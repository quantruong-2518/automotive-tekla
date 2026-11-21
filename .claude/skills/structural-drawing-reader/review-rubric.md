<!-- PROPOSAL rev11: part-mode rewrite of the installed review-rubric.md; installed only after the independent review. -->
# Review rubric: an independent check of one part

You are the **reviewer**: a fresh dispatch that has seen nothing of the part. You re-derive a sample of its claims blind (stage A), seal your answers, then open
the part and audit it against a fixed rubric (stage B). You change no finding, raise no question and fix nothing: you output a defect list and a verdict.

`W` = `projects/<id>/work`, `PT` = `W/parts/<part>`, `R` = `PT/review/round-<n>/` (the orchestrator gives id, part, round, seed and prompts). SKILL.md § Seen,
unread, absent and § Blocked text bind you too. Commands: [tools.md](tools.md) § Reading, § Linework; stages and receipts: [part-mode.md](part-mode.md).

## Stage A: blind re-derivation

**Open only**: `harness list-sheets`, `sheet-text`, `find-text`, `unassigned-clusters`, `dimensions`, `inventory.json`, `read-log.json`, `geometry`,
`contents` and `render` (read-only: never `--save`; `render` with `--out-dir R/renders`; to check counts and sizes), `marks.json`, `callouts.json`,
`grid-systems.json`, `structure/`, `answers.json`.
**Leave closed until stage B**: `reader-findings.json`, `reader-questions.json`, `reading-record.md`, `question-registry.json`, `reader-supplements.json`,
every file under `W/parts/` (`manifest.json`, `values.json`, `notes.md`, `receipts.json`, any earlier round), `harness status`, `harness finding list`,
`P/questions.md`, `P/01-analysis.md`.

Answer every prompt in `R/blind-answers.md`, one row each: `prompt | answer (verbatim values) | entries (ids) | state (seen | unread | absent + search record)
| confidence | minutes`. A prompt you cannot settle is answered `cannot determine` with what you searched. Stay within the prompts. *Done when* every prompt
has a row: run `sha256sum R/blind-answers.md` and keep the hash. The file is sealed: never edited again.

### Sample

The prompts come from `harness part review-sample W --part <part> --seed <n> [--n <k>]` (tools.md § Part mode; the orchestrator picks the seed once the part
is `checked`): value prompts from the part's rows (mark and field, never the value), one `absent` prompt and one outside-the-frame prompt when the part has
them. A prompt may hold no sheet number or view (they would give the value away): find the place by its `file` and `sheet`. The orchestrator adds by hand,
with no value from the reading or an earlier review in any prompt:

1. **Rows** (without the command): eight rows of `PT/values.json` by seed (one per listed field first): "Sheet `<number>`, view `<heading>`: what `<field>`
   does the drawing give for `<mark>`? Cite the entry ids."; one `absent` row; one cluster outside every frame of the part.
2. **`all-assembly`**: K1–K14 word for word from reading-method.md § Phase 5, always all fourteen.
3. **Round 2**: a new seed, plus one prompt per defect of the round before, its place and field only.

## Stage B: open audit

Write `R/review.md`. Its first line is the sha256 of the sealed answers. Now open the part.
**B1. Compare** each stage A row with the part's claim on the same subject:

| Outcome | Meaning | Next |
|---|---|---|
| `agree` | same value, or both `unread`, or both ask | — |
| `differ` | two different values | recheck both against the entries; the one the entries do not support is the defect (yours counts too: record it as `reviewer error`) |
| `reader only` | the reader claims, you could not determine | check the reader's entries: support the claim → `agree`; do not → defect |
| `reviewer only` | you found it, the reader has no claim and no question | defect: missed |
| `asked` | the reader asks, you found a value on two sources | Minor defect: asked what the drawing answers |

**B2. Audit** the part against every rule. `harness part check W --part <part>` exit 0 is the entry condition (receipt `checked` on the current hash, see
`harness status`): you record "by tool" with the code names, not redo it. Samples are minimums; a failed sample grows to the whole population for that rule.

| R | Rule | Checked by `part check` | You check (sample) |
|---|---|---|---|
| R1 | Evidence holds: each cited entry exists, is allowed, prints, is on the cited sheet and says what the claim says | `cite_unknown`, `cite_inactive`, `cite_stale`, `entry_blocked`, `entry_not_printed`, `entry_outside_part`, `number_unbacked`, `token_unbacked`, `value_not_verbatim` | the entry says what the claim says: `sheet-text --contains` on its text; a `measured` finding: `finding list` and a rerun of `geometry`/`contents`/`render` without `--save` for its count or size (20 findings spread over kinds, or all) |
| R2 | Every `absent` carries a search record, and its search still returns 0 hits with `blocked_in_scope` 0 | `search_unaccented`, `row_state` (a record exists) | rerun each search in every spelling (all) |
| R3 | No meaning from blocked text anywhere in findings, questions, rows, notes, the hand-back | `entry_blocked` (a blocked entry cited) | each quoted entry's `meaning`; each topic word of a question or note traced to an allowed entry (all blocked sheets of the part's manifest row) |
| R4 | The done-when of the part is true | receipt `checked`; `row_state`, `hand_sum_mismatch` | rerun the commands behind two `count_*` rows at index `seed % n` and `(seed + 3) % n` and compare (2 rows) |
| R5 | Coverage is whole: every sheet of the part has a row or a finding; every mark has a row with a size cell (entries or a question) | `sheet_uncovered`, `mark_missing`, `row_outside_part` | each size cell against its entries (all). `all-assembly` also: no Breakdown node `titled` **in the Breakdown table** (a card's words do not count) |
| R6 | Claim form: every finding except `note_item` has `node`, `basis`, `alt`; every `low` and every `single_source` has a question about its value; a `measured` finding is exempt from a per-value question; a listed value from linework alone needs its family's confirmation question (tools.md § Measured findings) | `claim_form`, `note_item_prefix`, `low_without_question`, `family_linework_twice`, `family_linework_needless` | `finding list`: a `measured` basis is honest (all) |
| R7 | Questions: Vietnamese, one subject each, `found` verbatim or a search record, a place to look, no duplicate of a producer's question; blocking exactly as SKILL.md § Asking defines it (the listed values and every question a rule names blocking) | `listed_needs_blocking`, `listed_question_not_blocking` | wording, language, one subject, `found`, place, duplicates (all blocking, all on listed values, 10 others) |
| R8 | `all-assembly` only. K1–K14 complete; every `claimed` line names a ruled-out alternative that the cited entry or check does rule out | — | the K lines of `W/parts/all-assembly/notes.md` (all) |
| R9 | The part's C-checks (reading-method.md § Phase 6: C2–C10 per part) each have a line in `PT/notes.md`; every mismatch has a `cross_check` finding and a question; `not run` names a reason; a hand sum shows its addends | `hand_sum_invalid`, `hand_sum_mismatch`, `cite_foreign_part` | the C lines of `PT/notes.md`; redo one check by hand. `all-assembly`: C1, C11, C12 per block, redo C11 and C12 for one block (all) |
| R10 | No unverified convention used as a rule: a mark's role without an answer, an edition mapped, a grade equated, a pinned or fixed base decided from a detail, a level called finished or structural without the word | — | findings and rows against conventions.md and steel-industrial.md (all `structural_system` findings and all role cells) |
| R11 | Text outside every frame was assigned before any `no rows`, `schedule unread` or `absent`; no `absent` on a sheet whose continuation sits in a cluster | `entry_outside_part`; `part manifest-check` `cluster_uncovered` (every cluster belongs to a part) | `sheet-text --unassigned` and `find-text --unassigned` for every `absent` or `unread` row (all such rows) |

## Manifest review (stage 1b, part `scout`)

`R` = `W/parts/scout/review/round-<n>/`; `review-sample` gives no prompts. **Stage A, blind:** open `list-sheets`, title-block `sheet-text`,
`unassigned-clusters`, `grid-systems.json`, `structure/` and saved phase 0 `geometry` documents (tools.md § Linework); keep `manifest.json`, `reading-record.md`
and the scout's findings and questions closed. In `R/blind-answers.md` write one row per sheet (`file | sheet | block | part kind and family | evidence: entry
ids, grid origin, number series`) and per cluster (`cluster | sheet it continues or none | evidence`); seal it with `sha256sum`. **Stage B:** open the manifest,
run `harness part manifest-check W`; record one defect per sheet or cluster placed in another block or part than yours, part merged where the cap asks for a
split, member part whose `inputs` lack a part below it on the load path, and acked warning or doubtful placement whose question is missing or not in that part's
`producer_questions`; a member or cross part whose `producer_questions` lacks the `reader_breakdown_confirm` id. A sheet in the wrong block is Critical; the rest as § Defects. Verdict as § Verdict, agreement = sheets placed alike ÷ sheets.

## Defects

One row per defect in `R/review.md`: `id (D-<round>-<nn>) | severity | class | phase | where (finding, question or row id, sheet) | reader wrote | entries
show (ids) | expected | layer`.

- **Critical**: a wrong value a model would be built from (block count, grid, level, system, grade, size, count, units evidence); meaning taken from blocked
  text; an `absent` whose search hits; a value with no evidence and no question; a count no command reproduces.
- **Major**: a key claim missing or without a ruled-out alternative; a scope gap nobody asked (a load-path link with no sheet, a listed sheet not in the
  files); an unresolved reference not asked; evidence that does not support a claim whose value is still right; a `titled` node in the table; a `low` or
  `single_source` finding (not `measured`) without a value question; a listed value from linework alone with no blocking family confirmation question; rule
  R10 broken; a question on a value listed in SKILL.md § Asking raised non-blocking; a family with no size and no question; no C11 or C12 row for a block; a
  schedule or table called empty while its rows sit outside the frame; a search that ran over `projects/` outside the project folder.
- **Minor**: wording, duplicate questions, a missing note field with no consequence, `asked`.
- **Class** (one, improvement-loop.md § Classes) and **layer** (`tool | skill | knowledge | input | reader slip`): your best reading of the cause.

## Verdict

Last section of `R/review.md`: counts by severity, the blind agreement (`agree` ÷ prompts; K1–K14 and the sample given separately for `all-assembly`), and one
verdict: `pass` (no Critical, no Major, sample agreement ≥ 95 %; `all-assembly` also K1–K14 all `agree` or `asked`); `fix` (anything else in round 1: the
reader gets the defect list, not your blind answers); `engineer` (round 2 or a later round still fails: the engineer rules in chat; if he accepts, the orchestrator writes
`review/round-3/review.md` with his words verbatim and records `--round 3 --verdict pass`; if he asks for fixes, a narrow round-3 review follows).

*Done when* every prompt has an outcome, every rule R1–R11 has a result line with its sample size (R8 only for `all-assembly`; for the manifest review, its Stage B defect kinds instead of R1–R11), every defect has all nine
fields, and the verdict is one of the three words. Report to the orchestrator: the part, the verdict, the counts, the Critical and Major defects, your `reviewer
error` count, and any rule you could not check, with the reason. The orchestrator records the verdict (`harness part receipt … --kind reviewed`, part-mode.md).
