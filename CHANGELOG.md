# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/).
Harness releases are tagged with their benchmark score (see `benchmark/README.md`).

## [Unreleased]

### Added
- SessionStart hook `handoff_reminder.py` (sources `startup` and `clear`): reads the open rows of
  `.handoff/INDEX.md` in the main checkout (found from a worktree too) and tells Claude to ask the
  engineer which multi-session handoff to resume before any other work; a row is removed only after the
  engineer confirms its topic is cleared (AGENTS.md `/handoff` row). Never blocks session start.
- Step 0 foundation: repository layout, `AGENTS.md` / `CLAUDE.md`, ADRs 0001–0004.
- Claude Code project config: Vietnamese replies, permission rules, plugins
  (Karpathy guidelines, pyright-lsp, csharp-lsp).
- Five subagent definitions: `doc-reader`, `planner`, `builder`, `verifier`, `reporter`.
- `guard_tekla_write.py` PreToolUse hook: only `builder` may run `tekla-cli` write commands;
  unknown subcommands are treated as writes (fail closed).
- `session_env_check.py` SessionStart hook: reports remote session, missing `tekla-cli`, Python version.
- JSON Schemas v0: `spec`, `project-state`, `read-log`, shared `common` (provenance, confidence).
- `tekla_harness` CLI: `harness validate`, `harness env-check`.
- CI on Windows and Ubuntu: ruff, pyright, pytest.
- Step 1 S1: `harness detect` (format from file bytes, DWG version, sha256, extension mismatch
  warnings) and the `readlog` builder (timed attempts, refuses silent failures, validates
  before writing).
- Step 1 S2: `harness dwg2dxf` — ODA File Converter, then LibreDWG `dwg2dxf` (ADR-0005).
  Success requires a DXF that ezdxf opens; fallback caps confidence at `medium`; no converter
  at all exits 3. Runtime dependency `ezdxf` (MIT) added: the DXF reader for all later slices.
- Step 1 S2b: per-project read cache (ADR-0006, ADR-0008). Content-addressed blobs plus an
  action cache; key = SHA-256 over a domain tag and canonical JSON of input digest, converter
  chain by content digest, argument templates, ezdxf version and code digest. Every
  read is verified; corrupt or inconsistent entries are discarded; only clean successes (no
  failed attempt) are cached; the input is snapshotted once; a hit replays
  converter, confidence cap, attempts and warnings. `harness dwg2dxf --cache-dir … [--refresh]`.
  New schema `cache-entry` (`urn:tekla-harness:schema:cache-entry:0.1`) and example.
- Step 1 S3: `harness read-dxf` / `probe_dxf` — deterministic DXF probe (units from `$INSUNITS`
  only, never defaulted to metres; layouts, layers, blocks, xrefs, text styles, legacy Vietnamese
  font hints, unreadable objects, dimension text-override audit, scales) with open questions.
  New schema `dxf-probe` (`urn:tekla-harness:schema:dxf-probe:0.1`) and example.
  Hardened after independent review: `$INSUNITS` accepted only as an integral code 0..20; header
  units never `high` (`units_confirm`), lowered to `low` with blocking `units_conflict`
  (`$MEASUREMENT`) or `units_suspect` (median modelspace linear dimension outside 0.01 m..100 m);
  angular dimensions gated on `DIMAUNIT`, linear on `DIMLUNIT`; group 42 cross-check; dimensions in
  block definitions audited; non-finite numbers never emitted (strict JSON); null handles for
  R12-era files; dynamic-block inserts attributed to their source block; `section_errors` and
  `status: partial` instead of a crash. Still `0.1`: not yet released.
  Integration pass: legacy-font hints now come from `encoding.font_hint(style name, font file)` only
  (the same call `extract_text` makes), one row per style with the matched fields listed
  (`matched`), `capital_font` recorded per style and per hint, and the old family, bigfont and
  `vni_` / `vni ` rules are gone; `probe_dxf(path, converter, xref_dir=None, knowledge=None)`
  looks xrefs up in `xref_dir` (the original drawing's folder for converted files); new
  non-blocking questions `font_encoding_proposed` and `font_encoding_conflict`; `handles_reliable`
  and `num` are public. Schema `dxf-probe` changed (still `0.1`).
- Step 1 S4: `harness intake <input_dir> --out <work_dir> --project-id <id>` / `run_intake` — one
  deterministic command chaining detect, `dwg_to_dxf` and `probe_dxf` over a folder. Writes
  `read-log.json`, `inventory.json`, `questions.json`, `probe/<path>.json`, `text/<path>.json`
  (the text index of every probed DXF), `converted/<path>.dxf`; never writes the input folder; exit 2 if the work folder is inside it, 3 if a DWG exists and no
  converter is configured (nothing written). One blocking `units_confirm_all` question lists every
  DXF; other probe questions are grouped by code (50 refs max, true count kept); formats without a
  reader (pdf, image, docx, xlsx, other) are `unreadable` with a blocking `no_reader_implemented`
  question. Inventory rows carry a text summary (entries, by encoding, low-confidence count) and
  `text_index`; a non-blocking `encoding_unknown_non_ascii` group lists the text styles holding
  non-ASCII text of unknown encoding; xrefs of a converted DWG are looked up beside the original DWG;
  a malformed knowledge table is exit 1 and nothing is written. Probe and text-index documents record
  each file by its path relative to the input folder (a DWG's text index names the DWG), so no output
  names the absolute input folder. New schema `intake`
  (`urn:tekla-harness:schema:intake:0.1`, kinds `inventory` and `questions`) and examples. `harness dwg2dxf` now prints `stderr_error_lines`,
  `stderr_warning_lines` and `stderr_tail`.
- Step 1 S5: `extract_text` / `harness extract-text <file.dxf> --out <text-index.json>` —
  deterministic text index of one DXF (stdout is a small summary, the index goes to the file; exit 1
  when the index is invalid or the file unreadable, 2 usage, 3 environment). Every TEXT, MTEXT, ATTRIB (tag, owning block, insert handle), MULTILEADER text and
  DIMENSION override text in modelspace and layouts, plus the same inside INSERTed blocks
  (recursive via `virtual_entities()`, `block_path`, depth limit 16 and cycle guard, both counted).
  ATTDEFs are listed as definitions only. Per entry: space/layout/coordinate frame, effective layer
  and state, style and font file, WCS position (OCS and alignment point handled), raw / plain /
  decoded / display text, `%%` special codes, decode record (encoding from code-point evidence,
  font names or an approved knowledge row, MTEXT runs split at inline `\F`/`\f` fonts, case and
  NFD flags), confidence, provenance
  (`sheet` is `unknown`, `method` `dxf_entity`/`dxf_dimension_text`). Legacy TCVN3/VNI text is
  converted before `%%c`/`%%d`/`%%p` are expanded; `\U+XXXX` escapes are decoded first. Per-entity
  failures give `status: partial` with the entity listed. New schema `text-index`
  (`urn:tekla-harness:schema:text-index:0.1`) and example. `extract_text(..., source=...)` sets the
  recorded `file.path` and every `provenance.file` (intake passes the input-relative path; the CLI keeps
  the path as given).
  Unicode evidence: a Vietnamese letter or tone mark that single-byte legacy text cannot hold
  (U+0102/0103, U+0110/0111, U+01A0/01A1, U+01AF/01B0, U+1EA0-U+1EF9, combining U+0300/0301/0303/
  0309/0323) proves the run is Unicode whatever the font (`decode.source` `codepoint_evidence`,
  confidence at most `medium`; flag `unicode_evidence_contradicts_font` when the font said TCVN3/VNI);
  judged on the text as the file's code page sees it, so a cp1258 file's view of legacy bytes is not
  mistaken for Unicode. U+00D0 (Eth) inside Vietnamese Unicode text is flagged `eth_for_d_stroke`,
  never replaced.
- Step 1: knowledge table mechanism (ADR-0006 layer 2): `knowledge/font-encodings.csv`
  (`pattern,applies_to,encoding,capital_font,status,evidence,source,decided_by,decided_on`),
  `knowledge/README.md`, `tekla_harness.knowledge` (load and validate; a malformed table raises,
  exit 1). Only `approved` rows change behaviour, and only when `encoding.font_hint` said unknown
  (text style runs, not inline MTEXT fonts): `decode.source` `knowledge_table` with the row pattern in
  `decode.knowledge_patterns`; approved rows that disagree leave the style undecided (flag
  `knowledge_conflict`). `proposed` rows only raise a question that shows their evidence. Seeded with
  three proposed rows for exact font files (`VHARIAL.TTF`, `vntimeh.shx` -> tcvn3, `vn_vni.shx` ->
  vni), each with evidence and counter-evidence from local samples (the first draft's `VH*.TTF` and
  `vn*.shx` wildcards also matched VNI fonts such as `VHELVCN.TTF` and `vn_vni.shx`). Packaging the folder into the wheel needs a `pyproject.toml` force-include.
- Step 1 item 5 (RTI-0001, RTI-0003): first structural extractors, library functions on a DXF plus
  its text index (sha256 checked; CLI: see the next entry). `sheets.extract_sheets`: sheet frames found as
  axis-aligned closed rectangles (top level or inside INSERTs, world coordinates; aspect 1.2..1.8,
  >= 5 texts, short side >= 40 text heights; inner borders merged, containers dropped), layouts with
  content as sheets, viewport windows map model space to layout sheets; every text assigned to a
  detector sheet id (`model#01`, `<layout>#01`) or unassigned; title-block candidates only from ATTRIB
  tags / `label: value` (medium) or label adjacency / lower-right sheet-code pattern (low), never from
  frame-block template text; questions for missing, conflicting and duplicate sheet numbers, missing
  revisions, identical sheet content. `grids.extract_grids`: bubbles = circles holding one axis label,
  paired with long collinear lines; views by crossing lines; families by direction with spacings,
  dimension evidence (override vs drawn), cross-view/cross-sheet consistency, skew, non-orthogonal,
  duplicate/missing/mixed labels, unlabelled grid-layer lines; Tekla coordinate-string PROPOSAL per
  family (`0 3*6000`) in declared drawing units, never converted; Tekla X/Y assignment and gate-1
  confirmation always asked. `levels.extract_levels`: signed level values in metres as written
  (forms bare/prefixed/labelled/embedded, level-symbol blocks), grouped values, derived storey
  heights; questions for name conflicts, out-of-range values, single occurrences, missing datum and
  finished vs structural level (always). New schemas `sheets`, `grids`, `levels`
  (`urn:tekla-harness:schema:<name>:0.1`) and synthetic examples.
  Hardened after independent review (schemas changed, still `0.1`). Grids: axes, spacings and proposals
  are never `high` (reserved for an engineer answer at gate 1); each spacing carries `evidence`
  (`dimension_adjacent` / `dimension_span` / `other_view`, `agrees`, `independent`, `ref`): an overall
  dimension is span evidence only, a view on the same sheet, a copied sheet (duplicate_of or >= 90 %
  identical texts) or the same block is not independent; disagreeing evidence still makes a spacing low
  with a blocking question. A circle holding other text besides its label is not a bubble
  (`summary.bubbles_other_text`); labels `1A`, `A1` are accepted; offsets are measured at line midpoints;
  'not parallel' is an end-to-end drift above half the rounding step; family directions are circular
  (median angle); collinear same-label pieces join only within 8 radii; new blocking
  `grid_axis_layer_mismatch` (axis off the family's majority layer/linetype) and
  `grid_label_order_nonmonotonic`; one compared spacing is never `scaled` (it hid mismatches as
  non-blocking); differences up to 2e-4 of the spacing are status `drafting_tolerance` with non-blocking
  `grid_spacing_drafting_tolerance` (heuristic); `question_counts` gives the true count per code; the
  bucket search is bounded (a 200 m circle no longer takes 20 s). Sheets: without title-block evidence a
  frame needs 60 text heights or the size of an accepted frame (schedule tables are not sheets); a
  container is dropped only when its inner frames are sheets themselves, else blocking
  `sheet_frame_ambiguous`; field ATTRIBs count only on the title block (frame insert, multi-field insert
  or near a field label); any disagreeing candidate is a `title_field_conflict` and nothing is chosen.
  Levels: medium only next to a level symbol (three decimals alone are low); level symbol = isosceles
  triangle with a horizontal base, height 0.3-1.0 base, no circle/arc (north arrows excluded); storey
  words matched with diacritics; `+-` / `+/-` read as ±; `mm` / `%` values and a spaced sign after a
  name are not levels; `occurrences` ignores copied sheets; storey heights only between named storeys,
  else low with blocking `level_storey_selection`; new blocking `level_negative_storey`;
  `question_counts`.
- Step 1 item 5 CLI: `harness extract-sheets <dxf> --text-index <t> --out <sheets.json>`,
  `harness extract-grids` and `harness extract-levels` (same plus `--sheets <sheets.json>`): stdout is a
  small summary, the full result goes to `--out` and is validated first; a text index or sheets document
  built from another file is exit 1 (sha256 named in the message), a missing input file exit 2.
  `harness read-structure <work_dir>` runs the three over every DXF that `harness intake` probed
  (native DXF, or `converted/` for a DWG), reading the existing text index: writes
  `structure/<path>.{sheets,grids,levels}.json`, `structure-questions.json` (intake schema kind
  `questions`, one question per code, blocking flag and file, refs carry `file`, detector `sheet`,
  `where`, `found`, at most 50 per question with the true `count`; ids and keys: see "stable question
  ids" below) and
  `structure-summary.json` (new kind `structure_summary` in the intake schema: per file the sheet count,
  title-block sheet numbers by confidence, grid families with labels and Tekla coordinate-string
  proposal and confidence, levels with counts, question counts, warnings; records the sha256 of the
  inventory it was built from). Never modifies `inventory.json` / `questions.json`; exit 2 without them
  or without `question-registry.json`;
  files with nothing to read (not DXF/DWG, no DXF produced, DXF did not open) are skipped with a logged
  reason; a work folder that disagrees with itself (DXF changed since intake, missing or invalid text
  index, path leaving the work folder) is exit 1 with nothing written. Intake schema changed (still
  `0.1`): optional `sheet` on a question ref, kind `structure_summary`. Consolidated `count` (and per-file question counts) are the
  true totals, including questions an extractor counted but did not list. `read-structure --input-dir
  <input_dir>` is required when the inventory lists a native DXF (exit 2 without it), because work-folder
  documents record files by their input-relative path only.
- Reader tools for the `doc-reader` agent, so it never writes ad-hoc scripts (read-only over an intake
  work folder, no new dependency, new schemas `sheet-text` and `callouts` with synthetic examples).
  `sheet_text.list_sheets(work_dir)`: per file and sheet the detector id, printed sheet number with its
  confidence (or null), frame bbox, text count and up to five title-like texts (largest height).
  `sheet_text.sheet_text(work_dir, file, sheet_id, contains=None, max_entries=400)`: the entries of ONE
  sheet in documented reading order (rows top-down within 0.6 x median text height of the row's first
  entry, then left to right), compact fields only, NFC + casefold `contains` filter (diacritics kept),
  truncation with true counts; unknown encodings are returned as stored with their flags.
  `callouts.extract_callouts(work_dir)`: candidates of kinds rebar_callout, rebar_grade, section_label,
  steel_grade, plate, bolt and member_mark with `parsed` only for notations the research marks verified
  (`rule` cites the pattern), else `unparsed_reason`; confidence capped (grade-B grammar at most medium,
  unparsed/ambiguous/member marks low, case-uncertain or unknown-encoding text low); provenance `derived`
  from the text entry with a file path relative to the input folder; questions `callout_ambiguous` (one
  per notation), `member_mark_prefix_meaning` (blocking, one per prefix) and `grade_legacy_mapping`
  (blocking). Nothing is computed from a callout. Input documents are checked for version and matching
  sha256; `check_inputs=True` also validates them against their schemas. Not covered: circled bar marks,
  welds and electrodes, sheet prefixes, axes and levels (other extractors).
- Stable question ids and engineer answers (RTI C1 / M14): a rerun, or one new input file, no longer
  shifts `Q-nnn` onto another question, so an engineer answer cannot attach to the wrong question.
  One question is now one (code, blocking flag, file) with its refs (caps keep the true `count`);
  consolidated documents keep the display order (blocking first, then code, then file). New module
  `questions.py`: `key` = first 16 hex of sha256 over code, file, that file's sha256 (inventory) and the
  sorted refs (`where`, `found`, `sheet`), so a changed drawing is re-asked and an unchanged one keeps
  its key. New `question-registry.json` (schema `question-registry`): key -> id, code, file, producer,
  status `open | answered | obsolete`, `first_seen_run`, `last_seen_run`; one counter allocates
  `Q-001..` for intake, read-structure and the new `callouts` command, ids are never reused, and a
  producer only marks its own unseen keys obsolete (no timestamps; the run counters are the only thing
  that differs between identical reruns). New `answers.json` (schema `answers`): the engineer's verbatim
  `answer_text`, structured `values` for the units questions (`unit`), `grid_family_axis_assignment`
  (`{family: X|Y}`) and `member_mark_prefix_meaning` (`{prefix: meaning}`), `answered_by`,
  `answered_on`, `status active | stale | superseded`. `harness answer <work_dir> <question_id> --text
  .. --by .. [--value k=v ..]` (meant for the engineer, or on the engineer's explicit instruction;
  refuses unknown or obsolete ids, invalid values, blank text or name; a second answer supersedes the
  first; refreshes the question documents on disk). Every question shows its `key`, `file` and `answer`
  (the active answer or null); each questions document has `summary.blocking_open` (blocking questions
  without an active answer). Intake diffs the sha256 of the input files against the previous
  `inventory.json` (`summary.changes` `added | removed | changed`, all empty on a first run); answers
  about a removed or changed file, or whose question its producer no longer raises, become `stale`
  (kept, listed as `stale_answers` in the `inventory.json` summary and in the run summaries,
  never re-bound). Intake schema changed (still
  `0.1`): question `key`, `file`, `answer`, `subjects`; `summary` of a questions document;
  `summary.changes` and `summary.stale_answers` of an inventory; `first_question_number` removed from `structure_summary`; the
  per-file `units_confirm_all` replaces the one question that listed every DXF. `read-structure` and
  `callouts` need the registry (exit 2: run intake first). `intake.question_group` moved to
  `questions.question_group` (new `file` argument); `dump_json` lives in `questions` and is still
  importable from `intake`.
- CLI for the reader tools: `harness list-sheets <work_dir>`, `harness sheet-text <work_dir> <file>
  <sheet_id> [--contains TEXT] [--max N]` (stdout is the JSON) and `harness callouts <work_dir>
  [--input-dir DIR]`, which writes `callouts.json` and `callouts-questions.json` (the three callout
  question codes as one question per code and file, with `subjects` per notation or member mark
  prefix; stdout is the summary). With `--input-dir` the DXF/DWG files must still match the inventory
  sha256 (exit 1 otherwise, nothing written).
- Step 2 grid systems: `grid_system.build_grid_systems(...)` consolidates the per-view grid families into
  project grid systems (gate 1 proposals); schema `grid-system` registered, command `harness grid-system
  <work_dir> [--no-svg]`. A family joins a system only if it agrees with every member within half the
  rounding step or 2e-4 (never averaged); same labels with incompatible spacings give separate systems and a
  blocking `grid_system_conflict`; partial views, independence, never above medium; `mm` only from agreeing
  units answers (one building in m and mm merges), Tekla X/Y only from `grid_family_axis_assignment`
  answers; 4 blocking question codes (producer `grid-system`); SVGs with the PROPOSAL banner. See
  `grid_system.py`.
- Work-folder status and guards (reading toolchain): `harness status <work_dir>` (read-only, new schema
  `status`, exit 0 for any readable work folder, 2 if not one) recomputes per producer (intake,
  read-structure, callouts, grid-system) total / blocking / blocking_open / stale answers from the registry and
  answers, whether each producer's outputs are `fresh | stale | missing` (inventory sha256 recorded in
  `structure-summary.json`, `callouts.json`, `grid-systems.json`; grid-system also an `answers_sha256`) with
  the command that fixes it, and `gate1.ready_for_gate1` with reasons. The registry entry now records
  `blocking` and `file_sha256` (optional for old entries, which status counts as blocking); `harness answer`
  refuses (exit 1, nothing written) a question whose file changed since it was raised, and
  `grid_system_select` takes an optional `systems=S001,S002` value. `callouts.json` no longer embeds the
  unnumbered `questions` (they are in `callouts-questions.json`); it keeps `question_counts` by code.
  Schemas changed (still `0.1`): `callouts`, `question-registry` (producer `grid-system`, `blocking`,
  `file_sha256`), `answers`, `intake` (descriptions), `grid-system` (`answers_sha256`, units reasons and
  flag `answered_units_differ`), new `status`.

- `harness ask` (`src/tekla_harness/ask.py`): the drawing-reader agent raises questions through the registry
  instead of inventing ids. New registry producer `reader`; questions in `reader-questions.json` (same
  document kind as the other `*questions.json`), one question and one ref per distinct
  (code, blocking, file, where) - the key hashes those and the file's inventory sha256, not `found`, `sheet`
  or the text - so asking the same place again prints the same id (`already_asked`). A file not in the
  inventory exits 1; a code owned by another producer, or not snake_case, exits 2. Reader questions are never
  obsoleted by another producer's run; `--withdraw Q-id --reason` marks one obsolete (kept, with
  `withdrawn_reason`, and its active answer goes stale). `harness status` gains the `reader` producer
  (outputs `n/a`) and gate 1 waits for its blocking open questions. Schemas changed (still `0.1`):
  `question-registry` (producer `reader`, `withdrawn_reason`), `intake` (ref `file` may be null in a
  project-level reader question), `status` (5 producers, outputs `n/a`).
- EVAL-1 wave groundwork: registry producer `marks` (`harness marks`, documents `marks.json` and
  `marks-questions.json`; like callouts, its blocking questions block lot specs, not gate 1; status checks
  its outputs' `inventory_sha256`); `harness ask` accepts any code in the `reader_` namespace (no producer
  owns it), and the owner table now lists `grid_family_axis_assignment` and `grid_units_doubt` under
  read-structure, which raises them (EVAL-1 F-20, F-21); `harness marks`, `harness questions-md` and
  `harness finding` registered as stubs that exit 3 until their modules land. Schemas changed:
  `question-registry`, `status` (6 producers).
- Step 3 groundwork: `tekla/api-notes.md` (Tekla Open API 2024 Diamond, 2025/2026 deltas;
  doc-sourced, not run-verified) and ADR-0007 (on error stop, keep and resume by `SPEC_ID`;
  backup by macro; exe config at build time; per-model unique tag UDAs). The CLI contract now
  names the executable `tekla-cli.exe` and pins NuGet 2024.0.4.
- Step 3 S1 (ADR-0009): .NET solution `tekla/TeklaHarness.slnx` (SDK 10 pinned in
  `tekla/global.json`), Tekla-free `TeklaCore` (netstandard2.0) with the contract exit codes and
  the model-path text guard for safety rule 1 (fail closed: refuses relative, UNC, device, `..`,
  8.3, trailing dot/space, invalid characters; NTFS-style case folding plus NFKC/NFKD caution);
  `TeklaCore.Tests` on net10.0 and net48; Stryker.NET as a local tool; CI job `dotnet` (Windows
  runs net10.0 and net48, Ubuntu net10.0). Globalization analyzers are errors.
- Step 3 S1a (ADR-0009 Amendment 2): `ModelLocationGuard` completes safety rule 1 with Windows
  file identity through `IFolderResolver` / `Win32FolderResolver` (128-bit `FILE_ID_INFO`, final
  path, NTFS/ReFS on local drives only): refuses aliases (subst, junctions, mapped drives),
  nesting found through real or typed ancestors, remote folders, a working copy declared through
  an alias, and links inside either folder or hard-linked files in the copy. Research note
  `docs/research/windows-file-identity.md`. Windows file-system tests run on CI windows-latest
  only (`Category=Windows`); Stryker config `tekla/TeklaCore.Tests/stryker-config.json`.
- Step 3 S1b contract (ADR-0010 Amendment 1): new schema `spec-receipt`
  (`urn:tekla-harness:schema:spec-receipt:0.1`) and example — the receipt
  `<spec file name>.receipt.json` binds the spec's exact bytes (SHA-256), the spec schema `$id`
  and the validator `rules_version`; `*.receipt.json` is git-ignored. Shared strict-JSON corpus
  `tests/fixtures/strict-json/` (accept/reject) for the Python and C# readers.
- Step 3 S1b Python: `harness validate spec` reads each spec once under the strict JSON profile
  (`tekla_harness.strict_json`: no BOM, duplicate keys, NaN/Infinity, integers beyond ±2^53, lone
  surrogates or NUL, depth over 64, size over 16 MiB), deletes a stale receipt first (exit 3 if it
  cannot), and writes `<spec>.receipt.json` atomically next to each valid spec
  (`SPEC_RULES_VERSION = 1`); each result gains `receipt`. `check_spec` now requires `lot` to be
  an integer token (not `1.0`) and at most 2147483647.
  Value parity: canonical dumps `tests/fixtures/strict-json/values/` (IEEE bits, UTF-16 units)
  for every accept file, plus `accept/number_parity.json` (4049 tokens incl. 1019 that
  .NET Framework 4.8 `double.Parse` rounds differently); compared by pytest and xunit.
- Step 3 S1b C#: `TeklaCore.SpecLoader.Load(spec, lot)` builds a `LotSpec` only when
  `<spec>.receipt.json` matches the spec's exact bytes (SHA-256 of the one buffer it also parses),
  an accepted spec schema `$id` and `rules_version ≥ 1`; then read-time checks (schema_version vs
  receipt, units `mm`, lot int32 = `--lot`, unique `spec_id` matching its pattern, profile,
  material, finite points). Refusals exit 5, I/O errors 3, bad path text 2. Hand-written strict
  JSON reader (no package) with its own correctly rounded decimal→double conversion
  (`System.Numerics.BigInteger`): 0 of 150,000 tokens differ from Python on .NET Framework 4.8.
- Step 3 S1c contract (ADR-0012): new schema `run-journal` (`urn:tekla-harness:schema:run-journal:0.1`)
  and example — one journal per lot and run (`run-journal-<RUN_ID>.json`), invocations with
  per-object intent/inserted/tagged states, failure and conflicts; `run_id` pattern
  `^[A-Z0-9][A-Z0-9_-]{0,31}$` added to `common`.
- Step 3 S1c C# (ADR-0012): `TeklaCore` run journal reader/writer (strict JSON, bytes identical to
  Python `json.dumps(indent=2, ensure_ascii=False)`, golden fixture `tests/fixtures/run-journal/`,
  atomic replace with retries), per-model run lock (named mutex on the normalised working-copy
  path; held → exit 3), model snapshot types (three-state tags, GUID presence) and a pure
  `ResumePlanner`: skip, retag, create or conflict per member, refusals before planning (spec hash,
  model path, header, any rollback, untrusted lookups), matching within 0.1 mm (+1e-6 rounding
  allowance), kind, rotation 0.01° and class.
  After independent review: lookups and tags that disagree in either direction refuse (exit 3);
  a `running` invocation or an invocation on another model refuses (5); the journal replace keeps a
  `.bak` and a leftover temp/backup without its journal refuses (5); `ResumePlan.Executable` and
  `MemberAction.Blocked` stop a plan with conflicts from being partly executed; the lock uses
  `Global\` and refuses a release on another thread.
- Versioning note: the reading-toolchain schemas above have not been released; they stay `0.1` and their
  changes are recorded here until the first tagged release, from which every change bumps its `$id`
  (AGENTS.md). Pending engineer confirmation.
- Legacy-font gate (EVAL-1 fix 2): `text_gate.meaning_block_reason(entry)` decides whether meaning may be
  taken from a text-index entry: pure-ASCII raw text is allowed; other text is blocked
  (`knowledge_conflict`, `encoding_proposed`, `encoding_contradiction`, `encoding_unknown`) until its
  encoding is settled by a font name, code-point evidence or an approved knowledge row. Used by
  sheet-text, find-text, list-sheets, `harness finding` and `harness marks`.
- Reader tools (EVAL-1 fix 2, F-08..F-11, F-25): every `sheet-text` entry carries `meaning`
  (`allowed | blocked`) and `blocked_reason`; `sheet-text` reports `legacy_font_gate` (blocked count, by
  reason, styles, the file's encoding question ids); `list-sheets` titles rank title keywords first
  (Vietnamese and English), skip grid labels, bare numbers and years, and carry `entry_id`, `meaning`,
  `matched_keyword`, plus `blocked_text_count` per sheet; `sheet-text` warns on stderr and in `warnings`
  when it truncates, and `--contains` without `--max` is unbounded. New `harness find-text <work_dir>
  --contains TEXT [--file F] [--max N]` searches every sheet of every file in one call and counts the
  blocked entries it could not search reliably (new `find_text` kind in the `sheet-text` schema).
  Changed: `sheet-text` entries use `entry_id` instead of `id`.
- `harness finding add | withdraw | list` (`findings.py`, new schema `reader-findings`, EVAL-1 fix 3):
  the drawing-reader agent records each judgement (sheet class, general-note item, structural-system
  claim, cross-check) in `work/reader-findings.json`, tied to text-index entries. `add` checks the file,
  entries, sheet membership, live question ids, note values as verbatim quotes, and the legacy-font gate
  (a blocked entry backs no finding; the refusal names the font questions to answer first). Confidence
  is the minimum of the cited entries, may only be lowered, never `high`. Ids `F-001..` are never reused;
  `withdraw` keeps the finding with its reason; `list` flags findings whose file changed as `stale`; one
  active `sheet_class` per sheet; an identical active finding returns its id (`already_recorded`).
- `harness marks <work_dir> [--input-dir DIR]` (`marks.py`, new schema `marks`, EVAL-1 fix 4): member
  marks (`D1`, `D1.1`, `D1-1`, `D1a`, `mark(b x h)` with b and h as written, never converted), member-type
  words before a mark (`DẦM D1.1`, `COLUMN C1`) as `title_member_word` evidence (never a prefix meaning),
  schedule tables from the DXF line grid or text alignment under a whole-cell header keyword, and
  plan-to-schedule matching by exact key only (NFC + casefold, whitespace removed). Separator or
  leading-zero variants (`D1.1`/`D1-1`) are never merged: one blocking `mark_notation_equivalence` per
  file; a plan section that differs from its schedule row raises a blocking `mark_size_conflict`; a
  keyword table that cannot be read raises a non-blocking `schedule_table_unparsed`. Tables whose header
  the font gate blocks are reported `header_blocked` and never matched. Writes `marks.json` and
  `marks-questions.json`; status tracks freshness.
- Gate-1 question noise (EVAL-1 fix 5, F-04, F-05, F-26): `units_confirm_all` is the only blocking units
  question per probed file: the probe's `units_conflict` / `units_suspect` / `units_unknown` become its
  refs (where/found verbatim) and `grid_units_doubt`, `grid_system_units_unconfirmed` are non-blocking
  evidence; a units check closes only on that question's structured `unit=`. New blocking
  `units_answer_contradicts_evidence` (grid-system) when the answered unit fails the `units_suspect`
  magnitude test (`units.dimension_median` now in the probe and inventory); it closes by re-answering, or
  by confirming the same unit. X/Y is asked once per grid system: `grid_system_axis_unassigned` takes
  `--value dir1=X|Y --value dir2=X|Y`, is bound by key and blocks only for selected, unassigned systems;
  `grid_family_axis_assignment` is non-blocking. `grid_system_select` takes `separate=S001,S002`; systems
  outside `systems=` raise no blocking question; `grid_system_conflict` is one question per pair, closes
  only via `systems=` or `separate=` (never answer text), and `harness answer` refuses it. Status reasons
  name the question id to answer. On the eval set, blocking units questions per file went from 5 to 1
  (267) and 3 to 1 (433, steel).
- `harness questions-md <work_dir> [--out PATH]` (EVAL-1 fix 1, F-07, F-22, F-24): renders `questions.md`
  (Vietnamese) deterministically from every question document, the registry, `answers.json`,
  `grid-systems.json`, `structure-summary.json` and the gate-1 reasons: summary, blocking then
  non-blocking open questions by topic and file, answered questions, stale answers. Refs verbatim, counts
  with "hiển thị n/N", the exact `harness answer` command with the values each code needs, proposals
  labelled "ĐỀ XUẤT — chưa xác nhận". The code-to-Vietnamese table `questions_md_vi.py` is proposed copy
  pending engineer review; a code without a row prints its English message and is listed in
  `untranslated_codes`.
- `harness ask`: `units_answer_contradicts_evidence` is owned by grid-system (exact codes now win over
  another producer's prefix).

- Drawing-reading skills active (engineer approval 2026-11-07, after EVAL-1, EVAL-2 and a
  skill-creator trigger check): `drawing-intake`, `structural-drawing-reader`,
  `drawing-analysis-report`, `tekla-conversion-plan` moved from `dwg-lab/proposals/skills/` to
  `.claude/skills/`; registered in the AGENTS.md skills table; preloaded through `skills:` in
  `.claude/agents/doc-reader.md` (first three) and `planner.md` (the plan). Trigger check, 2 runs per
  query: intake 10/10 and 6/6 on fresh queries, reader 10/10 and 5/6, report 10/10, plan 10/10; no
  near-miss triggered.
- Work-folder write lock (tool wave 2, ADR-0011, proposed): `worklock.work_lock` holds an exclusive OS
  lock on `work/.harness.lock` (POSIX `flock`, Windows `msvcrt.locking` on byte 0) for the whole run of
  intake, read-structure, callouts, marks, grid-system, answer, ask, finding add / withdraw and
  questions-md. A held lock is exit 3 at once, naming the holder (pid, host, command, start time) from
  `.harness.lock.json`, which the holder removes before unlocking; no waiting, no stale-lock rule, the
  lock file is never deleted. A filesystem without lock support is exit 3 (never runs unlocked).
  Read-only commands (status, list-sheets, sheet-text, find-text, finding list, dimensions) and the
  path-based tools (validate, detect, dwg2dxf, read-dxf, extract-*, env-check) do not lock; every
  subcommand must be on one list (`cli.UNLOCKED_COMMANDS`, test-checked). A writer whose work folder does
  not exist is refused with exit 2 before it runs ("not a folder"). The holder record names its
  `platform`; a record from the other OS (WSL vs Windows, whose locks do not see each other) refuses the
  lock with exit 3 and says how to clear a stale one. Intake now resolves its converters before it reads
  the work folder's registry, and creates the work folder just before locking it.
- Tool wave 2 seam (EVAL-2 fixes; the packages fill in the behaviour). Schemas, all additive and optional,
  `$id` still `0.1` (engineer, 2026-11-07): `text-index` decode source `style_family` and flag
  `legacy_ascii_suspect`; `dxf-probe` hint `matched.field` `family`; `sheet-text` block reason
  `legacy_ascii_suspect`, `list_file.blocked_text_count`, sheet id `unassigned` with null layout and bbox,
  `query.unassigned`, `find_text.counts.unassigned_entries_searched`; `levels` `blocked_candidates`;
  `marks` `table.blocked_columns`, match `size_compared` / `size_not_compared_reason`, `summary.by_sheet`,
  `summary.size_comparisons`; `callouts` `summary.unparsed_by_reason` and reason `legacy_ascii_suspect`;
  `intake` question `closed_by` and ref `families`; `answers` `answered_by_role` (engineer | simulated) and
  `file_set_relation` values; `reader-findings` `decoded_by` and list `summary.by_class`; `grid-system`
  `conflicts[].question_id` and `file_sets`; `status` `gate1.closed` and `gate1.non_engineer_answers`. New
  schemas `dimensions` and `supplements` with examples. Shared code: `questions.FILE_SET_CODE`, `ROLES`,
  `Closure`; `lifecycle.closures` and `supplements.load_supplements` stubs (no closure, no supplement
  yet); `harness status` leaves closed questions out of the blocking counts and makes a `simulated`
  answer to a gate-relevant question a gate-1 reason (an answer without a role still counts as the
  engineer's); `harness questions-md` renders closures and supplements and has a `file_set_relation` row;
  `harness answer --role engineer|simulated` and `file_set_relation` values (every file of the question
  once); `harness ask` gives `member_mark_prefix_meaning` to marks and `file_set_relation` to intake;
  `read_dxf.measure_dimension`. Not implemented yet (exit 3): `harness dimensions`, `sheet-text` /
  `find-text --unassigned`, `harness ask --supplement` / `--withdraw-supplement`.
- `marks` schema: `question_counts` accepts `member_mark_prefix_meaning` (tool wave 2, D6: marks asks the
  plan-mark prefix question instead of callouts); `anchor_entry_id` and `columns.role` descriptions cover
  line-grid tables found from a mark text with no header keyword. `$id` stays `0.1`.
- Tool wave 2 package P3, answer provenance and reader supplements (EVAL-2 fixes 10 and 7):
  - `harness answer --role engineer|simulated` is required (exit 2 without it). Every `harness answer`
    command that `harness status` and `harness questions-md` print names `--role engineer` after `--by`.
  - Gate 1 no longer counts an answer recorded without a role (DESIGN D4): like a `simulated` answer to a
    question of intake, read-structure, grid-system or the reader, it is a gate-1 reason naming its
    question id (`gate1.non_engineer_answers`, role null) until the engineer answers again.
  - The same holds for a non-engineer active answer whose question is not live (no registry entry, or
    obsolete) when a gate check still reads its code from every active answer (units, grid-system): the
    reason names the answer's key.
  - Review M1: every `harness answer` command in a gate-1 reason is introduced as the engineer's own step
    (`the engineer runs: …`), the role reason says the engineer must answer again themselves, and
    questions.md labels the command as one the engineer runs and an agent never runs instead.
    `record_answer` takes `role` as a required keyword (no default; None is a usage error).
  - Review M2: `harness status` and `harness questions-md` accept a `lifecycle.closures` closure only when
    its reason fits the closed question (not_selected / separate: grid-system `grid_system_conflict`;
    units_answered: read-structure `grid_units_doubt`; rejected_systems_only: read-structure `grid_*`
    except `grid_gate1_confirmation`; other_file_set: none yet, nothing derives it), the question is not
    the reader's, and it names a live question of the code the reason needs (`grid_system_select`, or
    `units_confirm_all` for units_answered) with an active engineer answer. A refused closure leaves the
    question open and is a `closures:` gate-1 reason. A closure a producer already wrote (registry
    `blocking: false` plus `closed_by` in the question document) is checked against the same contract;
    a refused one counts the question as blocking again, in status and in questions.md. An unreadable or
    invalid document the lifecycle reads is exit 1 in `harness status` and `harness questions-md`.
  - A grid-system conflict pending on an unanswered `file_set_relation` question (non-blocking, no
    `closed_by`) gets a gate-1 reason that names that question and its answer command, instead of the
    `separate=` advice.
  - `harness ask --supplement Q-id --where --found --text [--file --sheet]` adds the reader's evidence to a
    producer's question in `reader-supplements.json` (key = target key, file, file sha256, where; prints
    `new` or `already_supplemented`); exit 2 for an unknown, obsolete or reader-owned target, a withdrawn
    place, or `--code` / `--blocking`. `--withdraw-supplement KEY --reason R` keeps it as withdrawn. A
    supplement whose target goes obsolete reads as `stale`; questions.md shows active ones under the
    question. The target's blocking flag, answer and refs never change.
  - `harness finding add` records `decoded_by`: per decode source and knowledge pattern of the cited
    entries' runs, the knowledge row's status and decision date. `finding list` marks a finding `stale`
    when that row's status or date changes or the row is gone; such a finding no longer counts as a
    duplicate or as a sheet's active class.
  - `harness finding list` prints `summary.by_class`: the listed `sheet_class` findings per class, counting
    only active, non-stale ones (a withdrawn or stale class would count a sheet twice).
- Tool wave 2, package P4 (marks and dimensions):
  - `harness marks` gates schedule tables per column (EVAL-2 fix 8): only a blocked mark-column header
    blocks a table; any other blocked header cell is listed in `table.blocked_columns` and the table is
    read. A line-grid table without a keyword is read on the column it was found from (confidence low)
    unless that column's header is blocked. Every matched mark says `size_compared`, else
    `size_not_compared_reason`; `summary.size_comparisons` counts them.
  - Counts the report asks for (EVAL-2 fix 11): `harness marks` `summary.by_sheet` (plan marks, tables,
    header-blocked tables, rows, unparsed tables, blocked marks per detector sheet; sheet null for texts on
    no sheet) and `harness callouts` `summary.unparsed_by_reason` (unparsed candidates per reason).
  - `harness dimensions <work_dir> <file> [--sheet ID | --unassigned] [--layer L] [--max N] [--input-dir
    DIR]` (EVAL-2 fix 11), read-only: every DIMENSION of one drawing, also inside nested INSERTs (virtual
    copy, handle null, `block_path`), with what it measures next to its printed or override text and the
    probe's text rule and status, plus layer and detector sheet. Values as stored, never converted;
    `units` reports the declared and the answered unit only. A native DXF needs `--input-dir` (exit 2).
    The layer is the effective one: inside a block, layer 0 takes the layer of the placing INSERT
    (recursively), so `--layer` finds it; the stored layer is not reported (one layer field in the schema).
  - `member_mark_prefix_meaning` moves from `harness callouts` to `harness marks` (EVAL-2 fix 1b): one
    blocking question per file with one subject per prefix of its plan marks (upper-cased; titles such
    as `DẦM D3` count, schedule cells do not); `marks.json` `question_counts` counts the prefixes. Callouts
    still lists `member_mark` candidates but no longer asks; an answer to callouts' old question goes stale
    once at the next callouts run and the engineer answers the marks question (default D6, reversible).
- Tool wave 3 (EVAL-3 fixes; the packages fill in the behaviour):
  - Tool wave 3, seam. Schemas, all new fields optional, `$id` still `0.1`:
    - `answers`: `grid_system_missing` values `dir1_labels`, `dir1_spacings`, `dir2_labels`,
      `dir2_spacings` (arrays; both directions, or none) and optional `sheet` (ADR-0013 §2);
      `grid_answer_contradicts_drawing` takes no value.
    - `question-registry`: `obsolete_reason`, only on obsolete entries.
    - `grid-system`: question codes `grid_system_missing` and `grid_answer_contradicts_drawing`; system
      `source` (`detected` | `engineer_answer`) and `source_answer` (question id, key); a system built from
      an answer has no view, contributor or representative family, and its provenance method is
      `engineer_answer`; status `proposed_simulated` for `units.status`, `axis_assignment.status` and
      `files[].units_answer.status`, units reason `units answered by a non-engineer role`; conflict
      `proposed_closed_by` (what a non-engineer select answer would close; it closes nothing).
    - `marks`: `summary.mark_sets` (`file`, `family`, `members`, `complete`, `source`); `compared_with` on
      matched, schedule-only and plan-only marks (`schedule` | `detail_heading`, plus `none` for plan-only),
      `detail_headings` refs (a heading-only match needs no schedule row) and the per-file
      `detail_headings` count.
    - `callouts`: candidate `unparsed_code` (reason family, incl. `symbol_glyph_unverified`), top-level
      `rejected` matches with `reason_code` and `reason`, summary `unparsed_by_code`, `rejected`,
      `rejected_by_reason`, question count `callout_unparsed`.
    - `sheet-text`: `query.region`, `region` and `rows` (cells of entry ids with display text and the
      gate's meaning) for a region read; find-text `counts.blocked_in_scope` (query-independent); one of
      it and the deprecated `blocked_entries_not_searchable` is required.
    - `intake` question `places` and `amendments` (reader questions); new schema `reader-questions`
      (`harness validate reader-questions`), with example; examples `grid-system-answer` and
      `sheet-region`.
    - `status`: `gate1.closed` stays optional until `harness status` always writes it.
  - Tool wave 3, seam: a registry entry that a producer run makes obsolete records `obsolete_reason`
    (W5), first match wins: its input file was removed, or changed (asked again under a new key), or
    the producer declared its code superseded by an answer to another code (`Ledger.sync(...,
    superseded_by={code: answer_code})`, only while such an answer is active), else the latest run no
    longer raises it. Set on the transition, kept while obsolete, dropped when the key is raised again.
  - Tool wave 3, seam: new question codes `sheet_number_gap`, `callout_unparsed`, `legacy_ascii_text`,
    `grid_system_missing`, `grid_answer_contradicts_drawing` (shared constants in `questions`, with the
    `grid_system_missing` value keys) and their proposed Vietnamese rows in `harness questions-md`, whose
    answer command for `grid_system_missing` prints the ADR-0013 keys. New flags, parsed and checked
    (exit 2 on misuse) but not implemented yet (exit 3, nothing written) until their package lands:
    `harness ask --amend Q-id [--text T] [--places P ...]` (package C; `--places` only with `--amend`) and
    `harness sheet-text W FILE SHEET --region x0,y0,x1,y1` (package T; four finite numbers, x0 < x1,
    y0 < y1, a sheet id and no `--unassigned`; write negative coordinates as `--region=-5000,...`,
    which the help says, because argparse takes a `-` value after a space for an option). `harness find-text` warns with `blocked_in_scope` when the
    output has it. `harness answer --help` names the `grid_system_missing` keys.
  - Tool wave 3, package S (sheets + levels):
    - Levels: a storey name needs a number or a word that names one storey (`tầng 3`, `sàn tầng 3`,
      `tầng trệt`, `mái`, `2nd floor`, `roof`); a bare `sàn` (slab), which ends slab-plan titles and
      quantity headings, names nothing. So `level_name_conflict` is no longer raised between slab-plan
      titles (290: three false conflicts; 267: one), and storey heights fall back to the asked, low
      rule instead of skipping unnamed levels (290: +7.300 is no longer skipped).
    - Levels: a sign with one space before the digits right after `(` is a sign, so
      `(+ 6.00M LEVEL)` gives the level +6.000 (161 and Steel_01). Elsewhere a spaced sign after other
      text is still read as a dash (`TẦNG 2 - 3.600`).
    - Sheets: the sheet-number pattern (used only when no title field gives one) looks in the title-block
      corner, the last quarter of the frame along the text's reading direction and its lowest fifth,
      not the lower-right quadrant. A portrait frame is also read at 90 and 270 degrees. A member mark
      is never a number: a code that appears twice on its sheet, has a mark family on its sheet
      (`gĐ-1`, `gĐ-2`), or appears twice outside every title block. Among several corner codes a
      position repeated in other sheets' corners wins, then the tallest; a tie stays a
      `title_field_conflict`. Every corner code not taken is listed in `warnings` with its reason. A
      model text shown on a layout sheet is never in that sheet's corner. Corpus: 285 model#03
      `kc- 03`, 290 model#16-18 `Kc - 13` and 267 model#16-20 / #43-44 are now read; the false
      `gĐ-3` on 286 model#04 is gone.
    - Sheets: new non-blocking question `sheet_number_gap`, one per file, when the chosen sheet numbers
      of a letter series skip numbers that no sheet of any series carries (one counter may run over
      several series, as Kc and KT on 290). `found` gives each missing number or range with the sheets
      on each side, and the sheets without a detected number. `KT 1/18` counts as 1, `KC-05A` as 5;
      other values are left out. Corpus: 290 `missing 25`, 461 `missing 6-9` (three sheets there have
      no detected number); no other known file.
  - Tool wave 3, package T:
    - W4 (safety): `harness find-text` and `harness sheet-text --contains` never match a blocked
      (legacy-font) entry, on its stored, decoded or any normalised text; before, typing the stored legacy
      form of a word (`thèng kª`) found and in effect decoded blocked text (EVAL-3 F-B17). Blocked entries
      are reached by entry id or sheet listing only. find-text reports `counts.blocked_in_scope`, the
      blocked entries of the searched files or sheets whatever the query, and no longer writes the
      deprecated `blocked_entries_not_searchable`; hits are always `allowed`. sheet-text `--contains` warns
      how many blocked entries of the sheet it never matches.
    - W3: `read_dxf.legacy_ascii_questions(text_index, file, probe text_styles)` builds the
      `legacy_ascii_text` questions of one file: one per text style holding `legacy_ascii_suspect`
      entries, not blocking, `count` = the style's flagged entries, the first 5 listed by entry id and
      quoted as stored, the message and every ref's `where` naming the style, its font file and its
      TrueType family (`harness questions-md` shows the refs, not the English message). `harness
      intake` raises them after the `encoding_unknown_non_ascii` questions (none for a file whose text
      index is unreadable); on 267 one question covers the 786 ROMANS entries, on 461 two questions
      cover 14. The `questions.py` docstring and the intake schema descriptions now say these questions
      (and `callout_unparsed`) are one per file and style (or reason family), not one per code and
      file. The sheet-text
      `legacy_font_gate.question_ids` lists the file's live `legacy_ascii_text` questions when the sheet
      has `legacy_ascii_suspect` entries (encoding questions still only when an encoding answer can lift
      a reason); find-text `notes` names the questions covering the blocked entries in scope; `harness
      finding` counts `legacy_ascii_text` as a font question when it refuses a blocked entry.
    - a5: `harness sheet-text W FILE SHEET --region=x0,y0,x1,y1` (absolute coordinates, the entries' x/y
      and the list-sheets bbox) returns the sheet's entries whose insertion point lies in the box, edges
      included, as `rows` of `cells`: rows as the reading order with the whole sheet's row tolerance
      (0.6 x its median text height), a new cell where the insertion-x gap to the left neighbour exceeds
      that tolerance, each cell with its entry ids, joined display text, meaning and x span; no blank
      cell is invented. `entries[].row` indexes `rows`; `counts.assigned` and `legacy_font_gate` stay the
      whole sheet's; `--contains` and `--max` work as without a region. A box that misses the frame is
      warned about. On 286 the `Ø<10mm` row reads `Ø<10mm | CI | 225` (T001075, T001074, T001072).
  - Tool wave 3, package G:
    - `harness read-structure` finds grid bubbles drawn as an ARC that is a full turn within
      `FULL_ARC_GAP_DEG` (1 degree; EVAL-3 285 and 286 block `SADF`, an arc from 90.00006 to 90.0000031
      degrees), and a grid line drawn through the bubbles at both of its ends and on to the frame pairs
      with them when two bubbles of one label, at least `MIN_AXIS_LENGTH` radii apart, both lie on it
      (286 model#05). A ratio-1 ELLIPSE is a circle only when it, too, is a full turn (a door swing in an
      unevenly scaled block was counted). 285 now gives 1-2-3-4-5 = 3130/3540/3520/4590 x A-B-C =
      4250/3730 (and 4254 on model#03), 286 gives 1-2-3 = 3400/3980 x A-B-C = 4840/4190 on 13 sheets.
    - `harness grid-system` reads only the engineer's answers (`answered_by_role` engineer) as decisions.
      Units or Tekla X/Y that only a simulated or role-less answer gives are `proposed_simulated`
      (`units.answered` names the proposed unit; nothing is converted or assigned; the X/Y question keeps
      blocking); a `grid_system_select` answer from another role selects nothing and records what it would
      close as `proposed_closed_by` (the conflict keeps blocking); a `file_set_relation` answer from another
      role leaves the file sets pending; a `units_answer_contradicts_evidence` confirmation counts only from
      the engineer. Each such answer is named in `warnings`. A conflict that the engineer's file-set answer
      retires records `obsolete_reason` "superseded by an answer to file_set_relation".
    - ADR-0013 route in `harness grid-system`: every read drawing file that no selected two-direction
      detected system covers gets a blocking `grid_system_missing` question (`found` quotes the bubbles,
      labels and axes grids.py found; the message names the file's detected systems and why none is
      usable, and the `--value` keys). An active answer by the engineer with `dir1_labels`,
      `dir1_spacings`, `dir2_labels`, `dir2_spacings` (and optional `sheet`) builds a system with
      `source: engineer_answer` and `source_answer`, numbered after the detected systems; it is selected,
      given Tekla X/Y and units like a detected one, and the question stays raised while that answer is
      active, so the answer and the system survive reruns. A simulated, role-less, words-only or malformed
      answer builds nothing and is warned. The given spacings are checked against the linear dimensions
      between two of the given axes (labels case-blind, spans as sums, drafting tolerance): a
      disagreement raises a blocking `grid_answer_contradicts_drawing` quoting both values; a grid with no
      dimension to check is warned. `grid_system_missing` answers are part of the answers digest.
  - Tool wave 3, package C:
    - `harness answer` takes the `grid_system_missing` values (ADR-0013 §2): `dir1_labels`,
      `dir1_spacings`, `dir2_labels`, `dir2_spacings` together, optional `sheet`, or no value for an answer
      in words only. Per direction at least two distinct, non-blank labels and exactly one spacing fewer,
      each a plain decimal > 0 (no sign, exponent, `inf` or `nan`); anything else is exit 1, nothing
      written. Stored in `answers.json` as arrays: labels as strings, spacings as numbers (`3130` stays an
      integer, `3540.5` a float). The answer itself builds nothing; `harness grid-system` reads it.
    - `harness ask` refuses the producer codes `legacy_ascii_text` (intake) and
      `grid_answer_contradicts_drawing` (grid-system; it no longer falls under read-structure's `grid_`
      prefix) as reader codes (exit 2).
    - `harness ask --amend Q-id [--text T] [--places P ...]` works (it was a stub, exit 3): it changes a
      live, unanswered reader question in place. The id, key and ref stay; the new message and/or `places`
      replace the old ones, which are kept in `amendments` (`at` = the registry run counter, bumped once
      per amendment; only what changed is recorded). The same values again change nothing (status
      `unchanged`). Refused with exit 2 for an unknown, producer, withdrawn or answered question (any
      active answer, simulated included). A live entry missing from `reader-questions.json` is exit 1.
      `harness ask` now checks `reader-questions.json` against the `reader-questions` schema before it
      writes it.
    - `harness status` always writes `gate1.closed`, as `[]` when nothing is closed (W5).

### Changed
- Question lifecycle (tool wave 2, EVAL-2 fix 5):
  - `grid_system_conflict` keeps its Q-id across a units answer and a select rerun: its key is built from
    both sides' file, view and family ids and their shared labels; the system ids and the spacing
    differences (in mm once units are answered) moved into the message. Existing answers to a conflict go
    stale once (they never closed it). A conflict the `grid_system_select` answer settles carries
    `closed_by` {select question id, not_selected | separate}, `conflicts[].question_id` names its question,
    and a system's `conflict` flag stays only while one of its conflicts is open. `lifecycle.closures`
    returns these closures from a fresh `grid-systems.json`.
  - `harness intake` raises one blocking project-level `file_set_relation` question when two or more DXF /
    DWG files were read (one ref per file with its sha256; a file added, removed or changed asks again).
    `harness grid-system` reads its answer (`set1=a.dwg,b.dwg set2=c.dwg`): grids of two sets never merge
    into one system and are never compared; `grid-systems.json` records `file_sets` (pending, answered or
    single). While it is open, a conflict between two systems with no file in common does not block
    ("pending Q-x"); the answer is part of the answers `harness status` checks grid-systems.json against.
  - `harness read-structure` grid refs name the grid `families` they cite (the last listed ref of a
    truncated question also carries the unlisted refs' families; none when they are not all known).
    `lifecycle.closures` closes a read-structure grid question (`rejected_systems_only`) only when every
    family it cites belongs to a system the `grid_system_select` answer leaves out; a family of a selected
    system, of no system, or a ref without families keeps it open; `grid_gate1_confirmation` is never closed.
  - `grid_units_doubt` is closed (`units_answered`, naming the units question) once the same file's
    `units_confirm_all` has an active answer.
- `knowledge/font-encodings.csv`: the three seed rows are approved by the engineer (2026-11-07) after
  reading decoded samples: `VHARIAL.TTF` and `vntimeh.shx` = TCVN3, `vn_vni.shx` = VNI. Text in these
  fonts is now decoded instead of blocked by the legacy-font gate. The engineer also endorsed the
  `.Vn*…H` = TCVN3 capital-font naming convention that `encoding.font_hint` already applies.
  Test fixtures that need a blocked font now pin their own proposed-row table instead of the shipped one.
- Tool wave 2, package P1 (fonts and text access; EVAL-2 fixes 2a, 2b, 1a, 4, 11):
  - `encoding.font_hint(style, font_file, family)` also reads the text style's TrueType family (ACAD
    XDATA), after the style name and the font file: a `.Vn*` family gives TCVN3 and a `VNI-*` family VNI;
    a Unicode-looking family decides nothing (a legacy font file may carry one; the knowledge table then
    decides). The `H` capital-font rule applies to the family too (default D3, reversible); when the
    style name and the family disagree on case, the hint is null. `harness extract-text` records such a
    decision as `decode.source` / `run_details[].font_source` `style_family`; `harness read-dxf` lists
    `matched` field `family`. A `.Vn*` family now decides before an approved font-file row, so those
    styles carry no `knowledge_patterns`.
  - `harness extract-text` flags `legacy_ascii_suspect` (confidence low) on pure-ASCII text that looks like
    Vietnamese written in ASCII by a legacy font: a slash before a letter or brace (`4/g14`, `BT LO/ST`;
    not before a unit such as `kG/cm2` or a word of 3+ letters such as `Cu/PVC`) or an uppercase tone
    letter S F R X J after a vowel (`chi tiESt`, `haFn`). Only runs in a TCVN3 / VNI font, or in an
    unknown-encoding font that also holds non-ASCII text of unknown encoding, are judged (default D2,
    reversible: suspect shapes only, not all ASCII). The legacy-font gate blocks such text with reason
    `legacy_ascii_suspect`, ahead of the ASCII rule.
  - Level extractor (`read-structure`) applies the legacy-font gate: a blocked text gives no candidate,
    level, storey height, storey name or question; each level-shaped value in it is listed in
    `levels.json` `blocked_candidates` (entry id, line, value as stored, reason; count in
    `summary.blocked_candidates`), and `level_none_found` says how many were held back. A literal `±`
    in an unknown-encoding font is non-ASCII, so it is blocked too (`%%p` is read as before).
  - `harness sheet-text <work> <file> --unassigned` (instead of a sheet id) returns the entries on no sheet
    or on several as sheet `unassigned` (null layout and bbox; `space` lists their spaces; model space
    first, rows numbered on across spaces), and `harness find-text --unassigned` searches only those
    entries (hits with sheet id `unassigned`, `counts.unassigned_entries_searched`): the text of a file
    without a detected sheet is now reachable. A sheet id together with `--unassigned` is exit 2.
    `find-text` counts unassigned entries once each (an id both unassigned and ambiguous was counted twice).
  - `harness list-sheets` gives each listed file `blocked_text_count`: its text-index entries the
    legacy-font gate blocks, on a sheet or not (null for a skipped file).

### Fixed
- Tool wave 2, package F2 (review of P4, marks and dimensions):
  - `harness dimensions` measures block content on its block definition (ezdxf `origin_of_copy`), not on
    the virtual copy: a linear dimension stored without an angle in an INSERT rotated by 90 degrees
    measured about 0 (sample 270: 40 rows reported `ok` against group 42 = 4000). The copy still gives
    the sheet and the layer; an INSERT's scale no longer changes the measured value.
  - `harness dimensions` and the dxf-probe `dimension_audit`: a row whose group 42 disagrees with the
    measurement is `not_compared` with a note, whatever its text rule (measured-text rows were `ok`).
  - `harness marks`: a line-grid table without a keyword is read on the seed's column only when that
    column's header cell holds no text and at most half of its allowed cells are integers; only its
    mark-shaped cells become schedule marks. Otherwise it is header-blocked, as before wave 2 (sample 270:
    bar schedules keyed on the 'STT' row numbers, keys '1'..'11', '(sl:01)'; sample 461: plumbing lists
    whose first data row sat in the header band, keys 'd110', 'selta').
  - `harness marks` size reasons are exact: "the schedule header cells that could name a size column are
    blocked" only when a blocked column could give the missing size (its readable cells are numbers or
    `b x h` values, or none is readable), else "the schedule table has no size column"; a row with no
    cell in its size columns says "the schedule row has no size cells" (was "... are not numbers");
    `blocked_columns` no longer lists a header cell that lies in no column (`column: null`).
  - `harness dimensions` rows carry `text_entry` (schema `dimensions`, additive optional field, `$id` still
    0.1): the text-index entry of the dimension's own text and the legacy-font gate's verdict (`meaning`,
    `block_reason`); null for a text that only shows the measurement. An override text the gate blocks is
    not read (override_value null, status `not_compared`, note). A text with no index entry is counted in
    `warnings`. Sample 270: 75 of 75 texts linked, 15 blocked (were `not_numeric`).
- Reading toolchain, after an independent review of the EVAL-1 wave:
  - `harness marks`: a rotated header keyword (or one that is not a cell text) no longer crashes the run;
    the table becomes a non-blocking `schedule_table_unparsed`. Questions no longer quote table ids, so a
    table added to one file does not re-key another file's `mark_*` questions (their answers are asked
    again once).
  - Units contradiction also tests the median grid spacing under the ANSWERED unit (0.5 m to 30 m,
    `grids.implausible_spacing`), not only the median dimension; `grid-systems.json` files carry
    `grid_spacing_median`; `harness status` mirrors the test.
  - `harness status` reasons print `harness answer <work_dir> <id> ...` (the work folder was missing),
    one question per command.
  - `harness callouts` applies the legacy-font gate: blocked text yields no candidate and is listed in
    the new `blocked_entries` of `callouts.json` (a literal `4Ø16` in an unknown font was a rebar callout).
  - `harness answer`: `systems=` must name systems the select question lists.
  - `grid_system_select` keys include each system's file and its sha256, so systems of two files cannot
    swap S-ids under one key (existing select answers go stale once).
  - `harness finding`: a `note_item` quote must start and end at token boundaries; a write error exits 3;
    a document whose `next_id` is not above every `F-` id is refused.
  - `harness questions-md` prints reader questions as written (never "chưa có bản dịch"); `harness ask
    --text` is the Vietnamese question the engineer reads.
- Tool wave 2, review fixes, package F1 (legacy-font gate and grids):
  - Capital-font hint: a style name or family gives a case hint only when it is itself a font name
    (`.Vn`/`Vn` then letters, digits, spaces). Style names such as `VN-ABC` or `VNARIALH-BOLD` no longer
    veto their family's hint (`.VnAvantH` → capital); `vntimeh.shx` used as a style name no longer reads
    the `x` of its extension as "not capital" (its case is now reported as uncertain).
  - `legacy_ascii_suspect` (`harness extract-text`): an unknown-encoding run also counts as legacy when its
    style name, font file or family (inline font: its name) looks like a legacy Vietnamese font
    (`encoding.legacy_font_name`: `vncc-rms.shx`, `vnsimli.shx`), with no non-ASCII sibling needed; the
    sibling rule is keyed by the font file, so styles on one file share the evidence. New shape: an
    uppercase vowel between lowercase letters (`dAy`, `tEn`, `cOng trInh`). No longer suspect: `/a` plus a
    digit (`%%c8a100/a200`, `1:100/a3`), one letter ending the token after a slash (`C/C`, `N/A`, `b/h`,
    `1/A`) unless two letters stand before it (`BO/R`), and CamelCase words (`TieRod`, `HoleSize`). On
    dwgshare 461 the 16 Telex-style texts of the `vncc-rms.shx` / `vncc-sim.shx` styles are blocked
    (except `s.l`, `stt`): `haFn 200` is no longer two plan marks with a `HAFN` prefix question.
  - A TrueType family no longer silently overrides an approved knowledge row: when the family decides and
    an approved row for the style or its font file gives another encoding (or approved rows disagree),
    `harness extract-text` decodes nothing and flags `knowledge_conflict` (the gate blocks it), and
    `harness read-dxf` gives no hint and asks `font_encoding_conflict`. An agreeing row changes nothing.
    This replaces P1's "a `.Vn*` family decides before an approved font-file row" for disagreeing rows.
  - Grid extractor (`read-structure`) applies the legacy-font gate: a label-shaped text in a bubble that
    `text_gate` blocks (`4/g14`, `2/G20` in a TCVN3 style) is never a label or an axis; it is listed in
    `grids.json` `blocked_candidates` (entry id, value as shown, reason, sheet; count in
    `summary.blocked_candidates`), and a family line ending in such a circle asks `grid_label_missing`.
    `grids` schema: both fields added, optional (`$id` stays 0.1).
  - `harness sheet-text` / `find-text`: `legacy_font_gate.question_ids` lists the file's font questions only
    when some blocked entry has a reason an encoding answer can lift; a sheet whose blocked entries are all
    `legacy_ascii_suspect`, or that has none, lists no question. Schema descriptions of `question_ids` and
    `legacy_ascii_suspect` updated (no structural change, `$id` stays 0.1).
- Tool wave 2, package F3 (review of gate 1 and questions.md):
  - Only the engineer's answer settles a question of intake, read-structure, grid-system or the reader:
    a simulated or role-less answer leaves it in `blocking_open` / `blocking_open_ids`, out of `answered`,
    and in questions.md section 2, where the answer is shown labelled "(mô phỏng)" or "(chưa rõ vai
    trò)". Every non-engineer answer questions.md prints carries that label.
  - questions.md no longer says a grid-system conflict was "closed by the grid_system_select answer"
    when it is only non-blocking while the file sets are asked: it says the conflict waits for the
    `file_set_relation` question named in grid-systems.json `file_sets`. Any other open, non-blocking
    conflict shows how to close it.
  - Every gate-1 reason that tells someone to answer says the engineer does it (`the engineer answers …`,
    `the engineer says …`, `the engineer runs: harness answer …`): the select, axis, conflict, file-set,
    units-disagree and units-contradiction reasons; the conflict reason now prints the select answer
    command. questions.md "Cách đóng" lines carry "kỹ sư tự chạy, tác tử không chạy thay".
  - `harness status` validates each question document it reads for written closures against its schema:
    a damaged one (e.g. a list as a question key, an unknown closure reason) is exit 1 naming the
    document, not a traceback.
  - An unreadable DXF/DWG no longer gets the units reason "rerun harness intake", which no rerun clears:
    it stays a gate-1 reason through its own blocking intake question (`read_failed`,
    `conversion_empty`, `no_reader_implemented`) until the engineer answers it, and is a `files:` reason
    when no such question is live.
  - `harness grid-system`: a system's `grid_system_axis_unassigned` question is keyed by its representative
    families (`where` = `<file> <view>/<family> x <view>/<family>`), not by its positional system id, which
    moves to the message (`Grid system S00n: …`). Adding an unrelated drawing file no longer re-asks it or
    leaves the engineer's X/Y answer stale. Existing X/Y answers go stale once, on the first rerun.
  - `status` schema: the `blocking_open` / `answered` descriptions say that only the engineer's answer
    counts for those producers; the `grid-system` example shows the new axis `where` and message (no
    structural change, `$id` stays 0.1).
- Schema `pattern` now has ECMA-262 meaning in `harness validate` (JSON Schema 2020-12): Python's
  `$` matched before a final newline, so `"L1-C-A2\n"` passed the `spec_id` pattern; `.` no longer
  matches `\r`, U+2028 or U+2029. Applies to every schema (ADR-0010 Amendment 1 §10).
- `harness validate spec`: a file name that a receipt cannot record (backslash, non-UTF-8) is an
  invalid result instead of a traceback; an existing spec that cannot be read exits 3.
- `guard_tekla_write.py` now exits 2 (the blocking code) on any internal error instead of
  relying on an undocumented `onFailure` setting; the setting was removed.
- `guard_tekla_write.py` no longer blocks commands that only mention `tekla-cli` as data
  (`cat`, `grep`, `git commit -m`), and no longer lets a read hide a later unparsed write.
- Write guard no longer denies commands that only name a file containing `tekla-cli`
  (e.g. `sed -n 1,40p docs/tekla-cli-contract.md`); RTI-0005.
- Write guard now recognises the CLI under its .NET project name (`TeklaCli.exe`) and treats
  every `dotnet run|exec|watch` as a write; `dotnet build|restore|clean` stay allowed; RTI-0006.
- Forging a spec validation receipt is narrowed, not closed (RTI-0008): settings deny
  `Edit(**/*.receipt.json)` (covers Write, Edit, NotebookEdit and Bash redirection targets), and
  the write guard denies, for every agent including `builder`, any shell command that names or
  pipes `*.receipt.json` unless it only reads it. A script file that writes one is still not
  seen. `builder` no longer validates the spec itself; it checks that the receipt `doc-reader`
  wrote exists, and `tekla-cli build` checks that it matches.
- Write guard now treats a newline as a command separator: `cd x` + newline + a `tekla-cli`
  write passed for any agent (RTI-0009, critical).
- `workflow.md`: the lot loop is strictly sequential (lot n+1 waits for gate 4 of lot n).
- Added `PowerShell(...)` allow rules matching the existing `Bash(...)` ones.
