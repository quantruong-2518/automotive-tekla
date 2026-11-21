"""sheets + levels: texts that do not print give no value (tool wave 4, package S, V1 consumer side).

The text index is built from a synthetic DXF and then edited: `printed: false` is what `extract-text` writes
for a not-printed entry (visibility.is_printed). An index without the field reads as printed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ezdxf.filemanagement import new

from _dxf_fixtures import build_set
from tekla_harness.extract_text import extract_text
from tekla_harness.levels import extract_levels
from tekla_harness.schemas import validate
from tekla_harness.sheets import extract_sheets


def hide(entry: dict[str, Any], reason: str = "entity_invisible") -> None:
    entry["printed"] = False
    entry["not_printed_reasons"] = [reason]


def find(index: dict[str, Any], text: str, tag: str | None = None) -> dict[str, Any]:
    hits = [e for e in index["entries"] if e["display_text"] == text and (tag is None or e["tag"] == tag)]
    assert len(hits) == 1, (text, len(hits))
    return hits[0]


def sheets_of(path: Path, index: dict[str, Any]) -> dict[str, Any]:
    result = extract_sheets(path, index)
    assert validate("sheets", result) == []
    return result


def levels_of(path: Path, index: dict[str, Any]) -> dict[str, Any]:
    result = extract_levels(path, index, extract_sheets(path, index))
    assert validate("levels", result) == []
    json.dumps(result, allow_nan=False)
    return result


def number(result: dict[str, Any], sid: str) -> str | None:
    s = next(s for s in result["sheets"] if s["sheet_id"] == sid)
    n = s["title_block"]["sheet_number"]
    return n["value"] if n else None


# --- sheets -------------------------------------------------------------------------------------------


def test_a_not_printed_title_attrib_is_no_sheet_number(tmp_path):
    path = build_set(tmp_path)
    index = extract_text(path)
    assert number(sheets_of(path, index), "model#02") == "S-102"  # control: printed
    entry = find(index, "S-102", "SHEET_NO")
    hide(entry)
    result = sheets_of(path, index)
    assert number(result, "model#02") is None
    sheet = next(s for s in result["sheets"] if s["sheet_id"] == "model#02")
    assert all(c["evidence"]["value_text_id"] != entry["id"] for c in sheet["title_block"]["candidates"])
    assert entry["id"] in sheet["text_ids"]  # still assigned: only values are left out
    missing = [q for q in result["questions"] if q["code"] == "sheet_number_missing"]
    assert missing and "model#02" in missing[0]["where"]
    expected = f"1 of {len(index['entries'])} indexed texts are not printed (printed: false)"
    assert any(w.startswith(expected) for w in result["warnings"])


def test_not_printed_title_attrib_on_a_paper_space_sheet(tmp_path):
    path = build_set(tmp_path)
    index = extract_text(path)
    assert number(sheets_of(path, index), "Plot#01") == "S-201"
    hide(find(index, "S-201", "SHEET_NO"), "attribute_invisible")
    assert number(sheets_of(path, index), "Plot#01") is None


def test_a_not_printed_label_pairs_with_nothing(tmp_path):
    doc = new("R2018", setup=True)
    msp = doc.modelspace()
    for x in (0.0, 90000.0):
        msp.add_lwpolyline([(x, 0), (x + 84100, 0), (x + 84100, 59400), (x, 59400)], close=True)
        for i in range(6):
            msp.add_text(f"NOTE {i}", height=350, dxfattribs={"insert": (x + 2000, 6000 + i * 1000)})
        msp.add_text("DRAWING NO.:", height=300, dxfattribs={"insert": (x + 60000, 3000)})
        msp.add_text(f"KC-0{1 if x == 0 else 2}", height=300, dxfattribs={"insert": (x + 64000, 3000)})
    path = tmp_path / "labels.dxf"
    doc.saveas(path)
    index = extract_text(path)
    assert [number(sheets_of(path, index), s) for s in ("model#01", "model#02")] == ["KC-01", "KC-02"]
    hide(find(index, "KC-02"))  # the value
    assert [number(sheets_of(path, index), s) for s in ("model#01", "model#02")] == ["KC-01", None]
    index = extract_text(path)
    hide(
        next(
            e for e in index["entries"] if e["display_text"] == "DRAWING NO.:" and e["position"]["x"] > 100000
        )
    )
    result = sheets_of(path, index)
    kinds = [c["evidence"]["kind"] for c in result["sheets"][1]["title_block"]["candidates"]]
    assert "adjacent_label" not in kinds  # the label does not print: only the corner code can speak
    assert kinds == ["pattern"]


def test_a_not_printed_corner_code_is_not_a_competing_number(tmp_path):
    doc = new("R2018", setup=True)
    msp = doc.modelspace()
    for k, x in enumerate((0.0, 90000.0)):
        msp.add_lwpolyline([(x, 0), (x + 84100, 0), (x + 84100, 59400), (x, 59400)], close=True)
        for i in range(6):
            msp.add_text(f"NOTE {i}", height=350, dxfattribs={"insert": (x + 2000, 6000 + i * 1000)})
        msp.add_text(f"KC-0{k + 1}", height=300, dxfattribs={"insert": (x + 76000, 1500)})
    # a stale second code at the same corner position of sheet 1: a tie that would be a conflict
    msp.add_text("KC-77", height=300, dxfattribs={"insert": (76050, 1500)})
    path = tmp_path / "corner.dxf"
    doc.saveas(path)
    index = extract_text(path)
    result = sheets_of(path, index)
    assert number(result, "model#01") is None
    assert "title_field_conflict" in [q["code"] for q in result["questions"]]
    hide(find(index, "KC-77"))
    result = sheets_of(path, index)
    assert number(result, "model#01") == "KC-01"
    assert "title_field_conflict" not in [q["code"] for q in result["questions"]]


def test_an_index_without_printed_still_lowers_confidence_by_flags(tmp_path):
    path = build_set(tmp_path)
    index = extract_text(path)
    entry = find(index, "S-101", "SHEET_NO")
    entry["flags"] = [*entry["flags"], "attribute_invisible"]  # an index written before `printed` existed
    result = sheets_of(path, index)
    cand = next(
        c
        for c in result["sheets"][0]["title_block"]["candidates"]
        if c["evidence"]["value_text_id"] == entry["id"]
    )
    assert cand["confidence"] == "low"
    assert number(result, "model#01") == "S-101"


def test_a_not_printed_label_is_no_title_evidence_for_a_small_frame(tmp_path):
    # short side 45 text heights: a sheet only with title-block evidence, and the label is not printed
    doc = new("R2018", setup=True)
    msp = doc.modelspace()
    w, h = 21000.0, 14850.0
    msp.add_lwpolyline([(0, 0), (w, 0), (w, h), (0, h)], close=True)
    for i in range(6):
        msp.add_text(f"NOTE {i}", height=330, dxfattribs={"insert": (500, 1000 + i * 700)})
    msp.add_text("DRAWING NO.:", height=330, dxfattribs={"insert": (14000, 500)})
    path = tmp_path / "small.dxf"
    doc.saveas(path)
    index = extract_text(path)
    assert len(sheets_of(path, index)["sheets"]) == 1  # control: the printed label titles the frame
    hide(find(index, "DRAWING NO.:"))
    assert sheets_of(path, index)["sheets"] == []


def test_a_not_printed_copy_outside_the_frames_is_no_mark_evidence(tmp_path):
    doc = new("R2018", setup=True)
    msp = doc.modelspace()
    for k, x in enumerate((0.0, 90000.0)):
        msp.add_lwpolyline([(x, 0), (x + 84100, 0), (x + 84100, 59400), (x, 59400)], close=True)
        for i in range(6):
            msp.add_text(f"NOTE {i}", height=350, dxfattribs={"insert": (x + 2000, 6000 + i * 1000)})
        msp.add_text(f"KC-0{k + 1}", height=300, dxfattribs={"insert": (x + 76000, 1500)})
    for y in (-5000, -6000):  # the same code twice outside every frame: a mark, not a sheet number
        msp.add_text("KC-01", height=300, dxfattribs={"insert": (0, y)})
    path = tmp_path / "outside.dxf"
    doc.saveas(path)
    index = extract_text(path)
    assert number(sheets_of(path, index), "model#01") is None  # control: the code is a mark
    for e in index["entries"]:
        if e["display_text"] == "KC-01" and e["position"]["y"] < 0:
            hide(e)
    assert number(sheets_of(path, index), "model#01") == "KC-01"


# --- levels -------------------------------------------------------------------------------------------


def _level_file(tmp_path: Path) -> Path:
    doc = new("R2018", setup=True)
    msp = doc.modelspace()
    msp.add_text("+0.000", height=250, dxfattribs={"insert": (0, 0)})
    msp.add_text("+3.600", height=250, dxfattribs={"insert": (0, 3000)})
    msp.add_text("CAO ĐỘ +3.850", height=250, dxfattribs={"insert": (0, 6000)})  # the stale one
    msp.add_text("CAO ĐỘ +3.850", height=250, dxfattribs={"insert": (5000, 6000)})
    msp.add_text("TẦNG 5", height=250, dxfattribs={"insert": (0, 10250)})  # a name above a bare value
    msp.add_text("+15.000", height=250, dxfattribs={"insert": (0, 9500)})
    path = tmp_path / "levels.dxf"
    doc.saveas(path)
    return path


def test_not_printed_level_text_is_no_candidate(tmp_path):
    path = _level_file(tmp_path)
    index = extract_text(path)
    base = levels_of(path, index)
    assert {lv["value_text"] for lv in base["levels"]} >= {"+3.850", "+3.600", "+15.000"}
    stale = [e for e in index["entries"] if e["display_text"] == "CAO ĐỘ +3.850"]
    assert len(stale) == 2
    hide(stale[0])
    one = levels_of(path, index)
    (lv,) = [lv for lv in one["levels"] if lv["value_text"] == "+3.850"]
    assert len(lv["candidate_ids"]) == 1  # only the printed one
    hide(stale[1], "layer_off")
    none = levels_of(path, index)
    assert "+3.850" not in [lv["value_text"] for lv in none["levels"]]
    assert none["summary"]["candidates"] == base["summary"]["candidates"] - 2
    assert any(
        w.startswith("2 text(s) are not printed (printed: false) and hold 2 level-shaped value(s)")
        for w in none["warnings"]
    )


def test_the_not_printed_count_is_per_text_and_per_value(tmp_path):
    doc = new("R2018", setup=True)
    msp = doc.modelspace()
    msp.add_text("(FROM -0.250 TO +2.750 AND +5.000)", height=250, dxfattribs={"insert": (0, 0)})  # 3 values
    msp.add_text("+9.000", height=250, dxfattribs={"insert": (0, 3000)})  # 1 value
    msp.add_text("+3.600", height=250, dxfattribs={"insert": (0, 6000)})  # printed
    path = tmp_path / "count.dxf"
    doc.saveas(path)
    index = extract_text(path)
    hide(find(index, "(FROM -0.250 TO +2.750 AND +5.000)"))
    hide(find(index, "+9.000"))
    result = levels_of(path, index)
    assert [lv["value_text"] for lv in result["levels"]] == ["+3.600"]
    assert any(
        w.startswith("2 text(s) are not printed (printed: false) and hold 4 level-shaped value(s)")
        for w in result["warnings"]
    )


def test_a_not_printed_text_names_no_storey(tmp_path):
    path = _level_file(tmp_path)
    index = extract_text(path)

    def names(result: dict[str, Any]) -> list[str]:
        (lv,) = [lv for lv in result["levels"] if lv["value_text"] == "+15.000"]
        return lv["names"]

    assert names(levels_of(path, index)) == ["TẦNG 5"]
    hide(find(index, "TẦNG 5"))
    assert names(levels_of(path, index)) == []


def test_levels_without_printed_keep_the_flag_rule(tmp_path):
    path = _level_file(tmp_path)
    index = extract_text(path)
    entry = find(index, "+3.600")
    entry["flags"] = ["layer_off"]
    result = levels_of(path, index)
    (lv,) = [lv for lv in result["levels"] if lv["value_text"] == "+3.600"]
    assert lv["confidence"] == "low"
