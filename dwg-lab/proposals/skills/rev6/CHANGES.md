# Rev 6 skill proposals — changes from rev 5

PROPOSAL. These folders replace `.claude/skills/<name>/` only after the engineer approves them
(AGENTS.md principle 7). Base: rev 5 (`dwg-lab/proposals/skills/rev5/`). Each folder is a full
copy; `diff -r dwg-lab/proposals/skills/rev5 dwg-lab/proposals/skills/rev6` shows the edits.

Purpose: EVAL-4 runs on skills that match the tool-wave-3 CLI and close the skill-side defects of
EVAL-3 (`dwg-lab/proposals/skills/EVAL-3.md`). "Fix N" below is the EVAL-3 ranked-fix number.
"Row x" is a row of the EVAL-3 R1 root-cause tally that planned tool wave 3 (a1–a5, b1–b3,
c1–c2, d, and the R-arm rows). "Item N" is the rev-6 brief's change list (status wins, mark sets,
per-file notes, note scope, titles, grids, text gate, callouts, tables, questions, report style,
plan).

**Verified against the CLI on `a91fa9b`** (branch `feat/tool-wave-2`, all five tool-wave-3
packages merged): every command, flag, field and question code the four skills cite was checked
against `uv run harness <cmd> --help`, `schemas/`, `src/tekla_harness/` and the CHANGELOG
[Unreleased] "Tool wave 3" bullets. The changed behaviour was run on three scratch work folders
built from known drawings with LibreDWG: 286 + 290, 267 + 433, and 461 (list below). **Re-checked at `54d46cb`** (after `fix/w3-gridgate` and the wave-3 review fixes) by an independent
reviewer: every cited command and flag still exists (`cli.py` changed only in the `harness answer`
help text). The findings it raised are fixed in "Refresh at 54d46cb" below.

Size (lines, SKILL.md): intake 81 → 94, reader 140 → 193, report 85 → 110, plan 102 → 116 (after
the 54d46cb refresh; 88, 181, 107, 114 before it). The
growth carries the wave-3 outputs (mark sets, comparison scope, unparsed codes, the grid route)
and the rules that keep simulated proposals blocking. The report skill asks for a shorter
report: each fact once, reasons paraphrased.

## Refresh at 54d46cb (pre-EVAL-4 review, the only pre-run change)

An independent Opus reviewer checked the four skills against the CLI at `54d46cb`. It found nothing
Critical. The fixes:

| Skill | Change | Finding |
|---|---|---|
| intake | Answers: for `grid_system_missing`, a "no plan needs a grid" reply takes the **Hoặc** line (`--value no_grid=yes` alone); grid values are never filled in; the invalid-value refusals (exit 1) are named | M1 (`questions_md.py` Hoặc line) |
| intake | "No usable or selected grid system": invalid values and `no_grid=yes` build nothing; status closes it only on the engineer's `no_grid=yes` or a used system built from the engineer's values | m2 |
| intake | Status wins over producer stdout too: `grid-system` stdout and `harness answer` `summaries` show `blocking_open 0` for a simulated answer | m3 |
| reader | Step 4: a question is settled only when status drops it from `blocking_open_ids` or lists it in `gate1.closed`; trust status over producer output | M2 (`status.py` `answer_counts`) |
| reader | Step 6: a shorthand heading list names no mark; `plan_only` marks of its family are never written as "detail missing" and go into one reader question per file quoting the headings | M3 (7564542) |
| reader | Step 4: the exact `grid_system_missing` close rule; `no_grid=yes` leaves `grid_none_found` / `grid_gate1_confirmation` open | m1 (`status.py` `answer_closes`) |
| reader | Text gate: `find-text` "approve the font row" advice does not apply to `legacy_ascii_text` | m4 (`sheet_text.py` notes) |
| reader | Step 5: both causes of `level_storey_selection`; step 6: `diameter_glyph_no_notation` (`ù12`) quoted as stored | optional (7be161b; `callouts.py`) |
| report | §7: a `no_grid=yes` answer line (engineer vs `(mô phỏng)`); §8: `plan_only` of a shorthand-heading family is `có thể nằm trong tiêu đề viết tắt` | m6, M3 |
| plan | Gate 1 grids: after `no_grid=yes` the file's grid questions still block; an all-`no_grid` project keeps gate 1 shut (scope blocker) | m5 (ADR-0013) |

Checked and unchanged: `level_storey_selection` (the generic supplement rule covers both causes),
sheet numbers (the skills cite `sheet_number_missing` / `sheet_number_gap` and print only extractor
numbers), the `mark_sets.complete` wording (`ít nhất` plus `source` when false).

## Facts that landed differently from the design or the brief

- `harness status` at `54d46cb` follows ADR-0013 decision 6 (1944872, c1bedc5, 27392a6): it
  closes `grid_system_missing` only on the engineer's `no_grid=yes` or on a used system built from
  the engineer's values in a fresh `grid-systems.json`; the role is in the answers digest;
  answer-built systems are conflict-checked. History: at `a91fa9b` status did not yet follow
  decision 6. The G+T+C review (C1,
  Critical) found that it closes `grid_system_missing` from an answer's values alone, and that the
  answers digest ignores the role. ADR-0013 was amended at `c058966` (`no_grid=yes`,
  engineer-only; status closes the question only from the built grid or that answer), and the fix
  lands on `fix/w3-gridgate`. The skills therefore settle `grid_system_missing` by the built
  result: a system in `grid-systems.json` whose `source_answer` names the question, or the
  engineer's `no_grid=yes`. This rule holds before and after the fix.
- `marks.json` never writes `compared_with: none`, although the schema allows it. A file with no
  parsed schedule and no detail heading is simply not compared, and its `plan_only` stays empty.
  The skills derive "not compared" from `matching[]` (`schedule_tables` 0 and `detail_headings`
  0). Without a schedule, the heading comparison covers only families with both a plain plan mark
  and a heading. The skills read that from the mark set's `source` (`plan_marks` +
  `detail_heading`). Checked on 433: `C` is compared; `M`, `GM`, `DK` and `DM` are not.
- A `schedule_only` key with `compared_with: detail_heading` comes from a heading. It means that
  no plain plan label was read for that mark, not that the member is absent from the plan
  (package M; 290 `d-6`…`d-18`).
- Detected grid systems carry no `source` field. Only an answer-built system has
  `source: engineer_answer` and `source_answer`.
- `harness grid-system`'s own stdout counts a simulated `grid_system_missing` answer as answered
  (`blocking_open 0`), and so do the `summaries` of `harness answer` (461 at `54d46cb`). `harness
  status` keeps the question blocking and adds an `answers:` reason (461, Q-019). This is one more case of "status wins".
- `harness find-text` `notes` names `legacy_ascii_text` among the font questions and advises
  "ask the engineer to approve the font row". The question's own message says its answer "decodes
  nothing and unblocks nothing". The skills follow the message.
- `callout_unparsed` asks only the unparsed candidates that no other question covers. On 290,
  `member_mark_undefined` (111) goes to the prefix question instead. The skills cite the
  `callout_unparsed` id per file and `unparsed_code`.
- `sheet-text --region` needs the `=` form only when the first value is negative. The skills
  always use `=`.
- No finding kind fits a grid. `finding add` has the kinds `sheet_class`, `note_item`,
  `structural_system` and `cross_check`, and no system aspect names a grid. So a grid the reader
  reads off the drawing goes onto `grid_system_missing` as `ask --supplement` evidence
  (checked: accepted on 461 Q-019 and printed under "Bổ sung của người đọc"). The brief asked for
  "a finding with provenance". The supplement carries the same provenance: entries in `--found`
  and the place in `--where`.

## drawing-intake (3 changes)

| # | Change | Reason | Touched |
|---|---|---|---|
| 1 | "After any … answer" also covers `grid_system_missing`. A new sentence says that status wins over the producer files. `proposed_simulated` and `proposed_closed_by` record what a non-engineer answer would do, and confirm or close nothing | Fix 4; item 1 | Reading the results |
| 2 | New bullet **No usable or selected grid system**: the file has a blocking `grid_system_missing`. Its answer is the engineer's: the grid values its command names, or `no_grid=yes` (ADR-0013). Words only, or another role, builds nothing | Fix 1; item 6; ADR-0013 | Reading the results |
| 3 | **Legacy fonts**: blocked ASCII text gets a non-blocking `legacy_ascii_text` question per file and style. Intake reports its id and count; its answer unblocks nothing | Fix 3 (W3); item 7 | Reading the results |

**Deliberately not changed.**
- Frontmatter `description` (rev 4 tuned it with an 80-run trigger eval).
- Steps 1–6 and their completion criteria. Step 5 already says that `questions-md` writes the file.
- The **Answers** section. A simulated `grid_system_missing` relay works like any other: replace
  `--role engineer` in the question's **Lệnh trả lời** line. It builds nothing, as bullet 2 says.
- `questions-format.md`.
- The converter bullet and the hard stops.

## structural-drawing-reader (15 changes)

| # | Change | Reason | Touched |
|---|---|---|---|
| 1 | Tool list: `sheet-text W <file> <sheet_id> --region=x0,y0,x1,y1`. It returns a table as `rows` of `cells`, in absolute coordinates (the entries' `x`/`y` and the `list-sheets` frame), written in the `=` form | Row a5; item 9 | Before you start |
| 2 | Tool list: `find-text --unassigned` searches **only** the text on no sheet or on several. Rev 5 read as "also" | Fix 6; item 7 | Before you start |
| 3 | Tool list: `ask --amend Q-… [--text] [--places]` corrects or widens your own unanswered question in place, instead of a withdraw and a new ask | Fix 6; item 10 | Before you start |
| 4 | **Blocked text**: blocked ASCII text cites `legacy_ascii_text` (one per file and style) as its font question. Its answer unblocks nothing | Fix 3 (W3); item 7 | Blocked text |
| 5 | **Blocked text**: `find-text` and `sheet-text --contains` match allowed text only. `counts.blocked_in_scope` does not depend on the query, and `notes` names the font questions. While it is above 0, "0 hits" is written "not in the allowed text", with the count and those ids | Fix 3 (W4); item 7 | Blocked text |
| 6 | Step 1: cite read-structure's `sheet_number_gap` and `sheet_number_missing` | Row a1; item 10 | Step 1 |
| 7 | Step 1: a sheet whose ranked titles name different subjects gets one question quoting both, then a `cross_check` finding with that `--question` | Row c2; item 5 | Step 1 |
| 8 | Step 2: a `note_item` records its clause heading as `--field scope=T…`, outside `--entries`. A blocked heading goes into the item's question. Two items conflict only when their scopes overlap | Row c1; item 4 | Step 2 |
| 9 | Step 2: notes tables are read with `sheet-text --region`, row by row. A cell is blank only when that row's `cells` lack it | Row a5; item 9 | Step 2 |
| 10 | Step 3: a finding that names a mark set copies `members` from `summary.mark_sets`, gaps kept. It writes `ít nhất` plus the `source` when `complete` is false | Row b1; item 2 | Step 3 |
| 11 | Step 4: `proposed_simulated` (units, X/Y) and `proposed_closed_by` (conflicts) are proposals, not confirmed, answered or closed | Fix 4; item 1 | Step 4 |
| 12 | Step 4: write "no usable or selected grid system" and name the file's systems. The `grid_system_missing` answer (grid values, or `no_grid=yes`) is the engineer's own step. It is settled only by a system whose `source_answer` names it, or by `no_grid=yes`; words only or a simulated answer build nothing. The reader's own reading of the grid goes in as `ask --supplement`, evidence only. `grid_answer_contradicts_drawing` is quoted with both values | Fix 1; row b3; item 6; ADR-0013 | Step 4 |
| 13 | Step 6: mark lists are copied from `summary.mark_sets`. Comparison scope per file comes from `matching[]`: a file with no schedule and no heading is `chưa so sánh`, and its empty `plan_only` says nothing. Without a schedule, only `plan_marks` + `detail_heading` families were compared. A heading-only `schedule_only` means no plain plan label was read | Row a4; package M; item 2 | Step 6 |
| 14 | Step 6: callouts unparsed per `summary.unparsed_by_code`, with the file's `callout_unparsed` id. `symbol_glyph_unverified` is quoted as stored and never read as Ø. Check `rejected[]` / `summary.rejected_by_reason` before writing that a bar size is absent. This replaces the free-text `unparsed_by_reason` | Fix 2 (W1, W1b); item 8 | Step 6 |
| 15 | Rules: a `low` finding's `--question` asks about that value; a font question alone does not | R-arm row (J2 A64) | Rules |

**Deliberately not changed.**
- Frontmatter `description`.
- The units precondition, the hard stops and the step order.
- Step 5. Package S fixed `(+ 6.00M LEVEL)` and the bare `sàn` in the extractor (rows a2, a3), and
  the rule to quote missed level texts still holds.
- Step 7.
- "A file with no detected sheet".
- `conventions.md`.
- The rule to print the sheet number only where the extractor gave it. Row a1's skill part (A79)
  disappears with package S's detector fix.
- The class list for `finding add`, which code validates.

## drawing-analysis-report (11 changes)

| # | Change | Reason | Touched |
|---|---|---|---|
| 1 | Inputs: `questions-md` writes `questions.md`. Render it first. It is not a read-only step | R-arm row (c), J2 A53; item 11 | Inputs |
| 2 | New **Status wins** paragraph: status decides open, closed and confirmed. Rev 5's §10 blocking rule moves here. `proposed_simulated` and `proposed_closed_by` are printed `(mô phỏng)`, still blocking | Fix 4; item 1 | Inputs |
| 3 | §1 Kết luận: the main blockers with their Q-ids. Non-engineer answers are named `(mô phỏng)` | Item 11 | Part A §1 |
| 4 | §2 Vấn đề: a row built from per-file questions gives each file its own missing items, as its question states them | Row b2; item 3 | Part A §2 |
| 5 | §4: sheet numbers as the extractor gives them, with the `sheet_number_gap` / `sheet_number_missing` ids | Row a1; item 10 | Part A §4 |
| 6 | §5: font questions include `legacy_ascii_text`. A tool or environment line the writer did not run or verify reads `chưa chạy` | Fix 3; row d (P22); item 11 | Part A §5 |
| 7 | §6: a note item's scope (`fields.scope`). Two items conflict only when their scopes overlap | Row c1; item 4 | Part A §6 |
| 8 | §7: "no usable or selected grid system" with the `grid_system_missing` id. An answer-built system names its `source_answer`. `grid_answer_contradicts_drawing` is printed with both values | Row b3; fix 1; item 6 | Part A §7 |
| 9 | §8: mark sets come from `summary.mark_sets` (`ít nhất` + source when incomplete, no range over a gap). The comparison scope is stated first: a file with neither schedule nor heading is `chưa so sánh`, never "no plan-only marks", and only some families count without a schedule. A heading-only schedule-only key is `chưa đọc được nhãn trên mặt bằng`. Size comparisons sit beside the conflicts. Callouts are given per `unparsed_by_code`, with the `callout_unparsed` ids and `rejected_by_reason` | Rows b1, a4; package M; fix 2; items 2, 8 | Part A §8 |
| 10 | §10: blocking open first, then `gate1.closed`. The blocking rule now lives in **Status wins** | Item 11 (no duplication) | Part A §10 |
| 11 | Style: each fact is printed once and cited by id elsewhere. Gate-1 reasons and producer messages are paraphrased in Vietnamese with their Q-ids, never pasted in English | EVAL-3 "Reports are long and paste English status reasons (R6 stays 2)"; item 11 | Style |

**Deliberately not changed.**
- Frontmatter `description`.
- "You raise no questions; gaps go under **Chưa hỏi**".
- Part B (the info matrix). Gate 3 is not run in EVAL-4's report step, and no EVAL-3 item touches
  it.
- §3 and §9.

## tekla-conversion-plan (6 changes)

| # | Change | Reason | Touched |
|---|---|---|---|
| 1 | Inputs: a **Status wins** paragraph, as in the report. `proposed_simulated` and `proposed_closed_by` are shown `(mô phỏng)`, still blocking | Fix 4; items 1, 12 | Inputs |
| 2 | Inputs: a mark list copies `summary.mark_sets` (gaps kept, `ít nhất` + source) | Row b1 (P32 copied F-200); items 2, 12 | Inputs |
| 3 | Gate 1 draft: the `gate1.reasons` are paraphrased in Vietnamese with their Q-ids | Items 11, 12 | Gate 1 |
| 4 | Gate 1 **Lưới trục**: an answer-built system (`source: engineer_answer`) goes through select, X/Y and units. That file's `grid_none_found` / `grid_gate1_confirmation` are separate and still block. A file with no usable or selected grid system is named with its open `grid_system_missing` as a blocking reason. After the engineer's `no_grid=yes`, it has no grid by the engineer's statement | Fix 1; row b3; items 6, 12; ADR-0013; G gate note | Gate 1 |
| 5 | Style: a tool or environment line not run or verified (`tekla-cli info`, `validate`) reads `chưa chạy` | Row d (P22; R P-335); item 11 | Style |
| 6 | Hard stop "No grid system at all" becomes "a file with no usable or selected grid system and no `grid_system_missing` question for it". A file without a grid no longer stops the draft. It is a blocking reason in it, and `ready_for_gate1` stays false, so the gate is not weakened | Item 6 (consistent wording); the draft rule | Hard stops |

**Deliberately not changed.**
- Frontmatter `description`.
- Gates 2 and 3. No EVAL-3 item touches them, and EVAL-4 does not run them.
- The R-arm P-371 wording on piles in the R8 gap list. It is outside the brief, and a plan-wording
  fix is not needed for any EVAL-3 H claim.
- The **End** section.
- The units rule.

## Not fixed by tools (skill-side fallbacks)

- **Note scope.** No dedicated field exists. `--field scope=T…` uses the free `fields` key: the
  schema allows any snake_case key, and the CLI checks only its shape (run: F-001 on 286 with
  `fields.scope`). The tool does not check that the entry exists or that the font gate allows it.
  The skill therefore requires an allowed heading and sends a blocked one to a question. The
  heading stays out of `--entries`, because a `note_item` value must quote exactly the cited
  entries.
- **Two titles on one sheet.** `list-sheets` has no flag for this. The rule is reader judgement
  only.
- **Reader's grid reading.** There is no finding kind for a grid, so it goes in as
  `ask --supplement` on `grid_system_missing` (see above).
- **`find-text` `notes` wording** for `legacy_ascii_text` ("approve the font row"). The skills
  state that its answer unblocks nothing. Tool note for the next wave.
- **Heading lists in shorthand.** Fixed in the tool by 7564542: a shorthand list (`dầm d2-4, 5`)
  is not expanded and names no mark; it goes to `marks.json` `warnings` and keeps the family
  incomplete. `complete` needs a schedule, or headings equal to the plain plan marks, and no
  blocked plain text in the file. Residual risk: a false `plan_only` (286 at `54d46cb`: 44,
  including `d2-3`, `d2-4`, `d2-5`, `d2-7`). The reader step 6 and report §8 rules added in the
  refresh handle it (one reader question per file quoting the shorthand headings).

## Not verified by running

- (Moved to "Verified by running" at the 54d46cb refresh: `no_grid=yes` and ADR-0013 decision 6.)
- **The engineer-built grid** (status side now covered by `tests/test_grid_gate.py`)
  (`source: engineer_answer`, `source_answer`), the words-only
  engineer answer, and `grid_answer_contradicts_drawing`. All three need `--role engineer`, which
  this check never records. Evidence: the orchestrator's 461 end-to-end run in the wave-3
  integration log (G + C merge) and the CHANGELOG package G and C bullets.
- **`grid_none_found` / `grid_gate1_confirmation` still blocking after an engineer-built grid.**
  Source: the G gate note in the integration log. Both are raised on 461 (Q-009) and 286/290
  (Q-021, Q-022) before any answer.
- **285 and 161** (the `DETAIL ON` heading, the ARC bubbles) were not in this run; the skills
  cite no claim that rests on them alone.
- **The `--unassigned` route** is unchanged from rev 5 and was not run again.

## Verified by running (`a91fa9b`, LibreDWG, scratch work folders)

- **`no_grid=yes` (461, simulated, `54d46cb`).** Accepted with exit 0; refused with exit 1 when
  another key is added. `grid-system` warns "recorded, builds nothing" and its stdout shows
  `blocking_open 0`; status keeps Q-019 open with an `answers:` reason; `questions.md` prints the
  **Hoặc** line. Engineer side (closes; gate 1 opens after the rerun; a built system left out of
  the select answer stays open; role staleness): `tests/test_grid_gate.py`, 18 passed.

- **Pipeline.** `intake`, `read-structure`, `callouts`, `marks`, `grid-system`, `status` and
  `questions-md` exit 0 on 286 + 290, 267 + 433 and 461.
- **Status.** `gate1.closed` is always present (`[]`). After simulated answers,
  `gate1.non_engineer_answers` lists them (5 on 286 + 290, 2 on 461), with `answers:` and
  `closures:` reasons.
- **`grid-systems.json` after simulated answers.**
  - `proposed_simulated` appears in `units.status`, `axis_assignment.status` and
    `files[].units_answer.status`.
  - 30 conflicts carry `proposed_closed_by: not_selected`, and none has a `closed_by`.
  - `file_sets.status` stays `pending`.
  - Each such answer is warned.
- **461.** A blocking `grid_system_missing` (Q-019) is raised beside `grid_none_found`. A
  simulated answer with grid values builds nothing (warned); status keeps Q-019 blocking, and
  `questions.md` prints the answer `(mô phỏng)`. `ask --supplement Q-019` is accepted.
- **Marks.**
  - `summary.mark_sets`: 433 `M1`…`M8` and `GM1`…`GM5`, `GM7`, `GM8`, both `complete: false` from
    `plan_marks`; 286 `ĐC` from `detail_heading` only.
  - `compared_with`, and `matching[]` `schedule_tables` / `detail_headings`.
  - `summary.size_comparisons`: 286 + 290 compare 0 and leave 66 not compared (59 at `54d46cb`: 286 lost 7 shorthand heading
    matches), all "matched
    through detail headings only".
- **Callouts.**
  - `unparsed_by_code`, including `symbol_glyph_unverified` 538 on 290 (`3ù20`).
  - `callout_unparsed` Q-054 (286), Q-055 and Q-056 (290).
  - `rejected` 47 and 25, with `rejected_by_reason`.
- **Text gate.**
  - `find-text` on 267 gives `blocked_in_scope` 803 for two unrelated queries, and `notes` name
    Q-006, Q-008 and Q-009.
  - `legacy_ascii_text` Q-009 covers 786 ROMANS entries; its message says its answer unblocks
    nothing.
- **Sheet numbers.** `sheet_number_gap` Q-050 on 290 reads "missing 25".
- **Tables.** `sheet-text --region=` on 286 model#01 returns the row `Ø<10mm | CI` (T001075,
  T001074).
- **Questions and findings.**
  - `ask --amend` returns `amended`, then `unchanged` for the same values.
  - It exits 2 once the question has a simulated answer, and for a producer question.
  - `finding add --kind note_item … --field scope=T001029` records F-001 with `fields.scope`.
