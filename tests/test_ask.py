"""`harness ask`: the drawing-reader agent raises and withdraws questions through the registry."""

from __future__ import annotations

import copy
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from _dxf_fixtures import build_set
from tekla_harness.answers import record_answer
from tekla_harness.ask import amend_question, ask_question, reader_key, static_owner, withdraw_question
from tekla_harness.cli import main
from tekla_harness.intake import run_intake
from tekla_harness.questions import (
    CALLOUT_UNPARSED_CODE,
    GRID_CONTRADICTS_CODE,
    GRID_MISSING_CODE,
    LEGACY_ASCII_CODE,
    SHEET_GAP_CODE,
    QuestionsError,
)
from tekla_harness.questions_md import render_questions_md
from tekla_harness.schemas import validate
from tekla_harness.status import build_status
from tekla_harness.structure import read_structure

PROJECT = "demo-ask"
FILE = "set.dxf"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def run_cli(capsys, *argv: str) -> tuple[int, Any, str]:
    code = main(list(argv))
    cap = capsys.readouterr()
    return code, (json.loads(cap.out) if cap.out.strip() else None), cap.err


@pytest.fixture(scope="module")
def base_world(tmp_path_factory) -> Path:
    base = tmp_path_factory.mktemp("ask")
    root = base / "input"
    root.mkdir()
    build_set(root, FILE)
    run_intake(root, base / "work", PROJECT)
    read_structure(base / "work", root)
    return base


@pytest.fixture
def world(base_world, tmp_path) -> tuple[Path, Path]:
    target = tmp_path / "w"
    shutil.copytree(base_world, target)
    return target / "input", target / "work"


def ask(work: Path, where: str = "grid A", **kw: Any) -> dict[str, str]:
    args: dict[str, Any] = {
        "code": "label_unclear",
        "where": where,
        "found": "A or 4?",
        "text": "Is this label A or 4?",
        "file": FILE,
        "sheet": "model#01",
    }
    return ask_question(work, **{**args, **kw})


def test_new_question_gets_an_id_and_is_written_with_its_ref(world):
    _, work = world
    before = load(work / "question-registry.json")
    result = ask(work, blocking=True)
    assert result["status"] == "new"
    assert result["id"] == f"Q-{before['next_id']:03d}"
    entry = load(work / "question-registry.json")["questions"][result["key"]]
    sha = {r["path"]: r["sha256"] for r in load(work / "inventory.json")["files"]}[FILE]
    assert entry["producer"] == "reader"
    assert entry["blocking"] is True and entry["file_sha256"] == sha
    doc = load(work / "reader-questions.json")
    assert validate("intake", doc) == []
    (q,) = doc["questions"]
    assert q["id"] == result["id"] and q["key"] == result["key"] and q["answer"] is None
    assert q["message"] == "Is this label A or 4?" and q["count"] == 1
    assert q["refs"] == [{"file": FILE, "where": "grid A", "found": "A or 4?", "sheet": "model#01"}]
    assert doc["summary"] == {"questions": 1, "blocking_questions": 1, "answered": 0, "blocking_open": 1}


def test_same_where_is_idempotent_even_when_found_text_and_sheet_differ(world):
    _, work = world
    first = ask(work)
    snapshot = (work / "reader-questions.json").read_bytes(), (work / "question-registry.json").read_bytes()
    again = ask(work, found="something else", text="other wording", sheet="model#02")
    assert again == {**first, "status": "already_asked"}
    assert (work / "reader-questions.json").read_bytes() == snapshot[0]
    assert (work / "question-registry.json").read_bytes() == snapshot[1]


def test_different_where_blocking_or_file_is_another_question(world):
    _, work = world
    a, b = ask(work), ask(work, where="grid B")
    c, d = ask(work, blocking=True), ask(work, file=None)
    ids = [r["id"] for r in (a, b, c, d)]
    assert len(set(ids)) == 4 and ids == sorted(ids)
    assert d["status"] == "new"
    doc = load(work / "reader-questions.json")
    assert validate("intake", doc) == []
    assert [q["file"] for q in doc["questions"]] == [FILE, FILE, FILE, None]
    assert doc["questions"][3]["refs"][0]["file"] is None


def test_unknown_file_is_refused_with_exit_1_and_writes_nothing(world, capsys):
    _, work = world
    snapshot = (work / "question-registry.json").read_bytes()
    code, _, err = run_cli(
        capsys,
        "ask",
        str(work),
        "--code",
        "x_q",
        "--file",
        "nope.dxf",
        "--where",
        "w",
        "--found",
        "f",
        "--text",
        "t",
    )
    assert code == 1 and "not in inventory.json" in err
    assert (work / "question-registry.json").read_bytes() == snapshot
    assert not (work / "reader-questions.json").exists()


@pytest.mark.parametrize(
    ("code", "owner"),
    [
        ("units_unknown", "intake"),
        ("grid_system_select", "grid-system"),
        ("level_none_found", "structure"),
        # raised by read-structure, so owned by it (EVAL-1 F-21 listed them under grid-system)
        ("grid_family_axis_assignment", "structure"),
        ("grid_units_doubt", "structure"),
        ("mark_unmatched", "marks"),
        ("units_answer_contradicts_evidence", "grid-system"),  # exact code beats intake's units_ prefix
        ("schedule_row_unparsed", "marks"),
        ("member_mark_prefix_meaning", "marks"),  # tool wave 2: marks raises it, callouts no longer does
        ("file_set_relation", "intake"),  # tool wave 2: intake's project-level file-set question
        # tool wave 3 codes, with the producer that raises each (questions.py)
        (SHEET_GAP_CODE, "structure"),
        (CALLOUT_UNPARSED_CODE, "callouts"),
        (LEGACY_ASCII_CODE, "intake"),  # read-dxf at intake: no prefix covers it
        (GRID_MISSING_CODE, "grid-system"),
        (GRID_CONTRADICTS_CODE, "grid-system"),  # exact code beats read-structure's grid_ prefix
    ],
)
def test_a_code_owned_by_another_producer_is_refused_with_exit_2(world, capsys, code, owner):
    _, work = world
    rc, _, err = run_cli(
        capsys, "ask", str(work), "--code", code, "--where", "w", "--found", "f", "--text", "t"
    )
    assert rc == 2 and owner in err
    assert static_owner(code) == owner


@pytest.mark.parametrize("code", ["reader_level_storey_selection", "reader_grid_extra_line", "reader_units"])
def test_the_reader_namespace_is_never_owned_by_a_producer(world, code):
    _, work = world
    assert static_owner(code) is None
    assert ask(work, code=code)["status"] == "new"


def test_a_code_already_in_the_registry_under_another_producer_is_refused(world, capsys):
    _, work = world
    registry = load(work / "question-registry.json")
    entry = next(e for e in registry["questions"].values() if e["producer"] == "structure")
    rc, _, err = run_cli(
        capsys, "ask", str(work), "--code", entry["code"], "--where", "w", "--found", "f", "--text", "t"
    )
    assert rc == 2 and "'structure'" in err


@pytest.mark.parametrize("code", ["Bad", "1abc", "has-dash", "", "a__b"])
def test_a_bad_code_or_blank_argument_is_a_usage_error(world, capsys, code):
    _, work = world
    rc, _, _ = run_cli(
        capsys, "ask", str(work), "--code", code, "--where", "w", "--found", "f", "--text", "t"
    )
    assert rc == 2
    rc, _, _ = run_cli(
        capsys, "ask", str(work), "--code", "ok_code", "--where", " ", "--found", "f", "--text", "t"
    )
    assert rc == 2
    rc, _, _ = run_cli(
        capsys, "ask", str(work), "--code", "ok_code", "--where", "w"
    )  # --found/--text missing
    assert rc == 2


def test_cli_prints_the_documented_json_and_reports_already_asked(world, capsys):
    _, work = world
    argv = ["ask", str(work), "--code", "label_unclear", "--file", FILE, "--sheet", "model#01"]
    argv += ["--where", "grid A", "--found", "A or 4?", "--text", "Is this A or 4?", "--blocking"]
    rc, out, _ = run_cli(capsys, *argv)
    assert rc == 0 and set(out) == {"id", "key", "status"} and out["status"] == "new"
    rc, again, err = run_cli(capsys, *argv)
    assert rc == 0 and again == {**out, "status": "already_asked"} and "already asked" in err


def test_withdraw_marks_obsolete_keeps_the_registry_entry_and_is_idempotent(world, capsys):
    _, work = world
    keep, gone = ask(work), ask(work, where="grid B")
    rc, out, _ = run_cli(capsys, "ask", str(work), "--withdraw", gone["id"], "--reason", "read it myself")
    assert rc == 0 and out == {**gone, "status": "withdrawn"}
    entry = load(work / "question-registry.json")["questions"][gone["key"]]
    assert entry["status"] == "obsolete" and entry["withdrawn_reason"] == "read it myself"
    doc = load(work / "reader-questions.json")
    assert [q["id"] for q in doc["questions"]] == [keep["id"]]
    assert validate("question-registry", load(work / "question-registry.json")) == []
    rc, out, _ = run_cli(capsys, "ask", str(work), "--withdraw", gone["id"], "--reason", "again")
    assert rc == 0 and out["status"] == "already_withdrawn"
    # the place cannot be asked again; the id is never reused
    with pytest.raises(QuestionsError) as exc:
        ask(work, where="grid B")
    assert exc.value.exit_code == 2 and "withdrawn" in str(exc.value)
    assert ask(work, where="grid C")["id"] > gone["id"]


def test_withdraw_refusals(world, capsys):
    _, work = world
    other = next(
        e["id"]
        for e in load(work / "question-registry.json")["questions"].values()
        if e["producer"] == "intake"
    )
    q = ask(work)
    for argv in (
        ["--withdraw", other, "--reason", "r"],  # not a reader question
        ["--withdraw", "Q-999", "--reason", "r"],  # unknown
        ["--withdraw", q["id"], "--reason", " "],  # blank reason
        ["--withdraw", q["id"]],  # no reason
        ["--withdraw", q["id"], "--reason", "r", "--code", "x"],  # mixed with ask options
    ):
        rc, _, _ = run_cli(capsys, "ask", str(work), *argv)
        assert rc == 2, argv
    assert load(work / "question-registry.json")["questions"][q["key"]]["status"] == "open"


def test_withdrawing_an_answered_question_stales_its_answer(world):
    _, work = world
    q = ask(work, blocking=True)
    record_answer(work, q["id"], "It is A.", "eng", role="engineer")
    withdraw_question(work, q["id"], "moot")
    (answer,) = [a for a in load(work / "answers.json")["answers"] if a["key"] == q["key"]]
    assert answer["status"] == "stale"


def test_status_counts_reader_questions_and_gate1_waits_for_blocking_ones(world):
    _, work = world
    status = build_status(work)
    assert validate("status", status) == []
    reader = {p["producer"]: p for p in status["producers"]}["reader"]
    assert reader["questions"]["total"] == 0 and reader["outputs"]["status"] == "n/a"
    soft, hard = ask(work), ask(work, where="grid B", blocking=True)
    status = build_status(work)
    assert validate("status", status) == []
    reader = {p["producer"]: p for p in status["producers"]}["reader"]
    assert reader["questions"] | {} == {
        "total": 2,
        "blocking": 1,
        "blocking_unknown": 0,
        "blocking_open": 1,
        "answered": 0,
        "obsolete": 0,
    }
    assert reader["blocking_open_ids"] == [hard["id"]]
    assert any(
        r.startswith("reader: 1 blocking question(s) open") and hard["id"] in r
        for r in status["gate1"]["reasons"]
    )
    record_answer(work, hard["id"], "B", "eng", role="engineer")
    reader = {p["producer"]: p for p in build_status(work)["producers"]}["reader"]
    assert reader["questions"]["blocking_open"] == 0 and reader["questions"]["answered"] == 1
    withdraw_question(work, soft["id"], "r")
    reader = {p["producer"]: p for p in build_status(work)["producers"]}["reader"]
    assert reader["questions"]["total"] == 1 and reader["questions"]["obsolete"] == 1
    assert not any(r.startswith("reader:") for r in build_status(work)["gate1"]["reasons"])


def test_an_answer_to_a_reader_question_is_recorded_and_shown_in_the_document(world, capsys):
    _, work = world
    q = ask(work, blocking=True)
    rc, out, _ = run_cli(
        capsys, "answer", str(work), q["id"], "--text", "It is A.", "--by", "eng", "--role", "engineer"
    )
    assert rc == 0 and "reader-questions.json" in out["refreshed"]
    doc = load(work / "reader-questions.json")
    assert doc["questions"][0]["answer"]["answer_text"] == "It is A."
    assert doc["summary"]["blocking_open"] == 0 and doc["summary"]["answered"] == 1
    assert load(work / "question-registry.json")["questions"][q["key"]]["status"] == "answered"
    assert ask(work, blocking=True)["status"] == "already_asked"  # asking again keeps the answered question


def test_ids_never_collide_with_other_producers_and_reader_questions_survive_their_reruns(world):
    root, work = world
    q1 = ask(work, blocking=True)
    run_intake(root, work, PROJECT)  # other producers rerun: reader entries are untouched
    read_structure(work, root)
    registry = load(work / "question-registry.json")
    assert registry["questions"][q1["key"]]["status"] == "open"
    assert [q["id"] for q in load(work / "reader-questions.json")["questions"]] == [q1["id"]]
    q2 = ask(work, where="grid B")
    ids = [e["id"] for e in load(work / "question-registry.json")["questions"].values()]
    assert len(ids) == len(set(ids)) and q2["id"] > max(i for i in ids if i != q2["id"])
    (work / "question-registry.json").read_text(encoding="utf-8")
    assert registry["next_id"] <= int(q2["id"][2:])


def test_ask_needs_a_registry_and_a_valid_reader_document(world, tmp_path, capsys):
    _, work = world
    empty = tmp_path / "empty"
    empty.mkdir()
    rc, _, _ = run_cli(
        capsys, "ask", str(empty), "--code", "x_q", "--where", "w", "--found", "f", "--text", "t"
    )
    assert rc == 2
    (work / "reader-questions.json").write_text("{not json", encoding="utf-8")
    rc, _, err = run_cli(
        capsys, "ask", str(work), "--code", "x_q", "--where", "w", "--found", "f", "--text", "t"
    )
    assert rc == 1 and "reader-questions.json" in err


def test_key_depends_on_code_blocking_file_hash_and_where_only():
    base = reader_key("c", False, "a.dxf", "0" * 64, "w")
    assert len(base) == 16 and base == reader_key("c", False, "a.dxf", "0" * 64, "w")
    for other in (
        reader_key("d", False, "a.dxf", "0" * 64, "w"),
        reader_key("c", True, "a.dxf", "0" * 64, "w"),
        reader_key("c", False, "b.dxf", "0" * 64, "w"),
        reader_key("c", False, "a.dxf", "1" * 64, "w"),
        reader_key("c", False, "a.dxf", "0" * 64, "x"),
        reader_key("c", False, None, None, "w"),
    ):
        assert other != base


# --- harness ask --amend (tool wave 3, package C) ---------------------------------------------------


def reader_doc(work: Path) -> dict[str, Any]:
    doc = load(work / "reader-questions.json")
    assert validate("reader-questions", doc) == []
    return doc


def the_question(work: Path, qid: str) -> dict[str, Any]:
    return next(q for q in reader_doc(work)["questions"] if q["id"] == qid)


def test_amend_text_keeps_id_key_and_ref_and_records_what_it_replaced(world):
    _, work = world
    q = ask(work, blocking=True)
    runs = load(work / "question-registry.json")["runs"]
    before = the_question(work, q["id"])
    assert amend_question(work, q["id"], text="Nhãn này là A hay 4?") == {**q, "status": "amended"}
    after = the_question(work, q["id"])
    assert after["message"] == "Nhãn này là A hay 4?"
    assert after["amendments"] == [{"at": runs + 1, "text": before["message"]}]
    assert "places" not in after  # only what was given changes
    assert {k: v for k, v in after.items() if k not in ("message", "amendments")} == {
        k: v for k, v in before.items() if k != "message"
    }
    registry = load(work / "question-registry.json")
    assert registry["runs"] == runs + 1 and registry["questions"][q["key"]]["status"] == "open"
    assert registry["questions"][q["key"]]["id"] == q["id"]
    # the identity is the place: asking the same place again is still the same, amended, question
    assert ask(work, blocking=True) == {**q, "status": "already_asked"}


def test_amend_places_records_the_previous_list_and_successive_amendments_stack(world):
    _, work = world
    q = ask(work)
    amend_question(work, q["id"], places=["model#05 axis 3-4", "model#07"])
    assert the_question(work, q["id"])["places"] == ["model#05 axis 3-4", "model#07"]
    amend_question(work, q["id"], text="câu mới", places=["model#07"])
    after = the_question(work, q["id"])
    assert after["message"] == "câu mới" and after["places"] == ["model#07"]
    first, second = after["amendments"]
    assert set(first) == {"at", "places"} and first["places"] == []  # there were none
    assert second == {
        "at": first["at"] + 1,
        "text": "Is this label A or 4?",
        "places": ["model#05 axis 3-4", "model#07"],
    }


def test_amend_with_the_current_values_changes_nothing(world):
    _, work = world
    q = ask(work)
    amend_question(work, q["id"], places=["model#05"])
    snapshot = (work / "reader-questions.json").read_bytes(), (work / "question-registry.json").read_bytes()
    result = amend_question(work, q["id"], text="Is this label A or 4?", places=["model#05"])
    assert result == {**q, "status": "unchanged"}
    assert (work / "reader-questions.json").read_bytes() == snapshot[0]
    assert (work / "question-registry.json").read_bytes() == snapshot[1]
    # only the changed part is recorded
    amend_question(work, q["id"], text="Is this label A or 4?", places=["model#06"])
    assert the_question(work, q["id"])["amendments"][-1] == {
        "at": load(work / "question-registry.json")["runs"],
        "places": ["model#05"],
    }


def test_amend_other_questions_of_the_document_are_untouched(world):
    _, work = world
    a, b = ask(work), ask(work, where="grid B")
    other = the_question(work, a["id"])
    amend_question(work, b["id"], text="mới")  # the second one: the right question is found by its key
    assert the_question(work, a["id"]) == other and the_question(work, b["id"])["message"] == "mới"
    assert [q["id"] for q in reader_doc(work)["questions"]] == [a["id"], b["id"]]


def test_amend_refusals_exit_2_and_write_nothing(world, capsys):
    _, work = world
    other = next(
        e["id"]
        for e in load(work / "question-registry.json")["questions"].values()
        if e["producer"] == "intake"
    )
    answered, withdrawn, live = ask(work, blocking=True), ask(work, where="grid B"), ask(work, where="grid C")
    record_answer(work, answered["id"], "It is A.", "eng", role="engineer")
    withdraw_question(work, withdrawn["id"], "moot")
    snapshot = {p.name: p.read_bytes() for p in work.glob("*.json")}
    for qid, words in (
        ("Q-999", "unknown"),
        (other, "not the reader"),
        (withdrawn["id"], "withdrawn"),
        (answered["id"], "answered"),
    ):
        rc, out, err = run_cli(capsys, "ask", str(work), "--amend", qid, "--text", "mới")
        assert rc == 2 and out is None and words in err, (qid, err)
    cases: list[dict[str, Any]] = [{}, {"text": " "}, {"places": []}, {"places": ["a", " "]}]
    for kwargs in cases:
        with pytest.raises(QuestionsError) as caught:
            amend_question(work, live["id"], **kwargs)
        assert caught.value.exit_code == 2, kwargs
    assert {p.name: p.read_bytes() for p in work.glob("*.json")} == snapshot


def test_amend_a_question_answered_by_a_simulated_role_is_refused_too(world):
    _, work = world
    q = ask(work)
    record_answer(work, q["id"], "A", "agent", role="simulated")
    with pytest.raises(QuestionsError) as caught:
        amend_question(work, q["id"], text="mới")
    assert caught.value.exit_code == 2 and "answered" in str(caught.value)


def test_amend_after_a_stale_answer_is_allowed(world):
    """An answer that went stale no longer answers the question: it is live and unanswered again."""
    _, work = world
    q = ask(work)
    record_answer(work, q["id"], "A", "eng", role="engineer")
    answers = load(work / "answers.json")
    for a in answers["answers"]:
        if a["key"] == q["key"]:
            a["status"], a["stale_reason"] = "stale", "test"
    (work / "answers.json").write_text(json.dumps(answers), encoding="utf-8")
    registry = load(work / "question-registry.json")
    registry["questions"][q["key"]]["status"] = "open"
    (work / "question-registry.json").write_text(json.dumps(registry), encoding="utf-8")
    assert amend_question(work, q["id"], text="mới")["status"] == "amended"


def test_amend_a_question_missing_from_the_document_is_an_inconsistency(world):
    _, work = world
    q = ask(work)
    doc = load(work / "reader-questions.json")
    doc["questions"] = []
    doc["summary"] = {"questions": 0, "blocking_questions": 0, "answered": 0, "blocking_open": 0}
    (work / "reader-questions.json").write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(QuestionsError) as caught:
        amend_question(work, q["id"], text="mới")
    assert caught.value.exit_code == 1 and "reader-questions.json" in str(caught.value)


def test_a_reader_document_that_breaks_the_reader_rules_is_refused_when_read(world):
    """A question with two refs is a valid intake question but not a reader one: every mode of harness ask
    refuses the document (exit 1) and writes nothing."""
    _, work = world
    q = ask(work)
    doc = load(work / "reader-questions.json")
    doc["questions"][0]["refs"].append({"file": FILE, "where": "grid Z", "found": "f"})
    (work / "reader-questions.json").write_text(json.dumps(doc), encoding="utf-8")
    snapshot = (work / "question-registry.json").read_bytes()
    for run in (
        lambda: amend_question(work, q["id"], text="mới"),
        lambda: ask(work, where="grid Y"),
        lambda: withdraw_question(work, q["id"], "r"),
    ):
        with pytest.raises(QuestionsError) as caught:
            run()
        # the document on disk is at fault, not the command: it is refused when read
        assert caught.value.exit_code == 1 and "reader-questions.json is invalid" in str(caught.value)
    assert (work / "question-registry.json").read_bytes() == snapshot


def test_cli_amend_prints_the_documented_json(world, capsys):
    _, work = world
    q = ask(work)
    argv = ["ask", str(work), "--amend", q["id"], "--places", "model#05 axis 3-4", "model#07"]
    rc, out, _ = run_cli(capsys, *argv)
    assert rc == 0 and out == {**q, "status": "amended"}
    assert the_question(work, q["id"])["places"] == ["model#05 axis 3-4", "model#07"]


def test_questions_md_shows_the_amended_text(world):
    _, work = world
    q = ask(work, blocking=True, text="Câu hỏi cũ về nhãn trục")
    amend_question(work, q["id"], text="Câu hỏi mới về nhãn trục")
    text = render_questions_md(work).text
    assert "Câu hỏi mới về nhãn trục" in text and "Câu hỏi cũ về nhãn trục" not in text


# --- harness validate reader-questions on real-shaped documents ----------------------------------------

# The shape of the EVAL-3 reader documents (projects/_evals/eval3-2026-11-09, arms H and R: 31 and 22
# questions, all with exactly these keys), cut down to two questions with short stand-in text: a .dwg file,
# a blocking and a non-blocking question, no sheet, an empty `found`, no answer.
EVAL3_SHAPE: dict[str, Any] = {
    "schema_version": "0.1",
    "kind": "questions",
    "project_id": "eval3-r",
    "questions": [
        {
            "id": "Q-075",
            "key": "4ea02907ca0c8032",
            "code": "reader_drawing_list_missing",
            "blocking": True,
            "file": "267_4-story_house_complete_project.dwg",
            "message": "Không tìm thấy danh mục bản vẽ trong file.",
            "count": 1,
            "truncated": False,
            "refs": [
                {
                    "file": "267_4-story_house_complete_project.dwg",
                    "where": "cả file (65 tờ, model#01…model#65)",
                    "found": "find-text 'danh mục': 0 kết quả",
                }
            ],
            "answer": None,
        },
        {
            "id": "Q-117",
            "key": "86b2fa3ad2caba14",
            "code": "reader_level_storey_selection",
            "blocking": False,
            "file": "161_complete_steel_building.dwg",
            "message": "Cao độ nào là cao độ tầng?",
            "count": 1,
            "truncated": False,
            "refs": [{"file": "161_complete_steel_building.dwg", "where": "tờ Layout2#01", "found": ""}],
            "answer": None,
        },
    ],
    "summary": {"questions": 2, "blocking_questions": 1, "answered": 0, "blocking_open": 1},
}


def _validate_cli(capsys, path: Path, doc: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    rc = main(["validate", "reader-questions", str(path)])
    return rc, json.loads(capsys.readouterr().out)


def test_validate_reader_questions_accepts_the_eval3_shape_and_an_amended_question(tmp_path, capsys):
    rc, out = _validate_cli(capsys, tmp_path / "rq.json", EVAL3_SHAPE)
    assert rc == 0 and out["results"][0]["valid"] is True
    amended = copy.deepcopy(EVAL3_SHAPE)
    amended["questions"][0].update(
        message="mới",
        places=["model#05 axis 3-4"],
        amendments=[{"at": 7, "places": []}, {"at": 9, "text": "cũ", "places": ["model#05"]}],
    )
    rc, out = _validate_cli(capsys, tmp_path / "rq.json", amended)
    assert rc == 0, out


@pytest.mark.parametrize(
    "mutate",
    [
        lambda q: q["refs"].append({"file": q["file"], "where": "w2", "found": "f"}),  # one ref only
        lambda q: q.update(count=2),
        lambda q: q.update(truncated=True),
        lambda q: q.update(closed_by={"question_id": "Q-001", "reason": "not_selected"}),
        lambda q: q.update(subjects=[{"name": "dir1"}]),
        lambda q: q.update(amendments=[{"at": 3}]),  # an amendment records what it replaced
        lambda q: q.update(amendments=[]),
        lambda q: q.update(places=[" "]),
        lambda q: q.update(places=[]),
        lambda q: q.update(amendments=[{"at": 0, "text": "cũ"}]),
    ],
)
def test_validate_reader_questions_refuses_what_a_reader_question_cannot_be(tmp_path, capsys, mutate):
    bad = copy.deepcopy(EVAL3_SHAPE)
    mutate(bad["questions"][1])
    rc, out = _validate_cli(capsys, tmp_path / "rq.json", bad)
    assert rc == 1 and out["results"][0]["valid"] is False


def test_an_answer_keeps_the_amendments(world):
    _, work = world
    q = ask(work)
    amend_question(work, q["id"], text="mới", places=["model#05"])
    record_answer(work, q["id"], "A", "eng", role="engineer")
    after = the_question(work, q["id"])
    assert after["message"] == "mới" and after["places"] == ["model#05"] and len(after["amendments"]) == 1
    assert after["answer"]["answer_text"] == "A"


# --- --part (ADR-0019, part mode) -------------------------------------------------------------------------

PART_A, PART_B, PART_C = "blk1-piles", "blk1-columns", "blk2-beams"


def manifest(work: Path, *ids: str) -> None:
    path = work / "parts" / "manifest.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"parts": [{"id": i} for i in ids]}), encoding="utf-8")


def parts_of(work: Path, qid: str) -> Any:
    return the_question(work, qid).get("parts")


def snapshot(work: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in work.glob("*.json")}


def amend(work: Path, qid: str, **kw: Any) -> dict[str, str]:
    return amend_question(work, qid, **kw)


def withdraw(work: Path, qid: str, **kw: Any) -> dict[str, str]:
    return withdraw_question(work, qid, "moot", **kw)


def test_part_is_optional_without_a_manifest_and_is_stored_as_parts(world):
    _, work = world
    q = ask(work, part=PART_A)
    assert q["status"] == "new" and q["parts"] == [PART_A]
    assert parts_of(work, q["id"]) == [PART_A]
    assert validate("reader-questions", load(work / "reader-questions.json")) == []
    plain = ask(work, where="grid B")
    assert set(plain) == {"id", "key", "status"} and parts_of(work, plain["id"]) is None


def test_the_key_and_the_registry_do_not_depend_on_the_part(world):
    _, work = world
    q = ask(work, part=PART_A)
    assert q["key"] == reader_key(
        "label_unclear", False, FILE, load(work / "inventory.json")["files"][0]["sha256"], "grid A"
    )
    entry = load(work / "question-registry.json")["questions"][q["key"]]
    assert "part" not in entry and "parts" not in entry


@pytest.mark.parametrize("bad", ["", "-x", "a b", "a/b", "x" * 65, "a\n"])
def test_a_bad_part_pattern_is_exit_2_with_or_without_a_manifest(world, bad):
    _, work = world
    snap = snapshot(work)
    for _ in range(2):
        with pytest.raises(QuestionsError) as err:
            ask(work, part=bad)
        assert err.value.exit_code == 2
        manifest(work, PART_A)
    assert snapshot(work) == snap


def test_part_is_required_with_a_manifest_exit_2_and_an_unknown_id_exit_1(world):
    _, work = world
    manifest(work, PART_A)
    snap = snapshot(work)
    with pytest.raises(QuestionsError) as err:
        ask(work)
    assert err.value.exit_code == 2 and "--part" in str(err.value)
    with pytest.raises(QuestionsError) as err:
        ask(work, part=PART_B)
    assert err.value.exit_code == 1 and PART_B in str(err.value)
    assert snapshot(work) == snap
    assert ask(work, part=PART_A)["status"] == "new"


@pytest.mark.parametrize("content", ["{not json", "[]", '{"parts": 3}', '{"parts": [{"name": "x"}]}', ""])
def test_a_malformed_manifest_is_exit_1_naming_the_file(world, content):
    _, work = world
    (work / "parts").mkdir()
    (work / "parts" / "manifest.json").write_text(content, encoding="utf-8")
    snap = snapshot(work)
    for kw in ({"part": PART_A}, {}):
        with pytest.raises(QuestionsError) as err:
            ask(work, **kw)
        assert err.value.exit_code == 1 and "parts/manifest.json" in str(err.value)
    assert snapshot(work) == snap


def test_a_manifest_that_lists_no_parts_says_so(world):
    _, work = world
    manifest(work)
    with pytest.raises(QuestionsError) as err:
        ask(work, part=PART_A)
    assert err.value.exit_code == 1 and "lists no parts" in str(err.value)


def test_a_directory_at_the_manifest_path_is_exit_1_not_part_mode_off(world):
    _, work = world
    q = ask(work, part=PART_A)
    (work / "parts" / "manifest.json").mkdir(parents=True)
    snap = snapshot(work)
    calls = (
        lambda: ask(work, where="grid B", part=PART_A),
        lambda: ask(work, where="grid B"),
        lambda: amend(work, q["id"], text="mới", part=PART_A),
        lambda: withdraw(work, q["id"], part=PART_A),
    )
    for call in calls:
        with pytest.raises(QuestionsError) as err:
            call()
        assert err.value.exit_code == 1 and "parts/manifest.json" in str(err.value)
    assert snapshot(work) == snap


@pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0), reason="chmod 000 needs a user"
)
def test_an_unreadable_manifest_path_is_exit_3(world):
    _, work = world
    manifest(work, PART_A)
    snap = snapshot(work)
    for target in (work / "parts", work / "parts" / "manifest.json"):
        target.chmod(0o000)
        try:
            with pytest.raises(QuestionsError) as err:
                ask(work, part=PART_A)
        finally:
            target.chmod(0o755 if target.is_dir() else 0o644)
        assert err.value.exit_code == 3 and "parts/manifest.json" in str(err.value)
    assert snapshot(work) == snap
    assert ask(work, part=PART_A)["status"] == "new"


def test_a_producer_code_is_refused_for_its_owner_before_part_is_asked_for(world, capsys):
    _, work = world
    manifest(work, PART_A)
    snap = snapshot(work)
    rc, _, err = run_cli(
        capsys, "ask", str(work), "--code", "units_unknown", "--where", "w", "--found", "f", "--text", "t"
    )
    assert rc == 2 and "intake" in err and "--part" not in err
    assert snapshot(work) == snap


def test_the_manifest_is_read_from_parts_manifest_json_only(world):
    _, work = world
    (work / "manifest.json").write_text(json.dumps({"parts": [{"id": PART_A}]}), encoding="utf-8")
    assert ask(work)["status"] == "new"


def test_asking_an_existing_key_with_a_new_part_appends_it_in_arrival_order(world):
    _, work = world
    first = ask(work, part=PART_B)
    second = ask(work, part=PART_A)
    assert second["id"] == first["id"] and second["key"] == first["key"]
    assert second["status"] == "already_asked_part_added" and second["parts"] == [PART_B, PART_A]
    assert parts_of(work, first["id"]) == [PART_B, PART_A]
    assert validate("reader-questions", load(work / "reader-questions.json")) == []
    assert len(load(work / "reader-questions.json")["questions"]) == 1
    assert ask(work, where="grid B")["id"] > first["id"]  # the id counter did not move for the append


def test_the_same_part_again_does_not_duplicate_it(world):
    _, work = world
    first = ask(work, part=PART_A)
    ask(work, part=PART_B)
    snap = snapshot(work)
    again = ask(work, part=PART_A)
    assert again["status"] == "already_asked" and again["parts"] == [PART_A, PART_B]
    assert parts_of(work, first["id"]) == [PART_A, PART_B] and snapshot(work) == snap


def test_already_asked_without_a_part_is_unchanged(world):
    _, work = world
    plain = ask(work)
    assert ask(work) == {**plain, "status": "already_asked"}
    tagged = ask(work, where="grid B", part=PART_A)
    snap = snapshot(work)
    assert ask(work, where="grid B") == {"id": tagged["id"], "key": tagged["key"], "status": "already_asked"}
    assert snapshot(work) == snap


def test_a_part_on_an_untagged_question_is_appended(world):
    _, work = world
    plain = ask(work)
    tagged = ask(work, part=PART_A)
    assert tagged["status"] == "already_asked_part_added" and tagged["parts"] == [PART_A]
    assert parts_of(work, plain["id"]) == [PART_A]


def test_a_part_added_to_an_answered_question_keeps_the_answer(world):
    _, work = world
    q = ask(work, part=PART_A)
    record_answer(work, q["id"], "It is A.", "eng", role="engineer")
    assert parts_of(work, q["id"]) == [PART_A]  # answering keeps the parts
    assert ask(work, part=PART_B)["status"] == "already_asked_part_added"
    assert the_question(work, q["id"])["answer"] is not None
    assert parts_of(work, q["id"]) == [PART_A, PART_B]


def test_a_new_part_on_a_withdrawn_place_is_still_refused(world):
    _, work = world
    q = ask(work, part=PART_A)
    withdraw(work, q["id"], part=PART_A)
    with pytest.raises(QuestionsError) as err:
        ask(work, part=PART_B)
    assert err.value.exit_code == 2


def test_withdraw_needs_one_of_the_questions_parts_exit_1(world):
    _, work = world
    q = ask(work, part=PART_A)
    ask(work, part=PART_B)
    snap = snapshot(work)
    for kw in ({}, {"part": PART_C}):
        with pytest.raises(QuestionsError) as err:
            withdraw(work, q["id"], **kw)
        assert err.value.exit_code == 1, kw
    assert snapshot(work) == snap
    assert withdraw(work, q["id"], part=PART_B)["status"] == "part_removed"  # membership, not the first part


def test_withdraw_by_one_of_several_parts_only_removes_that_part_and_the_question_stays_open(world):
    _, work = world
    q = ask(work, part=PART_A)
    ask(work, part=PART_B)
    ask(work, part=PART_C)
    record_answer(work, q["id"], "It is A.", "eng", role="engineer")
    result = withdraw(work, q["id"], part=PART_A)
    assert result == {"id": q["id"], "key": q["key"], "status": "part_removed", "parts": [PART_B, PART_C]}
    assert parts_of(work, q["id"]) == [PART_B, PART_C]
    assert (
        load(work / "question-registry.json")["questions"][q["key"]]["status"] == "answered"
    )  # not obsolete
    assert the_question(work, q["id"])["answer"] is not None  # nothing else changes
    assert validate("reader-questions", load(work / "reader-questions.json")) == []
    with pytest.raises(QuestionsError) as err:  # A no longer holds it
        withdraw(work, q["id"], part=PART_A)
    assert err.value.exit_code == 1
    assert withdraw(work, q["id"], part=PART_B)["parts"] == [PART_C]
    last = withdraw(work, q["id"], part=PART_C)
    assert last["status"] == "withdrawn" and "parts" not in last  # the last part leaves: withdrawn as before
    assert load(work / "question-registry.json")["questions"][q["key"]]["status"] == "obsolete"
    assert all(x["id"] != q["id"] for x in reader_doc(work)["questions"])


def test_a_part_that_left_a_question_can_ask_it_again(world):
    _, work = world
    q = ask(work, part=PART_A)
    ask(work, part=PART_B)
    withdraw(work, q["id"], part=PART_A)
    again = ask(work, part=PART_A)
    assert again["status"] == "already_asked_part_added" and again["parts"] == [PART_B, PART_A]


def test_withdraw_with_a_manifest_needs_part_exit_2_and_an_unknown_one_exit_1(world):
    _, work = world
    q = ask(work, part=PART_A)
    manifest(work, PART_A, PART_B)
    snap = snapshot(work)
    for kw, code in (({}, 2), ({"part": "-bad"}, 2), ({"part": "blk9-none"}, 1), ({"part": PART_B}, 1)):
        with pytest.raises(QuestionsError) as err:
            withdraw(work, q["id"], **kw)
        assert err.value.exit_code == code, kw
    assert snapshot(work) == snap
    assert withdraw(work, q["id"], part=PART_A)["status"] == "withdrawn"


def test_withdraw_of_an_untagged_question_validates_the_part_and_stores_nothing(world):
    _, work = world
    q = ask(work)
    manifest(work, PART_A)
    for kw, code in (({}, 2), ({"part": PART_B}, 1)):
        with pytest.raises(QuestionsError) as err:
            withdraw(work, q["id"], **kw)
        assert err.value.exit_code == code
    assert withdraw(work, q["id"], part=PART_A)["status"] == "withdrawn"
    assert all("parts" not in x for x in load(work / "reader-questions.json")["questions"])


def test_withdrawing_an_already_withdrawn_question_skips_the_membership_check(world):
    _, work = world
    q = ask(work, part=PART_A)
    withdraw(work, q["id"], part=PART_A)
    assert withdraw(work, q["id"], part=PART_C)["status"] == "already_withdrawn"
    manifest(work, PART_A, PART_C)
    with pytest.raises(QuestionsError) as err:
        withdraw(work, q["id"])  # the part itself is still required once a manifest exists
    assert err.value.exit_code == 2


def test_amend_needs_one_of_the_questions_parts_exit_1(world):
    _, work = world
    q = ask(work, part=PART_A)
    ask(work, part=PART_B)
    snap = snapshot(work)
    for kw in ({}, {"part": PART_C}):
        with pytest.raises(QuestionsError) as err:
            amend(work, q["id"], text="mới", **kw)
        assert err.value.exit_code == 1, kw
    assert snapshot(work) == snap
    assert amend(work, q["id"], text="mới", part=PART_B)["status"] == "amended"
    assert parts_of(work, q["id"]) == [PART_A, PART_B]  # amend never edits the parts


def test_amend_with_a_manifest_needs_part_exit_2_and_an_unknown_one_exit_1(world):
    _, work = world
    q = ask(work, part=PART_A)
    manifest(work, PART_A)
    snap = snapshot(work)
    for kw, code in (({}, 2), ({"part": "-bad"}, 2), ({"part": PART_B}, 1)):
        with pytest.raises(QuestionsError) as err:
            amend(work, q["id"], text="mới", **kw)
        assert err.value.exit_code == code, kw
    assert snapshot(work) == snap
    assert amend(work, q["id"], text="mới", part=PART_A)["status"] == "amended"


def test_amend_of_an_untagged_question_validates_the_part_and_stores_nothing(world):
    _, work = world
    q = ask(work)
    assert amend(work, q["id"], text="mới")["status"] == "amended"  # no manifest: no part needed
    manifest(work, PART_A)
    with pytest.raises(QuestionsError) as err:
        amend(work, q["id"], text="khác", part=PART_B)
    assert err.value.exit_code == 1
    assert amend(work, q["id"], text="khác", part=PART_A)["status"] == "amended"
    assert parts_of(work, q["id"]) is None


def test_cli_part_flag_modes_and_stderr_line(world, capsys):
    _, work = world
    argv = ["ask", str(work), "--code", "label_unclear", "--file", FILE, "--sheet", "model#01"]
    argv += ["--where", "grid A", "--found", "A or 4?", "--text", "Is this A or 4?"]
    rc, out, _ = run_cli(capsys, *argv, "--part", PART_A)
    assert rc == 0 and out["status"] == "new" and out["parts"] == [PART_A]
    rc, again, err = run_cli(capsys, *argv, "--part", PART_B)
    assert rc == 0 and again["status"] == "already_asked_part_added" and again["parts"] == [PART_A, PART_B]
    assert f"{out['id']}: already asked, part added" in err
    rc, same, err = run_cli(capsys, *argv, "--part", PART_B)
    assert rc == 0 and same["status"] == "already_asked" and "already asked" in err
    rc, out2, _ = run_cli(capsys, "ask", str(work), "--amend", out["id"], "--text", "x", "--part", PART_A)
    assert rc == 0 and out2["status"] == "amended" and "parts" not in out2
    rc, _, _ = run_cli(capsys, "ask", str(work), "--amend", out["id"], "--text", "y", "--part", PART_C)
    assert rc == 1
    rc, _, _ = run_cli(capsys, "ask", str(work), "--amend", out["id"], "--text", "y", "--part", "-bad")
    assert rc == 2
    rc, _, _ = run_cli(capsys, "ask", str(work), "--withdraw", out["id"], "--reason", "r", "--part", PART_C)
    assert rc == 1
    rc, wd, _ = run_cli(capsys, "ask", str(work), "--withdraw", out["id"], "--reason", "r", "--part", PART_B)
    assert rc == 0 and wd["status"] == "part_removed" and wd["parts"] == [PART_A]
    rc, wd, err = run_cli(
        capsys, "ask", str(work), "--withdraw", out["id"], "--reason", "r", "--part", PART_A
    )
    assert rc == 0 and wd["status"] == "withdrawn"


def test_cli_withdraw_of_one_of_several_parts_prints_part_removed_on_stderr(world, capsys):
    _, work = world
    q = ask(work, part=PART_A)
    ask(work, part=PART_B)
    rc, out, err = run_cli(capsys, "ask", str(work), "--withdraw", q["id"], "--reason", "r", "--part", PART_A)
    assert rc == 0 and out == {"id": q["id"], "key": q["key"], "status": "part_removed", "parts": [PART_B]}
    assert f"{q['id']}: part removed" in err


def test_cli_part_is_refused_with_supplement_modes_exit_2(world, capsys):
    _, work = world
    snap = snapshot(work)
    other = next(
        e["id"]
        for e in load(work / "question-registry.json")["questions"].values()
        if e["producer"] == "intake"
    )
    sup = ["--where", "w", "--found", "f", "--text", "t"]
    for argv in (
        ["--supplement", other, *sup, "--part", PART_A],
        ["--withdraw-supplement", "0123456789abcdef", "--reason", "r", "--part", PART_A],
    ):
        rc, out, err = run_cli(capsys, "ask", str(work), *argv)
        assert rc == 2 and out is None and "--part" in err, argv
    assert snapshot(work) == snap


# --- a question whose part left the manifest can still be withdrawn (E4a D5) -----------------------------


def test_withdraw_accepts_the_questions_own_part_after_the_manifest_dropped_it(world):
    _, work = world
    q = ask(work, part=PART_A)
    manifest(work, PART_B)  # PART_A is gone
    snap = snapshot(work)
    for kw, code in (({}, 2), ({"part": "-bad"}, 2), ({"part": PART_B}, 1), ({"part": "blk9-none"}, 1)):
        with pytest.raises(QuestionsError) as err:
            withdraw(work, q["id"], **kw)
        assert err.value.exit_code == code, kw
    assert snapshot(work) == snap
    assert withdraw(work, q["id"], part=PART_A)["status"] == "withdrawn"
    # the same command again clears nothing more and is no error: the question's own orphan part is accepted
    assert withdraw(work, q["id"], part=PART_A)["status"] == "already_withdrawn"


def test_withdraw_removes_an_orphan_part_from_a_shared_question(world):
    _, work = world
    q = ask(work, part=PART_A)
    ask(work, part=PART_B)
    manifest(work, PART_B)  # PART_A is gone
    result = withdraw(work, q["id"], part=PART_A)
    assert result["status"] == "part_removed" and result["parts"] == [PART_B]
    assert parts_of(work, q["id"]) == [PART_B]


def test_a_repeated_withdraw_of_a_part_the_question_no_longer_holds_says_so_exit_1(world):
    _, work = world
    q = ask(work, part=PART_A)
    ask(work, part=PART_B)
    manifest(work, PART_B)  # PART_A is gone, and the question has left it
    withdraw(work, q["id"], part=PART_A)
    snap = snapshot(work)
    with pytest.raises(QuestionsError) as err:
        withdraw(work, q["id"], part=PART_A)  # neither listed nor held
    assert err.value.exit_code == 1
    message = str(err.value)
    assert f"{q['id']} belongs to part(s) {PART_B}" in message and f"(got --part {PART_A})" in message
    assert "not in" not in message
    assert snapshot(work) == snap


def test_a_part_that_is_neither_listed_nor_held_keeps_the_manifest_wording_for_an_untagged_question(world):
    _, work = world
    q = ask(work)  # no manifest yet: no part
    manifest(work, PART_B)
    with pytest.raises(QuestionsError) as err:
        withdraw(work, q["id"], part=PART_A)
    assert err.value.exit_code == 1 and "not in" in str(err.value) and "belongs to" not in str(err.value)


def test_asking_or_amending_with_a_part_the_manifest_dropped_is_still_exit_1(world):
    _, work = world
    q = ask(work, part=PART_A)
    manifest(work, PART_B)
    snap = snapshot(work)
    with pytest.raises(QuestionsError) as err:
        ask(work, "grid B", part=PART_A)  # a new question
    assert err.value.exit_code == 1
    with pytest.raises(QuestionsError) as err:
        ask(work, part=PART_A)  # an existing key
    assert err.value.exit_code == 1
    with pytest.raises(QuestionsError) as err:
        amend(work, q["id"], text="new wording", part=PART_A)
    assert err.value.exit_code == 1
    assert snapshot(work) == snap


def test_an_invalid_manifest_still_refuses_the_own_part_withdraw_exit_1(world):
    _, work = world
    q = ask(work, part=PART_A)
    (work / "parts").mkdir(exist_ok=True)
    (work / "parts" / "manifest.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(QuestionsError) as err:
        withdraw(work, q["id"], part=PART_A)
    assert err.value.exit_code == 1 and "parts/manifest.json" in str(err.value)


# --- a locked part refuses question writes (ADR-0019, E5b-4) -----------------------------------------------

LOCKED_AT = "2026-03-04T05:06:07Z"


def write_receipts(work: Path, part: str, *kinds: str, text: str | None = None) -> Path:
    """`parts/<part>/receipts.json` by hand: one receipt per kind (hash arbitrary), or `text` as is."""
    path = work / "parts" / part / "receipts.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if text is None:
        receipts = [
            {
                "n": i, "kind": k, "part_hash": "c" * 64, "at": LOCKED_AT, "tool_version": "0.1.0",
                "review": None, "inputs": {} if k == "locked" else None,
                "reason": "the sizes changed" if k == "reopened" else None,
            }
            for i, k in enumerate(kinds, start=1)
        ]  # fmt: skip
        text = json.dumps({"schema_version": "0.1", "part": part, "receipts": receipts})
    path.write_text(text, encoding="utf-8")
    return path


def locked_error(work: Path, call: Any, *, code: int = 1) -> str:
    """Run `call()` expecting a refusal that leaves every top-level json of the work folder as it was."""
    snap = snapshot(work)
    with pytest.raises(QuestionsError) as err:
        call()
    assert err.value.exit_code == code, str(err.value)
    assert snapshot(work) == snap  # nothing written
    return str(err.value)


def test_ask_new_existing_withdraw_refused_on_a_locked_part(world):
    _, work = world
    manifest(work, PART_A, PART_B)
    held = ask(work, part=PART_A)
    shared = ask(work, "grid B", part=PART_A)
    ask(work, "grid B", part=PART_B)  # `shared` is held by both parts
    write_receipts(work, PART_A, "checked", "locked")
    message = locked_error(work, lambda: ask(work, "grid C", part=PART_A))  # a new question
    assert f"part '{PART_A}' is locked (receipt 2, {LOCKED_AT})" in message
    assert f"harness part receipt W --part {PART_A} --kind reopened --reason" in message
    # the same place again would only say `already_asked`: refused too, before any branch
    assert "is locked" in locked_error(work, lambda: ask(work, part=PART_A))
    # an existing question that part B holds, asked with the locked part A: the part would be added
    other = ask(work, "grid D", part=PART_B)
    assert "is locked" in locked_error(work, lambda: ask(work, "grid D", part=PART_A))
    assert "is locked" in locked_error(work, lambda: withdraw(work, held["id"], part=PART_A))
    # a withdraw that would only remove part A from a shared question (`part_removed`)
    assert "is locked" in locked_error(work, lambda: withdraw(work, shared["id"], part=PART_A))
    # part B is not locked: its own writes go through
    assert ask(work, "grid E", part=PART_B)["status"] == "new"
    assert withdraw(work, other["id"], part=PART_B)["status"] == "withdrawn"
    write_receipts(work, PART_A, "checked", "locked", "reopened")
    assert ask(work, part=PART_A)["status"] == "already_asked"
    assert withdraw(work, held["id"], part=PART_A)["status"] == "withdrawn"


def test_withdraw_of_a_question_that_is_already_withdrawn_on_a_locked_part_is_refused_too(world):
    _, work = world
    manifest(work, PART_A)
    q = ask(work, part=PART_A)
    withdraw(work, q["id"], part=PART_A)
    write_receipts(work, PART_A, "locked")
    assert "is locked" in locked_error(work, lambda: withdraw(work, q["id"], part=PART_A))


def test_amend_refused_when_any_holding_part_is_locked(world):
    _, work = world
    manifest(work, PART_A, PART_B)
    q = ask(work, part=PART_A)
    ask(work, part=PART_B)  # part B holds it as well
    write_receipts(work, PART_B, "locked")
    # --part A is open, but the amended message changes part B's hash: refused, naming B
    message = locked_error(work, lambda: amend(work, q["id"], text="new wording", part=PART_A))
    assert f"part '{PART_B}' is locked" in message
    write_receipts(work, PART_A, "locked")
    write_receipts(work, PART_B, "locked", "reopened")
    assert f"part '{PART_A}' is locked" in locked_error(
        work, lambda: amend(work, q["id"], text="new wording", part=PART_A)
    )
    write_receipts(work, PART_A, "locked", "reopened")
    assert amend(work, q["id"], text="new wording", part=PART_A)["status"] == "amended"


def test_a_locked_receipt_without_a_manifest_checks_nothing_for_questions(world):
    _, work = world
    write_receipts(work, PART_A, "locked")
    q = ask(work, part=PART_A)
    assert amend(work, q["id"], text="new wording", part=PART_A)["status"] == "amended"
    assert withdraw(work, q["id"], part=PART_A)["status"] == "withdrawn"


@pytest.mark.parametrize(
    "content", ["{not json", "[]", '{"schema_version": "0.1", "part": "blk1-piles"}', ""]
)
def test_unreadable_receipts_refuse_a_question_write(world, content):
    _, work = world
    manifest(work, PART_A)
    q = ask(work, part=PART_A)
    write_receipts(work, PART_A, text=content)
    rel = f"parts/{PART_A}/receipts.json"
    calls = (
        lambda: ask(work, "grid C", part=PART_A),
        lambda: ask(work, part=PART_A),
        lambda: withdraw(work, q["id"], part=PART_A),
        lambda: amend(work, q["id"], text="new wording", part=PART_A),
    )
    for call in calls:
        assert rel in locked_error(work, call)


@pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0), reason="chmod 000 needs a user"
)
def test_an_unreadable_receipts_path_is_exit_3_for_questions(world):
    _, work = world
    manifest(work, PART_A)
    q = ask(work, part=PART_A)
    path = write_receipts(work, PART_A, "reopened")
    path.chmod(0o000)
    try:
        for call in (
            lambda: ask(work, "grid C", part=PART_A),
            lambda: withdraw(work, q["id"], part=PART_A),
            lambda: amend(work, q["id"], text="new wording", part=PART_A),
        ):
            assert "receipts.json" in locked_error(work, call, code=3)
    finally:
        path.chmod(0o644)
    assert ask(work, "grid C", part=PART_A)["status"] == "new"


def test_cli_ask_on_a_locked_part_is_exit_1_with_the_hint_on_stderr(world, capsys):
    _, work = world
    manifest(work, PART_A)
    write_receipts(work, PART_A, "locked")
    rc, out, err = run_cli(
        capsys, "ask", str(work), "--code", "label_unclear", "--where", "grid A", "--found", "A or 4?",
        "--text", "Is this label A or 4?", "--file", FILE, "--sheet", "model#01", "--part", PART_A,
    )  # fmt: skip
    assert rc == 1 and not out and "is locked" in err
