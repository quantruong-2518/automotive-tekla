"""grids: bubbles, axes, views, families, spacings, cross-sheet checks and coordinate proposals.

Fixtures are synthetic (tests/_dxf_fixtures.py); no sample drawing text is used.
"""

from __future__ import annotations

import json
import math
import time
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest
from ezdxf.enums import TextEntityAlignment
from ezdxf.filemanagement import new

from _dxf_fixtures import SHEET2_X, TH, R, _frame, _frame_block, build_set
from tekla_harness import grids as grids_mod
from tekla_harness.extract_text import extract_text
from tekla_harness.grids import _LABEL_RE, coordinate_string, extract_grids, rounding_step
from tekla_harness.schemas import validate
from tekla_harness.sheets import extract_sheets


def run(path: Path) -> dict[str, Any]:
    index = extract_text(path)
    sheets = extract_sheets(path, index)
    result = extract_grids(path, index, sheets)
    assert validate("grids", result) == [], validate("grids", result)
    json.dumps(result, allow_nan=False)
    return result


def families(result: dict[str, Any], sheet: str) -> list[dict[str, Any]]:
    return [f for g in result["groups"] if g["sheet"] == sheet for f in g["families"]]


def family(result: dict[str, Any], sheet: str, labels: str) -> dict[str, Any]:
    return next(f for f in families(result, sheet) if f["proposal"] and f["proposal"]["labels"] == labels)


def questions(result: dict[str, Any], code: str) -> list[dict[str, Any]]:
    return [q for q in result["questions"] if q["code"] == code]


@pytest.fixture(scope="module")
def grid_set(tmp_path_factory) -> dict[str, Any]:
    return run(build_set(tmp_path_factory.mktemp("grids")))


@pytest.mark.parametrize(
    ("spacings", "expected"),
    [
        ([6000.0, 6000.0, 6000.0], "0 3*6000"),
        ([5000.0, 4500.0], "0 5000 4500"),
        ([6000.0, 6000.0, 6500.0], "0 2*6000 6500"),
        ([4.5, 4.5], "0 2*4.5"),
        ([], "0"),
    ],
)
def test_coordinate_string(spacings, expected):
    assert coordinate_string(spacings) == expected


def test_rounding_step_keeps_four_significant_digits():
    assert rounding_step([6000.0, 4500.0]) == 1.0
    assert rounding_step([4.5, 6.0]) == pytest.approx(0.001)


def test_two_families_per_view_with_proposals(grid_set):
    vertical = family(grid_set, "model#01", "1 2 3 4")
    horizontal = family(grid_set, "model#01", "A B C")
    assert vertical["proposal"]["coordinates"] == "0 3*6000"
    assert horizontal["proposal"]["coordinates"] == "0 5000 4500"
    assert horizontal["proposal"]["complete"] is True
    assert vertical["direction"] == [0.0, 1.0] and vertical["normal"] == [1.0, 0.0]
    assert horizontal["direction"] == [1.0, 0.0] and horizontal["normal"] == [0.0, 1.0]
    assert vertical["proposal"]["unit"] == "mm" and vertical["proposal"]["status"] == "proposal"
    assert [s["measured"] for s in horizontal["spacings"]] == [5000.0, 4500.0]


def test_labels_come_from_attribs_and_loose_text(grid_set):
    vertical = family(grid_set, "model#01", "1 2 3 4")
    horizontal = family(grid_set, "model#01", "A B C")
    bubble = vertical["axes"][0]["bubbles"][0]
    assert (bubble["label_source"], bubble["tag"], bubble["radius"]) == ("attrib", "AXIS_NO", R)
    assert horizontal["axes"][0]["bubbles"][0]["label_source"] == "text"
    label = vertical["axes"][0]["label"]
    assert label["provenance"]["sheet"] == "model#01" and label["provenance"]["method"] == "dxf_entity"


def test_spacing_provenance_is_derived_from_both_lines(grid_set):
    spacing = family(grid_set, "model#01", "A B C")["spacings"][0]["value"]
    assert spacing["provenance"]["method"] == "derived"
    assert len(spacing["provenance"]["derived_from"]) == 2
    assert spacing["provenance"]["sheet"] == "model#01"


def test_cross_sheet_spacing_mismatch_is_blocking(grid_set):
    q = questions(grid_set, "grid_spacing_cross_sheet_mismatch")
    assert len(q) == 1 and q[0]["blocking"]
    assert q[0]["found"] == "3-4: 6000.0 vs 6500.0"
    statuses = sorted(c["status"] for c in grid_set["cross_checks"])
    assert statuses == ["consistent", "mismatch"]
    s1 = family(grid_set, "model#01", "1 2 3 4")["spacings"]
    assert s1[2]["value"]["confidence"] == "low"  # 3-4 disagrees with the other sheet and nothing agrees


def test_dimension_override_disagreeing_with_spacing(grid_set):
    spacings = family(grid_set, "model#01", "1 2 3 4")["spacings"]
    ev12 = spacings[0]["dimension_evidence"]
    assert [(e["status"], e["text"], e["displayed"]) for e in ev12] == [("differs", "6500", 6500.0)]
    assert spacings[0]["value"]["confidence"] == "low"
    assert [e["status"] for e in spacings[1]["dimension_evidence"]] == ["measured"]
    q = questions(grid_set, "grid_dimension_override_mismatch")
    assert len(q) == 1 and q[0]["blocking"] and "6500" in q[0]["found"]
    assert family(grid_set, "model#01", "1 2 3 4")["proposal"]["complete"] is False


def test_skewed_axis_is_its_own_family_and_a_question(grid_set):
    skewed = [f for f in families(grid_set, "model#01") if f["proposal"] is None]
    assert len(skewed) == 1 and skewed[0]["axes"][0]["label"]["value"] == "5"
    assert skewed[0]["angle_deg"] == pytest.approx(80.0)
    assert len(questions(grid_set, "grid_axis_skewed")) == 1


def test_line_with_empty_bubble_is_a_missing_label(grid_set):
    fam = family(grid_set, "model#02", "1 2 3 4")
    assert [(u["offset"], u["empty_bubble"]) for u in fam["unlabelled_lines"]] == [(24500.0, True)]
    assert fam["proposal"]["coordinates"] == "0 2*6000 6500"  # the unlabelled line is NOT used
    assert fam["proposal"]["complete"] is False
    assert len(questions(grid_set, "grid_label_missing")) == 1


def test_tekla_axis_assignment_and_gate1_are_always_asked(grid_set):
    for code in ("grid_family_axis_assignment", "grid_gate1_confirmation"):
        q = questions(grid_set, code)
        assert len(q) == 1
    assert questions(grid_set, "grid_gate1_confirmation")[0]["blocking"]
    # X/Y blocks once per grid system (grid-system's grid_system_axis_unassigned), not per family here
    family_axes = questions(grid_set, "grid_family_axis_assignment")[0]
    assert family_axes["blocking"] is False and "grid_system_axis_unassigned" in family_axes["message"]
    assert not questions(grid_set, "grid_units_doubt")  # 6000 mm is a plausible spacing


def _plain(tmp_path: Path, fn, insunits: int = 4) -> Path:
    doc = new("R2018", setup=True)
    doc.header["$INSUNITS"] = insunits
    fn(doc.modelspace())
    path = tmp_path / "plain.dxf"
    doc.saveas(path)
    return path


def _bubble(msp, c, label):
    msp.add_circle(c, R)
    msp.add_text(label, height=TH).set_placement(c, align=TextEntityAlignment.MIDDLE_CENTER)


def _simple_grid(msp, xs=(0.0, 6000.0, 12000.0), labels=("1", "2", "3"), both_ends=False):
    for x, label in zip(xs, labels, strict=True):
        msp.add_line((x, 0), (x, 12000))
        _bubble(msp, (x, -R), label)
        if both_ends:
            _bubble(msp, (x, 12000 + R), label)
    for y, label in ((2000.0, "A"), (8000.0, "B")):
        msp.add_line((-2000, y), (xs[-1] + 2000, y))
        _bubble(msp, (-2000 - R, y), label)


def _unicode_grid(msp, dim_text):
    for x, label in ((0.0, "1"), (6000.0, "2"), (12000.0, "3")):
        msp.add_line((x, 0), (x, 12000))
        msp.add_circle((x, -R), R)
        msp.add_text(label, height=TH, dxfattribs={"style": "UNI"}).set_placement(
            (x, -R), align=TextEntityAlignment.MIDDLE_CENTER
        )
    for y, label in ((2000.0, "A"), (8000.0, "B")):
        msp.add_line((-2000, y), (14000, y))
        msp.add_circle((-2000 - R, y), R)
        msp.add_text(label, height=TH, dxfattribs={"style": "UNI"}).set_placement(
            (-2000 - R, y), align=TextEntityAlignment.MIDDLE_CENTER
        )
    msp.add_linear_dim(base=(0, -3000), p1=(0, 0), p2=(6000, 0), text=dim_text, dimstyle="Standard").render()


@pytest.mark.parametrize(
    ("dim_text", "status", "independent"), [("<>", "measured", False), ("6000", "agrees", True)]
)
def test_an_agreeing_dimension_is_evidence_never_high(tmp_path, dim_text, status, independent):
    def fn(msp):
        msp.doc.styles.add("UNI", font="arial.ttf")
        _unicode_grid(msp, dim_text)

    result = run(_plain(tmp_path, fn))
    fam = family(result, "unknown", "1 2 3")
    assert fam["axes"][0]["label"]["confidence"] == "high"  # a Unicode font: the label is not the cap
    assert fam["axes"][0]["confidence"] == "medium"  # pairing is heuristic: an axis is never high
    first = fam["spacings"][0]
    assert [e["status"] for e in first["dimension_evidence"]] == [status]
    assert first["value"]["confidence"] == "medium"  # 'high' is reserved for the engineer at gate 1
    assert [(e["kind"], e["agrees"], e["independent"]) for e in first["evidence"]] == [
        ("dimension_adjacent", True, independent)
    ]


def test_bubbles_at_both_ends_make_one_axis(tmp_path):
    result = run(_plain(tmp_path, lambda m: _simple_grid(m, both_ends=True)))
    fam = family(result, "unknown", "1 2 3")
    assert [len(a["bubbles"]) for a in fam["axes"]] == [2, 2, 2]
    assert fam["proposal"]["coordinates"] == "0 2*6000"


def _arc_grid(msp, start: float, end: float, scale: float = 1.0, mirror: bool = False):
    """The 285/286 bubble (block SADF): an ARC whose sweep is a hair short of 360 degrees, off the block's
    base point, in a block inserted at a uniform scale (mirrored: x scale negative), the label a loose
    TEXT at its centre."""
    blk = msp.doc.blocks.new("SADF")
    off = (187.5, 250.0)  # the arc centre in the block, as in SADF
    blk.add_arc(off, R / scale, start, end)
    blk.add_line((off[0], off[1] + 1.5 * R / scale), (off[0], off[1] + 2 * R / scale))  # cross-hair tick
    sx = -scale if mirror else scale

    def bubble(c: tuple[float, float], label: str) -> None:
        insert = (c[0] - sx * off[0], c[1] - scale * off[1])
        msp.add_blockref("SADF", insert, dxfattribs={"xscale": sx, "yscale": scale})
        msp.add_text(label, height=TH).set_placement(c, align=TextEntityAlignment.MIDDLE_CENTER)

    for x, label in ((0.0, "1"), (6000.0, "2"), (12000.0, "3")):
        msp.add_line((x, 0), (x, 12000))
        bubble((x, -R), label)
    for y, label in ((2000.0, "a"), (8000.0, "b")):
        msp.add_line((-2000, y), (14000, y))
        bubble((-2000 - R, y), label)


@pytest.mark.parametrize(
    ("start", "end", "mirror"),
    [(90.00006, 90.0000031, False), (90.00006, 90.0000031, True), (90.0, 89.2, False), (90.0, 89.0, False)],
)
def test_a_bubble_drawn_as_an_almost_full_arc_is_a_bubble(tmp_path, start, end, mirror):
    """EVAL-3 285 / 286: the grid bubble is block SADF, an ARC from 90.00006 to 90.0000031 degrees (a full
    circle short by 0.00006 degrees), not a CIRCLE; 0 of the plan bubbles were found. A gap up to
    FULL_ARC_GAP_DEG (1 degree) is still a circle; a mirrored insert puts the arc where it is drawn."""
    result = run(_plain(tmp_path, lambda m: _arc_grid(m, start, end, scale=0.5436755, mirror=mirror)))
    numbers = family(result, "unknown", "1 2 3")
    assert numbers["proposal"]["coordinates"] == "0 2*6000"
    assert family(result, "unknown", "a b")["proposal"]["coordinates"] == "0 6000"
    assert numbers["axes"][0]["bubbles"][0]["radius"] == pytest.approx(R)
    assert result["summary"]["bubbles_paired"] == 5


@pytest.mark.parametrize(("start", "end"), [(0.0, 90.0), (90.0, 88.5), (45.0, 45.0)])
def test_an_arc_short_of_a_full_circle_is_not_a_bubble(tmp_path, start, end):
    """A door swing or any arc that is not (almost) a full circle never holds a grid label."""
    result = run(_plain(tmp_path, lambda m: _arc_grid(m, start, end)))
    assert result["summary"]["circles"] == 0 and result["groups"] == []


def test_a_partial_ellipse_of_ratio_one_is_not_a_bubble(tmp_path):
    """An ARC in a block scaled unevenly explodes into an ELLIPSE: only a full one is a circle."""

    def fn(msp):
        for x, label in ((0.0, "1"), (6000.0, "2"), (12000.0, "3")):
            msp.add_line((x, 0), (x, 12000))
            msp.add_ellipse((x, -R), major_axis=(R, 0), ratio=1.0, start_param=0.0, end_param=math.pi / 2)
            msp.add_text(label, height=TH).set_placement((x, -R), align=TextEntityAlignment.MIDDLE_CENTER)
        msp.add_ellipse((30000, 0), major_axis=(R, 0), ratio=1.0)  # a full one still counts
        msp.add_arc((50000, 0), 0.0, 90.00006, 90.0000031)  # a point, not a circle

    result = run(_plain(tmp_path, fn))
    assert result["summary"]["circles"] == 1 and result["groups"] == []


def _through_grid(msp, top: bool = True, gap: float = 15000.0, top_labels: tuple[str, ...] = ("1", "2", "3")):
    """The 286 model#05 plan: every grid line runs from frame edge to frame edge, through the bubbles at both
    of its ends, so no line END lies near a bubble."""
    for x, label, other in zip((0.0, 3400.0, 7380.0), ("1", "2", "3"), top_labels, strict=True):
        msp.add_line((x, -8000), (x, gap + 8000))
        _bubble(msp, (x, 0), label)
        if top:
            _bubble(msp, (x, gap), other)
    for y, label in ((2000.0, "A"), (6840.0, "B"), (11030.0, "C")):
        msp.add_line((-9000, y), (16000, y))
        _bubble(msp, (-3000, y), label)
        if top:
            _bubble(msp, (gap - 5000, y), label)


def test_a_grid_line_through_two_bubbles_of_one_label_is_an_axis(tmp_path):
    """EVAL-3 286 model#05: 1-2-3 = 3400/3980 and A-B-C = 4840/4190 were missed (lines drawn through)."""
    result = run(_plain(tmp_path, _through_grid))
    numbers = family(result, "unknown", "1 2 3")
    assert numbers["proposal"]["coordinates"] == "0 3400 3980"
    assert family(result, "unknown", "A B C")["proposal"]["coordinates"] == "0 4840 4190"
    assert [len(a["bubbles"]) for a in numbers["axes"]] == [2, 2, 2]
    assert {a["pairing"] for a in numbers["axes"]} == {"line"}
    assert result["unpaired_bubbles"]["count"] == 0


def test_the_longest_line_through_both_bubbles_is_the_axis(tmp_path):
    def fn(msp):
        _through_grid(msp)
        msp.add_line((0, -5000), (0, 20000))  # a shorter line through the same two bubbles

    result = run(_plain(tmp_path, fn))
    axis = family(result, "unknown", "1 2 3")["axes"][0]
    assert (axis["line"]["start"], axis["line"]["end"]) == ([0.0, -8000.0], [0.0, 23000.0])


def test_one_bubble_on_a_line_that_runs_through_it_is_not_an_axis(tmp_path):
    """A long line through a single bubble (a wall through a mark) proves nothing: both ends are needed. A
    bubble of the same label beside the line (parallel offset), or past the line's end, is not its other
    end."""

    def fn(msp):
        _through_grid(msp, top=False)
        _bubble(msp, (1500, 15000), "1")  # beside line 1, within its length
        _bubble(msp, (3400, 30000), "2")  # on line 2's extension, 7000 past its end (17.5 radii)

    result = run(_plain(tmp_path, fn))
    assert result["groups"] == [] and result["unpaired_bubbles"]["count"] == 8


def test_bubbles_of_two_labels_on_one_line_are_not_an_axis(tmp_path):
    result = run(_plain(tmp_path, lambda m: _through_grid(m, top_labels=("7", "8", "9"))))
    assert not [f for f in families(result, "unknown") if f["proposal"] and "1" in f["proposal"]["labels"]]
    assert family(result, "unknown", "A B C")["proposal"]["coordinates"] == "0 4840 4190"


def test_a_bubble_ends_one_axis_only(tmp_path):
    """The top bubble of axis 1 also sits on a long horizontal line through another '1' bubble: that line
    does not take it again."""

    def fn(msp):
        _through_grid(msp)
        msp.add_line((-9000, 15000), (40000, 15000))
        _bubble(msp, (30000, 15000), "1")

    result = run(_plain(tmp_path, fn))
    assert [len(a["bubbles"]) for a in family(result, "unknown", "1 2 3")["axes"]] == [2, 2, 2]
    assert [b["center"] for b in result["unpaired_bubbles"]["listed"]] == [[30000.0, 15000.0]]


def test_two_bubbles_of_one_label_too_close_on_a_line_are_not_an_axis(tmp_path):
    """Two same-label bubbles closer than MIN_AXIS_LENGTH radii on one long line are not an axis's ends."""
    result = run(_plain(tmp_path, lambda m: _through_grid(m, gap=8 * R)))
    assert result["groups"] == [] and result["unpaired_bubbles"]["count"] == 12


def test_numbered_circle_on_a_short_leader_is_not_an_axis(tmp_path):
    def fn(msp):
        _simple_grid(msp)
        msp.add_line((3000, 5000), (3000 + 5 * R, 5000))  # leader of a bar mark: 5 radii long
        _bubble(msp, (3000 + 6 * R, 5000), "7")

    result = run(_plain(tmp_path, fn))
    assert result["unpaired_bubbles"]["count"] == 1
    assert result["unpaired_bubbles"]["listed"][0]["label"] == "7"
    assert family(result, "unknown", "1 2 3")["proposal"]["coordinates"] == "0 2*6000"


def test_duplicate_label_in_one_view(tmp_path):
    result = run(_plain(tmp_path, lambda m: _simple_grid(m, labels=("1", "2", "2"))))
    assert questions(result, "grid_label_duplicate")
    assert family(result, "unknown", "1 2 2")["proposal"]["complete"] is False


def test_implausible_spacing_for_declared_unit(tmp_path):
    result = run(_plain(tmp_path, _simple_grid, insunits=6))  # metres declared, 6000 drawn
    q = questions(result, "grid_units_doubt")
    # evidence for intake's units_confirm_all, the file's one blocking units question
    assert len(q) == 1 and not q[0]["blocking"] and "= 6000.0 m" in q[0]["found"]
    assert "units_confirm_all" in q[0]["message"]
    assert family(result, "unknown", "1 2 3")["proposal"]["unit_confidence"] == "low"


def test_no_grid_found(tmp_path):
    result = run(_plain(tmp_path, lambda m: m.add_line((0, 0), (100, 0))))
    assert [q["code"] for q in result["questions"]] == ["grid_none_found"]
    assert result["groups"] == []


def test_output_is_deterministic(tmp_path):
    path = build_set(tmp_path)
    index = extract_text(path)
    sheets = extract_sheets(path, index)
    assert json.dumps(extract_grids(path, index, sheets)) == json.dumps(extract_grids(path, index, sheets))


# --- review regressions (each case is a reviewer reproduction) --------------------------------------


def _grid_at(msp, ox=0.0, xs=(0.0, 6000.0, 12000.0), ys=(2000.0, 8000.0), labels=("1", "2", "3"), layer="0"):
    for x, label in zip(xs, labels, strict=True):
        msp.add_line((ox + x, 0), (ox + x, 12000), dxfattribs={"layer": layer})
        _bubble(msp, (ox + x, -R), label)
    for y, label in zip(ys, ("A", "B"), strict=True):
        msp.add_line((ox - 2000, y), (ox + xs[-1] + 2000, y), dxfattribs={"layer": layer})
        _bubble(msp, (ox - 2000 - R, y), label)


def _all_families(result):
    return [f for g in result["groups"] for f in g["families"]]


def test_axes_spacings_and_cross_checks_are_never_high(grid_set):
    for fam in _all_families(grid_set):
        assert all(a["confidence"] != "high" for a in fam["axes"])
        assert all(s["value"]["confidence"] != "high" for s in fam["spacings"])


@pytest.mark.parametrize(
    ("text", "confidence", "asked"), [("12000", "medium", False), ("12500", "low", True)]
)
def test_an_overall_dimension_is_span_evidence_only(tmp_path, text, confidence, asked):
    def fn(msp):
        _grid_at(msp, xs=(0.0, 6500.0, 12000.0))
        msp.add_linear_dim(base=(0, -3000), p1=(0, 0), p2=(12000, 0), text=text, dimstyle="Standard").render()

    result = run(_plain(tmp_path, fn))
    fam = family(result, "unknown", "1 2 3")
    for sp in fam["spacings"]:  # 6500 and 5500: the 12000 span checks their sum, not each one
        assert [e["kind"] for e in sp["evidence"]] == ["dimension_span"]
        assert sp["value"]["confidence"] == confidence
    assert bool(questions(result, "grid_dimension_override_mismatch")) is asked


def test_a_grid_block_inserted_twice_is_not_an_independent_check(tmp_path):
    def fn(msp):
        blk = msp.doc.blocks.new("GRID")
        _grid_at(blk)
        msp.add_blockref("GRID", (0, 0))
        msp.add_blockref("GRID", (100000, 0))

    result = run(_plain(tmp_path, fn))
    assert {c["status"] for c in result["cross_checks"]} == {"consistent"}
    ev = [e for f in _all_families(result) for s in f["spacings"] for e in s["evidence"]]
    assert ev and all(e["kind"] == "other_view" and e["agrees"] and not e["independent"] for e in ev)
    assert all(s["value"]["confidence"] == "medium" for f in _all_families(result) for s in f["spacings"])


def test_an_agreeing_copy_does_not_outweigh_a_disagreeing_view(tmp_path):
    def fn(msp):
        blk = msp.doc.blocks.new("GRID")
        _grid_at(blk)
        msp.add_blockref("GRID", (0, 0))
        msp.add_blockref("GRID", (100000, 0))  # a copy: agrees, but is not independent
        _grid_at(msp, ox=200000, xs=(0.0, 6500.0, 12500.0))  # another grid with the same labels: 1-2 differs

    result = run(_plain(tmp_path, fn))
    copies = [g for g in result["groups"] if g["bbox"][0] < 150000]
    for g in copies:
        fam = next(f for f in g["families"] if f["proposal"]["labels"] == "1 2 3")
        assert (
            fam["spacings"][0]["value"]["confidence"] == "low"
        )  # 1-2: contradicted, the copy proves nothing
        assert fam["spacings"][1]["value"]["confidence"] == "medium"  # 2-3: 6000 everywhere
    assert questions(result, "grid_spacing_cross_sheet_mismatch")


def test_two_plans_on_one_sheet_do_not_confirm_each_other(tmp_path):
    result = run(_plain(tmp_path, lambda m: (_grid_at(m), _grid_at(m, ox=50000))))
    ev = [e for f in _all_families(result) for s in f["spacings"] for e in s["evidence"]]
    assert ev and not any(e["independent"] for e in ev) and all("same sheet" in e["ref"] for e in ev)


def test_two_sheets_are_independent_views(grid_set):
    fam = family(grid_set, "model#01", "1 2 3 4")
    other = [e for e in fam["spacings"][1]["evidence"] if e["kind"] == "other_view"]
    assert other and all(e["independent"] and e["agrees"] for e in other)  # 2-3 is 6000 on both sheets


def test_an_axis_on_another_layer_is_a_blocking_question(tmp_path):
    def fn(msp):
        _grid_at(msp)
        msp.doc.layers.add("SECTION")
        msp.add_line((13500, 0), (13500, 12000), dxfattribs={"layer": "SECTION"})
        msp.add_circle((13500, -R), R, dxfattribs={"layer": "SECTION"})
        msp.add_text("4", height=TH, dxfattribs={"layer": "SECTION"}).set_placement(
            (13500, -R), align=TextEntityAlignment.MIDDLE_CENTER
        )

    result = run(_plain(tmp_path, fn))
    q = questions(result, "grid_axis_layer_mismatch")
    assert len(q) == 1 and q[0]["blocking"] and "axis 4: SECTION" in q[0]["found"]
    assert family(result, "unknown", "1 2 3 4")["proposal"]["complete"] is False


def test_a_circle_with_other_text_is_not_a_bubble(tmp_path):
    def fn(msp):
        _grid_at(msp)
        # a section callout at the end of a long line: section number and sheet number in one circle
        msp.add_line((18000 + 800, 5000), (40000, 5000))
        msp.add_circle((18000, 5000), 800)
        msp.add_text("1", height=350).set_placement((18000, 5200), align=TextEntityAlignment.MIDDLE_CENTER)
        msp.add_text("S-301", height=200).set_placement(
            (18000, 4600), align=TextEntityAlignment.MIDDLE_CENTER
        )

    result = run(_plain(tmp_path, fn))
    assert result["summary"]["bubbles_other_text"] == 1
    assert [f["proposal"]["labels"] for f in _all_families(result)] == ["A B", "1 2 3"]


@pytest.mark.parametrize("reverse", [False, True])
def test_a_tilted_axis_gives_the_same_offset_from_either_end_and_is_asked(tmp_path, reverse):
    dx = 15500 * math.tan(math.radians(0.04))  # below the old 0.05 degree tolerance, 10.8 mm drift

    def fn(msp):
        for x, label in ((0.0, "1"), (12000.0, "3")):
            msp.add_line((x, 0), (x, 15500))
            _bubble(msp, (x, -R), label)
        a, b = (6000, 0), (6000 + dx, 15500)
        msp.add_line(*((b, a) if reverse else (a, b)))
        _bubble(msp, (6000, -R), "2")
        for y, label in ((2000.0, "A"), (8000.0, "B")):
            msp.add_line((-2000, y), (14000, y))
            _bubble(msp, (-2000 - R, y), label)

    result = run(_plain(tmp_path, fn))
    fam = family(result, "unknown", "1 2 3")
    assert [s["measured"] for s in fam["spacings"]] == pytest.approx([6000 + dx / 2, 6000 - dx / 2])
    assert len(questions(result, "grid_axis_not_parallel")) == 1
    assert fam["proposal"]["complete"] is False
    assert all(s["value"]["confidence"] == "low" for s in fam["spacings"])


def _rotated(msp, deg_a, deg_b, vertical=89.5):
    for x, label in ((0.0, "1"), (6000.0, "2"), (12000.0, "3")):
        t = math.radians(vertical)
        msp.add_line((x, 0.0), (x + 12000 * math.cos(t), 12000 * math.sin(t)))
        _bubble(msp, (x - R * math.cos(t), -R * math.sin(t)), label)
    for y, label, deg in ((2000.0, "A", deg_a), (8000.0, "B", deg_b)):
        t = math.radians(deg)
        msp.add_line((-2000.0, y), (-2000 + 16000 * math.cos(t), y + 16000 * math.sin(t)))
        _bubble(msp, (-2000 - R * math.cos(t), y - R * math.sin(t)), label)


def test_directions_are_circular_one_family_across_the_wrap(tmp_path):
    result = run(_plain(tmp_path, lambda m: _rotated(m, -0.49, -0.51)))  # -0.51 is stored as 179.49
    labels = sorted(f["proposal"]["labels"] for f in _all_families(result) if f["proposal"])
    assert labels == ["1 2 3", "A B"]
    assert len(questions(result, "grid_axis_not_parallel")) == 1  # 0.02 degrees over 16 m: 5.6 drift


def test_rotation_at_the_canonical_boundary(tmp_path):
    result = run(_plain(tmp_path, lambda m: _rotated(m, -0.5, -0.5)))
    fam = family(result, "unknown", "A B")
    assert fam["proposal"]["coordinates"] == "0 6000" and fam["proposal"]["complete"] is True


def test_collinear_axes_of_two_plans_on_one_sheet_stay_apart(tmp_path):
    result = run(_plain(tmp_path, lambda m: (_grid_at(m), _grid_at(m, ox=50000, ys=(2000.0, 9000.0)))))
    ab = [f for f in _all_families(result) if f["proposal"] and f["proposal"]["labels"] == "A B"]
    assert len(ab) == 2 and all(len(a["bubbles"]) == 1 for f in ab for a in f["axes"])
    assert sorted(f["proposal"]["coordinates"] for f in ab) == ["0 6000", "0 7000"]
    q = questions(result, "grid_spacing_cross_sheet_mismatch")  # one compared spacing is never 'scaled'
    assert len(q) == 1 and q[0]["blocking"] and not questions(result, "grid_scale_differs")


def test_labels_out_of_order_are_blocking_and_a_gap_is_not(tmp_path):
    result = run(
        _plain(
            tmp_path, lambda m: _grid_at(m, xs=(0.0, 6000.0, 12000.0, 18000.0), labels=("1", "3", "2", "4"))
        )
    )
    q = questions(result, "grid_label_order_nonmonotonic")
    assert len(q) == 1 and q[0]["blocking"] and q[0]["found"] == "1 3 2 4"
    assert family(result, "unknown", "1 3 2 4")["proposal"]["complete"] is False
    gap = run(_plain(tmp_path, lambda m: _grid_at(m, labels=("1", "2", "4"))))
    assert [q["blocking"] for q in questions(gap, "grid_label_sequence_gap")] == [False]
    assert family(gap, "unknown", "1 2 4")["proposal"]["complete"] is True


@pytest.mark.parametrize(
    ("label", "ok"),
    [
        ("1A", True),
        ("2B", True),
        ("A1", True),
        ("B12", True),
        ("1a", True),
        ("C'", True),
        ("ABC", False),
        ("1234", False),
        ("S-301", False),
    ],
)
def test_label_pattern(label, ok):
    assert bool(_LABEL_RE.match(label)) is ok


def test_a_label_the_legacy_font_gate_blocks_makes_no_axis_and_is_listed(tmp_path):
    # review of tool wave 2 (F1 item 3): grids took labels from blocked text. In a TCVN3 style '4/g14' and
    # '2/G20' are rebar callouts written in ASCII ('legacy_ascii_suspect'), not sub-axes; '1/A' stays one.
    def fn(msp):
        msp.doc.styles.add(".VnTime", font="vntime.ttf")
        for x, label in ((0.0, "1"), (6000.0, "1/A"), (12000.0, "4/g14"), (18000.0, "2/G20")):
            msp.add_line((x, 0), (x, 12000))
            msp.add_circle((x, -R), R)
            msp.add_text(label, height=TH, dxfattribs={"style": ".VnTime"}).set_placement(
                (x, -R), align=TextEntityAlignment.MIDDLE_CENTER
            )
        for y, label in ((2000.0, "A"), (8000.0, "B")):
            msp.add_line((-2000, y), (20000, y))
            _bubble(msp, (-2000 - R, y), label)

    result = run(_plain(tmp_path, fn))
    labels = [a["label"]["value"] for f in _all_families(result) for a in f["axes"] if a["label"]]
    assert "1/A" in labels and "4/g14" not in labels and "2/G20" not in labels
    blocked = result["blocked_candidates"]
    assert [(b["value_text"], b["reason"]) for b in blocked] == [
        ("4/g14", "legacy_ascii_suspect"),
        ("2/G20", "legacy_ascii_suspect"),
    ]
    assert all(b["entry_id"].startswith("T") and b["sheet"] == "unknown" for b in blocked)
    assert result["summary"]["blocked_candidates"] == 2
    # a circle holding only a blocked label is neither a bubble, nor 'other text', nor unpaired
    assert result["summary"]["bubbles_labelled"] == 4 and result["summary"]["bubbles_other_text"] == 0
    assert result["unpaired_bubbles"]["count"] == 0
    # its line ends in a bubble whose label cannot be read: asked as a missing label, never used (the line
    # at 18000 is beyond the 1.5-spacing reach of the unlabelled-line check)
    fam = family(result, "unknown", "1 1/A")
    assert [(u["offset"], u["empty_bubble"]) for u in fam["unlabelled_lines"]] == [(12000.0, True)]
    assert len(questions(result, "grid_label_missing")) == 1 and not questions(result, "grid_axis_unlabelled")
    assert all("4/g14" not in q["found"] and "2/G20" not in q["found"] for q in result["questions"])


def test_suffix_labels_are_axes_in_order(tmp_path):
    result = run(
        _plain(
            tmp_path, lambda m: _grid_at(m, xs=(0.0, 2000.0, 6000.0, 12000.0), labels=("1", "1A", "2", "3"))
        )
    )
    fam = family(result, "unknown", "1 1A 2 3")
    assert fam["proposal"]["coordinates"] == "0 2000 4000 6000" and fam["proposal"]["complete"] is True
    assert not questions(result, "grid_label_missing") and not questions(
        result, "grid_label_order_nonmonotonic"
    )


def test_a_huge_circle_does_not_blow_up_the_bucket_search(tmp_path):
    def fn(msp):
        for i in range(2000):
            msp.add_circle((i * 50.0, -5000), 5)
        _grid_at(msp)
        msp.add_circle((0, 0), 200000.0)  # a site boundary drawn as a circle

    path = _plain(tmp_path, fn)
    index = extract_text(path)
    sheets = extract_sheets(path, index)
    start = time.perf_counter()
    result = extract_grids(path, index, sheets)
    assert time.perf_counter() - start < 2.0
    assert family(result, "unknown", "1 2 3")["proposal"]["coordinates"] == "0 2*6000"


def test_mirrored_and_rotated_bubble_blocks_pair_by_circle_centre(tmp_path):
    def fn(msp):
        blk = msp.doc.blocks.new("BUBL")
        blk.add_circle((0, 0), R)
        blk.add_attdef("AXIS", (-120, -175), dxfattribs={"height": TH})
        kws = ({"xscale": -1}, {"rotation": 90}, {"xscale": -1, "rotation": 180})
        for x, label, kw in zip((0.0, 6000.0, 12000.0), ("1", "2", "3"), kws, strict=True):
            msp.add_line((x, 0), (x, 12000))
            msp.add_blockref("BUBL", (x, -R), dxfattribs=kw).add_auto_attribs({"AXIS": label})
        for y, label in ((2000.0, "A"), (8000.0, "B")):
            msp.add_line((-2000, y), (14000, y))
            msp.add_blockref("BUBL", (-2000 - R, y), dxfattribs={"yscale": -1}).add_auto_attribs(
                {"AXIS": label}
            )

    result = run(_plain(tmp_path, fn))
    assert family(result, "unknown", "1 2 3")["proposal"]["coordinates"] == "0 2*6000"
    assert family(result, "unknown", "A B")["proposal"]["coordinates"] == "0 6000"


@pytest.mark.parametrize(
    ("second", "status", "code", "blocking"),
    [
        (5770.83, "drafting_tolerance", "grid_spacing_drafting_tolerance", False),  # 1.4e-4 of the spacing
        (5772.5, "mismatch", "grid_spacing_cross_sheet_mismatch", True),  # 4.3e-4
    ],
)
def test_drafting_tolerance_between_views(tmp_path, second, status, code, blocking):
    def fn(msp):
        _grid_at(msp, xs=(0.0, 5770.0, 11540.0))
        _grid_at(msp, ox=50000, xs=(0.0, second, second + 5770.0))

    result = run(_plain(tmp_path, fn))
    row = next(c for c in result["cross_checks"] if "1" in c["common_labels"])
    assert row["status"] == status
    q = questions(result, code)
    assert len(q) == 1 and q[0]["blocking"] is blocking and "1-2" in q[0]["found"]
    other = "grid_spacing_cross_sheet_mismatch" if not blocking else "grid_spacing_drafting_tolerance"
    assert not questions(result, other)


def test_question_counts_are_true_counts_when_the_list_is_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(grids_mod, "MAX_QUESTIONS_PER_CODE", 1)
    result = run(_plain(tmp_path, lambda m: _rotated(m, -0.5, -0.5)))  # both families rotated
    assert len(questions(result, "grid_rotated")) == 1
    assert result["question_counts"]["grid_rotated"] == 2
    assert any("2 non-blocking 'grid_rotated' questions" in w for w in result["warnings"])


def test_example_is_valid(example):
    assert validate("grids", example("grids")) == []


# --- families a question cites (tool wave 2, fix 5b) ------------------------------------------------


def _doc(*axes_per_family: int) -> dict[str, Any]:
    """A grids document reduced to what question_families reads: families F001.. with n axes each."""
    fams = [{"family_id": f"F{k:03d}", "axes": [{}] * n} for k, n in enumerate(axes_per_family, start=1)]
    return {
        "groups": [{"group_id": "V001", "families": fams[:2]}, {"group_id": "V002", "families": fams[2:]}]
    }


def _q(code: str, where: str) -> dict[str, Any]:
    return {"code": code, "blocking": True, "message": "m", "where": where, "found": "f"}


@pytest.mark.parametrize(
    ("code", "where", "families"),
    [
        ("grid_label_duplicate", "V001/F001", ["F001"]),
        ("grid_axis_not_parallel", "V001/F002 axis 3", ["F002"]),
        ("grid_label_missing", "V002/F003 line 1A2", ["F003"]),
        ("grid_dimension_override_mismatch", "V002/F003 dimension 2F", ["F003"]),
        ("grid_non_orthogonal", "V001/F001,F002", ["F001", "F002"]),
        (
            "grid_spacing_cross_sheet_mismatch",
            "V002/F003 (model#02) vs V001/F001 (model#01)",
            ["F001", "F003"],
        ),
        ("grid_scale_differs", "V001/F002 vs V002/F003", ["F002", "F003"]),
        # every family of two or more axes (the where lists them with listed(), which truncates)
        ("grid_family_axis_assignment", "F001, F002 (+1 more)", ["F001", "F002", "F003"]),
        ("grid_gate1_confirmation", "F001, F002 (+1 more)", ["F001", "F002", "F003"]),
        # no family: before families exist, or about the whole file
        ("grid_axis_label_conflict", "line 1A2 on layer 'S-GRID'", None),
        ("grid_none_found", "plans/F001.dxf", None),
        ("grid_units_doubt", "header $INSUNITS", None),
        ("level_single_occurrence", "V001/F001", None),  # not a grids code
        ("grid_label_duplicate", "V001/F009", None),  # a family the document does not have
    ],
)
def test_question_families_reads_its_own_where_formats(code, where, families):
    assert grids_mod.question_families(_q(code, where), _doc(3, 4, 2, 1)) == families


def test_every_grids_question_code_is_classified_for_its_families():
    """A new grids question code must say whether its where cites families (else lifecycle never closes it,
    silently)."""
    import re

    source = Path(grids_mod.__file__).read_text(encoding="utf-8")
    raised = set(re.findall(r'ctx\.ask\(\s*"(grid_[a-z0-9_]+)"', source))
    without = {"grid_none_found", "grid_units_doubt"}  # about the whole file
    assert raised == grids_mod.FAMILY_WHERE_CODES | grids_mod.ALL_FAMILIES_CODES | without


def test_every_grids_question_cites_only_families_of_its_document(tmp_path):
    result = run(_plain(tmp_path, lambda m: _rotated(m, -0.5, -0.5)))
    ids = {f["family_id"] for g in result["groups"] for f in g["families"]}
    cited = [grids_mod.question_families(q, result) for q in result["questions"]]
    assert any(cited) and all(c is None or set(c) <= ids for c in cited)


def _bubble_lattice(
    msp,
    xs=(0.0, 6000.0, 12000.0),
    ys=(2000.0, 8000.0),
    x_labels=("1", "2", "3"),
    y_labels=("A", "B"),
    stubs=False,
    y_shift=0.0,
    x_shift=0.0,
    angle=0.0,
):
    """A grid drawn as bubble pairs only: `x_labels` at both ends of vertical axes, `y_labels` at both ends of
    horizontal ones, no axis line (or, with `stubs`, a 600-long stub next to each bubble). The lattice is
    turned by `angle` degrees about (0, 0) and then moved by (`x_shift`, `y_shift`)."""
    cos, sin = math.cos(math.radians(angle)), math.sin(math.radians(angle))

    def at(x, y):
        return (x * cos - y * sin + x_shift, x * sin + y * cos + y_shift)

    lo, hi = -R, 12000 + R
    for x, label in zip(xs, x_labels, strict=True):
        _bubble(msp, at(x, lo), label)
        _bubble(msp, at(x, hi), label)
        if stubs:
            msp.add_line(at(x, lo + R), at(x, lo + R + 600))
            msp.add_line(at(x, hi - R), at(x, hi - R - 600))
    for y, label in zip(ys, y_labels, strict=True):
        _bubble(msp, at(-2000 - R, y), label)
        _bubble(msp, at(14000 + R, y), label)
        if stubs:
            msp.add_line(at(-2000, y), at(-2000 + 600, y))
            msp.add_line(at(14000, y), at(14000 - 600, y))


@pytest.mark.parametrize("stubs", [False, True])
def test_two_bubble_lattice_seeds_a_view_on_a_sheet_with_no_line_view(tmp_path, stubs):
    """Dev corpus s774: labels `1 2 3 4` and `a b c` sit at both ends of their axes, the lines are drawn in
    pieces shorter than MIN_AXIS_LENGTH, so no axis line pairs and the sheet had 0 views."""
    result = run(_plain(tmp_path, lambda m: _bubble_lattice(m, stubs=stubs)))
    numbers = family(result, "unknown", "1 2 3")
    assert numbers["proposal"]["coordinates"] == "0 2*6000"
    assert family(result, "unknown", "A B")["proposal"]["coordinates"] == "0 6000"
    assert len([g for g in result["groups"] if g["sheet"] == "unknown"]) == 1
    axes = numbers["axes"] + family(result, "unknown", "A B")["axes"]
    assert {a["pairing"] for a in axes} == {"two_bubbles"}
    assert {a["confidence"] for a in axes} == {"low"}
    assert len(questions(result, "grid_two_bubble_axis")) == 5
    assert all(q["blocking"] for q in questions(result, "grid_two_bubble_axis"))
    assert result["unpaired_bubbles"]["count"] == 0


@pytest.mark.parametrize(("n_vertical", "n_horizontal"), [(3, 0), (0, 2), (3, 1), (1, 2)])
def test_two_bubble_pairs_of_one_direction_seed_no_view(tmp_path, n_vertical, n_horizontal):
    """A single row of pairs (bar numbers, details), or fewer than two pairs in either direction, seeds
    nothing."""

    def fn(msp):
        _bubble_lattice(
            msp,
            xs=(0.0, 6000.0, 12000.0)[:n_vertical],
            x_labels=("1", "2", "3")[:n_vertical],
            ys=(2000.0, 8000.0)[:n_horizontal],
            y_labels=("A", "B")[:n_horizontal],
        )

    result = run(_plain(tmp_path, fn))
    assert result["groups"] == []
    assert not questions(result, "grid_two_bubble_axis")
    assert result["unpaired_bubbles"]["count"] == 2 * (n_vertical + n_horizontal)


def test_two_bubble_pairs_that_do_not_cross_seed_no_view(tmp_path):
    """Two rows of pairs side by side whose extents never meet are not one grid."""

    def fn(msp):
        _bubble_lattice(msp, ys=(), y_labels=())
        for y, label in ((30000.0, "A"), (36000.0, "B")):
            _bubble(msp, (-2000 - R, y), label)
            _bubble(msp, (14000 + R, y), label)

    result = run(_plain(tmp_path, fn))
    assert result["groups"] == []
    assert result["unpaired_bubbles"]["count"] == 10


def test_two_bubble_pairs_not_perpendicular_seed_no_view(tmp_path):
    """Pairs in two directions that are not perpendicular (here 60 degrees apart from vertical) are no
    rectangular grid."""

    def fn(msp):
        _bubble_lattice(msp, ys=(), y_labels=())
        for y, label in ((2000.0, "A"), (8000.0, "B")):
            a = (-2000.0, y)
            b = (a[0] + 16000 * math.cos(math.radians(30)), a[1] + 16000 * math.sin(math.radians(30)))
            _bubble(msp, a, label)
            _bubble(msp, b, label)

    result = run(_plain(tmp_path, fn))
    assert result["groups"] == []
    assert not questions(result, "grid_two_bubble_axis")


def test_two_bubble_pair_crossing_nothing_stays_unpaired_beside_a_lattice(tmp_path):
    def fn(msp):
        _bubble_lattice(msp)
        _bubble(msp, (50000, -R), "9")
        _bubble(msp, (50000, 12000 + R), "9")

    result = run(_plain(tmp_path, fn))
    assert family(result, "unknown", "1 2 3")["proposal"]["coordinates"] == "0 2*6000"
    assert [b["label"] for b in result["unpaired_bubbles"]["listed"]] == ["9", "9"]


def test_two_bubble_lattice_does_not_seed_a_second_view_on_a_sheet_with_a_line_view(tmp_path):
    def fn(msp):
        _simple_grid(msp)
        _bubble_lattice(msp, xs=(0.0, 6000.0), x_labels=("7", "8"), y_labels=("C", "D"), y_shift=50000.0)

    result = run(_plain(tmp_path, fn))
    assert len(result["groups"]) == 1
    assert result["unpaired_bubbles"]["count"] == 8


def _vdim(msp, x, y1, y2):
    """A vertical linear dimension from (x, y1) to (x, y2), no text override."""
    msp.add_linear_dim(
        base=(x - 1500, (y1 + y2) / 2), p1=(x, y1), p2=(x, y2), angle=90, dimstyle="Standard"
    ).render()


def _lattice_next_to_line_grid(tmp_path, *, dimension, noise=1.5):
    """S-101 has the grid `1 2 3` x `A B` drawn with lines (A-B 6000). S-102 draws it as a bubble lattice
    whose B bubbles sit `noise` off; with `dimension`, a dimension between the true axes A and B (6000) is
    drawn."""
    doc = new("R2018", setup=True)
    doc.header["$INSUNITS"] = 4
    _frame_block(doc)
    msp = doc.modelspace()
    _frame(msp, 0.0, "S-101", "A")
    _frame(msp, SHEET2_X, "S-102", "A")
    _grid_at(msp, ox=20000.0)
    _bubble_lattice(msp, ys=(2000.0, 8000.0 + noise), x_shift=SHEET2_X + 20000.0, y_shift=10000.0)
    if dimension:
        _vdim(msp, SHEET2_X + 20000.0 - 2000.0, 12000.0, 18000.0)
    path = tmp_path / "next.dxf"
    doc.saveas(path)
    return run(path)


def test_a_dimension_between_two_undrawn_axes_sets_the_position_over_the_bubble_centres(tmp_path):
    """EVAL-3 285: the bubble centres of a lattice sheet are placed 1 mm off the grid the dimensions
    measure; a dimension whose extension points lie on both axes (within DIM_POINT_TOL) places the axis."""
    result = _lattice_next_to_line_grid(tmp_path, dimension=True)
    fam = family(result, "model#02", "A B")
    assert fam["proposal"]["coordinates"] == "0 6000"
    assert [a["offset"] for a in fam["axes"]] == [0.0, 6000.0]
    assert fam["spacings"][0]["measured"] == 6001.5  # the bubble-centre value stays visible
    assert [e["status"] for e in fam["spacings"][0]["dimension_evidence"]] == ["measured"]
    assert [r["status"] for r in result["cross_checks"] if "model#02" in r["sheets"]] == ["consistent"] * 2
    assert not questions(result, "grid_spacing_cross_sheet_mismatch")


def test_without_a_dimension_the_bubble_centres_keep_a_blocking_mismatch(tmp_path):
    """Control: the rule never hides a difference that has no dimension evidence."""
    result = _lattice_next_to_line_grid(tmp_path, dimension=False)
    fam = family(result, "model#02", "A B")
    assert fam["proposal"]["coordinates"] == "0 6002"  # 6001.5 rounded to the 1-unit step
    assert fam["spacings"][0]["measured"] == 6001.5
    q = questions(result, "grid_spacing_cross_sheet_mismatch")
    assert len(q) == 1 and q[0]["blocking"]


def _line_grid_with_undrawn_axis(msp, *, dim_ab, dim_bc):
    """Vertical lines 1 2 3 and horizontal lines A (y 2000) and C (y 14000); B (y 8000, bubbles 1.5 off) is
    drawn as a bubble pair only and joins the family. `dim_ab` / `dim_bc` are the (y1, y2) extension
    points."""
    for x, label in ((0.0, "1"), (6000.0, "2"), (12000.0, "3")):
        msp.add_line((x, 0), (x, 16000))
        _bubble(msp, (x, -R), label)
    for y, label in ((2000.0, "A"), (14000.0, "C")):
        msp.add_line((-2000, y), (14000, y))
        _bubble(msp, (-2000 - R, y), label)
    _bubble(msp, (-2000 - R, 8001.5), "B")
    _bubble(msp, (14000 + R, 8001.5), "B")
    for pair in (dim_ab, dim_bc):
        if pair:
            _vdim(msp, 20000.0 if pair is dim_ab else 22000.0, *pair)


def test_an_undrawn_axis_in_a_line_family_moves_onto_its_dimensions_and_the_lines_stay(tmp_path):
    result = run(
        _plain(tmp_path, lambda m: _line_grid_with_undrawn_axis(m, dim_ab=(2000, 8000), dim_bc=(8000, 14000)))
    )
    fam = family(result, "unknown", "A B C")
    assert [a["pairing"] for a in fam["axes"]] == ["line", "two_bubbles", "line"]
    assert [a["offset"] for a in fam["axes"]] == [0.0, 6000.0, 12000.0]
    assert [s["measured"] for s in fam["spacings"]] == [6001.5, 5998.5]
    for spacing in fam["spacings"]:
        cited = [
            d
            for d in spacing["value"]["provenance"]["derived_from"]
            if d["method"] == "dxf_dimension_measured"
        ]
        # each spacing cites the one dimension drawn between its two axes, at the DIMENSION's own extents
        # (the extension points are at x 20000 / 22000, the axes' bubbles at x -2400 / 14400)
        assert len(cited) == 1
        assert cited[0]["region"]["detail"].startswith("dimension ")
        assert "?" not in cited[0]["region"]["detail"]
        assert cited[0]["region"]["bbox"][0] >= 18000
    details = [
        d["region"]["detail"]
        for spacing in fam["spacings"]
        for d in spacing["value"]["provenance"]["derived_from"]
        if d["method"] == "dxf_dimension_measured"
    ]
    assert len(set(details)) == 2


def test_two_undrawn_axes_between_line_axes_are_each_placed_from_their_drawn_neighbour(tmp_path):
    """A and D are lines (y 2000, 20000), B and C are bubble pairs 1.5 off (8001.5, 14001.5). The dimension
    between B and C does not move either one: each is placed from the drawn axis next to it, and the lines
    never move."""

    def fn(msp):
        for x, label in ((0.0, "1"), (6000.0, "2"), (12000.0, "3")):
            msp.add_line((x, 0), (x, 22000))
            _bubble(msp, (x, -R), label)
        for y, label in ((2000.0, "A"), (20000.0, "D")):
            msp.add_line((-2000, y), (14000, y))
            _bubble(msp, (-2000 - R, y), label)
        for y, label in ((8001.5, "B"), (14001.5, "C")):
            _bubble(msp, (-2000 - R, y), label)
            _bubble(msp, (14000 + R, y), label)
        for i, (y1, y2) in enumerate(((2000, 8000), (8000, 14000), (14000, 20000))):
            _vdim(msp, 20000.0 + 2000.0 * i, y1, y2)

    fam = family(run(_plain(tmp_path, fn)), "unknown", "A B C D")
    assert [a["pairing"] for a in fam["axes"]] == ["line", "two_bubbles", "two_bubbles", "line"]
    assert [a["offset"] for a in fam["axes"]] == [0.0, 6000.0, 12000.0, 18000.0]


def test_an_undrawn_axis_whose_two_dimensions_disagree_stays_at_its_bubbles(tmp_path):
    """Its neighbours imply positions 4 apart (more than half the 1-unit rounding step): no guess."""
    result = run(
        _plain(tmp_path, lambda m: _line_grid_with_undrawn_axis(m, dim_ab=(2000, 8000), dim_bc=(8004, 14000)))
    )
    fam = family(result, "unknown", "A B C")
    assert [a["offset"] for a in fam["axes"]] == [0.0, 6001.5, 12000.0]


def test_an_undrawn_axis_with_one_dimension_is_anchored_on_that_side(tmp_path):
    result = run(
        _plain(tmp_path, lambda m: _line_grid_with_undrawn_axis(m, dim_ab=None, dim_bc=(8000, 14000)))
    )
    fam = family(result, "unknown", "A B C")
    assert [a["offset"] for a in fam["axes"]] == [0.0, 6000.0, 12000.0]


def test_a_dimension_with_a_scale_factor_does_not_place_an_undrawn_axis(tmp_path):
    def fn(msp):
        _line_grid_with_undrawn_axis(msp, dim_ab=None, dim_bc=None)
        msp.add_linear_dim(
            base=(18000, 5000),
            p1=(20000, 2000),
            p2=(20000, 8000),
            angle=90,
            dimstyle="Standard",
            override={"dimlfac": 2.0},
        ).render()

    result = run(_plain(tmp_path, fn))
    fam = family(result, "unknown", "A B C")
    assert [a["offset"] for a in fam["axes"]] == [0.0, 6001.5, 12000.0]


def test_a_dimension_whose_text_agrees_only_through_a_scale_factor_does_not_place_an_undrawn_axis(tmp_path):
    """DIMLFAC 2 with the text of twice the span is `agrees`, but the geometry is not the dimension."""

    def fn(msp):
        _line_grid_with_undrawn_axis(msp, dim_ab=None, dim_bc=None)
        msp.add_linear_dim(
            base=(18000, 5000),
            p1=(20000, 2000),
            p2=(20000, 8000),
            angle=90,
            text="12003",
            dimstyle="Standard",
            override={"dimlfac": 2.0},
        ).render()

    result = run(_plain(tmp_path, fn))
    fam = family(result, "unknown", "A B C")
    assert [e["status"] for e in fam["spacings"][0]["dimension_evidence"]] == ["agrees"]
    assert [a["offset"] for a in fam["axes"]] == [0.0, 6001.5, 12000.0]


def test_a_dimension_text_that_differs_does_not_place_an_undrawn_axis(tmp_path):
    def fn(msp):
        _line_grid_with_undrawn_axis(msp, dim_ab=None, dim_bc=None)
        msp.add_linear_dim(
            base=(18000, 5000), p1=(20000, 2000), p2=(20000, 8000), angle=90, text="6100", dimstyle="Standard"
        ).render()

    result = run(_plain(tmp_path, fn))
    fam = family(result, "unknown", "A B C")
    assert [a["offset"] for a in fam["axes"]] == [0.0, 6001.5, 12000.0]
    assert [e["status"] for e in fam["spacings"][0]["dimension_evidence"]] == ["differs"]


def test_two_dimensions_of_one_spacing_that_disagree_do_not_place_the_axis(tmp_path):
    def fn(msp):
        _line_grid_with_undrawn_axis(msp, dim_ab=(2000, 8000), dim_bc=None)
        _vdim(msp, 24000.0, 2000.0, 8004.0)  # 6000 and 6004: their mean (6002) is not the bubble value

    result = run(_plain(tmp_path, fn))
    fam = family(result, "unknown", "A B C")
    assert [a["offset"] for a in fam["axes"]] == [0.0, 6001.5, 12000.0]


def _label_sets(result, sheet="unknown"):
    """Per view of `sheet`, the sorted label strings of its families with a proposal (labels in sorted order:
    a turned family may run the other way)."""
    return sorted(
        sorted(" ".join(sorted(f["proposal"]["labels"].split())) for f in g["families"] if f["proposal"])
        for g in result["groups"]
        if g["sheet"] == sheet
    )


def test_two_disjoint_bubble_lattices_on_one_sheet_are_two_views(tmp_path):
    """REVIEW-FP2 M1: block A (1-3 / A-B) and block B (4-6 / C-D) are two plans, not one grid with a gap."""

    def fn(msp):
        _bubble_lattice(msp)
        _bubble_lattice(msp, x_labels=("4", "5", "6"), y_labels=("C", "D"), x_shift=40000.0, y_shift=30000.0)

    result = run(_plain(tmp_path, fn))
    assert _label_sets(result) == [["1 2 3", "A B"], ["4 5 6", "C D"]]
    assert family(result, "unknown", "4 5 6")["proposal"]["coordinates"] == "0 2*6000"
    assert result["unpaired_bubbles"]["count"] == 0


def test_a_bubble_lattice_component_with_one_pair_in_a_direction_seeds_nothing(tmp_path):
    """Each lattice needs TWO_BUBBLE_SEED_MIN pairs in both directions: the second block has one `D`."""

    def fn(msp):
        _bubble_lattice(msp)
        _bubble_lattice(
            msp, x_labels=("4", "5", "6"), ys=(2000.0,), y_labels=("D",), x_shift=40000.0, y_shift=30000.0
        )

    result = run(_plain(tmp_path, fn))
    assert _label_sets(result) == [["1 2 3", "A B"]]
    assert result["unpaired_bubbles"]["count"] == 8


def test_a_second_bubble_lattice_in_another_orientation_is_its_own_view(tmp_path):
    """REVIEW-FP2 m1: a 0/90 lattice and a separate 45 degree lattice on one sheet are both read."""

    def fn(msp):
        _bubble_lattice(msp)
        _bubble_lattice(msp, x_labels=("4", "5", "6"), y_labels=("C", "D"), x_shift=60000.0, angle=45.0)

    result = run(_plain(tmp_path, fn))
    assert _label_sets(result) == [["1 2 3", "A B"], ["4 5 6", "C D"]]
    assert family(result, "unknown", "4 5 6")["proposal"]["coordinates"] == "0 2*6000"
    assert result["unpaired_bubbles"]["count"] == 0
    assert [q["code"] for q in result["questions"] if q["code"] == "grid_rotated"] == ["grid_rotated"] * 2


def _bare_family(labels, pairings, offsets, dims):
    """A family built by hand for `_place_undrawn_axes`: `dims` maps a spacing index to the measurement of
    the dimension (handle `H<index>`, status `measured`, DIMLFAC 1) between that axis and the next."""
    axes = []
    for i, (label, pairing, offset) in enumerate(zip(labels, pairings, offsets, strict=True)):
        circle = grids_mod._Circle((0.0, offset), R, "model", ())
        bubble = grids_mod._Bubble(circle, {"display_text": label}, "S")
        seg = grids_mod._Seg(i, (0.0, offset), (1000.0, offset), "model", "", "", None, ())
        axes.append(grids_mod._Axis(seg, [bubble], pairing, "S", "model", offset=offset))
    fam = grids_mod._Family("F001", axes, 0.0, (1.0, 0.0), (0.0, 1.0))
    fam.spacings = [b - a for a, b in pairwise(offsets)]
    for k, measured in dims.items():
        dim = grids_mod._Dim(
            (0.0, offsets[k]),
            (0.0, offsets[k] + measured),
            (0.0, 1.0),
            measured,
            1.0,
            4,
            "",
            f"H{k}",
            "model",
            "S",
            (0.0, offsets[k], 500.0, offsets[k] + measured),
        )
        fam.dim_evidence[k].append(
            {
                "handle": f"H{k}",
                "from_label": labels[k],
                "to_label": labels[k + 1],
                "measured": measured,
                "dimlfac": 1.0,
                "status": "measured",
                "_dim": dim,
                "_axes": (axes[k], axes[k + 1]),
                "_item": None,
            }
        )
    return fam


def _placed_handles(fam):
    """spacing index -> the handles of the dimensions its placement cites."""
    return {k: [e["handle"] for e in evs] for k, evs in fam.placed_by.items()}


def test_an_undrawn_axis_is_placed_from_a_dimension_of_a_bare_family():
    """Control for the two guards below: the same family without the guard condition does move."""
    fam = _bare_family(["A", "B", "C"], ["line", "two_bubbles", "line"], [0.0, 6001.5, 12000.0], {0: 6000.0})
    grids_mod._place_undrawn_axes(fam)
    assert [a.offset for a in fam.axes] == [0.0, 6000.0, 12000.0]
    # both spacings of B moved; B-C moved only because B did, so it cites the dimension that placed B
    assert _placed_handles(fam) == {0: ["H0"], 1: ["H0"]}


def test_a_family_with_a_repeated_label_is_not_placed():
    """Dimensions are matched by label; with a label twice they cannot be told apart."""
    fam = _bare_family(["A", "B", "B"], ["line", "two_bubbles", "line"], [0.0, 6001.5, 12000.0], {0: 6000.0})
    fam.issues.add("duplicate")
    grids_mod._place_undrawn_axes(fam)
    assert [a.offset for a in fam.axes] == [0.0, 6001.5, 12000.0]
    assert not fam.placed_by


def test_a_placement_that_would_reorder_the_axes_is_dropped():
    """Axis B would land past C: the order stays (dimension evidence is keyed by spacing index)."""
    fam = _bare_family(["A", "B", "C"], ["line", "two_bubbles", "line"], [0.0, 6001.5, 6003.0], {0: 6005.0})
    assert grids_mod._place_undrawn_axes(fam) == "B"  # the axes it would have moved
    assert [a.offset for a in fam.axes] == [0.0, 6001.5, 6003.0]
    assert not fam.placed_by


def test_a_dropped_placement_is_a_warning_naming_the_view_family_and_axes():
    """Never silent: the caller says which view and family kept its bubble positions, and for which axes."""
    fam = _bare_family(["A", "B", "C"], ["line", "two_bubbles", "line"], [0.0, 6001.5, 6003.0], {0: 6005.0})
    group = grids_mod._Group("V007", "S-101", "model", list(fam.axes), [fam])
    ctx = grids_mod._Ctx("f.dxf", "medium", {}, None)  # type: ignore[arg-type]
    grids_mod._dimension_located_two_bubbles([group], ctx)
    assert len(ctx.warnings) == 1
    assert "V007/F001" in ctx.warnings[0] and "S-101" in ctx.warnings[0] and "axes B" in ctx.warnings[0]


def _extra_bubbles(msp, label, *points):
    for p in points:
        _bubble(msp, p, label)


def test_a_label_reused_elsewhere_on_the_sheet_keeps_the_pair_that_crosses_the_lattice(tmp_path):
    """REVIEW-FP2 M2: a detail bubble `1` at the side of the plan made four `1` bubbles, and axis 1 vanished
    from the lattice without a question."""

    def fn(msp):
        _bubble_lattice(msp)
        _extra_bubbles(msp, "1", (40000.0, 0.0), (40000.0, 9000.0))

    result = run(_plain(tmp_path, fn))
    numbers = family(result, "unknown", "1 2 3")
    assert numbers["proposal"]["coordinates"] == "0 2*6000"
    assert [b["label"] for b in result["unpaired_bubbles"]["listed"]] == ["1", "1"]
    assert result["unpaired_bubbles"]["count"] == 2
    assert len(questions(result, "grid_two_bubble_axis")) == 5  # one per axis; the reuse raised nothing


def test_a_reused_label_with_two_pairs_across_the_lattice_is_left_unpaired_and_asked(tmp_path):
    """Two pairs of `1` both run across the lattice: neither is taken, the bubbles are listed and a blocking
    question names them (never guess which one is axis 1)."""

    def fn(msp):
        _bubble_lattice(msp)
        _extra_bubbles(msp, "1", (3000.0, -R), (3000.0, 12000 + R))

    result = run(_plain(tmp_path, fn))
    assert _label_sets(result) == [["2 3", "A B"]]
    assert result["unpaired_bubbles"]["count"] == 4
    ambiguous = [q for q in questions(result, "grid_two_bubble_axis") if q["found"].startswith("label 1")]
    assert len(ambiguous) == 1 and ambiguous[0]["blocking"]
    assert grids_mod.question_families(ambiguous[0], result) is not None


def test_axes_tilted_either_side_of_the_angle_wrap_are_one_direction(tmp_path):
    """Canonical angles run from -0.5 to 179.5 degrees: `A` at 179.4 and `B` at -0.4 are 0.2 apart across
    the wrap, so they are one direction and the lattice has two horizontal axes."""
    turn = -0.4  # the lattice is rotated by this; A is then turned a further -0.2 degrees (179.4)

    def at(x, y):
        c, s = math.cos(math.radians(turn)), math.sin(math.radians(turn))
        return (x * c - y * s, x * s + y * c)

    def fn(msp):
        _bubble_lattice(msp, xs=(0.0, 6000.0), x_labels=("1", "2"), ys=(8000.0,), y_labels=("B",), angle=turn)
        drop = 6800 * math.tan(math.radians(0.2))
        _bubble(msp, at(-R, 2000.0), "A")
        _bubble(msp, at(6000 + R, 2000.0 - drop), "A")

    result = run(_plain(tmp_path, fn))
    assert _label_sets(result) == [["1 2", "A B"]]


def test_a_pair_shorter_than_an_axis_is_not_a_candidate_for_a_reused_label(tmp_path):
    """A third `1` just above the bottom row of `A`: its short pair with the bottom bubble crosses the lattice
    but is no axis, so only the two long pairs are named in the question."""

    def fn(msp):
        _bubble_lattice(msp)
        _extra_bubbles(msp, "1", (0.0, 2100.0))

    result = run(_plain(tmp_path, fn))
    ambiguous = [q for q in questions(result, "grid_two_bubble_axis") if q["found"].startswith("label 1")]
    assert len(ambiguous) == 1
    assert ambiguous[0]["found"].count(" to ") == 2


def test_a_reused_label_takes_the_pair_that_runs_the_way_its_kind_runs(tmp_path):
    """Numbers run one way and letters the other: of two pairs of `1` that cross the lattice, only the one
    parallel to the other number axes is a candidate; the horizontal one (a section mark) is not."""

    def fn(msp):
        _bubble_lattice(msp)
        _extra_bubbles(msp, "1", (-2000.0 - R, 5000.0), (14000.0 + R, 5000.0))

    result = run(_plain(tmp_path, fn))
    assert family(result, "unknown", "1 2 3")["proposal"]["coordinates"] == "0 2*6000"
    assert family(result, "unknown", "A B")["proposal"]["coordinates"] == "0 6000"
    assert result["unpaired_bubbles"]["count"] == 2
    assert len(questions(result, "grid_two_bubble_axis")) == 5


def test_a_reused_label_that_leaves_a_direction_with_one_axis_seeds_nothing(tmp_path):
    """REVIEW-FP2 B2: with `A` reused only `B` is left in its direction, so no view is seeded; the bubbles are
    listed and the missing grid is asked (grid_none_found), not guessed."""

    def fn(msp):
        _bubble_lattice(msp)
        _extra_bubbles(msp, "A", (40000.0, 0.0), (49000.0, 0.0))

    result = run(_plain(tmp_path, fn))
    assert result["groups"] == []
    assert questions(result, "grid_none_found")


def _two_grids_one_sheet(msp, second_xs):
    _grid_at(msp)
    _grid_at(msp, ox=60000.0, xs=second_xs)


def test_a_scale_is_judged_by_the_mean_ratio_not_the_first_one(tmp_path):
    """REVIEW-FP2 m2: ratios 1.0012 and 1.000225 are one ratio within SCALE_TOL, but their mean (1.000712) is
    within SCALE_TOL of 1: a real difference plus noise, not a view at another scale."""
    xs = (0.0, 6000.0 / 1.0012, 6000.0 / 1.0012 + 6000.0 / 1.000225)
    result = run(_plain(tmp_path, lambda m: _two_grids_one_sheet(m, xs)))
    assert not questions(result, "grid_scale_differs")
    assert [c["status"] for c in result["cross_checks"] if len(c["common_labels"]) == 3] == ["mismatch"]


def test_a_constant_ratio_beyond_the_tolerance_is_still_a_scale(tmp_path):
    xs = (0.0, 6000.0 / 1.01, 12000.0 / 1.01)
    result = run(_plain(tmp_path, lambda m: _two_grids_one_sheet(m, xs)))
    assert len(questions(result, "grid_scale_differs")) == 1
    assert [c["status"] for c in result["cross_checks"] if len(c["common_labels"]) == 3] == ["scaled"]


# --- review of FP2b: stale dimension status, undrawn tail, tilted reused label, provenance ----------


def _dim_with_text(msp, x, y1, y2, text):
    msp.add_linear_dim(
        base=(x - 1500, (y1 + y2) / 2), p1=(x, y1), p2=(x, y2), angle=90, dimstyle="Standard", text=text
    ).render()


def _lattice_c_off(msp, span_text):
    """A pure lattice `1 2 3` x `A B C` (A-B 4000, B-C 4000) whose C bubbles sit 1.5 off, with a dimension per
    spacing (no text) and an overall A-C dimension showing `span_text`."""
    _bubble_lattice(msp, ys=(2000.0, 6000.0, 10001.5), y_labels=("A", "B", "C"))
    _vdim(msp, 20000.0, 2000, 6000)
    _vdim(msp, 20000.0, 6000, 10000)
    _dim_with_text(msp, 24000.0, 2000, 10000, span_text)


def _non_view_evidence(spacing):
    return [e for e in spacing["evidence"] if e["kind"] != "other_view"]


def test_a_span_dimension_judged_before_an_undrawn_axis_moved_is_judged_again_after(tmp_path):
    """REVIEW-FP2b M1: C moves from 8001.5 to 8000 onto its dimensions, so the overall A-C dimension that
    reads `8000` agrees; it was `differs` at match time and raised a blocking override question."""
    result = run(_plain(tmp_path, lambda m: _lattice_c_off(m, "8000")))
    fam = family(result, "unknown", "A B C")
    assert [a["offset"] for a in fam["axes"]] == [0.0, 4000.0, 8000.0]
    for spacing in fam["spacings"]:
        span = [e for e in spacing["dimension_evidence"] if e["text"] == "8000"]
        assert [e["status"] for e in span] == ["agrees"]
        assert span[0]["displayed"] == 8000.0
        assert _non_view_evidence(spacing) and all(e["agrees"] for e in _non_view_evidence(spacing))
        assert all("(agrees)" in e["ref"] or "(measured)" in e["ref"] for e in _non_view_evidence(spacing))
    assert not questions(result, "grid_dimension_override_mismatch")


def test_a_span_dimension_that_agreed_with_the_bubbles_but_not_with_the_moved_axis_is_asked(tmp_path):
    """The other way round: `8001.5` equals the bubble span, not the dimensions' 8000 the axis moved onto, so
    it differs after the move and is asked (a stale `agrees` would hide it)."""
    result = run(_plain(tmp_path, lambda m: _lattice_c_off(m, "8001.5")))
    fam = family(result, "unknown", "A B C")
    assert [a["offset"] for a in fam["axes"]] == [0.0, 4000.0, 8000.0]
    assert {
        e["status"] for s in fam["spacings"] for e in s["dimension_evidence"] if e["text"] == "8001.5"
    } == {"differs"}
    assert any(not e["agrees"] for s in fam["spacings"] for e in _non_view_evidence(s))
    assert len(questions(result, "grid_dimension_override_mismatch")) == 1


def test_a_span_dimension_with_a_wrong_text_is_still_asked_after_the_move(tmp_path):
    result = run(_plain(tmp_path, lambda m: _lattice_c_off(m, "8100")))
    assert len(questions(result, "grid_dimension_override_mismatch")) == 1


def _tail_grid(msp, dim_bc=True, dim_cd=True, dim_cd_again=None):
    """Lines `1 2 3` x `A B` (y 2000, 8000) and two axes drawn as bubble pairs only: `C` (14000, 1.5 off) and
    `D` (20000, 3 off), so D has no drawn neighbour. A dimension between B-C and C-D as asked."""
    for x, label in ((0.0, "1"), (6000.0, "2"), (12000.0, "3")):
        msp.add_line((x, 0), (x, 22000))
        _bubble(msp, (x, -R), label)
    for y, label in ((2000.0, "A"), (8000.0, "B")):
        msp.add_line((-2000, y), (14000, y))
        _bubble(msp, (-2000 - R, y), label)
    for y, label in ((14001.5, "C"), (20003.0, "D")):
        _bubble(msp, (-2000 - R, y), label)
        _bubble(msp, (14000 + R, y), label)
    if dim_bc:
        _vdim(msp, 20000.0, 8000, 14000)
    if dim_cd:
        _vdim(msp, 22000.0, 14000, 20000)
    if dim_cd_again is not None:
        _vdim(msp, 24000.0, 14000, dim_cd_again)


def test_the_undrawn_tail_of_a_line_family_is_chained_through_its_own_spacings_dimension(tmp_path):
    """REVIEW-FP2b M2: C is placed from the drawn B, D from the placed C through the C-D dimension; each
    spacing cites its own dimension only."""
    result = run(_plain(tmp_path, _tail_grid))
    fam = family(result, "unknown", "A B C D")
    assert [a["pairing"] for a in fam["axes"]] == ["line", "line", "two_bubbles", "two_bubbles"]
    assert [a["offset"] for a in fam["axes"]] == [0.0, 6000.0, 12000.0, 18000.0]
    assert [s["measured"] for s in fam["spacings"]] == [6000.0, 6001.5, 6001.5]
    assert fam["proposal"]["coordinates"] == "0 3*6000"
    cited = [
        [
            d["region"]["detail"]
            for d in s["value"]["provenance"]["derived_from"]
            if d["method"] == "dxf_dimension_measured"
        ]
        for s in fam["spacings"]
    ]
    assert [len(c) for c in cited] == [0, 1, 1]
    assert cited[1] != cited[2]


@pytest.mark.parametrize(
    ("kwargs", "last"),
    [
        ({"dim_cd": False}, 18003.0),  # no C-D dimension: D stays at its bubbles
        ({"dim_cd_again": 20004.0}, 18003.0),  # 6000 and 6004 disagree: D stays
        ({"dim_bc": False}, 18003.0),  # C has no dimension, so it is no anchor for D
    ],
)
def test_an_undrawn_tail_axis_with_no_usable_dimension_stays_at_its_bubbles(tmp_path, kwargs, last):
    result = run(_plain(tmp_path, lambda m: _tail_grid(m, **kwargs)))
    fam = family(result, "unknown", "A B C D")
    assert fam["axes"][-1]["offset"] == last
    assert [a["offset"] for a in fam["axes"][:2]] == [0.0, 6000.0]  # the lines never move


def test_a_chain_of_undrawn_axes_in_a_bare_family_cites_one_spacing_each():
    """The reviewer's r3: C and D 1.5 off after drawn B. C-D keeps 6000 (both moved by 1.5), so only B-C
    changed and cites its dimension."""
    fam = _bare_family(
        ["A", "B", "C", "D"],
        ["line", "line", "two_bubbles", "two_bubbles"],
        [0, 6000, 12001.5, 18001.5],
        {1: 6000.0, 2: 6000.0},
    )
    assert grids_mod._place_undrawn_axes(fam) is None
    assert [a.offset for a in fam.axes] == [0, 6000, 12000.0, 18000.0]
    assert fam.spacings == [6000, 6000.0, 6000.0]
    assert _placed_handles(fam) == {1: ["H1"]}
    assert fam.bubble_spacing == {1: 6001.5}


def test_each_spacing_of_a_chain_cites_the_dimension_it_was_placed_through():
    fam = _bare_family(
        ["A", "B", "C", "D"],
        ["line", "line", "two_bubbles", "two_bubbles"],
        [0, 6000, 12001.5, 18003.0],
        {1: 6000.0, 2: 6000.0},
    )
    assert grids_mod._place_undrawn_axes(fam) is None
    assert [a.offset for a in fam.axes] == [0, 6000, 12000.0, 18000.0]
    assert _placed_handles(fam) == {1: ["H1"], 2: ["H2"]}
    assert fam.bubble_spacing == {1: 6001.5, 2: 6001.5}


def test_an_undrawn_head_is_chained_from_the_drawn_axis_on_its_right():
    fam = _bare_family(
        ["A", "B", "C", "D"],
        ["two_bubbles", "two_bubbles", "line", "line"],
        [-1.5, 6001.5, 12000.0, 18000.0],
        {0: 6000.0, 1: 6000.0},
    )
    assert grids_mod._place_undrawn_axes(fam) is None
    assert [a.offset for a in fam.axes] == [0.0, 6000.0, 12000.0, 18000.0]
    assert _placed_handles(fam) == {0: ["H0"], 1: ["H1"]}


def test_an_undrawn_axis_that_stays_at_its_bubbles_is_not_an_anchor():
    """Only the C-D dimension exists: C has none to a placed neighbour, so D is not placed from C's bubble."""
    fam = _bare_family(
        ["A", "B", "C", "D"],
        ["line", "line", "two_bubbles", "two_bubbles"],
        [0.0, 6000.0, 12001.5, 18001.5],
        {2: 6000.0},
    )
    assert grids_mod._place_undrawn_axes(fam) is None
    assert [a.offset for a in fam.axes] == [0.0, 6000.0, 12001.5, 18001.5]
    assert not fam.placed_by


def test_a_dimension_without_a_handle_is_cited_as_handle_unknown():
    """REVIEW-FP2b m: never `dimension ?`; the entry keeps its extents (the DIMENSION's own) either way."""
    ev = {"handle": None, "from_label": "A", "to_label": "B", "text": "6000", "status": "agrees"}
    assert grids_mod._handle_text(None) == "handle unknown"
    assert grids_mod._dimension_item(ev)["ref"] == "dimension handle unknown A-B text '6000' (agrees)"


def _tilted_one_lattice(msp, reuse):
    """Lattice `2 3` x `A B` and an axis `1` drawn as a bubble pair tilted 0.2 degrees (the lattice's axes are
    exact); with `reuse`, a detail pair of `1` far to the side makes four bubbles."""
    _bubble_lattice(msp, xs=(6000.0, 12000.0), x_labels=("2", "3"))
    _bubble(msp, (0.0, -R), "1")
    _bubble(msp, (12800 * math.tan(math.radians(0.2)), 12000 + R), "1")
    if reuse:
        _extra_bubbles(msp, "1", (40000.0, 0.0), (40000.0, 9000.0))


def test_a_reused_label_with_a_slightly_tilted_axis_is_taken_or_asked_never_dropped(tmp_path):
    """REVIEW-FP2b M3 (r2): `across` was the lattice axes perpendicular to the candidate's own angle, so a
    pair 0.2 degrees off (more than ORTHO_TOL) found none to cross and axis 1 vanished without a question."""
    result = run(_plain(tmp_path, lambda m: _tilted_one_lattice(m, reuse=True)))
    taken = ["1 2 3", "A B"] in _label_sets(result)
    asked = [q for q in questions(result, "grid_two_bubble_axis") if q["found"].startswith("label 1")]
    assert taken or (len(asked) == 1 and asked[0]["blocking"])


def test_a_reused_label_with_a_slightly_tilted_axis_is_taken(tmp_path):
    """The pair crosses the horizontal axes of the lattice (perpendicular to axis 2, which it runs along), so
    it is axis 1; only the detail pair stays unpaired."""
    result = run(_plain(tmp_path, lambda m: _tilted_one_lattice(m, reuse=True)))
    assert _label_sets(result) == [["1 2 3", "A B"]]
    # axis 1 is measured at its midpoint, 22 off the foot of its 0.2 degree tilt
    assert family(result, "unknown", "1 2 3")["proposal"]["coordinates"] == "0 5978 6000"
    assert result["unpaired_bubbles"]["count"] == 2
    assert not [q for q in questions(result, "grid_two_bubble_axis") if q["found"].startswith("label 1")]


def test_a_reused_label_whose_pair_runs_along_the_axes_but_crosses_none_is_asked(tmp_path):
    """REVIEW-FP2b M3: three `1` bubbles, the only long pair runs the way number axes run but beside the plan
    (no horizontal axis reaches it): no pair is taken and the blocking question names the pair."""

    def fn(msp):
        _bubble_lattice(msp, xs=(6000.0, 12000.0), x_labels=("2", "3"))
        _extra_bubbles(msp, "1", (40000.0, 0.0), (40000.0, 9000.0), (41000.0, 0.0))

    result = run(_plain(tmp_path, fn))
    assert _label_sets(result) == [["2 3", "A B"]]
    assert result["unpaired_bubbles"]["count"] == 3
    asked = [q for q in questions(result, "grid_two_bubble_axis") if q["found"].startswith("label 1")]
    assert len(asked) == 1 and asked[0]["blocking"]
    assert "(40000.0, 0.0) to (40000.0, 9000.0)" in asked[0]["found"]
    assert "none runs across it" in asked[0]["message"]
    assert grids_mod.question_families(asked[0], result) is not None


def test_a_reused_label_with_no_pair_along_any_axis_is_not_asked(tmp_path):
    """A detail mark whose bubbles run the wrong way for its kind is just unpaired, as before."""

    def fn(msp):
        _bubble_lattice(msp, xs=(6000.0, 12000.0), x_labels=("2", "3"))
        _extra_bubbles(msp, "1", (40000.0, 0.0), (49000.0, 0.0), (49000.0, 800.0))

    result = run(_plain(tmp_path, fn))
    assert result["unpaired_bubbles"]["count"] == 3
    assert not [q for q in questions(result, "grid_two_bubble_axis") if q["found"].startswith("label 1")]


def test_a_blocking_question_is_never_capped_by_the_per_code_limit():
    ask = grids_mod._Ask()
    for i in range(grids_mod.MAX_QUESTIONS_PER_CODE + 1):
        ask("grid_x", False, "m", f"w{i}", "f")
    ask("grid_x", True, "m", "blocking", "f")
    listed = [q for q in ask.questions if q["code"] == "grid_x"]
    assert len(listed) == grids_mod.MAX_QUESTIONS_PER_CODE + 1
    assert [q["where"] for q in listed if q["blocking"]] == ["blocking"]
    assert ask.counts["grid_x"] == grids_mod.MAX_QUESTIONS_PER_CODE + 2
    assert ask.capped["grid_x"] == grids_mod.MAX_QUESTIONS_PER_CODE + 1
    ask("grid_x", False, "m", "late", "f")
    assert [q["where"] for q in ask.questions].count("late") == 0


def test_non_blocking_questions_past_the_cap_are_counted_not_listed():
    ask = grids_mod._Ask()
    for i in range(grids_mod.MAX_QUESTIONS_PER_CODE + 1):
        ask("grid_x", False, "m", f"w{i}", "f")
    assert len(ask.questions) == grids_mod.MAX_QUESTIONS_PER_CODE
    assert ask.counts["grid_x"] == grids_mod.MAX_QUESTIONS_PER_CODE + 1
