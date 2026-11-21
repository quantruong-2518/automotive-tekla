# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/).
Harness releases are tagged with their benchmark score (see `benchmark/README.md`).

## [Unreleased]

### Added
- `harness part spotcheck W --part X --seed S [--n N]` (E9a, ADR-0019): the body of the E6w stub in
  `part_spotcheck.py`, a locked writer; exit 1 unless the part's status is `locked`. It draws a seeded sample of
  the part's `seen` rows (`part_sample.stratified`, salt `X:spot`, default 5): one row per LISTED field, chosen
  among that field's rows of the lowest priority (measured of medium confidence, other measured, the rest); the
  other slots are a seeded draw. It writes
  `parts/X/spotcheck.json` (new schema `answer-key` 0.1, `kind: spotcheck`: per row the mark or subject, field,
  value, file, sheet, sheet number, title and view texts, and the cited entry and finding ids, with the
  `part_hash` the sample was drawn at, which `answer-key` will accept only) and the Vietnamese form
  `P/spotcheck/X.md` (per row the value, the sheet, the quoted texts, the verdict boxes and the exact
  `harness part answer-key` command). The same seed and hash give byte-identical files and neither is
  rewritten; neither holds a timestamp. `schemas/examples/answer-key.example.json` is invented.
- `harness part answer-key W --part X --row R --verdict ok|wrong|cannot_tell --by NAME [--correct V] [--text T]`
  and `harness part score W [--answer-key FILE]` (E9b, ADR-0019, C11): bodies of the E6w stubs in
  `part_score.py`. `answer-key` is a locked writer: exit 1 unless the part is `locked`, the row is in
  `parts/X/spotcheck.json` (`row_not_sampled`), that file's `part_hash` is the current one (`spotcheck_stale`) and
  the row names a file; exit 2 for `--correct` missing with `wrong` or given with another verdict. It records the
  verdict in `W/answer-key.json` under the key (part, file, sheet, casefolded mark or subject, field), never a row
  or finding id; a new verdict supersedes the active one, one that repeats it (same verdict, correct value and
  value shown) writes nothing (`written: false`); `--by` is kept as given. `score` is read-only and exits 0
  whatever the `differ` count (1 for a key file that is missing or invalid, or a manifest that is there but
  unusable): per active key `cannot_tell` is
  apart; the expected value is the value shown (`ok`) or the correct one (`wrong`); no `seen` row with a value
  under the key is `missing`; `agree` only when every such row has the same value (`same_value`), else `differ`.
  A part with no manifest, not in the manifest, or without a usable `values.json` gives `missing` for each key,
  with one stderr line. `--answer-key` may name a benchmark copy outside the work folder. Schema `answer-key` 0.1
  gains `kind: answer_key` (additive); `schemas/examples/answer-key-file.example.json` is invented.
  `tests/test_part_actions.py` loses the stub test: no stub is left.
- `harness part chain W --block B` and `harness part review-sample W --part X --seed S [--n N]` (E7, ADR-0019):
  both read-only, bodies of the E6w stubs in `part_sample.py`, stdout per the frozen `$defs` `chain` and
  `review_sample`. `chain` lists the member parts of the block by (order, id) with their `count_plan`,
  `count_schedule` and `piles_per_member` rows by row id (`number`: the value's one number; `addends`: the
  hand-sum terms), the products `count_plan x piles_per_member` per mark and the sums of the mark rows, with no
  comparison; an unknown block, an unusable manifest or a member part without a valid `values.json` is exit 1.
  `review-sample` gives blind prompts: seeded value prompts, plus one `absence` and one `outside_frame` prompt
  when the part has such rows; a prompt names the sheet number and the view (the text of the manifest
  `number_entry` and of the row's `view.heading_entry`, null when none or when the text is font-blocked or not
  printed) and holds no value, cite or entry id. `part_sample.stratified(rows, n, seed, salt, priority=None)` is
  the seeded sampler (a pool of 8 rows or fewer whole, else one row per LISTED field, then a seeded shuffle);
  E9a reuses it.
- `harness part manifest-check`: new problem code `files_entry_unused` (E4a review 2, D2): a `files[]` item on a
  part that is not `no_sheet`, or naming a file that `list-sheets` does not skip (it is read as sheets, or is not
  an input DWG/DXF). One row for each part and file (`part` the holder, `file` the item, `sheet` null), both
  reasons in one detail. The `part-output` schema lists the code; `schemas/examples/` is unchanged.
- `harness takeoff render W (--part X | --all) [--out DIR]` (E8b, ADR-0019): writes `takeoff/<nn>-<part>.md` for
  each part with status `checked`, `reviewed` or `locked` (`nn` = rank of the non-bookkeeping parts by order and
  id), seven fixed sections of Vietnamese text generated from rows, findings, questions, the text index and the
  saved geometry or contents documents (`takeoff_cells`); only the `ai:method` and `ai:reason` slots are the AI's,
  kept from the file on disk (a new slot reads `_(chưa viết)_`). A file whose text is unchanged is not rewritten;
  `--all` removes the files of a part no longer eligible or renumbered. `--part X` of a part that is not eligible
  is exit 1; neither or both of `--part` and `--all` is exit 2. `takeoff` is in `cli.LOCKED_ACTIONS` for `render` and `plan`. New schema `takeoff-output` (`$defs/render`),
  listed in `SCHEMA_NAMES`.
- `harness takeoff plan W [--out DIR]` (E8c, ADR-0019): writes `takeoff/00-plan.md`, fully generated (no AI slot) and
  rewritten only when its text differs. Sections `Kết luận`, `Thứ tự các phần` (every non-bookkeeping part by rank:
  file link only for a `checked`, `reviewed` or `locked` part, main result, confidence and `status_line`; a part
  that is not eligible shows `—` and its values are never read), `Các lô` (the `chặn mọi lô` row is the status
  `project_blocking_ids`; then one `L<nn>` row per part with its open blocking ids, never a non-blocking one, and
  one row per bookkeeping part that holds open blocking ids), `Câu hỏi mở` (blocking first, by id) and `Nguồn`.
  `takeoff-output` gains `$defs/plan`. `TakeoffContext` gains `project_id` and `project_blocking_ids`, read from the
  one status run; `takeoff_cells` gains the public `DASH` and the statuses `reading` (`đang đọc`) and `reopened`
  (`đã mở lại`) in `STATUS_VI`, so `status_line` works for every part status. `takeoff render` and `plan` share the
  `--out` folder rule (exit 2 when it is not a folder).
- `harness takeoff check W [--out DIR]` (E8d, ADR-0019): read-only, the body of the E8b stub in `takeoff_check.py`
  (`takeoff.py` resolves `--out` as for `render` and `plan` and passes it on). One context renders every eligible
  part (with the slots read from its file) and `00-plan.md`; exit 0 when the folder equals that render and the slots
  are clean, 1 with a sorted problem list `{code, file, line, detail}`. Codes: `file_missing`, `file_unexpected`
  (a file of no part, of a part that is not eligible, or under another rank number), `generated_differs` (detail:
  first differing line, expected and found, and the command to rerun), `slot_markers` (a marker missing, doubled
  or out of order, or no body line; the file gets no other check), `ai_slot_empty` (blank or `_(chưa viết)_`),
  `ai_id` (the ids the harness mints; a token equal to a mark or subject of the part's rows is allowed),
  `ai_code` (a backtick), `ai_jargon` (whole word, case-blind) and `ai_number` (a number that no generated
  non-heading line of the file shows). An answer given after render makes `generated_differs` until the rerender,
  which keeps the slots. `takeoff-output` gains `$defs/check`.
- `harness part` gains the surface of six later actions (E6w, ADR-0019): `chain W --block B`, `review-sample W
  --part X --seed S [--n N]`, `conflicts W`, `spotcheck W --part X --seed S [--n N]`, `answer-key W --part X --row R
  --verdict ok|wrong|cannot_tell --by NAME [--correct V] [--text T]` and `score W [--answer-key FILE]`; a bad
  `--seed` (not 0 or more), `--n` (not 1 or more), `--row` (not `R` and 3 digits or more) or a blank `--by` is exit 2.
  Each body is a stub (exit 2, `not built yet (<package>)`) in `part_sample.py`, `part_conflicts.py`,
  `part_spotcheck.py` and `part_score.py`. `conflicts`, `spotcheck` and `answer-key` join `receipt` in
  `cli.LOCKED_ACTIONS["part"]`. `part-output.schema.json` gains the `$defs` `conflicts`, `chain`, `review_sample`,
  `spotcheck`, `answer_key` and `score` (same `$id`, additive).
- `harness part conflicts W` (E6b, C7, ADR-0019): two parts that read one mark, one system or one measurement
  differently become one Vietnamese question that tags both parts (producer `part-conflicts`,
  `part-conflicts-questions.json`), so `harness status` blocks only those parts. Parts are the manifest parts of kind
  member, cross and no_sheet; one without `values.json` is in `skipped_parts` and contributes nothing, an invalid
  one is exit 1 (the part is named, nothing written). `part_value_conflict`: rows with a value (`seen`, `asked`)
  of one (block, mark or subject, field) that two parts read differently (`same_value`); blocking when the field is
  in `part_rules.LISTED`. `part_system_conflict`: `structural_system` findings of two parts with one (file, sheet,
  aspect) and different values (`note_item` never). `part_measure_conflict`: two `measured` findings of two parts
  that share a cited item and differ in value (`cross_check` findings are left out); both are blocking when a LISTED
  row cites either finding. Duplicates (reader questions of two parts with one code, file and sheets; `note_item`
  findings that cite one entry) are listed in stdout, never asked. A conflict no longer raised goes obsolete; the
  questions never enter `part_hash`, and values, findings and reader questions are never edited. `questions.md`
  routes a `part-conflicts` question to its own topic before the code-prefix table.
- Part-conflicts plumbing (E6a, DECISIONS § 6): a seventh question producer `part-conflicts` (`harness part
  conflicts`, document `part-conflicts-questions.json`; the command itself is E6b). `Ledger.sync` copies a
  question's `parts` to the rendered question; `harness status` lists the producer last, `outputs` `n/a`, only the
  engineer's answer closes its questions, and it is no gate-1 reason (a simulated answer to one is none either: `GATE_ONE_PRODUCERS` keeps the role reason to the gate-1 producers; the tagged parts stay blocked through `blocking_open_ids`). `parts[].blocking_open_ids` adds the open
  blocking part-conflicts questions that hold the part (they never enter `part_hash`). New `project_blocking_ids` in
  part mode (the full list, by number): open blocking intake, read-structure and grid-system questions, callouts and
  marks questions that no part lists in `producer_questions`, and reader or part-conflicts questions that hold no
  part; when it is not empty every part is `blocked_by_project`, so no open blocking question sits in no lot.
  questions.md prints a part-conflicts message verbatim, as a reader question. `part_values.same_value(a, b)` is the
  value comparison E6b and E9b use. Schemas (same `$id`, additive): `question-registry` and `status` producer
  enums, `status` `producers` has 7 rows and `project_blocking_ids`, `intake` `parts` description.
- `harness status` shows `parts[]` in part mode (E5b, ADR-0019): when `parts/manifest.json` exists, one row per
  part, in manifest order: `{id, kind, status, hash, stale_inputs[], blocking_open_ids[], blocked_by_project,
  ready}`. `status` and `hash` come from `part_receipts`; `blocking_open_ids` are the reader's open blocking
  questions the part holds (the full list, not cut at 50) plus the open blocking ids its manifest row lists in
  `producer_questions`; `ready` is `locked` with none of them and no project reason. `blocked_by_project`
  is every gate-1 reason except the `reader:` line, plus an open blocking reader question that no part
  holds, so one reader question about one part no longer makes every part unready. A manifest or record that is
  not usable gives `parts: []` and `parts_error` (gate 1 unchanged); a manifest the system refuses to read is exit
  3. `status.schema.json` gains the optional `parts` and `parts_error` (same `$id`, additive).
  `harness status` also gains `parts_project_reasons: [string]` next to `parts` (E5b review 1, D4; absent with
  `parts_error`): the gate-1 reasons that block every part, in gate-1 order, then the line about reader questions
  without a part. `blocked_by_project` stays a boolean; `status.schema.json` (same `$id`, additive) and its
  example show the list.
- Locked-part refusal (E5b-4, ADR-0019): `harness finding add` / `withdraw` and `harness ask` (new, repeated,
  part added), `--withdraw` and `--amend` refuse, exit 1 and nothing written, when a part they would change has a
  latest receipt of kind `locked` (`part_receipts.locked_parts`, not the derived status: a hand edit of
  `values.json` does not unlock it). `--part` and the finding's own part are checked; an amend checks `--part`
  and every part that holds the question. The message gives `harness part receipt W --part X --kind reopened
  --reason "…"`. Unreadable or invalid receipts refuse (exit 1, the file named); another `OSError` is exit 3;
  without a parts manifest nothing is checked.
- Take-off cells (E8a): `takeoff_cells.py`, pure functions for every cell of the take-off files (no I/O, plain dicts
  in, strings out), so a hand edit cannot render run 3's errors C1, M4, M5. `row_confidence` is the lowest
  confidence of the cited findings, the `hand_sum` finding terms and the cited grid systems (none: `chưa có finding`);
  `row_cell` prints a state, `đã cũ (F-…)` for a stale finding and `đã trả lời Q-… (§ 5)`; `axes_token` names an
  unlabelled line from its nearest label (`trục không nhãn (D -6000)`); the trục cell comes from geometry or
  start/end axes only, never from a typed `axes` row; `status_line` lists blocking questions only; `FIELD_VI` and
  `CONF_VI` give the Vietnamese field and confidence labels.
- Part manifest warning `grid_origin_other_block` (E4b, ADR-0019), as the pure module
  `tekla_harness.part_warnings` (wired into `harness part manifest-check`, see below): a plan sheet filed under one
  block whose grid lines up with at least two sheets of another block (same file; one shared axis label at least,
  every shared label within 1 mm, in x or in y) and with none of its own block's other sheets is a probable
  misfiling. Reads `structure/<file>.grids.json` only; sheets listed under two blocks are left out. Sheets
  without a usable plan grid come back as skipped (`no_grids_document`, `no_plan_grid`, `several_plan_grids`,
  `rotated_grid`). `plan_grid()` also keeps, per family, the axes and the first labelled axis (position, offset,
  normal) for the linework rule. "1 mm" is in the unit of the file (answered, else declared, as `harness
  geometry` resolves it); a file without a length unit is skipped as `unit_unknown`, never guessed.
- Part manifest warning `linework_duplicate` (E4b, ADR-0019), in the same pure module (wired into `harness
  part manifest-check`, see below): a plan of one block whose outlines and symbols are a copy of another block's plan
  gave wrong member sizes. Per member part with `layers`, each plan sheet is compared with each plan sheet of a
  member part of another block (same file) on the part's layers: size and centre from the plan grid's origin
  (first labelled axis of each family), rounded to 1 mm, frames (outlines over 20 m) left out. At least 0.90 of
  the larger side in common warns, with both sheets holding 10 items or more; the twin part warns from its own
  pass. Sheets no pair could test are skipped (`unit_unknown`, the plan-grid reasons, `few_items`). One
  `read_geometry` walk per file.
  confidence of the cited findings, the `hand_sum` finding terms and the cited grid systems (none: `chưa ghi nhận`);
  a cited id missing from `findings` or `systems` raises `KeyError`, never a higher confidence. `value_cell`
  (the cell without its field label), `row_cell` and `field_cell` (rows of one field joined ` | `) print a state,
  `đã cũ (F-…)` for a stale cited finding or a stale `hand_sum` finding term, `đã trả lời Q-… (§ 5)` and, on an
  asked or unread row, `đã có trả lời Q-…, chưa cập nhật (§ 5)`; `axes_token` names an unlabelled line from its
  nearest label (`trục không nhãn (D -6000)`), and `item_token` leaves out a family with no labelled axis
  (`tọa độ tờ` when none is left); `positions` is in natural order whatever `PYTHONHASHSEED` and matches marks
  after NFC and casefold; the trục cell comes from geometry or start/end axes only, never from a typed `axes`
  row, and `axes_cell` requires `findings` and `questions`; `status_line` lists blocking questions only; the
  Vietnamese texts are public constants (`FIELD_VI`, `CONF_VI`, `NO_FINDING_VI`, `BLOCKS_EVERY_LOT_VI`,
  `STATUS_VI`) and no cell holds an English word; `hand_sum_text` shows the bare id of a term.
- Part sums (E5a-6): `part_sums.hand_sum_addends(row, findings, marks_doc, entry_text)` returns the
  `(term text, value)` of each `hand_sum` term (`F-012 symbols`, `F-012 items`, `marks K-2`, `T000470`) from plain
  documents, or `[]` when the row has no `hand_sum` or any term is invalid or unknown. `hand_total` shares its
  term arithmetic; `part check` output is unchanged.
- Part check, frame (ADR-0019, E5a): `harness part check W --part X` reads `W/parts/X/values.json` (new schema
  `part-values` 0.1: one row per mark or subject and field, with state `seen` / `asked` / `unread` / `absent`,
  the findings, questions, entries or saved geometry it cites, and an optional `hand_sum`) and prints
  `{command: "check", part, hash, ok, counts, problems: [{code, row, id, detail}]}`, problems sorted by all
  four fields (`hash` is the part hash of `part_receipts`, null when the check stops at `manifest_invalid`,
  `part_unknown` or `input_invalid`). It is read-only (no work lock) and exits 0 ok, 1 any problem (always
  with the JSON on stdout), 2 usage (a part id that does not match the pattern, no work folder or
  inventory.json), 3 an `OSError` other than not-found on the manifest, `values.json`,
  `reader-findings.json`, `reader-questions.json`, `question-registry.json`, `marks.json`,
  `grid-systems.json` or a saved file. A malformed manifest is `manifest_invalid`, a malformed `values.json`
  is `values_invalid`, a malformed `reader-findings.json`, `reader-questions.json`,
  `question-registry.json`, `marks.json` or `grid-systems.json` is `input_invalid` (the file and the first
  schema error in the detail), and a malformed saved file is `cite_unknown`. The row checks are
  `row_duplicate`, `row_state` and `row_outside_part`; the codes of the citations, numbers, hand sums and text
  rules come from `part_cites`, `part_numbers`, `part_sums` and `part_rules` (all 31 codes are in
  `check.PROBLEM_CODES` and the schema enum). `part_values.load_context` reads everything once (manifest, scope of the part and of its
  inputs, rows, findings with `stale`, registry and reader questions, entries of every scope file, marks,
  saved documents). `part-output` gains `$defs/check` and a `command` const in both documents
  (`manifest-check` output now carries `"command": "manifest-check"`; additive, `$id` stays 0.1).
- Part check, numbers (ADR-0019, E5a): `harness part check` raises `number_unbacked` (a standalone number of a
  row's `value`, `findings._numbers`, that equals no number of a cited source: exact for the text of a cited
  entry, finding value or finding entry, within the saved query's `tol` for the `short`, `long` and `diameter`
  of a cited finding's evidence or `cites.geometry`; the `symbols` and the item count back a number only
  exactly, as `findings` has it) and `token_unbacked` (a glued
  token such as `-1.200`, `2Ø16`, `-0,450`, `C30/37`, `24M` that no source text quotes, case-blind; the sign
  counts, so `-0,450` is not backed by `+0,450`). A cited question's `message` and `found` back an `asked` row
  only; a row with a `hand_sum` skips the number check. `part_values` gains `sources(ctx, row)`,
  `glued_tokens(value)` and `backs(source, value)` for the text-rule checks to import.
- Part check, text rules (ADR-0019, E5c): `harness part check` raises the reviewer's mechanical rubric as 14
  codes. Coverage: `sheet_uncovered` (an own sheet with no row and no own finding), `mark_missing` (a plan mark
  or schedule mark on an own sheet that fullmatches `marks_regex` and has no row, case-blind: the regex too),
  `marks_regex_invalid`. Blocking questions on listed values (`part_rules.LISTED`: every `field` but `material`
  and `other`): `listed_needs_blocking` (a row `asked`, `unread`, `absent`, or `seen` on under two source keys
  that cites no blocking question; two keys are two different (kind, file, sheet) sources that back every
  number of the value, a `high` finding, or an agreeing `count_plan` / `count_schedule` pair; a finding's own
  `basis: two_sources` is not read), `listed_question_not_blocking`, `low_without_question`. Claim form:
  `claim_form` (`node:`, `basis:`, `alt:`), `note_item_prefix` (`block:`). `search_unaccented` (a `searched`
  record of quoted terms lacks the unaccented twin of a term with accents, `đ` read as `d`, whether or not the
  twin would have hits), `family_linework_twice`, `family_linework_needless`. Verbatim values:
  `value_not_verbatim` (a `seen` row whose value quotes no cited source text nor the join of its cited
  entries) and `note_quote_unmatched` (a quoted span of a row note that quotes no cited source text); quote
  checks ignore case. A registry entry without `blocking` counts as blocking. No schema change.
- Part check, citations (ADR-0019, E5a): `harness part check` now checks every id a row of `values.json`
  cites in `cites` (the ids inside `hand_sum` terms get the same codes from the hand-sum check): `cite_unknown` (no such finding,
  registry question, entry of the row's `file`, saved geometry or contents document, or item in it; a missing
  saved document gives one problem per cited item), `cite_inactive` (a withdrawn finding, an obsolete
  question), `cite_stale` (a stale finding), `cite_foreign_part` (a reader finding or reader question held by
  neither the part nor an input; untagged reader records are foreign, producer questions always pass),
  `entry_blocked`, `entry_not_printed` and `entry_outside_part` (the entry is in no `text_ids` of a scope
  sheet and no `entry_ids` of a scope cluster; the sheets and clusters of the input parts count). No schema
  change: the codes were already in the enum.
- Part check, grid-system cites (ADR-0019, E5a-5): a row of `part-values` may cite `cites.grid_systems[]`
  (ids `^S[0-9]{3,}$`, unique; additive, `$id` stays 0.1; the example gains a row R007), so a grid or level row
  names the system it was read from. `harness part check` raises `cite_unknown` for an id that is not a
  `systems[].system_id` of `W/grid-systems.json` (file absent too) and `cite_foreign_part` for a known id in no
  `grid_system_ids` of the block of the part or of an input (a part with no block anywhere accepts any existing
  id). The cite is a citation only: it does not satisfy `seen` and backs no number. `load_context` reads and
  validates `grid-systems.json` only when a row cites a system (`PartContext.grid_systems`, last field).
- Part check, hand sums (ADR-0019, E5a): `harness part check` recomputes every `hand_sum` of `values.json`
  (`part_sums`). A term is `{finding, of: items|symbols}` (the number of `evidence.items` of a measured finding,
  or the sum of their `symbols`), `{marks: M}` (the plan marks of `marks.json` equal to M, NFC and casefold, on
  the row's file and sheet) or `{entry: T}` (the one standalone integer of the entry's text). `hand_sum_mismatch`
  when `_numbers(value)` is not exactly `[total]` ("7 pcs" passes, "7 of 12" does not; the detail lists each
  addend); `hand_sum_invalid` for a term that cannot be added (a finding without `evidence`, an item without
  `symbols`, a `marks` term on a row without `sheet` or with no `marks.json`, an entry that is font-blocked or not printed (font-blocked text is quoted, never read), an
  entry text without exactly one integer); `cite_unknown` for a term whose finding or entry does not exist. The ids of the terms get
  the checks of a row cite, with the same codes and detail on `[row, id]`: `cite_inactive`, `cite_stale`,
  `cite_foreign_part` (a hand sum that needs another part's rows lists that part as an input) and
  `entry_outside_part`. With a term problem the total is undefined and no mismatch is raised.
- `harness part manifest-check` raises the three drawing warnings (E4b-1, ADR-0019): `grid_origin_other_block` and
  `linework_duplicate` (`part_warnings.py`, always on; new flag `--input-dir DIR` for a native DXF, as `harness
  contents`) and `revision_from_table` (a `revision` candidate of `sheets.json`, chosen or not, whose text sits
  outside the title-block zone `u >= 0.75 or v <= 0.20` of its sheet). Each warning has an `id` (fields joined by
  `|`); the manifest's `acks[]` clears the warning whose id equals `ack.warning` exactly (`acked`, `ack`).
  New problems: `ack_unmatched`, `ack_duplicate`, `ack_question_unknown` (a question that is no id of
  `question-registry.json`, any status), `order_not_after_input` (a part's `order` not above an input's) and
  `grid_system_unknown` (a block's `grid_system_ids` entry is no `system_id` of `grid-systems.json`; the file
  absent: every listed id; invalid: exit 1). A sheet a warning could not test is in the new top-level `skipped[]
  {code, file, sheet, reason}`, never a failure. Exit 0 means no problem and every warning acknowledged, and
  `ok` is true exactly then; an unacknowledged warning is exit 1; `read_geometry`'s own errors keep their codes
  and an `OSError` is exit 3. `part-output` `$defs/manifest_check` gains the warning items, `skipped` and the
  codes (additive, `$id` stays 0.1); the `acks` description of `parts-manifest` says what the command does with them.
  A file whose unit answer cannot be read (answers ledger unreadable, or active answers with no single valid unit)
  gets no unit, not its declared one: the two measuring rules skip it as `unit_unknown` and the check raises the new
  problem `unit_answer_unread` (the file and the warning text; exit 1, no ack clears it). The shipped
  `parts-manifest.example.json` now acks warning ids, not codes. `part-output` gains the code `unit_answer_unread`
  (additive).
- Spacing evidence (ADR-0019, E10c): `harness grid-system W` writes `spacing_evidence[]` in every direction of
  every system in `grid-systems.json` (proposals and engineer-given systems; stdout unchanged): one row per
  spacing with `status` `dimension_agrees` (a typed number equals the spacing), `dimension_measured` (only the
  default text, which is the axis geometry itself: no second source), `dimension_differs` or `no_dimension`,
  and the counts, distinct values and up to 3 refs of the dimensions between exactly its two axes (labels
  case-blind, DIMLFAC applied, drafting tolerance). An overall dimension is no evidence for one spacing. The
  schema change is additive (`$defs/spacing_evidence`, optional `direction.spacing_evidence`, `$id` stays 0.1).
- `harness contents --dims` (E10b, ADR-0019): attaches the linear dimensions drawn on each rectangular outline
  and says whether the printed value agrees with the drawn size (motivation: pile caps copied from another
  building drawn 1700 wide while their dimension prints 3200). A dimension of dimtype 0 or 1 within `--mark-radius`
  (no new radius flag) measuring along a side within 1 degree attaches `edges` (both ends on the two edges, within
  `--tol`) or `centred` (neither end on an edge, middle at the middle of the side, the longer of dimension and side
  at most twice the shorter); an axis-to-edge dimension never attaches. `edges` wins over `centred`, then the
  smallest gap; an equal runner-up makes it ambiguous (counted, attached to none). The printed value is the typed
  number of an override (a legacy-font text the gate blocks is unusable) or the measured length times DIMLFAC;
  `agrees` = |printed - side x DIMLFAC| <= tol x DIMLFAC. Block content is placed by its INSERT (handle null; a
  scaled INSERT, which would print the definition's value, is unusable; a mirrored one attaches in world
  coordinates). Output with the flag: `query.dims`, per outline `printed_dims`, per summary row `printed_dims`
  (`agree` / `disagree` / `none`, `values`), top-level `dims` counts and a warning naming the outlines that
  disagree (and one counting the non-rectangles, which get none). Without the flag the output is byte-identical
  and documents saved before still validate (all new keys optional; schema `$id` stays 0.1).
  `geometry.read_geometry(..., dimensions=True)` keeps each region's DIMENSIONs (`GeometryRead.dims`).
- Part tag (ADR-0019, E2): `harness finding add|withdraw --part ID` and `harness ask --part ID` (also with
  `--amend` and `--withdraw`) say which part (block x member family) a reader finding or question belongs to.
  The id matches `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$` (exit 2). Without `<work>/parts/manifest.json` the flag is
  optional and the id is stored as `part` on the finding in `reader-findings.json` and as `parts[]` (unique,
  arrival order) on the question in `reader-questions.json`; with the manifest it is required (exit 2) and
  must be listed in `parts[].id` (exit 1). Anything at `parts/manifest.json` that is not a usable manifest (a
  directory, a dangling symlink, bad UTF-8 or JSON, a wrong shape) is exit 1 and the message names the file in
  plain words; a path the operating system refuses to check or read (permission, I/O) is exit 3 (`parts.manifest_present`
  is the one test for part mode, with `lstat`, so nothing present is taken for "no manifest"). `finding withdraw`
  of a finding that has a part, and `ask --amend` / `--withdraw` of a question that has parts, need `--part` to
  be that part (exit 1). The same finding in another part is a new finding; `ask` on an existing key with a
  part the question does not hold appends it (status `already_asked_part_added`, stderr `already asked, part
  added`); a raised question's output (`new`, `already_asked`, `already_asked_part_added`) carries `parts` once
  a `--part` is given, and `finding list` shows `part`. `ask --withdraw --part A` on a question that other parts
  also hold removes only `A` from `parts` and keeps it open (status `part_removed`, stdout carries the remaining
  `parts`, stderr `Q-id: part removed`); when `A` is the last part the question is withdrawn as before. A sheet
  keeps one active class whatever the part, and the refusal names the part that owns it (`withdraw` needs it).
  A producer's code is refused (exit 2, naming the producer) before `--part` is asked for. `--part` with
  `--supplement` or `--withdraw-supplement` is exit 2. Schemas `reader-findings` (optional `part`) and `intake`
  (optional `parts` on a question, the reader-questions document inherits it; `parts` has `minItems` 1 and
  `uniqueItems`), both still 0.1, pre-release, no `$id` bump; examples updated.
- Part mode, manifest check (ADR-0019, E4a): `harness part manifest-check W` is a read-only command (no work
  lock; `part` is on the per-action locked list with no locked action) that checks `W/parts/manifest.json`
  before any part reader starts and prints `{ok, sheets: {total, covered}, parts, problems: [{code, part, file,
  sheet, detail}], warnings: []}`, exit 0 when ok, 1 otherwise (a missing manifest, a path that is not a
  regular file, bytes that are not strict JSON (duplicate key, NaN, a BOM, bad UTF-8) and a schema failure are
  each one `schema` problem, with no absolute path in its detail), 2 for a missing work folder, no
  `inventory.json` or a DWG/DXF without its `structure/<file>.sheets.json` (run `harness read-structure`;
  nothing is blamed on the manifest), 3 when the operating system refuses to check or read the manifest
  (`parts.manifest_present`, the one rule) or an input file (a message on stderr, no JSON). The manifest path
  follows `parts.py`. Parts require `order`. Problem codes: `schema`, `duplicate_part_id`,
  `sheet_unknown`, `sheet_uncovered`, `cluster_uncovered`, `cluster_in_two_parts`, `cross_part_missing`,
  `bookkeeping_part_missing`, `input_unknown`, `input_cycle`, `block_unknown`, `sheet_in_two_blocks`,
  `part_over_cap` (more than 4 sheets, or more than 1,500 printed entries summed over the part's sheets),
  `table_outside_part` (a table's sheet is not in the part's `sheets[]`, or its cluster not in the part's
  `clusters[]`), `cluster_unknown` (a cluster in `clusters[]` or in a table that `unassigned-clusters` does not
  report), `entry_unknown` (a `number_entry`, `title_entry`, `heading_entry` or table `header_entries` id that
  the sheet, or for a table in a cluster the cluster, does not hold), `duplicate_block_id`, `part_kind_mismatch`
  (a fixed id with another kind, a non-fixed id that is not a member or a cross split, a member id that is
  neither `<block>-<family>` nor starts with `<block>-<family>-`) and `file_unread` (a DWG/DXF that
  `list-sheets` skips, for lack of a text index or an unreadable one, unless a `no_sheet` part names it in
  the new optional `files[]`) and `record_part_unknown` (a reader finding's `part` or a reader question's
  `parts[]` entry that the manifest does not list, one row per part naming the record ids, `file` and `sheet`
  null; withdrawn findings do not count; the detail names `harness finding withdraw … --part X` and
  `harness ask --withdraw … --part X`; read only when the manifest passed its schema; a record file that is not
  readable JSON of its schema is exit 1, one the operating system refuses is exit 3, both naming the file with
  no JSON on stdout). A cross part over the cap is split as `<fixed id>-<letter>` with kind `cross`
  and `split_of` the fixed id; such a part satisfies `cross_part_missing`. `sheet_unknown` is raised for the
  sheets of every part, bookkeeping and `no_sheet` included (they stay exempt from coverage, cap and blocks).
  A table on a sheet that `list-sheets` does not print is `sheet_unknown`. The text index and the sheets document of each file are
  loaded once (new `sheet_text.file_clusters`, the per-file body of `unassigned_clusters`, whose output is
  unchanged). The example's entry ids now name entries of the test fixture.
  Sheets are (file, sheet id) pairs of `list-sheets`, clusters are (file, sheet id, side) triples of
  `unassigned-clusters`. New schemas `parts-manifest` (the scout's manifest; `additionalProperties: false`
  everywhere, no value field; example `schemas/examples/parts-manifest.example.json`) and `part-output`
  (`$defs.manifest_check`; one entry per `part` command), both 0.1.
- Measured findings (tool T24): `harness geometry` and `harness contents` take `--save`, which writes the exact
  stdout document to `<work>/geometry/<command>-<sheet|bbox|all>-<hash12>.json` (hash12 = first 12 hex of
  sha256 over the drawing's inventory sha256 and the canonical JSON of the query: the same query gives the same
  file) and prints `saved: <path>` on stderr; with `--save` the command takes the work lock (ADR-0011,
  `cli.LOCKED_WHEN_FLAG`), without it nothing changes. New finding kind `measured`:
  `harness finding add <work> --kind measured --file F [--sheet S] --source geometry/<name>.json --items G-...
  --value "..." [--field quantity=count|size|position|level|spacing] [--entries ...] [--question Q-...]`
  records a value taken from vector geometry (pile count per cap, cap size, axes that carry caps) with
  `evidence` {source, sha256 of the saved file, command, query, items}. The document must be a saved
  geometry or contents document of `--file`, valid against its schema, named for the drawing's current
  inventory sha256, cover `--sheet`, and list every item id (geometry items need `--detail`). Confidence is
  `medium`, lowered by `--confidence` or a cited entry; `--entries` is optional. A `cross_check` may cite one
  entry plus `--source`/`--items` instead of two entries. `finding list` shows the evidence and marks a
  finding `stale` when its saved file changed or is gone. Schema `reader-findings` (still 0.1, pre-release, no
  `$id` bump): kind `measured`, `evidence`, `entries` may be empty only for `measured`; example updated.
- `harness contents <work> <file> --sheet ID --outline-layer L ... --circle-layer L ... [--max-long N]
  [--marks REGEX] [--mark-radius R] [--detail] [--max N] [--tol T] [--input-dir DIR]` (tool T22, read-only, no
  work lock, built on `harness geometry`): for each closed outline of one plan sheet (a pile cap, a column
  stub) its size, the symbols (pile circles, collapsed to unique centres: concentric circles are one) whose
  centre lies inside it (point in polygon, boundary within tol counts), the mark texts assigned to it (each printed entry
  fully matching `--marks` goes to its one nearest outline within `--mark-radius`; an entry equally near two
  outlines is listed in `marks_ambiguous`, one with no outline in range in `marks_unassigned`; legacy-font-blocked
  entries are not used) and the nearest axis
  of each grid family of the sheet (label and signed offset along the family normal, from `grids.json`). A
  `summary` groups outlines by layer, size and symbols inside, with `marks_seen` and `unmarked`: a mark is never
  copied to an outline that holds none. Outlines longer than `--max-long` (frames)
  are dropped with a warning. New schema `contents` (`$id` `urn:tekla-harness:schema:contents:0.1`) with an
  example.
  Review-1 fixes (T22-REVIEW-1): axes come only from the grid groups of the sheet whose bbox strictly contains the
  outline centre in the same space, each entry names its `group_id` and carries `nearest_unlabelled_offset`
  (C1); symbols merge by geometry's own dedupe key (M1); the point-in-polygon test uses the true outline ring,
  bulges flattened, no vertex cap (M2); a mark is measured from the middle of its text and ties are relative
  (M3); a mark inside nested outlines goes to the innermost (M4); `--tol`, `--max-long` (20 m) and
  `--mark-radius` (3 m) default from the drawing unit like geometry (M5); warnings for a mark seen on two
  summary rows or an outline holding two marks (m3), for items in other spaces (m6) and for unused circles on
  outline layers; leader marks are measured from the text, as the text index has no leader vertices (m9).
  The contents outline `id` pattern is the shared geometry `item_id` definition.
  Review-2 fixes (T22-REVIEW-2): a mark is placed at the centre of `sheets.text_box` of its entry, whatever
  the TEXT alignment or MTEXT attachment (M1; the middle estimate of review 1 is gone, width is 0.7 x height);
  an outline another in-range outline holds (a column stub in its cap) no longer competes in the nearest-outline
  tie, so a cap mark below the cap is not ambiguous with its own stub (M2); a mark on an edge of an outline
  (within tol) is held by it, on every edge, the innermost holder winning (m1); a pile exactly tol outside a
  box edge counts the same on all four edges, tested (m2); each outline has `invisible` and each summary row an
  `invisible` count, with one warning when an outline or symbol carries the invisible flag (m3; new required
  fields of the pre-release `contents` schema, no `$id` bump).
- `harness geometry <work> <file> [--sheet ID ...] [--bbox X0 Y0 X1 Y1] [--layer L ...] [--detail] [--max N]
  [--tol T] [--input-dir DIR]` (tool T21, read-only, no work lock): reads the linework of one drawing, one walk
  of the file. CIRCLEs (piles) and closed or first-equals-last LWPOLYLINE / 2D POLYLINE outlines (caps,
  columns) are grouped per sheet (or model-space region) by layer and size; a rectangle also gives short side,
  long side and the angle of the long side, so a rotated cap groups with an unrotated one. Identical items
  collapse into one with `copies`; LINE, ARC, HATCH and open polylines are only counted per layer; items on an
  off or frozen layer are counted as `hidden`. Layer 0 inside blocks takes the layer of the placing INSERT
  (nested); every coordinate is converted to WCS (mirrored INSERTs). Known gap: outlines drawn as loose LINEs.
  New schema `geometry` (`$id` `urn:tekla-harness:schema:geometry:0.1`) with an example.
  Additive, no `$id` bump (pre-release): every item names its `space`; shared definition `$defs/item_id`;
  bulged outlines keep their flattened ring; library function `read_geometry` (used by `harness contents`).
  Review fixes (T21 review 1, schema still 0.1): INSERTs on a frozen layer hide their whole
  content; the invisible flag (group 60) hides nothing but is reported (`invisible` per layer, group and item,
  one warning); hatches and splines are placed by their extents (`unplaced` counter, warning when none); a full
  ratio-1 ELLIPSE is a circle, other ELLIPSEs and SPLINEs are counted (`ellipses`, `splines`); a donut is a
  circle; the default `--tol` is 1 mm of the answered or declared unit (`query.tol` reports it); closed-flag
  polylines keep all vertices; angles never reach 180 and a square reports its angle modulo 90; dedupe cells no
  longer split near-identical copies; ids include the space; bulge outlines are sized by their arcs; ARCs are
  placed by their mid point; `--sheet` is repeatable.
- `harness render <work> <file> (--sheet ID | --bbox X0 Y0 X1 Y1) [--tiles COLSxROWS] [--layer L ...] [--max-px N]
  [--no-overlay] [--out-dir DIR] [--input-dir DIR]` (T23, ADR-0018; read-only on the work folder, no lock, writes
  only PNGs): draws one region of a drawing's model space (ezdxf SVG backend, rasterised by resvg-py) on a dark
  background with a margin of ticks in drawing units, long edge <= 1568 px and area <= 1.15 MP (about 1.5k image
  tokens). stdout is the new schema `render` (`$id` urn:tekla-harness:schema:render:0.1, with an example): per
  image the path, the requested region and the pixel to drawing transform. Only the region is drawn (entities
  whose box misses it are skipped, and counted); `--layer` filters on the effective layer. Paper-space sheets
  are refused (exit 2). New runtime dependencies `resvg-py` and `pillow` (ezdxf's drawing frontend imports it).
  Review-1 fixes (the schema `$id` stays `0.1`, unreleased): the pixel to drawing transform is exact to 0.12 px
  (the SVG page is laid out at 10 px per mm, every pixel an exact page step; it drifted up to 4 px on elongated
  regions); an XLINE or RAY is clipped to the region and drawn (never pruned, nor an INSERT that holds one);
  an INSERT on a frozen layer hides its whole content, as `harness geometry` counts it; `--max-px` is capped at
  1568 (`query.max_px` has `maximum`); what ezdxf prints becomes a warning, so stdout is the document only;
  y labels are never cut (the left margin widens, a label that cannot fit is left out and reported); new
  `images[].entities_invisible` (required; ezdxf does not draw group 60 = 1, `harness geometry` counts them);
  `entities_drawn` counts what ezdxf drew; the file name carries the drawing's inventory sha256; an unknown
  `--layer` name is a warning; a failure inside ezdxf is exit 1; no temporary PNG is left after a failed write.
  Review-2 fixes (still `0.1`): the inner SVG keeps `preserveAspectRatio="none"`, so a sliver whose drawn short
  side is a few pixels keeps the 0.12 px transform (it was 0.28 px); the temporary PNG has a name of its own per
  call (two identical renders at once both succeed); an XLINE or RAY that misses the region is no longer counted
  in `entities_drawn`; the invisible-flag warning of `render` and `geometry` now says these are mostly hidden
  visibility states of dynamic blocks (it no longer blames the DWG converter); the left-margin cap is a quarter
  of `--max-px`, as documented; new tests for the invisible ATTRIB and invisible-edge 3DFACE, hidden-layer,
  xref and top-edge cases. Known limit: the dash pattern of an XLINE or RAY starts at the edge of the clip box,
  so dashes may shift between tiles (positions of solid geometry are exact).
- `harness unassigned-clusters <work> [--file F]` (read-only, no work lock): assigns the printed text that lies
  outside every sheet frame to the nearest frame whose x range (below/above) or y range (left/right) holds it,
  no distance threshold; one cluster per file, frame and side, the rest in a `sheet_id: null`, side `none`
  cluster. Does not decide whether a cluster continues the frame's table. `sheet-text.schema.json` (`$id` still
  `0.1`): new `kind` `unassigned_clusters`.
- Part receipts, read side (ADR-0019, E5b): new module `part_receipts` and schema `part-receipts` 0.1
  (`parts/<X>/receipts.json`, an append-only list of `checked` / `reviewed` / `locked` / `reopened` receipts, each
  with the part hash, time, tool version, the review, the reason or the inputs' hashes its kind needs).
  `part_hash(work, manifest, X)` is the sha256 of the canonical JSON of the part's manifest row, its active and
  withdrawn findings, its reader questions and the bytes of `values.json` and `notes.md`; an answer, an
  amendment's history, the other parts a shared question lists and `decoded_by` are not in it, and
  part-conflicts questions stay out. `read_receipts` (absent is `[]`; an unusable file is `ReceiptsInvalid`,
  exit 1; any other `OSError` is exit 3), `part_status` / `PartStates` (`reading`, `checked`, `reviewed`,
  `locked`, `reopened`, `stale_input`, `receipts_invalid`; an input cycle is `stale_input`) and
  `locked_parts` (the ids whose latest receipt is `locked`, for the write refusal) read it. `harness part
  check` prints `hash` (null when it stops at `manifest_invalid` or `part_unknown`); `part-output`
  `$defs/check` requires it (additive, `$id` stays 0.1). The `receipt` action, `harness status` parts and the
  write refusal follow in the next packages.
- `harness part receipt W --part X --kind checked|reviewed|locked|reopened` (ADR-0019, E5b): appends one receipt to
  `parts/<X>/receipts.json` (`n` 1, 2, ..., UTC `at` from an injectable clock, validated against `part-receipts`
  before an atomic write) and prints `{command, part, kind, written, receipt, refused, problems}`. Exit 0 written
  or already recorded (`written` false: the latest receipt has the same kind and hash, and for `reviewed` the
  same round, review file and verdict, for `locked` the same input hashes), 1 a failed precondition (nothing written; `problems` are `part check`'s), 2 usage
  (a flag of another kind, a missing `--review`/`--round`/`--verdict`, an empty `--reason`, `--round` < 1), 3 the
  system refused a file (a receipt or output that fails its own schema is a bug: exit 1 "internal error"). `checked` and `locked` run `part check`; `checked` is refused on a locked part; `reviewed`
  needs the regular file `parts/X/review/round-N/review.md` (its sha256 is stored) and a `checked` receipt on the
  current hash after the last `reopened`/`locked`; `locked` needs the latest `reviewed` receipt likewise to be a `pass` and every
  input part `locked` (their hashes are stored); `reopened` needs a locked part and a reason. The action is a
  locked action (`cli.LOCKED_ACTIONS["part"]`: waits for the work-folder lock like every writer). `part-output`
  gains `$defs/receipt` (additive, `$id` stays 0.1).
- Tool wave 4 (FP3): an ATTRIB left out by no callout rule, whose (space, layout, block name, tag) also
  occurs in an INSERT that `callout_part_ids` groups as a rebar callout, stays a plan mark and carries the
  optional `possible_rebar_number` object in `marks.json` (`marks.schema.json`, `$id` stays 0.1; new
  question code `mark_possible_rebar_number` in `question_counts`; the object carries the evidence text,
  the `TAG=value` trigger that made the evidence INSERT a callout, and its space, layout and sheet).
  `marks` raises one blocking question per (file, block name) listing the tags, with one ref per distinct
  evidence ATTRIB and then the flagged marks. Block names pair case-insensitively; anonymous and dynamic
  blocks (`*U12`) are a known limit (their generated names do not pair, effective names are not resolved).
  Matching is unchanged until answered (answer handling not done yet).
- SessionStart hook `handoff_reminder.py` (sources `startup` and `clear`): reads the open rows of
  `.handoff/INDEX.md` in the main checkout (found from a worktree too) and tells Claude to ask the
  engineer which multi-session handoff to resume before any other work; a row is removed only after the
  engineer confirms its topic is cleared (AGENTS.md `/handoff` row). Never blocks session start.
- Step 0 foundation: repository layout, `AGENTS.md` / `CLAUDE.md`, ADRs 0001–0004.
- Claude Code project config: Vietnamese replies, permission rules, plugins
  (Karpathy guidelines, pyright-lsp, csharp-lsp).
- Five subagent definitions: `doc-reader`, `planner`, `builder`, `verifier`, `reporter`.
- `guard_tekla_write.py` PreToolUse hook: only `builder` may run `tekla-cli` write commands;
  unknown subcommands are treated as writes (fail closed).
- `session_env_check.py` SessionStart hook: reports remote session, missing `tekla-cli`, Python version.
- JSON Schemas v0: `spec`, `project-state`, `read-log`, shared `common` (provenance, confidence).
- `tekla_harness` CLI: `harness validate`, `harness env-check`.
- CI on Windows and Ubuntu: ruff, pyright, pytest.
- Step 1 S1: `harness detect` (format from file bytes, DWG version, sha256, extension mismatch
  warnings) and the `readlog` builder (timed attempts, refuses silent failures, validates
  before writing).
- Step 1 S2: `harness dwg2dxf` — ODA File Converter, then LibreDWG `dwg2dxf` (ADR-0005).
  Success requires a DXF that ezdxf opens; fallback caps confidence at `medium`; no converter
  at all exits 3. Runtime dependency `ezdxf` (MIT) added: the DXF reader for all later slices.
- Step 1 S2b: per-project read cache (ADR-0006, ADR-0008). Content-addressed blobs plus an
  action cache; key = SHA-256 over a domain tag and canonical JSON of input digest, converter
  chain by content digest, argument templates, ezdxf version and code digest. Every
  read is verified; corrupt or inconsistent entries are discarded; only clean successes (no
  failed attempt) are cached; the input is snapshotted once; a hit replays
  converter, confidence cap, attempts and warnings. `harness dwg2dxf --cache-dir … [--refresh]`.
  New schema `cache-entry` (`urn:tekla-harness:schema:cache-entry:0.1`) and example.
- Step 1 S3: `harness read-dxf` / `probe_dxf` — deterministic DXF probe (units from `$INSUNITS`
  only, never defaulted to metres; layouts, layers, blocks, xrefs, text styles, legacy Vietnamese
  font hints, unreadable objects, dimension text-override audit, scales) with open questions.
  New schema `dxf-probe` (`urn:tekla-harness:schema:dxf-probe:0.1`) and example.
  Hardened after independent review: `$INSUNITS` accepted only as an integral code 0..20; header
  units never `high` (`units_confirm`), lowered to `low` with blocking `units_conflict`
  (`$MEASUREMENT`) or `units_suspect` (median modelspace linear dimension outside 0.01 m..100 m);
  angular dimensions gated on `DIMAUNIT`, linear on `DIMLUNIT`; group 42 cross-check; dimensions in
  block definitions audited; non-finite numbers never emitted (strict JSON); null handles for
  R12-era files; dynamic-block inserts attributed to their source block; `section_errors` and
  `status: partial` instead of a crash. Still `0.1`: not yet released.
  Integration pass: legacy-font hints now come from `encoding.font_hint(style name, font file)` only
  (the same call `extract_text` makes), one row per style with the matched fields listed
  (`matched`), `capital_font` recorded per style and per hint, and the old family, bigfont and
  `vni_` / `vni ` rules are gone; `probe_dxf(path, converter, xref_dir=None, knowledge=None)`
  looks xrefs up in `xref_dir` (the original drawing's folder for converted files); new
  non-blocking questions `font_encoding_proposed` and `font_encoding_conflict`; `handles_reliable`
  and `num` are public. Schema `dxf-probe` changed (still `0.1`).
- Step 1 S4: `harness intake <input_dir> --out <work_dir> --project-id <id>` / `run_intake` — one
  deterministic command chaining detect, `dwg_to_dxf` and `probe_dxf` over a folder. Writes
  `read-log.json`, `inventory.json`, `questions.json`, `probe/<path>.json`, `text/<path>.json`
  (the text index of every probed DXF), `converted/<path>.dxf`; never writes the input folder; exit 2 if the work folder is inside it, 3 if a DWG exists and no
  converter is configured (nothing written). One blocking `units_confirm_all` question lists every
  DXF; other probe questions are grouped by code (50 refs max, true count kept); formats without a
  reader (pdf, image, docx, xlsx, other) are `unreadable` with a blocking `no_reader_implemented`
  question. Inventory rows carry a text summary (entries, by encoding, low-confidence count) and
  `text_index`; a non-blocking `encoding_unknown_non_ascii` group lists the text styles holding
  non-ASCII text of unknown encoding; xrefs of a converted DWG are looked up beside the original DWG;
  a malformed knowledge table is exit 1 and nothing is written. Probe and text-index documents record
  each file by its path relative to the input folder (a DWG's text index names the DWG), so no output
  names the absolute input folder. New schema `intake`
  (`urn:tekla-harness:schema:intake:0.1`, kinds `inventory` and `questions`) and examples. `harness dwg2dxf` now prints `stderr_error_lines`,
  `stderr_warning_lines` and `stderr_tail`.
- Step 1 S5: `extract_text` / `harness extract-text <file.dxf> --out <text-index.json>` —
  deterministic text index of one DXF (stdout is a small summary, the index goes to the file; exit 1
  when the index is invalid or the file unreadable, 2 usage, 3 environment). Every TEXT, MTEXT, ATTRIB (tag, owning block, insert handle), MULTILEADER text and
  DIMENSION override text in modelspace and layouts, plus the same inside INSERTed blocks
  (recursive via `virtual_entities()`, `block_path`, depth limit 16 and cycle guard, both counted).
  ATTDEFs are listed as definitions only. Per entry: space/layout/coordinate frame, effective layer
  and state, style and font file, WCS position (OCS and alignment point handled), raw / plain /
  decoded / display text, `%%` special codes, decode record (encoding from code-point evidence,
  font names or an approved knowledge row, MTEXT runs split at inline `\F`/`\f` fonts, case and
  NFD flags), confidence, provenance
  (`sheet` is `unknown`, `method` `dxf_entity`/`dxf_dimension_text`). Legacy TCVN3/VNI text is
  converted before `%%c`/`%%d`/`%%p` are expanded; `\U+XXXX` escapes are decoded first. Per-entity
  failures give `status: partial` with the entity listed. New schema `text-index`
  (`urn:tekla-harness:schema:text-index:0.1`) and example. `extract_text(..., source=...)` sets the
  recorded `file.path` and every `provenance.file` (intake passes the input-relative path; the CLI keeps
  the path as given).
  Unicode evidence: a Vietnamese letter or tone mark that single-byte legacy text cannot hold
  (U+0102/0103, U+0110/0111, U+01A0/01A1, U+01AF/01B0, U+1EA0-U+1EF9, combining U+0300/0301/0303/
  0309/0323) proves the run is Unicode whatever the font (`decode.source` `codepoint_evidence`,
  confidence at most `medium`; flag `unicode_evidence_contradicts_font` when the font said TCVN3/VNI);
  judged on the text as the file's code page sees it, so a cp1258 file's view of legacy bytes is not
  mistaken for Unicode. U+00D0 (Eth) inside Vietnamese Unicode text is flagged `eth_for_d_stroke`,
  never replaced.
- Step 1: knowledge table mechanism (ADR-0006 layer 2): `knowledge/font-encodings.csv`
  (`pattern,applies_to,encoding,capital_font,status,evidence,source,decided_by,decided_on`),
  `knowledge/README.md`, `tekla_harness.knowledge` (load and validate; a malformed table raises,
  exit 1). Only `approved` rows change behaviour, and only when `encoding.font_hint` said unknown
  (text style runs, not inline MTEXT fonts): `decode.source` `knowledge_table` with the row pattern in
  `decode.knowledge_patterns`; approved rows that disagree leave the style undecided (flag
  `knowledge_conflict`). `proposed` rows only raise a question that shows their evidence. Seeded with
  three proposed rows for exact font files (`VHARIAL.TTF`, `vntimeh.shx` -> tcvn3, `vn_vni.shx` ->
  vni), each with evidence and counter-evidence from local samples (the first draft's `VH*.TTF` and
  `vn*.shx` wildcards also matched VNI fonts such as `VHELVCN.TTF` and `vn_vni.shx`). Packaging the folder into the wheel needs a `pyproject.toml` force-include.
- Step 1 item 5 (RTI-0001, RTI-0003): first structural extractors, library functions on a DXF plus
  its text index (sha256 checked; CLI: see the next entry). `sheets.extract_sheets`: sheet frames found as
  axis-aligned closed rectangles (top level or inside INSERTs, world coordinates; aspect 1.2..1.8,
  >= 5 texts, short side >= 40 text heights; inner borders merged, containers dropped), layouts with
  content as sheets, viewport windows map model space to layout sheets; every text assigned to a
  detector sheet id (`model#01`, `<layout>#01`) or unassigned; title-block candidates only from ATTRIB
  tags / `label: value` (medium) or label adjacency / lower-right sheet-code pattern (low), never from
  frame-block template text; questions for missing, conflicting and duplicate sheet numbers, missing
  revisions, identical sheet content. `grids.extract_grids`: bubbles = circles holding one axis label,
  paired with long collinear lines; views by crossing lines; families by direction with spacings,
  dimension evidence (override vs drawn), cross-view/cross-sheet consistency, skew, non-orthogonal,
  duplicate/missing/mixed labels, unlabelled grid-layer lines; Tekla coordinate-string PROPOSAL per
  family (`0 3*6000`) in declared drawing units, never converted; Tekla X/Y assignment and gate-1
  confirmation always asked. `levels.extract_levels`: signed level values in metres as written
  (forms bare/prefixed/labelled/embedded, level-symbol blocks), grouped values, derived storey
  heights; questions for name conflicts, out-of-range values, single occurrences, missing datum and
  finished vs structural level (always). New schemas `sheets`, `grids`, `levels`
  (`urn:tekla-harness:schema:<name>:0.1`) and synthetic examples.
  Hardened after independent review (schemas changed, still `0.1`). Grids: axes, spacings and proposals
  are never `high` (reserved for an engineer answer at gate 1); each spacing carries `evidence`
  (`dimension_adjacent` / `dimension_span` / `other_view`, `agrees`, `independent`, `ref`): an overall
  dimension is span evidence only, a view on the same sheet, a copied sheet (duplicate_of or >= 90 %
  identical texts) or the same block is not independent; disagreeing evidence still makes a spacing low
  with a blocking question. A circle holding other text besides its label is not a bubble
  (`summary.bubbles_other_text`); labels `1A`, `A1` are accepted; offsets are measured at line midpoints;
  'not parallel' is an end-to-end drift above half the rounding step; family directions are circular
  (median angle); collinear same-label pieces join only within 8 radii; new blocking
  `grid_axis_layer_mismatch` (axis off the family's majority layer/linetype) and
  `grid_label_order_nonmonotonic`; one compared spacing is never `scaled` (it hid mismatches as
  non-blocking); differences up to 2e-4 of the spacing are status `drafting_tolerance` with non-blocking
  `grid_spacing_drafting_tolerance` (heuristic); `question_counts` gives the true count per code; the
  bucket search is bounded (a 200 m circle no longer takes 20 s). Sheets: without title-block evidence a
  frame needs 60 text heights or the size of an accepted frame (schedule tables are not sheets); a
  container is dropped only when its inner frames are sheets themselves, else blocking
  `sheet_frame_ambiguous`; field ATTRIBs count only on the title block (frame insert, multi-field insert
  or near a field label); any disagreeing candidate is a `title_field_conflict` and nothing is chosen.
  Levels: medium only next to a level symbol (three decimals alone are low); level symbol = isosceles
  triangle with a horizontal base, height 0.3-1.0 base, no circle/arc (north arrows excluded); storey
  words matched with diacritics; `+-` / `+/-` read as ±; `mm` / `%` values and a spaced sign after a
  name are not levels; `occurrences` ignores copied sheets; storey heights only between named storeys,
  else low with blocking `level_storey_selection`; new blocking `level_negative_storey`;
  `question_counts`.
- Step 1 item 5 CLI: `harness extract-sheets <dxf> --text-index <t> --out <sheets.json>`,
  `harness extract-grids` and `harness extract-levels` (same plus `--sheets <sheets.json>`): stdout is a
  small summary, the full result goes to `--out` and is validated first; a text index or sheets document
  built from another file is exit 1 (sha256 named in the message), a missing input file exit 2.
  `harness read-structure <work_dir>` runs the three over every DXF that `harness intake` probed
  (native DXF, or `converted/` for a DWG), reading the existing text index: writes
  `structure/<path>.{sheets,grids,levels}.json`, `structure-questions.json` (intake schema kind
  `questions`, one question per code, blocking flag and file, refs carry `file`, detector `sheet`,
  `where`, `found`, at most 50 per question with the true `count`; ids and keys: see "stable question
  ids" below) and
  `structure-summary.json` (new kind `structure_summary` in the intake schema: per file the sheet count,
  title-block sheet numbers by confidence, grid families with labels and Tekla coordinate-string
  proposal and confidence, levels with counts, question counts, warnings; records the sha256 of the
  inventory it was built from). Never modifies `inventory.json` / `questions.json`; exit 2 without them
  or without `question-registry.json`;
  files with nothing to read (not DXF/DWG, no DXF produced, DXF did not open) are skipped with a logged
  reason; a work folder that disagrees with itself (DXF changed since intake, missing or invalid text
  index, path leaving the work folder) is exit 1 with nothing written. Intake schema changed (still
  `0.1`): optional `sheet` on a question ref, kind `structure_summary`. Consolidated `count` (and per-file question counts) are the
  true totals, including questions an extractor counted but did not list. `read-structure --input-dir
  <input_dir>` is required when the inventory lists a native DXF (exit 2 without it), because work-folder
  documents record files by their input-relative path only.
- Reader tools for the `doc-reader` agent, so it never writes ad-hoc scripts (read-only over an intake
  work folder, no new dependency, new schemas `sheet-text` and `callouts` with synthetic examples).
  `sheet_text.list_sheets(work_dir)`: per file and sheet the detector id, printed sheet number with its
  confidence (or null), frame bbox, text count and up to five title-like texts (largest height).
  `sheet_text.sheet_text(work_dir, file, sheet_id, contains=None, max_entries=400)`: the entries of ONE
  sheet in documented reading order (rows top-down within 0.6 x median text height of the row's first
  entry, then left to right), compact fields only, NFC + casefold `contains` filter (diacritics kept),
  truncation with true counts; unknown encodings are returned as stored with their flags.
  `callouts.extract_callouts(work_dir)`: candidates of kinds rebar_callout, rebar_grade, section_label,
  steel_grade, plate, bolt and member_mark with `parsed` only for notations the research marks verified
  (`rule` cites the pattern), else `unparsed_reason`; confidence capped (grade-B grammar at most medium,
  unparsed/ambiguous/member marks low, case-uncertain or unknown-encoding text low); provenance `derived`
  from the text entry with a file path relative to the input folder; questions `callout_ambiguous` (one
  per notation), `member_mark_prefix_meaning` (blocking, one per prefix) and `grade_legacy_mapping`
  (blocking). Nothing is computed from a callout. Input documents are checked for version and matching
  sha256; `check_inputs=True` also validates them against their schemas. Not covered: circled bar marks,
  welds and electrodes, sheet prefixes, axes and levels (other extractors).
- Stable question ids and engineer answers (RTI C1 / M14): a rerun, or one new input file, no longer
  shifts `Q-nnn` onto another question, so an engineer answer cannot attach to the wrong question.
  One question is now one (code, blocking flag, file) with its refs (caps keep the true `count`);
  consolidated documents keep the display order (blocking first, then code, then file). New module
  `questions.py`: `key` = first 16 hex of sha256 over code, file, that file's sha256 (inventory) and the
  sorted refs (`where`, `found`, `sheet`), so a changed drawing is re-asked and an unchanged one keeps
  its key. New `question-registry.json` (schema `question-registry`): key -> id, code, file, producer,
  status `open | answered | obsolete`, `first_seen_run`, `last_seen_run`; one counter allocates
  `Q-001..` for intake, read-structure and the new `callouts` command, ids are never reused, and a
  producer only marks its own unseen keys obsolete (no timestamps; the run counters are the only thing
  that differs between identical reruns). New `answers.json` (schema `answers`): the engineer's verbatim
  `answer_text`, structured `values` for the units questions (`unit`), `grid_family_axis_assignment`
  (`{family: X|Y}`) and `member_mark_prefix_meaning` (`{prefix: meaning}`), `answered_by`,
  `answered_on`, `status active | stale | superseded`. `harness answer <work_dir> <question_id> --text
  .. --by .. [--value k=v ..]` (meant for the engineer, or on the engineer's explicit instruction;
  refuses unknown or obsolete ids, invalid values, blank text or name; a second answer supersedes the
  first; refreshes the question documents on disk). Every question shows its `key`, `file` and `answer`
  (the active answer or null); each questions document has `summary.blocking_open` (blocking questions
  without an active answer). Intake diffs the sha256 of the input files against the previous
  `inventory.json` (`summary.changes` `added | removed | changed`, all empty on a first run); answers
  about a removed or changed file, or whose question its producer no longer raises, become `stale`
  (kept, listed as `stale_answers` in the `inventory.json` summary and in the run summaries,
  never re-bound). Intake schema changed (still
  `0.1`): question `key`, `file`, `answer`, `subjects`; `summary` of a questions document;
  `summary.changes` and `summary.stale_answers` of an inventory; `first_question_number` removed from `structure_summary`; the
  per-file `units_confirm_all` replaces the one question that listed every DXF. `read-structure` and
  `callouts` need the registry (exit 2: run intake first). `intake.question_group` moved to
  `questions.question_group` (new `file` argument); `dump_json` lives in `questions` and is still
  importable from `intake`.
- CLI for the reader tools: `harness list-sheets <work_dir>`, `harness sheet-text <work_dir> <file>
  <sheet_id> [--contains TEXT] [--max N]` (stdout is the JSON) and `harness callouts <work_dir>
  [--input-dir DIR]`, which writes `callouts.json` and `callouts-questions.json` (the three callout
  question codes as one question per code and file, with `subjects` per notation or member mark
  prefix; stdout is the summary). With `--input-dir` the DXF/DWG files must still match the inventory
  sha256 (exit 1 otherwise, nothing written).
- Step 2 grid systems: `grid_system.build_grid_systems(...)` consolidates the per-view grid families into
  project grid systems (gate 1 proposals); schema `grid-system` registered, command `harness grid-system
  <work_dir> [--no-svg]`. A family joins a system only if it agrees with every member within half the
  rounding step or 2e-4 (never averaged); same labels with incompatible spacings give separate systems and a
  blocking `grid_system_conflict`; partial views, independence, never above medium; `mm` only from agreeing
  units answers (one building in m and mm merges), Tekla X/Y only from `grid_family_axis_assignment`
  answers; 4 blocking question codes (producer `grid-system`); SVGs with the PROPOSAL banner. See
  `grid_system.py`.
- Work-folder status and guards (reading toolchain): `harness status <work_dir>` (read-only, new schema
  `status`, exit 0 for any readable work folder, 2 if not one) recomputes per producer (intake,
  read-structure, callouts, grid-system) total / blocking / blocking_open / stale answers from the registry and
  answers, whether each producer's outputs are `fresh | stale | missing` (inventory sha256 recorded in
  `structure-summary.json`, `callouts.json`, `grid-systems.json`; grid-system also an `answers_sha256`) with
  the command that fixes it, and `gate1.ready_for_gate1` with reasons. The registry entry now records
  `blocking` and `file_sha256` (optional for old entries, which status counts as blocking); `harness answer`
  refuses (exit 1, nothing written) a question whose file changed since it was raised, and
  `grid_system_select` takes an optional `systems=S001,S002` value. `callouts.json` no longer embeds the
  unnumbered `questions` (they are in `callouts-questions.json`); it keeps `question_counts` by code.
  Schemas changed (still `0.1`): `callouts`, `question-registry` (producer `grid-system`, `blocking`,
  `file_sha256`), `answers`, `intake` (descriptions), `grid-system` (`answers_sha256`, units reasons and
  flag `answered_units_differ`), new `status`.
- `harness ask` (`src/tekla_harness/ask.py`): the drawing-reader agent raises questions through the registry
  instead of inventing ids. New registry producer `reader`; questions in `reader-questions.json` (same
  document kind as the other `*questions.json`), one question and one ref per distinct
  (code, blocking, file, where) - the key hashes those and the file's inventory sha256, not `found`, `sheet`
  or the text - so asking the same place again prints the same id (`already_asked`). A file not in the
  inventory exits 1; a code owned by another producer, or not snake_case, exits 2. Reader questions are never
  obsoleted by another producer's run; `--withdraw Q-id --reason` marks one obsolete (kept, with
  `withdrawn_reason`, and its active answer goes stale). `harness status` gains the `reader` producer
  (outputs `n/a`) and gate 1 waits for its blocking open questions. Schemas changed (still `0.1`):
  `question-registry` (producer `reader`, `withdrawn_reason`), `intake` (ref `file` may be null in a
  project-level reader question), `status` (5 producers, outputs `n/a`).
- EVAL-1 wave groundwork: registry producer `marks` (`harness marks`, documents `marks.json` and
  `marks-questions.json`; like callouts, its blocking questions block lot specs, not gate 1; status checks
  its outputs' `inventory_sha256`); `harness ask` accepts any code in the `reader_` namespace (no producer
  owns it), and the owner table now lists `grid_family_axis_assignment` and `grid_units_doubt` under
  read-structure, which raises them (EVAL-1 F-20, F-21); `harness marks`, `harness questions-md` and
  `harness finding` registered as stubs that exit 3 until their modules land. Schemas changed:
  `question-registry`, `status` (6 producers).
- Step 3 groundwork: `tekla/api-notes.md` (Tekla Open API 2024 Diamond, 2025/2026 deltas;
  doc-sourced, not run-verified) and ADR-0007 (on error stop, keep and resume by `SPEC_ID`;
  backup by macro; exe config at build time; per-model unique tag UDAs). The CLI contract now
  names the executable `tekla-cli.exe` and pins NuGet 2024.0.4.
- Step 3 S1 (ADR-0009): .NET solution `tekla/TeklaHarness.slnx` (SDK 10 pinned in
  `tekla/global.json`), Tekla-free `TeklaCore` (netstandard2.0) with the contract exit codes and
  the model-path text guard for safety rule 1 (fail closed: refuses relative, UNC, device, `..`,
  8.3, trailing dot/space, invalid characters; NTFS-style case folding plus NFKC/NFKD caution);
  `TeklaCore.Tests` on net10.0 and net48; Stryker.NET as a local tool; CI job `dotnet` (Windows
  runs net10.0 and net48, Ubuntu net10.0). Globalization analyzers are errors.
- Step 3 S1a (ADR-0009 Amendment 2): `ModelLocationGuard` completes safety rule 1 with Windows
  file identity through `IFolderResolver` / `Win32FolderResolver` (128-bit `FILE_ID_INFO`, final
  path, NTFS/ReFS on local drives only): refuses aliases (subst, junctions, mapped drives),
  nesting found through real or typed ancestors, remote folders, a working copy declared through
  an alias, and links inside either folder or hard-linked files in the copy. Research note
  `docs/research/windows-file-identity.md`. Windows file-system tests run on CI windows-latest
  only (`Category=Windows`); Stryker config `tekla/TeklaCore.Tests/stryker-config.json`.
- Step 3 S1b contract (ADR-0010 Amendment 1): new schema `spec-receipt`
  (`urn:tekla-harness:schema:spec-receipt:0.1`) and example — the receipt
  `<spec file name>.receipt.json` binds the spec's exact bytes (SHA-256), the spec schema `$id`
  and the validator `rules_version`; `*.receipt.json` is git-ignored. Shared strict-JSON corpus
  `tests/fixtures/strict-json/` (accept/reject) for the Python and C# readers.
- Step 3 S1b Python: `harness validate spec` reads each spec once under the strict JSON profile
  (`tekla_harness.strict_json`: no BOM, duplicate keys, NaN/Infinity, integers beyond ±2^53, lone
  surrogates or NUL, depth over 64, size over 16 MiB), deletes a stale receipt first (exit 3 if it
  cannot), and writes `<spec>.receipt.json` atomically next to each valid spec
  (`SPEC_RULES_VERSION = 1`); each result gains `receipt`. `check_spec` now requires `lot` to be
  an integer token (not `1.0`) and at most 2147483647.
  Value parity: canonical dumps `tests/fixtures/strict-json/values/` (IEEE bits, UTF-16 units)
  for every accept file, plus `accept/number_parity.json` (4049 tokens incl. 1019 that
  .NET Framework 4.8 `double.Parse` rounds differently); compared by pytest and xunit.
- Step 3 S1b C#: `TeklaCore.SpecLoader.Load(spec, lot)` builds a `LotSpec` only when
  `<spec>.receipt.json` matches the spec's exact bytes (SHA-256 of the one buffer it also parses),
  an accepted spec schema `$id` and `rules_version ≥ 1`; then read-time checks (schema_version vs
  receipt, units `mm`, lot int32 = `--lot`, unique `spec_id` matching its pattern, profile,
  material, finite points). Refusals exit 5, I/O errors 3, bad path text 2. Hand-written strict
  JSON reader (no package) with its own correctly rounded decimal→double conversion
  (`System.Numerics.BigInteger`): 0 of 150,000 tokens differ from Python on .NET Framework 4.8.
- Step 3 S1c contract (ADR-0012): new schema `run-journal` (`urn:tekla-harness:schema:run-journal:0.1`)
  and example — one journal per lot and run (`run-journal-<RUN_ID>.json`), invocations with
  per-object intent/inserted/tagged states, failure and conflicts; `run_id` pattern
  `^[A-Z0-9][A-Z0-9_-]{0,31}$` added to `common`.
- Step 3 S1c C# (ADR-0012): `TeklaCore` run journal reader/writer (strict JSON, bytes identical to
  Python `json.dumps(indent=2, ensure_ascii=False)`, golden fixture `tests/fixtures/run-journal/`,
  atomic replace with retries), per-model run lock (named mutex on the normalised working-copy
  path; held → exit 3), model snapshot types (three-state tags, GUID presence) and a pure
  `ResumePlanner`: skip, retag, create or conflict per member, refusals before planning (spec hash,
  model path, header, any rollback, untrusted lookups), matching within 0.1 mm (+1e-6 rounding
  allowance), kind, rotation 0.01° and class.
  After independent review: lookups and tags that disagree in either direction refuse (exit 3);
  a `running` invocation or an invocation on another model refuses (5); the journal replace keeps a
  `.bak` and a leftover temp/backup without its journal refuses (5); `ResumePlan.Executable` and
  `MemberAction.Blocked` stop a plan with conflicts from being partly executed; the lock uses
  `Global\` and refuses a release on another thread.
- Versioning note: the reading-toolchain schemas above have not been released; they stay `0.1` and their
  changes are recorded here until the first tagged release, from which every change bumps its `$id`
  (AGENTS.md). Pending engineer confirmation.
- Legacy-font gate (EVAL-1 fix 2): `text_gate.meaning_block_reason(entry)` decides whether meaning may be
  taken from a text-index entry: pure-ASCII raw text is allowed; other text is blocked
  (`knowledge_conflict`, `encoding_proposed`, `encoding_contradiction`, `encoding_unknown`) until its
  encoding is settled by a font name, code-point evidence or an approved knowledge row. Used by
  sheet-text, find-text, list-sheets, `harness finding` and `harness marks`.
- Reader tools (EVAL-1 fix 2, F-08..F-11, F-25): every `sheet-text` entry carries `meaning`
  (`allowed | blocked`) and `blocked_reason`; `sheet-text` reports `legacy_font_gate` (blocked count, by
  reason, styles, the file's encoding question ids); `list-sheets` titles rank title keywords first
  (Vietnamese and English), skip grid labels, bare numbers and years, and carry `entry_id`, `meaning`,
  `matched_keyword`, plus `blocked_text_count` per sheet; `sheet-text` warns on stderr and in `warnings`
  when it truncates, and `--contains` without `--max` is unbounded. New `harness find-text <work_dir>
  --contains TEXT [--file F] [--max N]` searches every sheet of every file in one call and counts the
  blocked entries it could not search reliably (new `find_text` kind in the `sheet-text` schema).
  Changed: `sheet-text` entries use `entry_id` instead of `id`.
- `harness finding add | withdraw | list` (`findings.py`, new schema `reader-findings`, EVAL-1 fix 3):
  the drawing-reader agent records each judgement (sheet class, general-note item, structural-system
  claim, cross-check) in `work/reader-findings.json`, tied to text-index entries. `add` checks the file,
  entries, sheet membership, live question ids, note values as verbatim quotes, and the legacy-font gate
  (a blocked entry backs no finding; the refusal names the font questions to answer first). Confidence
  is the minimum of the cited entries, may only be lowered, never `high`. Ids `F-001..` are never reused;
  `withdraw` keeps the finding with its reason; `list` flags findings whose file changed as `stale`; one
  active `sheet_class` per sheet; an identical active finding returns its id (`already_recorded`).
- `harness marks <work_dir> [--input-dir DIR]` (`marks.py`, new schema `marks`, EVAL-1 fix 4): member
  marks (`D1`, `D1.1`, `D1-1`, `D1a`, `mark(b x h)` with b and h as written, never converted), member-type
  words before a mark (`DẦM D1.1`, `COLUMN C1`) as `title_member_word` evidence (never a prefix meaning),
  schedule tables from the DXF line grid or text alignment under a whole-cell header keyword, and
  plan-to-schedule matching by exact key only (NFC + casefold, whitespace removed). Separator or
  leading-zero variants (`D1.1`/`D1-1`) are never merged: one blocking `mark_notation_equivalence` per
  file; a plan section that differs from its schedule row raises a blocking `mark_size_conflict`; a
  keyword table that cannot be read raises a non-blocking `schedule_table_unparsed`. Tables whose header
  the font gate blocks are reported `header_blocked` and never matched. Writes `marks.json` and
  `marks-questions.json`; status tracks freshness.
- Gate-1 question noise (EVAL-1 fix 5, F-04, F-05, F-26): `units_confirm_all` is the only blocking units
  question per probed file: the probe's `units_conflict` / `units_suspect` / `units_unknown` become its
  refs (where/found verbatim) and `grid_units_doubt`, `grid_system_units_unconfirmed` are non-blocking
  evidence; a units check closes only on that question's structured `unit=`. New blocking
  `units_answer_contradicts_evidence` (grid-system) when the answered unit fails the `units_suspect`
  magnitude test (`units.dimension_median` now in the probe and inventory); it closes by re-answering, or
  by confirming the same unit. X/Y is asked once per grid system: `grid_system_axis_unassigned` takes
  `--value dir1=X|Y --value dir2=X|Y`, is bound by key and blocks only for selected, unassigned systems;
  `grid_family_axis_assignment` is non-blocking. `grid_system_select` takes `separate=S001,S002`; systems
  outside `systems=` raise no blocking question; `grid_system_conflict` is one question per pair, closes
  only via `systems=` or `separate=` (never answer text), and `harness answer` refuses it. Status reasons
  name the question id to answer. On the eval set, blocking units questions per file went from 5 to 1
  (267) and 3 to 1 (433, steel).
- `harness questions-md <work_dir> [--out PATH]` (EVAL-1 fix 1, F-07, F-22, F-24): renders `questions.md`
  (Vietnamese) deterministically from every question document, the registry, `answers.json`,
  `grid-systems.json`, `structure-summary.json` and the gate-1 reasons: summary, blocking then
  non-blocking open questions by topic and file, answered questions, stale answers. Refs verbatim, counts
  with "hiển thị n/N", the exact `harness answer` command with the values each code needs, proposals
  labelled "ĐỀ XUẤT — chưa xác nhận". The code-to-Vietnamese table `questions_md_vi.py` is proposed copy
  pending engineer review; a code without a row prints its English message and is listed in
  `untranslated_codes`.
- `harness ask`: `units_answer_contradicts_evidence` is owned by grid-system (exact codes now win over
  another producer's prefix).
- Drawing-reading skills active (engineer approval 2026-11-07, after EVAL-1, EVAL-2 and a
  skill-creator trigger check): `drawing-intake`, `structural-drawing-reader`,
  `drawing-analysis-report`, `tekla-conversion-plan` moved from `dwg-lab/proposals/skills/` to
  `.claude/skills/`; registered in the AGENTS.md skills table; preloaded through `skills:` in
  `.claude/agents/doc-reader.md` (first three) and `planner.md` (the plan). Trigger check, 2 runs per
  query: intake 10/10 and 6/6 on fresh queries, reader 10/10 and 5/6, report 10/10, plan 10/10; no
  near-miss triggered.
- Work-folder write lock (tool wave 2, ADR-0011, proposed): `worklock.work_lock` holds an exclusive OS
  lock on `work/.harness.lock` (POSIX `flock`, Windows `msvcrt.locking` on byte 0) for the whole run of
  intake, read-structure, callouts, marks, grid-system, answer, ask, finding add / withdraw and
  questions-md. A held lock is exit 3 at once, naming the holder (pid, host, command, start time) from
  `.harness.lock.json`, which the holder removes before unlocking; no waiting, no stale-lock rule, the
  lock file is never deleted. A filesystem without lock support is exit 3 (never runs unlocked).
  Read-only commands (status, list-sheets, sheet-text, find-text, finding list, dimensions) and the
  path-based tools (validate, detect, dwg2dxf, read-dxf, extract-*, env-check) do not lock; every
  subcommand must be on one list (`cli.UNLOCKED_COMMANDS`, test-checked). A writer whose work folder does
  not exist is refused with exit 2 before it runs ("not a folder"). The holder record names its
  `platform`; a record from the other OS (WSL vs Windows, whose locks do not see each other) refuses the
  lock with exit 3 and says how to clear a stale one. Intake now resolves its converters before it reads
  the work folder's registry, and creates the work folder just before locking it.
- Tool wave 2 seam (EVAL-2 fixes; the packages fill in the behaviour). Schemas, all additive and optional,
  `$id` still `0.1` (engineer, 2026-11-07): `text-index` decode source `style_family` and flag
  `legacy_ascii_suspect`; `dxf-probe` hint `matched.field` `family`; `sheet-text` block reason
  `legacy_ascii_suspect`, `list_file.blocked_text_count`, sheet id `unassigned` with null layout and bbox,
  `query.unassigned`, `find_text.counts.unassigned_entries_searched`; `levels` `blocked_candidates`;
  `marks` `table.blocked_columns`, match `size_compared` / `size_not_compared_reason`, `summary.by_sheet`,
  `summary.size_comparisons`; `callouts` `summary.unparsed_by_reason` and reason `legacy_ascii_suspect`;
  `intake` question `closed_by` and ref `families`; `answers` `answered_by_role` (engineer | simulated) and
  `file_set_relation` values; `reader-findings` `decoded_by` and list `summary.by_class`; `grid-system`
  `conflicts[].question_id` and `file_sets`; `status` `gate1.closed` and `gate1.non_engineer_answers`. New
  schemas `dimensions` and `supplements` with examples. Shared code: `questions.FILE_SET_CODE`, `ROLES`,
  `Closure`; `lifecycle.closures` and `supplements.load_supplements` stubs (no closure, no supplement
  yet); `harness status` leaves closed questions out of the blocking counts and makes a `simulated`
  answer to a gate-relevant question a gate-1 reason (an answer without a role still counts as the
  engineer's); `harness questions-md` renders closures and supplements and has a `file_set_relation` row;
  `harness answer --role engineer|simulated` and `file_set_relation` values (every file of the question
  once); `harness ask` gives `member_mark_prefix_meaning` to marks and `file_set_relation` to intake;
  `read_dxf.measure_dimension`. Not implemented yet (exit 3): `harness dimensions`, `sheet-text` /
  `find-text --unassigned`, `harness ask --supplement` / `--withdraw-supplement`.
- `marks` schema: `question_counts` accepts `member_mark_prefix_meaning` (tool wave 2, D6: marks asks the
  plan-mark prefix question instead of callouts); `anchor_entry_id` and `columns.role` descriptions cover
  line-grid tables found from a mark text with no header keyword. `$id` stays `0.1`.
- Tool wave 2 package P3, answer provenance and reader supplements (EVAL-2 fixes 10 and 7):
  - `harness answer --role engineer|simulated` is required (exit 2 without it). Every `harness answer`
    command that `harness status` and `harness questions-md` print names `--role engineer` after `--by`.
  - Gate 1 no longer counts an answer recorded without a role (DESIGN D4): like a `simulated` answer to a
    question of intake, read-structure, grid-system or the reader, it is a gate-1 reason naming its
    question id (`gate1.non_engineer_answers`, role null) until the engineer answers again.
  - The same holds for a non-engineer active answer whose question is not live (no registry entry, or
    obsolete) when a gate check still reads its code from every active answer (units, grid-system): the
    reason names the answer's key.
  - Review M1: every `harness answer` command in a gate-1 reason is introduced as the engineer's own step
    (`the engineer runs: …`), the role reason says the engineer must answer again themselves, and
    questions.md labels the command as one the engineer runs and an agent never runs instead.
    `record_answer` takes `role` as a required keyword (no default; None is a usage error).
  - Review M2: `harness status` and `harness questions-md` accept a `lifecycle.closures` closure only when
    its reason fits the closed question (not_selected / separate: grid-system `grid_system_conflict`;
    units_answered: read-structure `grid_units_doubt`; rejected_systems_only: read-structure `grid_*`
    except `grid_gate1_confirmation`; other_file_set: none yet, nothing derives it), the question is not
    the reader's, and it names a live question of the code the reason needs (`grid_system_select`, or
    `units_confirm_all` for units_answered) with an active engineer answer. A refused closure leaves the
    question open and is a `closures:` gate-1 reason. A closure a producer already wrote (registry
    `blocking: false` plus `closed_by` in the question document) is checked against the same contract;
    a refused one counts the question as blocking again, in status and in questions.md. An unreadable or
    invalid document the lifecycle reads is exit 1 in `harness status` and `harness questions-md`.
  - A grid-system conflict pending on an unanswered `file_set_relation` question (non-blocking, no
    `closed_by`) gets a gate-1 reason that names that question and its answer command, instead of the
    `separate=` advice.
  - `harness ask --supplement Q-id --where --found --text [--file --sheet]` adds the reader's evidence to a
    producer's question in `reader-supplements.json` (key = target key, file, file sha256, where; prints
    `new` or `already_supplemented`); exit 2 for an unknown, obsolete or reader-owned target, a withdrawn
    place, or `--code` / `--blocking`. `--withdraw-supplement KEY --reason R` keeps it as withdrawn. A
    supplement whose target goes obsolete reads as `stale`; questions.md shows active ones under the
    question. The target's blocking flag, answer and refs never change.
  - `harness finding add` records `decoded_by`: per decode source and knowledge pattern of the cited
    entries' runs, the knowledge row's status and decision date. `finding list` marks a finding `stale`
    when that row's status or date changes or the row is gone; such a finding no longer counts as a
    duplicate or as a sheet's active class.
  - `harness finding list` prints `summary.by_class`: the listed `sheet_class` findings per class, counting
    only active, non-stale ones (a withdrawn or stale class would count a sheet twice).
- Tool wave 2, package P4 (marks and dimensions):
  - `harness marks` gates schedule tables per column (EVAL-2 fix 8): only a blocked mark-column header
    blocks a table; any other blocked header cell is listed in `table.blocked_columns` and the table is
    read. A line-grid table without a keyword is read on the column it was found from (confidence low)
    unless that column's header is blocked. Every matched mark says `size_compared`, else
    `size_not_compared_reason`; `summary.size_comparisons` counts them.
  - Counts the report asks for (EVAL-2 fix 11): `harness marks` `summary.by_sheet` (plan marks, tables,
    header-blocked tables, rows, unparsed tables, blocked marks per detector sheet; sheet null for texts on
    no sheet) and `harness callouts` `summary.unparsed_by_reason` (unparsed candidates per reason).
  - `harness dimensions <work_dir> <file> [--sheet ID | --unassigned] [--layer L] [--max N] [--input-dir
    DIR]` (EVAL-2 fix 11), read-only: every DIMENSION of one drawing, also inside nested INSERTs (virtual
    copy, handle null, `block_path`), with what it measures next to its printed or override text and the
    probe's text rule and status, plus layer and detector sheet. Values as stored, never converted;
    `units` reports the declared and the answered unit only. A native DXF needs `--input-dir` (exit 2).
    The layer is the effective one: inside a block, layer 0 takes the layer of the placing INSERT
    (recursively), so `--layer` finds it; the stored layer is not reported (one layer field in the schema).
  - `member_mark_prefix_meaning` moves from `harness callouts` to `harness marks` (EVAL-2 fix 1b): one
    blocking question per file with one subject per prefix of its plan marks (upper-cased; titles such
    as `DẦM D3` count, schedule cells do not); `marks.json` `question_counts` counts the prefixes. Callouts
    still lists `member_mark` candidates but no longer asks; an answer to callouts' old question goes stale
    once at the next callouts run and the engineer answers the marks question (default D6, reversible).
- Tool wave 3 (EVAL-3 fixes; the packages fill in the behaviour):
  - Tool wave 3, seam. Schemas, all new fields optional, `$id` still `0.1`:
    - `answers`: `grid_system_missing` values `dir1_labels`, `dir1_spacings`, `dir2_labels`,
      `dir2_spacings` (arrays; both directions, or none) and optional `sheet` (ADR-0013 §2);
      `grid_answer_contradicts_drawing` takes no value.
    - `question-registry`: `obsolete_reason`, only on obsolete entries.
    - `grid-system`: question codes `grid_system_missing` and `grid_answer_contradicts_drawing`; system
      `source` (`detected` | `engineer_answer`) and `source_answer` (question id, key); a system built from
      an answer has no view, contributor or representative family, and its provenance method is
      `engineer_answer`; status `proposed_simulated` for `units.status`, `axis_assignment.status` and
      `files[].units_answer.status`, units reason `units answered by a non-engineer role`; conflict
      `proposed_closed_by` (what a non-engineer select answer would close; it closes nothing).
    - `marks`: `summary.mark_sets` (`file`, `family`, `members`, `complete`, `source`); `compared_with` on
      matched, schedule-only and plan-only marks (`schedule` | `detail_heading`, plus `none` for plan-only),
      `detail_headings` refs (a heading-only match needs no schedule row) and the per-file
      `detail_headings` count.
    - `callouts`: candidate `unparsed_code` (reason family, incl. `symbol_glyph_unverified`), top-level
      `rejected` matches with `reason_code` and `reason`, summary `unparsed_by_code`, `rejected`,
      `rejected_by_reason`, question count `callout_unparsed`.
    - `sheet-text`: `query.region`, `region` and `rows` (cells of entry ids with display text and the
      gate's meaning) for a region read; find-text `counts.blocked_in_scope` (query-independent); one of
      it and the deprecated `blocked_entries_not_searchable` is required.
    - `intake` question `places` and `amendments` (reader questions); new schema `reader-questions`
      (`harness validate reader-questions`), with example; examples `grid-system-answer` and
      `sheet-region`.
    - `status`: `gate1.closed` stays optional until `harness status` always writes it.
  - Tool wave 3, seam: a registry entry that a producer run makes obsolete records `obsolete_reason`
    (W5), first match wins: its input file was removed, or changed (asked again under a new key), or
    the producer declared its code superseded by an answer to another code (`Ledger.sync(...,
    superseded_by={code: answer_code})`, only while such an answer is active), else the latest run no
    longer raises it. Set on the transition, kept while obsolete, dropped when the key is raised again.
  - Tool wave 3, seam: new question codes `sheet_number_gap`, `callout_unparsed`, `legacy_ascii_text`,
    `grid_system_missing`, `grid_answer_contradicts_drawing` (shared constants in `questions`, with the
    `grid_system_missing` value keys) and their proposed Vietnamese rows in `harness questions-md`, whose
    answer command for `grid_system_missing` prints the ADR-0013 keys. New flags, parsed and checked
    (exit 2 on misuse) but not implemented yet (exit 3, nothing written) until their package lands:
    `harness ask --amend Q-id [--text T] [--places P ...]` (package C; `--places` only with `--amend`) and
    `harness sheet-text W FILE SHEET --region x0,y0,x1,y1` (package T; four finite numbers, x0 < x1,
    y0 < y1, a sheet id and no `--unassigned`; write negative coordinates as `--region=-5000,...`,
    which the help says, because argparse takes a `-` value after a space for an option). `harness find-text` warns with `blocked_in_scope` when the
    output has it. `harness answer --help` names the `grid_system_missing` keys.
  - Tool wave 3, package S (sheets + levels):
    - Levels: a storey word names a storey except in the non-names seen on the corpus: a slab-plan
      title whose only storey word is `sàn` (slab), a quantity or schedule heading (`khối lượng`,
      `thống kê`), and a storey word with nothing else (`tầng`, `floor slab`). A sure name (`tầng 3`,
      `first floor`, `upper floor`, `tầng thượng`, `tầng kỹ thuật`, `tầng điển hình`, `áp mái`,
      `penthouse`) always counts, also as the text next to a bare value. So `level_name_conflict` is no
      longer raised between slab-plan titles (290: three false conflicts; 267: one) but still is between
      names without a number (`TẦNG THƯỢNG +10.800 / +10.500`), and storey heights fall back to the
      asked, low rule instead of skipping unnamed levels (290: +7.300 is no longer skipped).
    - Levels (safety): when storeys are named, an unnamed level that carries a storey word (on its line
      or in the text next to it), between the named levels or outside them, caps the storey heights at
      low and raises the blocking `level_storey_selection` listing those levels; before, `GROUND / FIRST /
      SECOND / ROOF FLOOR` gave one 10.8 m storey with no question, and a bare `GROUND ±0.000` or an
      unnamed basement below named floors was dropped from the heights silently. No known file changes.
    - Levels: a sign with one space before the digits right after `(` is a sign, so
      `(+ 6.00M LEVEL)` gives the level +6.000 (161 and Steel_01). Elsewhere a spaced sign after other
      text is still read as a dash (`TẦNG 2 - 3.600`).
    - Sheets: the sheet-number pattern (used only when no title field gives one) looks in the title-block
      corner, the last quarter of the frame along the text's reading direction and its lowest fifth,
      not the lower-right quadrant. A portrait frame is also read at 90 and 270 degrees. A member mark
      is never a number: a code that appears twice on its sheet, has a mark family on its sheet
      (`gĐ-1`, `gĐ-2`), or appears twice outside every title block. Among several corner codes a
      position repeated in other sheets' corners wins, then the tallest; a tie stays a
      `title_field_conflict`. Every corner code not taken is listed in `warnings` with its reason. A
      model text shown on a layout sheet is never in that sheet's corner. Corpus: 285 model#03
      `kc- 03`, 290 model#16-18 `Kc - 13` and 267 model#16-20 / #43-44 are now read; the false
      `gĐ-3` on 286 model#04 is gone.
    - Sheets (safety): a corner code is taken as the sheet number only when its position repeats in
      another sheet's corner. A code with no such backing (and every code of a one-sheet file) is a
      warning, and the sheet gets the blocking `sheet_number_missing`; before, a lone mark in the corner
      (`C-1` next to a number like `S101` that is not code-shaped) became the number with no question.
      Codes without a separator (`S101`) are still not sheet codes: on the known files that shape picks
      up stirrup spacings (`a100`, `a200`).
    - Sheets: a text equal to another sheet's corner code is a reference to that sheet (a detail callout,
      a drawing list, an index sheet), not evidence that the corner code is a mark, so a number referenced
      from two sheets or a sheet that references its siblings keeps its number. Only corner codes that pass
      their own sheet's mark checks count as sheets to reference. References to sheets outside the file
      still count as marks, so that sheet is asked. No known file changes.
    - Sheets: new non-blocking question `sheet_number_gap`, one per file, when the chosen sheet numbers
      of a letter series skip numbers that no sheet of any series carries (one counter may run over
      several series, as Kc and KT on 290). `found` gives each missing number or range with the sheets
      on each side, and the sheets without a detected number. `KT 1/18` counts as 1, `KC-05A` as 5;
      other values are left out. Corpus: 290 `missing 25`, 461 `missing 6-9` (three sheets there have
      no detected number); no other known file.
    - Sheets: more than 9 missing sheet numbers in a row (`SHEET_GAP_MAX_RUN`) is a numbering jump, not
      a gap: `S-101 / S-201 / S-301` (numbering by hundreds) no longer asks `missing 102-200; 202-300`.
      Each jump is a warning with the numbers and sheets on each side; shorter gaps next to it are still
      asked. The known gaps (290: 1 number, 461: 4) do not change.
  - Tool wave 3, package T:
    - W4 (safety): `harness find-text` and `harness sheet-text --contains` never match a blocked
      (legacy-font) entry, on its stored, decoded or any normalised text; before, typing the stored legacy
      form of a word (`thèng kª`) found and in effect decoded blocked text (EVAL-3 F-B17). Blocked entries
      are reached by entry id or sheet listing only. find-text reports `counts.blocked_in_scope`, the
      blocked entries of the searched files or sheets whatever the query, and no longer writes the
      deprecated `blocked_entries_not_searchable`; hits are always `allowed`. sheet-text `--contains` warns
      how many blocked entries of the sheet it never matches.
    - W3: `read_dxf.legacy_ascii_questions(text_index, file, probe text_styles)` builds the
      `legacy_ascii_text` questions of one file: one per text style holding `legacy_ascii_suspect`
      entries, not blocking, `count` = the style's flagged entries, the first 5 listed by entry id and
      quoted as stored, the message and every ref's `where` naming the style, its font file and its
      TrueType family (`harness questions-md` shows the refs, not the English message). `harness
      intake` raises them after the `encoding_unknown_non_ascii` questions (none for a file whose text
      index is unreadable); on 267 one question covers the 786 ROMANS entries, on 461 two questions
      cover 14. The `questions.py` docstring and the intake schema descriptions now say these questions
      (and `callout_unparsed`) are one per file and style (or reason family), not one per code and
      file. The sheet-text
      `legacy_font_gate.question_ids` lists the file's live `legacy_ascii_text` questions when the sheet
      has `legacy_ascii_suspect` entries (encoding questions still only when an encoding answer can lift
      a reason); find-text `notes` names the questions covering the blocked entries in scope; `harness
      finding` counts `legacy_ascii_text` as a font question when it refuses a blocked entry.
    - a5: `harness sheet-text W FILE SHEET --region=x0,y0,x1,y1` (absolute coordinates, the entries' x/y
      and the list-sheets bbox) returns the sheet's entries whose insertion point lies in the box, edges
      included, as `rows` of `cells`: rows as the reading order with the whole sheet's row tolerance
      (0.6 x its median text height), a new cell where the insertion-x gap to the left neighbour exceeds
      that tolerance, each cell with its entry ids, joined display text, meaning and x span; no blank
      cell is invented. `entries[].row` indexes `rows`; `counts.assigned` and `legacy_font_gate` stay the
      whole sheet's; `--contains` and `--max` work as without a region. A box that misses the frame is
      warned about. On 286 the `Ø<10mm` row reads `Ø<10mm | CI | 225` (T001075, T001074, T001072).
  - Tool wave 3, package G:
    - `harness read-structure` finds grid bubbles drawn as an ARC that is a full turn within
      `FULL_ARC_GAP_DEG` (1 degree; EVAL-3 285 and 286 block `SADF`, an arc from 90.00006 to 90.0000031
      degrees), and a grid line drawn through the bubbles at both of its ends and on to the frame pairs
      with them when two bubbles of one label, at least `MIN_AXIS_LENGTH` radii apart, both lie on it
      (286 model#05). A ratio-1 ELLIPSE is a circle only when it, too, is a full turn (a door swing in an
      unevenly scaled block was counted). 285 now gives 1-2-3-4-5 = 3130/3540/3520/4590 x A-B-C =
      4250/3730 (and 4254 on model#03), 286 gives 1-2-3 = 3400/3980 x A-B-C = 4840/4190 on 13 sheets.
    - `harness grid-system` reads only the engineer's answers (`answered_by_role` engineer) as decisions.
      Units or Tekla X/Y that only a simulated or role-less answer gives are `proposed_simulated`
      (`units.answered` names the proposed unit; nothing is converted or assigned; the X/Y question keeps
      blocking); a `grid_system_select` answer from another role selects nothing and records what it would
      close as `proposed_closed_by` (the conflict keeps blocking); a `file_set_relation` answer from another
      role leaves the file sets pending; a `units_answer_contradicts_evidence` confirmation counts only from
      the engineer. Each such answer is named in `warnings`. A conflict that the engineer's file-set answer
      retires records `obsolete_reason` "superseded by an answer to file_set_relation".
    - ADR-0013 route in `harness grid-system`: every read drawing file that no selected two-direction
      detected system covers gets a blocking `grid_system_missing` question (`found` quotes the bubbles,
      labels and axes grids.py found; the message names the file's detected systems and why none is
      usable, and the `--value` keys). An active answer by the engineer with `dir1_labels`,
      `dir1_spacings`, `dir2_labels`, `dir2_spacings` (and optional `sheet`) builds a system with
      `source: engineer_answer` and `source_answer`, numbered after the detected systems; it is selected,
      given Tekla X/Y and units like a detected one, and the question stays raised while that answer is
      active, so the answer and the system survive reruns. A simulated, role-less, words-only or malformed
      answer builds nothing and is warned. The given spacings are checked against the linear dimensions
      between two of the given axes (labels case-blind, spans as sums, drafting tolerance): a
      disagreement raises a blocking `grid_answer_contradicts_drawing` quoting both values; a grid with no
      dimension to check is warned. `grid_system_missing` answers are part of the answers digest.
  - Tool wave 3, package C:
    - `harness answer` takes the `grid_system_missing` values (ADR-0013 §2): `dir1_labels`,
      `dir1_spacings`, `dir2_labels`, `dir2_spacings` together, optional `sheet`, or no value for an answer
      in words only. Per direction at least two distinct, non-blank labels and exactly one spacing fewer,
      each a plain decimal > 0 (no sign, exponent, `inf` or `nan`); anything else is exit 1, nothing
      written. Stored in `answers.json` as arrays: labels as strings, spacings as numbers (`3130` stays an
      integer, `3540.5` a float). The answer itself builds nothing; `harness grid-system` reads it.
    - `harness ask` refuses the producer codes `legacy_ascii_text` (intake) and
      `grid_answer_contradicts_drawing` (grid-system; it no longer falls under read-structure's `grid_`
      prefix) as reader codes (exit 2).
    - `harness ask --amend Q-id [--text T] [--places P ...]` works (it was a stub, exit 3): it changes a
      live, unanswered reader question in place. The id, key and ref stay; the new message and/or `places`
      replace the old ones, which are kept in `amendments` (`at` = the registry run counter, bumped once
      per amendment; only what changed is recorded). The same values again change nothing (status
      `unchanged`). Refused with exit 2 for an unknown, producer, withdrawn or answered question (any
      active answer, simulated included). A live entry missing from `reader-questions.json` is exit 1.
      `harness ask` now checks `reader-questions.json` against the `reader-questions` schema before it
      writes it, and when it reads it (a document that breaks the reader rules is refused, exit 1).
    - `harness status` always writes `gate1.closed`, as `[]` when nothing is closed (W5).
    - `harness status`: an answer to `grid_system_missing` closes it only with its grid values (ADR-0013
      decision 2). The engineer's answer in words only (`{}`) builds nothing, so the question stays in
      `blocking_open`, and a `grid systems:` gate-1 reason gives the `harness answer` command with the
      `dir1_labels` / `dir1_spacings` / `dir2_labels` / `dir2_spacings` values. `harness questions-md`
      lists it with the open blocking questions as "chưa đóng: câu trả lời chỉ có lời", with those values.
    - `status` schema: `gate1.closed` is required (`$id` still 0.1; example updated). A status output
      written before tool wave 3 without it no longer validates; rerun `harness status`.
  - Tool wave 3, package M (marks + callouts):
    - `harness callouts`: every unparsed candidate names its reason family in `unparsed_code`
      (`ambiguous_notation`, `grade_unverified`, `notation_unverified`, `conflicting_values`,
      `member_mark_undefined`, `symbol_glyph_unverified`), counted in `summary.unparsed_by_code`. A character
      in diameter position that is not Ø or %%c (W1b: `2ù20`, `ù14a150` in drawing 290's style Arial, `2Þ16`
      in its VNI styles, U+2300 / U+2205) is an unparsed `rebar_callout` with `symbol_glyph_unverified`,
      never decoded: a non-ASCII letter only in the shapes count + diameter or diameter + spacing (`Đ`/`đ`
      never), the two diameter-like symbols also alone with a number. Before, these texts gave no candidate.
    - `harness callouts` drops nothing silently: text that matched and is no candidate is listed in
      `rejected` (file, sheet, entry id, the text, kind, `reason_code`, reason), counted in
      `summary.rejected` / `rejected_by_reason`: a diameter sign that no pattern reads
      (`diameter_sign_no_notation`, e.g. `Ø<10mm`, a glued `A4Ø16`), a mark-shaped sheet code
      (`sheet_code`), and a mark-shaped text another extractor took (`claimed_by_title_block`,
      `claimed_by_grids`, `claimed_by_levels`). Blocked texts stay in `blocked_entries` only.
    - `harness callouts` raises `callout_unparsed` (blocking for lot specs; callouts is no gate-1 producer):
      one question per file and `unparsed_code` over the unparsed candidates no other question asks (no
      ambiguity, no member mark, no legacy grade group). Subject = the code with the true count; refs = the
      first five examples (text entry ids, verbatim, scan order) and one `sheets` ref with the count per
      sheet. On EVAL-3's set this asks the 554 unparsed Ø-callouts and drawing 290's 538 glyph callouts.
    - Fix: a title-block candidate found by shape alone (the lower-right sheet-code fallback, evidence kind
      `pattern`) no longer consumes a real mark in `harness callouts` and `harness marks` when the sheet
      holds a family of that mark (another unclaimed mark-shaped text with the same prefix, style and
      height): 286's tie-beam mark `gĐ-3` is a mark again. Sheet numbers found the same way without such a
      family (461 `Đn-05`) stay claimed.
    - Fix: a whole `M<n>` text with a bolt size n is a member mark, not a bolt label, in `harness callouts`
      and `harness marks` when its footing family stands next to it: a whole `M<n-1>` or `M<n+1>` that is
      no bolt size, on the same sheet, in the same style and height. 433's footing `M8` (T000555, next to
      `M7`) joins M1–M7; bolt labels elsewhere (161, Steel) are unchanged.
    - `harness marks` reads a mark followed by a length in brackets, `LT1(L=4700)` (267's lintels), as the
      plan mark `LT1`; the length stays in `display_text` only (no size). 267 gains 41 lintel plan marks.
    - `harness marks` (a4) compares plan marks with RC detail headings as a second source besides parsed
      schedules: a title-form plan mark (`DẦM D1 (SL= 02)`, `CỘT C9`, `ĐÀI CỌC ĐC2`) and an English
      `DETAIL OF/ON <mark>` line (161 `DETAIL ON AB-20B`) are headings and no longer the plan side of the
      comparison (they stay plan marks for the prefix question). Matched, schedule-only and plan-only marks
      carry `compared_with` (`schedule` when a schedule row exists, else `detail_heading`), headings are
      listed in `detail_headings` (entry id, sheet, text) and counted per file in
      `matching[].detail_headings`. A match through headings only is not size-compared (reason
      `matched through detail headings only: no schedule row to compare`). `plan_only` is listed only for a
      file with a schedule or a heading; a file with neither is not compared (`none` is never written).
      Changed: a title that used to match a schedule row (`COLUMN C2`) is now a schedule-only key with
      that heading. The heading comparison covers only the families (prefix) that have both a plain plan
      mark and a heading; any other family is not compared through headings, so it gives no plan-only or
      schedule-only finding (433's footings next to column headings only; 286's pile-cap headings with no
      plan label read). `matching[].detail_headings` counts the headings that took part.
    - `harness marks` (W6) writes `summary.mark_sets`: one set per file and mark family (prefix,
      upper-cased as in `member_mark_prefix_meaning`) with `members` (one per key, as drawn, natural order,
      gaps kept), `source` (`schedule`, `detail_heading`, `plan_marks`) and `complete`. `complete` is true
      only when a parsed schedule or the heading sweep lists the family and nothing says the list may be
      short: no plan-only mark in the family, no notation variant, and no unparsed table, header-blocked
      table or blocked mark in the file. Otherwise the report writes "ít nhất". 433: `M1`…`M8` and `GM1`…`GM5`,
      `GM7`, `GM8`, both incomplete (plan marks only).
  - Tool wave 3, package GRIDGATE:
    - `grid_system_missing` takes `no_grid=yes`, alone (ADR-0013 decision 2): the engineer states that
      the file holds no plan that needs a grid (notes, details or sections only). `harness answer`
      accepts it from any role and refuses it with any other key or value (exit 1); `answers` schema:
      `values.no_grid` const `yes`, alone (`$id` still 0.1). `harness grid-system` builds nothing for it
      and keeps the question raised, answered, while the engineer's answer stands. `harness status` closes
      the question on the engineer's `no_grid=yes` only; a simulated one closes nothing. The question's
      message, the `grid systems:` reasons, `harness answer --help` and `harness questions-md` (a "Hoặc"
      line with the command, in Vietnamese) print the option.
    - Fix (review C1, EVAL-3 b1): `harness marks` no longer calls a partial family complete. A heading
      that lists marks (`dẦm ct-1,ct-2`, `CỘT C1, C2, C3`, `DẦM D1 & D2`, `DETAIL OF CP1 & CP2`) gives one
      heading per mark when every item after a `,` or `&` is a whole mark of the same family; before, only
      the first was read (290: `CT` = `ct-1` alone, complete). A list in shorthand (286 `dẦm d2-4, 5`,
      `dẦm d2, 3, 4, 5 , 6, 7, m-12`) is never expanded and names no mark (no false `d2`); it is listed in
      `warnings` with its entry id and keeps the families it may name incomplete. `complete` now needs a
      parsed schedule, or detail headings and plain plan marks that name the same keys (headings alone
      list the drawn details, not every member), and no blocked plain text anywhere in the file (a blocked
      text may be a heading). Known set: 290 `CT` = ct-1, ct-2; complete sets 10 → 3 (433 `C`, Steel_02
      `C`, `MB`); 286 loses 7 heading matches `d2-4` … `dm-4` (they came only from shorthand lists; now
      plan-only) and the false schedule-only `d2`; 290 gains schedule-only `d2`, `d3`, `d4` (from
      `dẦm d1 , d2`, `dẦm d5 , d4 , d3`) and 3 notation-variant groups.
    - Fix (review M2): `harness callouts` no longer drops glyph callouts outside the two narrow shapes.
      Glyph callouts joined by `+` or `/` (`2ù20+2ù18`, `2ù20 + 2ù18`, `2ù20/2ù18`, `2Þ16+2Þ18`) are one
      unparsed `rebar_callout` with `symbol_glyph_unverified` (rule `SYMBOL_GLYPH_JOIN`), as their Ø twins
      are one candidate; before, they gave no candidate and no `rejected` row (the spaced form gave two).
      A glyph before or between digits that no shape reads (bare `ù12`, `ù8@150`, `Ô1`) and a U+2300 /
      U+2205 no pattern reads are listed in `rejected` with `diameter_glyph_no_notation`: not a candidate,
      so a slab-panel letter raises no blocking question. Known drawings: no change (none of these forms
      occurs; 290 keeps 507 `ù` + 31 `Þ` candidates).
    - Fix (review, tie): when a sheet's shape-only (`pattern`) title-block candidates of one field have
      two values or more, `harness callouts` and `harness marks` claim none of them: sheets already chose
      none and raised a blocking `title_field_conflict`, so a mark among them stays a member mark in
      `marks.json` instead of a `claimed_by_title_block` row. One shape-only candidate (461 `Đn-05`) stays
      claimed. Known drawings: no change (no such tie in their sheets documents).
- Tool wave 4 (EVAL-4 fixes; the packages fill in the behaviour):
  - Tool wave 4, seam. Schemas, all new fields optional, `$id` still `0.1`; nothing reads or writes them
    yet:
    - `text-index`: per entry `printed` (boolean), `not_printed_reasons` (`entity_invisible`,
      `attribute_invisible`, `layer_off`, `layer_frozen`, `layer_no_plot`) and `print_uncertain_reasons`
      (`insert_invisible`, `attmode_not_normal`, `viewport_frozen`, `defpoints_layer`). The flags
      `layer_off`, `layer_frozen` and `attribute_invisible` stay in `flags`.
    - `marks`: per table `blocked_header_entries` (entry ids of blocked header cells; `header[]` keeps a
      placeholder only) and a header `cell` may have `entry_id` null for that placeholder.
    - `sheets`: `title_block.job_number` (shaped like `sheet_number`) and candidate field `job_number`.
  - Tool wave 4, seam: `tekla_harness.visibility` (`is_printed`, `not_printed_reasons`; a missing `printed`
    counts as printed); question code `text_visibility_uncertain` (constant in `questions`, Vietnamese
    row in `harness questions-md`, raised by package T); flag `--include-hidden` on `harness sheet-text`
    and `harness find-text` (also show entries that do not print, marked), exit 3 with nothing run until
    package T lands. A synthetic R2018 (AC1032) DXF is tested through intake and read-structure.
  - Tool wave 4, package M (marks + callouts):
    - `marks`: a blocked schedule header cell keeps only a placeholder in `tables[].header[]` (`entry_id`
      null, verbatim text and reason kept); its id is listed in the table's `blocked_header_entries`, so no
      blocked id is cited outside a `blocked*` list (EVAL-4 criterion 2, M2).
    - `marks` and `callouts` leave out every text entry that says `printed: false` (a hidden ATTRIB is no
      plan mark, header keyword, table cell, callout or footing-family evidence, and does not set the line
      tolerance); a file with such entries gets one warning with the count per `not_printed_reasons`
      (the documents have no counter field). An index without `printed` reads as printed. Repro: 271
      phantom `dẦm d2-1` on 12 sheets.
    - `marks` and `callouts` (EVAL-4 A4a): the ATTRIBs of a rebar-callout block (an INSERT with a spacing
      value `a150` / `A200` among its ATTRIBs, or a `THEP` / `KHOANGCACH` tag) are parts of a callout, not
      member marks; a strength class (`RB 500`, `CB 400`: grade prefix and verified yield class) and a signed
      level (`cos -300`) are not marks. `callouts.json` lists them in `rejected` (`callout_part`,
      `grade_token`, `level_token`); `marks.json` has no such list, so one warning per file gives the count
      per reason and five examples. Repro 278 (D6..D25, A150, `RB 500`, `cos -300`); second files 285, 286
      (`SH thep` blocks).
    - `marks` and `callouts` (EVAL-4 A4c): a steel profile (`HEB-650`, `IPE 300`, `UC 254`: series letters
      and a depth of 50 or more) and a detail label (`DET-2`; the bubble `A1` of a `DETAIL - A1` heading on
      the same sheet, when every mark-shaped text of its prefix on that sheet is such an id; English
      `DETAIL` headings only) are not marks
      (`steel_profile`, `detail_label` in `callouts.json` `rejected`; a warning in `marks.json`). A
      `job_number` title-block candidate is claimed by the title block even when found by shape alone, so
      `J-01` is never a mark next to J-02, J-03. Repro 180 (`HEB-650`, `A1` x16, `DET-2`).
    - `marks` (EVAL-4 R-e, R-g, R-k): a section-cut label (letters, a blank, `n-n` with the same number
      twice: `mc 1-1`, 355 on 286) is not a mark (`section_label` in the per-file warning); a heading may be
      glued to a bracket (`dẦm d2-7(sl= 01)`, 286) and may start with the pile-cap word `đài` (`ĐÀi dm 1`,
      285: the DM family appears in the mark sets).
    - `marks` (EVAL-4 R-c): a schedule drawn with lines may have ONE data row: when its mark cell is allowed
      text with a mark's shape (or a member-word title) and the row has a second cell, it is a table, not an
      `unparsed_tables` entry (161's crane-beam table: CB-01 is matched, not plan-only). Without lines two
      rows are still needed.
    - `marks` and `callouts` (EVAL-4 271): a whole text `<letters><n>` that a callout pattern claims (`bm-1`
      read as a plate tag) is a mark when it stands in a run of three consecutive numbers of one prefix,
      text style and height on one sheet (271 `bm-1` .. `bm-7`: the BM footing family, 16 plan marks); a
      plate number alone (`BM12`) stays a plate. Texts that do not print take no part.
    - `marks` (EVAL-4 R-f): when one mark of a family appears three times or more as a title-form text
      (`dẦm d-1`) on a sheet, every title-form text of that family on the sheet is a plan label, not a detail
      heading (form `plain` / `with_size` / `sub_number`, no `title_member_word`); one warning per file counts
      them per sheet. 290 `dẦm d-n`: matched 5 -> 16, schedule_only 17 -> 5. Review fix C1: a family
      with a quantity tail (`(sl= 02)`, `SL: 2`, `số lượng 5`) on the sheet is never demoted: a detail
      sheet heads one beam with its count and labels its cross-sections with bare titles (285 KC-17).
    - `marks` (review M1, SEAM-2): a data cell whose text the font gate blocks has `entry_id` null and its
      id is listed in the table's `blocked_cell_entries`; `blocked_marks` keeps the id. M2 on the marks
      test fixtures (gate: 1, inferred: 2) is 0. A cell of a header-blocked table with allowed text keeps
      its id (only ids the text index blocks are moved).
    - `marks` and `callouts` (review M3): a numbered run (`bm-1` .. `bm-7`) is a mark family only when a
      printed text of the file names its prefix in a member-word heading (`bẢn mÓng bm-3`: a line that ends
      with the mark and has a `MEMBER_WORDS` word before it); plate tags numbered in a connection detail
      (`BM1 BM2 BM3`, `PL1`..`PL4`) stay plates. `MEMBER_WORDS` now lives in `callouts` (`marks` imports it).
  - Tool wave 4, package T (text), visibility: `harness extract-text` fills `printed`,
    `not_printed_reasons` and `print_uncertain_reasons` on every entry. Not printed: group 60 on the entity
    (TEXT, MTEXT, ATTRIB, MULTILEADER, DIMENSION, also on block content), ATTRIB flag bit 1 (`invisible`
    stays that flag only), the effective layer off, frozen or with the plot flag 0. Kept printed but
    uncertain: an INSERT with group 60 above the entry, `$ATTMODE` other than 1 on an attribute (mode 2 shows even
    a flag-1 attribute, so that one is uncertain; mode 0 hides every attribute, so a flag-1 attribute is not
    printed), a layer frozen in some viewport (model space text only) and the `Defpoints` layer
    (ezdxf rewrites its plot flag to 0 on every load, so only its name counts). Entries stay in the index;
    the flags `layer_off`, `layer_frozen`, `attribute_invisible` and `text_gate` are unchanged. Known
    drawings, not printed: 271 305 (232 on real entities, the exact set of the EVAL-4 hidden list, plus 73
    rebar callout TEXT copies inside anonymous blocks), 278 46, 285 6 (dimension texts on a layer with plot
    0), the other seven 0.
  - Tool wave 4, package T (text), question: `read_dxf.text_visibility_questions(text_index, rel)` builds the
    one non-blocking `text_visibility_uncertain` question of a file that has printed entries with
    `print_uncertain_reasons` (a ref per reason with its entry count, then five example entry ids; `count` is
    the number of entries). Intake calls it from seam 2.
  - Tool wave 4, package T (text), wording: the `harness find-text` note no longer tells the engineer to
    approve the font row for `legacy_ascii_suspect` entries. It names the `legacy_ascii_text` questions as
    recording a reading that unblocks nothing, and mentions the font row (with its questions) only for
    entries blocked by an encoding reason.
  - Tool wave 4, package T (text), gate: unchanged. A font-evidence lift for plain Unicode text in a TrueType
    file (271 `KÍNH`) was built and reverted after review: it let TCVN3 / VNI strings past the gate. Such text
    stays blocked `encoding_unknown`; `tests/test_legacy_text_stays_blocked.py` keeps it so.
  - Tool wave 4, package S (sheets and levels):
    - Texts that do not print (`printed: false`, written by package T) give no sheet number, title field
      or level: `harness sheets` leaves them out of every label, value, title-block evidence, corner code
      and mark count (they keep their sheet in `text_ids`); `harness levels` gives no candidate and no
      storey name from them. Each file gets one warning counting them (and, for levels, the level-shaped
      values in them). An index written before `printed` existed still lowers confidence by `flags`.
      Measured with the 271 hidden set emulated from DXF group 60 (232 texts): the phantom levels
      +3.850, +3.450 and +3.050 (86 candidates) leave `levels.json`; the real `printed` field shows only
      once package T lands.
    - Sheet numbers by label (V3): a title-field label pairs with its value inside its title-block cell
      (the box between the nearest drawn lines; a label with no cell or an empty one keeps a reading-direction
      test: on its row to the right, with the value's box overlapping the label's rows, or just below it),
      one value per label and one label per value, nearest first. The old test (value centre within
      0.6 label heights of the label centre) missed values set larger than their label. New title field
      `job_number` (labels `JOB NO.`, `SỐ HĐ`, `MÃ CÔNG TRÌNH`, tags `JOBNO` ...): `title_block.job_number`
      (null when absent), a non-blocking `title_field_conflict` when its candidates disagree; its value is
      never a sheet number, not even as a corner code (180 `J-01` had become the number of 3D-1/3D-2).
      Known drawings: 180 numbers 2/8 -> 8/8 detected (P-01, P-01A, P-01B, P-02A, P-02B, P-04, 3D-1, 3D-2),
      its `sheet_number_duplicate` and six blocking sheet-number `title_field_conflict` questions leave; 264 gains
      `job_number` 08/2008 VKH; 278 gains low `title` candidates; 271, 285, 286, 290, 161, 267, 433 and
      Steel_01: no change. For marks, the entry ids of the number and job values are
      `title_block.candidates[].evidence.value_text_id` (fields `sheet_number`, `job_number`).
    - Title-block frame turned by a hair, drawing-list header (F6): a closed rectangle whose edges miss the
      axes by up to 1e-3 of its length (0.06 degrees; was 1e-6) is a frame, so a title-block INSERT scaled and
      turned by 0.002 degrees is a sheet (271 KC-00, bbox 164846 234376 215925 270497: 34 -> 35 sheets, the
      sheet ids after it shift by one). A sheet-number label whose value heads a column of two or more
      further sheet codes is the header of a drawing list: no candidate, one warning (271 `drawing no` over
      `dm-00`, `kc-00` ...: the drawing-list sheet now reads `kc - 01` from its own title block, and the
      blocking `title_field_conflict` becomes a blocking `sheet_number_duplicate` with the foundation plan,
      which prints the same number). Other known drawings: no change.
    - Levels (V4): a sign set apart from its digits by any number of spaces is a level sign when the sign
      starts the text (`+  0.000`, written with two spaces on 278: its eight storey levels +0.000 ... +28.650
      were missing and Q-067 said "no datum"); after a level word or `(` the one-space rule of tool wave 3
      stays, and `TẦNG 2 -  3.600` is still a name, a dash and an unsigned number. A storey name set beside
      the value counts as on its row when the text boxes overlap vertically or lie within 0.1 of the taller
      text's height (was: centres within 0.75 of the value's height, which missed a taller name text: 285
      `+0.450` with `tẦng 1`). Known drawings: 278 levels 4 -> 14 (the ten key levels ±0.000 TẦNG 1 ...
      +28.650 MÁI, all named); 285 names TẦNG 1-3 on +0.450, +4.350, +7.950; 290 gains -0.050, +1.140,
      +2.430, +3.850 (written `+  1.140` on one sheet); 271 names +7.660 MÁI; 264, 180, 286, 161, 267, 433,
      Steel_01: no change.
    - Review fixes (package S): the drawing-list header rule counts only a table column, a chain of rows with
      the first directly under the value, each next one within 3 row heights of the previous and of about its
      height; sheet-code-shaped marks further down the sheet no longer drop a real sheet number (a title block
      in the right strip with `C-1`, `C-2` 21 000 below it lost its number). 271 `kc - 01` / `dm-00` is unchanged.
      A level sign set apart from its digits by more than one space is read only for a bare value (nothing but
      the number, a unit or a closing bracket after it): `-   2.500 kN/m2` is no level. Known drawings: no
      change (the four 290 values are bare).
      A storey name beside the value is on its row by the old rule (centres within 0.75 of the value's height) or
      by the box rule of c09581a; the box rule only adds pairs (it had dropped a small name centred below the
      value). Its 0.1 limit: named candidates on the 11 known files are the same for 0.05 and 0.1 (285 needs
      more than 0), and 0.2 adds two names on 271.
      Title-block cell lines come from printed geometry only: a line or polyline edge on a layer that is off,
      frozen or set not to plot, or with its own invisible flag (group 60), no longer closes a cell; a block
      entity on layer 0 takes the layer of the INSERT that holds it (`Placed.outer_layer`). Known drawings:
      no change.
    - Re-measure fix G1 (package S, levels): a storey name belongs to the nearest level text. A word that has
      another level text (any text with a level in it) nearer, centre to centre, than the value it stands beside
      is that text's label and does not name the value; it still counts as a storey word near an unnamed level, so
      the storey-selection question stays. 271 column strips (`mÁi` over `tỪ +7.660` / `ĐẾn +8.710`, 1008 from
      a bare `+7.660`) no longer name T001938 / T002226, and the storey heights go back to the listing of the
      base. 278, 285, 290, 180, 264, 286, 161, 267, 433: no change.
      Review follow-up (fix/w4-s2): a level text is exempt as a nearer owner only when it is stacked below the
      value in its column, or when its whole text (lines joined) is over 40 characters.
  - Tool wave 4, seam 2: `harness intake` now raises the non-blocking `text_visibility_uncertain` question
    (one per file with printed entries that have `print_uncertain_reasons`, built by
    `read_dxf.text_visibility_questions`); it comes after `legacy_ascii_text` in `questions.json` and
    `ask.py` leaves its ownership to intake. The intake schema's question-order description lists it.
  - Tool wave 4, seam 2: `harness sheet-text` and `harness find-text` hide entries that do not print by default;
    `--include-hidden` lists them marked `printed: false` (the exit-3 stub is gone). `sheet-text.schema.json`
    (`$id` still `0.1`): entry and hit `printed` (const false, only on a hidden entry) and
    `counts.not_printed_in_scope`. Meaning change: by default `counts.assigned`, `matched`, `legacy_font_gate`
    and the find-text `entries_searched`, `unassigned_entries` and `blocked_in_scope` cover PRINTED entries
    only; `not_printed_in_scope` counts the rest, and with `--include-hidden` all entries are in. The
    `list-sheets` `text_count` and `blocked_text_count` still count every entry.
  - Tool wave 4, seam 2: `marks.schema.json` (`$id` still `0.1`): per table optional `blocked_cell_entries` (entry
    ids of DATA cells whose text the font gate blocks; such a cell keeps `entry_id` null). The cell `entry_id`
    description now names both null cases (header placeholder, blocked data cell). Nothing writes it until
    package M.
  - Tool wave 4, seam 3: `sheets.schema.json` (`$id` still `0.1`): `drawing_list` gets an optional
    `header_text_ids` (ids of drawing-list header values the title-block scan drops because they head a column
    of sheet codes). `sheets` writes it; `marks` and `callouts` claim these ids, so a header value such as
    `DM-00` is no longer a plan-only member mark. Claim is by id: a real `DM-01` elsewhere stays a mark.
    Also (fix/w4-s2 review): `header_text_ids` gets `minItems` 1 / `uniqueItems`, and `drawing_list` gets an
    optional `row_text_ids` (same shape; ids of the sheet-code rows under the header). The rows are claimed by
    id like the header, so `DM-01`, `DM-02` under `DM-00` are no plan-only marks either.
  - Tool wave 4, package G (grids, `grids.py` and `grid_system.py`; no schema change):
    - Text, lines, circles and dimensions that do not print are left out of bubbles, labels, axes and
      dimension evidence (not-printed text entries via `visibility.is_printed`; geometry by its own group 60
      and its layer off / frozen / plot 0, read from the DXF). An entity on layer 0 inside a block and the
      contents of an invisible INSERT stay (Autodesk does not settle them). What was left out is counted
      in `warnings` (the grids schema has no counter field).
    - Obround bubbles (two straight LINEs and two semicircular ARCs of one radius around the label) count as
      bubbles, with half the overall length as radius (EVAL-4 180: 0 of its framing-plan bubbles were found).
    - The grid-spacing units evidence uses plan systems only: `files[].grid_spacing_median` of
      `grid-systems.json` is the median spacing of the file's systems with two or more independent views
      (a single-source key plan never decides; a file with only single-source systems takes the median of
      its systems' medians), so a small key plan no longer raises `units_answer_contradicts_evidence`
      (EVAL-4 180, Q-199). `grid_units_doubt` in `grids.json` takes the median of the views' medians.
    - A line or circle on a layer that has no LAYER table row is read as a plain printing layer (a
      line there was dropped before, counted in `walk_skipped`).
    - A bubble pairs with the axis line of its sheet's axis style (the layer and linetype most axes of the
      sheet are on, when one clearly leads) before a nearer line of another style: another end candidate
      of the style, or a line of the style drawn through the bubbles at both of its ends (EVAL-3 285:
      the end bubbles took wall lines 110 outside their axes; spacings 3240 / 4700 become 3130 / 4590).
      A bubble already on a line of the style counts as the other end of that line, so the left bubble of an
      axis `a` no longer stays on a wall line 90 under it (285: `a a b c` becomes `a b c`).
    - An axis that differs from its family in two of three things is no axis: its size (bubble radius or
      label height more than 20 % from the family median), its block (the circle's outermost block name) or
      its line (layer + linetype); for block and line the family value is the one more than half of the
      axes share, and a family needs three axes (EVAL-4 264 `5` / `4` on a HIDDEN line, 278 section marker
      `T`, 271 rebar bubbles `12` / `14` / `20`). The bubbles are listed as unpaired bubbles and the
      warnings of `grids.json` name each axis and what differs.
    - A `*` may end an axis label (`2*`, an intermediate axis; EVAL-4 278). Two plans stacked on one sheet,
      whose shared axes are printed once, are two views: when exactly one family of a view repeats its
      labels in alike runs of at least two axes (`a b a b`, never `1 2 2` or `1 2 1 3`), the view is cut into
      one view per run and every other axis of it belongs to each (EVAL-4 278 KC-01). `bubbles_paired` counts
      each bubble once.
    - `harness grid-system`: a system of one direction seen in one view (any number of axes: rebar or pile
      marks, 3D views, details: EVAL-3 286 `b bt`, 290 `8 1` / `6 1` / `3 16`, 180 model#05 / #06) is not
      proposed as a grid system when its file has a main system, a two-direction system with three or more
      axes in each direction from any number of views (180: every plan is seen once, as half of one grid).
      It is listed in `unassigned_families` with the reason, counted in `summary.families_unassigned`, and
      raises no `grid_system_axis_unassigned` question. 180: 8 systems / 31 blocking grid questions become
      5 / 17; the other ten known drawings are unchanged.
    - Schema descriptions (no field changes, `$id` unchanged): `grid-system` `files[].grid_spacing_median` is the median of the file's plan systems (single-source case stated); `grids` `unpaired_bubbles` also holds the bubbles of set-aside axes and views, which have lines.
    - A view of one direction (one family of two or more axes, nothing across it) whose shared labels contradict
      every other family that shares two or more of them, while two or more of those families agree with each
      other, is set aside as an elevation or section: no grid system, no cross-check partner (EVAL-4 278
      KT-08: `1 2 4` at 10107 / 5192 against 25 plans of `1 2 2* 3 4`). The bubbles are listed as unpaired and
      a `grids.json` warning says why; a plan (two directions) is never set aside.
    - `harness grid-system` prints `blocking_without_engineer_answer` (blocking questions the engineer has not
      answered) and a `counts_note` beside the questions document's `answered` and `blocking_open`, which
      count a simulated answer as an answer while `harness status` still keeps that question blocking, so
      `blocking_open 0` read as "nothing left to answer".
  - Tool wave 4, FP4 (marks): a heading whose mark has a dash glued before the quantity tail
    (`DẦM D6.01- sl:04`, `sl=` / `số lượng`, any case) now reads the mark (`_MARK_HEAD`), also on the last
    list item (`DẦM D1, D2- sl:02`). A dash before another mark (`dẦm d 1- D 20,`, `dẦm  d  2- d 3+d 4, d 5`)
    is range shorthand: the heading is recognised with no single mark (`[]`), so the shorthand warning is
    raised and the family is reported "at least". No change on the 10 known drawings.
  - Tool wave 4, package FP1 (sheets, `sheets.py`; no schema change): frames drawn as four LINEs inside one
    block INSERT (dev-corpus s387: 29 `khung ban ve` inserts, 0 sheets before). Only as a fallback, in a space
    where no closed polyline rectangle was accepted as a frame, the LINEs of one INSERT occurrence (same
    top-level handle, block path and occurrence) are joined into axis-aligned rectangles (split or doubled
    edges allowed) and go through the unchanged `_find_frames` rules. `detection.method` stays
    `frame_rectangle`; one `sheets.json` warning per file says the frames are LINE-drawn. Spans too short
    to be a frame edge (under 40 text heights, 10th-percentile height of the space) are dropped before the
    60-level cap; a still-hit cap is counted and reported in the file's warnings
    (`line_frame_level_cap`). `frame_layer` is the layer of the LINEs on the rectangle's border and the
    sheet evidence says it was joined from LINEs; `summary.frame_candidates_rejected` keeps the polyline
    groups. Loose top-level LINEs stay a documented gap.
  - Tool wave 4, package FP2 (grids, `grids.py`; no schema change, no new question kind): a sheet with no view
    built from lines gets one view from a lattice of unpaired same-label bubble pairs (dev corpus s774: grid drawn
    as bubbles plus pieces of line shorter than MIN_AXIS_LENGTH, 0 grid systems). Each pair is two bubbles at least
    MIN_AXIS_LENGTH radii apart; a pair counts when it crosses a pair of the perpendicular direction (ORTHO_TOL),
    and the view needs at least `TWO_BUBBLE_SEED_MIN` (2) such pairs in each direction. A single row of pairs (bar
    numbers, details) seeds nothing, and a sheet that already has a line-backed view takes no second one. The axes
    are `two_bubbles` (low) and raise the blocking `grid_two_bubble_axis` question, one per axis.
    Follow-up after review (REVIEW-FP2, engineer approved the rule 2026-11-11):
    - Lattices are the connected components of the crossing graph within each pair of perpendicular directions
      (any orientation), so two plans on one sheet seed two views instead of one view with a gap.
    - A label with more than two bubbles on the sheet (a detail or section mark beside the plan) no longer
      drops its axis from the lattice: the one pair that runs the way its kind runs (numbers one way, letters
      the other) and crosses an axis perpendicular to the axis it runs along (not to the pair itself, which
      may be a little off) is the axis. With several such pairs, or with pairs that run along the grid but
      cross nothing, none is taken, the bubbles stay unpaired and a blocking `grid_two_bubble_axis` question
      names the pairs. The pairing of bubbles that join a line-backed view is unchanged.
    - An undrawn (`two_bubbles`) axis takes its position from the dimension(s) drawn between it and a placed
      neighbour (status `measured` or `agrees`, DIMLFAC 1, agreeing within half the rounding step), over the
      bubble centres, with no question: bubble placement on 285's slab and beam sheets is up to 1 mm off the
      grid its dimensions measure, which split a separate top-ranked grid system (`0 4250 3729` against the
      key's 3730) and added three blocking `grid_system_conflict`. A drawn axis never moves; a pure lattice
      is placed from its first axis; in a family with drawn axes an undrawn axis is anchored on a drawn
      neighbour, and a run of undrawn axes beyond the last drawn one is chained from it, each through its own
      spacing's dimension. An axis whose dimension is missing or disagrees (or whose two neighbours imply
      positions more than half the rounding step apart) stays at its bubbles and anchors nothing. The
      spacing's `measured` keeps the bubble-centre value, and its provenance cites the extents and handle of
      the DIMENSION entity (`handle unknown` when it has none), only for the spacing it was placed through.
      A placement that would reorder the axes is dropped with a warning naming the view and the axes.
    - A dimension is judged again after the undrawn axes have moved: an overall dimension whose text equals
      the dimensioned span no longer keeps a stale `differs` (and a blocking
      `grid_dimension_override_mismatch`) because the bubbles were 1.5 mm off, and a text equal to the
      bubble span is asked once the axis has moved off it.
    - Decided without asking (engineer-approved rule, 2026-11-11): `_match_dimensions` accepts a dimension
      whose extension points lie within `DIM_POINT_TOL` x r of the axes (0.05 r, 17 mm on 285), and a `<>`
      dimension inside that window is accepted as `measured` without a question. This window is wider than
      the 5.1 mm KC-01/02 conflict, so a difference of that size on a lattice sheet is resolved toward the
      dimension.

### Changed
- Work-folder lock (ADR-0011 amendment 2026-11-20): a command that finds the lock held waits for it, retrying every
  0.2 s, instead of exiting 3 at once. The wait is `HARNESS_LOCK_WAIT` seconds when set (a number >= 0, else exit 2),
  else 60 s when anything exists at `parts/manifest.json` (the shared `manifest_present` rule; a path that cannot be
  checked stops the command with exit 3), else 0 (the old behaviour). A wait that ends in success
  prints `lock: waited <s> s for harness <command> (pid <n>)` on stderr; one that runs out is exit 3 naming the seconds.
  A lock error other than "held" and a holder record from another OS are never waited for.
- `spec.schema.json` (0.1, review of P15-3): `poly_members[].name` refuses the reserved Names `PILE` and
  `PILE_CAP`; the schema reject tests now assert on schema errors only (no `check_spec` masking), with
  lot 0 cases for members, poly members, walls and empty grids.
- Docs: the documented Tekla target moves from 2024 (`Tekla.Structures.*` 2024.0.4) to Tekla 2026
  (2026.0.3), engineer decision Q1 of ADR-0015. ADR-0009 Amendment 3, ADR-0007 note, the contract
  Build section, `tekla/README.md`, `tekla/api-notes.md` (2024 facts kept and marked) and the roadmap.
  NuGet pin is documentary until `TeklaAdapter.csproj` exists. No code, no schema change.
- `docs/tekla-cli-contract.md` (ADR-0015, ADR-0016): subcommand table updated for grids, poly members,
  slabs, polygonal caps, walls and opening cuts; `--lot 0` accepted; tag UDAs also for grids; rule 6
  matching for the new kinds; new rules 7 (closed-world spec read), 8 (lot 0 and grid, poly member
  construction), 9 (lot 0 after it is built, with the `--allow-untagged-shift <question_id>` override
  while no member lot exists), 10 (Tekla 2026: parts not bound to levels), 11 (concrete parts) and
  12 (openings); open questions list To verify T1-T10 and C1-C16. No new subcommand, no new exit code.
- `docs/tekla-cli-contract.md` (review of P15-8, errata of the ADR-0015/0016 drafts): restores
  refusals the ADRs require: the T9 gate on additive lot-0 `update` and the override flag, the
  non-rectangular wall opening before C2/C12, the exit `3` for a failed cut tag write, enumeration
  (not `GetObjectsByBoundingBox`) for the untagged-part clause, Position refusal per (type ×
  material type) row, and a new rule 13 listing the To verify gates (T4 for every write; T1, T2, T3,
  T9; C4 to C9, C2 and C12). Rule 12 allows, in the C7-failed fallback only, the one delete inside
  `build` (the tagged cutter, this run's tags, journalled; `update` never deletes); steel members
  refuse until their Position rows exist (C2); rule 6 reports Name differences other than
  `PILE`/`PILE_CAP` instead of refusing; an `update` that would add an opening in the fallback
  refuses (exit `5`); the untagged-part extent is the union before and after the change. Second and
  third reviews (P15-8B, P15-8C): rule 11 keys its Position refusal on (kind × material type), array
  kinds included; rule 13 adds T2 for grids and every gate is a code constant opened only by an
  engineer-merged commit; openings need C4, C5 and C6 passed, and either C7 passed or C7 failed and
  C8 passed; one ordering sentence puts rule 1 first, then every refusal of rules 3 to 13 before the
  backup and the first write; exit `3` covers a failed cut tag read-back. Engineer decisions
  2026-11-11: an `update` whose spec lacks an existing object of the lot refuses (exit `5`) and
  lists each `SPEC_ID`, `RUN_ID` and GUID (rule 5); rule 13 also gates the profiles of pad footings, pile caps
  (both kinds), strip footings, slabs, walls and opening cutters on C1, the rectangular wall cutter
  on C10, piles built as columns on C14 and the backup macro on To verify #13; gates are keyed on
  the full `tekla_version`, service pack included, and a version with no recorded evidence keeps
  every gate closed; the rule 13 list is complete and `rollback` waits only for T4, #13 and the
  opening gates (engineer, 2026-11-11). Fourth review (P15-8D): the Order paragraph's closed list of
  mid-run stops adds a failed journal write and the rule 1 re-check right before `CommitChanges`;
  the missing-object refusal of rule 5 covers any `RUN_ID` and is decided before the backup. No new
  subcommand, no new exit code.
- `spec.schema.json` (0.1, ADR-0015): lot 0 setup lot with `grids` (each with an engineer-confirmed
  `origin` and `rotation_deg`, line positions absolute in the grid's frame, `y_lines` empty for a
  one-direction grid; levels as each grid's Z planes); `poly_members` (Tekla PolyBeam, `points[]`
  with `none`/`arc_point` chamfers); `members` stays required and may be empty, so lot 0 carries
  `"members": []`; `lot` minimum 0. `spec.example.json` updated: every member point's provenance
  traces to the storey-levels answer (ADR-0015 rule (f), OQ-B). Its `spec_sha256` in
  `spec-receipt.example.json` follows.
- `spec.schema.json` (0.1, ADR-0016): `members[].type` gains `pad_footing`, `pile_cap`, `pile`,
  `strip_footing` (reference lines per type; `class` required and Names `PILE`/`PILE_CAP` reserved
  for piles and pile caps); new `slabs` (horizontal ContourPlate, top-face outline, thickness),
  `polygonal_caps` (ContourPlate pile caps, class required) and `walls` (straight PANEL, base centre
  line, thickness, height); slabs and walls carry nested `openings` (BooleanPart cuts, corners
  only, `spec_id` at most 60 characters); lots >= 1 may hold only slabs, caps or walls; lot 0 holds
  none. New examples `spec-lot0-grid`, `spec-lot0-rotated-grid`, `spec-poly-members`,
  `spec-foundations` and `spec-slab-wall`; the schema-level reject set is in `tests/test_schemas.py`.
  The semantic rules (ADR-0015 (a)-(h), (r), (s); ADR-0016 (i)-(q)) follow in the `check_spec` package.
- `check_spec` (ADR-0015 decision 6): rules (a)-(h), (r), (s) for grids, levels and poly members -
  `spec_id` unique across `members`, `poly_members` and `grids`; grid name, label, position and
  `z` rules; composed Coordinate/Label strings at most 1024 characters; elevation and grid-frame
  provenance must reach an `engineer_answer`; poly point geometry; low confidence at any depth of an
  item; every `engineer_answer` carries a `question_id`.
- `check_spec` (ADR-0016 decision 9): rules (i)-(q) - `spec_id` unique across slabs, polygonal caps,
  walls and every opening; vertical pad footings, pile caps and piles (start 1 mm above end, same plan
  point within 0.1 mm) and horizontal strip footings; closed outlines of slabs, caps and openings (point
  spacing, simple polygon, arc points, counter-clockwise with area of at least 1 mm2, wall openings in
  the basis Z x wall direction); one z per slab or cap; openings inside their slab or wall rectangle and
  not overlapping each other; elevation provenance for the new paths; low confidence in slabs, caps,
  walls and each opening, with an opening's own `question_ids`. `SPEC_RULES_VERSION` is now 2 (one bump
  for ADR-0015 and ADR-0016); `spec-receipt.example.json` and the C# `SpecLoaderTests` example assert follow
  it. The C# `MinimumRulesVersion` stays 1 until P15-6.
  Review fixes: geometry rules fail closed on overflow (inf/NaN is a refusal with "geometry cannot be
  evaluated", and the 0.01 mm step check no longer raises on values above 1e306); a slab opening edge
  must not cross the slab outline (concave slabs); two consecutive poly member segments must not fold
  back, first and last included. Tests pin six tolerances the first mutation run left loose.
- Question lifecycle (tool wave 2, EVAL-2 fix 5):
  - `grid_system_conflict` keeps its Q-id across a units answer and a select rerun: its key is built from
    both sides' file, view and family ids and their shared labels; the system ids and the spacing
    differences (in mm once units are answered) moved into the message. Existing answers to a conflict go
    stale once (they never closed it). A conflict the `grid_system_select` answer settles carries
    `closed_by` {select question id, not_selected | separate}, `conflicts[].question_id` names its question,
    and a system's `conflict` flag stays only while one of its conflicts is open. `lifecycle.closures`
    returns these closures from a fresh `grid-systems.json`.
  - `harness intake` raises one blocking project-level `file_set_relation` question when two or more DXF /
    DWG files were read (one ref per file with its sha256; a file added, removed or changed asks again).
    `harness grid-system` reads its answer (`set1=a.dwg,b.dwg set2=c.dwg`): grids of two sets never merge
    into one system and are never compared; `grid-systems.json` records `file_sets` (pending, answered or
    single). While it is open, a conflict between two systems with no file in common does not block
    ("pending Q-x"); the answer is part of the answers `harness status` checks grid-systems.json against.
  - `harness read-structure` grid refs name the grid `families` they cite (the last listed ref of a
    truncated question also carries the unlisted refs' families; none when they are not all known).
    `lifecycle.closures` closes a read-structure grid question (`rejected_systems_only`) only when every
    family it cites belongs to a system the `grid_system_select` answer leaves out; a family of a selected
    system, of no system, or a ref without families keeps it open; `grid_gate1_confirmation` is never closed.
  - `grid_units_doubt` is closed (`units_answered`, naming the units question) once the same file's
    `units_confirm_all` has an active answer.
- `knowledge/font-encodings.csv`: the three seed rows are approved by the engineer (2026-11-07) after
  reading decoded samples: `VHARIAL.TTF` and `vntimeh.shx` = TCVN3, `vn_vni.shx` = VNI. Text in these
  fonts is now decoded instead of blocked by the legacy-font gate. The engineer also endorsed the
  `.Vn*…H` = TCVN3 capital-font naming convention that `encoding.font_hint` already applies.
  Test fixtures that need a blocked font now pin their own proposed-row table instead of the shipped one.
- Tool wave 2, package P1 (fonts and text access; EVAL-2 fixes 2a, 2b, 1a, 4, 11):
  - `encoding.font_hint(style, font_file, family)` also reads the text style's TrueType family (ACAD
    XDATA), after the style name and the font file: a `.Vn*` family gives TCVN3 and a `VNI-*` family VNI;
    a Unicode-looking family decides nothing (a legacy font file may carry one; the knowledge table then
    decides). The `H` capital-font rule applies to the family too (default D3, reversible); when the
    style name and the family disagree on case, the hint is null. `harness extract-text` records such a
    decision as `decode.source` / `run_details[].font_source` `style_family`; `harness read-dxf` lists
    `matched` field `family`. A `.Vn*` family now decides before an approved font-file row, so those
    styles carry no `knowledge_patterns`.
  - `harness extract-text` flags `legacy_ascii_suspect` (confidence low) on pure-ASCII text that looks like
    Vietnamese written in ASCII by a legacy font: a slash before a letter or brace (`4/g14`, `BT LO/ST`;
    not before a unit such as `kG/cm2` or a word of 3+ letters such as `Cu/PVC`) or an uppercase tone
    letter S F R X J after a vowel (`chi tiESt`, `haFn`). Only runs in a TCVN3 / VNI font, or in an
    unknown-encoding font that also holds non-ASCII text of unknown encoding, are judged (default D2,
    reversible: suspect shapes only, not all ASCII). The legacy-font gate blocks such text with reason
    `legacy_ascii_suspect`, ahead of the ASCII rule.
  - Level extractor (`read-structure`) applies the legacy-font gate: a blocked text gives no candidate,
    level, storey height, storey name or question; each level-shaped value in it is listed in
    `levels.json` `blocked_candidates` (entry id, line, value as stored, reason; count in
    `summary.blocked_candidates`), and `level_none_found` says how many were held back. A literal `±`
    in an unknown-encoding font is non-ASCII, so it is blocked too (`%%p` is read as before).
  - `harness sheet-text <work> <file> --unassigned` (instead of a sheet id) returns the entries on no sheet
    or on several as sheet `unassigned` (null layout and bbox; `space` lists their spaces; model space
    first, rows numbered on across spaces), and `harness find-text --unassigned` searches only those
    entries (hits with sheet id `unassigned`, `counts.unassigned_entries_searched`): the text of a file
    without a detected sheet is now reachable. A sheet id together with `--unassigned` is exit 2.
    `find-text` counts unassigned entries once each (an id both unassigned and ambiguous was counted twice).
  - `harness list-sheets` gives each listed file `blocked_text_count`: its text-index entries the
    legacy-font gate blocks, on a sheet or not (null for a skipped file).

### Fixed
- Part check, review 1 fixes (ADR-0019, E5 review 1, DECISIONS 11): `part check` drops a problem that two checks
  raise for one row and id (a finding cited directly and in a `hand_sum` term gives one `cite_inactive`). An
  obsolete question counts for nothing in `listed_needs_blocking` and `low_without_question`, also when a
  cited finding names it. The sheet of a sided cluster lets a row be written on it, but it no longer opens
  the other texts of that sheet (`entry_outside_part`) or demands its marks (`mark_missing`): a cluster opens its own
  entries only (`Scope.row_sheets` is the new set for the row check). A malformed findings, questions,
  registry, marks or grid-systems document is the stop problem `input_invalid` (JSON, exit 1, no hash)
  instead of exit 1 with a message only; the `check` enum of `part-output` gains it (additive, `$id` stays
  0.1), and a `values_invalid` stop whose hash cannot be read for the same reason has a null hash.
  `marks_regex` is compiled with `re.IGNORECASE` (a legacy-font plan mark decoded as `k-1` is still demanded
  by `K-\d+`). An `asked` count row no longer gives its partner the pair key (only `seen` rows pair), `searched`
  matches as a whole word (`researched` is no record), and `family_linework_needless` is not raised when no row
  uses linework.
- Spacing evidence: a negative DIMLFAC (AutoCAD: layout viewports only) is compared by magnitude, so such a
  dimension no longer always reads `dimension_differs`. The schema example now shows a `dimension_differs` row
  and an engineer-given system.
- `harness status W --verify` checks every locked part and follows the inputs (E5b review 3 M1, m2, m3, DECISIONS
  24 D1, D2): the part check runs on each `locked` part, ready or not; a part with an input that fails its check,
  directly or through an input of an input, reads `ready: false` and `input_check_failed: [ids]` (the take-off
  line says `đầu vào kiểm tra lại báo lỗi (ids)`); a check whose hash is not the row's counts as failed
  (`changed_during_check`); a failed row gains `check_codes`, a check that raised a `ReaderError` or
  `ManifestAccessError` gains `check_error: "<exit code>: <message>"`, and `verified` is true only when no
  `parts_error` is set and no row has a `check_error` (else false). Status schema, same `$id`: additive
  `check_codes`, `check_error`, `input_check_failed`.
- Readiness is checked by code, not by the hash alone (E5b review 2, E5b-fix-4: D1 second half, m4 findings half):
  `harness status W --verify` (`build_status(work, verify=True)`) runs the `harness part check` function on every
  part that would read `ready: true`; a part with at least one problem gets `check_failed: true` and
  `ready: false`, a part that passes `check_failed: false`, a part that was not ready is not checked and has no
  `check_failed`. A check that cannot run (its stop problem, a record that cannot be read) counts as failed. The
  document gains `verified: true`; without the flag it is unchanged. `schemas/status.schema.json` (same `$id`):
  additive `verified` and `parts[].check_failed`, and `parts_project_reasons` no longer says "with no line here"
  (an untagged blocking question has had its reason line since E5b-fix-3). `harness takeoff render | plan | check`
  load the status with `verify=True`, and `takeoff_cells.status_line` gives a part with `check_failed` the
  not-buildable form with the reason `kiểm tra lại báo lỗi` (`CHECK_FAILED_VI`), so no take-off file or plan row
  prints `dựng được` for it. m4 (findings half): only a not-found evidence file (`FileNotFoundError`,
  `NotADirectoryError`) is `evidence_missing`; another `OSError` is a `FindingError` exit 3 (`finding list`,
  `part receipt`, `harness status`), never a stale finding.
- Part lock and receipts (E5b review 2, E5b-fix-3: C1, M1, D2, m1, m2, m3, m4 in part): the part hash gains
  `files`, the inventory sha256 of every drawing the manifest row (`sheets[]`, `tables[]` and their cluster,
  `clusters[]`, `files[]`) or a row of `values.json` names, so a revised drawing moves the hash of a part whose
  rows cite entries or geometry and no finding (C1; the per-file sha256, never the bytes of `inventory.json`, so
  a re-intake of unchanged drawings reopens nothing). `cited_questions` now also collects the questions cited
  through a finding and carries each question's registry `blocking` flag (M1; an answer still moves nothing).
  Every hash moves once, as in fix 1 (no real lock exists yet). Still outside the hash: the bytes of a saved
  geometry or contents document, `grid-systems.json`, `marks.json` and the rules of `part check`; the check
  stays the judge at the point of use. The latest `reviewed` receipt since the last `reopened` or `locked`
  decides whatever its hash, and a `pass` counts only on the current hash, so a `fix` recorded on another hash is
  not forgotten when the part returns to the first one; `part receipt --kind reviewed` refuses a round lower than
  one already recorded since that reset (D2; exit 1, "round N is older than round M: record a new round").
  m1 `part receipt --kind locked` on a `stale_input` part whose input hashes did not change is refused (exit 1,
  nothing written) and names the inputs, instead of "already recorded". m2 `harness status` gives
  `parts_project_reasons` one line per `callouts` or `marks` label with blocking questions no part lists, and one
  for `part-conflicts` questions without a part, so `blocked_by_project` always has a line. m3 the E5b-3 entry
  below names the verdict and inputs in rule 5. m4 (part): a refusal the system gives while a finding is judged
  (`FindingError` from `findings._stale_reasons`) keeps its exit code through the part hash instead of escaping;
  the `findings.py` half (only not-found is `evidence_missing`) is not in this change.
- Part lock and receipts (E5b review 3, E5b-5b: m1, m4/D3, D4, m5): the part hash gains the questions of every
  own active finding (`cited_questions`, cited by a row or not: `low_without_question` reads them, so withdrawing
  one reopens a locked part) and `grid_systems`, the system object of `grid-systems.json` (null when it lacks the
  id) of every system a row of `values.json` cites; the file is read only when a row cites one (exit 1 / 3 as the
  other record documents). Every hash moves once (no real lock exists). Still outside the hash: the text index of
  an unchanged drawing, `marks.json`, the bytes of a saved geometry or contents document and the rules of
  `part check`. `part receipt --kind reviewed` refuses a `pass` of the round that a `fix` or `engineer` receipt
  since the last `reopened` or `locked` already holds (any hash; exit 1, nothing written, "round N said <verdict>:
  record round N+1"): only a higher round overturns a `fix`; the same round with the same verdict stays "already
  recorded". `tests/test_findings.py` pins that `finding add` is exit 3 and writes nothing while an evidence file
  is refused.
- Part lock and receipts (E5b review 1: C1/D1, M1/D2, D3): a locked part is no longer `locked` or `ready` after
  a finding of its own went stale, its block row changed or a question its rows cite changed state (review 2
  found more of what `part check` reads outside this list: see the next entry). The part hash now also holds, per active finding, `stale` (the one
  source `findings._stale_reasons`: a re-intaken drawing, a changed knowledge row, changed saved evidence), the
  manifest row of the part's `block` (its `grid_system_ids`), and `cited_questions` (each question id the rows of
  `values.json` cite, as `obsolete`, `open` or `unknown`; an answer is no state, so it still never moves the lock).
  Every hash moves once: a part locked before this change reads `reopened` (no real project has a lock yet).
  `part_hash`, `PartStates` and `part_status` take an optional `knowledge` table. The latest `reviewed` receipt on
  the current hash decides in the status and in the `locked` precondition (a later `fix` or `engineer` beats an
  earlier `pass`; the refusal names the latest round and verdict), and rule 5 for `reviewed` also compares the
  verdict, so the same review file recorded with another verdict is a new receipt. Rule 5 for `locked` also
  compares the stored `inputs`, so a part whose input changed (`stale_input`) cannot be locked again on its
  unchanged hash: it goes through `reopened`, `checked`, `reviewed`, `locked`.
- Part lock and receipts, the minor fixes (E5b review 1, E5b-fix-2): m1 a symbolic link at
  `parts/X/receipts.json`, dangling or not, is `ReceiptsInvalid` (exit 1) and no longer reads as "no receipts";
  m2 `part receipt --kind reviewed` refuses a review file reached through a linked folder; m3 `checked` and
  `locked` refuse ("the part changed while it was checked") when the hash `part check` saw is not the one the
  receipt would carry; m4 a `values.json` or `notes.md` that is not a regular file hashes as
  `"not_a_regular_file"`, not like an absent one; m5 `part receipt` validates its stdout against `part-output`
  before writing anything, and a receipt or output that fails its schema is exit 1 "internal error" (it was
  exit 3, the code for "the system refused a file"); m9 tests pin that a receipts or record file the system
  refuses is exit 3 for `harness status`, never a `parts_error`; X1 `harness status` with a part hash that
  raises exit 2 (no `inventory.json` while a finding is active) prints `parts: []` and `parts_error`, like the
  exit-1 case (`part check` and `part receipt` keep their own exits). `part-receipts.schema.json` (same `$id`,
  m10): `review`, `inputs` and `reason` must be null for the kinds that do not carry them. Not changed: m6 (done
  by D3) and m8 (the second producer is already read since E6a).
- `harness part spotcheck`, `answer-key` and `score` (E9 review 1, DECISIONS 19). `spotcheck` leaves out of the pool
  the rows that name no file and the rows whose key is shared with a `seen` row of a different value, and names
  them on stderr (`no_file: …`, `key_ambiguous: …`); `answer-key` refuses such a row (exit 1 `key_ambiguous`), so a
  second verdict can no longer supersede the first and score as `differ`. `answer-key` also checks the sampled
  row (mark or subject, field, value, file, sheet) against the part's `values.json` and refuses a mismatch
  (`spotcheck_stale`), since the part hash does not cover `spotcheck.json`. Each verdict row gains `part_hash` and
  `seed` (schema `answer-key` stays 0.1: no key file exists yet; the examples are updated and aligned). The key
  normalises the mark or subject (NFC, casefold, single spaces); a key file with two active verdicts under one key
  is invalid (exit 1). The form names the file and the sheet id of every row (`Tệp: …`), uses the field nouns of
  `part conflicts` and no longer shows the part hash, seed, n or an entry id; a form file that is not UTF-8 is
  rewritten instead of crashing the rerun.
- `harness takeoff render | plan | check` (E8 review 1, DECISIONS 20): a number below zero in an AI slot is a
  number (`-2.750`; `check` compares signed numbers by absolute value on both sides); `render` refuses a file
  whose slot markers are damaged (exit 1, nothing is written, `harness takeoff check` lists them) instead of
  resetting both slots; the generated text names the work folder as its path from the take-off folder (`../work`,
  the resolved POSIX path on another drive) so it is the same for every spelling, working folder and machine
  (replaces "as typed"); the `chặn mọi lô` row of `00-plan.md` is `project_blocking_ids` as `harness status` gives
  it (no union), followed by one row (lot `—`) per bookkeeping part that holds open blocking ids, and an open
  blocking question in no row is exit 3 (`internal: ...`); `project_blocking` counts `project_blocking_ids`; a
  question in the registry but in no question document is listed under `Câu hỏi mở` and counted in `blocking_open`;
  `Tekla X/Y` also reads `grid_system_missing`. Line breaks in a value or a quoted text are collapsed so a table
  row or bullet stays whole; a `hand_sum` term with a space in its mark is shown whole and a term that cannot be
  read is exit 1 (the bullet is never left out); `U<n>` is no id; jargon plurals (`findings`, `entries`) are
  jargon; § 7 `đầu` and `cuối` are the first and last cited items; the question-state words and `không có` live
  in `takeoff_cells` (`QUESTION_STATE_VI`, `NONE_VI`). `check`'s signed-number pattern no longer reads the
  `D`/`Ø` prefix of a diameter as part of a number (`D400` gives no number on either side).
- `harness part conflicts` (E6 review 1, DECISIONS 16): a plan count (`count_plan`) conflicts only between parts that
  read the same (file, sheet), so the partial counts of two split parts no longer block them (the sums stay with
  `part chain` and the assembler). Rule 3 compares two `measured` findings only when their `fields.quantity` is
  equal or absent on both: a size and a count of one item never differ. The `where` of a ref is built from what
  survives a re-read (rule 1: part, subject, field, sheet or `-`; rule 2: part, file, sheet, aspect; rule 3: part,
  shared item ids), so a part re-read with renumbered rows, or a finding recorded again under a new F-id, keeps its
  question id and its answer; the row and finding ids are listed in the message (`B1-caps (R001) '1500x2400'`).
  The rule-1 subject key is NFC, case-folded and whitespace-collapsed (`K-1` and `K-1 ` are one mark). The rule-2
  key gains the block (two blocks may differ on one notes sheet). The message names the quantity from a local
  table (`Hai phần ghi khác nhau kích thước của K-1 ...`); `takeoff_cells.FIELD_VI` is untouched. The
  `part-output` `conflicts.obsolete` description says it is cumulative (no `$id` change).
- `harness part review-sample` and `harness part chain` (E7 review 1, DECISIONS 15): a prompt leaves out the sheet
  number, the view and the mark or subject (and the key is null) when the text shares a number with the row's
  value or holds the value's casefolded text, so a view heading that names the size no longer gives it away. The
  prompt now starts `Sheet <sheet id> of <file>` when the manifest gives no sheet number (`File <file>` when the
  row has no sheet) and names a field by one fixed English phrase ("number on the plan", "top level", ...) in
  place of the field id. In `chain`, a mark's `count_plan` is the sum of its numeric `count_plan` rows (the rows
  of `sums.count_plan`), and it has a product only when its `piles_per_member` rows give one distinct number.
  Tests: the withhold rule, split marks, the golden sample, the outside-frame file match.
- `harness part manifest-check` (E4b review 1, DECISIONS 12): `grid_origin_other_block` and `linework_duplicate`
  measure with the answered unit only (the active `units_confirm_all` answer of the file); the declared unit is
  never a fall-back. A file with in-scope sheets and no active answer gets the new problem `unit_unanswered`
  (detail "answer the units question of `<file>` first", no ack clears it) and its sheets are skipped as
  `unit_unknown`. A missing `question-registry.json` is exit 2 before the rules (stderr names `harness intake`, no
  JSON), where it gave `ack_question_unknown` and `unit_answer_unread` rows. A member part whose block is no block
  id of the manifest no longer takes part in the linework rule (it could pair a sheet with itself). The linework
  signature rounds by `geometry._cell`, so an exact copy at a half-mm centre no longer splits across two cells.
  The `grid_system_unknown` detail reads "but grid-systems.json is missing (run `harness grid-system`)" for an
  absent file. `part-output` gains the problem code `unit_unanswered` (additive, `$id` stays 0.1). Seven mutants
  of the contract are pinned by new tests.
- `harness part manifest-check` (E4a review 2): a fixed cross part whose `split_of` named the other fixed id
  stood in for both cross parts (`cross_part_missing` was not raised for the one it replaced); a split now
  satisfies `cross_part_missing` only with `split_of` naming that id and an id `<fixed id>-<text>` (M1). An empty
  text after the dash (`all-grid-levels-`, `ALPHA-caps-`) is a `part_kind_mismatch` (m2). The ids of the cross
  split are `<fixed id>-<text>`, any non-empty text.
- `harness ask --withdraw Q --part X` run again on a question that is already withdrawn exits 0
  (`already_withdrawn`) for the part it held, as for any pattern-valid part; it exited 1 "not in
  parts/manifest.json" (E4a review 2, m1). Run on a question that is still open and no longer holds X, with X
  not in the manifest, it exits 1 with "belongs to part(s) …" instead of "not in parts/manifest.json" (D1).
- The `harness contents ... --save` line that a stale or mis-named evidence file prints (`redo`) kept no
  `--dims`: it saved a document with another query hash, so the cited file was never restored. It now ends
  `--dims` for a document saved with the flag (E10b review 1, M1). The `contents.example.json` example now shows
  `query.dims`, `printed_dims` (outline and summary) and `dims`; new tests pin the attach rules of `--dims` that
  had none (font gate, value not compared, DIMLFAC, 1 degree bound, largest gap, pick order, ambiguity,
  angle direction, hidden layer, tolerance times DIMLFAC).
- `harness contents --dims` (E10b review 1, D1, M2, m1): a `centred` dimension whose two ends both lie, along the
  dimension, within `--tol` of the centres of symbols inside that outline is a pile spacing and is no longer
  attached (it raised a false `disagree`; without the pile layer as `--circle-layer` it may still attach
  `centred`, said in `--dims` help and the schema). A block copy of a linear dimension whose definition stores no
  angle (group 50), inserted rotated, was dropped as a "scaled INSERT": its direction is now rebuilt from the
  linear map of the definition's points (collinear points keep the old, unusable result). A dimension text with
  no text-index entry passed the legacy-font gate silently: `GeometryRead.dims_unlinked` counts them and
  `contents --dims` warns, as `harness dimensions` does.
- Measured findings, T24 review 1 (changes the two bullets above before release; schema `reader-findings` stays
  0.1, no `$id` bump): `evidence.items` is now a list of objects, one snapshot per cited item (`id` plus the
  fields the item has: kind, layer, sheet, space, centre, short, long, diameter, symbols, marks, axes,
  invisible), not a list of ids. New repeatable `harness finding add --claim KEY=VALUE` (keys symbols, short,
  long, diameter, count) checks a number of `--value` against EVERY cited item (symbols exactly; short, long,
  diameter within the saved query's `tol`; count = number of items); a mismatch or a missing field exits 1
  naming the item and the field (`--value` stays free text; a contents outline has no diameter). A geometry item
  whose `sheet` differs from `--sheet` is refused (exit 1). Saved files are immutable:
  `<command>-<where>-<qhash8>-<chash8>.json`, qhash8 over the drawing's input-relative path, its inventory sha256
  and the query, chash8 over the bytes written; the same bytes again write nothing, new bytes make a new file
  next to the old one, other bytes under an existing name exit 1; two drawings with the same bytes no longer
  share a name. `finding add` refuses a source whose content hash differs from its name (hand edit).
  `finding list` adds `stale_reasons` ([{reason, detail}]: drawing_changed, knowledge_changed, evidence_missing,
  evidence_changed) and, for a stale finding with evidence, `redo` (the `harness ... --save` command of its
  stored query). `--save` computes the document without the work lock and takes it only for the write
  (`cli.SELF_LOCKING_COMMANDS`; `LOCKED_WHEN_FLAG` is gone); a re-intake during the run saves nothing (exit 1).
  The confidence of a measured finding is `medium` without entries and the minimum of its entries' confidence with
  entries, `high` included (any other kind stays below `high`); `--confidence` only lowers it. Example updated.
  Review 2: every standalone number of a measured `--value` (not glued to a letter, `#` or `-`; `d500` is 500;
  `1700x3200` is two) must be backed by a `--claim` (within the query's `tol`) or a number in a cited entry, else
  exit 1; `high` needs at least one `--claim` and every claimed number in a cited entry's text, else `medium`;
  the reader-findings schema requires `entries` minItems 1 for a measured finding with confidence `high`
  (pre-release: no `$id` bump).
- `harness finding withdraw --part X` and `harness ask --withdraw --part X` (also when it only removes X from a
  question's `parts`) accept X when it is the record's own part, even after `parts/manifest.json` dropped it
  (E4a D5); `finding add`, `ask`, `--amend` and every other `--part` check are unchanged.
- `contents --dims` (E10b review 2, m1, m2): a rotated copy of a block dimension that stores no angle (group 50)
  and whose definition points lie on one line could attach along the wrong axis (rotated 90 degrees, a diagonal
  collinear definition kept the direction (1, 0)). When the direction cannot be rebuilt the copy is now used only
  if its p1 to p2 equals plus or minus the definition's (relative 1e-6): unrotated and 180 degree copies still
  attach, every other rotation is `unusable`. The module docstring, the `_printed_value` docstring and the schema
  `dims.unusable` description name this case besides a scaled INSERT.
- `sheet-text` and `find-text`: `counts.not_printed_in_scope` counts the not-printed entries inside the scope the call
  selects (its sheet, `--region` and `--contains`, or the search text), as `matched` and `hits` do; it ignored the
  region and the text filter and counted every not-printed entry of the sheet or file.
- `contents`: `axes[].nearest_unlabelled_offset` is no longer null when an unlabelled grid line is the nearest
  line. The grid detector writes those lines under each family's `unlabelled_lines`, which `contents` did not read,
  so a member exactly on one was reported as on the nearest labelled axis only. They now feed only
  `nearest_unlabelled_offset` (position at the line midpoint); they never set `label` or `offset`, also in a family
  without a labelled axis, and no other field changes.
- `grid-system`: the per-code question cap (`MAX_QUESTIONS_PER_CODE`) no longer drops blocking questions
  (finding M4: a blocking `grid_system_conflict` past the 100th was neither listed nor blocking the run).
  The cap applies to non-blocking questions only; the "only the first N are listed" warning counts only those.
- `levels`: the per-code question cap (`MAX_QUESTIONS_PER_CODE`) no longer drops blocking questions
  (same defect as the grid-system finding M4). The cap applies to non-blocking questions only; the
  "only the first N are listed" warning counts only those.
- `grids`: the per-code question cap (`MAX_QUESTIONS_PER_CODE`) no longer drops blocking questions
  (same defect as the grid-system finding M4). The cap applies to non-blocking questions only; the
  "only the first N are listed" warning counts only those.
- Tool wave 4, FP2 follow-up (grids, REVIEW-FP2 m2): a cross-check between two views is a `scaled` copy
  (`grid_scale_differs`) only when the mean ratio, which is the value reported, differs from 1 by more than
  `SCALE_TOL`. It was tested on the first ratio, so two views 5 mm apart on one spacing and equal elsewhere
  were reported as a view at another scale (ratio 1.0007) with a question per sheet pair.
- Tool wave 3, package GRIDGATE (review of packages G and C; ADR-0013 decisions 2 and 6):
  - Gate 1 no longer opens on a grid that was never built or confirmed. `harness status` closes
    `grid_system_missing` only from the built result: the engineer's answer and a fresh
    `grid-systems.json` holding a system whose `source_answer.key` is the question's key, which the
    `grid_system_select` answer uses. Grid values alone close nothing; a values answer that built nothing,
    or whose system the select answer leaves out, stays in `blocking_open` with a `grid systems:` reason
    (`harness questions-md` shows it as "chưa đóng"). Who answered (`answered_by_role`) is part of the
    answers fingerprint of `grid-systems.json`, so an answer the engineer gives again with the same values
    after a simulated one makes it stale until `harness grid-system` reruns; every existing
    `grid-systems.json` reads as stale once. Every used system needs `units.status` confirmed and, once
    its units and X/Y are, a non-null `tekla_grid`.
  - `harness grid-system` compares a system built from a `grid_system_missing` answer with every other
    system, detected or built, like two detected ones: shared labels in order, distances between
    consecutive shared labels within the drafting tolerance (in mm when both files have an engineer units
    answer), the same file-set rules. A disagreement is a `grid_system_conflict` (blocking until the
    select answer leaves one out or declares both separate); an agreement is `compatible_with`. The
    conflict question's key names the answered question's key, not the system id. A
    `grid_system_missing` answer that builds nothing (words only, malformed) no longer keeps the question
    raised: once the file is covered by a selected system again, it is not asked and the answer goes stale.
  - `harness answer` refuses a `grid_system_missing` spacing above `MAX_SPACING` (1000000 drawing units)
    or one that is not finite as a float (a 400-digit number crashed it with `inf`), and labels that are
    equal ignoring case (`A,a`: the drawing check reads them as one axis); exit 1, nothing written.
    `harness grid-system` builds nothing from such a hand-written answer and warns, instead of crashing
    (`OverflowError` on a 400-digit integer).
- Tool wave 2, package F2 (review of P4, marks and dimensions):
  - `harness dimensions` measures block content on its block definition (ezdxf `origin_of_copy`), not on
    the virtual copy: a linear dimension stored without an angle in an INSERT rotated by 90 degrees
    measured about 0 (sample 270: 40 rows reported `ok` against group 42 = 4000). The copy still gives
    the sheet and the layer; an INSERT's scale no longer changes the measured value.
  - `harness dimensions` and the dxf-probe `dimension_audit`: a row whose group 42 disagrees with the
    measurement is `not_compared` with a note, whatever its text rule (measured-text rows were `ok`).
  - `harness marks`: a line-grid table without a keyword is read on the seed's column only when that
    column's header cell holds no text and at most half of its allowed cells are integers; only its
    mark-shaped cells become schedule marks. Otherwise it is header-blocked, as before wave 2 (sample 270:
    bar schedules keyed on the 'STT' row numbers, keys '1'..'11', '(sl:01)'; sample 461: plumbing lists
    whose first data row sat in the header band, keys 'd110', 'selta').
  - `harness marks` size reasons are exact: "the schedule header cells that could name a size column are
    blocked" only when a blocked column could give the missing size (its readable cells are numbers or
    `b x h` values, or none is readable), else "the schedule table has no size column"; a row with no
    cell in its size columns says "the schedule row has no size cells" (was "... are not numbers");
    `blocked_columns` no longer lists a header cell that lies in no column (`column: null`).
  - `harness dimensions` rows carry `text_entry` (schema `dimensions`, additive optional field, `$id` still
    0.1): the text-index entry of the dimension's own text and the legacy-font gate's verdict (`meaning`,
    `block_reason`); null for a text that only shows the measurement. An override text the gate blocks is
    not read (override_value null, status `not_compared`, note). A text with no index entry is counted in
    `warnings`. Sample 270: 75 of 75 texts linked, 15 blocked (were `not_numeric`).
- Reading toolchain, after an independent review of the EVAL-1 wave:
  - `harness marks`: a rotated header keyword (or one that is not a cell text) no longer crashes the run;
    the table becomes a non-blocking `schedule_table_unparsed`. Questions no longer quote table ids, so a
    table added to one file does not re-key another file's `mark_*` questions (their answers are asked
    again once).
  - Units contradiction also tests the median grid spacing under the ANSWERED unit (0.5 m to 30 m,
    `grids.implausible_spacing`), not only the median dimension; `grid-systems.json` files carry
    `grid_spacing_median`; `harness status` mirrors the test.
  - `harness status` reasons print `harness answer <work_dir> <id> ...` (the work folder was missing),
    one question per command.
  - `harness callouts` applies the legacy-font gate: blocked text yields no candidate and is listed in
    the new `blocked_entries` of `callouts.json` (a literal `4Ø16` in an unknown font was a rebar callout).
  - `harness answer`: `systems=` must name systems the select question lists.
  - `grid_system_select` keys include each system's file and its sha256, so systems of two files cannot
    swap S-ids under one key (existing select answers go stale once).
  - `harness finding`: a `note_item` quote must start and end at token boundaries; a write error exits 3;
    a document whose `next_id` is not above every `F-` id is refused.
  - `harness questions-md` prints reader questions as written (never "chưa có bản dịch"); `harness ask
    --text` is the Vietnamese question the engineer reads.
- Tool wave 2, review fixes, package F1 (legacy-font gate and grids):
  - Capital-font hint: a style name or family gives a case hint only when it is itself a font name
    (`.Vn`/`Vn` then letters, digits, spaces). Style names such as `VN-ABC` or `VNARIALH-BOLD` no longer
    veto their family's hint (`.VnAvantH` → capital); `vntimeh.shx` used as a style name no longer reads
    the `x` of its extension as "not capital" (its case is now reported as uncertain).
  - `legacy_ascii_suspect` (`harness extract-text`): an unknown-encoding run also counts as legacy when its
    style name, font file or family (inline font: its name) looks like a legacy Vietnamese font
    (`encoding.legacy_font_name`: `vncc-rms.shx`, `vnsimli.shx`), with no non-ASCII sibling needed; the
    sibling rule is keyed by the font file, so styles on one file share the evidence. New shape: an
    uppercase vowel between lowercase letters (`dAy`, `tEn`, `cOng trInh`). No longer suspect: `/a` plus a
    digit (`%%c8a100/a200`, `1:100/a3`), one letter ending the token after a slash (`C/C`, `N/A`, `b/h`,
    `1/A`) unless two letters stand before it (`BO/R`), and CamelCase words (`TieRod`, `HoleSize`). On
    dwgshare 461 the 16 Telex-style texts of the `vncc-rms.shx` / `vncc-sim.shx` styles are blocked
    (except `s.l`, `stt`): `haFn 200` is no longer two plan marks with a `HAFN` prefix question.
  - A TrueType family no longer silently overrides an approved knowledge row: when the family decides and
    an approved row for the style or its font file gives another encoding (or approved rows disagree),
    `harness extract-text` decodes nothing and flags `knowledge_conflict` (the gate blocks it), and
    `harness read-dxf` gives no hint and asks `font_encoding_conflict`. An agreeing row changes nothing.
    This replaces P1's "a `.Vn*` family decides before an approved font-file row" for disagreeing rows.
  - Grid extractor (`read-structure`) applies the legacy-font gate: a label-shaped text in a bubble that
    `text_gate` blocks (`4/g14`, `2/G20` in a TCVN3 style) is never a label or an axis; it is listed in
    `grids.json` `blocked_candidates` (entry id, value as shown, reason, sheet; count in
    `summary.blocked_candidates`), and a family line ending in such a circle asks `grid_label_missing`.
    `grids` schema: both fields added, optional (`$id` stays 0.1).
  - `harness sheet-text` / `find-text`: `legacy_font_gate.question_ids` lists the file's font questions only
    when some blocked entry has a reason an encoding answer can lift; a sheet whose blocked entries are all
    `legacy_ascii_suspect`, or that has none, lists no question. Schema descriptions of `question_ids` and
    `legacy_ascii_suspect` updated (no structural change, `$id` stays 0.1).
- Tool wave 2, package F3 (review of gate 1 and questions.md):
  - Only the engineer's answer settles a question of intake, read-structure, grid-system or the reader:
    a simulated or role-less answer leaves it in `blocking_open` / `blocking_open_ids`, out of `answered`,
    and in questions.md section 2, where the answer is shown labelled "(mô phỏng)" or "(chưa rõ vai
    trò)". Every non-engineer answer questions.md prints carries that label.
  - questions.md no longer says a grid-system conflict was "closed by the grid_system_select answer"
    when it is only non-blocking while the file sets are asked: it says the conflict waits for the
    `file_set_relation` question named in grid-systems.json `file_sets`. Any other open, non-blocking
    conflict shows how to close it.
  - Every gate-1 reason that tells someone to answer says the engineer does it (`the engineer answers …`,
    `the engineer says …`, `the engineer runs: harness answer …`): the select, axis, conflict, file-set,
    units-disagree and units-contradiction reasons; the conflict reason now prints the select answer
    command. questions.md "Cách đóng" lines carry "kỹ sư tự chạy, tác tử không chạy thay".
  - `harness status` validates each question document it reads for written closures against its schema:
    a damaged one (e.g. a list as a question key, an unknown closure reason) is exit 1 naming the
    document, not a traceback.
  - An unreadable DXF/DWG no longer gets the units reason "rerun harness intake", which no rerun clears:
    it stays a gate-1 reason through its own blocking intake question (`read_failed`,
    `conversion_empty`, `no_reader_implemented`) until the engineer answers it, and is a `files:` reason
    when no such question is live.
  - `harness grid-system`: a system's `grid_system_axis_unassigned` question is keyed by its representative
    families (`where` = `<file> <view>/<family> x <view>/<family>`), not by its positional system id, which
    moves to the message (`Grid system S00n: …`). Adding an unrelated drawing file no longer re-asks it or
    leaves the engineer's X/Y answer stale. Existing X/Y answers go stale once, on the first rerun.
  - `status` schema: the `blocking_open` / `answered` descriptions say that only the engineer's answer
    counts for those producers; the `grid-system` example shows the new axis `where` and message (no
    structural change, `$id` stays 0.1).
- Schema `pattern` now has ECMA-262 meaning in `harness validate` (JSON Schema 2020-12): Python's
  `$` matched before a final newline, so `"L1-C-A2\n"` passed the `spec_id` pattern; `.` no longer
  matches `\r`, U+2028 or U+2029. Applies to every schema (ADR-0010 Amendment 1 §10).
- `harness validate spec`: a file name that a receipt cannot record (backslash, non-UTF-8) is an
  invalid result instead of a traceback; an existing spec that cannot be read exits 3.
- `guard_tekla_write.py` now exits 2 (the blocking code) on any internal error instead of
  relying on an undocumented `onFailure` setting; the setting was removed.
- `guard_tekla_write.py` no longer blocks commands that only mention `tekla-cli` as data
  (`cat`, `grep`, `git commit -m`), and no longer lets a read hide a later unparsed write.
- Write guard no longer denies commands that only name a file containing `tekla-cli`
  (e.g. `sed -n 1,40p docs/tekla-cli-contract.md`); RTI-0005.
- Write guard now recognises the CLI under its .NET project name (`TeklaCli.exe`) and treats
  every `dotnet run|exec|watch` as a write; `dotnet build|restore|clean` stay allowed; RTI-0006.
- Forging a spec validation receipt is narrowed, not closed (RTI-0008): settings deny
  `Edit(**/*.receipt.json)` (covers Write, Edit, NotebookEdit and Bash redirection targets), and
  the write guard denies, for every agent including `builder`, any shell command that names or
  pipes `*.receipt.json` unless it only reads it. A script file that writes one is still not
  seen. `builder` no longer validates the spec itself; it checks that the receipt `doc-reader`
  wrote exists, and `tekla-cli build` checks that it matches.
- Write guard now treats a newline as a command separator: `cd x` + newline + a `tekla-cli`
  write passed for any agent (RTI-0009, critical).
- `workflow.md`: the lot loop is strictly sequential (lot n+1 waits for gate 4 of lot n).
- Added `PowerShell(...)` allow rules matching the existing `Bash(...)` ones.
