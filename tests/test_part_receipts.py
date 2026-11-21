"""`part_receipts` (ADR-0019, E5b): the part hash, `W/parts/<X>/receipts.json` (schema `part-receipts`), the
derived part status and the locked-part list (E5b-1), and the writer `harness part receipt` (E5b-2: the
receipts `checked`, `reviewed`, `locked` and `reopened`, their preconditions, `n`, the clock, the schema).

The work folder is the real intake of `_part_fixtures.build_part_work`: the chain all-assembly -> B1-caps ->
B1-piles of its manifest, two findings and two questions of B1-caps, one question of B1-piles. Receipts are
written by hand as valid JSON with hashes the module's own `part_hash` gives.
Each test copies the folder and changes one thing.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import shutil
import types
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from _part_fixtures import (
    INPUT_PART,
    MANIFEST,
    PART,
    REL,
    build_part_work,
    entry_ids,
    entry_row,
    row,
    write_values,
)
from tekla_harness import __version__
from tekla_harness.ask import amend_question, ask_question, withdraw_question
from tekla_harness.cli import main
from tekla_harness.findings import FindingError, add_finding, list_findings, withdraw_finding
from tekla_harness.knowledge import FontEncodingRow, FontEncodingTable
from tekla_harness.receipt import ReceiptError
from tekla_harness.schemas import validate
from tekla_harness.sheet_text import ReaderError

ASSEMBLY = "all-assembly"
AT = "2026-01-01T00:00:00Z"


def mod() -> Any:
    """The module under test, imported when a test runs (the red commit has no module yet)."""
    return importlib.import_module("tekla_harness.part_receipts")


@pytest.fixture(scope="module")
def base_work(tmp_path_factory) -> Path:
    return build_part_work(tmp_path_factory.mktemp("partreceipts"))


@pytest.fixture
def work(base_work, tmp_path) -> Path:
    target = tmp_path / "work"
    shutil.copytree(base_work, target)
    return target


# --- helpers -----------------------------------------------------------------------------------------------


def load(work: Path, rel: str) -> Any:
    return json.loads((work / rel).read_text(encoding="utf-8"))


def edit_json(work: Path, rel: str, change: Callable[[Any], None]) -> None:
    doc = load(work, rel)
    change(doc)
    (work / rel).write_text(json.dumps(doc), encoding="utf-8")


def h(work: Path, part: str = PART) -> str:
    return str(mod().part_hash(work, load(work, str(MANIFEST)), part))


def rec(kind: str, part_hash: str, **fields: Any) -> dict[str, Any]:
    """A receipt (without its `n`). A `reviewed` one carries a passing review, a `locked` one no inputs and a
    `reopened` one a reason, unless `fields` say otherwise."""
    out: dict[str, Any] = {
        "kind": kind, "part_hash": part_hash, "at": AT, "tool_version": "0.1.0",
        "review": None, "reason": None, "inputs": None,
    }  # fmt: skip
    if kind == "reviewed":
        out["review"] = {"round": 1, "verdict": "pass", "file": "parts/x/review/round-1/review.md",
                         "sha256": "a" * 64}  # fmt: skip
    elif kind == "locked":
        out["inputs"] = {}
    elif kind == "reopened":
        out["reason"] = "the sizes changed"
    out.update(fields)
    return out


def write_receipts(
    work: Path, part: str, receipts: list[dict[str, Any]] | str, *, doc_part: str = ""
) -> Path:
    path = work / "parts" / part / "receipts.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(receipts, str):
        path.write_text(receipts, encoding="utf-8")
    else:
        numbered = [{"n": i, **r} for i, r in enumerate(receipts, start=1)]
        doc = {"schema_version": "0.1", "part": doc_part or part, "receipts": numbered}
        path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def lock(work: Path, part: str, inputs: dict[str, str] | None = None) -> None:
    """One `locked` receipt of `part` on its current hash, storing `inputs` (default: the current hash of each
    input its manifest row lists)."""
    manifest = load(work, str(MANIFEST))
    listed = next(p for p in manifest["parts"] if p["id"] == part).get("inputs", [])
    stored = {i: h(work, i) for i in listed} if inputs is None else inputs
    write_receipts(work, part, [rec("locked", h(work, part), inputs=stored)])


def lock_chain(work: Path) -> None:
    """B1-piles, B1-caps and all-assembly locked, each on its current hash with its inputs' hashes."""
    write_values(work, [row()])
    for part in (INPUT_PART, PART, ASSEMBLY):
        lock(work, part)


def status(work: Path, part: str = PART) -> str:
    return str(mod().part_status(work, part))


def question_edit(work: Path, qid: str, change: Callable[[dict[str, Any]], None]) -> None:
    def apply(doc: Any) -> None:
        change(next(q for q in doc["questions"] if q["id"] == qid))

    edit_json(work, "reader-questions.json", apply)


def finding_edit(work: Path, fid: str, change: Callable[[dict[str, Any]], None]) -> None:
    def apply(doc: Any) -> None:
        change(next(f for f in doc["findings"] if f["id"] == fid))

    edit_json(work, "reader-findings.json", apply)


def canonical_hash(doc: dict[str, Any]) -> str:
    payload = json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def expected_hash(work: Path, part: str) -> str:
    """The part hash restated from the files, field by field, as the design lists them."""
    manifest = load(work, str(MANIFEST))
    findings = load(work, "reader-findings.json")["findings"]
    registry = {q["id"]: q["status"] for q in load(work, "question-registry.json")["questions"].values()}
    stale = {f["id"]: f["stale"] for f in list_findings(work)["findings"]}  # the one source: findings
    own_row = next(p for p in manifest["parts"] if p["id"] == part)

    entries = {e["id"]: e for e in load(work, "question-registry.json")["questions"].values()}

    def cited_item(qid: str) -> dict[str, Any]:
        entry = entries.get(qid)
        state = "unknown" if entry is None else "obsolete" if entry["status"] == "obsolete" else "open"
        flag = entry.get("blocking", True) is not False if entry is not None and state == "open" else None
        return {"id": qid, "status": state, "blocking": flag}

    by_id = {f["id"]: f for f in findings}
    cited: set[str] = set()
    cited_systems: set[str] = set()
    read_files: set[str] = set()
    values = work / "parts" / part / "values.json"
    if values.is_file():
        for r in json.loads(values.read_text(encoding="utf-8"))["rows"]:
            cites = r.get("cites", {})
            cited.update(cites.get("questions", []))
            cited_systems.update(cites.get("grid_systems", []))
            for fid in cites.get("findings", []):
                cited.update(by_id.get(fid, {}).get("questions", []))
            read_files.update([r["file"]] if "file" in r else [])
    for f in findings:  # E5b review 3, m1: the questions of an own active finding, cited by a row or not
        if f.get("part") == part and f["status"] == "active":
            cited.update(f["questions"])
    systems_file = work / "grid-systems.json"
    systems = (
        {s["system_id"]: s for s in json.loads(systems_file.read_text(encoding="utf-8"))["systems"]}
        if cited_systems and systems_file.is_file()
        else {}
    )  # E5b review 3, D3: read only when a row cites a system
    for item in [*own_row.get("sheets", []), *own_row.get("clusters", []), *own_row.get("tables", [])]:
        read_files.update([item["file"]] if "file" in item else [])
        read_files.update([item["cluster"]["file"]] if "cluster" in item else [])
    read_files.update(own_row.get("files", []))
    inventory = {r["path"]: r["sha256"] for r in load(work, "inventory.json")["files"]}

    def sha(rel: str) -> str | None:
        path = work / "parts" / part / rel
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None

    own = [f for f in findings if f.get("part") == part]
    doc = {
        "manifest_part": next(p for p in manifest["parts"] if p["id"] == part),
        "findings": sorted(
            (
                {
                    "id": f["id"], "kind": f["kind"], "file": f["file"], "sheet": f["sheet"],
                    "entries": [e["id"] for e in f["entries"]], "value": f["value"], "fields": f["fields"],
                    "questions": f["questions"], "confidence": f["confidence"],
                    "evidence_sha256": f["evidence"]["sha256"] if "evidence" in f else None,
                    "stale": stale[f["id"]],
                }
                for f in own
                if f["status"] == "active"
            ),
            key=lambda f: f["id"],
        ),
        "withdrawn": sorted(f["id"] for f in own if f["status"] == "withdrawn"),
        "questions": sorted(
            (
                {
                    "id": q["id"], "code": q["code"], "blocking": q["blocking"], "message": q["message"],
                    "refs": q["refs"], "places": q.get("places", []),
                    "status": "obsolete" if registry.get(q["id"]) == "obsolete" else "open",
                }
                for q in load(work, "reader-questions.json")["questions"]
                if part in q.get("parts", [])
            ),
            key=lambda q: q["id"],
        ),
        "values_sha256": sha("values.json"),
        "notes_sha256": sha("notes.md"),
        "block": next((b for b in manifest["blocks"] if b["id"] == own_row.get("block")), None),
        "cited_questions": [cited_item(qid) for qid in sorted(cited)],
        "files": {path: inventory.get(path) for path in sorted(read_files)},
        "grid_systems": {sid: systems.get(sid) for sid in sorted(cited_systems)},
    }  # fmt: skip
    return canonical_hash(doc)


def answer(work: Path, qid: str) -> None:
    code = main(["answer", str(work), qid, "--text", "It is 1500x2400.", "--by", "eng", "--role", "engineer"])
    assert code == 0


# --- the part hash -----------------------------------------------------------------------------------------


def test_hash_stable_and_unchanged_by_an_answer(work):
    write_values(work, [row()])
    first = h(work)
    assert len(first) == 64 and first == h(work) == expected_hash(work, PART)
    assert h(work, INPUT_PART) == expected_hash(work, INPUT_PART) != first
    assert h(work, "scout") == expected_hash(work, "scout")  # no values.json, no notes.md: both null
    answer(work, "Q-003")  # an answer moves readiness, never the lock
    registry = load(work, "question-registry.json")["questions"]
    assert {q["status"] for q in registry.values() if q["id"] == "Q-003"} == {"answered"}
    assert h(work) == first == expected_hash(work, PART)


def test_hash_of_an_unknown_part_is_refused(work):
    with pytest.raises(ReaderError, match="B9-nothing") as caught:
        h(work, "B9-nothing")
    assert caught.value.exit_code == 1


def _add_note_item(w: Path) -> None:
    add_finding(
        w, kind="note_item", file=REL, entries=[entry_ids(w)["D400"]], value="D400", sheet="model#01",
        fields=["topic=other"], part=PART,
    )  # fmt: skip


def _ask_new(w: Path) -> None:
    ask_question(
        w, code="reader_depth_unclear", where="model#01 K-2", found="a value", text="Chiều sâu?", file=REL,
        sheet="model#01", blocking=True, part=PART,
    )  # fmt: skip


def _edit_manifest_row(w: Path) -> None:
    def change(doc: Any) -> None:
        next(p for p in doc["parts"] if p["id"] == PART)["order"] = 7

    edit_json(w, str(MANIFEST), change)


def _append_values(w: Path) -> None:
    path = w / "parts" / PART / "values.json"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")


def _set(key: str, value: Any) -> Callable[[dict[str, Any]], None]:
    def change(record: dict[str, Any]) -> None:
        record[key] = value

    return change


def _measured(digit: str) -> Callable[[dict[str, Any]], None]:
    """Make a finding a `measured` one resting on a saved document whose sha256 is `digit` x 64."""

    def change(finding: dict[str, Any]) -> None:
        finding["kind"] = "measured"
        finding["evidence"] = {
            "source": "geometry/g1.json", "sha256": digit * 64, "command": "geometry", "query": {"tol": 1},
            "items": [{"id": "G-0123456789"}],
        }  # fmt: skip

    return change


CHANGES: dict[str, Callable[[Path], object]] = {
    "finding_added": _add_note_item,
    "finding_withdrawn": lambda w: withdraw_finding(w, "F-002", "test", part=PART),
    "finding_value": lambda w: finding_edit(w, "F-001", _set("value", "1600x2400")),
    "finding_confidence": lambda w: finding_edit(w, "F-001", _set("confidence", "low")),
    "finding_fields": lambda w: finding_edit(w, "F-001", _set("fields", {"topic": "cover"})),
    "finding_questions": lambda w: finding_edit(w, "F-001", _set("questions", ["Q-003"])),
    "finding_sheet": lambda w: finding_edit(w, "F-001", _set("sheet", "model#02")),
    "finding_file": lambda w: finding_edit(w, "F-001", _set("file", "plans/other.dxf")),
    "finding_entry": lambda w: finding_edit(w, "F-001", lambda f: f["entries"][0].update(id="T999999")),
    "finding_evidence_added": lambda w: finding_edit(w, "F-001", _measured("b")),
    "finding_evidence_sha256": lambda w: finding_edit(
        w, "F-001", lambda f: f["evidence"].update(sha256="c" * 64)
    ),
    "question_added": _ask_new,
    "question_message_amended": lambda w: amend_question(w, "Q-003", text="Another words.", part=PART),
    "question_places_amended": lambda w: amend_question(w, "Q-003", places=["near K-1"], part=PART),
    "question_withdrawn": lambda w: withdraw_question(w, "Q-003", "test", part=PART),
    "question_blocking": lambda w: question_edit(w, "Q-003", _set("blocking", False)),
    "question_code": lambda w: question_edit(w, "Q-003", _set("code", "reader_other_unclear")),
    "question_refs": lambda w: question_edit(w, "Q-003", lambda q: q["refs"][0].update(found="another")),
    "values_edited": _append_values,
    "values_deleted": lambda w: (w / "parts" / PART / "values.json").unlink(),
    "notes_created": lambda w: (w / "parts" / PART / "notes.md").write_text("scope: K-1\n", encoding="utf-8"),
    "manifest_row": _edit_manifest_row,
}


@pytest.mark.parametrize("name", sorted(CHANGES))
def test_hash_changes_on_finding_question_values_notes_manifest_row(work, name):
    write_values(work, [row()])
    if name == "finding_evidence_sha256":  # a finding that already carries evidence
        finding_edit(work, "F-001", _measured("b"))
    before = h(work)
    CHANGES[name](work)
    assert h(work) != before, name


def test_hash_changes_when_notes_change_and_when_they_go(work):
    notes = work / "parts" / PART / "notes.md"
    notes.parent.mkdir(parents=True, exist_ok=True)
    notes.write_text("scope: K-1\n", encoding="utf-8")
    first = h(work)
    notes.write_text("scope: K-1 and K-2\n", encoding="utf-8")
    second = h(work)
    notes.unlink()
    assert len({first, second, h(work)}) == 3


def test_a_values_or_notes_path_that_is_not_a_regular_file_is_not_an_absent_one(work):
    """m4: a directory there must not hash like a missing file (a bookkeeping part has no values.json)."""
    absent = h(work, SCOUT)
    (work / "parts" / SCOUT / "values.json").mkdir(parents=True)
    with_dir = h(work, SCOUT)
    assert with_dir != absent
    (work / "parts" / SCOUT / "values.json").rmdir()
    assert h(work, SCOUT) == absent
    (work / "parts" / SCOUT / "notes.md").mkdir()
    assert h(work, SCOUT) not in (absent, with_dir)


def test_hash_ignores_other_parts_records(work):
    write_values(work, [row()])
    write_values(work, [row(mark="P-1", sheet="model#02")], INPUT_PART)
    before, before_piles = h(work), h(work, INPUT_PART)
    # B1-piles gains a finding, a question, a values.json, a notes file and a manifest row change
    add_finding(
        work, kind="sheet_class", file=REL, entries=[entry_ids(work)["P-1"]], value="foundation",
        sheet="model#02", part=INPUT_PART,
    )  # fmt: skip
    ask_question(
        work, code="reader_depth_unclear", where="model#02 P-1", found="a value", text="Sâu?", file=REL,
        sheet="model#02", blocking=True, part=INPUT_PART,
    )  # fmt: skip
    write_values(work, [row(mark="P-1", sheet="model#02", field="depth")], INPUT_PART)
    (work / "parts" / INPUT_PART / "notes.md").write_text("scope: P-1\n", encoding="utf-8")
    edit_json(
        work, str(MANIFEST), lambda d: next(p for p in d["parts"] if p["id"] == INPUT_PART).update(order=9)
    )
    assert h(work) == before and h(work, INPUT_PART) != before_piles


def test_a_question_another_part_also_holds_changes_only_the_part_that_gains_it(work):
    """`parts` is never hashed: B1-caps holds Q-003 before and after B1-piles is added to it."""
    before, before_piles = h(work), h(work, INPUT_PART)
    out = ask_question(
        work, code="reader_size_unclear", where="model#01 K-1", found="a value", text="Giá trị nào?",
        file=REL, sheet="model#01", blocking=True, part=INPUT_PART,
    )  # fmt: skip
    assert out["status"] == "already_asked_part_added"
    assert h(work) == before and h(work, INPUT_PART) != before_piles


# --- what the hash also sees: a finding gone stale, the block row, the cited questions (E5b-fix-1, D1) -----


def revise_drawing(w: Path) -> None:
    """The drawing was revised and taken in again: its inventory sha256 is another one."""

    def change(doc: Any) -> None:
        next(f for f in doc["files"] if f["path"] == REL)["sha256"] = "e" * 64

    edit_json(w, "inventory.json", change)


def set_registry_status(w: Path, qid: str, new: str) -> None:
    def change(doc: Any) -> None:
        for entry in doc["questions"].values():
            if entry["id"] == qid:
                entry["status"] = new

    edit_json(w, "question-registry.json", change)


def block_edit(w: Path, change: Callable[[dict[str, Any]], None]) -> None:
    edit_json(w, str(MANIFEST), lambda doc: change(next(b for b in doc["blocks"] if b["id"] == "B1")))


def test_a_revised_drawing_moves_the_hash_of_the_parts_with_a_finding_on_it(work):
    """P3 / C1: the finding is `stale` as `findings.list_findings` says, and that moves the hash."""
    write_values(work, [row()])
    before, piles, scout = h(work), h(work, INPUT_PART), h(work, "scout")
    revise_drawing(work)
    assert [f["stale"] for f in list_findings(work)["findings"]] == [True, True]
    assert h(work) != before and h(work) == expected_hash(work, PART)
    assert h(work, INPUT_PART) != piles  # no finding of B1-piles, but its sheet is in the revised drawing
    assert h(work, "scout") == scout


def test_a_locked_part_is_reopened_when_its_drawing_is_revised(work):
    lock_chain(work)
    assert [status(work, p) for p in (INPUT_PART, PART, ASSEMBLY)] == ["locked"] * 3
    revise_drawing(work)
    assert status(work, INPUT_PART) == "reopened"  # B1-piles reads a sheet of the drawing (E5b-fix-3, C1)
    assert status(work) == "reopened"
    assert status(work, ASSEMBLY) == "stale_input"


def table_of(pattern: str, status: str, decided: str) -> FontEncodingTable:
    row_ = FontEncodingRow(2, pattern, "font_file", "tcvn3", None, status, "e", "tests", "eng", decided)
    return FontEncodingTable((row_,))


def test_a_changed_knowledge_row_moves_the_hash_and_reopens_a_locked_part(work):
    decoded_by = [
        {"source": "knowledge_table", "knowledge_pattern": "VHARIAL.TTF", "row_status": "approved",
         "decided_on": "2026-11-07", "entries": [entry_ids(work)["1500x2400"]]}
    ]  # fmt: skip
    finding_edit(work, "F-001", _set("decoded_by", decoded_by))
    write_values(work, [row()])
    known = table_of("VHARIAL.TTF", "approved", "2026-11-07")
    decided_again = table_of("VHARIAL.TTF", "approved", "2026-12-01")
    base = mod().part_hash(work, load(work, str(MANIFEST)), PART, knowledge=known)
    same = table_of("VHARIAL.TTF", "approved", "2026-11-07")
    assert mod().part_hash(work, load(work, str(MANIFEST)), PART, knowledge=same) == base
    assert mod().part_hash(work, load(work, str(MANIFEST)), PART, knowledge=decided_again) != base
    lock(work, INPUT_PART)  # no finding: its hash does not depend on the table
    stored = {INPUT_PART: h(work, INPUT_PART)}
    write_receipts(
        work, PART, [rec("locked", base, inputs=stored)]
    )  # a lock on the table it was decoded with
    assert mod().PartStates(work, knowledge=known).status(PART) == "locked"
    assert mod().PartStates(work, knowledge=decided_again).status(PART) == "reopened"
    assert mod().part_status(work, PART, knowledge=decided_again) == "reopened"


def test_a_changed_block_row_moves_the_hash_of_its_parts(work):
    """P5 / C1: `part check` reads the block's `grid_system_ids`; the part's own row does not hold them."""
    before = {p: h(work, p) for p in (INPUT_PART, PART, "scout", ASSEMBLY)}
    block_edit(work, lambda b: b.update(grid_system_ids=["S001"]))
    assert h(work) != before[PART] and h(work) == expected_hash(work, PART)
    assert h(work, INPUT_PART) != before[INPUT_PART]  # the same block
    assert h(work, "scout") == before["scout"] and h(work, ASSEMBLY) == before[ASSEMBLY]  # no block
    again = h(work)
    block_edit(work, lambda b: b.update(origin_note="Block B1: the same grid, said again"))
    assert h(work) != again


def test_a_locked_part_is_reopened_when_its_block_changes(work):
    lock_chain(work)
    block_edit(work, lambda b: b.update(grid_system_ids=["S001"]))
    assert status(work) == "reopened" and status(work, INPUT_PART) == "reopened"
    assert status(work, ASSEMBLY) == "stale_input"


def cite_questions(w: Path, *ids: str) -> None:
    write_values(w, [row(cites={"findings": ["F-001"], "questions": list(ids)})])


def test_a_cited_producer_question_going_obsolete_moves_the_hash(work):
    registry = {e["id"]: e for e in load(work, "question-registry.json")["questions"].values()}
    assert registry["Q-001"]["producer"] != "reader" and registry["Q-002"]["producer"] != "reader"
    cite_questions(work, "Q-001")
    before = h(work)
    assert before == expected_hash(work, PART)
    set_registry_status(work, "Q-002", "obsolete")  # a question the rows do not cite
    assert h(work) == before
    set_registry_status(work, "Q-001", "obsolete")
    obsolete = h(work)
    assert obsolete != before and obsolete == expected_hash(work, PART)
    set_registry_status(work, "Q-001", "open")
    assert h(work) == before  # back to open: the same hash again


def test_a_cited_question_answered_leaves_the_hash_alone(work):
    cite_questions(work, "Q-001", "Q-003")
    before = h(work)
    answer(work, "Q-003")
    set_registry_status(work, "Q-001", "answered")  # as `harness answer` writes it
    statuses = {e["id"]: e["status"] for e in load(work, "question-registry.json")["questions"].values()}
    assert statuses["Q-001"] == statuses["Q-003"] == "answered"
    assert h(work) == before  # an answer moves readiness, never the lock


def test_a_cited_question_the_registry_does_not_know_is_hashed_as_unknown(work):
    cite_questions(work, "Q-001", "Q-099")  # an id the registry does not know has a state of its own
    assert h(work) == expected_hash(work, PART)


def test_a_locked_part_is_reopened_when_a_cited_producer_question_goes_obsolete(work):
    cite_questions(work, "Q-001")
    for part in (INPUT_PART, PART, ASSEMBLY):
        lock(work, part)
    assert status(work) == "locked"
    set_registry_status(work, "Q-001", "obsolete")
    assert status(work) == "reopened"


# --- receipts.json -----------------------------------------------------------------------------------------


def test_read_receipts_absent_valid_and_n(work):
    assert mod().read_receipts(work, PART) == []
    first, second = rec("checked", h(work)), rec("reopened", h(work))
    write_receipts(work, PART, [first, second])
    got = mod().read_receipts(work, PART)
    assert [r["n"] for r in got] == [1, 2] and [r["kind"] for r in got] == ["checked", "reopened"]


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        '{"schema_version": "0.1", "part": "B1-caps", "receipts": [], "receipts": []}',  # duplicate key
        '{"schema_version": "0.1", "part": "B1-caps", "receipts": [{"n": 1}]}',
        '{"schema_version": "0.2", "part": "B1-caps", "receipts": []}',
    ],
)
def test_read_receipts_invalid_cases(work, text):
    write_receipts(work, PART, text)
    with pytest.raises(mod().ReceiptsInvalid, match=r"parts/B1-caps/receipts\.json") as caught:
        mod().read_receipts(work, PART)
    assert caught.value.exit_code == 1 and str(work) not in str(caught.value)


def test_read_receipts_of_another_part_n_gaps_and_non_files_are_invalid(work):
    write_receipts(work, PART, [rec("checked", h(work))], doc_part=INPUT_PART)
    with pytest.raises(mod().ReceiptsInvalid, match=INPUT_PART):
        mod().read_receipts(work, PART)
    path = write_receipts(work, PART, [rec("checked", h(work)), rec("checked", h(work))])
    edit_json(work, f"parts/{PART}/receipts.json", lambda d: d["receipts"][1].update(n=3))
    with pytest.raises(mod().ReceiptsInvalid, match="n"):
        mod().read_receipts(work, PART)
    path.unlink()
    path.mkdir()
    with pytest.raises(mod().ReceiptsInvalid, match="not a regular file"):
        mod().read_receipts(work, PART)


def test_a_symbolic_link_at_receipts_json_is_invalid_not_absent(work):
    """m1: a dangling link used to read as "no receipts" and let a write through."""
    folder = work / "parts" / SCOUT
    folder.mkdir(parents=True, exist_ok=True)
    link = folder / "receipts.json"
    try:
        link.symlink_to(work / "nowhere.json")  # dangling
    except OSError:
        pytest.skip("no symbolic links here")
    with pytest.raises(mod().ReceiptsInvalid, match="not a regular file") as caught:
        mod().read_receipts(work, SCOUT)
    assert caught.value.exit_code == 1 and "parts/scout/receipts.json" in str(caught.value)
    with pytest.raises(mod().ReceiptsInvalid):
        mod().locked_parts(work, [SCOUT])
    assert status(work, SCOUT) == "receipts_invalid"
    link.unlink()
    real = write_receipts(work, INPUT_PART, [rec("locked", h(work, INPUT_PART))])
    link.symlink_to(real)  # a link to a valid receipts file is no better
    with pytest.raises(mod().ReceiptsInvalid, match="not a regular file"):
        mod().read_receipts(work, SCOUT)
    with pytest.raises(mod().ReceiptsInvalid):
        mod().locked_parts(work, [SCOUT])


def test_read_receipts_refused_by_the_operating_system_is_exit_3(work, monkeypatch):
    write_receipts(work, PART, [rec("checked", h(work))])
    real = Path.read_bytes

    def refuse(self: Path) -> bytes:
        if self.name == "receipts.json":
            raise PermissionError("denied")
        return real(self)

    monkeypatch.setattr(Path, "read_bytes", refuse)
    with pytest.raises(ReaderError, match=r"receipts\.json") as caught:
        mod().read_receipts(work, PART)
    assert caught.value.exit_code == 3 and not isinstance(caught.value, mod().ReceiptsInvalid)
    with pytest.raises(ReaderError) as caught_status:  # a status does not turn it into a state
        mod().part_status(work, PART)
    assert caught_status.value.exit_code == 3


def test_receipts_example_and_schema(example):
    doc = example("part-receipts")
    assert validate("part-receipts", doc) == []
    assert [r["kind"] for r in doc["receipts"]] == ["checked", "reviewed", "locked", "reopened"]
    assert [r["n"] for r in doc["receipts"]] == [1, 2, 3, 4]

    def broken(change: Callable[[dict[str, Any]], None]) -> list[Any]:
        copy = json.loads(json.dumps(doc))
        change(copy)
        return validate("part-receipts", copy)

    assert broken(lambda d: d.update(stray=1))
    assert broken(lambda d: d["receipts"][0].update(stray=1))
    assert broken(lambda d: d["receipts"][0].update(kind="approved"))
    assert broken(lambda d: d["receipts"][0].update(part_hash="abc"))
    assert broken(lambda d: d["receipts"][0].update(at="2026-01-01 00:00:00"))
    assert broken(lambda d: d["receipts"][0].update(n=0))
    assert broken(lambda d: d["receipts"][0].pop("tool_version"))
    assert broken(lambda d: d["receipts"][1].update(review=None))  # reviewed needs its review
    assert broken(lambda d: d["receipts"][1]["review"].update(verdict="maybe"))
    assert broken(lambda d: d["receipts"][1]["review"].update(round=0))
    assert broken(lambda d: d["receipts"][2].update(inputs=None))  # locked needs its inputs
    assert broken(lambda d: d["receipts"][2]["inputs"].update({"bad id!": "a" * 64}))
    assert broken(lambda d: d["receipts"][2]["inputs"].update({"B1-piles": "xyz"}))
    assert broken(lambda d: d["receipts"][3].update(reason=None))  # reopened needs its reason
    assert broken(lambda d: d["receipts"][3].update(reason=""))
    assert broken(lambda d: d.update(part="bad id!"))
    # m10: the fields of another kind are null, not only optional
    assert broken(lambda d: d["receipts"][0].update(review=d["receipts"][1]["review"]))  # checked + review
    assert broken(lambda d: d["receipts"][2].update(reason="why"))  # locked + reason
    assert broken(lambda d: d["receipts"][3].update(inputs={}))  # reopened + inputs
    assert broken(lambda d: d["receipts"][1].update(inputs={}))  # reviewed + inputs
    assert not broken(lambda d: d["receipts"][0].update(review=None, reason=None, inputs=None))
    assert validate("part-receipts", {**doc, "receipts": []}) == []


# --- the derived status ------------------------------------------------------------------------------------


def test_status_reading_checked_reviewed_locked(work):
    write_values(work, [row()])
    current, other = h(work), "c" * 64
    assert status(work) == "reading"
    write_receipts(work, PART, [rec("checked", other)])  # checked on an older hash
    assert status(work) == "reading"
    write_receipts(work, PART, [rec("checked", current)])
    assert status(work) == "checked"
    write_receipts(work, PART, [rec("checked", current), rec("reviewed", current)])
    assert status(work) == "reviewed"
    fix = {"round": 1, "verdict": "fix", "file": "parts/x/review/round-1/review.md", "sha256": "a" * 64}
    write_receipts(work, PART, [rec("checked", current), rec("reviewed", current, review=fix)])
    assert status(work) == "checked"  # a review that asks for a fix is not a pass
    write_receipts(work, PART, [rec("checked", current), rec("reviewed", other)])
    assert status(work) == "checked"  # a review of another hash does not count
    write_receipts(work, PART, [rec("checked", current), rec("reviewed", current)])
    write_receipts(work, INPUT_PART, [rec("locked", h(work, INPUT_PART))])
    assert status(work, INPUT_PART) == "locked"
    stored = {INPUT_PART: h(work, INPUT_PART)}
    write_receipts(
        work, PART,
        [rec("checked", current), rec("reviewed", current), rec("locked", current, inputs=stored)],
    )  # fmt: skip
    assert status(work) == "locked"
    write_receipts(work, PART, [rec("reopened", current)])  # a reopened part with nothing after it
    assert status(work) == "reopened"


def test_status_reads_only_the_receipts_after_the_last_reopened_or_locked(work):
    write_values(work, [row()])
    current = h(work)
    lock(work, INPUT_PART)
    locked = rec("locked", current, inputs={INPUT_PART: h(work, INPUT_PART)})
    before = [rec("checked", current), rec("reviewed", current), locked]
    write_receipts(work, PART, [*before, rec("reopened", current)])
    assert status(work) == "reopened"
    write_receipts(work, PART, [*before, rec("reopened", current), rec("checked", current)])
    assert status(work) == "checked"  # the old review was before the lock and the reopening
    write_receipts(work, PART, [*before, rec("reopened", current), rec("reviewed", current)])
    assert status(work) == "reviewed"
    write_receipts(work, PART, [*before, rec("reopened", current), rec("reviewed", current), locked])
    assert status(work) == "locked"


def test_hash_change_after_lock_is_reopened(work):
    lock_chain(work)
    assert [status(work, p) for p in (INPUT_PART, PART, ASSEMBLY)] == ["locked"] * 3
    answer(work, "Q-003")  # an answer leaves the lock alone
    assert status(work) == "locked"
    values = work / "parts" / PART / "values.json"
    original = values.read_bytes()
    values.write_bytes(original + b"\n")  # a hand edit after the lock
    assert status(work) == "reopened"
    values.write_bytes(original)
    assert status(work) == "locked"
    from tekla_harness.findings import FindingError

    with pytest.raises(FindingError, match="is locked"):  # a locked part refuses a new finding
        _add_note_item(work)
    assert status(work) == "locked"
    before = h(work)
    receipts = load(work, f"parts/{PART}/receipts.json")["receipts"]
    write_receipts(work, PART, [*(_strip(r) for r in receipts), rec("reopened", before)])
    _add_note_item(work)  # a new finding of the reopened part moves its hash
    assert h(work) != before
    assert status(work) == "reopened"


def test_reopened_input_makes_dependants_stale_transitively(work):
    lock_chain(work)
    piles_hash = h(work, INPUT_PART)
    receipts = load(work, f"parts/{INPUT_PART}/receipts.json")["receipts"]
    write_receipts(work, INPUT_PART, [*(_strip(r) for r in receipts), rec("reopened", piles_hash)])
    assert status(work, INPUT_PART) == "reopened"
    assert status(work, PART) == "stale_input"
    assert status(work, ASSEMBLY) == "stale_input"  # transitively: its input is not locked
    # B1-piles is locked again, on a changed hash: B1-caps stored the old one
    write_values(work, [row(mark="P-1", sheet="model#02")], INPUT_PART)
    lock(work, INPUT_PART)
    assert status(work, INPUT_PART) == "locked" and h(work, INPUT_PART) != piles_hash
    assert status(work, PART) == "stale_input" and status(work, ASSEMBLY) == "stale_input"
    lock(work, PART)  # B1-caps is locked again over the new input hash: its own hash did not move
    assert status(work, PART) == "locked" and status(work, ASSEMBLY) == "locked"
    # B1-piles reopened and locked again on the same hash (a reopened part that changed nothing)
    lock(work, INPUT_PART)
    assert status(work, PART) == "locked"


def _strip(receipt: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in receipt.items() if k != "n"}


def test_an_input_cycle_is_stale_input(work):
    write_values(work, [row()])

    def cycle(doc: Any) -> None:
        by_id = {p["id"]: p for p in doc["parts"]}
        by_id[INPUT_PART]["inputs"] = [PART]  # B1-piles <-> B1-caps

    edit_json(work, str(MANIFEST), cycle)
    write_receipts(work, INPUT_PART, [rec("locked", h(work, INPUT_PART), inputs={PART: h(work, PART)})])
    write_receipts(work, PART, [rec("locked", h(work), inputs={INPUT_PART: h(work, INPUT_PART)})])
    assert status(work) == "stale_input" and status(work, INPUT_PART) == "stale_input"
    assert status(work, ASSEMBLY) == "reading"  # no receipts: the cycle is not its business


def test_an_input_the_manifest_does_not_list_is_stale_input(work):
    lock_chain(work)
    write_receipts(work, PART, [rec("locked", h(work), inputs={})])  # no stored hash for B1-piles
    assert status(work) == "stale_input"


def test_receipts_invalid_is_a_status(work):
    lock_chain(work)
    write_receipts(work, INPUT_PART, "not json")
    assert status(work, INPUT_PART) == "receipts_invalid"
    assert status(work, PART) == "stale_input"  # an input that is not locked
    assert status(work, ASSEMBLY) == "stale_input"
    write_receipts(work, INPUT_PART, [rec("checked", h(work, INPUT_PART))], doc_part=PART)  # another part's
    assert status(work, INPUT_PART) == "receipts_invalid"


def test_status_needs_a_valid_manifest_and_a_listed_part(work):
    with pytest.raises(ReaderError, match="B9-nothing") as unknown:
        status(work, "B9-nothing")
    assert unknown.value.exit_code == 1
    (work / MANIFEST).write_text("not json", encoding="utf-8")
    with pytest.raises(ReaderError, match=r"manifest\.json") as invalid:
        status(work)
    assert invalid.value.exit_code == 1


# --- locked_parts ------------------------------------------------------------------------------------------


def test_locked_parts_reads_the_latest_receipt_not_the_status(work):
    assert mod().locked_parts(work, [PART, INPUT_PART]) == []
    lock_chain(work)
    assert mod().locked_parts(work, [ASSEMBLY, PART, "scout", INPUT_PART]) == [ASSEMBLY, PART, INPUT_PART]
    # a hand edit of values.json after the lock: the status is reopened, the write refusal still holds
    values = work / "parts" / PART / "values.json"
    values.write_bytes(values.read_bytes() + b"\n")
    assert status(work) == "reopened" and mod().locked_parts(work, [PART]) == [PART]
    values.write_bytes(values.read_bytes()[:-1])
    # a `stale_input` part is locked too: its input was reopened, its own receipt is still `locked`
    write_receipts(
        work, INPUT_PART, [rec("locked", h(work, INPUT_PART)), rec("reopened", h(work, INPUT_PART))]
    )
    assert status(work) == "stale_input" and mod().locked_parts(work, [PART, INPUT_PART]) == [PART]


def test_locked_parts_reopened_after_locked_is_not_locked(work):
    current = h(work, PART)
    write_receipts(work, PART, [rec("checked", current), rec("locked", current), rec("reopened", current)])
    assert mod().locked_parts(work, [PART]) == []
    write_receipts(work, PART, [rec("locked", current), rec("reopened", current), rec("locked", current)])
    assert mod().locked_parts(work, [PART]) == [PART]


def test_locked_parts_with_unreadable_receipts_raises(work, monkeypatch):
    lock(work, INPUT_PART)
    write_receipts(work, PART, "not json")
    with pytest.raises(mod().ReceiptsInvalid, match=r"parts/B1-caps/receipts\.json"):
        mod().locked_parts(work, [INPUT_PART, PART])
    write_receipts(work, PART, [rec("locked", h(work))])
    real = Path.read_bytes

    def refuse(self: Path) -> bytes:
        if self.name == "receipts.json":
            raise PermissionError("denied")
        return real(self)

    monkeypatch.setattr(Path, "read_bytes", refuse)
    with pytest.raises(ReaderError, match=r"receipts\.json") as caught:
        mod().locked_parts(work, [PART])
    assert caught.value.exit_code == 3


# --- the writer: `harness part receipt` --------------------------------------------------------------------

SCOUT = "scout"  # a bookkeeping part with no rows: `part check` passes it, whatever the text rules become
SCOUT_REL = f"parts/{SCOUT}/receipts.json"


def rcpt(
    capsys: Any, work: Path, part: str, kind: str, *flags: str
) -> tuple[int, dict[str, Any] | None, str]:
    """Run `harness part receipt`; returns (exit code, parsed stdout or None, stderr)."""
    code = main(["part", "receipt", str(work), "--part", part, "--kind", kind, *flags])
    cap = capsys.readouterr()
    return code, (json.loads(cap.out) if cap.out else None), cap.err


def receipt_bytes(work: Path, part: str = SCOUT) -> bytes | None:
    path = work / "parts" / part / "receipts.json"
    return path.read_bytes() if path.exists() else None


def review_file(
    work: Path, part: str = SCOUT, n: int = 1, text: str = "Round review: nothing found.\n"
) -> Path:
    path = work / "parts" / part / "review" / f"round-{n}" / "review.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def review_flags(work: Path, part: str = SCOUT, n: int = 1, verdict: str = "pass") -> list[str]:
    return ["--review", str(work / "parts" / part / "review" / f"round-{n}" / "review.md"),
            "--round", str(n), "--verdict", verdict]  # fmt: skip


def kinds(work: Path, part: str = SCOUT) -> list[str]:
    return [r["kind"] for r in mod().read_receipts(work, part)]


def reviewed(capsys: Any, work: Path, part: str = SCOUT, verdict: str = "pass", n: int = 1) -> None:
    """`checked` (already recorded is fine) and a `reviewed` receipt of round `n`, through the command."""
    assert rcpt(capsys, work, part, "checked")[0] == 0
    review_file(work, part, n)
    assert rcpt(capsys, work, part, "reviewed", *review_flags(work, part, n, verdict))[0] == 0


def fake_check(problems: list[dict[str, Any]], digest: str | None = None) -> Callable[..., dict[str, Any]]:
    """A `check_part` that reports `problems` and the part's current hash (or `digest`), as the real one."""
    calls: list[tuple[Any, ...]] = []

    def check(work_dir: Any, part: str) -> dict[str, Any]:
        calls.append((work_dir, part))
        current = digest or h(Path(work_dir), part)
        return {"command": "check", "part": part, "hash": current, "ok": not problems, "problems": problems}

    check.calls = calls  # type: ignore[attr-defined]
    return check


PROBLEM = {"code": "row_state", "row": "R001", "id": None, "detail": "a made-up problem"}


def test_checked_runs_the_check_and_refuses_problems(capsys, work, monkeypatch):
    code, out, _ = rcpt(capsys, work, SCOUT, "checked")
    assert code == 0 and out and validate("part-output", out) == []
    assert (out["command"], out["part"], out["kind"], out["written"]) == ("receipt", SCOUT, "checked", True)
    assert out["refused"] is None and out["problems"] == []
    receipt = out["receipt"]
    assert receipt["n"] == 1 and receipt["part_hash"] == h(work, SCOUT)
    assert (receipt["review"], receipt["reason"], receipt["inputs"]) == (None, None, None)
    assert mod().read_receipts(work, SCOUT) == [receipt]
    # a part whose own check fails: the check's problems, nothing written
    code, out, err = rcpt(capsys, work, PART, "checked")
    assert code == 1 and out and validate("part-output", out) == [] and "refused" in err
    assert out["written"] is False and out["receipt"] is None and out["refused"]
    assert [p["code"] for p in out["problems"]] == ["values_invalid"]
    assert receipt_bytes(work, PART) is None
    # the check is really run, and its problems are the output's
    (work / "parts" / SCOUT / "notes.md").write_text("a new hash\n", encoding="utf-8")
    check = fake_check([PROBLEM])
    monkeypatch.setattr("tekla_harness.part_check.check_part", check)
    before = receipt_bytes(work)
    code, out, _ = rcpt(capsys, work, SCOUT, "checked")
    assert code == 1 and out and out["problems"] == [PROBLEM] and out["receipt"] is None
    assert check.calls == [(work, SCOUT)] and receipt_bytes(work) == before


def test_a_part_that_changed_while_it_was_checked_gets_no_receipt(capsys, work, monkeypatch):
    """m3: the receipt's hash must be the one the check saw."""
    for kind in ("checked", "locked"):
        monkeypatch.setattr("tekla_harness.part_check.check_part", fake_check([], "f" * 64))
        before = receipt_bytes(work)
        code, out, _ = rcpt(capsys, work, SCOUT, kind)
        assert code == 1 and out and out["written"] is False and out["receipt"] is None, kind
        assert "changed while it was checked" in out["refused"] and out["problems"] == [], kind
        assert receipt_bytes(work) == before, kind
    monkeypatch.setattr("tekla_harness.part_check.check_part", fake_check([]))
    assert rcpt(capsys, work, SCOUT, "checked")[0] == 0  # the same check on the current hash passes


def test_checked_is_refused_on_a_locked_part_until_it_is_reopened(capsys, work):
    write_receipts(work, SCOUT, [rec("locked", h(work, SCOUT))])
    before = receipt_bytes(work)
    code, out, _ = rcpt(capsys, work, SCOUT, "checked")
    assert code == 1 and out and out["written"] is False and out["receipt"] is None
    assert "reopen" in out["refused"] and out["problems"] == []
    assert receipt_bytes(work) == before
    assert rcpt(capsys, work, SCOUT, "reopened", "--reason", "sizes changed")[0] == 0
    code, out, _ = rcpt(capsys, work, SCOUT, "checked")
    assert code == 0 and out and out["receipt"]["n"] == 3


def test_reviewed_needs_checked_on_current_hash_and_the_round_path(capsys, work, monkeypatch):
    review = review_file(work)
    flags = review_flags(work)
    code, out, _ = rcpt(capsys, work, SCOUT, "reviewed", *flags)  # no checked yet
    assert code == 1 and out and out["refused"] and out["receipt"] is None
    assert receipt_bytes(work) is None
    assert rcpt(capsys, work, SCOUT, "checked")[0] == 0
    code, out, _ = rcpt(capsys, work, SCOUT, "reviewed", *flags)
    assert code == 0 and out and validate("part-output", out) == []
    stored = out["receipt"]
    assert stored["n"] == 2 and stored["kind"] == "reviewed" and stored["part_hash"] == h(work, SCOUT)
    assert stored["review"] == {
        "round": 1, "verdict": "pass", "file": "parts/scout/review/round-1/review.md",
        "sha256": hashlib.sha256(review.read_bytes()).hexdigest(),
    }  # fmt: skip
    assert (stored["reason"], stored["inputs"]) == (None, None)
    # a relative path to the same file is the same file
    monkeypatch.chdir(work)
    code, out, _ = rcpt(capsys, work, SCOUT, "reviewed", "--review", "parts/scout/review/round-1/review.md",
                        "--round", "1", "--verdict", "pass")  # fmt: skip
    assert code == 0 and out and out["written"] is False


def test_reviewed_refuses_a_wrong_review_path(capsys, work):
    assert rcpt(capsys, work, SCOUT, "checked")[0] == 0
    review_file(work, n=1)
    other = review_file(work, n=2)
    stray = work / "parts" / SCOUT / "review" / "round-1" / "notes.md"
    stray.write_text("x", encoding="utf-8")
    folder = work / "parts" / SCOUT / "review" / "round-3" / "review.md"
    folder.mkdir(parents=True)
    wrong = [
        ["--review", str(other), "--round", "1", "--verdict", "pass"],  # the file of round 2 named as round 1
        ["--review", str(stray), "--round", "1", "--verdict", "pass"],  # not review.md
        ["--review", str(work / "parts" / SCOUT / "review" / "round-4" / "review.md"), "--round", "4",
         "--verdict", "pass"],  # not there
        ["--review", str(folder), "--round", "3", "--verdict", "pass"],  # not a regular file
        ["--review", str(work / "parts" / INPUT_PART / "review" / "round-1" / "review.md"), "--round", "1",
         "--verdict", "pass"],  # another part's folder
    ]  # fmt: skip
    before = receipt_bytes(work)
    for flags in wrong:
        code, out, _ = rcpt(capsys, work, SCOUT, "reviewed", *flags)
        assert code == 1 and out and out["written"] is False and out["refused"], flags
        assert receipt_bytes(work) == before, flags
    # the right one is still accepted
    assert rcpt(capsys, work, SCOUT, "reviewed", *review_flags(work, SCOUT, 1))[0] == 0


def test_reviewed_refuses_a_symlinked_review_file(capsys, work):
    assert rcpt(capsys, work, SCOUT, "checked")[0] == 0
    target = work / "elsewhere.md"
    target.write_text("review", encoding="utf-8")
    link = work / "parts" / SCOUT / "review" / "round-1" / "review.md"
    link.parent.mkdir(parents=True)
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("no symbolic links here")
    code, out, _ = rcpt(capsys, work, SCOUT, "reviewed", *review_flags(work))
    assert code == 1 and out and out["receipt"] is None


def test_reviewed_refuses_a_review_folder_reached_through_a_symbolic_link(capsys, work):
    """m2: the review file must live in the work folder, not behind a linked folder."""
    assert rcpt(capsys, work, SCOUT, "checked")[0] == 0
    outside = work.parent / "outside"
    (outside).mkdir()
    (outside / "review.md").write_text("review", encoding="utf-8")
    link = work / "parts" / SCOUT / "review" / "round-1"
    link.parent.mkdir(parents=True)
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("no symbolic links here")
    before = receipt_bytes(work)
    code, out, _ = rcpt(capsys, work, SCOUT, "reviewed", *review_flags(work))
    assert code == 1 and out and out["receipt"] is None and out["written"] is False
    assert "symbolic link" in out["refused"] and "parts/scout/review/round-1" in out["refused"]
    assert receipt_bytes(work) == before


def test_reviewed_needs_a_checked_receipt_of_the_current_hash_after_the_last_reopened(capsys, work):
    current = h(work, SCOUT)
    review_file(work)
    flags = review_flags(work)
    # a checked receipt of an older hash does not count
    write_receipts(work, SCOUT, [rec("checked", "c" * 64)])
    assert rcpt(capsys, work, SCOUT, "reviewed", *flags)[0] == 1
    # a checked receipt from before the last reopened does not count (mutant: look at the whole history)
    write_receipts(
        work, SCOUT,
        [rec("checked", current), rec("reviewed", current), rec("locked", current), rec("reopened", current)],
    )  # fmt: skip
    before = receipt_bytes(work)
    code, out, _ = rcpt(capsys, work, SCOUT, "reviewed", *flags)
    assert code == 1 and out and out["refused"] and receipt_bytes(work) == before
    assert rcpt(capsys, work, SCOUT, "checked")[0] == 0  # a new check after the reopening: now it counts
    assert rcpt(capsys, work, SCOUT, "reviewed", *flags)[0] == 0
    # the part changed after the check: refused
    (work / "parts" / SCOUT / "notes.md").write_text("a note\n", encoding="utf-8")
    review_file(work, n=2)
    before = receipt_bytes(work)
    assert rcpt(capsys, work, SCOUT, "reviewed", *review_flags(work, SCOUT, 2))[0] == 1
    assert receipt_bytes(work) == before


@pytest.mark.parametrize("verdict", ["fix", "engineer"])
def test_reviewed_records_every_verdict(capsys, work, verdict):
    reviewed(capsys, work, verdict=verdict)
    assert mod().read_receipts(work, SCOUT)[-1]["review"]["verdict"] == verdict
    assert status(work, SCOUT) == "checked"


def test_locked_needs_pass_and_locked_inputs(capsys, work, monkeypatch):
    # no review at all
    assert rcpt(capsys, work, SCOUT, "checked")[0] == 0
    before = receipt_bytes(work)
    code, out, _ = rcpt(capsys, work, SCOUT, "locked")
    assert code == 1 and out and out["receipt"] is None and out["refused"] and receipt_bytes(work) == before
    # a review that asks for a fix (mutant: the verdict is not read)
    reviewed(capsys, work, verdict="fix")
    before = receipt_bytes(work)
    code, out, _ = rcpt(capsys, work, SCOUT, "locked")
    assert code == 1 and out and out["receipt"] is None and receipt_bytes(work) == before
    # the check fails now (the text rules grew stricter): refused with the check's problems
    reviewed(capsys, work, verdict="pass", n=2)
    monkeypatch.setattr("tekla_harness.part_check.check_part", fake_check([PROBLEM]))
    before = receipt_bytes(work)
    code, out, _ = rcpt(capsys, work, SCOUT, "locked")
    assert code == 1 and out and out["problems"] == [PROBLEM] and receipt_bytes(work) == before
    monkeypatch.undo()
    # the part changed after the review
    (work / "parts" / SCOUT / "notes.md").write_text("a note\n", encoding="utf-8")
    before = receipt_bytes(work)
    assert rcpt(capsys, work, SCOUT, "locked")[0] == 1 and receipt_bytes(work) == before
    # checked and reviewed again on the new hash: locked, with no inputs
    reviewed(capsys, work, n=3)
    code, out, _ = rcpt(capsys, work, SCOUT, "locked")
    assert code == 0 and out and validate("part-output", out) == []
    stored = out["receipt"]
    assert stored["kind"] == "locked" and stored["inputs"] == {} and stored["part_hash"] == h(work, SCOUT)
    assert (stored["review"], stored["reason"]) == (None, None)
    assert status(work, SCOUT) == "locked"


def test_locked_needs_every_input_part_locked_and_stores_their_hashes(capsys, work):
    # all-assembly lists B1-caps; B1-caps lists B1-piles
    reviewed(capsys, work, ASSEMBLY)
    before = receipt_bytes(work, ASSEMBLY)
    code, out, _ = rcpt(capsys, work, ASSEMBLY, "locked")
    assert code == 1 and out and out["receipt"] is None and PART in out["refused"]
    assert receipt_bytes(work, ASSEMBLY) == before
    write_values(work, [row()])
    lock(work, INPUT_PART)
    write_receipts(
        work, PART, [rec("locked", h(work, PART), inputs={INPUT_PART: "d" * 64})]
    )  # stale input hash
    assert status(work, PART) == "stale_input"
    assert rcpt(capsys, work, ASSEMBLY, "locked")[0] == 1
    lock(work, PART)
    assert status(work, PART) == "locked"
    code, out, _ = rcpt(capsys, work, ASSEMBLY, "locked")
    assert code == 0 and out and out["receipt"]["inputs"] == {PART: h(work, PART)}
    assert status(work, ASSEMBLY) == "locked"


def test_reopened_needs_reason_and_a_locked_part(capsys, work):
    code, out, _ = rcpt(capsys, work, SCOUT, "reopened", "--reason", "why not")  # nothing to reopen
    assert code == 1 and out and out["receipt"] is None and out["refused"]
    assert receipt_bytes(work) is None
    write_receipts(work, SCOUT, [rec("checked", h(work, SCOUT))])
    assert rcpt(capsys, work, SCOUT, "reopened", "--reason", "why not")[0] == 1  # latest is not `locked`
    write_receipts(work, SCOUT, [rec("locked", h(work, SCOUT))])
    before = receipt_bytes(work)
    for flags in ([], ["--reason", ""], ["--reason", "   "]):
        code, out, _ = rcpt(capsys, work, SCOUT, "reopened", *flags)
        assert code == 2 and out is None and receipt_bytes(work) == before, flags
    code, out, _ = rcpt(capsys, work, SCOUT, "reopened", "--reason", "the cap sizes changed")
    assert code == 0 and out and validate("part-output", out) == []
    stored = out["receipt"]
    assert stored["n"] == 2 and stored["kind"] == "reopened" and stored["reason"] == "the cap sizes changed"
    assert (stored["review"], stored["inputs"]) == (None, None) and stored["part_hash"] == h(work, SCOUT)
    assert status(work, SCOUT) == "reopened"


@pytest.mark.parametrize(
    "kind, flags",
    [
        ("checked", ["--reason", "x"]),
        ("locked", ["--reason", "x"]),
        ("reviewed", ["--reason", "x"]),
        ("checked", ["--round", "1"]),
        ("locked", ["--verdict", "pass"]),
        ("reopened", ["--review", "parts/scout/review/round-1/review.md"]),
        ("reopened", ["--reason", "x", "--verdict", "fix"]),
        ("reviewed", []),
        ("reviewed", ["--round", "1", "--verdict", "pass"]),  # no --review
        ("reviewed", ["--review", "parts/scout/review/round-1/review.md", "--verdict", "pass"]),  # no --round
        ("reviewed", ["--review", "parts/scout/review/round-1/review.md", "--round", "1"]),  # no --verdict
        (
            "reviewed",
            ["--review", "parts/scout/review/round-0/review.md", "--round", "0", "--verdict", "pass"],
        ),
        (
            "reviewed",
            ["--review", "parts/scout/review/round--1/review.md", "--round", "-1", "--verdict", "pass"],
        ),
    ],
)
def test_receipt_usage_errors_write_nothing(capsys, work, kind, flags):
    review_file(work)
    assert rcpt(capsys, work, SCOUT, "checked")[0] == 0  # the command works with the right flags
    before = receipt_bytes(work)
    code, out, err = rcpt(capsys, work, SCOUT, kind, *flags)
    assert code == 2 and out is None and err.strip()
    assert receipt_bytes(work) == before


def test_receipt_of_a_part_the_manifest_does_not_list_is_refused(capsys, work):
    code, out, _ = rcpt(capsys, work, "no-such-part", "checked")
    assert code == 1 and out and out["receipt"] is None and out["refused"]
    assert [p["code"] for p in out["problems"]] == ["part_unknown"] and validate("part-output", out) == []
    code, out, _ = rcpt(capsys, work, "no-such-part", "reopened", "--reason", "x")
    assert code == 1 and out and out["receipt"] is None and out["refused"] and out["problems"] == []
    assert not (work / "parts" / "no-such-part").exists()
    (work / "parts" / "manifest.json").write_text("{", encoding="utf-8")
    code, out, _ = rcpt(capsys, work, SCOUT, "locked")
    assert code == 1 and out and out["receipt"] is None and receipt_bytes(work) is None


def test_unreadable_receipts_refuse_the_receipt_and_stay_as_they_are(capsys, work):
    write_receipts(work, SCOUT, "not json")
    code, out, _ = rcpt(capsys, work, SCOUT, "checked")
    assert code == 1 and out and out["receipt"] is None and SCOUT_REL in out["refused"]
    assert receipt_bytes(work) == b"not json"
    assert validate("part-output", out) == []


def test_same_receipt_twice_is_not_written(capsys, work):
    code, first, _ = rcpt(capsys, work, SCOUT, "checked")
    assert code == 0 and first and first["written"] is True
    saved = receipt_bytes(work)
    code, again, _ = rcpt(capsys, work, SCOUT, "checked")
    assert code == 0 and again and validate("part-output", again) == []
    assert again["written"] is False and again["refused"] is None and again["receipt"] == first["receipt"]
    assert receipt_bytes(work) == saved
    # reviewed: the same round and file bytes; another file or another round is a new receipt
    review_file(work)
    flags = review_flags(work)
    assert rcpt(capsys, work, SCOUT, "reviewed", *flags)[1]["written"] is True  # type: ignore[index]
    saved = receipt_bytes(work)
    code, again, _ = rcpt(capsys, work, SCOUT, "reviewed", *flags)
    assert code == 0 and again and again["written"] is False and again["receipt"]["n"] == 2
    assert receipt_bytes(work) == saved
    review_file(work, text="A rewritten review.\n")  # same round, other bytes
    code, new, _ = rcpt(capsys, work, SCOUT, "reviewed", *flags)
    assert code == 0 and new and new["written"] is True and new["receipt"]["n"] == 3
    review_file(work, n=2)
    code, new, _ = rcpt(capsys, work, SCOUT, "reviewed", *review_flags(work, SCOUT, 2))  # another round
    assert code == 0 and new and new["written"] is True and new["receipt"]["n"] == 4
    # locked and reopened twice (their preconditions no longer hold, the recorded receipt is the answer)
    code, lock_out, _ = rcpt(capsys, work, SCOUT, "locked")
    assert code == 0 and lock_out and lock_out["written"] is True
    saved = receipt_bytes(work)
    code, again, _ = rcpt(capsys, work, SCOUT, "locked")
    assert code == 0 and again and again["written"] is False and again["receipt"] == lock_out["receipt"]
    assert receipt_bytes(work) == saved
    assert rcpt(capsys, work, SCOUT, "reopened", "--reason", "once")[1]["written"] is True  # type: ignore[index]
    saved = receipt_bytes(work)
    code, again, _ = rcpt(capsys, work, SCOUT, "reopened", "--reason", "twice")
    assert code == 0 and again and again["written"] is False and again["receipt"]["reason"] == "once"
    assert receipt_bytes(work) == saved


def test_same_kind_on_another_hash_is_a_new_receipt(capsys, work):
    assert rcpt(capsys, work, SCOUT, "checked")[0] == 0
    (work / "parts" / SCOUT / "notes.md").write_text("changed\n", encoding="utf-8")
    code, out, _ = rcpt(capsys, work, SCOUT, "checked")
    assert code == 0 and out and out["written"] is True and out["receipt"]["n"] == 2
    assert out["receipt"]["part_hash"] == h(work, SCOUT)


def test_receipts_validate_and_append_only(capsys, work, monkeypatch):
    reviewed(capsys, work)
    assert rcpt(capsys, work, SCOUT, "locked")[0] == 0
    assert rcpt(capsys, work, SCOUT, "reopened", "--reason", "sizes changed")[0] == 0
    first_four = mod().read_receipts(work, SCOUT)
    doc = load(work, SCOUT_REL)
    assert validate("part-receipts", doc) == [] and doc["part"] == SCOUT
    assert [r["n"] for r in doc["receipts"]] == [1, 2, 3, 4]
    assert [r["kind"] for r in doc["receipts"]] == ["checked", "reviewed", "locked", "reopened"]
    assert all(r["tool_version"] == __version__ for r in doc["receipts"])
    assert receipt_bytes(work).endswith(b"\n") and b"\r" not in receipt_bytes(work)  # type: ignore[union-attr]
    assert rcpt(capsys, work, SCOUT, "checked")[0] == 0  # one more: the first four stay exactly as they were
    after = mod().read_receipts(work, SCOUT)
    assert after[:4] == first_four and after[4]["n"] == 5
    # no temporary file is left behind
    assert sorted(p.name for p in (work / "parts" / SCOUT).iterdir() if p.is_file()) == ["receipts.json"]
    # the document is validated before it is written: a receipt the schema refuses is never written
    (work / "parts" / SCOUT / "notes.md").write_text("a new hash\n", encoding="utf-8")
    before = receipt_bytes(work)
    monkeypatch.setattr(
        "tekla_harness.part_receipts.validate",
        lambda name, data: (
            [types.SimpleNamespace(path="/receipts/5", message="made-up failure")]
            if name == "part-receipts" and len(data["receipts"]) == 6
            else []
        ),  # the 5 receipts on disk are read as they are; the sixth is the one the schema refuses
    )
    with pytest.raises(ReceiptError, match="made-up failure"):
        mod().write_part_receipt(work, SCOUT, "checked")
    assert receipt_bytes(work) == before
    code, out, err = rcpt(capsys, work, SCOUT, "checked")  # m5: a bug in the receipt is exit 1, not 3
    assert code == 1 and out is None and "internal error" in err and "made-up failure" in err
    assert receipt_bytes(work) == before


def test_an_output_that_fails_its_schema_is_an_internal_error_and_writes_nothing(capsys, work, monkeypatch):
    """m5: `part receipt` validates its stdout against `part-output`, as `part check` does."""
    real = mod().validate
    monkeypatch.setattr(
        "tekla_harness.part_receipts.validate",
        lambda name, data: (
            [types.SimpleNamespace(path="/receipt", message="made-up output failure")]
            if name == "part-output"
            else real(name, data)
        ),
    )
    code, out, err = rcpt(capsys, work, SCOUT, "checked")
    assert code == 1 and out is None and "internal error" in err and "made-up output failure" in err
    assert receipt_bytes(work) is None  # the output is checked before the receipt is written
    monkeypatch.undo()
    assert rcpt(capsys, work, SCOUT, "checked")[0] == 0
    monkeypatch.setattr(
        "tekla_harness.part_receipts.validate",
        lambda name, data: (
            [types.SimpleNamespace(path="/receipt", message="made-up output failure")]
            if name == "part-output"
            else real(name, data)
        ),
    )
    code, out, err = rcpt(capsys, work, SCOUT, "checked")  # already recorded: the same check, the same exit
    assert code == 1 and out is None and "internal error" in err


def test_the_clock_is_injectable_and_utc(work):
    local = timezone(timedelta(hours=7))
    out = mod().write_part_receipt(
        work, SCOUT, "checked", now=lambda: datetime(2026, 3, 4, 5, 6, 7, tzinfo=local)
    )
    assert out["receipt"]["at"] == "2026-03-03T22:06:07Z" and out["written"] is True
    review = review_file(work)
    out = mod().write_part_receipt(
        work, SCOUT, "reviewed", review=str(review), review_round=1, verdict="fix",
        now=lambda: datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC),
    )  # fmt: skip
    assert out["receipt"]["at"] == "2026-12-31T23:59:59Z" and out["receipt"]["review"]["verdict"] == "fix"
    assert [r["at"] for r in mod().read_receipts(work, SCOUT)] == [
        "2026-03-03T22:06:07Z",
        "2026-12-31T23:59:59Z",
    ]
    with pytest.raises(ReaderError) as caught:  # flags of another kind are a usage error of the function too
        mod().write_part_receipt(work, SCOUT, "checked", reason="x")
    assert caught.value.exit_code == 2


def test_a_write_the_system_refuses_is_exit_3_and_leaves_no_file(capsys, work, monkeypatch):
    def refuse(self: Path, target: Any) -> Any:
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "replace", refuse)
    code, out, err = rcpt(capsys, work, SCOUT, "checked")
    assert code == 3 and out is None and "denied" in err
    assert not any((work / "parts" / SCOUT).glob("receipts.json*"))


def test_the_receipt_output_stays_a_discriminated_union(capsys, work):
    code, out, _ = rcpt(capsys, work, SCOUT, "checked")
    assert code == 0 and out and validate("part-output", out) == []

    def broken(change: Callable[[dict[str, Any]], None]) -> list[Any]:
        copy = json.loads(json.dumps(out))
        change(copy)
        return validate("part-output", copy)

    assert broken(lambda d: d.update(stray=1))
    assert broken(lambda d: d.pop("refused"))
    assert broken(lambda d: d.update(kind="approved"))
    assert broken(lambda d: d.update(command="check"))
    assert broken(lambda d: d["receipt"].update(stray=1))
    assert broken(lambda d: d["receipt"].update(part_hash="abc"))
    assert broken(lambda d: d.update(receipt=None))  # written true needs its receipt
    assert broken(lambda d: d.update(refused="x"))  # refused goes with written false and no receipt
    assert broken(
        lambda d: d.update(problems=[{"code": "no_such_code", "row": None, "id": None, "detail": "x"}])
    )
    assert not broken(lambda d: d.update(written=False))  # already recorded: the receipt is still there
    refused = {"command": "receipt", "part": SCOUT, "kind": "checked", "written": False, "receipt": None,
               "refused": "why", "problems": [PROBLEM]}  # fmt: skip
    assert validate("part-output", refused) == []
    assert validate("part-output", {**refused, "refused": None})  # not written, not refused, no receipt
    assert validate("part-output", {**refused, "written": True})


# --- E5b-fix-1: the latest review decides (M1, D2); a changed input is re-reviewed (D3) -------------------


def test_the_latest_review_of_the_current_hash_decides_the_status(work):
    write_values(work, [row()])
    current = h(work)

    def review(verdict: str, n: int) -> dict[str, Any]:
        return rec("reviewed", current, review={"round": n, "verdict": verdict,
                   "file": f"parts/x/review/round-{n}/review.md", "sha256": "a" * 64})  # fmt: skip

    checked = rec("checked", current)
    write_receipts(work, PART, [checked, review("pass", 1), review("fix", 2)])
    assert status(work) == "checked"  # a later fix beats the earlier pass
    write_receipts(work, PART, [checked, review("pass", 1), review("engineer", 2)])
    assert status(work) == "checked"
    write_receipts(work, PART, [checked, review("fix", 1), review("pass", 2)])
    assert status(work) == "reviewed"  # and a later pass beats the earlier fix
    write_receipts(work, PART, [checked, review("pass", 1), review("fix", 2), review("pass", 3)])
    assert status(work) == "reviewed"
    other = rec("reviewed", "c" * 64, review={"round": 3, "verdict": "fix",
                "file": "parts/x/review/round-3/review.md", "sha256": "a" * 64})  # fmt: skip
    write_receipts(work, PART, [checked, review("pass", 1), other])
    assert status(work) == "checked"  # E5b-fix-3, D2: the latest review decides, whatever its hash


def test_a_later_fix_verdict_on_the_same_hash_refuses_the_lock(capsys, work):
    """P1: `reviewed` round 1 pass, round 2 fix: the latest review says fix, `locked` is refused."""
    reviewed(capsys, work, n=1)
    reviewed(capsys, work, verdict="fix", n=2)
    assert status(work, SCOUT) == "checked"
    before = receipt_bytes(work)
    code, out, err = rcpt(capsys, work, SCOUT, "locked")
    assert code == 1 and out and out["written"] is False and out["receipt"] is None
    assert "round 2" in out["refused"] and "fix" in out["refused"] and "refused" in err
    assert receipt_bytes(work) == before and kinds(work)[-1] == "reviewed" and "locked" not in kinds(work)
    reviewed(capsys, work, verdict="pass", n=3)  # a later pass decides again
    code, out, _ = rcpt(capsys, work, SCOUT, "locked")
    assert code == 0 and out and out["written"] is True
    assert status(work, SCOUT) == "locked"


def test_a_rewritten_review_recorded_with_fix_refuses_the_lock(capsys, work):
    """P1b: round 1 `pass`, then the same round's file rewritten and recorded again with `fix`."""
    reviewed(capsys, work, n=1)
    review_file(work, n=1, text="A rewritten review: one problem.\n")
    code, out, _ = rcpt(capsys, work, SCOUT, "reviewed", *review_flags(work, SCOUT, 1, "fix"))
    assert code == 0 and out and out["written"] is True
    before = receipt_bytes(work)
    code, out, _ = rcpt(capsys, work, SCOUT, "locked")
    assert code == 1 and out and out["receipt"] is None and receipt_bytes(work) == before


def test_the_same_review_file_with_another_verdict_is_a_new_receipt(capsys, work):
    """P2 / D2: rule 5 also compares the verdict, so the second verdict is written and then decides. A `pass`
    of the round that said `fix` is not recorded (E5b review 3, D4): only a higher round overturns it."""
    reviewed(capsys, work, n=1)
    saved = receipt_bytes(work)
    code, again, _ = rcpt(capsys, work, SCOUT, "reviewed", *review_flags(work, SCOUT, 1, "pass"))
    assert code == 0 and again and again["written"] is False and receipt_bytes(work) == saved  # same verdict
    code, new, _ = rcpt(capsys, work, SCOUT, "reviewed", *review_flags(work, SCOUT, 1, "fix"))
    assert code == 0 and new and new["written"] is True and new["receipt"]["n"] == 3
    assert new["receipt"]["review"]["verdict"] == "fix"
    assert status(work, SCOUT) == "checked"
    assert rcpt(capsys, work, SCOUT, "locked")[0] == 1
    before = receipt_bytes(work)
    code, back, _ = rcpt(capsys, work, SCOUT, "reviewed", *review_flags(work, SCOUT, 1, "pass"))
    assert code == 1 and back and back["receipt"] is None  # E5b review 3, D4: round 1 said fix
    assert back["refused"] == "round 1 said fix: record round 2" and receipt_bytes(work) == before
    review_file(work, n=2)
    code, back, _ = rcpt(capsys, work, SCOUT, "reviewed", *review_flags(work, SCOUT, 2, "pass"))
    assert code == 0 and back and back["written"] is True and back["receipt"]["n"] == 4  # a higher round
    assert rcpt(capsys, work, SCOUT, "locked")[0] == 0


def test_a_stale_input_part_cannot_be_locked_directly(capsys, work, monkeypatch):
    """D3: B1-caps is locked, its input B1-piles is reopened, changed and locked again: B1-caps is
    `stale_input` and `locked` on its unchanged hash is refused; the way back is reopened, checked and
    reviewed."""
    monkeypatch.setattr("tekla_harness.part_check.check_part", fake_check([]))
    write_values(work, [row()])
    lock(work, INPUT_PART)
    lock(work, PART)
    piles = [_strip(r) for r in load(work, f"parts/{INPUT_PART}/receipts.json")["receipts"]]
    write_receipts(work, INPUT_PART, [*piles, rec("reopened", h(work, INPUT_PART))])
    write_values(work, [row(mark="P-1", sheet="model#02")], INPUT_PART)
    lock(work, INPUT_PART)  # a changed input, locked again
    assert status(work, PART) == "stale_input"
    before = receipt_bytes(work, PART)
    code, out, err = rcpt(capsys, work, PART, "locked")
    assert code == 1 and out and out["written"] is False and out["receipt"] is None and "refused" in err
    assert receipt_bytes(work, PART) == before and status(work, PART) == "stale_input"
    assert rcpt(capsys, work, PART, "reopened", "--reason", "an input changed")[0] == 0
    assert rcpt(capsys, work, PART, "checked")[0] == 0
    review_file(work, PART)
    assert rcpt(capsys, work, PART, "reviewed", *review_flags(work, PART))[0] == 0
    code, out, _ = rcpt(capsys, work, PART, "locked")
    assert code == 0 and out and out["receipt"]["inputs"] == {INPUT_PART: h(work, INPUT_PART)}
    assert status(work, PART) == "locked"


# --- E5b-fix-3: the hash holds the drawings a part reads and what part check reads of a question -----------

OTHER = "plans/other.dxf"


def add_other_drawing(w: Path, sha: str) -> None:
    """A second drawing in the inventory (a copy of the first one's row under another path)."""

    def change(doc: Any) -> None:
        base = next(f for f in doc["files"] if f["path"] == REL)
        doc["files"].append({**base, "path": OTHER, "sha256": sha})

    edit_json(w, "inventory.json", change)


def set_sha(w: Path, path: str, sha: str) -> None:
    def change(doc: Any) -> None:
        next(f for f in doc["files"] if f["path"] == path)["sha256"] = sha

    edit_json(w, "inventory.json", change)


def registry_edit(w: Path, qid: str, change: Callable[[dict[str, Any]], None]) -> None:
    edit_json(
        w,
        "question-registry.json",
        lambda doc: change(next(e for e in doc["questions"].values() if e["id"] == qid)),
    )


def entry_only_part(w: Path) -> None:
    """B1-caps with no finding (both withdrawn) and one row on the entry of its text alone."""
    for fid in ("F-001", "F-002"):
        withdraw_finding(w, fid, "read from the entries", PART)
    write_values(w, [entry_row(w, "R001", "size", "1500x2400")])


def test_a_revised_drawing_moves_the_hash_of_a_part_with_no_finding_on_it(work):
    """C1, probe A: the row cites an entry only, so no finding of the part goes stale; the hash still sees
    the drawing through the `files` map (the inventory sha256 of each drawing the part reads)."""
    entry_only_part(work)
    before = h(work)
    assert before == expected_hash(work, PART)
    assert all(
        f["status"] == "withdrawn"
        for f in load(work, "reader-findings.json")["findings"]
        if f["part"] == PART
    )
    revise_drawing(work)
    assert h(work) != before and h(work) == expected_hash(work, PART)


def test_a_drawing_the_part_does_not_read_leaves_its_hash_alone(work):
    entry_only_part(work)
    before = h(work)
    add_other_drawing(work, "1" * 64)  # inventory.json changes, the drawing the part reads does not
    assert h(work) == before
    set_sha(work, OTHER, "2" * 64)
    assert h(work) == before  # a re-intake of unchanged drawings reopens nothing
    edit_json(
        work,
        "inventory.json",
        lambda doc: doc["files"].remove(next(f for f in doc["files"] if f["path"] == REL)),
    )
    assert h(work) != before and h(work) == expected_hash(work, PART)  # a drawing the inventory lost: null


def put_in_row(where: str) -> Callable[[dict[str, Any]], None]:
    cluster = {"file": OTHER, "sheet": None, "side": "none"}
    places: dict[str, dict[str, Any]] = {
        "sheets": {"sheets": [{"file": OTHER, "sheet": "model#01", "role": "plan"}]},
        "clusters": {"clusters": [cluster]},
        "tables": {"tables": [{"file": OTHER, "sheet": "model#01", "header_entries": ["T000001"]}]},
        "table_cluster": {"tables": [{"cluster": cluster, "header_entries": ["T000001"]}]},
        "files": {"files": [OTHER]},
    }
    return lambda part_row: part_row.update(places[where])


@pytest.mark.parametrize("where", ["sheets", "clusters", "tables", "table_cluster", "files"])
def test_every_file_the_manifest_row_names_is_in_the_hash(work, where):
    add_other_drawing(work, "1" * 64)
    edit_json(
        work,
        str(MANIFEST),
        lambda doc: put_in_row(where)(next(p for p in doc["parts"] if p["id"] == SCOUT)),
    )
    before = h(work, SCOUT)
    assert before == expected_hash(work, SCOUT)
    set_sha(work, OTHER, "2" * 64)
    assert h(work, SCOUT) != before and h(work, SCOUT) == expected_hash(work, SCOUT)


def test_a_file_a_values_row_names_is_in_the_hash(work):
    add_other_drawing(work, "1" * 64)
    write_values(work, [row(file=OTHER)])
    before = h(work)
    assert before == expected_hash(work, PART)
    set_sha(work, OTHER, "2" * 64)
    assert h(work) != before and h(work) == expected_hash(work, PART)


def test_a_locked_part_with_entry_only_rows_is_reopened_when_its_drawing_is_revised(work):
    entry_only_part(work)
    for part in (INPUT_PART, PART, ASSEMBLY):
        lock(work, part)
    assert status(work) == "locked"
    revise_drawing(work)
    assert status(work) == "reopened" and status(work, ASSEMBLY) == "stale_input"


def test_a_question_cited_through_a_finding_going_obsolete_moves_the_hash(work):
    """M1, probe C part 3: F-001 holds Q-001, the row cites F-001 and (directly) only Q-003."""
    finding_edit(work, "F-001", _set("questions", ["Q-001"]))
    write_values(work, [row()])
    before = h(work)
    assert before == expected_hash(work, PART)
    set_registry_status(work, "Q-002", "obsolete")  # cited by nothing
    assert h(work) == before
    set_registry_status(work, "Q-001", "obsolete")
    assert h(work) != before and h(work) == expected_hash(work, PART)
    set_registry_status(work, "Q-001", "answered")  # an answer moves nothing
    assert h(work) == before


def test_a_finding_id_no_record_holds_cites_no_question(work):
    write_values(work, [row(cites={"findings": ["F-001", "F-099"]})])
    assert h(work) == expected_hash(work, PART)


def test_a_cited_questions_blocking_flag_moves_the_hash(work):
    """M1, probe C part 4: the flag `part check` reads (a missing flag counts as blocking)."""
    write_values(work, [row()])  # cites Q-003 directly
    registry_edit(work, "Q-003", lambda e: e.update(blocking=True))
    before = h(work)
    assert before == expected_hash(work, PART)
    registry_edit(work, "Q-003", lambda e: e.update(blocking=False))
    assert h(work) != before and h(work) == expected_hash(work, PART)
    registry_edit(work, "Q-003", lambda e: e.pop("blocking"))
    assert h(work) == before
    registry_edit(work, "Q-003", lambda e: e.update(blocking=True))
    finding_edit(work, "F-001", _set("questions", ["Q-004"]))  # and through a finding
    through = h(work)
    registry_edit(work, "Q-004", lambda e: e.update(blocking=False))
    assert h(work) != through and h(work) == expected_hash(work, PART)
    registry_edit(work, "Q-002", lambda e: e.update(blocking=False))  # cited by nothing
    assert h(work) == expected_hash(work, PART)


def test_a_locked_part_is_reopened_when_a_question_it_cites_through_a_finding_stops_blocking(work):
    finding_edit(work, "F-001", _set("questions", ["Q-004"]))
    write_values(work, [row()])
    for part in (INPUT_PART, PART, ASSEMBLY):
        lock(work, part)
    assert status(work) == "locked"
    registry_edit(work, "Q-004", lambda e: e.update(blocking=False))
    assert status(work) == "reopened"


# --- E5b-fix-3: the latest review decides, whatever its hash; an older round is refused (D2) ----------------


def test_a_fix_recorded_on_another_hash_still_decides_when_the_part_comes_back(capsys, work):
    """D2, probe C part 1: pass on H1, fix on H2, the edit reverted (H1): the later fix still decides."""
    notes = work / "parts" / SCOUT / "notes.md"
    reviewed(capsys, work, n=1)
    notes.write_text("an edit\n", encoding="utf-8")
    reviewed(capsys, work, verdict="fix", n=2)
    notes.unlink()
    assert status(work, SCOUT) == "checked"
    before = receipt_bytes(work)
    code, out, _ = rcpt(capsys, work, SCOUT, "locked")
    assert code == 1 and out and out["receipt"] is None and receipt_bytes(work) == before
    reviewed(capsys, work, n=3)  # a new round, passing, on the current hash
    assert status(work, SCOUT) == "reviewed"
    assert rcpt(capsys, work, SCOUT, "locked")[0] == 0


def test_a_review_round_older_than_one_recorded_is_refused(capsys, work):
    """D2, probe F: round 1 pass, round 2 fix, then round 1 recorded again."""
    reviewed(capsys, work, n=1)
    reviewed(capsys, work, verdict="fix", n=2)
    before = receipt_bytes(work)
    for verdict in ("pass", "fix"):
        code, out, err = rcpt(capsys, work, SCOUT, "reviewed", *review_flags(work, SCOUT, 1, verdict))
        assert code == 1 and out and out["written"] is False and out["receipt"] is None
        assert "round 1 is older than round 2: record a new round" in out["refused"] and "refused" in err
        assert receipt_bytes(work) == before
    assert status(work, SCOUT) == "checked" and rcpt(capsys, work, SCOUT, "locked")[0] == 1
    code, out, _ = rcpt(capsys, work, SCOUT, "reviewed", *review_flags(work, SCOUT, 2, "pass"))
    assert code == 1 and out and out["receipt"] is None  # E5b review 3, D4: round 2 said fix
    assert out["refused"] == "round 2 said fix: record round 3" and receipt_bytes(work) == before
    reviewed(capsys, work, n=3)  # a higher round overturns the fix
    assert rcpt(capsys, work, SCOUT, "locked")[0] == 0


def test_review_rounds_count_again_after_a_reopened_receipt(capsys, work):
    reviewed(capsys, work, n=2)
    assert rcpt(capsys, work, SCOUT, "locked")[0] == 0
    assert rcpt(capsys, work, SCOUT, "reopened", "--reason", "a new reading")[0] == 0
    reviewed(capsys, work, n=1)  # the rounds of the earlier lock do not count
    assert status(work, SCOUT) == "reviewed"


# --- E5b-fix-3: minor fixes (m1, m4) ---------------------------------------------------------------------


def test_locked_on_a_stale_input_part_whose_input_hashes_did_not_change_is_refused(capsys, work):
    """m1, probe C part 2: B1-piles was reopened and not changed; the lock of B1-caps is not "recorded"."""
    write_values(work, [row()])
    lock(work, INPUT_PART)
    lock(work, PART)
    piles = [_strip(r) for r in load(work, f"parts/{INPUT_PART}/receipts.json")["receipts"]]
    write_receipts(work, INPUT_PART, [*piles, rec("reopened", h(work, INPUT_PART))])
    assert status(work) == "stale_input"
    before = receipt_bytes(work, PART)
    code, out, err = rcpt(capsys, work, PART, "locked")
    assert code == 1 and out and out["written"] is False and out["receipt"] is None and "refused" in err
    assert out["refused"] == (
        f"'{PART}' is locked (receipt 1) but its input part(s) are not locked: {INPUT_PART} (reopened): "
        "it reads locked again when they are locked on the hashes it stored"
    )
    assert receipt_bytes(work, PART) == before
    write_receipts(
        work,
        INPUT_PART,
        [*piles, rec("reopened", h(work, INPUT_PART)), rec("locked", h(work, INPUT_PART), inputs={})],
    )
    assert status(work) == "locked"  # reads locked again, with no new receipt
    code, out, _ = rcpt(capsys, work, PART, "locked")
    assert code == 0 and out and out["written"] is False and receipt_bytes(work, PART) == before


def test_a_finding_judgement_the_system_refuses_is_exit_3_not_a_stale_finding(work, monkeypatch):
    """m4 (the part hash's side): an `OSError` the findings module reports as exit 3 stays exit 3 here."""

    def refuse(*_: Any, **__: Any) -> Any:
        raise FindingError(3, "cannot read geometry/g1.json: denied")

    write_receipts(work, PART, [rec("checked", "a" * 64)])
    monkeypatch.setattr("tekla_harness.part_receipts._stale_reasons", refuse)
    for call in (lambda: h(work), lambda: status(work)):
        with pytest.raises(ReaderError) as caught:
            call()
        assert caught.value.exit_code == 3 and "denied" in str(caught.value)


# --- E5b review 3: own findings' questions and cited grid systems in the hash (m1, D3), a fix overturned only
# by a higher round (D4) -------------------------------------------------------------------------------------


def add_low_finding(w: Path, *questions: str) -> str:
    """An active `low` finding of B1-caps holding `questions` and cited by no row of `values.json`."""
    return add_finding(
        w, kind="note_item", file=REL, entries=[entry_ids(w)["D400"]], value="D400", sheet="model#01",
        fields=["topic=other"], part=PART, note="block: D400 as printed", questions=list(questions),
        confidence="low",
    )["id"]  # fmt: skip


def test_the_question_of_an_own_uncited_finding_moves_the_hash_when_it_is_withdrawn(work):
    """P1 (m1): the check reads the registry status of the questions of every own active `low` finding."""
    write_values(work, [row()])  # cites F-001 and Q-003: not the new finding, not Q-002
    add_low_finding(work, "Q-002")
    before = h(work)
    assert before == expected_hash(work, PART)
    set_registry_status(work, "Q-002", "obsolete")  # held by an own finding no row cites
    assert h(work) != before and h(work) == expected_hash(work, PART)
    set_registry_status(work, "Q-002", "open")
    assert h(work) == before
    set_registry_status(work, "Q-002", "answered")  # an answer moves nothing
    assert h(work) == before
    registry_edit(work, "Q-002", lambda e: e.update(blocking=not e.get("blocking", True)))  # the flag, too
    assert h(work) != before and h(work) == expected_hash(work, PART)


def test_a_locked_part_is_reopened_when_the_question_of_an_own_uncited_finding_is_withdrawn(work):
    write_values(work, [row()])
    add_low_finding(work, "Q-002")
    for part in (INPUT_PART, PART, ASSEMBLY):
        lock(work, part)
    assert status(work) == "locked"
    set_registry_status(work, "Q-002", "obsolete")
    assert status(work) == "reopened"


def test_a_question_held_by_a_finding_of_another_part_or_a_withdrawn_one_is_not_in_the_hash(work):
    write_values(work, [row()])
    other = add_finding(
        work, kind="note_item", file=REL, entries=[entry_ids(work)["D400"]], value="D400", sheet="model#01",
        fields=["topic=other"], part=INPUT_PART, note="block: D400 as printed", questions=["Q-001"],
        confidence="low",
    )["id"]  # fmt: skip
    mine = add_low_finding(work, "Q-002")
    withdraw_finding(work, mine, "wrong reading", part=PART)
    before = h(work)
    assert other and before == expected_hash(work, PART)
    set_registry_status(work, "Q-001", "obsolete")  # a finding of B1-piles
    set_registry_status(work, "Q-002", "obsolete")  # a finding of B1-caps that is withdrawn
    assert h(work) == before


def put_grid_systems(w: Path) -> None:
    shutil.copy(Path(__file__).parent.parent / "schemas" / "examples" / "grid-system.example.json",
                w / "grid-systems.json")  # fmt: skip


def cite_systems(w: Path, *ids: str) -> None:
    write_values(w, [row(cites={"findings": ["F-001"], "grid_systems": list(ids)})])


def system_edit(w: Path, sid: str, change: Callable[[dict[str, Any]], None]) -> None:
    edit_json(
        w, "grid-systems.json", lambda doc: change(next(s for s in doc["systems"] if s["system_id"] == sid))
    )


def test_a_cited_grid_system_is_hashed_whole_and_an_uncited_one_is_not(work):
    """P4 (m4, D3): a rerun that changes a cited system moves the hash; one that changes another does not."""
    put_grid_systems(work)
    cite_systems(work, "S001")
    before = h(work)
    assert before == expected_hash(work, PART)
    system_edit(work, "S002", _set("confidence", "medium"))  # no row cites S002
    assert h(work) == before
    system_edit(work, "S001", _set("confidence", "low"))  # the value the take-off prints
    low = h(work)
    assert low != before and low == expected_hash(work, PART)
    system_edit(work, "S001", _set("confidence", "medium"))
    assert h(work) == before  # back to the stored value: the same hash again
    system_edit(
        work, "S001", lambda s: s["directions"][0]["spacings"].__setitem__(0, 6500.0)
    )  # not the confidence
    assert h(work) not in (before, low) and h(work) == expected_hash(work, PART)


def test_a_cited_grid_system_the_document_lacks_is_hashed_as_null(work):
    cite_systems(work, "S001")
    no_file = h(work)  # grid-systems.json is not there
    assert no_file == expected_hash(work, PART)
    put_grid_systems(work)
    cite_systems(work, "S001")
    with_system = h(work)
    assert with_system != no_file
    edit_json(work, "grid-systems.json", lambda doc: doc["systems"].pop(0))  # S001 is gone from a rerun
    assert doc_systems(work) == ["S002", "S003"]
    assert h(work) == no_file == expected_hash(work, PART)


def doc_systems(w: Path) -> list[str]:
    return [s["system_id"] for s in load(w, "grid-systems.json")["systems"]]


def test_grid_systems_json_is_read_only_when_a_row_cites_a_system(work, monkeypatch):
    put_grid_systems(work)
    cite_systems(work, "S001")
    cited = h(work)
    write_values(work, [row()])  # no row cites a system
    plain = h(work)
    assert plain != cited and plain == expected_hash(work, PART)
    reads: list[str] = []
    real = Path.read_bytes

    def spy(self: Path) -> bytes:
        reads.append(self.name)
        return real(self)

    monkeypatch.setattr(Path, "read_bytes", spy)
    (work / "grid-systems.json").write_text("{", encoding="utf-8")  # unusable, and nothing cites a system
    assert h(work) == plain
    assert "grid-systems.json" not in reads
    cite_systems(work, "S001")
    with pytest.raises(ReaderError) as caught:  # the same mapping as the other record documents
        h(work)
    assert caught.value.exit_code == 1 and "grid-systems.json" in str(caught.value)
    assert "grid-systems.json" in reads


def test_a_grid_systems_document_the_system_refuses_is_exit_3(work, monkeypatch):
    put_grid_systems(work)
    cite_systems(work, "S001")
    real = Path.read_bytes

    def refuse(self: Path) -> bytes:
        if self.name == "grid-systems.json":
            raise PermissionError(13, "Permission denied")
        return real(self)

    monkeypatch.setattr(Path, "read_bytes", refuse)
    with pytest.raises(ReaderError) as caught:
        h(work)
    assert caught.value.exit_code == 3 and "grid-systems.json" in str(caught.value)


def test_a_locked_part_is_reopened_when_a_grid_system_it_cites_changes(work):
    put_grid_systems(work)
    cite_systems(work, "S001")
    for part in (INPUT_PART, PART, ASSEMBLY):
        lock(work, part)
    assert status(work) == "locked"
    system_edit(work, "S002", _set("confidence", "medium"))
    assert status(work) == "locked"
    system_edit(work, "S001", _set("confidence", "low"))
    assert status(work) == "reopened"


@pytest.mark.parametrize("verdict", ["fix", "engineer"])
def test_a_pass_of_the_round_that_said_fix_is_refused_with_the_same_or_a_rewritten_review(
    capsys, work, verdict
):
    """D4: round 2 said `fix` (or `engineer`): only round 3 overturns it."""
    reviewed(capsys, work, n=1)
    reviewed(capsys, work, verdict=verdict, n=2)
    before = receipt_bytes(work)
    for rewrite in (None, "A rewritten review: nothing found.\n"):
        if rewrite is None:  # the same round with the same verdict is "already recorded"
            again = rcpt(capsys, work, SCOUT, "reviewed", *review_flags(work, SCOUT, 2, verdict))
            assert again[0] == 0 and again[1] and again[1]["written"] is False
            assert receipt_bytes(work) == before
        else:
            review_file(work, n=2, text=rewrite)
        code, out, err = rcpt(capsys, work, SCOUT, "reviewed", *review_flags(work, SCOUT, 2, "pass"))
        assert code == 1 and out and out["written"] is False and out["receipt"] is None
        assert out["refused"] == f"round 2 said {verdict}: record round 3" and "refused" in err
        assert receipt_bytes(work) == before
        assert status(work, SCOUT) == "checked" and rcpt(capsys, work, SCOUT, "locked")[0] == 1
    reviewed(capsys, work, n=3)  # a higher round passes
    assert status(work, SCOUT) == "reviewed"
    code, out, _ = rcpt(capsys, work, SCOUT, "locked")
    assert code == 0 and out and out["written"] is True and status(work, SCOUT) == "locked"


def test_a_pass_of_the_round_that_said_fix_on_another_hash_is_refused(capsys, work):
    """D4: round 1 `fix` on H1, the notes edited (H2), `checked`, round 1 `pass` on H2."""
    notes = work / "parts" / SCOUT / "notes.md"
    reviewed(capsys, work, verdict="fix", n=1)
    notes.write_text("an edit\n", encoding="utf-8")
    assert rcpt(capsys, work, SCOUT, "checked")[0] == 0
    before = receipt_bytes(work)
    code, out, _ = rcpt(capsys, work, SCOUT, "reviewed", *review_flags(work, SCOUT, 1, "pass"))
    assert code == 1 and out and out["receipt"] is None
    assert out["refused"] == "round 1 said fix: record round 2" and receipt_bytes(work) == before
    assert rcpt(capsys, work, SCOUT, "locked")[0] == 1
    reviewed(capsys, work, n=2)
    assert rcpt(capsys, work, SCOUT, "locked")[0] == 0


def test_a_fix_before_the_last_reset_does_not_refuse_a_pass_of_its_round(capsys, work):
    """D4 counts the receipts since the last `reopened` or `locked`, as the round rule does."""
    reviewed(capsys, work, verdict="fix", n=1)
    reviewed(capsys, work, n=2)
    assert rcpt(capsys, work, SCOUT, "locked")[0] == 0
    assert rcpt(capsys, work, SCOUT, "reopened", "--reason", "a new reading")[0] == 0
    reviewed(capsys, work, n=1)  # the fix of round 1 belongs to the earlier lock
    assert status(work, SCOUT) == "reviewed"
