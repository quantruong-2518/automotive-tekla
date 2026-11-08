"""lifecycle: questions closed by other answers or selections (synthetic work folders)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tekla_harness.grid_system import run_grid_systems
from tekla_harness.lifecycle import closures
from tekla_harness.questions import Closure, QuestionsError, load_ledger
from test_grid_system import (
    Work,
    _gs_questions,
    _ledger_work,
    _one,
    _set_answers,
    _two_buildings,
    ans,
    plan,
)


def _closures(work: Path) -> dict[str, Closure]:
    return closures(work, load_ledger(work, None, create=False))


def _select(work: Path, values: dict[str, Any]) -> dict[str, Any]:
    select = _one(_gs_questions(work), "grid_system_select")
    return {**ans("grid_system_select", None, values), "key": select["key"], "question_id": select["id"]}


# --- grid-system conflicts (fix 5a) ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("values", "reason"),
    [
        ({"systems": ["S001"]}, "not_selected"),
        ({"systems": ["S001", "S002"], "separate": ["S001", "S002"]}, "separate"),
    ],
)
def test_a_conflict_the_select_answer_settles_is_closed_by_the_select_question(
    tmp_path, example, values, reason
):
    work = _ledger_work(_two_buildings(tmp_path, example))
    run_grid_systems(work, svg=False)
    assert _closures(work) == {}  # an open conflict
    answer = _select(work, values)
    _set_answers(work, [answer])
    assert _closures(work) == {}  # grid-systems.json predates the answer: nothing closes until the rerun
    run_grid_systems(work, svg=False)
    conflict = _one(_gs_questions(work), "grid_system_conflict")
    assert _closures(work) == {conflict["key"]: Closure(answer["question_id"], reason)}


@pytest.mark.parametrize("tamper", ["select_obsolete", "key_of_another_code"])
def test_a_conflict_closure_needs_a_live_select_question_and_a_conflict_entry(tmp_path, example, tamper):
    """The closure contract: the closing question is live and answered, and the reason fits the closed
    question's code (a damaged or older registry must not close anything)."""
    work = _ledger_work(_two_buildings(tmp_path, example))
    run_grid_systems(work, svg=False)
    answer = _select(work, {"systems": ["S001"]})
    _set_answers(work, [answer])
    run_grid_systems(work, svg=False)
    conflict = _one(_gs_questions(work), "grid_system_conflict")["key"]
    assert conflict in _closures(work)
    path = work / "question-registry.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    if tamper == "select_obsolete":
        registry["questions"][answer["key"]]["status"] = "obsolete"
    else:
        registry["questions"][conflict]["code"] = "grid_system_units_unconfirmed"
    path.write_text(json.dumps(registry), encoding="utf-8")
    assert conflict not in _closures(work)


def test_a_conflict_left_open_by_the_select_answer_is_not_closed(tmp_path, example):
    work = _ledger_work(_two_buildings(tmp_path, example))
    run_grid_systems(work, svg=False)
    _set_answers(work, [_select(work, {"systems": ["S001", "S002"]})])
    run_grid_systems(work, svg=False)
    assert _closures(work) == {}


def test_a_grid_systems_document_of_another_inventory_closes_nothing(tmp_path, example):
    work = _ledger_work(_two_buildings(tmp_path, example))
    run_grid_systems(work, svg=False)
    _set_answers(work, [_select(work, {"systems": ["S001"]})])
    run_grid_systems(work, svg=False)
    assert _closures(work) != {}
    inventory = work / "inventory.json"
    inventory.write_text(inventory.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert _closures(work) == {}


def test_no_grid_systems_document_closes_nothing_and_a_broken_one_is_an_error(tmp_path, example):
    work = _ledger_work(_two_buildings(tmp_path, example))
    assert _closures(work) == {}
    (work / "grid-systems.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(QuestionsError) as caught:
        _closures(work)
    assert caught.value.exit_code == 1 and "grid-systems.json" in str(caught.value)
    (work / "grid-systems.json").write_text(json.dumps({"schema_version": "0.1"}), encoding="utf-8")
    with pytest.raises(QuestionsError) as caught:
        _closures(work)
    assert caught.value.exit_code == 1 and "invalid" in str(caught.value)


# --- read-structure questions citing only rejected grid systems (fix 5b) ------------------------------
# _two_buildings: plans.dxf, S001 = views V001 V002 (families F001-F004), S002 = V003 V004 (F005-F008).


def _registry(work: Path) -> dict[str, Any]:
    return json.loads((work / "question-registry.json").read_text(encoding="utf-8"))


def _add(
    work: Path, producer: str, code: str, file: str | None, *, blocking: bool = True, status: str = "open"
) -> tuple[str, str]:
    """Register one question of `producer` (as its run would) and return (key, id)."""
    registry = _registry(work)
    qid = f"Q-{registry['next_id']:03d}"
    key = f"{registry['next_id']:016x}"
    sha = None
    if file is not None:
        rows = json.loads((work / "inventory.json").read_text(encoding="utf-8"))["files"]
        sha = next(r["sha256"] for r in rows if r["path"] == file)
    registry["questions"][key] = {
        "id": qid, "code": code, "file": file, "producer": producer, "status": status,
        "first_seen_run": 1, "last_seen_run": 1, "blocking": blocking, "file_sha256": sha,
    }  # fmt: skip
    registry["next_id"] += 1
    (work / "question-registry.json").write_text(json.dumps(registry), encoding="utf-8")
    return key, qid


def _structure_questions(work: Path, specs: list[tuple[str, list[list[str] | None]]]) -> list[str]:
    """Register one read-structure question per (code, families of each ref) and write
    structure-questions.json with them; returns their keys."""
    questions, keys = [], []
    for code, ref_families in specs:
        key, qid = _add(work, "structure", code, "plans.dxf")
        refs = []
        for k, fams in enumerate(ref_families):
            ref: dict[str, Any] = {"file": "plans.dxf", "where": f"V001/F{k:03d}", "found": "x"}
            if fams is not None:
                ref["families"] = fams
            refs.append(ref)
        questions.append(
            {
                "id": qid, "key": key, "code": code, "blocking": True, "file": "plans.dxf", "message": "m",
                "count": len(refs), "truncated": False, "refs": refs, "answer": None,
            }
        )  # fmt: skip
        keys.append(key)
    doc = {"schema_version": "0.1", "kind": "questions", "project_id": "demo-project", "questions": questions}
    doc["summary"] = {
        "questions": len(questions),
        "blocking_questions": len(questions),
        "answered": 0,
        "blocking_open": len(questions),
    }
    (work / "structure-questions.json").write_text(json.dumps(doc), encoding="utf-8")
    return keys


def _selected_world(tmp_path: Path, example: Any, systems: list[str]) -> tuple[Path, str]:
    work = _ledger_work(_two_buildings(tmp_path, example))
    run_grid_systems(work, svg=False)
    answer = _select(work, {"systems": systems})
    _set_answers(work, [answer])
    run_grid_systems(work, svg=False)
    return work, answer["question_id"]


def test_a_question_citing_only_families_of_unselected_systems_is_closed(tmp_path, example):
    work, select_id = _selected_world(tmp_path, example, ["S001"])
    conflict = _one(_gs_questions(work), "grid_system_conflict")["key"]
    rejected, mixed, two_refs, partly_known, unassigned, gate, no_family, axis = _structure_questions(
        work,
        [
            ("grid_label_duplicate", [["F005"], ["F006", "F008"]]),  # S002 only: closed
            ("grid_spacing_cross_sheet_mismatch", [["F001", "F005"]]),  # one family of selected S001
            ("grid_label_missing", [["F007"], ["F003"]]),  # the second ref cites S001
            ("grid_axis_not_parallel", [["F005"], None]),  # a ref that cites no family
            ("grid_label_order_nonmonotonic", [["F009"]]),  # a family of no system
            ("grid_gate1_confirmation", [["F005", "F006", "F007", "F008"]]),  # the gate-1 reason stays
            ("grid_rotated", [[]]),
            ("grid_family_axis_assignment", [["F005", "F007"]]),
        ],
    )
    got = _closures(work)
    assert got == {
        conflict: Closure(select_id, "not_selected"),
        rejected: Closure(select_id, "rejected_systems_only"),
        axis: Closure(select_id, "rejected_systems_only"),
    }
    assert not {mixed, two_refs, partly_known, unassigned, gate, no_family} & set(got)


def test_every_system_selected_or_no_select_answer_closes_no_structure_question(tmp_path, example):
    work, _ = _selected_world(tmp_path, example, ["S001", "S002"])
    (key,) = _structure_questions(work, [("grid_label_duplicate", [["F005"]])])
    assert key not in _closures(work)
    unanswered = _ledger_work(_two_buildings(tmp_path / "b", example))
    run_grid_systems(unanswered, svg=False)
    (key,) = _structure_questions(unanswered, [("grid_label_duplicate", [["F005"]])])
    assert _closures(unanswered) == {}


def test_an_obsolete_structure_question_is_not_closed(tmp_path, example):
    work, _ = _selected_world(tmp_path, example, ["S001"])
    (key,) = _structure_questions(work, [("grid_label_duplicate", [["F005"]])])
    registry = _registry(work)
    registry["questions"][key]["status"] = "obsolete"
    (work / "question-registry.json").write_text(json.dumps(registry), encoding="utf-8")
    assert key not in _closures(work)


def test_a_broken_structure_questions_document_is_an_error(tmp_path, example):
    work, _ = _selected_world(tmp_path, example, ["S001"])
    (work / "structure-questions.json").write_text("[", encoding="utf-8")
    with pytest.raises(QuestionsError) as caught:
        _closures(work)
    assert caught.value.exit_code == 1 and "structure-questions.json" in str(caught.value)


# --- grid_units_doubt closes with the file's units answer (fix 5c) ------------------------------------


def _units_answer(key: str, qid: str, status: str = "active") -> dict[str, Any]:
    answer = {**ans("units_confirm_all", "plans.dxf", {"unit": "mm"}, status), "key": key, "question_id": qid}
    return {**answer, "stale_reason": "the input file was changed"} if status == "stale" else answer


def test_grid_units_doubt_closes_once_the_file_units_question_is_answered(tmp_path, example):
    work = _ledger_work(_two_buildings(tmp_path, example))
    units_key, units_id = _add(work, "intake", "units_confirm_all", "plans.dxf")
    doubt, _ = _add(work, "structure", "grid_units_doubt", "plans.dxf", blocking=False)
    assert _closures(work) == {}
    _set_answers(work, [_units_answer(units_key, units_id)])
    assert _closures(work) == {doubt: Closure(units_id, "units_answered")}


def test_grid_units_doubt_needs_an_active_answer_on_its_own_file_units_confirm_all(tmp_path, example):
    w = Work(tmp_path, example)
    w.add_file("plans.dxf", [plan("V001", "model#01", 1)])
    w.add_file("other.dxf", [plan("V001", "model#01", 1)])
    work = _ledger_work(w.finish())
    units_key, units_id = _add(work, "intake", "units_confirm_all", "plans.dxf")
    other_key, other_id = _add(work, "intake", "units_confirm_all", "other.dxf")
    suspect_key, suspect_id = _add(work, "intake", "units_suspect", "plans.dxf")
    doubt, _ = _add(work, "structure", "grid_units_doubt", "plans.dxf", blocking=False)
    for answers in (
        [_units_answer(units_key, units_id, status="stale")],
        [{**_units_answer(other_key, other_id), "file": "other.dxf"}],  # another file's units
        [{**_units_answer(suspect_key, suspect_id), "code": "units_suspect"}],  # a legacy units code
    ):
        _set_answers(work, answers)
        assert doubt not in _closures(work), answers
    # the units question of another content of the file (sha changed since) does not count either
    registry = _registry(work)
    registry["questions"][units_key]["file_sha256"] = "0" * 64
    (work / "question-registry.json").write_text(json.dumps(registry), encoding="utf-8")
    _set_answers(work, [_units_answer(units_key, units_id)])
    assert doubt not in _closures(work)
    # and an obsolete units question closes nothing
    registry["questions"][units_key]["file_sha256"] = registry["questions"][doubt]["file_sha256"]
    registry["questions"][units_key]["status"] = "obsolete"
    (work / "question-registry.json").write_text(json.dumps(registry), encoding="utf-8")
    assert doubt not in _closures(work)
