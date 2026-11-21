# Conventions: where each rule lives

This file routes; it does not restate. The project's own legend and notes come first. Each
linked note marks every claim `verified` or `unverified` with its source: a `verified` claim is a
rule, an `unverified` one is a question. Rows pointing into `dwg-lab/` are lab notes: they
explain a drawing and decide no value.

| Need | Read | Section |
|---|---|---|
| Rebar callouts (`4Ø16`, `Ø8a150`), bar marks, schedule columns, grades (CB…, CI…CIV, A-I…A-IV) | `docs/research/vn-structural-drawing-conventions.md` | 1 |
| Sheet codes, sheet-set order, title block fields | same | 2 |
| Axis naming, levels (`±0.000`, metres) | same | 3 |
| Member marks (`C1`, `D1`, `M1`, `GM`): practice only, not standard | same | 4 |
| Steel sections (`I`, `H`, `U/C`, `L`, `V`), bolts, welds, steel grades (CCT/XCT, SS400, Q235) | same | 5 |
| Regexes for verified notations | same | Parsing patterns |
| Notations that must become questions | same | Ambiguous notations |
| Current and superseded editions of design, pile, drawing and material standards | `docs/research/vn-structural-standards-editions.md` | all; § What this means for a drawing reader |
| Steel industrial buildings: frames, bases, anchor bolts, purlins, bracing, crane beams | [steel-industrial.md](steel-industrial.md), then `docs/research/steel-industrial-building-drawings.md` | all |
| What a Tekla model needs from the drawings (order, catalog names, gaps) | `docs/research/tekla-modelling-from-drawings.md` | 11 |
| Legacy font decoding (TCVN3/VNI, capital fonts, `%%c` order) | `docs/research/vietnamese-legacy-encodings.md` | all |
| Approved font → encoding decisions | `knowledge/font-encodings.csv` (`approved` rows only) | — |
| Section designations outside Vietnam (UB/UC, HE/IPE, AISC, JIS, GB) | `dwg-lab/references/02-steel/NOTES.md` | Section designations |
| RC schedules and bar bending schedules outside Vietnam | `dwg-lab/references/03-rc/NOTES.md` | all |
| CAD traps: model and paper space, xrefs, dimension overrides, layers as hints | `dwg-lab/references/04-cad/NOTES.md` | all |

## Collisions

One label, two readings. The drawing's legend or schedule decides; without one, ask in the
file's prefix question with both readings and the entries for each.

| Label | Reading A | Reading B |
|---|---|---|
| `C` + number | column mark | channel section |
| `V` | wall mark (vách) | equal angle |
| `M` + number | footing mark (móng) | bolt diameter (`M20`) |
| `KT` | architecture sheet prefix | steel truss or rafter mark |
| `D`, `Đ`, `DC`, `DM`, `DP` | beam families | pile cap, foundation beam, other |
| `CT`, a letter pair beside a cut line | member family | section label |
| a number in a circle | bar mark | item number in a steel assembly |
| a code with a dash and digits (`xx-00`) | member mark | sheet or drawing-list code |
| `L` | angle section | length (`L=`) |
| `PL`, `BM`, `TẤM` + numbers | plate with thickness × width × length | another field order |
| `H`/`I` + four numbers | depth × width × web × flange of a rolled section | a built-up section, flange and web given in another order |

## Glossary (Vietnamese → English, for matching drawing text)

| Vietnamese | English |
|---|---|
| bản vẽ thi công | construction drawing |
| danh mục bản vẽ | drawing list |
| khung tên | title block |
| ghi chú chung, thuyết minh | general notes |
| mặt bằng định vị cột / cọc | column / pile setting-out plan |
| mặt bằng móng, mặt bằng cọc | foundation plan, pile plan |
| mặt bằng kết cấu tầng, mặt bằng dầm sàn | floor framing plan, beam and slab plan |
| mặt cắt, chi tiết, chi tiết điển hình | section, detail, typical detail |
| trục, lưới trục | axis, grid |
| cao độ, cốt | level, elevation |
| cột, dầm, sàn, móng, giằng móng, vách | column, beam, slab, footing, ground beam, wall |
| cọc, đài cọc, cổ cột, cao độ cắt cọc, đầu cọc | pile, pile cap, pedestal (stub column), pile cut-off level, pile head |
| sàn nền, khe co, khe giãn | slab on ground, contraction joint, expansion joint |
| cốt thép, thép đai, thép chủ | reinforcement, stirrup or tie, main bar |
| bảng thống kê cốt thép / thép | rebar schedule / steel schedule |
| lớp bê tông bảo vệ | concrete cover |
| nối chồng | lap splice |
| kết cấu thép, thép hình, thép tổ hợp | steel structure, rolled section, built-up section |
| nhà xưởng, nhà thép tiền chế | factory building, pre-engineered steel building |
| khung, kèo, cột, đỉnh kèo, nách kèo | frame, rafter, column, apex, haunch |
| xà gồ, giằng xà gồ | purlin or girt, sag rod |
| giằng mái, giằng cột, giằng cánh | roof bracing, wall bracing, flange brace |
| dầm cầu trục, vai cột | crane runway beam, crane bracket (corbel) |
| chân cột, bản đế, bản mã, sườn gia cường | column base, base plate, gusset or connection plate, stiffener |
| bu lông neo, bu lông cường độ cao | anchor bolt, high-strength bolt |
| đường hàn góc | fillet weld |
| tôn mái, tôn vách | roof sheeting, wall sheeting |
| mác thép, cấp độ bền bê tông | steel grade, concrete strength class |
| tương tự, đối xứng, điển hình | similar, symmetric (mirrored), typical |

The glossary matches words; it assigns no role to a mark and no meaning to a blocked entry. The
steel-building rows are search vocabulary: steel-industrial.md § Vietnamese terms says which a
source confirms.
