# 05 Takeoff methodology and QA

Accessed 2026-11-06. Grades: A = standards body / government / official publisher primary text;
B = university, agency or DOT guide, manufacturer catalogue, peer-reviewed paper; C = blog or supplier.
"Verified" = I opened the primary text/page and checked the claim.

## Sources

| # | Source | Grade | Region | Verified | Supports |
|---|---|---|---|---|---|
| 1 | [Phu luc VI "Phuong phap do boc khoi luong cong trinh" of Thong tu 13/2021/TT-BXD](https://cdn.thuvienphapluat.vn/uploads/phapluat/2022-2/PNY/phuong-phap-do-boc-khoi-luong-cong-trinh.docx) (2021 original, docx mirror on the thuvienphapluat CDN; superseded in 5.4 by source 2). Gazette copy of the circular body (Cong bao 809+810; ends with "continued in issue 811+812"; Appendix VI is not in this file): [congbaocdn.chinhphu.vn PDF](https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2021/8/34356/36890-1-2021809-81013-2021-tt-bxd.pdf) | A (text) / mirror is B | VN | Y (2021 docx read in full; gazette PDF read, Appendix VI not in that file) | General measurement rules (I.1-6, II.1-2), rebar rule 5.6, concrete 5.4, formwork 5.5, steel structure 5.11. |
| 2 | [Consolidated text 37/VBHN-BXD, docx](https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/6/37-vbhn-bxd-6.docx) and [its 4-page cover PDF](https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/6/37-vbhn-bxd.pdf) | A | VN | Y (both read; I diffed Appendix VI 5.4, 5.6, 5.11 and the general rules against the 2021 text) | TT13/2021 was amended by TT 01/2025/TT-BXD (22 Jan 2025) and TT 60/2025/TT-BXD (30 Dec 2025). The consolidated Appendix VI keeps 5.6 (rebar) and 5.11 (steel structure) unchanged (whitespace only). **5.4 (concrete) changed**: the "rebar < 2 % by volume" condition was replaced by "rebar volume, ties, gusset plates, prestressing parts (except ducts) are not deducted" for estimates, concrete class wording ("cap do ben") was added, and a sentence ties acceptance/payment quantities to the contract. The consolidation date is not stated in the file; the URL path suggests June 2026. |
| 3 | [RICS NRM 2, 2nd ed., Oct 2021](https://www.rics.org/content/dam/ricsglobal/documents/standards/october_2021_nrm_2.pdf) (PDF, 355 pp.) | A | UK | Y (parts read) | Work section 11 (in-situ concrete, reinforcement) and 15 (structural metalwork): units, drawings required, schedules treated as drawings (2.7.3). Not stored locally (RICS copyright). |
| 4 | [ICMS coalition: International Cost Management Standard, 3rd ed.](https://icms-coalition.org/the-standard/) and [RICS "ICMS explained" PDF](https://www.rics.org/content/dam/ricsglobal/documents/standards/icms-3-explained.pdf) | A | global | Y (site + guide read) | High-level cost classification (project > ... levels), cost+carbon; NOT a rule set for measuring tonnes of rebar. Standard renamed "Cost Management" in 3rd ed. |
| 5 | [Colorado DOT Bridge Detail Manual ch. 4 Reinforcing (eff. 2026-05-29)](https://www.codot.gov/programs/bridge/bridge-manuals/bridge_detail_manual/dm-04-reinforcing-2026-05.pdf) (copy: `../03-rc/pdf/`) | B | US (bridges) | Y | 4.12: quantities include splice lengths; two independent quantity sets (detailer and checker), totals within 1 %, not averaged. 4.2: bar lists only when required. |
| 6 | [CSI MasterFormat](https://www.csiresources.org/standards/masterformat), [UniFormat](https://www.csiresources.org/standards/uniformat) | A | US/CA | Partly (pages exist, 200; they only point to CSI's paid standards page). Division titles (03 Concrete, 05 Metals) are from secondary sources: unverified. | Classification systems for specs (MasterFormat) and elements (UniFormat). Link only. |
| 7 | [CESMM4 overview (Designing Buildings wiki)](https://www.designingbuildings.co.uk/wiki/CESMM4) | C | UK | Y (page read) | Existence, publisher (ICE), compatible with NEC/FIDIC. CESMM4 text itself is paid: not read. |
| 8 | RFI guides: e.g. [Autodesk RFI guide](https://www.autodesk.com/blogs/construction/construction-rfi-guide-template/) | C | global | N (403 to my fetcher; search snippets only) | RFI = formal written clarification; paper trail. Vendor content. No agency source found. |

## What the sources say (my distillation)

### Vietnamese measurement rules (TT13/2021 Appendix VI; 2021 text, checked against the consolidated 37/VBHN-BXD text)
- I.1: measurement = measuring/counting/calculating on the basis of dimensions and quantities in the drawings, design notes and technical specifications.
- I.4: if an item cannot be measured exactly, use a *provisional quantity* ("khoi luong tam tinh") and re-measure at acceptance.
- I.5 and II.1.4(c): if a quantity is taken from the designer's schedule or from software, say so and **cite the sheet number holding the schedule** and the way it was determined. The person compiling must understand the data.
- II.1.4(d): round before summing; decimals to three places.
- II.2.1: study the drawings and notes first; ask the designer to explain anything affecting quantities.
- II.2.5: review for completeness of item list against design, correct names/units/derivation, clarity of info for pricing.
- 5.6 Rebar: classify by type (ordinary/prestress, plain/deformed), grade, group, **diameter**, structural part (foundation, column, wall...). Quantity includes lap splices, threaded/sleeve couplers, spacers (con ke), connecting bolts and temporary rebar (e.g. spacer bars between two mats). Mass from the specific weight at **nominal diameter**.
- 5.4 Concrete: 2021 text did not deduct rebar < 2 % by volume, ties, gusset plates, openings < 0.1 m3. **Consolidated text (current)**: for estimates, rebar volume, ties, gusset plates and prestressing parts (except ducts) are not deducted, and voids < 0.1 m3 inside the member are not deducted; acceptance quantities follow the contract. Use the consolidated wording.
- 5.11 Steel structure: classify by steel type, technical properties, member size, connection type (weld/bolt); mass = sum of bars and plates; includes lap joints per spec, cut/bevel waste and cut-outs < 0.1 m2 each, bolts, nuts and spacers; excludes temporary bolts/erection aids.
- Status: 5.6 and 5.11 identical in the consolidated text (checked by diff); 5.4 changed as above. Other clauses of the circular (norms, indicators) not compared. Confirm the consolidation date on the ministry portal before citing as "current".

### UK (NRM 2, 2021)
- Reinforcement (11.33-34): measured in tonnes by nominal size, split straight / bent / curved / links; hooks, tying wire, spacers, cutting and bending are *included*; chairs "included unless not at the contractor's discretion". Mesh (11.37): m2.
- Structural steelwork (15): framed members in tonnes, banded by length (<=1 m, 1-9 m, >9 m) and mass per metre (<=25, 25-50, 50-100 kg/m, then steps of 50), split by member type; fittings allowance either calculated weight or stated percentage.
- 2.7.3: reinforcement (bar bending) schedules are to be treated as drawings (i.e. a contract document that the quantity surveyor may rely on).
- Section 15 lists the minimum drawing information: position of the work in the structure, types and sizes of all members and their positions, details of connections or reactions/moments/axial loads.

### US bridge practice (CDOT 4.12)
- Include splice lengths explicitly; percentage allowances "not acceptable".
- Two independent quantity sets, within 1 %, never averaged: a transferable "sum-of-parts vs independent recompute" rule.

### Rebar and plate mass: derive, do not memorise
Mass per metre of a round bar = (pi/4) * d^2 * density. With d in mm and density 7850 kg/m3:
`(pi/4) * (d/1000)^2 * 7850 = 0.006165 * d^2 kg/m` (equivalently d^2/162.2). Example: d = 16 mm -> 1.578 kg/m.
Plate mass = thickness(mm) * 7.85 kg/m2 per mm. Density 7850 kg/m3 is the usual convention; a Vietnamese search snippet says
7.85 g/cm3 is used in TCVN section tables (not verified in the standard itself). Rolled sections: use catalogue values (see 02-steel), not derived values,
because fillets make the true area differ from simple sums.

## Double-check strategies (practice, not quotes; sources 1, 3, 5 support the principles)
1. **Cross-sheet consistency**: member mark and size on plan vs schedule vs section vs elevation vs detail; grid and level labels identical on every sheet.
2. **Sum-of-parts**: member count by plan vs sum of schedule quantities; rebar sum by bar mark = schedule total; weight of assembly = sum of parts; compare with designer's stated tonnage if the drawing prints one.
3. **Independent second path** (CDOT 4.12): recompute totals by a different method (e.g. by member vs by bar diameter), compare within a tolerance, never average, resolve differences.
4. **Order-of-magnitude check**: steel kg/m2 floor area and rebar kg/m3 concrete against typical ranges *from the engineer's own past projects* (I did not find an authoritative range; do not hard-code one).
5. **Revision control**: every quantity tied to sheet + revision; quantities from superseded sheets flagged.
6. **Provisional vs measured**: mark items that cannot be measured (TT13 I.4).

## Common errors (from sources + general practice; the list is a synthesis, not a quote)
- Using a superseded revision or a sheet not listed in the index.
- Mixing units (mm vs m vs inch), or reading a "NOT TO SCALE"/overridden dimension as measured.
- Counting a typical detail once instead of N times ("TYP.", "U.N.O.", "SIM.").
- Forgetting splices, hooks, spacers, couplers (TT13 5.6, NRM2 11.34, CDOT 4.12 all call these out).
- Double counting where a member is shown on plan and elevation.
- Rebar: wrong length from shape code (no allowance for bends, see 03-rc).
- Steel: ignoring plates, stiffeners, bolts, base plates, shear studs, field-bolted fittings (NRM2 15 "allowance for fittings").
- Applying a foreign rule (NRM/CESMM/ICMS) where the contract is Vietnamese (TT13).

## Confidence and RFI practice
- RFI = a formal written question with a written answer, kept as record (secondary vendor sources only, grade C; no government guidance found).
- Harness mapping: low-confidence or conflicting value -> `questions.md` entry with sheet, revision, location, what was found, what is needed, impact (which quantity). A quantity that depends on an unanswered question is reported as *provisional* (TT13 I.4) with the question id, not as a measured value.

## One-page checklist (takeoff and QA)
1. **Scope and rule set**: which rule applies (contract clause; Vietnam default = Circular 13/2021/TT-BXD Appendix VI as consolidated in 37/VBHN-BXD; UK NRM 2; other). Write the rule id in the quantity sheet.
2. **Classify before measuring** (TT13 5.6, 5.11): rebar by type (ordinary/prestress, plain/deformed), grade, diameter, structural part; steel by steel type, member size, connection type (weld/bolt). Concrete by mix, member, thickness/height class.
3. **Inclusions** (TT13): rebar quantity includes laps, couplers, spacers (con ke), connecting bolts and temporary spacer bars; steel mass = bars + plates, includes cut/bevel waste and small cut-outs, bolts and nuts, excludes temporary erection bolts; concrete does not deduct rebar, ties, gusset plates or small voids (consolidated 5.4).
4. **Source of each number**: if taken from a designer's schedule, cite the sheet number holding it (TT13 II.1.4(c)); if from software, say how it was determined (TT13 I.5). Value record carries sheet+revision+region+method+confidence.
5. **Measure from dimensions, never by scaling**; units checked (mm vs m).
6. **Round only at the end**: three decimal places (TT13 II.1.4(d)); keep unrounded values in the detail table.
7. **Provisional items**: anything not measurable or dependent on an open question is flagged provisional with the question id (TT13 I.4).
8. **Two independent paths** (CDOT 4.12): second method or second reader; agree within a stated tolerance (1 % for rebar is the CDOT value; no Vietnamese tolerance found); do not average; resolve differences.
9. **Sum-of-parts and cross-sheet** checks (see `../reading-checklist.md` D1-D3): counts plan vs schedule, bar mass vs schedule total, mark/size equality on all sheets.
10. **Review** (TT13 II.2.5): item list complete against design, names/units/derivation clear, enough information for pricing.
11. **Report**: measured vs provisional separately, with the list of open questions that affect each total.

## Regional differences
- VN (TT13) classifies rebar by *diameter and grade* and includes splices/spacers in the quantity; UK (NRM2) classifies by nominal size and shape class, bands steel by kg/m; US bridge manual forces explicit splice lengths. Cost classification (ICMS, MasterFormat, UniFormat) is separate from measurement rules.
- ICMS 3 is a cost classification, not a measurement standard: do not treat it as rules for takeoff.

## Where sources disagree
- Whether lap splices are inside the designer's bar-schedule weights: TT13 5.6 says the *measured quantity* includes laps; whether a given schedule already includes them depends on that schedule's own notes (BS 8666 / ISO 4066 not read). Unresolved: read the schedule notes and raise a question if silent (see 03-rc).
- Steel: TT13 excludes temporary bolts and measures plates/bars; NRM2 allows either calculated weight or percentage for fittings. Decide per contract.

## Gaps / unverified
- Full CESMM4, MasterFormat/UniFormat text (paid). Division/class titles not verified from primary text.
- Only Appendix VI 5.4/5.6/5.11 and the general rules were diffed against the amendments; other clauses were not compared, and the consolidation date is not printed in the file.
- No authoritative RFI standard found. No agency-published typical kg/m2 or kg/m3 ratios found.
- Vietnamese price/norm system (Dinh muc, Thong tu 12/2021) not covered here.
