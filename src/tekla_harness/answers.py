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
        grid_family_axis_assignment   <family_id>=X|Y               (at least one)
        member_mark_prefix_meaning    <prefix>=<meaning>            (at least one)
        grid_system_select            systems=S001,S002             (optional: the grid systems the project
                                      uses; without it `harness status` takes every listed system as used)
    every other code takes no value;
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
    EXIT_INVALID,
    EXIT_USAGE,
    PREFIX_CODE,
    PRODUCER_COMMANDS,
    QUESTION_DOCUMENTS,
    SELECT_CODE,
    UNIT_CODES,
    UNITS,
    Ledger,
    QuestionsError,
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
    if code in UNIT_CODES:
        if set(values) != {"unit"}:
            return ["this question needs exactly one value: unit=" + "|".join(UNITS)]
        return (
            [] if values["unit"] in UNITS else [f"unit '{values['unit']}' is not one of {', '.join(UNITS)}"]
        )
    if code == AXIS_CODE:
        if not values:
            return ["this question needs at least one value: <family_id>=X|Y"]
        return [f"family '{k}': '{v}' is not X or Y" for k, v in values.items() if v not in AXES]
    if code == PREFIX_CODE:
        if not values:
            return ["this question needs at least one value: <prefix>=<meaning>"]
        return [f"prefix '{k}': the meaning is blank" for k, v in values.items() if not v.strip()]
    if code == SELECT_CODE:
        if set(values) - {"systems"}:
            return ["this question takes only the optional value systems=S001,S002"]
        if "systems" not in values:
            return []
        ids = _system_ids(values["systems"])
        bad = [f"systems: '{i}' is not a grid system id like S001" for i in ids if not SYSTEM_ID.fullmatch(i)]
        if not bad and len(set(ids)) != len(ids):
            bad = ["systems: the ids must be distinct"]
        return bad
    return [f"questions with code '{code}' take no value, got: {', '.join(sorted(values))}"] if values else []


def _system_ids(text: str) -> list[str]:
    return [part.strip() for part in text.split(",")]


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
) -> dict[str, Any]:
    """Append an answer (see the module docstring). Returns what was done. Raises QuestionsError."""
    work = Path(work_dir).resolve()
    if not work.is_dir():
        raise QuestionsError(EXIT_USAGE, f"work folder not found (not a folder): {work_dir}")
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

    stored: dict[str, Any] = dict(values)
    if entry["code"] == SELECT_CODE and "systems" in values:
        stored["systems"] = _system_ids(values["systems"])
    answer = {
        "key": key,
        "question_id": question_id,
        "code": entry["code"],
        "file": entry["file"],
        "answer_text": text,
        "values": stored,
        "answered_by": by.strip(),
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
