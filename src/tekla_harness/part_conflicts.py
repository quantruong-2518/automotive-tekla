"""`harness part conflicts W` (E6b, C7): two parts that read one mark, one system or one measurement
differently become one Vietnamese question that tags both parts, so the engineer settles it in questions.md
and `harness status` blocks only those parts.

Parts are the manifest parts of kind member, cross and no_sheet. A part without `values.json` is listed in
`skipped_parts` and contributes nothing (no rows, findings or reader questions); an invalid one stops the
command (exit 1, nothing written). Rules (SPEC-wave3-E6-E9 E6b, DECISIONS section 6):

  1. `part_value_conflict`: rows with a value (`seen`, `asked`) of one key (block, mark or subject
     normalised, field; for `count_plan` also the row's file and sheet, since two parts that read two plan
     sheets count partial sets that add up) that two parts do not read the same (`part_values.same_value`).
     Blocking when the field is in `part_rules.LISTED`.
  2. `part_system_conflict`: active `structural_system` findings of two parts of one block with one
     (file, sheet, aspect) and values that differ. `note_item` never conflicts.
  3. `part_measure_conflict`: two active `measured` findings of two parts that share a cited item, have one
     `fields.quantity` (or none on both) and differ in value; `cross_check` findings are left out.
  4. Rules 2 and 3 are blocking when either finding is cited by a LISTED row of any part.
  5. Duplicates are listed in stdout, never asked: live reader questions of two parts with one (code, file,
     sorted ref sheets); `note_item` findings of two parts that cite one entry.
  6. Messages are fixed templates with sorted parts and ids. The `where` of a ref is built from what survives
     a re-read (rule 1: part, subject, field, sheet or `-`; rule 2: part, file, sheet, aspect; rule 3: part,
     shared item ids), never a row or finding id, so a part re-read with renumbered rows keeps its question
     id and its answer; the row and finding ids are in the message. The questions go through
     `Ledger.sync("part-conflicts", ...)`: a conflict no longer raised becomes obsolete. They are never part
     of `part_hash`; values, findings and reader questions are never edited.

Writes `question-registry.json` then `part-conflicts-questions.json`; stdout is `part-output`
`$defs.conflicts`. `obsolete` lists every part-conflicts question of the registry that is obsolete after this
run (cumulative, by number), so a rerun prints the same.
Exit codes: 0 written (conflicts or not), 1 manifest or `values.json` invalid (the part is named), 2 usage,
3 environment.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from collections.abc import Iterable, Mapping
from itertools import combinations
from pathlib import Path
from typing import Any

from tekla_harness.findings import FindingError, list_findings
from tekla_harness.part_receipts import load_manifest
from tekla_harness.part_rules import LISTED
from tekla_harness.part_values import _read_document, read_values, same_value
from tekla_harness.parts import ManifestAccessError
from tekla_harness.questions import (
    QuestionsError,
    dump_json,
    load_ledger,
    question_group,
    questions_document,
    write_text_atomic,
)
from tekla_harness.schemas import validate
from tekla_harness.sheet_text import ReaderError, load_inventory

EXIT_OK, EXIT_INVALID, EXIT_ENV = 0, 1, 3
PRODUCER = "part-conflicts"
DOCUMENT = "part-conflicts-questions.json"
KINDS = ("member", "cross", "no_sheet")
VALUE_CODE, SYSTEM_CODE, MEASURE_CODE = "part_value_conflict", "part_system_conflict", "part_measure_conflict"
VALUES_STATES = ("seen", "asked")
MAX_ITEMS_SHOWN = 3
ASK_VI = "Giá trị nào đúng theo bản vẽ?"
FIELD_NOUN_VI = {
    "size": "kích thước",
    "thickness": "chiều dày",
    "depth": "chiều cao",
    "length": "chiều dài",
    "spacing": "khoảng cách",
    "count_plan": "số lượng trên mặt bằng",
    "count_schedule": "số lượng trong bảng thống kê",
    "piles_per_member": "số cọc mỗi cấu kiện",
    "level": "cao độ",
    "level_top": "cao độ đỉnh",
    "level_bottom": "cao độ đáy",
    "material": "vật liệu",
    "axes": "trục",
    "start_axes": "trục đầu",
    "end_axes": "trục cuối",
    "other": "giá trị",
}

# (part, row or finding id, value, the stable `where` of its ref, the record it is read in)
Entry = tuple[str, str, str, str, Mapping[str, Any]]


def _number(record_id: str) -> tuple[int, str]:
    """Sort key of a question, finding or row id (`Q-012`, `F-012`, `R012`): its number, then the text."""
    digits = "".join(c for c in record_id if c.isdigit())
    return (int(digits) if digits else 0, record_id)


def _listing(entries: Iterable[Entry]) -> str:
    """`part (ids) 'value'; part (ids) 'value'` over the distinct (part, value) pairs, sorted; the ids are
    the rows or findings of the pair, by number."""
    ids: dict[tuple[str, str], set[str]] = {}
    for part, rid, value, _, _ in entries:
        ids.setdefault((part, value), set()).add(rid)
    return "; ".join(
        f"{part} ({', '.join(sorted(rids, key=_number))}) '{value}'"
        for (part, value), rids in sorted(ids.items())
    )


def _differs(entries: list[Entry]) -> bool:
    """Two entries of two parts that do not say the same."""
    return any(a[0] != b[0] and not same_value(a[2], b[2]) for a, b in combinations(entries, 2))


def _question(code: str, blocking: bool, message: str, entries: list[Entry]) -> dict[str, Any]:
    """The raw question of `entries` (one ref each, by part and id), tagged with their sorted parts. `file`
    is the refs' one file, else null."""
    refs = []
    for _, _, value, where, read in sorted(entries, key=lambda e: (e[0], _number(e[1]))):
        ref: dict[str, Any] = {"file": read.get("file"), "where": where, "found": value}
        if read.get("sheet"):
            ref["sheet"] = read["sheet"]
        refs.append(ref)
    files = {r["file"] for r in refs}
    file = next(iter(files)) if len(files) == 1 and None not in files else None
    raw = question_group(code, blocking, message, refs, file=file)
    raw["parts"] = sorted({e[0] for e in entries})
    return raw


def _load_values(
    work: Path, parts: list[dict[str, Any]]
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """(rows by part id, the parts without values.json). Raises ReaderError (1: a values.json that is not
    valid, every such part named; 3: an unreadable file)."""
    rows: dict[str, list[dict[str, Any]]] = {}
    skipped: list[str] = []
    invalid: list[str] = []
    for part in parts:
        try:
            (work / "parts" / part["id"] / "values.json").stat()
        except (FileNotFoundError, NotADirectoryError):
            skipped.append(part["id"])
            continue
        except OSError as exc:
            raise ReaderError(EXIT_ENV, f"cannot read parts/{part['id']}/values.json ({exc})") from exc
        doc, problems = read_values(work, part["id"], part["kind"])
        if doc is None:
            invalid.append(f"part '{part['id']}': {problems[0].detail}")
        else:
            rows[part["id"]] = doc["rows"]
    if invalid:
        raise ReaderError(EXIT_INVALID, "values.json is not valid, nothing written: " + "; ".join(invalid))
    return rows, sorted(skipped)


def _cited_by_listed(rows: Mapping[str, list[dict[str, Any]]]) -> set[str]:
    """Finding ids cited (by `cites` or a `hand_sum` term) by a row whose field is in LISTED."""
    cited: set[str] = set()
    for part_rows in rows.values():
        for r in part_rows:
            if r["field"] not in LISTED:
                continue
            cited.update(r.get("cites", {}).get("findings", []))
            cited.update(t["finding"] for t in r.get("hand_sum", {}).get("terms", []) if "finding" in t)
    return cited


def _value_conflicts(
    rows: Mapping[str, list[dict[str, Any]]], blocks: Mapping[str, str | None]
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, tuple[str, str]], list[Entry]] = {}
    for part in sorted(rows):
        for r in rows[part]:
            if r["state"] not in VALUES_STATES or r["value"] is None:
                continue
            subject = r["mark"] if "mark" in r else r["subject"]
            name = " ".join(unicodedata.normalize("NFC", subject).casefold().split())
            sheet = r.get("sheet") or ""
            # two parts that read two plan sheets count partial sets: the place is part of a plan count's key
            place = (r.get("file") or "", sheet) if r["field"] == "count_plan" else ("", "")
            key = (blocks[part] or "", name, r["field"], place)
            where = f"{part} {name} {r['field']} {sheet or '-'}"
            groups.setdefault(key, []).append((part, r["row"], r["value"], where, {**r, "subject": subject}))
    out = []
    for (block, _, field, _), entries in sorted(groups.items()):
        if not _differs(entries):
            continue
        subject = min(e[4]["subject"] for e in entries)
        head = " ".join(f"Hai phần ghi khác nhau {FIELD_NOUN_VI[field]} của {subject}".split())
        clause = f" (khối {block})" if block else ""
        message = f"{head}{clause}: {_listing(entries)}. {ASK_VI}"
        out.append(_question(VALUE_CODE, field in LISTED, message, entries))
    return out


def _findings_entries(findings: list[dict[str, Any]], tail: str) -> list[Entry]:
    """One entry per finding; its `where` is the part and `tail` (what the finding says about, not its id)."""
    return [(f["part"], f["id"], f["value"], f"{f['part']} {tail}", f) for f in findings]


def _system_conflicts(
    findings: list[dict[str, Any]], cited: set[str], blocks: Mapping[str, str | None]
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for f in findings:
        if f["kind"] == "structural_system":
            key = (blocks[f["part"]] or "", f["file"], f["sheet"] or "", f["fields"]["aspect"])
            groups.setdefault(key, []).append(f)
    out = []
    for (_, file, sheet, aspect), group in sorted(groups.items()):
        entries = _findings_entries(group, f"{file} {sheet} {aspect}")
        if not _differs(entries):
            continue
        place = f"{file}, tờ {sheet}" if sheet else file
        message = f"Hai phần ghi khác nhau về hệ kết cấu {aspect} ({place}): {_listing(entries)}. {ASK_VI}"
        out.append(_question(SYSTEM_CODE, any(f["id"] in cited for f in group), message, entries))
    return out


def _measure_conflicts(findings: list[dict[str, Any]], cited: set[str]) -> list[dict[str, Any]]:
    measured = sorted((f for f in findings if f["kind"] == "measured"), key=lambda f: _number(f["id"]))
    items = {f["id"]: {i["id"] for i in f.get("evidence", {}).get("items", [])} for f in measured}
    out = []
    for a, b in combinations(measured, 2):
        shared = sorted(items[a["id"]] & items[b["id"]])
        if not shared or a["part"] == b["part"] or same_value(a["value"], b["value"]):
            continue
        if a.get("fields", {}).get("quantity") != b.get("fields", {}).get("quantity"):
            continue  # a count and a size of one item are two quantities: they cannot conflict
        shown = ", ".join(shared[:MAX_ITEMS_SHOWN]) + (" …" if len(shared) > MAX_ITEMS_SHOWN else "")
        entries = _findings_entries([a, b], " ".join(shared))
        message = f"Hai phần đo khác nhau cùng một đối tượng ({shown}): {_listing(entries)}. {ASK_VI}"
        out.append(_question(MEASURE_CODE, a["id"] in cited or b["id"] in cited, message, entries))
    return out


def _duplicates(
    questions: list[dict[str, Any]], findings: list[dict[str, Any]], active: set[str], cited: set[str]
) -> list[dict[str, Any]]:
    """Reader questions and `note_item` findings of two parts that say the same thing: listed, never asked."""
    live = []
    for q in questions:
        parts = sorted(set(q.get("parts", [])) & active)
        sheets = tuple(sorted(r.get("sheet") or "" for r in q["refs"]))
        live.append((q["id"], (q["code"], q["file"], sheets), parts, bool(q["blocking"])))
    out = []
    for (qa, ka, pa, ba), (qb, kb, pb, bb) in combinations(sorted(live, key=lambda x: _number(x[0])), 2):
        if ka == kb and any(x != y for x in pa for y in pb):
            out.append(
                {
                    "kind": "question", "ids": [qa, qb], "parts": sorted(set(pa) | set(pb)),
                    "blocking_differs": ba != bb,
                }
            )  # fmt: skip
    notes = sorted((f for f in findings if f["kind"] == "note_item"), key=lambda f: _number(f["id"]))
    for a, b in combinations(notes, 2):
        read = lambda f: {(f["file"], e["id"]) for e in f["entries"]}  # noqa: E731
        if a["part"] != b["part"] and read(a) & read(b):
            out.append(
                {
                    "kind": "finding", "ids": [a["id"], b["id"]], "parts": sorted({a["part"], b["part"]}),
                    "blocking_differs": (a["id"] in cited) != (b["id"] in cited),
                }
            )  # fmt: skip
    return out


def _conflicts(work: Path) -> dict[str, Any]:
    """The stdout document; writes the registry and the questions document. Raises ReaderError,
    QuestionsError, ManifestAccessError, OSError."""
    inv = load_inventory(work)
    work = inv.work
    manifest = load_manifest(work)
    parts = [p for p in manifest["parts"] if p["kind"] in KINDS]
    rows, skipped = _load_values(work, parts)
    blocks = {p["id"]: p.get("block") if p["kind"] == "member" else None for p in parts}
    try:
        findings_doc = list_findings(work)
    except FindingError as exc:
        raise ReaderError(exc.exit_code, str(exc)) from exc
    findings = [f for f in findings_doc["findings"] if f["status"] == "active" and f.get("part") in rows]
    reader = _read_document(work, "reader-questions.json", "reader-questions") or {"questions": []}
    cited = _cited_by_listed(rows)

    raw = [
        *_value_conflicts(rows, blocks),
        *_system_conflicts(findings, cited, blocks),
        *_measure_conflicts(findings, cited),
    ]
    duplicates = _duplicates(reader["questions"], findings, set(rows), cited)

    hashes = {r["path"]: r["sha256"] for r in inv.doc["files"]}
    ledger = load_ledger(work, inv.doc["project_id"], create=False)
    rendered = ledger.sync(PRODUCER, raw, hashes)
    registered = ledger.registry["questions"].values()
    obsolete = sorted(
        (e["id"] for e in registered if e["producer"] == PRODUCER and e["status"] == "obsolete"),
        key=_number,
    )
    qdoc = questions_document(inv.doc["project_id"], rendered)
    problems = validate("intake", qdoc)
    if problems:
        raise ReaderError(EXIT_INVALID, f"{DOCUMENT} is invalid, nothing written: {problems[0].message}")
    out = {
        "command": "conflicts",
        "conflicts": len(rendered),
        "questions": [
            {"id": q["id"], "code": q["code"], "blocking": q["blocking"], "parts": q["parts"]}
            for q in rendered
        ],
        "duplicates": duplicates,
        "obsolete": obsolete,
        "skipped_parts": skipped,
    }
    problems = validate("part-output", out)
    if problems:
        raise ReaderError(EXIT_INVALID, f"internal error: output is invalid: {problems[0].message}")
    try:
        text = dump_json(qdoc)
        text.encode("utf-8")
    except (ValueError, UnicodeEncodeError) as exc:
        raise ReaderError(EXIT_INVALID, f"{DOCUMENT} cannot be written as strict JSON: {exc}") from exc
    ledger.write()  # the registry is written before any document that uses its ids
    write_text_atomic(work / DOCUMENT, text)
    return out


def run_conflicts(args: argparse.Namespace) -> int:
    """The handler of `harness part conflicts` (the lock is taken by `cli`)."""
    try:
        doc = _conflicts(Path(args.work_dir))
    except ReaderError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except QuestionsError as exc:
        print(f"harness part conflicts: {exc}", file=sys.stderr)
        return exc.exit_code
    except ManifestAccessError as exc:
        print(f"harness part conflicts: {exc}", file=sys.stderr)
        return EXIT_ENV
    except OSError as exc:
        print(f"harness part conflicts: cannot read or write the work folder: {exc}", file=sys.stderr)
        return EXIT_ENV
    print(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False))
    return EXIT_OK
