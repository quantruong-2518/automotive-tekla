# SOURCE - libredwg-versions

- Level: L1 - tiny/clean
- Download date: 2026-11-06
- Source URL: https://github.com/LibreDWG/libredwg (raw: https://raw.githubusercontent.com/LibreDWG/libredwg/master/test/test-data/<dir>/<file>)
- Page URL: https://github.com/LibreDWG/libredwg/tree/master/test/test-data
- Licence / terms: GPL-3.0 (repo-level; the test-data directory carries no separate licence file). Repo COPYING header, verbatim: "GNU GENERAL PUBLIC LICENSE / Version 3, 29 June 2007". Full text: https://www.gnu.org/licenses/gpl-3.0.txt . Treat the samples as GPL-3.0 data; keep them out of any non-GPL redistribution.

## Files

| Local file | Original name | Size (bytes) | Header magic | sha256 |
|---|---|---|---|---|
| r2.6_dim.dwg | r2.6_dim.dwg | 4253 | AC1003 | 5cb89538f3aac12ac9b730968c257d049a85206767241f0279e06908a4893c89 |
| r11_entities-2d.dwg | r11_entities-2d.dwg | 5416 | AC1009 | f9b372579812de9867961f12a842898c27a7dff763a71f41ea10335964b877d4 |
| r14_v.dwg | r14_v.dwg | 26840 | AC1014 | e296ca50f237abb9eec1a8bdab77aa16fd59518e246df812aa4dd4f859bd12d3 |
| 2000_entities-2d.dwg | 2000_entities-2d.dwg | 24028 | AC1015 | 20db22c3e8b42d2630dab3ba4cb0bf5de417926861136d4e479a943798dcc753 |
| 2004_Line.dwg | 2004_Line.dwg | 62118 | AC1018 | 60c86e1d4f038a3f1755d15bd22710c34608900957af61282432e4719b730c24 |
| 2010_Line.dwg | 2010_Line.dwg | 62664 | AC1024 | 315729e57328ea09fc0e3530540294144fb1217922ca28ba076936bf52a9d0ec |
| 2013_Line.dwg | 2013_Line.dwg | 37961 | AC1027 | 351a239cdae05894fe11863aabecfde171bd4d1758a3dd1c9868d8fe534fe6c1 |
| 2018_Line.dwg | 2018_Line.dwg | 27982 | AC1032 | 1f4edd4c11aaf28b3295fd69fa59376f9cb911c637aa47a6073408ecac4797a3 |

Header magic: DWG = first 6 bytes (AC1003 = R2.x/R9-era, AC1009 = R11/R12, AC1012 = R13, AC1014 = R14, AC1015 = 2000, AC1018 = 2004, AC1021 = 2007, AC1024 = 2010, AC1027 = 2013, AC1032 = 2018). DXF text files are recognised by `0\nSECTION` (or a leading `999` comment).

## What it contains

Tiny, single-purpose test drawings, one per DWG release: r2.6_dim (AC1003, a dimension), r11_entities-2d (AC1009, 2D entities), r14_v (AC1014), 2000_entities-2d (AC1015, 2D entities), 2004/2010/2013/2018 `Line` (AC1018/AC1024/AC1027/AC1032, a single LINE). Original path in repo: test/test-data/<r2.6|r11|r14|2000|2004|2010|2013|2018>/<file>; local names are prefixed with the folder name. Contents inferred from file names and size (<= 62 KB each); DWG not opened (per rules).

## Why it is useful

Version-detection and header-parsing matrix (AC1003, AC1009, AC1014, AC1015, AC1018, AC1024, AC1027, AC1032). The `read-log.json` format detection must report the right version and fail loudly (or flag low confidence) on R2.6/R11 and R14, which most readers do not support. Not useful for structural content.

## Handling

Untrusted third-party data. Never executed. Not committed to git (`dwg-lab/samples/**` is git-ignored except `*.md`).
