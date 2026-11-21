"""render: `harness render`, one region of a drawing as a PNG the AI reader can look at.

Read-only on the work folder; writes only PNG files (default folder `<work_dir>/renders/`, no ledger, no
lock). Output: schema `render` on stdout, with the pixel <-> drawing-coordinate transform of every image.

Why: the reader reads text only. A geometry count (pile symbols, cap outlines) can be wrong in ways only a
picture shows. ADR-0018 holds the measurements behind the choices below.

How: ezdxf's drawing frontend draws the region into its SVG backend; resvg-py rasterises the SVG. Only the
region is drawn: a frontend subclass skips every entity whose box misses the region (an INSERT's box is its
block's box, memoised, times the insert matrix: `ezdxf.bbox.extents` on an INSERT explodes the block on every
call and costs minutes here; the box of a top-level entity is computed once per call, not once per tile). An
entity whose box is unknown is drawn, never skipped: a MINSERT, an XLINE or a RAY (and an INSERT that holds
one) has no box. An XLINE or RAY is clipped to the region and drawn across it.

Image: dark background, line weight x 2, a margin with ticks and labels in drawing units (drawn as SVG strokes
with a small built-in digit font, so no system font is needed; `--no-overlay` drops the margin; the left
margin widens until the longest y label fits, a label that cannot fit is not drawn and is reported). Long
edge <= `--max-px` (default 1568, at most 1568: the model downscales larger images and the transform would no
longer match what it sees) and area <= 1.15 MP, the margin included, so one image costs about 1.5k tokens;
more detail comes from a smaller region (`--bbox`, `--tiles`), not a bigger image. The SVG is laid out at
10 px per mm, so that every pixel is a whole 0.1 mm (ezdxf rounds page sizes to 0.1 mm): transform error
<= 0.12 px.

Transform of an image pixel (px, py) to drawing units:
    x = x0 + (px - left_margin_px) * units_per_px
    y = y1 - (py - top_margin_px) * units_per_px
`x0`, `y1` are the left and top edge of the drawn area. That area is the requested region grown by less than
half a pixel on each side (whole pixels, centred), so tiles abut with at most a pixel overlap.

Scope: model space only (a paper-space sheet is a usage error). What is not drawn is what AutoCAD hides, as
`harness geometry` counts it: an entity on an off or frozen layer; the content of an INSERT on a frozen
layer, at any depth (an INSERT on an off layer hides only its layer 0 content, which follows the INSERT's
layer); an entity or INSERT with the invisible flag (group 60 = 1: ezdxf does not draw it; the image reports
how many, `entities_invisible`, and an INSERT counts once, not its content). `--layer` filters on the
effective layer (layer 0 in a block follows the placing INSERT, nested); an INSERT is entered whatever its
layer (its content may be on another one), while a DIMENSION or another composite (LEADER, MLINE, table) is
kept or dropped as a whole by its own layer, every piece drawn whatever the piece's layer. Units are never
converted (`units` only reports what the header declares and the engineer answered). Text is never read from
an image: legacy-font text renders garbled, read it with `sheet-text`.

Anything ezdxf prints while drawing (a skipped MTEXT, a hatch timeout, a proxy graphic it cannot read) is
captured and becomes a warning: stdout holds the document only.

File name `<sheet id or 'bbox'>-<10 hex of sha1(file, sha256 of the file in the inventory, region, tile,
layers, max-px, overlay)>.png`: a rerun overwrites the same file; a re-intake of a changed drawing does not.
The PNG is written to a temporary file of its own (unique per call) and moved into place; nothing is
left behind when that fails.

Exit codes: 0 ok, 1 inconsistent work folder, a DXF that is damaged or does not match its text index, a
failure inside ezdxf while drawing, or invalid output; 2 usage (including `--max-px` out of range); 3 the DXF
file or the PNG cannot be read or written (I/O).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import math
import os
import re
import sys
import tempfile
import time
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

import resvg_py
from ezdxf.addons.drawing import layout
from ezdxf.addons.drawing.config import BackgroundPolicy, Configuration
from ezdxf.addons.drawing.frontend import Frontend
from ezdxf.addons.drawing.properties import RenderContext
from ezdxf.addons.drawing.svg import SVGBackend
from ezdxf.bbox import extents as _extents
from ezdxf.math import BoundingBox2d, Vec2, Vec3

from tekla_harness.dimensions import _answered_unit, _open
from tekla_harness.schemas import validate
from tekla_harness.sheet_text import (
    EXIT_INVALID,
    EXIT_USAGE,
    SCHEMA_VERSION,
    ReaderError,
    _details,
    _file_row,
    load_file,
    load_inventory,
)

COMMAND = "render"
HELP = (
    "draw one region of a drawing (model space) to PNG with a known pixel to drawing transform "
    "(writes only PNGs)"
)
EXIT_ENV = 3
DEFAULT_MAX_PX = 1568
MIN_MAX_PX = 128
MAX_MAX_PX = 1568  # the model downscales an image whose long edge is longer
MAX_AREA_PX = 1_150_000
TOKEN_PIXELS = 750  # est_image_tokens = ceil(width * height / 750)
PRUNE_PAD = 0.03  # a box test pad, as a share of the region, for strokes and rounding
PX_PER_MM = 10  # the SVG page is laid out at 10 px per mm: a whole pixel is an exact 0.1 mm page step
LINEWEIGHT_SCALING = 0.8  # line weight x 2 at PX_PER_MM: 2.0 (the old factor) x 4 px per mm / 10
BACKGROUND = "#000000"
FOREGROUND = "#ffffff"
# overlay margins (px): left holds the y labels, bottom the x labels
MARGIN_LEFT, MARGIN_TOP, MARGIN_RIGHT, MARGIN_BOTTOM = 94, 10, 8, 34
Y_LABEL_OFFSET = 8  # a y label ends this far left of the border (5 px tick + 3 px gap)
Y_LABEL_PAD = 4  # and keeps this many px clear of the image edge
GLYPH_SCALE = 2.0  # glyphs are 4 x 6 units
GLYPH_ADVANCE = 10.0
MIN_TICK_PX = {"x": 130.0, "y": 70.0}
LEGACY_TEXT_WARNING = (
    "text in legacy fonts may render garbled and some diacritics are dropped: never read text from the "
    "image, use sheet-text"
)

_OUTSIDE = "outside the region"  # skip reason of an XLINE or RAY that misses the region (no warning)
_UNKNOWN: Any = object()  # a box that could not be computed: the entity is drawn

# digit font: polylines on a 4 x 6 grid, y down
_GLYPHS: dict[str, list[list[tuple[float, float]]]] = {
    "0": [[(0, 0), (4, 0), (4, 6), (0, 6), (0, 0)]],
    "1": [[(1, 1), (2, 0), (2, 6)], [(1, 6), (3, 6)]],
    "2": [[(0, 0), (4, 0), (4, 3), (0, 3), (0, 6), (4, 6)]],
    "3": [[(0, 0), (4, 0), (4, 6), (0, 6)], [(1, 3), (4, 3)]],
    "4": [[(0, 0), (0, 3), (4, 3)], [(4, 0), (4, 6)]],
    "5": [[(4, 0), (0, 0), (0, 3), (4, 3), (4, 6), (0, 6)]],
    "6": [[(4, 0), (0, 0), (0, 6), (4, 6), (4, 3), (0, 3)]],
    "7": [[(0, 0), (4, 0), (4, 6)]],
    "8": [[(0, 0), (4, 0), (4, 6), (0, 6), (0, 0)], [(0, 3), (4, 3)]],
    "9": [[(4, 3), (0, 3), (0, 0), (4, 0), (4, 6), (0, 6)]],
    "-": [[(0, 3), (3, 3)]],
    ".": [[(1, 5.6), (1, 6)]],
}


# --- region pruning ------------------------------------------------------------------------------


class _Boxes:
    """Entity boxes for pruning, with the per-block box memoised for one drawing."""

    def __init__(self, doc: Any):
        self.doc = doc
        self._blocks: dict[str, Any] = {}
        self._top: dict[str, Any] = {}  # handle -> box of a top-level entity: computed once per call

    def block(self, name: str, stack: tuple[str, ...] = ()) -> Any:
        """The box of a block's content in block coordinates; None = empty, _UNKNOWN = not computable."""
        if name in self._blocks:
            return self._blocks[name]
        if name in stack or name not in self.doc.blocks:
            return _UNKNOWN
        points: list[Vec2] = []
        result: Any = None
        for child in self.doc.blocks[name]:
            if child.dxftype() in ("ATTDEF", "VIEWPORT"):  # never drawn inside a block
                continue
            box = self.entity(child, (*stack, name))
            if box is _UNKNOWN:
                result = _UNKNOWN
                break
            if box is not None:
                points += [box.extmin, box.extmax]
        if result is None and points:
            result = BoundingBox2d(points)
        self._blocks[name] = result
        return result

    def entity(self, e: Any, stack: tuple[str, ...] = ()) -> Any:
        """The box in the entity's own space (world space for a top-level or virtual entity)."""
        key = None if stack or e.is_virtual else e.dxf.get("handle")
        if key is None:
            return self._entity(e, stack)
        if key not in self._top:
            self._top[key] = self._entity(e, stack)
        return self._top[key]

    def _entity(self, e: Any, stack: tuple[str, ...]) -> Any:
        kind = e.dxftype()
        try:
            if kind in ("XLINE", "RAY"):  # infinite: no box, so never pruned (nor an INSERT holding one)
                return _UNKNOWN
            if kind == "INSERT":
                if e.mcount > 1:
                    return _UNKNOWN
                inner = self.block(str(e.dxf.name), stack)
                if inner is _UNKNOWN:
                    return _UNKNOWN
                points: list[Vec2] = []
                if inner is not None:
                    lo, hi = inner.extmin, inner.extmax
                    corners = [(lo.x, lo.y, 0), (hi.x, lo.y, 0), (hi.x, hi.y, 0), (lo.x, hi.y, 0)]
                    points += [Vec2(v) for v in e.matrix44().transform_vertices(corners)]
                for attrib in e.attribs:  # drawn outside the block's own content
                    box = self.entity(attrib)
                    if box is _UNKNOWN:
                        return _UNKNOWN
                    if box is not None:
                        points += [box.extmin, box.extmax]
                return BoundingBox2d(points) if points else None
            if kind == "DIMENSION":
                geometry = e.dxf.get("geometry")
                if not geometry or geometry not in self.doc.blocks:
                    return _UNKNOWN
                return self.block(str(geometry), stack)  # a dimension block holds world coordinates
            if kind in ("VIEWPORT", "ATTDEF"):
                return None
            box = _extents([e])
            return BoundingBox2d([box.extmin, box.extmax]) if box.has_data else None
        except Exception:
            return _UNKNOWN


def _clip_infinite(
    start: Vec3, direction: Vec3, is_ray: bool, box: tuple[float, float, float, float]
) -> tuple[Vec3, Vec3] | None:
    """The part of an XLINE (or RAY) inside `box` (x0, y0, x1, y1), in 2D; None when it misses the box."""
    dx, dy = float(direction.x), float(direction.y)
    length = math.hypot(dx, dy)
    if length < 1e-12:
        return None
    dx, dy = dx / length, dy / length
    t0, t1 = (0.0 if is_ray else -math.inf), math.inf
    for s, d, lo, hi in ((start.x, dx, box[0], box[2]), (start.y, dy, box[1], box[3])):
        if abs(d) < 1e-12:
            if s < lo or s > hi:
                return None
            continue
        ta, tb = (lo - s) / d, (hi - s) / d
        t0, t1 = max(t0, min(ta, tb)), min(t1, max(ta, tb))
    if t0 > t1:
        return None
    return (
        Vec3(start.x + t0 * dx, start.y + t0 * dy, start.z),
        Vec3(start.x + t1 * dx, start.y + t1 * dy, start.z),
    )


class _RegionFrontend(Frontend):
    """The ezdxf frontend limited to a region and, optionally, to some effective layers."""

    def __init__(
        self,
        ctx: RenderContext,
        out: SVGBackend,
        config: Configuration,
        boxes: _Boxes,
        region: tuple[float, float, float, float],
        layers: frozenset[str] | None,
    ):
        super().__init__(ctx, out, config)
        self.boxes = boxes
        pad_x, pad_y = (region[2] - region[0]) * PRUNE_PAD, (region[3] - region[1]) * PRUNE_PAD
        self.area = (region[0] - pad_x, region[1] - pad_y, region[2] + pad_x, region[3] + pad_y)
        # an infinite line is cut to the area plus a margin as wide as the area itself
        wide_x, wide_y = self.area[2] - self.area[0], self.area[3] - self.area[1]
        self._line_box = (
            self.area[0] - wide_x,
            self.area[1] - wide_y,
            self.area[2] + wide_x,
            self.area[3] + wide_y,
        )
        self.layers = layers
        self.drawn = 0  # leaves and composites (a dimension, a leader) once; INSERTs are entered, not counted
        self.pruned = 0
        self.invisible = 0  # entities with the invisible flag (group 60) inside the region: ezdxf skips them
        self.not_expanded: Counter[str] = Counter()
        self.skipped: Counter[str] = Counter()
        self._composite = 0  # depth inside a kept DIMENSION, LEADER, ...: its pieces are never filtered
        self._inside = 0  # depth inside an INSERT whose box lies wholly in the area: its children are kept
        self._leaves = 0
        self._skips = 0
        self._layer_state: dict[str, tuple[bool, bool]] = {}

    def _state(self, layer: str) -> tuple[bool, bool]:
        """(off, frozen) of a layer; an unknown layer is on."""
        key = layer.casefold()
        if key not in self._layer_state:
            layers = self.boxes.doc.layers
            entry = layers.get(layer) if layers.has_entry(layer) else None
            self._layer_state[key] = (False, False) if entry is None else (entry.is_off(), entry.is_frozen())
        return self._layer_state[key]

    def skip_entity(self, entity: Any, msg: str) -> None:
        if msg == "invisible":
            layer = self.ctx.resolve_layer(entity)
            hidden = self._state(layer)[1] if entity.dxftype() == "INSERT" else any(self._state(layer))
            if not hidden and int(entity.dxf.get("invisible", 0) or 0) == 1:  # not hidden by its layer
                self.invisible += 1
            return
        self._skips += 1
        if msg == _OUTSIDE:
            return  # a line that misses the region is not a defect: no warning
        self.skipped[f"{entity.dxftype()}: {msg}"] += 1

    def draw_line_entity(self, entity: Any, properties: Any) -> None:
        kind = entity.dxftype()
        if kind not in ("XLINE", "RAY"):
            super().draw_line_entity(entity, properties)
            return
        start, direction = Vec3(entity.dxf.start), Vec3(entity.dxf.unit_vector)
        clipped = _clip_infinite(start, direction, kind == "RAY", self._line_box)
        if clipped is None or _clip_infinite(start, direction, kind == "RAY", self.area) is None:
            self.skip_entity(entity, _OUTSIDE)  # nothing of it lies in the region: not drawn, not counted
            return
        self.pipeline.draw_line(clipped[0], clipped[1], properties)

    def draw_entity(self, entity: Any, properties: Any) -> None:
        kind = entity.dxftype()
        if kind == "INSERT" and self._state(properties.layer)[1]:
            return  # a frozen layer hides the whole reference, whatever the layers of its content
        composite = kind != "INSERT" and kind not in self._dispatch
        outer = self._composite == 0
        skips, leaves = self._skips, self._leaves
        inside = kind == "INSERT" and self._wholly_inside(entity)
        self._composite += composite
        self._inside += inside
        try:
            super().draw_entity(entity, properties)
        finally:
            self._composite -= composite
            self._inside -= inside
        if kind == "INSERT":
            return
        made = self._leaves > leaves if composite else self._skips == skips
        if made and not composite:
            self._leaves += 1
        if made and outer:
            self.drawn += 1

    def _wholly_inside(self, e: Any) -> bool:
        """True when the entity's box is known and lies inside the area (its children cannot be pruned)."""
        box = self.boxes.entity(e)
        if box is _UNKNOWN or box is None:
            return False
        a = self.area
        return bool(
            box.extmin.x >= a[0] and box.extmax.x <= a[2] and box.extmin.y >= a[1] and box.extmax.y <= a[3]
        )

    def draw_entities(self, entities: Any, *, filter_func: Any = None) -> None:
        super().draw_entities(entities, filter_func=self._keep)

    def _keep(self, e: Any) -> bool:
        if self._composite:  # the pieces of a composite that was kept
            return True
        kind = e.dxftype()
        box = None if self._inside else self.boxes.entity(e)  # inside a wholly visible INSERT: no test
        if box is not _UNKNOWN and box is not None:
            a = self.area
            if box.extmax.x < a[0] or box.extmin.x > a[2] or box.extmax.y < a[1] or box.extmin.y > a[3]:
                self.pruned += 1
                return False
        if kind == "INSERT":
            block = self.boxes.doc.blocks.get(str(e.dxf.get("name", "")))
            if block is None:
                self.not_expanded["missing_block"] += 1
            elif block.block is not None and (block.block.is_xref or block.block.is_xref_overlay):
                self.not_expanded["xref"] += 1
            return True  # entered whatever its layer: the content may be on another one
        return self.layers is None or self.ctx.resolve_layer(e).casefold() in self.layers


class _LogCollector(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: Counter[str] = Counter()

    def emit(self, record: logging.LogRecord) -> None:
        self.messages[record.getMessage()] += 1


# --- geometry of the image -----------------------------------------------------------------------


def _plan(
    width: float, height: float, max_px: int, overlay: bool, left: int = MARGIN_LEFT
) -> tuple[float, int, int, tuple[int, ...]]:
    """(px per unit, content width px, content height px, margins left/top/right/bottom) in the budget."""
    margins = (left, MARGIN_TOP, MARGIN_RIGHT, MARGIN_BOTTOM) if overlay else (0, 0, 0, 0)
    left, top, right, bottom = margins
    avail_w, avail_h = max_px - left - right, max_px - top - bottom
    scale = min(avail_w / width, avail_h / height)
    while True:
        w, h = max(1, math.ceil(width * scale - 1e-9)), max(1, math.ceil(height * scale - 1e-9))
        if w <= avail_w and h <= avail_h and (w + left + right) * (h + top + bottom) <= MAX_AREA_PX:
            return scale, w, h, margins
        scale *= 0.999


def _y_ticks(y0: float, y1: float, scale: float) -> list[tuple[float, str]]:
    """(value, label) of the y ticks of a drawn area."""
    step = _nice_step(y1 - y0, scale, MIN_TICK_PX["y"])
    ticks = []
    value = math.ceil(y0 / step) * step
    while value <= y1:
        ticks.append((value, _label(value, step)))
        value += step
    return ticks


def _label_room(text: str) -> int:
    """The left margin a y label needs: its glyphs, the tick and the gap, and a clear edge."""
    return math.ceil(GLYPH_ADVANCE * len(text)) + Y_LABEL_OFFSET + Y_LABEL_PAD


def _layout(
    region: tuple[float, float, float, float], max_px: int, overlay: bool
) -> tuple[float, int, int, tuple[int, ...], tuple[float, float, float, float]]:
    """(scale, w, h, margins, drawn area). The left margin widens until the longest y label fits, up to a
    quarter of `--max-px` (not of the final long edge, which the area cap can shorten); labels that still
    do not fit are left out by `_overlay_svg`."""
    rw, rh = region[2] - region[0], region[3] - region[1]
    cx, cy = (region[0] + region[2]) / 2, (region[1] + region[3]) / 2
    left, cap = MARGIN_LEFT, max(MARGIN_LEFT, max_px // 4)
    while True:
        scale, w, h, margins = _plan(rw, rh, max_px, overlay, left)
        eff = (cx - w / scale / 2, cy - h / scale / 2, cx + w / scale / 2, cy + h / scale / 2)
        if not overlay:
            return scale, w, h, margins, eff
        need = max((_label_room(text) for _, text in _y_ticks(eff[1], eff[3], scale)), default=0)
        if min(need, cap) <= left:
            return scale, w, h, margins, eff
        left = min(need, cap)


def _nice_step(span_units: float, px_per_unit: float, min_px: float) -> float:
    """The smallest 1, 2 or 5 x 10^k whose ticks are at least `min_px` apart."""
    raw = min_px / px_per_unit
    power = 10 ** math.floor(math.log10(raw))
    for mult in (1, 2, 5, 10):
        if mult * power >= raw:
            return mult * power
    return 10 * power


def _label(value: float, step: float) -> str:
    decimals = max(0, -math.floor(math.log10(step) + 1e-9))
    text = f"{value:.{decimals}f}"
    return "0" if text.strip("-0.") == "" else text


def _text_path(text: str, x: float, y: float, anchor: str) -> str:
    """SVG path data of `text` in the stroke digit font; (x, y) = anchor, 'm' centred / 'r' right-aligned
    horizontally, y the vertical middle."""
    width = GLYPH_ADVANCE * len(text)
    left = x - width / 2 if anchor == "m" else x - width
    top = y - 3 * GLYPH_SCALE
    parts = []
    for i, ch in enumerate(text):
        for line in _GLYPHS.get(ch, []):
            pts = [(left + i * GLYPH_ADVANCE + gx * GLYPH_SCALE, top + gy * GLYPH_SCALE) for gx, gy in line]
            parts.append("M" + " L".join(f"{px:.2f} {py:.2f}" for px, py in pts))
    return " ".join(parts)


def _overlay_svg(
    eff: tuple[float, float, float, float], scale: float, w: int, h: int, margins: tuple[int, ...]
) -> tuple[str, int]:
    """(SVG of the border, ticks and labels; the number of y labels left out for want of room)."""
    left, top, right, _ = margins
    total_w = left + w + right
    x0, y0, x1, y1 = eff
    ticks: list[str] = []
    labels: list[str] = []
    dropped = 0
    step_x = _nice_step(x1 - x0, scale, MIN_TICK_PX["x"])
    value = math.ceil(x0 / step_x) * step_x
    while value <= x1:
        px = left + (value - x0) * scale
        text = _label(value, step_x)
        ticks.append(f"M{px:.2f} {top + h} L{px:.2f} {top + h + 5}")
        if px - GLYPH_ADVANCE * len(text) / 2 >= 0 and px + GLYPH_ADVANCE * len(text) / 2 <= total_w:
            labels.append(_text_path(text, px, top + h + 5 + 3 + 3 * GLYPH_SCALE, "m"))
        value += step_x
    for value, text in _y_ticks(y0, y1, scale):
        py = top + (y1 - value) * scale
        ticks.append(f"M{left - 5} {py:.2f} L{left} {py:.2f}")
        if _label_room(text) <= left:
            labels.append(_text_path(text, left - Y_LABEL_OFFSET, py, "r"))
        else:
            dropped += 1
    border = f"M{left} {top} h{w} v{h} h{-w} Z"
    stroke = f'fill="none" stroke="{FOREGROUND}" stroke-width="1"'
    svg = (
        f'<path d="{border} {" ".join(ticks)}" {stroke}/>'
        f'<path d="{" ".join(labels)}" {stroke} stroke-linecap="round" stroke-linejoin="round"/>'
    )
    return svg, dropped


def _draw_region(
    doc: Any,
    boxes: _Boxes,
    region: tuple[float, float, float, float],
    layers: frozenset[str] | None,
    max_px: int,
    overlay: bool,
) -> tuple[bytes, dict[str, Any], list[str]]:
    """(PNG bytes, the image's measurements, warnings) of one region of model space."""
    scale, w, h, margins, eff = _layout(region, max_px, overlay)
    left, top, right, bottom = margins
    config = Configuration(background_policy=BackgroundPolicy.BLACK, lineweight_scaling=LINEWEIGHT_SCALING)
    backend = SVGBackend()
    frontend = _RegionFrontend(RenderContext(doc), backend, config, boxes, region, layers)
    collector = _LogCollector()
    ezdxf_log = logging.getLogger("ezdxf")
    ezdxf_log.addHandler(collector)
    printed = io.StringIO()  # ezdxf reports some problems with print(): they go to the warnings
    try:
        with redirect_stdout(printed):
            frontend.draw_layout(doc.modelspace(), finalize=True)
            # 10 px per mm: ezdxf rounds the page size to 0.1 mm, so a whole pixel is an exact page step
            page = layout.Page(w / PX_PER_MM, h / PX_PER_MM, layout.Units.mm)
            settings = layout.Settings(
                fit_page=True, crop_at_margins=True, page_alignment=layout.PageAlignment.TOP_LEFT
            )
            svg = backend.get_string(
                page, settings=settings, render_box=BoundingBox2d([(eff[0], eff[1]), (eff[2], eff[3])])
            )
    except ReaderError:
        raise
    except Exception as exc:
        raise ReaderError(EXIT_INVALID, f"ezdxf failed while drawing ({type(exc).__name__}): {exc}") from exc
    finally:
        ezdxf_log.removeHandler(collector)
    match = re.search(r'viewBox="([^"]+)"', svg)
    if match is None:
        raise ReaderError(EXIT_INVALID, "internal error: the SVG has no viewBox")
    body = svg[svg.index("<svg") :]
    body = re.sub(
        r"<svg [^>]*>",
        f'<svg x="{left}" y="{top}" width="{w}" height="{h}" viewBox="{match.group(1)}" '
        'preserveAspectRatio="none">',
        body,
        count=1,
    )
    total_w, total_h = left + w + right, top + h + bottom
    frame, dropped = _overlay_svg(eff, scale, w, h, margins) if overlay else ("", 0)
    document = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="{total_h}" '
        f'viewBox="0 0 {total_w} {total_h}"><rect width="{total_w}" height="{total_h}" fill="{BACKGROUND}"/>'
        f"{body}{frame}</svg>"
    )
    try:
        png = bytes(
            resvg_py.svg_to_bytes(
                svg_string=document,
                width=total_w,
                height=total_h,
                background=BACKGROUND,
                skip_system_fonts=True,
            )
        )
    except Exception as exc:
        raise ReaderError(EXIT_INVALID, f"internal error: the SVG cannot be rasterised: {exc}") from exc
    warnings = []
    if frontend.not_expanded:
        warnings.append(f"some INSERTs were not expanded: {dict(sorted(frontend.not_expanded.items()))}")
    for reason, count in sorted(frontend.skipped.items()):
        warnings.append(f"{count} entities were not drawn ({reason})")
    if frontend.invisible:
        warnings.append(
            f"{frontend.invisible} entities carry the invisible flag (group 60), mostly hidden visibility "
            "states of dynamic blocks; render does not draw them, geometry counts them: confirm a counted "
            "member with render"
        )
    if dropped:
        warnings.append(
            f"{dropped} y tick labels did not fit the left margin and are not drawn (the ticks are)"
        )
    lines = Counter(line.strip() for line in printed.getvalue().splitlines() if line.strip())
    for message, count in sorted(collector.messages.items()):
        warnings.append(f"ezdxf: {message}" + (f" (x{count})" if count > 1 else ""))
    for line, count in sorted(lines.items()):
        what = "a hatch was left unfilled, " if "hatching timeout" in line else ""
        warnings.append(f"{what}ezdxf: {line}" + (f" (x{count})" if count > 1 else ""))
    measures = {
        "region": list(region),
        "width_px": total_w,
        "height_px": total_h,
        "units_per_px": 1.0 / scale,
        "transform": {
            "left_margin_px": left,
            "top_margin_px": top,
            "units_per_px": 1.0 / scale,
            "x0": eff[0],
            "y1": eff[3],
        },
        "est_image_tokens": math.ceil(total_w * total_h / TOKEN_PIXELS),
        "entities_drawn": frontend.drawn,
        "entities_pruned": frontend.pruned,
        "entities_invisible": frontend.invisible,
    }
    return png, measures, warnings


# --- the command ---------------------------------------------------------------------------------


def _parse_tiles(text: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)[xX](\d+)", text.strip())
    if match is None or int(match.group(1)) < 1 or int(match.group(2)) < 1:
        raise ReaderError(EXIT_USAGE, f"--tiles must be COLSxROWS with both at least 1, got '{text}'")
    return int(match.group(1)), int(match.group(2))


def _tile_regions(
    region: tuple[float, float, float, float], cols: int, rows: int
) -> list[tuple[tuple[int, int], tuple[float, float, float, float]]]:
    x0, y0, x1, y1 = region
    xs = [x0 + (x1 - x0) * c / cols for c in range(cols)] + [x1]
    ys = [y1 - (y1 - y0) * r / rows for r in range(rows)] + [y0]  # top row first
    return [((c, r), (xs[c], ys[r + 1], xs[c + 1], ys[r])) for r in range(rows) for c in range(cols)]


def _file_name(
    prefix: str,
    file_rel: str,
    sha256: str,
    tile: tuple[int, int],
    region: tuple[float, float, float, float],
    layers: list[str],
    max_px: int,
    overlay: bool,
) -> str:
    key = json.dumps(
        [file_rel, sha256, list(region), list(tile), layers, max_px, overlay], separators=(",", ":")
    )
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
    return f"{re.sub(r'[^A-Za-z0-9#._-]', '_', prefix)}-{digest}.png"


def render(
    work_dir: Path | str,
    file_rel: str,
    *,
    sheet: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    tiles: str = "1x1",
    layers: list[str] | None = None,
    max_px: int = DEFAULT_MAX_PX,
    overlay: bool = True,
    out_dir: Path | str | None = None,
    input_dir: Path | str | None = None,
    check_inputs: bool = False,
) -> dict[str, Any]:
    """Render a region to PNG file(s) and return the render document. Raises ReaderError."""
    if (sheet is None) == (bbox is None):
        raise ReaderError(EXIT_USAGE, "give exactly one of --sheet and --bbox")
    if not MIN_MAX_PX <= max_px <= MAX_MAX_PX:
        raise ReaderError(
            EXIT_USAGE,
            f"--max-px must be between {MIN_MAX_PX} and {MAX_MAX_PX} (a longer edge is downscaled by the "
            f"model, and the transform would no longer match what it sees), got {max_px}",
        )
    cols, rows = _parse_tiles(tiles)
    if bbox is not None and (
        not all(math.isfinite(v) for v in bbox) or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]
    ):
        raise ReaderError(EXIT_USAGE, "--bbox X0 Y0 X1 Y1 needs finite numbers with X1 > X0 and Y1 > Y0")
    inv = load_inventory(work_dir)
    loaded = load_file(inv, _file_row(inv, file_rel), check_inputs=check_inputs)
    if loaded.skip is not None or loaded.text_index is None:
        raise ReaderError(EXIT_USAGE, f"{file_rel} cannot be read: {loaded.skip}")
    warnings = [f"{file_rel}: {w}" for w in loaded.warnings]
    if sheet is not None:
        if loaded.sheets is None:
            raise ReaderError(EXIT_USAGE, f"--sheet needs the sheets document: {'; '.join(warnings)}")
        found = {s["sheet_id"]: s for s in loaded.sheets["sheets"]}
        if sheet not in found:
            raise ReaderError(
                EXIT_USAGE, f"{file_rel} has no sheet '{sheet}' (sheets: {', '.join(found) or 'none'})"
            )
        if found[sheet]["space"] != "model":
            raise ReaderError(
                EXIT_USAGE,
                f"sheet '{sheet}' is on layout '{found[sheet]['space']}': only model space is drawn",
            )
        bbox = tuple(float(v) for v in found[sheet]["bbox"])  # type: ignore[assignment]
    assert bbox is not None
    region = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
    folded = None if not layers else sorted({name.casefold() for name in layers})
    target = Path(out_dir) if out_dir is not None else inv.work / "renders"
    doc = _open(inv, loaded, None if input_dir is None else Path(input_dir).resolve())
    boxes = _Boxes(doc)
    if folded is not None:
        known = {str(layer.dxf.name).casefold() for layer in doc.layers}
        for name in sorted({n for n in layers or [] if n.casefold() not in known}):
            warnings.append(f"--layer {name}: not in the file's layer table, so nothing is drawn on it")
    sha256 = str(loaded.row["sha256"])
    images: list[dict[str, Any]] = []
    prefix = sheet if sheet is not None else "bbox"
    for tile, tile_region in _tile_regions(region, cols, rows):
        png, measures, notes = _draw_region(
            doc, boxes, tile_region, None if folded is None else frozenset(folded), max_px, overlay
        )
        path = (
            target / _file_name(prefix, file_rel, sha256, tile, tile_region, folded or [], max_px, overlay)
        ).resolve()
        temp: Path | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # a name of its own per call: two identical renders at once must not share one temporary file
            fd, name = tempfile.mkstemp(dir=path.parent, prefix=f"{path.name}.", suffix=".tmp")
            temp = Path(name)
            with os.fdopen(fd, "wb") as handle:
                handle.write(png)
            temp.replace(path)
        except OSError as exc:
            raise ReaderError(EXIT_ENV, f"{path}: the PNG cannot be written: {exc}") from exc
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)  # nothing is left behind when the write or the move fails
        images.append({"path": str(path), **measures})
        warnings += [f"tile {tile[0] + 1},{tile[1] + 1}: {n}" if cols * rows > 1 else n for n in notes]
    warnings.append(LEGACY_TEXT_WARNING)
    declared = (loaded.row["units"] or {}).get("value")
    out = {
        "schema_version": SCHEMA_VERSION,
        "kind": "render",
        "project_id": inv.doc["project_id"],
        "file": file_rel,
        "query": {
            "sheet": sheet,
            "bbox": None if sheet is not None else list(region),
            "tiles": [cols, rows],
            "layers": list(layers) if layers else [],
            "max_px": max_px,
            "overlay": overlay,
        },
        "units": {
            "declared": None if declared in (None, "unknown") else declared,
            "answered": _answered_unit(inv, file_rel, warnings),
            "converted": False,
        },
        "images": images,
        "warnings": warnings,
    }
    problems = validate("render", out)
    if problems:
        raise ReaderError(EXIT_INVALID, f"internal error: output is invalid: {_details(problems)}")
    return out


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "work_dir", help="the --out folder of `harness intake` (after `harness read-structure`)"
    )
    parser.add_argument("file", help="input-relative path of the drawing, as in inventory.json")
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--sheet", help="draw this detector sheet (its bbox), e.g. model#06 (see list-sheets)")
    where.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("X0", "Y0", "X1", "Y1"),
        help="draw this region, in model-space drawing units",
    )
    parser.add_argument(
        "--tiles", default="1x1", help="split the region into COLSxROWS equal tiles (default 1x1)"
    )
    parser.add_argument(
        "--layer",
        nargs="+",
        action="extend",
        metavar="LAYER",
        help="draw only these effective layers (layer 0 in a block follows its INSERT), case-insensitive",
    )
    parser.add_argument(
        "--max-px",
        type=int,
        default=DEFAULT_MAX_PX,
        help=f"longest image edge in px, {MIN_MAX_PX} to {MAX_MAX_PX} (default {DEFAULT_MAX_PX})",
    )
    parser.add_argument("--no-overlay", action="store_true", help="no margin with ticks in drawing units")
    parser.add_argument("--out-dir", help="where the PNGs go (default <work_dir>/renders)")
    parser.add_argument(
        "--input-dir", help="the intake input folder (needed when the drawing is a native DXF file)"
    )
    parser.epilog = "Model space only: a paper-space sheet is refused. Text is never read from an image."


def run(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    try:
        doc = render(
            Path(args.work_dir),
            args.file,
            sheet=args.sheet,
            bbox=None if args.bbox is None else tuple(args.bbox),
            tiles=args.tiles,
            layers=args.layer,
            max_px=args.max_px,
            overlay=not args.no_overlay,
            out_dir=Path(args.out_dir) if args.out_dir else None,
            input_dir=Path(args.input_dir) if args.input_dir else None,
        )
    except ReaderError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    print(
        f"render: {len(doc['images'])} image(s), elapsed {time.perf_counter() - started:.1f} s",
        file=sys.stderr,
    )
    print(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False))
    return 0
