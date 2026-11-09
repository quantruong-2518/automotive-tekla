"""levels: level candidates in metres as written, grouping, storey heights and questions.

Fixtures are synthetic (tests/_dxf_fixtures.py); no sample drawing text is used.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from ezdxf.filemanagement import new

from _dxf_fixtures import build_set
from tekla_harness import levels as mod
from tekla_harness.extract_text import extract_text
from tekla_harness.levels import extract_levels
from tekla_harness.schemas import validate
from tekla_harness.sheets import extract_sheets


def run(path: Path) -> dict[str, Any]:
    index = extract_text(path)
    result = extract_levels(path, index, extract_sheets(path, index))
    assert validate("levels", result) == [], validate("levels", result)
    json.dumps(result, allow_nan=False)
    return result


def codes(result: dict[str, Any]) -> list[str]:
    return [q["code"] for q in result["questions"]]


@pytest.fixture(scope="module")
def level_set(tmp_path_factory) -> dict[str, Any]:
    return run(build_set(tmp_path_factory.mktemp("levels")))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("+3.600", [("3.600", "bare", None, None)]),
        ("-1.200", [("-1.200", "bare", None, None)]),
        ("±0.000", [("0.000", "bare", None, None)]),
        ("\N{MINUS SIGN}1.200", [("-1.200", "bare", None, None)]),
        ("EL. +3.600", [("3.600", "prefixed", "EL.", None)]),
        ("CỐT +3.600", [("3.600", "prefixed", "CỐT", None)]),
        ("EL+3.600", [("3.600", "prefixed", "EL", None)]),
        ("TẦNG 2: +3.600", [("3.600", "labelled", None, "TẦNG 2")]),
        ("ROOF EL.+9.45", [("9.45", "labelled", "EL.", "ROOF")]),
        ("(FROM -0.250 TO +2.750)", [("-0.250", "embedded", None, None), ("2.750", "embedded", None, None)]),
        ("+3.600mm", []),
        ("3.600", []),
        ("A-1.200", []),
        ("4%%c16", []),
        # review regressions
        ("+-0.000", [("0.000", "bare", None, None)]),
        ("+/-0.000", [("0.000", "bare", None, None)]),
        ("+3.600 mm", []),
        ("i=-2.5%", []),
        ("TẦNG 2 - 3.600", []),  # a dash between the name and an unsigned number
        ("MÁI - 12.600", []),
        ("- 3.600", [("-3.600", "bare", None, None)]),  # a spaced sign at the start of the line
        ("EL. - 3.600", [("-3.600", "prefixed", "EL.", None)]),
        ("SÂN +0.150", [("0.150", "embedded", None, None)]),  # sân (yard) is not sàn (floor)
        ("TĂNG CƯỜNG -0.200", [("-0.200", "embedded", None, None)]),  # tăng cường: strengthening
        ("tầng hầm -3.000", [("-3.000", "labelled", None, "tầng hầm")]),
        # a storey name needs a number or a storey word of its own (tool wave 3 a2): a bare sàn (slab) is not
        ("SÀN +3.600", [("3.600", "embedded", None, None)]),
        ("MẶT BẰNG THÉP SÀN +3.900", [("3.900", "embedded", None, None)]),
        ("KHỐI LƯỢNG THÉP SÀN +3.900", [("3.900", "embedded", None, None)]),
        ("FLOOR +3.600", [("3.600", "embedded", None, None)]),
        ("SÀN TẦNG 3 +7.200", [("7.200", "labelled", None, "SÀN TẦNG 3")]),
        ("MẶT BẰNG SÀN TẦNG 2 +3.600", [("3.600", "labelled", None, "MẶT BẰNG SÀN TẦNG 2")]),
        ("TẦNG HAI +3.600", [("3.600", "labelled", None, "TẦNG HAI")]),
        ("LẦU 1 +3.600", [("3.600", "labelled", None, "LẦU 1")]),
        ("SÀN MÁI +12.600", [("12.600", "labelled", None, "SÀN MÁI")]),
        ("TUM +15.600", [("15.600", "labelled", None, "TUM")]),
        ("2ND FLOOR +3.600", [("3.600", "labelled", None, "2ND FLOOR")]),
        ("LEVEL 2 +3.600", [("3.600", "labelled", None, "LEVEL 2")]),
        ("TẦNG +3.600", [("3.600", "embedded", None, None)]),
        ("TẦNG TRỆT ±0.000", [("0.000", "labelled", None, "TẦNG TRỆT")]),
        # 290: digits of another value in the title are no storey number
        (
            "MẶT BẰNG THÉP SÀN CAO ĐỘ +7.300 VÀ +10.500",
            [("7.300", "embedded", None, None), ("10.500", "embedded", None, None)],
        ),
    ],
)
def test_parse(text, expected):
    got = [(str(v), form, prefix, name) for _m, v, _f, form, prefix, name in mod._parse(text)]
    assert got == expected


def test_comma_decimal_is_flagged():
    ((_m, value, flags, form, _p, _n),) = mod._parse("+3,60")
    assert str(value) == "3.60" and flags == ["comma_decimal"] and form == "bare"


def test_values_grouped_in_metres_as_written(level_set):
    assert [lv["value_text"] for lv in level_set["levels"]] == ["±0.000", "+3.600", "+3.650", "+7.200"]
    assert [lv["value"] for lv in level_set["levels"]] == [0.0, 3.6, 3.65, 7.2]
    seven = level_set["levels"][3]
    assert seven["sheets"] == ["model#01", "model#02"] and len(seven["candidate_ids"]) == 2
    assert level_set["file"]["declared_units"]["name"] == "mm"  # declared, and still not converted


def test_only_a_level_symbol_makes_a_bare_value_medium(level_set):
    by_text = {(c["value_text"], c["form"]): c for c in level_set["candidates"]}
    assert by_text[("+7.200", "bare")]["value"]["confidence"] == "low"  # three decimals alone: unverified
    assert by_text[("+3.600", "bare")]["value"]["confidence"] == "medium"  # next to the level symbol
    labelled = by_text[("+3.650", "labelled")]
    assert labelled["value"]["confidence"] == "low"
    assert labelled["name"]["value"] == "TẦNG 2"
    assert labelled["sheet"] == "model#02" and labelled["value"]["provenance"]["sheet"] == "model#02"


def test_level_symbol_is_associated(level_set):
    bare = [c for c in level_set["candidates"] if c["value_text"] == "+3.600" and c["form"] == "bare"]
    assert bare[0]["symbol"]["block_name"] == "LVL_MARK"
    assert level_set["summary"]["level_symbol_inserts"] == 1


def test_conflicting_name_and_always_open_questions(level_set):
    q = next(q for q in level_set["questions"] if q["code"] == "level_name_conflict")
    assert q["blocking"] and q["where"] == "TẦNG 2" and q["found"] == "+3.600 / +3.650"
    fvs = next(q for q in level_set["questions"] if q["code"] == "level_finished_vs_structural")
    assert fvs["blocking"]
    once = [q["found"] for q in level_set["questions"] if q["code"] == "level_single_occurrence"]
    assert once == ["±0.000", "+3.650"]
    assert "level_datum_not_found" not in codes(level_set)


def test_storey_heights_only_between_named_storeys(level_set):
    heights = [(h["from_value"], h["to_value"], h["height"]["value"]) for h in level_set["storey_heights"]]
    assert heights == [(3.6, 3.65, pytest.approx(0.05))]  # only +3.600 and +3.650 carry 'TẦNG 2'
    first = level_set["storey_heights"][0]["height"]
    assert first["provenance"]["method"] == "derived" and len(first["provenance"]["derived_from"]) == 2
    assert first["provenance"]["sheet"] == "unknown"  # two sheets
    assert [lv["used_for_heights"] for lv in level_set["levels"]] == [False, True, True, False]
    assert "level_storey_selection" not in codes(level_set)


def test_unnamed_levels_give_low_heights_and_a_blocking_question(tmp_path):
    # '%%p' is ASCII as stored; a literal '±' in this unknown-encoding font would be blocked (see below)
    texts = ["%%p0.000", "-0.450", "-0.450", "-1.500", "-1.500", "+3.150", "+3.150", "+3.600", "+3.600"]
    result = run(_texts(tmp_path, *texts))
    assert [h["height"]["confidence"] for h in result["storey_heights"]] == ["low"] * 4
    q = next(q for q in result["questions"] if q["code"] == "level_storey_selection")
    assert q["blocking"] and q["where"] == "-1.500, -0.450, ±0.000, +3.150, +3.600"


def test_a_storey_name_with_a_negative_value_is_asked(tmp_path):
    result = run(_texts(tmp_path, "TẦNG HẦM -3.000", "TẦNG 1 ±0.000"))
    q = next(q for q in result["questions"] if q["code"] == "level_negative_storey")
    assert q["blocking"] and q["found"] == "TẦNG HẦM -3.000"


def test_a_north_arrow_is_not_a_level_symbol(tmp_path):
    doc = new("R2018", setup=True)
    blk = doc.blocks.new("NORTH_ARROW")
    blk.add_solid([(0, 0), (-300, -900), (300, -900)])  # tall triangle in a circle
    blk.add_circle((0, -600), 1000)
    tall = doc.blocks.new("TALL_TRIANGLE")
    tall.add_solid([(0, 0), (-300, -900), (300, -900)])  # no circle, but 1.5 base widths high
    msp = doc.modelspace()
    msp.add_blockref("NORTH_ARROW", (1000, 0))
    msp.add_blockref("TALL_TRIANGLE", (101000, 0))
    msp.add_text("+3.600", height=250, dxfattribs={"insert": (0, 0)})
    msp.add_text("+3.600", height=250, dxfattribs={"insert": (100000, 0)})
    path = tmp_path / "arrow.dxf"
    doc.saveas(path)
    result = run(path)
    assert [(c["symbol"], c["value"]["confidence"]) for c in result["candidates"]] == [(None, "low")] * 2
    assert result["summary"]["level_symbol_inserts"] == 0


def test_a_copied_sheet_is_not_a_second_occurrence(tmp_path):
    doc = new("R2018", setup=True)
    msp = doc.modelspace()
    for ox in (0.0, 90000.0):  # one sheet and its exact copy
        msp.add_lwpolyline([(ox, 0), (ox + 84100, 0), (ox + 84100, 59400), (ox, 59400)], close=True)
        for i in range(6):
            msp.add_text(f"NOTE {i}", height=350, dxfattribs={"insert": (ox + 1000, 1000 + i * 1000)})
        msp.add_text("+3.600", height=350, dxfattribs={"insert": (ox + 40000, 40000)})
        msp.add_text("%%p0.000", height=350, dxfattribs={"insert": (ox + 40000, 30000)})
    path = tmp_path / "copy.dxf"
    doc.saveas(path)
    result = run(path)
    three = next(lv for lv in result["levels"] if lv["value_text"] == "+3.600")
    assert len(three["candidate_ids"]) == 2 and three["occurrences"] == 1
    assert not three["used_for_heights"]
    once = sorted(q["found"] for q in result["questions"] if q["code"] == "level_single_occurrence")
    assert once == ["+3.600", "±0.000"]


def _texts(tmp_path: Path, *texts: str) -> Path:
    doc = new("R2018", setup=True)
    msp = doc.modelspace()
    for i, t in enumerate(texts):
        msp.add_text(t, height=250, dxfattribs={"insert": (0, i * 2000)})
    path = tmp_path / "t.dxf"
    doc.saveas(path)
    return path


def test_slab_plan_titles_are_not_storey_names(tmp_path):
    # two slab-plan titles that both end in 'SÀN': no storey name, so no name conflict (EVAL-3 a2)
    texts = ["MẶT BẰNG THÉP SÀN +3.900", "MẶT BẰNG THÉP SÀN +13.500", "+3.900", "+3.900", "+7.300", "+7.300"]
    result = run(_texts(tmp_path, *texts))
    assert "level_name_conflict" not in codes(result)
    assert all(c["name"] is None for c in result["candidates"])
    # no level is named: the storey heights come from the fallback rule (+7.300 is kept) and are asked
    heights = [(h["from_value"], h["to_value"], h["height"]["confidence"]) for h in result["storey_heights"]]
    assert heights == [(3.9, 7.3, "low")]
    assert "level_storey_selection" in codes(result)


def test_numbered_storey_names_still_conflict(tmp_path):
    result = run(_texts(tmp_path, "SÀN TẦNG 2 +3.600", "SÀN TẦNG 2 +3.900"))
    q = next(q for q in result["questions"] if q["code"] == "level_name_conflict")
    assert q["where"] == "SÀN TẦNG 2" and q["found"] == "+3.600 / +3.900"


def _named(tmp_path: Path, name: str) -> Path:
    doc = new("R2018", setup=True)
    msp = doc.modelspace()
    msp.add_text("+3.600", height=250, dxfattribs={"insert": (0, 0)})
    msp.add_text(name, height=250, dxfattribs={"insert": (0, 400)})  # just above the value
    path = tmp_path / "named.dxf"
    doc.saveas(path)
    return path


@pytest.mark.parametrize(  # ASCII names: a non-ASCII neighbour in this unknown-encoding file is gated
    ("name", "expected"),
    [
        ("FLOOR", None),
        ("FLOOR SLAB", None),
        ("FLOOR 2", "FLOOR 2"),
        ("ROOF", "ROOF"),
        ("BASEMENT", "BASEMENT"),
        ("LEVEL", None),
    ],
)
def test_an_adjacent_name_needs_a_number_or_a_roof_word(tmp_path, name, expected):
    (cand,) = run(_named(tmp_path, name))["candidates"]
    assert (cand["name"] or {}).get("value") == expected


@pytest.mark.parametrize(
    ("text", "named"),
    [
        ("sàn", False),
        ("SÀN BTCT", False),
        ("khối lượng thép sàn coss", False),
        ("MẶt bẰng bỐ trÍ lỚp thÉp dƯỚi (chỊu mÔ men dƯƠng) sÀn", False),  # 290 slab-plan title
        ("tầng", False),
        ("ground", False),
        ("level", False),
        ("TẦNG 3", True),
        ("Sàn tầng 3", True),
        ("tầng3", True),
        ("TẦNG HAI", True),
        ("tầng trệt", True),
        ("TẦNG LỬNG", True),
        ("lầu 2", True),
        ("MÁI", True),
        ("tum thang", True),
        ("TẦNG HẦM", True),
        ("3RD FLOOR", True),
        ("GROUND FLOOR", True),
        ("ROOF", True),
        ("TERRACE", True),
        ("MEZZANINE", True),
        ("STOREY 4", True),
    ],
)
def test_a_storey_name_needs_a_number_or_a_storey_word_of_its_own(text, named):
    assert mod._names_storey(text) is named


def test_out_of_range_value_is_a_unit_question(tmp_path):
    result = run(_texts(tmp_path, "+360.000", "+360.000"))
    q = next(q for q in result["questions"] if q["code"] == "level_value_out_of_range")
    assert q["blocking"] and q["found"] == "+360.000"


def test_no_datum_and_nonstandard_decimals(tmp_path):
    result = run(_texts(tmp_path, "+2.95", "+2.95", "+5.95", "+5.95"))
    assert {"level_datum_not_found", "level_decimals_nonstandard"} <= set(codes(result))
    assert all(c["value"]["confidence"] == "low" for c in result["candidates"])  # two decimals, no symbol


def test_every_non_embedded_single_value_is_asked(tmp_path):
    result = run(_texts(tmp_path, "+2.95", "+2.95", "+5.95"))
    five = next(lv for lv in result["levels"] if lv["value_text"] == "+5.950")
    assert not five["used_for_heights"]  # seen once, no name, no symbol
    once = [q["found"] for q in result["questions"] if q["code"] == "level_single_occurrence"]
    assert once == ["+5.950"]


def test_embedded_values_are_never_storey_heights(tmp_path):
    result = run(_texts(tmp_path, "(FROM -0.250 TO +2.750)", "(FROM -0.250 TO +2.750)"))
    assert {c["form"] for c in result["candidates"]} == {"embedded"}
    assert result["storey_heights"] == []
    assert all(not lv["used_for_heights"] for lv in result["levels"])


def test_no_level_found(tmp_path):
    result = run(_texts(tmp_path, "NOTE", "4%%c16"))
    assert codes(result) == ["level_none_found"]


# --- legacy-font gate (tool wave 2, fix 1a) ---------------------------------------------------------
# The Standard style (font txt) is covered by no font name, family or knowledge row, so non-ASCII text in it
# is blocked (encoding_unknown). '(cao \xaeé +3.850)' is 'cao độ' written in TCVN3 bytes.

BLOCKED_LEVEL = "(cao \xae\xe9 +3.850)"


def test_a_blocked_level_text_gives_no_level_and_is_listed(tmp_path):
    result = run(_texts(tmp_path, BLOCKED_LEVEL, "+3.600", "+3.600"))
    assert [c["value_text"] for c in result["candidates"]] == ["+3.600", "+3.600"]
    assert [lv["value_text"] for lv in result["levels"]] == ["+3.600"]
    (blocked,) = result["blocked_candidates"]
    text_id = next(c["text_id"] for c in result["candidates"])
    assert blocked == {"entry_id": "T000001", "line": 0, "value_text": "+3.850", "reason": "encoding_unknown"}
    assert text_id != "T000001"
    assert result["summary"]["blocked_candidates"] == 1
    assert all("3.850" not in q["where"] + q["found"] for q in result["questions"])


def test_only_blocked_level_texts_give_no_candidate_and_say_so(tmp_path):
    doc = new("R2018", setup=True)
    doc.modelspace().add_text("GHI CHU", height=250, dxfattribs={"insert": (0, 0)})
    attribs = {"insert": (0, 2000), "char_height": 250}
    doc.modelspace().add_mtext("\xae\xe9\\P+1.200 / -0.300", dxfattribs=attribs)
    doc.saveas(tmp_path / "m.dxf")
    result = run(tmp_path / "m.dxf")
    assert result["candidates"] == [] and result["levels"] == []
    held = [(b["line"], b["value_text"]) for b in result["blocked_candidates"]]
    assert held == [(1, "+1.200"), (1, "-0.300")]
    (q,) = result["questions"]
    assert q["code"] == "level_none_found" and "blocked" in q["message"]


def test_a_blocked_neighbour_never_names_a_level(tmp_path):
    def fixture(name: str, label: str) -> Path:
        doc = new("R2018", setup=True)
        msp = doc.modelspace()
        msp.add_text(label, height=250, dxfattribs={"insert": (0, 0)})
        msp.add_text("+3.600", height=250, dxfattribs={"insert": (2000, 0)})
        path = tmp_path / name
        doc.saveas(path)
        return path

    named = run(fixture("ok.dxf", "FLOOR 2"))
    assert named["candidates"][0]["name"]["value"] == "FLOOR 2"
    blocked = run(fixture("blocked.dxf", "FLOOR 2 \xae\xe9"))
    assert blocked["candidates"][0]["name"] is None


def test_a_level_in_legacy_looking_ascii_is_blocked_with_that_reason(tmp_path):
    doc = new("R2018", setup=True)
    doc.styles.add(".VnTime", font="vntime.ttf")
    msp = doc.modelspace()
    msp.add_text("BT LO/ST +3.850", height=250, dxfattribs={"insert": (0, 0), "style": ".VnTime"})
    msp.add_text("+3.850", height=250, dxfattribs={"insert": (0, 2000), "style": ".VnTime"})
    doc.saveas(tmp_path / "a.dxf")
    result = run(tmp_path / "a.dxf")
    assert [b["reason"] for b in result["blocked_candidates"]] == ["legacy_ascii_suspect"]
    assert [c["text_id"] for c in result["candidates"]] == ["T000002"]


def test_a_literal_plus_minus_in_an_unknown_font_is_blocked_but_the_special_code_is_read(tmp_path):
    # the gate blocks any non-ASCII text of unknown encoding, '±' (U+00B1) included; '%%p' is ASCII
    result = run(_texts(tmp_path, "±0.000", "%%p0.000"))
    assert [c["text_id"] for c in result["candidates"]] == ["T000002"]
    assert [(b["entry_id"], b["value_text"]) for b in result["blocked_candidates"]] == [("T000001", "±0.000")]


def test_allowed_texts_give_no_blocked_candidates(tmp_path):
    result = run(_texts(tmp_path, "+3.600", "TẦNG 2: +3.600"))
    assert result["blocked_candidates"] == [] and result["summary"]["blocked_candidates"] == 0


def test_output_is_deterministic(tmp_path):
    path = build_set(tmp_path)
    index = extract_text(path)
    sheets = extract_sheets(path, index)
    assert json.dumps(extract_levels(path, index, sheets)) == json.dumps(extract_levels(path, index, sheets))


def test_example_is_valid(example):
    assert validate("levels", example("levels")) == []
