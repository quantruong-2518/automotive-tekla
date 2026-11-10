"""sheets: segmentation into title-block frames / layouts, text assignment, title-block candidates.

Fixtures are synthetic (tests/_dxf_fixtures.py); no sample drawing text is used.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
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
        # the second sheet's number at the same corner position backs the first (review M3)
        msp.add_text("KC-06", height=250, dxfattribs={"insert": (2 * w + 5000 - 3000, 1000)})

    _, result = run(_frames_only(tmp_path, extra))
    number = sheet(result, "model#01")["title_block"]["sheet_number"]
    assert number["value"] == "KC-05" and number["confidence"] == "low"
    cand = sheet(result, "model#01")["title_block"]["candidates"][0]
    assert cand["evidence"]["kind"] == "pattern"


# --- tool wave 3 a1: the printed number in the title-block corner, in the frame's reading direction -----

# a text placed at (u, v) of a frame in its reading frame: u along the text, v across it, both 0..1
_Spec = tuple[str, float, float, float]  # (text, u, v, height)


def _numbered(
    tmp_path: Path,
    sheets: Sequence[Sequence[_Spec]],
    *,
    rotation: float = 0.0,
    portrait: bool = False,
    loose: Sequence[str] = (),
) -> Path:
    """Landscape frames side by side, each with 6 distinct notes and the given texts, all at `rotation`
    (0 or 270). A 270 frame is a landscape sheet drawn turned clockwise: its reading 'right' is world -y,
    its reading 'up' is world +x. `loose` texts lie below every frame, on no sheet."""
    doc = new("R2018", setup=True)
    msp = doc.modelspace()
    long_side, short_side = 42420.0, 30000.0
    w, h = (short_side, long_side) if portrait else (long_side, short_side)

    def world(x0: float, u: float, v: float) -> tuple[float, float]:
        if rotation == 270.0:
            return (x0 + v * w, (1.0 - u) * h)
        return (x0 + u * w, v * h)

    for k, specs in enumerate(sheets):
        x0 = k * (w + 5000)
        msp.add_lwpolyline([(x0, 0), (x0 + w, 0), (x0 + w, h), (x0, h)], close=True)
        for i in range(6):
            msp.add_text(
                f"NOTE {k}.{i}",
                height=250,
                dxfattribs={"insert": world(x0, 0.1, 0.3 + 0.05 * i), "rotation": rotation},
            )
        for text, u, v, th in specs:
            msp.add_text(text, height=th, dxfattribs={"insert": world(x0, u, v), "rotation": rotation})
    for i, text in enumerate(loose):
        msp.add_text(text, height=250, dxfattribs={"insert": (i * 3000, -20000)})
    path = tmp_path / "numbered.dxf"
    doc.saveas(path)
    return path


def _numbers(result: dict[str, Any]) -> list[str | None]:
    return [(s["title_block"]["sheet_number"] or {}).get("value") for s in result["sheets"]]


def test_a_mark_inside_the_quadrant_but_outside_the_corner_is_no_sheet_number(tmp_path):
    # 286 model#04: a tie-beam mark 59 % across and 44 % up the frame was taken as the sheet number
    _, result = run(_numbered(tmp_path, [[("GD-3", 0.59, 0.44, 110)], [("GD-1", 0.3, 0.6, 110)]]))
    assert _numbers(result) == [None, None]
    assert "sheet_number_missing" in codes(result)


def test_the_tallest_code_in_the_corner_wins_over_small_marks(tmp_path):
    # 285 model#03: the number 'KC- 03' and a tie-beam mark share the lower-right area
    sheets = [
        [("KC- 01", 0.92, 0.05, 350)],
        [("KC- 02", 0.92, 0.05, 350)],
        [("KC- 03", 0.92, 0.05, 350), ("GD-1", 0.80, 0.15, 110)],
    ]
    _, result = run(_numbered(tmp_path, sheets))
    assert _numbers(result) == ["KC- 01", "KC- 02", "KC- 03"]
    cand = sheet(result, "model#03")["title_block"]["candidates"]
    assert [(c["value"], c["evidence"]["kind"], c["confidence"]) for c in cand] == [
        ("KC- 03", "pattern", "low")
    ]


def test_a_position_that_repeats_across_sheets_beats_a_taller_one(tmp_path):
    sheets = [
        [("KC-01", 0.92, 0.05, 300)],
        [("KC-02", 0.92, 0.05, 300), ("A-1", 0.80, 0.05, 500)],  # taller, same height up, 12 % further left
    ]
    _, result = run(_numbered(tmp_path, sheets))
    assert _numbers(result) == ["KC-01", "KC-02"]


def test_two_equal_corner_codes_are_a_conflict_not_a_pick(tmp_path):
    # both positions repeat on the second sheet and both codes are as tall: no pick on either sheet
    sheets = [
        [("KC-01", 0.92, 0.05, 300), ("KC-09", 0.80, 0.12, 300)],
        [("KC-02", 0.92, 0.05, 300), ("KC-08", 0.80, 0.12, 300)],
    ]
    _, result = run(_numbered(tmp_path, sheets))
    assert _numbers(result) == [None, None]
    q = next(q for q in result["questions"] if q["code"] == "title_field_conflict")
    assert q["blocking"] and q["found"] == "KC-01 | KC-09"


def test_a_corner_code_that_is_also_drawn_on_the_sheet_is_a_mark(tmp_path):
    # the only code in the corner is a mark: the same text also labels a member on the plan
    sheets = [[("GD-1", 0.90, 0.05, 300), ("GD-1", 0.4, 0.5, 300)], []]
    _, result = run(_numbered(tmp_path, sheets))
    assert _numbers(result) == [None, None]
    assert any("'GD-1'" in w and "appears 2 times on this sheet" in w for w in result["warnings"])


def test_a_code_listed_once_on_another_sheet_is_still_a_number(tmp_path):
    # a drawing list on sheet 1 names the number of sheet 2 once: it stays a sheet number (270 has one)
    sheets = [[("KC-01", 0.92, 0.05, 300), ("KC-02", 0.5, 0.7, 200)], [("KC-02", 0.92, 0.05, 300)]]
    _, result = run(_numbered(tmp_path, sheets))
    assert _numbers(result) == ["KC-01", "KC-02"]


def test_a_rotated_frame_reads_its_number_in_its_own_corner(tmp_path):
    # 290 model#16-18: portrait frames whose content reads top to bottom (rotation 270); the number sits at
    # the world lower-left, which is the lower-right corner in the frame's reading direction
    sheets = [[("Kc - 13", 0.94, 0.03, 130)], [("Kc - 14", 0.94, 0.03, 130)]]
    _, result = run(_numbered(tmp_path, sheets, rotation=270.0, portrait=True))
    assert _numbers(result) == ["Kc - 13", "Kc - 14"]


def test_among_repeated_positions_the_taller_code_wins(tmp_path):
    sheets = [
        [("KC-07", 0.80, 0.15, 300), ("D-1", 0.92, 0.05, 200)],
        [("KC-08", 0.80, 0.15, 300), ("E-2", 0.92, 0.05, 200)],
    ]
    _, result = run(_numbered(tmp_path, sheets))
    assert _numbers(result) == ["KC-07", "KC-08"]
    assert any("'D-1'" in w and "a taller code" in w for w in result["warnings"])


@pytest.mark.parametrize("height", [500, 300])
def test_a_repeated_position_is_preferred_and_the_loser_is_reported(tmp_path, height):
    sheets = [[("KC-01", 0.92, 0.05, 300)], [("KC-02", 0.92, 0.05, 300), ("A-1", 0.80, 0.15, height)]]
    _, result = run(_numbered(tmp_path, sheets))
    assert _numbers(result) == ["KC-01", "KC-02"]
    assert any("'A-1'" in w and "repeated on other sheets" in w for w in result["warnings"])


def test_two_codes_close_together_on_one_sheet_do_not_back_each_other(tmp_path):
    _, result = run(_numbered(tmp_path, [[("KC-05", 0.92, 0.05, 300), ("D-1", 0.93, 0.06, 200)], []]))
    assert _numbers(result) == [None, None]


@pytest.mark.parametrize(("u", "v", "found"), [(0.70, 0.10, False), (0.80, 0.25, False), (0.78, 0.17, True)])
def test_the_corner_is_a_quarter_along_and_a_fifth_up(tmp_path, u, v, found):
    _, result = run(_numbered(tmp_path, [[("KC-05", u, v, 300)], [("KC-06", u, v, 300)]]))
    assert (_numbers(result)[0] == "KC-05") is found


def test_a_mark_family_on_the_sheet_disqualifies_its_corner_code(tmp_path):
    # 286: gĐ-3 next to gĐ-1 and gĐ-2 on the same plan is a tie-beam mark even when alone in the corner
    sheets = [[("GD-3", 0.92, 0.05, 300), ("GD-1", 0.4, 0.5, 110), ("GD-2", 0.5, 0.5, 110)], []]
    _, result = run(_numbered(tmp_path, sheets))
    assert _numbers(result)[0] is None
    assert any("'GD-3'" in w and "mark family" in w for w in result["warnings"])


def test_a_code_seen_twice_outside_every_title_block_is_a_mark(tmp_path):
    # twice on no sheet at all (a body text on another sheet that equals a corner code is a reference)
    sheets = [[("KC-09", 0.92, 0.05, 300)], [("KC-10", 0.92, 0.05, 300)], [("KC-11", 0.92, 0.05, 300)]]
    _, result = run(_numbered(tmp_path, sheets, loose=["KC-09", "KC-09"]))
    assert _numbers(result) == [None, "KC-10", "KC-11"]
    assert any("'KC-09'" in w and "2 times outside" in w for w in result["warnings"])


# --- review M3: a corner pick needs backing; M4: a code that is another sheet's number is a reference ----


def test_a_corner_code_whose_position_repeats_nowhere_is_not_a_number(tmp_path):
    # the printed numbers S101 / S102 are not code-shaped; a lone mark sits in each corner at its own spot
    sheets = [
        [("S101", 0.95, 0.03, 350), ("C-1", 0.80, 0.12, 250)],
        [("S102", 0.95, 0.03, 350), ("D-4", 0.85, 0.15, 250)],
    ]
    _, result = run(_numbered(tmp_path, sheets))
    assert _numbers(result) == [None, None]
    missing = next(q for q in result["questions"] if q["code"] == "sheet_number_missing")
    assert missing["blocking"] and missing["where"] == "model#01, model#02"
    assert any("'C-1'" in w and "no other sheet's corner" in w for w in result["warnings"])
    assert any("'D-4'" in w and "no other sheet's corner" in w for w in result["warnings"])


def test_a_one_sheet_file_takes_no_corner_code(tmp_path):
    _, result = run(_numbered(tmp_path, [[("KC-05", 0.92, 0.05, 300)]]))
    assert _numbers(result) == [None]
    assert "sheet_number_missing" in codes(result)
    assert any("'KC-05'" in w and "no other sheet's corner" in w for w in result["warnings"])


def test_a_corner_code_backed_only_by_a_mark_at_that_spot_is_not_a_number(tmp_path):
    # the only other code at the same corner position is a mark (twice on its sheet): no backing
    sheets = [[("KC-01", 0.92, 0.05, 300)], [("GD-1", 0.92, 0.05, 300), ("GD-1", 0.4, 0.5, 110)]]
    _, result = run(_numbered(tmp_path, sheets))
    assert _numbers(result) == [None, None]


def test_a_detail_reference_to_another_sheet_is_not_mark_evidence(tmp_path):
    # S-501 is referenced once on each of two sheets and printed in the corner of the third
    sheets = [
        [("S-101", 0.95, 0.03, 350), ("S-501", 0.4, 0.5, 200)],
        [("S-102", 0.95, 0.03, 350), ("S-501", 0.5, 0.5, 200)],
        [("S-501", 0.95, 0.03, 350)],
    ]
    _, result = run(_numbered(tmp_path, sheets))
    assert _numbers(result) == ["S-101", "S-102", "S-501"]
    assert "sheet_number_missing" not in codes(result)


def test_references_to_sibling_sheets_are_no_mark_family(tmp_path):
    sheets = [
        [("S-101", 0.95, 0.03, 350), ("S-201", 0.4, 0.5, 200), ("S-202", 0.5, 0.5, 200)],
        [("S-201", 0.95, 0.03, 350)],
        [("S-202", 0.95, 0.03, 350)],
    ]
    _, result = run(_numbered(tmp_path, sheets))
    assert _numbers(result) == ["S-101", "S-201", "S-202"]


def test_an_index_sheet_listing_the_series_keeps_its_own_number(tmp_path):
    listing = [("S-101", 0.3, 0.7, 200), ("S-102", 0.3, 0.65, 200), ("S-103", 0.3, 0.6, 200)]
    sheets = [
        [("S-001", 0.95, 0.03, 350), *listing],
        [("S-101", 0.95, 0.03, 350)],
        [("S-102", 0.95, 0.03, 350)],
        [("S-103", 0.95, 0.03, 350)],
    ]
    _, result = run(_numbered(tmp_path, sheets))
    assert _numbers(result) == ["S-001", "S-101", "S-102", "S-103"]


def test_references_to_sheets_outside_the_file_still_read_as_a_family_and_are_asked(tmp_path):
    # documented limit: S-201 / S-202 are no sheet of this file, so they still count as a mark family;
    # the sheet then has no number and is asked, never given a wrong one
    sheets = [
        [("S-101", 0.95, 0.03, 350), ("S-201", 0.4, 0.5, 200), ("S-202", 0.5, 0.5, 200)],
        [("S-102", 0.95, 0.03, 350)],
        [("S-103", 0.95, 0.03, 350)],
    ]
    _, result = run(_numbered(tmp_path, sheets))
    assert _numbers(result) == [None, "S-102", "S-103"]
    assert next(q for q in result["questions"] if q["code"] == "sheet_number_missing")["where"] == "model#01"


def test_a_code_backed_only_by_a_rejected_mark_is_not_a_number(tmp_path):
    # backing comes from corner codes that are not marks: S-101 is taken for a mark family, so S-102 has
    # nothing at its position and is asked as well
    sheets = [
        [("S-101", 0.95, 0.03, 350), ("S-201", 0.4, 0.5, 200), ("S-202", 0.5, 0.5, 200)],
        [("S-102", 0.95, 0.03, 350)],
    ]
    _, result = run(_numbered(tmp_path, sheets))
    assert _numbers(result) == [None, None]
    missing = next(q for q in result["questions"] if q["code"] == "sheet_number_missing")
    assert missing["where"] == "model#01, model#02"


def test_referable_sheets_are_judged_once_with_every_body_text_counted(tmp_path):
    # documented limit: S-101 references S-201 and S-202, so before references are known it looks like a
    # mark family and is not referable; the two S-101 references then count as marks and S-101 is asked.
    # One pass keeps the result independent of sheet order and never lets marks referable through a cascade.
    sheets = [
        [("S-201", 0.95, 0.03, 350)],
        [("S-202", 0.95, 0.03, 350)],
        [("S-101", 0.95, 0.03, 350), ("S-201", 0.4, 0.5, 200), ("S-202", 0.5, 0.5, 200)],
        [("S-102", 0.95, 0.03, 350), ("S-101", 0.4, 0.5, 200)],
        [("S-103", 0.95, 0.03, 350), ("S-101", 0.4, 0.5, 200)],
    ]
    _, result = run(_numbered(tmp_path, sheets))
    assert _numbers(result) == ["S-201", "S-202", None, "S-102", "S-103"]
    assert any("'S-101'" in w and "2 times outside" in w for w in result["warnings"])


def test_a_corner_code_drawn_twice_on_its_sheet_is_no_sheet_to_reference(tmp_path):
    # GD-1 is a mark on sheet 1 (twice there), so GD-1 on sheet 2 is mark evidence, not a reference
    sheets = [
        [("GD-1", 0.92, 0.05, 300), ("GD-1", 0.4, 0.5, 110)],
        [("GD-3", 0.92, 0.05, 300), ("GD-1", 0.4, 0.5, 110), ("GD-2", 0.5, 0.5, 110)],
        [("KC-03", 0.92, 0.05, 300)],
        [("KC-04", 0.92, 0.05, 300)],
    ]
    _, result = run(_numbered(tmp_path, sheets))
    assert _numbers(result) == [None, None, "KC-03", "KC-04"]
    assert any("'GD-3'" in w and "mark family" in w for w in result["warnings"])


def test_a_corner_mark_of_another_sheet_does_not_hide_a_mark_family(tmp_path):
    # 286: gĐ-3 next to gĐ-1 and gĐ-2 is a mark; gĐ-1 also sits in another sheet's corner, where it is a
    # mark of its own family (gĐ-5, gĐ-6), so it is no sheet that the plan could reference
    sheets = [
        [
            ("GD-3", 0.92, 0.05, 300),
            ("GD-1", 0.4, 0.5, 110),
            ("GD-2", 0.5, 0.5, 110),
            ("KC-01", 0.95, 0.03, 350),
        ],
        [
            ("GD-1", 0.92, 0.05, 300),
            ("GD-5", 0.4, 0.5, 110),
            ("GD-6", 0.5, 0.5, 110),
            ("KC-02", 0.95, 0.03, 350),
        ],
    ]
    _, result = run(_numbered(tmp_path, sheets))
    assert _numbers(result) == ["KC-01", "KC-02"]
    assert any("'GD-3'" in w and "mark family" in w for w in result["warnings"])


def test_model_marks_shown_on_a_layout_sheet_are_never_its_number(tmp_path):
    # Steel_01: a layout sheet without a frame shows model text through a viewport; those texts have model
    # coordinates, far outside the layout's own box, and must not land in its 'corner'
    doc = new("R2018", setup=True)
    msp = doc.modelspace()
    for i, mark in enumerate(["AB-20", "C-01", "TB-01"]):
        msp.add_text(mark, height=250, dxfattribs={"insert": (100000 + 2000 * i, -50000)})
    plot = doc.layouts.new("Plot")
    for i in range(3):
        plot.add_text(f"NOTE {i}", height=3.5, dxfattribs={"insert": (20, 20 + 10 * i)})
    plot.add_viewport(
        center=(200, 150), size=(300, 200), view_center_point=(102000, -50000), view_height=8000
    )
    path = tmp_path / "layout.dxf"
    doc.saveas(path)
    _, result = run(path)
    (only,) = result["sheets"]
    assert only["detection"]["method"] == "layout" and len(only["text_ids"]) == 6
    assert only["title_block"]["candidates"] == []
    assert "title_field_conflict" not in codes(result)


def test_a_portrait_frame_also_reads_upright_numbers(tmp_path):
    sheets = [[("KC-03", 0.92, 0.05, 300)], [("KC-04", 0.92, 0.05, 300)]]
    _, result = run(_numbered(tmp_path, sheets, portrait=True))
    assert _numbers(result) == ["KC-03", "KC-04"]


def test_a_rotated_code_in_a_horizontal_frame_is_not_a_number(tmp_path):
    def extra(msp, w, h):
        # read at 90 degrees this is its own lower-right corner (world upper right); a landscape frame is
        # read at 0 degrees only. The same spot on the second frame would back it if it counted.
        for k, code in enumerate(("KC-05", "KC-06")):
            x = k * (w + 5000) + 0.95 * w
            msp.add_text(code, height=250, dxfattribs={"insert": (x, 0.85 * h), "rotation": 90})

    _, result = run(_frames_only(tmp_path, extra))
    assert sheet(result, "model#01")["title_block"]["sheet_number"] is None


# --- tool wave 3: gaps in a file's printed sheet numbers (sheet_number_gap, not blocking) ---------------


def _corner(*numbers: str) -> list[list[_Spec]]:
    return [[(n, 0.92, 0.05, 300)] if n else [] for n in numbers]


def _gap(result: dict[str, Any]) -> dict[str, Any] | None:
    gaps = [q for q in result["questions"] if q["code"] == "sheet_number_gap"]
    assert len(gaps) <= 1  # one question per file
    return gaps[0] if gaps else None


def test_a_missing_number_in_the_sequence_is_asked(tmp_path):
    _, result = run(_numbered(tmp_path, _corner("KC-23", "KC-24", "KC-26", "KC-27")))
    q = _gap(result)
    assert q is not None and not q["blocking"]
    assert q["where"] == "model#02, model#03"
    assert q["found"] == "missing 25 (between KC-24 on model#02 and KC-26 on model#03)"


def test_a_run_of_missing_numbers_is_one_range_and_duplicates_name_every_sheet(tmp_path):
    _, result = run(_numbered(tmp_path, _corner("S-01", "S-01", "S-05", "S-06")))
    q = _gap(result)
    assert q is not None
    assert q["found"] == "missing 2-4 (between S-01 on model#01, model#02 and S-05 on model#03)"
    assert q["where"] == "model#01, model#02, model#03"


def test_several_gaps_and_sheets_without_a_number_are_listed(tmp_path):
    _, result = run(_numbered(tmp_path, _corner("KC-01", "KC-03", "", "KC-05")))
    q = _gap(result)
    assert q is not None
    assert q["found"] == (
        "missing 2 (between KC-01 on model#01 and KC-03 on model#02); "
        "missing 4 (between KC-03 on model#02 and KC-05 on model#04); "
        "1 sheet(s) without a detected number: model#03"
    )
    assert q["where"] == "model#01, model#02, model#04"


def test_a_number_taken_by_another_prefix_fills_the_gap(tmp_path):
    # 290: one counter runs over Kc and KT sheets (Kc - 13, KT - 14, Kc - 15)
    _, result = run(_numbered(tmp_path, _corner("Kc - 13", "KT - 14", "Kc - 15")))
    assert _gap(result) is None


def test_no_gap_question_for_a_complete_sequence_or_a_single_number(tmp_path):
    _, result = run(_numbered(tmp_path, _corner("KC-01", "KC-02", "KC-03")))
    assert _gap(result) is None
    _, result = run(_numbered(tmp_path, _corner("KC-07", "")))
    assert _gap(result) is None


def test_sheet_x_of_y_and_letter_suffixes_count_by_their_number(tmp_path):
    _, result = run(_numbered(tmp_path, _corner("KT 1/18", "KT 2/18", "KT-04A")))
    q = _gap(result)
    assert q is not None and q["found"] == "missing 3 (between KT 2/18 on model#02 and KT-04A on model#03)"


def test_numbers_that_are_not_codes_are_left_out_of_the_gap_check(tmp_path):
    def extra(msp, w, h):
        msp.add_text("SHEET NO: GENERAL", height=250, dxfattribs={"insert": (w - 8000, 1000)})

    _, result = run(_frames_only(tmp_path, extra))
    assert _gap(result) is None


# review minor: a run of more than SHEET_GAP_MAX_RUN missing numbers is a numbering jump, not a gap


def _jumps(result: dict[str, Any]) -> list[str]:
    return [w for w in result["warnings"] if "numbering jump" in w]


def test_hundreds_numbering_is_a_jump_not_a_gap(tmp_path):
    _, result = run(_numbered(tmp_path, _corner("S-101", "S-201", "S-301")))
    assert _gap(result) is None
    assert _jumps(result) == [
        "Sheet numbers jump from S-101 (model#01) to S-201 (model#02): 99 numbers skipped, taken as a "
        "numbering jump (more than 9), not asked as a gap.",
        "Sheet numbers jump from S-201 (model#02) to S-301 (model#03): 99 numbers skipped, taken as a "
        "numbering jump (more than 9), not asked as a gap.",
    ]


def test_a_small_gap_is_asked_next_to_a_numbering_jump(tmp_path):
    _, result = run(_numbered(tmp_path, _corner("S-101", "S-102", "S-201", "S-202", "S-204")))
    q = _gap(result)
    assert q is not None and q["found"] == "missing 203 (between S-202 on model#04 and S-204 on model#05)"
    assert q["where"] == "model#04, model#05"
    assert len(_jumps(result)) == 1 and "from S-102 (model#02) to S-201 (model#03)" in _jumps(result)[0]


@pytest.mark.parametrize(("last", "asked"), [("KC-11", True), ("KC-12", False)])
def test_nine_missing_numbers_are_still_a_gap_ten_are_a_jump(tmp_path, last, asked):
    _, result = run(_numbered(tmp_path, _corner("KC-01", last)))
    assert (_gap(result) is not None) is asked
    assert bool(_jumps(result)) is not asked


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
