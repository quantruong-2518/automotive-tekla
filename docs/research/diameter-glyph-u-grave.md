# `ù` used as the diameter sign in rebar callouts (`2ù20`, `ù10a150`)

- **Question:** why do some Vietnamese structural drawings show rebar callouts such as `2ù20`, `3ù20`,
  `ù10a150` where the drafter meant `Ø` (diameter)? Is there a documented cause, and is a decoding rule
  `ù` -> `Ø` safe? If so, how narrow must it be?
- **Evidence:** one known drawing, the archived EVAL-3 work folder
  `projects/_evals/eval3-2026-11-09/eval3/projects/eval3-h/work/`. The drawing is
  `290_4-story_house_9x12.3m.dwg`, with its text index `text/290_4-story_house_9x12.3m.dwg.json`, the DXF
  `converted/290_4-story_house_9x12.3m.dxf` (read with ezdxf and as raw bytes), `callouts.json` and
  `reader-questions.json`. Drawings 285 and 286 of the same set were used as counter-evidence. No
  held-out (EVAL-4) material was opened.
- **Date accessed:** 2026-11-09.
- **Status tags:** `verified` means read directly from the drawing data or quoted from a primary source.
  `inferred` means my deduction from verified facts. `not-found` means searched for and not found.
- **Answer in one line:** the cause is most likely a custom TrueType font, `CIC Arial Narrow E`, that
  draws a diameter glyph at code point U+00F9 (`ù`). The *meaning* `ù` = `Ø` is well supported by
  structure. The *cause* (what the font draws) is **inferred, not verified**: the font file and any
  vendor document for it were not found. A global rule would corrupt real Vietnamese text. The current
  `knowledge/font-encodings.csv` cannot hold a narrow rule, so **there is no safe row in the current
  table**. A schema extension is proposed below for the engineer to decide.

---

## 1. Problems first

| # | Rank | Problem | Reason | Fix (proposal only; nothing changed) |
|---|---|---|---|---|
| P1 | Major | `callouts` drops every `ù` callout without a trace. In drawing 290, 0 of 508 entries containing `ù` became a callout candidate. None was listed as unparsed or blocked, and `callouts-questions.json` raises no question about them. The 31 callouts that use `Þ` as a diameter sign in VNI styles (§6) are dropped the same way (0 candidates). | These are the beam, column and footing main bars of the file (`2ù20` ×117, `1ù20` ×105, `2ù18` ×81, …). In EVAL-3 only the reader's judgement caught the gap (`reader-questions.json` Q-144, blocking). A run without that judgement would lose the rebar silently. That breaks "never swallow an error". | Log an RTI: a line with a digit–non-ASCII letter–digit shape (`^\d*[^\x00-\x7F]\d+(a\d+)?$`) that matches no verified form should become an `unparsed` candidate with a question, not vanish. Ship it with a regression test built on these shapes. |
| P2 | Major | Style `Arial` is decoded as `unicode` because of its **style name**. Its TrueType family is `CIC Arial Narrow E`, a custom font, not Microsoft Arial. | `font_hint` tries the style name first, and `Arial` is in the list of Unicode fonts, so the family is never consulted. The sibling style `ArialH` uses family `CIC Arial NarrowH`, which holds TCVN3 text (§3). So the "unicode" verdict for this family is unverified, and every byte >= 0x80 in it passes the font gate as if it were a real Unicode letter. | Log an RTI. A style whose XDATA family differs from the style name's font should not be decided by the style name alone. The engineer should decide whether the family takes precedence. |
| P3 | Minor | Q-144 says "512 chữ chứa 'ù'". The text index holds **508** (507 in style `Arial`, 1 in `ArialH`), and 420 + 87 = 507. | Q-144 probably miscounted or included other entries. | Correct the count if Q-144 is reused. |
| P4 | Minor | The code points come from **LibreDWG** (`inventory.json`: `converter: libredwg`, `confidence_cap: medium`). | If the converter mis-mapped the string, every byte-level fact below shifts. The source DWG is AC1021 (R2007), which stores text as Unicode, so a code-page mis-mapping is unlikely (inferred). | Re-read one entity with another reader (ODA/ACadSharp) or in AutoCAD to confirm U+00F9. |

---

## 2. Primary sources

| # | Source | URL | Used for |
|---|---|---|---|
| S1 | Unicode.org, Microsoft cp1252 mapping file | https://unicode.org/Public/MAPPINGS/VENDORS/MICSFT/WINDOWS/CP1252.TXT | `0xF9 0x00F9 #LATIN SMALL LETTER U WITH GRAVE`; `0xD8 0x00D8 #LATIN CAPITAL LETTER O WITH STROKE` |
| S2 | Unicode.org, Microsoft cp1258 (Vietnamese) mapping file | https://unicode.org/Public/MAPPINGS/VENDORS/MICSFT/WINDOWS/CP1258.TXT | `0xF9 0x00F9 #LATIN SMALL LETTER U WITH GRAVE` (same as cp1252); `0xDE 0x0303 #COMBINING TILDE` |
| S3 | Autodesk, AutoCAD Help "Text Symbols and Special Characters Reference" (2016) | https://help.autodesk.com/cloudhelp/2016/ENU/AutoCAD-Core/files/GUID-518E1A9D-398C-4A8A-AC32-2D85590CDBE1.htm | Table row: Diameter, control code `%%c`, Unicode string `U+2205` ("Precede the Unicode string with a backslash") |
| S4 | Vietnamese Unicode FAQs, "Unicode & Vietnamese Legacy Character Encodings" | https://vietunicode.sourceforge.net/charset/ | `ự` (U+1EF1): TCVN3 hex `F9`, VNI hex `F6 EF`. `ú` (U+00FA): VNI `75 F9`. `ù` (U+00F9): VNI `75 F8`, TCVN3 `EF` |
| S5 | Repo note `docs/research/vietnamese-legacy-encodings.md` and `src/tekla_harness/encoding.py` | — | TCVN3 / VNI tables built from S4 and cross-checked with zero differences (`0xF9: 0x1EF1`; VNI `"\x75\xf9": 0x00FA`) |
| S6 | ezdxf documentation, Textstyle | https://ezdxf.readthedocs.io/en/stable/tables/style_table_entry.html | Extended font data (family name) lives in XDATA, "not well documented … optional and not reliable!" |

All accessed 2026-11-09.

**Searched for, not found (`not-found`):** any vendor page, font specification or forum post naming the
font `CIC Arial Narrow E`, `CIC Arial NarrowH` or a "CIC" CAD font set. I tried English and Vietnamese
queries such as "CIC Arial Narrow E", "font CIC autocad thép phi" and "gõ ù ra ký hiệu phi". I found no
copy of the font on this machine (`/mnt/c/Windows/Fonts`, the user font folder, `fc-list`). No source
says that any font draws `Ø` at U+00F9 or at byte 0xF9.

---

## 3. Findings

### Q1. Which style and font do the `ù` entries use, and what is stored?

All `verified` (drawing data):

- **507 of 508** `ù` entries use text style **`Arial`**. In the STYLE table this style has font file
  `""` (empty) and bigfont `""`. Its family sits in XDATA `ACAD`: `1000 = "CIC Arial Narrow E"`,
  `1071 = 0`. There is no SHX and no bigfont, so the font is a TrueType font chosen by family name. The
  text index records `font_file: null` for these entries and `decode.encoding_used: "unicode"`, with
  `flags: []`.
- The 1 remaining entry uses style **`ArialH`** (family `CIC Arial NarrowH`). Its text is `ThÐp chÞu lùc`,
  which is TCVN3 for "Thép chịu lực". There `ù` is byte 0xF9, which TCVN3 reads as `ự` (S4). That entry is
  flagged `encoding_unknown_non_ascii`.
- **Stored form:** the DXF (AC1021, `$DWGCODEPAGE = ANSI_1252`) holds the character as raw UTF-8
  `C3 B9`, which is U+00F9. Example: TEXT handle `1288`, group 1 = `3\xc3\xb920`. It is not stored as
  `\U+00F9`, and it is not `%%c`. The source DWG is also AC1021 (`inventory.json`), so the DWG itself
  stores U+00F9. In cp1252 and in cp1258, U+00F9 is byte **0xF9** (S1, S2).
- **Position:** all 507 entries in style `Arial` match `^\d*ù\d+(a\d+)?$`. `ù` is the **only**
  non-ASCII character among the 2,267 entries of that style. Forms: `2ù20` ×117, `1ù20` ×105,
  `2ù18` ×81, `2ù16` ×38, `3ù20` ×36, `1ù18` ×35, `ù14a150` ×30, `ù14a200` ×28, `ù14a500` ×18,
  `ù10a150` ×6, `ù14a600` ×5, and smaller counts. Layers: `TEXT` 448, `Steel` 59. All are TEXT entities.
- **`%%c` in the same style:** style `Arial` also holds 424 entries with `%%c`/`%%C`, in the same shapes:
  `%%c10a150` ×145, `%%c8a100` ×101, `2%%C14` ×4, `790(%%C8a100)` …. They sit on the same layers and
  carry the same XDATA application tags (`GhiChu`/`So thu tu dam`: 398 `ù` and 149 `%%c` entries;
  `STT Cot`/`STT tang DH`: 18 `ù`; `STT MC san`: 6 `ù`). `%%c` is AutoCAD's documented code for the
  diameter sign (S3). The schedule style `thep` (family `Arial Narrow`, file `ARIALN.TTF`) uses only
  `%%C` (`2%%C18`, `%%C8a100`), never `ù`.

### Q2. What does U+00F9 / byte 0xF9 render as?

| Font or encoding | 0xF9 / U+00F9 is | Status |
|---|---|---|
| Unicode font (real Arial, Times New Roman) | `ù` | `verified` (S1, S2) |
| cp1252, cp1258 | `ù` (U+00F9) | `verified` (S1, S2). **So no code-page mix-up explains `ù` -> `Ø`:** `Ø` is 0xD8 in both. |
| TCVN3 (`.Vn…` fonts, `vntimeh.shx`, and the sibling `CIC Arial NarrowH`) | `ự` | `verified` (S4, S5). Seen in this set: `lùc` (lực), `tù` (tự), `dù` (dự), `sù` (sự) |
| VNI (`VNI-…` fonts) | acute mark for lowercase (`u`+F9 = `ú`). Alone after a digit it is an orphan mark. | `verified` (S4, S5) |
| AutoCAD `%%c` | documented as the diameter sign; S3 lists U+2205 as its Unicode string (the glyph drawn depends on the font) | `verified` (S3) |
| `CIC Arial Narrow E` | a diameter glyph | **`inferred`**, not verified. Font not found. |

Why the inference holds (each step `verified` unless marked):

1. Plain Unicode Arial would show `2ù20`. TCVN3 would show `2ự20`. VNI would show `2` + orphan acute +
   `20`. None of these is a valid callout. So the drafter cannot have meant the encodings above.
2. The shapes are exactly the verified rebar forms, count + diameter and diameter + `a` + spacing. The
   same style uses `%%c` in identical shapes on the same layers.
3. A drafter would not plot 500+ unreadable callouts, so the drawing most likely rendered correctly on
   the drafter's machine (`inferred`).
4. The style is the only thing that differs from the `%%c` path: a custom family named `CIC … E`.
   "E" plausibly marks a variant with engineering symbols, but that reading is a guess. The sibling `…H`
   variant is TCVN3 (`inferred` that the family is a modified TCVN3 font with a symbol in the `ự` slot).
5. The same mechanism appears in this drawing for VNI fonts (§6), and there the meaning is nearly
   explicit in the drawing's own general note.

An alternative cause cannot be ruled out without the font. For example, an add-in that writes the
callouts (XDATA `GhiChu`, `So thu tu dam`, `Thep duong san`) may insert a code point it expects a
companion font to draw as `Ø`. Either way the fix is the same: the meaning holds **only together with
that font**.

### Q3. Is a rule safe, and how narrow must it be?

- **A global `ù` -> `Ø` rule is unsafe** (`verified`). Byte 0xF9 / U+00F9 is a real letter in every
  encoding met so far.
  - In this same drawing, `ArialH` holds `ThÐp chÞu lùc`.
  - Drawing 285: styles `KHUNGTEN` (4, `thÐp chÞu lùc`) and `VUA` (4, `cèt tù nhiªn`).
  - Drawing 286: `Title 3` (20, for example `khu vùc sµn …`, `Lùc Ðp tèi thiÓu …`) and `VNTIMEH` (11,
    for example `- §èi víi cèt thÐp chÞu lùc …`). All of these are TCVN3 `ự` in very common
    structural words (lực, tự, dự, sự).
  - In Unicode text, `ù` is itself a Vietnamese letter (for example "mù", "cù").
- **A family-wide rule (`CIC*`) is unsafe:** `CIC Arial NarrowH` uses 0xF9 as `ự`.
- **A style-name rule (`style_name = Arial`) is unsafe:** it would hit genuine Arial styles in other
  drawings.
- **Narrowest rule the evidence supports:** TrueType family exactly `CIC Arial Narrow E`, **and**
  U+00F9 followed by digits, optionally after a bar count, in a callout shape (`^\d*ù\d+(a\d+)?$`). Anything else in that family
  stays undecoded and raises a question.

---

## 4. What the current `knowledge/font-encodings.csv` can hold

**No safe row.** From `src/tekla_harness/knowledge.py`:

- `applies_to` must be `style_name` or `font_file`. The `font_file` of this style is empty, so a
  `font_file` row never matches. The family `CIC Arial Narrow E` exists only in XDATA, and no column
  matches on it. A `style_name` row for `Arial` is too broad (§3).
- `encoding` must be `tcvn3`, `vni` or `unicode`. `ù` -> `Ø` is not an encoding. It is a single glyph
  substitution, and no value expresses it.

### Proposed extension (needs an ADR and engineer approval; written here as a sketch, not a row)

A separate table, or new columns. A sketch in the CSV's style, status `proposed`:

```
pattern,applies_to,from_char,to_char,context,status,evidence,source,decided_by,decided_on
CIC Arial Narrow E,font_family,U+00F9,U+00D8,"^\d*ù\d+(a\d+)?$",proposed,"style Arial (XDATA family 'CIC Arial Narrow E', no font file) in drawing 290 of EVAL-3: 507/507 U+00F9 are followed by digits (optionally after a bar count) in callout shapes (2ù20 x117, 1ù20 x105, 2ù18 x81, ù14a150 x30, ...); U+00F9 is the only non-ASCII char of the style's 2267 entries; same style uses %%c 424 times in the same shapes and layers. Sibling family 'CIC Arial NarrowH' uses 0xF9 as TCVN3 'ự' (1 entry). Font file and vendor doc not found: glyph at U+00F9 unverified.","EVAL-3 drawing 290 (known set, not held-out)",,
```

- New `applies_to` value `font_family`: exact, case-insensitive match on the XDATA family, with no glob
  (`CIC Arial Narrow E` only).
- `to_char`: `U+00D8` follows the harness's existing choice (`display_text` expands `%%c` to U+00D8,
  per `callouts.py`), so callout parsing stays uniform. AutoCAD itself uses U+2205 (S3). The engineer
  picks one.
- `context`: the substitution applies only when the whole text matches the pattern. Any other U+00F9 in
  that family is reported, never converted.
- **Precedence blocker (depends on P2):** `knowledge/README.md` says the table is "consulted only after
  `encoding.font_hint` returned 'unknown': a row never overrides a positive font-name result". For this
  style `font_hint` returns `unicode` from the style name `Arial`, so even an approved `font_family` row
  would never be reached. The substitution needs either its own step outside the encoding lookup order,
  or the precedence change proposed in P2. Approving a row alone would do nothing.
- Every converted entry is flagged (for example `glyph_substitution`) and its confidence is capped, so
  the provenance shows the rule.
- Status: one drawing supports **`proposed`** at most, even after the schema exists. `approved` needs the
  engineer, and ideally the verification in §7 Q1.

---

## 5. Verified vs inferred (summary)

| Claim | Status |
|---|---|
| Entries store U+00F9 (UTF-8 `C3 B9`), not `%%c`, not `\U+00F9` | verified (DXF bytes, via LibreDWG) |
| Style `Arial` -> XDATA family `CIC Arial Narrow E`, no font file, no bigfont | verified (STYLE table) |
| 507/507 sit in callout shapes; `ù` is the style's only non-ASCII char | verified (text index) |
| U+00F9 = `ù` in cp1252/cp1258; `Ø` = 0xD8 | verified (S1, S2) |
| 0xF9 = `ự` in TCVN3; VNI acute mark | verified (S4, S5) |
| `%%c` = diameter sign | verified (S3) |
| The drafter meant `Ø` | inferred, strongly supported by structure |
| `CIC Arial Narrow E` draws a diameter glyph at U+00F9 | inferred; font and docs `not-found` |
| What "CIC" and the "E" suffix mean | not-found |

## 6. Related, separate scope: `Þ` (0xDE) in `VNI-*` styles

The same drawing uses `Þ` as a diameter sign in VNI styles:

- `VNI-HEVEL` (family `VNI-Helve`): `2Þ16`, `1Þ16`, `Þ6a100`, `Þ6a200`.
- `DIM-HELVE` (family `VNI-Aptima`): `Þ10a100` ×15, `Þ6a250` ×7, `Þ8a150` ×3.
- The VNI-encoded MTEXT general note reads `THEÙP {\fVNI-Aptima…;Þ}<10 DUØNG AI_Ra = 2100kg/cm2 …
  THEÙP {\fVNI-Aptima…;Þ}>10 DUØNG AII`, which is VNI for "THÉP Þ<10 DÙNG AI … THÉP Þ>10 DÙNG AII".
  The drafter switches font inline just for that one character, which makes the diameter meaning nearly
  explicit.

`Þ` has no entry in the VNI table (`convert_legacy` reports it unmapped). In TCVN3 it is `ị`, and in
cp1258 0xDE is a combining tilde (S2). This supports the general mechanism, a symbol glyph placed in a
legacy-font slot, but it is a **different character and different fonts**. It needs its own evidence
and its own row. Do not fold it into the `ù` rule. These 31 callout-shaped entries (`^\d*Þ\d+(a\d+)?$`: 25 in `DIM-HELVE`, 6 in `VNI-HEVEL`; the MTEXT
note not counted) are also silently dropped by `callouts` (P1). Other `Þ` entries in TCVN3 styles
(`STYLE12`, `Text_VntimeH`, `ArialH`) are the letter `ị` (for example `chÞu` = chịu) and are not callouts.

## 7. Open questions for the engineer

1. **(Decides the cause.)** Can you get the font `CIC Arial Narrow E` (the .ttf from the drafter or the
   company's CAD font pack), a PDF plot of a sheet of drawing 290 (for example a beam detail), or a look
   at the drawing in AutoCAD on a machine that has the font? Any one of these moves the cause from
   inferred to verified. Without one, the rule stays `proposed`.
2. Do you know the "CIC" fonts, or the add-in that writes the `GhiChu` / `So thu tu dam` /
   `Thep duong san` XDATA? Does your company use them?
3. Should the knowledge table be extended with a `font_family` match and a glyph-substitution row kind
   (§4)? This is a schema change: it needs an ADR, a CHANGELOG entry and a `$id` note. It also needs a
   decision on precedence (P2): today the style name `Arial` decides `unicode` before any table row is read.
4. Should a substituted `ù` map to U+00D8 (the harness's current `%%c` expansion) or to U+2205
   (AutoCAD's documented diameter sign)?
5. Should `Þ` in `VNI-Helve` / `VNI-Aptima` get the same treatment as a separate proposed row (§6)?
6. Until a rule exists, should drawing 290's `ù` callouts stay blocked behind Q-144? Recommended: yes,
   and fix P1 so the block does not depend on the reader noticing.
