from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from conftest import EXAMPLES
from tekla_harness.schemas import (
    _CANNOT_EVALUATE,
    Problem,
    _check_outline,
    _check_overlaps,
    _check_plane,
    _close,
    _crosses,
    _distance_to_line,
    _exceeds,
    _segment_distance,
    check_spec,
    validate,
    validator,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.mark.parametrize("name", ["spec", "project-state", "read-log"])
def test_examples_are_valid(name, example):
    assert validate(name, example(name)) == []


def test_unknown_schema_rejected():
    with pytest.raises(KeyError):
        validator("common")


# --- spec: schema rules ---------------------------------------------------------


def test_value_without_provenance_rejected(example):
    spec = example("spec")
    del spec["members"][0]["profile"]["provenance"]
    assert any("provenance" in p.message for p in validate("spec", spec))


def test_bad_confidence_rejected(example):
    spec = example("spec")
    spec["members"][0]["profile"]["confidence"] = "certain"
    assert validate("spec", spec)


def test_units_must_be_mm(example):
    spec = example("spec")
    spec["units"] = "m"
    assert validate("spec", spec)


def test_unknown_member_field_rejected(example):
    spec = example("spec")
    spec["members"][0]["colour"] = "red"
    assert validate("spec", spec)


# --- spec: semantic rules -------------------------------------------------------


def test_duplicate_spec_id(example):
    spec = example("spec")
    spec["members"][1]["spec_id"] = spec["members"][0]["spec_id"]
    assert any("duplicate spec_id" in p.message for p in validate("spec", spec))


def test_zero_length_member(example):
    spec = example("spec")
    spec["members"][0]["end"] = copy.deepcopy(spec["members"][0]["start"])
    assert any("less than 1 mm" in p.message for p in validate("spec", spec))


def test_low_confidence_needs_question(example):
    spec = example("spec")
    del spec["members"][2]["question_ids"]
    assert any("without a question_id" in p.message for p in validate("spec", spec))


def test_question_must_be_open(example):
    spec = example("spec")
    spec["open_questions"] = []
    assert any("not listed in open_questions" in p.message for p in validate("spec", spec))


# --- spec: lot 0, grids, poly members, concrete kinds (ADR-0015, ADR-0016) -------------------

SPEC_EXAMPLES = [
    "spec",
    "spec-lot0-grid",
    "spec-lot0-rotated-grid",
    "spec-poly-members",
    "spec-foundations",
    "spec-slab-wall",
]


@pytest.mark.parametrize("name", SPEC_EXAMPLES)
def test_every_spec_example_is_valid(name, example):
    assert validate("spec", example(name)) == []


def _paths(spec):
    return [p.path for p in validate("spec", spec)]


def _spec_id(n):
    return "A" * n


def _grid0(spec):
    return spec["grids"][0]


def _drop(spec, *keys):
    node = spec
    for key in keys[:-1]:
        node = node[key]
    del node[keys[-1]]


def _grid_label_space(spec):
    _grid0(spec)["x_lines"][0]["label"]["value"] = "A 1"


def _slab_two_points(spec):
    spec["slabs"][0]["outline"] = spec["slabs"][0]["outline"][:2]


def _slab_arc_opening(spec):
    spec["slabs"][0]["openings"][0]["outline"][1]["chamfer"] = "arc_point"


def _set(path, value):
    def apply(spec):
        node = spec
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value

    return apply


def _lot0_with(array, source):
    def apply(spec):
        donor = json.loads((EXAMPLES / f"{source}.example.json").read_text(encoding="utf-8"))
        spec[array] = donor[array]

    return apply


# (case id, example, mutation, exact JSON pointer of a schema error)
SCHEMA_REJECTS = [
    # ADR-0015 draft: grids, lot 0, poly members
    (
        "grid-y-lines-one-line",
        "spec-lot0-grid",
        lambda s: _grid0(s)["y_lines"].__delitem__(slice(1, None)),
        "/grids/0/y_lines",
    ),
    ("grid-no-origin", "spec-lot0-grid", lambda s: _drop(s, "grids", 0, "origin"), "/grids/0"),
    ("grid-no-rotation", "spec-lot0-grid", lambda s: _drop(s, "grids", 0, "rotation_deg"), "/grids/0"),
    (
        "rotation-minus-180",
        "spec-lot0-grid",
        lambda s: _grid0(s)["rotation_deg"].__setitem__("value", -180),
        "/grids/0/rotation_deg/value",
    ),
    (
        "rotation-181",
        "spec-lot0-grid",
        lambda s: _grid0(s)["rotation_deg"].__setitem__("value", 181),
        "/grids/0/rotation_deg/value",
    ),
    ("lot0-with-member", "spec-lot0-grid", _lot0_with("members", "spec"), "/members"),
    ("lot0-with-poly", "spec-lot0-grid", _lot0_with("poly_members", "spec-poly-members"), "/poly_members"),
    ("lot0-with-wall", "spec-lot0-grid", _lot0_with("walls", "spec-slab-wall"), "/walls"),
    ("lot0-empty-grids", "spec-lot0-grid", _set(("grids",), []), "/grids"),
    ("lot0-without-grids", "spec-lot0-grid", lambda s: _drop(s, "grids"), ""),
    ("lot1-with-grids", "spec-poly-members", _lot0_with("grids", "spec-lot0-grid"), "/grids"),
    ("lot1-with-nothing", "spec-poly-members", lambda s: s.update(poly_members=[]), ""),
    ("grid-label-space", "spec-lot0-grid", _grid_label_space, "/grids/0/x_lines/0/label/value"),
    ("grid-unknown-key", "spec-lot0-grid", lambda s: _grid0(s).update(colour="red"), "/grids/0"),
    (
        "poly-two-points",
        "spec-poly-members",
        lambda s: s["poly_members"][0]["points"].pop(),
        "/poly_members/0/points",
    ),
    (
        "poly-unknown-chamfer",
        "spec-poly-members",
        _set(("poly_members", 0, "points", 0, "chamfer"), "round"),
        "/poly_members/0/points/0/chamfer",
    ),
    (
        "poly-type-column",
        "spec-poly-members",
        _set(("poly_members", 0, "type"), "column"),
        "/poly_members/0/type",
    ),
    # ADR-0016 draft: lot 0, caps, piles, reserved names, openings, slabs, walls
    ("lot0-with-slab", "spec-lot0-grid", _lot0_with("slabs", "spec-slab-wall"), "/slabs"),
    ("lot0-with-cap", "spec-lot0-grid", _lot0_with("polygonal_caps", "spec-foundations"), "/polygonal_caps"),
    (
        "cap-without-class",
        "spec-foundations",
        lambda s: _drop(s, "polygonal_caps", 0, "class"),
        "/polygonal_caps/0",
    ),
    (
        "cap-with-name",
        "spec-foundations",
        _set(("polygonal_caps", 0, "name"), "PILE_CAP"),
        "/polygonal_caps/0",
    ),
    (
        "cap-with-openings",
        "spec-foundations",
        _set(("polygonal_caps", 0, "openings"), []),
        "/polygonal_caps/0",
    ),
    ("pile-without-class", "spec-foundations", lambda s: _drop(s, "members", 0, "class"), "/members/0"),
    ("pile-cap-without-class", "spec-foundations", lambda s: _drop(s, "members", 1, "class"), "/members/1"),
    ("pile-named-p", "spec-foundations", _set(("members", 0, "name"), "P"), "/members/0/name"),
    (
        "pad-footing-named-pile-cap",
        "spec-foundations",
        _set(("members", 2, "name"), "PILE_CAP"),
        "/members/2/name",
    ),
    ("column-named-pile", "spec", _set(("members", 0, "name"), "PILE"), "/members/0/name"),
    ("slab-named-pile-cap", "spec-slab-wall", _set(("slabs", 0, "name"), "PILE_CAP"), "/slabs/0/name"),
    ("wall-named-pile", "spec-slab-wall", _set(("walls", 0, "name"), "PILE"), "/walls/0/name"),
    ("opening-arc-point", "spec-slab-wall", _slab_arc_opening, "/slabs/0/openings/0/outline/1/chamfer"),
    (
        "opening-spec-id-61",
        "spec-slab-wall",
        _set(("slabs", 0, "openings", 0, "spec_id"), _spec_id(61)),
        "/slabs/0/openings/0/spec_id",
    ),
    ("top-level-openings", "spec-slab-wall", _set(("openings",), []), ""),
    ("slab-two-points", "spec-slab-wall", _slab_two_points, "/slabs/0/outline"),
    (
        "slab-thickness-0",
        "spec-slab-wall",
        _set(("slabs", 0, "thickness", "value"), 0),
        "/slabs/0/thickness/value",
    ),
    ("slab-profile-key", "spec-slab-wall", _set(("slabs", 0, "profile"), "PL120"), "/slabs/0"),
    (
        "wall-height-half-mm",
        "spec-slab-wall",
        _set(("walls", 0, "height", "value"), 0.5),
        "/walls/0/height/value",
    ),
    ("wall-rotation-key", "spec-slab-wall", _set(("walls", 0, "rotation_deg"), 0), "/walls/0"),
    (
        "poly-named-pile-cap",
        "spec-poly-members",
        _set(("poly_members", 0, "name"), "PILE_CAP"),
        "/poly_members/0/name",
    ),
    (
        "poly-named-pile",
        "spec-poly-members",
        _set(("poly_members", 0, "name"), "PILE"),
        "/poly_members/0/name",
    ),
    ("lot-minus-1", "spec-lot0-grid", _set(("lot",), -1), "/lot"),
    ("member-type-slab", "spec-foundations", _set(("members", 2, "type"), "slab"), "/members/2/type"),
    (
        "poly-type-strip-footing",
        "spec-poly-members",
        _set(("poly_members", 0, "type"), "strip_footing"),
        "/poly_members/0/type",
    ),
]


@pytest.mark.parametrize(
    ("case", "name", "mutate", "path"), SCHEMA_REJECTS, ids=[c[0] for c in SCHEMA_REJECTS]
)
def test_spec_schema_rejects(case, name, mutate, path, example):
    spec = example(name)
    mutate(spec)
    errors = [
        ("/" + "/".join(map(str, e.absolute_path))).rstrip("/") for e in validator("spec").iter_errors(spec)
    ]
    assert path in errors, (case, errors)


def _accept_one_direction_grid(spec):
    _grid0(spec)["y_lines"] = []


def _accept_rotation_180(spec):
    _grid0(spec)["rotation_deg"]["value"] = 180


def _accept_caps_only(spec):
    spec["members"] = []


def _accept_pile_named_pile(spec):
    spec["members"][0]["name"] = "PILE"


def _accept_cap_named_pile_cap(spec):
    spec["members"][1]["name"] = "PILE_CAP"


def _accept_opening_id_60(spec):
    spec["slabs"][0]["openings"][0]["spec_id"] = _spec_id(60)


def _accept_slab_id_64(spec):
    spec["slabs"][0]["spec_id"] = _spec_id(64)


def _accept_walls_only(spec):
    spec["members"] = []
    spec["slabs"] = []


def _accept_slabs_only(spec):
    spec["members"] = []
    spec["walls"] = []


SCHEMA_ACCEPTS = [
    ("one-direction-grid", "spec-lot0-grid", _accept_one_direction_grid),
    ("rotation-180", "spec-lot0-grid", _accept_rotation_180),
    ("caps-only-lot", "spec-foundations", _accept_caps_only),
    ("pile-named-pile", "spec-foundations", _accept_pile_named_pile),
    ("pile-cap-named-pile-cap", "spec-foundations", _accept_cap_named_pile_cap),
    ("opening-spec-id-60", "spec-slab-wall", _accept_opening_id_60),
    ("slab-spec-id-64", "spec-slab-wall", _accept_slab_id_64),
    ("walls-only-lot", "spec-slab-wall", _accept_walls_only),
    ("slabs-only-lot", "spec-slab-wall", _accept_slabs_only),
]


@pytest.mark.parametrize(("case", "name", "mutate"), SCHEMA_ACCEPTS, ids=[c[0] for c in SCHEMA_ACCEPTS])
def test_spec_schema_accepts(case, name, mutate, example):
    spec = example(name)
    mutate(spec)
    assert _paths(spec) == []


# --- spec: ADR-0015 semantic rules (a)-(h), (r), (s) ---------------------------------------------

DRAWING_ONLY = {"file": "S-201.dxf", "sheet": "S-201", "method": "dxf_entity"}


def _engineer(question_id="Q-010"):
    return {"file": "S-101.dxf", "sheet": "S-101", "method": "engineer_answer", "question_id": question_id}


def _derived_depth(depth):
    prov = _engineer()
    for _ in range(depth):
        prov = {**DRAWING_ONLY, "method": "derived", "derived_from": [DRAWING_ONLY, prov]}
    return prov


def _donor_member(spec_id):
    donor = json.loads((EXAMPLES / "spec.example.json").read_text(encoding="utf-8"))["members"][0]
    donor["spec_id"] = spec_id
    return donor


def _poly_member_donor(spec, spec_id):
    spec["members"] = [_donor_member(spec_id)]


def _dup_member_vs_poly(spec):
    _poly_member_donor(spec, spec["poly_members"][0]["spec_id"])


def _dup_poly_poly(spec):
    spec["poly_members"][1]["spec_id"] = spec["poly_members"][0]["spec_id"]


def _dup_grid_grid(spec):
    spec["grids"][1]["spec_id"] = spec["grids"][0]["spec_id"]


def _dup_grid_name(spec):
    spec["grids"][1]["name"] = spec["grids"][0]["name"]


def _dup_label(axis):
    def apply(spec):
        lines = _grid0(spec)[axis]
        lines[1]["label"]["value"] = lines[0]["label"]["value"]

    return apply


def _px(axis, i, value):
    return _set(("grids", 0, axis, i, "position", "value"), value)


def _long_lines(axis, field, count, label=None, step=1000):
    """Replace one grid axis by `count` lines; `label(i)` builds the label text."""

    def apply(spec):
        grid = _grid0(spec)
        template = grid[axis][0]
        lines = []
        for i in range(count):
            line = copy.deepcopy(template)
            line["label"]["value"] = label(i) if label else f"n{i}"
            line[field]["value"] = i * step
            lines.append(line)
        grid[axis] = lines

    return apply


def _two_labels(length_a, length_b):
    def apply(spec):
        _long_lines("x_lines", "position", 2, label=lambda i: "a" * (length_a, length_b)[i], step=6000)(spec)

    return apply


def _long(axis, field, label_wide):
    count = 40 if label_wide else 200
    label = (lambda i: f"L{i:0>40}") if label_wide else None
    return _long_lines(axis, field, count, label=label, step=10 if label_wide else 1000)


def _level_lines(count, label_wide):
    def apply(spec):
        grid = _grid0(spec)
        template = grid["levels"][0]
        levels = []
        for i in range(count):
            level = copy.deepcopy(template)
            level["label"]["value"] = f"L{i:0>40}" if label_wide else f"n{i}"
            level["z"]["value"] = i * (10 if label_wide else 1000)
            levels.append(level)
        grid["levels"] = levels

    return apply


def _prov(path, prov):
    return _set((*path, "provenance"), prov)


def _lowconf(path, question_ids=None):
    def apply(spec):
        node = spec
        for key in path:
            node = node[key]
        node["confidence"] = "low"
        if question_ids is not None:
            item = spec[path[0]][path[1]]
            item["question_ids"] = question_ids

    return apply


def _poly(*points):
    """Replace poly_members[0].points with (x, y, z[, chamfer]) tuples."""

    def apply(spec):
        member = spec["poly_members"][0]
        template = member["points"][0]
        built = []
        for point in points:
            x, y, z, *rest = point
            item = copy.deepcopy(template)
            item.update(x=x, y=y, z=z, chamfer=rest[0] if rest else "none")
            built.append(item)
        member["points"] = built

    return apply


Z = 7200
SQUARE = [(0, 0, Z), (5000, 0, Z), (5000, 5000, Z)]


def _two_empty_y(rot_a, rot_b):
    def apply(spec):
        for grid, rotation in zip(spec["grids"], (rot_a, rot_b), strict=True):
            grid["y_lines"] = []
            grid["rotation_deg"]["value"] = rotation

    return apply


def _no_question_id(path):
    def apply(spec):
        node = spec
        for key in path:
            node = node[key]
        node.pop("question_id", None)

    return apply


# (case id, example, mutation, JSON pointer prefix, message fragment)
SEMANTIC_REJECTS = [
    # (a) spec_id unique across members, poly_members, grids
    (
        "a-member-vs-poly",
        "spec-poly-members",
        _dup_member_vs_poly,
        "/poly_members/0/spec_id",
        "also /members/0",
    ),
    (
        "a-poly-vs-poly",
        "spec-poly-members",
        _dup_poly_poly,
        "/poly_members/1/spec_id",
        "also /poly_members/0",
    ),
    ("a-grid-vs-grid", "spec-lot0-rotated-grid", _dup_grid_grid, "/grids/1/spec_id", "also /grids/0"),
    # (b) grid name unique
    ("b-grid-name", "spec-lot0-rotated-grid", _dup_grid_name, "/grids/1/name", "duplicate grid name"),
    # (c) labels unique per axis and per level list
    ("c-x-label", "spec-lot0-grid", _dup_label("x_lines"), "/grids/0/x_lines/1/label", "duplicate label"),
    ("c-y-label", "spec-lot0-grid", _dup_label("y_lines"), "/grids/0/y_lines/1/label", "duplicate label"),
    ("c-level-label", "spec-lot0-grid", _dup_label("levels"), "/grids/0/levels/1/label", "duplicate label"),
    # (d) strictly increasing, steps >= 1 mm, 0.01 mm step
    (
        "d-x-decreasing",
        "spec-lot0-grid",
        _px("x_lines", 1, -5),
        "/grids/0/x_lines/1/position",
        "at least 1 mm",
    ),
    ("d-x-equal", "spec-lot0-grid", _px("x_lines", 1, 0), "/grids/0/x_lines/1/position", "at least 1 mm"),
    ("d-x-half-mm", "spec-lot0-grid", _px("x_lines", 1, 0.5), "/grids/0/x_lines/1/position", "at least 1 mm"),
    (
        "d-y-decreasing",
        "spec-lot0-grid",
        _px("y_lines", 1, -10),
        "/grids/0/y_lines/1/position",
        "at least 1 mm",
    ),
    (
        "d-z-decreasing",
        "spec-lot0-grid",
        _set(("grids", 0, "levels", 1, "z", "value"), -10),
        "/grids/0/levels/1/z",
        "at least 1 mm",
    ),
    (
        "d-x-step",
        "spec-lot0-grid",
        _px("x_lines", 1, 6000.005),
        "/grids/0/x_lines/1/position",
        "0.01 mm step",
    ),
    (
        "d-y-step",
        "spec-lot0-grid",
        _px("y_lines", 1, 7500.001),
        "/grids/0/y_lines/1/position",
        "0.01 mm step",
    ),
    (
        "d-z-step",
        "spec-lot0-grid",
        _set(("grids", 0, "levels", 1, "z", "value"), 3600.001),
        "/grids/0/levels/1/z",
        "0.01 mm step",
    ),
    (
        "d-origin-x-step",
        "spec-lot0-grid",
        _set(("grids", 0, "origin", "x"), 0.005),
        "/grids/0/origin/x",
        "0.01 mm step",
    ),
    (
        "d-origin-y-step",
        "spec-lot0-grid",
        _set(("grids", 0, "origin", "y"), 0.005),
        "/grids/0/origin/y",
        "0.01 mm step",
    ),
    # (e) composed strings <= 1024 characters
    (
        "e-coordinate-x",
        "spec-lot0-grid",
        _long("x_lines", "position", False),
        "/grids/0/x_lines",
        "CoordinateX",
    ),
    ("e-label-x", "spec-lot0-grid", _long("x_lines", "position", True), "/grids/0/x_lines", "LabelX"),
    (
        "e-coordinate-y",
        "spec-lot0-grid",
        _long("y_lines", "position", False),
        "/grids/0/y_lines",
        "CoordinateY",
    ),
    ("e-label-y", "spec-lot0-grid", _long("y_lines", "position", True), "/grids/0/y_lines", "LabelY"),
    ("e-coordinate-z", "spec-lot0-grid", _level_lines(200, False), "/grids/0/levels", "CoordinateZ"),
    ("e-label-z", "spec-lot0-grid", _level_lines(40, True), "/grids/0/levels", "LabelZ"),
    ("e-label-1025", "spec-lot0-grid", _two_labels(512, 512), "/grids/0/x_lines", "LabelX"),
    # (f) elevation provenance
    (
        "f-level-drawing-only",
        "spec-lot0-grid",
        _prov(("grids", 0, "levels", 1, "z"), DRAWING_ONLY),
        "/grids/0/levels/1/z",
        "engineer_answer",
    ),
    (
        "f-level-derived-without-engineer",
        "spec-lot0-grid",
        _prov(
            ("grids", 0, "levels", 1, "z"),
            {
                **DRAWING_ONLY,
                "method": "derived",
                "derived_from": [
                    DRAWING_ONLY,
                    {**DRAWING_ONLY, "method": "derived", "derived_from": [DRAWING_ONLY]},
                ],
            },
        ),
        "/grids/0/levels/1/z",
        "engineer_answer",
    ),
    (
        "f-level-derived-no-sources",
        "spec-lot0-grid",
        _prov(("grids", 0, "levels", 1, "z"), {**DRAWING_ONLY, "method": "derived"}),
        "/grids/0/levels/1/z",
        "engineer_answer",
    ),
    (
        "f-level-non-derived-with-sources",
        "spec-lot0-grid",
        _prov(("grids", 0, "levels", 1, "z"), {**DRAWING_ONLY, "derived_from": [_engineer()]}),
        "/grids/0/levels/1/z",
        "engineer_answer",
    ),
    (
        "f-member-start",
        "spec",
        _prov(("members", 0, "start"), DRAWING_ONLY),
        "/members/0/start",
        "engineer_answer",
    ),
    ("f-member-end", "spec", _prov(("members", 0, "end"), DRAWING_ONLY), "/members/0/end", "engineer_answer"),
    (
        "f-pile-start",
        "spec-foundations",
        _prov(("members", 0, "start"), DRAWING_ONLY),
        "/members/0/start",
        "engineer_answer",
    ),
    (
        "f-cap-end",
        "spec-foundations",
        _prov(("members", 1, "end"), DRAWING_ONLY),
        "/members/1/end",
        "engineer_answer",
    ),
    (
        "f-poly-point",
        "spec-poly-members",
        _prov(("poly_members", 0, "points", 1), DRAWING_ONLY),
        "/poly_members/0/points/1",
        "engineer_answer",
    ),
    # (g) poly points
    (
        "g-consecutive-close",
        "spec-poly-members",
        _poly((0, 0, Z), (0.5, 0, Z), (5000, 5000, Z)),
        "/poly_members/0/points/1",
        "less than 1 mm",
    ),
    (
        "g-repeated-point",
        "spec-poly-members",
        _poly((0, 0, Z), (5000, 0, Z), (5000, 5000, Z), (5000.2, 0.3, Z)),
        "/poly_members/0/points/3",
        "repeated point",
    ),
    (
        "g-first-arc",
        "spec-poly-members",
        _poly((0, 0, Z, "arc_point"), (5000, 0, Z), (5000, 5000, Z)),
        "/poly_members/0/points/0/chamfer",
        "first and last",
    ),
    (
        "g-last-arc",
        "spec-poly-members",
        _poly((0, 0, Z), (5000, 0, Z), (5000, 5000, Z, "arc_point")),
        "/poly_members/0/points/2/chamfer",
        "first and last",
    ),
    (
        "g-two-arcs",
        "spec-poly-members",
        _poly(
            (0, 0, Z),
            (3000, -500, Z, "arc_point"),
            (6000, -500, Z, "arc_point"),
            (9000, 0, Z),
            (9000, 5000, Z),
        ),
        "/poly_members/0/points/2/chamfer",
        "arc_point in a row",
    ),
    (
        "g-flat-arc",
        "spec-poly-members",
        _poly((0, 0, Z), (3000, 0.5, Z, "arc_point"), (6000, 0, Z), (6000, 5000, Z)),
        "/poly_members/0/points/1",
        "chord",
    ),
    (
        "g-coplanar",
        "spec-poly-members",
        _poly((0, 0, Z), (5000, 0, Z), (5000, 5000, Z), (0, 5000, Z + 50)),
        "/poly_members/0/points",
        "plane",
    ),
    (
        "g-collinear",
        "spec-poly-members",
        _poly((0, 0, Z), (6000, 0, Z), (12000, 0.4, Z)),
        "/poly_members/0",
        "collinear",
    ),
    (
        "g-loop-crossing",
        "spec-poly-members",
        _poly((0, 0, Z), (6000, 6000, Z), (6000, 0, Z), (0, 6000, Z), (-3000, 3000, Z)),
        "/poly_members/0",
        "loops",
    ),
    (
        "g-loop-near-touch",
        "spec-poly-members",
        _poly((0, 0, Z), (6000, 0, Z), (6000, 3000, Z), (3000, 0.5, Z)),
        "/poly_members/0",
        "loops",
    ),
    # (h) low confidence anywhere in an item
    (
        "h-grid-origin",
        "spec-lot0-grid",
        _lowconf(("grids", 0, "origin")),
        "/grids/0",
        "without a question_id",
    ),
    (
        "h-grid-rotation",
        "spec-lot0-grid",
        _lowconf(("grids", 0, "rotation_deg")),
        "/grids/0",
        "without a question_id",
    ),
    (
        "h-grid-x-position",
        "spec-lot0-grid",
        _lowconf(("grids", 0, "x_lines", 1, "position")),
        "/grids/0",
        "without a question_id",
    ),
    (
        "h-grid-y-label",
        "spec-lot0-grid",
        _lowconf(("grids", 0, "y_lines", 0, "label")),
        "/grids/0",
        "without a question_id",
    ),
    (
        "h-grid-level-z",
        "spec-lot0-grid",
        _lowconf(("grids", 0, "levels", 1, "z")),
        "/grids/0",
        "without a question_id",
    ),
    (
        "h-poly-point",
        "spec-poly-members",
        _lowconf(("poly_members", 0, "points", 1)),
        "/poly_members/0",
        "without a question_id",
    ),
    (
        "h-poly-question-not-open",
        "spec-poly-members",
        _lowconf(("poly_members", 0, "points", 1), ["Q-099"]),
        "/poly_members/0/question_ids",
        "not listed in open_questions",
    ),
    (
        "h-grid-question-not-open",
        "spec-lot0-grid",
        _lowconf(("grids", 0, "origin"), ["Q-099"]),
        "/grids/0/question_ids",
        "not listed in open_questions",
    ),
    # (r) grid frame
    ("r-origin-z", "spec-lot0-grid", _set(("grids", 0, "origin", "z"), 5), "/grids/0/origin/z", "0.1 mm"),
    (
        "r-origin-provenance",
        "spec-lot0-grid",
        _prov(("grids", 0, "origin"), DRAWING_ONLY),
        "/grids/0/origin",
        "engineer_answer",
    ),
    (
        "r-rotation-provenance",
        "spec-lot0-grid",
        _prov(("grids", 0, "rotation_deg"), DRAWING_ONLY),
        "/grids/0/rotation_deg",
        "engineer_answer",
    ),
    (
        "r-orthogonal-pair",
        "spec-lot0-rotated-grid",
        _two_empty_y(0, 90),
        "/grids/1/rotation_deg",
        "orthogonal",
    ),
    (
        "r-orthogonal-negative",
        "spec-lot0-rotated-grid",
        _two_empty_y(-45, 45),
        "/grids/1/rotation_deg",
        "orthogonal",
    ),
    (
        "r-orthogonal-half-degree",
        "spec-lot0-rotated-grid",
        _two_empty_y(0, 90.5),
        "/grids/1/rotation_deg",
        "orthogonal",
    ),
    (
        "r-orthogonal-mod-180",
        "spec-lot0-rotated-grid",
        _two_empty_y(-170, 100),
        "/grids/1/rotation_deg",
        "orthogonal",
    ),
    # (s) engineer_answer carries question_id
    (
        "s-level-z",
        "spec-lot0-grid",
        _no_question_id(("grids", 0, "levels", 1, "z", "provenance")),
        "/grids/0/levels/1/z/provenance",
        "question_id",
    ),
    (
        "s-origin",
        "spec-lot0-grid",
        _no_question_id(("grids", 0, "origin", "provenance")),
        "/grids/0/origin/provenance",
        "question_id",
    ),
    (
        "s-nested-derived",
        "spec-lot0-rotated-grid",
        _no_question_id(("grids", 1, "x_lines", 1, "position", "provenance", "derived_from", 1)),
        "/grids/1/x_lines/1/position/provenance/derived_from/1",
        "question_id",
    ),
    (
        "s-empty-question-id",
        "spec-lot0-grid",
        _set(("grids", 0, "origin", "provenance", "question_id"), ""),
        "/grids/0/origin/provenance",
        "question_id",
    ),
    (
        "s-blank-question-id",
        "spec-lot0-grid",
        _set(("grids", 0, "origin", "provenance", "question_id"), "  "),
        "/grids/0/origin/provenance",
        "question_id",
    ),
    (
        "s-member-profile",
        "spec",
        _prov(("members", 0, "profile"), {**_engineer(), "question_id": ""}),
        "/members/0/profile/provenance",
        "question_id",
    ),
]


@pytest.mark.parametrize(
    ("case", "name", "mutate", "path", "fragment"), SEMANTIC_REJECTS, ids=[c[0] for c in SEMANTIC_REJECTS]
)
def test_spec_semantic_rejects(case, name, mutate, path, fragment, example):
    spec = example(name)
    mutate(spec)
    problems = validate("spec", spec)
    assert any(p.path.startswith(path) and fragment in p.message for p in problems), (case, problems)


def test_spec_id_unique_across_grids_and_members(example):
    spec = example("spec-lot0-grid")
    spec["members"] = [_donor_member(spec["grids"][0]["spec_id"])]
    problems = check_spec(spec)
    assert any(p.path == "/grids/0/spec_id" and "also /members/0" in p.message for p in problems)


def test_pre_adr0015_example_fails_elevation_rule():
    old = json.loads((FIXTURES / "spec-pre-adr0015.example.json").read_text(encoding="utf-8"))
    problems = check_spec(old)
    assert any(p.path == "/members/0/start" and "engineer_answer" in p.message for p in problems)
    assert any(p.path == "/members/0/end" and "engineer_answer" in p.message for p in problems)


def _accept_label_on_both_axes(spec):
    _grid0(spec)["y_lines"][0]["label"]["value"] = _grid0(spec)["x_lines"][0]["label"]["value"]


def _accept_pile_toe_drawing_only(spec):
    spec["members"][0]["end"]["provenance"] = DRAWING_ONLY


def _accept_level_derived_deep(spec):
    _grid0(spec)["levels"][1]["z"]["provenance"] = _derived_depth(3)


def _accept_one_mm_step(spec):
    _px("x_lines", 1, 1)(spec)


def _accept_hundredth_step(spec):
    _px("x_lines", 1, 6000.01)(spec)
    _set(("grids", 0, "origin", "x"), 0.05)(spec)


def _accept_label_1024(spec):
    _two_labels(511, 512)(spec)


def _accept_low_with_question(spec):
    _lowconf(("poly_members", 0, "points", 1), ["Q-001"])(spec)
    spec["open_questions"] = ["Q-001", "Q-031"]


def _accept_grid_low_with_question(spec):
    _lowconf(("grids", 0, "x_lines", 1, "position"), ["Q-007"])(spec)
    spec["open_questions"] = ["Q-007"]


def _accept_five_point_run(spec):
    _poly(
        (0, 0, Z),
        (3000, 500, Z, "arc_point"),
        (6000, 0, Z),
        (6000, 5000, Z),
        (0, 5000, Z + 0.5),
    )(spec)


def _accept_orthogonal_with_y_lines(spec):
    spec["grids"][0]["rotation_deg"]["value"] = 0
    spec["grids"][1]["rotation_deg"]["value"] = 90
    spec["grids"][1]["y_lines"] = []


def _accept_near_orthogonal(spec):
    _two_empty_y(0, 90.6)(spec)


def _accept_origin_z_small(spec):
    _set(("grids", 0, "origin", "z"), 0.05)(spec)


SEMANTIC_ACCEPTS = [
    ("same-label-on-two-axes", "spec-lot0-grid", _accept_label_on_both_axes),
    ("pile-toe-needs-no-engineer", "spec-foundations", _accept_pile_toe_drawing_only),
    ("level-derived-depth-3", "spec-lot0-grid", _accept_level_derived_deep),
    ("one-mm-step", "spec-lot0-grid", _accept_one_mm_step),
    ("hundredth-step", "spec-lot0-grid", _accept_hundredth_step),
    ("label-string-1024", "spec-lot0-grid", _accept_label_1024),
    ("poly-low-with-question", "spec-poly-members", _accept_low_with_question),
    ("grid-low-with-question", "spec-lot0-grid", _accept_grid_low_with_question),
    ("five-point-run", "spec-poly-members", _accept_five_point_run),
    ("orthogonal-grids-with-y-lines", "spec-lot0-rotated-grid", _accept_orthogonal_with_y_lines),
    ("near-orthogonal-90.6", "spec-lot0-rotated-grid", _two_empty_y(0, 90.6)),
    ("origin-z-0.05", "spec-lot0-grid", _accept_origin_z_small),
]


@pytest.mark.parametrize(("case", "name", "mutate"), SEMANTIC_ACCEPTS, ids=[c[0] for c in SEMANTIC_ACCEPTS])
def test_spec_semantic_accepts(case, name, mutate, example):
    spec = example(name)
    mutate(spec)
    assert _paths(spec) == []


# --- spec: ADR-0016 semantic rules (i)-(q) ----------------------------------------------------------
# Examples: spec-foundations (members 0 pile, 1 pile_cap, 2 pad_footing, 3 strip_footing; polygonal_caps 0)
# and spec-slab-wall (slab 0 is 6000 x 7500 at z 3600 with opening 0 at x 1000-3400, y 1000-2200;
# wall 0 runs (0, 9000) to (4000, 9000), base z 3600, height 3480, opening 0 at along 1000-1900, z 3600-5700).

SW = "spec-slab-wall"
FD = "spec-foundations"
SLAB_Z = 3600
WALL_Y = 9000


def _node(spec, path):
    for key in path:
        spec = spec[key]
    return spec


def _pts(path, *points, key="outline"):
    """Replace <path>[key] with (x, y, z[, chamfer]) tuples, copying the first point as the template."""

    def apply(spec):
        holder = _node(spec, path)
        template = holder[key][0]
        built = []
        for x, y, z, *rest in points:
            item = copy.deepcopy(template)
            item.update(x=x, y=y, z=z, chamfer=rest[0] if rest else "none")
            built.append(item)
        holder[key] = built

    return apply


def _slab_pts(*points):
    return _pts(("slabs", 0), *points)


def _cap_pts(*points):
    return _pts(("polygonal_caps", 0), *points)


def _slab_open_pts(*points):
    return _pts(("slabs", 0, "openings", 0), *points)


def _wall_open_pts(*points):
    return _pts(("walls", 0, "openings", 0), *points)


def _flat(*xy, z=SLAB_Z):
    return [(x, y, z) for x, y in xy]


def _on_wall(*along_z, y=WALL_Y):
    """Wall opening points from (along, z) pairs on the x-aligned example wall."""
    return [(a, y, z) for a, z in along_z]


def _add_opening(parent, spec_id, points):
    def apply(spec):
        holder = spec[parent[0]][parent[1]]
        extra = copy.deepcopy(holder["openings"][0])
        extra["spec_id"] = spec_id
        holder["openings"].append(extra)
        _pts((*parent, "openings", len(holder["openings"]) - 1), *points)(spec)

    return apply


def _move(path, **fields):
    def apply(spec):
        _node(spec, path).update(fields)

    return apply


def _both(*mutators):
    def apply(spec):
        for mutate in mutators:
            mutate(spec)

    return apply


def _copy_id(src, dst):
    def apply(spec):
        _node(spec, dst[:-1])[dst[-1]] = _node(spec, src)

    return apply


def _drawing_only_at(path):
    return _set((*path, "provenance"), DRAWING_ONLY)


def _low_opening(parent_questions, opening_questions, parent):
    """A low value inside opening 0 of `parent`, with question ids on the parent and/or the opening."""

    def apply(spec):
        holder = spec[parent[0]][parent[1]]
        opening = holder["openings"][0]
        opening["outline"][1]["confidence"] = "low"
        if parent_questions is not None:
            holder["question_ids"] = parent_questions
        if opening_questions is not None:
            opening["question_ids"] = opening_questions
        spec["open_questions"] = ["Q-021", "Q-022"]

    return apply


def _low_parent_only(parent):
    """A low parent value while only the opening names a question."""

    def apply(spec):
        holder = spec[parent[0]][parent[1]]
        holder["thickness" if parent[0] == "slabs" else "height"]["confidence"] = "low"
        holder["openings"][0]["question_ids"] = ["Q-021"]
        spec["open_questions"] = ["Q-021"]

    return apply


def _circle(count, radius=3000):
    return [
        (
            round(radius * math.cos(2 * math.pi * k / count), 3),
            round(radius * math.sin(2 * math.pi * k / count), 3),
            SLAB_Z,
        )
        for k in range(count)
    ]


SLAB_SQUARE = _flat((0, 0), (6000, 0), (6000, 7500), (0, 7500))
L_SLAB = _flat((0, 0), (6000, 0), (6000, 3000), (3000, 3000), (3000, 7500), (0, 7500))
OPEN_MAIN = _flat((1000, 1000), (3400, 1000), (3400, 2200), (1000, 2200))
D1 = _on_wall((1000, 3600), (1000, 5700), (1900, 5700), (1900, 3600))
W_SLAB = ("slabs", 0)
W_WALL = ("walls", 0)
S_OPEN2 = ("slabs", 0, "openings", 1)
CAP_HEX = [
    (13900, 3400, -700),
    (16100, 3400, -700),
    (16650, 4350, -700),
    (15550, 6250, -700),
    (14450, 6250, -700),
    (13350, 4350, -700),
]

# (case id, example, mutation, JSON pointer prefix, message fragment)
ADR16_REJECTS = [
    # (i) spec_id unique across all arrays and nested openings
    (
        "i-wall-vs-slab",
        SW,
        _copy_id(("slabs", 0, "spec_id"), ("walls", 0, "spec_id")),
        "/walls/0/spec_id",
        "also /slabs/0",
    ),
    (
        "i-cap-vs-member",
        FD,
        _copy_id(("members", 0, "spec_id"), ("polygonal_caps", 0, "spec_id")),
        "/polygonal_caps/0/spec_id",
        "also /members/0",
    ),
    (
        "i-cap-vs-member-later-member",
        FD,
        _copy_id(("polygonal_caps", 0, "spec_id"), ("members", 1, "spec_id")),
        "/polygonal_caps/0/spec_id",
        "also /members/1",
    ),
    (
        "i-opening-vs-parent",
        SW,
        _copy_id(("slabs", 0, "spec_id"), ("slabs", 0, "openings", 0, "spec_id")),
        "/slabs/0/openings/0/spec_id",
        "also /slabs/0",
    ),
    (
        "i-wall-opening-vs-slab-opening",
        SW,
        _copy_id(("slabs", 0, "openings", 0, "spec_id"), ("walls", 0, "openings", 0, "spec_id")),
        "/walls/0/openings/0/spec_id",
        "also /slabs/0/openings/0",
    ),
    (
        "i-opening-vs-sibling-opening",
        SW,
        _add_opening(W_SLAB, "L4-S-A1B2-O1", _flat((4000, 1000), (5000, 1000), (5000, 2000), (4000, 2000))),
        "/slabs/0/openings/1/spec_id",
        "also /slabs/0/openings/0",
    ),
    # (j) vertical pad_footing, pile_cap, pile
    ("j-pile-flat", FD, _move(("members", 0, "end"), z=-1400), "/members/0/end", "at least 1 mm above"),
    (
        "j-pile-toe-above-head",
        FD,
        _move(("members", 0, "end"), z=-1000),
        "/members/0/end",
        "at least 1 mm above",
    ),
    (
        "j-cap-half-mm-drop",
        FD,
        _move(("members", 1, "end"), z=-700.5),
        "/members/1/end",
        "at least 1 mm above",
    ),
    ("j-pad-reversed", FD, _move(("members", 2, "end"), z=-500), "/members/2/end", "at least 1 mm above"),
    ("j-pile-leans-x", FD, _move(("members", 0, "end"), x=3000.5), "/members/0/end", "in plan"),
    ("j-cap-leans-y", FD, _move(("members", 1, "end"), y=4001), "/members/1/end", "in plan"),
    (
        "j-pad-leans-diagonal",
        FD,
        _move(("members", 2, "end"), x=9000.1, y=4000.1),
        "/members/2/end",
        "in plan",
    ),
    # (k) horizontal strip_footing
    ("k-strip-sloped", FD, _move(("members", 3, "end"), z=-1000.5), "/members/3/end", "differ"),
    ("k-strip-sloped-up", FD, _move(("members", 3, "end"), z=-500), "/members/3/end", "differ"),
    # (l) closed outlines
    (
        "l-slab-close-points",
        SW,
        _slab_pts(*_flat((0, 0), (6000, 0), (6000, 7500), (0, 0.5))),
        "/slabs/0/outline",
        "less than 1 mm apart",
    ),
    (
        "l-slab-adjacent-points",
        SW,
        _slab_pts(*_flat((0, 0), (0.5, 0), (6000, 7500), (0, 7500))),
        "/slabs/0/outline",
        "less than 1 mm apart",
    ),
    (
        "l-slab-repeated-point",
        SW,
        _slab_pts(*_flat((0, 0), (6000, 0), (6000, 7500), (0, 7500), (6000.2, 0.2))),
        "/slabs/0/outline",
        "repeated point",
    ),
    (
        "l-slab-bowtie",
        SW,
        _slab_pts(*_flat((0, 0), (6000, 7500), (6000, 0), (0, 7500))),
        "/slabs/0/outline",
        "meet",
    ),
    (
        "l-slab-bowtie-closing-edge",
        SW,
        _slab_pts(*_flat((0, 0), (6000, 0), (0, 7500), (6000, 7500))),
        "/slabs/0/outline",
        "meet",
    ),
    (
        "l-slab-near-touch",
        SW,
        _slab_pts(*_flat((0, 0), (6000, 0), (6000, 7500), (3000, 0.5), (0, 7500))),
        "/slabs/0/outline",
        "meet",
    ),
    (
        "l-slab-arcs-in-a-row",
        SW,
        _slab_pts(
            (0, 0, SLAB_Z),
            (6000, 0, SLAB_Z, "arc_point"),
            (6000, 7500, SLAB_Z, "arc_point"),
            (0, 7500, SLAB_Z),
        ),
        "/slabs/0/outline/2/chamfer",
        "arc_point in a row",
    ),
    (
        "l-slab-arcs-in-a-row-cyclic",
        SW,
        _slab_pts(
            (0, 0, SLAB_Z, "arc_point"),
            (6000, 0, SLAB_Z),
            (6000, 7500, SLAB_Z),
            (0, 7500, SLAB_Z, "arc_point"),
        ),
        "/slabs/0/outline/0/chamfer",
        "arc_point in a row",
    ),
    (
        "l-slab-arc-on-chord",
        SW,
        _slab_pts(
            (0, 0, SLAB_Z),
            (3000, 0.5, SLAB_Z, "arc_point"),
            (6000, 0, SLAB_Z),
            (6000, 7500, SLAB_Z),
            (0, 7500, SLAB_Z),
        ),
        "/slabs/0/outline/1",
        "chord",
    ),
    (
        "l-slab-arc-on-chord-last-point",
        SW,
        _slab_pts(
            (0, 0, SLAB_Z),
            (6000, 0, SLAB_Z),
            (6000, 7500, SLAB_Z),
            (0, 7500, SLAB_Z),
            (0.5, 3750, SLAB_Z, "arc_point"),
        ),
        "/slabs/0/outline/4",
        "chord",
    ),
    (
        "l-slab-arc-on-chord-cyclic",
        SW,
        _slab_pts(
            (3000, 0.5, SLAB_Z, "arc_point"),
            (6000, 0, SLAB_Z),
            (6000, 7500, SLAB_Z),
            (0, 7500, SLAB_Z),
            (0, 0, SLAB_Z),
        ),
        "/slabs/0/outline/0",
        "chord",
    ),
    ("l-slab-clockwise", SW, _slab_pts(*SLAB_SQUARE[::-1]), "/slabs/0/outline", "clockwise"),
    (
        "l-slab-tiny-area",
        SW,
        _slab_pts(*_flat((0, 0), (1000, 0), (0, 0.001))),
        "/slabs/0/outline",
        "less than 1 mm2",
    ),
    ("l-cap-clockwise", FD, _cap_pts(*CAP_HEX[::-1]), "/polygonal_caps/0/outline", "clockwise"),
    (
        "l-cap-bowtie",
        FD,
        _cap_pts((13900, 3400, -700), (16100, 6250, -700), (16100, 3400, -700), (13900, 6250, -700)),
        "/polygonal_caps/0/outline",
        "meet",
    ),
    (
        "l-cap-arcs-in-a-row",
        FD,
        _cap_pts(
            *CAP_HEX[:2], (16650, 4350, -700, "arc_point"), (15550, 6250, -700, "arc_point"), *CAP_HEX[4:]
        ),
        "/polygonal_caps/0/outline/3/chamfer",
        "arc_point in a row",
    ),
    (
        "l-slab-opening-clockwise",
        SW,
        _slab_open_pts(*OPEN_MAIN[::-1]),
        "/slabs/0/openings/0/outline",
        "clockwise",
    ),
    (
        "l-slab-opening-bowtie",
        SW,
        _slab_open_pts(*_flat((1000, 1000), (3400, 2200), (3400, 1000), (1000, 2200))),
        "/slabs/0/openings/0/outline",
        "meet",
    ),
    (
        "l-slab-opening-close-points",
        SW,
        _slab_open_pts(*_flat((1000, 1000), (3400, 1000), (3400, 2200), (1000, 1000.4))),
        "/slabs/0/openings/0/outline",
        "less than 1 mm apart",
    ),
    ("l-wall-opening-clockwise", SW, _wall_open_pts(*D1[::-1]), "/walls/0/openings/0/outline", "clockwise"),
    (
        "l-wall-opening-bowtie",
        SW,
        _wall_open_pts(*_on_wall((1000, 3600), (1900, 5700), (1900, 3600), (1000, 5700))),
        "/walls/0/openings/0/outline",
        "meet",
    ),
    (
        "l-wall-opening-flat",
        SW,
        _wall_open_pts(*_on_wall((1000, 3600), (1900, 3600), (1500, 3600.002))),
        "/walls/0/openings/0/outline",
        "less than 1 mm2",
    ),
    (
        "l-wall-reversed-direction-opening",
        SW,
        _both(_move(("walls", 0, "start"), x=4000), _move(("walls", 0, "end"), x=0)),
        "/walls/0/openings/0/outline",
        "clockwise",
    ),
    # (m) one z, openings inside the slab, no openings with an arc
    ("m-slab-z-off", SW, _move(("slabs", 0, "outline", 2), z=SLAB_Z + 0.5), "/slabs/0/outline/2", "z"),
    (
        "m-slab-z-off-first-point",
        SW,
        _move(("slabs", 0, "outline", 0), z=SLAB_Z - 1),
        "/slabs/0/outline",
        "z",
    ),
    (
        "m-cap-z-off",
        FD,
        _move(("polygonal_caps", 0, "outline", 3), z=-699.5),
        "/polygonal_caps/0/outline/3",
        "z",
    ),
    (
        "m-opening-z-off",
        SW,
        _move(("slabs", 0, "openings", 0, "outline", 1), z=SLAB_Z + 0.5),
        "/slabs/0/openings/0/outline/1",
        "z",
    ),
    (
        "m-opening-outside",
        SW,
        _slab_open_pts(*_flat((7000, 1000), (9400, 1000), (9400, 2200), (7000, 2200))),
        "/slabs/0/openings/0/outline/0",
        "outside the slab",
    ),
    (
        "m-opening-pokes-out",
        SW,
        _slab_open_pts(*_flat((1000, 1000), (6500, 1000), (6500, 2200), (1000, 2200))),
        "/slabs/0/openings/0/outline/1",
        "outside the slab",
    ),
    (
        "m-opening-barely-out",
        SW,
        _slab_open_pts(*_flat((-1.5, 1000), (3400, 1000), (3400, 2200), (-1.5, 2200))),
        "/slabs/0/openings/0/outline/0",
        "outside the slab",
    ),
    (
        "m-opening-in-the-notch",
        SW,
        _both(
            _slab_pts(*L_SLAB), _slab_open_pts(*_flat((4000, 4000), (5000, 4000), (5000, 5000), (4000, 5000)))
        ),
        "/slabs/0/openings/0/outline/0",
        "outside the slab",
    ),
    (
        "m-arc-slab-with-openings",
        SW,
        _slab_pts((0, 0, SLAB_Z), (6000, 0, SLAB_Z, "arc_point"), (6000, 7500, SLAB_Z), (0, 7500, SLAB_Z)),
        "/slabs/0/openings",
        "arc_point",
    ),
    # (n) walls
    ("n-wall-base-sloped", SW, _move(("walls", 0, "end"), z=SLAB_Z + 0.5), "/walls/0/end", "differ"),
    ("n-wall-no-length", SW, _move(("walls", 0, "end"), x=0), "/walls/0/end", "less than 1 mm"),
    ("n-wall-half-mm-long", SW, _move(("walls", 0, "end"), x=0.5), "/walls/0/end", "less than 1 mm"),
    (
        "n-opening-off-plane",
        SW,
        _move(("walls", 0, "openings", 0, "outline", 1), y=WALL_Y + 0.5),
        "/walls/0/openings/0/outline/1",
        "vertical plane",
    ),
    (
        "n-opening-off-plane-negative",
        SW,
        _move(("walls", 0, "openings", 0, "outline", 2), y=WALL_Y - 2),
        "/walls/0/openings/0/outline/2",
        "vertical plane",
    ),
    (
        "n-opening-past-end",
        SW,
        _wall_open_pts(*_on_wall((1000, 3600), (1000, 5700), (4500, 5700), (4500, 3600))),
        "/walls/0/openings/0/outline/2",
        "outside the wall rectangle",
    ),
    (
        "n-opening-before-start",
        SW,
        _wall_open_pts(*_on_wall((-2, 3600), (-2, 5700), (1900, 5700), (1900, 3600))),
        "/walls/0/openings/0/outline/0",
        "outside the wall rectangle",
    ),
    (
        "n-opening-above-top",
        SW,
        _wall_open_pts(*_on_wall((1000, 3600), (1000, 7082), (1900, 7082), (1900, 3600))),
        "/walls/0/openings/0/outline/1",
        "outside the wall rectangle",
    ),
    (
        "n-opening-below-base",
        SW,
        _wall_open_pts(*_on_wall((1000, 3598), (1000, 5700), (1900, 5700), (1900, 3598))),
        "/walls/0/openings/0/outline/0",
        "outside the wall rectangle",
    ),
    (
        "n-diagonal-wall-opening-off-plane",
        SW,
        _both(
            _move(("walls", 0, "start"), x=0, y=0),
            _move(("walls", 0, "end"), x=3000, y=4000),
            _wall_open_pts((600, 800, 3600), (600, 800, 5700), (1145, 1520, 5700), (1140, 1520, 3600)),
        ),
        "/walls/0/openings/0/outline/2",
        "vertical plane",
    ),
    # (o) openings of one parent
    (
        "o-slab-edges-cross",
        SW,
        _add_opening(W_SLAB, "L4-S-A1B2-O2", _flat((3000, 1500), (5000, 1500), (5000, 3000), (3000, 3000))),
        "/slabs/0/openings/1",
        "overlap",
    ),
    (
        "o-slab-nested",
        SW,
        _add_opening(W_SLAB, "L4-S-A1B2-O2", _flat((1500, 1300), (2500, 1300), (2500, 2000), (1500, 2000))),
        "/slabs/0/openings/1",
        "overlap",
    ),
    (
        "o-slab-contains-the-first",
        SW,
        _add_opening(W_SLAB, "L4-S-A1B2-O2", _flat((500, 500), (4000, 500), (4000, 3000), (500, 3000))),
        "/slabs/0/openings/1",
        "overlap",
    ),
    (
        "o-slab-identical",
        SW,
        _add_opening(W_SLAB, "L4-S-A1B2-O2", OPEN_MAIN),
        "/slabs/0/openings/1",
        "overlap",
    ),
    (
        "o-slab-half-mm-apart",
        SW,
        _add_opening(
            W_SLAB, "L4-S-A1B2-O2", _flat((3400.5, 1000), (5000, 1000), (5000, 2200), (3400.5, 2200))
        ),
        "/slabs/0/openings/1",
        "overlap",
    ),
    (
        "o-wall-edges-cross",
        SW,
        _add_opening(
            W_WALL, "L4-W-C-12-D2", _on_wall((1500, 4000), (1500, 5000), (2500, 5000), (2500, 4000))
        ),
        "/walls/0/openings/1",
        "overlap",
    ),
    (
        "o-wall-nested",
        SW,
        _add_opening(
            W_WALL, "L4-W-C-12-D2", _on_wall((1200, 4000), (1200, 5000), (1500, 5000), (1500, 4000))
        ),
        "/walls/0/openings/1",
        "overlap",
    ),
    ("o-wall-identical", SW, _add_opening(W_WALL, "L4-W-C-12-D2", D1), "/walls/0/openings/1", "overlap"),
    # (p) elevation provenance of the new paths, and (f) is not repeated for members
    (
        "p-slab-outline",
        SW,
        _drawing_only_at(("slabs", 0, "outline", 1)),
        "/slabs/0/outline/1",
        "engineer_answer",
    ),
    (
        "p-slab-outline-last",
        SW,
        _drawing_only_at(("slabs", 0, "outline", 3)),
        "/slabs/0/outline/3",
        "engineer_answer",
    ),
    (
        "p-cap-outline",
        FD,
        _drawing_only_at(("polygonal_caps", 0, "outline", 2)),
        "/polygonal_caps/0/outline/2",
        "engineer_answer",
    ),
    ("p-wall-start", SW, _drawing_only_at(("walls", 0, "start")), "/walls/0/start", "engineer_answer"),
    ("p-wall-end", SW, _drawing_only_at(("walls", 0, "end")), "/walls/0/end", "engineer_answer"),
    ("p-pile-head", FD, _drawing_only_at(("members", 0, "start")), "/members/0/start", "engineer_answer"),
    ("p-pile-cap-bottom", FD, _drawing_only_at(("members", 1, "end")), "/members/1/end", "engineer_answer"),
    ("p-pad-top", FD, _drawing_only_at(("members", 2, "start")), "/members/2/start", "engineer_answer"),
    ("p-pad-bottom", FD, _drawing_only_at(("members", 2, "end")), "/members/2/end", "engineer_answer"),
    ("p-strip-start", FD, _drawing_only_at(("members", 3, "start")), "/members/3/start", "engineer_answer"),
    ("p-strip-end", FD, _drawing_only_at(("members", 3, "end")), "/members/3/end", "engineer_answer"),
    # (q) low confidence in slabs, caps, walls and each opening
    ("q-slab-thickness", SW, _lowconf(("slabs", 0, "thickness")), "/slabs/0", "without a question_id"),
    ("q-slab-material", SW, _lowconf(("slabs", 0, "material")), "/slabs/0", "without a question_id"),
    ("q-slab-outline-point", SW, _lowconf(("slabs", 0, "outline", 2)), "/slabs/0", "without a question_id"),
    (
        "q-cap-outline-point",
        FD,
        _lowconf(("polygonal_caps", 0, "outline", 1)),
        "/polygonal_caps/0",
        "without a question_id",
    ),
    (
        "q-cap-thickness",
        FD,
        _lowconf(("polygonal_caps", 0, "thickness")),
        "/polygonal_caps/0",
        "without a question_id",
    ),
    ("q-wall-height", SW, _lowconf(("walls", 0, "height")), "/walls/0", "without a question_id"),
    ("q-wall-start", SW, _lowconf(("walls", 0, "start")), "/walls/0", "without a question_id"),
    (
        "q-slab-opening-point",
        SW,
        _lowconf(("slabs", 0, "openings", 0, "outline", 1)),
        "/slabs/0/openings/0",
        "without a question_id",
    ),
    (
        "q-slab-opening-point-parent-has-question",
        SW,
        _low_opening(["Q-021"], None, W_SLAB),
        "/slabs/0/openings/0",
        "without a question_id",
    ),
    (
        "q-wall-opening-point-parent-has-question",
        SW,
        _low_opening(["Q-021"], None, W_WALL),
        "/walls/0/openings/0",
        "without a question_id",
    ),
    (
        "q-slab-low-only-opening-has-question",
        SW,
        _low_parent_only(W_SLAB),
        "/slabs/0",
        "without a question_id",
    ),
    (
        "q-wall-low-only-opening-has-question",
        SW,
        _low_parent_only(W_WALL),
        "/walls/0",
        "without a question_id",
    ),
    (
        "q-slab-unknown-question",
        SW,
        _set(("slabs", 0, "question_ids"), ["Q-099"]),
        "/slabs/0/question_ids",
        "not listed",
    ),
    (
        "q-cap-unknown-question",
        FD,
        _set(("polygonal_caps", 0, "question_ids"), ["Q-099"]),
        "/polygonal_caps/0/question_ids",
        "not listed",
    ),
    (
        "q-wall-unknown-question",
        SW,
        _set(("walls", 0, "question_ids"), ["Q-099"]),
        "/walls/0/question_ids",
        "not listed",
    ),
    (
        "q-opening-unknown-question",
        SW,
        _set(("slabs", 0, "openings", 0, "question_ids"), ["Q-099"]),
        "/slabs/0/openings/0/question_ids",
        "not listed",
    ),
    (
        "q-wall-opening-unknown-question",
        SW,
        _set(("walls", 0, "openings", 0, "question_ids"), ["Q-099"]),
        "/walls/0/openings/0/question_ids",
        "not listed",
    ),
]


@pytest.mark.parametrize(
    ("case", "name", "mutate", "path", "fragment"), ADR16_REJECTS, ids=[c[0] for c in ADR16_REJECTS]
)
def test_adr16_semantic_rejects(case, name, mutate, path, fragment, example):
    spec = example(name)
    mutate(spec)
    problems = validate("spec", spec)
    assert any(p.path.startswith(path) and fragment in p.message for p in problems), (case, problems)


def _accept_open_at_edge(spec):
    _slab_open_pts(*_flat((0, 1000), (2400, 1000), (2400, 2200), (0, 2200)))(spec)


def _accept_open_half_mm_out(spec):
    _slab_open_pts(*_flat((-0.5, 1000), (2400, 1000), (2400, 2200), (-0.5, 2200)))(spec)


def _accept_open_inside_l(spec):
    _slab_pts(*L_SLAB)(spec)


def _accept_arc_slab_without_openings(spec):
    _slab_pts(
        (0, 0, SLAB_Z),
        (3000, -300, SLAB_Z, "arc_point"),
        (6000, 0, SLAB_Z),
        (6000, 7500, SLAB_Z),
        (0, 7500, SLAB_Z),
    )(spec)
    del spec["slabs"][0]["openings"]


def _accept_arc_slab_corner_zero(spec):
    _slab_pts(
        (0, 0, SLAB_Z, "arc_point"),
        (6000, 0, SLAB_Z),
        (6000, 7500, SLAB_Z),
        (3000, 8000, SLAB_Z, "arc_point"),
        (0, 7500, SLAB_Z),
    )(spec)
    del spec["slabs"][0]["openings"]


def _accept_many_points(spec):
    _slab_pts(*_circle(130))(spec)
    del spec["slabs"][0]["openings"]


def _accept_wall_diagonal(spec):
    _both(
        _move(("walls", 0, "start"), x=0, y=0),
        _move(("walls", 0, "end"), x=3000, y=4000),
        _wall_open_pts((600, 800, 3600), (600, 800, 5700), (1140, 1520, 5700), (1140, 1520, 3600)),
    )(spec)


def _accept_wall_negative_direction(spec):
    _both(
        _move(("walls", 0, "start"), x=4000),
        _move(("walls", 0, "end"), x=0),
        _wall_open_pts(*_on_wall((1900, 3600), (1900, 5700), (1000, 5700), (1000, 3600))),
    )(spec)


def _accept_wall_north(spec):
    # Wall along +y: Z x direction = -x, so a CCW opening runs the same (along, z) order as D1.
    _both(
        _move(("walls", 0, "start"), x=0, y=0),
        _move(("walls", 0, "end"), x=0, y=4000),
        _wall_open_pts((0, 1000, 3600), (0, 1000, 5700), (0, 1900, 5700), (0, 1900, 3600)),
    )(spec)


def _accept_second_opening(offset):
    return _add_opening(
        W_SLAB,
        "L4-S-A1B2-O2",
        _flat((3400 + offset, 1000), (5000, 1000), (5000, 2200), (3400 + offset, 2200)),
    )


def _accept_wall_second_opening(spec):
    _add_opening(W_WALL, "L4-W-C-12-D2", _on_wall((1902, 3600), (1902, 5000), (2500, 5000), (2500, 3600)))(
        spec
    )


def _accept_low_with_own_question(parent):
    return _low_opening(None, ["Q-021"], parent)


def _accept_parent_and_opening_questions(parent):
    return _low_opening(["Q-022"], ["Q-021"], parent)


def _accept_slab_low_with_question(spec):
    _lowconf(("slabs", 0, "thickness"), ["Q-021"])(spec)
    spec["open_questions"] = ["Q-021"]


def _accept_cap_low_with_question(spec):
    _lowconf(("polygonal_caps", 0, "outline", 1), ["Q-021"])(spec)
    spec["open_questions"] = ["Q-051", "Q-021"]


def _accept_wall_low_with_question(spec):
    _lowconf(("walls", 0, "start"), ["Q-021"])(spec)
    spec["open_questions"] = ["Q-021"]


def _accept_opening_pins_a_value(spec):
    _move(("walls", 0, "openings", 0, "outline", 1), y=WALL_Y + 0.1)(spec)
    _move(("walls", 0, "end"), x=4000.9)(spec)
    _wall_open_pts(*_on_wall((1000, 3600), (1000, 5700), (4000.9, 5700), (4000.9, 3600)))(spec)
    _move(("walls", 0, "openings", 0, "outline", 1), y=WALL_Y + 0.1)(spec)


ADR16_ACCEPTS = [
    ("j-pile-one-mm-drop", FD, _move(("members", 0, "end"), z=-1401)),
    ("j-pad-plan-offset-0.1", FD, _move(("members", 2, "end"), x=9000.1)),
    ("j-cap-plan-offset-0.1-y", FD, _move(("members", 1, "end"), y=4000.1)),
    ("k-strip-z-offset-0.1", FD, _move(("members", 3, "end"), z=-1000.1)),
    (
        "k-strip-other-z",
        FD,
        _both(_move(("members", 3, "start"), z=-2000), _move(("members", 3, "end"), z=-2000)),
    ),
    ("l-opening-point-count-is-not-checked", SW, _accept_many_points),
    ("l-slab-arc-point-ok", SW, _accept_arc_slab_without_openings),
    ("l-slab-arc-point-at-closing-edge", SW, _accept_arc_slab_corner_zero),
    ("m-slab-z-0.1-off", SW, _move(("slabs", 0, "outline", 2), z=SLAB_Z + 0.1)),
    ("m-opening-z-0.1-off", SW, _move(("slabs", 0, "openings", 0, "outline", 1), z=SLAB_Z + 0.1)),
    ("m-opening-on-slab-edge", SW, _accept_open_at_edge),
    ("m-opening-half-mm-out", SW, _accept_open_half_mm_out),
    ("m-opening-in-l-slab", SW, _accept_open_inside_l),
    ("n-wall-z-0.1-off", SW, _move(("walls", 0, "end"), z=SLAB_Z + 0.1)),
    (
        "n-wall-length-1",
        SW,
        _both(
            _move(("walls", 0, "end"), x=1),
            _wall_open_pts(*_on_wall((0, 3600), (0, 5700), (1, 5700), (1, 3600))),
        ),
    ),
    (
        "n-opening-is-the-whole-wall",
        SW,
        _wall_open_pts(*_on_wall((0, 3600), (0, 7080), (4000, 7080), (4000, 3600))),
    ),
    (
        "n-opening-1mm-over-the-edge",
        SW,
        _wall_open_pts(*_on_wall((-1, 3599), (-1, 7081), (4001, 7081), (4001, 3599))),
    ),
    ("n-opening-0.1-off-plane", SW, _accept_opening_pins_a_value),
    ("n-diagonal-wall", SW, _accept_wall_diagonal),
    ("n-wall-running-west", SW, _accept_wall_negative_direction),
    ("n-wall-running-north", SW, _accept_wall_north),
    ("o-slab-openings-2mm-apart", SW, _accept_second_opening(2)),
    ("o-slab-openings-far-apart", SW, _accept_second_opening(500)),
    ("o-wall-openings-2mm-apart", SW, _accept_wall_second_opening),
    ("p-pile-toe-drawing-only", FD, _drawing_only_at(("members", 0, "end"))),
    ("p-slab-opening-point-drawing-only", SW, _drawing_only_at(("slabs", 0, "openings", 0, "outline", 1))),
    ("p-wall-opening-point-drawing-only", SW, _drawing_only_at(("walls", 0, "openings", 0, "outline", 1))),
    ("q-slab-low-with-question", SW, _accept_slab_low_with_question),
    ("q-cap-low-with-question", FD, _accept_cap_low_with_question),
    ("q-wall-low-with-question", SW, _accept_wall_low_with_question),
    ("q-slab-opening-low-with-own-question", SW, _accept_low_with_own_question(W_SLAB)),
    ("q-wall-opening-low-with-own-question", SW, _accept_low_with_own_question(W_WALL)),
    ("q-opening-and-parent-questions", SW, _accept_parent_and_opening_questions(W_SLAB)),
]


@pytest.mark.parametrize(("case", "name", "mutate"), ADR16_ACCEPTS, ids=[c[0] for c in ADR16_ACCEPTS])
def test_adr16_semantic_accepts(case, name, mutate, example):
    spec = example(name)
    mutate(spec)
    assert _paths(spec) == []


@pytest.mark.parametrize(
    ("name", "path"),
    [
        (FD, ("members", 2, "end")),
        (FD, ("members", 2, "start")),
        (FD, ("members", 1, "end")),
        (FD, ("members", 3, "end")),
        (FD, ("members", 0, "start")),
        (FD, ("polygonal_caps", 0, "outline", 2)),
        (SW, ("slabs", 0, "outline", 1)),
        (SW, ("walls", 0, "start")),
        (SW, ("walls", 0, "end")),
    ],
    ids=lambda v: "/".join(map(str, v)) if isinstance(v, tuple) else v,
)
def test_adr16_each_elevation_path_is_checked_once(name, path, example):
    spec = example(name)
    _drawing_only_at(path)(spec)
    pointer = "/" + "/".join(map(str, path))
    assert [p.path for p in check_spec(spec)].count(pointer) == 1


def test_adr16_examples_still_valid(example):
    for name in (SW, FD):
        assert _paths(example(name)) == []


def test_adr16_opening_low_value_reports_the_opening_not_the_parent(example):
    spec = example(SW)
    _low_opening(["Q-022"], None, W_SLAB)(spec)
    paths = _paths(spec)
    assert "/slabs/0/openings/0" in paths
    assert "/slabs/0" not in paths


def test_adr16_parent_low_value_does_not_ask_for_an_opening_question(example):
    spec = example(SW)
    _lowconf(("slabs", 0, "thickness"), ["Q-021"])(spec)
    spec["open_questions"] = ["Q-021"]
    assert _paths(spec) == []


# --- spec: review fixes of the check_spec rules (P15-5c) ------------------------------------------------

BIG = 1e200  # squares overflow to inf, inf - inf is NaN: the geometry rules must refuse, not accept


def _bowtie_slab(spec):
    _slab_pts(*_flat((0, 0), (BIG, BIG), (BIG, 0), (0, BIG)))(spec)
    spec["slabs"][0]["openings"] = []


def _bowtie_wall(spec):
    _move(("walls", 0, "start"), x=0, y=0, z=0)(spec)
    _move(("walls", 0, "end"), x=BIG, y=0, z=0)(spec)
    _set(("walls", 0, "height", "value"), BIG)(spec)
    _wall_open_pts(*_on_wall((0, 0), (BIG, BIG), (BIG, 0), (0, BIG), y=0))(spec)


def _lift_opening(mm):
    def apply(spec):
        for point in spec["slabs"][0]["openings"][0]["outline"]:
            point["z"] += mm

    return apply


def _high_levels(count):
    def apply(spec):
        grid = _grid0(spec)
        template = grid["levels"][0]
        grid["levels"] = []
        for i in range(count):
            level = copy.deepcopy(template)
            level["label"]["value"] = f"L{i}"
            level["z"]["value"] = 1_000_000 + i
            grid["levels"].append(level)

    return apply


def _huge_wall(spec):
    _move(("walls", 0, "start"), x=-1e308)(spec)
    _move(("walls", 0, "end"), x=1e308)(spec)


U_SLAB = _flat(
    (0, 0), (9000, 0), (9000, 9000), (6000, 9000), (6000, 3000), (3000, 3000), (3000, 9000), (0, 9000)
)
SPAN_OPENING = _flat((1000, 6000), (8000, 6000), (8000, 7000), (1000, 7000))
ARM_OPENING = _flat((1000, 6000), (2500, 6000), (2500, 7000), (1000, 7000))
TILTED = [(0, 0, 0), (5000, 0, 0), (10000, 0, 0.5), (10000, 5000, 3000), (0, 5000, 3000)]
HAIRPIN = [(0, 0, Z), (0, 5000, Z), (100, 5000, Z), (100, 0, Z)]

P15_5C_REJECTS = [
    # M-1 / M-2: overflow is a normal problem, never a traceback and never an accept
    (
        "m1-position-1e307",
        "spec-lot0-grid",
        _px("x_lines", 1, 1e307),
        "/grids/0/x_lines/1/position",
        "0.01 mm step",
    ),
    (
        "m1-origin-x-1e307",
        "spec-lot0-grid",
        _set(("grids", 0, "origin", "x"), 1e307),
        "/grids/0/origin/x",
        "0.01 mm",
    ),
    ("m2-bowtie-slab-1e200", SW, _bowtie_slab, "/slabs/0/outline", "cannot be evaluated"),
    ("m2-bowtie-wall-opening-1e200", SW, _bowtie_wall, "/walls/0/openings/0/outline", "cannot be evaluated"),
    (
        "m2-poly-member-1e200",
        "spec-poly-members",
        _poly((0, 0, 0), (BIG, 0, 0), (BIG, BIG, 0), (0, BIG, BIG / 10)),
        "/poly_members/0",
        "cannot be evaluated",
    ),
    # m-1: an opening edge that crosses the outline spans the gap of a concave slab
    (
        "m-opening-spans-u-gap",
        SW,
        _both(_slab_pts(*U_SLAB), _slab_open_pts(*SPAN_OPENING)),
        "/slabs/0/openings/0/outline",
        "crosses slab outline edge",
    ),
    # m-2: two consecutive segments that double back, first and last included
    (
        "g-fold-back-last-segment",
        "spec-poly-members",
        _poly((0, 0, Z), (0, 5000, Z), (10000, 5000, Z), (5000, 5000, Z)),
        "/poly_members/0/points/2",
        "fold back",
    ),
    (
        "g-fold-back-first-segment",
        "spec-poly-members",
        _poly((5000, 5000, Z), (10000, 5000, Z), (0, 5000, Z), (0, 0, Z)),
        "/poly_members/0/points/1",
        "fold back",
    ),
    ("m2-wall-length-overflows", SW, _huge_wall, "/walls/0/end", "cannot be evaluated"),
    (
        "g-fold-back-half-mm-lateral",
        "spec-poly-members",
        _poly((0, 0, Z), (0, 5000, Z), (10000, 5000, Z), (5000, 5000.5, Z)),
        "/poly_members/0/points/2",
        "fold back",
    ),
    # m-3: inputs that pin tolerances the mutation run found loose
    (
        "m8-level-z-is-absolute",
        "spec-lot0-grid",
        _high_levels(110),
        "/grids/0/levels",
        "composed CoordinateZ",
    ),
    (
        "m11-opening-z-against-slab",
        SW,
        _lift_opening(50),
        "/slabs/0/openings/0/outline",
        "50.00 mm from the slab outline's z",
    ),
    (
        "m17-origin-z-0.5",
        "spec-lot0-grid",
        _set(("grids", 0, "origin", "z"), 0.5),
        "/grids/0/origin/z",
        "0.1 mm",
    ),
    (
        "m18-step-5e-6",
        "spec-lot0-grid",
        _px("x_lines", 1, 6000.000005),
        "/grids/0/x_lines/1/position",
        "0.01 mm",
    ),
    (
        "m25-plane-1.5-mm-off",
        "spec-poly-members",
        _poly((0, 0, Z), (5000, 0, Z), (5000, 5000, Z), (0, 5000, Z + 1.5)),
        "/poly_members/0/points",
        "1.5 mm off the plane",
    ),
]


@pytest.mark.parametrize(
    ("case", "name", "mutate", "path", "fragment"), P15_5C_REJECTS, ids=[c[0] for c in P15_5C_REJECTS]
)
def test_review_fixes_rejects(case, name, mutate, path, fragment, example):
    spec = example(name)
    mutate(spec)
    problems = validate("spec", spec)  # must not raise
    assert any(p.path.startswith(path) and fragment in p.message for p in problems), (case, problems)


P15_5C_ACCEPTS = [
    # m-1: an opening inside one arm of a concave slab stays valid
    ("m-opening-in-u-arm", SW, _both(_slab_pts(*U_SLAB), _slab_open_pts(*ARM_OPENING))),
    # m-2: a hairpin 100 mm wide is not a fold-back
    ("g-hairpin-100-mm", "spec-poly-members", _poly(*HAIRPIN)),
    (
        "g-fold-back-5-mm-lateral-is-a-turn",
        "spec-poly-members",
        _poly((0, 0, Z), (0, 5000, Z), (10000, 5000, Z), (5000, 5005, Z)),
    ),
    # m-3 M1: the plane comes from the largest triangle, not from points 0, 1 and 2
    ("m1-plane-from-largest-triangle", "spec-poly-members", _poly(*TILTED)),
]


@pytest.mark.parametrize(("case", "name", "mutate"), P15_5C_ACCEPTS, ids=[c[0] for c in P15_5C_ACCEPTS])
def test_review_fixes_accepts(case, name, mutate, example):
    spec = example(name)
    mutate(spec)
    assert _paths(spec) == []


def _square(side, z=0.0):
    corners = [(0.0, 0.0), (side, 0.0), (side, side), (0.0, side)]
    return [{"x": x, "y": y, "z": z, "chamfer": "none"} for x, y in corners]


def test_overflow_helpers_fail_closed():
    """Each guard in isolation: the rule tests above are refused by several guards at once."""
    nan = math.nan
    assert _exceeds(nan, 1.0)
    for distance in (nan, math.inf):
        problems: list[Problem] = []
        _close(problems, "/p", distance, "message")
        assert problems == [Problem("/p", _CANNOT_EVALUATE)]
    # squares overflow: a = 1e308 and e = 1e308 are finite, a * e is not
    assert math.isnan(_segment_distance((0, 0, 0), (1e154, 0, 0), (0, 1, 0), (0, 1, 1e154)))
    assert math.isnan(_segment_distance((0, 0, 0), (1e200, 0, 0), (0, 1, 0), (0, 1, 0)))
    assert math.isnan(_distance_to_line((0, 1, 0), (0, 0, 0), (1e200, 0, 0)))  # length is inf, 1 / inf is 0
    assert _check_plane("/m", [(0, 0, 0), (1e200, 0, 0), (0, 1e200, 0), (1e200, 1e200, 1e200)]) == [
        Problem("/m", _CANNOT_EVALUATE)
    ]
    # exactly collinear but too large to see it: a zero normal, not a ZeroDivisionError
    assert _check_plane("/m", [(0, 0, 0), (1e160, 0, 0), (2e160, 0, 0)]) == [Problem("/m", _CANNOT_EVALUATE)]
    huge_uv = [(0.0, 0.0), (1e200, 1e200), (1e200, 0.0), (0.0, 1e200)]
    outline = _square(1000.0)
    xyz = [(p["x"], p["y"], p["z"]) for p in outline]
    assert _check_outline("/o", outline, huge_uv, xyz) == [Problem("/o", _CANNOT_EVALUATE)]
    assert _crosses((0, 0), (1e200, 1e200), (0, 1e200), (1e200, 0)) is None
    assert _check_overlaps("/p", [_square(1e200), _square(1e200)], None) == [
        Problem("/p/1", _CANNOT_EVALUATE)
    ]


# --- project-state --------------------------------------------------------------


def test_gate_decision_needs_engineer(example):
    state = example("project-state")
    del state["gates"]["g1_plan"]["decided_by"]
    assert validate("project-state", state)


# --- read-log -------------------------------------------------------------------


def test_failed_attempt_needs_error(example):
    log = example("read-log")
    del log["files"][0]["attempts"][0]["error"]
    assert validate("read-log", log)


# --- tool wave 2 seam: additive fields (all optional, $id stays 0.1) ------------------------------


@pytest.mark.parametrize("name", ["dimensions", "supplements"])
def test_new_schema_examples_are_valid(name, example):
    assert validate(name, example(name)) == []


def test_code_enums_match_their_schema_copies():
    """ROLES and CLOSURE_REASONS are repeated in schemas; a change to one side must reach the other."""
    from tekla_harness.questions import CLOSURE_REASONS, ROLES

    def enum_at(name: str, *path: str) -> set[str]:
        node: dict = validator(name).schema  # type: ignore[assignment]
        for key in path:
            node = node[key]
        return set(node["enum"])

    assert enum_at("answers", "$defs", "answer", "properties", "answered_by_role") == set(ROLES)
    intake = ("$defs", "question", "properties", "closed_by", "properties", "reason")
    status = ("properties", "gate1", "properties", "closed", "items", "properties", "reason")
    assert enum_at("intake", *intake) == set(CLOSURE_REASONS)
    assert enum_at("status", *status) == set(CLOSURE_REASONS)


def test_new_schemas_keep_id_0_1():
    for name in ("dimensions", "supplements"):
        schema: dict = validator(name).schema  # type: ignore[assignment]
        assert schema["$id"] == f"urn:tekla-harness:schema:{name}:0.1"


def test_supplement_withdrawn_needs_a_reason_and_file_needs_its_sha(example):
    doc = example("supplements")
    del doc["supplements"][1]["withdrawn_reason"]
    assert validate("supplements", doc)
    doc = example("supplements")
    doc["supplements"][0]["file_sha256"] = None
    assert validate("supplements", doc)
    doc = example("supplements")
    doc["supplements"][0]["target_producer"] = "reader"
    assert validate("supplements", doc)


def test_dimensions_are_never_converted(example):
    doc = example("dimensions")
    doc["units"]["converted"] = True
    assert validate("dimensions", doc)


def test_text_index_style_family_source_and_ascii_flag(example):
    doc = example("text-index")
    decode = doc["entries"][0]["decode"]
    decode["source"] = "style_family"
    decode["run_details"][0]["font_source"] = "style_family"
    doc["entries"][0]["flags"] = ["legacy_ascii_suspect"]
    assert validate("text-index", doc) == []
    decode["source"] = "family_guess"
    assert validate("text-index", doc)


def test_probe_hint_matched_on_family(example):
    doc = example("dxf-probe")
    doc["text_encoding_hints"][0]["matched"] = [{"field": "family", "value": ".VnAvantH"}]
    assert validate("dxf-probe", doc) == []
    doc["text_encoding_hints"][0]["matched"] = [{"field": "bigfont", "value": "x"}]
    assert validate("dxf-probe", doc)


def test_sheet_text_unassigned_sheet_and_ascii_reason(example):
    doc = example("sheet-text")
    doc["sheet"] = {
        "sheet_id": "unassigned",
        "space": "model",
        "layout": None,
        "bbox": None,
        "sheet_number": None,
        "duplicate_of": None,
    }
    doc["query"]["unassigned"] = True
    doc["entries"][0]["meaning"] = "blocked"
    doc["entries"][0]["blocked_reason"] = "legacy_ascii_suspect"
    doc["legacy_font_gate"]["by_reason"] = {"legacy_ascii_suspect": 1}
    assert validate("sheet-text", doc) == []
    doc["sheet"]["sheet_id"] = "model#01"  # a real sheet still needs its layout and frame
    assert validate("sheet-text", doc)


def test_unassigned_clusters_by_side_rejects_a_misspelled_side(example):
    doc = example("unassigned-clusters")
    assert validate("sheet-text", doc) == []
    doc["totals"]["by_side"]["belw"] = 1
    assert validate("sheet-text", doc)


def test_sheet_list_and_find_text_new_counts(example):
    listing = example("sheet-list")
    listing["files"][0]["blocked_text_count"] = 3
    assert validate("sheet-text", listing) == []
    found = example("find-text")
    found["query"]["unassigned"] = True
    found["counts"]["unassigned_entries_searched"] = 7
    found["hits"][0]["sheet_id"] = "unassigned"
    assert validate("sheet-text", found) == []


def test_levels_blocked_candidates(example):
    doc = example("levels")
    doc["blocked_candidates"] = [
        {"entry_id": "T000012", "line": 0, "value_text": "+3.850", "reason": "encoding_unknown"}
    ]
    doc["summary"]["blocked_candidates"] = 1
    assert validate("levels", doc) == []
    doc["blocked_candidates"][0]["reason"] = "nope"
    assert validate("levels", doc)


def test_marks_blocked_columns_size_compared_and_by_sheet(example):
    doc = example("marks")
    doc["tables"][0]["blocked_columns"] = [{"column": 2, "entry_id": "T000061", "reason": "encoding_unknown"}]
    match = doc["matching"][0]["matched"][0]
    match["size_compared"] = False
    match["size_not_compared_reason"] = "plan_size_missing"
    doc["summary"]["by_sheet"] = [
        {"file": "plans/set.dxf", "sheet": "model#01", "plan_marks": 3, "tables": 1}
    ]
    doc["summary"]["size_comparisons"] = {"compared": 1, "not_compared": 1}
    assert validate("marks", doc) == []
    match["size_compared"] = True  # a compared size has no reason for not comparing
    assert validate("marks", doc)


def test_callouts_unparsed_by_reason_and_ascii_reason(example):
    doc = example("callouts")
    doc["summary"]["unparsed_by_reason"] = {"no verified pattern": 2}
    doc["blocked_entries"][0]["reason"] = "legacy_ascii_suspect"
    assert validate("callouts", doc) == []


def test_intake_question_closed_by_and_ref_families(example):
    doc = example("intake-questions")
    q = doc["questions"][0]
    q["closed_by"] = {"question_id": "Q-002", "reason": "units_answered"}
    q["refs"][0]["families"] = ["F001", "F002"]
    assert validate("intake", doc) == []
    q["closed_by"] = {"question_id": None, "reason": "rejected_systems_only"}
    assert validate("intake", doc) == []
    q["closed_by"] = {"question_id": None, "reason": "because"}
    assert validate("intake", doc)


def test_answers_role_and_file_set_values(example):
    doc = example("answers")
    answer = doc["answers"][0]
    answer["answered_by_role"] = "simulated"
    assert validate("answers", doc) == []
    answer["answered_by_role"] = "agent"
    assert validate("answers", doc)
    answer["answered_by_role"] = "engineer"
    answer.update(code="file_set_relation", file=None, values={"set1": ["a.dwg", "b.dwg"], "set2": ["c.dwg"]})
    assert validate("answers", doc) == []
    answer["values"] = {"group1": ["a.dwg"]}
    assert validate("answers", doc)
    answer["values"] = {"set1": []}
    assert validate("answers", doc)


def test_reader_findings_decoded_by_and_list_summary(example):
    doc = example("reader-findings")
    doc["findings"][0]["decoded_by"] = [
        {
            "source": "knowledge_table",
            "knowledge_pattern": "vntimeh.shx",
            "row_status": "approved",
            "decided_on": "2026-11-07",
            "entries": ["T000001"],
        }
    ]
    doc["summary"] = {"by_class": {"general_notes": 1}}
    assert validate("reader-findings", doc) == []
    doc["findings"][0]["decoded_by"][0]["row_status"] = "maybe"
    assert validate("reader-findings", doc)


def test_grid_system_conflict_question_id_and_file_sets(example):
    doc = example("grid-system")
    doc["conflicts"][0]["question_id"] = "Q-023"
    doc["file_sets"] = {
        "status": "answered",
        "sets": [["a.dwg", "b.dwg"], ["c.dwg"]],
        "question_id": "Q-030",
    }
    assert validate("grid-system", doc) == []
    doc["file_sets"] = {"status": "pending", "sets": None, "question_id": "Q-030"}
    assert validate("grid-system", doc) == []


def test_status_gate1_closed_and_non_engineer_answers(example):
    doc = example("status")
    doc["gate1"]["closed"] = [{"id": "Q-005", "reason": "units_answered"}]
    doc["gate1"]["non_engineer_answers"] = [
        {"question_id": "Q-001", "code": "units_confirm_all", "file": "S-101.dwg", "role": "simulated"}
    ]
    assert validate("status", doc) == []
    doc["gate1"]["closed"] = [{"id": "Q-005", "reason": "answered"}]
    assert validate("status", doc)


# --- tool wave 3 seam: new codes and fields (all optional, $id stays 0.1) -------------------------


GRID_ANSWER_VALUES = {
    "dir1_labels": ["1", "2", "3"],
    "dir1_spacings": [3130, 3540.5],
    "dir2_labels": ["A", "B"],
    "dir2_spacings": [4250],
}


def test_answers_grid_system_missing_values(example):
    doc = example("answers")
    answer = doc["answers"][0]
    answer.update(code="grid_system_missing", file="S-101.dwg", values=dict(GRID_ANSWER_VALUES))
    assert validate("answers", doc) == []
    answer["values"]["sheet"] = "model#05"
    assert validate("answers", doc) == []
    answer["values"] = {}  # words only: recorded, builds nothing
    assert validate("answers", doc) == []
    for bad in (
        {k: v for k, v in GRID_ANSWER_VALUES.items() if k != "dir2_spacings"},
        {**GRID_ANSWER_VALUES, "dir1_spacings": [3130, 0]},
        {**GRID_ANSWER_VALUES, "dir1_labels": "1,2,3"},
        {**GRID_ANSWER_VALUES, "dir1_labels": ["1"], "dir1_spacings": []},
        {**GRID_ANSWER_VALUES, "dir1_labels": ["1", "1", "2"]},
        {**GRID_ANSWER_VALUES, "dir3_labels": ["X", "Y"]},
        {**GRID_ANSWER_VALUES, "sheet": ""},
    ):
        answer["values"] = bad
        assert validate("answers", doc), bad
    answer.update(code="grid_answer_contradicts_drawing", values={"unit": "mm"})
    assert validate("answers", doc)  # takes no value
    answer["values"] = {}
    assert validate("answers", doc) == []


def test_registry_obsolete_reason_only_on_obsolete_entries(example):
    doc = example("question-registry")
    entries = list(doc["questions"].values())
    obsolete = next(e for e in entries if e["status"] == "obsolete")
    live = next(e for e in entries if e["status"] != "obsolete")
    obsolete["obsolete_reason"] = "the latest intake run no longer raises it"
    assert validate("question-registry", doc) == []
    live["obsolete_reason"] = "the input file changed since the question was raised"
    assert validate("question-registry", doc)
    del live["obsolete_reason"]
    obsolete["obsolete_reason"] = ""
    assert validate("question-registry", doc)


def test_grid_system_answer_example_and_detected_guards(example):
    doc = example("grid-system-answer")
    assert validate("grid-system", doc) == []
    answered = next(s for s in doc["systems"] if s.get("source") == "engineer_answer")
    assert answered["evidence"]["contributors"] == []
    assert answered["directions"][0]["representative"] is None
    codes = {q["code"] for q in doc["questions"]}
    assert {"grid_system_missing", "grid_answer_contradicts_drawing"} <= codes

    no_answer = copy.deepcopy(doc)
    del next(s for s in no_answer["systems"] if s.get("source") == "engineer_answer")["source_answer"]
    assert validate("grid-system", no_answer)
    detected_with_answer = copy.deepcopy(doc)
    detected = next(s for s in detected_with_answer["systems"] if s.get("source") != "engineer_answer")
    detected["source_answer"] = answered["source_answer"]
    assert validate("grid-system", detected_with_answer)
    for mutate in (
        lambda s: s["evidence"].update(contributors=[]),
        lambda s: s["evidence"].update(views=0),
        lambda s: s["directions"][0].update(representative=None),
        lambda s: s["directions"][0].update(families=0),
    ):
        bad = copy.deepcopy(doc)
        mutate(next(s for s in bad["systems"] if s.get("source") != "engineer_answer"))
        assert validate("grid-system", bad)
    bad = copy.deepcopy(doc)
    answered_bad = next(s for s in bad["systems"] if s.get("source") == "engineer_answer")
    answered_bad["directions"][0]["provenance"]["method"] = "derived"
    assert validate("grid-system", bad)


def test_grid_system_proposed_simulated_statuses(example):
    doc = example("grid-system")
    system = doc["systems"][0]
    system["units"] = {
        "declared": "mm",
        "answered": "mm",
        "status": "proposed_simulated",
        "reason": "units answered by a non-engineer role",
    }
    system["axis_assignment"] = {"status": "proposed_simulated", "reason": "simulated answer Q-024"}
    doc["conflicts"][0]["proposed_closed_by"] = "separate"
    assert validate("grid-system", doc) == []
    doc["conflicts"][0]["closed_by"] = "proposed_simulated"  # never a closure reason
    assert validate("grid-system", doc)
    doc["conflicts"][0]["closed_by"] = None
    doc["conflicts"][0]["proposed_closed_by"] = "answered"
    assert validate("grid-system", doc)


def test_marks_mark_sets_and_compared_with(example):
    doc = example("marks")
    doc["summary"]["mark_sets"] = [
        {
            "file": "plans/set.dxf",
            "family": "D",
            "members": ["D1", "D2", "D9"],
            "complete": True,
            "source": ["schedule", "plan_marks"],
        },
        {
            "file": "plans/set.dxf",
            "family": "B",
            "members": ["B7"],
            "complete": False,
            "source": ["plan_marks"],
        },
    ]
    file_match = doc["matching"][0]
    file_match["detail_headings"] = 1
    file_match["matched"][0]["compared_with"] = "schedule"
    heading = {"entry_id": "T000070", "sheet": "model#02", "text": "DẦM D2 (SL= 02)"}
    file_match["matched"][2].update(compared_with="detail_heading", schedule=[], detail_headings=[heading])
    file_match["plan_only"][0]["compared_with"] = "none"
    file_match["schedule_only"][0]["compared_with"] = "schedule"
    assert validate("marks", doc) == []

    for path, value in (
        (("summary", "mark_sets", 0, "complete"), "yes"),
        (("summary", "mark_sets", 0, "source"), []),
        (("summary", "mark_sets", 0, "source"), ["guess"]),
        (("summary", "mark_sets", 0, "members"), []),
        (("matching", 0, "plan_only", 0, "compared_with"), "both"),
        (("matching", 0, "matched", 0, "compared_with"), "none"),
        (("matching", 0, "matched", 2, "detail_headings"), []),
    ):
        bad = copy.deepcopy(doc)
        node = bad
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value
        assert validate("marks", bad), path
    bad = copy.deepcopy(doc)
    bad["matching"][0]["matched"][0]["schedule"] = []  # a schedule match keeps its schedule row
    assert validate("marks", bad)


def test_callouts_unparsed_code_rejected_and_unparsed_question(example):
    doc = example("callouts")
    unparsed = next(c for c in doc["candidates"] if c["parsed"] is None)
    parsed = next(c for c in doc["candidates"] if c["parsed"] is not None)
    unparsed["unparsed_code"] = "symbol_glyph_unverified"
    doc["rejected"] = [
        {
            "file": unparsed["file"],
            "sheet": "model#01",
            "entry_id": "T000099",
            "display_text": "KC-03",
            "reason_code": "claimed_by_title_block",
            "reason": "the text is the sheet number of the title block",
        }
    ]
    doc["summary"]["unparsed_by_code"] = {"symbol_glyph_unverified": 1}
    doc["summary"]["rejected"] = 1
    doc["summary"]["rejected_by_reason"] = {"claimed_by_title_block": 1}
    doc["question_counts"]["callout_unparsed"] = 2
    assert validate("callouts", doc) == []

    bad = copy.deepcopy(doc)
    next(c for c in bad["candidates"] if c["id"] == parsed["id"])["unparsed_code"] = "notation_unverified"
    assert validate("callouts", bad)  # a parsed candidate has no unparsed code
    bad = copy.deepcopy(doc)
    next(c for c in bad["candidates"] if c["id"] == unparsed["id"])["unparsed_code"] = "decoded_u_grave"
    assert validate("callouts", bad)
    bad = copy.deepcopy(doc)
    del bad["rejected"][0]["reason"]
    assert validate("callouts", bad)  # nothing is rejected without a reason


def test_sheet_text_region_rows(example):
    doc = example("sheet-region")
    assert validate("sheet-text", doc) == []
    cells = [c for r in doc["rows"] for c in r["cells"]]
    assert any(c["meaning"] == "blocked" for c in cells)
    bad = copy.deepcopy(doc)
    del bad["rows"]
    assert validate("sheet-text", bad)  # a region query always returns its rows
    bad = copy.deepcopy(doc)
    bad["rows"][0]["cells"][0]["entry_ids"] = []
    assert validate("sheet-text", bad)
    bad = copy.deepcopy(doc)
    bad["query"]["region"] = [0, 0, 1]
    assert validate("sheet-text", bad)
    plain = example("sheet-text")
    plain["rows"] = doc["rows"]
    assert validate("sheet-text", plain)  # rows only answer a region query


def test_find_text_blocked_in_scope(example):
    found = example("find-text")
    found["counts"]["blocked_in_scope"] = 3
    del found["counts"]["blocked_entries_not_searchable"]
    assert validate("sheet-text", found) == []
    found["counts"]["blocked_in_scope"] = -1
    assert validate("sheet-text", found)
    del found["counts"]["blocked_in_scope"]  # one of the two blocked counts is always there
    assert validate("sheet-text", found)


def test_reader_questions_schema(example):
    doc = example("reader-questions")
    assert validate("reader-questions", doc) == []
    assert validate("intake", doc) == []  # the reader document stays a questions document
    amended = next(q for q in doc["questions"] if q.get("amendments"))
    assert amended["places"]
    for mutate in (
        lambda q: q["refs"].append(dict(q["refs"][0])),
        lambda q: q["amendments"].append({"at": 9}),
        lambda q: q["amendments"].append({"at": 0, "text": "x"}),
        lambda q: q.update(places=[]),
        lambda q: q.update(count=2),
    ):
        bad = copy.deepcopy(doc)
        mutate(next(q for q in bad["questions"] if q["id"] == amended["id"]))
        assert validate("reader-questions", bad)
    bad = copy.deepcopy(doc)
    bad["kind"] = "inventory"
    assert validate("reader-questions", bad)


def test_status_gate1_closed_is_required_and_may_be_empty(example):
    # W5: harness status always writes gate1.closed (package C), so the schema requires it
    doc = example("status")
    doc["gate1"]["closed"] = []
    assert validate("status", doc) == []
    del doc["gate1"]["closed"]
    assert validate("status", doc)


def test_status_parts_project_reasons_is_an_optional_list_of_strings(example):
    # E5b review 1, D4: additive, next to `parts`; `blocked_by_project` stays a boolean
    doc = example("status")
    assert doc["parts"] and doc["parts_project_reasons"] and validate("status", doc) == []
    assert all(isinstance(r, str) and r for r in doc["parts_project_reasons"])
    for bad in ("one reason", [1], [""], None):
        assert validate("status", {**doc, "parts_project_reasons": bad}), bad
    assert validate("status", {**doc, "parts_project_reasons": []}) == []
    del doc["parts_project_reasons"]
    assert validate("status", doc) == []
    doc["parts"][0]["blocked_by_project"] = "units"
    assert validate("status", doc)


def test_wave3_schemas_keep_id_0_1():
    for name in ("reader-questions", "grid-system", "marks", "callouts", "sheet-text", "answers"):
        schema: dict = validator(name).schema  # type: ignore[assignment]
        assert schema["$id"] == f"urn:tekla-harness:schema:{name}:0.1"


@pytest.mark.parametrize(
    ("name", "schema"),
    [
        ("text-index", "text-index"),
        ("dxf-probe", "dxf-probe"),
        ("sheet-text", "sheet-text"),
        ("sheet-list", "sheet-text"),
        ("find-text", "sheet-text"),
        ("unassigned-clusters", "sheet-text"),
        ("levels", "levels"),
        ("marks", "marks"),
        ("callouts", "callouts"),
        ("intake-questions", "intake"),
        ("answers", "answers"),
        ("reader-findings", "reader-findings"),
        ("grid-system", "grid-system"),
        ("status", "status"),
    ],
)
def test_current_outputs_still_validate_without_the_new_fields(example, name, schema):
    assert validate(schema, example(name)) == []


@pytest.mark.parametrize("lot", [1.0, 2147483648, 9007199254740992])
def test_lot_must_be_int32(example, lot):
    spec = example("spec")
    spec["lot"] = lot
    assert any("lot" in p.path for p in validate("spec", spec))


def test_lot_int32_maximum_ok(example):
    spec = example("spec")
    spec["lot"] = 2147483647
    assert validate("spec", spec) == []


# --- ECMA-262 pattern semantics (ADR-0010 Amendment 1, review fix M1) --------------------


@pytest.mark.parametrize(
    ("pattern", "text", "ok"),
    [
        ("^[A-Z]+$", "AB", True),
        ("^[A-Z]+$", "AB\n", False),  # Python `$` matches before a final newline; ECMA's does not
        ("^(?!\\.{1,2}$)[^/\\\\]+$", "..\n", True),  # `[^/\\]` accepts \n; lookahead `$` is end of input
        ("^(?!\\.{1,2}$)[^/\\\\]+$", "..", False),
        ("^a.c$", "a\rc", False),  # ECMA `.` excludes every line terminator
        ("^a.c$", "a\u2028c", False),
        ("^a.c$", "abc", True),
        ("^[$]$", "$", True),  # `$` inside a class stays literal
        ("^\\$$", "$", True),  # escaped `$` stays literal
        ("^[.]$", "x", False),  # `.` inside a class stays literal
        ("\\S", " x ", True),
    ],
)
def test_pattern_uses_ecma_semantics(pattern, text, ok):
    from tekla_harness.schemas import ecma_regex

    assert bool(ecma_regex(pattern).search(text)) is ok


def test_spec_id_with_trailing_newline_rejected(example):
    spec = example("spec")
    spec["members"][1]["spec_id"] = spec["members"][0]["spec_id"] + "\n"
    assert any(p.path == "/members/1/spec_id" for p in validate("spec", spec))


def test_every_schema_pattern_translates():
    import json as _json

    from tekla_harness.schemas import ecma_regex, schema_dir

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "pattern" and isinstance(value, str):
                    yield value
                yield from walk(value)
        elif isinstance(node, list):
            for item in node:
                yield from walk(item)

    docs = [_json.loads(f.read_text("utf-8")) for f in schema_dir().glob("*.schema.json")]
    patterns = {p for doc in docs for p in walk(doc)}
    assert patterns
    for p in patterns:
        ecma_regex(p)


# --- run journal (ADR-0012) ---------------------------------------------------------------


def test_run_journal_example_valid(example):
    assert validate("run-journal", example("run-journal")) == []


def test_run_journal_inserting_entry_has_no_guid(example):
    journal = example("run-journal")
    journal["invocations"][0]["objects"][0]["state"] = "inserting"
    assert validate("run-journal", journal)
    journal["invocations"][0]["objects"][0]["guid"] = None
    assert validate("run-journal", journal) == []


def test_run_journal_inserted_entry_needs_guid(example):
    journal = example("run-journal")
    journal["invocations"][0]["objects"][1]["guid"] = None
    assert validate("run-journal", journal)


@pytest.mark.parametrize("run_id", ["r1", "-R1", "R 1", "R1\n", "R" * 33, ""])
def test_run_journal_rejects_bad_run_id(example, run_id):
    journal = example("run-journal")
    journal["run_id"] = run_id
    assert validate("run-journal", journal)


def test_run_journal_rejects_uppercase_guid(example):
    journal = example("run-journal")
    journal["invocations"][0]["objects"][0]["guid"] = "3F2504E0-4F89-11D3-9A0C-0305E82C3301"
    assert validate("run-journal", journal)


def test_run_journal_golden_matches_schema_and_python_bytes():
    """The C# writer's output (tests/fixtures/run-journal/golden.json, checked byte for byte in
    xunit) is a valid journal and equals Python's json.dumps of the same content."""
    import json as _json

    from conftest import EXAMPLES, REPO

    golden = (REPO / "tests" / "fixtures" / "run-journal" / "golden.json").read_bytes()
    data = _json.loads(golden)
    assert validate("run-journal", data) == []
    assert data == _json.loads((EXAMPLES / "run-journal.example.json").read_text("utf-8"))
    assert golden == (_json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


PART_IDS_OK = ["a", "blk1-piles", "A_b-9", "x" * 64]
PART_IDS_BAD = ["", "-x", "_x", "a b", "a/b", "é", "x" * 65, 3, None]


def test_reader_findings_part_is_optional_and_checked(example):
    doc = example("reader-findings")
    assert any("part" in f for f in doc["findings"])  # the example shows the field
    assert validate("reader-findings", doc) == []
    for ok in PART_IDS_OK:
        good = copy.deepcopy(doc)
        good["findings"][0]["part"] = ok
        assert validate("reader-findings", good) == [], ok
    untagged = copy.deepcopy(doc)
    for f in untagged["findings"]:
        f.pop("part", None)
    assert validate("reader-findings", untagged) == []  # a finding recorded before a manifest existed
    for bad_id in PART_IDS_BAD:
        bad = copy.deepcopy(doc)
        bad["findings"][0]["part"] = bad_id
        assert validate("reader-findings", bad), bad_id


def test_reader_questions_parts_is_optional_and_checked(example):
    doc = example("reader-questions")
    assert any("parts" in q for q in doc["questions"])  # the example shows the field
    assert validate("reader-questions", doc) == []
    assert validate("intake", doc) == []
    for ok in PART_IDS_OK:
        good = copy.deepcopy(doc)
        good["questions"][0]["parts"] = [ok, "blk2-beams"]
        assert validate("reader-questions", good) == [], ok
    untagged = copy.deepcopy(doc)
    for q in untagged["questions"]:
        q.pop("parts", None)
    assert validate("reader-questions", untagged) == []
    for bad_parts in ([], ["a", "a"], "blk1-piles", *([bad] for bad in PART_IDS_BAD)):
        bad = copy.deepcopy(doc)
        bad["questions"][0]["parts"] = bad_parts
        assert validate("reader-questions", bad), bad_parts
