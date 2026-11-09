"""Gate 1 and the grid of a file the detector cannot read (ADR-0013 decisions 2 and 6; tool wave 3 review
C1): `grid_system_missing` closes only from the built result, never from the answer alone; who answered is
part of the grid-system freshness; every used system needs confirmed units and a Tekla grid.

The world (`world3`): test_status.py's two synthetic plans plus notes.dxf, a drawing with text only, so the
detector finds no grid in it and grid-system asks grid_system_missing for it. Everything else is answered by
the engineer. Tests work on a copy.
"""

# ruff: noqa: F811

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from ezdxf.filemanagement import new

from _dxf_fixtures import build_set
from tekla_harness.answers import record_answer
from tekla_harness.grid_system import consumed_answers_digest, run_grid_systems
from tekla_harness.questions import CONFLICT_CODE, GRID_MISSING_CODE, SELECT_CODE
from tekla_harness.questions_md import render_questions_md
from tekla_harness.schemas import validate
from tekla_harness.status import build_status
from test_status import (  # noqa: F401  (pytest fixtures, used by name)
    answer_blocking,
    answer_select,
    base_world,
    by_label,
    find,
    load,
    questions_of,
    ready,
    ready_world,
    rerun_all,
)

GRID = {"dir1_labels": "1,2,3", "dir1_spacings": "6000,6000", "dir2_labels": "A,B", "dir2_spacings": "5000"}


def notes_dxf(path: Path) -> None:
    """A drawing with notes and a section title only: no bubble, no axis."""
    doc = new("R2018", setup=True)
    doc.header["$INSUNITS"] = 4
    msp = doc.modelspace()
    msp.add_text("GENERAL NOTES", dxfattribs={"height": 350}).set_placement((1000, 9000))
    msp.add_text("CONCRETE B25", dxfattribs={"height": 250}).set_placement((1000, 8000))
    msp.add_text("SECTION 1-1", dxfattribs={"height": 250}).set_placement((1000, 7000))
    doc.saveas(path)


@pytest.fixture(scope="module")
def world3(tmp_path_factory) -> Path:
    """Every question answered by the engineer except grid_system_missing on notes.dxf (and the conflict,
    which the select answer's separate= closes)."""
    base = tmp_path_factory.mktemp("w3")
    root = base / "input"
    root.mkdir()
    build_set(root, "set.dxf")
    build_set(root, "other.dxf", sheet2_number="S-777")
    notes_dxf(root / "notes.dxf")
    work = base / "work"
    rerun_all(root, work)
    answer_blocking(work, ("questions.json", "structure-questions.json"))
    run_grid_systems(work)
    answer_select(work)
    for _ in range(2):
        answer_blocking(work, ("grid-system-questions.json",), skip=(CONFLICT_CODE, GRID_MISSING_CODE))
        run_grid_systems(work)
    return base


@pytest.fixture
def w3(world3, tmp_path) -> Path:
    target = tmp_path / "c"
    shutil.copytree(world3, target)
    return target / "work"


def missing_q(work: Path) -> dict[str, Any]:
    return find(questions_of(work, "grid-system-questions.json"), GRID_MISSING_CODE, "notes.dxf")


def built(work: Path) -> list[dict[str, Any]]:
    return [s for s in load(work / "grid-systems.json")["systems"] if s.get("source") == "engineer_answer"]


def grid_step(status: dict[str, Any]) -> dict[str, Any]:
    return by_label(status)["grid-system"]


def reasons_about(status: dict[str, Any], qid: str) -> list[str]:
    return [r for r in status["gate1"]["reasons"] if r.startswith(f"grid systems: {qid} {GRID_MISSING_CODE}")]


def select_all(work: Path, *, leave_out: str | None = None) -> None:
    """The engineer's select answer: every system of this run (but `leave_out`), the detected two separate."""
    select = find(questions_of(work, "grid-system-questions.json"), SELECT_CODE)
    ids = [r["where"] for r in select["refs"] if r["where"] != leave_out]
    systems = load(work / "grid-systems.json")["systems"]
    detected = [s["system_id"] for s in systems if not s.get("source_answer")]
    values = {"systems": ",".join(ids), "separate": ",".join(detected)}
    record_answer(work, select["id"], "test answer", "tester", values, role="engineer")


def answer_new_axes(work: Path) -> None:
    """The engineer gives Tekla X / Y to every system still waiting for it (an answer-built system's
    directions carry no angle: dir1 X, dir2 Y)."""
    for q in questions_of(work, "grid-system-questions.json"):
        if q["code"] == "grid_system_axis_unassigned" and q["blocking"] and q["answer"] is None:
            values = {"dir1": "X", "dir2": "Y"}
            record_answer(work, q["id"], "test answer", "tester", values, role="engineer")


def test_world3_is_blocked_by_the_missing_grid_only(w3):
    q = missing_q(w3)
    status = build_status(w3)
    assert status["gate1"]["reasons"] == [f"grid-system: 1 blocking question(s) open ({q['id']})"]


# --- C1.1: who answered is part of the grid-system freshness ----------------------------------------------


def test_the_answers_digest_covers_who_answered():
    row = {
        "key": "0123456789abcdef", "question_id": "Q-001", "code": "units_confirm_all", "file": "a.dxf",
        "answer_text": "mm", "values": {"unit": "mm"}, "answered_by": "x", "answered_on": "2026-11-09",
        "status": "active",
    }  # fmt: skip
    roles = [{**row, "answered_by_role": r} for r in ("engineer", "simulated")] + [row]
    digests = {consumed_answers_digest([a]) for a in roles}
    assert len(digests) == 3  # engineer, simulated and no role recorded differ


def test_a_grid_answer_given_again_by_the_engineer_makes_grid_systems_stale(w3):
    """C1 scenario 1: simulated, rerun, then the engineer with the same values and no rerun."""
    q = missing_q(w3)
    record_answer(w3, q["id"], "proposed", "agent", GRID, role="simulated")
    run_grid_systems(w3)
    assert built(w3) == []
    record_answer(w3, q["id"], "confirmed", "A. Nguyen", GRID, role="engineer")
    status = build_status(w3)
    assert grid_step(status)["outputs"]["status"] == "stale"
    assert q["id"] in grid_step(status)["blocking_open_ids"]
    assert status["gate1"]["ready_for_gate1"] is False
    run_grid_systems(w3)  # now the system is built from the engineer's answer, and the question closes
    (system,) = built(w3)
    assert system["source_answer"]["key"] == q["key"]
    status = build_status(w3)
    assert grid_step(status)["outputs"]["status"] == "fresh"
    assert q["id"] not in grid_step(status)["blocking_open_ids"]
    assert reasons_about(status, q["id"]) == []


def test_a_units_answer_given_again_by_the_engineer_makes_grid_systems_stale(ready):
    """C1 scenario 2: units simulated, rerun (proposed_simulated), then the engineer, same unit, no rerun."""
    _, work = ready
    q = find(questions_of(work, "questions.json"), "units_confirm_all", "set.dxf")
    record_answer(work, q["id"], "mm (agent)", "agent", {"unit": "mm"}, role="simulated")
    run_grid_systems(work)
    record_answer(work, q["id"], "mm", "A. Nguyen", {"unit": "mm"}, role="engineer")
    status = build_status(work)
    assert grid_step(status)["outputs"]["status"] == "stale"
    assert status["gate1"]["ready_for_gate1"] is False


# --- C1.2: every used system has confirmed units and a Tekla grid -----------------------------------------


def patch_system(work: Path, change: dict[str, Any]) -> str:
    """Change the first used system of a fresh grid-systems.json (fingerprints kept: the outputs stay
    fresh), as an older or hand-edited document would have it."""
    path = work / "grid-systems.json"
    doc = load(path)
    system = doc["systems"][0]
    for k, v in change.items():
        system[k] = {**system[k], **v} if isinstance(v, dict) else v
    assert validate("grid-system", doc) == []
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return system["system_id"]


@pytest.mark.parametrize("units", ["proposed_simulated", "not_confirmed"])
def test_a_used_system_whose_units_are_not_confirmed_blocks_gate1(ready, units):
    _, work = ready
    assert build_status(work)["gate1"]["ready_for_gate1"] is True
    sid = patch_system(work, {"units": {"status": units, "reason": "units answered by a non-engineer role"}})
    status = build_status(work)
    assert grid_step(status)["outputs"]["status"] == "fresh"
    assert status["gate1"]["ready_for_gate1"] is False
    (reason,) = [r for r in status["gate1"]["reasons"] if r.startswith(f"grid systems: {sid} ")]
    assert f"units are {units}" in reason and "units_confirm_all" in reason


def test_a_used_system_without_a_tekla_grid_blocks_gate1(ready):
    _, work = ready
    sid = patch_system(work, {"tekla_grid": None})
    status = build_status(work)
    assert status["gate1"]["ready_for_gate1"] is False
    (reason,) = [r for r in status["gate1"]["reasons"] if r.startswith(f"grid systems: {sid} ")]
    assert "no Tekla grid" in reason and "harness grid-system" in reason


# --- C1.3: grid_system_missing closes only from the built result ------------------------------------------


@pytest.mark.parametrize(
    "values",
    [
        {"dir1_spacings": [6000]},  # one spacing for three labels
        {"dir2_labels": ["A", "A "]},  # the same label once stripped
    ],
    ids=["spacings-count", "labels-blank-twin"],
)
def test_an_engineer_grid_answer_that_built_nothing_leaves_the_question_open(w3, values):
    """answers.json edited by hand: values `harness answer` would refuse, that grid-system builds nothing
    from. The question stays open with a reason, outputs fresh."""
    q = missing_q(w3)
    record_answer(w3, q["id"], "grid", "A. Nguyen", GRID, role="engineer")
    path = w3 / "answers.json"
    doc = load(path)
    (row,) = [a for a in doc["answers"] if a["key"] == q["key"] and a["status"] == "active"]
    row["values"] = {**row["values"], **values}
    assert validate("answers", doc) == []
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    run_grid_systems(w3)
    assert built(w3) == []
    status = build_status(w3)
    assert grid_step(status)["outputs"]["status"] == "fresh"
    assert q["id"] in grid_step(status)["blocking_open_ids"]
    (reason,) = reasons_about(status, q["id"])
    assert "built no grid system" in reason and f"harness answer {w3} {q['id']} " in reason
    assert status["gate1"]["ready_for_gate1"] is False


def test_an_answer_built_system_left_out_by_the_select_answer_keeps_the_question_open(w3):
    """ADR-0013 decision 1: usable = not left out by the engineer's select answer. The file then has no
    used grid, so gate 1 stays shut, with a reason naming the system and the select question."""
    q = missing_q(w3)
    record_answer(w3, q["id"], "grid", "A. Nguyen", GRID, role="engineer")
    run_grid_systems(w3)
    (system,) = built(w3)
    sid = system["system_id"]
    select_all(w3, leave_out=sid)
    run_grid_systems(w3)
    assert [s["system_id"] for s in built(w3)] == [sid]
    status = build_status(w3)
    assert grid_step(status)["outputs"]["status"] == "fresh"
    assert q["id"] in grid_step(status)["blocking_open_ids"]
    (reason,) = reasons_about(status, q["id"])
    assert f"{sid}, built from its answer, is left out by the {SELECT_CODE} answer" in reason
    assert status["gate1"]["ready_for_gate1"] is False
    # selected again: the question closes
    select_all(w3)
    run_grid_systems(w3)
    status = build_status(w3)
    assert q["id"] not in grid_step(status)["blocking_open_ids"] and reasons_about(status, q["id"]) == []


def test_an_answer_built_system_closes_the_question_only_while_grid_systems_is_fresh(w3):
    q = missing_q(w3)
    record_answer(w3, q["id"], "grid", "A. Nguyen", GRID, role="engineer")
    run_grid_systems(w3)
    assert q["id"] not in grid_step(build_status(w3))["blocking_open_ids"]
    select_all(w3)  # an answer grid-system reads, not yet applied: the built result is not current
    status = build_status(w3)
    assert grid_step(status)["outputs"]["status"] == "stale"
    assert q["id"] in grid_step(status)["blocking_open_ids"]


def test_an_answer_built_system_that_disagrees_with_a_detected_one_keeps_gate1_shut(w3):
    """Review M1: the engineer gives notes.dxf the labels of S001 at other spacings; the systems conflict,
    and only the select answer (separate=, or leaving one out) closes it, like two detected systems."""
    detected = [s for s in load(w3 / "grid-systems.json")["systems"] if s.get("source") != "engineer_answer"]
    d1, d2 = detected[0]["directions"]
    values = {
        "dir1_labels": ",".join(d1["labels"]),
        "dir1_spacings": ",".join(str(int(v) + 1000) for v in d1["spacings"]),
        "dir2_labels": ",".join(d2["labels"]),
        "dir2_spacings": ",".join(str(int(v) + 1000) for v in d2["spacings"]),
    }
    q = missing_q(w3)
    record_answer(w3, q["id"], "grid", "A. Nguyen", values, role="engineer")
    run_grid_systems(w3)
    (system,) = built(w3)
    sid = system["system_id"]
    select_all(w3)  # every system used; only the detected two declared separate
    run_grid_systems(w3)
    answer_new_axes(w3)
    run_grid_systems(w3)
    doc = load(w3 / "grid-systems.json")
    open_conflicts = [c for c in doc["conflicts"] if sid in c["systems"] and c["closed_by"] is None]
    assert open_conflicts and all(c["blocking"] for c in open_conflicts)
    status = build_status(w3)
    assert status["gate1"]["ready_for_gate1"] is False
    assert any(
        f" and {sid} conflict (" in r or f"grid systems: {sid} and " in r for r in status["gate1"]["reasons"]
    )
    # declared a separate building too: the conflicts close, gate 1 opens
    select = find(questions_of(w3, "grid-system-questions.json"), SELECT_CODE)
    every = ",".join(r["where"] for r in select["refs"])
    record_answer(
        w3, select["id"], "all separate", "A. Nguyen", {"systems": every, "separate": every}, role="engineer"
    )
    run_grid_systems(w3)
    assert build_status(w3)["gate1"]["ready_for_gate1"] is True


def test_questions_md_shows_a_grid_answer_that_built_nothing_as_open(w3):
    q = missing_q(w3)
    record_answer(w3, q["id"], "grid", "A. Nguyen", GRID, role="engineer")
    lines = render_questions_md(w3).text.splitlines()
    section2 = next(i for i, line in enumerate(lines) if line.startswith("## 2. "))
    section3 = next(i for i, line in enumerate(lines) if line.startswith("## 3. "))
    heading = next(i for i, line in enumerate(lines) if line.startswith("#") and q["id"] in line)
    assert section2 < heading < section3
    answer = next(line for line in lines[heading:] if line.startswith("- **Trả lời:**"))
    assert "chưa đóng" in answer and "không phải kỹ sư" not in answer
    run_grid_systems(w3)  # built: the question is answered (section 4)
    lines = render_questions_md(w3).text.splitlines()
    section4 = next(i for i, line in enumerate(lines) if line.startswith("## 4. "))
    assert not any(line.startswith("#") and q["id"] in line for line in lines[:section4])
    assert any(q["id"] in line for line in lines[section4:])
