"""ask: the drawing-reader agent raises (or withdraws) a question through the registry (`harness ask`).

The reader agent used to invent question ids; now it asks here and gets the id back. The questions are
the `reader` producer of the registry (questions.py) and live in `reader-questions.json`, the same
document kind as the other `*questions.json`.

  * One question per distinct (code, blocking, file, where): the key hashes those four and the file's
    sha256 from `inventory.json`, NOT `found`, `sheet` or the text. Asking the same place again gives the
    same key and id, changes nothing and reports `already_asked`; another `where` is another question
    with the next id from the registry's shared counter. Each question has exactly one ref.
  * `--file` (an inventory path) may be omitted for a project-level question; a file that the inventory
    does not list is refused (exit 1).
  * `--code` is lowercase snake_case and must not be a code another producer owns: the codes already in
    the registry under another producer, plus the known codes and code families in `OTHER_OWNERS` (exit 2,
    the owner is named). Codes starting with `reader_` are always the reader's (e.g.
    `reader_level_storey_selection`): use that namespace for a gap whose natural code a producer owns.
  * `--text` is the English question; the Vietnamese rendering belongs to questions.md, not here.
  * A reader question is never obsoleted by another producer's run. `--withdraw Q-id --reason "..."`
    marks one obsolete (kept in the registry with its reason, dropped from reader-questions.json; an
    active answer to it goes stale). Withdrawing twice is a no-op. A withdrawn place cannot be asked again
    (exit 2): ask about another `where`.
  * Answers work unchanged (`harness answer`).

Stdout: {"id", "key", "status": "new" | "already_asked"}, or {"id", "key", "status": "withdrawn" |
"already_withdrawn"}. Registry first, then the document (questions.py).

Exit codes (AGENTS.md): 1 invalid documents or a file not in the inventory, 2 usage.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from tekla_harness.questions import (
    EXIT_INVALID,
    EXIT_USAGE,
    KEY_LENGTH,
    PRODUCER_COMMANDS,
    Ledger,
    QuestionsError,
    dump_json,
    load_ledger,
    questions_document,
    write_text_atomic,
)
from tekla_harness.schemas import validate

READER = "reader"
READER_FILE = "reader-questions.json"
CODE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
# Codes and code families the other producers raise. The registry is the authority for codes already
# raised; this table also stops the reader from taking a code a producer raises only when its input needs it.
OTHER_OWNERS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    # producer -> (exact codes, prefixes)
    "intake": (
        (
            "dimension_override_differs",
            "font_encoding_conflict",
            "font_encoding_proposed",
            "multiple_scales",
            "probe_section_failed",
            "text_encoding_hint",
            "unreadable_objects",
            "xref_unresolved",
            "encoding_unknown_non_ascii",
            "conversion_empty",
            "converter_errors",
            "read_failed",
            "no_reader_implemented",
        ),
        ("units_",),
    ),
    "grid-system": ((), ("grid_system_",)),
    "structure": (("grid_family_axis_assignment", "grid_units_doubt"), ("grid_", "level_", "sheet_")),
    "callouts": (
        ("member_mark_prefix_meaning", "grade_legacy_mapping"),
        ("callout_", "steel_grade", "rebar_"),
    ),
    "marks": ((), ("mark_", "schedule_")),
}
# Codes in this namespace are always the reader's own: no producer may own them, so the reader can ask
# about grids, levels, sheets or rebar without colliding with a producer's prefix.
READER_NAMESPACE = "reader_"


def static_owner(code: str) -> str | None:
    if code.startswith(READER_NAMESPACE):
        return None
    for producer, (exact, prefixes) in OTHER_OWNERS.items():
        if code in exact or code.startswith(prefixes):
            return producer
    return None


def reader_key(code: str, blocking: bool, file: str | None, file_sha: str | None, where: str) -> str:
    """Stable identity of a reader question: sha256 over (code, blocking, file, file sha256, where)."""
    payload = json.dumps([code, blocking, file, file_sha, where], separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()[:KEY_LENGTH]


def _inventory_sha(work: Path, file: str) -> str:
    path = work / "inventory.json"
    if not path.is_file():
        raise QuestionsError(
            EXIT_USAGE, f"{work} has no inventory.json: run `harness intake <input_dir> --out {work}` first"
        )
    try:
        inventory = json.loads(path.read_text(encoding="utf-8"))
        rows = {row["path"]: row["sha256"] for row in inventory["files"]}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise QuestionsError(EXIT_INVALID, f"inventory.json cannot be read: {exc}") from exc
    if file not in rows:
        raise QuestionsError(
            EXIT_INVALID,
            f"file '{file}' is not in inventory.json: use a path exactly as listed there "
            "(a question about the whole project needs no --file)",
        )
    return rows[file]


def _owner_of(ledger: Ledger, code: str) -> str | None:
    if code.startswith(READER_NAMESPACE):
        return None
    for entry in ledger.registry["questions"].values():
        if entry["code"] == code and entry["producer"] != READER:
            return entry["producer"]
    return static_owner(code)


def _load_reader_doc(work: Path, project_id: str) -> dict[str, Any]:
    path = work / READER_FILE
    if not path.is_file():
        return questions_document(project_id, [])
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QuestionsError(EXIT_INVALID, f"{READER_FILE} cannot be read: {exc}") from exc
    problems = validate("intake", doc)
    if problems or doc.get("kind") != "questions":
        why = problems[0].message if problems else "kind is not 'questions'"
        raise QuestionsError(EXIT_INVALID, f"{READER_FILE} is invalid: {why}")
    return doc


def _finish(ledger: Ledger, doc: dict[str, Any]) -> None:
    """Refresh answers and summary, validate everything, then write registry/answers first, document last."""
    questions = doc["questions"]
    for q in questions:
        q["answer"] = ledger.active(q["key"])
    doc.update(questions_document(ledger.registry["project_id"], questions))
    problems = validate("intake", doc)
    if problems:  # a bug here, not in the work folder
        raise QuestionsError(
            EXIT_INVALID, f"{READER_FILE} would be invalid, nothing written: {problems[0].message}"
        )
    ledger.check()
    ledger.write()
    write_text_atomic(ledger.work / READER_FILE, dump_json(doc))


def ask_question(
    work_dir: Path | str,
    *,
    code: str,
    where: str,
    found: str,
    text: str,
    file: str | None = None,
    sheet: str | None = None,
    blocking: bool = False,
) -> dict[str, str]:
    """Raise one reader question (see the module docstring). Raises QuestionsError."""
    work = Path(work_dir).resolve()
    if not work.is_dir():
        raise QuestionsError(EXIT_USAGE, f"work folder not found (not a folder): {work_dir}")
    if not CODE.fullmatch(code):
        raise QuestionsError(
            EXIT_USAGE, f"--code '{code}' must be lowercase snake_case, e.g. grid_label_unclear"
        )
    if not where.strip():
        raise QuestionsError(EXIT_USAGE, "--where is empty: say where in the drawing the question applies")
    if not text.strip():
        raise QuestionsError(EXIT_USAGE, "--text is empty: write the question in English")
    if file is not None and not file.strip():
        raise QuestionsError(EXIT_USAGE, "--file is empty: omit it for a project-level question")
    if sheet is not None and not sheet.strip():
        raise QuestionsError(EXIT_USAGE, "--sheet is empty: omit it when the question has no sheet")
    ledger = load_ledger(work, None, create=False)
    owner = _owner_of(ledger, code)
    if owner is not None:
        raise QuestionsError(
            EXIT_USAGE,
            f"code '{code}' belongs to producer '{owner}' ({PRODUCER_COMMANDS[owner]}): "
            "choose a code of your own, it must not collide with a producer's",
        )
    file_sha = _inventory_sha(work, file) if file is not None else None
    key = reader_key(code, blocking, file, file_sha, where)
    entries = ledger.registry["questions"]
    entry = entries.get(key)
    if entry is not None:
        if entry["producer"] != READER:
            raise QuestionsError(EXIT_INVALID, f"key {key} belongs to producer '{entry['producer']}'")
        if entry["status"] == "obsolete":
            raise QuestionsError(
                EXIT_USAGE,
                f"{entry['id']} for this place was withdrawn ({entry.get('withdrawn_reason', 'no reason')}): "
                "ask about another --where",
            )
        return {"id": entry["id"], "key": key, "status": "already_asked"}

    doc = _load_reader_doc(work, ledger.registry["project_id"])
    registry = ledger.registry
    run = registry["runs"] + 1
    registry["runs"] = run
    question_id = f"Q-{registry['next_id']:03d}"
    registry["next_id"] += 1
    entries[key] = {
        "id": question_id,
        "code": code,
        "file": file,
        "producer": READER,
        "status": "open",
        "first_seen_run": run,
        "last_seen_run": run,
        "blocking": blocking,
        "file_sha256": file_sha,
    }
    ref: dict[str, Any] = {"file": file, "where": where, "found": found}
    if sheet is not None:
        ref["sheet"] = sheet
    doc["questions"].append(
        {
            "id": question_id,
            "key": key,
            "code": code,
            "blocking": blocking,
            "file": file,
            "message": text,
            "count": 1,
            "truncated": False,
            "refs": [ref],
            "answer": None,
        }
    )
    _finish(ledger, doc)
    return {"id": question_id, "key": key, "status": "new"}


def withdraw_question(work_dir: Path | str, question_id: str, reason: str) -> dict[str, str]:
    """Mark a reader question obsolete (kept in the registry). Raises QuestionsError."""
    work = Path(work_dir).resolve()
    if not work.is_dir():
        raise QuestionsError(EXIT_USAGE, f"work folder not found (not a folder): {work_dir}")
    if not reason.strip():
        raise QuestionsError(EXIT_USAGE, "--reason is empty: say why the question is withdrawn")
    ledger = load_ledger(work, None, create=False)
    found = ledger.entry_by_id(question_id)
    if found is None:
        raise QuestionsError(EXIT_USAGE, f"unknown question id '{question_id}' (see question-registry.json)")
    key, entry = found
    if entry["producer"] != READER:
        raise QuestionsError(
            EXIT_USAGE,
            f"{question_id} belongs to producer '{entry['producer']}', not the reader: "
            f"only {PRODUCER_COMMANDS[entry['producer']]} can retire it",
        )
    if entry["status"] == "obsolete":
        return {"id": question_id, "key": key, "status": "already_withdrawn"}
    entry["status"] = "obsolete"
    entry["withdrawn_reason"] = reason.strip()
    for a in ledger.answers["answers"]:
        if a["key"] == key and a["status"] == "active":
            a["status"], a["stale_reason"] = "stale", f"the question was withdrawn: {reason.strip()}"
            ledger.answers_changed = True
    doc = _load_reader_doc(work, ledger.registry["project_id"])
    doc["questions"] = [q for q in doc["questions"] if q["key"] != key]
    _finish(ledger, doc)
    return {"id": question_id, "key": key, "status": "withdrawn"}
