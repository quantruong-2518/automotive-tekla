"""part_check: `harness part check W --part X`, the gate that proves every row of `W/parts/X/values.json`.

Read-only. `check_part(work, part)` returns the `part-output` document `$defs.check`:
`{command: "check", part, hash, ok, counts, problems: [{code, row, id, detail}]}`, problems sorted by
all four fields (null first). `hash` is the part hash of `part_receipts` (what a receipt binds to), null
when the check stops at `manifest_invalid`, `part_unknown` or `input_invalid` (or at `values_invalid` with a
malformed record document: the hash reads them). The row checks of this module are the
structure of the file: duplicate rows, the rules of each state, and the sheets a row may be read on. The
checks of the citations, numbers, hand sums and text rules live in `part_cites`, `part_numbers`,
`part_sums` and `part_rules`; each takes the `PartContext` and returns its problems, which are merged here.

Stops (the problem is the whole answer, counts are zero): `manifest_invalid`, `part_unknown`,
`values_invalid`, `input_invalid` (a findings, questions, registry, marks or grid-systems document that is
not JSON or fails its schema). Exit codes (see `parts_manifest._run_check`): 0 ok, 1 any problem (always with
the JSON document), 2 usage (a part id that does not match the pattern, no work folder or inventory.json),
3 the operating system refused a file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tekla_harness import part_cites, part_numbers, part_receipts, part_rules, part_sums
from tekla_harness.part_values import ContextStop, PartContext, Problem, load_context
from tekla_harness.parts_manifest import _read_manifest
from tekla_harness.schemas import validate
from tekla_harness.sheet_text import ReaderError

EXIT_INVALID = 1
STATES = ("seen", "asked", "unread", "absent")
# Every code a check raises (E5a's, then the text-rule codes of `part_rules`); equal to the schema's enum.
PROBLEM_CODES = (
    "manifest_invalid", "part_unknown", "values_invalid", "input_invalid", "row_duplicate", "row_state",
    "row_outside_part",
    "cite_unknown", "cite_inactive", "cite_stale", "cite_foreign_part",
    "entry_blocked", "entry_not_printed", "entry_outside_part",
    "number_unbacked", "token_unbacked", "hand_sum_invalid", "hand_sum_mismatch",
    "sheet_uncovered", "mark_missing", "marks_regex_invalid", "listed_needs_blocking",
    "listed_question_not_blocking", "low_without_question", "claim_form", "note_item_prefix",
    "search_unaccented", "family_linework_twice", "family_linework_needless", "value_not_verbatim",
    "note_quote_unmatched",
)  # fmt: skip


def _cites(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("cites", {})  # type: ignore[no-any-return]


def _duplicates(rows: list[dict[str, Any]]) -> list[Problem]:
    problems: list[Problem] = []
    ids: dict[str, int] = {}
    keys: dict[tuple[Any, ...], str] = {}
    for r in rows:
        ids[r["row"]] = ids.get(r["row"], 0) + 1
        if ids[r["row"]] > 1:
            problems.append(Problem("row_duplicate", r["row"], None, "the row id is used twice"))
            continue
        subject = ("mark", r["mark"]) if "mark" in r else ("subject", r["subject"])
        key = (r.get("file"), r.get("sheet"), subject, r["field"])
        if key in keys:
            problems.append(
                Problem(
                    "row_duplicate",
                    r["row"],
                    None,
                    f"same file, sheet, {subject[0]} and field as {keys[key]}",
                )
            )
        else:
            keys[key] = r["row"]
    return problems


def _state_reasons(r: dict[str, Any]) -> list[str]:
    cites, state, value = _cites(r), r["state"], r["value"]
    questions, findings = cites.get("questions"), cites.get("findings")
    reasons: list[str] = []
    if state == "seen":
        if value is None:
            reasons.append("seen needs a value")
        if r.get("file") is None:
            reasons.append("seen needs a file")
        if not (findings or cites.get("entries") or cites.get("geometry") or r.get("hand_sum")):
            reasons.append("seen needs a finding, entry, geometry or hand_sum")
    elif state == "asked":
        if not questions:
            reasons.append("asked needs a question")
    elif state == "unread":
        if value is not None:
            reasons.append("unread has no value")
        if not questions:
            reasons.append("unread needs a question")
    elif state == "absent":
        if value is not None:
            reasons.append("absent has no value")
        if not (findings or questions):
            reasons.append("absent needs a finding or a question holding the search record")
    return reasons


def _outside_reasons(ctx: PartContext, r: dict[str, Any]) -> list[str]:
    file, sheet = r.get("file"), r.get("sheet")
    reasons: list[str] = []
    if file is not None and sheet is not None and (file, sheet) not in ctx.own.row_sheets:
        where = " (only an input part lists it)" if (file, sheet) in ctx.inputs.row_sheets else ""
        reasons.append(f"sheet {sheet} of {file} is not in the part's sheets, tables or clusters{where}")
    if (
        file is not None
        and sheet is None
        and not any(f == file and s is None for f, s, _ in ctx.own.clusters)
    ):
        reasons.append(f"the part lists no cluster outside the sheets of {file}")
    listed = ctx.views.get((file, sheet), []) if file is not None and sheet is not None else []
    if "view" in r and r["view"] not in listed:
        reasons.append("the view is not one of the views[] the manifest lists for that sheet")
    return reasons


def _row_problems(ctx: PartContext) -> list[Problem]:
    problems = _duplicates(ctx.rows)
    for r in ctx.rows:
        if reasons := _state_reasons(r):
            problems.append(Problem("row_state", r["row"], None, "; ".join(reasons)))
        if reasons := _outside_reasons(ctx, r):
            problems.append(Problem("row_outside_part", r["row"], None, "; ".join(reasons)))
    return problems


def _document(
    part: str, problems: list[Problem], ctx: PartContext | None, digest: str | None
) -> dict[str, Any]:
    states = [r["state"] for r in ctx.rows] if ctx else []
    doc: dict[str, Any] = {
        "command": "check",
        "part": part,
        "hash": digest,
        "ok": not problems,
        "counts": {
            "rows": len(states),
            **{s: states.count(s) for s in STATES},
            "findings": sum(f["status"] == "active" and f.get("part") == part for f in ctx.findings.values())
            if ctx
            else 0,
            # the obsolete filter guards a hand-edited ledger: `withdraw_question` removes the question
            "questions": sum(
                part in q.get("parts", []) and ctx.registry.get(q["id"], {}).get("status") != "obsolete"
                for q in ctx.questions.values()
            )
            if ctx
            else 0,
        },
        "problems": [p.as_dict() for p in sorted(problems, key=Problem.sort_key)],
    }
    invalid = validate("part-output", doc)
    if invalid:
        shown = "; ".join(f"{p.path}: {p.message}" for p in invalid[:3])
        raise ReaderError(EXIT_INVALID, f"internal error: output is invalid: {shown}")
    return doc


def _stopped_hash(work: Path, part: str, stop: ContextStop) -> str | None:
    """The hash of a check that stopped: None unless the stop is `values_invalid` (the manifest is usable and
    lists the part then) and the record documents the hash reads are valid (else None, never an exit 1 with
    no JSON)."""
    if stop.problems[0].code != "values_invalid":
        return None
    manifest, _ = _read_manifest(work.resolve())
    if manifest is None:
        return None
    try:
        return part_receipts.part_hash(work, manifest, part)
    except ReaderError as exc:
        if exc.exit_code == EXIT_INVALID:
            return None
        raise


def check_part(work_dir: Path | str, part: str) -> dict[str, Any]:
    """The check document of one part. Raises ReaderError (usage 2, environment 3) and ManifestAccessError
    (3); an unusable document is a stop problem in the returned document."""
    try:
        ctx = load_context(work_dir, part)
    except ContextStop as stop:
        return _document(part, stop.problems, None, _stopped_hash(Path(work_dir), part, stop))
    problems = _row_problems(ctx)
    for hook in (part_cites.cite_problems, part_numbers.number_problems, part_sums.sum_problems):
        problems += hook(ctx)
    problems += part_rules.text_problems(ctx)
    problems = list(dict.fromkeys(problems))  # a row that cites a record directly and in a hand_sum term
    return _document(part, problems, ctx, part_receipts.part_hash(ctx.work, ctx.manifest, part))
