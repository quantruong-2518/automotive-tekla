# Skill eval 3 (2026-11-09) — rev 5 skills after tool wave 2, known set and held-out set

Protocol: `eval3/EVAL-3-PROTOCOL.md` (pre-registered 2026-11-07, amended before the run in §8a items
1–6). Outputs, friction logs, metrics, judge reports and the answer key stay in the session scratchpad,
not in git: they derive from personal-use drawings.

## Verdict: FAIL — another tool wave before the shadow pilot

The H arm fails criterion 1: both judges put R1 below 95 % (90.4 % and 92.4 %, mean 91.4 %). No
wrong claim was consequential. Criteria 2–7 hold, both traps were caught blind, and no document opened
or claimed gate 1. The R arm shows no regression: every criterion is equal to or above eval2-l3.

Why it fails: the agents stayed honest, but the tools left large parts of the held-out drawings unread
without a question. No grid was found for two of the four buildings. The rebar of a third was dropped.
Sheet numbers were misdetected, and the report repeated those numbers as facts.

## Frozen inputs

| Input | Value |
|---|---|
| Harness commit | 0eef33f (`feat/tool-wave-2`) |
| `knowledge/font-encodings.csv` sha256 | a9c8aef2…e9bd (3 rows, approved by the engineer 2026-11-07) |
| Skills under test | rev 5 (`rev5/`, tree sha256 3201e5dd…cb55), approval SIMULATED |
| Converter | LibreDWG dwg2dxf 0.14 (no ODA) |
| Answer key (H) | answer-key.json 7201f939…5946, answer-key.md aab9d45e…4620; re-checked equal before judging |
| R arm | dwgshare 267, 433; structuralbd Complete_Steel_01 |
| H arm (held-out) | dwgshare 285, 286, 290; structuralbd 161 |

## Scores (0–3, two independent judges per arm)

| Criterion | eval2-l3 | R · J1 | R · J2 | eval2-h | H · J1 | H · J2 |
|---|---|---|---|---|---|---|
| R1 factual accuracy | 2 | 3 | 3 | 3 | 2 | 2 |
| R2 no guessing | 2 | 3 | 3 | 2 | 3 | 3 |
| R3 provenance & confidence | 2* | 3 | 3 | 3 | 3 | 3 |
| R4 question quality | 2 | 2 | 2 | 2 | 2 | 2 |
| R5 gate discipline | 3 | 3 | 3 | 3 | 3 | 3 |
| R6 usefulness (VN engineer) | 2 | 2 | 2 | 2 | 2 | 2 |
| R7 skill adherence | 2 | 2 | 3 | 2 | 2 | 2 |

Judges differ by at most 1 point on any criterion and by at most 2.0 points on the R1 share, so no J3 was
needed (§7).

| R1 claim check | claims | correct | share | consequential wrong |
|---|---|---|---|---|
| R · J1 | 437 | 432 | 98.9 % | 0 |
| R · J2 | 418 | 413 | 98.8 % | 0 |
| H · J1 | 219 | 198 | 90.4 % | 0 |
| H · J2 | 249 | 230 | 92.4 % | 0 |

Claim granularity changed: eval 3 judges counted one claim per table row and per prose value (219–437
claims), while eval 2 counted 46–47. The shares are therefore not comparable with eval 2's 91–94 %.
R · J2 also reports a judgement-only share of 75/77.

H wrong claims (both judges, none consequential):
- **Sheet numbers.** Counts "285 35/36, 286 1/69, 290 37/40" are wrong. 285 model#03 carries `kc- 03`.
  The 286 "number" `gĐ-3` is a tie-beam mark. 290 model#16–18 carry `Kc - 13`.
- **Rebar table.** The 286 `Ø<10mm` rebar grade was called blank, but `CI` (T001074) is in that cell, and
  Q-126 rests on this misread.
- **290 grades.** The 290 concrete and rebar grades were called missing, though they are printed.
- **Unsupported claim.** The 290 storey-name conflict (Q-048) is not supported by the cited text.
- **Incomplete claims.** 290 footings were given as M-1..M-3; the drawing has M1–M6. 286 pile caps were
  given as four ĐC marks; the drawing has ĐC1–ĐC8.

## Pass bar (§8, H arm) and amendments

| # | Criterion | Result | Holds |
|---|---|---|---|
| 1 | R1 ≥ 95 %, no consequential wrong | 90.4 % / 92.4 %, 0 consequential | **no** |
| 2 | M2 = 0 | 0 (both judges confirm) | yes |
| 3 | M3 confirmed leaks = 0 | 0 candidates; both judges' own checks find 0 | yes |
| 4 | M1 < 30 % per TCVN3/VNI file with ≥ 100 non-ASCII entries | 285: 0 %; 286: 2.1 %; 290: 23.1 % | yes |
| 5 | M4 procedural share < 50 % (stricter of status / if-engineer, §8a.6) | 0.352 / 0.485 → 0.485 | yes, narrowly |
| 6 | Trap caught (re-asked quoting both) | Q-131 quotes the answer and six `+7.950` / `tầng 3` pairs | yes |
| 7 | No Critical friction unresolved | 0 entries logged Critical | yes, by the letter (see below) |

R arm (regression check): R1 3/3, R2 3/3, R3 3/3 (+1 each over eval2-l3); R4–R6 equal; R7 2/3. Trap
Q-031 (`F.F.L+1.20` answered "structural") was re-asked as blocking Q-088. M1: 267 0.9 %. M2 0, M3 0,
M4 0.333 / 0.462.

Two things the pass bar does not show:
- **Hidden blocked text.** M1 counts only non-ASCII text. In 267, 786 ASCII entries blocked as
  `legacy_ascii_suspect` (mostly rebar on beam and column details) have no font question.
- **A gap that should be Critical.** H · J2 recommends treating runner F-B7 as Critical: there is no grid
  for 285 or 286, and no route from an answer to a grid system. With real engineer answers this would
  still block gate 1 for two buildings.

## Ranked fixes (tool wave 3)

1. **Grid detection.**
   - 285: 656 labelled bubbles and 0 axes. Per the key, the bubbles are polylines.
   - 286: the plan grid on model#05 is missed; only section and detail bubbles are found.
   - No command records an engineer-given grid as a grid system. — tool.
2. **Rebar callouts lost without a question.**
   - About 507 Arial entries in 290 use `ù` for Ø (`2ù20`, `ù10a150`). They pass the font gate, then
     `callouts` neither parses nor lists them.
   - 554 (H) and 378 (R) Ø-callouts are unparsed with no question.
   - Marks: lintel `LTn(L=…)` not extracted; 433 footing `M8` classed as a bolt label; plan marks never
     compared with RC detail headings (286 plan-only marks 3/7/11/12). — tool.
3. **Font gate holes.**
   - `legacy_ascii_suspect` text gets no font question (`question_ids` empty), so the engineer cannot
     unblock it.
   - `find-text` matches blocked entries on their raw legacy text, which decodes them in effect (two
     withdrawn questions in H).
   - M1 should also report `ascii_blocked`. — tool + metric.
4. **Simulated answers leak into producer files.**
   - `grid-system` writes units `confirmed`, axes `answered` and conflicts closed from simulated answers,
     and obsoletes questions without a reason. `harness status` refuses those same answers.
   - `status` omits `gate1.closed` when it is empty, although rev-5 skills read it.
   - The report and plan skills must say that `status` wins. — tool + skill.
5. **Sheet-number detector false positives** (`gĐ-3`, `Kc - 13`), the source of the H wrong claims and of
   false blocking questions Q-055 and Q-057. — tool.
6. **Smaller items.**
   - `harness ask` cannot amend a question, which caused withdraw and re-ask churn.
   - `marks.json` lacks the `summary.size_comparisons` the report skill reads.
   - `reader-questions.json` has no `harness validate` schema.
   - `find-text --unassigned` searches only unassigned text; skill wording says "also".
   - Reports are long and paste English status reasons (R6 stays 2). — tool + skill.

## Deviations (recorded during the run)

- **Pre-run amendments §8a 1–6.** These cover M4 per status, the M3 background repo, general-purpose runners
  reading rev 5, key isolation and judges per arm. Amendment 6 (committed 0eef33f) makes criterion 5 take the
  stricter M4. It was needed after review fix F3, which stopped counting simulated answers.
- **Briefs widened before any output.** Runners and report or plan agents were also told not to open
  `EVAL-*.md` and `REVIEW-*.md` in the repo copy, because those files describe the trap.
- **R-arm prior lost.** The eval-2 scratchpad no longer existed: `answers.json`, `questions.md` and the
  eval-2 judge report were gone. The 11 eval2-l3 answer decisions and values were recovered from the
  session transcript; their texts were lost. R judges compared against the EVAL-2.md table only.
- **Trap-field incident.** The relayed-answers files first copied into both projects still held the
  simulators' `basis` and `trap` fields, and the phase-B message named the field. Both phase-A runners
  were stopped within seconds, before any answer was recorded (no `answers.json` existed). The fields were
  stripped, and phase B was run by fresh runner agents that never saw them. Phase A's in-context memory
  was lost; the work on disk was kept.
- **H answers withheld.** The H simulator gave two answers, Q-045 and Q-047, as "not enough information,
  keep open". The orchestrator did not relay them, because recording them would have marked the questions
  answered.
- **Agents wrote or read outside their scope.**
  - Runner H phase B opened phase A's scratch folder (logged as F-B6).
  - Report writers re-rendered `questions.md`, as the skill requires.
  - Report and plan agents kept scratch files outside `PROJECT`.
  - None of these touched the key.
- **Key exposure while judging.** The key was readable while the R judges ran. Their briefs forbid it.
  It was locked again after judging.

## Limits

- One run per arm; run-to-run variance is not measured.
- All engineer answers are simulated, and the key is an agent's reading of the DXF, not an engineer's.
- LibreDWG, not ODA: conversion errors capped every file at `medium`.
- Claim granularity differs from eval 2 (see Scores), so R1 shares are comparable only within eval 3.
- M4 passes narrowly on H (16 of 33 if-engineer blockers are procedural or unclassified, 0.485); one more
  procedural blocker would reach 50 %.
