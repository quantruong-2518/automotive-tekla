# SOURCE - acadsharp-aec

- Level: L3 - complex/dense
- Download date: 2026-11-06
- Source URL: https://raw.githubusercontent.com/DomCR/ACadSharp/master/samples/aec_objects/AecObjects.dwg
- Page URL: https://github.com/DomCR/ACadSharp/tree/master/samples/aec_objects
- Licence / terms: Repo licence: MIT (copied to ./LICENSE), verbatim:
```text
MIT License

Copyright (c) 2021 Albert Domenech

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

The sample was authored for the library tests; authorship of the file contents is not stated.

## Files

| Local file | Original name | Size (bytes) | Header magic | sha256 |
|---|---|---|---|---|
| AecObjects.dwg | AecObjects.dwg | 423600 | AC1032 | dc196e99b8944d169493c9f3205d45f8a579c0c96e81dbc7fc2f90cd971f7a7e |

Header magic: DWG = first 6 bytes (AC1003 = R2.x/R9-era, AC1009 = R11/R12, AC1012 = R13, AC1014 = R14, AC1015 = 2000, AC1018 = 2004, AC1021 = 2007, AC1024 = 2010, AC1027 = 2013, AC1032 = 2018). DXF text files are recognised by `0\nSECTION` (or a leading `999` comment).

## What it contains

AC1032, 424 KB. Name and folder indicate Autodesk Architecture (AEC) proxy objects (walls, doors, windows, etc. as custom objects); DWG not opened.

## Why it is useful

AEC custom objects appear in architect-supplied backgrounds and xref'd base plans for structural work; a reader must degrade gracefully (proxy graphics only, no parametric data). Tests the 'unknown object' path in read-log.

## Handling

Untrusted third-party data. Never executed. Not committed to git (`dwg-lab/samples/**` is git-ignored except `*.md`).
