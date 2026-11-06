# 0001. Record architecture decisions

- Status: accepted
- Date: 2026-11-06

## Context

The harness will be changed by agents and humans over many versions. Decisions that are
hard to reverse need a durable record of why they were made.

## Decision

Use Architecture Decision Records in `docs/decisions/`, numbered `NNNN-title.md`, with the
sections Context, Decision, Consequences. Accepted ADRs are never edited; a new ADR supersedes them.

## Consequences

Reviewers and agents can check a proposal against recorded decisions before changing structure.
