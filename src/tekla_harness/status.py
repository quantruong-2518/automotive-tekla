"""status: where a work folder stands (`harness status <work_dir>`), and whether gate 1 can be opened.

Read-only: nothing is written. Everything is recomputed from the sources of truth, never from the question
documents (they can be stale after `harness answer` or a producer rerun); the one exception is `closed_by`,
read from them only to check a closure a producer wrote (closure_state), so an unreadable question document,
or one its schema refuses, is an error (exit 1):

  * per producer (intake, read-structure, callouts, grid-system, reader): question counts from
    `question-registry.json` + `answers.json` (total, blocking, blocking_open, answered), the stale answers,
    and whether the producer's output documents are `fresh`, `stale` or `missing` with the command that
    fixes it. read-structure, callouts and grid-system record the sha256 of the `inventory.json` they were
    built from (`inventory_sha256`); grid-system also fingerprints the units and axis answers it read
    (`answers_sha256`). Intake's own documents are fresh when they exist (inventory.json is the reference).
  * `gate1.ready_for_gate1`, true only when `reasons` is empty (see schemas/status.schema.json for the
    exact rules): every DXF/DWG intake could not read has a live intake question (read_failed ...) that the
    blocking-question rule below keeps open until the engineer answers it (none at all: a `files:`
    reason); every other probed DXF/DWG has an active answer on its own units_confirm_all question, its unit
    answers agree, and the answered unit is not contradicted by the drawing's dimensions (or that was
    confirmed on the units_answer_contradicts_evidence question); grid systems found, grid_system_select
    answered, every used system axis-assigned (family or system answers) and no conflict between two used
    systems that the select answer does not declare `separate`; level_storey_selection and
    level_finished_vs_structural answered; no blocking question open in intake, read-structure, grid-system
    or reader (the drawing-reader's `harness ask` questions); all outputs fresh (reader: n/a).
    These are checked from the answers' structured values and grid-systems.json, never from an answer's
    words: an answer to a grid_system_conflict question (legacy) does not close it. Every reason names the
    question id to answer.

An entry written to the registry before it recorded the `blocking` flag counts as blocking (never assume a
question is harmless) and is reported in `blocking_unknown`.

Tool wave 2:
  * a question `lifecycle.closures` closes (another answer or selection settles it) leaves the `blocking` and
    `blocking_open` counts and is listed in `gate1.closed` with its reason (tool wave 3, W5: `gate1.closed`
    is always written, [] when nothing is closed), but only when the closure keeps
    the contract (`check_closures`: its reason fits the closed question's producer and code, the question
    is not the reader's, and it names a live question of the code the reason needs, which the engineer
    answered; other_file_set is never accepted). A refused closure leaves the
    question open and is a gate-1 reason (`closures: ...`);
  * an active answer to a live gate-relevant question (producers intake, read-structure, grid-system,
    reader: every question gate 1 reads) that the engineer did not give (`answered_by_role` 'simulated', or
    no role at all: an answer recorded before roles existed) is a gate-1 reason naming its question id and
    is listed in `gate1.non_engineer_answers`. So is a non-engineer active answer whose question is not live
    (no registry entry, or obsolete) when a gate check still reads its code from every active answer (units,
    grid-system: GATE_READ_CODES); its reason names the answer's key. Both lists appear only when not empty.
    Such an answer does not settle its question either (answer_counts): the question stays in
    `blocking_open` / `blocking_open_ids` and out of `answered`, as in questions.md section 2.

Tool wave 3:
  * `gate1.closed` is always written ([] when nothing is closed);
  * an answer to grid_system_missing closes it only from the built result (ADR-0013 decision 6,
    built_grid_answers): the engineer's answer, and a fresh grid-systems.json holding a system built from
    it (`source_answer.key` is the question's key) that the select answer uses. Its values alone close
    nothing; an answer in words only builds nothing either. Such a question stays in `blocking_open` and a
    `grid systems:` reason says what closes it: the values, valid values, or selecting the system again;
  * who answered is part of the grid-system answers fingerprint (consumed_answers_digest), and every used
    system needs `units.status` confirmed and, once its units and X/Y are, a `tekla_grid`.

Exit codes (AGENTS.md): 0 for any readable work folder (status is information, not a verdict), 1 an
unreadable or invalid document, 2 not a work folder.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tekla_harness import lifecycle
from tekla_harness.grid_system import (
    CONSUMED_CODES,
    consumed_answers_digest,
    units_by_file,
    units_evidence,
)
from tekla_harness.questions import (
    CLOSURE_REASONS,
    CONFLICT_CODE,
    CONTRADICTION_CODE,
    FILE_SET_CODE,
    GRID_ANSWER_KEYS,
    GRID_ANSWER_SHEET_KEY,
    GRID_MISSING_CODE,
    PRODUCER_COMMANDS,
    QUESTION_DOCUMENTS,
    REGISTRY_FILE,
    SELECT_CODE,
    UNIT_CODES,
    UNITS,
    UNITS_CONFIRM_CODE,
    Closure,
    Ledger,
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
# intake's blocking questions about a drawing file it could not read (intake._failure_groups,
# _conversion_groups); such a file has no units row (_unreadable_reasons)
UNREADABLE = "unreadable"
READ_FAILURE_CODES = ("read_failed", "conversion_empty", "no_reader_implemented")
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
# their registry producers: an answer to one of their questions must be the engineer's
GATE_ANSWER_PRODUCERS = frozenset(dict(PRODUCERS)[label] for label in GATE_PRODUCERS)
# An answer recorded without answered_by_role (before roles existed) does not count as the engineer's: the
# engineer answers it again with --role engineer (DESIGN D4). Kept as a named constant so the rule is visible.
LEGACY_ANSWER_IS_ENGINEER = False
# an answer to these never closes them: they close through another question's structured values
NOT_CLOSED_BY_AN_ANSWER = frozenset({CONFLICT_CODE})
# an answer to these closes them only with its structured values: an answer in words only builds nothing, so
# the file still has no usable grid system (ADR-0013 decision 2, even when the engineer gave it)
VALUES_NEEDED_TO_CLOSE = frozenset({GRID_MISSING_CODE})
# an answer to these closes them only from the built result, never from its values alone (ADR-0013 decision
# 6): a fresh grid-systems.json holds a USED system built from it (built_grid_answers)
CLOSED_BY_THE_BUILT_GRID = frozenset({GRID_MISSING_CODE})
GRID_SYSTEMS_FILE = "grid-systems.json"
# codes a gate check reads from every active answer, whatever its question's registry state: units_by_file
# (units) and harness grid-system (CONSUMED_CODES). A non-engineer answer of these to a question that is not
# live is a gate-1 reason too (_retired_answers)
GATE_READ_CODES = UNIT_CODES | CONSUMED_CODES
# closure contract (check_closures): units_answered closes this read-structure code only, and
# rejected_systems_only closes read-structure codes of this prefix only (grids.py, refs with `families`)
UNITS_DOUBT_CODE = "grid_units_doubt"
GRID_FAMILY_PREFIX = "grid_"
# confirming the grids stays a gate-1 step: dropping it is the engineer's decision (DESIGN, "NOT taken")
NOT_REJECTABLE = frozenset({"grid_gate1_confirmation"})
# the code of the question whose engineer answer a closure of each reason must name (check_closures)
CLOSER_CODES = {
    "not_selected": SELECT_CODE,
    "separate": SELECT_CODE,
    "rejected_systems_only": SELECT_CODE,
    "units_answered": UNITS_CONFIRM_CODE,
}
# A printed answer command is the ENGINEER's step, never an agent's (review M1): it is always introduced by
# ENGINEER_STEP and names `--role engineer` once, after --by (gate 1 counts the engineer's answers only).
ENGINEER_STEP = "the engineer runs: "
ANSWER = ENGINEER_STEP + 'harness answer {work_dir} {id} --text "..." --by "..." --role engineer'


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


def answer_counts(producer: str, answer: dict[str, Any] | None) -> bool:
    """An active answer counts for its question when the question's (registry) producer is not read by gate 1,
    or when the engineer gave it: a simulated or role-less answer to a gate producer's question leaves the
    question open (the same rule in `harness status` and questions.md)."""
    if answer is None:
        return False
    return producer not in GATE_ANSWER_PRODUCERS or _by_engineer(answer)


def words_only(code: str, answer: dict[str, Any] | None) -> bool:
    """An answer without values to a code whose answer must carry them (VALUES_NEEDED_TO_CLOSE): it is
    recorded but builds nothing, so it does not close its question."""
    return answer is not None and code in VALUES_NEEDED_TO_CLOSE and not answer["values"]


def answer_closes(
    producer: str, code: str, answer: dict[str, Any] | None, built: frozenset[str] = frozenset()
) -> bool:
    """The answer takes its question out of the open ones: it counts (answer_counts), the code is one an
    answer closes (an answer to a grid_system_conflict question never does), and, for a code closed by the
    built result (CLOSED_BY_THE_BUILT_GRID: grid_system_missing), its key is in `built`: the keys whose
    answer built a used system in a fresh grid-systems.json (built_grid_answers). A grid_system_missing
    answer's values alone never close it (ADR-0013 decision 6), words only even less."""
    if answer is None or not answer_counts(producer, answer) or code in NOT_CLOSED_BY_AN_ANSWER:
        return False
    if code in CLOSED_BY_THE_BUILT_GRID:
        return answer.get("key") in built
    return True


def _question_counts(
    registry: dict[str, Any],
    active: dict[str, dict[str, Any]],
    producer: str,
    closed: frozenset[str],
    forced: frozenset[str] = frozenset(),
    built: frozenset[str] = frozenset(),
) -> tuple[dict[str, int], list[str]]:
    """`closed`: keys of the accepted closures; they block nothing. `forced`: non-blocking questions whose
    written closure was refused; they count as blocking (closure_state). `built`: see answer_closes."""
    entries = {k: e for k, e in registry["questions"].items() if e["producer"] == producer}
    live = {k: e for k, e in entries.items() if e["status"] != "obsolete"}
    blocking = {k: e for k, e in live.items() if (e.get("blocking", True) or k in forced) and k not in closed}
    open_ids = sorted(
        (
            e["id"]
            for k, e in blocking.items()
            if not answer_closes(producer, e["code"], active.get(k), built)
        ),
        key=_id_number,
    )
    counts = {
        "total": len(live),
        "blocking": len(blocking),
        "blocking_unknown": sum(1 for e in live.values() if "blocking" not in e),
        "blocking_open": len(open_ids),
        "answered": sum(1 for k in live if answer_counts(producer, active.get(k))),
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
            reason = "grid-systems.json was built before the latest answers it reads (units, axes, selection)"
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


def _live(registry: dict[str, Any], code: str) -> dict[str | None, tuple[str, dict[str, Any]]]:
    """file -> (key, entry) of the non-obsolete registry entries of a code (the latest one per file)."""
    out: dict[str | None, tuple[str, dict[str, Any]]] = {}
    for k, e in sorted(registry["questions"].items(), key=lambda kv: _id_number(kv[1]["id"])):
        if e["code"] == code and e["status"] != "obsolete":
            out[e["file"]] = (k, e)
    return out


def _spacing_medians(work: Path, inventory_sha: str) -> dict[str, dict[str, Any] | None]:
    """file -> median grid spacing (drawing units) recorded by `harness grid-system`; empty when
    grid-systems.json is absent, unreadable or built from another inventory (the outputs check says so)."""
    path = work / "grid-systems.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(doc, dict) or doc.get("inventory_sha256") != inventory_sha:
        return {}
    return {
        f["path"]: f.get("grid_spacing_median")
        for f in doc.get("files", [])
        if isinstance(f, dict) and isinstance(f.get("path"), str)
    }


def _drawing_rows(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in inventory["files"] if r["format"] in ("dwg", "dxf")]


def _unreadable_reasons(inventory: dict[str, Any], registry: dict[str, Any]) -> list[str]:
    """A DXF/DWG that intake could not read (outcome unreadable, or no probe) has no units row: it stays a
    gate-1 reason through its own blocking intake question (READ_FAILURE_CODES) until the engineer answers
    it. Fail closed: when no live intake question of those codes names the file, the file is a reason of
    its own."""
    asked = {
        e["file"]
        for e in registry["questions"].values()
        if e["producer"] == "intake" and e["code"] in READ_FAILURE_CODES and e["status"] != "obsolete"
    }
    return [
        f"files: {r['path']} is unreadable and no live intake question ({', '.join(READ_FAILURE_CODES)}) "
        "names it: rerun harness intake"
        for r in _drawing_rows(inventory)
        if (r["outcome"] == UNREADABLE or r["probe"] is None) and r["path"] not in asked
    ]


def _units_reasons(
    inventory: dict[str, Any],
    registry: dict[str, Any],
    active: dict[str, dict[str, Any]],
    answers: list[dict[str, Any]],
    spacing_medians: dict[str, dict[str, Any] | None],
    work_dir: str,
) -> list[str]:
    """Per probed DXF/DWG intake could read (an unreadable one: _unreadable_reasons): its units_confirm_all
    answered with a unit, unit answers that agree, and an answered unit the drawing's dimensions and grid
    spacings do not contradict (units_suspect test, grid plausibility range) unless confirmed on purpose.
    `answers`: every answer of answers.json; only the active ones count."""
    rows = {
        r["path"]: r
        for r in _drawing_rows(inventory)
        if r["probe"] is not None and r["outcome"] != UNREADABLE
    }
    current = [a for a in answers if a["status"] == "active"]
    statuses = units_by_file(current, list(rows), [])
    confirm, contra = _live(registry, UNITS_CONFIRM_CODE), _live(registry, CONTRADICTION_CODE)
    values = "--value unit=" + "|".join(UNITS)
    reasons = []
    for f, row in rows.items():
        status, unit = statuses[f]
        hit = confirm.get(f)
        command = (
            ANSWER.format(work_dir=work_dir, id=hit[1]["id"])
            if hit
            else f"{ENGINEER_STEP}harness answer {work_dir} <{UNITS_CONFIRM_CODE} id>"
        )
        if hit is not None and hit[0] not in active:
            reasons.append(f"units: {f} is not confirmed: {command} {values} ({UNITS_CONFIRM_CODE})")
            continue
        if status == "not_answered":
            reasons.append(
                f"units: {f} has no active units answer and no open {UNITS_CONFIRM_CODE} question: rerun "
                "harness intake"
            )
        elif status == "disagree":
            ids = sorted(
                {a["question_id"] for a in current if a["code"] in UNIT_CODES and a["file"] in (f, None)}
            )
            reasons.append(
                f"units: {f} has active units answers that disagree ({', '.join(ids)}): the engineer answers "
                f"them with one unit ({command} {values})"
            )
        elif status == "invalid":
            reasons.append(f"units: {f} has a units answer without a valid unit: {command} {values}")
        elif unit is not None:
            units_row = row["units"] or {}
            if row["units"] is not None and "dimension_median" not in units_row:
                reasons.append(
                    f"units: {f}: inventory.json has no dimension_median (built by an older intake), so the "
                    f"answered unit {unit} cannot be tested against the drawing: rerun harness intake"
                )
                continue
            evidence = units_evidence(units_row.get("dimension_median"), spacing_medians.get(f), unit)
            if evidence is None:
                continue
            c = contra.get(f)
            if c is not None and c[0] in active and active[c[0]]["values"].get("unit") == unit:
                continue  # the engineer confirmed this unit against the evidence, on purpose
            where = (
                f"{ANSWER.format(work_dir=work_dir, id=c[1]['id'])} --value unit={unit} "
                f"({CONTRADICTION_CODE})"
                if c is not None
                else f"the {CONTRADICTION_CODE} question that harness grid-system raises (rerun it)"
            )
            again = hit[1]["id"] if hit else UNITS_CONFIRM_CODE
            reasons.append(
                f"units: {f}: the answered unit {unit} contradicts the drawing ({evidence}): the engineer "
                f"answers {again} again with the right unit, or confirms {unit} on purpose ({where})"
            )
    return reasons


def _select_answer(
    registry: dict[str, Any], active: dict[str, dict[str, Any]]
) -> tuple[list[tuple[str, dict[str, Any]]], dict[str, Any] | None]:
    """The live grid_system_select questions (key, entry) and the first active answer to one of them."""
    select = [
        (k, e)
        for k, e in registry["questions"].items()
        if e["code"] == SELECT_CODE and e["producer"] == "grid-system" and e["status"] != "obsolete"
    ]
    return select, next((active[k] for k, _ in select if k in active), None)


def _select_command(select: list[tuple[str, dict[str, Any]]], work_dir: str) -> str:
    """A command names one question: the latest select question (an answer to any live one is read)."""
    return ANSWER.format(
        work_dir=work_dir,
        id=max((e["id"] for _, e in select), key=_id_number) if select else f"<{SELECT_CODE} id>",
    )


def _used(answer: dict[str, Any] | None, system_ids: list[str]) -> list[str]:
    """The systems the select answer uses: its systems= value, else every system."""
    chosen = answer["values"].get("systems") if answer is not None else None
    return list(chosen) if chosen else list(system_ids)


def _built_answers(
    work: Path,
    registry: dict[str, Any],
    active: dict[str, dict[str, Any]],
    answers: list[dict[str, Any]],
    inventory_sha: str,
) -> dict[str, tuple[str, bool]] | None:
    """grid_system_missing key -> (id of the system built from its answer, whether the select answer uses
    it), from grid-systems.json; None when that document is absent, unreadable, or not fresh (built from
    another inventory or before the latest answers it reads: then it shows nothing that is current, and the
    outputs check says so)."""
    try:
        doc = json.loads((work / GRID_SYSTEMS_FILE).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if (
        not isinstance(doc, dict)
        or doc.get("inventory_sha256") != inventory_sha
        or doc.get("answers_sha256") != consumed_answers_digest(answers)
    ):
        return None
    systems = [s for s in doc.get("systems") or [] if isinstance(s, dict)]
    used = set(_used(_select_answer(registry, active)[1], [str(s.get("system_id")) for s in systems]))
    return {
        str(s["source_answer"]["key"]): (str(s["system_id"]), s["system_id"] in used)
        for s in systems
        if s.get("source") == "engineer_answer" and isinstance(s.get("source_answer"), dict)
    }


def _closing(built: dict[str, tuple[str, bool]] | None) -> frozenset[str]:
    return frozenset(k for k, (_, used) in (built or {}).items() if used)


def built_grid_answers(work: Path, ledger: Ledger) -> frozenset[str]:
    """The grid_system_missing keys a fresh grid-systems.json holds a USED system built from (ADR-0013
    decisions 1 and 6): the only grid_system_missing questions an answer closes (answer_closes). Used by
    `harness status` and questions-md."""
    try:
        inventory_sha = hashlib.sha256((work / "inventory.json").read_bytes()).hexdigest()
    except OSError:
        return frozenset()
    built = _built_answers(
        work, ledger.registry, active_answers(ledger.answers), ledger.answers["answers"], inventory_sha
    )
    return _closing(built)


def _grid_reasons(
    work: Path,
    registry: dict[str, Any],
    active: dict[str, dict[str, Any]],
    outputs: dict[str, Any],
    work_dir: str,
) -> list[str]:
    if outputs["status"] != "fresh":
        return [f"grid systems: not checked, the grid-system outputs are {outputs['status']}"]
    doc = _read_json(work / GRID_SYSTEMS_FILE, GRID_SYSTEMS_FILE)
    systems = {s["system_id"]: s for s in doc["systems"]}
    if not systems:
        return ["grid systems: none found in the drawings (no view has a usable grid family)"]
    select, answer = _select_answer(registry, active)
    select_ids = ", ".join(e["id"] for _, e in select) or SELECT_CODE
    select_command = _select_command(select, work_dir)
    if answer is None:
        return [
            f"grid systems: {SELECT_CODE} ({select_ids}) is not answered: the engineer says which systems "
            f"are the project's grids ({select_command} [--value systems=S001,S002])"
        ]
    used = _used(answer, list(systems))
    separate = set(answer["values"].get("separate") or [])
    id_of = {k: e["id"] for k, e in registry["questions"].items() if e["status"] != "obsolete"}
    reasons = [
        f"grid systems: the {SELECT_CODE} answer names {sid}, which is not in the latest grid-systems.json"
        for sid in [*used, *sorted(separate)]
        if sid not in systems
    ]
    for sid in used:
        system = systems.get(sid)
        if system is None:
            continue
        axis = system["axis_assignment"]
        if axis["status"] != "answered":
            qid = id_of.get(system.get("axis_question_key") or "")
            names = ["dir1", "dir2"][: len(system["directions"])]
            how = (
                f"{ANSWER.format(work_dir=work_dir, id=qid)} " + " ".join(f"--value {n}=X|Y" for n in names)
                if qid
                else f"the engineer answers the grid_system_axis_unassigned question of {sid}"
            )
            reasons.append(
                f"grid systems: {sid} has no Tekla X/Y ({axis['reason']}): {how} (or the engineer answers "
                "grid_family_axis_assignment per family), then rerun harness grid-system"
            )
        units = system["units"]
        if units["status"] != "confirmed":  # proposed_simulated or not_confirmed: nothing converted
            reasons.append(
                f"grid systems: {sid} units are {units['status']} ({units['reason']}): the engineer answers "
                f"the {UNITS_CONFIRM_CODE} question of each of its files (--value unit=...), then rerun "
                "harness grid-system"
            )
        elif axis["status"] == "answered" and system.get("tekla_grid") is None:
            # fail closed: units and X/Y read as confirmed, but no Tekla grid was written
            reasons.append(
                f"grid systems: {sid} has no Tekla grid (tekla_grid is null although its units and X/Y are "
                "confirmed): rerun harness grid-system"
            )
    # an unanswered live file_set_relation question: a conflict grid-system left non-blocking without a
    # closure is pending on it (the two systems may be separate projects), so it is the question to answer
    file_set = max(
        (e["id"] for k, e in _live(registry, FILE_SET_CODE).values() if k not in active),
        key=_id_number,
        default=None,
    )
    for c in doc.get("conflicts", []):
        a, b = c["systems"]
        if a not in used or b not in used or {a, b} <= separate:
            continue
        qid = id_of.get(c["question_key"] or "") or CONFLICT_CODE
        if file_set is not None and not c["blocking"] and c["closed_by"] is None:
            reasons.append(
                f"grid systems: {a} and {b} conflict ({qid}) across drawing files, pending {file_set} "
                f"({FILE_SET_CODE}): the engineer says which files form one set first "
                f"({ANSWER.format(work_dir=work_dir, id=file_set)} --value set1=<file>,<file> "
                "[--value set2=...]), then rerun harness grid-system"
            )
            continue
        reasons.append(
            f"grid systems: {a} and {b} conflict ({qid}); an answer to it closes nothing: the engineer "
            f"answers {SELECT_CODE} ({select_ids}) again with systems= leaving one of them out, or with "
            f"separate={a},{b} if they are different buildings ({select_command} --value systems=... "
            f"[--value separate={a},{b}]), then rerun harness grid-system"
        )
    return reasons


def _non_engineer_answers(
    registry: dict[str, Any], active: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Active answers to live gate-relevant questions that the engineer did not give, by question id."""
    out = []
    for key, answer in active.items():
        entry = registry["questions"].get(key)
        if entry is None or entry["status"] == "obsolete" or entry["producer"] not in GATE_ANSWER_PRODUCERS:
            continue
        if _by_engineer(answer):
            continue
        out.append(
            {
                "question_id": entry["id"],
                "code": entry["code"],
                "file": entry["file"],
                "role": answer.get("answered_by_role"),
            }
        )
    return sorted(out, key=lambda a: _id_number(a["question_id"]))


def _retired_answers(registry: dict[str, Any], active: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Active answers whose question is not live (no registry entry, or obsolete) but whose code a gate check
    still reads from every active answer (units_by_file, grid-system), that the engineer did not give. Each
    keeps its key (`key`) and why it is retired (`retired`); sorted by key."""
    out = []
    for key, answer in sorted(active.items()):
        entry = registry["questions"].get(key)
        if entry is not None and entry["status"] != "obsolete":
            continue
        if answer["code"] not in GATE_READ_CODES or _by_engineer(answer):
            continue
        out.append(
            {
                "question_id": answer["question_id"],
                "code": answer["code"],
                "file": answer["file"],
                "role": answer.get("answered_by_role"),
                "key": key,
                "retired": "not in the registry" if entry is None else "obsolete",
            }
        )
    return out


# what clears a retired answer: a rerun marks an answer to an obsolete question stale (questions.Ledger.sync),
# but nothing in the harness retires an answer whose key no registry entry has
RETIRED_REMEDY = {
    "obsolete": "rerun the command that raises this code (the answer goes stale), then the engineer answers "
    "the live question themselves",
    "not in the registry": "no harness command retires this answer (no question has its key): the engineer "
    "decides what to do with answers.json",
}


def _retired_reasons(retired: list[dict[str, Any]]) -> list[str]:
    return [
        f"answers: {a['question_id']} {a['code']} ({a['file'] or 'project'}), answer key {a['key']}, was "
        f"answered by {'a ' + a['role'] + ' role' if a['role'] else 'no recorded role'}, not the engineer, "
        f"and its question is {a['retired']}; gate checks still read it, so gate 1 does not count it: "
        f"{RETIRED_REMEDY[a['retired']]}"
        for a in retired
    ]


def _by_engineer(answer: dict[str, Any]) -> bool:
    role = answer.get("answered_by_role")
    return role == "engineer" or (role is None and LEGACY_ANSWER_IS_ENGINEER)


def _closure_fits(reason: str, entry: dict[str, Any]) -> bool:
    """The closure contract (DESIGN §1 5a-5d): which reason may close which producer's code."""
    producer, code = entry["producer"], entry["code"]
    if reason in ("not_selected", "separate"):  # 5a: a grid-system conflict
        return producer == "grid-system" and code == CONFLICT_CODE
    # other_file_set (5d) closes nothing: lifecycle never derives it (a cross-set conflict is not raised at
    # all once the file sets are answered), so a closure claiming it fails closed
    if reason == "units_answered":  # 5c
        return producer == "structure" and code == UNITS_DOUBT_CODE
    if reason == "rejected_systems_only":  # 5b: a read-structure question citing grid families
        return producer == "structure" and code.startswith(GRID_FAMILY_PREFIX) and code not in NOT_REJECTABLE
    return False


def check_closures(
    registry: dict[str, Any], active: dict[str, dict[str, Any]], closures: dict[str, Closure]
) -> tuple[dict[str, Closure], list[str]]:
    """The closures gate 1 accepts, and a gate-1 reason per refused one (review M2). A closure is accepted
    only when its reason fits the closed question (`_closure_fits`), the question is not the reader's (a
    reader question closes only through its own answer), and it names a live question of the code the reason
    needs (CLOSER_CODES) with an active answer the engineer gave. other_file_set is never accepted (nothing
    derives it yet). A refused closure leaves its question open and blocking as before. Closures of keys
    that are unknown or obsolete in the registry are ignored (they block nothing either way)."""
    entries = registry["questions"]
    accepted: dict[str, Closure] = {}
    refused: list[tuple[str, str]] = []
    for key, c in closures.items():
        entry = entries.get(key)
        if entry is None or entry["status"] == "obsolete":
            continue
        why = _refusal(registry, active, entry, c.question_id, c.reason)
        if why is None:
            accepted[key] = c
            continue
        refused.append((entry["id"], _refusal_reason(entry, c.question_id, c.reason, why, written=False)))
    return accepted, [r for _, r in sorted(refused, key=lambda row: _id_number(row[0]))]


def _refusal(
    registry: dict[str, Any],
    active: dict[str, dict[str, Any]],
    entry: dict[str, Any],
    question_id: str | None,
    reason: str,
) -> str | None:
    """Why a closure of `entry` (named closer, reason) breaks the contract; None when it keeps it."""
    closer = next(
        (
            (k, e)
            for k, e in registry["questions"].items()
            if e["id"] == question_id and question_id is not None
        ),
        None,
    )
    if reason not in CLOSURE_REASONS:
        return f"unknown closure reason '{reason}'"
    if entry["producer"] == "reader":
        return "a reader question closes only through its own answer"
    if not _closure_fits(reason, entry):
        return f"{reason} cannot close a {entry['producer']} {entry['code']} question"
    if question_id is None:
        return "it names no question whose answer closes it"
    if closer is None or closer[1]["status"] == "obsolete":
        return f"{question_id} is not a live question"
    if closer[1]["code"] != CLOSER_CODES[reason]:
        return f"{question_id} is not a {CLOSER_CODES[reason]} question"
    if closer[0] not in active:
        return f"{question_id} has no active answer"
    if not _by_engineer(active[closer[0]]):
        return f"{question_id} was not answered by the engineer"
    return None


def _refusal_reason(
    entry: dict[str, Any], question_id: str | None, reason: str, why: str, *, written: bool
) -> str:
    by = f" by {question_id}" if question_id else ""
    state, what = ("stays blocking", "written closure") if written else ("stays open", "closure")
    return (
        f"closures: {entry['id']} {entry['code']} ({entry['file'] or 'project'}) {state}: the {what} "
        f"{reason}{by} is refused ({why})"
    )


def _written_closures(work: Path, registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """key -> `closed_by` of the live questions a producer already wrote as closed: non-blocking in the
    registry and carrying `closed_by` in its question document (grid-system writes these for a conflict the
    select answer settles). Read-only; an unreadable document, or one its schema (intake, kind questions)
    refuses, is an error (exit 1)."""
    out: dict[str, dict[str, Any]] = {}
    for name in QUESTION_DOCUMENTS:
        if not (work / name).is_file():
            continue
        doc = _read_json(work / name, name)
        problems = validate("intake", doc)
        if problems or not isinstance(doc, dict) or doc.get("kind") != "questions":
            why = f"{problems[0].path}: {problems[0].message}" if problems else "kind is not 'questions'"
            raise StatusError(EXIT_INVALID, f"{name} is invalid (intake schema): {why}")
        for q in doc["questions"]:
            if not isinstance(q.get("closed_by"), dict):
                continue
            entry = registry["questions"].get(q.get("key"))
            if entry is not None and entry["status"] != "obsolete" and entry.get("blocking", True) is False:
                out[q["key"]] = q["closed_by"]
    return out


@dataclass(frozen=True)
class ClosureState:
    """What gate 1 treats as closed (`accepted`), the non-blocking questions whose written closure breaks the
    contract and so count as blocking (`forced`), and a gate-1 reason per refusal (`reasons`)."""

    accepted: dict[str, Closure]
    forced: frozenset[str]
    reasons: list[str]


def closure_state(work: Path, ledger: Ledger) -> ClosureState:
    """`lifecycle.closures` and the closures producers wrote (blocking false + closed_by), both checked
    against the closure contract (`check_closures`, `_refusal`). Used by `harness status` and questions-md."""
    registry, active = ledger.registry, active_answers(ledger.answers)
    accepted, reasons = check_closures(registry, active, lifecycle.closures(work, ledger))
    forced: set[str] = set()
    written_reasons: list[tuple[str, str]] = []
    for key, closed_by in _written_closures(work, registry).items():
        entry = registry["questions"][key]
        qid, reason = closed_by.get("question_id"), str(closed_by.get("reason"))
        why = _refusal(registry, active, entry, qid, reason)
        if why is not None:
            forced.add(key)
            written_reasons.append((entry["id"], _refusal_reason(entry, qid, reason, why, written=True)))
    accepted = {k: c for k, c in accepted.items() if k not in forced}
    reasons += [r for _, r in sorted(written_reasons, key=lambda row: _id_number(row[0]))]
    return ClosureState(accepted, frozenset(forced), reasons)


def accepted_closures(work: Path, ledger: Ledger) -> dict[str, Closure]:
    """The closures `harness status` and questions.md treat as closed (closure_state)."""
    return closure_state(work, ledger).accepted


def _role_reasons(non_engineer: list[dict[str, Any]], work_dir: str) -> list[str]:
    return [
        f"answers: {a['question_id']} {a['code']} ({a['file'] or 'project'}) was answered by "
        f"{'a ' + a['role'] + ' role' if a['role'] else 'no recorded role'}, not the engineer: the engineer "
        "must answer it again themselves; an agent never does "
        f"({ANSWER.format(work_dir=work_dir, id=a['question_id'])})"
        for a in non_engineer
    ]


def _grid_missing_reasons(
    registry: dict[str, Any],
    active: dict[str, dict[str, Any]],
    built: dict[str, tuple[str, bool]] | None,
    work_dir: str,
) -> list[str]:
    """A live grid_system_missing question whose ENGINEER answer does not close it (answer_closes), with
    the step that does: an answer in words only (VALUES_NEEDED_TO_CLOSE) builds nothing; with values, the
    fresh grid-systems.json (`built`, see _built_answers) built no system from it, or the select answer
    leaves that system out. While grid-systems.json is not fresh, the outputs reason asks for the rerun. A
    non-engineer answer is already a reason of its own (_role_reasons)."""
    values = " ".join(f"--value {k}=<{k.split('_')[1][:-1]}>,..." for k in GRID_ANSWER_KEYS)
    reasons = []
    for k, e in sorted(registry["questions"].items(), key=lambda kv: _id_number(kv[1]["id"])):
        if (
            e["status"] == "obsolete"
            or e["code"] not in CLOSED_BY_THE_BUILT_GRID
            or e["producer"] not in GATE_ANSWER_PRODUCERS
            or k not in active
            or not _by_engineer(active[k])
            or answer_closes(e["producer"], e["code"], active[k], _closing(built))
        ):
            continue
        head = f"grid systems: {e['id']} {e['code']} ({e['file'] or 'project'})"
        command = (
            f"{ANSWER.format(work_dir=work_dir, id=e['id'])} {values} "
            f"[--value {GRID_ANSWER_SHEET_KEY}=<sheet id>]"
        )
        if words_only(e["code"], active[k]):
            reasons.append(
                f"{head} was answered in words only, which builds no grid system, so the question stays "
                f"open: the engineer gives the grid ({command}), then rerun harness grid-system"
            )
        elif built is not None and k in built:
            sid = built[k][0]
            select, _ = _select_answer(registry, active)
            reasons.append(
                f"{head}: {sid}, built from its answer, is left out by the {SELECT_CODE} answer, so the file "
                "has no used grid system and the question stays open: the engineer selects it again "
                f"({_select_command(select, work_dir)} --value systems=...,{sid}) or answers {e['id']} "
                "again, then rerun harness grid-system"
            )
        elif built is not None:
            reasons.append(
                f"{head} was answered with grid values, but the latest grid-systems.json built no grid "
                "system from them (harness grid-system warns why), so the question stays open: the engineer "
                f"answers again with valid values ({command}), then rerun harness grid-system"
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
    try:
        state = closure_state(work, ledger)
    except QuestionsError as exc:  # lifecycle: an unreadable or invalid document it reads
        raise StatusError(exc.exit_code, str(exc)) from exc
    closures, refused_closures = state.accepted, state.reasons
    closed_keys = frozenset(closures)
    built = _built_answers(work, registry, active, answers, inventory_sha)

    producers: list[dict[str, Any]] = []
    for label, producer in PRODUCERS:
        counts, open_ids = _question_counts(
            registry, active, producer, closed_keys, state.forced, _closing(built)
        )
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

    reasons = _units_reasons(
        inventory, registry, active, answers, _spacing_medians(work, inventory_sha), shown
    )
    reasons += _unreadable_reasons(inventory, registry)
    reasons += _grid_reasons(work, registry, active, by_label["grid-system"]["outputs"], shown)
    reasons += _grid_missing_reasons(registry, active, built, shown)
    reasons += _level_reasons(registry, active)
    non_engineer = _non_engineer_answers(registry, active)
    reasons += _role_reasons(non_engineer, shown)
    retired = _retired_answers(registry, active)
    reasons += _retired_reasons(retired)
    non_engineer += [{k: a[k] for k in ("question_id", "code", "file", "role")} for a in retired]
    reasons += refused_closures
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

    entries = registry["questions"]
    # always written, [] when nothing is closed (tool wave 3, W5)
    closed = sorted(
        (
            {
                "id": entries[k]["id"],
                "reason": c.reason,
                **({"question_id": c.question_id} if c.question_id else {}),
            }
            for k, c in closures.items()
            if k in entries and entries[k]["status"] != "obsolete"
        ),
        key=lambda row: _id_number(row["id"]),
    )
    gate1: dict[str, Any] = {"ready_for_gate1": not reasons, "reasons": reasons, "closed": closed}
    if non_engineer:
        gate1["non_engineer_answers"] = non_engineer
    doc = {
        "schema_version": SCHEMA_VERSION,
        "kind": "status",
        "project_id": inventory["project_id"],
        "inventory_sha256": inventory_sha,
        "producers": producers,
        "gate1": gate1,
    }
    issues = validate("status", doc)
    if issues:  # a bug here, not in the work folder
        raise StatusError(
            EXIT_INVALID, f"internal error: status is invalid: {issues[0].path}: {issues[0].message}"
        )
    return doc
