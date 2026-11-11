# 0014. Context guard and session cleanup hooks

- Status: accepted (engineer decisions 2026-11-10; orchestrator design)
- Date: 2026-11-10
- Decided by: engineer for the thresholds, the no-compaction choice and the cleanup scope;
  orchestrator for the mechanics

## Context

Long sessions cost more and work worse. Every turn re-reads the whole context, so a session's cost
grows roughly with the square of its length. The EVAL-4 orchestrator session reached 856k tokens.
Opus 5.5 and Sonnet 5.5 run a native 1M window in Claude Code. The docs put the default
auto-compact near 967k. Observed behaviour differs: the main chain of one 2.1.319 session
auto-compacted at 242k, 353k and 489k with `autoCompactWindow` unset in both the user and the
project settings. So the real trigger is undocumented, and compaction can land before any
threshold below.

Quality also drops with length. Anthropic states it in words ("context rot"; "response quality
degrades as a conversation grows"), but no primary source gives a threshold for any 5.x model. The
only Claude data split by length is for Opus 4.6. Its MRCR v2 8-needle score holds at 91.9 in the
(128k, 256k] bucket and falls to 78.3 at (524k, 1M]. Nothing measures 256k to 524k. Sources and
gaps: [`docs/research/context-length-quality.md`](../research/context-length-quality.md).

Facts from the Claude Code docs (hooks, statusline, model-config; read 2026-11-10, v2.1.322):

- No hook can run `/clear` or `/compact`, or start a session.
- Hook input carries `transcript_path` but no token count.
- `Stop` can block once with a `reason` that Claude acts on; `stop_hook_active` marks a stop that
  is already continuing.
- `UserPromptSubmit` can add `additionalContext`.
- Hooks also run inside subagents, where `agent_id` is set.
- The statusline input does carry `context_window.*`, but a statusline only runs in the
  interactive UI.

The repository also gathers stale state. On 2026-11-10 it held 25 worktrees and 47 local branches;
22 of the worktrees were clean and already merged.

## Decision

1. **Thresholds** (engineer defaults, not measurements, the same for every model):
   - warn at **200,000** tokens;
   - handoff at **250,000** tokens.

   `autoCompactWindow` stays at its default. The engineer rejected compaction as the refresh
   path because the summary loses real context and carries no provenance.
2. **Refresh path:** at the handoff limit, Claude updates the active `.handoff/<topic>.md` and its
   `INDEX.md` row, then asks the engineer to type `/clear`. The existing `handoff_reminder` hook
   then offers the topic in the fresh session.

   This is an explicit exception to "user-invoked skills: suggest them, do not imitate them". The
   exception covers only the repository's `.handoff/` files; Claude still does not run `/handoff`.
3. **`context_guard.py`** is registered for `UserPromptSubmit` and `Stop`.
   - **Token count:** the last main-chain assistant entry in `transcript_path` gives
     `input_tokens + cache_creation_input_tokens + cache_read_input_tokens`. This is the same sum
     the statusline documents for `used_percentage`.
   - **`UserPromptSubmit`:** at warn or above, it injects a short note and shows a
     `systemMessage`. It never blocks the engineer.
   - **`Stop`:** at the handoff limit, it blocks once per session. A marker file in the system
     temp directory, named by the validated `session_id`, prevents repeats. The marker is cleared
     when usage drops below warn.
   - **Subagents** (`agent_id` set) are skipped. The `executor` agent keeps its own
     `autoCompactWindow` cap.
4. **`session_cleanup.py`** is registered for `SessionStart` with the `startup|clear` matcher.
   - **Worktrees:** a worktree is removed (`git worktree remove`, never `--force`) only when every
     condition below holds:
     - it is not the main worktree, the session's own directory (stdin `cwd`, process cwd or
       `CLAUDE_PROJECT_DIR`) or the cwd of a live Claude session (best effort, from the
       undocumented `~/.claude/sessions/*.json`; this check can only add keeps);
     - it is not locked or prunable, and `git worktree prune` is never run;
     - `git status --porcelain --ignored` shows only regenerable caches;
     - its HEAD is merged into `master`, `origin/master` or a `feat/*` branch other than its own;
     - it has been idle for 24 hours;
     - no `.handoff/*.md` file names it.
   - **Branches:** a local branch is deleted only with `git branch -d`, only when it is merged into
     `master`, and only when it is not checked out, not `feat/*` and not named in a handoff file.
   - Every action is logged to `.git/claude-session-cleanup.jsonl`. Anything else that looks stale
     is listed for the engineer, never removed.
5. **`statusline.py`** is registered as `statusLine` (main session) and as `subagentStatusLine`
   with `--subagents`.
   - The main line shows `[worktree]` (`[main]` in the main checkout), the model, the effort, the
     context tokens, the session cost, the 5-hour and 7-day rate-limit shares (`limit 8%|47%`,
     yellow from 70%, red from 90%) and the branch. The subagent rows show each agent's type (one
     colour per role), model, effort, tokens, the model's input list price per million tokens and
     the task. The cost is Claude Code's list-price estimate, not the bill; the row price is not a
     running cost because the panel sends no per-task spend.
   - Colour gives freshness: green below warn, yellow from warn, red from handoff. The thresholds
     are loaded from `context_guard.py`, the single source.
   - The main token count is the documented `context_window.total_input_tokens`.
6. **Prefix trimming:** the six claude.ai-synced plugins that do not bear on this repository
   (`sales`, `marketing`, `finance`, `operations`, `product-management`,
   `cowork-plugin-management`) are set to `"<name>@synced": false` in the project
   `enabledPlugins`. Every listed skill is in the prompt on every turn. Prompt caching itself
   already works: the EVAL-4 orchestrator session read 33M tokens from cache against 0.7M written.
   The cost driver is context length, not cache misses.
7. All three scripts are stdlib only, never block a session start, and always exit 0. A failure is
   reported on stderr and skips the check; it does not crash the session.

## Consequences

- At 250k and above, every prompt carries "start no new work". The session then idles until the
  engineer types `/clear`, so cost per turn stays bounded. Background agents still running at
  that point are recorded in the handoff, and Claude waits for them before asking for `/clear`.
- Compaction can still happen earlier on Claude Code's own trigger (see Context). After a
  compaction the guard counts from the `compact_boundary` line, which gives the post-compaction
  size. A re-injection of the handoff file after compaction is not part of this decision.
- **Undocumented dependency:** the transcript JSONL format (`type`, `isSidechain`,
  `message.usage`) is not documented. A format change makes the guard fall silent, not wrong: no
  count means no warning. It is checked against Claude Code 2.1.322. Re-check after upgrades with
  `tests/test_context_guard.py`, which uses synthetic transcripts.
- The thresholds are a convention until measured. The measurement plan is in the research note
  (fill levels 50k–800k, at least 5 trials per cell, on the benchmark). Change the constants only
  after that measurement or by engineer decision.
- Cleanup errs toward keeping. Worktrees of an unmerged integration branch (for example
  `feat/tool-wave-4`) are removed when idle and merged into that branch. Their branches stay until
  the integration branch reaches `master`, because `git branch -d` refuses them.
- Stale `/tmp` scratchpads and `.handoff/` rows are out of scope: the OS clears the first, and the
  engineer confirms the second.
