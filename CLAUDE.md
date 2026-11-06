@AGENTS.md

## Claude Code specifics

- Run only in a **local** session on the Tekla machine. The `SessionStart` hook prints an
  environment report; if it says the session is remote or `tekla-cli` is missing, tell the
  engineer before doing anything that touches Tekla.
- Reply language is set by `"language": "vietnamese"` in `.claude/settings.json`.
- Subagents live in `.claude/agents/`. Delegate by role; the main session is the orchestrator
  and never calls `tekla-cli` write commands itself (the guard hook will deny it).
- Plugins: use the `karpathy-guidelines` skill for any non-trivial code change.
- Before claiming a Claude Code feature works a certain way, check the docs
  (https://code.claude.com/docs) — features change between versions.
- Slash commands (`/new-project`, `/approve`, …) arrive in Step 5. Until then, do not invent them.
