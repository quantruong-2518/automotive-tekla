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
   `tagged`). Within one invocation there is one entry per `SPEC_ID`, updated in place
   (`inserting` → `inserted` → `tagged`); two entries for one `SPEC_ID` in one invocation make the
   journal malformed.
3. **Write policy.** The whole file is rewritten atomically (temporary file in the same folder,
   flushed to disk, then `File.Replace` **with a backup file**, deleted only after success; the
   temporary file is never deleted while the journal is missing; up to 3 retries 100 ms apart for a
   locked target). A missing journal next to a leftover temporary or backup file for that `RUN_ID`
   refuses (exit `5`): a write may have been interrupted. Writes happen at invocation
   start (`running`), **before each `Insert`** (intent: `state: inserting`, no GUID), after it
   (`inserted` + GUID), after tagging (`tagged`), and at the end. If a journal write fails the run
   stops before the next `Insert`; an object whose GUID is known is still tagged, every GUID made is
   printed in the stdout JSON, and the exit code is `4`.
4. **One writer per model.** A write command holds an exclusive lock for its whole run, keyed on the
   normalised working-copy path (named mutex in the `Global\` namespace, so other Windows sessions
   are covered; Tekla serves only the first session, so every CLI on the machine talks to the same
   model). A held lock, or a mutex that cannot be created or opened, refuses (exit `3`). The lock is
   released on the thread that took it; a release from another thread throws and leaves the lock held
   (closing the handle there would destroy the named mutex on Windows while its owner still writes). After taking the lock, the CLI marks every invocation still
   `running` as `abandoned` (it crashed) **before** planning; the planner refuses (exit `5`) a
   journal that still has a `running` invocation.
5. **What refuses before planning** (nothing written):
   - journal exists but is not strict JSON or not schema-shaped → `5`; journal I/O error → `3`;
   - journal `spec_sha256` ≠ the receipt's → `5` (a changed spec is `update` in S4, or `rollback` of
     this run and a build with a new `RUN_ID`, decided by the engineer);
   - journal `model_path` (header or any invocation) ≠ the open working copy (same comparison as
     safety rule 1) → `5`;
   - the journal header's `project_id`, `lot` or `run_id` differs from this run → `5`;
   - the run has any `rollback` invocation, whatever its outcome → `5` (a partial rollback is never
     followed by a resume that rebuilds what the engineer asked to delete);
   - no journal, but objects tagged with this lot and `RUN_ID` exist → `5` (untagged leftovers
     cannot be ruled out without it).
6. **Snapshot** (supplied by S2, global coordinates in mm): the union of objects with `LOT` = lot,
   `RUN_ID` = run, `SPEC_ID` in the spec's ids, and every journal GUID. Per object: GUID, which of
   those lookups found it, kind (`beam`/`column`/... in the spec's `type` vocabulary, or `other`),
   each of the three tags as value / absent / unreadable, start, end, profile, material, rotation,
   class, name. Per journal GUID: present, absent (only when the lookup of that very GUID says "not
   found") or error. Refusals: an unreadable tag or a GUID lookup error → `3`/`4`; lookups and tags
   that disagree in **either direction** → `3` (the filter cannot be trusted): an object carrying
   this `LOT`, this `RUN_ID` or a `SPEC_ID` of the spec that its lookup did not return, an object a
   lookup returned whose tag does not hold that value, an object no lookup returned, or a
   journal-GUID flag that disagrees with the journal.
7. **"Differs"** (ADR-0007 §2, widened by the engineer on 2026-11-08): an object matches its spec
   item only when the start and the end are each within 0.1 mm (Euclidean, `d <= 0.1 + 1e-6`: the
   1e-6 mm absorbs binary rounding, so 6000 against 6000.1 matches; a non-finite point never
   matches; start with start, end with end), profile and material are equal (ordinal),
   the kind equals the spec `type`, the rotation is within 0.01° (+ 1e-9° rounding allowance) modulo 360 (absent in the spec =
   0), and the class is equal when the spec gives one. A different name is reported, not a conflict.
8. **Plan per spec member** — exactly one action. A plan is executable only when there is no
   refusal and no conflict; the plan type enforces it (no executable actions are exposed
   otherwise), so S4 cannot write part of a lot while the planner reported a conflict:
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
   conflicts are returned together. Implementation choices, all fail-closed: with several journal
   GUIDs for one `SPEC_ID` (it was recreated) the latest one is the target, an older one still
   present is a conflict; an object carrying this `SPEC_ID` under another `RUN_ID` is a conflict in
   any lot; an object of another run in this lot is `unclassified` even if its `SPEC_ID` is not in
   the spec; a tagged matching object the journal never recorded is skipped (a journal write may
   have failed after its GUID was printed, decision 3).

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
