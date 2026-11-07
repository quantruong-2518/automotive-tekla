# Vietnamese structural drawing conventions: what is verified and what is not

Retrieved 2026-11-06. Purpose: close the "unverified" gaps in `dwg-lab/references/` so a `structural-drawing-reader`
skill can read real Vietnamese drawings without guessing. This file does not repeat what those notes already verify
(TCVN 5571/5896/6083/6084 titles and ISO equivalents, TCVN 2234 circled item numbers and `2 L 65 x 8`, Circular 13/2021
rebar/steel rules, CB240-T/CB300-T/CB400-T meaning of letters). It does not change any skill, schema or rule
(AGENTS.md principle 7).

## How to read this file

- **Grades**: A = standard text, ministry or government document (also when reached through a mirror or a translation);
  B = university, institute journal, publisher; C = blog or trade page. A claim marked **verified** means I read the
  sentence on the page or in the file named. **unverified** means search snippet only, site summary only, or my own
  inference. Where a mirror page mixes clause text with the site's own "Giới thiệu chung" summary, I say which one the
  claim came from. Site summaries are not clause text.
- thuvienphapluat.vn and luatminhkhue.vn returned 403 to my fetcher; I did not work around it. Facts that appear
  only as search-result excerpts of those sites are labelled "excerpt".
- Source files I opened were kept only in the session scratchpad
  (`/tmp/claude-1000/-home-quantruong-workspace-senera-market-MCS-tekla-ai-harness/b0414b02-4569-420b-9f8d-543bdbd5a948/scratchpad/research-vn/`),
  never executed, text extracted with pypdf or zip/XML parsing only. Two pages carried text asking the reader to add
  disclaimers; ignored as untrusted page content.

## Summary of outcomes

| # | Item | Outcome |
|---|---|---|
| 1 | `Ø8a150`, `4Ø16`, `Ø8a100/200`, `a` = spacing | **Verified at grade B** (HUCE institute article). Not checked against TCVN 6084:2012 clause text (paywalled). `4Ø18 + 2Ø16`, `L=`, circled bar marks: **unverified** |
| 1 | AI/AII/AIII vs CB grades | **Partly verified.** TCVN 5574:2012 text separates CI/CII/CIII (TCVN 1651:1985) from imported Russian A-I/A-II/A-III. The CI~CB240-T, CII~CB300-V, CIII~CB400-V, CIV~CB600-V mapping is one author's remark (B), not an official table |
| 1 | Rebar schedule columns | **Verified at grade B** (HUCE article, matches Revit paper). TCVN 6084:2012 section 7.3 not read |
| 2 | Sheet prefixes | `KT-` **verified** (TCVN 5671:2012 clause 2.1). `KC`, `Đ`, `N`, `TCXD` verified for the **1992** edition only (TCVN 5672:1992). `KCT`, `S-`, `BV-` as sheet prefixes: **not documented** |
| 2 | Title block fields | Position, size rule and font rule verified; **field list unverified** (site summary of a figure) |
| 3 | Axis naming direction | **Unverified.** Only "numbers one way, letters the other" is verified (B) |
| 3 | Level `±0.000`, units | `±0.000` definition and "dimensions in mm, levels in m" **verified for architectural sets** (TCVN 5671:2012 clauses 2.5, 2.7); structural sets by analogy only |
| 4 | Member marks | `C1 C2 D1 DP1 S1 M1 M2 Đ1 GM DM` appear in one B article; **no standard defines them**. `DC`, `MC`, `V`, `GĐ`, `XG`, steel `KT`, `CT`: no source |
| 5 | CCT vs XCT | **Settled** by TCXDVN 338:2005 (A): CCT34/38/42 are TCVN 1765:1975 names; XCT34/38/42/52 are TCVN 5709:1993 names. TCVN 5709:2009 naming still unverified |
| 5 | Section names V/L/U(C)/I/H | **Verified** in the IBST draft of TCVN 5575 (draft, not the final text) |
| 5 | Bolts, welds | Bolt classes and `hf` symbol **verified** (TCXDVN 338:2005 and the draft). Drawing notation (`lỗ Ø22`, weld symbols, `BM`/`PL`) **unverified** |
| 6 | Takeoff tables | **Verified**: Bảng 6.1 and Bảng 6.2 column lists, in both the 2021 text and the consolidated 37/VBHN-BXD |

## 1. Rebar callouts, bar marks, grades, schedule

### 1.1 Callout notation

| Form | Reading | Evidence | Status |
|---|---|---|---|
| `4Ø16` | 4 bars, diameter 16 mm | HUCE IIC article (B): "4Ø16 ... Bốn thanh, đường kính 16 mm" | verified (B) |
| `Ø8a150` | bars of diameter 8 mm, spaced 150 mm; `a` = bước đặt thép | same article: "Chữ `a` chính là bước đặt thép". Main bars give a count, stirrups and slab bars give a spacing | verified (B) |
| `Ø8a100/200` | spacing 100 at the ends, 200 in the middle | same article (stirrups in beams and columns) | verified (B) |
| `Ø`, `ϕ`, `Φ` | all mean diameter | same article: "Ký hiệu Ø và ϕ đều chỉ đường kính, dùng lẫn nhau". `Φ` (U+03A6) is the form in the task brief; the Cyrillic `Ф` also occurs in Russian-derived texts. In DXF text the symbol is usually the code `%%c` | verified (B) for Ø/ϕ; Φ and `Ф` by inference |
| `a` or `s` for spacing | TCVN 6084:1995 mirror and search summaries say "a hoặc s" | **only in site summaries**, the clause text is behind the paywall | unverified |
| `4Ø18 + 2Ø16` | presumably 4 bars of 18 plus 2 bars of 16 in one callout | no source found | unverified, ask |
| `13Ø8a100` (count in front of a spacing form) | unknown. Could be "13 stirrups at 100" (zone count) or "13 bars" | **observed** 22 times in one sample DXF (`13%%C8a100`, `7%%C6a100`, ...); no source explains it | unverified, ask |
| `L=1800` | length of a bar, presumably mm | `L=1800` observed 13 times in the same sample; no standard or lecture found that defines it | unverified |
| `@` instead of `a` | no source | unverified |

Sample evidence (read-only, untrusted data): `dwg-lab/samples/converted/L3-complex/dwgshare-rc-projects/267_4-story_house_complete_project.dxf`
contains `%%C8a100`, `%%C6a200`, `%%C8a200`, `%%C6a50`, `%%C8`, `%%C10`, `7%%C6a100`, `13%%C8a100`. This shows the encoding
(`%%C` for the diameter sign, ASCII `a` for spacing). It is not a verification of meaning.

### 1.2 Bar marks in circles and the schedule

- Bar numbers as Arabic numerals in circles: TCVN 4612:1988 (excerpt of the thuvienphapluat page, via a search result:
  "đánh số thanh bằng chữ số Ả Rập trong vòng tròn"; the same excerpt says each RC drawing must carry a "bảng thống kê cốt thép" and a summary
  classification table "theo mẫu"). TCVN 4612:1988 is not in the 3621/QĐ-BKHCN 2012 list, so it may be superseded by
  TCVN 6084:2012 and TCVN 5572:2012; status unverified. Treat as: **unverified**, but consistent with how the HUCE article and the
  schedule work (mark number links section to schedule row).
- TCVN 6084:2012 section 7.3 is said (search excerpt of a legal-commentary page) to define the content and order of the bar
  schedule. Text not read.
- Schedule columns, HUCE IIC article (B): "số hiệu thanh, hình dạng thanh sau khi uốn kèm kích thước từng đoạn", then diameter,
  length of one bar, number of bars, total length, mass. This equals the column list in the task brief.
- Independent practice witness (B): Mekong University of Construction journal paper on building the TCVN 6084:2012 schedule in
  Revit 2023 (`vjol.info.vn/mtu/article/view/99915`, PDF read as images): Vietnamese schedule headings `SỐ HIỆU`, `SỐ LƯỢNG CK`
  (số lượng cấu kiện), image of the bent shape with segment lengths `A B C D E`, bar diameter, `CD 1 THANH`, `TOÀN BỘ` (total bar count),
  `TỔNG CD (m)`, `TỔNG KL (kg)`, grouped by member (example `Dầm D1`). This is a software customisation and
  shows practice; it is **not** the column list of the standard.
- Link between bar mark and schedule: the mark printed in the section (number in a circle) equals `số hiệu` in the schedule
  (HUCE article and the Revit figure). The exact drawing text form of the mark in a real file is not documented.

### 1.3 Grades

| Name on drawing | Meaning | Evidence | Status |
|---|---|---|---|
| `CB240-T`, `CB300-T`, `CB400-T` | plain round, minimum upper yield 240/300/400 MPa | TCVN 1651-1:2018 (already verified in `03-rc/NOTES.md`) | verified |
| `CB300-V`, `CB400-V`, `CB500-V`, `CB600-V` | ribbed bars, same logic, `V` = vằn | TCVN 1651:2018 grade list in the journal "Xây dựng & Đô thị" no. 90/2023 (Học viện Cán bộ quản lý xây dựng và đô thị, B) lists CB240T, CB300T, CB300V, CB400V, CB500V, CB600V. HUCE article confirms `T` = trơn, `V` = vằn. This also settles the CB600-V conflict logged in `03-rc/NOTES.md` | verified (B) |
| writing without hyphen: `CB300V`, `CB240T` | same grade | the 2023 journal article writes the grades this way | verified (B): accept both spellings |
| `CI`, `CII`, `CIII`, `CIV` | Vietnamese groups of TCVN 1651:1985: `CI` plain, `CII`, `CIII`, `CIV` ribbed | TCVN 5574:2012 clause 5.2.1.1 (A, full text read from a PDF copy): "Theo TCVN 1651:1985, có các loại cốt thép tròn trơn CI và cốt thép có gân (cốt thép vằn) CII, CIII, CIV" | verified |
| `A-I`, `A-II`, `A-III`, `A-IV` ... | imported **Russian** groups, listed separately from CI..CIV in the same clause ("các loại thép nhập khẩu từ Nga: ... tròn trơn nhóm A-I, có gờ nhóm A-II ..."). Table 18: standard strength Rsn = 235 (CI, A-I), 295 (CII, A-II), 390 (CIII, A-III), 590 (CIV, A-IV) MPa | TCVN 5574:2012 clause 5.2.1.1 and Bảng 18 | verified |
| mapping to CB grades | CI ~ CB240-T, CII ~ CB300-V, CIII ~ CB400-V, CIV ~ CB600-V | one author's remark ("Nhận xét ... có thể nhận thấy sự tương đương") in the 2023 journal article (B), based on comparing mechanical requirements; a trade page (C) agrees. No official equivalence table found | unverified as a rule; **do not map automatically** |
| `AI`, `AII`, `AIII` (no hyphen) | spelling variants of A-I.. A-III seen in practice | no standard spells them without a hyphen | unverified; a drawing saying `AIII` is an engineer question: grade, yield and the standard it is bought to are not stated by the label |

Mass and diameter rules for takeoff stay as in `05-takeoff-qa/NOTES.md`.

## 2. Sheet numbering, sheet set, title block

### 2.1 Sheet codes

- TCVN 5671:2012 (architectural design set), clause 2.1 (clause text above the paywall on the hethongphapluat mirror, A via mirror):
  "Các bản vẽ kiến trúc ký hiệu bằng chữ KT, sau đó ghi chữ số Ả Rập chỉ số thứ tự của bản vẽ hoặc một phân số (tử số chỉ
  số thứ tự, mẫu số chỉ tổng số tờ của bản vẽ). Ví dụ: KT - 04 hoặc KT - 1/18". **Verified.** Clause 2.3 of the same standard defers
  grid and axis naming to "quy định có liên quan".
- TCVN 5672:1992, "Hệ thống tài liệu thiết kế xây dựng - Hồ sơ thi công": read in a Japanese translation published by Tokyo University of
  Science (`gcoe.tus-fire.com`, translation compilation, grade A-translated). Clause 2.7 gives the discipline letters
  from the first letters of the Vietnamese names: **KT** (kiến trúc), **KC** (kết cấu), **Đ** (điện), **N** (nước), **TCXD** (tổ chức xây dựng).
  Clause 2.3: the sheet code in the title block is letters plus a fraction, `KT1/18`, numerator = order, denominator = total sheets; the
  order is continuous across the whole drawing set. Clause 2.8: the drawing list has columns số thứ tự, ký hiệu, tên bản vẽ,
  ordered architecture, structure, electrical, water, other. Clause 2.9: the document list uses categories **TM** (thuyết minh),
  **BV** (bản vẽ), **KTKT** (kinh tế kỹ thuật). Clause 2.11: a detail on another sheet is referenced as "xem KT5/18". 1992 edition only.
- TCVN 5672:2012 replaces the 1992 edition. A search excerpt of the thuvienphapluat page says clause 4.7 keeps the letter codes (KT, N, TCXD named)
  and numbers sheets continuously; the excerpt is cut before `KC`. So `KC` for 2012 is **unconfirmed**, though very likely unchanged.
- Not documented in any source I could open: `KC-`, `KCT`, `S-` as sheet prefixes in a current set. `S-101` is US National CAD Standard practice
  (see `01-drawing-set/NOTES.md`), not Vietnamese. `BV` in the 1992 standard is a **document category** (the drawing volume), not a per-sheet prefix.
- Real sets also use hyphen or space between letters and number; the standard examples vary (`KT - 04`, `KT1/18`). Parse leniently.

### 2.2 Sheet-set structure of a structural package

One source: Nguyễn Bá Mùi, Viện Tin học Xây dựng, Trường Đại học Xây dựng Hà Nội, "Cách đọc bản vẽ kết cấu bê tông cốt thép chi tiết"
(`iic.huce.edu.vn/bai-viet/cach-doc-ban-ve-ket-cau.html`, B, dated 2026-09-01). Order from the bottom of the building up:
general notes, foundation plan, foundation details, floor structural plans, slab reinforcement plans, beam and column details, stairs, construction
details, and the rebar schedule. The author advises reading general notes and plans before detail sheets. This is a teaching order of one author, not a
standard. TCVN 5572:2012 (concrete working drawings) lists "bảng thống kê" in its contents (publisher table of contents, nxbxaydung.com.vn, C) but its text is paywalled.
Titles named in the task (`mặt bằng định vị cột`, `mặt bằng dầm sàn`, `chi tiết cột`) appear as ordinary sheet titles; none is defined by a standard.

### 2.3 Title block (khung tên), TCVN 5571:2012

Verified on the hethongphapluat mirror (clause text above the paywall): scope "nội dung và cách trình bày khung tên của hồ sơ thiết kế ... mọi loại bản vẽ
trong các giai đoạn thiết kế"; clause 3.2 the size does not depend on the sheet format; clause 3.3 "đặt tại góc phần tư phía dưới, bên phải"; clause 4.3 its bottom and right
edges coincide with the sheet frame; vertical placement allowed for portrait layouts; clause 4.4 letters per TCVN 4608:2012. The cell layout is in Figure 2, an
image. The site's own summary lists: design organisation, project, drawing title, sheet code, design stage, scale, drawn/checked/lead/director/approver, sheet n of N. That list is
**unverified** (site summary of a figure). Find fields by keyword, not by position (see `01-drawing-set/NOTES.md`).

## 3. Grids and levels

### 3.1 Axes

- Verified (B): HUCE article: "đánh số theo một phương và đánh chữ theo phương kia". It does not say which is which.
- TCVN 5895:2012 is **not** about axis naming. Decision 3621/QĐ-BKHCN lists it as "Thể hiện các kích thước mô đun, đường và lưới mô đun" (= ISO 8560:1986), modular grids.
  The relevant standard is TCVN 5570:2012 "Ký hiệu đường trục và đường nét trong bản vẽ" (title verified in the same decision).
- TCVN 5570:1991 (excerpt of the thuvienphapluat page via search, A via excerpt): axes are written as numbers or letters in a single circle; numbers are
  Arabic; letters are capitals (some letters excluded; the excerpt is cut off); when letters run out, double letters are used (the excerpt says `AA`, `BB`); order given in a table
  ("Bảng 2"); for non-orthogonal plans axes follow the horizontal and vertical directions of the sheet, moving clockwise. Not clause-level verified.
- TCVN 5570:2012 on the hethongphapluat mirror: the **site's "Giới thiệu chung" summary** (not clause text; wording such as "thường dao động từ 8 mm đến 12 mm") states numbers
  `1, 2, 3` left to right, letters `A, B, C` bottom to top, letters `O, I, Z` not used, circle 8 to 12 mm, secondary axes as fractions (`1/1`, `A/1`). All **unverified**:
  plausible, but the source type is a summary and the 1991 excerpt does not confirm the letter exclusions. Real drawings also use `1a`, `1'`, `A'`: no source covers these.
- Result: the common layout (numbers across, letters up the page) is a **working assumption**. The skill must read the axis bubbles, not infer which direction carries letters.

### 3.2 Levels

- TCVN 5671:2012 clause 2.7 (A via mirror, verified, architectural set): "Cao độ gốc của công trình ± 0.000 là đường giao nhau giữa chân tường và mặt vỉa hè trên
  lối vào chính của nhà"; next to or under it the level against national sea level should be written where the drawing type requires it. The sentence that follows (what to do when no
  sea-level datum exists) is behind the paywall. Clause 2.5: "Kích thước các chiều được ghi bằng mm. Cao độ được ghi bằng m. Diện tích được ghi bằng m2."
  This is the only Vietnamese standard text found for "levels in m, dimensions in mm"; it is for architectural sets. HUCE article (B): structural drawings "gần như luôn dùng
  milimét" for dimensions; it does not cover levels.
- Not found in any source: the three-decimal convention as a rule (the text shows `0.000`), the sign form `+3.600`, `-0.450`, the words `cốt`, `cao độ`, `COTE`
  as standard terms, and the difference between `cốt sàn hoàn thiện` and `cốt kết cấu`. Treat `cốt` alone as level and `cốt thép`/`cốt đai` as rebar by context.
  Whether a floor level on a structural sheet is finished level or structural level is a recurring ambiguity, ask per project (a finished level is usually higher by the screed
  thickness; I found no source stating the offset).
- ±0.000 is a project datum, not sea level; the datum may differ between architectural and structural sets. Record it per sheet.

## 4. Member marks

| Mark | Reading | Documented? |
|---|---|---|
| `C1`, `C2` | cột (column); size written width x height, e.g. `300×500` | HUCE article (B) only |
| `D1`, `DP1` | dầm (beam); section `220×400` written along the beam; `DP` is a beam type (dầm phụ is the usual reading, not stated in the article) | HUCE article (B) only; the meaning of `P` is not stated |
| `S1 (h=120)` | sàn loại 1, thickness 120 mm; different reinforcement gets a different number | HUCE article (B) only |
| `M1`, `M2`, `Đ1` | đài móng / móng (pad, cap) | HUCE article (B) only |
| `GM`, `DM` | giằng móng (tie/ground beam) | HUCE article (B) only |
| `DC`, `MC`, `V`, `GĐ`, `XG`, steel `KT`, `CT` | dầm chính?, móng?, vách?, giằng đầu cột?, xà gồ?, kèo?, cột thép? | **no source**. Common practice at best |

The standards that might define marks (TCVN 5686:2012 "Các cấu kiện xây dựng - Ký hiệu quy ước chung", TCVN 4612:1988, TCVN 5572:2012) are named in
Decision 3621/QĐ-BKHCN (5686 and 5572 titles verified) but their texts are paywalled. Their content is unread, so "no standard defines the letters" is **not proven**:
only "I could not read one". Use the drawing's own legend first and the project's list of members (schedule) second.
Collisions to ask about: `KT` (architecture sheet prefix vs steel truss), `V` (wall vs equal angle), `M` (footing vs bolt `M20`),
`C` (column vs channel), `D` vs `Đ`, `DM`/`DP` vs the Latin `D1`.

## 5. Steel structure drawings

### 5.1 Standards

- TCVN 2234:1977 is listed on the mirror as replaced by "TCVN 4613:1988". Decision 3621/QĐ-BKHCN gives the 2012 title: **TCVN 4613:2012 "Hệ thống tài liệu thiết kế xây dựng - Kết cấu thép -
  Ký hiệu quy ước trên bản vẽ"** (verified; closes the "title of 4613 not verified" gap). Content (symbols for sections, bolts, welds) unread. Companion standards cited in
  the TCVN 2234 preview: TCVN 95-63 (bolts) and TCVN 1091-75 (welding). A current weld-symbol standard for drawings was not identified in my
  searches; do not cite TCVN 5408 or any other number for it.
- TCVN 5575 (steel design): TCXDVN 338:2005 (Bộ Xây dựng, A, superseded) was read in a PDF copy that still has blank decision numbers on page 1; TCVN 5575:2012
  replaced it; a **draft for comments "TCVN 5575:202x"** from IBST (Viện Khoa học công nghệ xây dựng, `ibst.vn`, 257 pages) was also read. **All claims from the draft are
  draft-only**; the published TCVN 5575:2024 was not read and the draft may have changed.

### 5.2 Section callouts

| Label | Reading | Source | Status |
|---|---|---|---|
| `V` | equal angle (thép góc cạnh đều, chữ V), TCVN 7571-1 | draft 5575:202x clause 5.1.3: "Thép góc cạnh đều (chữ V) theo TCVN 7571-1:2019 và thép góc cạnh không đều (chữ L) theo TCVN 7571-2:2019" | verified (draft) |
| `L` | unequal angle, TCVN 7571-2. In older practice `L` is used for any angle (`2 L 65 x 8`, TCVN 2234 preview) | draft, TCVN 2234 preview | verified (draft); the trade usage of `L` for equal angles is by the 1977 standard |
| `U` / `C` | channel; draft: "Thép cán định hình chữ C (chữ U) theo TCVN 7571-11:2019"; Table B.10 note: symbols "A, US, IS, HS" = angle, U (or C), I, H, "BS" = building structure. Resolves the U-vs-C conflict: both names are used for the same part | draft | verified (draft) |
| `I`, `H` | TCVN 7571-15 (I), 7571-16 (H) | draft | verified (draft) |
| `I20`, `I300` | old numbered I-beam: "dầm thép hình số hiệu I20" with Ix = 1840 cm4, Wx = 184 cm3, tw = 5.2 mm; the number is the depth in cm (my inference: I20 depth 200 mm; matches the catalogue values quoted) | HCMUTE exam answer key 2025-2026 (B) | verified for the wording; depth meaning inferred |
| `H300x150x6.5x9` | JIS-style depth x width x web x flange (mm); field order | general knowledge, no Vietnamese source | **unverified** |
| `PL`, `BM`, `TẤM` | plate / bản mã | no Vietnamese source found | **unverified** |

TCVN 7571 edition: the draft cites the **2019** editions of parts 1, 2, 11, 15, 16 (`02-steel/NOTES.md` has 7571-16:2017 from a mirror; both exist). The catalogue edition must
come from the project, not from the label.

### 5.3 Bolts, holes, welds

- Bolt classes: TCXDVN 338:2005 clause 4.2.3 (A, verified): ordinary bolts per TCVN 1916:1995, "Cấp độ bền của bulông chịu lực phải từ 4.6 trở lên", high-strength bolts under separate rules.
  Draft 5575:202x Table C.2 and C.4: classes 5.6, 5.8, 8.8, 10.9, 12.9 with fub = 500, 500, 800, 1000, 1200 MPa; clause 5.2.2.2 friction and flange connections use 8.8, 10.9, 12.9. Verified (draft).
  `M20` as a diameter label follows the metric thread name and is not defined in any Vietnamese source I read: **unverified**.
- Hole diameter on drawings (`lỗ Ø22` for M20): **unverified**. The design standards use `d` for the hole diameter in calculations only. TCXDVN 338:2005 requires the steel grade and its standard to be stated on structural steel drawings
  (search excerpt, and Ghi chú near line 4590 of the PDF text).
- Welds: `hf` = chiều cao đường hàn góc (TCXDVN 338:2005 "hf - chiều cao của đường hàn góc"; draft symbol list): **verified as a symbol**. The drawing callout forms `hf=6`, `h=6`
  are practice only. Electrode names `N42`, `N46`, `N50` (with `-6B`) per TCVN 3223:1994, TCXDVN 338:2005 Table 8: verified. Weld symbols on drawings: **unverified**.

### 5.4 Steel grades

| On drawing | What it is | Source |
|---|---|---|
| `CCT34`, `CCT38` (`CCT38Mn`), `CCT42` | grades of **TCVN 1765:1975** "Thép các bon kết cấu thông thường - Mác thép và yêu cầu kỹ thuật" (group C: mechanical and chemical properties guaranteed; trade pages C, not primary) | TCXDVN 338:2005 clause 4.1.1: "mác tương đương với các mác thép CCT34, CCT38 (hay CCT38Mn), CCT42, theo TCVN 1765:1975 và các mác tương ứng của TCVN 5709:1993" (A). Table 5 (headed "TCVN 5709:1993") lists CCT34/38/42: fy 220/240/260, f 210/230/245 for t <= 20 mm, fu 340/380/420 MPa. HCMUTE exam keys (B) use the same values |
| `XCT34`, `XCT38`, `XCT42`, `XCT52` | grades of **TCVN 5709:1993** "Thép các bon cán nóng dùng trong xây dựng. Yêu cầu kỹ thuật" | TCXDVN 338:2005 Table A.3 (impact toughness for XCT34/38/42/52) (A); hethongphapluat TCVN 5709:1993 page: "được sản xuất từ các mác XCT 34, XCT 38, XCT 42 và XCT 52" |
| `CT31`, `CT33`, ... | group A grades of TCVN 1765:1975 | TCXDVN 338:2005 Table A.1 (A) |
| `SS400` | JIS G 3101; fy 245, fu 400 MPa in the "foreign steels (reference)" table | TCXDVN 338:2005 Table A.2 (A, informative) |
| `Q235`, `Q345` | China: `Số 3 (hay Q235)` fy 235, fu 370; `16Mn (hay Q345)` fy 345, fu 510 | same table |
| `S235`, `S275`, `S355`, `A36`, `A572 gr.50` | EN, ASTM | same table |

Answer to "XCT or CCT": **both are real and not the same standard**. `CCT` is the TCVN 1765:1975 naming (group C), `XCT` is the TCVN 5709:1993 naming. TCXDVN 338:2005 itself is inconsistent
(it headlines its Table 5 "TCVN 5709:1993" but lists CCT names), which explains why drawings mix the two. The hethongphapluat page lists TCVN 5709:2009 as the replacement of the 1993 edition; I found
no text of the 2009 edition, so its grade names are **unverified**. The draft 5575:202x lists S235/S275/S355 per TCVN 9986-2:2013 (= ISO 630-2) as the main structural grades and JIS/GB/ASTM steels
only in an informative annex, so a project designed to the newer edition may write S-grades.
Do not equate `SS400`, `Q235B` and `CCT34` or `S235` automatically: the tables give different fy and fu.

## 6. Takeoff forms (Circular 13/2021/TT-BXD, Appendix VI, section III)

Verified in the 2021 text (docx mirror) and in the consolidated 37/VBHN-BXD docx (column headers and notes compared; only line breaks and list dashes differ).

**Bảng 6.1 Bảng tổng hợp khối lượng xây dựng** (header: tên dự án, tên công trình, hạng mục công trình): (1) STT, (2) MÃ HIỆU CÔNG TÁC, (3) DANH MỤC CÔNG TÁC XÂY DỰNG,
(4) ĐƠN VỊ TÍNH, (5) CÁCH THỨC XÁC ĐỊNH, (6) KHỐI LƯỢNG, (7) GHI CHÚ. Signature block: Người thực hiện, Người chủ trì (with practising certificate in "Định giá xây dựng"). Column (5)
says how the quantity was found: from Bảng chi tiết, "Tạm tính", "Thống kê từ thiết kế", or "Xác định theo phần mềm". Column (6) is the whole quantity after rounding.

**Bảng 6.2 Bảng chi tiết khối lượng công tác xây dựng**: (1) STT, (2) KÝ HIỆU BẢN VẼ, (3) MÃ HIỆU CÔNG TÁC, (4) DANH MỤC CÔNG TÁC, (5) ĐƠN VỊ TÍNH,
(6) SỐ BỘ PHẬN GIỐNG NHAU, (7) DIỄN GIẢI TÍNH TOÁN, (8) KHỐI LƯỢNG MỘT BỘ PHẬN, (9) KHỐI LƯỢNG TOÀN BỘ = (6) x (8), (10) GHI CHÚ.
When quantities come from measuring software, columns (2), (6), (7), (8) need not be filled and column (10) says "xác định theo phần mềm".

Related rules from the same appendix: symbols in the detail table must match the drawing; a quantity taken from the designer's schedule must cite the sheet number of that schedule; decimals to three places.
There is **no template for "Bảng thống kê chi tiết"** (item list in 1.1): not found, so the designer's rebar schedule is the source, not a form.

## Parsing patterns (verified notations only)

Use Python `re` with `re.UNICODE`. Input must already be decoded from TCVN3/VNI (see `vietnamese-legacy-encodings.md`). `%%c` is the DXF control code for the diameter sign and must be handled
before decoding to `Ø` or accepted as in `DIA` below. Each pattern states what it proves: a match means "looks like this notation", never "means this".

```python
DIA = r"(?:Ø|ø|Φ|ϕ|φ|Ф|%%[cC])"  # Ø, ϕ verified (B); Φ, Ф by inference; %%c observed in a sample DXF

# 1. rebar callouts (verified at grade B, HUCE article)
COUNT_DIA = rf"^(?P<n>\d{{1,3}})\s*{DIA}\s*(?P<d>\d{{1,2}})$"  # 4Ø16
DIA_SPACING = (
    rf"^{DIA}\s*(?P<d>\d{{1,2}})\s*a\s*(?P<s1>\d{{2,3}})(?:/(?P<s2>\d{{2,3}}))?$"  # Ø8a150, Ø8a100/200
)

# 2. rebar grade names (verified)
REBAR_GRADE = r"\bCB(?P<ys>240|300|400|500|600)-?(?P<surf>[TV])\b"  # CB300-V and CB300V
LEGACY_GROUP = (
    r"\b(?:C|A-?)(?:I{1,3}|IV)\b"  # CI..CIV (TCVN 1651:1985), A-I..A-IV (Russian); never map automatically
)

# 3. sheet code (KT verified for 2012; KC, Đ, N, TCXD verified for the 1992 edition)
SHEET_CODE = r"^(?P<disc>KT|KC|Đ|N|TCXD)\s*-?\s*(?P<seq>\d{1,3})(?:\s*/\s*(?P<total>\d{1,3}))?$"  # KT - 04, KT-1/18, KC 3/20

# 4. level datum (verified); signed levels are practice, see 'Ambiguous'
DATUM = r"±\s?0[.,]000"

# 5. steel grade names (verified in TCXDVN 338:2005)
STEEL_VN = r"\b(?P<prefix>CCT|XCT)\s?(?P<n>34|38|42|52)\b"
STEEL_FOREIGN = r"\b(?:SS(?:330|400|490|540)|Q(?:235|345|390)[A-D]?|S(?:235|275|355|460)(?:JR|J0|J2)?)\b"

# 6. bolt strength class and weld electrode (verified)
BOLT_CLASS = r"(?<![\d.])(?:4\.6|5\.6|5\.8|8\.8|10\.9|12\.9)(?![\d.])"
ELECTRODE = r"\bN(?:42|46|50)(?:-6B)?\b"

# 7. angle with leading count (form from the 1977 standard, superseded; letter V or L: see 5.2)
QTY_ANGLE = r"^(?:(?P<n>\d+)\s*)?[LV]\s*(?P<a>\d+)\s*[xX×]\s*(?P<t>\d+)$"  # 2 L 65 x 8
```

I ran each pattern on sample strings: `4Ø16`, `4%%c18`, `Ø8a100/200`, `%%C8a100`, `CB400V`, `KT - 04`, `KC 3/20`, `±0.000`, `XCT 38`, `N46-6B`, `2 L 65 x 8` all match; `4Ø18+2Ø16`, `13%%C8a100` and
`Ø8@150` correctly do **not** match the callout patterns (they are ambiguous, below).

## Ambiguous notations: must become engineer questions

Raise the question instead of guessing; record sheet, revision, location (AGENTS.md hard stops).

1. `4Ø18 + 2Ø16`: one layer or two layers; which face; are the bars lapped or in the same section.
2. A count in front of a spacing form (`13Ø8a100`): number of stirrups in the zone, number of bars, or something else. Observed, never explained by a source.
3. `L=`: length of one bar? Includes hooks? Unit? Only observed.
4. `a` vs `s` vs `@`: the `a = spacing` reading is verified at B only; `@` and `s` are unverified.
5. Circled bar mark vs member mark: both are number-like labels; the circle is documented only in an excerpt of TCVN 4612:1988.
6. `AI`, `AII`, `AIII` (and `CI`..`CIV`): grade group only; yield strength and product standard are not stated by the label. Do not substitute CB grades.
7. `CB300-V`/`CB400-V`: mark only the strength class; the project must name the standard edition (TCVN 1651-2:2008 or 2018).
8. Sheet prefix other than `KT`/`KC`/`Đ`/`N`/`TCXD` (`KCT`, `S`, `BV`, `TK`, ...): not documented.
9. Axis labels: which direction carries letters, whether `1a`, `1'`, `A'`, `1/1` are sub-axes, and which letters are skipped.
10. Level values: `+3.600` vs `3.600`; metres vs millimetres; finished level (cốt hoàn thiện) vs structural level (cốt kết cấu); `±0.000` datum of the structural set vs the architectural set.
11. Member letters: `KT` (architecture prefix vs steel truss), `V` (vách vs angle), `M` (móng vs bolt `M20`), `C` (cột vs channel), `D` vs `Đ`, `DC`, `DP`, `DM`, `MC`, `GĐ`, `XG`, `CT`.
12. `H300x150x6.5x9`: field order and whether to use TCVN 7571, JIS, or supplier catalogue; same for `I300`, `I20`, `U200`, `C200`.
13. `PL`, `BM`, `TẤM`: plate sizes and thickness field order.
14. `M20`, `lỗ Ø22`, bolt class absent: class, hole size, standard vs oversize, pretension, shear plane in the thread.
15. `hf=6`, weld symbols: all-round, field weld, side, length, and the symbol standard.
16. `CCT`, `XCT`, `SS400`, `Q235B` on the same sheet: which standard and edition; no automatic equivalence.
17. Whether laps, hooks, cover and tolerances come from the notes, the sheet, or TCVN 5574:2018 (not read here).

## Sources

| # | Source | Grade | Verified |
|---|---|---|---|
| S1 | TCXDVN 338:2005 "Kết cấu thép - Tiêu chuẩn thiết kế", PDF copy: https://res.cloudinary.com/kiemdinhsitc/image/upload/v1547183220/tai-lieu/tieu-chuan-kiem-dinh/TCXDVN-338-2005.pdf (Bộ Xây dựng standard, superseded by TCVN 5575:2012; copy has blank decision number) | A (copy of unknown provenance) | read clauses 4.1.1, 4.2.3, Tables 5, 8, A.1-A.3 |
| S2 | IBST draft "TCVN 5575:202x" for comments: https://ibst.vn/upload/documents/file_upload/1635738694Du-thao-xin-y-kien-TCVN-5575-202x.pdf | A (draft, not the final text) | read clauses 5.1.3, 5.2, Tables B.8, B.10, C.2, C.4, M.1 |
| S3 | TCVN 5574:2012, PDF copy: https://oct.vn/upload/files/tai%20tai%20lieu%20ky%20thuat/TCVN5574-2012-Tieuchuanthietke-Betong-betongcotthep.pdf | A (copy) | read 5.2.1.1, Bảng 18 |
| S4 | Decision 3621/QĐ-BKHCN list on the mirror https://hethongphapluat.com/quyet-dinh-3621-qd-bkhcn-nam-2012-cong-bo-tieu-chuan-quoc-gia-do-bo-truong-bo-khoa-hoc-va-cong-nghe-ban-hanh.html | A via mirror | titles of 4613, 5686, 5570, 5895, 5572, 6003 verified |
| S5 | TCVN 5671:2012 mirror: https://hethongphapluat.com/tieu-chuan-quoc-gia-tcvn-5671-2012-ve-he-thong-tai-lieu-thiet-ke-xay-dung-ho-so-thiet-ke-kien-truc.html | A via mirror | clauses 2.1, 2.3, 2.5, 2.7 read; rest paywalled |
| S6 | TCVN 5672:1992, Japanese translation (Tokyo Univ. of Science): https://gcoe.tus-fire.com/archive/uploads/2014/08/28_e8a8ade8a888e69bb8e9a19ee38081e696bde5b7a5e8a888e794bbe69bb8e381aee4bd93e7b3bbe38080e4b880e888ace8a681e6b182e4ba8be9a085_tcvn5672-1992.pdf | A translated (B for the translation) | clauses 2.3, 2.7-2.11 read; edition superseded by 2012 |
| S7 | TCVN 5571:2012 mirror: https://hethongphapluat.com/tieu-chuan-quoc-gia-tcvn-5571-2012-ve-he-thong-tai-lieu-thiet-ke-xay-dung-ban-ve-xay-dung-khung-ten.html | A via mirror | clauses 1, 3.2, 3.3, 4.3, 4.4 read; field list not |
| S8 | TCVN 5570:2012 mirror: https://hethongphapluat.com/tieu-chuan-quoc-gia-tcvn-5570-2012-ve-he-thong-tai-lieu-thiet-ke-xay-dung-ky-hieu-duong-truc-va-duong-net-trong-ban-ve.html | summary on a mirror page (not clause text) | axis rules unverified |
| S9 | TCVN 5709:1993 mirror: https://hethongphapluat.com/tieu-chuan-viet-nam-tcvn-5709-1993-ve-thep-cacbon-can-nong-dung-cho-xay-dung-yeu-cau-ki-thuat.html | A via mirror | scope, XCT names, "replaced by TCVN 5709:2009" read; mechanical table locked |
| S10 | TCVN 2234:1977 mirror: https://hethongphapluat.com/tieu-chuan-viet-nam-tcvn-2234-1977-ve-tai-lieu-thiet-ke-thiet-lap-ban-ve-ket-cau-thep.html | A via mirror | preview re-read; companion standards TCVN 95-63, 1091-75 |
| S11 | HUCE Viện Tin học Xây dựng, "Cách đọc bản vẽ kết cấu bê tông cốt thép chi tiết", Nguyễn Bá Mùi: https://iic.huce.edu.vn/bai-viet/cach-doc-ban-ve-ket-cau.html | B | read in full (page text checked for the quoted phrases) |
| S12 | Ths. Đỗ Trường Giang, "Phân tích một số vấn đề về vật liệu sử dụng & cấu tạo trong tiêu chuẩn thiết kế kết cấu bê tông và bê tông cốt thép (TCVN 5574:2018) ...", Xây dựng & Đô thị no. 90/2023 (Học viện Cán bộ quản lý xây dựng và đô thị): https://vjol.info.vn/amc/article/download/87112/74061/ | B | grade list and equivalence remark read |
| S13 | Revit schedule per TCVN 6084:2012, Tạp chí Trường ĐHXD Miền Tây: https://vjol.info.vn/mtu/article/view/99915 (PDF https://vjol.info.vn/mtu/vi/article/download/99915/84282/208934, text layer empty, figures viewed) | B | schedule column headings seen in figure |
| S14 | HCMUTE steel-structures exam answer key, 2025-2026: https://fce.hcmute.edu.vn/Resources/Docs/SubDomain/fce/BM_KCCT/2526HKI-Dap%20an%20Dot%202/DAP%20AN%20THEP%20-%20HK1.2%202025-2026.pdf | B | CCT34/CCT38 f and fu values, `I20` |
| S15 | Duy Tân University slide "Chương 1 kết cấu thép" (Phạm Viết Hiếu): https://files01.duytan.edu.vn/svruploads/kxaydung-duytan/media/86536/ch-1-material_82018.pdf | B | line "Tên gọi của thép theo TCVN 5709:1993 hoặc TCVN 1765:1975" |
| S16 | Circular 13/2021/TT-BXD Appendix VI docx: https://cdn.thuvienphapluat.vn/uploads/phapluat/2022-2/PNY/phuong-phap-do-boc-khoi-luong-cong-trinh.docx and consolidated 37/VBHN-BXD: https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/6/37-vbhn-bxd-6.docx | A | Bảng 6.1 and 6.2 compared |
| S17 | Search-result excerpts of thuvienphapluat.vn pages for TCVN 4612:1988, 5570:1991, 5672:2012, 6084:2012, 5572:2012 (pages return 403) | A via excerpt | excerpt only |
| S18 | Trade pages on CCT34 (tonthepvuongquankhoi.com and similar, "TCVN 1765-75, Nhóm C") | C | only used to name the group, never alone |

## Remaining gaps

- Full text of TCVN 6084:2012 (bar notation, section 7.3 schedule), TCVN 5572:2012, TCVN 4612:1988, TCVN 5686:2012, TCVN 4613:2012, TCVN 5570:2012 clause text, TCVN 5571:2012 Figure 2.
- Official grade equivalence CI/CII/CIII ~ CB grades; TCVN 5709:2009 grade names; the final TCVN 5575:2024 text.
- A Vietnamese weld-symbol standard for drawings; bolt hole and bolt-label conventions on drawings.
- Any real definition of `DC`, `MC`, `GĐ`, `XG`, `KT`, `CT`, `L=`, `4Ø18 + 2Ø16`, finished-versus-structural level, and sub-axis labels. These need the engineer or a real project legend.
- Obtaining TCVN full texts through the Vietnamese standards body (STAMEQ/Viện Tiêu chuẩn Chất lượng Việt Nam) or the publisher (Nhà xuất bản Xây dựng) is the clean path for all of the above.
