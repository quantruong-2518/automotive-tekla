"""`harness answer` structured values added in tool wave 3: the grid_system_missing answer (ADR-0013 §2)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tekla_harness.answers import check_values, grid_answer_values, record_answer
from tekla_harness.cli import main
from tekla_harness.questions import (
    GRID_ANSWER_KEYS,
    GRID_ANSWER_SHEET_KEY,
    GRID_MISSING_CODE,
    QuestionsError,
    load_ledger,
    question_group,
)
from tekla_harness.schemas import validate

PROJECT = "demo-answers"
FILE = "a.dxf"
GRID = {
    "dir1_labels": "1,2,3",
    "dir1_spacings": "3130,3540.5",
    "dir2_labels": "A,B",
    "dir2_spacings": "4250",
}
STORED = {
    "dir1_labels": ["1", "2", "3"],
    "dir1_spacings": [3130, 3540.5],
    "dir2_labels": ["A", "B"],
    "dir2_spacings": [4250],
}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def answers_doc(values: dict[str, Any]) -> dict[str, Any]:
    answer = {
        "key": "0123456789abcdef",
        "question_id": "Q-001",
        "code": GRID_MISSING_CODE,
        "file": FILE,
        "answer_text": "t",
        "values": values,
        "answered_by": "x",
        "answered_by_role": "engineer",
        "answered_on": "2026-11-09",
        "status": "active",
    }
    return {"schema_version": "0.1", "project_id": PROJECT, "answers": [answer]}


def test_the_seam_keys_are_the_ones_checked():
    assert set(GRID) == set(GRID_ANSWER_KEYS) and GRID_ANSWER_SHEET_KEY == "sheet"


@pytest.mark.parametrize(
    "values, stored",
    [
        (GRID, STORED),
        ({**GRID, "sheet": "model#05"}, {**STORED, "sheet": "model#05"}),
        ({**GRID, "sheet": " model#05 "}, {**STORED, "sheet": "model#05"}),
        (  # blanks around the items are dropped
            {**GRID, "dir1_labels": " 1, 2 ,3 ", "dir1_spacings": " 3130 , 3540.5"},
            STORED,
        ),
        ({**GRID, "dir2_spacings": "4250.0"}, {**STORED, "dir2_spacings": [4250.0]}),
        ({**GRID, "dir2_spacings": ".5"}, {**STORED, "dir2_spacings": [0.5]}),
        ({**GRID, "dir2_spacings": "3."}, {**STORED, "dir2_spacings": [3.0]}),
        ({}, {}),  # words only: recorded, builds nothing
    ],
)
def test_grid_system_missing_values_are_stored_as_arrays(values, stored):
    assert check_values(GRID_MISSING_CODE, values) == []
    out = grid_answer_values(values)
    assert out == stored
    for key in ("dir1_spacings", "dir2_spacings"):  # 3130 stays an int, 3540.5 and 4250.0 are floats
        assert [type(x) for x in out.get(key, [])] == [type(x) for x in stored.get(key, [])]
    assert all(isinstance(x, str) for k in ("dir1_labels", "dir2_labels") for x in out.get(k, []))
    assert validate("answers", answers_doc(out)) == []  # the schema says the same as the command


@pytest.mark.parametrize(
    "values, words",
    [
        ({k: v for k, v in GRID.items() if k != "dir1_labels"}, "dir1_labels"),
        ({k: v for k, v in GRID.items() if k != "dir1_spacings"}, "dir1_spacings"),
        ({k: v for k, v in GRID.items() if k != "dir2_labels"}, "dir2_labels"),
        ({k: v for k, v in GRID.items() if k != "dir2_spacings"}, "dir2_spacings"),
        ({"sheet": "model#05"}, "dir1_labels"),  # a sheet alone is not a grid
        ({**GRID, "dir3_labels": "X,Y"}, "dir3_labels"),
        ({**GRID, "unit": "mm"}, "unit"),
        ({**GRID, "sheet": " "}, "sheet"),
        ({**GRID, "dir1_labels": "1", "dir1_spacings": ""}, "at least 2"),
        ({**GRID, "dir2_labels": "A,,B", "dir2_spacings": "1,2"}, "blank"),
        ({**GRID, "dir2_labels": "A, ", "dir2_spacings": "1"}, "blank"),
        ({**GRID, "dir2_labels": "A,A"}, "distinct"),
        ({**GRID, "dir2_labels": "A, A"}, "distinct"),
        ({**GRID, "dir1_spacings": "3130,0"}, "'0'"),
        ({**GRID, "dir1_spacings": "3130,0.0"}, "'0.0'"),
        ({**GRID, "dir1_spacings": "3130,-5"}, "'-5'"),
        ({**GRID, "dir1_spacings": "3130,inf"}, "'inf'"),
        ({**GRID, "dir1_spacings": "3130,nan"}, "'nan'"),
        ({**GRID, "dir1_spacings": "3130,1e3"}, "'1e3'"),
        ({**GRID, "dir1_spacings": "3130,3_540"}, "'3_540'"),
        ({**GRID, "dir1_spacings": "3130,abc"}, "'abc'"),
        ({**GRID, "dir1_spacings": "3130,"}, "''"),
        ({**GRID, "dir1_spacings": "3130,+5"}, "'+5'"),
        ({**GRID, "dir1_spacings": "3130,٣"}, "'٣'"),  # a non-ASCII digit is not a drawing number
        ({**GRID, "dir1_spacings": "3130"}, "one fewer"),  # 3 labels need 2 spacings
        ({**GRID, "dir1_spacings": "3130,3540,10"}, "one fewer"),
        ({**GRID, "dir2_spacings": "4250,1"}, "one fewer"),
    ],
)
def test_grid_system_missing_values_refused(values, words):
    problems = check_values(GRID_MISSING_CODE, values)
    assert problems, values
    assert words in "; ".join(problems)


def test_a_malformed_spacing_is_reported_once_without_a_count_complaint():
    (problem,) = check_values(GRID_MISSING_CODE, {**GRID, "dir1_spacings": "3130 mm"})
    assert "'3130 mm' is not a number" in problem and "one fewer" not in problem


def test_a_count_mismatch_is_refused_by_the_command_though_the_schema_keeps_it():
    """JSON Schema cannot say 'one spacing fewer than the labels': harness answer checks it."""
    values = {**GRID, "dir1_spacings": "3130"}
    assert check_values(GRID_MISSING_CODE, values) != []
    assert validate("answers", answers_doc({**STORED, "dir1_spacings": [3130]})) == []


def test_grid_answer_contradicts_drawing_takes_no_value():
    assert check_values("grid_answer_contradicts_drawing", {}) == []
    assert check_values("grid_answer_contradicts_drawing", {"dir1_labels": "1,2"}) != []


# --- end to end: harness answer records the arrays and ledger.check accepts them ------------------------


@pytest.fixture
def work(tmp_path) -> tuple[Path, str]:
    """A work folder whose registry holds one grid-system grid_system_missing question (no producer raises
    it on this branch yet: package G)."""
    ledger = load_ledger(tmp_path, PROJECT, create=True)
    refs = [{"file": FILE, "where": "model#05", "found": "0 usable grid systems"}]
    (q,) = ledger.sync(
        "grid-system", [question_group(GRID_MISSING_CODE, True, "m", refs, file=FILE)], {FILE: "ab" * 32}
    )
    ledger.write()
    return tmp_path, q["id"]


def test_record_answer_stores_the_grid_as_arrays(work):
    path, qid = work
    values = {**GRID, "sheet": "model#05"}
    result = record_answer(path, qid, "lưới trục 1-3, A-B", "A. Nguyen", values, role="engineer")
    assert result["answer"]["values"] == {**STORED, "sheet": "model#05"}
    doc = load(path / "answers.json")
    assert validate("answers", doc) == []
    (answer,) = doc["answers"]
    assert answer["values"] == {**STORED, "sheet": "model#05"} and answer["status"] == "active"
    assert load(path / "question-registry.json")["questions"][answer["key"]]["status"] == "answered"


def test_record_answer_takes_words_only(work):
    path, qid = work
    result = record_answer(path, qid, "chưa đọc được lưới", "A. Nguyen", {}, role="engineer")
    assert result["answer"]["values"] == {}
    assert validate("answers", load(path / "answers.json")) == []


def test_record_answer_refuses_bad_grid_values_and_writes_nothing(work):
    path, qid = work
    before = {p.name: p.read_bytes() for p in path.glob("*.json")}
    with pytest.raises(QuestionsError) as caught:
        record_answer(path, qid, "t", "A. Nguyen", {**GRID, "dir1_spacings": "3130"}, role="engineer")
    assert caught.value.exit_code == 1
    assert GRID_MISSING_CODE in str(caught.value) and "one fewer" in str(caught.value)
    assert {p.name: p.read_bytes() for p in path.glob("*.json")} == before


def test_cli_answer_with_the_grid_keys(work, capsys):
    path, qid = work
    argv = ["answer", str(path), qid, "--text", "lưới", "--by", "A. Nguyen", "--role", "engineer"]
    argv += [f"--value={k}={v}" for k, v in GRID.items()]
    assert main(argv) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["answer"]["values"] == STORED


# --- no_grid=yes (ADR-0013 decision 2): the engineer states the file holds no plan that needs a grid --------


def test_no_grid_yes_alone_is_accepted_and_stored_verbatim():
    assert check_values(GRID_MISSING_CODE, {"no_grid": "yes"}) == []
    assert grid_answer_values({"no_grid": "yes"}) == {"no_grid": "yes"}
    assert validate("answers", answers_doc({"no_grid": "yes"})) == []


@pytest.mark.parametrize(
    ("values", "words"),
    [
        ({"no_grid": "yes", **GRID}, "alone"),
        ({"no_grid": "yes", "sheet": "model#05"}, "alone"),
        ({"no_grid": "yes", "dir1_labels": "1,2"}, "alone"),
        ({"no_grid": "no"}, "'no'"),
        ({"no_grid": "Yes "}, "'Yes '"),
        ({"no_grid": ""}, "''"),
    ],
)
def test_no_grid_is_refused_with_another_key_or_another_value(values, words):
    problems = check_values(GRID_MISSING_CODE, values)
    assert problems and words in "; ".join(problems), problems
    assert "no_grid=yes" in "; ".join(problems)


@pytest.mark.parametrize(
    "stored",
    [
        {"no_grid": "yes", **STORED},
        {"no_grid": "no"},
        {"no_grid": "yes", "sheet": "model#05"},
        {"no_grid": True},
    ],
)
def test_the_schema_keeps_no_grid_alone_and_yes(stored):
    assert validate("answers", answers_doc(stored)) != []


@pytest.mark.parametrize("role", ["engineer", "simulated"])
def test_record_answer_takes_no_grid_from_any_role(work, role):
    """Only the engineer's no_grid closes the question (harness status); a simulated one is recorded."""
    path, qid = work
    result = record_answer(path, qid, "chỉ có ghi chú", "A. Nguyen", {"no_grid": "yes"}, role=role)
    assert result["answer"]["values"] == {"no_grid": "yes"}
    assert validate("answers", load(path / "answers.json")) == []


def test_record_answer_refuses_no_grid_with_grid_keys_and_writes_nothing(work):
    path, qid = work
    before = {p.name: p.read_bytes() for p in path.glob("*.json")}
    with pytest.raises(QuestionsError) as caught:
        record_answer(path, qid, "t", "A. Nguyen", {"no_grid": "yes", **GRID}, role="engineer")
    assert caught.value.exit_code == 1 and "alone" in str(caught.value)
    assert {p.name: p.read_bytes() for p in path.glob("*.json")} == before


def test_cli_answer_with_no_grid(work, capsys):
    path, qid = work
    argv = ["answer", str(path), qid, "--text", "ghi chú", "--by", "A. Nguyen", "--role", "engineer"]
    assert main([*argv, "--value", "no_grid=yes"]) == 0
    assert json.loads(capsys.readouterr().out)["answer"]["values"] == {"no_grid": "yes"}
    assert main([*argv, "--value", "no_grid=yes", "--value", "sheet=model#05"]) == 1
