# SOURCE - cadcraft-opencirt

- Level: L2 - realistic single-discipline
- Download date: 2026-11-06
- Source URL: https://github.com/ohagmann/cadcraft-sample-dwgs (raw: https://raw.githubusercontent.com/ohagmann/cadcraft-sample-dwgs/main/<file>)
- Page URL: https://github.com/ohagmann/cadcraft-sample-dwgs
- Licence / terms: CC0-1.0 (repo LICENSE, 'Creative Commons Legal Code - CC0 1.0 Universal', copied to ./LICENSE). Public-domain dedication: https://creativecommons.org/publicdomain/zero/1.0/ . The repo README states the files are real BricsCAD V26 production sheets (German building-automation planning, openCirt plugin) with project-specific content replaced.

## Files

| Local file | Original name | Size (bytes) | Header magic | sha256 |
|---|---|---|---|---|
| 06-function-list-ahu.dwg | 06-function-list-ahu.dwg | 196553 | AC1032 | 6abb8c9a08c5362e93aea04221cb74e7222bb1ac8c7627cac62c0bd7f359e9e6 |
| 07-cover-sheet-a.dwg | 07-cover-sheet-a.dwg | 54078 | AC1032 | dcfd13da6a95c982348cd7fee172b206bacdade632d77f7c9fa0ee1ff0c99fb2 |
| 02-ahu-schema-a.dwg | 02-ahu-schema-a.dwg | 331783 | AC1032 | 22cfb377dc35360313bfd17a7e935b454f414cb321fd852cb98279779d99ab88 |

Header magic: DWG = first 6 bytes (AC1003 = R2.x/R9-era, AC1009 = R11/R12, AC1012 = R13, AC1014 = R14, AC1015 = 2000, AC1018 = 2004, AC1021 = 2007, AC1024 = 2010, AC1027 = 2013, AC1032 = 2018). DXF text files are recognised by `0\nSECTION` (or a leading `999` comment).

## What it contains

Three of the 15 sheets (all AC1032, written by BricsCAD V26): `06-function-list-ahu` (GA function list, table sheet), `07-cover-sheet-a` (A2 frame, title block, index table, legend), `02-ahu-schema-a` (air-handling-unit schema with control diagrams and data-point columns). Per the README (verified claims about the set, DWG not opened by us): A2 layouts with viewports, title blocks with ~50 attributes (some invisible), nested blocks with attributes, MText with formatting codes, dimensions, page setups. IMPORTANT: all text/attribute/dimension values were replaced by hash placeholders (e.g. `T123456`, `AKS-123456`), so the text is not meaningful.

## Why it is useful

Best realistic source of title-block attributes, A2 sheets with several layouts/viewports, and table sheets; MEP (building automation), not structural. Use for title-block and sheet-frame detection, layout/viewport handling and attribute extraction. Do not use for text semantics. The other 12 sheets in the repo were not taken (size/redundancy); same licence.

## Handling

Untrusted third-party data. Never executed. Not committed to git (`dwg-lab/samples/**` is git-ignored except `*.md`).
