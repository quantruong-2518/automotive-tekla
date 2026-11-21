"""part_receipts: the part hash, `W/parts/<X>/receipts.json` and the status derived from them (ADR-0019, E5b).

This is the read side. `part_hash` is one fingerprint of what a part holds: its manifest row, its active and
withdrawn findings, its reader questions, the bytes of `values.json` and `notes.md`. It also holds part of
what `harness part check` judges those against (E5b-fix-1, E5b-fix-3): per active finding `stale` (as
`findings.list_findings` computes it: the drawing's inventory sha256, the knowledge rows of `decoded_by`,
the saved evidence); the manifest row of the part's block (`block`, its `grid_system_ids` included);
`files`, the inventory sha256 of every drawing the manifest row or a row of `values.json` names (so a
revised drawing moves the hash of a part whose rows cite entries or geometry and no finding);
`cited_questions`, every question the rows of `values.json` cite directly or through a finding and every
question an own active finding holds (cited by a row or not: `low_without_question` reads them), with its
state (`obsolete`, `open`, or `unknown` when the registry lacks the id) and its registry `blocking` flag; and
`grid_systems`, the system object of `grid-systems.json` (null when it lacks the id) of every system a row of
`values.json` cites (`cites.grid_systems`), which that file is read for only then.
Answers, amendments, the other parts a shared question lists, `decoded_by` and the registry's `answered` are
never hashed: an answer moves readiness, never the lock. The hash is not all of the check: the text index
and sheets document of an unchanged drawing, the bytes of a saved geometry or contents document,
`marks.json` and the check's own rules are outside it, so `part check` stays the judge at the point of use.
`read_receipts` reads the part's receipts file (schema `part-receipts`).
`PartStates` / `part_status` derive the status of a part from its latest receipts and the current hash:

    locked  the latest receipt is `locked`, on the current hash, and every input part is `locked` on the hash
            that receipt stored
    reopened  the latest receipt is `reopened`, or a `locked` one whose hash is no longer the current hash
    stale_input  a `locked` receipt whose input is not `locked` any more, or has another hash (a cycle too)
    reviewed / checked / reading  among the receipts after the last `reopened` or `locked`: `reviewed` when
            the latest `reviewed` one, whatever its hash, says `pass` and is on the current hash (`fix` or
            `engineer`, or a review of another hash, leaves `checked`); else `checked` when one of them is a
            `checked` on the current hash; else none
    receipts_invalid  the receipts file is unreadable as a receipts file (exit 3 is never a status)

`write_part_receipt` is `harness part receipt` (the writer, below the status): one receipt appended to
`parts/<X>/receipts.json` when its preconditions hold, nothing written when one fails.

`locked_parts` is the write refusal's question: the parts whose LATEST receipt is `locked`, read from the
receipts alone, so a hand edit of `values.json` cannot unlock a write. Reading rules as `part_values`: a file
that is not there is absent; an `OSError` is exit 3 (`ReaderError`); a file that is there but unusable is
`ReceiptsInvalid` (exit 1, names the file).
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tekla_harness import __version__
from tekla_harness.findings import FindingError, _stale_reasons, _table
from tekla_harness.knowledge import FontEncodingTable
from tekla_harness.part_values import _read_document, read_values
from tekla_harness.parts_manifest import _read_manifest
from tekla_harness.receipt import ReceiptError
from tekla_harness.schemas import validate
from tekla_harness.sheet_text import Inventory, ReaderError, load_inventory
from tekla_harness.strict_json import StrictJsonError, loads_strict

EXIT_INVALID, EXIT_ENV = 1, 3
RECEIPTS_NAME = "receipts.json"
KINDS = ("checked", "reviewed", "locked", "reopened")
STATUSES = ("reading", "checked", "reviewed", "locked", "reopened", "stale_input", "receipts_invalid")


class ReceiptsInvalid(ReaderError):
    """`parts/<X>/receipts.json` is there and is not a usable receipts file (exit 1); names the file."""

    def __init__(self, message: str) -> None:
        super().__init__(EXIT_INVALID, message)


def receipts_rel(part: str) -> str:
    return f"parts/{part}/{RECEIPTS_NAME}"


def read_receipts(work_dir: Path | str, part: str) -> list[dict[str, Any]]:
    """The receipts of `part`, oldest first; [] when there is no file. Raises ReceiptsInvalid (not a regular
    file: a symbolic link, dangling or not, is not one; not strict JSON, not `part-receipts`, another
    part's file, `n` not 1, 2, ...) and ReaderError(3)
    for any other `OSError`."""
    rel = receipts_rel(part)
    path = Path(work_dir) / rel
    try:
        try:
            # lstat: a link is there even when its target is not, and no receipts file is a link (the writer
            # replaces one); decided before any open: a named pipe would block it
            if not stat.S_ISREG(path.lstat().st_mode):
                raise ReceiptsInvalid(f"{rel} is not a regular file")
            data = path.read_bytes()
        except (FileNotFoundError, NotADirectoryError):
            return []
    except OSError as exc:
        raise ReaderError(EXIT_ENV, f"cannot read {rel} ({exc})") from exc
    try:
        doc = loads_strict(data)
    except StrictJsonError as exc:
        raise ReceiptsInvalid(f"{rel} is not valid JSON: {exc}") from exc
    found = validate("part-receipts", doc)
    if found:
        raise ReceiptsInvalid(f"{rel} is invalid (part-receipts): {found[0].path or '/'}: {found[0].message}")
    if doc["part"] != part:
        raise ReceiptsInvalid(f"{rel}: part is '{doc['part']}', not '{part}'")
    for index, receipt in enumerate(doc["receipts"], start=1):
        if receipt["n"] != index:
            raise ReceiptsInvalid(f"{rel}: receipts[{index - 1}].n is {receipt['n']}, expected {index}")
    return doc["receipts"]  # type: ignore[no-any-return]


def locked_parts(work_dir: Path | str, ids: Iterable[str]) -> list[str]:
    """The ids (in the given order, each once) whose latest receipt kind is `locked`. Not the derived status:
    a part whose values changed after its lock is `reopened` there and still listed here. Raises what
    `read_receipts` raises: an unreadable file refuses the write, it does not unlock it."""
    out: list[str] = []
    for part in dict.fromkeys(ids):
        receipts = read_receipts(work_dir, part)
        if receipts and receipts[-1]["kind"] == "locked":
            out.append(part)
    return out


# --- the hash ----------------------------------------------------------------------------------------------


NOT_A_REGULAR_FILE = "not_a_regular_file"  # never equal to a sha256: a directory is not an absent file


def _file_sha256(work: Path, rel: str) -> str | None:
    """The sha256 of the bytes of `work/rel`; None when it is not there; `NOT_A_REGULAR_FILE` when it is
    there and is not a regular file. Raises ReaderError(3) for an `OSError` other than not-found."""
    path = work / rel
    try:
        if not stat.S_ISREG(path.stat().st_mode):  # decided before any open: a named pipe would block it
            return NOT_A_REGULAR_FILE
        data = path.read_bytes()
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError as exc:
        raise ReaderError(EXIT_ENV, f"cannot read {rel} ({exc})") from exc
    return hashlib.sha256(data).hexdigest()


class _Records:
    """The reader's own records, read once: findings and questions as stored, the registry's status by id. The
    inventory and the knowledge table (what `stale` is judged against) are read when the first finding needs
    them."""

    def __init__(self, work: Path, knowledge: FontEncodingTable | None = None) -> None:
        self.work = work
        self._knowledge = knowledge
        findings = _read_document(work, "reader-findings.json", "reader-findings")
        questions = _read_document(work, "reader-questions.json", "reader-questions")
        registry = _read_document(work, "question-registry.json", "question-registry")
        self.findings: list[dict[str, Any]] = (findings or {}).get("findings", [])
        self.questions: list[dict[str, Any]] = (questions or {}).get("questions", [])
        self.entries: dict[str, dict[str, Any]] = {
            q["id"]: q for q in (registry or {}).get("questions", {}).values()
        }
        self.status = {qid: entry["status"] for qid, entry in self.entries.items()}
        self.by_id = {f["id"]: f for f in self.findings}
        self._inventory: tuple[Inventory, dict[str, str]] | None = None
        self._table: FontEncodingTable | None = None

    def inventory(self) -> tuple[Inventory, dict[str, str]]:
        """The inventory and its per-file sha256 (path -> sha256), read once. Raises ReaderError (2: no
        inventory.json)."""
        if self._inventory is None:
            inv = load_inventory(self.work)
            self._inventory = (inv, {row["path"]: row["sha256"] for row in inv.doc["files"]})
        return self._inventory

    def stale(self, finding: dict[str, Any]) -> bool:
        """`stale` of the finding, from the one source `findings._stale_reasons` (as `list_findings`). Raises
        ReaderError (the inventory or the knowledge table cannot be read, or the judgement is refused by the
        system: the exit code of the `FindingError` is kept)."""
        inv, current = self.inventory()
        try:
            if self._table is None:
                self._table = _table(self._knowledge)
            return bool(_stale_reasons(inv, finding, current, self._table))
        except FindingError as exc:
            raise ReaderError(exc.exit_code, str(exc)) from exc


def _finding(f: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f["id"], "kind": f["kind"], "file": f["file"], "sheet": f["sheet"],
        "entries": [e["id"] for e in f["entries"]], "value": f["value"], "fields": f["fields"],
        "questions": f["questions"], "confidence": f["confidence"],
        "evidence_sha256": f["evidence"]["sha256"] if "evidence" in f else None,
    }  # fmt: skip


def _cited_questions(values: dict[str, Any] | None, records: _Records, part: str) -> list[dict[str, Any]]:
    """The question ids the rows of the part's `values.json` cite, as `part_rules._cited_questions` does:
    `cites.questions` and the `questions` of every finding in `cites.findings` (a finding id no record holds
    adds none); and the `questions` of every active finding of `part` itself, cited or not (E5b review 3, m1:
    `part_rules._finding_problems` reads the registry status of those of a `low` one). Each with what
    `part check` reads of it: `status` (`obsolete`, `open` (an answer is not a
    state: it never moves the lock) or `unknown`: the registry lacks the id) and `blocking` (null for an
    unknown or obsolete id, else the registry's flag, a missing one counting as blocking, as
    `part_rules._blocks`).
    A `values.json` that is missing or unusable cites none (its bytes are hashed anyway). Still outside the
    hash: the text index of an unchanged drawing, `marks.json`, saved documents and the check's rules."""
    cited: set[str] = set()
    for r in (values or {}).get("rows", []):
        cites = r.get("cites", {})
        cited.update(cites.get("questions", []))
        for fid in cites.get("findings", []):
            cited.update(records.by_id.get(fid, {}).get("questions", []))
    for f in records.findings:
        if f.get("part") == part and f["status"] == "active":
            cited.update(f["questions"])
    out: list[dict[str, Any]] = []
    for qid in sorted(cited):
        entry = records.entries.get(qid)
        state = "unknown" if entry is None else "obsolete" if entry["status"] == "obsolete" else "open"
        blocking = entry.get("blocking", True) is not False if entry is not None and state == "open" else None
        out.append({"id": qid, "status": state, "blocking": blocking})
    return out


def _files(row: dict[str, Any], values: dict[str, Any] | None, records: _Records) -> dict[str, str | None]:
    """The drawings the part reads: every `file` its manifest row names (`sheets[]`, `tables[]` and the
    cluster of a table, `clusters[]`, `files[]`) and every `file` of a row of `values.json`, each with the
    inventory's sha256 of it (null when the inventory no longer lists it). The per-file sha256, never the
    bytes of `inventory.json`: a re-intake of unchanged drawings reopens nothing. The inventory is read only
    when the part names a file."""
    named = {x["file"] for key in ("sheets", "tables", "clusters") for x in row.get(key, []) if "file" in x}
    named |= {t["cluster"]["file"] for t in row.get("tables", []) if "cluster" in t}
    named |= set(row.get("files", []))
    named |= {r["file"] for r in (values or {}).get("rows", []) if "file" in r}
    if not named:
        return {}
    _, current = records.inventory()
    return {path: current.get(path) for path in sorted(named)}


def _grid_systems(work: Path, values: dict[str, Any] | None) -> dict[str, dict[str, Any] | None]:
    """The system object of `grid-systems.json` (null when the document or the id is not there) of every
    system a row of `values.json` cites. The document is read only when a row cites one, as the check does.
    Raises ReaderError (1: the document is not strict JSON or not `grid-system`; 3: an `OSError`)."""
    cited = {
        sid for r in (values or {}).get("rows", []) for sid in r.get("cites", {}).get("grid_systems", [])
    }
    if not cited:
        return {}
    doc = _read_document(work, "grid-systems.json", "grid-system")
    systems = {s["system_id"]: s for s in (doc or {}).get("systems", [])}
    return {sid: systems.get(sid) for sid in sorted(cited)}


def _hash(work: Path, manifest: dict[str, Any], row: dict[str, Any], part: str, records: _Records) -> str:
    own = [f for f in records.findings if f.get("part") == part]
    values, _ = read_values(work, part, row["kind"])
    block = next((b for b in manifest.get("blocks", []) if b["id"] == row.get("block")), None)
    doc = {
        "manifest_part": row,
        "block": block,
        "findings": sorted(
            ({**_finding(f), "stale": records.stale(f)} for f in own if f["status"] == "active"),
            key=lambda f: f["id"],
        ),
        "withdrawn": sorted(f["id"] for f in own if f["status"] == "withdrawn"),
        "questions": sorted(
            (
                {
                    "id": q["id"], "code": q["code"], "blocking": q["blocking"], "message": q["message"],
                    "refs": q["refs"], "places": q.get("places", []),
                    "status": "obsolete" if records.status.get(q["id"]) == "obsolete" else "open",
                }
                for q in records.questions
                if part in q.get("parts", [])
            ),
            key=lambda q: q["id"],
        ),
        "cited_questions": _cited_questions(values, records, part),
        "files": _files(row, values, records),
        "grid_systems": _grid_systems(work, values),
        "values_sha256": _file_sha256(work, f"parts/{part}/values.json"),
        "notes_sha256": _file_sha256(work, f"parts/{part}/notes.md"),
    }  # fmt: skip
    payload = json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _row(manifest: dict[str, Any], part: str) -> dict[str, Any]:
    row = next((p for p in manifest["parts"] if p["id"] == part), None)
    if row is None:
        raise ReaderError(EXIT_INVALID, f"part '{part}' is not in parts[] of the manifest")
    return row  # type: ignore[no-any-return]


def part_hash(
    work_dir: Path | str, manifest: dict[str, Any], part: str, knowledge: FontEncodingTable | None = None
) -> str:
    """The sha256 (hex) of the canonical JSON of what `part` holds (see the module docstring). A
    `values.json` or `notes.md` that is not there counts as null, one that is not a regular file as
    "not_a_regular_file". `knowledge`: the
    font-encoding table a finding's `stale` is judged against (default the shipped one, as `part check`).
    Raises ReaderError (1: `part` is not in `manifest` or a record document is invalid; 2: no inventory.json
    while a finding is active; 3: an `OSError` other than not-found, the knowledge table cannot be read)."""
    work = Path(work_dir)
    return _hash(work, manifest, _row(manifest, part), part, _Records(work, knowledge))


# --- the status --------------------------------------------------------------------------------------------


def load_manifest(work: Path) -> dict[str, Any]:
    """The work folder's manifest. Raises ReaderError(1) when it is missing or invalid, ManifestAccessError
    when the operating system refuses it (exit 3)."""
    manifest, found = _read_manifest(work)
    if manifest is None:
        raise ReaderError(
            EXIT_INVALID, "parts/manifest.json is not usable: " + "; ".join(p[4] for p in found[:3])
        )
    return manifest


def _since_reset(receipts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The receipts after the last `reopened` or `locked`, whatever their hash."""
    boundary = max((i for i, r in enumerate(receipts) if r["kind"] in ("reopened", "locked")), default=-1)
    return receipts[boundary + 1 :]


def _tail(receipts: list[dict[str, Any]], current: str) -> list[dict[str, Any]]:
    """The receipts after the last `reopened` or `locked` that carry the current hash: what a stage may build
    on. One rule for the status and for the preconditions of the writer."""
    return [r for r in _since_reset(receipts) if r["part_hash"] == current]


def _latest_review(since: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The latest `reviewed` receipt of `since` (`_since_reset`), whatever its hash: it decides, so a later
    `fix` beats an earlier `pass`, and a `fix` recorded on another hash is not forgotten when the part comes
    back to the earlier one. Its verdict counts as `pass` only when it is on the current hash."""
    return next((r for r in reversed(since) if r["kind"] == "reviewed"), None)


def _passes(review: dict[str, Any] | None, current: str) -> bool:
    return review is not None and review["part_hash"] == current and review["review"]["verdict"] == "pass"


class PartStates:
    """The hashes and statuses of the parts of one manifest, each worked out once (the records are read once,
    and a status once, however many parts list the part as an input). Not a cache across calls: build a new
    one after a file changed."""

    def __init__(
        self,
        work_dir: Path | str,
        manifest: dict[str, Any] | None = None,
        knowledge: FontEncodingTable | None = None,
    ) -> None:
        self.work = Path(work_dir)
        self._knowledge = knowledge
        self.manifest = load_manifest(self.work) if manifest is None else manifest
        self._rows = {p["id"]: p for p in self.manifest["parts"]}
        self._records: _Records | None = None
        self._hashes: dict[str, str] = {}
        self._statuses: dict[str, str] = {}
        self._visiting: set[str] = set()

    def hash(self, part: str) -> str:
        if part not in self._hashes:
            if self._records is None:
                self._records = _Records(self.work, self._knowledge)
            self._hashes[part] = _hash(
                self.work, self.manifest, _row(self.manifest, part), part, self._records
            )
        return self._hashes[part]

    def status(self, part: str) -> str:
        """One of `STATUSES`. Raises ReaderError (1: `part` is not in the manifest; 3: an `OSError`)."""
        if part in self._visiting:  # a cycle of inputs: the part on it is not locked yet
            return "stale_input"
        if part not in self._statuses:
            _row(self.manifest, part)
            self._visiting.add(part)
            try:
                self._statuses[part] = self._derive(part)
            finally:
                self._visiting.discard(part)
        return self._statuses[part]

    def _derive(self, part: str) -> str:
        try:
            receipts = read_receipts(self.work, part)
        except ReceiptsInvalid:
            return "receipts_invalid"
        if not receipts:
            return "reading"
        current = self.hash(part)
        latest = receipts[-1]
        if latest["kind"] == "locked":
            if latest["part_hash"] != current:
                return "reopened"
            stored = latest["inputs"] or {}
            stale = [i for i in self._rows[part].get("inputs", []) if not self._input_holds(i, stored.get(i))]
            return "stale_input" if stale else "locked"
        if latest["kind"] == "reopened":
            return "reopened"
        if _passes(_latest_review(_since_reset(receipts)), current):
            return "reviewed"
        if any(r["kind"] == "checked" for r in _tail(receipts, current)):
            return "checked"
        return "reading"

    def _input_holds(self, part: str, stored: str | None) -> bool:
        """The input part is `locked` and its hash is the one the lock stored."""
        return part in self._rows and self.status(part) == "locked" and stored == self.hash(part)


def part_status(work_dir: Path | str, part: str, knowledge: FontEncodingTable | None = None) -> str:
    """The derived status of `part` (see the module docstring). Raises ReaderError (1: the manifest is not
    usable or does not list `part`; 3: an `OSError`) and ManifestAccessError."""
    return PartStates(work_dir, knowledge=knowledge).status(part)


# --- the writer --------------------------------------------------------------------------------------------

VERDICTS = ("pass", "fix", "engineer")
_RESET = "reopened or locked receipt"
_REOPEN = 'harness part receipt W --part {part} --kind reopened --reason "..."'


class _Refused(Exception):
    """A precondition failed: the receipt is not written (exit 1). `problems` are the check's, when it ran."""

    def __init__(self, message: str, problems: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.problems = problems or []


def _output(
    part: str,
    kind: str,
    receipt: dict[str, Any] | None,
    *,
    written: bool,
    refused: str | None = None,
    problems: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """The output document, validated against `part-output` as `part check` does its own. Raises
    ReaderError(1) "internal error" when it is invalid (a bug)."""
    doc = {
        "command": "receipt", "part": part, "kind": kind, "written": written, "receipt": receipt,
        "refused": refused, "problems": problems or [],
    }  # fmt: skip
    invalid = validate("part-output", doc)
    if invalid:
        shown = "; ".join(f"{p.path}: {p.message}" for p in invalid[:3])
        raise ReaderError(EXIT_INVALID, f"internal error: output is invalid: {shown}")
    return doc


def _usage(
    kind: str, review: str | None, review_round: int | None, verdict: str | None, reason: str | None
) -> None:
    """Flags that do not go with `kind` (ReaderError 2): `--review --round --verdict` belong to `reviewed`
    and need all three, `--reason` belongs to `reopened` and needs text."""
    if kind not in KINDS:
        raise ReaderError(2, f"--kind must be one of {', '.join(KINDS)}, not '{kind}'")
    review_flags = {"--review": review, "--round": review_round, "--verdict": verdict}
    if kind == "reviewed":
        missing = [flag for flag, value in review_flags.items() if value is None]
        if missing:
            raise ReaderError(2, f"--kind reviewed needs {', '.join(missing)}")
        if not review or not str(review).strip():
            raise ReaderError(2, "--review is empty")
        if review_round is not None and review_round < 1:
            raise ReaderError(2, f"--round must be 1 or more, not {review_round}")
        if verdict not in VERDICTS:
            raise ReaderError(2, f"--verdict must be one of {', '.join(VERDICTS)}, not '{verdict}'")
    else:
        given = [flag for flag, value in review_flags.items() if value is not None]
        if given:
            raise ReaderError(2, f"{', '.join(given)} go with --kind reviewed, not {kind}")
    if kind == "reopened":
        if reason is None or not reason.strip():
            raise ReaderError(2, "--kind reopened needs a non-empty --reason")
    elif reason is not None:
        raise ReaderError(2, f"--reason goes with --kind reopened, not {kind}")


def _check(work: Path, part: str) -> dict[str, Any]:
    """The document of `harness part check` for `part` (`problems` empty: the check passes)."""
    from tekla_harness import part_check  # part_check imports this module

    return part_check.check_part(work, part)


def _review_record(work: Path, part: str, review: str, review_round: int, verdict: str) -> dict[str, Any]:
    """The `review` object of a `reviewed` receipt: `review` must be the regular file
    `parts/<part>/review/round-<round>/review.md` of the work folder (a symbolic link is not one)."""
    rel = f"parts/{part}/review/round-{review_round}/review.md"
    path = work / rel
    if Path(review).resolve() != path.resolve():
        raise _Refused(f"--review must be {rel} (--round {review_round}), not {review}")
    if path.resolve() != work.resolve() / rel:  # a folder on the way is a link: the file would live elsewhere
        raise _Refused(f"parts/{part}/review/round-{review_round} is reached through a symbolic link")
    try:
        if not stat.S_ISREG(path.lstat().st_mode):  # decided before any open: a named pipe would block it
            raise _Refused(f"{rel} is not a regular file")
        data = path.read_bytes()
    except (FileNotFoundError, NotADirectoryError):
        raise _Refused(f"{rel} is not there") from None
    except OSError as exc:
        raise ReaderError(EXIT_ENV, f"cannot read {rel} ({exc})") from exc
    return {
        "round": review_round,
        "verdict": verdict,
        "file": rel,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _same_stage(
    latest: dict[str, Any] | None,
    kind: str,
    current: str,
    review: dict[str, Any] | None,
    inputs: dict[str, str] | None,
) -> bool:
    """Rule 5: the latest receipt is of this kind, on this hash; for `reviewed` also this round, file and
    verdict, for `locked` also the same stored input hashes (`inputs`, the current ones)."""
    if latest is None or latest["kind"] != kind or latest["part_hash"] != current:
        return False
    if kind == "locked":
        return (latest["inputs"] or {}) == inputs
    if review is None:
        return True
    stored = latest["review"]
    keys = ("round", "sha256", "verdict")
    return bool(stored) and all(stored[k] == review[k] for k in keys)


def _input_hashes(states: PartStates, part: str) -> dict[str, str]:
    """The current hash of each input the manifest lists for `part`; an input the manifest does not list is
    left out (a lock refuses it through `_unlocked_inputs`)."""
    return {i: states.hash(i) for i in states._rows[part].get("inputs", []) if i in states._rows}


def _unlocked_inputs(states: PartStates, part: str) -> list[str]:
    out: list[str] = []
    for item in states._rows[part].get("inputs", []):
        if item not in states._rows:
            out.append(f"{item} (not in the manifest)")
        elif (status := states.status(item)) != "locked":
            out.append(f"{item} ({status})")
    return out


def _preconditions(
    kind: str,
    part: str,
    receipts: list[dict[str, Any]],
    current: str,
    states: PartStates,
    work: Path,
    record: dict[str, Any] | None,
) -> None:
    """Preconditions 1 to 4 of ADR-0019 (E5b); raises _Refused. Rule 5 is the caller's."""
    latest = receipts[-1] if receipts else None
    since = _since_reset(receipts)
    after = _tail(receipts, current)
    if kind in ("checked", "locked"):
        if kind == "checked" and latest and latest["kind"] == "locked":
            raise _Refused(
                f"part '{part}' is locked (receipt {latest['n']}): reopen it first: "
                + _REOPEN.format(part=part)
            )
        checked = _check(work, part)
        problems = list(checked["problems"])
        if problems:
            raise _Refused(f"harness part check reports {len(problems)} problem(s) for '{part}'", problems)
        if checked["hash"] != current:  # a hand edit between the hash and the check: nothing vouches for it
            raise _Refused("the part changed while it was checked: run the receipt again")
    if kind == "reviewed" and not any(r["kind"] == "checked" for r in after):
        raise _Refused(
            f"'{part}' has no `checked` receipt on its current hash since the last reopened or locked"
        )
    if kind == "reviewed" and record is not None:
        highest = max((r["review"]["round"] for r in since if r["kind"] == "reviewed"), default=0)
        if record["round"] < highest:
            raise _Refused(f"round {record['round']} is older than round {highest}: record a new round")
        said = next(  # a `fix` or `engineer` of this round (any hash) is overturned only by a higher round
            (
                r["review"]["verdict"]
                for r in reversed(since)
                if r["kind"] == "reviewed"
                and r["review"]["round"] == record["round"]
                and r["review"]["verdict"] != "pass"
            ),
            None,
        )
        if record["verdict"] == "pass" and said is not None:
            raise _Refused(f"round {record['round']} said {said}: record round {record['round'] + 1}")
    if kind == "locked":
        review = _latest_review(since)
        if review is None:
            raise _Refused(
                f"'{part}' has no passing `reviewed` receipt on its current hash since the last {_RESET}"
            )
        shown = f"round {review['review']['round']}, verdict {review['review']['verdict']}"
        if review["review"]["verdict"] != "pass":
            raise _Refused(
                f"'{part}' has no passing review on its current hash since the last {_RESET} "
                f"(latest review: {shown})"
            )
        if review["part_hash"] != current:
            raise _Refused(
                f"'{part}' has no passing review on its current hash since the last {_RESET} "
                f"(latest review: {shown}, recorded on another hash)"
            )
        unlocked = _unlocked_inputs(states, part)
        if unlocked:
            raise _Refused(f"input part(s) not locked: {', '.join(unlocked)}")
    if kind == "reopened" and not (latest and latest["kind"] == "locked"):
        raise _Refused(f"part '{part}' is not locked: only a locked part is reopened")


def _write_atomic(work: Path, part: str, doc: dict[str, Any]) -> None:
    found = validate("part-receipts", doc)
    if found:
        raise ReceiptError("; ".join(f"{p.path}: {p.message}" for p in found))
    target = work / receipts_rel(part)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=target.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        Path(tmp_name).replace(target)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def write_part_receipt(
    work_dir: Path | str,
    part: str,
    kind: str,
    *,
    review: str | None = None,
    review_round: int | None = None,
    verdict: str | None = None,
    reason: str | None = None,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Append one receipt of `kind` to `parts/<part>/receipts.json` and return the output document of
    `harness part receipt` (`$defs.receipt` of `part-output`: `written`, `receipt`, `refused`, `problems`).

    The part hash is the current one. A receipt of the same kind and hash as the latest (for `reviewed` also
    the same round, review file and verdict; for `locked` also the same input hashes) is not written again:
    `written` false, `receipt` the recorded one; a `locked` one whose input parts are not locked is refused
    instead. A failed precondition writes nothing: `receipt` null, `refused` the reason, `problems` the
    check's when `part check` was the reason. Preconditions: `checked` and `locked` pass `part check`, and
    `checked` is not on a locked part; `reviewed` needs a `checked` receipt on the current hash after the
    last `reopened` or `locked`, a round not lower than a `reviewed` receipt recorded since then (any
    hash), and, for a `pass`, a round no `fix` or `engineer` receipt recorded since then (any hash) has
    (a higher round overturns it; the same round with the same verdict is "already recorded"); `locked`
    needs the latest `reviewed` receipt since the last `reopened` or `locked`, whatever its hash, to be a
    `pass` on the current hash and every input part `locked` (their hashes are stored);
    `reopened` needs a locked part. Raises ReaderError (2: flags that do not go with `kind`; 3: an
    `OSError`; 1: the output document is invalid, "internal error"), ManifestAccessError and ReceiptError
    (the receipt built does not satisfy its schema: a bug; the command maps it to exit 1)."""
    _usage(kind, review, review_round, verdict, reason)
    work = Path(work_dir)
    try:
        try:
            states = PartStates(work)
            current = states.hash(part)
        except ReaderError as exc:
            if exc.exit_code != EXIT_INVALID:
                raise
            raise _Refused(
                str(exc), list(_check(work, part)["problems"]) if kind in ("checked", "locked") else None
            ) from exc
        receipts = read_receipts(work, part)
        record = None
        if review is not None and review_round is not None and verdict is not None:
            record = _review_record(work, part, review, review_round, verdict)
        latest = receipts[-1] if receipts else None
        wanted = _input_hashes(states, part) if kind == "locked" else None
        recorded = latest if _same_stage(latest, kind, current, record, wanted) else None
        if recorded is None:
            _preconditions(kind, part, receipts, current, states, work, record)
        elif kind == "locked" and (unlocked := _unlocked_inputs(states, part)):
            raise _Refused(
                f"'{part}' is locked (receipt {recorded['n']}) but its input part(s) are not locked: "
                f"{', '.join(unlocked)}: it reads locked again when they are locked on the hashes it stored"
            )
    except _Refused as refusal:
        return _output(part, kind, None, written=False, refused=str(refusal), problems=refusal.problems)
    except ReaderError as exc:
        if (
            exc.exit_code != EXIT_INVALID
        ):  # ReceiptsInvalid and the record documents: refused, never rewritten
            raise
        return _output(part, kind, None, written=False, refused=str(exc))
    if recorded is not None:  # outside the try: an "internal error" of the output is not a refusal
        return _output(part, kind, recorded, written=False)
    moment = (now or (lambda: datetime.now(UTC)))().astimezone(UTC)
    new: dict[str, Any] = {
        "n": len(receipts) + 1,
        "kind": kind,
        "part_hash": current,
        "at": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tool_version": __version__,
        "review": record,
        "reason": reason if kind == "reopened" else None,
        "inputs": wanted,
    }
    out = _output(part, kind, new, written=True)  # checked before anything is written
    _write_atomic(work, part, {"schema_version": "0.1", "part": part, "receipts": [*receipts, new]})
    return out
