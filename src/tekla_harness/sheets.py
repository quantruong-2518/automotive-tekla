"""sheets: split one DXF into sheets, assign every indexed text to a sheet, read title-block candidates.

`extract_sheets(dxf_path, text_index)` returns a dict that validates against `schemas/sheets.schema.json`.
The text index is the output of `extract_text.extract_text` for the SAME file (checked by sha256).

Why: Vietnamese sets often place many sheets side by side in model space, each inside a title-block
frame, instead of one sheet per layout. Every later value needs a real sheet in its provenance.

Algorithm (deterministic, every threshold is a named constant below):

1. Frames. In model space and in every layout, collect axis-aligned closed rectangles (LWPOLYLINE,
   2D POLYLINE), at top level and inside INSERTs (recursively, world/paper coordinates, so a frame
   block whose geometry sits far from its base point is still placed right). A rectangle is a frame
   when its long/short side ratio is within FRAME_RATIO (paper sheets: A-series is 1.414), it holds
   >= FRAME_MIN_TEXTS text entries, and its short side is >= FRAME_MIN_SIDE_IN_TEXT_HEIGHTS x the median
   height of the text inside it (a detail box is small compared with its text, a sheet is not); without
   title-block evidence inside (a title-field label or field ATTRIB) it must reach
   FRAME_MIN_SIDE_NO_TITLE heights or have the size of an accepted frame (a schedule table is not a
   sheet). Identical rectangles are deduplicated; a frame inside a larger frame is an inner border and
   is merged into it. A larger one holding two or more disjoint frames is a container around sheets and
   is dropped only when those inner frames are sheets themselves (own title-block evidence, or the size
   of a frame found outside it); otherwise it stays the sheet and a blocking sheet_frame_ambiguous
   question is asked (two boxed views on one sheet). Partial overlaps keep the larger frame and raise a
   question.
2. Layouts. A paper-space layout without frames is one sheet when it holds anything other than
   viewports, or when one of its viewports shows indexed model text. Viewport model windows are
   target + view centre, view height x (width / height); only plan views without twist are used.
3. Assignment. A text entry (and, through `SheetLocator`, any point) belongs to the frame that holds
   it in its own space; a model point outside model frames belongs to the single layout sheet whose
   viewport windows show it; several -> ambiguous, none -> unassigned.
4. Title block. Candidates come only from evidence: an ATTRIB whose tag names a field
   (`attrib_tag`, medium at most) and that sits on the title block (the frame's own INSERT, an INSERT
   carrying ATTRIBs of two or more fields, or within TITLE_REGION_MARGIN text heights of a title-field
   label: a section callout's SHEET_NO is not), a text 'label: value' (`inline_label`, medium at most),
   a value text right of or below a label text (`adjacent_label`, low), or, for the sheet number only
   and only when nothing else was found, a sheet-code-looking text in the title-block corner
   (`pattern`, low; TCVN 5571 places the title block at the lower right): the last CORNER_U of the
   frame along the text's reading direction and the lowest CORNER_V across it. A portrait frame is
   also read at 90 and 270 degrees (a landscape sheet drawn turned). A member mark is never a number
   (`_pick_corner_numbers`: the same code twice on its sheet, a mark family on its sheet, or the code
   twice outside every title block of the file; a text equal to another sheet's corner code is a
   reference to that sheet, not mark evidence); among the rest a position repeated in other sheets'
   corners wins, then the tallest. A code whose position repeats in no other sheet's corner is never
   taken (nothing backs it; a one-sheet file has nothing to back it with). Ties stay a conflict, and
   every corner code not taken is a warning.
   Constant text of the frame's own block is template text and never a value. A text that does not print
   (`printed: false`, tool wave 4) is no label, no value, no title evidence and no corner code: it keeps its
   sheet in `text_ids`, and one warning counts such texts. A field value is chosen
   only when ALL its candidates agree; any disagreement is a title_field_conflict question (blocking
   for sheet_number and revision).
5. Number gaps. One non-blocking sheet_number_gap question per file lists the numbers that a letter
   series skips and no sheet of any series carries, with the sheets on each side
   (`_number_gap_question`). More than SHEET_GAP_MAX_RUN missing numbers in a row is a numbering jump
   (S-101 to S-201), given as a warning and not asked.

Not done here (documented gaps): frames drawn as four LINEs, rotated frame rectangles, clipped
viewports (the rectangle is used), and the drawing list / sheet index (`drawing_list.status` is
'not_searched'; nothing is asserted about it).
"""

from __future__ import annotations

import bisect
import math
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ezdxf import bbox as ezbbox
from ezdxf import units as dxf_units
from ezdxf.document import Drawing
from ezdxf.filemanagement import readfile

from tekla_harness.detect import sha256_file
from tekla_harness.questions import SHEET_GAP_CODE
from tekla_harness.visibility import is_printed

SCHEMA_VERSION = "0.1"
SHEET_UNKNOWN = "unknown"  # provenance.sheet when a value lies on no detected sheet
MAX_WALK_DEPTH = 8  # INSERT nesting levels expanded when looking for geometry
FRAME_RATIO = (1.2, 1.8)  # long side / short side of a sheet frame
FRAME_MIN_TEXTS = 5
FRAME_MIN_SIDE_IN_TEXT_HEIGHTS = 40.0
# Heuristic: a frame-shaped rectangle with no title-block evidence inside (no title-field label text, no
# field ATTRIB) is a sheet only when its short side is at least this many median text heights, or when
# it has the size of an accepted frame. A schedule table is small compared with its text (about 40
# heights); an A4 sheet (210 mm short side) with 3.5 mm text is 60, with 3 mm text 70 (a corpus sheet);
# an A1 sheet with 3.5 mm text about 170.
FRAME_MIN_SIDE_NO_TITLE = 60.0
TITLE_REGION_MARGIN = 10.0  # text heights around the title-block anchors (labels, title-block attribs)
SAME_SIZE_TOL = 0.005  # relative: two frames are 'the same size'
CONTAIN_TOL = 0.01  # relative to the larger frame's short side
MAX_LISTED = 50  # ids listed in one question
# Title-block corner for the sheet-code pattern (tool wave 3, EVAL-3 a1): the last quarter of the frame along
# the reading direction and the lowest fifth across it. Corpus numbers sit at 0.92-0.97 along and 0.01-0.06
# up (267, 270, 285, 290, 461); the tie-beam mark taken on 286 sat at 0.59 / 0.44.
CORNER_U = 0.25
CORNER_V = 0.20
CORNER_POS_TOL = 0.03  # frame shares: two corner codes at 'the same position' on different sheets
SHEET_GAP_MAX_RUN = 9  # missing numbers in a row asked as a gap; a longer run is a numbering jump

_CONF_ORDER = {"low": 0, "medium": 1, "high": 2}
_BUILDING_UNITS = {"mm", "cm", "m", "in", "ft"}


# --- small shared helpers (also used by grids.py and levels.py) ---------------------------


def min_conf(*values: str | None) -> str:
    """Lowest of the given confidences (None is ignored; no value gives 'high')."""
    present = [v for v in values if v is not None]
    return min(present, key=_CONF_ORDER.__getitem__) if present else "high"


def max_conf(*values: str) -> str:
    return max(values, key=_CONF_ORDER.__getitem__)


def question(
    code: str, blocking: bool, message: str, where: str, found: str, sheet: str | None = None
) -> dict:
    q: dict[str, Any] = {
        "code": code,
        "blocking": blocking,
        "message": message,
        "where": where,
        "found": found,
    }
    if sheet is not None:
        q["sheet"] = sheet
    return q


def listed(items: Iterable[str], limit: int = MAX_LISTED) -> str:
    items = list(items)
    head = ", ".join(items[:limit])
    return head + (f" (+{len(items) - limit} more)" if len(items) > limit else "")


def fold(text: str) -> str:
    """Casefold, strip Vietnamese diacritics (đ/Đ and the look-alike Eth become d), collapse spaces."""
    text = text.replace("đ", "d").replace("Đ", "d").replace("ð", "d").replace("Ð", "d")
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped.casefold()).strip()


def rnum(value: float) -> float:
    """Round a coordinate for output (1e-6 relative noise is not information). Never NaN/inf."""
    if not math.isfinite(value):
        raise ValueError(f"non-finite number {value!r}")
    return float(round(value, 6)) + 0.0  # + 0.0 turns -0.0 into 0.0


def rbox(box: tuple[float, float, float, float]) -> list[float]:
    return [rnum(v) for v in box]


def declared_units(doc: Drawing) -> dict[str, Any]:
    raw = doc.header.get("$INSUNITS")
    code = raw if isinstance(raw, int) and not isinstance(raw, bool) and 0 <= raw <= 20 else None
    name = "unknown"
    if code:
        try:
            decoded = dxf_units.decode(code)
        except IndexError:
            decoded = None
        if decoded in _BUILDING_UNITS:
            name = str(decoded)
    return {"insunits": code, "name": name}


def open_checked(dxf_path: str | Path, text_index: dict[str, Any], doc: Drawing | None = None) -> Drawing:
    """The DXF document, after checking that the text index was built from this very file.

    Raises ValueError when the index is unreadable or belongs to another file (handles and ids are only
    valid for one conversion), OSError when the DXF cannot be read.
    """
    if text_index.get("status") == "unreadable" or "entries" not in text_index:
        raise ValueError("text index is unreadable: nothing to segment")
    digest = sha256_file(Path(dxf_path))
    if digest != text_index["file"]["sha256"]:
        raise ValueError(
            f"text index sha256 {text_index['file']['sha256']} does not match the DXF ({digest}): "
            "build the index from this file"
        )
    return doc if doc is not None else readfile(str(dxf_path))


def text_box(entry: dict[str, Any]) -> tuple[float, float, float, float] | None:
    """Approximate extents of an indexed text from its anchor, alignment, height and rotation.

    Width is estimated as 0.7 x height per character (no font metrics). Used only for 'near' tests.
    """
    pos = entry["position"]
    x, y = pos["x"], pos["y"]
    if x is None or y is None:
        return None
    h = entry.get("height") or 0.0
    if h <= 0 or pos["basis"] in ("text_midpoint", "context_block_insert", "context_mtext_insert"):
        return (x, y, x, y)
    lines = entry["display_text"].split("\n") or [""]
    w = max(len(line) for line in lines) * 0.7 * h
    th = h * (1.0 + 1.5 * (len(lines) - 1))
    align = (entry.get("alignment") or "LEFT").upper()
    if align in ("LEFT", "ALIGNED", "FIT"):
        hx, vert = 0.0, "BASE"
    elif align == "CENTER":
        hx, vert = 0.5, "BASE"
    elif align == "RIGHT":
        hx, vert = 1.0, "BASE"
    elif align == "MIDDLE":
        hx, vert = 0.5, "MIDDLE"
    else:
        vert, _, horiz = align.partition("_")
        hx = {"LEFT": 0.0, "CENTER": 0.5, "RIGHT": 1.0}.get(horiz, 0.0)
    x0 = -hx * w
    y0 = {"TOP": -th, "MIDDLE": -th / 2}.get(vert, 0.0)
    corners = [(x0, y0), (x0 + w, y0), (x0, y0 + th), (x0 + w, y0 + th)]
    rot = math.radians(entry.get("rotation") or 0.0)
    c, s = math.cos(rot), math.sin(rot)
    pts = [(x + cx * c - cy * s, y + cx * s + cy * c) for cx, cy in corners]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def box_center(box: tuple[float, float, float, float]) -> tuple[float, float]:
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def text_center(entry: dict[str, Any]) -> tuple[float, float] | None:
    box = text_box(entry)
    return box_center(box) if box else None


def inside(box: tuple[float, float, float, float], x: float, y: float, tol: float = 0.0) -> bool:
    return box[0] - tol <= x <= box[2] + tol and box[1] - tol <= y <= box[3] + tol


# --- geometry walk ------------------------------------------------------------------------


@dataclass(frozen=True)
class Placed:
    """An entity in its space's coordinates (a virtual copy when it comes from a block)."""

    entity: Any
    space: str
    block_path: tuple[str, ...]  # blocks entered from the top-level INSERT down to the entity's block
    top_handle: str | None  # handle of the top-level entity it came through (itself at top level)
    owner: int  # serial of the INSERT occurrence that holds it (0 at top level)
    serial: int  # this occurrence's serial (an INSERT's children carry it as owner)


@dataclass
class Walker:
    """Depth-first walk of a layout, expanding INSERTs with `virtual_entities()` (cycle and depth guarded).

    Everything that could not be expanded is counted in `skipped` (reason -> count); nothing is dropped
    silently. `types` limits what is yielded (INSERTs are always expanded).
    """

    doc: Drawing
    handles_ok: bool
    max_depth: int = MAX_WALK_DEPTH
    skipped: Counter[str] = field(default_factory=Counter)
    _serial: int = 0

    def handle(self, entity: Any) -> str | None:
        h = entity.dxf.get("handle")
        return str(h) if self.handles_ok and h else None

    def walk(self, layout: Any, space: str, types: frozenset[str] | None = None) -> Iterator[Placed]:
        for entity in layout:
            self._serial += 1
            yield from self._visit(entity, space, (), self.handle(entity), 0, self._serial, types)

    def _visit(
        self,
        entity: Any,
        space: str,
        path: tuple[str, ...],
        top: str | None,
        owner: int,
        serial: int,
        types: frozenset[str] | None,
    ) -> Iterator[Placed]:
        kind = entity.dxftype()
        if types is None or kind in types:
            yield Placed(entity, space, path, top, owner, serial)
        if kind != "INSERT":
            return
        name = str(entity.dxf.get("name", ""))
        block = self.doc.blocks.get(name)
        if block is None:
            self.skipped["missing_block"] += 1
            return
        if block.block is not None and (block.block.is_xref or block.block.is_xref_overlay):
            self.skipped["xref"] += 1
            return
        if name in path:
            self.skipped["cycle"] += 1
            return
        if len(path) >= self.max_depth:
            self.skipped["depth_limit"] += 1
            return
        try:
            inserts = list(entity.multi_insert()) if entity.mcount > 1 else [entity]
            children: list[Any] = []
            for ins in inserts:
                children.extend(
                    ins.virtual_entities(
                        skipped_entity_callback=lambda e, reason: self.skipped.update(
                            [f"transform:{e.dxftype()}"]
                        )
                    )
                )
        except Exception as exc:
            self.skipped[f"expand_error:{type(exc).__name__}"] += 1
            return
        for child in children:
            self._serial += 1
            yield from self._visit(child, space, (*path, name), top, serial, self._serial, types)


def layout_spaces(doc: Drawing) -> list[tuple[str, Any, bool]]:
    """(space name as in the text index, layout, is_model) in tab order."""
    out = []
    for name in doc.layout_names_in_taborder():
        layout = doc.layouts.get(name)
        is_model = bool(layout.is_modelspace)
        out.append(("model" if is_model else name, layout, is_model))
    return out


# --- rectangles and frames ------------------------------------------------------------------


@dataclass
class _Rect:
    box: tuple[float, float, float, float]
    space: str
    layer: str
    handle: str | None
    block_path: tuple[str, ...]
    top_handle: str | None
    owner: int
    texts: list[str] = field(default_factory=list)
    inner: int = 0

    @property
    def w(self) -> float:
        return self.box[2] - self.box[0]

    @property
    def h(self) -> float:
        return self.box[3] - self.box[1]

    @property
    def area(self) -> float:
        return self.w * self.h


def _axis_aligned_rect(points: list[tuple[float, float]]) -> tuple[float, float, float, float] | None:
    pts = list(points)
    if len(pts) >= 2 and math.isclose(pts[0][0], pts[-1][0]) and math.isclose(pts[0][1], pts[-1][1]):
        pts = pts[:-1]
    if len(pts) != 4:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    size = max(x1 - x0, y1 - y0)
    if size <= 0 or min(x1 - x0, y1 - y0) <= 0:
        return None
    tol = 1e-6 * size
    for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1], strict=True):
        if not (abs(ax - bx) <= tol or abs(ay - by) <= tol):
            return None
    for px, py in pts:
        if not (
            (abs(px - x0) <= tol or abs(px - x1) <= tol) and (abs(py - y0) <= tol or abs(py - y1) <= tol)
        ):
            return None
    return (x0, y0, x1, y1)


def rect_of(entity: Any) -> tuple[float, float, float, float] | None:
    """Box of a closed, straight-edged, axis-aligned 4-vertex LWPOLYLINE / 2D POLYLINE, else None."""
    kind = entity.dxftype()
    if kind == "LWPOLYLINE":
        if any(abs(b[0]) > 1e-12 for b in entity.get_points("b")):
            return None
        pts = [(v.x, v.y) for v in entity.vertices_in_wcs()]
        if not entity.closed and len(pts) != 5:
            return None
        return _axis_aligned_rect(pts)
    if kind == "POLYLINE":
        if not entity.is_2d_polyline:
            return None
        if any(abs(v.dxf.get("bulge", 0.0)) > 1e-12 for v in entity.vertices):
            return None
        pts = [(v.x, v.y) for v in entity.points_in_wcs()]
        if not entity.is_closed and len(pts) != 5:
            return None
        return _axis_aligned_rect(pts)
    return None


class _TextGrid:
    """Text centres of one space sorted by x, for 'which texts are inside this box' queries."""

    def __init__(self, entries: list[dict[str, Any]]):
        pts = []
        for e in entries:
            c = text_center(e)
            if c is not None:
                pts.append((c[0], c[1], e["id"], e.get("height") or 0.0))
        pts.sort()
        self.pts = pts
        self.xs = [p[0] for p in pts]

    def within(self, box: tuple[float, float, float, float]) -> list[tuple[float, float, str, float]]:
        lo = bisect.bisect_left(self.xs, box[0])
        hi = bisect.bisect_right(self.xs, box[2])
        return [p for p in self.pts[lo:hi] if box[1] <= p[1] <= box[3]]


def _contains(outer: tuple[float, ...], inner: tuple[float, ...], tol: float) -> bool:
    return (
        outer[0] - tol <= inner[0]
        and outer[1] - tol <= inner[1]
        and inner[2] <= outer[2] + tol
        and inner[3] <= outer[3] + tol
    )


def _overlap_area(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def _size_key(r: _Rect) -> tuple[float, float]:
    return (r.w, r.h)


def _same_size(a: _Rect, b: _Rect) -> bool:
    return abs(a.w - b.w) <= SAME_SIZE_TOL * max(a.w, b.w) and abs(a.h - b.h) <= SAME_SIZE_TOL * max(a.h, b.h)


@dataclass
class _SpaceFrames:
    frames: list[_Rect]
    rejected_groups: list[tuple[float, float, int]]  # (w, h, count) of same-size text-holding rectangles
    overlaps: list[tuple[_Rect, _Rect]]
    containers: list[_Rect]
    ambiguous: list[tuple[_Rect, int]]  # (kept frame, disjoint frame-shaped rectangles inside it)


def _find_frames(
    rects: list[_Rect], grid: _TextGrid, title_evidence: Callable[[list[str]], bool] = lambda ids: True
) -> _SpaceFrames:
    """Frames among the rectangles of one space. `title_evidence(text ids)`: does a title-block field
    (label text or field ATTRIB) lie among these texts."""
    # dedupe identical boxes (same rectangle drawn twice, or a block copy at the same place)
    unique: dict[tuple[float, ...], _Rect] = {}
    for r in rects:
        size = max(r.w, r.h)
        key = tuple(round(v / (size * 1e-4)) for v in r.box)
        unique.setdefault(key, r)
    candidates: list[_Rect] = []
    pending: list[_Rect] = []  # frame-shaped but small for their text and untitled
    textful_rejects: list[_Rect] = []
    for r in unique.values():
        inner_texts = grid.within(r.box)
        if len(inner_texts) < FRAME_MIN_TEXTS:
            continue
        heights = [p[3] for p in inner_texts if p[3] > 0]
        median_h = statistics.median(heights) if heights else 0.0
        ratio = max(r.w, r.h) / min(r.w, r.h)
        big_enough = median_h <= 0 or min(r.w, r.h) >= FRAME_MIN_SIDE_IN_TEXT_HEIGHTS * median_h
        ids = [p[2] for p in inner_texts]
        sheet_sized = median_h <= 0 or min(r.w, r.h) >= FRAME_MIN_SIDE_NO_TITLE * median_h
        if FRAME_RATIO[0] <= ratio <= FRAME_RATIO[1] and big_enough:
            r.texts = ids
            (candidates if sheet_sized or title_evidence(ids) else pending).append(r)
        else:
            textful_rejects.append(r)
    # a small untitled rectangle is still a sheet when it has the size of an accepted one (a set of
    # same-size sheets); two same-size schedule tables confirm nothing
    for r in pending:
        (candidates if any(_same_size(r, c) for c in candidates) else textful_rejects).append(r)

    candidates.sort(key=lambda r: (-r.area, r.box))
    # containers: a candidate holding two or more disjoint candidates of >= 10 % of its area that are
    # sheets themselves: each has its own title-block evidence, or has the size of a frame found outside
    # this rectangle. Otherwise (two boxed views on one sheet) the outer rectangle stays the sheet and a
    # blocking sheet_frame_ambiguous question is asked.
    containers: list[_Rect] = []
    ambiguous: list[tuple[_Rect, int]] = []
    for big in candidates:
        tol = CONTAIN_TOL * min(big.w, big.h)
        inner = [
            r
            for r in candidates
            if r is not big and r.area >= 0.1 * big.area and _contains(big.box, r.box, tol)
        ]
        disjoint = [r for r in inner if not any(_overlap_area(r.box, o.box) > 0 for o in inner if o is not r)]
        if len(disjoint) < 2:
            continue
        outside = [o for o in candidates if o is not big and not _contains(big.box, o.box, tol)]
        sheets_inside = [
            r for r in disjoint if title_evidence(r.texts) or any(_same_size(r, o) for o in outside)
        ]
        if len(sheets_inside) >= 2:
            containers.append(big)
        else:
            ambiguous.append((big, len(disjoint)))
    kept: list[_Rect] = []
    overlaps: list[tuple[_Rect, _Rect]] = []
    for r in candidates:
        if r in containers:
            continue
        holder = next((k for k in kept if _contains(k.box, r.box, CONTAIN_TOL * min(k.w, k.h))), None)
        if holder is not None:
            holder.inner += 1
            continue
        clash = next((k for k in kept if _overlap_area(k.box, r.box) > 0.01 * min(k.area, r.area)), None)
        if clash is not None:
            overlaps.append((clash, r))
            continue
        kept.append(r)

    groups: list[list[_Rect]] = []
    for r in sorted(textful_rejects, key=lambda r: (_size_key(r), r.box)):
        g = next((g for g in groups if _same_size(g[0], r)), None)
        if g is None:
            groups.append([r])
        else:
            g.append(r)
    rejected = [(g[0].w, g[0].h, len(g)) for g in groups if len(g) >= 2]
    return _SpaceFrames(kept, rejected, overlaps, containers, [(r, n) for r, n in ambiguous if r in kept])


def _row_order(frames: list[_Rect]) -> list[_Rect]:
    """Rows from the top (frames whose vertical extents overlap by half are one row), left to right."""
    rows: list[list[_Rect]] = []
    for r in sorted(frames, key=lambda r: (-r.box[3], r.box[0])):
        row = next(
            (row for row in rows if _vertical_overlap(row[0], r) >= 0.5 * min(row[0].h, r.h)),
            None,
        )
        if row is None:
            rows.append([r])
        else:
            row.append(r)
    return [r for row in rows for r in sorted(row, key=lambda r: (r.box[0], -r.box[3]))]


def _vertical_overlap(a: _Rect, b: _Rect) -> float:
    return min(a.box[3], b.box[3]) - max(a.box[1], b.box[1])


# --- viewports -------------------------------------------------------------------------------


def _viewport_window(vp: Any) -> tuple[tuple[float, float, float, float] | None, str | None]:
    """(model-space box shown by a paper-space viewport, reason when it cannot be used)."""
    direction = vp.dxf.get("view_direction_vector")
    if direction is not None:
        length = math.sqrt(direction[0] ** 2 + direction[1] ** 2 + direction[2] ** 2)
        if length <= 0 or abs(direction[0]) > 1e-9 * length or abs(direction[1]) > 1e-9 * length:
            return None, "not a plan view"
        if direction[2] < 0:
            return None, "view from below"
    if abs(float(vp.dxf.get("view_twist_angle", 0.0) or 0.0)) > 1e-9:
        return None, "twisted view"
    width, height = float(vp.dxf.get("width", 0.0)), float(vp.dxf.get("height", 0.0))
    view_h = float(vp.dxf.get("view_height", 0.0))
    if width <= 0 or height <= 0 or view_h <= 0:
        return None, "zero size"
    target = vp.dxf.get("view_target_point", (0.0, 0.0, 0.0))
    centre = vp.dxf.get("view_center_point", (0.0, 0.0))
    cx, cy = target[0] + centre[0], target[1] + centre[1]
    view_w = view_h * width / height
    box = (cx - view_w / 2, cy - view_h / 2, cx + view_w / 2, cy + view_h / 2)
    if not all(math.isfinite(v) for v in box):
        return None, "non-finite"
    return box, None


# --- locating -------------------------------------------------------------------------------


class SheetLocator:
    """Answers 'which sheet is this point / text on' from an `extract_sheets` result."""

    def __init__(self, sheets_result: dict[str, Any]):
        self.by_text: dict[str, str] = {}
        self.frames: dict[str, list[tuple[tuple[float, ...], str]]] = defaultdict(list)
        self.whole: dict[str, str] = {}
        self.windows: list[tuple[tuple[float, ...], str]] = []
        for s in sheets_result["sheets"]:
            for tid in s["text_ids"]:
                self.by_text[tid] = s["sheet_id"]
            if s["detection"]["method"] == "layout":
                self.whole[s["space"]] = s["sheet_id"]
            else:
                self.frames[s["space"]].append((tuple(s["bbox"]), s["sheet_id"]))
            for w in s["model_windows"]:
                self.windows.append((tuple(w["bbox"]), s["sheet_id"]))

    def locate(self, space: str, x: float | None, y: float | None) -> str:
        """Detector sheet id, or SHEET_UNKNOWN (outside every sheet, or shown on several)."""
        if x is None or y is None:
            return SHEET_UNKNOWN
        sheet = self._locate(space, x, y)
        return sheet if sheet and sheet != "ambiguous" else SHEET_UNKNOWN

    def _locate(self, space: str, x: float, y: float) -> str | None:
        for box, sid in self.frames.get(space, ()):
            if inside(box, x, y):  # type: ignore[arg-type]
                return sid
        if space in self.whole:
            return self.whole[space]
        if space == "model":
            hits = sorted({sid for box, sid in self.windows if inside(box, x, y)})  # type: ignore[arg-type]
            if len(hits) == 1:
                return hits[0]
            if len(hits) > 1:
                return "ambiguous"
        return None

    def text_sheet(self, text_id: str) -> str:
        return self.by_text.get(text_id, SHEET_UNKNOWN)


# --- title block ---------------------------------------------------------------------------

# Field labels, folded (no diacritics, casefold). English drawing practice and the Vietnamese field
# names of the TCVN 5571 title block as summarised in docs/research/vn-structural-drawing-conventions.md
# (field list unverified: a label only says which cell this is, it never proves the value).
FIELD_LABELS: dict[str, tuple[str, ...]] = {
    "sheet_number": (
        "sheet no",
        "sheet no.",
        "sheet number",
        "drawing no",
        "drawing no.",
        "drawing number",
        "dwg no",
        "dwg. no",
        "dwg no.",
        "dwg. no.",
        "ky hieu ban ve",
        "ban ve so",
        "so ban ve",
        "so hieu ban ve",
    ),
    "revision": ("rev", "rev.", "revision", "lan sua", "lan sua doi", "sua doi"),
    "title": ("title", "drawing title", "dwg title", "dwg. title", "ten ban ve"),
    "scale": ("scale", "ty le", "ti le"),
    "date": ("date", "ngay", "ngay thang"),
    "project": ("project", "cong trinh", "du an"),
}
# ATTRIB tags, folded and stripped of everything but letters and digits.
FIELD_TAGS: dict[str, tuple[str, ...]] = {
    "sheet_number": (
        "sheetno",
        "sheetnumber",
        "sheetnum",
        "drawingno",
        "drawingnumber",
        "dwgno",
        "dwgnumber",
        "sobanve",
        "kyhieubanve",
        "banveso",
        "sohieubanve",
    ),
    "revision": ("rev", "revision", "revno", "lansua", "suadoi"),
    "title": ("title", "drawingtitle", "dwgtitle", "tenbanve"),
    "scale": ("scale", "tyle", "tile"),
    "date": ("date", "ngay"),
    "project": ("project", "projectname", "congtrinh", "duan"),
}
_LABEL_LOOKUP = {label: f for f, labels in FIELD_LABELS.items() for label in labels}
_TAG_LOOKUP = {tag: f for f, tags in FIELD_TAGS.items() for tag in tags}
# Sheet codes such as KC-01, KT 1/18 (TCVN 5671/5672 examples), S-101; matched case-insensitively because
# legacy capital fonts make the stored case unreliable.
_SHEET_CODE_RE = re.compile(
    r"^[A-ZĐ]{1,4}\s?[-:.]\s?\d{1,3}[A-Z]?$|^[A-ZĐ]{1,4}\s?\d{1,3}\s?/\s?\d{1,3}$", re.IGNORECASE
)
_INLINE_RE = re.compile(
    r"^(?P<label>[^:\uff1a]{1,40})[:\uff1a]\s*(?P<value>\S.*)$"
)  # \uff1a: fullwidth colon


_COLONS = " :\uff1a"


def _label_field(text: str) -> str | None:
    """Field named by a label text; bilingual labels 'vi - en' / 'vi / en' are split."""
    folded = fold(text).strip(_COLONS)
    if folded in _LABEL_LOOKUP:
        return _LABEL_LOOKUP[folded]
    for part in re.split(r"\s+[-/]\s+", folded):
        part = part.strip(_COLONS)
        if part in _LABEL_LOOKUP:
            return _LABEL_LOOKUP[part]
    return None


def _tag_field(tag: str) -> str | None:
    return _TAG_LOOKUP.get(re.sub(r"[^0-9a-z]", "", fold(tag)))


def _anchor_field(entry: dict[str, Any]) -> str | None:
    """Title field this text names: a field ATTRIB tag, a label text, or the label of 'label: value'."""
    if entry["entity_type"] == "ATTRIB" and entry["tag"]:
        fld = _tag_field(entry["tag"])
        if fld:
            return fld
    text = entry["display_text"].strip()
    fld = _label_field(text)
    if fld:
        return fld
    m = _INLINE_RE.match(text)
    if m and "\n" not in text:
        return _label_field(m.group("label"))
    return None


def _entry_conf(entry: dict[str, Any], cap: str) -> str:
    conf = min_conf(entry["confidence"], cap, "medium")
    flags = set(entry["flags"])
    if flags & {"layer_off", "layer_frozen", "attribute_invisible"}:
        conf = "low"
    return conf


@dataclass
class _SheetCtx:
    sheet_id: str
    box: tuple[float, float, float, float]
    template: Callable[[dict[str, Any]], bool]
    own_insert: Callable[[dict[str, Any]], bool] = lambda e: False  # ATTRIB of the frame's own INSERT


def _insert_key(entry: dict[str, Any]) -> tuple[Any, ...]:
    """The INSERT an ATTRIB belongs to (by handle; by block name and path when handles are absent)."""
    return (
        entry["insert_handle"],
        entry["block_name"],
        tuple(entry["block_path"]),
        tuple(entry["insert_handles"]),
    )


def _title_region(entries: list[dict[str, Any]]) -> tuple[set[tuple[Any, ...]], list[tuple[float, ...]]]:
    """(title-block INSERTs, title-block region boxes) of one sheet.

    A title-block INSERT carries ATTRIBs of at least two different title fields (a section callout
    carries a sheet number only). The region is every title-field label text and every ATTRIB of a
    title-block INSERT, each grown by TITLE_REGION_MARGIN of its text height.
    """
    fields_by_insert: dict[tuple[Any, ...], set[str]] = defaultdict(set)
    for e in entries:
        if e["entity_type"] == "ATTRIB" and e["tag"] and _tag_field(e["tag"]):
            fields_by_insert[_insert_key(e)].add(_tag_field(e["tag"]) or "")
    title_inserts = {k for k, f in fields_by_insert.items() if len(f) >= 2}
    boxes: list[tuple[float, ...]] = []
    for e in entries:
        is_anchor = (e["entity_type"] == "ATTRIB" and _insert_key(e) in title_inserts) or (
            e["entity_type"] != "ATTRIB" and _anchor_field(e)
        )
        box = text_box(e) if is_anchor and e["position"]["x"] is not None else None
        if box is None:
            continue
        m = TITLE_REGION_MARGIN * (e.get("height") or (box[3] - box[1]) or 0.0)
        boxes.append((box[0] - m, box[1] - m, box[2] + m, box[3] + m))
    return title_inserts, boxes


def _horizontal(entry: dict[str, Any]) -> bool:
    rot = (entry.get("rotation") or 0.0) % 360.0
    return min(rot, 360.0 - rot) < 1.0


def _candidate(
    fld: str,
    value: str,
    kind: str,
    key: str,
    ventry: dict[str, Any],
    lentry: dict | None,
    conf: str,
    sheet_id: str,
    file_path: str,
) -> dict[str, Any] | None:
    """One title-block candidate (schema `candidates[]`), or None when the value is blank."""
    value = value.strip().strip(_COLONS).strip()
    if not value:
        return None
    vbox = text_box(ventry) or (ventry["position"]["x"], ventry["position"]["y"]) * 2
    return {
        "field": fld,
        "value": value,
        "evidence": {
            "kind": kind,
            "key": key,
            "value_text_id": ventry["id"],
            "label_text_id": lentry["id"] if lentry else None,
            "position": [rnum(ventry["position"]["x"]), rnum(ventry["position"]["y"])],
        },
        "confidence": conf,
        "provenance": {
            "file": file_path,
            "sheet": sheet_id,
            "method": "dxf_entity",
            "region": {"bbox": rbox(vbox)},
        },
    }


def _title_candidates(
    entries: list[dict[str, Any]], ctx: _SheetCtx, file_path: str, cap: str
) -> list[dict[str, Any]]:
    """Candidates from field ATTRIBs and labels; the sheet-code pattern is `_pick_corner_numbers`."""
    out: list[dict[str, Any]] = []

    def add(
        fld: str, value: str, kind: str, key: str, ventry: dict[str, Any], lentry: dict | None, conf: str
    ):
        cand = _candidate(fld, value, kind, key, ventry, lentry, conf, ctx.sheet_id, file_path)
        if cand is not None:
            out.append(cand)

    labels: list[tuple[dict[str, Any], str, tuple[float, float, float, float]]] = []
    values: list[tuple[dict[str, Any], tuple[float, float, float, float]]] = []
    title_inserts, region = _title_region(entries)
    for e in entries:
        text = e["display_text"].strip()
        if e["position"]["x"] is None or not text:
            continue
        if e["entity_type"] == "ATTRIB" and e["tag"]:
            fld = _tag_field(e["tag"])
            if fld:
                # a field tag is evidence only on the title block: the frame's own INSERT, a title-block
                # INSERT, or inside the title-block region (a section callout's SHEET_NO is not)
                c = text_center(e)
                on_title = (
                    ctx.own_insert(e)
                    or _insert_key(e) in title_inserts
                    or (c is not None and any(inside(b, *c) for b in region))  # type: ignore[arg-type]
                )
                if on_title:
                    add(fld, text, "attrib_tag", e["tag"], e, None, _entry_conf(e, cap))
                continue
        fld = _label_field(text)
        if fld:
            box = text_box(e)
            if box and _horizontal(e):
                labels.append((e, fld, box))
            continue
        m = _INLINE_RE.match(text)
        if m and "\n" not in text:
            fld = _label_field(m.group("label"))
            if fld:
                add(
                    fld,
                    m.group("value"),
                    "inline_label",
                    m.group("label").strip(),
                    e,
                    None,
                    _entry_conf(e, cap),
                )
                continue
        if ctx.template(e) or not _horizontal(e) or len(text) > 80 or "\n" in text:
            continue
        box = text_box(e)
        if box:
            values.append((e, box))

    for lentry, fld, lbox in labels:
        lh = lentry.get("height") or (lbox[3] - lbox[1]) or 0.0
        if lh <= 0:
            continue
        lcx, lcy = box_center(lbox)
        best: tuple[float, str, dict[str, Any]] | None = None
        for ventry, vbox in values:
            vcx, vcy = box_center(vbox)
            right = abs(vcy - lcy) <= 0.6 * lh and 0 < vbox[0] - lbox[2] + 0.5 * lh <= 30 * lh
            below = (
                vbox[0] < lbox[2]
                and vbox[2] > lbox[0]
                and 0 < lbox[1] - vbox[3] + 0.5 * lh <= 4 * lh
                and vcy < lcy
            )
            if not (right or below):
                continue
            dist = math.hypot(vcx - lcx, vcy - lcy)
            key = (dist, ventry["id"])
            if best is None or key < (best[0], best[1]):
                best = (dist, ventry["id"], ventry)
        if best is not None:
            add(
                fld,
                best[2]["display_text"],
                "adjacent_label",
                lentry["display_text"].strip(),
                best[2],
                lentry,
                "low",
            )

    return out


def _candidate_order(c: dict[str, Any]) -> tuple[str, str, str]:
    return (c["field"], c["evidence"]["value_text_id"], c["evidence"]["kind"])


# --- printed sheet number in the title-block corner (tool wave 3, EVAL-3 a1) -------------------------


def _code_key(text: str) -> str:
    """A sheet code or mark compared as letters and digits only ('Kc - 13' and 'KC-13' are one code)."""
    return re.sub(r"[^0-9a-z]", "", fold(text))


def _right_angle(entry: dict[str, Any]) -> int | None:
    """The text's rotation when it is a multiple of 90 degrees (within 1 degree), else None."""
    rot = (entry.get("rotation") or 0.0) % 360.0
    quarter = round(rot / 90.0)
    return (quarter % 4) * 90 if abs(rot - quarter * 90.0) < 1.0 else None


def _reading_position(
    frame: tuple[float, float, float, float], point: tuple[float, float], rotation: int
) -> tuple[float, float]:
    """(u, v) of a point in a frame read along `rotation`: u from the reading left (0) to right (1), v from
    the reading bottom (0) to top (1). At 270 the reading 'right' is world -y and 'up' is world +x."""
    a = (point[0] - frame[0]) / (frame[2] - frame[0])
    b = (point[1] - frame[1]) / (frame[3] - frame[1])
    return {0: (a, b), 90: (b, 1.0 - a), 180: (1.0 - a, 1.0 - b), 270: (1.0 - b, a)}[rotation]


@dataclass
class _CornerHit:
    """A sheet-code-shaped text in a frame's title-block corner."""

    entry: dict[str, Any]
    sheet_id: str
    u: float
    v: float
    key: str
    prefix: str


def _corner_scan(
    entries: list[dict[str, Any]], ctx: _SheetCtx
) -> tuple[list[_CornerHit], list[dict[str, Any]]]:
    """(sheet-code texts in the frame's title-block corner, sheet-code texts elsewhere on the sheet).

    The corner is the last CORNER_U of the frame along the text's reading direction and the lowest
    CORNER_V across it (TCVN 5571 puts the title block at the lower right). A landscape frame is read at
    0 degrees only; a portrait frame also at 90 and 270 degrees (a landscape sheet drawn turned, as on 267
    and 290). Constant text of the frame's own block is template text and never a value."""
    x0, y0, x1, y1 = ctx.box
    portrait = (y1 - y0) > (x1 - x0)
    allowed = (0, 90, 270) if portrait else (0,)
    corner: list[_CornerHit] = []
    body: list[dict[str, Any]] = []
    for e in entries:
        text = e["display_text"].strip()
        if e["position"]["x"] is None or "\n" in text or not _SHEET_CODE_RE.match(text):
            continue
        box = text_box(e)
        rot = _right_angle(e)
        # a model text shown through a layout's viewport has model coordinates: never in that layout's box
        if box is not None and rot in allowed and not ctx.template(e) and inside(ctx.box, *box_center(box)):
            u, v = _reading_position(ctx.box, box_center(box), rot)  # type: ignore[arg-type]
            if u >= 1.0 - CORNER_U and v <= CORNER_V:
                key = _code_key(text)
                prefix = re.match(r"[a-z]*", key)
                corner.append(_CornerHit(e, ctx.sheet_id, u, v, key, prefix.group(0) if prefix else ""))
                continue
        body.append(e)
    return corner, body


def _pick_corner_numbers(
    corner: dict[str, list[_CornerHit]],
    body: dict[str, list[dict[str, Any]]],
    unplaced_codes: Counter[str],
    need: set[str],
) -> tuple[dict[str, list[_CornerHit]], list[str]]:
    """Sheet-number picks for the sheets in `need` (no other sheet-number candidate), and one warning per
    corner code not picked. Rules, in order:

    1. A member mark is never a sheet number. A corner code is a mark when the same code appears on
       another text of its own sheet (a sheet prints its number once), when two or more other texts of its
       sheet share its letters with other numbers (a mark family such as gĐ-1, gĐ-2), or when the code
       appears two or more times outside every title-block corner of the file. A text on a sheet whose code
       is the corner code of ANOTHER sheet of the file is a reference to that sheet (a detail callout, a
       drawing list, an index sheet), never mark evidence; only corner codes that pass the two own-sheet
       checks count as sheets that can be referenced. References to sheets outside the file cannot be told
       apart: they still count, so the sheet is asked (sheet_number_missing), never given a wrong number.
    2. A code at a position that repeats in another sheet's corner (within CORNER_POS_TOL) beats one that
       does not; then the tallest wins. Codes that tie on both are all kept, so they become a
       title_field_conflict question, never a silent choice.
    3. A pick needs that backing (review M3): when no code of a sheet's corner sits at a position repeated
       in another sheet's corner (a one-sheet file never has one), nothing is picked; each code is a
       warning and the sheet gets sheet_number_missing."""

    def own_counts(sid: str, hits: list[_CornerHit], refs: set[str]):
        own = Counter(k for e in body.get(sid, []) if (k := _code_key(e["display_text"])) not in refs)
        own.update(h.key for h in hits)
        families: Counter[str] = Counter()
        for key, n in own.items():
            families[re.match(r"[a-z]*", key).group(0)] += n  # type: ignore[union-attr]
        return own, families

    # corner codes that pass the own-sheet checks with every body text counted: the sheets a body text can
    # reference. A body text equal to its OWN sheet's corner code makes that code a twice-seen mark, which
    # is never referable, so a referable code always names another sheet.
    referable: set[str] = set()
    for sid, hits in corner.items():
        own, families = own_counts(sid, hits, set())
        referable.update(h.key for h in hits if own[h.key] < 2 and families[h.prefix] - own[h.key] < 2)

    outside = Counter(unplaced_codes)
    for texts in body.values():
        outside.update(k for e in texts if (k := _code_key(e["display_text"])) not in referable)
    marks: dict[int, str] = {}
    for sid, hits in corner.items():
        own, families = own_counts(sid, hits, referable)
        for h in hits:
            others = families[h.prefix] - own[h.key]
            if own[h.key] >= 2:
                marks[id(h)] = f"the same text appears {own[h.key]} times on this sheet (a member mark)"
            elif others >= 2:
                marks[id(h)] = f"{others} other texts on this sheet share its letters (a mark family)"
            elif outside[h.key] >= 2:
                marks[id(h)] = f"it appears {outside[h.key]} times outside the title blocks (a mark)"
    usable = [h for hits in corner.values() for h in hits if id(h) not in marks]
    picks: dict[str, list[_CornerHit]] = {}
    warnings: list[str] = []
    for sid in [sid for sid in corner if sid in need]:  # sheet order
        hits = corner[sid]

        def rank(h: _CornerHit) -> tuple[bool, float]:
            repeats = any(
                o.sheet_id != h.sheet_id
                and abs(o.u - h.u) <= CORNER_POS_TOL
                and abs(o.v - h.v) <= CORNER_POS_TOL
                for o in usable
            )
            return (repeats, float(h.entry.get("height") or 0.0))

        ranked = [(rank(h), h) for h in hits if id(h) not in marks]
        best = max((r for r, _ in ranked), default=(False, 0.0))
        backed = best[0]  # rule 3: some code of this corner sits at a position repeated elsewhere
        chosen = [h for r, h in ranked if backed and r[0] and _same_height(r[1], best[1])]
        if chosen:
            picks[sid] = chosen
        for r, h in ranked:
            if h in chosen:
                continue
            if not backed:
                why = "its position repeats in no other sheet's corner, so nothing backs it as a sheet number"
            elif not r[0]:
                why = "a code at a position repeated on other sheets was preferred"
            else:
                why = "a taller code was preferred"
            warnings.append(
                f"{sid}: corner code '{h.entry['display_text'].strip()}' ({h.entry['id']}) is "
                f"not the sheet number: {why}."
            )
        for h in hits:
            if id(h) in marks:
                warnings.append(
                    f"{sid}: corner code '{h.entry['display_text'].strip()}' ({h.entry['id']}) is "
                    f"not the sheet number: {marks[id(h)]}."
                )
    return picks, warnings


def _same_height(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-6 * max(abs(a), abs(b), 1.0)


# --- gaps in the printed numbers (tool wave 3, KC-25 on 290) ---------------------------------------------

# A chosen sheet number as letters and a sequence number: 'KC-05', 'Kc - 13', 'S-101A' (a letter suffix
# counts as its number), 'KT 1/18' (sheet 1 of 18). Anything else ('A1-02', 'GENERAL') is left out of the
# gap check.
_NUMBER_PARTS_RE = re.compile(
    r"^(?P<prefix>[a-z]{1,4})\s?(?:[-:.]\s?(?P<n>\d{1,3})[a-z]?|(?P<n2>\d{1,3})\s?/\s?\d{1,3})$"
)


def _number_gap_question(sheets: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, list[str]]:
    """(one non-blocking sheet_number_gap question per file or None when no printed number is skipped,
    one warning per numbering jump).

    A number is missing when it lies between the lowest and highest number of one letter series and no
    sheet of ANY series carries it: on 290 one counter runs over Kc and KT sheets (Kc - 13, KT - 14,
    Kc - 15), so KT - 14 fills the Kc series. Consecutive missing numbers are one range, given with the
    sheets on each side. Sheets without a chosen number are listed: they may carry a missing one.
    A range of more than SHEET_GAP_MAX_RUN numbers is a numbering jump, not a gap (review: S-101, S-201,
    S-301 number by hundreds): it is a warning with the sheets on each side, never asked. The known gaps
    are 1 (290) and 4 (461) numbers long; hundreds numbering skips 98 or more."""
    by_number: dict[int, list[tuple[str, str]]] = defaultdict(list)  # number -> (sheet id, printed value)
    series: dict[str, list[int]] = defaultdict(list)
    for s in sheets:
        chosen = s["title_block"]["sheet_number"]
        if chosen is None:
            continue
        m = _NUMBER_PARTS_RE.match(fold(chosen["value"]))
        if m is None:
            continue
        n = int(m.group("n") or m.group("n2"))
        by_number[n].append((s["sheet_id"], chosen["value"]))
        series[m.group("prefix")].append(n)
    missing = sorted(
        {n for nums in series.values() for n in range(min(nums), max(nums) + 1) if n not in by_number}
    )
    runs: list[list[int]] = []
    for n in missing:
        if runs and runs[-1][-1] == n - 1:
            runs[-1].append(n)
        else:
            runs.append([n])
    order = {s["sheet_id"]: i for i, s in enumerate(sheets)}
    around: set[str] = set()
    parts = []
    jumps = []
    for run in runs:
        lo, hi = by_number[run[0] - 1], by_number[run[-1] + 1]
        if len(run) > SHEET_GAP_MAX_RUN:
            jumps.append(
                f"Sheet numbers jump from {lo[0][1]} ({', '.join(sid for sid, _ in lo)}) to {hi[0][1]} "
                f"({', '.join(sid for sid, _ in hi)}): {len(run)} numbers skipped, taken as a numbering jump "
                f"(more than {SHEET_GAP_MAX_RUN}), not asked as a gap."
            )
            continue
        around.update(sid for sid, _ in lo + hi)
        span = str(run[0]) if len(run) == 1 else f"{run[0]}-{run[-1]}"
        parts.append(
            f"missing {span} (between {lo[0][1]} on {', '.join(sid for sid, _ in lo)} "
            f"and {hi[0][1]} on {', '.join(sid for sid, _ in hi)})"
        )
    if not parts:
        return None, jumps
    unnumbered = [s["sheet_id"] for s in sheets if s["title_block"]["sheet_number"] is None]
    if unnumbered:
        parts.append(f"{len(unnumbered)} sheet(s) without a detected number: {listed(unnumbered)}")
    gap = question(
        SHEET_GAP_CODE,
        False,
        "The printed sheet numbers of this file skip some numbers: is a sheet missing from the set, does "
        "the numbering jump on purpose, or was a number misread?",
        listed(sorted(around, key=order.__getitem__)),
        "; ".join(parts),
    )
    return gap, jumps


def _choose(cands: list[dict[str, Any]], fld: str) -> tuple[dict[str, Any] | None, list[str]]:
    """(chosen sourced_string or None, distinct values among ALL candidates of the field).

    A value is chosen only when every candidate agrees: a lower-confidence candidate that disagrees (the
    number typed as loose text next to a template attribute) is a conflict, not outvoted."""
    mine = [c for c in cands if c["field"] == fld]
    if not mine:
        return None, []
    distinct = sorted({c["value"] for c in mine})
    if len(distinct) != 1:
        return None, distinct
    best = max_conf(*[c["confidence"] for c in mine])
    top = [c for c in mine if c["confidence"] == best]
    c = top[0]
    return {"value": c["value"], "provenance": c["provenance"], "confidence": c["confidence"]}, distinct


# --- entry point -----------------------------------------------------------------------------


def extract_sheets(dxf_path: str | Path, text_index: dict[str, Any], *, doc: Drawing | None = None) -> dict:
    """Segment one DXF into sheets. See the module docstring for the rules."""
    doc = open_checked(dxf_path, text_index, doc)
    file_path = text_index["file"]["path"]
    cap = text_index["file"]["confidence_cap"]
    handles_ok = bool(text_index["file"]["handles_reliable"])
    entries: list[dict[str, Any]] = text_index["entries"]
    by_space: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in entries:
        by_space[e["space"]].append(e)

    walker = Walker(doc, handles_ok)
    questions: list[dict[str, Any]] = []
    warnings: list[str] = []
    sheets: list[dict[str, Any]] = []
    rejected_total = 0
    frame_sources: dict[str, _Rect] = {}
    entry_by_id = {e["id"]: e for e in entries}

    def title_evidence(ids: list[str]) -> bool:
        return any(
            _anchor_field(entry_by_id[t]) for t in ids if t in entry_by_id and is_printed(entry_by_id[t])
        )

    def build_frame_sheets(space: str, layout_name: str, frame: str, layout: Any) -> list[dict[str, Any]]:
        nonlocal rejected_total
        rects: list[_Rect] = []
        for p in walker.walk(layout, space, frozenset({"LWPOLYLINE", "POLYLINE"})):
            try:
                box = rect_of(p.entity)
            except Exception:
                walker.skipped[f"rect_error:{p.entity.dxftype()}"] += 1
                continue
            if box is None:
                continue
            handle = walker.handle(p.entity) if not p.block_path else p.top_handle
            rects.append(
                _Rect(
                    box,
                    space,
                    str(p.entity.dxf.get("layer", "0")),
                    handle,
                    p.block_path,
                    p.top_handle,
                    p.owner,
                )
            )
        found = _find_frames(rects, _TextGrid(by_space.get(space, [])), title_evidence)
        rejected_total += sum(n for _, _, n in found.rejected_groups)
        for a, b in found.overlaps:
            questions.append(
                question(
                    "sheet_frames_overlap",
                    True,
                    "Two sheet-frame candidates overlap; the larger is used, the other is ignored. "
                    "Which one is the sheet?",
                    f"{space}: {rbox(a.box)} and {rbox(b.box)}",
                    f"{rnum(a.w)} x {rnum(a.h)} and {rnum(b.w)} x {rnum(b.h)}",
                )
            )
        for big, n in found.ambiguous:
            questions.append(
                question(
                    "sheet_frame_ambiguous",
                    True,
                    "A sheet-shaped rectangle holds several sheet-shaped rectangles that carry no title "
                    "block of their own: it is kept as ONE sheet (the inner ones as boxed views). Are the "
                    "inner rectangles separate sheets?",
                    f"{space}: {rbox(big.box)}",
                    f"{n} inner rectangle(s) in {rnum(big.w)} x {rnum(big.h)}",
                )
            )
        for c in found.containers:
            warnings.append(
                f"{space}: rectangle {rbox(c.box)} holds several sheet frames; "
                "treated as a container, not a sheet."
            )
        if found.rejected_groups and not found.frames:
            questions.append(
                question(
                    "sheet_frame_candidates_rejected",
                    False,
                    "Groups of same-size rectangles hold text but are not sheet-shaped (aspect ratio or size "
                    "rule). Are any of them sheet frames?",
                    space,
                    "; ".join(f"{n} x {rnum(w)} by {rnum(h)}" for w, h, n in found.rejected_groups[:10]),
                )
            )
        out = []
        for i, r in enumerate(_row_order(found.frames), start=1):
            sid = f"{space}#{i:02d}"
            same = sum(1 for o in found.frames if _same_size(o, r))
            evidence = [
                f"closed axis-aligned rectangle {rnum(r.w)} x {rnum(r.h)} on layer '{r.layer}'",
                f"{len(r.texts)} text entries inside",
                f"{same} frame(s) of this size in {space}",
            ]
            if r.block_path:
                evidence.append(f"inside INSERT path {' > '.join(r.block_path)}")
            if r.inner:
                evidence.append(f"{r.inner} inner rectangle(s) merged")
            frame_sources[sid] = r
            out.append(
                {
                    "sheet_id": sid,
                    "space": space,
                    "layout": layout_name,
                    "coordinate_frame": frame,
                    "bbox": rbox(r.box),
                    "detection": {
                        "method": "frame_rectangle",
                        "confidence": min_conf("medium" if same >= 2 else "low", cap),
                        "evidence": evidence,
                        "frame_handle": r.handle,
                        "frame_block": r.block_path[-1] if r.block_path else None,
                        "frame_layer": r.layer,
                        "inner_frames": r.inner,
                    },
                    "model_windows": [],
                    "text_ids": [],
                    "title_block": {"sheet_number": None, "revision": None, "candidates": []},
                    "duplicate_of": None,
                }
            )
        return out

    spaces = layout_spaces(doc)
    pending_windows: list[tuple[str, Any, tuple[float, ...]]] = []  # (space, viewport, paper centre)
    for space, layout, is_model in spaces:
        frame = "wcs" if is_model else "paper"
        built = build_frame_sheets(space, layout.name, frame, layout)
        if not is_model:
            other = 0
            for e in layout:
                if e.dxftype() == "VIEWPORT":
                    if int(e.dxf.get("id", 0)) == 1:
                        continue
                    centre = e.dxf.get("center", (0.0, 0.0, 0.0))
                    pending_windows.append((space, e, (centre[0], centre[1])))
                else:
                    other += 1
            if not built:
                extent = None
                try:
                    ext = ezbbox.extents([e for e in layout if e.dxftype() != "VIEWPORT"] or [], fast=True)
                    extent = (
                        (ext.extmin.x, ext.extmin.y, ext.extmax.x, ext.extmax.y) if ext.has_data else None
                    )
                except Exception as exc:
                    warnings.append(f"{space}: layout extents failed ({type(exc).__name__}); viewports used.")
                vps = [v for s, v, _ in pending_windows if s == space]
                for v in vps:
                    c, w, h = v.dxf.get("center"), float(v.dxf.get("width", 0)), float(v.dxf.get("height", 0))
                    vb = (c[0] - w / 2, c[1] - h / 2, c[0] + w / 2, c[1] + h / 2)
                    extent = (
                        vb
                        if extent is None
                        else (
                            min(extent[0], vb[0]),
                            min(extent[1], vb[1]),
                            max(extent[2], vb[2]),
                            max(extent[3], vb[3]),
                        )
                    )
                if extent is not None and (other or vps):
                    built = [
                        {
                            "sheet_id": f"{space}#01",
                            "space": space,
                            "layout": layout.name,
                            "coordinate_frame": "paper",
                            "bbox": rbox(extent),
                            "detection": {
                                "method": "layout",
                                "confidence": min_conf("medium", cap),
                                "evidence": [
                                    f"paper-space layout '{layout.name}' with {other} non-viewport entities "
                                    f"and {len(vps)} viewport(s); no frame found"
                                ],
                                "frame_handle": None,
                                "frame_block": None,
                                "frame_layer": None,
                                "inner_frames": 0,
                            },
                            "model_windows": [],
                            "text_ids": [],
                            "title_block": {"sheet_number": None, "revision": None, "candidates": []},
                            "duplicate_of": None,
                            "_other": other,
                        }
                    ]
        sheets.extend(built)

    # viewport windows -> the sheet of the layout that holds the viewport
    by_id = {s["sheet_id"]: s for s in sheets}
    for space, vp, (px, py) in pending_windows:
        window, why = _viewport_window(vp)
        handle = walker.handle(vp)
        if window is None:
            warnings.append(f"{space}: viewport {handle or '?'} not mapped to model space ({why}).")
            continue
        holder = next(
            (
                s
                for s in sheets
                if s["space"] == space
                and s["detection"]["method"] != "layout"
                and inside(tuple(s["bbox"]), px, py)
            ),  # type: ignore[arg-type]
            None,
        ) or next((s for s in sheets if s["space"] == space and s["detection"]["method"] == "layout"), None)
        if holder is None:
            warnings.append(f"{space}: viewport {handle or '?'} lies on no sheet of its layout.")
            continue
        holder["model_windows"].append({"viewport_handle": handle, "bbox": rbox(window)})

    # a model frame shown (even partly) through a viewport that shows no other model frame is drawn
    # inside a printed view of that layout: the layout is the sheet, the frame is not. A window over
    # two or more frames is an overview of the model and removes nothing.
    windows = [(tuple(w["bbox"]), s["sheet_id"]) for s in sheets for w in s["model_windows"]]
    model_frames = [
        s for s in sheets if s["space"] == "model" and s["detection"]["method"] == "frame_rectangle"
    ]
    single: dict[str, str] = {}
    for wb, sid in windows:
        touched = [f["sheet_id"] for f in model_frames if _overlap_area(wb, tuple(f["bbox"])) > 0]
        if len(touched) == 1:
            single.setdefault(touched[0], sid)
    kept_sheets = []
    for s in sheets:
        box = tuple(s["bbox"])
        shown = single.get(s["sheet_id"])
        if shown is not None:
            warnings.append(
                f"model frame {rbox(box)} is shown through a viewport of {shown}: the layout is the sheet."
            )
            frame_sources.pop(s["sheet_id"], None)
            continue
        kept_sheets.append(s)
    if len(kept_sheets) != len(sheets):
        renamed: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for s in kept_sheets:
            renamed[s["space"]].append(s)
        for space_sheets in renamed.values():
            for i, s in enumerate(space_sheets, start=1):
                new_id = f"{s['space']}#{i:02d}"
                if new_id != s["sheet_id"] and s["sheet_id"] in frame_sources:
                    frame_sources[new_id] = frame_sources.pop(s["sheet_id"])
                s["sheet_id"] = new_id
    sheets = kept_sheets
    by_id = {s["sheet_id"]: s for s in sheets}

    # assignment
    locator = SheetLocator({"sheets": [{**s, "text_ids": []} for s in sheets]})
    unassigned: list[str] = []
    ambiguous: list[str] = []
    for e in entries:
        x, y = e["position"]["x"], e["position"]["y"]
        sid = locator._locate(e["space"], x, y) if x is not None and y is not None else None  # pyright: ignore[reportPrivateUsage]
        if sid is None:
            unassigned.append(e["id"])
        elif sid == "ambiguous":
            ambiguous.append(e["id"])
        else:
            by_id[sid]["text_ids"].append(e["id"])

    # layout sheets that show nothing are not sheets
    final: list[dict[str, Any]] = []
    for s in sheets:
        other = s.pop("_other", None)
        if s["detection"]["method"] == "layout" and not other and not s["text_ids"]:
            warnings.append(
                f"{s['space']}: layout holds only viewports that show no indexed text; "
                "not counted as a sheet."
            )
            continue
        final.append(s)
    sheets = final

    # title blocks: field ATTRIBs and labels per sheet, then the sheet-code pattern over all sheets
    title_cands: dict[str, list[dict[str, Any]]] = {}
    corner: dict[str, list[_CornerHit]] = {}
    body: dict[str, list[dict[str, Any]]] = {}
    for s in sheets:
        src = frame_sources.get(s["sheet_id"])

        def is_template(e: dict[str, Any], src: _Rect | None = src) -> bool:
            if src is None or not src.block_path or e["entity_type"] == "ATTRIB":
                return False
            path = tuple(e["block_path"])
            if path[: len(src.block_path)] != src.block_path:
                return False
            return not handles_ok or not e["insert_handles"] or e["insert_handles"][0] == src.top_handle

        def own_insert(e: dict[str, Any], src: _Rect | None = src) -> bool:
            if src is None or not src.block_path or e["entity_type"] != "ATTRIB":
                return False
            if handles_ok and src.top_handle:
                firsts = [e["insert_handle"], *e["insert_handles"][:1]]
                return src.top_handle in firsts
            return e["block_name"] == src.block_path[0] or e["block_path"][:1] == [src.block_path[0]]

        ctx = _SheetCtx(s["sheet_id"], tuple(s["bbox"]), is_template, own_insert)  # type: ignore[arg-type]
        mine = [entry_by_id[t] for t in s["text_ids"] if is_printed(entry_by_id[t])]
        title_cands[s["sheet_id"]] = _title_candidates(mine, ctx, file_path, cap)
        corner[s["sheet_id"]], body[s["sheet_id"]] = _corner_scan(mine, ctx)
    on_sheets = {t for s in sheets for t in s["text_ids"]}
    unplaced = Counter(
        _code_key(e["display_text"])
        for e in entries
        if e["id"] not in on_sheets and is_printed(e) and _SHEET_CODE_RE.match(e["display_text"].strip())
    )
    need = {sid for sid, cands in title_cands.items() if not any(c["field"] == "sheet_number" for c in cands)}
    picks, corner_warnings = _pick_corner_numbers(corner, body, unplaced, need)
    warnings.extend(corner_warnings)
    conflicted: set[tuple[str, str]] = set()  # (sheet, field) with disagreeing candidates
    for s in sheets:
        cands = title_cands[s["sheet_id"]]
        for h in picks.get(s["sheet_id"], []):
            cand = _candidate(
                "sheet_number",
                h.entry["display_text"],
                "pattern",
                "sheet_code_lower_right",
                h.entry,
                None,
                "low",
                s["sheet_id"],
                file_path,
            )
            if cand is not None:
                cands.append(cand)
        cands.sort(key=_candidate_order)
        number, _ = _choose(cands, "sheet_number")
        revision, _ = _choose(cands, "revision")
        s["title_block"] = {"sheet_number": number, "revision": revision, "candidates": cands}
        for fld in sorted({c["field"] for c in cands}):
            values = sorted({c["value"] for c in cands if c["field"] == fld})
            if len(values) > 1:
                questions.append(
                    question(
                        "title_field_conflict",
                        fld in ("sheet_number", "revision"),
                        f"The title block offers different values for '{fld}' (nothing is chosen). "
                        "Which one is printed for this sheet?",
                        s["sheet_id"],
                        " | ".join(values),
                        sheet=s["sheet_id"],
                    )
                )
                if fld in ("sheet_number", "revision"):
                    conflicted.add((s["sheet_id"], fld))

    # consistency
    if not sheets:
        questions.append(
            question(
                "sheets_not_detected",
                True,
                "No sheet frame and no paper-space layout with content was found; every value has sheet "
                "'unknown'. How is this file divided into sheets?",
                str(file_path),
                f"{len(entries)} text entries",
            )
        )
    missing = [
        s["sheet_id"]
        for s in sheets
        if s["title_block"]["sheet_number"] is None and (s["sheet_id"], "sheet_number") not in conflicted
    ]
    if missing:
        questions.append(
            question(
                "sheet_number_missing",
                True,
                "No sheet number could be tied to a title-block field on these sheets. "
                "Give the printed sheet number of each.",
                listed(missing),
                f"{len(missing)} sheet(s)",
            )
        )
    numbers: dict[str, list[str]] = defaultdict(list)
    for s in sheets:
        if s["title_block"]["sheet_number"] is not None:
            numbers[re.sub(r"[^0-9a-z/]", "", fold(s["title_block"]["sheet_number"]["value"]))].append(
                s["sheet_id"]
            )
    for _, ids in sorted(numbers.items()):
        if len(ids) > 1:
            shown = next(s for s in sheets if s["sheet_id"] == ids[0])["title_block"]["sheet_number"]["value"]
            questions.append(
                question(
                    "sheet_number_duplicate",
                    True,
                    "Several sheets carry the same sheet number (two revisions, a copy, or a misread). "
                    "Which sheet is current?",
                    listed(ids),
                    shown,
                )
            )
    gap, jumps = _number_gap_question(sheets)
    warnings.extend(jumps)
    if gap is not None:
        questions.append(gap)
    signatures: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for s in sheets:
        texts = tuple(sorted(entry_by_id[t]["display_text"] for t in s["text_ids"]))
        if len(texts) >= FRAME_MIN_TEXTS:
            signatures[texts].append(s["sheet_id"])
    for ids in sorted(signatures.values()):
        if len(ids) > 1:
            for other in ids[1:]:
                by_id[other]["duplicate_of"] = ids[0]
            questions.append(
                question(
                    "sheet_content_duplicate",
                    True,
                    "These sheets hold exactly the same texts (a copy of the sheet, e.g. inside a block, or "
                    "two revisions). Which one is the drawing to read?",
                    listed(ids),
                    f"{len(by_id[ids[0]]['text_ids'])} identical texts each",
                )
            )
    no_rev = [
        s["sheet_id"]
        for s in sheets
        if s["title_block"]["revision"] is None and (s["sheet_id"], "revision") not in conflicted
    ]
    if sheets and no_rev:
        questions.append(
            question(
                "revision_missing",
                False,
                "No revision could be tied to a title-block field on these sheets (asked once for the set). "
                "What revision is current?",
                listed(no_rev),
                f"{len(no_rev)} sheet(s)",
            )
        )
    if sheets and unassigned:
        questions.append(
            question(
                "texts_unassigned",
                False,
                "Some texts lie outside every detected sheet (notes, scratch work, or an undetected sheet). "
                "Are they part of the drawing set?",
                listed(unassigned, 20),
                f"{len(unassigned)} text entries",
            )
        )
    if ambiguous:
        questions.append(
            question(
                "texts_ambiguous_sheet",
                False,
                "Some model-space texts are shown by viewports of several sheets; they are not assigned.",
                listed(ambiguous, 20),
                f"{len(ambiguous)} text entries",
            )
        )
    for reason, n in sorted(walker.skipped.items()):
        warnings.append(f"{n} block entit(ies)/insert(s) not expanded while looking for frames: {reason}.")
    not_printed = sum(1 for e in entries if not is_printed(e))
    if not_printed:
        warnings.append(
            f"{not_printed} of {len(entries)} indexed texts are not printed (printed: false) and are left "
            "out of every title-block value; they keep their sheet in text_ids."
        )

    assigned = sum(len(s["text_ids"]) for s in sheets)
    return {
        "schema_version": SCHEMA_VERSION,
        "file": {
            "path": file_path,
            "sha256": text_index["file"]["sha256"],
            "confidence_cap": cap,
            "declared_units": declared_units(doc),
        },
        "sheets": sheets,
        "unassigned": {"text_ids": unassigned, "ambiguous_text_ids": ambiguous},
        "drawing_list": {"status": "not_searched"},
        "summary": {
            "sheet_count": len(sheets),
            "by_method": dict(sorted(Counter(s["detection"]["method"] for s in sheets).items())),
            "text_entries": len(entries),
            "assigned": assigned,
            "unassigned": len(unassigned),
            "ambiguous": len(ambiguous),
            "frame_candidates_rejected": rejected_total,
        },
        "questions": questions,
        "warnings": warnings,
    }
