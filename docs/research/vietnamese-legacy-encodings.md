# Vietnamese legacy font encodings (TCVN3, VNI) — sources and limits

Step 1 slice S4 (RTI-0004). Code: `src/tekla_harness/encoding.py`; tests: `tests/test_encoding.py`.
Retrieved 2026-11-06. All downloads were read only, never executed.

## Sources

| # | Source | Licence | Used for |
|---|---|---|---|
| 1 | Vietnamese Unicode FAQs, "Unicode & Vietnamese Legacy Character Encodings", https://vietunicode.sourceforge.net/charset/ | none stated on the page | **Generated the tables** (134 rows: Unicode, VNI, TCVN3 columns) |
| 2 | Wikipedia "VSCII" (wikitext of the code-point grid, VSCII-3 cells), https://en.wikipedia.org/wiki/VSCII | CC BY-SA 4.0 | Cross-check of TCVN3 (74 bytes); also the VSCII-3 structure (67 lowercase + 7 capitals) |
| 3 | UniKey VnConv tables, `ukengine/data.cpp` in https://github.com/vn-input/ibus-unikey (licence from Debian `copyright`: GPL-2.0-or-later for `data.cpp`) | GPL-2.0-or-later | Cross-check of TCVN3 and VNI-WIN, all entries. Read only, nothing copied |
| 4 | Wikipedia "VNI" (ANSI grid; it cites source 1, so **not independent**), https://en.wikipedia.org/wiki/VNI | CC BY-SA 4.0 | Mark-byte layout of VNI (e.g. 0xD8 grave on capitals, 0xF8 on lowercase) |
| 5 | bogotiengviet.com "fontchu-bangma" (Web Archive 2010-11-20) | unknown | Font names: `.Vn…` = TCVN3, `VNI-…` = VNI; Unicode fonts = Times New Roman, Arial, Tahoma, Courier New, Verdana |
| 6 | mytour.vn "character encodings corresponding to fonts" | unknown | Font names: `.Vn`/`VH` = TCVN3, `VNI-` = VNI, `Vn` = Vietware X, `SVN` = Vietware F, `UVF` = Unicode |

Only 2 witnesses exist for `.Vn…` and `VNI-…` (5 and 6). `VH`, `SVN`, `UVF` and `Vn` (no dot) have
one witness (6) of grade C, so `guess_encoding_from_font` returns `unknown` for them. Source 6 and the
`.Vn` rule conflict on `Vn` vs `.Vn` only by the dot; the dot is the deciding character.

## How the tables were made (reproducible)

1. Source 1: parse the HTML `<tr>` rows with 12 cells; take Unicode (col 2), VNI hex (col 4), TCVN3 hex (col 10). 134 rows.
2. TCVN3: bytes 0xA1-0xAE are single-case (marked bases). The 60 other bytes are shared by a lowercase and an
   uppercase letter (source 1 prints the capital as `A` + the same byte and says capitals live in a separate capital
   font and its capital column "is not correct"). Only the lowercase is stored; the capital is `str.upper()`
   (checked equal to source 1 and 3 for all 60).
3. Compared entry by entry with source 2 (74 bytes), source 3 (74 TCVN3 bytes + 134 VNI sequences) and the mark layout of
   source 4. Result: **zero differences**; an independent review re-checked the counts (74 TCVN3 bytes, 134 VNI sequences).
   The two fixtures in the test file were transcribed from sources 2 and 3 (not from 1) by the same agent session that
   wrote the module; the transcription script was not kept. They are independent of the module in source only, not in
   process (see the header of `tests/test_encoding.py`).

## Where sources disagree

Nothing, for any code point. The only structural fact is that TCVN3 has no toned capitals in its bytes (below).

## Behaviour that is easy to get wrong

* **Case in TCVN3** is not in the bytes. Toned letters use the same bytes in the normal (lowercase) font and in the
  all-capital font; no fetched source says how an all-capital font draws a-z or the marked bases 0xA8-0xAE. The
  converter never silently mixes cases. `capital_font=True`: toned letters and 0xA8-0xAE become uppercase, lowercase
  ASCII a-z is kept but **each letter is reported** in `ambiguous` (reason: renders as capital in most `.VnXxxH` fonts,
  unverified). `capital_font=None` (unknown): output is lowercase and toned letters, 0xA8-0xAE and a-z are all reported.
  `capital_font=False`: nothing reported. `ConversionResult.case_uncertain` is True whenever anything was reported.
  Real example (style `.VnAvantH`): `mÆt b»ng §ÞNH VÞ CéT T1` with `True` gives `mẶt bẰng ĐỊNH VỊ CỘT T1`, with m t b n g
  flagged; it still needs the engineer (or a rendering check) to settle the case of a-z.
* **`font_hint(style_name, font_file)`** returns the encoding and `capital_font`: True when the style name looks like
  legacy Vietnamese (`.Vn…`, dot optional) and ends with `H`, False without the `H`, None otherwise. The `H` suffix is an
  **observed naming convention, not verified against a font spec**: a hint only. Evidence from the sample drawing
  `dwg-lab/samples/converted/L3-complex/dwgshare-rc-projects/267_4-story_house_complete_project.dxf` (read-only, untrusted
  data): style `.VnAvantH` uses font file `VHAVAN.TTF`; style `VntimeH` uses `vntimeh.shx`; style `TKT_TieuDe` uses
  `vntimeh.shx`; the text `mÆt b»ng §ÞNH VÞ CéT T1` uses `.VnAvantH`. File names such as `VHAVAN.TTF` and `vntimeh.shx`
  return `unknown` for the encoding (conservative); the engineer can decide whether to map `VH*` / `vn*.shx` file names.
  `VntimeH` has no dot, so its encoding stays `unknown` while its `capital_font` hint is True.
* **VNI** is base byte + mark byte; case is in the bytes (grave: `A`+D8, `a`+F8). Longest match first, because
  Ơ Ư ơ ư are both letters and bases. Case-mismatched or orphan marks are kept and reported in `unmapped`.
* **Input form**: str of code points 0x00-0xFF = bytes decoded as latin-1. Every mapped byte is >= 0xA1, where cp1252
  equals latin-1 (tested). cp1252-only characters (euro sign etc.) and real Unicode letters are kept and reported.
  A DXF with another `$DWGCODEPAGE` (for example ANSI_1258) must be re-encoded to bytes and decoded as latin-1 first
  (`s.encode("cp1258").decode("latin-1")`; the round trip is tested for every TCVN3 byte, the DXF reader side is not).
* **Convert before expanding `%%c`/`%%d`**: U+00D8 is a letter in TCVN3 (`ỉ`) and, in VNI, the uppercase grave mark
  (byte 0xD8). In VNI a diameter sign right after A E O U Y (or Ơ Ư) is absorbed: `convert_legacy("AØ", "vni")` gives
  `À` by design; a standalone `Ø` is reported in `unmapped`.
* **NFD-damaged input**: combining marks (category Mn) in the input mean the string was decomposed upstream. Each is
  reported in `unmapped` and `ConversionResult.nfd_damaged` is set. The output is NFC; `index` in `unmapped`/`ambiguous`
  always refers to the input string.
* **C0 bytes in TCVN3**: 0x01-0x17 hold capitals in other TCVN 5712 tables (VN1). They are reported in `unmapped`;
  tab, LF and CR are exempt (a choice made here, not taken from a source).
* **False positives**: the converter does not detect legacy text. Real Unicode text that only uses Latin-1 letters
  (`café`) is converted if the caller says `tcvn3` (`é` is 0xE9 = `ộ`). Pick the encoding from the font name first.
  A statistical `looks_like_legacy` was deliberately not written (no real sample to measure false positives).
* Bytes >= 0x80 that are not in a table (symbol glyphs in the fonts, for example 0xB0) are kept and reported as
  unmapped. U+00A0 (no-break space) passes through silently.

## Licence caveat (engineer decision)

The repository licence is proprietary. No source above is permissive: source 1 states no licence, source 3 is GPL,
source 2 is CC BY-SA. The table is a factual code-point mapping of TCVN 5712:1993 (VN3) and of the VNI layout, generated
from source 1 and verified against the others; no code or table expression from the GPL source was copied. The engineer
should confirm this is acceptable, or replace the table with one from TCVN 5712:1993 itself.

**OPEN decision for the engineer:** the licence status of the tables is not settled.

## Not validated

* One real sample DXF was inspected read-only (see `font_hint` evidence above); the converter was not validated against
  a known-correct reading of its text.
* `guess_encoding_from_font` expects a font name (style name, extended data or MTEXT `\f` code). Only `.ttf/.otf/.ttc`
  are stripped; `.shx` is not, so `.VnTime.shx` returns `tcvn3` (leading dot decides) while `vntimeh.shx` returns
  `unknown`. Whether real font files keep the leading dot (`.vntime.ttf` vs `vntime.ttf`) is not known.
* The `H`-suffix rule of `font_hint` rests on the style names of one sample drawing plus common usage; unverified.
* VNI for Mac/DOS and VISCII/VPS/Windows-1258 are out of scope (VNI Windows only).
* The wheel needs no change: tables are Python literals in `encoding.py`.
