# Security and safety

## Reporting

Report a security or model-safety issue privately to the repository owner. Do not open a public issue.

## What counts as a safety issue

- Any path by which an agent other than `builder` can write to a Tekla model.
- Any `tekla-cli` write that skips backup or the `LOT` / `RUN_ID` / `SPEC_ID` tags.
- A gate that opens without an explicit engineer action.
- Client data (drawings, models, reports) committed to git or sent to an unapproved service.
- Secrets (licence keys, API tokens) in code, logs, or agent context.

## Defences in this repo

| Layer | Mechanism |
|---|---|
| Hard block | `PreToolUse` hook `guard_tekla_write.py` (fails closed, `onFailure: block`) |
| Human check | `permissions.ask` on every `tekla-cli` write command |
| Tool scope | Each subagent's `tools` list in `.claude/agents/` |
| Data hygiene | `.gitignore` for `projects/`, models, drawings, `.env*` |
| Traceability | Mandatory object tags + per-lot backup + command log |

Prompt text in `AGENTS.md` / `CLAUDE.md` is guidance, not a control. Controls are code.
