# SOURCE - ezdxf-schedule-layouts

- Level: L2 - realistic single-discipline
- Download date: 2026-11-06
- Source URL: https://github.com/mozman/ezdxf (raw: https://raw.githubusercontent.com/mozman/ezdxf/master/examples_dxf/<file>)
- Page URL: https://github.com/mozman/ezdxf/tree/master/examples_dxf
- Licence / terms: MIT (repo LICENSE, copied to ./LICENSE). Verbatim:
```text
MIT License

Copyright (c) 2020 Manfred Moitzi

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


## Files

| Local file | Original name | Size (bytes) | Header magic | sha256 |
|---|---|---|---|---|
| acad_table_simple.dxf | acad_table_simple.dxf | 92040 | text:0\nSECTION\n   | 2fc8d0e9517b36dd13db95740b37bc2f534005f16abc222faab036c3407d9e8d |
| VP4.dxf | VP4.dxf | 76778 | text:0\nSECTION\n   | aa535057afadab4ed0fc8cadb4b624d272c90603c7e03f44df1e6a6d1a15acc0 |
| text_fonts.dxf | text_fonts.dxf | 301744 | text:0\nSECTION\n   | c69dbb759042ebdb3e23047e61f4053cfcd48d210ca846490d3c3ffc64d56ea1 |

Header magic: DWG = first 6 bytes (AC1003 = R2.x/R9-era, AC1009 = R11/R12, AC1012 = R13, AC1014 = R14, AC1015 = 2000, AC1018 = 2004, AC1021 = 2007, AC1024 = 2010, AC1027 = 2013, AC1032 = 2018). DXF text files are recognised by `0\nSECTION` (or a leading `999` comment).

## What it contains

Three DXF files, verified with ezdxf (probe table below): `acad_table_simple.dxf` (a single ACAD_TABLE entity, two paper layouts), `VP4.dxf` (two paper-space layouts with viewports, TEXT and LWPOLYLINE), `text_fonts.dxf` (384 TEXT entities, 8 text styles, all TrueType: ARIAL, ARIAL_NARROW, BOUTON, Baby Kruffy, Brussels, ...).

### ezdxf probe of the DXF files (verified)

| File | $ACADVER | Layers | Entities in modelspace | Layouts | Non-anon blocks | Text styles (first) |
|---|---|---|---|---|---|---|
| acad_table_simple.dxf | AC1027 | 2 (0, Defpoints) | ACAD_TABLE:1 (total 1) | Layout1, Layout2, Model | 0 | Standard:arial.ttf |
| VP4.dxf | AC1027 | 2 (0, Defpoints) | TEXT:4, LWPOLYLINE:2 (total 6) | Layout1, Layout2, Model | 1 | Standard:arial.ttf; DYN_DIM:arial.ttf |
| text_fonts.dxf | AC1027 | 4 (0, Defpoints, INSERT_POINTS, BOUNDARIES) | CIRCLE:704, TEXT:384, LINE:256 (total 1344) | Layout1, Model | 0 | Standard:txt; ARIAL:arial.ttf; ARIAL_NARROW:ARIALN.TTF; BOUTON:BOUTON_International_symbols.ttf; Baby Kruffy:babyk___.ttf |

## Why it is useful

ACAD_TABLE (the native schedule entity, whose cell data is stored as a proxy/ACIS-like structure and is often unreadable by naive parsers), multiple layouts/viewports (paper space vs model space), and text-style/font handling. Fonts are TrueType only; no SHX or Vietnamese-specific font (gap).

## Handling

Untrusted third-party data. Never executed. Not committed to git (`dwg-lab/samples/**` is git-ignored except `*.md`).
