"""supplements: evidence the drawing-reader adds to a producer's question (`harness ask --supplement`).

Document `reader-supplements.json`, schema `supplements`. Instead of asking a producer's question again, the
reader adds what it found (where, found, its note in Vietnamese) to that question:

  * identity: `key` = first 16 hex of sha256 over (target key, file, the file's inventory sha256, where);
    supplementing the same place again changes nothing and reports `already_supplemented`;
  * the target must be a live question of another producer: an unknown or obsolete id, or a reader question
    (the reader edits its own questions with `harness ask` / `--withdraw`), is a usage error (exit 2);
    `--file` must be an inventory path (exit 1 otherwise);
  * a supplement NEVER changes the target: not its blocking flag, not its answer, not its refs. Nothing but
    this document is written;
  * `--withdraw-supplement <key> --reason R` marks one withdrawn (kept, twice is a no-op); a withdrawn place
    cannot be supplemented again (exit 2), like a withdrawn reader question;
  * `load_supplements` computes the status on read: an active supplement whose target is obsolete (or gone)
    in the registry is `stale`. The stored status is only active or withdrawn.

questions.md shows the active supplements under their question (questions_md.supplement_lines).

Exit codes (AGENTS.md): 1 an invalid document or a file not in the inventory, 2 usage.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from tekla_harness.ask import READER, _inventory_sha
from tekla_harness.questions import (
    EXIT_INVALID,
    EXIT_USAGE,
    KEY_LENGTH,
    PRODUCER_COMMANDS,
    QuestionsError,
    dump_json,
    load_ledger,
    write_text_atomic,
)
from tekla_harness.schemas import validate

SUPPLEMENTS_FILE = "reader-supplements.json"
SCHEMA_VERSION = "0.1"


def supplement_key(target_key: str, file: str | None, file_sha: str | None, where: str) -> str:
    """Stable identity of a supplement: sha256 over (target key, file, file sha256, where)."""
    payload = json.dumps([target_key, file, file_sha, where], separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()[:KEY_LENGTH]


def _work(work_dir: Path | str) -> Path:
    work = Path(work_dir).resolve()
    if not work.is_dir():
        raise QuestionsError(EXIT_USAGE, f"work folder not found (not a folder): {work_dir}")
    return work


def _read(work: Path, project_id: str) -> dict[str, Any] | None:
    """The stored document (validated), or None when there is none yet."""
    path = work / SUPPLEMENTS_FILE
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QuestionsError(EXIT_INVALID, f"{SUPPLEMENTS_FILE} cannot be read: {exc}") from exc
    problems = validate("supplements", doc)
    if problems:
        raise QuestionsError(
            EXIT_INVALID, f"{SUPPLEMENTS_FILE} is invalid: {problems[0].path}: {problems[0].message}"
        )
    if doc["project_id"] != project_id:
        raise QuestionsError(
            EXIT_INVALID, f"{SUPPLEMENTS_FILE} is for project '{doc['project_id']}', not '{project_id}'"
        )
    return doc


def _write(work: Path, doc: dict[str, Any]) -> None:
    problems = validate("supplements", doc)
    if problems:  # a bug here, not in the work folder
        raise QuestionsError(
            EXIT_INVALID, f"{SUPPLEMENTS_FILE} would be invalid, nothing written: {problems[0].message}"
        )
    write_text_atomic(work / SUPPLEMENTS_FILE, dump_json(doc))


def load_supplements(work: Path) -> list[dict[str, Any]]:
    """Every supplement of the work folder, in the order added, with the status computed on read (`stale`
    when an active supplement's target is obsolete or no longer in the registry). Raises QuestionsError."""
    if not (Path(work) / SUPPLEMENTS_FILE).is_file():
        return []
    ledger = load_ledger(Path(work), None, create=False)
    doc = _read(ledger.work, ledger.registry["project_id"])
    entries = ledger.registry["questions"]
    out = []
    for row in doc["supplements"] if doc is not None else []:
        entry = entries.get(row["target_key"])
        live = entry is not None and entry["status"] != "obsolete"
        out.append({**row, "status": "stale"} if row["status"] == "active" and not live else dict(row))
    return out


def add_supplement(
    work_dir: Path | str,
    *,
    target_id: str,
    where: str,
    found: str,
    text: str,
    file: str | None = None,
    sheet: str | None = None,
) -> dict[str, str]:
    """Append one supplement; returns {key, target_id, status: new | already_supplemented}. Raises
    QuestionsError."""
    work = _work(work_dir)
    if not where.strip():
        raise QuestionsError(EXIT_USAGE, "--where is empty: say where in the drawing the evidence is")
    if not text.strip():
        raise QuestionsError(EXIT_USAGE, "--text is empty: write the note in Vietnamese")
    if file is not None and not file.strip():
        raise QuestionsError(EXIT_USAGE, "--file is empty: omit it for project-level evidence")
    if sheet is not None and not sheet.strip():
        raise QuestionsError(EXIT_USAGE, "--sheet is empty: omit it when the evidence has no sheet")
    ledger = load_ledger(work, None, create=False)
    found_entry = ledger.entry_by_id(target_id)
    if found_entry is None:
        raise QuestionsError(EXIT_USAGE, f"unknown question id '{target_id}' (see question-registry.json)")
    target_key, entry = found_entry
    if entry["producer"] == READER:
        raise QuestionsError(
            EXIT_USAGE,
            f"{target_id} is a reader question: supplement only a producer's question; edit your own with "
            "harness ask (ask another --where, or --withdraw it)",
        )
    if entry["status"] == "obsolete":
        raise QuestionsError(
            EXIT_USAGE,
            f"{target_id} is obsolete: its producer ({PRODUCER_COMMANDS[entry['producer']]}) no longer "
            "raises it; supplement the question that replaced it",
        )
    file_sha = _inventory_sha(work, file) if file is not None else None
    key = supplement_key(target_key, file, file_sha, where)
    project_id = ledger.registry["project_id"]
    doc = _read(work, project_id) or {
        "schema_version": SCHEMA_VERSION,
        "kind": "reader_supplements",
        "project_id": project_id,
        "supplements": [],
    }
    old = next((s for s in doc["supplements"] if s["key"] == key), None)
    if old is not None:
        if old["status"] == "withdrawn":
            raise QuestionsError(
                EXIT_USAGE,
                f"supplement {key} for this place was withdrawn ({old['withdrawn_reason']}): "
                "supplement another --where",
            )
        return {"key": key, "target_id": old["target_id"], "status": "already_supplemented"}
    doc["supplements"].append(
        {
            "key": key,
            "target_key": target_key,
            "target_id": entry["id"],
            "target_code": entry["code"],
            "target_producer": entry["producer"],
            "file": file,
            "file_sha256": file_sha,
            "sheet": sheet,
            "where": where,
            "found": found,
            "text": text,
            "status": "active",
        }
    )
    _write(work, doc)
    return {"key": key, "target_id": entry["id"], "status": "new"}


def withdraw_supplement(work_dir: Path | str, key: str, reason: str) -> dict[str, str]:
    """Mark a supplement withdrawn (kept); returns {key, status: withdrawn | already_withdrawn}. Raises
    QuestionsError."""
    work = _work(work_dir)
    if not reason.strip():
        raise QuestionsError(EXIT_USAGE, "--reason is empty: say why the supplement is withdrawn")
    ledger = load_ledger(work, None, create=False)
    doc = _read(work, ledger.registry["project_id"])
    row = next((s for s in doc["supplements"] if s["key"] == key), None) if doc is not None else None
    if doc is None or row is None:
        raise QuestionsError(EXIT_USAGE, f"unknown supplement key '{key}' (see {SUPPLEMENTS_FILE})")
    if row["status"] == "withdrawn":
        return {"key": key, "status": "already_withdrawn"}
    row["status"] = "withdrawn"
    row["withdrawn_reason"] = reason.strip()
    _write(work, doc)
    return {"key": key, "status": "withdrawn"}
