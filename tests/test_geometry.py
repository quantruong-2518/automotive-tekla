"""geometry: `harness geometry`, circles and closed outlines of one drawing, grouped by size.

The world is `_dxf_fixtures.build_set` (sheet 1 = model#01 at x 0..84100, sheet 2 = model#02 from x 90000,
paper sheet Plot#01) plus, invented here: piles (circles) loose, in a block and in a 2-level block with
layer 0, pile caps (closed LWPOLYLINEs, one rotated), an open polyline, a polyline closed by repeating its
first vertex, loose LINEs, and entities on a frozen and on an off layer."""

from __future__ import annotations

import json
import math
import re
import shutil
from pathlib import Path
from typing import Any

import pytest
from ezdxf.filemanagement import readfile

from _callout_fixtures import PROPOSED_FONT_TABLE, REL, write_structure
from _dxf_fixtures import build_set
from tekla_harness.cli import main
from tekla_harness.geometry import geometry, read_geometry
from tekla_harness.intake import run_intake
from tekla_harness.schemas import validate
from tekla_harness.sheet_text import ReaderError

PILE = "S-PILE"
CAP = "S-CAP"
HOST = "S-HOST"
FROZEN = "S-FROZEN"
OFF = "S-OFF"
MIR = "S-MIR"
FZINS = "S-FZINS"
OFFINS = "S-OFFINS"


def rect(cx: float, cy: float, long: float, short: float, angle: float = 0.0) -> list[tuple[float, float]]:
    """Corners of a rectangle whose long side runs along `angle` degrees."""
    a = math.radians(angle)
    ux, uy = math.cos(a), math.sin(a)
    vx, vy = -uy, ux
    pts = []
    for s, t in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        pts.append((cx + s * long / 2 * ux + t * short / 2 * vx, cy + s * long / 2 * uy + t * short / 2 * vy))
    return pts


def build_geometry_dxf(base: Path) -> Path:
    root = base / "input"
    (root / "plans").mkdir(parents=True)
    doc = readfile(str(build_set(base, "src.dxf")))
    for name in (PILE, CAP, HOST, FROZEN, OFF, MIR):
        doc.layers.add(name)
    doc.layers.get(FROZEN).freeze()
    doc.layers.get(OFF).off()
    msp = doc.modelspace()
    at = {"layer": PILE}
    # sheet 1: piles; the third is a drawn duplicate of the first (0.2 apart)
    msp.add_circle((10000, 10000), 150, dxfattribs=at)
    msp.add_circle((10000.2, 10000), 150, dxfattribs=at)
    msp.add_circle((12000, 10000), 150, dxfattribs=at)
    msp.add_circle((14000, 10000), 200, dxfattribs=at)
    # a pile in a block whose circle is on layer 0, the INSERT on the pile layer
    blk = doc.blocks.new("PILE_BLK")
    blk.add_circle((0, 0), 150, dxfattribs={"layer": "0"})
    msp.add_blockref("PILE_BLK", (20000, 10000), dxfattribs={"layer": PILE})
    # two levels: layer 0 circle inside a block inside a block; the outer INSERT sets the layer
    inner = doc.blocks.new("PILE_IN")
    inner.add_circle((0, 0), 150, dxfattribs={"layer": "0"})
    outer = doc.blocks.new("PILE_OUT")
    outer.add_blockref("PILE_IN", (0, 0), dxfattribs={"layer": "0"})
    msp.add_blockref("PILE_OUT", (30000, 10000), dxfattribs={"layer": HOST})
    # pile caps: 1700x1700, an unrotated and a rotated 800x1700, an open polyline, a first==last one
    cap = {"layer": CAP}
    msp.add_lwpolyline(rect(40000, 20000, 1700, 1700), close=True, dxfattribs=cap)
    msp.add_lwpolyline(rect(42000, 20000, 1700, 800), close=True, dxfattribs=cap)
    msp.add_lwpolyline(rect(44000, 20000, 1700, 800, 30), close=True, dxfattribs=cap)
    msp.add_lwpolyline([(50000, 20000), (51000, 20000), (51000, 21000)], dxfattribs=cap)
    sq = [(60000, 20000), (61000, 20000), (61000, 21000), (60000, 21000), (60000, 20000)]
    msp.add_lwpolyline(sq, dxfattribs=cap)
    msp.add_line((52000, 25000), (53000, 25000), dxfattribs=cap)
    msp.add_line((52000, 26000), (53000, 26000), dxfattribs=cap)
    # hidden layers
    msp.add_circle((15000, 15000), 150, dxfattribs={"layer": FROZEN})
    msp.add_line((15000, 16000), (16000, 16000), dxfattribs={"layer": OFF})
    # a mirrored INSERT (xscale -1): its virtual copies have extrusion (0, 0, -1), coordinates in OCS
    mir = doc.blocks.new("MIRROR_BLK")
    mir.add_circle((100, 50), 150, dxfattribs={"layer": MIR})
    mir.add_lwpolyline(
        [(1000, 100), (2800, 100), (2800, 900), (1000, 900)], close=True, dxfattribs={"layer": MIR}
    )
    msp.add_blockref("MIRROR_BLK", (70000, 10000), dxfattribs={"xscale": -1.0})
    # sheet 2 (x from 90000)
    msp.add_circle((100000, 10000), 150, dxfattribs=at)
    msp.add_lwpolyline(rect(105000, 20000, 1700, 1700), close=True, dxfattribs=cap)
    add_review_cases(doc, msp)
    doc.saveas(root / REL)
    return root


def add_review_cases(doc: Any, msp: Any) -> None:
    """One layer per case of the T21 review (all on sheet 1, y 30000..40000, unless stated)."""
    for name in (FZINS, OFFINS):
        doc.layers.add(name)
    doc.layers.get(FZINS).freeze()
    doc.layers.get(OFFINS).off()
    # C1: a block inserted on a frozen layer hides its content whatever the content's layer
    b = doc.blocks.new("B_FZ")
    b.add_circle((0, 0), 150, dxfattribs={"layer": "S-FZPILE"})
    msp.add_blockref("B_FZ", (10000, 30000), dxfattribs={"layer": FZINS})
    inner = doc.blocks.new("B_FZ_IN")
    inner.add_circle((0, 0), 150, dxfattribs={"layer": "S-NEST"})
    outer = doc.blocks.new("B_FZ_OUT")
    outer.add_blockref("B_FZ_IN", (0, 0), dxfattribs={"layer": "S-NESTIN"})
    msp.add_blockref("B_FZ_OUT", (12000, 30000), dxfattribs={"layer": FZINS})
    off = doc.blocks.new("B_OFF")
    off.add_circle((0, 0), 150, dxfattribs={"layer": "S-OFFPILE"})
    msp.add_blockref("B_OFF", (14000, 30000), dxfattribs={"layer": OFFINS})
    # Minor 6: the invisible flag hides
    msp.add_circle((16000, 30000), 150, dxfattribs={"layer": "S-INV", "invisible": 1})
    ib = doc.blocks.new("B_INV")
    ib.add_circle((0, 0), 150, dxfattribs={"layer": "S-INVBLK"})
    msp.add_blockref("B_INV", (17000, 30000), dxfattribs={"invisible": 1})
    msp.add_circle((18000, 30000), 150, dxfattribs={"layer": "S-INVMIX", "invisible": 1})
    msp.add_circle((18000, 30000), 150, dxfattribs={"layer": "S-INVMIX"})
    # C2: hatches: in a block (block-local seed), with an elevation, an edge path, one without a boundary
    hb = doc.blocks.new("HB")
    hh = hb.add_hatch(dxfattribs={"layer": "S-HATCH"})
    hh.paths.add_polyline_path([(0, 0), (10, 0), (10, 10), (0, 10)])
    hh.set_seed_points([(1, 1)])
    msp.add_blockref("HB", (20000, 32000))
    h2 = msp.add_hatch(dxfattribs={"layer": "S-HATCH"})
    h2.dxf.elevation = (0, 0, 5)
    h2.paths.add_polyline_path([(22000, 32000), (22010, 32000), (22010, 32010), (22000, 32010)])
    h3 = msp.add_hatch(dxfattribs={"layer": "S-HATCH"})
    ep = h3.paths.add_edge_path()
    ep.add_line((24000, 32000), (24010, 32000))
    ep.add_line((24010, 32000), (24010, 32010))
    ep.add_line((24010, 32010), (24000, 32000))
    msp.add_hatch(dxfattribs={"layer": "S-HATCH-NONE"})
    # M1 / Minor 3: angle noise and squares
    msp.add_lwpolyline(
        [(41700, 34000), (40000, 34000.000001), (40000, 34800), (41700, 34800)],
        close=True,
        dxfattribs={"layer": "S-ANG"},
    )
    sqa = [(30000, 34000), (31000, 34000), (31000, 35000), (30000, 35000)]
    sqb = [(32000, 34000), (32999.9999999, 34000), (33000, 35000), (32000, 35000)]
    for pts in (sqa, sqb, rect(34500, 34500, 1000, 1000, 100)):
        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "S-SQ"})
    # M2: copies on a half-unit
    msp.add_circle((18000.5, 34000), 150, dxfattribs={"layer": "S-HALF"})
    msp.add_circle((18000.5000001, 34000), 150, dxfattribs={"layer": "S-HALF"})
    # M3: a circle in a non-uniformly scaled INSERT becomes an ELLIPSE; a real ellipse; a spline
    pu = doc.blocks.new("PU")
    pu.add_circle((0, 0), 0.5, dxfattribs={"layer": "S-NU"})
    msp.add_blockref("PU", (20000, 36000), dxfattribs={"xscale": 300, "yscale": 300.0001, "zscale": 300})
    msp.add_ellipse((22000, 36000), major_axis=(100, 0, 0), ratio=0.5, dxfattribs={"layer": "S-ELL"})
    msp.add_spline([(23000, 36000), (23100, 36100), (23200, 36000)], dxfattribs={"layer": "S-SPL"})
    # M4: a closed 1700x800 and one closed by a repeated start 0.5 away
    msp.add_lwpolyline(rect(26000, 36000, 1700, 800), close=True, dxfattribs={"layer": "S-CLOSED"})
    unfl = rect(28000, 36000, 1700, 800)
    msp.add_lwpolyline([*unfl, (unfl[0][0] + 0.5, unfl[0][1])], dxfattribs={"layer": "S-UNFL"})
    # Minor 1: a donut
    msp.add_lwpolyline(
        [(40000, 36000, 0, 0, 1), (40300, 36000, 0, 0, 1)],
        format="xyseb",
        close=True,
        dxfattribs={"layer": "S-DONUT"},
    )
    msp.add_lwpolyline(  # bulges of opposite sign: an S, not a circle
        [(40000, 38000, 0, 0, 1), (40300, 38000, 0, 0, -1)],
        format="xyseb",
        close=True,
        dxfattribs={"layer": "S-SNAKE"},
    )
    # Minor 2: the same circle in model space and in paper space gets two ids
    msp.add_circle((-50000, -50000), 150, dxfattribs={"layer": "S-IDS"})
    doc.layouts.get("Plot").add_circle((-50000, -50000), 150, dxfattribs={"layer": "S-IDS"})
    # Minor 5: an outline with a bulge is not a rectangle and its bbox follows the arc
    msp.add_lwpolyline(
        [(44000, 36000, 0.5), (45000, 36000, 0), (45000, 36800, 0), (44000, 36800, 0)],
        format="xyb",
        close=True,
        dxfattribs={"layer": "S-BULGE"},
    )
    # Minor 7: a spline-frame control vertex is not a point of the outline
    pl = msp.add_polyline2d(rect(47000, 36000, 1000, 600), close=True, dxfattribs={"layer": "S-SPLFIT"})
    pl.append_vertices([(48500, 37500)])
    pl.vertices[-1].dxf.flags = 16
    # Minor 9: an ARC is placed by its mid point (its centre lies on no sheet)
    msp.add_arc((-80000, 36000), 100000, -80, 80, dxfattribs={"layer": "S-ARC"})
    # M5: shapes the first fixture lacked
    msp.add_lwpolyline(
        [(50000, 30000), (51000, 30000), (51000, 30400), (50400, 30400), (50400, 31000), (50000, 31000)],
        close=True,
        dxfattribs={"layer": "S-L"},
    )
    skew = [(52000, 30000), (53000, 30000), (53000 + 173.648, 30984.808), (52173.648, 30984.808)]
    msp.add_lwpolyline(skew, close=True, dxfattribs={"layer": "S-QUAD"})
    ring = [
        (30000 + 500 * math.cos(2 * math.pi * k / 70), 38000 + 500 * math.sin(2 * math.pi * k / 70))
        for k in range(70)
    ]
    msp.add_lwpolyline(ring, close=True, dxfattribs={"layer": "S-POLY"})
    msp.add_polyline2d(rect(55000, 30500, 1000, 600), close=True, dxfattribs={"layer": "S-OLD"})
    msp.add_polyline3d(
        [(56000, 30000, 0), (57000, 30000, 5), (57000, 31000, 9)], dxfattribs={"layer": "S-3D"}
    )
    msp.add_circle((10000, 10000), 150, dxfattribs={"layer": CAP})  # same geometry as a PILE circle


@pytest.fixture(scope="module")
def base(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("geom")
    inp = build_geometry_dxf(root)
    work = root / "work"
    run_intake(inp, work, "demo-geom", knowledge=PROPOSED_FONT_TABLE)
    write_structure(inp, work)
    return root


@pytest.fixture(scope="module")
def doc(base) -> dict[str, Any]:
    return geometry(base / "work", REL, input_dir=base / "input", detail=True)


def region(d: dict[str, Any], sheet: str | None) -> dict[str, Any]:
    (found,) = [r for r in d["regions"] if r["sheet"] == sheet]
    return found


def group(r: dict[str, Any], key: str, layer: str, **match: Any) -> dict[str, Any]:
    (found,) = [g for g in r[key] if g["layer"] == layer and all(g[k] == v for k, v in match.items())]
    return found


def test_document_is_schema_valid(doc):
    assert validate("geometry", doc) == []
    assert doc["kind"] == "geometry" and doc["file"] == REL and doc["project_id"] == "demo-geom"
    assert doc["units"] == {"declared": "mm", "answered": None, "converted": False}


def test_layer_zero_in_a_two_level_block_takes_the_outer_insert_layer(doc):
    r = region(doc, "model#01")
    assert group(r, "circle_groups", HOST)["count"] == 1
    item = next(i for i in r["items"] if i["layer"] == HOST)
    assert item["block_path"] == ["PILE_OUT", "PILE_IN"] and item["centre"] == [30000.0, 10000.0]
    # one level: the INSERT's layer
    assert any(i["block_path"] == ["PILE_BLK"] and i["layer"] == PILE for i in r["items"])


def test_duplicates_collapse_into_one_item_with_copies(doc):
    r = region(doc, "model#01")
    g = group(r, "circle_groups", PILE, diameter=300.0)
    assert (g["count"], g["copies"]) == (3, 4)  # (10000,10000) twice, (12000,10000), the block pile
    assert g["centre_bbox"] == [10000.0, 10000.0, 20000.0, 10000.0]
    dup = next(i for i in r["items"] if i["centre"][0] == pytest.approx(10000, abs=1) and i["layer"] == PILE)
    assert dup["copies"] == 2 and dup["kind"] == "circle" and dup["diameter"] == 300.0
    assert r["layers"][PILE]["copies_collapsed"] == 1
    assert group(r, "circle_groups", PILE, diameter=400.0)["count"] == 1


def test_rotated_rectangle_groups_with_the_unrotated_one(doc):
    r = region(doc, "model#01")
    g = group(r, "outline_groups", CAP, short=800.0, long=1700.0)
    assert (g["count"], g["copies"], g["rectangle"], g["vertices"]) == (2, 2, True, 4)
    angles = sorted(i["angle"] for i in r["items"] if i["short"] == 800.0 and i["layer"] == CAP)
    assert angles == [pytest.approx(0.0), pytest.approx(30.0)]
    sq = group(r, "outline_groups", CAP, short=1700.0, long=1700.0)
    assert sq["count"] == 1


def test_open_polyline_is_counted_not_an_outline_and_first_equals_last_is_closed(doc):
    r = region(doc, "model#01")
    c = r["layers"][CAP]
    assert c["open_polylines"] == 1
    assert c["outlines"] == 4  # 1700x1700, two 800x1700, the first==last square
    assert c["lines"] == 2
    unit = group(r, "outline_groups", CAP, short=1000.0, long=1000.0)
    assert unit["vertices"] == 4 and unit["rectangle"] is True  # the closing duplicate is not a vertex
    assert all(len(i["centre"]) == 2 for i in r["items"])
    assert not any(i["centre"] == [50500.0, 20500.0] for i in r["items"])


def test_frozen_and_off_layers_are_counted_hidden_only(doc):
    r = region(doc, "model#01")
    assert r["layers"][FROZEN] == {**r["layers"][FROZEN], "hidden": 1, "circles": 0}
    assert r["layers"][OFF]["hidden"] == 1 and r["layers"][OFF]["lines"] == 0
    assert not [g for g in r["circle_groups"] if g["layer"] == FROZEN]
    assert not [i for i in r["items"] if i["layer"] in (FROZEN, OFF)]


def test_mirrored_insert_items_are_in_world_coordinates(doc):
    """Virtual copies of a mirrored INSERT carry extrusion (0,0,-1): their points are OCS, not WCS."""
    r = region(doc, "model#01")
    circle = next(i for i in r["items"] if i["layer"] == MIR and i["kind"] == "circle")
    assert circle["centre"] == [69900.0, 10050.0]
    outline = next(i for i in r["items"] if i["layer"] == MIR and i["kind"] == "outline")
    assert outline["centre"] == [68100.0, 10500.0]  # block centre (1900, 500) mirrored in x
    assert outline["bbox"] == [67200.0, 10100.0, 69000.0, 10900.0]
    assert (outline["short"], outline["long"], outline["rectangle"]) == (800.0, 1800.0, True)


def test_non_rectangle_outline_lists_its_points_in_detail(base):
    work, inp = base / "work", base / "input"
    d = geometry(work, REL, input_dir=inp, sheet=["model#01"], layer=["s-cap"], detail=True)
    rects = [i for i in region(d, "model#01")["items"] if i["kind"] == "outline"]
    assert all(i["points"] is None for i in rects if i["rectangle"])
    assert validate("geometry", d) == []


def test_sheet_filter_with_two_ids_and_unknown_sheet(base):
    work, inp = base / "work", base / "input"
    d = geometry(work, REL, input_dir=inp, sheet=["model#01", "model#02"])
    assert [r["sheet"] for r in d["regions"]] == ["model#01", "model#02"]
    assert group(region(d, "model#02"), "circle_groups", PILE)["count"] == 1
    assert d["query"]["sheet"] == ["model#01", "model#02"]
    with pytest.raises(ReaderError) as exc:
        geometry(work, REL, input_dir=inp, sheet=["model#99"])
    assert exc.value.exit_code == 2


def test_bbox_filter_is_model_space_by_item_centre(base):
    work, inp = base / "work", base / "input"
    d = geometry(work, REL, input_dir=inp, bbox=(39000, 19000, 46000, 21000), layer=[CAP])
    (r,) = d["regions"]
    assert r["sheet"] is None and r["bbox"] == [39000.0, 19000.0, 46000.0, 21000.0]
    assert r["layers"][CAP]["outlines"] == 3 and r["layers"][CAP]["open_polylines"] == 0
    assert d["query"]["bbox"] == [39000.0, 19000.0, 46000.0, 21000.0]
    assert validate("geometry", d) == []


def test_layer_filter_is_case_insensitive_on_the_effective_layer(base):
    work, inp = base / "work", base / "input"
    d = geometry(work, REL, input_dir=inp, sheet=["model#01"], layer=["s-host"])
    r = region(d, "model#01")
    assert list(r["layers"]) == [HOST] and [g["layer"] for g in r["circle_groups"]] == [HOST]
    two = geometry(work, REL, input_dir=inp, sheet=["model#01"], layer=["s-host", "S-PILE"])
    assert sorted(region(two, "model#01")["layers"]) == [HOST, PILE]


def test_groups_sorted_by_count_then_layer(base):
    d = geometry(base / "work", REL, input_dir=base / "input", sheet=["model#01"], layer=[PILE, HOST])
    r = region(d, "model#01")
    keys = [(g["layer"], g["diameter"], g["count"]) for g in r["circle_groups"]]
    assert keys == [(PILE, 300.0, 3), (HOST, 300.0, 1), (PILE, 400.0, 1)]
    counts = [g["count"] for g in r["outline_groups"]]
    assert counts == sorted(counts, reverse=True)


def test_max_truncates_groups_with_a_warning_naming_the_full_count(base):
    work, inp = base / "work", base / "input"
    d = geometry(work, REL, input_dir=inp, sheet=["model#01"], layer=[PILE, HOST], max_rows=1, detail=True)
    r = region(d, "model#01")
    assert len(r["circle_groups"]) == 1 and len(r["items"]) == 1
    assert r["circle_groups"][0]["count"] == 3
    text = " ".join(d["warnings"])
    assert "geometry truncated" in text and "--max 3" in text
    assert validate("geometry", d) == []


def test_tol_rounds_sizes(base):
    work, inp = base / "work", base / "input"
    d = geometry(work, REL, input_dir=inp, sheet=["model#01"], tol=1000.0)
    r = region(d, "model#01")
    assert group(r, "circle_groups", PILE, diameter=0.0)["count"] >= 1  # 300 rounds to 0 at 1000
    assert d["query"]["tol"] == 1000.0


def test_default_run_lists_every_sheet(doc):
    ids = {r["sheet"] for r in doc["regions"]}
    assert {"model#01", "model#02"} <= ids


def test_read_only_nothing_written(base, capsys):
    before = sorted(p.relative_to(base) for p in base.rglob("*"))
    assert main(["geometry", str(base / "work"), REL, "--input-dir", str(base / "input")]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["kind"] == "geometry" and validate("geometry", out) == []
    assert sorted(p.relative_to(base) for p in base.rglob("*")) == before


def test_cli_two_sheets_and_elapsed_on_stderr(base, capsys):
    argv = ["geometry", str(base / "work"), REL, "--input-dir", str(base / "input")]
    assert main([*argv, "--sheet", "model#01", "model#02", "--layer", PILE, "--detail", "--max", "2"]) == 0
    cap = capsys.readouterr()
    assert [r["sheet"] for r in json.loads(cap.out)["regions"]] == ["model#01", "model#02"]
    assert "geometry truncated" in cap.err and "s" in cap.err


@pytest.mark.parametrize(
    "extra",
    [
        ["--sheet", "model#99"],
        ["--max", "0"],
        ["--tol", "0"],
        ["--sheet", "model#01", "--bbox", "0", "0", "1", "1"],
        ["--bbox", "0", "0", "1"],
    ],
)
def test_cli_usage_errors(base, capsys, extra):
    argv = ["geometry", str(base / "work"), REL, "--input-dir", str(base / "input"), *extra]
    assert main(argv) == 2
    assert capsys.readouterr().err


def test_native_dxf_without_input_dir_and_missing_inventory(base, tmp_path, capsys):
    assert main(["geometry", str(base / "work"), REL]) == 2
    assert "--input-dir" in capsys.readouterr().err
    with pytest.raises(ReaderError) as exc:
        geometry(tmp_path, REL)
    assert exc.value.exit_code == 2


def test_sheet_filter_needs_the_sheets_document(base, tmp_path):
    shutil.copytree(base, tmp_path / "w")
    work, inp = tmp_path / "w" / "work", tmp_path / "w" / "input"
    (work / "structure" / f"{REL}.sheets.json").unlink()
    with pytest.raises(ReaderError) as exc:
        geometry(work, REL, input_dir=inp, sheet=["model#01"])
    assert exc.value.exit_code == 2
    out = geometry(work, REL, input_dir=inp)
    assert [r["sheet"] for r in out["regions"]] == [None]
    assert validate("geometry", out) == []


def test_a_changed_drawing_is_refused(base, tmp_path):
    shutil.copytree(base, tmp_path / "w")
    dxf = tmp_path / "w" / "input" / REL
    dxf.write_bytes(dxf.read_bytes() + b"\n")
    with pytest.raises(ReaderError) as exc:
        geometry(tmp_path / "w" / "work", REL, input_dir=tmp_path / "w" / "input")
    assert exc.value.exit_code == 1


# --- the T21 review: findings C1-C2, M1-M5, minor 1-9 -----------------------------------------


def all_items(d: dict[str, Any], layer: str | None = None) -> list[dict[str, Any]]:
    return [i for r in d["regions"] for i in r.get("items", []) if layer is None or i["layer"] == layer]


def total(d: dict[str, Any], layer: str, counter: str, sheet: Any = "any") -> int:
    return sum(
        r["layers"].get(layer, {}).get(counter, 0)
        for r in d["regions"]
        if sheet == "any" or r["sheet"] == sheet
    )


def test_c1_a_frozen_insert_layer_hides_the_block_content_on_other_layers(doc):
    assert total(doc, "S-FZPILE", "hidden") == 1 and total(doc, "S-FZPILE", "circles") == 0
    assert not all_items(doc, "S-FZPILE")


def test_c1_frozen_outer_insert_hides_an_inner_insert_on_a_visible_layer(doc):
    assert total(doc, "S-NEST", "hidden") == 1 and total(doc, "S-NEST", "circles") == 0
    assert not all_items(doc, "S-NEST")


def test_c1_an_off_insert_layer_hides_only_layer_zero_content(doc):
    assert total(doc, "S-OFFPILE", "circles") == 1 and total(doc, "S-OFFPILE", "hidden") == 0


def test_minor6_invisible_entities_stay_counted_and_are_reported(doc):
    assert total(doc, "S-INV", "circles") == 1 and total(doc, "S-INV", "hidden") == 0
    assert total(doc, "S-INV", "invisible") == 1
    (item,) = all_items(doc, "S-INV")
    assert item["invisible"] is True
    (g,) = [g for r in doc["regions"] for g in r["circle_groups"] if g["layer"] == "S-INV"]
    assert g["invisible"] == 1


def test_minor6_an_invisible_insert_passes_the_flag_to_its_content(doc):
    (item,) = all_items(doc, "S-INVBLK")
    assert item["invisible"] is True and total(doc, "S-INVBLK", "hidden") == 0
    assert total(doc, "S-INVBLK", "invisible") == 1


def test_minor6_a_visible_copy_makes_the_item_visible(doc):
    (item,) = all_items(doc, "S-INVMIX")
    assert item["copies"] == 2 and item["invisible"] is False
    assert total(doc, "S-INVMIX", "invisible") == 1
    (g,) = [g for r in doc["regions"] for g in r["circle_groups"] if g["layer"] == "S-INVMIX"]
    assert g["invisible"] == 0


def test_minor6_one_warning_names_the_total(doc):
    (w,) = [w for w in doc["warnings"] if "invisible flag" in w]
    assert "3 entities carry the invisible flag (group 60)" in w
    assert "render does not draw them, geometry counts them: confirm a counted member with render" in w
    assert "converter" not in w


def test_c2_hatches_are_placed_by_their_boundary(doc):
    r = region(doc, "model#01")
    assert r["layers"]["S-HATCH"]["hatches"] == 3  # block-local seed, elevation 5, edge path
    assert total(doc, "S-HATCH", "hatches", None) == 0 and total(doc, "S-HATCH", "unplaced") == 0


def test_c2_a_hatch_without_boundary_is_unplaced_with_a_warning(doc):
    assert total(doc, "S-HATCH-NONE", "unplaced", None) == 1
    assert total(doc, "S-HATCH-NONE", "hatches") == 0
    assert any("HATCH" in w and "no boundary" in w for w in doc["warnings"])


def test_m1_an_angle_that_rounds_to_180_is_zero(doc):
    (item,) = all_items(doc, "S-ANG")
    assert item["angle"] == 0.0 and item["rectangle"] is True


def test_minor3_a_square_reports_its_angle_modulo_90(doc):
    angles = sorted(i["angle"] for i in all_items(doc, "S-SQ"))
    assert angles == [pytest.approx(0.0), pytest.approx(0.0), pytest.approx(10.0)]


def test_m2_copies_on_a_half_unit_merge(doc):
    assert total(doc, "S-HALF", "circles") == 1 and total(doc, "S-HALF", "copies_collapsed") == 1
    assert [i["copies"] for i in all_items(doc, "S-HALF")] == [2]


def test_m3_a_circle_in_a_non_uniformly_scaled_insert_stays_a_circle(doc):
    (item,) = all_items(doc, "S-NU")
    assert item["kind"] == "circle" and item["diameter"] == 300.0
    assert item["centre"] == [20000.0, 36000.0]


def test_m3_real_ellipses_and_splines_are_counted_not_dropped(doc):
    assert total(doc, "S-ELL", "ellipses") == 1 and total(doc, "S-ELL", "circles") == 0
    assert total(doc, "S-SPL", "splines") == 1


def test_m4_closed_flag_keeps_every_vertex_at_a_large_tolerance(base):
    d = geometry(base / "work", REL, input_dir=base / "input", layer=["S-CLOSED"], detail=True, tol=1000.0)
    (item,) = all_items(d)
    assert (item["vertices"], item["rectangle"], item["short"], item["long"]) == (4, True, 800.0, 1700.0)


def test_m4_an_unflagged_polyline_closed_within_tol_drops_the_repeated_vertex(doc):
    (item,) = all_items(doc, "S-UNFL")
    assert item["kind"] == "outline" and item["vertices"] == 4 and item["rectangle"] is True


def test_m4_default_tol_is_one_millimetre_of_the_unit_and_reported(doc):
    assert doc["query"]["tol"] == 1.0 and not any("tol" in w for w in doc["warnings"])


@pytest.mark.parametrize(
    ("unit", "tol"), [("mm", 1.0), ("cm", 0.1), ("m", 0.001), ("in", 1 / 25.4), ("ft", 1 / 304.8)]
)
def test_m4_default_tol_table(unit, tol):
    from tekla_harness.geometry import _default_tol

    warnings: list[str] = []
    assert _default_tol(unit, None, warnings) == pytest.approx(tol) and not warnings
    assert _default_tol(None, unit, warnings) == pytest.approx(tol) and not warnings
    assert _default_tol("m" if unit != "m" else "mm", unit, warnings) != pytest.approx(tol)  # answer wins


def test_m4_unknown_units_assume_one_with_a_warning():
    from tekla_harness.geometry import _default_tol

    warnings: list[str] = []
    assert _default_tol(None, None, warnings) == 1.0
    assert any("pass --tol" in w for w in warnings)


def build_units_dxf(base: Path, insunits: int) -> Path:
    root = base / "input"
    (root / "plans").mkdir(parents=True)
    doc = readfile(str(build_set(base, "src.dxf")))
    doc.header["$INSUNITS"] = insunits
    msp = doc.modelspace()
    msp.add_lwpolyline(rect(30, 20, 1.7, 0.8), close=True, dxfattribs={"layer": CAP})
    msp.add_circle((10, 10), 0.15, dxfattribs={"layer": PILE})
    msp.add_circle((12, 10), 0.2, dxfattribs={"layer": PILE})
    doc.saveas(root / REL)
    return root


def run_units(tmp_path: Path, insunits: int, **kw: Any) -> dict[str, Any]:
    inp = build_units_dxf(tmp_path, insunits)
    run_intake(inp, tmp_path / "work", "demo-units", knowledge=PROPOSED_FONT_TABLE)
    write_structure(inp, tmp_path / "work")
    return geometry(tmp_path / "work", REL, input_dir=inp, **kw)


def test_m4_a_drawing_in_metres_gets_a_millimetre_tolerance(tmp_path):
    d = run_units(tmp_path, 6, detail=True)
    assert d["units"]["declared"] == "m" and d["query"]["tol"] == 0.001
    diameters = sorted(g["diameter"] for r in d["regions"] for g in r["circle_groups"] if g["layer"] == PILE)
    assert diameters == [0.3, 0.4]
    (cap,) = all_items(d, CAP)
    assert (cap["vertices"], cap["rectangle"], cap["short"], cap["long"]) == (4, True, 0.8, 1.7)


def test_m4_undeclared_units_fall_back_to_one_with_a_warning(tmp_path):
    d = run_units(tmp_path, 0)
    assert d["query"]["tol"] == 1.0 and any("pass --tol" in w for w in d["warnings"])


def test_minor1_a_donut_is_a_circle(doc):
    (item,) = all_items(doc, "S-DONUT")
    assert item["kind"] == "circle" and item["diameter"] == 300.0 and item["centre"] == [40150.0, 36000.0]
    assert total(doc, "S-DONUT", "open_polylines") == 0


def test_minor1_bulges_of_opposite_sign_are_not_a_circle(doc):
    assert total(doc, "S-SNAKE", "circles") == 0 and total(doc, "S-SNAKE", "open_polylines") == 1


def test_minor2_ids_differ_between_spaces(doc):
    ids = [i["id"] for i in all_items(doc, "S-IDS")]
    assert len(ids) == 2 and len(set(ids)) == 2


def test_every_item_names_its_space(doc):
    items = all_items(doc, "S-IDS")  # the same circle in the model and in the layout
    assert sorted(i["space"] for i in items) == ["Plot", "model"]
    assert all(i["space"] for i in all_items(doc))


def test_ids_are_hex_stable_and_unique(base, doc):
    ids = [i["id"] for i in all_items(doc)]
    assert ids and all(re.fullmatch(r"G-[0-9a-f]{10}", i) for i in ids)
    assert len(set(ids)) == len(ids)
    again = geometry(base / "work", REL, input_dir=base / "input", detail=True, max_rows=100000)
    assert sorted(ids) == sorted(i["id"] for i in all_items(again))


def test_minor5_an_outline_with_a_bulge_is_sized_by_its_arcs(doc):
    (item,) = all_items(doc, "S-BULGE")
    assert item["rectangle"] is False and item["angle"] is None
    assert item["bbox"][1] < 36000.0 - 50  # the arc bulges below the straight edge
    assert (item["short"], item["long"]) == (1000.0, 1050.0)  # 800 + the 250 sagitta


def test_minor7_spline_frame_control_vertices_are_not_points(doc):
    (item,) = all_items(doc, "S-SPLFIT")
    assert item["vertices"] == 4 and item["rectangle"] is True


def test_minor9_an_arc_is_placed_by_its_mid_point(doc):
    assert total(doc, "S-ARC", "arcs", "model#01") == 1 and total(doc, "S-ARC", "arcs", None) == 0


def test_m5_l_shaped_outline_lists_its_points(doc):
    (item,) = all_items(doc, "S-L")
    assert item["rectangle"] is False and item["vertices"] == 6
    assert item["points"] == [
        [50000.0, 30000.0],
        [51000.0, 30000.0],
        [51000.0, 30400.0],
        [50400.0, 30400.0],
        [50400.0, 31000.0],
        [50000.0, 31000.0],
    ]
    assert (item["short"], item["long"], item["angle"]) == (1000.0, 1000.0, None)
    assert item["points_truncated"] is False


def test_m5_a_quadrilateral_with_an_80_degree_corner_is_not_a_rectangle(doc):
    (item,) = all_items(doc, "S-QUAD")
    assert item["rectangle"] is False and item["vertices"] == 4 and len(item["points"]) == 4


def test_m5_a_70_vertex_polygon_is_truncated_to_64_points(doc):
    (item,) = all_items(doc, "S-POLY")
    assert item["vertices"] == 70 and len(item["points"]) == 64 and item["points_truncated"] is True


def test_m5_old_style_2d_polyline_is_an_outline_and_3d_is_ignored_with_a_warning(doc):
    (item,) = all_items(doc, "S-OLD")
    assert item["rectangle"] is True and (item["short"], item["long"]) == (600.0, 1000.0)
    assert total(doc, "S-3D", "open_polylines") == 0 and not all_items(doc, "S-3D")
    assert any("not a 2D polyline" in w for w in doc["warnings"])


def test_m5_the_same_circle_on_two_layers_is_two_items(doc):
    cap = all_items(doc, CAP)
    assert [i["kind"] for i in cap].count("circle") == 1
    assert total(doc, CAP, "circles") == 1
    assert total(doc, PILE, "circles", "model#01") == 4  # layer is part of the dedupe key


def test_m5_arcs_and_hatches_have_their_own_counters(doc):
    assert total(doc, "S-ARC", "arcs") == 1 and total(doc, "S-ARC", "lines") == 0
    assert total(doc, "S-HATCH", "hatches") == 3 and total(doc, "S-HATCH", "lines") == 0


def test_minor8_sheet_is_repeatable(base, capsys):
    argv = ["geometry", str(base / "work"), REL, "--input-dir", str(base / "input")]
    assert main([*argv, "--sheet", "model#01", "--sheet", "model#02"]) == 0
    assert [r["sheet"] for r in json.loads(capsys.readouterr().out)["regions"]] == ["model#01", "model#02"]


def test_read_geometry_dimensions_keyword_only_adds_the_dimensions(base):
    """E10b: `dimensions=True` keeps the DIMENSIONs of the sheets read; the geometry document is the same."""
    kw: dict[str, Any] = {"sheet": ["model#01"], "input_dir": base / "input", "detail": True}
    plain = read_geometry(base / "work", REL, **kw)
    withdims = read_geometry(base / "work", REL, dimensions=True, **kw)
    assert plain.dims == {}
    assert withdims.doc == plain.doc  # no layer row, counter or warning for a dimension
    assert list(withdims.dims) == ["model#01"]
    assert len(withdims.dims["model#01"]) == 2  # the two dimensions of `build_set`'s sheet 1


def test_read_geometry_counts_the_dimension_texts_without_a_text_index_entry(base, monkeypatch):
    """E10b fix 2, m1: `dims_unlinked` is the count of dimension texts the font gate could not see."""
    from tekla_harness.dimensions import _TextLinks

    kw: dict[str, Any] = {"sheet": ["model#01"], "input_dir": base / "input"}
    assert read_geometry(base / "work", REL, **kw).dims_unlinked == 0  # no dimensions read, none counted
    assert read_geometry(base / "work", REL, dimensions=True, **kw).dims_unlinked == 0
    real = _TextLinks.link

    def link(self: Any, space: str, block_path: Any, text: str, at: Any) -> Any:
        return real(self, space, block_path, "no such text", at)

    monkeypatch.setattr(_TextLinks, "link", link)
    read = read_geometry(base / "work", REL, dimensions=True, **kw)
    assert read.dims_unlinked == len(read.dims["model#01"]) == 2
    assert read_geometry(base / "work", REL, **kw).dims_unlinked == 0
