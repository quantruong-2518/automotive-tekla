# 0012. Run journal and resume planner (slice S1c)

- Status: accepted (orchestrator design within ADR-0007; decision 7 by the engineer, 2026-11-08)
- Date: 2026-11-08
- Decided by: orchestrator after an independent Opus critique; engineer for decision 7

## Context

ADR-0007 fixed the behaviour: on any API error `build` stops, keeps what it made, writes a run
journal and exits `4`; re-running the same lot with the same `RUN_ID` builds only what is missing,
never a duplicate `SPEC_ID`, and stops (exit `1`) when an existing object differs from its spec item.
It left the journal format and the exact resume rules open. `tekla/api-notes.md` §5 recommends
recording each GUID before tagging: an object can exist without tags if the run dies in between,
and whether uncommitted inserts survive a crash is unknown (To verify #9).

An independent critique of the first draft found four ways to create a duplicate `SPEC_ID`: a crash
between `Insert` and the journal write; a snapshot that silently misses objects because UDA filters
are unverified (To verify #5, #7); "not found" confused with "failed to load" (To verify #15); and two
CLI runs at once. This version closes them.

S1c is Tekla-free: journal (schema, reader, writer), model snapshot types, run lock and a pure
resume planner in `TeklaCore`. S2 fills the snapshot from the Open API; S4 executes the plan.

## Decision

1. **`RUN_ID`** matches `^[A-Z0-9][A-Z0-9_-]{0,31}$` (`run_id` in `common.schema.json`): it is a UDA
   value and part of a file name. A `RUN_ID` belongs to one lot: objects carrying it in another lot
   are a conflict. `LOT` is written as the invariant-culture integer, no padding.
2. **Journal file** `run-journal-<RUN_ID>.json` in the spec's folder, schema
   `urn:tekla-harness:schema:run-journal:0.1`, strict JSON profile (ADR-0010 A1 §1) on read and
   write. Header binds the run: `project_id`, `lot`, `run_id`, `spec_file`, `spec_sha256` (from the
   receipt), `model_path` (the working copy). `invocations[]` in execution order, each: `command`
   (`build`, `update`, `rollback`), `started_at`/`ended_at` (UTC, information only), `tekla_version`,
   `model_path`, `outcome` (`running`, `ok`, `stopped`, `conflict`, `refused`, `abandoned`),
   `exit_code`, `committed`, `objects[]`, `failure` and `conflicts[]`. An object entry is `spec_id`,
   `guid` (null until known), `action` (`created`, `retagged`) and `state` (`inserting`, `inserted`,
   `tagged`).
3. **Write policy.** The whole file is rewritten atomically (temporary file in the same folder,
   flushed to disk, then replace; up to 3 retries 100 ms apart for a locked target) at invocation
   start (`running`), **before each `Insert`** (intent: `state: inserting`, no GUID), after it
   (`inserted` + GUID), after tagging (`tagged`), and at the end. If a journal write fails the run
   stops before the next `Insert`; an object whose GUID is known is still tagged, every GUID made is
   printed in the stdout JSON, and the exit code is `4`.
4. **One writer per model.** A write command holds an exclusive lock for its whole run, keyed on the
   normalised working-copy path (named mutex; Tekla serves only the first session, so every CLI on
   the machine talks to the same model). A held lock refuses (exit `3`). An invocation still
   `running` in a journal when the lock was free crashed: it is marked `abandoned`.
5. **What refuses before planning** (nothing written):
   - journal exists but is not strict JSON or not schema-shaped → `5`; journal I/O error → `3`;
   - journal `spec_sha256` ≠ the receipt's → `5` (a changed spec is `update` in S4, or `rollback` of
     this run and a build with a new `RUN_ID`, decided by the engineer);
   - journal `model_path` ≠ the open working copy (same comparison as safety rule 1) → `5`;
   - the run has a completed `rollback` invocation → `5`;
   - no journal, but objects tagged with this lot and `RUN_ID` exist → `5` (untagged leftovers
     cannot be ruled out without it).
6. **Snapshot** (supplied by S2, global coordinates in mm): the union of objects with `LOT` = lot,
   `RUN_ID` = run, `SPEC_ID` in the spec's ids, and every journal GUID. Per object: GUID, which of
   those lookups found it, kind (`beam`/`column`/... in the spec's `type` vocabulary, or `other`),
   each of the three tags as value / absent / unreadable, start, end, profile, material, rotation,
   class, name. Per journal GUID: present, absent (only when the lookup of that very GUID says "not
   found") or error. Refusals: an unreadable tag or a GUID lookup error → `3`/`4`; a journal GUID
   tagged with this lot that the `LOT` lookup did not return → `3` (the filter cannot be trusted).
7. **"Differs"** (ADR-0007 §2, widened by the engineer on 2026-11-08): an object matches its spec
   item only when the start and the end are each within 0.1 mm (Euclidean, `d <= 0.1`; a non-finite
   point never matches; start with start, end with end), profile and material are equal (ordinal),
   the kind equals the spec `type`, the rotation is within 0.01° modulo 360 (absent in the spec =
   0), and the class is equal when the spec gives one. A different name is reported, not a conflict.
8. **Plan per spec member** — exactly one action:
   - `skip`: one object tagged with this lot, run and `SPEC_ID` that matches; if the journal has a
     GUID for this `SPEC_ID`, it must be that object;
   - `retag`: no tagged object, a present journal GUID for this `SPEC_ID` with missing tags (none
     contradicting), and it matches;
   - `create`: no object anywhere in the snapshot for this `SPEC_ID`, and no present journal GUID for
     it. A journal GUID that is absent is reported (`recreated`, with its last state), never silent;
   - `conflict` (exit `1`, nothing written): a mismatch (decision 7); two or more objects with this
     `SPEC_ID` in the lot; this `SPEC_ID` under another `RUN_ID`; a journal entry still `inserting`
     (an object may exist untagged: the engineer checks the model, then rolls the run back or removes
     the stray object and starts a new `RUN_ID`); tags that contradict the journal.
   Run-level conflicts: an object tagged with this lot and run whose `SPEC_ID` is not in the spec;
   an object with any harness tag the rules above cannot classify; this `RUN_ID` in another lot. All
   conflicts are returned together.

## Consequences

- S2 supplies the snapshot as defined in decision 6 and must set the global work plane before
  reading points; S4 executes the plan, writes the journal at the points in decision 3, writes
  `LOT` first when tagging, and adds the `update` before-image to the journal schema.
- New To verify items on the test model: UDA filters on parts return exactly the tagged objects;
  `GetIdentifierByGUID` distinguishes "not found" from errors; points come back in global mm; profile
  and material strings come back exactly as written; the UDA string length limit holds a 64-character
  `SPEC_ID`; tagging before `Insert` works (it would close the intent window of decision 3).
- Accepted limits: a journal edited by hand is trusted like a forged receipt (ADR-0010 A1); a crash
  between `Insert` and the `inserted` write leaves an intent the engineer must resolve by hand.
- Python validates journals (`harness validate run-journal`) and reads them for lot reports.
