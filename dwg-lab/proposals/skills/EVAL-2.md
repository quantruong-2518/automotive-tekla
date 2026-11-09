# Skill eval 2 (2026-11-07) — rev 3 drafts, known set and held-out set

Setup: the four rev-3 drafts, after the EVAL-1 tool wave (questions-md, font gate, reader findings,
marks, gate-1 question noise). Two runs, each: one Opus agent ran `drawing-intake` and reader steps
1–2, the orchestrator recorded SIMULATED engineer answers (labelled), the same agent ran reader steps
3–7, then a fresh agent wrote `01-analysis.md` and the gate-1 `02-plan.md`. An independent Opus judge
scored both with the EVAL-1 rubric and checked claims with the read-only harness tools.

- **eval2-l3**: the eval-1 drawings (dwgshare 267, 433; structuralbd Complete_Steel_01), font rows
  PROPOSED. One simulated answer (levels are structural) was deliberately left contradicting the
  drawing, as in eval 1.
- **eval2-h**: three HELD-OUT drawings never used in development (dwgshare 270, 461; structuralbd
  Complete_Steel_02), run on a scratch copy of the repo where the three font rows were marked approved
  as a simulation.

Outputs, friction logs (l3: 43 entries, 0 Critical; h: 44 entries, 1 Critical) and the judge's report
stay in the session scratchpad, not in git: they derive from personal-use drawings.

## Scores (0–3)

| Criterion | Eval 1 | eval2-l3 | eval2-h |
|---|---|---|---|
| R1 factual accuracy | 2 | 2 | 3 |
| R2 no guessing | 2 | 2 | 2 |
| R3 provenance & confidence | 3 | 2* | 3 |
| R4 question quality | 2 | 2 | 2 |
| R5 gate discipline | 2 | 3 | 3 |
| R6 usefulness (VN engineer) | 2 | 2 | 2 |
| R7 skill adherence | 2 | 2 | 2 |

\* a check eval 1 did not apply: two findings asserting level values were `medium` while the level
extractor had those values `low` (`finding add` takes confidence from text entries only).

Claims checked: eval 1 34/40 correct; eval2-l3 42/46 (2 wrong, both interpretation); eval2-h 44/47
(0 wrong, 2 unsupported: words taken from font-blocked text into the plan's prose). Every number
copied from an artefact was correct. Eval 1's missed grid sanity check (433) is now caught; the
contradicted simulated answer was caught again and re-asked quoting both.

## Verdict

Skills: the agents follow them well on known drawings; remaining skill issues are clarifications.
Tools: not yet a company shadow pilot. On held-out drawings the agents stayed honest but yield was
low: one file had no detected sheet (all text unreachable), most legacy Vietnamese text stayed blocked
because `font_hint` ignores the TTF `.Vn*` family name, and producers (callouts, levels) still take
values from blocked text.

Pilot conditions: producers apply the font gate; `.Vn*` family read and the font rows decided by the
engineer; sheet-less files searchable; question lifecycle fixed (no re-issued conflicts, rejection
per family); reader questions rendered as written (done after the eval); pilot entry with ODA or
AutoCAD-exported DXF, the Tekla version recorded, real engineer answers only. Then a new held-out eval.
Proposed pass bar: R1 ≥ 95 % with no consequential wrong claim, no producer value from blocked text,
no prose leak, < 30 % of non-ASCII text blocked on TCVN3/VNI drawings, gate-1 blockers less than half
procedural.

## Ranked fixes

1. Producers bypass the font gate (callouts fixed after the eval; levels, marks prefix questions open) — tool.
2. Font coverage: read the `.Vn*` TTF family; block ASCII text in legacy-font styles — tool + engineer decision.
3. No words from blocked text in any prose, scope row or risk title — skill.
4. Sheet-less files: `--unassigned` search and a skill route — tool + skill.
5. Question lifecycle: keep conflict ids, non-blocking only when every cited family is rejected, close
   `grid_units_doubt` from the units answer, one project-level "same set or separate projects?" question — tool.
6. Reader questions print as written; `ask` text is Vietnamese — tool (done after the eval).
7. Duplicate producer questions (storey selection) and missing prefix questions (`ask --supplement`) — tool + skill.
8. Schedule gate too coarse (one blocked header cell blocks a table); plan-mark sizes not compared — tool.
9. Converter: ODA or AutoCAD DXF for the pilot; record the LibreDWG version — engineer decision + tool.
10. Answer provenance: role of who answered; gate readiness refuses non-engineer answers; `decoded_by` on findings — tool.
11. Measurement and summary tools: dimensions, per-sheet/per-file counts the report asks for — tool.
12. Skill clarifications: gate 1 not ready → draft headed by the reasons; empty levels table; one Tekla
    model or several for separate buildings; a file outside every selected system; a `low` finding needs
    a question; the report writer returns gaps to the orchestrator; compound rule statuses cited as
    written; `planner.md` lot split is gate 3; a finding about levels takes the level extractor's confidence.
