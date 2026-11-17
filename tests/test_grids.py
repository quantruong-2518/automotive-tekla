"""grids: bubbles, axes, views, families, spacings, cross-sheet checks and coordinate proposals.

Fixtures are synthetic (tests/_dxf_fixtures.py); no sample drawing text is used.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

import pytest
from ezdxf.enums import TextEntityAlignment
from ezdxf.filemanagement import new

from _dxf_fixtures import TH, R, build_set
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
    assert any("2 'grid_rotated' questions" in w for w in result["warnings"])


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
