# Context length and model quality (Claude 5.x): where does it measurably drop?

- **Question:** at what context length does quality (recall, reasoning, instruction following,
  hallucination) measurably drop, per model: Opus 5.5, Sonnet 5.5, Haiku 5.5, Fable 5.2 (predecessors
  where 5.x has no data)? Used to set Claude Code thresholds: warn, force handoff, `autoCompactWindow`.
- **Sources searched:** Anthropic system cards (Opus 4.6, 4.7, Opus 5.5, Sonnet 5.5, Haiku 5.5, Fable 5.1 /
  Mythos 5.1; PDFs downloaded and text-extracted), platform.claude.com docs (context windows,
  compaction, prompting best practices), Anthropic engineering blog (context engineering), Claude Code
  docs (`model-config`, `costs`), Chroma "Context Rot" report, RULER (arXiv 2404.06654), NoLiMa
  (arXiv 2502.05167), Fiction.LiveBench, OpenAI MRCR. Not searched: Fable 5.2 system card (none listed).
- **Date accessed:** 2026-11-10.
- **Status tags:** `verified` = quoted from a primary source with URL. `inferred` = my deduction.
  `not-found` = searched, not found.
- **Answer in one line:** **no primary source gives a per-model "quality drops at N tokens" threshold
  for any 5.x model.** Anthropic says in words that quality degrades as context grows, but gives no
  number. The only per-length Claude numbers are for Opus 4.6 (MRCR/GraphWalks, buckets 128k-256k vs
  524k-1M) and old models (NoLiMa, Chroma). So 200k / 300k / 400k are **unsupported by data in either
  direction**: nothing contradicts them, nothing supports those exact values. Measure on our own benchmark.

---

## 1. Problems first

| # | Rank | Problem | Reason | Fix |
|---|---|---|---|---|
| P1 | Critical | **No per-length data exists for Opus 5.5, Sonnet 5.5, Haiku 5.5 or Fable 5.2.** | The 5.x system cards report one long-context number (ProgramBench, aggregate over episodes "up to the full 1M token window"), no length buckets (§3). Fable 5.2 has no system card on the system-cards page; the nearest is Fable 5.1 / Mythos 5.1. | Treat every threshold as a hypothesis. Measure (§6). |
| P2 | Critical | The only bucketed Claude numbers (MRCR v2, GraphWalks) measure **retrieval and graph search over synthetic filler**, not agentic coding with tool output, edits and instructions in CLAUDE.md. | They do not measure instruction following or hallucination of absent values, the things this harness cares about most (principles 2, 4). | Build our own probe (§6). Use benchmarks only as an upper bound for recall. |
| P3 | Major | Numbers for 4.x do not transfer to 5.x. Within 4.x, Opus 4.6 to 4.7 changed long-context behaviour in opposite directions on two benchmarks (§3). | Same lineage, different result per benchmark. A 5.x generation can differ again. | Re-measure per model ID; re-run after every model alias change (`opus` -> 5.5 at Claude Code v2.1.280). |
| P4 | Major | MRCR bins are coarse: Anthropic reports only (128k, 256k] and (524k, 1024k]. | Nothing is reported below 128k or between 256k and 524k, so 300k and 400k fall in a gap, 200k inside a bin. | Cannot place a threshold from these data. |
| P5 | Major | Third-party studies tested old models (Chroma: Opus 4, Sonnet 4, Sonnet 3.7/3.5, Haiku 3.5; NoLiMa: Claude 3.5 Sonnet; RULER: no Claude). | Cannot be applied to 5.x. | Use as qualitative support for "degradation exists" only. |
| P6 | Major | Haiku 5.5 costs more for prompts over 100k tokens. | A cost reason, not a quality reason, to keep Haiku sessions short; do not mix with a quality threshold. | Set Haiku thresholds separately. |
| P7 | Minor | Opus 4.7 MRCR numbers (59.2 / 32.2) appear only in figures in the PDF and in a blog. | I could not read them from the primary text (§3). | Marked `claimed`. |
| P8 | Minor | Compaction is itself lossy and can alter behaviour (Anthropic lists it as an eval limitation). | A low `autoCompactWindow` trades context rot for summary loss. | Keep notes in files (handoff) rather than relying on summary. |

## 2. Anthropic's statements on degradation (all words, no numbers)

- `verified` Context windows doc: "As token count grows, accuracy and recall degrade, a phenomenon
  known as *context rot*. This makes curating what's in context just as important as how much space is
  available." https://platform.claude.com/docs/en/build-with-claude/context-windows
- `verified` Compaction doc: it "keeps the active context small, because response quality degrades as a
  conversation grows." https://platform.claude.com/docs/en/build-with-claude/compaction
- `verified` Engineering blog: "the model's ability to accurately recall information from that context
  decreases" as the window fills; attention gives "n² pairwise relationships for n tokens."
  https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- `not-found` Any Anthropic page naming a token count at which quality starts to fall, for any model.
- `verified` Claude Code docs describe Fable as one that "holds long sessions without losing the thread"
  (vendor description, no benchmark) - https://code.claude.com/docs/en/model-config

## 3. Per-model table

Windows: https://platform.claude.com/docs/en/build-with-claude/context-windows (all four are 1M; Fable 5.2,
Opus 5.5, Sonnet 5.5, Haiku 5.5 listed). Claude Code compacts native-1M models at "about 967K tokens by
default" (model-config, "Default auto-compact thresholds").

| Model | Window | Evidence of degradation (metric, length, short vs long) | Source | Status |
|---|---|---|---|---|
| Opus 5.5 | 1M | None bucketed. ProgramBench 91.2%, "episodes cover a range of context lengths up to the full 1M token window"; no per-length split. | Opus 5.5 system card (Sep 22, 2026), sec. 8.10.1: https://www.anthropic.com/claude-opus-5-5-system-card | `not-found` (per length) |
| Sonnet 5.5 | 1M | None bucketed. ProgramBench 79.7% (Sonnet 5: 77.3%). | Sonnet 5.5 system card (Sep 28, 2026), sec. 8.10.1: https://www.anthropic.com/claude-sonnet-5-5-system-card | `not-found` |
| Haiku 5.5 | 1M | None bucketed. ProgramBench 82.0%. Prompts over 100k cost more. | Haiku 5.5 system card (Oct 7, 2026), sec. 8.7.1: https://www.anthropic.com/claude-haiku-5-5-system-card | `not-found` |
| Fable 5.2 | 1M | No system card found. Predecessor Fable 5.1: ProgramBench 87.6% (Fable 5: 86.3%), no per-length split. | Fable 5.1 / Mythos 5.1 system card, sec. 8.11.1: https://www.anthropic.com/claude-fable-5-1-mythos-5-1-system-card | `not-found` |
| Opus 4.6 (predecessor) | 1M | MRCR v2 8-needle (Mean Match Ratio, 64k thinking): **91.9** at (128k, 256k] -> **78.3** at (524k, 1024k] (max effort: 93.0 -> 76.0). GraphWalks BFS F1: 61.5 on the 256K subset -> 41.2 on 1M; parents: 95.1 -> 71.1. | Opus 4.6 system card, sec. 2.18, Table 2.18.A: https://www-cdn.anthropic.com/6a5fa276ac68b9aeb0c8b6af5fa36326e0e166dd.pdf | `verified` |
| Opus 4.7 (predecessor) | 1M | GraphWalks: BFS 76.91 / parents 93.57 on the 256K subset; 58.6 / 75.1 on 256K-1M (so a drop at the longer half). MRCR v2 results are in figures only; a blog gives 59.2 (256k) and 32.2 (1M), down from 91.9 / 78.3 for Opus 4.6. | Opus 4.7 system card, sec. 8.7: https://anthropic.com/claude-opus-4-7-system-card . Blog: https://allthings.how/claude-opus-4-7-system-card-key-findings-and-benchmarks/ | GraphWalks `verified`; MRCR `claimed, not traced to a primary source` (figure not readable as text) |
| Sonnet 4.5 | 200k (1M beta) | MRCR v2 8-needle, 64k thinking: 10.8 at (128k, 256k], 18.5 at (524k, 1024k]. Both low; the 1M bin is not lower than the 256K bin (odd; not explained in the card). | Opus 4.6 system card, Table 2.18.A (same URL) | `verified` |
| Claude 3.5 Sonnet (old) | 200k | NoLiMa (latent-match needle), score by length: 1K 85.4, 2K 84.0, 4K 77.6, 8K 61.7, 16K 45.7, 32K 29.8 (base score 87.5; threshold 74.4 = 85% of base). Paper's "effective length": 4K. | NoLiMa arXiv 2502.05167, results table: https://arxiv.org/abs/2502.05167 | `verified` (old model) |
| Opus 4, Sonnet 4, Sonnet 3.7/3.5, Haiku 3.5 | 200k | Chroma: "The Claude models exhibit the most pronounced gap between focused and full prompt performance" (LongMemEval, ~113k full vs ~300 tokens focused), mostly from abstentions. Needle task: Claude had the lowest hallucination rates with distractors; "Sonnet 4 and Opus 4 are particularly conservative and tend to abstain when uncertain." No numeric Claude scores in the report text. | https://www.trychroma.com/research/context-rot | `verified` (words only) |
| Any Claude | - | RULER (arXiv 2404.06654) tables list no Claude model; Claude appears only in citations. | https://arxiv.org/abs/2404.06654 | `not-found` |
| Any Claude | - | Fiction.LiveBench page fetched had no readable table. | https://fiction.live | `not-found` |

NoLiMa note: columns are `1K 2K 4K 8K 16K 32K` after the base score. Abstract: models "perform well in
short contexts (<1K), performance degrades significantly as context length increases."

Observations (`inferred`):
- Opus 4.6 loses about 13.6 points of MRCR between the 128k-256k bin and the 524k-1M bin. That is a
  measurable loss, but it says nothing about 200k vs 300k vs 400k, and the model is not a 5.x.
- Opus 4.7 improved GraphWalks vs 4.6 (256K subset BFS 76.91 vs 61.5) while the blog claims MRCR got
  worse. Different benchmarks can move opposite ways between neighbouring models.

## 4. What Anthropic recommends for long agentic sessions

- Compaction first: "For long-running conversations and agentic workflows, server-side compaction is the
  primary strategy for context management." (context windows doc)
- Clear stale tool output: tool result clearing is "one of the safest lightest touch forms of
  compaction." (context-engineering blog)
- Notes outside the window: "the agent regularly writes notes persisted to memory outside of the
  context window." (blog)
- Sub-agents: "specialized sub-agents can handle focused tasks with clean context windows", returning
  summaries "often 1,000-2,000 tokens." (blog)
- Fresh window over compaction when state is on disk: "consider starting with a brand new context window
  rather than using compaction. Claude's latest models are extremely effective at discovering state from
  the local filesystem." (prompting best practices, "Workflows across multiple context windows")
  https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices
- Claude Code: "Use `/clear` to start fresh when switching to unrelated work. Stale context wastes tokens
  on every subsequent message." Delegate verbose output to subagents. (costs page)
  https://code.claude.com/docs/en/costs
- Claude Code compacts native-1M models at about 967K by default; the window is set per model with
  `/autocompact`, `autoCompactWindow`, `--autocompact` or `CLAUDE_CODE_AUTO_COMPACT_WINDOW`, accepted
  range 100K to 1M. (model-config)
- Context awareness tags (token budget) are injected only for Sonnet 5 and older Sonnet/Haiku 4.x;
  Opus 4.7+, Sonnet 5.5, Fable 5.x and Haiku 5.5 "don't receive these injected tags." (context windows
  doc). So 5.5 models do not see their remaining budget; the harness must warn for them.
- Anthropic's own 5.5 evals ran with big windows: HLE runs had a 980k token budget and "Context
  compaction was not used" (Sonnet 5.5 / Haiku 5.5 cards). `inferred`: Anthropic treats the 1M window as
  usable for capability tests; this is not a statement of quality at 900k.

## 5. Implications for 200k warn / 300k handoff / 400k compact

| Proposed value | Supported? | Why |
|---|---|---|
| Warn at 200k | Weakly, and only as a convention | 200k is the old window size and sits inside Opus 4.6's (128k, 256k] MRCR bin, where that model still scored 91.9. No 5.x data. Cost argument holds for Haiku 5.5 (premium over 100k). Arbitrary for quality. |
| Handoff at 300k | Arbitrary | Falls in an unmeasured gap (256k-524k). No source tests it. |
| Compact at 400k | Arbitrary, but conservative | Below the 967k default and the 524k start of the only long bin. Nothing contradicts compacting earlier; the qualitative sources (context rot, "response quality degrades as a conversation grows") favour keeping context small. Cost: summary loss (P8). |
| 967k default | Not supported as a quality point | A capacity guard (the window nearly full), not a quality threshold. Opus 4.6 lost 13.6 MRCR points before reaching it. |

Direction is consistent with Anthropic's wording (shorter is safer, compaction and handoff are the
documented remedies). The numbers are not. Order of thresholds (warn < handoff < compact) is a
design choice, not a finding. Do not present them as evidence-based.

## 6. Proposed measurement ("measure, don't feel")

Goal: for each of Opus 5.5, Sonnet 5.5, Haiku 5.5, Fable 5.2, find the first fill level where a task
metric drops against its own 50k baseline.

1. Take 3 benchmark projects with answer models. Build each prompt from a real session transcript (real
   tool output, not random filler), truncated or padded to fill levels 50k, 100k, 150k, 200k, 300k, 400k,
   600k, 800k.
2. At each level, ask a fixed battery with known answers:
   - recall: a mark, level or value planted early, with its provenance (sheet, revision, location);
   - reasoning: a multi-step cross-check across two early facts (schedule vs plan);
   - instruction following: a rule from `AGENTS.md` that conflicts with the easy path (for example
     "write an open question, do not guess");
   - hallucination: ask for a value that is absent; correct answer is "not found" plus a question.
3. At least 5 trials per cell, same sampling settings, same effort; record pass rate and Wilson interval.
   Add a control: the same question in a fresh context holding only the needed facts.
4. Threshold = first level whose pass rate is more than a pre-agreed margin (for example 10 points)
   below the 50k baseline with non-overlapping intervals. Report per model and per metric; hallucination
   (false value instead of abstain) matters most for this harness.
5. Also record cost per level (cache reads) and compaction-summary loss: after a forced compaction at each
   level, rerun the recall probe on the summary.
6. Archive the run under `projects/_evals/` (per the "archive eval evidence" rule), then set warn,
   handoff and `autoCompactWindow` from the measured knee, per model.

Until then, a defensible interim policy is "warn and hand off earlier than the default, because every
source says shorter is safer", labelled as a hypothesis, with the 200/300/400 numbers kept as
placeholders.
