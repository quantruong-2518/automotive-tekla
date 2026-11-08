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


def test_a_simulated_units_answer_keeps_gate1_closed_and_its_reason_names_the_question(ready):
    _, work = ready
    q = find(questions_of(work, "questions.json"), "units_confirm_all", "set.dxf")
    record_answer(work, q["id"], "mm (simulated)", "agent", {"unit": "mm"}, role="simulated")
    gate1 = build_status(work)["gate1"]
    assert gate1["ready_for_gate1"] is False
    (reason,) = [r for r in gate1["reasons"] if q["id"] in r]
    assert reason.startswith(f"answers: {q['id']} units_confirm_all (set.dxf)") and "simulated" in reason
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
