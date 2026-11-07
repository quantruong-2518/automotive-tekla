"""Convert legacy Vietnamese font encodings (TCVN3 "ABC" and VNI-Windows) to Unicode NFC.

Why: a DWG/DXF text style that uses a legacy font (".VnTime", "VNI-Times") stores bytes that
decode "successfully" into Latin-1 garbage (RTI-0004). This module turns that garbage back
into Vietnamese. Pure functions, no I/O, deterministic.

Expected input form
-------------------
`text` is the *raw* entity string whose code points 0x00-0xFF map one-to-one to the legacy
bytes, i.e. the bytes decoded as latin-1. A cp1252 decode gives the same string for every
byte that carries a Vietnamese letter (all are >= 0xA1; cp1252 differs from latin-1 only in
0x80-0x9F). Anything above U+00FF (for example cp1252's euro sign, or text that is already
Unicode) is never converted: it is kept and reported in `ConversionResult.unmapped`.
Combining marks (category Mn, U+0300...) in the input mean the string was decomposed (NFD)
upstream, so it is not one-byte-per-char legacy text: each is reported in `unmapped` and
`ConversionResult.nfd_damaged` is set. The output is NFC, so such marks get composed into the
preceding character; every `index` in this module refers to the INPUT string, never to the
output. A DXF/DWG that is not cp1252/latin-1 (for example ANSI_1258) must be re-encoded with
its own code page and re-decoded as latin-1 first (`s.encode("cp1258").decode("latin-1")`;
tested for every TCVN3 byte).
Convert BEFORE expanding `%%c` / `%%d` codes: U+00D8 (the expanded diameter sign) is a letter
in TCVN3 (ỉ) and, in VNI, the uppercase grave mark byte 0xD8. In VNI a diameter sign right
after A E O U Y (or Ơ Ư) is therefore silently absorbed into one letter (`AØ` -> `À`, by
design); a standalone Ø is reported in `unmapped`. ASCII (including `%%c`, `\\P`,
`{\\f...;}` MTEXT codes) passes through untouched.

Tables (provenance in docs/research/vietnamese-legacy-encodings.md)
--------------------------------------------------------------------
Generated from the Vietnamese Unicode FAQs charset table (vietunicode.sourceforge.net/charset/,
retrieved 2026-11-06), then checked entry by entry against two other sources:
  * the VSCII-3 cells of the Wikipedia "VSCII" code-point grid (CC BY-SA 4.0), and
  * the UniKey VnConv tables (ibus-unikey ukengine/data.cpp, GPL-2.0-or-later; read only,
    nothing copied) for TCVN3 and VNI-WIN.
All three agree on every entry: 74 TCVN3 bytes and 134 VNI sequences (an independent review
re-checked this count). The tables are a factual code-point mapping of TCVN 5712:1993 (VN3) and of the VNI
layout, not a creative work; see the research note for the licence caveat.

TCVN3 facts
-----------
* 0xA1-0xA7 are Ă Â Ê Ô Ơ Ư Đ; 0xA8-0xAE are ă â ê ô ơ ư đ.
* 0xB5-0xFE (with gaps) are the 60 *toned lowercase* letters. TCVN3 has no toned capitals:
  the sources say capitals with tone marks come from a separate all-capital font that reuses
  the same bytes. The code cannot tell from the bytes which kind of font was used, so
  `capital_font` is explicit (see `convert_legacy`).
* 0x01-0x17 (except tab, LF, CR) hold capitals in other TCVN 5712 tables (VN1); this module
  does not map them and reports them in `unmapped`.
VNI facts
---------
* A letter is a base byte plus an optional mark byte (`a` + 0xF8 = à); upper- and lower-case
  have different mark bytes (`A` + 0xD8 = À). Ơ Ư ơ ư (0xD4 0xD6 0xF4 0xF6) are standalone
  letters and can also be the base of a toned letter, so matching is longest-first.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal, cast

Encoding = Literal["tcvn3", "vni"]
FontEncoding = Literal["tcvn3", "vni", "unicode", "unknown"]

_TCVN3_MARKED_BASE: dict[int, int] = {
    0xA1: 0x0102,
    0xA2: 0x00C2,
    0xA3: 0x00CA,
    0xA4: 0x00D4,
    0xA5: 0x01A0,
    0xA6: 0x01AF,
    0xA7: 0x0110,
    0xA8: 0x0103,
    0xA9: 0x00E2,
    0xAA: 0x00EA,
    0xAB: 0x00F4,
    0xAC: 0x01A1,
    0xAD: 0x01B0,
    0xAE: 0x0111,
}
_TCVN3_TONED: dict[int, int] = {
    0xB5: 0x00E0,
    0xB6: 0x1EA3,
    0xB7: 0x00E3,
    0xB8: 0x00E1,
    0xB9: 0x1EA1,
    0xBB: 0x1EB1,
    0xBC: 0x1EB3,
    0xBD: 0x1EB5,
    0xBE: 0x1EAF,
    0xC6: 0x1EB7,
    0xC7: 0x1EA7,
    0xC8: 0x1EA9,
    0xC9: 0x1EAB,
    0xCA: 0x1EA5,
    0xCB: 0x1EAD,
    0xCC: 0x00E8,
    0xCE: 0x1EBB,
    0xCF: 0x1EBD,
    0xD0: 0x00E9,
    0xD1: 0x1EB9,
    0xD2: 0x1EC1,
    0xD3: 0x1EC3,
    0xD4: 0x1EC5,
    0xD5: 0x1EBF,
    0xD6: 0x1EC7,
    0xD7: 0x00EC,
    0xD8: 0x1EC9,
    0xDC: 0x0129,
    0xDD: 0x00ED,
    0xDE: 0x1ECB,
    0xDF: 0x00F2,
    0xE1: 0x1ECF,
    0xE2: 0x00F5,
    0xE3: 0x00F3,
    0xE4: 0x1ECD,
    0xE5: 0x1ED3,
    0xE6: 0x1ED5,
    0xE7: 0x1ED7,
    0xE8: 0x1ED1,
    0xE9: 0x1ED9,
    0xEA: 0x1EDD,
    0xEB: 0x1EDF,
    0xEC: 0x1EE1,
    0xED: 0x1EDB,
    0xEE: 0x1EE3,
    0xEF: 0x00F9,
    0xF1: 0x1EE7,
    0xF2: 0x0169,
    0xF3: 0x00FA,
    0xF4: 0x1EE5,
    0xF5: 0x1EEB,
    0xF6: 0x1EED,
    0xF7: 0x1EEF,
    0xF8: 0x1EE9,
    0xF9: 0x1EF1,
    0xFA: 0x1EF3,
    0xFB: 0x1EF7,
    0xFC: 0x1EF9,
    0xFD: 0x00FD,
    0xFE: 0x1EF5,
}
_VNI: dict[str, int] = {
    "\x41\xd8": 0x00C0,
    "\x41\xd9": 0x00C1,
    "\x41\xc2": 0x00C2,
    "\x41\xd5": 0x00C3,
    "\x45\xd8": 0x00C8,
    "\x45\xd9": 0x00C9,
    "\x45\xc2": 0x00CA,
    "\xcc": 0x00CC,
    "\xcd": 0x00CD,
    "\x4f\xd8": 0x00D2,
    "\x4f\xd9": 0x00D3,
    "\x4f\xc2": 0x00D4,
    "\x4f\xd5": 0x00D5,
    "\x55\xd8": 0x00D9,
    "\x55\xd9": 0x00DA,
    "\x59\xd9": 0x00DD,
    "\x61\xf8": 0x00E0,
    "\x61\xf9": 0x00E1,
    "\x61\xe2": 0x00E2,
    "\x61\xf5": 0x00E3,
    "\x65\xf8": 0x00E8,
    "\x65\xf9": 0x00E9,
    "\x65\xe2": 0x00EA,
    "\xec": 0x00EC,
    "\xed": 0x00ED,
    "\x6f\xf8": 0x00F2,
    "\x6f\xf9": 0x00F3,
    "\x6f\xe2": 0x00F4,
    "\x6f\xf5": 0x00F5,
    "\x75\xf8": 0x00F9,
    "\x75\xf9": 0x00FA,
    "\x79\xf9": 0x00FD,
    "\x41\xca": 0x0102,
    "\x61\xea": 0x0103,
    "\xd1": 0x0110,
    "\xf1": 0x0111,
    "\xd3": 0x0128,
    "\xf3": 0x0129,
    "\x55\xd5": 0x0168,
    "\x75\xf5": 0x0169,
    "\xd4": 0x01A0,
    "\xf4": 0x01A1,
    "\xd6": 0x01AF,
    "\xf6": 0x01B0,
    "\x41\xcf": 0x1EA0,
    "\x61\xef": 0x1EA1,
    "\x41\xdb": 0x1EA2,
    "\x61\xfb": 0x1EA3,
    "\x41\xc1": 0x1EA4,
    "\x61\xe1": 0x1EA5,
    "\x41\xc0": 0x1EA6,
    "\x61\xe0": 0x1EA7,
    "\x41\xc5": 0x1EA8,
    "\x61\xe5": 0x1EA9,
    "\x41\xc3": 0x1EAA,
    "\x61\xe3": 0x1EAB,
    "\x41\xc4": 0x1EAC,
    "\x61\xe4": 0x1EAD,
    "\x41\xc9": 0x1EAE,
    "\x61\xe9": 0x1EAF,
    "\x41\xc8": 0x1EB0,
    "\x61\xe8": 0x1EB1,
    "\x41\xda": 0x1EB2,
    "\x61\xfa": 0x1EB3,
    "\x41\xdc": 0x1EB4,
    "\x61\xfc": 0x1EB5,
    "\x41\xcb": 0x1EB6,
    "\x61\xeb": 0x1EB7,
    "\x45\xcf": 0x1EB8,
    "\x65\xef": 0x1EB9,
    "\x45\xdb": 0x1EBA,
    "\x65\xfb": 0x1EBB,
    "\x45\xd5": 0x1EBC,
    "\x65\xf5": 0x1EBD,
    "\x45\xc1": 0x1EBE,
    "\x65\xe1": 0x1EBF,
    "\x45\xc0": 0x1EC0,
    "\x65\xe0": 0x1EC1,
    "\x45\xc5": 0x1EC2,
    "\x65\xe5": 0x1EC3,
    "\x45\xc3": 0x1EC4,
    "\x65\xe3": 0x1EC5,
    "\x45\xc4": 0x1EC6,
    "\x65\xe4": 0x1EC7,
    "\xc6": 0x1EC8,
    "\xe6": 0x1EC9,
    "\xd2": 0x1ECA,
    "\xf2": 0x1ECB,
    "\x4f\xcf": 0x1ECC,
    "\x6f\xef": 0x1ECD,
    "\x4f\xdb": 0x1ECE,
    "\x6f\xfb": 0x1ECF,
    "\x4f\xc1": 0x1ED0,
    "\x6f\xe1": 0x1ED1,
    "\x4f\xc0": 0x1ED2,
    "\x6f\xe0": 0x1ED3,
    "\x4f\xc5": 0x1ED4,
    "\x6f\xe5": 0x1ED5,
    "\x4f\xc3": 0x1ED6,
    "\x6f\xe3": 0x1ED7,
    "\x4f\xc4": 0x1ED8,
    "\x6f\xe4": 0x1ED9,
    "\xd4\xd9": 0x1EDA,
    "\xf4\xf9": 0x1EDB,
    "\xd4\xd8": 0x1EDC,
    "\xf4\xf8": 0x1EDD,
    "\xd4\xdb": 0x1EDE,
    "\xf4\xfb": 0x1EDF,
    "\xd4\xd5": 0x1EE0,
    "\xf4\xf5": 0x1EE1,
    "\xd4\xcf": 0x1EE2,
    "\xf4\xef": 0x1EE3,
    "\x55\xcf": 0x1EE4,
    "\x75\xef": 0x1EE5,
    "\x55\xdb": 0x1EE6,
    "\x75\xfb": 0x1EE7,
    "\xd6\xd9": 0x1EE8,
    "\xf6\xf9": 0x1EE9,
    "\xd6\xd8": 0x1EEA,
    "\xf6\xf8": 0x1EEB,
    "\xd6\xdb": 0x1EEC,
    "\xf6\xfb": 0x1EED,
    "\xd6\xd5": 0x1EEE,
    "\xf6\xf5": 0x1EEF,
    "\xd6\xcf": 0x1EF0,
    "\xf6\xef": 0x1EF1,
    "\x59\xd8": 0x1EF2,
    "\x79\xf8": 0x1EF3,
    "\xce": 0x1EF4,
    "\xee": 0x1EF5,
    "\x59\xdb": 0x1EF6,
    "\x79\xfb": 0x1EF7,
    "\x59\xd5": 0x1EF8,
    "\x79\xf5": 0x1EF9,
}

_NBSP = 0xA0  # passes through both converters: it is the same character in every encoding here


@dataclass(frozen=True)
class Unmapped:
    """A character with no entry in the table. Kept as-is in the output."""

    index: int  # code point index in the INPUT string (not the NFC output)
    char: str
    reason: str


@dataclass(frozen=True)
class Ambiguous:
    """A character converted with a documented caveat; `candidates` lists the plausible readings."""

    index: int  # code point index in the INPUT string (not the NFC output)
    char: str
    candidates: tuple[str, ...]
    reason: str


@dataclass
class ConversionResult:
    text: str  # NFC
    ambiguous: list[Ambiguous] = field(default_factory=list)
    unmapped: list[Unmapped] = field(default_factory=list)
    # True whenever any case ambiguity was reported (TCVN3 only): one flag for the caller to check.
    case_uncertain: bool = False
    # True when the input held combining marks (category Mn): it was NFD-decomposed upstream and
    # is not one-byte-per-char legacy text, so the conversion cannot be trusted.
    nfd_damaged: bool = False


_C0_PASSTHROUGH = frozenset({0x09, 0x0A, 0x0D})  # tab, LF, CR are whitespace, not VN1 capitals
_ASCII_LOWER_IN_CAPITAL_FONT = (
    "lowercase ASCII in a capital font: renders as capital in most .VnXxxH fonts, unverified"
)
_ASCII_LOWER_CASE_UNKNOWN = (
    "lowercase ASCII with unknown font case: renders as capital in a .VnXxxH capital font, "
    "unverified; pass capital_font to settle it"
)


def convert_legacy(
    text: str,
    encoding: Encoding,
    *,
    capital_font: bool | None = None,
) -> ConversionResult:
    """Convert legacy-encoded `text` to Unicode NFC. Unmapped characters are kept and reported.

    `capital_font` only matters for TCVN3. The toned bytes 0xB5-0xFE are the same bytes in the
    normal font (lowercase) and in the all-capital font (uppercase), and no source fixes how an
    all-capital font draws a-z or the marked bases 0xA8-0xAE. The output never silently mixes
    cases; every uncertain character is reported in `ambiguous` and `case_uncertain` is set:
      * True : the caller asserts an all-capital font. Toned letters and 0xA8-0xAE (ă â ê ô ơ ư
        đ) become uppercase. Lowercase ASCII a-z is NOT uppercased (unsourced) but each one is
        reported in `ambiguous`.
      * None (default, font unknown): toned letters, 0xA8-0xAE and lowercase ASCII a-z are
        output as lowercase and each is reported in `ambiguous`.
      * False: the caller asserts a normal font; lowercase, nothing reported.
    Which style names are capital fonts is a naming hint only (see `font_hint`); the caller
    must not guess either. VNI encodes case in the bytes; `capital_font` is ignored.
    Every `index` in the result refers to the input string, not the NFC output.
    """
    if encoding == "tcvn3":
        out, ambiguous, unmapped = _convert_tcvn3(text, capital_font)
    elif encoding == "vni":
        out, ambiguous, unmapped = _convert_vni(text)
    else:  # pyright: ignore[reportUnnecessaryComparison]
        raise ValueError(f"unsupported encoding {encoding!r}; expected 'tcvn3' or 'vni'")
    return ConversionResult(
        unicodedata.normalize("NFC", "".join(out)),
        ambiguous,
        unmapped,
        case_uncertain=bool(ambiguous),
        nfd_damaged=any(unicodedata.category(ch) == "Mn" for ch in text),
    )


def _convert_tcvn3(text: str, capital_font: bool | None) -> tuple[list[str], list[Ambiguous], list[Unmapped]]:
    out: list[str] = []
    ambiguous: list[Ambiguous] = []
    unmapped: list[Unmapped] = []
    for index, ch in enumerate(text):
        code = ord(ch)
        if "a" <= ch <= "z":
            out.append(ch)
            if capital_font is not False:
                reason = _ASCII_LOWER_IN_CAPITAL_FONT if capital_font else _ASCII_LOWER_CASE_UNKNOWN
                ambiguous.append(Ambiguous(index, ch, (ch, ch.upper()), reason))
        elif 0x01 <= code <= 0x17 and code not in _C0_PASSTHROUGH:
            unmapped.append(Unmapped(index, ch, _unmapped_reason(ch)))
            out.append(ch)
        elif code < 0x80 or code == _NBSP:
            out.append(ch)
        elif code in _TCVN3_MARKED_BASE:
            letter = chr(_TCVN3_MARKED_BASE[code])
            if code < 0xA8:  # Ă Â Ê Ô Ơ Ư Đ: uppercase in every TCVN3 font
                out.append(letter)
            elif capital_font is True:
                out.append(letter.upper())
            else:
                out.append(letter)
                if capital_font is None:
                    ambiguous.append(
                        Ambiguous(
                            index,
                            ch,
                            (letter, letter.upper()),
                            "marked lowercase base (0xA8-0xAE) with unknown font case: no source says "
                            "how a capital font draws it; pass capital_font to settle it",
                        )
                    )
        elif code in _TCVN3_TONED:
            lower = chr(_TCVN3_TONED[code])
            if capital_font is True:
                out.append(lower.upper())
            else:
                out.append(lower)
                if capital_font is None:
                    ambiguous.append(
                        Ambiguous(
                            index,
                            ch,
                            (lower, lower.upper()),
                            "TCVN3 toned letters share one byte between the normal (lowercase) and "
                            "the all-capital font; pass capital_font to settle it",
                        )
                    )
        else:
            unmapped.append(Unmapped(index, ch, _unmapped_reason(ch)))
            out.append(ch)
    return out, ambiguous, unmapped


def _convert_vni(text: str) -> tuple[list[str], list[Ambiguous], list[Unmapped]]:
    out: list[str] = []
    unmapped: list[Unmapped] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if i + 1 < n and text[i : i + 2] in _VNI:  # longest match first
            out.append(chr(_VNI[text[i : i + 2]]))
            i += 2
            continue
        if ch in _VNI:
            out.append(chr(_VNI[ch]))
        else:
            if ord(ch) >= 0x80 and ord(ch) != _NBSP:
                unmapped.append(Unmapped(i, ch, _unmapped_reason(ch)))
            out.append(ch)
        i += 1
    return out, [], unmapped


def _unmapped_reason(ch: str) -> str:
    code = ord(ch)
    if unicodedata.category(ch) == "Mn":
        return "combining mark: the input was NFD-decomposed upstream, not one-byte-per-char legacy text"
    if code > 0xFF:
        return "above U+00FF: not a legacy byte (already Unicode, or a cp1252 0x80-0x9F character)"
    if code < 0x20:
        return "C0 control byte: holds a capital in other TCVN 5712 tables (VN1), not mapped here"
    return "no table entry for this byte"


# Font-name conventions. Evidence (two independent witnesses each, see the research note):
#   ".Vn..."  -> TCVN3 : bogotiengviet.com "fontchu-bangma" (archived 2010) and mytour.vn
#   "VNI-..." -> VNI   : the same two pages
# Names with one weak witness or a conflicting one are deliberately "unknown": "Vn..." without
# the dot (mytour: Vietware X), "VH...", "SVN-..." (Vietware F), "UVF..." (Unicode).
_UNICODE_FONTS = frozenset({"times new roman", "arial", "tahoma", "courier new", "verdana"})
_FONT_FILE_SUFFIXES = (".ttf", ".otf", ".ttc")
# Style names that look like a legacy Vietnamese TrueType name: ".Vn..." or "Vn..." (dot optional,
# because the real sample has "VntimeH"), but not "VNI-..." (VNI keeps case in its bytes).
_LEGACY_STYLE = re.compile(r"\.?vn(?!i-)", re.IGNORECASE)


@dataclass(frozen=True)
class FontHint:
    """Hint from a text style: the encoding and whether it looks like an all-capital font."""

    encoding: FontEncoding
    capital_font: bool | None


def _clean_font_name(font_name: str) -> str:
    name = font_name.strip().lstrip("@")
    for suffix in _FONT_FILE_SUFFIXES:
        if name.casefold().endswith(suffix):
            name = name[: -len(suffix)]
    return name


def guess_encoding_from_font(font_name: str) -> FontEncoding:
    """Hint the text encoding from a font *name* (case-insensitive). Never proof.

    Rules, applied after trimming, dropping a leading "@" and one trailing ".ttf"/".otf"/".ttc":
    a name starting ".vn" is "tcvn3", starting "vni-" is "vni", a well-known Unicode family
    (Times New Roman, Arial, ...) is "unicode", anything else is "unknown".
    Only .ttf/.otf/.ttc are stripped; ".shx" is NOT. So ".VnTime.shx" returns "tcvn3" (the
    leading dot decides, the extension is ignored), while "vntimeh.shx", "romans.shx" and
    "VHAVAN.TTF" return "unknown" (no leading dot, or not a listed family). Whether real font
    files keep the leading dot is not validated.
    """
    name = _clean_font_name(font_name).casefold()
    if name.startswith(".vn"):
        return "tcvn3"
    if name.startswith("vni-"):
        return "vni"
    if name in _UNICODE_FONTS:
        return "unicode"
    return "unknown"


def font_hint(style_name: str, font_file: str | None = None) -> FontHint:
    """Hint encoding and capital-font status from a text style name and its font file name.

    `encoding`: `guess_encoding_from_font(style_name)`; only if that is "unknown" the font file
    name is tried the same way.

    `capital_font` comes from the STYLE NAME only: True when it looks like legacy Vietnamese
    (".Vn..." or "Vn...", dot optional) and ends with an uppercase "H"; False when it looks like
    that but has no H suffix; None otherwise. An all-lowercase name ending in "h" returns None,
    because lowercasing destroyed the suffix. So "VntimeH" gives encoding "unknown" (no dot) but
    capital_font True: the two answers are independent hints.

    This is an observed naming convention, NOT verified against any font specification or font
    file: treat the result as a hint and settle it with the engineer.

    Evidence (read-only look with ezdxf at dwg-lab/samples/converted/L3-complex/dwgshare-rc-projects/
    267_4-story_house_complete_project.dxf, untrusted data): style ".VnAvantH" uses font
    VHAVAN.TTF; style "VntimeH" uses vntimeh.shx; style "TKT_TieuDe" uses vntimeh.shx; the text
    'mÆt b»ng §ÞNH VÞ CéT T1' (bytes of "mặt bằng ĐỊNH VỊ CỘT T1" in TCVN3 capitals) uses
    ".VnAvantH". The file names VHAVAN.TTF and vntimeh.shx return "unknown" for the encoding
    (conservative); the engineer may decide to map "VH*" or "vn*.shx" file names. "TKT_TieuDe"
    reads the same vntimeh.shx but carries no H hint in its own name, so it returns None.
    """
    encoding = guess_encoding_from_font(style_name)
    if encoding == "unknown" and font_file is not None:
        encoding = guess_encoding_from_font(font_file)
    name = _clean_font_name(style_name)
    capital: bool | None = None
    if _LEGACY_STYLE.match(name):
        if name.endswith("H"):
            capital = True
        elif name == name.lower() and name.endswith("h"):
            capital = None
        else:
            capital = False
    return FontHint(encoding, capital)


# --- Unicode evidence -----------------------------------------------------------------------
# Legacy TCVN3 / VNI text is one byte per character, so as a string it only holds code points
# <= U+00FF, plus the cp1252 0x80-0x9F block when the file was decoded with cp1252. A Vietnamese
# letter outside that set therefore cannot come from a legacy font: the text is Unicode, whatever
# the font name says. Built byte by byte because cp1252 leaves 0x81, 0x8D, 0x8F, 0x90, 0x9D undefined.


def _cp1252_high_block() -> frozenset[int]:
    out: set[int] = set()
    for byte in range(0x80, 0xA0):
        try:
            out.add(ord(bytes([byte]).decode("cp1252")))
        except UnicodeDecodeError:
            continue
    return frozenset(out)


LEGACY_POSSIBLE_CODEPOINTS: frozenset[int] = frozenset(range(0x100)) | _cp1252_high_block()
# Vietnamese letters and tone marks outside LEGACY_POSSIBLE_CODEPOINTS: A-breve, D-stroke, O-horn,
# U-horn (both cases), the Latin Extended Additional block (U+1EA0-U+1EF9) and the five combining
# tone marks (grave, acute, tilde, hook above, dot below).
UNICODE_VIETNAMESE_EVIDENCE: frozenset[int] = frozenset(
    {0x0102, 0x0103, 0x0110, 0x0111, 0x01A0, 0x01A1, 0x01AF, 0x01B0, 0x0300, 0x0301, 0x0303, 0x0309, 0x0323}
    | set(range(0x1EA0, 0x1EFA))
)
assert UNICODE_VIETNAMESE_EVIDENCE.isdisjoint(LEGACY_POSSIBLE_CODEPOINTS)


def has_unicode_vietnamese(text: str) -> bool:
    """True when `text` holds a Vietnamese letter or tone mark that legacy single-byte text cannot hold."""
    return any(ord(ch) in UNICODE_VIETNAMESE_EVIDENCE for ch in text)


# --- lone surrogates -------------------------------------------------------------------------
# ezdxf reads undecodable bytes (a damaged or mis-converted file) as lone surrogates (U+DC80...). They
# cannot be written as UTF-8, so a JSON document holding one cannot be saved. Outputs replace them with
# U+FFFD and say so; callers flag the entries that held them.

_LONE_SURROGATE = re.compile("[\ud800-\udfff]")
REPLACEMENT_CHARACTER = "�"


def has_lone_surrogate(text: str) -> bool:
    return _LONE_SURROGATE.search(text) is not None


def scrub_surrogates(data: Any) -> tuple[Any, int]:
    """Copy of `data` (dicts, lists, tuples, strings) with every lone surrogate replaced by U+FFFD.

    Returns the copy and the number of characters replaced. Dict keys are scrubbed too.
    """
    count = 0

    def walk(value: Any) -> Any:
        nonlocal count
        if isinstance(value, str):
            clean, n = _LONE_SURROGATE.subn(REPLACEMENT_CHARACTER, value)
            count += n
            return clean
        if isinstance(value, dict):
            return {walk(k): walk(v) for k, v in cast("dict[Any, Any]", value).items()}
        if isinstance(value, list | tuple):
            return [walk(v) for v in cast("list[Any]", value)]
        return value

    return walk(data), count
