"""extract_text: a deterministic text index of one DXF, with where each text is and how it was read.

`extract_text(path)` returns a dict that validates against `schemas/text-index.schema.json`. It lists
TEXT, MTEXT, ATTRIB, MULTILEADER and DIMENSION-override text in modelspace and every paper-space layout,
plus the same kinds found inside INSERTed blocks (recursively, through `virtual_entities()`, with a
`block_path`). ATTDEFs are listed separately as definitions: they are not visible text. Nothing is
interpreted: no title block, no grid, no level. That is the job of later slices that read this index.

Decoding order (the hazard is documented in docs/research/vietnamese-legacy-encodings.md):
  1. split an MTEXT into runs at inline font switches (`\\F`/`\\f`), with ezdxf's MTextParser;
  2. choose each run's encoding. Precedence: code-point evidence, then FONT NAMES via `encoding.font_hint`
     (inline font, else the text style: its name, font file, then its TrueType family from the ACAD XDATA,
     source `style_family`), then an APPROVED row of the knowledge table (text style runs
     only, and only when `font_hint` said nothing), else unknown. Evidence: legacy TCVN3/VNI text is one
     byte per character, so a Vietnamese letter above U+00FF (or a tone mark) proves the run is Unicode
     whatever the font name says (`encoding.has_unicode_vietnamese`); it is judged on the text as the
     code page sees it, so a cp1258 file's view of legacy bytes is not mistaken for Unicode;
  3. convert legacy (TCVN3/VNI) literal text with `encoding.convert_legacy`;
  4. only then expand `%%c %%d %%p` (and drop `%%u %%o %%k`) into `display_text`.
`%%` codes are protected from ezdxf's own expansion (which would turn `%%c` into U+00D8 before step 3,
where U+00D8 is a letter in TCVN3) and are never fed to the converter.

Special-code characters follow ezdxf (`ezdxf.const.SPECIAL_CHAR_ENCODING`): `%%c` U+00D8 (Latin capital
O with stroke, not the true diameter sign U+2300), `%%d` U+00B0, `%%p` U+00B1, `%%%` '%'.

Every entity is processed inside its own try block: a failure is counted and listed in `summary.errors`
with its handle and the status becomes 'partial'. Nothing is dropped silently: empty texts, skipped
inserts, entities ezdxf could not transform and text-bearing types this slice cannot read are all
counted in the summary.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path, PureWindowsPath
from typing import Any

from ezdxf import const as dxf_const
from ezdxf.document import Drawing
from ezdxf.entities.dxfentity import DXFEntity
from ezdxf.entities.viewport import Viewport
from ezdxf.enums import MTextEntityAlignment
from ezdxf.filemanagement import readfile
from ezdxf.fonts.font_face import FontFace
from ezdxf.lldxf.encoding import decode_dxf_unicode, has_dxf_unicode, has_mif_encoding
from ezdxf.math import Vec3
from ezdxf.tools.text import MTextContext, MTextParser, TokenType
from ezdxf.version import __version__ as EZDXF_VERSION

from tekla_harness.detect import sha256_file
from tekla_harness.encoding import (
    FontHint,
    convert_legacy,
    font_hint,
    has_lone_surrogate,
    has_unicode_vietnamese,
    legacy_font_name,
    scrub_surrogates,
)
from tekla_harness.knowledge import FontEncodingRow, FontEncodingTable, default_font_encodings
from tekla_harness.read_dxf import CONVERTER_CAPS, handles_reliable, num, text_style_family
from tekla_harness.readlog import timed_attempt

SCHEMA_VERSION = "0.1"
MAX_BLOCK_DEPTH = 16  # nesting levels of INSERTs that are expanded; deeper inserts are counted, not read
MAX_ERRORS_LISTED = 200
MAX_TOP = 50  # rows kept in the "top N" summary tables
MAX_SKIPPED_LISTED = 50
SHEET_UNKNOWN = "unknown"  # provenance.sheet: the sheet number printed in the title block is not known here

_CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}
_PH = "\U0010fffd"  # private-use placeholder for '%%' while ezdxf's MTextParser runs
_STYLE_FONT = "\U0010fffc"  # sentinel font family: "no inline font; the entity's text style applies"
_UNICODE_VERSION = "AC1021"  # R2007: DXF text is UTF-8 from here on
_UTF8_LIKE = frozenset({"utf8", "utf_8", "cp1252", "latin1", "latin_1", "iso8859_1", "iso_8859_1"})

_TEXT_TYPES = frozenset({"TEXT", "MTEXT", "MULTILEADER", "MLEADER", "DIMENSION"})
_NOT_EXTRACTED_TYPES = frozenset({"ACAD_TABLE", "ACAD_PROXY_ENTITY", "TOLERANCE"})
_SPECIAL_RE = re.compile(r"%%([cdpuokCDPUOK%])")
_ANY_SPECIAL_RE = re.compile(r"%%(.?)", re.DOTALL)
_SPECIAL_EXPANSION = {
    "c": dxf_const.SPECIAL_CHAR_ENCODING["c"],
    "d": dxf_const.SPECIAL_CHAR_ENCODING["d"],
    "p": dxf_const.SPECIAL_CHAR_ENCODING["p"],
    "%": dxf_const.SPECIAL_CHAR_ENCODING["%"],
    "u": "",
    "o": "",
    "k": "",
}
_ASCII_LOWER = re.compile(r"[a-z]")
_SOURCE_ORDER = (
    "codepoint_evidence",
    "knowledge_table",
    "mtext_inline_font",
    "style_font",
    "style_family",
)  # entry-level source


# --- text pieces and decoding --------------------------------------------------------


@dataclass(frozen=True)
class _Run:
    font: str | None  # inline font family, or None when the entity's text style applies
    text: str  # formatting codes removed; '%%' codes still as written; legacy bytes not decoded


@dataclass
class _RunResult:
    font: str | None
    font_source: str  # style_font | mtext_inline_font | knowledge_table | codepoint_evidence | none
    encoding: str  # unicode | tcvn3 | vni | unknown
    capital_font: bool | None
    decoded: str
    display: str
    codes: list[str]
    ambiguous: int = 0
    unmapped: int = 0
    nfd_damaged: bool = False
    unknown_non_ascii: bool = False
    reencode_failed: bool = False
    unknown_code: bool = False
    literals: list[str] = field(default_factory=list)  # the run's text pieces between '%%' codes, as stored
    knowledge_pattern: str | None = None
    contradicts_font: bool = False  # Unicode evidence in a run whose font said TCVN3 / VNI
    eth: bool = False
    conflict: bool = False  # approved knowledge rows disagree about this run's style
    proposed: bool = False  # a proposed knowledge row matches this run's style


def _protect(raw: str) -> str:
    return raw.replace("%%", _PH)


def _restore(text: str) -> str:
    return text.replace(_PH, "%%")


def mtext_runs(raw: str) -> list[_Run]:
    """Split MTEXT content into runs of constant inline font, formatting codes removed.

    Uses ezdxf's MTextParser. A run whose font is None is on the entity's text style (the parser starts from a
    sentinel font family, so a `}` that closes a font group returns to it). Whitespace never opens a run, so a
    space between two fonts does not count as a font change. Paragraph breaks become '\\n', tabs '\\t',
    stacked
    fractions 'upper' + divider + 'lower' (as `ezdxf.tools.text.plain_mtext` does).
    """
    ctx = MTextContext()
    ctx.font_face = FontFace(family=_STYLE_FONT)
    runs: list[list[Any]] = []  # [font, [pieces]]
    pending: list[str] = []
    for token in MTextParser(_protect(raw), ctx):
        family = token.ctx.font_face.family
        font = None if family == _STYLE_FONT else family
        kind = token.type
        if kind == TokenType.WORD:
            piece = str(token.data)
        elif kind in (TokenType.SPACE, TokenType.NBSP):
            piece = " "
        elif kind in (TokenType.NEW_PARAGRAPH, TokenType.NEW_COLUMN):
            piece = "\n"
        elif kind == TokenType.TABULATOR:
            piece = "\t"
        elif kind == TokenType.STACK:
            upper, lower, divider = token.data or ("", "", "")
            piece = f"{upper}{divider}{lower}"
        else:
            continue
        piece = _restore(piece)
        if piece.strip() == "":  # whitespace joins the current run, or waits for the first one
            (runs[-1][1] if runs else pending).append(piece)
            continue
        if not runs or runs[-1][0] != font:
            runs.append([font, [*pending, piece]])
            pending = []
        else:
            runs[-1][1].append(piece)
    if not runs:
        return [_Run(None, "".join(pending))]
    return [_Run(font, "".join(parts)) for font, parts in runs]


def _split_specials(text: str) -> list[tuple[bool, str]]:
    """Split on known `%%x` codes: [(is_code, piece)]. Unknown `%%x` stays inside the literal pieces."""
    out: list[tuple[bool, str]] = []
    last = 0
    for match in _SPECIAL_RE.finditer(text):
        if match.start() > last:
            out.append((False, text[last : match.start()]))
        out.append((True, match.group(0)))
        last = match.end()
    if last < len(text):
        out.append((False, text[last:]))
    return out


def _has_unknown_code(text: str) -> bool:
    return any(not _SPECIAL_RE.fullmatch(m.group(0)) for m in _ANY_SPECIAL_RE.finditer(text))


# (font key: ("file", font file leaf) | ("style", name) | ("font", inline family), encoding, legacy font name)
_SuspectRun = tuple[tuple[str, str], str, bool]


@dataclass(frozen=True)
class _StyleDecision:
    hint: FontHint
    source: str = "style_font"  # style_font | style_family | knowledge_table
    pattern: str | None = None  # the approved knowledge row that decided
    conflict: bool = False
    proposed: tuple[FontEncodingRow, ...] = ()


@dataclass
class _Context:
    """Per-file decode settings and the state shared by the whole extraction."""

    doc: Drawing
    path: Path
    cap: str
    handles_ok: bool
    layer_state: dict[str, str]
    layer_no_plot: frozenset[str] = (
        frozenset()
    )  # case-folded names of layers with the plot flag off (group 290)
    viewport_frozen: frozenset[str] = frozenset()  # case-folded names of layers frozen in some viewport
    attmode: int = 1  # header $ATTMODE (1 when absent): 0 none shown, 1 by their own flag, 2 all shown
    knowledge: FontEncodingTable = field(default_factory=FontEncodingTable)
    style_cache: dict[str, tuple[str | None, bool]] = field(default_factory=dict)
    family_cache: dict[str, str | None] = field(default_factory=dict)
    decision_cache: dict[str, _StyleDecision] = field(default_factory=dict)
    proposed_hits: dict[int, tuple[FontEncodingRow, Counter[str]]] = field(default_factory=dict)
    block_info: dict[str, tuple[bool, tuple[str, ...]]] = field(default_factory=dict)
    bears_text: dict[str, bool] = field(default_factory=dict)
    entries: list[dict[str, Any]] = field(default_factory=list)
    # legacy_ascii_suspect: fonts (("style", name) or ("font", inline family)) holding non-ASCII text of
    # unknown encoding, and the pure-ASCII entries with a legacy-looking run, judged once all are read
    unknown_non_ascii_fonts: set[tuple[str, str]] = field(default_factory=set)
    ascii_suspects: list[tuple[dict[str, Any], list[_SuspectRun]]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    errors_total: int = 0
    empty_skipped: int = 0
    depth_limit_count: int = 0
    cycle_count: int = 0
    xref_inserts_skipped: int = 0
    missing_block_inserts: int = 0
    dimensions_without_override: int = 0
    not_extracted: Counter[str] = field(default_factory=Counter)
    transform_skipped: Counter[str] = field(default_factory=Counter)
    transform_skipped_listed: list[dict[str, str]] = field(default_factory=list)
    codepage: str = ""
    source: str = ""  # provenance.file / file.path as recorded (input-relative when intake runs)

    def legacy_form(self, text: str) -> tuple[str, bool]:
        """Text as 'one char per legacy byte' (latin-1 view), as encoding.convert_legacy expects.

        UTF-8 and cp1252/latin-1 files already give that. A file with another code page was decoded with it by
        ezdxf: re-encode with the same code page and read the bytes as latin-1 (see encoding.py). False when a
        character cannot be re-encoded.
        """
        name = self.codepage.lower().replace("-", "_")
        if not name or name in _UTF8_LIKE:
            return text, True
        try:
            return text.encode(self.codepage).decode("latin-1"), True
        except (UnicodeEncodeError, LookupError):
            return text, False

    def has_unicode_evidence(self, text: str) -> bool:
        """A Vietnamese letter or tone mark that legacy single-byte text cannot hold (encoding.py).

        In a file read with another code page (cp1258...) ezdxf's view of a legacy byte can be one of those
        letters (0xD0 is U+0110 in cp1258), so there only a character the code page cannot encode counts: it
        can only have come from a `\\U+XXXX` escape.
        """
        if not has_unicode_vietnamese(text):
            return False
        name = self.codepage.lower().replace("-", "_")
        if not name or name in _UTF8_LIKE:
            return True
        for ch in text:
            if has_unicode_vietnamese(ch):
                try:
                    ch.encode(self.codepage)
                except (UnicodeEncodeError, LookupError):
                    return True
        return False

    def style_decision(self, style: str | None) -> _StyleDecision:
        """Encoding hint of a text style: `font_hint` (name, font file, TrueType family), then an approved
        knowledge row if that says nothing. A family that disagrees with an approved row (or approved rows
        that disagree among themselves) decides nothing: a knowledge conflict, as between rows."""
        key = style or ""
        if key not in self.decision_cache:
            if not style:
                self.decision_cache[key] = _StyleDecision(FontHint("unknown", None))
            else:
                font_file, _exists = self.style_font(style)
                hint = font_hint(style, font_file, self.style_family(style))
                source = "style_family" if hint.decided_by == "family" else "style_font"
                decision = _StyleDecision(hint, source)
                if hint.decided_by == "family":
                    found = self.knowledge.match(style, font_file)
                    if found.conflict or (found.encoding is not None and found.encoding != hint.encoding):
                        decision = _StyleDecision(
                            FontHint("unknown", hint.capital_font), conflict=True, proposed=found.proposed
                        )
                elif hint.encoding == "unknown":
                    found = self.knowledge.match(style, font_file)
                    decision = _StyleDecision(hint, conflict=bool(found.conflict), proposed=found.proposed)
                    if found.encoding is not None:
                        capital = hint.capital_font if hint.capital_font is not None else found.capital_font
                        decision = _StyleDecision(
                            FontHint(found.encoding, capital),
                            "knowledge_table",
                            found.patterns[0],
                            proposed=found.proposed,
                        )
                self.decision_cache[key] = decision
        return self.decision_cache[key]

    def style_font(self, style: str | None) -> tuple[str | None, bool]:
        """(font file, style exists) for a text style name."""
        if style is None:
            return None, False
        if style not in self.style_cache:
            if self.doc.styles.has_entry(style):
                font = str(self.doc.styles.get(style).dxf.get("font", "")) or None
                self.style_cache[style] = (font, True)
            else:
                self.style_cache[style] = (None, False)
        return self.style_cache[style]

    def font_key(self, style: str | None) -> tuple[str, str]:
        """The font a style run is drawn with, for the sibling rule (`_flag_legacy_ascii`): its font file's
        leaf, case-folded, so styles sharing one file share the evidence; the style name without a file."""
        font_file, _exists = self.style_font(style)
        if font_file:
            return ("file", PureWindowsPath(font_file).name.casefold())
        return ("style", style or "")

    def style_names(self, style: str | None) -> tuple[str, ...]:
        """Style name, font file and TrueType family of a text style (the names `font_hint` reads)."""
        if not style:
            return ()
        font_file, _exists = self.style_font(style)
        return tuple(n for n in (style, font_file, self.style_family(style)) if n)

    def style_family(self, style: str) -> str | None:
        """TrueType family of a text style (read_dxf.text_style_family); None when absent or empty."""
        if style not in self.family_cache:
            entry = self.doc.styles.get(style) if self.doc.styles.has_entry(style) else None
            self.family_cache[style] = (text_style_family(entry) or None) if entry is not None else None
        return self.family_cache[style]


def _decode_run(ctx: _Context, run: _Run, decision: _StyleDecision) -> _RunResult:
    pattern: str | None = None
    if run.font is None:
        hint, source, pattern = decision.hint, decision.source, decision.pattern
    else:
        hint, source = font_hint(run.font), "mtext_inline_font"
    encoding, capital = hint.encoding, hint.capital_font
    if encoding == "unknown":
        source = "none"
    contradicts = False
    evidence = ctx.has_unicode_evidence(run.text)
    if evidence and encoding != "unicode":
        contradicts = encoding in ("tcvn3", "vni")
        encoding, source, pattern, capital = "unicode", "codepoint_evidence", None, None
    result = _RunResult(run.font, source, encoding, capital, "", "", [])
    result.knowledge_pattern = pattern
    result.contradicts_font = contradicts
    result.eth = encoding == "unicode" and evidence and "\u00d0" in run.text
    if run.font is None and encoding == "unknown":  # nothing decided: say why a table row did not
        result.conflict, result.proposed = decision.conflict, bool(decision.proposed)
    result.unknown_code = _has_unknown_code(run.text)
    decoded: list[str] = []
    display: list[str] = []
    for is_code, piece in _split_specials(run.text):
        if is_code:
            result.codes.append(piece.lower())
            decoded.append(piece)
            display.append(_SPECIAL_EXPANSION[piece[2:].lower()])
            continue
        result.literals.append(piece)
        if encoding in ("tcvn3", "vni"):
            latin, ok = ctx.legacy_form(piece)
            if not ok:
                result.reencode_failed = True
            converted = convert_legacy(latin, encoding, capital_font=capital)  # type: ignore[arg-type]
            result.ambiguous += len(converted.ambiguous)
            result.unmapped += len(converted.unmapped)
            result.nfd_damaged = result.nfd_damaged or converted.nfd_damaged
            text = converted.text
        else:
            text = piece
            if encoding == "unknown":
                if not piece.isascii():
                    result.unknown_non_ascii = True
                if capital:  # a capital-font style name with no known encoding: case is a guess
                    result.ambiguous += len(_ASCII_LOWER.findall(piece))
        decoded.append(text)
        display.append(text)
    result.decoded = "".join(decoded)
    result.display = "".join(display)
    return result


def _combine(values: list[bool | None]) -> bool | None:
    known = {v for v in values if v is not None}
    return known.pop() if len(known) == 1 else None


def _decode_text(ctx: _Context, raw: str, style: str | None, *, mtext: bool) -> dict[str, Any]:
    """All text-derived fields of one entry. `mtext`: parse inline formatting codes and font switches."""
    decision = ctx.style_decision(style)
    runs = mtext_runs(raw) if mtext else [_Run(None, raw)]
    # DXF stores characters outside the file's code page as '\\U+XXXX' (R2004 and older); ezdxf leaves them
    # in TEXT/MTEXT strings. Decode before anything else; '\\M+' (multibyte) needs the code page: flagged.
    escapes: list[str] = []
    if any(has_dxf_unicode(r.text) for r in runs):
        runs = [_Run(r.font, decode_dxf_unicode(r.text)) for r in runs]
        escapes.append("dxf_unicode_escape_decoded")
    mif = any(has_mif_encoding(r.text) for r in runs)
    results = [_decode_run(ctx, run, decision) for run in runs]
    suspect: list[_SuspectRun] = []  # the runs that look legacy
    for run, r in zip(runs, results, strict=True):
        key = ctx.font_key(style) if run.font is None else ("font", run.font.casefold())
        if r.unknown_non_ascii:
            ctx.unknown_non_ascii_fonts.add(key)
        if r.encoding in ("tcvn3", "vni", "unknown") and any(
            piece.isascii() and looks_legacy_ascii(piece) for piece in r.literals
        ):
            names = ctx.style_names(style) if run.font is None else (run.font,)
            suspect.append((key, r.encoding, any(legacy_font_name(n) for n in names)))

    encodings = [r.encoding for r in results]
    used = encodings[0] if len(set(encodings)) == 1 else "mixed"
    sources = {r.font_source for r in results}
    source = next(
        (name for name in _SOURCE_ORDER if name in sources),
        "none",
    )
    fonts = {r.font or "" for r in results}
    ambiguous = sum(r.ambiguous for r in results)
    unmapped = sum(r.unmapped for r in results)
    nfd = any(r.nfd_damaged for r in results)
    unknown_non_ascii = any(r.unknown_non_ascii for r in results)
    reencode_failed = any(r.reencode_failed for r in results)
    unknown_code = any(r.unknown_code for r in results)
    case_uncertain = ambiguous > 0
    codes: list[str] = []
    for r in results:
        for code in r.codes:
            if code not in codes:
                codes.append(code)

    flags: list[str] = list(escapes)
    if mif:
        flags.append("mif_escape_not_decoded")
    if unknown_non_ascii:
        flags.append("encoding_unknown_non_ascii")
    if reencode_failed:
        flags.append("codepage_reencode_failed")
    if unknown_code:
        flags.append("unknown_special_code")
    if len(fonts) > 1:
        flags.append("mixed_fonts")
    if any(r.font is not None and r.encoding == "unknown" for r in results):
        flags.append("inline_font_unknown")
    if any(r.contradicts_font for r in results):
        flags.append("unicode_evidence_contradicts_font")
    if any(r.eth for r in results):
        flags.append("eth_for_d_stroke")
    if any(r.conflict for r in results):
        flags.append("knowledge_conflict")
    if any(r.proposed for r in results):
        flags.append("proposed_knowledge_row")
        for row_ in decision.proposed:
            ctx.proposed_hits.setdefault(row_.line, (row_, Counter()))[1][str(style)] += 1
    patterns = list(dict.fromkeys(r.knowledge_pattern for r in results if r.knowledge_pattern))

    confidence = ctx.cap
    # high only for text whose font is a known Unicode family: legacy, unknown and mixed text, and Unicode
    # proved by code points or a knowledge row (the font itself is not known), are never better than medium
    if used != "unicode" or sources & {"codepoint_evidence", "knowledge_table"}:
        confidence = _min_conf(confidence, "medium")
    if case_uncertain or unmapped or nfd or unknown_non_ascii or reencode_failed or unknown_code or mif:
        confidence = "low"

    return {
        "plain_text": "".join(r.text for r in runs),
        "decoded_text": "".join(r.decoded for r in results),
        "display_text": "".join(r.display for r in results),
        "special_codes": codes,
        "decode": {
            "encoding_used": used,
            "source": source,
            "capital_font": _combine([r.capital_font for r in results]),
            "knowledge_patterns": patterns,
            "case_uncertain": case_uncertain,
            "ambiguous_count": ambiguous,
            "unmapped_count": unmapped,
            "nfd_damaged": nfd,
            "runs": len(results),
            "mixed_fonts": len(fonts) > 1,
            "run_details": [
                {
                    "font": r.font,
                    "font_source": r.font_source,
                    "encoding": r.encoding,
                    "capital_font": r.capital_font,
                    "knowledge_pattern": r.knowledge_pattern,
                }
                for r in results
            ],
        },
        "flags": flags,
        "confidence": confidence,
        "_suspect_runs": suspect,
    }


def _min_conf(a: str, b: str) -> str:
    return min(a, b, key=_CONFIDENCE_ORDER.__getitem__)


# --- ASCII text that looks like legacy Vietnamese (tool wave 2, fix 2b) ----------------------------
# Legacy fonts keep ASCII as ASCII, so the gate allows pure-ASCII text (text_gate). Some legacy Vietnamese
# fonts, though, write Vietnamese with plain ASCII letters. EVAL-2 saw two shapes in legacy-font styles
# (dwgshare 267 and 461): a slash before a letter or brace ('4/g14', 'BT LO/ST #100', '3 L/}/{/SI') and an
# uppercase tone letter after a vowel, Telex style: S F R X J = acute, grave, hook, tilde, dot ('chi tiESt
# kim thu seSt', 'haFn 200', 'coJC'). The encoding.py TCVN3 / VNI tables do not produce either shape (their
# Vietnamese letters are all bytes >= 0x80), so the shapes come from the observed strings, kept narrow:
#   * a slash before a unit denominator is not suspect ('kG/cm2', 'T/m2', 'kN/m', 'Kg/M2'), nor before a word
#     of three or more letters ('Cu/PVC/PVC', seen in a TCVN3 capital-font style of dwgshare 461);
#   * a slash before 'a' and a digit is a bar spacing or a paper size ('%%c8a100/a200', '1:100/a3'), and one
#     letter that ends the token after a slash is an abbreviation or a grid sub-axis ('C/C', 'N/A', 'b/h',
#     '1/A'), unless two letters stand before the slash ('BO/R', the 'BO/R 300mm' of dwgshare 267);
#   * a tone letter needs a lowercase vowel just before it, or an uppercase A E O that follows a lowercase
#     letter ('tiESt'), so all-capital words ('EST', 'HEA 300', 'S355JR') and marks ('D1', 'C2') never match;
#   * an uppercase vowel between two lowercase letters is a circumflex vowel written as a capital ('dAy',
#     'tEn vAJt', 'cOng trInh', dwgshare 461), never a unit ('kA') or a mark;
#   * both letter shapes are judged per word, and a CamelCase word is English, not Telex: a capitalised first
#     part, then humps of an uppercase letter and two or more lowercase letters with a vowel ('TieRod',
#     'BaseRing', 'HoleSize'); 'DiJa' (one letter after the hump) stays suspect.
# A text is flagged when such a run is in a TCVN3 / VNI font, or in an unknown-encoding font that has a legacy
# Vietnamese name (`encoding.legacy_font_name` of the style name, font file or family; inline font: its
# family), or that also holds non-ASCII text of unknown encoding (its "siblings", judged per font file: two
# styles on one file share it). Default D2, reversible: suspect patterns only, not all ASCII.
_SLASH_LETTER = re.compile(
    r"/(?!(?i:mm|cm|dm|m)[23]?(?![A-Za-z0-9]))"  # a unit denominator
    r"(?![A-Za-z]{3})"  # a word
    r"(?!a\d)"  # a bar spacing or a paper size
    r"(?:(?<=[A-Za-z]{2}/)|(?![A-Za-z](?![A-Za-z0-9{}])))"  # one letter ending the token
    r"[A-Za-z{}]"
)
_WORD = re.compile(r"[A-Za-z]+")
_TONE_LETTER = re.compile(r"(?:[aeiouy]|(?<=[a-z])[AEO])[SFRXJ]")
_CAPITAL_VOWEL = re.compile(r"(?<=[a-z])[AEIOUY](?=[a-z])")
_CAMEL_CASE = re.compile(r"[A-Z][a-z]+(?:[A-Z](?=[a-z]*[aeiouy])[a-z]{2,})+")


def looks_legacy_ascii(text: str) -> bool:
    """True when ASCII `text` has a shape legacy Vietnamese fonts give when written in ASCII (see above)."""
    if _SLASH_LETTER.search(text):
        return True
    return any(
        not _CAMEL_CASE.fullmatch(word) and (_TONE_LETTER.search(word) or _CAPITAL_VOWEL.search(word))
        for word in _WORD.findall(text)
    )


def _flag_legacy_ascii(ctx: _Context) -> None:
    """Flag `legacy_ascii_suspect` (confidence low) on each pure-ASCII entry with a legacy-looking run in a
    TCVN3 / VNI font, in an unknown-encoding font with a legacy name, or in one that holds non-ASCII text of
    unknown encoding."""
    for entry, runs in ctx.ascii_suspects:
        if any(
            enc in ("tcvn3", "vni") or legacy_name or key in ctx.unknown_non_ascii_fonts
            for key, enc, legacy_name in runs
        ):
            entry["flags"].append("legacy_ascii_suspect")
            entry["confidence"] = "low"


# --- entities ------------------------------------------------------------------------


@dataclass(frozen=True)
class _Frame:
    space: str  # 'model' or the layout name
    layout: str
    coordinate_frame: str  # wcs | paper
    block_path: tuple[str, ...] = ()
    insert_handles: tuple[str | None, ...] = ()
    container_layer: str | None = None  # effective layer of the INSERT whose definition we are reading
    insert_invisible: bool = (
        False  # an INSERT on the way down has group 60 = 1 (print_uncertain: insert_invisible)
    )


def _point(entity: Any, point: Vec3) -> tuple[float | None, float | None]:
    """x, y in WCS of an OCS point (TEXT, ATTRIB, DIMENSION). Non-finite numbers become None."""
    try:
        ocs = entity.ocs()
        wcs = ocs.to_wcs(point) if ocs.transform else point
    except Exception:
        wcs = point
    return num(wcs.x), num(wcs.y)


def _layer_fields(ctx: _Context, frame: _Frame, layer: str) -> tuple[str, str | None, str]:
    """(effective layer, definition layer when it was replaced, layer state)."""
    effective, definition = layer, None
    if frame.container_layer is not None and layer == "0":
        effective, definition = frame.container_layer, layer
    return effective, definition, ctx.layer_state.get(effective.casefold(), "unknown")


def _visibility(
    ctx: _Context,
    frame: _Frame,
    *,
    entity: Any,
    entity_type: str,
    layer: str,
    state: str,
    attribute_flag: bool,
    own_insert_invisible: bool,
) -> tuple[list[str], list[str]]:
    """(not_printed_reasons, print_uncertain_reasons) of one entry, `layer` being its effective layer.

    A hard reason is a setting Autodesk documents as keeping the object off the printed sheet: group 60 on the
    entity, ATTRIB flag bit 1 (unless `$ATTMODE` 2 shows every attribute), the layer off, frozen or plot 0.
    With any, the entry is not printed and nothing uncertain is listed. Otherwise the entry stays printed and
    lists what the file does not settle: an INSERT with group 60 above it, `$ATTMODE` != 1 on an attribute, a
    layer frozen in some viewport (model space text only) and the Defpoints layer.
    """
    attribute = entity_type == "ATTRIB"
    attmode_overrides = attribute and ctx.attmode != 1
    key = layer.casefold()
    hard: list[str] = []
    if entity.dxf.get("invisible", 0):
        hard.append("entity_invisible")
    if attribute_flag and not (attribute and ctx.attmode == 2):
        hard.append("attribute_invisible")
    if state == "off":
        hard.append("layer_off")
    if state == "frozen":
        hard.append("layer_frozen")
    if key in ctx.layer_no_plot:
        hard.append("layer_no_plot")
    if hard:
        return hard, []
    uncertain: list[str] = []
    if frame.insert_invisible or own_insert_invisible:
        uncertain.append("insert_invisible")
    if attmode_overrides:
        uncertain.append("attmode_not_normal")
    if frame.space == "model" and key in ctx.viewport_frozen:
        uncertain.append("viewport_frozen")
    if key == "defpoints":
        uncertain.append("defpoints_layer")
    return hard, uncertain


def _handle_of(ctx: _Context, entity: DXFEntity) -> str | None:
    handle = entity.dxf.get("handle")
    return str(handle) if ctx.handles_ok and handle else None


def _add_entry(
    ctx: _Context,
    frame: _Frame,
    *,
    entity: Any,
    entity_type: str,
    raw: str,
    style: str | None,
    mtext: bool,
    layer: str,
    position: tuple[float | None, float | None],
    position_basis: str,
    alignment: str | None,
    height: float | None,
    rotation: float | None,
    handle: str | None,
    definition_handle: str | None = None,
    tag: str | None = None,
    block_name: str | None = None,
    insert_handle: str | None = None,
    invisible: bool | None = None,
    text_rule: str | None = None,
    extra_flags: tuple[str, ...] = (),
    dimension: bool = False,
    insert_invisible: bool = False,
) -> None:
    if raw.strip() == "":
        ctx.empty_skipped += 1
        return
    font_file, style_exists = ctx.style_font(style)
    decoded = _decode_text(ctx, raw, style, mtext=mtext)
    suspect_runs = decoded.pop("_suspect_runs")
    flags = list(extra_flags) + decoded.pop("flags")
    if has_lone_surrogate(raw):  # undecodable bytes: scrubbed on output, so say it here
        flags.append("invalid_utf8_bytes")
        decoded["confidence"] = "low"
    if style is not None and not style_exists:
        flags.append("style_not_found")
    effective, definition, state = _layer_fields(ctx, frame, layer)
    if state in ("off", "frozen"):
        flags.append(f"layer_{state}")
    if definition is not None:
        flags.append("layer_from_insert")
    if invisible:
        flags.append("attribute_invisible")
    not_printed, uncertain = _visibility(
        ctx,
        frame,
        entity=entity,
        entity_type=entity_type,
        layer=effective,
        state=state,
        attribute_flag=bool(invisible),
        own_insert_invisible=insert_invisible,
    )
    extrusion = entity.dxf.get("extrusion") if entity.dxf.is_supported("extrusion") else None
    if extrusion is not None and tuple(extrusion) != (0.0, 0.0, 1.0):
        flags.append("non_default_extrusion")
    entry: dict[str, Any] = {
        "id": f"T{len(ctx.entries) + 1:06d}",
        "entity_type": entity_type,
        "space": frame.space,
        "layout": frame.layout,
        "coordinate_frame": frame.coordinate_frame,
        "layer": effective,
        "definition_layer": definition,
        "layer_state": state,
        "style": style,
        "font_file": font_file,
        "position": {"x": position[0], "y": position[1], "basis": position_basis},
        "alignment": alignment,
        "height": height,
        "rotation": rotation,
        "handle": handle,
        "definition_handle": definition_handle,
        "block_path": list(frame.block_path),
        "insert_handles": list(frame.insert_handles),
        "tag": tag,
        "block_name": block_name,
        "insert_handle": insert_handle,
        "invisible": invisible,
        "text_rule": text_rule,
        "raw_text": raw,
        **decoded,
        "provenance": {
            "file": ctx.source or str(ctx.path),
            "sheet": SHEET_UNKNOWN,
            "method": "dxf_dimension_text" if dimension else "dxf_entity",
        },
    }
    entry["flags"] = flags
    entry["printed"] = not not_printed
    entry["not_printed_reasons"] = not_printed
    entry["print_uncertain_reasons"] = uncertain
    ctx.entries.append(entry)
    if suspect_runs and raw.isascii():
        ctx.ascii_suspects.append((entry, suspect_runs))


def _definition_handle(ctx: _Context, entity: Any) -> str | None:
    source = getattr(entity, "source_of_copy", None)
    if source is None:
        return None
    return _handle_of(ctx, source) if source is not entity else None


def _text_like(ctx: _Context, frame: _Frame, e: Any, entity_type: str, **owner: Any) -> None:
    """TEXT or ATTRIB."""
    align, p1, _p2 = e.get_placement()
    basis = "insert" if e.dxf.get("halign", 0) == 0 and e.dxf.get("valign", 0) == 0 else "align_point"
    layer = str(e.dxf.get("layer", "0"))
    _add_entry(
        ctx,
        frame,
        entity=e,
        entity_type=entity_type,
        raw=str(e.dxf.get("text", "")),
        style=str(e.dxf.get("style", "Standard")),
        mtext=False,
        layer=layer,
        position=_point(e, p1),
        position_basis=basis,
        alignment=align.name,
        height=num(e.dxf.get("height")),
        rotation=num(e.dxf.get("rotation", 0.0)),
        handle=_handle_of(ctx, e),
        definition_handle=_definition_handle(ctx, e),
        **owner,
    )


def _mtext(ctx: _Context, frame: _Frame, e: Any) -> None:
    _add_entry(
        ctx,
        frame,
        entity=e,
        entity_type="MTEXT",
        raw=str(e.text),
        style=str(e.dxf.get("style", "Standard")),
        mtext=True,
        layer=str(e.dxf.get("layer", "0")),
        position=(num(e.dxf.insert.x), num(e.dxf.insert.y)),
        position_basis="insert",
        alignment=MTextEntityAlignment(e.dxf.get("attachment_point", 1)).name,
        height=num(e.dxf.get("char_height")),
        rotation=num(e.get_rotation()),
        handle=_handle_of(ctx, e),
        definition_handle=_definition_handle(ctx, e),
    )


def _style_name(ctx: _Context, handle: str | None) -> str | None:
    target = ctx.doc.entitydb.get(handle) if handle else None
    return str(target.dxf.name) if target is not None and target.dxf.hasattr("name") else None


def _multileader(ctx: _Context, frame: _Frame, e: Any) -> None:
    mleader_layer = str(e.dxf.get("layer", "0"))
    context = e.context
    mtext = context.mtext
    if mtext is not None:
        style = _style_name(ctx, mtext.style_handle)
        rotation = math.degrees(mtext.rotation)
        _add_entry(
            ctx,
            frame,
            entity=e,
            entity_type="MULTILEADER",
            raw=str(mtext.default_content),
            style=style,
            mtext=True,
            layer=mleader_layer,
            position=(num(mtext.insert.x), num(mtext.insert.y)),
            position_basis="context_mtext_insert",
            alignment=None,
            height=num(context.char_height),
            rotation=num(rotation),
            handle=_handle_of(ctx, e),
            definition_handle=_definition_handle(ctx, e),
            extra_flags=() if style else ("style_unresolved",),
        )
        return
    if context.block is None:
        return
    # Block content: the visible text lives in attributes stored on the MULTILEADER itself.
    origin = context.block.insert
    entitydb = ctx.doc.entitydb
    for attr in e.block_attribs:
        attdef = entitydb.get(attr.handle)
        tag = str(attdef.dxf.get("tag")) if attdef is not None else None
        style = str(attdef.dxf.get("style", "Standard")) if attdef is not None else None
        _add_entry(
            ctx,
            frame,
            entity=e,
            entity_type="MULTILEADER",
            raw=str(attr.text),
            style=style,
            mtext=False,
            layer=mleader_layer,
            position=(num(origin.x), num(origin.y)),
            position_basis="context_block_insert",
            alignment=None,
            height=None,
            rotation=None,
            handle=_handle_of(ctx, e),
            definition_handle=_definition_handle(ctx, e),
            tag=tag,
            extra_flags=("block_content_attribute", "position_is_block_insert"),
        )


def _dimension(ctx: _Context, frame: _Frame, e: Any) -> None:
    text = str(e.dxf.get("text", ""))
    if text in ("", "<>", " "):  # measured value, or suppressed: the probe's job
        ctx.dimensions_without_override += 1
        return
    rule = "measured_with_text" if "<>" in text else "override"
    style: str | None = None
    try:
        style = str(e.override().get("dimtxsty") or "") or None
    except Exception:
        style = None
    mid = e.dxf.get("text_midpoint")
    _add_entry(
        ctx,
        frame,
        entity=e,
        entity_type="DIMENSION",
        raw=text,
        style=style,
        mtext=True,
        layer=str(e.dxf.get("layer", "0")),
        position=_point(e, mid) if mid is not None else (None, None),
        position_basis="text_midpoint",
        alignment=None,
        height=None,
        rotation=num(e.dxf.get("text_rotation")) if e.dxf.hasattr("text_rotation") else None,
        handle=_handle_of(ctx, e),
        definition_handle=_definition_handle(ctx, e),
        text_rule=rule,
        extra_flags=() if style else ("style_unresolved",),
        dimension=True,
    )


# --- blocks --------------------------------------------------------------------------


def _info(ctx: _Context, name: str) -> tuple[bool, tuple[str, ...]]:
    """(block holds text-bearing entities itself, names of blocks it inserts)."""
    key = name.casefold()
    if key not in ctx.block_info:
        direct = False
        children: list[str] = []
        block = ctx.doc.blocks.get(name)  # None when the block does not exist
        if block is not None:
            for e in block:
                kind = e.dxftype()
                if kind in _TEXT_TYPES:
                    direct = True
                elif kind == "INSERT":
                    if getattr(e, "attribs", None):
                        direct = True
                    children.append(str(e.dxf.get("name", "")))
        ctx.block_info[key] = (direct, tuple(children))
    return ctx.block_info[key]


def _bears_text(ctx: _Context, name: str) -> bool:
    """True when the block, or a block it inserts at any depth, holds text. Cycle-safe, memoised."""
    key = name.casefold()
    if key in ctx.bears_text:
        return ctx.bears_text[key]
    stack, seen, found = [name], set(), False
    while stack and not found:
        current = stack.pop()
        if current.casefold() in seen:
            continue
        seen.add(current.casefold())
        direct, children = _info(ctx, current)
        if direct:
            found = True
        else:
            stack.extend(children)
    ctx.bears_text[key] = found
    if not found:
        for k in seen:
            ctx.bears_text[k] = False
    return found


def _is_xref(ctx: _Context, name: str) -> bool:
    block = ctx.doc.blocks.get(name)
    return block is not None and block.block is not None and block.block.is_xref


def _record_error(
    ctx: _Context, frame: _Frame, entity: DXFEntity | None, entity_type: str, exc: BaseException
) -> None:
    ctx.errors_total += 1
    if len(ctx.errors) < MAX_ERRORS_LISTED:
        ctx.errors.append(
            {
                "handle": _handle_of(ctx, entity) if entity is not None else None,
                "entity_type": entity_type,
                "space": frame.space,
                "block_path": list(frame.block_path),
                "error": f"{type(exc).__name__}: {exc}",
            }
        )


def _visit_insert(ctx: _Context, frame: _Frame, ins: Any) -> None:
    name = str(ins.dxf.get("name", ""))
    insert_handle = _handle_of(ctx, ins)
    for attrib in ins.attribs:
        try:
            _text_like(
                ctx,
                frame,
                attrib,
                "ATTRIB",
                tag=str(attrib.dxf.get("tag", "")),
                block_name=name,
                insert_handle=insert_handle,
                invisible=bool(attrib.dxf.get("flags", 0) & 1),
                insert_invisible=bool(ins.dxf.get("invisible", 0)),
            )
        except Exception as exc:
            _record_error(ctx, frame, attrib, "ATTRIB", exc)
    if _is_xref(ctx, name):
        ctx.xref_inserts_skipped += 1
        return
    if ctx.doc.blocks.get(name) is None:
        ctx.missing_block_inserts += 1
        return
    if not _bears_text(ctx, name):
        return
    if len(frame.block_path) >= MAX_BLOCK_DEPTH:
        ctx.depth_limit_count += 1
        return
    if name.casefold() in {n.casefold() for n in frame.block_path}:
        ctx.cycle_count += 1
        return
    own_layer = _layer_fields(ctx, frame, str(ins.dxf.get("layer", "0")))[0]
    child = replace(
        frame,
        block_path=(*frame.block_path, name),
        insert_handles=(*frame.insert_handles, insert_handle),
        container_layer=own_layer,
        insert_invisible=frame.insert_invisible or bool(ins.dxf.get("invisible", 0)),
    )
    instances = list(ins.multi_insert()) if getattr(ins, "mcount", 1) > 1 else [ins]
    for instance in instances:
        _visit_virtual(ctx, child, instance)


def _skipped(ctx: _Context, entity: DXFEntity, reason: str) -> None:
    kind = entity.dxftype()
    ctx.transform_skipped[kind] += 1
    if len(ctx.transform_skipped_listed) < MAX_SKIPPED_LISTED:
        ctx.transform_skipped_listed.append({"entity_type": kind, "reason": reason})


def _virtual_children(ctx: _Context, frame: _Frame, ins: Any) -> Iterator[Any]:
    """virtual_entities() with a failure counted instead of raised (a generator dies on its first error)."""
    iterator = ins.virtual_entities(skipped_entity_callback=lambda e, reason: _skipped(ctx, e, reason))
    while True:
        try:
            yield next(iterator)
        except StopIteration:
            return
        except Exception as exc:
            _record_error(ctx, frame, ins, "INSERT", exc)
            return


def _visit_virtual(ctx: _Context, frame: _Frame, ins: Any) -> None:
    for child in _virtual_children(ctx, frame, ins):
        _visit_entity(ctx, frame, child)


def _visit_entity(ctx: _Context, frame: _Frame, e: Any) -> None:
    kind = e.dxftype()
    try:
        if kind == "TEXT":
            _text_like(ctx, frame, e, "TEXT")
        elif kind == "MTEXT":
            _mtext(ctx, frame, e)
        elif kind in ("MULTILEADER", "MLEADER"):
            _multileader(ctx, frame, e)
        elif kind == "DIMENSION":
            _dimension(ctx, frame, e)
        elif kind == "INSERT":
            _visit_insert(ctx, frame, e)
        elif kind in _NOT_EXTRACTED_TYPES:
            ctx.not_extracted[kind] += 1
    except Exception as exc:  # counted and listed, never dropped
        _record_error(ctx, frame, e, kind, exc)


# --- definitions and summary ---------------------------------------------------------


def _attdefs(ctx: _Context) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for block in ctx.doc.blocks:
        if block.is_any_layout or (block.block is not None and block.block.is_xref):
            continue
        for e in block.query("ATTDEF"):
            flags = int(e.dxf.get("flags", 0))
            insert = e.dxf.get("insert", Vec3())
            out.append(
                {
                    "space": f"block:{block.name}",
                    "coordinate_frame": "block_definition",
                    "block": block.name,
                    "tag": str(e.dxf.get("tag", "")),
                    "prompt": str(e.dxf.get("prompt", "")),
                    "default_text": str(e.dxf.get("text", "")),
                    "layer": str(e.dxf.get("layer", "0")),
                    "style": str(e.dxf.get("style", "Standard")),
                    "position": {"x": num(insert.x), "y": num(insert.y)},
                    "height": num(e.dxf.get("height")),
                    "invisible": bool(flags & 1),
                    "constant": bool(flags & 2),
                    "handle": _handle_of(ctx, e),
                }
            )
    return out


def _top(counter: Counter[str]) -> dict[str, Any]:
    ranked = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    return {
        "total_distinct": len(counter),
        "top": [{"name": k, "count": v} for k, v in ranked[:MAX_TOP]],
        "truncated": len(ranked) > MAX_TOP,
    }


def _summary(ctx: _Context) -> dict[str, Any]:
    entries = ctx.entries
    unknown_by_style: Counter[str] = Counter()
    for e in entries:
        if e["decode"]["encoding_used"] in ("unknown", "mixed"):
            unknown_by_style[str(e["style"])] += 1
    return {
        "total_entries": len(entries),
        "by_entity_type": dict(sorted(Counter(e["entity_type"] for e in entries).items())),
        "by_space": _top(Counter(e["space"] for e in entries)),
        "by_layer": _top(Counter(e["layer"] for e in entries)),
        "by_encoding_used": dict(sorted(Counter(e["decode"]["encoding_used"] for e in entries).items())),
        "by_confidence": dict(sorted(Counter(e["confidence"] for e in entries).items())),
        "unknown_or_mixed_encoding_by_style": _top(unknown_by_style),
        "case_uncertain_count": sum(1 for e in entries if e["decode"]["case_uncertain"]),
        "in_block_count": sum(1 for e in entries if e["block_path"]),
        "depth_limit_count": ctx.depth_limit_count,
        "max_block_depth": MAX_BLOCK_DEPTH,
        "cycle_count": ctx.cycle_count,
        "xref_inserts_skipped": ctx.xref_inserts_skipped,
        "missing_block_inserts": ctx.missing_block_inserts,
        "empty_text_skipped": ctx.empty_skipped,
        "dimensions_without_override": ctx.dimensions_without_override,
        "not_extracted": dict(sorted(ctx.not_extracted.items())),
        "transform_skipped": {
            "count": sum(ctx.transform_skipped.values()),
            "by_entity_type": dict(sorted(ctx.transform_skipped.items())),
            "listed": ctx.transform_skipped_listed,
        },
        "errors_total": ctx.errors_total,
        "errors": ctx.errors,
    }


# --- entry point ---------------------------------------------------------------------


def _layer_states(doc: Drawing) -> dict[str, str]:
    states: dict[str, str] = {}
    for layer in doc.layers:
        state = "frozen" if layer.is_frozen() else "off" if not layer.is_on() else "on"
        states[str(layer.dxf.name).casefold()] = state
    return states


def _layer_no_plot(doc: Drawing) -> frozenset[str]:
    """Case-folded names of the layers whose plot flag (group 290) is 0. Defpoints is left out: ezdxf sets its
    flag to 0 on every load, so the file's own value is unknown there (it is `defpoints_layer`, uncertain)."""
    return frozenset(
        str(layer.dxf.name).casefold()
        for layer in doc.layers
        if int(layer.dxf.get("plot", 1)) == 0 and str(layer.dxf.name).casefold() != "defpoints"
    )


def _viewport_frozen(doc: Drawing) -> frozenset[str]:
    """Layers frozen in at least one viewport of any layout (VIEWPORT group 331), case-folded."""
    return frozenset(
        name.casefold()
        for layout in doc.layouts
        for viewport in layout.query("VIEWPORT")
        if isinstance(viewport, Viewport)
        for name in viewport.frozen_layers
    )


def extract_text(
    path: str | Path,
    converter: str = "none",
    knowledge: FontEncodingTable | None = None,
    *,
    source: str | None = None,
) -> dict[str, Any]:
    """Index every piece of text in one DXF. Raises OSError if the file cannot be hashed, ValueError for a
    bad converter, KnowledgeError for a malformed knowledge table. A DXF ezdxf cannot open is returned with
    `status: "unreadable"`, not raised. A failing entity is listed in `summary.errors` and the status is
    'partial'. `knowledge`: font-encoding table; default is the shipped `knowledge/font-encodings.csv`.
    `source`: the path recorded in `file.path` and every `provenance.file` (intake passes the path relative
    to the project input folder, common.schema.json); default: `path` as given.
    """
    result = _extract_text(path, converter, knowledge, source)
    clean, scrubbed = scrub_surrogates(result)
    if scrubbed and "warnings" in clean:
        clean["warnings"].append(
            f"{scrubbed} character(s) were bytes that are not valid UTF-8 (a damaged or mis-converted file): "
            "replaced by U+FFFD; the entries concerned are flagged invalid_utf8_bytes."
        )
    return clean


def _extract_text(
    path: str | Path,
    converter: str = "none",
    knowledge: FontEncodingTable | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """The extraction itself; `extract_text` adds the UTF-8 scrub."""
    if converter not in CONVERTER_CAPS:
        raise ValueError(f"unknown converter '{converter}'; choose from {', '.join(CONVERTER_CAPS)}")
    path = Path(path)
    cap = CONVERTER_CAPS[converter]
    table = knowledge if knowledge is not None else default_font_encodings()
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "ok",
        "file": {
            "path": source or str(path),
            "sha256": sha256_file(path),
            "ezdxf_version": EZDXF_VERSION,
            "dxf_version": None,
            "converter": converter,
            "confidence_cap": cap,
            "handles_reliable": False,
            "codepage": None,
        },
    }
    doc: Drawing | None = None
    with timed_attempt("ezdxf", EZDXF_VERSION) as attempt:
        try:
            doc = readfile(str(path))
        except Exception as exc:  # recorded as a failed attempt and returned as JSON
            attempt.fail(f"{type(exc).__name__}: {exc}")
    result["attempts"] = [attempt.as_dict()]
    if doc is None:
        result.update(status="unreadable", error=attempt.error)
        return result

    warnings: list[str] = []
    version = doc.header.get("$ACADVER")
    result["file"]["dxf_version"] = str(version) if version else None
    try:
        handles_ok = bool(handles_reliable(doc, path))
    except Exception as exc:
        handles_ok = False
        warnings.append(
            f"handle reliability could not be determined ({type(exc).__name__}: {exc}): no handles"
        )
    result["file"]["handles_reliable"] = handles_ok
    # R2007+ (AC1021) files are UTF-8 whatever $DWGCODEPAGE says; ezdxf still reports that header value
    codepage = "utf8" if str(doc.dxfversion) >= _UNICODE_VERSION else str(doc.encoding)
    result["file"]["codepage"] = codepage
    if not handles_ok:
        warnings.append("This DXF stores no usable entity handles (R12-era): handle fields are null.")
    if codepage.lower().replace("-", "_") not in _UTF8_LIKE:
        warnings.append(
            f"File code page is {codepage}: legacy text is re-encoded with it before conversion "
            "(encoding.py); not validated on a real file."
        )

    ctx = _Context(
        doc,
        path,
        cap,
        handles_ok,
        _layer_states(doc),
        layer_no_plot=_layer_no_plot(doc),
        viewport_frozen=_viewport_frozen(doc),
        attmode=int(doc.header.get("$ATTMODE", 1)),
        knowledge=table,
        codepage=codepage,
        source=source or str(path),
    )
    for name in doc.layout_names_in_taborder():
        layout = doc.layouts.get(name)
        is_model = bool(layout.is_modelspace)
        frame = _Frame("model" if is_model else name, name, "wcs" if is_model else "paper")
        for entity in layout:
            _visit_entity(ctx, frame, entity)
    _flag_legacy_ascii(ctx)
    attdefs: list[dict[str, Any]] = []
    try:
        attdefs = _attdefs(ctx)
    except Exception as exc:
        ctx.errors_total += 1
        ctx.errors.append(
            {
                "handle": None,
                "entity_type": "ATTDEF",
                "space": "block",
                "block_path": [],
                "error": f"{type(exc).__name__}: {exc}",
            }
        )

    if converter == "libredwg":
        warnings.append("DXF produced by the fallback converter (libredwg): confidence capped at medium.")
    summary = _summary(ctx)
    if ctx.errors_total:
        result["status"] = "partial"
    if ctx.depth_limit_count:
        warnings.append(
            f"{ctx.depth_limit_count} insert(s) nested deeper than {MAX_BLOCK_DEPTH} levels "
            "were not expanded."
        )
    if ctx.xref_inserts_skipped:
        warnings.append(
            f"{ctx.xref_inserts_skipped} insert(s) of external references: their text is not indexed."
        )
    if ctx.transform_skipped:
        warnings.append(
            f"{sum(ctx.transform_skipped.values())} block entit(ies) could not be transformed by ezdxf "
            "and are not indexed; see summary.transform_skipped."
        )
    for _line, (row_, per_style) in sorted(ctx.proposed_hits.items()):
        names = ", ".join(sorted(per_style))
        warnings.append(
            f"{sum(per_style.values())} entr(ies) in text style(s) {names} match the PROPOSED knowledge row "
            f"{row_.cite()}: not applied, their encoding stays unknown (see the font_encoding_proposed "
            "question)."
        )
    if ctx.not_extracted:
        warnings.append(
            "Text-bearing entities this slice cannot read were counted, not indexed: "
            + ", ".join(f"{n} x {t}" for t, n in sorted(ctx.not_extracted.items()))
        )
    result.update(
        entries=ctx.entries,
        attdefs=attdefs,
        summary=summary,
        warnings=warnings,
    )
    return result
