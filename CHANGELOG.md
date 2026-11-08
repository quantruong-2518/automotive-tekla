# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/).
Harness releases are tagged with their benchmark score (see `benchmark/README.md`).

## [Unreleased]

### Added
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

### Changed
- `knowledge/font-encodings.csv`: the three seed rows are approved by the engineer (2026-11-07) after
  reading decoded samples: `VHARIAL.TTF` and `vntimeh.shx` = TCVN3, `vn_vni.shx` = VNI. Text in these
  fonts is now decoded instead of blocked by the legacy-font gate. The engineer also endorsed the
  `.Vn*…H` = TCVN3 capital-font naming convention that `encoding.font_hint` already applies.
  Test fixtures that need a blocked font now pin their own proposed-row table instead of the shipped one.

### Fixed
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
- `guard_tekla_write.py` now exits 2 (the blocking code) on any internal error instead of
  relying on an undocumented `onFailure` setting; the setting was removed.
- `guard_tekla_write.py` no longer blocks commands that only mention `tekla-cli` as data
  (`cat`, `grep`, `git commit -m`), and no longer lets a read hide a later unparsed write.
- Write guard no longer denies commands that only name a file containing `tekla-cli`
  (e.g. `sed -n 1,40p docs/tekla-cli-contract.md`); RTI-0005.
- Write guard now recognises the CLI under its .NET project name (`TeklaCli.exe`) and treats
  every `dotnet run|exec|watch` as a write; `dotnet build|restore|clean` stay allowed; RTI-0006.
- `workflow.md`: the lot loop is strictly sequential (lot n+1 waits for gate 4 of lot n).
- Added `PowerShell(...)` allow rules matching the existing `Bash(...)` ones.
