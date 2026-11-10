"""grids, tool wave 4 package G: visibility of text and lines, obround bubbles, family consistency, pairing,
stray families, `*` labels and stacked views, elevation families, grid-system units evidence.

Synthetic DXF only (tests/_dxf_fixtures.py helpers); corpus checks live in the wave 4 evidence notes.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest
from ezdxf.enums import TextEntityAlignment

from _dxf_fixtures import TH, R
from tekla_harness.extract_text import extract_text
from tekla_harness.grid_system import build_grid_systems
from tekla_harness.grids import extract_grids
from tekla_harness.schemas import validate
from tekla_harness.sheets import extract_sheets
from test_grid_system import Work, ans, codes, fam, view
from test_grids import _bubble, _plain, _simple_grid, families, family, questions


def run_with(path: Path, mutate=None) -> dict[str, Any]:
    """Like test_grids.run, with `mutate(index)` applied to the text index first (a stand-in for package T's
    `printed` field, which this package only reads)."""
    index = extract_text(path)
    if mutate is not None:
        mutate(index)
    sheets = extract_sheets(path, index)
    result = extract_grids(path, index, sheets)
    assert validate("grids", result) == [], validate("grids", result)
    json.dumps(result, allow_nan=False)
    return result


def not_printed(*texts: str, reasons: tuple[str, ...] = ("entity_invisible",)):
    """Mutator: every index entry whose text is in `texts` becomes `printed: false`."""

    def apply(index: dict[str, Any]) -> None:
        for e in index["entries"]:
            if e["display_text"].strip() in texts:
                e["printed"] = False
                e["not_printed_reasons"] = list(reasons)

    return apply


def _axes_labels(result: dict[str, Any], sheet: str = "unknown") -> list[list[str]]:
    return [[a["label"]["value"] for a in f["axes"]] for f in families(result, sheet)]


def _warnings(result: dict[str, Any]) -> str:
    return " | ".join(result["warnings"])


# --- item 1: not-printed text and lines are not bubbles, labels or axes -------------------------------------


def _grid3(msp):
    """Axes 1 2 3 at 0 / 6000 / 12000 and A B, the horizontal axes long enough to cross a fourth vertical
    line at x = 18000 (the test draws that one)."""
    for x, label in ((0.0, "1"), (6000.0, "2"), (12000.0, "3")):
        msp.add_line((x, 0), (x, 12000))
        _bubble(msp, (x, -R), label)
    for y, label in ((2000.0, "A"), (8000.0, "B")):
        msp.add_line((-2000, y), (20000, y))
        _bubble(msp, (-2000 - R, y), label)


def _grid_with_rebar_bubble(msp, hidden_label: str = "9"):
    _grid3(msp)
    # a fourth vertical line with a bubble whose label does not print (a rebar mark drawn like an axis)
    msp.add_line((18000, 0), (18000, 12000))
    _bubble(msp, (18000, -R), hidden_label)


def test_a_bubble_whose_label_does_not_print_is_no_bubble(tmp_path):
    path = _plain(tmp_path, _grid_with_rebar_bubble)
    shown = run_with(path)
    assert ["1", "2", "3", "9"] in _axes_labels(shown)  # printed: the extra axis is read
    hidden = run_with(path, not_printed("9"))
    assert ["1", "2", "3"] in _axes_labels(hidden)
    assert hidden["summary"]["bubbles_labelled"] == shown["summary"]["bubbles_labelled"] - 1
    assert "not printed" in _warnings(hidden) and "1 text" in _warnings(hidden)


def test_a_hidden_text_inside_a_circle_is_not_other_text(tmp_path):
    """A visible label plus a hidden note in one circle: the note does not print, so it is not 'other text'
    and does not make the label ambiguous."""

    def fn(msp):
        _simple_grid(msp)
        msp.add_text("see note", height=TH).set_placement((0.0, -R), align=TextEntityAlignment.MIDDLE_CENTER)

    path = _plain(tmp_path, fn)
    assert run_with(path)["summary"]["bubbles_other_text"] >= 1  # printed: a callout, not a bubble
    hidden = run_with(path, not_printed("see note"))
    assert hidden["summary"]["bubbles_other_text"] == 0
    assert ["1", "2", "3"] in _axes_labels(hidden)


def test_a_hidden_second_label_does_not_make_the_bubble_ambiguous(tmp_path):
    def fn(msp):
        _simple_grid(msp)
        msp.add_text("9", height=TH).set_placement((6000.0, -R), align=TextEntityAlignment.MIDDLE_CENTER)

    path = _plain(tmp_path, fn)
    assert run_with(path)["summary"]["bubbles_ambiguous_label"] == 1
    hidden = run_with(path, not_printed("9"))
    assert hidden["summary"]["bubbles_ambiguous_label"] == 0


def test_uncertain_visibility_keeps_the_text(tmp_path):
    """print_uncertain_reasons alone changes nothing (the entry is kept printed)."""

    def mark(index: dict[str, Any]) -> None:
        for e in index["entries"]:
            if e["display_text"].strip() == "9":
                e["print_uncertain_reasons"] = ["viewport_frozen_layer"]

    result = run_with(_plain(tmp_path, _grid_with_rebar_bubble), mark)
    assert ["1", "2", "3", "9"] in _axes_labels(result)
    assert "not printed" not in _warnings(result)


def _hide_line(msp, how: str, a, b, layer: str = "AXHIDE"):
    doc = msp.doc
    lay = doc.layers.add(layer)
    if how == "off":
        lay.off()
    elif how == "frozen":
        lay.freeze()
    elif how == "no_plot":
        lay.dxf.plot = 0
    attribs: dict[str, Any] = {"layer": layer if how != "entity" else "0"}
    if how == "entity":
        attribs["invisible"] = 1
    msp.add_line(a, b, dxfattribs=attribs)


@pytest.mark.parametrize("how", ["entity", "off", "frozen", "no_plot"])
def test_a_line_that_does_not_print_is_no_axis(tmp_path, how):
    def fn(msp):
        _grid3(msp)
        # a fourth axis line with a printed bubble, but the line itself does not print
        _hide_line(msp, how, (18000, 0), (18000, 12000))
        _bubble(msp, (18000, -R), "4")

    result = run_with(_plain(tmp_path, fn))
    assert ["1", "2", "3"] in _axes_labels(result)
    assert result["unpaired_bubbles"]["count"] == 1
    assert "not printed" in _warnings(result) and "line" in _warnings(result)


def test_a_bubble_pairs_with_the_printed_line_not_a_nearer_hidden_one(tmp_path):
    def fn(msp):
        _grid3(msp)
        # a hidden line ends nearer to bubble 3 than its printed axis line does: it must not win the pairing
        _hide_line(msp, "entity", (12000.0 + 0.2 * R, -R), (12000.0 + 0.2 * R, 12000))

    result = run_with(_plain(tmp_path, fn))
    axis3 = family(result, "unknown", "1 2 3")["axes"][2]
    assert axis3["line"]["start"][0] == pytest.approx(12000.0)


def test_a_circle_that_does_not_print_is_no_bubble(tmp_path):
    def fn(msp):
        _grid3(msp)
        msp.add_line((18000, 0), (18000, 12000))
        msp.add_circle((18000, -R), R, dxfattribs={"invisible": 1})
        msp.add_text("4", height=TH).set_placement((18000, -R), align=TextEntityAlignment.MIDDLE_CENTER)

    result = run_with(_plain(tmp_path, fn))
    assert ["1", "2", "3"] in _axes_labels(result)
    assert "not printed" in _warnings(result) and "circle" in _warnings(result)


def test_a_line_inside_an_invisible_insert_is_kept_uncertain(tmp_path):
    """Autodesk is silent on an INSERT's group 60 hiding its contents (research note, section 2): the
    children are kept, as the note says 'flag rather than drop'."""

    def fn(msp):
        _grid3(msp)
        blk = msp.doc.blocks.new("AXLINE")
        blk.add_line((0, 0), (0, 12000))
        msp.add_blockref("AXLINE", (18000, 0), dxfattribs={"invisible": 1})
        _bubble(msp, (18000, -R), "4")

    result = run_with(_plain(tmp_path, fn))
    assert ["1", "2", "3", "4"] in _axes_labels(result)


def test_a_layer_zero_line_in_a_block_on_an_off_layer_is_kept_uncertain(tmp_path):
    """Which layer an entity on layer 0 inside a block takes is not settled by Autodesk (research note,
    section 7): the line is kept."""

    def fn(msp):
        _grid3(msp)
        msp.doc.layers.add("BLK").off()
        blk = msp.doc.blocks.new("AXLINE")
        blk.add_line((0, 0), (0, 12000), dxfattribs={"layer": "0"})
        msp.add_blockref("AXLINE", (18000, 0), dxfattribs={"layer": "BLK"})
        _bubble(msp, (18000, -R), "4")

    result = run_with(_plain(tmp_path, fn))
    assert ["1", "2", "3", "4"] in _axes_labels(result)


def test_visibility_never_adds_questions_about_printed_items(tmp_path):
    result = run_with(_plain(tmp_path, _simple_grid))
    assert not questions(result, "grid_none_found")
    assert "not printed" not in _warnings(result)


# --- item 2 (F2a): obround bubbles ---------------------------------------------------------------

HALF = 328.0  # half of the straight part of the obround (EVAL-4 180: 656 long, 850 apart)
RHO = 425.0  # the caps' radius
R_EQ = HALF + RHO  # the bubble's equivalent radius: half of the overall length


def _obround(msp, c, label, *, half=HALF, rho=RHO, layer="0", turn=0.0, with_lines=True, rho_b=None):
    """A bubble drawn as two LINEs and two semicircular ARCs (a stadium) around a TEXT label. `turn` rotates
    it about its centre (degrees); `rho_b` gives the second cap another radius."""
    ca, sa = math.cos(math.radians(turn)), math.sin(math.radians(turn))

    def at(dx: float, dy: float) -> tuple[float, float]:
        return (c[0] + dx * ca - dy * sa, c[1] + dx * sa + dy * ca)

    attribs = {"layer": layer}
    if with_lines:
        msp.add_line(at(-half, rho), at(half, rho), dxfattribs=attribs)
        msp.add_line(at(-half, -rho), at(half, -rho), dxfattribs=attribs)
    msp.add_arc(at(half, 0), rho_b or rho, turn - 90.0, turn + 90.0, dxfattribs=attribs)
    msp.add_arc(at(-half, 0), rho, turn + 90.0, turn + 270.0, dxfattribs=attribs)
    msp.add_text(label, height=750.0, dxfattribs=attribs).set_placement(
        c, align=TextEntityAlignment.MIDDLE_CENTER
    )


def _obround_grid(msp, **kw):
    for x, label in ((0.0, "1"), (6000.0, "2"), (12000.0, "3")):
        msp.add_line((x, 0), (x, 12000))
        _obround(msp, (x, -R_EQ), label, **kw)
    for y, label in ((2000.0, "A"), (8000.0, "B")):
        msp.add_line((-2000, y), (14000, y))
        _obround(msp, (-2000 - R_EQ, y), label, **kw)


def test_an_obround_bubble_is_a_bubble(tmp_path):
    """EVAL-4 180: the framing-plan axis labels sit in an obround (2 LINE + 2 ARC, no CIRCLE): 0 bubbles."""
    result = run_with(_plain(tmp_path, _obround_grid))
    numbers = family(result, "unknown", "1 2 3")
    assert numbers["proposal"]["coordinates"] == "0 2*6000"
    assert family(result, "unknown", "A B")["proposal"]["coordinates"] == "0 6000"
    assert numbers["axes"][0]["bubbles"][0]["radius"] == pytest.approx(R_EQ)
    assert result["summary"]["bubbles_paired"] == 5


def test_a_turned_obround_is_a_bubble(tmp_path):
    result = run_with(_plain(tmp_path, lambda m: _obround_grid(m, turn=90.0)))
    assert family(result, "unknown", "1 2 3")["proposal"]["coordinates"] == "0 2*6000"


def test_an_obround_inside_a_block_is_a_bubble(tmp_path):
    def fn(msp):
        blk = msp.doc.blocks.new("OBR")
        _obround(blk, (0.0, 0.0), "9")
        _obround_grid(msp)
        msp.add_blockref("OBR", (30000.0, 0.0), dxfattribs={"rotation": 30.0})

    result = run_with(_plain(tmp_path, fn))
    assert result["summary"]["circles"] == 6  # five on the grid and the inserted one
    assert family(result, "unknown", "1 2 3")["proposal"]["coordinates"] == "0 2*6000"


def test_two_arcs_without_their_lines_are_no_bubble(tmp_path):
    result = run_with(_plain(tmp_path, lambda m: _obround_grid(m, with_lines=False)))
    assert result["summary"]["circles"] == 0 and result["groups"] == []


def test_caps_of_two_radii_are_no_obround(tmp_path):
    result = run_with(_plain(tmp_path, lambda m: _obround_grid(m, rho_b=RHO * 1.3)))
    assert result["summary"]["circles"] == 0


def test_a_quarter_arc_pair_is_no_obround(tmp_path):
    def fn(msp):
        msp.add_line((-HALF, RHO), (HALF, RHO))
        msp.add_line((-HALF, -RHO), (HALF, -RHO))
        msp.add_arc((HALF, 0.0), RHO, -45.0, 45.0)  # not a semicircle
        msp.add_arc((-HALF, 0.0), RHO, 135.0, 225.0)

    assert run_with(_plain(tmp_path, fn))["summary"]["circles"] == 0


# --- item 2 (F2a): the units evidence uses plan systems only ----------------------------------------


def _scaled_grid(msp, ox: float, spacing: float, n: int, radius: float) -> None:
    """n vertical axes 1..n and n horizontal axes A.. at `spacing`, bubbles of `radius`, from (ox, 0)."""
    top = (n - 1) * spacing + 2 * spacing
    for k in range(n):
        x = ox + k * spacing
        msp.add_line((x, 0), (x, top))
        msp.add_circle((x, -radius), radius)
        msp.add_text(str(k + 1), height=0.9 * radius).set_placement(
            (x, -radius), align=TextEntityAlignment.MIDDLE_CENTER
        )
    for k in range(n):
        y = k * spacing + spacing
        msp.add_line((ox - spacing, y), (ox + (n - 1) * spacing + spacing, y))
        msp.add_circle((ox - spacing - radius, y), radius)
        msp.add_text(chr(65 + k), height=0.9 * radius).set_placement(
            (ox - spacing - radius, y), align=TextEntityAlignment.MIDDLE_CENTER
        )


def test_the_grid_units_doubt_follows_the_plan_views_not_a_small_key_plan(tmp_path):
    """EVAL-4 180: a key plan drawn small (spacings about 300) made the median of all spacings 330 and the
    file's mm answer 'implausible', though every real plan has 8000 spacings."""

    def fn(msp):
        _scaled_grid(msp, 0.0, 300.0, 8, 15.0)  # the key plan: 14 spacings of 300
        _scaled_grid(msp, 100000.0, 8000.0, 3, 400.0)  # two plan views: 4 spacings of 8000 each
        _scaled_grid(msp, 200000.0, 8000.0, 3, 400.0)

    result = run_with(_plain(tmp_path, fn))
    assert len(result["groups"]) == 3
    assert not questions(result, "grid_units_doubt")


def test_the_grid_units_doubt_still_fires_when_most_views_disagree(tmp_path):
    def fn(msp):
        for ox in (0.0, 100000.0, 200000.0):
            _scaled_grid(msp, ox, 6.0, 3, 0.4)  # drawn in metres, declared mm

    result = run_with(_plain(tmp_path, fn))
    assert len(questions(result, "grid_units_doubt")) == 1


def _plan_views(spacing: float, sheets=("model#03", "model#04")) -> list[dict[str, Any]]:
    return [
        view(
            f"V{k + 2:03d}",
            sheet,
            fam(f"F{2 * k + 3:03d}", ["A", "B", "C"], [spacing, spacing], angle=0.0),
            fam(f"F{2 * k + 4:03d}", ["1", "2", "3"], [spacing, spacing]),
        )
        for k, sheet in enumerate(sheets)
    ]


def _key_plan(spacing: float, n: int = 8) -> dict[str, Any]:
    """A key plan on its own sheet: more axes than the plans, the same labels, a different scale."""
    return view(
        "V001",
        "Layout1#01",
        fam("F001", [chr(65 + k) for k in range(n)], [spacing] * (n - 1), angle=0.0),
        fam("F002", [str(k + 1) for k in range(n)], [spacing] * (n - 1)),
    )


def _units_work(tmp_path, example, key: float, plan_spacing: float) -> Path:
    w = Work(tmp_path, example)
    w.add_file("plans.dxf", [_key_plan(key), *_plan_views(plan_spacing)])
    return w.finish()


def _mm(file: str = "plans.dxf") -> dict[str, Any]:
    return ans("units_confirm_all", file, {"unit": "mm"})


def test_a_single_source_key_plan_never_decides_the_units_evidence(tmp_path, example):
    """EVAL-4 180 (Q-199): a key plan with spacings about 300 beside plans of 8000, units answered mm: the
    plans are the plan systems and agree with mm, so no units_answer_contradicts_evidence."""
    doc = build_grid_systems(_units_work(tmp_path, example, 300.0, 8000.0), answers=[_mm()])
    assert "units_answer_contradicts_evidence" not in codes(doc)
    assert doc["files"][0]["units_answer"] == {"status": "answered", "unit": "mm"}
    assert doc["files"][0]["grid_spacing_median"] == {"value": 8000.0, "count": 4}


def test_a_single_source_key_plan_that_agrees_does_not_hide_wrong_plans(tmp_path, example):
    """The key plan is plausible in mm (6000), the real plans are drawn in metres (6): the plans decide."""
    doc = build_grid_systems(_units_work(tmp_path, example, 6000.0, 6.0), answers=[_mm()])
    (q,) = [q for q in doc["questions"] if q["code"] == "units_answer_contradicts_evidence"]
    assert "median grid spacing 6 drawing units = 0.006 m in mm over 4 spacing(s)" in q["found"]
    assert doc["files"][0]["units_answer"] == {"status": "contradicted", "unit": None}


def test_units_are_flagged_when_every_plan_system_disagrees(tmp_path, example):
    doc = build_grid_systems(_units_work(tmp_path, example, 300.0, 6.0), answers=[_mm()])
    assert "units_answer_contradicts_evidence" in codes(doc)


def test_a_file_with_only_single_source_systems_is_tested_on_all_of_them(tmp_path, example):
    w = Work(tmp_path, example)
    w.add_file("plans.dxf", [_key_plan(6.0)])
    doc = build_grid_systems(w.finish(), answers=[_mm()])
    assert "units_answer_contradicts_evidence" in codes(doc)
    assert doc["files"][0]["grid_spacing_median"] == {"value": 6.0, "count": 14}


def _stadium_parts(msp, *, bulge_in: bool = False, skew_a: float = 0.0, skew_b: float = 0.0) -> None:
    """A stadium of half-length HALF and cap radius RHO centred on the origin, caps `skew_a`/`skew_b` degrees
    off true. Both LINEs run between the ends of cap a (right) shifted by the centre line d."""
    out_a, out_b = (90.0, 270.0) if bulge_in else (-90.0, 90.0), (-90.0, 90.0) if bulge_in else (90.0, 270.0)
    msp.add_arc((HALF, 0.0), RHO, out_a[0] + skew_a, out_a[1] + skew_a)
    msp.add_arc((-HALF, 0.0), RHO, out_b[0] + skew_b, out_b[1] + skew_b)
    a1 = (
        HALF + RHO * math.cos(math.radians(out_a[0] + skew_a)),
        RHO * math.sin(math.radians(out_a[0] + skew_a)),
    )
    a2 = (
        HALF + RHO * math.cos(math.radians(out_a[1] + skew_a)),
        RHO * math.sin(math.radians(out_a[1] + skew_a)),
    )
    for p in (a1, a2):
        msp.add_line(p, (p[0] - 2 * HALF, p[1]))


def test_caps_bulging_toward_each_other_are_no_obround(tmp_path):
    result = run_with(_plain(tmp_path, lambda m: _stadium_parts(m, bulge_in=True)))
    assert result["summary"]["circles"] == 0


def test_a_cap_whose_diameter_is_skewed_is_no_obround(tmp_path):
    for skew in ({"skew_a": 20.0}, {"skew_b": 20.0}):
        result = run_with(_plain(tmp_path, lambda m, s=skew: _stadium_parts(m, **s)))
        assert result["summary"]["circles"] == 0, skew


def test_the_straight_stadium_parts_are_a_bubble(tmp_path):
    """The helper above, unskewed, is accepted (guards the negatives against a broken fixture)."""
    assert run_with(_plain(tmp_path, _stadium_parts))["summary"]["circles"] == 1


def test_a_printed_layer_state_is_read_once_per_layer_name(tmp_path):
    """Two layers, one off: lines on the off layer are left out, lines on the other are kept (the per-layer
    cache must not hand one layer's state to the next)."""

    def fn(msp):
        _grid3(msp)
        msp.doc.layers.add("OFFLAYER").off()
        msp.doc.layers.add("ONLAYER")
        msp.add_line((16000, 0), (16000, 12000), dxfattribs={"layer": "OFFLAYER"})
        _bubble(msp, (16000, -R), "4")
        msp.add_line((19000, 0), (19000, 12000), dxfattribs={"layer": "ONLAYER"})
        _bubble(msp, (19000, -R), "5")

    result = run_with(_plain(tmp_path, fn))
    assert ["1", "2", "3", "5"] in _axes_labels(result)


def _stadium_cases(msp, *, bulge_in: str = "", drop_line: str = "", half: float = HALF, rho: float = RHO):
    """A stadium (half-length `half`, cap radius `rho`) at the origin: `bulge_in` 'a' / 'b' turns that cap
    inward; `drop_line` ('top' or 'bottom') leaves out that LINE."""
    a_range = (90.0, 270.0) if "a" in bulge_in else (-90.0, 90.0)
    b_range = (-90.0, 90.0) if "b" in bulge_in else (90.0, 270.0)
    msp.add_arc((half, 0.0), rho, *a_range)
    msp.add_arc((-half, 0.0), rho, *b_range)
    if drop_line != "top":
        msp.add_line((-half, rho), (half, rho))
    if drop_line != "bottom":
        msp.add_line((-half, -rho), (half, -rho))


@pytest.mark.parametrize("bulge_in", ["a", "b"])
def test_one_cap_bulging_inward_is_no_obround(tmp_path, bulge_in):
    result = run_with(_plain(tmp_path, lambda m: _stadium_cases(m, bulge_in=bulge_in)))
    assert result["summary"]["circles"] == 0


@pytest.mark.parametrize("dropped", ["top", "bottom"])
def test_a_stadium_missing_one_line_is_no_obround(tmp_path, dropped):
    assert (
        run_with(_plain(tmp_path, lambda m: _stadium_cases(m, drop_line=dropped)))["summary"]["circles"] == 0
    )
    assert run_with(_plain(tmp_path, _stadium_cases))["summary"]["circles"] == 1


def test_a_very_long_slot_is_no_obround(tmp_path):
    """A slot 13 radii between the cap centres (a track, a long slotted hole) is not a label bubble."""
    result = run_with(_plain(tmp_path, lambda m: _stadium_cases(m, half=6.5 * RHO)))
    assert result["summary"]["circles"] == 0


def test_two_semicircles_split_by_a_hair_are_a_circle_not_an_obround(tmp_path):
    """A circle drawn as two half arcs whose straight parts are 0.05 radius long: too short for a stadium."""
    result = run_with(_plain(tmp_path, lambda m: _stadium_cases(m, half=0.025 * RHO)))
    assert result["summary"]["circles"] == 0


def test_a_line_inside_a_block_on_layer_zero_is_kept_when_layer_zero_is_off(tmp_path):
    """Layer 0 off hides top-level layer-0 lines; the same layer inside a block is the INSERT's layer, not
    settled by Autodesk, so the block's line stays."""

    def bubble(msp, c, label):
        msp.add_circle(c, R, dxfattribs={"layer": "G"})
        msp.add_text(label, height=TH, dxfattribs={"layer": "G"}).set_placement(
            c, align=TextEntityAlignment.MIDDLE_CENTER
        )

    def fn(msp):
        msp.doc.layers.add("G")
        for x, label in ((0.0, "1"), (6000.0, "2"), (12000.0, "3")):
            msp.add_line((x, 0), (x, 12000), dxfattribs={"layer": "G"})
            bubble(msp, (x, -R), label)
        for y, label in ((2000.0, "A"), (8000.0, "B")):
            msp.add_line((-2000, y), (20000, y), dxfattribs={"layer": "G"})
            bubble(msp, (-2000 - R, y), label)
        blk = msp.doc.blocks.new("AXLINE")
        blk.add_line((0, 0), (0, 12000), dxfattribs={"layer": "0"})
        msp.add_blockref("AXLINE", (18000, 0), dxfattribs={"layer": "G"})
        msp.add_line((16000, 0), (16000, 12000))  # a top-level line on layer 0: hidden
        bubble(msp, (16000, -R), "X")
        bubble(msp, (18000, -R), "4")
        msp.doc.layers.get("0").off()

    result = run_with(_plain(tmp_path, fn))
    assert ["1", "2", "3", "4"] in _axes_labels(result)
    assert result["unpaired_bubbles"]["count"] == 1  # X: its layer-0 line does not print


def test_a_file_of_single_source_systems_counts_each_system_once(tmp_path, example):
    """Only single-source systems: a big key plan (14 spacings of 300) does not outvote the one plan view
    (4 spacings of 8000); the median of the two systems' medians is 4150, plausible in mm."""
    w = Work(tmp_path, example)
    w.add_file("plans.dxf", [_key_plan(300.0), *_plan_views(8000.0, sheets=("model#03",))])
    doc = build_grid_systems(w.finish(), answers=[_mm()])
    assert "units_answer_contradicts_evidence" not in codes(doc)
    assert doc["files"][0]["grid_spacing_median"] == {"value": 4150.0, "count": 18}
