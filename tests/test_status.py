"""`harness grid-system`, `harness status` and the `harness answer` file guard, over a real work folder.

The world: an input folder with two synthetic DXF drawings, taken through intake, read-structure, callouts and
grid-system. Tests that change something work on a copy of it.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest
from ezdxf.filemanagement import new

from _dxf_fixtures import build_set
from tekla_harness.answers import record_answer
from tekla_harness.callouts import run_callouts
from tekla_harness.cli import main
from tekla_harness.grid_system import GridSystemError, build_grid_systems, run_grid_systems
from tekla_harness.intake import run_intake
from tekla_harness.marks import run_marks
from tekla_harness.questions import (
    AXIS_CODE,
    CONFLICT_CODE,
    CONTRADICTION_CODE,
    SELECT_CODE,
    SYSTEM_AXIS_CODE,
    UNIT_CODES,
    QuestionsError,
)
from tekla_harness.schemas import validate
from tekla_harness.status import StatusError, build_status
from tekla_harness.structure import read_structure

PROJECT = "demo-status"
QUESTION_FILES = ("questions.json", "structure-questions.json", "grid-system-questions.json")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def run_cli(capsys, *argv: str) -> tuple[int, Any, str]:
    code = main(list(argv))
    cap = capsys.readouterr()
    return code, (json.loads(cap.out) if cap.out.strip() else None), cap.err


def questions_of(work: Path, name: str) -> list[dict[str, Any]]:
    return load(work / name)["questions"]


def find(questions: list[dict[str, Any]], code: str, file: str | None = None) -> dict[str, Any]:
    (q,) = [q for q in questions if q["code"] == code and (file is None or q["file"] == file)]
    return q


def by_label(status: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {p["producer"]: p for p in status["producers"]}


def rerun_all(root: Path, work: Path) -> None:
    run_intake(root, work, PROJECT)
    read_structure(work, root)
    run_callouts(work, root)
    run_marks(work, root)
    run_grid_systems(work)


@pytest.fixture(scope="module")
def base_world(tmp_path_factory) -> Path:
    base = tmp_path_factory.mktemp("status")
    root = base / "input"
    root.mkdir()
    build_set(root, "set.dxf")
    build_set(root, "other.dxf", sheet2_number="S-777")
    rerun_all(root, base / "work")
    return base


@pytest.fixture
def world(base_world, tmp_path) -> tuple[Path, Path]:
    """(input folder, work folder) of a private copy."""
    target = tmp_path / "w"
    shutil.copytree(base_world, target)
    return target / "input", target / "work"


def values_for(q: dict[str, Any]) -> dict[str, str]:
    """Structured values an answer to this question needs (the answers are test data, not engineering)."""
    if q["code"] in UNIT_CODES:
        return {"unit": "mm"}
    if q["code"] == AXIS_CODE:
        dirs = re.findall(r"(F\d+): dir \(([-\d.]+), ", q["refs"][0]["found"])
        return {fid: ("X" if float(x) == 0.0 else "Y") for fid, x in dirs}
    if q["code"] == SYSTEM_AXIS_CODE:  # vertical lines (90 deg) are Tekla X
        dirs = re.findall(r"(dir\d): \S+ labels .*?, angle ([-\d.]+) deg", q["refs"][0]["found"])
        return {name: ("X" if abs(float(angle) - 90.0) < 45.0 else "Y") for name, angle in dirs}
    if q["code"] == "file_set_relation":  # one project: the grids of both files are compared
        return {"set1": ",".join(r["file"] for r in q["refs"])}
    return {}


def answer_blocking(work: Path, names: tuple[str, ...], skip: tuple[str, ...] = ()) -> None:
    for name in names:
        for q in questions_of(work, name):
            if q["blocking"] and q["answer"] is None and q["code"] not in skip:
                record_answer(work, q["id"], "test answer", "tester", values_for(q), role="engineer")


def answer_select(work: Path, *, separate: bool = True, systems: str | None = None) -> dict[str, Any]:
    """Answer grid_system_select with every system (or `systems`), declared separate buildings."""
    select = find(questions_of(work, "grid-system-questions.json"), SELECT_CODE)
    ids = systems or ",".join(r["where"] for r in select["refs"])
    values = {"systems": ids, **({"separate": ids} if separate and "," in ids else {})}
    return record_answer(work, select["id"], "test answer", "tester", values, role="engineer")


@pytest.fixture(scope="module")
def ready_world(base_world, tmp_path_factory) -> Path:
    """Every blocking question answered with the structured values it needs, grid-system rerun: gate 1 is
    ready. X/Y is answered per grid system; the two conflicting systems are declared separate buildings."""
    target = tmp_path_factory.mktemp("ready") / "w"
    shutil.copytree(base_world, target)
    work = target / "work"
    answer_blocking(work, ("questions.json", "structure-questions.json"))
    run_grid_systems(work)  # now reads the units answers
    answer_select(work)
    answer_blocking(work, ("grid-system-questions.json",), skip=(CONFLICT_CODE,))
    run_grid_systems(work)  # reads the select and axis answers: the conflict closes, the axes are assigned
    return target


def ready_gate1(work: Path) -> dict[str, Any]:
    """gate1 of the ready world: no reason, and the conflict between the two separate buildings closed by the
    select answer (lifecycle.closures, fix 5a)."""
    gs = questions_of(work, "grid-system-questions.json")
    closed = {
        "id": find(gs, CONFLICT_CODE)["id"],
        "reason": "separate",
        "question_id": find(gs, SELECT_CODE)["id"],
    }
    return {"ready_for_gate1": True, "reasons": [], "closed": [closed]}


@pytest.fixture
def ready(ready_world, tmp_path) -> tuple[Path, Path]:
    target = tmp_path / "r"
    shutil.copytree(ready_world, target)
    return target / "input", target / "work"


# --- the registry records blocking and the file hash ----------------------------------------------------


def test_registry_entries_record_blocking_and_file_sha256(world):
    _, work = world
    registry = load(work / "question-registry.json")
    assert validate("question-registry", registry) == []
    inventory = {r["path"]: r["sha256"] for r in load(work / "inventory.json")["files"]}
    docs = {q["key"]: q for name in QUESTION_FILES for q in questions_of(work, name)}
    assert docs
    for key, q in docs.items():
        entry = registry["questions"][key]
        assert entry["blocking"] is q["blocking"]
        assert entry["file_sha256"] == (inventory[q["file"]] if q["file"] else None)
    assert {e["producer"] for e in registry["questions"].values()} == {"intake", "structure", "grid-system"}


# --- harness grid-system --------------------------------------------------------------------------------


def test_grid_system_command_writes_documents_drawings_and_numbered_questions(world, capsys):
    _, work = world
    for stale in (work / "grid-systems.json", work / "grid-system-questions.json"):
        stale.unlink()
    shutil.rmtree(work / "structure" / "grid-systems")
    code, summary, err = run_cli(capsys, "grid-system", str(work))
    assert code == 0 and err == "", err
    doc = load(work / "grid-systems.json")
    assert validate("grid-system", doc) == []
    assert doc["inventory_sha256"] == build_status(work)["inventory_sha256"]
    drawings = sorted(p.name for p in (work / "structure" / "grid-systems").glob("*.svg"))
    assert drawings == [f"{s['system_id']}.svg" for s in doc["systems"]] and drawings
    qdoc = load(work / "grid-system-questions.json")
    assert validate("intake", qdoc) == []
    qs = qdoc["questions"]
    keys = [(not q["blocking"], q["code"], q["file"] or "") for q in qs]
    assert keys == sorted(keys)
    own = (SYSTEM_AXIS_CODE, CONFLICT_CODE, CONTRADICTION_CODE)  # one question per system / pair / file
    merged = [q for q in qs if q["code"] not in own]
    assert len({(q["code"], q["blocking"], q["file"]) for q in merged}) == len(merged)
    axis = [q for q in qs if q["code"] == SYSTEM_AXIS_CODE]
    assert sorted(q["refs"][0]["where"] for q in axis) == [s["system_id"] for s in doc["systems"]]
    assert all(q["count"] == 1 and [x["name"] for x in q["subjects"]] == ["dir1", "dir2"] for q in axis)
    select = find(qs, SELECT_CODE)
    assert select["file"] is None and select["blocking"]
    assert [r["where"] for r in select["refs"]] == [s["system_id"] for s in doc["systems"]]
    assert all(r["file"] for r in select["refs"])
    assert {q["code"] for q in qs} <= {
        "grid_system_select",
        "grid_system_conflict",
        "grid_system_units_unconfirmed",
        "grid_system_axis_unassigned",
        "units_answer_contradicts_evidence",
    }
    registry = load(work / "question-registry.json")["questions"]
    assert {registry[q["key"]]["producer"] for q in qs} == {"grid-system"}
    assert registry[select["key"]]["file"] is None
    assert summary["questions"] == len(qs) == qdoc["summary"]["questions"]
    assert summary["blocking_open"] == qdoc["summary"]["blocking_open"] == sum(q["blocking"] for q in qs)
    assert summary["outputs"]["questions"] == str(work / "grid-system-questions.json")
    assert summary["grid_systems"][0]["svg"] == doc["systems"][0]["svg"]


def test_grid_system_rerun_keeps_ids_and_documents(world):
    _, work = world
    before = {n: (work / n).read_bytes() for n in ("grid-systems.json", "grid-system-questions.json")}
    ids = {q["key"]: q["id"] for q in questions_of(work, "grid-system-questions.json")}
    run_grid_systems(work)
    assert {n: (work / n).read_bytes() for n in before} == before
    assert {q["key"]: q["id"] for q in questions_of(work, "grid-system-questions.json")} == ids


def test_grid_system_no_svg_clears_old_drawings(world, capsys):
    _, work = world
    assert any((work / "structure" / "grid-systems").glob("*.svg"))
    code, summary, _ = run_cli(capsys, "grid-system", str(work), "--no-svg")
    assert code == 0 and not (work / "structure" / "grid-systems").exists()
    assert summary["outputs"]["svg_dir"] is None and summary["grid_systems"][0]["svg"] is None
    assert (work / "grid-systems.json").is_file()


def test_grid_system_answers_flow_through_the_ledger(world, capsys):
    _, work = world
    units = [q for q in questions_of(work, "questions.json") if q["code"] == "units_confirm_all"]
    for q in units:
        record_answer(work, q["id"], "mm", "tester", {"unit": "mm"}, role="engineer")
    code, summary, _ = run_cli(capsys, "grid-system", str(work))
    assert code == 0
    doc = load(work / "grid-systems.json")
    assert all(s["units"]["status"] == "confirmed" for s in doc["systems"])  # the answers were read
    assert "grid_system_units_unconfirmed" not in {
        q["code"] for q in questions_of(work, "grid-system-questions.json")
    }
    select = find(questions_of(work, "grid-system-questions.json"), SELECT_CODE)
    before = summary["blocking_open"]
    result = record_answer(
        work, select["id"], "S001 is the warehouse", "tester", {"systems": "S001"}, role="engineer"
    )
    assert result["answer"]["values"] == {"systems": ["S001"]}
    assert "grid-system-questions.json" in result["refreshed"]  # harness answer refreshes this document too
    assert find(questions_of(work, "grid-system-questions.json"), SELECT_CODE)["answer"] is not None
    assert load(work / "grid-system-questions.json")["summary"]["blocking_open"] == before - 1
    run_grid_systems(work)  # the answer is kept: same question, same key
    assert find(questions_of(work, "grid-system-questions.json"), SELECT_CODE)["answer"] is not None


@pytest.mark.parametrize(
    "value",
    ["systems=S1", "systems=S001,S001", "systems=", "other=S001", "systems=S001;S002"],
)
def test_select_answer_values_are_checked(world, capsys, value):
    _, work = world
    select = find(questions_of(work, "grid-system-questions.json"), SELECT_CODE)
    code, out, err = run_cli(
        capsys,
        "answer",
        str(work),
        select["id"],
        "--text",
        "x",
        "--by",
        "me",
        "--role",
        "engineer",
        "--value",
        value,
    )
    assert code == 1 and out is None and "systems" in err
    assert not (work / "answers.json").exists()
    other = find(questions_of(work, "grid-system-questions.json"), "grid_system_conflict")
    code, _, err = run_cli(
        capsys,
        "answer",
        str(work),
        other["id"],
        "--text",
        "x",
        "--by",
        "me",
        "--role",
        "engineer",
        "--value",
        "systems=S001",
    )
    assert code == 1 and "take no value" in err


def test_grid_system_needs_the_earlier_steps(tmp_path, world):
    _, work = world
    with pytest.raises(GridSystemError) as caught:
        run_grid_systems(tmp_path / "missing")
    assert caught.value.exit_code == 2
    bare = tmp_path / "bare"
    bare.mkdir()
    with pytest.raises(GridSystemError) as caught:
        run_grid_systems(bare)
    assert caught.value.exit_code == 2 and "question-registry.json" in str(caught.value)
    (work / "structure-summary.json").unlink()
    snapshot = {p.name: p.read_bytes() for p in work.glob("*.json")}
    with pytest.raises(GridSystemError, match="read-structure") as caught:
        run_grid_systems(work)
    assert caught.value.exit_code == 2
    assert {p.name: p.read_bytes() for p in work.glob("*.json")} == snapshot  # nothing written


def test_grid_system_refuses_a_stale_read_structure(world, capsys):
    root, work = world
    build_set(root, "set.dxf", sheet2_number="S-888")
    run_intake(root, work, PROJECT)  # inventory.json changed, structure-summary.json did not
    snapshot = {p.name: p.read_bytes() for p in work.glob("*.json")}
    code, out, err = run_cli(capsys, "grid-system", str(work))
    assert code == 1 and out is None and "rerun `harness read-structure`" in err
    assert {p.name: p.read_bytes() for p in work.glob("*.json")} == snapshot


# --- harness answer: the file guard ---------------------------------------------------------------------


def test_answer_is_refused_when_the_questions_file_changed_since_it_was_raised(world, capsys):
    root, work = world
    structure_q = find(
        questions_of(work, "structure-questions.json"), "grid_family_axis_assignment", "set.dxf"
    )
    intake_q = find(questions_of(work, "questions.json"), "units_confirm_all", "set.dxf")
    build_set(root, "set.dxf", sheet2_number="S-888")  # the drawing changed ...
    run_intake(root, work, PROJECT)  # ... and intake saw it; read-structure has not rerun yet
    snapshot = {p.name: p.read_bytes() for p in work.glob("*.json")}
    code, out, err = run_cli(
        capsys,
        "answer",
        str(work),
        structure_q["id"],
        "--text",
        "x",
        "--by",
        "me",
        "--role",
        "engineer",
        "--value",
        "F001=X",
    )
    assert code == 1 and out is None
    assert "file changed since this question was raised" in err and "rerun `harness read-structure`" in err
    assert "set.dxf" in err
    assert {p.name: p.read_bytes() for p in work.glob("*.json")} == snapshot  # nothing written
    # intake's own question was obsoleted by the intake rerun: the older, clearer refusal comes first
    code, _, err = run_cli(
        capsys,
        "answer",
        str(work),
        intake_q["id"],
        "--text",
        "x",
        "--by",
        "me",
        "--role",
        "engineer",
        "--value",
        "unit=mm",
    )
    assert code == 2 and "obsolete" in err
    # an untouched file's question is still accepted
    other = find(questions_of(work, "structure-questions.json"), "grid_family_axis_assignment", "other.dxf")
    code, _, _ = run_cli(
        capsys,
        "answer",
        str(work),
        other["id"],
        "--text",
        "x",
        "--by",
        "me",
        "--role",
        "engineer",
        "--value",
        "F001=X",
    )
    assert code == 0


def test_answer_names_the_producer_command_and_a_removed_file(world):
    root, work = world
    callouts_like = find(questions_of(work, "grid-system-questions.json"), "grid_system_conflict")
    (root / callouts_like["file"]).unlink()
    run_intake(root, work, PROJECT)
    with pytest.raises(QuestionsError, match="rerun `harness grid-system`") as caught:
        record_answer(work, callouts_like["id"], "x", "me", role="engineer")
    assert caught.value.exit_code == 1 and "removed" in str(caught.value)


def test_answer_guard_skips_project_questions_legacy_entries_and_folders_without_inventory(world):
    _, work = world
    select = find(questions_of(work, "grid-system-questions.json"), SELECT_CODE)
    structure_q = find(questions_of(work, "structure-questions.json"), "grid_label_missing", "set.dxf")
    registry = load(work / "question-registry.json")
    del registry["questions"][structure_q["key"]]["file_sha256"]  # an entry from before the field existed
    registry["questions"][structure_q["key"]]["blocking"] = True
    (work / "question-registry.json").write_text(json.dumps(registry), encoding="utf-8")
    inventory = load(work / "inventory.json")
    inventory["files"][0]["sha256"] = "0" * 64  # every file differs from what the questions were raised on
    inventory["files"][1]["sha256"] = "1" * 64
    (work / "inventory.json").write_text(json.dumps(inventory), encoding="utf-8")
    record_answer(work, select["id"], "x", "me", role="engineer")  # file null: not checked
    record_answer(work, structure_q["id"], "x", "me", role="engineer")  # nothing recorded: not checked
    (work / "inventory.json").unlink()
    other = find(questions_of(work, "structure-questions.json"), "grid_label_missing", "other.dxf")
    record_answer(work, other["id"], "x", "me", role="engineer")  # no inventory.json at all: not checked


# --- harness status -------------------------------------------------------------------------------------


def test_status_counts_come_from_the_registry_and_answers_not_from_the_question_files(world):
    _, work = world
    status = build_status(work)
    assert validate("status", status) == []
    labels = by_label(status)
    assert list(labels) == ["intake", "read-structure", "callouts", "marks", "grid-system", "reader"]
    docs = {
        "intake": "questions.json",
        "read-structure": "structure-questions.json",
        "grid-system": "grid-system-questions.json",
    }
    for label, name in docs.items():
        qs = questions_of(work, name)
        counts = labels[label]["questions"]
        assert counts["total"] == len(qs) and counts["blocking"] == sum(q["blocking"] for q in qs)
        assert counts["blocking_open"] == load(work / name)["summary"]["blocking_open"]
        assert counts["blocking_unknown"] == 0 and counts["answered"] == 0
        assert len(labels[label]["blocking_open_ids"]) == counts["blocking_open"]
    q = find(questions_of(work, "structure-questions.json"), "grid_label_missing", "set.dxf")
    record_answer(work, q["id"], "ok", "me", role="engineer")
    for name in QUESTION_FILES:  # question documents that are wrong or gone change nothing
        (work / name).write_text("{}", encoding="utf-8")
    after = by_label(build_status(work))["read-structure"]["questions"]
    assert (
        after["answered"] == 1
        and after["blocking_open"] == labels["read-structure"]["questions"]["blocking_open"] - 1
    )


def test_status_outputs_are_fresh_stale_or_missing_with_the_command_that_fixes_them(world):
    root, work = world
    labels = by_label(build_status(work))
    assert {p["outputs"]["status"] for k, p in labels.items() if k != "reader"} == {"fresh"}
    assert labels["reader"]["outputs"] == {"status": "n/a", "files": [], "reason": None, "rerun": None}
    assert all(p["outputs"]["rerun"] is None for p in labels.values())
    (work / "callouts.json").unlink()
    callouts = by_label(build_status(work))["callouts"]["outputs"]
    assert callouts["status"] == "missing" and callouts["rerun"] == f"harness callouts {work}"
    run_callouts(work, root)
    build_set(root, "set.dxf", sheet2_number="S-888")
    run_intake(root, work, PROJECT)  # a new inventory.json: everything built from the old one is stale
    labels = by_label(build_status(work))
    assert labels["intake"]["outputs"]["status"] == "fresh"
    assert {labels[k]["outputs"]["status"] for k in ("read-structure", "callouts", "grid-system")} == {
        "stale"
    }
    assert (
        labels["read-structure"]["outputs"]["rerun"]
        == f"harness read-structure {work} --input-dir <input_dir>"
    )
    assert labels["grid-system"]["outputs"]["rerun"] == f"harness grid-system {work}"
    assert len(labels["intake"]["stale_answers"]) == 0


def test_status_sees_answers_given_after_grid_system_ran(ready):
    _, work = ready
    assert build_status(work)["producers"][3]["outputs"]["status"] == "fresh"
    unit = next(a for a in load(work / "answers.json")["answers"] if a["code"] in UNIT_CODES)
    record_answer(work, unit["question_id"], "now cm", "me", {"unit": "cm"}, role="engineer")
    out = by_label(build_status(work))["grid-system"]["outputs"]
    assert out["status"] == "stale" and "answers" in out["reason"]


def test_status_lists_stale_answers_under_their_producer(world):
    root, work = world
    q = find(questions_of(work, "structure-questions.json"), "grid_family_axis_assignment", "set.dxf")
    record_answer(work, q["id"], "x", "me", {"F001": "X"}, role="engineer")
    build_set(root, "set.dxf", sheet2_number="S-888")
    run_intake(root, work, PROJECT)
    labels = by_label(build_status(work))
    (stale,) = labels["read-structure"]["stale_answers"]
    assert stale["question_id"] == q["id"] and stale["code"] == "grid_family_axis_assignment"
    assert all(not labels[k]["stale_answers"] for k in ("intake", "callouts", "grid-system"))


def test_status_counts_registry_entries_without_a_blocking_flag_as_blocking(world):
    _, work = world
    registry = load(work / "question-registry.json")
    entry = next(
        e for e in registry["questions"].values() if e["producer"] == "intake" and e["status"] == "open"
    )
    was_blocking = entry.pop("blocking")
    (work / "question-registry.json").write_text(json.dumps(registry), encoding="utf-8")
    counts = by_label(build_status(work))["intake"]["questions"]
    assert counts["blocking_unknown"] == 1 and counts["blocking"] >= 1
    status = build_status(work)
    reason = next(r for r in status["gate1"]["reasons"] if r.startswith("intake: ") and "blocking" in r)
    assert "no recorded blocking flag" in reason and "harness intake" in reason
    assert was_blocking in (True, False)


def test_gate1_is_not_ready_with_every_reason_named(world):
    _, work = world
    gate = build_status(work)["gate1"]
    assert gate["ready_for_gate1"] is False
    text = "\n".join(gate["reasons"])
    ids = {
        q["file"]: q["id"] for q in questions_of(work, "questions.json") if q["code"] == "units_confirm_all"
    }
    for needle in (
        "units: set.dxf is not confirmed: the engineer runs: "
        f'harness answer {work} {ids["set.dxf"]} --text "..." --by "..." --role engineer --value',
        "--value unit=mm|cm|m|in|ft (units_confirm_all)",
        "units: other.dxf is not confirmed: the engineer runs: "
        f"harness answer {work} {ids['other.dxf']} --text",
        "grid_system_select",
        # two units questions and the project-level file set question
        f"intake: 3 blocking question(s) open ({ids['other.dxf']}, {ids['set.dxf']}, "
        f"{find(questions_of(work, 'questions.json'), 'file_set_relation')['id']})",
        "read-structure: ",
        "grid-system: ",
    ):
        assert needle in text, needle
    assert "callouts: " not in text  # callouts' blocking questions do not stop gate 1


def test_gate1_is_ready_when_everything_is_answered_and_fresh(ready):
    _, work = ready
    status = build_status(work)
    assert status["gate1"] == ready_gate1(work)
    for p in status["producers"]:
        assert p["outputs"]["status"] == ("n/a" if p["producer"] == "reader" else "fresh")
    assert by_label(status)["callouts"]["questions"]["blocking_open"] == 0  # none raised by this world


def test_gate1_needs_the_select_answer_and_every_used_system_axis_assigned(ready):
    _, work = ready
    answers = load(work / "answers.json")
    select_answer = next(a for a in answers["answers"] if a["code"] == SELECT_CODE)
    # naming a system the latest grid-systems.json does not have (harness answer refuses it now: a damaged or
    # older answers.json is the only way in)
    with pytest.raises(QuestionsError, match="systems names S009") as caught:
        record_answer(work, select_answer["question_id"], "S009", "me", {"systems": "S009"}, role="engineer")
    assert caught.value.exit_code == 1
    select_answer["values"]["systems"] = ["S009"]
    (work / "answers.json").write_text(json.dumps(answers), encoding="utf-8")
    stale = build_status(work)["gate1"]["reasons"]  # grid-system reads the select answer: rerun it first
    assert "grid systems: not checked, the grid-system outputs are stale" in stale
    run_grid_systems(work)
    reasons = build_status(work)["gate1"]["reasons"]
    assert any("S009" in r and "not in the latest grid-systems.json" in r for r in reasons)
    # no select answer at all
    answers = load(work / "answers.json")
    answers["answers"] = [a for a in answers["answers"] if a["code"] != SELECT_CODE]
    (work / "answers.json").write_text(json.dumps(answers), encoding="utf-8")
    run_grid_systems(work)
    reasons = build_status(work)["gate1"]["reasons"]
    assert any(
        f"{SELECT_CODE} (Q-" in r and "not answered" in r and f"harness answer {work} Q-" in r
        for r in reasons
    )


def test_gate1_needs_axis_assignment_not_just_a_word_answer(ready):
    _, work = ready
    answers = load(work / "answers.json")
    answers["answers"] = [a for a in answers["answers"] if a["code"] != SYSTEM_AXIS_CODE]
    (work / "answers.json").write_text(json.dumps(answers), encoding="utf-8")
    status = build_status(work)  # the axis answers are gone: grid-systems.json is stale AND unassigned
    assert status["gate1"]["ready_for_gate1"] is False
    run_grid_systems(work)
    status = build_status(work)
    text = "\n".join(status["gate1"]["reasons"])
    axis = {
        q["refs"][0]["where"]: q
        for q in questions_of(work, "grid-system-questions.json")
        if q["code"] == SYSTEM_AXIS_CODE
    }
    for sid, q in axis.items():  # F-04: the reason names the question id to answer and the values it needs
        assert f"{sid} has no Tekla X/Y" in text
        assert (
            f'harness answer {work} {q["id"]} --text "..." --by "..." --role engineer '
            "--value dir1=X|Y --value dir2=X|Y" in text
        )
    assert "grid_family_axis_assignment" in text
    # words alone are refused: an answer that would assign nothing is not recorded
    q = next(iter(axis.values()))
    for values in ({}, {"dir1": "X"}, {"dir1": "X", "dir2": "X"}, {"dir3": "X", "dir1": "Y"}):
        with pytest.raises(QuestionsError) as caught:
            record_answer(work, q["id"], "X is the numbers", "me", values, role="engineer")
        assert caught.value.exit_code == 1, values
    assert "has no Tekla X/Y" in "\n".join(build_status(work)["gate1"]["reasons"])
    # the family form still assigns (unioned with the system form)
    for fq in questions_of(work, "structure-questions.json"):
        if fq["code"] == AXIS_CODE:
            record_answer(work, fq["id"], "test answer", "me", values_for(fq), role="engineer")
    run_grid_systems(work)
    status = build_status(work)
    assert status["gate1"] == ready_gate1(work)
    assert all(
        not q["blocking"]
        for q in questions_of(work, "grid-system-questions.json")
        if q["code"] == SYSTEM_AXIS_CODE
    )


def test_gate1_needs_the_level_questions_answered(ready):
    _, work = ready
    registry = load(work / "question-registry.json")
    for number, code in ((900, "level_storey_selection"), (901, "level_finished_vs_structural")):
        registry["questions"][f"{number:016x}"] = {
            "id": f"Q-{number}",
            "code": code,
            "file": "set.dxf",
            "producer": "structure",
            "status": "open",
            "first_seen_run": 1,
            "last_seen_run": 1,
            "blocking": True,
            "file_sha256": next(
                r["sha256"] for r in load(work / "inventory.json")["files"] if r["path"] == "set.dxf"
            ),
        }
    registry["next_id"] = 902
    (work / "question-registry.json").write_text(json.dumps(registry), encoding="utf-8")
    reasons = build_status(work)["gate1"]["reasons"]
    assert "levels: Q-900 level_storey_selection (set.dxf) is not answered" in reasons
    assert "levels: Q-901 level_finished_vs_structural (set.dxf) is not answered" in reasons
    record_answer(work, "Q-900", "storeys are ...", "me", role="engineer")
    record_answer(work, "Q-901", "finished", "me", role="engineer")
    after = build_status(work)["gate1"]
    assert not [r for r in after["reasons"] if r.startswith("levels:")]
    assert after == ready_gate1(work)  # the added blocking questions are answered too


def test_gate1_needs_a_units_answer_for_every_probed_file(ready):
    _, work = ready
    answers = load(work / "answers.json")
    for a in answers["answers"]:
        if a["code"] == "units_confirm_all" and a["file"] == "other.dxf":
            a["status"] = "superseded"
    (work / "answers.json").write_text(json.dumps(answers), encoding="utf-8")
    reasons = build_status(work)["gate1"]["reasons"]
    qid = find(questions_of(work, "questions.json"), "units_confirm_all", "other.dxf")["id"]
    expected = (
        f"units: other.dxf is not confirmed: the engineer runs: harness answer {work} {qid} "
        '--text "..." --by "..." --role engineer --value unit='
    )
    assert any(r.startswith(expected) for r in reasons), reasons
    assert not any(r.startswith("units: set.dxf") for r in reasons)


# --- gate 1: fewer, sharper questions; nothing closes without a structured value (EVAL-1 fix 5) ------------


def answer_units(work: Path, unit: str = "mm") -> None:
    for q in questions_of(work, "questions.json"):
        if q["code"] == "units_confirm_all":
            record_answer(work, q["id"], "test answer", "tester", {"unit": unit}, role="engineer")


def blocking_now(work: Path) -> set[tuple[str, str]]:
    return {
        (q["code"], q["refs"][0]["where"][:4])
        for q in questions_of(work, "grid-system-questions.json")
        if q["blocking"]
    }


def test_words_in_the_select_answer_close_no_conflict_and_no_axis_question(world, capsys):
    """EVAL-1 F-26 replay: the select answer said in words "S004/S005 are variant views of 267, not used"
    without a structured value; the conflict and axis questions must keep blocking."""
    _, work = world
    answer_units(work)
    run_grid_systems(work)
    select = find(questions_of(work, "grid-system-questions.json"), SELECT_CODE)
    record_answer(
        work, select["id"], "S004/S005 are variant views of 267, not used", "tester", role="engineer"
    )
    run_grid_systems(work)
    assert blocking_now(work) == {
        (SELECT_CODE, "S001"),
        (CONFLICT_CODE, "othe"),  # where names both sides by file and family, no system id
        (SYSTEM_AXIS_CODE, "S001"),
        (SYSTEM_AXIS_CODE, "S002"),
    }
    conflict = find(questions_of(work, "grid-system-questions.json"), CONFLICT_CODE)
    status = build_status(work)
    text = "\n".join(status["gate1"]["reasons"])
    assert f"grid systems: S001 and S002 conflict ({conflict['id']})" in text and "separate=S001,S002" in text
    assert "S001 has no Tekla X/Y" in text and "S002 has no Tekla X/Y" in text
    # a conflict cannot be answered in words: it closes through the select answer only
    code, out, err = run_cli(
        capsys,
        "answer",
        str(work),
        conflict["id"],
        "--text",
        "different buildings",
        "--by",
        "me",
        "--role",
        "engineer",
    )
    assert code == 2 and out is None and "cannot be answered" in err and select["id"] in err
    assert build_status(work) == status  # nothing was written


def test_rejected_systems_stop_blocking_and_separate_buildings_close_their_conflict(world):
    _, work = world
    answer_units(work)
    run_grid_systems(work)
    answer_select(work, systems="S001")
    run_grid_systems(work)
    assert blocking_now(work) == {(SELECT_CODE, "S001"), (SYSTEM_AXIS_CODE, "S001")}
    doc = load(work / "grid-systems.json")
    assert [(c["systems"], c["closed_by"]) for c in doc["conflicts"]] == [(["S001", "S002"], "not_selected")]
    reasons = build_status(work)["gate1"]["reasons"]
    assert not [r for r in reasons if "S002" in r] and any("S001 has no Tekla X/Y" in r for r in reasons)
    answer_select(work)  # both used, declared separate buildings
    run_grid_systems(work)
    assert blocking_now(work) == {
        (SELECT_CODE, "S001"),
        (SYSTEM_AXIS_CODE, "S001"),
        (SYSTEM_AXIS_CODE, "S002"),
    }
    assert load(work / "grid-systems.json")["conflicts"][0]["closed_by"] == "separate"
    assert not [r for r in build_status(work)["gate1"]["reasons"] if " conflict " in r]


def test_a_legacy_words_answer_to_a_conflict_still_counts_as_open(world):
    """Before EVAL-1 fix 5 a conflict could be answered in words; such an answer closes nothing now."""
    _, work = world
    conflict = find(questions_of(work, "grid-system-questions.json"), CONFLICT_CODE)
    legacy = {
        "key": conflict["key"],
        "question_id": conflict["id"],
        "code": CONFLICT_CODE,
        "file": conflict["file"],
        "answer_text": "they are two different buildings",
        "values": {},
        "answered_by": "me",
        "answered_by_role": "engineer",
        "answered_on": "2026-11-01",
        "status": "active",
    }
    (work / "answers.json").write_text(
        json.dumps({"schema_version": "0.1", "project_id": PROJECT, "answers": [legacy]}), encoding="utf-8"
    )
    grid = by_label(build_status(work))["grid-system"]
    assert conflict["id"] in grid["blocking_open_ids"] and grid["questions"]["answered"] == 1


@pytest.mark.parametrize(
    ("values", "needle"),
    [
        (["separate=S001"], "at least two"),
        (["separate=S001,S009"], "does not list"),
        (["systems=S001", "separate=S001,S002"], "not in systems"),
        (["separate=S001,S001"], "distinct"),
    ],
)
def test_separate_values_are_checked(world, capsys, values, needle):
    _, work = world
    select = find(questions_of(work, "grid-system-questions.json"), SELECT_CODE)
    argv = ["answer", str(work), select["id"], "--text", "x", "--by", "me", "--role", "engineer"]
    for v in values:
        argv += ["--value", v]
    code, out, err = run_cli(capsys, *argv)
    assert code == 1 and out is None and needle in err
    assert not (work / "answers.json").exists()


def test_system_axis_answers_survive_reruns_and_keep_the_outputs_fresh(ready):
    _, work = ready
    names = ("grid-systems.json", "grid-system-questions.json", "answers.json", "question-registry.json")
    run_grid_systems(work)
    before = {n: (work / n).read_bytes() for n in names if n != "question-registry.json"}
    run_grid_systems(work)
    assert {n: (work / n).read_bytes() for n in before} == before  # answers stay active, docs identical
    axis = [a for a in load(work / "answers.json")["answers"] if a["code"] == SYSTEM_AXIS_CODE]
    assert len(axis) == 2 and all(a["status"] == "active" for a in axis)
    assert all(
        s["axis_assignment"]["status"] == "answered" for s in load(work / "grid-systems.json")["systems"]
    )
    assert by_label(build_status(work))["grid-system"]["outputs"]["status"] == "fresh"


def test_a_unit_answered_on_another_units_code_does_not_close_units_confirm_all(world):
    _, work = world
    answer_units(work)
    answers = load(work / "answers.json")
    for a in answers["answers"]:
        if a["file"] == "set.dxf":
            a["status"] = "superseded"
    legacy = {
        **answers["answers"][0],
        "key": "0123456789abcdef",
        "question_id": "Q-999",
        "code": "units_suspect",
    }
    answers["answers"].append({**legacy, "file": "set.dxf", "status": "active", "values": {"unit": "mm"}})
    (work / "answers.json").write_text(json.dumps(answers), encoding="utf-8")
    qid = find(questions_of(work, "questions.json"), "units_confirm_all", "set.dxf")["id"]
    reasons = build_status(work)["gate1"]["reasons"]
    assert any(
        r.startswith(f"units: set.dxf is not confirmed: the engineer runs: harness answer {work} {qid}")
        for r in reasons
    )


def test_an_inventory_from_an_older_intake_is_read_and_asks_for_an_intake_rerun(world, capsys):
    """inventory.json written before units.dimension_median existed: status and grid-system still work."""
    _, work = world
    answer_units(work)
    inventory = load(work / "inventory.json")
    for row in inventory["files"]:
        if row["units"] is not None:
            del row["units"]["dimension_median"]
    (work / "inventory.json").write_text(json.dumps(inventory), encoding="utf-8")
    code, status, err = run_cli(capsys, "status", str(work))
    assert code == 0 and err == ""
    units = [r for r in status["gate1"]["reasons"] if r.startswith("units:")]
    assert len(units) == 2 and all("rerun harness intake" in r for r in units)
    summary = load(work / "structure-summary.json")  # (the edit above changed the inventory's sha256)
    summary["inventory_sha256"] = status["inventory_sha256"]
    (work / "structure-summary.json").write_text(json.dumps(summary), encoding="utf-8")
    doc = build_grid_systems(work, answers=load(work / "answers.json")["answers"])  # does not raise
    assert "units_answer_contradicts_evidence" not in {q["code"] for q in doc["questions"]}


def _metres_world(tmp_path: Path) -> Path:
    """One DXF declared in metres whose dimensions read 4000 (a 4 km building in m, 4 m in mm)."""
    root = tmp_path / "input"
    root.mkdir()
    doc = new("R2018")
    doc.header["$INSUNITS"] = 6
    doc.header["$MEASUREMENT"] = 1
    for i in range(3):
        doc.modelspace().add_linear_dim(base=(0, 3 + i), p1=(0, 0), p2=(4000 + i, 0)).render()
    doc.saveas(root / "m.dxf")
    work = tmp_path / "work"
    run_intake(root, work, PROJECT)
    read_structure(work, root)
    run_callouts(work, root)
    run_marks(work, root)
    run_grid_systems(work)
    return work


def test_a_units_answer_the_drawing_contradicts_is_named_reasked_and_never_closed_silently(tmp_path):
    work = _metres_world(tmp_path)
    units_q = find(questions_of(work, "questions.json"), "units_confirm_all")
    assert units_q["count"] == 2 and "units_suspect" in units_q["refs"][1]["message"]  # folded evidence
    record_answer(work, units_q["id"], "metres, as declared", "me", {"unit": "m"}, role="engineer")
    reasons = [r for r in build_status(work)["gate1"]["reasons"] if r.startswith("units:")]
    assert len(reasons) == 1 and "the answered unit m contradicts the drawing" in reasons[0]
    assert "4001 drawing units = 4001 m in m" in reasons[0] and "rerun it" in reasons[0]
    run_grid_systems(work)  # the next producer run re-asks, quoting the answer and the evidence
    contra = find(questions_of(work, "grid-system-questions.json"), CONTRADICTION_CODE)
    found = contra["refs"][0]["found"]
    assert contra["blocking"] and contra["file"] == "m.dxf"
    assert f'{units_q["id"]} units_confirm_all unit=m: "metres, as declared"' in found and "4001 m" in found
    reasons = [r for r in build_status(work)["gate1"]["reasons"] if r.startswith("units:")]
    assert (
        len(reasons) == 1
        and f'harness answer {work} {contra["id"]} --text "..." --by "..." --role engineer --value unit=m'
        in reasons[0]
    )
    with pytest.raises(QuestionsError, match="only confirms that unit") as caught:
        record_answer(work, contra["id"], "no, millimetres", "me", {"unit": "mm"}, role="engineer")
    assert caught.value.exit_code == 1
    # confirmed on purpose: the units reason goes (grid-system must still be rerun for the answer)
    record_answer(work, contra["id"], "yes, metres: a site plan", "me", {"unit": "m"}, role="engineer")
    assert not [r for r in build_status(work)["gate1"]["reasons"] if r.startswith("units:")]
    # the engineer changes the unit instead: the contradiction question is no longer raised
    record_answer(work, units_q["id"], "millimetres after all", "me", {"unit": "mm"}, role="engineer")
    run_grid_systems(work)
    assert CONTRADICTION_CODE not in {q["code"] for q in questions_of(work, "grid-system-questions.json")}
    assert not [r for r in build_status(work)["gate1"]["reasons"] if r.startswith("units:")]
    stale = by_label(build_status(work))["grid-system"]["stale_answers"]
    assert [a["code"] for a in stale] == [CONTRADICTION_CODE]


def test_status_blocks_an_answered_unit_the_grid_spacings_contradict(ready):
    """Mirror of grid-system: no dimension evidence, but the file's median grid spacing is 0.006 m in the
    answered unit (mm). The reason stays until the same unit is confirmed on the contradiction question."""
    _, work = ready
    assert build_status(work)["gate1"]["ready_for_gate1"] is True
    doc = load(work / "grid-systems.json")
    for f in doc["files"]:
        f["grid_spacing_median"] = {"value": 6.0, "count": 5}
    (work / "grid-systems.json").write_text(json.dumps(doc), encoding="utf-8")
    reasons = [r for r in build_status(work)["gate1"]["reasons"] if r.startswith("units:")]
    assert len(reasons) == 2 and all(
        "median grid spacing 6 drawing units = 0.006 m in mm" in r for r in reasons
    )
    assert all("contradicts the drawing" in r for r in reasons)
    # a plausible spacing under the answered unit raises nothing
    for f in doc["files"]:
        f["grid_spacing_median"] = {"value": 6000.0, "count": 5}
    (work / "grid-systems.json").write_text(json.dumps(doc), encoding="utf-8")
    assert build_status(work)["gate1"]["ready_for_gate1"] is True


def test_status_cli_prints_the_document_and_always_exits_0_for_a_work_folder(world, ready, capsys):
    _, work = world
    code, out, err = run_cli(capsys, "status", str(work))
    assert code == 0 and err == "" and out == build_status(work)
    assert validate("status", out) == [] and out["gate1"]["ready_for_gate1"] is False
    _, rwork = ready
    code, out, _ = run_cli(capsys, "status", str(rwork))
    assert code == 0 and out["gate1"]["ready_for_gate1"] is True


def test_status_exit_codes(tmp_path, capsys, world):
    code, out, err = run_cli(capsys, "status", str(tmp_path / "missing"))
    assert code == 2 and out is None and "not a work folder" in err
    code, out, err = run_cli(capsys, "status", str(tmp_path))
    assert code == 2 and out is None and "inventory.json" in err and "harness intake" in err
    with pytest.raises(StatusError) as caught:
        build_status(tmp_path)
    assert caught.value.exit_code == 2
    _, work = world
    (work / "inventory.json").write_text("{", encoding="utf-8")
    code, out, err = run_cli(capsys, "status", str(work))
    assert code == 1 and out is None and "not valid JSON" in err


def test_status_writes_nothing(world):
    _, work = world
    before = {str(p.relative_to(work)): p.read_bytes() for p in work.rglob("*") if p.is_file()}
    build_status(work)
    assert {str(p.relative_to(work)): p.read_bytes() for p in work.rglob("*") if p.is_file()} == before


def test_status_example_is_valid(example):
    assert validate("status", example("status")) == []


def test_every_command_in_a_gate1_reason_names_the_work_folder_and_parses(world):
    """Review fix: `harness answer` takes the work folder first; a reason's command must run as printed
    (one question id per command)."""
    from tekla_harness.cli import build_parser

    _, work = world
    reasons = build_status(work)["gate1"]["reasons"]
    commands = [
        m for r in reasons for m in re.findall(r"harness answer [^()\n]*?--by \"\.\.\.\"(?: --role \w+)?", r)
    ]
    assert commands
    parser = build_parser()
    for c in commands:
        assert c.startswith(f"harness answer {work} Q-"), c
        args = parser.parse_args(c.split(" ", 1)[1].replace('"..."', "x").split())
        assert args.work_dir == str(work) and re.fullmatch(r"Q-\d+", args.question_id)


# --- tool wave 2 seam: closures and answer roles ---------------------------------------------------


def test_a_closed_question_leaves_the_blocking_counts(world, monkeypatch):
    from tekla_harness import lifecycle
    from tekla_harness.questions import Closure

    _, work = world
    before = build_status(work)
    step = by_label(before)["read-structure"]
    closed_id = step["blocking_open_ids"][0]
    registry = load(work / "question-registry.json")["questions"]
    (key,) = [k for k, e in registry.items() if e["id"] == closed_id]
    monkeypatch.setattr(
        lifecycle, "closures", lambda w, ledger: {key: Closure(None, "rejected_systems_only")}
    )
    after = build_status(work)
    counts = by_label(after)["read-structure"]
    assert counts["questions"]["blocking_open"] == step["questions"]["blocking_open"] - 1
    assert counts["questions"]["blocking"] == step["questions"]["blocking"] - 1
    assert closed_id not in counts["blocking_open_ids"]
    assert after["gate1"]["closed"] == [{"id": closed_id, "reason": "rejected_systems_only"}]
    assert validate("status", after) == []


def test_no_closure_and_engineer_answers_keep_gate1_unchanged(ready):
    _, work = ready
    assert build_status(work)["gate1"] == ready_gate1(work)


def test_a_simulated_answer_does_not_open_gate1(ready):
    _, work = ready
    q = find(questions_of(work, "questions.json"), "units_confirm_all", "set.dxf")
    record_answer(work, q["id"], "mm (simulated)", "agent", {"unit": "mm"}, role="simulated")
    assert load(work / "answers.json")["answers"][-1]["answered_by_role"] == "simulated"
    gate1 = build_status(work)["gate1"]
    assert gate1["ready_for_gate1"] is False
    assert gate1["non_engineer_answers"] == [
        {"question_id": q["id"], "code": "units_confirm_all", "file": "set.dxf", "role": "simulated"}
    ]
    (reason,) = [r for r in gate1["reasons"] if r.startswith("answers:")]
    assert q["id"] in reason and "simulated" in reason and "--role engineer" in reason


# answers without a role (legacy): tests/test_status_roles.py


def test_record_answer_refuses_an_unknown_role(world):
    _, work = world
    q = find(questions_of(work, "questions.json"), "units_confirm_all", "set.dxf")
    with pytest.raises(QuestionsError) as caught:
        record_answer(work, q["id"], "mm", "me", {"unit": "mm"}, role="agent")
    assert caught.value.exit_code == 2 and "engineer" in str(caught.value)
    assert not (work / "answers.json").exists()


@pytest.mark.parametrize(
    ("values", "ok"),
    [
        ({"set1": "a.dwg,b.dwg", "set2": "c.dwg"}, True),
        ({"set1": " a.dwg , b.dwg "}, True),
        ({}, False),
        ({"group1": "a.dwg"}, False),
        ({"set0": "a.dwg"}, False),
        ({"set01": "a.dwg"}, False),
        ({"set1": ""}, False),
        ({"set1": "a.dwg,"}, False),
        ({"set1": "a.dwg,a.dwg"}, False),
        ({"set1": "a.dwg", "set2": "a.dwg"}, False),
    ],
)
def test_file_set_values(values, ok):
    from tekla_harness.answers import check_values

    assert (check_values("file_set_relation", values) == []) is ok, values


def raise_file_set_question(work: Path) -> str:
    """Put a file_set_relation question (intake, project level, one ref per file) into the work folder, as
    package P2's intake will raise it."""
    registry = load(work / "question-registry.json")
    key = "f" * 16
    registry["questions"][key] = {
        "id": "Q-950", "code": "file_set_relation", "file": None, "producer": "intake",
        "status": "open", "first_seen_run": 1, "last_seen_run": 1, "blocking": True, "file_sha256": None,
    }  # fmt: skip
    registry["next_id"] = 951
    (work / "question-registry.json").write_text(json.dumps(registry), encoding="utf-8")
    doc = load(work / "questions.json")
    rows = {r["path"]: r["sha256"] for r in load(work / "inventory.json")["files"]}
    doc["questions"].append(
        {
            "id": "Q-950", "key": key, "code": "file_set_relation", "blocking": True, "file": None,
            "message": "which files form one set?", "count": 2, "truncated": False,
            "refs": [{"file": f, "where": f, "found": f"sha256 {rows[f]}"} for f in ("other.dxf", "set.dxf")],
            "answer": None,
        }
    )  # fmt: skip
    (work / "questions.json").write_text(json.dumps(doc), encoding="utf-8")
    return "Q-950"


def test_file_set_answer_must_name_every_file_of_the_question_once(world):
    _, work = world
    qid = raise_file_set_question(work)
    for values, needle in (
        ({"set1": "set.dxf"}, "other.dxf"),  # a file left out
        ({"set1": "set.dxf,other.dxf", "set2": "x.dxf"}, "x.dxf"),  # a file the question does not list
    ):
        with pytest.raises(QuestionsError) as caught:
            record_answer(work, qid, "x", "me", values, role="engineer")
        assert caught.value.exit_code == 1 and needle in str(caught.value), values
    result = record_answer(
        work, qid, "two buildings", "me", {"set1": "set.dxf", "set2": "other.dxf"}, role="engineer"
    )
    assert result["answer"]["values"] == {"set1": ["set.dxf"], "set2": ["other.dxf"]}
    assert validate("answers", load(work / "answers.json")) == []


def test_cli_answer_records_the_role(world, capsys):
    _, work = world
    q = find(questions_of(work, "questions.json"), "units_confirm_all", "set.dxf")
    code, out, _ = run_cli(
        capsys, "answer", str(work), q["id"], "--text", "mm", "--by", "me", "--value", "unit=mm",
        "--role", "engineer",
    )  # fmt: skip
    assert code == 0 and out["answer"]["answered_by_role"] == "engineer"
