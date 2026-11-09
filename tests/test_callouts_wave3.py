"""callouts, tool wave 3 (package M): every candidate says its unparsed reason family (`unparsed_code`), a
character in diameter position that is not Ø or %%c is an unparsed candidate (W1b, never decoded), nothing
that matched is dropped without a reason (`rejected`), and unparsed candidates no other question covers are
asked as `callout_unparsed`. Synthetic drawings only (see _callout_fixtures); the shapes of the glyph texts
follow docs/research/diameter-glyph-u-grave.md (drawing 290 of EVAL-3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from _callout_fixtures import build_work
from tekla_harness.callouts import extract_callouts, member_mark, scan_line
from tekla_harness.schemas import validate

DIA = "Ø"
U_GRAVE = "ù"  # 'ù', drawing 290 style Arial (family 'CIC Arial Narrow E')
THORN = "Þ"  # 'Þ', drawing 290 VNI styles
GLYPH = "symbol_glyph_unverified"

# --- unparsed_code (unit) ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "code"),
    [
        (f"4{DIA}18 + 2{DIA}16", "ambiguous_notation"),
        (f"13{DIA}8a100", "ambiguous_notation"),
        (f"{DIA}8@150", "ambiguous_notation"),
        ("L=1800", "ambiguous_notation"),
        ("CB240-V", "grade_unverified"),
        ("AIII", "grade_unverified"),
        ("CCT52", "grade_unverified"),
        ("XCT 40", "grade_unverified"),
        ("I300", "notation_unverified"),
        ("H300x150x6.5x9", "notation_unverified"),
        ("PL12", "notation_unverified"),
        ("M20", "notation_unverified"),
        (f"lỗ {DIA}22", "notation_unverified"),
        (f"{DIA}10", "notation_unverified"),
        ("M20 4.6 8.8", "conflicting_values"),
        (f"2{U_GRAVE}20", GLYPH),
    ],
)
def test_every_unparsed_hit_names_its_reason_family(line, code):
    (hit,) = scan_line(line)
    assert hit.parsed is None and hit.code == code


@pytest.mark.parametrize("line", [f"4{DIA}16", f"{DIA}8a150", "CB300-V", "CII", "SS400", "M20 8.8"])
def test_a_parsed_hit_has_no_unparsed_code(line):
    (hit,) = scan_line(line)
    assert hit.parsed is not None and hit.code is None


def test_a_member_mark_is_member_mark_undefined():
    hit = member_mark("GM1", False)
    assert hit is not None and hit.code == "member_mark_undefined"


# --- W1b: a glyph in diameter position (unit) -----------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        f"2{U_GRAVE}20",  # count + diameter (2ù20 x117 in drawing 290)
        f"1{U_GRAVE}18",
        f"{U_GRAVE}14a150",  # diameter + spacing
        f"{U_GRAVE}10a150",
        f"2{THORN}16",  # VNI-Helve
        f"{THORN}6a100",
        f"{THORN}10a100",  # VNI-Aptima
        "⌀8a150",  # U+2300: not in the research's diameter set
        "⌀16",  # U+2300 alone with a number
        "2∅16",  # U+2205: AutoCAD's documented Unicode for %%c, not in the research set either
    ],
)
def test_a_glyph_in_diameter_position_is_an_unparsed_candidate(line):
    (hit,) = scan_line(line)
    assert (hit.kind, hit.parsed, hit.ambiguity, hit.code) == ("rebar_callout", None, None, GLYPH)
    assert hit.cap == "low"
    assert (hit.start, hit.end) == (0, len(line))
    assert "never decoded" in (hit.reason or "") and "diameter-glyph-u-grave.md" in hit.rule


def test_a_glyph_callout_keeps_its_neighbours():
    hits = scan_line(f"2{U_GRAVE}20 L=1800")
    assert [(h.code, h.ambiguity) for h in hits] == [
        (GLYPH, None),
        ("ambiguous_notation", "bar_length_l_equals"),
    ]


@pytest.mark.parametrize(
    "line",
    [
        "Đ1",  # 'Đ1' is a member mark, never a glyph
        "đ1a150",
        "220\u00d7350",  # multiplication sign: a size
        "±0.000",  # plus-minus: a level
        "45°30",  # degree sign
        "Ô1",  # 'Ô1', a slab panel letter: a lone letter + number has no callout shape
        f"{U_GRAVE}20",  # bare glyph + number: no count, no spacing (none in drawing 290)
        f"l{U_GRAVE}c",  # TCVN3 'lực'
        f"ThÐp ch{THORN}u l{U_GRAVE}c",  # TCVN3 words
        f"2{U_GRAVE}",
        f"a2{U_GRAVE}20",  # glued to the token before
        f"2{U_GRAVE}20x",  # glued to the token after
        f"3{U_GRAVE}{U_GRAVE}20",
    ],
)
def test_not_a_glyph_callout(line):
    assert all(h.code != GLYPH for h in scan_line(line))


# --- the work folder ------------------------------------------------------------------------------------

GLYPH_STYLES = [("Arial", "arial.ttf"), ("VNI-HEVEL", "VNI-Helve.ttf")]
GLYPH_TEXTS = [
    (f"2{U_GRAVE}20", "Arial"),
    (f"{U_GRAVE}14a150", "Arial"),
    (f"2{THORN}16", "VNI-HEVEL"),
    (f"{THORN}6a100", "VNI-HEVEL"),
]


@pytest.fixture(scope="module")
def glyph_work(tmp_path_factory) -> Path:
    return build_work(
        tmp_path_factory.mktemp("glyphs"),
        s1=["C1", "%%c10", "CB240-V", "M20"],
        styled=GLYPH_TEXTS,
        s2=["C1"],
        paper=[],
        extra_styles=GLYPH_STYLES,
    )


@pytest.fixture(scope="module")
def glyph_doc(glyph_work) -> dict[str, Any]:
    return extract_callouts(glyph_work, check_inputs=True)


def test_glyph_callouts_are_listed_unparsed_with_their_code(glyph_doc):
    assert validate("callouts", glyph_doc) == []
    glyphs = [c for c in glyph_doc["candidates"] if c.get("unparsed_code") == GLYPH]
    assert [c["display_text"] for c in glyphs] == [t for t, _ in GLYPH_TEXTS]
    assert all(c["parsed"] is None and c["confidence"] == "low" for c in glyphs)
    assert {c["kind"] for c in glyphs} == {"rebar_callout"}
    assert {c["encoding"] for c in glyphs} == {"unicode", "vni"}  # both allowed by the gate, neither decoded


def test_every_unparsed_candidate_has_a_code_and_no_parsed_one_has(glyph_doc):
    for c in glyph_doc["candidates"]:
        assert ("unparsed_code" in c) == (c["parsed"] is None), c


def test_summary_counts_unparsed_candidates_per_code(glyph_doc):
    s = glyph_doc["summary"]
    assert s["unparsed_by_code"] == {
        GLYPH: 4,
        "grade_unverified": 1,
        "member_mark_undefined": 2,
        "notation_unverified": 2,
    }
    assert sum(s["unparsed_by_code"].values()) == s["unparsed"]
