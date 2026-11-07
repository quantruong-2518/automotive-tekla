# 06 Research: automatic drawing understanding, LLM + CAD, benchmark candidates

Accessed 2026-11-06. "Verified" = I opened the primary page or PDF (arXiv abs page, PDF, project
page, repo URL returned HTTP 200). Grades: A = standards body / official primary text,
B = peer-reviewed or arXiv paper, university/agency guide, manufacturer catalogue, C = blog or supplier.
Papers are rated B (arXiv preprint or conference paper, not independently replicated).

## Sources

| # | Source | Grade | Region | Verified | What it supports |
|---|---|---|---|---|---|
| 1 | [DrawingVQA, arXiv 2607.15418](https://arxiv.org/abs/2607.15418) (PDF copy: `pdf/2607.15418-DrawingVQA.pdf`, licence CC BY-NC-SA 4.0 per arXiv page) | B | US | Y (PDF read) | Closest to our task: 33 "Issued for Construction" structural drawings, 92 expert QA pairs, 3 reasoning depths, 7 construction dimensions incl. Quantity Take-Off (QTO). |
| 2 | [DrawingVQA project page](https://joonv2.github.io/DrawingVQA/) and [HF dataset](https://huggingface.co/datasets/S2-MIND/DrawingVQA) | B | US | Y (HTTP 200, page read) | Question set is public (CC BY-NC per page); the original drawing images are NOT fully public (privacy). |
| 3 | [AECV-Bench, arXiv 2601.04819](https://arxiv.org/abs/2601.04819), [repo](https://github.com/AECFoundry/AECV-Bench) | B | AU/global | Y (PDF read, repo HTTP 200) | 120 floor plans, 192 doc-QA pairs; exact-match + MAPE for counting; LLM-as-judge for QA. Floor plans, not structural. |
| 4 | [FloorPlanCAD, arXiv 2105.07147](https://arxiv.org/abs/2105.07147), [dataset site](https://floorplancad.github.io) | B | CN | Y (abs + site read) | Vector (SVG) CAD dataset, 30 object classes, panoptic symbol spotting task. Site says 15,663 drawings (updated release) vs 11,602 in the first release and "over 10,000" in the abstract; project shut down in 2022 (site news). Licence CC BY-NC 4.0 (from search snippet only: unverified on the page body). |
| 5 | [SymPoint, arXiv 2401.10556 (ICLR 2024)](https://arxiv.org/abs/2401.10556), [code](https://github.com/nicehuster/SymPoint), [SymPointV2 code](https://github.com/nicehuster/SymPointV2) | B | CN | Y (PDF read, repos HTTP 200) | Works directly on vector primitives (not pixels); PQ 83.3 / RQ 91.1 on FloorPlanCAD. Evidence that DXF/vector input beats raster for symbol tasks. |
| 6 | [Training-free agentic CV for structural framing plans, arXiv 2608.17237](https://arxiv.org/abs/2608.17237) | B | CA | Y (abs read only) | Closest design to our harness: deterministic geometry + scale-by-dimension-ratio consensus, then a VLM agent restricted to typed, reviewed corrections ("fail-closed"). Own 100-plan synthetic benchmark; authors state it does not cover independently drafted plans or raster input. |
| 7 | [AEC layout detection benchmark, arXiv 2607.18997](https://arxiv.org/abs/2607.18997) | B | - | Y (abs read only) | Layout detection (title block, tables, views) on AEC drawings: RF-DETR mAP50 0.949, Qwen3-VL F1 0.911; general-document models degrade ("domain interference"). Data release not confirmed. |
| 8 | [CEQuest, arXiv 2508.16081](https://arxiv.org/abs/2508.16081) | B | - | Y (abs read only) | Text QA benchmark on construction drawing interpretation and estimation; dataset "will be open-sourced" (release not confirmed). |

## Best 2-5 sources for us (the cut)
1. **DrawingVQA (1, 2)**: only benchmark on real structural IFC drawings with QTO questions; read in full; question set public, images not.
2. **AECV-Bench (3)**: public repo, clear metrics (exact match, MAPE, LLM-as-judge with human audit); floor plans only.
3. **SymPoint + FloorPlanCAD (4, 5)**: the vector-CAD baseline and the PQ/SQ/RQ metric; closest to a DXF-based pipeline.
4. **Agentic framing-plan paper (6)**: closest design to the harness (deterministic extraction, reviewed typed corrections); abstract only was read, no public code confirmed.
Lower priority: layout-detection benchmark (7) and CEQuest (8), both abstract-only and data release unconfirmed.

## Findings that matter for this harness

1. **Quantity take-off is the weakest skill of general MLLMs.** DrawingVQA reports the top model
   (Gemini-2.5-pro) at 41.7 on QTO questions, several models near 0, against 71.7 overall; Claude-4.5-Sonnet 57.6 overall.
   The authors attribute it to weak spatial grounding and counting in dense drawings. This supports
   AGENTS.md principle 3 (code counts, model interprets).
2. **Symbols and counting are weak, text is strong.** AECV-Bench: OCR/text QA up to 0.95, but door/window
   counting about 0.40-0.55 accuracy. Same conclusion: use vector data / deterministic extraction for counts.
3. **Vector input is the better substrate** (SymPoint, FloorPlanCAD, and the 2608.17237 pipeline all start from vector primitives).
4. **Reviewed-correction pattern** (2608.17237): model proposes typed edits, deterministic admission tests
   accept or reject. Matches "agents propose, humans approve".
5. All public sets are **architectural floor plans or small structural sets**. I found no open dataset of
   rebar schedules, steel connection details, or Vietnamese drawings. Searches covered: "structural drawing dataset",
   "rebar schedule dataset", "connection detail dataset" (search results only; absence is not proven).

## Candidate benchmark design for our own harness (proposal, not from a paper)

Datasets are too small/off-domain to reuse directly, but the **metrics and question taxonomy** can be borrowed.

| Need | Borrow from | Metric |
|---|---|---|
| Value extraction (grid spacing, level, section, schedule cell) | DrawingVQA question types (perceptual / contextual / expert) | exact match per field, plus provenance match (sheet + region) |
| Counting (columns, footings, bolts) | AECV-Bench | per-class exact match + MAPE |
| Symbol / entity recognition from DXF | FloorPlanCAD / SymPoint | PQ, SQ, RQ (panoptic quality) |
| Free-text answers | AECV-Bench LLM-as-judge + human adjudication | binary correct/incorrect, judge audited on a sample |
| Layout (title block, schedule regions) | 2607.18997 | mAP50 per region class |
| End-to-end model vs answer model | harness benchmark (past projects) | tonnage and element-count deviation vs answer model |

Add harness-specific metrics the papers lack: **confidence calibration** (share of "high" values that are wrong),
**open-question precision/recall** (did the system ask where the drawing was truly missing/ambiguous),
and **silent-error rate** (wrong value reported with high confidence; should be zero).

## One-page checklist (how to use this for our benchmark)
1. Build the answer-model set from past projects (AGENTS.md principle 9); freeze it; never tune on the test projects.
2. Define question/field types borrowed from DrawingVQA: perceptual (sheet title, revision), contextual (single sheet: member size at a grid), expert (cross-sheet: bars total, tonnage).
3. Metrics per field type: exact match (strings, sizes, counts); MAPE for counts and quantities (AECV-Bench); PQ/SQ/RQ for DXF symbol/entity recognition (SymPoint); mAP50 per region class for layout (2607.18997); LLM-as-judge only for free text, with human audit of a sample.
4. Add what the papers lack: **provenance match** (sheet + revision + region correct), **confidence calibration** (share of "high" values that are wrong; target zero silent errors), **open-question precision/recall** (did the system ask exactly where the drawing is silent or contradictory).
5. Report by depth and by task (QTO separately: it is the weakest area in DrawingVQA) and by input format (DXF vs vector PDF vs scan).
6. Include Vietnamese-specific cases (legacy encodings TCVN3/VNI, TCVN notation) because no public benchmark has them.
7. Keep a leaderboard row per model/prompt/skill version; changes accepted only if the benchmark does not regress.

## Regional differences
Everything here is English/US/Chinese-CAD biased. No Vietnamese-language drawing set (TCVN3/VNI fonts, TCVN
conventions) exists in these benchmarks. Expect lower OCR accuracy on Vietnamese diacritics and legacy encodings.

## Where sources disagree
- FloorPlanCAD size: abstract "over 10,000", ICLR SymPoint paper 11,602, site 15,663 (later release). Use release number when citing.
- DrawingVQA dates: arXiv v1 is dated 16 Jul 2026 and the project page says "CVPR Findings 2026". I did not resolve the venue timeline.

## Gaps / unverified
- Whether 2607.18997 and CEQuest actually released data/code: not confirmed.
- DrawingVQA full drawings are not public; only the question set. We cannot reproduce their pixels.
- FloorPlanCAD licence text read only in a search snippet.
- I did not run or reproduce any result.
