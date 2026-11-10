# Skill eval 4 (2026-11-10) — rev 6 skills after tool wave 3, known set and held-out set

Protocol: `eval4/EVAL-4-PROTOCOL.md` (pre-registered 2026-11-09 at 3accbea, before any wave-3 code; not
edited after). Outputs, friction logs, metrics, judge reports and both answer keys are not in git (they
derive from personal-use drawings). They are archived, without the repo copy, in the git-ignored
`projects/_evals/eval4-2026-11-09/` of the engineer's checkout (`run/` holds the eval folder,
`orchestrator-notes.md` the event log).

## Verdict: FAIL — another tool wave before the shadow pilot

The H arm fails criteria 1 and 2.
- **Criterion 1.** Both judges put R1 far below 95 %: 82.5 % and 85.7 %, mean 84.1 %. H · J2 counts 6
  consequential wrong claims; H · J1 counts 0.
- **Criterion 2.** M2 = 5. Both judges confirm the `marks` producer stores five blocked header cells of
  the 271 bar schedules in `tables[].header[]`, outside a `blocked*` list. It fails by the letter of
  the frozen metric, not because blocked meaning reached a value: each cell carries `meaning: blocked`,
  the table has `header_blocked: true`, and no value is derived from it. The defects behind it are two:
  the font gate over-blocked the plain-Unicode word `KÍNH`, and `marks` keeps blocked header ids where
  M2 counts them (fix 4).

Criteria 3–6 and 8 hold. Criterion 7 fails on H · J2's count (2 no-route gaps; H · J1 counts 0). Both
traps were caught blind, and no document opened or claimed gate 1.

The R arm shows the EVAL-3 fixes landed. No criterion is lower than in EVAL-3 H. R1 rose from 91.4 % to
95.9 % (mean). The R arm fails criterion 7 on R · J2's count, for the same two build-side gaps
(research §11 R1/R8). They predate wave 3, and the EVAL-3 judges did not count them, so this is not a
regression. The M arm holds.

Why it fails: the held-out set hit tool gaps that wave 3 never saw.
- The text extractor reads invisible text. In 271, 232 hidden entries became levels, marks and titles.
- The level extractor misses `+  0.000`. 278's ten storey levels were lost.
- The grid detector found only the key plan of 180. The correct mm answer was then flagged as
  contradicting the drawing.

The agents stayed honest. Every wrong value traces to a tool output, or to a report that dropped the
reader's own correction.

## Frozen inputs

| Input | Value |
|---|---|
| Harness commit | e53a6fd (`feat/tool-wave-2`): 54d46cb plus the rev-6 refresh (EVAL-4 step 1, the only pre-run change) |
| `knowledge/font-encodings.csv` sha256 | a9c8aef2…e9bd (unchanged since EVAL-3) |
| Skills under test | rev 6 (`rev6/`, tree sha256 259a5a6e…29a6), approval SIMULATED |
| Converter | LibreDWG dwg2dxf 0.14 (no ODA) |
| Answer key (H) | answer-key.json 2431e2c8…542c, answer-key.md e3b93205…b83e; 387 items, 12 unsettled; re-checked equal before judging |
| Answer key (R) | EVAL-3 key: answer-key.json 7201f939…5946, answer-key.md aab9d45e…4620; re-checked equal |
| R arm | dwgshare 285, 286, 290; structuralbd 161 (EVAL-3's held-out set, now known material) |
| H arm (held-out) | dwgshare 264, 271, 278; dwgshare 180 steel |
| M arm (metrics only) | dwgshare 267, 433; structuralbd Complete_Steel_01 |

Input drawing sha256 per arm: `frozen-inputs.md` in the archive.

## Scores (0–3, two independent judges per arm)

| Criterion | EVAL-3 H | R · J1 | R · J2 | H · J1 | H · J2 |
|---|---|---|---|---|---|
| R1 factual accuracy | 2 | 3 | 2 | 2 | 1 |
| R2 no guessing | 3 | 3 | 3 | 3 | 3 |
| R3 provenance & confidence | 3 | 3 | 3 | 3 | 3 |
| R4 question quality | 2 | 2 | 2 | 2 | 2 |
| R5 gate discipline | 3 | 3 | 3 | 3 | 3 |
| R6 usefulness (VN engineer) | 2 | 2 | 2 | 2 | 2 |
| R7 skill adherence | 2 | 2 | 2 | 2 | 2 |

Judges differ by at most 1 point on any criterion, and by at most 3.2 points on the R1 share. So no J3
was needed (§7). Final score = mean of J1 and J2: R arm R1 2.5, H arm R1 1.5, every other criterion as
shown.

| R1 claim check | claims | correct | share | consequential wrong |
|---|---|---|---|---|
| R · J1 | 414 | 399 | 96.4 % | 0 |
| R · J2 | 548 | 522 | 95.3 % | 3 |
| H · J1 | 555 | 458 | 82.5 % | 0 |
| H · J2 | 510 | 437 | 85.7 % | 6 |

The judges disagree on "consequential" in both arms. §7 sends only score and share gaps to J3, so the
disagreement stands and both counts are reported.
- **R.** Three claims say the 285 axes are drawn at 3240/4700, and blocking Q-222 offers that as an
  option. Both judges find them wrong: the TRUC axis lines sit at 3130/4590, and 3240/4700 are layer-0
  wall lines 110 mm outside. J2 calls them consequential, because an engineer who picks that option
  shifts axes 1 and 5 by 110 mm. J1 does not, because nothing closes on them and the plan keeps
  3130/4590.
- **H.** Four claims state 278 has no ±0.000 datum or storey levels, and two give the 264 roof slab as
  100 where the key records a conflict (100 vs d=120). J2 calls all six consequential; J1 calls none.

H wrong claims, root causes (both judges):
- **Invisible text read as visible** (about 30 claims, H · J1). 271 ATTRIBs with DXF group code 60 = 1 are
  indexed `invisible: false`. 232 hidden entries in all. They produce:
  - phantom levels +3.850 ×32, +3.450 ×24 and +3.050 ×15;
  - a phantom `d2-1` plan mark on 12 sheets;
  - stale sheet titles, which raised false questions Q-182…Q-185 and cross-checks F-084…F-089.
- **278 storey levels lost.** The level extractor misses text with a space after the sign (`+  0.000`).
  The runner caught it and quoted all ten levels of KT-08 in a Q-054 supplement. The report and plan
  dropped that supplement and wrote "không có mốc ±0.000".
- **180 sheet numbers and grid.**
  - The job number J-01 is taken as the sheet number, and P-01…P-04 are missed.
  - Only the P-01 key-plan grid is found (median spacing 330.78). Q-199 therefore flags the correct
    mm answer as contradicting the drawing, and the report and plan repeat it as fact.
  - The framing-plan grid (1–12, A–Q, 8073 spans) is missed, so 180 got no reader steps 3–7.
- **Marks noise.** Bar diameters D6…D25, A150, `RB 500`, `cos -300`, sheet and job numbers and profiles are
  counted as member marks, which skews every per-sheet count and family list. The 271 BM footing set is
  missing.

## Pass bar (§8, H arm)

| # | Criterion | Result | Holds |
|---|---|---|---|
| 1 | R1 ≥ 95 %, no consequential wrong | 82.5 % / 85.7 % (mean 84.1 %); consequential 0 / 6 | **no** |
| 2 | M2 = 0 | 5 (`marks`, 271 schedules S004–S008 header cell `KÍNH`, T001081 T004157 T005403 T001578 T006438); both judges confirm | **no** |
| 3 | M3 confirmed leaks = 0 | 6 candidates, 0 leaks (both judges); no leak missed | yes |
| 4 | M1 < 30 % per TCVN3/VNI file with ≥ 100 non-ASCII entries | 264: 1.9 %; 271: 6.5 %; 278: 0.1 % (180: 5 entries, below the floor) | yes |
| 5 | M4 procedural share < 50 % (stricter of status / if-engineer) | 0.200 / 0.163 → 0.200 | yes |
| 6 | Trap caught (re-asked quoting both) | Q-052 (264 tầng 3 = +7.200) → blocking Q-204 quotes it and `sàn dày 120 cốt +6.900` (T000174, T000175); caught blind by both judges | yes |
| 7 | No Critical friction unresolved, counting no-route gaps | 0 entries logged Critical; H · J1 0 gaps, H · J2 2 gaps (below) | **no** (on J2's count) |
| 8 | M6 = 0 | 0 (both judges confirm) | yes |

The two no-route gaps of H · J2 (R · J2 names the same two):
- **No grid or level object in the lot spec or the Tekla CLI contract.** No tool emits the Tekla Z string.
  Research §11 R1 gap.
- **The lot spec has linear members only.** Slabs, footings, pile caps, piles, walls and rebar cannot
  enter a lot. Research §11 R8 gap.

Both are build-side gaps of Steps 3–4, not gaps of the reading tools. On the reading side, both H judges
reran `grid-system` with the answers relabelled as the engineer's (on a copy):
- 278 gets S014 from its Q-108 grid values.
- After a select answer that leaves S004 out, 180 gets a `grid_system_missing` (Q-219). So the 180 grid
  has a route, two answer rounds deep.

The M4 engineer-rerun diagnostic in `metrics.py` reported `files_with_engineer_grid: []` for H, which
under-reports (see Limits).

**R arm.** No criterion's final score is lower than EVAL-3 H's (R1 2.5 vs 2; the others equal), and R1 is
95.9 % (mean of 96.4 and 95.3).
- Criteria 2, 3, 6 and 8 hold: M2 0, M3 0 candidates, M6 0, M1 290 23.1 %, M4 0.200 / 0.243.
- Trap: Q-055 (285 tầng 3 = +8.250) → blocking Q-220 quotes the answer, T003318 `+7.950` beside T003321
  `tẦng 3`, and `find-text '8.250'` 0 hits.
- Criterion 7 fails on R · J2's count, for the same two build-side gaps.

The EVAL-3 failures:
- **Sheet numbers: fixed.** 285 36/36 and 290 40/40 match the key.
- **Notes `CI` cell: fixed.**
- **Partial mark lists: mostly fixed.** 290 M1–M6 and 286 ĐC1–ĐC8 are complete. 285 drops DM1–DM4, and
  286 misses the `d2-7` and `d5-5` headings.
- **Grids: 286 fixed, 285 partly fixed.** See fix 3.
- **290 `ù` callouts: no longer silent.** 538 are counted under blocking Q-092, but they are still not
  parsed, so 290's rebar stays unread.

**M arm** holds: M2 0, M6 0, M1 267 0.91 % (786 `ascii_blocked`, all with a question) and 433 0 %, equal to
EVAL-3.

## Ranked fixes (tool wave 4)

1. **Honour DXF group code 60 (invisible) in text extraction.** 271's 232 hidden ATTRIB entries are the
   largest single cause of H wrong claims. Fix: skip or flag invisible entities, with a regression test on
   a synthetic ATTRIB with code 60. — tool.
2. **Grid detection still misses real grids and invents others.**
   - 180: only the key plan is found, and the framing-plan grid is missed. The units check then turns the
     correct mm answer into blocking Q-199.
   - 278: axis `2*` and the A–B direction are missed.
   - 285: bubbles 1, 5 and `a` pair with layer-0 wall lines 110 mm outside the axis lines. This makes the
     spurious S012, false Q-047 and Q-222, and the only R consequential claims.
   - 285: the grid is found on 4 of 16 sheets.
   - The R arm gets 21 systems for 4 buildings, many from rebar or pile labels: 69 conflicts and 99
     grid questions (33 blocking). — tool.
3. **Level extractor:** accept `+  0.000` (space after the sign). 278's ten storey levels were lost and a
   false "no datum" question followed. — tool.
4. **Marks and callouts.**
      - The font gate blocked the plain-Unicode word `KÍNH` (arial_3.ttf) in 271's schedule headers. That one
     word voids 5 schedules (53 rows).
   - `marks` keeps the blocked header ids in `tables[].header[]`, outside a `blocked*` list, which is
     the M2 = 5. Move them to a blocked list, or have M2 read `meaning: blocked`; decide which before
     EVAL-5.
   - Bar diameters, spacings and sheet or job numbers are counted as member marks.
   - 290 `dẦm d-n` plan labels are filed as detail headings.
   - 286 `dẦm d2-7(sl= 01)` is not read.
   - 285 `mark_sets` and `matching[]` disagree.
   - 161's crane-beam schedule is not parsed, so CB-01 is wrongly reported plan-only.
   - 271 BM footings are missing.
   - No plan-mark size is compared with details or schedules (0 of 71 pairs), so the 264 D3 size conflict
     was never asked.
   - — tool.
5. **180 sheet numbers:** the job number J-01 is taken as the sheet number, and P-01…P-04 are missed.
   This is EVAL-3 fix 5 on a new sheet style. — tool.
6. **Skills.**
   - The report and plan must carry reader supplements on producer questions. The Q-054 levels were
     dropped.
   - "Answer contradicts drawing" must check layer and dimensions before treating geometry as the drawing
     (Q-222).
   - Add a reader code for an answer that contradicts the drawing; runners improvised
     `reader_answer_contradicts_drawing`.
   - Say whether the units gate is per file or per project.
   - The rule that every `low` finding cites a question floods the registry with confirmation-only
     questions (R4 stays 2).
   - — skill.
7. **Font questions an engineer can act on.** Q-019 (290 legacy text behind the column schedule) is
   non-blocking and shows no sample, and the font-hint questions give no action that unblocks text.
   — tool + skill.
8. **Build-side routes** (criterion 7, both J2s): add grid and level objects and non-linear members to the
   lot spec and the Tekla CLI contract, or have the engineer decide to keep them `engineer manual`. These
   belong to Steps 3–4. — engineer decision.

## Deviations (recorded during the run)

- **Orchestrator exposure before the run** (recorded 2026-11-09). The key agent's hand-back summary named
  some H content: hidden text via DXF code 60 in 271/278, vns.shx `/g` read as Ø in 271, bars written
  `6D20` in 278, duplicated sheet numbers in 264/271, a missing P-03 in 180. Tool wave 3 briefs predate
  it, and no wave-3 change was made because of it. The code-60 item turned out to be fix 1 above; the
  exposure did not help the tools.
- **Rev-6 refresh as the only pre-run change.** An independent Opus reviewer (no protocol, no key)
  checked rev 6 against the CLI at 54d46cb: 0 Critical, 3 Major, 6 Minor. The fixes are in `rev6/` only
  (commit e53a6fd, the frozen sha).
- **Arm M run by the orchestrator** with a fixed script (`run-m.sh`: intake, read-structure,
  grid-system, callouts, marks, status, questions-md), not by an agent. These are deterministic
  commands, with no judgement involved.
- **Agent tier.** Runners, simulators, report writers, planners and judges were general-purpose Opus
  subagents at the default effort. Briefs were pasted verbatim (runner, simulator, report and plan) or
  copied into the judge's `OUT` as `BRIEF.md`, because the briefs folder is forbidden to those agents.
- **Simulator logs readable for about 38 minutes.** `sim-r/` and `sim-h/` (which name the traps) were not
  locked from about 01:02Z to 01:40Z, while phase-B runners and report writers worked. The keys were
  locked throughout. A grep of every runner, writer and planner transcript, and of every file they
  wrote, finds no read of a simulator folder, key or answer key. Both traps had been caught before the
  writers started.
- **Agents wrote outside `PROJECT`.** Runner R, the R simulator and the H report writer kept helper files
  in the eval folder root (`classes-r.txt`, `notes-r.txt`, `r-env.sh`, `simscripts/`, `gen-h/`).
- **180 held after reader step 2.** The simulated mm answer raised producer question Q-199
  (`units_answer_contradicts_evidence`). The protocol has one simulator round, so no second round was
  run, and 180 got no reader steps 3–7. This is tool behaviour, not a deviation; it is recorded because
  it shrinks the H arm's scored surface.
- **Phase B continued the same runners** through SendMessage, as §6.3 asks. There was no trap-field
  incident: `relay.py` kept only `question_id`, `code`, `text` and `values`, and a grep found no `trap` or
  `basis` field.

## Limits

- One run per arm; run-to-run variance is not measured.
- All engineer answers are simulated, and the keys are agents' readings of the DXF, not an engineer's.
- LibreDWG, not ODA: every file is `partial` and capped at `medium`. On 271, 292 FIELD objects were not
  interpreted.
- The H set is 3 Vietnamese RC houses from one site plus one steel set, not the MCS project mix.
- The R arm is known material: its scores show the wave-3 fixes landed, not that the tools generalise.
- **`metrics.py` M4 engineer-rerun diagnostic under-reports.** It listed no file gaining an engineer grid
  on H, but both judges' own reruns built S014 for 278. The diagnostic is not part of the pass bar; it
  needs a fix before EVAL-5.
- Claim counts vary by judge (414–555), so a share differs by a few points with the reading of the claim
  unit. Both H shares are far below the bar, so this does not change the verdict.
