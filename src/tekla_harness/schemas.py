"""Load the JSON Schemas in `schemas/` and validate artefacts against them."""

from __future__ import annotations

import itertools
import json
import math
import re
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError, validators
from jsonschema.protocols import Validator
from referencing import Registry, Resource

SCHEMA_NAMES = (
    "common",
    "spec",
    "project-state",
    "read-log",
    "dxf-probe",
    "intake",
    "text-index",
    "sheets",
    "grids",
    "levels",
    "sheet-text",
    "callouts",
    "answers",
    "question-registry",
    "grid-system",
    "status",
    "cache-entry",
    "reader-findings",
    "marks",
    "dimensions",
    "geometry",
    "contents",
    "render",
    "supplements",
    "spec-receipt",
    "run-journal",
    "reader-questions",
    "parts-manifest",
    "part-values",
    "part-receipts",
    "part-output",
    "takeoff-output",
    "answer-key",
)
MAX_LOT = 2**31 - 1  # the C# reader parses lot as int32
# Item arrays that rules (a)/(i) (spec_id unique) and (h)/(q) (low confidence) walk.
_ITEM_ARRAYS = ("members", "poly_members", "grids", "slabs", "polygonal_caps", "walls")
_EPSILON = 1e-9  # float noise on a tolerance compare (7200.1 - 7200 is 0.1000000000000227)
_MIN_AREA_MM2 = 1.0
_VERTICAL_TYPES = ("pad_footing", "pile_cap", "pile")  # start is the top, end the bottom
_DISTANCE_TOLERANCE_MM = 1.0  # every distance rule, as the member length rule
_FRAME_TOLERANCE_MM = 0.1  # a value meant to be equal (grid origin.z = 0)
_STEP_TOLERANCE = 1e-6  # grid values lie on a 0.01 mm step within this
_COMPOSED_LIMIT = 1024  # Tekla UI limit of a Coordinate or Label string (API limit unknown, T5)
_ORTHOGONAL_TOLERANCE_DEG = 0.5
# Geometry rules fail closed: an overflow to inf or NaN is a refusal, never an accept (ADR-0010).
_CANNOT_EVALUATE = "geometry cannot be evaluated: the coordinates are too large"
_REPO_SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"


@dataclass(frozen=True)
class Problem:
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "message": self.message}


def schema_dir() -> Path:
    """Repo `schemas/` in a checkout; the packaged copy in an installed wheel."""
    if _REPO_SCHEMAS.is_dir():
        return _REPO_SCHEMAS
    return Path(str(resources.files("tekla_harness") / "schema_files"))


@cache
def _load_all() -> tuple[dict[str, dict[str, Any]], Registry]:
    schemas: dict[str, dict[str, Any]] = {}
    registry: Registry = Registry()
    for name in SCHEMA_NAMES:
        doc = json.loads((schema_dir() / f"{name}.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(doc)
        schemas[name] = doc
        registry = registry.with_resource(doc["$id"], Resource.from_contents(doc))
    return schemas, registry


_ECMA_DOT = "[^\\n\\r\\u2028\\u2029]"


@cache
def ecma_regex(pattern: str) -> re.Pattern[str]:
    """Compile a JSON Schema `pattern` with ECMA-262 meaning (JSON Schema 2020-12 §6.4).

    Python differs on two points our patterns use: `$` also matches before a final newline
    (`"A\\n"` passed `^A$`), and `.` matches `\\r`, U+2028 and U+2029. Outside a character
    class, `$` becomes `\\Z` and `.` excludes every ECMA line terminator.
    """
    out: list[str] = []
    in_class = False
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "\\":
            out.append(pattern[i : i + 2])
            i += 2
            continue
        if in_class:
            in_class = ch != "]"
            out.append(ch)
        elif ch == "[":
            in_class = True
            out.append(ch)
        elif ch == "$":
            out.append("\\Z")
        elif ch == ".":
            out.append(_ECMA_DOT)
        else:
            out.append(ch)
        i += 1
    return re.compile("".join(out))


def _ecma_pattern(
    _validator: Validator, pattern: str, instance: Any, _schema: dict[str, Any]
) -> Iterator[ValidationError]:
    if isinstance(instance, str) and not ecma_regex(pattern).search(instance):
        yield ValidationError(f"{instance!r} does not match {pattern!r}")


_Validator = validators.extend(Draft202012Validator, {"pattern": _ecma_pattern})


def validator(name: str) -> Validator:
    if name not in SCHEMA_NAMES or name == "common":
        raise KeyError(f"unknown schema '{name}'; choose from {', '.join(SCHEMA_NAMES[1:])}")
    schemas, registry = _load_all()
    return _Validator(schemas[name], registry=registry)


def validate(name: str, data: Any) -> list[Problem]:
    """Schema errors first; semantic checks only run on schema-valid data."""
    problems = [
        Problem("/" + "/".join(str(p) for p in err.absolute_path), err.message)
        for err in sorted(validator(name).iter_errors(data), key=lambda e: list(e.absolute_path))
    ]
    if not problems and name == "spec":
        problems = check_spec(data)
    return problems


Point = tuple[float, float, float]


def check_spec(spec: dict[str, Any]) -> list[Problem]:
    """Rules JSON Schema cannot express (ADR-0015 decision 6; ADR-0016 adds its own)."""
    problems: list[Problem] = []
    lot = spec["lot"]
    if not isinstance(lot, int):
        problems.append(Problem("/lot", f"lot must be an integer, not {lot!r}"))
    elif lot > MAX_LOT:
        problems.append(Problem("/lot", f"lot {lot} is above {MAX_LOT} (int32 maximum)"))
    seen: dict[str, str] = {}
    open_questions = set(spec["open_questions"])
    for array in _ITEM_ARRAYS:
        for i, item in enumerate(spec.get(array, [])):
            here = f"/{array}/{i}"
            sid = item["spec_id"]
            if sid in seen:
                problems.append(Problem(f"{here}/spec_id", f"duplicate spec_id '{sid}' (also {seen[sid]})"))
            seen.setdefault(sid, here)
            parent = {k: v for k, v in item.items() if k != "openings"}  # an opening has its own questions
            problems.extend(_check_low_confidence(here, parent, open_questions))
            for j, opening in enumerate(item.get("openings", [])):
                there = f"{here}/openings/{j}"
                oid = opening["spec_id"]
                if oid in seen:
                    problems.append(
                        Problem(f"{there}/spec_id", f"duplicate spec_id '{oid}' (also {seen[oid]})")
                    )
                seen.setdefault(oid, there)
                problems.extend(_check_low_confidence(there, opening, open_questions))

    for i, member in enumerate(spec["members"]):
        a, b = member["start"], member["end"]
        if math.dist((a["x"], a["y"], a["z"]), (b["x"], b["y"], b["z"])) < 1.0:
            problems.append(Problem(f"/members/{i}", "start and end are less than 1 mm apart"))
        problems.extend(_check_footing_axis(f"/members/{i}", member))
    for i, poly in enumerate(spec.get("poly_members", [])):
        problems.extend(_check_poly_points(f"/poly_members/{i}", poly["points"]))
    grids = spec.get("grids", [])
    names: dict[str, str] = {}
    for i, grid in enumerate(grids):
        here = f"/grids/{i}"
        if grid["name"] in names:
            problems.append(
                Problem(f"{here}/name", f"duplicate grid name '{grid['name']}' (also {names[grid['name']]})")
            )
        names.setdefault(grid["name"], here)
        problems.extend(_check_grid(here, grid))
    problems.extend(_check_orthogonal_pairs(grids))
    for i, slab in enumerate(spec.get("slabs", [])):
        problems.extend(_check_slab(f"/slabs/{i}", slab))
    for i, cap in enumerate(spec.get("polygonal_caps", [])):
        problems.extend(_check_flat_outline(f"/polygonal_caps/{i}/outline", cap["outline"]))
    for i, wall in enumerate(spec.get("walls", [])):
        problems.extend(_check_wall(f"/walls/{i}", wall))

    for pointer, prov in _elevation_provenances(spec):
        if not _provenance_reaches_answer(prov):
            problems.append(
                Problem(
                    pointer,
                    "elevation provenance does not reach an engineer_answer (ADR-0015 (f), ADR-0016 (p))",
                )
            )
    for pointer, prov in _walk_methods(spec, ""):
        if prov["method"] == "engineer_answer" and not _has_text(prov.get("question_id")):
            problems.append(Problem(pointer, "engineer_answer provenance has no non-empty question_id"))
    return problems


# --- provenance and confidence walks --------------------------------------------------------


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _provenance_reaches_answer(prov: Any) -> bool:
    """engineer_answer, or derived with any `derived_from` entry that reaches one at any depth."""
    if not isinstance(prov, dict):
        return False
    if prov.get("method") == "engineer_answer":
        return True
    if prov.get("method") == "derived":
        return any(_provenance_reaches_answer(p) for p in prov.get("derived_from", []))
    return False


def _walk_methods(obj: Any, pointer: str) -> Iterator[tuple[str, dict[str, Any]]]:
    """Every object with a `method` key, at any depth, with its JSON pointer."""
    if isinstance(obj, dict):
        if "method" in obj:
            yield pointer, obj
        for key, value in obj.items():
            yield from _walk_methods(value, f"{pointer}/{key}")
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            yield from _walk_methods(value, f"{pointer}/{i}")


def _walk_confidence(obj: Any, pointer: str) -> Iterator[tuple[str, Any]]:
    """Every object that holds a `confidence`, at any depth, with its path below the item."""
    if isinstance(obj, dict):
        if "confidence" in obj:
            yield pointer, obj["confidence"]
        for key, value in obj.items():
            yield from _walk_confidence(value, f"{pointer}/{key}" if pointer else key)
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            yield from _walk_confidence(value, f"{pointer}/{i}" if pointer else str(i))


def _check_low_confidence(here: str, item: dict[str, Any], open_questions: set[str]) -> list[Problem]:
    problems: list[Problem] = []
    low = [path for path, confidence in _walk_confidence(item, "") if confidence == "low"]
    qids = item.get("question_ids", [])
    if low and not qids:
        problems.append(Problem(here, f"low-confidence field(s) {', '.join(low)} without a question_id"))
    for q in qids:
        if q not in open_questions:
            problems.append(Problem(f"{here}/question_ids", f"'{q}' is not listed in open_questions"))
    return problems


def _elevation_provenances(spec: dict[str, Any]) -> Iterator[tuple[str, Any]]:
    """Rules (f) and (p): each elevation's provenance and its pointer, each path once.

    Every member point is here, so the pad_footing, pile_cap, pile and strip_footing paths of (p) are
    already covered; a pile's end (toe) is the one exemption (ADR-0016 Q14).
    """
    for g, grid in enumerate(spec.get("grids", [])):
        for k, level in enumerate(grid["levels"]):
            yield f"/grids/{g}/levels/{k}/z", level["z"].get("provenance")
    for m, member in enumerate(spec["members"]):
        yield f"/members/{m}/start", member["start"].get("provenance")
        if member.get("type") != "pile":  # a pile's toe is the one exception (ADR-0016 Q14)
            yield f"/members/{m}/end", member["end"].get("provenance")
    for p, poly in enumerate(spec.get("poly_members", [])):
        for k, point in enumerate(poly["points"]):
            yield f"/poly_members/{p}/points/{k}", point.get("provenance")
    for array in ("slabs", "polygonal_caps"):
        for a, item in enumerate(spec.get(array, [])):
            for k, point in enumerate(item["outline"]):
                yield f"/{array}/{a}/outline/{k}", point.get("provenance")
    for w, wall in enumerate(spec.get("walls", [])):
        yield f"/walls/{w}/start", wall["start"].get("provenance")
        yield f"/walls/{w}/end", wall["end"].get("provenance")


# --- grids (rules (b)-(e), (r)) -------------------------------------------------------------


def _on_step(value: float) -> bool:
    scaled = value * 100  # inf for |value| above ~1.8e306: not on the step, and round() would raise
    return math.isfinite(scaled) and abs(scaled - round(scaled)) <= _STEP_TOLERANCE


def _check_axis(
    here: str, lines: list[dict[str, Any]], key: str, noun: str, check_step: bool = True
) -> list[Problem]:
    """Rules (c) and (d) on one list of lines or levels: unique labels, increasing values, 0.01 mm step."""
    problems: list[Problem] = []
    labels: dict[str, int] = {}
    previous: float | None = None
    for i, line in enumerate(lines):
        label = line["label"]["value"]
        if label in labels:
            problems.append(
                Problem(f"{here}/{i}/label/value", f"duplicate label '{label}' (also {here}/{labels[label]})")
            )
        labels.setdefault(label, i)
        value = line[key]["value"]
        pointer = f"{here}/{i}/{key}/value" if key == "position" else f"{here}/{i}/{key}"
        if previous is not None and value - previous < _DISTANCE_TOLERANCE_MM - _STEP_TOLERANCE:
            problems.append(
                Problem(pointer, f"{noun} {value} is not at least 1 mm above the previous one ({previous})")
            )
        if check_step and not _on_step(value):
            problems.append(Problem(pointer, f"{noun} {value} is not on the 0.01 mm step"))
        previous = value
    return problems


def _spacings(positions: list[float]) -> str:
    """Tekla CoordinateX/Y: `0.00` then the spacing from each line to the next, 2 decimals (decision 2)."""
    return " ".join(["0.00", *(f"{b - a:.2f}" for a, b in itertools.pairwise(positions))])


def _check_grid(here: str, grid: dict[str, Any]) -> list[Problem]:
    problems: list[Problem] = []
    origin = grid["origin"]
    for axis in ("x", "y"):
        if not _on_step(origin[axis]):
            problems.append(
                Problem(f"{here}/origin/{axis}", f"origin.{axis} {origin[axis]} is not on the 0.01 mm step")
            )
    if abs(origin["z"]) > _FRAME_TOLERANCE_MM:
        problems.append(Problem(f"{here}/origin/z", f"origin.z {origin['z']} is not within 0.1 mm of 0"))
    for field in ("origin", "rotation_deg"):
        if not _provenance_reaches_answer(grid[field].get("provenance")):
            problems.append(
                Problem(
                    f"{here}/{field}",
                    f"grid {field} provenance does not reach an engineer_answer (ADR-0015 rule (r))",
                )
            )

    axes = (
        ("x_lines", "position", "line position", "CoordinateX", "LabelX"),
        ("y_lines", "position", "line position", "CoordinateY", "LabelY"),
        ("levels", "z", "level z", "CoordinateZ", "LabelZ"),
    )
    for name, key, noun, coordinate_name, label_name in axes:
        lines = grid[name]
        if not lines:
            continue  # a one-direction grid has no y_lines
        problems.extend(_check_axis(f"{here}/{name}", lines, key, noun))
        values = [line[key]["value"] for line in lines]
        composed = {
            coordinate_name: _spacings(values) if name != "levels" else " ".join(f"{v:.2f}" for v in values),
            label_name: " ".join(line["label"]["value"] for line in lines),
        }
        for string_name, text in composed.items():
            if len(text) > _COMPOSED_LIMIT:
                problems.append(
                    Problem(
                        f"{here}/{name}",
                        f"composed {string_name} is {len(text)} characters, over the {_COMPOSED_LIMIT} limit",
                    )
                )
    return problems


def _check_orthogonal_pairs(grids: list[dict[str, Any]]) -> list[Problem]:
    """Rule (r): two one-direction grids 90 degrees apart are one orthogonal grid."""
    problems: list[Problem] = []
    one_direction = [(i, g) for i, g in enumerate(grids) if not g["y_lines"]]
    for n, (i, first) in enumerate(one_direction):
        for j, second in one_direction[n + 1 :]:
            d = abs(first["rotation_deg"]["value"] - second["rotation_deg"]["value"]) % 180
            if abs(d - 90) <= _ORTHOGONAL_TOLERANCE_DEG:
                problems.append(
                    Problem(
                        f"/grids/{j}/rotation_deg",
                        f"/grids/{i} and /grids/{j} are one-direction grids 90 degrees apart: "
                        "they are one orthogonal grid",
                    )
                )
    return problems


# --- poly members (rule (g)) ------------------------------------------------------------------


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Point, b: Point) -> Point:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _length(a: Point) -> float:
    return math.sqrt(_dot(a, a))


def _distance_to_line(p: Point, a: Point, b: Point) -> float:
    """Distance from p to the infinite line through a and b (to a when they coincide). NaN on overflow."""
    ab = _sub(b, a)
    base = _length(ab)
    if base == 0.0:
        return math.dist(p, a)
    across = _length(_cross(_sub(p, a), ab))
    return across / base if math.isfinite(base) and math.isfinite(across) else math.nan


def _close(problems: list[Problem], pointer: str, distance: float, message: str) -> None:
    """Rule helper: a distance under 1 mm is a problem; so is one that is not finite (fail closed)."""
    if not math.isfinite(distance):
        problems.append(Problem(pointer, _CANNOT_EVALUATE))
    elif distance < _DISTANCE_TOLERANCE_MM:
        problems.append(Problem(pointer, message))


def _segment_distance(p1: Point, q1: Point, p2: Point, q2: Point) -> float:
    """Shortest distance between segments p1-q1 and p2-q2 (closest points, parallel case handled)."""

    def clamp(v: float) -> float:
        return min(1.0, max(0.0, v))

    d1, d2, r = _sub(q1, p1), _sub(q2, p2), _sub(p1, p2)
    a, e, f = _dot(d1, d1), _dot(d2, d2), _dot(d2, r)
    b, c = _dot(d1, d2), _dot(d1, r)
    if not all(math.isfinite(v) for v in (a, e, f, b, c, a * e)):
        return math.nan  # squares overflowed: the closest points cannot be found
    if a == 0.0 and e == 0.0:
        return math.dist(p1, p2)
    if a == 0.0:
        s, t = 0.0, clamp(f / e)
    else:
        if e == 0.0:
            s, t = clamp(-c / a), 0.0
        else:
            denominator = a * e - b * b
            s = clamp((b * f - c * e) / denominator) if denominator > 1e-12 * a * e else 0.0
            t = (b * s + f) / e
            if t < 0.0:
                s, t = clamp(-c / a), 0.0
            elif t > 1.0:
                s, t = clamp((b - c) / a), 1.0
    c1 = (p1[0] + d1[0] * s, p1[1] + d1[1] * s, p1[2] + d1[2] * s)
    c2 = (p2[0] + d2[0] * t, p2[1] + d2[1] * t, p2[2] + d2[2] * t)
    return math.dist(c1, c2)


def _check_poly_points(here: str, points: list[dict[str, Any]]) -> list[Problem]:
    problems: list[Problem] = []
    xyz: list[Point] = [(p["x"], p["y"], p["z"]) for p in points]
    chamfer = [p["chamfer"] for p in points]
    n = len(points)

    for j in range(1, n):
        _close(
            problems,
            f"{here}/points/{j}",
            math.dist(xyz[j - 1], xyz[j]),
            f"points {j - 1} and {j} are less than 1 mm apart",
        )
    for j in range(2, n):
        for i in range(j - 1):
            _close(
                problems,
                f"{here}/points/{j}",
                math.dist(xyz[i], xyz[j]),
                f"repeated point: points {i} and {j} are within 1 mm of each other",
            )

    for k in (0, n - 1):
        if chamfer[k] != "none":
            problems.append(Problem(f"{here}/points/{k}/chamfer", "the first and last points must be 'none'"))
    for k in range(1, n):
        if chamfer[k - 1] == "arc_point" and chamfer[k] == "arc_point":
            problems.append(
                Problem(f"{here}/points/{k}/chamfer", f"points {k - 1} and {k}: arc_point in a row")
            )
    for k in range(1, n - 1):
        if chamfer[k] == "arc_point":
            _close(
                problems,
                f"{here}/points/{k}",
                _distance_to_line(xyz[k], xyz[k - 1], xyz[k + 1]),
                f"arc_point {k} is less than 1 mm from the chord of its neighbours (Tekla drops the arc)",
            )

    problems.extend(_check_plane(here, xyz))

    for a in range(n - 1):
        for b in range(a + 2, n - 1):
            _close(
                problems,
                f"{here}/points/{b}",
                _segment_distance(xyz[a], xyz[a + 1], xyz[b], xyz[b + 1]),
                f"segments {a} and {b} meet within 1 mm (contours must not have loops)",
            )
    for k in range(1, n - 1):  # two consecutive segments that double back, first and last included
        ends = (
            _segment_distance(xyz[k + 1], xyz[k + 1], xyz[k - 1], xyz[k]),
            _segment_distance(xyz[k - 1], xyz[k - 1], xyz[k], xyz[k + 1]),
        )
        _close(
            problems,
            f"{here}/points/{k}",
            min(ends) if all(math.isfinite(v) for v in ends) else math.nan,
            f"segments {k - 1} and {k} fold back on each other at point {k} (contours must not double back)",
        )
    return problems


def _check_plane(here: str, xyz: list[Point]) -> list[Problem]:
    """All points within 1 mm of the plane through the first point and the largest triangle."""
    first = xyz[0]
    far = max(xyz, key=lambda p: math.dist(first, p))
    if math.dist(first, far) < _DISTANCE_TOLERANCE_MM:
        return []  # every point coincides with the first: reported as repeated points
    if all(_distance_to_line(p, first, far) <= _DISTANCE_TOLERANCE_MM for p in xyz):
        return [Problem(here, "all points are collinear within 1 mm: a straight member belongs in members")]
    areas = {
        (i, j): _length(_cross(_sub(xyz[i], first), _sub(xyz[j], first)))
        for i in range(1, len(xyz))
        for j in range(i + 1, len(xyz))
    }
    if not all(math.isfinite(v) for v in areas.values()):
        return [Problem(here, _CANNOT_EVALUATE)]
    best = max(areas, key=lambda ij: areas[ij])
    normal = _cross(_sub(xyz[best[0]], first), _sub(xyz[best[1]], first))
    base = _length(normal)
    if not (math.isfinite(base) and base > 0.0):
        return [Problem(here, _CANNOT_EVALUATE)]
    problems: list[Problem] = []
    for k, p in enumerate(xyz):
        off = abs(_dot(_sub(p, first), normal)) / base
        if not math.isfinite(off):
            problems.append(Problem(f"{here}/points/{k}", _CANNOT_EVALUATE))
        elif off > _DISTANCE_TOLERANCE_MM:
            problems.append(
                Problem(
                    f"{here}/points/{k}",
                    f"point {k} is {off:.1f} mm off the plane of the first point and the largest triangle "
                    "(more than 1 mm)",
                )
            )
    return problems


# --- footings, piles, slabs, caps, walls and openings (ADR-0016 rules (j)-(o)) -----------------

Point2 = tuple[float, float]


def _exceeds(value: float, tolerance: float) -> bool:
    return not (value <= tolerance + _EPSILON)  # NaN exceeds: every caller refuses


def _check_footing_axis(here: str, member: dict[str, Any]) -> list[Problem]:
    """Rule (j): vertical pad_footing, pile_cap and pile. Rule (k): horizontal strip_footing."""
    kind = member.get("type")
    a, b = member["start"], member["end"]
    problems: list[Problem] = []
    if kind in _VERTICAL_TYPES:
        drop = a["z"] - b["z"]
        if drop < _DISTANCE_TOLERANCE_MM:
            problems.append(
                Problem(
                    f"{here}/end",
                    f"{kind}: start must be at least 1 mm above end (start is {drop:.2f} mm above)",
                )
            )
        plan = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
        if _exceeds(plan, _FRAME_TOLERANCE_MM):
            problems.append(
                Problem(
                    f"{here}/end", f"{kind}: start and end are {plan:.2f} mm apart in plan (vertical: 0.1 mm)"
                )
            )
    elif kind == "strip_footing":
        rise = abs(a["z"] - b["z"])
        if _exceeds(rise, _FRAME_TOLERANCE_MM):
            problems.append(
                Problem(
                    f"{here}/end",
                    f"strip_footing: start and end z differ by {rise:.2f} mm (horizontal: 0.1 mm)",
                )
            )
    return problems


def _signed_area(uv: list[Point2]) -> float:
    n = len(uv)
    return sum(uv[k][0] * uv[(k + 1) % n][1] - uv[(k + 1) % n][0] * uv[k][1] for k in range(n)) / 2.0


def _inside(p: Point2, polygon: list[Point2]) -> bool:
    """Ray casting; points on the boundary are decided by the caller's distance test."""
    inside = False
    n = len(polygon)
    for k in range(n):
        (x1, y1), (x2, y2) = polygon[k], polygon[(k + 1) % n]
        if (y1 > p[1]) != (y2 > p[1]) and p[0] < x1 + (p[1] - y1) / (y2 - y1) * (x2 - x1):
            inside = not inside
    return inside


def _distance_to_polygon_edges(p: Point2, polygon: list[Point2]) -> float:
    n = len(polygon)
    a = (p[0], p[1], 0.0)
    return min(
        _segment_distance(
            a, a, (polygon[k][0], polygon[k][1], 0.0), (polygon[(k + 1) % n][0], polygon[(k + 1) % n][1], 0.0)
        )
        for k in range(n)
    )


def _crosses(p1: Point2, q1: Point2, p2: Point2, q2: Point2) -> bool | None:
    """True when segment 1 properly crosses segment 2: each has its ends strictly on opposite sides of the
    other's line, by more than 1 mm. None when that cannot be evaluated."""
    tol = _DISTANCE_TOLERANCE_MM
    both_sides = True
    for a, b, ends in ((p1, q1, (p2, q2)), (p2, q2, (p1, q1))):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if not math.isfinite(length):
            return None
        if length < tol:
            return False  # a degenerate edge: refused by the spacing rule
        side = [(dx * (e[1] - a[1]) - dy * (e[0] - a[0])) / length for e in ends]
        if not all(math.isfinite(v) for v in side):
            return None
        both_sides = both_sides and ((side[0] > tol and side[1] < -tol) or (side[0] < -tol and side[1] > tol))
    return both_sides


def _check_edges_cross(here: str, opening: list[Point2], polygon: list[Point2]) -> list[Problem]:
    """Rule (m): an opening edge may touch the slab outline but not cross it (a concave slab has gaps)."""
    problems: list[Problem] = []
    n, m = len(opening), len(polygon)
    for k in range(n):
        for e in range(m):
            crossed = _crosses(opening[k], opening[(k + 1) % n], polygon[e], polygon[(e + 1) % m])
            if crossed is None:
                problems.append(Problem(f"{here}/{k}", _CANNOT_EVALUATE))
            elif crossed:
                problems.append(
                    Problem(
                        f"{here}/{k}", f"opening edge {k} crosses slab outline edge {e}: not inside the slab"
                    )
                )
    return problems


def _check_outline(
    here: str, points: list[dict[str, Any]], uv: list[Point2] | None, xyz: list[Point]
) -> list[Problem]:
    """Rule (l): a closed outline. `uv` is the 2D basis with a x b = normal; None skips the winding."""
    problems: list[Problem] = []
    chamfer = [p["chamfer"] for p in points]
    n = len(points)
    for j in range(n):
        k = (j + 1) % n
        _close(
            problems, f"{here}/{k}", math.dist(xyz[j], xyz[k]), f"points {j} and {k} are less than 1 mm apart"
        )
    for j in range(n):
        for i in range(j):
            if (i + 1) % n == j or (j + 1) % n == i:
                continue
            _close(
                problems,
                f"{here}/{j}",
                math.dist(xyz[i], xyz[j]),
                f"repeated point: points {i} and {j} are within 1 mm of each other",
            )
    for k in range(n):
        nxt = (k + 1) % n
        if chamfer[k] == "arc_point" and chamfer[nxt] == "arc_point":
            problems.append(Problem(f"{here}/{nxt}/chamfer", f"points {k} and {nxt}: arc_point in a row"))
        if chamfer[k] == "arc_point":
            _close(
                problems,
                f"{here}/{k}",
                _distance_to_line(xyz[k], xyz[k - 1], xyz[nxt]),
                f"arc_point {k} is less than 1 mm from the chord of its neighbours (Tekla drops the arc)",
            )
    for a in range(n):
        for b in range(a + 2, n):
            if a == 0 and b == n - 1:
                continue  # adjacent through the closing edge
            _close(
                problems,
                f"{here}/{b}",
                _segment_distance(xyz[a], xyz[(a + 1) % n], xyz[b], xyz[(b + 1) % n]),
                f"edges {a} and {b} meet within 1 mm (outlines must not have loops)",
            )
    if uv is not None:
        area = _signed_area(uv)
        if not math.isfinite(area):
            problems.append(Problem(here, _CANNOT_EVALUATE))
        elif area <= -_MIN_AREA_MM2:
            problems.append(
                Problem(
                    here,
                    f"outline runs clockwise (signed area {area:.1f} mm2); counter-clockwise is required",
                )
            )
        elif area < _MIN_AREA_MM2:
            problems.append(Problem(here, f"outline area {area:.2f} mm2 is less than 1 mm2"))
    return problems


def _xyz(points: list[dict[str, Any]]) -> list[Point]:
    return [(p["x"], p["y"], p["z"]) for p in points]


def _check_same_z(here: str, points: list[dict[str, Any]], z0: float, what: str) -> list[Problem]:
    return [
        Problem(f"{here}/{k}", f"z {p['z']} is {abs(p['z'] - z0):.2f} mm from {what} z {z0} (same z: 0.1 mm)")
        for k, p in enumerate(points)
        if _exceeds(abs(p["z"] - z0), _FRAME_TOLERANCE_MM)
    ]


def _check_flat_outline(here: str, points: list[dict[str, Any]]) -> list[Problem]:
    """Rules (l) and (m) for a slab or a polygonal cap outline: +Z normal, one z."""
    uv = [(p["x"], p["y"]) for p in points]
    problems = _check_outline(here, points, uv, _xyz(points))
    problems.extend(_check_same_z(here, points, points[0]["z"], "the first point's"))
    return problems


def _check_slab(here: str, slab: dict[str, Any]) -> list[Problem]:
    outline = slab["outline"]
    problems = _check_flat_outline(f"{here}/outline", outline)
    openings = slab.get("openings", [])
    polygon = [(p["x"], p["y"]) for p in outline]
    z0 = outline[0]["z"]
    if openings and any(p["chamfer"] == "arc_point" for p in outline):
        problems.append(
            Problem(
                f"{here}/openings",
                "a slab whose outline has an arc_point cannot have openings (ADR-0016 rule (m))",
            )
        )
        arcs = True
    else:
        arcs = False
    for j, opening in enumerate(openings):
        there = f"{here}/openings/{j}/outline"
        points = opening["outline"]
        uv = [(p["x"], p["y"]) for p in points]
        problems.extend(_check_outline(there, points, uv, _xyz(points)))
        problems.extend(_check_same_z(there, points, z0, "the slab outline's"))
        if arcs:
            continue
        for k, corner in enumerate(uv):
            distance = _distance_to_polygon_edges(corner, polygon)
            if not math.isfinite(distance):
                problems.append(Problem(f"{there}/{k}", _CANNOT_EVALUATE))
            elif not _inside(corner, polygon) and _exceeds(distance, _DISTANCE_TOLERANCE_MM):
                problems.append(Problem(f"{there}/{k}", f"opening corner {k} lies outside the slab outline"))
        problems.extend(_check_edges_cross(there, uv, polygon))
    problems.extend(_check_overlaps(f"{here}/openings", [o["outline"] for o in openings], None))
    return problems


def _wall_frame(wall: dict[str, Any]) -> tuple[Point2, float, float] | None:
    """(unit direction in plan, plan length, base z) or None when the wall has no plan direction."""
    a, b = wall["start"], wall["end"]
    dx, dy = b["x"] - a["x"], b["y"] - a["y"]
    length = math.hypot(dx, dy)
    if not (math.isfinite(length) and length >= _DISTANCE_TOLERANCE_MM):
        return None
    return (dx / length, dy / length), length, a["z"]


def _wall_uv(frame: tuple[Point2, float, float], wall: dict[str, Any], p: dict[str, Any]) -> Point2:
    """Wall basis (a = Z, b = wall direction): Z x direction is the normal (ADR-0016 draft section 2)."""
    (ux, uy), _, _ = frame
    start = wall["start"]
    return (p["z"], (p["x"] - start["x"]) * ux + (p["y"] - start["y"]) * uy)


def _check_wall(here: str, wall: dict[str, Any]) -> list[Problem]:
    """Rule (n), with the opening outline rules (l) and the overlap rule (o)."""
    problems: list[Problem] = []
    a, b = wall["start"], wall["end"]
    rise = abs(a["z"] - b["z"])
    if _exceeds(rise, _FRAME_TOLERANCE_MM):
        problems.append(
            Problem(
                f"{here}/end", f"wall start and end z differ by {rise:.2f} mm (base is horizontal: 0.1 mm)"
            )
        )
    frame = _wall_frame(wall)
    if frame is None:
        plan = math.hypot(b["x"] - a["x"], b["y"] - a["y"])
        problems.append(
            Problem(
                f"{here}/end",
                f"wall plan length {plan:.2f} mm is less than 1 mm"
                if math.isfinite(plan)
                else _CANNOT_EVALUATE,
            )
        )
    openings = wall.get("openings", [])
    for j, opening in enumerate(openings):
        there = f"{here}/openings/{j}/outline"
        points = opening["outline"]
        uv = [_wall_uv(frame, wall, p) for p in points] if frame else None
        problems.extend(_check_outline(there, points, uv, _xyz(points)))
        if frame is None:
            continue
        (ux, uy), length, base = frame
        for k, p in enumerate(points):
            along = uv[k][1] if uv else 0.0
            off = abs((p["x"] - a["x"]) * uy - (p["y"] - a["y"]) * ux)
            if _exceeds(off, _FRAME_TOLERANCE_MM):
                problems.append(
                    Problem(
                        f"{there}/{k}",
                        f"opening point {k} is {off:.2f} mm off the wall's vertical plane (0.1 mm)",
                    )
                )
            tol = _DISTANCE_TOLERANCE_MM + _EPSILON
            height = wall["height"]["value"]
            if not (-tol <= along <= length + tol and base - tol <= p["z"] <= base + height + tol):
                problems.append(Problem(f"{there}/{k}", f"opening point {k} lies outside the wall rectangle"))
    if frame is not None:
        problems.extend(
            _check_overlaps(
                f"{here}/openings", [o["outline"] for o in openings], lambda p: _wall_uv(frame, wall, p)
            )
        )
    return problems


def _check_overlaps(here: str, outlines: list[list[dict[str, Any]]], to_uv: Any) -> list[Problem]:
    """Rule (o): openings of one parent. No edges meeting within 1 mm, no corner inside another opening."""
    problems: list[Problem] = []
    flat = [([(p["x"], p["y"]) for p in o] if to_uv is None else [to_uv(p) for p in o]) for o in outlines]
    spatial = [_xyz(o) for o in outlines]
    for j in range(len(outlines)):
        for i in range(j):
            n_i, n_j = len(spatial[i]), len(spatial[j])
            gaps = [
                _segment_distance(
                    spatial[i][a], spatial[i][(a + 1) % n_i], spatial[j][b], spatial[j][(b + 1) % n_j]
                )
                for a in range(n_i)
                for b in range(n_j)
            ]
            if not all(math.isfinite(g) for g in gaps):
                problems.append(Problem(f"{here}/{j}", _CANNOT_EVALUATE))
                continue
            if any(g < _DISTANCE_TOLERANCE_MM for g in gaps):
                problems.append(
                    Problem(f"{here}/{j}", f"openings {i} and {j} overlap: their edges meet within 1 mm")
                )
                continue
            if any(_inside(c, flat[i]) for c in flat[j]) or any(_inside(c, flat[j]) for c in flat[i]):
                problems.append(
                    Problem(f"{here}/{j}", f"openings {i} and {j} overlap: a corner lies inside the other")
                )
    return problems
