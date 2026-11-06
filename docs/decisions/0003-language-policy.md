# 0003. Language policy

- Status: accepted
- Date: 2026-11-06

## Context

The engineer works in Vietnamese. Code and tooling ecosystems, Tekla API docs, and model
performance favour English for code.

## Decision

- Everything committed to the repository is English: code, comments, identifiers, schemas,
  docs, skills, agent definitions, commit messages.
- Agent replies to the engineer are Vietnamese (`"language": "vietnamese"` in `.claude/settings.json`).
- Human-facing project deliverables (analysis, questions, reports) are Vietnamese; their
  file names, JSON keys and enum values are English.
- Drawing text is stored verbatim (after encoding normalisation to Unicode), never translated in place.

## Consequences

Reports read naturally for the engineer while code stays searchable and tool-friendly.
A Vietnamese–English structural glossary is required (Step 2 skill).
