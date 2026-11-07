"""status: where a work folder stands (`harness status <work_dir>`), and whether gate 1 can be opened.

Read-only: nothing is written. Everything is recomputed from the sources of truth, never from the question
documents (they can be stale after `harness answer` or a producer rerun):

  * per producer (intake, read-structure, callouts, grid-system, reader): question counts from
    `question-registry.json` + `answers.json` (total, blocking, blocking_open, answered), the stale answers,
    and whether the producer's output documents are `fresh`, `stale` or `missing` with the command that
    fixes it. read-structure, callouts and grid-system record the sha256 of the `inventory.json` they were
    built from (`inventory_sha256`); grid-system also fingerprints the units and axis answers it read
    (`answers_sha256`). Intake's own documents are fresh when they exist (inventory.json is the reference).
  * `gate1.ready_for_gate1`, true only when `reasons` is empty (see schemas/status.schema.json for the
    exact rules): units answered for every probed DXF/DWG; grid systems found, grid_system_select answered
    and every used system axis-assigned; level_storey_selection and level_finished_vs_structural answered;
    no blocking question open in intake, read-structure, grid-system or reader (the drawing-reader's
    `harness ask` questions); all outputs fresh (reader: n/a, it has no freshness).

An entry written to the registry before it recorded the `blocking` flag counts as blocking (never assume a
question is harmless) and is reported in `blocking_unknown`.

Exit codes (AGENTS.md): 0 for any readable work folder (status is information, not a verdict), 1 an
unreadable or invalid document, 2 not a work folder.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from tekla_harness.grid_system import consumed_answers_digest, units_by_file
from tekla_harness.questions import (
    PRODUCER_COMMANDS,
    REGISTRY_FILE,
    SELECT_CODE,
    QuestionsError,
    active_answers,
    load_ledger,
)
from tekla_harness.schemas import validate

SCHEMA_VERSION = "0.1"
EXIT_OK, EXIT_INVALID, EXIT_USAGE = 0, 1, 2
MAX_IDS = 50  # question ids listed per producer
REASON_IDS = 10  # question ids named in one gate-1 reason
LEVEL_CODES = ("level_storey_selection", "level_finished_vs_structural")
# status name -> registry producer, in the order they run
PRODUCERS = (
    ("intake", "intake"),
    ("read-structure", "structure"),
    ("callouts", "callouts"),
    ("marks", "marks"),
    ("grid-system", "grid-system"),
    ("reader", "reader"),
)
# gate 1 needs no blocking question open in these
GATE_PRODUCERS = ("intake", "read-structure", "grid-system", "reader")


class StatusError(Exception):
    """A run that cannot proceed; `exit_code` is the CLI exit code."""

    def __init__(self, exit_code: int, message: str) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise StatusError(EXIT_INVALID, f"{label} {path} cannot be read: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise StatusError(EXIT_INVALID, f"{label} {path} is not valid JSON: {exc}") from exc


def _id_number(question_id: str) -> int:
    return int(question_id[2:])


# --- questions ------------------------------------------------------------------------------------


def _question_counts(
    registry: dict[str, Any], active: dict[str, dict[str, Any]], producer: str
) -> tuple[dict[str, int], list[str]]:
    entries = {k: e for k, e in registry["questions"].items() if e["producer"] == producer}
    live = {k: e for k, e in entries.items() if e["status"] != "obsolete"}
    blocking = {k: e for k, e in live.items() if e.get("blocking", True)}
    open_ids = sorted((e["id"] for k, e in blocking.items() if k not in active), key=_id_number)
    counts = {
        "total": len(live),
        "blocking": len(blocking),
        "blocking_unknown": sum(1 for e in live.values() if "blocking" not in e),
        "blocking_open": len(open_ids),
        "answered": sum(1 for k in live if k in active),
        "obsolete": len(entries) - len(live),
    }
    return counts, open_ids


def _stale_answers(
    ledger_answers: list[dict[str, Any]], registry: dict[str, Any], producer: str
) -> list[dict]:
    out = []
    for a in ledger_answers:
        entry = registry["questions"].get(a["key"])
        if a["status"] != "stale" or entry is None or entry["producer"] != producer:
            continue
        out.append(
            {
                "question_id": a["question_id"],
                "key": a["key"],
                "code": a["code"],
                "file": a["file"],
                "reason": a["stale_reason"],
            }
        )
    return sorted(out, key=lambda a: _id_number(a["question_id"]))


# --- freshness ------------------------------------------------------------------------------------


def _rerun(label: str, work_dir: str) -> str:
    command = PRODUCER_COMMANDS[dict(PRODUCERS)[label]]
    if label == "intake":
        return f"{command} <input_dir> --out {work_dir}"
    if label == "read-structure":
        return f"{command} {work_dir} --input-dir <input_dir>"
    return f"{command} {work_dir}"


def _outputs(
    work: Path,
    label: str,
    work_dir: str,
    inventory_sha: str,
    answers: list[dict[str, Any]],
) -> dict[str, Any]:
    """fresh | stale | missing for one producer's documents (n/a for the reader)."""
    if label == "reader":  # questions are raised one at a time by `harness ask`: nothing to go stale
        return {"status": "n/a", "files": [], "reason": None, "rerun": None}
    files = {
        "intake": ["inventory.json", "questions.json"],
        "read-structure": ["structure-summary.json", "structure-questions.json"],
        "callouts": ["callouts.json", "callouts-questions.json"],
        "marks": ["marks.json", "marks-questions.json"],
        "grid-system": ["grid-systems.json", "grid-system-questions.json"],
    }[label]
    status, reason = "fresh", None
    absent = [f for f in files if not (work / f).is_file()]
    if absent:
        status, reason = "missing", f"{', '.join(absent)} not found"
    elif label != "intake":
        doc = _read_json(work / files[0], files[0])
        recorded = doc.get("inventory_sha256") if isinstance(doc, dict) else None
        if recorded != inventory_sha:
            status = "stale"
            reason = f"{files[0]} was built from another inventory.json (intake reran since)"
        elif label == "grid-system" and doc.get("answers_sha256") != consumed_answers_digest(answers):
            status = "stale"
            reason = "grid-systems.json was built before the latest units / axis answers"
    return {
        "status": status,
        "files": files,
        "reason": reason,
        "rerun": None if status == "fresh" else _rerun(label, work_dir),
    }


# --- gate 1 ---------------------------------------------------------------------------------------


def _ids(ids: list[str]) -> str:
    shown = ", ".join(ids[:REASON_IDS])
    return shown + (f" and {len(ids) - REASON_IDS} more" if len(ids) > REASON_IDS else "")


def _units_reasons(inventory: dict[str, Any], answers: list[dict[str, Any]]) -> list[str]:
    """`answers`: every answer of answers.json; only the active ones count."""
    probed = [
        r["path"] for r in inventory["files"] if r["format"] in ("dwg", "dxf") and r["probe"] is not None
    ]
    statuses = units_by_file([a for a in answers if a["status"] == "active"], probed, [])
    why = {
        "not_answered": "has no active units answer (harness answer <id> ... --value unit=mm)",
        "disagree": "has active units answers that disagree",
        "invalid": "has a units answer without a valid unit",
    }
    return [f"units: {f} {why[st]}" for f, (st, _) in statuses.items() if st != "answered"]


def _grid_reasons(
    work: Path,
    registry: dict[str, Any],
    active: dict[str, dict[str, Any]],
    outputs: dict[str, Any],
) -> list[str]:
    if outputs["status"] != "fresh":
        return [f"grid systems: not checked, the grid-system outputs are {outputs['status']}"]
    doc = _read_json(work / "grid-systems.json", "grid-systems.json")
    systems = {s["system_id"]: s for s in doc["systems"]}
    if not systems:
        return ["grid systems: none found in the drawings (no view has a usable grid family)"]
    select = [
        (k, e)
        for k, e in registry["questions"].items()
        if e["code"] == SELECT_CODE and e["producer"] == "grid-system" and e["status"] != "obsolete"
    ]
    answer = next((active[k] for k, _ in select if k in active), None)
    if answer is None:
        ids = ", ".join(e["id"] for _, e in select) or SELECT_CODE
        return [
            f"grid systems: {SELECT_CODE} ({ids}) is not answered: say which systems are the project's grids"
        ]
    used = answer["values"].get("systems") or list(systems)
    reasons = [
        f"grid systems: the {SELECT_CODE} answer names {sid}, which is not in the latest grid-systems.json"
        for sid in used
        if sid not in systems
    ]
    for sid in used:
        axis = systems.get(sid, {}).get("axis_assignment")
        if axis is not None and axis["status"] != "answered":
            reasons.append(
                f"grid systems: {sid} has no Tekla X/Y ({axis['reason']}): answer "
                "grid_family_axis_assignment for its families, then rerun harness grid-system"
            )
    return reasons


def _level_reasons(registry: dict[str, Any], active: dict[str, dict[str, Any]]) -> list[str]:
    return [
        f"levels: {e['id']} {e['code']} ({e['file']}) is not answered"
        for k, e in sorted(registry["questions"].items(), key=lambda kv: _id_number(kv[1]["id"]))
        if e["code"] in LEVEL_CODES and e["status"] != "obsolete" and k not in active
    ]


# --- the document ---------------------------------------------------------------------------------


def build_status(work_dir: str | Path) -> dict[str, Any]:
    """The status document of a work folder. Raises StatusError."""
    work = Path(work_dir).resolve()
    shown = str(work_dir)
    if not work.is_dir():
        raise StatusError(EXIT_USAGE, f"not a work folder (not a folder): {work_dir}")
    missing = [n for n in ("inventory.json", REGISTRY_FILE) if not (work / n).is_file()]
    if missing:
        raise StatusError(
            EXIT_USAGE,
            f"{work_dir} is not a work folder (no {', '.join(missing)}): "
            f"run `harness intake <input_dir> --out {work_dir}`",
        )
    inventory_bytes = (work / "inventory.json").read_bytes()
    inventory = _read_json(work / "inventory.json", "inventory.json")
    problems = validate("intake", inventory)
    if problems or inventory.get("kind") != "inventory":
        raise StatusError(
            EXIT_INVALID, f"inventory.json is invalid: {problems[0].message if problems else 'kind'}"
        )
    try:
        ledger = load_ledger(work, inventory["project_id"], create=False)
    except QuestionsError as exc:
        raise StatusError(exc.exit_code, str(exc)) from exc
    registry, answers = ledger.registry, ledger.answers["answers"]
    active = active_answers(ledger.answers)
    inventory_sha = hashlib.sha256(inventory_bytes).hexdigest()

    producers: list[dict[str, Any]] = []
    for label, producer in PRODUCERS:
        counts, open_ids = _question_counts(registry, active, producer)
        producers.append(
            {
                "producer": label,
                "command": PRODUCER_COMMANDS[producer],
                "questions": counts,
                "blocking_open_ids": open_ids[:MAX_IDS],
                "stale_answers": _stale_answers(answers, registry, producer),
                "outputs": _outputs(work, label, shown, inventory_sha, answers),
            }
        )
    by_label = {p["producer"]: p for p in producers}

    reasons = _units_reasons(inventory, answers)
    reasons += _grid_reasons(work, registry, active, by_label["grid-system"]["outputs"])
    reasons += _level_reasons(registry, active)
    for label in GATE_PRODUCERS:
        q = by_label[label]["questions"]
        if q["blocking_open"]:
            note = (
                f"; {q['blocking_unknown']} of the producer's questions have no recorded blocking flag "
                f"(rerun {by_label[label]['command']}) and count as blocking"
                if q["blocking_unknown"]
                else ""
            )
            reasons.append(
                f"{label}: {q['blocking_open']} blocking question(s) open "
                f"({_ids(by_label[label]['blocking_open_ids'])}){note}"
            )
    for p in producers:
        out = p["outputs"]
        if out["status"] not in ("fresh", "n/a"):
            reasons.append(
                f"{p['producer']}: outputs {out['status']} ({out['reason']}); rerun {out['rerun']}"
            )

    doc = {
        "schema_version": SCHEMA_VERSION,
        "kind": "status",
        "project_id": inventory["project_id"],
        "inventory_sha256": inventory_sha,
        "producers": producers,
        "gate1": {"ready_for_gate1": not reasons, "reasons": reasons},
    }
    issues = validate("status", doc)
    if issues:  # a bug here, not in the work folder
        raise StatusError(
            EXIT_INVALID, f"internal error: status is invalid: {issues[0].path}: {issues[0].message}"
        )
    return doc
