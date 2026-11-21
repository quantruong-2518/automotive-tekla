"""sheets: a sheet-number or job-number label pairs with its value inside its title-block cell (wave 4, V3).

Synthetic title blocks (tests/_titleblock_fixtures.py): a job cell above a drawing-number cell, the value of
each centred in its cell and set larger than its label, so the value's centre is not on the label's line.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from _titleblock_fixtures import FH, FW, add_frame, add_title_block, sheet_set
from tekla_harness.extract_text import extract_text
from tekla_harness.schemas import validate
from tekla_harness.sheets import extract_sheets


def run(tmp_path: Path, blocks: list[dict[str, Any]], *, lines: bool = True) -> dict[str, Any]:
    doc, msp = sheet_set()
    for i, b in enumerate(blocks):
        x = i * (FW + 5000.0)
        add_frame(msp, x)
        add_title_block(msp, x, b["number"], b["job"], lines=lines, **b.get("labels", {}))
    path = tmp_path / "tb.dxf"
    doc.saveas(path)
    result = extract_sheets(path, extract_text(path))
    assert validate("sheets", result) == [], validate("sheets", result)
    json.dumps(result, allow_nan=False)
    return result


def numbers(result: dict[str, Any]) -> list[str | None]:
    return [
        s["title_block"]["sheet_number"] and s["title_block"]["sheet_number"]["value"]
        for s in result["sheets"]
    ]


def jobs(result: dict[str, Any]) -> list[str | None]:
    return [
        s["title_block"]["job_number"] and s["title_block"]["job_number"]["value"] for s in result["sheets"]
    ]


def cands(result: dict[str, Any], sid: str, field: str) -> list[dict[str, Any]]:
    s = next(s for s in result["sheets"] if s["sheet_id"] == sid)
    return [c for c in s["title_block"]["candidates"] if c["field"] == field]


BLOCKS = [{"number": "P-01A", "job": "J-01"}, {"number": "3D-1", "job": "J-01"}]


@pytest.mark.parametrize("lines", [True, False], ids=["cell_lines", "no_cell_lines"])
def test_number_label_takes_the_value_of_its_cell_and_the_job_label_its_own(tmp_path, lines):
    result = run(tmp_path, BLOCKS, lines=lines)
    assert numbers(result) == ["P-01A", "3D-1"]  # 3D-1 is not sheet-code shaped: only the label finds it
    assert "sheet_number_missing" not in [q["code"] for q in result["questions"]]
    n = cands(result, "model#01", "sheet_number")
    assert [(c["value"], c["evidence"]["kind"], c["evidence"]["key"]) for c in n] == [
        ("P-01A", "adjacent_label", "DRAWING NO.:")
    ]
    j = cands(result, "model#01", "job_number")
    if lines:
        assert jobs(result) == ["J-01", "J-01"]
        assert [(c["value"], c["evidence"]["kind"]) for c in j] == [("J-01", "adjacent_label")]
    else:
        # without drawn cells a value below a label must overlap it in x (J-01 is centred in a wide cell): it
        # pairs with no label, and it is never the drawing-number label's value
        assert jobs(result) == [None, None]
        assert j == []


def test_the_chosen_values_entry_ids_are_in_the_candidates(tmp_path):
    result = run(tmp_path, BLOCKS)
    s = result["sheets"][0]
    n, j = cands(result, "model#01", "sheet_number")[0], cands(result, "model#01", "job_number")[0]
    assert n["evidence"]["value_text_id"] != j["evidence"]["value_text_id"]
    assert n["evidence"]["label_text_id"] and j["evidence"]["label_text_id"]
    assert s["title_block"]["job_number"]["provenance"]["sheet"] == "model#01"
    assert s["title_block"]["job_number"]["confidence"] == "low"  # a label pairing is low, like sheet numbers


def test_a_value_claimed_as_job_number_is_never_a_sheet_number(tmp_path):
    # no sheet-number label at all: J-01 is sheet-code shaped and sits in the corner of both sheets
    doc, msp = sheet_set()
    for i in range(2):
        x = i * (FW + 5000.0)
        add_frame(msp, x)
        add_title_block(msp, x, "unused", "J-01", number_label="NOTE:")
    path = tmp_path / "jobonly.dxf"
    doc.saveas(path)
    result = extract_sheets(path, extract_text(path))
    assert jobs(result) == ["J-01", "J-01"]
    assert numbers(result) == [None, None]
    assert not [
        c for s in result["sheets"] for c in s["title_block"]["candidates"] if c["field"] == "sheet_number"
    ]
    assert "sheet_number_missing" in [q["code"] for q in result["questions"]]


@pytest.mark.parametrize(
    ("label", "value"),
    [
        ("JOB NO.:", "J-07"),
        ("MÃ CÔNG TRÌNH:", "CT-2024/05"),
        ("SỐ HĐ:", "08/2008 VKH"),
        ("job number", "JN-4"),
    ],
)
def test_job_labels(tmp_path, label, value):
    result = run(tmp_path, [{"number": "S-1", "job": value, "labels": {"job_label": label}}] * 2)
    assert jobs(result) == [value, value]
    assert numbers(result) == ["S-1", "S-1"]


def test_inline_job_label(tmp_path):
    doc, msp = sheet_set()
    add_frame(msp, 0.0)
    msp.add_text("SỐ HĐ: 08/2008 VKH", height=200, dxfattribs={"insert": (60000.0, 3000.0)})
    msp.add_text("DRAWING NO.:", height=200, dxfattribs={"insert": (60000.0, 2000.0)})
    msp.add_text("KC-03", height=200, dxfattribs={"insert": (64000.0, 2000.0)})
    path = tmp_path / "inline.dxf"
    doc.saveas(path)
    result = extract_sheets(path, extract_text(path))
    j = cands(result, "model#01", "job_number")
    assert [(c["value"], c["evidence"]["kind"]) for c in j] == [("08/2008 VKH", "inline_label")]
    assert numbers(result) == ["KC-03"]


def test_two_job_values_on_one_sheet_are_a_non_blocking_conflict(tmp_path):
    doc, msp = sheet_set()
    add_frame(msp, 0.0)
    msp.add_text("JOB NO.: J-01", height=200, dxfattribs={"insert": (60000.0, 3000.0)})
    msp.add_text("JOB NO.: J-02", height=200, dxfattribs={"insert": (60000.0, 2000.0)})
    path = tmp_path / "jobs.dxf"
    doc.saveas(path)
    result = extract_sheets(path, extract_text(path))
    assert jobs(result) == [None]
    conflict = [
        q for q in result["questions"] if q["code"] == "title_field_conflict" and "job_number" in q["message"]
    ]
    assert len(conflict) == 1 and conflict[0]["blocking"] is False


def test_job_number_is_null_when_there_is_none(tmp_path):
    doc, msp = sheet_set()
    add_frame(msp, 0.0)
    msp.add_text("DRAWING NO.:", height=200, dxfattribs={"insert": (60000.0, 2000.0)})
    msp.add_text("KC-03", height=200, dxfattribs={"insert": (64000.0, 2000.0)})
    path = tmp_path / "nojob.dxf"
    doc.saveas(path)
    result = extract_sheets(path, extract_text(path))
    assert "job_number" in result["sheets"][0]["title_block"]
    assert result["sheets"][0]["title_block"]["job_number"] is None


def test_a_value_pairs_with_one_label_only_the_nearer(tmp_path):
    # JOB NO. and DRAWING NO. on one row, a single value right of both: it belongs to the nearer label
    doc, msp = sheet_set()
    add_frame(msp, 0.0)
    y = 3000.0
    msp.add_text("JOB NO.:", height=300, dxfattribs={"insert": (50000.0, y)})
    msp.add_text("DRAWING NO.:", height=300, dxfattribs={"insert": (55000.0, y)})
    msp.add_text("Z-5", height=300, dxfattribs={"insert": (59500.0, y)})
    path = tmp_path / "two.dxf"
    doc.saveas(path)
    result = extract_sheets(path, extract_text(path))
    assert numbers(result) == ["Z-5"]
    assert jobs(result) == [None]


def test_a_value_above_or_left_of_its_label_is_not_paired(tmp_path):
    doc, msp = sheet_set()
    add_frame(msp, 0.0)
    msp.add_text("KC-04", height=300, dxfattribs={"insert": (55000.0, 4000.0)})  # above
    msp.add_text("KC-05", height=300, dxfattribs={"insert": (50000.0, 3000.0)})  # left
    msp.add_text("DRAWING NO.:", height=300, dxfattribs={"insert": (55000.0, 3000.0)})
    path = tmp_path / "wrongway.dxf"
    doc.saveas(path)
    result = extract_sheets(path, extract_text(path))
    assert not cands(result, "model#01", "sheet_number") or all(
        c["evidence"]["kind"] != "adjacent_label" for c in cands(result, "model#01", "sheet_number")
    )


def test_frame_height_constant_is_a_landscape_a_sheet():
    assert 1.2 <= FW / FH <= 1.8


# --- cell rules ------------------------------------------------------------------------------------------


def _sheet_with(tmp_path: Path, build) -> dict[str, Any]:
    doc, msp = sheet_set()
    add_frame(msp, 0.0)
    build(msp)
    path = tmp_path / "cells.dxf"
    doc.saveas(path)
    return extract_sheets(path, extract_text(path))


def _box(msp: Any, x0: float, y0: float, x1: float, y1: float) -> None:
    for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        msp.add_line(a, b)


def _paired(result: dict[str, Any], field: str = "sheet_number") -> list[tuple[str, str]]:
    return [
        (c["value"], c["evidence"]["kind"])
        for c in result["sheets"][0]["title_block"]["candidates"]
        if c["field"] == field
    ]


def test_a_cell_value_beats_a_nearer_value_of_a_label_without_a_cell(tmp_path):
    # Q-1 sits inside the DRAWING NO. cell (low, under the label); 'JOB NO.:' stands just outside the cell's
    # left line, has no cell of its own and Q-1 on its row, nearer: the cell label still gets Q-1
    def build(msp):
        _box(msp, 60000, 0, 68000, 3500)
        msp.add_text("DRAWING NO.:", height=300, dxfattribs={"insert": (60200, 3000)})
        msp.add_text("Q-1", height=300, dxfattribs={"insert": (60300, 300)})
        msp.add_text("JOB NO.:", height=300, dxfattribs={"insert": (57600, 300)})

    result = _sheet_with(tmp_path, build)
    assert _paired(result) == [("Q-1", "adjacent_label")]
    assert _paired(result, "job_number") == []


def test_only_the_labels_own_cell_is_searched_when_it_holds_a_value(tmp_path):
    # NEXT-2 (next cell, the label's row) is nearer than OWN-1 (own cell, low): the cell decides
    def build(msp):
        _box(msp, 60000, 0, 66000, 3500)
        msp.add_text("DRAWING NO.:", height=300, dxfattribs={"insert": (62900, 3000)})
        msp.add_text("OWN-1", height=300, dxfattribs={"insert": (63000, 100)})
        msp.add_text("NEXT-2", height=300, dxfattribs={"insert": (66100, 3000)})

    assert _paired(_sheet_with(tmp_path, build)) == [("OWN-1", "adjacent_label")]


def test_a_label_takes_one_value_the_nearest_in_its_cell(tmp_path):
    def build(msp):
        _box(msp, 60000, 1000, 70000, 3000)
        msp.add_text("DRAWING NO.:", height=300, dxfattribs={"insert": (60200, 2500)})
        msp.add_text("NEAR-1", height=300, dxfattribs={"insert": (64000, 2500)})
        msp.add_text("FAR-2", height=300, dxfattribs={"insert": (67000, 1300)})

    assert _paired(_sheet_with(tmp_path, build)) == [("NEAR-1", "adjacent_label")]


def test_values_above_or_left_of_the_label_in_its_cell_are_not_paired(tmp_path):
    def build(msp):
        _box(msp, 60000, 0, 72000, 5000)
        msp.add_text("ABOVE-1", height=300, dxfattribs={"insert": (66000, 4300)})
        msp.add_text("LEFT-2", height=300, dxfattribs={"insert": (60200, 2000)})
        msp.add_text("DRAWING NO.:", height=300, dxfattribs={"insert": (63000, 2000)})

    assert _paired(_sheet_with(tmp_path, build)) == []


def test_a_box_taller_than_twelve_label_heights_is_no_cell(tmp_path):
    # 30 label heights tall (the label is 15 heights from each line), 53 wide: the value is 32 heights right
    # of the label, past the 30-height reach
    def build(msp):
        _box(msp, 60000, 0, 76000, 9000)
        msp.add_text("DRAWING NO.:", height=300, dxfattribs={"insert": (60200, 4500)})
        msp.add_text("KC-9", height=300, dxfattribs={"insert": (60200 + 2520 + 32 * 300, 4500)})

    assert _paired(_sheet_with(tmp_path, build)) == []


def test_a_box_wider_than_sixty_label_heights_is_no_cell(tmp_path):
    def build(msp):
        _box(msp, 20000, 2000, 60000, 4000)  # 40 000 wide: 133 label heights
        msp.add_text("DRAWING NO.:", height=300, dxfattribs={"insert": (20500, 3300)})
        msp.add_text("KC-9", height=300, dxfattribs={"insert": (20500 + 3000 + 40 * 300, 3300)})

    assert _paired(_sheet_with(tmp_path, build)) == []


def _far_value(msp: Any) -> None:
    """A label and a value 32 label heights right of it: only a cell can pair them (the reach is 30)."""
    msp.add_text("DRAWING NO.:", height=300, dxfattribs={"insert": (60200, 2500)})
    msp.add_text("KC-9", height=300, dxfattribs={"insert": (60200 + 2520 + 32 * 300, 2500)})


def test_the_far_value_is_paired_inside_a_closed_cell(tmp_path):
    def build(msp):
        _box(msp, 60000, 1000, 75000, 3000)
        _far_value(msp)

    assert _paired(_sheet_with(tmp_path, build)) == [("KC-9", "adjacent_label")]


def _hidden_cell(layer_attribs: dict[str, Any], entity_attribs: dict[str, Any] | None = None):
    """A closed cell around the far value, drawn on a layer set up by `layer_attribs`."""

    def build(msp):
        doc = msp.doc
        layer = doc.layers.add("CELL")
        if layer_attribs.get("off"):
            layer.off()
        if layer_attribs.get("freeze"):
            layer.freeze()
        if layer_attribs.get("plot") is False:
            layer.dxf.plot = 0
        attribs = {"layer": "CELL", **(entity_attribs or {})}
        for a, b in (
            ((60000, 1000), (75000, 1000)),
            ((75000, 1000), (75000, 3000)),
            ((75000, 3000), (60000, 3000)),
            ((60000, 3000), (60000, 1000)),
        ):
            msp.add_line(a, b, dxfattribs=attribs)
        _far_value(msp)

    return build


@pytest.mark.parametrize(
    ("layer_attribs", "entity_attribs", "closes"),
    [
        ({}, None, True),  # control: a normal layer closes the cell
        ({"off": True}, None, False),
        ({"freeze": True}, None, False),
        ({"plot": False}, None, False),
        ({}, {"invisible": 1}, False),  # group 60 on the line itself
    ],
    ids=["printed", "layer_off", "layer_frozen", "layer_no_plot", "entity_invisible"],
)
def test_cell_lines_come_from_printed_geometry_only(tmp_path, layer_attribs, entity_attribs, closes):
    result = _sheet_with(tmp_path, _hidden_cell(layer_attribs, entity_attribs))
    assert _paired(result) == ([("KC-9", "adjacent_label")] if closes else [])


def test_cell_lines_in_a_block_take_the_insert_layer_when_drawn_on_layer_0(tmp_path):
    def build(msp):
        doc = msp.doc
        doc.layers.add("OFFCELL").off()
        blk = doc.blocks.new("CELL_BOX")
        for a, b in (
            ((0, 0), (15000, 0)),
            ((15000, 0), (15000, 2000)),
            ((15000, 2000), (0, 2000)),
            ((0, 2000), (0, 0)),
        ):
            blk.add_line(a, b)  # layer 0: takes the layer of the INSERT
        msp.add_blockref("CELL_BOX", (60000, 1000), dxfattribs={"layer": "OFFCELL"})
        _far_value(msp)

    assert _paired(_sheet_with(tmp_path, build)) == []


def test_layer_0_follows_the_chain_of_inserts(tmp_path):
    def build(msp):
        doc = msp.doc
        doc.layers.add("OFFCELL").off()
        inner = doc.blocks.new("INNER_BOX")
        for a, b in (
            ((0, 0), (15000, 0)),
            ((15000, 0), (15000, 2000)),
            ((15000, 2000), (0, 2000)),
            ((0, 2000), (0, 0)),
        ):
            inner.add_line(a, b)
        outer = doc.blocks.new("OUTER_BOX")
        outer.add_blockref("INNER_BOX", (0, 0))  # layer 0 inside layer 0
        msp.add_blockref("OUTER_BOX", (60000, 1000), dxfattribs={"layer": "OFFCELL"})
        _far_value(msp)

    assert _paired(_sheet_with(tmp_path, build)) == []


def test_lines_on_a_layer_without_a_table_row_print(tmp_path):
    def build(msp):
        for a, b in (
            ((60000, 1000), (75000, 1000)),
            ((75000, 1000), (75000, 3000)),
            ((75000, 3000), (60000, 3000)),
            ((60000, 3000), (60000, 1000)),
        ):
            msp.add_line(a, b, dxfattribs={"layer": "NOT_IN_THE_TABLE"})
        _far_value(msp)

    assert _paired(_sheet_with(tmp_path, build)) == [("KC-9", "adjacent_label")]


def test_a_slanted_line_is_no_cell_wall(tmp_path):
    def build(msp):
        msp.add_line((60000, 1000), (75000, 1000))
        msp.add_line((60000, 3000), (75000, 3000))
        msp.add_line((60000, 1000), (60000, 3000))
        msp.add_line((75000, 1000), (75600, 3000))  # leans: not a vertical wall, so no cell
        _far_value(msp)

    assert _paired(_sheet_with(tmp_path, build)) == []


def test_a_wall_that_stops_just_short_of_the_label_row_still_closes_the_cell(tmp_path):
    def build(msp):
        msp.add_line((60000, 1000), (75000, 1000))
        msp.add_line((60000, 3000), (75000, 3000))
        msp.add_line((60000, 1000), (60000, 3000))
        msp.add_line((75000, 1000), (75000, 2600))  # ends 50 below the label's centre line
        _far_value(msp)

    assert _paired(_sheet_with(tmp_path, build)) == [("KC-9", "adjacent_label")]


@pytest.mark.parametrize("kind", ["lwpolyline", "polyline2d"])
def test_a_polyline_outline_is_a_cell(tmp_path, kind):
    pts = [(60000, 1000), (75000, 1000), (75000, 3000), (60000, 3000)]

    def build(msp):
        if kind == "lwpolyline":
            msp.add_lwpolyline(pts, close=True)
        else:
            msp.add_polyline2d(pts, close=True)
        _far_value(msp)

    assert _paired(_sheet_with(tmp_path, build)) == [("KC-9", "adjacent_label")]


def test_a_polyline_with_many_vertices_is_no_cell(tmp_path):
    xs = [60000 + i * 1000 for i in range(16)]  # 15 000 wide, 16 collinear vertices along the bottom
    pts = [(x, 1000) for x in xs] + [(75000, 3000), (60000, 3000)]

    def build(msp):
        msp.add_lwpolyline(pts, close=True)
        _far_value(msp)

    assert _paired(_sheet_with(tmp_path, build)) == []
