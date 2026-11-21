"""contents: `harness contents`, what each member outline of one plan sheet holds.

Read-only (no work-folder lock, nothing written) unless `--save` is given: then the document is also saved
in `<work>/geometry/` (saved_evidence.py; the work lock is held only for the write).
Output: schema `contents` on stdout, elapsed time on stderr.

Built on `geometry.read_geometry` (T21): one call for one sheet and the outline and circle layers gives the
unique closed outlines and circles (the walk, INSERT expansion, WCS conversion of mirrored INSERTs, the
effective layer, hidden layers, dedupe and the `G-` ids are all T21's), with the full drawn ring of each
outline (bulges flattened, no vertex cap) and its space. This module adds the relations.

Units: `--tol` defaults to geometry's (1 mm of the answered, else the declared unit); `--max-long` (20 m) and
`--mark-radius` (3 m) are converted by the same unit. In an unknown unit the millimetre values are used, with
a warning. `query` reports the values used.

Outlines: closed outlines on `--outline-layer` whose centre is on the sheet; those whose long side exceeds
`--max-long` (a frame) are dropped and listed in a warning. The space of the outlines is the space most of
them are drawn in; outlines, circles and mark texts of another space are not used and are counted in a
warning. Containment uses the drawn ring. An outline that holds the centre of another one (a column stub in
its cap) is listed in a warning as nested.

Symbols: circles on `--circle-layer`, merged when their centres lie within `--tol` of each other (the first
centre is kept): concentric circles are one symbol, and the diameters seen are reported per group. A symbol is
inside an outline when its centre is in the ring (a point on the boundary, within `--tol`, counts as inside).
A symbol inside two outlines counts in both and is listed in a warning. Circles on an outline layer (a round
cap drawn as a donut) are not used and are counted in a warning. Outlines and symbols that carry the invisible
flag (group 60) are used like the others: each outline reports `invisible`, a summary row counts them, and one
warning counts the outlines and symbols concerned.

Marks (only with `--marks REGEX`): the printed text entries of the sheet whose stripped display_text fully
matches the regex. An entry whose meaning the legacy-font gate blocks is not used (counted in a warning), nor
is one without a position; an entry that contains a match without fully matching is counted. A mark is
measured from the MIDDLE of its text: the centre of `sheets.text_box` (estimated width 0.7 x height x
characters; it handles every TEXT alignment, every MTEXT attachment, rotation and several lines; a text
midpoint or a block position is the point itself). The mark goes to the innermost outline that holds that
point (a point on an edge, within `--tol`, is held: the ring is closed); if two outlines hold it and neither
holds the other it is ambiguous. A point inside no outline goes to the ONE nearest outline within
`--mark-radius`, an outline held by another outline in range (a column stub in its cap) not competing; when
the runner-up is nearly as close (`d2 - d1 <= max(tol, 0.25 x d2)`) it goes to neither and is listed in
`marks_ambiguous`; one with no outline in the radius is in `marks_unassigned`. A mark is never copied to an
outline that holds none: a summary row
reports the marks seen (`marks_seen`, text to the number of outlines holding it) and how many outlines are
`unmarked`. A mark seen on two summary rows, or an outline with different marks, is named in a warning.
A mark of a MULTILEADER is measured from its text, not from the arrow (the text index has no leader vertices).

Axes: every family of every grid group of the sheet in `structure/<file>.grids.json` whose bbox strictly
contains the outline centre (same space): the axis nearest to the centre measured along the family normal,
the position of an axis taken at its line midpoint. The entry carries the group and family ids, the label of
the nearest LABELLED axis, the signed offset (centre minus axis) and, when an unlabelled axis is nearer, its
offset; the unlabelled axes are the family's axes without a label and its `unlabelled_lines` (lines the grid
detector found without a bubble). The lines answer only the nearest unlabelled offset: they never set the
label or the offset, which come from the family's `axes`. An outline in no group gets no axes and a warning;
one in several groups gets one entry per group.

Printed dimensions (only with `--dims`): every linear DIMENSION of the sheet (any layer; hidden layers
dropped as in `geometry`) that measures along a side of a rectangular outline within 1 degree and lies within
`--mark-radius` of it across that side, attached to the outline it belongs to. The reach is the resolved
`--mark-radius`. A dimension of dimtype 0 or 1 attaches `edges` when its two ends are on the two edges across
that side (within `--tol`), or `centred` when neither end is on an edge, its middle is the middle of the side,
and the longer of dimension and side is at most twice the shorter (copied linework keeps the member centre
while its dimension keeps the old value); a `centred` candidate whose two ends both lie, along the dimension,
on the centres of symbols inside that outline is a pile spacing and is not attached (without the pile layer
as `--circle-layer` it may still attach `centred`). An axis-to-edge or partial dimension never attaches.
`edges` wins over `centred`, then the smallest gap; a runner-up of the same kind within `--tol` of the gap
makes the dimension ambiguous (counted, attached to none). A dimension attaches to at most one outline. The
printed number `P` is the typed number of an override text (a text the legacy-font gate blocks is unusable)
or the measured length times DIMLFAC; `agrees` is |P - side x DIMLFAC| <= tol x DIMLFAC. A dimension that is
not linear, has no readable number or DIMLFAC, or sits in a scaled INSERT (whose definition it measures), or
in a rotated INSERT whose dimension stores no angle (group 50) and whose definition points lie on one line,
is not used. Each outline lists `printed_dims`, a summary row counts its outlines `agree` / `disagree` /
`none`, and a warning names the outlines that disagree. A dimension of a column stub centred on its cap
attaches to the cap unless the stub's layer is passed as an outline layer. Without `--dims` nothing of
this is read or written.

Values are in the drawing's units as stored, never converted. Exit codes: 0 ok, 1 inconsistent work folder or
invalid output, 2 usage, 3 the DXF cannot be read.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

from tekla_harness.dimensions import EXIT_ENV
from tekla_harness.geometry import _UNIT_TOL, DimRead, _cell, _r3, _snap, read_geometry
from tekla_harness.saved_evidence import add_save_argument, save_document, sha_before_save
from tekla_harness.schemas import validate
from tekla_harness.sheet_text import (
    EXIT_INVALID,
    EXIT_USAGE,
    STRUCTURE_DIR,
    ReaderError,
    _details,
    _printed_scope,
    _sheet_entries,
    read_json,
)
from tekla_harness.sheets import box_center, text_box
from tekla_harness.text_gate import meaning_block_reason

COMMAND = "contents"
HELP = (
    "what each member outline of a plan sheet holds: symbols inside, mark, grid position (read-only; "
    "--save keeps the document)"
)
_ = EXIT_ENV  # re-exported: the documented exit code 3 comes from the DXF open inside `geometry`
DEFAULT_MAX_LONG_MM = 20000.0  # 20 m
DEFAULT_MARK_RADIUS_MM = 3000.0  # 3 m
DEFAULT_MAX_OUTLINES = 500
LISTED = 10  # ids or centres named in a warning
TIE_RATIO = 0.25  # a runner-up this close (relative to its distance) makes a mark ambiguous
PARALLEL = math.sin(math.radians(1.0))  # a dimension measures along a side within 1 degree
CENTRED_RATIO = 2.0  # a centred dimension and the side differ at most by this factor

Point = tuple[float, float]
Axis = tuple[str | None, float]
Family = tuple[str, Point, list[Axis], list[float]]  # id, normal, axes, unlabelled line positions


def _segment_distance(p: Point, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def _boundary_distance(p: Point, poly: list[Point]) -> float:
    return min(_segment_distance(p, poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly)))


def _strictly_inside(p: Point, poly: list[Point]) -> bool:
    inside = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 > p[1]) != (y2 > p[1]) and p[0] < (x2 - x1) * (p[1] - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _contains(poly: list[Point], p: Point, tol: float) -> bool:
    """Inside the polygon, or on its boundary within `tol`."""
    return _strictly_inside(p, poly) or _boundary_distance(p, poly) <= tol


def _bounds(poly: list[Point]) -> tuple[float, float, float, float]:
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def _area(poly: list[Point]) -> float:
    twice = sum(
        poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
        for i in range(len(poly))
    )
    return abs(twice) / 2


def _in_box(box: tuple[float, float, float, float], p: Point, pad: float = 0.0) -> bool:
    """The box grown by `pad` on every side, edges included (a prefilter: the polygon test decides)."""
    return box[0] - pad <= p[0] <= box[2] + pad and box[1] - pad <= p[1] <= box[3] + pad


def _grid_groups(work: Path, file_rel: str, sheet: str, warnings: list[str]) -> list[dict[str, Any]]:
    """The grid groups of the sheet: id, space, bbox and families (id, normal, axes as label and position
    along the normal, taken at the line midpoint) and lines (the positions of its `unlabelled_lines`, which
    feed only the nearest unlabelled offset)."""
    rel = f"{STRUCTURE_DIR}/{file_rel}.grids.json"
    path = work / rel
    if not path.is_file():
        warnings.append(f"{rel} is missing: run `harness read-structure` (no grid axes for sheet {sheet})")
        return []
    doc = read_json(path, rel)
    groups: list[dict[str, Any]] = []
    try:
        for group in doc["groups"]:
            if group["sheet"] != sheet:
                continue
            families: list[Family] = []
            for fam in group["families"]:
                nx, ny = (float(v) for v in fam["normal"])
                axes: list[Axis] = []
                for ax in fam["axes"]:
                    sx, sy = (float(v) for v in ax["line"]["start"])
                    ex, ey = (float(v) for v in ax["line"]["end"])
                    label = ax.get("label")
                    axes.append(
                        (None if not label else str(label["value"]), nx * (sx + ex) / 2 + ny * (sy + ey) / 2)
                    )
                # lines the grid detector found without a label sit beside `axes`, not in it
                lines: list[float] = []
                for line in fam["unlabelled_lines"]:
                    (sx, sy), (ex, ey) = line["line"]["start"], line["line"]["end"]
                    lines.append(nx * (float(sx) + float(ex)) / 2 + ny * (float(sy) + float(ey)) / 2)
                families.append((str(fam["family_id"]), (nx, ny), axes, lines))
            x0, y0, x1, y1 = (float(v) for v in group["bbox"])
            groups.append(
                {
                    "group_id": str(group["group_id"]),
                    "space": str(group["space"]),
                    "bbox": (x0, y0, x1, y1),
                    "families": families,
                }
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise ReaderError(EXIT_INVALID, f"{rel} has an unexpected shape ({exc!r})") from exc
    if not groups:
        warnings.append(f"sheet {sheet} has no grid group in {rel}: no grid axes reported")
    return sorted(groups, key=lambda g: g["group_id"])


def _nearest_axis(here: float, axes: list[Axis], tol: float) -> Axis | None:
    """The nearest axis; axes equally near (within tol) give the lower position."""
    if not axes:
        return None
    best = min(abs(here - a[1]) for a in axes)
    return min((a for a in axes if abs(here - a[1]) - best <= tol), key=lambda a: a[1])


def _family_axes(
    here: float, axes: list[Axis], lines: list[float], tol: float
) -> tuple[str | None, float, float | None] | None:
    """(label, offset, nearest unlabelled offset) of one family at the position `here` along its normal.
    `label` and `offset` come from `axes` only; the unlabelled `lines` join the unlabelled candidates of the
    nearest unlabelled offset, and only when the family has a labelled axis."""
    labelled = _nearest_axis(here, [a for a in axes if a[0] is not None], tol)
    unlabelled = _nearest_axis(here, [a for a in axes if a[0] is None], tol)
    if labelled is None:
        return None if unlabelled is None else (None, round(here - unlabelled[1], 3) + 0.0, None)
    unlabelled = _nearest_axis(here, [a for a in axes if a[0] is None] + [(None, p) for p in lines], tol)
    nearer = unlabelled is not None and abs(here - unlabelled[1]) < abs(here - labelled[1])
    return (
        labelled[0],
        round(here - labelled[1], 3) + 0.0,
        round(here - unlabelled[1], 3) + 0.0 if nearer and unlabelled is not None else None,
    )


def _by_text(marks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(marks, key=lambda c: (c["text"], c["entry_id"]))


def _mark_json(c: dict[str, Any]) -> dict[str, Any]:
    return {"text": c["text"], "entry_id": c["entry_id"], "position": list(c["at"])}


def _listed(names: list[str]) -> str:
    more = f" (+{len(names) - LISTED} more)" if len(names) > LISTED else ""
    return ", ".join(names[:LISTED]) + more


def _printed_value(d: DimRead) -> float | None:
    """The number a dimension prints (the typed number of an override, else the measured length times
    DIMLFAC), or None when it prints no usable one: an error, a value not compared, a text that is no
    number, a suppressed text, a DIMLFAC that is not positive, a scaled INSERT, or a rotated one whose
    dimension stores no angle (group 50) and whose definition points lie on one line."""
    row = d.row
    if d.copy_differs or d.factor is None or d.factor <= 0 or d.u is None or d.p1 is None or d.p2 is None:
        return None
    if row["status"] in ("error", "not_compared", "not_numeric"):
        return None
    if row["text_rule"] == "override":
        return row["override_value"]  # status ok or override_differs: a number
    if row["text_rule"] in ("measured", "measured_with_text") and row["measured"] is not None:
        return float(row["measured"]) * d.factor
    return None


def _attach_dims(
    dims: list[DimRead],
    kept: list[Any],
    polys: list[list[Point]],
    space: str | None,
    tol: float,
    reach: float,
    symbols: list[list[Point]] | None = None,
) -> tuple[dict[int, list[dict[str, Any]]], dict[str, int]]:
    """Attach each usable linear dimension to the rectangular outline it dimensions (see the module
    docstring): outline index to its `printed_dim` rows, and the counts of `dims`. `symbols`: the symbol
    centres inside each outline (same index as `kept`); a `centred` candidate whose two ends both lie on
    the projection of such a centre is a pile spacing and is dropped."""
    counts = {"on_sheet": len(dims), "attached": 0, "ambiguous": 0, "unusable": 0, "not_linear": 0}
    attached: dict[int, list[dict[str, Any]]] = {}
    rect = [i for i, item in enumerate(kept) if item.rectangle]
    for d in dims:
        if not d.linear:
            counts["not_linear"] += 1
            continue
        printed = _printed_value(d)
        if printed is None or d.u is None or d.p1 is None or d.p2 is None:
            counts["unusable"] += 1
            continue
        if d.space != space:
            continue
        ux, uy = d.u
        a, b = sorted((d.p1[0] * ux + d.p1[1] * uy, d.p2[0] * ux + d.p2[1] * uy))
        found: list[
            tuple[int, float, int, str, float]
        ] = []  # kind (0 edges, 1 centred), gap, outline, side, S
        for oi in rect:
            item = kept[oi]
            angle = math.radians(item.angle or 0.0)
            along = abs(ux * math.sin(angle) - uy * math.cos(angle))  # |u x long direction|
            across = abs(ux * math.cos(angle) + uy * math.sin(angle))  # |u . long direction|
            if along <= PARALLEL:
                side, size = "long", item.long or 0.0
            elif across <= PARALLEL:
                side, size = "short", item.short or 0.0
            else:
                continue
            lo = min(x * ux + y * uy for x, y in polys[oi])
            hi = max(x * ux + y * uy for x, y in polys[oi])
            ns = [-x * uy + y * ux for x, y in polys[oi]]
            gap = max(
                max(min(ns) - v, v - max(ns), 0.0)
                for v in (-d.p1[0] * uy + d.p1[1] * ux, -d.p2[0] * uy + d.p2[1] * ux)
            )
            if gap > reach:
                continue
            if abs(a - lo) <= tol and abs(b - hi) <= tol:
                found.append((0, gap, oi, side, size))
                continue
            on_edge = any(abs(end - edge) <= tol for end in (a, b) for edge in (lo, hi))
            length = b - a
            along_symbols = [x * ux + y * uy for x, y in symbols[oi]] if symbols else []
            spacing = all(any(abs(end - at) <= tol for at in along_symbols) for end in (a, b))
            if (
                not on_edge
                and not spacing
                and abs((a + b) / 2 - (lo + hi) / 2) <= tol
                and max(length, size) <= CENTRED_RATIO * min(length, size)
            ):
                found.append((1, gap, oi, side, size))
        if not found:
            continue
        found.sort(key=lambda c: (c[0], c[1], c[2]))
        best = found[0]
        if any(c[0] == best[0] and c[1] - best[1] <= tol for c in found[1:]):
            counts["ambiguous"] += 1
            continue
        kind, _, oi, side, size = best
        link = d.row.get("text_entry")
        factor = d.factor or 1.0
        counts["attached"] += 1
        attached.setdefault(oi, []).append(
            {
                "handle": d.row["handle"],
                "entry_id": None if link is None else link["entry_id"],
                "text": d.row["text"],
                "printed": _r3(printed),
                "side": side,
                "how": "edges" if kind == 0 else "centred",
                "agrees": abs(printed - size * factor) <= tol * factor,
            }
        )
    for rows in attached.values():
        rows.sort(key=lambda r: (r["side"], r["printed"], r["how"], r["handle"] or "", r["entry_id"] or ""))
    return attached, counts


def contents(
    work_dir: Path | str,
    file_rel: str,
    *,
    sheet: str,
    outline_layers: list[str],
    circle_layers: list[str],
    max_long: float | None = None,
    marks: str | None = None,
    mark_radius: float | None = None,
    detail: bool = False,
    max_rows: int | None = None,
    tol: float | None = None,
    input_dir: Path | str | None = None,
    check_inputs: bool = False,
    dims: bool = False,
) -> dict[str, Any]:
    """The contents document of one sheet (nothing written). `dims`: attach the printed dimensions to the
    outlines (module docstring). Raises ReaderError."""
    if not outline_layers or not circle_layers:
        raise ReaderError(EXIT_USAGE, "give at least one --outline-layer and one --circle-layer")
    if max_long is not None and not max_long > 0:
        raise ReaderError(EXIT_USAGE, "--max-long must be greater than 0")
    if mark_radius is not None and mark_radius < 0:
        raise ReaderError(EXIT_USAGE, "--mark-radius must not be negative")
    if max_rows is not None and max_rows < 1:
        raise ReaderError(EXIT_USAGE, "--max must be at least 1")
    if tol is not None and not tol > 0:
        raise ReaderError(EXIT_USAGE, "--tol must be greater than 0")
    pattern = None
    if marks is not None:
        try:
            pattern = re.compile(marks)
        except re.error as exc:
            raise ReaderError(EXIT_USAGE, f"--marks is not a regular expression: {exc}") from exc
    given_tol = tol
    read = read_geometry(
        work_dir,
        file_rel,
        sheet=[sheet],
        layer=[*outline_layers, *circle_layers],
        max_rows=10**9,
        tol=tol,
        input_dir=input_dir,
        check_inputs=check_inputs,
        dimensions=dims,
    )
    geo = read.doc
    warnings: list[str] = list(geo["warnings"])
    tol = float(geo["query"]["tol"])
    unit = next((u for u in (geo["units"]["answered"], geo["units"]["declared"]) if u in _UNIT_TOL), None)
    per_mm = 1.0 if unit is None else _UNIT_TOL[unit]
    if unit is None and None in (given_tol, max_long, mark_radius):
        warnings.append("contents: mm defaults assumed in unknown units; pass --tol/--max-long/--mark-radius")
    if max_long is None:
        max_long = DEFAULT_MAX_LONG_MM * per_mm
    if mark_radius is None:
        mark_radius = DEFAULT_MARK_RADIUS_MM * per_mm
    region = read.regions.get(sheet)
    items = [] if region is None else list(region.items.values())
    outline_set = {n.casefold() for n in outline_layers}
    circle_set = {n.casefold() for n in circle_layers}

    # outlines
    raw = [i for i in items if i.kind == "outline" and i.layer.casefold() in outline_set]
    kept = [i for i in raw if (i.long or 0.0) <= max_long]
    dropped = [i for i in raw if (i.long or 0.0) > max_long]
    if dropped:
        warnings.append(
            f"{len(dropped)} outline(s) longer than --max-long {max_long:g} dropped (frames): "
            + _listed([f"{i.id} ({i.long:g})" for i in dropped])
        )
    spaces = Counter(i.space for i in kept)
    space = min(spaces, key=lambda name: (-spaces[name], name)) if spaces else None
    other_outlines = [i for i in kept if i.space != space]
    kept = [i for i in kept if i.space == space]
    kept.sort(key=lambda i: (i.layer, i.short or 0.0, i.long or 0.0, i.centre[1], i.centre[0]))
    polys: list[list[Point]] = [list(i.ring or []) for i in kept]
    boxes = [_bounds(p) for p in polys]
    areas = [_area(p) for p in polys]
    chords = [i.id for i in kept if i.ring_chords]
    if chords:
        warnings.append(
            f"{len(chords)} outline(s) with arcs that could not be flattened (chords used): {_listed(chords)}"
        )
    holds: list[set[int]] = [set() for _ in kept]  # per outline: the outlines whose centre it holds
    for a in range(len(kept)):
        for b in range(len(kept)):
            if (
                a != b
                and areas[b] < areas[a]
                and _in_box(boxes[a], kept[b].centre)
                and _strictly_inside(kept[b].centre, polys[a])
            ):
                holds[a].add(b)
    nested = [f"{kept[a].id} holds {kept[b].id}" for a in range(len(kept)) for b in sorted(holds[a])]
    if nested:
        warnings.append(
            f"{len(nested)} nested outline(s) (a mark inside both goes to the inner one): {_listed(nested)}"
        )

    # symbols: circles merged when their centres lie within tol
    circles = [i for i in items if i.kind == "circle" and i.layer.casefold() in circle_set]
    on_outlines = [i for i in items if i.kind == "circle" and i.layer.casefold() in outline_set - circle_set]
    if on_outlines:
        warnings.append(f"{len(on_outlines)} circle(s) on outline layers not used")
    other_circles: list[Any] = []
    if space is not None:  # no outline kept: no space to compare with
        other_circles = [i for i in circles if i.space != space]
        circles = [i for i in circles if i.space == space]
    if other_outlines or other_circles:
        warnings.append(
            f"{len(other_outlines)} outline(s) and {len(other_circles)} circle(s) in other spaces "
            f"than {space} not used"
        )
    syms: list[dict[str, Any]] = []
    cells: dict[tuple[int, int], list[int]] = {}
    for c in sorted(circles, key=lambda i: (i.centre[0], i.centre[1], i.diameter or 0.0)):
        cx, cy = c.centre
        ci, cj = _cell(cx, tol), _cell(cy, tol)
        near = [
            (math.hypot(cx - syms[k]["centre"][0], cy - syms[k]["centre"][1]), k)
            for di in (-1, 0, 1)
            for dj in (-1, 0, 1)
            for k in cells.get((ci + di, cj + dj), ())
        ]
        near = [n for n in near if n[0] <= tol]
        if near:
            sym = syms[min(near)[1]]
        else:
            sym = {"centre": (cx, cy), "diameters": set(), "invisible": True}
            cells.setdefault((ci, cj), []).append(len(syms))
            syms.append(sym)
        sym["diameters"].add(_snap(c.diameter or 0.0, tol))
        sym["invisible"] = sym["invisible"] and c.invisible_copies == c.copies
    holders: list[list[int]] = [[] for _ in syms]  # per symbol: the outlines it lies in
    inside_of: list[list[int]] = [[] for _ in kept]
    for si, sym in enumerate(syms):
        for oi, (poly, box) in enumerate(zip(polys, boxes, strict=True)):
            if _in_box(box, sym["centre"], tol) and _contains(poly, sym["centre"], tol):
                holders[si].append(oi)
                inside_of[oi].append(si)
    shared = [si for si, h in enumerate(holders) if len(h) > 1]
    if shared:
        named = [f"({syms[si]['centre'][0]:.3f}, {syms[si]['centre'][1]:.3f})" for si in shared]
        warnings.append(
            f"{len(shared)} symbol(s) inside more than one outline, counted in each: {_listed(named)}"
        )

    hidden_outlines = sum(1 for i in kept if i.invisible_copies == i.copies)
    hidden_symbols = sum(1 for s in syms if s["invisible"])
    if hidden_outlines or hidden_symbols:
        warnings.append(
            f"{hidden_outlines} outline(s) and {hidden_symbols} symbol(s) used carry the invisible flag "
            "(group 60): they are in the file but not drawn"
        )

    # marks
    candidates: list[dict[str, Any]] = []
    if pattern is not None:
        loaded = read.loaded
        sheet_row = next(s for s in loaded.sheets["sheets"] if s["sheet_id"] == sheet)
        entries = _printed_scope(_sheet_entries(loaded, sheet_row), False)
        blocked = partial = no_position = elsewhere = 0
        for e in entries:
            text = e["display_text"].strip()
            if not pattern.fullmatch(text):
                partial += pattern.search(text) is not None
                continue
            if meaning_block_reason(e) is not None:
                blocked += 1
                continue
            x, y = e["position"]["x"], e["position"]["y"]
            if x is None or y is None:
                no_position += 1
                continue
            if space is not None and e.get("space") != space:
                elsewhere += 1
                continue
            box = text_box(e)
            if box is None:  # unreachable: x and y are set
                raise ReaderError(EXIT_INVALID, f"text entry {e['id']} has a position but no text box")
            candidates.append(
                {"text": text, "entry_id": e["id"], "at": (float(x), float(y)), "middle": box_center(box)}
            )
        if blocked:
            warnings.append(f"{blocked} matching text(s) not used: the legacy-font gate blocks their meaning")
        if partial:
            warnings.append(f"{partial} text(s) contain a mark but do not fully match it (not used)")
        if no_position:
            warnings.append(f"{no_position} matching text(s) have no position (not used)")
        if elsewhere:
            warnings.append(f"{elsewhere} mark text(s) in other spaces than {space} not used")

    assigned: dict[int, list[dict[str, Any]]] = {}
    ambiguous: list[dict[str, Any]] = []
    unassigned: list[dict[str, Any]] = []

    def give(c: dict[str, Any], oi: int, distance: float) -> None:
        assigned.setdefault(oi, []).append(
            {"text": c["text"], "entry_id": c["entry_id"], "distance": distance}
        )

    for c in candidates:
        p = c["middle"]
        holding = [
            oi for oi in range(len(kept)) if _in_box(boxes[oi], p, tol) and _contains(polys[oi], p, tol)
        ]
        if holding:
            inner = [oi for oi in holding if all(oi in holds[o] for o in holding if o != oi)]
            if len(inner) == 1:
                give(c, inner[0], 0.0)
            else:
                ambiguous.append({**c, "outlines": sorted(kept[oi].id for oi in holding)})
            continue
        ranked = sorted((round(_boundary_distance(p, poly), 3) + 0.0, oi) for oi, poly in enumerate(polys))
        ranked = [r for r in ranked if r[0] <= mark_radius]
        # an outline another ranked outline holds (a column stub in its cap) is never the nearest from outside
        ranked = [r for r in ranked if not any(r[1] in holds[o] for _, o in ranked if o != r[1])]
        if not ranked:
            unassigned.append(c)
            continue
        first = ranked[0][0]
        ties = [oi for d, oi in ranked if d - first <= max(tol, TIE_RATIO * d)]
        if len(ranked) > 1 and len(ties) > 1:
            ambiguous.append({**c, "outlines": sorted(kept[oi].id for oi in ties)})
        else:
            give(c, ranked[0][1], first)

    printed: dict[int, list[dict[str, Any]]] = {}
    dim_counts: dict[str, int] = {}
    if dims:
        if read.dims_unlinked:
            warnings.append(
                f"{file_rel}: {read.dims_unlinked} dimension text(s) have no text-index entry "
                "(text_entry null): the legacy-font gate was not applied to them"
            )
        printed, dim_counts = _attach_dims(
            read.dims.get(sheet, []),
            kept,
            polys,
            space,
            tol,
            mark_radius,
            [[syms[si]["centre"] for si in inside_of[oi]] for oi in range(len(kept))],
        )

    outlines_out: list[dict[str, Any]] = []
    groups = _grid_groups(Path(work_dir).resolve(), file_rel, sheet, warnings)
    ungrouped: list[str] = []
    multi: list[str] = []
    for oi, item in enumerate(kept):
        found = sorted(assigned.get(oi, []), key=lambda m: (m["distance"], m["entry_id"]))
        cx, cy = item.centre
        axes = []
        here = [
            g
            for g in groups
            if g["space"] == item.space
            and g["bbox"][0] < cx < g["bbox"][2]
            and g["bbox"][1] < cy < g["bbox"][3]
        ]
        if groups and not here:
            ungrouped.append(item.id)
        if len(here) > 1:
            multi.append(item.id)
        for g in here:
            for fid, (nx, ny), fam_axes, fam_lines in g["families"]:
                answer = _family_axes(nx * cx + ny * cy, fam_axes, fam_lines, tol)
                if answer is not None:
                    label, offset, unlabelled = answer
                    axes.append(
                        {
                            "group_id": g["group_id"],
                            "family_id": fid,
                            "label": label,
                            "offset": offset,
                            "nearest_unlabelled_offset": unlabelled,
                        }
                    )
        row: dict[str, Any] = {
            "id": item.id,
            "layer": item.layer,
            "short": item.short,
            "long": item.long,
            "angle": item.angle,
            "centre": list(item.centre),
            "symbols": len(inside_of[oi]),
            "invisible": item.invisible_copies == item.copies,
            "marks": found,
            "axes": axes,
        }
        if dims:
            row["printed_dims"] = printed.get(oi, [])
        if detail:
            row["symbol_centres"] = [list(syms[si]["centre"]) for si in sorted(inside_of[oi])]
        outlines_out.append(row)
    if ungrouped:
        warnings.append(
            f"{len(ungrouped)} outline(s) lie in no grid group of sheet {sheet}: no axes reported for them: "
            + _listed(ungrouped)
        )
    if multi:
        warnings.append(
            f"{len(multi)} outline(s) lie in more than one grid group (one axes entry per group): "
            + _listed(multi)
        )

    if dims:
        disagreeing: list[str] = []
        for row in outlines_out:
            bad = next((q for q in row["printed_dims"] if not q["agrees"]), None)
            if bad is not None:
                size = row[bad["side"]]
                disagreeing.append(f"{row['id']} ({bad['side']} {size:g} vs printed {bad['printed']:g})")
        if disagreeing:
            warnings.append(
                f"printed dimensions disagree with the linework on {len(disagreeing)} outline(s): "
                + _listed(disagreeing)
            )
        flat = [item.id for item in kept if not item.rectangle]
        if flat:
            warnings.append(
                f"printed dimensions: {len(flat)} outline(s) are not rectangles and get none: "
                + _listed(flat)
            )

    rows: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in outlines_out:
        key = (row["layer"], _snap(row["short"], tol), _snap(row["long"], tol), row["symbols"])
        r = rows.setdefault(
            key,
            {"layer": key[0], "short": key[1], "long": key[2], "symbols": key[3], "count": 0,
             "marks_seen": {}, "unmarked": 0, "invisible": 0},
        )  # fmt: skip
        r["count"] += 1
        r["unmarked"] += not row["marks"]
        r["invisible"] += row["invisible"]
        for text in {m["text"] for m in row["marks"]}:
            r["marks_seen"][text] = r["marks_seen"].get(text, 0) + 1
        if dims:
            pd = r.setdefault("printed_dims", {"agree": 0, "disagree": 0, "none": 0, "values": {}})
            found = row["printed_dims"]
            pd["none" if not found else "agree" if all(q["agrees"] for q in found) else "disagree"] += 1
            for value in {(q["side"], _snap(q["printed"], tol)) for q in found}:  # an outline counts once
                pd["values"][value] = pd["values"].get(value, 0) + 1
    summary = sorted(
        rows.values(), key=lambda r: (-r["count"], r["layer"], r["short"], r["long"], r["symbols"])
    )
    for r in summary:
        r["marks_seen"] = dict(sorted(r["marks_seen"].items()))
        if dims:
            r["printed_dims"]["values"] = [
                {"side": side, "printed": printed_value, "count": n}
                for (side, printed_value), n in sorted(r["printed_dims"]["values"].items())
            ]
    types: dict[str, list[str]] = {}
    for r in summary:
        for text in r["marks_seen"]:
            types.setdefault(text, []).append(f"{r['short']:g}x{r['long']:g} / {r['symbols']} symbol(s)")
    for text in sorted(types):
        if len(types[text]) > 1:
            warnings.append(
                f"mark {text} is seen on outlines of {len(types[text])} types: {'; '.join(types[text])}"
            )
    mixed = [
        f"{row['id']} ({', '.join(sorted({m['text'] for m in row['marks']}))})"
        for row in outlines_out
        if len({m["text"] for m in row["marks"]}) > 1
    ]
    if mixed:
        warnings.append(f"{len(mixed)} outline(s) hold different marks: {_listed(mixed)}")

    sym_groups: Counter[tuple[float, ...]] = Counter(tuple(sorted(s["diameters"])) for s in syms)
    inside_count = sum(1 for h in holders if h)
    out: dict[str, Any] = {
        "schema_version": geo["schema_version"],
        "kind": "contents",
        "project_id": geo["project_id"],
        "file": file_rel,
        "query": {
            "sheet": sheet,
            "outline_layers": outline_layers,
            "circle_layers": circle_layers,
            "max_long": max_long,
            "marks": marks,
            "mark_radius": mark_radius,
            "detail": detail,
            "max": max_rows,
            "tol": tol,
            **({"dims": True} if dims else {}),
        },
        "units": geo["units"],
        "summary": summary,
        "symbols": {
            "total": len(syms),
            "inside": inside_count,
            "outside": len(syms) - inside_count,
            "groups": [
                {"diameters": list(k), "count": n}
                for k, n in sorted(sym_groups.items(), key=lambda kv: (-kv[1], kv[0]))
            ],
        },
        "outlines_total": len(outlines_out),
        "outlines": outlines_out,
        "marks_unassigned": [_mark_json(c) for c in _by_text(unassigned)],
        "marks_ambiguous": [{**_mark_json(c), "outlines": c["outlines"]} for c in _by_text(ambiguous)],
        **({"dims": dim_counts} if dims else {}),
        "warnings": warnings,
    }
    limit = DEFAULT_MAX_OUTLINES if max_rows is None else max_rows
    if len(outlines_out) > limit:
        warnings.append(
            f"contents truncated: outlines {limit} of {len(outlines_out)} returned; "
            f"rerun with --max {len(outlines_out)} to get all of them"
        )
        out["outlines"] = outlines_out[:limit]
    if detail:
        out["symbols_outside"] = [
            {"centre": list(s["centre"]), "diameters": sorted(s["diameters"])}
            for si, s in enumerate(syms)
            if not holders[si]
        ]
    problems = validate("contents", out)
    if problems:
        raise ReaderError(EXIT_INVALID, f"internal error: output is invalid: {_details(problems)}")
    return out


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "work_dir", help="the --out folder of `harness intake` (after `harness read-structure`)"
    )
    parser.add_argument("file", help="input-relative path of the drawing, as in inventory.json")
    parser.add_argument("--sheet", required=True, metavar="ID", help="detector sheet id, e.g. model#06")
    parser.add_argument(
        "--outline-layer",
        nargs="+",
        action="extend",
        required=True,
        metavar="L",
        help="effective layers of the member outlines (case-insensitive)",
    )
    parser.add_argument(
        "--circle-layer",
        nargs="+",
        action="extend",
        required=True,
        metavar="L",
        help="effective layers of the symbols (pile circles)",
    )
    parser.add_argument(
        "--max-long",
        type=float,
        default=None,
        help="drop outlines with a longer long side (frames; default 20 m in the answered or declared unit, "
        "20000 when the unit is unknown)",
    )
    parser.add_argument(
        "--marks", metavar="REGEX", help="mark texts: a printed entry whose text fully matches"
    )
    parser.add_argument(
        "--mark-radius",
        type=float,
        default=None,
        help="largest distance from an outline to its mark (default 3 m in the answered or declared unit, "
        "3000 when the unit is unknown)",
    )
    parser.add_argument(
        "--dims",
        action="store_true",
        help="also attach the dimensions drawn on each rectangular outline and say whether the printed value "
        "agrees with the drawn size (reach: --mark-radius); a dimension of a stub centred on a cap attaches "
        "to the cap unless the stub's layer is passed as an outline layer; a pile spacing (both ends on "
        "symbol centres inside the outline) is not attached, but without the pile layer as --circle-layer "
        "it may still attach centred",
    )
    parser.add_argument("--detail", action="store_true", help="also list each outline's symbol centres")
    parser.add_argument(
        "--max", type=int, default=None, help=f"outlines listed (default {DEFAULT_MAX_OUTLINES})"
    )
    parser.add_argument(
        "--tol",
        type=float,
        default=None,
        help="dedupe and rounding tolerance in drawing units (default 1 mm in the answered or declared unit)",
    )
    parser.add_argument(
        "--input-dir", help="the intake input folder (needed when the drawing is a native DXF file)"
    )
    add_save_argument(parser)


def run(args: argparse.Namespace) -> int:
    started = time.monotonic()
    try:
        sha_before = sha_before_save(args.work_dir, args.file) if args.save else None
        doc = contents(
            Path(args.work_dir),
            args.file,
            sheet=args.sheet,
            outline_layers=args.outline_layer,
            circle_layers=args.circle_layer,
            max_long=args.max_long,
            marks=args.marks,
            mark_radius=args.mark_radius,
            detail=args.detail,
            max_rows=args.max,
            tol=args.tol,
            input_dir=Path(args.input_dir) if args.input_dir else None,
            dims=args.dims,
        )
    except ReaderError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    for warning in doc["warnings"]:
        if warning.startswith("contents truncated"):
            print(warning, file=sys.stderr)
    print(f"contents: {time.monotonic() - started:.1f} s elapsed", file=sys.stderr)
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
