"""dwg_to_dxf: ODA File Converter, then LibreDWG `dwg2dxf` (ADR-0005).

A conversion counts only if the DXF exists and ezdxf opens it; the exit code alone proves
nothing. Every attempt is returned for the read log. The input is copied once into a staging
folder and every converter works on that copy; the input folder is never written.

Executables come from the call, then the environment (HARNESS_ODA_CONVERTER,
HARNESS_DWG2DXF), then PATH; a bare name is resolved on PATH once and the resolved file is
both run and hashed. UNVERIFIED: the ODA argument order below is from memory of the ODA docs
(input folder, output folder, version, type, recurse, audit, filter); check it against the
installed version on the Tekla machine.

With a ReadCache (ADR-0007), a conversion whose every attempt succeeded is recorded under an
action key built from everything that can change the result: the staged input's bytes, the
converter chain (each command word that is a file by content digest, in order), the argument
templates, the ezdxf version (the success oracle) and the source of the modules that produce
the result. A result with any failed attempt is never cached: a transient failure must not
pin a fallback result.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache
from importlib.metadata import version
from pathlib import Path
from typing import Any

from ezdxf.filemanagement import readfile

from tekla_harness.cache import CACHE_FORMAT, CacheEntry, ReadCache, action_key
from tekla_harness.detect import sha256_file
from tekla_harness.readlog import Attempt, timed_attempt

ODA_TOOL, LIBREDWG_TOOL = "oda_file_converter", "libredwg_dwg2dxf"
_ENV = {ODA_TOOL: "HARNESS_ODA_CONVERTER", LIBREDWG_TOOL: "HARNESS_DWG2DXF"}
_PATH_NAMES = {ODA_TOOL: "ODAFileConverter", LIBREDWG_TOOL: "dwg2dxf"}
CONFIDENCE_CAP = {ODA_TOOL: "high", LIBREDWG_TOOL: "medium"}
ODA_OUTPUT_VERSION = "ACAD2018"
# Argument templates; part of the cache key, so any change to them invalidates entries.
_ARGS = {
    ODA_TOOL: ("{src_dir}", "{out_dir}", ODA_OUTPUT_VERSION, "DXF", "0", "1", "{src_name}"),
    LIBREDWG_TOOL: ("-y", "-o", "{out}", "{src}"),
}
DEFAULT_TIMEOUT_S = 300
EZDXF_VERSION = version("ezdxf")
_OUTPUT_NAME = "output.dxf"  # logical name in the cache; the real file takes the input's stem
# Modules whose code decides what a cached conversion contains or how it is replayed.
_CODE_FILES = ("convert.py", "cache.py", "readlog.py", "detect.py")


class NoConverterError(RuntimeError):
    """No DWG converter is configured or on PATH: an environment problem (exit 3)."""


@dataclass
class ConversionResult:
    dwg: Path
    dxf: Path | None
    converter: str | None
    confidence_cap: str | None
    attempts: list[Attempt] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cache: dict[str, Any] | None = None  # {"hit": bool, "key": str} when a cache was used


def _split_command(value: str) -> list[str]:
    """An executable path from the environment or the CLI. Paths may contain spaces."""
    return [value]


def _resolve_word(word: str) -> str:
    """Turn the executable into one absolute path that is both run and hashed.

    A bare name is looked up on PATH, as subprocess does on POSIX (a same-named file in the
    current folder is not what runs). A path is resolved; a Windows path without its extension
    goes through `which` for PATHEXT. Unresolvable words stay as given and fail as attempts."""
    if not any(sep in word for sep in (os.sep, os.altsep) if sep):
        return shutil.which(word) or word
    if Path(word).is_file():
        return str(Path(word).resolve())
    return shutil.which(word) or word


def resolve_converters(
    oda: list[str] | None = None, dwg2dxf: list[str] | None = None
) -> dict[str, list[str]]:
    resolved: dict[str, list[str]] = {}
    for tool, given in ((ODA_TOOL, oda), (LIBREDWG_TOOL, dwg2dxf)):
        if given:
            command = list(given)
        elif env := os.environ.get(_ENV[tool]):
            command = _split_command(env)
        elif found := shutil.which(_PATH_NAMES[tool]):
            command = [found]
        else:
            continue
        resolved[tool] = [_resolve_word(command[0]), *command[1:]]
    return resolved


def _command(tool: str, exe: list[str], src: Path, out_dir: Path) -> tuple[list[str], Path]:
    out = out_dir / f"{src.stem}.dxf"
    values = {"src_dir": src.parent, "out_dir": out_dir, "src_name": src.name, "out": out, "src": src}
    return [*exe, *(arg.format(**{k: str(v) for k, v in values.items()}) for arg in _ARGS[tool])], out


# --- cache key -----------------------------------------------------------------------

_FILE_DIGESTS: dict[tuple[str, int, int], str] = {}


def _file_digest(path: Path) -> str:
    """Content digest of an executable, memoised per process by (realpath, size, mtime_ns),
    the cheap identity check ccache uses for compilers; the digest itself is of the bytes."""
    real = Path(path).resolve()
    st = real.stat()
    ident = (str(real), st.st_size, st.st_mtime_ns)
    if ident not in _FILE_DIGESTS:
        _FILE_DIGESTS[ident] = sha256_file(real)
    return _FILE_DIGESTS[ident]


def _command_identity(exe: list[str]) -> list[dict[str, str]]:
    """Each command word that is a file is identified by its bytes, never by its path."""
    return [{"file_sha256": _file_digest(Path(w))} if Path(w).is_file() else {"arg": w} for w in exe]


@cache
def _code_digest() -> str:
    """Digest of the modules in _CODE_FILES, line endings normalised (a CRLF checkout of the
    same code gives the same key)."""
    digest = hashlib.sha256()
    here = Path(__file__).parent
    for name in _CODE_FILES:
        data = (here / name).read_bytes().replace(b"\r\n", b"\n")
        digest.update(f"{name}\0{len(data)}\0".encode() + data)
    return digest.hexdigest()


def _key_material(input_sha256: str, converters: dict[str, list[str]]) -> dict[str, Any]:
    return {
        "action": "dwg_to_dxf",
        "cache_format": CACHE_FORMAT,
        "input_sha256": input_sha256,
        "chain": [
            {"tool": tool, "command": _command_identity(converters[tool]), "args": list(_ARGS[tool])}
            for tool in (ODA_TOOL, LIBREDWG_TOOL)
            if tool in converters
        ],
        "oracle": {"ezdxf": EZDXF_VERSION},
        "code_sha256": _code_digest(),
    }


def _inside(path: Path, folder: Path) -> bool:
    return path == folder or folder in path.parents


def _tail(text: str, limit: int = 300) -> str:
    text = text.strip()
    return text if len(text) <= limit else "…" + text[-limit:]


def _deliver(src: Path, dst: Path) -> Path:
    """Copy a validated DXF to the caller's output folder."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    return Path(shutil.copy2(src, dst))


# --- conversion ----------------------------------------------------------------------


def _try(tool: str, exe: list[str], src: Path, timeout: float) -> tuple[Attempt, Path | None, Path]:
    """Run one converter in its own temp folder on a copy of the staged input.
    Returns (attempt, dxf or None, temp dir)."""
    work = Path(tempfile.mkdtemp(prefix=f"{tool}-"))
    src_dir, out_dir = work / "in", work / "out"
    src_dir.mkdir()
    out_dir.mkdir()
    local = Path(shutil.copy2(src, src_dir / src.name))
    cmd, out = _command(tool, exe, local, out_dir)
    with timed_attempt(tool) as attempt:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        except (FileNotFoundError, PermissionError) as exc:
            attempt.fail(f"converter not found or not executable: {exc}")
            return attempt, None, work
        except subprocess.TimeoutExpired:
            attempt.fail(f"timed out after {timeout:g} s")
            return attempt, None, work
        if proc.returncode != 0:
            attempt.fail(f"exit code {proc.returncode}: {_tail(proc.stderr or proc.stdout)}")
            return attempt, None, work
        if not out.is_file() or out.stat().st_size == 0:
            attempt.fail(
                f"exit code 0 but no DXF written ({_tail(proc.stderr or proc.stdout) or 'no output'})"
            )
            return attempt, None, work
        try:
            readfile(out)
        except Exception as exc:  # ezdxf raises more than DXFError on corrupt files (e.g. StopIteration)
            attempt.fail(f"exit code 0 but the DXF cannot be opened by ezdxf: {type(exc).__name__}: {exc}")
            return attempt, None, work
    return attempt, out, work


def _run_chain(
    src: Path,
    dwg: Path,
    out_dir: Path,
    converters: dict[str, list[str]],
    timeout: float,
    on_success: Callable[[Path, ConversionResult], None] | None = None,
) -> ConversionResult:
    """Try converters in order on the staged copy `src`. `on_success` receives the validated
    DXF inside the converter's work folder, before that folder is deleted."""
    result = ConversionResult(dwg, None, None, None)
    for tool in (ODA_TOOL, LIBREDWG_TOOL):
        if tool not in converters:
            result.warnings.append(f"{tool} not configured; skipped")
            continue
        attempt, produced, work = _try(tool, converters[tool], src, timeout)
        result.attempts.append(attempt)
        try:
            if produced is not None:
                result.converter, result.confidence_cap = tool, CONFIDENCE_CAP[tool]
                if tool != ODA_TOOL:
                    result.warnings.append(
                        f"fallback converter {tool} used: confidence capped at {CONFIDENCE_CAP[tool]}"
                    )
                if on_success is not None:
                    on_success(produced, result)
                result.dxf = _deliver(produced, out_dir / f"{dwg.stem}.dxf")
                return result
        finally:
            shutil.rmtree(work, ignore_errors=True)
    result.warnings.append("all converters failed: ask the engineer for a DXF or PDF export of this sheet")
    return result


# --- cache ---------------------------------------------------------------------------


def _replay(entry: CacheEntry, dwg: Path, out_dir: Path) -> ConversionResult:
    """Rebuild a ConversionResult from a verified entry. Raises on anything a fresh run of this
    code could not have recorded, so a well-formed but wrong entry is never served."""
    recorded = entry.result
    converter, cap = recorded["converter"], recorded["confidence_cap"]
    if converter not in CONFIDENCE_CAP or cap != CONFIDENCE_CAP[converter]:
        raise ValueError(f"recorded converter/cap {converter!r}/{cap!r} is inconsistent")
    raw_attempts, warnings = recorded["attempts"], recorded["warnings"]
    if not isinstance(raw_attempts, list) or not isinstance(warnings, list):
        raise TypeError("recorded attempts and warnings must be lists")
    if not all(isinstance(w, str) for w in warnings):
        raise TypeError("recorded warnings must be strings")
    attempts = [Attempt.from_dict(a) for a in raw_attempts]
    if not attempts or any(a.status != "ok" for a in attempts) or attempts[-1].tool != converter:
        raise ValueError("recorded attempts are not a clean success by the recorded converter")
    if set(entry.outputs) != {_OUTPUT_NAME}:
        raise ValueError(f"recorded outputs {sorted(entry.outputs)} are not [{_OUTPUT_NAME!r}]")
    dxf = _deliver(entry.output_path(_OUTPUT_NAME), out_dir / f"{dwg.stem}.dxf")
    return ConversionResult(dwg, dxf, converter, cap, attempts, list(warnings), None)


def _cached_run(
    src: Path,
    dwg: Path,
    out_dir: Path,
    converters: dict[str, list[str]],
    timeout: float,
    cache_: ReadCache,
    refresh: bool,
) -> ConversionResult:
    material = _key_material(sha256_file(src), converters)
    key = action_key(material)
    if refresh:
        cache_.invalidate(key, "refresh requested")  # a failed recompute must not leave it behind
    elif (entry := cache_.get(key)) is not None:
        try:
            replayed = _replay(entry, dwg, out_dir)
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            cache_.invalidate(key, f"recorded result unusable ({type(exc).__name__}: {exc})")
        else:
            replayed.cache = {"hit": True, "key": key}
            return replayed

    def record(produced: Path, result: ConversionResult) -> None:
        failed = [a.tool for a in result.attempts if a.status != "ok"]
        if failed:  # a fallback after a failure may be transient: never pin it
            result.warnings.append(
                f"read cache: result not cached because {', '.join(failed)} failed in this run; "
                "fix that converter to get cache hits"
            )
            return
        recorded = {
            "converter": result.converter,
            "confidence_cap": result.confidence_cap,
            "attempts": [a.as_dict() for a in result.attempts],
            "warnings": list(result.warnings),
        }
        try:
            cache_.put(key, material, {_OUTPUT_NAME: produced}, recorded)
        except (OSError, ValueError) as exc:  # the conversion stands; only the cache write failed
            result.warnings.append(f"read cache write failed, result not cached: {exc}")

    result = _run_chain(src, dwg, out_dir, converters, timeout, on_success=record)
    result.cache = {"hit": False, "key": key}
    return result


def dwg_to_dxf(
    dwg: Path,
    out_dir: Path,
    oda: list[str] | None = None,
    dwg2dxf: list[str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
    cache: ReadCache | None = None,
    refresh: bool = False,
) -> ConversionResult:
    """Convert one DWG. With `cache`, a recorded clean success of the same action is replayed;
    `refresh` deletes the recorded result first, then recomputes."""
    dwg, out_dir = Path(dwg).resolve(), Path(out_dir).resolve()
    if _inside(out_dir, dwg.parent):
        raise ValueError(f"output folder {out_dir} is inside the input folder {dwg.parent}")
    if cache is not None:
        if _inside(cache.root, dwg.parent):
            raise ValueError(f"cache folder {cache.root} is inside the input folder {dwg.parent}")
        if _inside(dwg, cache.root):
            raise ValueError(f"cache folder {cache.root} contains the input {dwg}")
        cache.check_usable()
    converters = resolve_converters(oda, dwg2dxf)
    if not converters:
        raise NoConverterError(
            f"no DWG converter: set {_ENV[ODA_TOOL]} or {_ENV[LIBREDWG_TOOL]}, "
            f"or put {_PATH_NAMES[ODA_TOOL]} / {_PATH_NAMES[LIBREDWG_TOOL]} on PATH"
        )
    staging = Path(tempfile.mkdtemp(prefix="dwg-stage-"))
    try:
        # One immutable copy: the key and every converter see the same bytes, even if the
        # input file changes while we run.
        src = Path(shutil.copy2(dwg, staging / dwg.name))
        if cache is None:
            return _run_chain(src, dwg, out_dir, converters, timeout)
        return _cached_run(src, dwg, out_dir, converters, timeout, cache, refresh)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
