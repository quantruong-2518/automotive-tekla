<!-- PROPOSAL rev 11 — not live. The live file is .claude/skills/structural-drawing-reader/tools.md (rev 10). -->

# Tools: what exists, what is proposed, what to do meanwhile

Run every command through the one harness the dispatch names, for example `uv run --project <checkout> harness <command> <absolute path to
projects/<id>/work> …`. Projects live only in the main checkout: always pass absolute paths to `projects/<id>/…`. Never run two CLIs against one work
folder. `--help` of that same invocation is the source of truth. A command its `--help` does not list is missing: use the row's fallback. A fallback
of `stop` is a hard stop. A schema error from `status` on the work folder means the wrong harness: stop and name the command you ran.

Harness choice (engineer decision 2026-11-19, amended 2026-11-20): this skill needs the RT harness, branch `feat/reading-tools` (W4, the linework
commands and every `harness part` action); the dispatch names its worktree. A harness whose `--help` lacks them is the wrong one: `stop`. The W4 and
master fallbacks apply only if a later dispatch names another harness.

The fallbacks for rows marked P are engineer-approved procedure (rev 8–9, chat), not ad-hoc replacements in the sense of AGENTS.md § Hard stops:
"missing script → stop and ask" does not trigger. Record each manual step as `manual` in `PT/notes.md`; the reviewer re-checks it. Reported numbers
come from these commands and artefacts only; a scratch script adds none. Exceptions: grouping the rows of a saved `contents` document for C11 axes
(`manual: scratch grouping`, ids and document cited); a hand sum of printed integers or of `--claim` numbers, addends cited (a `values.json`
`hand_sum`). Search and listing stay inside `P`: no `grep -r`, `rg`, `find` or `**` glob over `projects/` or above `P` (SKILL.md § Hard stops).

Availability: **M** = on `master`; **W4** = on `feat/tool-wave-4`; **RT** = on `feat/reading-tools`; **P** = proposed, does not exist.

## Reading

| Need | Command or artefact | Avail. | Fallback when missing |
|---|---|---|---|
| Producer freshness, gate-1 reasons, `parts[]` | `harness status W` (§ Part mode) | M | stop |
| Sheets, ranked titles, `blocked_text_count` | `harness list-sheets W` | M | stop |
| Text of one sheet; search one sheet | `harness sheet-text W <file> <sheet_id> [--contains …] [--max N] [--include-hidden]`; rerun with the `--max` it names when `counts.truncated`; its `legacy_font_gate.blocked_entries` is the sheet's `blocked_in_scope` | M (count W4) | stop |
| Text on no sheet or on several | `sheet-text … --unassigned`, `find-text --unassigned` | W4 | Reach value `unread: text outside frames not reachable`, one question |
| Clusters of text outside every frame, assigned to the nearest frame by position | `harness unassigned-clusters W [--file F]` | RT | stop |
| A table as rows of cells | `sheet-text … --region=x0,y0,x1,y1` (always with `=`: a negative first value after a space is read as an option) | W4 | read the table row by row from entry `x`/`y`; a blank cell is `unread`, never `absent` |
| Search every sheet | `harness find-text W --contains … [--file F]`, then with `--include-hidden`, then with `--unassigned`. Write `--contains=-1.` with `=` when the text starts with `-`. `counts.blocked_in_scope`, `counts.not_printed_in_scope` and the font questions go into the search record | W4 | on a harness without these counts: no `absent`; the statement is `unread: search scope not reported`, with one question |
| Diacritic-, case- and space-insensitive search; `--sheet` | `find-text --normalised` | P (T10) | run each spelling yourself: with diacritics, without, upper and lower case, with and without the space or dash; list all in `searched:` (`part check` reports a missing twin: `search_unaccented`) |
| Text that does not print | `--include-hidden`, `printed` flag | W4 | cite read-log warnings; values stay at the extractor's confidence |
| Measured and printed dimension values | `harness dimensions W F [--sheet S \| --unassigned] [--layer L] [--max N]` | W4 | compare dimension texts only (`find-text` on the number); a measured value is `unread` |
| Marks, schedules, matching; rebar, steel, plate, bolt candidates | `W/marks.json`; `W/callouts.json` | M | stop |
| Grid systems and SVGs (per spacing `spacing_evidence` status `dimension_agrees`, `dimension_measured`, `dimension_differs`, `no_dimension`: SKILL.md § Phases, item 3 says what each needs); sheets, title blocks, grids, levels per file | `W/grid-systems.json`; `W/structure/<file>.{sheets,grids,levels}.json` | M | stop |
| Counts per mark across plan, column table and schedule (C12) | `harness part chain W --block B` (§ Part mode); the plan side comes from `contents` | RT (E7) | schedule and column-table counts side by side from `marks.json` and the table entries; the plan side from the saved `contents` document; integer hand sum with addends cited |
| Section and detail references, resolved to their targets | `harness detail-refs W` | P (T5) | trace by headings: `find-text` each section or detail label the plan shows (`1-1`, `A-A`, `CHI TIẾT`, `MẶT CẮT`, `DETAIL`, `SECTION`) and cite the heading entry; a label you cannot find as a heading goes into the orphan question |
| Revision, date and issue status per sheet; duplicate sheet numbers | `harness revisions W` | P (T9) | read `title_block.candidates` in `sheets.json`; search `REV`, `SỬA ĐỔI`, `HIỆU CHỈNH`, `LẦN`, `PHÁT HÀNH`; nothing → `revision: null` and one non-blocking question per set |
| Blocked entries per font across the set | `harness font-coverage W` | P (T15) | sum `blocked_text_count` per sheet from `list-sheets`; name the font questions |

**Compact output (every role).** Context is the budget: print what the step needs, never a whole artefact. `sheet-text` with `--region`, `--contains`
or `--max`; `find-text --max`; `contents` and `geometry` saved, then only the `summary` fields below; `finding list --kind K --file F`; `jq` or
`python -I -c` printing the keys you need. Never print `marks.json`, `callouts.json`, a saved document or a text index whole.

## Linework: geometry, contents, render (RT)

`W` = work folder, `F` = the file as `inventory.json` names it, `S` = a detector sheet id. All three are read-only on the drawing.
A layer's meaning (cap, pile, stub) is your judgement, recorded in the part's rows with its evidence (a legend, a mark inside the
outline, a schedule row); no tool decides it. Coordinates are world coordinates in drawing units as stored (`units` reports declared
and answered; the answer governs). Identical copies collapse into one item (`copies`).

| Command and args pattern | When (phase, trigger) | Cost |
|---|---|---|
| `geometry W F --sheet S1 S2 … [--layer L …] [--bbox x0 y0 x1 y1] [--detail] [--save]` | Phase 0, once per file, `--sheet` listing every sheet of the file (from `list-sheets`), `--save > /dev/null` (scout): which layers hold geometry, circle and outline groups by size. Read it through the compact summary below, never whole. Later, with `--layer`, to look at one layer. `--detail` only when a finding cites `G-` ids of this document. A `--bbox` document backs only a finding without `--sheet`: prefer `--sheet` with `--layer` | ~30 s per call on a large DWG whatever the filter (one walk of the file): batch the sheets; ~10 kB of JSON per sheet |
| `contents W F --sheet S --outline-layer L … --circle-layer L … [--marks REGEX] [--max-long N] [--mark-radius R] [--dims] [--detail] [--save]` | Phase 6 C11 (axes per member) and phase 4 (size, count, symbols and marks per type), one member plan sheet and one member family per call, once its layers are decided; run it once with `--save`, later steps reuse the same file. `--dims` also attaches the dimensions drawn on each rectangular outline and says whether the printed value agrees with the drawn size (`dims`; a stub's dimension centred on a cap attaches to the cap) | ~30 s per call; 60–80 kB of JSON for 80 outlines: always `--save` and print only the fields below |
| `render W F (--sheet S \| --bbox x0 y0 x1 y1) [--tiles CxR] [--layer L …] [--max-px N] [--out-dir D]` | Phase 4: before a count is recorded, one region per summary row (the bbox around one outline of that type, from its `centre`), and once the whole plan with `--layer` set to the member layers (members on other layers come from the phase 0 `geometry` groups, not from the render). Phase 1 only to orient. Open the PNG with Read | ~5–18 s per region; ~1.5k image tokens per image (`est_image_tokens`) |
| `dimensions W F --sheet S` (W4) | Before any size is taken from a detail or section. Only a row with `override_value` or `expected_text_value` gives a ratio (that value ÷ `measured`). A `text_rule: measured` row prints its measurement × DIMLFAC, which `dimensions` does not report (proposed T26): such rows confirm no ratio. A ratio on the detail → a size from its linework = `measured` × ratio, recorded with both sources. No ratio → a linework size from the detail is recorded only with an agreeing printed dimension (a text entry: an automatic dimension value has no entry id, so it cannot be cited; an override dimension's `text_entry` can), else a question (E06); no dimension rows → size `unread` (E39) | seconds |

Pattern for a saved run: `… contents W F --sheet model#02 --outline-layer S-CAP --circle-layer S-PILE --marks 'PC-\d+' --save > /dev/null`
→ stderr `saved: geometry/contents-model-02-<hash12>.json` (work-relative, `#` becomes `-`; the name carries a content hash,
a saved file is never overwritten; pass the path as `--source` as printed). Read it with
`python -I -c "import json,sys; d=json.load(open(sys.argv[1])); print(json.dumps({k: d[k] for k in ('summary','symbols','marks_unassigned','marks_ambiguous','outlines_total','warnings')}, ensure_ascii=False, indent=1))" <saved path>`.
`--marks` is the regex of the marks of ONE member family (caps: `PC-\d+`; stubs: `ST-\d+`), matched against the whole text,
never a plan's whole mark set: `contents` attaches any matching mark within `--mark-radius` to the nearest outline, so a beam mark
(`BM-…`) given on a stub plan lands on a stub. One `contents` call per family; a plan with no mark of that family: omit `--marks`
(every outline is `unmarked`). Legacy-font-blocked entries are never used.

Compact summary of a saved `geometry` document (phase 0; per sheet the layers as `[circles, outlines,
lines, hatches, invisible]`, every circle and outline group with its count and `invisible`, then the
warnings; fields only, no number comes from the script):
`python -I -c "import json,sys; d=json.load(open(sys.argv[1])); [print(r['sheet'], {k: [v['circles'], v['outlines'], v['lines'], v['hatches'], v['invisible']] for k, v in r['layers'].items()}, ['%s D%g x%d' % (g['layer'], g['diameter'], g['count']) for g in r['circle_groups']], ['%s %gx%g x%d inv%d' % (g['layer'], g['short'], g['long'], g['count'], g['invisible']) for g in r['outline_groups']]) for r in d['regions']]; print(d['warnings'])" <saved path>`.

### Reading `geometry`

`regions[]`, one per sheet: `layers{<layer>: circles, outlines, lines, arcs, hatches, open_polylines, hidden, invisible, …}`,
`circle_groups[]` (layer, diameter, count, copies, centre_bbox), `outline_groups[]` (layer, short, long, rectangle, vertices,
count, copies, invisible, centre_bbox). Counts are unique items. Two circle groups with the same count and `centre_bbox`, on one
layer or across layers, are one symbol family drawn with two diameters (Ø350 and Ø500 on `S-PILE`, Ø1100 on `S-PILE3D`, each 96:
96 piles, not 192 or 288). `hidden` = on an off or frozen layer, not drawn. `LINE`, `ARC`, hatch and open polylines are counted
per layer only: members drawn that way have no outline group (E39). Phase 0: a sheet with no text and no geometry is `near-empty`.
Phase 1: the layers and groups a sheet carries class a plan (caps and piles → foundation plan; stubs → stub plan); two sheets with
the same groups and counts are repeated views, never added; the same groups on another block's sheets are copied linework
(`linework_duplicate`, E40).

### Reading `contents`

- `summary[]`: one row per type (layer, `short` × `long`, `symbols` inside, `count`, `marks_seen`, `unmarked`, `invisible`);
  sizes, counts and piles per outline come from here; `symbols` = unique symbol centres inside the outline (concentric circles
  are one).
- `marks_seen` = mark text → how many outlines of the row hold it; `unmarked` = outlines with no mark. A mark is never copied to
  an unmarked outline; whether they carry the mark seen on the others is your judgement, recorded as a finding (SKILL.md §
  Claims). Example: row 1200×1200, 3 piles, 40 outlines, `marks_seen {PC-2: 20}`, `unmarked 20`.
- Warning `mark M is seen on outlines of 2 types` (`PC-1` on 800×1200 and 1200×2000): the tool does not say which is wrong: a
  question quoting both rows and the schedule row.
- `marks_unassigned`: no outline within `--mark-radius` (beam marks: beams are lines). `marks_ambiguous`: equally near two
  outlines: never pick. A mark applies only to the outlines it was assigned to, never to the whole row. Beam marks `BM-…(25x50)`
  in `--marks` of a stub plan attach to a stub within the radius: rerun without them.
- `symbols` / `symbols_outside`: circles inside no kept outline. Outside > 0 on a pile plan is a pile in no cap, the wrong
  outline layer, or a frame-sized outline dropped (`--max-long`). `--circle-layer` is required: on a plan with no symbols name
  the pile layer and expect `total 0`; the grid-bubble layer puts every symbol outside: a wrong layer, not piles.
- `outlines[]` (ids `G-…`): `centre`, `angle`, `symbols`, `marks[]` (text, `entry_id`, distance), `invisible`, `axes[]`, and with
  `--dims` `dims[]`. `axes[]`: per grid group of the sheet, per family, the nearest labelled axis `label` and the signed `offset`
  (outline centre minus axis, along the family normal; 300 and 250 on cap `G-0a1b2c3d4e` against axes A and 1);
  `nearest_unlabelled_offset` appears only when an unlabelled axis is nearer. `dims[]`: each dimension drawn on the outline and
  whether its printed value agrees with the drawn size.
- Warnings, each read: `N outline(s) lie in no grid group of sheet S` (a finding and a question: grid missing on that view or
  members outside it, C11); `N outline(s) longer than --max-long dropped (frames)` (confirm they are frames); `N entities carry
  the invisible flag (group 60)` (file level) and `N outline(s) and M symbol(s) used carry the invisible flag (group 60)` (the
  counted members themselves; next section); `some INSERTs were not expanded` (unread: `VIEWPORT` content; E08).
- `--save` lists outlines up to `--max` (500): `outlines_total` above the listed ones (`contents truncated` on stderr) is a
  truncated document that cannot back a count of the rest; rerun with `--max <outlines_total>`.

### The invisible flag (group 60 = 1)

`geometry` and `contents` count entities that carry it (`invisible` per layer, group, outline and summary row, plus the
file-level and outline-level warnings); `render` does not draw them. A summary row with `invisible` above 0 (or the outline-level
warning) needs the step below; the file-level warning alone needs only the whole-plan render. The warning says they are mostly
hidden visibility states of dynamic blocks: quote that sense, name no other cause. When a counted member is invisible, render its
region (`--bbox` around one such outline). Member drawn there by other entities (a stub layer whose every outline is invisible,
the render showing outline and hatch) → the count stands; the finding says `counted from hidden outlines, confirmed by render`.
Nothing drawn there → do not count it (a hidden state) and record that with its count. Where the render does not settle it, ask
whether it prints.

### Reading `render`

stdout is the document: per image `path`, `region`, `units_per_px`, `transform` (x = x0 + (px − left_margin_px) × units_per_px;
y = y1 − (py − top_margin_px) × units_per_px), `entities_drawn`, `entities_pruned`, `entities_invisible`, `est_image_tokens`.
A sheet is ~230 units per pixel (overview), four caps ~23, one cap ~3: a smaller bbox, never a bigger image, shows more. The
check per summary row: the outline looks like that member, the circles inside equal `symbols`, the outline's `marks[]` entry lies
at it. A mismatch is a defect to chase before recording (a mirrored insert once gave 80 piles for 96). An image never gives a
number or a text: the text index does. Model space only (a paper-space sheet is refused, exit 2). `--tiles 2x2` for a region
bigger than a few caps; `--out-dir` moves the PNGs from the default `W/renders`.

## Recording

In part mode every write below takes `--part <own part>` (§ Part mode). `finding add --field` takes: `note_item`
`topic=` one of `design_code`, `concrete_class`, `rebar_grade`, `steel_grade`, `bolt_grade`, `weld`, `cover`, `lap`,
`convention`, `other`; `structural_system` `aspect=` one of `frame_type`, `foundation_type`, `lateral_system`, `floors`,
`typical_floors`; `measured` `quantity=` one of `count`, `size`, `position`, `level`, `spacing`.

| Need | Command | Avail. | Fallback when missing |
|---|---|---|---|
| A claim | `harness finding add W --kind sheet_class\|note_item\|structural_system\|cross_check --file … [--sheet …] --entries T…,T… --value "…" [--field k=v] [--question Q-…] [--confidence low\|medium] [--note "…"] [--part P]`. For a `cross_check` whose entries sit on two sheets, omit `--sheet`. Omit `--sheet` too whenever a cited entry belongs to a text cluster outside the frames (the tool refuses entries not assigned to the sheet); put `assigned by position: <sheet>` in `--note`. A comparison across two files cannot be one finding: record one `cross_check` per file, each citing the other's finding id in `--note`, and both carry the same question | M | stop |
| Evidence saved for a measured finding | `harness geometry\|contents … --save` (`geometry` needs `--detail` to list items) | RT | stop |
| A value measured on linework: one member type (a count with its size and piles per outline), a position, a spacing | `harness finding add W --kind measured --file F [--sheet S] --source geometry/<name>.json --items G-…,G-… --field quantity=count\|size\|position\|level\|spacing --claim count=N --claim short=S --claim long=L --claim symbols=K --value "…" [--entries T…] [--question Q-…] [--confidence low\|medium] --note "…" [--part P]`. Recipe: (1) one finding per member type, that is one `summary` row: `--items` every outline id of that type, so a reviewer can recount; (2) every standalone number in `--value` must match a `--claim KEY=VALUE` (keys `symbols`, `short`, `long`, `diameter`, `count`) or a number in a cited entry, else `finding add` exits 1 (numbers glued to letters, `#` or `-` like PC-1 or C30 are ignored; d500 counts as 500; 1200x3200 is two numbers); each claim is checked against every cited item (`count` = the number of items; a `contents` outline carries no diameter, so a diameter needs a cited schedule or callout entry); (3) the items must lie on `--sheet`, and the tool refuses a cited entry not on `--sheet`: omit `--sheet` when an agreeing entry sits on another sheet than the plan (the saved document still names the plan sheet); (4) cite the saved file as printed on stderr (never overwritten: the name carries a content hash); extract the ids with `python -I -c` filtering `outlines[]` on layer, `short`, `long`, `symbols` (ids only; no number comes from the script); (5) `--entries` is optional: the mark entries (`marks[].entry_id`) and any printed value that agrees. A total over types (96 piles) is no finding of its own: it is a `hand_sum` of the per-type findings (`{finding, of: symbols}` terms, each `of: symbols` adds that finding's `symbols` over its items; `of: items` counts them), written in the row or judgement that needs it. Confidence: § Measured findings below | RT | stop |
| A mismatch between a printed quantity and a counted one (C12) | `finding add --kind cross_check --file F --entries T<schedule entry> --source geometry/<name>.json --items G-… --question Q-… --value "…" --note "…"`: one entry plus the saved document replaces two entries; omit `--sheet` when the entry and the document are on different sheets | RT | two entries, as in the first row of this table |
| Alternative and basis as fields; refusal of `low` without `--question` | `finding add --basis … --alt …` | P (T3) | the `--note` form in SKILL.md § Claims (`part check`: `claim_form`, `low_without_question`) |
| A breakdown node (parent, sheets, coverage) | `finding add --kind breakdown_node` (RTI-0014 decision 2) | P (T1) | the Breakdown table in `W/reading-record.md`; each sheet's `sheet_class` finding carries `node: <id>` in `--note` |
| An absence with its search scope | `harness finding absence W --file F [--sheet …\|--all] --topic T --query … --question Q-…` (the tool runs the search and refuses on a hit) | P (T2) | the search record in the question's `--found` or the row's `note`, in the form of SKILL.md § Seen, unread, absent |
| A question | `harness ask W --code reader_<topic> --file … --sheet <detector id> --where "…" --found "…" --text "…" [--blocking] [--part P]` | M | stop |
| Evidence on a producer's question | `ask --supplement Q-…` (**producer questions only**; with `--part` it is exit 2) | W4 | cite the producer's Q-id in your finding; put the evidence in the finding's `--note` |
| Amending, withdrawing your own question or finding | `ask --amend Q-… [--text …] [--places …] [--part P]`, `ask --withdraw Q-… --reason … [--part P]` (`--part` one of the question's parts), `finding withdraw W F-… --reason … [--part P]` (the finding's own part) | W4 | ask again with a `--where` that names every place, then withdraw the old question with `--reason "replaced by Q-…"` |
| Rendered questions | `harness questions-md W` | M | stop |

### Measured findings: confidence (the one statement; SKILL.md, reading-method, review-rubric R6 and the design note point here)

- Confidence is `high` only when there is at least one `--claim` and every claimed number appears in a cited entry's text (an
  agreeing schedule row, note, pile total or size text; `basis: two_sources`, never above the lowest cited entry's confidence).
  Otherwise it is `medium` (the measurement is exact; which layer is a pile or a cap is your reading), `basis: single_source`.
  This is not `low`: no `--confidence low`, and R6 asks no per-value question for it. `--confidence` only lowers it.
- A gate 1 or gate 3 listed value (SKILL.md § Asking) read only from linework (`medium`, no agreeing printed entry) needs ONE
  blocking question per part (`reader_family_linework`), not one per value: "Đài móng khối A: 3 loại kích thước và số cọc mỗi
  loại đo từ nét vẽ như bảng sau, đúng không?" (form: reading-method § Recording forms). A measured finding with an agreeing
  printed entry needs no question, nor does one outside listed values or one from linework copied from another block (E40).
- A disagreeing printed value (beyond E42's spread): no `measured` finding rests on it; record a `cross_check` (one entry plus `--source`/`--items`)
  and a question quoting both. The render checks the tool; it is no second source.

## Part mode: `harness part`, `--part`, lock wait

Part mode is on when `W/parts/manifest.json` exists. Then `finding add|withdraw` and `ask` need `--part <id>` (exit 2 without; exit 1 for an id the
manifest does not list, or a locked part: reopen it first); `ask` on an existing key with another part adds the part (`already_asked_part_added`).
Part ids: `all-grid-levels`, `all-notes-materials`, `scout`, `all-assembly`, `all-no-sheet`, `<block>-<family>[-<letter>]`. Order, roles, forms:
[part-mode.md](part-mode.md). Every `part` action prints JSON (exit 0 ok, 1 problems, 2 usage, 3 environment).

| Action (`harness part …`) | Use and result | Lock | Fallback when missing |
|---|---|---|---|
| `manifest-check W [--input-dir I]` | Scout, after writing the manifest: `{ok, sheets {total, covered}, parts, problems[], warnings[], skipped[]}`; exit 0 only with no problem and every warning acknowledged by its exact id in `acks[]` | no | stop |
| `check W --part X` | Reader and reviewer; on every `locked` part the assembler runs it before assembly and Part C of `drawing-analysis-report` before take-off (a revised input moves the hash): `{part, hash, ok, counts, problems[{code, row, id, detail}]}` for every cited id, number, hand sum, state and text rule of `X/values.json` and its findings (§ Problem codes) | no | stop |
| `receipt W --part X --kind checked\|reviewed\|locked\|reopened [--review R --round N --verdict pass\|fix\|engineer] [--reason T]` | Orchestrator only. `checked` reruns `check`, refuses on problems and on a part whose latest receipt is `locked`; `reviewed` needs `checked` on the current hash plus `--review W/parts/X/review/round-N/review.md`, `--round`, `--verdict`; `locked` needs the latest `reviewed` receipt on the current hash to say `pass` (a later `fix` blocks it) and every input part `locked`; `reopened` needs `--reason` and a part whose latest receipt is `locked` (also the way back for status `reopened` and `stale_input`). Appends to `X/receipts.json`; exit 1, nothing written, when a precondition fails | yes | stop |
| `chain W --block B` | Assembler (C12): the member parts of `B` in manifest order, each `count_plan`, `count_schedule`, `piles_per_member` row with its hand-sum addends, the cap products and sums; judges nothing | no | the C12 fallback in § Reading |
| `review-sample W --part X --seed S [--n N]` | Orchestrator, for stage A, with a `--seed` it picks after the part is `checked` (never the reader): one prompt per sampled row (mark × field, never the value), plus one absence and one outside-frame prompt when the part has them; same seed, same prompts. A prompt may hold no sheet number or view (they would give the value away): the reviewer finds the place with its `file` and `sheet` keys | no | review-rubric.md § Sample |
| `conflicts W` | Orchestrator, after each `checked` receipt and again before assembly: one question per value two parts state differently (`part_value_conflict`, `part_system_conflict`, `part_measure_conflict`), blocking when the field is listed, tagged with both parts; a plan count conflicts only when two parts read the same sheet (sums across sheets: `chain`); an answered conflict question keeps its answer on a rerun; duplicates are listed, never asked; no merged value | yes | stop |
| `spotcheck W --part X --seed S [--n N]` | Orchestrator, a `locked` part only: writes `X/spotcheck.json` and `P/spotcheck/X.md` (the engineer's checklist, Vietnamese); its pool leaves out a row whose key is ambiguous (named on stderr, `key_ambiguous`) and a row with no file | yes | not run; name it in the hand-back |
| `answer-key W --part X --row R --verdict ok\|wrong\|cannot_tell --by NAME [--correct V] [--text T]` | Orchestrator, a `locked` part: the engineer's chat words, `--by` his name as he gives it, `--correct` with `wrong`; refuses a row not sampled, a part changed since the sample and an ambiguous key (exit 1 `key_ambiguous`) | yes | not run; name it in the hand-back |
| `score W [--answer-key F]` | Read-only, exit 0: any work folder against `W/answer-key.json` or a benchmark copy; per part `checked`, `agree` (every `seen` row under the key equals its correct value), `differ` (any row differs), `missing` (no counting row), `cannot_tell`; accuracy is agree ÷ (checked − cannot_tell), so `missing` counts against the reading | no | not run; name it in the hand-back |
| `takeoff render W (--part X \| --all) [--out DIR]`, `takeoff plan W [--out DIR]`, `takeoff check W [--out DIR]` | Take-off stage, run by `drawing-analysis-report` Part C: `render` writes the part file (generated blocks never edited; the writer fills the slots `<!-- ai:method -->` and `<!-- ai:reason -->`); `plan` writes `00-plan.md`; `check` (read-only) exits 0 when generated blocks equal a fresh render and the slots hold no ids or jargon | render, plan | stop |

**`harness status W` `parts[]`**: per part `{id, kind, status, hash, stale_inputs, blocking_open_ids, blocked_by_project, ready}`. `status`: `reading`
(no `checked` receipt on the current hash), `checked`, `reviewed`, `locked`, `reopened` (a locked part whose hash changed: findings, questions, a
revised drawing, a cited grid system, its block or `values.json` or `notes.md` edited), `stale_input` (an input part changed after the lock), `receipts_invalid`. `ready` =
locked, `blocking_open_ids` empty and `blocked_by_project` false; an answer moves `ready`, never the hash. `harness status W --verify` runs the part
check on every `locked` part: a failing part shows `check_failed: true`, `ready: false` and `check_codes` (or `check_error` when the check could not run: fix the environment, never reopen on it); a part built on a failing input shows `input_check_failed: [ids]` and `ready: false`; `verified` is true only when every check ran. The take-off commands always verify. Next
to `parts[]`: `project_blocking_ids` (open blocking questions that hold every part) and `parts_project_reasons` (why `blocked_by_project` is true). A
`parts_error` (manifest or a record unusable, the message names the file) means: fix the named record first.

**Lock wait.** `finding add|withdraw`, `ask`, `answer`, `questions-md`, `part receipt|conflicts|spotcheck|answer-key`, `takeoff render|plan` and the
file write of `--save` hold one exclusive lock on the work folder. In part mode a second command waits up to 60 s (retry every 0.2 s), then exits 3
and says how long it waited; after a wait that succeeds, stderr prints `lock: waited <s> s for harness <command> (pid n)`. So readers record their own
findings and questions. `HARNESS_LOCK_WAIT=<seconds>` overrides the 60 s (write it in the command: a shell keeps no variable; a non-number or negative
value is exit 2). A lock held from another OS (WSL against Windows) is refused at once. Without a manifest a second writer gets exit 3 at once. After
an exit 3 from a lock wait, rerun the same command once; a second exit 3 is a hard stop: hand back with the stderr line. Writes are atomic: no update
is lost, ids follow arrival order. Every other command takes no lock.

### Problem codes: where each is fixed

`part check` `problems[].code` (`row` or `id` names the row or the finding or question). Fix a problem where it sits, rerun `check`.

| Fix in | Codes: meaning |
|---|---|
| Stop, whole answer | `manifest_invalid`: manifest unreadable or off schema (scout). `part_unknown`: `--part` not in `parts[]`. `values_invalid`: `values.json` off the `part-values` schema (the detail names the path). `input_invalid`: a tool-written input (findings, questions, registry, marks, `grid-systems.json`) is malformed: regenerate it with its producer; no row is at fault |
| The row | `row_duplicate`: a row id, or file + sheet + mark or subject + field, twice. `row_state`: `seen` needs value, file and a finding, entry, geometry or hand sum; `asked` a question; `unread` no value and a question; `absent` no value and a finding or question holding the search record. `row_outside_part`: its sheet, cluster or view is not in the part's manifest row (only an input lists it): fix the row, or the manifest (scout) |
| The citations | `cite_unknown`: an id is in no findings file, registry, saved document or text index. `cite_inactive`: withdrawn finding, obsolete question. `cite_stale`: the finding's evidence changed: rerun the call, record again. `cite_foreign_part`: the id belongs to a part that is neither this one nor an input: the scout lists that part in `inputs[]`, or cite your own finding (a grid system of another block counts here). `entry_blocked`, `entry_not_printed`: quote the entry in a question, never cite it. `entry_outside_part`: the entry lies on no sheet or cluster of the part or its inputs |
| The value | `number_unbacked`: a number of `value` is in no cited finding value, claim or entry text. `token_unbacked`: a glued token (`-1.200`, `2Ø16`, `C30/37`) no cited text quotes. `value_not_verbatim`: a `seen` text value that quotes no cited entry. `note_quote_unmatched`: a quoted span of the `note` is in no cited source. `hand_sum_invalid`: a term cannot be added (finding without evidence, item without `symbols`, font-blocked or unprinted entry, entry without exactly one integer, `marks` term with no sheet or no `marks.json`). `hand_sum_mismatch`: the terms do not add up to the value |
| Coverage | `sheet_uncovered`: a manifest sheet has no row and no finding of the part: read it, or add an `unread` row with its question. `mark_missing`: a `marks.json` mark on the part's sheets that fits `marks_regex` has no row. `marks_regex_invalid`: the regex does not compile (scout) |
| Questions and notes | `listed_needs_blocking`: a listed field (all but `material`, `other`) that is `asked`, `unread`, `absent` or `seen` on one source cites no blocking question. `listed_question_not_blocking`: a question a listed row cites is not blocking. `low_without_question`: a `low` finding cites no question beyond the font questions. `claim_form`: the note lacks `node:`, `basis:` or `alt:`. `note_item_prefix`: a `note_item` note does not start `block:` |
| Search and linework | `search_unaccented`: a `searched:` record has an accented term and no unaccented twin (`đ` → `d`). `family_linework_twice`: a second live `reader_family_linework` question in the part: `ask --withdraw` it. `family_linework_needless`: the question stays though every linework row has two source keys: withdraw it |

`part manifest-check` `problems[]` (scout; `{code, part, file, sheet, detail}`):

| Fix in | Codes: meaning |
|---|---|
| Coverage | `sheet_uncovered`, `cluster_uncovered`: no part lists it. `cluster_in_two_parts`, `sheet_in_two_blocks`: in two parts, or in member parts of two blocks. `sheet_unknown`, `cluster_unknown`: not in `list-sheets` or `unassigned-clusters`. `file_unread`: a DWG or DXF `list-sheets` skips and no `no_sheet` part names in `files[]`. `files_entry_unused`: a `files[]` item on a part that is not `no_sheet`, or on a file `list-sheets` does not skip. `part_over_cap`: over 4 sheets or 1,500 printed entries: split the part |
| Parts and inputs | `duplicate_part_id`, `duplicate_block_id`, `cross_part_missing` (a cross part or its split), `bookkeeping_part_missing`, `part_kind_mismatch` (id and kind disagree), `block_unknown` (a member part needs a listed `block` and a `family`), `input_unknown`, `input_cycle`, `order_not_after_input`, `table_outside_part`, `entry_unknown` (a manifest entry id is not on that sheet or cluster), `grid_system_unknown` (not in `grid-systems.json`), `schema` (manifest missing or off schema) |
| Records and acks | `record_part_unknown`: a finding or question names a part the manifest does not list: `finding withdraw … --part X`, `ask --withdraw … --part X`. `ack_unmatched` (names no warning), `ack_duplicate`, `ack_question_unknown` (question not in the registry) |
| Units | `unit_answer_unread`: the units answer cannot be read (ledger unreadable, or active answers give no single unit); not ackable. `unit_unanswered`: the file has no units answer, so no ack clears it: only the engineer's answer, recorded by the orchestrator (SKILL.md § Asking), does; the measuring rules skip the file, the declared unit is never a fallback. A missing `question-registry.json`: exit 2, no JSON, stderr names `harness intake` |

Warnings of `manifest-check` block exit 0 until acknowledged; `warnings[].id` is the exact `acks[].warning`:
`grid_origin_other_block|<file>|<sheet>|<other block>` (grid origin on another block's sheets), `linework_duplicate|<part>|<file>|<sheet>|<other
sheet>` (plans of two blocks with the same outline signature on the part's layers: copied linework, E40), `revision_from_table|<file>|<sheet>|<entry
id>` (a revision read from a table, not a title block). Ack with the question that asks the designer, or a reason. `skipped[]` (`unit_unknown`,
`no_grids_document`, `no_plan_grid`, `several_plan_grids`, `rotated_grid`, `few_items`, `no_position`): a sheet a warning could not test, no failure;
say it in `notes.md`.

## Review and improvement (orchestrator and reviewer)

| Need | Command | Avail. | Fallback when missing |
|---|---|---|---|
| Blind prompts sampled from a part's rows without their values | `harness part review-sample` (§ Part mode) | RT (E7) | review-rubric.md § Sample |
| Comparing sealed answers with the reading | `harness review-compare W --round N` | P (T6) | the reviewer's stage B table |
| A report whose negatives and numbers all cite an artefact | `harness check-report W <doc>` | P (T7) | the report skill's own done-when |
| A search over `projects/` outside the work folder denied | PreToolUse hook | P (T19; built later) | SKILL.md § Hard stops, written rule |
| Known-answer cases after a skill or tool change | `harness part spotcheck`, `part answer-key`, `part score` (§ Part mode) | RT (E9) | improvement-loop.md § Benchmark |
| Approved reading conventions | `knowledge/drawing-conventions.csv`, `approved` rows only | P (T11) | conventions.md routes to the research notes; only their `verified` claims are rules |

## What no tool gives today

Say so in `PT/notes.md` and in the hand-back; these are tool gaps, never facts about the drawing:

- one grid system placed on two blocks of the same file (`separate=` splits different systems only); section and detail
  bubbles as objects; revision clouds and triangles; viewport scales, frozen layers per viewport, unexploded inserts (read-log
  warnings only); a steel column or base-plate table that `marks` did not recognise (`matched: 0` then says nothing);
- members drawn as loose lines, as hatch only, or as two parallel lines (beams: no outline, so no count, size or axis;
  `geometry --detail` lists no items on open-line layers, T25); details drawn only in paper space (`render` refuses them);
  sections without a dimension row, or whose rows give no ratio (`dimensions` does not report DIMLFAC: T26 proposed) (E39,
  E06): read by text, a linework size not recorded without an agreeing printed dimension, count `unread`, one question.
