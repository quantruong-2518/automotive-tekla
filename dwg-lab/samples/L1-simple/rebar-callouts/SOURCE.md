# SOURCE - rebar-callouts

- Level: L1 - tiny/clean
- Download date: 2026-11-06
- Source URL: https://github.com/tolga-ileri/Rebar-Takeoff (raw: https://raw.githubusercontent.com/tolga-ileri/Rebar-Takeoff/main/tests/<file>)
- Page URL: https://github.com/tolga-ileri/Rebar-Takeoff/tree/main/tests
- Licence / terms: MIT (repo LICENSE, copied to ./LICENSE). Verbatim:
```text
MIT License

Copyright (c) 2026 Tolga İleri

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Note: the repo README describes its sample as synthetic (`sample_structure.dxf`, 'illustrative'); the `tests/*.dxf` files are test fixtures, not real project drawings.

## Files

| Local file | Original name | Size (bytes) | Header magic | sha256 |
|---|---|---|---|---|
| test.dxf | test.dxf | 20302 | text:0\nSECTION\n   | 8bdb16870d3f945563dde36956f04b3065fbba3efeea3455e7c9abea1c773519 |
| test_blocks.dxf | test_blocks.dxf | 18542 | text:0\nSECTION\n   | b2f1e102d12fdd163a5e4be589aa18ffc4ca6791cf6f3ea04456ec91478c3bdd |

Header magic: DWG = first 6 bytes (AC1003 = R2.x/R9-era, AC1009 = R11/R12, AC1012 = R13, AC1014 = R14, AC1015 = 2000, AC1018 = 2004, AC1021 = 2007, AC1024 = 2010, AC1027 = 2013, AC1032 = 2018). DXF text files are recognised by `0\nSECTION` (or a leading `999` comment).

## What it contains

Synthetic test fixtures of reinforcement annotations (Turkish workflow): TEXT/MTEXT callouts such as `16[16/20`, `L=400` on layers DEMYAZXUST/DEMYAZYUST/... (Turkish 'slab reinforcement text' layer names), a DONATI layer, plus block inserts. Verified with ezdxf.

### ezdxf probe of the DXF files (verified)

| File | $ACADVER | Layers | Entities in modelspace | Layouts | Non-anon blocks | Text styles (first) |
|---|---|---|---|---|---|---|
| test.dxf | AC1032 | 11 (0, Defpoints, DEMYAZXUST, DEMYAZXALT, DEMYAZYUST, DEMYAZYALT, DEM YAZ UST ILAVE X, DEM YAZ UST ILAVE Y...) | TEXT:24, INSERT:1, MTEXT:1 (total 26) | Model, Layout1 | 1 | Standard:txt |
| test_blocks.dxf | AC1024 | 3 (0, Defpoints, DONATI) | INSERT:3, TEXT:2 (total 5) | Model, Layout1 | 4 | Standard:txt |

## Why it is useful

Rebar callout grammar (count + bar diameter / spacing, length `L=`), non-ASCII diameter symbols and `%%c` escapes, annotation placed on dedicated layers. Good unit test for a bar-schedule parser. Not a realistic sheet.

## Handling

Untrusted third-party data. Never executed. Not committed to git (`dwg-lab/samples/**` is git-ignored except `*.md`).
