# SOURCE - ezdxf-minimal

- Level: L1 - tiny/clean
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
| Minimal_DXF_AC1021.dxf | Minimal_DXF_AC1021.dxf | 3041 | text:999\ndxfrw 0. | 6866a50766e178f19356607ee3d3fe619f9f46cfcd2d7d5969f1077eb675464d |
| multi_insert_with_attribs.dxf | multi_insert_with_attribs.dxf | 17346 | text:0\nSECTION\n   | 14951dbef1c750fefc0a452e0bd4fb5b281dc092820d5b6da31b3855dddb4411 |

Header magic: DWG = first 6 bytes (AC1003 = R2.x/R9-era, AC1009 = R11/R12, AC1012 = R13, AC1014 = R14, AC1015 = 2000, AC1018 = 2004, AC1021 = 2007, AC1024 = 2010, AC1027 = 2013, AC1032 = 2018). DXF text files are recognised by `0\nSECTION` (or a leading `999` comment).

## What it contains

Two DXF files. `Minimal_DXF_AC1021.dxf`: valid empty R2007 DXF (no entities). `multi_insert_with_attribs.dxf`: one INSERT of a block carrying attributes, layer FLAGS. Verified with ezdxf (see probe table below).

### ezdxf probe of the DXF files (verified)

| File | $ACADVER | Layers | Entities in modelspace | Layouts | Non-anon blocks | Text styles (first) |
|---|---|---|---|---|---|---|
| Minimal_DXF_AC1021.dxf | AC1021 | 2 (0, Defpoints) | none (total 0) | Model, Layout1 | 0 | Standard:txt |
| multi_insert_with_attribs.dxf | AC1027 | 3 (0, Defpoints, FLAGS) | INSERT:1 (total 1) | Model, Layout1 | 1 | Standard:txt |

## Why it is useful

Smallest possible valid DXF (empty-drawing edge case) and the attribute-on-block-insert pattern used by title blocks, column marks and level tags.

## Handling

Untrusted third-party data. Never executed. Not committed to git (`dwg-lab/samples/**` is git-ignored except `*.md`).
