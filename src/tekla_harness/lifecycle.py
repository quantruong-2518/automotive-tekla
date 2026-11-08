"""lifecycle: questions that other answers or selections close, without an answer of their own.

A closed question stays in the registry and its document, is no longer counted as blocking by `harness
status`, and is listed in `gate1.closed` with the reason (questions.Closure; the intake schema's
`closed_by`). Reasons: not_selected and separate (a grid-system conflict closed by the grid_system_select
answer), units_answered (grid_units_doubt once the file's units_confirm_all has an active answer),
rejected_systems_only (a read-structure question whose every cited grid family belongs to an unselected
system), other_file_set (a cross-file question between two different file sets).

Tool wave 2 seam: no closure is derived yet; package P2 implements the rules. Read-only: never writes.
"""

from __future__ import annotations

from pathlib import Path

from tekla_harness.questions import Closure, Ledger


def closures(work: Path, ledger: Ledger) -> dict[str, Closure]:
    """Registry key -> why that question is closed. Seam: none."""
    del work, ledger
    return {}
