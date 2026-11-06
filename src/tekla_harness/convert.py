"""dwg_to_dxf: ODA File Converter, then LibreDWG `dwg2dxf` (ADR-0005).

A conversion counts only if the DXF exists and ezdxf opens it; the exit code alone proves
nothing. Every attempt is returned for the read log. Converters run in a temporary folder;
the input folder is never written.

Executables come from the call, then the environment (HARNESS_ODA_CONVERTER,
HARNESS_DWG2DXF), then PATH. UNVERIFIED: the ODA argument order below is from memory of the
ODA docs (input folder, output folder, version, type, recurse, audit, filter); check it
against the installed version on the Tekla machine.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ezdxf.filemanagement import readfile

from tekla_harness.readlog import Attempt, timed_attempt

ODA_TOOL, LIBREDWG_TOOL = "oda_file_converter", "libredwg_dwg2dxf"
_ENV = {ODA_TOOL: "HARNESS_ODA_CONVERTER", LIBREDWG_TOOL: "HARNESS_DWG2DXF"}
_PATH_NAMES = {ODA_TOOL: "ODAFileConverter", LIBREDWG_TOOL: "dwg2dxf"}
CONFIDENCE_CAP = {ODA_TOOL: "high", LIBREDWG_TOOL: "medium"}
ODA_OUTPUT_VERSION = "ACAD2018"
DEFAULT_TIMEOUT_S = 300


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


def _split_command(value: str) -> list[str]:
    """An executable path from the environment or the CLI. Paths may contain spaces."""
    return [value]


def resolve_converters(
    oda: list[str] | None = None, dwg2dxf: list[str] | None = None
) -> dict[str, list[str]]:
    resolved: dict[str, list[str]] = {}
    for tool, given in ((ODA_TOOL, oda), (LIBREDWG_TOOL, dwg2dxf)):
        if given:
            resolved[tool] = given
        elif env := os.environ.get(_ENV[tool]):
            resolved[tool] = _split_command(env)
        elif found := shutil.which(_PATH_NAMES[tool]):
            resolved[tool] = [found]
    return resolved


def _command(tool: str, exe: list[str], src: Path, out_dir: Path) -> tuple[list[str], Path]:
    out = out_dir / f"{src.stem}.dxf"
    if tool == ODA_TOOL:
        args = [str(src.parent), str(out_dir), ODA_OUTPUT_VERSION, "DXF", "0", "1", src.name]
    else:
        args = ["-y", "-o", str(out), str(src)]
    return [*exe, *args], out


def _tail(text: str, limit: int = 300) -> str:
    text = text.strip()
    return text if len(text) <= limit else "…" + text[-limit:]


def _try(tool: str, exe: list[str], dwg: Path, timeout: float) -> tuple[Attempt, Path | None, Path]:
    """Run one converter in its own temp folder. Returns (attempt, dxf or None, temp dir)."""
    work = Path(tempfile.mkdtemp(prefix=f"{tool}-"))
    src_dir, out_dir = work / "in", work / "out"
    src_dir.mkdir()
    out_dir.mkdir()
    src = Path(shutil.copy2(dwg, src_dir / dwg.name))
    cmd, out = _command(tool, exe, src, out_dir)
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


def dwg_to_dxf(
    dwg: Path,
    out_dir: Path,
    oda: list[str] | None = None,
    dwg2dxf: list[str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> ConversionResult:
    dwg, out_dir = Path(dwg).resolve(), Path(out_dir).resolve()
    if out_dir == dwg.parent or dwg.parent in out_dir.parents:
        raise ValueError(f"output folder {out_dir} is inside the input folder {dwg.parent}")
    converters = resolve_converters(oda, dwg2dxf)
    if not converters:
        raise NoConverterError(
            f"no DWG converter: set {_ENV[ODA_TOOL]} or {_ENV[LIBREDWG_TOOL]}, "
            f"or put {_PATH_NAMES[ODA_TOOL]} / {_PATH_NAMES[LIBREDWG_TOOL]} on PATH"
        )
    result = ConversionResult(dwg, None, None, None)
    for tool in (ODA_TOOL, LIBREDWG_TOOL):
        if tool not in converters:
            result.warnings.append(f"{tool} not configured; skipped")
            continue
        attempt, produced, work = _try(tool, converters[tool], dwg, timeout)
        result.attempts.append(attempt)
        try:
            if produced is not None:
                out_dir.mkdir(parents=True, exist_ok=True)
                result.dxf = Path(shutil.copy2(produced, out_dir / produced.name))
                result.converter, result.confidence_cap = tool, CONFIDENCE_CAP[tool]
                if tool != ODA_TOOL:
                    result.warnings.append(
                        f"fallback converter {tool} used: confidence capped at {CONFIDENCE_CAP[tool]}"
                    )
                return result
        finally:
            shutil.rmtree(work, ignore_errors=True)
    result.warnings.append("all converters failed: ask the engineer for a DXF or PDF export of this sheet")
    return result
