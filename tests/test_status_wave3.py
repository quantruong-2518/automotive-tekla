"""`harness status` and the tool wave 3 producers (package C): gate1.closed is always written (W5), and what a
simulated answer only proposes (grid-system `proposed_simulated`, `proposed_closed_by`, a simulated
grid_system_missing answer) never counts as confirmed, answered or closed.

The world is test_status.py's; its fixtures are imported by name, so a test parameter re-binds them (F811).
Producer package G writes the proposed_* fields; until it lands they are patched into a fresh
grid-systems.json, keeping its inventory and answers fingerprints so the outputs stay fresh.
"""

# ruff: noqa: F811

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tekla_harness.answers import record_answer
from tekla_harness.grid_system import run_grid_systems
from tekla_harness.questions import GRID_MISSING_CODE
from tekla_harness.questions_md import render_questions_md
from tekla_harness.schemas import validate
from tekla_harness.status import build_status
from test_status import (  # noqa: F401  (pytest fixtures, used by name)
    answer_select,
    base_world,
    by_label,
    load,
    ready,
    ready_world,
    world,
)

GRID = {
    "dir1_labels": "1,2,3",
    "dir1_spacings": "3130,3540",
    "dir2_labels": "A,B",
    "dir2_spacings": "4250",
}


def patch_grid_systems(work: Path, mutate: Callable[[dict[str, Any]], None]) -> None:
    path = work / "grid-systems.json"
    doc = load(path)
    mutate(doc)
    assert validate("grid-system", doc) == []  # the shape package G writes
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


# --- W5: gate1.closed is always there ------------------------------------------------------------------


def test_gate1_closed_is_written_empty_when_nothing_is_closed(world):
    _, work = world
    status = build_status(work)
    assert status["gate1"]["closed"] == []
    assert validate("status", status) == []


def test_gate1_closed_lists_the_closures_when_there_are_some(ready):
    _, work = ready
    closed = build_status(work)["gate1"]["closed"]
    assert closed and all(row["reason"] == "separate" for row in closed)


# --- proposed_simulated never counts as answered --------------------------------------------------------


def test_a_proposed_simulated_axis_assignment_gives_no_tekla_axis(ready):
    _, work = ready
    assert build_status(work)["gate1"]["ready_for_gate1"] is True
    sid: list[str] = []

    def simulated_axes(doc: dict[str, Any]) -> None:
        system = doc["systems"][0]
        sid.append(system["system_id"])
        system["axis_assignment"] = {"status": "proposed_simulated", "reason": "simulated answer Q-024"}

    patch_grid_systems(work, simulated_axes)
    gate1 = build_status(work)["gate1"]
    assert gate1["ready_for_gate1"] is False
    assert any(r.startswith(f"grid systems: {sid[0]} has no Tekla X/Y") for r in gate1["reasons"])


def test_a_conflict_a_simulated_answer_would_close_stays_open(ready):
    _, work = ready
    answer_select(work, separate=False)  # the engineer: every system used, none declared separate
    run_grid_systems(work)
    before = build_status(work)
    conflicts = [c for c in load(work / "grid-systems.json")["conflicts"] if c["closed_by"] is None]
    assert conflicts and before["gate1"]["ready_for_gate1"] is False
    assert any(" conflict (" in r for r in before["gate1"]["reasons"])

    def proposed(doc: dict[str, Any]) -> None:
        for c in doc["conflicts"]:
            if c["closed_by"] is None:
                c["proposed_closed_by"] = "separate"

    patch_grid_systems(work, proposed)
    after = build_status(work)
    assert after == before  # proposed_closed_by closes nothing
    ids = {e["id"] for k, e in load(work / "question-registry.json")["questions"].items()}
    assert all(row["id"] in ids for row in after["gate1"]["closed"])
    conflict_ids = {
        e["id"]
        for k, e in load(work / "question-registry.json")["questions"].items()
        if any(c["question_key"] == k for c in conflicts)
    }
    assert conflict_ids and not conflict_ids & {row["id"] for row in after["gate1"]["closed"]}


def inject_missing(work: Path) -> str:
    """A live, blocking grid-system grid_system_missing question on set.dxf (package G raises it), in the
    registry and in grid-system-questions.json (questions.md lists the documents' questions)."""
    registry = load(work / "question-registry.json")
    number = registry["next_id"]
    qid, key = f"Q-{number:03d}", f"{number:016x}"
    registry["questions"][key] = {
        "id": qid, "code": GRID_MISSING_CODE, "file": "set.dxf", "producer": "grid-system", "status": "open",
        "first_seen_run": registry["runs"], "last_seen_run": registry["runs"], "blocking": True,
        "file_sha256": None,
    }  # fmt: skip
    registry["next_id"] = number + 1
    (work / "question-registry.json").write_text(json.dumps(registry), encoding="utf-8")
    path = work / "grid-system-questions.json"
    doc = load(path)
    doc["questions"].append(
        {
            "id": qid, "key": key, "code": GRID_MISSING_CODE, "blocking": True, "file": "set.dxf",
            "message": "No usable grid system on set.dxf", "count": 1, "truncated": False,
            "refs": [{"file": "set.dxf", "where": "model#01", "found": "0 usable grid systems"}],
            "answer": None,
        }
    )  # fmt: skip
    assert validate("intake", doc) == []
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return qid


def words_only_reasons(status: dict[str, Any], qid: str) -> list[str]:
    prefix = f"grid systems: {qid} {GRID_MISSING_CODE} (set.dxf) was answered in words only"
    return [r for r in status["gate1"]["reasons"] if r.startswith(prefix)]


def test_a_simulated_grid_system_missing_answer_leaves_the_question_open(ready):
    _, work = ready
    qid = inject_missing(work)
    record_answer(work, qid, "lưới 1-3, A-B (simulated)", "agent", GRID, role="simulated")
    status = build_status(work)
    grid = by_label(status)["grid-system"]
    assert qid in grid["blocking_open_ids"]
    row = {"question_id": qid, "code": GRID_MISSING_CODE, "file": "set.dxf", "role": "simulated"}
    assert row in status["gate1"]["non_engineer_answers"]
    assert status["gate1"]["ready_for_gate1"] is False
    assert any(r.startswith(f"answers: {qid} {GRID_MISSING_CODE}") for r in status["gate1"]["reasons"])
    assert words_only_reasons(status, qid) == []  # it has values: the role is what keeps it open


def test_an_engineer_words_only_grid_system_missing_answer_does_not_close_it(ready):
    """ADR-0013 decision 2: an answer without values builds nothing, so the file still has no usable grid
    system and the question stays open, even when the engineer gave the answer."""
    _, work = ready
    qid = inject_missing(work)
    record_answer(work, qid, "không đọc được lưới", "A. Nguyen", {}, role="engineer")
    status = build_status(work)
    assert qid in by_label(status)["grid-system"]["blocking_open_ids"]
    assert status["gate1"]["ready_for_gate1"] is False
    assert qid not in [a["question_id"] for a in status["gate1"].get("non_engineer_answers", [])]
    (reason,) = words_only_reasons(status, qid)
    # the reason tells the engineer to give the values, with the exact command
    assert f"harness answer {work} {qid} " in reason and "--role engineer" in reason
    for key in ("dir1_labels", "dir1_spacings", "dir2_labels", "dir2_spacings"):
        assert f"--value {key}=" in reason, key
    assert "[--value sheet=" in reason and "harness grid-system" in reason


def test_an_engineer_answer_with_the_grid_values_alone_does_not_close_it(ready):
    """ADR-0013 decision 6 (review C1): the question closes only from the built result, a fresh
    grid-systems.json holding a system built from this answer (test_grid_gate.py), never from the values."""
    _, work = ready
    qid = inject_missing(work)
    record_answer(work, qid, "lưới 1-3, A-B", "A. Nguyen", GRID, role="engineer")
    status = build_status(work)
    assert qid in by_label(status)["grid-system"]["blocking_open_ids"]
    assert words_only_reasons(status, qid) == []
    assert status["gate1"]["ready_for_gate1"] is False


def test_a_words_only_answer_superseded_by_values_is_no_longer_words_only(ready):
    _, work = ready
    qid = inject_missing(work)
    record_answer(work, qid, "chưa đọc được", "A. Nguyen", {}, role="engineer")
    record_answer(work, qid, "lưới 1-3, A-B", "A. Nguyen", GRID, role="engineer")
    status = build_status(work)
    assert qid in by_label(status)["grid-system"]["blocking_open_ids"]  # not built yet
    assert words_only_reasons(status, qid) == []


def answer_line(work: Path, qid: str) -> str:
    lines = render_questions_md(work).text.splitlines()
    heading = next(i for i, line in enumerate(lines) if line.startswith("#") and qid in line)
    return next(line for line in lines[heading:] if line.startswith("- **Trả lời:**"))


def test_questions_md_a_simulated_words_only_answer_is_shown_as_not_the_engineers(ready):
    """The role comes first: the engineer must answer it themselves, with the values."""
    _, work = ready
    qid = inject_missing(work)
    record_answer(work, qid, "không đọc được lưới", "agent", {}, role="simulated")
    line = answer_line(work, qid)
    assert "không phải kỹ sư" in line and "chỉ có lời" not in line
    assert words_only_reasons(build_status(work), qid) == []  # the role reason names it instead


def test_questions_md_does_not_show_a_words_only_grid_answer_as_closing(ready):
    _, work = ready
    qid = inject_missing(work)
    record_answer(work, qid, "không đọc được lưới", "A. Nguyen", {}, role="engineer")
    rendered = render_questions_md(work)
    lines = rendered.text.splitlines()
    heading = next(i for i, line in enumerate(lines) if line.startswith("#") and qid in line)
    answer = next(line for line in lines[heading:] if line.startswith("- **Trả lời:**"))
    assert "chỉ có lời" in answer and "chưa đóng" in answer
    assert "không phải kỹ sư" not in answer  # it IS the engineer's answer
    assert "`--value dir1_labels=" in answer and "`[--value sheet=" in answer  # sheet is optional
    # it is listed with the open blocking questions (section 2), not with the answered ones (section 4)
    section2 = next(i for i, line in enumerate(lines) if line.startswith("## 2. "))
    section3 = next(i for i, line in enumerate(lines) if line.startswith("## 3. "))
    assert section2 < heading < section3
    answered = "\n".join(lines[next(i for i, line in enumerate(lines) if line.startswith("## 4. ")) :])
    assert qid not in answered.split("## 5. ")[0]
