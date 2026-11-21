"""The `part-conflicts` producer's plumbing (E6a, DECISIONS § 6): a question that `harness part conflicts`
raises is registered, shown on its parts in `harness status`, printed in questions.md and closed only by the
engineer's answer. Questions are raised with `Ledger.sync` directly (the command is E6b). The world is
test_status.py's; its fixtures are imported by name, so a test parameter re-binds them (F811 is expected).
"""

# ruff: noqa: F811

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tekla_harness.answers import record_answer
from tekla_harness.questions import (
    PRODUCER_COMMANDS,
    PRODUCERS,
    QUESTION_DOCUMENTS,
    load_ledger,
    question_group,
    questions_document,
)
from tekla_harness.questions_md import UNTRANSLATED, code_span, render_questions_md
from tekla_harness.schemas import validate
from tekla_harness.status import (
    GATE_ANSWER_PRODUCERS,
    GATE_PRODUCERS,
    PART_QUESTION_FILES,
    build_status,
)
from tekla_harness.status import PRODUCERS as STATUS_PRODUCERS
from test_status import (  # noqa: F401  (pytest fixtures, used by name)
    PART_A,
    PART_B,
    PART_C,
    answer_by_engineer,
    ask_reader,
    base_world,
    by_label,
    lock_all,
    part_rows,
    put_parts,
    ready,
    ready_gate1,
    ready_world,
    world,
)

PRODUCER = "part-conflicts"
DOCUMENT = "part-conflicts-questions.json"
MESSAGE = "K-1 ghi 1500x2400 ở hai nơi khác nhau; kỹ sư chọn giá trị đúng."


def conflict(code: str, parts: list[str] | None = None, *, blocking: bool = True) -> dict[str, Any]:
    """A question as `harness part conflicts` hands it over: project level (no file), tagged with parts."""
    refs = [{"file": None, "where": f"{code} K-1", "found": "1500x2400 vs 900x900"}]
    raw = question_group(code, blocking, MESSAGE, refs, file=None)
    if parts is not None:
        raw["parts"] = parts
    return raw


def raise_conflicts(work: Path, raws: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """What the producer does: sync its FULL list of questions, then registry and document (as `harness ask`
    writes reader-questions.json)."""
    ledger = load_ledger(work, None, create=False)
    rendered = ledger.sync(PRODUCER, raws, {})
    ledger.write()
    doc = questions_document(ledger.registry["project_id"], rendered)
    assert validate("intake", doc) == []
    (work / DOCUMENT).write_text(json.dumps(doc), encoding="utf-8")
    return rendered


def raise_other(work: Path, producer: str, *codes: tuple[str, bool]) -> list[str]:
    """The questions (code, blocking) of the callouts or marks producer, registry only (status counts from
    it); one call per producer, as a sync obsoletes the producer's questions it does not list."""
    raws = [
        question_group(c, b, "m", [{"file": None, "where": c, "found": "f"}], file=None) for c, b in codes
    ]
    ledger = load_ledger(work, None, create=False)
    rendered = ledger.sync(producer, raws, {})
    ledger.write()
    return [str(q["id"]) for q in rendered]


def test_producer_listed_in_every_table():
    assert PRODUCER in PRODUCERS and PRODUCER_COMMANDS[PRODUCER] == "harness part conflicts"
    assert DOCUMENT in QUESTION_DOCUMENTS
    assert (DOCUMENT, "intake") in PART_QUESTION_FILES  # the file status reads `parts` from
    assert dict(STATUS_PRODUCERS)[PRODUCER] == PRODUCER
    assert PRODUCER in GATE_ANSWER_PRODUCERS  # only the engineer's answer closes it ...
    assert PRODUCER not in GATE_PRODUCERS  # ... and it blocks its parts, not gate 1


def test_sync_renders_parts(tmp_path):
    ledger = load_ledger(tmp_path, "demo", create=True)
    tagged, untagged = ledger.sync(
        PRODUCER, [conflict("size_conflict", [PART_A, PART_B]), conflict("note_conflict")], {}
    )
    assert tagged["parts"] == [PART_A, PART_B] and "parts" not in untagged
    assert validate("intake", questions_document("demo", [tagged, untagged])) == []
    assert ledger.registry["questions"][tagged["key"]]["producer"] == PRODUCER
    assert validate("question-registry", ledger.registry) == []


def test_status_shows_producer_with_outputs_na(world):
    _, work = world
    (q,) = raise_conflicts(work, [conflict("size_conflict")])
    doc = build_status(work)
    assert validate("status", doc) == []
    assert [p["producer"] for p in doc["producers"]][-2:] == ["reader", PRODUCER]
    row = by_label(doc)[PRODUCER]
    assert row["command"] == "harness part conflicts"
    assert row["outputs"] == {"status": "n/a", "files": [], "reason": None, "rerun": None}
    assert row["questions"]["total"] == 1 and row["questions"]["blocking_open"] == 1
    assert row["blocking_open_ids"] == [q["id"]]
    assert not [r for r in doc["gate1"]["reasons"] if PRODUCER in r]


def test_part_conflict_blocks_only_tagged_parts(ready):
    _, work = ready
    put_parts(work)
    lock_all(work)
    before = {k: v["hash"] for k, v in part_rows(work).items()}
    one, both, quiet = raise_conflicts(
        work,
        [
            conflict("size_conflict", [PART_A]),
            conflict("note_conflict", [PART_A, PART_C]),
            conflict("quiet_conflict", [PART_B], blocking=False),  # not blocking: never listed
        ],
    )
    rows = part_rows(work)
    assert rows[PART_A]["blocking_open_ids"] == [one["id"], both["id"]]
    assert rows[PART_C]["blocking_open_ids"] == [both["id"]]
    assert rows[PART_B]["blocking_open_ids"] == [] and quiet["id"] not in str(rows)
    assert [rows[p]["ready"] for p in (PART_A, PART_B, PART_C)] == [False, True, False]
    assert all(not r["blocked_by_project"] for r in rows.values())
    assert {k: v["hash"] for k, v in rows.items()} == before  # a conflict never enters a part's hash
    answer_by_engineer(work, both["id"])
    rows = part_rows(work)
    assert rows[PART_C]["ready"] is True and rows[PART_A]["blocking_open_ids"] == [one["id"]]


def test_part_conflict_is_no_gate1_reason(ready):
    _, work = ready
    before = build_status(work)["gate1"]
    assert before == ready_gate1(work)
    raise_conflicts(work, [conflict("size_conflict", [PART_A]), conflict("note_conflict")])
    doc = build_status(work)
    assert doc["gate1"] == before  # open, blocking, tagged or not: gate 1 stays ready
    assert by_label(doc)[PRODUCER]["questions"]["blocking_open"] == 2


def test_simulated_answer_does_not_close_it(ready):
    _, work = ready
    put_parts(work)
    lock_all(work)
    (q,) = raise_conflicts(work, [conflict("size_conflict", [PART_A])])
    record_answer(work, q["id"], "A. Nguyen says A", "bot", {}, role="simulated")
    doc = build_status(work)
    rows = {p["id"]: p for p in doc["parts"]}
    assert rows[PART_A]["blocking_open_ids"] == [q["id"]] and rows[PART_A]["ready"] is False
    assert by_label(doc)[PRODUCER]["questions"]["answered"] == 0
    assert rows[PART_B]["ready"] is True  # the simulated answer is no project reason either
    assert doc["gate1"] == ready_gate1(work)
    answer_by_engineer(work, q["id"])
    assert part_rows(work)[PART_A]["ready"] is True


def test_project_blocking_ids_full_with_unlisted_callouts_and_marks(ready, world):
    _, work = ready
    assert "project_blocking_ids" not in build_status(work)  # part mode only
    untagged_reader = ask_reader(work, "reader_size_unclear")  # asked before the manifest
    callout, listed = raise_other(work, "callouts", ("callout_open", True), ("callout_listed", True))
    mark, _quiet = raise_other(work, "marks", ("mark_open", True), ("mark_quiet", False))
    put_parts(work, producer_questions={PART_B: [listed]})  # a part holds this one: no project reason
    lock_all(work)
    many = [conflict(f"conflict_{n}") for n in range(55)]  # more than MAX_IDS, no part
    ids = [q["id"] for q in raise_conflicts(work, [*many, conflict("tagged_conflict", [PART_A])])[:55]]
    doc = build_status(work)
    expected = sorted([untagged_reader, callout, mark, *ids], key=lambda i: int(i[2:]))
    assert doc["project_blocking_ids"] == expected and len(expected) == 58
    assert validate("status", doc) == []
    rows = {p["id"]: p for p in doc["parts"]}
    assert all(r["blocked_by_project"] and not r["ready"] for r in rows.values())
    assert rows[PART_B]["blocking_open_ids"] == [listed]
    for qid in (untagged_reader, callout, mark, *ids):
        answer_by_engineer(work, qid)
    doc = build_status(work)
    assert doc["project_blocking_ids"] == []
    assert part_rows(work)[PART_C]["ready"] is True
    _, wwork = world  # gate-1 producers: every open blocking id, whatever the parts
    put_parts(wwork)
    status = build_status(wwork)
    gate = [
        i
        for p in ("intake", "read-structure", "grid-system")
        for i in by_label(status)[p]["blocking_open_ids"]
    ]
    assert gate and status["project_blocking_ids"] == sorted(gate, key=lambda i: int(i[2:]))


def test_questions_md_message_verbatim(world):
    _, work = world
    raise_conflicts(work, [conflict("size_conflict", [PART_A])])
    rendered = render_questions_md(work)
    assert code_span(MESSAGE) in rendered.text
    assert UNTRANSLATED not in rendered.text
    assert rendered.summary["untranslated_codes"] == []


def test_questions_md_files_it_under_its_own_topic(world):
    _, work = world
    raise_conflicts(work, [conflict("size_conflict", [PART_A])])
    rendered = render_questions_md(work)
    assert rendered.summary["by_topic"]["part-conflicts"] == 1 and "other" not in rendered.summary["by_topic"]
    assert "### Mâu thuẫn giữa các phần (1)" in rendered.text
    assert "### Khác" not in rendered.text


@pytest.mark.parametrize(
    ("a", "b", "same"),
    [
        ("1500x2400", "1500\u00d72400", True),
        ("1500 x 2400", "1500x2400", True),
        ("Ø500", "ø500", True),
        ("1500x2400", "2400x1500", True),  # same numbers, any order
        ("(SL: 7)", "7", True),
        ("B22.5(M300)", "B25(M350)", False),  # no standalone number: only the text compare applies
        ("B22.5(M300)", "b22.5 (m300)", True),
        ("1500x2400", "900x900", False),
        ("seven", "7", False),  # no number on one side
        ("", "", True),
        ("5", "", False),
    ],
)
def test_same_value(a, b, same):
    from tekla_harness.part_values import same_value

    assert same_value(a, b) is same and same_value(b, a) is same
