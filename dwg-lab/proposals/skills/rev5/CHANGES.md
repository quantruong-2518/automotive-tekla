# Rev 5 skill proposals — changes from rev 4

PROPOSAL. These folders replace `.claude/skills/<name>/` only after the engineer approves them
(AGENTS.md principle 7). Base: rev 4 as active at `c99e258`. Each folder is a full copy;
`diff -r .claude/skills/<name> dwg-lab/proposals/skills/rev5/<name>` shows the edits.

Purpose: EVAL-3 runs on skills that match the tool-wave-2 CLI and close the skill items of
EVAL-2 (`dwg-lab/proposals/skills/EVAL-2.md`, ranked fixes). "Fix N" below is the EVAL-2
ranked-fix number.

**Verified against the CLI on `c5a4fac`** (branch `feat/tool-wave-2`): every command, flag,
field and question code the four skills cite was checked against `uv run harness <cmd> --help`,
`schemas/`, `src/tekla_harness/` and the CHANGELOG [Unreleased] tool-wave-2 entries, and the
behaviour below was run on a synthetic work folder (two framed DXF sets plus one DXF with text on
no sheet, built with `tests/_dxf_fixtures.py`).

Size (lines, SKILL.md): intake 71 → 81, reader 123 → 140, report 75 → 85, plan 95 → 102. The
writing-for-agents skill sets no line limit; the growth comes from replacing manual rules with
the wave-2 tools and from the role distinction (simulated vs engineer answers).

## Facts that landed differently from the design (fixed in this revision)

- `harness answer --role engineer|simulated` is required (exit 2 without it). Every answer command
  `harness status` and `questions.md` print carries `--role engineer` and is labelled as the
  engineer's own step (`the engineer runs: …`; `Lệnh trả lời (kỹ sư tự chạy, tác tử không chạy
  thay)`). Rev 5 first told the agent to record answers with `--role engineer|simulated`; it now
  follows RTI-0011: the agent never records `--role engineer`, relays an eval simulator's answer
  with `--role simulated`, and asks the orchestrator when no role is stated.
- A closure counts only when `harness status` accepts it and lists it in `gate1.closed`. The
  producer still writes `closed_by` into its question document, but status refuses it when the
  settling answer (e.g. `grid_system_select`) is not the engineer's: the question stays blocking
  and a `closures:` reason appears. Observed: a simulated select answer left Q-030
  (`closed_by: not_selected` in `grid-system-questions.json`) blocking, with no `gate1.closed`.
  In EVAL-3, where every answer is simulated, nothing closes. Every "carries `closed_by`" rule now
  reads "listed in `gate1.closed`".
- A `simulated` units answer removes the file's `units:` reason; it reappears as an `answers: …
  units_confirm_all … simulated role` reason. So the reader's units precondition is simply "no
  reason starting `units:`"; the `gate1.non_engineer_answers` exception rev 5 first added is not
  needed. A contradicted unit still gives a `units:` reason and still stops the reader.
- `file_set_relation` answers take repeated values: `--value set1=a.dwg,b.dwg --value set2=c.dwg`,
  every file of the question exactly once.
- `--unassigned` (`sheet-text`, `find-text`, `dimensions`) means the entries on no sheet **or on
  several**, not "outside every sheet". Plain `find-text` skips them
  (`counts.unassigned_entries_not_searched`).
- `member_mark_prefix_meaning` is one blocking question per file (raised by `harness marks`), one
  subject per plan-mark prefix; callouts no longer asks it.
- `harness dimensions W <file> [--sheet ID | --unassigned] [--layer L] [--max N] [--input-dir I]`:
  `--input-dir` is needed only for a native DXF (exit 2 without it) and ignored for a DWG (the
  converted DXF is read), so the skill always passes it. `handle` is null for a dimension inside a
  block; `block_path` then locates it.

## drawing-intake (6 changes)

| # | Change | Reason | Touched |
|---|---|---|---|
| 1 | New bullet **File sets**: intake's blocking project-level `file_set_relation` for two or more readable drawing files; its answer `--value set1=… --value set2=…`, each file once; grid-system compares within a set; until it is answered a cross-file conflict does not block and its gate-1 reason points at `file_set_relation` | Fix 5 (5d, D7) | Reading the results |
| 2 | "After any … answer" also covers the file-set answer; a question another answer settles is closed only when `gate1.closed` lists it; a `closures:` reason leaves it blocking | Fix 5 (5a–5c); closure contract (P3 review M2) | Reading the results |
| 3 | **No sheet detected**: the file's text is reachable with `--unassigned` on `sheet-text` / `find-text`; report the file so the reader takes that route | Fix 4 | Reading the results |
| 4 | **Legacy fonts**: ASCII text in a legacy font shaped like encoded Vietnamese (`legacy_ascii_suspect`) is blocked too | Fix 2b, applied to the gate rule of fix 3 | Reading the results |
| 5 | **Answers** rewritten per RTI-0011: the printed command (`--role engineer`) is the engineer's own step, handed to the engineer; the agent records only an answer the orchestrator relays from an eval's simulator, from the question's **Lệnh trả lời** line in `questions.md` with `--role engineer` *replaced* by `--role simulated` (argparse keeps the last `--role`: appending would record an engineer answer — checked); no role stated → ask the orchestrator. Rev 4's `harness answer` template line (no `--role`, now exit 2) is removed rather than given a role: the per-question line is the single source and names the values (the `answers:` re-answer command in `status` has no `--value`). "Only the engineer answers" removed (contradicted eval relays) | Fix 10; RTI-0011; EVAL-3 protocol §6.2 | Answers |
| 6 | `questions-format.md`: reader evidence on a producer question (`harness ask --supplement Q-id`, printed under it as "Bổ sung của người đọc") is also what the reader writes into `questions.md` | Fix 7 | questions-format.md |

Also cut: "It closes only on `--value unit=…`" (Units bullet): the command `questions.md` prints
names the value, so the line was a cache of the environment.

**Deliberately not changed.** Frontmatter `description` (rev 4 tuned it with an 80-run trigger
eval). Steps 1–6 and their completion criteria (step 3's split — intake, read-structure,
grid-system and reader block gate 1; callouts and marks block lot specs — still matches
`status`; marks' new blocking prefix question is a lot-spec blocker). The converter bullet: wave 2
does not record the LibreDWG version or change the ERROR-line rule (fix 9 is an engineer/licence
decision), so the rev-4 text still matches the code. The `font_encoding_proposed` closure rule
and the hard stops. Step 2 still runs `callouts` before `marks`: D6 moves the prefix question to
marks without changing the order.

## structural-drawing-reader (12 changes)

| # | Change | Reason | Touched |
|---|---|---|---|
| 1 | Steps 3–7 precondition and the matching hard stop: "no reason starting `units:` in `gate1.reasons`"; a `simulated` units answer shows as an `answers:` reason and is enough for reading. Rev 4's "free of units reasons" was ambiguous (an `answers: … units_confirm_all` reason could be read as one and stop every EVAL-3 runner after step 2) | Fix 10; EVAL-3 §6.3 | Before you start; Hard stops |
| 2 | Tool list: `sheet-text … <sheet_id>\|--unassigned` and `find-text … [--unassigned]`; plain `find-text` does not search text on no sheet or on several | Fix 4 | Before you start |
| 3 | Tool list: `harness dimensions W <file> --input-dir I [--sheet ID\|--unassigned]`, drawing units | Fix 11 | Before you start |
| 4 | Tool list: `harness ask W --supplement Q-… [--file --sheet] --where --found --text`, producer questions only, no `--code`/`--blocking`; `--withdraw-supplement <key> --reason` | Fix 7 | Before you start |
| 5 | **Blocked text** rewritten as a positive provenance rule: decide by `meaning` alone (ASCII can be blocked: `legacy_ascii_suspect`); every class, value, topic and keyword rests on an allowed entry, a finding or an answer; a blocked title is written `<sheet id>: tiêu đề bị chặn (T…)` + font Q-id; a finding `finding list` marks `stale` (a row in its `decoded_by` changed) is checked again | Fix 3; fix 2b; fix 10 (`decoded_by`) | Blocked text |
| 6 | **A file with no detected sheet**: steps 2, 3, 7 read its text via `--unassigned`; step 1 cites the `sheets_not_detected` question; steps 4–6 as usual. Any `unassigned` text: findings, questions and supplements omit `--sheet` | Fix 4 | A file with no detected sheet |
| 7 | **Asking**: reuse a producer question's id and add evidence with `ask --supplement` instead of a second question | Fix 7 | Asking |
| 8 | **Asking**: an answer "engineer or simulated" contradicted by the drawing → blocking reader question quoting both (keeps the EVAL-3 trap catch explicit under `--role simulated`) | Fix 10; EVAL-3 §8.6 | Asking |
| 9 | **Asking** + step 1: the reader's own `reader_file_set_relation` replaced by intake's `file_set_relation`; cross-file comparison waits for its answer; drawing-list question per set once it is answered | Fix 5 (5d) | Asking; step 1 |
| 10 | Step 4: grid sanity check runs on `harness dimensions` (measured value vs sum of spacings, both in drawing units; quote `handle`, or `block_path` when null, and the spacing string); a question is settled only by its answer or by `gate1.closed`, never because it seems to sit on a rejected system. A simulated answer is enough here: this is reading, not a gate | Fix 11; fix 5 and EVAL-2 judge l3 #19 | Step 4 |
| 11 | Step 5: `blocked_candidates` are not candidates and are cited by entry id with the font question; storey candidates go to read-structure's `level_storey_selection` via `ask --supplement`; "allowed" level texts only; a level finding takes the extractor's confidence for that value | Fix 7; fix 1a; fix 12 | Step 5 |
| 12 | Step 6: `blocked_columns`; `size_compared: false` → `chưa so sánh` with its `size_not_compared_reason`; title member word goes to the file's `member_mark_prefix_meaning` (one subject per prefix, raised by marks) as `ask --supplement`; callouts unparsed per `summary.unparsed_by_reason`. Rules: a `low` finding carries `--question` | Fix 8; fix 7 (1b, D6); fix 11; fix 12 | Step 6; Rules |

**Deliberately not changed.** Frontmatter `description` (trigger-tuned in rev 4). The units hard
stop before step 3 and the step order. Step 1's class list: EVAL-2 judge listed missing slots
(drawing list, lintels, ground beams), but no fix number covers it and `finding add` validates
the class list in code, so a change needs a tool change first. Steps 2, 3 and 7 text (they now
also run on `--unassigned` text through the section above, without restating it).
`conventions.md` (no EVAL-2 item). The level-confidence rule already existed in rev 4; it was
only sharpened, not duplicated. `--confidence` stays out of the `finding add` tool line (rev 4
did the same; step 5 names it where it is used). `dimensions --layer`/`--max` stay out of the
tool line: `--help` gives them when a grid layer needs filtering.

## drawing-analysis-report (8 changes)

| # | Change | Reason | Touched |
|---|---|---|---|
| 1 | Inputs: `harness finding list` for `stale` flags and `summary.by_class` | Fix 10, fix 11 | Inputs |
| 2 | §1 Kết luận names the answers not given by the engineer (`gate1.non_engineer_answers`) among the gate-1 blockers | Fix 10; EVAL-3 §6.5 | Part A §1 |
| 3 | §4 a file with no detected sheet: its `sheets_not_detected` question and the findings on its text | Fix 4 | Part A §4 |
| 4 | §5 blocked count from `list-sheets` `files[].blocked_text_count`; font rows that decoded cited text (`decoded_by`) and stale findings | Fix 11; fix 10 | Part A §5 |
| 5 | §7 levels: `blocked_candidates` by entry id with the font question | Fix 1a, fix 3 | Part A §7 |
| 6 | §8 marks per sheet (`summary.by_sheet`), `blocked_columns`, size conflicts printed beside the compared / not-compared counts (`summary.size_comparisons`), callouts `summary.unparsed_by_reason` | Fix 8, fix 11 | Part A §8 |
| 7 | §10 questions closed by another answer listed separately from `gate1.closed` with its reason; a question blocks until the engineer answers it or `gate1.closed` lists it, whatever system or file it seems to sit on; an answer in `gate1.non_engineer_answers` leaves it blocking | Fix 5; fix 10; judge l3 #19 | Part A §10 |
| 8 | Style: positive provenance rule for every topic, title and keyword, headings and §2/§9 titles included; blocked item written `tiêu đề bị chặn (T…)` + Q-id; an answer in `gate1.non_engineer_answers` (role `simulated`, or none) printed `(mô phỏng)` | Fix 3; fix 10 | Style |

**Deliberately not changed.** Frontmatter `description`. The rule "you raise no questions; gaps
go under **Chưa hỏi** in §9 and in your final message to the orchestrator" — rev 4 already covers
fix 12 "the report writer returns gaps to the orchestrator", and the *Done when* already requires
every `low` or unconfirmed value to carry a question id or a **Chưa hỏi** entry (fix 12 "a `low`
finding needs a question"). Part B (info matrix): no EVAL-2 item, and gate 3 is not run in
EVAL-3. `questions.md` does not print an answer's role; the report reads it from
`gate1.non_engineer_answers` (or `answers.json` `answered_by_role`), not from `questions.md`.

## tekla-conversion-plan (5 changes)

| # | Change | Reason | Touched |
|---|---|---|---|
| 1 | Units: no lot proposed for building until the engineer (`answered_by_role: engineer`) answered units and grid selection | Fix 10 | Inputs |
| 2 | Gate 1 draft: `ready_for_gate1: false` is always so while a gate answer is not the engineer's (`gate1.non_engineer_answers`), as in an eval; the draft calls gate 1 not ready throughout | Fix 12 (draft headed by reasons); fix 10; EVAL-3 §6.5 | Gate 1 |
| 3 | Scope per file set (`file_set_relation`) as well as per building | Fix 5 (5d) | Gate 1 |
| 4 | Positive provenance rule for every scope row, assumption and risk title; blocked item written `tiêu đề bị chặn (T…)` + Q-id; a question blocks until the engineer answers it or `gate1.closed` lists it; one whose answer is in `gate1.non_engineer_answers` is shown `(mô phỏng)` and still blocks, with every value resting on it | Fix 3; fix 10; fix 5 and judge l3 #19 | Gate 1 |
| 5 | End: a draft ends with the reasons to clear first, `gate1.non_engineer_answers` included, instead of "the gate the engineer must open next" (which invited a gate claim — Critical under EVAL-3 §6.5) | Fix 12; EVAL-3 §6.5 | End |

**Deliberately not changed.** Frontmatter `description`. Fix 12 items rev 4 already handles and
EVAL-2 did not fault after rev 4: the empty levels table (one line with question ids), one Tekla
model or several for `separate=` buildings (R13), a file outside every selected system (a named
scope decision), compound rule statuses cited as written, and gate 1 listing no lots. The
`planner.md` agent definition already says "The lot split belongs to gate 3 (`05-sequence.md`)
only" since rev 4 (commit 5ed1685); it lies outside the four skill folders and is not touched.
Gates 2 and 3: no EVAL-2 item and not run in EVAL-3.

## Open points — resolved against `c5a4fac`

- `find-text --unassigned` searches **only** the entries on no sheet or on several (hits carry
  `sheet_id: unassigned`, `counts.unassigned_entries_searched`); plain `find-text` searches sheets
  only and reports `counts.unassigned_entries_not_searched`. Run on the synthetic folder. The
  reader tool line now says so.
- `finding add` on unassigned entries: omitting `--sheet` works for every kind except
  `sheet_class` (run: `note_item` on a no-sheet file → `F-001`). `--sheet unassigned` is refused
  (exit 1, "has no sheet 'unassigned'"). `harness ask` and `ask --supplement` do not validate
  `--sheet` and accept `unassigned`. Rev 5 uses one rule: omit `--sheet` on unassigned text
  everywhere. The tools' inconsistency is a tool note, not a skill change.
- `legacy_ascii_suspect` landed as designed (P1: suspect shapes in TCVN3/VNI or unknown-encoding
  fonts, blocked ahead of the ASCII rule; reason in sheet-text, callouts, levels and marks).
  The `harness answer` printed in `questions.md` and status carries `--role engineer` and the
  engineer-only label (P3 review M1); the intake **Answers** section is rewritten to match (above).

## Not verified by running

`member_mark_prefix_meaning` from `harness marks`, `blocked_columns`, `size_compared` and
`summary.unparsed_by_reason` with real data: the synthetic folder had no marks or callouts, so
these were checked against `marks.py`, `callouts.py`, the schemas and the CHANGELOG only.
`legacy_ascii_suspect`, `blocked_candidates` and `decoded_by`/`stale` likewise (the shipped
font rows are approved, so the synthetic folder blocked nothing).
