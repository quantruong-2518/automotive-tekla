"""`harness ask`: the drawing-reader agent raises and withdraws questions through the registry."""

from __future__ import annotations

import json
import shutil
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


def test_the_reader_document_is_checked_against_its_own_schema_before_writing(world):
    """A question with two refs is a valid intake question but not a reader one: nothing is written."""
    _, work = world
    q = ask(work)
    doc = load(work / "reader-questions.json")
    doc["questions"][0]["refs"].append({"file": FILE, "where": "grid Z", "found": "f"})
    (work / "reader-questions.json").write_text(json.dumps(doc), encoding="utf-8")
    snapshot = (work / "question-registry.json").read_bytes()
    with pytest.raises(QuestionsError) as caught:
        amend_question(work, q["id"], text="mới")
    assert caught.value.exit_code == 1 and "would be invalid" in str(caught.value)
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


def test_an_answer_keeps_the_amendments(world):
    _, work = world
    q = ask(work)
    amend_question(work, q["id"], text="mới", places=["model#05"])
    record_answer(work, q["id"], "A", "eng", role="engineer")
    after = the_question(work, q["id"])
    assert after["message"] == "mới" and after["places"] == ["model#05"] and len(after["amendments"]) == 1
    assert after["answer"]["answer_text"] == "A"
