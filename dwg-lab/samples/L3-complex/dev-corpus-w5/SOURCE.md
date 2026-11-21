# SOURCE - dev-corpus-w5

Development corpus, wave 5 (2026-11-10): 18 DWG sets widening the variety available before EVAL-5. NOT held-out: these may be used for tuning. All come from dwgshare.com (the only open-access source found that needed no login, payment or captcha; see "Not found" below).

- Licence / terms (all rows): no per-file licence; dwgshare Terms & Conditions section 1.5 (https://dwgshare.com/terms-conditions/). PERSONAL / INTERNAL RESEARCH USE, NO REDISTRIBUTION. Do not commit, push or ship in a benchmark release.
- Safety: files untrusted, never opened with a CAD tool, never converted, never executed. Header magic and sha256 verified; every content claim is "per source page, not verified". ZIPs were listed with `unzip -Z1` (no absolute paths or `..`) before `unzip -d` into a staging folder outside the corpus.
- Dedup: DWG sha256 checked against `known-sample-sha256.txt` (0 matches kept; one candidate, post 161, matched and was dropped); download and page URLs checked against the held-out URL list (posts 447 and 442 were skipped for that reason).

| Folder | Post | DWG version | Size | sha256 | Variety targets (per source page, unverified) |
|---|---|---|---|---|---|
| `dwgshare-441-download-free-detailed-cad-drawings-of-beam-reinforcement-fo/` | 441 | AC1021 | 7.2 MB | `5d4594c7699a0ba7f36a1852b1bc2894d1b1fe197fa10ef2be59a3cc4d098567` | RC multi-storey frame; beam schedules/reinforcement; tall building (22 storeys per title) |
| `dwgshare-446-typical-floor-levels-2-8-technical-floor-structural-cad-draw/` | 446 | AC1021 | 1.2 MB | `e0101f77dfff478acce6b7da3c80f5f9db68b9b98cfbe216ef79f99670a5b64e` | RC multi-storey frame; typical floor + technical floor plans (levels 2-8 per title); possibly multiple sheets |
| `dwgshare-438-complete-reinforced-concrete-structural-cad-drawings-for-res/` | 438 | AC1032 | 4.5 MB | `bcd465399b31a0e3a5bd2a9b0622855d698af67c87ef3fcd99338a239bcfa9d0` | RC multi-storey residential complete set; foundation + frame + schedules (per title) |
| `dwgshare-459-12-story-apartment-building-design-project-full-architecture/` | 459 | AC1032 | 2.5 MB | `602d5671359397280ecd0d09c1f90c2c6ae5da4b17b07822dc38fd6d7c9d04dc` | RC multi-storey (12 storeys); architecture + structure in one file, technical report; multi-sheet |
| `dwgshare-387-free-download-of-structural-cad-drawings-for-9-2m-x-22-8m-re/` | 387 | AC1021 | 1.4 MB | `7ad90d0fdacce6dd3f4011c0cb9aaa7b33d0202386dc99ae0f8e4de7f2fa9def` | RC townhouse (narrow plot 9.2 x 22.8 m); Vietnamese-style nha pho layout (unverified) |
| `dwgshare-430-download-of-structural-cad-drawings-for-6-4m-x-13m-reinforce/` | 430 | AC1032 | 1.2 MB | `95cb52c8782d4189ca44247f9cac185e9620aaba23a618d7d1de9c8d1607d201` | RC townhouse (6.4 x 13 m, narrow plot); newer DWG version |
| `dwgshare-435-download-of-structural-cad-drawings-for-15-4m-x-15-7m-reinfo/` | 435 | AC1032 | 2.0 MB | `7476dd8517d4d44eae3ac2cbf93aa97fd72d43e288dd3c19ad29ad34c2f1cc63` | RC townhouse (15.4 x 15.7 m, near-square plan); different aspect ratio from the narrow-plot sets |
| `dwgshare-460-download-of-structural-cad-drawings-for-8-2m-x-19-3m-reinfor/` | 460 | AC1027 | 754 KB | `32a36adef415d44a1740333625fbb8be77107dd25bd64410b9d3e7a47ef8ad96` | RC townhouse (8.2 x 19.3 m); AC1027 header (DWG 2013) |
| `dwgshare-774-5-story-house-design-6m-x-14m-complete-floor-plans-elevation/` | 774 | AC1032 | 1.3 MB | `a1f5f79a792e30128c3d750faac309d4fa0e2131819871346390b367b1668397` | RC 5-storey house; floor plans, elevations and foundation in one file |
| `dwgshare-437-foundation-structural-cad-drawings-footings-grade-beams-colu/` | 437 | AC1032 | 690 KB | `be512a10afdd879012c5d2f069903ddfc417fa18a24ed85029ec53ce4ad8c740` | Foundation plan: footings, grade beams, column details (per title); footing schedules likely |
| `dwgshare-439-download-complete-pile-foundation-structural-cad-drawings-wi/` | 439 | AC1032 | 11.4 MB | `ada18b72054f5a385e07521e51114e07cc8b07650aaac5c3201fcb65efe4abe7` | Pile foundation, complete set with reinforcement details; large (11.9 MB) file |
| `dwgshare-443-download-free-detailed-cad-drawings-of-raft-foundation-steel/` | 443 | AC1021 | 1.1 MB | `5f31643a6e0ac7b796ebf4fbaa50444b13c0847cdc008971197a8c62e1f5e282` | Raft foundation plans (title also says steel structure); AC1021 |
| `dwgshare-451-download-reinforced-concrete-curved-beam-cad-drawings-with-r/` | 451 | AC1032 | 2.3 MB | `171c1392054aaf8a240de878310209b64af641be4ec58bca57a9905fff25e781` | RC curved beam with reinforcement details and bar schedules; curved/polyline beam target; schedules |
| `dwgshare-449-download-reinforced-concrete-beam-reinforcement-cad-drawings/` | 449 | AC1032 | 4.8 MB | `2d16c0f41e70e22b0d0f56c73280a9224930aa0266bd63568701977fefea246b` | RC beam reinforcement with rebar schedules; beam/column schedule target |
| `dwgshare-51-cad-drawings-of-steel-factory-plan-sections-and-elevation-30/` | 51 | AC1032 | 1.7 MB | `a9ce2e878b1407a65425509bb6f7ccccdd9de4c311d0e7b18732bff23e61f97e` | Steel factory/industrial shed 30 x 96 m: plan, sections, elevation |
| `dwgshare-362-download-structural-cad-drawing-of-factory-with-dimensions-2/` | 362 | AC1021 | 605 KB | `0db3f18a9b62487720bf88f345f90d7bae393577375283081c5ba8aa3ad7f59b` | Structural drawing of a factory 28 x 36 m (frame type not stated on page); AC1021 |
| `dwgshare-456-free-steel-structure-shop-drawings-roof-framing-connection-d/` | 456 | AC1032 | 8.5 MB | `b36790deaedd9e76fbb010014d753174c06746cae05d67acfa161b3dea0c3d11` | Steel structure shop drawings: roof framing and connection details; large (8.9 MB) file |
| `dwgshare-599-download-curved-steel-roof-truss-cad-drawings-structural-fra/` | 599 | AC1032 | 234 KB | `e0c529f18951998d7dd92d188865dbcf86321fd76d52d942cf477cd46e34fbad` | Curved steel roof truss: structural frame and connection details; curved members |

## Coverage summary

- Header versions: AC1021 x5, AC1027 x1, AC1032 x12. No file older than AC1021 was found among free sets (older versions remain only in the L1 version matrix).
- Covered (claimed): RC multi-storey frames, RC townhouses (several plan aspect ratios), foundation/pile/raft plans, beam rebar schedules, steel factory/shed, curved beam (451), curved steel truss (599), multi-sheet files (459, 446, 438 per titles).
- Not covered: imperial/feet-inch set; Vietnamese TCVN3/VNI font use is unverified (townhouse sets are Vietnamese-style but fonts were not read); non-orthogonal or curved grid axes not claimed by any page; older DWG (< AC1021); a second curved/polyline beam set beyond 451.

## Not found (no workaround attempted)

- designscad.com: login required (already rejected in INDEX.md).
- cadbull.com: pages found by search but downloads need an account (not tried further).
- GitHub code search for `.dwg` structural files returned nothing usable.
- No open-licence imperial structural set was found.
