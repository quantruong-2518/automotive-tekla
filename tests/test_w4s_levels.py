"""levels: a spaced sign at the start of the text, and a storey name set beside a bare value (wave 4)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from ezdxf.filemanagement import new

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


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("+  0.000", [("0.000", "bare")]),
        ("+   2.500", [("2.500", "bare")]),
        ("-  1.200", [("-1.200", "bare")]),
        ("+\t3.600", [("3.600", "bare")]),
        ("+ 3.600", [("3.600", "bare")]),  # one space: as before
        ("TẦNG 2 -  3.600", []),  # a dash between a name and an unsigned number, however wide
        ("TẦNG 2 - 3.600", []),
        ("A  +  1.200", []),  # wide gap away from the start of the text: still not a sign
        ("EL. +  3.600", []),  # after a level word only the one-space gap of tool wave 3 counts
        ("EL. + 3.600", [("3.600", "prefixed")]),
        # review m4: the wide gap is for a bare value, not for a value with text after it
        ("-   2.500 kN/m2", []),
        ("+  3.600 (sàn tầng 2)", []),
        ("+  3.600 mm", []),
        ("+  1.140m", [("1.140", "bare")]),  # a trailing unit is part of the value
        ("+  3.600)", [("3.600", "embedded")]),  # a trailing bracket is allowed
        ("+ 3.600 kN/m2", [("3.600", "embedded")]),  # one space: as before
    ],
)
def test_wide_gap_after_a_sign_that_starts_the_text(text, expected):
    got = [(str(v), form) for _m, v, _f, form, _p, _n in mod._parse(text)]
    assert got == expected


def _file(
    tmp_path: Path, rows: list[tuple[str, str, tuple[float, float], tuple[float, float], float, float]]
) -> Path:
    """rows: (value text, name text, value insert, name insert, value height, name height)."""
    doc = new("R2018", setup=True)
    msp = doc.modelspace()
    for value, name, vat, nat, vh, nh in rows:
        msp.add_text(value, height=vh, dxfattribs={"insert": vat})
        msp.add_text(name, height=nh, dxfattribs={"insert": nat})
    path = tmp_path / "lv.dxf"
    doc.saveas(path)
    return path


def _names(result: dict[str, Any]) -> dict[str, str | None]:
    return {c["value_text"]: (c["name"] or {}).get("value") for c in result["candidates"]}


def test_a_spaced_zero_level_takes_the_name_set_just_above_it(tmp_path):
    path = _file(
        tmp_path,
        [
            ("+  0.000", "TẦNG 1", (149281, 1814), (149317, 2002), 100, 100),
            ("+  2.500", "TẦNG LỬNG", (149281, 4314), (149317, 4502), 100, 100),
            ("+  5.500", "TẦNG 2", (149281, 7314), (149317, 7502), 100, 100),
        ],
    )
    result = run(path)
    assert [lv["value_text"] for lv in result["levels"]] == ["±0.000", "+2.500", "+5.500"]
    assert _names(result) == {"+  0.000": "TẦNG 1", "+  2.500": "TẦNG LỬNG", "+  5.500": "TẦNG 2"}
    assert not [q for q in result["questions"] if q["code"] == "level_none_found"]


def test_a_taller_name_text_on_the_same_row_names_a_smaller_value(tmp_path):
    # the value (h 139) and its name (h 184, left and a little lower) share a row: their boxes nearly touch
    path = _file(
        tmp_path,
        [
            ("+0.450", "TẦNG 1", (1025363, -594205), (1024115, -594398), 139.4, 184.0),
            ("+4.350", "TẦNG 2", (1025363, -590305), (1024115, -590498), 139.4, 184.0),
        ],
    )
    assert _names(run(path)) == {"+0.450": "TẦNG 1", "+4.350": "TẦNG 2"}


@pytest.mark.parametrize(
    ("gap", "named"),
    [(-20.0, True), (9.0, True), (16.0, True), (30.0, False), (55.0, False)],
    ids=["overlapping", "touching", "a_tenth_of_the_taller", "a_sixth", "a_third"],
)
def test_the_name_must_touch_the_value_row(tmp_path, gap, named):
    # the name (h 184) sits left of the value (h 139) with `gap` between its top edge and the value's bottom
    top = -594205 - gap
    path = _file(tmp_path, [("+0.450", "TẦNG 1", (1025363, -594205), (1024115, top - 184.0), 139.4, 184.0)])
    assert _names(run(path)) == {"+0.450": "TẦNG 1" if named else None}


def test_a_small_name_centred_below_the_value_is_still_a_name(tmp_path):
    # review m5: the old rule took a name whose centre is within 0.75 of the value's height; keep that pair.
    # Value h 139.4 (box -594205 .. -594065.6, centre -594135.3); name h 20, centre -594235.3: 100 below
    # (< 0.75 x 139.4), and its box top (-594225.3) is 20.3 clear of the value's bottom (> 0.1 x 139.4)
    path = _file(tmp_path, [("+0.450", "TẦNG 1", (1025363, -594205), (1024115, -594245.3), 139.4, 20.0)])
    assert _names(run(path)) == {"+0.450": "TẦNG 1"}


def test_a_small_name_centred_over_three_quarters_of_the_height_below_is_not(tmp_path):
    # as above with the name centre 130 below the value centre (> 0.75 x 139.4) and 50 clear of its box
    path = _file(tmp_path, [("+0.450", "TẦNG 1", (1025363, -594205), (1024115, -594275.3), 139.4, 20.0)])
    assert _names(run(path)) == {"+0.450": None}


def test_a_name_ten_heights_away_on_the_row_is_a_name_and_thirty_is_not(tmp_path):
    near = _file(
        tmp_path, [("+0.450", "TẦNG 1", (1025363, -594205), (1025363 - 1900, -594205), 139.4, 139.4)]
    )
    assert _names(run(near)) == {"+0.450": "TẦNG 1"}
    far = _file(tmp_path, [("+0.450", "TẦNG 1", (1025363, -594205), (1025363 - 4400, -594205), 139.4, 139.4)])
    assert _names(run(far)) == {"+0.450": None}


def test_a_name_two_rows_away_is_not_a_name_on_the_same_row(tmp_path):
    path = _file(
        tmp_path,
        [("+0.450", "TẦNG 1", (1025363, -594205), (1024115, -594205 - 700), 139.4, 184.0)],
    )
    assert _names(run(path)) == {"+0.450": None}


def test_a_name_far_to_the_side_is_not_a_name(tmp_path):
    path = _file(
        tmp_path,
        [("+0.450", "TẦNG 1", (1025363, -594205), (1025363 + 5000, -594398), 139.4, 184.0)],
    )
    assert _names(run(path)) == {"+0.450": None}


# --- a name belongs to the nearest level text (re-measure G1) ---------------------------------------------


def _band_file(tmp_path: Path, below: list[tuple[str, float]], *, label: str = "MÁI") -> Path:
    """A level value with a centred storey word 1008 to its right on its row (the column-strip layout of 271)
    and level texts `below` it, set under the word: (text, drop in drawing units under the word)."""
    from ezdxf.enums import TextEntityAlignment

    doc = new("R2018", setup=True)
    doc.styles.add("UNI", font="arial.ttf")  # a Unicode font: 'MÁI' is not blocked as legacy-encoded
    msp = doc.modelspace()
    msp.add_text("+7.660", height=100, dxfattribs={"insert": (0, 0)})
    msp.add_text(label, height=100, dxfattribs={"style": "UNI"}).set_placement(
        (1008, -35), align=TextEntityAlignment.MIDDLE_CENTER
    )
    for text, drop in below:
        msp.add_text(text, height=100, dxfattribs={"style": "UNI"}).set_placement(
            (1003, -35 - drop), align=TextEntityAlignment.MIDDLE_CENTER
        )
    path = tmp_path / "band.dxf"
    doc.saveas(path)
    return path


def _bare(result: dict[str, Any]) -> dict[str, str | None]:
    return {
        c["value_text"]: (c["name"] or {}).get("value") for c in result["candidates"] if c["form"] == "bare"
    }


def test_a_storey_word_over_its_own_level_texts_does_not_name_a_beside_value(tmp_path):
    # the word heads 'TỪ +7.660' / 'ĐẾN +8.710' set under it (536 and 745 away); the bare value is 802 away
    path = _band_file(tmp_path, [("TỪ +7.660", 536.0), ("ĐẾN +8.710", 745.0)])
    result = run(path)
    assert _bare(result) == {"+7.660": None}
    # the word still counts as a storey word near an unnamed level: the safety net does not stay silent
    assert result["summary"]["candidates"] == 3


def test_the_same_word_names_the_value_when_no_level_text_is_nearer(tmp_path):
    assert _bare(run(_band_file(tmp_path, []))) == {"+7.660": "MÁI"}
    far = _band_file(tmp_path, [("TỪ +7.660", 1500.0)])  # 1500 away: the bare value (802) is nearer
    assert _bare(run(far)) == {"+7.660": "MÁI"}


def test_a_name_between_two_values_goes_to_the_nearer_one(tmp_path):
    from ezdxf.enums import TextEntityAlignment

    doc = new("R2018", setup=True)
    msp = doc.modelspace()
    msp.add_text("+3.600", height=100, dxfattribs={"insert": (0, 0)})
    msp.add_text("+7.200", height=100, dxfattribs={"insert": (700, -120)})
    # beside both values, nearer the second: the first must not take it
    msp.add_text("TẦNG 3", height=100).set_placement((1500, -30), align=TextEntityAlignment.MIDDLE_CENTER)
    path = tmp_path / "two.dxf"
    doc.saveas(path)
    assert _bare(run(path)) == {"+3.600": None, "+7.200": "TẦNG 3"}


def _row_file(tmp_path: Path, items: list[tuple[str, float, float]], height: float = 100) -> Path:
    """Unicode level/name texts at left-inserted (text, x, y) positions."""
    doc = new("R2018", setup=True)
    doc.styles.add("UNI", font="arial.ttf")
    msp = doc.modelspace()
    for text, x, y in items:
        msp.add_text(text, height=height, dxfattribs={"style": "UNI", "insert": (x, y)})
    path = tmp_path / "row.dxf"
    doc.saveas(path)
    return path


def test_a_level_text_stacked_in_the_values_column_does_not_drop_its_name(tmp_path):
    # repro A: the SSL value under +3.600 shares its column; it is not a nearer owner of the name
    path = _row_file(tmp_path, [("+3.600", 0, 0), ("+3.550 (SSL)", 0, -170), ("TẦNG 2", 1100, 0)])
    assert _bare(run(path))["+3.600"] == "TẦNG 2"


def test_a_long_note_with_a_level_does_not_drop_a_storey_name(tmp_path):
    # repro D: a long note mentioning a level (h=60) is a note, not a level text
    note = "GHI CHÚ: CAO ĐỘ ±0.000 LẤY THEO MẶT SÀN HOÀN THIỆN TẦNG 1 TẠI SẢNH"
    path = _row_file(tmp_path, [("+3.600", 0, 0), ("TẦNG 2", 1100, 0)])
    from ezdxf.filemanagement import readfile

    doc = readfile(str(path))
    doc.modelspace().add_text(note, height=60, dxfattribs={"style": "UNI", "insert": (900, -400)})
    doc.saveas(path)
    assert _bare(run(path))["+3.600"] == "TẦNG 2"


def test_a_name_above_a_column_of_values_names_only_the_one_nearest_to_it(tmp_path):
    # review m1: the stacked-column exemption is for a text BELOW the value only; a level text above counts
    path = _row_file(tmp_path, [("TẦNG 3", 0, 120), ("+7.200", 0, 0), ("+3.600", 0, -120)])
    assert _bare(run(path)) == {"+7.200": "TẦNG 3", "+3.600": None}


def test_a_multi_line_note_with_short_lines_does_not_drop_a_storey_name(tmp_path):
    # review m2: the 40-character test is on the whole text, not on each line
    note = "GHI CHÚ:\\PCAO ĐỘ ±0.000 LẤY THEO MẶT SÀN\\PHOÀN THIỆN TẦNG 1 TẠI SẢNH"
    path = _row_file(tmp_path, [("+3.600", 0, 0), ("TẦNG 2", 1100, 0)])
    from ezdxf.filemanagement import readfile

    doc = readfile(str(path))
    doc.modelspace().add_mtext(note, dxfattribs={"style": "UNI", "insert": (900, -300), "char_height": 60})
    doc.saveas(path)
    assert _bare(run(path))["+3.600"] == "TẦNG 2"


@pytest.mark.parametrize(("extra", "owner"), [("", None), ("N", "TẦNG 2")])
def test_a_level_text_of_forty_characters_owns_the_name_and_one_of_forty_one_does_not(tmp_path, extra, owner):
    text = "CAO ĐỘ +0.000 LẤY THEO MẶT SÀN HOÀN THIỆ" + extra
    assert len(text) == 40 + len(extra)
    path = _row_file(tmp_path, [("+3.600", 0, 0), ("TẦNG 2", 1100, 0)])
    from ezdxf.filemanagement import readfile

    doc = readfile(str(path))
    doc.modelspace().add_text(text, height=60, dxfattribs={"style": "UNI", "insert": (900, -150)})
    doc.saveas(path)
    assert _bare(run(path))["+3.600"] == owner


def test_a_level_text_on_the_values_row_still_owns_a_name_nearer_to_it(tmp_path):
    path = _row_file(tmp_path, [("+3.600", 0, 0), ("TẦNG 3", 1100, 0), ("+7.200", 1600, 0)])
    assert _bare(run(path))["+3.600"] is None


def _left_name_file(tmp_path: Path, others: list[tuple[str, float]]) -> Path:
    """A second layout (not the 271 strip): text height 250, a storey word centred 1500 LEFT of a bare value
    on its row, and level texts `others` set ABOVE the word: (text, rise in drawing units over the word)."""
    from ezdxf.enums import TextEntityAlignment

    doc = new("R2018", setup=True)
    doc.styles.add("UNI", font="arial.ttf")
    msp = doc.modelspace()
    msp.add_text("+7.660", height=250, dxfattribs={"insert": (2000, 0)})
    msp.add_text("MÁI", height=250, dxfattribs={"style": "UNI"}).set_placement(
        (500, 125), align=TextEntityAlignment.MIDDLE_CENTER
    )
    for text, rise in others:
        msp.add_text(text, height=250, dxfattribs={"style": "UNI"}).set_placement(
            (500, 125 + rise), align=TextEntityAlignment.MIDDLE_CENTER
        )
    path = tmp_path / "left.dxf"
    doc.saveas(path)
    return path


def test_a_name_left_of_a_value_is_not_taken_when_it_heads_a_level_text_above_it(tmp_path):
    # the word is about 2000 from the bare value and 1000 from the level text over it
    result = run(_left_name_file(tmp_path, [("ĐẾN +8.710", 1000.0)]))
    assert _bare(result) == {"+7.660": None}
    assert result["summary"]["candidates"] == 2  # the level text over the word is still a candidate


def test_a_name_left_of_a_value_is_kept_when_the_level_text_over_it_is_not_nearer(tmp_path):
    assert _bare(run(_left_name_file(tmp_path, []))) == {"+7.660": "MÁI"}
    far = _left_name_file(
        tmp_path, [("ĐẾN +8.710", 3000.0)]
    )  # 3000 over the word: the bare value (2000) wins
    assert _bare(run(far)) == {"+7.660": "MÁI"}


def _centred(msp: Any, text: str, at: tuple[float, float], height: float = 100) -> None:
    from ezdxf.enums import TextEntityAlignment

    msp.add_text(text, height=height, dxfattribs={"style": "UNI"}).set_placement(
        at, align=TextEntityAlignment.MIDDLE_CENTER
    )


def _doc_uni() -> tuple[Any, Any]:
    doc = new("R2018", setup=True)
    doc.styles.add("UNI", font="arial.ttf")
    return doc, doc.modelspace()


def test_a_nearer_level_text_with_a_name_pair_leaves_the_farther_name_for_the_value(tmp_path):
    # TẦNG 2 heads the strip texts under it (rejected for the value); TẦNG 3 stands left of the value, no
    # level text nearer to it: the value takes TẦNG 3 although TẦNG 2 is the nearer name
    doc, msp = _doc_uni()
    msp.add_text("+7.660", height=100, dxfattribs={"insert": (0, 0)})
    _centred(msp, "TẦNG 2", (1008, -35))
    _centred(msp, "TỪ +7.660", (1003, -571))
    _centred(msp, "TẦNG 3", (-900, 50))
    path = tmp_path / "pair.dxf"
    doc.saveas(path)
    assert _bare(run(path)) == {"+7.660": "TẦNG 3"}


def test_a_text_that_is_no_level_does_not_take_the_name(tmp_path):
    # 'i = -2.5%' (a slope) matches the value shape but is no level: it is not a nearer level text
    doc, msp = _doc_uni()
    msp.add_text("+7.660", height=100, dxfattribs={"insert": (0, 0)})
    _centred(msp, "MÁI", (1008, -35))
    _centred(msp, "i = -2.5%", (1003, -536))
    path = tmp_path / "slope.dxf"
    doc.saveas(path)
    assert _bare(run(path)) == {"+7.660": "MÁI"}


def test_a_nearer_level_on_a_later_line_of_a_multi_line_text_takes_the_name(tmp_path):
    doc, msp = _doc_uni()
    msp.add_text("+7.660", height=100, dxfattribs={"insert": (0, 0)})
    _centred(msp, "MÁI", (1008, -35))
    msp.add_mtext("ĐẾN\\P+8.710", dxfattribs={"insert": (800, -400), "char_height": 100, "style": "UNI"})
    path = tmp_path / "multi.dxf"
    doc.saveas(path)
    result = run(path)
    assert _bare(result)["+7.660"] is None
    assert result["summary"]["candidates"] >= 2


def test_a_level_text_as_far_as_the_value_does_not_take_the_name(tmp_path):
    # strictly nearer only: the word sits 600 from the centre of each of two values, one on either side of it
    doc, msp = _doc_uni()
    msp.add_text("+7.660", height=100, dxfattribs={"insert": (0, 0)})  # centre (210, 50)
    _centred(msp, "+8.710", (1410.0, 50.0))
    _centred(msp, "MÁI", (810.0, 50.0))
    path = tmp_path / "tie.dxf"
    doc.saveas(path)
    assert _bare(run(path)) == {"+7.660": "MÁI", "+8.710": "MÁI"}


def test_a_rejected_name_keeps_the_storey_safety_net_asking(tmp_path):
    # two named storeys elsewhere; the strip's level has a storey word beside it that names nothing
    doc, msp = _doc_uni()
    for i, (value, name) in enumerate([("+0.000", "TẦNG 1"), ("+3.600", "TẦNG 2")]):
        msp.add_text(value, height=100, dxfattribs={"insert": (50000, i * 3000)})
        msp.add_text(name, height=100, dxfattribs={"style": "UNI", "insert": (49000, i * 3000)})
    msp.add_text("+7.660", height=100, dxfattribs={"insert": (0, 0)})
    _centred(msp, "MÁI", (1008, -35))
    _centred(msp, "TỪ +7.660", (1003, -571))
    path = tmp_path / "net.dxf"
    doc.saveas(path)
    result = run(path)
    assert _bare(result)["+7.660"] is None
    assert "level_storey_selection" in [q["code"] for q in result["questions"]]
