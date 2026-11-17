# EVAL-5 brief: report writer and planner (fresh agents)

Same setup as the runner (`REPO`, `SKILLS` = `$REPO/.claude/skills/` rev 6 with approval SIMULATED,
`PROJECT`, harness via `uv run --project $REPO harness ...`, `export TMPDIR=$PROJECT/tmp`). Follow the skill
LITERALLY; when a line is unclear, wrong or missing, do the most plausible thing and log it in your
friction log (Critical / Major / Minor + skill file:line). Read only `$PROJECT`, `$REPO` and paths given
here; never open `dwg-lab/proposals/skills/eval3/`, `dwg-lab/proposals/skills/eval4/`, `dwg-lab/proposals/skills/eval5/`, `projects/_evals/`, `dwg-lab/proposals/skills/EVAL-*.md`, `REVIEW-*.md`, any answer key, any other arm, or any judge file.
Do NOT call the Skill tool and do not read `.claude/skills/` of any other checkout (an older skill
revision may be loaded elsewhere); read SKILL.md files from `$SKILLS` only. Take your role from
`$REPO/.claude/agents/<role>.md`. Every engineer answer in this project was given by a simulator (`--role simulated`); treat that exactly as
the skills say.

## Report writer (`doc-reader` role)

Skill: `drawing-analysis-report`, Part A only. Write `$PROJECT/01-analysis.md`. You raise no questions
(the skill says where gaps go). Friction log: `$PROJECT/friction-report.md`. Command log: append to
`$PROJECT/cmdlog-report.txt`.

## Planner (`planner` role, see `$REPO/.claude/agents/planner.md`)

Skill: `tekla-conversion-plan`, gate 1 only. Write `$PROJECT/02-plan.md`. You never open a gate and
never claim it is open or ready unless `harness status` says `ready_for_gate1: true`. No Tekla command
that writes; read-only Tekla commands are not available on this machine (say so if the skill asks for
them). Friction log: `$PROJECT/friction-plan.md`. Command log: `$PROJECT/cmdlog-plan.txt`.

Return (both): the file you wrote, its line count, what you could not support with an artefact, and
friction counts by severity.

Keep every helper file (scripts, tables, scratch output) under `$PROJECT/tmp/`; write nothing
elsewhere outside `$PROJECT`.
