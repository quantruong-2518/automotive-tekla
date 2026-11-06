# projects/

One folder per project run, created by `/new-project` (Step 5). Everything here except this
README is git-ignored: drawings, models and reports are client data.

```
projects/<project-id>/
  input/                 drawings as received (read-only after inventory)
  project-state.json     orchestrator state (schemas/project-state.schema.json)
  read-log.json          every read attempt and fallback (schemas/read-log.schema.json)
  00-inventory.csv … 05-sequence.md
  questions.md
  lots/<n>/spec.json     (schemas/spec.schema.json)
  lots/<n>/issues.json
  lots/<n>/report.md
  phase-report.md
```
