"""`harness part answer-key` and `harness part score` (E9b, C11): the engineer's verdicts on sampled rows, and
the score of a work folder against them.

`answer-key W --part X --row R --verdict ok|wrong|cannot_tell --by NAME [--correct V] [--text T]` records one
verdict in `W/answer-key.json` (schema `answer-key`, `kind: answer_key`). It takes only a row of
`W/parts/X/spotcheck.json` whose `part_hash` is the part's current hash, and only while the part is `locked`.
The key of a verdict is (part, file, sheet, mark or subject in NFC, casefolded, single-spaced; field), never a
row or finding id, so a reread with new ids is still scored. The sampled row is checked against the part's
`values.json` (`spotcheck.json` is not covered by the part hash): a row that differs is `spotcheck_stale`, and
a row whose key is shared with another `seen` row of a different value is `key_ambiguous` (exit 1): the score
could not tell them apart. A new verdict on a key supersedes the active one; one that repeats the active
verdict (same verdict, correct value and value shown) writes nothing. Each verdict keeps the `part_hash` and
the `seed` of the sample it judged. `--by` is kept as given.

`score W [--answer-key FILE]` is read-only. For each active key it compares the work folder's current rows
with the expected value (the value shown for `ok`, the correct value for `wrong`): `cannot_tell` is counted
apart, a key with no current row (a `seen` row with a value) is `missing`, and it is `agree` only when every
such row under the key has the same value (`part_values.same_value`), else `differ`. A part whose manifest,
row listing or `values.json` cannot be used gives `missing` for each of its keys, with one stderr line.
`--answer-key` may name a copy outside the work folder (a benchmark). The exit is 0 whatever the `differ`
count, 1 for a key file that is missing or invalid (two active verdicts under one key included), or a manifest
that is there but unusable.

Exit codes: 0 ok, 1 invalid (see above), 2 usage, 3 the operating system refused a file. Stdout is the
`answer_key` or `score` definition of `part-output`. The lock of `answer-key` is taken by `cli`.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from tekla_harness.part_receipts import PartStates
from tekla_harness.part_sample import _manifest
from tekla_harness.part_values import ContextStop, Problem, read_values, same_value
from tekla_harness.parts import ManifestAccessError, manifest_present
from tekla_harness.parts_manifest import _os_errors_are_environment, _read_manifest
from tekla_harness.questions import dump_json, write_text_atomic
from tekla_harness.schemas import validate
from tekla_harness.sheet_text import ReaderError, load_inventory
from tekla_harness.strict_json import StrictJsonError, loads_strict

EXIT_OK, EXIT_INVALID, EXIT_USAGE, EXIT_ENV = 0, 1, 2, 3
KEY_NAME, SPOT_NAME = "answer-key.json", "spotcheck.json"
COUNTS = ("agree", "differ", "missing", "cannot_tell")
Key = tuple[str, str | None, str | None, str, str]


def _key(part: str, file: str | None, sheet: str | None, who: str, field: str) -> Key:
    """The key of a reading: the mark or subject in NFC, casefolded, with one space between words."""
    return (part, file, sheet, " ".join(unicodedata.normalize("NFC", who).casefold().split()), field)


def _key_of_answer(r: dict[str, Any]) -> Key:
    return _key(r["part"], r["file"], r["sheet"], r["subject"], r["field"])


def key_index(part: str, rows: list[dict[str, Any]]) -> dict[Key, list[tuple[str, str]]]:
    """(row id, value) of the `seen` rows of `part` that have a value, by key. An `asked` row may carry a
    candidate value; it is no reading and does not count."""
    index: dict[Key, list[tuple[str, str]]] = {}
    for r in rows:
        if r["state"] == "seen" and r.get("value") is not None:
            k = _key(part, r.get("file"), r.get("sheet"), r.get("mark") or r["subject"], r["field"])
            index.setdefault(k, []).append((r["row"], str(r["value"])))
    return index


def _all_same(items: list[tuple[str, str]]) -> bool:
    return all(same_value(a[1], b[1]) for i, a in enumerate(items) for b in items[i + 1 :])


def ambiguous_rows(part: str, rows: list[dict[str, Any]]) -> list[str]:
    """The ids of the `seen` rows whose key is shared with a row of a different value, in file order: the
    score cannot tell such rows apart, so they are never sampled and `answer-key` refuses them."""
    bad = {id_ for items in key_index(part, rows).values() if not _all_same(items) for id_, _ in items}
    return [r["row"] for r in rows if r["row"] in bad]


def _read_document(path: Path, kind: str, *, missing_ok: bool = False) -> dict[str, Any] | None:
    """The `answer-key` document at `path` of the given `kind`. Raises ReaderError (1: not found, not strict
    JSON, not the schema or another kind; 3: an OSError). None when `missing_ok` and it is not there."""
    try:
        data = path.read_bytes()
    except (FileNotFoundError, NotADirectoryError):
        if missing_ok:
            return None
        raise ReaderError(EXIT_INVALID, f"key file not found: {path}") from None
    except IsADirectoryError:
        raise ReaderError(EXIT_INVALID, f"key file is not a file: {path}") from None
    except OSError as exc:
        raise ReaderError(EXIT_ENV, f"cannot read {path} ({exc})") from exc
    try:
        doc = loads_strict(data)
    except StrictJsonError as exc:
        raise ReaderError(EXIT_INVALID, f"{path} is not valid JSON: {exc}") from exc
    found = validate("answer-key", doc)
    if found:
        raise ReaderError(
            EXIT_INVALID, f"{path} is invalid (answer-key): {found[0].path or '/'}: {found[0].message}"
        )
    if doc["kind"] != kind:
        raise ReaderError(EXIT_INVALID, f"{path} is invalid: kind is '{doc['kind']}', not '{kind}'")
    active: set[Key] = set()
    for r in doc["rows"] if kind == "answer_key" else []:
        if r["status"] == "active" and _key_of_answer(r) in active:
            raise ReaderError(
                EXIT_INVALID,
                f"{path} is invalid: two active verdicts under one key: "
                + ", ".join(str(x) for x in _key_of_answer(r)),
            )
        if r["status"] == "active":
            active.add(_key_of_answer(r))
    return doc  # type: ignore[no-any-return]


def _checked(doc: dict[str, Any], name: str) -> dict[str, Any]:
    found = validate("part-output", doc)
    if found:
        shown = "; ".join(f"{p.path}: {p.message}" for p in found[:3])
        raise ReaderError(EXIT_INVALID, f"internal error: {name} output is invalid: {shown}")
    return doc


# --- answer-key --------------------------------------------------------------------------------------------


def _sampled_row(
    work: Path, states: PartStates, part: str, row_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The sample (`spotcheck.json`) and its row the verdict is about. Raises ContextStop (`row_not_sampled`,
    `spotcheck_stale`) and ReaderError."""
    spot = _read_document(work / "parts" / part / SPOT_NAME, "spotcheck", missing_ok=True)
    held = None if spot is None else next((r for r in spot["rows"] if r["row"] == row_id), None)
    if spot is None or spot["part"] != part or held is None:
        raise ContextStop(
            [
                Problem(
                    "row_not_sampled", row_id, part, f"{row_id} is not in parts/{part}/{SPOT_NAME}: sample it"
                )
            ]
        )
    if spot["part_hash"] != states.hash(part):
        raise ContextStop(
            [
                Problem(
                    "spotcheck_stale",
                    row_id,
                    part,
                    f"parts/{part}/{SPOT_NAME} was drawn at another part hash: run `part spotcheck` again",
                )
            ]
        )
    return spot, held


def _stale(part: str, row_id: str, why: str) -> ContextStop:
    return ContextStop(
        [
            Problem(
                "spotcheck_stale", row_id, part, f"parts/{part}/{SPOT_NAME} {why}: run `part spotcheck` again"
            )
        ]
    )


def _checked_against_values(
    work: Path, manifest: dict[str, Any], part: str, shown: dict[str, Any]
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    """The row of the part's `values.json` that the sampled row stands for, and the (row id, value) of all
    rows under its key. Raises ContextStop: `spotcheck_stale` when the file or the row's content differs from
    the sampled row (the part hash does not cover `spotcheck.json`), `key_ambiguous` when the key is shared
    with a row of a different value."""
    row_id = shown["row"]
    listed = next((p for p in manifest["parts"] if p["id"] == part), None)
    values, problems = read_values(work, part, listed["kind"] if listed else "")
    if values is None:
        raise ContextStop(problems)
    held = next((r for r in values["rows"] if r["row"] == row_id), None)

    def identity(r: dict[str, Any]) -> tuple[Any, ...]:
        who = ("mark", r["mark"]) if "mark" in r else ("subject", r["subject"])
        return (who, r["field"], r.get("value"), r.get("file"), r.get("sheet"))

    if held is None or held["state"] != "seen" or identity(held) != identity(shown):
        raise _stale(part, row_id, f"row {row_id} differs from the part's values.json")
    key = _key(part, held.get("file"), held.get("sheet"), held.get("mark") or held["subject"], held["field"])
    items = key_index(part, values["rows"])[key]
    if not _all_same(items):
        ids = ", ".join(i for i, _ in items)
        raise ContextStop(
            [
                Problem(
                    "key_ambiguous",
                    row_id,
                    part,
                    f"rows {ids} share this key with different values: the score cannot tell them apart",
                )
            ]
        )
    return held, items


def record_verdict(
    work_dir: str, part: str, row_id: str, verdict: str, by: str, correct: str | None, text: str | None
) -> dict[str, Any]:
    """Record the verdict and return the stdout document. Raises ContextStop, ReaderError,
    ManifestAccessError and OSError."""
    work, manifest = _manifest(work_dir)
    states = PartStates(work, manifest)
    status = states.status(part)
    if status != "locked":
        raise ContextStop(
            [Problem("part_not_locked", None, part, f"part '{part}' is {status}, not locked: nothing to key")]
        )
    spot, shown = _sampled_row(work, states, part, row_id)
    if shown["file"] is None:
        raise ReaderError(EXIT_INVALID, f"harness part answer-key: {row_id} row names no file: it has no key")
    held, _ = _checked_against_values(work, manifest, part, shown)
    key = _key(part, held["file"], held.get("sheet"), held.get("mark") or held["subject"], held["field"])
    path = work / KEY_NAME
    doc = _read_document(path, "answer_key", missing_ok=True) or {
        "schema_version": "0.1", "kind": "answer_key", "rows": [],
    }  # fmt: skip
    active = [r for r in doc["rows"] if r["status"] == "active" and _key_of_answer(r) == key]
    out = {
        "command": "answer_key", "written": False, "superseded": 0,
        "key": {"part": key[0], "file": key[1], "sheet": key[2], "subject": key[3], "field": key[4]},
    }  # fmt: skip
    if any(
        r["verdict"] == verdict and r["correct"] == correct and r["value_shown"] == held["value"]
        for r in active
    ):
        return _checked(out, "answer_key")
    for r in active:
        r["status"] = "superseded"
    doc["rows"].append(
        {
            "part": key[0], "file": key[1], "sheet": key[2], "subject": key[3], "field": key[4],
            "row": row_id, "verdict": verdict, "correct": correct, "engineer_text": text or None,
            "by": by, "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "value_shown": held["value"], "status": "active", "part_hash": spot["part_hash"],
            "seed": spot["seed"],
        }
    )  # fmt: skip
    found = validate("answer-key", doc)
    if found:
        shown_problems = "; ".join(f"{p.path}: {p.message}" for p in found[:3])
        raise ReaderError(EXIT_INVALID, f"internal error: answer-key.json is invalid: {shown_problems}")
    out.update(written=True, superseded=len(active))
    _checked(out, "answer_key")
    write_text_atomic(path, dump_json(doc))
    return out


def run_answer_key(args: argparse.Namespace) -> int:
    """The handler of `harness part answer-key` (the lock is taken by `cli`)."""
    if args.verdict == "wrong":
        if args.correct is None or not args.correct.strip():
            print(
                "harness part answer-key: usage: --correct is required with --verdict wrong", file=sys.stderr
            )
            return EXIT_USAGE
    elif args.correct is not None:
        print(
            f"harness part answer-key: usage: --correct is only for --verdict wrong, not {args.verdict}",
            file=sys.stderr,
        )
        return EXIT_USAGE
    try:
        out = record_verdict(
            args.work_dir, args.part, args.row, args.verdict, args.by, args.correct, args.text
        )
    except ContextStop as stop:
        for p in stop.problems:
            print(f"harness part answer-key: {p.code}: {p.detail}", file=sys.stderr)
        return EXIT_INVALID
    except ReaderError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except ManifestAccessError as exc:
        print(f"harness part answer-key: {exc}", file=sys.stderr)
        return EXIT_ENV
    except OSError as exc:
        print(f"harness part answer-key: cannot read or write the work folder: {exc}", file=sys.stderr)
        return EXIT_ENV
    print(json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False))
    return EXIT_OK


# --- score -------------------------------------------------------------------------------------------------


def _current_values(
    work: Path, manifest: dict[str, Any] | None, part: str, notes: list[str]
) -> dict[Key, list[str]]:
    """The values of the `seen` rows of `part` by key; empty, and one note, when they cannot be read."""
    if manifest is None:
        notes.append(f"part {part}: parts/manifest.json is missing: every key of the part is missing")
        return {}
    listed = next((p for p in manifest["parts"] if p["id"] == part), None)
    if listed is None:
        notes.append(f"part {part}: not in parts[] of the manifest: every key of the part is missing")
        return {}
    values, problems = read_values(work, part, listed["kind"])
    if values is None:
        notes.append(f"part {part}: {problems[0].detail}: every key of the part is missing")
        return {}
    return {k: [v for _, v in items] for k, items in key_index(part, values["rows"]).items()}


def _verdict_of(r: dict[str, Any], current: dict[Key, list[str]]) -> str:
    if r["verdict"] == "cannot_tell":
        return "cannot_tell"
    values = current.get(_key_of_answer(r))
    if not values:
        return "missing"
    expected = r["value_shown"] if r["verdict"] == "ok" else r["correct"]
    return "agree" if all(same_value(expected, v) for v in values) else "differ"


def build_score(work_dir: str, key_file: str | None, notes: list[str]) -> dict[str, Any]:
    """The `score` document; `notes` gets the stderr lines. Raises ReaderError and ManifestAccessError."""
    with _os_errors_are_environment():
        work = load_inventory(work_dir).work
    path = Path(key_file) if key_file else work / KEY_NAME
    doc = cast(dict[str, Any], _read_document(path, "answer_key"))
    manifest = None
    if manifest_present(work):
        manifest, found = _read_manifest(work)
        if manifest is None:
            raise ReaderError(
                EXIT_INVALID, "parts/manifest.json is not usable: " + "; ".join(p[4] for p in found[:3])
            )
    active = [r for r in doc["rows"] if r["status"] == "active"]
    parts = []
    for part in sorted({r["part"] for r in active}):
        current = _current_values(work, manifest, part, notes)
        tally: dict[str, int] = dict.fromkeys(COUNTS, 0)
        for r in active:
            if r["part"] == part:
                tally[_verdict_of(r, current)] += 1
        parts.append({"part": part, "checked": sum(tally.values()), **tally})
    total = {"checked": sum(p["checked"] for p in parts)} | {c: sum(p[c] for p in parts) for c in COUNTS}
    out = {"command": "score", "answer_key": str(path.resolve()), "parts": parts, "total": total}
    return _checked(out, "score")


def run_score(args: argparse.Namespace) -> int:
    """The handler of `harness part score` (read-only: no lock)."""
    notes: list[str] = []
    try:
        out = build_score(args.work_dir, args.answer_key, notes)
    except ReaderError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except ManifestAccessError as exc:
        print(f"harness part score: {exc}", file=sys.stderr)
        return EXIT_ENV
    except OSError as exc:
        print(f"harness part score: cannot read the work folder: {exc}", file=sys.stderr)
        return EXIT_ENV
    for line in notes:
        print(f"harness part score: {line}", file=sys.stderr)
    print(json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False))
    return EXIT_OK
