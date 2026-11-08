"""Answer provenance (tool wave 2, fix 10): `harness answer --role` is required, and gate 1 counts only the
engineer's answers to the questions it reads.

The world is test_status.py's (two synthetic DXF drawings through every producer); `ready` has every
blocking question answered by the engineer, so gate 1 is open there. Its fixtures are imported by name,
so a test parameter re-binds them (F811 is expected here).
"""

# ruff: noqa: F811

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from tekla_harness.answers import record_answer
from tekla_harness.schemas import validate
from tekla_harness.status import build_status
from test_status import (  # noqa: F401  (pytest fixtures, used by name)
    base_world,
    find,
    load,
    questions_of,
    ready,
    ready_gate1,
    ready_world,
    world,
)

ROLE = "--role engineer"
ENGINEER_STEP = "the engineer runs: "
COMMAND = re.compile(r"harness answer \S+ (?:Q-\d+|<[^>]+>)[^()\n]*")


def answer_commands(reasons: list[str]) -> list[str]:
    """Every full `harness answer ... --text ...` command printed in the gate-1 reasons."""
    return [c for r in reasons for c in COMMAND.findall(r) if "--text" in c]


def test_every_printed_answer_command_names_the_engineer_role_once_after_by(world):
    _, work = world
    commands = answer_commands(build_status(work)["gate1"]["reasons"])
    assert commands
    for c in commands:
        assert c.count("--role") == 1, c
        assert f'--by "..." {ROLE}' in c, c


def test_every_printed_answer_command_is_the_engineers_step_not_an_agents(world):
    """Review M1: a reason never hands an agent a ready-to-paste `--role engineer` command."""
    _, work = world
    reasons = build_status(work)["gate1"]["reasons"]
    hits = [r for r in reasons if "harness answer" in r]
    assert hits
    for r in hits:
        assert r.count("harness answer") == r.count(f"{ENGINEER_STEP}harness answer"), r


def test_record_answer_needs_a_role_keyword(world):
    from tekla_harness.questions import QuestionsError

    _, work = world
    q = find(questions_of(work, "questions.json"), "units_confirm_all", "set.dxf")
    with pytest.raises(TypeError):
        record_answer(work, q["id"], "mm", "me", {"unit": "mm"})  # type: ignore[call-arg]
    with pytest.raises(QuestionsError) as caught:
        record_answer(work, q["id"], "mm", "me", {"unit": "mm"}, role=None)  # type: ignore[arg-type]
    assert caught.value.exit_code == 2 and "--role" in str(caught.value)
    assert not (work / "answers.json").exists()


def test_a_simulated_units_answer_keeps_gate1_closed_and_its_reason_names_the_question(ready):
    _, work = ready
    q = find(questions_of(work, "questions.json"), "units_confirm_all", "set.dxf")
    record_answer(work, q["id"], "mm (simulated)", "agent", {"unit": "mm"}, role="simulated")
    gate1 = build_status(work)["gate1"]
    assert gate1["ready_for_gate1"] is False
    (reason,) = [r for r in gate1["reasons"] if q["id"] in r]
    assert reason.startswith(f"answers: {q['id']} units_confirm_all (set.dxf)") and "simulated" in reason
    assert "the engineer must answer it again themselves" in reason
    assert f"({ENGINEER_STEP}harness answer " in reason
    (command,) = answer_commands([reason])
    assert command.count("--role") == 1 and f'--by "..." {ROLE}' in command


# --- legacy answers (no role) do not count for gate 1 (DESIGN D4) ---------------------------------------


def strip_roles(work: Path, question_ids: set[str] | None = None) -> list[dict[str, Any]]:
    """Make answers look recorded before roles existed (all, or those of `question_ids`); returns them."""
    doc = load(work / "answers.json")
    stripped = []
    for a in doc["answers"]:
        if question_ids is None or a["question_id"] in question_ids:
            a.pop("answered_by_role", None)
            stripped.append(a)
    (work / "answers.json").write_text(json.dumps(doc), encoding="utf-8")
    return stripped


def test_legacy_answers_do_not_count_as_the_engineers(ready):
    from tekla_harness import status as status_module

    _, work = ready
    assert status_module.LEGACY_ANSWER_IS_ENGINEER is False
    stripped = [a for a in strip_roles(work) if a["status"] == "active"]
    gate1 = build_status(work)["gate1"]
    assert gate1["ready_for_gate1"] is False
    assert validate("status", build_status(work)) == []
    listed = gate1["non_engineer_answers"]
    assert {a["role"] for a in listed} == {None}
    assert {a["question_id"] for a in listed} == {a["question_id"] for a in stripped}
    for a in listed:
        (reason,) = [r for r in gate1["reasons"] if r.startswith(f"answers: {a['question_id']} ")]
        assert "no recorded role" in reason and f"{a['question_id']} --text" in reason


def test_one_legacy_units_answer_blocks_gate1_until_the_engineer_answers_again(ready):
    _, work = ready
    q = find(questions_of(work, "questions.json"), "units_confirm_all", "set.dxf")
    strip_roles(work, {q["id"]})
    gate1 = build_status(work)["gate1"]
    assert gate1["ready_for_gate1"] is False
    assert [a["question_id"] for a in gate1["non_engineer_answers"]] == [q["id"]]
    (reason,) = gate1["reasons"]
    assert reason.startswith(f"answers: {q['id']} units_confirm_all (set.dxf) was answered by no recorded")
    record_answer(work, q["id"], "mm", "the engineer", {"unit": "mm"}, role="engineer")
    assert build_status(work)["gate1"] == ready_gate1(work)


def test_a_superseded_simulated_answer_no_longer_counts(ready):
    _, work = ready
    q = find(questions_of(work, "structure-questions.json"), "level_finished_vs_structural", "set.dxf")
    record_answer(work, q["id"], "structural (simulated)", "agent", role="simulated")
    assert build_status(work)["gate1"]["ready_for_gate1"] is False
    record_answer(work, q["id"], "structural", "the engineer", role="engineer")
    assert build_status(work)["gate1"] == ready_gate1(work)


def test_a_simulated_answer_to_every_gate_producer_is_a_reason(ready):
    """intake, read-structure, grid-system and reader questions are read by gate 1."""
    from tekla_harness.ask import ask_question

    _, work = ready
    reader = ask_question(work, code="reader_note", where="W", found="", text="Câu hỏi?")
    picks = {
        "intake": find(questions_of(work, "questions.json"), "units_confirm_all", "other.dxf")["id"],
        "structure": find(
            questions_of(work, "structure-questions.json"), "level_finished_vs_structural", "set.dxf"
        )["id"],
        "grid-system": find(questions_of(work, "grid-system-questions.json"), "grid_system_select")["id"],
        "reader": reader["id"],
    }
    for qid in picks.values():
        record_answer(work, qid, "simulated", "agent", values_of(work, qid), role="simulated")
    gate1 = build_status(work)["gate1"]
    assert sorted(a["question_id"] for a in gate1["non_engineer_answers"]) == sorted(picks.values())


def test_a_simulated_answer_outside_the_gate_producers_is_not_a_reason(ready):
    """callouts and marks questions do not feed gate 1 (status.GATE_PRODUCERS)."""
    _, work = ready
    registry, answers = load(work / "question-registry.json"), load(work / "answers.json")
    for n, (producer, code) in enumerate((("callouts", "callout_ambiguous"), ("marks", "mark_unparsed"))):
        key, qid = f"{n}" * 16, f"Q-{900 + n}"
        registry["questions"][key] = {
            "id": qid, "code": code, "file": "set.dxf", "producer": producer, "status": "answered",
            "first_seen_run": 1, "last_seen_run": 1, "blocking": True, "file_sha256": None,
        }  # fmt: skip
        answers["answers"].append(
            {
                "key": key, "question_id": qid, "code": code, "file": "set.dxf", "answer_text": "x",
                "values": {}, "answered_by": "agent", "answered_by_role": "simulated",
                "answered_on": "2026-11-08", "status": "active",
            }
        )  # fmt: skip
    registry["next_id"] = 902
    (work / "question-registry.json").write_text(json.dumps(registry), encoding="utf-8")
    (work / "answers.json").write_text(json.dumps(answers), encoding="utf-8")
    assert build_status(work)["gate1"] == ready_gate1(work)


def values_of(work: Path, question_id: str) -> dict[str, str]:
    """The structured values of the active answer to a question, as `--value` strings (none: {})."""
    for a in load(work / "answers.json")["answers"]:
        if a["question_id"] == question_id and a["status"] == "active":
            return {k: ",".join(v) if isinstance(v, list) else v for k, v in a["values"].items()}
    return {}


# --- answers to retired questions that a gate check still reads (units, grid-system) --------------------


def orphan(work: Path, code: str, values: dict[str, Any], role: str | None, *, key: str = "e" * 16) -> None:
    """An active answer whose key is in no registry entry (hand-edited, or left from another run)."""
    doc = load(work / "answers.json")
    doc["answers"].append(
        {
            "key": key, "question_id": "Q-990", "code": code, "file": "set.dxf", "answer_text": "x",
            "values": values, "answered_by": "x", "answered_on": "2026-11-08", "status": "active",
            **({"answered_by_role": role} if role is not None else {}),
        }
    )  # fmt: skip
    (work / "answers.json").write_text(json.dumps(doc), encoding="utf-8")


def answer_reasons(work: Path) -> list[str]:
    return [r for r in build_status(work)["gate1"]["reasons"] if r.startswith("answers:")]


@pytest.mark.parametrize("role", ["simulated", None])
def test_a_non_engineer_answer_to_no_registry_question_is_named_by_its_key(ready, role):
    _, work = ready
    orphan(work, "units_confirm_all", {"unit": "mm"}, role)
    gate1 = build_status(work)["gate1"]
    assert gate1["ready_for_gate1"] is False
    assert validate("status", build_status(work)) == []
    assert {"question_id": "Q-990", "code": "units_confirm_all", "file": "set.dxf", "role": role} in gate1[
        "non_engineer_answers"
    ]
    (reason,) = answer_reasons(work)
    assert "e" * 16 in reason and "not in the registry" in reason, reason


def test_a_non_engineer_answer_to_an_obsolete_question_still_read_by_a_gate_check_is_named(ready):
    _, work = ready
    q = find(questions_of(work, "questions.json"), "units_confirm_all", "set.dxf")
    registry = load(work / "question-registry.json")
    registry["questions"][q["key"]]["status"] = "obsolete"  # its active answer is still read by units_by_file
    (work / "question-registry.json").write_text(json.dumps(registry), encoding="utf-8")
    doc = load(work / "answers.json")
    for a in doc["answers"]:
        if a["key"] == q["key"] and a["status"] == "active":
            a["answered_by_role"] = "simulated"
    (work / "answers.json").write_text(json.dumps(doc), encoding="utf-8")
    (reason,) = answer_reasons(work)
    assert q["key"] in reason and "obsolete" in reason, reason


def test_retired_answers_by_the_engineer_or_not_read_by_gate_1_are_no_reason(ready):
    _, work = ready
    orphan(work, "units_confirm_all", {"unit": "mm"}, "engineer")
    orphan(work, "level_name_conflict", {}, "simulated", key="d" * 16)  # gate 1 reads levels by live key
    assert answer_reasons(work) == []


# --- review M2: status accepts a lifecycle closure only under the closure contract --------------------


def inject(work: Path, producer: str, code: str, *, role: str | None = None, blocking: bool = True) -> str:
    """Add a live registry question (and, with `role`, an active answer by that role); returns its id."""
    registry, answers = load(work / "question-registry.json"), load(work / "answers.json")
    number = registry["next_id"]
    qid, key = f"Q-{number:03d}", f"{number:016x}"
    registry["questions"][key] = {
        "id": qid, "code": code, "file": "set.dxf", "producer": producer,
        "status": "open" if role is None else "answered", "first_seen_run": 1, "last_seen_run": 1,
        "blocking": blocking, "file_sha256": None,
    }  # fmt: skip
    registry["next_id"] = number + 1
    if role is not None:
        answers["answers"].append(
            {
                "key": key, "question_id": qid, "code": code, "file": "set.dxf", "answer_text": "x",
                "values": {}, "answered_by": "x", "answered_by_role": role, "answered_on": "2026-11-08",
                "status": "active",
            }
        )  # fmt: skip
    (work / "question-registry.json").write_text(json.dumps(registry), encoding="utf-8")
    (work / "answers.json").write_text(json.dumps(answers), encoding="utf-8")
    return qid


def close(monkeypatch, work: Path, rows: dict[str, Any]) -> None:
    """lifecycle.closures returns these closures (question id -> Closure)."""
    from tekla_harness import lifecycle

    keys = {e["id"]: k for k, e in load(work / "question-registry.json")["questions"].items()}
    monkeypatch.setattr(lifecycle, "closures", lambda w, ledger: {keys[q]: c for q, c in rows.items()})


def select_id(work: Path) -> str:
    return find(questions_of(work, "grid-system-questions.json"), "grid_system_select")["id"]


def units_id(work: Path) -> str:
    return find(questions_of(work, "questions.json"), "units_confirm_all", "set.dxf")["id"]


def refused(work: Path, qid: str) -> str:
    gate1 = build_status(work)["gate1"]
    assert gate1["ready_for_gate1"] is False
    assert qid not in [row["id"] for row in gate1.get("closed", [])]
    (reason,) = [r for r in gate1["reasons"] if r.startswith(f"closures: {qid} ")]
    return reason


def test_a_closure_naming_no_answer_does_not_open_gate1(ready, monkeypatch):
    """The review probe: Closure(None, units_answered) on an unanswered blocking reader question."""
    from tekla_harness.ask import ask_question
    from tekla_harness.questions import Closure

    _, work = ready
    asked = ask_question(work, code="reader_gap", where="S-1 note 3", found="??", text="?", blocking=True)
    close(monkeypatch, work, {asked["id"]: Closure(None, "units_answered")})
    reason = refused(work, asked["id"])
    assert "stays open" in reason and "a reader question closes only through its own answer" in reason
    reasons = build_status(work)["gate1"]["reasons"]
    assert any(r.startswith("reader: 1 blocking question(s) open") for r in reasons)


WHY = {  # the refusal each contract violation names (each check, not just the first that happens to fire)
    "wrong_reason": "units_answered cannot close a structure grid_label_missing question",
    "no_question": "it names no question whose answer closes it",
    "unknown_question": "Q-999 is not a live question",
    "obsolete": "is not a live question",
    "unanswered": "has no active answer",
    "simulated": "was not answered by the engineer",
    "legacy": "was not answered by the engineer",
    "reader": "a reader question closes only through its own answer",
}


@pytest.mark.parametrize("case", list(WHY))
def test_a_closure_outside_the_contract_is_refused(ready, monkeypatch, case):
    from tekla_harness.questions import Closure

    _, work = ready
    target = inject(work, "reader" if case == "reader" else "structure", "grid_label_missing")
    closer = {
        "wrong_reason": units_id(work),
        "no_question": None,
        "unknown_question": "Q-999",
        "unanswered": inject(work, "grid-system", "grid_system_select"),
        "simulated": inject(work, "grid-system", "grid_system_select", role="simulated"),
    }.get(case, select_id(work))
    if case == "legacy":
        doc = load(work / "answers.json")
        for a in doc["answers"]:
            if a["question_id"] == closer:
                a.pop("answered_by_role")
        (work / "answers.json").write_text(json.dumps(doc), encoding="utf-8")
    if case == "obsolete":  # the select question is no longer raised; its answer is still active
        registry = load(work / "question-registry.json")
        for e in registry["questions"].values():
            if e["id"] == closer:
                e["status"] = "obsolete"
        (work / "question-registry.json").write_text(json.dumps(registry), encoding="utf-8")
    why = "units_answered" if case == "wrong_reason" else "rejected_systems_only"
    close(monkeypatch, work, {target: Closure(closer, why)})
    reason = refused(work, target)
    assert "stays open" in reason and WHY[case] in reason, reason


@pytest.mark.parametrize(
    ("producer", "code", "reason", "closer"),
    [
        ("structure", "grid_label_missing", "rejected_systems_only", "select"),
        ("structure", "grid_units_doubt", "units_answered", "units"),
        ("grid-system", "grid_system_conflict", "not_selected", "select"),
        ("grid-system", "grid_system_conflict", "separate", "select"),
    ],
)
def test_a_closure_under_the_contract_closes_its_question(ready, monkeypatch, producer, code, reason, closer):
    from tekla_harness.questions import Closure

    _, work = ready
    target = inject(work, producer, code)
    assert build_status(work)["gate1"]["ready_for_gate1"] is False
    by = select_id(work) if closer == "select" else units_id(work)
    close(monkeypatch, work, {target: Closure(by, reason)})
    gate1 = build_status(work)["gate1"]
    assert gate1["ready_for_gate1"] is True, gate1["reasons"]
    assert {"id": target, "reason": reason, "question_id": by} in gate1["closed"]


@pytest.mark.parametrize(
    ("producer", "code", "reason"),
    [
        ("structure", "grid_label_missing", "units_answered"),
        ("structure", "level_name_conflict", "rejected_systems_only"),
        ("structure", "grid_gate1_confirmation", "rejected_systems_only"),  # stays a gate-1 step
        ("intake", "grid_label_missing", "rejected_systems_only"),
        ("structure", "grid_system_conflict", "separate"),
        ("grid-system", "grid_system_select", "not_selected"),
        ("grid-system", "grid_system_axis_unassigned", "separate"),
        ("grid-system", "units_answer_contradicts_evidence", "other_file_set"),
        ("structure", "grid_units_doubt", "not_selected"),
        ("grid-system", "grid_system_conflict", "units_answered"),
        ("grid-system", "grid_system_conflict", "other_file_set"),  # never derived yet: fail closed
    ],
)
def test_a_closure_reason_must_fit_the_closed_question(ready, monkeypatch, producer, code, reason):
    from tekla_harness.questions import Closure

    _, work = ready
    target = inject(work, producer, code)
    close(monkeypatch, work, {target: Closure(select_id(work), reason)})
    assert "cannot close" in refused(work, target)


@pytest.mark.parametrize(
    ("producer", "code", "reason", "closer", "needed"),
    [
        ("grid-system", "grid_system_conflict", "not_selected", "units", "grid_system_select"),
        ("grid-system", "grid_system_conflict", "separate", "units", "grid_system_select"),
        ("structure", "grid_label_missing", "rejected_systems_only", "units", "grid_system_select"),
        ("structure", "grid_units_doubt", "units_answered", "select", "units_confirm_all"),
        ("structure", "grid_units_doubt", "units_answered", "level", "units_confirm_all"),
    ],
)
def test_a_closure_needs_the_closing_question_its_reason_names(
    ready, monkeypatch, producer, code, reason, closer, needed
):
    """An engineer answer to another question does not close: the closer's code must be the one whose
    answer settles the reason."""
    from tekla_harness.questions import Closure

    _, work = ready
    target = inject(work, producer, code)
    by = {
        "units": units_id(work),
        "select": select_id(work),
        "level": find(
            questions_of(work, "structure-questions.json"), "level_finished_vs_structural", "set.dxf"
        )["id"],
    }[closer]
    close(monkeypatch, work, {target: Closure(by, reason)})
    reason_text = refused(work, target)
    assert f"{by} is not a {needed} question" in reason_text, reason_text


# --- a closure a producer already wrote (blocking: false + closed_by) passes the same contract ----------


def write_closed_by(work: Path, name: str, code: str, closed_by: dict[str, Any] | None) -> dict[str, Any]:
    """Set `closed_by` on the first question of `code` in a question document and make its registry entry
    non-blocking (what a producer writes for a question a closure settles); returns the question."""
    doc = load(work / name)
    q = next(q for q in doc["questions"] if q["code"] == code)
    q["closed_by"], q["blocking"] = closed_by, False
    (work / name).write_text(json.dumps(doc), encoding="utf-8")
    registry = load(work / "question-registry.json")
    registry["questions"][q["key"]]["blocking"] = False
    (work / "question-registry.json").write_text(json.dumps(registry), encoding="utf-8")
    return q


def test_the_conflict_grid_system_closed_stays_closed(ready):
    _, work = ready
    conflict = find(questions_of(work, "grid-system-questions.json"), "grid_system_conflict")
    assert conflict["blocking"] is False and conflict["closed_by"]["reason"] == "separate"
    assert build_status(work)["gate1"] == ready_gate1(work)


@pytest.mark.parametrize(
    ("name", "code", "closed_by", "why"),
    [
        (
            "grid-system-questions.json",
            "grid_system_conflict",
            {"question_id": None, "reason": "separate"},
            "it names no question whose answer closes it",
        ),
        (
            "structure-questions.json",
            "grid_family_axis_assignment",
            {"question_id": "UNITS", "reason": "rejected_systems_only"},
            "is not a grid_system_select question",
        ),
        (
            "structure-questions.json",
            "grid_family_axis_assignment",
            {"question_id": "SELECT", "reason": "x"},
            "unknown closure reason",
        ),
    ],
)
def test_a_written_closure_outside_the_contract_counts_as_blocking(
    ready, monkeypatch, name, code, closed_by, why
):
    from tekla_harness import lifecycle

    _, work = ready
    monkeypatch.setattr(lifecycle, "closures", lambda w, ledger: {})  # only the written flag says closed
    ids = {"UNITS": units_id(work), "SELECT": select_id(work)}
    if closed_by["question_id"] in ids:
        closed_by = {**closed_by, "question_id": ids[closed_by["question_id"]]}
    before = build_status(work)
    q = write_closed_by(work, name, code, closed_by)
    status = build_status(work)
    gate1 = status["gate1"]
    assert gate1["ready_for_gate1"] is False
    (reason,) = [r for r in gate1["reasons"] if r.startswith(f"closures: {q['id']} ")]
    assert "stays blocking" in reason and why in reason, reason
    label = "grid-system" if name.startswith("grid-system") else "read-structure"
    counts = {p["producer"]: p["questions"] for p in status["producers"]}[label]
    old = {p["producer"]: p["questions"] for p in before["producers"]}[label]
    assert counts["blocking"] == old["blocking"] + 1  # both questions were non-blocking before


# --- an unreadable lifecycle document is a status error, not a traceback --------------------------------


def test_an_invalid_grid_systems_document_is_exit_1_in_status_and_questions_md(ready, capsys):
    from tekla_harness.cli import main
    from tekla_harness.questions_md import QuestionsMdError, render_questions_md
    from tekla_harness.status import StatusError

    _, work = ready
    (work / "grid-systems.json").write_text("{}", encoding="utf-8")  # JSON, but not a grid-system document
    with pytest.raises(StatusError) as caught:
        build_status(work)
    assert caught.value.exit_code == 1
    with pytest.raises(QuestionsMdError) as rendered:
        render_questions_md(work)
    assert rendered.value.exit_code == 1
    assert main(["status", str(work)]) == 1
    assert "Traceback" not in capsys.readouterr().err
