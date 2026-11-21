"""saved evidence: `--save` of `harness geometry` and `harness contents`, the files a measured finding cites.

`--save` writes the exact stdout document (byte for byte, one trailing newline) to
`<work>/geometry/<command>-<where>-<qhash8>-<chash8>.json`:

  * `<where>` is the sheet id(s) of the query with every run of characters outside `A-Za-z0-9._+-` as one `-`
    (`model#06` -> `model-06`, several sheets joined by `+`), `bbox` for a region query, `all` for a
    geometry query with neither;
  * `qhash8` is the first 8 hex of sha256 over the drawing's input-relative path, its inventory sha256 and
    the canonical JSON of the document's `query` (keys sorted, no spaces, UTF-8; floats as `json.dumps`
    prints them), each part followed by a NUL byte: two drawings with the same bytes get two names;
  * `chash8` is the first 8 hex of sha256 over the bytes written.

A saved file never changes. The same query on the same drawing with the same bytes gives the same name: a
repeat writes nothing. New bytes (another tool version, another converter) give a new name next to the old
file, so a finding recorded from the old file keeps resolving. A name that exists with other bytes is never
overwritten (exit 1). A new drawing version changes the inventory sha256 and so `qhash8`: `harness finding
add` recomputes both hashes from the file it is given and refuses a file saved for another drawing version
or edited after `--save`.

The command computes the document without the work lock. Only the write holds it (`work_lock`, ADR-0011),
and it first checks that the inventory sha256 is still the one read before the computation. Without `--save`
a command is read-only and never locks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
from pathlib import Path
from typing import Any

from tekla_harness.sheet_text import EXIT_INVALID, ReaderError, load_inventory
from tekla_harness.worklock import WorkLockError, lock_wait, work_lock

GEOMETRY_DIR = "geometry"
EXIT_ENV = 3
EXIT_USAGE = 2
COMMANDS = ("geometry", "contents")
_UNSAFE = re.compile(r"[^A-Za-z0-9._+-]+")
_MAX_SLUG = 60
# <command>-<where>-<qhash8>-<chash8>.json
NAME = re.compile(
    r"^(?P<prefix>(?P<command>geometry|contents)-.+-[0-9a-f]{8})-(?P<content>[0-9a-f]{8})\.json$"
)


def add_save_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--save",
        action="store_true",
        help=f"also write the document to <work>/{GEOMETRY_DIR}/ (never overwrites a saved file; takes the "
        "work lock only for the write; prints 'saved: <path>' on stderr) so "
        "`harness finding add --kind measured` can cite it",
    )


def _canonical(query: dict[str, Any]) -> str:
    return json.dumps(query, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def query_hash(file_rel: str, file_sha256: str, query: dict[str, Any]) -> str:
    """The 8 hex characters of a saved document's query part: drawing path, drawing sha256, query."""
    material = "\0".join((file_rel, file_sha256, _canonical(query)))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:8]


def content_hash(data: bytes) -> str:
    """The 8 hex characters of a saved document's content part: the bytes written."""
    return hashlib.sha256(data).hexdigest()[:8]


def _where(command: str, query: dict[str, Any]) -> str:
    if command == "contents":
        raw = str(query["sheet"])
    elif query.get("bbox") is not None:
        raw = "bbox"
    elif query.get("sheet"):
        raw = "+".join(query["sheet"])
    else:
        raw = "all"
    return _UNSAFE.sub("-", raw).strip("-")[:_MAX_SLUG] or "x"


def file_name(command: str, doc: dict[str, Any], file_sha256: str, data: bytes) -> str:
    """`<command>-<where>-<qhash8>-<chash8>.json` of the geometry or contents document `doc`, written as
    `data`, of its drawing with this sha256."""
    q = query_hash(str(doc["file"]), file_sha256, doc["query"])
    return f"{command}-{_where(command, doc['query'])}-{q}-{content_hash(data)}.json"


def redo_command(work_dir: Path | str, command: str, file_rel: str, query: dict[str, Any]) -> str:
    """The `harness <command> ... --save` line that saves `query` again."""
    q = shlex.quote
    parts = ["harness", command, q(str(work_dir)), q(file_rel)]

    def option(flag: str, values: list[str]) -> None:
        if values:
            parts.extend([flag, *(q(v) for v in values)])

    if command == "contents":
        option("--sheet", [str(query["sheet"])])
        option("--outline-layer", list(query["outline_layers"]))
        option("--circle-layer", list(query["circle_layers"]))
        option("--max-long", [repr(query["max_long"])])
        if query.get("marks") is not None:
            option("--marks", [str(query["marks"])])
        option("--mark-radius", [repr(query["mark_radius"])])
        if query.get("dims"):
            parts.append("--dims")
    else:
        if query.get("bbox") is not None:
            option("--bbox", [repr(v) for v in query["bbox"]])
        else:
            option("--sheet", list(query.get("sheet") or []))
        option("--layer", list(query.get("layer") or []))
    if query.get("detail"):
        parts.append("--detail")
    if query.get("max") is not None:
        option("--max", [str(query["max"])])
    option("--tol", [repr(query["tol"])])
    parts.extend(["[--input-dir DIR]", "--save"])
    return " ".join(parts)


def drawing_sha256(work_dir: Path | str, file_rel: str) -> str:
    """The inventory's sha256 of one drawing. Raises ReaderError."""
    inv = load_inventory(work_dir)
    for row in inv.doc["files"]:
        if row["path"] == file_rel:
            return str(row["sha256"])
    raise ReaderError(EXIT_INVALID, f"'{file_rel}' is not in inventory.json")


def sha_before_save(work_dir: Path | str, file_rel: str) -> str | None:
    """The drawing's inventory sha256 to read before the computation of a command with `--save`; None when it
    cannot be read (the computation then fails with its own message, or `save_document` refuses). Raises
    ReaderError (usage) when the work folder does not exist."""
    work = Path(work_dir)
    if not work.is_dir():
        raise ReaderError(EXIT_USAGE, f"{work} is not a folder: nothing was run or written")
    try:
        return drawing_sha256(work_dir, file_rel)
    except ReaderError:
        return None


def save_document(work_dir: Path | str, doc: dict[str, Any], text: str, sha_before: str | None) -> str:
    """Write `text` (the document exactly as printed, newline included) under the work lock and return its
    work-relative path with forward slashes. `sha_before`: the drawing's inventory sha256 read before the
    document was computed (`sha_before_save`); another one now means a re-intake during the run and the
    document is refused. A saved file is never overwritten: the same bytes are a no-op, other bytes under
    the same name are refused. Raises ReaderError."""
    work = Path(work_dir).resolve()
    if not work.is_dir():
        raise ReaderError(EXIT_USAGE, f"{work} is not a folder: nothing was written")
    command = str(doc["kind"])
    data = text.encode("utf-8")  # bytes: no newline translation on Windows
    try:
        with work_lock(work, f"{command} --save", wait=lock_wait(work)):
            sha = drawing_sha256(work, str(doc["file"]))
            if sha_before is None or sha != sha_before:
                raise ReaderError(
                    EXIT_INVALID,
                    f"the inventory sha256 of {doc['file']} changed while {command} was running "
                    "(a new intake?): nothing was saved; run the command again",
                )
            name = file_name(command, doc, sha, data)
            path = work / GEOMETRY_DIR / name
            try:
                if path.exists():
                    if path.read_bytes() != data:
                        raise ReaderError(
                            EXIT_INVALID,
                            f"{path} exists with other bytes: a saved file is never overwritten "
                            "(was it edited by hand? move it away and save again)",
                        )
                    return f"{GEOMETRY_DIR}/{name}"
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_name(path.name + ".tmp")
                tmp.write_bytes(data)
                tmp.replace(path)
            except OSError as exc:
                raise ReaderError(EXIT_ENV, f"cannot write {path}: {exc}") from exc
    except WorkLockError as exc:
        raise ReaderError(exc.exit_code, str(exc)) from exc
    return f"{GEOMETRY_DIR}/{name}"
