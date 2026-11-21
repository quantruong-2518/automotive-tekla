# 0019. The part is the unit of work through the five project stages

- Status: accepted (decisions 1–5 and 8); decisions 6–7 raised with the engineer, not yet confirmed
- Date: 2026-11-20
- Decided by: engineer (chat, 2026-11-20): he gave the five project stages, asked whether the flow
  is optimal for "small parts, few errors, reviewed clean output", and answered "oke triển đi" to
  the part proposal below

## Context

The engineer describes a project as five stages:

1. analyse the drawings, write the analysis report, break the set down;
2. write the approach and the take-off plan: logical order, nothing missed, every risk, gap and
   unclear point listed for his approval;
3. AI builds the Tekla model from the plan with parallel agents, each piece reviewed as it is
   built, cluster reports rolled up into an overall report;
4. review the final model, write the report, index the context needed for drawings;
5. produce the drawings (assembly, GA, …).

Run 3 of project 01 (2026-11-20, reader rev10) shows where the current flow breaks that intent:

- 28 sheets were read in 4 sheet groups; reader contexts reached 470–750k tokens; the read took
  116 min and about 85 USD (list price).
- One merger agent re-recorded 146 candidates as 121 findings and lost the NX2 cap sizes its
  group had read correctly.
- The only review ran after the merge (41 min). The first take-off set, written afterwards, had
  16 problems in 121 sampled rows; a page written from memory invented values.
- 40 open blocking questions blocked every lot, although some member families were nearly complete.

No MCS project has a Tekla model that could serve as an answer model (engineer, 2026-11-20), so
the exit criterion of roadmap Step 2 cannot be met as written.

"Step N" in `docs/roadmap.md` is a build phase of the harness. The engineer's "bước N" is a
project stage. This ADR and `docs/workflow.md` say **stage** for the latter.

## Decision

1. **Five project stages**: 1 Analyse, 2 Plan, 3 Build, 4 Review and index, 5 Drawings. They
   group the numbered steps of `docs/workflow.md`; the gates stay where they are.
2. **A part** is one block × one member family (`NX1-piles`), plus the cross-cutting parts
   `grid-levels`, `notes-materials` and the members that have no sheet. The same part id runs
   through every stage: analysis → take-off file → lot → cluster report → drawings, so every
   figure traces back.
3. **Stage 1 reads per part.** A scout breaks the set down into parts (the sheets, views and
   tables of each); one reader reads one part. The cross-cutting parts are read first and are
   inputs to the others. No agent re-types a value another agent recorded: summaries link to the
   parts.
4. **Each part is closed on its own**: read → script checks → independent review → locked. A
   locked part changes only by being reopened, which sends it through the checks and review again.
5. **Gates work per part.** A locked part with no open blocking question moves on to stage 2 and
   stage 3; the others wait. Gates are still opened only by the engineer.
6. **Stage 3 parallelism** (not yet confirmed): lot-spec preparation, validation and review run
   in parallel across parts; writes to the Tekla model stay one lot at a time through `builder`
   (principle 4, workflow section III unchanged). Parallel writes to one model need research
   first (Tekla multi-user or Model Sharing, unverified).
7. **Before stage 5** (not yet confirmed): connections, clash check and numbering come before
   any drawing; drawings use the company's templates and drawing properties.
8. **Accuracy is measured per part by the engineer's spot check.** Each part offers a short list
   of values with their sheet references; the values he checks become the answer key. This
   replaces the Tekla answer model in the exit criterion of roadmap Step 2 until a real model
   exists.

## Consequences

- The reader's parallel mode (sheet groups, merger) is replaced by a part mode (skill rev11).
- New deterministic checks per part are needed (ids exist, confidence copied, counts agree,
  status from open blocking questions); they are tools, built red-first.
- `drawing-analysis-report` writes the take-off file of a part, not a regrouping after the fact.
- More agents with smaller contexts: time and cost are measured on a rerun of project 01 and
  compared with run 3 (157 min with review, about 85 USD for the read).

## Open

- Sample size of the spot check per part; where the answer key is stored.
- Parallel writes (decision 6) and the place of connections and numbering (decision 7).
- Company templates, drawing properties and UDA names for stage 5.
- Which stage owns PDF, image, DOCX and XLSX reading (`docs/research/step1-exit-audit.md`).
