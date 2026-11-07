# Skill eval 1 (2026-11-06) — rev 2 drafts on 3 real sample sets

Setup: one Opus agent acted as `doc-reader` then `planner`, following the four rev-2 drafts
literally on dwgshare 267 (RC, TCVN3, wrong header units), dwgshare 433 (RC, VNI/Unicode) and
structuralbd Complete_Steel_01 (steel). LibreDWG 0.14 conversion. Engineer answers were
SIMULATED by the orchestrator and labelled so in `answers.json`. Outputs and the friction log
(37 entries: 1 Critical, 17 Major, 19 Minor) are in the session scratchpad (`eval/`), not in git:
they derive from personal-use drawings. An independent Opus judge scored the outputs.

## Scores (0–3)

| Criterion | Score | Key evidence |
|---|---|---|
| R1 factual accuracy | 2 | 40 claims checked: 34 correct, 2 wrong, 2 unsupported, 1 incomplete, 1 unverifiable; every error sits where a tool is missing (marks/schedules from a scratch script) |
| R2 no guessing | 2 | meaning read from `unknown`-encoded text (notes labels, sheet classes) without an approved font row; "three buildings" stated while still asked |
| R3 provenance & confidence | 3 | no confidence raised; detector ids vs printed sheet numbers kept apart; simulated answers flagged everywhere |
| R4 question quality | 2 | verbatim, counts shown; but 26 gate-1 blockers, ~half procedural; duplicates; scratch renderer dropped proposals |
| R5 gate discipline | 2 | stopped at the units hard stop; never proposed building; but continued past the step-6 hard stop with a scratch matcher |
| R6 usefulness (VN engineer) | 2 | clear Vietnamese, conclusion first; eval jargon leaked; missed a grid sanity check (433: 20620 vs 14620) |
| R7 skill adherence | 2 | improvisations logged as friction, but implicit decoding and the step-6 overrun not logged as deviations |

Highlight: the agent caught a simulated answer contradicted by the drawing (`F.F.L+1.20`
vs "structural") and asked again instead of complying.

## Verdict

Not ready for a pilot. Ready for a supervised read-only shadow pilot once fixes 1–4 below and
fix 9 are in.

## Fixes, ranked by impact

1. `harness questions-md`: deterministic renderer of all question sources, reviewed code→Vietnamese
   table, proposals and grid strings/SVG shown, ordered by topic.
2. Legacy-font gate: no meaning from `unknown`/`proposed` text (prose, classes, questions); the
   engineer approves the knowledge row first.
3. `work/reader-findings.json` (schema) for sheet classes, note items, mark matches; reports print
   only numbers from named artefacts; scratch-script numbers banned.
4. Mark and schedule extractor (`Dn.m`, `Dn-m`, `mark(bxh)`, schedule rows); step 6 stays a hard stop until it exists.
5. Grid-system noise: no blockers on rejected systems; selected separate buildings close their
   conflicts; one units question per file, one X/Y question per system.
6. Levels: local platforms are not storeys; reader may raise storey selection; parse `(+ 6.00M LEVEL)`;
   Z coordinate string and origin once storeys are confirmed.
7. Grid sanity: unlabelled grid-layer lines beyond the last axis; overall dimension vs sum of spacings.
8. Skill rules: answer contradicted by drawing → re-ask quoting both; missing framing/foundation
   drawings block gate-1 scope; merge duplicate datum/footing questions.
9. Converter: keep ERROR lines; pilot needs ODA or AutoCAD-exported DXF.
10. Engineer-facing style: no eval/producer jargon; glossary; buildability per building or defer to gate 3.
