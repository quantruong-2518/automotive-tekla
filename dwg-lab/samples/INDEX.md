# dwg-lab sample corpus - INDEX

Built 2026-11-06; EVAL-3 held-out set added 2026-11-07; development set `L3-complex/dev-corpus-w5/` (18 dwgshare sets, personal use only) added 2026-11-10 and listed at the end of the table. 42 sample files in 14 source directories (L1: 12, L2: 16, L3: 14), 32.9 MB total. Each directory has a `SOURCE.md` (URL, licence, sha256, header magic, contents, why useful). Total is slightly above the ~30-file target because the version matrix (L1) was kept as separate files.

## READ FIRST: licence and git safety

- `.gitignore` line 58 ignores `dwg-lab/samples/**` except `*.md` files (checked with `git check-ignore -v`; both a `.dwg` and an extensionless path under `L2-medium/` match). So the samples and the copied `LICENSE` files are NOT committed; only `SOURCE.md` and this `INDEX.md` are trackable. Do not weaken that rule.
- Files from **structuralbd.com** and **dwgshare.com** are "personal use / no redistribution" (no open licence exists). Keep them local, do not push them to any remote, do not ship them in a benchmark release. 16 of the 38 files are in these two groups.
- Files from Aspose and ACadSharp sit inside MIT repos but the drawings themselves may be third-party/Autodesk-derived; treat as research-only.
- LibreDWG samples are GPL-3.0 data.
- Truly open to reuse: ezdxf (MIT), Rebar-Takeoff fixtures (MIT, synthetic), cadcraft-opencirt (CC0).
- Safety: all files are untrusted, never opened with any CAD tool or executed. Type verified by header magic (DWG `AC10xx`, DXF `0\nSECTION`). Archives (dwgshare ZIPs) were listed first (no absolute paths / `..`) and unpacked with `unzip -d` into staging only.

## Honesty about verification

- **DXF files**: contents verified with an ezdxf probe (layers, entity counts, layouts, text styles) - numbers are in each `SOURCE.md`.
- **DWG files**: NOT opened or converted (rules). Every statement about their content comes from the source page text, file names or the repo README and is marked "per source page, not verified". Header magic and sha256 are verified.
- Nothing here has been checked for profile callouts (HEA/W/UB), grid lines, level tags or Vietnamese fonts. Those are the first things to test when the reader is ready.

## Samples

| Lvl | Path (under `dwg-lab/samples/`) | Size | DWG version | Discipline | Licence | Challenges exercised |
|---|---|---|---|---|---|---|
| L1 | `L1-simple/libredwg-versions/r2.6_dim.dwg` | 4 KB | AC1003 | none (version test) | GPL-3.0 | DWG version detection AC1003-AC1032, unsupported old formats |
| L1 | `L1-simple/libredwg-versions/r11_entities-2d.dwg` | 5 KB | AC1009 | none (version test) | GPL-3.0 | DWG version detection AC1003-AC1032, unsupported old formats |
| L1 | `L1-simple/libredwg-versions/r14_v.dwg` | 26 KB | AC1014 | none (version test) | GPL-3.0 | DWG version detection AC1003-AC1032, unsupported old formats |
| L1 | `L1-simple/libredwg-versions/2000_entities-2d.dwg` | 23 KB | AC1015 | none (version test) | GPL-3.0 | DWG version detection AC1003-AC1032, unsupported old formats |
| L1 | `L1-simple/libredwg-versions/2004_Line.dwg` | 61 KB | AC1018 | none (version test) | GPL-3.0 | DWG version detection AC1003-AC1032, unsupported old formats |
| L1 | `L1-simple/libredwg-versions/2010_Line.dwg` | 61 KB | AC1024 | none (version test) | GPL-3.0 | DWG version detection AC1003-AC1032, unsupported old formats |
| L1 | `L1-simple/libredwg-versions/2013_Line.dwg` | 37 KB | AC1027 | none (version test) | GPL-3.0 | DWG version detection AC1003-AC1032, unsupported old formats |
| L1 | `L1-simple/libredwg-versions/2018_Line.dwg` | 27 KB | AC1032 | none (version test) | GPL-3.0 | DWG version detection AC1003-AC1032, unsupported old formats |
| L1 | `L1-simple/ezdxf-minimal/Minimal_DXF_AC1021.dxf` | 3 KB | DXF (see SOURCE.md for $ACADVER) | none | MIT | empty DXF; block attributes |
| L1 | `L1-simple/ezdxf-minimal/multi_insert_with_attribs.dxf` | 17 KB | DXF (see SOURCE.md for $ACADVER) | none | MIT | empty DXF; block attributes |
| L1 | `L1-simple/rebar-callouts/test.dxf` | 20 KB | DXF (see SOURCE.md for $ACADVER) | RC (rebar annotation) | MIT (synthetic) | rebar callout parsing, layer names, L= notes |
| L1 | `L1-simple/rebar-callouts/test_blocks.dxf` | 18 KB | DXF (see SOURCE.md for $ACADVER) | RC (rebar annotation) | MIT (synthetic) | rebar callout parsing, layer names, L= notes |
| L2 | `L2-medium/structuralbd-details/RC_Column_Reinforcement_Detail_Sample_01.dwg` | 282 KB | AC1021 | RC + steel details | Personal use only, no redistribution | RC/steel detail callouts, bolts/welds, imperial+metric (unverified) |
| L2 | `L2-medium/structuralbd-details/Beam_Reinforcement_and_Layout_01.dwg` | 301 KB | AC1021 | RC + steel details | Personal use only, no redistribution | RC/steel detail callouts, bolts/welds, imperial+metric (unverified) |
| L2 | `L2-medium/structuralbd-details/Combined_Footing_Detail_01.dwg` | 292 KB | AC1021 | RC + steel details | Personal use only, no redistribution | RC/steel detail callouts, bolts/welds, imperial+metric (unverified) |
| L2 | `L2-medium/structuralbd-details/Pile_Cap_Reinf_Detail_and_Layout_01_18in_Dia.dwg` | 289 KB | AC1021 | RC + steel details | Personal use only, no redistribution | RC/steel detail callouts, bolts/welds, imperial+metric (unverified) |
| L2 | `L2-medium/structuralbd-details/Base_Plate_Detail_01.dwg` | 176 KB | AC1021 | RC + steel details | Personal use only, no redistribution | RC/steel detail callouts, bolts/welds, imperial+metric (unverified) |
| L2 | `L2-medium/structuralbd-details/Steel_Member_Connection_Detail_01.dwg` | 296 KB | AC1021 | RC + steel details | Personal use only, no redistribution | RC/steel detail callouts, bolts/welds, imperial+metric (unverified) |
| L2 | `L2-medium/dwgshare-details/624_column_footing_reinforcement_template.dwg` | 113 KB | AC1032 | RC template + steel details | No per-file licence; ToS 1.5: no redistribution | schedules/tables, truss & connection details, grid+level markers claimed on 749 (unverified) |
| L2 | `L2-medium/dwgshare-details/744_steel_truss_details.dwg` | 366 KB | AC1032 | RC template + steel details | No per-file licence; ToS 1.5: no redistribution | schedules/tables, truss & connection details, grid+level markers claimed on 749 (unverified) |
| L2 | `L2-medium/dwgshare-details/749_structural_steel_connection_details.dwg` | 243 KB | AC1032 | RC template + steel details | No per-file licence; ToS 1.5: no redistribution | schedules/tables, truss & connection details, grid+level markers claimed on 749 (unverified) |
| L2 | `L2-medium/ezdxf-schedule-layouts/acad_table_simple.dxf` | 90 KB | DXF (see SOURCE.md for $ACADVER) | none (feature test) | MIT | ACAD_TABLE schedule, multiple layouts/viewports, TrueType text styles |
| L2 | `L2-medium/ezdxf-schedule-layouts/VP4.dxf` | 75 KB | DXF (see SOURCE.md for $ACADVER) | none (feature test) | MIT | ACAD_TABLE schedule, multiple layouts/viewports, TrueType text styles |
| L2 | `L2-medium/ezdxf-schedule-layouts/text_fonts.dxf` | 295 KB | DXF (see SOURCE.md for $ACADVER) | none (feature test) | MIT | ACAD_TABLE schedule, multiple layouts/viewports, TrueType text styles |
| L2 | `L2-medium/cadcraft-opencirt/06-function-list-ahu.dwg` | 192 KB | AC1032 | MEP / building automation | CC0-1.0 | title-block attributes, A2 layouts/viewports, table sheets (text scrubbed) |
| L2 | `L2-medium/cadcraft-opencirt/07-cover-sheet-a.dwg` | 53 KB | AC1032 | MEP / building automation | CC0-1.0 | title-block attributes, A2 layouts/viewports, table sheets (text scrubbed) |
| L2 | `L2-medium/cadcraft-opencirt/02-ahu-schema-a.dwg` | 324 KB | AC1032 | MEP / building automation | CC0-1.0 | title-block attributes, A2 layouts/viewports, table sheets (text scrubbed) |
| L2 | `L2-medium/rebar-takeoff-project/test_project_b.dxf` | 26 KB | DXF (see SOURCE.md for $ACADVER) | RC (rebar annotation) | MIT (synthetic) | callout notation variants (Ø/ø/Φ/%%c), mixed language |
| L3 | `L3-complex/structuralbd-complete-sets/Complete_Steel_Building_Drawing_01.dwg` | 1.7 MB | AC1021 | Steel building (per page) | Personal use only, no redistribution | steel framing set, sections (unverified, open first) |
| L3 | `L3-complex/structuralbd-complete-sets/Complete_Steel_Building_Drawing_02.dwg` | 2.0 MB | AC1021 | Steel building (per page) | Personal use only, no redistribution | steel framing set, sections (unverified, open first) |
| L3 | `L3-complex/structuralbd-complete-sets/Steel_Building_Section_01.dwg` | 1.3 MB | AC1021 | Steel building (per page) | Personal use only, no redistribution | steel framing set, sections (unverified, open first) |
| L3 | `L3-complex/dwgshare-rc-projects/267_4-story_house_complete_project.dwg` | 2.4 MB | AC1018 | RC buildings (per page) | No per-file licence; ToS 1.5: no redistribution | grids, levels, column/beam marks, schedules, multi-sheet RC (unverified) |
| L3 | `L3-complex/dwgshare-rc-projects/270_3-story_house_complete_project.dwg` | 2.5 MB | AC1021 | RC buildings (per page) | No per-file licence; ToS 1.5: no redistribution | grids, levels, column/beam marks, schedules, multi-sheet RC (unverified) |
| L3 | `L3-complex/dwgshare-rc-projects/461_residential_building_structural.dwg` | 1.0 MB | AC1021 | RC buildings (per page) | No per-file licence; ToS 1.5: no redistribution | grids, levels, column/beam marks, schedules, multi-sheet RC (unverified) |
| L3 | `L3-complex/dwgshare-rc-projects/433_townhouse_12m_x_20.6m.dwg` | 985 KB | AC1021 | RC buildings (per page) | No per-file licence; ToS 1.5: no redistribution | grids, levels, column/beam marks, schedules, multi-sheet RC (unverified) |
| L3 | `L3-complex/eval3-heldout/285_3-story_house_8.2x15m.dwg` | 1.1 MB | AC1021 | RC buildings (per page) | No per-file licence; ToS 1.5: no redistribution | EVAL-3 held-out (never used for tuning); sheets/fonts unverified |
| L3 | `L3-complex/eval3-heldout/286_7-story_house_9.2x7.6m.dwg` | 4.7 MB | AC1021 | RC buildings (per page) | No per-file licence; ToS 1.5: no redistribution | EVAL-3 held-out (never used for tuning); sheets/fonts unverified |
| L3 | `L3-complex/eval3-heldout/290_4-story_house_9x12.3m.dwg` | 2.5 MB | AC1021 | RC buildings (per page) | No per-file licence; ToS 1.5: no redistribution | EVAL-3 held-out (never used for tuning); sheets/fonts unverified |
| L3 | `L3-complex/eval3-heldout/161_complete_steel_building.dwg` | 1.6 MB | AC1032 | Steel building (per page) | No per-file licence; ToS 1.5: no redistribution | EVAL-3 held-out (never used for tuning); sheets/fonts unverified |
| L3 | `L3-complex/aspose-curtainwall/SLS-CW-CD-CE001-R01_blockClip.dxf` | 5.0 MB | DXF (see SOURCE.md for $ACADVER) | Architectural / curtain wall | MIT repo; underlying drawing rights unclear | nested blocks, 99 layers, SHX styles, only 1 INSERT in modelspace |
| L3 | `L3-complex/libredwg-dynblocks/Dynblocks.dwg` | 2.1 MB | AC1032 | none (feature test) | GPL-3.0 | dynamic blocks (*U instances) |
| L3 | `L3-complex/acadsharp-aec/AecObjects.dwg` | 414 KB | AC1032 | Architectural (AEC objects) | MIT repo; file authorship unstated | AEC proxy objects |
| L3 | `L3-complex/dev-corpus-w5/dwgshare-441-download-free-detailed-cad-drawings-of-beam-reinforcement-fo/441_download-free-detailed-cad-drawings-of-beam-reinforcement-fo.dwg` | 7.2 MB | AC1021 | RC / steel / foundation (per page) | No per-file licence; ToS 1.5: no redistribution | Dev corpus w5 (not held-out): RC multi-storey frame; beam schedules/reinforcement; tall building (22 storeys per title) (unverified) |
| L3 | `L3-complex/dev-corpus-w5/dwgshare-446-typical-floor-levels-2-8-technical-floor-structural-cad-draw/446_typical-floor-levels-2-8-technical-floor-structural-cad-draw.dwg` | 1.2 MB | AC1021 | RC / steel / foundation (per page) | No per-file licence; ToS 1.5: no redistribution | Dev corpus w5 (not held-out): RC multi-storey frame; typical floor + technical floor plans (levels 2-8 per title); possibly multiple sheets (unverified) |
| L3 | `L3-complex/dev-corpus-w5/dwgshare-438-complete-reinforced-concrete-structural-cad-drawings-for-res/438_complete-reinforced-concrete-structural-cad-drawings-for-res.dwg` | 4.5 MB | AC1032 | RC / steel / foundation (per page) | No per-file licence; ToS 1.5: no redistribution | Dev corpus w5 (not held-out): RC multi-storey residential complete set; foundation + frame + schedules (per title) (unverified) |
| L3 | `L3-complex/dev-corpus-w5/dwgshare-459-12-story-apartment-building-design-project-full-architecture/459_12-story-apartment-building-design-project-full-architecture.dwg` | 2.5 MB | AC1032 | RC / steel / foundation (per page) | No per-file licence; ToS 1.5: no redistribution | Dev corpus w5 (not held-out): RC multi-storey (12 storeys); architecture + structure in one file, technical report; multi-sheet (unverified) |
| L3 | `L3-complex/dev-corpus-w5/dwgshare-387-free-download-of-structural-cad-drawings-for-9-2m-x-22-8m-re/387_free-download-of-structural-cad-drawings-for-9-2m-x-22-8m-re.dwg` | 1.4 MB | AC1021 | RC / steel / foundation (per page) | No per-file licence; ToS 1.5: no redistribution | Dev corpus w5 (not held-out): RC townhouse (narrow plot 9.2 x 22.8 m); Vietnamese-style nha pho layout (unverified) (unverified) |
| L3 | `L3-complex/dev-corpus-w5/dwgshare-430-download-of-structural-cad-drawings-for-6-4m-x-13m-reinforce/430_download-of-structural-cad-drawings-for-6-4m-x-13m-reinforce.dwg` | 1.2 MB | AC1032 | RC / steel / foundation (per page) | No per-file licence; ToS 1.5: no redistribution | Dev corpus w5 (not held-out): RC townhouse (6.4 x 13 m, narrow plot); newer DWG version (unverified) |
| L3 | `L3-complex/dev-corpus-w5/dwgshare-435-download-of-structural-cad-drawings-for-15-4m-x-15-7m-reinfo/435_download-of-structural-cad-drawings-for-15-4m-x-15-7m-reinfo.dwg` | 2.0 MB | AC1032 | RC / steel / foundation (per page) | No per-file licence; ToS 1.5: no redistribution | Dev corpus w5 (not held-out): RC townhouse (15.4 x 15.7 m, near-square plan); different aspect ratio from the narrow-plot sets (unverified) |
| L3 | `L3-complex/dev-corpus-w5/dwgshare-460-download-of-structural-cad-drawings-for-8-2m-x-19-3m-reinfor/460_download-of-structural-cad-drawings-for-8-2m-x-19-3m-reinfor.dwg` | 754 KB | AC1027 | RC / steel / foundation (per page) | No per-file licence; ToS 1.5: no redistribution | Dev corpus w5 (not held-out): RC townhouse (8.2 x 19.3 m); AC1027 header (DWG 2013) (unverified) |
| L3 | `L3-complex/dev-corpus-w5/dwgshare-774-5-story-house-design-6m-x-14m-complete-floor-plans-elevation/774_5-story-house-design-6m-x-14m-complete-floor-plans-elevation.dwg` | 1.3 MB | AC1032 | RC / steel / foundation (per page) | No per-file licence; ToS 1.5: no redistribution | Dev corpus w5 (not held-out): RC 5-storey house; floor plans, elevations and foundation in one file (unverified) |
| L3 | `L3-complex/dev-corpus-w5/dwgshare-437-foundation-structural-cad-drawings-footings-grade-beams-colu/437_foundation-structural-cad-drawings-footings-grade-beams-colu.dwg` | 690 KB | AC1032 | RC / steel / foundation (per page) | No per-file licence; ToS 1.5: no redistribution | Dev corpus w5 (not held-out): Foundation plan: footings, grade beams, column details (per title); footing schedules likely (unverified) |
| L3 | `L3-complex/dev-corpus-w5/dwgshare-439-download-complete-pile-foundation-structural-cad-drawings-wi/439_download-complete-pile-foundation-structural-cad-drawings-wi.dwg` | 11.4 MB | AC1032 | RC / steel / foundation (per page) | No per-file licence; ToS 1.5: no redistribution | Dev corpus w5 (not held-out): Pile foundation, complete set with reinforcement details; large (11.9 MB) file (unverified) |
| L3 | `L3-complex/dev-corpus-w5/dwgshare-443-download-free-detailed-cad-drawings-of-raft-foundation-steel/443_download-free-detailed-cad-drawings-of-raft-foundation-steel.dwg` | 1.1 MB | AC1021 | RC / steel / foundation (per page) | No per-file licence; ToS 1.5: no redistribution | Dev corpus w5 (not held-out): Raft foundation plans (title also says steel structure); AC1021 (unverified) |
| L3 | `L3-complex/dev-corpus-w5/dwgshare-451-download-reinforced-concrete-curved-beam-cad-drawings-with-r/451_download-reinforced-concrete-curved-beam-cad-drawings-with-r.dwg` | 2.3 MB | AC1032 | RC / steel / foundation (per page) | No per-file licence; ToS 1.5: no redistribution | Dev corpus w5 (not held-out): RC curved beam with reinforcement details and bar schedules; curved/polyline beam target; schedules (unverified) |
| L3 | `L3-complex/dev-corpus-w5/dwgshare-449-download-reinforced-concrete-beam-reinforcement-cad-drawings/449_download-reinforced-concrete-beam-reinforcement-cad-drawings.dwg` | 4.8 MB | AC1032 | RC / steel / foundation (per page) | No per-file licence; ToS 1.5: no redistribution | Dev corpus w5 (not held-out): RC beam reinforcement with rebar schedules; beam/column schedule target (unverified) |
| L3 | `L3-complex/dev-corpus-w5/dwgshare-51-cad-drawings-of-steel-factory-plan-sections-and-elevation-30/51_cad-drawings-of-steel-factory-plan-sections-and-elevation-30.dwg` | 1.7 MB | AC1032 | RC / steel / foundation (per page) | No per-file licence; ToS 1.5: no redistribution | Dev corpus w5 (not held-out): Steel factory/industrial shed 30 x 96 m: plan, sections, elevation (unverified) |
| L3 | `L3-complex/dev-corpus-w5/dwgshare-362-download-structural-cad-drawing-of-factory-with-dimensions-2/362_download-structural-cad-drawing-of-factory-with-dimensions-2.dwg` | 605 KB | AC1021 | RC / steel / foundation (per page) | No per-file licence; ToS 1.5: no redistribution | Dev corpus w5 (not held-out): Structural drawing of a factory 28 x 36 m (frame type not stated on page); AC1021 (unverified) |
| L3 | `L3-complex/dev-corpus-w5/dwgshare-456-free-steel-structure-shop-drawings-roof-framing-connection-d/456_free-steel-structure-shop-drawings-roof-framing-connection-d.dwg` | 8.5 MB | AC1032 | RC / steel / foundation (per page) | No per-file licence; ToS 1.5: no redistribution | Dev corpus w5 (not held-out): Steel structure shop drawings: roof framing and connection details; large (8.9 MB) file (unverified) |
| L3 | `L3-complex/dev-corpus-w5/dwgshare-599-download-curved-steel-roof-truss-cad-drawings-structural-fra/599_download-curved-steel-roof-truss-cad-drawings-structural-fra.dwg` | 234 KB | AC1032 | RC / steel / foundation (per page) | No per-file licence; ToS 1.5: no redistribution | Dev corpus w5 (not held-out): Curved steel roof truss: structural frame and connection details; curved members (unverified) |

DWG version coverage (header magic): AC1003, AC1009, AC1014, AC1015, AC1018, AC1021, AC1024, AC1027, AC1032. DXF versions: AC1021 (empty), AC1024, AC1027, AC1032 (see probes). AC1012 (R13) was available (libredwg `example_r13.dwg`) but not taken.

## Rejected / not downloadable

| Source | Reason |
|---|---|
| designscad.com (many free-looking steel/RC sets) | Download requires an account (Login / Sign Up); Terms: files may not be redistributed or resold as standalone products; part of the library is subscription-only. Not downloaded. |
| Autodesk "AutoCAD Sample Files" (autodesk.com/autocad-samples) | HTTP 403 for both curl and the fetch tool; not bypassed. Candidate files named on Autodesk pages (e.g. building.dwg, civil_example-imperial.dwg) were not obtained from there. |
| OAS "Building Guidelines Drawings" (oas.org/pgdm/document/codedraw, DWG zip for steel/concrete/masonry details) | Cloudflare JavaScript challenge ("Just a moment..."), not bypassed. Good topical match (steel construction section D) - worth a manual download by a human, licence unchecked. |
| AZDOT structure detail drawings, Harris County standard bridge drawings | HTTP 403. |
| Alberta bridge standard drawings, ARDOT standard bridge drawings | Reachable but PDF only (no DWG/DGN links). Other US DOT libraries found are DGN/PDF (MicroStation), not DWG. |
| nextgis/dwg_samples, owerko/DWG_test_files, tinytales03/SampleDWG, codelibs/fess-testdata, pattern-x/gemini-viewer-examples | No licence file in the repo (GitHub API: none; raw LICENSE 404). Also toy entity files or unknown-origin building DXFs. Not taken. |
| akaiHuang/cad-intelligent-recognizer (`ALL-PLAN-S.dwg` structural plan, `ALL-PLAN.dwg`) | Looks like a real building project of unknown origin; no licence confirmed (repo shows an MIT badge, but the API reports no licence file). Possible client data - skipped on purpose. Worth asking the owner. |
| mlightcad/cad-viewer `sheet_0.dxf` | MIT, but it is a sheet-metal nesting drawing (11k lines/arcs), not structural. Downloaded and discarded. |
| ezdwg `mechanical_example-imperial.dwg`, Aspose `AutoCad_Sample.dwg` etc. | Look like Autodesk sample files inside MIT repos (rights unclear) and are mechanical/generic; not taken. |
| structuralbd/dwgshare timber, stair, floor-plan, plumbing, electrical samples; other 4 complete-steel sets (03, 05, 06 downloaded then dropped for count) | Off-target for steel/RC or redundant with the files kept. |
| dwgshare.com, structuralbd.com | Taken, but see licence warning above. |
| cadbull.com, freecads.com, cadforum.cz | Only seen in search results; subscription/terms unchecked; not fetched. |

## Gaps (could not fill)

- **No confirmed steel framing plan with profile callouts.** The only steel-building candidates (`structuralbd-complete-sets`, dwgshare 744/749) are described by their source pages; whether they contain HEA/UB/W-style callouts is unknown. No European (HEA/IPE/UB) or US (W12x26) callout is confirmed anywhere in the corpus - the only verified callouts are rebar notations in the synthetic DXFs.
- **No licensed, redistributable structural drawing.** All real structural sets are personal-use only. A benchmark that must be shared needs permission or a truly open set (the OAS DWG pack is the best lead).
- **No confirmed xref host/target pair.** No file is known to reference external DWGs; xref behaviour is untested.
- **No verified Vietnamese text or SHX fonts.** Only `aspose-curtainwall` is verified to use SHX styles (ISOCP, romans, simplex) and a CJK-named style; `text_fonts.dxf` is TrueType only. Whether the dwgshare/structuralbd files carry Vietnamese text (TCVN3/VNI fonts or Unicode) is unverified.
- **No verified multi-layout DWG.** Multiple layouts are verified only in DXF (`VP4.dxf`, `acad_table_simple.dxf`). The CC0 cadcraft sheets claim A2 layouts with viewports (README) but their text is scrubbed.
- **No verified dimension-heavy or hatch-heavy structural DWG** - expected in the RC projects, unconfirmed.
- Real text semantics (cadcraft) are hash placeholders; synthetic rebar DXFs are tiny. L1 is therefore weighted to format/version tests.

## Doubtful points

- `ezdxf-minimal/Minimal_DXF_AC1021.dxf` is an empty drawing (0 entities) - only useful as an edge case.
- `SLS-CW-CD-CE001-R01_blockClip.dxf` modelspace has 1 entity; the content is in 224 blocks. Not structural.
- structuralbd descriptions are based on the site's headings; the file names say "Complete Steel Building Drawing" but the real scope (plan vs. details) is unseen.
- File dates: dwgshare ZIP timestamps range from Sep 2024 to Jun 2026; ToS last updated 2026-08-30 - re-check terms before any wider use.
