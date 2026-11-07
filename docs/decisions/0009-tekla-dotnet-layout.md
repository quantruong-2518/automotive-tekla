# 0009. .NET layout, build and test rules for the Tekla CLI

- Status: accepted
- Date: 2026-11-07
- Decided by: engineer (start Step 3 now, develop the Tekla-free part on WSL), layout proposed
  by the orchestrator
- Numbering: 0008 is taken by the read cache ADR on branch `feat/read-cache`, not yet merged.

## Context

`tekla/README.md` planned one `TeklaCore` library referencing the Tekla NuGet packages, a CLI
and one test project "against an empty test model". Since then:

- `tekla/api-notes.md` §7: nothing in the Open API is documented to work without a running
  Tekla, so only code with no Tekla reference can be unit-tested.
- RTI-0007: integration tests must be separate from unit tests and refuse any model that is not
  the declared test model.
- The development machine (WSL) has no Tekla and no Windows; the CLI ships on .NET Framework
  4.8, x64 (ADR-0007, contract).

## Decision

1. **Projects** under `tekla/`:

   | Project | Target | Tekla references | Holds |
   |---|---|---|---|
   | `TeklaCore` | `netstandard2.0` | none | exit codes, model-path guard, spec model and validation, run journal, resume planner, JSON output, gateway interfaces |
   | `TeklaAdapter` | `net48`, x64 | `Tekla.Structures.Model` + `.Catalogs` 2024.0.4 | gateway implementations over the Open API |
   | `TeklaCli` | `net48`, x64 exe, `AssemblyName` `tekla-cli` | via `TeklaAdapter`; `TSAppConfigPatcherTask` | argument parsing, wiring, exit |
   | `TeklaCore.Tests` | `net10.0;net48` | none | unit tests with in-memory fakes |
   | `TeklaCore.IntegrationTests` | `net48`, x64 | yes | RTI-0007 fixture; Tekla machine only |

   `TeklaCore` holds every rule that can be decided without Tekla, so the adapter stays thin.
2. **Where it builds and runs.** On WSL: .NET SDK 10 in `~/.dotnet`; every project builds (net48
   through the reference-assembly packs); only the `net10.0` tests run. CI `windows-latest` runs
   the tests on `net10.0` and `net48`; `ubuntu-latest` runs `net10.0`. Integration tests never
   run in CI.
3. **Numbers and text are culture-invariant.** Every parse and format uses
   `CultureInfo.InvariantCulture`; a test runs the core under `vi-VN` (comma decimal separator).
   Reason: the Tekla machine may use a Vietnamese locale, and number formatting also differs
   between .NET Framework and .NET.
4. **The model-path guard fails closed and does not use `System.IO.Path`.** It compares Windows
   paths with its own normaliser (separators, case, trailing separator, `.` segments). It allows
   a write only when the open path is provably the working copy and provably not the original.
   Anything it cannot prove (`..`, UNC vs drive letter, `\\?\` prefixes, 8.3 short names,
   relative paths) refuses. `System.IO.Path` behaves differently on Linux, where the tests run.
5. **Mutation testing** with Stryker.NET from a local tool manifest (`dotnet stryker`), on
   `TeklaCore`.
6. **Tool names and the guard.** Shell commands that name the CLI project after a non-inert
   command are denied by the guard hook (RTI-0006); project files are created with editor tools,
   and builds use `dotnet build` (inert). The guard is not loosened.

## Consequences

- `tekla/README.md` layout is replaced by the table above.
- Spec validation needs one source of truth (the Python `check_spec` exists); decided before
  slice S1b. Any JSON library choice waits for a check of the `TSAppConfigPatcherTask` redirect
  list, so a runtime redirect cannot swap our dependency version.
- Artefact schemas (run journal, CLI output) are added to `schemas/` with `SCHEMA_NAMES`
  entries in a later slice.
