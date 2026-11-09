"""callouts, tool wave 3 (package M): every candidate says its unparsed reason family (`unparsed_code`), a
character in diameter position that is not Ø or %%c is an unparsed candidate (W1b, never decoded), nothing
that matched is dropped without a reason (`rejected`), and unparsed candidates no other question covers are
asked as `callout_unparsed`. Synthetic drawings only (see _callout_fixtures); the shapes of the glyph texts
follow docs/research/diameter-glyph-u-grave.md (drawing 290 of EVAL-3)."""

from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from _callout_fixtures import REL, build_work
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


# --- nothing that matched is dropped without a reason (rejected) -------------------------------------------

REJECT_TEXTS = [
    "C1",
    "%%c<10mm",  # a diameter sign with no number after it (286's rebar table: 'Ø<10mm')
    "A4%%c16",  # glued to the token before
    "4%%c16 + %%c",  # the trailing sign belongs to no candidate
    "KC-01",  # a sheet code
    "D1",
    "C2",
]


@pytest.fixture(scope="module")
def reject_work(tmp_path_factory) -> Path:
    return build_work(tmp_path_factory.mktemp("rejects"), s1=REJECT_TEXTS, styled=[], s2=["C1"], paper=[])


@pytest.fixture(scope="module")
def reject_doc(reject_work) -> dict[str, Any]:
    return extract_callouts(reject_work, check_inputs=True)


def rejected(doc: dict[str, Any], code: str) -> list[str]:
    return [r["display_text"] for r in doc["rejected"] if r["reason_code"] == code]


def test_a_diameter_sign_no_pattern_reads_is_rejected_with_its_reason(reject_doc):
    assert validate("callouts", reject_doc) == []
    assert rejected(reject_doc, "diameter_sign_no_notation") == [f"{DIA}<10mm", f"A4{DIA}16", DIA]
    row = next(r for r in reject_doc["rejected"] if r["display_text"] == f"{DIA}<10mm")
    assert row["kind"] == "rebar_callout" and row["sheet"] == "model#01" and row["entry_id"].startswith("T")
    assert "no callout pattern" in row["reason"]


def test_a_sheet_code_and_a_title_block_value_are_rejected_not_dropped(reject_doc):
    assert rejected(reject_doc, "sheet_code") == ["KC-01"]
    assert "S-101" in rejected(reject_doc, "claimed_by_title_block")  # the printed sheet number
    marks = {c["display_text"] for c in reject_doc["candidates"] if c["kind"] == "member_mark"}
    assert not {"KC-01", "S-101"} & marks
    others = [r for r in reject_doc["rejected"] if r["reason_code"] != "diameter_sign_no_notation"]
    assert others and {r["kind"] for r in others} == {"member_mark"}


def test_texts_claimed_by_grids_or_levels_are_rejected_with_the_claimer(reject_work, tmp_path):
    target = tmp_path / "copy"
    shutil.copytree(reject_work, target)
    index = json.loads((target / "text" / f"{REL}.json").read_text(encoding="utf-8"))
    c2 = next(e["id"] for e in index["entries"] if e["display_text"] == "C2")
    d1 = next(e["id"] for e in index["entries"] if e["display_text"] == "D1")
    structure = target / "structure"
    (structure / f"{REL}.grids.json").write_text(json.dumps({"a": [{"text_id": c2}]}), encoding="utf-8")
    (structure / f"{REL}.levels.json").write_text(json.dumps({"b": {"text_id": d1}}), encoding="utf-8")
    out = extract_callouts(target)
    assert rejected(out, "claimed_by_grids") == ["C2"] and rejected(out, "claimed_by_levels") == ["D1"]


def test_summary_counts_rejected_matches(reject_doc):
    s = reject_doc["summary"]
    assert s["rejected"] == len(reject_doc["rejected"])
    by_reason = Counter(r["reason_code"] for r in reject_doc["rejected"])
    assert s["rejected_by_reason"] == dict(sorted(by_reason.items()))
    assert s["rejected_by_reason"]["diameter_sign_no_notation"] == 3


def test_every_diameter_sign_is_a_candidate_a_blocked_entry_or_rejected(reject_doc, reject_work):
    """The 'never drop silently' invariant: every text with a diameter sign is accounted for."""
    index = json.loads((reject_work / "text" / f"{REL}.json").read_text(encoding="utf-8"))
    accounted = {c["text_ref"]["entry_id"] for c in reject_doc["candidates"]}
    accounted |= {b["entry_id"] for b in reject_doc["blocked_entries"]}
    accounted |= {r["entry_id"] for r in reject_doc["rejected"]}
    with_sign = {e["id"] for e in index["entries"] if DIA in e["display_text"]}
    assert len(with_sign) == 3 and with_sign <= accounted
