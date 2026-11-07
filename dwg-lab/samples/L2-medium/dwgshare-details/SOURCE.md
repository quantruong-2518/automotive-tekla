# SOURCE - dwgshare-details

- Level: L2 - realistic single-discipline
- Download date: 2026-11-06
- Source URL: Google Drive direct-download links published on each post (each is a ZIP containing one DWG, unpacked with `unzip -d` into its own staging dir after listing the names): 624 https://drive.google.com/uc?export=download&id=1t0Ub6_B_zPjD47S4qOLK6hkHBrepK4q_ ; 744 https://drive.google.com/uc?export=download&id=1teHcKuvhvyMtgrvN0_La-FTenNiO3av3 ; 749 https://drive.google.com/uc?export=download&id=1UBwp-f6t8OPb4POdUHkcGRGgqXWCfsv7 (no login needed).
- Page URL: https://dwgshare.com/624-free-download-standard-column-footing-reinforcement-cad-template/ ; https://dwgshare.com/744-steel-truss-details-cad-drawing-free-dwg-download/ ; https://dwgshare.com/749-structural-steel-connection-details-free-autocad-dwg-drawing/
- Licence / terms: No per-file licence. Site Terms & Conditions (https://dwgshare.com/terms-conditions/, last updated August 30, 2026), section 1.5, verbatim: "Downloading a file does not automatically transfer ownership of that file or grant unrestricted rights to reproduce, redistribute, modify, or use it commercially. Visitors must comply with the applicable license, permissions, and intellectual property rights associated with each resource." Section 1.1 verbatim: "Visitors are not required to register or log in to browse or download publicly available resources." Treat as PERSONAL / INTERNAL RESEARCH USE, NO REDISTRIBUTION. Do not commit or publish these files.

## Files

| Local file | Original name | Size (bytes) | Header magic | sha256 |
|---|---|---|---|---|
| 624_column_footing_reinforcement_template.dwg | 624. Free Download Standard Column & Footing Reinforcement CAD Template.dwg | 115242 | AC1032 | f7f7bd6fbb8aee46b988d467d8ca64cd01f76fec686a8f3a74a14207035e235d |
| 744_steel_truss_details.dwg | 744. Steel Truss Details CAD Drawing – Free DWG Download.dwg | 374727 | AC1032 | 8e23f8cc3d52cfaa97edd9c2ca3f6b1e9426713dfb4c214e1cbc244d8bd16776 |
| 749_structural_steel_connection_details.dwg | 749. Structural Steel Connection Details – Free AutoCAD DWG Drawing.dwg | 248493 | AC1032 | 250a54721ea26a00a6ec6ba4d0d85e9a3d0df2a6371470ce4147e470356dfb00 |

Header magic: DWG = first 6 bytes (AC1003 = R2.x/R9-era, AC1009 = R11/R12, AC1012 = R13, AC1014 = R14, AC1015 = 2000, AC1018 = 2004, AC1021 = 2007, AC1024 = 2010, AC1027 = 2013, AC1032 = 2018). DXF text files are recognised by `0\nSECTION` (or a leading `999` comment).

## What it contains

624 (AC1032): standard column and footing reinforcement template - column/footing connection, column offset and lap splice, column tie tables, notes on splice lengths, bar diameters, stirrup spacing (page text). 744 (AC1032): steel truss details - gusset plates, top/bottom chords, purlin and base connections, bolting patterns, plate thickness annotations (page text). 749 (AC1032): structural steel connection details - section views, dimensions, weld sizes, bolt configuration, 'grid lines and level markers' (page text). Everything above is per source page, not verified (DWG not opened).

## Why it is useful

Table-heavy RC template (tie/splice tables) for schedule reading; steel truss and connection details for plate/weld/bolt callouts and detail-marker reading. Page 749 claims grid lines and level markers - worth checking first for the grid/level extractor.

## Handling

Untrusted third-party data. Never executed. Not committed to git (`dwg-lab/samples/**` is git-ignored except `*.md`).
