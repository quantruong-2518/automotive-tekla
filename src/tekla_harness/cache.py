"""Content-addressed read cache (ADR-0006, ADR-0008).

Two levels, as in the Bazel Remote Execution API and git:

- **CAS** `cas/<2 hex>/<sha256>`: output blobs, named by the SHA-256 of their bytes.
- **Action cache** `ac/<2 hex>/<key>.json`: action key -> output digests + recorded result.
  The entry is written last, so it is the commit marker: an entry exists only after all of
  its blobs do.

The action key is SHA-256 over a domain tag plus canonical JSON of everything that can change
the result (a constructive trace, in the terms of "Build Systems à la Carte"). Every read is
verified (entry schema, key, blob size and digest); anything wrong is a miss and is discarded.
Writes go through a temp file in the target folder, fsync, then os.replace. Failures are
never cached; that is the caller's rule (only `put` successful results).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import IO, Any

from tekla_harness.detect import sha256_file
from tekla_harness.schemas import validate

CACHE_FORMAT = 1
ENTRY_SCHEMA_VERSION = "0.1"
# Domain separation: the same bytes hashed for another purpose never collide with a key.
_KEY_DOMAIN = b"tekla-harness/read-cache/action/v1\x00"
# https://bford.info/cachedir/ — tells backup and archive tools to skip this folder.
CACHEDIR_TAG_SIGNATURE = "Signature: 8a477f597d28d172789f06886806bc55"
_CACHEDIR_TAG = (
    f"{CACHEDIR_TAG_SIGNATURE}\n"
    "# This file is a cache directory tag created by tekla-harness.\n"
    "# For information about cache directory tags, see https://bford.info/cachedir/\n"
)
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _check_json(value: Any, where: str = "$") -> None:
    """Key material is str/int/bool/None, lists and str-keyed dicts only.

    Floats are refused: they have no single canonical text form (RFC 8785 needs ECMAScript
    number formatting, which json.dumps does not promise). Use strings or integers instead.
    """
    if value is None or isinstance(value, (str, int)):  # bool is an int; float is not
        return
    if isinstance(value, list):
        for i, item in enumerate(value):
            _check_json(item, f"{where}[{i}]")
        return
    if isinstance(value, dict):
        for k, item in value.items():
            if not isinstance(k, str):
                raise TypeError(f"{where}: key {k!r} is not a string")
            _check_json(item, f"{where}.{k}")
        return
    raise TypeError(f"{where}: {type(value).__name__} is not allowed in cache key material")


def canonical_json(value: Any) -> bytes:
    _check_json(value)
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return text.encode("utf-8")


def action_key(material: dict[str, Any]) -> str:
    return hashlib.sha256(_KEY_DOMAIN + canonical_json(material)).hexdigest()


def _check_digest(value: str) -> str:
    if not _HEX64.match(value):
        raise ValueError(f"not a SHA-256 hex digest: {value!r}")
    return value


def _warn(message: str) -> None:
    sys.stderr.write(f"read cache: {message}\n")


def _fsync_dir(folder: Path) -> None:
    """Make a rename durable on POSIX. Windows has no directory fsync; NTFS journals metadata."""
    if os.name != "posix":
        return
    try:
        fd = os.open(folder, os.O_RDONLY)
    except OSError as exc:
        _warn(f"cannot open {folder} to fsync it ({exc}); entry is valid but may not survive power loss")
        return
    try:
        os.fsync(fd)
    except OSError as exc:  # some file systems (network, WSL drvfs) refuse directory fsync
        _warn(f"directory fsync failed for {folder} ({exc}); entry may not survive power loss")
    finally:
        os.close(fd)


def _atomic_write(target: Path, write: Callable[[IO[bytes]], object]) -> None:
    """Temp file in the same folder, fsync, os.replace, fsync the folder.

    os.replace is atomic on POSIX. On Windows the replace is not documented as atomic, and it
    fails with PermissionError while another process has the target open; readers therefore
    never trust a file without verifying it (see ReadCache.get).
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".tmp-")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            write(fh)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            tmp.replace(target)  # os.replace semantics
        except PermissionError:
            # Windows: a concurrent reader or writer holds the target. If it already holds the
            # same bytes, the other writer won with an identical result; otherwise fail loudly.
            if target.is_file() and sha256_file(target) == sha256_file(tmp):
                tmp.unlink()
                return
            raise
        _fsync_dir(target.parent)
    finally:
        tmp.unlink(missing_ok=True)


class _Corrupt(Exception):
    """An entry or blob that fails verification."""


def _unlink(path: Path) -> None:
    """Delete if present; a failure (Windows: file in use) is reported, never raised, because
    the caller is already treating the entry as a miss."""
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        _warn(f"could not delete {path.name} ({exc}); it will be verified again next time")


@dataclass(frozen=True)
class CacheEntry:
    key: str
    action: dict[str, Any]
    outputs: dict[str, dict[str, Any]]
    result: dict[str, Any]
    root: Path

    def output_path(self, name: str) -> Path:
        return self.root / "cas" / self.outputs[name]["sha256"][:2] / self.outputs[name]["sha256"]


class ReadCache:
    """One project's cache folder. Never share a cache across projects (ADR-0006)."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()

    # --- paths ------------------------------------------------------------------------

    def entry_path(self, key: str) -> Path:
        _check_digest(key)
        return self.root / "ac" / key[:2] / f"{key}.json"

    def blob_path(self, digest: str) -> Path:
        _check_digest(digest)
        return self.root / "cas" / digest[:2] / digest

    _OWN_NAMES = frozenset({"ac", "cas", ".gitignore", "CACHEDIR.TAG"})

    def check_usable(self) -> None:
        """Refuse a folder that already holds something else: tagging it would make backup
        tools and git skip unrelated files (e.g. `--cache-dir projects/<id>`)."""
        if not self.root.exists():
            return
        if not self.root.is_dir():
            raise ValueError(f"cache folder {self.root} is not a folder")
        if (self.root / "CACHEDIR.TAG").is_file():
            return
        foreign = sorted(
            p.name
            for p in self.root.iterdir()
            if p.name not in self._OWN_NAMES and not p.name.startswith(".tmp-")  # our temp files
        )
        if foreign:
            raise ValueError(
                f"cache folder {self.root} is not empty and is not a read cache "
                f"(contains {', '.join(foreign[:3])}); choose an empty or dedicated folder"
            )

    def _init_dir(self) -> None:
        """Self-ignoring for git and tagged for backup tools, like .pytest_cache."""
        self.check_usable()
        self.root.mkdir(parents=True, exist_ok=True)
        for name, text in ((".gitignore", "*\n"), ("CACHEDIR.TAG", _CACHEDIR_TAG)):
            path = self.root / name
            if not path.is_file():
                data = text.encode("utf-8")
                _atomic_write(path, lambda fh, data=data: fh.write(data))

    # --- read -------------------------------------------------------------------------

    def get(self, key: str) -> CacheEntry | None:
        """A verified entry, or None. I/O errors are a miss (the entry may be fine, e.g. a
        Windows sharing violation); anything malformed is a miss and is deleted."""
        path = self.entry_path(key)
        try:
            return self._verified(key, path)
        except FileNotFoundError:
            return None
        except OSError as exc:
            _warn(f"entry {key[:12]} unreadable right now ({exc}); treated as a miss")
            return None
        except _Corrupt as exc:
            self.invalidate(key, str(exc))
            return None
        except (ValueError, TypeError, KeyError) as exc:  # e.g. a float smuggled into the action
            self.invalidate(key, f"entry unusable ({type(exc).__name__}: {exc})")
            return None

    def _verified(self, key: str, path: Path) -> CacheEntry:
        raw = path.read_bytes()
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _Corrupt(f"entry is not valid JSON ({exc})") from exc
        if not isinstance(data, dict):
            raise _Corrupt("entry is not a JSON object")
        problems = validate("cache-entry", data)
        if problems:
            raise _Corrupt(f"entry fails its schema at {problems[0].path or '/'}: {problems[0].message}")
        if data["key"] != key or action_key(data["action"]) != key:
            raise _Corrupt("entry key does not match its action")
        outputs = {o["name"]: {"sha256": o["sha256"], "size": o["size"]} for o in data["outputs"]}
        for name, meta in outputs.items():
            blob = self.blob_path(meta["sha256"])
            if not blob.is_file():
                raise _Corrupt(f"output {name} is missing")
            if blob.stat().st_size != meta["size"] or sha256_file(blob) != meta["sha256"]:
                _unlink(blob)
                raise _Corrupt(f"output {name} is corrupt")
        return CacheEntry(key, data["action"], outputs, data["result"], self.root)

    def invalidate(self, key: str, reason: str, strict: bool = False) -> None:
        """Delete an entry (blobs stay: other entries may share them). With `strict`, an entry
        that cannot be deleted raises OSError instead of a warning."""
        path = self.entry_path(key)
        if not path.exists():
            return
        if strict:
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                raise OSError(f"cannot refresh: entry {key[:12]} cannot be deleted ({exc})") from exc
        else:
            _unlink(path)
        if not path.exists():
            _warn(f"discarded entry {key[:12]}: {reason}")

    # --- write ------------------------------------------------------------------------

    def put(
        self, key: str, material: dict[str, Any], outputs: dict[str, Path], result: dict[str, Any]
    ) -> CacheEntry:
        if action_key(material) != key:
            raise ValueError("key does not match its material")
        self._init_dir()
        stored: list[dict[str, Any]] = []
        for name, src in sorted(outputs.items()):
            digest = sha256_file(src)
            blob = self.blob_path(digest)
            if not (blob.is_file() and sha256_file(blob) == digest):
                with Path(src).open("rb") as fh_src:
                    _atomic_write(blob, lambda fh, s=fh_src: shutil.copyfileobj(s, fh))
            stored.append({"name": name, "sha256": digest, "size": Path(src).stat().st_size})
        entry = {
            "schema_version": ENTRY_SCHEMA_VERSION,
            "cache_format": CACHE_FORMAT,
            "key": key,
            "action": material,
            "outputs": stored,
            "result": result,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        problems = validate("cache-entry", entry)
        if problems:  # a bug in the caller, never a reason to write a bad entry
            raise ValueError(f"cache entry invalid: {problems[0].path}: {problems[0].message}")
        data = json.dumps(entry, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        _atomic_write(self.entry_path(key), lambda fh: fh.write(data))  # commit marker: last
        return CacheEntry(key, material, {o["name"]: o for o in stored}, result, self.root)
