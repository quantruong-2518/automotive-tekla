# SOURCE - rebar-takeoff-project

- Level: L2 - realistic single-discipline
- Download date: 2026-11-06
- Source URL: https://raw.githubusercontent.com/tolga-ileri/Rebar-Takeoff/main/tests/test_project_b.dxf
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

Synthetic fixture (see rebar-callouts).

## Files

| Local file | Original name | Size (bytes) | Header magic | sha256 |
|---|---|---|---|---|
| test_project_b.dxf | test_project_b.dxf | 26152 | text:0\nSECTION\n   | 4b30b0649f7616a607f6a67151b5437c5fc2a81db36af096377ec241c281ae4a |

Header magic: DWG = first 6 bytes (AC1003 = R2.x/R9-era, AC1009 = R11/R12, AC1012 = R13, AC1014 = R14, AC1015 = 2000, AC1018 = 2004, AC1021 = 2007, AC1024 = 2010, AC1027 = 2013, AC1032 = 2018). DXF text files are recognised by `0\nSECTION` (or a leading `999` comment).

## What it contains

79 TEXT entities and one block across 7 layers (S-01-A, X_9924, KAT-PLAN-3, TXT-NOTES, COTES): rebar callouts in several notations (`24Ø16/20`, `18ø12/15`, `12Φ10/25`, `30%%c14/20`), length notes (`L:500`, `L 320`, `BOY=260`) and a concrete class note `BETON C30/37`. Verified with ezdxf.

### ezdxf probe of the DXF files (verified)

| File | $ACADVER | Layers | Entities in modelspace | Layouts | Non-anon blocks | Text styles (first) |
|---|---|---|---|---|---|---|
| test_project_b.dxf | AC1032 | 7 (0, Defpoints, S-01-A, X_9924, KAT-PLAN-3, TXT-NOTES, COTES) | TEXT:79, INSERT:1 (total 80) | Model, Layout1 | 1 | Standard:txt |

## Why it is useful

Same intent expressed in different notations and layer-naming conventions (diameter symbol Ø / ø / Φ / %%c, `L:` vs `L ` vs `BOY=`) - a good normalisation test and a layer-name-is-not-reliable test. Mixed language (Turkish) annotations.

## Handling

Untrusted third-party data. Never executed. Not committed to git (`dwg-lab/samples/**` is git-ignored except `*.md`).
