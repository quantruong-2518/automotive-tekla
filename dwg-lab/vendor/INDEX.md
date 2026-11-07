# Vendor index: existing skills and tools for reading DWG/DXF

Assessment date: 2026-11-06. Purpose: inform the design of the DWG-reading skill for the
Tekla harness. All clones are shallow (`git clone --depth 1`), read-only, and treated as
untrusted data. Nothing here was executed, installed or imported. Nothing was committed.

Project constraints used as the yardstick (AGENTS.md, ADR-0005): Python >= 3.12, ezdxf for
DXF, DWG -> DXF via ODA File Converter then LibreDWG `dwg2dxf`, "AI decides, code does",
provenance + confidence on every value, never guess, every fallback logged, Linux/WSL dev
box, no AutoCAD.

Method limits (be aware): clone contents were read with `cat`/`grep`/`sed`; code quality is
judged from reading, not from running tests. Star counts, dates and sizes come from the
GitHub API and `git log` on the clone. `claudskills.com` and `skillsmp.com` could not be
browsed directly; they were reached only through search-engine snippets (and
claudeskills.info / vibeindex.ai / skills.cat mirrors), so listings there are second-hand.
Research repos (FloorPlanCAD, MechVQA, DrawingVQA) were judged from abstracts and READMEs,
not from running anything.

## Ranking (usefulness to our skill)

| # | Candidate | Verdict in one line |
|---|---|---|
| 1 | `numikel_cad-drawings` | Closest existing match to our design: ezdxf + ODA -> LibreDWG chain, JSON-summary CLI, refuses unitless drawings, handles + `expect` guards. Steal the architecture, not the code. |
| 2 | `ezdxf` (+ `odafc` addon, docs) | The ground truth for text/MTEXT/dimension/block/xref/proxy behaviour; its odafc source confirms the ODA CLI signature and the Linux "exit-code lies" quirk. |
| 3 | `mihaicristianfarcas_dwg-takeoff` | Best "AI decides, code measures" pipeline; units-with-evidence model and deterministic element catalogue are directly reusable ideas. |
| 4 | `lyx100275-alt_ftth-address-extractor` | The strictest never-guess protocol seen (P1-P5 prohibitions, stop-on-contradiction, human-locked baseline). No licence file: ideas only. |
| 5 | `ezdwg` | Independent Rust DWG decoder with ezdxf-like API: good as a cross-check / third fallback, not as the primary reader. Not pure Python. |
| 6 | `hwdemtv_tianzheng-dwg-parse` | Hard-won pitfalls: proxy entities, ATTDEF default values hold names, double counting, rotated frames. Windows/AutoCAD path unusable; the lessons are gold. |
| 7 | `libredwg` | Already in ADR-0005. Add: `dwgread -O JSON`, `dwglayers`, `dwggrep` for cross-checks; frequent CVEs, so sandbox it. |
| 8 | `jeremylongshore_cad-ai-agent` | Large deterministic DXF toolkit (RFI generator, zones, fail-closed CRS). Over-scoped, partly AI-generated looking; mine the RFI and CRS ideas only. |
| 9 | `MatheusMeM_dwg-interpreter-claude-skill` | Small, readable `dwg2dxf` + ezdxf sidecar-JSON inventory; has a download-and-run install step (red flag). |
| 10 | `ACadSharp` (C#, MIT) | Native .NET DWG reader that could run on the Tekla machine (net48/netstandard2.0); a possible Windows-side cross-check. |
| 11 | `skillsbench_sparse` (architectural-dxf-extraction) | Useful layer-alias schema + output-schema pattern; but the skill text tells the model to report a "plausible" value when ambiguous (violates our rules). |
| 12 | `ddc_skills` (dwg-to-excel, cad-to-data) | Not useful: `dwg-to-excel` wraps a closed Windows-only `DwgExporter.exe`; `cad-to-data` DWG path is fake (`_simulate_dwg_extraction`). |
| 13 | MCP servers (puran-water, U-C4N, C48H74, Roy-y111) | Mostly drawing authoring; reading is shallow. Only U-C4N's `dwg_read.py` attempts[] pattern and `dxf_recover` are worth a look. |
| 14 | Other skills (see "Minor") | Windows/AutoCAD-bound or off-topic. |

Top 5 final answer is the first five rows.

---

## 1. numikel/cad-drawings  (clone: `numikel_cad-drawings/`)

- What: Claude Code plugin/skill `cad-drawings` (v0.4.0). Inspect, find, dump, render,
  measure, diff, edit, plot, QA DWG/DXF. About 30k lines of Python plus tests, CI, CodeQL,
  evals, JSON schemas. 
- DWG route: converter pool in `scripts/cadlib/convert.py`: COM (Windows, only with explicit
  consent flag) -> ODA File Converter -> LibreDWG `dwg2dxf` (flagged `approximate`). Then ezdxf.
  This is almost exactly ADR-0005.
- Output: every command ends with a JSON summary (under ~4 KB); big results go to files in a
  fresh run directory; the source file is never modified. Exit codes are typed (3 no backend,
  4 busy, 5 timeout, 6 exists, 7 QA failure).
- Licence: MIT. Last commit 2026-10-29. Maintenance: active, single author, versioned
  changelog, SECURITY.md, tests/CI present.
- Quality: high. Typed errors (`CadError` codes), staged copies, `verify_output()` after each
  converter, fallbacks recorded as warnings, `approximate` flag propagates into the result.
- Security: SECURITY.md states no network code; grep found only a download URL string in
  `doctor.py`. External programs only run when installed; COM path gated by `--allow-com`
  (not relevant to us, would be removed). No red flags found. The SKILL.md asks the model to
  ask the user before writes, installs, long operations and when "stating the intent behind a
  change", which matches our gating.
- Ideas to steal:
  - Converter staging: copy source to `oda/in/input.dwg`, ODA writes into a separate out
    dir, args `[in_dir, out_dir, "ACAD2018", "DXF", "0", "0", filename]` (no recurse, no
    audit), `xvfb-run -a` prefix on Linux without DISPLAY, non-ASCII path warning, then
    verify output exists and opens. Matches our "exit 0 proves nothing" rule.
  - `info` command contents: units, extents, layouts + page setups, layers, blocks, XREFs,
    missing SHX fonts, lock files. Good checklist for our "read-log" and inventory.
  - `$INSUNITS == 0` is refused (`NO_UNITS`); only an explicit `--assume-unit` unlocks it and
    the result says the unit was assumed. This is "never guess" done right.
  - `find`/`dump` results carry an `expect` object (type, layer, space, current text); edits
    refuse if the entity no longer matches. Adapt as provenance: every extracted value keeps
    `handle + expect` so it can be re-verified against a re-conversion.
  - Walk all spaces: model, every paper layout and every block definition, plus ATTRIB
    (`iter_locations` in `entities.py`, with `space/layout/block/parent`). Provenance fields.
  - `measure`: arcs/bulges/splines measured not approximated; hatch = outline minus islands;
    no cross-type total; "never read dimensions off a rendered PNG".
  - `register`: transform between two drawings from control points, with an independent
    check point and residuals. Useful for plan vs section vs detail alignment later.
  - Viewport maths (`DCS = R(+twist) * (WCS - center)`), paper-space units, handles being
    valid only inside one file version.
  - `qa` command that reports what it did not check.
- Caveats: depends on pypdfium2 and pywin32 extras we do not need; large surface (edit, plot)
  we must not import; its ODA arg list uses `ACAD2018` output regardless of input.

## 2. mozman/ezdxf  (clone: `ezdxf/`, 144 MB on disk incl. .git)

- What: the DXF library already chosen. Version in tree is 1.4.6b0; last commit
  2026-11-02. MIT. Very active, long-lived, single lead maintainer, large test suite.
- DWG: none by design. `ezdxf.addons.dwg` is an alpha DWG loader ("Supported DWG versions so
  far: None", "don't use this add-on as DWG to DXF converter"). `ezdxf.readfile` on a DWG
  raises "not a DXF file" (confirmed by the tianzheng pitfalls file too).
- `addons/odafc.py` (read the source):
  - CLI contract confirmed from source: `ODAFileConverter "Input Folder" "Output Folder"
    version type recurse audit [filter]`. This corroborates the "from memory" signature in
    ADR-0005 from a second and third independent source (cad-drawings, dwg-takeoff). It does
    not replace checking the installed version.
  - `_odafc_failed()`: on Linux "ODAFileConverter *always* crashes even if the output was
    successful"; failure is judged by stderr not equal to empty or "Quit (core dumped)".
    So on Linux a non-zero exit or core dump can still come with valid output, and (per
    cad-drawings) the reverse can also happen. Our rule "success = output exists and ezdxf
    opens it" is the right one. Add: treat stderr text as a log field, not a verdict.
  - Linux needs a (virtual) display; the addon starts xvfb. Docs warn that executing an
    external program is a security issue and that the exec path must not be attacker
    controllable: keep the path in config/env only.
  - Version strings map `R2018 -> ACAD2018` etc.; ODA supports an `audit` flag.
- Relevant docs under `docs/source/`: `tutorials/text.rst`, `mtext.rst`, `mleader.rst`,
  `*_dimension.rst`, `xref_module.rst`, `dxfentities/acad_proxy_entity.rst`, `disassemble.rst`,
  `bbox.rst`, `blkrefs.rst`.
- Verified API pointers (grep of the source, not run): `ezdxf.recover.readfile` returns
  `(doc, auditor)`; `MText.plain_text(split, fast)`; `ezdxf.tools.text.plain_text` /
  `fast_plain_mtext`; `Dimension.get_measurement()` and `.virtual_entities()`;
  `Insert.virtual_entities()`; `MLeader.virtual_entities()`; `ezdxf.xref.dxf_info` / `find_xref`;
  `ezdxf.lldxf.validator.dwg_version(path)` reads the DWG header magic (`AC10xx`) without a
  converter, useful for the "detect input formats" step.
- Facts that matter to us:
  - Proxy / custom objects: ACAD_PROXY_ENTITY content is not readable except through proxy
    graphic; `ezdxf.xref` cannot copy it; ACAD_TABLE, OLE2FRAME, ACIS entities are likewise
    not copyable. Treat each as an `unreadable` item with count per layer, never skip silently.
  - DIMENSION text (verified in `docs/source/dxfentities/dimension.rst` line ~202): `dxf.text`
    empty or `"<>"` means the measured value is drawn, a single blank `" "` suppresses the
    text, anything else is a literal override. So read `get_measurement()` AND `dxf.text`; an
    override string is an unverified human-typed value, flag it when it disagrees with the
    measurement (beyond rounding). Dimension styles (DIMSCALE, DIMLFAC, DIMTXT) also change
    what is shown; not checked here.
  - TEXT/ATTRIB `plain_text()` (verified in `src/ezdxf/tools/text.py`, ~line 283-300): decodes
    `%%` special codes through `const.SPECIAL_CHAR_ENCODING` (the usual `%%c`, `%%d`, `%%p`
    symbols; I did not open the table to confirm each letter), drops `%%k %%o %%u`
    formatting codes, and decodes caret control codes. MTEXT uses `MText.plain_text()`.
    Keep the raw string next to the plain one.
  - `readfile(recover=True)` is lossy and reports; log as a fallback and cap confidence.
- Security: normal; `exec`/`eval` hits are in tests only.

## 3. mihaicristianfarcas/dwg-takeoff  (clone: `mihaicristianfarcas_dwg-takeoff/`)

- What: web/CLI quantity-takeoff tool for DWG/DXF. Pipeline: DWG -(ODA)-> DXF -(ezdxf +
  shapely)-> `Drawing` -> deterministic "catalogue" of measurable entries -> LLM (Codex CLI,
  Claude API or OpenAI API) picks entries and factors as schema-checked JSON -> geometry
  engine measures -> LLM reviews. About 9.7k lines. MIT. Last commit 2026-10-15.
- Why it ranks high: it is the closest published realisation of our principle "AI decides,
  code does". The model never outputs a number; every quantity carries its formula, the
  contributing entity handles, de-duplication notes and factor origin (`from the drawing`,
  `from documents`, `assumed`).
- Ideas to steal:
  - `cad/units.py`: `UnitInfo{code, scale, name, source: header|inferred|default|override,
    header_code, confidence, evidence[]}`. The header `$INSUNITS` is kept unless the drawing
    contradicts it (checks against dimensions, objects of known size, survey notation). We
    should keep the structure (source/confidence/evidence) but NOT its default of treating
    unitless as metres: that is a guess. Ours should return `unknown` + open question.
  - Catalogue entry kinds (surface / outline / linear / block / nested_block / table / part)
    with stable keys `kind|layer|pattern|colour|block|container`. Pattern for a structural
    catalogue: beams = linear by layer, columns = blocks or closed outlines, schedules = tables.
  - Block "containers" vs "symbols" by size heuristics; legend swatches excluded from counts.
  - Tables: AutoCAD tables, tables drawn as text, embedded Excel/Word (OLE) tables.
  - `convert.py`: file lock so one ODA run at a time, per-file hash cache, ODA path
    discovery order (env var, Program Files glob, macOS app path, PATH). Cache key by sha256
    is worth copying (never reconvert).
  - Evaluation doc (`docs/evaluation.md`) measures accuracy against drawings with known
    answers; fits our "measure, don't feel" principle.
- Caveats: web UI is Romanian; default AI backend is Codex CLI; AI calls leave the machine
  (our model call policy decides this, not this repo). Local server has no auth (documented,
  binds 127.0.0.1). Treat the tool as a design reference, not a dependency.

## 4. lyx100275-alt/ftth-address-extractor  (clone: `lyx100275-alt_ftth-address-extractor/`)

- What: Chinese-language Agent Skill that parses FTTH telecom drawings (DXF, converted from
  DWG with ODA by the user) with ezdxf into address tables. Domain is unrelated to Tekla.
- Licence: no LICENSE file in the repo. Treat as all-rights-reserved: take ideas only,
  copy nothing. Last commit 2026-10-25. Includes golden expected JSON, a test corpus, a
  changelog, a version file. Pins `ezdxf==1.4.4`. (Metadata carries "AIGC" labels: the skill
  appears to be AI-assisted.)
- Why it matters: its L0 invariants are the best written never-guess protocol seen:
  P1 no inference beyond the drawing, P2 no fabrication or defaults, P3 no silent edits of
  confirmed data, P4 stop on contradiction (no "majority wins"), P5 unknown annotation means
  ask. "Confirmed" requires quoting the user's words in the current session. Three levels:
  measurement (free), normalisation (only rewrites form, adds no numbers; automatic),
  inference (human only). Hard gates before output; one full parse per task through a cached
  loader; contradictions listed in a fixed four-column table for a human decision.
- Ideas to steal:
  - The measurement / normalisation / inference split for our provenance model: every field
    has a `level`; only measurement and normalisation may be auto-filled; inference becomes an
    open question.
  - Authority ladder (user's current-session ruling > invariants > contracts > script defaults)
    and "script defaults must be overridden per drawing after the probe step".
  - A probe step that writes `profile.json` (what this drawing's layers/blocks/text look like)
    before any parse. Matches our read-log idea.
  - Golden-file tests per drawing family.
- Caveat: very prescriptive and long; port the principles, not the text.

## 5. monozukuri-ai/ezdwg  (clone: `ezdwg/`)

- What: DWG reader with an ezdxf-like API: `ezdwg.read(path)`, `modelspace().query(...)`,
  layouts, viewports, `doc.units`, `header_variables()`, plus a narrow writer and
  `to_dxf()` (uses ezdxf as the DXF writer backend).
- Correction to the brief: it is not pure Python. The core is Rust exposed through PyO3
  (maturin); wheels exist on PyPI (0.8.0 seen via search). `requires-python >= 3.10`.
- Licence: MIT. Last commit 2026-11-06 (shallow clone shows 1 commit; CHANGELOG is long and
  detailed). Young project: 28 stars, one main author. Its changelog describes fixes found on
  "production files" (one HATCH entry mentions "36 of 600 DWGs"), covers R13 to R2018, and
  fixes R2007/R2010+ text and attribute decoding. Test coverage and accuracy are unverified by us.
- Security: native binary parser for untrusted input; no network code seen in `src/`.
  Use inside the same sandbox as the converters. Prebuilt wheels are a supply-chain choice;
  building from source needs Rust.
- Value for us:
  - A converter-free second opinion. Compare entity counts per type/layer, text list and
    extents between "ODA -> ezdxf" and "ezdwg" and log disagreements; large disagreement
    lowers confidence or raises a question.
  - `test_dwg/` holds ~13 MB of small real DWGs in R14..R2018 plus some DXF twins. Check each
    file's provenance/licence before reusing as test fixtures (the `acadsharp` subfolder looks
    like it comes from ACadSharp, MIT).
  - Not for primary reading: coverage of MLEADER, tables, proxy objects and dimension styles
    is narrower than ODA + ezdxf; confidence from it should be capped.
- Open question for us: add as optional fallback #3 after LibreDWG (needs an ADR amendment).

## 6. hwdemtv/tianzheng-dwg-parse  (clone: `hwdemtv_tianzheng-dwg-parse/`)

- What: read-only statistics on Tianzheng (T20/T3) DWGs: AutoCAD `accoreconsole` DXFOUT ->
  ezdxf -> per-layer clustering and block counts. MIT, last commit 2026-09-17. Windows +
  AutoCAD required, so the pipeline is unusable on our dev box; the knowledge is reusable.
- Lessons worth copying (all from real-project notes in `references/pitfalls.md`):
  1. Custom-object drawings (Tianzheng, Civil 3D, Architecture) arrive as ACAD_PROXY_ENTITY
     and ezdxf sees no geometry. Always report proxy-entity counts per layer in the
     inventory and cap confidence for anything near them. Structural drawings exported from
     Chinese/Vietnamese architecture add-ons may behave the same.
  2. Equipment/symbol names live in ATTDEF default values (tag `A`) and in the full block
     name; same handle prefix can hide several different block variants. Always key on the
     full block name and read ATTDEF + ATTRIB.
  3. Three counting laws: never combine "expand parent block recursively" with "collect by
     window centre" (real case: 208 counted vs 77 true); treat "block definition anatomy +
     top-level insert clustering" as the gold method; accept a number only when two or
     three independent counts (insert clusters, top-level text, legend) agree.
  4. Rotated (270 degree) sheet frames: use `ezdxf.bbox.extents([insert], fast=False)` for the
     true bbox before selecting text in it.
  5. 100 MB DXF takes 1-3 minutes to produce and 1-2 minutes to load: write stats to files,
     do not print them.
  6. DWG magic bytes: `AC1018` vs `AC1021+` decide the advice to the user.
- Red flag (minor): `install.sh` is a `curl | bash`-style installer (documented one-liner).
  Not needed; do not run.

## 7. LibreDWG/libredwg  (clone: `libredwg/`, 186 MB on disk incl. .git)

- What: GNU C library + tools. GPL-3.0-or-later. Active (last commit 2026-11-06). Latest
  NEWS entry seen: 0.14.1 (2026-07-25, beta) with several memory-safety CVE/GHSA fixes
  (heap overflow, use-after-free in the DWG decoder). README: decoder reads all DWG versions
  but "very advanced R2010+ objects fail to read and are skipped"; writer has CRC problems
  for R2010-R2018.
- Tools (README): `dwgread` (JSON/other outputs), `dwg2dxf`, `dwglayers`, `dwggrep`,
  `dwg2ps`, `dwgfilter`. The Python binding in the tree is only a SWIG stub (`bindings/python`
  holds a Makefile.am); no maintained PyPI binding was found. Do not plan on in-process use.
- Use in our chain: keep as subprocess only (GPL boundary, ADR-0005). Extra uses:
  - `dwgread -O JSON` gives a dump of DWG objects that is independent of ezdxf: a second
    opinion on text and layer lists when ODA is unavailable.
  - `dwglayers`/`dwggrep` are cheap sanity checks.
- Sample corpus: `libredwg/test/test-data/` (54 MB; folders 2000, 2004, 2007, 2010, 2013, ...) holds
  real DWGs per version; dwg-takeoff used it for testing. Useful for converter regression tests;
  check licences/provenance per file before copying any into our repo.
- Risk: parser bugs on malformed input are repeatedly fixed; run on a copy, with a timeout,
  inside a throwaway directory, as an unprivileged user. Pin the version in the read-log.
- Fidelity: confirmed weaker than ODA by cad-drawings (marks it `approximate`) and by
  dwg-interpreter. ADR-0005's "cap confidence at medium" is consistent.

## 8. jeremylongshore/cad-ai-agent  (clone: `jeremylongshore_cad-ai-agent/`, 21 MB)

- What: "cad-dxf-agent" v0.12: Python package with a `cad-analyze` CLI and a Claude Code
  skill. About 37k lines. Apache-2.0, last commit 2026-09-24, 55 stars. Wide scope: DXF edit,
  ADA/IBC compliance, health report, takeoff, summary, RFI generator, zone detection, revision
  diff, georeferencing, desktop/web apps, Firebase, OpenTelemetry. Looks heavily AI-generated
  (e.g. `GitHub_Issues_Ready_To_Paste.md`, `pr_body.md`, ko-fi badge): quality is uneven.
- DWG route: `ezdxf.addons.odafc.readfile` only (ODA); no LibreDWG fallback.
- Ideas worth taking:
  - `rfi_generator.py`: deterministic ambiguity detector emitting categorised, severity-ranked
    RFI items. Map to our `questions.md` generator.
  - `crs.py` and the `dxf_reader.load_dxf()` doc: fail-closed precedence (caller override,
    `.prj` sidecar, DXF GEODATA); a present-but-invalid or unit-contradicting CRS raises
    instead of guessing.
  - "Protected layers", "the LLM planner returns structured operations only".
- Security: the SKILL.md install step pins a git commit SHA and asks the user first (good
  practice). It lists `allowed-tools: Bash(python3:*)`, which is broad. `proxy/` folder and
  Dockerfile are for its hosted version; not needed.

## 9. MatheusMeM/dwg-interpreter-claude-skill  (clone: `MatheusMeM_dwg-interpreter-claude-skill/`)

- What: skill `dwg-views`: `dwg2dxf` (LibreDWG 0.14) + ezdxf; writes `<name>.dwg-views.json`
  and `<name>.dxf` next to the drawing; prints only a short summary. MIT, last commit
  2026-08-07, 1 star. Single 1.3k-line Python script, includes a `--self-check`.
- Good: inventory by what a human sees (layouts, viewports with scale, named views,
  section/detail/elevation labels, title block, texts, dimensions) with handles on every item;
  "read the file, not the stdout; never load the 450 KB JSON whole (about 140k tokens)";
  exit codes (3 backend missing, 5 DWG newer than 0.14 can read); signature check by header.
- Bad / red flags: (a) SKILL.md instructs the model to run a PowerShell `Invoke-WebRequest`
  that downloads a LibreDWG zip from GitHub releases and `Expand-Archive`s it, then to execute
  it: a download-and-run step with no checksum. (b) Windows only. (c) Writes sidecar files
  next to the user's DWG (we write only into the project workspace).
- Idea: viewport-scale extraction and "view label" detection for section/detail callouts.

## 10. DomCR/ACadSharp  (clone: `ACadSharp/`, 62 MB incl. .git)

- What: C# library to read/write DXF and DWG (DWG read AC1014 to AC1032; AC1012 and
  AC1009 not read). MIT, last commit 2026-11-06, 919 stars. Targets
  `net8.0;net9.0;net10.0;net48;netstandard2.0/2.1`, so it can be referenced from a Tekla-side
  .NET tool without any converter.
- Use: an optional Windows-side cross-check or a future `tekla-cli` helper; no use on the
  WSL dev box without a dotnet SDK. Tests include sample DWGs (`ACadSharp.Tests/Data`); check
  licence per sample before reuse. Submodule `CSUtilities` is needed to build.
- Not verified: entity coverage versus ODA; behaviour on proxy/custom objects.

## 11. benchflow-ai/skillsbench: architectural-dxf-extraction  (clone: `skillsbench_sparse/`)

- Whole repo is 885 MB, over the limit. Used a blobless sparse checkout of one task only
  (`tasks/ada-bathroom-plan-repair`, 3 MB). Apache-2.0, last commit in clone 2026-10-12.
- What: a benchmark task (ADA bathroom repair) with three skills; the DXF-extraction skill
  tells the agent to: open with ezdxf, build a layer inventory (entity counts and types per
  layer), normalise layer aliases through a supplied `layer_schema.json`, keep drawing units
  unless the header proves otherwise, round only at the JSON boundary (3 decimals), use
  deterministic ids (`WC1`, `LAV1`), do not invent properties not in a plan view.
- Ideas: `layer_schema.json` pattern (alias -> canonical layer + type + description), output
  JSON schemas per artefact (`layer_inventory`, `extracted_original_layout`, ...), verifier
  tests that check the JSON against the DXF.
- Red flags: the skill text says "If the exact nominal clear width is ambiguous, report a
  plausible CAD opening measurement" and prescribes very task-specific geometric rules
  (ignore arcs larger than 1.5x fixture size, etc.). Both are benchmark-fitting and encourage
  guessing. Do not import the prose. The task's Dockerfile pip-installs packages in a sandbox
  (not executed).

## 12. datadrivenconstruction/ddc_skills_for_ai_agents_in_construction  (clone: `ddc_skills/`)

- 394 stars, MIT for skills (book and cost database have separate, restrictive terms in
  `NOTICE.md`: CWICR is CC BY-NC plus commercial licence). Last commit 2026-10-19
  ("Remove ODA references"). I removed the 348 MB `Books/` directory and the PDF from my
  working copy to keep the clone small; the git objects remain (~141 MB `.git`). The repo
  was 166 MB per the API but 506 MB on disk after checkout.
- `1_DDC_Toolkit/CAD-Converters/dwg-to-excel`: wraps a closed-source Windows executable
  `DwgExporter.exe` (DDC) via `subprocess`; output is an Excel with sheets Elements/Layers/
  Blocks/Layouts. No source, no checksums, Windows only (`os: win32`). The embedded Python
  class has dataclasses and aggregations (layers, blocks, duplicates) but the extraction
  itself is the opaque binary. Not usable under our "scripts we can audit" rule.
- `2_DDC_Book/2.4-PDF-CAD-to-Data/cad-to-data`: the DWG branch is a stub:
  `DWGExtractor.extract()` calls `_simulate_dwg_extraction()` which returns hard-coded layers
  and 15 invented polylines ("Walls", "Doors", ...). A skill that returns fabricated data
  from a "converter" is the exact failure mode our principles forbid. Do not use.
- Other: `publish_*.ps1`, `update_all_skills.py` in repo root; `REVIEW_2026.md` is a
  self-review. The repo advertises 214-221 skills; most are generic business-process text.
- Red flags: fake extraction code; closed binary download dependency; marketing claims
  ("1983-2026 without Autodesk licences") with no verification possible.

## 13. AutoCAD MCP servers

| Repo | Licence | Last commit | DWG reading | Notes |
|---|---|---|---|---|
| puran-water/autocad-mcp (638 stars) | MIT | 2026-11-04 | none; `drawing_open` is `ezdxf.readfile` | Authoring-oriented (create/modify entities, P&ID). `block_get_attributes`, `entity_list` are the only read tools. Tiny (1.3 MB). |
| U-C4N/Autocad-MCP (`autocad-mcp-pro`, 237 stars) | MIT | 2026-11-06 | `backends/dwg_read.py`: ODA via odafc, then `accoreconsole`; every attempt recorded in `attempts[]` | 257 tools (!), COM + ezdxf engines, durable journal, `dxf_recover.py` (`ezdxf.recover`, reports every fix), `quarantine.py`. Heavy and tool-count-driven; its own README admits "257 registered, 6 listed" discovery mode to cut prompt tokens. |
| C48H74/autocad-mcp | MIT | 2026-10-05 | none ("A DWG cannot be read without AutoCAD") | Piping focus; 5 stars. |
| Roy-y111/autocad-mcp | MIT | 2026-10-13 | via live AutoCAD (LISP over MCP) | Contains skills `structural-drawing-to-excel` and `compare-dwg-revisions`. |
| hvkshetry/autocad-mcp | | | | Repo moved (HTTP 301 from the API); not followed. |

Ideas from the group:
- U-C4N `dwg_read.py`: ordered routes, `attempts[]` with route/reason/exit code/last log
  lines, private ASCII staging folder per conversion, script content generated only by the
  module, hard deadline with whole-process-tree kill, staging swept after use. Matches ADR
  "every attempt is recorded". Also its capability refusal type (`dwg_read` refusal) is the
  idea of exit code 3.
- Roy-y111 `structural-drawing-to-excel` (structural domain, Taiwan): detect floor boundaries
  from plan-title text positions (exact-match titles, exclude combined "6th to 7th floor"
  titles), assign each member label to a floor by Y coordinate, look up the size in the
  schedule table by floor code with fallback, then produce a diff sheet: in-schedule-not-on-
  plan, on-plan-not-in-schedule, default-without-label, matched. That diff is exactly the
  cross-check our harness needs for beam/column schedules. Implementation here is unusable:
  it needs live AutoCAD + LISP, a manual "delete the top-view beams first" step, writes to
  `C:/Users/{USER}/Desktop`, and the SKILL.md runs `exec(open(...).read())` on a script path
  (red flag).
- Security of the whole group: all are tools that drive CAD with powerful commands; the
  MCP security.py in U-C4N does path-traversal and LISP-injection filtering (a good sign) but
  none of it matters for read-only extraction. No obfuscation or telemetry found in my greps
  (searched for base64 decode, eval/exec, curl-pipe, `Invoke-Expression`).

## 14. "cad-viewer" agent skill (ClawHub) and text-to-cad  (clones: `tangsh0708_cad-viewer/`, `text-to-cad_sparse/`)

- The `cad-viewer` skill seen in search results (discoveraiskills.com, termo.ai, ClawHub) is a
  DWG/DXF reader skill: a `cad_tools.py` script with subcommands `layers`, `texts`,
  `layer-content`, `distance`, `screenshot`, `search`; it installs the ODA File Converter (and
  optionally QCAD `dwg2bmp`) for DWG. Its ClawHub page carries a "suspicious patterns detected"
  security flag (the same page says the code appears to match its description and setup needs
  user confirmation). I could not locate its source repository, so it is NOT assessed
  beyond its listing; treat as unverified and do not install. Idea only: its `texts` command
  (TEXT + MTEXT + block attributes, with keyword filter and limit) is the same shape as
  cad-drawings `find`.
- The only GitHub repo named `cad-viewer` that I found (`tangsh0708/cad-viewer`, a fork of
  `mlightcad/cad-viewer`, MIT, last commit 2026-07-21, 42 MB) is a TypeScript browser viewer
  (libredwg-web WASM + dxf-json) with a `cad-agent-plugin` package. Not the agent skill, not
  Python, not useful for us. Its `PROPRIETARY-PARSER.md` advertises a paid closed-source
  DWG parser; note only that LibreDWG-based stacks hit WASM heap limits on big DWGs.
- `earthtojake/text-to-cad` (MIT, last commit 2026-11-05; repo ~432 MB so only
  `skills/dxf` and `skills/engineering-drawing` were fetched by a blobless sparse checkout,
  1.5 MB): skills for generating DXF/PDF drawings from build123d models. The `dxf` skill
  explicitly generates, it does not inspect existing DXF. No reading ideas worth stealing;
  its setup tells the agent to install the `cad` command, which is another install-from-skill
  step to avoid.

## 15. PDF and vector-PDF alternatives (ADR-0005 last resort: "ask for DXF or PDF")

- `jeremylongshore_cad-ai-agent`: `pdf_classifier.py` classifies each PDF page as
  `vector_layout`, `raster_scanned`, `mixed` or `cover_text_heavy` using PyMuPDF metadata
  (`fitz`), and `pdfplumber` is a declared dependency. Idea: classify each PDF page first
  and refuse raster pages for dimensioned values (confidence none, open question).
  PyMuPDF is AGPL-3.0 or commercial: do not make it a dependency of ours without a licence
  decision.
- `numikel_cad-drawings`: renders PDF to PNG with pypdfium2 (Apache-2.0/BSD-3, bundled in
  its `pyproject.toml`); PyMuPDF is AGPL and only an opt-in flag, with a notice in
  `THIRD_PARTY_NOTICES.md` that it is "not recommended for distribution". Idea: use
  pypdfium2 for rasterising and pdfplumber (MIT) / pypdfium2 text objects for vector text
  with coordinates, if we add a PDF lane.
- SymPoint / FloorPlanCAD operate on SVG/vector primitives converted from PDF/CAD (research,
  not a usable PDF reader for us; SymPoint licence is non-commercial).
- Not assessed: `pdfminer.six`, `pdfplumber` internals, Poppler `pdftotext -bbox`; no
  vendor repo exercised a vector-PDF -> structural-values pipeline with provenance. A PDF
  lane with per-value page + bbox provenance remains to be designed by us.

## Minor / not worth deeper work

- `xy425yi_claude-cad-skill` (MIT, 2026-10-01): `accoreconsole` + AutoLISP headless editing,
  Windows + AutoCAD only. `install.ps1` pip-installs pymupdf/numpy/ezdxf and the README
  tells users to run it with `-ExecutionPolicy Bypass`. Idea: `survey` row format
  `handle|type|layer|space|bbox|name|attrs|text`.
- `shlomorsh_claude-code-skills-for-architects` (MIT, 2026-08-16): Hebrew skills,
  `dwg-inspector` via `accoreconsole` LISP. Windows + AutoCAD only.
- `aianime0012-coder_vitruvius-skills` (MIT, 2026-08-04): `dxf-drawing-inspection` hygiene
  checklist is generic but sensible: coordinates beyond +-1e6 (off-origin), everything on layer
  0, empty layers, default layer names, duplicate overlapping lines, missing units ("report
  units unknown, do not guess"). Also has stdlib DXF text parser (useless next to ezdxf).
- `89chency_dwg-compare` (MIT, 2026-10-07): revision compare through BricsCAD/AutoCAD.
- `beiming183-cloud_AutoCAD-skills` (MIT, 2026-07-19): mechanical drafting, off-topic.
- `imerfs_dwg-to-webgis-skill` (Apache-2.0, 2026-11-02): DWG -> GIS via GDAL; off-topic, but
  confirms GDAL/OGR can read DXF as an alternative reader (not DWG without a driver).
- `SymPoint` (clone, 3.6 MB, last commit 2024-03-20): ICLR 2024 panoptic symbol spotting on
  FloorPlanCAD. Licence "Non-commercial scientific research purposes": cannot be used in our
  product. Research reference only; needs CUDA, detectron2, Python 3.8.
- `libdxfrw` (LibreCAD, GPL-2.0-or-later, clone 43 MB, last commit 2026-10-12): C++17 DXF
  library with a DWG reader path; GPL and C++; no use for a Python skill. Noted for
  completeness.

## Not cloned (and why)

| Item | Reason |
|---|---|
| `earthtojake/text-to-cad` (25k stars, MIT) | ~432 MB, over the 200 MB cap; only `skills/dxf` and `skills/engineering-drawing` were fetched by sparse checkout (section 14). Generator, not a reader. |
| `xiaofengShi/MechVQA` (Apache-2.0, 57 stars) | 369 MB per API (772 MB checked out; I deleted that clone). Mechanical-drawing VQA benchmark (about 3.3k drawings, 21k QA) with a model `MechVL`; images, not DWG; domain differs from structural plans. Optional later reading for how to score drawing QA. |
| `FloorPlanCAD` dataset (ICCV 2021) | Dataset, not a skill; vector floor plans with 35 classes. Link: floorplancad.github.io. Architectural not structural. |
| DrawingVQA (construction drawings, civil/structural, 33 drawings, 92 QA, 2026) | Closest in domain by abstract, but no public repository found in search snippets. Re-check later. |
| QueryCAD (arXiv 2409.08704) | 3D CAD models, not 2D drawings. |
| ODA File Converter | Closed source; docs live on opendesign.com (not fetched). Behaviour taken from ezdxf's wrapper and two skills' wrappers. |
| libopencad, other DWG libs | Searches returned nothing usable; not verified. |
| `claudskills.com`, `skillsmp.com` listings | Reached only as search snippets/mirrors. |
| `hvkshetry/autocad-mcp` | Moved. |

## Cross-cutting findings

### What the ecosystem does about DWG
1. Nobody reads DWG with ezdxf. Every working non-Windows skill converts DWG -> DXF first
   (ODA, then LibreDWG), exactly like ADR-0005. Windows skills use `accoreconsole`
   (needs AutoCAD) and are out of scope.
2. Fidelity ranking everyone agrees on: AutoCAD/COM > ODA > LibreDWG. cad-drawings labels
   LibreDWG output "approximate; some R2010+ objects may be dropped". This supports the ADR's
   confidence cap.
3. ODA command line: `ODAFileConverter in_dir out_dir ACAD2018 DXF 0 0 [filter]` is
   consistent across ezdxf, cad-drawings and dwg-takeoff. Still verify on the installed
   version (ADR-0005 already says so). Linux needs xvfb; folder-based, so stage one file per
   folder; non-ASCII paths are a known trap.
4. Proxy/custom entity drawings (Tianzheng, Civil 3D, Architecture add-ons) lose their
   content in DXF. Only tianzheng and ezdxf docs mention this; add a first-class
   "unreadable objects" section to our output.

### Concrete design ideas (what to put in our skill)
- Probe step first: format magic bytes (`ezdxf.lldxf.validator.dwg_version`), converter
  attempts, ACADVER, INSUNITS, extents, layouts, layers, blocks, XREFs, missing SHX fonts,
  proxy object counts per layer. Write `read-log.json`. (cad-drawings `info`, dwg-views,
  tianzheng census, ftth `profile.json`.)
- Units record: `{value, source: header|inferred|user, header_code, confidence, evidence[]}`;
  header 0 -> `unknown` plus an open question; never default to metres (dwg-takeoff does,
  cad-drawings refuses). Cross-check by dimension text magnitudes and typical beam/column
  sizes (inference, so confidence capped and the result stays a question until the engineer
  confirms).
- Provenance fields on every value: source file sha256, converter name + version +
  `approximate` flag, sheet/layout name, space (model/paper/block), block path (parent
  INSERT handles), entity handle (valid only for this conversion), entity type, layer,
  bbox in model coordinates, and viewport transform if read from paper space, plus
  `level` (measurement/normalisation/inference) and `confidence`.
- Text normalisation (all from ezdxf, verify in its docs): MTEXT -> `plain_text()` and keep the
  raw string; TEXT with `%%c %%d %%p` codes decoded; DIMENSION -> both `get_measurement()` and
  the override text, flag when they disagree; MLEADER content via `virtual_entities()`;
  ATTRIB value + ATTDEF default + tag; collapse whitespace but preserve the raw value;
  NFC-normalise Vietnamese text and keep the original; record the DXF text style/font when a
  missing SHX font would garble text.
- Layer semantics: a project `layer_map.json` (alias regex -> canonical meaning), seeded
  from the AIA/NCS pattern for structural layers (`S-BEAM`, `S-COLS`, `S-GRID`, `S-ANNO`)
  from general knowledge, not from vendor repos. Unmapped layers go to a report with entity
  counts and sample text instead of being guessed (skillsbench `layer_schema.json`;
  vitruvius hygiene checks: everything on layer 0, default names, empty layers).
- Counting discipline (tianzheng): count by a single method, cross-check by a second
  independent method, never combine recursive expansion with window collection; unequal
  counts become an open question.
- Floor/sheet detection and schedule reconciliation (Roy-y111, dwg-views): find plan titles by
  text + position, assign members by region, compare the plan's labels against the schedule
  table and output the four-state diff.
- Tables drawn as text: cluster text by X/Y into rows and columns (dwg-takeoff `tables.py`,
  Roy-y111, energent customer story); output the grid with the cell bbox as provenance.
- Result transport: summary JSON small on stdout, full detail in files, read sections not the
  whole (dwg-views, cad-drawings). Keeps model tokens low.
- Converter robustness: per-file temp dir, staged copy, `xvfb-run -a` on Linux, deadline +
  process-group kill, success = output exists and ezdxf opens (matches ADR), record last log
  lines, cache by sha256 (dwg-takeoff), one ODA run at a time (file lock).
- Never auto-install or download binaries from a skill prompt (dwg-views). Keep converter
  paths in config/env only (ezdxf's own warning).

### What is missing from everything reviewed
- No tool targets structural plans specifically (grids, beam/column marks, schedules,
  rebar callouts, section cuts). The closest are Roy-y111's schedule diff (needs AutoCAD) and
  dwg-takeoff's catalogue (civil/site). We will build this part ourselves.
- No tool records provenance + confidence per value to the standard we need.
- No tool tests the DWG path against real DWG samples in CI; `ezdwg/test_dwg` and
  `ACadSharp.Tests/Data` are the only sample corpora seen. Our samples directory
  (`dwg-lab/samples/`) is still empty.

## Red-flag register

| Where | Flag | Severity | Action |
|---|---|---|---|
| ddc_skills `cad-to-data` | DWG extractor returns hard-coded fake entities | Critical for correctness | Do not use or copy |
| ddc_skills `dwg-to-excel` | Depends on closed `DwgExporter.exe` (Windows); no source, no checksum | Major | Do not use |
| MatheusMeM `dwg-views` SKILL.md / README | Model told to download a zip with `Invoke-WebRequest` and run the contained exe, no checksum | Major | Never copy; install converters by hand |
| Roy-y111 `structural-drawing-to-excel` | `exec(open(path).read())`, writes to Desktop, live-AutoCAD LISP | Major | Do not use; ideas only |
| skillsbench `architectural-dxf-extraction` | Says to report a "plausible" value when ambiguous | Major (violates never-guess) | Do not import prose |
| tianzheng `install.sh`, xy425yi `install.ps1`/README | `curl | bash`-style installer; `-ExecutionPolicy Bypass` | Minor-Major | Never run |
| ftth-address-extractor | No licence file | Minor (legal) | Ideas only |
| SymPoint | Non-commercial research licence | Minor (legal) | Do not ship |
| libredwg | Repeated memory-safety CVEs in the DWG decoder; GPL-3 | Major (operational) | Subprocess, sandbox, timeout, pinned version |
| ezdwg | Native Rust parser on untrusted input, young project, prebuilt wheels | Minor-Major | Optional, sandboxed, confidence-capped |
| ClawHub `cad-viewer` skill (source not found) | Marketplace flagged "suspicious patterns"; setup installs ODA + QCAD | Major (unverified) | Do not install; not assessed |
| text-to-cad skills | Setup tells agent to install a CLI from the repo | Minor | Do not follow |
| ODA File Converter (not cloned) | Closed source; licence for commercial use still open (roadmap) | Open question | Needs engineer's written confirmation |
| cad-ai-agent | Large AI-generated-looking surface; `Bash(python3:*)` allowed-tools; Firebase/cloud code | Minor | Mine ideas only |

No prompt-injection text addressed to the model ("ignore previous instructions", "disable
safety") was found in the cloned skills by grep. No obfuscated code (base64 blobs, eval of
decoded strings) found outside ezdxf test files. This was a pattern search, not a full audit.

## Suggested next actions (for the engineer, one recommendation)

1. Build our skill's inventory/probe layer after cad-drawings' `info` + dwg-takeoff's
   `UnitInfo`, with our provenance schema; do not vendor code from the clones.
2. Add `ezdwg` as an optional cross-check (needs an ADR) and use `libredwg dwgread -O JSON`
   in the same role; do not make either a primary reader.
3. Collect real structural DWG/DXF samples into `dwg-lab/samples/` (empty today): they are
   the only way to judge any of the above for our drawings.

## Housekeeping (what I did to this folder)

- Nothing from any clone was executed, imported, installed or pip-installed. I used `git`,
  `curl` to the GitHub API, `ls`, `cat`, `grep`, `sed`. All code-quality judgements come from
  reading the code, not from running tests. (Two tiny helper scripts of mine ran with the
  vendor folder as working directory; no harm.)
- Removed after cloning to save space: `ddc_skills/Books/` and the 11 MB GuideBook PDF from
  the working copy (the `.git` of that clone stays, ~141 MB), and the whole `MechVQA` clone
  (772 MB checked out, over the cap). `skillsbench_sparse` and `text-to-cad_sparse` are
  blobless sparse checkouts (only the listed task/skills folders).
- Size now: roughly 0.7 GB, mostly `libredwg`, `ezdxf`, `ddc_skills`, `ACadSharp`. If space
  matters, `rm -rf` any clone; INDEX.md is self-contained.
- Git hygiene: `git check-ignore -v dwg-lab/vendor/ezdxf` reports the rule
  `.gitignore:62: dwg-lab/vendor/*/` (the root `.gitignore` already has an uncommitted change
  adding it), so the nested clones are ignored. `dwg-lab/vendor/INDEX.md` is NOT ignored by
  that rule (it matches only sub-directories), so it will show up as untracked. I did not
  change `.gitignore` and did not commit anything.
- Clone dates: all clones were made on 2026-11-06; the last-commit dates in this file are the
  dates of the cloned HEAD.
