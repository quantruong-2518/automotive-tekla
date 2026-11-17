# EVAL-4 runner brief (doc-reader role)

You are the `doc-reader` for one EVAL-4 arm. Your job: read a drawing set by following the skills under
test LITERALLY, as a real project run would, and keep an honest friction log. You are being evaluated on
how well the skills and tools work, not on how clever you are: when a skill line is unclear, wrong or
missing, do what it most plausibly means, and LOG it (Critical / Major / Minor + the skill file and line).

## Your setup (filled in per arm by the orchestrator)

- `REPO` = a scratch copy of the harness at the frozen commit; run every harness command as
  `uv run --project $REPO harness ...` (or `cd $REPO` first). Never use another checkout.
- `SKILLS` = `$REPO/.claude/skills/` — rev 6 of `drawing-intake`, `structural-drawing-reader`,
  `drawing-analysis-report`, `tekla-conversion-plan` (approval SIMULATED for this eval). Read the
  SKILL.md files and the files they point to yourself; ignore any other copy of these skills.
- `PROJECT` = the project folder: `input/` holds the drawings; you write `work/` with the harness and
  `questions.md` next to it, as the skills say. Project id: given per arm.
- DWG converter: `export HARNESS_DWG2DXF=<given path>`; there is no ODA converter.
- `export TMPDIR=$PROJECT/tmp` (create it).

## Rules

- Do NOT call the Skill tool and do not read `.claude/skills/` of any other checkout: the session may
  hold an older revision of these skills. Read SKILL.md files from `$SKILLS` only.

- Role: `doc-reader` (see `$REPO/.claude/agents/doc-reader.md`). You never touch Tekla, never open a
  gate, never write `--role engineer`.
- Engineer answers: you do NOT invent them. At the units hard stop you stop and return. The orchestrator
  will later hand you a file of relayed answers from an "engineer simulator"; you record them exactly as
  the rev-6 intake skill says for relayed eval answers (`--role simulated`). If an answer contradicts the
  drawing, the skills tell you what to do; do it.
- Do not read anything outside `$PROJECT`, `$REPO` and the paths given here. In particular never open
  `dwg-lab/proposals/skills/eval3/`, `dwg-lab/proposals/skills/eval4/`, `projects/_evals/`, any `answer-key*` file, any `eval3/key`, `eval4/key` folder, any other arm's
  project, or any judge file. Also never open `$REPO/dwg-lab/proposals/skills/EVAL-*.md` or
  `REVIEW-*.md` (earlier eval records; they would tell you what is being tested).
- Friction log: `$PROJECT/friction-runner.md`, one entry per problem: severity, skill file:line or tool,
  what happened, what you did. Also log every place you had to improvise.
- Command log: append every harness command you run (one line, with its exit code) to
  `$PROJECT/cmdlog-runner.txt`.

## Phase A (now)

`drawing-intake` in full, then `structural-drawing-reader` steps 1–2 (the skills say what may run before
the units answer). Stop at the units hard stop.

Return (short): the path of `questions.md`, the open blocking question ids with codes (from `harness
status`), what you could not do, and the friction counts by severity.

## Phase B (when the orchestrator sends the relayed answers)

Record the relayed answers, rerun what the skills say to rerun after answers, then
`structural-drawing-reader` steps 3–7. Stop when the skill's "done when" holds. Do NOT write
`01-analysis.md` or `02-plan.md` (fresh agents do that).

Return (short): findings count by kind, reader questions raised (ids + codes), whether any relayed answer
contradicted the drawing and what you did, gate-1 reasons from `harness status`, friction counts.
