"""grids, tool wave 4 package G: visibility of text and lines, obround bubbles, family consistency, pairing,
stray families, `*` labels and stacked views, elevation families, grid-system units evidence.

Synthetic DXF only (tests/_dxf_fixtures.py helpers); corpus checks live in the wave 4 evidence notes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from ezdxf.enums import TextEntityAlignment

from _dxf_fixtures import TH, R
from tekla_harness.extract_text import extract_text
from tekla_harness.grids import extract_grids
from tekla_harness.schemas import validate
from tekla_harness.sheets import extract_sheets
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
