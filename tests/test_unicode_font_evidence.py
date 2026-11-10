"""Tool wave 4, package T, V2: plain Unicode text in a TrueType style is no longer blocked as encoding_unknown
when the font file has already shown itself to be Unicode.

EVAL-4 criterion 2: 271 `KÍNH` (style KCS_SMTEXT, arial_3.ttf, a name that says nothing about the encoding)
was blocked `encoding_unknown`, because `Í` (U+00CD) is below U+0100 and so is no code-point evidence of its
own, while 160 other entries of the same font file are proved Unicode by letters no legacy single-byte font
can hold. The rule (extract_text flag `unicode_by_font_evidence`): an entry whose unknown-encoding runs all
sit in a TrueType file that holds at least one run proved Unicode by code points, and no run read as TCVN3 /
VNI or contradicting its font, and whose non-ASCII letters there are all Vietnamese letters Latin-1 holds,
passes the gate. TCVN3 / VNI and legacy_ascii_suspect blocking do not change. Fixtures are built with ezdxf.
"""

from __future__ import annotations

import pytest

from tekla_harness.text_gate import meaning_block_reason
from test_extract_text import SUSPECT, build, family_style, flagged, index, only, text_at
from test_knowledge import approved, row, table_of

KINH = "K\xcdNH"  # KÍNH: U+00CD is below U+0100, valid Vietnamese and a legacy byte alike
PROVEN = "ĐƯNG"  # ĐƯNG: Vietnamese letters above U+00FF, only Unicode can hold them
FLAG = "unicode_by_font_evidence"


def fixture(*, proven_style: str = "KCS", proven_font: str = "arial_3.ttf", style_font: str = "arial_3.ttf"):
    """Style `KCS` on `style_font` holding KÍNH; a proven-Unicode entry in `proven_style` on `proven_font`."""

    def fn(doc):
        doc.styles.add("KCS", font=style_font)
        if proven_style != "KCS":
            doc.styles.add(proven_style, font=proven_font)
        text_at(doc.modelspace(), KINH, "KCS", insert=(0, 0))
        text_at(doc.modelspace(), PROVEN, proven_style, insert=(0, 9))

    return fn


def test_the_eval_4_case_is_allowed_by_the_font_evidence(tmp_path):
    result = index(build(tmp_path, fixture()))
    e = only(result, raw_text=KINH)
    assert meaning_block_reason(e) is None
    assert FLAG in e["flags"] and "encoding_unknown_non_ascii" not in e["flags"]
    # nothing about the string itself is claimed: the decode stays what the string alone supports
    assert (e["decode"]["encoding_used"], e["decode"]["source"]) == ("unknown", "none")
    assert e["decoded_text"] == e["display_text"] == KINH
    proven = only(result, raw_text=PROVEN)
    assert meaning_block_reason(proven) is None and FLAG not in proven["flags"]


def test_without_a_proven_sibling_the_same_text_stays_blocked(tmp_path):
    def fn(doc):
        doc.styles.add("KCS", font="arial_3.ttf")
        text_at(doc.modelspace(), KINH, "KCS")

    e = only(index(build(tmp_path, fn)), raw_text=KINH)
    assert meaning_block_reason(e) == "encoding_unknown"
    assert FLAG not in e["flags"] and "encoding_unknown_non_ascii" in e["flags"]


def test_the_evidence_belongs_to_the_font_file_not_the_style(tmp_path):
    result = index(build(tmp_path, fixture(proven_style="BIG", proven_font="ARIAL_3.TTF")))
    assert meaning_block_reason(only(result, raw_text=KINH)) is None


def test_evidence_in_another_font_file_does_not_count(tmp_path):
    result = index(build(tmp_path, fixture(proven_style="BIG", proven_font="other.ttf")))
    assert meaning_block_reason(only(result, raw_text=KINH)) == "encoding_unknown"


def test_a_shx_font_is_never_lifted_by_a_sibling(tmp_path):
    # a Unicode run in an SHX style proves nothing about the SHX file's other strings
    result = index(build(tmp_path, fixture(style_font="face.shx", proven_font="face.shx")))
    assert meaning_block_reason(only(result, raw_text=KINH)) == "encoding_unknown"


def test_a_font_file_shared_with_a_tcvn3_style_is_not_lifted(tmp_path):
    def fn(doc):
        doc.styles.add(".VnTime", font="shared.ttf")  # TCVN3 by its name
        doc.styles.add("KCS", font="shared.ttf")
        text_at(doc.modelspace(), PROVEN, "KCS", insert=(0, 9))  # proves Unicode in the shared file
        text_at(doc.modelspace(), "m\xb5t", ".VnTime", insert=(0, 18))  # legacy bytes on the same file
        text_at(doc.modelspace(), KINH, "KCS", insert=(0, 0))

    result = index(build(tmp_path, fn))
    assert meaning_block_reason(only(result, raw_text=KINH)) == "encoding_unknown"
    assert meaning_block_reason(only(result, raw_text="m\xb5t")) is None  # TCVN3, converted: unchanged


def test_unicode_text_in_a_tcvn3_style_does_not_prove_its_file(tmp_path):
    def fn(doc):
        doc.styles.add(".VnTime", font="shared.ttf")
        doc.styles.add("KCS", font="shared.ttf")
        text_at(doc.modelspace(), PROVEN, ".VnTime", insert=(0, 9))  # contradicts the style's own font
        text_at(doc.modelspace(), KINH, "KCS", insert=(0, 0))

    result = index(build(tmp_path, fn))
    assert "unicode_evidence_contradicts_font" in only(result, raw_text=PROVEN)["flags"]
    assert meaning_block_reason(only(result, raw_text=KINH)) == "encoding_unknown"


@pytest.mark.parametrize("text", ["b\xb6n", "\xa7\xb5t", "K\xcd\xadNH", "\xd8\x31\x36", "K\xcdNH\xb2"])
def test_letters_that_are_no_vietnamese_unicode_letters_stay_blocked(tmp_path, text):
    # pilcrow, section sign, soft hyphen, O-stroke, superscript two: legacy bytes or symbols, not letters
    def fn(doc):
        fixture()(doc)
        text_at(doc.modelspace(), text, "KCS", insert=(0, 20))

    e = only(index(build(tmp_path, fn)), raw_text=text)
    assert meaning_block_reason(e) == "encoding_unknown" and FLAG not in e["flags"]


@pytest.mark.parametrize("word", ["SÂN SAU", "BAN CÔNG", "ÀÁÃÈÉÊÌÍÒÓÔÕÙÚÝ", "àáâãèéêìíòóôõùúý"])
def test_every_latin_1_vietnamese_letter_is_accepted(tmp_path, word):
    def fn(doc):
        fixture()(doc)
        text_at(doc.modelspace(), word, "KCS", insert=(0, 20))

    assert meaning_block_reason(only(index(build(tmp_path, fn)), raw_text=word)) is None


@pytest.mark.parametrize("word", ["\xc4", "\xd6", "\xdc", "\xc7", "\xd1", "\xc5", "\xdf", "\xe7"])
def test_latin_1_letters_vietnamese_does_not_use_stay_blocked(tmp_path, word):
    def fn(doc):
        fixture()(doc)
        text_at(doc.modelspace(), word, "KCS", insert=(0, 20))

    assert meaning_block_reason(only(index(build(tmp_path, fn)), raw_text=word)) == "encoding_unknown"


@pytest.mark.parametrize("lead", ["SAN ", "S\xc2N "])
def test_a_mixed_mtext_whose_unknown_style_run_is_plain_is_lifted(tmp_path, lead):
    def fn(doc):
        fixture()(doc)
        doc.modelspace().add_mtext(
            lead + "{\\fArial|b0|i0|c0|p34;" + PROVEN + "}", dxfattribs={"style": "KCS", "insert": (0, 40)}
        )

    e = only(index(build(tmp_path, fn)), entity_type="MTEXT")
    assert e["decode"]["encoding_used"] == "mixed"
    assert meaning_block_reason(e) is None and FLAG in e["flags"]


def test_a_mixed_mtext_stays_blocked_without_the_evidence(tmp_path):
    def fn(doc):
        doc.styles.add("KCS", font="arial_3.ttf")
        doc.modelspace().add_mtext(
            "SAN {\\fArial|b0|i0|c0|p34;" + PROVEN + "}", dxfattribs={"style": "KCS", "insert": (0, 40)}
        )

    e = only(index(build(tmp_path, fn)), entity_type="MTEXT")
    assert meaning_block_reason(e) == "encoding_unknown" and FLAG not in e["flags"]


def test_an_unknown_inline_font_run_is_never_lifted(tmp_path):
    def fn(doc):
        fixture()(doc)
        doc.modelspace().add_mtext(
            "{\\fMysteryFace|b0|i0|c0|p34;" + KINH + "}", dxfattribs={"style": "KCS", "insert": (0, 40)}
        )

    e = only(index(build(tmp_path, fn)), entity_type="MTEXT")
    assert meaning_block_reason(e) == "encoding_unknown" and FLAG not in e["flags"]


def test_a_proposed_row_still_blocks_first(tmp_path):
    table = table_of(tmp_path, row(pattern="arial_3.ttf"))  # proposed, never applied
    e = only(index(build(tmp_path, fixture()), knowledge=table), raw_text=KINH)
    assert "proposed_knowledge_row" in e["flags"] and meaning_block_reason(e) == "encoding_proposed"


def test_an_approved_row_that_decides_the_style_is_untouched(tmp_path):
    table = table_of(tmp_path, approved(pattern="arial_3.ttf", encoding="tcvn3"))
    e = only(index(build(tmp_path, fixture()), knowledge=table), raw_text=KINH)
    assert e["decode"]["encoding_used"] == "tcvn3" and FLAG not in e["flags"]


def test_legacy_ascii_suspect_flagging_is_unchanged_by_the_lift(tmp_path):
    # kept on purpose (tool wave 4 brief): the lifted KÍNH still registers its font as holding non-ASCII text
    # of unknown encoding, so ASCII of a legacy shape in that style is flagged exactly as before
    def fn(doc):
        doc.styles.add("KCS", font="arial_3.ttf")
        msp = doc.modelspace()
        for i, text in enumerate(SUSPECT):
            text_at(msp, text, "KCS", insert=(0, 9 * i))
        text_at(msp, KINH, "KCS", insert=(500, 0))
        text_at(msp, PROVEN, "KCS", insert=(500, 9))

    result = index(build(tmp_path, fn))
    assert all(flagged(result)[t] for t in SUSPECT)
    assert all(meaning_block_reason(only(result, raw_text=t)) == "legacy_ascii_suspect" for t in SUSPECT)
    assert meaning_block_reason(only(result, raw_text=KINH)) is None


def test_a_tcvn3_family_style_keeps_its_own_decision(tmp_path):
    def fn(doc):
        family_style(doc, "kt..1", "VHARIAL.TTF", ".VnArial")
        text_at(doc.modelspace(), "m\xc6t", "kt..1")

    e = only(index(build(tmp_path, fn)), entity_type="TEXT")
    assert (e["decode"]["encoding_used"], FLAG in e["flags"]) == ("tcvn3", False)
