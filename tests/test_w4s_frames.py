"""sheets: a frame drawn as a slightly turned, scaled INSERT; a drawing-list header is no title field.

Wave 4, F6. The corpus repro (a frame INSERT at scale 2.16 turned by 0.002 degrees, so its edges miss the axes
by a few units over 51 000) is not axis-aligned to 1e-6 but is a frame to the eye. The trigger here is the
angle, never the scale: the synthetic frames use other scales and turns.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from ezdxf.filemanagement import new

from _titleblock_fixtures import FH, FW
from tekla_harness.extract_text import extract_text
from tekla_harness.schemas import validate
from tekla_harness.sheets import extract_sheets


def _doc() -> tuple[Any, Any]:
    doc = new("R2018", setup=True)
    doc.header["$INSUNITS"] = 4
    return doc, doc.modelspace()


def _frame_block(doc: Any) -> None:
    blk = doc.blocks.new("SHEET_FRAME")
    w, h = 49000.0, 34650.0
    blk.add_lwpolyline([(0, 0), (w, 0), (w, h), (0, h)], close=True)
    blk.add_lwpolyline([(500, 500), (w - 500, 500), (w - 500, h - 500), (500, h - 500)], close=True)


def _notes(msp: Any, x: float, y: float = 0.0) -> None:
    for i in range(8):
        msp.add_text(f"NOTE {i}", height=350, dxfattribs={"insert": (x + 3000, y + 6000 + i * 1200)})


def _sheets(path: Path) -> list[dict[str, Any]]:
    result = extract_sheets(path, extract_text(path))
    assert validate("sheets", result) == []
    return result["sheets"]


@pytest.mark.parametrize("rotation", [0.002, 0.03, -0.04])
def test_a_scaled_insert_turned_by_a_few_thousandths_of_a_degree_is_a_frame(tmp_path, rotation):
    doc, msp = _doc()
    _frame_block(doc)
    scale = 1.7
    msp.add_blockref(
        "SHEET_FRAME", (0, 0), dxfattribs={"xscale": scale, "yscale": scale, "rotation": rotation}
    )
    _notes(msp, 0.0)
    msp.add_blockref("SHEET_FRAME", (FW + 5000, 0), dxfattribs={"xscale": scale, "yscale": scale})
    _notes(msp, FW + 5000)
    path = tmp_path / "turned.dxf"
    doc.saveas(path)
    sheets = _sheets(path)
    assert len(sheets) == 2
    assert {s["detection"]["method"] for s in sheets} == {"frame_rectangle"}
    box = sheets[0]["bbox"]
    assert box[0] == pytest.approx(0, abs=60) and box[2] == pytest.approx(49000 * scale, abs=60)
    assert box[3] == pytest.approx(34650 * scale, abs=60)
    assert sheets[0]["detection"]["frame_block"] == "SHEET_FRAME"


@pytest.mark.parametrize("rotation", [0.1, 0.5])
def test_a_frame_turned_by_a_tenth_of_a_degree_or_more_is_still_not_a_frame(tmp_path, rotation):
    doc, msp = _doc()
    _frame_block(doc)
    msp.add_blockref("SHEET_FRAME", (0, 0), dxfattribs={"xscale": 1.7, "yscale": 1.7, "rotation": rotation})
    _notes(msp, 0.0)
    msp.add_blockref("SHEET_FRAME", (FW + 5000, 0), dxfattribs={"xscale": 1.7, "yscale": 1.7})
    _notes(msp, FW + 5000)
    path = tmp_path / "half.dxf"
    doc.saveas(path)
    assert len(_sheets(path)) == 1  # rotated frames stay a documented gap


def test_a_plain_rectangle_slightly_off_the_axes_is_a_frame(tmp_path):
    doc, msp = _doc()
    eps = 20.0  # 20 units over 84 100: 0.014 degrees
    msp.add_lwpolyline([(0, 0), (FW, eps), (FW - eps, FH + eps), (-eps, FH)], close=True)
    _notes(msp, 0.0)
    msp.add_lwpolyline([(FW + 5000, 0), (2 * FW + 5000, 0), (2 * FW + 5000, FH), (FW + 5000, FH)], close=True)
    _notes(msp, FW + 5000)
    path = tmp_path / "plain.dxf"
    doc.saveas(path)
    assert len(_sheets(path)) == 2


# --- a drawing-list header is not the sheet's number label -----------------------------------------------


def _list_sheet(tmp_path: Path, rows: list[str], *, number: str = "KC-07") -> dict[str, Any]:
    doc, msp = _doc()
    msp.add_lwpolyline([(0, 0), (FW, 0), (FW, FH), (0, FH)], close=True)
    _notes(msp, 0.0)
    # a drawing list: a header cell and one sheet code per row below it
    msp.add_text("DRAWING NO", height=300, dxfattribs={"insert": (20000.0, 40000.0)})
    for i, code in enumerate(rows):
        msp.add_text(code, height=300, dxfattribs={"insert": (20000.0, 39200.0 - i * 800.0)})
    # the title block, lower right
    msp.add_text("BẢN VẼ SỐ:", height=250, dxfattribs={"insert": (70000.0, 3000.0)})
    msp.add_text(number, height=250, dxfattribs={"insert": (73500.0, 3000.0)})
    path = tmp_path / "list.dxf"
    doc.saveas(path)
    result = extract_sheets(path, extract_text(path))
    assert validate("sheets", result) == []
    return result


def test_a_header_over_a_column_of_sheet_codes_is_a_table_not_a_title_field(tmp_path):
    result = _list_sheet(tmp_path, ["KC-00", "KC-01", "KC-02", "KC-03"])
    (sheet,) = result["sheets"]
    assert sheet["title_block"]["sheet_number"]["value"] == "KC-07"
    assert "title_field_conflict" not in [q["code"] for q in result["questions"]]
    assert [c["value"] for c in sheet["title_block"]["candidates"] if c["field"] == "sheet_number"] == [
        "KC-07"
    ]
    assert any("DRAWING NO" in w and "column" in w for w in result["warnings"])


def _header_and(tmp_path: Path, extra: list[tuple[str, float, float]]) -> dict[str, Any]:
    """'DRAWING NO' over one code (KC-00), the title block saying KC-07, and further texts (text, x, y)."""
    doc, msp = _doc()
    msp.add_lwpolyline([(0, 0), (FW, 0), (FW, FH), (0, FH)], close=True)
    _notes(msp, 0.0)
    msp.add_text("DRAWING NO", height=300, dxfattribs={"insert": (20000.0, 40000.0)})
    msp.add_text("KC-00", height=300, dxfattribs={"insert": (20000.0, 39200.0)})
    for text, x, y in extra:
        msp.add_text(text, height=300, dxfattribs={"insert": (x, y)})
    msp.add_text("BẢN VẼ SỐ:", height=250, dxfattribs={"insert": (70000.0, 3000.0)})
    msp.add_text("KC-07", height=250, dxfattribs={"insert": (73500.0, 3000.0)})
    path = tmp_path / "hdr.dxf"
    doc.saveas(path)
    return extract_sheets(path, extract_text(path))


@pytest.mark.parametrize(
    "extra",
    [
        [("KC-01", 20000.0, 41200.0), ("KC-02", 20000.0, 42000.0), ("KC-03", 20000.0, 42800.0)],  # above
        [
            ("KC-01", 30000.0, 38400.0),
            ("KC-02", 30000.0, 37600.0),
            ("KC-03", 30000.0, 36800.0),
        ],  # other column
        [("A3", 20000.0, 38400.0), ("A3", 20000.0, 37600.0), ("A3", 20000.0, 36800.0)],  # not sheet codes
    ],
    ids=["codes_above", "codes_in_another_column", "rows_are_not_codes"],
)
def test_only_sheet_codes_stacked_below_make_a_table(tmp_path, extra):
    result = _header_and(tmp_path, extra)
    assert "title_field_conflict" in [q["code"] for q in result["questions"]]  # KC-00 is still a candidate
    assert not any("column" in w for w in result["warnings"])


def test_the_column_rule_is_for_sheet_number_labels_only(tmp_path):
    doc, msp = _doc()
    msp.add_lwpolyline([(0, 0), (FW, 0), (FW, FH), (0, FH)], close=True)
    _notes(msp, 0.0)
    msp.add_text("SCALE", height=300, dxfattribs={"insert": (20000.0, 40000.0)})
    for i, code in enumerate(["KC-00", "KC-01", "KC-02", "KC-03"]):
        msp.add_text(code, height=300, dxfattribs={"insert": (20000.0, 39200.0 - i * 800.0)})
    path = tmp_path / "scale.dxf"
    doc.saveas(path)
    result = extract_sheets(path, extract_text(path))
    cands = result["sheets"][0]["title_block"]["candidates"]
    assert [(c["field"], c["value"]) for c in cands] == [("scale", "KC-00")]


def test_a_header_with_only_two_codes_below_is_still_a_candidate(tmp_path):
    result = _list_sheet(tmp_path, ["KC-00", "KC-01"])
    assert "title_field_conflict" in [q["code"] for q in result["questions"]]


def test_a_header_alone_is_not_taken_as_the_sheet_number(tmp_path):
    doc, msp = _doc()
    msp.add_lwpolyline([(0, 0), (FW, 0), (FW, FH), (0, FH)], close=True)
    _notes(msp, 0.0)
    msp.add_text("DRAWING NO", height=300, dxfattribs={"insert": (20000.0, 40000.0)})
    for i, code in enumerate(["KC-00", "KC-01", "KC-02"]):
        msp.add_text(code, height=300, dxfattribs={"insert": (20000.0, 39200.0 - i * 800.0)})
    path = tmp_path / "listonly.dxf"
    doc.saveas(path)
    result = extract_sheets(path, extract_text(path))
    assert result["sheets"][0]["title_block"]["sheet_number"] is None
    assert "sheet_number_missing" in [q["code"] for q in result["questions"]]


# --- the column must be a table: evenly spaced rows directly under the value (review M2) ------------------


def _strip_number(tmp_path: Path, marks: list[tuple[str, float, float, float]]) -> dict[str, Any]:
    """A title-block cell in the right strip (DRAWING NO.: with S-101 to its right) and further texts
    (text, x, y, height)."""
    doc, msp = _doc()
    msp.add_lwpolyline([(0, 0), (FW, 0), (FW, FH), (0, FH)], close=True)
    _notes(msp, 0.0)
    msp.add_text("DRAWING NO.:", height=250, dxfattribs={"insert": (76000.0, 30000.0)})
    msp.add_text("S-101", height=400, dxfattribs={"insert": (79000.0, 30000.0)})
    for text, x, y, h in marks:
        msp.add_text(text, height=h, dxfattribs={"insert": (x, y)})
    path = tmp_path / "strip.dxf"
    doc.saveas(path)
    result = extract_sheets(path, extract_text(path))
    assert validate("sheets", result) == []
    return result


def _is_table(result: dict[str, Any]) -> bool:
    return any("column" in w for w in result["warnings"])


def _rows(first_y: float, pitch: float, heights: tuple[float, ...] = (400.0, 400.0, 400.0)):
    return [(f"C-{i + 1}", 79000.0, first_y - i * pitch, h) for i, h in enumerate(heights)]


def test_ordinary_marks_far_below_a_title_block_number_do_not_drop_it(tmp_path):
    result = _strip_number(tmp_path, [("C-1", 79100.0, 9000.0, 300.0), ("C-2", 79300.0, 4000.0, 300.0)])
    assert result["sheets"][0]["title_block"]["sheet_number"]["value"] == "S-101"
    assert not _is_table(result)
    assert "sheet_number_missing" not in [q["code"] for q in result["questions"]]


@pytest.mark.parametrize(
    ("pitch", "table"),
    [(1000.0, True), (1500.0, True), (1700.0, False), (2400.0, False)],
    ids=["tight", "gap_2.75_heights", "gap_3.25_heights", "wide"],
)
def test_rows_must_follow_each_other_within_three_heights(tmp_path, pitch, table):
    # S-101 (h 400) heads three rows; the gap between consecutive boxes is pitch - 400
    result = _strip_number(tmp_path, _rows(30000.0 - pitch, pitch))
    assert _is_table(result) is table


def test_a_row_of_another_height_breaks_the_column(tmp_path):
    assert not _is_table(_strip_number(tmp_path, _rows(29000.0, 1000.0, (400.0, 700.0, 400.0))))
    assert _is_table(_strip_number(tmp_path, _rows(29000.0, 1000.0, (450.0, 450.0, 450.0))))  # 12 % taller


def test_the_chain_ends_at_a_row_of_another_height_even_when_a_later_row_is_near(tmp_path):
    rows = _rows(29000.0, 700.0, (400.0, 600.0, 400.0))  # row 3 is 2.5 heights below row 1
    assert not _is_table(_strip_number(tmp_path, rows))


def test_the_gap_limit_is_three_heights_of_the_taller_of_two_rows(tmp_path):
    # C-2 (h 450) is 1300 below C-1 (h 400): over 3 x 400, within 3 x 450
    marks = [
        ("C-1", 79000.0, 29000.0, 400.0),
        ("C-2", 79000.0, 27250.0, 450.0),
        ("C-3", 79000.0, 26200.0, 450.0),
    ]
    assert _is_table(_strip_number(tmp_path, marks))


def test_a_text_beside_a_row_is_not_the_next_row(tmp_path):
    marks = [("C-1", 79000.0, 29000.0, 400.0), ("C-2", 79300.0, 29000.0, 400.0)]
    assert not _is_table(_strip_number(tmp_path, marks))


def test_a_row_in_another_column_is_not_a_row(tmp_path):
    # C-2 overlaps the value in x but not C-1; C-3 is back in C-1's column, 4 heights below it
    marks = [
        ("C-1", 79000.0, 29000.0, 400.0),
        ("C-2", 80000.0, 28000.0, 400.0),
        ("C-3", 79000.0, 27000.0, 400.0),
    ]
    assert not _is_table(_strip_number(tmp_path, marks))


def test_a_column_needs_the_first_row_right_under_the_value(tmp_path):
    near = [("C-2", 79000.0, 29000.0, 400.0), ("C-3", 79000.0, 28000.0, 400.0)]
    assert _is_table(_strip_number(tmp_path, near))
    far = [("C-2", 79000.0, 20000.0, 400.0), ("C-3", 79000.0, 19000.0, 400.0)]
    assert not _is_table(_strip_number(tmp_path, far))  # tidy rows, but not under the value
