"""findings: `harness finding`, the drawing-reader agent records each judgement as a validated finding.

A reader judgement (what kind of drawing a sheet is, what a general-note item says, how the structure is
organised, where two sources disagree) used to live in prose, so a report could print a number or a claim
that no extracted entry backed, and meaning could be taken from text in a font nobody had decoded. Now the
judgement is a finding in `work/reader-findings.json`, tied to text-index entries, and the report prints only
what a finding (or another named artefact) carries.

    harness finding add <work_dir> --kind K --file F [--sheet S] --entries T000123,T000124 --value "..."
                        [--field k=v ...] [--question Q-012 ...] [--confidence low|medium] [--note "..."]
    harness finding withdraw <work_dir> F-001 --reason "..."
    harness finding list <work_dir> [--kind K] [--file F]

Kinds (schemas/reader-findings.schema.json):

  * sheet_class        --sheet required; --value one of SHEET_CLASSES (`mixed` = one sheet, several drawings;
                       `other` needs --note); every cited entry is assigned to that sheet.
  * note_item          --field topic=<NOTE_TOPICS>; the value is a verbatim quote of the cited entries'
                       display_text joined with single spaces (NFC, whitespace runs collapsed) that
                       starts and ends at token boundaries: the character before and after the match
                       is the end of the text, whitespace, punctuation or a symbol (`C30/3` is not a
                       quote of `C30/37`).
  * structural_system  --field aspect=<SYSTEM_ASPECTS>; the value is the reader's claim; entries may span
                       the sheets of one file.
  * cross_check        a mismatch between sources: at least two entries and one --question.

Refusals (nothing written): the file is not in the inventory; an entry or sheet does not exist; an entry is
not on the cited sheet; a question is unknown or obsolete; a note value is not a quote; and the FONT GATE: an
entry that `text_gate.meaning_block_reason` blocks (unknown, proposed or contradicted legacy-font encoding)
may not back any finding. The message names the entries, the reason and the font questions to answer first.
A blocked entry can only be quoted in a reader question (`harness ask`).

Confidence is the minimum of the cited entries' confidence; `--confidence` can only lower it; it is never
`high` (only an engineer answer is). Ids F-001.. are monotonic and never reused; `withdraw` keeps the
finding with its reason (twice is a no-op). Adding the same finding again (same kind, file, sheet, entries,
value, fields and questions as an active one) prints that id with status `already_recorded`. A sheet has one
active class: classify it again only after withdrawing the first finding. Each finding records the file's
sha256 from the inventory; `list` marks a finding `stale` once the inventory sha256 differs.

`decoded_by` (tool wave 2, fix 10) records how the cited entries were decoded: one item per (decode source,
knowledge pattern) of their runs (text-index `decode.run_details`), with that knowledge row's status and
decision date in the font-encoding table at the time. `list` also marks a finding `stale` when such a row
now has another status or date, or is gone. A stale finding is neither a duplicate of a new one nor in the
way of a new sheet class.

Stdout: add -> {"id", "status": "new" | "already_recorded"}; withdraw -> {"id", "status": "withdrawn" |
"already_withdrawn"}; list -> the document with a `stale` flag on every finding. Exit codes (AGENTS.md):
1 a refusal that depends on the work folder, 2 usage (missing or malformed option, unknown finding id, no
work folder), 3 environment.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any

from tekla_harness.knowledge import FontEncodingTable, KnowledgeError, default_font_encodings
from tekla_harness.questions import (
    EXIT_INVALID,
    EXIT_USAGE,
    Ledger,
    QuestionsError,
    dump_json,
    load_ledger,
    write_text_atomic,
)
from tekla_harness.schemas import validate
from tekla_harness.sheet_text import Inventory, ReaderError, index_by_id, load_file, load_inventory
from tekla_harness.text_gate import meaning_block_reason

COMMAND = "finding"
HELP = "record a drawing-reader finding tied to extracted entries (reader-findings.json)"

EXIT_ENV = 3
SCHEMA_VERSION = "0.1"
FINDINGS_FILE = "reader-findings.json"
KINDS = ("sheet_class", "note_item", "structural_system", "cross_check")
SHEET_CLASSES = (
    "general_notes",
    "setting_out",
    "foundation",
    "foundation_details",
    "floor_framing",
    "column_details",
    "beam_details",
    "slab_details",
    "stairs",
    "schedules",
    "steel_details",
    "mixed",
    "other",
)
NOTE_TOPICS = (
    "design_code",
    "concrete_class",
    "rebar_grade",
    "steel_grade",
    "bolt_grade",
    "weld",
    "cover",
    "lap",
    "convention",
    "other",
)
SYSTEM_ASPECTS = ("frame_type", "foundation_type", "lateral_system", "floors", "typical_floors")
# kind -> (required field name, its allowed values)
REQUIRED_FIELD = {
    "note_item": ("topic", NOTE_TOPICS),
    "structural_system": ("aspect", SYSTEM_ASPECTS),
}
# registry codes of the questions that unblock a legacy-font entry (the engineer approves the font row)
FONT_QUESTION_CODES = (
    "font_encoding_proposed",
    "font_encoding_conflict",
    "encoding_unknown_non_ascii",
    "text_encoding_hint",
)
CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
MAX_LISTED = 8


class FindingError(Exception):
    """A request that cannot be recorded; `exit_code` is the CLI exit code."""

    def __init__(self, exit_code: int, message: str) -> None:
        super().__init__(message)
        self.exit_code = exit_code


# --- document ---------------------------------------------------------------------------------------


def _empty(project_id: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "reader_findings",
        "project_id": project_id,
        "next_id": 1,
        "findings": [],
    }


def _load_doc(work: Path, project_id: str | None) -> dict[str, Any] | None:
    """The stored document, or None when there is none yet. `project_id`: refuse another project's."""
    path = work / FINDINGS_FILE
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FindingError(EXIT_INVALID, f"{FINDINGS_FILE} cannot be read: {exc}") from exc
    problems = validate("reader-findings", doc)
    if problems:
        raise FindingError(
            EXIT_INVALID, f"{FINDINGS_FILE} is invalid: {problems[0].path}: {problems[0].message}"
        )
    if project_id is not None and doc["project_id"] != project_id:
        raise FindingError(
            EXIT_INVALID,
            f"{FINDINGS_FILE} is for project '{doc['project_id']}', not '{project_id}' (inventory.json)",
        )
    highest = max((int(f["id"][2:]) for f in doc["findings"]), default=0)
    if doc["next_id"] <= highest:  # ids are never reused: a smaller next_id would allocate a duplicate
        raise FindingError(
            EXIT_INVALID,
            f"{FINDINGS_FILE}: next_id {doc['next_id']} is not above the highest id F-{highest:03d}",
        )
    return doc


def _write_doc(work: Path, doc: dict[str, Any]) -> None:
    doc["findings"].sort(key=lambda f: f["id"])
    problems = validate("reader-findings", doc)
    if problems:  # a bug here, not in the work folder
        raise FindingError(
            EXIT_INVALID, f"{FINDINGS_FILE} would be invalid, nothing written: {problems[0].message}"
        )
    try:
        write_text_atomic(work / FINDINGS_FILE, dump_json(doc))
    except OSError as exc:
        raise FindingError(EXIT_ENV, f"cannot write {work / FINDINGS_FILE}: {exc}") from exc


# --- checks -----------------------------------------------------------------------------------------


def collapse(text: str) -> str:
    """NFC with every whitespace run as one space, trimmed: what a note quote is compared on."""
    return " ".join(unicodedata.normalize("NFC", text).split())


def _is_boundary(char: str) -> bool:
    """Whitespace, punctuation or a symbol: a character a token cannot continue through."""
    return char.isspace() or unicodedata.category(char)[0] in "PSZC"


def is_quote(value: str, text: str) -> bool:
    """True when `value` is a verbatim quote of `text` on the collapsed form (NFC, whitespace runs as one
    space) that starts and ends at token boundaries: the character before the match and the one after it
    are each the end of the text, whitespace, punctuation or a symbol. `C30/3` is not a quote of
    `C30/37` (cut mid-token), `C30/37` is. An empty value never is."""
    quote, haystack = collapse(value), collapse(text)
    if not quote:
        return False
    start = haystack.find(quote)
    while start != -1:
        end = start + len(quote)
        if (start == 0 or _is_boundary(haystack[start - 1])) and (
            end == len(haystack) or _is_boundary(haystack[end])
        ):
            return True
        start = haystack.find(quote, start + 1)
    return False


def _shown(items: list[str]) -> str:
    more = f" (+{len(items) - MAX_LISTED} more)" if len(items) > MAX_LISTED else ""
    return ", ".join(items[:MAX_LISTED]) + more


def _font_questions(ledger: Ledger, file: str) -> list[str]:
    rows = [
        f"{e['id']} ({e['code']}, {e['status']})"
        for e in ledger.registry["questions"].values()
        if e["file"] == file and e["code"] in FONT_QUESTION_CODES and e["status"] != "obsolete"
    ]
    return sorted(rows)


def _gate(entries: list[dict[str, Any]], ledger: Ledger, file: str) -> None:
    blocked = [(e["id"], reason) for e in entries if (reason := meaning_block_reason(e)) is not None]
    if not blocked:
        return
    reasons = sorted({r for _, r in blocked})
    questions = _font_questions(ledger, file)
    advice = (
        f"answer the font question first: {', '.join(questions)}"
        if questions
        else "no font question is registered for this file: rerun `harness intake`"
    )
    raise FindingError(
        EXIT_INVALID,
        f"refused: {len(blocked)} cited entr{'y is' if len(blocked) == 1 else 'ies are'} blocked by the "
        f"legacy-font gate ({', '.join(reasons)}): {_shown([i for i, _ in blocked])}. Meaning may not be "
        f"taken from text whose encoding is not settled; {advice}. "
        "Quote the text in a reader question (`harness ask`) instead.",
    )


def _usage_checks(
    kind: str,
    sheet: str | None,
    entry_ids: list[str],
    value: str,
    fields: dict[str, str],
    questions: list[str],
    note: str | None,
) -> None:
    if not value.strip():
        raise FindingError(EXIT_USAGE, "--value is empty: say what the finding is")
    if note is not None and not note.strip():
        raise FindingError(EXIT_USAGE, "--note is empty: omit it")
    if sheet is not None and not sheet.strip():
        raise FindingError(EXIT_USAGE, "--sheet is empty: omit it when the finding has no one sheet")
    if not entry_ids:
        raise FindingError(EXIT_USAGE, "--entries is empty: cite at least one text-index entry id")
    if len(set(entry_ids)) != len(entry_ids):
        raise FindingError(EXIT_USAGE, "--entries lists an entry id twice")
    for eid in entry_ids:
        if not (len(eid) >= 7 and eid[0] == "T" and eid[1:].isdigit()):
            raise FindingError(EXIT_USAGE, f"entry id '{eid}' must look like T000123")
    for qid in questions:
        if not (qid.startswith("Q-") and len(qid) >= 5 and qid[2:].isdigit()):
            raise FindingError(EXIT_USAGE, f"question id '{qid}' must look like Q-012")
    if kind in REQUIRED_FIELD:
        name, allowed = REQUIRED_FIELD[kind]
        if name not in fields:
            raise FindingError(EXIT_USAGE, f"kind {kind} needs --field {name}=<{'|'.join(allowed)}>")
        if fields[name] not in allowed:
            raise FindingError(
                EXIT_USAGE, f"--field {name}={fields[name]} is not one of: {', '.join(allowed)}"
            )
    if kind == "sheet_class":
        if sheet is None:
            raise FindingError(EXIT_USAGE, "kind sheet_class needs --sheet (a detector sheet id)")
        if value not in SHEET_CLASSES:
            raise FindingError(
                EXIT_USAGE, f"--value '{value}' is not a sheet class: {', '.join(SHEET_CLASSES)}"
            )
        if value == "other" and (note is None or not note.strip()):
            raise FindingError(EXIT_USAGE, "sheet class 'other' needs --note saying what the sheet is")
        if fields:
            raise FindingError(EXIT_USAGE, "kind sheet_class takes no --field")
    if kind == "cross_check":
        if len(entry_ids) < 2:
            raise FindingError(EXIT_USAGE, "kind cross_check cites at least two entries (one per source)")
        if not questions:
            raise FindingError(
                EXIT_USAGE, "kind cross_check needs at least one --question (the mismatch is asked)"
            )


def _row_state(table: FontEncodingTable, pattern: str) -> tuple[str | None, str | None]:
    """(status, decided_on) of the knowledge row with this pattern; (None, None) when the table has none.
    The text index records the pattern only, not `applies_to`: when two rows share it, the approved one
    (the only kind that decides a decoding), then the first by line, is taken; the same rule is applied at
    `add` and at `list`, so a change of either row is still seen."""
    rows = sorted(
        (r for r in table.rows if r.pattern == pattern), key=lambda r: (r.status != "approved", r.line)
    )
    if not rows:
        return None, None
    return rows[0].status, rows[0].decided_on or None


def _decoded_by(entries: list[dict[str, Any]], table: FontEncodingTable) -> list[dict[str, Any]]:
    """One item per (decode source, knowledge pattern) of the cited entries' runs (text-index
    decode.run_details), in order of first appearance, with the row's status and decision date now."""
    groups: dict[tuple[str, str | None], list[str]] = {}
    for e in entries:
        runs = e["decode"]["run_details"]
        for pair in dict.fromkeys((r["font_source"], r["knowledge_pattern"]) for r in runs):
            groups.setdefault(pair, []).append(e["id"])
    out = []
    for (source, pattern), ids in groups.items():
        status, decided_on = _row_state(table, pattern) if pattern is not None else (None, None)
        out.append(
            {
                "source": source,
                "knowledge_pattern": pattern,
                "row_status": status,
                "decided_on": decided_on,
                "entries": ids,
            }
        )
    return out


def _knowledge_changed(finding: dict[str, Any], table: FontEncodingTable) -> bool:
    """True when a knowledge row that decoded a cited entry has another status or decision date now (or is
    gone). A finding recorded before decoded_by existed is judged by its file only."""
    return any(
        _row_state(table, item["knowledge_pattern"]) != (item["row_status"], item["decided_on"])
        for item in finding.get("decoded_by") or ()
        if item["knowledge_pattern"] is not None
    )


def _table(knowledge: FontEncodingTable | None) -> FontEncodingTable:
    if knowledge is not None:
        return knowledge
    try:
        return default_font_encodings()
    except KnowledgeError as exc:
        raise FindingError(EXIT_ENV, f"the font-encoding knowledge table cannot be read: {exc}") from exc


def _confidence(entries: list[dict[str, Any]], requested: str | None) -> str:
    computed = min((e["confidence"] for e in entries), key=lambda c: CONFIDENCE_RANK[c])
    computed = "medium" if computed == "high" else computed  # only an engineer answer is high
    if requested is None:
        return computed
    if CONFIDENCE_RANK[requested] > CONFIDENCE_RANK[computed]:
        raise FindingError(
            EXIT_INVALID,
            f"--confidence {requested} is higher than the cited entries allow ({computed}): "
            "it can only be lowered",
        )
    return requested


def _parse_fields(raw: list[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for item in raw:
        name, sep, val = item.partition("=")
        if not sep or not name or not val.strip():
            raise FindingError(EXIT_USAGE, f"--field '{item}' must be key=value")
        if not (name[0].islower() and all(c.islower() or c.isdigit() or c == "_" for c in name)):
            raise FindingError(EXIT_USAGE, f"--field key '{name}' must be lowercase snake_case")
        if name in fields:
            raise FindingError(EXIT_USAGE, f"--field {name} given twice")
        fields[name] = val
    return dict(sorted(fields.items()))


# --- add --------------------------------------------------------------------------------------------


def _inventory(work_dir: Path | str) -> Inventory:
    try:
        return load_inventory(work_dir)
    except ReaderError as exc:
        raise FindingError(exc.exit_code, str(exc)) from exc


def _inventory_row(inv: Inventory, file: str) -> dict[str, Any]:
    for row in inv.doc["files"]:
        if row["path"] == file:
            return row
    raise FindingError(
        EXIT_INVALID, f"file '{file}' is not in inventory.json: use a path exactly as listed there"
    )


def add_finding(
    work_dir: Path | str,
    *,
    kind: str,
    file: str,
    entries: list[str],
    value: str,
    sheet: str | None = None,
    fields: list[str] | None = None,
    questions: list[str] | None = None,
    confidence: str | None = None,
    note: str | None = None,
    knowledge: FontEncodingTable | None = None,
) -> dict[str, str]:
    """Record one finding (see the module docstring). `knowledge`: the font-encoding table whose rows are
    recorded in decoded_by (default: the shipped one). Raises FindingError."""
    if kind not in KINDS:
        raise FindingError(EXIT_USAGE, f"unknown kind '{kind}': choose from {', '.join(KINDS)}")
    if confidence is not None and confidence not in ("low", "medium"):
        raise FindingError(
            EXIT_USAGE, "--confidence is low or medium; 'high' comes only from an engineer answer"
        )
    field_map = _parse_fields(fields or [])
    question_ids = list(dict.fromkeys(questions or []))
    _usage_checks(kind, sheet, entries, value, field_map, question_ids, note)

    inv = _inventory(work_dir)
    work = inv.work
    row = _inventory_row(inv, file)
    try:
        loaded = load_file(inv, row)
    except ReaderError as exc:
        raise FindingError(exc.exit_code, str(exc)) from exc
    if loaded.text_index is None:
        raise FindingError(EXIT_INVALID, f"{file}: {loaded.skip}")
    by_id = index_by_id(loaded.text_index)
    missing = [e for e in entries if e not in by_id]
    if missing:
        raise FindingError(EXIT_INVALID, f"entries not in the text index of {file}: {_shown(missing)}")
    cited = [by_id[e] for e in entries]

    if sheet is not None:
        if loaded.sheets is None:
            raise FindingError(
                EXIT_INVALID, f"{file} has no structure/ sheets document: run `harness read-structure` first"
            )
        sheet_doc = next((s for s in loaded.sheets["sheets"] if s["sheet_id"] == sheet), None)
        if sheet_doc is None:
            known = [s["sheet_id"] for s in loaded.sheets["sheets"]]
            raise FindingError(EXIT_INVALID, f"{file} has no sheet '{sheet}' (sheets: {_shown(known)})")
        on_sheet = set(sheet_doc["text_ids"])
        elsewhere = [e for e in entries if e not in on_sheet]
        if elsewhere:
            raise FindingError(
                EXIT_INVALID, f"entries not assigned to sheet {sheet} in {file}: {_shown(elsewhere)}"
            )

    try:
        ledger = load_ledger(work, None, create=False)
    except QuestionsError as exc:
        raise FindingError(exc.exit_code, str(exc)) from exc
    _gate(cited, ledger, file)
    for qid in question_ids:
        found = ledger.entry_by_id(qid)
        if found is None:
            raise FindingError(EXIT_INVALID, f"unknown question id {qid} (see question-registry.json)")
        if found[1]["status"] == "obsolete":
            raise FindingError(EXIT_INVALID, f"question {qid} is obsolete: cite a live question")

    if kind == "note_item" and not is_quote(value, " ".join(e["display_text"] for e in cited)):
        raise FindingError(
            EXIT_INVALID,
            "a note_item value must be a verbatim quote of the cited entries' display_text "
            "(joined with single spaces) that starts and ends at word boundaries (not cut inside a "
            "token: 'C30/3' is not a quote of 'C30/37'): cite the entries that hold the words, do not "
            "paraphrase",
        )
    final_confidence = _confidence(cited, confidence)
    table = _table(knowledge)

    doc = _load_doc(work, inv.doc["project_id"]) or _empty(inv.doc["project_id"])
    sha = row["sha256"]
    cited_record = [{"id": e["id"], "display_text": e["display_text"]} for e in cited]
    for old in doc["findings"]:
        if old["status"] != "active" or old["file"] != file or old["file_sha256"] != sha:
            continue
        if _knowledge_changed(old, table):  # stale like a changed file: neither a duplicate nor in the way
            continue
        same = (
            old["kind"] == kind
            and old["sheet"] == sheet
            and [e["id"] for e in old["entries"]] == entries
            and old["value"] == value
            and old["fields"] == field_map
            and sorted(old["questions"]) == sorted(question_ids)
        )
        if same:
            return {"id": old["id"], "status": "already_recorded"}
        if kind == "sheet_class" and old["kind"] == kind and old["sheet"] == sheet:
            raise FindingError(
                EXIT_INVALID,
                f"{old['id']} already classifies sheet {sheet} as '{old['value']}': "
                "withdraw it first (`harness finding withdraw`) to classify the sheet again",
            )

    finding_id = f"F-{doc['next_id']:03d}"
    doc["next_id"] += 1
    finding: dict[str, Any] = {
        "id": finding_id,
        "kind": kind,
        "status": "active",
        "file": file,
        "file_sha256": sha,
        "sheet": sheet,
        "entries": cited_record,
        "value": value,
        "fields": field_map,
        "questions": question_ids,
        "confidence": final_confidence,
        "decoded_by": _decoded_by(cited, table),
    }
    if note is not None:
        finding["note"] = note.strip()
    doc["findings"].append(finding)
    _write_doc(work, doc)
    return {"id": finding_id, "status": "new"}


# --- withdraw and list ------------------------------------------------------------------------------


def withdraw_finding(work_dir: Path | str, finding_id: str, reason: str) -> dict[str, str]:
    """Mark a finding withdrawn (kept, with the reason). Raises FindingError."""
    work = Path(work_dir).resolve()
    if not work.is_dir():
        raise FindingError(EXIT_USAGE, f"work folder not found (not a folder): {work_dir}")
    if not reason.strip():
        raise FindingError(EXIT_USAGE, "--reason is empty: say why the finding is withdrawn")
    doc = _load_doc(work, None)
    if doc is None:
        raise FindingError(EXIT_USAGE, f"{work} has no {FINDINGS_FILE}: nothing to withdraw")
    found = next((f for f in doc["findings"] if f["id"] == finding_id), None)
    if found is None:
        raise FindingError(EXIT_USAGE, f"unknown finding id '{finding_id}' (see {FINDINGS_FILE})")
    if found["status"] == "withdrawn":
        return {"id": finding_id, "status": "already_withdrawn"}
    found["status"] = "withdrawn"
    found["withdrawn_reason"] = reason.strip()
    _write_doc(work, doc)
    return {"id": finding_id, "status": "withdrawn"}


def list_findings(
    work_dir: Path | str,
    *,
    kind: str | None = None,
    file: str | None = None,
    knowledge: FontEncodingTable | None = None,
) -> dict[str, Any]:
    """The document with `stale` on every finding (its file's inventory sha256 changed or the file is gone,
    or a knowledge row in its decoded_by has another status or decision date in `knowledge`, default the
    shipped table), optionally filtered. Raises FindingError."""
    if kind is not None and kind not in KINDS:
        raise FindingError(EXIT_USAGE, f"unknown kind '{kind}': choose from {', '.join(KINDS)}")
    inv = _inventory(work_dir)
    doc = _load_doc(inv.work, inv.doc["project_id"]) or _empty(inv.doc["project_id"])
    current = {row["path"]: row["sha256"] for row in inv.doc["files"]}
    table = _table(knowledge)
    out = dict(doc)
    out["findings"] = [
        {**f, "stale": current.get(f["file"]) != f["file_sha256"] or _knowledge_changed(f, table)}
        for f in doc["findings"]
        if (kind is None or f["kind"] == kind) and (file is None or f["file"] == file)
    ]
    return out


# --- command ----------------------------------------------------------------------------------------


def add_arguments(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="action", required=True, metavar="{add,withdraw,list}")

    p_add = sub.add_parser("add", help="record a finding tied to text-index entries")
    p_add.add_argument("work_dir", help="the --out folder of `harness intake`")
    p_add.add_argument("--kind", required=True, choices=KINDS)
    p_add.add_argument("--file", required=True, help="the drawing file, as listed in inventory.json")
    p_add.add_argument("--sheet", help="the detector sheet id every cited entry is on (model#01)")
    p_add.add_argument(
        "--entries", required=True, help="comma-separated text-index entry ids, e.g. T000123,T000124"
    )
    p_add.add_argument("--value", required=True, help="the finding (a quote for note_item)")
    p_add.add_argument(
        "--field",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="note_item topic=, structural_system aspect=",
    )
    p_add.add_argument(
        "--question", action="append", default=[], metavar="Q-ID", help="a related registry question"
    )
    p_add.add_argument("--confidence", choices=("low", "medium"), help="lower than the entries' minimum")
    p_add.add_argument("--note", help="free remark (required for sheet class 'other')")

    p_wd = sub.add_parser("withdraw", help="withdraw a finding (kept, with the reason)")
    p_wd.add_argument("work_dir", help="the --out folder of `harness intake`")
    p_wd.add_argument("finding_id", metavar="F-ID")
    p_wd.add_argument("--reason", required=True)

    p_ls = sub.add_parser("list", help="print reader-findings.json with a stale flag per finding")
    p_ls.add_argument("work_dir", help="the --out folder of `harness intake`")
    p_ls.add_argument("--kind", choices=KINDS)
    p_ls.add_argument("--file", help="only findings of this drawing file")


def run(args: argparse.Namespace) -> int:
    try:
        if args.action == "add":
            result: dict[str, Any] = add_finding(
                args.work_dir,
                kind=args.kind,
                file=args.file,
                sheet=args.sheet,
                entries=[e.strip() for e in args.entries.split(",") if e.strip()],
                value=args.value,
                fields=args.field,
                questions=args.question,
                confidence=args.confidence,
                note=args.note,
            )
            if result["status"] == "already_recorded":
                print(f"{result['id']}: already recorded", file=sys.stderr)
        elif args.action == "withdraw":
            result = withdraw_finding(args.work_dir, args.finding_id, args.reason)
        else:
            result = list_findings(args.work_dir, kind=args.kind, file=args.file)
    except FindingError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except OSError as exc:  # environment: an unreadable or unwritable work folder, not a refusal
        print(f"harness {COMMAND}: {exc}", file=sys.stderr)
        return EXIT_ENV
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
