"""sheets: segmentation into title-block frames / layouts, text assignment, title-block candidates.

Fixtures are synthetic (tests/_dxf_fixtures.py); no sample drawing text is used.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from ezdxf.filemanagement import new, readfile

from _dxf_fixtures import FRAME_H, FRAME_W, build_set
from tekla_harness.extract_text import extract_text
from tekla_harness.schemas import validate
from tekla_harness.sheets import SheetLocator, extract_sheets


def run(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    index = extract_text(path)
    result = extract_sheets(path, index)
    assert validate("sheets", result) == [], validate("sheets", result)
    json.dumps(result, allow_nan=False)
    return index, result


def codes(result: dict[str, Any]) -> list[str]:
    return [q["code"] for q in result["questions"]]


def sheet(result: dict[str, Any], sid: str) -> dict[str, Any]:
    return next(s for s in result["sheets"] if s["sheet_id"] == sid)


@pytest.fixture
def drawing_set(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    return run(build_set(tmp_path))


def test_two_model_frames_and_one_layout_sheet(drawing_set):
    _, result = drawing_set
    assert [s["sheet_id"] for s in result["sheets"]] == ["model#01", "model#02", "Plot#01"]
    s1 = sheet(result, "model#01")
    # the frame block's geometry sits far from its base point: the world box must still be right
    assert s1["bbox"] == [0.0, 0.0, FRAME_W, FRAME_H]
    assert s1["detection"]["method"] == "frame_rectangle"
    assert s1["detection"]["confidence"] == "medium"  # two frames of the same size
    assert s1["detection"]["inner_frames"] == 1  # the inner border is merged, not a sheet
    assert s1["detection"]["frame_block"] == "TB_FRAME"
    assert sheet(result, "Plot#01")["detection"]["method"] == "layout"
    assert result["summary"]["by_method"] == {"frame_rectangle": 2, "layout": 1}


def test_title_block_fields_from_attrib_tags(drawing_set):
    _, result = drawing_set
    numbers = {s["sheet_id"]: s["title_block"]["sheet_number"]["value"] for s in result["sheets"]}
    revisions = {s["sheet_id"]: s["title_block"]["revision"]["value"] for s in result["sheets"]}
    assert numbers == {"model#01": "S-101", "model#02": "S-102", "Plot#01": "S-201"}
    assert revisions == {"model#01": "A", "model#02": "A", "Plot#01": "B"}
    number = sheet(result, "model#01")["title_block"]["sheet_number"]
    assert number["confidence"] == "medium"
    assert number["provenance"]["sheet"] == "model#01"
    cand = next(
        c for c in sheet(result, "model#01")["title_block"]["candidates"] if c["field"] == "sheet_number"
    )
    assert cand["evidence"]["kind"] == "attrib_tag"
    assert cand["evidence"]["key"] == "SHEET_NO"
    assert "sheet_number_missing" not in codes(result)


def test_template_text_of_the_frame_block_is_never_a_value(drawing_set):
    _, result = drawing_set
    cands = sheet(result, "model#01")["title_block"]["candidates"]
    assert all(c["value"] != "TEMPLATE-ONLY" for c in cands)
    assert not [c for c in cands if c["field"] == "date"]
    scale = [c for c in cands if c["field"] == "scale"]
    assert [(c["value"], c["evidence"]["kind"], c["confidence"]) for c in scale] == [
        ("1:100", "adjacent_label", "low")
    ]


def test_every_text_is_assigned_and_viewports_map_model_space(drawing_set):
    index, result = drawing_set
    assert result["summary"]["assigned"] == result["summary"]["text_entries"] == len(index["entries"])
    assert result["unassigned"] == {"text_ids": [], "ambiguous_text_ids": []}
    note = next(e for e in index["entries"] if e["display_text"] == "GENERAL NOTE")
    plot = sheet(result, "Plot#01")
    assert note["id"] in plot["text_ids"]
    assert len(plot["model_windows"]) == 1
    loc = SheetLocator(result)
    assert loc.locate("model", 300000, 1000) == "Plot#01"
    assert loc.locate("model", 10, 10) == "model#01"
    assert loc.locate("model", -5e6, 0) == "unknown"


def test_overview_viewport_over_several_frames_keeps_them(tmp_path):
    path = build_set(tmp_path)
    doc = readfile(path)
    overview = doc.layouts.new("Overview")
    overview.add_viewport(
        center=(200, 150), size=(400, 150), view_center_point=(87050, 29700), view_height=60000
    )
    doc.saveas(path)
    _, result = run(path)
    assert [s["sheet_id"] for s in result["sheets"]] == ["model#01", "model#02", "Plot#01"]
    assert any("Overview" in w for w in result["warnings"])  # shows only framed content: not a sheet


def test_duplicate_sheet_number_is_a_blocking_question(tmp_path):
    _, result = run(build_set(tmp_path, sheet2_number="S-101"))
    dup = [q for q in result["questions"] if q["code"] == "sheet_number_duplicate"]
    assert len(dup) == 1 and dup[0]["blocking"]
    assert dup[0]["where"] == "model#01, model#02"


def _frames_only(tmp_path: Path, extra=None, ratio: float = FRAME_W / FRAME_H) -> Path:
    doc = new("R2018", setup=True)
    msp = doc.modelspace()
    h = 30000.0
    w = h * ratio
    for k in range(2):
        x = k * (w + 5000)
        msp.add_lwpolyline([(x, 0), (x + w, 0), (x + w, h), (x, h)], close=True)
        for i in range(6):
            msp.add_text(f"NOTE {i}", height=250, dxfattribs={"insert": (x + 2000, 2000 + i * 1000)})
    if extra:
        extra(msp, w, h)
    path = tmp_path / "frames.dxf"
    doc.saveas(path)
    return path


def test_missing_number_and_revision_are_questions(tmp_path):
    _, result = run(_frames_only(tmp_path))
    assert len(result["sheets"]) == 2
    missing = next(q for q in result["questions"] if q["code"] == "sheet_number_missing")
    assert missing["blocking"] and missing["where"] == "model#01, model#02"
    rev = next(q for q in result["questions"] if q["code"] == "revision_missing")
    assert not rev["blocking"]  # asked once per set


def test_sheet_code_pattern_in_lower_right_quadrant_is_low(tmp_path):
    def extra(msp, w, h):
        msp.add_text("KC-05", height=250, dxfattribs={"insert": (w - 3000, 1000)})

    _, result = run(_frames_only(tmp_path, extra))
    number = sheet(result, "model#01")["title_block"]["sheet_number"]
    assert number["value"] == "KC-05" and number["confidence"] == "low"
    cand = sheet(result, "model#01")["title_block"]["candidates"][0]
    assert cand["evidence"]["kind"] == "pattern"


def test_inline_label_is_medium(tmp_path):
    def extra(msp, w, h):
        msp.add_text("SHEET NO: S-301", height=250, dxfattribs={"insert": (w - 8000, 1000)})

    _, result = run(_frames_only(tmp_path, extra))
    number = sheet(result, "model#01")["title_block"]["sheet_number"]
    assert number["value"] == "S-301" and number["confidence"] == "medium"


def test_conflicting_title_values_are_not_chosen(tmp_path):
    def extra(msp, w, h):
        msp.add_text("SHEET NO: S-301", height=250, dxfattribs={"insert": (w - 8000, 1000)})
        msp.add_text("DWG NO: S-399", height=250, dxfattribs={"insert": (w - 8000, 2000)})

    _, result = run(_frames_only(tmp_path, extra))
    assert sheet(result, "model#01")["title_block"]["sheet_number"] is None
    q = next(q for q in result["questions"] if q["code"] == "title_field_conflict")
    assert q["found"] == "S-301 | S-399" and q["sheet"] == "model#01"


def test_non_sheet_shaped_rectangles_are_rejected(tmp_path):
    _, result = run(_frames_only(tmp_path, ratio=3.0))
    assert result["sheets"] == []
    assert result["summary"]["frame_candidates_rejected"] == 2
    assert {"sheets_not_detected", "sheet_frame_candidates_rejected"} <= set(codes(result))
    assert len(result["unassigned"]["text_ids"]) == result["summary"]["text_entries"]


def _container(msp, w, h):
    total = 2 * w + 5000
    msp.add_lwpolyline(
        [(-1000, -1000), (total + 1000, -1000), (total + 1000, 0.7 * total), (-1000, 0.7 * total)],
        close=True,
    )


def test_container_rectangle_around_sheets_is_not_a_sheet(tmp_path):
    def extra(msp, w, h):
        _container(msp, w, h)
        for x in (0.0, w + 5000):  # each inner frame has its own title block
            msp.add_text("SHEET NO.", height=250, dxfattribs={"insert": (x + w - 8000, 1000)})

    _, result = run(_frames_only(tmp_path, extra))
    assert [s["sheet_id"] for s in result["sheets"]] == ["model#01", "model#02"]
    assert any("container" in w for w in result["warnings"])
    assert "sheet_frame_ambiguous" not in codes(result)


def test_rectangles_without_title_blocks_inside_a_frame_are_ambiguous(tmp_path):
    _, result = run(_frames_only(tmp_path, _container))  # no title block anywhere: sheets or boxed views?
    assert len(result["sheets"]) == 1 and result["sheets"][0]["detection"]["inner_frames"] == 2
    q = next(q for q in result["questions"] if q["code"] == "sheet_frame_ambiguous")
    assert q["blocking"] and "2 inner" in q["found"]


def test_two_boxed_views_on_one_sheet(tmp_path):
    doc = new("R2018", setup=True)
    msp = doc.modelspace()

    def rect(x0, y0, x1, y1):
        msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True)

    rect(0, 0, FRAME_W, FRAME_H)
    for x0 in (2000.0, 42000.0):
        rect(x0, 15000, x0 + 38000, 42000)  # two boxed plan views, about 20 % of the sheet each
        for i in range(6):
            msp.add_text(f"P{i}", height=350, dxfattribs={"insert": (x0 + 500, 15500 + i * 1000)})
    msp.add_text("SHEET NO.", height=350, dxfattribs={"insert": (70000, 3000)})
    msp.add_text("KC-01", height=350, dxfattribs={"insert": (74000, 3000)})
    path = tmp_path / "views.dxf"
    doc.saveas(path)
    _, result = run(path)
    assert [s["bbox"] for s in result["sheets"]] == [[0.0, 0.0, FRAME_W, FRAME_H]]
    assert result["sheets"][0]["title_block"]["sheet_number"]["value"] == "KC-01"
    q = next(q for q in result["questions"] if q["code"] == "sheet_frame_ambiguous")  # not a container
    assert q["blocking"] and "2 inner" in q["found"]


def test_a_schedule_table_is_not_a_sheet(tmp_path):
    doc = new("R2018", setup=True)
    msp = doc.modelspace()
    for x0 in (0.0, 10000.0):  # 3000 x 2000 outlines with 50-high rows: 40 text heights, no title block
        msp.add_lwpolyline([(x0, 0), (x0 + 3000, 0), (x0 + 3000, 2000), (x0, 2000)], close=True)
        for i in range(6):
            msp.add_text(f"ROW {i}", height=50, dxfattribs={"insert": (x0 + 100, 100 + i * 300)})
    path = tmp_path / "table.dxf"
    doc.saveas(path)
    _, result = run(path)
    assert result["sheets"] == []
    assert "sheets_not_detected" in codes(result)


def _attrib_title(tmp_path: Path, loose: str | None, callout: bool = False) -> Path:
    doc = new("R2018", setup=True)
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (FRAME_W, 0), (FRAME_W, FRAME_H), (0, FRAME_H)], close=True)
    for i in range(6):
        msp.add_text(f"NOTE {i}", height=350, dxfattribs={"insert": (10000, 10000 + i * 1000)})
    if loose is None:
        tb = doc.blocks.new("TB")
        tb.add_text("SHEET NO.", height=350, dxfattribs={"insert": (70000, 3000)})
        tb.add_attdef("SHEET_NO", (74000, 3000), dxfattribs={"height": 350})
        msp.add_blockref("TB", (0, 0)).add_auto_attribs({"SHEET_NO": "KC-00"})  # template default left in
        msp.add_text("SHEET NO.", height=350, dxfattribs={"insert": (70000, 6000)})
        msp.add_text("KC-05", height=350, dxfattribs={"insert": (74000, 6000)})  # what the drafter typed
    else:
        msp.add_text("SHEET NO.", height=350, dxfattribs={"insert": (70000, 3000)})
        msp.add_text(loose, height=350, dxfattribs={"insert": (74000, 3000)})
    if callout:
        blk = doc.blocks.new("SECTION_CALLOUT")
        blk.add_circle((0, 0), 800)
        blk.add_attdef("SECTION_NO", (0, 200), dxfattribs={"height": 350})
        blk.add_attdef("SHEET_NO", (0, -500), dxfattribs={"height": 350})
        for x in (20000, 50000):
            ref = msp.add_blockref("SECTION_CALLOUT", (x, 30000))
            ref.add_auto_attribs({"SECTION_NO": "1", "SHEET_NO": "S-301"})
    path = tmp_path / "title.dxf"
    doc.saveas(path)
    return path


def test_a_lower_confidence_candidate_that_disagrees_is_a_conflict(tmp_path):
    _, result = run(_attrib_title(tmp_path, None))
    s = result["sheets"][0]
    values = sorted((c["value"], c["evidence"]["kind"]) for c in s["title_block"]["candidates"])
    assert values == [("KC-00", "attrib_tag"), ("KC-05", "adjacent_label")]
    assert s["title_block"]["sheet_number"] is None
    q = next(q for q in result["questions"] if q["code"] == "title_field_conflict")
    assert q["blocking"] and q["found"] == "KC-00 | KC-05"
    assert "sheet_number_missing" not in codes(result)  # asked once, as the conflict


def test_a_callout_sheet_number_attribute_is_not_a_title_block_value(tmp_path):
    _, result = run(_attrib_title(tmp_path, "S-101", callout=True))
    s = result["sheets"][0]
    assert [(c["value"], c["evidence"]["kind"]) for c in s["title_block"]["candidates"]] == [
        ("S-101", "adjacent_label")
    ]
    assert s["title_block"]["sheet_number"]["value"] == "S-101"


def test_identical_sheets_are_flagged(tmp_path):
    _, result = run(_frames_only(tmp_path))
    dup = next(q for q in result["questions"] if q["code"] == "sheet_content_duplicate")
    assert dup["blocking"] and dup["where"] == "model#01, model#02"
    assert [s["duplicate_of"] for s in result["sheets"]] == [None, "model#01"]


def test_index_of_another_file_is_rejected(tmp_path):
    a = build_set(tmp_path, "a.dxf")
    b = _frames_only(tmp_path)
    with pytest.raises(ValueError, match="sha256"):
        extract_sheets(a, extract_text(b))


def test_output_is_deterministic(tmp_path):
    path = build_set(tmp_path)
    index = extract_text(path)
    assert json.dumps(extract_sheets(path, index)) == json.dumps(extract_sheets(path, index))


def test_example_is_valid(example):
    assert validate("sheets", example("sheets")) == []
