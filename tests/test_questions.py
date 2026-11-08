"""Stable question keys, the registry, answers and the commands around them (RTI C1 / M14).

The world: an input folder with two native DXF drawings, `harness intake` and `harness read-structure` over
it. Tests that change something work on a copy of that world.
"""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from _callout_fixtures import REL, build_work
from _dxf_fixtures import build_set
from conftest import EXAMPLES
from tekla_harness.answers import check_values, parse_values, record_answer
from tekla_harness.callouts import run_callouts
from tekla_harness.cli import main
from tekla_harness.intake import IntakeError, run_intake
from tekla_harness.marks import run_marks
from tekla_harness.questions import (
    QuestionsError,
    load_ledger,
    question_group,
    question_key,
    questions_summary,
)
from tekla_harness.schemas import validate
from tekla_harness.sheet_text import ReaderError
from tekla_harness.structure import read_structure

PROJECT = "demo-questions"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def questions_of(work: Path, name: str = "questions.json") -> list[dict[str, Any]]:
    return load(work / name)["questions"]


def find(questions: list[dict[str, Any]], code: str, file: str | None = None) -> dict[str, Any]:
    (q,) = [q for q in questions if q["code"] == code and (file is None or q["file"] == file)]
    return q


def ids_by_key(work: Path, name: str) -> dict[str, str]:
    return {q["key"]: q["id"] for q in questions_of(work, name)}


def run_cli(capsys, *argv: str) -> tuple[int, Any, str]:
    code = main(list(argv))
    cap = capsys.readouterr()
    return code, (json.loads(cap.out) if cap.out.strip() else None), cap.err


def rerun_all(root: Path, work: Path) -> None:
    run_intake(root, work, PROJECT)
    read_structure(work, root)


@pytest.fixture(scope="module")
def base_world(tmp_path_factory) -> Path:
    base = tmp_path_factory.mktemp("questions")
    root = base / "input"
    root.mkdir()
    build_set(root, "set.dxf")
    build_set(root, "other.dxf", sheet2_number="S-777")
    run_intake(root, base / "work", PROJECT)
    read_structure(base / "work", root)
    return base


@pytest.fixture
def world(base_world, tmp_path) -> tuple[Path, Path]:
    """(input folder, work folder) of a private copy."""
    target = tmp_path / "w"
    shutil.copytree(base_world, target)
    return target / "input", target / "work"


# --- keys ---------------------------------------------------------------------------------------


REFS = [
    {"file": "a.dxf", "where": "w1", "found": "f1", "sheet": "model#01"},
    {"file": "a.dxf", "where": "w2", "found": "f2"},
]


def test_key_is_16_hex_and_ignores_ref_order_and_extra_fields():
    key = question_key("c", "a.dxf", "ab" * 32, REFS)
    assert len(key) == 16 and int(key, 16) >= 0
    shuffled = [{**REFS[1], "message": "other wording"}, REFS[0]]
    assert question_key("c", "a.dxf", "ab" * 32, shuffled) == key


@pytest.mark.parametrize(
    "change",
    [
        {"code": "d"},
        {"file": "b.dxf"},
        {"sha": "cd" * 32},
        {"refs": [REFS[0]]},
        {"refs": [{**REFS[0], "found": "f1!"}, REFS[1]]},
        {"refs": [{k: v for k, v in REFS[0].items() if k != "sheet"}, REFS[1]]},
    ],
)
def test_key_changes_with_code_file_file_hash_and_refs(change):
    args = {"code": "c", "file": "a.dxf", "sha": "ab" * 32, "refs": REFS} | change
    assert question_key(args["code"], args["file"], args["sha"], args["refs"]) != question_key(
        "c", "a.dxf", "ab" * 32, REFS
    )


def test_key_is_null_safe_for_a_project_level_question():
    assert question_key("c", None, None, REFS) != question_key("c", "a.dxf", None, REFS)
    assert question_key("c", None, None, REFS) == question_key("c", None, None, list(reversed(REFS)))


def test_questions_carry_key_file_answer_and_the_documented_summary(world):
    _, work = world
    doc = load(work / "questions.json")
    assert validate("intake", doc) == []
    for q in doc["questions"]:
        assert len(q["key"]) == 16 and q["answer"] is None
        if q["code"] == "file_set_relation":  # the one project-level question: one ref per drawing file
            assert q["file"] is None and [r["file"] for r in q["refs"]] == ["other.dxf", "set.dxf"]
            continue
        assert q["file"] in ("set.dxf", "other.dxf")
        assert all(r["file"] == q["file"] for r in q["refs"])
    assert doc["summary"] == questions_summary(doc["questions"])
    registry = load(work / "question-registry.json")
    assert validate("question-registry", registry) == []
    assert {q["key"] for q in doc["questions"]} <= set(registry["questions"])
    assert registry["next_id"] == 1 + len(registry["questions"])


# --- id stability -------------------------------------------------------------------------------


def test_two_identical_runs_give_identical_documents_and_ids(world):
    root, work = world
    docs = ("questions.json", "structure-questions.json", "structure-summary.json", "inventory.json")
    before = {n: (work / n).read_bytes() for n in docs}
    runs = load(work / "question-registry.json")["runs"]
    rerun_all(root, work)
    assert {n: (work / n).read_bytes() for n in docs} == before
    registry = load(work / "question-registry.json")
    assert registry["runs"] == runs + 2  # one intake run and one read-structure run
    assert all(e["status"] == "open" for e in registry["questions"].values())


def test_a_new_file_keeps_existing_ids_and_appends_new_ones(world):
    root, work = world
    old_intake, old_struct = ids_by_key(work, "questions.json"), ids_by_key(work, "structure-questions.json")
    highest = max(int(i[2:]) for i in [*old_intake.values(), *old_struct.values()])
    build_set(root, "third.dxf", sheet2_number="S-555")
    rerun_all(root, work)
    new_intake, new_struct = ids_by_key(work, "questions.json"), ids_by_key(work, "structure-questions.json")
    # the project-level file_set_relation lists every drawing file: a new file re-keys it (asked again)
    (file_set,) = [q["key"] for q in questions_of(work, "questions.json") if q["code"] == "file_set_relation"]
    old_set = {
        k
        for k in old_intake
        if load(work / "question-registry.json")["questions"][k]["code"] == "file_set_relation"
    }
    assert len(old_set) == 1 and file_set not in old_set and old_set.isdisjoint(new_intake)
    old_intake = {k: v for k, v in old_intake.items() if k not in old_set}
    assert {k: new_intake[k] for k in old_intake} == old_intake
    assert {k: new_struct[k] for k in old_struct} == old_struct
    added = {
        k: v for d in (new_intake, new_struct) for k, v in d.items() if k not in {*old_intake, *old_struct}
    }
    assert added and all(int(i[2:]) > highest for i in added.values())
    assert len(set(added.values())) == len(added)
    third = [q for n in ("questions.json", "structure-questions.json") for q in questions_of(work, n)]
    assert {q["file"] for q in third if q["id"] in added.values()} == {"third.dxf", None}  # None: file set
    assert load(work / "inventory.json")["summary"]["changes"] == {
        "added": ["third.dxf"],
        "removed": [],
        "changed": [],
    }


def test_first_run_reports_no_changes(base_world):
    changes = load(base_world / "work" / "inventory.json")["summary"]["changes"]
    assert changes == {"added": [], "removed": [], "changed": []}


def test_a_removed_file_obsoletes_only_intake_keys_until_read_structure_runs(world):
    root, work = world
    registry = load(work / "question-registry.json")["questions"]
    other_intake = {
        k: e for k, e in registry.items() if e["file"] == "other.dxf" and e["producer"] == "intake"
    }
    other_struct = {
        k: e for k, e in registry.items() if e["file"] == "other.dxf" and e["producer"] == "structure"
    }
    assert other_intake and other_struct
    (root / "other.dxf").unlink()
    result = run_intake(root, work, PROJECT)
    assert load(work / "inventory.json")["summary"]["changes"]["removed"] == ["other.dxf"]
    assert result.summary["files"] == 1
    after = load(work / "question-registry.json")["questions"]
    assert {after[k]["status"] for k in other_intake} == {"obsolete"}
    assert {after[k]["status"] for k in other_struct} == {"open"}  # not intake's to obsolete
    read_structure(work, root)
    after = load(work / "question-registry.json")["questions"]
    assert {after[k]["status"] for k in other_struct} == {"obsolete"}
    assert all(after[k]["id"] == e["id"] for k, e in {**other_intake, **other_struct}.items())  # ids kept
    assert "other.dxf" not in {q["file"] for q in questions_of(work, "structure-questions.json")}


def test_ids_are_never_reused(world):
    root, work = world
    before = load(work / "question-registry.json")
    (root / "other.dxf").unlink()
    rerun_all(root, work)
    build_set(root, "other.dxf", sheet2_number="S-999")  # a different drawing under the old name
    rerun_all(root, work)
    registry = load(work / "question-registry.json")
    ids = [e["id"] for e in registry["questions"].values()]
    assert len(ids) == len(set(ids))
    assert registry["next_id"] > before["next_id"]
    old = {e["id"] for k, e in before["questions"].items() if e["file"] == "other.dxf"}
    new = {q["id"] for n in ("questions.json", "structure-questions.json") for q in questions_of(work, n)}
    assert not old & {q["id"] for q in questions_of(work) if q["file"] == "other.dxf"}
    assert new <= set(ids)


# --- a changed file ------------------------------------------------------------------------------


def test_a_changed_file_is_asked_again_and_its_old_answer_goes_stale(world):
    root, work = world
    old = find(questions_of(work), "units_confirm_all", "set.dxf")
    untouched = find(questions_of(work), "units_confirm_all", "other.dxf")
    record_answer(
        work,
        old["id"],
        "mm, checked against the 6000 dimension",
        "A. Nguyen",
        {"unit": "mm"},
        role="engineer",
    )
    build_set(root, "set.dxf", sheet2_number="S-888")  # the drawing changed
    result = run_intake(root, work, PROJECT)
    assert load(work / "inventory.json")["summary"]["changes"]["changed"] == ["set.dxf"]
    new = find(questions_of(work), "units_confirm_all", "set.dxf")
    assert new["key"] != old["key"] and new["id"] != old["id"] and new["answer"] is None
    assert find(questions_of(work), "units_confirm_all", "other.dxf")["id"] == untouched["id"]
    (stale,) = load(work / "answers.json")["answers"]
    assert stale["status"] == "stale" and stale["key"] == old["key"] and "changed" in stale["stale_reason"]
    assert stale["answer_text"] == "mm, checked against the 6000 dimension"  # kept, not re-bound
    expected = [
        {
            "question_id": old["id"],
            "key": old["key"],
            "code": "units_confirm_all",
            "file": "set.dxf",
            "reason": stale["stale_reason"],
        }
    ]
    assert result.summary["stale_answers"] == expected
    assert load(work / "inventory.json")["summary"]["stale_answers"] == expected  # also on disk
    run_intake(root, work, PROJECT)  # a rerun on the same input lists the same stale answer
    assert load(work / "inventory.json")["summary"]["stale_answers"] == expected
    registry = load(work / "question-registry.json")["questions"]
    assert registry[old["key"]]["status"] == "obsolete" and registry[new["key"]]["status"] == "open"
    with pytest.raises(QuestionsError, match="obsolete") as caught:
        record_answer(work, old["id"], "again", "A. Nguyen", {"unit": "mm"}, role="engineer")
    assert caught.value.exit_code == 2


def test_an_answer_goes_stale_when_its_producer_no_longer_raises_the_question(tmp_path):
    def raw(code: str, found: str) -> dict[str, Any]:
        refs = [{"file": "a.dxf", "where": "w", "found": found}]
        return question_group(code, True, "m", refs, file="a.dxf")

    hashes = {"a.dxf": "ab" * 32}
    ledger = load_ledger(tmp_path, PROJECT, create=True)
    q1, q2 = ledger.sync("structure", [raw("grid_x", "1"), raw("grid_y", "2")], hashes)
    ledger.answers["answers"].append(
        {
            "key": q2["key"],
            "question_id": q2["id"],
            "code": "grid_y",
            "file": "a.dxf",
            "answer_text": "yes",
            "values": {},
            "answered_by": "A. Nguyen",
            "answered_by_role": "engineer",
            "answered_on": "2026-11-06",
            "status": "active",
        }
    )
    ledger.mark_answered(q2["key"], True)
    again = ledger.sync("structure", [raw("grid_x", "1")], hashes)  # same file, same hash: only q2 is gone
    assert [q["id"] for q in again] == [q1["id"]]
    (stale,) = ledger.stale_answers()
    assert stale["question_id"] == q2["id"] and "no longer raises" in stale["reason"]
    assert ledger.registry["questions"][q2["key"]]["status"] == "obsolete"
    assert ledger.registry["questions"][q1["key"]]["status"] == "open"
    # another producer's run never obsoletes it or stales its answers
    ledger.sync("callouts", [], hashes)
    assert ledger.registry["questions"][q1["key"]]["status"] == "open"  # not obsoleted
    assert ledger.registry["questions"][q2["key"]]["status"] == "obsolete"
    assert len(ledger.stale_answers()) == 1
    # a new question gets a new id: the obsolete one is never reused
    third = ledger.sync("structure", [raw("grid_x", "1"), raw("grid_z", "3")], hashes)
    assert third[1]["id"] not in (q1["id"], q2["id"]) and ledger.registry["next_id"] == 4


def test_structure_answers_of_a_changed_file_go_stale_at_intake(world):
    root, work = world
    q = find(questions_of(work, "structure-questions.json"), "grid_gate1_confirmation", "set.dxf")
    record_answer(work, q["id"], "confirmed", "A. Nguyen", role="engineer")
    build_set(root, "set.dxf", sheet2_number="S-888")
    result = run_intake(root, work, PROJECT)
    assert [a["question_id"] for a in result.summary["stale_answers"]] == [q["id"]]
    entry = load(work / "question-registry.json")["questions"][q["key"]]
    assert entry["status"] == "open"  # structure has not rerun: still raised, but nobody's answer counts
    read_structure(work, root)
    again = find(questions_of(work, "structure-questions.json"), "grid_gate1_confirmation", "set.dxf")
    assert again["key"] != q["key"] and again["answer"] is None


def test_a_rebuilt_drawing_stales_the_answer_and_read_structure_reports_it(world):
    root, work = world
    q = find(questions_of(work, "structure-questions.json"), "grid_gate1_confirmation", "other.dxf")
    record_answer(work, q["id"], "confirmed", "A. Nguyen", role="engineer")
    # the same name now holds a different drawing: the structure producer no longer raises this key
    build_set(root, "other.dxf", sheet2_number="S-999")
    run_intake(root, work, PROJECT)
    result = read_structure(work, root)
    assert [a["question_id"] for a in result.summary["stale_answers"]] == [q["id"]]


# --- the answer command --------------------------------------------------------------------------


def test_answer_is_bound_to_the_key_and_shown_in_every_document(world, capsys):
    _, work = world
    q = find(questions_of(work), "units_confirm_all", "set.dxf")
    before = load(work / "questions.json")["summary"]["blocking_open"]
    code, out, err = run_cli(
        capsys,
        "answer",
        str(work),
        q["id"],
        "--text",
        "Don vi la mm.",
        "--by",
        "A. Nguyen",
        "--role",
        "engineer",
        "--value",
        "unit=mm",
    )
    assert code == 0 and err == "", err
    assert out["superseded"] == 0 and out["refreshed"] == ["questions.json", "structure-questions.json"]
    answer = out["answer"]
    assert validate("answers", load(work / "answers.json")) == []
    assert (answer["key"], answer["question_id"], answer["file"], answer["status"]) == (
        q["key"],
        q["id"],
        "set.dxf",
        "active",
    )
    assert answer["values"] == {"unit": "mm"} and answer["answer_text"] == "Don vi la mm."
    assert len(answer["answered_on"]) == 10
    doc = load(work / "questions.json")
    assert find(doc["questions"], "units_confirm_all", "set.dxf")["answer"] == answer
    assert doc["summary"]["blocking_open"] == before - 1 and doc["summary"]["answered"] == 1
    assert validate("intake", doc) == []
    assert load(work / "question-registry.json")["questions"][q["key"]]["status"] == "answered"


def test_an_answer_survives_reruns_and_lowers_blocking_open(world):
    root, work = world
    structure_open = load(work / "structure-questions.json")["summary"]["blocking_open"]
    intake_open = load(work / "questions.json")["summary"]["blocking_open"]
    units = find(questions_of(work), "units_confirm_all", "set.dxf")
    gate = find(questions_of(work, "structure-questions.json"), "grid_gate1_confirmation", "set.dxf")
    record_answer(work, units["id"], "mm", "A. Nguyen", {"unit": "mm"}, role="engineer")
    record_answer(work, gate["id"], "confirmed", "A. Nguyen", role="engineer")
    rerun_all(root, work)
    again = find(questions_of(work), "units_confirm_all", "set.dxf")
    assert (again["id"], again["key"]) == (units["id"], units["key"]) and again["answer"]["values"] == {
        "unit": "mm"
    }
    assert load(work / "questions.json")["summary"]["blocking_open"] == intake_open - 1
    assert load(work / "structure-questions.json")["summary"]["blocking_open"] == structure_open - 1
    gate_again = find(questions_of(work, "structure-questions.json"), "grid_gate1_confirmation", "set.dxf")
    assert gate_again["id"] == gate["id"] and gate_again["answer"]["answer_text"] == "confirmed"
    registry = load(work / "question-registry.json")["questions"]
    assert registry[units["key"]]["status"] == "answered" and registry[gate["key"]]["status"] == "answered"


def test_a_second_answer_supersedes_the_first(world):
    _, work = world
    q = find(questions_of(work), "units_confirm_all", "other.dxf")
    record_answer(work, q["id"], "cm", "A. Nguyen", {"unit": "cm"}, today=date(2026, 11, 1), role="engineer")
    result = record_answer(
        work, q["id"], "No, mm", "B. Tran", {"unit": "mm"}, today=date(2026, 11, 2), role="engineer"
    )
    assert result["superseded"] == 1
    first, second = load(work / "answers.json")["answers"]
    assert (first["status"], first["values"], first["answered_on"]) == (
        "superseded",
        {"unit": "cm"},
        "2026-11-01",
    )
    assert (second["status"], second["values"], second["answered_by"]) == (
        "active",
        {"unit": "mm"},
        "B. Tran",
    )
    shown = find(questions_of(work), "units_confirm_all", "other.dxf")["answer"]
    assert shown["answer_text"] == "No, mm"
    assert load(work / "questions.json")["summary"]["answered"] == 1


def test_a_non_blocking_answer_does_not_change_blocking_open(world):
    _, work = world
    non_blocking = [
        q for q in questions_of(work) + questions_of(work, "structure-questions.json") if not q["blocking"]
    ]
    if not non_blocking:  # the world may only have blocking questions
        pytest.skip("no non-blocking question in this world")
    q = non_blocking[0]
    name = "questions.json" if q in questions_of(work) else "structure-questions.json"
    before = load(work / name)["summary"]
    record_answer(work, q["id"], "noted", "A. Nguyen", role="engineer")
    after = load(work / name)["summary"]
    assert after["blocking_open"] == before["blocking_open"] and after["answered"] == before["answered"] + 1


@pytest.mark.parametrize(
    ("code", "values", "ok"),
    [
        ("units_confirm_all", {"unit": "mm"}, True),
        ("units_conflict", {"unit": "ft"}, True),
        ("grid_units_doubt", {"unit": "in"}, True),
        ("units_unknown", {"unit": "furlong"}, False),
        ("units_suspect", {}, False),
        ("units_confirm_all", {"unit": "mm", "extra": "x"}, False),
        ("grid_family_axis_assignment", {"F1": "X", "F2": "Y"}, True),
        ("grid_family_axis_assignment", {"F1": "Z"}, False),
        ("grid_family_axis_assignment", {}, False),
        ("member_mark_prefix_meaning", {"C": "column", "TB": "tie beam"}, True),
        ("member_mark_prefix_meaning", {"C": " "}, False),
        ("member_mark_prefix_meaning", {}, False),
        ("grid_gate1_confirmation", {}, True),
        ("grid_gate1_confirmation", {"unit": "mm"}, False),
        ("units_answer_contradicts_evidence", {"unit": "m"}, True),
        ("units_answer_contradicts_evidence", {}, False),
        ("grid_system_axis_unassigned", {"dir1": "X", "dir2": "Y"}, True),
        ("grid_system_axis_unassigned", {"dir1": "X"}, True),  # the question's directions: harness answer
        ("grid_system_axis_unassigned", {"dir3": "X"}, False),
        ("grid_system_axis_unassigned", {"dir1": "Z"}, False),
        ("grid_system_conflict", {}, True),  # takes no value (and harness answer refuses it: see test_status)
    ],
)
def test_structured_values_by_code(code, values, ok):
    assert (check_values(code, values) == []) is ok
    answer = {
        "key": "0123456789abcdef",
        "question_id": "Q-001",
        "code": code,
        "file": None,
        "answer_text": "t",
        "values": values,
        "answered_by": "x",
        "answered_by_role": "engineer",
        "answered_on": "2026-11-06",
        "status": "active",
    }
    doc = {"schema_version": "0.1", "project_id": PROJECT, "answers": [answer]}
    assert (validate("answers", doc) == []) is ok  # the schema says the same as the command


@pytest.mark.parametrize("values", [{"dir1": "X", "dir2": "X"}, {}])
def test_system_axis_values_the_command_refuses_but_the_schema_keeps(values):
    """Two directions on one axis cannot be said in JSON Schema, and {} is how a words-only answer recorded
    before values existed looks (it stays loadable, and assigns nothing): harness answer refuses both."""
    assert check_values("grid_system_axis_unassigned", values) != []
    answer = {
        "key": "0123456789abcdef",
        "question_id": "Q-001",
        "code": "grid_system_axis_unassigned",
        "file": "a.dxf",
        "answer_text": "t",
        "values": values,
        "answered_by": "x",
        "answered_by_role": "engineer",
        "answered_on": "2026-11-06",
        "status": "active",
    }
    assert validate("answers", {"schema_version": "0.1", "project_id": PROJECT, "answers": [answer]}) == []


def test_parse_values():
    assert parse_values(["unit=mm", "F1=X"]) == {"unit": "mm", "F1": "X"}
    assert parse_values(["C=a=b"]) == {"C": "a=b"}
    for bad in (["unit"], ["=mm"], ["unit=mm", "unit=cm"]):
        with pytest.raises(QuestionsError) as caught:
            parse_values(bad)
        assert caught.value.exit_code == 2


def test_answer_refusals_and_exit_codes(world, capsys):
    _, work = world
    q = find(questions_of(work), "units_confirm_all", "set.dxf")
    snapshot = {p.name: p.read_bytes() for p in work.glob("*.json")}
    cases = [
        (
            ["Q-999", "--text", "x", "--by", "me", "--role", "engineer", "--value", "unit=mm"],
            2,
            "unknown question id",
        ),
        (["nope", "--text", "x", "--by", "me", "--role", "engineer"], 2, "unknown question id"),
        ([q["id"], "--text", "   ", "--by", "me", "--role", "engineer", "--value", "unit=mm"], 2, "empty"),
        ([q["id"], "--text", "x", "--by", " ", "--role", "engineer", "--value", "unit=mm"], 2, "empty"),
        (
            [q["id"], "--text", "x", "--by", "me", "--role", "engineer", "--value", "unit=furlong"],
            1,
            "furlong",
        ),
        ([q["id"], "--text", "x", "--by", "me", "--role", "engineer"], 1, "unit="),
        ([q["id"], "--text", "x", "--by", "me", "--role", "engineer", "--value", "unit"], 2, "key=value"),
    ]
    for argv, expected, needle in cases:
        code, out, err = run_cli(capsys, "answer", str(work), *argv)
        assert code == expected and out is None and needle in err, (argv, code, err)
    assert {p.name: p.read_bytes() for p in work.glob("*.json")} == snapshot  # nothing written
    assert not (work / "answers.json").exists()


def test_answer_needs_a_registry(tmp_path, capsys):
    code, _, err = run_cli(
        capsys, "answer", str(tmp_path), "Q-001", "--text", "x", "--by", "me", "--role", "engineer"
    )
    assert code == 2 and "question-registry.json" in err
    code, _, err = run_cli(
        capsys,
        "answer",
        str(tmp_path / "missing"),
        "Q-001",
        "--text",
        "x",
        "--by",
        "me",
        "--role",
        "engineer",
    )
    assert code == 2


def test_answer_help_says_who_runs_it(capsys):
    assert main(["answer", "--help"]) == 0
    text = " ".join(capsys.readouterr().out.split())
    assert "engineer's explicit instruction" in text and "never invent" in text


def test_an_invalid_question_document_is_left_alone_and_reported(world):
    _, work = world
    (work / "structure-questions.json").write_text("{}", encoding="utf-8")
    q = find(questions_of(work), "units_confirm_all", "set.dxf")
    result = record_answer(work, q["id"], "mm", "A. Nguyen", {"unit": "mm"}, role="engineer")
    assert result["refreshed"] == ["questions.json"]
    assert [i["file"] for i in result["not_refreshed"]] == ["structure-questions.json"]
    assert (work / "structure-questions.json").read_text(encoding="utf-8") == "{}"


# --- documents that disagree ----------------------------------------------------------------------


def test_another_project_in_the_same_work_folder_is_refused(world):
    root, work = world
    with pytest.raises(IntakeError, match="demo-questions") as caught:
        run_intake(root, work, "another-project")
    assert caught.value.exit_code == 2


def test_read_structure_needs_the_registry(world):
    root, work = world
    (work / "question-registry.json").unlink()
    with pytest.raises(Exception, match=r"question-registry\.json") as caught:
        read_structure(work, root)
    assert caught.value.exit_code == 2  # type: ignore[attr-defined]


def test_two_active_answers_to_one_key_are_refused(world):
    _, work = world
    q = find(questions_of(work), "units_confirm_all", "set.dxf")
    record_answer(work, q["id"], "mm", "A. Nguyen", {"unit": "mm"}, role="engineer")
    doc = load(work / "answers.json")
    doc["answers"].append({**doc["answers"][0], "answer_text": "cm", "values": {"unit": "cm"}})
    (work / "answers.json").write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(QuestionsError, match="two active answers") as caught:
        load_ledger(work, PROJECT, create=False)
    assert caught.value.exit_code == 1


def test_an_unreadable_previous_inventory_stops_intake(world):
    root, work = world
    (work / "inventory.json").write_text("not json", encoding="utf-8")
    with pytest.raises(IntakeError, match="previous") as caught:
        run_intake(root, work, PROJECT)
    assert caught.value.exit_code == 1


def test_examples_are_valid():
    for name in ("answers", "question-registry"):
        assert validate(name, load(EXAMPLES / f"{name}.example.json")) == []


# --- sheet commands and callouts -----------------------------------------------------------------


@pytest.fixture(scope="module")
def callout_base(tmp_path_factory) -> Path:
    return build_work(tmp_path_factory.mktemp("callout-questions"))


@pytest.fixture
def cwork(callout_base, tmp_path) -> Path:
    target = tmp_path / "copy"
    shutil.copytree(callout_base.parent, target)
    return target / "work"


def test_cli_list_sheets_and_sheet_text(cwork, capsys):
    code, doc, err = run_cli(capsys, "list-sheets", str(cwork))
    assert code == 0 and err == "" and doc["kind"] == "sheet_list" and validate("sheet-text", doc) == []
    assert [s["sheet_id"] for s in doc["files"][0]["sheets"]] == ["model#01", "model#02", "Plot#01"]
    code, doc, err = run_cli(
        capsys, "sheet-text", str(cwork), REL, "model#01", "--contains", "cb300", "--max", "5"
    )
    assert code == 0 and doc["kind"] == "sheet_text" and validate("sheet-text", doc) == []
    assert doc["query"] == {"contains": "cb300", "max_entries": 5}
    assert [e["display_text"] for e in doc["entries"]] == ["CB300-V"]
    code, doc, _ = run_cli(capsys, "sheet-text", str(cwork), REL, "model#01", "--max", "2")
    assert code == 0 and doc["counts"]["returned"] == 2 and doc["counts"]["truncated"] is True


def test_cli_sheet_commands_report_usage_errors(cwork, capsys, tmp_path):
    for argv in (
        ["sheet-text", str(cwork), REL, "model#99"],
        ["sheet-text", str(cwork), "nope.dxf", "model#01"],
        ["sheet-text", str(cwork), REL, "model#01", "--max", "0"],
        ["list-sheets", str(tmp_path / "missing")],
    ):
        code, out, err = run_cli(capsys, *argv)
        assert code == 2 and out is None and err, argv


def test_cli_callouts_writes_documents_and_numbers_questions(cwork, capsys):
    before_intake = ids_by_key(cwork, "questions.json")
    code, summary, err = run_cli(capsys, "callouts", str(cwork))
    assert code == 0 and err == "", err
    assert (cwork / "callouts.json").is_file() and (cwork / "callouts-questions.json").is_file()
    doc = load(cwork / "callouts-questions.json")
    assert validate("intake", doc) == []
    qs = doc["questions"]
    assert {q["code"] for q in qs} == {"callout_ambiguous", "grade_legacy_mapping"}  # prefixes: harness marks
    assert all(q["file"] == REL and all(r["file"] == REL for r in q["refs"]) for q in qs)
    keys = [(not q["blocking"], q["code"], q["file"]) for q in qs]
    assert keys == sorted(keys)
    assert summary["questions"] == len(qs) == doc["summary"]["questions"]
    assert summary["blocking_open"] == doc["summary"]["blocking_open"] == sum(q["blocking"] for q in qs)
    assert summary["outputs"]["questions"] == str(cwork / "callouts-questions.json")
    # ids come from the one registry: after intake's, none reused
    intake_ids = set(before_intake.values())
    assert not intake_ids & {q["id"] for q in qs}
    registry = load(cwork / "question-registry.json")["questions"]
    assert {registry[q["key"]]["producer"] for q in qs} == {"callouts"}
    assert {registry[k]["status"] for k in before_intake} == {"open"}  # callouts never touches intake keys
    counts = load(cwork / "callouts.json")  # the extractor document holds counts, not questions
    assert "questions" not in counts
    assert set(counts["question_counts"]) == {q["code"] for q in qs}
    notations = {s["name"] for q in qs if q["code"] == "callout_ambiguous" for s in q["subjects"]}
    assert {"rebar_plus_join", "section_designation", "steel_grade_standard_mix"} <= notations
    for q in (q for q in qs if q["code"] == "callout_ambiguous"):
        assert q["refs"][0]["message"]  # the wording of the first notation


def test_callouts_are_stable_across_runs_and_survive_an_unrelated_change(cwork):
    run_callouts(cwork)
    first = (cwork / "callouts-questions.json").read_bytes()
    first_json = (cwork / "callouts.json").read_bytes()
    run_callouts(cwork)
    assert (cwork / "callouts-questions.json").read_bytes() == first
    assert (cwork / "callouts.json").read_bytes() == first_json
    ids = ids_by_key(cwork, "callouts-questions.json")
    assert len(ids) == len(questions_of(cwork, "callouts-questions.json"))
    run_intake(cwork.parent / "input", cwork, "demo-callouts")  # intake does not obsolete callouts keys
    registry = load(cwork / "question-registry.json")["questions"]
    assert {registry[k]["status"] for k in ids} == {"open"}


def test_member_mark_prefix_answer_has_values_and_lowers_blocking_open(cwork):
    run_marks(cwork)  # tool wave 2: marks asks member_mark_prefix_meaning
    q = find(questions_of(cwork, "marks-questions.json"), "member_mark_prefix_meaning")
    with pytest.raises(QuestionsError):
        record_answer(
            cwork, q["id"], "C is a column", "A. Nguyen", role="engineer"
        )  # needs at least one prefix meaning
    result = record_answer(
        cwork, q["id"], "C cot, D dam", "A. Nguyen", {"C": "column", "D": "beam"}, role="engineer"
    )
    assert result["summaries"]["marks-questions.json"]["blocking_open"] == (
        load(cwork / "marks-questions.json")["summary"]["blocking_questions"] - 1
    )
    summary = run_marks(cwork).summary
    assert summary["answered"] == 1
    assert find(questions_of(cwork, "marks-questions.json"), "member_mark_prefix_meaning")["answer"][
        "values"
    ] == {"C": "column", "D": "beam"}


def test_callouts_checks_the_input_folder_when_given(cwork, capsys):
    root = cwork.parent / "input"
    code, summary, err = run_cli(capsys, "callouts", str(cwork), "--input-dir", str(root))
    assert code == 0 and summary["questions"] > 0, err
    (root / REL).write_bytes((root / REL).read_bytes() + b"\n")
    snapshot = (cwork / "callouts-questions.json").read_bytes()
    code, out, err = run_cli(capsys, "callouts", str(cwork), "--input-dir", str(root))
    assert code == 1 and out is None and "changed since intake" in err
    assert (cwork / "callouts-questions.json").read_bytes() == snapshot
    code, _, err = run_cli(capsys, "callouts", str(cwork), "--input-dir", str(cwork.parent / "nope"))
    assert code == 2


def test_callouts_needs_the_registry(cwork):
    (cwork / "question-registry.json").unlink()
    with pytest.raises(ReaderError, match=r"question-registry\.json") as caught:
        run_callouts(cwork)
    assert caught.value.exit_code == 2
