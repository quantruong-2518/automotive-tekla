# SOURCE - libredwg-dynblocks

- Level: L3 - complex/dense
- Download date: 2026-11-06
- Source URL: https://raw.githubusercontent.com/LibreDWG/libredwg/master/test/test-data/2018/Dynblocks.dwg
- Page URL: https://github.com/LibreDWG/libredwg/tree/master/test/test-data/2018
- Licence / terms: GPL-3.0 (repo-level). Repo COPYING header, verbatim: "GNU GENERAL PUBLIC LICENSE / Version 3, 29 June 2007". Full text: https://www.gnu.org/licenses/gpl-3.0.txt .

## Files

| Local file | Original name | Size (bytes) | Header magic | sha256 |
|---|---|---|---|---|
| Dynblocks.dwg | Dynblocks.dwg | 2179277 | AC1032 | 95cc558d02a2596d13ce2a8da30e22c734a5fba7e0ba990fcf203955674c7f88 |

Header magic: DWG = first 6 bytes (AC1003 = R2.x/R9-era, AC1009 = R11/R12, AC1012 = R13, AC1014 = R14, AC1015 = 2000, AC1018 = 2004, AC1021 = 2007, AC1024 = 2010, AC1027 = 2013, AC1032 = 2018). DXF text files are recognised by `0\nSECTION` (or a leading `999` comment).

## What it contains

AC1032, 2.2 MB drawing that exercises dynamic blocks (the matching DXF in the repo is 10 MB, not taken). Contents inferred from the file name and the libredwg test purpose; DWG not opened.

## Why it is useful

Dynamic blocks (anonymous `*U` block instances with parameter/action data) are common in real structural/architectural drawings for symbols, level markers and section marks; readers that only follow the named block definition get the wrong geometry.

## Handling

Untrusted third-party data. Never executed. Not committed to git (`dwg-lab/samples/**` is git-ignored except `*.md`).
