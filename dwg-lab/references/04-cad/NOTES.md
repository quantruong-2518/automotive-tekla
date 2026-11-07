# 04 CAD-specific: layer naming, text and dimension conventions, model space vs paper space, xrefs

Accessed 2026-11-06. Grades: A = standards body / official publisher primary text; B = university, agency,
vendor documentation, library docs; C = blog or supplier. "Verified" = I opened the page/file and the claim is on it.

## Sources

| # | Source | Grade | Region | Verified | Supports |
|---|---|---|---|---|---|
| 1 | [National CAD Standard (NIBS)](https://www.nationalcadstandard.org/) | A | US | Y: paid license, V7 mentioned; layer tables not readable | NCS contains the AIA CAD Layer Guidelines; paid. Link only. |
| 2 | [AIA & NCS layer format decoded (draftsperson.net blog, updated Aug 2026)](https://blog.draftsperson.net/the-aia-cad-layer-format) | C | US | Y (page read) | Field structure: discipline (2 chars, e.g. `S-`), major group (4), minor group (4, optional), second minor (4, NCS long format only), status (1, last). Discipline = **author** of the information, not the trade (a column drawn by the architect is `A-COLS`, not `S-COLS`). Major groups seen: BEAM, COLS, FNDN, GRID, SLAB, ANNO, DIMS, TEXT, NOTE, SYMB, TTBL, XREF... Status letters N, E, D, F, T, M, R, X. Page itself says the standard is paid; I did not cross-check with NCS text. |
| 3 | [BS EN ISO 13567-2:2017 listing (NSAI shop)](https://shop.standards.ie/en-ie/standards/bs-en-iso-13567-2-2017-224368_saig_bsi_bsi_3108113) | A (metadata) | EU/UK | Y (status "Current", title "Technical product documentation. Organization and naming of layers for CAD: concepts, format and codes used in construction documentation"; paid) | Current layer-naming standard family (ISO 13567-1 concepts, -2 format and codes). Layer name fields per a Wikipedia-mirror summary seen in search: agent (2 chars), element (6), presentation (2), optional work-package and user fields: **unverified** (source not opened). |
| 4 | [BS 1192-5:1998 listing (NSAI shop)](https://shop.standards.ie/en-ie/standards/bs-1192-5-1998-298042_saig_bsi_bsi_690849) | A (metadata) | UK | Y (status "Superseded"; table of contents has "10 Layers and layer naming", "Annex B layer name fields") | The old UK layer standard is superseded. Which document replaced it is **not stated on the page**; the UK national foreword of BS EN ISO 13567-2:2017 links it to the ISO 13567 family and BS EN ISO 19650 (seen in a search snippet, not opened). ISO 19650 itself is about information management, not a layer list. |
| 5 | [Autodesk help: Model Space and Layouts](https://help.autodesk.com/cloudhelp/2020/ENU/AutoCAD-LT-MAC/files/GUID-A0B16C83-C61F-41BD-A295-14026CA142EC.htm) | B | global | Y | Two working environments: model space (create the 2D drawing) and paper-space layouts (plotting: scaling views, locating views, controlling plot area/settings). Plotting from model space is possible. |
| 6 | [ezdxf documentation: Dimension entity](https://ezdxf.readthedocs.io/en/stable/dxfentities/dimension.html) | B | global | Y (version 1.4.5 page) | `dxf.text` = text explicitly entered by the user: empty string or `<>` means the measurement is drawn as the text, a single blank suppresses the text, anything else is displayed as the dimension text (an override). `dxf.actual_measurement` is an optional, read-only attribute that is "often not present". So displayed text can differ from geometry, and the measurement must be recomputed from the definition points: this is the basis for the harness's proposed check "overridden dimension text vs measured value". |
| 7 | [Autodesk OARX developer guide: layouts/viewports](https://help.autodesk.com/cloudhelp/2021/ENU/OARX-DevGuide/files/GUID-76CBF548-700A-4531-AB40-EDCBFB830D13.htm) | B | global | N: content seen in search summary only | Layout viewports show scaled model-space views. |
| 8 | [All3DP: xref in AutoCAD](https://all3dp.com/2/xref-autocad-tutorial/) | C | global | N: search summary only | Attachment vs overlay xrefs. |
| 9 | [FloorPlanCAD / SymPoint papers](../06-research/NOTES.md) | B | global | Y | Real CAD drawings are vector; symbol layers/blocks matter for recognition. |
| 10 | Harness documents `docs/workflow.md` (proposed DXF checks) and `schemas/read-log.schema.json` | internal | - | Y | Local checks to align: multiple scales in model space, missing xrefs, `$INSUNITS`, legacy Vietnamese encodings. |

Not found: a free authoritative page for the **Vietnamese** layer-naming convention. TCVN 5570:2012 ("ky hieu duong truc va duong net", per a search snippet) is about axis symbols and line types on drawings, not CAD layer names; no TCVN layer standard was found. "UNI": the brief is ambiguous. If it means Italian UNI standards, the relevant family is UNI 11337 (BIM information management; I did not verify that it prescribes CAD layers). If it means Uniclass (UK classification, used as the element field in ISO 13567), I also did not open it. Treat both as **unverified**.

## Layer naming: how to use it
- Layer names are *hints*, never proof: offices rename layers, and in Vietnam many files use free names (`COT`, `DAM`, `LUOI TRUC`, `kich thuoc`, legacy font-encoded). Use layer names to propose a classification, confirm with geometry (closed polylines, block names, text content), and record confidence "medium" when the layer name is the only evidence.
- If layer names follow AIA/NCS (`S-BEAM`, `S-COLS`, `S-GRID`, `S-FNDN`, `S-SLAB`, `S-ANNO-DIMS`, `S-ANNO-TEXT`): the first field says who authored the data; check for architect-authored layers that duplicate structural members (`A-COLS`).
- If layer names follow ISO 13567 style (agent + element + presentation fields): the element field is a classification code (e.g. Uniclass or CI/SfB): needs the project's own code table.
- Xref layers appear as `xrefname|layername` in DWG/DXF; the prefix tells which attached file owns the layer.
- Frozen/off layers: check for hidden revisions or superseded content; an off layer may be the old design.

## Text and dimension conventions (what can go wrong)
- Dimension *text* may be overridden by a typed string; the geometric *measurement* may differ (ezdxf `text` vs `actual_measurement`). Always compare, report mismatch (could be a drafting error or a deliberate "n.t.s." note).
- Dimension scale (`DIMSCALE`) and paper-space scaling: the displayed value in a dimension depends on the dimension style (units, scale factor, rounding). Dimensions in a viewport at 1:50 may be drawn at 1:1 in model space or at 1:50-scaled geometry: sheet "scale" in the title block is not proof of model-space geometry scale.
- Text height depends on annotative scale or on drawing scale; use it only to understand which view a note belongs to.
- Text encoding: legacy Vietnamese fonts (TCVN3/VNI) can produce garbage characters when read as Unicode; harness read-log has an `encoding` field. SHX fonts missing -> render and read with vision at lower confidence (harness fallback).
- Units: `$INSUNITS` in the DXF header may be 0 (unitless) or wrong. Cross-check with dimension values (e.g. a 6000 mm span drawn as 6000 or as 6).
- Multi-line text and tables: schedules may be built from MTEXT, from TABLE entities, or from lines + single-line text; handle all three (the DrawingVQA paper lists tabular schedules as a major element).

## Why model space vs paper space and xrefs matter
- Model space holds the geometry at real size (or, in poorly made files, at several different scales side by side). Paper-space layouts hold the sheets: title blocks, viewports (each with its own scale and layer visibility). Title-block data (sheet number, revision, scale) is therefore often in **paper space** while members and dimensions are in **model space**. Reading only model space misses the sheet identity; reading only paper space misses geometry (Autodesk help, source 5).
- The same model space can feed several sheets via viewports with different visible layers: a viewport freeze state can hide the layer you are looking for; per-viewport layer overrides are saved in the DWG.
- Xrefs: grids, levels, architectural backgrounds are often external files. If an xref is missing, the harness will see no grid -> report as missing xref (do not infer). Xrefs can be nested; paths may be absolute from the author's machine.
- DXF export from DWG may bind or drop xrefs; the harness conversion chain (ODA File Converter -> DXF) should log it in `read-log.json`.

## One-page checklist (CAD)
1. Record DXF/DWG version, `$INSUNITS`, encoding detected, fonts missing.
2. List layers: names, on/off/frozen, colour; classify naming style (AIA/NCS, ISO 13567, custom, Vietnamese free text).
3. List xrefs and whether they resolve; list blocks (names, counts) and attributes (block attributes often hold marks and sizes).
4. List layouts (paper space) and viewports: scale, target model-space window, frozen layers; read title block from the layout.
5. Dimension audit: text override vs measurement; dimension style scales; non-associative text posing as dimension.
6. Text audit: encoding artefacts, `%%c`/`%%d` codes (diameter / degree symbols), stacked fractions, MTEXT formatting codes.
7. Anything unreadable -> render region, read with vision, mark confidence low, raise a question.

## Regional differences
- US: NCS/AIA layer names common in architectural-led projects; imperial units common.
- UK/EU: ISO 13567 + ISO 19650 naming for BIM-era projects; many UK offices still use BS 1192-style names from habit.
- Vietnam: no widely applied national layer standard was found; free names, Vietnamese words, legacy encodings; company-specific templates.
- China/Japan origin files: layer names in Chinese or Japanese, GBK/Shift-JIS encodings (general knowledge, not verified).

## Where sources disagree
- Which document superseded BS 1192-5: not stated on the NSAI listing; the ISO 13567/19650 link is only a hint.
- AIA/NCS: older AIA guidelines define one minor group + status; NCS long format adds a second minor group (the blog states this itself). Do not assume the 4th field is status.

## Gaps / unverified
- NCS layer tables, ISO 13567-1/-2 text, UNI documents not read (paid or not found).
- Autodesk pages on xref/viewport layer overrides and DIMSCALE were not opened in this session.
- No Vietnamese CAD layer standard found.
