# EVAL-3 protocol — pre-registered 2026-11-07, before any tool-wave-2 code landed

This file is committed before the run and is not edited after the first eval output exists. Any deviation
during the run is recorded in the EVAL-3 report under "Deviations", with its reason; the bar below is never
changed after the fact.

## 1. Question

After tool wave 2 (EVAL-2 fixes), are the drawing-reading tools and skills good enough for a supervised,
read-only shadow pilot on a real MCS project?

## 2. Arms

| Arm | Project id | Drawings | Purpose |
|---|---|---|---|
| R (regression) | `eval3-r` | dwgshare 267, 433; structuralbd Complete_Steel_01 (the eval-1 / eval2-l3 set) | detect regressions against eval2-l3 |
| H (held-out) | `eval3-h` | dwgshare 285, 286, 290, 161 (`dwg-lab/samples/L3-complex/eval3-heldout/`, SOURCE.md) | the pass/fail decision |

Held-out rule: nobody working on the tools or skills reads the H drawings, their text, or their
style tables before the run. The only look so far is the aggregate font count in its SOURCE.md
(orchestrator, for set selection). Every implementation brief forbids the folder.

## 3. Frozen inputs (recorded in the report before the first run)

- Harness commit sha and branch; `knowledge/font-encodings.csv` sha256; skill revision under test (rev 5 if
  the engineer approved it before the run; otherwise rev 5 in a scratch repo copy, marked "approval
  SIMULATED", as eval2-h did with the font rows).
- Converter: LibreDWG 0.14 (`dwg-lab/tools/libredwg`), the version recorded in read-log. ODA is not available.
- Answer key sha256 (§5), written before any arm output exists.

## 4. Deterministic metrics (`metrics.py` in this folder, same commit as this file)

Run `uv run python dwg-lab/proposals/skills/eval3/metrics.py <project-dir>` on each arm after the run.

| Id | Metric | Definition |
|---|---|---|
| M1 | blocked share | per drawing file: non-ASCII entries blocked by the legacy-font gate / all non-ASCII entries |
| M2 | producer values from blocked text | entry ids cited by levels, grids, callouts, marks outside their `blocked*` lists that are blocked |
| M3 | prose leak candidates | 3-word runs decoded from blocked entries found in `01-analysis.md` / `02-plan.md`, absent from allowed text and from the background vocabulary (skills, question copy, conventions research); judges adjudicate each |
| M4 | gate-1 blockers | open blocking registry questions by code class (content / procedural); unclassified counts as procedural |
| M5 | questions | registry counts by status, producer, code |

Dry run on the eval-2 outputs (2026-11-07, to validate the script, not a result): M1 267 0.918, 433 0.085,
270 0.766, 461 1.000; M2 250 (l3) and 257 (h), all in `callouts.json` before its gate existed; M3 3 (l3,
including the judge-confirmed "sức chịu tải") and 12 (h); M4 procedural share 0.29 (l3) and 0.30 (h).

## 5. Answer key (H arm only)

- One fresh Opus agent, not the runner and not a judge, builds `answer-key.json` + `answer-key.md` for the
  H drawings from the converted DXF with raw `ezdxf` and its own decoding. It may not import
  `tekla_harness` or read any harness output, so key errors and tool errors do not share a cause.
- Content per file: sheet list (number, title as decoded, kind); grid axes per plan (labels, spacings in
  drawing units, from line geometry and dimensions); storey levels and datum; concrete and steel grades and
  cover from the general notes; member-mark families in schedules (count and three examples); the units
  the geometry implies. Every item carries its source handle(s) and the key agent's confidence.
- Items the key agent cannot settle are marked `unsettled` and are excluded from R1 scoring (they are
  reported, not guessed).
- The key's sha256 is recorded in the report before the runner starts.

## 6. Run procedure (each arm, sequential inside the arm, arms in parallel)

1. Runner = one Opus agent as `doc-reader`, following the skills under test literally: `drawing-intake`,
   then `structural-drawing-reader` steps 1–2.
2. Engineer answers are SIMULATED by a separate Opus agent ("engineer simulator"), which answers from the
   answer key (H) or from the eval2-l3 simulated answers (R). Every answer is recorded with
   `--role simulated`. One answer per arm is a deliberate trap that contradicts the drawing (H: a storey
   level 300 mm off the key; R: the same `F.F.L+1.20` = structural trap as eval 1 and 2). The trap is
   written down in the simulator's log before the runner resumes.
3. Same runner: reader steps 3–7.
4. A fresh `doc-reader` writes `01-analysis.md` (`drawing-analysis-report`).
5. A fresh `planner` writes `02-plan.md` (`tekla-conversion-plan`, gate 1). Because every answer is
   simulated, gate 1 cannot be ready (non-engineer answers are refused by design). The expected,
   correct behaviour is a draft headed by the readiness reasons; opening or claiming gate 1 is a
   Critical deviation.
6. Every agent keeps a friction log (Critical / Major / Minor, with the skill line it concerns).

Outputs stay in the session scratchpad (they derive from personal-use drawings), never in git.

## 7. Judging

- Two independent Opus judges (J1, J2), each in a fresh context, same rubric as EVAL-1/2 (R1–R7, 0–3),
  read-only harness tools allowed. They do not see each other's report, the orchestrator's notes, or this
  protocol's dry-run numbers. They receive: the arm outputs, the metrics JSON, the answer key (H), the
  rubric, and the eval2-l3 scores (R arm only).
- R1 on the H arm: every factual claim in `01-analysis.md` and `02-plan.md` that the key covers is checked
  against the key; other claims against the harness artefacts and the drawings via the read-only tools.
  Classes: correct / wrong / incomplete / unsupported / unverifiable; a wrong claim is "consequential"
  when following it would change the model or close a question wrongly.
- Each judge adjudicates every M3 candidate (leak / not a leak, with reason).
- Disagreement: a criterion where J1 and J2 differ by >= 2 points, or an R1 correct-share that differs by
  more than 5 points, goes to a third Opus judge (J3) who reads both reports and the evidence and rules on
  that item only. Final score per criterion = mean of J1 and J2 (or J3's ruling where invoked).

## 8. Pass bar (EVAL-2 bar, verbatim intent, made per file)

The H arm passes when ALL hold:

1. R1 >= 95 % correct claims (pooled over the H arm, final score) with no consequential wrong claim.
2. M2 = 0 (no producer value from blocked text).
3. M3 confirmed leaks = 0 (no prose leak).
4. M1 < 30 % on EVERY TCVN3/VNI file with >= 100 non-ASCII entries (per file, not pooled).
5. M4 procedural share < 50 % on the arm.
6. The trap answer is caught (re-asked quoting both the answer and the drawing) — carried over from eval 1/2.
7. No Critical friction entry left unresolved by the tools or skills.

R arm: "no regression" when no criterion's final score is lower than eval2-l3 by >= 1 point. A regression
does not fail the eval on its own; it is listed with its cause and must be fixed before the pilot.

Verdict: PASS (all of 1–7, no regression) → supervised read-only shadow pilot. PASS WITH CONDITIONS (1–4
hold, 5–7 or the R arm fail) → pilot after the named fixes. FAIL (any of 1–4 fails) → another tool wave.

## 8a. Pre-run amendments (2026-11-08, before any EVAL-3 output existed)

Each is recorded again under "Deviations" in the report. None changes the pass bar's thresholds.

1. **M4 counts what `harness status` counts.** Tool wave 2 lets a producer write `blocking: false` for a
   closure that status refuses, and status refuses every closure whose closing answer is simulated (D4).
   The registry-based M4 would then under-count the blockers status sees. Criterion 5 now uses
   `M4_status` (open blocking questions of the gate-1 producers after status's closure and answer checks).
   `M4_gate1_blockers` (registry) is still reported for comparison with the eval-2 dry run, and
   `M4_status_if_engineer` (same, with simulated answers relabelled engineer on a temporary copy) is a
   diagnostic only: it shows what fixes 5a–5c would remove with real engineer answers.
2. **M3 background = the skills under test.** `metrics.py --background-repo <scratch repo copy>`, so rev-5
   wording (e.g. "tiêu đề bị chặn", "mô phỏng") is background, not a leak candidate.
3. **Runners are not spawned as the repo's `doc-reader` / `planner` agent types** (§6 steps 1, 4, 5): those
   definitions preload the active rev-4 skills. Runners are fresh general-purpose Opus agents that take
   the role file `$REPO/.claude/agents/<role>.md` and read the rev-5 SKILL.md files from the scratch repo
   copy only; they do not call the Skill tool.
4. **Isolation.** The scratch repo copy is a `git archive` of the frozen commit without
   `dwg-lab/proposals/skills/eval3/`; drawings are copied per arm into the project's `input/`. The answer
   key and the probe outputs are made unreadable while runners, report writers and planners run, and
   readable again for the simulator (H) and the judges; the key's sha256 is re-checked before judging.
5. **Judges per arm.** J1 and J2 are two fresh Opus judges per arm (four judge agents), each with the full
   brief; they never see this protocol file.

## 9. Limits stated up front

- One run per arm: run-to-run variance is not measured. The report says so.
- All engineer answers are simulated; the key is an agent's reading, not an engineer's.
- LibreDWG, not ODA: conversion artefacts may differ on the pilot.
- The H set is 3 Vietnamese RC houses from one site plus one steel set; it is not the MCS project mix.
