# Part mode

Part mode is on once `W/parts/manifest.json` exists. The scout cuts the set into **parts**; each part is read, checked,
reviewed and locked on its own; the assembler joins the locked parts. Roles and rules: [SKILL.md](SKILL.md). Commands:
[tools.md](tools.md). `W` is the work folder of `harness intake`; `PT` = `W/parts/<part>`.

## Parts

| Kind | Ids | Holds |
|---|---|---|
| `cross` | `all-grid-levels`, `all-notes-materials` (a part over the cap splits as `<id>-<suffix>`) | grids and levels; general notes and materials, per block |
| `member` | `<block>-<family>`, split `<block>-<family>-<letter>` with `split_of` | one family of one block: piles, caps, ground beams, columns |
| `bookkeeping` | `scout`, `all-assembly` | the manifest and its review; K1–K14 and the cross-part checks |
| `no_sheet` | `all-no-sheet` | files with no detected sheet (`files[]`) and clusters on no sheet |

A part id matches `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`. **Cap per part:** at most 4 sheets and 1,500 printed entries
(`part_over_cap`); split the part, never raise the cap. A part reads only its own sheets; a value of another part is cited
from that part, which the manifest lists in `inputs`.

## Stages

| # | Stage | Who | Does | Done when |
|---|---|---|---|---|
| 0 | Intake | orchestrator | `drawing-intake` skill | `harness status W` shows every producer `fresh` |
| 1 | Scout | `doc-reader`, Opus high, 150k | phases 0–1, `W/parts/manifest.json`, Reach and Breakdown tables | `part manifest-check` exit 0 |
| 1b | Manifest review | fresh `doc-reader`, 15 min | the manifest against the sheets: block placement, caps, inputs ([review-rubric.md](review-rubric.md) § Manifest review) | `W/parts/scout/review/round-1/review.md`; then `scout` is `locked` |
| 2 | Cross parts | 2 part readers in parallel | `all-notes-materials` (phase 2), `all-grid-levels` (phase 3; needs units answered); `all-no-sheet` when the manifest has it (phase 0 reach of its files and clusters) | both `locked` before stage 3 |
| 3 | Member parts | one part reader each, Opus high | phase 4; a part starts when every part in its `inputs` is `locked` | `part check` exit 0, then 4–5 |
| 4 | Part review | fresh `doc-reader` | `part review-sample` prompts, [review-rubric.md](review-rubric.md) | `PT/review/round-<n>/{blind-answers.md,review.md}`; blind answers sealed by sha256 |
| 5 | Fix and lock | same reader, orchestrator | fix the defects, `part check` exit 0, narrow round-2 review | receipt `locked` |
| 6 | Assembly | assembler, 120k | `harness status W --verify` (§ Lock and reopen), `part check` on every `locked` part (one that reads `reopened` or `stale_input` goes back through steps 2–4 of § Dispatch and fix loop), the questions of `part conflicts`, `part chain --block <id>` per block; K1–K14, C1, C11, C12 | `part check --part all-assembly` exit 0 |
| 7 | Take-off | `drawing-analysis-report` Part C | `takeoff render`, `takeoff plan`, `takeoff check` (flags there); this skill only points to it | `takeoff check` exit 0 |
| 8 | Spot check | orchestrator, engineer | `part spotcheck`, `part answer-key`, `part score` | the score is recorded in [improvement-loop.md](improvement-loop.md) |

Sonnet high is a **trial** for count parts (piles, caps, stubs): the orchestrator passes the model on the spawn, the
`doc-reader` frontmatter stays. A worse score on run 4 means Opus again. `takeoff render` covers `checked`, `reviewed` and
`locked` parts; an unlocked part is marked `chưa khóa (…)`.

## Manifest

The scout writes `W/parts/manifest.json` (schema `parts-manifest`; validate with `harness validate parts-manifest <file>`),
then runs `harness part manifest-check W [--input-dir I]` to exit 0. Per part: `id`, `kind`, `order`, `inputs`, `sheets[]`
(`file`, `sheet`, `number_entry`, `title_entry`, `role`, `views[]`), `clusters[]`, `tables[]`, `layers`, `marks_regex`,
`expected_sources`, `producer_questions`. A **cluster** is the triple `{file, sheet|null, side}`: every cluster of text
outside a frame belongs to exactly one part. Every sheet is in one block and one part per family. A synthetic example:

```json
{"schema_version": "0.1",
 "blocks": [{"id": "ALPHA", "grid_system_ids": ["S001"], "origin_note": "own grid, origin at the lower-left crossing"},
            {"id": "BETA", "grid_system_ids": ["S002"], "origin_note": "own grid, origin at the lower-left crossing"}],
 "parts": [
  {"id": "scout", "kind": "bookkeeping", "order": 0},
  {"id": "all-grid-levels", "kind": "cross", "order": 1, "expected_sources": ["text", "linework"], "producer_questions": ["Q-003"],
   "sheets": [{"file": "plans/set.dxf", "sheet": "model#06", "number_entry": "T000012", "title_entry": "T000012", "role": "plan"}]},
  {"id": "all-notes-materials", "kind": "cross", "order": 1, "expected_sources": ["text"], "producer_questions": ["Q-003"],
   "sheets": [{"file": "plans/set.dxf", "sheet": "model#05", "number_entry": "T000010", "title_entry": "T000011", "role": "notes"}]},
  {"id": "ALPHA-piles", "kind": "member", "block": "ALPHA", "family": "piles", "order": 2, "inputs": ["all-grid-levels", "all-notes-materials"],
   "producer_questions": ["Q-001", "Q-003"],
   "sheets": [{"file": "plans/set.dxf", "sheet": "model#01", "number_entry": "T000001", "title_entry": "T000002", "role": "plan"}],
   "clusters": [{"file": "plans/set.dxf", "sheet": "model#01", "side": "below"}],
   "layers": {"outline": ["S-PILE-OUT"], "symbol": ["S-PILE"]}, "marks_regex": "^P[0-9]+$", "expected_sources": ["text", "linework"]},
  {"id": "ALPHA-piles-b", "kind": "member", "block": "ALPHA", "family": "piles", "order": 2, "inputs": ["all-grid-levels", "all-notes-materials"],
   "split_of": "ALPHA-piles", "producer_questions": ["Q-003"], "sheets": [{"file": "plans/set.dxf", "sheet": "model#02", "role": "plan"}]},
  {"id": "BETA-piles", "kind": "member", "block": "BETA", "family": "piles", "order": 2, "inputs": ["all-grid-levels", "all-notes-materials"],
   "sheets": [{"file": "plans/set.dxf", "sheet": "model#03", "number_entry": "T000007", "title_entry": "T000008", "role": "plan"}],
   "marks_regex": "^P[0-9]+$", "expected_sources": ["text", "linework"], "producer_questions": ["Q-002", "Q-003"]},
  {"id": "all-assembly", "kind": "bookkeeping", "order": 4, "inputs": ["ALPHA-piles", "ALPHA-piles-b", "BETA-piles"]}],
 "acks": [{"warning": "grid_origin_other_block|plans/set.dxf|model#03|ALPHA", "question": "Q-002", "reason": "title block and number series place this sheet in BETA; the designer is asked"},
          {"warning": "revision_from_table|plans/set.dxf|model#01|T000001", "question": "Q-001"}]}
```

- **Place a sheet** in its block by title, grid origin and number series together; a sheet that shows another block's origin or
  series gets a question (E41).
- **Questions that hold a part.** `harness status` holds a part un-`ready` only for blocking questions tagged with it and the ids
  in its `producer_questions`. List there every blocking question you raise about the part's sheets (block placement E41/E02, copied
  linework E40, a revision in doubt, a mis-title), and `reader_breakdown_confirm` in every member and cross part; list every open blocking
  `callouts` or `marks` question about the part's marks (unlisted, those block every part). A placement in doubt still puts the
  sheet in the part its title block names: the question in `producer_questions` keeps that part from `ready`.
- **Cite `number_entry` and `title_entry`** for every sheet; a sheet with no readable number gets the entry that proves its
  sheet is that one, and a question.
- **Revision** comes from the title block, never from an abbreviation table (`revision_from_table`).
- **Warnings** of `manifest-check` (`grid_origin_other_block`, `linework_duplicate`, `revision_from_table`) block exit 0 until
  each has an entry in `acks[]`: `{warning, question?, reason?}` with at least one of the last two. The `warning` is the exact id
  the tool printed, `code|file|sheet|…`; an ack that matches no warning is `ack_unmatched`.
- **Units** come only from the engineer's answer, which the orchestrator records (SKILL.md § Asking). Until then `manifest-check`
  reports `unit_unanswered` (no ack clears it) or `unit_answer_unread`: hand the units question ids back and stop; resume after the
  answer. A missing `question-registry.json` means `harness intake` has not run.
- `inputs` lists every part whose rows this part's hand sums or cites use; an unlisted one is `cite_foreign_part`.
  `all-assembly` lists every member part. `order` is later than every input (`order_not_after_input`).

## Brief

The orchestrator gives a part reader its **brief**, never the whole skill. Fill it from the part's manifest entry:

```
Part: <id> (<kind>), block <block>, family <family>. P = <path>, W = <path>. Model: <model>, effort high.
Read: SKILL.md § Roles, Seen/unread/absent, Claims, Done when by tool, Phases (your phase's item), Blocked text, Asking, Hand-back, Hard stops;
      tools.md § Reading, § Linework, § Recording, § Measured findings, § Part mode; <reading-method sections by kind>.
Sheets: <sheets[] with number_entry, title_entry, role, views[]>   Clusters: <clusters[]>   Tables: <tables[]>
Layers: <layers>   marks_regex: <regex>   Expected sources: <expected_sources>
Inputs (locked; cite, never re-record): <inputs>   Questions that hold this part: <producer_questions> (supplement a producer's; to cite a scout's, add your part to it with `ask --part <id>` on its key)
Write: --part <id> on every `finding add` and `ask`; PT/values.json (schema part-values); PT/notes.md (60 lines at most:
       scope, unread and absent lines with Q-ids, tool gaps, `needs: <part>, <what>` lines).
Locked: after the lock, edit nothing under PT until the orchestrator records `reopened`; receipts.json is written by `harness part receipt` only.
Done when: `harness part check W --part <id>` exits 0. Then hand back; run no receipt, no `answer`.
Context target: 200k. Print no whole artefact.
```

| Part | Method sections in `Read` |
|---|---|
| `all-grid-levels` | reading-method.md § Phase 3, § Recording forms, § Search terms, § Phase 6 (C2–C10), § Required counts |
| `all-notes-materials` | § Phase 2, § Recording forms, § Search terms, § Phase 6 (C2–C10), § Required counts |
| member | § Phase 4, § Recording forms, § Search terms, § Phase 6 (C2–C10), § Required counts; [steel-industrial.md](steel-industrial.md) or [conventions.md](conventions.md) as the family needs |
| `all-no-sheet` | § Phase 0 (reach of its files and clusters), § Recording forms, § Search terms |
| `all-assembly` | § Phase 5, § Phase 6, § Required counts, C1, C11, C12 |

A `values.json` row is `{row, mark|subject, field, value, file, sheet, view, state, cites, hand_sum}`; `view` is copied from that sheet's manifest `views[]`, or left out; `state` is `seen`,
`asked`, `unread` or `absent`; `cites` holds `findings`, `questions`, `entries`, `geometry`, `grid_systems`. A grid row cites the
finding and the grid system; the grid system backs no number. The reader fixes a `part check` problem in `values.json` or the
findings, never by editing a tool-written file: `input_invalid` names such a file to regenerate, not a row.

## Dispatch and fix loop

The orchestrator runs every receipt (`reopened` too, § Lock and reopen) and `part conflicts`; readers run only `part check` and hand back.

1. Spawn the reader with its brief. At most **6 part readers** run at once; `contents` and `geometry` take 60–83 s under load.
2. The reader reaches `part check` exit 0 and hands back. The orchestrator records
   `harness part receipt W --part <id> --kind checked`, then runs `harness part conflicts W` (it raises a question for each
   value two parts state differently, a plan count only when two parts read the same sheet; an answered question keeps its
   answer on a rerun; the questions block `ready`, not the lock). It runs again before assembly.
3. Spawn a fresh reviewer (`harness part review-sample W --part <id> --seed <n> [--n <k>]` gives its blind prompts; the orchestrator picks `<n>`
   after `checked`, never the reader). Its verdict is `pass`, `fix` or `engineer`.
4. `pass`: `harness part receipt W --part <id> --kind reviewed --review <absolute W/parts/<id>/review/round-1/review.md> --round 1
   --verdict pass`, then `--kind locked`. `locked` needs the latest `reviewed` receipt on the current hash to be `pass` (a later `fix` blocks it) and every input part
   `locked`.
5. `fix`: send the defect list to the same reader (SendMessage), else to a fresh reader with the list. Any edit changes the part
   hash: the reader reruns `part check` to exit 0, the orchestrator records `checked` again and a narrow round-2 review
   (`--round 2`) covers the defects only. A round 2 that fails goes to the engineer (`--verdict engineer`): he rules in chat. If he accepts, the orchestrator writes
   `review/round-3/review.md` (the blind-answer sha line, his words verbatim, verdict `pass`), records `--round 3 --verdict pass`, then
   `locked`. If he asks for fixes, the reader fixes, `checked` is recorded again and a fresh narrow round-3 review runs. A `fix` or `engineer` verdict is overturned only by a `pass` of a higher round: the tool refuses a `pass` recorded at the same round.
6. `harness status W` shows per part `status`, `blocking_open_ids` and `ready`; a part is done when `locked` with no
   blocking question open (`project_blocking_ids` and `parts_project_reasons` name what blocks the project; a `parts_error` means fix
   the named record first). `stale_input` (an input part's hash changed after the lock) and `reopened` (the part's own hash
   changed after the lock) count as `reading`: record `--kind reopened --reason "<why>"` (a locked receipt is the latest, so `checked`
   is refused until then), then repeat steps 2–4 for that part.

Several writers share `W`: a write call waits for the work-folder lock (tools.md); the wait and an exit 3 are handled there.

## Lock and reopen

A `locked` part refuses `finding add`, `finding withdraw` and `ask` writes (exit 1, "reopen first"). Reopen it only for a defect
found later, and only the orchestrator does: `harness part receipt W --part <id> --kind reopened --reason "<why>"` (a non-empty
reason). The part then counts as `reading` and every part that lists it in `inputs` becomes `stale_input` until it is `locked`
again. A hand edit of `values.json` after the lock, a revised drawing, a changed block row, a changed grid system that a row cites, or a question (cited by a row or held by one of the part's own findings) that goes obsolete or whose
blocking flag changes also shows as `reopened`: the part is checked and reviewed again. An answer alone never moves the lock. A reader
(resumed or new) never edits `values.json`, `notes.md` or `receipts.json` of a locked part; the way back is the `reopened` receipt of
the orchestrator. Before assembly the assembler runs `harness status W --verify`, names every part it reports with
`check_failed: true` or `input_check_failed` to the orchestrator and stops. The command checks every `locked` part. A part with `check_codes` is reopened: the orchestrator records
`harness part receipt W --part <id> --kind reopened --reason "part check: <check_codes>"`. Two codes never reopen a part on their own: `input_invalid` (rerun the producer of the file the check names) and `changed_during_check` (run the command again). A part with `check_error` (the check could not run) is never reopened: fix what the message names and run the command again. A part with `input_check_failed` waits for the input it names; `takeoff render | plan | check` load the status with that verification themselves.
