"""geometry: `harness geometry`, the linework of one drawing: circles (piles), closed outlines (caps).

Read-only (no work-folder lock, nothing written) unless `--save` is given: then the document is also saved
in `<work>/geometry/` (saved_evidence.py; the work lock is held only for the write).
Output: schema `geometry` on stdout, elapsed time on stderr.

`geometry(work_dir, file_rel, ...)` opens the drawing of one inventory row as `harness dimensions` does (the
converted DXF for a DWG, the input file for a native DXF with `--input-dir`; it must be the one the text
index was built from, else exit 1) and walks it once (`sheets.Walker`, INSERTs and nested INSERTs expanded,
layout tab order). Entities taken from a block are virtual copies in the space's coordinates.

World coordinates: a mirrored INSERT gives copies with extrusion (0, 0, -1), whose centres and vertices are
stored in OCS (x negated). Every coordinate is converted to WCS before it is used.

Kinds. Itemised: `circle` (a CIRCLE; a full ELLIPSE with ratio within 1e-6 of 1, which is what a non-uniform
INSERT scale makes of a circle; a donut: a closed 2-vertex LWPOLYLINE with both bulges +1 or both -1) and
`outline` (a LWPOLYLINE or 2D POLYLINE with the closed flag, or without it when its first and last vertex
coincide within `--tol`; vertices as placed, spline-frame control vertices left out). Only COUNTED per layer,
never itemised (v1): LINE, ARC, HATCH, other ELLIPSEs, SPLINEs and open polylines. KNOWN GAP: an outline drawn
as loose LINEs is not found (`sheets._line_rects` finds such rectangles; a later package may use it). An
outline with a bulge (an arc segment) is never `rectangle`; its bbox follows the arcs.
Tolerance: with the closed flag, only a closing vertex repeating the first one (1e-9 of the size) is dropped.
Position: LINE midpoint, ARC mid-angle point, HATCH and SPLINE the centre of their extents (a hatch without
extents is `unplaced`, with a warning).

Layer: the effective layer. Inside a block, a stored layer 0 takes the layer of the INSERT that places it
(AutoCAD's layer-0 rule, nested: `Placed.outer_layer`). `--layer` (one or more, repeatable) filters on it,
case-insensitive.
An entity is not itemised or counted as a kind but counted as `hidden` for its layer when its effective layer
is off or frozen, or when an INSERT above it (any depth) is on a frozen layer (freezing hides the whole
reference; an off INSERT layer hides only its layer-0 content). The invisible flag (group 60 = 1) hides
nothing: such entities stay in items and groups and are reported (`invisible` per layer, group and item, an
INSERT passes the flag to its content; an item is invisible when all its copies are) with one warning, since
the flag may mean "does not print" or may be set by the DWG converter.

Dedupe: items of the same kind and layer whose geometry is equal after rounding to `--tol` (circle: centre and
diameter; outline: the set of rounded vertices) collapse into one item with `copies` = how many were drawn
(a pile block can draw the same circle many times). `layers.<l>.circles / outlines` count unique items,
`copies_collapsed` the extra copies.

Sheet: `SheetLocator.locate(space, centre)` on the sheets document: the first frame in detector order that
holds the point, null when no frame does. `--sheet`
(one or more ids, one walk serves all) needs the sheets document. `--bbox X0 Y0 X1 Y1` is a model-space
region (item centre inside, inclusive), exclusive with `--sheet`; with neither, every sheet is reported (the
non-empty ones, plus a null-sheet region for what lies on no sheet).

Groups: per region, `circle_groups` (layer, diameter rounded to tol) and `outline_groups` (layer, short, long
rounded to tol, rectangle, vertices), by count (unique items) desc then layer; `--max` caps groups per region
(default 40) and, with `--detail`, items per region (default 500), with a truncation warning naming the full
count. Values are in the drawing's units as stored, never converted (`units` reports declared and answered).
`--tol` defaults to 1 mm in the answered unit, else the declared one, else 1.0 with a warning; `query.tol`
holds the value used.

Library use: `read_geometry` returns the document plus the unique items (`_Item`) of every region: their
space, and for an outline its full drawn ring (bulges flattened to within `--tol` with ezdxf's path, no
64-vertex cap) in world coordinates. `harness contents` is built on it.

Exit codes: 0 ok, 1 inconsistent work folder or invalid output, 2 usage, 3 the DXF cannot be read (I/O).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ezdxf import bbox as ezbbox
from ezdxf import path as ezpath
from ezdxf.lldxf.const import DXFError
from ezdxf.math import OCS, Vec3

from tekla_harness.dimensions import (
    EXIT_ENV,
    _answered_unit,
    _definition,
    _gate_override,
    _open,
    _TextLinks,
)
from tekla_harness.read_dxf import measure_dimension
from tekla_harness.saved_evidence import add_save_argument, save_document, sha_before_save
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
from tekla_harness.sheets import SHEET_UNKNOWN, SheetLocator, Walker, layout_spaces

COMMAND = "geometry"
HELP = (
    "circles (piles) and closed outlines (caps, columns) of one drawing, grouped by size (read-only; "
    "--save keeps the document)"
)
_ = EXIT_ENV  # re-exported: the documented exit code 3 comes from `_open`
_WALKED = frozenset(
    {"CIRCLE", "ARC", "ELLIPSE", "SPLINE", "LINE", "LWPOLYLINE", "POLYLINE", "HATCH", "INSERT"}
)
_WALKED_WITH_DIMENSIONS = _WALKED | {"DIMENSION"}  # `dimensions=True`: the walk also yields DIMENSIONs
_COLLINEAR_REL = 1e-6  # |va x vb| below this share of |va||vb|: the two definition vectors are collinear
_SCALED_REL_TOL = 1e-6  # a block dimension whose copy measures this much differently was scaled
DEFAULT_MAX_GROUPS = 40
DEFAULT_MAX_ITEMS = 500
MAX_POINTS = 64
RIGHT_ANGLE_TOL = math.sin(math.radians(0.5))
_COUNTERS = (
    "circles",
    "outlines",
    "lines",
    "arcs",
    "hatches",
    "ellipses",
    "splines",
    "open_polylines",
    "hidden",
    "invisible",
    "unplaced",
    "copies_collapsed",
)
_KIND_COUNTER = {"LINE": "lines", "ARC": "arcs", "HATCH": "hatches", "SPLINE": "splines"}
_UNIT_TOL = {"mm": 1.0, "cm": 0.1, "m": 0.001, "in": 1 / 25.4, "ft": 1 / 304.8}  # 1 mm in each unit
_CELL_DIGITS = 6
_CLOSE_REL = 1e-9
_CIRCLE_RATIO_TOL = 1e-6
_TAU = 2 * math.pi
_EXTENTS_ERRORS = (DXFError, ValueError, TypeError, IndexError, ArithmeticError)


@dataclass
class _Item:
    id: str
    kind: str
    layer: str
    sheet: str | None
    centre: tuple[float, float]
    top_handle: str | None
    block_path: list[str]
    diameter: float | None = None
    bbox: tuple[float, float, float, float] | None = None
    short: float | None = None
    long: float | None = None
    angle: float | None = None
    rectangle: bool | None = None
    vertices: int | None = None
    points: list[tuple[float, float]] | None = None
    copies: int = 1
    invisible_copies: int = 0
    space: str = "model"
    ring: list[tuple[float, float]] | None = None  # outlines: the drawn ring (arcs flattened), no cap
    ring_chords: bool = False  # outlines: the arcs could not be flattened, the vertex ring is used


@dataclass
class DimRead:
    """One DIMENSION on a sheet, as `read_geometry(..., dimensions=True)` keeps it (any layer, not deduped).

    `row` is the measured row of `read_dxf.measure_dimension` (of the block definition for block content, else
    of the entity) after the legacy-font gate, with `text_entry` linked. `linear` is dimtype 0 or 1: then
    `p1`, `p2` are the extension origins of the placed copy (world) and `u` the unit direction it measures
    along (None when it has none). `factor` is DIMLFAC (None when unreadable). `copy_differs`: a block
    dimension whose copy measures other than its definition (a scaled INSERT)."""

    space: str
    linear: bool
    p1: tuple[float, float] | None
    p2: tuple[float, float] | None
    u: tuple[float, float] | None
    row: dict[str, Any]
    factor: float | None
    copy_differs: bool


@dataclass
class GeometryRead:
    """What one read of a drawing found: the geometry document and the unique items behind it.
    `dims`: the DIMENSIONs of each region, only when read with `dimensions=True`; `dims_unlinked`: how many of
    their texts have no text-index entry (the legacy-font gate was not applied to them)."""

    doc: dict[str, Any]
    regions: dict[str | None, _Region]
    loaded: Any
    dims: dict[str | None, list[DimRead]] = field(default_factory=dict)
    dims_unlinked: int = 0


@dataclass
class _Region:
    sheet: str | None
    bbox: tuple[float, float, float, float] | None = None
    layers: dict[str, Counter[str]] = field(default_factory=dict)
    items: dict[tuple[Any, ...], _Item] = field(default_factory=dict)

    def counter(self, layer: str) -> Counter[str]:
        return self.layers.setdefault(layer, Counter())


def _r3(value: float) -> float:
    return round(float(value), 3) + 0.0


def _cell(value: float, tol: float) -> int:
    """The tolerance cell of a value: round half up on a value pre-rounded to 6 decimals of a cell, so two
    copies that differ by noise (1e-7) never straddle a half-to-even boundary."""
    return math.floor(round(value / tol, _CELL_DIGITS) + 0.5)


def _snap(value: float, tol: float) -> float:
    return round(_cell(value, tol) * tol, 6) + 0.0


def _default_tol(answered: str | None, declared: str | None, warnings: list[str]) -> float:
    """1 mm in drawing units: from the answered unit, else the declared one, else 1.0 with a warning."""
    for unit in (answered, declared):
        if unit in _UNIT_TOL:
            return _UNIT_TOL[str(unit)]
    warnings.append("geometry: tol 1.0 assumed in unknown units; pass --tol")
    return 1.0


def _wcs_xy(entity: Any, x: float, y: float, z: float = 0.0) -> tuple[float, float]:
    v = entity.ocs().to_wcs((x, y, z))
    return float(v[0]), float(v[1])


def _polyline_points(entity: Any) -> tuple[list[tuple[float, float]], bool, list[float]] | None:
    """(world vertices, closed flag, bulge per vertex), or None for what is not a 2D polyline. A spline-frame
    control vertex of a 2D POLYLINE is not on the drawn curve and is left out."""
    kind = entity.dxftype()
    if kind == "LWPOLYLINE":
        pts = [(float(v.x), float(v.y)) for v in entity.vertices_in_wcs()]
        bulges = [float(b) for (b,) in entity.get_points("b")]
        return pts, bool(entity.closed), bulges
    if not entity.is_2d_polyline:
        return None
    pts, bulges = [], []
    for v, p in zip(entity.vertices, entity.points_in_wcs(), strict=True):
        if int(v.dxf.get("flags", 0)) & 16:
            continue
        pts.append((float(p.x), float(p.y)))
        bulges.append(float(v.dxf.get("bulge", 0.0)))
    return pts, bool(entity.is_closed), bulges


def _extents(entity: Any, *, fast: bool = True) -> tuple[float, float, float, float] | None:
    """The world bounding box of an entity (virtual copies included), None when it has none."""
    try:
        box = ezbbox.extents([entity], fast=fast)
    except _EXTENTS_ERRORS:
        return None
    if not box.has_data:
        return None
    return float(box.extmin.x), float(box.extmin.y), float(box.extmax.x), float(box.extmax.y)


def _centre(box: tuple[float, float, float, float]) -> tuple[float, float]:
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def _rectangle(pts: list[tuple[float, float]], bulge: bool, tol: float) -> tuple[float, float, float] | None:
    """(short, long, angle of the long side) of a right-angled 4-vertex outline, else None. The angle is
    rounded first, then reduced into [0, 180) (a square: [0, 90)), so it never reaches the period."""
    if bulge or len(pts) != 4:
        return None
    edges = [(pts[(i + 1) % 4][0] - pts[i][0], pts[(i + 1) % 4][1] - pts[i][1]) for i in range(4)]
    lengths = [math.hypot(*e) for e in edges]
    if min(lengths) <= 0:
        return None
    for i in range(4):
        a, b = edges[i], edges[(i + 1) % 4]
        if abs(a[0] * b[0] + a[1] * b[1]) / (lengths[i] * lengths[(i + 1) % 4]) > RIGHT_ANGLE_TOL:
            return None
    side_a, side_b = (lengths[0] + lengths[2]) / 2, (lengths[1] + lengths[3]) / 2
    long_edge = edges[0] if side_a >= side_b else edges[1]
    period = 90.0 if abs(side_a - side_b) <= tol else 180.0
    angle = _r3(math.degrees(math.atan2(long_edge[1], long_edge[0]))) % period
    return min(side_a, side_b), max(side_a, side_b), angle + 0.0


def _item_id(space: str, kind: str, layer: str, geometry: Any) -> str:
    return "G-" + hashlib.sha1(f"{space}|{kind}|{layer}|{geometry}".encode()).hexdigest()[:10]


def _layer_state(doc: Any, cache: dict[str, tuple[bool, bool]], layer: str) -> tuple[bool, bool]:
    """(off, frozen) of a layer in the layer table; (False, False) for a layer without an entry."""
    if layer not in cache:
        state = (False, False)
        if doc.layers.has_entry(layer):
            entry = doc.layers.get(layer)
            state = (bool(entry.is_off()), bool(entry.is_frozen()))
        cache[layer] = state
    return cache[layer]


def _is_hidden(doc: Any, cache: dict[str, tuple[bool, bool]], layer: str) -> bool:
    return any(_layer_state(doc, cache, layer))


def _arc_mid_point(arc: Any) -> tuple[float, float]:
    centre = arc.dxf.center
    start, end = float(arc.dxf.start_angle), float(arc.dxf.end_angle)
    mid = math.radians(start + ((end - start) % 360.0) / 2)
    r = float(arc.dxf.radius)
    return _wcs_xy(
        arc, float(centre[0]) + r * math.cos(mid), float(centre[1]) + r * math.sin(mid), float(centre[2])
    )


def _polyline_geometry(
    entity: Any,
    pts: list[tuple[float, float]],
    closed_flag: bool,
    bulges: list[float],
    tol: float,
    noted: Counter[str],
) -> tuple[dict[str, Any] | None, tuple[float, float]]:
    """(item geometry or None, position) of a 2D polyline.

    A donut (closed, two vertices, both bulges the same +-1) is a circle. With the closed flag only a closing
    vertex that repeats the first one (within 1e-9 of the size) is dropped; without it the ends closing the
    outline within `tol` is the closure test, and that last vertex is dropped.
    """
    if len(bulges) != len(pts):
        bulges = [0.0] * len(pts)
    if (
        closed_flag
        and len(pts) == 2
        and all(abs(abs(b) - 1.0) <= 1e-6 for b in bulges)
        and bulges[0] * bulges[1] > 0
    ):
        centre = ((pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2)
        diameter = math.hypot(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])
        return {"kind": "circle", "centre": centre, "diameter": diameter}, centre
    gap = math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1])
    size = max(
        max(p[0] for p in pts) - min(p[0] for p in pts), max(p[1] for p in pts) - min(p[1] for p in pts)
    )
    repeated = gap <= (_CLOSE_REL * size if closed_flag else tol)
    drop = len(pts) > 2 and repeated
    ring = pts[:-1] if drop else pts
    ring_bulges = bulges[:-1] if drop else bulges
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    vertex_box = (min(xs), min(ys), max(xs), max(ys))
    if not ((closed_flag or repeated) and len(ring) >= 3):
        return None, _centre(vertex_box)
    has_bulge = any(ring_bulges)
    outline_box = vertex_box
    if has_bulge:  # arc segments reach beyond the vertices
        extents = _extents(entity, fast=False)
        if extents is None:
            noted["outline with a bulge (no extents: vertex bounding box used)"] += 1
        else:
            outline_box = extents
    centre = _centre(outline_box)
    geometry_: dict[str, Any] = {
        "kind": "outline",
        "ring": ring,
        "bulges": ring_bulges,
        "bulge": has_bulge,
        "box": outline_box,
        "centre": centre,
    }
    if has_bulge:
        flat = _flatten(entity, tol)
        if flat is None:
            noted["outline with a bulge (arcs not flattened: vertex ring used)"] += 1
        else:
            geometry_["flat"] = flat
    return geometry_, centre


def _flatten(entity: Any, tol: float) -> list[tuple[float, float]] | None:
    """The drawn ring of a bulged outline in world coordinates, arcs flattened to within `tol`; None when
    ezdxf cannot make a path of the entity."""
    try:
        points = [(float(v.x), float(v.y)) for v in ezpath.make_path(entity).flattening(distance=tol)]
    except _EXTENTS_ERRORS:
        return None
    if len(points) > 1 and math.hypot(points[0][0] - points[-1][0], points[0][1] - points[-1][1]) <= tol / 2:
        points.pop()
    return points if len(points) >= 3 else None


def _inside(box: tuple[float, float, float, float], x: float, y: float) -> bool:
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def _group_lists(
    region: _Region, tol: float, max_groups: int, warnings: list[str], where: str
) -> tuple[Any, Any]:
    circles: dict[tuple[Any, ...], list[_Item]] = {}
    outlines: dict[tuple[Any, ...], list[_Item]] = {}
    for item in region.items.values():
        if item.kind == "circle":
            assert item.diameter is not None
            circles.setdefault((item.layer, _snap(item.diameter, tol)), []).append(item)
        else:
            assert item.short is not None and item.long is not None
            key = (item.layer, _snap(item.short, tol), _snap(item.long, tol), item.rectangle, item.vertices)
            outlines.setdefault(key, []).append(item)

    def centre_bbox(members: list[_Item]) -> list[float]:
        xs, ys = [m.centre[0] for m in members], [m.centre[1] for m in members]
        return [min(xs), min(ys), max(xs), max(ys)]

    cg = [
        {
            "layer": k[0],
            "diameter": k[1],
            "count": len(m),
            "copies": sum(i.copies for i in m),
            "invisible": sum(1 for i in m if i.invisible_copies == i.copies),
            "centre_bbox": centre_bbox(m),
        }
        for k, m in circles.items()
    ]
    og = [
        {
            "layer": k[0],
            "short": k[1],
            "long": k[2],
            "rectangle": k[3],
            "vertices": k[4],
            "count": len(m),
            "copies": sum(i.copies for i in m),
            "invisible": sum(1 for i in m if i.invisible_copies == i.copies),
            "centre_bbox": centre_bbox(m),
        }
        for k, m in outlines.items()
    ]
    cg.sort(key=lambda g: (-g["count"], g["layer"], g["diameter"]))
    og.sort(key=lambda g: (-g["count"], g["layer"], g["short"], g["long"], g["vertices"]))
    for name, groups in (("circle_groups", cg), ("outline_groups", og)):
        if len(groups) > max_groups:
            warnings.append(
                f"geometry truncated: {where} {name} {max_groups} of {len(groups)} returned; "
                f"rerun with --max {len(groups)} to get all of them"
            )
    return cg[:max_groups], og[:max_groups]


def _item_json(i: _Item) -> dict[str, Any]:
    points = None
    truncated = None
    if i.points is not None:
        points = [list(p) for p in i.points[:MAX_POINTS]]
        truncated = len(i.points) > MAX_POINTS
    return {
        "id": i.id,
        "kind": i.kind,
        "layer": i.layer,
        "sheet": i.sheet,
        "space": i.space,
        "centre": list(i.centre),
        "diameter": i.diameter,
        "bbox": None if i.bbox is None else list(i.bbox),
        "short": i.short,
        "long": i.long,
        "angle": i.angle,
        "rectangle": i.rectangle,
        "vertices": i.vertices,
        "points": points,
        "points_truncated": truncated,
        "copies": i.copies,
        "invisible": i.invisible_copies == i.copies,
        "top_handle": i.top_handle,
        "block_path": i.block_path,
    }


def _region_json(
    region: _Region, tol: float, max_groups: int, max_items: int, detail: bool, warnings: list[str]
) -> dict[str, Any]:
    where = f"sheet {region.sheet}" if region.sheet else ("region" if region.bbox else "unassigned")
    cg, og = _group_lists(region, tol, max_groups, warnings, where)
    out: dict[str, Any] = {
        "sheet": region.sheet,
        "bbox": None if region.bbox is None else list(region.bbox),
        "layers": {
            name: {c: int(counts.get(c, 0)) for c in _COUNTERS}
            for name, counts in sorted(region.layers.items())
        },
        "circle_groups": cg,
        "outline_groups": og,
    }
    if detail:
        items = sorted(
            region.items.values(),
            key=lambda i: (i.kind, i.layer, i.diameter or i.long or 0.0, i.centre),
        )
        if len(items) > max_items:
            warnings.append(
                f"geometry truncated: {where} items {max_items} of {len(items)} returned; "
                f"rerun with --max {len(items)} to get all of them"
            )
        out["items"] = [_item_json(i) for i in items[:max_items]]
    return out


def geometry(
    work_dir: Path | str,
    file_rel: str,
    *,
    sheet: list[str] | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    layer: list[str] | None = None,
    detail: bool = False,
    max_rows: int | None = None,
    tol: float | None = None,
    input_dir: Path | str | None = None,
    check_inputs: bool = False,
) -> dict[str, Any]:
    """The geometry document of one drawing (nothing written). Raises ReaderError."""
    return read_geometry(
        work_dir,
        file_rel,
        sheet=sheet,
        bbox=bbox,
        layer=layer,
        detail=detail,
        max_rows=max_rows,
        tol=tol,
        input_dir=input_dir,
        check_inputs=check_inputs,
    ).doc


def read_geometry(
    work_dir: Path | str,
    file_rel: str,
    *,
    sheet: list[str] | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    layer: list[str] | None = None,
    detail: bool = False,
    max_rows: int | None = None,
    tol: float | None = None,
    input_dir: Path | str | None = None,
    check_inputs: bool = False,
    dimensions: bool = False,
) -> GeometryRead:
    """`geometry`, plus the unique items with their full rings and spaces and the loaded file (for the
    tools built on it). `dimensions=True` also keeps each region's DIMENSIONs (`GeometryRead.dims`, any
    layer: the `layer` filter does not apply; the document is the same). Raises ReaderError."""
    if sheet and bbox is not None:
        raise ReaderError(EXIT_USAGE, "give --sheet or --bbox, not both")
    if max_rows is not None and max_rows < 1:
        raise ReaderError(EXIT_USAGE, "--max must be at least 1")
    if tol is not None and not tol > 0:
        raise ReaderError(EXIT_USAGE, "--tol must be greater than 0")
    box = None
    if bbox is not None:
        if len(bbox) != 4:
            raise ReaderError(EXIT_USAGE, "--bbox needs X0 Y0 X1 Y1")
        box = (min(bbox[0], bbox[2]), min(bbox[1], bbox[3]), max(bbox[0], bbox[2]), max(bbox[1], bbox[3]))
    inv = load_inventory(work_dir)
    loaded = load_file(inv, _file_row(inv, file_rel), check_inputs=check_inputs)
    if loaded.skip is not None or loaded.text_index is None:
        raise ReaderError(EXIT_USAGE, f"{file_rel} cannot be read: {loaded.skip}")
    warnings = [f"{file_rel}: {w}" for w in loaded.warnings]
    if sheet:
        if loaded.sheets is None:
            raise ReaderError(EXIT_USAGE, f"--sheet needs the sheets document: {'; '.join(warnings)}")
        ids = [s["sheet_id"] for s in loaded.sheets["sheets"]]
        for wanted in sheet:
            if wanted not in ids:
                raise ReaderError(
                    EXIT_USAGE, f"{file_rel} has no sheet '{wanted}' (sheets: {', '.join(ids) or 'none'})"
                )
    doc = _open(inv, loaded, None if input_dir is None else Path(input_dir).resolve())
    handles_ok = bool(loaded.text_index["file"]["handles_reliable"])
    locator = None if loaded.sheets is None else SheetLocator(loaded.sheets)
    wanted_sheets = set(sheet or ())
    folded = None if not layer else {name.casefold() for name in layer}
    declared = (loaded.row["units"] or {}).get("value")
    declared = None if declared in (None, "unknown") else declared
    answered = _answered_unit(inv, file_rel, warnings)
    if tol is None:
        tol = _default_tol(answered, declared, warnings)
    walker = Walker(doc, handles_ok)
    links = _TextLinks(loaded.text_index["entries"]) if dimensions else None
    dims_by_region: dict[str | None, list[DimRead]] = {}
    regions: dict[str | None, _Region] = {}
    layer_cache: dict[str, tuple[bool, bool]] = {}
    hidden_under: dict[int, bool] = {}  # INSERT serial -> it, or an ancestor, is on a frozen layer
    invisible_under: dict[int, bool] = {}  # INSERT serial -> it, or an ancestor, has the invisible flag
    invisible_total = 0
    ignored: Counter[str] = Counter()
    noted: Counter[str] = Counter()
    for space, layout, is_model in layout_spaces(doc):
        if box is not None and not is_model:
            continue
        for placed in walker.walk(layout, space, _WALKED_WITH_DIMENSIONS if dimensions else _WALKED):
            e = placed.entity
            kind = e.dxftype()
            stored = str(e.dxf.get("layer", "0"))
            name = placed.outer_layer if stored == "0" and placed.outer_layer else stored
            own_invisible = int(e.dxf.get("invisible", 0)) == 1
            invisible = own_invisible or invisible_under.get(placed.owner, False)
            if kind == "INSERT":
                # a frozen INSERT hides everything it draws, whatever the layers inside; an off one hides
                # only the layer-0 content, which already takes its layer
                hidden_under[placed.serial] = (
                    hidden_under.get(placed.owner, False) or _layer_state(doc, layer_cache, name)[1]
                )
                invisible_under[placed.serial] = invisible

                continue
            if kind == "DIMENSION":  # only walked with `dimensions=True`; no layer filter, no counters
                x, y = _world_anchor(e)
                found = SHEET_UNKNOWN if locator is None else locator.locate(space, x, y)
                if box is not None:
                    if x is None or y is None or not _inside(box, x, y):
                        continue
                    dim_key: str | None = "bbox"
                else:
                    dim_key = None if found == SHEET_UNKNOWN else found
                    if wanted_sheets and dim_key not in wanted_sheets:
                        continue
                if hidden_under.get(placed.owner, False) or _is_hidden(doc, layer_cache, name):
                    continue
                if links is not None:
                    dims_by_region.setdefault(dim_key, []).append(
                        _read_dimension(e, placed, layout, is_model, handles_ok, links, (x, y))
                    )
                continue
            if folded is not None and name.casefold() not in folded:
                continue
            item_geometry: dict[str, Any] | None = None
            counter: str | None = _KIND_COUNTER.get(kind)
            point: tuple[float, float] | None
            if kind == "CIRCLE":
                cx, cy = _wcs_xy(e, float(e.dxf.center[0]), float(e.dxf.center[1]), float(e.dxf.center[2]))
                point = (cx, cy)
                item_geometry = {"kind": "circle", "centre": point, "diameter": 2 * float(e.dxf.radius)}
            elif kind == "ARC":
                point = _arc_mid_point(e)
            elif kind == "ELLIPSE":
                point = (float(e.dxf.center[0]), float(e.dxf.center[1]))
                span = (float(e.dxf.end_param) - float(e.dxf.start_param)) % _TAU
                full = span < 1e-9 or _TAU - span < 1e-9
                if abs(float(e.dxf.ratio) - 1.0) <= _CIRCLE_RATIO_TOL:
                    if full:  # a circle that a non-uniform INSERT scale turned into an ellipse
                        item_geometry = {
                            "kind": "circle",
                            "centre": point,
                            "diameter": 2 * float(Vec3(e.dxf.major_axis).magnitude),
                        }
                    else:
                        counter = "arcs"
                else:
                    counter = "ellipses"
            elif kind == "LINE":
                s, t = e.dxf.start, e.dxf.end
                point = ((float(s[0]) + float(t[0])) / 2, (float(s[1]) + float(t[1])) / 2)
            elif kind in ("HATCH", "SPLINE"):
                # ezdxf does not transform a hatch's seed points: the placement is the extents' centre
                extents = _extents(e)
                point = None if extents is None else _centre(extents)
                if point is None:
                    noted[
                        f"{kind} (no {'boundary' if kind == 'HATCH' else 'curve'} extents) counted unplaced"
                    ] += 1
            else:  # LWPOLYLINE, POLYLINE
                parsed = _polyline_points(e)
                if parsed is None:
                    ignored[f"{kind} (not a 2D polyline)"] += 1
                    continue
                pts, closed_flag, bulges = parsed
                if len(pts) < 2:
                    ignored[f"{kind} (fewer than 2 vertices)"] += 1
                    continue
                item_geometry, point = _polyline_geometry(e, pts, closed_flag, bulges, tol, noted)
            # which region: a bbox, a sheet, or (no filter) the sheet the point lies on
            on: str | None = None
            if locator is not None and point is not None:
                found = locator.locate(space, point[0], point[1])
                on = None if found == SHEET_UNKNOWN else found
            if box is not None:
                if point is None or not _inside(box, point[0], point[1]):
                    if point is None:
                        ignored["entity without a position (outside --bbox test)"] += 1
                    continue
                region_key: str | None = "bbox"
            else:
                if wanted_sheets and on not in wanted_sheets:
                    continue
                region_key = on
            region = regions.get(region_key)
            if region is None:
                region = regions[region_key] = _Region(None if region_key == "bbox" else region_key, box)
            counts = region.counter(name)
            if hidden_under.get(placed.owner, False) or _is_hidden(doc, layer_cache, name):
                counts["hidden"] += 1
                continue
            if invisible:
                counts["invisible"] += 1
                invisible_total += 1
            if point is None:
                counts["unplaced"] += 1
                continue
            if item_geometry is None:
                counts[counter or "open_polylines"] += 1
                continue
            _add_item(region, item_geometry, space, name, on, placed, tol, counts, invisible)
    if walker.skipped:
        warnings.append(f"{file_rel}: some INSERTs were not expanded: {dict(sorted(walker.skipped.items()))}")
    for what, n in sorted(ignored.items()):
        warnings.append(f"{file_rel}: {n} {what} ignored")
    if invisible_total:
        warnings.append(
            f"{file_rel}: {invisible_total} entities carry the invisible flag (group 60), mostly hidden "
            "visibility states of dynamic blocks; render does not draw them, geometry counts them: "
            "confirm a counted member with render"
        )
    for what, n in sorted(noted.items()):
        warnings.append(f"{file_rel}: {n} {what}")
    max_groups = DEFAULT_MAX_GROUPS if max_rows is None else max_rows
    max_items = DEFAULT_MAX_ITEMS if max_rows is None else max_rows
    if box is not None:
        order: list[str | None] = ["bbox"]
        regions.setdefault("bbox", _Region(None, box))
    elif sheet:
        order = list(sheet)
        for sid in order:
            regions.setdefault(sid, _Region(sid))
    else:
        known = [s["sheet_id"] for s in loaded.sheets["sheets"]] if loaded.sheets else []
        order = [sid for sid in known if sid in regions]
        if None in regions:
            order.append(None)
    out = {
        "schema_version": SCHEMA_VERSION,
        "kind": "geometry",
        "project_id": inv.doc["project_id"],
        "file": file_rel,
        "query": {
            "sheet": sheet or None,
            "bbox": None if box is None else list(box),
            "layer": layer or None,
            "detail": detail,
            "max": max_rows,
            "tol": tol,
        },
        "units": {
            "declared": declared,
            "answered": answered,
            "converted": False,
        },
        "regions": [_region_json(regions[k], tol, max_groups, max_items, detail, warnings) for k in order],
        "warnings": warnings,
    }
    problems = validate("geometry", out)
    if problems:
        raise ReaderError(EXIT_INVALID, f"internal error: output is invalid: {_details(problems)}")
    return GeometryRead(
        doc=out,
        regions=regions,
        loaded=loaded,
        dims=dims_by_region,
        dims_unlinked=0 if links is None else links.missing,
    )


def _world_anchor(dim: Any) -> tuple[float | None, float | None]:
    """Where a dimension sits for the sheet test, in world coordinates: its text midpoint (an OCS point, so a
    mirrored copy needs its extrusion), else its definition point (already world)."""
    mid = dim.dxf.get("text_midpoint")
    if mid is not None:
        point = OCS(dim.dxf.get("extrusion", (0.0, 0.0, 1.0))).to_wcs(Vec3(mid))
        return float(point.x), float(point.y)
    point = dim.dxf.get("defpoint")
    if point is not None:
        return float(point[0]), float(point[1])
    return None, None


def _copy_direction(definition: Any, copy: Any) -> tuple[float, float] | None:
    """The unit direction of a block copy of a linear dimension whose definition stores no angle (group 50).

    ezdxf transforms the angle only when it exists, so the copy would still measure along x. The INSERT is a
    linear map of the plane: solve it from the definition's vectors (defpoint to defpoint2 and to defpoint3)
    and the copy's, apply it to the definition's direction (1, 0 in its OCS), and normalise. None when those
    two vectors are collinear (the map is not determined) or the result is null: the caller keeps the
    direction the copy stores."""
    points = [(e.dxf.get(n)) for e in (definition, copy) for n in ("defpoint", "defpoint2", "defpoint3")]
    if any(p is None for p in points):
        return None
    (o, a, b), (o2, a2, b2) = (
        [(float(p[0]), float(p[1])) for p in points[:3]],
        [(float(p[0]), float(p[1])) for p in points[3:]],
    )
    va, vb = (a[0] - o[0], a[1] - o[1]), (b[0] - o[0], b[1] - o[1])
    ca, cb = (a2[0] - o2[0], a2[1] - o2[1]), (b2[0] - o2[0], b2[1] - o2[1])
    det = va[0] * vb[1] - va[1] * vb[0]
    if abs(det) <= _COLLINEAR_REL * math.hypot(*va) * math.hypot(*vb):
        return None
    way = OCS(definition.dxf.get("extrusion", (0.0, 0.0, 1.0))).to_wcs(Vec3(1, 0, 0))
    # coordinates of the direction in the basis (va, vb), then the same combination of the copy's vectors
    s = (way.x * vb[1] - way.y * vb[0]) / det
    t = (va[0] * way.y - va[1] * way.x) / det
    x, y = s * ca[0] + t * cb[0], s * ca[1] + t * cb[1]
    length = math.hypot(x, y)
    return None if length == 0 else (x / length, y / length)


def _same_vector_up_to_sign(definition: Any, p1: Any, p2: Any) -> bool:
    """True when the copy's p1 to p2 equals plus or minus the definition's (relative `_SCALED_REL_TOL`):
    the only copies of a collinear definition whose stored direction is known to be right (not turned)."""
    d2, d3 = definition.dxf.get("defpoint2"), definition.dxf.get("defpoint3")
    if d2 is None or d3 is None or p1 is None or p2 is None:
        return False
    want = (float(d3[0]) - float(d2[0]), float(d3[1]) - float(d2[1]))
    got = (p2[0] - p1[0], p2[1] - p1[1])
    tol = _SCALED_REL_TOL * max(math.hypot(*want), 1e-12)
    return (
        min(math.hypot(got[0] - want[0], got[1] - want[1]), math.hypot(got[0] + want[0], got[1] + want[1]))
        <= tol
    )


def _read_dimension(
    e: Any,
    placed: Any,
    layout: Any,
    is_model: bool,
    handles_ok: bool,
    links: _TextLinks,
    at: tuple[float | None, float | None],
) -> DimRead:
    """The `DimRead` of one placed DIMENSION: what it measures and prints (by the definition for block
    content), the text link and the font gate as `harness dimensions` does, and where it measures."""
    block_path = placed.block_path
    target = _definition(e) if block_path else e
    row = measure_dimension(
        target,
        layout=str(layout.name),
        is_model=is_model and not block_path,
        in_block=bool(block_path),
        handles_ok=handles_ok,
    )
    if block_path:
        row["handle"] = None  # a placement of the definition, not the definition itself
    row["text_entry"] = links.link(placed.space, block_path, row["text"], at)
    _gate_override(row)
    dimtype = int(e.dxf.get("dimtype", 0)) & 7
    linear = dimtype in (0, 1)
    p1 = p2 = u = None
    unrebuilt = False  # a block copy whose direction could not be rebuilt: it keeps the stored (1, 0)
    if linear:
        d2, d3 = e.dxf.get("defpoint2"), e.dxf.get("defpoint3")
        if d2 is not None and d3 is not None:
            p1, p2 = (float(d2[0]), float(d2[1])), (float(d3[0]), float(d3[1]))
            if dimtype == 0:
                ang = math.radians(float(e.dxf.get("angle", 0.0)))  # in the dimension's OCS
                way = OCS(e.dxf.get("extrusion", (0.0, 0.0, 1.0))).to_wcs(
                    Vec3(math.cos(ang), math.sin(ang), 0)
                )
                u = (float(way.x), float(way.y))
                if block_path and not target.dxf.hasattr("angle"):
                    rebuilt = _copy_direction(target, e)  # a copy keeps no angle the definition lacks
                    if rebuilt is not None:
                        u = rebuilt
                    else:
                        unrebuilt = True
            else:
                length = math.dist(p1, p2)
                u = None if length == 0 else ((p2[0] - p1[0]) / length, (p2[1] - p1[1]) / length)
    factor: float | None
    try:
        factor = float(target.override().get("dimlfac", 1.0))
    except (DXFError, ValueError, TypeError):
        factor = None
    if factor is not None and not math.isfinite(factor):
        factor = None
    copy_differs = False
    if block_path:  # the copy must measure, in the world, what its definition measures (a scaled INSERT: no)
        measured = row["measured"]
        copy = None
        if p1 is not None and p2 is not None:
            copy = abs((p2[0] - p1[0]) * u[0] + (p2[1] - p1[1]) * u[1]) if u is not None else None
        copy_differs = measured is not None and (
            copy is None or abs(copy - measured) > _SCALED_REL_TOL * max(abs(measured), 1e-12)
        )
        if unrebuilt and not copy_differs:
            copy_differs = not _same_vector_up_to_sign(target, p1, p2)
    return DimRead(placed.space, linear, p1, p2, u, row, factor, copy_differs)


def _add_item(
    region: _Region,
    g: dict[str, Any],
    space: str,
    layer: str,
    sheet: str | None,
    placed: Any,
    tol: float,
    counts: Counter[str],
    invisible: bool,
) -> None:
    if g["kind"] == "circle":
        cx, cy = g["centre"]
        geo: Any = (_cell(cx, tol), _cell(cy, tol), _cell(g["diameter"], tol))
    else:
        geo = tuple(
            sorted(
                {
                    (_cell(x, tol), _cell(y, tol), round(b, 3) + 0.0)
                    for (x, y), b in zip(g["ring"], g["bulges"], strict=True)
                }
            )
        )
    key = (space, g["kind"], layer, geo)
    found = region.items.get(key)
    if found is not None:
        found.copies += 1
        found.invisible_copies += int(invisible)
        counts["copies_collapsed"] += 1
        return
    centre = (_r3(g["centre"][0]), _r3(g["centre"][1]))
    item = _Item(
        id=_item_id(space, g["kind"], layer, geo),
        kind=g["kind"],
        layer=layer,
        sheet=sheet,
        centre=centre,
        top_handle=placed.top_handle,
        block_path=list(placed.block_path),
        invisible_copies=int(invisible),
        space=space,
    )
    if g["kind"] == "circle":
        item.diameter = _r3(g["diameter"])
        counts["circles"] += 1
    else:
        ring = g["ring"]
        x0, y0, x1, y1 = g["box"]
        item.bbox = (_r3(x0), _r3(y0), _r3(x1), _r3(y1))
        item.vertices = len(ring)
        item.ring = g.get("flat") or list(ring)
        item.ring_chords = bool(g["bulge"]) and "flat" not in g
        rect = _rectangle(ring, g["bulge"], tol)
        item.rectangle = rect is not None
        if rect is not None:
            item.short, item.long, item.angle = _r3(rect[0]), _r3(rect[1]), _r3(rect[2])
        else:
            sides = sorted((item.bbox[2] - item.bbox[0], item.bbox[3] - item.bbox[1]))
            item.short, item.long = _r3(sides[0]), _r3(sides[1])
            item.points = [(_r3(x), _r3(y)) for x, y in ring]
        counts["outlines"] += 1
    region.items[key] = item


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "work_dir", help="the --out folder of `harness intake` (after `harness read-structure`)"
    )
    parser.add_argument("file", help="input-relative path of the drawing, as in inventory.json")
    where = parser.add_mutually_exclusive_group()
    where.add_argument(
        "--sheet",
        nargs="+",
        action="extend",
        metavar="ID",
        help="only these detector sheet ids, e.g. model#05 model#06 (repeatable)",
    )
    where.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("X0", "Y0", "X1", "Y1"),
        help="only items whose centre is inside this model-space region",
    )
    parser.add_argument(
        "--layer",
        nargs="+",
        action="extend",
        metavar="L",
        help="only these effective layers (case-insensitive)",
    )
    parser.add_argument("--detail", action="store_true", help="also list every unique item")
    parser.add_argument(
        "--max",
        type=int,
        default=None,
        help=f"groups per sheet (default {DEFAULT_MAX_GROUPS}); with --detail items ({DEFAULT_MAX_ITEMS})",
    )
    parser.add_argument(
        "--tol",
        type=float,
        default=None,
        help="dedupe and rounding tolerance in drawing units (default: 1 mm of the answered, else the "
        "declared unit; 1.0 with a warning when neither is known)",
    )
    parser.add_argument(
        "--input-dir", help="the intake input folder (needed when the drawing is a native DXF file)"
    )
    add_save_argument(parser)


def run(args: argparse.Namespace) -> int:
    started = time.monotonic()
    try:
        sha_before = sha_before_save(args.work_dir, args.file) if args.save else None
        doc = geometry(
            Path(args.work_dir),
            args.file,
            sheet=args.sheet,
            bbox=None if args.bbox is None else (args.bbox[0], args.bbox[1], args.bbox[2], args.bbox[3]),
            layer=args.layer,
            detail=args.detail,
            max_rows=args.max,
            tol=args.tol,
            input_dir=Path(args.input_dir) if args.input_dir else None,
        )
    except ReaderError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    for warning in doc["warnings"]:
        if warning.startswith("geometry truncated"):
            print(warning, file=sys.stderr)
    print(f"geometry: {time.monotonic() - started:.1f} s elapsed", file=sys.stderr)
    text = json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.save:
        try:
            saved = save_document(args.work_dir, doc, text, sha_before)
        except ReaderError as exc:
            print(str(exc), file=sys.stderr)
            return exc.exit_code
        print(f"saved: {saved}", file=sys.stderr)
    sys.stdout.write(text)
    return 0
