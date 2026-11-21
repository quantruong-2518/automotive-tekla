"""structure: command-line wiring of the structural extractors (sheets, grids, levels).

Single file (`harness extract-sheets | extract-grids | extract-levels`): a DXF, the text index built
from that very DXF, and for grids and levels the sheets document built from it. The full result goes to
`--out`; stdout is a small summary. Inputs are checked (schema, sha256) and the output is validated
before anything is written.

Whole work folder (`harness read-structure <work_dir>`): runs sheets -> grids -> levels over every DXF that
`harness intake` probed, with the text index intake already wrote. Reads `inventory.json`,
`questions.json` and `question-registry.json` (owned by intake; the registry is updated, the others never
modified) and writes:

    structure/<path>.sheets.json | .grids.json | .levels.json   one set per processed file
    structure-questions.json   the questions, one per (code, file), with stable key, registry id and answer
                               (intake schema, kind 'questions'; see questions.py)
    structure-summary.json     per-file overview (intake schema, kind 'structure_summary')

Native DXF files stay in the intake input folder and every work-folder document records them by their
input-relative path only (provenance rule, common.schema.json), so `--input-dir <input_dir>` is required
when the inventory lists one (exit 2 without it); a text index written before that rule (absolute
`file.path`) is still found. Consolidated `count` values are the true totals, also for questions an
extractor counted but did not list (its per-code cap, `question_counts`).

Question ids come from the shared registry (questions.py): a question keeps its id on every rerun, new
questions get the next free ids (after those of intake and callouts), and a question this command no longer
raises becomes obsolete (its id is never reused). An existing answer (answers.json) is shown in the
question. Intake does not clear the structure files when it reruns: `structure-summary.json` records the
sha256 of the inventory it was built from, and read-structure must be rerun after every intake.

A file is skipped (logged on stderr and in the summary) when it has nothing to read: not a DXF/DWG, the
DWG did not convert, the DXF did not open, or no text index exists. A work folder that disagrees with
itself (a DXF changed since intake, a missing or invalid text index, a path leaving the work folder) is
exit 1 and NOTHING is written; every such problem is listed.

Exit codes (AGENTS.md): 0 ok, 1 validation failure or inconsistent inputs, 2 usage, 3 environment.
Nothing in the outputs is a timestamp or duration: the same work folder gives byte-identical files.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ezdxf.document import Drawing

from tekla_harness.detect import sha256_file
from tekla_harness.grids import extract_grids, question_families
from tekla_harness.levels import extract_levels
from tekla_harness.questions import (
    QuestionsError,
    dump_json,
    load_ledger,
    merged_question,
    questions_document,
)
from tekla_harness.schemas import validate
from tekla_harness.sheets import extract_sheets, min_conf, open_checked

SCHEMA_VERSION = "0.1"
MAX_STRUCTURE_REFS = 50  # refs listed per consolidated question; `count` is always the true total
MAX_FAMILIES_LISTED = 100  # grid families listed per file in a summary; the true total is always given
MAX_LEVELS_LISTED = 100  # levels listed per file in a summary; the true total is always given
STRUCTURE_DIR = "structure"
EXIT_OK, EXIT_INVALID, EXIT_USAGE, EXIT_ENV = 0, 1, 2, 3

_KINDS = ("sheets", "grids", "levels")
_CONFIDENCES = ("high", "medium", "low")
_DWG_NOT_CONVERTED = "no DXF was produced from this file (conversion failed; see read-log.json)"


class StructureError(Exception):
    """A run that cannot proceed; `exit_code` is the CLI exit code."""

    def __init__(self, exit_code: int, message: str) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass
class StructureResult:
    exit_code: int
    summary: dict[str, Any]


# --- reading and checking documents -------------------------------------------------------------


def _read_json(path: Path, label: str) -> Any:
    if not path.is_file():
        raise StructureError(EXIT_USAGE, f"{label} is not a file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise StructureError(EXIT_ENV, f"cannot read {label} {path}: {exc}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise StructureError(EXIT_INVALID, f"{label} {path} is not valid JSON: {exc}") from exc


def _details(problems: list[Any]) -> str:
    return "; ".join(f"{p.path or '/'}: {p.message}" for p in problems[:5])


def _load_checked(path: Path, schema: str, label: str) -> Any:
    data = _read_json(path, label)
    problems = validate(schema, data)
    if problems:
        raise StructureError(
            EXIT_INVALID, f"{label} {path} is invalid ({schema} schema): {_details(problems)}"
        )
    return data


def _load_text_index(path: Path) -> dict[str, Any]:
    data = _load_checked(path, "text-index", "text index")
    if data["status"] == "unreadable":
        raise StructureError(
            EXIT_INVALID, f"text index {path} is unreadable: {data.get('error', 'no reason given')}"
        )
    return data


def _load_sheets(path: Path, text_index: dict[str, Any]) -> dict[str, Any]:
    data = _load_checked(path, "sheets", "sheets document")
    if data["file"]["sha256"] != text_index["file"]["sha256"]:
        raise StructureError(
            EXIT_INVALID,
            f"sheets document {path} was built from another file (sha256 {data['file']['sha256']}, the text "
            f"index has {text_index['file']['sha256']}): rerun extract-sheets on this DXF",
        )
    return data


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise StructureError(EXIT_USAGE, f"not a file: {path}")


def _output_text(name: str, data: dict[str, Any], label: str) -> str:
    """Validated, strict-JSON, UTF-8 encodable text of an extractor result (a failure is a bug, exit 1)."""
    problems = validate(name, data)
    if problems:  # a bug in the extractor, not in the drawing: never write an invalid document
        raise StructureError(EXIT_INVALID, f"{label} output is invalid ({name} schema): {_details(problems)}")
    try:
        text = dump_json(data)
        text.encode("utf-8")
    except (ValueError, UnicodeEncodeError) as exc:
        raise StructureError(EXIT_INVALID, f"{label} output cannot be written as strict JSON: {exc}") from exc
    return text


# --- per-document overviews ---------------------------------------------------------------------


def true_counts(doc: dict[str, Any]) -> Counter[str]:
    """Questions per code, counting those the extractor did not list (grids and levels cap their list per
    code and give the true numbers in `question_counts`)."""
    counts = Counter(q["code"] for q in doc["questions"])
    for code, n in doc.get("question_counts", {}).items():
        counts[code] = max(counts[code], n)
    return counts


def _question_counts(doc: dict[str, Any]) -> dict[str, int]:
    """Total and blocking questions, counting unlisted ones (a capped code has one blocking value)."""
    qs = doc["questions"]
    listed = Counter(q["code"] for q in qs)
    blocking_codes = {q["code"] for q in qs if q["blocking"]}
    extra = {c: n - listed[c] for c, n in doc.get("question_counts", {}).items() if n > listed[c]}
    return {
        "total": len(qs) + sum(extra.values()),
        "blocking": sum(1 for q in qs if q["blocking"])
        + sum(n for c, n in extra.items() if c in blocking_codes),
    }


def sheets_overview(doc: dict[str, Any]) -> dict[str, Any]:
    numbers = [s["title_block"]["sheet_number"] for s in doc["sheets"]]
    found = [n for n in numbers if n is not None]
    by_conf = Counter(n["confidence"] for n in found)
    return {
        "count": len(doc["sheets"]),
        "by_method": dict(sorted(doc["summary"]["by_method"].items())),
        "sheet_numbers": {
            "found": len(found),
            "missing": len(numbers) - len(found),
            "by_confidence": {c: by_conf[c] for c in _CONFIDENCES if by_conf[c]},
        },
    }


def _family_overview(group: dict[str, Any], fam: dict[str, Any]) -> dict[str, Any]:
    proposal = fam["proposal"]  # null for a family of one axis: no spacing, no coordinate string
    confidences = [a["confidence"] for a in fam["axes"]] + [s["value"]["confidence"] for s in fam["spacings"]]
    labels = (
        proposal["labels"]
        if proposal
        else " ".join((a["label"] or {}).get("value", "?") for a in fam["axes"])
    )
    return {
        "sheet": group["sheet"],
        "group_id": group["group_id"],
        "family_id": fam["family_id"],
        "axes": len(fam["axes"]),
        "labels": labels,
        "coordinates": proposal["coordinates"] if proposal else None,
        "unit": proposal["unit"] if proposal else None,
        "confidence": min_conf(*confidences),  # the lowest of its axes and spacings
        "complete": proposal["complete"] if proposal else None,
    }


def grids_overview(doc: dict[str, Any]) -> dict[str, Any]:
    families = [_family_overview(g, f) for g in doc["groups"] for f in g["families"]]
    return {
        "groups": len(doc["groups"]),
        "families_total": len(families),
        "families": families[:MAX_FAMILIES_LISTED],
        "families_truncated": len(families) > MAX_FAMILIES_LISTED,
    }


def levels_overview(doc: dict[str, Any]) -> dict[str, Any]:
    levels = [
        {
            "value": lv["value"],
            "value_text": lv["value_text"],
            "count": len(lv["candidate_ids"]),
            "confidence": lv["confidence"],
        }
        for lv in doc["levels"]
    ]
    return {
        "candidates": len(doc["candidates"]),
        "levels_total": len(levels),
        "levels": levels[:MAX_LEVELS_LISTED],
        "levels_truncated": len(levels) > MAX_LEVELS_LISTED,
    }


_OVERVIEW = {"sheets": sheets_overview, "grids": grids_overview, "levels": levels_overview}


# --- single-file commands -----------------------------------------------------------------------


def _write_out(out: Path, text: str) -> None:
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise StructureError(EXIT_ENV, f"cannot write {out}: {exc}") from exc


def run_extractor(kind: str, dxf: Path, text_index_path: Path, out: Path, sheets_path: Path | None) -> dict:
    """One extractor over one DXF; returns the small stdout summary. Raises StructureError."""
    _require_file(dxf)
    text_index = _load_text_index(text_index_path)
    sheets = _load_sheets(sheets_path, text_index) if sheets_path is not None else None
    try:
        doc = open_checked(dxf, text_index)
        if kind == "sheets":
            result = extract_sheets(dxf, text_index, doc=doc)
        elif sheets is None:  # the CLI makes --sheets required for the other two
            raise StructureError(EXIT_USAGE, f"extract-{kind} needs a sheets document")
        elif kind == "grids":
            result = extract_grids(dxf, text_index, sheets, doc=doc)
        else:
            result = extract_levels(dxf, text_index, sheets, doc=doc)
    except OSError as exc:
        raise StructureError(EXIT_ENV, f"cannot read {dxf}: {exc}") from exc
    except ValueError as exc:
        raise StructureError(EXIT_INVALID, f"extract-{kind}: {exc}") from exc
    _write_out(out, _output_text(kind, result, f"extract-{kind}"))
    return {
        "file": str(dxf),
        "out": str(out),
        kind: _OVERVIEW[kind](result),
        "questions": _question_counts(result),
        "warnings": result["warnings"],
    }


# --- read-structure ------------------------------------------------------------------------------


@dataclass
class _Row:
    rel: str
    sha256: str
    row: dict[str, Any]
    skip: str | None = None
    dxf: Path | None = None
    text_index: dict[str, Any] | None = None


def _inside_work(work: Path, rel: str, what: str, problems: list[str]) -> Path | None:
    path = (work / rel).resolve()
    if path != work and work not in path.parents:
        problems.append(f"{what} '{rel}' is outside the work folder")
        return None
    return path


def _plan(work: Path, row: dict[str, Any], problems: list[str], input_dir: Path | None = None) -> _Row:
    """Decide what to do with one inventory row. Consistency problems are appended to `problems`."""
    rel = row["path"]
    plan = _Row(rel, row["sha256"], row)
    if row["format"] not in ("dwg", "dxf"):
        plan.skip = f"no reader implemented for format {row['format']} yet (roadmap)"
        return plan
    if row["probe"] is None:
        plan.skip = _DWG_NOT_CONVERTED if row["format"] == "dwg" else "no probe was written for this file"
        return plan
    probe_path = _inside_work(work, row["probe"], f"{rel}: probe", problems)
    if probe_path is None:
        return plan
    if not probe_path.is_file():
        problems.append(f"{rel}: probe {row['probe']} is missing")
        return plan
    try:
        probe = json.loads(probe_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        problems.append(f"{rel}: probe {row['probe']} cannot be read: {exc}")
        return plan
    if probe.get("status") == "unreadable":
        plan.skip = f"ezdxf could not open the DXF: {probe.get('error', 'no reason given')}"
        return plan
    if row["text_index"] is None:
        plan.skip = "no text index was computed for this file (see warnings in read-log.json)"
        return plan
    ti_path = _inside_work(work, row["text_index"], f"{rel}: text index", problems)
    if ti_path is None:
        return plan
    if not ti_path.is_file():
        problems.append(f"{rel}: text index {row['text_index']} is missing")
        return plan
    try:
        plan.text_index = _load_text_index(ti_path)
    except StructureError as exc:
        problems.append(f"{rel}: {exc}")
        return plan
    if row["format"] == "dwg":
        if row["converted"] is None:
            problems.append(f"{rel}: inventory has a probe but no converted DXF")
            return plan
        dxf = _inside_work(work, row["converted"], f"{rel}: converted DXF", problems)
    else:  # a native DXF stays in the input folder; the text index records it input-relative
        recorded = Path(plan.text_index["file"]["path"])
        if input_dir is not None:
            dxf = input_dir / rel
        elif recorded.is_absolute():  # a work folder from before input-relative paths
            dxf = recorded
        else:
            problems.append(
                f"{rel}: a native DXF is read from the intake input folder: pass --input-dir <input_dir>"
            )
            return plan
    if dxf is None:
        return plan
    if not dxf.is_file():
        where = "converted DXF" if row["format"] == "dwg" else "DXF (the input folder moved or was deleted?)"
        problems.append(f"{rel}: {where} not found: {dxf}")
        return plan
    digest = sha256_file(dxf)
    if digest != plan.text_index["file"]["sha256"]:
        problems.append(
            f"{rel}: the DXF {dxf} has sha256 {digest} but the text index was built from "
            f"{plan.text_index['file']['sha256']}: the file changed after intake, rerun harness intake"
        )
        return plan
    plan.dxf = dxf
    return plan


Cited = list[tuple[dict[str, Any], list[str] | None]]  # extractor questions with the grid families each cites


def _cited(docs: dict[str, dict[str, Any]]) -> Cited:
    """Every question of one file's sheets, grids and levels documents, with the grid families it cites
    (grids.question_families; None for sheets and levels questions and grid questions about no family)."""
    return [
        (q, question_families(q, docs["grids"]) if k == "grids" else None)
        for k in _KINDS
        for q in docs[k]["questions"]
    ]


def _families(refs: list[dict[str, Any]], dropped: list[list[str] | None], unknown: bool) -> None:
    """Set `families` on the listed refs so that their union is the question's TRUE family list (lifecycle
    closes a question only when every ref carries families): the last listed ref also takes the families of
    the refs the cap did not list. When some are unknown (a ref the cap dropped cites no family, or the
    extractor counted questions it did not list) no ref carries families."""
    if unknown or any(f is None for f in dropped):
        for ref in refs:
            ref.pop("families", None)
        return
    if dropped and refs and "families" in refs[-1]:
        refs[-1]["families"] = sorted({*refs[-1]["families"], *(f for fams in dropped if fams for f in fams)})


def _consolidate(per_file: list[tuple[str, Cited, Counter[str]]]) -> list[dict[str, Any]]:
    """Group extractor questions by (blocking, code, file), over sheets, grids and levels of one file.

    `count` is the true total: questions an extractor counted but did not list (per-code cap, see
    `true_counts`) are added to the question of their code and file (a code has one blocking value per
    extractor). A grid ref names the grid `families` it cites (not part of the key; see _families for refs
    the cap does not list). Raw questions (no id, key or answer yet), blocking first, then by code, then by
    file."""
    groups: dict[tuple[bool, str, str], list[tuple[str, dict[str, Any]]]] = {}
    cited: dict[tuple[bool, str, str], list[list[str] | None]] = {}
    unlisted: Counter[tuple[bool, str, str]] = Counter()
    for rel, questions, totals in per_file:
        listed_by_code: Counter[str] = Counter()
        key_of: dict[str, tuple[bool, str, str]] = {}
        for q, families in questions:
            ref: dict[str, Any] = {"file": rel}
            if "sheet" in q:
                ref["sheet"] = q["sheet"]
            ref.update(where=q["where"], found=q["found"])
            if families:
                ref["families"] = families
            key = (not q["blocking"], q["code"], rel)
            groups.setdefault(key, []).append((q["message"], ref))
            cited.setdefault(key, []).append(families)
            listed_by_code[q["code"]] += 1
            key_of.setdefault(q["code"], key)
        for code, n in totals.items():
            if n > listed_by_code[code] and code in key_of:
                unlisted[key_of[code]] += n - listed_by_code[code]
    out = []
    for key, items in sorted(groups.items()):
        non_blocking, code, rel = key
        question = merged_question(code, not non_blocking, rel, items, MAX_STRUCTURE_REFS, unlisted[key])
        _families(question["refs"], cited[key][len(question["refs"]) :], unlisted[key] > 0)
        out.append(question)
    return out


def _file_row(plan: _Row) -> dict[str, Any]:
    base: dict[str, Any] = {"path": plan.rel, "sha256": plan.sha256}
    if plan.skip is not None:
        return {
            **base,
            "status": "skipped",
            "reason": plan.skip,
            "outputs": None,
            "sheets": None,
            "grids": None,
            "levels": None,
            "questions": None,
            "warnings": [],
        }
    return {**base, "status": "processed", "reason": None}


def read_structure(work_dir: Path, input_dir: Path | None = None) -> StructureResult:
    """Run sheets, grids and levels over every probed DXF of an intake work folder. Raises StructureError.

    `input_dir`: the folder intake read; needed when the inventory lists native DXF files (they are read
    in place and recorded by their input-relative path only)."""
    work = Path(work_dir).resolve()
    if not work.is_dir():
        raise StructureError(EXIT_USAGE, f"work folder not found (not a folder): {work_dir}")
    if input_dir is not None:
        input_dir = Path(input_dir).resolve()
        if not input_dir.is_dir():
            raise StructureError(EXIT_USAGE, f"input folder not found (not a folder): {input_dir}")
    for name in ("inventory.json", "questions.json", "question-registry.json"):
        if not (work / name).is_file():
            raise StructureError(
                EXIT_USAGE, f"{work} has no {name}: run `harness intake <input_dir> --out {work_dir}` first"
            )
    inventory_bytes = (work / "inventory.json").read_bytes()
    inventory = _load_checked(work / "inventory.json", "intake", "inventory.json")
    questions_doc = _load_checked(work / "questions.json", "intake", "questions.json")
    if inventory["kind"] != "inventory" or questions_doc["kind"] != "questions":
        raise StructureError(EXIT_INVALID, "inventory.json or questions.json has the wrong 'kind'")
    try:
        ledger = load_ledger(work, inventory["project_id"], create=False)
    except QuestionsError as exc:
        raise StructureError(exc.exit_code, str(exc)) from exc

    problems: list[str] = []
    plans = [
        _plan(work, row, problems, input_dir) for row in sorted(inventory["files"], key=lambda r: r["path"])
    ]
    missing_input = [p for p in problems if p.endswith("--input-dir <input_dir>")]
    if missing_input:
        raise StructureError(EXIT_USAGE, "\n".join(missing_input))
    if problems:
        raise StructureError(
            EXIT_INVALID,
            "the work folder is inconsistent, nothing was written:\n  " + "\n  ".join(problems),
        )

    rows: list[dict[str, Any]] = []
    texts: dict[str, str] = {}
    per_file_questions: list[tuple[str, Cited, Counter[str]]] = []
    for plan in plans:
        row = _file_row(plan)
        rows.append(row)
        if plan.skip is not None or plan.dxf is None or plan.text_index is None:
            continue
        docs = _extract_all(plan.dxf, plan.text_index, plan.rel, texts)
        outputs = {k: f"{STRUCTURE_DIR}/{plan.rel}.{k}.json" for k in _KINDS}
        totals: Counter[str] = Counter()
        for k in _KINDS:
            totals.update(true_counts(docs[k]))
        per_file_questions.append((plan.rel, _cited(docs), totals))
        per_kind = {k: _question_counts(docs[k]) for k in _KINDS}
        counts = {k: per_kind[k]["total"] for k in _KINDS}
        counts["total"] = sum(counts.values())
        counts["blocking"] = sum(per_kind[k]["blocking"] for k in _KINDS)
        row.update(
            outputs=outputs,
            sheets=sheets_overview(docs["sheets"]),
            grids=grids_overview(docs["grids"]),
            levels=levels_overview(docs["levels"]),
            questions=counts,
            warnings=[f"{k}: {w}" for k in _KINDS for w in docs[k]["warnings"]],
        )

    hashes = {r["path"]: r["sha256"] for r in inventory["files"]}
    try:
        questions = ledger.sync("structure", _consolidate(per_file_questions), hashes)
    except QuestionsError as exc:
        raise StructureError(exc.exit_code, str(exc)) from exc
    project_id = inventory["project_id"]
    processed = sum(1 for r in rows if r["status"] == "processed")
    summary_doc = {
        "schema_version": SCHEMA_VERSION,
        "kind": "structure_summary",
        "project_id": project_id,
        "inventory_sha256": hashlib.sha256(inventory_bytes).hexdigest(),
        "files": rows,
        "summary": {
            "files": len(rows),
            "processed": processed,
            "skipped": len(rows) - processed,
            "questions": len(questions),
            "blocking_questions": sum(1 for q in questions if q["blocking"]),
        },
    }
    questions_out = questions_document(project_id, questions)
    out_texts = {}
    for name, doc in (("structure-questions.json", questions_out), ("structure-summary.json", summary_doc)):
        issues = validate("intake", doc)
        if issues:
            raise StructureError(EXIT_INVALID, f"{name} is invalid, nothing written: {_details(issues)}")
        try:
            out_texts[name] = dump_json(doc)
            out_texts[name].encode("utf-8")
        except (ValueError, UnicodeEncodeError) as exc:
            raise StructureError(EXIT_INVALID, f"{name} cannot be written as strict JSON: {exc}") from exc

    try:
        ledger.write()  # the registry is written before any document that uses its ids
        shutil.rmtree(work / STRUCTURE_DIR, ignore_errors=True)  # rerun: no stale files
        for rel, text in texts.items():
            target = work / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        for name, text in out_texts.items():
            (work / name).write_text(text, encoding="utf-8")
    except OSError as exc:
        raise StructureError(EXIT_ENV, f"cannot write into {work}: {exc}") from exc

    result = {
        "project_id": project_id,
        **summary_doc["summary"],
        "answered": questions_out["summary"]["answered"],
        "blocking_open": questions_out["summary"]["blocking_open"],
        "stale_answers": ledger.stale_answers(),
        "skipped_files": [
            {"path": r["path"], "reason": r["reason"]} for r in rows if r["status"] == "skipped"
        ],
        "outputs": {
            "structure_dir": str(work / STRUCTURE_DIR),
            "questions": str(work / "structure-questions.json"),
            "summary": str(work / "structure-summary.json"),
        },
    }
    return StructureResult(EXIT_OK, result)


def _extract_all(
    dxf: Path, text_index: dict[str, Any], rel: str, texts: dict[str, str]
) -> dict[str, dict[str, Any]]:
    """Sheets -> grids -> levels over one DXF (read once). Output texts are added to `texts`."""
    try:
        doc: Drawing = open_checked(dxf, text_index)
        docs: dict[str, dict[str, Any]] = {}
        docs["sheets"] = extract_sheets(dxf, text_index, doc=doc)
        docs["grids"] = extract_grids(dxf, text_index, docs["sheets"], doc=doc)
        docs["levels"] = extract_levels(dxf, text_index, docs["sheets"], doc=doc)
    except OSError as exc:
        raise StructureError(EXIT_ENV, f"cannot read {dxf}: {exc}") from exc
    except ValueError as exc:
        raise StructureError(EXIT_INVALID, f"{rel}: {exc}") from exc
    for kind in _KINDS:
        texts[f"{STRUCTURE_DIR}/{rel}.{kind}.json"] = _output_text(kind, docs[kind], f"{rel} {kind}")
    return docs
