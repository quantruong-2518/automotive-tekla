"""marks, tool wave 3 (package M): lintel marks with a length in brackets (`LT1(L=4700)`, drawing 267),
plan marks compared with RC detail headings (a4), and the per-file mark sets (W6). Synthetic drawings only
(see _marks_fixtures / _callout_fixtures)."""

from __future__ import annotations

from typing import Any

import pytest

from tekla_harness.marks import parse_mark

# --- lintel marks with a length (267 T003614 'LT1(L=4700)') ----------------------------------------------


@pytest.mark.parametrize(
    ("text", "mark", "numbers"),
    [
        ("LT1(L=4700)", "LT1", ["1"]),
        ("LT10(L=3700)", "LT10", ["10"]),
        ("LT3 (L = 1800)", "LT3", ["3"]),
        ("LT2-1(L=3200)", "LT2-1", ["2", "1"]),
        ("LT4(L=1,5)", "LT4", ["4"]),
    ],
)
def test_a_mark_with_a_length_in_brackets_is_the_mark(text, mark, numbers):
    m = parse_mark(text)
    assert m is not None and m.text == mark and list(m.numbers) == numbers
    assert m.size is None  # a length is no section


@pytest.mark.parametrize(
    "text",
    [
        "L=4700",
        "LT1(L=)",
        "LT1(L=4700",
        "LT1(L=4700) D2",
        "LT1(H=4700)",
        "(L=4700)",
        "M20(L=4700)",  # the mark part itself is a bolt label
        "I300(L=4700)",  # ... or a section label
    ],
)
def test_not_a_mark_with_a_length(text):
    assert parse_mark(text) is None


def test_a_lintel_plan_mark_keeps_the_whole_line(tmp_path):
    from _marks_fixtures import build_marks_work
    from tekla_harness.marks import extract_marks

    work = build_marks_work(tmp_path, plan_texts=("LT1(L=4700)", "LT1(L=4700)", "LT2(L=3200)", "D1"))
    doc: dict[str, Any] = extract_marks(work, tmp_path / "input")
    lintels = [p for p in doc["plan_marks"] if p["mark"].startswith("LT")]
    assert [(p["mark"], p["display_text"], p["form"], p["size"]) for p in lintels] == [
        ("LT1", "LT1(L=4700)", "plain", None),
        ("LT1", "LT1(L=4700)", "plain", None),
        ("LT2", "LT2(L=3200)", "plain", None),
    ]
    assert {p["key"] for p in lintels} == {"lt1", "lt2"}


# --- a4: plan marks compared with RC detail headings ------------------------------------------------------
# Default tables of _marks_fixtures: A (KÝ HIỆU | b | h: D1, D2, D1-1, D9), B (NAME ...: C1, C2), a blocked
# table C (D7, D8) and an unreadable one. The plan side holds marks only; a member-word title ('DẦM D3',
# 'COLUMN C2') or an English 'DETAIL OF/ON <mark>' line is a detail heading, the second comparison source.

HEADING_PLAN = (
    "D1",
    "D2(220x500)",
    "C1 (220x220)",
    "COLUMN C2",
    "DẦM D3",
    "D3",
    "D4",
    "DẦM D5 (SL= 02)",
    "DETAIL OF AB-20B",
    "AB-20B",
    "DETAIL ON CP7A",
    "gm1",
)


@pytest.fixture(scope="module")
def heading_doc(tmp_path_factory) -> dict[str, Any]:
    from _marks_fixtures import build_marks_work
    from tekla_harness.marks import extract_marks

    base = tmp_path_factory.mktemp("headings")
    work = build_marks_work(base, plan_texts=HEADING_PLAN)
    return extract_marks(work, base / "input", check_inputs=True)


def by_key(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {x["key"]: x for x in items}


def test_headings_are_a_second_comparison_source(heading_doc):
    from tekla_harness.schemas import validate

    assert validate("marks", heading_doc) == []
    (m,) = heading_doc["matching"]
    assert m["detail_headings"] == 5
    matched = by_key(m["matched"])
    assert sorted(matched) == ["ab-20b", "c1", "d1", "d2", "d3"]
    assert {k: v["compared_with"] for k, v in matched.items()} == {
        "ab-20b": "detail_heading",
        "c1": "schedule",
        "d1": "schedule",
        "d2": "schedule",
        "d3": "detail_heading",
    }
    assert matched["d3"]["schedule"] == []
    assert [h["text"] for h in matched["d3"]["detail_headings"]] == ["DẦM D3"]
    assert [h["text"] for h in matched["ab-20b"]["detail_headings"]] == ["DETAIL OF AB-20B"]
    assert "detail_headings" not in matched["d1"]


def test_a_heading_is_no_plan_mark_in_the_comparison(heading_doc):
    (m,) = heading_doc["matching"]
    only = by_key(m["schedule_only"])
    assert sorted(only) == ["c2", "cp7a", "d1-1", "d5", "d9"]
    assert only["c2"]["compared_with"] == "schedule" and only["c2"]["schedule"]  # schedule row + heading
    assert [h["text"] for h in only["c2"]["detail_headings"]] == ["COLUMN C2"]
    assert only["d5"]["compared_with"] == "detail_heading" and only["d5"]["schedule"] == []
    assert only["d5"]["mark"] == "D5" and by_key(m["matched"])["ab-20b"]["mark"] == "AB-20B"
    assert only["cp7a"]["mark"] == "CP7A" and only["cp7a"]["detail_headings"][0]["text"] == "DETAIL ON CP7A"
    assert [h["text"] for h in only["d5"]["detail_headings"]] == ["DẦM D5 (SL= 02)"]
    assert all(
        h["sheet"] == "model#01" and h["entry_id"].startswith("T") for h in only["d5"]["detail_headings"]
    )
    plan_only = by_key(m["plan_only"])
    assert {"d4", "gm1"} <= set(plan_only) and not {"d3", "ab-20b"} & set(plan_only)
    assert {x["compared_with"] for x in m["plan_only"]} == {"schedule"}


def test_a_heading_only_match_says_why_its_size_was_not_compared(heading_doc):
    (m,) = heading_doc["matching"]
    d3 = by_key(m["matched"])["d3"]
    assert d3["size_compared"] is False
    assert (
        d3["size_not_compared_reason"] == "matched through detail headings only: no schedule row to compare"
    )


def test_title_marks_stay_plan_marks_for_the_prefix_question(heading_doc):
    titles = {p["mark"]: p for p in heading_doc["plan_marks"] if p["form"] == "title"}
    assert set(titles) == {"C2", "D3", "D5"}  # 'DETAIL OF AB-20B' is a heading only, never a plan mark
    assert [p["mark"] for p in heading_doc["plan_marks"]].count("AB-20B") == 1


@pytest.fixture(scope="module")
def no_schedule(tmp_path_factory) -> dict[str, Any]:
    from _callout_fixtures import build_work
    from tekla_harness.marks import extract_marks

    base = tmp_path_factory.mktemp("noschedule")
    work = build_work(base, s1=["D1", "D2", "DẦM D1 (SL= 02)", "DẦM D9"], styled=[], s2=["D2"], paper=[])
    return extract_marks(work, base / "input")


def test_without_a_schedule_the_headings_alone_are_compared(no_schedule):
    (m,) = no_schedule["matching"]
    assert (m["schedule_tables"], m["detail_headings"]) == (0, 2)
    assert [(x["key"], x["compared_with"]) for x in m["matched"]] == [("d1", "detail_heading")]
    assert [(x["key"], x["compared_with"]) for x in m["schedule_only"]] == [("d9", "detail_heading")]
    assert [(x["key"], x["compared_with"]) for x in m["plan_only"]] == [("d2", "detail_heading")]


def test_with_neither_source_nothing_is_compared(tmp_path):
    from _callout_fixtures import build_work
    from tekla_harness.marks import extract_marks

    work = build_work(tmp_path, s1=["D1", "D2"], styled=[], s2=[], paper=[])
    (m,) = extract_marks(work, tmp_path / "input")["matching"]
    assert (m["schedule_tables"], m["detail_headings"]) == (0, 0)
    assert m["matched"] == m["schedule_only"] == m["plan_only"] == []  # not compared is no finding


# --- W6: mark sets per file and family --------------------------------------------------------------------


def sets_of(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {s["family"]: s for s in doc["summary"]["mark_sets"]}


def marks_doc(tmp_path, s1: list[str], s2: list[str] | None = None) -> dict[str, Any]:
    from _callout_fixtures import build_work
    from tekla_harness.marks import extract_marks

    work = build_work(tmp_path, s1=s1, styled=[], s2=s2 or [], paper=[])
    return extract_marks(work, tmp_path / "input")


def test_a_family_a_heading_sweep_covers_is_complete(tmp_path):
    from tekla_harness.schemas import validate

    s1 = ["DẦM D1 (SL= 02)", "DẦM D2", "D1", "D2", "ĐÀI CỌC DC1", "M1", "M2", "M3", "M5"]
    doc = marks_doc(tmp_path, s1, ["D2"])
    assert validate("marks", doc) == []
    sets = sets_of(doc)
    assert set(sets) == {"D", "DC", "M"}
    assert sets["D"] == {
        "file": "plans/set.dxf",
        "family": "D",
        "members": ["D1", "D2"],
        "complete": True,
        "source": ["detail_heading", "plan_marks"],
    }
    assert (sets["DC"]["members"], sets["DC"]["complete"], sets["DC"]["source"]) == (
        ["DC1"],
        True,
        ["detail_heading"],
    )
    # plan marks alone never make a complete set, and a gap stays a gap
    assert (sets["M"]["members"], sets["M"]["complete"], sets["M"]["source"]) == (
        ["M1", "M2", "M3", "M5"],
        False,
        ["plan_marks"],
    )


def test_a_plan_mark_no_source_lists_makes_its_family_incomplete(no_schedule):
    d = sets_of(no_schedule)["D"]
    assert d["members"] == ["D1", "D2", "D9"] and d["complete"] is False  # D2 is plan-only


def test_a_notation_variant_makes_its_family_incomplete(tmp_path):
    doc = marks_doc(tmp_path, ["DẦM D1-1", "DẦM D1.1", "D1-1", "D1.1", "DẦM C1", "C1"])
    sets = sets_of(doc)
    assert sets["D"]["members"] == ["D1-1", "D1.1"] and sets["D"]["complete"] is False
    assert sets["C"]["complete"] is True


def test_members_are_in_natural_order_with_one_entry_per_key(tmp_path):
    doc = marks_doc(tmp_path, ["DẦM D10", "DẦM D2", "DẦM D1a", "DẦM D1", "D2", "d2", "D10"])
    d = sets_of(doc)["D"]
    assert d["members"] == ["D1", "D1a", "D2", "D10"]  # 'D2' and 'd2' are one key; the first drawn wins


def test_a_schedule_is_a_source_but_unread_tables_keep_every_set_incomplete(heading_doc):
    sets = sets_of(heading_doc)
    assert "schedule" in sets["D"]["source"] and "schedule" in sets["C"]["source"]
    assert "D7" not in sets["D"]["members"] and "D8" not in sets["D"]["members"]  # blocked rows: never read
    # the fixture holds an unparsed table and a header-blocked one: rows may be missing anywhere in the file
    assert not any(s["complete"] for s in heading_doc["summary"]["mark_sets"])
    assert sets["AB"]["members"] == ["AB-20B"] and sets["CP"]["source"] == ["detail_heading"]


# --- mutation-test follow-ups ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "mark"),
    [("DETAIL OF CP1", "CP1"), ("DETAIL ON AB-20B", "AB-20B"), ("detail of jp2 (thickness 16mm)", "jp2")],
)
def test_detail_of_headings(text, mark):
    from tekla_harness.marks import parse_detail_of

    found = parse_detail_of(text)
    assert found is not None and found.text == mark


@pytest.mark.parametrize(
    "text", ["DETAIL D1", "DETAIL OF STIFFENER", "DETAIL OF I300", "DETAILS OF CP1", "OF CP1"]
)
def test_not_detail_of_headings(text):
    from tekla_harness.marks import parse_detail_of

    assert parse_detail_of(text) is None


def test_every_heading_counts_and_a_low_heading_lowers_the_match(tmp_path):
    from _callout_fixtures import build_work
    from tekla_harness.marks import extract_marks

    # .VnTimeH is a capital font: its ASCII text is case-uncertain, so the heading is low
    work = build_work(
        tmp_path,
        s1=["DẦM D1", "D1", "DẦM D2", "D2"],
        styled=[("beam d1", ".VnTimeH")],
        s2=["DẦM D2"],
        paper=[],
    )
    (m,) = extract_marks(work, tmp_path / "input")["matching"]
    assert m["detail_headings"] == 4  # every heading counts, not every key
    matched = by_key(m["matched"])
    assert len(matched["d2"]["detail_headings"]) == 2 and matched["d2"]["confidence"] == "medium"
    assert matched["d1"]["confidence"] == "low"  # its heading "beam d1" is case-uncertain


def test_plan_marks_alone_are_never_a_complete_set(tmp_path):
    doc = marks_doc(tmp_path, ["M1", "M2"])
    assert doc["matching"][0]["plan_only"] == []  # nothing compared ...
    assert sets_of(doc)["M"]["complete"] is False  # ... and still not complete


def test_mark_sets_read_only_mark_shaped_cells_of_readable_tables():
    from tekla_harness.marks import _mark_sets

    def table(blocked: bool, marks: list[tuple[str, str, Any]]) -> dict[str, Any]:
        row = {"marks": [{"key": k, "text": t, "_structure": st} for k, t, st in marks]}
        return {"header_blocked": blocked, "mark_column": None if blocked else 0, "rows": [row]}

    tables = [
        table(False, [("x 1", "X 1", None), ("d4", "D4", ("d", (4,), ""))]),  # 'X 1' is no mark shape
        table(True, [("q1", "Q1", ("q", (1,), ""))]),  # a header-blocked table is never read
    ]
    sets = _mark_sets("f.dxf", [], tables, [], {"plan_only": [], "notation_variants": []}, False)
    assert sets == [
        {"file": "f.dxf", "family": "D", "members": ["D4"], "complete": True, "source": ["schedule"]}
    ]


@pytest.mark.parametrize(
    ("unparsed", "blocked", "header_blocked", "hides"),
    [(0, 0, False, False), (1, 0, False, True), (0, 1, False, True), (0, 0, True, True)],
)
def test_which_files_may_hide_rows(unparsed, blocked, header_blocked, hides):
    from tekla_harness.marks import _may_hide_rows

    info = {"unparsed_tables": unparsed, "blocked_marks": blocked}
    assert _may_hide_rows(info, [{"header_blocked": False}, {"header_blocked": header_blocked}]) is hides
