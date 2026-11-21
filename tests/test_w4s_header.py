"""A drawing-list header value is claimed by its text id and is no member mark (wave 4)."""

from __future__ import annotations

from pathlib import Path

import pytest
from ezdxf.filemanagement import readfile

from _callout_fixtures import PROPOSED_FONT_TABLE, write_structure
from _callout_fixtures import REL as FIXTURE_REL
from _dxf_fixtures import build_set
from _marks_fixtures import PLAN_STEP, PLAN_TOP, PLAN_X, TH
from tekla_harness.intake import run_intake
from tekla_harness.marks import extract_marks
from tekla_harness.schemas import validate


def build(base: Path, header: str, first: str, rest: list[str], elsewhere: list[str]) -> tuple[Path, Path]:
    root = base / "input"
    (root / "plans").mkdir(parents=True)
    doc = readfile(str(build_set(base, "src.dxf")))
    msp = doc.modelspace()
    msp.add_text(header, height=TH, dxfattribs={"insert": (PLAN_X, PLAN_TOP)})
    for i, t in enumerate([first, *rest], start=1):
        msp.add_text(t, height=TH, dxfattribs={"insert": (PLAN_X, PLAN_TOP - i * 3 * TH)})
    for i, t in enumerate(elsewhere):
        msp.add_text(t, height=TH, dxfattribs={"insert": (PLAN_X + 20000, PLAN_TOP - i * 3 * PLAN_STEP)})
    doc.saveas(root / FIXTURE_REL)
    work = base / "work"
    run_intake(root, work, "demo-marks", knowledge=PROPOSED_FONT_TABLE)
    write_structure(root, work)
    return work, root


@pytest.mark.parametrize(
    ("header", "first", "rest", "plan_mark"),
    [
        ("DRAWING NO", "DM-00", ["KC-01", "KC-02"], "DM-01"),
        ("SHEET NO.", "TL-00", ["KT-01", "KT-02", "KT-03"], "TL-01"),
    ],
)
def test_header_value_is_no_mark_but_the_same_shape_elsewhere_is(tmp_path, header, first, rest, plan_mark):
    work, root = build(tmp_path, header, first, rest, ["DM-01", "TL-01"])
    doc = extract_marks(work, root / "input", check_inputs=True)
    marks = [p["mark"].upper() for p in doc["plan_marks"]]
    assert first not in marks
    assert plan_mark in marks


def test_sheets_document_lists_the_header_id_and_validates(tmp_path):
    import json

    work, root = build(tmp_path, "DRAWING NO", "DM-00", ["KC-01", "KC-02"], [])
    extract_marks(work, root / "input", check_inputs=True)
    docs = sorted(work.rglob("*.sheets.json"))
    assert docs
    sheets = json.loads(docs[0].read_text(encoding="utf-8"))
    assert validate("sheets", sheets) == []
    ids = sheets["drawing_list"]["header_text_ids"]
    assert len(ids) == 1
    header = next(t for t in _texts(work) if t["display_text"].strip() == "DM-00")
    assert ids == [header["id"]]


def test_a_label_over_a_single_value_is_no_drawing_list_header(tmp_path):
    import json

    work, root = build(tmp_path, "DRAWING NO", "DM-00", [], [])
    extract_marks(work, root / "input", check_inputs=True)
    sheets = json.loads(sorted(work.rglob("*.sheets.json"))[0].read_text(encoding="utf-8"))
    assert validate("sheets", sheets) == []
    assert sheets["drawing_list"] == {"status": "not_searched"}


def _texts(work: Path) -> list[dict]:
    import json

    out: list[dict] = []
    for p in sorted(work.rglob("*.json")):
        doc = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(doc, dict) and isinstance(doc.get("entries"), list):
            out.extend(e for e in doc["entries"] if isinstance(e, dict) and "display_text" in e)
    return out


@pytest.mark.parametrize(
    ("first", "rows"),
    [("DM-00", ["DM-01", "DM-02"]), ("S-100", ["S-101", "S-102", "S-103"])],
)
def test_the_rows_under_a_drawing_list_header_are_no_marks_either(tmp_path, first, rows):
    import json

    work, root = build(tmp_path, "DRAWING NO", first, rows, ["DM-01"])
    doc = extract_marks(work, root / "input", check_inputs=True)
    marks = [p["mark"].upper() for p in doc["plan_marks"]]
    assert first not in marks
    assert [m for m in marks if m in rows and m != "DM-01"] == []
    assert (
        marks.count("DM-01") == 1
    )  # the DM-01 placed elsewhere stays a mark; a list row of that name does not
    sheets = json.loads(sorted(work.rglob("*.sheets.json"))[0].read_text(encoding="utf-8"))
    assert validate("sheets", sheets) == []
    by_id = {t["id"]: t["display_text"].strip() for t in _texts(work)}
    assert sorted(by_id[i] for i in sheets["drawing_list"]["row_text_ids"]) == sorted(rows)


def test_sheet_code_shaped_texts_stacked_under_a_labelled_sheet_number_are_list_rows_not_marks(tmp_path):
    # review m4: the rule is wider than a real drawing list. Any sheet-code-shaped text stacked within the
    # row gap under a labelled sheet number is claimed as a list row, a member-mark-looking code included.
    work, root = build(tmp_path, "DRAWING NO", "DM-00", ["P-02", "J-01", "J-02"], [])
    doc = extract_marks(work, root / "input", check_inputs=True)
    marks = [p["mark"].upper() for p in doc["plan_marks"]]
    assert [m for m in marks if m in {"DM-00", "P-02", "J-01", "J-02"}] == []
    import json

    sheets = json.loads(sorted(work.rglob("*.sheets.json"))[0].read_text(encoding="utf-8"))
    by_id = {t["id"]: t["display_text"].strip() for t in _texts(work)}
    assert sorted(by_id[i] for i in sheets["drawing_list"]["row_text_ids"]) == ["J-01", "J-02", "P-02"]
