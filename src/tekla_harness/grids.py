"""grids: grid axes, spacings and a Tekla coordinate-string proposal per family, from one DXF.

`extract_grids(dxf_path, text_index, sheets_result)` returns a dict that validates against
`schemas/grids.schema.json`. Nothing here is final: gate 1 needs the engineer to confirm the grids
(RTI-0003), and which family is Tekla X / Y is always asked, never decided.

Two questions are NOT blocking here because another producer owns the blocking one (one question per
decision): grid_family_axis_assignment (the blocking X/Y question is grid-system's per-system
grid_system_axis_unassigned; family answers still assign) and grid_units_doubt (the blocking units
question is intake's units_confirm_all of the file; this one is evidence for it).

Algorithm (deterministic; thresholds are the named constants below):

1. Walk model space and every layout, expanding INSERTs (sheets.Walker), collecting CIRCLEs (and
   ARCs or circular ELLIPSEs from scaled blocks whose sweep is a full turn within FULL_ARC_GAP_DEG: a
   bubble drawn as an arc from 90.00006 to 90.0000031 degrees is a circle, a door swing is not), straight
   segments (LINE, 2-vertex open polylines) and linear DIMENSIONs, all in world / paper coordinates. A
   bubble is therefore found by its circle centre, whatever the block's base point or mirroring.
2. Bubble = circle whose centre (within BUBBLE_TEXT_RADIUS x r) holds exactly one distinct axis-label
   text from the text index (ATTRIB, text inside a block, or loose TEXT), of height 0.15 r .. 1.6 r,
   and no other text. Two different label texts in one circle: ambiguous; a label plus other text (a
   section callout with its sheet number): not a bubble (both counted, not used).
3. Pairing: the longest segment >= MIN_AXIS_LENGTH radii long whose infinite line passes within
   LINE_THROUGH_CENTRE x r of the centre and whose nearer end is within END_NEAR_BUBBLE x r of it.
   Number-in-circle bar marks sit on short leaders and fail the length rule. Bubbles at both ends of
   one line (same label, collinear) become one axis; collinear same-label pieces join only when they
   overlap or leave a gap of at most END_NEAR_BUBBLE radii (two plans side by side keep their own axes).
   A bubble pair with the same label, no line, and a line between them that joins an existing view
   becomes a 'two_bubbles' axis (low confidence).
4. Views: per sheet, axes whose segments cross (ends extended by 2 r) are one view (union-find).
   Views made only of parallel axes join a neighbouring parallel view when their projections overlap by
   half and their label sets stay disjoint. Views of fewer than 2 axes are dropped (isolated_axes).
5. Families: axes of a view within FAMILY_ANGLE_TOL degrees, directions circular (179.6 = -0.4); the
   family angle is the median of its axes'; ordered by offset along the normal, measured at each line's
   midpoint. Same offset with two labels, the same label at two offsets, an axis drifting end to end by
   more than half the rounding step ('not parallel'), an axis off the family's majority layer/linetype,
   labels that neither rise nor fall, single skewed axes, non-orthogonal families and label gaps all
   raise questions. Lines on the family's layer and linetype that look like a further axis but carry no
   label are listed, never used in spacings.
6. Spacings between consecutive axes; a linear DIMENSION whose two extension points lie on two axes of
   a family is evidence: its override text (or measurement x DIMLFAC) is compared with the spacing. Only
   one between neighbouring axes is `dimension_adjacent`; an overall one is `dimension_span`.
7. Cross-check every pair of families sharing >= 2 labels (all views, all sheets): equal spacings ->
   consistent, a constant ratio over >= 2 spacings -> scaled copy (question), differences of at most
   DRAFTING_TOL of the spacing -> drafting_tolerance (non-blocking question), otherwise mismatch
   (blocking). Each compared spacing is `other_view` evidence, independent unless same sheet, copied
   sheets or same block. Nothing here is 'high' (MAX_CONFIDENCE): agreeing evidence is data for gate 1.
8. Proposal: '0' then the spacings rounded to 4 significant digits of the smallest spacing, equal runs
   as 'n*d', in drawing units with the declared header unit attached (never converted).
"""

from __future__ import annotations

import math
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Any

from ezdxf.document import Drawing
from ezdxf.tools.text import plain_mtext

from tekla_harness.sheets import (
    SHEET_UNKNOWN,
    SheetLocator,
    Walker,
    declared_units,
    layout_spaces,
    listed,
    min_conf,
    open_checked,
    question,
    rbox,
    rnum,
    text_box,
    text_center,
)
from tekla_harness.text_gate import meaning_block_reason
from tekla_harness.visibility import is_printed

SCHEMA_VERSION = "0.1"
BUBBLE_TEXT_RADIUS = 0.9  # label centre within this x r of the circle centre
MIN_AXIS_LENGTH = 10.0  # axis line length, in bubble radii
LINE_THROUGH_CENTRE = 0.35  # the line passes within this x r of the centre
END_NEAR_BUBBLE = 8.0  # the nearer line end lies within this x r of the centre (bubbles often sit past a gap)
SAME_LINE_TOL = 0.1  # x r: two collinear axes are the same line
FAMILY_ANGLE_TOL = 0.5  # degrees
# Heuristic: an ARC (or a ratio-1 ELLIPSE) whose sweep falls short of a full turn by at most this many degrees
# is drawn as a circle (EVAL-3 285/286: block SADF, an arc from 90.00006 to 90.0000031 degrees)
FULL_ARC_GAP_DEG = 1.0
ORTHO_TOL = 0.1  # degrees
# Heuristics for an obround bubble (two LINEs and two semicircular ARCs around the label; EVAL-4 180): the
# caps have one radius within OBROUND_RADIUS_TOL (x radius), their diameters are perpendicular to the line
# between their centres within OBROUND_PERP_TOL (|cos|), the two LINEs join their ends within
# OBROUND_END_TOL (x radius), and the straight part is at most OBROUND_MAX_LENGTH radii long. The bubble's
# radius is half the overall length (straight part + both caps), so a label as tall as the stadium is wide
# still fits the label-height test (0.15 r .. 1.6 r).
OBROUND_RADIUS_TOL = 0.02
OBROUND_PERP_TOL = 0.05
OBROUND_END_TOL = 0.05
OBROUND_MAX_LENGTH = 12.0
# Heuristics, family consistency (F2b): in a family of FAMILY_MIN_AXES or more axes an axis is set aside when
# it differs from the family in at least FAMILY_MIN_DEVIATIONS of three things: its size (bubble radius or
# label height more than FAMILY_SIZE_TOL of the family median away; the two scale together, so they count
# once), its block (the circle's outermost block name) or its line (layer + linetype). For the last two the
# family value is the one more than half of the family's axes share.
FAMILY_MIN_AXES = 3
FAMILY_MIN_DEVIATIONS = 2
FAMILY_SIZE_TOL = 0.20
DIM_POINT_TOL = 0.05  # x r: a dimension extension point lies on an axis
SCALE_TOL = 1e-3  # relative: two spacing sets differ by one ratio
# Heuristic (not a standard): two views whose spacing differs by at most this fraction of the spacing
# (5770.83 vs 5770) are taken as a drafting inaccuracy, asked non-blocking; more is a blocking mismatch.
DRAFTING_TOL = 2e-4
# Heuristic: two sheets whose text multisets overlap this much (Jaccard) are copies of one drawing, so a
# grid on one does not independently confirm the other.
NEAR_IDENTICAL_TEXTS = 0.9
PLAUSIBLE_SPACING_M = (0.5, 30.0)
MAX_QUESTIONS_PER_CODE = 100
MAX_UNPAIRED_LISTED = 100
MAX_CONFIDENCE = "medium"  # 'high' is reserved for an engineer answer at gate 1 (pairing is heuristic)

_METRES = {"mm": 0.001, "cm": 0.01, "m": 1.0, "in": 0.0254, "ft": 0.3048}


def implausible_spacing(median: dict[str, Any] | None, unit: str) -> str | None:
    """The grid-spacing plausibility test (PLAUSIBLE_SPACING_M) for `unit`: the evidence, in plain words, when
    the median grid spacing of a file read in `unit` falls outside the range; None when it is plausible, or
    when the median ({"value", "count"}, drawing units) or the unit is unknown (nothing to test)."""
    factor = _METRES.get(unit)
    if median is None or factor is None:
        return None
    metres = median["value"] * factor
    if PLAUSIBLE_SPACING_M[0] <= metres <= PLAUSIBLE_SPACING_M[1]:
        return None
    return (
        f"median grid spacing {median['value']:g} drawing units = {metres:g} m in {unit} over "
        f"{median['count']} spacing(s); plausible range {PLAUSIBLE_SPACING_M[0]:g} m to "
        f"{PLAUSIBLE_SPACING_M[1]:g} m"
    )


# --- the grid families a question cites (tool wave 2: lifecycle closes a question only when every family it
# cites belongs to an unselected grid system). Read back from this module's own `where` formats: the grids
# schema has no field for them on a question.

# codes whose `where` starts with "<view>/<family>[,<family>]" (and, for cross-checks, " vs <view>/<family>")
FAMILY_WHERE_CODES = frozenset(
    {
        "grid_axis_label_conflict",  # "line <handle> on layer ..." before families exist: no family
        "grid_label_duplicate",
        "grid_axis_not_parallel",
        "grid_axis_layer_mismatch",
        "grid_label_kind_mixed",
        "grid_label_order_nonmonotonic",
        "grid_label_sequence_gap",
        "grid_rotated",
        "grid_axis_skewed",
        "grid_non_orthogonal",
        "grid_label_missing",
        "grid_axis_unlabelled",
        "grid_two_bubble_axis",
        "grid_label_order_mismatch",
        "grid_scale_differs",
        "grid_spacing_cross_sheet_mismatch",
        "grid_spacing_drafting_tolerance",
        "grid_dimension_override_mismatch",
    }
)
# codes about every family of two or more axes (their `where` is listed(), which truncates)
ALL_FAMILIES_CODES = frozenset({"grid_family_axis_assignment", "grid_gate1_confirmation"})
_WHERE_FAMILIES = re.compile(r"(?:^| vs )V\d{3,}/(F\d{3,}(?:,F\d{3,})*)")


def question_families(question: dict[str, Any], doc: dict[str, Any]) -> list[str] | None:
    """Sorted family ids (F001..) a grids question of `doc` is about; None when it cites no family (or one
    the document does not have: never guess)."""
    code = question["code"]
    known = {f["family_id"]: len(f["axes"]) for g in doc["groups"] for f in g["families"]}
    if code in ALL_FAMILIES_CODES:
        found = [fid for fid, n in known.items() if n >= 2]
    elif code in FAMILY_WHERE_CODES:
        found = [fid for m in _WHERE_FAMILIES.finditer(question["where"]) for fid in m.group(1).split(",")]
    else:
        return None
    if not found or any(fid not in known for fid in found):
        return None
    return sorted(set(found))


_LABEL_RE = re.compile(
    r"^(?:[A-Za-z]{1,2}[a-z]?|\d{1,3}[A-Za-z]?|[A-Za-z]\d{1,2}[a-z]?)(?:'{1,2}|\u2032)?$"
    r"|^[A-Za-z0-9]{1,3}/[A-Za-z0-9]{1,3}$"
)
_LABEL_TOKEN_RE = re.compile(r"\d+|[A-Za-z]+|['\u2032]+|/")
_NUMBER_RE = re.compile(r"^\s*[-+]?\d+(?:\.\d+)?\s*$")
_GEOMETRY = frozenset({"LINE", "LWPOLYLINE", "POLYLINE", "CIRCLE", "ARC", "ELLIPSE", "DIMENSION"})
_GEOMETRY_NAME = {"CIRCLE": "circle", "ARC": "circle", "ELLIPSE": "circle", "DIMENSION": "dimension"}


# --- primitives --------------------------------------------------------------------------------


@dataclass
class _Seg:
    sid: int
    a: tuple[float, float]
    b: tuple[float, float]
    space: str
    layer: str
    linetype: str
    handle: str | None
    block_path: tuple[str, ...]

    @property
    def length(self) -> float:
        return math.dist(self.a, self.b)

    @property
    def mid(self) -> tuple[float, float]:
        return ((self.a[0] + self.b[0]) / 2, (self.a[1] + self.b[1]) / 2)

    def angle(self) -> float:
        return _canonical_angle(math.degrees(math.atan2(self.b[1] - self.a[1], self.b[0] - self.a[0])))

    def line_json(self) -> dict[str, Any]:
        return {
            "start": [rnum(self.a[0]), rnum(self.a[1])],
            "end": [rnum(self.b[0]), rnum(self.b[1])],
            "handle": self.handle,
            "layer": self.layer,
            "linetype": self.linetype,
            "block_path": list(self.block_path),
        }

    def box(self) -> tuple[float, float, float, float]:
        return (
            min(self.a[0], self.b[0]),
            min(self.a[1], self.b[1]),
            max(self.a[0], self.b[0]),
            max(self.a[1], self.b[1]),
        )


@dataclass
class _Circle:
    c: tuple[float, float]
    r: float
    space: str
    block_path: tuple[str, ...]


@dataclass
class _Arc:
    """A semicircular ARC, in world coordinates: the cap of a possible obround bubble."""

    p1: tuple[float, float]
    p2: tuple[float, float]
    mid: tuple[float, float]  # the point halfway along the arc
    r: float
    space: str
    block_path: tuple[str, ...]

    @property
    def c(self) -> tuple[float, float]:
        return ((self.p1[0] + self.p2[0]) / 2, (self.p1[1] + self.p2[1]) / 2)


@dataclass
class _Bubble:
    circle: _Circle
    entry: dict[str, Any] | None
    sheet: str

    @property
    def label(self) -> str | None:
        return self.entry["display_text"].strip() if self.entry else None

    def as_json(self) -> dict[str, Any]:
        e = self.entry
        source = "none"
        if e is not None:
            source = "attrib" if e["entity_type"] == "ATTRIB" else "block_text" if e["block_path"] else "text"
        return {
            "center": [rnum(self.circle.c[0]), rnum(self.circle.c[1])],
            "radius": rnum(self.circle.r),
            "label": self.label,
            "label_source": source,
            "tag": e["tag"] if e is not None and e["entity_type"] == "ATTRIB" else None,
            "text_id": e["id"] if e is not None else None,
            "block_path": list(self.circle.block_path),
            "sheet": self.sheet,
        }


@dataclass
class _Dim:
    p1: tuple[float, float]
    p2: tuple[float, float]
    u: tuple[float, float]  # measurement direction
    measured: float
    dimlfac: float
    dimdec: int
    text: str
    handle: str | None
    space: str
    sheet: str


@dataclass
class _Axis:
    seg: _Seg
    bubbles: list[_Bubble]
    pairing: str
    sheet: str
    space: str
    aid: str = ""
    offset: float = 0.0
    dev: float = 0.0  # signed angle from the family direction, degrees

    @property
    def label(self) -> str | None:
        return self.bubbles[0].label if self.bubbles else None

    @property
    def r(self) -> float:
        return max(b.circle.r for b in self.bubbles)


@dataclass
class _Family:
    fid: str
    axes: list[_Axis]
    theta: float
    d: tuple[float, float]
    n: tuple[float, float]
    issues: set[str] = field(default_factory=set)
    unlabelled: list[tuple[float, _Seg, bool]] = field(default_factory=list)
    spacings: list[float] = field(default_factory=list)
    dim_evidence: dict[int, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))
    evidence: dict[int, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))

    @property
    def rel_offsets(self) -> list[float]:
        base = self.axes[0].offset
        return [a.offset - base for a in self.axes]

    def r(self) -> float:
        return statistics.median(a.r for a in self.axes)

    def labels(self) -> list[str | None]:
        return [a.label for a in self.axes]


@dataclass
class _Group:
    gid: str
    sheet: str
    space: str
    axes: list[_Axis]
    families: list[_Family] = field(default_factory=list)


# --- helpers -----------------------------------------------------------------------------------


def _effective_linetype(doc: Drawing, entity: Any) -> str:
    lt = str(entity.dxf.get("linetype", "BYLAYER"))
    if lt.upper() == "BYLAYER":
        name = str(entity.dxf.get("layer", "0"))
        layer = doc.layers.get(name) if doc.layers.has_entry(name) else None  # an undefined layer is plain
        return str(layer.dxf.get("linetype", "CONTINUOUS")) if layer is not None else "BYLAYER"
    return lt


def _geometry_not_printed(
    doc: Drawing, entity: Any, in_block: bool, layers: dict[str, str | None]
) -> str | None:
    """Why a line, circle or dimension does not print, else None (docs/research/dxf-invisible-text.md).

    Its own group 60, or its layer off (colour < 0), frozen, or with the plot flag 0. An entity on layer '0'
    inside a block takes the INSERT's layer, and whether AutoCAD then hides it is not settled (research
    note, section 7), so only its own group 60 counts. An INSERT's own group 60 over its contents is not
    settled either (section 2): the contents are kept."""
    if int(entity.dxf.get("invisible", 0) or 0) == 1:
        return "entity_invisible"
    name = str(entity.dxf.get("layer", "0"))
    if in_block and name == "0":
        return None
    if name not in layers:
        layer = doc.layers.get(name) if doc.layers.has_entry(name) else None  # an undefined layer is plain
        reason = None
        if layer is not None:
            if layer.is_off():
                reason = "layer_off"
            elif layer.is_frozen():
                reason = "layer_frozen"
            elif int(layer.dxf.get("plot", 1)) == 0:
                reason = "layer_no_plot"
        layers[name] = reason
    return layers[name]


def _segments_of(entity: Any) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    kind = entity.dxftype()
    if kind == "LINE":
        s, e = entity.dxf.start, entity.dxf.end
        return [((s.x, s.y), (e.x, e.y))]
    if kind == "LWPOLYLINE" and len(entity) == 2 and not entity.closed:
        if any(abs(b[0]) > 1e-12 for b in entity.get_points("b")):
            return []
        pts = [(v.x, v.y) for v in entity.vertices_in_wcs()]
        return [(pts[0], pts[1])]
    if kind == "POLYLINE" and entity.is_2d_polyline and len(entity) == 2 and not entity.is_closed:
        pts = [(v.x, v.y) for v in entity.points_in_wcs()]
        return [(pts[0], pts[1])]
    return []


def _dist_to_line(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    return abs((p[0] - a[0]) * dy - (p[1] - a[1]) * dx) / length if length else math.dist(p, a)


def _segments_cross(s: _Seg, t: _Seg, tol: float) -> bool:
    d1 = (s.b[0] - s.a[0], s.b[1] - s.a[1])
    d2 = (t.b[0] - t.a[0], t.b[1] - t.a[1])
    den = d1[0] * d2[1] - d1[1] * d2[0]
    l1, l2 = math.hypot(*d1), math.hypot(*d2)
    if l1 == 0 or l2 == 0 or abs(den) <= 1e-9 * l1 * l2:
        return False
    qx, qy = t.a[0] - s.a[0], t.a[1] - s.a[1]
    u = (qx * d2[1] - qy * d2[0]) / den
    v = (qx * d1[1] - qy * d1[0]) / den
    return -tol / l1 <= u <= 1 + tol / l1 and -tol / l2 <= v <= 1 + tol / l2


def fmt_number(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(round(value))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def coordinate_string(spacings: list[float]) -> str:
    """'0' then relative spacings, equal consecutive runs written 'n*d' (Tekla grid syntax)."""
    tokens = ["0"]
    i = 0
    while i < len(spacings):
        j = i
        while j + 1 < len(spacings) and spacings[j + 1] == spacings[i]:
            j += 1
        run = j - i + 1
        tokens.append(f"{run}*{fmt_number(spacings[i])}" if run > 1 else fmt_number(spacings[i]))
        i = j + 1
    return " ".join(tokens)


def rounding_step(spacings: list[float]) -> float:
    positive = [s for s in spacings if s > 0]
    if not positive:
        return 1.0
    return 10.0 ** (math.floor(math.log10(min(positive))) - 3)


def _round_to(value: float, step: float) -> float:
    return round(round(value / step) * step, 9)


def _label_seq_gap(labels: list[str]) -> str | None:
    """Description of a gap in a pure-number or pure-single-letter label sequence, else None."""
    if len(labels) < 2:
        return None
    if all(lbl.isdigit() for lbl in labels):
        values = [int(lbl) for lbl in labels]
    elif all(len(lbl) == 1 and lbl.isalpha() and lbl.isupper() for lbl in labels):
        values = [ord(lbl) for lbl in labels]
    else:
        return None
    steps = {b - a for a, b in pairwise(values)}
    if steps in ({1}, {-1}):
        return None
    return " ".join(labels)


def _label_key(label: str) -> tuple[tuple[Any, ...], ...]:
    """Sort key of an axis label: '2' < '10', 'Z' < 'AA', '1' < '1A' < '2', 'A1' < 'A2' < 'B1'."""
    out: list[tuple[Any, ...]] = []
    for tok in _LABEL_TOKEN_RE.findall(label):
        if tok.isdigit():
            out.append((0, int(tok)))
        elif tok.isalpha():
            out.append((1, len(tok), tok.upper()))
        elif tok == "/":
            out.append((3, 0))
        else:
            out.append((2, len(tok)))
    return tuple(out)


def _label_order_broken(labels: list[str]) -> bool:
    """True when the labels, in offset order, neither rise nor fall (e.g. '1 3 2 4').

    Only the leading number or letters are compared, and repeats are allowed: an intermediate axis
    ('1A', "6'") sits next to its base axis on either side (drawings differ: 3, 3', 4 and 6, 6', 5 both
    occur), so its suffix says nothing about the direction."""
    keys = [_label_key(lbl)[:1] for lbl in labels]
    rising = all(a <= b for a, b in pairwise(keys))
    falling = all(a >= b for a, b in pairwise(keys))
    return not (rising or falling)


def _canonical_angle(theta: float) -> float:
    """Direction angle in [-FAMILY_ANGLE_TOL, 180 - FAMILY_ANGLE_TOL) degrees (lines have no sense)."""
    t = theta % 180.0
    return t - 180.0 if t >= 180.0 - FAMILY_ANGLE_TOL else t


def _signed_angle(a: float, ref: float) -> float:
    """a - ref for line directions, in (-90, 90] degrees."""
    d = (a - ref) % 180.0
    return d - 180.0 if d > 90.0 else d


class _Index:
    """Uniform grid buckets of points -> payloads, for near queries."""

    def __init__(self, cell: float):
        self.cell = cell if cell > 0 else 1.0
        self.buckets: dict[tuple[int, int], list[Any]] = defaultdict(list)

    def add(self, p: tuple[float, float], payload: Any) -> None:
        self.buckets[(math.floor(p[0] / self.cell), math.floor(p[1] / self.cell))].append(payload)

    def near(self, p: tuple[float, float], radius: float) -> list[Any]:
        """Payloads of the buckets within `radius` (a superset: callers filter by distance).

        A huge radius (a site boundary drawn as a circle) scans the occupied buckets instead of the
        (2k+1)^2 cells around the point, so the cost stays bounded by the number of buckets.
        """
        k = max(1, math.ceil(radius / self.cell))
        cx, cy = math.floor(p[0] / self.cell), math.floor(p[1] / self.cell)
        out: list[Any] = []
        if (2 * k + 1) ** 2 > len(self.buckets):
            for (i, j), items in sorted(self.buckets.items()):
                if abs(i - cx) <= k and abs(j - cy) <= k:
                    out.extend(items)
            return out
        for i in range(cx - k, cx + k + 1):
            for j in range(cy - k, cy + k + 1):
                out.extend(self.buckets.get((i, j), ()))
        return out


# --- main ----------------------------------------------------------------------------------------


@dataclass
class _Ctx:
    file_path: str
    cap: str
    units: dict[str, Any]
    locator: SheetLocator
    questions: list[dict[str, Any]] = field(default_factory=list)
    q_counts: Counter[str] = field(default_factory=Counter)
    warnings: list[str] = field(default_factory=list)
    not_printed_text: int = 0  # text entries the index marks printed: false, left out of every bubble
    not_printed_geometry: Counter[str] = field(default_factory=Counter)  # "<kind>:<reason>" -> count

    def ask(self, code: str, blocking: bool, message: str, where: str, found: str, sheet: str | None = None):
        self.q_counts[code] += 1
        if self.q_counts[code] <= MAX_QUESTIONS_PER_CODE:
            self.questions.append(question(code, blocking, message, where, found, sheet))

    def prov(self, sheet: str, box: tuple[float, float, float, float], method: str = "dxf_entity", **extra):
        p: dict[str, Any] = {
            "file": self.file_path,
            "sheet": sheet,
            "method": method,
            "region": {"bbox": rbox(box)},
        }
        p.update(extra)
        return p


def _collect(doc: Drawing, walker: Walker, ctx: _Ctx):
    segs: list[_Seg] = []
    circles: list[_Circle] = []
    caps: list[_Arc] = []
    dims: list[_Dim] = []
    layers: dict[str, str | None] = {}
    for space, layout, _ in layout_spaces(doc):
        for p in walker.walk(layout, space, _GEOMETRY):
            e = p.entity
            kind = e.dxftype()
            handle = walker.handle(e) if not p.block_path else p.top_handle
            try:
                hidden = _geometry_not_printed(doc, e, bool(p.block_path), layers)
                if hidden is not None:
                    ctx.not_printed_geometry[f"{_GEOMETRY_NAME.get(kind, 'line')}:{hidden}"] += 1
                    continue
                if kind == "CIRCLE":
                    c = e.dxf.center
                    if e.dxf.get("extrusion", (0, 0, 1))[2] < 0:
                        c = e.ocs().to_wcs(c)
                    if e.dxf.radius > 0:
                        circles.append(_Circle((c.x, c.y), float(e.dxf.radius), space, p.block_path))
                elif kind == "ARC":
                    sweep = (float(e.dxf.end_angle) - float(e.dxf.start_angle)) % 360.0
                    if e.dxf.radius > 0 and sweep >= 360.0 - FULL_ARC_GAP_DEG:
                        c = e.dxf.center
                        if e.dxf.get("extrusion", (0, 0, 1))[2] < 0:
                            c = e.ocs().to_wcs(c)
                        circles.append(_Circle((c.x, c.y), float(e.dxf.radius), space, p.block_path))
                    elif e.dxf.radius > 0 and abs(sweep - 180.0) <= FULL_ARC_GAP_DEG:
                        caps.append(_cap(e, space, p.block_path))
                elif kind == "ELLIPSE":
                    span = math.degrees((float(e.dxf.end_param) - float(e.dxf.start_param)) % math.tau)
                    full = span >= 360.0 - FULL_ARC_GAP_DEG or span == 0.0  # 0 and 2 pi: a whole ellipse
                    if abs(float(e.dxf.ratio) - 1.0) < 1e-3 and full:
                        c, major = e.dxf.center, e.dxf.major_axis
                        circles.append(_Circle((c.x, c.y), math.hypot(major.x, major.y), space, p.block_path))
                elif kind == "DIMENSION":
                    dim = _dimension(e, handle, space, ctx)
                    if dim is not None:
                        dims.append(dim)
                else:
                    for a, b in _segments_of(e):
                        if math.dist(a, b) > 0:
                            segs.append(
                                _Seg(
                                    len(segs),
                                    a,
                                    b,
                                    space,
                                    str(e.dxf.get("layer", "0")),
                                    _effective_linetype(doc, e),
                                    handle,
                                    p.block_path,
                                )
                            )
            except Exception as exc:
                walker.skipped[f"read_error:{kind}:{type(exc).__name__}"] += 1
    return segs, circles, caps, dims


def _cap(e: Any, space: str, block_path: tuple[str, ...]) -> _Arc:
    start, end = float(e.dxf.start_angle), float(e.dxf.end_angle)
    sweep = (end - start) % 360.0
    p1, p2 = e.start_point, e.end_point
    (m,) = e.vertices([start + sweep / 2.0])
    return _Arc((p1.x, p1.y), (p2.x, p2.y), (m.x, m.y), float(e.dxf.radius), space, block_path)


def _dimension(e: Any, handle: str | None, space: str, ctx: _Ctx) -> _Dim | None:
    dimtype = int(e.dxf.get("dimtype", 0)) & 7
    if dimtype not in (0, 1):
        return None
    p1, p2 = e.dxf.get("defpoint2"), e.dxf.get("defpoint3")
    if p1 is None or p2 is None:
        return None
    if dimtype == 0:
        ang = math.radians(float(e.dxf.get("angle", 0.0)))
        u = (math.cos(ang), math.sin(ang))
    else:
        length = math.dist((p1.x, p1.y), (p2.x, p2.y))
        if length == 0:
            return None
        u = ((p2.x - p1.x) / length, (p2.y - p1.y) / length)
    measured = e.get_measurement()
    ov = e.override()
    dimlfac = float(ov.get("dimlfac", 1.0) or 1.0)
    dimdec = int(ov.get("dimdec", 4))
    mid = ((p1.x + p2.x) / 2, (p1.y + p2.y) / 2)
    return _Dim(
        (p1.x, p1.y),
        (p2.x, p2.y),
        u,
        float(measured),
        dimlfac,
        dimdec,
        str(e.dxf.get("text", "")),
        handle,
        space,
        ctx.locator.locate(space, *mid),
    )


def _joins(seg: _Seg, p: tuple[float, float], q: tuple[float, float], tol: float) -> bool:
    """The segment runs from p to q (either way) within `tol`."""
    return (math.dist(seg.a, p) <= tol and math.dist(seg.b, q) <= tol) or (
        math.dist(seg.a, q) <= tol and math.dist(seg.b, p) <= tol
    )


def _obround_circles(caps: list[_Arc], segs: list[_Seg]) -> list[_Circle]:
    """Bubbles drawn as an obround (stadium): two semicircular ARCs of one radius facing away from each other,
    their ends joined by two LINEs (EVAL-4 180 framing plans: 0 of the labelled bubbles were circles). Each is
    returned as a circle at the middle of the stadium with half its overall length as radius (see
    OBROUND_*). Nothing is taken from the layer or the label: the geometry alone decides."""
    if len(caps) < 2:
        return []
    cell = statistics.median(a.r for a in caps) * 4
    by_space: dict[str, _Index] = defaultdict(lambda: _Index(cell))
    for k, a in enumerate(caps):
        by_space[a.space].add(a.c, (k, a))
    ends: _Index | None = None
    out: list[_Circle] = []
    used: set[int] = set()
    for i, a in enumerate(caps):
        if i in used:
            continue
        nx, ny = a.p2[0] - a.p1[0], a.p2[1] - a.p1[1]
        norm = math.hypot(nx, ny)
        if norm == 0:
            continue
        for j, b in sorted(by_space[a.space].near(a.c, OBROUND_MAX_LENGTH * a.r), key=lambda t: t[0]):
            if j <= i or j in used or abs(b.r - a.r) > OBROUND_RADIUS_TOL * a.r:
                continue
            d = (b.c[0] - a.c[0], b.c[1] - a.c[1])
            length = math.hypot(*d)
            if not 0.1 * a.r <= length <= OBROUND_MAX_LENGTH * a.r:
                continue
            # both diameters are perpendicular to d, and the caps bulge away from each other
            nb = (b.p2[0] - b.p1[0], b.p2[1] - b.p1[1])
            if abs(nx * d[0] + ny * d[1]) > OBROUND_PERP_TOL * norm * length:
                continue
            if abs(nb[0] * d[0] + nb[1] * d[1]) > OBROUND_PERP_TOL * math.hypot(*nb) * length:
                continue
            if (a.mid[0] - a.c[0]) * d[0] + (a.mid[1] - a.c[1]) * d[1] >= 0:
                continue
            if (b.mid[0] - b.c[0]) * d[0] + (b.mid[1] - b.c[1]) * d[1] <= 0:
                continue
            if ends is None:
                ends = _Index(cell)
                for s in segs:
                    ends.add(s.a, s)
                    ends.add(s.b, s)
            tol = OBROUND_END_TOL * a.r
            ok = True
            for p in (a.p1, a.p2):
                q = (p[0] + d[0], p[1] + d[1])
                near = {id(s): s for s in ends.near(p, tol + 1e-9) if s.space == a.space}
                if not any(_joins(s, p, q, tol) for s in near.values()):
                    ok = False
                    break
            if not ok:
                continue
            used.update((i, j))
            centre = ((a.c[0] + b.c[0]) / 2, (a.c[1] + b.c[1]) / 2)
            out.append(_Circle(centre, length / 2 + a.r, a.space, a.block_path))
            break
    return out


def _find_bubbles(circles: list[_Circle], entries: list[dict[str, Any]], ctx: _Ctx):
    """(bubbles, circles with two labels, circles with a label and other text, empty circles, circles whose
    only label the legacy-font gate blocks, the blocked label entries with their circle's sheet).

    A circle holding any text besides its one label (a section or detail callout: number + sheet) is
    not a bubble; a repeat of the label's own text is not 'other text'. A label-shaped text whose meaning
    `text_gate.meaning_block_reason` blocks is never a label ('4/g14' in a TCVN3 style is a rebar callout):
    it is listed, and its circle is a bubble without a readable label (not empty, not other text).
    """
    texts_by_space: dict[str, _Index] = {}
    cell_r = statistics.median(c.r for c in circles) if circles else 1.0
    for e in entries:
        text = e["display_text"].strip()
        if not text:
            continue
        if not is_printed(e):  # tool wave 4: text that does not print is no label and no other text
            ctx.not_printed_text += 1
            continue
        c = text_center(e)
        if c is None:
            continue
        idx = texts_by_space.setdefault(e["space"], _Index(4 * cell_r))
        idx.add(c, (c, e, bool(_LABEL_RE.match(text))))
    bubbles: list[_Bubble] = []
    ambiguous = 0
    other_text = 0
    empty: list[_Circle] = []
    unreadable: list[_Circle] = []
    blocked: dict[str, tuple[dict[str, Any], str, str]] = {}  # entry id -> (entry, reason, sheet)
    for circle in circles:
        idx = texts_by_space.get(circle.space)
        hits: list[dict[str, Any]] = []
        blocked_here: list[dict[str, Any]] = []
        inside_texts: set[str] = set()
        if idx is not None:
            for c, e, is_label in idx.near(circle.c, circle.r):
                if math.dist(c, circle.c) > BUBBLE_TEXT_RADIUS * circle.r:
                    continue
                inside_texts.add(e["display_text"].strip())
                h = e.get("height")
                if is_label and (h is None or 0.15 * circle.r <= h <= 1.6 * circle.r):
                    reason = meaning_block_reason(e)
                    if reason is None:
                        hits.append(e)
                    else:
                        blocked_here.append(e)
                        sheet = ctx.locator.locate(circle.space, *circle.c)
                        blocked.setdefault(e["id"], (e, reason, sheet))
        labels = {e["display_text"].strip() for e in hits}
        if blocked_here and inside_texts == {e["display_text"].strip() for e in blocked_here}:
            unreadable.append(circle)
        elif not inside_texts:
            empty.append(circle)
        elif len(labels) > 1:
            ambiguous += 1
        elif len(labels) == 1 and inside_texts != labels:
            other_text += 1
        elif hits:
            entry = min(hits, key=lambda e: e["id"])
            bubbles.append(_Bubble(circle, entry, ctx.locator.locate(circle.space, *circle.c)))
    blocked_list = [
        {"entry_id": e["id"], "value_text": e["display_text"].strip(), "reason": reason, "sheet": sheet}
        for e, reason, sheet in sorted(blocked.values(), key=lambda t: t[0]["id"])
    ]
    return bubbles, ambiguous, other_text, empty, unreadable, blocked_list


def _style(seg: _Seg) -> tuple[str, str]:
    return (seg.layer, seg.linetype)


def _sheet_styles(axes: list[_Axis]) -> dict[tuple[str, str], tuple[str, str]]:
    """(space, sheet) -> the (layer, linetype) most axes of that sheet are drawn on, when one style has more
    axes than any other and at least two (a clear majority); sheets without one are absent."""
    counts: dict[tuple[str, str], Counter[tuple[str, str]]] = defaultdict(Counter)
    for a in axes:
        counts[(a.space, a.sheet)][_style(a.seg)] += 1
    out: dict[tuple[str, str], tuple[str, str]] = {}
    for key, counter in counts.items():
        top = counter.most_common(2)
        if top[0][1] >= 2 and (len(top) == 1 or top[0][1] > top[1][1]):
            out[key] = top[0][0]
    return out


def _pair(bubbles: list[_Bubble], segs: list[_Seg], ctx: _Ctx) -> tuple[list[_Axis], list[_Bubble]]:
    if not bubbles:
        return [], []
    cell = 4 * statistics.median(b.circle.r for b in bubbles)
    by_space: dict[str, _Index] = defaultdict(lambda: _Index(cell))
    for s in segs:
        by_space[s.space].add(s.a, s)
        by_space[s.space].add(s.b, s)
    axes: list[_Axis] = []
    unpaired: list[_Bubble] = []
    # every line a bubble could end: nearest end first (half-radius steps), then the longest line
    candidates: dict[int, list[_Seg]] = {}
    for b in bubbles:
        c, r = b.circle.c, b.circle.r
        found: list[tuple[tuple[float, float, int], _Seg]] = []
        for s in by_space[b.circle.space].near(c, END_NEAR_BUBBLE * r):
            if s.length < MIN_AXIS_LENGTH * r:
                continue
            if min(math.dist(c, s.a), math.dist(c, s.b)) > END_NEAR_BUBBLE * r:
                continue
            if _dist_to_line(c, s.a, s.b) > LINE_THROUGH_CENTRE * r:
                continue
            found.append(((round(2 * min(math.dist(c, s.a), math.dist(c, s.b)) / r), -s.length, s.sid), s))
        candidates[id(b)] = [s for _, s in sorted(found, key=lambda t: t[0])]
    for b in bubbles:
        options = candidates[id(b)]
        if not options:
            unpaired.append(b)
            continue
        sheet = ctx.locator.locate(options[0].space, *options[0].mid)
        axes.append(
            _Axis(options[0], [b], "line", sheet if sheet != SHEET_UNKNOWN else b.sheet, options[0].space)
        )
    through, unpaired = _pair_through(unpaired, segs)
    for seg, ends in through:
        sheet = ctx.locator.locate(seg.space, *seg.mid)
        axes.append(_Axis(seg, ends, "line", sheet if sheet != SHEET_UNKNOWN else ends[0].sheet, seg.space))
    # A line of the sheet's axis style through a bubble's centre beats a nearer line of another style it was
    # paired with (EVAL-3 285: the bubbles at the foot of axes 1 and 5 ended wall lines 110 away while their
    # own axes ran on past them). First another end candidate of the style; else a line of the style drawn
    # through the bubbles at both of its ends.
    styles = _sheet_styles(axes)
    off = [
        a
        for a in axes
        if len(a.bubbles) == 1
        and a.pairing == "line"
        and styles.get((a.space, a.sheet), _style(a.seg)) != _style(a.seg)
    ]
    pool: dict[tuple[str, str], list[_Bubble]] = defaultdict(list)
    for a in off:
        style = styles[(a.space, a.sheet)]
        b = a.bubbles[0]
        better = next((s for s in candidates[id(b)] if _style(s) == style), None)
        if better is not None:
            a.seg = better
        else:
            pool[(a.space, a.sheet)].append(b)
    for b in unpaired:
        key = (b.circle.space, b.sheet)
        if key in styles:
            pool[key].append(b)
    seg_sheet: dict[int, str] = {}  # sheet of a line's midpoint, looked up once
    for (space, sheet), members in pool.items():
        style = styles[(space, sheet)]
        r_min = min(b.circle.r for b in members)
        mine = [
            s
            for s in segs
            if s.space == space
            and s.length >= MIN_AXIS_LENGTH * r_min
            and _style(s) == style
            and seg_sheet.setdefault(s.sid, ctx.locator.locate(s.space, *s.mid)) == sheet
        ]
        for seg, ends in _pair_through(members, mine)[0]:
            gone = {id(x) for x in ends}
            axes = [a for a in axes if not any(id(x) in gone for x in a.bubbles)]
            unpaired = [x for x in unpaired if id(x) not in gone]
            where = ctx.locator.locate(seg.space, *seg.mid)
            axes.append(
                _Axis(seg, ends, "line", where if where != SHEET_UNKNOWN else ends[0].sheet, seg.space)
            )
    return _merge_same_line(axes, ctx), unpaired


def _on_segment(c: tuple[float, float], s: _Seg, r: float) -> bool:
    """The line of `s` passes within LINE_THROUGH_CENTRE x r of `c`, and `c` projects inside the segment."""
    if _dist_to_line(c, s.a, s.b) > LINE_THROUGH_CENTRE * r:
        return False
    t = ((c[0] - s.a[0]) * (s.b[0] - s.a[0]) + (c[1] - s.a[1]) * (s.b[1] - s.a[1])) / (s.length**2)
    return 0.0 <= t <= 1.0


def _pair_through(
    bubbles: list[_Bubble], segs: list[_Seg]
) -> tuple[list[tuple[_Seg, list[_Bubble]]], list[_Bubble]]:
    """Bubbles no line END reaches (step 3): a grid line drawn through the bubbles at both of its ends and on
    to the frame (EVAL-3 286). Two bubbles of one label, at least MIN_AXIS_LENGTH radii apart, whose centres
    both lie on one segment make that segment their axis (the longest such segment); a line through one
    bubble alone (a wall through a mark) pairs nothing. Returns (segment, bubbles) pairs and the rest."""
    if not bubbles:
        return [], []
    r_min = min(b.circle.r for b in bubbles)
    step = 4 * statistics.median(b.circle.r for b in bubbles)
    index: dict[str, _Index] = defaultdict(lambda: _Index(step))
    for s in segs:
        if s.length < MIN_AXIS_LENGTH * r_min:
            continue
        n = math.ceil(s.length / step)
        for k in range(n + 1):
            t = k / n
            index[s.space].add((s.a[0] + t * (s.b[0] - s.a[0]), s.a[1] + t * (s.b[1] - s.a[1])), s)
    by_label: dict[tuple[str, str], list[_Bubble]] = defaultdict(list)
    for b in bubbles:
        if b.label:
            by_label[(b.circle.space, b.label)].append(b)
    used: set[int] = set()
    out: list[tuple[_Seg, list[_Bubble]]] = []
    for b in bubbles:
        if id(b) in used or not b.label:
            continue
        c, r = b.circle.c, b.circle.r
        found = {s.sid: s for s in index[b.circle.space].near(c, step)}
        # a segment through both centres, MIN_AXIS_LENGTH radii apart, is at least that long
        candidates = sorted(
            (s for s in found.values() if _on_segment(c, s, r)), key=lambda s: (-s.length, s.sid)
        )
        for s in candidates:
            ends = [
                o
                for o in by_label[(b.circle.space, b.label)]
                if o is not b
                and id(o) not in used
                and math.dist(o.circle.c, c) >= MIN_AXIS_LENGTH * max(r, o.circle.r)
                and _on_segment(o.circle.c, s, o.circle.r)
            ]
            if ends:
                pair = [b, *ends]
                used.update(id(x) for x in pair)
                out.append((s, pair))
                break
    return out, [b for b in bubbles if id(b) not in used]


def _merge_same_line(axes: list[_Axis], ctx: _Ctx) -> list[_Axis]:
    """Bubbles at both ends of one line -> one axis; two labels on one line -> question, both kept."""
    merged: list[_Axis] = []
    by_seg: dict[int, list[_Axis]] = defaultdict(list)
    for a in axes:
        by_seg[a.seg.sid].append(a)
    for _sid, group in sorted(by_seg.items()):
        labels = sorted({a.label or "" for a in group})
        if len(labels) > 1:
            ctx.ask(
                "grid_axis_label_conflict",
                True,
                "One grid line carries bubbles with different labels. Which label is right?",
                f"line {group[0].seg.handle or '?'} on layer '{group[0].seg.layer}'",
                " / ".join(labels),
                group[0].sheet,
            )
        for lbl in labels:
            same = [a for a in group if (a.label or "") == lbl]
            bubbles = [bb for a in same for bb in a.bubbles]
            merged.append(_Axis(same[0].seg, bubbles, "line", same[0].sheet, same[0].space))
    # same label, collinear, different segments (a grid line drawn in pieces): only pieces that overlap
    # or leave a gap of at most END_NEAR_BUBBLE radii are one line (two plans side by side on one sheet
    # share collinear axes with the same label, far apart)
    out: list[_Axis] = []
    for a in merged:
        twin = next(
            (
                o
                for o in out
                if o.sheet == a.sheet
                and o.space == a.space
                and o.label == a.label
                and _angle_diff(o.seg.angle(), a.seg.angle()) < 0.1
                and _dist_to_line(a.seg.a, o.seg.a, o.seg.b) < SAME_LINE_TOL * a.r
                and _dist_to_line(a.seg.b, o.seg.a, o.seg.b) < SAME_LINE_TOL * a.r
                and _collinear_gap(o.seg, a.seg) <= END_NEAR_BUBBLE * max(a.r, o.r)
            ),
            None,
        )
        if twin is None:
            out.append(a)
        else:
            twin.bubbles.extend(a.bubbles)
            if a.seg.length > twin.seg.length:
                twin.seg = a.seg
    return out


def _collinear_gap(s: _Seg, t: _Seg) -> float:
    """Gap between two collinear segments along s (0 when they overlap or touch)."""
    length = s.length
    d = ((s.b[0] - s.a[0]) / length, (s.b[1] - s.a[1]) / length)

    def proj(p: tuple[float, float]) -> float:
        return p[0] * d[0] + p[1] * d[1]

    lo1, hi1 = sorted((proj(s.a), proj(s.b)))
    lo2, hi2 = sorted((proj(t.a), proj(t.b)))
    return max(lo2 - hi1, lo1 - hi2, 0.0)


class _UF:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, i: int) -> int:
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, i: int, j: int) -> None:
        ri, rj = self.find(i), self.find(j)
        if ri != rj:
            self.p[max(ri, rj)] = min(ri, rj)


def _angle_diff(a: float, b: float) -> float:
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def _views(axes: list[_Axis]) -> tuple[list[list[_Axis]], int]:
    by_sheet: dict[tuple[str, str], list[_Axis]] = defaultdict(list)
    for a in axes:
        by_sheet[(a.space, a.sheet)].append(a)
    views: list[list[_Axis]] = []
    isolated = 0
    for key in sorted(by_sheet):
        items = by_sheet[key]
        uf = _UF(len(items))
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                tol = 2 * max(items[i].r, items[j].r)
                if _segments_cross(items[i].seg, items[j].seg, tol):
                    uf.union(i, j)
        comps: dict[int, list[int]] = defaultdict(list)
        for i in range(len(items)):
            comps[uf.find(i)].append(i)
        # parallel-only components join neighbours while labels stay unique
        parallel = [
            root
            for root, idx in comps.items()
            if all(
                _angle_diff(items[i].seg.angle(), items[idx[0]].seg.angle()) < FAMILY_ANGLE_TOL for i in idx
            )
        ]
        pairs = []
        for x in range(len(parallel)):
            for y in range(x + 1, len(parallel)):
                ia, ib = comps[parallel[x]], comps[parallel[y]]
                a0, b0 = items[ia[0]], items[ib[0]]
                if _angle_diff(a0.seg.angle(), b0.seg.angle()) >= FAMILY_ANGLE_TOL:
                    continue
                theta = math.radians(a0.seg.angle())
                d = (math.cos(theta), math.sin(theta))
                n = (-d[1], d[0])

                def span(
                    ids: list[int], vec: tuple[float, float], items: list[_Axis] = items
                ) -> tuple[float, float]:
                    vals = [
                        p[0] * vec[0] + p[1] * vec[1] for i in ids for p in (items[i].seg.a, items[i].seg.b)
                    ]
                    return min(vals), max(vals)

                sa, sb = span(ia, d), span(ib, d)
                overlap = min(sa[1], sb[1]) - max(sa[0], sb[0])
                if overlap < 0.5 * min(sa[1] - sa[0], sb[1] - sb[0]):
                    continue
                oa, ob = span(ia, n), span(ib, n)
                gap = max(ob[0] - oa[1], oa[0] - ob[1], 0.0)
                mean_len = statistics.mean(items[i].seg.length for i in ia + ib)
                if gap <= 0.5 * mean_len:
                    pairs.append((gap, parallel[x], parallel[y]))
        for _gap, ra, rb in sorted(pairs):
            fa, fb = uf.find(ra), uf.find(rb)
            if fa == fb:
                continue
            la = {items[i].label for i in range(len(items)) if uf.find(i) == fa}
            lb = {items[i].label for i in range(len(items)) if uf.find(i) == fb}
            if la & lb:
                continue
            uf.union(fa, fb)
        final: dict[int, list[_Axis]] = defaultdict(list)
        for i in range(len(items)):
            final[uf.find(i)].append(items[i])
        for root in sorted(final):
            comp = final[root]
            if len(comp) < 2:
                isolated += len(comp)
            else:
                views.append(comp)
    return views, isolated


def _offset(seg: _Seg, n: tuple[float, float]) -> float:
    """Signed distance of the line along the family normal, measured at the line's midpoint (a common
    projection: an axis drawn from either end gives the same offset)."""
    m = seg.mid
    return m[0] * n[0] + m[1] * n[1]


def _family_frame(theta: float) -> tuple[tuple[float, float], tuple[float, float]]:
    t = math.radians(theta)
    d = (math.cos(t), math.sin(t))
    n = (-d[1], d[0])
    if n[0] < -1e-9 or (abs(n[0]) <= 1e-9 and n[1] < 0):
        n = (-n[0], -n[1])
    return d, n


def _families(group: _Group, next_id: list[int]) -> None:
    """Cluster the axes of a view by direction. Angles are circular (179.6 and -0.4 degrees are one
    direction), so clusters that meet across the wrap are joined. The family angle is the median of its
    axes' angles (one skewed axis does not tilt the others)."""
    axes = sorted(group.axes, key=lambda a: (a.seg.angle(), a.seg.sid))
    clusters: list[list[_Axis]] = []
    for a in axes:
        if clusters and _angle_diff(a.seg.angle(), clusters[-1][0].seg.angle()) < FAMILY_ANGLE_TOL:
            clusters[-1].append(a)
        else:
            clusters.append([a])
    if len(clusters) > 1 and _angle_diff(clusters[-1][0].seg.angle(), clusters[0][0].seg.angle()) < (
        FAMILY_ANGLE_TOL
    ):
        clusters[0] = clusters.pop() + clusters[0]
    for members in clusters:
        ref = members[0].seg.angle()
        devs = sorted(_signed_angle(m.seg.angle(), ref) for m in members)
        theta = _canonical_angle(ref + statistics.median_low(devs))
        d, n = _family_frame(theta)
        for m in members:
            m.offset = _offset(m.seg, n)
            m.dev = _signed_angle(m.seg.angle(), theta)
        members.sort(key=lambda m: (m.offset, m.seg.sid))
        next_id[0] += 1
        group.families.append(_Family(f"F{next_id[0]:03d}", members, theta, d, n))


def _label_height(a: _Axis) -> float | None:
    for b in a.bubbles:
        if b.entry is not None and b.entry.get("height"):
            return float(b.entry["height"])
    return None


def _axis_deviations(axes: list[_Axis]) -> dict[int, list[str]]:
    """axis index -> the things (size, block, line) in which it differs from its family (see FAMILY_*);
    deviating axes only."""
    n = len(axes)
    out: dict[int, list[str]] = defaultdict(list)
    if n < FAMILY_MIN_AXES:
        return out
    off_size: set[int] = set()
    for values in ([a.r for a in axes], [_label_height(a) for a in axes]):
        known = [v for v in values if v]
        if len(known) < FAMILY_MIN_AXES:
            continue
        med = statistics.median(known)
        off_size |= {k for k, v in enumerate(values) if v and abs(v - med) > FAMILY_SIZE_TOL * med}
    for k in sorted(off_size):
        out[k].append("size")
    for name, keys in (
        ("block", [a.bubbles[0].circle.block_path[:1] for a in axes]),
        ("line", [_style(a.seg) if a.pairing == "line" else None for a in axes]),
    ):
        counts = Counter(k for k in keys if k is not None)
        top = counts.most_common(1)
        if top and top[0][1] * 2 > sum(counts.values()):
            for k, key in enumerate(keys):
                if key is not None and key != top[0][0]:
                    out[k].append(name)
    return out


def _set_aside(group: _Group, ctx: _Ctx) -> list[_Bubble]:
    """Remove from the families of `group` the axes that differ from their family in at least
    FAMILY_MIN_DEVIATIONS attributes (a section marker, a rebar bubble, a bar mark drawn like a grid bubble);
    returns their bubbles for the unpaired list and says in the warnings which axes and why. An axis is
    never set aside from a family left with fewer than two others."""
    aside: list[_Bubble] = []
    notes: list[str] = []
    for fam in group.families:
        dev = _axis_deviations(fam.axes)
        gone = [k for k, why in dev.items() if len(why) >= FAMILY_MIN_DEVIATIONS]
        if not gone or len(fam.axes) - len(gone) < 2:
            continue
        for k in sorted(gone, reverse=True):
            axis = fam.axes.pop(k)
            group.axes.remove(axis)
            aside.extend(axis.bubbles)
            notes.append(f"{axis.label or '?'} ({', '.join(dev[k])})")
    if notes:
        ctx.warnings.append(
            f"{group.gid} on {group.sheet}: set aside {len(notes)} axis(es) that differ from the rest of "
            f"their family (listed as unpaired bubbles): {'; '.join(notes[:20])}."
        )
    return aside


def _check_family(fam: _Family, group: _Group, ctx: _Ctx) -> None:
    sheet = group.sheet
    labels = fam.labels()
    r = fam.r()
    for a, b in zip(fam.axes, fam.axes[1:], strict=False):
        if abs(b.offset - a.offset) < SAME_LINE_TOL * r and a.label != b.label:
            fam.issues.add("label_conflict")
            ctx.ask(
                "grid_axis_label_conflict",
                True,
                "Two differently labelled axes lie on the same line. Which label is right?",
                f"{group.gid}/{fam.fid}",
                f"{a.label} / {b.label}",
                sheet,
            )
    seen = Counter(lbl for lbl in labels if lbl)
    dups = sorted(lbl for lbl, n in seen.items() if n > 1)
    if dups:
        fam.issues.add("duplicate")
        ctx.ask(
            "grid_label_duplicate",
            True,
            "The same axis label appears at different positions in one view. Which position is right?",
            f"{group.gid}/{fam.fid}",
            ", ".join(dups),
            sheet,
        )
    # not parallel: the axis drifts, end to end, by more than half the proposal's rounding step from the
    # family direction, so its spacing to the neighbours changes along it
    step = rounding_step(fam.spacings)
    for a in fam.axes:
        drift = a.seg.length * math.sin(math.radians(abs(a.dev)))
        if drift > step / 2:
            fam.issues.add("not_parallel")
            ctx.ask(
                "grid_axis_not_parallel",
                True,
                "This axis is not parallel to the rest of its family; the spacing changes along it. "
                "Is the axis really skewed, or is the drawing inaccurate?",
                f"{group.gid}/{fam.fid} axis {a.label}",
                f"{rnum(a.dev)} degrees off: drifts {rnum(drift)} drawing units over its length "
                f"(rounding step {rnum(step)})",
                sheet,
            )
    styles = Counter((a.seg.layer, a.seg.linetype) for a in fam.axes if a.pairing == "line")
    if len(styles) > 1:
        top = styles.most_common()
        majority = top[0][0] if top[0][1] > top[1][1] else None
        odd = [a for a in fam.axes if a.pairing == "line" and (a.seg.layer, a.seg.linetype) != majority]
        fam.issues.add("layer_mismatch")
        ctx.ask(
            "grid_axis_layer_mismatch",
            True,
            "Axes of this family are drawn on different layers or linetypes; a line of another kind (a "
            "section cut, a wall line) may have been taken as a grid axis. Which lines are grid axes?",
            f"{group.gid}/{fam.fid}",
            (f"majority {majority[0]}/{majority[1]}; " if majority else "no majority layer/linetype; ")
            + "; ".join(f"axis {a.label}: {a.seg.layer}/{a.seg.linetype}" for a in odd[:20]),
            sheet,
        )
    kinds = {lbl[0].isdigit() for lbl in labels if lbl}
    if len(kinds) > 1:
        fam.issues.add("mixed_kinds")
        ctx.ask(
            "grid_label_kind_mixed",
            True,
            "Number and letter labels are mixed in one family (numbers run one way and letters the other); "
            "a bubble may belong to something else (a mark, a detail). Which labels are grid axes?",
            f"{group.gid}/{fam.fid}",
            " ".join(lbl or "?" for lbl in labels),
            sheet,
        )
    named = [lbl for lbl in labels if lbl]
    if len(kinds) == 1 and _label_order_broken(named):
        fam.issues.add("label_order")
        ctx.ask(
            "grid_label_order_nonmonotonic",
            True,
            "The axis labels of this family do not run in one direction along the family (e.g. 1 3 2 4): "
            "a label is misplaced or a bubble belongs to another line. Which order is right?",
            f"{group.gid}/{fam.fid}",
            " ".join(named),
            sheet,
        )
    gap = None if "label_order" in fam.issues else _label_seq_gap(named)
    if gap is not None and len(fam.axes) >= 2:
        ctx.ask(
            "grid_label_sequence_gap",
            False,
            "Axis labels skip a value in this family (letters I and O are often skipped; that "
            "convention is unverified). Is an axis missing from the drawing?",
            f"{group.gid}/{fam.fid}",
            gap,
            sheet,
        )
    if fam.axes and abs(((fam.theta % 90.0) + 45.0) % 90.0 - 45.0) > ORTHO_TOL and len(fam.axes) >= 2:
        ctx.ask(
            "grid_rotated",
            False,
            "This grid family is rotated relative to the sheet axes. Confirm the rotation (Tekla needs it "
            "as the grid's work plane or origin rotation).",
            f"{group.gid}/{fam.fid}",
            f"{rnum(fam.theta)} degrees",
            sheet,
        )


def _check_view(group: _Group, ctx: _Ctx) -> None:
    big = [f for f in group.families if len(f.axes) >= 2]
    for f in group.families:
        if (
            len(f.axes) == 1
            and big
            and all(abs(_angle_diff(f.theta, g.theta) - 90.0) > ORTHO_TOL for g in big)
        ):
            f.issues.add("skewed")
            ctx.ask(
                "grid_axis_skewed",
                True,
                "A single axis crosses this view at an angle that is neither parallel nor perpendicular "
                "to the other axes. Is it a skewed grid line (Tekla needs a separate grid or line)?",
                f"{group.gid}/{f.fid} axis {f.axes[0].label}",
                f"{rnum(f.theta)} degrees",
                group.sheet,
            )
    for i in range(len(big)):
        for j in range(i + 1, len(big)):
            angle = _angle_diff(big[i].theta, big[j].theta)
            if abs(angle - 90.0) > ORTHO_TOL:
                big[i].issues.add("non_orthogonal")
                big[j].issues.add("non_orthogonal")
                ctx.ask(
                    "grid_non_orthogonal",
                    True,
                    "Two grid families of one view are not perpendicular; a Tekla rectangular grid cannot "
                    "represent them. How should this grid be modelled?",
                    f"{group.gid}/{big[i].fid},{big[j].fid}",
                    f"{rnum(angle)} degrees between families",
                    group.sheet,
                )


def _unlabelled(groups: list[_Group], segs: list[_Seg], empty: list[_Circle], ctx: _Ctx) -> None:
    used = {a.seg.sid for g in groups for f in g.families for a in f.axes}
    by_style: dict[tuple[str, str, str], list[_Seg]] = defaultdict(list)
    for s in segs:
        if s.sid not in used:
            by_style[(s.space, s.layer, s.linetype)].append(s)
    for g in groups:
        for fam in g.families:
            if len(fam.axes) < 2:
                continue
            style = Counter((a.seg.space, a.seg.layer, a.seg.linetype) for a in fam.axes).most_common(1)[0][0]
            max_spacing = max(fam.spacings) if fam.spacings else 0.0
            spans = [
                tuple(
                    sorted(
                        (
                            a.seg.a[0] * fam.d[0] + a.seg.a[1] * fam.d[1],
                            a.seg.b[0] * fam.d[0] + a.seg.b[1] * fam.d[1],
                        )
                    )
                )
                for a in fam.axes
            ]
            med_len = statistics.median(a.seg.length for a in fam.axes)
            r = fam.r()
            offsets = [a.offset for a in fam.axes]
            for s in by_style.get(style, ()):
                if ctx.locator.locate(s.space, *s.mid) != g.sheet:
                    continue
                if _angle_diff(s.angle(), fam.theta) > 0.1 or s.length < 0.5 * med_len:
                    continue
                off = _offset(s, fam.n)
                if min(abs(off - o) for o in offsets) < SAME_LINE_TOL * r:
                    continue
                # a further axis lies next to the family (within 1.5 max spacings) and runs alongside it
                if not (min(offsets) - 1.5 * max_spacing <= off <= max(offsets) + 1.5 * max_spacing):
                    continue
                # ... and starts and ends where one of the family's axes does (grid lines of a view are
                # drawn to common extents; wall and beam lines are not)
                lo, hi = sorted(
                    (s.a[0] * fam.d[0] + s.a[1] * fam.d[1], s.b[0] * fam.d[0] + s.b[1] * fam.d[1])
                )
                end_tol = max(2 * r, 0.05 * med_len)
                if not any(abs(lo - alo) <= end_tol and abs(hi - ahi) <= end_tol for alo, ahi in spans):
                    continue
                bubble = any(
                    c.space == s.space
                    and _dist_to_line(c.c, s.a, s.b) <= LINE_THROUGH_CENTRE * c.r
                    and min(math.dist(c.c, s.a), math.dist(c.c, s.b)) <= END_NEAR_BUBBLE * c.r
                    for c in empty
                )
                fam.unlabelled.append((off - fam.axes[0].offset, s, bubble))
                fam.issues.add("unlabelled")
                if bubble:
                    ctx.ask(
                        "grid_label_missing",
                        True,
                        "A grid line of this family ends in an empty bubble: its label is missing. "
                        "What is the axis label (or is it not an axis)?",
                        f"{g.gid}/{fam.fid} line {s.handle or '?'}",
                        f"offset {rnum(off - fam.axes[0].offset)} from axis {fam.axes[0].label}",
                        g.sheet,
                    )
                else:
                    ctx.ask(
                        "grid_axis_unlabelled",
                        True,
                        "A line on this family's grid layer and linetype looks like a further axis but has "
                        "no "
                        "bubble. Is it a grid axis, and what is its label?",
                        f"{g.gid}/{fam.fid} line {s.handle or '?'}",
                        f"offset {rnum(off - fam.axes[0].offset)} from axis {fam.axes[0].label}",
                        g.sheet,
                    )
            fam.unlabelled.sort(key=lambda t: (t[0], t[1].sid))


def _same_kind(label: str, labels: list[str | None]) -> bool:
    """Numbers run one way and letters the other (verified at grade B): a fallback axis must match."""
    kinds = {lbl[0].isdigit() for lbl in labels if lbl}
    return kinds == {label[0].isdigit()}


def _two_bubble_axes(
    groups: list[_Group], unpaired: list[_Bubble], ctx: _Ctx, next_axis: list[int]
) -> list[_Bubble]:
    """Same-label bubble pairs with no line that join an existing view (low)."""
    by_key: dict[tuple[str, str, str], list[_Bubble]] = defaultdict(list)
    for b in unpaired:
        if b.label:
            by_key[(b.circle.space, b.sheet, b.label)].append(b)
    still = list(unpaired)
    for (space, sheet, label), pair in sorted(by_key.items()):
        if len(pair) != 2:
            continue
        a, b = pair
        r = max(a.circle.r, b.circle.r)
        if math.dist(a.circle.c, b.circle.c) < MIN_AXIS_LENGTH * r:
            continue
        seg = _Seg(-1 - next_axis[0], a.circle.c, b.circle.c, space, "", "", None, ())
        for g in groups:
            if g.sheet != sheet or g.space != space:
                continue
            fam = next((f for f in g.families if _angle_diff(f.theta, seg.angle()) < FAMILY_ANGLE_TOL), None)
            if fam is None or label in fam.labels() or not _same_kind(label, fam.labels()):
                continue
            others = [x for f in g.families if f is not fam for x in f.axes]
            if not any(_segments_cross(seg, x.seg, 2 * r) for x in others):
                continue
            next_axis[0] += 1
            axis = _Axis(seg, [a, b], "two_bubbles", sheet, space)
            axis.offset = _offset(seg, fam.n)
            axis.dev = _signed_angle(seg.angle(), fam.theta)
            fam.axes.append(axis)
            fam.axes.sort(key=lambda m: (m.offset, m.seg.sid))
            fam.issues.add("two_bubbles")
            g.axes.append(axis)
            still = [x for x in still if x is not a and x is not b]
            ctx.ask(
                "grid_two_bubble_axis",
                True,
                "Two bubbles with the same label face each other with no grid line between them; the axis is "
                "assumed to run between their centres. Is that right?",
                f"{g.gid}/{fam.fid}",
                label,
                sheet,
            )
            break
    return still


def _match_dimensions(groups: list[_Group], dims: list[_Dim]) -> int:
    matched = 0
    cos_tol = math.cos(math.radians(FAMILY_ANGLE_TOL))
    for dim in dims:
        for g in groups:
            if g.space != dim.space or g.sheet != dim.sheet:
                continue
            done = False
            for fam in g.families:
                if len(fam.axes) < 2 or abs(dim.u[0] * fam.n[0] + dim.u[1] * fam.n[1]) < cos_tol:
                    continue
                tol = DIM_POINT_TOL * fam.r()
                i = next(
                    (k for k, a in enumerate(fam.axes) if _dist_to_line(dim.p1, a.seg.a, a.seg.b) <= tol),
                    None,
                )
                j = next(
                    (k for k, a in enumerate(fam.axes) if _dist_to_line(dim.p2, a.seg.a, a.seg.b) <= tol),
                    None,
                )
                if i is None or j is None or i == j:
                    continue
                i, j = min(i, j), max(i, j)
                span = fam.axes[j].offset - fam.axes[i].offset
                if abs(abs(dim.measured) - span) > max(1e-6 * span, tol):
                    continue
                shown = str(plain_mtext(dim.text)).strip() if dim.text else ""
                if shown in ("", "<>") or "<>" in shown:
                    # the shown value is the measurement of the same geometry: evidence, not a cross-check
                    displayed: float | None = dim.measured * dim.dimlfac
                    status = "measured" if math.isclose(dim.dimlfac, 1.0) else "scaled"
                elif _NUMBER_RE.match(shown):
                    displayed = float(shown)
                    expected = span * dim.dimlfac
                    tol_text = max(0.5 * 10.0 ** (-max(0, min(dim.dimdec, 16))), 1e-9 * abs(expected))
                    status = "agrees" if abs(displayed - expected) <= tol_text else "differs"
                else:
                    displayed, status = None, "not_numeric"
                ev = {
                    "handle": dim.handle,
                    "from_label": fam.axes[i].label,
                    "to_label": fam.axes[j].label,
                    "measured": rnum(dim.measured),
                    "dimlfac": rnum(dim.dimlfac),
                    "displayed": rnum(displayed) if displayed is not None else None,
                    "text": dim.text,
                    "status": status,
                }
                # only a dimension between neighbouring axes checks one spacing; an overall (span)
                # dimension checks a sum and is evidence only (a disagreeing one is still a question)
                kind = "dimension_adjacent" if j == i + 1 else "dimension_span"
                if status != "not_numeric":
                    ref = (
                        f"dimension {dim.handle or '?'} {fam.axes[i].label}-{fam.axes[j].label} "
                        f"text '{dim.text}' ({status})"
                    )
                    item = {
                        "kind": kind,
                        "agrees": status != "differs",
                        "independent": status in ("agrees", "differs"),
                        "ref": ref,
                    }
                    for k in range(i, j):
                        fam.evidence[k].append(item)
                for k in range(i, j):
                    fam.dim_evidence[k].append(ev)
                matched += 1
                done = True
                break
            if done:
                break
    return matched


class _Copies:
    """Which sheets are copies of one another: sheets.json duplicate_of, or near-identical texts."""

    def __init__(self, sheets_result: dict[str, Any], text_index: dict[str, Any]):
        sheets = sheets_result["sheets"]
        self.root = {s["sheet_id"]: s["duplicate_of"] for s in sheets if s.get("duplicate_of")}
        by_id = {e["id"]: e["display_text"] for e in text_index["entries"]}
        self.texts = {s["sheet_id"]: Counter(by_id[t] for t in s["text_ids"] if t in by_id) for s in sheets}
        self._cache: dict[frozenset[str], bool] = {}

    def linked(self, a: str, b: str) -> bool:
        if a == b:
            return True
        if self.root.get(a, a) == self.root.get(b, b):
            return True
        key = frozenset((a, b))
        if key not in self._cache:
            ta, tb = self.texts.get(a), self.texts.get(b)
            if not ta or not tb:
                self._cache[key] = False
            else:
                union = sum((ta | tb).values())
                self._cache[key] = sum((ta & tb).values()) >= NEAR_IDENTICAL_TEXTS * union
        return self._cache[key]


def _pairs_text(diffs: list[dict[str, Any]]) -> str:
    return "; ".join(f"{d['from_label']}-{d['to_label']}: {d['first']} vs {d['second']}" for d in diffs)


def _not_independent(ga: _Group, fa: _Family, gb: _Group, fb: _Family, copies: _Copies) -> str | None:
    """Why two families do not check each other independently, or None when they do."""
    if ga.sheet == gb.sheet:
        return "same sheet"
    if copies.linked(ga.sheet, gb.sheet):
        return "copied sheets"
    roots_a = {a.seg.block_path[0] for a in fa.axes if a.seg.block_path}
    roots_b = {b.seg.block_path[0] for b in fb.axes if b.seg.block_path}
    if roots_a & roots_b:
        return f"same block {sorted(roots_a & roots_b)[0]}"
    return None


def _cross_checks(families: list[tuple[_Group, _Family]], ctx: _Ctx, copies: _Copies) -> list[dict[str, Any]]:
    """Every pair of families sharing >= 2 labels. Each compared neighbouring pair becomes `other_view`
    evidence on both families (independent unless same sheet, copied sheets or the same block)."""
    out: list[dict[str, Any]] = []
    for x in range(len(families)):
        ga, fa = families[x]
        la = fa.labels()
        if len(la) < 2 or "duplicate" in fa.issues:
            continue
        for y in range(x + 1, len(families)):
            gb, fb = families[y]
            lb = fb.labels()
            if "duplicate" in fb.issues:
                continue
            common = [lbl for lbl in la if lbl and lbl in lb]
            if len(common) < 2:
                continue
            pa = dict(zip(la, fa.rel_offsets, strict=True))
            pb = dict(zip(lb, fb.rel_offsets, strict=True))
            seq_b = [pb[lbl] for lbl in common]
            inc = all(q > p for p, q in pairwise(seq_b))
            dec = all(q < p for p, q in pairwise(seq_b))
            row: dict[str, Any] = {
                "families": [fa.fid, fb.fid],
                "sheets": [ga.sheet, gb.sheet],
                "common_labels": common,
                "status": "consistent",
                "ratio": None,
                "differences": [],
            }
            where = f"{ga.gid}/{fa.fid} ({ga.sheet}) vs {gb.gid}/{fb.fid} ({gb.sheet})"
            if not (inc or dec):
                row["status"] = "order_mismatch"
                ctx.ask(
                    "grid_label_order_mismatch",
                    True,
                    "The same axis labels come in a different order in two views. Which order is right?",
                    where,
                    f"{' '.join(common)} vs {' '.join(sorted(common, key=lambda lbl: pb[lbl]))}",
                    ga.sheet,
                )
                out.append(row)
                continue
            step = max(rounding_step(fa.spacings), rounding_step(fb.spacings))
            diffs, ratios = [], []
            for p, q in pairwise(common):
                da, db = abs(pa[q] - pa[p]), abs(pb[q] - pb[p])
                ratios.append(da / db if db else math.inf)
                if abs(da - db) > max(step / 2, 1e-9 * da):
                    diffs.append({"from_label": p, "to_label": q, "first": rnum(da), "second": rnum(db)})
            tolerated: set[frozenset[str]] = set()
            bad: set[frozenset[str]] = set()
            if diffs:
                finite = [r for r in ratios if math.isfinite(r)]
                # one constant ratio needs at least two compared spacings: with one, any difference
                # would pass as 'scaled' (non-blocking) and hide a real mismatch
                same_ratio = (
                    len(ratios) >= 2
                    and len(finite) == len(ratios)
                    and max(finite) - min(finite) <= SCALE_TOL * max(finite)
                )
                row["differences"] = diffs
                if same_ratio and abs(finite[0] - 1.0) > SCALE_TOL:
                    row["status"], row["ratio"] = "scaled", rnum(statistics.mean(finite))
                    bad = {frozenset((d["from_label"], d["to_label"])) for d in diffs}
                    ctx.ask(
                        "grid_scale_differs",
                        False,
                        "Two views show the same axes with all spacings in one constant ratio (a view drawn "
                        "at another scale?). Which view holds the true-size grid?",
                        f"{ga.gid}/{fa.fid} vs {gb.gid}/{fb.fid}",
                        f"ratio {rnum(statistics.mean(finite))}",
                        ga.sheet,
                    )
                else:
                    small = [
                        d
                        for d in diffs
                        if abs(d["first"] - d["second"]) <= DRAFTING_TOL * max(d["first"], d["second"])
                    ]
                    big = [d for d in diffs if d not in small]
                    tolerated = {frozenset((d["from_label"], d["to_label"])) for d in small}
                    bad = {frozenset((d["from_label"], d["to_label"])) for d in big}
                    row["status"] = "mismatch" if big else "drafting_tolerance"
                    if big:
                        ctx.ask(
                            "grid_spacing_cross_sheet_mismatch",
                            True,
                            "The same axes have different spacings in two views. Which spacing is right?",
                            where,
                            _pairs_text(big),
                            ga.sheet,
                        )
                    if small:
                        ctx.ask(
                            "grid_spacing_drafting_tolerance",
                            False,
                            f"The same axes differ between two views by at most {DRAFTING_TOL:g} of the "
                            "spacing (a drafting inaccuracy?). Which value is meant?",
                            where,
                            _pairs_text(small),
                            ga.sheet,
                        )
            why = _not_independent(ga, fa, gb, fb, copies)
            compared = {frozenset((p, q)) for p, q in pairwise(common)}
            for fam, labels, other_g, other_f in ((fa, la, gb, fb), (fb, lb, ga, fa)):
                for k in range(len(labels) - 1):
                    key = frozenset((labels[k], labels[k + 1]))
                    if key not in compared:
                        continue
                    note = (
                        "differs"
                        if key in bad
                        else "agrees within drafting tolerance"
                        if key in tolerated
                        else "agrees"
                    )
                    fam.evidence[k].append(
                        {
                            "kind": "other_view",
                            "agrees": key not in bad,
                            "independent": why is None,
                            "ref": f"{other_g.gid}/{other_f.fid} on sheet {other_g.sheet}: {note}"
                            + (f" (not independent: {why})" if why else ""),
                        }
                    )
            out.append(row)
    return out


def extract_grids(
    dxf_path: str | Path,
    text_index: dict[str, Any],
    sheets_result: dict[str, Any],
    *,
    doc: Drawing | None = None,
) -> dict[str, Any]:
    """Grid axes of one DXF. See the module docstring for the rules."""
    doc = open_checked(dxf_path, text_index, doc)
    if sheets_result["file"]["sha256"] != text_index["file"]["sha256"]:
        raise ValueError("sheets result was built from another file")
    ctx = _Ctx(
        text_index["file"]["path"],
        text_index["file"]["confidence_cap"],
        declared_units(doc),
        SheetLocator(sheets_result),
    )
    walker = Walker(doc, bool(text_index["file"]["handles_reliable"]))
    segs, circles, caps, dims = _collect(doc, walker, ctx)
    circles += _obround_circles(caps, segs)
    found = _find_bubbles(circles, text_index["entries"], ctx)
    bubbles, ambiguous, other_text, empty, unreadable, blocked = found
    axes, unpaired = _pair(bubbles, segs, ctx)
    views, isolated = _views(axes)
    groups: list[_Group] = []
    fam_counter = [0]
    aside: list[_Bubble] = []  # axes set aside as no member of their family: unpaired, never dropped silently
    for k, comp in enumerate(views, start=1):
        g = _Group(f"V{k:03d}", comp[0].sheet, comp[0].space, comp)
        _families(g, fam_counter)
        groups.append(g)
    unpaired = _two_bubble_axes(groups, unpaired, ctx, [0])
    for g in groups:
        aside.extend(_set_aside(g, ctx))
        g.families = [f for f in g.families if f.axes]
    unpaired = unpaired + aside
    axis_no = 0
    for g in groups:
        for fam in g.families:
            for a in fam.axes:
                axis_no += 1
                a.aid = f"G{axis_no:04d}"
            fam.spacings = [b.offset - a.offset for a, b in zip(fam.axes, fam.axes[1:], strict=False)]
            _check_family(fam, g, ctx)
        _check_view(g, ctx)
    _unlabelled(groups, segs, empty + unreadable, ctx)  # a blocked label is a missing label for the line
    matched = _match_dimensions(groups, dims)
    all_fams = [(g, f) for g in groups for f in g.families]
    cross = _cross_checks(all_fams, ctx, _Copies(sheets_result, text_index))

    unit = ctx.units["name"]
    # the units evidence is the median over VIEWS of each view's median spacing: a key plan drawn small on one
    # sheet (EVAL-4 180: spacings about 300 beside plans of 8000) outvoted by every real plan, not by the
    # number of its spacings
    view_medians = [
        statistics.median(s for f in g.families for s in f.spacings if s > 0)
        for g in groups
        if any(s > 0 for f in g.families for s in f.spacings)
    ]
    families_found = [f for _, f in all_fams if len(f.axes) >= 2]
    if not families_found:
        ctx.ask(
            "grid_none_found",
            True,
            "No grid (two or more labelled axes) was found. Where are the grid axes defined?",
            ctx.file_path,
            f"{len(bubbles)} labelled circle(s), {len(axes)} axis line(s)",
        )
    else:
        ctx.ask(
            "grid_family_axis_assignment",
            False,
            "Not blocking: Tekla X / Y is asked once per grid system by `harness grid-system` "
            "(grid_system_axis_unassigned, --value dir1=X --value dir2=Y). Optionally, which grid family is "
            "Tekla X (lines parallel to Y) and which is Y? Directions are given per family.",
            listed(f.fid for f in families_found),
            "; ".join(
                f"{f.fid}: dir ({rnum(f.d[0])}, {rnum(f.d[1])}) "
                f"labels {' '.join(lbl or '?' for lbl in f.labels())}"
                for f in families_found[:20]
            ),
        )
        ctx.ask(
            "grid_gate1_confirmation",
            True,
            "Gate 1: confirm the grid families, labels, spacings and proposed coordinate strings (RTI-0003).",
            listed(f.fid for f in families_found),
            f"{len(families_found)} family(ies) in {len(groups)} view(s)",
        )
        median = statistics.median(view_medians) if view_medians else 0.0
        factor = _METRES.get(unit)
        metres = median * factor if factor else None
        if metres is None or not (PLAUSIBLE_SPACING_M[0] <= metres <= PLAUSIBLE_SPACING_M[1]):
            ctx.ask(
                "grid_units_doubt",
                False,
                "Evidence for this file's units_confirm_all question (intake), which is the one to answer "
                "(--value unit=...): the declared drawing unit makes the grid spacings implausible for a "
                "building (or no unit is declared).",
                "header $INSUNITS",
                f"median spacing {rnum(median)} drawing units (median of {len(view_medians)} view medians), "
                f"declared unit '{unit}'" + (f" = {rnum(metres)} m" if metres is not None else ""),
            )
    groups_json: list[dict[str, Any]] = []
    for g in groups:
        fams_json = []
        for fam in g.families:
            fams_json.append(_family_json(fam, g, ctx, unit))
        boxes = [a.seg.box() for a in g.axes]
        gbox = (
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        )
        groups_json.append(
            {"group_id": g.gid, "sheet": g.sheet, "space": g.space, "bbox": rbox(gbox), "families": fams_json}
        )

    for code, n in sorted(ctx.q_counts.items()):
        if n > MAX_QUESTIONS_PER_CODE:
            ctx.warnings.append(
                f"{n} '{code}' questions; only the first {MAX_QUESTIONS_PER_CODE} are listed."
            )
    for reason, n in sorted(walker.skipped.items()):
        ctx.warnings.append(f"{n} entit(ies)/insert(s) not read while walking the drawing: {reason}.")
    ctx.warnings.extend(_not_printed_warnings(ctx))

    unpaired_sorted = sorted(unpaired, key=lambda b: (b.circle.space, b.sheet, b.circle.c))
    return {
        "schema_version": SCHEMA_VERSION,
        "file": {
            "path": ctx.file_path,
            "sha256": text_index["file"]["sha256"],
            "confidence_cap": ctx.cap,
            "declared_units": ctx.units,
        },
        "groups": groups_json,
        "cross_checks": cross,
        "unpaired_bubbles": {
            "count": len(unpaired),
            "listed": [b.as_json() for b in unpaired_sorted[:MAX_UNPAIRED_LISTED]],
        },
        "blocked_candidates": blocked,
        "summary": {
            "circles": len(circles),
            "bubbles_labelled": len(bubbles),
            "bubbles_ambiguous_label": ambiguous,
            "bubbles_other_text": other_text,
            "bubbles_paired": sum(len(a.bubbles) for g in groups for f in g.families for a in f.axes),
            "axes": axis_no,
            "groups": len(groups),
            "families": len(all_fams),
            "isolated_axes": isolated,
            "dimensions_linear": len(dims),
            "dimensions_matched": matched,
            "walk_skipped": dict(sorted(walker.skipped.items())),
            "blocked_candidates": len(blocked),
        },
        "questions": ctx.questions,
        "question_counts": dict(sorted(ctx.q_counts.items())),
        "warnings": ctx.warnings,
    }


def _not_printed_warnings(ctx: _Ctx) -> list[str]:
    """What was left out because it does not print (counted apart; the grids schema has no counter field)."""
    out = []
    if ctx.not_printed_text:
        out.append(
            f"{ctx.not_printed_text} text(s) not printed (text index printed: false): left out of every "
            "bubble label."
        )
    for kind in ("line", "circle", "dimension"):
        parts = {
            k.split(":", 1)[1]: n for k, n in ctx.not_printed_geometry.items() if k.startswith(f"{kind}:")
        }
        if parts:
            detail = ", ".join(f"{r} {n}" for r, n in sorted(parts.items()))
            out.append(
                f"{sum(parts.values())} {kind}(s) not printed ({detail}): left out of bubbles, axes and "
                "dimension evidence."
            )
    return out


def _label_json(a: _Axis, ctx: _Ctx) -> dict[str, Any] | None:
    b = next((b for b in a.bubbles if b.entry is not None), None)
    if b is None or b.entry is None:
        return None
    e = b.entry
    conf = min_conf(e["confidence"], ctx.cap)
    if set(e["flags"]) & {"layer_off", "layer_frozen", "attribute_invisible"} or a.pairing == "two_bubbles":
        conf = "low"
    box = text_box(e) or (b.circle.c[0], b.circle.c[1], b.circle.c[0], b.circle.c[1])
    return {"value": e["display_text"].strip(), "provenance": ctx.prov(a.sheet, box), "confidence": conf}


def _span(fam: _Family, ev: dict[str, Any]) -> float:
    pos = {a.label: a.offset for a in fam.axes}
    return abs(pos.get(ev["to_label"], 0.0) - pos.get(ev["from_label"], 0.0))


def _family_json(fam: _Family, g: _Group, ctx: _Ctx, unit: str) -> dict[str, Any]:
    step = rounding_step(fam.spacings)
    labels_conf = []
    axes_json = []
    for a in fam.axes:
        label = _label_json(a, ctx)
        labels_conf.append(label["confidence"] if label else "low")
        axes_json.append(
            {
                "axis_id": a.aid,
                "label": label,
                "offset": rnum(a.offset - fam.axes[0].offset),
                "line": a.seg.line_json(),
                "bubbles": [b.as_json() for b in a.bubbles],
                "pairing": a.pairing,
                "angle_deviation_deg": rnum(a.dev),
                # pairing a bubble with a line is a heuristic: never above medium
                "confidence": min_conf(label["confidence"], MAX_CONFIDENCE) if label else "low",
            }
        )
    spacings_json = []
    rounded = []
    residual = 0.0
    spacing_issue = False
    for k, s in enumerate(fam.spacings):
        a, b = fam.axes[k], fam.axes[k + 1]
        val = _round_to(s, step)
        rounded.append(val)
        residual = max(residual, abs(s - val))
        ev = fam.dim_evidence.get(k, [])
        evidence = fam.evidence.get(k, [])
        # never 'high' here: agreeing evidence is kept as data for gate 1. A disagreeing dimension (adjacent
        # or span), or another view disagreeing with no independent view agreeing, makes the spacing low
        # (the question stays blocking either way)
        views = [e for e in evidence if e["kind"] == "other_view"]
        dims_bad = any(not e["agrees"] for e in evidence if e["kind"] != "other_view")
        # only an INDEPENDENT agreeing view outweighs a disagreeing one (a copy of the sheet, a plan on the
        # same sheet or the same block agreeing proves nothing)
        views_bad = any(not e["agrees"] for e in views) and not any(
            e["agrees"] and e["independent"] for e in views
        )
        conf = "low" if dims_bad or views_bad else MAX_CONFIDENCE
        conf = min_conf(conf, labels_conf[k], labels_conf[k + 1], ctx.cap)
        if "not_parallel" in fam.issues:
            conf = "low"
        if conf == "low":
            spacing_issue = True
        box = (
            min(a.seg.box()[0], b.seg.box()[0]),
            min(a.seg.box()[1], b.seg.box()[1]),
            max(a.seg.box()[2], b.seg.box()[2]),
            max(a.seg.box()[3], b.seg.box()[3]),
        )
        derived = [ctx.prov(a.sheet, a.seg.box()), ctx.prov(b.sheet, b.seg.box())]
        spacings_json.append(
            {
                "from_label": a.label,
                "to_label": b.label,
                "measured": rnum(s),
                "value": {
                    "value": rnum(val),
                    "provenance": ctx.prov(g.sheet, box, method="derived", derived_from=derived),
                    "confidence": conf,
                },
                "dimension_evidence": ev,
                "evidence": evidence,
            }
        )
        for e in ev:
            if e["status"] == "differs" and e["from_label"] == a.label:
                ctx.ask(
                    "grid_dimension_override_mismatch",
                    True,
                    "A dimension between grid axes shows a value different from the drawn axis spacing "
                    "(overridden text). Which value is right?",
                    f"{g.gid}/{fam.fid} dimension {e['handle'] or '?'}",
                    f"text '{e['text']}' vs drawn {fmt_number(_round_to(_span(fam, e), step))} "
                    f"({e['from_label']}-{e['to_label']}, DIMLFAC {e['dimlfac']})",
                    g.sheet,
                )
    proposal = None
    if len(fam.axes) >= 2:
        incomplete = (
            bool(
                fam.issues
                & {
                    "label_conflict",
                    "duplicate",
                    "unlabelled",
                    "not_parallel",
                    "mixed_kinds",
                    "two_bubbles",
                    "layer_mismatch",
                    "label_order",
                }
            )
            or spacing_issue
        )
        zero = any(v <= 0 for v in rounded)
        proposal = {
            "status": "proposal",
            "coordinates": coordinate_string([v for v in rounded if v > 0]),
            "labels": " ".join(lbl or "?" for lbl in fam.labels()),
            "unit": unit,
            "unit_confidence": "low" if unit == "unknown" or "grid_units_doubt" in ctx.q_counts else "medium",
            "rounding_step": step,
            "max_rounding_residual": rnum(residual),
            "complete": not (incomplete or zero),
            "note": "Proposal only: relative spacings in drawing units (declared unit, not converted). "
            "Confirm at gate 1; Tekla X/Y assignment is asked separately.",
        }
    return {
        "family_id": fam.fid,
        "direction": [rnum(fam.d[0]), rnum(fam.d[1])],
        "normal": [rnum(fam.n[0]), rnum(fam.n[1])],
        "angle_deg": rnum(fam.theta),
        "axes": axes_json,
        "spacings": spacings_json,
        "proposal": proposal,
        "unlabelled_lines": [
            {"offset": rnum(off), "line": s.line_json(), "empty_bubble": bubble}
            for off, s, bubble in fam.unlabelled
        ],
    }
