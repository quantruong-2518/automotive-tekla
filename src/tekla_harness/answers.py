"""answers: record an engineer's answer to a question (`harness answer`).

An answer is the highest-trust provenance (common.schema.json method 'engineer_answer', question_id). It is
bound to the question's stable key (questions.py), stored verbatim in `answers.json`, and shown in the
`answer` field of every question document. This module is meant to be run by the engineer, or on the
engineer's explicit instruction with the engineer's own words. An agent must never invent an answer.

Rules:
  * the question id must exist in `question-registry.json` and must not be obsolete;
  * the question's file must not have changed since the question was raised: the registry records the
    file's sha256 at question time (`file_sha256`); when the current `inventory.json` has another sha256
    for that file (or no longer lists it) the answer is refused (exit 1) and the producer that raised the
    question must be rerun. Project-level questions, entries without a recorded sha256 and a work folder
    without `inventory.json` are not checked;
  * `answer_text` (verbatim) and `answered_by` must not be blank;
  * structured `values` exist for some codes only (see answers.schema.json):
        units_confirm_all, units_conflict, units_suspect, units_unknown, grid_units_doubt
                                      unit=mm|cm|m|in|ft            (required)
        units_answer_contradicts_evidence
                                      unit=<the unit already answered for the file>   (required: confirms
                                      that unit on purpose; to change it, answer units_confirm_all again)
        grid_family_axis_assignment   <family_id>=X|Y               (at least one)
        grid_system_axis_unassigned   dir1=X|Y, dir2=X|Y            (exactly the directions the question
                                      lists in `subjects`, distinct axes)
        member_mark_prefix_meaning    <prefix>=<meaning>            (at least one)
        file_set_relation             set1=a.dwg,b.dwg set2=c.dwg   (at least one set; every file the
                                      question's refs list (their `file`) exactly once, no other file)
        grid_system_select            systems=S001,S002             (optional: the grid systems the project
                                      uses; without it `harness status` takes every listed system as used)
                                      separate=S001,S002            (optional: two or more systems of the
                                      question, all selected, that are different buildings)
    every other code takes no value;
  * grid_system_conflict cannot be answered: a conflict closes only through the grid_system_select answer
    (`systems` without one of the two, or `separate` with both), never through words;
  * `role` (`answered_by_role`): 'engineer' or 'simulated' (an agent standing in for the engineer); gate 1
    counts the engineer's answers only (status.py). Required (`harness answer --role`, and the keyword
    `role` of record_answer, which has no default): every new answer records its role. Any other role,
    None included, is a usage error. An answer recorded before roles existed has none; gate 1 does not
    count it;
  * a second answer to the same key supersedes the first (kept, status 'superseded');
  * nothing is deleted: answers are only appended or change status.

The question documents already on disk (questions.json, structure-questions.json, callouts-questions.json)
are refreshed with the new answer and their summary, so `blocking_open` is right without a rerun. A
document that is invalid is left alone and reported in `not_refreshed`.

Exit codes (AGENTS.md): 1 invalid structured values, inconsistent documents or a question whose file has
changed, 2 usage (unknown or obsolete id, blank text or name, bad `--value`, no registry).
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from tekla_harness.questions import (
    AXIS_CODE,
    AXIS_DIRECTIONS,
    CONFLICT_CODE,
    CONTRADICTION_CODE,
    EXIT_INVALID,
    EXIT_USAGE,
    FILE_SET_CODE,
    FILE_SET_KEY,
    PREFIX_CODE,
    PRODUCER_COMMANDS,
    QUESTION_DOCUMENTS,
    ROLES,
    SELECT_CODE,
    SYSTEM_AXIS_CODE,
    UNIT_CODES,
    UNITS,
    Ledger,
    QuestionsError,
    active_answers,
    dump_json,
    load_ledger,
    questions_summary,
    write_text_atomic,
)
from tekla_harness.schemas import validate

AXES = ("X", "Y")


def parse_values(items: list[str]) -> dict[str, str]:
    """`--value k=v` options to a dict. A repeated key or a missing '=' is a usage error."""
    values: dict[str, str] = {}
    for item in items:
        name, sep, value = item.partition("=")
        if not sep or not name.strip():
            raise QuestionsError(EXIT_USAGE, f"--value '{item}': expected key=value")
        if name in values:
            raise QuestionsError(EXIT_USAGE, f"--value '{name}' given twice")
        values[name] = value
    return values


SYSTEM_ID = re.compile(r"S[0-9]{3,}")


def check_values(code: str, values: dict[str, str]) -> list[str]:
    """Problems with the structured values of an answer to a question with this code (empty when fine)."""
    if code in UNIT_CODES or code == CONTRADICTION_CODE:
        if set(values) != {"unit"}:
            return ["this question needs exactly one value: unit=" + "|".join(UNITS)]
        return (
            [] if values["unit"] in UNITS else [f"unit '{values['unit']}' is not one of {', '.join(UNITS)}"]
        )
    if code == AXIS_CODE:
        if not values:
            return ["this question needs at least one value: <family_id>=X|Y"]
        return [f"family '{k}': '{v}' is not X or Y" for k, v in values.items() if v not in AXES]
    if code == SYSTEM_AXIS_CODE:
        if not values:
            return ["this question needs a value per direction: dir1=X|Y (and dir2=X|Y)"]
        bad = [
            f"'{k}' is not a direction ({', '.join(AXIS_DIRECTIONS)})"
            for k in values
            if k not in AXIS_DIRECTIONS
        ]
        bad += [f"direction '{k}': '{v}' is not X or Y" for k, v in values.items() if v not in AXES]
        if not bad and len(set(values.values())) != len(values):
            bad = ["two directions cannot take the same axis"]
        return bad
    if code == PREFIX_CODE:
        if not values:
            return ["this question needs at least one value: <prefix>=<meaning>"]
        return [f"prefix '{k}': the meaning is blank" for k, v in values.items() if not v.strip()]
    if code == SELECT_CODE:
        if set(values) - {"systems", "separate"}:
            return ["this question takes only the optional values systems=S001,S002 and separate=S001,S002"]
        bad: list[str] = []
        for name in ("systems", "separate"):
            if name not in values:
                continue
            ids = _system_ids(values[name])
            wrong = [
                f"{name}: '{i}' is not a grid system id like S001" for i in ids if not SYSTEM_ID.fullmatch(i)
            ]
            if not wrong and len(set(ids)) != len(ids):
                wrong = [f"{name}: the ids must be distinct"]
            if not wrong and name == "separate" and len(ids) < 2:
                wrong = ["separate: name at least two systems (they are different buildings)"]
            bad += wrong
        if not bad and "separate" in values and "systems" in values:
            outside = sorted(set(_system_ids(values["separate"])) - set(_system_ids(values["systems"])))
            if outside:
                bad = [
                    f"separate: {', '.join(outside)} not in systems (a separate building must be selected)"
                ]
        return bad
    if code == FILE_SET_CODE:
        if not values:
            return ["this question needs at least one set: set1=a.dwg,b.dwg (set2=..., every file once)"]
        bad = [f"'{k}' is not a set name like set1" for k in values if not FILE_SET_KEY.fullmatch(k)]
        seen: dict[str, str] = {}
        for name, text in values.items():
            files = _system_ids(text)
            if any(not f for f in files):
                bad.append(f"{name}: a file name is blank")
                continue
            for f in files:
                if f in seen:
                    bad.append(f"{f} is named twice ({seen[f]} and {name}): each file belongs to one set")
                seen.setdefault(f, name)
        return bad
    return [f"questions with code '{code}' take no value, got: {', '.join(sorted(values))}"] if values else []


def _system_ids(text: str) -> list[str]:
    """Comma-separated ids or file names, stripped."""
    return [part.strip() for part in text.split(",")]


def _raised_question(work: Path, key: str) -> dict[str, Any] | None:
    """The question with this key in the question documents on disk (None when no readable one has it)."""
    for name in QUESTION_DOCUMENTS:
        path = work / name
        if not path.is_file():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        for q in doc.get("questions", []) if isinstance(doc, dict) else []:
            if isinstance(q, dict) and q.get("key") == key:
                return q
    return None


def _check_in_context(
    ledger: Ledger, question_id: str, key: str, entry: dict[str, Any], values: dict[str, str]
) -> None:
    """Rules that need the question itself or the other answers. Raises QuestionsError."""
    code = entry["code"]
    if code == CONFLICT_CODE:
        select = [
            e["id"]
            for e in ledger.registry["questions"].values()
            if e["code"] == SELECT_CODE and e["status"] != "obsolete"
        ]
        raise QuestionsError(
            EXIT_USAGE,
            f"{question_id} ({CONFLICT_CODE}) cannot be answered: a conflict closes only through the "
            f"{SELECT_CODE} answer ({', '.join(select) or SELECT_CODE}): systems= without one of the two, or "
            "separate= naming both when they are different buildings; then rerun harness grid-system. "
            "Nothing was written",
        )
    if code == SYSTEM_AXIS_CODE:
        q = _raised_question(ledger.work, key)
        names = [s["name"] for s in (q or {}).get("subjects") or [] if isinstance(s, dict)]
        if not names:
            raise QuestionsError(
                EXIT_INVALID,
                f"{question_id}: its directions are not in grid-system-questions.json; "
                "rerun harness grid-system",
            )
        if set(values) != set(names):
            raise QuestionsError(
                EXIT_INVALID,
                f"{question_id} ({code}): give exactly {', '.join(f'{n}=X|Y' for n in names)}, got "
                f"{', '.join(sorted(values))}",
            )
    if code == SELECT_CODE:
        q = _raised_question(ledger.work, key)
        known = [r["where"] for r in (q or {}).get("refs") or [] if isinstance(r, dict)]
        for name in ("systems", "separate"):  # both may only name systems the question lists
            if name not in values:
                continue
            unknown = [i for i in _system_ids(values[name]) if i not in known]
            if not known or unknown:
                raise QuestionsError(
                    EXIT_INVALID,
                    f"{question_id}: {name} names {', '.join(unknown) or 'systems'} that the question does "
                    f"not list ({', '.join(known) or 'grid-system-questions.json has no such question'})",
                )
    if code == FILE_SET_CODE:
        q = _raised_question(ledger.work, key)
        listed = {r["file"] for r in (q or {}).get("refs") or [] if isinstance(r, dict) and r.get("file")}
        if not listed:
            raise QuestionsError(
                EXIT_INVALID, f"{question_id}: its files are not in questions.json; rerun harness intake"
            )
        named = {f for text in values.values() for f in _system_ids(text)}
        missing, unknown = sorted(listed - named), sorted(named - listed)
        if missing or unknown:
            raise QuestionsError(
                EXIT_INVALID,
                f"{question_id} ({code}): name every file of the question exactly once"
                + (f"; missing {', '.join(missing)}" if missing else "")
                + (f"; not in the question: {', '.join(unknown)}" if unknown else ""),
            )
    if code == CONTRADICTION_CODE:
        units = {
            str(a["values"].get("unit"))
            for a in active_answers(ledger.answers).values()
            if a["code"] in UNIT_CODES and a["file"] in (entry["file"], None)
        }
        if units != {values["unit"]}:
            raise QuestionsError(
                EXIT_INVALID,
                f"{question_id}: unit={values['unit']} is not the unit answered for {entry['file']} "
                f"({', '.join(sorted(units)) or 'none'}): this question only confirms that unit; to change "
                "it, answer the file's units_confirm_all again",
            )


def _check_file_unchanged(work: Path, question_id: str, entry: dict[str, Any]) -> None:
    """Refuse (exit 1) when the question's file differs from what the question was raised on."""
    recorded, file = entry.get("file_sha256"), entry["file"]
    path = work / "inventory.json"
    if recorded is None or file is None or not path.is_file():
        return
    try:
        inventory = json.loads(path.read_text(encoding="utf-8"))
        current = {row["path"]: row["sha256"] for row in inventory["files"]}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise QuestionsError(
            EXIT_INVALID, f"inventory.json cannot be read to check {question_id}: {exc}"
        ) from exc
    now = current.get(file)
    if now == recorded:
        return
    command = PRODUCER_COMMANDS.get(entry["producer"], entry["producer"])
    what = "was removed" if now is None else "changed"
    raise QuestionsError(
        EXIT_INVALID,
        f"{question_id}: file changed since this question was raised; rerun `{command}` "
        f"({file} {what}: sha256 {recorded[:12]} when asked, {'not in' if now is None else now[:12] + ' in'} "
        "inventory.json now). Nothing was written",
    )


def _refreshed(ledger: Ledger) -> tuple[dict[str, str], dict[str, dict[str, int]], list[dict[str, str]]]:
    """New text of every readable question document, their summaries, and the ones left alone."""
    texts: dict[str, str] = {}
    summaries: dict[str, dict[str, int]] = {}
    skipped: list[dict[str, str]] = []
    for name in QUESTION_DOCUMENTS:
        path = ledger.work / name
        if not path.is_file():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            skipped.append({"file": name, "reason": f"cannot be read: {exc}"})
            continue
        problems = validate("intake", doc)
        if problems:
            skipped.append({"file": name, "reason": f"invalid, rerun its command: {problems[0].message}"})
            continue
        for q in doc["questions"]:
            q["answer"] = ledger.active(q["key"])
        doc["summary"] = questions_summary(doc["questions"])
        problems = validate("intake", doc)
        if problems:  # a bug here, not in the file
            raise QuestionsError(
                EXIT_INVALID, f"{name} would be invalid, nothing written: {problems[0].message}"
            )
        texts[name] = dump_json(doc)
        summaries[name] = doc["summary"]
    return texts, summaries, skipped


def record_answer(
    work_dir: Path | str,
    question_id: str,
    text: str,
    by: str,
    values: dict[str, str] | None = None,
    *,
    today: date | None = None,
    role: str,
) -> dict[str, Any]:
    """Append an answer (see the module docstring). Returns what was done. Raises QuestionsError."""
    work = Path(work_dir).resolve()
    if not work.is_dir():
        raise QuestionsError(EXIT_USAGE, f"work folder not found (not a folder): {work_dir}")
    if role not in ROLES:
        raise QuestionsError(EXIT_USAGE, f"--role '{role}' is not one of {', '.join(ROLES)}")
    if not text.strip():
        raise QuestionsError(EXIT_USAGE, "the answer text is empty: write the engineer's words verbatim")
    if not by.strip():
        raise QuestionsError(EXIT_USAGE, "who answered (--by) is empty")
    ledger = load_ledger(work, None, create=False)
    found = ledger.entry_by_id(question_id)
    if found is None:
        raise QuestionsError(EXIT_USAGE, f"unknown question id '{question_id}' (see question-registry.json)")
    key, entry = found
    if entry["status"] == "obsolete":
        raise QuestionsError(
            EXIT_USAGE,
            f"{question_id} is obsolete: its producer ({entry['producer']}) no longer raises it (the drawing "
            "behind it changed). Answer the question that replaced it, in the latest question documents",
        )
    _check_file_unchanged(work, question_id, entry)
    values = dict(values or {})
    problems = check_values(entry["code"], values)
    if problems:
        raise QuestionsError(EXIT_INVALID, f"{question_id} ({entry['code']}): " + "; ".join(problems))
    _check_in_context(ledger, question_id, key, entry, values)

    stored: dict[str, Any] = dict(values)
    if entry["code"] == SELECT_CODE:
        for name in ("systems", "separate"):
            if name in values:
                stored[name] = _system_ids(values[name])
    if entry["code"] == FILE_SET_CODE:
        stored = {name: _system_ids(files) for name, files in values.items()}
    answer: dict[str, Any] = {
        "key": key,
        "question_id": question_id,
        "code": entry["code"],
        "file": entry["file"],
        "answer_text": text,
        "values": stored,
        "answered_by": by.strip(),
        "answered_by_role": role,
        "answered_on": (today or date.today()).isoformat(),
        "status": "active",
    }
    superseded = 0
    for old in ledger.answers["answers"]:
        if old["key"] == key and old["status"] == "active":
            old["status"] = "superseded"
            superseded += 1
    ledger.answers["answers"].append(answer)
    ledger.answers_changed = True
    ledger.mark_answered(key, True)
    ledger.check()
    texts, summaries, skipped = _refreshed(ledger)

    ledger.write()  # registry and answers first, then the documents
    for name, doc_text in texts.items():
        write_text_atomic(work / name, doc_text)
    return {
        "answer": answer,
        "superseded": superseded,
        "refreshed": sorted(texts),
        "not_refreshed": skipped,
        "summaries": summaries,
    }
