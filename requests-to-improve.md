# Requests to improve (RTI)

Improvement log for the harness itself. Each entry: classification, root cause, proposed fix,
regression test, status. Statuses: `proposed` → `approved` → `done` (with version) or `rejected`.

Classification: `reading` · `planning` · `spec` · `build` · `verify` · `report` · `process` · `tooling`.
Severity: `critical` · `major` · `minor`.

---

## RTI-0001 — No drawing inventory or revision control at intake

- Source: flow review, 2026-11-06 (Flow I)
- Classification: process · Severity: critical · Status: **approved** (engineer, 2026-11-06)
- Root cause: step 1 copies files without checking the sheet list, revisions or duplicates.
- Proposed fix: deterministic `inventory` step (hash, sheet no./rev/date from title block,
  compare with drawing list); lock `input/` by hash; a separate "new revision" flow.
- Regression test: fixture set with one missing sheet and two revisions of one sheet →
  both reported as blocking questions.

## RTI-0002 — Confidence assigned per file format instead of per value

- Source: flow review, 2026-11-06 (Flow I)
- Classification: reading · Severity: critical · Status: **approved** (engineer, 2026-11-06; schema support already in v0)
- Root cause: fallback table rates DXF "High" regardless of dimension overrides, mixed scales,
  missing xrefs, units.
- Proposed fix: per-value `provenance` + `confidence` (done in `schemas/common.schema.json`);
  DXF checks for overridden dimension text vs measured value, scale regions, xrefs, `$INSUNITS`.
- Regression test: DXF fixture with an overridden dimension → value flagged, question raised.

## RTI-0003 — Grids and levels reach planning without human confirmation

- Source: flow review, 2026-11-06 (Flow I)
- Classification: process · Severity: critical · Status: **approved** (engineer, 2026-11-06)
- Root cause: grids/levels are extracted inside the large analysis step and flow straight into the plan.
- Proposed fix: deterministic `grids.json` / `levels.json`; mandatory section with a rendered
  grid plan in gate 1.
- Regression test: gate-1 checklist fails if the grid section is missing.

## RTI-0004 — Legacy Vietnamese font encodings (TCVN3/VNI) in DWG/DXF

- Source: flow review, 2026-11-06 (Flow I)
- Classification: reading · Severity: major · Status: **approved** (engineer, 2026-11-06)
- Root cause: text decodes "successfully" into garbage; not detected by the fallback chain.
- Proposed fix: detect encoding from text style font names; convert to Unicode deterministically.
- Regression test: fixture with `.VnTime` text → correct Unicode output.

## RTI-0005 — Write guard blocks reading a file whose name contains `tekla-cli`

- Source: main session, 2026-11-06 (`sed -n 1,40p docs/tekla-cli-contract.md` was denied)
- Classification: tooling · Severity: minor · Status: **done** (Unreleased; engineer approved the fix 2026-11-06)
- Root cause: in a segment whose command word is not on the inert list (`sed`, `python`, …),
  any `tekla-cli` substring counted as an unparsed invocation, so a file name such as
  `tekla-cli-contract.md` was treated as a write. ADR-0004 says data mentions must pass.
- Fix: the mention regex ignores `tekla-cli` followed by `-` or a word character (a longer,
  different name). `sed` stays off the inert list: its `e` command runs shell code.
- Regression test: `tests/test_guard_hook.py` — the denied command and a
  `python … docs/tekla-cli-contract.md` call pass; `sed -n 'e tekla-cli build'` and
  `bash -c 'tekla-cli.cmd build'` stay denied.
- Known limit (unchanged): a heredoc or inline script that contains the bare word `tekla-cli`
  is still denied; write such text with the Edit/Write tools instead.

## RTI-0006 — Write guard does not see the CLI under its default .NET build name

- Source: review of `tekla/api-notes.md`, 2026-11-06
- Classification: tooling · Severity: critical · Status: **done** (Unreleased; approved by the engineer 2026-11-07, both layers; ADR-0007)
- Root cause: the guard recognises only the executable name `tekla-cli(.exe)`. An SDK-style
  `TeklaCli.csproj` builds `TeklaCli.exe` by default, and `dotnet run --project tekla/TeklaCli -- build`
  never names the exe. Today both `TeklaCli.exe build --lot 1` and that `dotnet run` call get
  no decision from the guard, so the main session could write to Tekla.
- Proposed fix: (1) contract: "the executable is named `tekla-cli.exe` (`AssemblyName`
  `tekla-cli`); agents never invoke it through `dotnet run`/`dotnet exec`" (the csproj in
  `tekla/api-notes.md` already sets `AssemblyName`); (2) hook: also treat `teklacli(.exe)`
  and `dotnet run|exec` aimed at the CLI project as invocations (fail closed).
- Regression test: `TeklaCli.exe build --lot 1` and `dotnet run --project tekla/TeklaCli -- build`
  are denied outside `builder`.
- Done: contract names the exe and forbids the dotnet routes; the hook matches `tekla[-_]?cli`
  and denies any `dotnet run|exec|watch` (`tests/test_guard_hook.py`, RTI-0006 cases).
- Follow-up: integration tests that reach the Tekla API outside `builder` → RTI-0007.

## RTI-0007 — Integration tests could write to whatever Tekla model is open

- Source: review of RTI-0006, 2026-11-07
- Classification: tooling · Severity: minor (no Tekla test project exists yet; major once
  Step 3 adds one) · Status: **proposed** (engineer agreed with the direction 2026-11-07; to be
  done when `tekla/` gets its first .NET project)
- Root cause: an external Open API client talks to the first Tekla session started and writes
  to whatever model is open there. A `dotnet test` run of integration tests, by an agent or by
  the engineer, would build test objects into a real project model if one is open. The guard
  hook cannot protect this: it sees only agents, and test runners can be started many ways
  (`dotnet test`, `vstest.console`, Test Explorer, scripts), which ADR-0004 already accepts it
  cannot catch.
- Rejected: extending the hook to deny `dotnet test`. It would block the Tekla-free unit tests
  (most of the code, runnable on Linux CI) or need fragile project-name matching, could still
  be bypassed, would push test runs onto `builder` (wrong role), and would not stop the
  engineer's own runs.
- Proposed fix:
  1. Two test projects: `TeklaCore.Tests` (no Tekla references, runs anywhere and in CI) and
     `TeklaCore.IntegrationTests` (needs a running Tekla).
  2. The integration fixture fails before any write unless the open model path equals the
     declared test model path and that model folder holds a marker file
     (e.g. `.harness-test-model`); same comparison code as contract safety rule 1.
  3. A `permissions.ask` rule for `dotnet test` on the IntegrationTests project, so each run is
     confirmed by the engineer.
- Regression test: with a model open that lacks the marker or has another path, the integration
  fixture fails before any write; `TeklaCore.Tests` builds and runs with no Tekla installed.

## RTI-0008 — An agent can forge a spec validation receipt

- Source: independent design review of slice S1b (ADR-0010 Amendment 1), 2026-11-08
- Classification: safety layer · Severity: minor (the receipt is not a gate; gate approval stays
  with the engineer) · Status: **done** (Unreleased; approved by the engineer 2026-11-08; PR #8, master
  `3307060`; live-checked 2026-11-09 in a fresh Claude Code 2.1.319 session on master)
- Live check (2026-11-09, `claude -p` in a master worktree, `acceptEdits`, `cp`/`echo` allowed):
  Write and Edit of a receipt were denied by the permission rule ("denied by your permission
  settings"); `cp`, `echo >`, a two-line `cd` + `cp`, and `ls … | xargs cp` were denied by the
  hook; a control Write, `cat`, `test -f` and `harness validate spec` were allowed, and the
  receipt it wrote matched the spec's SHA-256. PowerShell was not exercised (Linux).
- Root cause: the receipt is a plain JSON file holding the spec's SHA-256. Any agent with file
  write access (`builder` has Write) can create a receipt for a spec that was never validated,
  and the CLI cannot tell. Signing adds nothing while the key sits on the same machine.
- Proposed fix: a Claude Code `permissions.deny` rule for Write and Edit on `**/*.receipt.json`
  (and a guard-hook check for shell redirection into such a file), so only `harness validate spec`
  produces receipts. Check the current permission-rule syntax in the Claude Code docs first.
- Regression test: a hook/permission test where `builder` tries to Write `x.json.receipt.json`
  and is denied, while `uv run harness validate spec` still writes it.
- Related, also needs approval (agent definition): `.claude/agents/builder.md` step 1 runs
  `harness validate spec` right before building, so the agent that writes to Tekla produces its
  own receipt, and the Tekla machine needs Python (ADR-0010 says it should not). Proposed: step 1
  becomes "the receipt exists and matches", checked by `tekla-cli` itself; validation stays with
  the planner/doc-reader before the gate.
- Implemented: settings deny `Edit(**/*.receipt.json)` (Claude Code permissions docs, read
  2026-11-08: Edit rules cover Write, Edit, NotebookEdit and Bash `>`/`>>`/`2>` targets; the
  pattern is anchored at the working directory). `guard_tekla_write.py` denies any shell
  command naming a receipt, or piping one into another command, unless it only reads
  (cat, ls, Test-Path, jq, …) with no redirection into a receipt and no `--output`, for every
  agent. `builder.md` step 1 now only checks that the receipt exists. Tests:
  `tests/test_guard_hook.py` (`test_receipt_*`, `test_settings_deny_edits_of_receipts`); the
  producer side stays covered by `tests/test_receipt.py`. An independent Opus review found the
  newline bypass logged as RTI-0009, fixed on the same branch.
- Remaining limits: this narrows forgery, it does not close it; only an OS-level sandbox would.
  Not seen: a script file that writes a receipt (`uv run python forge.py`), a glob that does
  not spell `.receipt.json`, a directory copy, a path outside the working directory. Nothing
  stops `builder` from running `harness validate spec` itself; `builder.md` no longer asks it
  to. Unverified: whether the `Edit(...)` pattern matches case-insensitively on Windows. The
  Write-tool denial is enforced by Claude Code and is pinned only as configuration in pytest.

## RTI-0009 — Write guard reads a multi-line command as one command

- Source: independent review of RTI-0008, 2026-11-08
- Classification: tooling (safety layer) · Severity: critical · Status: **done**
  (Unreleased; merged by the engineer with RTI-0008 in PR #8, 2026-11-09)
- Root cause: `_split` in `guard_tekla_write.py` let `shlex` treat a newline as whitespace, so
  `cd projects/p` + newline + `tekla-cli build …` became one segment whose command word `cd`
  is inert, and the write passed for any agent. The `Bash(tekla-cli build *)` ask rule still
  prompted, but it does not check which agent runs the command.
- Fix: every newline separates commands like `;`, a bash backslash-newline too (in PowerShell a
  trailing `\` is part of a path, so joining lines would hide the next one; a split bash
  continuation fails closed). Inside quotes a newline stays in its token, so a multi-line
  `git commit -m` is still data. Accepted change: a heredoc body is now read as commands, so a
  heredoc that mentions a CLI write is denied outside `builder` (the commit skill uses `-F`).
- Regression test: `tests/test_guard_hook.py` — newline, CRLF, bash continuation and
  PowerShell trailing-backslash cases in `WRITE_COMMANDS` and `RECEIPT_WRITE_COMMANDS`; a
  multi-line commit message in `MENTION_ONLY_COMMANDS`.
## RTI-0010 — On Windows, an unlocked reader can make a work-folder write fail

- Source: independent review of the tool wave 2 seam (ADR-0011), 2026-11-08
- Classification: tooling · Severity: minor · Status: **proposed**
- Root cause: Python opens files on Windows without delete sharing, so while a read-only command
  (status, sheet-text, find-text) has `answers.json` or the registry open, a writer's
  `os.replace` in `write_text_atomic` fails with `PermissionError`. The registry may already be
  written by then, and `harness answer` catches only `QuestionsError`, so the engineer sees a
  traceback. ADR-0011 leaves readers unlocked by design. The same sharing rule can stop the
  holder record from being removed (a warning only).
- Proposed fix: retry the replace a few times with a short back-off on `PermissionError` on
  Windows; turn a final failure into exit 3 with a "retry" message.
- Regression test: Windows-only test that holds a read handle on the target while
  `write_text_atomic` replaces it; it expects retry, then success, or exit 3 with no traceback.

## RTI-0011 — An agent can declare itself the engineer when it records an answer

- Source: independent review of the tool wave 2 seam, 2026-11-08 (finding M1)
- Classification: safety layer · Severity: major · Status: **proposed** (needs engineer decision)
- Root cause: gate 1 counts only answers recorded with `--role engineer` (tool wave 2, D4), but the
  role is whatever the caller types. Any agent can run `harness answer … --role engineer`, or call
  `record_answer(role="engineer")` from Python, and gate 1 then reports ready on an answer the
  engineer never gave. Until P3, `status` even printed that command, ready to paste, in its reasons.
  The engineer still opens every gate (principle 5), so gate readiness alone does not let an agent
  build, but a wrong "ready" misleads the planner and the engineer.
- What the tools can and cannot do (Claude Code docs, 2026-11-08): a PreToolUse hook sees every
  Bash call that the model or a subagent makes, but not `!` commands typed by the engineer. A hook
  matches command text only, so `sh -c`, a script or a Python call get past it; the permissions
  page says such a rule "isn't a security boundary around the program". A hook cannot tell who
  issued a call.
- Proposed fix (defence in depth, none of it is a boundary on its own):
  1. P3 (tool wave 2): no gate-1 reason or printed command hands an agent `--role engineer`; the
     text says the engineer must answer.
  2. Guard hook: deny any model-issued Bash command that runs `harness answer` with
     `--role engineer`. The engineer records their answers with `! harness answer …` in the
     session, or from their own terminal.
  3. AGENTS.md hard rule: an agent never records an answer as the engineer; simulated answers
     use `--role simulated`.
  4. Later, if needed: engineer answers carry something an agent cannot produce (for example, an
     answer file the engineer edits, checked by hash at gate time).
- Regression test: the guard hook denies `harness answer W Q-1 --text x --by y --role engineer`
  from the model and allows `--role simulated`; a `status` run after a simulated answer prints no
  `--role engineer` command addressed to an agent.

## RTI-0012 — `harness callouts` drops rebar callouts whose diameter sign is an unexpected glyph

- Source: EVAL-3 (290 'ù' callouts, reader Q-144) and research note
  `docs/research/diameter-glyph-u-grave.md`, 2026-11-09
- Classification: tool · Severity: major · Status: **accepted**, fix in tool wave 3 (package M)
- Root cause: the callout candidate scan only starts at Ø or `%%c`. In dwgshare 290, 507 callouts write the
  diameter as `ù` (style `Arial`, TrueType family `CIC Arial Narrow E`), and 31 VNI-style callouts write it
  as `Þ`. They get no candidate at all: they are neither parsed, nor listed as unparsed, nor blocked, and
  no question is raised. All rebar of that house is missing from the counts without any sign.
- Proposed fix: a diameter-position glyph that is not Ø or `%%c` is a candidate. It is listed as unparsed
  with reason `symbol_glyph_unverified` and asked (`callout_unparsed`). It is never decoded until the
  engineer approves a scoped knowledge row (the research note finds no safe rule today: byte 0xF9 is the
  TCVN3 letter ự in sibling styles).
- Regression test: a fixture with `2ù20` and `ù10a150` in a unicode-decoded style gives unparsed
  candidates with that reason and one `callout_unparsed` question. No entry is silently dropped.

## RTI-0013 — A style named like a Windows font hides its TrueType family from the font hint

- Source: research note `docs/research/diameter-glyph-u-grave.md`, 2026-11-09
- Classification: tool · Severity: major · Status: **proposed** (needs engineer decision; not in tool wave 3)
- Root cause: `encoding.font_hint` decides `unicode` from the style name (`Arial`) before it looks at the
  style's TrueType family (`CIC Arial Narrow E`), which can be a legacy Vietnamese font. The knowledge
  table is consulted only after `unknown`, so even an approved row for that family would never be read.
- Proposed fix: when the TrueType family is present and differs from the style name's font, the family
  decides. Unknown families are `unknown`, not `unicode`. This blocks more text (290's M1 would rise), so it
  needs the engineer's decision and a corpus measurement before it lands.
- Regression test: a style named `Arial` with family `CIC Arial Narrow E` is not hinted `unicode`; a
  style named `Arial` with family `Arial` still is.

## RTI-0016 — Step 2 ends without a take-off plan the modeller and the 3D step can use

- Source: engineer, chat 2026-11-20 (session 10, run 3 of project 01): "đầu ra step 2 là phải có cái đó mà".
  The instruction is the principle-7 approval for the skill change below.
- Number note: RTI-0014 and RTI-0015 exist only on branch `docs/rti-0014-breakdown-tree`; this branch stops
  at RTI-0013, so expect a merge conflict on this file.
- Classification: skill · Severity: major · Status: **fixing** (skill edit on `feat/reading-tools`)
- Root cause: `drawing-analysis-report` outputs `01-analysis.md` (how the set was read) and, at gate 3,
  `04-info-matrix.csv`. Nothing lists, per member family, the values to model, how each was taken off, where
  to check it, how sure it is and whether it can be built. Run 3 had to rebuild that view by hand for the
  engineer's page (`page/gen.py`), whose author invented values (page REVIEW-1: 2 Critical), and the saved
  geometry files that hold coordinates for a 3D draft were linked from nowhere.
- Fix: `drawing-analysis-report` Part C writes `projects/<id>/takeoff/`: `00-plan.md` (order, lots,
  open questions) and one file per block and member family with the fields Mô tả + phương pháp bóc,
  Kết quả, Ref đối soát, Độ tin cậy, Chưa rõ, Trạng thái, Tọa độ cho 3D. Values come only from findings,
  saved geometry/contents files and the question registry. The engineer's page and any 3D draft are
  generated from `takeoff/`. `structural-drawing-reader` hand-back and `docs/workflow.md` step 3 name it.
- Regression test: on the next read, `takeoff/00-plan.md` exists and links one file per member family
  listed in `01-analysis.md` §8; every value row cites a finding id or a saved geometry/contents file plus
  its item ids; every part file has a Trạng thái line.

## RTI-0017 — Intake reports a broken `.dwg`/`.dxf` as a format with no reader and exits 0

- Source: Step 1 exit audit, `docs/research/step1-exit-audit.md` (gap M1), 2026-11-20; reproduced with the CLI.
- Classification: tool · Severity: major · Status: **fixed** (cc95206, b349994; independent review found the
  first fix also caught a PDF renamed `.dwg`, the second limits it to content detected as `other`)
- Root cause: `detect_input` classifies by content. A file named `.dxf` or `.dwg` whose bytes are not DXF/DWG
  (empty, garbage, a broken `AC10xx` header, a UTF-8 BOM) is detected as `other`, so intake logs "no reader
  implemented for other yet", asks a blocking question that tells the engineer to wait for a reader, and
  exits 0. The intake contract (module docstring of `intake.py`) says a dwg or dxf that cannot be read is
  exit 1.
- Fix: in intake, an input whose extension is `.dwg` or `.dxf` but whose detected format is `other` is a
  read failure of that file: logged in `read-log.json` as failed, question text says the file is damaged or
  not a drawing and asks for a new export, exit 1.
- Regression test: one parametrized intake test over the four cases above; each ends with exit 1, a failed
  read-log entry and no "wait for the reader" question.

## RTI-0018 — `harness dimensions` places a dimension by the raw text anchor, not the world anchor

- Source: `dwg-lab/proposals/tools/E10b-REVIEW-1.md` finding m4, 2026-11-21.
- Classification: tool · Severity: minor · Status: **open**
- Root cause: `geometry._world_anchor` converts the OCS text midpoint to world. `dimensions._anchor` uses the raw
  OCS point. A mirrored copy of a block can land on a different sheet than `contents --dims` puts it.
- Fix: `dimensions._anchor` calls the world anchor of `geometry.py`.
- Regression test: a mirrored INSERT holding a DIMENSION; `harness dimensions` and `contents --dims` give the
  same sheet for it.

## RTI-0019 — Dimensions that carry the invisible flag are used and counted nowhere

- Source: `dwg-lab/proposals/tools/E10b-REVIEW-2.md` finding m5, 2026-11-21.
- Classification: tool · Severity: minor · Status: **open**
- Root cause: in the DIMENSION branch of `geometry.py` the flag (group 60) is computed but not used. A dimension in
  a hidden state of a dynamic block is attached like a visible one. Outlines and symbols with the flag are
  counted in a warning; dimensions are not.
- Fix: count such dimensions in the same warning, or mark them `invisible` per item.
- Regression test: a DXF with one invisible and one visible dimension; the warning and the count show exactly one.

## RTI-0020 — Reader commands map an OS error on their inputs to exit 1 with no JSON

- Source: `dwg-lab/proposals/tools/E4a-REVIEW-1.md` finding m2 and `E4a-REVIEW-2.md` finding m4 (the entry was
  asked there and never written), 2026-11-21.
- Classification: contract (exit codes) · Severity: minor · Status: **open**
- Root cause: `sheet_text.read_json` folds `OSError` into `EXIT_INVALID`. `list-sheets`, `sheet-text` and
  `unassigned-clusters` give exit 1 where AGENTS.md says an environment error is exit 3. `manifest-check` is
  already mapped to 3.
- Fix: the same `__cause__` mapping as `parts_manifest._os_errors_are_environment`.
- Regression test: `chmod 000` on an input of each of the three commands; each ends with exit 3.

## RTI-0021 — `harness part manifest-check` exits 1 with no JSON problem when `grid-systems.json` is invalid

- Source: `dwg-lab/proposals/skills/rev11/DECISIONS.md` § 11 and § 14, 2026-11-21.
- Classification: tool · Severity: minor · Status: **open**
- Root cause: `manifest-check` fails on an invalid `grid-systems.json` with a message on stderr. `part check`
  reports the same file as `input_invalid`.
- Fix: `manifest-check` reports the same problem code.
- Regression test: an invalid `grid-systems.json`; `manifest-check` prints the `input_invalid` problem in JSON.

## RTI-0022 — The receipts file has no tamper chain

- Source: `dwg-lab/proposals/tools/E5b-REVIEW-1.md` decision D5 and DECISIONS.md § 13 D5 (accepted limit),
  2026-11-21.
- Classification: tool · Severity: minor · Status: **open**
- Root cause: an agent can append a forged `reviewed` or `locked` receipt. Same class as RTI-0008.
- Fix: a `prev_sha256` per receipt, checked by `harness status --verify`.
- Regression test: a receipt appended or edited by hand makes `status --verify` fail.

## RTI-0023 — The part hash twice missed an input that `part check` reads

- Source: `E5b-REVIEW-1.md` and `E5b-REVIEW-2.md` (the Critical of each); DECISIONS.md § 13 D1 and § 18 D1,
  2026-11-21.
- Classification: tool · Severity: major · Status: **open**
- Root cause: the list of hashed inputs and the list of files `part check` reads are written by hand in two
  places, so they drift.
- Fix: one registry of the inputs of `part check`, read by both the check and the hash.
- Regression test: a test that fails when `part check` opens a file the hash document does not hold.

## RTI-0024 — `harness part answer-key` has no verdict for "the drawing does not show this item"

- Source: `dwg-lab/proposals/tools/E9-REVIEW-1.md` decision D2 and DECISIONS.md § 19 D2, 2026-11-21.
- Classification: tool · Severity: minor · Status: **open**
- Root cause: such rows are answered `cannot_tell`, which mixes "unreadable" with "not on the drawing".
- Fix: a verdict `absent`, counted apart in the score.
- Regression test: an answer-key row with `absent` is counted in its own bucket, not in `cannot_tell`.

## RTI-0025 — Tests pin temporary state

- Source: rev11 review rounds (E-series), 2026-11-21.
- Classification: process · Severity: minor · Status: **open**
- Root cause: some tests pin stub actions, review-round numbers in their names, or problem text that a later
  package rewrote.
- Fix: after run 4 of project 01, one pass that prunes them. No behaviour test is lost.
- Regression test: the suite count of behaviour tests before and after the pass is the same list of behaviours.

## RTI-0026 — `harness part review-sample --seed` can be steered by whoever picks the seed

- Source: `dwg-lab/proposals/tools/E7-REVIEW-1.md`, 2026-11-21.
- Classification: tool · Severity: minor · Status: **open**
- Root cause: the skill gives the seed choice to the orchestrator after `checked`, when the reader's values
  already exist.
- Fix: derive the seed from the part hash, or record the seed in the `checked` receipt before the reader's values
  exist.
- Regression test: the same part hash always gives the same sample; a seed that differs from the receipt is
  refused.

## RTI-0027 — `harness takeoff check` does not compare a number glued to a letter

- Source: `src/tekla_harness/takeoff_check.py` (pattern `_SIGNED`), reading review of E8, 2026-11-21.
- Classification: tool · Severity: minor · Status: **open**
- Root cause: `_SIGNED` skips a number glued to a letter (`D400`, `400mm`) on both sides, so such a number typed
  in a free-text slot has no backing check.
- Fix: a unit and prefix table (`mm`, `m`, `D`, `Ø`) stripped before the match. Marks stay exempt.
- Regression test: a free-text slot with `400mm` that differs from the source fails; the same number in a mark
  passes.

## RTI-0028 — Three nits of `harness takeoff` left by the E8 fix package

- Source: `dwg-lab/proposals/tools/E8-REVIEW-1.md` finding m11, 2026-11-21.
- Classification: tool · Severity: minor · Status: **open**
- Root cause: (1) `_files(out, "plan")` matches `00-plan.md`, so a part with id `plan` would delete the plan.
  (2) Blank lines added at the end of a file pass `check`, while `render` rewrites that file. (3) The `Nguồn`
  commands print the path unquoted, while `Lệnh đo lại` quotes it.
- Fix: (1) skip `PLAN_FILE` in `_files`. (2) report `generated_differs` for extra lines at the end. (3) quote
  the path with `shlex.quote`.
- Regression test: one test per nit.

## RTI-0029 — `harness status --verify` reports a broken tool-written file as a failed check of every part

- Source: `E5b-REVIEW-4.md` decision D1 (probe P9); DECISIONS.md § 25, 2026-11-21.
- Classification: tool · Severity: minor · Status: **open**
- Root cause: a check that stops only with `input_invalid` (a tool-written record the hash does not read, today
  `marks.json`) lands in `check_codes` of every locked part, like a defect of the part itself.
- Fix: write that case as `check_error` (no `check_codes`, `verified: false`) and name it in the schema
  description. Until then the skill rule holds: `input_invalid` alone never reopens a part.
- Regression test: a malformed `marks.json` under two locked parts gives `check_error` on both rows and no
  `check_codes`.

## RTI-0030 — Minor points of the fourth review of the part lock

- Source: `E5b-REVIEW-4.md` findings m1 to m6, 2026-11-21.
- Classification: tool · Severity: minor · Status: **open**
- Root cause: edge paths of `harness status --verify` that fail safe but report badly: a check that stops
  without a hash gets a false `changed_during_check` (m1); the manifest is read twice, so the second read can
  disagree with the rows (m2) or end the command with no document (m3); two paths have weak or no tests
  (m4, m5); one regression test came with the fix commit, not the red one (m6).
- Fix: as the report lists per finding; pass the manifest read once into the verification.
- Regression test: one test per finding as the report names them; the D4 mutant R30 must be killed.
