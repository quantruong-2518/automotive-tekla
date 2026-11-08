"""`harness ask`: the drawing-reader agent raises and withdraws questions through the registry."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from _dxf_fixtures import build_set
from tekla_harness.answers import record_answer
from tekla_harness.ask import ask_question, reader_key, static_owner, withdraw_question
from tekla_harness.cli import main
from tekla_harness.intake import run_intake
from tekla_harness.questions import QuestionsError
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
    rc, out, _ = run_cli(capsys, "answer", str(work), q["id"], "--text", "It is A.", "--by", "eng")
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
