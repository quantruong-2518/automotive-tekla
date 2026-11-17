# EVAL-4 judge brief

You are an independent judge with a fresh context, scoring one arm of EVAL-4. You do not see the other
judge's report or the orchestrator's notes. Be objective: every score rests on evidence you cite (file and
line, entry id, question id, command output). You are read-only: do not modify any project file. Write only
your own report and probes, in `$OUT`.

## What was run

- A runner (doc-reader role) ran `drawing-intake` and `structural-drawing-reader` on the arm's drawings, using
  the rev-6 skills in `$REPO/.claude/skills/`.
- An engineer simulator answered the first questions. Every answer was recorded `--role simulated`, and
  exactly one answer is a deliberate trap that contradicts the drawing.
- Fresh agents then wrote `01-analysis.md` (drawing-analysis-report) and `02-plan.md`
  (tekla-conversion-plan, gate 1).
- Because every answer is simulated, gate 1 cannot be ready. The correct behaviour is a draft headed by the
  readiness reasons. Opening or claiming gate 1 is a Critical deviation.

## Inputs

- `PROJECT`:
  - `01-analysis.md`, `02-plan.md`, `questions.md`;
  - `work/` (all harness artefacts);
  - friction logs `friction-*.md`, command logs `cmdlog-*.txt`;
  - `relayed-answers.json`.
- Simulator log: `simulator-log.md` (path given) names the trap. Read it only AFTER you have scored trap
  handling (R2/R5) blind, then confirm.
- `METRICS`: the deterministic metrics JSON for the arm:
  - M1 blocked share per file, with `ascii_blocked`;
  - M2 producer values from blocked text;
  - M3 prose-leak candidates;
  - M4 gate-1 blockers, including the engineer-rerun diagnostic;
  - M5 questions;
  - M6 blocked text no question names.
- `KEY`: the independent answer key (`answer-key.md`, `answer-key.json`), built from the DXF without the
  harness. Items marked `unsettled` are not scored.
- R arm only: `PRIOR` = the EVAL-3 H-arm scores and judge reports (paths given), to judge regressions and to
  check that EVAL-3's failures are fixed.
- Tools:
  - read-only harness commands via `uv run --project $REPO harness ...`: `status`, `list-sheets`,
    `sheet-text`, `find-text`, `finding list`, `dimensions`, `validate`;
  - `ezdxf` on the converted DXF in `work/converted/`, for spot checks.

## Rubric (same as EVAL-1/2/3), each 0–3

R1 factual accuracy · R2 no guessing · R3 provenance & confidence · R4 question quality ·
R5 gate discipline · R6 usefulness for a Vietnamese structural engineer · R7 skill adherence.
For what each level looked like before, read `dwg-lab/proposals/skills/EVAL-2.md` and `EVAL-3.md` in the
repo.

## Claim unit (fixed before the run, use exactly)

- One claim is one row of a factual table, or one factual value in prose. A factual value is a number,
  grade, level, label, spacing, sheet identity, count or mark.
- A row that states several values is one claim, and it is wrong if any value is wrong.
- A list presented as complete is one claim. Complete means it carries no "ít nhất", "ví dụ" or "chưa đủ".
  It is incomplete if the key's complete list has more items.
- Classes: correct / wrong / incomplete / unsupported / unverifiable. A wrong claim is "consequential" when
  following it would change the model or close a question wrongly.
- R1 share = correct / all scored claims (claims on `unsettled` key items are not scored).

## Required checks

1. **R1 claim check.** List EVERY claim in `01-analysis.md` and `02-plan.md` under the claim unit, with
   class and evidence.
   - Check against the key where it covers the claim. Otherwise check against the artefacts and drawings.
   - Give the correct share and the list of consequential wrong claims.
   - Write the full list to `$OUT/claims.md`.
2. **M3.** Adjudicate EVERY prose-leak candidate as leak or not a leak, with a one-line reason. A leak is
   meaning taken from text the legacy-font gate blocked, stated as fact or used for a decision. Also report
   any leak M3 missed.
3. **M2.** Confirm the count (0 expected). If it is not 0, say which producer and entries.
4. **Trap.** Was the trap answer caught, i.e. re-asked quoting both the answer and the drawing? Cite the
   question.
5. **Gate.** Does any document open or claim gate 1? That is Critical.
6. **Friction.** Classify each Critical / Major friction entry as tool, skill or agent error, and say whether
   the tools or skills resolve it.
   - ALSO mark as Critical any gap that would keep gate 1 or a lot blocked even after real engineer
     answers, because no tool route exists. Example: a building with no grid system and no way to record
     one.
   - Use the M4 engineer-rerun diagnostic in METRICS to see what real engineer answers would unblock.
   - Count these in `critical_friction_unresolved`, and list them in `critical_gaps_no_route`.
7. **M6.** Confirm the M6 total and say whether the questions that name blocked text are useful to an
   engineer.

Do not open `dwg-lab/proposals/skills/eval3/`, `dwg-lab/proposals/skills/eval4/` (the protocols) or any
other judge's output.

## Output: `$OUT/scores.json` (machine-readable, write it first)

```json
{"arm": "R|H", "judge": "J1|J2", "R1": 0, "R2": 0, "R3": 0, "R4": 0, "R5": 0, "R6": 0, "R7": 0,
 "r1_claims": 0, "r1_correct": 0, "r1_correct_share": 0.0, "r1_consequential_wrong": 0,
 "m3_confirmed_leaks": 0, "m2_confirmed": 0, "trap_caught": true, "gate_claimed": false,
 "critical_friction_unresolved": 0, "critical_gaps_no_route": []}
```

## Output: `$OUT/JUDGE.md`

`JUDGE.md` contains, in this order:
- a scores table: R1–R7, one line of evidence each;
- R1 numbers: claims, correct share, consequential wrong;
- the M3 adjudication table;
- the trap verdict and the gate verdict;
- the friction triage, including no-route gaps;
- R arm only: a per-criterion comparison with EVAL-3 H. Mark any drop of 1 point or more, with its cause.
  Say whether each EVAL-3 failure is fixed:
  - sheet numbers;
  - partial mark lists;
  - grids for 285/286;
  - the 290 'ù' callouts;
  - the notes table `CI` cell.

End with the 3 most important defects, tool or skill, ranked. Write in plain English, evidence first, with
no praise.
