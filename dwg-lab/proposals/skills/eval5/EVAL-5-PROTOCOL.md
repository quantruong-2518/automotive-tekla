# EVAL-5 protocol — pre-registered 2026-11-10, before any tool-wave-4 code landed

This file is committed before the run, together with the held-out set's SOURCE.md and the answer key's
sha256, and before the first tool-wave-4 code commit. It is not edited after the first eval output exists.
Any deviation during the run goes into the EVAL-5 report under "Deviations", with its reason. The pass
bar below is never changed after the fact, and it is never easier than EVAL-4's.

Base: `eval4/EVAL-4-PROTOCOL.md`. What changed is listed in §10.

## 1. Question

After tool wave 4 (the EVAL-4 fixes) and the rev-7 skills, are the drawing-reading tools and skills good
enough for a supervised, read-only shadow pilot on a real MCS project?

## 2. Arms

| Arm | Project id | Drawings | Purpose |
|---|---|---|---|
| R (regression) | `eval5-r` | dwgshare 264, 271, 278; dwgshare 180 steel (EVAL-4's held-out set, `eval4-heldout/`) | the EVAL-4 failures are fixed; no criterion drops against EVAL-4 H |
| H (held-out) | `eval5-h` | dwgshare 297, 281, 447; dwgshare 442 steel (`dwg-lab/samples/L3-complex/eval5-heldout/`, SOURCE.md) | the pass/fail decision |
| M (metrics only) | `eval5-m` | dwgshare 267, 433; structuralbd Complete_Steel_01 | deterministic regression check, no judges: intake + read-structure + grid-system + callouts + marks, then `metrics.py` |

Held-out rule: nobody working on the tools or skills reads the H drawings, their text, or their style
tables. The only looks so far are the post titles, the files' header magic, size and sha256, and the
style-table font counts in SOURCE.md (download agent, for set selection). The key agent reports back
only its item count, unsettled count and sha256, never content (the EVAL-4 orchestrator-exposure
lesson). Every implementation brief forbids the `eval5-heldout/` folder and the EVAL-5 key.
The R drawings are known material from now on: tool wave 4 is built against EVAL-4's findings on them,
and wave-4 briefs may open them.

## 3. Frozen inputs (recorded in the report before the first run)

- Harness commit sha and branch; `knowledge/font-encodings.csv` sha256. Skill revision under test: rev 7 if
  the engineer approved it before the run, otherwise rev 7 in a scratch repo copy, marked "approval
  SIMULATED".
- Converter: LibreDWG 0.14 (`dwg-lab/tools/libredwg`). ODA is not available.
- Answer key sha256 (§5), recorded in this protocol's commit message and in
  `projects/_evals/eval5-2026-11-10/key-sha256.txt`.
- Input drawings' sha256 per arm.

## 4. Deterministic metrics (`metrics.py` in this folder, same commit as this file)

Run `uv run python <main checkout>/dwg-lab/proposals/skills/eval5/metrics.py <project-dir> --background-repo
<repo copy>` with the scratch repo copy as the working directory, on each arm after the run (the repo copy
has no `eval5/` folder).

| Id | Metric | Definition |
|---|---|---|
| M1 | blocked share | per drawing file: non-ASCII entries blocked by the legacy-font gate / all non-ASCII entries; `ascii_blocked` reported per file |
| M2 | producer values from blocked text | entry ids cited by levels, grids, callouts and marks outside their `blocked*` lists that are blocked |
| M3 | prose leak candidates | 3-word runs decoded from blocked entries, found in `01-analysis.md` / `02-plan.md`, absent from allowed text and from the background vocabulary of the repo copy; judges adjudicate each |
| M4 | gate-1 blockers | `M4_status` (as `harness status` counts) and `M4_status_if_engineer` (simulated answers relabelled engineer on a temporary copy); `M4_criterion5_share` = the larger procedural share; unclassified counts as procedural. Content codes as in EVAL-4. Diagnostic for criterion 7: `M4_engineer_rerun_diagnostic` reruns `grid-system` on the relabelled copy and lists files that gain a grid system with `source: engineer_answer` (fixed for EVAL-5: the file is read from the system's `members` and from its directions' `provenance.file`) |
| M5 | questions | registry counts by status, producer and code |
| M6 | unnamed blocked text | entries blocked by the legacy-font gate whose file has no live (non-obsolete) registry question with a code covering the block reason (`M6_COVERING_CODES`, frozen in `metrics.py`) |

M2 stays as strict as in EVAL-4: a blocked entry id cited outside a `blocked*` list counts, whatever
`meaning` field sits next to it.

Dry run on the archived EVAL-4 H outputs (2026-11-10, to validate the fix, not a result): the
engineer-rerun diagnostic now lists `278_5-story_house_4.4x15.3m.dwg` (EVAL-4: `[]`); M2 5 and
`M4_criterion5_share` 0.2 are unchanged.

## 5. Answer key (H arm)

- One fresh Opus agent, not a runner and not a judge, builds `answer-key.json` + `answer-key.md` from the
  converted DXF with raw `ezdxf` and its own decoding. It may not import `tekla_harness` or read any harness
  output, so key errors and tool errors do not share a cause. It may reuse the EVAL-4 key scripts, which are
  independent of the harness.
- Content per file: units; sheets (frames, printed numbers, titles); grid systems (labels, order, spacings);
  storey and local levels (and what ties a level to a floor); general notes (grades, cover, codes); member
  marks on plans and in schedules or detail headings, as complete lists with a completeness flag; rebar
  callout forms; internal conflicts of the drawing. The key says, per fact, whether any text involved is
  hidden on the printed sheet, and takes no hidden text as printed content. Every item carries source
  handles and confidence.
- Items the key agent cannot settle are `unsettled` and are excluded from R1 scoring.
- The key is unreadable (chmod 000) while runners, report writers and planners run. It is readable for the
  H simulator and the judges, and its sha256 is re-checked before judging.
- R arm: the EVAL-4 key (archived, `projects/_evals/eval4-2026-11-09/key/`, answer-key.json 2431e2c8…542c,
  answer-key.md e3b93205…b83e) plays the same role.

## 6. Run procedure (arms R and H in parallel, sequential inside an arm)

As EVAL-4 §6, steps 1–8, with these additions:
- R-arm trap: the EVAL-4 trap (264 storey tầng 3 = +7.200; the drawing has +6.900). H-arm trap: one
  storey-level answer 300 mm off the key.
- Simulator output folders (`sim-r/`, `sim-h/`) sit outside the project folders and are chmod 000 except
  while their simulator or the judges run (EVAL-4 left them readable for 38 minutes).
- Runners, report writers and planners keep every helper file under `$PROJECT/tmp/`.
- Sync points: the simulators start only after both phase-A runners stop; the judges start only after
  both planners stop. No key is readable while a runner, writer or planner works.

Briefs (`briefs/RUNNER.md`, `SIMULATOR.md`, `REPORT-PLAN.md`, `JUDGE.md`) and `setup.sh` in this folder are
part of this protocol and are frozen with it.

## 7. Judging

As EVAL-4 §7: two independent Opus judges per judged arm, the same claim unit, R1 classes, M3
adjudication, friction severity (no-route gaps are Critical) and J3 trigger (a criterion where J1 and J2
differ by >= 2 points, or an R1 share that differs by more than 5 points). R-arm judges get the EVAL-4
H-arm scores and judge reports as their prior.

Made explicit (it is how EVAL-4 was applied): a consequential wrong claim, and a no-route Critical gap,
count for the pass bar when either judge names it and no J3 ruled on it.

## 8. Pass bar (EVAL-4 bar, unchanged)

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

R arm: no criterion's final score is lower than EVAL-4 H's (R1 1.5, R2 3, R3 3, R4 2, R5 3, R6 2, R7 2)
by >= 1 point. Also R1 >= 95 %, and criteria 2, 3, 6, 7 and 8 hold. A failure here does not fail the eval on
its own; it is listed with its cause and must be fixed before the pilot.
M arm: M2 = 0, M6 = 0, and M1 per file no higher than in EVAL-4 (267 0.91 %, 433 0 %).

Verdict:
- **PASS** when criteria 1–8 hold and the R and M arms hold → supervised read-only shadow pilot.
- **PASS WITH CONDITIONS** when criteria 1–4 hold but criteria 5–8, the R arm or the M arm fail → pilot
  after the named fixes.
- **FAIL** when any of criteria 1–4 fails → another tool wave.

## 9. Limits stated up front

- One run per arm; run-to-run variance is not measured.
- All engineer answers are simulated, and the keys are agents' readings, not an engineer's.
- LibreDWG, not ODA: conversion artefacts may differ on the pilot.
- The H set is 3 Vietnamese RC sets (two houses, one multistorey building) plus one steel set, all from
  dwgshare. It is not the MCS project mix.
- The R arm is known material: its scores show the wave-4 fixes landed, not that the tools generalise.
- Criterion 7 counts build-side no-route gaps (no grid or level object and linear members only in the lot
  spec, research §11 R1/R8). Both EVAL-4 J2 judges named them. Unless the engineer decides on those routes
  before the run, criterion 7 is expected to fail, which caps the verdict at PASS WITH CONDITIONS.

## 10. Changes from EVAL-4

- Arms: R = EVAL-4 H set with the EVAL-4 key and trap; H = the new `eval5-heldout/` set.
- Skills under test: rev 7.
- `metrics.py`: the engineer-rerun diagnostic reads an answer-built system's file from its directions
  (EVAL-4 under-reported it as `[]`). No pass-bar metric changed.
- Briefs: forbid `eval4/` and `eval5/` folders and keys; the R-arm prior is EVAL-4 H; the judges check the
  EVAL-4 failures.
- §6: simulator folders locked outside their use; helper files under `$PROJECT/tmp/`.
- §7: "either judge" rule made explicit for consequential claims and no-route gaps.
