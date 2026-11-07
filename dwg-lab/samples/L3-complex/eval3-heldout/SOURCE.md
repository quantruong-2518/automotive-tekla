# SOURCE - eval3-heldout

- Level: L3 - complex/dense. EVAL-3 held-out set: never used before; do not use for tuning the reader.
- Download date: 2026-11-07
- Source: dwgshare.com, Google Drive direct-download links published on each post (ZIP with one DWG each, listed first - no absolute paths or `..` - then unpacked with `unzip -d` into the folder; no login needed).
- Licence / terms: No per-file licence. Site Terms & Conditions (https://dwgshare.com/terms-conditions/), re-read 2026-11-07. Section 1.5 verbatim: "Downloading a file does not automatically transfer ownership of that file or grant unrestricted rights to reproduce, redistribute, modify, or use it commercially." Section 1.1: "Visitors are not required to register or log in to browse or download publicly available resources." Treat as PERSONAL / INTERNAL RESEARCH USE, NO REDISTRIBUTION. Do not commit or publish these files.

## Files

| Local file | Page URL | Download URL | Size (bytes) | Header magic | sha256 | Why it fits |
|---|---|---|---|---|---|---|
| 285_3-story_house_8.2x15m.dwg | https://dwgshare.com/285-structural-drawings-of-3-story-house-a-complete-project-8-2m-x-15m-for-download/ | https://drive.google.com/uc?export=download&id=12Emvo-Tdy_1E0Uo3T14Fdr8dojobuKBX | 1203392 | AC1021 | 857ddd24c5febbfb58d895a3911391b716a5f5efc54ef8452fc899b921f8d7c1 | RC house "complete project", Vietnamese series (same site series as used 267/270) |
| 286_7-story_house_9.2x7.6m.dwg | https://dwgshare.com/286-structural-drawings-of-7-story-house-a-complete-project-9-2m-x-7-6m-for-download/ | https://drive.google.com/uc?export=download&id=13nA9gHT-nFvQdiOLWkpDzGZn9f_ROrlW | 4906048 | AC1021 | 2ece6b4f66f54ca0324f0d9a1e43bf688673fd487dc45f902d5ec1523407a6b3 | 7-storey RC house, taller than any used set; larger file (many sheets likely) |
| 290_4-story_house_9x12.3m.dwg | https://dwgshare.com/290-structural-drawings-of-4-story-house-a-complete-project-9m-x-12-3m-for-download/ | https://drive.google.com/uc?export=download&id=1OuPIkyb6d4d-e7ALAIVuXm60z6XCdmrh | 2640288 | AC1021 | 7bced0f63d73f620758583d706ecacc1bf9ef59e8dc1b7a85d7ffea3512031ad | 4-storey RC house with a footprint (9 m x 12.3 m) different from used 267 |
| 161_complete_steel_building.dwg | https://dwgshare.com/161-cad-drawings-of-complete-steel-building-for-download/ | https://drive.google.com/uc?export=download&id=1mLgiTJQFQIeJ_0TdzzFGY8z1pY1TywYz | 1626062 | AC1032 | 8a541e0a5ecf29d5f18a56ba508848cb35b52c3d81025c604fda794818abf888 | Steel building set, not from structuralbd, not an already-used dwgshare number |

Original ZIP entry names (before renaming to short names): "285. Structural Drawings Of 3-Story House A Complete Project 8.2m x 15m For Download.dwg", "286. ... 7-Story House ... 9.2m x 7.6m ...", "290. ... 4-Story House ... 9m x 12.3m ...", "161. Cad Drawings Of Complete Steel Building For Download.dwg".

Header magic: DWG = first 6 bytes (AC1021 = 2007, AC1032 = 2018).

## What the source pages say

Only the post titles. The pages have no description of sheets, fonts or language beyond the title ("complete project" for 285/286/290; "complete steel building" for 161). Sheet content (foundation plan, column/beam layout, schedules, notes) is therefore NOT confirmed. Vietnamese origin is inferred from the site series and house types, not verified.

## Fonts (UNVERIFIED)

DWG files were not opened or converted. A passive `strings` scan of the binaries found no `.shx`/`.ttf`/VnTime/VNI font names (expected: AC1021+ stores data compressed, so absence proves nothing). Whether any file uses legacy TCVN3/VNI fonts is unknown until the reader runs on them. The steel set 161 country of origin is unknown.

## Handling

Untrusted third-party data. Never executed, never opened with a CAD tool. Not committed to git (`dwg-lab/samples/**` is git-ignored except `*.md`).

## Font check after conversion (2026-11-07, orchestrator)

Converted with LibreDWG 0.14 (`harness dwg2dxf`) into a session scratchpad, then `harness extract-text`;
only counts were read, no drawing content, to keep the set held out. Non-ASCII entries / encoding used
with the knowledge rows approved on 2026-11-07:

| File | Entries | Non-ASCII | tcvn3 | vni | unicode | unknown/mixed | Note |
|---|---|---|---|---|---|---|---|
| 285 | 4069 | 959 | 7 | 0 | 37 | 915 | 915 unknown entries have no font file name on their style |
| 286 | 11897 | 1137 | 1066 | 0 | 44 | 27 | vntimeh.shx 805, Vharial.ttf 243 |
| 290 | 5959 | 1586 | 9 | 7 | 507 | 1063 | 1583 non-ASCII entries have no font file name on their style |
| 161 | 1124 | 3 | 0 | 0 | 0 | 3 | steel, almost all ASCII |

So the RC sets do carry legacy Vietnamese text: 286 exercises the approved rows, 285 and 290 the
styles without a font file (TTF family name only), which tool-wave-2 fix 2 targets.
