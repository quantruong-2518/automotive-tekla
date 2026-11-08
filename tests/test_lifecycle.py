"""lifecycle: questions closed by other answers or selections (synthetic work folders)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tekla_harness.grid_system import run_grid_systems
from tekla_harness.lifecycle import closures
from tekla_harness.questions import Closure, QuestionsError, load_ledger
from test_grid_system import _gs_questions, _ledger_work, _one, _set_answers, _two_buildings, ans


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
