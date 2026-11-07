# 01 Drawing-set anatomy and reading order

Accessed 2026-11-06. Grades: A = standards body / government / official publisher primary text;
B = university, agency or DOT guide, manufacturer catalogue, peer-reviewed paper; C = blog, wiki or supplier.
"Verified" = I opened the page or file and the claim is on it. Where a Vietnamese standard is reached only
through a mirror (hethongphapluat.com preview), the grade is that of the standard but the access is a mirror.

## Sources

| # | Source | Grade | Region | Verified | Supports |
|---|---|---|---|---|---|
| 1 | [ACI 315R-18 "Guide to Presenting Reinforcing Steel Design Details"](https://www.concrete.org/store/productdetail.aspx?ItemID=31518) (free preview with table of contents: [315R-18_preview.pdf](https://www.concrete.org/Portals/0/Files/PDF/Previews/315R-18_preview.pdf); full text paid) | A | US | Y (TOC read; body paywalled) | The table of contents lists these sheet types in this sequence: general notes, plan, elevation, section, large-scale view, detail, schedule/diagram, foundation sheets/schedules, user-defined, 3D (section 4.3 "Order of sheets" exists, but its content was NOT read: paywalled). |
| 2 | [Designing Buildings wiki: How to read technical drawings](https://www.designingbuildings.co.uk/How_to_read_technical_drawings) | C | UK | Y | Title block fields (drawn/checked/approved, status, drawing no., revision, scale, sheet size), revision block, "do not scale", zones, abbreviation key. |
| 3 | [TCVN 5571:2012 title blocks (preview on hethongphapluat.com)](https://hethongphapluat.com/tieu-chuan-quoc-gia-tcvn-5571-2012-ve-he-thong-tai-lieu-thiet-ke-xay-dung-ban-ve-xay-dung-khung-ten.html) | A (text paywalled) | VN | Partly: scope, placement lower-right, fonts per TCVN 4608:2012, replaces TCVN 5571:1991. Field list is the page's summary, not the clause text. | Vietnamese title block placement and content. |
| 4 | [Decision 3621/QD-BKHCN, 28/12/2012 (mirror)](https://hethongphapluat.com/quyet-dinh-3621-qd-bkhcn-nam-2012-cong-bo-tieu-chuan-quoc-gia-do-bo-truong-bo-khoa-hoc-va-cong-nghe-ban-hanh.html), also [caselaw.vn](https://caselaw.vn/van-ban-phap-luat/178260-quyet-dinh-so-3621-qd-bkhcn-ngay-28-12-2012-cua-bo-truong-bo-khoa-hoc-va-cong-nghe-cong-bo-tieu-chuan-quoc-gia) | A (decision) via mirror | VN | Y (list read on the hethongphapluat mirror) | Confirms the 2012 set: TCVN 5571 (title block), 5572 (RC working drawings), 5896 (= ISO 9431:1990: layout, text, title block), 6083 (= ISO 7519:1991: general presentation, general arrangement and assembly drawings), 6084 (= ISO 3766:2003: rebar), 6085 (= ISO 7437:1990: prefabricated structures), 4608 (lettering), 5672 (construction document sets), 5671 (architectural design set). |
| 5 | [ISO 7200:2004 data fields in title blocks (ISO page)](https://www.iso.org/standard/35446.html) | A | global | N (ISO site returned 403 to my fetcher). Search results disagree on status: ISO says confirmed 2025, AFNOR/IHS list it as cancelled/withdrawn. | International list of title-block data fields. Status unresolved. |
| 6 | [National CAD Standard (NIBS)](https://www.nationalcadstandard.org/) | A | US | Y (site is paid, "Order the NCS to obtain a license"; V7 referred to) | Uniform Drawing System sheet identification (discipline prefix S/A/M...). I could not read the UDS text. |
| 7 | [DrawingVQA, arXiv 2607.15418](https://arxiv.org/abs/2607.15418) | B | US | Y | Says the NCS was used as basis for interpreting symbols/callouts; question types give a practical taxonomy: sheet title, single-sheet inference, cross-sheet expert reasoning. |
| 8 | [TT13/2021 Appendix VI](https://cdn.thuvienphapluat.vn/uploads/phapluat/2022-2/PNY/phuong-phap-do-boc-khoi-luong-cong-trinh.docx) II.2.1 | A (mirror) | VN | Y | "Study and master the design drawings and accompanying documents; ask the designer to explain where needed" as step one. |
| 9 | [CDOT Bridge Detail Manual ch.4](https://www.codot.gov/programs/bridge/bridge-manuals/bridge_detail_manual/dm-04-reinforcing-2026-05.pdf) 4.3 | B | US | Y | Each sheet should carry enough information to determine bar shapes without hunting other sheets: a quality standard we can test. |
| 10 | [RICS NRM 2](https://www.rics.org/content/dam/ricsglobal/documents/standards/october_2021_nrm_2.pdf) section 15 intro | A | UK | Y | Minimum structural-steel drawing information: general arrangement plans/sections/elevations, member types and sizes and positions, connection details or reactions. |

## One-page checklist (distilled; full ordered method is in `../reading-checklist.md`)

1. **Sheet index first.** List every sheet (number, title, revision, date). Mark sheets present in files but missing from the index, and vice versa. Missing -> open question.
2. **Per sheet, read the title block.** Project, sheet number and title, scale(s), revision letter/date, status ("for construction", "for tender"...), drawn/checked/approved. Different scale per view is normal: record per view, not per sheet.
3. **Revision history.** Take the latest revision per sheet; note clouds/deltas. If two files carry the same sheet number with different revisions, use the later and ask the engineer which is current.
4. **General notes and legends before plans.** Material grades, cover, laps, codes, tolerances, "U.N.O.", abbreviation list, symbol legend. Notes on a plan sheet override general notes only if the drawing says so: otherwise ask.
5. **Units and scale.** Units per sheet (mm, m, ft-in), and "do not scale" notes. Dimension text beats scaling.
6. **Grids and levels.** Grid names and spacings, level names and elevations (datum), north arrow/true north vs project north. These anchor every later position.
7. **Structural system and sheet types.** Identify plans, elevations, sections, details, schedules (the ACI 315R-18 table of contents lists sheet types in the sequence general notes, plan, elevation, section, large-scale, detail, schedule, foundation; section 4.3 content not read, so this is not a verified ordering rule).
8. **Cross-references.** Follow every detail/section bubble to its target sheet; record unresolved references.
9. **Record provenance for every value**: file, sheet, revision, region (page/bbox/grid ref/detail), method, confidence.
10. **Stop and ask** when: index and files disagree; revision unclear; units not stated; grids inconsistent across sheets; a referenced sheet is missing.

## Regional differences
- **Vietnam**: sheet layout and title block per TCVN 5896:2012 and TCVN 5571:2012; drawing sets per TCVN 5672:2012. Title block at lower right (as in most countries). Field names in Vietnamese; expect legacy fonts (TCVN3/VNI) in DWG.
- **US**: NCS/UDS sheet identification with a discipline prefix (S for structural; seen in search-result summaries only) and "S-101" style numbering (general knowledge, UDS text not read); levels in feet-inches; north arrow plus project north.
- **UK/EU**: ISO 7200 data fields; drawing numbering by project/originator/zone/level/type (ISO 19650 style); I did not verify the exact scheme from a primary source.
- The "read zones right to left" statement in the Designing Buildings wiki is not a general rule; do not encode it.

## Where sources disagree
- Title-block position: TCVN 5571 puts it in the lower-right quadrant; ISO 7200 text could not be read (ISO 403). Do not assume fixed position: locate by content (keywords: scale, drawing no., revision).
- ISO 7200:2004 status (current vs withdrawn) conflicts across search results.
- Designing Buildings says revision block is top-right; many offices put revisions next to the title block. Search by content, not by position.

## Gaps / unverified
- NCS UDS and ISO 7200 text not read (paid / blocked).
- TCVN 5571:2012 and 5896:2012 full text paywalled; field lists come from mirrors' summaries.
- I found no authoritative Vietnamese guide that gives a reading order for a whole structural set (only per-topic standards). The reading order in `../reading-checklist.md` is my synthesis.
- TCVN 5894 (named in the brief): no matching document found in two searches; title and scope unknown: **unverified**.
