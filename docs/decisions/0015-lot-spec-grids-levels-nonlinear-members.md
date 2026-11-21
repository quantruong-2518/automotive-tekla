# 0015. Lot spec: grids, levels and non-linear members

- Status: Accepted (engineer, 2026-11-11)
- Date: 2026-11-10; revised 2026-11-11 after an independent review
  (`projects/_evals/wave4-2026-11-10/REVIEW-ADR-0015-0016.md`) and the engineer's answers Q1–Q17
  and OQ-A–OQ-E
- Decided by: orchestrator design (tool wave 4, EVAL-4 ranked fix 8); engineer decisions marked
  "(engineer, 2026-11-11)"; accepted by the engineer together with ADR-0016
- Safety: a lot-0 `update` with `--allow-untagged-shift <question_id>` may now make a
  non-additive lot-0 grid change that moves, re-levels or orphans **untagged** engineer parts on
  the grid or bound to its levels, when no member lot exists and an engineer answer authorises it
  (decision 10). Without the flag it still refuses, and nothing else that was refused is now
  allowed. The commit that adds the flag to the contract carries this line.
- Amends: [ADR-0012](0012-run-journal-and-resume-planner.md) §1, §6, §7 and §8 (section
  "Amends ADR-0012" below)

## Context

EVAL-4 failed criterion 7 because some objects had no build-side route. `spec.schema.json` and
`docs/tekla-cli-contract.md` carry straight members only (`start` → `end`). They have no grid and no
level, so the selected grid systems and storey Z chains could only be built by hand. Both J2 judges
counted this as a no-route gap (EVAL-4 ranked fix 8). On 2026-11-10 the engineer decided that grid
and level objects, curved and polyline beams, slabs, footings, pile caps, piles and walls go into
the lot spec and the CLI contract now (`docs/roadmap.md`, "Open before later steps"). This ADR
covers grids, levels and curved or polyline beams. [ADR-0016](0016-lot-spec-slabs-footings-piles-walls.md)
covers the area and volume objects. This ADR is the design only: the code that writes to Tekla waits
for the test-model checks below.

**Tekla target: 2026** (engineer, 2026-11-11, Q1). The company runs Tekla 2026 Diamond. The API
facts below are read first from `Tekla.Structures.Model` 2026.0.3 (PKG26). 2024.0.4 (PKG24) is
cited only to show that a member is not new. The repo still pins 2024.0.4 in ADR-0009, the contract,
`tekla/api-notes.md` and `tekla/README.md`. Execution package 1 moves those pins; this ADR does not
edit them.

Open API facts used below. They come from the docs and have not been run on a model. Sources are in
[`0015-schema-draft.md`](0015-schema-draft.md) § "API facts".
- **Levels.** There is no level object. A level is a Z plane of a `Grid` (`CoordinateZ`/`LabelZ`).
  Tekla 2026 binds parts to grid levels with `Beam/PolyBeam.StartLevelName/EndLevelName/...Offset`
  and `ContourPlate.LevelName/LevelOffset`. These members are absent in 2024.0.4 (F5). Bound parts
  follow when the level moves (F12). 2026 SP4 adds an `Auto` binding to the nearest level, and the
  docs do not say whether it is the default (F13).
- **Grids.**
  - `Grid` (via `GridBase`) has `Name`, `Origin`, `IsMagnetic`, `Insert/Modify/Delete/Select` and
    `SetUserProperty`. Its children are `GridPlane` objects (F6, F7). Neither `Grid` nor `GridBase` documents a
    rotation member: their full member list in the 2026.0.3 XML was read on 2026-11-11 (F6). A
    rotated grid can therefore only come from the work plane it is inserted in (`TransformationPlane`,
    K19 of ADR-0016). `ModelObject.GetCoordinateSystem()` ("Returns the coordinate system for the
    given model object") is the candidate to read the rotation back (T7).
  - The UI enters X/Y as spacings from the previous line and Z as absolute values (F10).
  - The API docs do not say how the API reads the strings, but the constructor defaults support the
    UI reading (F6, nuget-metadata): `CoordinateX "0.00 4*3000.00"` uses the `n*d` repeat syntax,
    which makes sense only for spacings, and `CoordinateZ "0.00 6000.00 8000.00 9000.00"` with
    `LabelZ "+0 +6000 +8000 +9000"` match only if Z is absolute. To verify T1 still checks `Origin`
    handling and the read-back form.
  - `objects.inp` has a `grid` section, and `CatalogObjectTypeEnum.GRID` exists (F9, F14).
  - The documented Grid members are the same in 2024.0.4 and 2026.0.3.
- **Non-linear members.**
  - `PolyBeam` is "a continuous beam with a contour as input": a list of `ContourPoint(Point, Chamfer)`.
    `Chamfer.CHAMFER_ARC_POINT` rounds a polybeam corner into an arc (F1, F2).
  - The Curved beam component produces "a poly-beam" with 3 points and its middle point set to an arc
    chamfer (F16).
  - `Beam.Radius` appears in the XML only as a field. The field reads: "Used only internally! May be
    removed later when conversion from curved to polybeam exists". There is no property and no
    constructor for it, so there is no API route to the UI's radius-based curved beam (F4).

## Decision

0. **Tekla target 2026** (engineer, 2026-11-11, Q1). The design, its API facts and its To verify
   items target Tekla 2026 (`Tekla.Structures.Model`/`.Catalogs` 2026.0.x). Writes still wait for
   the test-model checks. The repo's 2024.0.4 pins move in execution package P15-1, not in this
   ADR.
1. **Three kinds, two new spec arrays.**
   - `grids[]`: one Tekla `Grid` each.
   - `poly_members[]`: one Tekla `PolyBeam` each.
   - Levels are **not** a separate array. They are `grids[].levels[]`, the Z planes of the grid
     they belong to. Tekla has no level object, and 2026 binds parts to grid elevations by grid name.
     A project with several buildings or wings has several grids, each with its own levels.
   - `members[]` keeps its shape.
   - The spec `$id` stays `0.1` (AGENTS.md). Every schema change goes in a CHANGELOG entry.
2. **Grid shape and frame.** The fields are `spec_id`, `name`, `origin`, `rotation_deg`, `x_lines[]`,
   `y_lines[]`, `levels[]`, `question_ids` and `notes`.
   - **Frame** (engineer, 2026-11-11, Q17: rotated and non-orthogonal grids are in scope now).
     - `origin` is a global point in mm with `z = 0`.
     - `rotation_deg` is the angle from global +X to the grid's local x axis, counter-clockwise seen
       from +Z, in (−180, 180].
     - Both are `sourced_*` values that come from an engineer answer (engineer, 2026-11-11:
       confirmed; decision 6, rule (r)). The `grid-system` tool already leaves origin and direction
       to gate 1, and its `angle_deg` is drawing-side only.
   - **Lines.** A line is `{label, position}`. A level is `{label, z}`. Each label is a
     `sourced_string` and each number a `sourced_number`, so every value carries provenance and
     confidence.
   - **Positions are absolute, never spacings** (engineer, 2026-11-11, Q7: absolute mm per line, each
     with provenance, and the CLI composes Tekla's spacing strings).
     - A line's `position` is its distance in mm from `origin` along the grid's local axis: local x
       for `x_lines`, local y for `y_lines`.
     - Q7 together with Q17 means absolute positions in each grid's own frame, equal to global X/Y
       when `origin` is (0, 0, 0) and `rotation_deg` is 0 (engineer, 2026-11-11: confirmed). For a
       rotated grid, global X/Y cannot describe a line by one number. The frame itself is global.
     - Levels are global Z.
   - **One-direction grids.** `y_lines` is either empty or holds at least two lines. An empty
     `y_lines` makes a one-direction grid: one family of parallel lines. See "non-orthogonal" below.
   - **How the CLI builds it.**
     - It sets `IsMagnetic = false`. Extensions keep the constructor defaults.
     - It writes X and Y as `0 d1 d2 …` spacings from the first line, each with exactly 2 decimals.
       Z is written as absolute values.
     - `rotation_deg = 0`: the global work plane is set (as ADR-0012 already requires for the
       snapshot). `Origin = origin + (x_lines[0].position, y_lines[0].position or 0, 0)`. This route
       depends only on To verify T1.
     - `rotation_deg ≠ 0`: the CLI sets a work plane whose origin is `origin` and whose X axis is
       global X turned by `rotation_deg` about +Z. It inserts the grid with
       `Origin = (x_lines[0].position, y_lines[0].position or 0, 0)` in that plane, then sets the
       global plane back. With a horizontal plane at Z = 0, levels stay global Z. This route is
       **blocked until To verify T7 passes**. T7 checks four things: the rotated plane gives a rotated
       grid; how the grid reads back in the global plane (no rotation member is documented;
       `GetCoordinateSystem` is the candidate); whether the UI's work plane changes; and what state remains after a crash before the
       plane is set back. Until T7 passes, the CLI refuses a grid with `rotation_deg ≠ 0` (exit `5`).
   - **Non-orthogonal axes.** One Tekla `Grid` is orthogonal by construction. They are covered in two
     ways:
     - **(1) Several orthogonal grids.** A layout whose families pair up at right angles is several
       grids, each with its own origin and rotation. The common case is a main grid plus a rotated
       wing. This needs T7 only.
     - **(2) One-direction grids.** A family without a perpendicular partner, such as a parallelogram
       grid or a skew family, is a one-direction grid with its own rotation. This route is **blocked
       until To verify T8** shows how Tekla takes an empty `CoordinateY`/`LabelY`, and that no extra
       line appears. If T8 fails, such families stay `engineer manual` at gate 3. A new ADR then
       weighs single grid lines (`GridPlane`).
     - Radial grids and curved grid surfaces stay out of scope.
   - `name` is a harness choice, not a drawing value (2026 binding picks levels by grid name).
3. **Level values** (engineer, 2026-11-11, Q5).
   - Every elevation in a spec comes from an engineer answer, directly or derived from one, with its
     `question_id`. In this ADR that is every level's `z`, and the Z of every `members` point
     (`start`, `end`) and every `poly_members` point, taken from the engineer-confirmed levels,
     directly or derived (engineer, 2026-11-11, OQ-B) (rule (f)). ADR-0016 extends the rule to slab
     tops, wall bases, footing and cap tops and bottoms and the pile head. A pile's toe is the one
     exception (Q14).
   - `schemas/examples/spec.example.json` is updated so that each member point is `derived` from
     its drawing source and the storey-levels answer (draft §3.4, OQ-B).
   - The reason: `levels.json` stores metres as written and never knows whether a level is structural
     or finished (its schema says so), so a drawing value alone is a guess.
   - The conversion from metres to mm happens upstream, in the tool that writes the spec (method
     `derived`). The CLI never converts.
   - The spec-writing tool also checks that each cited answer is active and was recorded with
     `answered_by_role: engineer`, as ADR-0013 decision 3 does for grids. `check_spec` cannot see
     `answers.json`.
4. **Non-linear member shape.** The fields are those of `members[]`, with `points[]` (at least 3)
   in place of `start`/`end`.
   - Each point is a global mm point with `chamfer`: `none` (a corner, `CHAMFER_NONE`) or
     `arc_point` (`CHAMFER_ARC_POINT`), plus its own provenance and confidence.
   - **Intended** meaning of `arc_point`: the run from the previous point through this point to the
     next one is one arc. This matches the UI's 3-point curved beam (start, point on the arc, end).
     No API source states that the built curve passes through the arc point. XML26 says only "the
     arc point type chamfer". This is To verify T3, and it must pass on the test model before the
     first poly member is built.
   - `type` is a harness kind (`beam`, `brace`, `purlin`, `girt`, `rafter`, `other`), always built as
     `PolyBeamTypeEnum.BEAM`. Curved columns are out of scope.
   - A curve given on the drawing by its radius is turned into its arc-point coordinates upstream,
     with method `derived`.
5. **Lot placement** (engineer, 2026-11-11, Q3: lot 0, grids and levels only, gated before the
   member lots).
   - Grids go in a **setup lot, lot 0**, which holds grids only. It must carry `"members": []`,
     because `members` stays a required key.
   - Lots 1 and above hold `members`/`poly_members` (and ADR-0016's arrays), never grids.
   - Lot 0 gets its own backup, run, gate-4 check and rollback, so members never depend on an
     unapproved grid. The lot numbers in existing plans stay as they are.
   - The schema enforces the split with `if lot = 0`. One lot 0 per project is a planner and gate
     rule, since it cannot be checked inside one spec.
6. **Validation** (Python stays the only full validator, ADR-0010).
   - Schema: the draft in `0015-schema-draft.md`.
   - New rules in `check_spec`, each with a regression test. Letters (r) and (s) follow ADR-0016's
     (i)–(q), so references in both drafts stay stable.
     - (a) `spec_id` unique across `members`, `poly_members` and `grids`.
     - (b) Grid `name` unique in the spec.
     - (c) Labels unique per axis and per level list. The schema already forbids whitespace.
     - (d) Positions and `z` strictly increasing, each step ≥ 1 mm. Every line position, `origin.x`,
       `origin.y` and level `z` lies on a 0.01 mm step (within 1e-6). This way the 2-decimal
       spacings the CLI writes are exact, and Tekla's rounding of a spacing to 2 decimals (F6) loses
       nothing. T1 confirms the round-trip.
     - (e) Each composed Coordinate or Label string ≤ 1024 characters (the UI limit; the API limit is
       unknown, T5).
     - (f) **Elevation provenance** (Q5). The value's provenance is `engineer_answer`, or `derived`
       with an `engineer_answer` provenance at **any depth** of `derived_from`. This ADR applies it to
       every grid level's `z`, to `members[*].start` and `.end` (except a `pile`'s `end`, ADR-0016
       Q14) and to every `poly_members[*].points[*]` (OQ-B). ADR-0016 rule (p) adds its paths.
     - (g) Poly points:
       - consecutive points ≥ 1 mm apart, and no repeated point;
       - first and last points `none`, and never two `arc_point`s in a row (Tekla's recommendation);
       - each `arc_point` ≥ 1 mm from the chord of its neighbours, else Tekla drops the arc
         (`XS_POLYBEAM_CURVATURE_TOLERANCE`);
       - all points coplanar within 1 mm (Tekla's recommendation);
       - no two non-adjacent segments meeting ("contours must not have loops").
     - (h) The low-confidence rule walks **every** object that holds a `confidence`, at any depth,
       including `points[]`, `origin`, `rotation_deg`, `x_lines[]`, `y_lines[]` and `levels[]`. Today
       it reads only a member's top-level fields.
     - (r) **Grid frame.** `origin.z` within 0.1 mm of 0. `origin` and `rotation_deg` pass the
       provenance test of rule (f): they come from an engineer answer, given at gate 1 (engineer,
       2026-11-11: confirmed). Two one-direction
       grids whose rotations differ by 90° ± 0.5° (mod 180°) are refused, because they are one
       orthogonal grid. The schema fixes the rotation range.
     - (s) Every `engineer_answer` provenance anywhere in the spec carries a `question_id` (Q5,
       "with question_id"). Today `common.schema.json` leaves it optional.
   - `SPEC_RULES_VERSION` is bumped once, with ADR-0016's rules if both land together.
   - The receipt needs **no new field**: its SHA-256 covers every byte, grids and poly members
     included.
   - **Checked so far** (2026-11-11): the draft schema with the **current** `check_spec` only, on the
     draft's examples and a reject set (`0015-schema-draft.md`, top). Rules (a)–(h), (r) and (s) do
     not exist yet and were not run. A scratch probe of rules (d), (f) (member and poly paths
     included), (h) and (s), and of the origin and provenance parts of (r), passes on the examples
     and rejects today's `spec.example.json` under (f). The execution package runs the real rules on
     every example plus one reject case per rule.
7. **Closed-world reader in the CLI.** `SpecLoader` today ignores keys it does not know. Since the
   `$id` stays 0.1, a reader that knows only `members` would accept a valid receipt and silently
   build no grids. So the C# reader:
   - refuses (exit `5`) any key outside the schema, at the top level and at **every nested object
     the CLI interprets**: items, grid lines, levels, frame values, points, provenance;
   - refuses any **enum value** outside the schema (`type`, `chamfer`). Today `ReadMember` accepts
     any `type` string, and an old reader given `type: pile` would build a plain beam;
   - reads `grids` and `poly_members` with the same read-time checks as members: `spec_id` pattern,
     uniqueness across arrays, finite numbers, at least 3 points, `y_lines` empty or ≥ 2;
   - raises `SpecLoader.MinimumRulesVersion` to the new `SPEC_RULES_VERSION`, so a receipt from the
     old rules never feeds the new reader.
8. **Tags.**
   - Grids and poly members get `LOT`, `RUN_ID` and `SPEC_ID` like members.
   - The repo's `objects.inp`, not written yet (ADR-0007 §5), must define the three UDAs in the
     `grid` section as well as for parts. Polybeams: T3 finds which catalog type and `objects.inp`
     section cover them (Trimble's `objects.inp` parser lists no polybeam section).
   - `info` and write commands check `GetUserPropertyItems(CatalogObjectTypeEnum.GRID)` and exit
     `3` if any of the three is missing.
   - Lookups for grids use no UDA filter (To verify #7). The CLI enumerates
     `GetAllObjectsWithType(ModelObjectEnum.GRID)` and reads each grid's tags. A model has few grids,
     so this is cheap. It is the grid's lookup source in ADR-0012 §6 (see "Amends ADR-0012").
   - `GridPlane` children are not tagged and not compared.
9. **Compare: receipt, resume and verifier.**
   - The snapshot (ADR-0012 §6) gains the kinds `grid` and `polybeam`, and per-kind geometry: for a
     grid, its name, origin, rotation and parsed lines and levels; for a polybeam, its points and
     their chamfers.
   - "Differs" for a grid:
     - a different name;
     - origin more than 0.1 mm off (+1e-6), or rotation more than 0.01° off (mod 360°);
     - a different count or order of lines or levels, or any label different (ordinal);
     - any position or `z` more than 0.1 mm off (+1e-6).
   - "Differs" for a polybeam:
     - a different point count or order, any point more than 0.1 mm off, or any chamfer different;
     - a different profile, material, rotation or class, per ADR-0012 §7 without its kind rule.
   - **Kinds.** A grid item matches only kind `grid`, and a poly member only kind `polybeam`. For poly
     members the spec `type` is **not** compared: every poly member is built as `PolyBeamTypeEnum.BEAM`,
     and Tekla keeps no harness kind. A `members` item never matches a `polybeam` or a `grid`.
   - The CLI reads a grid back from its own strings with the same rule it uses to write them. It
     checks once against the `GridPlane` children on the test model (T1; T7 for rotated grids).
   - The verifier compares the `export` CSV. The CSV has:
     - one row per grid (`SPEC_ID`, name, origin, rotation);
     - one row per grid line or level (`SPEC_ID`, axis `x|y|z`, label, position);
     - one row per polybeam point (`SPEC_ID`, index, x, y, z, chamfer).

     IFC is not used for grids. For polybeams IFC is a count check only.
10. **Lot 0 after it is built: update, rollback and untagged objects.**
    - **Member lots exist** is decided **fail-closed, from two sources**:
      - (i) An exhaustive enumeration of the model's objects of every kind the harness builds,
        reading `LOT` per object. A UDA filter alone is not enough (To verify #7, #20).
      - (ii) The run journals of every lot folder beside the spec's (`lots/*/run-journal-*.json`),
        plus `project-state.json`. A lot ≥ 1 counts as existing when a journal of it records at
        least one object entry (a GUID, or an `inserting` intent) and no later complete `rollback`
        of that run. A run that was refused or stopped before its first `Insert` wrote nothing, so
        it does not count.
      - If the two sources disagree, or any tag is unreadable, the CLI refuses (exit `3`). The
        refusal names each lot, run journal and GUID that disagree. The usual case is objects the
        engineer deleted by hand. The engineer resolves it with a `rollback` of that run (which
        records the rollback in its journal), or by restoring the objects. T10 checks that the
        enumeration sees just-inserted, uncommitted objects.
    - **While member lots exist, lot 0 allows additive updates only** (engineer, 2026-11-11, Q4).
      - An additive update adds grids, lines or levels. It moves and removes nothing: each existing
        grid keeps its name, origin and rotation, and every existing line and level keeps its label
        and position or `z` (≤ 0.1 mm).
      - The CLI compares the read-back grids with the new spec. Anything non-additive, and any
        `rollback` of lot 0, refuses (exit `5`): the member lots are rolled back first, decided by
        the engineer.
      - An additive `Modify` must leave every existing `GridPlane` and every part where it was, tagged
        or not, bound or not. This is To verify T9. Additive updates wait for it.
    - **Parts the CLI did not tag.** Engineer-made `engineer manual` parts may sit on the harness grid.
      On 2026 they may also be bound to its levels (F12, F13). So a non-additive update or a
      rollback of lot 0 also refuses (exit `5`), even with no member lot, while any of these holds:
      - any part, tagged or not, has `StartLevelName`, `EndLevelName` or `LevelName` naming a level
        of a grid being changed;
      - any part has a reference point within the grid's extent (its lines' and levels' span plus
        1 000 mm), found by enumeration, not by `GetObjectsByBoundingBox` (To verify #18).

      The refusal lists each such part: GUID, type, name, reference points and level names.
    - **Override flag** (engineer, 2026-11-11, OQ-A: a non-additive lot-0 change is allowed with an
      explicit engineer override, even when untagged engineer parts sit on the grid; the reviewer's
      default, refuse, was not taken).
      - Name: `--allow-untagged-shift <question_id>`, on `update` of lot 0 only. The `question_id`
        is the engineer answer that authorises the shift. The CLI checks its pattern and records it.
        `builder` passes the flag only when its brief cites that answer (P15-9). No agent sets it on
        its own.
      - It lifts **one** refusal: the untagged-part clause above. Any part tagged `LOT` ≥ 1 already
        means a member lot exists, so with no member lot every part the clause finds is untagged,
        and the flag can only ever reach untagged parts.
      - **Before.** The refusal without the flag lists the parts (above), so the engineer decides on
        that list. With the flag, the CLI reads and lists them again just before the change.
      - **After.** After `Modify`, the CLI reads each listed part back and lists it again, marked
        `moved` when a reference point changed by more than 0.1 mm or a level name changed.
      - **Journal.** The run journal header records the flag, its `question_id` and the parts with
        their before and after values (P15-4). The lot report shows them.
      - It does **not** lift: the additive-only rule while a member lot exists (Q4); the exit `3`
        when the two sources disagree or a tag is unreadable; the rule that untagged grids are never
        touched (Q6); the T9 gate. `rollback` of lot 0 takes no such flag and still refuses while
        untagged parts sit on the grid.
      - The flagged route waits for To verify T9, which also checks that the after read-back shows
        what moved.
    - **Untagged grids** (engineer, 2026-11-11, Q6), such as the default grid of a new model or the
      original's grids:
      - the CLI never modifies or deletes them;
      - `build` of lot 0 lists them (GUID, name, origin) in its output;
      - the lot report lists them too;
      - the engineer keeps or removes each one by hand at the lot-0 gate.
    - `rollback` deletes tagged grids like any other object of the run, within the limits above.
11. **Level binding (2026)** (engineer, 2026-11-11, Q2: parts stay unbound on absolute coordinates;
    if the API cannot undo `Auto`, the build route pauses for a new ADR).
    - Members and poly members stay on absolute Z and are not bound to levels.
    - **T4 is the first test on the 2026 test model.** It answers:
      - is a part inserted through the API bound by default;
      - which value unbinds it, before or after `Insert`;
      - whether the unbinding is kept.

      No write route opens before T4 passes. If T4 shows that `Auto` cannot be undone through the
      API, the build route stays closed until a new ADR. The CLI never exits `4` per object in
      production because of binding.
    - Once T4 passes, the CLI sets the unbound value T4 identifies. After `Insert` it reads
      `StartLevelName`/`EndLevelName` back. A part still bound during `build` or `update` is an
      API-level failure: the CLI stops, keeps what it made, writes the journal and exits `4`
      (contract rule 5).
    - A bound part found in the snapshot while planning a resume "differs", and the CLI exits `1`
      with nothing written.
    - A CLI built without the 2026 level members refuses every write command (exit `3`) when the
      running Tekla is 2026 or later. It cannot run the check, so it must not skip it.

## Amends ADR-0012

ADR-0012 is accepted, so this ADR amends it explicitly. ADR-0012 itself gets a dated amendment
note now that the engineer has accepted this ADR (execution package 11). ADR-0016 extends these
amendments for its kinds. Its per-kind table supersedes the one below when both land.

- **§1 and the journal header.** `lot` 0 is a valid lot. `run-journal.schema.json` and
  `RunJournalJson.cs` accept `lot ≥ 0`. "A `RUN_ID` belongs to one lot" is unchanged, and lot 0 has
  its own runs.
- **§6 Snapshot: lookup sources.**
  - The snapshot is the union of each kind's lookup sources, not always the UDA filters.
  - Members and poly members keep ADR-0012's UDA lookups plus the journal GUIDs.
  - Grids use the enumeration of decision 8 plus the journal GUIDs.
  - The "lookups and tags agree" check stays. For kind `grid` it compares the tags read on every
    enumerated grid with the journal GUIDs. It never expects a UDA filter to return a grid.
- **§6 Snapshot: kind vocabulary.** "Kind" is the **Tekla kind** read from the object (table below),
  not the spec's `type` word.
- **§7 "Differs": kind rule.** "The kind equals the spec `type`" becomes "the kind equals the Tekla
  kind that the item's array and `type` map to". This also corrects a gap for today's members:
  `brace`, `purlin`, `girt`, `rafter` and `other` are all Tekla `Beam` of type BEAM, so a literal
  comparison (as in `ResumePlanner` today) could never match them once S2 reads real kinds. Grid and
  polybeam "differs" are decision 9.
- **§8 Plan.** Unchanged, except that grids and poly members are spec items like members.

| Spec array / `type` | Tekla object | Snapshot kind | Lookup sources | "Differs" beyond ADR-0012 §7 |
|---|---|---|---|---|
| `members` `column` | `Beam` COLUMN | `column` | UDA lookups + journal GUIDs | — |
| `members` `beam`, `brace`, `purlin`, `girt`, `rafter`, `other` | `Beam` BEAM | `beam` | UDA lookups + journal GUIDs | — |
| `poly_members` (any `type`) | `PolyBeam` BEAM | `polybeam` | UDA lookups (T3: which catalog type) + journal GUIDs | points, chamfers (decision 9); `type` not compared |
| `grids` | `Grid` | `grid` | enumeration of every `Grid` with tags read + journal GUIDs | name, origin, rotation, lines, levels (decision 9) |

## Out of scope

- Radial grids and curved grid surfaces (`GridCylindricalSurface`). Single grid lines added to a
  grid (`GridPlane`); T8's fallback. Grid extensions, colours and magnetism.
- Building hierarchy objects: `HierarchicObject`, and `ModelObjectEnum.STOREY`, `BUILDING` and
  `SPACE`, which exist already in 2024.0.4 (2026 adds only `BUILDING_SITE`). Also base points and site
  coordinates.
- Binding parts to levels. Decision 11 keeps parts unbound and detects binding.
- Curved columns, spiral beams (`SpiralBeam`), and arcs not lying in one plane.
- Connections, numbering and drawings.

## Consequences

- **Schema**: the spec schema draft and three examples (an axis-aligned lot 0, a lot 0 with a
  rotated wing, poly members), plus a CHANGELOG entry. The entry notes that lot 0 carries
  `"members": []`. Today's `spec.example.json` stays schema-valid but fails the extended rule (f),
  so it is replaced by draft §3.4 in the same change as the rule (OQ-B).
- **`lot` 0** must be allowed in each place that requires a minimum of 1 today (grep of `src/`,
  `schemas/`, `tekla/TeklaCore/` and `.claude/hooks/` at 7150cc5, confirmed by the review):
  - the spec schema;
  - `run-journal.schema.json` and `RunJournalJson.cs`;
  - `project-state.schema.json` (`$defs/lot`);
  - `SpecLoader` (`LotInvalid`);
  - the CLI's `--lot` parsing (S4).

  `check_spec` checks only the upper bound. The guard hook does not parse `--lot`.
- **Members array**: `members` may be empty. The schema `minItems` and the `SpecLoader` "non-empty"
  check give way to "at least one item array is non-empty".
- **Workflow and agents.**
  - `docs/workflow.md` step III runs "for n = 1…N" and now starts at 0, with lot 0's gate 4 before
    lot 1.
  - `builder`, `verifier` and `reporter` handle a lot without members: the lot report shows the
    grids, levels and untagged grids, and any `--allow-untagged-shift` run with its before and
    after part list.
  - `builder` passes `--allow-untagged-shift` only when its brief cites the authorising engineer
    answer.
- **Run journal**: the header gains an optional `override` object (flag, `question_id`, parts with
  before and after values), written only by a flagged lot-0 `update`.
- **Contract**: the additions in the draft, rule 9 with the override flag included. No new
  subcommand and no new exit code.
- **`tekla/api-notes.md`**: To verify T1–T10 (draft §5), and the F facts with F8 corrected.
- **Skills**: `tekla-conversion-plan` Known gaps loses R1. ADR-0016 updates R8.
- **Producer pending.** The contract and the schema give grids and levels a route. No tool writes a
  lot-0 spec yet. That tool is execution package 10, with an EVAL-5 criterion. Until it exists,
  criterion 7 is closed for the contract and schema only.
- **Open API risk.**
  - If grids cannot carry the UDAs on the test model (T2), the grid route is closed (exit `3`). A
    new ADR then decides between GUID-only tracking through the journal and engineer-manual grids.
    No untagged object is ever built.
  - If T7 fails, rotated grids are `engineer manual`. If T8 fails, one-direction grids are.

## Rejected alternatives

- **Levels as a top-level `levels[]` array or their own Tekla object.** Tekla has no level object,
  and 2026 binds to grid elevations. A separate array would need a second link back to its grid.
- **Grid as Tekla strings** (`coordinate_x: "0 2*6000"`, as in `grid-systems.json` `tekla_grid`).
  Opaque to validation, and it cannot carry provenance per line. It would also fix the
  relative/absolute reading in the spec instead of in one CLI function.
- **Spacings in the spec.** Spacing errors add up along the axis (Q7 chose absolute positions).
- **Line positions in global X/Y for rotated grids** (each line as a global point and direction). It
  needs two numbers and a direction per line, can describe lines that are not parallel, and must
  then be checked for parallelism. One frame per grid with one number per line is what a Tekla grid
  is.
- **A rotation field written to the `Grid` object.** No such member is documented on `Grid` or
  `GridBase` in 2026.0.3 (member list read on 2026-11-11) or 2024.0.4.
- **Grids inside lot 1 with the first members.** Grid errors would then be rolled back together
  with members, and members would be built before the grid is checked.
- **A `members[]` variant (`oneOf` start/end or points).** It changes the existing member shape, the
  C# member reader and every consumer of it. A separate array is additive.
- **A radius-based curved beam** (`Beam` + radius, the UI's Curved beam command). There is no public
  API: `Beam.Radius` is an internal field. Tekla's own Curved beam component builds a 3-point
  polybeam with an arc chamfer.
- **New subcommands** (`build-grid`, `rollback-grid`). They would add write subcommands for the
  guard hook to classify. The same safety rules apply inside `build`/`update`/`rollback`.
- **Excluding grids from tagging and rollback.** It would leave model objects the harness created
  but cannot find or remove (principle 4).

## Execution packages

In dependency order. ADR-0016 adds its own part to packages P15-3, P15-5, P15-6, P15-7, P15-8 and P15-9 (one package per
concern for both ADRs, with one `SPEC_RULES_VERSION` bump), and adds packages of its own. No `dotnet`
is installed in WSL, so C# packages are done when the windows-latest CI job (`dotnet test
tekla/TeklaCore.Tests`) is green.

1. **P15-1 Docs pin to Tekla 2026** (Q1). One concern: the version pin.
   - Files:
     - a new dated amendment to `docs/decisions/0009-tekla-dotnet-layout.md` (its accepted text is
       not edited);
     - `docs/tekla-cli-contract.md` § "Build and invocation";
     - `tekla/README.md`;
     - `tekla/api-notes.md`: the version matrix "company" column, the start-here checklist, and the
       wording of To verify #1, #3 and #4;
     - `docs/roadmap.md` ("Open before later steps", Tekla version);
     - `CHANGELOG.md`;
     - a dated note in `docs/decisions/0007-tekla-cli-failure-backup-and-tags.md`, whose line 37
       says the macro route must pass "on the 2024 test model".
   - **NuGet.** No project file references `Tekla.Structures.*` yet (`TeklaAdapter` does not exist),
     so the NuGet pin is documentary for now. The package states that the future
     `TeklaAdapter.csproj` references `Tekla.Structures.Model` and `Tekla.Structures.Catalogs`
     2026.0.3.
   - The package records the 2026 deltas already known (Model package `netstandard2.0` only, x64-only
     DLLs) and leaves the first Windows build to confirm that the `net48` x64 executable consumes it.
   - Done when `grep -n "2024.0.4" tekla/README.md docs/tekla-cli-contract.md` prints no pin line
     (history notes only) and `grep -n "2026.0.3" docs/decisions/0009-tekla-dotnet-layout.md` prints
     the new amendment.
2. **P15-2 api-notes To verify and facts.** Add T1–T10 and the F table (F8 corrected) to
   `tekla/api-notes.md`, and add the contract's open-question line. Done when
   `grep -n "T10\." tekla/api-notes.md` prints one line.
3. **P15-3 Spec schema, examples, CHANGELOG.**
   - Files:
     - `schemas/spec.schema.json` (ADR-0016's composed schema, since both are accepted);
     - `schemas/examples/spec-lot0-grid.example.json`, `spec-lot0-rotated-grid.example.json` and
       `spec-poly-members.example.json`;
     - `schemas/examples/spec.example.json`, replaced by draft §3.4 (OQ-B);
     - `CHANGELOG.md`;
     - `tests/test_schemas.py` (the schema-level reject set of the draft).
   - Done when `uv run pytest tests/test_schemas.py` passes and
     `uv run harness validate spec schemas/examples/spec-lot0-rotated-grid.example.json` exits `0`.
4. **P15-4 Lot 0 in the journal and the project state.**
   - `lot ≥ 0`, and the optional header object `override` (`flag`, `question_id`, `parts[]` with
     GUID and before and after reference points and level names) for `--allow-untagged-shift`
     (decision 10, OQ-A).
   - Files: `schemas/run-journal.schema.json`, `schemas/project-state.schema.json`, `CHANGELOG.md`,
     `tekla/TeklaCore/RunJournalJson.cs`, `tekla/TeklaCore.Tests/RunJournalJsonTests.cs` and
     `tests/test_schemas.py`.
   - Done when `uv run pytest tests/test_schemas.py` passes and `dotnet test tekla/TeklaCore.Tests`
     passes on the windows-latest CI job.
5. **P15-5 `check_spec` rules and `SPEC_RULES_VERSION`.**
   - Rules (a)–(h), (r) and (s), each with a regression test, and one bump of `SPEC_RULES_VERSION` in
     `src/tekla_harness/receipt.py`.
   - Files: `src/tekla_harness/schemas.py`, `src/tekla_harness/receipt.py`, `tests/test_schemas.py`,
     `tests/test_receipt.py`.
   - Done when `uv run pytest tests/test_schemas.py tests/test_receipt.py` passes and
     `uv run harness validate spec` exits `0` on every example, `spec.example.json` included, and a
     reject test shows today's `spec.example.json` failing rule (f). Needs package 3.
6. **P15-6 Closed-world C# `SpecLoader`** (decision 7).
   - Unknown keys and enum values refused at every nested level; `grids` and `poly_members` read;
     lot 0 accepted; `MinimumRulesVersion` = the new `SPEC_RULES_VERSION`.
   - Files: `tekla/TeklaCore/SpecLoader.cs`, `tekla/TeklaCore/LotSpec.cs`,
     `tekla/TeklaCore.Tests/SpecLoaderTests.cs`.
   - Done when `dotnet test tekla/TeklaCore.Tests` passes on the windows-latest CI job. Needs package 5, because the rules version lands in Python
     first.
7. **P15-7 Snapshot kinds and "differs"** ("Amends ADR-0012").
   - The kind mapping table (`brace` … `other` → `beam`), the `grid` and `polybeam` kinds and their
     "differs", and grid enumeration as a lookup source.
   - Files: `tekla/TeklaCore/ModelSnapshot.cs`, `tekla/TeklaCore/ResumePlanner.cs`,
     `tekla/TeklaCore.Tests/ResumePlannerTests.cs`.
   - Done when `dotnet test tekla/TeklaCore.Tests` passes on the windows-latest CI job. Needs package
     6.
8. **P15-8 Contract text.** Apply draft §4 to `docs/tekla-cli-contract.md`, rule 9 with the
   `--allow-untagged-shift` flag. The commit carries the `Safety:` line of this ADR's header. Done
   when `uv run pytest tests/test_guard_hook.py` passes (no read subcommand added),
   `grep -c "^7\. Read the spec closed-world\|^8\. Lot 0 holds\|^9\. Lot 0 after\|^10\. Tekla 2026" docs/tekla-cli-contract.md`
   prints 4 and `grep -c "allow-untagged-shift" docs/tekla-cli-contract.md` prints 1. Needs package
   1, which edits the same file.
9. **P15-9 Planner skill, workflow and agents.**
   - Lot 0 in step III, the lot-0 gate 4, untagged grids in the lot report, and the R1 gap closed.
   - `builder.md`: pass `--allow-untagged-shift <question_id>` only when the brief cites that
     engineer answer; `reporter.md`: show the flagged run's before and after part list.
   - Files: `.claude/skills/tekla-conversion-plan/SKILL.md`, `docs/workflow.md`,
     `.claude/agents/builder.md`, `verifier.md` and `reporter.md`.
   - Follows `writing-for-agents`, and needs the engineer's approval (principle 7).
   - Done when `uv run pytest tests/test_agent_definitions.py` passes.
10. **P15-10 Lot-0 spec producer** (review M-9).
    - A harness command writes `lots/0/spec.json` from `grid-systems.json` plus the active engineer
      answers: units, axis assignment, origin and rotation, and levels.
    - Grid-system spacings are in drawing units and never `high`. The producer converts them to
      absolute mm with a `derived` chain to the units answer and the frame answer.
    - It refuses answers that are not active or not `answered_by_role: engineer`.
    - Files: `src/tekla_harness/lot0_spec.py` (new), `src/tekla_harness/cli.py`,
      `tests/test_lot0_spec.py` (new).
    - EVAL-5 criterion: on every corpus set with a selected grid system, the lot-0 spec validates, and
      every level `z`, `origin` and `rotation_deg` traces to an engineer answer.
    - Done when `uv run pytest tests/test_lot0_spec.py` passes. Needs package 5.
11. **P15-11 ADR-0012 amendment note.** Unblocked: the engineer accepted both ADRs on 2026-11-11.
    Add a dated "Amendment" section that points to "Amends ADR-0012" here and in ADR-0016. Done when
    `grep -n "Amendment" docs/decisions/0012-run-journal-and-resume-planner.md` prints it.
