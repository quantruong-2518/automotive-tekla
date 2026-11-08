"""intake: chain detect -> dwg_to_dxf -> probe_dxf over a whole input folder (workflow steps 1b, 2).

One deterministic command for the future `drawing-intake` skill. Writes into the work folder:

    read-log.json    every attempt per file (read-log schema)
    inventory.json   one row per file + summary, with the diff against the previous inventory.json of the
                     same work folder (intake schema, kind 'inventory')
    questions.json   the questions, one per (code, file), with stable key, registry id and answer
                     (intake schema, kind 'questions'; see questions.py)
    question-registry.json  key -> id for the three producers (written by questions.py)
    answers.json            only rewritten when an answer became stale (the file of its question changed
                            or was removed, or the question is no longer raised)
    probe/<path>.json       dxf-probe document of each DXF (native or converted)
    text/<path>.json        text-index document of each DXF that was probed (extract_text)
    converted/<path>.dxf    DXF produced from each DWG

Units: every probed file gets ONE blocking units question, `units_confirm_all` (answered with a structured
`unit=`); the probe's units_conflict / units_suspect / units_unknown questions are not asked apart: their
where / found / message are refs of that question (FOLDED_UNITS_CODES).

The input folder is never written. Everything is validated and serialised in memory before the
first document is written, so a bug never leaves an invalid document on disk.

Exit codes (AGENTS.md): 0 the run completed (even with blocking questions); 1 a supported-format
file (dwg, dxf) could not be read, or an output document failed its own schema; 2 usage; 3 environment
(no DWG converter while a DWG exists, or an input file cannot be read). Formats that have no reader yet
(pdf, image, docx, xlsx, other) are 'unreadable' with a blocking question but do NOT cause exit 1.
A malformed knowledge table (`knowledge/font-encodings.csv`) is exit 1 and nothing is written.
"""

from __future__ import annotations

import json
import shutil
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tekla_harness.convert import (
    DEFAULT_TIMEOUT_S,
    LIBREDWG_TOOL,
    ODA_TOOL,
    ConversionResult,
    dwg_to_dxf,
    resolve_converters,
)
from tekla_harness.detect import detect_file, iter_input_files
from tekla_harness.extract_text import extract_text
from tekla_harness.knowledge import FontEncodingTable, KnowledgeError, default_font_encodings
from tekla_harness.questions import (
    QuestionsError,
    dump_json,
    load_ledger,
    merged_question,
    question_group,
    questions_document,
    questions_per_file,
)
from tekla_harness.read_dxf import probe_dxf
from tekla_harness.readlog import Attempt, ReadLog, ReadLogError, timed_attempt
from tekla_harness.schemas import validate
from tekla_harness.worklock import work_lock

SCHEMA_VERSION = "0.1"
MAX_PROBE_REFS = 50  # refs listed per probe or text question group; the true total is always given
WORK_SUBFOLDERS = ("converted", "probe", "text")  # cleared on every run
EXIT_OK, EXIT_UNREADABLE, EXIT_USAGE, EXIT_ENV = 0, 1, 2, 3

_CONVERTER_NAME = {ODA_TOOL: "oda", LIBREDWG_TOOL: "libredwg"}
_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
# read-log.json has no undetermined 'pdf': log 'other' (never claim vector/scan/mixed before a
# PDF reader has looked) and say why in warnings; the inventory keeps 'pdf'.
_READ_LOG_FORMAT = {"pdf": "other"}
_READ_LOG_FORMAT_NOTE = {"pdf": "PDF type (vector, scan or mixed) not determined yet: logged as 'other'"}
_NO_READER_TOOL = "intake_no_reader"

UNITS_CONFIRM_ALL_MESSAGE = (
    "Header units are unreliable on real drawings and are not accepted automatically. Confirm the "
    "drawing unit of this DXF (against a known dimension, a PDF or your own knowledge) before any "
    "extraction: answer with --value unit=mm|cm|m|in|ft. This is the file's only blocking units question; "
    "the probe's units evidence (header unit vs measurement system, implausible dimensions, unknown unit) "
    "is listed in its refs. Replaces the non-blocking units_confirm probe question."
)
# probe units questions whose evidence is folded into the file's units_confirm_all refs (not asked apart)
FOLDED_UNITS_CODES = ("units_confirm", "units_conflict", "units_suspect", "units_unknown")
_MESSAGES = {
    "conversion_empty": (
        "The DWG converted to a DXF without any entity in any layout although the DWG is not tiny. "
        "Treat it as a failed parse unless you confirm the sheet is empty; otherwise provide a DXF or "
        "PDF export of this sheet."
    ),
    "converter_errors": (
        "The DWG converter printed ERROR lines although it exited normally: some objects or strings "
        "may be missing or truncated, and confidence is capped. Check the text-heavy parts of this "
        "sheet or provide a DXF or PDF export."
    ),
    "encoding_unknown_non_ascii": (
        "Text with non-ASCII characters was found in text styles whose font gives no encoding (not a known "
        "Unicode family or legacy Vietnamese font name, and no approved knowledge-table row). It is kept "
        "as stored with low confidence. Say which encoding each style uses (TCVN3, VNI or Unicode); an "
        "answer can become an approved row in knowledge/font-encodings.csv."
    ),
    "read_failed": (
        "This file could not be read by any supported route. Provide a DXF or PDF export of the sheet."
    ),
    "no_reader_implemented": (
        "No reader exists yet for these file formats (roadmap), so nothing was extracted from them. "
        "Provide a DXF or DWG of each listed sheet, or wait for the reader."
    ),
}


class IntakeError(Exception):
    """A run that cannot proceed; `exit_code` is the CLI exit code."""

    def __init__(self, exit_code: int, message: str) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass
class IntakeResult:
    exit_code: int
    summary: dict[str, Any]


@dataclass
class _Entry:
    rel: str
    info: dict[str, Any]
    attempts: list[Attempt] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    outcome: str = "unreadable"
    cap: str | None = None
    converter: str | None = None
    conversion: ConversionResult | None = None
    converted_rel: str | None = None
    probe: dict[str, Any] | None = None
    probe_rel: str | None = None
    probe_text: str | None = None
    text_rel: str | None = None
    text_text: str | None = None
    text_summary: dict[str, Any] | None = None
    unknown_by_style: dict[str, tuple[int, str | None]] = field(default_factory=dict)
    read_failure: str | None = None  # supported format that could not be read: why
    failure_stage: str = ""
    no_reader: bool = False

    @property
    def fmt(self) -> str:
        return self.info["kind"]

    @property
    def probed(self) -> bool:
        """A probe exists and ezdxf opened the DXF."""
        return self.probe is not None and self.probe["status"] != "unreadable"


def _inside(child: Path, parent: Path) -> bool:
    return child == parent or parent in child.parents


def _min_confidence(*caps: str | None) -> str | None:
    known = [c for c in caps if c]
    return min(known, key=_CONFIDENCE_RANK.__getitem__) if known else None


def _attempt_from_dict(data: dict[str, Any]) -> Attempt:
    return Attempt(
        tool=data["tool"],
        started_at=data["started_at"],
        status=data["status"],
        duration_ms=data.get("duration_ms", 0),
        error=data.get("error"),
        tool_version=data.get("tool_version"),
    )


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _check_paths(input_dir: Path, work_dir: Path) -> None:
    if not input_dir.is_dir():
        raise IntakeError(EXIT_USAGE, f"input folder not found: {input_dir}")
    if _inside(work_dir, input_dir):
        raise IntakeError(EXIT_USAGE, f"work folder {work_dir} is inside the input folder {input_dir}")
    if work_dir.exists() and not work_dir.is_dir():
        raise IntakeError(EXIT_USAGE, f"work folder {work_dir} exists and is not a folder")
    for name in WORK_SUBFOLDERS:
        if _inside(input_dir, work_dir / name):
            raise IntakeError(EXIT_USAGE, f"input folder {input_dir} is inside {work_dir / name}")


def _detect_all(input_dir: Path) -> list[_Entry]:
    entries = []
    for path in iter_input_files([input_dir]):
        try:
            info = detect_file(path)
        except OSError as exc:
            raise IntakeError(EXIT_ENV, f"cannot read input file {path}: {exc}") from exc
        entries.append(_Entry(path.relative_to(input_dir).as_posix(), info))
    entries.sort(key=lambda e: e.rel)
    return entries


def _converted_rel(rel: str) -> str:
    return (Path("converted") / rel).with_suffix(".dxf").as_posix()


def _text_summary(text: dict[str, Any]) -> dict[str, Any]:
    entries = text["entries"]
    return {
        "entries": len(entries),
        "by_encoding_used": dict(sorted(Counter(e["decode"]["encoding_used"] for e in entries).items())),
        "low_confidence": sum(1 for e in entries if e["confidence"] == "low"),
    }


def _unknown_by_style(text: dict[str, Any]) -> dict[str, tuple[int, str | None]]:
    out: dict[str, tuple[int, str | None]] = {}
    for e in text["entries"]:
        if "encoding_unknown_non_ascii" in e["flags"]:
            style = e["style"] if e["style"] is not None else "(no style)"
            out[style] = (out.get(style, (0, None))[0] + 1, e["font_file"])
    return dict(sorted(out.items()))


def _run_text(entry: _Entry, dxf: Path, converter: str, text_dir: Path, knowledge: FontEncodingTable) -> None:
    try:
        # provenance.file is relative to the project input folder (common.schema.json); for a DWG it is
        # the DWG itself (the converted DXF is not in the input folder)
        text = extract_text(dxf, converter=converter, knowledge=knowledge, source=entry.rel)
    except OSError as exc:
        raise IntakeError(EXIT_ENV, f"cannot read {dxf}: {exc}") from exc
    problems = validate("text-index", text)
    if problems:  # a bug in the extractor, not in the drawing
        details = "; ".join(f"{p.path or '/'}: {p.message}" for p in problems[:5])
        raise IntakeError(EXIT_UNREADABLE, f"text index for {entry.rel} is invalid: {details}")
    try:
        entry.text_text = _utf8(dump_json(text), f"text index for {entry.rel}")
    except ValueError as exc:
        raise IntakeError(
            EXIT_UNREADABLE, f"text index for {entry.rel} has a non-finite number: {exc}"
        ) from exc
    entry.text_rel = (Path(text_dir.name) / f"{entry.rel}.json").as_posix()
    entry.warnings += text.get("warnings", [])
    if text["status"] == "unreadable":  # the probe opened the file, so this is not expected
        entry.warnings.append(f"text index could not be computed: {text['error']}")
        entry.outcome = "partial"
        return
    entry.text_summary = _text_summary(text)
    entry.unknown_by_style = _unknown_by_style(text)
    if text["status"] == "partial":
        entry.warnings.append(
            f"text index status partial: {text['summary']['errors_total']} entity error(s), "
            "see summary.errors in the text index"
        )
        entry.outcome = "partial"


def _run_probe(
    entry: _Entry,
    dxf: Path,
    converter: str,
    dirs: tuple[Path, Path],
    xref_dir: Path | None,
    knowledge: FontEncodingTable,
) -> None:
    probe_dir, text_dir = dirs
    try:
        probe = probe_dxf(dxf, converter=converter, xref_dir=xref_dir, knowledge=knowledge)
    except OSError as exc:
        raise IntakeError(EXIT_ENV, f"cannot read {dxf}: {exc}") from exc
    # the probe records the path it read; the work folder records files by their input-relative path,
    # so no output names the absolute input folder (provenance rule, common.schema.json)
    probe["file"]["path"] = entry.rel
    problems = validate("dxf-probe", probe)
    if problems:  # a bug in the probe, not in the drawing
        details = "; ".join(f"{p.path or '/'}: {p.message}" for p in problems[:5])
        raise IntakeError(EXIT_UNREADABLE, f"probe output for {entry.rel} is invalid: {details}")
    try:
        entry.probe_text = _utf8(dump_json(probe), f"probe output for {entry.rel}")
    except ValueError as exc:
        raise IntakeError(
            EXIT_UNREADABLE, f"probe output for {entry.rel} has a non-finite number: {exc}"
        ) from exc
    entry.probe, entry.probe_rel = probe, (Path(probe_dir.name) / f"{entry.rel}.json").as_posix()
    entry.attempts += [_attempt_from_dict(a) for a in probe["attempts"]]
    entry.warnings += probe.get("warnings", [])
    entry.converter = converter
    if probe["status"] == "unreadable":
        entry.read_failure, entry.failure_stage = probe["error"], "dxf open"
        return
    conv = entry.conversion
    conversion_partial = conv is not None and (
        any(a.status == "partial" for a in conv.attempts) or conv.stderr_error_lines > 0
    )
    if probe["status"] == "partial":
        sections = ", ".join(e["section"] for e in probe["section_errors"])
        entry.warnings.append(f"probe status partial: section(s) {sections} could not be computed")
    entry.outcome = "partial" if probe["status"] == "partial" or conversion_partial else "read"
    entry.cap = _min_confidence(probe["file"]["confidence_cap"], conv.confidence_cap if conv else None)
    _run_text(entry, dxf, converter, text_dir, knowledge)


def _process(
    entry: _Entry,
    input_dir: Path,
    work_dir: Path,
    oda: list[str] | None,
    dwg2dxf: list[str] | None,
    timeout: float,
    knowledge: FontEncodingTable,
) -> None:
    src = input_dir / entry.rel
    entry.warnings += entry.info["warnings"]
    dirs = (work_dir / "probe", work_dir / "text")
    if entry.fmt == "dxf":
        _run_probe(entry, src, "none", dirs, None, knowledge)
    elif entry.fmt == "dwg":
        out_dir = work_dir / "converted" / Path(entry.rel).parent
        try:
            conv = dwg_to_dxf(src, out_dir, oda=oda, dwg2dxf=dwg2dxf, timeout=timeout)
        except ValueError as exc:
            raise IntakeError(EXIT_USAGE, str(exc)) from exc
        entry.conversion = conv
        entry.attempts += conv.attempts
        entry.warnings += conv.warnings
        if conv.dxf is None or conv.converter is None:
            reasons = "; ".join(f"{a.tool}: {a.error}" for a in conv.attempts)
            entry.read_failure, entry.failure_stage = reasons, "dwg conversion"
            return
        entry.converted_rel = conv.dxf.resolve().relative_to(work_dir).as_posix()
        # the converted DXF sits in the work folder: its xrefs are looked up beside the original DWG
        _run_probe(entry, conv.dxf, _CONVERTER_NAME[conv.converter], dirs, src.parent, knowledge)
    else:
        message = f"no reader implemented for {entry.fmt} yet (roadmap)"
        with timed_attempt(_NO_READER_TOOL) as attempt:
            attempt.fail(message)
        entry.attempts.append(attempt)
        entry.no_reader = True


# --- documents ---------------------------------------------------------------------------------


def _units_of(entry: _Entry) -> dict[str, Any] | None:
    if not entry.probed or entry.probe is None:
        return None
    flags = sorted({q["code"] for q in entry.probe["questions"] if q["code"].startswith("units_")})
    units = entry.probe.get("units")
    if units is None:  # probe status partial and the units section failed
        return {
            "value": "unknown",
            "confidence": "low",
            "flags": sorted({*flags, "units_not_read"}),
            "dimension_median": None,
        }
    return {
        "value": units["value"],
        "confidence": units["confidence"],
        "flags": flags,
        "dimension_median": units["dimension_median"],
    }


def _inventory_row(entry: _Entry) -> dict[str, Any]:
    probe = entry.probe if entry.probed else None
    layouts = probe.get("layouts") if probe else None
    audit = probe.get("dimension_audit") if probe else None
    hints = probe.get("text_encoding_hints") if probe else None
    unreadable = probe.get("unreadable_objects") if probe else None
    conv = entry.conversion
    return {
        "path": entry.rel,
        "sha256": entry.info["sha256"],
        "format": entry.fmt,
        "dwg_version": entry.info.get("dwg_version"),
        "converter": entry.converter,
        "confidence_cap": entry.cap,
        "outcome": entry.outcome,
        "units": _units_of(entry),
        "layouts": None if layouts is None else [x["name"] for x in layouts],
        "modelspace_entity_total": None
        if layouts is None
        else sum(x["entity_total"] for x in layouts if x["is_model"]),
        "text_encoding_hints": None
        if hints is None
        else [{"style": h["style"], "encoding_hint": h["encoding_hint"]} for h in hints],
        "unreadable_objects": None
        if unreadable is None
        else [{"kind": u["kind"], "dxftype": u["dxftype"], "count": u["count"]} for u in unreadable],
        "dimension_override_differs": None
        if audit is None
        else audit["by_status"].get("override_differs", 0),
        "probe": entry.probe_rel,
        "text_index": entry.text_rel if entry.text_summary is not None else None,
        "text": entry.text_summary,
        "converted": entry.converted_rel if conv and conv.dxf else None,
        "conversion": None
        if not (conv and conv.dxf)
        else {
            "stderr_error_lines": conv.stderr_error_lines,
            "stderr_warning_lines": conv.stderr_warning_lines,
            "stderr_tail": conv.stderr_tail,
        },
    }


def _units_group(entries: list[_Entry]) -> list[dict[str, Any]]:
    """One blocking units_confirm_all per probed file: the header ref first, then one ref per folded probe
    units question (its where, found and message verbatim), so the count is the true number of refs."""
    out = []
    for e in entries:
        units = _units_of(e)
        if units is None:
            continue
        code = e.probe["units"]["header_code"] if e.probe and "units" in e.probe else None
        flags = ", ".join(units["flags"]) or "none"
        refs: list[dict[str, Any]] = [
            {
                "file": e.rel,
                "where": "header $INSUNITS",
                "found": f"{units['value']} ($INSUNITS={code}), "
                f"confidence {units['confidence']}, flags: {flags}",
                "unit": units["value"],
                "confidence": units["confidence"],
                "flags": units["flags"],
            }
        ]
        for q in (e.probe or {}).get("questions", []):
            if q["code"] in FOLDED_UNITS_CODES and q["code"] != "units_confirm":
                refs.append(
                    {
                        "file": e.rel,
                        "where": q["where"],
                        "found": q["found"],
                        "message": f"{q['code']}: {q['message']}",
                    }
                )
        out.append(question_group("units_confirm_all", True, UNITS_CONFIRM_ALL_MESSAGE, refs, file=e.rel))
    return out


def _probe_groups(entries: list[_Entry]) -> list[dict[str, Any]]:
    groups: dict[tuple[bool, str, str], list[tuple[str, dict[str, Any]]]] = {}
    for e in entries:
        if not (e.probed and e.probe):
            continue
        for q in e.probe["questions"]:
            if q["code"] in FOLDED_UNITS_CODES:  # folded into the file's units_confirm_all
                continue
            ref = {"file": e.rel, "where": q["where"], "found": q["found"]}
            groups.setdefault((not q["blocking"], q["code"], e.rel), []).append((q["message"], ref))
    return [
        merged_question(code, not non_blocking, rel, items, MAX_PROBE_REFS)
        for (non_blocking, code, rel), items in sorted(groups.items())
    ]


def _text_groups(entries: list[_Entry]) -> list[dict[str, Any]]:
    refs = []
    for e in entries:
        for style, (count, font) in e.unknown_by_style.items():
            noun = "entry" if count == 1 else "entries"
            refs.append(
                {
                    "file": e.rel,
                    "where": f"text style {style}",
                    "found": f"{count} {noun} with non-ASCII text and no known encoding "
                    f"(font file {font or 'none'})",
                }
            )
    message = _MESSAGES["encoding_unknown_non_ascii"]
    return questions_per_file("encoding_unknown_non_ascii", False, message, refs, MAX_PROBE_REFS)


def _conversion_groups(entries: list[_Entry]) -> list[dict[str, Any]]:
    empty, errors = [], []
    for e in entries:
        conv = e.conversion
        if conv is None or conv.dxf is None:
            continue
        for a in conv.attempts:
            if a.status == "partial":
                empty.append({"file": e.rel, "where": "dwg conversion", "found": f"{a.tool}: {a.error}"})
        if conv.stderr_error_lines > 0:
            found = f"{conv.stderr_error_lines} ERROR line(s), {conv.stderr_warning_lines} warning line(s)"
            errors.append({"file": e.rel, "where": "dwg conversion", "found": found})
    return questions_per_file("conversion_empty", True, _MESSAGES["conversion_empty"], empty) + (
        questions_per_file("converter_errors", False, _MESSAGES["converter_errors"], errors)
    )


def _failure_groups(entries: list[_Entry]) -> list[dict[str, Any]]:
    failed = [
        {"file": e.rel, "where": e.failure_stage, "found": e.read_failure or ""}
        for e in entries
        if e.read_failure is not None
    ]
    no_reader = [
        {
            "file": e.rel,
            "where": f"format {e.fmt}",
            "found": f"no reader implemented for {e.fmt} yet (roadmap)",
        }
        for e in entries
        if e.no_reader
    ]
    return questions_per_file("read_failed", True, _MESSAGES["read_failed"], failed) + questions_per_file(
        "no_reader_implemented", True, _MESSAGES["no_reader_implemented"], no_reader
    )


def _questions(entries: list[_Entry]) -> list[dict[str, Any]]:
    """Raw questions (no id, key or answer yet), one per code, blocking flag and file, in document order."""
    groups = _units_group(entries) + _probe_groups(entries) + _text_groups(entries)
    return groups + _conversion_groups(entries) + _failure_groups(entries)


def _read_log(project_id: str, entries: list[_Entry]) -> ReadLog:
    log = ReadLog(project_id)
    for e in entries:
        log.add_file(
            e.rel,
            e.info["sha256"],
            _READ_LOG_FORMAT.get(e.fmt, e.fmt),
            e.attempts,
            e.outcome,
            max_confidence=e.cap,
            warnings=_dedupe([*e.warnings, *filter(None, [_READ_LOG_FORMAT_NOTE.get(e.fmt)])]),
        )
    return log


def _utf8(text: str, label: str) -> str:
    """`text` if it can be written as UTF-8 (checked now, so nothing is half written later)."""
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise IntakeError(
            EXIT_UNREADABLE, f"{label} cannot be written as UTF-8, nothing written: {exc}"
        ) from exc
    return text


def _previous_hashes(work_dir: Path) -> dict[str, str] | None:
    """path -> sha256 of the previous inventory.json of this work folder; None when there is none.

    Only the file list is read, so an inventory written by an older version still serves. An inventory that
    exists but cannot be read is an error: the diff must never be silently skipped."""
    path = work_dir / "inventory.json"
    if not path.is_file():
        return None
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))["files"]
        return {r["path"]: r["sha256"] for r in rows}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise IntakeError(
            EXIT_UNREADABLE,
            f"the previous {path} cannot be read ({exc}): it is needed to find changed input files; "
            "move it away to start this work folder over",
        ) from exc


def _diff_inputs(previous: dict[str, str] | None, current: dict[str, str]) -> dict[str, Any]:
    if previous is None:
        return {"added": [], "removed": [], "changed": []}
    return {
        "added": sorted(set(current) - set(previous)),
        "removed": sorted(set(previous) - set(current)),
        "changed": sorted(p for p in current.keys() & previous.keys() if current[p] != previous[p]),
    }


def _check(name: str, data: Any, label: str) -> None:
    problems = validate(name, data)
    if problems:
        details = "; ".join(f"{p.path or '/'}: {p.message}" for p in problems[:5])
        raise IntakeError(EXIT_UNREADABLE, f"{label} is invalid, nothing written: {details}")


# --- entry point -------------------------------------------------------------------------------


def run_intake(
    input_dir: Path,
    work_dir: Path,
    project_id: str,
    oda: list[str] | None = None,
    dwg2dxf: list[str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
    knowledge: FontEncodingTable | None = None,
) -> IntakeResult:
    """Run the whole intake. Raises IntakeError for exit codes 2 and 3 (and 1 for a self-check failure
    or a malformed knowledge table). `knowledge`: font-encoding table, default the shipped one."""
    input_dir, work_dir = Path(input_dir).resolve(), Path(work_dir).resolve()
    if validate("read-log", {"schema_version": SCHEMA_VERSION, "project_id": project_id, "files": []}):
        raise IntakeError(
            EXIT_USAGE, f"invalid project id '{project_id}': use a-z, 0-9 and '-', 2 to 64 chars"
        )
    _check_paths(input_dir, work_dir)
    try:
        table = knowledge if knowledge is not None else default_font_encodings()
    except KnowledgeError as exc:
        raise IntakeError(EXIT_UNREADABLE, str(exc)) from exc
    entries = _detect_all(input_dir)
    if not entries:
        raise IntakeError(EXIT_USAGE, f"input folder {input_dir} has no files")
    targets: dict[str, str] = {}
    for e in entries:
        if e.fmt == "dwg":
            other = targets.setdefault(_converted_rel(e.rel).lower(), e.rel)
            if other != e.rel:
                raise IntakeError(EXIT_USAGE, f"{other} and {e.rel} would both convert to the same DXF")
    if targets and not resolve_converters(oda, dwg2dxf):
        raise IntakeError(
            EXIT_ENV,
            "input contains DWG files but no DWG converter is configured: pass --oda / --dwg2dxf, set "
            "HARNESS_ODA_CONVERTER / HARNESS_DWG2DXF, or put ODAFileConverter / dwg2dxf on PATH",
        )
    try:
        work_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise IntakeError(EXIT_ENV, f"cannot create the work folder {work_dir}: {exc}") from exc
    # One writer per work folder (ADR-0011): everything below reads or writes the work folder's state.
    with work_lock(work_dir, "intake"):
        return _intake_locked(input_dir, work_dir, project_id, entries, oda, dwg2dxf, timeout, table)


def _intake_locked(
    input_dir: Path,
    work_dir: Path,
    project_id: str,
    entries: list[_Entry],
    oda: list[str] | None,
    dwg2dxf: list[str] | None,
    timeout: float,
    table: FontEncodingTable,
) -> IntakeResult:
    """run_intake after its usage checks, under the work-folder lock."""
    try:
        ledger = load_ledger(work_dir, project_id, create=True)
    except QuestionsError as exc:
        raise IntakeError(exc.exit_code, str(exc)) from exc
    hashes = {e.rel: e.info["sha256"] for e in entries}
    changes = _diff_inputs(_previous_hashes(work_dir), hashes)

    for name in WORK_SUBFOLDERS:  # rerun into the same folder: no stale files
        shutil.rmtree(work_dir / name, ignore_errors=True)
    for e in entries:
        _process(e, input_dir, work_dir, oda, dwg2dxf, timeout, table)

    gone = {**dict.fromkeys(changes["removed"], "removed"), **dict.fromkeys(changes["changed"], "changed")}
    try:
        questions = ledger.sync("intake", _questions(entries), hashes, gone)
    except QuestionsError as exc:
        raise IntakeError(exc.exit_code, str(exc)) from exc
    rows = [_inventory_row(e) for e in entries]
    summary = {
        "files": len(entries),
        "by_format": dict(sorted(Counter(r["format"] for r in rows).items())),
        "by_outcome": dict(sorted(Counter(r["outcome"] for r in rows).items())),
        "questions": len(questions),
        "blocking_questions": sum(1 for q in questions if q["blocking"]),
        "changes": changes,
        "stale_answers": ledger.stale_answers(),
    }
    inventory = {
        "schema_version": SCHEMA_VERSION,
        "kind": "inventory",
        "project_id": project_id,
        "files": rows,
        "summary": summary,
    }
    questions_doc = questions_document(project_id, questions)
    _check("intake", inventory, "inventory.json")
    _check("intake", questions_doc, "questions.json")
    try:
        log = _read_log(project_id, entries)
    except ReadLogError as exc:
        raise IntakeError(EXIT_UNREADABLE, f"read-log.json is incomplete, nothing written: {exc}") from exc
    _check("read-log", log.as_dict(), "read-log.json")
    inventory_text = _utf8(dump_json(inventory), "inventory.json")
    questions_text = _utf8(dump_json(questions_doc), "questions.json")

    try:
        ledger.write()  # the registry is written before any document that uses its ids
    except OSError as exc:
        raise IntakeError(EXIT_ENV, f"cannot write into {work_dir}: {exc}") from exc
    for e in entries:
        if e.probe_rel and e.probe_text:
            target = work_dir / e.probe_rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(e.probe_text, encoding="utf-8")
        if e.text_rel and e.text_text:
            target = work_dir / e.text_rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(e.text_text, encoding="utf-8")
    try:
        log.write(work_dir / "read-log.json")
    except ReadLogError as exc:  # unreachable after the check above; kept so a bug is never silent
        raise IntakeError(EXIT_UNREADABLE, str(exc)) from exc
    (work_dir / "inventory.json").write_text(inventory_text, encoding="utf-8")
    (work_dir / "questions.json").write_text(questions_text, encoding="utf-8")

    failures = [e.rel for e in entries if e.read_failure is not None]
    result_summary = {
        "project_id": project_id,
        **summary,
        "answered": questions_doc["summary"]["answered"],
        "blocking_open": questions_doc["summary"]["blocking_open"],
        "stale_answers": ledger.stale_answers(),
        "read_failures": failures,
        "outputs": {
            "read_log": str(work_dir / "read-log.json"),
            "inventory": str(work_dir / "inventory.json"),
            "questions": str(work_dir / "questions.json"),
            "registry": str(work_dir / "question-registry.json"),
            "answers": str(work_dir / "answers.json"),
            "probe_dir": str(work_dir / "probe"),
            "text_dir": str(work_dir / "text"),
            "converted_dir": str(work_dir / "converted"),
        },
    }
    return IntakeResult(EXIT_UNREADABLE if failures else EXIT_OK, result_summary)
