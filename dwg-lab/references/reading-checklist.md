# Reading checklist for a structural drawing set (machine-followable)

Status: **synthesis by the research pass of 2026-11-06, not an approved rule.** It merges the per-topic notes in
this folder (`01-drawing-set` ... `06-research`). Each step cites the note that supports it; steps with no
authoritative source are marked `[practice]`. The engineer must approve any promotion into a skill (AGENTS.md principle 7).

## Conventions used below

- **Value record** = `{value, provenance{file, sheet, revision, region{page, bbox, grid_ref, detail}, method}, confidence}`
  as in `schemas/common.schema.json`. Confidence: `high` = deterministic read **and** cross-checked; `medium` = deterministic, not cross-checked, or vector PDF;
  `low` = vision, scan, or inferred (never used downstream without an engineer answer).
- **Open question** = an entry in `questions.md`:
  `Q-nnn | blocking? | what is needed | where to check (file, sheet, revision, region/grid ref) | what was found (verbatim) | which quantity/lot it affects`.
  Never write a guessed value in its place. A quantity that depends on an open question is marked *provisional* (Circular 13/2021 Appendix VI, I.4).
- **Fallbacks** (ODA -> DXF -> render -> ask) are logged in `read-log.json`; each lowers confidence.
- **Region-dependent rules** (notation, grades, laps, cover, section tables): never fill from memory; read the project's own legend/notes, or ask.

---

## Phase A. Intake and inventory

**A1. File inventory** - *Find:* every file, its format, hash, encoding. *Where:* `input/`, `read-log.json`. *Verify:* sha256 present; format detected; encoding detected for text (utf-8 / tcvn3 / vni / gbk). *If missing/failed:* log attempt and fallback; if `outcome=unreadable` -> blocking question "please send DXF/PDF of <file>". (Notes: 04-cad.)

**A2. Sheet index (drawing list)** - *Find:* the list of all sheets with number, title, revision, date. *Where:* cover sheet, G-/S-001 index sheet, or a separate transmittal/drawing register. *Verify:* every listed sheet is present in the files and every file's title block appears in the list; counts match. *If missing:* blocking question "no drawing list: confirm the full sheet list" (record which sheets were actually received). (Notes: 01.)

**A3. Title block of every sheet** - *Find:* project, sheet number, sheet title, scale(s), revision letter/number, date, status (for tender / for construction), drawn/checked/approved. *Where:* usually lower-right (TCVN 5571:2012 places it in the lower-right quadrant) but locate by keywords; in DWG it is usually in paper space, not model space. *Verify:* sheet number in file name = title block = index; one revision per sheet. *If conflict:* two files for the same sheet with different revisions -> use the later one provisionally (confidence medium) and ask which is current. *If scale not given:* do not scale; use dimension text only. (Notes: 01, 04.)

**A4. Revision history and status** - *Find:* revision table, clouds/delta markers, "superseded" stamps, status. *Where:* beside the title block, or top-right on some sets. *Verify:* revision letter in title block = last row of table. *If no revision printed:* store `revision=null` and flag; ask once per set, not per value. *If status is "for tender"/"preliminary":* every quantity is provisional. (Notes: 01, 05.)

## Phase B. Global information (read before any plan)

**B1. General notes and specification notes** - *Find:* design codes and editions; material grades (concrete, rebar, structural steel, bolts, welds); cover; lap/splice and hook rules; tolerances; coatings/fireproofing; special inspection; "U.N.O.", "TYP.", "SIM." conventions; who designs connections; whether laps are included in schedules. *Where:* dedicated general-notes sheets (the ACI 315R-18 table of contents lists general notes sheets first; section 4.3 not read), plus notes blocks on plan sheets. *Verify:* notes on a plan sheet that contradict general notes -> record both; do not choose. *If missing:* question per missing item (grade, cover, lap, code edition). Do not infer from "typical" practice of another region. (Notes: 01, 02, 03.)

**B2. Legend, symbols, abbreviations** - *Find:* symbol legend, section/detail bubble convention, rebar callout style, weld symbol key, hatch meanings, abbreviation list. *Where:* general sheet or first sheet of each discipline. *Verify:* each symbol used on the plans appears in the legend. *If missing:* low-confidence interpretation + question for each unexplained symbol. (Notes: 02, 03.)

**B3. Units** - *Find:* unit system per sheet (mm, m, in, ft-in) and any mixed use; mass units (kg/m vs lb/ft). *Where:* general notes, title block, dimension style, DXF `$INSUNITS`. *Verify:* a known dimension (e.g. grid spacing 6000) consistent with dimension text and geometry. *If unitless or conflicting:* blocking question. (Notes: 02, 04.)

**B4. Grids** - *Find:* grid names, directions, spacing between each pair, bubbles; skewed or radial grids. *Where:* plan sheets; in DXF the `GRID` layer or a block with attributes, possibly from an xref. *Verify:* identical names and spacings on every sheet that shows them (`crosscheck` grid counts); total of spacings = overall dimension. *If inconsistent or xref missing:* blocking question; **do not rebuild grids from member positions**. Output: `grids.json` with provenance. (Notes: 01, 04.)

**B5. Levels and datum** - *Find:* floor levels (FFL, TOS, TOC, SSL...), datum and its relation to site level, storey names, section/elevation heights. *Where:* elevations, sections, level schedules, notes on plan ("EL +3.600"). *Verify:* same level names/elevations on all sheets; storey heights = difference of levels; mm vs m consistent. *If missing:* question; no default storey height. Output: `levels.json`. (Notes: 01.)

**B6. North and orientation** - *Find:* north arrow (project north vs true north), orientation of plan relative to grids. *Where:* site/key plan. *Verify:* consistent on all plans. *If missing:* only matters if the model is oriented; ask once. (Notes: 01.)

**B7. Structural system overview** - *Find:* structural type (RC frame/wall, steel frame, composite, mixed), foundation type (footings, mat, piles), lateral system, floors covered, typical vs unique floors. *Where:* general arrangement/key plans, section sheets, general notes. *Verify:* each system element in the overview appears on a plan and in a schedule. *If conflicting:* question. (Notes: 01, 02, 03.)

## Phase C. Member and schedule extraction

**C1. Classify sheets by type** - *Find:* plans, elevations, sections, large-scale views, details, schedules/diagrams, foundation sheets (sheet types as listed in the ACI 315R-18 table of contents; not a verified order). *Where:* sheet titles. *Verify:* each sheet assigned exactly one primary type; unknown type -> list. (Notes: 01, 03.)

**C2. Schedules (deterministic first)** - *Find:* column, beam, wall, slab, footing, pile, steel member, connection, bar bending schedules. *Where:* schedule sheets or tables on plan sheets; in DXF as TABLE, MTEXT or line+text grids; in PDF as text layer tables. *Verify:* header row recognised; units in header; row count > 0; each cell has provenance with row/column; a row's mark appears on a plan. *If extraction fails:* render tiles, read with vision, mark every cell `low`, log fallback, question. Output: `schedules.json`. (Notes: 02, 03.)

**C3. Members from plans** - *Find:* member marks/tags, sizes, positions on grids, elevations (TOS/top of beam), orientation, camber, openings. *Where:* framing, column, foundation, slab plans. *Verify:* every tag has a schedule row or a detail; every schedule row is located on at least one plan (member count by plan = by schedule); position expressed as grid reference + offset. *If tag has no schedule row, or a row has no location:* question naming the tag/row. (Notes: 02, 03.)

**C4. Section labels (steel)** - *Find:* section designation text; standard/edition (from notes or catalogue sheet). *Verify:* resolve against the catalogue for that standard; kg/m in the label (UK/US) equals catalogue mass; nominal vs actual dimensions never mixed. *If label not in catalogue or standard unknown:* question; never guess a substitute section. (Notes: 02.)

**C5. Reinforcement callouts (RC)** - *Find:* count, diameter, grade, spacing, location (top/bottom/each way/each face), zones, hooks, laps, cover. *Where:* sections, beam/column/slab details, schedules, general notes. *Verify:* parse with the notation of the project (legend first); callout that fits two styles -> flag; spacing x count fits member width minus cover; bar mark in section = bar mark in bar bending schedule. *If silent on lap/hook/cover/grade:* question; quantity provisional. (Notes: 03.)

**C6. Connections and plates (steel)** - *Find:* plate sizes (thickness x width x length), bolt count/diameter/grade/hole type, weld type/size/length/field-or-shop, typical connection notes, delegated-design statements. *Where:* connection details, typical-details sheets, general notes. *Verify:* each connection reference ("see detail 3/S-501") resolves; plate item list complete. *If connection design is delegated or "by fabricator":* record `connection_design=fabricator`; question about allowance for fittings (NRM 2 section 15 style) with the client's rule. (Notes: 02, 05.)

**C7. Cross-references** - *Find:* every detail/section/elevation bubble and its target sheet. *Verify:* target exists, label matches, revision of target consistent with source. *If unresolved:* list in `questions.md`. (Notes: 01.)

## Phase D. Verification before use ("cross-sheet" and "sum-of-parts")

**D1. Cross-sheet consistency** - member mark and size equal on plan, schedule, section, elevation, detail; grid names/spacings and levels identical; notes consistent. *Output:* `crosscheck` report; mismatches -> question (never overwrite). Confidence upgrade to `high` only after the check passes. (Notes: 05.)

**D2. Sum-of-parts** - counts: members by plan = by schedule; bars: bar-length x count x kg/m summed per bar mark = bar bending schedule total (mass per metre = 0.006165 x d^2 for d in mm, 7850 kg/m3; derivation in 05); steel: sum of members (length x kg/m) + plates + bolts vs any tonnage printed by the designer. Tolerance: choose explicitly (CDOT requires two independent quantity sets within 1 %, not averaged: a useful default for rebar). (Notes: 03, 05.)

**D3. Geometry sanity** - span = grid distance; bar dimension sum <= member size minus cover; member lengths vs grid spacing; elevation consistency. (Notes: 03, 05.)

**D4. DXF-specific checks** - overridden dimension text vs measured value; multiple scales in model space; missing xrefs; `$INSUNITS`; encoding artefacts; frozen/off layers; layer names used only as hints. (Notes: 04.)

**D5. Revision control** - every extracted value carries sheet+revision; values from superseded sheets are rejected or flagged. (Notes: 01, 05.)

## Phase E. Output and hand-off

**E1. Questions** - consolidate duplicates; mark blocking vs non-blocking; each has sheet, revision, region, what was found, what is needed, affected quantity. Vietnamese prose for the engineer, English keys. (Notes: 05.)

**E2. Information matrix** - member x field x source sheet x status (`04-info-matrix.csv` in the workflow), gaps shown explicitly. (docs/workflow.md.)

**E3. Quantities** - report measured vs provisional separately; show the rule used (TT13 Appendix VI 5.4/5.6/5.11 as consolidated in 37/VBHN-BXD, or the project's contract rule), rounding (decimals to 3 places per TT13 II.1.4(d)), and the sheet number of any designer's schedule used. (Notes: 05.)

**E4. Do not proceed to a lot** until: A2-A4 passed, B1 grades known, B3 units known, B4/B5 consistent, and no blocking question is open for the lot's members.

---

### Stop conditions (hard stops, from AGENTS.md)
A required script/skill does not exist; session not local to the Tekla machine; a drawing value is missing, contradictory or below the confidence threshold; an action would write to Tekla outside `builder`.
