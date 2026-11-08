"""Answer provenance (tool wave 2, fix 10): `harness answer --role` is required, and gate 1 counts only the
engineer's answers to the questions it reads.

The world is test_status.py's (two synthetic DXF drawings through every producer); `ready` has every
blocking question answered by the engineer, so gate 1 is open there. Its fixtures are imported by name,
so a test parameter re-binds them (F811 is expected here).
"""

# ruff: noqa: F811

from __future__ import annotations

import re

from tekla_harness.answers import record_answer
from tekla_harness.status import build_status
from test_status import (  # noqa: F401  (pytest fixtures, used by name)
    base_world,
    find,
    questions_of,
    ready,
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
