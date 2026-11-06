# `tekla-cli` contract (draft, implemented in Step 3)

`tekla-cli` is the only path from an agent to a Tekla model. It is a thin, deterministic
.NET Framework 4.8 executable over `TeklaCore`. This document fixes its interface now so
the guard hook, permissions and schemas can rely on it.

## Conventions

- Input: arguments plus an optional JSON file (`--spec <path>`). Output: one JSON object on
  stdout. Diagnostics on stderr.
- Exit codes: `0` ok · `1` validation failure (nothing written) · `2` usage error ·
  `3` environment error (Tekla not running, wrong model, wrong version) · `4` Tekla API error
  (rolled back) · `5` refused by safety rule.
- Every command prints `tekla_version`, `model_path`, and `run_id` in its JSON output.
- The subcommand is always the first argument; options follow it
  (`tekla-cli build --lot 3 …`, never `tekla-cli --lot 3 build`). The guard hook relies on this
  and treats anything else as a write.

## Subcommands

| Subcommand | Class | Purpose |
|---|---|---|
| `info` | read | Tekla version, open model, catalogs available |
| `validate` | read | Check profiles/materials/components in a spec exist in the catalogs |
| `query` | read | Objects by `LOT` / `RUN_ID` / `SPEC_ID` / GUID |
| `selected` | read | Objects currently selected in the Tekla UI |
| `export` | read | CSV report + IFC of a lot or run (writes files, not the model) |
| `build` | **write** | Create all objects of one lot from `spec.json`, tag them, one commit |
| `update` | **write** | Modify objects of one lot from a corrected spec |
| `rollback` | **write** | Delete all objects of a `RUN_ID` (or restore the lot backup) |

Any subcommand not listed as **read** is treated as a write by the guard hook (fail closed).
Adding a read subcommand requires updating `READ_SUBCOMMANDS` in
`.claude/hooks/guard_tekla_write.py` and its tests.

## Safety rules enforced inside `tekla-cli` (write commands)

1. Refuse unless the open model path matches the project's declared working copy, and that
   path differs from the declared original.
2. Refuse unless a backup for this lot exists or is created first.
3. Refuse unless `--lot`, `--run-id` and a schema-valid `--spec` are given.
4. Tag every created or modified object with UDAs `LOT`, `RUN_ID`, `SPEC_ID`.
5. Commit once per command; on any API error, roll back and exit `4`.

## Open questions

- Exact Tekla version + SP (decides NuGet `Tekla.Structures.*` version).
- UDA names: confirm `LOT`, `RUN_ID`, `SPEC_ID` do not clash with the company environment.
