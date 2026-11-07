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
4. **The model-path guard fails closed and does not use `System.IO.Path`** (restated in the
   Amendment: text checks are necessary but not sufficient; S1a adds file identity). It compares Windows
   paths with its own normaliser (separators, case, trailing separator, `.` segments). It allows
   a write only when the open path is provably the working copy and provably not the original.
   Anything it cannot prove (`..`, UNC vs drive letter, `\\?\` prefixes, 8.3 short names,
   relative paths) refuses. `System.IO.Path` behaves differently on Linux, where the tests run.
5. **Mutation testing** with Stryker.NET from a local tool manifest (`dotnet stryker`), on
   `TeklaCore`.
6. **Tool names and the guard.** Shell commands that name the CLI project after a non-inert
   command are denied by the guard hook (RTI-0006); project files are created with editor tools,
   and builds use `dotnet build` (inert). The guard is not loosened.

## Amendment (2026-11-07, independent review of slice S1)

An Opus review found, and reproduced on NTFS (Windows build 26200) and in the guard under
.NET Framework 4.8 and .NET 10:

- **Text compare missed NTFS equal names.** "NFKC then upper-case" allowed e.g. `Pi`+U+0307
  vs `PI`+U+0307, which NTFS treats as one folder (it upper-cases each UTF-16 unit and does not
  normalise). Fixed in S1: names are "possibly equal" if they match by per-unit upper-casing
  (as NTFS), or after NFKC, or after NFKD. Acceptance: 0 false allows over all 973 Windows
  upcase mappings (`RtlUpcaseUnicodeChar`) on .NET Framework 4.8.
- **Text cannot prove two paths are different folders.** `subst` drives, junctions, symlinks,
  volume mount points and two mapped drives on one share are aliases the text guard allows.
  §4 is therefore restated:
  1. The text guard (S1, `TeklaCore`) is necessary, not sufficient.
  2. Slice **S1a** adds a file-identity check on Windows: volume serial number + file ID
     (`GetFileInformationByHandleEx`, `FILE_ID_INFO`, which also covers ReFS) of the open model,
     the working copy, the original and their parent folders. A write needs: open = working
     copy by identity; working copy, open and original pairwise different by identity and not
     ancestors of one another; any path whose identity cannot be read refuses.
  3. No write command (slice S4) ships before S1a passes on Windows.
  4. UNC paths stay refused by the text guard until S1a exists; S1a may then allow them.
- Exit codes for rule 1: another model open is "wrong model" (3); every other refusal is 5.
  The contract states this split.
- Known limits, accepted: a legitimate folder name such as `Rev~2` is refused (it looks like
  an 8.3 short name); short names set by hand without `~N` are left to S1a; under .NET
  invariant-globalization mode normalisation is not applied (not used on net48, where the CLI
  runs). The path is checked once per command; S4 re-checks it before `CommitChanges`.

## Amendment 2 (2026-11-07, slice S1a and its independent review)

Built from [`docs/research/windows-file-identity.md`](../research/windows-file-identity.md) and
checked on real Windows (NTFS, .NET Framework 4.8). Rule 1 now allows a write only when all hold:

1. The path-text guard passes (S1).
2. Open model, working copy and original each resolve (`CreateFileW` with
   `FILE_FLAG_BACKUP_SEMANTICS`, following reparse points) to a 128-bit `FILE_ID_INFO` that is not
   all zeros or all ones, on NTFS or ReFS, on a fixed, removable or RAM drive.
3. Open = working copy by identity; working copy ≠ original by identity.
4. A folder whose final path is UNC cannot be proven different, so **both folders must be on
   local drives**. An original on a server share is refused (open question for the engineer).
5. No ancestor of either folder — from its final path and from its typed path — is the other.
6. The working copy's typed path is its real path (final path equal ignoring case): subst and
   mapped letters are per logon session, and Tekla reports the path from its own session. This
   also refuses a copy typed through a junction (global, not per session): deliberate, so the
   declared copy path is always the plain path. The original's typed drive letter must be its
   real drive (second review: a subst letter may name another folder in another session);
   junctions on the original's own drive stay allowed.
7. Neither folder contains a reparse point (junction, symlink, mount point, and also cloud-sync
   placeholders such as OneDrive Files-On-Demand: a model in a synced folder is refused), and
   the working copy contains no file with more than one hard link (walk without following links). Reason: the review showed
   `robocopy /E /SJ` copying a junction that still points into the original, and a write through
   it landing in the original.

Research steps not taken, with reason: no 64-bit file-index fallback (it can never prove
"different", so it could only lead to the same refusal); no `VOLUME_NAME_GUID` retry (volumes
without a drive letter are refused); handles are not held from check to write (S4 re-runs the
check right before `CommitChanges`; a time-of-check gap remains and cannot be removed by this
check); a third-party driver that reports "NTFS" on a local-looking letter is trusted (unverified).

Not verified (needs admin rights or hardware not available): directory symlinks, mount points,
ReFS, FAT/exFAT, volume shadow copies, Tekla multi-user models.

## Consequences

- `tekla/README.md` layout is replaced by the table above.
- Spec validation needs one source of truth (the Python `check_spec` exists); decided before
  slice S1b. Any JSON library choice waits for a check of the `TSAppConfigPatcherTask` redirect
  list, so a runtime redirect cannot swap our dependency version.
- Artefact schemas (run journal, CLI output) are added to `schemas/` with `SCHEMA_NAMES`
  entries in a later slice.
