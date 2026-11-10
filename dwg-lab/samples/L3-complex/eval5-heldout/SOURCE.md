# SOURCE - eval5-heldout

- Level: L3 - complex/dense. EVAL-5 held-out set: never used before (disjoint from eval3-heldout, eval4-heldout and every set used for tuning); do not use for tuning the reader. Nobody building the tools has seen the drawing content: files were chosen by post title only.
- Download date: 2026-11-10
- Source: dwgshare.com, Google Drive direct-download links published on each post (ZIP listed first with `unzip -l` - no absolute paths or `..` - then unpacked with `unzip -d` into a new empty folder; no login needed). Excluded by rule: posts 161, 180, 264, 267, 270, 271, 278, 285, 286, 290, 369, 412, 433, 461 and anything from structuralbd. No sha256 matches any other DWG under `dwg-lab/samples/` (checked).
- Licence / terms: No per-file licence. Site Terms & Conditions (https://dwgshare.com/terms-conditions/), as quoted in `../eval4-heldout/SOURCE.md` (re-read 2026-11-09, not re-read today). Section 1.5 verbatim: "Downloading a file does not automatically transfer ownership of that file or grant unrestricted rights to reproduce, redistribute, modify, or use it commercially." Treat as PERSONAL / INTERNAL RESEARCH USE, NO REDISTRIBUTION. Do not commit or publish these files.

## Files

| Local file | Page URL | Download URL | Size (bytes) | Header magic | sha256 | Why it fits |
|---|---|---|---|---|---|---|
| 297_3-story_house_8x18m.dwg | https://dwgshare.com/297-structural-drawings-of-3-story-house-a-complete-project-8m-x-18m-for-download/ | https://drive.google.com/uc?export=download&id=1SjhvVEzBXzTrnXkPBK5nWlCUEHDpouv6 | 2009088 | AC1021 | 652758381b1c7ca691fb3997972760cacf03d710450b6f149192cf281769dd7b | 3-storey RC house, wide footprint (8 m x 18 m) - between the narrow townhouse plots and the 14.2 m x 19.7 m eval4 set |
| 281_5-story_house_4.4x19.8m.dwg | https://dwgshare.com/281-structural-drawings-of-5-story-house-a-complete-project-4-4m-x-19-8m-for-download/ | https://drive.google.com/uc?export=download&id=10ncBM8kcy_maOnWkbomZej7FP0Yv0ZW1 | 1788096 | AC1021 | 49b9f4ec7a87e65d1d65730c02b2b2498eeb582c886cd5987194a57ad873212e | 5-storey RC house on a narrow plot (4.4 m x 19.8 m), longer than eval4's 278 (4.4 m x 15.3 m) |
| 447_rc_multistorey_building.dwg | https://dwgshare.com/447-complete-reinforced-concrete-structural-cad-drawings-for-multi-storey-building-dwg/ | https://drive.google.com/uc?export=download&id=1LCLB9p-EMIFn_tnzIQyhMW1S9C7ATa2c | 3056079 | AC1032 | 0b6d87788e8f368ed08b58384bc45dbc2124a42bc0a63e37fea82f6091f8e83f | Non-house RC set ("Complete Reinforced Concrete Structural CAD Drawings for Multi-Storey Building"); newest DWG version of the series (2018) and the largest RC file so far |
| 442_steel_structure_22-story.dwg | https://dwgshare.com/442-download-free-detailed-cad-drawings-of-steel-structure-floor-plans-for-a-22-story-building/ | https://drive.google.com/uc?export=download&id=1z6ghM3uB7obNvIyMnuuQ_MVql3K3miHp | 2148608 | AC1021 | 69f660abfbaee595570ee1d145e3b91bc50a9517fe1ad2f1889127120e7de7a7 | Steel-structure building set ("Steel Structure Floor Plans for a 22-Story Building"); a multi-storey steel frame, unlike the portal-frame style steel sets in eval3/eval4. By title it is floor plans, so it may not be a complete set |

Original ZIP entry names (before renaming to short names): "297. Structural Drawings Of 3-Story House A Complete Project 8m x 18m For Download.dwg", "281. Structural Drawings Of 5-Story House A Complete Project 4.4m x 19.8m For Download.dwg", "447. Complete Reinforced Concrete Structural CAD Drawings for Multi-Storey Building (DWG).dwg", "442. Download Free Detailed CAD Drawings of Steel Structure Floor Plans for a 22-Story Building (1).dwg". Each ZIP held exactly one DWG.

Header magic: DWG = first 6 bytes (AC1021 = 2007, AC1032 = 2018).

Considered and not used: post 181 (steel building 3D template; the download is a 7z, not a ZIP/DWG). Not unpacked, deleted.

## What the source pages say

Only the post titles. The pages were not read for description. Sheet content (foundation plan, column/beam layout, schedules, notes) is therefore NOT confirmed. Vietnamese origin of 297/281 is inferred from the site series and house types, not verified. For 447 and 442 the country is unknown; their STYLE tables list Vietnamese-looking font files (447: vn_vni.shx, vh* TTFs, nghia5.shx; 442: vns.shx, vntimeh.shx), which suggests Vietnamese text, unverified.

## Fonts (aggregate, STYLE table only)

Converted with LibreDWG `dwg2dxf` into a scratch folder under /tmp/claude-1000/eval5-dl; only the STYLE table font file names were counted (no text, no sheet content), then the DXFs were deleted.

| File | Styles | With a font file | With a big font | Font files named |
|---|---|---|---|---|
| 297 | 17 | 12 | 2 | arial.ttf, bigfont.shx, chhbg.shx, hoatbif.shx, iso.shx, isocp.shx, micross.ttf, romans.shx, vn_vni.shx, vns.shx, vnsimli.shx |
| 281 | 24 | 24 | 4 | arial_3.ttf, romans.shx, times.ttf, txt.shx, vharialb_2.ttf, vhavan_2.ttf, vhavanb_2.ttf, vhhels_2.ttf, vn1.shx, vns.shx, vnsimli.shx, vntimeh.shx |
| 447 | 31 | 31 | 0 | arial.ttf, ltypeshp.shx, nghia5.shx, swissl.ttf, times.ttf, vharial.ttf, vharialn.ttf, vhavan.ttf, vhelvcn.ttf, vn_vni.shx |
| 442 | 5 | 3 | 1 | romans.shx, txt, vns.shx, vntimeh.shx |

All four reference legacy Vietnamese fonts (vn_vni.shx, vns.shx, vntimeh.shx, vh* TTFs). Styles without a font file (297: 5 of 17; 442: 2 of 5) are the case tool-wave-2 fix 2 targets. Which fonts the text actually uses is unknown until the reader runs.

## Handling

Untrusted third-party data. Never executed, never opened with a CAD tool, DWG content never read; only `head -c 6`, `sha256sum`, size and the STYLE-table font count above. Not committed to git (`dwg-lab/samples/**` is git-ignored except `*.md`).
