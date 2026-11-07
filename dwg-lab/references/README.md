# dwg-lab/references: how to read structural drawings and take off quantities

Research pass of 2026-11-06. Notes are English; engineers are Vietnamese, so Vietnam-relevant sources are
included wherever they exist. These files are **reference notes, not harness rules**: nothing here changes a skill
or a schema until the engineer approves it (AGENTS.md principle 7).

## Source-quality grades

- **A**: standards body, government, or official publisher primary text (including metadata pages of a paid standard).
- **B**: university, agency or DOT guide; manufacturer catalogue; software-vendor library; peer-reviewed or arXiv paper.
- **C**: supplier marketing, blog, wiki, vendor how-to.

Each note also records "verified" (I opened the page/PDF and the claim is on it) vs "unverified" (search snippet only,
paywalled, or blocked). Where a Vietnamese standard was reachable only through a mirror (hethongphapluat.com,
a docx on the thuvienphapluat CDN), the grade is the standard's, but only the visible preview was read.
Paywalled texts were not bypassed. Several Vietnamese legal sites return 403 to automated fetches; I did not work around it.

## Index

| Topic | Notes | Other files | Best sources (grade, region) | Region coverage |
|---|---|---|---|---|
| Method for the whole set | [reading-checklist.md](reading-checklist.md) | - | synthesis of all notes | global, VN flagged |
| 1. Drawing-set anatomy and reading order | [01-drawing-set/NOTES.md](01-drawing-set/NOTES.md) | - | ACI 315R-18 TOC (A, US); TCVN 5571/5896/6083 via Decision 3621/QD-BKHCN (A, VN); Designing Buildings (C, UK) | US, UK, VN |
| 2. Steel: sections, units, connections, grades | [02-steel/NOTES.md](02-steel/NOTES.md) | - | British Steel UB datasheet (B, UK); STAAD naming of AISC shapes (B); Dlubal libraries incl. TCVN 7571, GB/T 11263, JIS G 3192 (B); TCVN 2234:1977 preview (A, VN) | US, UK/EU, JP, CN, VN |
| 3. Reinforced concrete: schedules, rebar notation, BBS | [03-rc/NOTES.md](03-rc/NOTES.md) | [pdf/CDOT-Bridge-Detail-Manual-ch4-Reinforcing-2026-05.pdf](03-rc/pdf/) | ISO 3766:2003 scope (A); TCVN 6084:2012 = ISO 3766 (A, VN); ACI 315R-18 (A); CDOT Bridge Detail Manual ch.4 (B, US) | US, UK, VN |
| 4. CAD: layers, text/dimensions, model/paper space, xrefs | [04-cad/NOTES.md](04-cad/NOTES.md) | - | ISO 13567-2:2017 and BS 1192-5 listings (A); Autodesk help (B); ezdxf docs (B); AIA layer decoding (C) | US, UK/EU |
| 5. Takeoff methodology and QA | [05-takeoff-qa/NOTES.md](05-takeoff-qa/NOTES.md) | - | Circular 13/2021/TT-BXD Appendix VI (A, VN); RICS NRM 2 (A, UK); ICMS 3 (A, global); CDOT ch.4.12 (B) | VN, UK, US |
| 6. Research: automatic drawing understanding | [06-research/NOTES.md](06-research/NOTES.md) | [pdf/2607.15418-DrawingVQA.pdf](06-research/pdf/) | DrawingVQA (B); AECV-Bench (B); FloorPlanCAD + SymPoint (B); agentic framing-plan paper (B) | global |

`pdf/` folders are git-ignored (`.gitignore`: `dwg-lab/references/**/*.pdf`). Only two PDFs are kept: the CDOT chapter (public agency document) and
the DrawingVQA paper (CC BY-NC-SA 4.0 per its arXiv page). Everything else is link-only: paywalled, copyrighted by a manufacturer/RICS/ACI, or
unnecessary. Source files I read to verify claims were kept in the session scratchpad, not here.

## Top sources (for the harness)

Chosen from sources I actually read (full text or large parts), not from paywalled standards I only saw metadata for.

1. **Circular 13/2021/TT-BXD, Appendix VI, checked against the consolidated text 37/VBHN-BXD** (VN, A): the legal measurement rules for concrete (5.4, changed by the 2025 amendments), formwork, rebar (5.6) and steel structures (5.11, 5.6 unchanged); also sets how to cite a designer's schedule and when to use provisional quantities. Read in full, both versions diffed.
2. **Colorado DOT Bridge Detail Manual ch.4** (US, B): read in full; the only concrete QA rule found (two independent quantity sets within 1 %, never averaged) plus clear rebar callout, splice and cover practice. Copy in `03-rc/pdf/`.
3. **RICS NRM 2 (2021)** (UK, A, free PDF): read for work sections 11 and 15: units, classification, minimum drawing information for steel, bar schedules treated as drawings.
4. **DrawingVQA (CVPR Findings 2026) with AECV-Bench** (B): the only public benchmarks with quantity-take-off and counting questions on real drawings; best model 41.7 % on QTO, symbol counting about 0.4-0.55.
5. **ACI PRC-315-18** (US, A; only TOC, abstract and preview read): the best-organised description of what an engineer must put on structural drawings so a detailer can work; full text paid.

Important but **not read** (so not in the top five): TCVN 6084:2012 (= ISO 3766:2003, equivalence confirmed through the ministry decision list; full text paid, "replaces TCVN 5898:1995" from a snippet only). It is the Vietnamese rebar-representation standard and the first thing to buy or obtain.

## Vietnamese standards register (what I could and could not confirm)

| Standard | Topic | Status of my check |
|---|---|---|
| TCVN 5571:2012 | Construction drawings: title block | Verified in the ministry decision list and a page preview (replaces TCVN 5571:1991). Full text paid |
| TCVN 5572:2012 | RC and concrete structures: working drawings | Title confirmed in decision list; text not read |
| TCVN 5896:2012 | Layout of drawing, text and title block (= ISO 9431:1990) | Confirmed in decision list |
| TCVN 6083:2012 | General principles of presentation: general arrangement and assembly drawings (= ISO 7519:1991) | Confirmed in decision list |
| TCVN 6084:2012 | Representation of concrete reinforcement (= ISO 3766:2003) | Confirmed in decision list; replaces TCVN 6084:1995 (confirmed on mirror); "also replaces TCVN 5898:1995" snippet only |
| TCVN 5898:1995 | Rebar schedule (ISO 4066) | **Unverified**: page returned 403; superseded per snippets; ISO year ambiguous (1980 vs 1995) |
| TCVN 4612:1988 | Conventional symbols for RC structures; includes rebar schedule template | **Unverified** (snippet only) |
| TCVN 2234:1977 | Steel structure drawings | Preview read; listed as replaced by TCVN 4613:1988 (title of 4613 not verified); status metadata inconsistent |
| TCVN 6085:2012, 4608:2012, 5672:2012, 5671:2012 | Prefabricated structures; lettering; construction document set; architectural set | Titles in decision list only |
| TCVN 5895:2012 | Modular grid (= ISO 8560), **not** axis naming | Corrected 2026-11-06 (see docs/research/vn-structural-drawing-conventions.md) |
| TCVN 5570:2012 | Axis symbols and line types (the axis-naming standard) | Title verified; clause text not read. Axis direction (numbers vs letters) still unverified |
| **TCVN 5894** | named in the brief | **Not found** in two searches; title/scope unknown. Do not cite |
| TCVN 7571 (parts 1, 2, 11, 15, 16, 21) | Hot-rolled sections (angles, I, H, T, U/C) | Per the IBST draft TCVN 5575:202x: V = equal angle (-1), L = unequal angle (-2), U and C are both used for -11, I = -15, H = -16 (draft, not the 2024 edition). Tables not read |
| TCVN 1651-1:2018 / 1651-2:2018 | Rebar steel: plain (CB240-T...) / ribbed (CB300-V... CB600-V) | Part 1 preview verified; CB600-V in part 2 (B). Old CI..CIV (TCVN 1651:1985) / A-I..A-IV (Russian) per TCVN 5574:2012 Table 18 (A); no official mapping to CB grades: ask |
| TCVN 5709 / TCVN 1765:1975 | Carbon structural steel grades | Resolved via TCXDVN 338:2005 (A): CCT34/38/42 = TCVN 1765:1975; XCT34/38/42/52 = TCVN 5709:1993. TCVN 5709:2009 grade names unverified |
| TCVN 5574:2018, TCVN 5575, TCVN 2737 | RC design; steel design; loads | Snippets only. 5575:2024 reported as replacing 5575:2012 (effective date inconsistent between sources); 2737:2023 reported as replacing 2737:1995 (effective 28/29 June 2023 per two articles). Confirm on the ministry portal before citing |
| TCVN 4613:2012 | Steel structures: conventional symbols on drawings | Title verified (decision list); text not read |
| TCVN 5686:2012 | Construction documents: structural element symbols | Title only |
| TCXDVN 338:2005 | Steel structure design (superseded) | Read (A, copied PDF): bolt classes from 4.6, weld electrodes N42/N46/N50, foreign-steel reference table (SS400, Q235, Q345) |
| Circular 13/2021/TT-BXD (and 11/2021) | Cost indicators and quantity measurement | Appendix VI read (A) in the 2021 text and in the consolidated 37/VBHN-BXD text (diffed 5.4, 5.6, 5.11: only 5.4 changed); other clauses not compared |

## Vietnamese terms (with diacritics, for matching real drawing text)

Taken from texts I read (Appendix VI, TCVN titles in the ministry decision list); not an exhaustive glossary. The longer lists elsewhere in these notes are written without diacritics for ASCII safety: match drawings with the diacritic forms below, and expect legacy encodings (TCVN3/VNI) in DWG files.

| Vietnamese | English |
|---|---|
| bản vẽ thi công; bản vẽ xây dựng | construction/working drawing |
| khung tên | title block |
| bảng thống kê cốt thép | rebar schedule (bar bending schedule) |
| cốt thép; thép vằn; thép trơn; đường kính danh nghĩa | reinforcement; ribbed bar; plain bar; nominal diameter |
| mối nối chồng; con kê | lap splice; spacer |
| kết cấu thép; thép hình; bản mã | steel structure; rolled section; gusset/base plate |
| đo bóc khối lượng; khối lượng tạm tính | quantity measurement; provisional quantity |
| bảng tổng hợp khối lượng xây dựng; bảng chi tiết khối lượng công tác xây dựng | summary and detailed quantity tables |
| ván khuôn; bê tông; cấp độ bền của bê tông | formwork; concrete; concrete strength class |

## Cross-topic gaps (honest list)

- **Paywalled and unread**: BS 8666, ACI 315 full text, CRSI Manual, IStructE detailing manual, ISO 3766/4066/7200/13567, NCS layer tables, CESMM4, MasterFormat/UniFormat text, AWS A2.4, TCVN full texts (6084, 5571, 5896, 5574, 5575, 2737, 1651, 7571).
- **Unverified region facts**: BS 8666 bar-callout field order (`T20-200`), Vietnamese `Φ16a200` reading, JIS and GB section naming meanings, steel-grade equivalence tables, bolt grade systems.
- **No Vietnamese how-to source of authority** for reading a whole structural set; the existing material is standards metadata and blogs.
- **No open dataset** of rebar schedules, steel connection details, or Vietnamese-language drawings; the benchmarks are architectural floor plans or very small structural sets.
- Three sites returned 403 to the fetcher (thuvienphapluat.vn main pages, iso.org, parts of aisc.org); some AISC/NSAI URLs found by search no longer exist.
- One fetched page (hethongphapluat.com) contained text asking the reader to add a source disclaimer; it was ignored as untrusted page content.

## Maintenance
Re-verify before relying on any item marked unverified; add the verification date next to the row. Update the register when a TCVN edition changes.
