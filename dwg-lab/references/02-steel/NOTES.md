# 02 Structural steel drawings: section designations, units, connections, framing, grades

Accessed 2026-11-06. Grades: A = standards body / government / official publisher primary text;
B = university, agency or DOT guide, manufacturer catalogue, peer-reviewed paper, software vendor library;
C = blog, wiki or supplier. "Verified" = I opened the page/file and the claim is on it.

## Sources

| # | Source | Grade | Region | Verified | Supports |
|---|---|---|---|---|---|
| 1 | [AISC Shapes Database v16.0 (AISC page)](https://www.aisc.org/publications/steel-construction-manual-resources/16th-ed-steel-construction-manual/aisc-shapes-database-v16.0/) | A | US | Partly: page exists (HTTP 200, title "AISC Shapes Database v16.0"), but its body is script-rendered and I could not read it. "Excel file", "EDI naming convention", "separate HSS A1085 database", "US and metric units" come from a search snippet: unverified. | Authoritative W/HSS/C/L/WT property tables (AISC Manual part 1). Download from AISC; do not use third-party copies. |
| 2 | [Bentley STAAD.Pro help: AISC section names in the database](https://docs.bentley.com/LiveContent/web/STAAD.Pro%20Help-v20/en/GUID-0DD5F539-AF0D-4DB6-8BC7-79E289D06021.html) | B | US/global | Y | How software renames AISC shapes: `W10X49`, `C8X11.5` becomes `C8X11`, round HSS `HSS16X0.438`, rect HSS `HSST14X10X0.313`, angles `L505010` = L5x5x5/8. Drawing text and model database names differ: a mapping layer is needed (`profile_map`). |
| 3 | [British Steel UB datasheet (Jul 2026)](https://www.britishsteel.co.uk/wp-content/uploads/2026/07/UB-datasheet-21.07.26.pdf) (link only; copyright manufacturer) | B | UK | Y (PDF read) | UB designation "depth x width x kg/m" with a separate table of actual depth, width, tf, tw, r; stated "to BS EN 10365:2017". Example rows: 203x133x25 has actual mass 25.1 kg/m, depth 203.2 mm. |
| 4 | [Dlubal cross-section library: HN 450x200, GB/T 11263-2005](https://www.dlubal.com/en/cross-section-properties/h-hn-450x200-gb-t-11263-2005) and [TCVN 7571-16:2017 H series](https://www.dlubal.com/en/cross-section-properties/series-h-tcvn-7571-16-2017), [I-beams/H-beams index](https://www.dlubal.com/en/cross-section-properties/i-beams-h-beams.html) | B (software vendor) | CN, VN, JP, EU | Partly: page titles and the standards list confirm that the library has GB/T 11263 (1998/2005/2010/2017), GB/T 706, JIS G 3192, JIS A 5526:2005, TCVN 7571-15 (2006) and TCVN 7571-16 (2006 and 2017), and that designation text looks like `HN 450x200`. Property values were not extractable (script-rendered). | Existence of machine-readable section libraries per standard; designation style. |
| 5 | [TCVN 2234:1977 steel structure drawings (hethongphapluat mirror, preview)](https://hethongphapluat.com/tieu-chuan-viet-nam-tcvn-2234-1977-ve-tai-lieu-thiet-ke-thiet-lap-ban-ve-ket-cau-thep.html) | A (text paywalled) | VN | Partly (preview only). Page lists status "replaced by TCVN 4613:1988" but also "under review" with an inconsistent effective date. | Vietnamese drawing conventions for steel structures: quantity written before the section symbol (example `2 L 65 x 8`); item numbers in circles 7-10 mm; mirror parts share a number with suffix T (right) / N (left); bill of materials lists right and left hand parts separately. |
| 6 | [TCVN 7571-16:2017 H sections (hethongphapluat mirror)](https://hethongphapluat.com/tieu-chuan-quoc-gia-tcvn-7571-16-2017-ve-thep-hinh-can-nong-phan-16-thep-chu-h.html) | A (text paywalled) | VN | Partly: title "Thep hinh can nong - Phan 16: Thep chu H", year 2017, replaces 7571-16:2006 (ISO 657-16:1980), based also on JIS 3192:2014 and a POSCO SS VINA proposal; dimension tables not visible. | The Vietnamese H-section standard exists in a 2017 edition derived partly from the JIS series. |
| 7 | [Circular 13/2021/TT-BXD Appendix VI 5.11](https://cdn.thuvienphapluat.vn/uploads/phapluat/2022-2/PNY/phuong-phap-do-boc-khoi-luong-cong-trinh.docx) | A (mirror) | VN | Y | Steel-structure quantity rules (classification, what is included/excluded). See `../05-takeoff-qa`. |
| 8 | [RICS NRM 2, work section 15](https://www.rics.org/content/dam/ricsglobal/documents/standards/october_2021_nrm_2.pdf) | A | UK | Y | Drawing information a steel measurer needs; weight-per-metre bands; fittings allowance. |
| 9 | [AISC Code of Standard Practice for Steel Buildings and Bridges (AISC 303)](https://www.aisc.org/products/publication/standards/aisc-303/) | A | US | N. Product page I tried returned 404 and the older press-release URL was not fetched. Search results said the 2016 and 2022 editions were free downloads: unverified. | Contract-document hierarchy (design drawings vs shop drawings vs approval drawings). Link only. |
| 10 | [AWS A2.4 Standard Symbols for Welding (ANSI webstore)](https://webstore.ansi.org/standards/aws/awsa298) | A | US | N (not opened; paid) | Weld symbols. Secondary pages found were commercial: C. Treat symbol reading as an expert-confirm item. |

Not found / not opened: JIS G 3192 / JIS G 3101 primary text (JISC); GB/T 11263 and GB/T 700/1591 primary text; EN 10365, EN 10025, EN 1090; ASTM A6/A992/A36/A572/A500; RCSC bolt specification; SCI "Blue Book" (steelconstruction.info pages I guessed returned 404).

## Section designations (what the drawing says versus what the table says)

| System | Typical callout | Reads as | Verified? |
|---|---|---|---|
| UK/EN UB, UC | `457x191x82 UB`, `203x203x52 UC` | nominal depth x width x kg/m (BS EN 10365 serial size). Actual depth and width differ (e.g. 457x191x67 actual 453.4 x 189.9). | Y for UB table (source 3); the 457x191x67 actual values come from a search summary: unverified |
| EN HE/IPE | `HEA 300`, `HEB 300`, `IPE 300` | series + nominal depth; HEA/HEB/HEM differ in flange/web thickness, depths differ slightly | Series names listed on Dlubal (source 4); relative dimensions: unverified (one third-party page was found inconsistent and rejected) |
| AISC | `W14x90`, `HSS8x6x1/2`, `L4x4x3/8`, `C10x15.3`, `WT7x34` | W: nominal depth (in) x weight (lb/ft); HSS: outside dims x wall; L: legs x thickness | Software form verified (source 2). The "nominal depth x lb/ft" meaning is general knowledge, repeated by search snippets: unverified in a primary source. Metric AISC form `W360x134` is mm x kg/m: unverified |
| JIS H | `H-300x150x6.5x9` | depth x width x web thickness x flange thickness (mm). | Format from general knowledge; JIS G 3192 listed in Dlubal; text not read: unverified |
| Chinese GB/T 11263 | `HW 250x250`, `HM 390x300`, `HN 450x200`, `TW/TM/TN` for tees | wide / medium / narrow flange series, nominal depth x width | Series names HW, HM, HN seen in Dlubal page titles; meaning of letters is general knowledge: unverified |
| Chinese I, channels | `I 32a`, `[ 20b` | GB/T 706: number = depth in cm, letter a/b/c = web thickness class | General knowledge, unverified |
| Vietnamese "thep hinh" | `I300`, `H300x150x6.5x9`, `U200`, `L100x100x10`, `V` for angle in trade usage | I/H/U (channel, also called C in some texts)/L (angle, also called V in trade). TCVN 7571 parts: -1 equal angles, -2 unequal angles, -11 U or C (sources disagree), -15 I, -16 H, -21 T | Part list from search snippets and mirror titles; 7571-11 U vs C naming conflict; real tables not read: mostly unverified |

Rules the machine can use regardless of region:
1. The callout is a *label*; take geometry and mass/m from a catalogue table keyed by the **standard and edition**, not from the label.
2. Nominal and actual dimensions differ (UB table). Never compute mass from nominal depth x width.
3. Same label, different standard: `H300x150x6.5x9` (JIS/VN) vs `HN 300x150` (GB/T) vs HEA/IPE: ask which catalogue the project uses.
4. Cross-check: label's kg/m vs catalogue kg/m (UK third number; AISC second number). Mismatch -> open question.

## Units
- Mass per metre in tables is kg/m (EN/JIS/GB/TCVN) or lb/ft (AISC US customary). 1 lb/ft = 1.488 kg/m (conversion constant, general arithmetic: 0.45359237 / 0.3048).
- Dimensions mm in EN/JIS/GB/TCVN; inches (often fractions, e.g. 3/8) in US drawings. Metric AISC drawings exist.
- Steel density 7850 kg/m3 (usual convention); for plates 7.85 kg/m2 per mm thickness. Derived by me; consistent with the Heaton mass formula for bars (see 03-rc).
- Bolt callouts mix diameter units (M20, 3/4 in) and hole sizes; see below.

## Plates, bolts, welds, connections
- Plates: `PL 12x200x450` style (thickness x width x length) is the common convention, in mm in metric sets and `PL 1/2x8x1'-6"` in US sets; Vietnamese sets may write a mark number and list in a bill of materials (TCVN 2234 preview: items numbered, list gives sizes). Always take thickness, width, length from the item list and verify against the detail.
- Bolts: callout normally gives count, diameter, grade, hole type (standard/oversize/slotted) and sometimes pretension. Grade systems: ASTM A325/A490 (US), ISO 898-1 classes 8.8/10.9 and EN 14399 (EU), JIS B 1186 (JP). **I did not open a primary source for any of these**: treat the list as a prompt for questions, not as verified knowledge.
- Welds: AWS A2.4 reference line with arrow side/other side, fillet size, all-around and field-weld flags (anatomy repeated in commercial secondary pages: C). ISO 2553 is the EN/ISO counterpart (not opened).
- Connections are often given by typical-detail notes ("provide shear tab per detail 3/S-501", "connections by fabricator for reactions shown"): the NRM2 section 15 intro and AISC 303 distinguish connections *designed by engineer of record* from *delegated to fabricator*. If the drawing is silent, raise a question: this changes the tonnage (fittings allowance).

## Framing plans, elevations, details
- Framing plan: members tagged with size, sometimes camber `(3/4)` and stud count; arrows give beam span direction for decking; level label gives top-of-steel (TOS) elevation. Elevation: bracing and column splices, base plate levels. Details: connection geometry, plate sizes, bolt/weld info.
- Typical checks (principle): every tag on plan has a schedule/detail; column marks on plan = column schedule; levels on plan match elevation; grid names identical.
- DrawingVQA (see `../06-research`) lists weld symbols, material hatches, discipline acronyms and cross-references among the hard parts of real IFC drawings.

## Steel grades
| Region | Grades seen on drawings | Status |
|---|---|---|
| US | ASTM A992 (W shapes), A36, A572 Gr 50, A500 Gr B/C (HSS), A1085 (HSS) | Names appear in the AISC database descriptions in search snippets and in STAAD naming (`_A1085`): partly verified. Yield strengths not verified here. |
| EU/UK | EN 10025-2 S275, S355 | Not opened; British Steel datasheet title shows EN 10365 only. Unverified here. |
| JP | SS400 (JIS G 3101), SM490 | Not opened. |
| CN | Q235B, Q355B (formerly Q345B) per GB/T 700 / GB/T 1591 | Not opened; Q355 name is from general knowledge: unverified. |
| VN | Per search snippets: TCVN 5709 (1993 edition names grades "XCT34, XCT38, XCT42, XCT52"; a 2009 edition is also mentioned; the brief writes "CCT34/CCT38"); imported/trade grades SS400, Q235, Q345 are very common | Unverified. Whether CCT and XCT are the same naming across editions is unresolved. No authoritative equivalence table found: do not map SS400 to S275 etc. without the engineer. |

## One-page checklist (steel)
1. Find the general-notes steel block: grades per member class, bolt specification, weld electrodes and procedure, coating/fireproofing, connection design responsibility, tolerances, code edition.
2. Build the **member list**: from framing plans (tags), column/beam schedules, elevations. Each entry: mark, section label, standard/edition, grade, length source, quantity source, sheet+revision+location.
3. Resolve each label against the catalogue for the stated standard; store catalogue id and kg/m; flag labels not found.
4. Read connection details: plate sizes, bolt count/size/grade, weld size/length; apply "typical" and "SIM" notes; note delegated-connection statements.
5. Check: grid and level consistency between plan, elevation, details; member lengths vs grid spacing; label kg/m vs table kg/m; count of marks on plan vs schedule.
6. Missing or contradictory item -> open question with sheet, revision, location and the quantity affected.

## Regional differences
- Label conventions differ (see table); mass per metre convention (kg/m vs lb/ft).
- Chinese-origin Vietnamese projects: GB/T and JIS section names appear in VN DWG files; TCVN catalogues exist for I/H/U/L but real project sets often cite the supplier catalogue.
- Delegated connection design is routine in the US (AISC 303) and the UK (NRM2/BCSA "Green Book"-style practice, not opened); in Vietnam it depends on the contract.

## Where sources disagree
- TCVN 7571-11: "U" (one source) vs "C" (another) for the same part.
- TCVN 5709: 1993 vs 2009 edition; XCT vs CCT names.
- TCVN 2234:1977 status: replaced by TCVN 4613:1988 (page) yet "under review"/odd effective date (mirror metadata is unreliable).
- Sources 2 and 1 differ on shape names (software vs AISC): not a conflict but a mapping risk.

## Gaps
- No primary table values (kg/m, areas) were read for AISC, JIS, GB, TCVN: only the UB table and metadata. Section libraries must be loaded from the official files before use.
- Bolt, weld and steel-grade standards not opened. Bolt grades and weld symbol details need an expert-written glossary in the skill, with sources added after the engineer approves them.
- No authoritative Vietnamese guide to reading steel drawings found (search results were blogs and standards metadata).
