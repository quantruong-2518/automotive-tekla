"""part_sums: the hand-sum checks (hand_sum_invalid, hand_sum_mismatch) of `harness part check`.

A count a reader adds up by hand is written as `hand_sum.terms` and recomputed here, so a wrong sum cannot be
locked. A term is one of:

- `{finding, of}`: a measured finding, its number of `evidence.items` (`items`) or the sum of their
  `symbols` (`symbols`);
- `{marks: M}`: the plan marks of `marks.json` equal to M (NFC, casefold) on the row's file and sheet;
- `{entry: T}`: the one standalone integer of the text of entry T of the row's file (an entry that is
  font-blocked or not printed cannot be added: font-blocked text is quoted, never read).

A term id gets the checks of a row cite (`part_cites`): `cite_inactive` (a withdrawn finding), `cite_stale`,
`cite_foreign_part` (a finding held by neither the part nor an input; untagged counts as foreign) and
`entry_outside_part` (an entry in no sheet or cluster of the part or its inputs), each [row, finding or entry
id] with the text of the row cite. A hand sum that needs another part's rows lists that part as an input.
`hand_sum_invalid` [row, finding or entry id or None]: a term that cannot be added (a finding without
`evidence`, an item without `symbols` for `symbols`, a `marks` term on a row without `sheet` or with no
`marks.json`, an entry that is font-blocked or not printed, an entry text without exactly one standalone
integer). A term that names a finding or an entry
that does not exist is `cite_unknown`. With any of these problems the total is undefined, so no mismatch is
raised.
`hand_sum_mismatch` [row, None]: `_numbers(value)` is not exactly `[total]` ("7 pcs" passes, "7 of 12" does
not); the detail lists each addend. A row whose value is null has nothing to compare.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterator, Mapping
from typing import Any

from tekla_harness import part_cites
from tekla_harness.findings import _NUMBER, _TIMES, _numbers
from tekla_harness.part_values import Entry, PartContext, Problem


def _fold(mark: str) -> str:
    return unicodedata.normalize("NFC", mark).casefold()


def _fmt(n: float) -> str:
    return str(int(n)) if float(n).is_integer() else str(n)


def _finding_term(
    findings: Mapping[str, dict[str, Any]], row_id: str, term: dict[str, Any]
) -> tuple[int | None, str, Problem | None]:
    fid, of = term["finding"], term["of"]
    finding = findings.get(fid)
    if finding is None:
        return None, "", Problem("cite_unknown", row_id, fid, f"hand_sum term: there is no finding {fid}")
    evidence = finding.get("evidence")
    if evidence is None:
        detail = f"hand_sum term: finding {fid} has no evidence (only a measured finding can be added up)"
        return None, "", Problem("hand_sum_invalid", row_id, fid, detail)
    items = evidence["items"]
    if of == "items":
        return len(items), f"{fid} items: {len(items)}", None
    missing = [i["id"] for i in items if i.get("symbols") is None]
    if missing:
        detail = f"hand_sum term: items of {fid} without symbols: {', '.join(missing)}"
        return None, "", Problem("hand_sum_invalid", row_id, fid, detail)
    total = sum(i["symbols"] for i in items)
    return total, f"{fid} symbols: {total}", None


def _marks_term(
    marks_doc: dict[str, Any] | None, row: dict[str, Any], term: dict[str, Any]
) -> tuple[int | None, str, Problem | None]:
    mark, sheet = term["marks"], row.get("sheet")

    def invalid(why: str) -> tuple[None, str, Problem]:
        return None, "", Problem("hand_sum_invalid", row["row"], None, f"hand_sum term marks '{mark}': {why}")

    if sheet is None:
        return invalid("the row has no sheet to count the marks on")
    if marks_doc is None:
        return invalid("marks.json is missing (run `harness marks`)")
    wanted = _fold(mark)
    count = sum(
        p["file"] == row.get("file") and p["sheet"] == sheet and _fold(p["mark"]) == wanted
        for p in marks_doc["plan_marks"]
    )
    return count, f"marks {mark} on {sheet}: {count}", None


def _entry_term(
    entries: Mapping[tuple[str, str], Entry], row: dict[str, Any], term: dict[str, Any]
) -> tuple[int | None, str, Problem | None]:
    tid, file = term["entry"], row.get("file")
    entry = entries.get((file, tid)) if file is not None else None
    if entry is None:
        where = f"in {file}" if file is not None else "(the row has no file to look in)"
        return (
            None,
            "",
            Problem("cite_unknown", row["row"], tid, f"hand_sum term: there is no entry {tid} {where}"),
        )
    text, allowed, printed, _ = entry
    if not allowed or not printed:
        why = "is font-blocked: its text is quoted, never read" if not allowed else "is not printed"
        return None, "", Problem("hand_sum_invalid", row["row"], tid, f"hand_sum term: entry {tid} {why}")
    found = [m[1] for m in _NUMBER.finditer(_TIMES.sub(" ", text))]
    if len(found) != 1 or "." in found[0]:
        detail = (
            f"hand_sum term: the text of {tid} ('{text}') must hold exactly one standalone integer; "
            f"it holds {', '.join(found) if found else 'none'}"
        )
        return None, "", Problem("hand_sum_invalid", row["row"], tid, detail)
    return int(found[0]), f"{tid} '{text}': {found[0]}", None


def _terms(
    findings: Mapping[str, dict[str, Any]],
    marks_doc: dict[str, Any] | None,
    entries: Mapping[tuple[str, str], Entry],
    row: dict[str, Any],
) -> Iterator[tuple[dict[str, Any], int | None, str, Problem | None]]:
    """Per term of the row: (the term, its value, its addend text, its problem). The one term arithmetic."""
    for term in row["hand_sum"]["terms"]:
        if "finding" in term:
            yield (term, *_finding_term(findings, row["row"], term))
        elif "marks" in term:
            yield (term, *_marks_term(marks_doc, row, term))
        else:
            yield (term, *_entry_term(entries, row, term))


def hand_sum_addends(
    row: dict[str, Any],
    findings: Mapping[str, dict[str, Any]],
    marks_doc: dict[str, Any] | None,
    entry_text: Mapping[tuple[str, str], str],
) -> list[tuple[str, int]]:
    """(term text, value) per term of the row's `hand_sum`, in term order, from plain documents: the active
    findings by id, `marks.json` or None, and the text of the readable, printed entries by (file, id).
    `[]` when the row has no `hand_sum` or when any term is invalid or unknown (never a partial list)."""
    if "hand_sum" not in row:
        return []
    entries: dict[tuple[str, str], Entry] = {k: (v, True, True, None) for k, v in entry_text.items()}
    addends: list[tuple[str, int]] = []
    for term, n, _, problem in _terms(findings, marks_doc, entries, row):
        if problem is not None or n is None:
            return []
        if "finding" in term:
            label = f"{term['finding']} {term['of']}"
        elif "marks" in term:
            label = f"marks {term['marks']}"
        else:
            label = term["entry"]
        addends.append((label, n))
    return addends


def hand_total(ctx: PartContext, row: dict[str, Any]) -> tuple[int | None, list[str], list[Problem]]:
    """(the total of the row's terms, one addend text per term, the problems of the terms). The total is None
    when any term has a problem."""
    total, addends, problems = 0, [], []
    for _, n, text, problem in _terms(ctx.findings, ctx.marks, ctx.entries, row):
        if problem is not None:
            problems.append(problem)
        elif n is not None:
            total += n
            addends.append(text)
    return (None if problems else total), addends, problems


def _cite_problems(ctx: PartContext, row: dict[str, Any], held: set[str]) -> list[Problem]:
    """The row-cite problems of the finding and entry ids of the terms that exist (`cite_unknown` is
    `hand_total`'s): withdrawn, stale, another part's, outside the part."""
    problems: list[Problem] = []
    for term in row["hand_sum"]["terms"]:
        if "finding" in term and term["finding"] in ctx.findings:
            problems += part_cites._finding_problems(ctx, row["row"], term["finding"], held)
        elif "entry" in term:
            file, tid = row.get("file"), term["entry"]
            if file is not None and (file, tid) in ctx.entries and not part_cites._in_scope(ctx, file, tid):
                detail = f"{tid} is in no sheet or cluster of {ctx.part} or its inputs"
                problems.append(Problem("entry_outside_part", row["row"], tid, detail))
    return problems


def sum_problems(ctx: PartContext) -> list[Problem]:
    found: list[Problem] = []
    held = part_cites._held(ctx)
    for row in ctx.rows:
        if "hand_sum" not in row:
            continue
        total, addends, problems = hand_total(ctx, row)
        found += problems
        cited = _cite_problems(ctx, row, held)
        found += cited
        value = row["value"]
        if cited or total is None or value is None:
            continue
        numbers = _numbers(value)
        if numbers != [float(total)]:
            shown = ", ".join(_fmt(n) for n in numbers) or "none"
            detail = (
                f"the value '{value}' holds the numbers {shown}, the hand sum is {total} = "
                + " + ".join(addends)
            )
            found.append(Problem("hand_sum_mismatch", row["row"], None, detail))
    return found
