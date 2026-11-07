# 0007. tekla-cli: stop-and-resume on failure, macro backup, build-time config, per-model UDAs

- Status: accepted
- Date: 2026-11-07
- Decided by: engineer (question round on 2026-11-07, after `tekla/api-notes.md`)

## Context

The Open API research (`tekla/api-notes.md`, doc-sourced, not run-verified) found that
`docs/tekla-cli-contract.md` promises things the API does not provide, and that the write
guard has a gap:

- There is no transaction, undo or rollback call; `Model.CommitChanges(string)` is only a user
  undo step.
- There is no SaveAs or backup call on `ModelHandler` (2024 to 2026). The UI has
  *File > Save as > Save and create backup copy*, which keeps GUIDs.
- Since 2024 Tekla assemblies are not in the GAC. A stand-alone exe needs a patched
  `exe.config` (`codeBase` + `bindingRedirect`) to connect.
- UDAs must be defined in an `objects.inp`; plain `attribute` values are copied with a part when
  a user copies it in the UI, `unique_attribute` values are not.
- The guard only recognises the executable name `tekla-cli(.exe)` (RTI-0006).

## Decision

1. **Failure: stop, keep, resume. No automatic delete.** On any API error during `build` or
   `update`, `tekla-cli` stops, keeps every object already created or modified, writes the run
   journal (GUID and `SPEC_ID` of each object done so far, the failing item and the error), and
   exits `4`. It never deletes objects to clean up.
2. **Retry resumes.** Re-running the same lot with the same `RUN_ID` skips every spec item whose
   `SPEC_ID` already exists in the model for that lot and run, and builds only the missing ones.
   It never creates a duplicate. If an existing object differs from its spec item, it stops
   (exit `1`) and asks the engineer. "Differs" (engineer, 2026-11-07): a start or end point more
   than **0.1 mm** from the spec, or any difference in profile or material (compared exactly).
3. **Backup by macro.** Before writing, `tekla-cli` creates the lot backup itself by running a
   Tekla macro that performs *Save and create backup copy* (`Operation.RunMacro`), then checks
   that a new backup folder exists. If the macro fails or no new backup appears, it refuses to
   write (exit `5`). The macro route is unverified: it must pass on the 2024 test model
   (`tekla/api-notes.md`, To verify #13) before the first real lot.
4. **Config at build time.** The CLI is built with `TSAppConfigPatcherTask` (2.1.x),
   `TeklaVersion` set for every configuration (not Debug only), so the build output carries the
   patched `tekla-cli.exe.config`. A machine with Tekla installed elsewhere needs a rebuild.
5. **UDAs per model, unique.** The repo keeps a small `objects.inp` holding only `LOT`, `RUN_ID`,
   `SPEC_ID` as `unique_attribute`, type `string`, `special_flag no` (no effect on numbering).
   It is copied into the test model and each working-copy model folder; the company (firm)
   `objects.inp` is not touched. `info` and every write command check with
   `CatalogHandler.GetUserPropertyItems()` that all three are defined, unique and not affecting
   numbering, else exit `3`.
6. **Guard: two layers (RTI-0006).** (a) Contract: the executable is named `tekla-cli.exe`
   (`AssemblyName` `tekla-cli`) and agents never invoke it through `dotnet run` or `dotnet exec`.
   (b) Hook: `TeklaCli(.exe)` and `dotnet run|exec` aimed at the CLI project count as invocations,
   with regression tests.

## Consequences

- Contract safety rule 5 changes from "roll back and exit 4" to "stop, keep, journal, exit 4;
  resume on retry". `rollback --run-id` stays a deliberate, engineer-approved command, not an
  automatic step.
- A failed lot leaves a partial lot in the working-copy model until the engineer retries or
  rolls back. Reports must show the partial state from the journal.
- `RUN_ID` is reused on retry, so one run can span several invocations; the journal records each.
- `SPEC_ID` must stay unique within a lot (already checked by `check_spec`).
- Still to verify on the test model: whether objects inserted before a crash without
  `CommitChanges` persist (To verify #9), and the backup macro (To verify #13).
