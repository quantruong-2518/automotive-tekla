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
     ADR-0007 from `docs/research/read-cache.md`).
3. S3 minimal `read_dxf` + RTI-0002 checks (`$INSUNITS`, overridden dimension text, xrefs, scales).
4. S4 TCVN3/VNI → Unicode (RTI-0004).
5. Then title-block inventory and grids/levels (RTI-0001, RTI-0003), and the tier-1 skill last.

## Open before later steps

- Exact Tekla version (with SP) — before Step 3.
- Benchmark set with answer models — before Step 2.
- Licence terms of ODA File Converter for commercial use — the engineer chose ODA with a
  LibreDWG fallback (ADR-0005); written licence confirmation still needed before a client run.
- PyMuPDF licence (AGPL-3 or commercial) — decide before the PDF slice.
- 1–2 sample DWG files that are not client data — needed to prove the DWG path for real.
