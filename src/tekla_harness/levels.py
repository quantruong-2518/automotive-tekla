"""levels: level candidates (elevations written in metres) and storey heights, from one DXF.

`extract_levels(dxf_path, text_index, sheets_result)` returns a dict that validates against
`schemas/levels.schema.json`. Gate 1 needs the engineer to confirm levels (RTI-0003).

What is verified (docs/research/vn-structural-drawing-conventions.md, TCVN 5671:2012 for architectural
sets, structural sets by analogy): levels are written in metres and '±0.000' is the project datum.
NOT verified: the three-decimal convention, the words EL / CỐT / COTE / CAO ĐỘ, and whether a floor level
on a structural sheet is finished or structural. So:

1. Every line of every indexed text is scanned (display_text: '%%p' is already '±') for a signed decimal
   (`_VALUE_RE`): '±' (also written '+-' or '+/-'), '+', '-' or U+2212, 1-3 digits, '.' or ','
   (flagged), 1-3 decimals, optional 'm'. A sign separated from the digits by a space counts only at the
   start of the line, after a level word, or right after '(' ('(+ 6.00M LEVEL)'); 'TẦNG 2 - 3.600' is a
   name, a dash and an unsigned number: no level. Unsigned numbers, values followed by 'mm' or '%' are
   not levels.
2. The line around the value gives the form: bare (nothing else), prefixed (a level word only),
   labelled (a storey name, optionally a level word, then the value), embedded (anything else). Storey
   words are matched WITH their diacritics (tầng, sàn, mái, tum, hầm, lầu; English floor, roof, ...):
   'TĂNG CƯỜNG' (strengthening) and 'SÂN' (yard) are not storeys. A storey word is a storey NAME
   (`_names_storey`) except in the non-names seen on the corpus: a slab-plan title whose only storey word
   is 'sàn' (slab), a quantity or schedule heading, and a storey word with nothing else ('tầng', 'floor
   slab'). A sure name ('tầng 3', 'first floor', 'tầng thượng', 'mái', `_NAMED_STOREY_RE`) wins over them.
3. A level symbol is an INSERT (anywhere, also nested) of a block that looks like a level marker: it
   holds an isosceles triangle (SOLID/TRACE, closed 3-vertex polyline, or a 3-vertex HATCH boundary)
   with a horizontal base, its apex over the base midpoint (within 5 % of the base width) and a height of
   0.3 to 1.0 base widths, and the block holds no CIRCLE, ARC or ELLIPSE (a north arrow is a tall
   triangle in a circle). A candidate is next to it when the insertion point lies within
   SYMBOL_DISTANCE text heights of the text extents.
4. Confidence: medium only for a bare value next to a level symbol; low otherwise (the three-decimal
   convention is NOT verified, so three decimals alone are low); never above the text entry or the file
   cap; low for text on an off/frozen layer or an invisible attribute.
5. Equal values are grouped. A group's `occurrences` counts its candidates on original sheets only (a
   sheet that is a copy, sheets.json duplicate_of, adds nothing). Storey heights are differences of
   consecutive levels whose candidates name a storey; when fewer than two levels are named, the
   differences of all non-embedded levels seen twice, at the datum, or next to a symbol are given, capped
   'low', with a blocking level_storey_selection question. Safety net: when storeys are named, an unnamed
   level that carries a storey word (on the value's line, or in a neighbour that names no storey) may be a
   storey the heights skip, between named storeys or outside them ('GROUND ±0.000' under named floors, a
   basement): the heights are capped 'low' and a blocking level_storey_selection question lists those
   levels. Values are never converted.
6. Legacy-font gate (`text_gate.meaning_block_reason`, tool wave 2 fix 1a): an entry whose meaning is blocked
   gives no candidate, level, group, storey name or question; each level-shaped match in it is listed in
   `blocked_candidates` (entry id, 0-based line, value text as stored, reason), and a 'none found' question
   says how many were held back.
Questions: none found, finished vs structural (always), same name with different values, a storey name
with a negative value, values outside LEVEL_RANGE_M (unit doubt), a level seen once, no datum, storey
selection, non-three-decimal writing. `question_counts` gives the true number per code (the list is
capped at MAX_QUESTIONS_PER_CODE).
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter, defaultdict
from decimal import Decimal
from itertools import pairwise
from pathlib import Path
from typing import Any

from ezdxf.document import Drawing

from tekla_harness.sheets import (
    SHEET_UNKNOWN,
    SheetLocator,
    Walker,
    declared_units,
    fold,
    layout_spaces,
    listed,
    max_conf,
    min_conf,
    open_checked,
    question,
    rbox,
    rnum,
    text_box,
)
from tekla_harness.text_gate import meaning_block_reason

SCHEMA_VERSION = "0.1"
_MINUS = "\u2212"  # MINUS SIGN, also accepted as a sign
LEVEL_RANGE_M = (-50.0, 300.0)
SYMBOL_DISTANCE = 6.0  # text heights
NAME_SAME_LINE = 15.0  # text heights, left or right of the value
NAME_ABOVE = 2.5  # text heights
MAX_QUESTIONS_PER_CODE = 50

_VALUE_RE = re.compile(
    r"(?<![\d,])(?<!\d\.)(?P<sign>\+/-|\+-|[±+\-\u2212])(?P<gap>\s?)(?P<int>\d{1,3})(?P<sep>[.,])"
    r"(?P<dec>\d{1,3})(?P<unit>\s?[mM](?![A-Za-z]))?(?![\d.,]|\w)"
)
_NOT_LEVEL_AFTER_RE = re.compile(r"\s?(?:mm(?![A-Za-z])|%)", re.IGNORECASE)  # '+3.600 mm', 'i=-2.5%'
_PLUS_MINUS = ("±", "+-", "+/-")
# Level words before a value (folded). None is a verified standard term: candidates only.
_PREFIXES = (
    "el",
    "el.",
    "elev",
    "elev.",
    "elevation",
    "cot",
    "cote",
    "cao do",
    "cd",
    "ffl",
    "f.f.l",
    "f.f.l.",
    "ssl",
    "s.s.l",
    "s.s.l.",
    "tos",
    "t.o.s",
    "t.o.s.",
    "toc",
    "level",
    "lvl",
)
_PREFIX_RE = re.compile(
    r"(?:^|[\s(])("
    + "|".join(re.escape(p) for p in sorted(_PREFIXES, key=len, reverse=True))
    + r")\s*[:=]?\s*$"
)
# Storey words, matched on NFC casefolded text WITH diacritics: Vietnamese tầng/sàn/mái/tum/hầm/lầu (not
# tăng 'strengthen', sân 'yard') and English equivalents.
_STOREY_RE = re.compile(
    r"\b(tầng|sàn|mái|tum|hầm|lầu|thượng|floor|roof|storey|story|level|basement|ground|terrace|mezzanine"
    r"|penthouse)\b"
)
# A storey NAME (tool wave 3, EVAL-3 a2 and its review). A storey word names a storey, except in the
# non-names seen on the corpus: a bare 'sàn' (slab) ends slab-plan titles ('mặt bằng thép sàn') and
# quantity headings ('khối lượng thép sàn'), and a storey word with nothing else ('tầng', 'floor slab')
# names nothing. A sure name (_NAMED_STOREY_RE) wins over those rejections: a storey word followed by a
# number, a number word or a qualifier ('tầng 3', 'sàn tầng 3', 'tầng hai', 'tầng trệt', 'tầng thượng',
# 'tầng kỹ thuật', 'tầng điển hình', 'level 2'), an ordinal or a qualifier before the word ('2nd floor',
# 'first floor', 'upper floor', 'ground floor'), or a word that names one storey by itself (mái, áp mái,
# tum, hầm, thượng, roof, terrace, basement, mezzanine, penthouse).
_NAMED_STOREY_RE = re.compile(
    r"\b(?:tầng|sàn|lầu|floor|storey|story|level)\s*(?:\d+|một|hai|ba|bốn|tư|năm|sáu|bảy|tám|chín|mười"
    r"|trệt|lửng|ground|thượng|kỹ thuật|điển hình)\b"
    r"|\b(?:\d+\s*(?:st|nd|rd|th)?|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth"
    r"|upper|lower|top|typical|ground|mezzanine)\s*(?:floor|storey|story|level)\b"
    r"|\b(?:áp\s*mái|mái|tum|hầm|thượng|roof|terrace|basement|mezzanine|penthouse)\b"
)
# Non-names: quantity and schedule headings, and the words that are no storey of their own.
_QUANTITY_HEADING_RE = re.compile(r"\b(?:khối lượng|thống kê|quantity|quantities|schedule)\b")
_SLAB_WORD = "sàn"
_BARE_STOREY_WORDS_RE = re.compile(r"\b(?:tầng|sàn|lầu|floor|storey|story|level|ground|slab)\b")


def _names_storey(text: str) -> bool:
    """Does this text (a candidate's label or a neighbour) name a storey? See _NAMED_STOREY_RE."""
    folded = _storey_fold(text)
    if _NAMED_STOREY_RE.search(folded):
        return True
    words = _STOREY_RE.findall(folded)
    if not words or _QUANTITY_HEADING_RE.search(folded):
        return False
    if all(w == _SLAB_WORD for w in words):
        return False  # a slab-plan title or a bare 'sàn'
    return re.search(r"\w", _BARE_STOREY_WORDS_RE.sub(" ", folded)) is not None  # 'tầng', 'floor slab': bare


LEVEL_MARK_APEX_TOL = 0.05  # apex offset from the base midpoint, in base widths
LEVEL_MARK_HEIGHT = (0.3, 1.0)  # triangle height, in base widths


def _storey_fold(text: str) -> str:
    """NFC, casefolded, spaces collapsed; diacritics kept (they tell tầng from tăng)."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text).casefold()).strip()


def _fold_keep(text: str) -> str:
    """Per-character fold (casefold, no diacritics, đ -> d) that keeps the string length."""
    out = []
    for ch in text:
        base = unicodedata.normalize("NFD", ch)[0] if ch not in "đĐðÐ" else "d"
        low = base.lower()
        out.append(low if len(low) == 1 else base)
    return "".join(out)


_Pt = tuple[float, float]


def _triangles(entity: Any) -> list[list[_Pt]]:
    """Triangles of the entity (3 vertices each): SOLID/TRACE, closed 3-vertex polyline, HATCH boundary."""
    kind = entity.dxftype()
    found: list[set[_Pt]] = []
    if kind in ("SOLID", "TRACE"):
        found.append({(round(v[0], 9), round(v[1], 9)) for v in entity.vertices()})
    elif kind == "LWPOLYLINE":
        pts = [(round(x, 9), round(y, 9)) for x, y in entity.get_points("xy")]
        if len(pts) >= 2 and pts[0] == pts[-1]:
            pts = pts[:-1]
        if (entity.closed or len(pts) == 3) and len(pts) == 3:
            found.append(set(pts))
    elif kind == "POLYLINE" and entity.is_2d_polyline:
        pts = [(round(v.x, 9), round(v.y, 9)) for v in entity.points()]
        if len(pts) >= 2 and pts[0] == pts[-1]:
            pts = pts[:-1]
        if len(pts) == 3:
            found.append(set(pts))
    elif kind == "HATCH":
        for path in entity.paths:
            vertices = getattr(path, "vertices", None)
            if vertices is not None:
                found.append({(round(v[0], 9), round(v[1], 9)) for v in vertices})
            else:
                edges = getattr(path, "edges", [])
                if edges and all(e.type.name == "LINE" for e in edges):
                    found.append({(round(e.start[0], 9), round(e.start[1], 9)) for e in edges})
    return [sorted(p) for p in found if len(p) == 3]


def _level_mark_triangle(pts: list[_Pt]) -> bool:
    """Isosceles, horizontal base, apex over the base midpoint, height 0.3..1.0 x base (module docstring)."""
    for k in range(3):
        apex = pts[k]
        a, b = (pts[i] for i in range(3) if i != k)
        width = abs(b[0] - a[0])
        if width <= 0 or abs(b[1] - a[1]) > 1e-6 * width:
            continue
        mid = (a[0] + b[0]) / 2
        height = abs(apex[1] - a[1])
        if (
            abs(apex[0] - mid) <= LEVEL_MARK_APEX_TOL * width
            and LEVEL_MARK_HEIGHT[0] * width <= height <= LEVEL_MARK_HEIGHT[1] * width
        ):
            return True
    return False


def _symbol_blocks(doc: Drawing) -> tuple[set[str], Counter[str]]:
    """(names of blocks that look like a level marker, entity read failures by type: never silent)."""
    names: set[str] = set()
    failed: Counter[str] = Counter()
    for block in doc.blocks:
        if block.block is not None and (block.block.is_xref or block.block.is_xref_overlay):
            continue
        mark = round_shape = False
        for e in block:
            try:
                if e.dxftype() in ("CIRCLE", "ARC", "ELLIPSE"):
                    round_shape = True
                elif any(_level_mark_triangle(t) for t in _triangles(e)):
                    mark = True
            except Exception as exc:
                failed[f"{e.dxftype()}:{type(exc).__name__}"] += 1
        if mark and not round_shape:
            names.add(block.name)
    return names, failed


def _box_distance(box: tuple[float, float, float, float], p: tuple[float, float]) -> float:
    dx = max(box[0] - p[0], 0.0, p[0] - box[2])
    dy = max(box[1] - p[1], 0.0, p[1] - box[3])
    return math.hypot(dx, dy)


def _value_text(value: Decimal) -> str:
    return "±0.000" if value == 0 else f"{value:+.3f}"


def _parse(line: str):
    for m in _VALUE_RE.finditer(line):
        before, after = line[: m.start()].strip(), line[m.end() :].strip()
        raw_before = line[: m.start()]
        if raw_before and raw_before[-1].isalpha() and not _PREFIX_RE.search(_fold_keep(raw_before)):
            continue  # a letter glued to the sign ('A-1.200') is not a level unless it ends a level word
        if (
            m.group("gap")
            and before
            and not _PREFIX_RE.search(_fold_keep(raw_before))
            and not raw_before.rstrip().endswith("(")
        ):
            continue  # 'TẦNG 2 - 3.600': a dash between a name and a number, not a sign; '(+ 6.00M' is one
        if _NOT_LEVEL_AFTER_RE.match(line, m.end()):
            continue  # '+3.600 mm' (millimetres), 'i=-2.5%' (a slope)
        sign = m.group("sign")
        number = Decimal(f"{m.group('int')}.{m.group('dec')}")
        value = -number if sign in ("-", _MINUS) else number
        flags = []
        if m.group("sep") == ",":
            flags.append("comma_decimal")
        if sign in _PLUS_MINUS and number != 0:
            flags.append("pm_nonzero")
        if sign == _MINUS:
            flags.append("minus_sign_u2212")
        form, prefix, name = "embedded", None, None
        if not before and not after:
            form = "bare"
        elif not after:
            keep = _fold_keep(before)  # same length as `before`, so positions map back
            pm = _PREFIX_RE.search(keep)
            rest = before
            if pm:
                rest, prefix = before[: pm.start(1)], before[pm.start(1) :].strip(" :=")
            rest = rest.strip(" :=-(")
            if pm and not rest:
                form = "prefixed"
            elif rest and _names_storey(rest):
                form, name = "labelled", rest
            else:
                prefix = None
        yield m, value, flags, form, prefix, name


def extract_levels(
    dxf_path: str | Path,
    text_index: dict[str, Any],
    sheets_result: dict[str, Any],
    *,
    doc: Drawing | None = None,
) -> dict[str, Any]:
    """Level candidates of one DXF. See the module docstring for the rules."""
    doc = open_checked(dxf_path, text_index, doc)
    if sheets_result["file"]["sha256"] != text_index["file"]["sha256"]:
        raise ValueError("sheets result was built from another file")
    file_path = text_index["file"]["path"]
    cap = text_index["file"]["confidence_cap"]
    handles_ok = bool(text_index["file"]["handles_reliable"])
    locator = SheetLocator(sheets_result)
    warnings: list[str] = []
    questions: list[dict[str, Any]] = []
    q_counts: Counter[str] = Counter()

    def ask(
        code: str, blocking: bool, message: str, where: str, found: str, sheet: str | None = None
    ) -> None:
        q_counts[code] += 1
        if q_counts[code] <= MAX_QUESTIONS_PER_CODE:
            questions.append(question(code, blocking, message, where, found, sheet))

    # level symbols
    symbol_names, failed = _symbol_blocks(doc)
    for reason, n in sorted(failed.items()):
        warnings.append(f"{n} block entit(ies) could not be checked for a level-symbol triangle: {reason}.")
    walker = Walker(doc, handles_ok)
    symbols: dict[str, list[tuple[tuple[float, float], str, str | None]]] = defaultdict(list)
    for space, layout, _ in layout_spaces(doc):
        for p in walker.walk(layout, space, frozenset({"INSERT"})):
            name = str(p.entity.dxf.get("name", ""))
            if name in symbol_names:
                ins = p.entity.dxf.insert
                handle = walker.handle(p.entity) if not p.block_path else p.top_handle
                symbols[space].append(((ins.x, ins.y), name, handle))
    for reason, n in sorted(walker.skipped.items()):
        warnings.append(f"{n} insert(s) not expanded while looking for level symbols: {reason}.")

    entries = text_index["entries"]
    by_sheet_space: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for e in entries:
        by_sheet_space[(locator.text_sheet(e["id"]), e["space"])].append(e)

    candidates: list[dict[str, Any]] = []
    storey_worded: set[str] = set()  # candidate ids: a storey word on the value's line or next to it
    blocked: list[dict[str, Any]] = []
    for e in entries:
        lines = e["display_text"].split("\n")
        reason = meaning_block_reason(e)
        if reason is not None:  # legacy-font gate: listed, never a candidate
            blocked.extend(
                {"entry_id": e["id"], "line": i, "value_text": m.group(0).strip(), "reason": reason}
                for i, line in enumerate(lines)
                for m, *_ in _parse(line)
            )
            continue
        for line in lines:
            for m, value, flags, form, prefix, name in _parse(line):
                if len(lines) > 1:
                    flags = [*flags, "multiline_text"]
                if e["entity_type"] == "DIMENSION":
                    flags = [*flags, "from_dimension_text"]
                sheet = locator.text_sheet(e["id"])
                box = text_box(e)
                if box is None:
                    continue
                h = e.get("height") or (box[3] - box[1]) or 0.0
                symbol = None
                if h > 0:
                    near = [
                        (_box_distance(box, pt), bname, handle)
                        for pt, bname, handle in symbols.get(e["space"], ())
                        if _box_distance(box, pt) <= SYMBOL_DISTANCE * h
                    ]
                    if near:
                        dist, bname, handle = min(near, key=lambda t: (t[0], t[1], t[2] or ""))
                        symbol = {"block_name": bname, "handle": handle, "distance": rnum(dist)}
                decimals = len(m.group("dec"))
                # the three-decimal convention is not verified: only a level symbol makes a bare value medium
                conf = "medium" if form == "bare" and symbol is not None else "low"
                if flags and set(flags) & {"comma_decimal", "pm_nonzero"}:
                    conf = "low"
                if set(e["flags"]) & {"layer_off", "layer_frozen", "attribute_invisible"}:
                    conf = "low"
                conf = min_conf(conf, e["confidence"], cap)
                prov = {
                    "file": file_path,
                    "sheet": sheet,
                    "method": "dxf_entity",
                    "region": {"bbox": rbox(box)},
                }
                name_obj = None
                storey_word = _STOREY_RE.search(_storey_fold(line)) is not None
                if name is not None:
                    name_obj = {"value": name, "provenance": prov, "confidence": "low"}
                elif form in ("bare", "prefixed") and h > 0:
                    name_obj, near_word = _adjacent_name(
                        e, box, h, by_sheet_space[(sheet, e["space"])], file_path, sheet
                    )
                    storey_word = storey_word or near_word
                if storey_word:
                    storey_worded.add(f"L{len(candidates) + 1:04d}")
                candidates.append(
                    {
                        "candidate_id": f"L{len(candidates) + 1:04d}",
                        "text_id": e["id"],
                        "sheet": sheet,
                        "value": {"value": float(value), "provenance": prov, "confidence": conf},
                        "value_text": m.group(0).strip(),
                        "form": form,
                        "prefix": prefix,
                        "decimals": decimals,
                        "unit_suffix": m.group("unit").strip() if m.group("unit") else None,
                        "name": name_obj,
                        "symbol": symbol,
                        "flags": flags,
                    }
                )

    copies = {s["sheet_id"] for s in sheets_result["sheets"] if s.get("duplicate_of")}
    groups: dict[Decimal, list[dict[str, Any]]] = defaultdict(list)
    for c in candidates:
        groups[Decimal(str(c["value"]["value"]))].append(c)
    levels = []
    fallback: list[bool] = []  # per level: usable for heights when too few levels name a storey
    for value in sorted(groups):
        members = groups[value]
        solid = [c for c in members if c["form"] != "embedded"]
        conf = max_conf(*[c["value"]["confidence"] for c in solid]) if solid else "low"
        names = sorted({c["name"]["value"] for c in members if c["name"]})
        # a candidate on a copied sheet (sheets.json duplicate_of) is not a second occurrence
        occurrences = sum(1 for c in members if c["sheet"] not in copies)
        fallback.append(
            bool(solid) and (value == 0 or occurrences >= 2 or any(c["name"] or c["symbol"] for c in solid))
        )
        levels.append(
            {
                "value": float(value),
                "value_text": _value_text(value),
                "candidate_ids": [c["candidate_id"] for c in members],
                "occurrences": occurrences,
                "sheets": sorted({c["sheet"] for c in members}),
                "names": names,
                "confidence": conf,
                "used_for_heights": False,
            }
        )
    # storey heights: between levels whose candidates name a storey; with fewer than two named, the old
    # rule (datum, seen twice, next to a symbol) gives the differences, capped low and asked
    named = [bool(lv["names"]) for lv in levels]
    storeys_named = sum(named) >= 2
    for lv, n, fb in zip(levels, named, fallback, strict=True):
        lv["used_for_heights"] = n if storeys_named else fb
    # safety net (review of a2): an unnamed level that carries a storey word may be a storey the named
    # heights skip (between named storeys, or a basement / top storey outside them), so those heights are
    # low and asked
    skipped: list[dict[str, Any]] = []
    if storeys_named:
        skipped = [
            lv
            for lv in levels
            if not lv["names"] and any(cid in storey_worded for cid in lv["candidate_ids"])
        ]
    heights_asked = not storeys_named or bool(skipped)

    heights = []
    used = [lv for lv in levels if lv["used_for_heights"]]
    for lo, hi in pairwise(used):
        a = next(c for c in candidates if c["candidate_id"] == lo["candidate_ids"][0])
        b = next(c for c in candidates if c["candidate_id"] == hi["candidate_ids"][0])
        sheet = a["sheet"] if a["sheet"] == b["sheet"] else SHEET_UNKNOWN
        diff = Decimal(str(hi["value"])) - Decimal(str(lo["value"]))
        heights.append(
            {
                "from_value": lo["value"],
                "to_value": hi["value"],
                "height": {
                    "value": float(diff),
                    "provenance": {
                        "file": file_path,
                        "sheet": sheet,
                        "method": "derived",
                        "derived_from": [a["value"]["provenance"], b["value"]["provenance"]],
                    },
                    "confidence": min_conf(
                        lo["confidence"], hi["confidence"], "low" if heights_asked else None
                    ),
                },
            }
        )
    if skipped:
        ask(
            "level_storey_selection",
            True,
            "These levels carry a storey word but no storey name, so the storey heights given (between "
            "named storeys only, low) skip them. Is each of them a floor?",
            listed(lv["value_text"] for lv in skipped),
            f"{len(skipped)} unnamed level(s) with a storey word; heights use the {len(used)} named level(s)",
        )
    if heights and not storeys_named:
        ask(
            "level_storey_selection",
            True,
            "Fewer than two levels are tied to a storey name, so it is not known which levels are storeys "
            "(a sill, a pit or a step level is also a level). Which of these levels are floors?",
            listed(lv["value_text"] for lv in used),
            f"{len(used)} level(s) used for the storey heights given (low)",
        )

    # questions
    if not candidates:
        held = (
            f" {len(blocked)} level-shaped text(s) are blocked by the legacy-font gate (unknown or suspect "
            "font encoding, see blocked_candidates): no value is taken from them."
            if blocked
            else ""
        )
        ask(
            "level_none_found",
            True,
            "No level text (signed value in metres such as '+3.600') was found."
            + held
            + " Where are the levels given?",
            str(file_path),
            f"{len(entries)} texts scanned",
        )
    else:
        ask(
            "level_finished_vs_structural",
            True,
            "Are these levels finished floor levels or structural (top of slab / beam) levels? "
            "The convention is "
            "not verified and the two differ by the screed thickness.",
            listed(lv["value_text"] for lv in used) or "embedded values only",
            f"{len(levels)} distinct value(s) on {len({c['sheet'] for c in candidates})} sheet(s)",
        )
    by_name: dict[str, set[str]] = defaultdict(set)
    shown_name: dict[str, str] = {}
    for c in candidates:
        if c["name"]:
            key = re.sub(r"\s+", " ", fold(c["name"]["value"]))
            by_name[key].add(_value_text(Decimal(str(c["value"]["value"]))))
            shown_name.setdefault(key, c["name"]["value"])
    for key in sorted(by_name):
        if len(by_name[key]) > 1:
            ask(
                "level_name_conflict",
                True,
                "The same storey name is given with different levels. Which level is right (or are they "
                "different datums, e.g. architectural vs structural)?",
                shown_name[key],
                " / ".join(sorted(by_name[key])),
            )
    for lv in levels:
        if not (LEVEL_RANGE_M[0] <= lv["value"] <= LEVEL_RANGE_M[1]):
            ask(
                "level_value_out_of_range",
                True,
                "A level value is outside -50 m .. +300 m: is it in another unit (mm?) or not a level?",
                listed(lv["candidate_ids"]),
                lv["value_text"],
            )
    for c in candidates:
        if c["name"] and c["value"]["value"] < 0:
            ask(
                "level_negative_storey",
                True,
                "A storey name is written with a negative level: a basement, or a dash used as a separator "
                "('TẦNG 2 -3.600' for +3.600)? Which is it?",
                c["candidate_id"],
                f"{c['name']['value']} {c['value_text']}",
                c["sheet"],
            )
    non_embedded = {c["candidate_id"] for c in candidates if c["form"] != "embedded"}
    for lv in levels:
        if lv["occurrences"] <= 1 and any(cid in non_embedded for cid in lv["candidate_ids"]):
            ask(
                "level_single_occurrence",
                False,
                "This level appears only once in the file (a copied sheet does not count); it is not "
                "cross-checked by another view.",
                lv["candidate_ids"][0],
                lv["value_text"],
                lv["sheets"][0],
            )
    if used and not any(lv["value"] == 0 and lv["candidate_ids"][0] in non_embedded for lv in levels):
        ask(
            "level_datum_not_found",
            False,
            "No ±0.000 datum was found among the levels. What is the project datum?",
            str(file_path),
            listed(lv["value_text"] for lv in used),
        )
    loose = sorted({c["value_text"] for c in candidates if c["decimals"] < 3 and c["form"] != "embedded"})
    if loose:
        ask(
            "level_decimals_nonstandard",
            False,
            "Some levels are written with fewer than three decimals; confirm they are metres.",
            str(file_path),
            listed(loose, 20),
        )
    for code, n in sorted(q_counts.items()):
        if n > MAX_QUESTIONS_PER_CODE:
            warnings.append(f"{n} '{code}' questions; only the first {MAX_QUESTIONS_PER_CODE} are listed.")

    return {
        "schema_version": SCHEMA_VERSION,
        "file": {
            "path": file_path,
            "sha256": text_index["file"]["sha256"],
            "confidence_cap": cap,
            "declared_units": declared_units(doc),
        },
        "candidates": candidates,
        "levels": levels,
        "storey_heights": heights,
        "blocked_candidates": blocked,
        "summary": {
            "texts_scanned": len(entries),
            "candidates": len(candidates),
            "by_form": dict(sorted(Counter(c["form"] for c in candidates).items())),
            "levels": len(levels),
            "level_symbol_inserts": sum(len(v) for v in symbols.values()),
            "blocked_candidates": len(blocked),
        },
        "questions": questions,
        "question_counts": dict(sorted(q_counts.items())),
        "warnings": warnings,
    }


def _adjacent_name(
    entry: dict[str, Any],
    box: tuple[float, float, float, float],
    h: float,
    neighbours: list[dict[str, Any]],
    file_path: str,
    sheet: str,
) -> tuple[dict[str, Any] | None, bool]:
    """(nearest storey-name text on the same line (within NAME_SAME_LINE heights) or just above it, whether
    such a neighbour carries a storey word but names no storey: 'FLOOR SLAB' above a bare value)."""
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    best: tuple[float, str, dict[str, Any], tuple[float, float, float, float]] | None = None
    storey_word = False
    for other in neighbours:
        if other["id"] == entry["id"] or meaning_block_reason(other) is not None:
            continue  # a blocked text never names a storey (legacy-font gate)
        text = other["display_text"].strip()
        if not text or len(text) > 40 or "\n" in text or _VALUE_RE.search(text):
            continue
        start = _storey_fold(text).lstrip("(-: ")
        if not _STOREY_RE.search(start):
            continue
        name = (_STOREY_RE.match(start) or _NAMED_STOREY_RE.match(start)) and _names_storey(text)
        obox = text_box(other)
        if obox is None:
            continue
        ox, oy = (obox[0] + obox[2]) / 2, (obox[1] + obox[3]) / 2
        same_line = (
            abs(oy - cy) <= 0.75 * h
            and min(abs(obox[2] - box[0]), abs(obox[0] - box[2])) <= NAME_SAME_LINE * h
        )
        above = (
            obox[1] >= box[3] - 0.25 * h
            and obox[1] - box[3] <= NAME_ABOVE * h
            and obox[0] < box[2]
            and obox[2] > box[0]
        )
        if not (same_line or above):
            continue
        if not name:
            storey_word = True
            continue
        dist = math.hypot(ox - cx, oy - cy)
        if best is None or (dist, other["id"]) < (best[0], best[1]):
            best = (dist, other["id"], other, obox)
    if best is None:
        return None, storey_word
    prov = {"file": file_path, "sheet": sheet, "method": "dxf_entity", "region": {"bbox": rbox(best[3])}}
    return {"value": best[2]["display_text"].strip(), "provenance": prov, "confidence": "low"}, storey_word
