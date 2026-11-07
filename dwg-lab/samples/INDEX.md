# dwg-lab sample corpus - INDEX

Built 2026-11-06. 38 sample files in 13 source directories (L1: 12, L2: 16, L3: 10), 23.0 MB total. Each directory has a `SOURCE.md` (URL, licence, sha256, header magic, contents, why useful). Total is slightly above the ~30-file target because the version matrix (L1) was kept as separate files.

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
| L3 | `L3-complex/aspose-curtainwall/SLS-CW-CD-CE001-R01_blockClip.dxf` | 5.0 MB | DXF (see SOURCE.md for $ACADVER) | Architectural / curtain wall | MIT repo; underlying drawing rights unclear | nested blocks, 99 layers, SHX styles, only 1 INSERT in modelspace |
| L3 | `L3-complex/libredwg-dynblocks/Dynblocks.dwg` | 2.1 MB | AC1032 | none (feature test) | GPL-3.0 | dynamic blocks (*U instances) |
| L3 | `L3-complex/acadsharp-aec/AecObjects.dwg` | 414 KB | AC1032 | Architectural (AEC objects) | MIT repo; file authorship unstated | AEC proxy objects |

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
