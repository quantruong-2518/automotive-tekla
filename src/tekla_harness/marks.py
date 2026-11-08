"""marks: `harness marks`, member marks and schedule tables, plan-to-schedule matching.

`run_marks(work_dir)` reads, for every DXF/DWG of `inventory.json`, its text index, its sheets document and
(for line grids) the DXF itself, and writes `marks.json` and `marks-questions.json`. Nothing is computed
from a mark beyond comparing text: no quantity, length, weight or unit conversion.

Split with `callouts.py`. callouts lists a text whose WHOLE line is a bare mark (`C1`, `GM2`, `DC-3a`,
upper-case prefix) as a `member_mark` candidate. Since tool wave 2 (fix 1b) this module owns the
`member_mark_prefix_meaning` question: one blocking question per file, one subject per prefix of its plan
marks (upper-cased), whatever grammar found them; it never gives a prefix a meaning itself. An answer given
to the question callouts raised before goes stale once (its key is no longer raised) and is asked again
here. It extends the mark grammar (`in_callouts` says when callouts also lists the text):

  * sub-numbered marks `D1.1`, `D1-1` (numbers kept as written), letter suffixes in either case
    (`D1a`, `D1.9A`), lower-case prefixes (`gm1`; a lone lower-case `a` or `s` is the spacing letter of a
    bar callout, never a mark), and a section in brackets `D1.1(220X350)`, `C1 (220x220)`: `b` and `h`
    are the two numbers as written, in drawing units, never converted (separator x, X or U+00D7);
  * a member-type word in front of the mark, as in a detail title (`DẦM D1.1`, `CỘT C1`, `ĐÀI CỌC DC1`,
    `GIẰNG MÓNG GM1`, `BEAM B1`, `COLUMN C1`): recorded as `title_member_word` evidence (confidence at
    most medium). It is NOT a prefix meaning: prefix meanings come only from `member_mark_prefix_meaning`
    answers;
  * schedule tables and the matching of schedule rows to plan marks (below).

A mark is never taken from a line that a callouts pattern claims (`I300`, `M20`, `BM12`...), from a
sheet code (`KC-01`), from texts the title block, grid or level extractors claimed, from a dimension, or
from a sheet that duplicates an earlier one.

Legacy-font gate (`text_gate.meaning_block_reason`). Only an entry whose meaning is allowed can be a plan
mark, a header keyword or a matchable schedule mark. The gate works per column (tool wave 2, fix 8): only
the mark column's header can block a table. A table whose mark column is not named by an allowed keyword
and whose mark-column header cell holds blocked text is reported with `header_blocked: true`; every cell
of it carries `meaning: blocked`, and its mark-shaped cells are listed in `blocked_marks` (verbatim, with
the entry id and the reason), never matched and never part of a notation variant. Any other blocked
header cell is listed in the table's `blocked_columns`: its column gets no role, the rest of the table is
read (cells keep their own meaning). A blocked cell in the mark column of an allowed table is listed in
`blocked_marks` the same way. No question paraphrases blocked text.

Schedule tables, per sheet and per space of the texts (a paper sheet shows model-space texts through its
viewports: the table is in the texts' own coordinates, `space` says which):

  * header keywords, matched on the WHOLE cell after NFC + casefold, collapsed whitespace and a stripped
    trailing ':' or '(mm)': KÝ HIỆU, KÝ HIỆU CẤU KIỆN, TÊN CẤU KIỆN, TÊN, MARK, MEMBER MARK, MEMBER, NAME.
    With several in one header the mark column is the first of: ký hiệu / mark, tên cấu kiện / member,
    tên / name.
  * line grid first. LINE, LWPOLYLINE and 2D POLYLINE edges (also inside INSERTs, via sheets.Walker) that
    are axis-aligned are merged when collinear (tolerance `LINE_TOL` x the median text height of the
    space). The cell around the keyword (or around a mark, see below) is bounded by the nearest lines
    crossing it (at most `MAX_CELL_H` x h above/below, `MAX_CELL_W` x h left/right, h the text height).
    Rows are the bands between horizontal lines that span the mark column, walked up and down while both
    vertical lines of the column cover the band (a merged mark cell is one band, as drawn); the table's
    x-range is the overlap of its top and bottom lines; columns are the vertical lines crossing the
    first data band. A text belongs to the band and column holding its box centre (sheets.text_box).
  * text alignment when no grid surrounds the keyword: the header row is the chain of texts whose boxes
    overlap the keyword's box vertically by at least half the smaller height, each at most `COL_GAP` x h
    from the previous one; column boundaries are the midpoints between header centres (outer edges one h
    beyond the header boxes); data rows are texts below the header inside those edges, grouped when
    their centres differ by at most `ROW_TOL` x h; a row needs a cell in the mark column and (with two
    header columns or more) a second cell, and lies at most `ROW_PITCH` x h below the previous row.
    Rotated texts and dimensions are never cells in this mode.
  * headers without an allowed keyword are found from the line grid only: a mark-shaped text (the seed)
    in a grid cell whose topmost band spans at least two columns, holds blocked text, no allowed keyword
    and no mark-shaped text, with at least two data bands holding a mark-shaped cell in the seed's
    column. The seed's column is the mark column. When its header cell holds blocked text the table is
    header-blocked; otherwise the table is read on that column, with confidence low (no keyword names
    it). Without a grid such a table is not detected (a known miss). A grid of mark-shaped cells whose
    header has neither a keyword nor blocked text is not reported either: on a plan it is as likely the
    space between drawn lines.
  * a keyword whose table has fewer than two data rows with a mark cell is listed in `unparsed_tables`
    and asked as a non-blocking `schedule_table_unparsed` question; texts inside the part of it that was
    found (line grid) are not plan marks.

Matching, per file, only between allowed plan marks and allowed mark-column cells of tables whose header
is not blocked. Keys: NFC + casefold + all whitespace removed. Equal keys match; nothing else ever does.
Two keys with the same structure (prefix, the numbers as integers, suffix, compared case-insensitively)
but different keys, e.g. `D1.1` / `D1-1` or `C-01` / `C1`, are a `notation_variant`: never merged, asked
once per file as `mark_notation_equivalence` (blocking for lot specs). A matched plan mark with a section
`(b x h)` and a schedule row whose size columns (b / h, or a combined `b x h` column) hold numbers is
compared; a difference is a blocking `mark_size_conflict` quoting both entry ids. Every matched key says
`size_compared` (true when at least one plan mark and row pair had both sizes) and otherwise
`size_not_compared_reason`: the plan marks have no size, or per row the table has no size column, the
header cells that could name one are blocked, the size cells are blocked, or they are not numbers
(`summary.size_comparisons` counts both). `plan_only` is listed only for a file with at least one
matchable schedule. `summary.by_sheet` counts plan marks, tables, rows, unparsed tables and blocked marks
per detector sheet (sheet null: on no sheet).

Confidence is never high: plan marks, titles and tables are at most medium (callouts' rule: min(cap,
entry confidence), low for case-uncertain text, unmapped characters or unknown-encoding flags); a
header-blocked table, and a table whose mark column no keyword names, is low.

Exit codes as `harness callouts`: 0 ok, 1 inconsistent work folder or invalid output, 2 usage, 3 cannot
write. A DXF that cannot be opened for its lines (native DXF without `--input-dir`, read error) is not an
error: that file falls back to text alignment and the reason is in `files[].line_grid` and `warnings`.
"""

from __future__ import annotations

import argparse
import bisect
import itertools
import json
import math
import re
import statistics
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ezdxf.lldxf.const import DXFError

from tekla_harness.callouts import (
    _SHEET_CODE,
    _check_input_dir,
    _claimed_text_ids,
    _confidence,
    _num,
    _provenance,
    member_mark,
    scan_line,
)
from tekla_harness.questions import (
    QuestionsError,
    dump_json,
    load_ledger,
    question_group,
    questions_document,
    write_text_atomic,
)
from tekla_harness.schemas import validate
from tekla_harness.sheet_text import (
    EXIT_INVALID,
    SCHEMA_VERSION,
    LoadedFile,
    ReaderError,
    _details,
    _inside,
    load_file,
    load_inventory,
    normalize,
    printed_number,
    sheet_label,
    stale_warning,
)
from tekla_harness.sheets import Walker, layout_spaces, open_checked, text_box
from tekla_harness.text_gate import meaning_block_reason

COMMAND = "marks"
HELP = "member marks and schedule tables, plan-to-schedule matching: marks.json, marks-questions.json"

# tolerances, all x the relevant text height h
LINE_TOL = 0.1  # collinear line merge and line-to-line snapping (x median text height of the space)
MAX_CELL_H = 60.0  # a grid cell around a text: nearest line above / below at most this far
MAX_CELL_W = 100.0  # ... left / right
MAX_BAND = 60.0  # one table band at most this tall (a merged mark cell spans many bar rows)
ROW_TOL = 0.6  # text alignment: same row when centres differ by at most this (as sheet_text)
COL_GAP = 6.0  # text alignment: neighbouring header cells at most this far apart
ROW_PITCH = 4.0  # text alignment: a data row at most this far below the previous row (centre to centre)
LINE_CHARS = 200
MAX_REFS = 50
MAX_FOUND = 8  # occurrences quoted in one question ref
MAX_PREFIX_REFS = 10  # refs per prefix in member_mark_prefix_meaning (count stays true)
MAX_EXAMPLES = 5  # marks as written, per prefix subject

CELL_TYPES = frozenset({"TEXT", "MTEXT", "ATTRIB"})
_LINE_TYPES = frozenset({"LINE", "LWPOLYLINE", "POLYLINE"})
_ORDER = {"low": 0, "medium": 1, "high": 2}

# --- marks ----------------------------------------------------------------------------------------

_SIZE = r"(?:\s*\(\s*(?P<b>\d+(?:[.,]\d+)?)\s*(?P<x>[xX\u00d7])\s*(?P<h>\d+(?:[.,]\d+)?)\s*\))?"
_BODY = (
    r"(?P<prefix>[A-Za-zĐđ]{1,4})(?P<sep1>\s?-?\s?)(?P<n1>\d{1,3})"
    r"(?:(?P<sep2>[.\-])(?P<n2>\d{1,3}))?(?P<suffix>[A-Za-z']?)"
)
_MARK = re.compile("^" + _BODY + _SIZE + "$")
_MARK_HEAD = re.compile("^" + _BODY + _SIZE + r"(?=$|[\s,;:])")
_SPACING_LETTERS = frozenset({"a", "s"})  # Ø8a150: a lone lower-case a / s is a spacing, not a mark

# member-type words of a detail title (matched case-insensitively on NFC text), longest first
MEMBER_WORDS = (
    "giằng móng",
    "dầm móng",
    "đài cọc",
    "đài móng",
    "lanh tô",
    "dầm",
    "cột",
    "giằng",
    "móng",
    "sàn",
    "vách",
    "cọc",
    "tie beam",
    "pile cap",
    "footing",
    "column",
    "purlin",
    "rafter",
    "girder",
    "brace",
    "beam",
    "slab",
    "wall",
)
_TITLE = re.compile(
    r"^(?:(?:chi tiết|mặt cắt|detail of|detail|section)\s+)?(?P<word>"
    + "|".join(re.escape(w) for w in sorted(MEMBER_WORDS, key=len, reverse=True))
    + r")\s+(?P<rest>\S.*)$",
    re.IGNORECASE,
)

# header keywords (normalized) -> priority (lower wins) for the mark column
HEADER_KEYWORDS = {
    "ký hiệu": 0,
    "ký hiệu cấu kiện": 0,
    "mark": 0,
    "member mark": 0,
    "tên cấu kiện": 1,
    "member": 1,
    "tên": 2,
    "name": 2,
}
SIZE_KEYWORDS = {
    "b": "b",
    "h": "h",
    "bxh": "bxh",
    "b x h": "bxh",
    "b\u00d7h": "bxh",
    "b \u00d7 h": "bxh",
    "kích thước": "bxh",
    "tiết diện": "bxh",
    "kích thước (bxh)": "bxh",
    "tiết diện (bxh)": "bxh",
    "size": "bxh",
    "section": "bxh",
}
# why a matched mark's size was not compared (marks.json matched[].size_not_compared_reason)
NO_PLAN_SIZE = "the plan mark has no size"
NO_SIZE_COLUMN = "the schedule table has no size column"
SIZE_HEADER_BLOCKED = "the schedule header cells that could name a size column are blocked"
SIZE_CELLS_BLOCKED = "the schedule size cells are blocked"
SIZE_NOT_NUMBERS = "the schedule size cells are not numbers"
_SIZE_VALUE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*[xX\u00d7]\s*(\d+(?:[.,]\d+)?)\s*$")
_NUMBER = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*$")


@dataclass
class Mark:
    """A mark as written. `text` excludes the section; `key` is what matching compares."""

    text: str
    key: str
    prefix: str
    numbers: tuple[str, ...]
    separators: tuple[str, ...]
    suffix: str
    size: dict[str, Any] | None

    @property
    def structure(self) -> tuple[str, tuple[int, ...], str]:
        return (self.prefix.casefold(), tuple(int(n) for n in self.numbers), self.suffix.casefold())

    def lexical(self) -> dict[str, Any]:
        return {
            "prefix": self.prefix,
            "numbers": list(self.numbers),
            "separators": list(self.separators),
            "suffix": self.suffix,
        }


def mark_key(text: str) -> str:
    """NFC + casefold + all whitespace removed: the only equality matching uses."""
    return "".join(normalize(text).split())


def _mark_from(m: re.Match[str], text: str) -> Mark | None:
    if m["prefix"] in _SPACING_LETTERS:
        return None
    mark_text = text[: m.end("suffix")].strip()
    code = _SHEET_CODE.match(mark_text.upper())
    if code and (code["disc"] in ("KT", "KC", "TCXD") or "-" in mark_text or "/" in mark_text):
        return None  # a sheet code (research parsing pattern 3), not a member
    numbers = (m["n1"],) + ((m["n2"],) if m["n2"] else ())
    separators = (m["sep1"],) + ((m["sep2"],) if m["sep2"] else ())
    size = None
    if m["b"]:
        size = {"b": _num(m["b"]), "h": _num(m["h"]), "text": f"{m['b']}{m['x']}{m['h']}"}
    return Mark(mark_text, mark_key(mark_text), m["prefix"], numbers, separators, m["suffix"], size)


def parse_mark(text: str, case_uncertain: bool = False) -> Mark | None:
    """The mark when the WHOLE text (one line) is a mark, optionally with a section; else None."""
    t = unicodedata.normalize("NFC", text).strip()
    m = _MARK.match(t)
    if m is None or scan_line(t, case_uncertain):
        return None
    return _mark_from(m, t)


def parse_title(text: str, case_uncertain: bool = False) -> tuple[str, Mark] | None:
    """(member word as written, mark) when the line is '<member word> <mark> ...'; else None."""
    t = " ".join(unicodedata.normalize("NFC", text).split())
    m = _TITLE.match(t)
    if m is None:
        return None
    rest = m["rest"]
    head = _MARK_HEAD.match(rest)
    if head is None or scan_line(rest[: head.end()], case_uncertain):
        return None
    mark = _mark_from(head, rest[: head.end()])
    return None if mark is None else (m["word"], mark)


def _header_text(text: str) -> str:
    t = " ".join(normalize(text).split())
    t = re.sub(r"\s*\(mm\)$", "", t)
    return t.rstrip(":").strip()


def header_keyword(text: str) -> int | None:
    """Priority of a mark-column keyword when the whole cell is one; else None."""
    return HEADER_KEYWORDS.get(_header_text(text))


def size_role(text: str) -> str | None:
    return SIZE_KEYWORDS.get(_header_text(text))


# --- line grid --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Ln:
    c: float  # y of a horizontal line, x of a vertical one
    a0: float
    a1: float


def _merge(segs: list[tuple[float, float, float]], tol: float) -> list[_Ln]:
    """Collinear segments (same c within tol) whose ranges touch (gap <= tol) become one line."""
    out: list[_Ln] = []
    segs = sorted(segs)
    i = 0
    while i < len(segs):
        j = i
        while j + 1 < len(segs) and segs[j + 1][0] - segs[i][0] <= tol:
            j += 1
        group = segs[i : j + 1]
        c = statistics.median(s[0] for s in group)
        spans = sorted((s[1], s[2]) for s in group)
        a0, a1 = spans[0]
        for b0, b1 in spans[1:]:
            if b0 <= a1 + tol:
                a1 = max(a1, b1)
            else:
                out.append(_Ln(c, a0, a1))
                a0, a1 = b0, b1
        out.append(_Ln(c, a0, a1))
        i = j + 1
    out.sort(key=lambda ln: (ln.c, ln.a0))
    return out


class Lines:
    """Merged axis-aligned lines of one space."""

    def __init__(self, h: list[tuple[float, float, float]], v: list[tuple[float, float, float]], tol: float):
        self.tol = tol
        self.h = _merge(h, tol)
        self.v = _merge(v, tol)
        self._hc = [ln.c for ln in self.h]
        self._vc = [ln.c for ln in self.v]

    def h_in(self, y0: float, y1: float) -> list[_Ln]:
        return self.h[
            bisect.bisect_left(self._hc, y0 - self.tol) : bisect.bisect_right(self._hc, y1 + self.tol)
        ]

    def v_in(self, x0: float, x1: float) -> list[_Ln]:
        return self.v[
            bisect.bisect_left(self._vc, x0 - self.tol) : bisect.bisect_right(self._vc, x1 + self.tol)
        ]

    def _crosses(self, ln: _Ln, at: float) -> bool:
        return ln.a0 - self.tol <= at <= ln.a1 + self.tol

    def cell(self, x: float, y: float, h: float) -> tuple[float, float, float, float] | None:
        """(x_left, y_bottom, x_right, y_top) of the grid cell around a point, or None."""
        above = [ln.c for ln in self.h_in(y, y + MAX_CELL_H * h) if ln.c > y and self._crosses(ln, x)]
        below = [ln.c for ln in self.h_in(y - MAX_CELL_H * h, y) if ln.c < y and self._crosses(ln, x)]
        left = [ln.c for ln in self.v_in(x - MAX_CELL_W * h, x) if ln.c < x and self._crosses(ln, y)]
        right = [ln.c for ln in self.v_in(x, x + MAX_CELL_W * h) if ln.c > x and self._crosses(ln, y)]
        if not (above and below and left and right):
            return None
        return (max(left), max(below), min(right), min(above))

    def covered(self, x: float, y0: float, y1: float) -> bool:
        """A vertical line at x covers [y0, y1]."""
        return any(
            abs(ln.c - x) <= self.tol and ln.a0 <= y0 + self.tol and ln.a1 >= y1 - self.tol
            for ln in self.v_in(x, x)
        )

    def spanning(self, x0: float, x1: float, y0: float, y1: float) -> list[_Ln]:
        """Horizontal lines in [y0, y1] that span [x0, x1]."""
        return [ln for ln in self.h_in(y0, y1) if ln.a0 <= x0 + self.tol and ln.a1 >= x1 - self.tol]


def _edges(entity: Any) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    kind = entity.dxftype()
    if kind == "LINE":
        s, e = entity.dxf.start, entity.dxf.end
        return [((s.x, s.y), (e.x, e.y))]
    if kind == "LWPOLYLINE":
        pts = [(v.x, v.y) for v in entity.vertices_in_wcs()]
        bulges = [p[0] for p in entity.get_points("b")]
        closed = bool(entity.closed)
    elif kind == "POLYLINE" and entity.is_2d_polyline:
        pts = [(v.x, v.y) for v in entity.points_in_wcs()]
        bulges = [float(v.dxf.get("bulge", 0.0)) for v in entity.vertices]
        closed = bool(entity.is_closed)
    else:
        return []
    n = len(pts)
    out = []
    for i in range(n if closed else n - 1):
        if i < len(bulges) and abs(bulges[i]) > 1e-12:
            continue  # an arc, not a table edge
        out.append((pts[i], pts[(i + 1) % n]))
    return out


def read_lines(
    doc: Any, handles_ok: bool, tol_by_space: dict[str, float]
) -> tuple[dict[str, Lines], Counter[str]]:
    """Merged lines per space (only spaces with a tolerance) and what could not be read."""
    walker = Walker(doc, handles_ok)
    problems: Counter[str] = Counter()
    out: dict[str, Lines] = {}
    for space, layout, _ in layout_spaces(doc):
        tol = tol_by_space.get(space)
        if tol is None:
            continue
        hs: list[tuple[float, float, float]] = []
        vs: list[tuple[float, float, float]] = []
        for placed in walker.walk(layout, space, _LINE_TYPES):
            try:
                edges = _edges(placed.entity)
            except Exception as exc:  # one bad entity is counted, never fatal
                problems[f"edge_error:{type(exc).__name__}"] += 1
                continue
            for (x0, y0), (x1, y1) in edges:
                length = math.hypot(x1 - x0, y1 - y0)
                if length <= 0:
                    continue
                if abs(y1 - y0) <= 1e-3 * length:
                    hs.append(((y0 + y1) / 2, min(x0, x1), max(x0, x1)))
                elif abs(x1 - x0) <= 1e-3 * length:
                    vs.append(((x0 + x1) / 2, min(y0, y1), max(y0, y1)))
        out[space] = Lines(hs, vs, tol)
    problems.update(walker.skipped)
    return out, problems


# --- tables ------------------------------------------------------------------------------------------

Box = tuple[float, float, float, float]


@dataclass
class _Text:
    entry: dict[str, Any]
    box: Box
    cx: float
    cy: float
    h: float
    block: str | None  # meaning_block_reason

    @property
    def id(self) -> str:
        return self.entry["id"]


@dataclass
class _Table:
    detection: str
    bbox: Box
    columns: list[tuple[float, float]]
    header: list[tuple[int | None, _Text]]
    rows: list[tuple[Box, list[tuple[int | None, _Text]]]]
    mark_column: int | None
    header_blocked: bool
    anchor: _Text
    ids: set[str] = field(default_factory=set)
    inferred: bool = False  # the mark column is the seed's column, not named by an allowed keyword


def _column(columns: list[tuple[float, float]], x: float) -> int | None:
    for i, (x0, x1) in enumerate(columns):
        if x0 <= x <= x1:
            return i
    return None


def _box_has(box: Box, t: _Text) -> bool:
    return box[0] <= t.cx <= box[2] and box[1] <= t.cy <= box[3]


def _union(boxes: list[Box]) -> Box:
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def _mark_priority(cells: list[tuple[int | None, _Text]]) -> int | None:
    """Column of the best allowed header keyword, or None."""
    best: tuple[int, float, int] | None = None
    for col, t in cells:
        if col is None or t.block is not None:
            continue
        prio = header_keyword(t.entry["display_text"])
        if prio is not None and (best is None or (prio, t.cx) < best[:2]):
            best = (prio, t.cx, col)
    return None if best is None else best[2]


def _grid_table(lines: Lines, seed: _Text, pool: list[_Text], keyword: bool) -> _Table | str | None:
    """The line-grid table around a seed text. None: no grid there. A string: why it is not a table."""
    cell = lines.cell(seed.cx, seed.cy, seed.h)
    if cell is None:
        return None
    xl, _, xr, _ = cell
    reach = 400.0 * seed.h
    spans = lines.spanning(xl, xr, seed.cy - reach, seed.cy + reach)
    ys: list[float] = []
    for ln in sorted(spans, key=lambda ln: -ln.c):
        if not ys or ys[-1] - ln.c > lines.tol:
            ys.append(ln.c)
    i = next((k for k in range(len(ys) - 1) if ys[k] >= seed.cy >= ys[k + 1]), None)
    if i is None:
        return None

    def band_ok(top: float, bottom: float) -> bool:
        return (
            top - bottom <= MAX_BAND * seed.h
            and lines.covered(xl, bottom, top)
            and lines.covered(xr, bottom, top)
        )

    if not band_ok(ys[i], ys[i + 1]):
        return None
    top, bottom = i, i + 1
    while top > 0 and band_ok(ys[top - 1], ys[top]):
        top -= 1
    while bottom + 1 < len(ys) and band_ok(ys[bottom], ys[bottom + 1]):
        bottom += 1
    bands = [(ys[k], ys[k + 1]) for k in range(top, bottom)]
    if keyword:
        head = i - top
    else:
        head = 0
        if i == top:
            return "the mark is in the top band"
    t_line = [ln for ln in spans if abs(ln.c - ys[top]) <= lines.tol]
    b_line = [ln for ln in spans if abs(ln.c - ys[bottom]) <= lines.tol]
    x_lo = max(max(ln.a0 for ln in t_line), max(ln.a0 for ln in b_line), -math.inf)
    x_hi = min(min(ln.a1 for ln in t_line), min(ln.a1 for ln in b_line), math.inf)
    probe_band = bands[head + 1] if head + 1 < len(bands) else bands[head]
    probe_y = (probe_band[0] + probe_band[1]) / 2
    xs = sorted(
        {x_lo, x_hi}
        | {ln.c for ln in lines.v_in(x_lo, x_hi) if ln.a0 - lines.tol <= probe_y <= ln.a1 + lines.tol}
    )
    bounds: list[float] = []
    for x in xs:
        if x_lo - lines.tol <= x <= x_hi + lines.tol and (not bounds or x - bounds[-1] > lines.tol):
            bounds.append(x)
    columns = list(itertools.pairwise(bounds))
    if len(columns) < 2:
        return "the grid around it has fewer than two columns"
    head_top, head_bottom = bands[head]
    table_box = (x_lo, ys[bottom], x_hi, head_top)
    inside = [
        t
        for t in pool
        if x_lo <= t.cx <= x_hi and ys[bottom] <= t.cy <= head_top and t.entry["entity_type"] in CELL_TYPES
    ]
    header = [(_column(columns, t.cx), t) for t in inside if head_bottom <= t.cy <= head_top]
    rows = []
    for b_top, b_bottom in bands[head + 1 :]:
        cells = [(_column(columns, t.cx), t) for t in inside if b_bottom <= t.cy < b_top]
        if cells:
            rows.append(
                ((x_lo, b_bottom, x_hi, b_top), sorted(cells, key=lambda c: (c[0] or 0, -c[1].cy, c[1].cx)))
            )
    mark_col = _mark_priority(header)
    inferred = mark_col is None and not keyword
    if mark_col is None:
        mark_col = _column(columns, seed.cx)
    if mark_col is None:
        return "the text it was found from lies in no column of the grid"
    # only the mark column's header can block the table (fix 8); other blocked cells are blocked_columns
    header_blocked = inferred and any(t.block is not None for c, t in header if c == mark_col)
    table = _Table("line_grid", table_box, columns, header, rows, mark_col, header_blocked, seed)
    table.ids = {t.id for t in inside}
    table.inferred = inferred
    return table


def _upright(entry: dict[str, Any]) -> bool:
    r = (entry.get("rotation") or 0.0) % 360.0
    return min(r, 360.0 - r) <= 0.5


def _aligned_table(seed: _Text, pool: list[_Text]) -> _Table | str:
    """The text-aligned table under a header keyword, or why there is none."""
    h = seed.h
    flat = [t for t in pool if t.entry["entity_type"] in CELL_TYPES and _upright(t.entry)]

    def same_row(t: _Text) -> bool:
        overlap = min(t.box[3], seed.box[3]) - max(t.box[1], seed.box[1])
        return overlap >= 0.5 * min(t.box[3] - t.box[1], seed.box[3] - seed.box[1]) > 0

    row = sorted((t for t in flat if same_row(t)), key=lambda t: t.box[0])
    k = next((i for i, t in enumerate(row) if t.id == seed.id), None)
    if k is None:  # the keyword is rotated or not a cell text: it is not part of any header row
        return "the header keyword is rotated or is not a cell text, so no header row can be read"
    lo = hi = k
    while lo > 0 and row[lo].box[0] - row[lo - 1].box[2] <= COL_GAP * h:
        lo -= 1
    while hi + 1 < len(row) and row[hi + 1].box[0] - row[hi].box[2] <= COL_GAP * h:
        hi += 1
    head = row[lo : hi + 1]
    centres = [t.cx for t in head]
    edges = [head[0].box[0] - h] + [(a + b) / 2 for a, b in itertools.pairwise(centres)]
    edges.append(head[-1].box[2] + h)
    columns = list(itertools.pairwise(edges))
    header: list[tuple[int | None, _Text]] = list(enumerate(head))
    mark_col = _mark_priority(header)
    if mark_col is None:
        mark_col = next(i for i, t in header if t.id == seed.id)
    head_bottom = min(t.box[1] for t in head)
    head_cy = statistics.median(t.cy for t in head)
    below = sorted(
        (
            t
            for t in flat
            if t.cy < head_bottom and edges[0] <= t.cx <= edges[-1] and t.id not in {x.id for x in head}
        ),
        key=lambda t: (-t.cy, t.cx),
    )
    groups: list[list[_Text]] = []
    for t in below:
        if groups and groups[-1][0].cy - t.cy <= ROW_TOL * h:
            groups[-1].append(t)
        else:
            groups.append([t])
    rows = []
    prev_cy = head_cy
    for g in groups:
        if prev_cy - g[0].cy > ROW_PITCH * h:
            break
        cells = sorted(((_column(columns, t.cx), t) for t in g), key=lambda c: (c[0] or 0, c[1].cx))
        cols = {c for c, _ in cells if c is not None}
        if mark_col not in cols or (len(columns) >= 2 and len(cols) < 2):
            break
        rows.append((_union([t.box for t in g]), cells))
        prev_cy = statistics.median(t.cy for t in g)
    if len(columns) < 2:
        return "the header row has a single cell"
    if len(rows) < 2:
        return "fewer than two data rows aligned under the header columns"
    bbox = _union([t.box for t in head] + [b for b, _ in rows])
    table = _Table("text_alignment", bbox, columns, header, rows, mark_col, False, seed)
    table.ids = {t.id for t in head} | {t.id for _, cells in rows for _, t in cells}
    return table


# --- one file ---------------------------------------------------------------------------------------


def _cell_doc(col: int | None, t: _Text) -> dict[str, Any]:
    return {
        "column": col,
        "entry_id": t.id,
        "display_text": " ".join(t.entry["display_text"].split())[:LINE_CHARS],
        "meaning": "allowed" if t.block is None else "blocked",
        "block_reason": t.block,
    }


def _round_box(box: Box) -> list[float]:
    return [round(v, 3) for v in box]


def _min_conf(*values: str) -> str:
    return min(values, key=_ORDER.__getitem__)


@dataclass
class _FileOut:
    plan: list[dict[str, Any]] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    unparsed: list[dict[str, Any]] = field(default_factory=list)
    blocked: list[dict[str, Any]] = field(default_factory=list)


def _space_tolerances(entries: list[dict[str, Any]]) -> dict[str, float]:
    heights: dict[str, list[float]] = {}
    for e in entries:
        if e["height"] is not None and e["height"] > 0:
            heights.setdefault(e["space"], []).append(e["height"])
    return {space: LINE_TOL * statistics.median(hs) for space, hs in heights.items()}


def _dxf_path(inv_work: Path, loaded: LoadedFile, input_dir: Path | None) -> tuple[Path | None, str | None]:
    row = loaded.row
    if row["format"] == "dwg":
        if row.get("converted") is None:
            return None, "the DWG has no converted DXF"
        return _inside(inv_work, row["converted"], f"{loaded.rel}: converted DXF"), None
    if input_dir is not None:
        return input_dir / loaded.rel, None
    assert loaded.text_index is not None
    recorded = Path(loaded.text_index["file"]["path"])
    if recorded.is_absolute():
        return recorded, None
    return None, "a native DXF is read from the intake input folder: pass --input-dir to use its lines"


def _load_lines(
    inv_work: Path, loaded: LoadedFile, input_dir: Path | None, warnings: list[str]
) -> tuple[dict[str, Lines], dict[str, Any]]:
    assert loaded.text_index is not None
    path, why = _dxf_path(inv_work, loaded, input_dir)
    info: dict[str, Any] = {"status": "unavailable", "reason": why, "skipped": {}}
    if path is not None and not path.is_file():
        why = f"DXF not found: {path.name}"
    if path is None or not path.is_file():
        info["reason"] = why
        warnings.append(f"{loaded.rel}: line grids not read ({why}); tables come from text alignment only")
        return {}, info
    try:
        doc = open_checked(path, loaded.text_index)
    except ValueError as exc:
        raise ReaderError(EXIT_INVALID, f"{loaded.rel}: {exc}") from exc
    except (OSError, DXFError) as exc:
        info["reason"] = f"the DXF cannot be read: {type(exc).__name__}"
        warnings.append(f"{loaded.rel}: line grids not read ({exc}); tables come from text alignment only")
        return {}, info
    lines, problems = read_lines(
        doc,
        bool(loaded.text_index["file"]["handles_reliable"]),
        _space_tolerances(loaded.text_index["entries"]),
    )
    info.update(status="read", reason=None, skipped=dict(sorted(problems.items())))
    if problems:
        warnings.append(
            f"{loaded.rel}: some geometry was not read for line grids: {dict(sorted(problems.items()))}"
        )
    return lines, info


def _texts(entries: list[dict[str, Any]], claimed: set[str]) -> list[_Text]:
    out = []
    for e in entries:
        if e["id"] in claimed or e["entity_type"] == "DIMENSION" or not e["display_text"].strip():
            continue
        if e["height"] is None or e["height"] <= 0:
            continue
        box = text_box(e)
        if box is None:
            continue
        out.append(
            _Text(
                e,
                box,
                (box[0] + box[2]) / 2,
                (box[1] + box[3]) / 2,
                float(e["height"]),
                meaning_block_reason(e),
            )
        )
    return out


def _tables_of_group(
    pool: list[_Text], lines: Lines | None
) -> tuple[list[_Table], list[tuple[_Text, str, str, Box | None]]]:
    """Tables of one (sheet, space) group and the unparsed ones: (anchor, detection, reason, bbox)."""
    tables: list[_Table] = []
    unparsed: list[tuple[_Text, str, str, Box | None]] = []

    def taken(t: _Text) -> bool:
        return any(t.id in tb.ids or _box_has(tb.bbox, t) for tb in tables)

    anchors = [t for t in pool if t.block is None and header_keyword(t.entry["display_text"]) is not None]
    for anchor in anchors:
        if taken(anchor):
            continue
        result: _Table | str | None = None
        detection = "line_grid"
        if lines is not None:
            result = _grid_table(lines, anchor, pool, keyword=True)
        if result is None:
            detection = "text_alignment"
            result = _aligned_table(anchor, pool)
        if isinstance(result, str):
            unparsed.append((anchor, detection, result, None))
            continue
        marked = sum(1 for _, cells in result.rows if any(c == result.mark_column for c, _ in cells))
        if marked < 2:
            unparsed.append(
                (anchor, detection, "fewer than two data rows with a cell in the mark column", result.bbox)
            )
            continue
        tables.append(result)
    if lines is None:
        return tables, unparsed
    # blocked headers and keyword-less grids: seeded by mark-shaped allowed texts in a grid cell
    seen_boxes: list[Box] = []
    for seed in pool:
        if seed.block is not None or taken(seed) or seed.entry["entity_type"] not in CELL_TYPES:
            continue
        if any(_box_has(b, seed) for b in seen_boxes):
            continue
        if parse_mark(seed.entry["display_text"], seed.entry["decode"]["case_uncertain"]) is None:
            continue
        result = _grid_table(lines, seed, pool, keyword=False)
        if not isinstance(result, _Table):
            continue
        seed_col = _column(result.columns, seed.cx)
        marked = sum(
            1
            for _, cells in result.rows
            if any(
                c == seed_col
                and t.block is None
                and parse_mark(t.entry["display_text"], t.entry["decode"]["case_uncertain"]) is not None
                for c, t in cells
            )
        )
        if marked < 2:
            continue
        if any(_box_has(result.bbox, a) for a, _, _, _ in unparsed):
            continue  # the keyword pass already judged this table
        if not result.inferred or _plausible_blocked_header(result):
            seen_boxes.append(result.bbox)
            tables.append(result)
        # otherwise not a schedule: a plan region between drawn lines, or a table with no keyword (a miss)
    return tables, unparsed


def _plausible_blocked_header(table: _Table) -> bool:
    """A header row without a keyword that still marks a schedule: it holds blocked text, spans at least
    two columns and holds no mark-shaped text."""
    if not any(t.block is not None for _, t in table.header):
        return False
    cols = {c for c, _ in table.header if c is not None}
    marks_in_header = any(
        t.block is None
        and parse_mark(t.entry["display_text"], t.entry["decode"]["case_uncertain"]) is not None
        for _, t in table.header
    )
    return len(cols) >= 2 and not marks_in_header


def _scan_file(
    inv_work: Path,
    loaded: LoadedFile,
    input_dir: Path | None,
    warnings: list[str],
    skipped_sheets: list[dict[str, Any]],
) -> tuple[_FileOut, dict[str, Any]]:
    assert loaded.text_index is not None
    entries = loaded.text_index["entries"]
    out = _FileOut()
    sheet_of: dict[str, dict[str, Any]] = {}
    duplicate_ids: set[str] = set()
    order: list[dict[str, Any] | None] = []
    if loaded.sheets is not None:
        for sh in loaded.sheets["sheets"]:
            if sh["duplicate_of"] is not None:
                duplicate_ids.update(sh["text_ids"])
                skipped_sheets.append(
                    {
                        "file": loaded.rel,
                        "sheet": sh["sheet_id"],
                        "duplicate_of": sh["duplicate_of"],
                        "text_entries": len(sh["text_ids"]),
                    }
                )
            else:
                sheet_of.update({tid: sh for tid in sh["text_ids"]})
                order.append(sh)
    order.append(None)
    claimed = _claimed_text_ids(inv_work, loaded, warnings) | duplicate_ids
    lines_by_space, grid_info = _load_lines(inv_work, loaded, input_dir, warnings)
    texts = _texts(entries, claimed)
    groups: dict[tuple[str | None, str], list[_Text]] = {}
    for t in texts:
        sh = sheet_of.get(t.id)
        groups.setdefault((None if sh is None else sh["sheet_id"], t.entry["space"]), []).append(t)
    sheets_by_id = {sh["sheet_id"]: sh for sh in order if sh is not None}
    in_table: set[str] = set()
    group_keys = sorted(
        groups, key=lambda k: (k[0] is None, [s["sheet_id"] if s else None for s in order].index(k[0]), k[1])
    )
    for sheet_id, space in group_keys:
        sheet = None if sheet_id is None else sheets_by_id[sheet_id]
        tables, unparsed = _tables_of_group(groups[(sheet_id, space)], lines_by_space.get(space))
        for tb in tables:
            in_table |= tb.ids
            out.tables.append(_table_doc(loaded.rel, sheet, space, tb))
        for anchor, detection, reason, bbox in unparsed:
            in_table.add(anchor.id)
            if bbox is not None:  # what was found of it is a schedule, not a plan
                in_table |= {t.id for t in groups[(sheet_id, space)] if _box_has(bbox, t)}
            out.unparsed.append(
                {
                    "file": loaded.rel,
                    "sheet": sheet_id,
                    "sheet_number": None if sheet is None else printed_number(sheet),
                    "space": space,
                    "bbox": _round_box(bbox if bbox is not None else anchor.box),
                    "detection": detection,
                    "anchor_entry_id": anchor.id,
                    "anchor_text": " ".join(anchor.entry["display_text"].split())[:LINE_CHARS],
                    "reason": reason,
                }
            )
    by_id = {t.id: t.entry for t in texts}
    for t_index, tdoc in enumerate(out.tables):
        for row in tdoc["rows"]:
            for cell in row["cells"]:
                in_mark_col = cell["column"] is not None and cell["column"] == tdoc["mark_column"]
                if tdoc["header_blocked"]:
                    entry = by_id[cell["entry_id"]]
                    if meaning_block_reason(entry) is not None:
                        continue  # blocked by its own text: shape unknown
                    if parse_mark(entry["display_text"], entry["decode"]["case_uncertain"]) is None:
                        continue
                    reason = "header_blocked:" + ",".join(tdoc["header_block_reasons"])
                elif in_mark_col and cell["meaning"] == "blocked":
                    reason = cell["block_reason"]
                else:
                    continue
                out.blocked.append(
                    {
                        "file": loaded.rel,
                        "sheet": tdoc["sheet"],
                        "table": "",
                        "_t": t_index,
                        "row": row["index"],
                        "entry_id": cell["entry_id"],
                        "display_text": cell["display_text"],
                        "reason": reason,
                    }
                )
    for t in texts:
        if t.id in in_table or t.block is not None:
            continue
        sh = sheet_of.get(t.id)
        out.plan.extend(_plan_marks(loaded.rel, sh, t.entry))
    return out, grid_info


def _plan_marks(rel: str, sheet: dict[str, Any] | None, entry: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    cu = entry["decode"]["case_uncertain"]
    for line in entry["display_text"].split("\n"):
        if not line.strip():
            continue
        title = None
        mark = parse_mark(line, cu)
        if mark is None:
            found = parse_title(line, cu)
            if found is None:
                continue
            title, mark = found
        conf = _confidence("medium", entry, ())
        flags = list(entry["flags"])
        if cu:
            flags.append("case_uncertain")
        doc: dict[str, Any] = {
            "id": "",
            "file": rel,
            "sheet": None if sheet is None else sheet["sheet_id"],
            "sheet_number": None if sheet is None else printed_number(sheet),
            "space": entry["space"],
            "text_ref": {"file": rel, "entry_id": entry["id"]},
            "display_text": " ".join(line.split())[:LINE_CHARS],
            "position": {"x": entry["position"]["x"], "y": entry["position"]["y"]},
            "mark": mark.text,
            "key": mark.key,
            "lexical": mark.lexical(),
            "size": mark.size,
            "form": "title"
            if title
            else ("with_size" if mark.size else ("sub_number" if len(mark.numbers) > 1 else "plain")),
            "title_member_word": None if title is None else {"word": title, "confidence": conf},
            "in_callouts": title is None and mark.size is None and member_mark(line, cu) is not None,
            "confidence": conf,
            "flags": flags,
            "provenance": _provenance(rel, sheet, entry),
        }
        doc["_structure"] = mark.structure
        out.append(doc)
    return out


def _schedule_mark(cell: dict[str, Any], entry: dict[str, Any]) -> tuple[Mark | None, str]:
    cu = entry["decode"]["case_uncertain"]
    mark = parse_mark(cell["display_text"], cu)
    if mark is None:
        found = parse_title(cell["display_text"], cu)
        mark = None if found is None else found[1]
    return mark, (mark.key if mark else mark_key(cell["display_text"]))


def _table_doc(rel: str, sheet: dict[str, Any] | None, space: str, tb: _Table) -> dict[str, Any]:
    roles: dict[int, str] = {}
    if not tb.header_blocked:
        for col, t in tb.header:
            role = size_role(t.entry["display_text"]) if t.block is None else None
            if col is not None and role is not None and col != tb.mark_column:
                roles.setdefault(col, role)
    conf = "low" if tb.header_blocked or tb.inferred else _confidence("medium", tb.anchor.entry, ())
    header_reasons = sorted({t.block for _, t in tb.header if t.block is not None})
    ordered_header = sorted(tb.header, key=lambda ct: (ct[1].cx, -ct[1].cy))
    blocked_columns = [
        {"column": c, "entry_id": t.id, "reason": t.block}
        for c, t in ordered_header
        if t.block is not None and not tb.header_blocked and c != tb.mark_column
    ]
    rows = []
    for index, (box, cells) in enumerate(tb.rows, start=1):
        cell_docs = [_cell_doc(c, t) for c, t in cells]
        if tb.header_blocked:
            for cd in cell_docs:
                cd["meaning"] = "blocked"
                cd["block_reason"] = cd["block_reason"] or "header_blocked"
        marks = []
        if tb.mark_column is not None and not tb.header_blocked:
            for cd, (_, t) in zip(cell_docs, cells, strict=True):
                if cd["column"] != tb.mark_column or cd["meaning"] != "allowed":
                    continue
                mark, key = _schedule_mark(cd, t.entry)
                if not key:
                    continue
                marks.append(
                    {
                        "entry_id": t.id,
                        "text": mark.text if mark else cd["display_text"],
                        "key": key,
                        "shape": "mark" if mark else "other",
                        "confidence": _min_conf(conf, _confidence("medium", t.entry, ())),
                        "_structure": None if mark is None else mark.structure,
                    }
                )
        size, size_reason = _row_size(cells, roles, bool(blocked_columns))
        rows.append(
            {
                "index": index,
                "bbox": _round_box(box),
                "cells": cell_docs,
                "marks": marks,
                "size": size,
                "_size_reason": size_reason,
            }
        )
    columns = [
        {
            "index": i,
            "x0": round(x0, 3),
            "x1": round(x1, 3),
            "role": "mark" if i == tb.mark_column and not tb.header_blocked else roles.get(i),
        }
        for i, (x0, x1) in enumerate(tb.columns)
    ]
    header = [_cell_doc(c, t) for c, t in ordered_header]
    prov: dict[str, Any] = {
        "file": rel,
        "sheet": sheet_label(sheet),
        "method": "table",
        "region": {"bbox": _round_box(tb.bbox)},
    }
    revision = None if sheet is None else sheet["title_block"]["revision"]
    if revision is not None:
        prov["revision"] = revision["value"]
    return {
        "id": "",
        "file": rel,
        "sheet": None if sheet is None else sheet["sheet_id"],
        "sheet_number": None if sheet is None else printed_number(sheet),
        "space": space,
        "bbox": _round_box(tb.bbox),
        "detection": tb.detection,
        "anchor_entry_id": tb.anchor.id,
        "header_blocked": tb.header_blocked,
        "header_block_reasons": header_reasons if tb.header_blocked else [],
        "blocked_columns": blocked_columns,
        "header": header,
        "columns": columns,
        "mark_column": None if tb.header_blocked else tb.mark_column,
        "rows": rows,
        "confidence": conf,
        "provenance": prov,
    }


def _row_size(
    cells: list[tuple[int | None, _Text]], roles: dict[int, str], header_cells_blocked: bool
) -> tuple[dict[str, Any] | None, str | None]:
    """The row's (b, h) from its size columns, else None and why (a SIZE_* reason)."""
    named = set(roles.values())
    if "bxh" not in named and not {"b", "h"} <= named:
        return None, SIZE_HEADER_BLOCKED if header_cells_blocked else NO_SIZE_COLUMN
    found: dict[str, tuple[int | float, str]] = {}
    blocked = False
    for col, t in cells:
        role = roles.get(col) if col is not None else None
        if role is None:
            continue
        if t.block is not None:
            blocked = True
            continue
        text = " ".join(t.entry["display_text"].split())
        if role == "bxh":
            m = _SIZE_VALUE.match(text)
            if m:
                found.setdefault("b", (_num(m[1]), t.id))
                found.setdefault("h", (_num(m[2]), t.id))
        else:
            m = _NUMBER.match(text)
            if m:
                found.setdefault(role, (_num(m[1]), t.id))
    if "b" not in found or "h" not in found:
        return None, SIZE_CELLS_BLOCKED if blocked else SIZE_NOT_NUMBERS
    size = {"b": found["b"][0], "h": found["h"][0], "entry_ids": sorted({found["b"][1], found["h"][1]})}
    return size, None


# --- matching -----------------------------------------------------------------------------------------


def _match_file(file: str, plan: list[dict[str, Any]], tables: list[dict[str, Any]]) -> dict[str, Any]:
    plan_by_key: dict[str, list[dict[str, Any]]] = {}
    for p in plan:
        plan_by_key.setdefault(p["key"], []).append(p)
    sched_by_key: dict[str, list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]] = {}
    matchable = [t for t in tables if not t["header_blocked"] and t["mark_column"] is not None]
    for t in matchable:
        for row in t["rows"]:
            for m in row["marks"]:
                sched_by_key.setdefault(m["key"], []).append((t, row, m))

    def first_text(key: str) -> str:
        if key in sched_by_key:
            return sched_by_key[key][0][2]["text"]
        return plan_by_key[key][0]["mark"]

    def sched_refs(key: str) -> list[dict[str, Any]]:
        return [
            {"table": t["id"], "row": row["index"], "entry_id": m["entry_id"]}
            for t, row, m in sched_by_key[key]
        ]

    matched, schedule_only, plan_only, conflicts = [], [], [], []
    for key in sorted(set(plan_by_key) | set(sched_by_key)):
        ps, ss = plan_by_key.get(key, []), sched_by_key.get(key, [])
        if ps and ss:
            conf = _min_conf(*(p["confidence"] for p in ps), *(m["confidence"] for _, _, m in ss))
            match: dict[str, Any] = {
                "key": key,
                "mark": first_text(key),
                "plan_marks": [p["id"] for p in ps],
                "schedule": sched_refs(key),
                "confidence": conf,
                "size_compared": False,
            }
            matched.append(match)
            row_reasons: set[str] = set()
            for p in ps:
                if p["size"] is None:
                    continue
                for t, row, m in ss:
                    size = row["size"]
                    if size is None:
                        row_reasons.add(row["_size_reason"])
                        continue
                    match["size_compared"] = True
                    if (size["b"], size["h"]) == (p["size"]["b"], p["size"]["h"]):
                        continue
                    conflicts.append(
                        {
                            "key": key,
                            "mark": first_text(key),
                            "plan_mark": p["id"],
                            "plan_entry_id": p["text_ref"]["entry_id"],
                            "plan_text": p["display_text"],
                            "plan_size": {"b": p["size"]["b"], "h": p["size"]["h"]},
                            "table": t["id"],
                            "row": row["index"],
                            "schedule_entry_id": m["entry_id"],
                            "schedule_size": size,
                        }
                    )
            if not match["size_compared"]:
                reasons = sorted(row_reasons) if row_reasons else [NO_PLAN_SIZE]
                match["size_not_compared_reason"] = "; ".join(reasons)
        elif ss:
            schedule_only.append({"key": key, "mark": first_text(key), "schedule": sched_refs(key)})
        elif matchable:
            plan_only.append({"key": key, "mark": first_text(key), "plan_marks": [p["id"] for p in ps]})
    by_structure: dict[tuple[str, tuple[int, ...], str], set[str]] = {}
    for p in plan:
        by_structure.setdefault(p["_structure"], set()).add(p["key"])
    for key, items in sched_by_key.items():
        for _, _, m in items:
            if m["_structure"] is not None:
                by_structure.setdefault(m["_structure"], set()).add(key)
    variants = []
    for structure, keys in sorted(by_structure.items(), key=lambda kv: sorted(kv[1])):
        if len(keys) < 2:
            continue
        variants.append(
            {
                "structure": {"prefix": structure[0], "numbers": list(structure[1]), "suffix": structure[2]},
                "marks": [
                    {
                        "key": k,
                        "mark": first_text(k),
                        "plan_marks": [p["id"] for p in plan_by_key.get(k, [])],
                        "schedule": sched_refs(k) if k in sched_by_key else [],
                    }
                    for k in sorted(keys)
                ],
            }
        )
    return {
        "file": file,
        "schedule_tables": len(matchable),
        "matched": matched,
        "schedule_only": schedule_only,
        "plan_only": plan_only,
        "notation_variants": variants,
        "size_conflicts": conflicts,
    }


# --- questions --------------------------------------------------------------------------------------

VARIANT_MESSAGE = (
    "The same member mark is written in different notations in this file (another separator, or leading "
    "zeros), e.g. D1.1 and D1-1. Each group in `subjects` lists marks with the same letters and numbers. "
    "Do the marks of a group name the same member? They are never merged without your answer."
)
SIZE_MESSAGE = (
    "A plan mark with a section in brackets (b x h) and the schedule row of the same mark give different "
    "sizes. Which size is right? Both texts are quoted with their entry ids."
)
PREFIX_MESSAGE = (
    "What does each member mark prefix listed in `subjects` mean in this project (column, beam, slab, "
    "footing, tie beam, lintel, steel member...)? No standard defines the letters; use the drawing legend or "
    "the member schedule. A member word in a detail title is evidence, not the answer. Answer with one value "
    "per prefix, e.g. --value C=column. (research, section 4 and ambiguous #11)"
)
UNPARSED_MESSAGE = (
    "A schedule table was found but its rows could not be read reliably (reason per ref). Read it from the "
    "drawing; its rows are not matched to plan marks."
)


def _table_ref(table: dict[str, Any]) -> str:
    """How a question names a table. Never its id (S001.. numbers the tables across ALL files, so a table
    added to file A would re-key file B's questions); the anchor text entry is stable within the file."""
    return f"table (header text entry {table['anchor_entry_id']})"


def _occurrences(
    variant: dict[str, Any], plan_by_id: dict[str, dict[str, Any]], tables_by_id: dict[str, dict[str, Any]]
) -> list[str]:
    found = []
    for m in variant["marks"]:
        for pid in m["plan_marks"]:
            p = plan_by_id[pid]
            found.append(f"'{p['mark']}' ({p['text_ref']['entry_id']}, {p['sheet'] or 'no sheet'}, plan)")
        for s in m["schedule"]:
            table = tables_by_id[s["table"]]
            sheet = table["sheet"] or "no sheet"
            where = f"schedule {_table_ref(table)} row {s['row']}"
            found.append(f"'{m['mark']}' ({s['entry_id']}, {sheet}, {where})")
    return sorted(found, key=lambda f: f.split("(", 1)[1])


def _prefix_questions(plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One blocking member_mark_prefix_meaning per file over its plan marks: one subject per prefix
    (upper-cased, as callouts listed them), refs capped per prefix, counts true. The refs' wording differs
    from the question callouts raised before wave 2, so the two keys never collide."""
    by_file: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for p in plan:
        by_file.setdefault(p["file"], {}).setdefault(p["lexical"]["prefix"].upper(), []).append(p)
    out = []
    for file in sorted(by_file):
        refs: list[dict[str, Any]] = []
        subjects = []
        for prefix in sorted(by_file[file]):
            group = by_file[file][prefix]
            written = Counter(p["mark"] for p in group)
            examples = [
                {"mark": mark, "count": n}
                for mark, n in sorted(written.items(), key=lambda kv: (-kv[1], kv[0]))[:MAX_EXAMPLES]
            ]
            subjects.append({"name": prefix, "count": len(group), "examples": examples})
            for p in group[:MAX_PREFIX_REFS]:
                ref = {
                    "file": file,
                    "where": f"plan mark prefix {prefix}, text entry {p['text_ref']['entry_id']}",
                    "found": p["display_text"],
                }
                if p["sheet"] is not None:
                    ref["sheet"] = p["sheet"]
                refs.append(ref)
        q = question_group(
            "member_mark_prefix_meaning", True, PREFIX_MESSAGE, refs, file=file, subjects=subjects
        )
        q["count"] = sum(s["count"] for s in subjects)
        q["truncated"] = len(refs) < q["count"]
        out.append(q)
    return out


def marks_questions(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Raw questions of a marks document: one per (code, file). Refs are sorted, so keys are stable."""
    plan_by_id = {p["id"]: p for p in doc["plan_marks"]}
    tables_by_id = {t["id"]: t for t in doc["tables"]}
    out: list[dict[str, Any]] = _prefix_questions(doc["plan_marks"])
    for match in doc["matching"]:
        file = match["file"]
        if match["notation_variants"]:
            refs, subjects = [], []
            for v in match["notation_variants"]:
                names = " / ".join(m["mark"] for m in v["marks"])
                occ = _occurrences(v, plan_by_id, tables_by_id)
                shown = "; ".join(occ[:MAX_FOUND]) + (
                    f"; +{len(occ) - MAX_FOUND} more" if len(occ) > MAX_FOUND else ""
                )
                refs.append({"file": file, "where": f"marks {names}", "found": shown})
                subjects.append({"name": names, "count": len(occ)})
            refs.sort(key=lambda r: r["where"])
            subjects.sort(key=lambda s: s["name"])
            out.append(
                question_group(
                    "mark_notation_equivalence",
                    True,
                    VARIANT_MESSAGE,
                    refs,
                    MAX_REFS,
                    file=file,
                    subjects=subjects,
                )
            )
        if match["size_conflicts"]:
            refs = []
            for c in match["size_conflicts"]:
                p = plan_by_id[c["plan_mark"]]
                s = c["schedule_size"]
                refs.append(
                    {
                        "file": file,
                        "sheet": p["sheet"],
                        "where": f"mark {c['mark']}: plan text entry {c['plan_entry_id']}, "
                        f"schedule {_table_ref(tables_by_id[c['table']])} row {c['row']} "
                        f"text entry {c['schedule_entry_id']}",
                        "found": f"plan '{c['plan_text']}' gives {c['plan_size']['b']} x "
                        f"{c['plan_size']['h']}; schedule size cells {', '.join(s['entry_ids'])} give "
                        f"{s['b']} x {s['h']}",
                    }
                )
            refs = [
                {k: v for k, v in r.items() if v is not None} for r in sorted(refs, key=lambda r: r["where"])
            ]
            out.append(question_group("mark_size_conflict", True, SIZE_MESSAGE, refs, MAX_REFS, file=file))
    by_file: dict[str, list[dict[str, Any]]] = {}
    for u in doc["unparsed_tables"]:
        ref: dict[str, Any] = {
            "file": u["file"],
            "where": f"{u['space']} bbox {[round(v, 1) for v in u['bbox']]} "
            f"(header text entry {u['anchor_entry_id']})",
            "found": f"{u['reason']}; header text '{u['anchor_text']}'",
        }
        if u["sheet"] is not None:
            ref["sheet"] = u["sheet"]
        by_file.setdefault(u["file"], []).append(ref)
    for file in sorted(by_file):
        refs = sorted(by_file[file], key=lambda r: (r.get("sheet") or "", r["where"]))
        out.append(
            question_group("schedule_table_unparsed", False, UNPARSED_MESSAGE, refs, MAX_REFS, file=file)
        )
    return sorted(out, key=lambda q: (not q["blocking"], q["code"], q["file"]))


def question_counts(questions: list[dict[str, Any]]) -> dict[str, int]:
    """Per code, how many things are asked (variant groups, conflicts, unparsed tables; for prefixes the
    number of distinct prefixes over the project, as callouts counted them)."""
    counts: Counter[str] = Counter()
    prefixes: set[str] = set()
    for q in questions:
        if q["code"] == "member_mark_prefix_meaning":
            prefixes.update(s["name"] for s in q["subjects"])
        else:
            counts[q["code"]] += q["count"]
    if prefixes:
        counts["member_mark_prefix_meaning"] = len(prefixes)
    return dict(sorted(counts.items()))


# --- the whole work folder --------------------------------------------------------------------------------


def _check(doc: dict[str, Any]) -> dict[str, Any]:
    problems = validate("marks", doc)
    if problems:
        raise ReaderError(EXIT_INVALID, f"internal error: output is invalid: {_details(problems)}")
    return doc


def extract_marks(
    work_dir: Path | str, input_dir: Path | str | None = None, *, check_inputs: bool = False
) -> dict[str, Any]:
    """The marks document of a work folder (nothing written). Raises ReaderError."""
    inv = load_inventory(work_dir)
    in_dir = None if input_dir is None else Path(input_dir).resolve()
    warnings: list[str] = []
    stale = stale_warning(inv)
    if stale:
        warnings.append(stale)
    files: list[dict[str, Any]] = []
    skipped_sheets: list[dict[str, Any]] = []
    plan: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    unparsed: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for row in sorted(inv.doc["files"], key=lambda r: r["path"]):
        if row["format"] not in ("dwg", "dxf"):
            continue
        loaded = load_file(inv, row, check_inputs=check_inputs)
        warnings.extend(f"{loaded.rel}: {w}" for w in loaded.warnings)
        info: dict[str, Any] = {
            "path": loaded.rel,
            "status": "scanned",
            "reason": None,
            "text_entries": None,
            "line_grid": {"status": "unavailable", "reason": "not scanned", "skipped": {}},
            "plan_marks": 0,
            "tables": 0,
            "unparsed_tables": 0,
            "blocked_marks": 0,
        }
        files.append(info)
        if loaded.skip is not None or loaded.text_index is None:
            info.update(status="skipped", reason=loaded.skip)
            continue
        info["text_entries"] = len(loaded.text_index["entries"])
        out, grid_info = _scan_file(inv.work, loaded, in_dir, warnings, skipped_sheets)
        info.update(
            line_grid=grid_info,
            plan_marks=len(out.plan),
            tables=len(out.tables),
            unparsed_tables=len(out.unparsed),
            blocked_marks=len(out.blocked),
        )
        start = len(tables)
        for n, t in enumerate(out.tables, start=start + 1):
            t["id"] = f"S{n:03d}"
        for b in out.blocked:
            b["table"] = out.tables[b.pop("_t")]["id"]
        plan.extend(out.plan)
        tables.extend(out.tables)
        unparsed.extend(out.unparsed)
        blocked.extend(out.blocked)
    for n, p in enumerate(plan, start=1):
        p["id"] = f"P{n:06d}"
    matching = []
    for f in files:
        if f["status"] != "scanned":
            continue
        mine_p = [p for p in plan if p["file"] == f["path"]]
        mine_t = [t for t in tables if t["file"] == f["path"]]
        matching.append(_match_file(f["path"], mine_p, mine_t))
    for p in plan:
        p.pop("_structure", None)
    for t in tables:
        for row in t["rows"]:
            row.pop("_size_reason", None)
            for m in row["marks"]:
                m.pop("_structure", None)
    doc: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "marks",
        "project_id": inv.doc["project_id"],
        "inventory_sha256": inv.sha256,
        "files": files,
        "skipped_sheets": skipped_sheets,
        "plan_marks": plan,
        "tables": tables,
        "unparsed_tables": unparsed,
        "blocked_marks": blocked,
        "matching": matching,
        "question_counts": {},
        "summary": {},
        "warnings": warnings,
    }
    doc["question_counts"] = question_counts(marks_questions(doc))
    doc["summary"] = _summary(doc)
    return _check(doc)


def _summary(doc: dict[str, Any]) -> dict[str, Any]:
    by_file = []
    for f in doc["files"]:
        match = next((m for m in doc["matching"] if m["file"] == f["path"]), None)
        mine = [t for t in doc["tables"] if t["file"] == f["path"]]
        by_file.append(
            {
                "file": f["path"],
                "plan_marks": f["plan_marks"],
                "tables": f["tables"],
                "header_blocked_tables": sum(1 for t in mine if t["header_blocked"]),
                "rows": sum(len(t["rows"]) for t in mine),
                "unparsed_tables": f["unparsed_tables"],
                "blocked_marks": f["blocked_marks"],
                "matched": len(match["matched"]) if match else 0,
                "schedule_only": len(match["schedule_only"]) if match else 0,
                "plan_only": len(match["plan_only"]) if match else 0,
                "notation_variants": len(match["notation_variants"]) if match else 0,
                "size_conflicts": len(match["size_conflicts"]) if match else 0,
            }
        )
    totals = {k: sum(b[k] for b in by_file) for k in by_file[0] if k != "file"} if by_file else {}
    keys = (
        "plan_marks",
        "tables",
        "header_blocked_tables",
        "rows",
        "unparsed_tables",
        "blocked_marks",
        "matched",
        "schedule_only",
        "plan_only",
        "notation_variants",
        "size_conflicts",
    )
    out: dict[str, Any] = {k: totals.get(k, 0) for k in keys}
    out["files_scanned"] = sum(1 for f in doc["files"] if f["status"] == "scanned")
    out["files_skipped"] = sum(1 for f in doc["files"] if f["status"] == "skipped")
    out["by_file"] = by_file
    out["by_sheet"] = _by_sheet(doc)
    matches = [m for f in doc["matching"] for m in f["matched"]]
    out["size_comparisons"] = {
        "compared": sum(1 for m in matches if m["size_compared"]),
        "not_compared": sum(1 for m in matches if not m["size_compared"]),
        "by_reason": dict(
            sorted(Counter(m["size_not_compared_reason"] for m in matches if not m["size_compared"]).items())
        ),
    }
    return out


_SHEET_COUNTS = ("plan_marks", "tables", "header_blocked_tables", "rows", "unparsed_tables", "blocked_marks")


def _by_sheet(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Counts per (file, detector sheet); sheet None = on no sheet. Only sheets with something to count."""
    rows: dict[tuple[str, str | None], dict[str, Any]] = {}

    def row(file: str, sheet: str | None, number: dict[str, str] | None) -> dict[str, Any]:
        found = rows.get((file, sheet))
        if found is None:
            found = rows[(file, sheet)] = {"file": file, "sheet": sheet, "sheet_number": number}
            found.update(dict.fromkeys(_SHEET_COUNTS, 0))
        return found

    for p in doc["plan_marks"]:
        row(p["file"], p["sheet"], p["sheet_number"])["plan_marks"] += 1
    tables = {t["id"]: t for t in doc["tables"]}
    for t in doc["tables"]:
        r = row(t["file"], t["sheet"], t["sheet_number"])
        r["tables"] += 1
        r["header_blocked_tables"] += t["header_blocked"]
        r["rows"] += len(t["rows"])
    for u in doc["unparsed_tables"]:
        row(u["file"], u["sheet"], u["sheet_number"])["unparsed_tables"] += 1
    for b in doc["blocked_marks"]:
        t = tables[b["table"]]
        row(t["file"], t["sheet"], t["sheet_number"])["blocked_marks"] += 1
    return [rows[k] for k in sorted(rows, key=lambda k: (k[0], k[1] is None, k[1] or ""))]


@dataclass
class MarksResult:
    exit_code: int
    summary: dict[str, Any]


def run_marks(
    work_dir: Path | str, input_dir: Path | str | None = None, *, check_inputs: bool = False
) -> MarksResult:
    """Marks, schedule tables, matching and their numbered questions of an intake work folder. Writes
    `marks.json`, `marks-questions.json` and updates the registry. Raises ReaderError.

    `input_dir`: when given, every DXF/DWG of the inventory must still be there with the same sha256; it is
    also where native DXF files are opened for their lines."""
    inv = load_inventory(work_dir)
    try:
        ledger = load_ledger(inv.work, inv.doc["project_id"], create=False)
    except QuestionsError as exc:
        raise ReaderError(exc.exit_code, str(exc)) from exc
    if input_dir is not None:
        _check_input_dir(inv, Path(input_dir).resolve())
    doc = extract_marks(inv.work, input_dir, check_inputs=check_inputs)
    hashes = {r["path"]: r["sha256"] for r in inv.doc["files"]}
    try:
        questions = ledger.sync("marks", marks_questions(doc), hashes)
    except QuestionsError as exc:
        raise ReaderError(exc.exit_code, str(exc)) from exc
    qdoc = questions_document(inv.doc["project_id"], questions)
    problems = validate("intake", qdoc)
    if problems:
        raise ReaderError(
            EXIT_INVALID, f"marks-questions.json is invalid, nothing written: {_details(problems)}"
        )
    try:
        texts = {"marks.json": dump_json(doc), "marks-questions.json": dump_json(qdoc)}
        for text in texts.values():
            text.encode("utf-8")
    except (ValueError, UnicodeEncodeError) as exc:
        raise ReaderError(EXIT_INVALID, f"marks output cannot be written as strict JSON: {exc}") from exc
    try:
        ledger.write()  # the registry is written before any document that uses its ids
        for name, text in texts.items():
            write_text_atomic(inv.work / name, text)
    except OSError as exc:
        raise ReaderError(3, f"cannot write into {inv.work}: {exc}") from exc  # 3: environment
    s = doc["summary"]
    summary = {
        "project_id": doc["project_id"],
        **{k: v for k, v in s.items() if k not in ("by_file", "by_sheet")},
        **qdoc["summary"],
        "stale_answers": ledger.stale_answers(),
        "warnings": doc["warnings"],
        "outputs": {
            "marks": str(inv.work / "marks.json"),
            "questions": str(inv.work / "marks-questions.json"),
            "registry": str(inv.work / "question-registry.json"),
        },
    }
    return MarksResult(0, summary)


# --- command line ----------------------------------------------------------------------------------------


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "work_dir", help="the --out folder of `harness intake` (after `harness read-structure`)"
    )
    parser.add_argument(
        "--input-dir",
        help="the intake input folder: its DXF/DWG files must still match inventory.json (sha256); native "
        "DXF files are opened from it for their table lines",
    )


def run(args: argparse.Namespace) -> int:
    try:
        result = run_marks(Path(args.work_dir), Path(args.input_dir) if args.input_dir else None)
    except ReaderError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    print(json.dumps(result.summary, ensure_ascii=False, indent=2))
    return result.exit_code
