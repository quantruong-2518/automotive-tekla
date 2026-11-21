"""lifecycle: questions that other answers or selections close, without an answer of their own.

A closed question stays in the registry and its document, is no longer counted as blocking by `harness
status`, and is listed in `gate1.closed` with the reason (questions.Closure; the intake schema's
`closed_by`). Reasons: not_selected and separate (a grid-system conflict closed by the grid_system_select
answer), units_answered (grid_units_doubt once the file's units_confirm_all has an active answer),
rejected_systems_only (a read-structure question whose every cited grid family belongs to an unselected
system), other_file_set (a cross-file question between two different file sets).

Rules (deterministic, conservative: when in doubt nothing closes):

  * Only live registry entries (not obsolete) are closed, never a `reader` question, and only for a reason
    that fits the question's code. Every closure names (`question_id`) the live, actively answered question
    whose answer closes it; without one nothing closes.
  * Grid closures are read from `grid-systems.json` only while it is fresh: built from the current
    `inventory.json` and from the answers it reads as they are now (`answers_sha256`). System ids are
    positional, so a stale document could name other systems; `harness status` asks for the rerun.
  * not_selected / separate: the conflict's `closed_by` in that fresh document (harness grid-system derived it
    from the grid_system_select answer); `question_id` is the answered select question.
  * rejected_systems_only: a live read-structure question of a REJECTABLE_CODES code whose every ref in
    `structure-questions.json` names its grid `families`, every one of them (file-local ids) a member family
    (full or partial) of a system the answered select question leaves out and of no selected system. A
    family in no system, a ref without families, or every system selected keeps it open. Not
    grid_gate1_confirmation: confirming the grids stays a gate-1 step (an engineer decision to drop it).
  * units_answered: a live grid_units_doubt whose file's live units_confirm_all (same file content) has an
    active answer; `question_id` is that units question.
  * other_file_set is not derived: once file_set_relation is answered, harness grid-system no longer
    compares two sets, so a cross-set conflict is no longer raised at all (obsolete, not closed). Its
    registry `obsolete_reason` says so when harness grid-system passes Ledger.sync
    `superseded_by={grid_system_conflict: file_set_relation}` (questions.OBSOLETE_SUPERSEDED).

Read-only: never writes. A missing document closes nothing; an unreadable or invalid one is an error
(QuestionsError, exit 1), never silently skipped.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from tekla_harness.grid_system import consumed_answers_digest
from tekla_harness.grids import FAMILY_WHERE_CODES
from tekla_harness.questions import (
    CONFLICT_CODE,
    EXIT_INVALID,
    SELECT_CODE,
    UNITS_CONFIRM_CODE,
    Closure,
    Ledger,
    QuestionsError,
    active_answers,
)
from tekla_harness.schemas import validate

GRID_SYSTEMS_FILE = "grid-systems.json"
INVENTORY_FILE = "inventory.json"
STRUCTURE_QUESTIONS_FILE = "structure-questions.json"
UNITS_DOUBT_CODE = "grid_units_doubt"
# read-structure codes that rejected_systems_only may close: every grids code whose refs cite families,
# except grid_gate1_confirmation (the grid confirmation stays a gate-1 step)
REJECTABLE_CODES = FAMILY_WHERE_CODES | frozenset({"grid_family_axis_assignment"})


def _load(path: Path, schema: str) -> Any:
    """A work-folder document, schema-checked; None when it does not exist."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QuestionsError(
            EXIT_INVALID, f"{path} cannot be read for the question lifecycle: {exc}"
        ) from exc
    problems = validate(schema, data)
    if problems:
        details = "; ".join(f"{p.path or '/'}: {p.message}" for p in problems[:5])
        raise QuestionsError(EXIT_INVALID, f"{path} is invalid ({schema} schema): {details}")
    return data


def _live(ledger: Ledger, code: str, producer: str) -> list[tuple[str, dict[str, Any]]]:
    """(key, entry) of the live registry entries of a code, in id order."""
    return sorted(
        (
            (k, e)
            for k, e in ledger.registry["questions"].items()
            if e["code"] == code and e["producer"] == producer and e["status"] != "obsolete"
        ),
        key=lambda kv: int(kv[1]["id"][2:]),
    )


def _answered(ledger: Ledger, code: str, producer: str) -> tuple[str, dict[str, Any]] | None:
    """(question id, active answer) of the live question of `code` that has one (the latest id)."""
    active = active_answers(ledger.answers)
    found = [(e["id"], active[k]) for k, e in _live(ledger, code, producer) if k in active]
    return found[-1] if found else None


def _fresh_grid_systems(work: Path, ledger: Ledger) -> dict[str, Any] | None:
    """grid-systems.json when it was built from the current inventory and answers; None otherwise."""
    doc = _load(work / GRID_SYSTEMS_FILE, "grid-system")
    inventory = work / INVENTORY_FILE
    if doc is None or not inventory.is_file():
        return None
    try:
        inventory_sha = hashlib.sha256(inventory.read_bytes()).hexdigest()
    except OSError as exc:
        raise QuestionsError(
            EXIT_INVALID, f"{inventory} cannot be read for the question lifecycle: {exc}"
        ) from exc
    if doc["inventory_sha256"] != inventory_sha:
        return None
    if doc["answers_sha256"] != consumed_answers_digest(ledger.answers["answers"]):
        return None
    return doc


def _conflict_closures(
    doc: dict[str, Any], ledger: Ledger, live: dict[str, dict[str, Any]]
) -> dict[str, Closure]:
    select = _answered(ledger, SELECT_CODE, "grid-system")
    if select is None:  # a closure always names the answered question that closes it
        return {}
    out: dict[str, Closure] = {}
    for c in doc["conflicts"]:
        key = c["question_key"]
        entry = live.get(key) if key is not None else None
        if (
            key is not None
            and entry is not None
            and (entry["code"], entry["producer"]) == (CONFLICT_CODE, "grid-system")
            and c["closed_by"] is not None
        ):
            out[key] = Closure(select[0], c["closed_by"])
    return out


def _rejected_closures(
    work: Path, doc: dict[str, Any], ledger: Ledger, live: dict[str, dict[str, Any]]
) -> dict[str, Closure]:
    select = _answered(ledger, SELECT_CODE, "grid-system")
    if select is None:
        return {}
    ids = [s["system_id"] for s in doc["systems"]]
    values = select[1].get("values")
    chosen = values.get("systems") if isinstance(values, dict) else None
    selected = {str(x) for x in chosen} if isinstance(chosen, list) and chosen else set(ids)

    def members(sids: set[str]) -> set[tuple[str, str]]:
        return {
            (c["file"], f["family_id"])
            for s in doc["systems"]
            if s["system_id"] in sids
            for c in s["evidence"]["contributors"]
            for f in c["families"]
        }

    rejected = members(set(ids) - selected) - members(selected)
    if not rejected:
        return {}
    questions = _load(work / STRUCTURE_QUESTIONS_FILE, "intake")
    out: dict[str, Closure] = {}
    for q in questions["questions"] if questions is not None else []:
        entry = live.get(q["key"])
        if (
            entry is None
            or (entry["producer"], entry["code"]) != ("structure", q["code"])
            or q["code"] not in REJECTABLE_CODES
            or not q["refs"]
        ):
            continue
        cited = [(r.get("file") or q["file"], fid) for r in q["refs"] for fid in r.get("families") or [None]]
        if all(fid is not None and (file, fid) in rejected for file, fid in cited):
            out[q["key"]] = Closure(select[0], "rejected_systems_only")
    return out


def _units_closures(ledger: Ledger) -> dict[str, Closure]:
    active = active_answers(ledger.answers)
    answered = {
        (e["file"], e.get("file_sha256")): e["id"]
        for k, e in _live(ledger, UNITS_CONFIRM_CODE, "intake")
        if k in active and e["file"] is not None
    }
    out: dict[str, Closure] = {}
    for k, e in _live(ledger, UNITS_DOUBT_CODE, "structure"):
        qid = answered.get((e["file"], e.get("file_sha256")))
        if qid is not None:
            out[k] = Closure(qid, "units_answered")
    return out


def closures(work: Path, ledger: Ledger) -> dict[str, Closure]:
    """Registry key -> why that question is closed. See the module docstring for the rules."""
    work = Path(work)
    live = {k: e for k, e in ledger.registry["questions"].items() if e["status"] != "obsolete"}
    out = _units_closures(ledger)
    grid = _fresh_grid_systems(work, ledger)
    if grid is not None:
        out.update(_conflict_closures(grid, ledger, live))
        out.update(_rejected_closures(work, grid, ledger, live))
    return out
