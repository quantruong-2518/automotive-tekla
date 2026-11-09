"""callouts: deterministic candidates for rebar callouts, steel labels, plates, bolts and member marks.

`extract_callouts(work_dir)` reads, for every DXF/DWG of `inventory.json`, its text index and sheets document
(`structure/<path>.sheets.json`; grids and levels documents are read only to know which texts another
extractor already claimed) and lists CANDIDATES. A candidate is text that looks like a notation; it is never
a decision. Nothing is computed from it: no quantity, length or weight, no unit conversion, no catalogue.

Rules (docs/research/vn-structural-drawing-conventions.md, "Parsing patterns (verified notations only)" and
"Ambiguous notations: must become engineer questions"; dwg-lab/references/02-steel/NOTES.md "Section
designations"):

  * `parsed` is filled ONLY when the text matches a notation the research marks verified; `rule` names the
    pattern and where the research verifies it. Otherwise `parsed` is null and `unparsed_reason` says why.
    `rule` is always set (for an unparsed candidate it names the detector that fired).
  * Patterns are the research patterns, searched inside each line of `display_text` with token guards (not
    glued to a neighbouring token) instead of anchored on the whole string, so `2Ø16 L=1800` gives two
    candidates. A line that holds an ambiguous notation never also yields its parts: `4Ø18 + 2Ø16` is ONE
    candidate (ambiguity `rebar_plus_join`), not `4Ø18` and `2Ø16`. Case-sensitive, as the research patterns.
  * `display_text` has `%%c` already expanded to U+00D8 by the text index; the diameter sign set is the
    research's (U+2300 is NOT in it). A literal diameter sign in a non-Unicode text is flagged
    (`diameter_sign_literal_non_unicode`): U+00D8 is also byte 0xD8 of single-byte code pages.
  * Tool wave 3, W1b (docs/research/diameter-glyph-u-grave.md): a character in diameter position that is
    not a verified diameter sign (`2ù20`, `ù14a150`, `2Þ16`, U+2300, U+2205) is an unparsed rebar callout
    with `unparsed_code` symbol_glyph_unverified, never decoded (`_GLYPH` says which shapes count). Such
    callouts joined by '+' or '/' (`2ù20+2ù18`, `2ù20/2ù18`) are ONE such candidate (review M2). A glyph
    before or between digits that no shape reads (bare `ù12`, `ù8@150`, a mark letter `Ô1`) is listed in
    `rejected` (`diameter_glyph_no_notation`): never a candidate, so a slab panel `Ô1` raises no question.
  * Precedence on a line (a character belongs to one candidate): ambiguous rebar forms, verified rebar
    forms, `L=`, grades, steel sections, plates, bolts, loose diameter-sign forms, glyphs. A line with no
    candidate whose whole text looks like a member mark is a `member_mark` (practice only, never verified).
  * Every unparsed candidate names its reason family in `unparsed_code`. Nothing that matched is dropped
    silently: a diameter sign no pattern reads, a mark-shaped sheet code and a mark-shaped text another
    extractor took are listed in `rejected` with a `reason_code`.
  * Confidence: min(rule cap, the text entry's own confidence). Caps: verified grammar from a grade-B source
    'medium'; unparsed, ambiguous and member marks 'low'. Any of
    these also forces 'low': case_uncertain text, unmapped characters, NFD damage, flags
    encoding_unknown_non_ascii, unicode_evidence_contradicts_font, knowledge_conflict,
    codepage_reencode_failed, mif_escape_not_decoded, unknown_special_code, mixed_fonts,
    inline_font_unknown.
  * Legacy-font gate (`text_gate.meaning_block_reason`): an entry whose meaning is blocked (non-ASCII text in
    an unknown, proposed or contradicted encoding) yields no candidate, not even a literal `4Ø16`. An entry
    that would have yielded one is listed verbatim in `blocked_entries` (entry id, reason), never read.
  * Sheets that are exact copies of an earlier sheet (`duplicate_of`) are not scanned (their texts would be
    counted twice); they are listed in `skipped_sheets`.
  * Texts another extractor claimed (title-block fields, grid bubble labels, level values) are never member
    marks. Provenance: `method` 'derived', `derived_from` the text entry's provenance, `file` the inventory
    path (relative to the input folder), `sheet` the printed sheet number or 'unknown'.

Questions. `callouts.json` holds no questions, only `question_counts` (per code: ambiguous notations, 1 for
legacy grades). `run_callouts` (`harness callouts <work_dir>`) writes `callouts-questions.json`:
`callout_ambiguous` and `grade_legacy_mapping` (blocking) as ONE question per (code, blocking flag, file)
with a stable key, a registry id and the engineer's answer (questions.py, intake schema kind 'questions').
Inside a `callout_ambiguous` question `subjects` lists the notations. A changed drawing gives new keys, so
these questions are asked again. Member mark prefixes (`member_mark_prefix_meaning`) are asked by
`harness marks` since tool wave 2 (fix 1b): an answer given to the question callouts raised before goes
stale once, at the next callouts run. Tool wave 3: `callout_unparsed` (blocking: lot specs cannot use the
texts) is ONE question per (file, unparsed_code) over the unparsed candidates no other question covers
(no ambiguity, no member mark, no legacy grade group); its subject names the code, its refs give the first
five examples in scan order and one `sheets` ref with the count per sheet, `count` is the true total.

Not covered (research ambiguous list): 5 circled bar marks, 8-10 sheet prefixes / axes / levels (other
extractors), 15 weld symbols, 17 laps and hooks; welds and electrodes are not detected at all.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tekla_harness.detect import sha256_file
from tekla_harness.questions import (
    CALLOUT_UNPARSED_CODE,
    QuestionsError,
    dump_json,
    load_ledger,
    question_group,
    questions_document,
    write_text_atomic,
)
from tekla_harness.schemas import validate
from tekla_harness.sheet_text import (
    EXIT_INVALID,
    EXIT_USAGE,
    SCHEMA_VERSION,
    STRUCTURE_DIR,
    LoadedFile,
    ReaderError,
    _details,
    _inside,
    load_file,
    load_inventory,
    printed_number,
    read_json,
    sheet_label,
    stale_warning,
)
from tekla_harness.sheets import text_box
from tekla_harness.text_gate import meaning_block_reason

MAX_REFS = 50  # refs listed per question; `count` is always the true total
MAX_PREFIX_REFS = 10
REF_TEXT_CHARS = 80
LINE_CHARS = 200

_ORDER = {"low": 0, "medium": 1, "high": 2}
KINDS = (
    "rebar_callout",
    "rebar_grade",
    "section_label",
    "steel_grade",
    "plate",
    "bolt",
    "member_mark",
)
LOW_FLAGS = frozenset(
    {
        "encoding_unknown_non_ascii",
        "unicode_evidence_contradicts_font",
        "knowledge_conflict",
        "codepage_reencode_failed",
        "mif_escape_not_decoded",
        "unknown_special_code",
        "mixed_fonts",
        "inline_font_unknown",
    }
)

# --- patterns (research "Parsing patterns" unless noted) ----------------------------------------------

DIA_CHARS = "\u00d8\u00f8\u03a6\u03d5\u03c6\u0424"  # O-stroke, o-stroke, Phi, phi (2), Cyrillic Ef
DIA = "(?:[" + DIA_CHARS + "]|%%[cC])"
_L = r"(?<![\w.,/+@=])"  # not glued to the token before
_R = r"(?![\w/+@=])"  # ... or to the token after
_NUM = r"\d+(?:[.,]\d+)?"
_X = r"\s*[xX\u00d7]\s*"
_RN = r"(?!\w|[.,]\d)"
_UNIT = r"(?:\d{1,3}\s*)?" + DIA + r"\s*\d{1,2}(?:\s*[aA@sS]\s*\d{2,3}(?:/\d{2,3})?)?"

_PLUS_JOIN = re.compile(_L + _UNIT + r"(?:\s*\+\s*" + _UNIT + r")+(?![\w/@=])")
_COUNT_BEFORE = re.compile(_L + r"\d{1,3}\s*" + DIA + r"\s*\d{1,2}\s*a\s*\d{2,3}(?:/\d{2,3})?" + _R)
_SPACING_SYMBOL = re.compile(
    _L + r"(?:\d{1,3}\s*)?" + DIA + r"\s*\d{1,2}\s*(?:@|[sSA])\s*\d{2,3}(?:/\d{2,3})?" + _R
)
_DIA_SPACING = re.compile(_L + DIA + r"\s*(?P<d>\d{1,2})\s*a\s*(?P<s1>\d{2,3})(?:/(?P<s2>\d{2,3}))?" + _R)
_COUNT_DIA = re.compile(_L + r"(?P<n>\d{1,3})\s*" + DIA + r"\s*(?P<d>\d{1,2})" + _R)
_LEN_EQ = re.compile(r"(?<![\w])L\s*=\s*\d+(?:[.,]\d+)?(?!\w)")
_LOOSE_DIA = re.compile(_L + r"(?:\d{1,3}\s*)?" + DIA + r"\s*\d{1,3}(?:\s*[aAsS@]\s*\d{1,4}(?:/\d{1,4})?)?")
# W1b (docs/research/diameter-glyph-u-grave.md): a character in diameter position that is not a verified
# diameter sign. A non-ASCII letter (not a diameter sign, not the mark letter Đ/đ) counts only in the two
# callout shapes, count + diameter or diameter + spacing (`2ù20`, `ù14a150`, `2Þ16`): a lone letter + number
# (`Ô1`) is no callout. The diameter-like symbols U+2300 and U+2205 (AutoCAD's Unicode for %%c, not in the
# research's verified set) count in any of those shapes or alone with a number.
_GLYPH_LETTER = r"(?=[^\x00-\x7f])(?![" + DIA_CHARS + r"Đđ])[^\W\d_]"
_GLYPH_SYMBOL = r"[⌀∅]"
_GLYPH_ANY = "(?:" + _GLYPH_LETTER + "|" + _GLYPH_SYMBOL + ")"
_GLYPH_SPACING = r"\s*a\s*\d{2,3}(?:/\d{2,3})?"
_GLYPH = re.compile(
    _L
    + r"(?:\d{1,3}\s*(?P<g1>"
    + _GLYPH_ANY
    + r")\s*\d{1,2}(?:"
    + _GLYPH_SPACING
    + r")?|(?P<g2>"
    + _GLYPH_ANY
    + r")\s*\d{1,2}"
    + _GLYPH_SPACING
    + r"|(?P<g3>"
    + _GLYPH_SYMBOL
    + r")\s*\d{1,2})"
    + _R
)
# review M2: glyph callouts joined by '+' or '/' (`2ù20+2ù18`, `2ù20/2ù18`), one candidate as their Ø twins
# (`_PLUS_JOIN`); each part has one of the `_GLYPH` shapes
_GLYPH_PART = (
    r"(?:\d{1,3}\s*"
    + _GLYPH_ANY
    + r"\s*\d{1,2}(?:"
    + _GLYPH_SPACING
    + r")?|"
    + _GLYPH_ANY
    + r"\s*\d{1,2}"
    + _GLYPH_SPACING
    + r"|"
    + _GLYPH_SYMBOL
    + r"\s*\d{1,2})"
)
_GLYPH_JOIN = re.compile(_L + _GLYPH_PART + r"(?:\s*[+/]\s*" + _GLYPH_PART + r")+(?![\w/@=])")
_GLYPH_CHAR = re.compile(_GLYPH_ANY)

_REBAR_GRADE = re.compile(r"\bCB(?P<ys>240|300|400|500|600)-?(?P<surf>[TV])\b")
_LEGACY = re.compile(r"\b(?P<p>C|A-?)(?P<g>I{1,3}|IV)\b")
_STEEL_VN = re.compile(r"\b(?P<prefix>CCT|XCT)\s?(?P<n>34|38|42|52)(?P<sfx>Mn|MN)?\b")
_STEEL_FOREIGN = re.compile(
    r"\b(?:SS(?:330|400|490|540)|Q(?:235|345|390)[A-D]?|S(?:235|275|355|460)(?:JR|J0|J2)?)\b"
)
_VN_STEEL_PREFIX = re.compile(r"\b(?:CCT|XCT)\s?\d{2}")  # near-miss detector (CCT52, XCT 40, ...)

_UB = re.compile(
    _L + r"(?P<d>\d{3})" + _X + r"(?P<w>\d{2,3})" + _X + r"(?P<m>\d{2,3}(?:\.\d+)?)\s*(?P<s>UB)" + _RN
)
_QTY_ANGLE = re.compile(  # 2 L 65 x 8
    _L + r"(?:(?P<n>\d+)\s*)?(?P<l>[LV])\s*(?P<a>\d+)" + _X + r"(?P<t>\d+)" + _RN
)
_ANGLE_ANY = re.compile(_L + r"(?:\d+\s*)?[LV]\s*" + _NUM + r"(?:" + _X + _NUM + r"){1,2}" + _RN)
_H_SERIES = re.compile(_L + r"H\s*-?\s*" + _NUM + r"(?:" + _X + _NUM + r"){1,3}" + _RN)
_OTHER_SERIES = re.compile(
    _L
    + r"(?:(?:HE[ABM]|IPE|IPN|UPN)\s*\d{2,4}"
    + r"|\d{3}\s*[xX]\s*\d{2,3}\s*[xX]\s*\d{2,3}(?:\.\d+)?\s*UC"
    + r"|H[WMN]\s*\d{2,3}(?:\s*[xX]\s*\d{2,3})?"
    + r"|W\d{1,2}\s*[xX]\s*\d{2,3}"
    + r"|HSS\s*\d+(?:\.\d+)?\s*[xX]\s*\d+(?:\.\d+)?(?:\s*[xX]\s*\d+(?:\.\d+)?)?)"
    + _RN
)
_NUMBERED = re.compile(_L + r"(?:I\s?\d{2,3}[a-c]?|[UC]\s?\d{3})" + _RN)

_PLATE = re.compile(
    _L + r"(?P<tag>(?i:PL|BM|T\u1ea4M))\.?\s*[-:]?\s*(?P<dims>" + _NUM + r"(?:" + _X + _NUM + r"){0,3})" + _RN
)

_M_SIZE = re.compile(r"(?<![^\W\d_])M(?P<d>8|10|12|14|16|18|20|22|24|27|30|33|36|39|42|48)(?!\w)")
_BOLT_CLASS = re.compile(r"(?<![\d.])(?:4\.6|5\.6|5\.8|8\.8|10\.9|12\.9)(?![\d.])")
_BOLT_WORD = re.compile(r"(?i:\bbolts?\b|\bbu\s*-?\s*l[o\u00f4]ng\b|\bbulong\b)")
_HOLE = re.compile(r"(?<!\w)(?i:l[o\u1ed7])\s*" + DIA + r"\s*\d{2}(?!\w)")

_MARK = re.compile(r"^(?P<prefix>[A-Z\u0110]{1,3})\s?-?\s?(?P<number>\d{1,3})(?P<suffix>[a-z']?)$")
_MARK_CI = re.compile(_MARK.pattern, re.IGNORECASE)
_SHEET_CODE = re.compile(r"^(?P<disc>KT|KC|\u0110|N|TCXD)\s*-?\s*\d{1,3}(?:\s*/\s*\d{1,3})?$")

_CITE = "docs/research/vn-structural-drawing-conventions.md"

# unparsed_code (tool wave 3): the reason family of an unparsed candidate (callouts schema)
AMBIGUOUS = "ambiguous_notation"
GRADE_UNVERIFIED = "grade_unverified"
NOTATION_UNVERIFIED = "notation_unverified"
CONFLICTING = "conflicting_values"
MARK_UNDEFINED = "member_mark_undefined"
SYMBOL_GLYPH = "symbol_glyph_unverified"

# ambiguity id -> (blocking, notation text, message)
AMBIGUITIES: dict[str, tuple[bool, str]] = {
    "rebar_plus_join": (
        True,
        "A bar callout joins several bar groups with '+' (e.g. 4Ø18 + 2Ø16). One layer or two? Which face? "
        "Lapped or in the same section? (research, ambiguous #1)",
    ),
    "rebar_count_before_spacing": (
        True,
        "A count stands in front of a spacing form (e.g. 13Ø8a100). Number of stirrups in the zone, number "
        "of bars, or something else? (research, ambiguous #2)",
    ),
    "bar_length_l_equals": (
        True,
        "'L=' followed by a number (e.g. L=1800). Length of one bar? With hooks? Which unit? "
        "(research, ambiguous #3)",
    ),
    "rebar_spacing_symbol": (
        True,
        "Spacing written with '@', 's' or a capital 'A' instead of the lowercase 'a' of the verified form. "
        "Is it the spacing, in mm? (research, ambiguous #4)",
    ),
    "section_designation": (
        True,
        "Steel section label (e.g. H300x150x6.5x9, I300, U200, C200, L100x100x10, HEA 300, W14x90): field "
        "order and catalogue (TCVN 7571, JIS, GB/T, EN, AISC or a supplier) are not stated by the label. "
        "Which catalogue does the project use? (research, ambiguous #12)",
    ),
    "plate_designation": (
        True,
        "Plate label (PL, BM, TAM): thickness, width and length field order is not verified; take the sizes "
        "from the item list or the detail. (research, ambiguous #13)",
    ),
    "bolt_label_hole": (
        True,
        "Bolt label without a verified strength class, or a hole diameter (M20, 'lỗ Ø22'): strength class, "
        "hole size, standard or oversize, pretension, shear plane in the thread. 'M' may also be a footing "
        "mark. (research, ambiguous #14 and #11)",
    ),
    "rebar_grade_edition": (
        False,
        "CB grades name only the strength class: which edition of TCVN 1651 (2008 or 2018) does the project "
        "buy to? (research, ambiguous #7)",
    ),
    "steel_grade_standard_mix": (
        False,
        "Steel grade names from different standards (CCT, XCT, SS, Q, S) on one sheet. Which standard and "
        "edition? There is no automatic equivalence. (research, ambiguous #16)",
    ),
}

# --- candidate hits ----------------------------------------------------------------------------------


@dataclass
class _Hit:
    kind: str
    start: int
    end: int
    rule: str
    cap: str
    parsed: dict[str, Any] | None = None
    reason: str | None = None
    ambiguity: str | None = None
    family: str | None = None
    lexical: dict[str, str] | None = None
    derived_flags: tuple[str, ...] = ()
    code: str | None = None  # unparsed_code (UNPARSED_CODES) of an unparsed hit; None when parsed


class _Line:
    """Spans already claimed on one line, and the hits that claimed them."""

    def __init__(self, case_uncertain: bool = False) -> None:
        self.case_uncertain = case_uncertain
        self.spans: list[tuple[int, int]] = []
        self.hits: list[_Hit] = []

    def free(self, start: int, end: int) -> bool:
        return all(end <= a or start >= b for a, b in self.spans)

    def add(self, hit: _Hit) -> None:
        self.spans.append((hit.start, hit.end))
        self.hits.append(hit)


def _num(text: str) -> int | float:
    value = float(text.replace(",", "."))
    return int(value) if value.is_integer() else value


def _cite(pattern: str, where: str) -> str:
    return f"{pattern} ({_CITE}: {where})"


def _unparsed(
    kind: str, m: re.Match[str], rule: str, reason: str, code: str, ambiguity: str | None = None
) -> _Hit:
    return _Hit(kind, m.start(), m.end(), rule, "low", None, reason, ambiguity, code=code)


def _parsed(kind: str, m: re.Match[str], rule: str, cap: str, parsed: dict[str, Any], **extra: Any) -> _Hit:
    return _Hit(kind, m.start(), m.end(), rule, cap, parsed, **extra)


_B = "Parsing patterns 1, section 1.1, verified at grade B"
_Maker = Callable[[re.Match[str]], _Hit | None]


def _ambiguous_rebar(amb: str, item: int) -> _Maker:
    def make(m: re.Match[str]) -> _Hit:
        rule = _cite(f"AMBIG_{amb.upper()}", f"Ambiguous notations, #{item}")
        return _unparsed("rebar_callout", m, rule, f"ambiguous notation, not parsed: {amb}", AMBIGUOUS, amb)

    return make


def _dia_spacing(m: re.Match[str]) -> _Hit:
    parsed = {
        "form": "diameter_spacing",
        "diameter_mm": int(m["d"]),
        "spacing_mm": int(m["s1"]),
        "spacing_mid_mm": int(m["s2"]) if m["s2"] else None,
    }
    return _parsed("rebar_callout", m, _cite("DIA_SPACING", _B), "medium", parsed)


def _count_dia(m: re.Match[str]) -> _Hit:
    parsed = {"form": "count_diameter", "count": int(m["n"]), "diameter_mm": int(m["d"])}
    return _parsed("rebar_callout", m, _cite("COUNT_DIA", _B), "medium", parsed)


_GRADES = {("T", 240), ("T", 300), ("T", 400), ("V", 300), ("V", 400), ("V", 500), ("V", 600)}


def _rebar_grade(m: re.Match[str]) -> _Hit:
    rule = _cite("REBAR_GRADE", "Parsing patterns 2, section 1.3")
    if (m["surf"], int(m["ys"])) not in _GRADES:
        reason = "this strength class and surface letter pair is not in the verified grade list (section 1.3)"
        return _Hit("rebar_grade", m.start(), m.end(), rule, "low", None, reason, code=GRADE_UNVERIFIED)
    parsed = {
        "form": "rebar_grade",
        "yield_class_mpa": int(m["ys"]),
        "letter": m["surf"],
        "surface": "plain" if m["surf"] == "T" else "ribbed",
    }
    return _parsed("rebar_grade", m, rule, "medium", parsed, ambiguity="rebar_grade_edition")


def _legacy(m: re.Match[str]) -> _Hit:
    rule = _cite(
        "LEGACY_GROUP", "Parsing patterns 2, section 1.3, TCVN 5574:2012 5.2.1.1; never map automatically"
    )
    if m["p"] == "A":
        reason = "spelling without a hyphen (AI, AII, AIII) is in no standard (section 1.3)"
        return _Hit("rebar_grade", m.start(), m.end(), rule, "low", None, reason, code=GRADE_UNVERIFIED)
    family = "CI..CIV (TCVN 1651:1985)" if m["p"] == "C" else "A-I..A-IV (imported Russian groups)"
    return _parsed(
        "rebar_grade", m, rule, "medium", {"form": "legacy_group", "family": family, "group": m["g"]}
    )


def _steel_vn(m: re.Match[str]) -> _Hit:
    rule = _cite("STEEL_VN", "Parsing patterns 5, section 5.4, TCXDVN 338:2005")
    prefix, number = m["prefix"], m["n"]
    if prefix == "CCT" and number == "52":
        reason = "CCT52 is not in the verified list (CCT34, CCT38, CCT42)"
        return _Hit(
            "steel_grade", m.start(), m.end(), rule, "low", None, reason, family=prefix, code=GRADE_UNVERIFIED
        )
    parsed = {
        "form": "steel_grade_vn",
        "prefix": prefix,
        "number": int(number),
        "suffix": "Mn" if m["sfx"] else None,
        "standard": "TCVN 1765:1975" if prefix == "CCT" else "TCVN 5709:1993",
    }
    return _parsed("steel_grade", m, rule, "medium", parsed, family=prefix)


def _steel_vn_near_miss(m: re.Match[str]) -> _Hit:
    rule = _cite("STEEL_VN", "Parsing patterns 5, section 5.4")
    reason = "CCT/XCT followed by a number outside the verified list (CCT34/38/42, XCT34/38/42/52)"
    family = m.group(0)[:3]
    return _Hit(
        "steel_grade", m.start(), m.end(), rule, "low", None, reason, family=family, code=GRADE_UNVERIFIED
    )


def _steel_foreign(m: re.Match[str]) -> _Hit:
    name = m.group(0)
    family = "JIS" if name.startswith("SS") else "GB" if name.startswith("Q") else "EN"
    rule = _cite("STEEL_FOREIGN", "Parsing patterns 5, section 5.4 (informative table)")
    return _parsed(
        "steel_grade", m, rule, "medium", {"form": "steel_grade_foreign", "name": name}, family=family
    )


def _ub(m: re.Match[str]) -> _Hit:
    parsed = {
        "form": "ub",
        "series": m["s"],
        "nominal_depth_mm": int(m["d"]),
        "nominal_width_mm": int(m["w"]),
        "mass_kg_per_m": _num(m["m"]),
    }
    rule = _cite("UB", "dwg-lab/references/02-steel/NOTES.md 'Section designations', UB table verified (B)")
    return _parsed("section_label", m, rule, "medium", parsed)


def _qty_angle(m: re.Match[str]) -> _Hit:
    parsed = {
        "form": "angle",
        "count": int(m["n"]) if m["n"] else None,
        "letter": m["l"],
        "leg_mm": int(m["a"]),
        "thickness_mm": int(m["t"]),
    }
    rule = _cite("QTY_ANGLE", "Parsing patterns 7, section 5.2, TCVN 2234 form '2 L 65 x 8'")
    return _parsed("section_label", m, rule, "medium", parsed)


def _section_unverified(rule_id: str, why: str) -> _Maker:
    def make(m: re.Match[str]) -> _Hit:
        rule = _cite(rule_id, "section 5.2, NOTES.md 'Section designations', ambiguous #12")
        return _unparsed("section_label", m, rule, why, NOTATION_UNVERIFIED, "section_designation")

    return make


def _plate(m: re.Match[str]) -> _Hit:
    if re.search(r"[xX\u00d7]", m["dims"]):
        why = "plate size: thickness x width x length field order is unverified (use the item list)"
    else:
        why = "plate tag with a number (mark or thickness): no verified form"
    rule = _cite("PLATE_TAG", "section 5.2, NOTES.md 'Plates', ambiguous #13")
    return _unparsed("plate", m, rule, why, NOTATION_UNVERIFIED, "plate_designation")


def _loose_dia(m: re.Match[str]) -> _Hit:
    rule = _cite("LOOSE_DIAMETER", "Parsing patterns 1: no verified form matches")
    why = "diameter sign with a number, outside the verified forms (count + diameter, diameter + spacing)"
    return _unparsed("rebar_callout", m, rule, why, NOTATION_UNVERIFIED)


def _glyph(m: re.Match[str]) -> _Hit:
    glyph = m["g1"] or m["g2"] or m["g3"]
    rule = (
        "SYMBOL_GLYPH (docs/research/diameter-glyph-u-grave.md: a character that is not a verified diameter "
        "sign stands in diameter position; never decoded)"
    )
    why = (
        f"the character '{glyph}' (U+{ord(glyph):04X}) stands where a diameter sign stands (count + diameter "
        "or diameter + spacing), but it is not \u00d8 or %%c: never decoded, the meaning depends on a font "
        "nobody verified (research note diameter-glyph-u-grave.md)"
    )
    return _unparsed("rebar_callout", m, rule, why, SYMBOL_GLYPH)


def _glyph_join(m: re.Match[str]) -> _Hit:
    found = _GLYPH_CHAR.search(m.group(0))
    assert found is not None  # every part holds a glyph
    glyph = found.group(0)
    rule = (
        "SYMBOL_GLYPH_JOIN (docs/research/diameter-glyph-u-grave.md: bar groups joined by '+' or '/' with a "
        "character that is not a verified diameter sign in diameter position; never decoded)"
    )
    why = (
        f"bar groups joined by '+' or '/' where the character '{glyph}' (U+{ord(glyph):04X}) stands where a "
        "diameter sign stands, but it is not Ø or %%c: never decoded, the meaning depends on a font "
        "nobody verified (research note diameter-glyph-u-grave.md); with Ø the join itself is ambiguous"
    )
    return _unparsed("rebar_callout", m, rule, why, SYMBOL_GLYPH)


def _hole(m: re.Match[str]) -> _Hit:
    rule = _cite("BOLT_HOLE", "section 5.3, ambiguous #14")
    why = "hole diameter notation ('lỗ Ø22'): hole size, standard or oversize unverified"
    return _unparsed("bolt", m, rule, why, NOTATION_UNVERIFIED, "bolt_label_hole")


def _pattern(rx: re.Pattern[str], make: _Maker, fold: bool = False) -> Callable[[str, _Line], None]:
    """`fold`: in a text whose case is a guess (capital fonts draw a-z as capitals) match on the upper-cased
    line; the spans still index the original line."""

    def scan(text: str, acc: _Line) -> None:
        if fold and acc.case_uncertain and len(text.upper()) == len(text):
            text = text.upper()
        for m in rx.finditer(text):
            if acc.free(m.start(), m.end()):
                hit = make(m)
                if hit is not None:
                    acc.add(hit)

    return scan


def _bolts(text: str, acc: _Line) -> None:
    """One candidate per line from its class / M-label tokens, plus one per hole notation."""
    sizes = [m for m in _M_SIZE.finditer(text) if acc.free(m.start(), m.end())]
    classes = [m for m in _BOLT_CLASS.finditer(text) if acc.free(m.start(), m.end())]
    context = bool(sizes) or bool(_BOLT_WORD.search(text))
    marks = sizes + classes
    if classes and context:
        values = sorted({m.group(0) for m in classes})
        start, end = min(m.start() for m in marks), max(m.end() for m in marks)
        rule = _cite("BOLT_CLASS", "Parsing patterns 6, section 5.3, TCXDVN 338:2005 4.2.3 and draft 5575")
        if len(values) == 1:
            label = sizes[0].group(0) if sizes else None
            parsed = {"form": "bolt_class", "strength_class": values[0], "thread_label": label}
            acc.add(_Hit("bolt", start, end, rule, "medium", parsed))
        else:
            why = f"several strength classes on one line: {', '.join(values)}"
            acc.add(_Hit("bolt", start, end, rule, "low", None, why, "bolt_label_hole", code=CONFLICTING))
    elif sizes:
        rule = _cite("BOLT_M_LABEL", "section 5.3, ambiguous #14")
        why = "bolt diameter label (M20...) without a verified strength class on the line"
        start, end = sizes[0].start(), sizes[-1].end()
        acc.add(_Hit("bolt", start, end, rule, "low", None, why, "bolt_label_hole", code=NOTATION_UNVERIFIED))
    _pattern(_HOLE, _hole)(text, acc)


_AMBIG_ITEM = {"rebar_plus_join": 1, "rebar_count_before_spacing": 2, "rebar_spacing_symbol": 4}
_SCANNERS: tuple[Callable[[str, _Line], None], ...] = (
    *(
        _pattern(rx, _ambiguous_rebar(amb, _AMBIG_ITEM[amb]))
        for rx, amb in (
            (_PLUS_JOIN, "rebar_plus_join"),
            (_COUNT_BEFORE, "rebar_count_before_spacing"),
            (_SPACING_SYMBOL, "rebar_spacing_symbol"),
        )
    ),
    _pattern(_DIA_SPACING, _dia_spacing),
    _pattern(_COUNT_DIA, _count_dia),
    _pattern(_LEN_EQ, _ambiguous_rebar("bar_length_l_equals", 3)),
    _pattern(_REBAR_GRADE, _rebar_grade, fold=True),
    _pattern(_LEGACY, _legacy, fold=True),
    _pattern(_STEEL_VN, _steel_vn, fold=True),
    _pattern(_VN_STEEL_PREFIX, _steel_vn_near_miss, fold=True),
    _pattern(_STEEL_FOREIGN, _steel_foreign, fold=True),
    _pattern(_UB, _ub),
    _pattern(_QTY_ANGLE, _qty_angle),
    _pattern(
        _ANGLE_ANY,
        _section_unverified(
            "ANGLE_UNVERIFIED_FORM",
            "angle other than 'L a x t' (three numbers or decimals): field order unverified",
        ),
    ),
    _pattern(
        _H_SERIES,
        _section_unverified(
            "H_SERIES", "H-section 'H d x b x tw x tf': field order is JIS general knowledge, unverified"
        ),
    ),
    _pattern(
        _OTHER_SERIES,
        _section_unverified(
            "SERIES_LABEL",
            "series label (HEA/HEB/IPE/HW/HN/W/HSS...): catalogue and field meaning unverified",
        ),
    ),
    _pattern(
        _NUMBERED,
        _section_unverified(
            "NUMBERED_SECTION",
            "numbered I/U/C section: the number's meaning is unverified; C/U/I may also be a member mark",
        ),
    ),
    _pattern(_PLATE, _plate),
    _bolts,
    _pattern(_LOOSE_DIA, _loose_dia),
    _pattern(_GLYPH_JOIN, _glyph_join),
    _pattern(_GLYPH, _glyph),
)


def scan_line(line: str, case_uncertain: bool = False) -> list[_Hit]:
    """All candidates of one line, in order of position. In a case-uncertain text only the grade names
    (rebar and steel) are matched case-insensitively; every other pattern stays case-sensitive."""
    acc = _Line(case_uncertain)
    for scan in _SCANNERS:
        scan(line, acc)
    return sorted(acc.hits, key=lambda h: (h.start, h.end))


def member_mark(line: str, case_uncertain: bool) -> _Hit | None:
    text = line.strip()
    m = (_MARK_CI if case_uncertain else _MARK).match(text)
    if m is None or is_sheet_code(text, case_uncertain):
        return None  # a sheet code (research parsing pattern 3) is not a member
    lexical = {"prefix": m["prefix"].upper(), "number": m["number"], "suffix": m["suffix"]}
    rule = _cite("MEMBER_MARK_SHAPE", "section 4: practice only, no standard defines the letters")
    why = "member mark letters are not defined by any standard or by this drawing's legend yet (section 4)"
    return _Hit("member_mark", 0, len(line), rule, "low", None, why, lexical=lexical, code=MARK_UNDEFINED)


def is_sheet_code(line: str, case_uncertain: bool) -> bool:
    """The whole line has a member mark's shape but is a sheet code (research parsing pattern 3)."""
    text = line.strip()
    if (_MARK_CI if case_uncertain else _MARK).match(text) is None:
        return False
    code = _SHEET_CODE.match(text.upper() if case_uncertain else text)
    return bool(code and (code["disc"] in ("KT", "KC", "TCXD") or "-" in text or "/" in text))


# --- one text entry -----------------------------------------------------------------------------------

# rejected[] reason codes: text that matched a candidate pattern and is no candidate (callouts schema)
NO_NOTATION = "diameter_sign_no_notation"
GLYPH_NO_NOTATION = "diameter_glyph_no_notation"
SHEET_CODE = "sheet_code"
REJECT_REASONS = {
    NO_NOTATION: "a diameter sign that no callout pattern reads: no number right after it, or glued to the "
    "token before or after it",
    GLYPH_NO_NOTATION: "a character that is not a verified diameter sign stands in diameter position (a "
    "letter alone before a number or between numbers, U+2300 / U+2205 anywhere) but no callout shape reads "
    "it (bare 'ù12', 'ù8@150'; or a mark letter such as 'Ô1'): never decoded (research note "
    "diameter-glyph-u-grave.md)",
    SHEET_CODE: "the whole text is a sheet code (research parsing pattern 3), not a member mark",
    "claimed_by_title_block": "the title-block extractor took this text as a field value or label",
    "claimed_by_grids": "the grid extractor took this text (a grid bubble label)",
    "claimed_by_levels": "the level extractor took this text (a level value)",
}
_DIA_SIGN = re.compile("[" + DIA_CHARS + "]")
_TOKEN = re.compile(r"\S+")


def _uncovered_signs(line: str, hits: list[_Hit]) -> list[str]:
    """The line's tokens (whitespace-separated) holding a diameter sign that no hit covers, in order."""
    out = []
    for tok in _TOKEN.finditer(line):
        for sign in _DIA_SIGN.finditer(line, tok.start(), tok.end()):
            if not any(h.start <= sign.start() < h.end for h in hits):
                out.append(tok.group(0))
                break
    return out


# a glyph letter with no letter before it (not the end of a word: 'là 20', 'lÀ9' stay out; a letter after
# it is ruled out by the digit `_uncovered_glyphs` asks for)
_LONE_GLYPH = re.compile(r"(?<![^\W\d_])(?:" + _GLYPH_LETTER + r")|" + _GLYPH_SYMBOL)


def _uncovered_glyphs(line: str, hits: list[_Hit]) -> list[str]:
    """Review M2: the line's tokens holding a glyph in diameter position that no hit covers, in order. A
    glyph letter counts when a digit follows it directly ('ù12'), or a digit precedes it directly and one
    follows after optional blanks ('2ù 20'); U+2300 / U+2205 count anywhere (as a diameter sign)."""
    out = []
    for tok in _TOKEN.finditer(line):
        for g in _LONE_GLYPH.finditer(line, tok.start(), tok.end()):
            i = g.start()
            symbol = g.group(0) in "⌀∅"
            follows = line[i + 1 : i + 2].isdigit()
            between = i > 0 and line[i - 1].isdigit() and line[i + 1 :].lstrip()[:1].isdigit()
            if (symbol or follows or between) and not any(h.start <= i < h.end for h in hits):
                out.append(tok.group(0))
                break
    return out


def _confidence(cap: str, entry: dict[str, Any], extra_flags: tuple[str, ...]) -> str:
    conf = min(cap, entry["confidence"], key=_ORDER.__getitem__)
    dec = entry["decode"]
    low = (
        dec["case_uncertain"]
        or dec["unmapped_count"] > 0
        or dec["nfd_damaged"]
        or bool(LOW_FLAGS.intersection(entry["flags"]))
        or bool(extra_flags)
    )
    return "low" if low else conf


_BARE_M = re.compile(r"^M(?P<n>\d{1,2})$")


def footing_m_labels(entries: list[dict[str, Any]], sheet_of: dict[str, dict[str, Any]]) -> set[str]:
    """Ids of texts that are a whole `M<n>` with a bolt size n (which the bolt pattern reads as a bolt
    label) but stand in a family of `M` marks: the same sheet (or, for texts on no sheet, the same no-sheet
    group) holds a whole `M<n-1>` or `M<n+1>` that is no bolt size, in the same text style and height.
    EVAL-3 R arm, 433 model#01: footings M1..M7 and T000555 `M8`. Such a text is a member mark."""
    groups: dict[tuple[str | None, str | None, float | None], dict[int, list[str]]] = {}
    bolt: dict[int, bool] = {}
    for e in entries:
        m = _BARE_M.match(e["display_text"].strip())
        if m is None:
            continue
        sheet = sheet_of.get(e["id"])
        key = (None if sheet is None else sheet["sheet_id"], e["style"], e["height"])
        n = int(m["n"])
        bolt[n] = bolt.get(n, False) or _M_SIZE.fullmatch("M" + m["n"]) is not None
        groups.setdefault(key, {}).setdefault(n, []).append(e["id"])
    out: set[str] = set()
    for numbers in groups.values():
        for n, ids in numbers.items():
            if bolt[n] and any(k in numbers and not bolt[k] for k in (n - 1, n + 1)):
                out.update(ids)
    return out


def _entry_hits(
    entry: dict[str, Any], claimed_by: str | None, as_mark: bool = False
) -> tuple[list[tuple[str, _Hit]], list[tuple[str, str, str]]]:
    """(line, hit) for every candidate of the entry, lines in order, and what matched but is no candidate:
    (text, kind, reason code). `claimed_by`: the extractor that took the text (title_block, grids, levels);
    such a text is never a member mark. `as_mark`: a bolt-size `M<n>` of a footing family
    (`footing_m_labels`), read as a member mark only."""
    out: list[tuple[str, _Hit]] = []
    rejects: list[tuple[str, str, str]] = []
    dec = entry["decode"]
    cu = dec["case_uncertain"]
    literal_sign_unsafe = dec["encoding_used"] != "unicode" and "%%c" not in entry["special_codes"]
    for line in entry["display_text"].split("\n"):
        hits = [] if as_mark else scan_line(line, cu)
        if not hits:
            mark = member_mark(line, cu)
            if mark is not None and claimed_by is not None:
                rejects.append((line.strip(), "member_mark", f"claimed_by_{claimed_by}"))
            elif mark is not None:
                hits = [mark]
            elif is_sheet_code(line, cu):
                rejects.append((line.strip(), "member_mark", SHEET_CODE))
        rejects.extend((tok, "rebar_callout", NO_NOTATION) for tok in _uncovered_signs(line, hits))
        rejects.extend((tok, "rebar_callout", GLYPH_NO_NOTATION) for tok in _uncovered_glyphs(line, hits))
        for hit in hits:
            if literal_sign_unsafe and re.search("[" + DIA_CHARS + "]", line[hit.start : hit.end]):
                hit.derived_flags += ("diameter_sign_literal_non_unicode",)
            out.append((line, hit))
    return out, rejects


# the prefix of a mark-shaped text (marks.py's grammar, without the section): `gĐ-3`, `Đn - 05`, `GM1`
_FAMILY = re.compile(r"^(?P<prefix>[A-Za-zĐđ]{1,4})\s?-?\s?\d{1,3}(?:[.\-]\d{1,3})?[A-Za-z']?$")


def _family_key(entry: dict[str, Any]) -> tuple[str, str | None, float | None] | None:
    """(prefix casefolded, style, height) of a text whose whole text has a mark's shape, else None."""
    m = _FAMILY.match(entry["display_text"].strip())
    return None if m is None else (m["prefix"].casefold(), entry["style"], entry["height"])


def _released_pattern_values(loaded: LoadedFile) -> set[str]:
    """Value texts of title-block candidates found by shape alone (evidence kind `pattern`: the lower-right
    sheet-code fallback, no tag and no label) that belong to a mark family drawn on the same sheet: another
    text of the sheet that no title-block candidate took has the same prefix, style and height and a mark's
    shape (EVAL-3 286 model#04: `gĐ-3` next to `gĐ-1`, `gĐ-2`). Such a text is a member mark, not the sheet
    number, so it is not claimed. A printed sheet number found the same way (461 `Đn-05`, one per sheet)
    has no such family and stays claimed."""
    if loaded.sheets is None or loaded.text_index is None:
        return set()
    entries = {e["id"]: e for e in loaded.text_index["entries"]}
    out: set[str] = set()
    for sh in loaded.sheets["sheets"]:
        cands = sh["title_block"]["candidates"]
        taken = {c["evidence"]["value_text_id"] for c in cands} | {
            c["evidence"]["label_text_id"] for c in cands if c["evidence"]["label_text_id"]
        }
        families = {_family_key(entries[t]) for t in sh["text_ids"] if t in entries and t not in taken}
        families.discard(None)
        for c in cands:
            value = entries.get(c["evidence"]["value_text_id"])
            if c["evidence"]["kind"] == "pattern" and value is not None and _family_key(value) in families:
                out.add(value["id"])
    return out


def _claimed_text_ids(inv_work: Path, loaded: LoadedFile, warnings: list[str]) -> dict[str, str]:
    """Text ids that title-block, grid and level extraction already used, each with the extractor that
    took it first (title_block, grids, levels). A shape-only title-block candidate that belongs to a mark
    family is not claimed (`_released_pattern_values`)."""
    ids: dict[str, str] = {}
    released = _released_pattern_values(loaded)
    if loaded.sheets is not None:
        for sh in loaded.sheets["sheets"]:
            for cand in sh["title_block"]["candidates"]:
                ev = cand["evidence"]
                if ev["value_text_id"] not in released:
                    ids.setdefault(ev["value_text_id"], "title_block")
                if ev["label_text_id"]:
                    ids.setdefault(ev["label_text_id"], "title_block")

    def walk(node: Any, kind: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "text_id" and isinstance(value, str):
                    ids.setdefault(value, kind)
                else:
                    walk(value, kind)
        elif isinstance(node, list):
            for item in node:
                walk(item, kind)

    for kind in ("grids", "levels"):
        rel = f"{STRUCTURE_DIR}/{loaded.rel}.{kind}.json"
        path = _inside(inv_work, rel, f"{loaded.rel}: {kind} document")
        if not path.is_file():
            warnings.append(f"{loaded.rel}: {rel} is missing: its texts are not excluded from member marks")
            continue
        walk(read_json(path, f"{loaded.rel}: {rel}"), kind)  # not schema-checked: only text_id keys read
    return ids


# --- the whole work folder ----------------------------------------------------------------------------


def _provenance(rel: str, sheet: dict[str, Any] | None, entry: dict[str, Any]) -> dict[str, Any]:
    label = sheet_label(sheet)
    source: dict[str, Any] = {"file": rel, "sheet": label, "method": entry["provenance"]["method"]}
    outer: dict[str, Any] = {"file": rel, "sheet": label, "method": "derived"}
    revision = None if sheet is None else sheet["title_block"]["revision"]
    if revision is not None:
        source["revision"] = outer["revision"] = revision["value"]
    box = text_box(entry)
    if box is not None:
        source["region"] = {"bbox": [round(v, 6) for v in box]}
    outer["derived_from"] = [source]
    return outer


def _ref(c: dict[str, Any]) -> dict[str, Any]:
    text = " ".join(c["display_text"].split())
    cut = len(text) > REF_TEXT_CHARS
    return {
        "file": c["file"],
        "sheet": c["sheet"],
        "entry_id": c["text_ref"]["entry_id"],
        "text": text[:REF_TEXT_CHARS] + ("…" if cut else ""),
    }


LEGACY_GRADE_MESSAGE = (
    "Old reinforcement grade groups (CI..CIV, A-I..A-IV, AI..AIII) appear. The label gives "
    "neither yield strength nor product standard, and there is no official mapping to CB "
    "grades. Which grade, yield strength and standard does each group mean in this project? "
    "(research, ambiguous #6)"
)


def question_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    """Questions per code over the whole project: one `callout_ambiguous` per ambiguous notation, one
    `grade_legacy_mapping` when legacy grade groups appear. (`callouts-questions.json` splits them per file;
    this is the project-wide number asked.) Member mark prefixes are asked by `harness marks`."""
    counts = {
        "callout_ambiguous": len({c["ambiguity"] for c in candidates if c["ambiguity"]}),
        "grade_legacy_mapping": int(
            any(
                (c["parsed"] and c["parsed"]["form"] == "legacy_group")
                or (c["parsed"] is None and c["rule"].startswith("LEGACY_GROUP"))
                for c in candidates
            )
        ),
        CALLOUT_UNPARSED_CODE: len(
            {(c["file"], c["unparsed_code"]) for c in candidates if _asked_unparsed(c)}
        ),
    }
    return {code: n for code, n in counts.items() if n}


def _asked_unparsed(c: dict[str, Any]) -> bool:
    """An unparsed candidate no other question covers, so callout_unparsed asks it: not an ambiguous
    notation (callout_ambiguous), not a member mark (member_mark_prefix_meaning, harness marks), not a
    legacy grade group (grade_legacy_mapping)."""
    return (
        c["parsed"] is None
        and c["ambiguity"] is None
        and c["kind"] != "member_mark"
        and not c["rule"].startswith("LEGACY_GROUP")
    )


def _check(doc: dict[str, Any]) -> dict[str, Any]:
    problems = validate("callouts", doc)
    if problems:
        raise ReaderError(EXIT_INVALID, f"internal error: output is invalid: {_details(problems)}")
    return doc


def _summary(
    candidates: list[dict[str, Any]],
    files: list[dict[str, Any]],
    blocked: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
) -> dict[str, Any]:
    by_file: dict[str, Counter[str]] = {}
    by_sheet: dict[tuple[str, str | None], tuple[dict[str, str] | None, Counter[str]]] = {}
    for c in candidates:
        by_file.setdefault(c["file"], Counter())[c["kind"]] += 1
        by_sheet.setdefault((c["file"], c["sheet"]), (c["sheet_number"], Counter()))[1][c["kind"]] += 1
    parsed = sum(1 for c in candidates if c["parsed"] is not None)
    return {
        "candidates": len(candidates),
        "parsed": parsed,
        "unparsed": len(candidates) - parsed,
        "by_kind": {k: n for k, n in sorted(Counter(c["kind"] for c in candidates).items())},
        "by_confidence": {k: n for k, n in sorted(Counter(c["confidence"] for c in candidates).items())},
        "by_file": [
            {"file": f, "total": sum(k.values()), "by_kind": dict(sorted(k.items()))}
            for f, k in sorted(by_file.items())
        ],
        "by_sheet": [
            {
                "file": f,
                "sheet": s,
                "sheet_number": by_sheet[(f, s)][0],
                "total": sum(by_sheet[(f, s)][1].values()),
                "by_kind": dict(sorted(by_sheet[(f, s)][1].items())),
            }
            for f, s in sorted(by_sheet, key=lambda k: (k[0], k[1] is None, k[1] or ""))
        ],
        "member_mark_prefixes": len({c["lexical"]["prefix"] for c in candidates if c.get("lexical")}),
        "unparsed_by_reason": dict(
            sorted(Counter(c["unparsed_reason"] for c in candidates if c["parsed"] is None).items())
        ),
        "unparsed_by_code": dict(
            sorted(Counter(c["unparsed_code"] for c in candidates if c["parsed"] is None).items())
        ),
        "rejected": len(rejected),
        "rejected_by_reason": dict(sorted(Counter(r["reason_code"] for r in rejected).items())),
        "files_scanned": sum(1 for f in files if f["status"] == "scanned"),
        "files_skipped": sum(1 for f in files if f["status"] == "skipped"),
        "blocked_entries": len(blocked),
    }


def extract_callouts(work_dir: Path | str, *, check_inputs: bool = False) -> dict[str, Any]:
    """Callout candidates of every DXF/DWG of an intake work folder. Raises ReaderError.

    `check_inputs`: validate the text indexes and sheets documents against their schemas first (slow)."""
    inv = load_inventory(work_dir)
    warnings: list[str] = []
    stale = stale_warning(inv)
    if stale:
        warnings.append(stale)
    files: list[dict[str, Any]] = []
    skipped_sheets: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for row in sorted(inv.doc["files"], key=lambda r: r["path"]):
        if row["format"] not in ("dwg", "dxf"):
            continue
        loaded = load_file(inv, row, check_inputs=check_inputs)
        warnings.extend(f"{loaded.rel}: {w}" for w in loaded.warnings)
        info: dict[str, Any] = {
            "path": loaded.rel,
            "status": "scanned",
            "reason": None,
            "text_entries": None,
            "scanned": 0,
            "candidates": 0,
        }
        files.append(info)
        if loaded.skip is not None or loaded.text_index is None:
            info.update(status="skipped", reason=loaded.skip)
            continue
        entries = loaded.text_index["entries"]
        info["text_entries"] = len(entries)
        sheet_of: dict[str, dict[str, Any]] = {}
        duplicate_ids: set[str] = set()
        if loaded.sheets is not None:
            for sh in loaded.sheets["sheets"]:
                if sh["duplicate_of"] is not None:
                    duplicate_ids.update(sh["text_ids"])
                    skipped_sheets.append(
                        {
                            "file": loaded.rel,
                            "sheet": sh["sheet_id"],
                            "duplicate_of": sh["duplicate_of"],
                            "text_entries": len(sh["text_ids"]),
                        }
                    )
                else:
                    sheet_of.update({tid: sh for tid in sh["text_ids"]})
        claimed_ids = _claimed_text_ids(inv.work, loaded, warnings)
        as_marks = footing_m_labels([e for e in entries if e["id"] not in duplicate_ids], sheet_of)
        for entry in entries:
            if entry["id"] in duplicate_ids:
                continue
            info["scanned"] += 1
            sheet = sheet_of.get(entry["id"])
            hits, rejects = _entry_hits(entry, claimed_ids.get(entry["id"]), entry["id"] in as_marks)
            reason = meaning_block_reason(entry)
            if reason is not None:  # legacy-font gate: no meaning from this text, only a verbatim listing
                if hits:
                    blocked.append(
                        {
                            "file": loaded.rel,
                            "sheet": None if sheet is None else sheet["sheet_id"],
                            "entry_id": entry["id"],
                            "display_text": " ".join(entry["display_text"].split())[:LINE_CHARS],
                            "reason": reason,
                        }
                    )
                continue
            for text, kind, code in rejects:
                rejected.append(
                    {
                        "file": loaded.rel,
                        "sheet": None if sheet is None else sheet["sheet_id"],
                        "entry_id": entry["id"],
                        "display_text": text[:LINE_CHARS],
                        "kind": kind,
                        "reason_code": code,
                        "reason": REJECT_REASONS[code],
                    }
                )
            for line, hit in hits:
                span = line[hit.start : hit.end]
                flags = list(entry["flags"])
                if entry["decode"]["case_uncertain"]:
                    flags.append("case_uncertain")
                flags.extend(f for f in hit.derived_flags if f not in flags)
                cand: dict[str, Any] = {
                    "id": "",
                    "kind": hit.kind,
                    "file": loaded.rel,
                    "sheet": None if sheet is None else sheet["sheet_id"],
                    "sheet_number": None if sheet is None else printed_number(sheet),
                    "text_ref": {"file": loaded.rel, "entry_id": entry["id"]},
                    "display_text": span,
                    "position": {"x": entry["position"]["x"], "y": entry["position"]["y"]},
                    "layer": entry["layer"],
                    "encoding": entry["decode"]["encoding_used"],
                    "parsed": hit.parsed,
                    "rule": hit.rule,
                    "unparsed_reason": hit.reason if hit.parsed is None else None,
                    "ambiguity": hit.ambiguity,
                    "lexical": hit.lexical,
                    "confidence": _confidence(hit.cap, entry, hit.derived_flags),
                    "flags": flags,
                    "provenance": _provenance(loaded.rel, sheet, entry),
                }
                if hit.parsed is None:
                    assert hit.code is not None, hit.rule  # every unparsed hit names its reason family
                    cand["unparsed_code"] = hit.code
                if hit.family is not None:
                    cand["_family"] = hit.family
                if span.strip() != line.strip():
                    cand["line_text"] = " ".join(line.split())[:LINE_CHARS]
                if hit.kind == "member_mark":
                    cand["display_text"] = span.strip()
                candidates.append(cand)
                info["candidates"] += 1
    _finish(candidates)
    doc = {
        "schema_version": SCHEMA_VERSION,
        "kind": "callouts",
        "project_id": inv.doc["project_id"],
        "inventory_sha256": inv.sha256,
        "files": files,
        "skipped_sheets": skipped_sheets,
        "candidates": candidates,
        "blocked_entries": blocked,
        "rejected": rejected,
        "question_counts": question_counts(candidates),
        "summary": _summary(candidates, files, blocked, rejected),
        "warnings": warnings,
    }
    return _check(doc)


def _finish(candidates: list[dict[str, Any]]) -> None:
    """Ids, the steel-standard mix flag, and removal of working keys. Order is the scan order."""
    families: dict[tuple[str, str | None], set[str]] = {}
    for c in candidates:
        if "_family" in c:
            families.setdefault((c["file"], c["sheet"]), set()).add(c["_family"])
    for n, c in enumerate(candidates, start=1):
        c["id"] = f"K{n:06d}"
        family = c.pop("_family", None)
        if family is not None and c["ambiguity"] is None and len(families[(c["file"], c["sheet"])]) > 1:
            c["ambiguity"] = "steel_grade_standard_mix"
        if c["lexical"] is None:
            del c["lexical"]


# --- numbered questions (callouts-questions.json) ---------------------------------------------------------

AMBIGUOUS_GROUP_MESSAGE = (
    "These texts match a notation that has more than one reading (research, ambiguous list). Each notation "
    "listed in `subjects` is a question of its own: its wording is the `message` of its first reference. "
    "Answer in words, per notation."
)


def _qref(c: dict[str, Any], where: str, found_prefix: str = "") -> dict[str, Any]:
    ref = _ref(c)
    out: dict[str, Any] = {"file": c["file"], "where": where, "found": found_prefix + ref["text"]}
    if c["sheet"] is not None:
        out["sheet"] = c["sheet"]
    return out


def _ambiguous_questions(file: str, cands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_block: dict[bool, dict[str, list[dict[str, Any]]]] = {}
    for c in cands:
        if c["ambiguity"]:
            blocking = AMBIGUITIES[c["ambiguity"]][0]
            by_block.setdefault(blocking, {}).setdefault(c["ambiguity"], []).append(c)
    out = []
    for blocking, by_amb in by_block.items():
        refs: list[dict[str, Any]] = []
        subjects = []
        for amb in sorted(by_amb):
            group = by_amb[amb]
            shown = [_qref(c, f"text entry {c['text_ref']['entry_id']}", f"[{amb}] ") for c in group]
            shown[0]["message"] = AMBIGUITIES[amb][1]  # the wording of this notation's question
            refs.extend(shown[:MAX_PREFIX_REFS])
            subjects.append({"name": amb, "count": len(group)})
        total = sum(s["count"] for s in subjects)
        q = question_group(
            "callout_ambiguous", blocking, AMBIGUOUS_GROUP_MESSAGE, refs, file=file, subjects=subjects
        )
        q["count"], q["truncated"] = total, len(refs) < total
        out.append(q)
    return out


def _legacy_question(file: str, cands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    legacy = [c for c in cands if c["parsed"] and c["parsed"]["form"] == "legacy_group"]
    legacy += [c for c in cands if c["rule"].startswith("LEGACY_GROUP") and c["parsed"] is None]
    legacy.sort(key=lambda c: c["id"])
    if not legacy:
        return []
    refs = [_qref(c, f"text entry {c['text_ref']['entry_id']}") for c in legacy]
    return [question_group("grade_legacy_mapping", True, LEGACY_GRADE_MESSAGE, refs, MAX_REFS, file=file)]


UNPARSED_EXAMPLES = 5  # example candidates quoted per callout_unparsed question; count stays true
UNPARSED_MESSAGE = (
    "These texts look like a callout but are not read into values; the subject names the reason family "
    "({code}: {why}). The refs give up to five examples (text entry ids, verbatim) and the sheets that hold "
    "them, with counts. Look at the examples on the drawing: what does the notation mean, and must these "
    "texts be read? Lot specs cannot use them until this is answered."
)
UNPARSED_WHY = {
    NOTATION_UNVERIFIED: "a diameter, section, plate, hole or bolt form outside the verified notations",
    GRADE_UNVERIFIED: "a grade spelling or number outside the verified grade list",
    CONFLICTING: "one line gives several values",
    SYMBOL_GLYPH: "a character that is not Ø or %%c stands in diameter position; it is never decoded",
}


def _unparsed_questions(file: str, cands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One blocking callout_unparsed per reason family (unparsed_code) of the file's asked candidates:
    the first UNPARSED_EXAMPLES in scan order, then one ref listing the sheets with counts."""
    by_code: dict[str, list[dict[str, Any]]] = {}
    for c in cands:
        if _asked_unparsed(c):
            by_code.setdefault(c["unparsed_code"], []).append(c)
    out = []
    for code in sorted(by_code):
        group = by_code[code]
        refs = [_qref(c, f"text entry {c['text_ref']['entry_id']}") for c in group[:UNPARSED_EXAMPLES]]
        per_sheet = Counter(c["sheet"] or "no sheet" for c in group)
        sheets = ", ".join(f"{sheet} ({n})" for sheet, n in sorted(per_sheet.items()))
        refs.append({"file": file, "where": "sheets", "found": sheets})
        message = UNPARSED_MESSAGE.format(code=code, why=UNPARSED_WHY[code])
        q = question_group(
            CALLOUT_UNPARSED_CODE,
            True,
            message,
            refs,
            file=file,
            subjects=[{"name": code, "count": len(group)}],
        )
        q["count"], q["truncated"] = len(group), len(group) > UNPARSED_EXAMPLES
        out.append(q)
    return out


def callout_questions(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Raw questions (no id, key or answer yet) of a callouts document: one per (code, blocking flag, file),
    blocking first, then by code, then by file. Counts come from all candidates, not from capped lists."""
    by_file: dict[str, list[dict[str, Any]]] = {}
    for c in candidates:
        by_file.setdefault(c["file"], []).append(c)
    out: list[dict[str, Any]] = []
    for file in sorted(by_file):
        mine = by_file[file]
        out += (
            _ambiguous_questions(file, mine) + _legacy_question(file, mine) + _unparsed_questions(file, mine)
        )
    return sorted(out, key=lambda q: (not q["blocking"], q["code"], q["file"]))


@dataclass
class CalloutsResult:
    exit_code: int
    summary: dict[str, Any]


def _check_input_dir(inv: Any, input_dir: Path) -> None:
    """The input folder must still hold the files intake read (same sha256)."""
    if not input_dir.is_dir():
        raise ReaderError(EXIT_USAGE, f"input folder not found (not a folder): {input_dir}")
    problems = []
    for row in inv.doc["files"]:
        if row["format"] not in ("dwg", "dxf"):
            continue
        path = input_dir / row["path"]
        if not path.is_file():
            problems.append(f"{row['path']}: not found in {input_dir}")
        elif sha256_file(path) != row["sha256"]:
            problems.append(f"{row['path']}: changed since intake")
    if problems:
        raise ReaderError(
            EXIT_INVALID,
            "the input folder no longer matches inventory.json, nothing written (rerun `harness intake`):\n  "
            + "\n  ".join(problems),
        )


def run_callouts(
    work_dir: Path | str, input_dir: Path | str | None = None, *, check_inputs: bool = False
) -> CalloutsResult:
    """Callout candidates and their numbered questions of an intake work folder. Writes `callouts.json`,
    `callouts-questions.json` and updates the registry. Raises ReaderError (QuestionsError is mapped to it).

    `input_dir`: when given, every DXF/DWG of the inventory must still be there with the same sha256."""
    inv = load_inventory(work_dir)
    try:
        ledger = load_ledger(inv.work, inv.doc["project_id"], create=False)
    except QuestionsError as exc:
        raise ReaderError(exc.exit_code, str(exc)) from exc
    if input_dir is not None:
        _check_input_dir(inv, Path(input_dir).resolve())
    doc = extract_callouts(inv.work, check_inputs=check_inputs)
    hashes = {r["path"]: r["sha256"] for r in inv.doc["files"]}
    try:
        questions = ledger.sync("callouts", callout_questions(doc["candidates"]), hashes)
    except QuestionsError as exc:
        raise ReaderError(exc.exit_code, str(exc)) from exc
    qdoc = questions_document(inv.doc["project_id"], questions)
    problems = validate("intake", qdoc)
    if problems:
        raise ReaderError(
            EXIT_INVALID, f"callouts-questions.json is invalid, nothing written: {_details(problems)}"
        )
    try:
        texts = {"callouts.json": dump_json(doc), "callouts-questions.json": dump_json(qdoc)}
        for text in texts.values():
            text.encode("utf-8")
    except (ValueError, UnicodeEncodeError) as exc:
        raise ReaderError(EXIT_INVALID, f"callouts output cannot be written as strict JSON: {exc}") from exc
    try:
        ledger.write()  # the registry is written before any document that uses its ids
        for name, text in texts.items():
            write_text_atomic(inv.work / name, text)
    except OSError as exc:
        raise ReaderError(3, f"cannot write into {inv.work}: {exc}") from exc  # 3: environment
    s = doc["summary"]
    summary = {
        "project_id": doc["project_id"],
        "candidates": s["candidates"],
        "parsed": s["parsed"],
        "unparsed": s["unparsed"],
        "by_kind": s["by_kind"],
        "files_scanned": s["files_scanned"],
        "files_skipped": s["files_skipped"],
        **qdoc["summary"],
        "stale_answers": ledger.stale_answers(),
        "warnings": doc["warnings"],
        "outputs": {
            "callouts": str(inv.work / "callouts.json"),
            "questions": str(inv.work / "callouts-questions.json"),
            "registry": str(inv.work / "question-registry.json"),
        },
    }
    return CalloutsResult(0, summary)
