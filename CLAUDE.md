@AGENTS.md

## Claude Code specifics

- Run only in a **local** session on the Tekla machine. The `SessionStart` hook prints an
  environment report; if it says the session is remote or `tekla-cli` is missing, tell the
  engineer before doing anything that touches Tekla.
- Reply language is set by `"language": "vietnamese"` in `.claude/settings.json`.
- Subagents live in `.claude/agents/`. Delegate by role; the main session is the orchestrator
  and never calls `tekla-cli` write commands itself (the guard hook will deny it).
- Skills: which one to use when is the table in `AGENTS.md` § Skills. Plugin skills are
  enabled in `.claude/settings.json`; global skills (`delegating-work`, plus `handoff`,
  `grilling`, `grill-me`, `writing-for-agents`, `diagnosing-bugs`, `to-questionnaire`,
  `research` from mattpocock/skills) live in `~/.claude/skills/` per machine, so a new
  machine — the Tekla machine included — must install them separately.
- Before claiming a Claude Code feature works a certain way, check the docs
  (https://code.claude.com/docs) — features change between versions.
- Slash commands (`/new-project`, `/approve`, …) arrive in Step 5. Until then, do not invent them.
