# Conventions: where each rule lives

This file routes; it does not restate. Each linked note marks every claim `verified` or
`unverified` with its source. Use only verified rules as rules; unverified ones become
questions. Rows pointing into `dwg-lab/` are **context only** (lab notes, not approved): they
explain a drawing, they never decide a value.

| Need | Read | Section |
|---|---|---|
| Rebar callouts (`4Ø16`, `Ø8a150`), bar marks, schedule columns, grades (CB…, CI…CIV, A-I…A-IV) | `docs/research/vn-structural-drawing-conventions.md` | 1 |
| Sheet codes, sheet-set order, title block fields | same | 2 |
| Axis naming, levels (`±0.000`, metres) | same | 3 |
| Member marks (`C1`, `D1`, `M1`, `GM`) — practice only, not standard | same | 4 |
| Steel sections (`I`, `H`, `U/C`, `L`, `V`), bolts, welds, steel grades (CCT/XCT, SS400, Q235) | same | 5 |
| Regexes for verified notations | same | Parsing patterns |
| Notations that must become questions | same | Ambiguous notations |
| Legacy font decoding (TCVN3/VNI, capital fonts, `%%c` order) | `docs/research/vietnamese-legacy-encodings.md` | all |
| Approved font → encoding decisions | `knowledge/font-encodings.csv` (only `approved` rows) | — |
| Section designations outside Vietnam (UB/UC, HE/IPE, AISC, JIS, GB) | `dwg-lab/references/02-steel/NOTES.md` | Section designations |
| RC schedules and BBS outside Vietnam (ACI 315, BS 8666, CDOT) | `dwg-lab/references/03-rc/NOTES.md` | all |
| CAD traps: model/paper space, xrefs, dimension overrides, layers as hints | `dwg-lab/references/04-cad/NOTES.md` | all |
| Reading order for a whole set (phases A–E) — context only; its A3 "use the later revision provisionally" is not a rule here (ask instead) | `dwg-lab/references/reading-checklist.md` | all |

## Glossary (Vietnamese → English, for matching drawing text)

| Vietnamese | English |
|---|---|
| bản vẽ thi công | construction drawing |
| khung tên | title block |
| ghi chú chung | general notes |
| mặt bằng định vị cột | column setting-out plan |
| mặt bằng móng | foundation plan |
| mặt bằng kết cấu tầng / mặt bằng dầm sàn | floor framing plan / beam and slab plan |
| trục, lưới trục | axis, grid |
| cao độ, cốt | level, elevation |
| cột, dầm, sàn, móng, giằng móng, vách | column, beam, slab, footing, ground beam, wall |
| cốt thép, thép đai, thép chủ | reinforcement, stirrup/tie, main bar |
| bảng thống kê cốt thép | rebar schedule |
| lớp bê tông bảo vệ | concrete cover |
| nối chồng | lap splice |
| kết cấu thép, thép hình, bản mã | steel structure, rolled section, plate (gusset/base) |
| bu lông cường độ cao | high-strength bolt |
| đường hàn góc | fillet weld |
| mác thép, cấp độ bền bê tông | steel grade, concrete strength class |
| đo bóc khối lượng | quantity takeoff |
