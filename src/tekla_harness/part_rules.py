"""part_rules: the text-rule checks of `harness part check` (E5c, ADR-0019).

The reviewer's mechanical rubric as checks, so `part check` refuses what a reviewer would refuse for these
reasons. Own findings = active, `part` is the part; own questions = reader questions whose `parts` hold it.

- coverage: `sheet_uncovered` (an own sheet with no row and no own finding), `mark_missing` (a mark of
  `marks.json` on an own sheet that fullmatches `marks_regex` and has no row; the regex and the row compare
  are both case-blind),
  `marks_regex_invalid`;
- blocking questions on LISTED values (every `field` but `material` and `other`): `listed_needs_blocking`
  (a row `asked`, `unread`, `absent`, or `seen` on under two source keys, citing no blocking question),
  `listed_question_not_blocking`, `low_without_question`; a blocking question is a live one: an obsolete
  question counts for nothing, cited directly or through a finding;
- claim form: `claim_form` (`node:`, `basis:`, `alt:`), `note_item_prefix` (`block:`);
- `search_unaccented`: a search record (the whole word `searched`, then quoted terms) lacks the unaccented
  twin of a term that has accents;
- `family_linework_twice`, `family_linework_needless`;
- verbatim values: `value_not_verbatim`, `note_quote_unmatched` (quote checks ignore case).

Source keys of a row (the "two sources" rule): an entry is `("text", file, sheet or cluster)`; a cited
finding with `evidence`, or the row's `cites.geometry`, is `("linework", file, sheet)`; a cited finding
without evidence is `("text", its file, its sheet)`; a `hand_sum` is `("sum", file, sheet)`; a `high`
finding adds a second key. A key counts only when its source backs every number of the value. A
`count_plan` and a `count_schedule` row of one mark, both `seen`, with equal single numbers give each other
one extra key (an `asked` row's value is only a candidate reading). The finding's own `basis: two_sources`
is not read. A registry entry without `blocking` counts as blocking (as `harness status` does).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from tekla_harness.findings import FONT_QUESTION_CODES, _numbers, is_quote
from tekla_harness.part_values import PartContext, Problem, backs, sources

# Every `field` of part-values but `material` and `other` (tests keep it equal to the schema enum).
LISTED = frozenset(
    {
        "size", "thickness", "depth", "length", "count_plan", "count_schedule", "piles_per_member",
        "level", "level_top", "level_bottom", "axes", "start_axes", "end_axes", "spacing",
    }
)  # fmt: skip
FAMILY_LINEWORK = "reader_family_linework"
UNSETTLED = ("asked", "unread", "absent")
COUNT_FIELDS = ("count_plan", "count_schedule")
Key = tuple[str, str, str]

_CLAIM_PARTS = (
    ("node", re.compile(r"node:\s*\S")),
    ("basis", re.compile(r"basis:\s*(two_sources|single_source)\b")),
    ("alt", re.compile(r"alt:\s*\S")),
)
_SEARCH_WORD = re.compile(r"\bsearched\b", re.IGNORECASE)
_LSQ, _RSQ = "\N{LEFT SINGLE QUOTATION MARK}", "\N{RIGHT SINGLE QUOTATION MARK}"
_LDQ, _RDQ = "\N{LEFT DOUBLE QUOTATION MARK}", "\N{RIGHT DOUBLE QUOTATION MARK}"
_OPEN, _CLOSE = f"\"'{_LSQ}{_LDQ}", f"\"'{_RSQ}{_RDQ}"
_QUOTED = f"[{_OPEN}][^{_CLOSE}]+[{_CLOSE}]"  # as the prototype: any opening mark, any closing mark
_TERM_RUN = re.compile(rf"(?:{_QUOTED}[\s,]*)+")
_TERM = re.compile(f"[{_OPEN}]([^{_CLOSE}]+)[{_CLOSE}]")
_SPAN = re.compile(
    "|".join(
        (
            r"(?<!\w)'([^']{2,})'(?!\w)",
            r'"([^"]{2,})"',
            f"{_LSQ}([^{_RSQ}]{{2,}}){_RSQ}",
            f"{_LDQ}([^{_RDQ}]{{2,}}){_RDQ}",
        )
    )
)


def _fold(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


def _own_findings(ctx: PartContext) -> list[dict[str, Any]]:
    found = [f for f in ctx.findings.values() if f["status"] == "active" and f.get("part") == ctx.part]
    return sorted(found, key=lambda f: f["id"])


def _own_questions(ctx: PartContext) -> list[dict[str, Any]]:
    held = [q for q in ctx.questions.values() if ctx.part in q.get("parts", [])]
    return sorted(held, key=lambda q: q["id"])


def _blocks(ctx: PartContext, qid: str) -> bool | None:
    """True or False by the registry (a missing `blocking` is True); None for an id the registry lacks or
    whose question is obsolete (a withdrawn question blocks nothing and is not a "non-blocking" one)."""
    entry = ctx.registry.get(qid)
    if entry is None or entry.get("status") == "obsolete":
        return None
    return entry.get("blocking", True) is not False


def _cited_questions(ctx: PartContext, row: dict[str, Any]) -> list[tuple[str, str]]:
    """(question id, route) a row cites: directly, or through a cited finding."""
    cites = row.get("cites", {})
    found = [(q, "the row") for q in cites.get("questions", [])]
    for fid in cites.get("findings", []):
        found += [(q, fid) for q in ctx.findings.get(fid, {}).get("questions", [])]
    return found


# --- coverage ---------------------------------------------------------------------------------------------


def _sheet_uncovered(ctx: PartContext) -> list[Problem]:
    rows = {(r.get("file"), r.get("sheet")) for r in ctx.rows}
    held = rows | {(f["file"], f.get("sheet")) for f in _own_findings(ctx)}
    seen: set[tuple[str, str]] = set()
    problems: list[Problem] = []
    for s in ctx.part_row.get("sheets", []):
        pair = (s["file"], s["sheet"])
        if pair not in held and pair not in seen:
            seen.add(pair)
            detail = (
                f"{pair[0]} {pair[1]} has no row and no finding of {ctx.part}: read it or add an unread row"
            )
            problems.append(Problem("sheet_uncovered", None, None, detail))
    return problems


def _marks_on_own_sheets(ctx: PartContext) -> list[tuple[str, str, str]]:
    """(mark, file, sheet) of the plan marks and the mark-shaped schedule cells on the part's own sheets."""
    marks = ctx.marks or {}
    found = [(m["mark"], m["file"], m["sheet"]) for m in marks.get("plan_marks", [])]
    for table in marks.get("tables", []):
        for table_row in table.get("rows", []):
            found += [
                (m["text"], table["file"], table["sheet"])
                for m in table_row.get("marks", [])
                if m.get("shape") == "mark"
            ]
    return [m for m in found if (m[1], m[2]) in ctx.own.sheets]


def _mark_problems(ctx: PartContext) -> list[Problem]:
    pattern = ctx.part_row.get("marks_regex")
    if pattern is None:
        return []
    try:
        regex = re.compile(pattern, re.IGNORECASE)  # a legacy-font text decodes in an uncertain case
    except (re.error, OverflowError, RecursionError) as exc:
        return [
            Problem("marks_regex_invalid", None, None, f"marks_regex '{pattern}' does not compile: {exc}")
        ]
    have = {_fold(r["mark"]) for r in ctx.rows if "mark" in r}
    missing: dict[str, tuple[str, set[str]]] = {}
    for mark, file, sheet in _marks_on_own_sheets(ctx):
        if regex.fullmatch(mark) and _fold(mark) not in have:
            missing.setdefault(_fold(mark), (mark, set()))[1].add(f"{file} {sheet}")
    return [
        Problem(
            "mark_missing",
            None,
            None,
            f"'{mark}' ({', '.join(sorted(places))}) fits marks_regex and has no row",
        )
        for mark, places in missing.values()
    ]


# --- source keys and blocking questions ---------------------------------------------------------------------


def _entry_place(ctx: PartContext, file: str, tid: str) -> str:
    sheet = ctx.entries[(file, tid)][3]
    if sheet is not None:
        return sheet
    for (f, s, side), ids in sorted(ctx.cluster_entries.items(), key=str):
        if f == file and tid in ids:
            return f"cluster {s or '-'} {side}"
    return "-"


def _linework(ctx: PartContext, row: dict[str, Any]) -> bool:
    cites = row.get("cites", {})
    return "geometry" in cites or any(
        "evidence" in ctx.findings.get(f, {}) for f in cites.get("findings", [])
    )


def _row_keys(ctx: PartContext, row: dict[str, Any]) -> set[Key]:
    """The source keys of one row whose source backs every number of its value."""
    cites = row.get("cites", {})
    value = row.get("value")
    numbers = list(dict.fromkeys(_numbers(value))) if isinstance(value, str) else []
    by_label = {s.label: s for s in sources(ctx, row)}

    def counts(label: str) -> bool:
        source = by_label.get(label)
        return source is not None and all(backs(source, n) for n in numbers)

    file, sheet = row.get("file") or "-", row.get("sheet") or "-"
    keys: set[Key] = set()
    for tid in cites.get("entries", []) if row.get("file") is not None else []:
        if (row["file"], tid) in ctx.entries and counts(tid):
            keys.add(("text", row["file"], _entry_place(ctx, row["file"], tid)))
    for fid in cites.get("findings", []):
        finding = ctx.findings.get(fid)
        if finding is None or not counts(fid):
            continue
        where = (finding["file"], finding.get("sheet") or "-")
        keys.add(("linework" if "evidence" in finding else "text", *where))
        if finding["confidence"] == "high":
            keys.add(("high", *where))
    geometry = cites.get("geometry")
    if geometry is not None and counts(geometry["source"]):
        keys.add(("linework", file, sheet))
    if row.get("hand_sum"):
        keys.add(("sum", file, sheet))
    return keys


def _single_number(row: dict[str, Any]) -> float | None:
    value = row.get("value")
    found = _numbers(value) if isinstance(value, str) else []
    return found[0] if len(found) == 1 else None


def _pair_keys(rows: list[dict[str, Any]]) -> list[set[Key]]:
    """Per row, the extra key an agreeing count_plan / count_schedule pair of one mark gives it."""
    singles: dict[tuple[str, float], set[str]] = {}
    for r in rows:
        number = _single_number(r)
        if r.get("field") in COUNT_FIELDS and r["state"] == "seen" and "mark" in r and number is not None:
            singles.setdefault((_fold(r["mark"]), number), set()).add(r["field"])
    extra: list[set[Key]] = []
    for r in rows:
        number = _single_number(r)
        agrees = (
            r.get("field") in COUNT_FIELDS
            and r["state"] == "seen"
            and "mark" in r
            and number is not None
            and len(singles.get((_fold(r["mark"]), number), ())) == len(COUNT_FIELDS)
        )
        extra.append({("pair", _fold(r["mark"]), "-")} if agrees else set())
    return extra


def _keys_per_row(ctx: PartContext) -> list[set[Key]]:
    return [_row_keys(ctx, r) | p for r, p in zip(ctx.rows, _pair_keys(ctx.rows), strict=True)]


def _blocking_problems(ctx: PartContext, keys: list[set[Key]]) -> list[Problem]:
    problems: list[Problem] = []
    for r, held in zip(ctx.rows, keys, strict=True):
        if r["field"] not in LISTED:
            continue
        cited = _cited_questions(ctx, r)
        if r["state"] in UNSETTLED:
            why = f"a '{r['state']}' row"
        elif r["state"] == "seen" and len(held) < 2:
            why = f"a 'seen' row on {len(held)} source key(s), not two"
        else:
            why = ""
        if why and not any(_blocks(ctx, q) for q, _ in cited):
            problems.append(
                Problem("listed_needs_blocking", r["row"], None, f"{why} cites no blocking question")
            )
        for qid in dict.fromkeys(q for q, _ in cited):
            if _blocks(ctx, qid) is False:
                via = next(route for q, route in cited if q == qid)
                detail = f"{qid} (cited by {via}) is not blocking: a listed value needs a blocking question"
                problems.append(Problem("listed_question_not_blocking", r["row"], qid, detail))
    return problems


# --- findings and questions -------------------------------------------------------------------------------


def _finding_problems(ctx: PartContext) -> list[Problem]:
    problems: list[Problem] = []
    for f in _own_findings(ctx):
        if f["confidence"] == "low":
            live = [ctx.registry.get(q, {}) for q in f.get("questions", [])]
            codes = [e.get("code") for e in live if e.get("status") != "obsolete"]
            if not any(c is not None and c not in FONT_QUESTION_CODES for c in codes):
                detail = f"{f['id']} is low and cites no question outside the font questions"
                problems.append(Problem("low_without_question", None, f["id"], detail))
        note = f.get("note") or ""
        if f["kind"] != "note_item":
            missing = [name for name, regex in _CLAIM_PARTS if not regex.search(note)]
            if missing:
                detail = f"{f['id']}: the note lacks {', '.join(f'`{m}:`' for m in missing)}"
                problems.append(Problem("claim_form", None, f["id"], detail))
        elif not note.startswith("block:"):
            problems.append(
                Problem("note_item_prefix", None, f["id"], f"{f['id']}: the note does not start 'block:'")
            )
    return problems


def _family_problems(ctx: PartContext, keys: list[set[Key]]) -> list[Problem]:
    live = [
        q["id"]
        for q in _own_questions(ctx)
        if q.get("code") == FAMILY_LINEWORK and ctx.registry.get(q["id"], {}).get("status") != "obsolete"
    ]
    problems = [
        Problem("family_linework_twice", None, qid, f"{qid} is a second live {FAMILY_LINEWORK} question")
        for qid in live[1:]
    ]
    linework = [k for r, k in zip(ctx.rows, keys, strict=True) if _linework(ctx, r)]
    if len(live) == 1 and linework and all(len(k) >= 2 for k in linework):
        detail = f"{live[0]} is needless: every linework row already has two source keys"
        problems.append(Problem("family_linework_needless", None, live[0], detail))
    return problems


# --- search records -----------------------------------------------------------------------------------------


def unaccented(text: str) -> str:
    """NFD, combining marks dropped, `đ` -> `d`, `Đ` -> `D`."""
    plain = unicodedata.normalize("NFD", text).replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in plain if not unicodedata.combining(c))


def _search_records(text: str) -> list[list[str]]:
    """The quoted terms of every `searched` record of a text: the word, an optional ':' or '(...)', then
    a run of quoted terms. A `searched` with no quoted term is no record."""
    records: list[list[str]] = []
    for m in _SEARCH_WORD.finditer(text):
        rest = text[m.end() :].lstrip()
        candidates = [rest[1:].lstrip() if rest.startswith(":") else rest]
        if rest.startswith("(") and (close := rest.find(")")) != -1:
            candidates += [rest[close + 1 :].lstrip(": \t"), rest[1:close]]
        for candidate in candidates:
            run = _TERM_RUN.match(candidate)
            if run:
                records.append(_TERM.findall(run.group(0)))
                break
    return records


def _search_problems(ctx: PartContext) -> list[Problem]:
    scanned: list[tuple[str | None, str | None, str]] = []  # (row, id, text)
    for q in _own_questions(ctx):
        scanned += [(None, q["id"], q.get("message", ""))]
        scanned += [(None, q["id"], ref.get("found", "")) for ref in q.get("refs", [])]
    scanned += [(None, f["id"], f.get("note") or "") for f in _own_findings(ctx)]
    scanned += [(r["row"], None, r.get("note") or "") for r in ctx.rows]
    problems: dict[Problem, None] = {}
    for row, rid, text in scanned:
        for terms in _search_records(text):
            have = {_fold(t) for t in terms}
            twins = [unaccented(t) for t in terms if unaccented(t) != t and _fold(unaccented(t)) not in have]
            if twins:
                names = ", ".join(f"'{t}'" for t in dict.fromkeys(twins))
                detail = f"a search record lacks the unaccented term(s) {names}"
                problems[Problem("search_unaccented", row, rid, detail)] = None
    return list(problems)


# --- verbatim values ----------------------------------------------------------------------------------------


def _verbatim_problems(ctx: PartContext) -> list[Problem]:
    problems: list[Problem] = []
    for r in ctx.rows:
        found = sources(ctx, r)
        value, file = r.get("value"), r.get("file")
        if (
            r["state"] == "seen"
            and isinstance(value, str)
            and not r.get("hand_sum")
            and not _linework(ctx, r)
        ):
            held = [(file or "", t) for t in r.get("cites", {}).get("entries", []) if file is not None]
            texts = [ctx.entries[k][0] for k in held if k in ctx.entries]
            joined = " ".join(texts)
            if not any(backs(s, value) for s in found) and not (
                joined and is_quote(value.casefold(), joined.casefold())
            ):
                problems.append(
                    Problem("value_not_verbatim", r["row"], None, f"'{value}' quotes no cited source text")
                )
        spans = [next(g for g in m.groups() if g is not None) for m in _SPAN.finditer(r.get("note") or "")]
        for span in dict.fromkeys(spans):
            if not any(backs(s, span) for s in found):
                problems.append(
                    Problem(
                        "note_quote_unmatched",
                        r["row"],
                        None,
                        f"'{span}' in the note quotes no cited source text",
                    )
                )
    return problems


def text_problems(ctx: PartContext) -> list[Problem]:
    keys = _keys_per_row(ctx)
    return [
        *_sheet_uncovered(ctx),
        *_mark_problems(ctx),
        *_blocking_problems(ctx, keys),
        *_finding_problems(ctx),
        *_family_problems(ctx, keys),
        *_search_problems(ctx),
        *_verbatim_problems(ctx),
    ]
