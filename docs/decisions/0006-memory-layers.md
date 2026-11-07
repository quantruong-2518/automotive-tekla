# 0006. How the harness gets better over time: three memory layers, no graph yet

- Status: accepted
- Date: 2026-11-06

## Context

The engineer wants the product to improve with every project, and asked whether to add an
AI cache or a knowledge graph. Two risks shape the answer: paying again for the same reading
work (vision reads are expensive), and unreviewed "knowledge" written by agents slowly turning
errors into facts (principles 2 and 7).

## Decision

Three layers, each measurable and each human-approved where it holds knowledge:

1. **Read cache** — a content-addressed cache of deterministic reading results (DWG→DXF
   conversion first; DXF extraction and vision reads later). A hit returns a recorded valid
   result of the same action, with its original provenance and confidence cap. The detailed
   design is ADR-0008, written from `docs/research/read-cache.md`. Step 1, slice S2b.
2. **Approved knowledge tables** — versioned in git, every row with source and status
   `proposed` → `approved`: drawing-profile → Tekla catalog map, Vietnamese–English glossary,
   `tekla/api-notes.md` per Tekla version, conventions per design office. Engineer answers to
   questions become rows here. Steps 2–3.
3. **Improvement loop** — RTI → regression test → benchmark → release tag (gate 6). Step 6.

Data rules:

- A cache belongs to one project and lives inside `projects/<project-id>/` (git-ignored):
  it holds client data. No user-global cache, no cache shared across projects.
- Shared knowledge (layer 2) holds only anonymised rules — never drawings, model data or
  client names.

Not now: a knowledge graph or graph database. There is too little data and no relational
query that needs one; tables in git are reviewable as diffs. Revisit when cross-project
queries appear; SQLite tables come before a graph.

Claude prompt caching is automatic in Claude Code; what we control (stable prompt prefixes,
short briefs) is in the `delegating-work` skill.

## Consequences

- Every cached result must stay indistinguishable from a fresh run in provenance and
  confidence; this is a test requirement, not a guideline.
- Knowledge tables need a review step before use; until Step 2 defines it, nothing is
  written to them automatically.
