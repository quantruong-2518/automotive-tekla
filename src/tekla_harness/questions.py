"""questions: stable question keys, the question registry, answers, and the rendering shared by the producers.

Why: question ids used to be positional (Q-001 was "the first group of this run"), so a rerun or one new
input file shifted them and an engineer answer could attach to the wrong question. Now a question has an
identity that does not depend on the position:

  key       first 16 hex of sha256 over (code, file, sha256 of that file, canonical sorted refs). The same
            drawing content gives the same key on every run; changed content gives a new key, which is
            asked again.
  id        Q-001.. allocated by the registry (`question-registry.json`) in increasing order and NEVER
            reused. A key keeps its id for ever. A key its producer no longer raises becomes 'obsolete'
            (kept, not deleted), with an `obsolete_reason` (OBSOLETE_*: file removed, file changed,
            superseded by an answer the producer names, or not raised any more).
  answer    `answers.json`: the engineer's words, bound to the key. An answer whose file was changed or
            removed (or whose question is no longer raised) becomes 'stale'; it is never deleted and never
            re-bound to another key.

One question is one (code, blocking flag, file) with its refs (file null = a question about the whole
project), except one per file and text style for legacy_ascii_text and one per file and unparsed_code for
callout_unparsed (tool wave 3): those differ by their refs, so by their key.
Six producers share the registry and own disjoint code sets: `intake` (harness intake),
`structure` (harness read-structure), `callouts` (harness callouts), `marks` (harness marks: member marks
and schedules), `grid-system` (harness grid-system) and
`reader` (harness ask, the drawing-reader agent's own questions, see ask.py: one question per
(code, blocking, file, where), added one at a time, never obsoleted by another producer's run).
A producer only obsoletes keys of its own producer. Every registry entry also records the question's
`blocking` flag and, for a file question, the file's sha256 at the time the question was raised
(`file_sha256`): `harness status` counts blocking questions from the registry alone, and `harness answer`
refuses a question whose file has changed since.

Usage in a producer (all in memory, then write):

    ledger = load_ledger(work, project_id, create=...)
    questions = ledger.sync("structure", raw_questions, file_hashes)   # ids, keys, answers
    ... build and validate every document ...
    ledger.write()                       # registry and answers FIRST, then the documents

Writing the registry before the documents means a crash can never leave a document that uses an id the
registry does not know. Nothing here is a timestamp: the same work folder gives the same documents (the
registry's run counters change on every run, by design).

Exit codes (AGENTS.md): 1 a document is invalid or inconsistent, 2 usage (no registry, wrong project).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tekla_harness.schemas import validate

SCHEMA_VERSION = "0.1"
REGISTRY_FILE = "question-registry.json"
ANSWERS_FILE = "answers.json"
KEY_LENGTH = 16
PRODUCERS = ("intake", "structure", "callouts", "marks", "grid-system", "reader")
# the command that (re)runs each producer, for messages
PRODUCER_COMMANDS = {
    "intake": "harness intake",
    "structure": "harness read-structure",
    "callouts": "harness callouts",
    "marks": "harness marks",
    "grid-system": "harness grid-system",
    "reader": "harness ask",
}
# the question documents each producer writes, for `harness answer` to refresh
QUESTION_DOCUMENTS = (
    "questions.json",
    "structure-questions.json",
    "callouts-questions.json",
    "marks-questions.json",
    "grid-system-questions.json",
    "reader-questions.json",
)
EXIT_INVALID, EXIT_USAGE = 1, 2

UNITS = ("mm", "cm", "m", "in", "ft")
# units_confirm_all is THE units question of a probed file (intake); the other codes are legacy (folded into
# its refs, or non-blocking evidence) but their unit answers still count, so old answers.json stay valid
UNITS_CONFIRM_CODE = "units_confirm_all"
UNIT_CODES = frozenset(
    {UNITS_CONFIRM_CODE, "units_conflict", "units_suspect", "units_unknown", "grid_units_doubt"}
)
# grid-system: the answered unit makes the drawing's dimensions implausible; closed by re-confirming the unit
CONTRADICTION_CODE = "units_answer_contradicts_evidence"
AXIS_CODE = "grid_family_axis_assignment"
SYSTEM_AXIS_CODE = "grid_system_axis_unassigned"
CONFLICT_CODE = "grid_system_conflict"
PREFIX_CODE = "member_mark_prefix_meaning"
SELECT_CODE = "grid_system_select"
AXIS_DIRECTIONS = ("dir1", "dir2")  # value keys of a grid_system_axis_unassigned answer
# intake, project level: which readable drawing files form one set (one building, one grid); answered with
# set1=a.dwg,b.dwg set2=c.dwg, every file of the question's refs exactly once
FILE_SET_CODE = "file_set_relation"
FILE_SET_KEY = re.compile(r"set[1-9][0-9]*")
# tool wave 3 codes (names frozen: the EVAL-4 metrics use them), with their producers:
SHEET_GAP_CODE = "sheet_number_gap"  # read-structure (sheets), not blocking: gaps in a file's sheet numbers
CALLOUT_UNPARSED_CODE = "callout_unparsed"  # callouts: one per file and unparsed_code; blocks lot specs
LEGACY_ASCII_CODE = "legacy_ascii_text"  # intake (read-dxf), not blocking: one per file and text style
GRID_MISSING_CODE = "grid_system_missing"  # grid-system, blocking (ADR-0013): a file with no usable system
GRID_CONTRADICTS_CODE = "grid_answer_contradicts_drawing"  # grid-system, blocking (ADR-0013 §5)
# value keys of a grid_system_missing answer (ADR-0013 §2): comma-separated labels and spacings per
# direction, both directions required; GRID_ANSWER_SHEET_KEY is optional
GRID_ANSWER_KEYS = ("dir1_labels", "dir1_spacings", "dir2_labels", "dir2_spacings")
GRID_ANSWER_SHEET_KEY = "sheet"
# tool wave 4 code (V1; package T raises it): texts that may not print, which the file does not settle
TEXT_VISIBILITY_CODE = "text_visibility_uncertain"  # intake (extract-text), not blocking: one per file
# who gave an answer (answers.json answered_by_role): gate 1 counts the engineer's answers only
ROLES = ("engineer", "simulated")
# why a question is closed without an answer of its own (intake schema closed_by.reason; lifecycle.py)
CLOSURE_REASONS = ("not_selected", "separate", "units_answered", "rejected_systems_only", "other_file_set")
# why a producer run made a registry entry obsolete (registry `obsolete_reason`, tool wave 3 W5), in the
# precedence order Ledger.sync applies: the file went, the file changed, an answer superseded it, or simply
# not raised any more
OBSOLETE_FILE_REMOVED = "its input file was removed"
OBSOLETE_FILE_CHANGED = "its input file changed (the question is asked again under a new key)"
OBSOLETE_SUPERSEDED = "superseded by an answer to {code}"
OBSOLETE_NOT_RAISED = "the latest {producer} run no longer raises it"


@dataclass(frozen=True)
class Closure:
    """A question closed by another answer or selection (lifecycle.closures): `question_id` is the question
    whose answer closes it (None when no single question does), `reason` one of CLOSURE_REASONS."""

    question_id: str | None
    reason: str

    def __post_init__(self) -> None:
        if self.reason not in CLOSURE_REASONS:
            raise ValueError(f"unknown closure reason '{self.reason}'")

    def as_dict(self) -> dict[str, str | None]:
        return {"question_id": self.question_id, "reason": self.reason}


class QuestionsError(Exception):
    """A run that cannot proceed; `exit_code` is the CLI exit code."""

    def __init__(self, exit_code: int, message: str) -> None:
        super().__init__(message)
        self.exit_code = exit_code


# --- small shared helpers -----------------------------------------------------------------------


def dump_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def write_text_atomic(path: Path, text: str) -> None:
    """Write through a temporary file in the same folder, so a crash never leaves half a document."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _details(problems: list[Any]) -> str:
    return "; ".join(f"{p.path or '/'}: {p.message}" for p in problems[:5])


def question_group(
    code: str,
    blocking: bool,
    message: str,
    refs: list[dict[str, Any]],
    cap: int | None = None,
    *,
    file: str | None,
    subjects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """A question as a producer hands it over (no id, key or answer yet). `cap`: refs listed at most; the
    count stays the true total."""
    shown = refs if cap is None else refs[:cap]
    out: dict[str, Any] = {
        "code": code,
        "blocking": blocking,
        "file": file,
        "message": message,
        "count": len(refs),
        "truncated": len(shown) < len(refs),
        "refs": shown,
    }
    if subjects is not None:
        out["subjects"] = subjects
    return out


def merged_question(
    code: str,
    blocking: bool,
    file: str | None,
    items: list[tuple[str, dict[str, Any]]],
    cap: int | None = None,
    unlisted: int = 0,
) -> dict[str, Any]:
    """One question from (message, ref) items: the first message is the question's, a ref whose wording
    differs carries its own `message`. `unlisted`: occurrences an extractor counted but did not list."""
    message = items[0][0]
    refs = [ref if msg == message else {**ref, "message": msg} for msg, ref in items]
    question = question_group(code, blocking, message, refs, cap, file=file)
    if unlisted:
        question["count"] += unlisted
        question["truncated"] = True
    return question


def questions_per_file(
    code: str, blocking: bool, message: str, refs: list[dict[str, Any]], cap: int | None = None
) -> list[dict[str, Any]]:
    """One question per file for refs that all carry their `file`, in order of first appearance."""
    by_file: dict[str, list[dict[str, Any]]] = {}
    for ref in refs:
        by_file.setdefault(ref["file"], []).append(ref)
    return [question_group(code, blocking, message, rs, cap, file=f) for f, rs in by_file.items()]


def question_key(code: str, file: str | None, file_sha: str | None, refs: list[dict[str, Any]]) -> str:
    """Stable identity of a question: see the module docstring. `file_sha` None (project-level question, or
    a file not in the inventory) is part of the hash as null."""
    canonical = sorted([r["where"], r["found"], r.get("sheet") or ""] for r in refs)
    payload = json.dumps([code, file, file_sha, canonical], separators=(",", ":"))
    return hashlib.sha256(payload.encode("ascii")).hexdigest()[:KEY_LENGTH]


def questions_summary(questions: list[dict[str, Any]]) -> dict[str, int]:
    blocking = [q for q in questions if q["blocking"]]
    return {
        "questions": len(questions),
        "blocking_questions": len(blocking),
        "answered": sum(1 for q in questions if q["answer"] is not None),
        "blocking_open": sum(1 for q in blocking if q["answer"] is None),
    }


def questions_document(project_id: str, questions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "questions",
        "project_id": project_id,
        "questions": questions,
        "summary": questions_summary(questions),
    }


def active_answers(answers_doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """key -> its active answer."""
    return {a["key"]: a for a in answers_doc["answers"] if a["status"] == "active"}


def _id_number(question_id: str) -> int:
    return int(question_id[2:])


# --- the ledger: registry + answers ---------------------------------------------------------------


def empty_registry(project_id: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "next_id": 1,
        "runs": 0,
        "questions": {},
    }


def empty_answers(project_id: str) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "project_id": project_id, "answers": []}


def _load_document(path: Path, schema: str, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise QuestionsError(EXIT_INVALID, f"{label} {path} cannot be read: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise QuestionsError(EXIT_INVALID, f"{label} {path} is not valid JSON: {exc}") from exc
    problems = validate(schema, data)
    if problems:
        raise QuestionsError(
            EXIT_INVALID, f"{label} {path} is invalid ({schema} schema): {_details(problems)}"
        )
    return data


def check_consistency(registry: dict[str, Any], answers: dict[str, Any]) -> None:
    """Rules JSON Schema cannot express. Raises QuestionsError(1)."""
    entries = registry["questions"]
    ids = [e["id"] for e in entries.values()]
    if len(set(ids)) != len(ids):
        raise QuestionsError(EXIT_INVALID, f"{REGISTRY_FILE}: an id is used by two keys")
    highest = max((_id_number(i) for i in ids), default=0)
    if registry["next_id"] <= highest:
        raise QuestionsError(
            EXIT_INVALID,
            f"{REGISTRY_FILE}: next_id {registry['next_id']} is not above the highest id Q-{highest:03d}",
        )
    active: set[str] = set()
    for a in answers["answers"]:
        entry = entries.get(a["key"])
        if entry is not None and entry["id"] != a["question_id"]:
            raise QuestionsError(
                EXIT_INVALID,
                f"{ANSWERS_FILE}: answer to key {a['key']} says {a['question_id']}, "
                f"the registry has {entry['id']}",
            )
        if a["status"] == "active":
            if a["key"] in active:
                raise QuestionsError(EXIT_INVALID, f"{ANSWERS_FILE}: two active answers to key {a['key']}")
            active.add(a["key"])


@dataclass
class Ledger:
    """The registry and the answers of one work folder, in memory."""

    work: Path
    registry: dict[str, Any]
    answers: dict[str, Any]
    answers_changed: bool = False

    def active(self, key: str) -> dict[str, Any] | None:
        return active_answers(self.answers).get(key)

    def entry_by_id(self, question_id: str) -> tuple[str, dict[str, Any]] | None:
        for key, entry in self.registry["questions"].items():
            if entry["id"] == question_id:
                return key, entry
        return None

    def stale_answers(self) -> list[dict[str, Any]]:
        """Every stale answer, for the run summary: the engineer must ask these questions again."""
        return [
            {
                "question_id": a["question_id"],
                "key": a["key"],
                "code": a["code"],
                "file": a["file"],
                "reason": a["stale_reason"],
            }
            for a in self.answers["answers"]
            if a["status"] == "stale"
        ]

    def mark_answered(self, key: str, answered: bool) -> None:
        entry = self.registry["questions"][key]
        if entry["status"] != "obsolete":
            entry["status"] = "answered" if answered else "open"

    def check(self) -> None:
        """Both documents against their schemas and the consistency rules; raises QuestionsError(1)."""
        for name, doc, label in (
            ("question-registry", self.registry, REGISTRY_FILE),
            ("answers", self.answers, ANSWERS_FILE),
        ):
            problems = validate(name, doc)
            if problems:
                raise QuestionsError(
                    EXIT_INVALID, f"{label} would be invalid, nothing written: {_details(problems)}"
                )
        check_consistency(self.registry, self.answers)

    def sync(
        self,
        producer: str,
        raw: list[dict[str, Any]],
        file_hashes: dict[str, str],
        stale_files: dict[str, str] | None = None,
        *,
        superseded_by: Mapping[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Register this run's questions of `producer` and return them rendered, in the producer's order:
        id, key, code, blocking, file, message, count, truncated, refs, [subjects], answer.

        New keys get the next ids (in order). Keys of this producer that were not raised become obsolete,
        with `obsolete_reason` set on that transition (_obsolete_reason) and dropped if the key is raised
        again. An active answer becomes stale when its file is in `stale_files` (path -> 'changed' |
        'removed') or when its question is no longer raised. `file_hashes`: input-relative path -> sha256.
        `superseded_by`: question code -> answer code, for codes this run stopped raising BECAUSE of an
        answer to that code (e.g. grid-system: grid_system_conflict -> file_set_relation)."""
        if producer not in PRODUCERS:
            raise ValueError(f"unknown producer '{producer}'")
        registry, entries = self.registry, self.registry["questions"]
        run = registry["runs"] + 1
        registry["runs"] = run

        keyed: list[tuple[str, dict[str, Any]]] = []
        used: set[str] = set()
        for q in raw:
            file = q["file"]
            base = question_key(
                q["code"], file, file_hashes.get(file) if file is not None else None, q["refs"]
            )
            key, n = base, 1
            while key in used:  # two identical questions in one run: a producer bug, but keys stay unique
                n += 1
                key = hashlib.sha256(f"{base}#{n}".encode("ascii")).hexdigest()[:KEY_LENGTH]
            used.add(key)
            keyed.append((key, q))
        seen = {k for k, _ in keyed}

        for a in self.answers["answers"]:
            if a["status"] != "active":
                continue
            reason = None
            if a["file"] is not None and a["file"] in (stale_files or {}):
                reason = f"the input file was {(stale_files or {})[a['file']]} since the answer was given"
            else:
                entry = entries.get(a["key"])
                if entry is not None and entry["producer"] == producer and a["key"] not in seen:
                    reason = f"the latest {producer} run no longer raises this question"
            if reason is not None:
                a["status"], a["stale_reason"] = "stale", reason
                self.answers_changed = True

        active = active_answers(self.answers)
        for key, q in keyed:
            entry = entries.get(key)
            if entry is None:
                entry = entries[key] = {
                    "id": f"Q-{registry['next_id']:03d}",
                    "code": q["code"],
                    "file": q["file"],
                    "producer": producer,
                    "status": "open",
                    "first_seen_run": run,
                    "last_seen_run": run,
                }
                registry["next_id"] += 1
            elif entry["producer"] != producer:
                raise QuestionsError(
                    EXIT_INVALID,
                    f"question {entry['id']} ({entry['code']}) belongs to producer '{entry['producer']}', "
                    f"but '{producer}' raised the same key: producers must own disjoint codes",
                )
            entry["last_seen_run"] = run
            # a key seen again has the same file sha256 (the key hashes it): backfilling is safe
            entry["blocking"] = q["blocking"]
            entry["file_sha256"] = file_hashes.get(q["file"]) if q["file"] is not None else None
        for key, entry in entries.items():
            if entry["producer"] == producer:
                if key in seen:  # raised (again): a revived key forgets why it was obsolete
                    entry.pop("obsolete_reason", None)
                    entry["status"] = "answered" if key in active else "open"
                elif entry["status"] != "obsolete":  # the reason is the transition's; later runs keep it
                    entry["status"] = "obsolete"
                    entry["obsolete_reason"] = self._obsolete_reason(
                        entry, producer, file_hashes, stale_files or {}, superseded_by or {}
                    )
            elif entry["status"] != "obsolete":  # another producer's question whose answer just went stale
                entry["status"] = "answered" if key in active else "open"

        rendered = []
        for key, q in keyed:
            out: dict[str, Any] = {
                "id": entries[key]["id"],
                "key": key,
                "code": q["code"],
                "blocking": q["blocking"],
                "file": q["file"],
                "message": q["message"],
                "count": q["count"],
                "truncated": q["truncated"],
                "refs": q["refs"],
            }
            if "subjects" in q:
                out["subjects"] = q["subjects"]
            out["answer"] = dict(active[key]) if key in active else None
            rendered.append(out)
        self.check()
        return rendered

    def _obsolete_reason(
        self,
        entry: dict[str, Any],
        producer: str,
        file_hashes: dict[str, str],
        stale_files: dict[str, str],
        superseded_by: Mapping[str, str],
    ) -> str:
        """Why `producer`'s run no longer raises this entry (OBSOLETE_*), first match wins: its file was
        removed (intake's diff, or absent from the run's hashes) or changed (intake's diff, or a sha256 other
        than the one recorded when it was raised); the producer declared its code superseded by an answer
        to another code (`superseded_by`: code -> answer code) and such an answer is active; else not
        raised. A project-level entry (file null) has no file reason."""
        file = entry["file"]
        if file is not None:
            diff = stale_files.get(file)
            if diff == "removed" or (diff is None and file not in file_hashes):
                return OBSOLETE_FILE_REMOVED
            recorded = entry.get("file_sha256")
            if diff == "changed" or (recorded is not None and file_hashes.get(file) != recorded):
                return OBSOLETE_FILE_CHANGED
        answer_code = superseded_by.get(entry["code"])
        if answer_code is not None and any(
            a["code"] == answer_code and a["status"] == "active" for a in self.answers["answers"]
        ):
            return OBSOLETE_SUPERSEDED.format(code=answer_code)
        return OBSOLETE_NOT_RAISED.format(producer=producer)

    def write(self) -> None:
        """Registry (always) and answers (when they changed); call BEFORE writing any question document."""
        entries = self.registry["questions"]
        self.registry["questions"] = dict(sorted(entries.items(), key=lambda kv: _id_number(kv[1]["id"])))
        write_text_atomic(self.work / REGISTRY_FILE, dump_json(self.registry))
        if self.answers_changed:
            write_text_atomic(self.work / ANSWERS_FILE, dump_json(self.answers))
            self.answers_changed = False


def load_ledger(work: Path, project_id: str | None, *, create: bool) -> Ledger:
    """Load registry and answers of a work folder. `create`: a missing registry starts a new one (intake
    only); otherwise it is a usage error. `project_id` None: take the registry's. Raises QuestionsError."""
    work = Path(work)
    reg_path, ans_path = work / REGISTRY_FILE, work / ANSWERS_FILE
    if reg_path.is_file():
        registry = _load_document(reg_path, "question-registry", REGISTRY_FILE)
        if project_id is not None and registry["project_id"] != project_id:
            raise QuestionsError(
                EXIT_USAGE,
                f"{work} holds project '{registry['project_id']}' (see {REGISTRY_FILE}), not '{project_id}': "
                "use another work folder",
            )
    elif create and project_id is not None:
        registry = empty_registry(project_id)
    else:
        raise QuestionsError(
            EXIT_USAGE, f"{work} has no {REGISTRY_FILE}: run `harness intake <input_dir> --out {work}` first"
        )
    if ans_path.is_file():
        answers = _load_document(ans_path, "answers", ANSWERS_FILE)
        if answers["project_id"] != registry["project_id"]:
            raise QuestionsError(
                EXIT_INVALID,
                f"{ANSWERS_FILE} is for project '{answers['project_id']}', not '{registry['project_id']}'",
            )
    else:
        answers = empty_answers(registry["project_id"])
    check_consistency(registry, answers)
    return Ledger(work, registry, answers)
