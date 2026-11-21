"""findings: `harness finding`, the drawing-reader agent records each judgement as a validated finding.

A reader judgement (what kind of drawing a sheet is, what a general-note item says, how the structure is
organised, where two sources disagree) used to live in prose, so a report could print a number or a claim
that no extracted entry backed, and meaning could be taken from text in a font nobody had decoded. Now the
judgement is a finding in `work/reader-findings.json`, tied to text-index entries, and the report prints only
what a finding (or another named artefact) carries.

    harness finding add <work_dir> --kind K --file F [--sheet S] --entries T000123,T000124 --value "..."
                        [--field k=v ...] [--question Q-012 ...] [--confidence low|medium] [--note "..."]
    harness finding add <work_dir> --kind measured --file F [--sheet S] --source geometry/<name>.json
                        --items G-0123456789,G-... --value "..." [--field quantity=count] [--entries ...]
                        [--claim symbols=4 --claim short=1700 ...]
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
  * cross_check        a mismatch between sources: at least two entries and one --question; one entry
                       is enough with --source/--items (the second source is a measurement).
  * measured           a value measured on vector geometry (a pile count per cap, a cap size, the axes
                       that carry caps), not read from text: `--source` is a document saved by
                       `harness geometry --save` or `harness contents --save` (saved_evidence.py) and
                       `--items` ids in it (geometry: regions[].items[].id, saved with --detail;
                       contents: outlines[].id). The document must be of --file, cover --sheet, validate
                       against its schema and carry the name its query and the drawing's inventory sha256
                       give (a document saved for another drawing version, or edited after `--save`, is
                       refused). The finding stores `evidence` {source, sha256 of the saved file,
                       command, query, items}; `items` holds a snapshot of each cited item (its id and
                       the measured fields it has: kind, layer, sheet, space, centre, short, long,
                       diameter, symbols, marks, axes, invisible), so the report reads the numbers next to
                       the finding. With --sheet, a geometry item on another sheet is refused. `--claim
                       KEY=VALUE` (keys symbols, short, long, diameter, count; repeatable) states a number
                       of --value: it is checked against EVERY cited item (symbols exactly, short, long and
                       diameter within the saved query's tol, count = the number of cited items) and a
                       mismatch exits 1 naming the item and the field. --value stays free text, but every
                       standalone number in it (DC-1, C30, model#06 hold none; d500 is 500; 1700x3200 is
                       two) must be backed by a --claim or a number in a cited entry, else exit 1 (a
                       contents outline carries no diameter, so a diameter needs a cited schedule or
                       callout entry). `--entries` are optional.
                       Confidence is `medium` without entries (the measurement is exact, which layer is a
                       pile or a cap is the reader's reading); it is `high` only when at least one --claim
                       is given and every claimed number is in the text of a cited entry (an agreeing
                       printed value), and then the minimum of the entries'; --confidence only lowers it.

Refusals (nothing written): the file is not in the inventory; an entry or sheet does not exist; an entry is
not on the cited sheet; a question is unknown or obsolete; a note value is not a quote; and the FONT GATE: an
entry that `text_gate.meaning_block_reason` blocks (unknown, proposed or contradicted legacy-font encoding)
may not back any finding. The message names the entries, the reason and the font questions to answer first.
A blocked entry can only be quoted in a reader question (`harness ask`).

Confidence is the minimum of the cited entries' confidence (`medium` without entries); `--confidence` can
only lower it; it is never `high` (only an engineer answer is), except for kind measured whose claims
every cite entries show (an agreeing printed value): that one takes the entries' minimum, `high` included.
Ids F-001.. are monotonic and never reused;
`withdraw` keeps the finding with its reason (twice is a no-op). Adding the same finding again (same kind,
file, sheet, entries, value, fields, part, questions and evidence as an active one) prints that id with status
`already_recorded`. A sheet has one active class, whatever the part: classify it again only after
withdrawing the first finding (the refusal names its part, which `withdraw` needs). Each finding records
the file's sha256 from the inventory; `list` marks a finding `stale` once
the inventory sha256 differs, or once the saved file of its evidence has changed or is gone (`evidence` is
listed with the finding). Saved files are immutable (saved_evidence.py), so a re-save never makes a finding
stale. Every stale finding lists `stale_reasons` ([{reason, detail}]: drawing_changed, knowledge_changed,
evidence_missing, evidence_changed) and, with evidence, `redo`: the `harness ... --save` command of its
stored query; then add the finding again and withdraw the old one.

`decoded_by` (tool wave 2, fix 10) records how the cited entries were decoded: one item per (decode source,
knowledge pattern) of their runs (text-index `decode.run_details`), with that knowledge row's status and
decision date in the font-encoding table at the time. `list` also marks a finding `stale` when such a row
now has another status or date, or is gone. A stale finding is neither a duplicate of a new one nor in the
way of a new sheet class.

`--part ID` (add, withdraw; ADR-0019) stores the part on the finding (`part`) and `list` shows it. It is
optional until the work folder has parts/manifest.json (an id must match parts.PART_ID_RE, exit 2), then
required (exit 2) and must be listed in the manifest (exit 1). Anything at the manifest path that is not a
usable manifest (a directory, a dangling symlink, bad JSON) is exit 1, a path the system refuses to check or
read is exit 3 (parts.manifest_present). `withdraw`
of a finding that has a part needs that same part (exit 1), which is accepted even when the manifest no
longer lists it. The same finding in another part is a new finding.
A locked part refuses `add` and `withdraw` (ADR-0019, E5b): the `--part` given, and a withdrawn finding's own
part, whose latest receipt is `locked` is exit 1 with the reopen command, nothing written; unreadable receipts
are exit 1 naming the file, another `OSError` exit 3. Without a manifest nothing is checked.

Stdout: add -> {"id", "status": "new" | "already_recorded"}; withdraw -> {"id", "status": "withdrawn" |
"already_withdrawn"}; list -> the document with a `stale` flag on every finding and `summary.by_class`
(listed sheet_class findings per class, active and not stale only). Exit codes (AGENTS.md):
1 a refusal that depends on the work folder, 2 usage (missing or malformed option, unknown finding id, no
work folder), 3 environment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import unicodedata
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from tekla_harness.knowledge import FontEncodingTable, KnowledgeError, default_font_encodings
from tekla_harness.parts import MANIFEST_REL, PART_ID_RE, ManifestAccessError, ManifestError, part_ids
from tekla_harness.questions import (
    EXIT_INVALID,
    EXIT_USAGE,
    Ledger,
    QuestionsError,
    dump_json,
    load_ledger,
    write_text_atomic,
)
from tekla_harness.saved_evidence import COMMANDS as EVIDENCE_COMMANDS
from tekla_harness.saved_evidence import GEOMETRY_DIR, NAME, content_hash, file_name, redo_command
from tekla_harness.schemas import validate
from tekla_harness.sheet_text import Inventory, ReaderError, index_by_id, load_file, load_inventory
from tekla_harness.text_gate import meaning_block_reason

COMMAND = "finding"
HELP = "record a drawing-reader finding tied to extracted entries or measured geometry (reader-findings.json)"

EXIT_ENV = 3
SCHEMA_VERSION = "0.1"
FINDINGS_FILE = "reader-findings.json"
PART_HELP = (
    "the part (block x member family) the finding belongs to; optional until the work folder has "
    "parts/manifest.json, then required and listed in it"
)
KINDS = ("sheet_class", "note_item", "structural_system", "cross_check", "measured")
EVIDENCE_KINDS = ("measured", "cross_check")  # the kinds that may cite a saved geometry or contents document
QUANTITIES = ("count", "size", "position", "level", "spacing")
CLAIM_KEYS = ("symbols", "short", "long", "diameter", "count")  # --claim: integers, then numbers within tol
_SNAPSHOT_FIELDS = (
    "kind", "layer", "sheet", "space", "centre", "short", "long", "diameter", "symbols", "marks", "axes",
    "invisible",
)  # fmt: skip
_SOURCE = re.compile(rf"^{GEOMETRY_DIR}/[^/\\]+\.json$")
_ITEM_ID = re.compile(r"^G-[0-9a-f]{10}$")
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
    "legacy_ascii_text",  # tool wave 3 (W3): what a legacy-ASCII style holds; its answer decodes nothing
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
    source: str | None = None,
    items: list[str] | None = None,
    claims: dict[str, float | int] | None = None,
) -> None:
    items = items or []
    if not value.strip():
        raise FindingError(EXIT_USAGE, "--value is empty: say what the finding is")
    if note is not None and not note.strip():
        raise FindingError(EXIT_USAGE, "--note is empty: omit it")
    if sheet is not None and not sheet.strip():
        raise FindingError(EXIT_USAGE, "--sheet is empty: omit it when the finding has no one sheet")
    if (source is not None or items) and kind not in EVIDENCE_KINDS:
        raise FindingError(
            EXIT_USAGE, f"--source and --items are for kinds {' and '.join(EVIDENCE_KINDS)}, not {kind}"
        )
    if kind == "measured" and source is None:
        raise FindingError(EXIT_USAGE, f"kind measured needs --source {GEOMETRY_DIR}/<name>.json and --items")
    if source is not None:
        if not _SOURCE.match(source):
            raise FindingError(
                EXIT_USAGE,
                f"--source '{source}' must be a document saved in the work folder: "
                f"{GEOMETRY_DIR}/<name>.json "
                "(`harness geometry --save` or `harness contents --save` prints the path)",
            )
        if not items:
            raise FindingError(EXIT_USAGE, "--items is empty: cite at least one item id of the source")
        if len(set(items)) != len(items):
            raise FindingError(EXIT_USAGE, "--items lists an item id twice")
        for item in items:
            if not _ITEM_ID.match(item):
                raise FindingError(EXIT_USAGE, f"item id '{item}' must look like G-0123456789")
    elif items:
        raise FindingError(EXIT_USAGE, "--items needs --source")
    if claims and source is None:
        raise FindingError(EXIT_USAGE, "--claim needs --source and --items (it is checked against the items)")
    if kind == "measured" and "quantity" in fields and fields["quantity"] not in QUANTITIES:
        raise FindingError(
            EXIT_USAGE, f"--field quantity={fields['quantity']} is not one of: {', '.join(QUANTITIES)}"
        )
    if not entry_ids and kind != "measured":
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
        if len(entry_ids) < (1 if source is not None else 2):
            raise FindingError(
                EXIT_USAGE,
                "kind cross_check cites at least two entries (one per source), "
                "or one entry with --source and --items (the other source is a measurement)",
            )
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


# A standalone number: not glued to a letter, digit, `#` or `-` on either side (DC-1, model#06, A-3, C30 and
# KC-B1-09 hold none); a d, D or O-slash prefix is kept (d500 is 500). `NxM` is split first.
_NUMBER = re.compile(r"(?<![\w#\-.])[dD\u00d8\u00f8]?(\d+(?:\.\d+)?)(?![\w#\-])")
_TIMES = re.compile(r"(?<=\d)\s*[xX\u00d7]\s*(?=\d)")


def _numbers(text: str) -> list[float]:
    """The standalone numbers of a text, in order (see _NUMBER)."""
    return [float(m[1]) for m in _NUMBER.finditer(_TIMES.sub(" ", text))]


def _unbacked_numbers(
    value: str, claims: dict[str, float | int], tol: float, entry_texts: list[str]
) -> list[float]:
    """The numbers of `value` that no claim (symbols, count exactly; the others within tol) and no cited entry
    text shows."""
    shown = {n for text in entry_texts for n in _numbers(text)}
    return [
        n
        for n in _numbers(value)
        if n not in shown
        and not any(n == c if k in ("symbols", "count") else abs(n - c) <= tol for k, c in claims.items())
    ]


def _claims_shown(claims: dict[str, float | int], entry_texts: list[str]) -> bool:
    """True when there is a claim and every claimed number is in the text of at least one cited entry."""
    shown = {n for text in entry_texts for n in _numbers(text)}
    return bool(claims) and all(float(c) in shown for c in claims.values())


def _confidence(
    kind: str,
    entries: list[dict[str, Any]],
    requested: str | None,
    claims: dict[str, float | int] | None = None,
) -> str:
    computed = min((e["confidence"] for e in entries), key=lambda c: CONFIDENCE_RANK[c], default="medium")
    if computed == "high" and not (
        kind == "measured" and _claims_shown(claims or {}, [e["display_text"] for e in entries])
    ):
        computed = (
            "medium"  # only an engineer answer is high; a measurement whose claims an entry shows may be
        )
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


def _checked_part(work: Path, part: str | None, own: tuple[str, ...] = ()) -> str | None:
    """`--part` as the work folder allows it (ADR-0019): the id must match the pattern (exit 2); with a
    parts manifest it is required (exit 2) and must be listed in it (exit 1); anything at the manifest path
    that is not a usable manifest is exit 1, a path the system refuses to check or read is exit 3. Without a
    manifest the part stays optional. `own`: the parts the record being withdrawn holds; one of them is
    accepted even when the manifest no longer lists it (a withdraw can always clear its own part)."""
    if part is not None and not PART_ID_RE.fullmatch(part):
        raise FindingError(EXIT_USAGE, f"--part '{part}' must match {PART_ID_RE.pattern}")
    try:
        known = part_ids(work)
    except ManifestError as exc:
        raise FindingError(EXIT_INVALID, str(exc)) from exc
    except ManifestAccessError as exc:
        raise FindingError(EXIT_ENV, str(exc)) from exc
    if known is None:
        return part
    if part is None:
        raise FindingError(EXIT_USAGE, f"--part is required: {MANIFEST_REL} exists (give the part's id)")
    if part in own:
        return part
    if not known:
        raise FindingError(
            EXIT_INVALID, f"part '{part}' is not in {MANIFEST_REL}: the manifest lists no parts"
        )
    if part not in known:
        raise FindingError(
            EXIT_INVALID, f"part '{part}' is not in {MANIFEST_REL} (parts: {_shown(sorted(known))})"
        )
    return part


def _refuse_locked(work: Path, parts: Iterable[str | None]) -> None:
    """Refuse a write that changes a part the receipts say is locked (ADR-0019, E5b): the latest receipt of
    each part decides (`part_receipts.locked_parts`), not the derived status, so a hand edit of
    `values.json` cannot unlock it. Does nothing without a parts manifest. Exit 1 for a locked part and
    for receipts that are there and unusable (the file is named); any other `OSError` is exit 3."""
    from tekla_harness import part_receipts  # here: part_receipts imports this module through parts_manifest

    try:
        if part_ids(work) is None:
            return
    except ManifestError as exc:
        raise FindingError(EXIT_INVALID, str(exc)) from exc
    except ManifestAccessError as exc:
        raise FindingError(EXIT_ENV, str(exc)) from exc
    try:
        locked = part_receipts.locked_parts(work, [p for p in parts if p is not None])
        if not locked:
            return
        latest = part_receipts.read_receipts(work, locked[0])[-1]
    except ReaderError as exc:
        raise FindingError(exc.exit_code, str(exc)) from exc
    part = locked[0]
    raise FindingError(
        EXIT_INVALID,
        f"part '{part}' is locked (receipt {latest['n']}, {latest['at']}): reopen it first: "
        f'harness part receipt W --part {part} --kind reopened --reason "…"',
    )


# --- evidence ---------------------------------------------------------------------------------------


def _document_items(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The items a saved document lists by id: contents outlines[], geometry regions[].items[]."""
    if doc["kind"] == "contents":
        return {o["id"]: o for o in doc["outlines"]}
    return {i["id"]: i for r in doc["regions"] for i in r.get("items", [])}


def _snapshot(item: dict[str, Any]) -> dict[str, Any]:
    """The id and the measured fields an item has (a null field is left out)."""
    snap: dict[str, Any] = {"id": item["id"]}
    for name in _SNAPSHOT_FIELDS:
        if item.get(name) is not None:
            snap[name] = item[name]
    return snap


def _covers(doc: dict[str, Any], sheet: str) -> bool:
    """Whether the query of a saved document reads that sheet."""
    query = doc["query"]
    if doc["kind"] == "contents":
        return bool(query["sheet"] == sheet)
    if query.get("bbox") is not None:
        return False
    if query.get("sheet"):
        return sheet in query["sheet"]
    return any(r["sheet"] == sheet for r in doc["regions"])


def _parse_claims(raw: list[str]) -> dict[str, float | int]:
    """`--claim KEY=VALUE` strings -> {key: number}: symbols and count are integers. Raises FindingError."""
    claims: dict[str, float | int] = {}
    for text in raw:
        name, sep, val = text.partition("=")
        if not sep or not name or not val.strip():
            raise FindingError(EXIT_USAGE, f"--claim '{text}' must be key=value")
        if name not in CLAIM_KEYS:
            raise FindingError(EXIT_USAGE, f"--claim key '{name}' is not one of: {', '.join(CLAIM_KEYS)}")
        if name in claims:
            raise FindingError(EXIT_USAGE, f"--claim {name} given twice")
        try:
            number: float | int = int(val) if name in ("symbols", "count") else float(val)
        except ValueError as exc:
            kind = "an integer" if name in ("symbols", "count") else "a number"
            raise FindingError(EXIT_USAGE, f"--claim {name}={val} is not {kind}") from exc
        if not (isinstance(number, int) or math.isfinite(number)) or number < 0:
            raise FindingError(EXIT_USAGE, f"--claim {name}={val} must be a finite number, not negative")
        claims[name] = number
    return claims


def _check_claims(
    source: str,
    doc: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    items: list[str],
    claims: dict[str, Any],
) -> None:
    """Every claim must hold for EVERY cited item (numbers within the query's tol; `count` is the number of
    cited items). Raises FindingError (exit 1) naming the item and the field."""
    tol = float(doc["query"]["tol"])
    for name, claimed in claims.items():
        if name == "count":
            if len(items) != claimed:
                raise FindingError(
                    EXIT_INVALID, f"claim count={claimed}: {len(items)} items are cited, not {claimed}"
                )
            continue
        for item_id in items:
            actual = by_id[item_id].get(name)
            if actual is None:
                raise FindingError(
                    EXIT_INVALID,
                    f"claim {name}={claimed}: item {item_id} has no {name} in {source}"
                    + (
                        " (a contents outline carries no diameter: cite a schedule or callout entry "
                        "for a diameter)"
                        if name == "diameter" and doc["kind"] == "contents"
                        else ""
                    ),
                )
            ok = actual == claimed if name == "symbols" else abs(float(actual) - float(claimed)) <= tol
            if not ok:
                raise FindingError(
                    EXIT_INVALID,
                    f"claim {name}={claimed}: item {item_id} has {name} {actual}"
                    + ("" if name == "symbols" else f" (tol {tol:g})")
                    + f" in {source}",
                )


def _evidence(
    work: Path,
    row: dict[str, Any],
    file: str,
    sheet: str | None,
    source: str,
    items: list[str],
    claims: dict[str, float | int],
    value: str | None = None,
    entry_texts: list[str] | None = None,
) -> dict[str, Any]:
    """The `evidence` of a finding citing `items` of the document `source`: each item as a snapshot of the
    saved measurement. With `value` (kind measured) every number in it must be backed by a claim or a cited
    entry text. Raises FindingError."""
    path = work / source
    if not path.is_file():
        raise FindingError(
            EXIT_INVALID,
            f"--source {source} does not exist in {work}: save the document with "
            "`harness geometry --save` or `harness contents --save`",
        )
    raw = path.read_bytes()
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FindingError(EXIT_INVALID, f"{source} is not valid JSON: {exc}") from exc
    kind = doc.get("kind") if isinstance(doc, dict) else None
    if kind not in EVIDENCE_COMMANDS:
        raise FindingError(EXIT_INVALID, f"{source} is not a geometry or contents document (kind: {kind!r})")
    problems = validate(kind, doc)
    if problems:
        raise FindingError(EXIT_INVALID, f"{source} is invalid: {problems[0].path}: {problems[0].message}")
    if doc["file"] != file:
        raise FindingError(EXIT_INVALID, f"{source}: its file is '{doc['file']}', not '{file}' (--file)")
    expected = file_name(kind, doc, row["sha256"], raw)
    name = Path(source).name
    if name != expected:
        given, wanted = NAME.match(name), NAME.match(expected)
        if given and wanted and given["prefix"] == wanted["prefix"]:
            raise FindingError(
                EXIT_INVALID,
                f"{source} changed after it was saved (its bytes hash to {content_hash(raw)}, its name "
                f"says {given['content']}): a saved file is never edited; save the query again with "
                f"`{redo_command(work, kind, file, doc['query'])}`",
            )
        raise FindingError(
            EXIT_INVALID,
            f"{source} was not saved for this version of {file} (or its query or file name was edited): "
            f"its name starts {GEOMETRY_DIR}/{wanted['prefix'] if wanted else expected}; run "
            f"`{redo_command(work, kind, file, doc['query'])}`",
        )
    if sheet is not None and not _covers(doc, sheet):
        raise FindingError(EXIT_INVALID, f"the query of {source} does not cover sheet {sheet}")
    listed = _document_items(doc)
    missing = [i for i in items if i not in listed]
    if missing:
        hint = ""
        if kind == "geometry" and not doc["query"]["detail"]:
            hint = ": a geometry document lists item ids only when saved with --detail"
        elif kind == "contents" and doc["outlines_total"] > len(doc["outlines"]):
            hint = ": the outline list was cut by --max"
        raise FindingError(EXIT_INVALID, f"items not in {source}: {_shown(missing)}{hint}")
    if sheet is not None and kind == "geometry":  # a contents document holds one sheet, which _covers checked
        elsewhere = [
            f"{i} (on {listed[i].get('sheet') or 'no sheet'})"
            for i in items
            if listed[i].get("sheet") != sheet
        ]
        if elsewhere:
            raise FindingError(
                EXIT_INVALID, f"items of {source} not on sheet {sheet} (--sheet): {_shown(elsewhere)}"
            )
    _check_claims(source, doc, listed, items, claims)
    if value is not None:
        loose = _unbacked_numbers(value, claims, float(doc["query"]["tol"]), entry_texts or [])
        if loose:
            shown = ", ".join(f"{n:g}" for n in loose)
            raise FindingError(
                EXIT_INVALID,
                f"--value holds numbers no --claim or cited entry backs: {shown}: add a --claim for each "
                "(symbols, short, long, diameter, count), cite the entry that prints it, or drop the number",
            )
    return {
        "source": source,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "command": kind,
        "query": doc["query"],
        "items": [_snapshot(listed[i]) for i in items],
    }


def _evidence_reasons(work: Path, finding: dict[str, Any]) -> list[dict[str, str]]:
    """Why the saved file of a finding's evidence no longer backs it: missing or changed (else empty). Only a
    file that is not found is `evidence_missing`; a file the system refuses (held by another process, no
    permission) raises FindingError (3): a transient refusal never makes a finding stale."""
    evidence = finding.get("evidence")
    if evidence is None:
        return []
    try:
        digest = hashlib.sha256((work / evidence["source"]).read_bytes()).hexdigest()
    except (FileNotFoundError, NotADirectoryError):
        return [{"reason": "evidence_missing", "detail": f"{evidence['source']} is missing"}]
    except OSError as exc:
        raise FindingError(EXIT_ENV, f"cannot read {evidence['source']}: {exc}") from exc
    if digest != evidence["sha256"]:
        return [
            {
                "reason": "evidence_changed",
                "detail": f"{evidence['source']} content changed since the finding was recorded",
            }
        ]
    return []


def _stale_reasons(
    inv: Inventory, finding: dict[str, Any], current: dict[str, str], table: FontEncodingTable
) -> list[dict[str, str]]:
    """Every reason a finding is stale (empty when it is not): `stale` is true exactly when there is one."""
    reasons: list[dict[str, str]] = []
    now = current.get(finding["file"])
    if now != finding["file_sha256"]:
        detail = (
            f"{finding['file']} is no longer in the inventory"
            if now is None
            else f"drawing re-intaken: inventory sha256 of {finding['file']} is now {now[:12]}, "
            f"the finding was recorded at {finding['file_sha256'][:12]}"
        )
        reasons.append({"reason": "drawing_changed", "detail": detail})
    if _knowledge_changed(finding, table):
        reasons.append(
            {"reason": "knowledge_changed", "detail": "a font-encoding row it was decoded with has changed"}
        )
    reasons.extend(_evidence_reasons(inv.work, finding))
    return reasons


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
    source: str | None = None,
    items: list[str] | None = None,
    claims: list[str] | None = None,
    knowledge: FontEncodingTable | None = None,
    part: str | None = None,
) -> dict[str, str]:
    """Record one finding (see the module docstring). `part`: the part (block x member family) it belongs
    to, required once the work folder has parts/manifest.json (_checked_part). `source`, `items`: the saved
    geometry or contents
    document and the item ids of a measured finding (or of a cross_check against a measurement). `claims`:
    `KEY=VALUE` strings (symbols, short, long, diameter, count) every cited item must back. `knowledge`:
    the font-encoding table whose rows are recorded in decoded_by (default: the shipped one). Raises
    FindingError."""
    if kind not in KINDS:
        raise FindingError(EXIT_USAGE, f"unknown kind '{kind}': choose from {', '.join(KINDS)}")
    if confidence is not None and confidence not in ("low", "medium"):
        raise FindingError(
            EXIT_USAGE, "--confidence is low or medium; 'high' comes only from an engineer answer"
        )
    field_map = _parse_fields(fields or [])
    question_ids = list(dict.fromkeys(questions or []))
    claim_map = _parse_claims(claims or [])
    _usage_checks(kind, sheet, entries, value, field_map, question_ids, note, source, items, claim_map)

    inv = _inventory(work_dir)
    work = inv.work
    part = _checked_part(work, part)
    _refuse_locked(work, [part])
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
    texts = [e["display_text"] for e in cited]
    evidence = (
        None
        if source is None
        else _evidence(
            work,
            row,
            file,
            sheet,
            source,
            items or [],
            claim_map,
            value if kind == "measured" else None,
            texts,
        )
    )
    final_confidence = _confidence(kind, cited, confidence, claim_map)
    table = _table(knowledge)

    doc = _load_doc(work, inv.doc["project_id"]) or _empty(inv.doc["project_id"])
    sha = row["sha256"]
    cited_record = [{"id": e["id"], "display_text": e["display_text"]} for e in cited]
    for old in doc["findings"]:
        if old["status"] != "active" or old["file"] != file or old["file_sha256"] != sha:
            continue
        if _knowledge_changed(old, table) or _evidence_reasons(work, old):
            continue  # stale like a changed file: neither a duplicate nor in the way
        same = (
            old["kind"] == kind
            and old["sheet"] == sheet
            and [e["id"] for e in old["entries"]] == entries
            and old["value"] == value
            and old["fields"] == field_map
            and old.get("part") == part
            and sorted(old["questions"]) == sorted(question_ids)
            and old.get("evidence") == evidence
        )
        if same:
            return {"id": old["id"], "status": "already_recorded"}
        if kind == "sheet_class" and old["kind"] == kind and old["sheet"] == sheet:
            owner = f" (part {old['part']})" if old.get("part") else ""
            with_part = f" with --part {old['part']}" if old.get("part") else ""
            raise FindingError(
                EXIT_INVALID,
                f"{old['id']}{owner} already classifies sheet {sheet} as '{old['value']}': "
                f"withdraw it first (`harness finding withdraw`{with_part}) to classify the sheet again",
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
    if evidence is not None:
        finding["evidence"] = evidence
    if note is not None:
        finding["note"] = note.strip()
    if part is not None:
        finding["part"] = part
    doc["findings"].append(finding)
    _write_doc(work, doc)
    return {"id": finding_id, "status": "new"}


# --- withdraw and list ------------------------------------------------------------------------------


def withdraw_finding(
    work_dir: Path | str, finding_id: str, reason: str, part: str | None = None
) -> dict[str, str]:
    """Mark a finding withdrawn (kept, with the reason). `part`: checked like `add_finding`'s, and equal to
    the finding's own part when it has one (exit 1); that own part is accepted even when the manifest no
    longer lists it. Raises FindingError."""
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
    owner = found.get("part")
    part = _checked_part(work, part, (owner,) if owner is not None else ())
    _refuse_locked(work, [part, owner])  # the part given and the finding's own
    if owner is not None and part != owner:
        raise FindingError(
            EXIT_INVALID,
            f"{finding_id} belongs to part '{owner}': withdraw it with --part {owner}"
            + ("" if part is None else f" (got --part {part})"),
        )
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
    out["findings"] = []
    for f in doc["findings"]:
        if (kind is not None and f["kind"] != kind) or (file is not None and f["file"] != file):
            continue
        reasons = _stale_reasons(inv, f, current, table)
        listed = {**f, "stale": bool(reasons), "stale_reasons": reasons}
        if reasons and "evidence" in f:  # the way to measure it again (then add the finding, withdraw this)
            ev = f["evidence"]
            listed["redo"] = redo_command(inv.work, ev["command"], f["file"], ev["query"])
        out["findings"].append(listed)
    # the sheets' current classes: a withdrawn or stale class was (or must be) replaced, never counted
    current_classes = [
        f["value"]
        for f in out["findings"]
        if f["kind"] == "sheet_class" and f["status"] == "active" and not f["stale"]
    ]
    out["summary"] = {"by_class": {c: current_classes.count(c) for c in sorted(set(current_classes))}}
    return out


# --- command ----------------------------------------------------------------------------------------


def add_arguments(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="action", required=True, metavar="{add,withdraw,list}")

    p_add = sub.add_parser("add", help="record a finding tied to text-index entries or saved geometry")
    p_add.add_argument("work_dir", help="the --out folder of `harness intake`")
    p_add.add_argument("--kind", required=True, choices=KINDS)
    p_add.add_argument("--file", required=True, help="the drawing file, as listed in inventory.json")
    p_add.add_argument("--sheet", help="the detector sheet id every cited entry is on (model#01)")
    p_add.add_argument(
        "--entries",
        default="",
        help="comma-separated text-index entry ids, e.g. T000123,T000124 (required except for kind measured)",
    )
    p_add.add_argument(
        "--source",
        help=f"measured, cross_check: a document saved by `harness geometry|contents --save`, "
        f"{GEOMETRY_DIR}/<name>.json",
    )
    p_add.add_argument(
        "--items", help="with --source: comma-separated item ids in it (geometry items, contents outlines)"
    )
    p_add.add_argument(
        "--claim",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="with --source: a number of --value that the cited items back; checked against EVERY cited item "
        "(symbols=N exact, short= long= diameter= within the saved query's tol, count=N the number of "
        "cited items); a mismatch exits 1. Every standalone number in a measured --value must be backed by a "
        "--claim or by a number in a cited entry (DC-1, C30, model#06 hold none; d500 is 500; 1700x3200 "
        "is two numbers); a contents outline has no diameter",
    )
    p_add.add_argument("--value", required=True, help="the finding (a quote for note_item)")
    p_add.add_argument(
        "--field",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="note_item topic=, structural_system aspect=, measured quantity=",
    )
    p_add.add_argument(
        "--question", action="append", default=[], metavar="Q-ID", help="a related registry question"
    )
    p_add.add_argument("--confidence", choices=("low", "medium"), help="lower than the entries' minimum")
    p_add.add_argument("--note", help="free remark (required for sheet class 'other')")
    p_add.add_argument("--part", help=PART_HELP)

    p_wd = sub.add_parser("withdraw", help="withdraw a finding (kept, with the reason)")
    p_wd.add_argument("work_dir", help="the --out folder of `harness intake`")
    p_wd.add_argument("finding_id", metavar="F-ID")
    p_wd.add_argument("--reason", required=True)
    p_wd.add_argument("--part", help=PART_HELP + "; must be the finding's own part when it has one")

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
                source=args.source,
                items=None if args.items is None else [i.strip() for i in args.items.split(",") if i.strip()],
                value=args.value,
                claims=args.claim,
                fields=args.field,
                questions=args.question,
                confidence=args.confidence,
                note=args.note,
                part=args.part,
            )
            if result["status"] == "already_recorded":
                print(f"{result['id']}: already recorded", file=sys.stderr)
        elif args.action == "withdraw":
            result = withdraw_finding(args.work_dir, args.finding_id, args.reason, part=args.part)
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
