# Roadmap

Agreed order: drawing reading first, Tekla second. A step is done when its exit criteria
pass, not when its code exists.

| # | Step | Needs | Exit criteria |
|---|---|---|---|
| **0** | **Foundation** — repo, `AGENTS.md`/`CLAUDE.md`, schemas v0, guard hooks, CI | nothing | CI green; guard hook tests pass; `harness env-check` runs on the Tekla machine |
| 1 | File reading + fallback (skill tier 1, readers, `read-log`) | synthetic DXF + public files | each fallback path covered by a test; no silent failure |
| 2 | Expert reading (tier 2, accuracy measured) | **≥2 sets exported from Tekla + ≥1 past project** | grid/level/profile accuracy reported on the benchmark set |
| 3 | Touch Tekla: `tekla-api-reference`, `TeklaCore` + `tekla-cli` | exact Tekla version + SP, empty test model | contract in `tekla-cli-contract.md` implemented and tested |
| 4 | Build and verify loop: builder, verifier, hooks | spec from Step 2 + answer model | build→verify→rollback round-trip on a test model |
| 5 | Full process: slash commands, gates | one complete set | end-to-end run with all gates |
| 6 | Improvement loop: `/feedback`, RTI, `/improve`, benchmark | **fixed benchmark of 3–5 projects** | a release tag carries a benchmark score |
| 7 | Extend: connections, numbering, clash, shop-drawing QA, Agent SDK | project with connections | — |

## Step 0 — current state

- [x] Repository layout, licence, contribution rules, ADRs
- [x] Claude Code config: language, permissions, plugins
- [x] Subagent definitions (behaviour only; their scripts arrive in later steps)
- [x] `guard_tekla_write.py`, `session_env_check.py` + tests
- [x] Schemas v0 + examples + `harness validate`
- [ ] Run `scripts/setup.ps1` on the Tekla machine and confirm `harness env-check`
  (still open; the engineer decided on 2026-11-06 to start Step 1 in parallel, since Step 1
  does not touch Tekla)
- [x] Engineer approves the flow-review proposals: RTI-0001…0004 approved 2026-11-06

## Step 1 — plan (DWG first, by engineer decision)

Each slice: tests first, then one commit.

1. S1 `detect_input` + sha256 + read-log builder validated against the schema (RTI-0001 hashing).
2. S2 `dwg_to_dxf`: ODA → LibreDWG fallback chain ([ADR-0005](decisions/0005-dwg-converter-chain.md)).
   - S2b read cache for conversions ([ADR-0006](decisions/0006-memory-layers.md); design in
     ADR-0008 from `docs/research/read-cache.md`).
3. S3 minimal `read_dxf` + RTI-0002 checks (`$INSUNITS`, overridden dimension text, xrefs, scales).
4. S4 TCVN3/VNI → Unicode (RTI-0004).
5. Then title-block inventory and grids/levels (RTI-0001, RTI-0003), and the tier-1 skill last.

## Step 3 — plan (started in parallel with Step 1, by engineer decision)

The engineer decided on 2026-11-07 to start Step 3 before Steps 1–2 are done: the Tekla-free
part is written and tested on the development machine (WSL, .NET SDK in `~/.dotnet`); anything
that runs against Tekla waits for the Tekla machine. Layout and build/test rules:
[ADR-0009](decisions/0009-tekla-dotnet-layout.md). Behaviour: [ADR-0007](decisions/0007-tekla-cli-failure-backup-and-tags.md),
[`tekla-cli-contract.md`](tekla-cli-contract.md). Each slice: tests first (proved red on a stub),
mutation testing, independent review, then one commit.

| Slice | Content | Runs where |
|---|---|---|
| S1 | Solution scaffold; `TeklaCore` exit codes and model-path text guard (contract rule 1); .NET CI job | dev machine + CI |
| S1a | File-identity check for rule 1 (volume serial + file ID; catches `subst`, junctions, mapped drives, links inside the folders). Blocks S4 | Windows (CI + local) |
| S1b | Spec loading: Python validates and writes a receipt, C# checks the receipt ([ADR-0010](decisions/0010-spec-validation-receipt.md)) | dev machine + CI |
| S1c | Run journal (schema) and resume planner (contract rule 6) | dev machine + CI |
| S2 | `TeklaAdapter` over the Open API (compiles here, runs on the Tekla machine) | compile here |
| S3 | `tekla-cli` read commands: `info`, `validate`, `query`, `selected` | Tekla machine to run |
| S4 | Write commands, backup macro, tag `objects.inp` | Tekla machine to run |
| S5 | Integration tests on the test model (RTI-0007); the 19 checks in `tekla/api-notes.md` | Tekla machine only |

Step 3 is done only when S5 passes on the Tekla version the engineer confirms (see below).

**Paused after S1c (engineer, 2026-11-09).** S1–S1c and RTI-0008/0009 are merged. S2–S5 depend on
the exact Tekla version, so they wait until Steps 1 and 2 are done. At that point, ask the
engineer for the Tekla version and configuration, record it here and in an ADR-0009 amendment
(NuGet pin, `TSAppConfigPatcherTask`, contract, `tekla/api-notes.md` deltas), then start S2.
Building once for the confirmed version is cheaper than building for a guess.

## Open before later steps

- Tekla version: first given as **2024 Diamond** (engineer, 2026-11-06); on 2026-11-09 the
  engineer reported the company uses **2026 Diamond**. ADR-0009, the contract and
  `tekla/api-notes.md` still pin `Tekla.Structures.*` 2024.0.4; they change only when the version
  is confirmed at the restart of Step 3 (above). Known 2026 deltas: Model package
  netstandard2.0-only, x64-only DLLs (projects are already x64), IFC2x3 export in the API.
  Tekla machine for S5: the Windows host of the development WSL (engineer, 2026-11-07); no Tekla
  is installed there yet, and it needs the .NET SDK and an empty test model.
- Resume "differs" tolerance for contract rule 6: **0.1 mm** on start and end points; profile
  and material compared exactly (engineer, 2026-11-07; ADR-0007).
- Original models live on local drives, so the local-only rule of ADR-0009 Amendment 2 stays
  (engineer, 2026-11-07).
- Benchmark set with answer models — before Step 2.
- Licence terms of ODA File Converter for commercial use — the engineer chose ODA with a
  LibreDWG fallback (ADR-0005); written licence confirmation still needed before a client run.
- PyMuPDF licence (AGPL-3 or commercial) — decide before the PDF slice.
- 1–2 sample DWG files that are not client data — needed to prove the DWG path for real.
