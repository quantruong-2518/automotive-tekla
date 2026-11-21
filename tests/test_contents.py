"""contents: `harness contents`, what each member outline of a plan sheet holds (symbols, mark, axes).

The world is `_dxf_fixtures.build_set` (sheet 1 = model#01, sheet 2 = model#02 from x 90000) plus, invented
here, pile caps (closed LWPOLYLINEs on CAP), piles (circles on PILE), mark texts, a frame-sized outline and a
mirrored block. A hand-written grids document gives sheet 1 two families (a horizontal and a vertical one).

Sheet 1 (all values in drawing units):
  A  1700x1700 at (10000, 20000): two piles, one drawn as two concentric circles; marks DC-1 (650 away,
     nearest), DC-2 (1750 away), plus texts that do not match
  B  800x1700 rotated 30 deg at (20000, 20000): a pile at its centre, one in its bbox but outside the polygon
  C  1700x1700 at (30000, 20000): a pile exactly on its boundary; mark DC-3 3150 away (beyond the 3000 radius)
  D, E  1700x1700 at (50000, 30000) and (51500, 30000), overlapping: a pile in both, one in D only; D has a
     mark in a legacy font next to it
  F  a 30000x20000 outline (a frame) on the cap layer
  H, I  1000x1000 at (10000, 5000) and (14000, 5000): DC-8 at x 11500 is nearer to H (1000 against
     2000), DC-9 at x 12000 is 1500 from both
  G  800x1800 from a mirrored INSERT at (70000, 10000) holding one pile in world coordinates

Marks are placed by their MIDDLE (`text(value, x, y)` puts the middle of the text at x, y): the tool
measures a mark from the middle of its text, estimated as 0.7 x height per character.

Probes of the T22 review (own layers and `P..-n` mark names, so the world above is unchanged):
A concentric circles across a rounding boundary, B round cap (bulges), T 70-gon, N cap with a column stub,
M long mark under the next cap, R near tie, K rotated cap, Z frozen pile block, D donut on the outline layer,
X texts (spaces, off layer, partial), W one mark on two cap types, U sizes within the tolerance,
GR three grid groups, L layout.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import pytest
from ezdxf.enums import MTextEntityAlignment, TextEntityAlignment
from ezdxf.filemanagement import readfile

from _callout_fixtures import PROPOSED_FONT_TABLE, REL, write_structure
from _dxf_fixtures import build_set
from tekla_harness.cli import main
from tekla_harness.contents import _attach_dims, contents
from tekla_harness.dimensions import _TextLinks
from tekla_harness.geometry import DimRead, _Item, read_geometry
from tekla_harness.intake import run_intake
from tekla_harness.schemas import validate
from tekla_harness.sheet_text import ReaderError

PILE = "S-PILE"
CAP = "S-CAP"
BLOCKED_TEXT = "DC-7 tªn"


def rect(cx: float, cy: float, long: float, short: float, angle: float = 0.0) -> list[tuple[float, float]]:
    a = math.radians(angle)
    ux, uy = math.cos(a), math.sin(a)
    vx, vy = -uy, ux
    return [
        (cx + s * long / 2 * ux + t * short / 2 * vx, cy + s * long / 2 * uy + t * short / 2 * vy)
        for s, t in ((-1, -1), (1, -1), (1, 1), (-1, 1))
    ]


def mid_insert(value: str, mx: float, my: float, height: float = 350) -> tuple[float, float]:
    """Insertion point of a left-aligned TEXT whose estimated middle (0.7 x height each) is (mx, my)."""
    return mx - 0.35 * height * len(value), my - height / 2


def grids_doc() -> dict[str, Any]:
    def axis(label: str | None, start: list[float], end: list[float]) -> dict[str, Any]:
        return {"axis_id": "G0001", "label": None if label is None else {"value": label},
                "line": {"start": start, "end": end}}  # fmt: skip

    def family(fid: str, direction: list[float], normal: list[float], axes: list[Any]) -> dict[str, Any]:
        return {
            "family_id": fid,
            "direction": direction,
            "normal": normal,
            "axes": axes,
            "unlabelled_lines": [],
        }

    return {
        "schema_version": "0.1",
        "file": REL,
        "groups": [
            {
                "group_id": "V001",
                "sheet": "model#01",
                "space": "model",
                "bbox": [-1000.0, -1000.0, 75000.0, 60000.0],
                "families": [
                    {
                        "family_id": "F001",
                        "direction": [1.0, 0.0],
                        "normal": [0.0, 1.0],
                        "axes": [
                            axis("A", [0, 10000], [80000, 10000]),
                            axis("B", [0, 25000], [80000, 25000]),
                        ],
                        "unlabelled_lines": [],
                    },
                    {
                        "family_id": "F002",
                        "direction": [0.0, 1.0],
                        "normal": [1.0, 0.0],
                        "axes": [axis("1", [5000, 0], [5000, 50000]), axis(None, [12000, 0], [12000, 50000])],
                        "unlabelled_lines": [],
                    },
                ],
            },
            {  # a group of the layout space over the same sheet: never answers for model-space outlines
                "group_id": "V003",
                "sheet": "model#01",
                "space": "Plot",
                "bbox": [-1000.0, -1000.0, 75000.0, 60000.0],
                "families": [family("F013", [1.0, 0.0], [0.0, 1.0], [axis("Z", [0, 0], [80000, 0])])],
            },
            {  # an enlarged detail on the same sheet, with its own axes
                "group_id": "V002",
                "sheet": "model#01",
                "space": "model",
                "bbox": [60000.0, 47000.0, 62000.0, 49000.0],
                "families": [
                    family("F009", [1.0, 0.0], [0.0, 1.0], [axis("X", [60000, 48000], [62000, 48000])]),
                    family("F010", [0.0, 1.0], [1.0, 0.0], [axis(None, [60500, 47000], [60500, 49000])]),
                    family(  # equally far from the centre: the lower position answers
                        "F011",
                        [0.0, 1.0],
                        [1.0, 0.0],
                        [
                            axis("Q", [62000, 47000], [62000, 49000]),
                            axis("P", [60000, 47000], [60000, 49000]),
                        ],
                    ),
                    family(  # 0.3 degrees off its family: start and midpoint are 50 apart
                        "F012", [1.0, 0.0], [0.0, 1.0], [axis("S", [50000, 48000], [69100, 48100])]
                    ),
                ],
            },
        ],
    }


def build_dxf(base: Path) -> Path:
    root = base / "input"
    (root / "plans").mkdir(parents=True)
    doc = readfile(str(build_set(base, "src.dxf")))
    doc.layers.add(PILE)
    doc.layers.add(CAP)
    doc.styles.add("VntimeH", font="vntimeh.shx")
    msp = doc.modelspace()
    cap, pile = {"layer": CAP}, {"layer": PILE}

    def text(value: str, x: float, y: float, style: str = "Standard") -> None:
        msp.add_text(value, height=350, dxfattribs={"insert": mid_insert(value, x, y), "style": style})

    # A
    msp.add_lwpolyline(rect(10000, 20000, 1700, 1700), close=True, dxfattribs=cap)
    msp.add_circle((9500, 19500), 150, dxfattribs=pile)
    msp.add_circle((9500, 19500), 200, dxfattribs=pile)
    msp.add_circle((10500, 20500), 150, dxfattribs=pile)
    text("DC-1", 10000, 21500)
    text("DC-2", 10000, 22600)
    text("NOTE", 10000, 21000)
    text("XDC-5", 11000, 21000)  # contains a mark but is not one
    # B
    msp.add_lwpolyline(rect(20000, 20000, 1700, 800, 30), close=True, dxfattribs=cap)
    msp.add_circle((20000, 20000), 150, dxfattribs=pile)
    msp.add_circle((20900, 19300), 150, dxfattribs=pile)
    # C
    msp.add_lwpolyline(rect(30000, 20000, 1700, 1700), close=True, dxfattribs=cap)
    msp.add_circle((30850, 20000), 150, dxfattribs=pile)
    text("DC-3", 30000, 24000)
    # D, E
    msp.add_lwpolyline(rect(50000, 30000, 1700, 1700), close=True, dxfattribs=cap)
    msp.add_lwpolyline(rect(51500, 30000, 1700, 1700), close=True, dxfattribs=cap)
    msp.add_circle((50750, 30000), 150, dxfattribs=pile)
    msp.add_circle((49500, 30000), 150, dxfattribs=pile)
    text(BLOCKED_TEXT, 50000, 32000, "VntimeH")
    # F
    msp.add_lwpolyline(rect(40000, 45000, 30000, 20000), close=True, dxfattribs=cap)
    # G: a mirrored block, its pile inside its outline only in world coordinates
    blk = doc.blocks.new("MIRROR_CAP")
    blk.add_lwpolyline([(1000, 100), (2800, 100), (2800, 900), (1000, 900)], close=True, dxfattribs=cap)
    blk.add_circle((1900, 500), 150, dxfattribs=pile)
    msp.add_blockref("MIRROR_CAP", (70000, 10000), dxfattribs={"xscale": -1.0})
    # H, I: two caps side by side with a label between them
    msp.add_lwpolyline(rect(10000, 5000, 1000, 1000), close=True, dxfattribs=cap)
    msp.add_lwpolyline(rect(14000, 5000, 1000, 1000), close=True, dxfattribs=cap)
    text("DC-8", 11500, 5000)
    text("DC-9", 12000, 5000)
    # sheet 2: no grid group
    msp.add_lwpolyline(rect(105000, 20000, 1700, 1700), close=True, dxfattribs=cap)
    msp.add_circle((105000, 20000), 150, dxfattribs=pile)

    # --- probes of the T22 review (own layers and mark names) ---
    def probe(layer: str, *points: tuple[float, float, float, float], angle: float = 0.0) -> None:
        for cx, cy, long, short in points:
            msp.add_lwpolyline(rect(cx, cy, long, short, angle), close=True, dxfattribs={"layer": layer})

    def probe_text(value: str, mx: float, my: float, layer: str = "0", height: float = 350) -> None:
        msp.add_text(
            value, height=height, dxfattribs={"insert": mid_insert(value, mx, my, height), "layer": layer}
        )

    for name in (
        "A",
        "B",
        "T",
        "N",
        "M",
        "R",
        "K",
        "Z",
        "D",
        "X",
        "W",
        "U",
        "GR",
        "L",
        "Y",
        "V",
        "E",
        "LP",
        "LQ",
    ):
        doc.layers.add(f"{name}-CAP")
        doc.layers.add(f"{name}-PILE")
    doc.layers.add("N-COL")
    doc.layers.add("OFFTXT").off()
    doc.layers.add("FROZEN").freeze()
    # A: concentric circles whose centres straddle a half-unit rounding boundary
    probe("A-CAP", (5000, 30000, 1700, 1700))
    msp.add_circle((4500.4, 29500), 150, dxfattribs={"layer": "A-PILE"})
    msp.add_circle((4500.6, 29500), 200, dxfattribs={"layer": "A-PILE"})
    # B: a round cap, four arcs (bulge tan(22.5 deg)), r 1000, with a pile at r 750 on a diagonal
    b = math.tan(math.radians(90) / 4)
    msp.add_lwpolyline(
        [(6000, 35000, 0, 0, b), (5000, 36000, 0, 0, b), (4000, 35000, 0, 0, b), (5000, 34000, 0, 0, b)],
        format="xyseb",
        close=True,
        dxfattribs={"layer": "B-CAP"},
    )
    msp.add_circle((5530, 35530), 150, dxfattribs={"layer": "B-PILE"})
    # T: a 70-gon of r 1000 with a pile at r 960 in the sector beyond the 64th vertex
    msp.add_lwpolyline(
        [(15000 + 1000 * math.cos(2 * math.pi * k / 70), 35000 + 1000 * math.sin(2 * math.pi * k / 70))
         for k in range(70)],
        close=True,
        dxfattribs={"layer": "T-CAP"},
    )  # fmt: skip
    msp.add_circle(
        (15000 + 960 * math.cos(math.radians(347)), 35000 + 960 * math.sin(math.radians(347))),
        50,
        dxfattribs={"layer": "T-PILE"},
    )
    # N: a column stub drawn inside its cap; one mark beside the stub, one inside it
    probe("N-CAP", (5000, 42000, 1700, 1700))
    probe("N-COL", (5000, 42000, 400, 400))
    msp.add_circle((5000, 42000), 150, dxfattribs={"layer": "N-PILE"})
    probe_text("PN-1", 5300, 42100)
    probe_text("PN-2", 4950, 41950)
    # M: a long left-aligned mark that starts under the first cap and is written under the second
    probe("M-CAP", (15000, 42000, 1000, 1000), (19000, 42000, 1000, 1000))
    msp.add_text("PM-10", height=1250, dxfattribs={"insert": (16800, 40500)})
    # R: a mark 1.06 nearer to one cap than to the other (more than tol, far less than a quarter)
    probe("R-CAP", (5000, 50000, 1000, 1000), (7000, 50000, 1000, 1000))
    probe_text("PR-11", 6000.75, 51000)
    # K: a cap rotated 30 degrees: piles 50 inside and 50 outside its corner
    probe("K-CAP", (45000, 5000, 1700, 800), angle=30)
    u, v = (
        (math.cos(math.radians(30)), math.sin(math.radians(30))),
        (-math.sin(math.radians(30)), math.cos(math.radians(30))),
    )
    for d in (800, 900):  # 50 inside the corner, 50 outside it
        px = 45000 + d * u[0] + (d - 450) * v[0]
        py = 5000 + d * u[1] + (d - 450) * v[1]
        msp.add_circle((px, py), 50, dxfattribs={"layer": "K-PILE"})
    # 1.8 beyond the middle of a long edge (inside the bbox of the rotated cap, outside the tolerance)
    msp.add_circle((45000 + 401.8 * v[0], 5000 + 401.8 * v[1]), 50, dxfattribs={"layer": "K-PILE"})
    # Z: a superseded pile layout kept as a block on a frozen layer, next to the real pile
    probe("Z-CAP", (55000, 5000, 1700, 1700))
    msp.add_circle((54900, 5000), 100, dxfattribs={"layer": "Z-PILE"})
    old = doc.blocks.new("OLD_PILES")
    old.add_circle((0, 0), 100, dxfattribs={"layer": "Z-PILE"})
    msp.add_blockref("OLD_PILES", (55200, 5100), dxfattribs={"layer": "FROZEN"})
    # D: a round cap drawn as a donut on the outline layer, and a rectangular cap beside it
    msp.add_lwpolyline(
        [(15000 - 800, 25000, 0, 0, 1), (15000 + 800, 25000, 0, 0, 1)],
        format="xyseb",
        close=True,
        dxfattribs={"layer": "D-CAP"},
    )
    probe("D-CAP", (18000, 25000, 1700, 1700))
    msp.add_circle((18000, 25000), 150, dxfattribs={"layer": "D-PILE"})
    # S: marks with spaces, on an off layer, partly matching, and none near
    probe("X-CAP", (25000, 25000, 1700, 1700))
    probe_text(" PS-4 ", 25000, 26200)
    probe_text("PS-5", 25000, 26600, layer="OFFTXT")
    probe_text("PS-6, PS-7", 25000, 27000)
    # W: one mark on two cap types, and two copies of it on one outline
    probe("W-CAP", (70000, 30000, 1000, 1000), (74000, 30000, 1500, 1000))
    probe_text("PW-1", 70000, 31000)
    probe_text("PW-1", 70000, 31400)
    probe_text("PW-1", 74000, 31000)
    probe_text("PD-1", 50750, 30300)  # inside both D and E
    # U: two caps whose sizes differ by less than the tolerance
    probe("U-CAP", (62000, 5000, 1000, 1000), (64000, 5000, 1000.4, 1000))
    # GR: a cap in two grid groups, one in no group
    probe("GR-CAP", (61000, 48000, 800, 800), (78000, 20000, 800, 800), (62000, 48000, 800, 800))
    # the other edges of the detail group V002 (60000-62000 x 47000-49000) and points just outside it
    probe(
        "GR-CAP",
        (60000, 48000, 810, 810),  # on the left edge
        (61000, 47000, 820, 820),  # on the bottom edge
        (61000, 49000, 830, 830),  # on the top edge
        (59000, 48000, 840, 840),  # left of it
        (61000, 46000, 850, 850),  # below it
        (61000, 50000, 860, 860),  # above it
        (63000, 48000, 870, 870),  # right of it
    )
    # Y: a text rotated 90 degrees: its middle is half its width above, half its height left of the insertion
    probe("Y-CAP", (70000, 45000, 1000, 1000))
    msp.add_text("PY-1", height=350, dxfattribs={"insert": (70875, 45200), "rotation": 90})
    # V: two caps 4 apart and a mark 1.6 from one and 2.4 from the other (0.8 apart: within tol of each other)
    probe("V-CAP", (64000, 20000, 1000, 1000), (65004, 20000, 1000, 1000))
    probe_text("PV-1", 64501.6, 20000)
    # E: piles 0.5 outside each side of the cap (count, within tol) and one 1.2 outside (does not)
    probe("E-CAP", (35000, 5000, 1700, 1700))
    for pos in ((35850.5, 5000), (34149.5, 4800), (35100, 5850.5), (35000, 4149.5)):
        msp.add_circle(pos, 100, dxfattribs={"layer": "E-PILE"})
    msp.add_circle((35851.2, 5200), 100, dxfattribs={"layer": "E-PILE"})
    # L: a cap shown through the viewport of the layout, a mark text written in paper space over it
    probe("L-CAP", (300000, 1000, 1700, 1700))
    msp.add_circle((300000, 1000), 150, dxfattribs={"layer": "L-PILE"})
    doc.layouts.get("Plot").add_text("PL-5", height=3.5, dxfattribs={"insert": (300, 330)})
    # LP: two caps drawn in the layout itself and one shown through the viewport, with a pile through it
    probe_plot = doc.layouts.get("Plot")
    for cx in (200, 400):
        probe_plot.add_lwpolyline(rect(cx, 300, 40, 40), close=True, dxfattribs={"layer": "LP-CAP"})
        probe_plot.add_lwpolyline(rect(cx, 300, 40, 40), close=True, dxfattribs={"layer": "LQ-CAP"})
    msp.add_lwpolyline(rect(300000, 1000, 1700, 1700), close=True, dxfattribs={"layer": "LP-CAP"})
    msp.add_lwpolyline(rect(300000, 1000, 1700, 1700), close=True, dxfattribs={"layer": "LQ-CAP"})
    msp.add_circle((300000, 1000), 150, dxfattribs={"layer": "LP-PILE"})
    doc.saveas(root / REL)
    return root


@pytest.fixture(scope="module")
def base(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("contents")
    inp = build_dxf(root)
    work = root / "work"
    run_intake(inp, work, "demo-contents", knowledge=PROPOSED_FONT_TABLE)
    write_structure(inp, work)
    (work / "structure" / f"{REL}.grids.json").write_text(json.dumps(grids_doc()), encoding="utf-8")
    return root


def call(base: Path, **kw: Any) -> dict[str, Any]:
    kw.setdefault("sheet", "model#01")
    kw.setdefault("outline_layers", [CAP])
    kw.setdefault("circle_layers", [PILE])
    return contents(base / "work", REL, input_dir=base / "input", **kw)


@pytest.fixture(scope="module")
def doc(base) -> dict[str, Any]:
    return call(base, marks=r"DC-\d+", max_long=20000)


def outline(d: dict[str, Any], long: float, short: float, near: tuple[float, float]) -> dict[str, Any]:
    found = [
        o
        for o in d["outlines"]
        if o["long"] == long and o["short"] == short and math.dist(o["centre"], near) < 1
    ]
    assert len(found) == 1, (long, short, near, [o["centre"] for o in d["outlines"]])
    return found[0]


def test_document_is_schema_valid(doc):
    assert validate("contents", doc) == []
    assert doc["kind"] == "contents" and doc["file"] == REL and doc["project_id"] == "demo-contents"
    assert doc["units"] == {"declared": "mm", "answered": None, "converted": False}
    assert len(doc["outlines"]) == 8 == doc["outlines_total"]


def test_concentric_circles_are_one_symbol(doc):
    a = outline(doc, 1700, 1700, (10000, 20000))
    assert a["symbols"] == 2
    groups = {tuple(g["diameters"]): g["count"] for g in doc["symbols"]["groups"]}
    assert groups[(300.0, 400.0)] == 1 and groups[(300.0,)] == 7


def test_symbol_inside_outside_and_on_the_boundary(doc):
    assert outline(doc, 1700, 1700, (30000, 20000))["symbols"] == 1  # exactly on its right edge
    assert doc["symbols"] == {**doc["symbols"], "total": 8, "inside": 7, "outside": 1}


def test_rotated_rectangle_is_tested_by_polygon_not_bbox(doc):
    b = outline(doc, 1700, 800, (20000, 20000))
    assert b["symbols"] == 1 and b["angle"] == pytest.approx(30.0)  # (20900, 19300) is in its bbox only


def test_symbol_in_a_mirrored_insert_lands_in_the_right_outline(doc):
    g = outline(doc, 1800, 800, (68100, 10500))
    assert g["symbols"] == 1


def test_symbol_inside_two_outlines_counts_in_both_and_warns(doc):
    d = outline(doc, 1700, 1700, (50000, 30000))
    e = outline(doc, 1700, 1700, (51500, 30000))
    assert (d["symbols"], e["symbols"]) == (2, 1)
    assert doc["symbols"]["total"] == 8  # still one symbol
    assert any("inside more than one outline" in w and "50750" in w for w in doc["warnings"])


def test_max_long_drops_a_frame_and_says_so(base, doc):
    assert not any(o["long"] == 30000 for o in doc["outlines"])
    assert any("1 outline" in w and "--max-long" in w for w in doc["warnings"])
    all_of_them = call(base, marks=None)  # default 20000 also drops it
    assert len(all_of_them["outlines"]) == 8
    big = call(base, max_long=40000)
    assert len(big["outlines"]) == 9 and not any("--max-long" in w for w in big["warnings"])
    assert len(call(base, max_long=30000)["outlines"]) == 9  # a long side equal to the limit stays


def test_each_mark_goes_to_its_one_nearest_outline(doc):
    a = outline(doc, 1700, 1700, (10000, 20000))
    assert [(m["text"], m["distance"]) for m in a["marks"]] == [("DC-1", 650.0), ("DC-2", 1750.0)]
    assert all(m["entry_id"].startswith("T") for m in a["marks"])  # NOTE and XDC-5 do not fully match
    h = outline(doc, 1000, 1000, (10000, 5000))
    i = outline(doc, 1000, 1000, (14000, 5000))
    assert [m["text"] for m in h["marks"]] == ["DC-8"] and i["marks"] == []
    assert "mark" not in a and "mark_candidates" not in a


def test_equally_near_mark_goes_to_neither_outline(doc):
    (amb,) = doc["marks_ambiguous"]
    assert amb["text"] == "DC-9" and amb["position"] == list(mid_insert("DC-9", 12000, 5000))
    h = outline(doc, 1000, 1000, (10000, 5000))
    i = outline(doc, 1000, 1000, (14000, 5000))
    assert sorted(amb["outlines"]) == sorted([h["id"], i["id"]])
    assert not any(m["text"] == "DC-9" for o in doc["outlines"] for m in o["marks"])
    assert not any(m["text"] == "DC-9" for m in doc["marks_unassigned"])


def test_mark_radius_is_respected(base, doc):
    c = outline(doc, 1700, 1700, (30000, 20000))
    assert c["marks"] == []  # DC-3 is 3150 away
    assert [m["text"] for m in doc["marks_unassigned"]] == ["DC-3"]
    wide = call(base, marks=r"DC-\d+", mark_radius=4000)
    assert [m["text"] for m in outline(wide, 1700, 1700, (30000, 20000))["marks"]] == ["DC-3"]
    assert wide["marks_unassigned"] == []


def test_blocked_font_mark_is_not_used(base):
    d = call(base, marks=r"DC-\d+.*")
    dd = outline(d, 1700, 1700, (50000, 30000))
    assert dd["marks"] == []
    assert any("legacy-font" in w and "1" in w for w in d["warnings"])
    assert not any(m["text"] == BLOCKED_TEXT for m in d["marks_unassigned"])


def test_without_marks_there_is_no_mark_work(base):
    d = call(base)
    assert d["query"]["marks"] is None and d["marks_unassigned"] == [] and d["marks_ambiguous"] == []
    assert all(o["marks"] == [] for o in d["outlines"])
    assert all(r["marks_seen"] == {} and r["unmarked"] == r["count"] for r in d["summary"])


def test_axes_label_and_signed_offset(doc):
    a = outline(doc, 1700, 1700, (10000, 20000))
    by_family = {x["family_id"]: x for x in a["axes"]}
    assert by_family["F001"] == {
        "group_id": "V001",
        "family_id": "F001",
        "label": "B",
        "offset": -5000.0,
        "nearest_unlabelled_offset": None,
    }
    # m5: the unlabelled axis (12000) is nearer than axis 1 (5000), but the label comes from the labelled one
    assert by_family["F002"] == {
        "group_id": "V001",
        "family_id": "F002",
        "label": "1",
        "offset": 5000.0,
        "nearest_unlabelled_offset": -2000.0,
    }
    g = outline(doc, 1800, 800, (68100, 10500))
    assert {x["family_id"]: x["offset"] for x in g["axes"]}["F001"] == 500.0  # axis A, 10000 below


def test_no_grid_group_gives_empty_axes_and_a_warning(base):
    d = call(base, sheet="model#02")
    (o,) = d["outlines"]
    assert o["axes"] == [] and o["symbols"] == 1
    assert any("no grid group" in w and "model#02" in w for w in d["warnings"])
    assert not any("lie in no grid group" in w for w in d["warnings"])  # said once, for the sheet


def test_summary_groups_by_layer_size_and_symbols_with_marks_seen(doc):
    rows = doc["summary"]
    key = lambda r: (r["short"], r["long"], r["symbols"])  # noqa: E731
    assert len({key(r) for r in rows}) == len(rows)
    assert sum(r["count"] for r in rows) == 8
    sq = next(r for r in rows if key(r) == (1700.0, 1700.0, 1))  # C and E
    assert sq == {**sq, "count": 2, "marks_seen": {}, "unmarked": 2}
    a = next(r for r in rows if key(r) == (1700.0, 1700.0, 2))  # A holds two marks, D has none
    assert a["count"] == 2 and a["marks_seen"] == {"DC-1": 1, "DC-2": 1} and a["unmarked"] == 1
    small = next(r for r in rows if key(r) == (1000.0, 1000.0, 0))
    assert small["marks_seen"] == {"DC-8": 1} and small["unmarked"] == 1
    assert [r["count"] for r in rows] == sorted((r["count"] for r in rows), reverse=True)


def test_layers_are_case_insensitive(base):
    d = call(base, outline_layers=["s-cap"], circle_layers=["S-pile"])
    assert len(d["outlines"]) == 8 and d["symbols"]["total"] == 8


def test_detail_lists_symbol_centres_and_the_outside_symbols(base):
    d = call(base, detail=True)
    b = outline(d, 1700, 800, (20000, 20000))
    assert b["symbol_centres"] == [[20000.0, 20000.0]]
    assert d["symbols_outside"] == [{"centre": [20900.0, 19300.0], "diameters": [300.0]}]
    assert "symbol_centres" not in call(base)["outlines"][0]
    assert validate("contents", d) == []


def test_outline_list_is_capped_with_a_warning(base):
    d = call(base, max_rows=2)
    assert len(d["outlines"]) == 2 and d["outlines_total"] == 8
    assert any("contents truncated" in w for w in d["warnings"])
    assert sum(r["count"] for r in d["summary"]) == 8


@pytest.mark.parametrize(
    "kw",
    [
        {"marks": "("},
        {"max_long": 0},
        {"mark_radius": -1},
        {"max_rows": 0},
        {"tol": 0},
        {"sheet": "model#99"},
        {"outline_layers": []},
        {"circle_layers": []},
    ],
)
def test_usage_errors_exit_two(base, kw):
    with pytest.raises(ReaderError) as err:
        call(base, **kw)
    assert err.value.exit_code == 2


def test_cli_prints_json_and_elapsed_time(base, capsys):
    argv = ["contents", str(base / "work"), REL, "--sheet", "model#01", "--outline-layer", CAP,
            "--circle-layer", PILE, "--marks", r"DC-\d+", "--input-dir", str(base / "input")]  # fmt: skip
    assert main(argv) == 0
    out, err = capsys.readouterr()
    assert validate("contents", json.loads(out)) == []
    assert "elapsed" in err
    assert main(["contents", str(base / "work"), REL, "--sheet", "nope", "--outline-layer", CAP,
                 "--circle-layer", PILE, "--input-dir", str(base / "input")]) == 2  # fmt: skip


def test_cli_requires_the_layers(base):
    assert main(["contents", str(base / "work"), REL, "--sheet", "model#01"]) == 2


def test_writes_nothing(base):
    before = sorted(p.relative_to(base).as_posix() for p in base.rglob("*"))
    call(base, marks=r"DC-\d+")
    assert sorted(p.relative_to(base).as_posix() for p in base.rglob("*")) == before


# --- the T22 review 1 findings -------------------------------------------------------------------------


def build_units_dxf(base: Path, insunits: int) -> Path:
    root = base / "input"
    (root / "plans").mkdir(parents=True)
    doc = readfile(str(build_set(base, "src.dxf")))
    doc.header["$INSUNITS"] = insunits
    doc.layers.add(PILE)
    doc.layers.add(CAP)
    msp = doc.modelspace()
    msp.add_lwpolyline(rect(40, 40, 15, 2), close=True, dxfattribs={"layer": CAP})
    msp.add_lwpolyline(rect(20, 30, 25, 3), close=True, dxfattribs={"layer": CAP})  # 25 m: a frame
    msp.add_circle((40, 40), 0.15, dxfattribs={"layer": PILE})
    doc.saveas(root / REL)
    return root


def probe_call(base: Path, name: str, **kw: Any) -> dict[str, Any]:
    kw.setdefault("outline_layers", [f"{name}-CAP"])
    kw.setdefault("circle_layers", [f"{name}-PILE"])
    return call(base, **kw)


def axes_of(o: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(x["group_id"], x["family_id"]): x for x in o["axes"]}


def test_c1_axes_come_only_from_the_group_holding_the_outline(base, doc):
    a = outline(doc, 1700, 1700, (10000, 20000))
    assert {x["group_id"] for x in a["axes"]} == {"V001"}
    assert all(x["family_id"] != "F009" for x in a["axes"])  # the detail's axis X is 28000 away
    d = probe_call(base, "GR")
    q = outline(d, 800, 800, (61000, 48000))
    z = outline(d, 800, 800, (78000, 20000))
    assert {x["group_id"] for x in q["axes"]} == {"V001", "V002"}  # in both: one entry per group
    assert any("more than one grid group" in w for w in d["warnings"])
    assert axes_of(q)[("V002", "F009")] == {
        "group_id": "V002",
        "family_id": "F009",
        "label": "X",
        "offset": 0.0,
        "nearest_unlabelled_offset": None,
    }
    assert z["axes"] == []  # outside every group
    edge = outline(
        d, 800, 800, (62000, 48000)
    )  # its centre lies on the bbox edge of V002: not strictly inside
    assert {x["group_id"] for x in edge["axes"]} == {"V001"}
    assert "V003" not in {x["group_id"] for o in d["outlines"] for x in o["axes"]}  # another space
    assert any("1 outline" in w and "no grid group" in w for w in d["warnings"])
    assert not any(
        "grid group" in w for w in doc["warnings"]
    )  # nothing to say for the outlines of the main world


def test_m5_label_comes_from_the_nearest_labelled_axis_ties_take_the_lower(base):
    q = outline(probe_call(base, "GR"), 800, 800, (61000, 48000))
    axes = axes_of(q)
    assert axes[("V002", "F010")] == {  # no labelled axis: the unlabelled one answers
        "group_id": "V002",
        "family_id": "F010",
        "label": None,
        "offset": 500.0,
        "nearest_unlabelled_offset": None,
    }
    f11 = axes[("V002", "F011")]  # P (60000) and Q (62000) are both 1000 away
    assert (f11["label"], f11["offset"]) == ("P", 1000.0)


def test_m4_axis_position_is_taken_at_the_line_midpoint(base):
    q = outline(probe_call(base, "GR"), 800, 800, (61000, 48000))
    assert axes_of(q)[("V002", "F012")]["offset"] == pytest.approx(-50.0, abs=0.5)  # start would give 0


def test_m1_concentric_circles_across_a_rounding_boundary_are_one_symbol(base):
    d = probe_call(base, "A")
    (a,) = d["outlines"]
    assert a["symbols"] == 1 and d["symbols"]["total"] == 1
    assert [(g["diameters"], g["count"]) for g in d["symbols"]["groups"]] == [([300.0, 400.0], 1)]


def test_m2_a_round_cap_is_tested_by_its_arcs_not_its_chords(base):
    d = probe_call(base, "B")
    (b,) = d["outlines"]
    assert b["symbols"] == 1 and d["symbols"]["outside"] == 0  # r 750 is inside r 1000, outside the square


def test_m2_a_polygon_of_more_than_64_vertices_is_tested_whole(base):
    d = probe_call(base, "T")
    (t,) = d["outlines"]
    assert t["symbols"] == 1 and d["symbols"]["outside"] == 0
    assert not any("64" in w for w in d["warnings"])


def test_m2_arcs_that_cannot_be_flattened_are_named_in_a_warning(base, monkeypatch):
    import ezdxf.path

    def boom(*_a: Any, **_k: Any) -> Any:
        raise ValueError("no path")

    monkeypatch.setattr(ezdxf.path, "make_path", boom)
    d = probe_call(base, "B")
    (b,) = d["outlines"]
    assert any(b["id"] in w and "flatten" in w for w in d["warnings"])


def test_m2_a_rotated_cap_is_the_drawn_polygon(base):
    d = probe_call(base, "K")
    assert (d["symbols"]["inside"], d["symbols"]["outside"]) == (
        1,
        2,
    )  # 50 inside its corner, 50 and 1.8 outside


def test_m3_a_mark_is_measured_from_the_middle_of_its_text(base):
    d = probe_call(base, "M", marks=r"PM-\d+")
    near = outline(d, 1000, 1000, (19000, 42000))
    far = outline(d, 1000, 1000, (15000, 42000))
    assert [m["text"] for m in near["marks"]] == ["PM-10"] and far["marks"] == []
    assert d["marks_ambiguous"] == []


def test_m3_a_near_tie_is_ambiguous_by_the_relative_rule(base):
    d = probe_call(base, "R", marks=r"PR-\d+")
    (amb,) = d["marks_ambiguous"]
    assert amb["text"] == "PR-11" and len(amb["outlines"]) == 2
    assert all(o["marks"] == [] for o in d["outlines"])


def test_m4_a_mark_inside_nested_outlines_goes_to_the_innermost(base):
    d = probe_call(base, "N", outline_layers=["N-CAP", "N-COL"], marks=r"PN-\d+")
    cap = outline(d, 1700, 1700, (5000, 42000))
    col = outline(d, 400, 400, (5000, 42000))
    assert [m["text"] for m in cap["marks"]] == ["PN-1"]  # beside the stub, inside the cap only
    assert [m["text"] for m in col["marks"]] == ["PN-2"]  # inside both
    assert d["marks_ambiguous"] == []
    assert any(cap["id"] in w and col["id"] in w and "nested" in w for w in d["warnings"])


def test_m4_a_mark_inside_two_overlapping_outlines_stays_ambiguous(base):
    d = call(base, marks=r"PD-\d+")  # D and E overlap between x 50650 and 50850; neither holds the other
    (amb,) = d["marks_ambiguous"]
    assert amb["text"] == "PD-1" and len(amb["outlines"]) == 2


def test_m5_defaults_follow_the_unit_of_the_drawing(tmp_path):
    inp = build_units_dxf(tmp_path, 6)  # metres
    run_intake(inp, tmp_path / "work", "demo-units", knowledge=PROPOSED_FONT_TABLE)
    write_structure(inp, tmp_path / "work")
    d = contents(
        tmp_path / "work", REL, input_dir=inp, sheet="model#01", outline_layers=[CAP], circle_layers=[PILE]
    )
    assert (d["query"]["tol"], d["query"]["max_long"], d["query"]["mark_radius"]) == (0.001, 20.0, 3.0)
    assert [o["long"] for o in d["outlines"]] == [15.0]  # the 25 m outline is a frame
    assert any("--max-long" in w for w in d["warnings"])
    assert not any("mm defaults" in w for w in d["warnings"])


def test_m5_unknown_units_use_the_millimetre_values_and_say_so(tmp_path):
    inp = build_units_dxf(tmp_path, 0)
    run_intake(inp, tmp_path / "work", "demo-units", knowledge=PROPOSED_FONT_TABLE)
    write_structure(inp, tmp_path / "work")
    d = contents(
        tmp_path / "work", REL, input_dir=inp, sheet="model#01", outline_layers=[CAP], circle_layers=[PILE]
    )
    assert (d["query"]["tol"], d["query"]["max_long"], d["query"]["mark_radius"]) == (1.0, 20000.0, 3000.0)
    assert any("mm defaults assumed" in w and "--max-long" in w for w in d["warnings"])


def test_m5_explicit_values_are_kept(base):
    d = call(base, tol=2.0, max_long=40000, mark_radius=1234.0)
    assert (d["query"]["tol"], d["query"]["max_long"], d["query"]["mark_radius"]) == (2.0, 40000.0, 1234.0)


def test_m5_the_cli_defaults_are_resolved_not_fixed(base, capsys):
    argv = ["contents", str(base / "work"), REL, "--sheet", "model#01", "--outline-layer", CAP,
            "--circle-layer", PILE, "--input-dir", str(base / "input")]  # fmt: skip
    assert main(argv) == 0
    q = json.loads(capsys.readouterr().out)["query"]
    assert (q["tol"], q["max_long"], q["mark_radius"]) == (1.0, 20000.0, 3000.0)


def test_m6_marks_ignore_spaces_off_layers_and_partial_matches(base):
    d = probe_call(base, "X", marks=r"PS-\d+")
    (x,) = d["outlines"]
    assert [m["text"] for m in x["marks"]] == ["PS-4"]  # " PS-4 " is stripped; "PS-5" is on an off layer
    assert d["marks_unassigned"] == [] and d["marks_ambiguous"] == []
    assert any("1 text" in w and "do not fully match" in w for w in d["warnings"])  # m8: "PS-6, PS-7"


def test_m6_a_mark_exactly_at_the_radius_is_assigned(base):
    c = outline(call(base, marks=r"DC-\d+", mark_radius=3150.0), 1700, 1700, (30000, 20000))
    assert [m["text"] for m in c["marks"]] == ["DC-3"]


def test_m6_sizes_within_the_tolerance_share_a_summary_row(base):
    d = probe_call(base, "U")
    (row,) = d["summary"]
    assert (row["count"], row["short"], row["long"]) == (2, 1000.0, 1000.0)


def test_m8_a_matching_text_without_a_position_is_counted(base, monkeypatch):
    import tekla_harness.contents as module

    real = module._printed_scope

    def scope(entries: Any, hidden: bool) -> Any:
        kept = real(entries, hidden)
        for e in kept:
            if e["display_text"].strip() == "PS-4":
                e["position"] = {**e["position"], "x": None}
        return kept

    monkeypatch.setattr(module, "_printed_scope", scope)
    d = probe_call(base, "X", marks=r"PS-\d+")
    assert d["outlines"][0]["marks"] == []
    assert any("1 matching text" in w and "no position" in w for w in d["warnings"])


def test_m8_a_matching_text_without_a_y_is_counted_too(base, monkeypatch):
    import tekla_harness.contents as module

    real = module._printed_scope

    def scope(entries: Any, hidden: bool) -> Any:
        kept = real(entries, hidden)
        for e in kept:
            if e["display_text"].strip() == "PS-4":
                e["position"] = {**e["position"], "y": None}
        return kept

    monkeypatch.setattr(module, "_printed_scope", scope)
    d = probe_call(base, "X", marks=r"PS-\d+")
    assert any("1 matching text" in w and "no position" in w for w in d["warnings"])


def test_m3_a_mark_on_two_cap_types_and_an_outline_with_two_marks_are_warned(base, doc):
    d = probe_call(base, "W", marks=r"PW-\d+")
    assert any("PW-1" in w and "2 types" in w for w in d["warnings"])
    assert not any("hold different marks" in w for w in d["warnings"])
    a = outline(doc, 1700, 1700, (10000, 20000))
    assert any(
        a["id"] in w and "hold different marks" in w and "DC-1" in w and "DC-2" in w for w in doc["warnings"]
    )


def test_m2_a_mark_seen_twice_on_one_outline_counts_that_outline_once(base):
    d = probe_call(base, "W", marks=r"PW-\d+")
    one = next(r for r in d["summary"] if (r["short"], r["long"]) == (1000.0, 1000.0))
    assert one["marks_seen"] == {"PW-1": 1} and one["unmarked"] == 0


def test_m1_shared_symbol_warning_keeps_every_digit_of_the_coordinates(doc):
    assert any("(50750.000, 30000.000)" in w for w in doc["warnings"])


def test_m7_dropped_frames_are_named_with_their_long_side(base, doc):
    frame = next(o for o in call(base, max_long=40000)["outlines"] if o["long"] == 30000)
    assert any(frame["id"] in w and "30000" in w and "--max-long" in w for w in doc["warnings"])


def test_m6_texts_and_items_of_another_space_are_not_used(base):
    sheets = json.loads((base / "work" / "structure" / f"{REL}.sheets.json").read_text())["sheets"]
    (layout,) = [s["sheet_id"] for s in sheets if s["space"] != "model"]
    d = probe_call(base, "L", sheet=layout, marks=r"PL-\d+")
    (cap,) = d["outlines"]
    assert cap["symbols"] == 1 and d["marks_unassigned"] == [] and cap["marks"] == []
    assert any("1 mark text" in w and "other space" in w for w in d["warnings"])


def test_a_frozen_pile_block_inside_a_cap_does_not_count(base):
    d = probe_call(base, "Z")
    (z,) = d["outlines"]
    assert z["symbols"] == 1  # only the pile on the live layer


def test_a_donut_on_the_outline_layer_is_not_used_and_says_so(base):
    d = probe_call(base, "D")
    (cap,) = d["outlines"]
    assert cap["long"] == 1700 and any("1 circle(s) on outline layers not used" in w for w in d["warnings"])


def test_the_id_pattern_is_one_shared_definition():
    contents_schema = json.loads(Path("schemas/contents.schema.json").read_text(encoding="utf-8"))
    pattern = contents_schema["$defs"]["outline"]["properties"]["id"]
    assert "pattern" not in pattern and "item_id" in pattern["$ref"]


def test_m3_a_rotated_text_is_measured_from_its_rotated_middle(base):
    d = probe_call(base, "Y", marks=r"PY-\d+")
    (cap,) = d["outlines"]
    (m,) = cap["marks"]
    # box 980 x 350 turned 90 degrees: middle = insert + (-175, +490) = (70700, 45690); the cap corner is
    # (70500, 45500)
    assert m["distance"] == pytest.approx(math.hypot(200, 190), abs=0.001)


def test_m3_the_tie_rule_keeps_the_absolute_tolerance_near_zero(base):
    d = probe_call(base, "V", marks=r"PV-\d+")
    (amb,) = d["marks_ambiguous"]  # 1.6 and 2.4 from the two caps: 0.8 apart, more than a quarter of 2.4
    assert amb["text"] == "PV-1" and all(o["marks"] == [] for o in d["outlines"])


def test_a_symbol_within_the_tolerance_of_the_boundary_counts_as_inside(base):
    d = probe_call(base, "E", detail=True)
    (cap,) = d["outlines"]
    assert cap["symbols"] == 4 and (d["symbols"]["inside"], d["symbols"]["outside"]) == (4, 1)
    assert [35851.2, 5200.0] in [s["centre"] for s in d["symbols_outside"]]


def test_m5_the_unknown_unit_warning_only_when_a_default_is_used(tmp_path):
    inp = build_units_dxf(tmp_path, 0)
    run_intake(inp, tmp_path / "work", "demo-units", knowledge=PROPOSED_FONT_TABLE)
    write_structure(inp, tmp_path / "work")

    def run(**kw: Any) -> dict[str, Any]:
        return contents(
            tmp_path / "work",
            REL,
            input_dir=inp,
            sheet="model#01",
            outline_layers=[CAP],
            circle_layers=[PILE],
            **kw,
        )

    every = {"tol": 1.0, "max_long": 20000.0, "mark_radius": 3000.0}
    assert not any("mm defaults" in w for w in run(**every)["warnings"])
    for missing in every:
        given = {k: v for k, v in every.items() if k != missing}
        assert any("mm defaults" in w for w in run(**given)["warnings"]), missing


def test_listed_names_at_most_ten_and_counts_the_rest():
    from tekla_harness.contents import _listed

    names = [f"G-{i}" for i in range(11)]
    assert _listed(names[:10]) == ", ".join(names[:10])
    assert _listed(names) == ", ".join(names[:10]) + " (+1 more)"


def test_the_detail_group_answers_only_for_centres_strictly_inside_it(base):
    d = probe_call(base, "GR")
    groups = {}
    for o in d["outlines"]:
        groups[(o["short"], tuple(o["centre"]))] = {x["group_id"] for x in o["axes"]}
    inside = groups[(800.0, (61000.0, 48000.0))]
    assert inside == {"V001", "V002"}
    for short in (810.0, 820.0, 830.0, 840.0, 850.0, 860.0, 870.0):  # on an edge, or beside the group
        (only,) = [g for (sh, _), g in groups.items() if sh == short]
        assert only == {"V001"}, short
    q = next(o for o in d["outlines"] if o["short"] == 800.0 and o["centre"][0] == 61000.0)
    assert [x["group_id"] for x in q["axes"]][:2] == ["V001", "V001"]  # groups in id order
    assert [x["group_id"] for x in q["axes"]][-1] == "V002"


def test_the_outline_list_may_hold_exactly_the_limit(base):
    d = call(base, max_rows=8)
    assert len(d["outlines"]) == 8 and not any("truncated" in w for w in d["warnings"])


def test_a_layout_with_more_outlines_of_its_own_names_the_other_space(base):
    sheets = json.loads((base / "work" / "structure" / f"{REL}.sheets.json").read_text())["sheets"]
    (layout,) = [s["sheet_id"] for s in sheets if s["space"] != "model"]
    d = probe_call(base, "LP", sheet=layout)
    assert len(d["outlines"]) == 2  # the two drawn in the layout
    assert d["symbols"]["total"] == 0  # the pile of the viewport lies in another space
    assert any("1 outline(s) and 1 circle(s) in other spaces than Plot not used" in w for w in d["warnings"])
    q = probe_call(base, "LQ", sheet=layout)
    assert any("1 outline(s) and 0 circle(s) in other spaces than Plot not used" in w for w in q["warnings"])


def test_no_outline_kept_means_no_space_to_compare_marks_with(base):
    d = call(base, marks=r"DC-\d+", max_long=1)
    assert d["outlines"] == [] and len(d["marks_unassigned"]) > 3
    assert not any("other spaces" in w for w in d["warnings"])


def test_a_layer_in_both_lists_is_read_as_symbols_and_not_reported(base):
    d = probe_call(base, "D", circle_layers=["D-PILE", "D-CAP"])
    assert not any("not used" in w for w in d["warnings"])
    assert d["symbols"]["total"] == 2  # the pile and the donut, read as a circle


def test_shared_symbol_warning_counts_the_shared_ones(doc):
    (w,) = [w for w in doc["warnings"] if "inside more than one outline" in w]
    assert w.startswith("1 symbol(s) inside")


def test_symbol_centres_come_in_order_and_equal_to_the_limit_is_not_a_frame(base):
    d = call(base, detail=True, max_long=30000)
    a = outline(d, 1700, 1700, (10000, 20000))
    assert a["symbol_centres"] == [[9500.0, 19500.0], [10500.0, 20500.0]]
    assert not any("--max-long" in w for w in d["warnings"])


def test_a_zero_tolerance_or_a_zero_radius(base):
    with pytest.raises(ReaderError):
        call(base, tol=0)
    assert call(base, mark_radius=0, marks=r"DC-\d+")["outlines"]  # radius 0 is allowed


# --- a second small world for the mutation run: dedupe, nesting, order and tie probes -------------------


def build_dxf2(base: Path) -> Path:
    root = base / "input"
    (root / "plans").mkdir(parents=True)
    doc = readfile(str(build_set(base, "src.dxf")))
    names = ("Q", "OR", "NE", "EQ", "LS", "TA", "TB", "TC", "NM", "AM", "SE", "OU", "BIG")
    for name in names:
        doc.layers.add(f"{name}-CAP")
        doc.layers.add(f"{name}-PILE")
    msp = doc.modelspace()

    def caps(layer: str, *points: tuple[float, float, float, float], cw: bool = False) -> None:
        for cx, cy, long, short in points:
            ring = rect(cx, cy, long, short)
            msp.add_lwpolyline(ring[::-1] if cw else ring, close=True, dxfattribs={"layer": layer})

    def label(value: str, mx: float, my: float, layer: str = "0") -> None:
        msp.add_text(value, height=350, dxfattribs={"insert": mid_insert(value, mx, my), "layer": layer})

    def piles(layer: str, *points: tuple[float, float, float]) -> None:
        for x, y, d in points:
            msp.add_circle((x, y), d / 2, dxfattribs={"layer": layer})

    # Q: symbols merged within the tolerance (1) inside one cap
    caps("Q-CAP", (5000, 5000, 2000, 2000))
    piles(
        "Q-PILE",
        (4500, 4500.6, 200),  # y straddles a rounding boundary with the next one; created first
        (4500, 4500.4, 150),
        (5500, 5000, 150),  # exactly tol from the next one: one symbol
        (5501, 5000, 120),
        (5700, 5000, 100),  # 1.4 from the next one: two symbols
        (5701.4, 5000, 80),
        (4200, 4200, 210),  # a, b are 1.2 apart; c is within tol of both and nearest to b
        (4200.9, 4199.2, 310),
        (4200.95, 4200.1, 130),
        (5300, 5300, 300.4),  # a diameter within the tolerance of 300
        (4600, 5800, 300),
        (4600, 5900, 300),
    )
    # OR: caps in an order that is not their sort order (short, long, y, x)
    caps(
        "OR-CAP",
        (33000, 4000, 1000, 800),
        (31000, 4000, 1000, 800),
        (30000, 5000, 1000, 800),
        (35000, 8000, 1000, 800),
        (36500, 8000, 1200, 700),
        (37500, 8000, 1000, 800),
    )
    # NE: a clockwise outer cap with a counter-clockwise inner one and a mark inside the inner one
    caps("NE-CAP", (15000, 5000, 3000, 3000), cw=True)
    caps("NE-CAP", (15000, 5000, 1000, 1000))
    label("PN-1", 15000, 5000)
    # EQ: two caps of the same area with each other's centre inside, and a mark inside both
    caps("EQ-CAP", (20000, 5000, 1000, 1000), (20400, 5000, 1000, 1000))
    label("PE-1", 20200, 5000)
    # LS: an L-shaped cap with a small cap standing in its notch (its bbox holds the small one)
    msp.add_lwpolyline(
        [(25000, 5000), (28000, 5000), (28000, 6000), (26000, 6000), (26000, 8000), (25000, 8000)],
        close=True,
        dxfattribs={"layer": "LS-CAP"},
    )
    caps("LS-CAP", (27000, 7000, 400, 400))
    # TA, TB, TC: a mark between two caps, 6/8, 7.3/10 and 6/7.9 from them
    for i, (layer, d1, d2) in enumerate((("TA", 6, 8), ("TB", 7.3, 10), ("TC", 6, 7.9))):
        y = 15000 + 7000 * i
        caps(f"{layer}-CAP", (50000, y, 1000, 1000), (50500 + d1 + d2 + 500, y, 1000, 1000))
        label(f"P{layer}-1", 50500 + d1, y)
    # NM: two marks beside a cap, the farther one written first
    caps("NM-CAP", (40000, 12000, 1000, 1000))
    label("PM-2", 40000, 12800)
    label("PM-1", 40000, 12700 - 300 + 100)
    # AM: two ambiguous marks, written in the opposite order of their names
    caps("AM-CAP", (60000, 20000, 1000, 1000), (62000, 20000, 1000, 1000))
    label("PA-9", 61000, 20000)
    label("PA-1", 61000, 20200)
    # SE: three caps of one size, two holding marks written in the opposite order of their names
    caps("SE-CAP", (10000, 40000, 1000, 1000), (12000, 40000, 1000, 1000), (14000, 40000, 1000, 1000))
    label("PS-2", 10000, 40000)
    label("PS-1", 12000, 40000)
    # OU: concentric circles outside every cap, drawn 18 then 15 wide
    caps("OU-CAP", (20000, 40000, 1000, 1000))
    piles("OU-PILE", (30000, 40000, 18), (30000, 40000, 15))
    # BIG: more outlines than the default list limit
    caps("BIG-CAP", *[(1000 + 100 * (k % 40), 45000 - 100 * (k // 40), 50, 50) for k in range(501)])
    doc.saveas(root / REL)
    return root


@pytest.fixture(scope="module")
def base2(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("contents2")
    inp = build_dxf2(root)
    work = root / "work"
    run_intake(inp, work, "demo-contents", knowledge=PROPOSED_FONT_TABLE)
    write_structure(inp, work)
    (work / "structure" / f"{REL}.grids.json").write_text(json.dumps(grids_doc()), encoding="utf-8")
    return root


def call2(base: Path, name: str, **kw: Any) -> dict[str, Any]:
    kw.setdefault("sheet", "model#01")
    return contents(
        base / "work",
        REL,
        input_dir=base / "input",
        outline_layers=[f"{name}-CAP"],
        circle_layers=[f"{name}-PILE"],
        **kw,
    )


def test_symbols_merge_within_tolerance_in_both_directions_and_to_the_nearest(base2):
    d = call2(base2, "Q", detail=True)
    (cap,) = d["outlines"]
    # merged: (4500, 4500.4/.6), (5500/5501), and the c circle joins the nearer b
    assert d["symbols"]["total"] == 9 and cap["symbols"] == 9
    groups = {tuple(g["diameters"]): g["count"] for g in d["symbols"]["groups"]}
    assert groups == {
        (150.0, 200.0): 1,  # the y pair
        (120.0, 150.0): 1,  # the pair exactly tol apart
        (100.0,): 1,
        (80.0,): 1,  # 1.4 apart: two symbols
        (210.0,): 1,
        (130.0, 310.0): 1,  # c joins b, the nearer of the two
        (300.0,): 3,  # 300.4 snapped to 300, plus the two of 300 (100 apart)
    }
    assert d["symbols"]["groups"][0]["count"] == 3  # largest count first
    assert [4500.0, 4500.4] in cap[
        "symbol_centres"
    ]  # the lower of the pair is kept, whatever the drawing order
    assert [5500.0, 5000.0] in cap["symbol_centres"]


def test_outlines_come_sorted_by_layer_short_long_then_position(base2):
    d = call2(base2, "OR")
    got = [(o["short"], o["long"], o["centre"]) for o in d["outlines"]]
    assert got == [
        (700.0, 1200.0, [36500.0, 8000.0]),
        (800.0, 1000.0, [31000.0, 4000.0]),
        (800.0, 1000.0, [33000.0, 4000.0]),
        (800.0, 1000.0, [30000.0, 5000.0]),
        (800.0, 1000.0, [35000.0, 8000.0]),
        (800.0, 1000.0, [37500.0, 8000.0]),
    ]


def test_a_mark_inside_a_clockwise_outer_cap_and_its_inner_cap_goes_to_the_inner(base2):
    d = call2(base2, "NE", marks=r"PN-\d+")
    inner = next(o for o in d["outlines"] if o["long"] == 1000)
    outer = next(o for o in d["outlines"] if o["long"] == 3000)
    assert [(m["text"], m["distance"]) for m in inner["marks"]] == [("PN-1", 0.0)]
    assert outer["marks"] == [] and d["marks_ambiguous"] == []
    assert any(
        "1 nested outline(s)" in w and outer["id"] + " holds " + inner["id"] in w for w in d["warnings"]
    )


def test_equal_caps_with_each_others_centre_inside_are_not_nested(base2):
    d = call2(base2, "EQ", marks=r"PE-\d+")
    assert not any("nested" in w for w in d["warnings"])
    assert [m["text"] for m in d["marks_ambiguous"]] == ["PE-1"] and len(
        d["marks_ambiguous"][0]["outlines"]
    ) == 2


def test_a_cap_whose_notch_holds_a_small_cap_does_not_hold_it(base2):
    d = call2(base2, "LS")
    assert len(d["outlines"]) == 2 and not any("nested" in w for w in d["warnings"])


@pytest.mark.parametrize(
    ("layer", "ambiguous"),
    [("TA", True), ("TB", False), ("TC", True)],  # 6/8 and 6/7.9 tie, 7.3/10 does not
)
def test_the_relative_tie_rule_at_its_edges(base2, layer, ambiguous):
    d = call2(base2, layer, marks=rf"P{layer}-\d+")
    assert bool(d["marks_ambiguous"]) is ambiguous
    assert sum(len(o["marks"]) for o in d["outlines"]) == (0 if ambiguous else 1)


def test_marks_of_one_outline_come_nearest_first_whatever_their_order_in_the_drawing(base2):
    d = call2(base2, "NM", marks=r"PM-\d+")
    (cap,) = d["outlines"]
    assert [m["text"] for m in cap["marks"]] == ["PM-1", "PM-2"]
    assert cap["marks"][0]["distance"] < cap["marks"][1]["distance"]


def test_ambiguous_marks_are_listed_by_text(base2):
    d = call2(base2, "AM", marks=r"PA-\d+")
    assert [m["text"] for m in d["marks_ambiguous"]] == ["PA-1", "PA-9"]


def test_marks_seen_are_listed_by_text(base2):
    d = call2(base2, "SE", marks=r"PS-\d+")
    (row,) = d["summary"]
    assert list(row["marks_seen"]) == ["PS-1", "PS-2"] and row["unmarked"] == 1


def test_the_diameters_of_an_outside_symbol_are_listed_in_order(base2):
    d = call2(base2, "OU", detail=True)
    assert d["symbols_outside"] == [{"centre": [30000.0, 40000.0], "diameters": [15.0, 18.0]}]


def test_the_default_limit_is_five_hundred_outlines(base2):
    d = call2(base2, "BIG")
    assert d["outlines_total"] == 501 and len(d["outlines"]) == 500
    assert any("contents truncated: outlines 500 of 501" in w for w in d["warnings"])


def test_nearest_axis_ties_within_tol_take_the_lower_and_a_far_axis_never_ties():
    from tekla_harness.contents import _family_axes, _nearest_axis

    assert _nearest_axis(5.0, [], 1.0) is None
    assert _nearest_axis(70.0, [("a", 0.0), ("b", 80.0)], 1.0) == ("b", 80.0)
    assert _nearest_axis(1.0, [("a", 0.0), ("b", 2.0)], 1.0) == ("a", 0.0)  # equally near: the lower
    assert _nearest_axis(1.1, [("a", 0.0), ("b", 2.0)], 1.0) == ("a", 0.0)  # 0.2 apart, within tol: the lower
    assert _nearest_axis(1.9, [("a", 0.0), ("b", 2.0)], 1.0) == ("b", 2.0)
    assert _family_axes(2.0, [], [], 1.0) is None
    assert _family_axes(2.0, [(None, 0.0)], [], 1.0) == (None, 2.0, None)
    assert _family_axes(2.0, [(None, 5.0)], [], 1.0) == (None, -3.0, None)
    assert _family_axes(2.0, [("A", 0.0), (None, 10.0)], [], 1.0) == (
        "A",
        2.0,
        None,
    )  # the labelled is nearer
    assert _family_axes(5.0, [("A", 0.0), (None, 10.0)], [], 1.0) == (
        "A",
        5.0,
        None,
    )  # equally near: the labelled
    assert _family_axes(9.0, [("A", 0.0), (None, 10.0)], [], 1.0) == (
        "A",
        9.0,
        -1.0,
    )  # the unlabelled is nearer
    # lines: they join only the nearest unlabelled offset, and never answer alone
    assert _family_axes(9.0, [("A", 0.0)], [10.0], 1.0) == ("A", 9.0, -1.0)
    assert _family_axes(9.0, [(None, 0.0)], [10.0], 1.0) == (None, 9.0, None)
    assert _family_axes(9.0, [], [10.0], 1.0) is None


def test_marks_are_listed_by_text_then_entry():
    from tekla_harness.contents import _by_text

    marks = [
        {"text": "B", "entry_id": "T1"},
        {"text": "A", "entry_id": "T9"},
        {"text": "A", "entry_id": "T2"},
    ]
    assert [(m["text"], m["entry_id"]) for m in _by_text(marks)] == [("A", "T2"), ("A", "T9"), ("B", "T1")]


# --- T22 review 2: probes on sheet model#02 (own layers and mark names) ---------------------------


def build_dxf3(base: Path) -> Path:
    root = base / "input"
    (root / "plans").mkdir(parents=True)
    doc = readfile(str(build_set(base, "src.dxf")))
    for name in ("K", "V", "W", "E", "F", "P", "I"):
        doc.layers.add(f"{name}-CAP")
        doc.layers.add(f"{name}-PILE")
    doc.layers.add("E-COL")
    doc.layers.add("F-COL")
    msp = doc.modelspace()

    def cap(layer: str, cx: float, cy: float, size: float, **extra: Any) -> None:
        msp.add_lwpolyline(rect(cx, cy, size, size), close=True, dxfattribs={"layer": layer, **extra})

    # K: two caps 3000 apart; MTEXT and TEXT, both MIDDLE_CENTER, centred 1200 below K1
    cap("K-CAP", 120000, 40000, 1000)
    cap("K-CAP", 123000, 40000, 1000)
    msp.add_mtext(
        "DK-1",
        dxfattribs={
            "insert": (120000, 38800),
            "char_height": 1250,
            "attachment_point": MTextEntityAlignment.MIDDLE_CENTER,
        },
    )
    msp.add_text("DK-2", height=1250).set_placement((120000, 38800), align=TextEntityAlignment.MIDDLE_CENTER)
    # V: stacked caps; MTEXT TOP_LEFT (the MTEXT default) whose box middle is 175 above V2
    cap("V-CAP", 140000, 40000, 1000)
    cap("V-CAP", 140000, 37000, 1000)
    msp.add_mtext(
        "DV-1",
        dxfattribs={
            "insert": (138000, 38300),
            "char_height": 1250,
            "attachment_point": MTextEntityAlignment.TOP_LEFT,
        },
    )
    msp.add_text("DV-2", height=1250).set_placement((138000, 37675), align=TextEntityAlignment.MIDDLE_LEFT)
    # W: TEXT MIDDLE_LEFT from x 161000 (middle under W2), and its LEFT twin at the same visual place
    cap("W-CAP", 160000, 40000, 1000)
    cap("W-CAP", 163000, 40000, 1000)
    msp.add_text("DW-1", height=1250).set_placement((161000, 38800), align=TextEntityAlignment.MIDDLE_LEFT)
    msp.add_text("DW-2", height=1250, dxfattribs={"insert": (161000, 38800 - 625)})
    # E: cap 1700 with a column stub 400, four MIDDLE_CENTER marks exactly on the stub's edges
    cap("E-CAP", 110000, 40000, 1700)
    cap("E-COL", 110000, 40000, 400)
    for value, pt in (
        ("EC-1", (110000, 39800)),
        ("EC-2", (110000, 40200)),
        ("EC-3", (109800, 40000)),
        ("EC-4", (110200, 40000)),
    ):
        msp.add_text(value, height=100).set_placement(pt, align=TextEntityAlignment.MIDDLE_CENTER)
    # F: the same pair; a cap mark 2000 below the cap's bottom edge (near the stub's tie distance)
    cap("F-CAP", 110000, 20000, 1700)
    cap("F-COL", 110000, 20000, 400)
    msp.add_text("FC-1", height=350).set_placement(
        (110000, 20000 - 850 - 2000), align=TextEntityAlignment.MIDDLE_CENTER
    )
    # P: piles exactly tol (1) outside each edge of a cap, and one 1.5 outside the left edge
    cap("P-CAP", 120000, 10000, 1700)
    for pt in ((119149, 10000), (120851, 10000), (120000, 9149), (120000, 10851), (119148.5, 10200)):
        msp.add_circle(pt, 150, dxfattribs={"layer": "P-PILE"})
    # I: an invisible cap with an invisible pile, a visible cap of the same size with a visible pile
    cap("I-CAP", 130000, 10000, 1700, invisible=1)
    msp.add_circle((130000, 10000), 150, dxfattribs={"layer": "I-PILE", "invisible": 1})
    cap("I-CAP", 133000, 10000, 1700)
    msp.add_circle((133000, 10000), 150, dxfattribs={"layer": "I-PILE"})
    doc.saveas(root / REL)
    return root


@pytest.fixture(scope="module")
def base3(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("contents3")
    inp = build_dxf3(root)
    work = root / "work"
    run_intake(inp, work, "demo-contents", knowledge=PROPOSED_FONT_TABLE)
    write_structure(inp, work)
    return root


def call3(base: Path, name: str, **kw: Any) -> dict[str, Any]:
    kw.setdefault("sheet", "model#02")
    kw.setdefault("outline_layers", [f"{name}-CAP"])
    kw.setdefault("circle_layers", [f"{name}-PILE"])
    return contents(base / "work", REL, input_dir=base / "input", **kw)


def marks_by_centre(d: dict[str, Any]) -> dict[tuple[float, float], list[str]]:
    return {(o["centre"][0], o["centre"][1]): [m["text"] for m in o["marks"]] for o in d["outlines"]}


@pytest.mark.parametrize(
    ("name", "centre", "texts"),
    [
        ("K", (120000, 40000), ["DK-1", "DK-2"]),  # MTEXT and TEXT MIDDLE_CENTER under K1
        ("V", (140000, 37000), ["DV-1", "DV-2"]),  # MTEXT TOP_LEFT and its MIDDLE_LEFT twin: V2
        ("W", (163000, 40000), ["DW-1", "DW-2"]),  # TEXT MIDDLE_LEFT and its LEFT twin: W2
    ],
)
def test_m1_a_mark_is_placed_by_the_centre_of_its_text_box_whatever_its_alignment(base3, name, centre, texts):
    d = call3(base3, name, marks=rf"D{name}-\d+")
    assert d["marks_ambiguous"] == [] and d["marks_unassigned"] == []
    marked = {k: v for k, v in marks_by_centre(d).items() if v}
    assert marked == {centre: texts}


@pytest.mark.parametrize("edge", ["EC-1", "EC-2", "EC-3", "EC-4"])
def test_m1_a_mark_on_an_edge_of_the_inner_outline_goes_to_it_on_every_edge(base3, edge):
    d = call3(base3, "E", outline_layers=["E-CAP", "E-COL"], marks=r"EC-\d+")
    stub = next(o for o in d["outlines"] if o["layer"] == "E-COL")
    cap = next(o for o in d["outlines"] if o["layer"] == "E-CAP")
    assert sorted(m["text"] for m in stub["marks"]) == ["EC-1", "EC-2", "EC-3", "EC-4"]
    assert edge in [m["text"] for m in stub["marks"]] and cap["marks"] == []
    assert d["marks_ambiguous"] == [] and all(m["distance"] == 0.0 for m in stub["marks"])


def test_m2_a_cap_mark_is_not_ambiguous_with_the_stub_inside_the_cap(base3):
    d = call3(base3, "F", outline_layers=["F-CAP", "F-COL"], marks=r"FC-\d+")
    cap = next(o for o in d["outlines"] if o["layer"] == "F-CAP")
    stub = next(o for o in d["outlines"] if o["layer"] == "F-COL")
    assert [(m["text"], m["distance"]) for m in cap["marks"]] == [("FC-1", 2000.0)]
    assert stub["marks"] == [] and d["marks_ambiguous"] == []


def test_m2_piles_exactly_tol_outside_each_edge_count_on_low_and_high_edges(base3):
    d = call3(base3, "P")
    (cap,) = d["outlines"]
    assert cap["symbols"] == 4 and d["symbols"]["total"] == 5 and d["symbols"]["outside"] == 1


def test_m3_the_invisible_flag_is_reported_per_outline_per_row_and_in_one_warning(base3):
    d = call3(base3, "I")
    assert sorted(o["invisible"] for o in d["outlines"]) == [False, True]
    (row,) = d["summary"]
    assert row["count"] == 2 and row["invisible"] == 1
    hits = [w for w in d["warnings"] if "invisible" in w]
    assert any("1 outline(s) and 1 symbol(s) used carry the invisible flag" in w for w in hits)


def test_m3_no_invisible_warning_without_the_flag(doc):
    assert all(o["invisible"] is False for o in doc["outlines"])
    assert all(r["invisible"] == 0 for r in doc["summary"])
    assert not any("invisible" in w for w in doc["warnings"])


# --- E10a: an unlabelled grid line of the grids document answers `nearest_unlabelled_offset` ------


def build_dxf4(base: Path) -> Path:
    root = base / "input"
    (root / "plans").mkdir(parents=True)
    doc = readfile(str(build_set(base, "src.dxf")))
    doc.layers.add("U-CAP")
    msp = doc.modelspace()
    for cx, cy in ((100000, 18000), (110000, 25000), (120000, 10000)):  # on the line, on B, on A
        msp.add_lwpolyline(rect(cx, cy, 1000, 1000), close=True, dxfattribs={"layer": "U-CAP"})
    doc.saveas(root / REL)
    return root


def grids_doc_unlabelled_line() -> dict[str, Any]:
    """One family of model#02: A at y 10000, B at y 25000 and, in `unlabelled_lines` (not in `axes`, as the
    grid detector writes it), a line 0.1 degrees off the family direction whose midpoint is at y 18000 (its
    start is at y 17960); its `offset` (8000, from the first axis) is no position."""

    def line(y: float) -> dict[str, Any]:
        return {"start": [90000, y], "end": [140000, y]}

    return {
        "schema_version": "0.1",
        "file": REL,
        "groups": [
            {
                "group_id": "V001",
                "sheet": "model#02",
                "space": "model",
                "bbox": [89000.0, 0.0, 141000.0, 50000.0],
                "families": [
                    {
                        "family_id": "F001",
                        "direction": [1.0, 0.0],
                        "normal": [0.0, 1.0],
                        "axes": [
                            {"axis_id": "G0001", "label": {"value": "A"}, "line": line(10000)},
                            {"axis_id": "G0002", "label": {"value": "B"}, "line": line(25000)},
                        ],
                        "unlabelled_lines": [
                            {
                                "offset": 8000.0,
                                "line": {"start": [90000, 17960], "end": [140000, 18040]},
                                "empty_bubble": False,
                            }
                        ],
                    }
                ],
            }
        ],
    }


@pytest.fixture(scope="module")
def base4(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("contents4")
    inp = build_dxf4(root)
    work = root / "work"
    run_intake(inp, work, "demo-contents", knowledge=PROPOSED_FONT_TABLE)
    write_structure(inp, work)
    (work / "structure" / f"{REL}.grids.json").write_text(
        json.dumps(grids_doc_unlabelled_line()), encoding="utf-8"
    )
    return root


def test_e10a_an_unlabelled_grid_line_nearer_than_the_labelled_axis_is_reported(base4):
    d = contents(
        base4 / "work",
        REL,
        input_dir=base4 / "input",
        sheet="model#02",
        outline_layers=["U-CAP"],
        circle_layers=[PILE],
    )
    assert validate("contents", d) == []
    by_centre = {tuple(o["centre"]): o["axes"] for o in d["outlines"]}
    assert by_centre[(100000.0, 18000.0)] == [  # exactly on the unlabelled line, 7000 from B
        {
            "group_id": "V001",
            "family_id": "F001",
            "label": "B",
            "offset": -7000.0,
            "nearest_unlabelled_offset": 0.0,
        }
    ]
    assert by_centre[(110000.0, 25000.0)] == [  # on the labelled axis B: the unlabelled line is not nearer
        {
            "group_id": "V001",
            "family_id": "F001",
            "label": "B",
            "offset": 0.0,
            "nearest_unlabelled_offset": None,
        }
    ]
    assert by_centre[(120000.0, 10000.0)] == [  # on A, 8000 from the line
        {
            "group_id": "V001",
            "family_id": "F001",
            "label": "A",
            "offset": 0.0,
            "nearest_unlabelled_offset": None,
        }
    ]


@pytest.fixture(scope="module")
def base5(tmp_path_factory) -> Path:
    """The E10a set, but both axes of the family carry no label (an empty or font-blocked bubble)."""
    root = tmp_path_factory.mktemp("contents5")
    inp = build_dxf4(root)
    work = root / "work"
    run_intake(inp, work, "demo-contents", knowledge=PROPOSED_FONT_TABLE)
    write_structure(inp, work)
    doc = grids_doc_unlabelled_line()
    for ax in doc["groups"][0]["families"][0]["axes"]:
        ax["label"] = None
    (work / "structure" / f"{REL}.grids.json").write_text(json.dumps(doc), encoding="utf-8")
    return root


def test_e10a_an_unlabelled_line_never_sets_offset_in_a_family_without_labelled_axis(base5):
    d = contents(
        base5 / "work",
        REL,
        input_dir=base5 / "input",
        sheet="model#02",
        outline_layers=["U-CAP"],
        circle_layers=[PILE],
    )
    assert validate("contents", d) == []
    by_centre = {tuple(o["centre"]): o["axes"] for o in d["outlines"]}
    assert by_centre[(100000.0, 18000.0)] == [  # on the line, 7000 from the unlabelled axis at 25000
        {
            "group_id": "V001",
            "family_id": "F001",
            "label": None,
            "offset": -7000.0,
            "nearest_unlabelled_offset": None,
        }
    ]


# --- E10b: `--dims`, the printed dimensions of each rectangular outline ---------------------------------
#
# Own world on model#02 (layers D-CAP, D-DIM, D-PILE; the module world above is not touched). Every cap is
# 1450 x 1150 (long side along x unless said), the default mark radius (3000) is the reach of a dimension:
#   A  (100000, 20000)  a dimension on each pair of edges: both agree
#   B  (110000, 20000)  a dimension of 2150 centred on the long side: disagrees
#   C  (120000, 20000)  axis-to-edge dimensions (one end on an edge, the other on the centre): not attached
#   D  (130000, 20000)  an edge-to-edge dimension 3925 away (beyond the reach) and a centred one of 2902
#                       (over twice the side): neither is attached
#   E  (140000, 20000) and (140000, 22600): one edge-to-edge dimension 725 from both: ambiguous
#   F  (150000, 20000)  typed texts: '1500' over a measured 1450 (disagrees), '1150' on the short
#                       side (agrees)
#   G  (160000, 20000)  a typed text in a legacy font the gate blocks: unusable
#   H  (170000, 20000)  a measured dimension with DIMLFAC 2: prints 2900 and agrees
#   I  block inserted twice: at scale 1 at (110000, 40000) (handle null, agrees) and at scale 2 at
#      (100000, 40000), whose dimension prints the definition's value: unusable
#   J  a mirrored block (xscale -1) with a cap and a dimension both rotated 30 degrees: agrees in the world
#   K  (130000, 40000)  an L-shaped outline with a dimension along its foot: no printed dimensions
#   L  (150000, 40000)  a horizontal dimension whose extension origins are 1400 apart across its direction:
#      measured along its angle (1450), not along the line through its two origins
#   a dimension of cap A on a frozen layer (text 2222): never read
#   an angular dimension (not linear)
DIM_SHEET = "model#02"
D_CAP, D_DIM, D_PILE, D_HIDDEN = "D-CAP", "D-DIM", "D-PILE", "D-HID"
D_BLOCKED = "1450 cöa"
D_STYLE = "VntimeH"
SIZE_LONG, SIZE_SHORT = 1450.0, 1150.0


def build_dxf_dims(base: Path) -> Path:
    root = base / "input"
    (root / "plans").mkdir(parents=True)
    doc = readfile(str(build_set(base, "src.dxf")))
    doc.layers.add(D_CAP)
    doc.layers.add(D_DIM)
    doc.layers.add(D_HIDDEN).freeze()
    doc.styles.add(D_STYLE, font="vntimeh.shx")
    msp = doc.modelspace()

    def cap(cx: float, cy: float, angle: float = 0.0, target: Any = msp) -> None:
        target.add_lwpolyline(
            rect(cx, cy, SIZE_LONG, SIZE_SHORT, angle), close=True, dxfattribs={"layer": D_CAP}
        )

    def dim(
        p1: tuple[float, float],
        p2: tuple[float, float],
        base_at: tuple[float, float],
        angle: float = 0.0,
        text: str = "<>",
        target: Any = msp,
        layer: str = D_DIM,
        **override: Any,
    ) -> None:
        target.add_linear_dim(
            base=base_at,
            p1=p1,
            p2=p2,
            angle=angle,
            text=text,
            dimstyle="Standard",
            override=override or None,
            dxfattribs={"layer": layer},
        ).render()

    hx, hy = SIZE_LONG / 2, SIZE_SHORT / 2  # 725, 575
    # A
    cap(100000, 20000)
    dim((100000 - hx, 20000 - hy), (100000 + hx, 20000 - hy), (100000, 18000))
    dim((100000 + hx, 20000 - hy), (100000 + hx, 20000 + hy), (102000, 20000), angle=90)
    # B: 1075 each side of the centre
    cap(110000, 20000)
    dim((110000 - 1075, 20000), (110000 + 1075, 20000), (110000, 22000))
    # C: from the centre to the right edge, and from the left edge to the centre
    cap(120000, 20000)
    dim((120000, 20000 - hy), (120000 + hx, 20000 - hy), (120000, 18000))
    dim((120000 - hx, 20000 + hy), (120000, 20000 + hy), (120000, 22000))
    # D: beyond the reach, and over twice the side
    cap(130000, 20000)
    dim((130000 - hx, 24500), (130000 + hx, 24500), (130000, 25500))
    dim((130000 - 1451, 20000), (130000 + 1451, 20000), (130000, 18000))
    # E: two equal caps with one dimension between them
    cap(140000, 20000)
    cap(140000, 22600)
    dim((140000 - hx, 21300), (140000 + hx, 21300), (140000, 21300))
    # F: typed numbers
    cap(150000, 20000)
    dim((150000 - hx, 20000 - hy), (150000 + hx, 20000 - hy), (150000, 18000), text="1500")
    dim((150000 + hx, 20000 - hy), (150000 + hx, 20000 + hy), (152000, 20000), angle=90, text="1150")
    # G: a typed text in a legacy font whose encoding is unknown
    cap(160000, 20000)
    dim(
        (160000 - hx, 20000 - hy),
        (160000 + hx, 20000 - hy),
        (160000, 18000),
        text=D_BLOCKED,
        dimtxsty=D_STYLE,
    )
    # H: DIMLFAC 2 on a measured text
    cap(170000, 20000)
    dim((170000 - hx, 20000 - hy), (170000 + hx, 20000 - hy), (170000, 18000), dimlfac=2)
    # I: a block with a cap and a dimension, at scale 1 and at scale 2
    blk = doc.blocks.new("D_UNIT")
    cap(0, 0, target=blk)
    dim((-hx, -hy), (hx, -hy), (0, -1500), target=blk)
    msp.add_blockref("D_UNIT", (110000, 40000))
    msp.add_blockref("D_UNIT", (100000, 40000), dxfattribs={"xscale": 2, "yscale": 2})
    # J: a mirrored block, cap and dimension rotated 30 degrees
    mir = doc.blocks.new("D_MIRROR")
    cap(2000, 500, angle=30, target=mir)
    ux, uy = math.cos(math.radians(30)), math.sin(math.radians(30))
    vx, vy = -uy, ux
    p1 = (2000 - hx * ux - hy * vx, 500 - hx * uy - hy * vy)
    p2 = (2000 + hx * ux - hy * vx, 500 + hx * uy - hy * vy)
    dim(p1, p2, (2000 - 2000 * vx, 500 - 2000 * vy), angle=30, target=mir)
    msp.add_blockref("D_MIRROR", (120000, 40000), dxfattribs={"xscale": -1.0})
    # K: an L-shaped outline with a dimension along its foot
    msp.add_lwpolyline(
        [
            (130000, 40000),
            (131450, 40000),
            (131450, 40650),
            (130550, 40650),
            (130550, 41350),
            (130000, 41350),
        ],
        close=True,
        dxfattribs={"layer": D_CAP},
    )
    dim((130000, 40000), (131450, 40000), (130000, 39000))
    # L: the extension origins are 1400 apart across the direction of the dimension
    cap(150000, 40000)
    dim((150000 - hx, 40000 - hy - 100), (150000 + hx, 40000 - hy - 1500), (150000, 37000))
    # a dimension of cap A on a frozen layer
    dim((100000 - hx, 20000 - hy), (100000 + hx, 20000 - hy), (100000, 17000), text="2222", layer=D_HIDDEN)
    # an angular dimension: not linear
    msp.add_angular_dim_2l(
        base=(140500, 40500),
        line1=((140000, 40000), (141000, 40000)),
        line2=((140000, 40000), (141000, 41000)),
        dimstyle="EZ_CURVED",
        dxfattribs={"layer": D_DIM},
    ).render()
    doc.saveas(root / REL)
    return root


@pytest.fixture(scope="module")
def base_dims(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("contents-dims")
    inp = build_dxf_dims(root)
    work = root / "work"
    run_intake(inp, work, "demo-contents", knowledge=PROPOSED_FONT_TABLE)
    write_structure(inp, work)
    return root


def call_dims(base: Path, **kw: Any) -> dict[str, Any]:
    kw.setdefault("sheet", DIM_SHEET)
    kw.setdefault("outline_layers", [D_CAP])
    kw.setdefault("circle_layers", [D_PILE])
    return contents(base / "work", REL, input_dir=base / "input", **kw)


@pytest.fixture(scope="module")
def dims_off(base_dims) -> dict[str, Any]:
    return call_dims(base_dims)


@pytest.fixture(scope="module")
def dims_on(base_dims) -> dict[str, Any]:
    return call_dims(base_dims, dims=True)


def cap_at(d: dict[str, Any], x: float, y: float, long: float = SIZE_LONG) -> dict[str, Any]:
    found = [o for o in d["outlines"] if o["long"] == long and math.dist(o["centre"], (x, y)) < 1]
    assert len(found) == 1, (x, y, [(o["long"], o["centre"]) for o in d["outlines"]])
    return found[0]


def shown(o: dict[str, Any]) -> list[tuple[str, str, float, bool]]:
    return [(p["side"], p["how"], p["printed"], p["agrees"]) for p in o["printed_dims"]]


def test_without_dims_the_document_is_unchanged(dims_off, dims_on):
    """Off: no new key anywhere. On: the same document plus the new keys and the new warnings."""
    assert "dims" not in dims_off and "dims" not in dims_off["query"]
    assert all("printed_dims" not in o for o in dims_off["outlines"])
    assert all("printed_dims" not in r for r in dims_off["summary"])
    assert not any("printed dimensions" in w for w in dims_off["warnings"])
    assert dims_on["query"]["dims"] is True  # the flag reaches the document
    stripped = json.loads(json.dumps(dims_on))
    del stripped["dims"], stripped["query"]["dims"]
    for o in stripped["outlines"]:
        del o["printed_dims"]
    for r in stripped["summary"]:
        del r["printed_dims"]
    stripped["warnings"] = [w for w in stripped["warnings"] if not w.startswith("printed dimensions")]
    assert stripped == dims_off


def test_saved_documents_without_dims_still_validate(dims_off, dims_on):
    """Additive schema: a document of an older run (no dims keys) is valid, so is one with them."""
    assert validate("contents", dims_off) == []
    assert validate("contents", dims_on) == []
    older = json.loads(json.dumps(dims_on))
    del older["dims"], older["query"]["dims"]
    for o in older["outlines"]:
        del o["printed_dims"]
    for r in older["summary"]:
        del r["printed_dims"]
    assert validate("contents", older) == []
    flagged = json.loads(json.dumps(dims_off))
    flagged["query"]["dims"] = True  # a key the schema must know
    assert validate("contents", flagged) == []
    path = Path(__file__).resolve().parent.parent / "schemas" / "examples" / "contents.example.json"
    example = json.loads(path.read_text(encoding="utf-8"))
    assert validate("contents", example) == []


def test_dimension_on_both_edges_agrees(dims_on):
    a = cap_at(dims_on, 100000, 20000)
    assert shown(a) == [("long", "edges", 1450.0, True), ("short", "edges", 1150.0, True)]
    first = a["printed_dims"][0]
    assert set(first) == {"handle", "entry_id", "text", "printed", "side", "how", "agrees"}
    assert first["entry_id"] is None and first["text"] == "<>" and first["handle"]


def test_centred_longer_dimension_disagrees_and_warns(dims_on):
    b = cap_at(dims_on, 110000, 20000)
    assert shown(b) == [("long", "centred", 2150.0, False)]
    (warning,) = [w for w in dims_on["warnings"] if w.startswith("printed dimensions disagree")]
    assert warning.startswith("printed dimensions disagree with the linework on ")
    assert f"{b['id']} (long 1450 vs printed 2150)" in warning
    f = cap_at(dims_on, 150000, 20000)
    assert f"{f['id']} (long 1450 vs printed 1500)" in warning
    assert "on 2 outline(s)" in warning


def test_axis_to_edge_dimension_is_not_attached(dims_on):
    assert cap_at(dims_on, 120000, 20000)["printed_dims"] == []


def _bare_dim(a: float, b: float) -> DimRead:
    """A measured linear dimension along x, `a` to `b`, 800 below a 1450 x 1150 rectangle at the origin."""
    row = {"handle": "H1", "text": "<>", "text_rule": "measured", "measured": b - a, "status": "ok"}
    return DimRead("model", True, (a, -575.0 - 800.0), (b, -575.0 - 800.0), (1.0, 0.0), row, 1.0, False)


def test_one_end_on_an_edge_never_attaches_and_off_centre_does_not_either():
    ring = [(-725.0, -575.0), (725.0, -575.0), (725.0, 575.0), (-725.0, 575.0)]
    item = _Item("O1", "outline", "L", "model#01", (0.0, 0.0), None, [], short=1150.0, long=1450.0, angle=0.0)
    item.rectangle = True
    kept = [item]
    cases = {
        "edges": ((-725.0, 725.0), 1),
        "centred": ((-1000.0, 1000.0), 1),
        "one end on an edge, the other within 2 tol of the far edge": ((-725.0, 726.8), 0),
        "off centre beyond tol": ((-625.0, 425.0), 0),
    }
    for name, ((a, b), attached) in cases.items():
        rows, counts = _attach_dims([_bare_dim(a, b)], kept, [ring], "model", 1.0, 3000.0)
        assert counts["attached"] == attached, name
        assert bool(rows.get(0)) == bool(attached), name


def _outline(
    oid: str, cx: float, cy: float, long: float = 1450.0, short: float = 1150.0
) -> tuple[_Item, Any]:
    """A rectangular outline centred on (cx, cy), long side along x, with its ring."""
    item = _Item(oid, "outline", "L", "model#01", (cx, cy), None, [], short=short, long=long, angle=0.0)
    item.rectangle = True
    hx, hy = long / 2, short / 2
    return item, [(cx - hx, cy - hy), (cx + hx, cy - hy), (cx + hx, cy + hy), (cx - hx, cy + hy)]


def _free_dim(
    p1: tuple[float, float],
    p2: tuple[float, float],
    measured: float,
    *,
    u: tuple[float, float] = (1.0, 0.0),
    status: str = "ok",
    factor: float = 1.0,
) -> DimRead:
    """A measured linear dimension with its extension origins and direction given."""
    row = {"handle": "H1", "text": "<>", "text_rule": "measured", "measured": measured, "status": status}
    return DimRead("model", True, p1, p2, u, row, factor, False)


def _attach(dim: DimRead, *outlines: tuple[_Item, Any], reach: float = 3000.0):
    return _attach_dims([dim], [o[0] for o in outlines], [o[1] for o in outlines], "model", 1.0, reach)


def test_a_measured_value_not_compared_is_unusable():
    """A group-42 disagreement marks the row `not_compared`: its measured value is not used."""
    dim = _free_dim((-725.0, -1375.0), (725.0, -1375.0), 1450.0, status="not_compared")
    rows, counts = _attach(dim, _outline("O1", 0.0, 0.0))
    assert (counts["unusable"], counts["attached"]) == (1, 0) and not rows


@pytest.mark.parametrize("factor", [0.0, -1.0])
def test_a_dimlfac_that_is_not_positive_is_unusable(factor):
    dim = _free_dim((-725.0, -1375.0), (725.0, -1375.0), 1450.0, factor=factor)
    rows, counts = _attach(dim, _outline("O1", 0.0, 0.0))
    assert (counts["unusable"], counts["attached"]) == (1, 0) and not rows


@pytest.mark.parametrize(("degrees", "attached"), [(2.0, 0), (0.5, 1)])
def test_a_dimension_is_parallel_to_a_side_within_one_degree(degrees, attached):
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    u, n = (c, s), (-s, c)
    p1 = (-1000 * u[0] - 1375 * n[0], -1000 * u[1] - 1375 * n[1])
    p2 = (1000 * u[0] - 1375 * n[0], 1000 * u[1] - 1375 * n[1])
    rows, counts = _attach(_free_dim(p1, p2, 2000.0, u=u), _outline("O1", 0.0, 0.0))
    assert counts["attached"] == attached
    if attached:
        assert rows[0][0]["how"] == "centred" and rows[0][0]["side"] == "long"


def test_the_gap_is_the_largest_of_the_two_ends():
    """One extension origin 100 off the outline, the other 3500: beyond a reach of 3000."""
    dim = _free_dim((-725.0, -675.0), (725.0, -4075.0), 1450.0)
    rows, counts = _attach(dim, _outline("O1", 0.0, 0.0))
    assert counts["attached"] == 0 and not rows


def test_edges_win_over_a_nearer_centred_outline():
    """X (1450 x 1150 at the origin) and Y (2000 x 1150 centred at (0, -3000)); the dimension spans X's long
    side, so it is `edges` on X (gap 1425) and `centred` on Y (gap 425)."""
    near = _free_dim((-725.0, -2000.0), (725.0, -2000.0), 1450.0)
    rows, counts = _attach(near, _outline("X", 0.0, 0.0), _outline("Y", 0.0, -3000.0, long=2000.0))
    assert counts["attached"] == 1 and set(rows) == {0} and rows[0][0]["how"] == "edges"


def test_an_edges_best_is_not_ambiguous_with_a_centred_runner_up_at_the_same_gap():
    level = _free_dim((-725.0, -1500.0), (725.0, -1500.0), 1450.0)  # gap 925 to both
    rows, counts = _attach(level, _outline("X", 0.0, 0.0), _outline("Y", 0.0, -3000.0, long=2000.0))
    assert counts["attached"] == 1 and counts["ambiguous"] == 0
    assert set(rows) == {0} and rows[0][0]["how"] == "edges"


def test_agreement_is_within_the_tolerance_times_dimlfac():
    dim = _free_dim((-725.0, -1375.0), (725.0, -1375.0), 1450.75, factor=2.0)  # prints 2901.5 against 2900
    rows, _ = _attach(dim, _outline("O1", 0.0, 0.0))
    assert rows[0][0]["printed"] == 2901.5 and rows[0][0]["agrees"] is True


def test_a_centred_dimension_exactly_twice_the_side_attaches():
    dim = _free_dim((-1450.0, -1375.0), (1450.0, -1375.0), 2900.0)
    rows, counts = _attach(dim, _outline("O1", 0.0, 0.0))
    assert counts["attached"] == 1 and rows[0][0]["how"] == "centred"


def test_beyond_radius_or_twice_the_side_is_not_attached(base_dims, dims_on):
    assert cap_at(dims_on, 130000, 20000)["printed_dims"] == []
    wide = call_dims(base_dims, dims=True, mark_radius=4000)  # the reach is the resolved mark radius
    assert shown(cap_at(wide, 130000, 20000)) == [("long", "edges", 1450.0, True)]
    assert cap_at(wide, 130000, 20000)["printed_dims"][0]["how"] == "edges"  # the 2902 one stays out


def test_equal_candidates_stay_ambiguous(dims_on):
    assert cap_at(dims_on, 140000, 20000)["printed_dims"] == []
    assert cap_at(dims_on, 140000, 22600)["printed_dims"] == []
    assert dims_on["dims"]["ambiguous"] == 1


def test_typed_number_is_printed(dims_on):
    f = cap_at(dims_on, 150000, 20000)
    assert shown(f) == [("long", "edges", 1500.0, False), ("short", "edges", 1150.0, True)]
    typed = f["printed_dims"][0]
    assert typed["text"] == "1500" and typed["entry_id"] is not None and typed["entry_id"].startswith("T")


def test_blocked_font_override_unusable(base_dims, dims_on):
    assert cap_at(dims_on, 160000, 20000)["printed_dims"] == []
    # the text is not a number whether or not the gate ran, so the row itself shows that the gate was reached
    read = read_geometry(
        base_dims / "work", REL, sheet=[DIM_SHEET], input_dir=base_dims / "input", dimensions=True
    )
    (blocked,) = [d.row for d in read.dims[DIM_SHEET] if d.row["text"] == D_BLOCKED]
    assert blocked["status"] == "not_compared"
    assert blocked["text_entry"]["meaning"] == "blocked"


def test_a_dimension_on_a_hidden_layer_is_ignored(dims_on):
    a = cap_at(dims_on, 100000, 20000)
    assert shown(a) == [("long", "edges", 1450.0, True), ("short", "edges", 1150.0, True)]
    assert all(p["text"] != "2222" for o in dims_on["outlines"] for p in o["printed_dims"])
    assert dims_on["dims"]["on_sheet"] == 18  # the frozen one is not among them


def test_dimtype_0_measures_along_its_angle_not_along_its_extension_origins(dims_on):
    ell = cap_at(dims_on, 150000, 40000)
    assert shown(ell) == [("long", "edges", 1450.0, True)]


def test_dimlfac_scales_the_comparison(dims_on):
    h = cap_at(dims_on, 170000, 20000)
    assert shown(h) == [("long", "edges", 2900.0, True)]  # measured 1450 x DIMLFAC 2 against 1450 x 2


def test_scaled_insert_unusable(dims_on):
    scaled = cap_at(dims_on, 100000, 40000, long=2900.0)
    assert scaled["printed_dims"] == []
    plain = cap_at(dims_on, 110000, 40000)
    assert shown(plain) == [("long", "edges", 1450.0, True)] and plain["printed_dims"][0]["handle"] is None


def test_mirrored_insert_attaches_in_world(dims_on):
    (j,) = [o for o in dims_on["outlines"] if o["angle"] == pytest.approx(150.0)]
    assert shown(j) == [("long", "edges", 1450.0, True)]


def test_non_rectangle_gets_no_dims(dims_on):
    (k,) = [o for o in dims_on["outlines"] if math.dist(o["centre"], (130725, 40675)) < 1]
    assert k["angle"] is None and k["printed_dims"] == []
    (warning,) = [w for w in dims_on["warnings"] if w.startswith("printed dimensions:")]
    assert "1 outline(s)" in warning and "not rectangle" in warning and k["id"] in warning


def test_summary_counts_and_values(dims_on):
    assert dims_on["dims"] == {"on_sheet": 18, "attached": 9, "ambiguous": 1, "unusable": 2, "not_linear": 1}
    (row,) = [r for r in dims_on["summary"] if (r["short"], r["long"]) == (SIZE_SHORT, SIZE_LONG)]
    assert row["count"] == 12
    assert row["printed_dims"] == {
        "agree": 5,
        "disagree": 2,
        "none": 5,
        "values": [
            {"side": "long", "printed": 1450.0, "count": 4},
            {"side": "long", "printed": 1500.0, "count": 1},
            {"side": "long", "printed": 2150.0, "count": 1},
            {"side": "long", "printed": 2900.0, "count": 1},
            {"side": "short", "printed": 1150.0, "count": 2},
        ],
    }
    for r in dims_on["summary"]:
        pd = r["printed_dims"]
        assert pd["agree"] + pd["disagree"] + pd["none"] == r["count"]


def test_schema_valid(dims_on):
    assert validate("contents", dims_on) == []
    bad = json.loads(json.dumps(dims_on))
    cap_at(bad, 100000, 20000)["printed_dims"][0]["side"] = "middle"
    assert validate("contents", bad)
    bad = json.loads(json.dumps(dims_on))
    cap_at(bad, 100000, 20000)["printed_dims"][0]["extra"] = 1
    assert validate("contents", bad)
    bad = json.loads(json.dumps(dims_on))
    bad["dims"]["attached"] = -1
    assert validate("contents", bad)


def test_cli_dims_flag(base_dims, capsys):
    argv = ["contents", str(base_dims / "work"), REL, "--sheet", DIM_SHEET, "--outline-layer", D_CAP,
            "--circle-layer", D_PILE, "--input-dir", str(base_dims / "input")]  # fmt: skip
    assert main(argv) == 0
    off = json.loads(capsys.readouterr().out)
    assert "dims" not in off and "dims" not in off["query"]
    assert main([*argv, "--dims"]) == 0
    on = json.loads(capsys.readouterr().out)
    assert on["query"]["dims"] is True and on["dims"]["on_sheet"] == 18
    assert main(["contents", "--help"]) == 0
    help_text = " ".join(capsys.readouterr().out.split())
    assert "--dims" in help_text and "stub" in help_text and "outline layer" in help_text


# --- E10b fix 2: the pile-spacing guard (D1), a rotated block copy without group 50 (M2), unlinked texts (m1)


def test_a_dimension_ending_on_two_symbol_centres_is_not_attached():
    """D1: a two-pile cap 2900 x 1150 and a dimension of 1800 between the pile centres is a pile spacing,
    not the size of the cap: with the symbols it is not attached, without them it attaches `centred`."""
    cap = _outline("O1", 0.0, 0.0, long=2900.0, short=1150.0)
    dim = _free_dim((-900.0, -1375.0), (900.0, -1375.0), 1800.0)
    rows, counts = _attach_dims([dim], [cap[0]], [cap[1]], "model", 1.0, 3000.0)
    assert [(r["how"], r["agrees"]) for r in rows[0]] == [("centred", False)] and counts["attached"] == 1
    for symbols in (
        [[(-900.0, 0.0), (900.0, 0.0)]],
        [[(-900.0, 300.0), (900.0, -250.0)]],
    ):  # u-projection only
        rows, counts = _attach_dims([dim], [cap[0]], [cap[1]], "model", 1.0, 3000.0, symbols)
        assert rows == {}
        assert counts == {"on_sheet": 1, "attached": 0, "ambiguous": 0, "unusable": 0, "not_linear": 0}


def test_the_pile_spacing_guard_does_not_apply_to_an_edges_dimension():
    """m4b: the guard is for `centred` only: a dimension on the cap edges stays attached even when both
    ends lie on symbol centres."""
    cap = _outline("O1", 0.0, 0.0, long=2900.0, short=1150.0)
    dim = _free_dim((-1450.0, -1375.0), (1450.0, -1375.0), 2900.0)
    symbols = [[(-1450.0, 0.0), (1450.0, 0.0)]]
    rows, counts = _attach_dims([dim], [cap[0]], [cap[1]], "model", 1.0, 3000.0, symbols)
    assert [(r["how"], r["agrees"]) for r in rows[0]] == [("edges", True)] and counts["attached"] == 1


def test_the_pile_spacing_guard_needs_both_ends_on_a_centre_of_that_outline():
    cap = _outline("O1", 0.0, 0.0, long=2900.0, short=1150.0)
    dim = _free_dim((-900.0, -1375.0), (900.0, -1375.0), 1800.0)

    def attached(symbols: list[list[tuple[float, float]]], tol: float = 1.0) -> int:
        rows, _ = _attach_dims([dim], [cap[0]], [cap[1]], "model", tol, 3000.0, symbols)
        return len(rows.get(0, []))

    assert attached([[(-900.0, 0.0), (300.0, 0.0)]]) == 1  # only the left end is on a centre
    assert attached([[(-900.0, 0.0), (903.0, 0.0)]]) == 1  # the right end is 3 off, tol 1
    assert attached([[(-900.0, 0.0), (903.0, 0.0)]], tol=3.5) == 0  # within tol
    assert attached([[(-900.0, 0.0)]]) == 1 and attached([[]]) == 1


def test_the_pile_spacing_guard_uses_only_the_symbols_inside_the_outline():
    far = _outline("O2", 0.0, 9000.0, long=2900.0, short=1150.0)  # beyond the reach of the dimension
    cap = _outline("O1", 0.0, 0.0, long=2900.0, short=1150.0)
    dim = _free_dim((-900.0, -1375.0), (900.0, -1375.0), 1800.0)
    ring_of_piles = [(-900.0, 9000.0), (900.0, 9000.0)]
    rows, counts = _attach_dims(
        [dim], [cap[0], far[0]], [cap[1], far[1]], "model", 1.0, 3000.0, [[], ring_of_piles]
    )
    assert [r["how"] for r in rows[0]] == ["centred"] and counts["attached"] == 1


def build_dxf_piles(base: Path) -> Path:
    """Own world on model#02: caps 2900 x 1150 with a dimension of 1800 centred on the long side.
    P (100000, 20000): two piles 1800 apart (D-PILE) at the ends of the dimension: a pile spacing.
    R (110000, 20000): no pile, the same dimension: attaches `centred`.
    S (110000, 28000): two piles at the same x as the ends of R's dimension, in another outline."""
    root = base / "input"
    (root / "plans").mkdir(parents=True)
    doc = readfile(str(build_set(base, "src.dxf")))
    for name in (D_CAP, D_DIM, D_PILE):
        doc.layers.add(name)
    msp = doc.modelspace()
    for cx, cy in ((100000, 20000), (110000, 20000), (110000, 28000)):
        msp.add_lwpolyline(rect(cx, cy, 2900, 1150), close=True, dxfattribs={"layer": D_CAP})
    for cx, cy in ((100000, 20000), (110000, 28000)):
        for dx in (-900, 900):
            msp.add_circle((cx + dx, cy), 300, dxfattribs={"layer": D_PILE})
    for cx in (100000, 110000):
        msp.add_linear_dim(
            base=(cx, 18000),
            p1=(cx - 900, 19425),
            p2=(cx + 900, 19425),
            dimstyle="Standard",
            dxfattribs={"layer": D_DIM},
        ).render()
    doc.saveas(root / REL)
    return root


@pytest.fixture(scope="module")
def base_piles(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("contents-piles")
    inp = build_dxf_piles(root)
    work = root / "work"
    run_intake(inp, work, "demo-contents", knowledge=PROPOSED_FONT_TABLE)
    write_structure(inp, work)
    return root


def test_pile_spacing_is_not_attached_with_the_circle_layer_and_is_centred_without(base_piles):
    with_piles = call_dims(base_piles, dims=True)
    p = cap_at(with_piles, 100000, 20000, long=2900.0)
    assert p["printed_dims"] == [] and p["symbols"] == 2
    r = cap_at(with_piles, 110000, 20000, long=2900.0)  # piles of S lie at the same x: not its own
    assert shown(r) == [("long", "centred", 1800.0, False)]
    assert with_piles["dims"]["attached"] == 1 and with_piles["dims"]["on_sheet"] == 2
    without = call_dims(base_piles, dims=True, circle_layers=["D-NONE"])
    p = cap_at(without, 100000, 20000, long=2900.0)
    assert shown(p) == [("long", "centred", 1800.0, False)] and p["symbols"] == 0
    assert without["dims"]["attached"] == 2
    assert validate("contents", with_piles) == [] and validate("contents", without) == []


def test_help_and_schema_say_a_pile_spacing_may_attach_centred_without_the_pile_layer(capsys):
    assert main(["contents", "--help"]) == 0
    help_text = " ".join(capsys.readouterr().out.split())
    assert "pile spacing" in help_text and "centred" in help_text
    schema = (Path(__file__).parent.parent / "schemas" / "contents.schema.json").read_text()
    assert "pile spacing" in schema


def test_a_dimension_text_with_no_text_index_entry_is_warned(base_dims, monkeypatch):
    """m1: the font gate cannot see a text without a text-index entry, so the run says how many."""
    clean = call_dims(base_dims, dims=True)
    assert not any("no text-index entry" in w for w in clean["warnings"])
    real = _TextLinks.link

    def link(self: Any, space: str, block_path: Any, text: str, at: Any) -> Any:
        return real(self, space, block_path, "no such text" if text == "1500" else text, at)

    monkeypatch.setattr(_TextLinks, "link", link)
    warned = call_dims(base_dims, dims=True)
    expected = (
        f"{REL}: 1 dimension text(s) have no text-index entry (text_entry null): "
        "the legacy-font gate was not applied to them"
    )
    assert [w for w in warned["warnings"] if "no text-index entry" in w] == [expected]
    off = call_dims(base_dims)
    assert not any("no text-index entry" in w for w in off["warnings"])


def build_dxf_rotated(base: Path) -> Path:
    """Own world on model#02: block cap + dimension whose dimension stores no group 50, inserted rotated.
    A (100000, 20000) rotation 90; B (110000, 20000) rotation 90 scale 2; C (120000, 20000) rotation 90 with
    a dimension whose definition points lie on one line; D (130000, 20000) mirrored, rotated 30;
    E (140000, 20000) the collinear block unrotated."""
    root = base / "input"
    (root / "plans").mkdir(parents=True)
    doc = readfile(str(build_set(base, "src.dxf")))
    for name in (D_CAP, D_DIM):
        doc.layers.add(name)
    msp = doc.modelspace()
    for name, line in (("R_UNIT", -1500), ("R_LINE", -575)):
        blk = doc.blocks.new(name)
        blk.add_lwpolyline(rect(0, 0, 1450, 1150), close=True, dxfattribs={"layer": D_CAP})
        dim = blk.add_linear_dim(
            base=(0, line), p1=(-725, -575), p2=(725, -575), dimstyle="Standard", dxfattribs={"layer": D_DIM}
        )
        dim.render()
    for name, at, attribs in (
        ("R_UNIT", (100000, 20000), {"rotation": 90}),
        ("R_UNIT", (110000, 20000), {"rotation": 90, "xscale": 2, "yscale": 2}),
        ("R_LINE", (120000, 20000), {"rotation": 90}),
        ("R_UNIT", (130000, 20000), {"rotation": 30, "xscale": -1}),
        ("R_LINE", (140000, 20000), {}),
    ):
        msp.add_blockref(name, at, dxfattribs=attribs)
    doc.saveas(root / REL)
    # ezdxf always writes group 50 for a linear dimension: take it out of the saved file
    saved = (root / REL).read_bytes()
    stripped = re.sub(
        rb"(\r?\n) 50\r?\n[-0-9.]+\r?\n100\r?\nAcDbRotatedDimension",
        rb"\g<1>100\g<1>AcDbRotatedDimension",
        saved,
    )
    assert stripped.count(b"AcDbRotatedDimension") == saved.count(b"AcDbRotatedDimension") >= 2
    assert len(stripped) < len(saved)
    (root / REL).write_bytes(stripped)
    return root


@pytest.fixture(scope="module")
def base_rotated(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("contents-rotated")
    inp = build_dxf_rotated(root)
    work = root / "work"
    run_intake(inp, work, "demo-contents", knowledge=PROPOSED_FONT_TABLE)
    write_structure(inp, work)
    return root


def test_a_rotated_block_copy_without_group_50_attaches(base_rotated):
    """M2/D2: the copy's direction is rebuilt from the linear map of the definition's points."""
    doc = call_dims(base_rotated, dims=True)
    a = cap_at(doc, 100000, 20000)
    assert shown(a) == [("long", "edges", 1450.0, True)] and a["angle"] == pytest.approx(90.0)
    (d,) = [o for o in doc["outlines"] if math.dist(o["centre"], (130000, 20000)) < 1]
    assert [(p["how"], p["agrees"]) for p in d["printed_dims"]] == [("edges", True)]  # mirrored and rotated
    (e,) = [o for o in doc["outlines"] if math.dist(o["centre"], (140000, 20000)) < 1]
    assert shown(cap_at(doc, 140000, 20000)) == [("long", "edges", 1450.0, True)]  # collinear, not rotated
    assert e["printed_dims"]
    assert doc["dims"]["on_sheet"] == 5


def test_a_scaled_or_collinear_rotated_block_copy_without_group_50_stays_unusable(base_rotated):
    doc = call_dims(base_rotated, dims=True)
    scaled = cap_at(doc, 110000, 20000, long=2900.0)
    assert scaled["printed_dims"] == []  # killed by the scale, not by a missing angle
    collinear = cap_at(doc, 120000, 20000)
    assert collinear["printed_dims"] == []
    assert doc["dims"]["unusable"] == 2 and doc["dims"]["attached"] == 3


def test_the_rebuilt_direction_is_a_unit_vector(base_rotated):
    read = read_geometry(
        base_rotated / "work", REL, sheet=[DIM_SHEET], input_dir=base_rotated / "input", dimensions=True
    )
    by_x = {round(d.p1[0] / 10000): d for d in read.dims[DIM_SHEET] if d.p1 is not None}
    scaled = by_x[11]
    assert scaled.copy_differs and scaled.u == pytest.approx((0.0, 1.0), abs=1e-9)
    for d in read.dims[DIM_SHEET]:
        assert d.u is not None and math.hypot(*d.u) == pytest.approx(1.0)


def build_dxf_diagonal(base: Path) -> Path:
    """Own world on model#02: a block with a collinear diagonal dimension (no group 50, the dimension line
    through one extension origin), inserted at rotation 0, 90, 180 and 37."""
    root = base / "input"
    (root / "plans").mkdir(parents=True)
    doc = readfile(str(build_set(base, "src.dxf")))
    doc.layers.add(D_DIM)
    blk = doc.blocks.new("R_DIAG")
    dim = blk.add_linear_dim(
        base=(500, 0), p1=(0, 0), p2=(1000, 1000), dimstyle="Standard", dxfattribs={"layer": D_DIM}
    )
    dim.render()
    msp = doc.modelspace()
    for rotation in (0, 90, 180, 37):
        msp.add_blockref("R_DIAG", (150000 + rotation * 100, 20000), dxfattribs={"rotation": rotation})
    doc.saveas(root / REL)
    saved = (root / REL).read_bytes()
    stripped = re.sub(
        rb"(\r?\n) 50\r?\n[-0-9.]+\r?\n100\r?\nAcDbRotatedDimension",
        rb"\g<1>100\g<1>AcDbRotatedDimension",
        saved,
    )
    assert len(stripped) < len(saved)
    (root / REL).write_bytes(stripped)
    return root


def test_a_collinear_block_copy_without_group_50_attaches_only_when_it_is_not_turned(tmp_path):
    """m1/D1: with no rebuilt direction the copy is used only if its p1 to p2 is plus or minus the
    definition's: 0 and 180 degrees keep it, 90 and 37 degrees (a wrong axis otherwise) make it unusable."""
    inp = build_dxf_diagonal(tmp_path)
    work = tmp_path / "work"
    run_intake(inp, work, "demo-contents", knowledge=PROPOSED_FONT_TABLE)
    write_structure(inp, work)
    read = read_geometry(work, REL, sheet=[DIM_SHEET], input_dir=inp, dimensions=True)
    by_turn = {round((d.p1[0] - 150000) / 100): d.copy_differs for d in read.dims[DIM_SHEET] if d.p1}
    assert len(read.dims[DIM_SHEET]) == 4
    assert by_turn == {0: False, 90: True, 180: False, 37: True}
