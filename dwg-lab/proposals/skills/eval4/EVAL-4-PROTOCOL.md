# EVAL-4 protocol — pre-registered 2026-11-09, before any tool-wave-3 code landed

This file is committed before the run, together with the held-out set's SOURCE.md and the answer key's
sha256, and before the first tool-wave-3 code commit. It is not edited after the first eval output exists.
Any deviation during the run goes into the EVAL-4 report under "Deviations", with its reason. The pass
bar below is never changed after the fact, and it is never easier than EVAL-3's.

## 1. Question

After tool wave 3 (the EVAL-3 fixes), are the drawing-reading tools and skills good enough for a supervised,
read-only shadow pilot on a real MCS project?

## 2. Arms

| Arm | Project id | Drawings | Purpose |
|---|---|---|---|
| R (regression) | `eval4-r` | dwgshare 285, 286, 290; dwgshare 161 (EVAL-3's held-out set) | the EVAL-3 failures are fixed; no criterion drops against EVAL-3 H |
| H (held-out) | `eval4-h` | dwgshare 264, 271, 278; dwgshare 180 steel (`dwg-lab/samples/L3-complex/eval4-heldout/`, SOURCE.md) | the pass/fail decision |
| M (metrics only) | `eval4-m` | dwgshare 267, 433; structuralbd Complete_Steel_01 (the EVAL-1/2/3 R set) | deterministic regression check, no judges: intake + read-structure + grid-system + callouts + marks, then `metrics.py` |

Held-out rule: nobody working on the tools or skills reads the H drawings, their text, or their style
tables. The only looks so far are the post titles, the files' header magic and sha256, and the style-table
font counts in SOURCE.md (download agent, for set selection). Every implementation brief forbids the folder.
The R drawings are known material from now on (wave 3 is built against EVAL-3's findings on them).

## 3. Frozen inputs (recorded in the report before the first run)

- Harness commit sha and branch; `knowledge/font-encodings.csv` sha256. Skill revision under test: rev 6 if
  the engineer approved it before the run, otherwise rev 6 in a scratch repo copy, marked "approval
  SIMULATED".
- Converter: LibreDWG 0.14 (`dwg-lab/tools/libredwg`). ODA is not available.
- Answer key sha256 (§5), recorded in this protocol's commit message and in `eval4/key-sha256.txt` of the
  orchestrator's scratchpad.
- Input drawings' sha256 per arm.

## 4. Deterministic metrics (`metrics.py` in this folder, same commit as this file)

Run `uv run python dwg-lab/proposals/skills/eval4/metrics.py <project-dir> --background-repo <repo copy>`
from inside the scratch repo copy, on each arm after the run.

| Id | Metric | Definition |
|---|---|---|
| M1 | blocked share | per drawing file: non-ASCII entries blocked by the legacy-font gate / all non-ASCII entries; `ascii_blocked` reported per file |
| M2 | producer values from blocked text | entry ids cited by levels, grids, callouts and marks outside their `blocked*` lists that are blocked |
| M3 | prose leak candidates | 3-word runs decoded from blocked entries, found in `01-analysis.md` / `02-plan.md`, absent from allowed text and from the background vocabulary of the repo copy; judges adjudicate each |
| M4 | gate-1 blockers | `M4_status` (as `harness status` counts) and `M4_status_if_engineer` (simulated answers relabelled engineer on a temporary copy); `M4_criterion5_share` = the larger procedural share; unclassified counts as procedural. Wave-3 codes `grid_system_missing`, `grid_answer_contradicts_drawing`, `sheet_number_gap`, `callout_unparsed`, `legacy_ascii_text` are classed content. Diagnostic for criterion 7: `M4_engineer_rerun_diagnostic` reruns `grid-system` on the relabelled copy and lists files that gain a grid system with `source: engineer_answer` |
| M5 | questions | registry counts by status, producer and code |
| M6 | unnamed blocked text | entries blocked by the legacy-font gate whose file has no live (non-obsolete) registry question with a code covering the block reason. The map is frozen in `metrics.py` (`M6_COVERING_CODES`): encoding reasons → `font_encoding_proposed`, `font_encoding_conflict`, `text_encoding_hint`, `encoding_unknown_non_ascii`; `legacy_ascii_suspect` → `legacy_ascii_text`. Computed from the text index and the registry, never from a harness reader |

Dry run on the archived EVAL-3 outputs (2026-11-09, to validate the script, not a result): M6 = 786 on
eval3-r (all `legacy_ascii_suspect` in 267) and 0 on eval3-h; the engineer-rerun diagnostic ran (exit 0, no
engineer grids, as expected before wave 3).

## 5. Answer key (H arm)

- One fresh Opus agent, not a runner and not a judge, builds `answer-key.json` + `answer-key.md` from the
  converted DXF with raw `ezdxf` and its own decoding. It may not import `tekla_harness` or read any harness
  output, so key errors and tool errors do not share a cause. It may reuse the EVAL-3 key scripts, which are
  independent of the harness.
- Content per file: units; sheets (frames, printed numbers, titles); grid systems (labels, order, spacings);
  storey and local levels (and what ties a level to a floor); general notes (grades, cover, codes); member
  marks on plans and in schedules or detail headings, as complete lists with a completeness flag; rebar
  callout forms; internal conflicts of the drawing. Every item carries source handles and confidence.
- Items the key agent cannot settle are `unsettled` and are excluded from R1 scoring.
- The key is unreadable (chmod 000) while runners, report writers and planners run. It is readable for the
  H simulator and the judges, and its sha256 is re-checked before judging.
- R arm: the EVAL-3 key (archived, `projects/_evals/eval3-2026-11-09/eval3/key/`, sha256 as in EVAL-3.md)
  plays the same role.

## 6. Run procedure (arms R and H in parallel, sequential inside an arm)

1. Runner: one fresh general-purpose Opus agent taking the `doc-reader` role file from the scratch repo
   copy, reading the rev-6 SKILL.md files there (never the Skill tool, which may load another revision).
   Runs `drawing-intake`, then `structural-drawing-reader` steps 1–2, and stops at the units hard stop.
2. Engineer simulator: a separate Opus agent answers from the key (H: EVAL-4 key; R: EVAL-3 key). Exactly one
   answer per arm is a trap that contradicts the drawing: H, a storey level 300 mm off the key; R, the
   EVAL-3 trap (285 storey 3 = +8.250, drawing +7.950). The trap goes into the simulator's log first. Answers
   that say "not enough information, keep open" are not relayed.
3. Before relay, the orchestrator runs `relay.py` (this folder), which keeps only `question_id`, `code`,
   `text` and `values` of the simulator's answers (no `basis`, no `trap`). The simulator's log stays outside the
   project folder. The same runner then records the answers (`--role simulated`) and runs reader steps
   3–7. If that runner is unavailable, a fresh runner takes over from the state on disk; this is recorded
   as a deviation.
4. A fresh report writer writes `01-analysis.md` (`drawing-analysis-report`).
5. A fresh planner writes `02-plan.md` (`tekla-conversion-plan`, gate 1). Every answer is simulated, so gate
   1 cannot be ready. The correct behaviour is a draft headed by the readiness reasons; opening or claiming
   gate 1 is a Critical deviation.
6. Every agent keeps a friction log (Critical / Major / Minor, with the skill line it concerns) and a command
   log. Runners, report writers and planners may not open `EVAL-*.md`, `REVIEW-*.md`,
   `dwg-lab/proposals/skills/eval*/`, any key, another arm, or any judge file.
7. Arm M: one agent runs the producers listed in §2 with no answers, then `metrics.py`. No judges.
8. After judging, the orchestrator copies the whole eval folder (without the repo copy) to the git-ignored
   `projects/_evals/eval4-<date>/` before writing the report.

Briefs (`briefs/RUNNER.md`, `SIMULATOR.md`, `REPORT-PLAN.md`, `JUDGE.md`) and `setup.sh` in this folder are
part of this protocol and are frozen with it.

## 7. Judging

- Two independent Opus judges per judged arm (four in all), each in a fresh context, with the brief, the
  rubric (R1–R7, 0–3), read-only harness tools, the arm's outputs, the metrics JSON, the key, and (R arm)
  the EVAL-3 H scores and judge reports from the archive. They never see this protocol, each other's
  report, or the orchestrator's notes.
- **Claim unit (new).** One claim = one table row of a factual table, or one factual value in prose (a
  number, grade, level, label, spacing, sheet identity, count or mark). A row that states several values
  is one claim and is wrong if any value is wrong. A list presented as complete (no "ít nhất", "ví dụ" or
  "chưa đủ") is one claim and is incomplete if the key's complete list has more items.
- R1 classes: correct / wrong / incomplete / unsupported / unverifiable; a wrong claim is "consequential"
  when following it would change the model or close a question wrongly. R1 share = correct / all scored
  claims.
- Each judge adjudicates every M3 candidate and reports any leak M3 missed.
- **Friction severity (new).** Besides the agents' own labels, the judge marks as Critical any gap that
  would keep gate 1 or a lot blocked even after real engineer answers, because no tool route exists (e.g.
  a building with no grid system and no way to record one). Such gaps count in criterion 7.
- Disagreement: a criterion where J1 and J2 differ by >= 2 points, or an R1 share that differs by more than
  5 points, goes to a third Opus judge (J3), who rules on that item only. Final score = mean of J1 and J2,
  or J3's ruling where invoked.

## 8. Pass bar (EVAL-3 bar with its amendments; criterion 8 new)

The H arm passes when ALL hold:

1. R1 >= 95 % correct claims (mean of the judges' shares over the H arm), with no consequential wrong claim.
2. M2 = 0 (no producer value from blocked text).
3. M3 confirmed leaks = 0 (no prose leak).
4. M1 < 30 % on EVERY TCVN3/VNI file with >= 100 non-ASCII entries (per file, not pooled).
5. `M4_criterion5_share` < 50 % on the arm.
6. The trap answer is caught: re-asked quoting both the answer and the drawing.
7. No Critical friction left unresolved by the tools or skills, counting the judges' §7 Critical gaps.
8. M6 = 0 on the arm: every blocked entry is named by a live question of its file whose code covers its
   block reason.

R arm: no criterion's final score is lower than EVAL-3 H's by >= 1 point. Also R1 >= 95 %, and criteria
2, 3, 6, 7 and 8 hold. A failure here does not fail the eval on its own; it is listed with its cause and
must be fixed before the pilot.
M arm: M2 = 0, M6 = 0, and M1 per file no higher than in EVAL-3 (267 0.91 %, 433 0 %).

Verdict:
- **PASS** when criteria 1–8 hold and the R and M arms hold → supervised read-only shadow pilot.
- **PASS WITH CONDITIONS** when criteria 1–4 hold but criteria 5–8, the R arm or the M arm fail → pilot
  after the named fixes.
- **FAIL** when any of criteria 1–4 fails → another tool wave.

## 9. Limits stated up front

- One run per arm; run-to-run variance is not measured.
- All engineer answers are simulated, and the keys are agents' readings, not an engineer's.
- LibreDWG, not ODA: conversion artefacts may differ on the pilot.
- The H set is 3 Vietnamese RC houses from one site plus one steel set. It is not the MCS project mix.
- The R arm is now known material: its scores show the fixes landed, not that the tools generalise.
