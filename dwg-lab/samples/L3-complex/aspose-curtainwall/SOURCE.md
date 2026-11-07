# SOURCE - aspose-curtainwall

- Level: L3 - complex/dense
- Download date: 2026-11-06
- Source URL: https://github.com/aspose-cad/Aspose.CAD-for-.NET/blob/master/Examples/Data/DXF-Drawings/SLS-CW-CD-CE001-R01_blockClip.dxf (raw: https://raw.githubusercontent.com/aspose-cad/Aspose.CAD-for-.NET/master/Examples/Data/DXF-Drawings/SLS-CW-CD-CE001-R01_blockClip.dxf)
- Page URL: https://github.com/aspose-cad/Aspose.CAD-for-.NET/tree/master/Examples/Data/DXF-Drawings
- Licence / terms: Repo licence: MIT (copied to ./LICENSE), verbatim:
```text
The MIT License (MIT)

Copyright (c) 2001-2025 Aspose Pty Ltd

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

CAVEAT: the MIT grant covers the repo; the drawing itself looks like a third-party curtain-wall shop drawing (text style names such as `YKKAP_STANDARD`, `TC_T1_ Partial Elevation`). Underlying copyright of the drawing content is unclear. Treat as research-only; do not redistribute.

## Files

| Local file | Original name | Size (bytes) | Header magic | sha256 |
|---|---|---|---|---|
| SLS-CW-CD-CE001-R01_blockClip.dxf | SLS-CW-CD-CE001-R01_blockClip.dxf | 5204449 | text:0\nSECTION\n   | b5a79eca0f432a7e7c52b97e958f436f556e35c7579937871070d32537e241f2 |

Header magic: DWG = first 6 bytes (AC1003 = R2.x/R9-era, AC1009 = R11/R12, AC1012 = R13, AC1014 = R14, AC1015 = 2000, AC1018 = 2004, AC1021 = 2007, AC1024 = 2010, AC1027 = 2013, AC1032 = 2018). DXF text files are recognised by `0\nSECTION` (or a leading `999` comment).

## What it contains

Verified with ezdxf (probe table below): R2010 DXF, 99 layers (LEVEL, GLASS, WALL, DIM, DIM1, EXTLINE1/2, SYMBOLS1/2, PARTS1-3, SOLID6/7, HAT, NOTPRINT ...), 224 non-anonymous blocks, text styles using SHX (ISOCP, romans, simplex) and TrueType fonts, a CJK-named style. Model space holds a single INSERT; all geometry lives in nested blocks.

### ezdxf probe of the DXF files (verified)

| File | $ACADVER | Layers | Entities in modelspace | Layouts | Non-anon blocks | Text styles (first) |
|---|---|---|---|---|---|---|
| SLS-CW-CD-CE001-R01_blockClip.dxf | AC1024 | 99 (0, LEVEL, SYMBOLS2, GLASS, SHAPE, MAT, CENTER2, PARTS2...) | INSERT:1 (total 1) | Layout1, Model | 224 | STANDARD:ISOCP.SHX; ROMANS:romans.shx; arial:arial.ttf; Stmm:simplex.shx; HZTEXT:romans.shx |

## Why it is useful

Stress test for nested blocks (everything is inside block definitions, so a reader that only walks modelspace entities sees one INSERT), many layers, SHX fonts, dimension and level layers. Architectural/façade, not structural.

## Handling

Untrusted third-party data. Never executed. Not committed to git (`dwg-lab/samples/**` is git-ignored except `*.md`).
