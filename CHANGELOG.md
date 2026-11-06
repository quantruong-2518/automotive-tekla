# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/).
Harness releases are tagged with their benchmark score (see `benchmark/README.md`).

## [Unreleased]

### Added
- Step 0 foundation: repository layout, `AGENTS.md` / `CLAUDE.md`, ADRs 0001–0004.
- Claude Code project config: Vietnamese replies, permission rules, plugins
  (Karpathy guidelines, pyright-lsp, csharp-lsp).
- Five subagent definitions: `doc-reader`, `planner`, `builder`, `verifier`, `reporter`.
- `guard_tekla_write.py` PreToolUse hook: only `builder` may run `tekla-cli` write commands;
  unknown subcommands are treated as writes (fail closed).
- `session_env_check.py` SessionStart hook: reports remote session, missing `tekla-cli`, Python version.
- JSON Schemas v0: `spec`, `project-state`, `read-log`, shared `common` (provenance, confidence).
- `tekla_harness` CLI: `harness validate`, `harness env-check`.
- CI on Windows and Ubuntu: ruff, pyright, pytest.
- Step 1 S1: `harness detect` (format from file bytes, DWG version, sha256, extension mismatch
  warnings) and the `readlog` builder (timed attempts, refuses silent failures, validates
  before writing).
- Step 1 S2: `harness dwg2dxf` — ODA File Converter, then LibreDWG `dwg2dxf` (ADR-0005).
  Success requires a DXF that ezdxf opens; fallback caps confidence at `medium`; no converter
  at all exits 3. Runtime dependency `ezdxf` (MIT) added: the DXF reader for all later slices.

### Fixed
- `guard_tekla_write.py` now exits 2 (the blocking code) on any internal error instead of
  relying on an undocumented `onFailure` setting; the setting was removed.
- `guard_tekla_write.py` no longer blocks commands that only mention `tekla-cli` as data
  (`cat`, `grep`, `git commit -m`), and no longer lets a read hide a later unparsed write.
- Write guard no longer denies commands that only name a file containing `tekla-cli`
  (e.g. `sed -n 1,40p docs/tekla-cli-contract.md`); RTI-0005.
- `workflow.md`: the lot loop is strictly sequential (lot n+1 waits for gate 4 of lot n).
- Added `PowerShell(...)` allow rules matching the existing `Bash(...)` ones.
