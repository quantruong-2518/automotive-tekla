# Reading method: what an engineer asks at each phase

One section per phase of SKILL.md, read before that phase starts: the questions to answer, where to look first, what the phase
records. Part mode ([part-mode.md](part-mode.md)) splits the phases by role: the **scout** runs phases 0–1 (`--part scout`); a
**part reader** runs phases 2–4 on its one part (`--part <its part>`); the **assembler** runs phases 5–6 across the parts of
each block (`--part all-assembly`). The order follows `dwg-lab/references/reading-checklist.md` (steps in brackets); where it
says "use the later revision provisionally", this method asks. Notation lives in [conventions.md](conventions.md) and
[steel-industrial.md](steel-industrial.md); this file is procedure.

## Phase 0. Reach (scout)

An engineer first asks: *did I receive the whole set, and can I read all of it?* [A1]

1. `inventory.json`: per file `read | partial | unreadable`, converter, `confidence_cap`.
2. `list-sheets`: per sheet `text_count` and `blocked_text_count`. A sheet with little text beyond its title block **and** no
   circle, outline or line in its `geometry` (item 6) is `near-empty`: its content may sit in an insert or viewport the tools
   did not open. A sheet with geometry and little text is not (E08).
3. Blocked share per sheet. A mostly blocked general-notes sheet makes phase 2 `unread` for those topics: say so now, with the font question.
4. Layouts and xrefs listed by the probe: [edge-cases.md](edge-cases.md) rows E05–E08.
5. **Text outside every frame** (`harness unassigned-clusters W --file F`; tools.md): one cluster per frame and side, plus one
   `sheet_id: null` cluster per file, each with x and y range, nearest frame and gap. You decide whether a cluster continues a
   frame's table (same columns, directly below or beside it, under that table's header; the tool does not). It is then
   **assigned**: read it as that sheet's rows and say `by position; no entry ties it to the sheet` (E10). A cluster no frame
   continues stays `U<n>`; the `U<n>` of a file share one question. This runs before phase 1 states any coverage and before
   anything is called `no rows`, `schedule unread` or `absent`.
6. **Linework reach.** One `geometry` call per file, `--sheet` listing every sheet of the file and `--save > /dev/null` (scout
   only; part readers reuse the saved files, tools.md § Linework). Read each saved file through the compact summary of tools.md;
   no number comes from a script. Per sheet note the layers that hold geometry, the circle and outline groups, the `hidden` and
   `invisible` counts and the warnings. A sheet with geometry but no text is readable for linework and `unread` for text (`reason` says which).

The scout reads no content beyond this and phase 1: sizes, counts and levels belong to the part readers. Reach table: `file |
sheet | text_count | blocked | reach | reason | question`, plus one row `U<n>` per cluster: `file | U<n> | entries | bbox |
nearest frame, gap | assigned (by position) | question`.

## Phase 1. Orient (scout)

*What is this building, and what did they send me of it?* Read titles and the drawing list before any plan. [A2–A4, B7, C1]

1. **Title pass.** For each sheet take the title-block title and the in-frame headings. Class by the in-frame drawings.
   `sheet_class` values: `general_notes, setting_out, foundation, foundation_details, floor_framing, column_details,
   beam_details, slab_details, stairs, schedules, steel_details`, `mixed` (one sheet, several drawings), `other` with `--note`.
   A title-block title naming a subject no heading on the sheet shows is a mis-title: one question quoting both, after searching
   the sheet for the subject word. The class follows the headings and member labels the sheet shows, with the title as evidence
   in the question. A plan is also classed by what `geometry` shows (caps and piles: foundation plan; stubs: stub plan; one
   outline per grid node: column plan); two sheets with the same groups and counts are repeated views, never added. A sheet
   whose number and title name no block goes to the block whose frames share its row or column in the `list-sheets` boxes; quote
   the position and ask. A block that number series and grid origin place differently is E41.
2. **Drawing list.** Search `danh mục`, `DANH MỤC BẢN VẼ`, `drawing list`, `index`. Found → compare both ways: listed but not in
   the files; in the files but not listed; the same number on two sheets; a number outside its series. A list that covers one
   discipline or one block says so in its own title: quote it, and treat the other parts as having no list.
3. **Revision and status.** Per sheet: revision, date, issue status (tender, approval, construction) from the title block, never
   from an abbreviation or legend table (the manifest check warns `revision_from_table` for an entry outside the title-block
   zone). Same sheet in two revisions → blocking question which is current; take no value from either until answered. No
   revision anywhere → `revision: null`, one non-blocking question per set. The sheet number is the entry the manifest names as
   `number_entry`; sheets that print no number go together in one question, never one each.
4. **The works in one paragraph.** Name and use as printed; blocks; disciplines drawn (RC foundation, RC frame, steel frame,
   roof, enclosure, ancillary works); storeys; structural system as a first reading with its entries.
5. **Load path.** Write it from the roof down, one line per link, each naming the sheets that show it or `no sheet`. For a steel
   building on piles: sheeting → purlins → rafters → columns → base plates and anchor bolts → pedestals or caps → piles;
   lateral: bracing, portal action, crane loads. A link with `no sheet` is a scope gap, asked in this phase. The load path gives
   the manifest `order` of the member parts.
6. **Breakdown tree.** Nodes follow the works, not the sheet order: block first when the set holds several buildings, then part
   (foundation, ground floor, each storey, roof, steel frame), then member group. A sheet that fits no node, or two nodes of
   different blocks, is listed unplaced with its reason. Then write the reading order along the tree.
7. **Layer map.** From the phase 0 `geometry` summaries: per member layer of each plan, what member it holds, with its evidence
   (a legend entry, a mark text inside the outline, a schedule row) and confidence. A layer named like a member (`S-CAP`) is a
   hint (E14), never the evidence. Write it in the `sheets` cell of the plan's Breakdown row (`plan-1 [S-CAP: pile caps; S-PILE:
   piles]`); it becomes `layers.outline` and `layers.symbol` of that member part. A layer you cannot place stays in a question.
8. **Manifest** (form and example: part-mode.md § Manifest). The tree becomes `W/parts/manifest.json`: a `blocks[]` row per
   block (its grid systems; `origin_note` says where its grid origin sits on its plan), a part per leaf (`<block>-<family>`),
   the two cross parts, `all-no-sheet`, `scout`, `all-assembly`. `all-grid-levels` takes, per block, the setting-out or grid
   plan and the sheets that print the datum or a level schedule; `all-notes-materials` takes the general-notes, legend and
   typical-detail sheets; a sheet may also sit in a member part. A member part lists its `inputs` (the parts below it on the
   load path), sheets with `number_entry`, `title_entry` and a `views[]` item (heading entry) for every titled view of a plan,
   section or detail sheet that holds values, tables, phase 0 clusters, and the `marks_regex` of its own family only. A part over 4 sheets or 1,500 printed entries is split, never merged. Run `harness part manifest-check W` until exit 0:
   - a **problem** is fixed in the manifest;
   - a **warning** is acknowledged by its exact id in `acks[]`, with a question or a reason, after you looked:
     `grid_origin_other_block` (E41), `linework_duplicate` (E40), `revision_from_table` (item 3);
   - units come only from the engineer's answer, which the orchestrator records (SKILL.md § Asking). Until then `manifest-check`
     reports `unit_unanswered` (no ack clears it) or `unit_answer_unread`: hand the units question ids back and stop; resume
     after the answer. A missing `question-registry.json` means `harness intake` has not run.

Breakdown table: `id | parent | node | sheets (detector id, title entry) | grid system | coverage | confidence | question`.

Coverage is `titled` in this phase (the scout reads no content); `absent` needs the search record, `unread` the count and
question. After the scout a node's coverage is the status of its parts in `harness status`; every manifest sheet must carry a
row or a finding of its part (an unreadable sheet gets an `unread` row citing its question).

The confirm question (`reader_breakdown_confirm`, Vietnamese) shows the blocks, what is proposed (`đề xuất (chưa xác nhận)`),
what is absent or unread, the unplaced sheets, and offers: (a) as proposed, (b) one building in two versions, (c) another split.

## Recording forms

Where no finding kind fits, record evidence like this and never bend a kind:

- **Level or datum text:** `note_item --field topic=other` with the verbatim level text. The `--note` starts `block: <id>;
  element=level|datum`.
- **Grid, level candidate or mark from a producer:** cite the artefact pointer `grid-systems.json:<system_id>`,
  `structure/<file>.levels.json:<candidate id>` or `marks.json:<mark>`, plus the entry ids.
- **Blocks, list, revision, family, base claims (scout):** a row of the Breakdown table, citing entry ids and pointers. A
  `single_source` row carries its question.
- **A value of a member or a rule: one row of `W/parts/<part>/values.json` per mark × field** (schema `part-values`, example
  `schemas/examples/part-values.example.json`). The row has `mark` (as printed) or `subject` (what a markless row is about:
  `piles`, `grid S001 A-B`, `concrete of caps`), `field`, `value`, `file`, `sheet`, `view` (copied from that sheet's manifest
  `views[]`, or left out), a `state` and `cites`:
  - `seen`: value set, with at least one cited finding, entry, geometry item or `hand_sum`; `asked`: a cited question, value
    null or the candidate reading; `unread`: value null, a cited question; `absent`: value null, a cited finding or question
    that holds the search record.
  - The `value` is the printed text, its unit as printed and never converted: one entry's text, or the cited entries' texts
    joined by single spaces in reading order. Every number in it is in a cited source; a token that glues digits to other
    characters (`-1.200`, `2Ø16`, `1-1`) is in a cited entry's text.
  - A **match is a row**, not a finding. The `count_plan` and `count_schedule` rows of one mark, both `seen` and equal, are the
    plan-against-schedule result; a printed size beside a measured one is two cites on one row. `cross_check` records a
    disagreement only (two entries, or one entry plus `--source`/`--items`, and `--question`).
  - A **grid row** cites the finding and the grid system (`cites.grid_systems`). The grid system backs no number and no `seen`:
    the entry or measurement does.
  - A **hand sum** is `hand_sum.terms[]`: `{finding, of: symbols|items}`, `{marks: M}` (the plan marks of `marks.json` equal to
    M on the row's sheet) or `{entry: T}`; the `value` is exactly the total. A term that uses another part's finding or row
    needs that part in the manifest `inputs`, else `cite_foreign_part`: a part with no count finding of its own records its own.
- **A value read off another quantity** (a pile-cap size from the bar lengths of its schedule row, a beam depth from its stirrup
  width, a count from a total line): never the value. Quote it as `suy ra: <figure> from <entry ids>` inside the question that
  asks for the value.
- **A measured finding** (`finding add --kind measured`; recipe: tools.md § Recording; confidence: tools.md § Measured
  findings): `--value` is the counted or measured value of ONE member type with unit and layers, `--field quantity=`, `--items`
  every `G-` id of that type, one `--claim KEY=VALUE` per number of the value, `--entries` the mark entries and any agreeing
  printed value (optional), `--note` the claim form with `render: <image name>`. Omit `--sheet` when a cited entry sits on
  another sheet than the plan (the tool refuses entries not on `--sheet`; the saved document still names the plan sheet).
- **One question for a family's linework values** (tools.md § Measured findings), only where a measured row has no agreeing
  printed entry, at most one per part, none from copied linework (E40): `harness ask W --code reader_family_linework --file
  plans.dxf --sheet plan-1 --where "B1 caps, plan-1" --found "F-012 12 caps 1500x2400, 3 piles; F-013 7 caps 900x900, 1 pile
  (measured, no printed entry)" --text "Đài móng B1: 2 loại kích thước và số cọc mỗi loại đo từ nét vẽ như bảng sau, đúng
  không?" --blocking --part B1-caps`; each finding cites it with `--question`.
- **`--question` on a finding** is the question that asks that finding's own value, not the nearest open question of the same
  block; a value asked nowhere gets its own question first.
- **A work folder that already holds reader findings** (E35): the scout runs `harness finding list W`, reads
  `reader-questions.json` and lists them in its `counts:` line (`findings=<n>, reader_questions=<n>`). Cite an active finding or
  open question that still holds instead of recording it again; the `node:` of an old finding goes in the Breakdown table.
  Withdraw one (`finding withdraw W F-… --reason "…"`) only when your reading of the same entries differs, then record the new one.

## Phase 2. Rules (part `all-notes-materials`)

*What does the designer say applies to every sheet?* [B1, B2]

Topics, each per block; each is a `note_item` finding and a row (`subject` names topic and element; `field` `material` for grade
and class topics, `other` for the rest). The names in code are the tool's `--field topic=` values; the `other` topics name
themselves at the start of `--note`.

- `design_code`: standards with editions, load standard. `concrete_class`: class per element (pile, cap, beam, slab, lean
  concrete). `rebar_grade`: grades per diameter range. `steel_grade`: grade per member class, plate.
- `bolt_grade`: bolt class and standard, anchor bolt grade and standard. `weld`: electrode, size rule, inspection. `cover`: per
  element. `lap`: laps, anchorage, hooks.
- `convention`: U.N.O., TYP., SIM., symmetry and mirror statements; legend (symbols, hatches, abbreviations, bar-mark style).
- `other`: pile type, size, class, capacity, test load; cold-formed members (purlins, girts); surface treatment (paint,
  galvanising, fire protection); who designs connections and what the fabricator details; tolerances; grout under base plates.

Rules of use:

- Quote verbatim; the scope of a note (which element, which block) comes from its clause heading.
- **Notes sit on drawing sheets too** (a pile-head fill concrete beside a detail, a slab-thickness note on a plan, a grade in a
  table header). Search every sheet of the block, not only the notes sheets, with the topic's terms before a topic is `unread`
  or `absent`. A hit on a sheet of another part is recorded by that part; here the topic's row is `unread`, citing a question
  that names the entry, and `notes.md` gets `needs: <part>, <topic>, <entry id>`.
- Two notes that give different values for the same scope → one question per item; you pick neither.
- A note sheet shared by two blocks is recorded for both only when a sheet says so or the engineer answers; otherwise the second
  block's topics are `unread: no notes sheet of its own` in one question.
- **Typical details** are rules, not members: record what each applies to (`áp dụng cho`, `điển hình`, `TYP.`). A typical detail
  with no stated scope is a question.

## Phase 3. Frame (part `all-grid-levels`)

*Where is everything measured from?* [B3–B6]

1. **Units** are the engineer's answer; you add evidence, never a value.
2. **Grid per block.** From `grid-systems.json`: which system each plan of the block uses. Every plan of one block shows the
   same labels and spacings: RC foundation and steel column-base plans are compared label by label; a difference is a blocking
   question quoting both. Two blocks whose plans carry the same labels are two grids for the model even when the tool reports
   one system: ask (E01). A grid labelled wider than the members drawn on it is C11's question (assembly); note the overall
   dimensions here for it.
3. **Relative position of blocks.** Where the set holds two or more blocks, where one stands against the other (the offset
   between their grid origins, or the axes that coincide) is a value the model needs. Search the site plan and setting-out
   sheets (§ Search terms, *Block position*). Printed → a row (`subject` `position of B2 against B1`, field `other`). Printed on
   no sheet → one blocking question, state `asked`; never take it from the plans' places in the file or from equal labels.
4. **Sum check.** Overall dimension against the sum of the spacings, as the tool reports them. Per spacing, read
   `spacing_evidence[].status` in `grid-systems.json`: `dimension_agrees` needs no question; `dimension_measured` needs none
   only when the spacing is a whole number of millimetres (recorded "printed, default text" at normal confidence), else it
   is asked; `dimension_differs` and `no_dimension` are always a question.
5. **Datum.** `±0.000` and the absolute level printed beside it; whether every sheet of the block states the same pair.
   Structural and architectural datums may differ: ask per block.
6. **Levels a model needs.** Storey levels; for a single-storey steel building the reference levels printed instead (top of
   concrete or pedestal, underside of base plate, eave, ridge, crane rail, mezzanine); for foundations: pile cut-off, cap top
   and bottom, ground beam top, slab top. Each is `seen` or in the level question of its block.
7. **Finished or structural.** A floor level is one or the other only when the sheet says so; otherwise it stays in the block's question.
8. **Orientation.** North arrow, mirrored or rotated views, key plans: edge cases E09 and E28.
9. **Producer questions that close this phase.**
   - `grid_system_select`: the engineer answers `systems=` or `separate=`;
   - `grid_system_axis_unassigned`: `dir1=X dir2=Y`;
   - `level_storey_selection` and `level_finished_vs_structural`: answered by the engineer.

   Add evidence with `ask --supplement Q-…`; never raise a reader question on the same subject. Every open producer grid question
   gets a supplement before the phase closes: the measured and printed dimensions of each plan of the block (`dimensions`, tool
   measure and text rule quoted) and the scale reading, or the sentence that none exists. Without a producer
   `level_storey_selection` for a file, raise one blocking `reader_level_storey_selection` per file listing the candidates
   verbatim. A blocked level is no candidate.

The grid, spacing, axes and level rows of this part use `subject` (`grid S001 A-B`, `level +0.000 of B1`) and cite the finding
and the grid system (Recording forms).

## Phase 4. Members (one member part)

*For each leaf of the part, from the ground up: what is it, where is it, how big, at what level, how many, and where is its
detail?* [C2–C7]

Your part is one family of one block; the manifest `order` is the building order and its `inputs` are locked parts you cite and
never re-record. Per leaf, in this order (the **trace**):

1. **Plan**: the marks on the plan sheet (from `marks.json`; search the sheet for a mark the tool may have missed before saying
   it is not there) and its member outlines from `contents` (the counting steps below).
2. **Schedule or table**: the row for each mark; quantity column against the count on plan. A table the tool did not recognise
   is read row by row and named as a tool gap (E32).
3. **Section and detail references** on the plan → the target heading → read the detail (size, level, reinforcement or plates,
   bolts) → back to the plan to confirm the detail's mark and location. Each reference ends `resolved (heading entry id)` or in
   the orphan question.
4. **Level source**: which sheet gives the top and bottom of this member.
5. **What a typical detail or a U.N.O. note supplies** for this family.

**Counting members from linework** (replaces counting by marks):

1. `contents` on the plan, one member family per call: the part's `layers.outline` as outline layer, its `layers.symbol` as
   symbol layer (a pile plan: caps and piles; a stub plan: stubs, and the pile layer for the required `--circle-layer`,
   expecting `symbols.total` 0), `--marks` its `marks_regex` (that family only; omit it when the plan holds none), `--dims` when
   the plan's linework may be copied (E40), `--save`. This saved file is also the assembler's C11 input: cite it in the rows and
   findings.
2. Read `summary`: one row per type; size `short` × `long`; piles per outline `symbols`; `count`. Check `symbols.outside`,
   `marks_unassigned`, `marks_ambiguous` and every warning.
3. **Render check, before anything is recorded.** One `render --bbox` around one outline of each summary row (its `centre`, a
   margin of about its long side), and the whole plan once with `--layer` set to the member layers. Confirm that the outline is
   that member, that the circles inside equal `symbols`, that the outline's `marks[]` entry lies at it; members on other layers
   are found from the phase 0 `geometry` outline groups (same sizes on another layer), not from the render. A disagreement is
   chased first.
4. Marks per type: `marks_seen` against `unmarked` per row. A mark applies only to the outlines it was assigned to
   (`marks_seen`), never to the whole row. A mark of another member family in `marks_seen` (a beam mark on a stub row) is never
   the row's mark: rerun without it. Whether the `unmarked` outlines carry the same mark is a finding (the alternative that they
   carry another mark ruled out) or, when the row splits, a question. A mark seen on two types is a question quoting both rows
   and the schedule row.
5. Record one `measured` finding per summary row (one member type): every outline id of the row in `--items`, `--claim count=N`,
   `--claim short=S --claim long=L` and, where piles are counted, `--claim symbols=K`; `--field quantity=count`; value like `12
   caps 1500×2400 on S-CAP, 3 piles each` (claims count=12, short=1500, long=2400, symbols=3) (recipe: tools.md § Recording).
   The row cites the finding. A total over types (36 piles) is no finding: it is a `hand sum` row of the per-type findings'
   `symbols`, each term `{finding, of: symbols}`, compared with `symbols.total` of the document (outside 0).
6. **Invisible members** (a summary row's `invisible` above 0, or the outline-level warning; the file-level warning alone needs
   only the step 3 render): render the region of one such outline. Drawn there by other entities (stubs: outline and hatch) →
   the count stands and the finding says `counted from hidden outlines, confirmed by render`. Nothing drawn → not counted (a
   hidden state); record that with its count. Say only what the tool's warning says (mostly hidden visibility states of dynamic
   blocks; `render` does not draw them); where the render does not settle it, ask whether it prints.
7. **What the tools do not cover** (tools.md § What no tool gives): a member drawn as loose lines, hatch only or two parallel
   lines (beams), a detail only in paper space, a section with no dimension row. Read by text (mark, schedule, printed size);
   count and size are `unread (no outline tool)`, never `0`; one question per family (E39).

**A row per mark × field.** The fields a model needs per member type are those of `schemas/spec.schema.json` (the ones
drawing-analysis-report Part B uses); the manifest's `expected_sources` say which sources the part has. `size`, `thickness`,
`depth` or `length` per mark; `count_plan` and `count_schedule`; `piles_per_member` for a pile bearing member; `level_top` and
`level_bottom`; `material`; `axes` of a point member, `start_axes` and `end_axes` of a linear one. A row that cannot be read is
`unread` or `asked` with its question; a field settled by no source needs a blocking question, except `material` and `other`.

**Member detail is never dropped.** Each mark has its own size row: the section or plan size of a cap, column stub or pile
(diameter, class), the depth and width of a ground beam (`25x50` is a size; its unit is the units answer or a question), the
thickness of a slab (`hs=…`, `dày`), the section of a steel member. A plan size comes from `contents` (`short` × `long`); it is
the real size only while the plan's grid spacing is backed as Phase 3 item 4 says; say so in the finding's `--note`, else ask,
one question per plan sheet quoting the `contents` values. The printed size (`marks.json` `size`, a schedule row, a section) is
the second source with its entry ids: equal (within E42's spread counts as equal; the printed value is the value) → two cites on one `seen` row, different → `cross_check` and a question. Depth,
thickness and any size from a detail or section come from printed dimensions; **before taking one run `dimensions --sheet <S>`**
(E06): only a row with `override_value` or `expected_text_value` gives a ratio (that value ÷ `measured`); a `text_rule:
measured` row confirms none. A ratio on this detail → size = measured × ratio, both sources recorded. No ratio → a linework size
is recorded only with an agreeing printed dimension (a text entry; an automatic dimension has no entry id), else a question; no
dimension rows → `unread` (E39). Search the sheet that locates the mark and its detail for the size words (§ Search terms,
*Member sizes*) and quote its `dimensions --sheet` values with their counts before a cell reads `unread` or `absent`. A row
holding only a sheet name is empty. A size is `seen` when printed beside the mark or in its schedule row, `single_source`
otherwise.

**Copied linework.** Where the plan's linework may be a copy of another block's (the `linework_duplicate` warning, or `contents
--dims` `disagree` at E42's `--tol` on outlines of one row), a size or count from linework needs a mark and an agreeing typed dimension on that
sheet. Cite its entry (`printed_dims[].entry_id`); an automatic dimension has none and confirms nothing. Without one the row is
`unread` and one question to the designer names the copy (E40). A drawn size within E42's spread of its printed one raises
no question (E42).

**A discrepancy is a question.** Two sheets of the part that state different values, or a drawing error you saw (a mark on no
plan, a dimension that contradicts its neighbour), get one question to the designer, whether or not it changes a number.

A mark's role (column, pile cap, tie beam) comes from the engineer's answer to the prefix question, or is written `đề xuất (chưa
xác nhận)` with the title entry that suggests it. A section label, bar number, sheet code or profile letter is not a mark
family: conventions.md § Collisions.

**Done when** the part's C2–C10 checks (Phase 6) have run. Write `notes.md` first (≤ 60 lines: scope, `unread` and `absent` lines
with question ids, tool gaps, `not run: <C>, <reason>, Q-id`, `needs:` lines, and a `counts:` line, § Required counts); then run
`harness part check W --part <part>` to exit 0 and hand back. A problem it names is fixed in `values.json` or in the findings;
`input_invalid` names a tool-written file to regenerate, not a row to fix. The orchestrator records `checked` (part-mode.md § Dispatch and fix loop).

## Phase 5. Reason (assembler)

*If I had to defend this reading to the designer, where would it break?*

Run once per block after its member parts are locked (`harness status W --verify` first: a part showing `check_failed: true` or `input_check_failed` is named to the orchestrator, who alone decides on `reopened`), reading their rows
(`harness status`, `part chain`), findings and `notes.md`. The key claims go in `W/parts/all-assembly/notes.md`, one line each: `K | status (claimed |
question | unread) | value | findings or rows | basis | alternative ruled out by | question`.

- K1 blocks and the sheets of each. K2 parts and disciplines drawn, and those not in the set. K3 drawing list: missing and
  unlisted sheets, repeated numbers. K4 revision and issue status per sheet, any sheet twice.
- K5 evidence on units (dimension magnitudes, level format). K6 structural system per block (frame, lateral system), on which
  entries. K7 foundation system per block (pile type and size, caps, ground beams, slab).
- K8 grid per block: labels, spacings, overall size; do all sheets agree, do the members fill it (C11). K9 datum; storey,
  reference and local levels; finished or structural.
- K10 standards with editions, and the concrete, rebar, steel, bolt and weld grades. K11 member families, marks, sizes, where
  each is sized, plan against schedule counts.
- K12 where the frame meets the foundation: column bases per block, grid points, anchor bolts, pinned or fixed as the designer
  labels it; do caps, stubs and bases agree in number (C12).
- K13 contradicting values, and where. K14 what the engineer must supply or decide before a model is planned.

For each `claimed` line write the strongest other reading and what rules it out. Usual rivals: two blocks ↔ one building in two
versions; a missing discipline ↔ a discipline not yet issued ↔ a discipline in another file; storey level ↔ local level; mark
family ↔ section label; this block's notes ↔ the other block's notes; structural level ↔ finished level.

**Surprises.** Read the rows once as the person who must build it: every column base sits on a foundation; every foundation
carries something; bases, pedestals and caps per block agree or the difference is explained; no schedule row lacks a place on a
plan; no span or level changes between two sheets of one block; no axis is empty on every plan of its block. Each surprise is a
question.

## Phase 6. Analyse (part reader: C2–C10; assembler: C1, C11, C12)

Each part reader runs C2–C10 on its own sheets before `part check`; a check that did not run is a `not run` line of its
`notes.md`. The orchestrator has run `harness part conflicts W` after every `checked` receipt and runs it again before assembly
(part-mode.md); the assembler reads its questions, then does C1, C11 and C12 per block. An agreement is two rows (Recording
forms); a mismatch is a `cross_check` finding citing both entries, or one entry plus a saved `contents` document, with its
question (`--part` the part that found it, `all-assembly` for C1, C11, C12). Rank the problems Critical / Major / Minor, each
with its question id, in the `notes.md` of the part or of `all-assembly`.

| C | Cross-check |
|---|---|
| C1 | Drawing list ↔ sheets, both directions; sheet numbers unique |
| C2 | Grid labels and spacings equal on every plan of the part; sum of spacings = overall dimension; RC grid = steel grid |
| C3 | Datum pair and each named level equal on every sheet that states them |
| C4 | Same mark → same name, size and bar diameter and spacing on plan, schedule, section and detail; a plan mark that no detail or schedule row names, and the reverse, is listed; a detail or schedule row whose count, length or position matches a plan member that carries another mark (`B-7 (SL 03, L=6.4m)` against plan `B-8` ×3 on one axis) is listed as a mismatch |
| C5 | Count on plan = quantity in schedule, per mark (`contents` or `marks.json` counts only) |
| C6 | Grade in the notes = grade in schedules and tables |
| C7 | Every section and detail reference resolved; every detail heading owned by a family |
| C8 | Every typical detail has a stated scope; every family it should cover is covered |
| C9 | Every engineer answer consistent with allowed, printed entries |
| C10 | No value taken from a sheet whose revision is in question |
| C11 | **Spatial occupancy per block**: on each plan, which axes and bays carry piles, caps, ground beams, slab edges, steel columns; every axis or bay of the block's grid that carries nothing is named |
| C12 | **Count chain per block**: along the load-path links phase 1 named, from the foundation up (for example piles, caps, pedestals or column stubs, column bases or columns, schedule rows), the count of each link against the next, per mark where both links use the same marks, and in total; each `.1/.2` pair counted as one column and as two, both totals quoted, the pairing a question and never adopted; piles on plan = pile count printed in the title and notes |

You compare printed values and tool-reported numbers for equality, and you may add integer counts the entries or the tools print
(write `7+12+3 = 22`, addends cited, the sum labelled `hand sum`, never a finding value on its own). Lengths of beams, weights,
areas and level differences belong to a tool; without one the cell is `not run: no tool` (beam lines are outside `contents`,
E39).

**C11 procedure.** Per member plan of the block, take the part's saved `contents` document (Phase 4 counting step 1). From
`outlines[].axes` take, per grid family, the labels that carry members and how many outlines each (to count, group the rows of
the saved file with a scratch `python -I -c`, labelled `manual: scratch grouping`, a fallback until T27 `contents --by-axis`
exists; cite the document and ids). Piles take the axes of the cap that holds them. Compare with the axes of the block's grid
(`grid-systems.json`): axes with no member on any plan of the block, a row of members that stops short of the grid's overall
dimension, or a grid labelled wider than every member drawn means the block may sit on a grid shared with another block or
copied from it. That is a `cross_check` finding and a blocking question (the grid of a block is a gate 1 value) quoting both
readings: the grid is right and the block is partly drawn, or the grid is wider than the block. Outlines in no grid group
(warning) are listed with their ids: the grid may be missing on that view, or the member lies outside it (E37). Never shorten
the grid yourself (E29); read dimension entries before concluding. Members with no outline (E39): fallback, labelled `manual: by
mark position`: assign each `marks.json` `plan_marks` entry of the family to the nearest axis label of the same direction, by
position only, and write per axis the count with the entry ids.

**C12 procedure.** Build the chain per block with `harness part chain W --block B`: per part in manifest order, the
`count_plan`, `count_schedule` and `piles_per_member` rows with their hand-sum addends and the products `count × piles`. Quote
the counts side by side; the tool judges nothing. Plan links come from the per-type `measured` findings and the saved `contents`
`summary`; a plan total (piles) is a `hand sum` of their `symbols`, checked against `symbols.total`; schedule links from
`marks.json` or entries. A mismatch between a schedule quantity and a counted type is a `cross_check` with one schedule entry
plus `--source` and the counted `--items`. A schedule that lists marks `T-4..T-6` while the plan shows `T-4` and `T-6` only is
a mismatch even when the totals agree, and a question offers the readings (the schedule groups or renumbers the plan marks;
a count is wrong; a mark is missing). A link the phase 1 load path names but no sheet shows is `absent` or `unread` with its
question; a link the load path does not have is `n/a`.

Whether a part is ready for a model is not written here: `harness status` `parts[]` shows `status`, `blocking_open_ids`, `ready`.

## Search terms

A term of two or three letters counts only as a whole token: read its hits and keep those where the term stands alone or is
followed by a digit; record kept/total in the search record. Every accented term is searched with its unaccented twin too (`part check` problem `search_unaccented`).

Before an `absent`, search every row's terms for the topic, in each spelling `find-text` needs (tools.md). The list is a floor:
add the project's own words from its legend.

| Topic | Terms |
|---|---|
| Drawing list; general notes | `danh mục`, `DANH MỤC`, `drawing list`, `index`, `mục lục`; `ghi chú`, `GHI CHÚ CHUNG`, `thuyết minh`, `general notes`, `notes` |
| Standards | `TCVN`, `TCXDVN`, `QCVN`, `tiêu chuẩn`, `AISC`, `MBMA`, `AWS`, `ASTM`, `JIS`, `GB` |
| Concrete; rebar | `bê tông`, `mác`, `cấp độ bền`, `B15`…`B60` (each class), `M150`…`M600` (each mark); `cốt thép`, `CB`, `CI`, `CII`, `CIII`, `AI`, `AII`, `AIII`, `SD` |
| Steel | `thép`, `mác thép`, `SS400`, `Q235`, `Q345`, `Q355`, `A36`, `A572`, `CCT`, `S235`, `S355` |
| Bolts; welds | `bu lông`, `bulông`, `bulong`, `bolt`, `cấp bền`, `8.8`, `10.9`, `neo`, `anchor`; `hàn`, `que hàn`, `đường hàn`, `weld`, `E70`, `N46` |
| Cover, laps | `lớp bảo vệ`, `bảo vệ`, `cover`, `nối chồng`, `neo`, `lap` |
| Levels | `cao độ`, `cốt`, `±0.000`, `+0.000`, `COTE`, `EL`, `đỉnh`, `đáy`, `cắt cọc`, `đầu cọc` |
| Piles | `cọc`, `PHC`, `PC`, `D300`…`D600` (each size), `sức chịu tải`, `thử`, `ép`, `đóng`, `khoan nhồi` |
| Revision | `REV`, `sửa đổi`, `hiệu chỉnh`, `lần`, `phát hành`, `ngày` |
| Member sizes | `hs=`, `h=`, `dày`, `tiết diện`, `kích thước`, `KT`, `b x h`, `bxh`, `x` (keep hits of the form digits-x-digits), `D300`, `Ø` |
| Scope of a typical detail | `điển hình`, `áp dụng`, `tương tự`, `đối xứng`, `TYP`, `SIM`, `U.N.O` |
| Block position | `mặt bằng tổng thể`, `tổng mặt bằng`, `site plan`, `layout plan`, `định vị`, `tọa độ` |

## Required counts

Each count is stated with its command and JSON field path, in a `counts:` line of the role's `notes.md`:

- scout: files, sheets, sheets_blocked, unassigned_clusters, clusters_assigned, geometry_calls, sheets_classed, sheets_unplaced,
  list_differences, nodes, parts, manifest_warnings_acked;
- part reader: `harness part check` prints rows by state, findings and questions (`counts`); the reader adds contents_runs,
  render_checks, orphan_headings, measured_findings (`finding list W --kind measured`);
- assembler: K_claimed, K_question, K_unread, surprises, checks_run (of C1, C11, C12), blocks_with_C11, blocks_with_C12,
  mismatches.

`geometry_calls`, `contents_runs` and `render_checks` have no JSON field: each is the count of calls you made.
