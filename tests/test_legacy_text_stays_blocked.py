"""Tool wave 4, package T: legacy-encoded text in a TrueType file stays blocked, even next to Unicode text.

The independent review of tool wave 4 (REVIEW-TS.md, C1) showed that a font-evidence lift ("one Unicode string
proves the font file, so its undecided strings are Unicode") let TCVN3 and VNI strings past the gate: 9 of 9
strings below, in `vhtime.ttf`, with one Unicode string beside them. A Unicode string typed into a legacy-font
style is evidence about that string only. The lift was reverted and is not re-landed in this wave; `KÍNH`
(271, `arial_3.ttf`) stays blocked, and the marks package moves its ids out of the header cells instead.
These tests keep it that way: the strings are TCVN3 / VNI bytes as Latin-1 characters, built from table facts.
"""

from __future__ import annotations

import pytest

from tekla_harness.text_gate import meaning_block_reason
from test_extract_text import build, index, text_at

UNICODE = "Mặt bằng m\xf3ng"  # Mặt bằng móng: U+1EB7 and U+1EB1 prove this string Unicode
TCVN3 = ["c\xe9t", "M\xe3ng", "c\xe8t +3.600", "tr\xf4c", "n\xd2n", "s\xe8"]  # cột Móng cốt trục nền số
VNI = ["Mo\xf9ng", "co\xe1t the\xf9p", "Ta\xe0ng"]  # Móng cốt thép Tầng
NINE = TCVN3 + VNI
FLAG = "unicode_by_font_evidence"


def blocked(e) -> bool:
    return meaning_block_reason(e) is not None


def test_nine_legacy_strings_next_to_a_unicode_string_stay_blocked(tmp_path):
    def fn(doc):
        doc.styles.add("KT", font="vhtime.ttf")  # Vietware naming: no encoding decided from the name
        text_at(doc.modelspace(), UNICODE, "KT", insert=(0, 0))
        for i, text in enumerate(NINE):
            text_at(doc.modelspace(), text, "KT", insert=(0, 9 * (i + 1)))

    result = index(build(tmp_path, fn))
    legacy = [e for e in result["entries"] if e["raw_text"] in NINE]
    assert len(legacy) == 9 and all(e["decode"]["encoding_used"] == "unknown" for e in legacy)
    assert [meaning_block_reason(e) for e in legacy] == ["encoding_unknown"] * 9
    assert not any(FLAG in e["flags"] for e in result["entries"])


def test_the_same_nine_without_any_unicode_string_stay_blocked(tmp_path):
    def fn(doc):
        doc.styles.add("KT", font="vhtime.ttf")
        for i, text in enumerate(NINE):
            text_at(doc.modelspace(), text, "KT", insert=(0, 9 * i))

    assert all(blocked(e) for e in index(build(tmp_path, fn))["entries"])


def test_legacy_text_in_another_style_of_the_proven_file_stays_blocked(tmp_path):
    def fn(doc):
        doc.styles.add("S1", font="arial_3.ttf")
        doc.styles.add("S2", font="arial_3.ttf")
        text_at(doc.modelspace(), UNICODE, "S1", insert=(0, 0))
        text_at(doc.modelspace(), "c\xe9t", "S2", insert=(0, 9))
        text_at(doc.modelspace(), "Mo\xf9ng", "S2", insert=(0, 18))

    result = index(build(tmp_path, fn))
    assert [meaning_block_reason(e) for e in result["entries"] if e["style"] == "S2"] == [
        "encoding_unknown"
    ] * 2


def test_a_unicode_string_inside_an_mtext_does_not_unblock_a_text(tmp_path):
    def fn(doc):
        doc.styles.add("S1", font="kcs.ttf")
        doc.modelspace().add_mtext(UNICODE, dxfattribs={"style": "S1", "insert": (200, 0)})
        text_at(doc.modelspace(), "M\xe3ng", "S1")

    result = index(build(tmp_path, fn))
    assert meaning_block_reason(next(e for e in result["entries"] if e["raw_text"] == "M\xe3ng")) is not None


@pytest.mark.parametrize("font", ["VNTIME.TTF", "VNARIAL.TTF", "VHAVAN.TTF"])
def test_the_files_of_legacy_styles_do_not_lift_undecided_strings(tmp_path, font):
    def fn(doc):
        doc.styles.add("Standard2", font=font)
        for i, text in enumerate(["Ghi ch\xfa: b\xea t\xf4ng cấp độ bền B20", "c\xe9t C1", "M\xe3ng M1"]):
            text_at(doc.modelspace(), text, "Standard2", insert=(0, 9 * i))

    result = index(build(tmp_path, fn))
    assert not any(FLAG in e["flags"] for e in result["entries"])
    assert all(blocked(e) for e in result["entries"] if e["decode"]["encoding_used"] == "unknown")


def test_kinh_in_the_eval_4_style_stays_blocked(tmp_path):
    # 271 T001081: Í is below U+0100, so the string has no code-point evidence of its own
    def fn(doc):
        doc.styles.add("KCS", font="arial_3.ttf")
        text_at(doc.modelspace(), "K\xcdNH", "KCS", insert=(0, 0))
        text_at(doc.modelspace(), "ĐƯNG", "KCS", insert=(0, 9))

    result = index(build(tmp_path, fn))
    kinh = next(e for e in result["entries"] if e["raw_text"] == "K\xcdNH")
    assert meaning_block_reason(kinh) == "encoding_unknown" and FLAG not in kinh["flags"]
    assert "encoding_unknown_non_ascii" in kinh["flags"]  # so intake still asks about the style
