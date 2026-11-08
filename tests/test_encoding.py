"""Legacy Vietnamese encodings (TCVN3 / VNI) to Unicode NFC (RTI-0004).

Provenance of the fixtures, stated exactly. `src/tekla_harness/encoding.py` was generated from
the vietunicode charset table. The two fixture strings below were written by the same agent
session, by transcribing two OTHER sources into `byte=codepoint` form: the Wikipedia VSCII
code-point grid (TCVN3) and the UniKey VnConv `data.cpp` table (VNI-WIN). The transcription
script was not kept, so the strings cannot be regenerated from this repository. They are
independent of the module's table in SOURCE only, not in process: same author, same session.
Checks that do not depend on that claim: the letter-universe test (Unicode composition rules)
and an independent review that compared both fixtures and the module tables entry by entry
(74 TCVN3 bytes, 134 VNI sequences) without differences. Known-answer byte strings were derived
by hand from the grids. No test builds an inverse from the module's own tables.
"""

from __future__ import annotations

import contextlib
import unicodedata

import pytest

from tekla_harness.encoding import (
    LEGACY_POSSIBLE_CODEPOINTS,
    UNICODE_VIETNAMESE_EVIDENCE,
    FontHint,
    convert_legacy,
    font_hint,
    guess_encoding_from_font,
    has_lone_surrogate,
    has_unicode_vietnamese,
    scrub_surrogates,
)

# --- independent fixtures -------------------------------------------------------------------
# Wikipedia "VSCII" article, code-point grid, cells outside the VSCII-1/-2 additions
# (= the VSCII-3 / TCVN3 repertoire), retrieved 2026-11-06. Format: byte=code point (hex).
WIKIPEDIA_VSCII3_GRID = (
    "A1=0102 A2=00C2 A3=00CA A4=00D4 A5=01A0 A6=01AF A7=0110 A8=0103 A9=00E2 AA=00EA AB=00F4 AC=01A1 "
    "AD=01B0 AE=0111 B5=00E0 B6=1EA3 B7=00E3 B8=00E1 B9=1EA1 BB=1EB1 BC=1EB3 BD=1EB5 BE=1EAF C6=1EB7 "
    "C7=1EA7 C8=1EA9 C9=1EAB CA=1EA5 CB=1EAD CC=00E8 CE=1EBB CF=1EBD D0=00E9 D1=1EB9 D2=1EC1 D3=1EC3 "
    "D4=1EC5 D5=1EBF D6=1EC7 D7=00EC D8=1EC9 DC=0129 DD=00ED DE=1ECB DF=00F2 E1=1ECF E2=00F5 E3=00F3 "
    "E4=1ECD E5=1ED3 E6=1ED5 E7=1ED7 E8=1ED1 E9=1ED9 EA=1EDD EB=1EDF EC=1EE1 ED=1EDB EE=1EE3 EF=00F9 "
    "F1=1EE7 F2=0169 F3=00FA F4=1EE5 F5=1EEB F6=1EED F7=1EEF F8=1EE9 F9=1EF1 FA=1EF3 FB=1EF7 FC=1EF9 "
    "FD=00FD FE=1EF5 "
)
# UniKey VnConv "VNI-WIN" double-byte table (ibus-unikey ukengine/data.cpp), retrieved
# 2026-11-06, transcribed to byte sequence=code point (hex) by the agent session (script not
# kept). Sequence is base byte then mark byte.
UNIKEY_VNI_WIN_TABLE = (
    "41d8=00C0 41d9=00C1 41c2=00C2 41d5=00C3 45d8=00C8 45d9=00C9 45c2=00CA cc=00CC cd=00CD 4fd8=00D2 "
    "4fd9=00D3 4fc2=00D4 4fd5=00D5 55d8=00D9 55d9=00DA 59d9=00DD 61f8=00E0 61f9=00E1 61e2=00E2 "
    "61f5=00E3 65f8=00E8 65f9=00E9 65e2=00EA ec=00EC ed=00ED 6ff8=00F2 6ff9=00F3 6fe2=00F4 6ff5=00F5 "
    "75f8=00F9 75f9=00FA 79f9=00FD 41ca=0102 61ea=0103 d1=0110 f1=0111 d3=0128 f3=0129 55d5=0168 "
    "75f5=0169 d4=01A0 f4=01A1 d6=01AF f6=01B0 41cf=1EA0 61ef=1EA1 41db=1EA2 61fb=1EA3 41c1=1EA4 "
    "61e1=1EA5 41c0=1EA6 61e0=1EA7 41c5=1EA8 61e5=1EA9 41c3=1EAA 61e3=1EAB 41c4=1EAC 61e4=1EAD "
    "41c9=1EAE 61e9=1EAF 41c8=1EB0 61e8=1EB1 41da=1EB2 61fa=1EB3 41dc=1EB4 61fc=1EB5 41cb=1EB6 "
    "61eb=1EB7 45cf=1EB8 65ef=1EB9 45db=1EBA 65fb=1EBB 45d5=1EBC 65f5=1EBD 45c1=1EBE 65e1=1EBF "
    "45c0=1EC0 65e0=1EC1 45c5=1EC2 65e5=1EC3 45c3=1EC4 65e3=1EC5 45c4=1EC6 65e4=1EC7 c6=1EC8 e6=1EC9 "
    "d2=1ECA f2=1ECB 4fcf=1ECC 6fef=1ECD 4fdb=1ECE 6ffb=1ECF 4fc1=1ED0 6fe1=1ED1 4fc0=1ED2 6fe0=1ED3 "
    "4fc5=1ED4 6fe5=1ED5 4fc3=1ED6 6fe3=1ED7 4fc4=1ED8 6fe4=1ED9 d4d9=1EDA f4f9=1EDB d4d8=1EDC "
    "f4f8=1EDD d4db=1EDE f4fb=1EDF d4d5=1EE0 f4f5=1EE1 d4cf=1EE2 f4ef=1EE3 55cf=1EE4 75ef=1EE5 "
    "55db=1EE6 75fb=1EE7 d6d9=1EE8 f6f9=1EE9 d6d8=1EEA f6f8=1EEB d6db=1EEC f6fb=1EED d6d5=1EEE "
    "f6f5=1EEF d6cf=1EF0 f6ef=1EF1 59d8=1EF2 79f8=1EF3 ce=1EF4 ee=1EF5 59db=1EF6 79fb=1EF7 59d5=1EF8 "
    "79f5=1EF9 "
)


def _parse(table: str) -> dict[str, int]:
    return {k: int(v, 16) for k, v in (pair.split("=") for pair in table.split())}


TCVN3_GRID = {bytes.fromhex(k).decode("latin-1"): chr(v) for k, v in _parse(WIKIPEDIA_VSCII3_GRID).items()}
VNI_TABLE = {bytes.fromhex(k).decode("latin-1"): chr(v) for k, v in _parse(UNIKEY_VNI_WIN_TABLE).items()}


def _vietnamese_letters() -> set[str]:
    """All 134 non-ASCII Vietnamese letters, computed from Unicode composition rules."""
    tones = ["\u0300", "\u0301", "\u0303", "\u0309", "\u0323"]
    letters = {"\u0111", "\u0110"}  # d with stroke has no decomposition
    for base in "aăâeêioôơuưyAĂÂEÊIOÔƠUƯY":
        letters.add(unicodedata.normalize("NFC", base))
        letters.update(unicodedata.normalize("NFC", base + t) for t in tones)
    return {c for c in letters if ord(c) > 0x7F}


def tcvn3(*data: bytes) -> str:
    return b"".join(data).decode("latin-1")


# --- fixtures sanity --------------------------------------------------------------------------


def test_fixture_sizes_match_the_sources():
    assert len(TCVN3_GRID) == 74
    assert len(VNI_TABLE) == 134


def test_letter_universe_is_the_134_vietnamese_letters():
    letters = _vietnamese_letters()
    # 12 vowel families x 5 tones x 2 cases + 14 marked bases (7 per case incl. d with stroke)
    # = the 134 letters of the Vietnamese alphabet outside ASCII; plain accent-free vowels excluded.
    assert len(letters) == 134
    assert set(VNI_TABLE.values()) == letters


# --- TCVN3 ------------------------------------------------------------------------------------


def test_tcvn3_every_grid_byte_matches_the_wikipedia_grid():
    for legacy, expected in TCVN3_GRID.items():
        assert convert_legacy(legacy, "tcvn3", capital_font=False).text == expected


def test_tcvn3_covers_all_67_lowercase_letters_and_7_capitals():
    letters = _vietnamese_letters()
    lowercase = {c for c in letters if c.islower()}
    produced = {convert_legacy(k, "tcvn3", capital_font=False).text for k in TCVN3_GRID}
    assert lowercase <= produced
    # the only capitals TCVN3 has bytes for are the seven with a mark on the base letter
    assert {c for c in produced if c.isupper()} == set("ĂÂÊÔƠƯĐ")


def test_tcvn3_known_answer_phrases():
    # Bytes derived by hand from the Wikipedia grid: ả=B6 ẽ=CF ế=D5 ấ=CA é=D0 ộ=E9 ầ=C7 ó=E3 ê=AA.
    assert convert_legacy(tcvn3(b"B\xb6n v\xcf k\xd5t c\xcau th\xd0p"), "tcvn3", capital_font=False).text == (
        "Bản vẽ kết cấu thép"
    )
    assert (
        convert_legacy(tcvn3(b"C\xe9t, d\xc7m, m\xe3ng"), "tcvn3", capital_font=False).text
        == "Cột, dầm, móng"
    )
    assert convert_legacy(tcvn3(b"\xae\xad\xeang"), "tcvn3", capital_font=False).text == "đường"


def test_tcvn3_marked_capitals_are_uppercase_in_every_font():
    for font in (None, False, True):
        result = convert_legacy(tcvn3(b"\xa1\xa2\xa3\xa4\xa5\xa6\xa7"), "tcvn3", capital_font=font)
        assert result.text == "ĂÂÊÔƠƯĐ"
        assert result.ambiguous == []
        assert not result.case_uncertain


def test_tcvn3_marked_lowercase_bases_normal_font_is_lowercase_and_unflagged():
    result = convert_legacy(tcvn3(b"\xa8\xa9\xaa\xab\xac\xad\xae"), "tcvn3", capital_font=False)
    assert result.text == "ăâêôơưđ"
    assert result.ambiguous == []
    assert not result.case_uncertain


def test_tcvn3_marked_lowercase_bases_with_unknown_font_are_flagged():
    result = convert_legacy(tcvn3(b"\xa8\xae"), "tcvn3")  # capital_font=None
    assert result.text == "ăđ"
    assert [(a.index, a.candidates) for a in result.ambiguous] == [(0, ("ă", "Ă")), (1, ("đ", "Đ"))]
    assert result.case_uncertain


def test_tcvn3_marked_lowercase_bases_become_uppercase_in_a_capital_font():
    result = convert_legacy(tcvn3(b"\xa8\xa9\xaa\xab\xac\xad\xae"), "tcvn3", capital_font=True)
    assert result.text == "ĂÂÊÔƠƯĐ"
    assert result.ambiguous == []
    assert not result.case_uncertain


def test_tcvn3_mixed_ascii_and_legacy():
    result = convert_legacy(tcvn3(b"D\xc7m 300x150 (m\xe3ng) [S235]; %%c12"), "tcvn3", capital_font=False)
    assert result.text == "Dầm 300x150 (móng) [S235]; %%c12"
    assert result.unmapped == []


def test_tcvn3_empty_string():
    result = convert_legacy("", "tcvn3")
    assert (result.text, result.ambiguous, result.unmapped) == ("", [], [])


def test_tcvn3_capital_font_unspecified_reports_every_toned_letter_as_ambiguous():
    text = tcvn3(b"B\xb6N V\xcf")  # ả ẽ are toned; no lowercase ASCII, so only they are flagged
    result = convert_legacy(text, "tcvn3")  # capital_font=None
    assert result.text == "BảN Vẽ"  # lowercase, never silently guessed uppercase
    assert result.case_uncertain
    assert [(a.index, a.char, a.candidates) for a in result.ambiguous] == [
        (1, "\xb6", ("ả", "Ả")),
        (5, "\xcf", ("ẽ", "Ẽ")),
    ]


def test_tcvn3_capital_font_true_uppercases_toned_letters():
    result = convert_legacy(tcvn3(b"B\xb6N V\xcf"), "tcvn3", capital_font=True)
    assert result.text == "BẢN VẼ"
    assert result.ambiguous == []


def test_tcvn3_capital_font_unspecified_also_flags_lowercase_ascii():
    result = convert_legacy("bn", "tcvn3")
    assert result.text == "bn"
    assert [(a.index, a.char, a.candidates) for a in result.ambiguous] == [
        (0, "b", ("b", "B")),
        (1, "n", ("n", "N")),
    ]
    assert result.case_uncertain


def test_tcvn3_capital_font_false_never_flags_case():
    result = convert_legacy(tcvn3(b"b\xb6n \xa8 V\xcf"), "tcvn3", capital_font=False)
    assert result.ambiguous == []
    assert not result.case_uncertain


def test_tcvn3_capital_font_true_flags_each_lowercase_ascii_letter_and_keeps_it():
    result = convert_legacy("aBc 1", "tcvn3", capital_font=True)
    assert result.text == "aBc 1"  # a-z are NOT uppercased: no source says how a capital font draws them
    assert [(a.index, a.char, a.candidates) for a in result.ambiguous] == [
        (0, "a", ("a", "A")),
        (2, "c", ("c", "C")),
    ]
    assert all(
        "lowercase ASCII in a capital font" in a.reason and "unverified" in a.reason for a in result.ambiguous
    )
    assert result.case_uncertain


def test_tcvn3_capital_font_true_real_sample_string():
    # Real text from dwg-lab/.../267_4-story_house_complete_project.dxf, style .VnAvantH.
    result = convert_legacy("m\xc6t b\xbbng \xa7\xdeNH V\xde C\xe9T T1", "tcvn3", capital_font=True)
    assert result.text == "mẶt bẰng ĐỊNH VỊ CỘT T1"  # toned letters and Đ upper; m t b n g left as-is
    assert [(a.index, a.char) for a in result.ambiguous] == [(0, "m"), (2, "t"), (4, "b"), (6, "n"), (7, "g")]
    assert result.case_uncertain
    assert result.unmapped == []


def test_tcvn3_c0_control_bytes_are_unmapped_but_whitespace_is_not():
    result = convert_legacy("A\x01B\x17C\x18\t\n\r", "tcvn3", capital_font=False)
    assert result.text == "A\x01B\x17C\x18\t\n\r"
    assert [(u.index, u.char) for u in result.unmapped] == [(1, "\x01"), (3, "\x17")]
    assert "C0 control" in result.unmapped[0].reason


def test_tcvn3_unmapped_characters_are_kept_and_reported():
    # 0xB0 (degree sign in latin-1) has no TCVN3 letter; the euro sign is what cp1252 gives for 0x80.
    result = convert_legacy("a\xb0\u20acb\x85", "tcvn3", capital_font=False)
    assert result.text == "a\xb0\u20acb\x85"
    assert [(u.index, u.char) for u in result.unmapped] == [(1, "\xb0"), (2, "\u20ac"), (4, "\x85")]


def test_tcvn3_already_unicode_letters_above_ff_are_reported_not_converted():
    result = convert_legacy("B\u1ea3n", "tcvn3", capital_font=False)
    assert result.text == "B\u1ea3n"
    assert [u.char for u in result.unmapped] == ["\u1ea3"]


def test_tcvn3_documented_hazard_latin1_letters_in_real_unicode_text_are_converted():
    # U+00E9 is also the TCVN3 byte for ộ. The caller must decide the encoding before calling.
    assert convert_legacy("caf\xe9", "tcvn3", capital_font=False).text == "cafộ"


def test_tcvn3_does_not_expand_cad_codes():
    text = "%%c12 \\P{\\fArial|b0;x}"
    assert convert_legacy(text, "tcvn3", capital_font=False).text == text


def test_tcvn3_expanded_diameter_sign_would_be_a_letter():
    # Why %%c must stay unexpanded: U+00D8 is "ỉ" in TCVN3.
    assert convert_legacy("\u00d8", "tcvn3", capital_font=False).text == "ỉ"


def test_tcvn3_nbsp_passes_through_silently():
    result = convert_legacy("a\xa0b", "tcvn3")
    assert (result.text, result.unmapped) == ("a\xa0b", [])


# --- VNI --------------------------------------------------------------------------------------


@pytest.mark.parametrize(("legacy", "expected"), sorted(VNI_TABLE.items()))
def test_vni_every_sequence_matches_the_unikey_table(legacy, expected):
    result = convert_legacy(legacy, "vni")
    assert result.text == expected
    assert result.unmapped == []


def test_vni_known_answer_phrases():
    # Hand-derived: ộ = o+E4, ầ = a+E0, ó = o+F9, é = e+F9, đ=F1, ư=F6, ơ=F4, grave on lowercase = F8.
    assert convert_legacy("Co\xe4t, da\xe0m, mo\xf9ng", "vni").text == "Cột, dầm, móng"
    assert convert_legacy("Ba\xfbn ve\xf5 ke\xe1t", "vni").text == "Bản vẽ kết"
    assert convert_legacy("Th\x65\xf9p", "vni").text == "Thép"
    assert convert_legacy("\xf1\xf6\xf4\xf8ng", "vni").text == "đường"


def test_vni_uppercase_and_lowercase_have_different_mark_bytes():
    assert convert_legacy("A\xd8 a\xf8", "vni").text == "À à"
    assert convert_legacy("\xd4\xd8 \xf4\xf8", "vni").text == "Ờ ờ"


def test_vni_longest_match_prefers_toned_horn_letter_over_two_letters():
    assert convert_legacy("\xf6\xf4\xf8", "vni").text == "ườ"  # ư + ờ, not ừ + stray ơ


def test_vni_case_mismatch_and_orphan_marks_are_kept_and_reported():
    # 'a' + uppercase grave mark (D8), and a mark after a consonant.
    result = convert_legacy("a\xd8b\xf8", "vni")
    assert result.text == "a\xd8b\xf8"
    assert [(u.index, u.char) for u in result.unmapped] == [(1, "\xd8"), (3, "\xf8")]


def test_vni_u00d8_is_the_uppercase_grave_mark_not_a_diameter_sign():
    # Hazard: an already expanded diameter sign directly after A/E/O/U/Y is absorbed. By design.
    assert convert_legacy("A\u00d8", "vni").text == "À"
    assert convert_legacy("O\u00d8", "vni").text == "Ò"
    assert convert_legacy("A\u00d8", "vni").unmapped == []
    # Standalone, or after a character that cannot take it, it is reported and kept.
    for text in ("\u00d8", "x\u00d8", "2\u00d812"):
        result = convert_legacy(text, "vni")
        assert result.text == text
        assert [u.char for u in result.unmapped] == ["\u00d8"]


def test_vni_mixed_ascii_empty_and_codes():
    assert convert_legacy("", "vni").text == ""
    text = "%%c12 \\P{\\fVNI-Times|b0;x} 300x150"
    assert convert_legacy(text, "vni").text == text


def test_vni_has_no_ambiguity_to_report():
    result = convert_legacy("Co\xe4t da\xe0m", "vni")
    assert result.ambiguous == []
    assert not result.case_uncertain


def test_vni_euro_sign_and_unicode_letters_are_reported():
    result = convert_legacy("\u20ac\u1ea3", "vni")
    assert result.text == "\u20ac\u1ea3"
    assert [u.char for u in result.unmapped] == ["\u20ac", "\u1ea3"]


# --- shared contract --------------------------------------------------------------------------


@pytest.mark.parametrize("encoding", ["tcvn3", "vni"])
def test_output_is_nfc_and_deterministic(encoding):
    text = "e\u0301" + "".join(TCVN3_GRID if encoding == "tcvn3" else VNI_TABLE)
    first = convert_legacy(text, encoding, capital_font=False)
    assert first.text == unicodedata.normalize("NFC", first.text)
    assert convert_legacy(text, encoding, capital_font=False) == first
    assert first.text.startswith("\u00e9")  # decomposed input is composed on output


def test_cp1252_and_latin1_decodings_agree_for_every_mapped_byte():
    mapped = {ord(ch) for key in list(TCVN3_GRID) + list(VNI_TABLE) for ch in key if ord(ch) > 0x7F}
    assert min(mapped) >= 0xA1  # nothing in cp1252's divergent 0x80-0x9F range
    for code in mapped:
        raw = bytes([code])
        assert raw.decode("cp1252") == raw.decode("latin-1")


@pytest.mark.parametrize("encoding", ["tcvn3", "vni"])
def test_combining_marks_in_input_are_reported_and_flag_nfd_damage(encoding):
    result = convert_legacy("Ba\u0309n", encoding, capital_font=False)  # 'a' + combining hook above
    assert result.nfd_damaged
    assert [(u.index, u.char) for u in result.unmapped] == [(2, "\u0309")]  # index into the INPUT
    assert "NFD" in result.unmapped[0].reason
    assert result.text == "B\u1ea3n"  # output is NFC, so it is shorter than the input


@pytest.mark.parametrize("encoding", ["tcvn3", "vni"])
def test_clean_input_is_not_flagged_nfd_damaged(encoding):
    assert not convert_legacy("Co\xe4t", encoding, capital_font=False).nfd_damaged
    assert not convert_legacy("B\u1ea3n", encoding, capital_font=False).nfd_damaged  # above U+00FF but not Mn


def test_cp1258_recipe_recovers_legacy_bytes_for_every_tcvn3_byte():
    # A reader that decoded the file as cp1258 gets different code points (for example 0xC3 -> U+0102).
    # Documented recipe: re-encode with cp1258, decode as latin-1.
    for legacy in TCVN3_GRID:
        raw = legacy.encode("latin-1")
        wrongly_decoded = raw.decode("cp1258")
        assert wrongly_decoded.encode("cp1258").decode("latin-1") == legacy
        assert (
            convert_legacy(
                wrongly_decoded.encode("cp1258").decode("latin-1"), "tcvn3", capital_font=False
            ).unmapped
            == []
        )
    wrong = b"\xc3".decode("cp1258")
    assert [u.char for u in convert_legacy(wrong, "tcvn3", capital_font=False).unmapped] == [wrong]


def test_unknown_encoding_is_rejected():
    with pytest.raises(ValueError, match="unsupported encoding"):
        convert_legacy("a", "viscii")  # type: ignore[arg-type]


# --- font-name hint ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("font", "expected"),
    [
        (".VnTime", "tcvn3"),
        (".VNARIAL", "tcvn3"),
        (".VnTimeH", "tcvn3"),
        (" .vnarial.ttf ", "tcvn3"),
        ("@.VnTime", "tcvn3"),
        ("VNI-Times", "vni"),
        ("vni-helve", "vni"),
        ("VNI-Times.ttf", "vni"),
        ("Times New Roman", "unicode"),
        ("arial", "unicode"),
        ("Tahoma", "unicode"),
        # deliberately unknown: weak or conflicting evidence, file names, SHX fonts
        ("VnTime", "unknown"),  # no dot: Vietware-X per one source
        ("VHTime", "unknown"),
        ("SVN-Arial", "unknown"),
        ("UVF Tahoma", "unknown"),
        ("vntime.ttf", "unknown"),
        ("romans.shx", "unknown"),
        ("vntimeh.shx", "unknown"),  # real sample file names stay unknown (conservative)
        ("VHAVAN.TTF", "unknown"),
        ("VntimeH", "unknown"),
        (".VnTime.shx", "tcvn3"),  # actual behaviour: ".shx" is not stripped, the leading dot decides
        ("txt", "unknown"),
        ("", "unknown"),
    ],
)
def test_guess_encoding_from_font(font, expected):
    assert guess_encoding_from_font(font) == expected


@pytest.mark.parametrize(
    ("style", "font_file", "expected"),
    [
        # real names from dwg-lab/.../267_4-story_house_complete_project.dxf
        (".VnAvantH", "VHAVAN.TTF", FontHint("tcvn3", True)),
        ("VntimeH", "vntimeh.shx", FontHint("unknown", True)),  # no dot: encoding unknown, H hint stays
        ("TKT_TieuDe", "vntimeh.shx", FontHint("unknown", None)),
        ("AvantH", "VHAVAN.TTF", FontHint("unknown", None)),
        ("Standard", "txt", FontHint("unknown", None)),
        # synthetic
        (".VnTimeH", None, FontHint("tcvn3", True)),
        (".VnTime", None, FontHint("tcvn3", False)),
        (".VnTime", "VHAVAN.TTF", FontHint("tcvn3", False)),
        ("@.VnArialH", None, FontHint("tcvn3", True)),
        ("vntimeh", None, FontHint("unknown", None)),  # all lowercase: the H suffix is not readable
        ("VNI-Times", None, FontHint("vni", None)),
        ("VNI-TimesH", None, FontHint("vni", None)),  # VNI keeps case in its bytes
        ("Arial", None, FontHint("unicode", None)),
        (
            "MyStyle",
            ".VnTime.ttf",
            FontHint("tcvn3", None),
        ),  # file name used only when the style says nothing
        ("", None, FontHint("unknown", None)),
    ],
)
def test_font_hint(style, font_file, expected):
    assert font_hint(style, font_file) == expected


# --- TrueType family (tool wave 2, fix 2a; capital rule on the family: default D3) -------------------


def test_font_hint_reads_the_ttf_family_after_the_name_and_the_file():
    # EVAL-2: styles whose family is '.VnAvantH' carried most blocked text; the file name says nothing
    hint = font_hint("kt..1", "VHAVAN_2.TTF", ".VnAvantH")
    assert hint == FontHint("tcvn3", True) and hint.decided_by == "family"


@pytest.mark.parametrize(
    ("style", "font_file", "family", "expected", "decided_by"),
    [
        ("kt..1", "VHAVAN_2.TTF", ".VnArial", FontHint("tcvn3", False), "family"),
        ("kt..1", "VHAVAN_2.TTF", "@.VnArialH", FontHint("tcvn3", True), "family"),
        ("kt..1", "x.ttf", "VNI-Times", FontHint("vni", None), "family"),
        # the style name and the font file come first
        (".VnTime", None, "VNI-Times", FontHint("tcvn3", False), "name"),
        ("kt..1", ".VnTime.ttf", "VNI-Times", FontHint("tcvn3", None), "font"),
        ("Arial", None, ".VnArial", FontHint("unicode", False), "name"),
        # a Unicode family never decides: a legacy font file may carry a Unicode-looking family, and
        # 'unicode' would let mojibake through the gate (the knowledge table decides such a style)
        ("kt..1", "VHARIAL.TTF", "Arial", FontHint("unknown", None), None),
        # nothing in any field
        ("kt..1", "VHAVAN_2.TTF", "", FontHint("unknown", None), None),
        ("kt..1", "VHAVAN_2.TTF", None, FontHint("unknown", None), None),
        ("kt..1", "VHAVAN_2.TTF", "AvantGarde", FontHint("unknown", None), None),
    ],
)
def test_font_hint_family_order(style, font_file, family, expected, decided_by):
    hint = font_hint(style, font_file, family)
    assert hint == expected and hint.decided_by == decided_by


@pytest.mark.parametrize(
    ("style", "family", "capital"),
    [
        (".VnTimeH", ".VnTimeH", True),  # both say capital
        (".VnTime", ".VnTime", False),
        ("VntimeH", None, True),  # the style name alone, as before
        ("kt..1", ".vnarialh", None),  # all lowercase family: the H suffix is not readable
        ("kt..1", "AvantGarde", None),  # not a legacy-looking family: no hint
        (".VnTime", ".VnTimeH", None),  # name and family disagree: never guess
        (".VnTimeH", ".VnTime", None),
        (".VnTimeH", "Arial", True),  # a non-legacy family says nothing about case
    ],
)
def test_capital_hint_from_the_family(style, family, capital):
    assert font_hint(style, None, family).capital_font is capital


def test_decided_by_names_the_field_that_gave_the_encoding():
    assert font_hint(".VnTime").decided_by == "name"
    assert font_hint("MyStyle", ".VnTime.ttf").decided_by == "font"
    assert font_hint("Standard", "txt").decided_by is None


# --- Unicode evidence ---------------------------------------------------------------------------


def test_legacy_possible_set_is_latin1_plus_cp1252_high_block():
    # Built byte by byte: cp1252 leaves 0x81, 0x8D, 0x8F, 0x90 and 0x9D undefined.
    high = set()
    for byte in range(0x80, 0xA0):
        with contextlib.suppress(UnicodeDecodeError):
            high.add(ord(bytes([byte]).decode("cp1252")))
    assert len(high) == 27
    assert frozenset(range(0x100)) | high == LEGACY_POSSIBLE_CODEPOINTS
    assert 0x20AC in LEGACY_POSSIBLE_CODEPOINTS  # euro sign: cp1252 0x80


def test_evidence_set_never_overlaps_what_legacy_single_byte_text_can_hold():
    assert UNICODE_VIETNAMESE_EVIDENCE.isdisjoint(LEGACY_POSSIBLE_CODEPOINTS)


def test_evidence_set_is_the_listed_vietnamese_letters_and_tone_marks():
    expected = {0x102, 0x103, 0x110, 0x111, 0x1A0, 0x1A1, 0x1AF, 0x1B0, 0x300, 0x301, 0x303, 0x309, 0x323}
    expected |= set(range(0x1EA0, 0x1EFA))
    assert frozenset(expected) == UNICODE_VIETNAMESE_EVIDENCE


@pytest.mark.parametrize("text", ["Ký hiệu bản vẽ", "ĐỊNH VỊ", "đường", "a\u0301", "ơ", "Ư", "ạ"])
def test_unicode_vietnamese_detected(text):
    assert has_unicode_vietnamese(text)


@pytest.mark.parametrize(
    "text", ["", "ASCII 123", "K\xfd hi\xd6u b\xb6n v\xcf", "\u20ac", "\xd0", "\xe0", "a\u0302"]
)
def test_legacy_bytes_and_plain_latin_are_not_evidence(text):
    # Note: U+0302 (circumflex) is a combining mark but not one of the five tone marks.
    assert not has_unicode_vietnamese(text)


# --- lone surrogates (undecodable bytes) ----------------------------------------------------------


def test_scrub_surrogates_replaces_lone_surrogates_everywhere_and_counts_them():
    bad = b"b\xffn".decode("utf-8", errors="surrogateescape")  # as ezdxf reads a damaged file
    assert any(0xD800 <= ord(c) <= 0xDFFF for c in bad) and has_lone_surrogate(bad)
    data = {"a": bad, "b": [1, True, None, 2.5, {bad: ["ok", bad]}], "c": ("x",)}
    clean, count = scrub_surrogates(data)
    assert count == 3  # a value, a key and a nested value
    assert clean == {"a": "b\ufffdn", "b": [1, True, None, 2.5, {"b\ufffdn": ["ok", "b\ufffdn"]}], "c": ["x"]}
    assert data["a"] == bad  # the input is not modified
    assert scrub_surrogates("Ký hiệu") == ("Ký hiệu", 0)
    assert not has_lone_surrogate("Ký hiệu")


def test_scrubbed_data_encodes_as_utf8():
    bad = b"\xff\xfe".decode("utf-8", errors="surrogateescape")
    clean, count = scrub_surrogates({"t": bad})
    assert count == 2
    clean["t"].encode("utf-8")
