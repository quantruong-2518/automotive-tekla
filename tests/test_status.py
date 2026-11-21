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
from tekla_harness.ask import ask_question
from tekla_harness.callouts import run_callouts
from tekla_harness.cli import main
from tekla_harness.findings import add_finding
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


def subject(q: dict[str, Any]) -> str:
    """What a question is about: an axis question's system id (in its message; its `where` names the
    representative families, so its key survives renumbering), else its first ref's `where`."""
    if q["code"] == SYSTEM_AXIS_CODE:
        m = re.search(r"Grid system (S\d+):", q["message"])
        assert m, q["message"]
        return m.group(1)
    return q["refs"][0]["where"]


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


def answer_everything(work: Path) -> None:
    """Every blocking question answered with the structured values it needs, grid-system rerun: gate 1 is
    ready. X/Y is answered per grid system; the two conflicting systems are declared separate buildings."""
    answer_blocking(work, ("questions.json", "structure-questions.json"))
    run_grid_systems(work)  # now reads the units answers
    answer_select(work)
    answer_blocking(work, ("grid-system-questions.json",), skip=(CONFLICT_CODE,))
    run_grid_systems(work)  # reads the select and axis answers: the conflict closes, the axes are assigned


@pytest.fixture(scope="module")
def ready_world(base_world, tmp_path_factory) -> Path:
    """The world with every blocking question answered (`answer_everything`)."""
    target = tmp_path_factory.mktemp("ready") / "w"
    shutil.copytree(base_world, target)
    answer_everything(target / "work")
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
    assert sorted(subject(q) for q in axis) == [s["system_id"] for s in doc["systems"]]
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
    assert list(labels) == [
        "intake",
        "read-structure",
        "callouts",
        "marks",
        "grid-system",
        "reader",
        "part-conflicts",
    ]
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
    for name in QUESTION_FILES:  # question documents that are gone change nothing
        (work / name).unlink()
    after = by_label(build_status(work))["read-structure"]["questions"]
    assert (
        after["answered"] == 1
        and after["blocking_open"] == labels["read-structure"]["questions"]["blocking_open"] - 1
    )


def test_status_outputs_are_fresh_stale_or_missing_with_the_command_that_fixes_them(world):
    root, work = world
    labels = by_label(build_status(work))
    assert {p["outputs"]["status"] for k, p in labels.items() if k not in ("reader", "part-conflicts")} == {
        "fresh"
    }
    for k in ("reader", "part-conflicts"):
        assert labels[k]["outputs"] == {"status": "n/a", "files": [], "reason": None, "rerun": None}
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
        assert p["outputs"]["status"] == ("n/a" if p["producer"] in ("reader", "part-conflicts") else "fresh")
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
        subject(q): q
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
        (q["code"], subject(q)[:4]) for q in questions_of(work, "grid-system-questions.json") if q["blocking"]
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
    by = answer_select(work)["answer"]["question_id"]  # a closure names an engineer answer (review M2)
    before = build_status(work)
    step = by_label(before)["read-structure"]
    closed_id = step["blocking_open_ids"][0]
    registry = load(work / "question-registry.json")["questions"]
    (key,) = [k for k, e in registry.items() if e["id"] == closed_id]
    monkeypatch.setattr(lifecycle, "closures", lambda w, ledger: {key: Closure(by, "rejected_systems_only")})
    after = build_status(work)
    counts = by_label(after)["read-structure"]
    assert counts["questions"]["blocking_open"] == step["questions"]["blocking_open"] - 1
    assert counts["questions"]["blocking"] == step["questions"]["blocking"] - 1
    assert closed_id not in counts["blocking_open_ids"]
    assert after["gate1"]["closed"] == [
        {"id": closed_id, "reason": "rejected_systems_only", "question_id": by}
    ]
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


# --- parts[] of a work folder with a parts manifest (ADR-0019, E5b-3) ---------------------------------------

MAX_IDS_FOR_TEST = 55  # more than the 50 ids a producer lists
PART_A, PART_B, PART_C = "B1-caps", "B1-piles", "B1-ties"
MANIFEST_REL = Path("parts") / "manifest.json"


def put_parts(
    work: Path,
    *,
    producer_questions: dict[str, list[str]] | None = None,
    inputs: dict[str, list[str]] | None = None,
) -> None:
    """A valid manifest of the block B1: member parts B1-caps, B1-piles, B1-ties (no inputs) and the scout."""
    extra = producer_questions or {}
    parts: list[dict[str, Any]] = [{"id": "scout", "kind": "bookkeeping", "order": 0}]
    for order, (part, family) in enumerate(((PART_A, "caps"), (PART_B, "piles"), (PART_C, "ties")), start=1):
        row: dict[str, Any] = {"id": part, "kind": "member", "block": "B1", "family": family, "order": order}
        if part in extra:
            row["producer_questions"] = extra[part]
        if part in (inputs or {}):
            row["inputs"] = (inputs or {})[part]
        parts.append(row)
    manifest = {
        "schema_version": "0.1",
        "blocks": [{"id": "B1", "grid_system_ids": [], "origin_note": "Block B1: its own grid"}],
        "parts": parts,
    }
    (work / MANIFEST_REL).parent.mkdir(parents=True, exist_ok=True)
    (work / MANIFEST_REL).write_text(json.dumps(manifest), encoding="utf-8")


def ask_reader(work: Path, code: str, part: str | None = None, *, blocking: bool = True) -> str:
    return str(
        ask_question(
            work, code=code, where="model#01 K-1", found="a value", text="Which value?", file="set.dxf",
            sheet="model#01", blocking=blocking, part=part,
        )["id"]
    )  # fmt: skip


def receipts_of(work: Path, part: str, *kinds: str, stored: dict[str, str] | None = None) -> None:
    """Receipts of `kinds` in order, each on the part's current hash (a locked one stores no inputs)."""
    from tekla_harness.part_receipts import part_hash

    current = part_hash(work, load(work / MANIFEST_REL), part)
    review = {
        "round": 1,
        "verdict": "pass",
        "file": f"parts/{part}/review/round-1/review.md",
        "sha256": "a" * 64,
    }
    receipts = [
        {
            "n": n, "kind": kind, "part_hash": current, "at": "2026-01-01T00:00:00Z", "tool_version": "0.1.0",
            "review": review if kind == "reviewed" else None,
            "reason": "the sizes changed" if kind == "reopened" else None,
            "inputs": (stored or {}) if kind == "locked" else None,
        }
        for n, kind in enumerate(kinds, start=1)
    ]  # fmt: skip
    path = work / "parts" / part / "receipts.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"schema_version": "0.1", "part": part, "receipts": receipts}
    assert validate("part-receipts", doc) == []
    path.write_text(json.dumps(doc), encoding="utf-8")


def lock_all(work: Path) -> None:
    for part in (PART_A, PART_B, PART_C):
        receipts_of(work, part, "checked", "reviewed", "locked")


def part_rows(work: Path) -> dict[str, dict[str, Any]]:
    doc = build_status(work)
    assert validate("status", doc) == []
    return {p["id"]: p for p in doc["parts"]}


def answer_by_engineer(work: Path, question_id: str) -> None:
    record_answer(work, question_id, "test answer", "tester", {}, role="engineer")


def test_ready_needs_locked_and_no_open_blocking_of_the_part(ready):
    _, work = ready
    put_parts(work)
    qa = ask_reader(work, "reader_size_unclear", PART_A)
    ask_reader(work, "reader_note_unclear", PART_B, blocking=False)  # not blocking: never listed
    receipts_of(work, PART_A, "checked", "reviewed", "locked")
    receipts_of(work, PART_B, "checked", "reviewed", "locked")
    receipts_of(work, PART_C, "checked", "reviewed")  # reviewed is not locked
    rows = part_rows(work)
    assert list(rows) == ["scout", PART_A, PART_B, PART_C]  # manifest order
    assert {k: rows[PART_A][k] for k in ("id", "kind", "status", "blocking_open_ids", "ready")} == {
        "id": PART_A, "kind": "member", "status": "locked", "blocking_open_ids": [qa], "ready": False,
    }  # fmt: skip
    assert rows[PART_B]["status"] == "locked" and rows[PART_B]["blocking_open_ids"] == []
    assert rows[PART_B]["ready"] is True and rows[PART_B]["blocked_by_project"] is False
    assert rows[PART_C]["status"] == "reviewed" and rows[PART_C]["ready"] is False
    assert rows["scout"]["status"] == "reading" and rows["scout"]["ready"] is False
    assert all(len(r["hash"]) == 64 and r["stale_inputs"] == [] for r in rows.values())
    answer_by_engineer(work, qa)  # an answer moves readiness, never the hash
    rows = part_rows(work)
    assert rows[PART_A]["status"] == "locked" and rows[PART_A]["ready"] is True
    assert rows[PART_A]["blocking_open_ids"] == []


def test_blocking_open_ids_are_the_full_list_and_include_producer_questions(world):
    _, work = world
    put_parts(work)
    ids = [ask_reader(work, f"reader_size_unclear_{n}", PART_A) for n in range(MAX_IDS_FOR_TEST)]
    assert len(by_label(build_status(work))["reader"]["blocking_open_ids"]) == 50  # the producer list is cut
    assert part_rows(work)[PART_A]["blocking_open_ids"] == ids  # the part's list is not
    intake = by_label(build_status(work))["intake"]["blocking_open_ids"][0]
    put_parts(work, producer_questions={PART_B: [intake, "Q-999"]})  # Q-999: not in the registry
    rows = part_rows(work)
    assert rows[PART_B]["blocking_open_ids"] == [intake]
    assert rows[PART_A]["blocking_open_ids"] == ids and rows[PART_C]["blocking_open_ids"] == []
    answered = find(questions_of(work, "questions.json"), "units_confirm_all", "set.dxf")["id"]
    record_answer(work, answered, "mm", "tester", {"unit": "mm"}, role="engineer")
    put_parts(work, producer_questions={PART_B: [answered]})
    assert part_rows(work)[PART_B]["blocking_open_ids"] == []  # answered: no longer open


def test_project_reasons_block_every_part_reader_line_not(ready, world):
    _, rwork = ready
    put_parts(rwork)
    qa = ask_reader(rwork, "reader_size_unclear", PART_A)
    lock_all(rwork)
    doc = build_status(rwork)
    assert doc["gate1"]["ready_for_gate1"] is False  # the reader line stops gate 1 ...
    assert [r for r in doc["gate1"]["reasons"] if r.startswith("reader:")]
    rows = {p["id"]: p for p in doc["parts"]}
    assert rows[PART_B]["blocked_by_project"] is False and rows[PART_B]["ready"] is True  # ... not part B
    assert rows[PART_A]["blocking_open_ids"] == [qa] and rows[PART_A]["ready"] is False
    _, work = world  # gate 1 has project reasons of its own (units, levels, intake ...)
    put_parts(work)
    lock_all(work)
    doc = build_status(work)
    assert [r for r in doc["gate1"]["reasons"] if not r.startswith("reader:")]
    rows = {p["id"]: p for p in doc["parts"]}
    assert all(r["blocked_by_project"] is True for r in rows.values())
    assert all(rows[p]["status"] == "locked" and rows[p]["ready"] is False for p in (PART_A, PART_B, PART_C))


def test_untagged_blocking_reader_question_blocks_every_part(ready):
    _, work = ready
    untagged = ask_reader(work, "reader_size_unclear")  # asked before the manifest: no part needed
    put_parts(work)
    lock_all(work)
    rows = part_rows(work)
    assert all(r["blocked_by_project"] is True and r["ready"] is False for r in rows.values())
    assert all(rows[p]["blocking_open_ids"] == [] for p in (PART_A, PART_B, PART_C))  # held by no part
    assert [r for r in build_status(work)["gate1"]["reasons"] if r.startswith("reader:")]
    answer_by_engineer(work, untagged)
    rows = part_rows(work)
    assert all(rows[p]["blocked_by_project"] is False and rows[p]["ready"] is True for p in (PART_A, PART_C))


def test_no_manifest_no_parts_invalid_sets_parts_error(world, ready, monkeypatch, capsys):
    _, work = world
    before = build_status(work)
    assert "parts" not in before and "parts_error" not in before  # no manifest: part mode is off
    for text in ("{", json.dumps({"schema_version": "0.1", "blocks": [], "parts": "x"})):
        (work / MANIFEST_REL).parent.mkdir(parents=True, exist_ok=True)
        (work / MANIFEST_REL).write_text(text, encoding="utf-8")
        doc = build_status(work)
        assert doc["parts"] == [] and "manifest.json" in doc["parts_error"]
        assert "parts_project_reasons" not in doc
        assert doc["gate1"] == before["gate1"] and validate("status", doc) == []
    _, rwork = ready  # records the hash needs, invalid: the same answer, the file named
    put_parts(rwork)
    (rwork / "reader-findings.json").write_text("{", encoding="utf-8")
    doc = build_status(rwork)
    assert doc["parts"] == [] and "reader-findings.json" in doc["parts_error"]
    assert doc["gate1"] == ready_gate1(rwork)
    (work / MANIFEST_REL).write_text("{", encoding="utf-8")  # a manifest the system refuses: exit 3
    from tekla_harness.parts import ManifestAccessError

    def refuse(_work: Path) -> bool:
        raise ManifestAccessError("cannot check parts/manifest.json (denied)")

    monkeypatch.setattr("tekla_harness.status.manifest_present", refuse)
    with pytest.raises(StatusError) as caught:
        build_status(work)
    assert caught.value.exit_code == 3 and "denied" in str(caught.value)
    code, out, err = run_cli(capsys, "status", str(work))
    assert code == 3 and out is None and "denied" in err


def test_parts_project_reasons_say_why_every_part_is_blocked(ready, world):
    """D4: the top-level `parts_project_reasons` lists what `blocked_by_project` reduces to a boolean."""
    _, rwork = ready
    untagged = ask_reader(rwork, "reader_size_unclear")  # asked before the manifest: no part needed
    put_parts(rwork)
    ask_reader(rwork, "reader_other_unclear", PART_A)  # tagged: the reader line is no project reason
    lock_all(rwork)
    doc = build_status(rwork)
    (line,) = doc["parts_project_reasons"]
    assert line.startswith("reader questions without a part:") and untagged in line
    assert all(p["blocked_by_project"] is True for p in doc["parts"]) and validate("status", doc) == []
    answer_by_engineer(rwork, untagged)
    doc = build_status(rwork)
    assert doc["parts_project_reasons"] == [] and doc["project_blocking_ids"] == []
    _, work = world  # gate 1 has project reasons of its own: the same lines, in order, the reader line apart
    ask_reader(work, "reader_size_unclear")
    put_parts(work)
    doc = build_status(work)
    gate1 = [r for r in doc["gate1"]["reasons"] if not r.startswith("reader:")]
    assert gate1 and doc["parts_project_reasons"][:-1] == gate1
    assert doc["parts_project_reasons"][-1].startswith("reader questions without a part:")


def test_parts_project_reasons_are_absent_without_parts_or_with_parts_error(world):
    _, work = world
    assert "parts_project_reasons" not in build_status(work)  # no manifest: part mode is off
    (work / MANIFEST_REL).parent.mkdir(parents=True, exist_ok=True)
    (work / MANIFEST_REL).write_text("{", encoding="utf-8")
    doc = build_status(work)
    assert doc["parts"] == [] and doc["parts_error"]
    assert "parts_project_reasons" not in doc and "project_blocking_ids" not in doc


@pytest.mark.parametrize("name", ["receipts.json", "reader-questions.json"])
def test_a_record_the_system_refuses_is_exit_3_not_a_parts_error(ready, monkeypatch, capsys, name):
    """m9: only an unusable record is a `parts_error`; a file the operating system refuses is exit 3."""
    _, work = ready
    put_parts(work)
    ask_reader(work, "reader_size_unclear", PART_A)
    receipts_of(work, PART_A, "checked")
    real = Path.read_bytes

    def refuse(self: Path) -> bytes:
        if self.name == name:
            raise PermissionError("denied")
        return real(self)

    monkeypatch.setattr(Path, "read_bytes", refuse)
    with pytest.raises(StatusError) as caught:
        build_status(work)
    assert caught.value.exit_code == 3 and name in str(caught.value)
    code, out, err = run_cli(capsys, "status", str(work))
    assert code == 3 and out is None and name in err


def test_a_missing_inventory_under_the_part_hash_is_a_parts_error(ready, tmp_path, monkeypatch, capsys):
    """X1: the part hash raises exit 2 when an active finding needs inventory.json and it is gone; the status
    still prints its JSON, `parts: []` and `parts_error` naming the cause."""
    from tekla_harness import part_receipts

    real = part_receipts.load_inventory

    def vanished(work: Path, *_: Any) -> Any:  # inventory.json goes after the status has read it
        (work / "inventory.json").unlink()
        return real(work)  # the real exit 2: "<work> has no inventory.json: run `harness intake` first"

    _, work = ready
    put_parts(work)
    before = build_status(work)["gate1"]
    copy = tmp_path / "copy"
    shutil.copytree(work, copy)
    monkeypatch.setattr(part_receipts, "_hash", vanished)
    doc = build_status(work)
    assert doc["parts"] == [] and "inventory.json" in doc["parts_error"]
    assert "parts_project_reasons" not in doc and doc["gate1"] == before and validate("status", doc) == []
    code, out, _ = run_cli(capsys, "status", str(copy))
    assert code == 0 and out["parts"] == [] and "inventory.json" in out["parts_error"]


def test_status_example_shows_parts(example):
    doc = example("status")
    assert doc["parts"] and validate("status", doc) == []
    broken = {**doc, "parts": [{**doc["parts"][0], "status": "done"}]}
    assert validate("status", broken)
    assert validate("status", {**doc, "parts": [{k: v for k, v in doc["parts"][0].items() if k != "ready"}]})


def test_stale_inputs_name_the_inputs_that_no_longer_hold(ready):
    from tekla_harness.part_receipts import part_hash

    _, work = ready
    put_parts(work, inputs={PART_A: [PART_B]})
    receipts_of(work, PART_B, "checked", "reviewed", "locked")
    receipts_of(work, PART_A, "checked", "reviewed", "locked", stored={PART_B: "0" * 64})  # another hash
    rows = part_rows(work)
    assert rows[PART_A]["status"] == "stale_input" and rows[PART_A]["stale_inputs"] == [PART_B]
    assert rows[PART_A]["ready"] is False and rows[PART_B]["stale_inputs"] == []
    stored = {PART_B: part_hash(work, load(work / MANIFEST_REL), PART_B)}
    receipts_of(work, PART_A, "checked", "reviewed", "locked", stored=stored)
    assert part_rows(work)[PART_A]["status"] == "locked"
    assert part_rows(work)[PART_A]["stale_inputs"] == []
    receipts_of(work, PART_B, "checked", "reviewed", "locked", "reopened")  # the input is reopened
    rows = part_rows(work)
    assert rows[PART_A]["status"] == "stale_input" and rows[PART_A]["stale_inputs"] == [PART_B]


# --- E5b-fix-3: a drawing revision or a question change reopens a part, a project reason has its line -------

CAP_SIZE = "1500x2400"


def edit_text_of_set(
    root: Path, work: Path, *, add: str | None = None, replace: tuple[str, str] | None = None
):
    """Add a text to `set.dxf` (sheet model#01) or change one, take the drawing in again and answer again as
    the ready world does."""
    from ezdxf.filemanagement import readfile

    doc = readfile(str(root / "set.dxf"))
    msp = doc.modelspace()
    if add:
        msp.add_text(add, height=350, dxfattribs={"insert": (62000, 56500)})
    if replace:
        for text in msp.query("TEXT"):
            if text.dxf.text == replace[0]:
                text.dxf.text = replace[1]
    doc.saveas(root / "set.dxf")
    rerun_all(root, work)
    answer_everything(work)


def entry_of(work: Path, text: str) -> str:
    index = load(work / "text" / "set.dxf.json")
    return next(e["id"] for e in index["entries"] if e["display_text"] == text)


def caps_reads_set(work: Path, values: list[dict[str, Any]]) -> None:
    """The manifest of `put_parts` with B1-caps reading sheet model#01 of set.dxf, and its `values.json`."""
    put_parts(work)
    doc = load(work / MANIFEST_REL)
    next(p for p in doc["parts"] if p["id"] == PART_A)["sheets"] = [
        {"file": "set.dxf", "sheet": "model#01", "role": "plan"}
    ]
    (work / MANIFEST_REL).write_text(json.dumps(doc), encoding="utf-8")
    path = work / "parts" / PART_A / "values.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": "0.1", "part": PART_A, "rows": values}), encoding="utf-8")


def lock_through_the_command(capsys, work: Path, part: str) -> None:
    code, out, err = run_cli(capsys, "part", "receipt", str(work), "--part", part, "--kind", "checked")
    assert code == 0, (out, err)
    review = work / "parts" / part / "review" / "round-1" / "review.md"
    review.parent.mkdir(parents=True, exist_ok=True)
    review.write_text("Round review: nothing found.\n", encoding="utf-8")
    flags = ["--review", str(review), "--round", "1", "--verdict", "pass"]
    assert run_cli(capsys, "part", "receipt", str(work), "--part", part, "--kind", "reviewed", *flags)[0] == 0
    code, out, err = run_cli(capsys, "part", "receipt", str(work), "--part", part, "--kind", "locked")
    assert code == 0, (out, err)


def test_a_revised_drawing_reopens_a_locked_part_whose_row_cites_an_entry_only(ready, capsys):
    """C1, probe B end to end: no finding on the drawing, one row on the entry of a text; the text changes."""
    root, work = ready
    edit_text_of_set(root, work, add=CAP_SIZE)
    row = {
        "row": "R001", "subject": "caps", "field": "material", "value": CAP_SIZE, "file": "set.dxf",
        "sheet": "model#01", "state": "seen", "cites": {"entries": [entry_of(work, CAP_SIZE)]},
    }  # fmt: skip
    caps_reads_set(work, [row])
    code, out, err = run_cli(capsys, "part", "check", str(work), "--part", PART_A)
    assert code == 0 and out["problems"] == [], (out["problems"], err)
    lock_through_the_command(capsys, work, PART_A)
    before = part_rows(work)[PART_A]
    assert before["status"] == "locked" and before["ready"] is True
    edit_text_of_set(root, work, replace=(CAP_SIZE, "1600x2400"))
    after = part_rows(work)[PART_A]
    assert after["status"] == "reopened" and after["ready"] is False and after["hash"] != before["hash"]
    code, out, _ = run_cli(capsys, "part", "check", str(work), "--part", PART_A)
    assert code == 1 and {p["code"] for p in out["problems"]} >= {"number_unbacked"}  # what the lock hid


def test_a_question_that_stops_blocking_reopens_a_part_that_cites_it_through_a_finding(world, capsys):
    """M1, probe D end to end: a single-source value held by the blocking conflict question through its
    finding; the conflict closes and the registry flips `blocking`."""
    root, work = world
    edit_text_of_set(root, work, add=CAP_SIZE)  # answers everything, the conflict closed
    run_cli(capsys, "status", str(work))
    conflict = find(questions_of(work, "grid-system-questions.json"), CONFLICT_CODE)["id"]
    registry = load(work / "question-registry.json")
    entry = next(e for e in registry["questions"].values() if e["id"] == conflict)
    entry.update(status="open", blocking=True)  # as it stands before the second half of the answers
    (work / "question-registry.json").write_text(json.dumps(registry), encoding="utf-8")
    finding = add_finding(
        work, kind="note_item", file="set.dxf", entries=[entry_of(work, CAP_SIZE)], value=CAP_SIZE,
        sheet="model#01", fields=["topic=other"], questions=[conflict], part=PART_A,
        note="block: cap size as printed",
    )["id"]  # fmt: skip
    row = {
        "row": "R001", "subject": "caps", "field": "size", "value": CAP_SIZE, "file": "set.dxf",
        "sheet": "model#01", "state": "seen", "cites": {"findings": [finding]},
    }  # fmt: skip
    caps_reads_set(work, [row])
    code, out, err = run_cli(capsys, "part", "check", str(work), "--part", PART_A)
    assert code == 0 and out["problems"] == [], (out["problems"], err)
    lock_through_the_command(capsys, work, PART_A)
    assert part_rows(work)[PART_A]["status"] == "locked"
    registry = load(work / "question-registry.json")
    next(e for e in registry["questions"].values() if e["id"] == conflict)["blocking"] = False
    (work / "question-registry.json").write_text(json.dumps(registry), encoding="utf-8")
    after = part_rows(work)[PART_A]
    assert after["status"] == "reopened" and after["ready"] is False
    code, out, _ = run_cli(capsys, "part", "check", str(work), "--part", PART_A)
    assert code == 1 and "listed_question_not_blocking" in {p["code"] for p in out["problems"]}


def open_blocking_entry(work: Path, producer: str) -> str:
    """A new open blocking question of `producer` in the registry (nothing else holds it)."""
    registry = load(work / "question-registry.json")
    qid = f"Q-{registry['next_id']:03d}"
    registry["next_id"] += 1
    registry["questions"]["c" * 15 + str(registry["next_id"] % 10)] = {
        "id": qid, "code": f"{producer.replace('-', '_')}_made_up", "file": "set.dxf",
        "producer": producer, "status": "open", "first_seen_run": 1, "last_seen_run": 1, "blocking": True,
    }  # fmt: skip
    (work / "question-registry.json").write_text(json.dumps(registry), encoding="utf-8")
    return qid


def test_a_blocking_question_no_part_holds_has_a_project_reason_line(ready):
    """m2: `blocked_by_project` was true with `parts_project_reasons` empty."""
    _, work = ready
    put_parts(work)
    lock_all(work)
    assert build_status(work)["parts_project_reasons"] == []
    callout, marks = open_blocking_entry(work, "callouts"), open_blocking_entry(work, "marks")
    conflict = open_blocking_entry(work, "part-conflicts")
    doc = build_status(work)
    assert {callout, marks, conflict} <= set(doc["project_blocking_ids"])
    assert all(p["blocked_by_project"] is True for p in doc["parts"]) and validate("status", doc) == []
    assert doc["parts_project_reasons"] == [
        f"callouts questions no part lists: 1 blocking question(s) open ({callout}); "
        "list each in the producer_questions of the part it belongs to",
        f"marks questions no part lists: 1 blocking question(s) open ({marks}); "
        "list each in the producer_questions of the part it belongs to",
        f"part-conflicts questions without a part: 1 blocking question(s) open ({conflict}); "
        "rerun harness part conflicts",
    ]
    put_parts(work, producer_questions={PART_A: [callout, marks]})  # listed: they block that part only
    doc = build_status(work)
    assert doc["parts_project_reasons"] == [
        f"part-conflicts questions without a part: 1 blocking question(s) open ({conflict}); "
        "rerun harness part conflicts"
    ]
    assert callout not in doc["project_blocking_ids"] and conflict in doc["project_blocking_ids"]


def test_a_finding_judgement_the_system_refuses_is_exit_3_in_the_status(ready, monkeypatch, capsys):
    """m4 (the part hash's side): the status does not turn it into a stale finding or a `parts_error`."""
    from tekla_harness.findings import FindingError

    _, work = ready
    put_parts(work)
    ask_reader(work, "reader_size_unclear", PART_A)
    first = load(work / "text" / "set.dxf.json")["entries"][0]
    add_finding(
        work, kind="note_item", file="set.dxf", entries=[first["id"]], value=first["display_text"],
        sheet="model#01", fields=["topic=other"], part=PART_A, note="block: a text as printed",
    )  # fmt: skip
    receipts_of(work, PART_A, "checked")

    def refuse(*_: Any, **__: Any) -> Any:
        raise FindingError(3, "cannot read geometry/g1.json: denied")

    monkeypatch.setattr("tekla_harness.part_receipts._stale_reasons", refuse)
    code, out, err = run_cli(capsys, "status", str(work))
    assert code == 3 and out is None and "denied" in err


# --- `harness status --verify`: ready is checked by the part check, not the hash alone (E5b-4) -----------

CLEAN = {"schema_version": "0.1", "rows": []}  # a values.json every check accepts: no row to prove
BAD_ROW = {
    "row": "R001",
    "mark": "K-1",
    "field": "size",
    "value": "1",
    "file": "set.dxf",
    "sheet": "model#01",
    "state": "seen",
    "cites": {"findings": ["F-009"]},
}  # fmt: skip: cites a finding that does not exist


def put_values(work: Path, part: str, rows: list[dict[str, Any]] | str) -> None:
    path = work / "parts" / part / "values.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = rows if isinstance(rows, str) else json.dumps({**CLEAN, "part": part, "rows": rows})
    path.write_text(text, encoding="utf-8")


def verified_rows(work: Path) -> dict[str, dict[str, Any]]:
    doc = build_status(work, verify=True)
    assert validate("status", doc) == [] and doc["verified"] is True
    return {p["id"]: p for p in doc["parts"]}


def locked_world(work: Path, bad: str | list[dict[str, Any]] | None = None) -> None:
    """Manifest, values.json for the three parts (PART_A: `bad`; the others clean), then every part locked on
    that hash: the part check is the only thing that can tell PART_A's file from the others'."""
    put_parts(work)
    put_values(work, PART_A, bad if isinstance(bad, str) else bad or [])
    put_values(work, PART_B, [])
    put_values(work, PART_C, [])
    for part in (PART_A, PART_B, PART_C):
        receipts_of(work, part, "checked", "reviewed", "locked")


def test_verify_fails_a_locked_ready_part_whose_values_do_not_pass_the_check(ready):
    _, work = ready
    locked_world(work, [BAD_ROW])
    plain = part_rows(work)  # the hash alone: locked, nothing open: ready
    assert plain[PART_A]["ready"] is True and "check_failed" not in plain[PART_A]
    assert "verified" not in build_status(work)
    rows = verified_rows(work)
    assert rows[PART_A]["check_failed"] is True and rows[PART_A]["ready"] is False
    assert rows[PART_A]["status"] == "locked" and rows[PART_A]["hash"] == plain[PART_A]["hash"]
    assert rows[PART_B]["check_failed"] is False and rows[PART_B]["ready"] is True
    assert rows[PART_C]["check_failed"] is False and rows[PART_C]["ready"] is True


def test_verify_checks_every_locked_part_ready_or_not(ready, monkeypatch):
    from tekla_harness import status
    from tekla_harness.part_check import check_part

    _, work = ready
    put_parts(work)
    for part in (PART_A, PART_B, PART_C):
        put_values(work, part, [])
    qa = ask_reader(work, "reader_size_unclear", PART_A)  # an open blocking question: PART_A is not ready
    receipts_of(work, PART_A, "checked", "reviewed", "locked")
    receipts_of(work, PART_B, "checked", "reviewed")  # reviewed is not locked; PART_C has no receipt
    seen: list[str] = []

    def spy(work_dir: Path | str, part: str) -> dict[str, Any]:
        seen.append(part)
        return check_part(work_dir, part)

    monkeypatch.setattr(status, "check_part", spy)
    rows = verified_rows(work)
    assert seen == [PART_A] and rows[PART_A]["blocking_open_ids"] == [qa]  # locked, not ready: still checked
    assert rows[PART_A]["check_failed"] is False and rows[PART_A]["ready"] is False  # blocked, not unlocked
    assert all("check_failed" not in rows[p] for p in (PART_B, PART_C, "scout"))
    assert all(r["ready"] is False for r in rows.values())
    seen.clear()
    answer_by_engineer(work, qa)
    receipts_of(work, PART_B, "checked", "reviewed", "locked")
    rows = verified_rows(work)
    assert sorted(seen) == [PART_A, PART_B]  # exactly the locked ones, once each
    assert rows[PART_A]["check_failed"] is False and rows[PART_B]["check_failed"] is False
    assert rows[PART_A]["ready"] is True and rows[PART_B]["ready"] is True
    assert "check_failed" not in rows[PART_C] and "check_failed" not in rows["scout"]


def lock_chain(work: Path, *parts: str) -> None:
    """Lock `parts` (dependencies first), each on its current hash, storing the hash of every listed input."""
    from tekla_harness.part_receipts import part_hash

    manifest = load(work / MANIFEST_REL)
    for part in parts:
        listed = next(p for p in manifest["parts"] if p["id"] == part).get("inputs", [])
        stored = {i: part_hash(work, manifest, i) for i in listed}
        receipts_of(work, part, "checked", "reviewed", "locked", stored=stored)


def test_verify_makes_a_part_built_on_a_failing_input_not_ready(ready):
    """P6: the input is ready and fails its check; the part built on it must not stay ready."""
    _, work = ready
    put_parts(work, inputs={PART_A: [PART_B]})
    put_values(work, PART_A, [])
    put_values(work, PART_B, [BAD_ROW])
    put_values(work, PART_C, [])
    lock_chain(work, PART_B, PART_A, PART_C)
    plain = part_rows(work)
    assert plain[PART_A]["ready"] is True and "input_check_failed" not in plain[PART_A]  # the hash alone
    rows = verified_rows(work)
    assert rows[PART_B]["check_failed"] is True and rows[PART_B]["ready"] is False
    assert rows[PART_A]["check_failed"] is False and rows[PART_A]["ready"] is False
    assert rows[PART_A]["input_check_failed"] == [PART_B] and rows[PART_A]["status"] == "locked"
    assert "input_check_failed" not in rows[PART_B] and "input_check_failed" not in rows[PART_C]
    assert rows[PART_C]["ready"] is True  # no input: untouched


def test_verify_follows_the_inputs_of_inputs(ready):
    _, work = ready
    put_parts(work, inputs={PART_A: [PART_B], PART_C: [PART_A]})  # C -> A -> B
    put_values(work, PART_A, [])
    put_values(work, PART_B, [BAD_ROW])
    put_values(work, PART_C, [])
    lock_chain(work, PART_B, PART_A, PART_C)
    rows = verified_rows(work)
    assert rows[PART_A]["input_check_failed"] == [PART_B]
    assert rows[PART_C]["input_check_failed"] == [PART_B]  # through A, which itself passes
    assert rows[PART_C]["ready"] is False and rows[PART_C]["check_failed"] is False


def test_verify_lists_every_failing_input_sorted(ready):
    _, work = ready
    put_parts(work, inputs={PART_C: [PART_B, PART_A]})
    put_values(work, PART_A, [BAD_ROW])
    put_values(work, PART_B, [BAD_ROW])
    put_values(work, PART_C, [])
    lock_chain(work, PART_B, PART_A, PART_C)
    assert verified_rows(work)[PART_C]["input_check_failed"] == [PART_A, PART_B]


def test_verify_checks_a_locked_input_that_is_not_ready(ready):
    """P5: the input has an open blocking question, so it is not ready, but its lock is still void."""
    _, work = ready
    put_parts(work, inputs={PART_A: [PART_B]})
    put_values(work, PART_A, [])
    put_values(work, PART_B, [BAD_ROW])
    qb = ask_reader(work, "reader_size_unclear", PART_B)
    lock_chain(work, PART_B, PART_A)
    rows = verified_rows(work)
    assert rows[PART_B]["blocking_open_ids"] == [qb] and rows[PART_B]["ready"] is False
    assert rows[PART_B]["check_failed"] is True  # checked although it is not ready
    assert rows[PART_A]["input_check_failed"] == [PART_B] and rows[PART_A]["ready"] is False


def test_verify_names_the_codes_of_a_failing_check(ready):
    from tekla_harness.part_check import check_part

    _, work = ready
    put_parts(work)
    put_values(work, PART_A, [BAD_ROW, {**BAD_ROW, "row": "R002"}])  # one code, twice
    put_values(work, PART_B, [])
    put_values(work, PART_C, [])
    lock_chain(work, PART_A, PART_B, PART_C)
    codes = sorted({p["code"] for p in check_part(work, PART_A)["problems"]})
    assert codes
    rows = verified_rows(work)
    assert rows[PART_A]["check_codes"] == codes
    assert "check_codes" not in rows[PART_B] and "check_error" not in rows[PART_A]


def test_verify_counts_a_check_whose_hash_is_not_the_rows_as_failed(ready, monkeypatch):
    """P2 (m2): the file changes between the hash and the check, and the changed file passes."""
    from tekla_harness import status
    from tekla_harness.part_check import check_part

    _, work = ready
    put_parts(work)
    for part in (PART_A, PART_B, PART_C):
        put_values(work, part, [])
    lock_chain(work, PART_A, PART_B, PART_C)

    def racing(work_dir: Path | str, part: str) -> dict[str, Any]:
        if part == PART_A:  # another file that passes too, written after the status hashed the part
            text = json.dumps({**CLEAN, "part": PART_A, "rows": []}, indent=2)
            put_values(work, PART_A, text)
        return check_part(work_dir, part)

    monkeypatch.setattr(status, "check_part", racing)
    rows = verified_rows(work)
    assert rows[PART_A]["check_failed"] is True and rows[PART_A]["ready"] is False
    assert rows[PART_A]["check_codes"] == ["changed_during_check"]
    assert rows[PART_B]["check_failed"] is False and rows[PART_B]["ready"] is True


def test_verify_merges_the_changed_code_with_the_codes_of_the_check(ready, monkeypatch):
    from tekla_harness import status
    from tekla_harness.part_check import check_part

    _, work = ready
    put_parts(work)
    for part in (PART_A, PART_B, PART_C):
        put_values(work, part, [])
    put_values(work, PART_A, [BAD_ROW])
    lock_chain(work, PART_A, PART_B, PART_C)
    own = sorted({p["code"] for p in check_part(work, PART_A)["problems"]})

    def racing(work_dir: Path | str, part: str) -> dict[str, Any]:
        doc = check_part(work_dir, part)
        return {**doc, "hash": "0" * 64} if part == PART_A else doc

    monkeypatch.setattr(status, "check_part", racing)
    assert verified_rows(work)[PART_A]["check_codes"] == sorted({*own, "changed_during_check"})


def test_verify_reports_a_check_that_cannot_run_and_keeps_the_other_rows(ready, monkeypatch):
    from tekla_harness import status
    from tekla_harness.part_check import check_part
    from tekla_harness.parts import ManifestAccessError

    _, work = ready
    locked_world(work, [])
    before = verified_rows(work)

    def refusing(work_dir: Path | str, part: str) -> dict[str, Any]:
        if part == PART_A:
            raise ManifestAccessError("cannot read parts/B1-caps/values.json (denied)")
        return check_part(work_dir, part)

    monkeypatch.setattr(status, "check_part", refusing)
    doc = build_status(work, verify=True)
    assert validate("status", doc) == [] and doc["verified"] is False  # a check did not run
    rows = {p["id"]: p for p in doc["parts"]}
    assert rows[PART_A]["check_error"] == "3: cannot read parts/B1-caps/values.json (denied)"
    assert rows[PART_A]["check_failed"] is True and rows[PART_A]["ready"] is False
    assert "check_codes" not in rows[PART_A]
    for part in (PART_B, PART_C, "scout"):
        assert rows[part] == before[part]


def test_verify_reports_a_reader_error_with_its_exit_code(ready, monkeypatch):
    from tekla_harness import status
    from tekla_harness.sheet_text import ReaderError

    _, work = ready
    locked_world(work, [])

    def broken(*_: Any, **__: Any) -> Any:
        raise ReaderError(1, "values.json is not valid")

    monkeypatch.setattr(status, "check_part", broken)
    doc = build_status(work, verify=True)
    rows = {p["id"]: p for p in doc["parts"]}
    assert rows[PART_A]["check_error"] == "1: values.json is not valid" and doc["verified"] is False
    assert all(
        rows[p]["check_failed"] is True and rows[p]["ready"] is False for p in (PART_A, PART_B, PART_C)
    )


def test_verify_is_false_when_the_manifest_is_unusable(ready):
    _, work = ready
    locked_world(work, [])
    (work / MANIFEST_REL).write_text("{", encoding="utf-8")  # no part can be listed, so none is checked
    doc = build_status(work, verify=True)
    assert doc["parts"] == [] and doc["parts_error"] and doc["verified"] is False
    assert validate("status", doc) == []


def test_verify_lets_any_other_exception_end_the_command(ready, monkeypatch):
    from tekla_harness import status

    _, work = ready
    locked_world(work, [])

    def bug(*_: Any, **__: Any) -> Any:
        raise KeyError("blocks")

    monkeypatch.setattr(status, "check_part", bug)
    with pytest.raises(KeyError):
        build_status(work, verify=True)


def test_verify_counts_a_check_that_cannot_run_as_failed(ready):
    _, work = ready
    locked_world(work, "{")  # values.json is not JSON
    rows = verified_rows(work)
    assert rows[PART_A]["check_failed"] is True and rows[PART_A]["ready"] is False
    assert rows[PART_A]["check_codes"] == ["values_invalid"]
    (work / "parts" / PART_A / "values.json").unlink()  # missing: a stop problem of the check
    receipts_of(work, PART_A, "checked", "reviewed", "locked")
    assert check_stops(work, PART_A)
    rows = verified_rows(work)
    assert rows[PART_A]["check_failed"] is True and rows[PART_A]["ready"] is False
    assert rows[PART_B]["check_failed"] is False


def test_verify_follows_an_input_whose_file_is_outside_the_hash(tmp_path, monkeypatch):
    """P7: marks.json is no part of the hash, so a rerun can void a lock while the hash stays."""
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from _part_fixtures import INPUT_PART, MANIFEST, PART, REL, build_part_work, entry_ids, row, write_values
    from tekla_harness.part_receipts import part_hash, write_part_receipt

    work = build_part_work(tmp_path)
    piles = row(
        "R001", mark="P-1", field="count_plan", value="26", sheet="model#02",
        cites={"questions": ["Q-005"], "entries": [entry_ids(work)["26"]]},
    )  # fmt: skip
    write_values(work, [piles], INPUT_PART)
    write_values(work, [row("R001")])
    doc = load(work / MANIFEST)
    next(p for p in doc["parts"] if p["id"] == INPUT_PART)["marks_regex"] = "P-[0-9]+"
    (work / MANIFEST).write_text(json.dumps(doc), encoding="utf-8")
    marks = load(Path(__file__).parents[1] / "schemas" / "examples" / "marks.example.json")
    first = {**marks["plan_marks"][0], "file": REL, "sheet": "model#02", "mark": "P-1", "key": "p-1",
             "display_text": "P-1"}  # fmt: skip
    marks["plan_marks"] = [first]
    (work / "marks.json").write_text(json.dumps(marks), encoding="utf-8")
    from tekla_harness import status as status_module

    real = status_module._part_rows

    def keep_q005(w: Path, open_by_label: dict[str, list[str]], project_reasons: list[str]) -> Any:
        kept = {label: [q for q in ids if q == "Q-005"] for label, ids in open_by_label.items()}
        return real(w, kept, [])  # no project reason; only Q-005 stays open (the input is not ready)

    monkeypatch.setattr(status_module, "_part_rows", keep_q005)
    for part in (INPUT_PART, PART):
        review = work / "parts" / part / "review" / "round-1" / "review.md"
        review.parent.mkdir(parents=True, exist_ok=True)
        review.write_text("pass\n", encoding="utf-8")
        for kind, extra in (
            ("checked", {}),
            ("reviewed", {"review": str(review), "review_round": 1, "verdict": "pass"}),
            ("locked", {}),
        ):
            assert write_part_receipt(work, part, kind, **extra)["written"]
    before = part_hash(work, load(work / MANIFEST), INPUT_PART)
    marks["plan_marks"].append({**first, "id": "P000002", "mark": "P-2", "key": "p-2", "display_text": "P-2"})
    (work / "marks.json").write_text(json.dumps(marks), encoding="utf-8")
    assert part_hash(work, load(work / MANIFEST), INPUT_PART) == before  # the hash does not move
    rows = {p["id"]: p for p in build_status(work, verify=True)["parts"]}
    assert rows[INPUT_PART]["check_failed"] is True and rows[INPUT_PART]["check_codes"] == ["mark_missing"]
    assert rows[INPUT_PART]["ready"] is False and rows[INPUT_PART]["blocking_open_ids"] == ["Q-005"]
    assert rows[PART]["input_check_failed"] == [INPUT_PART] and rows[PART]["ready"] is False


def check_stops(work: Path, part: str) -> bool:
    from tekla_harness.part_check import check_part

    doc = check_part(work, part)
    return doc["ok"] is False and doc["problems"][0]["code"] == "values_invalid"


def test_without_verify_the_document_is_what_it_was(ready, world):
    _, work = ready
    locked_world(work, [BAD_ROW])
    plain = build_status(work)
    assert build_status(work, verify=False) == plain and "verified" not in plain
    assert all("check_failed" not in p for p in plain["parts"])
    assert [p["ready"] for p in plain["parts"]] == [False, True, True, True]
    _, bare = world  # no manifest: the flag still ran, and there are no parts to check
    doc = build_status(bare, verify=True)
    assert doc["verified"] is True and "parts" not in doc and validate("status", doc) == []


def test_status_cli_verify_flag(ready, capsys):
    _, work = ready
    locked_world(work, [BAD_ROW])
    code, out, err = run_cli(capsys, "status", str(work))
    assert code == 0 and err == "" and "verified" not in out
    assert [p["ready"] for p in out["parts"]] == [False, True, True, True]
    code, out, err = run_cli(capsys, "status", str(work), "--verify")
    assert code == 0 and err == "" and out["verified"] is True and validate("status", out) == []
    ready_by_part = {p["id"]: p["ready"] for p in out["parts"]}
    assert ready_by_part == {"scout": False, PART_A: False, PART_B: True, PART_C: True}
    assert {p["id"]: p["check_failed"] for p in out["parts"] if "check_failed" in p} == {
        PART_A: True, PART_B: False, PART_C: False,
    }  # fmt: skip


def test_verify_writes_nothing(ready):
    _, work = ready
    locked_world(work, [BAD_ROW])
    before = {str(p.relative_to(work)): p.read_bytes() for p in work.rglob("*") if p.is_file()}
    build_status(work, verify=True)
    assert {str(p.relative_to(work)): p.read_bytes() for p in work.rglob("*") if p.is_file()} == before
