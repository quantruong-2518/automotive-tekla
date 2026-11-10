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
from tekla_harness.grid_system import build_grid_systems, run_grid_systems
from tekla_harness.grids import _LABEL_RE, extract_grids
from tekla_harness.questions import empty_registry
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


def test_lines_and_circles_on_an_undefined_layer_are_still_a_grid(tmp_path):
    """A layer that is used but has no LAYER table row is a plain, printing layer: nothing is dropped."""

    def fn(msp):
        for x, label in ((0.0, "1"), (6000.0, "2"), (12000.0, "3")):
            msp.add_line((x, 0), (x, 12000), dxfattribs={"layer": "NOLAYERROW"})
            msp.add_circle((x, -R), R, dxfattribs={"layer": "NOLAYERROW"})
            msp.add_text(label, height=TH).set_placement((x, -R), align=TextEntityAlignment.MIDDLE_CENTER)
        for y, label in ((2000.0, "A"), (8000.0, "B")):
            msp.add_line((-2000, y), (14000, y), dxfattribs={"layer": "NOLAYERROW"})
            msp.add_circle((-2000 - R, y), R, dxfattribs={"layer": "NOLAYERROW"})
            msp.add_text(label, height=TH).set_placement(
                (-2000 - R, y), align=TextEntityAlignment.MIDDLE_CENTER
            )

    result = run_with(_plain(tmp_path, fn))
    assert family(result, "unknown", "1 2 3")["proposal"]["coordinates"] == "0 2*6000"
    assert not result["summary"]["walk_skipped"]


# --- item 4 (R-a): a bubble pairs with the axis line of the family style ---------------------

TOP = 13132.0  # where the top bubbles sit; the bottom ones sit at 0 (EVAL-3 285 model#01)
XS = (0.0, 3130.0, 6670.0, 10190.0, 14780.0)


def _styled_grid(
    msp,
    *,
    off: float = 110.0,
    bubble_on_wall: bool = False,
    wall_layer: str = "0",
    wall_a: bool = False,
    long_wall: bool = False,
):
    """EVAL-3 285: five vertical axes on layer TRUC / DASHED2, each with a bubble at both ends and the line
    running on past both. Beside the two end axes a short continuous wall line (`wall_layer`) sits `off`
    outside, its end 7 radii from the bottom bubble. With `bubble_on_wall` the end bubbles are centred on the
    wall line instead of on their axis."""
    radius = 340.0
    msp.doc.linetypes.add("DASHED2", pattern=[0.5, 0.25, -0.25])
    msp.doc.layers.add("TRUC", linetype="DASHED2")

    def bubble(c, label):
        msp.add_circle(c, radius)
        msp.add_text(label, height=0.9 * radius).set_placement(c, align=TextEntityAlignment.MIDDLE_CENTER)

    for k, (x, label) in enumerate(zip(XS, "12345", strict=True)):
        msp.add_line((x, -4704), (x, TOP + 3495), dxfattribs={"layer": "TRUC"})
        if long_wall and k == 0:  # a longer layer-0 line through both bubbles of axis 1, far past each
            msp.add_line((x, -6000), (x, TOP + 6000), dxfattribs={"layer": wall_layer})
        wall_x = x - off if k == 0 else x + off
        end = k in (0, 4)
        if end:
            msp.add_line((wall_x, 2460), (wall_x, 7440), dxfattribs={"layer": wall_layer})
        bx = wall_x if end and bubble_on_wall else x
        bubble((bx, 0.0), label)
        bubble((bx, TOP), label)
    if wall_a:  # a wall line 90 under axis a, starting 7.9 radii from its left bubble
        msp.add_line((1188.0, 3910.0), (11188.0, 3910.0), dxfattribs={"layer": wall_layer})
    for y, label in ((4000.0, "a"), (9000.0, "b")):
        msp.add_line((-4500 if wall_a else -3500, y), (XS[-1] + 3500, y), dxfattribs={"layer": "TRUC"})
        bubble((-1500.0, y), label)
        bubble((XS[-1] + 1500.0, y), label)


def test_a_bubble_pairs_with_the_axis_line_of_the_family_style(tmp_path):
    """EVAL-3 285: the bubble at the foot of axes 1 and 5 ended a layer-0 wall line 110 away while its own
    TRUC / DASHED2 axis ran on past both bubbles: spacings 3240 / 4700 instead of 3130 / 4590."""
    result = run_with(_plain(tmp_path, _styled_grid))
    numbers = family(result, "unknown", "1 2 3 4 5")
    assert numbers["proposal"]["coordinates"] == "0 3130 3540 3520 4590"
    assert {(a["line"]["layer"], a["line"]["linetype"]) for a in numbers["axes"]} == {("TRUC", "DASHED2")}
    assert [len(a["bubbles"]) for a in numbers["axes"]] == [2] * 5
    assert not questions(result, "grid_axis_layer_mismatch")
    assert result["unpaired_bubbles"]["count"] == 0


def test_the_other_end_of_a_style_line_is_not_left_on_a_wall_line(tmp_path):
    """EVAL-3 285: axis `a` had a bubble at each end; the right one ended the DASHED2 axis, the left one
    a wall line 90 under it, so the family read `a a b c` with a 90 spacing."""
    result = run_with(_plain(tmp_path, lambda m: _styled_grid(m, wall_a=True)))
    letters = family(result, "unknown", "a b")
    assert letters["proposal"]["coordinates"] == "0 5000"
    assert [len(a["bubbles"]) for a in letters["axes"]] == [2, 2]
    assert not questions(result, "grid_label_duplicate")
    assert result["unpaired_bubbles"]["count"] == 0


def test_a_tie_between_styles_is_no_style_majority(tmp_path):
    """Two axes on each of three layers: no style leads, so a bubble keeps the nearer line it ends even
    though a line of another style also passes through its centre."""

    def fn(msp):
        for name in "ABC":
            msp.doc.layers.add(name)
        for x, label, layer in (
            (0.0, "1", "A"),
            (6000.0, "2", "A"),
            (12000.0, "3", "B"),
            (18000.0, "4", "B"),
        ):
            msp.add_line((x, 0), (x, 8000), dxfattribs={"layer": layer})
            msp.add_circle((x, -340), 340)
            msp.add_text(label, height=300).set_placement((x, -340), align=TextEntityAlignment.MIDDLE_CENTER)
        msp.add_line((12050, 300), (12050, 8000), dxfattribs={"layer": "A"})  # farther end, passes 50 off
        for y, label in ((2000.0, "a"), (6000.0, "b")):
            msp.add_line((-1500, y), (19500, y), dxfattribs={"layer": "C"})
            msp.add_circle((-1500 - 340, y), 340)
            msp.add_text(label, height=300).set_placement(
                (-1500 - 340, y), align=TextEntityAlignment.MIDDLE_CENTER
            )

    result = run_with(_plain(tmp_path, fn))
    numbers = family(result, "unknown", "1 2 3 4")
    assert [a["line"]["layer"] for a in numbers["axes"]] == ["A", "A", "B", "B"]


def test_a_longer_line_of_another_style_does_not_win_the_style_pairing(tmp_path):
    """Axis 1 also has a longer layer-0 line through both bubbles: the sheet's style line stays the pair."""
    result = run_with(_plain(tmp_path, lambda m: _styled_grid(m, long_wall=True)))
    numbers = family(result, "unknown", "1 2 3 4 5")
    assert {a["line"]["layer"] for a in numbers["axes"]} == {"TRUC"}
    assert numbers["proposal"]["coordinates"] == "0 3130 3540 3520 4590"


def test_the_wall_line_under_the_bubble_stays_when_the_axis_is_off_its_centre(tmp_path):
    """The family-style axis passes 200 from the end bubbles' centres (> 0.35 radius): not through them, so
    the wall line they sit on stays their pair."""
    result = run_with(_plain(tmp_path, lambda m: _styled_grid(m, off=200.0, bubble_on_wall=True)))
    layers = {a["line"]["layer"] for a in family(result, "unknown", "1 2 3 4 5")["axes"]}
    assert layers == {"0", "TRUC"}


def test_an_end_bubble_takes_the_style_line_it_ends_before_a_nearer_wall_line(tmp_path):
    """Both lines end near the bubble; the wall line starts nearer, the axis passes through the centre."""

    def fn(msp):
        msp.doc.linetypes.add("DASHED2", pattern=[0.5, 0.25, -0.25])
        msp.doc.layers.add("TRUC", linetype="DASHED2")
        for k, (x, label) in enumerate(zip((0.0, 3000.0, 6000.0, 9000.0), "1234", strict=True)):
            msp.add_line((x, 0), (x, 8000), dxfattribs={"layer": "TRUC"})
            wall = k == 0
            if wall:  # a wall line 100 outside the first axis, starting nearer the bubble
                msp.add_line((x - 100.0, -200), (x - 100.0, 8000), dxfattribs={"layer": "0"})
            bx = x - 100.0 if wall else x
            msp.add_circle((bx, -340), 340)
            msp.add_text(label, height=300).set_placement((bx, -340), align=TextEntityAlignment.MIDDLE_CENTER)
        for y, label in ((2000.0, "a"), (6000.0, "b")):
            msp.add_line((-1500, y), (10500, y), dxfattribs={"layer": "TRUC"})
            msp.add_circle((-1500 - 340, y), 340)
            msp.add_text(label, height=300).set_placement(
                (-1500 - 340, y), align=TextEntityAlignment.MIDDLE_CENTER
            )

    result = run_with(_plain(tmp_path, fn))
    assert family(result, "unknown", "1 2 3 4")["proposal"]["coordinates"] == "0 3*3000"


def test_the_nearer_line_still_wins_without_a_style_majority(tmp_path):
    def fn(msp):
        # two bubbles only, on different styles: nothing to prefer
        msp.doc.layers.add("A")
        msp.doc.layers.add("B")
        msp.add_line((0, 0), (0, 8000), dxfattribs={"layer": "A"})
        msp.add_line((3000, 0), (3000, 8000), dxfattribs={"layer": "B"})
        for x, label in ((0.0, "1"), (3000.0, "2")):
            msp.add_circle((x, -340), 340)
            msp.add_text(label, height=300).set_placement((x, -340), align=TextEntityAlignment.MIDDLE_CENTER)
        for y, label in ((2000.0, "a"), (6000.0, "b")):
            msp.add_line((-1500, y), (4500, y), dxfattribs={"layer": "A"})
            msp.add_circle((-1500 - 340, y), 340)
            msp.add_text(label, height=300).set_placement(
                (-1500 - 340, y), align=TextEntityAlignment.MIDDLE_CENTER
            )

    result = run_with(_plain(tmp_path, fn))
    numbers = family(result, "unknown", "1 2")
    assert [a["line"]["layer"] for a in numbers["axes"]] == ["A", "B"]


# --- item 3 (F2b): axes that do not match their family are no axes ------------------------------------


def _odd_family(
    msp,
    *,
    odd_r=False,
    odd_h=False,
    odd_block=False,
    odd_style=False,
    n=5,
    n_odd=1,
    odd_radius=250.0,
    two_bubbles=False,
):
    """`n` axes 1 2 3 .. of one family: bubbles of radius 350 from block KY, label height 315, lines on layer
    CEN. The last `n_odd` axes deviate in the attributes asked for: radius `odd_radius` (still from KY,
    scaled), label height 190 (at most 1.2 radius), a loose circle instead of block KY, a line on layer DUT
    (another linetype). `two_bubbles`: the odd axis has no line, only two bubbles facing each other."""
    doc = msp.doc
    doc.linetypes.add("CENTER2", pattern=[0.5, 0.25, -0.25])
    doc.linetypes.add("HIDDEN2", pattern=[0.3, 0.15, -0.15])
    doc.layers.add("CEN", linetype="CENTER2")
    doc.layers.add("DUT", linetype="HIDDEN2")
    doc.blocks.new("KY").add_circle((0, 0), 350)
    xs = [6000.0 * k for k in range(n)]
    first_odd = n - n_odd
    for k, (x, label) in enumerate(zip(xs, "123456", strict=False)):
        odd = k >= first_odd
        r = odd_radius if odd and odd_r else 350.0
        h = min(190.0 if odd and odd_h else 315.0, 1.2 * r)
        layer = "DUT" if odd and odd_style else "CEN"
        if not (odd and two_bubbles):
            msp.add_line((x, 0), (x, 20000 if odd else 12000), dxfattribs={"layer": layer})
        for c in ((x, -350.0), (x, 12350.0)) if odd and two_bubbles else ((x, -350.0),):
            if odd and odd_block:
                msp.add_circle(c, r)
            else:
                msp.add_blockref("KY", c, dxfattribs={"xscale": r / 350.0, "yscale": r / 350.0})
            msp.add_text(label, height=h).set_placement(c, align=TextEntityAlignment.MIDDLE_CENTER)
    for y, label in ((2000.0, "A"), (8000.0, "B")):
        msp.add_line((-2000, y), (xs[-1] + 2000, y), dxfattribs={"layer": "CEN"})
        msp.add_blockref("KY", (-2000 - 350.0, y))
        msp.add_text(label, height=315.0).set_placement(
            (-2000 - 350.0, y), align=TextEntityAlignment.MIDDLE_CENTER
        )


def _numbers(result) -> list[str]:
    return [lbl for lbls in _axes_labels(result) for lbl in lbls if lbl.isdigit()]


@pytest.mark.parametrize(
    "kw",
    [
        {"odd_r": True, "odd_block": True},
        {"odd_h": True, "odd_style": True},
        {"odd_block": True, "odd_style": True},
        {"odd_r": True, "odd_style": True},
        {"odd_r": True, "odd_h": True, "odd_block": True},
    ],
)
def test_an_axis_that_differs_from_its_family_in_two_ways_is_no_axis(tmp_path, kw):
    """EVAL-4 264 / 271 / 278: a r 250 bubble on a HIDDEN line among r 350 axes on CENTER lines; a section
    marker among the grid bubbles: two or more of size, block and line differ."""
    result = run_with(_plain(tmp_path, lambda m: _odd_family(m, **kw)))
    assert _numbers(result) == ["1", "2", "3", "4"]
    assert family(result, "unknown", "1 2 3 4")["proposal"]["coordinates"] == "0 3*6000"
    # not dropped silently: the bubble is listed as unpaired and the warnings say why
    assert [b["label"] for b in result["unpaired_bubbles"]["listed"]] == ["5"]
    assert "set aside" in _warnings(result) and "5" in _warnings(result)
    assert result["groups"][0]["bbox"][3] == 12000.0  # the view no longer spans the taller axis set aside


@pytest.mark.parametrize(
    "kw",
    [{"odd_r": True}, {"odd_h": True}, {"odd_block": True}, {"odd_style": True}],
    ids=lambda kw: next(iter(kw)),
)
def test_an_axis_that_differs_in_one_way_only_stays(tmp_path, kw):
    result = run_with(_plain(tmp_path, lambda m: _odd_family(m, **kw)))
    assert _numbers(result) == ["1", "2", "3", "4", "5"]


def test_two_odd_axes_of_six_are_both_set_aside(tmp_path):
    kw = {"odd_r": True, "odd_block": True, "n": 6, "n_odd": 2}
    result = run_with(_plain(tmp_path, lambda m: _odd_family(m, **kw)))
    assert _numbers(result) == ["1", "2", "3", "4"]
    assert sorted(b["label"] for b in result["unpaired_bubbles"]["listed"]) == ["5", "6"]


def test_without_a_majority_nothing_is_set_aside(tmp_path):
    """Two axes of each kind in a family of four: neither is the family."""
    kw = {"odd_r": True, "odd_block": True, "n": 4, "n_odd": 2}
    result = run_with(_plain(tmp_path, lambda m: _odd_family(m, **kw)))
    assert _numbers(result) == ["1", "2", "3", "4"]
    assert "set aside" not in _warnings(result)


def test_a_family_of_two_is_never_judged(tmp_path):
    def fn(msp):
        doc = msp.doc
        doc.blocks.new("KY").add_circle((0, 0), 350)
        msp.add_line((0, 0), (0, 12000))
        msp.add_line((6000, 0), (6000, 12000))
        msp.add_blockref("KY", (0, -350.0))
        msp.add_text("1", height=315.0).set_placement((0, -350.0), align=TextEntityAlignment.MIDDLE_CENTER)
        msp.add_circle((6000, -250.0), 250.0)
        msp.add_text("2", height=190.0).set_placement((6000, -250.0), align=TextEntityAlignment.MIDDLE_CENTER)
        for y, label in ((2000.0, "A"), (8000.0, "B")):
            msp.add_line((-2000, y), (8000, y))
            _bubble(msp, (-2000 - R, y), label)

    result = run_with(_plain(tmp_path, fn))
    assert _numbers(result) == ["1", "2"]


def test_obround_bubbles_of_a_family_with_different_label_lengths_stay(tmp_path):
    """Obrounds of one family differ in length with the label (EVAL-4 180: letters 811 to 1011): within 20 %
    of the family median the radius is no deviation."""

    def fn(msp):
        for x, label, half in (
            (0.0, "1", 328.0),
            (6000.0, "2", 328.0),
            (12000.0, "3", 400.0),
            (18000.0, "4", 328.0),
        ):
            msp.add_line((x, 0), (x, 12000))
            _obround(msp, (x, -(half + RHO)), label, half=half)
        for y, label in ((2000.0, "A"), (8000.0, "B")):
            msp.add_line((-2000, y), (20000, y))
            _obround(msp, (-2000 - R_EQ, y), label)

    result = run_with(_plain(tmp_path, fn))
    assert _numbers(result) == ["1", "2", "3", "4"]


def test_a_family_of_three_is_judged(tmp_path):
    kw = {"odd_r": True, "odd_block": True, "n": 3, "n_odd": 1}
    result = run_with(_plain(tmp_path, lambda m: _odd_family(m, **kw)))
    assert _numbers(result) == ["1", "2"]


@pytest.mark.parametrize(
    ("radius", "set_aside"), [(297.5, False), (245.0, True), (455.0, True), (420.0, False)]
)
def test_the_size_tolerance_is_twenty_percent_of_the_family_median(tmp_path, radius, set_aside):
    """With the block also off, the axis goes only when its radius is more than 20 % from the median (350)."""
    kw = {"odd_r": True, "odd_block": True, "odd_radius": radius}
    result = run_with(_plain(tmp_path, lambda m: _odd_family(m, **kw)))
    assert (_numbers(result) == ["1", "2", "3", "4"]) is set_aside


def test_a_tie_in_the_block_is_not_a_majority(tmp_path):
    """Two axes with one block and two with another: neither block is the family's, so the block is no
    deviation, even when the size of all four is far from their median."""
    kw = {"odd_r": True, "odd_block": True, "n": 4, "n_odd": 2, "odd_radius": 100.0}
    result = run_with(_plain(tmp_path, lambda m: _odd_family(m, **kw)))
    assert _numbers(result) == ["1", "2", "3", "4"]
    assert "set aside" not in _warnings(result)


def test_an_axis_without_a_line_has_no_line_deviation(tmp_path):
    """A two-bubble axis (no line between its bubbles) differs in size only: it stays."""
    kw = {"odd_r": True, "two_bubbles": True}
    result = run_with(_plain(tmp_path, lambda m: _odd_family(m, **kw)))
    assert _numbers(result) == ["1", "2", "3", "4", "5"]
    assert "set aside" not in _warnings(result)


# --- item 6 (F2e): `*` in labels, two stacked views on one sheet ------------------------------------


@pytest.mark.parametrize("text", ["2*", "A*", "12*", "1A*", "3'*"])
def test_a_star_may_end_a_label(text):
    assert _LABEL_RE.match(text)


@pytest.mark.parametrize("text", ["*", "*2", "2*3", "**", "2**"])
def test_a_star_elsewhere_is_no_label(text):
    assert not _LABEL_RE.match(text)


def test_an_intermediate_axis_with_a_star_is_an_axis(tmp_path):
    """EVAL-4 278: axis `2*` between 2 and 3 was an empty bubble and its line `grid_axis_unlabelled`."""

    def fn(msp):
        xs = (0.0, 5850.0, 7910.0, 10850.0, 15000.0)
        for x, label in zip(xs, ("1", "2", "2*", "3", "4"), strict=True):
            msp.add_line((x, 0), (x, 12000))
            _bubble(msp, (x, -R), label)
        for y, label in ((2000.0, "A"), (6180.0, "B")):
            msp.add_line((-2000, y), (17000, y))
            _bubble(msp, (-2000 - R, y), label)

    result = run_with(_plain(tmp_path, fn))
    fam = family(result, "unknown", "1 2 2* 3 4")
    assert fam["proposal"]["coordinates"] == "0 5850 2060 2940 4150"
    assert not questions(result, "grid_axis_unlabelled")
    assert not questions(result, "grid_label_order_nonmonotonic")


def _stacked(msp, letters=("a", "b", "a", "b")):
    """Two plans stacked on one sheet: vertical axes 1..4 run through both (their labels are printed once),
    each plan has its own horizontal axes."""
    for x, label in zip((0.0, 5850.0, 10850.0, 15000.0), "1234", strict=True):
        msp.add_line((x, -20000), (x, 12000))
        _bubble(msp, (x, -20000 - R), label)
    for y, label in zip((-14000.0, -9820.0, 2000.0, 6180.0), letters, strict=True):
        msp.add_line((-2000, y), (17000, y))
        _bubble(msp, (-2000 - R, y), label)


def test_two_stacked_views_on_one_sheet_are_two_groups(tmp_path):
    """EVAL-4 278 KC-01: the horizontal axes a b a b of two stacked plans were one family with duplicate
    labels; the vertical axes (printed once) belong to both plans."""
    result = run_with(_plain(tmp_path, _stacked))
    assert len(result["groups"]) == 2
    for g in result["groups"]:
        assert sorted(f["proposal"]["labels"] for f in g["families"]) == ["1 2 3 4", "a b"]
        assert {f["proposal"]["coordinates"] for f in g["families"]} == {"0 5850 5000 4150", "0 4180"}
    assert not questions(result, "grid_label_duplicate")
    assert not questions(result, "grid_label_order_nonmonotonic")
    ids = [a["axis_id"] for g in result["groups"] for f in g["families"] for a in f["axes"]]
    assert len(ids) == len(set(ids)) == 12
    assert (
        result["summary"]["bubbles_paired"] == 8
    )  # each bubble once, though both views use the vertical axes


def test_a_label_repeated_in_one_run_is_not_a_stacked_view(tmp_path):
    """`1 2 2` (a typo): the second run is one axis long, so the view stays whole and asks the duplicate."""

    def fn(msp):
        for x, label in zip((0.0, 5850.0, 10850.0), ("1", "2", "2"), strict=True):
            msp.add_line((x, 0), (x, 12000))
            _bubble(msp, (x, -R), label)
        for y, label in ((2000.0, "A"), (6180.0, "B")):
            msp.add_line((-2000, y), (12000, y))
            _bubble(msp, (-2000 - R, y), label)

    result = run_with(_plain(tmp_path, fn))
    assert len(result["groups"]) == 1 and questions(result, "grid_label_duplicate")


def test_runs_with_different_labels_are_not_stacked_views(tmp_path):
    """`a b a c`: the second run is not a repeat of the first (rebar marks among grid labels)."""
    result = run_with(_plain(tmp_path, lambda m: _stacked(m, letters=("a", "b", "a", "c"))))
    assert len(result["groups"]) == 1 and questions(result, "grid_label_duplicate")


def test_a_b_a_is_not_a_stacked_view(tmp_path):
    result = run_with(_plain(tmp_path, lambda m: _stacked_three(m)))
    assert len(result["groups"]) == 1 and questions(result, "grid_label_duplicate")


def _stacked_three(msp):
    for x, label in zip((0.0, 5850.0, 10850.0), "123", strict=True):
        msp.add_line((x, -20000), (x, 12000))
        _bubble(msp, (x, -20000 - R), label)
    for y, label in zip((-14000.0, -9820.0, 2000.0), ("a", "b", "a"), strict=True):
        msp.add_line((-2000, y), (12000, y))
        _bubble(msp, (-2000 - R, y), label)


def test_two_repeating_families_are_not_split(tmp_path):
    """Both directions repeat their labels (2 x 2 plans around shared lines): which family to cut by is not
    clear, so the view stays whole and the duplicates are asked."""

    def fn(msp):
        xs = (0.0, 5850.0, 30000.0, 35850.0)
        ys = (-14000.0, -9820.0, 2000.0, 6180.0)
        for x, label in zip(xs, "1212", strict=True):
            msp.add_line((x, -20000), (x, 12000))
            _bubble(msp, (x, -20000 - R), label)
        for y, label in zip(ys, "abab", strict=True):
            msp.add_line((-2000, y), (38000, y))
            _bubble(msp, (-2000 - R, y), label)

    result = run_with(_plain(tmp_path, fn))
    assert len(result["groups"]) == 1 and questions(result, "grid_label_duplicate")


def test_two_axes_with_one_label_are_not_two_stacked_views(tmp_path):
    result = run_with(_plain(tmp_path, lambda m: _simple_grid(m, xs=(0.0, 6000.0), labels=("1", "1"))))
    assert len(result["groups"]) == 1 and questions(result, "grid_label_duplicate")


# --- item 5 (F2d): a stray two-axis family is not a grid system ----------------------------------------


def _plans_work(
    tmp_path, example, extra: list[dict[str, Any]], *, second_file: list[dict[str, Any]] | None = None
):
    w = Work(tmp_path, example)
    w.add_file("plans.dxf", [*_plan_views(6000.0, sheets=("model#03", "model#04")), *extra])
    if second_file is not None:
        w.add_file("other.dxf", second_file)
    return w.finish()


def _stray(gid="V009", sheet="model#09", labels=("x", "y"), spacing=250.0, fid="F009"):
    return view(gid, sheet, fam(fid, list(labels), [spacing] * (len(labels) - 1)))


def test_a_two_axis_family_seen_once_beside_the_plans_is_not_a_system(tmp_path, example):
    """EVAL-3 286 `b bt` and 290 `8 1` / `17 10` / `6 1` / `3 16`: two labels 250 apart seen on one sheet
    beside a plan grid read on many sheets: rebar or pile marks drawn like bubbles."""
    doc = build_grid_systems(_plans_work(tmp_path, example, [_stray()]), answers=[])
    assert [len(s["directions"]) for s in doc["systems"]] == [2]
    (row,) = doc["unassigned_families"]
    assert (row["file"], row["sheet"], row["group_id"], row["family_id"], row["labels"]) == (
        "plans.dxf",
        "model#09",
        "V009",
        "F009",
        "x y",
    )
    assert "one direction" in row["reason"] and "S001" in row["reason"]
    assert doc["summary"]["families_unassigned"] == 1
    assert codes(doc).count("grid_system_axis_unassigned") == 1  # the plan system only


def test_without_a_main_system_the_two_axis_family_is_kept(tmp_path, example):
    w = Work(tmp_path, example)
    w.add_file("plans.dxf", [_stray()])
    doc = build_grid_systems(w.finish(), answers=[])
    assert len(doc["systems"]) == 1 and not doc["unassigned_families"]


def test_a_main_system_seen_in_one_view_makes_a_stray(tmp_path, example):
    """EVAL-4 180: every plan is seen once (halves of one grid), so no system has two independent views, but a
    two-direction system with three or more axes in each direction is still the file's grid."""
    w = Work(tmp_path, example)
    w.add_file("plans.dxf", [*_plan_views(6000.0, sheets=("model#03",)), _stray()])
    doc = build_grid_systems(w.finish(), answers=[])
    assert [len(s["directions"]) for s in doc["systems"]] == [2]
    assert [u["labels"] for u in doc["unassigned_families"]] == ["x y"]


def test_a_longer_one_direction_family_seen_once_is_a_stray_too(tmp_path, example):
    """EVAL-4 180 model#05/06 (3D views) and 278-like details: any number of axes, one direction, one view."""
    stray = _stray(labels=("x", "y", "z", "w"))
    doc = build_grid_systems(_plans_work(tmp_path, example, [stray]), answers=[])
    assert len(doc["systems"]) == 1
    assert [u["labels"] for u in doc["unassigned_families"]] == ["x y z w"]


def test_a_two_direction_system_of_two_axes_is_no_main_system(tmp_path, example):
    """Two axes per direction is too little to be the file's grid: the one-direction family stays."""
    w = Work(tmp_path, example)
    small = view(
        "V002", "model#03", fam("F003", ["A", "B"], [6000.0], angle=0.0), fam("F004", ["1", "2"], [6000.0])
    )
    w.add_file("plans.dxf", [small, _stray(labels=("x", "y", "z"))])
    doc = build_grid_systems(w.finish(), answers=[])
    assert len(doc["systems"]) == 2 and not doc["unassigned_families"]


def test_a_three_axis_family_seen_on_two_sheets_is_kept(tmp_path, example):
    extra = [_stray(labels=("x", "y", "z")), _stray("V010", "model#10", labels=("x", "y", "z"), fid="F010")]
    doc = build_grid_systems(_plans_work(tmp_path, example, extra), answers=[])
    assert len(doc["systems"]) == 2 and not doc["unassigned_families"]


def test_a_two_axis_family_seen_on_two_sheets_is_kept(tmp_path, example):
    extra = [_stray(), _stray("V010", "model#10", fid="F010")]
    doc = build_grid_systems(_plans_work(tmp_path, example, extra), answers=[])
    assert len(doc["systems"]) == 2 and not doc["unassigned_families"]


def test_a_two_axis_family_of_another_file_is_kept(tmp_path, example):
    work = _plans_work(tmp_path, example, [], second_file=[_stray()])
    doc = build_grid_systems(work, answers=[])
    assert len(doc["systems"]) == 2 and not doc["unassigned_families"]


def test_a_two_direction_stray_is_kept(tmp_path, example):
    """Only one-direction families are dropped: a second direction makes a grid the engineer may want."""
    both = view(
        "V009", "model#09", fam("F009", ["x", "y"], [250.0], angle=0.0), fam("F010", ["p", "q"], [250.0])
    )
    doc = build_grid_systems(_plans_work(tmp_path, example, [both]), answers=[])
    assert len(doc["systems"]) == 2 and not doc["unassigned_families"]


# --- item 7 (F2f): a one-direction view that contradicts the file's plans is no grid ---------------


def _plan(msp, ox: float, xs=(0.0, 5850.0, 10850.0, 15000.0), labels="1234") -> None:
    """A two-direction plan at x offset `ox`: vertical axes `labels` at `ox + xs`, horizontal axes a, b."""
    for x, label in zip(xs, labels, strict=True):
        msp.add_line((ox + x, 0), (ox + x, 12000))
        _bubble(msp, (ox + x, -R), label)
    for y, label in ((2000.0, "a"), (6180.0, "b")):
        msp.add_line((ox - 2000, y), (ox + xs[-1] + 2000, y))
        _bubble(msp, (ox - 2000 - R, y), label)


def _elevation(msp, ox: float, xs=(0.0, 10107.0, 15299.0), labels="124") -> None:
    """Vertical axes only (a column elevation): no second direction, tall lines."""
    for x, label in zip(xs, labels, strict=True):
        msp.add_line((ox + x, 0), (ox + x, 30000))
        _bubble(msp, (ox + x, 30000 + R), label)


def _plans_and_elevation(msp, plans: int = 3, **kw) -> None:
    for k in range(plans):
        _plan(msp, 40000.0 * k)
    _elevation(msp, 200000.0, **kw)


def test_an_elevation_that_contradicts_the_plans_is_set_aside(tmp_path):
    """EVAL-4 278 KT-08: a column elevation shows axes 1 2 4 at 10107 / 5192, while every plan has 1 2 2* 3 4
    at 5850 / 5000 / 4150; it became its own system and raised order and spacing mismatches."""
    result = run_with(_plain(tmp_path, _plans_and_elevation))
    assert len(result["groups"]) == 3
    assert not questions(result, "grid_spacing_cross_sheet_mismatch")
    assert not questions(result, "grid_label_order_mismatch")
    assert sorted(b["label"] for b in result["unpaired_bubbles"]["listed"]) == ["1", "2", "4"]
    assert "contradict" in _warnings(result) and "set aside" in _warnings(result)


def test_an_elevation_that_agrees_with_the_plans_stays(tmp_path):
    result = run_with(
        _plain(tmp_path, lambda m: _plans_and_elevation(m, xs=(0.0, 5850.0, 10850.0), labels="123"))
    )
    assert len(result["groups"]) == 4
    assert not result["unpaired_bubbles"]["listed"]


def test_one_other_view_is_not_enough_to_set_a_view_aside(tmp_path):
    result = run_with(_plain(tmp_path, lambda m: _plans_and_elevation(m, plans=1)))
    assert len(result["groups"]) == 2
    assert questions(result, "grid_spacing_cross_sheet_mismatch")


def test_a_two_direction_plan_is_never_set_aside(tmp_path):
    """A fourth plan with another spacing is a real conflict for the engineer, not an elevation."""

    def fn(msp):
        for k in range(3):
            _plan(msp, 40000.0 * k)
        _plan(msp, 200000.0, xs=(0.0, 6000.0, 10850.0, 15000.0))

    result = run_with(_plain(tmp_path, fn))
    assert len(result["groups"]) == 4
    assert questions(result, "grid_spacing_cross_sheet_mismatch")


def test_views_that_disagree_among_themselves_do_not_outvote_a_view(tmp_path):
    """Two plans that do not agree with each other give no main grid to measure the elevation against."""

    def fn(msp):
        _plan(msp, 0.0)
        _plan(msp, 40000.0, xs=(0.0, 6000.0, 10850.0, 15000.0))
        _elevation(msp, 200000.0)

    result = run_with(_plain(tmp_path, fn))
    assert len(result["groups"]) == 3


def test_an_elevation_that_agrees_with_one_plan_is_not_set_aside(tmp_path):
    """Two plans give 1 2 4 at 5850 / 9150, a third at 6000 / 9000; the elevation follows the third: it does
    not contradict every plan."""

    def fn(msp):
        _plan(msp, 0.0)
        _plan(msp, 40000.0)
        _plan(msp, 80000.0, xs=(0.0, 6000.0, 10850.0, 15000.0))
        _elevation(msp, 200000.0, xs=(0.0, 6000.0, 15000.0))

    assert len(run_with(_plain(tmp_path, fn))["groups"]) == 4


def test_a_view_that_shares_one_label_with_a_plan_is_not_compared_with_it(tmp_path):
    """A fourth plan sharing only axis 4 with the elevation says nothing about it."""

    def fn(msp):
        _plans_and_elevation(msp)
        _plan(msp, 120000.0, xs=(0.0, 6000.0, 12000.0, 18000.0), labels="4567")

    result = run_with(_plain(tmp_path, fn))
    assert len(result["groups"]) == 4  # the three plans and the fourth; the elevation is set aside
    assert sorted(b["label"] for b in result["unpaired_bubbles"]["listed"]) == ["1", "2", "4"]


def test_a_different_order_is_a_contradiction_even_with_equal_spacings(tmp_path):
    """1 3 2 at 0 / 12000 / 18000 has the distances of 1 2 3 on a grid of 6000 but not its order."""

    def fn(msp):
        for k in range(3):
            _plan(msp, 40000.0 * k, xs=(0.0, 6000.0, 12000.0, 18000.0))
        _elevation(msp, 200000.0, xs=(0.0, 12000.0, 18000.0), labels="132")

    result = run_with(_plain(tmp_path, fn))
    assert len(result["groups"]) == 3 and "set aside" in _warnings(result)


@pytest.mark.parametrize(("shift", "set_aside"), [(0.3, False), (1.0, False), (4.0, True)])
def test_an_elevation_within_the_drafting_tolerance_agrees(tmp_path, shift, set_aside):
    """Spacings 0.3 apart are inside half the rounding step, 1.0 inside 2e-4 of 5850, 4.0 neither."""

    def fn(msp):
        for k in range(3):
            _plan(msp, 40000.0 * k, xs=(0.0, 5850.0, 10850.0, 15000.0))
        _elevation(msp, 200000.0, xs=(0.0, 5850.0 + shift, 15000.0 + shift), labels="124")

    groups = len(run_with(_plain(tmp_path, fn))["groups"])
    assert (groups == 3) is set_aside


def test_an_elevation_with_smaller_spacings_is_set_aside_too(tmp_path):
    result = run_with(_plain(tmp_path, lambda m: _plans_and_elevation(m, xs=(0.0, 3000.0, 4500.0))))
    assert len(result["groups"]) == 3


def test_half_the_rounding_step_is_agreement_on_small_spacings(tmp_path):
    """On spacings of 1000 the drafting tolerance is 0.2; half the rounding step (0.5) is the wider bound."""

    def fn(msp):
        for k in range(3):
            _plan(msp, 40000.0 * k, xs=(0.0, 1000.0, 2000.0, 3000.0))
        _elevation(msp, 200000.0, xs=(0.0, 1000.4, 3000.4), labels="124")

    assert len(run_with(_plain(tmp_path, fn))["groups"]) == 4


# --- item 8 (V7): the grid-system stdout does not call a simulated answer a closed question -----------------


def test_the_grid_system_stdout_labels_answered_and_open_counts(tmp_path, example):
    """`blocking_open 0` was printed for a question that only a simulated answer touched and that
    `harness status` still keeps blocking."""
    work = Path(tmp_path)
    w = Work(work, example)
    w.add_file("plans.dxf", _plan_views(6000.0))
    w.finish()
    (work / "question-registry.json").write_text(json.dumps(empty_registry("demo-project")), encoding="utf-8")
    first = run_grid_systems(work, svg=False).summary
    assert first["answered"] == 0
    assert first["blocking_without_engineer_answer"] == first["blocking_open"] >= 1
    assert "simulated" in first["counts_note"] and "harness status" in first["counts_note"]

    questions_doc = json.loads((work / "grid-system-questions.json").read_text(encoding="utf-8"))
    axis = next(q for q in questions_doc["questions"] if q["code"] == "grid_system_axis_unassigned")
    answer = {
        **ans("grid_system_axis_unassigned", axis["file"], {"dir1": "Y", "dir2": "X"}),
        "key": axis["key"],
        "question_id": axis["id"],
        "answered_by_role": "simulated",
    }
    doc = {"schema_version": "0.1", "project_id": "demo-project", "answers": [answer]}
    (work / "answers.json").write_text(json.dumps(doc), encoding="utf-8")
    second = run_grid_systems(work, svg=False).summary
    assert second["answered"] == 1
    assert second["blocking_open"] == first["blocking_open"] - 1  # the document counts the simulated answer
    assert (
        second["blocking_without_engineer_answer"] == first["blocking_without_engineer_answer"]
    )  # not the gate

    select = next(
        q
        for q in json.loads((work / "grid-system-questions.json").read_text())["questions"]
        if q["code"] == "grid_system_select"
    )
    by_engineer = {
        **ans("grid_system_select", None, {}),
        "key": select["key"],
        "question_id": select["id"],
        "answered_by_role": "engineer",
    }
    doc["answers"] = [answer, by_engineer]
    (work / "answers.json").write_text(json.dumps(doc), encoding="utf-8")
    third = run_grid_systems(work, svg=False).summary
    assert third["blocking_without_engineer_answer"] == first["blocking_without_engineer_answer"] - 1
