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

## Amendment 1 (2026-11-07, slice S1b design)

The engineer delegated these choices to the orchestrator ("decide the best options, brainstorm
with a second agent"). An independent Opus review reached the same design; it also ran the current
validator and found it accepts `NaN`, `Infinity`, `1e400` (read as infinity), duplicate keys
(last wins), `lot: 1.0`, lone surrogates and NUL. A receipt over such a file would vouch for values
the C# reader cannot see the same way. Decisions:

1. **One strict JSON profile on both sides** (RFC 8259 plus restrictions). A spec file and a
   receipt file are rejected, by Python and by C#, when they contain: a BOM; invalid UTF-8;
   anything outside RFC 8259 (comments, trailing commas, single quotes, content after the
   document); a duplicate object key (compared after unescaping); `NaN`/`Infinity` or a number that
   is not a finite double; an integer token outside ±2^53; a lone surrogate or U+0000 in a string;
   nesting deeper than 64; a file over 16 MiB. Both read the file's bytes **once**, hash that
   buffer and parse that same buffer. A shared corpus `tests/fixtures/strict-json/` (accept/reject)
   runs in pytest and xunit so the two readers cannot drift. Python applies the profile to `spec`
   validation only.
2. **C# JSON: a hand-written strict reader in `TeklaCore`, no package.** Reason (closes the
   ADR-0009 Consequences item): `TSAppConfigPatcherTask` 2.1.3 redirects
   `System.Runtime.CompilerServices.Unsafe` to the copy in Tekla's `bin` (its `GacDlls` list,
   `tekla/api-notes.md` §1), and `System.Text.Json` on netstandard2.0 depends on that package, so
   Tekla would choose its version at run time. Newtonsoft.Json is a dependency of Tekla 2026's
   Open API and is lenient by default (comments, `NaN`, duplicate keys, date parsing). The strict
   profile above needs a reader that rejects by default anyway.
3. **Receipt**: file `<spec file name>.receipt.json` in the spec's folder (`spec.json` →
   `spec.json.receipt.json`), derived from `--spec`; there is no `--receipt` option. Schema
   `urn:tekla-harness:schema:spec-receipt:0.1`. Fields: `spec_file` (base name, information only),
   `spec_sha256` (lowercase hex of the exact bytes), `spec_schema_id`, `validator`
   (`name`, `version`, `rules_version`) and `validated_at` (UTC, information only, never an
   expiry). Not bound on purpose: absolute path, host, user (the receipt travels with the spec).
4. **`rules_version`** is an integer in Python (`SPEC_RULES_VERSION`), bumped whenever
   `check_spec` or the strict profile becomes stricter; the CLI is built with a minimum and
   refuses older receipts. This covers validator changes that keep the schema `$id`.
5. **`harness validate spec` behaviour**: writing is on by default (decision 1 of this ADR). For
   each file, it first deletes any existing receipt, then validates, then writes the receipt only
   on success (temporary file + atomic replace, validated against its own schema before writing).
   A receipt that cannot be deleted is an environment error (exit `3`). `*.receipt.json` is
   git-ignored; tests validate copies in a temporary folder.
6. **Exit code `5`, not `1`** for every receipt refusal (missing, not strict JSON, wrong shape,
   hash mismatch, unknown schema `$id`, `rules_version` too old), for a spec the C# reader rejects,
   and for a spec `lot` other than `--lot`. Reason: contract rule 3 is a safety rule and the
   contract defines `5` as "refused by safety rule"; decision 2 above said `1` and is replaced.
   Missing or malformed path arguments stay `2`; an I/O error reading a file that exists (access
   denied, a folder, a sharing violation) is `3`.
7. **Read-time checks in C#** (decision 3) also include: spec `schema_version` matches the
   receipt's `spec_schema_id`; `lot` is an integer token within int32; `spec_id` unique within
   the file (contract rule 6 relies on it, so the reader enforces it rather than trusting it).

8. **Numbers are converted by our own code, correctly rounded** (added after the independent
   review). Measured on .NET Framework 4.8.9363 (the production runtime): `double.Parse` gave a
   value 1 ULP away from Python `float()` for 1019 of 150,000 tokens, including plain
   coordinates such as `9.178631892786`. The C# reader therefore converts decimal text to `double`
   with an exact big-integer algorithm (round half to even, as Python), integer tokens become
   `(double)` of their exact integer (`-0` is `+0`, as Python's int `0`), and float tokens keep
   their sign (`-0.0` is `-0.0`).
9. **Values, not only verdicts, are shared.** Every accept file in `tests/fixtures/strict-json/`
   has a canonical dump in `values/` (UTF-16 units of every string and key, IEEE bits of every
   number, int/float flag), produced by Python (`tests/strict_json_values.py`) and compared byte
   for byte by pytest and xunit. `accept/number_parity.json` holds the 1019 tokens above plus
   signed zeros, subnormals and halfway cases.
10. **`pattern` has ECMA-262 meaning** in the Python validator, as JSON Schema 2020-12 requires.
    Python's `$` also matched before a final newline, so `"L1-C-A2\n"` passed the `spec_id`
    pattern and could sit beside `"L1-C-A2"` (found by the review). Outside a character class `$`
    is translated to `\Z` and `.` excludes every line terminator; this applies to every schema.
    The C# reader also checks `spec_id` against its pattern, since `SPEC_ID` becomes a Tekla tag.

Accepted limits:
- A receipt proves the spec bytes have not changed since a validation, not that the validator
  produced the receipt: any agent with file write access can forge one. Signing adds nothing while
  the key sits on the same machine. Gate approval stays with the engineer; a write-deny rule for
  receipts in the Claude Code settings is proposed as an RTI, not part of S1b.
- Any re-encoding in transit (line endings, BOM added by an editor) breaks the hash: that refuses,
  which is safe. How specs travel to the Tekla machine is not defined yet (`projects/` is
  git-ignored).
