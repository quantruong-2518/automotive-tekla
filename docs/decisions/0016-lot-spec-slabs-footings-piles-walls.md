# 0016. Lot spec: slabs, footings, pile caps, piles and walls

- Status: Accepted (engineer, 2026-11-11)
- Date: 2026-11-10; revised 2026-11-11 after an independent review
  (`projects/_evals/wave4-2026-11-10/REVIEW-ADR-0015-0016.md`) and the engineer's answers Q1–Q17
  and OQ-A–OQ-E
- Decided by: orchestrator design (tool wave 4, EVAL-4 ranked fix 8); engineer decisions marked
  "(engineer, 2026-11-11)"; accepted by the engineer together with ADR-0015
- Safety: only if To verify C7 fails and C8 passes, `build` may delete the tagged opening cutter it
  inserted in the same invocation: that GUID only, only while it carries this run's tags, and
  journalled (decision 6, OQ-D). This is the one exception to contract rule 5; no other delete
  inside `build` or `update` is allowed. Newly blocked: steel members refuse (exit `5`) until C2
  fills their Position rows (decision 2, OQ-C). In practice nothing changes, since every write route
  already waits for T4. The commit that adds contract rules 11 and 12 carries this line.
- Amends: [ADR-0012](0012-run-journal-and-resume-planner.md) §2, §3, §6, §7 and §8, and extends
  [ADR-0015](0015-lot-spec-grids-levels-nonlinear-members.md) (section "Amends ADR-0012" below)

## Context

EVAL-4 failed criterion 7 because most of each RC building had no build-side route. Both J2 judges
counted this as a Critical no-route gap:
- h-j2: "Linear members only … The slabs, pile caps and footings, piles and walls of 264, 271 and
  278 are blocked by tool, with `engineer manual` the only path";
- r-j2 gap 1: "No slab, footing, pile cap, pile, wall or rebar object … that is most of three
  buildings".

The EVAL-4 gate-1 plan (`eval4-h/02-plan.md` §2) shows what these objects look like in a real set:
- 264: piled foundation with caps (F-142), slabs 120 mm and a 100 mm roof (F-144);
- 271: pad footings bm-1 … bm-7 (F-158), slab 100 mm (F-145);
- 278: walls of unclear position (F-149), precast RC piles 20x20 cm with caps and ground beams
  (F-150).

On 2026-11-10 the engineer decided that these objects go into the lot spec and the `tekla-cli`
contract in tool wave 4. Reinforcement stays out of scope (`docs/roadmap.md`, "Open before later
steps"). This ADR is the design only: the code that writes to Tekla waits for the test-model checks
below.

This ADR builds on ADR-0015, and the two were accepted together. These parts of ADR-0015
apply unchanged unless stated below:
- provenance per value, the tags and the closed-world reader;
- the snapshot kinds and the 0.1 mm "differs" rule;
- `check_spec` rules (a)–(h), (r) and (s);
- lot 0 and its 2026 level-binding rule.

**Tekla target: 2026** (engineer, 2026-11-11, Q1). The facts below come from PKG26 first. PKG24 is
cited only where it shows that nothing changed.

The Open API facts used below come from the docs and have not been run on a model. Each one has a
K-number, and the sources are in [`0016-schema-draft.md`](0016-schema-draft.md) § "API facts".
- **No pile object.** `ModelObjectEnum`, `Beam.BeamTypeEnum`, `PolyBeam.PolyBeamTypeEnum` and
  `CatalogObjectTypeEnum` have no pile value (K5).
- **Footings.** Footings are `Beam` types: `PAD_FOOTING` and `STRIP_FOOTING`. They are "valid only
  if the material type of the beam is concrete" (K3).
- **Pad footing example.** Trimble's own Open API exercise shows a pad footing with Position Plane
  `MIDDLE`, Depth `MIDDLE`, Rotation `FRONT`, end 500 mm below start (K12). The page shows no
  `BeamTypeEnum.PAD_FOOTING` constructor, because the code is in a download. That pad footings are
  `Beam(PAD_FOOTING)` rests on XML24's `Beam(BeamTypeEnum)` constructor and the K3 remark (the
  member is unchanged in 2026.0.3).
- **Walls.** A concrete wall is a panel: `BeamTypeEnum.PANEL`, profile "thickness × height of the
  wall" (K3, K11).
- **Slabs.** A slab is a `ContourPlate`. Its read-only `Type` becomes `SLAB` when the material is
  concrete. Its profile is its thickness. Its depth position is "always perpendicular to the work
  plane" (K1, K2, K8).
- **Openings.**
  - An opening is a `BooleanPart` cut. Its operative part has class `BooleanOperativeClassName`, and
    the documented recipe inserts the operative part, inserts the cut, then deletes the operative
    part (K13).
  - `BooleanPart.Modify` "will actually call modify for the operative part member". Changes of the
    cut go through `OperativePart`, the copy "with the same identifier as the boolean part" (K13).
- **Tags on openings.** `BooleanPart` inherits `SetUserProperty` from `ModelObject` (K14). But no
  `CatalogObjectTypeEnum` value covers booleans (K17), and Trimble's `objects.inp` parser lists no
  boolean section (ADR-0015 F14).
- **2024 → 2026.** On every class used here the only API difference is the 2026 level binding:
  `ContourPlate.LevelName/LevelOffset`, and on beams `Start/EndLevelName/Offset` (K20).

## Decision

0. **Tekla target 2026** (engineer, 2026-11-11, Q1), as ADR-0015 decision 0: the K facts and the
   C items target 2026.0.x, and the pins move in ADR-0015 package P15-1.
1. **Four routes, three new arrays, no new subcommand.**
   - `members[]` gains four types: `pad_footing`, `pile_cap`, `pile` and `strip_footing`. Each is a
     concrete `Beam` with a profile and two points, so it has the member shape.
   - `slabs[]`: horizontal concrete `ContourPlate`s.
   - `polygonal_caps[]`: pile caps whose plan is a polygon, as `ContourPlate`s (decision 3, Q16).
   - `walls[]`: straight concrete panels (`Beam` of type `PANEL`) (engineer, 2026-11-11, Q9).
     Gable and stepped walls stay `engineer manual`.
   - Openings are nested in their slab or wall as `openings[]`. Each opening is one `BooleanPart` cut
     with its own `spec_id` (engineer, 2026-11-11, Q10).
   - `$id` stays 0.1, and the change gets a CHANGELOG entry. The schema is the draft, composed on top
     of ADR-0015's.
2. **Reference lines: the spec carries the drawing's; the CLI maps them to Tekla's native handles**
   (engineer, 2026-11-11, Q8: Tekla-native handles per concrete kind, concrete beams and columns
   included, signs proven on a test model first; no company standard given).
   - The spec never holds Position enums. Each kind's reference is the one the drawing gives, and
     the CLI uses it as the Tekla reference line or contour **as it is**, with no shift arithmetic:

     | Kind (concrete material) | Spec reference = Tekla reference | Solid lies |
     |---|---|---|
     | `column` | bottom centre → top centre | centred on the line |
     | `beam`, `brace`, `purlin`, `girt`, `rafter`, `other` (ground beams included) | top centre line | below the line, centred across it |
     | `pad_footing`, `pile_cap` | top centre → bottom centre | centred on the line |
     | `pile` | head (cut-off level) → toe | centred on the line |
     | `strip_footing` | top centre line | below the line, centred across it |
     | wall | base centre line | above the line, centred on it across the thickness |
     | slab, polygonal cap | top-face outline | below the face |

   - **Position values.** The CLI keeps one table, keyed by (spec `type` × material type), that sets
     Plane, Depth, Rotation and the three offsets so the solid lies as stated above and below. The
     key is the spec `type`, not the Tekla type, because a steel beam and a steel brace are both
     Tekla `BEAM` but lie differently. The values come
     from To verify C2 and are not guessed here. K12 documents `MIDDLE`/`MIDDLE`/`FRONT` for a pad
     footing, and C2 confirms that one too. Until a kind's values are in the table, the CLI refuses
     that kind (exit `5`).
   - "Concrete" means a catalog material of type `MATERIAL_CONCRETE` (K18), read by `validate`.
   - **Steel members** (engineer, 2026-11-11, OQ-C; Q8 covered concrete only, review M-5):

     | Kind (steel material) | Spec reference = Tekla reference | Solid lies |
     |---|---|---|
     | `beam` | top-of-steel centre line | below the line, centred across it |
     | `column` | centroid axis, bottom → top | centred on the line |
     | `brace` | centroid axis | centred on the line |
     | `purlin`, `girt`, `rafter`, `other` | top-of-steel centre line (reading) | below the line, centred across it |

     - The answer names beams, columns and braces. The last row is a reading, not an answer: those
       kinds are Tekla `BEAM` like `beam`, so they follow the beam rule. The gate-2 modelling
       approach states it, so the engineer sees it before any build.
     - Poly members take the row of their `type`. That row sets their Position, which is not
       compared (ADR-0015 decision 9).
     - Position values for these rows are fixed after C2, like the concrete rows. Until a row is in
       the table, the CLI refuses that kind (exit `5`). EVAL-5 build checks for steel members wait
       for C2, not for an answer.
   - A member's `rotation_deg` is applied as it is for other members.
   - On a `ContourPlate` only Depth and DepthOffset shape the solid, so only those two are set and
     compared (review Minor 12). C2 confirms it.
   - `CastUnitType` is always `CAST_IN_PLACE`, and "differs" compares it (engineer, 2026-11-11, Q13).
     A per-item field comes later with precast. Pour phase keeps its default.
3. **Footings, pile caps and piles.**

   | Spec | API object | Tekla Name | `start` → `end` or outline | `profile` or `thickness` | Usual drawing source |
   |---|---|---|---|---|---|
   | `members` `pad_footing` | `Beam(PAD_FOOTING)` | from the spec, never `PILE`/`PILE_CAP` | top centre → bottom centre, vertical | plan size `B*L`; with `rotation_deg`, as for a rectangular column | foundation plan (position, mark), footing schedule or detail (B, L, H), top level (engineer answer) |
   | `members` `pile_cap` | `Beam(PAD_FOOTING)` | `PILE_CAP` | top centre → bottom centre, vertical | `B*L`, or a round section | pile layout or foundation plan, pile cap detail |
   | `polygonal_caps` | `ContourPlate` (type `SLAB`) | `PILE_CAP` | top-face outline, counter-clockwise from +Z | `thickness` (cap depth) | pile cap detail (3-pile, hexagonal) |
   | `members` `pile` | `Beam(COLUMN)` | `PILE` | head → toe, vertical | e.g. `200*200`, or a round section | pile layout plan, pile section, pile notes ("L=18m") |
   | `members` `strip_footing` | `Beam(STRIP_FOOTING)` | from the spec | top centre line, horizontal | `W*H` | foundation plan, strip footing section |

   - **Piles** (engineer, 2026-11-11, Q15): `Beam` `COLUMN`, head to toe. The CLI writes Name `PILE`.
     `class` is required, so reports tell piles from columns. To verify C14 checks that Tekla accepts
     a column with its start above its end.
   - **Pile toe** (engineer, 2026-11-11, Q14) comes **from the drawing**, for example from the pile
     length "L=18m" with the head. It carries provenance and confidence like any drawing value. It is
     the one carve-out from Q5's elevation rule (rule (p)). The pile head stays under Q5.
     - A low-confidence toe needs a question (rule (q)).
     - A missing toe is a rule of the spec-writing tool, not of `check_spec`: `end` is required, so
       the tool writes no pile item and raises a question instead.
     - The engineer did not take the reviewer's default (engineer answer always).
   - **Polygonal pile caps** (engineer, 2026-11-11, Q16: in scope, built as `ContourPlate`). The
     reviewer's default (`engineer manual`) was not taken.
     - **How they are told apart from slabs.** Tekla gives both `ContourPlate.Type` `SLAB`.
       - The CLI writes Name `PILE_CAP`, and `class` is required (the project's pile-cap class, set
         at gate 2).
       - Name `PILE_CAP` is reserved: no slab, wall, column, beam or footing may carry it, and the
         schema enforces it.
       - Reports and drawing filters select pile caps by Name, together with the class.
       - Rectangular and round caps (`members` `pile_cap`) get the same Name, so one filter finds
         every cap (engineer, 2026-11-11, OQ-E: Name `PILE_CAP` on all pile caps, rectangular,
         round and polygonal; the class is chosen at gate 2; the name is reserved).
       - The snapshot matches a polygonal cap only to a `slab`-kind object named `PILE_CAP`, and a
         slab never to one (decision 8). No fourth UDA is added, so contract rule 4 stays as it is.
     - **What they lose** compared with a `PAD_FOOTING` cap:
       - the Tekla part type `PAD_FOOTING` and the catalog type `CONCRETE_PAD_FOOTING`, so company
         UDA definitions, templates, numbering series and report or drawing filters keyed on the
         footing type do not see them;
       - Tekla's footing reinforcement components later (rebar is out of scope now);
       - the footing IFC entity: they export as a slab unless Tekla offers a per-part IFC entity
         override, which is To verify C16.

       The spec, the lot report and the verifier still list them as pile caps.
   - **Ground beams** stay `beam` members. Under decision 2 they lie on their top centre line.
   - **Polyline strip footings** are split into straight segments. `PolyBeam(STRIP_FOOTING)` exists
     (K4), but using it would change ADR-0015's rule that every polybeam is `BEAM` and its type is
     not compared.
   - Which profile number lies along which axis is To verify C1. The spec stores the string the
     company's catalog uses.
4. **Slab shape** (`slabs[]`).
   - Fields: `spec_id`, `mark`, `material`, `thickness`, `outline[]`, `openings[]`, `name`, `class`,
     `question_ids`, `notes`.
   - `outline` is the slab's **top face**: ≥ 3 ADR-0015 `poly_point`s (x, y, z, `none`|`arc_point`,
     provenance, confidence), at one Z, counter-clockwise seen from +Z. `thickness` is a sourced
     number in mm.
   - The CLI builds the contour on the top face, with the Depth that puts the thickness below it
     (decision 2, C2). It composes the profile from the thickness in one function. The exact string
     is To verify C1 (K1's example uses `PL200`).
   - After `Insert`, `Type` must read `SLAB` (K2): a concrete material makes it one. Any other value is
     an API failure (exit `4`).
   - Usual sources:
     - outline: the floor framing plan (slab panel edges, grid);
     - Z: the storey level (engineer answer, Q5) and any step shown on the plan;
     - thickness: the slab note or section ("S=120", F-144) or the general notes.
   - Sloped slabs are out of scope.
   - A polygonal cap (`polygonal_caps[]`) has the same outline and thickness rules, a required
     `class`, no `openings` and no `name` key (the CLI writes `PILE_CAP`).
5. **Wall shape** (`walls[]`).
   - Fields: `spec_id`, `mark`, `material`, `start`, `end`, `thickness`, `height`, `openings[]`,
     `name`, `class`, `question_ids`, `notes`.
   - `start`–`end` is the **base centre line**, horizontal. `height` is measured up from it.
   - The CLI builds `Beam(PANEL)` on the base line, with the Position that puts the wall above it and
     centres it across the thickness (decision 2, C2). It composes the profile from thickness and
     height in the order the UI states ("thickness × height", K11), checked by C1.
   - Usual sources:
     - line and thickness: the floor plan or wall layout ("vách");
     - base and height: storey levels (engineer answer) and the slab or beam above.
   - Curved, polyline and non-rectangular walls (gables, steps) are out of scope (Q9).
6. **Openings** (`slabs[].openings[]`, `walls[].openings[]`). In scope as through-cuts (Q10).
   - **Gate.** The route is **blocked until To verify C4 (cut tags persist) and either C7 (an
     operative part that is never inserted works) or C8 (the tagged-cutter fallback below works)
     pass on the test model**. Resume also needs C5 (cut read-back), and rollback's count check needs
     C6 (cascade delete). Until then an opening item refuses (exit `5`) before anything is written.
   - **Fields.**
     - `spec_id` is at most 60 characters, so that the reserved cutter tag fits the 64 that #24
       verifies. Other fields: `mark`, `question_ids`, `notes`.
     - `outline[]` holds ≥ 3 `poly_point`s, each with provenance and confidence, and corners only:
       `arc_point` is refused (review Minor 11).
     - A slab opening lies on the slab's top face. A wall opening lies in the wall's vertical centre
       plane.
     - Each outline is counter-clockwise about its plane's normal: +Z for a slab, Z × (end − start)
       for a wall.
   - **The composed cutter.** The CLI derives it from the opening and its parent. It is what is
     built, compared and updated:
     - **Slab opening:** an operative `ContourPlate` on the opening outline. It reaches from 50 mm
       above the top face to 50 mm below the bottom face (thickness + 100), with the parent's
       material.
     - **Rectangular wall opening** (four corners, two edges horizontal and two vertical within
       0.1 mm; doors and windows, the corpus case): an operative `Beam` whose axis runs along the wall
       normal through the opening's centre, 50 mm beyond each face (thickness + 100). Its profile is
       the opening's width × height (axis order C1), with no work-plane change (review M-6, To verify
       C10).
     - **Any other wall opening:** an operative `ContourPlate` in a work plane set to the wall's
       centre plane. It is blocked until C2 (wall cutter) and C12 (does `SetCurrentTransformationPlane`
       change the engineer's UI work plane, and what state does a crash leave) pass.
     - **Flush edges:** an opening edge within 1 mm of a parent edge, such as a door at the wall base,
       is pushed 50 mm outward in the composed cutter, so that no face coincides (To verify C11).
   - **Build**, right after the parent and in the same command:
     1. The CLI makes the operative part in memory: class `BooleanOperativeClassName`, the composed
        geometry.
     2. It inserts a `BooleanPart` with `Father` = the parent, type `BOOLEAN_CUT`, and
        `SetOperativePart` with the never-inserted part (C7). No transient object is created.
     3. It tags the cut, checks each tag write's result and reads the tags back (C4).
   - **Fallback, only if C7 fails and C8 passes** (engineer, 2026-11-11, Q11: no untagged exception).
     - The operative part is inserted and tagged before the cut: `LOT`, `RUN_ID` and the **reserved**
       `SPEC_ID` `<opening spec_id>~CUT`. `~` is outside the `spec_id` pattern, so it can never
       collide with a spec item.
     - It is journalled with role `cutter` (decision 10).
     - After the cut's `Insert` the CLI deletes it, as the documented recipe does (K13) (engineer,
       2026-11-11, OQ-D). That is the one delete inside `build`, an exception to contract rule 5. It
       removes only the GUID this invocation inserted, only while it carries this run's tags, and
       the journal records it (state `deleted`).
     - A cutter that a stopped run left behind is found by the normal UDA lookups like any tagged
       object.
   - Nesting makes "same lot, same spec as the parent" structural. No reference ever crosses lots.
   - Usual sources: the slab plan (hatched or crossed opening with dimensions, stair, shaft) and the
     wall elevation or plan (door, window).
7. **Tags and lookups.**
   - Parts get `LOT`, `RUN_ID` and `SPEC_ID` as members do.
   - `info` checks the UDA definitions for every (Tekla type × material type) pair the spec can
     produce (review Minor 8), not a fixed list:
     - the concrete part types `CONCRETE_BEAM`, `CONCRETE_COLUMN`, `CONCRETE_PAD_FOOTING`,
       `CONCRETE_STRIP_FOOTING`, `CONCRETE_PANEL` and `CONCRETE_SLAB` (K17);
     - the steel types of members and poly members (names taken from the CAT26 enumeration by the
       execution package);
     - `GRID` (ADR-0015).

     The repo's `objects.inp` task lists the matching sections, whose names differ from the enum
     names (`pad_footing`, `concrete_slab`, … in Trimble's parser).
   - A cut is tagged too: `SetUserProperty` is inherited (K14). No catalog type covers booleans, so
     `info` cannot check the definition ahead. The CLI therefore checks every tag write's result and
     reads the tag back. If the cut tags do not persist on the test model (C4), the opening route
     stays closed and a new ADR decides. No untagged object is ever built.
   - The CLI finds cuts by enumerating each found parent's `GetBooleans()` (K15) and reading their
     tags, with no UDA filter. This is the approach ADR-0015 takes for grids.
   - A tagged cut whose parent is gone can be reached only by its journal GUID. Whether that case can
     happen depends on C6.
8. **Kinds and "differs"** (amends ADR-0012 §6–7; this table supersedes ADR-0015's and covers
   every kind).

   | Spec array / `type` | Tekla object | Snapshot kind | Lookup sources | "Differs" beyond ADR-0012 §7 (points ≤ 0.1 mm, profile, material, rotation, class) |
   |---|---|---|---|---|
   | `members` `column` | `Beam` COLUMN | `column` | UDA lookups + journal GUIDs | Position = table (concrete and steel); concrete: `CastUnitType`; Name `PILE` is a conflict |
   | `members` `beam`, `brace`, `purlin`, `girt`, `rafter`, `other` | `Beam` BEAM | `beam` | UDA lookups + journal GUIDs | Position = table (concrete and steel); concrete: `CastUnitType` |
   | `members` `pile` | `Beam` COLUMN | `column` | UDA lookups + journal GUIDs | Position, `CastUnitType`; Name must be `PILE` |
   | `members` `pad_footing` | `Beam` PAD_FOOTING | `pad_footing` | UDA lookups + journal GUIDs | Position, `CastUnitType`; Name `PILE_CAP` is a conflict |
   | `members` `pile_cap` | `Beam` PAD_FOOTING | `pad_footing` | UDA lookups + journal GUIDs | Position, `CastUnitType`; Name must be `PILE_CAP` |
   | `members` `strip_footing` | `Beam` STRIP_FOOTING | `strip_footing` | UDA lookups + journal GUIDs | Position, `CastUnitType` |
   | `poly_members` | `PolyBeam` BEAM | `polybeam` | ADR-0015 | ADR-0015 decision 9 |
   | `grids` | `Grid` | `grid` | ADR-0015 (enumeration) | ADR-0015 decision 9 |
   | `walls` | `Beam` PANEL | `panel` | UDA lookups + journal GUIDs | reference line = base line (each end ≤ 0.1 mm); profile = the composed string; Position; `CastUnitType` |
   | `slabs` | `ContourPlate`, `Type` SLAB | `slab` | UDA lookups (#7 covers `ContourPlate`) + journal GUIDs | contour: the same count and order, each point ≤ 0.1 mm, the same chamfers (C3); profile = the composed string; Depth and DepthOffset only; `CastUnitType`; Name `PILE_CAP` is a conflict |
   | `polygonal_caps` | `ContourPlate`, `Type` SLAB | `slab` | UDA lookups + journal GUIDs | as for slabs; Name must be `PILE_CAP` |
   | openings | `BooleanPart` BOOLEAN_CUT | `cut` | each found parent's `GetBooleans()`, tags read + journal GUIDs | the father is the parent's object; the operative part's contour or line (≤ 0.1 mm), profile and Position equal the composed cutter |
   | cutter (fallback only) | operative part, `SPEC_ID` `<id>~CUT` | `cutter` | UDA lookups + journal GUIDs (role `cutter`) | none: a present cutter on resume is the conflict `cutter_left` |

   - The harness kind is not kept in Tekla: a `pile` reads back as `column`, a `pile_cap` as
     `pad_footing`, a polygonal cap as `slab`. A spec item therefore matches the Tekla kind its array
     and `type` map to, never its own name.
   - For the shared kinds, the reserved Names `PILE` and `PILE_CAP` are part of the match: a mismatch
     is a conflict (exit `1`), not a reported name difference. Every other name difference is still
     reported only (ADR-0012 §7).
   - The Position, cast unit and profile checks close a blind spot. Without them, a part with the
     wrong Depth keeps every reference point within 0.1 mm and still sits one thickness off.
   - Whether Tekla returns a contour in the order and winding it was given is To verify C3. If it does
     not, the comparison changes, not the schema.
   - The verifier compares the `export` CSV:
     - per slab, polygonal cap and opening, one row per contour point (`SPEC_ID`, index, x, y, z,
       chamfer);
     - per concrete part, its profile, Position values, cast unit type and Name.

     The verifier checks the Position values against the contract's table (rule 11), independent
     of the CLI. IFC is a count check only for slabs, caps, walls and cuts.
9. **Validation** (Python stays the only full validator, ADR-0010). The schema already enforces:
   - reserved names: `PILE` only on piles and `PILE_CAP` only on pile caps, nowhere else;
   - `class` required on piles, pile caps and polygonal caps;
   - corners only in openings, and opening `spec_id` ≤ 60 characters.

   New `check_spec` rules, each with a regression test:
   - **(i)** extends (a): `spec_id` unique across `members`, `poly_members`, `grids`, `slabs`,
     `polygonal_caps`, `walls` and every nested opening.
   - **(j)** `pad_footing`, `pile_cap` and `pile`: start at least 1 mm above end, and start and end
     within 0.1 mm in plan (vertical).
   - **(k)** `strip_footing`: start and end within 0.1 mm in Z (horizontal).
   - **(l)** Outline rules for slabs, polygonal caps and openings:
     - consecutive points (cyclic) ≥ 1 mm apart, and no repeated point;
     - a simple polygon: no two non-adjacent edges meet ("contours must not have loops", ADR-0015
       F3);
     - never two `arc_point`s adjacent (cyclic), and each `arc_point` ≥ 1 mm from the chord of its
       neighbours (ADR-0015 F17, F18);
     - counter-clockwise about the plane's normal (decision 6), with area ≥ 1 mm².

     The point count against `Contour.MAX_CONTOUR_POINTS` is a `validate` check in the CLI, since its
     value is To verify C15.
   - **(m)** Slab and polygonal cap: every outline Z within 0.1 mm of the first. Every slab opening
     point at the same Z (≤ 0.1 mm) and inside or on the slab outline (1 mm tolerance). A slab with an
     `arc_point` has no openings in this ADR, since the inside test uses the corner polygon.
   - **(n)** Wall: start and end Z within 0.1 mm, plan length ≥ 1 mm. Every opening point within
     0.1 mm of the vertical plane through the base line, and inside the wall rectangle (start to end,
     base to base + height) with 1 mm tolerance.
   - **(o)** The openings of one parent do not overlap: no edge crossing, and no corner inside
     another opening.
   - **(p)** **Elevation provenance** (Q5, with Q14's carve-out). ADR-0015 rule (f) applies to these
     paths too:
     - every point of a slab's or a polygonal cap's `outline`;
     - a wall's `start` and `end`;
     - the `start` (top, or pile head) of `pad_footing`, `pile_cap` and `pile`;
     - the `end` (bottom) of `pad_footing` and `pile_cap`, derived from the top's answer and the
       depth (Q5, "every elevation");
     - `start` and `end` of `strip_footing`.

     A pile's `end` (toe) is exempt: drawing provenance is accepted (Q14). Since OQ-B, ADR-0015 rule
     (f) covers every member point anyway; these paths are named so that each kind's rule is in one
     place, and they are checked once.
   - **(q)** extends (h): the low-confidence walk covers `slabs`, `polygonal_caps`, `walls` and each
     opening's `outline`. A low value inside an opening needs a question in that opening's
     `question_ids`. Every listed id must be in `open_questions`.

   Further:
   - `validate` (CLI, catalog) checks that the material type is `MATERIAL_CONCRETE` (K18) for every
     kind of this ADR. It also checks every composed profile, cutters included.
   - `SPEC_RULES_VERSION` is bumped once, for ADR-0015 and this ADR together.
   - The receipt needs no new field: its SHA-256 covers every byte.
   - The closed-world reader (ADR-0015 decision 7) adds `slabs`, `polygonal_caps`, `walls` and
     `openings` to its key lists, the four member types to its `type` enum, and the reserved-name and
     corners-only rules.
   - **Checked so far** (2026-11-11): the composed schema with the current `check_spec` on all six
     examples (ADR-0015's updated `spec.example.json` included) and a reject set
     (`0016-schema-draft.md`, top). Rules (i)–(q) were not run, because they do not exist yet. A
     scratch probe of rules (j), (k), (p) and (q), and of ADR-0015 rule (f) with the member paths,
     passes on the examples.
10. **Journal, resume, update and rollback.**
    - **Resume.** Each opening is its own spec item (ADR-0012 §8). It is skipped, retagged, built or
      in conflict like a member, and it is built only after its parent is present and matches.
    - **Cutter journal entries** (fallback only, if C7 fails).
      - An object entry gains `role`: `part` (the default, also when omitted) or `cutter`.
      - Within one invocation, entries are unique per (`spec_id`, `role`), not per `spec_id`.
      - A cutter entry goes `inserting` → `inserted` → `tagged` → `deleted`. Each step is written
        before the next model call, as ADR-0012 §3 requires.
      - A present object tagged `<id>~CUT` with this run's tags is the conflict `cutter_left` on
        resume (exit `1`), and `build` never deletes it.
      - If C7 passes, none of this is built, and the journal schema stays as it is.
    - **Update** (engineer, 2026-11-11, Q12: modify in place through `OperativePart`).
      - An opening is updated whenever its composed cutter changes. That covers its outline, and also
        its parent's thickness, top face, base line or height (review Minor 10).
      - The CLI selects the cut, sets `OperativePart`'s contour or line, profile and Position to the
        new composed cutter, and calls `Modify`. XML24 says that call modifies the operative part
        (the member is unchanged in 2026.0.3). The GUID is kept, and the before-image is journalled
        as ADR-0007 requires.
      - This is To verify C9. Until C9 passes, an `update` that changes an opening refuses (exit `5`).
      - If C9 fails, delete-and-replace comes back only with the engineer's approval of a delete
        inside `update`, as a new decision.
    - **Rollback** (Q11).
      - `rollback` deletes a run's cuts before their parents. Whether deleting a parent also deletes
        its cuts is C6, and the count check must allow for it.
      - It deletes leftover cutters **only** when their GUID is in this run's journal **and** they
        carry this run's tags. A cutter with this run's tags but no journal entry is listed for the
        engineer and not deleted.
    - **2026.** ADR-0015 decision 11 extends to `ContourPlate.LevelName` (K20): slabs, polygonal caps
      and walls stay unbound, as Q2 decided. A bound part is an API failure (exit `4`), or "differs"
      on resume.
11. **Lot placement.**
    - These items go in lots ≥ 1, never in lot 0 (schema). A lot may mix them with members.
    - The schema does not enforce any order. The planner's order, from research §11 R4/R8:
      1. piles;
      2. pile caps (both kinds), pad and strip footings, ground beams;
      3. then per storey: columns and walls, beams, and slabs with their openings.
    - The spec holds no reference between lots: a slab does not name its beams, and an opening lives
      inside its parent.

## Amends ADR-0012

These amend ADR-0012 in substance, on top of ADR-0015's amendments. ADR-0012 gets a dated amendment
note after acceptance (ADR-0015 execution package 11).

- **§2 Journal.** "One entry per `SPEC_ID`" becomes "one entry per (`spec_id`, `role`)". `role` is
  `part` or `cutter`, and the `cutter` role and the state `deleted` are used only in the C7-failed
  fallback (decision 10).
- **§3 Write policy.** The intent write before each `Insert` covers a cutter's `Insert` too.
- **§6 Snapshot.**
  - **Lookup sources per kind** (decision 8): cuts come from their parents' `GetBooleans()` plus the
    journal GUIDs, and the "lookups and tags agree" check for kind `cut` uses that enumeration. It
    never expects a part filter to return a `BooleanPart`.
  - **Kind** is the Tekla kind, with a many-to-one mapping from spec types (`pile` → `column`,
    `pile_cap` → `pad_footing`, polygonal cap → `slab`).
  - Per object, the snapshot also carries Name, Position, `CastUnitType`, contour, father and
    operative-part geometry where the kind has them.
- **§7 "Differs".**
  - The kind rule is ADR-0015's ("the kind the item maps to").
  - For `column`, `pad_footing` and `slab` objects, the reserved Names `PILE` and `PILE_CAP` are part
    of the match, and a mismatch is a conflict.
  - The extra fields of decision 8 are compared.
- **§8 Plan.**
  - "With several journal GUIDs for one `SPEC_ID`, the latest one is the target" applies per
    (`spec_id`, role `part`). A cutter GUID is never an item's target.
  - A tag `SPEC_ID` of the form `<id>~CUT`, with `<id>` in the spec, is classified as the conflict
    `cutter_left`, not `UnknownSpecId`. With `<id>` not in the spec it stays `UnknownSpecId`.

## Out of scope

- Reinforcement (rebar, meshes, rebar sets, reinforcement components), embeds, anchor bolts and
  connections.
- Pour objects, pour breaks and pour management. Cast unit merging. Precast (Q13: a per-item cast
  unit field comes with precast).
- Sloped, lofted and curved slabs (`LoftedPlate`). Slab steps, drops, haunches and edge chamfers.
- Polyline, curved and non-rectangular walls, `PolyBeam(PANEL)`, and polyline strip footings as one
  object (Q9). Wall and floor layout tools.
- Stepped or sloped footings. Piles other than straight and vertical.
- Partial-depth recesses and notches. Openings with arc corners. Openings in a slab with arc corners
  (rule (m)).
- Stairs, tanks, lintels and parapets as their own kinds (they remain `engineer manual`).
- Level binding (2026). Numbering. Drawings.

## Consequences

- **Schema and validation:**
  - the composed spec schema draft, plus a CHANGELOG entry;
  - two new examples (`spec-foundations.example.json`, `spec-slab-wall.example.json`);
  - `check_spec` rules (i)–(q), with the one `SPEC_RULES_VERSION` bump shared with ADR-0015.
- **C# side:**
  - `SpecLoader`: the new arrays, member types and schema rules, read closed-world;
  - `ModelSnapshot` and `ResumePlanner`: the decision 8 table, the reserved-name match and
    `cutter_left`;
  - `run-journal.schema.json` and `RunJournalJson.cs`: the `role` field and the `deleted` state, only
    if C7 fails.
- **Contract**: the additions in the draft (rules 11–12 and table rows). No new subcommand and no
  new exit code.
- **`objects.inp`**: the three UDAs for every (Tekla type × material type) section (decision 7), and
  for booleans if the test model shows a section is needed (C4).
- **`tekla/api-notes.md`**: To verify C1–C16 (draft §5), and the facts K1–K21 with K12 and K13
  corrected.
- **Skills**: in `tekla-conversion-plan` Known gaps, R8 loses slabs, footings, pile caps, piles and
  walls, and keeps pours and rebar.
- **Criterion 7.** With ADR-0015, every object class the EVAL-4 judges named has a **contract and
  schema route; the producer is pending**. No tool writes slab, wall or foundation items yet
  (execution package P16-5). The exceptions are rebar, out of scope by the engineer's decision, and
  the out-of-scope shapes above. Those remain `engineer manual` at gate 3.
- **Open API risk.**
  - If cut tags fail (C4), or both C7 and C8 fail, openings stay closed until a new ADR.
  - If C1 or C2 fails for panels, walls wait for a new ADR.
  - If C2 cannot place a kind's solid on the stated side, that kind waits.

  None of these leads to an untagged or approximate build.

## Rejected alternatives

- **Every kind as a `ContourPlate`** (pads, rectangular caps, walls as thick plates). It loses
  Tekla's own part types (`PAD_FOOTING`, `PANEL`) and their catalog types, which UDA definitions and
  company templates key on. It also needs a 3D contour per part where two points suffice. Polygonal
  caps take this trade-off only because a `Beam` cannot have a polygonal plan (Q16).
- **Walls as vertical `ContourPlate`s.** Panels are Tekla's wall object, and their catalog type keys
  company UDAs and templates (Q9). A vertical plate would allow gable and stepped walls. Its
  thickness direction depends on the work plane, the same question C2 and C12 answer for polygonal
  wall cutters. So if those pass, the vertical-plate route is technically open for a later ADR.
- **MIDDLE Position everywhere** (the first draft). It is sign-safe, but engineers editing the model,
  2026 level binding, company templates and later rebar work all expect Tekla's native handles. Q8
  chose native handles once C2 proves their signs.
- **Tekla `Position` enums in the spec.** They are Tekla-specific and invite FRONT/BEHIND sign errors
  that no reference point reveals.
- **Polygonal caps as `slabs` items with a role field.** It mixes two kinds with different rules
  (openings, class, name) in one array, and the closed-world reader would branch on a field. A
  separate array maps one array to one rule set.
- **A fourth UDA naming the harness kind.** It would change contract rule 4 and every model's
  `objects.inp`. Name plus class tells caps from slabs and piles from columns, and Tekla reports
  already filter on both.
- **Delete-and-replace on opening update** (the first draft). Its reason was wrong: `Modify` acts on
  the operative part (K13). It also needed a delete inside `update` and gave the same `SPEC_ID` a
  new GUID.
- **An untagged transient cutter** (the first draft). The harness would make an object that its
  lookups cannot see and `rollback` cannot find (principle 4). Q11 rules it out.
- **Separate `foundations[]` or `piles[]` arrays.** Pads, rectangular caps, piles and straight strips
  are member-shaped (profile, two points, rotation). A new array would duplicate the member
  definition and reader for no new field.
- **`PolyBeam` `STRIP_FOOTING`/`PANEL` now.** It reopens ADR-0015's polybeam kind rule. Straight
  segments cover the corpus, and a later amendment can add it.
- **Openings as a top-level array with a parent reference.** It allows dangling and cross-lot
  references. Nesting rules both out by construction.
- **`CutPlane`/`Fitting` for openings.** They are plane cuts (K14 lists them as `Boolean` siblings),
  not polygonal voids.
- **A `profile` string for slabs and walls.** Thickness and height as numbers let `check_spec` check
  openings and the cutter size. The composed string is one CLI function, checked once (C1).
- **New subcommands** (`build-slab`, `cut`). The guard hook would have to classify them, and the same
  safety rules apply inside `build`/`update`/`rollback`.

## Execution packages

ADR-0015's packages 1–11 come first, and its packages 3, 5, 6, 7, 8 and 9 also carry this ADR's
part. There is one package per concern for both ADRs, with one `SPEC_RULES_VERSION` bump. The
additions are:
- **P15-3**: the composed schema of `0016-schema-draft.md` §1 and the two examples here;
- **P15-5**: rules (i)–(q);
- **P15-6**: the arrays, the types and the schema rules of decision 9;
- **P15-7**: the decision 8 table and the reserved-name match;
- **P15-8**: draft §4;
- **P15-9**: R8 in the planner skill, and the lot report for concrete kinds.

The packages of this ADR alone, in dependency order:

1. **P16-1 api-notes To verify and facts.** Add C1–C16 and K1–K21 (K12 and K13 corrected) to
   `tekla/api-notes.md`. Done when `grep -n "C16\." tekla/api-notes.md` prints one line. Can run with
   ADR-0015 package 2.
2. **P16-2 Cutter journal role.** Blocked until C7 is run, and dropped if C7 passes.
   - `role` and `deleted` in `schemas/run-journal.schema.json` (with a CHANGELOG entry),
     `tekla/TeklaCore/RunJournal.cs` and `RunJournalJson.cs`; `cutter_left` in
     `tekla/TeklaCore/ResumePlanner.cs`; tests in `tekla/TeklaCore.Tests/RunJournalJsonTests.cs` and
     `ResumePlannerTests.cs`.
   - Done when `uv run pytest tests/test_schemas.py` passes and `dotnet test tekla/TeklaCore.Tests`
     passes on the windows-latest CI job. Needs ADR-0015 package 7.
3. **P16-3 Position table.** Blocked until C2.
   - The (spec `type` × material type) → Position values, concrete and steel rows of decision 2,
     with the C2 evidence reference, in contract rule 11 (`docs/tekla-cli-contract.md`) and in
     `tekla/api-notes.md`.
   - Done when `grep -n "C2" docs/tekla-cli-contract.md` shows rule 11 citing it, and
     `grep -n "Position" tekla/api-notes.md` lists one value row per kind of decision 2, steel
     rows included.
4. **P16-4 Repo `objects.inp`** (ADR-0007 §5, decision 7).
   - Sections for `grid` and for every (Tekla type × material type) pair, holding `LOT`, `RUN_ID` and
     `SPEC_ID` as `unique_attribute`, string, `special_flag no`.
   - Files: `tekla/objects.inp` (new), `tests/test_objects_inp.py` (new; parses the sections and
     checks the three UDAs in each).
   - Done when `uv run pytest tests/test_objects_inp.py` passes. Needs T3 (polybeam section).
5. **P16-5 Spec producer for foundations, slabs and walls** (review M-9).
   - It writes `members` (footings, caps, piles), `polygonal_caps`, `slabs` and `walls` items from
     the reader's findings and the engineer answers.
   - Every Q5 elevation is traced to an engineer answer, column, beam and poly member Z included
     (OQ-B). The pile toe comes from the drawing, with a question when it is missing or low.
   - Files: `src/tekla_harness/lot_spec.py` (new), `src/tekla_harness/cli.py`,
     `tests/test_lot_spec.py` (new).
   - EVAL-5 criterion: on the corpus sets with foundations, slabs or walls (264, 271 and 278 types),
     every produced spec validates, and every elevation of rules (f) and (p) traces to an engineer
     answer.
   - Done when `uv run pytest tests/test_lot_spec.py` passes. Needs ADR-0015 packages 5 and 10.
