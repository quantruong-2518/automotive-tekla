# Benchmark

Every harness change is judged against a fixed set of 3–5 past projects that each have an
answer model. Data lives in `benchmark/data/` (git-ignored) or on a shared drive.

## Layout of one case

```
benchmark/data/<case-id>/
  input/          drawings exactly as received
  answer/         answer model export (CSV + IFC) and answer spec where available
  case.json       metadata: source, Tekla version, scope, known traps
```

## Metrics (draft — fixed in Step 2)

| Stage | Metric |
|---|---|
| Reading | grid accuracy, level accuracy, profile recall/precision, % values with provenance |
| Questions | true questions raised, false questions raised |
| Build | member count match, position error (mm), profile/material match rate |
| Verify | issues found vs seeded defects |

A release (`vX.Y`) may not make any metric worse. The tag message records the scores.
