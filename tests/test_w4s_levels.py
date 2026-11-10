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
