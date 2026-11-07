"""dwg_to_dxf: ODA File Converter, then LibreDWG `dwg2dxf` (ADR-0005).

A conversion counts only if the DXF exists and ezdxf opens it; the exit code alone proves
nothing. Every attempt is returned for the read log. The input is copied once into a staging
folder and every converter works on that copy; the input folder is never written.

Executables come from the call, then the environment (HARNESS_ODA_CONVERTER,
HARNESS_DWG2DXF), then PATH; a bare name is resolved on PATH once and the resolved file is
both run and hashed. UNVERIFIED: the ODA argument order below is from memory of the ODA docs
(input folder, output folder, version, type, recurse, audit, filter); check it against the
installed version on the Tekla machine.

With a ReadCache (ADR-0008), a conversion whose every attempt succeeded is recorded under an
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

from ezdxf.document import Drawing
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
EMPTY_CHECK_MIN_DWG_BYTES = 10 * 1024  # below this an empty drawing is plausible
_LOWER_CAP = {"high": "medium", "medium": "medium", "low": "low"}
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
    stderr_tail: str = ""
    stderr_error_lines: int = 0
    stderr_warning_lines: int = 0
    cache: dict[str, Any] | None = None  # {"hit": bool, "key": str} when a cache was used


@dataclass
class _Probe:
    """What one successful run revealed beyond 'a DXF exists'."""

    stderr_tail: str = ""
    error_lines: int = 0
    warning_lines: int = 0
    empty: bool = False


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
        return str(Path(word).absolute())  # absolute, symlinks kept: argv[0] stays as given
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
    """Copy a validated DXF's bytes to the caller's output folder. Content only (copyfile):
    a hit and a fresh run give the same file mode and a current timestamp."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    return Path(shutil.copyfile(src, dst))


# --- conversion ----------------------------------------------------------------------


def _text(data: bytes) -> str:
    """Converter output in any encoding (Windows uses the ANSI code page): never raises."""
    return data.decode("utf-8", errors="replace")


def _count_prefixed(text: str, prefix: str) -> int:
    return sum(1 for line in text.splitlines() if line.startswith(prefix))


def _entity_count(doc: Drawing) -> int:
    return sum(len(layout) for layout in doc.layouts)


def _cap_for(tool: str, error_lines: int, empty: bool) -> str:
    """The one rule for a result's confidence cap (ADR-0005 and its ERROR-line amendment).
    Used for fresh runs and to check replayed ones."""
    if empty:
        return "low"
    base = CONFIDENCE_CAP[tool]
    return _LOWER_CAP[base] if error_lines > 0 else base


def _apply_probe(result: ConversionResult, tool: str, probe: _Probe) -> None:
    result.stderr_tail = probe.stderr_tail
    result.stderr_error_lines = probe.error_lines
    result.stderr_warning_lines = probe.warning_lines
    if probe.error_lines > 0:
        result.warnings.append(
            f"converter reported {probe.error_lines} ERROR lines; "
            "some objects/strings may be missing or truncated"
        )
        lowered = _cap_for(tool, probe.error_lines, empty=False)
        if lowered != result.confidence_cap:
            result.confidence_cap = lowered
            result.warnings.append(f"confidence cap lowered to {lowered} because of converter ERROR lines")
    if probe.empty:
        result.confidence_cap = _cap_for(tool, probe.error_lines, empty=True)
        result.warnings.append(
            "DXF opened but contains no entities in any layout although the DWG is not tiny: "
            "treat as a failed parse unless the engineer confirms the sheet is empty"
        )


def _try(tool: str, exe: list[str], src: Path, timeout: float) -> tuple[Attempt, Path | None, Path, _Probe]:
    """Run one converter in its own temp folder on a copy of the staged input.
    Returns (attempt, dxf or None, temp dir, probe). If it raises, it removes its temp dir
    itself: the folder holds a copy of a client drawing."""
    work = Path(tempfile.mkdtemp(prefix=f"{tool}-"))
    try:
        return _try_in(tool, exe, src, timeout, work)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise


def _try_in(
    tool: str, exe: list[str], src: Path, timeout: float, work: Path
) -> tuple[Attempt, Path | None, Path, _Probe]:
    probe = _Probe()
    src_dir, out_dir = work / "in", work / "out"
    src_dir.mkdir()
    out_dir.mkdir()
    local = Path(shutil.copy2(src, src_dir / src.name))
    cmd, out = _command(tool, exe, local, out_dir)
    with timed_attempt(tool) as attempt:
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            attempt.fail(f"timed out after {timeout:g} s")
            return attempt, None, work, probe
        except FileNotFoundError as exc:
            attempt.fail(f"converter not found: {exc}")
            return attempt, None, work, probe
        except OSError as exc:  # not executable, exec format error, ...
            attempt.fail(f"converter could not be started: {type(exc).__name__}: {exc}")
            return attempt, None, work, probe
        said = _tail(_text(proc.stderr or proc.stdout or b""))
        if proc.returncode != 0:
            attempt.fail(f"exit code {proc.returncode}: {said}")
            return attempt, None, work, probe
        if not out.is_file() or out.stat().st_size == 0:
            attempt.fail(f"exit code 0 but no DXF written ({said or 'no output'})")
            return attempt, None, work, probe
        stderr = _text(proc.stderr or b"")
        probe.stderr_tail = _tail(stderr)
        probe.error_lines = _count_prefixed(stderr, "ERROR")
        probe.warning_lines = _count_prefixed(stderr, "Warning")
        try:
            doc = readfile(out)
        except Exception as exc:  # ezdxf raises more than DXFError on corrupt files (e.g. StopIteration)
            attempt.fail(f"exit code 0 but the DXF cannot be opened by ezdxf: {type(exc).__name__}: {exc}")
            return attempt, None, work, probe
        if _entity_count(doc) == 0 and src.stat().st_size > EMPTY_CHECK_MIN_DWG_BYTES:
            probe.empty = True
            attempt.fail("DXF opened but contains no entities in any layout", status="partial")
    return attempt, out, work, probe


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
        attempt, produced, work, probe = _try(tool, converters[tool], src, timeout)
        result.attempts.append(attempt)
        try:
            if produced is not None:
                result.converter, result.confidence_cap = tool, CONFIDENCE_CAP[tool]
                if tool != ODA_TOOL:
                    result.warnings.append(
                        f"fallback converter {tool} used: confidence capped at {CONFIDENCE_CAP[tool]}"
                    )
                _apply_probe(result, tool, probe)
                result.dxf = _deliver(produced, out_dir / f"{dwg.stem}.dxf")
                if on_success is not None:  # after delivery: caching can never cost the DXF
                    on_success(produced, result)
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
    tail, errors, warns = (
        recorded["stderr_tail"],
        recorded["stderr_error_lines"],
        recorded["stderr_warning_lines"],
    )
    if not isinstance(tail, str) or any(type(n) is not int or n < 0 for n in (errors, warns)):
        raise TypeError("recorded stderr fields have wrong types")
    if converter not in CONFIDENCE_CAP or cap != _cap_for(converter, errors, empty=False):
        raise ValueError(f"recorded converter/cap {converter!r}/{cap!r} is inconsistent")
    raw_attempts, warnings = recorded["attempts"], recorded["warnings"]
    if not isinstance(raw_attempts, list) or not isinstance(warnings, list):
        raise TypeError("recorded attempts and warnings must be lists")
    if not all(isinstance(w, str) for w in warnings):
        raise TypeError("recorded warnings must be strings")
    attempts = [Attempt.from_dict(a) for a in raw_attempts]
    for a in attempts:
        if not (
            isinstance(a.tool, str)
            and isinstance(a.started_at, str)
            and type(a.duration_ms) is int
            and a.duration_ms >= 0
            and a.error is None
            and (a.tool_version is None or isinstance(a.tool_version, str))
        ):
            raise TypeError(f"recorded attempt has wrong field types: {a!r}")
    if not attempts or any(a.status != "ok" for a in attempts) or attempts[-1].tool != converter:
        raise ValueError("recorded attempts are not a clean success by the recorded converter")
    if set(entry.outputs) != {_OUTPUT_NAME}:
        raise ValueError(f"recorded outputs {sorted(entry.outputs)} are not [{_OUTPUT_NAME!r}]")
    dxf = _deliver(entry.output_path(_OUTPUT_NAME), out_dir / f"{dwg.stem}.dxf")
    return ConversionResult(
        dwg=dwg,
        dxf=dxf,
        converter=converter,
        confidence_cap=cap,
        attempts=attempts,
        warnings=list(warnings),
        stderr_tail=tail,
        stderr_error_lines=errors,
        stderr_warning_lines=warns,
    )


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
        # A failed recompute must not leave the old entry behind, so a refresh that cannot
        # delete it (Windows: file in use) stops instead of pretending.
        cache_.invalidate(key, "refresh requested", strict=True)
    elif (entry := cache_.get(key)) is not None:
        try:
            replayed = _replay(entry, dwg, out_dir)
        except (KeyError, TypeError, ValueError, AttributeError, OSError) as exc:
            cache_.invalidate(key, f"recorded result unusable ({type(exc).__name__}: {exc})")
        else:
            replayed.cache = {"hit": True, "key": key}
            return replayed

    def record(produced: Path, result: ConversionResult) -> None:
        unclean = [
            f"{a.tool} {'failed' if a.status == 'failed' else 'was partial'}"
            for a in result.attempts
            if a.status != "ok"
        ]
        if unclean:  # a fallback after a failure may be transient; a partial is suspect: never pin
            result.warnings.append(
                f"read cache: result not cached because {', '.join(unclean)} in this run; "
                "fix that converter to get cache hits"
            )
            return
        recorded = {
            "converter": result.converter,
            "confidence_cap": result.confidence_cap,
            "attempts": [a.as_dict() for a in result.attempts],
            "warnings": list(result.warnings),
            "stderr_tail": result.stderr_tail,
            "stderr_error_lines": result.stderr_error_lines,
            "stderr_warning_lines": result.stderr_warning_lines,
        }
        try:
            cache_.put(key, material, {_OUTPUT_NAME: produced}, recorded)
        except Exception as exc:  # the conversion stands; the failure is reported, not hidden
            result.warnings.append(f"read cache write failed, result not cached: {type(exc).__name__}: {exc}")

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
