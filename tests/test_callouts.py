"""callouts: candidate extraction. Pattern tests are unit tests on `scan_line` / `member_mark`; the rest runs
on a real intake work folder (synthetic drawing, see _callout_fixtures)."""

from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from _callout_fixtures import REL, build_work
from tekla_harness import callouts as callouts_mod
from tekla_harness.callouts import (
    AMBIGUITIES,
    callout_questions,
    extract_callouts,
    member_mark,
    question_counts,
    scan_line,
)
from tekla_harness.schemas import validate
from tekla_harness.sheet_text import ReaderError

DIA_SIGN = "Ø"  # what %%c becomes in display_text


@pytest.fixture(scope="module")
def work(tmp_path_factory) -> Path:
    return build_work(tmp_path_factory.mktemp("callouts"))


@pytest.fixture(scope="module")
def doc(work) -> dict[str, Any]:
    return extract_callouts(work, check_inputs=True)


@pytest.fixture
def damaged(work, tmp_path) -> Path:
    target = tmp_path / "copy"
    shutil.copytree(work, target)
    return target


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def find(doc: dict[str, Any], text: str, kind: str | None = None, sheet: str | None = None) -> list[dict]:
    return [
        c
        for c in doc["candidates"]
        if c["display_text"] == text
        and (kind is None or c["kind"] == kind)
        and (sheet is None or c["sheet"] == sheet)
    ]


def one(doc: dict[str, Any], text: str, kind: str | None = None, sheet: str | None = "model#01") -> dict:
    found = find(doc, text, kind, sheet)
    assert len(found) == 1, (text, [c["id"] for c in found])
    return found[0]


def first(doc: dict[str, Any], text: str, kind: str | None = None, sheet: str | None = "model#01") -> dict:
    """The first candidate in scan order (the plain column text, before the styled copies)."""
    return find(doc, text, kind, sheet)[0]


def shape(line: str) -> list[tuple[str, str | None, str | None]]:
    """(kind, parsed form or None, ambiguity) of every candidate of a line."""
    return [(h.kind, h.parsed["form"] if h.parsed else None, h.ambiguity) for h in scan_line(line)]


# --- verified patterns (unit) ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "fields"),
    [
        (f"4{DIA_SIGN}16", {"form": "count_diameter", "count": 4, "diameter_mm": 16}),
        ("4%%c18", {"form": "count_diameter", "count": 4, "diameter_mm": 18}),  # a raw code is accepted too
        (f"4 {DIA_SIGN} 16", {"form": "count_diameter", "count": 4, "diameter_mm": 16}),
        (
            f"{DIA_SIGN}8a150",
            {"form": "diameter_spacing", "diameter_mm": 8, "spacing_mm": 150, "spacing_mid_mm": None},
        ),
        (
            f"{DIA_SIGN}8a100/200",
            {"form": "diameter_spacing", "diameter_mm": 8, "spacing_mm": 100, "spacing_mid_mm": 200},
        ),
        (
            "%%C8a100",
            {"form": "diameter_spacing", "diameter_mm": 8, "spacing_mm": 100, "spacing_mid_mm": None},
        ),
        (
            f"{DIA_SIGN}8 a 150",
            {"form": "diameter_spacing", "diameter_mm": 8, "spacing_mm": 150, "spacing_mid_mm": None},
        ),
        ("ø8a150", {"form": "diameter_spacing", "diameter_mm": 8, "spacing_mm": 150, "spacing_mid_mm": None}),
        ("Φ8a150", {"form": "diameter_spacing", "diameter_mm": 8, "spacing_mm": 150, "spacing_mid_mm": None}),
        ("ϕ8a150", {"form": "diameter_spacing", "diameter_mm": 8, "spacing_mm": 150, "spacing_mid_mm": None}),
        ("φ8a150", {"form": "diameter_spacing", "diameter_mm": 8, "spacing_mm": 150, "spacing_mid_mm": None}),
        ("Ф8a150", {"form": "diameter_spacing", "diameter_mm": 8, "spacing_mm": 150, "spacing_mid_mm": None}),
        ("CB300-V", {"form": "rebar_grade", "yield_class_mpa": 300, "letter": "V", "surface": "ribbed"}),
        ("CB400V", {"form": "rebar_grade", "yield_class_mpa": 400, "letter": "V", "surface": "ribbed"}),
        ("CB240-T", {"form": "rebar_grade", "yield_class_mpa": 240, "letter": "T", "surface": "plain"}),
        ("CIII", {"form": "legacy_group", "family": "CI..CIV (TCVN 1651:1985)", "group": "III"}),
        ("A-IV", {"form": "legacy_group", "family": "A-I..A-IV (imported Russian groups)", "group": "IV"}),
        (
            "CCT34",
            {
                "form": "steel_grade_vn",
                "prefix": "CCT",
                "number": 34,
                "suffix": None,
                "standard": "TCVN 1765:1975",
            },
        ),
        (
            "XCT 52",
            {
                "form": "steel_grade_vn",
                "prefix": "XCT",
                "number": 52,
                "suffix": None,
                "standard": "TCVN 5709:1993",
            },
        ),
        (
            "CCT38Mn",
            {
                "form": "steel_grade_vn",
                "prefix": "CCT",
                "number": 38,
                "suffix": "Mn",
                "standard": "TCVN 1765:1975",
            },
        ),
        ("SS400", {"form": "steel_grade_foreign", "name": "SS400"}),
        ("Q345B", {"form": "steel_grade_foreign", "name": "Q345B"}),
        ("S275J0", {"form": "steel_grade_foreign", "name": "S275J0"}),
        ("2 L 65 x 8", {"form": "angle", "count": 2, "letter": "L", "leg_mm": 65, "thickness_mm": 8}),
        ("L65x8", {"form": "angle", "count": None, "letter": "L", "leg_mm": 65, "thickness_mm": 8}),
        ("V 50 \u00d7 5", {"form": "angle", "count": None, "letter": "V", "leg_mm": 50, "thickness_mm": 5}),
        (
            "457x191x82 UB",
            {
                "form": "ub",
                "series": "UB",
                "nominal_depth_mm": 457,
                "nominal_width_mm": 191,
                "mass_kg_per_m": 82,
            },
        ),
        ("M20 8.8", {"form": "bolt_class", "strength_class": "8.8", "thread_label": "M20"}),
        ("bu lông 10.9", {"form": "bolt_class", "strength_class": "10.9", "thread_label": None}),
        ("Bolt 4.6", {"form": "bolt_class", "strength_class": "4.6", "thread_label": None}),
    ],
)
def test_verified_pattern_is_parsed_with_its_rule(line, fields):
    hits = scan_line(line)
    assert len(hits) == 1, [(h.kind, h.rule) for h in hits]
    hit = hits[0]
    assert hit.parsed == fields and hit.reason is None
    assert "docs/research/vn-structural-drawing-conventions.md" in hit.rule or "NOTES.md" in hit.rule
    assert hit.cap in ("medium", "high")


@pytest.mark.parametrize(
    ("line", "kinds"),
    [
        (f"{DIA_SIGN}8a150 (2 lớp)", ["diameter_spacing"]),
        (f"{DIA_SIGN}8a150, {DIA_SIGN}10a200", ["diameter_spacing", "diameter_spacing"]),
        (f"4{DIA_SIGN}16, 2{DIA_SIGN}14", ["count_diameter", "count_diameter"]),
        (f"{DIA_SIGN}8a150 CB300-V", ["diameter_spacing", "rebar_grade"]),
        (f"2{DIA_SIGN}16 L=1800", ["count_diameter", None]),
    ],
)
def test_several_candidates_in_one_line(line, kinds):
    assert [h.parsed["form"] if h.parsed else None for h in scan_line(line)] == kinds


# --- near misses and ambiguous notations (unit) ---------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        f"A4{DIA_SIGN}16",  # glued to the token before
        f"12345{DIA_SIGN}16",  # five-digit count
        "CB350-V",
        "CB300-X",
        "8.8",  # a bare class is not a bolt
        "12.9 mm",
        "M5",  # not a metric bolt size
        "M20x80",  # glued
        "PL",
        "L=",
        "S1 (h=120)",
        "AIIIX",
    ],
)
def test_near_misses_give_no_candidate(line):
    assert scan_line(line) == []


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (
            f"4{DIA_SIGN}18 + 2{DIA_SIGN}16",
            [("rebar_callout", None, "rebar_plus_join")],
        ),  # ONE candidate, not its parts
        (f"4{DIA_SIGN}18+2{DIA_SIGN}16", [("rebar_callout", None, "rebar_plus_join")]),
        (f"3{DIA_SIGN}20 + 2{DIA_SIGN}18 + 2{DIA_SIGN}16", [("rebar_callout", None, "rebar_plus_join")]),
        (f"13{DIA_SIGN}8a100", [("rebar_callout", None, "rebar_count_before_spacing")]),
        ("7%%c6a100", [("rebar_callout", None, "rebar_count_before_spacing")]),
        (f"{DIA_SIGN}8@150", [("rebar_callout", None, "rebar_spacing_symbol")]),
        (f"{DIA_SIGN}8 s 150", [("rebar_callout", None, "rebar_spacing_symbol")]),
        (f"{DIA_SIGN}8A150", [("rebar_callout", None, "rebar_spacing_symbol")]),
        (f"13{DIA_SIGN}8@150", [("rebar_callout", None, "rebar_spacing_symbol")]),
        ("L=1800", [("rebar_callout", None, "bar_length_l_equals")]),
        ("L = 1,5", [("rebar_callout", None, "bar_length_l_equals")]),
        (f"{DIA_SIGN}10", [("rebar_callout", None, None)]),  # loose: diameter sign + number only
        (f"{DIA_SIGN}8a1", [("rebar_callout", None, None)]),  # spacing needs 2-3 digits
        (f"{DIA_SIGN}8a100/2000", [("rebar_callout", None, None)]),
        ("203x203x52 UC", [("section_label", None, "section_designation")]),  # only the UB table is verified
        ("CB240-V", [("rebar_grade", None, None)]),  # strength/surface pair outside the verified list
        ("CB500T", [("rebar_grade", None, None)]),
        ("CB600-T", [("rebar_grade", None, None)]),
        ("AIII", [("rebar_grade", None, None)]),  # no hyphen: in no standard
        ("AII", [("rebar_grade", None, None)]),
        ("CCT52", [("steel_grade", None, None)]),
        ("XCT 40", [("steel_grade", None, None)]),
        ("L100x100x10", [("section_label", None, "section_designation")]),
        ("L65x8.5", [("section_label", None, "section_designation")]),
        ("H300x150x6.5x9", [("section_label", None, "section_designation")]),
        ("H-300x150", [("section_label", None, "section_designation")]),
        ("I300", [("section_label", None, "section_designation")]),
        ("I20", [("section_label", None, "section_designation")]),
        ("U200", [("section_label", None, "section_designation")]),
        ("C200", [("section_label", None, "section_designation")]),
        ("HEA 300", [("section_label", None, "section_designation")]),
        ("IPE300", [("section_label", None, "section_designation")]),
        ("HN 450x200", [("section_label", None, "section_designation")]),
        ("W14x90", [("section_label", None, "section_designation")]),
        ("HSS8x6x0.5", [("section_label", None, "section_designation")]),
        ("PL 12x200x450", [("plate", None, "plate_designation")]),
        ("PL12", [("plate", None, "plate_designation")]),
        ("BM 20x300", [("plate", None, "plate_designation")]),
        ("Tấm 12x300", [("plate", None, "plate_designation")]),
        ("M20", [("bolt", None, "bolt_label_hole")]),
        ("4M24", [("bolt", None, "bolt_label_hole")]),
        (f"lỗ {DIA_SIGN}22", [("bolt", None, "bolt_label_hole")]),
        ("M20 4.6 8.8", [("bolt", None, "bolt_label_hole")]),  # two classes on one line
    ],
)
def test_ambiguous_and_unverified_notations_are_not_parsed(line, expected):
    assert shape(line) == expected
    assert all(h.reason and h.cap == "low" and h.rule for h in scan_line(line))


def test_grade_names_match_case_insensitively_only_where_the_case_is_a_guess():
    def forms(line: str, uncertain: bool) -> list[str | None]:
        return [h.parsed["form"] if h.parsed else None for h in scan_line(line, uncertain)]

    assert forms("cii", False) == [] and forms("cb300-v", False) == []
    assert forms("cii", True) == ["legacy_group"]  # a capital font drew CII, the index decoded 'cii'
    assert forms("a-iii", True) == ["legacy_group"]
    assert forms("aii", True) == [None]  # no hyphen: unparsed, as in capital letters
    assert forms("cb300-v", True) == ["rebar_grade"]
    assert forms("cct38mn", True) == ["steel_grade_vn"]
    assert scan_line("cct38mn", True)[0].parsed["suffix"] == "Mn"  # type: ignore[index]
    # only the grade names fold: a lowercase spacing marker stays the verified 'a'
    assert forms(f"{DIA_SIGN}8a150", True) == ["diameter_spacing"]
    # the candidate text keeps the original case
    hit = scan_line("cii", True)[0]
    assert "cii"[hit.start : hit.end] == "cii"


def test_c200_is_not_a_member_mark_and_c1_is_not_a_section():
    assert shape("C200")[0][0] == "section_label"
    assert scan_line("C1") == []  # two digits are needed for a channel
    assert member_mark("C1", False) is not None


@pytest.mark.parametrize(
    ("text", "case_uncertain", "lexical"),
    [
        ("C1", False, {"prefix": "C", "number": "1", "suffix": ""}),
        ("DP12", False, {"prefix": "DP", "number": "12", "suffix": ""}),
        ("GM-3", False, {"prefix": "GM", "number": "3", "suffix": ""}),
        ("MCB1p", False, {"prefix": "MCB", "number": "1", "suffix": "p"}),
        ("Đ1", False, {"prefix": "Đ", "number": "1", "suffix": ""}),
        ("N1", False, {"prefix": "N", "number": "1", "suffix": ""}),
        ("  C 4 ", False, {"prefix": "C", "number": "4", "suffix": ""}),
        ("dp1", True, {"prefix": "DP", "number": "1", "suffix": ""}),
    ],
)
def test_member_mark_shape_is_lexical_only(text, case_uncertain, lexical):
    hit = member_mark(text, case_uncertain)
    assert hit is not None
    assert hit.lexical == lexical and hit.parsed is None and hit.cap == "low"
    assert "no standard defines" in hit.rule


@pytest.mark.parametrize(
    ("text", "case_uncertain"),
    [
        ("KC-01", False),  # sheet codes (research parsing pattern 3)
        ("KT 04", False),
        ("KC 3/20", False),
        ("Đ-01", False),  # hyphenated: the electrical sheet code
        ("TCXD1", False),
        ("C", False),
        ("C1234", False),
        ("c1", False),  # lowercase is not a mark unless the case is a guess
        ("C1 (300x500)", False),
        ("Ab1", False),
    ],
)
def test_not_a_member_mark(text, case_uncertain):
    assert member_mark(text, case_uncertain) is None


# --- the work folder ------------------------------------------------------------------------------


def test_output_validates_and_names_no_absolute_path(work, doc):
    assert validate("callouts", doc) == []
    dumped = json.dumps(doc, ensure_ascii=False)
    assert str(work.parent) not in dumped and "/tmp" not in dumped
    assert [f["path"] for f in doc["files"]] == [REL] and doc["files"][0]["status"] == "scanned"
    assert doc["warnings"] and all("grids.json" in w or "levels.json" in w for w in doc["warnings"])


def test_runs_are_identical_and_ids_sequential(work, doc):
    assert extract_callouts(work) == doc
    assert [c["id"] for c in doc["candidates"]] == [f"K{n:06d}" for n in range(1, len(doc["candidates"]) + 1)]


def test_percent_percent_c_is_already_expanded(doc):
    c = first(doc, f"4{DIA_SIGN}16", "rebar_callout")
    assert "%%" not in c["display_text"] and DIA_SIGN in c["display_text"]
    assert c["parsed"] == {"form": "count_diameter", "count": 4, "diameter_mm": 16}
    assert c["rule"].startswith("COUNT_DIA (docs/research/vn-structural-drawing-conventions.md")
    assert (c["confidence"], c["ambiguity"], c["unparsed_reason"]) == ("medium", None, None)


def test_nothing_is_high_a_single_text_is_never_cross_checked(doc):
    assert "high" not in doc["summary"]["by_confidence"]
    for line in ("CCT34", "SS400", "XCT 38", "Q345B"):
        assert [h.cap for h in scan_line(line)] == ["medium"]


def test_unlisted_grade_pairs_are_not_a_legacy_question_and_the_listed_ones_are_parsed():
    for ok in ("CB240-T", "CB300T", "CB300-V", "CB400-T", "CB400V", "CB500-V", "CB600V"):
        assert scan_line(ok)[0].parsed is not None, ok


def test_verified_grade_b_grammar_is_at_most_medium(doc):
    for c in doc["candidates"]:
        if c["parsed"] and c["parsed"]["form"] in (
            "count_diameter",
            "diameter_spacing",
            "bolt_class",
            "angle",
        ):
            assert c["confidence"] in ("medium", "low")
    assert one(doc, f"{DIA_SIGN}8a100/200")["parsed"]["spacing_mid_mm"] == 200


def test_unparsed_candidates_say_why_and_are_low(doc):
    unparsed = [c for c in doc["candidates"] if c["parsed"] is None]
    assert unparsed
    for c in unparsed:
        assert c["unparsed_reason"] and c["rule"] and c["confidence"] == "low", c["display_text"]
    for c in doc["candidates"]:
        if c["parsed"] is not None:
            assert c["unparsed_reason"] is None


def test_ambiguous_forms_are_single_candidates_in_their_line(doc):
    plus = find(doc, f"4{DIA_SIGN}18 + 2{DIA_SIGN}16")
    assert len(plus) == 1 and plus[0]["ambiguity"] == "rebar_plus_join" and plus[0]["parsed"] is None
    same_entry = [c for c in doc["candidates"] if c["text_ref"] == plus[0]["text_ref"]]
    assert same_entry == plus  # its parts are not extracted again
    count = one(doc, f"13{DIA_SIGN}8a100")
    assert count["ambiguity"] == "rebar_count_before_spacing" and count["parsed"] is None
    assert find(doc, f"{DIA_SIGN}8a100", sheet="model#01") == []  # the zone count is not stripped off


def test_two_candidates_in_one_text_share_its_ref_and_show_the_line(doc):
    both = [c for c in doc["candidates"] if c.get("line_text") == f"2{DIA_SIGN}16 L=1800"]
    assert [c["display_text"] for c in both] == [f"2{DIA_SIGN}16", "L=1800"]
    assert both[0]["text_ref"] == both[1]["text_ref"]
    assert both[0]["parsed"]["count"] == 2 and both[1]["ambiguity"] == "bar_length_l_equals"
    assert all("line_text" not in c for c in doc["candidates"] if c["display_text"] == f"{DIA_SIGN}8a150")


def test_near_misses_of_the_fixture_do_not_appear(doc):
    texts = {c["display_text"] for c in doc["candidates"]}
    for absent in ("A4" + DIA_SIGN + "16", "⌀16", "CB350-V", "8.8", "S1", "KC-01", "ROW-A"):
        assert absent not in texts
    assert not [c for c in doc["candidates"] if "A4" in c.get("line_text", "") or "⌀" in c["display_text"]]
    assert one(doc, "CCT52")["parsed"] is None and one(doc, "AIII")["parsed"] is None


def test_every_verified_pattern_of_the_fixture_is_parsed(doc):
    forms = {c["display_text"]: c["parsed"]["form"] for c in doc["candidates"] if c["parsed"]}
    assert forms[f"{DIA_SIGN}8a150"] == "diameter_spacing"
    assert forms["CB300-V"] == forms["CB400V"] == forms["CB240-T"] == "rebar_grade"
    assert forms["CII"] == forms["A-III"] == "legacy_group"
    assert forms["CCT34"] == forms["XCT 38"] == forms["CCT38Mn"] == "steel_grade_vn"
    assert forms["SS400"] == forms["Q235B"] == forms["S355JR"] == "steel_grade_foreign"
    assert forms["2 L 65 x 8"] == "angle" and forms["457x191x82 UB"] == "ub"
    assert forms["M20 8.8"] == forms["10.9 M24"] == "bolt_class"
    assert one(doc, "XCT 38")["parsed"]["standard"] == "TCVN 5709:1993"
    assert one(doc, "10.9 M24")["line_text"] == "BOLT 10.9 M24"


def test_sheet_and_printed_number_with_provenance_shape(doc):
    c = first(doc, f"4{DIA_SIGN}16", "rebar_callout")
    assert c["file"] == REL and c["sheet"] == "model#01"
    assert c["sheet_number"] == {"value": "S-101", "confidence": "medium"}
    prov = c["provenance"]
    assert prov["method"] == "derived" and prov["file"] == REL and prov["sheet"] == "S-101"
    assert prov["revision"] == "A"
    (src,) = prov["derived_from"]
    assert (src["file"], src["sheet"], src["method"], src["revision"]) == (REL, "S-101", "dxf_entity", "A")
    assert len(src["region"]["bbox"]) == 4 and "derived_from" not in src
    assert c["text_ref"] == {"file": REL, "entry_id": c["text_ref"]["entry_id"]}
    paper = one(doc, f"2{DIA_SIGN}14", "rebar_callout", sheet="Plot#01")
    assert paper["sheet_number"]["value"] == "S-201" and paper["provenance"]["sheet"] == "S-201"
    assert paper["provenance"]["revision"] == "B"
    assert validate("callouts", doc) == []


def test_without_a_printed_number_provenance_sheet_is_unknown(damaged):
    path = damaged / "structure" / f"{REL}.sheets.json"
    sheets = load(path)
    for sh in sheets["sheets"]:
        sh["title_block"]["sheet_number"] = None
        sh["title_block"]["revision"] = None
    path.write_text(json.dumps(sheets), encoding="utf-8")
    out = extract_callouts(damaged)
    c = first(out, f"4{DIA_SIGN}16", "rebar_callout")
    assert c["sheet"] == "model#01" and c["sheet_number"] is None
    assert c["provenance"]["sheet"] == "unknown" and "revision" not in c["provenance"]
    assert c["provenance"]["derived_from"][0]["sheet"] == "unknown"
    assert validate("callouts", out) == []


def test_missing_sheets_document_keeps_candidates_without_sheets(damaged):
    (damaged / "structure" / f"{REL}.sheets.json").unlink()
    out = extract_callouts(damaged)
    assert out["candidates"] and all(c["sheet"] is None for c in out["candidates"])
    assert any("sheets.json is missing" in w for w in out["warnings"])
    assert validate("callouts", out) == []


# --- confidence -----------------------------------------------------------------------------------


def test_member_marks_are_always_low_and_lexical(doc):
    marks = [c for c in doc["candidates"] if c["kind"] == "member_mark"]
    assert marks and all(c["confidence"] == "low" and c["parsed"] is None for c in marks)
    assert all(set(c["lexical"]) == {"prefix", "number", "suffix"} for c in marks)
    assert all("lexical" not in c for c in doc["candidates"] if c["kind"] != "member_mark")


def test_title_block_and_sheet_codes_are_not_member_marks(doc):
    marks = {c["display_text"] for c in doc["candidates"] if c["kind"] == "member_mark"}
    assert "S-101" not in marks and "KC-01" not in marks  # claimed by the title block / a sheet code


def test_texts_claimed_by_grids_or_levels_are_not_member_marks(damaged):
    index = load(damaged / "text" / f"{REL}.json")
    c2 = next(e["id"] for e in index["entries"] if e["display_text"] == "C2")
    d1 = next(e["id"] for e in index["entries"] if e["display_text"] == "D1")
    structure = damaged / "structure"
    (structure / f"{REL}.grids.json").write_text(
        json.dumps({"groups": [{"families": [{"axes": [{"bubbles": [{"text_id": c2}]}]}]}]}), encoding="utf-8"
    )
    (structure / f"{REL}.levels.json").write_text(
        json.dumps({"candidates": [{"text_id": d1}]}), encoding="utf-8"
    )
    out = extract_callouts(damaged)
    marks = {c["display_text"] for c in out["candidates"] if c["kind"] == "member_mark"}
    assert "C2" not in marks and "D1" not in marks and "C1" in marks
    assert out["warnings"] == []


def test_unknown_encoding_and_case_uncertain_text_is_low(doc):
    # review fix: the legacy-font gate blocks non-ASCII text in an unknown encoding, so a literal O-stroke
    # (4Ø16 in VntimeH) and "4%%c16 tên" are no candidates; they are listed as blocked_entries instead
    assert not [c for c in doc["candidates"] if "diameter_sign_literal_non_unicode" in c["flags"]]
    same_code = [
        c for c in find(doc, f"4{DIA_SIGN}16", "rebar_callout", "model#01") if c["encoding"] == "unknown"
    ]
    assert any(  # the same notation through %%c is ASCII in raw_text: allowed
        c["confidence"] == "medium" and "diameter_sign_literal_non_unicode" not in c["flags"]
        for c in same_code
    )
    d1 = [c for c in doc["candidates"] if c["display_text"] == "d1"]
    assert len(d1) == 1 and d1[0]["lexical"]["prefix"] == "D"
    assert "case_uncertain" in d1[0]["flags"] and d1[0]["confidence"] == "low"


# --- questions ------------------------------------------------------------------------------------


def questions(doc: dict[str, Any], code: str) -> list[dict[str, Any]]:
    """The numbered-questions' raw form (callouts-questions.json is built from it), for one code."""
    return [q for q in callout_questions(doc["candidates"]) if q["code"] == code]


def subjects(doc: dict[str, Any], code: str) -> dict[str, dict[str, Any]]:
    return {s["name"]: s for q in questions(doc, code) for s in q["subjects"]}


def refs_of(doc: dict[str, Any], code: str, name: str) -> list[dict[str, Any]]:
    """The refs of one notation: they carry its name in `found`."""
    return [r for q in questions(doc, code) for r in q["refs"] if r["found"].startswith(f"[{name}] ")]


def test_the_document_holds_no_questions_only_counts(doc, work):
    assert "questions" not in doc and "questions" not in doc["summary"]
    assert "blocking_questions" not in doc["summary"]
    assert doc["question_counts"] == {"callout_ambiguous": 9, "grade_legacy_mapping": 1}
    assert doc["question_counts"] == question_counts(doc["candidates"])
    assert extract_callouts(work)["question_counts"] == doc["question_counts"]  # deterministic


def test_question_counts_follow_the_candidates(example):
    cands = [
        c for c in example("callouts")["candidates"] if c["ambiguity"] is None and c["kind"] != "member_mark"
    ]
    assert question_counts(cands) == {}  # codes without a question are absent


def test_one_callout_ambiguous_subject_per_notation_with_refs(doc):
    qs = questions(doc, "callout_ambiguous")
    assert all(q["file"] == REL and q["truncated"] is False for q in qs)
    found = subjects(doc, "callout_ambiguous")
    for q in qs:  # sorted inside each question (blocking and non-blocking notations are separate questions)
        names = [s["name"] for s in q["subjects"]]
        assert names == sorted(names)
    assert set(found) == {
        "bar_length_l_equals",
        "bolt_label_hole",
        "plate_designation",
        "rebar_count_before_spacing",
        "rebar_grade_edition",
        "rebar_plus_join",
        "rebar_spacing_symbol",
        "section_designation",
        "steel_grade_standard_mix",
    }
    for name, subject in found.items():
        members = [c for c in doc["candidates"] if c["ambiguity"] == name]
        assert subject["count"] == len(members)
        refs = refs_of(doc, "callout_ambiguous", name)
        assert [r["where"] for r in refs] == [f"text entry {c['text_ref']['entry_id']}" for c in members]
        assert refs[0]["message"]  # the wording of this notation's question
        owner = next(q for q in qs if name in {s["name"] for s in q["subjects"]})
        assert owner["blocking"] is AMBIGUITIES[name][0]
    assert not qs[0]["refs"][0]["file"].startswith("/")


def test_blocking_choice_interpretation_blocks_standards_do_not(doc):
    blocking = {s["name"]: q["blocking"] for q in questions(doc, "callout_ambiguous") for s in q["subjects"]}
    assert blocking["rebar_plus_join"] and blocking["section_designation"] and blocking["bolt_label_hole"]
    assert not blocking["rebar_grade_edition"] and not blocking["steel_grade_standard_mix"]


def test_member_marks_are_listed_but_their_prefixes_are_asked_by_marks(doc):
    """Tool wave 2 (fix 1b, D6): `harness marks` asks member_mark_prefix_meaning for every plan-mark
    prefix; callouts still lists member_mark candidates but raises no prefix question."""
    assert not questions(doc, "member_mark_prefix_meaning")
    assert "member_mark_prefix_meaning" not in question_counts(doc["candidates"])
    prefixes = {c["lexical"]["prefix"] for c in doc["candidates"] if c["kind"] == "member_mark"}
    assert prefixes == {"C", "D", "DP", "GM", "M", "TB", "Đ"}
    assert doc["summary"]["member_mark_prefixes"] == len(prefixes)


def test_legacy_grades_raise_one_blocking_mapping_question(doc):
    (q,) = questions(doc, "grade_legacy_mapping")
    assert q["blocking"] and q["count"] == 3  # CII, A-III, AIII
    assert "no official mapping" in q["message"]
    legacy = [c for c in doc["candidates"] if c["display_text"] in ("CII", "A-III", "AIII")]
    assert len(legacy) == 3 and all("yield" not in json.dumps(c["parsed"]) for c in legacy)  # never mapped


def test_refs_are_capped_but_counts_stay_true(work, monkeypatch):
    monkeypatch.setattr(callouts_mod, "MAX_REFS", 1)
    monkeypatch.setattr(callouts_mod, "MAX_PREFIX_REFS", 1)
    out = extract_callouts(work)
    mix = subjects(out, "callout_ambiguous")["steel_grade_standard_mix"]
    assert mix["count"] == 7 and len(refs_of(out, "callout_ambiguous", "steel_grade_standard_mix")) == 1
    (q,) = questions(out, "callout_ambiguous")[:1]
    assert q["truncated"] is True
    assert validate("callouts", out) == []


def only_steel_grades(work: Path, target: Path, keep: set[str]) -> dict[str, Any]:
    """Copy the work folder, blank every steel grade text but `keep`, then extract."""
    shutil.copytree(work, target)
    damaged = target
    path = damaged / "text" / f"{REL}.json"
    index = load(path)
    for e in index["entries"]:
        if e["display_text"] in {"CCT34", "XCT 38", "CCT52", "CCT38Mn", "SS400", "Q235B", "S355JR"} - keep:
            e["display_text"] = "x"
    path.write_text(json.dumps(index), encoding="utf-8")
    return extract_callouts(damaged)


def test_steel_standard_mix_is_asked_only_when_a_sheet_mixes_standards(work, tmp_path):
    out = only_steel_grades(work, tmp_path / "one", {"CCT34", "CCT38Mn", "CCT52"})  # one family
    assert not [c for c in out["candidates"] if c["ambiguity"] == "steel_grade_standard_mix"]
    assert "steel_grade_standard_mix" not in subjects(out, "callout_ambiguous")
    out = only_steel_grades(work, tmp_path / "two", {"CCT34", "XCT 38"})  # TCVN 1765 and TCVN 5709 names
    mix = [c for c in out["candidates"] if c["ambiguity"] == "steel_grade_standard_mix"]
    assert {c["display_text"] for c in mix} == {"CCT34", "XCT 38"}


# --- summary and structure ------------------------------------------------------------------------


def test_summary_counts_add_up(doc):
    s = doc["summary"]
    cands = doc["candidates"]
    assert s["candidates"] == len(cands) == s["parsed"] + s["unparsed"]
    assert s["unparsed"] == sum(1 for c in cands if c["parsed"] is None)
    assert sum(s["by_kind"].values()) == len(cands) and sum(s["by_confidence"].values()) == len(cands)
    assert [r["file"] for r in s["by_file"]] == [REL] and s["by_file"][0]["total"] == len(cands)
    sheets = {r["sheet"]: r for r in s["by_sheet"]}
    assert set(sheets) == {"model#01", "model#02", "Plot#01"}
    assert sheets["model#02"]["sheet_number"]["value"] == "S-102"
    assert sum(r["total"] for r in s["by_sheet"]) == len(cands)
    assert s["member_mark_prefixes"] == len(
        {c["lexical"]["prefix"] for c in cands if c["kind"] == "member_mark"}
    )
    assert (s["files_scanned"], s["files_skipped"]) == (1, 0)
    assert doc["files"][0]["candidates"] == len(cands)


def test_summary_counts_unparsed_candidates_per_reason(doc):
    """Tool wave 2 (fix 11): the report asks how many candidates stayed unparsed and why."""
    s = doc["summary"]
    unparsed = [c["unparsed_reason"] for c in doc["candidates"] if c["parsed"] is None]
    assert s["unparsed_by_reason"] == dict(sorted(Counter(unparsed).items()))
    assert sum(s["unparsed_by_reason"].values()) == s["unparsed"]
    assert list(s["unparsed_by_reason"]) == sorted(s["unparsed_by_reason"])
    assert len(s["unparsed_by_reason"]) > 3
    assert validate("callouts", doc) == []


def test_summary_unparsed_by_reason_is_empty_without_unparsed_candidates(tmp_path):
    work = build_work(tmp_path, s1=["4%%c16", "CB300-V"], styled=[], s2=[], paper=[])
    s = extract_callouts(work)["summary"]
    assert s["unparsed"] == 0 and s["unparsed_by_reason"] == {}


def test_duplicate_sheets_are_skipped_and_listed(damaged):
    path = damaged / "structure" / f"{REL}.sheets.json"
    sheets = load(path)
    copy = next(s for s in sheets["sheets"] if s["sheet_id"] == "model#02")
    copy["duplicate_of"] = "model#01"
    path.write_text(json.dumps(sheets), encoding="utf-8")
    out = extract_callouts(damaged)
    assert out["skipped_sheets"] == [
        {"file": REL, "sheet": "model#02", "duplicate_of": "model#01", "text_entries": len(copy["text_ids"])}
    ]
    assert not [c for c in out["candidates"] if c["sheet"] == "model#02"]
    row = out["files"][0]
    assert row["scanned"] == row["text_entries"] - len(copy["text_ids"])
    assert validate("callouts", out) == []


def test_stale_structure_and_foreign_sheets_are_reported(damaged):
    (damaged / "structure-summary.json").write_text(
        json.dumps({"inventory_sha256": "0" * 64}), encoding="utf-8"
    )
    assert any("stale" in w for w in extract_callouts(damaged)["warnings"])
    path = damaged / "structure" / f"{REL}.sheets.json"
    sheets = load(path)
    sheets["file"]["sha256"] = "f" * 64
    path.write_text(json.dumps(sheets), encoding="utf-8")
    with pytest.raises(ReaderError) as err:
        extract_callouts(damaged)
    assert err.value.exit_code == 1


def test_missing_inventory_is_a_usage_error(tmp_path):
    with pytest.raises(ReaderError) as err:
        extract_callouts(tmp_path)
    assert err.value.exit_code == 2


# --- schema ------------------------------------------------------------------------------


def test_example_is_valid(example):
    assert validate("callouts", example("callouts")) == []


@pytest.mark.parametrize(
    "damage",
    [
        lambda c: c.update(unparsed_reason="why"),  # parsed and unparsed_reason together
        lambda c: c.update(parsed=None, unparsed_reason=None),
        lambda c: c.update(parsed={"form": "count_diameter", "count": 4}),  # incomplete
        lambda c: c.update(parsed={"form": "weld", "size": 6}),  # unknown form
        lambda c: c["provenance"].update(method="dxf_entity"),  # must be derived
        lambda c: c["provenance"].pop("derived_from"),
        lambda c: c.update(extra="x"),
        lambda c: c.update(kind="weld"),
        lambda c: c.update(confidence="certain"),
    ],
)
def test_schema_rejects_damaged_candidates(example, damage):
    doc = example("callouts")
    damage(next(c for c in doc["candidates"] if c["parsed"] is not None))
    assert validate("callouts", doc)


def test_schema_member_marks_are_low_and_lexical(example):
    doc = example("callouts")
    mark = next(c for c in doc["candidates"] if c["kind"] == "member_mark")
    mark["confidence"] = "medium"
    assert validate("callouts", doc)
    mark["confidence"] = "low"
    del mark["lexical"]
    assert validate("callouts", doc)


def test_blocked_text_yields_no_candidate_and_is_listed_verbatim(work, doc):
    """A non-ASCII text in an unknown-encoding font is never read (text_gate), even if it looks like 4Ø16."""
    from tekla_harness.text_gate import meaning_block_reason

    entries = {e["id"]: e for e in load(work / "text" / f"{REL}.json")["entries"]}
    blocked_ids = {i for i, e in entries.items() if meaning_block_reason(e)}
    assert blocked_ids
    assert not [c for c in doc["candidates"] if c["text_ref"]["entry_id"] in blocked_ids]
    listed = {b["entry_id"]: b for b in doc["blocked_entries"]}
    assert listed and set(listed) <= blocked_ids
    literal = [b for b in doc["blocked_entries"] if b["display_text"] == f"4{DIA_SIGN}16"]
    assert len(literal) == 1
    assert literal[0]["reason"] == meaning_block_reason(entries[literal[0]["entry_id"]])
    assert literal[0]["sheet"] == "model#01" and literal[0]["file"] == REL
    assert doc["summary"]["blocked_entries"] == len(doc["blocked_entries"])
    assert validate("callouts", doc) == []
