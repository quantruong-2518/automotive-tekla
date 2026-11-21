# tekla/ — TeklaCore and tekla-cli (Step 3)

Nothing here talks to Tekla yet. Layout and build/test rules: [ADR-0009](../docs/decisions/0009-tekla-dotnet-layout.md).

```
tekla/
  TeklaCore/                     netstandard2.0, no Tekla references: rules, journal, guards
  TeklaAdapter/                  net48 x64, Tekla.Structures.* 2026.0.3: Open API gateways
  TeklaCli/                      net48 x64 exe named tekla-cli: implements docs/tekla-cli-contract.md
  TeklaCore.Tests/               net10.0 + net48 unit tests, no Tekla
  TeklaCore.IntegrationTests/    net48, Tekla machine and test model only (RTI-0007)
  api-notes.md                   Open API facts, with version and source for each note
```

Target: Tekla Structures 2026 (Diamond), engineer decision Q1 of ADR-0015 (2026-11-11); the earlier 2024 target is history, kept in `api-notes.md`. The NuGet pin is documentary until `TeklaAdapter.csproj` exists. Running against Tekla still needs the Tekla machine and
an empty test model (roadmap, Step 3 S5).
