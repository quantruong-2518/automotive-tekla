# `tekla-cli` contract (draft, implemented in Step 3)

`tekla-cli` is the only path from an agent to a Tekla model. It is a thin, deterministic
.NET Framework 4.8 executable over `TeklaCore`. This document fixes its interface now so
the guard hook, permissions and schemas can rely on it. Open API facts behind it, with sources:
[`tekla/api-notes.md`](../tekla/api-notes.md). Decisions: [ADR-0007](decisions/0007-tekla-cli-failure-backup-and-tags.md).

## Build and invocation

- Target: Tekla Structures **2024** (Diamond). NuGet `Tekla.Structures.Model` and
  `Tekla.Structures.Catalogs` **2024.0.4** (the pin does not depend on the service pack),
  `net48`, `x64`. Later versions (2025, 2026) are separate builds, each verified on its own.
- The executable is named **`tekla-cli.exe`** (`AssemblyName` `tekla-cli`). Agents call it only
  by that name, never through `dotnet run`, `dotnet exec` or `dotnet watch`. The guard hook
  denies those routes outside `builder` (RTI-0006).
- `tekla-cli.exe.config` (assembly `codeBase` + `bindingRedirect`, needed since Tekla 2024 is
  not in the GAC) is generated at build time by `TSAppConfigPatcherTask`, for every build
  configuration. A machine with Tekla installed in another folder needs a rebuild.

## Conventions

- Input: arguments plus an optional JSON file (`--spec <path>`). Output: one JSON object on
  stdout. Diagnostics on stderr.
- Exit codes: `0` ok · `1` validation failure (nothing written, or an existing object differs
  from its spec item on resume) · `2` usage error · `3` environment error (Tekla not running,
  wrong model, wrong version, tag UDAs not defined) · `4` Tekla API error (stopped; objects done
  so far are kept and listed in the run journal) · `5` refused by safety rule.
- Every command prints `tekla_version`, `model_path`, and `run_id` in its JSON output.
- The subcommand is always the first argument; options follow it
  (`tekla-cli build --lot 3 …`, never `tekla-cli --lot 3 build`). The guard hook relies on this
  and treats anything else as a write.

## Subcommands

| Subcommand | Class | Purpose |
|---|---|---|
| `info` | read | Tekla version, open model, catalogs available, tag UDA definitions |
| `validate` | read | Check profiles/materials/components in a spec exist in the catalogs |
| `query` | read | Objects by `LOT` / `RUN_ID` / `SPEC_ID` / GUID |
| `selected` | read | Objects currently selected in the Tekla UI |
| `export` | read | CSV + IFC of a lot or run (writes files, not the model; may change the UI selection, restores it afterwards) |
| `build` | **write** | Create the objects of one lot from `spec.json`, tag them, one commit; resumes a stopped run |
| `update` | **write** | Modify objects of one lot from a corrected spec |
| `rollback` | **write** | Delete all objects of a `RUN_ID`; run only on the engineer's request, never automatically |

Any subcommand not listed as **read** is treated as a write by the guard hook (fail closed).
Adding a read subcommand requires updating `READ_SUBCOMMANDS` in
`.claude/hooks/guard_tekla_write.py` and its tests.

## Safety rules enforced inside `tekla-cli` (write commands)

1. Refuse unless the open model path matches the project's declared working copy, and that
   path differs from the declared original. Check on every command: external applications
   talk only to the first Tekla session started. Both a path-text check and a file-identity
   check must prove it ([ADR-0009](decisions/0009-tekla-dotnet-layout.md), Amendments 1–2); any
   doubt refuses. Both folders must be on local NTFS/ReFS drives, the working copy must be
   declared and opened by its real path (no subst, junction or mapped letter), the original by
   its real drive letter, and neither folder may contain links or cloud-sync placeholders (nor
   the copy hard-linked files). Another model open is exit `3` (wrong
   model); any other refusal is exit `5`.
2. Before writing, create the lot backup with a Tekla macro that runs *Save and create backup
   copy*, then check that a new backup folder exists. Refuse (exit `5`) if either fails. The
   macro route must pass on the test model before the first real lot.
3. Refuse unless `--lot`, `--run-id` and a schema-valid `--spec` are given. "Schema-valid" means
   a validation receipt from `harness validate spec` whose SHA-256 matches the spec file
   ([ADR-0010](decisions/0010-spec-validation-receipt.md), Amendment 1). A missing or mismatched
   receipt, a spec the reader rejects, or a spec `lot` other than `--lot` exits `5`; missing
   arguments exit `2`; an existing spec or receipt that cannot be read exits `3`.
4. Tag every created or modified object with UDAs `LOT`, `RUN_ID`, `SPEC_ID`. Refuse (exit `3`)
   unless all three are defined in the model as `unique_attribute`, type `string`, not affecting
   numbering (the repo ships the `objects.inp` to copy into each model folder).
5. Commit once per command. On any API error: stop, keep every object already created or
   modified, write the run journal (GUID and `SPEC_ID` of each object done, the failing item,
   the error) and exit `4`. Never delete objects to clean up.
6. Resume: re-running `build` for the same lot and `RUN_ID` skips every spec item whose
   `SPEC_ID` already exists in that lot and run, and builds only the missing ones. If an existing
   object differs from its spec item, stop with exit `1` and ask the engineer. Never create a
   duplicate `SPEC_ID`. Journal, snapshot, matching rules ("differs" includes kind, rotation and
   class since 2026-11-08), lock and refusals: [ADR-0012](decisions/0012-run-journal-and-resume-planner.md).

## Open questions

- Whether objects inserted before a crash, without `CommitChanges`, persist
  (`tekla/api-notes.md`, To verify #9).
- The backup macro (To verify #13) and the backup folder location (`XS_MODEL_BACKUP_DIRECTORY`)
  on the Tekla machine.
- UDA names: among `objects.inp` files the model folder is read first, so its definitions win;
  but an existing model keeps the definitions stored in its `environment.db` (update them with
  *Diagnose and change attribute definitions*). Confirm on the test model that `LOT`, `RUN_ID`,
  `SPEC_ID` are not already used with another type.
