# SOURCE - eval4-heldout

- Level: L3 - complex/dense. EVAL-4 held-out set: never used before (disjoint from eval3-heldout and from every set used for tuning); do not use for tuning the reader. Nobody building the tools has seen the drawing content: files were chosen by post title only.
- Download date: 2026-11-09
- Source: dwgshare.com, Google Drive direct-download links published on each post (ZIP listed first with `unzip -l` - no absolute paths or `..` - then unpacked with `unzip -d` into a new empty folder; no login needed). Excluded by rule: posts 161, 267, 270, 285, 286, 290, 369, 412, 433, 461 and anything from structuralbd.
- Licence / terms: No per-file licence. Site Terms & Conditions (https://dwgshare.com/terms-conditions/), re-read 2026-11-09. Section 1.5 verbatim: "Downloading a file does not automatically transfer ownership of that file or grant unrestricted rights to reproduce, redistribute, modify, or use it commercially." Section 1.1: "Visitors are not required to register or log in to browse or download publicly available resources." Treat as PERSONAL / INTERNAL RESEARCH USE, NO REDISTRIBUTION. Do not commit or publish these files.

## Files

| Local file | Page URL | Download URL | Size (bytes) | Header magic | sha256 | Why it fits |
|---|---|---|---|---|---|---|
| 264_6-story_house_6x16.5m.dwg | https://dwgshare.com/264-structural-drawings-of-6-story-house-a-complete-project-6m-x-16-5m-for-download/ | https://drive.google.com/uc?export=download&id=19MfUHvMJ9yQM2FD5nE4MMRT1WE6_HXy6 | 691904 | AC1021 | 293cb68929a5f3d47080de2b11b31410cb989fb3e449fd10dec721b6d110cbe5 | 6-storey RC house, narrow 6 m x 16.5 m footprint; 6 storeys, above the 3-4 storey bulk of the series, and a smaller file than any eval3 RC set |
| 271_3-story_house_14.2x19.7m.dwg | https://dwgshare.com/271-structural-drawings-of-3-story-house-a-complete-project-14-2m-x-19-7m-for-download/ | https://drive.google.com/uc?export=download&id=15rzqOe4Nh-AhLQ9ZDs53xTlL0_69RcvY | 2662144 | AC1021 | e19855b6e6017be496f760a8a2759e818b6f1117edf2d14378ed3de00fa3aa60 | 3-storey RC house with a large footprint (14.2 m x 19.7 m), unlike the narrow townhouse footprints |
| 278_5-story_house_4.4x15.3m.dwg | https://dwgshare.com/278-structural-drawings-of-5-story-house-a-complete-project-4-4m-x-15-3m-for-download/ | https://drive.google.com/uc?export=download&id=1jqJDngGZhMAL2r-oAW1MJcVqHDCbvO7j | 1194496 | AC1021 | f9d2bf8945854c8a577a5ac1124bb64ea27ab0555ba3ded6c84358597c34d848 | 5-storey RC house on a very narrow plot (4.4 m x 15.3 m) |
| 180_steel_building.dwg | https://dwgshare.com/180-cad-drawing-of-steel-building-free-download/ | https://drive.google.com/uc?export=download&id=1xaXcIuXMHySZ8EX2nmHuFoXKgJPWj1LO | 12179168 | AC1021 | 15dc2000f26092749f248b594473e4f01657e0868cdba1fa3b415659ad838f57 | Steel building set (post "CAD drawing Of Steel Building"), not from structuralbd, not the already-used 161; largest file of the series so far |

Original ZIP entry names (before renaming to short names): "264. Structural Drawings Of 6-Story House A Complete Project 6m x 16.5m For Download.dwg", "271. Structural Drawings Of 3-Story House A Complete Project 14.2m x 19.7m For Download.dwg", "278. Structural Drawings Of 5-Story House A Complete Project 4.4m x 15.3m For Download.dwg", "180. CAD drawing Of Steel Building Free download.dwg".

Note on 264: its ZIP held two DWGs. Kept the one whose name matches the post title (691904 bytes). The other, "... For Download (2).dwg" (852352 bytes, AC1021, sha256 107d7cfebe4ac0ea54c3784e1f7101e672caa42d5a7e4278a22b39dae0070186), was not copied; it is not in this folder.

Header magic: DWG = first 6 bytes (AC1021 = 2007).

## What the source pages say

Only the post titles. The pages have no description of sheets, fonts or language beyond the title ("complete project" for 264/271/278; "CAD drawing Of Steel Building" for 180). Sheet content (foundation plan, column/beam layout, schedules, notes) is therefore NOT confirmed. Vietnamese origin of the RC houses is inferred from the site series and house types, not verified. The steel set 180 country of origin is unknown (its STYLE table lists ghs.shx and whgtxt.shx, which suggests Chinese-language text, unverified).

## Fonts (aggregate, STYLE table only)

Converted with LibreDWG `dwg2dxf` into the session scratchpad; only the STYLE table font file names were counted (no text, no sheet content), then the DXFs were deleted.

| File | Styles | With a font file | With a big font | Font files named |
|---|---|---|---|---|
| 264 | 13 | 8 | 1 | arial.ttf, arialbd.ttf, romans.shx, sas_____.pfb, times.ttf, vn1.shx, vntimeh.shx |
| 271 | 28 | 28 | 4 | arial_3.ttf, romans.shx, simsun.ttf, txt.shx, vharialb_2.ttf, vhavan_2.ttf, vhavanb_2.ttf, vhhels_2.ttf, vn1.shx, vnih____.shx, vns.shx, vnsimli.shx, vntimeh.shx |
| 278 | 10 | 7 | 0 | arial.ttf, chhbg.shx, romans.shx, uv-abc.shx, vntimeh.shx |
| 180 | 22 | 22 | 2 | arial.ttf, arialn.ttf, ghs.shx, gothic.ttf, rom_____.pfb, romanc.shx, romans.shx, romant.shx, sanss___.ttf, swissc.ttf, swissel.ttf, tahoma.ttf, times.ttf, whgtxt.shx |

So the three RC sets reference legacy Vietnamese fonts (vntimeh.shx, vn1.shx, vns.shx, VH* TTFs; 271 also vnih____.shx, vnsimli.shx). Styles without a font file (264: 5 of 13, 278: 3 of 10) are the case tool-wave-2 fix 2 targets. Which fonts the text actually uses is unknown until the reader runs.

## Handling

Untrusted third-party data. Never executed, never opened with a CAD tool, DWG content never read; only `head -c 6`, `sha256sum`, size and the STYLE-table font count above. Not committed to git (`dwg-lab/samples/**` is git-ignored except `*.md`).
