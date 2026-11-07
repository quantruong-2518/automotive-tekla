# 0010. One spec validator: Python validates, the CLI checks a receipt

- Status: accepted
- Date: 2026-11-07
- Decided by: engineer (question round, 2026-11-07)

## Context

Contract safety rule 3 makes `tekla-cli` refuse unless `--spec` is schema-valid. The Python side
already validates specs (`harness validate spec`, JSON Schema plus `check_spec`: unique
`spec_id`, non-zero length, low confidence needs a question). Re-implementing those rules in C#
would create a second validator that drifts from the first (ADR-0009, Consequences).

## Decision

1. **The Python validator is the only full validator.** On success it writes a receipt next to
   the spec: the spec's SHA-256 (of the exact file bytes), the spec schema `$id`, the validator
   version, and the time. The receipt is itself a JSON artefact with a schema in `schemas/`.
2. **The CLI checks the receipt, not the rules.** Before `build` or `update` it refuses (exit `1`)
   unless a receipt exists, its SHA-256 equals the spec file's bytes, and its schema `$id` is one
   the CLI was built for. Any edit to the spec after validation therefore refuses.
3. **The CLI still checks what it needs to build safely** while reading the spec (units `mm`,
   `lot` matching `--lot`, every member it creates has a `spec_id`, profile, material and two
   points). These are read-time checks of the CLI's own input, not a second copy of
   `check_spec`.

## Consequences

- Slice S1b: receipt schema and writer in Python (`harness validate spec` gains the receipt),
  receipt check and spec reader in `TeklaCore`.
- The Tekla machine needs no Python to build; the receipt travels with the spec.
- A receipt proves the spec was validated, not who validated it; gate approval stays with the
  engineer (principle 5).
