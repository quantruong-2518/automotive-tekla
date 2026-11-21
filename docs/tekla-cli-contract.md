# `tekla-cli` contract (draft, implemented in Step 3)

`tekla-cli` is the only path from an agent to a Tekla model. It is a thin, deterministic
.NET Framework 4.8 executable over `TeklaCore`. This document fixes its interface now so
the guard hook, permissions and schemas can rely on it. Open API facts behind it, with sources:
[`tekla/api-notes.md`](../tekla/api-notes.md). Decisions: [ADR-0007](decisions/0007-tekla-cli-failure-backup-and-tags.md).

## Build and invocation

- Target: Tekla Structures **2026** (Diamond), engineer decision Q1 of
  [ADR-0015](decisions/0015-lot-spec-grids-levels-nonlinear-members.md) (2026-11-11). NuGet
  `Tekla.Structures.Model` and `Tekla.Structures.Catalogs` **2026.0.3**, `net48`, `x64`. The pin is
  documentary until `TeklaAdapter.csproj` exists (no project references `Tekla.Structures.*` yet).
  Known 2026 deltas: the `Tekla.Structures.Model` package targets `netstandard2.0` only and the
  DLLs are x64-only; the first Windows build confirms that the `net48` x64 executable consumes
  them. Other versions are separate builds, each verified on its own.
  History: the pin was 2024.0.4 (Tekla 2024) until 2026-11-11; the 2024 facts stay in
  [`tekla/api-notes.md`](../tekla/api-notes.md), marked as 2024.
- The executable is named **`tekla-cli.exe`** (`AssemblyName` `tekla-cli`). Agents call it only
  by that name, never through `dotnet run`, `dotnet exec` or `dotnet watch`. The guard hook
  denies those routes outside `builder` (RTI-0006).
- `tekla-cli.exe.config` (assembly `codeBase` + `bindingRedirect`, needed since Tekla 2024 (so for 2026 too) is
  not in the GAC) is generated at build time by `TSAppConfigPatcherTask`, for every build
  configuration. A machine with Tekla installed in another folder needs a rebuild.

## Conventions

- Input: arguments plus an optional JSON file (`--spec <path>`). Output: one JSON object on
  stdout. Diagnostics on stderr.
- Exit codes: `0` ok · `1` validation failure (nothing written, or an existing object differs
  from its spec item on resume) · `2` usage error · `3` environment error (Tekla not running,
  wrong model, wrong version, tag UDAs not defined, member-lot sources disagree or a tag is
  unreadable, a cut tag write or read-back fails; a failed cut tag write or read-back, and a wrong
  model found by the rule 1 re-check before `CommitChanges`, stop mid-run as in rule 5, objects
  kept and journalled) · `4` Tekla API error (stopped; objects done so far are kept and listed in
  the run journal) · `5` refused by safety rule.
- Every command prints `tekla_version`, `model_path`, and `run_id` in its JSON output.
- The subcommand is always the first argument; options follow it
  (`tekla-cli build --lot 3 …`, never `tekla-cli --lot 3 build`). The guard hook relies on this
  and treats anything else as a write.

## Subcommands

| Subcommand | Class | Purpose |
|---|---|---|
| `info` | read | Tekla version, open model, catalogs available, tag UDA definitions for every (Tekla type × material type) pair a spec can produce, and `CatalogObjectTypeEnum.GRID` |
| `validate` | read | Check profiles/materials/components in a spec exist in the catalogs (members, poly members, slabs, polygonal caps, walls, and the profiles the CLI composes for them and for opening cutters); poly member point count within `Contour.MAX_POLYBEAM_POINTS`, outline and opening point counts within `Contour.MAX_CONTOUR_POINTS`; material type `MATERIAL_CONCRETE` for footings, pile caps, piles, slabs, polygonal caps and walls |
| `query` | read | Objects by `LOT` / `RUN_ID` / `SPEC_ID` / GUID; grids by enumerating every `Grid` and reading its tags (no UDA filter); untagged grids listed separately; opening cuts by enumerating each found slab's or wall's `GetBooleans()` and reading the cut's tags (no UDA filter) |
| `selected` | read | Objects currently selected in the Tekla UI |
| `export` | read | CSV + IFC of a lot or run (writes files, not the model; may change the UI selection, restores it afterwards). CSV adds one row per grid (frame), one per grid line or level, one per polybeam point and one per slab, cap or opening contour point, and the profile, Position, cast unit type and name of each concrete part; grids are not exported to IFC, and IFC is a count check only for slabs, caps, walls and cuts |
| `build` | **write** | Create the objects of one lot from `spec.json`, tag them, one commit; resumes a stopped run. Lot 0 builds grids (levels are their Z planes); lots ≥ 1 build members, poly members, slabs, polygonal caps and walls, each slab or wall followed by its opening cuts |
| `update` | **write** | Modify objects of one lot from a corrected spec; for lot 0 only additive while a member lot exists (rule 9); an opening is modified in place (rule 12) |
| `rollback` | **write** | Delete all objects of a `RUN_ID`, grids and opening cuts included (cuts before their parent), and the journalled cutters carrying this run's tags; run only on the engineer's request, never automatically; a cutter with this run's tags but no journal entry is listed, not deleted; refused for lot 0 while a member lot exists (rule 9) |

Any subcommand not listed as **read** is treated as a write by the guard hook (fail closed).
Adding a read subcommand requires updating `READ_SUBCOMMANDS` in
`.claude/hooks/guard_tekla_write.py` and its tests.

## Safety rules enforced inside `tekla-cli` (write commands)

Order: rule 1 is checked first. Then every refusal of rules 3 to 13 that can be decided without
writing (from the arguments, the spec and its receipt, the run journals, the model as read at the
start of this command, and the CLI's own gate constants and Position table) is decided for the
whole command before the backup of rule 2 and before the first `Insert`, `Modify`, `Delete` or
`SetUserProperty`; "before anything is written" means this. A command stops mid-run only on an API
error (rule 5), a failed journal write (ADR-0012 §3), a failed rule 1 re-check right before
`CommitChanges` (ADR-0009 Amendment 1), or a failed check after a model call in rules 10, 11 and
12. Each keeps what was made and journals it as rule 5 does (after a failed journal write, the
output lists every GUID made instead), with the exit code its rule or ADR gives.

1. Refuse unless the open model path matches the project's declared working copy, and that path
   differs from the declared original. Check on every command, and again right before
   `CommitChanges` (ADR-0009 Amendment 1): external applications talk only to the first Tekla
   session started. Both a path-text check and a file-identity check must prove it
   ([ADR-0009](decisions/0009-tekla-dotnet-layout.md), Amendments 1–2); any doubt refuses. Both
   folders must be on local NTFS/ReFS drives, the working copy must be declared and opened by its
   real path (no subst, junction or mapped letter), the original by its real drive letter, and
   neither folder may contain links or cloud-sync placeholders (nor the copy hard-linked files).
   Another model open is exit `3` (wrong model); any other refusal is exit `5`.
2. Before writing, create the lot backup with a Tekla macro that runs *Save and create backup
   copy*, then check that a new backup folder exists. Refuse (exit `5`) if either fails. The
   macro route must pass on the test model before the first real lot.
3. Refuse unless `--lot`, `--run-id` and a schema-valid `--spec` are given. "Schema-valid" means
   a validation receipt from `harness validate spec` whose SHA-256 matches the spec file
   ([ADR-0010](decisions/0010-spec-validation-receipt.md), Amendment 1). A missing or mismatched
   receipt, a spec the reader rejects, or a spec `lot` other than `--lot` exits `5`; missing
   arguments exit `2`; an existing spec or receipt that cannot be read exits `3`. `--lot` accepts
   `0` (the setup lot, [ADR-0015](decisions/0015-lot-spec-grids-levels-nonlinear-members.md)).
4. Tag every created or modified object, grids included, with UDAs `LOT`, `RUN_ID`, `SPEC_ID`.
   Refuse (exit `3`) unless all three are defined in the model as `unique_attribute`, type
   `string`, not affecting numbering, for parts and for grids (`CatalogObjectTypeEnum.GRID`; the
   repo ships the `objects.inp`, with a `grid` section, to copy into each model folder).
   If To verify T2 shows that a `Grid` cannot keep the three tags, the grid route stays closed
   until a new ADR and refuses with exit `3` (ADR-0015 Consequences);
   while T2 has no recorded result, rule 13 refuses it with exit `5`.
5. Commit once per command. On any API error: stop, keep every object already created or modified,
   write the run journal (GUID and `SPEC_ID` of each object done, the failing item, the error) and
   exit `4`. Never delete objects to clean up (one exception: rule 12's fallback cutter). `update`
   never deletes an object (ADR-0016, Safety). An `update` whose spec lacks an object of this lot,
   under any `RUN_ID`, refuses (exit `5`) before anything is written and lists each such `SPEC_ID`,
   `RUN_ID` and GUID; the engineer uses `rollback`, for lot 0 within rule 9's limits (engineer,
   2026-11-11).
6. Resume: re-running `build` for the same lot and `RUN_ID` skips every spec item whose
   `SPEC_ID` already exists in that lot and run, and builds only the missing ones. If an existing
   object differs from its spec item, stop with exit `1` and ask the engineer. Never create a
   duplicate `SPEC_ID`. Journal, snapshot, matching rules ("differs" includes kind, rotation and
   class since 2026-11-08), lock and refusals: [ADR-0012](decisions/0012-run-journal-and-resume-planner.md),
   as amended by ADR-0015. The kind compared is the Tekla kind the spec item maps to (`brace`,
   `purlin`, `girt`, `rafter`, `other` are kind `beam`); a grid item matches only kind `grid`, a
   poly member only kind `polybeam` (its spec `type` is not compared); "differs" per ADR-0015
   decision 9. Concrete parts and openings ([ADR-0016](decisions/0016-lot-spec-slabs-footings-piles-walls.md)
   decision 8): a `pile` matches kind `column` named `PILE`, a `pile_cap` kind `pad_footing` named
   `PILE_CAP`, a slab kind `slab` not named `PILE_CAP`, a polygonal cap kind `slab` named
   `PILE_CAP`, a wall kind `panel`, an opening kind `cut` whose father is its parent's object; the
   reserved Names `PILE` and `PILE_CAP` are part of the match (a `members` `column` item
   whose object is named `PILE`, or a `pad_footing` item whose object is named `PILE_CAP`, is a
   conflict too), other name differences are reported only;
   "differs" also covers the Position, the cast unit type and the composed profile. Position (rule
   11 table) is compared for every member, steel included; for poly members it is set, not
   compared.
7. Read the spec closed-world: any key or enum value outside the spec schema, at any nesting level
   the CLI interprets, refuses (exit `5`), so no spec item is ever skipped or misread silently.
   `spec_id` is unique across `members`, `poly_members`, `grids`, `slabs`, `polygonal_caps`,
   `walls` and every nested opening. A receipt whose `rules_version` is below the CLI's minimum
   refuses (exit `5`).
8. Lot 0 holds grids only and lots ≥ 1 hold no grids; anything else refuses (exit `5`). A grid
   with `rotation_deg` 0 is built in the global work plane with `Origin` = its origin plus its
   first line positions; a rotated grid in a work plane turned by `rotation_deg` about +Z at its
   origin, the global plane set back afterwards (refused, exit `5`, until To verify T7 passes); a
   one-direction grid (`y_lines` empty) is refused until T8 passes. X/Y are written as spacings
   from the first line with 2 decimals, Z as absolute level values, `IsMagnetic = false`. A poly
   member is a `PolyBeam` of type `BEAM`, one `ContourPoint` per spec point, chamfer
   `CHAMFER_NONE` or `CHAMFER_ARC_POINT`, built in the global work plane.
9. Lot 0 after it is built. Never modify or delete an untagged grid; `build` of lot 0 lists untagged
   grids in its output. Whether a member lot exists is decided from two sources, an enumeration of
   every harness-built kind with `LOT` read per object and the run journals of the project's lot
   folders plus `project-state.json` (a member lot is any lot ≥ 1, whatever it holds; one counts
   when an object carries its `LOT` or a journal of it records an object entry not followed by a
   complete `rollback`, ADR-0015 decision 10); a disagreement or an unreadable tag refuses (exit
   `3`), and the refusal names each lot, run journal and GUID that disagree. While a member lot
   exists, `update` of lot 0 may only add grids, lines or levels (nothing moved, renamed or removed:
   each grid keeps its name, origin and rotation, each line and level its label and position, ≤ 0.1
   mm) and `rollback` of lot 0 refuses (exit `5`); a grid missing from the spec refuses under rule 5
   whether or not a member lot exists. A non-additive `update` or a `rollback` of lot 0 also refuses
   (exit `5`) while any part, tagged or not, is bound to a level of a grid being changed or has a
   reference point within the union of the grid's extent before and after the change (the span of
   its lines and levels; the union: engineer, 2026-11-11) plus 1 000 mm, both found by enumerating
   every part and reading its level names and reference points, never by `GetObjectsByBoundingBox`
   (To verify #18); the refusal lists each such part (GUID, type, name, reference points, level
   names). Only while no member lot exists, `update` of lot 0 with `--allow-untagged-shift
   <question_id>` lifts this one refusal; the `question_id` is the engineer answer that authorises
   it. The output then lists those parts before the change and again after it, each read back and
   marked moved when a reference point changed by more than 0.1 mm or a level name changed, and the
   run journal records the flag, the `question_id` and the parts with their before and after values.
   With no member lot, every part the clause finds is untagged. The flag lifts nothing else: not the
   member-lot rule, not the exit `3`, not untagged grids, not the T9 gate, not rule 5's
   missing-object refusal, and `rollback` of lot 0 takes no such flag. The flag is valid only on
   `update --lot 0`; on any other command or lot, or with a `question_id` that does not match
   `^Q-[0-9]{3,}$` (`schemas/common.schema.json`, `question_id`), the CLI exits `2`. Until To verify
   T9 passes, an additive `update` of lot 0 and every `update` with the flag refuse (exit `5`)
   before anything is written (ADR-0015 decision 10).
10. Tekla 2026: parts are not bound to levels. A write command checks, before anything is written,
    that this CLI can read the level members; one built without them refuses on Tekla 2026 or later
    (exit `3`). The CLI sets the unbound value (To verify T4); a part whose `StartLevelName` or
    `EndLevelName` (beams, polybeams) or `LevelName` (contour plates) is still set after `Insert`
    stops the run as in rule 5 (keep, journal, exit `4`); one found in the snapshot when planning a
    resume differs from its spec item (exit `1`). If T4 shows that the API cannot unbind, no write
    route opens until a new ADR.
11. Concrete parts (ADR-0016). Pad footings and pile caps are a `Beam` of type `PAD_FOOTING`, piles
    of type `COLUMN` with Name `PILE`, strip footings of type `STRIP_FOOTING`, walls of type
    `PANEL`; slabs and polygonal caps a `ContourPlate` (a polygonal cap with Name `PILE_CAP`, every
    pile cap likewise). The reference line or contour is the spec's own (top line, top face, base
    line, head to toe). Steel members: a beam's line is its top-of-steel centre line, a column's
    and a brace's their centroid axis. The CLI sets the `Position` from one table, one row per (kind
    × material type) as keyed below, whose values come from To verify C2, and refuses (exit `5`),
    before anything is written, every item whose row is not yet in the table. A row is keyed by
    (kind × material type): for `members` and `poly_members` the kind is the spec `type` (poly
    members take the row of their `type`), for `walls`, `slabs` and `polygonal_caps` it is the
    array (rows wall, slab, polygonal cap); steel rows included (ADR-0016 decision 2, OQ-C).
    `CastUnitType` is `CAST_IN_PLACE` for concrete parts. After `Insert` the CLI reads back
    `Beam.Type` and `ContourPlate.Type` (`SLAB`); any other value stops the run as in rule 5.
12. Openings (ADR-0016). Each opening is a `BooleanPart` of type `BOOLEAN_CUT` whose father is its
    parent's object, built right after the parent in the same command and tagged like a part. No
    catalog type covers booleans, so rule 4's definition check cannot cover a cut: the CLI checks
    the result of each cut tag write and reads the three tags back; a failed write or read-back
    stops the run, keeps what is made, writes the journal and exits `3`; the output names the cut's
    GUID and the tags that failed (ADR-0016 decisions 6 and 7; exit `3`: engineer, 2026-11-11).
    Refused (exit `5`), before anything is written, until To verify C4 (cut tags persist), C5 (cut
    read-back) and C6 (cascade delete) pass, and C7 has a recorded result with either C7 passed or
    C7 failed and C8 passed. So every run with openings can be resumed and rolled back (ADR-0016
    decision 6; C5 and C6 before build: engineer, 2026-11-11). A wall opening that is a rectangle
    (four corners, two horizontal and two vertical edges within 0.1 mm) is cut by an operative
    `Beam` along the wall normal through its centre, in the global work plane (no work-plane change;
    To verify C10); any other wall opening needs an operative `ContourPlate` in a work plane set to
    the wall's centre plane and refuses (exit `5`) until To verify C2 (wall cutter) and C12 pass
    (ADR-0016 decision 6). The operative part (class `BooleanPart.BooleanOperativeClassName`) is
    composed from the opening and its parent and is never inserted (C7). Only if C7 fails and C8
    passes: it is inserted with `LOT`, `RUN_ID` and the reserved `SPEC_ID` `<opening spec_id>~CUT`,
    journalled with role `cutter`, and deleted after the cut's `Insert`: the only delete inside
    `build`, an exception to rule 5 for that GUID only, while it carries this run's tags, and
    journalled; one left by a stopped run is a conflict on resume (exit `1`), never deleted by
    `build`. An `update` that would add an opening in this fallback refuses (exit `5`); the engineer
    rolls back and rebuilds the lot instead (`update` never deletes, rule 5; engineer, 2026-11-11).
    Cuts are looked up by enumerating each found parent's `GetBooleans()` plus the journal GUIDs.
    `update` modifies an opening in place through `BooleanPart.OperativePart` and `Modify`, keeping
    its GUID, whenever the composed cutter changes; until To verify C9 passes, an `update` that
    changes an opening refuses (exit `5`).
13. A route opens only after the To verify items it depends on pass on the test model; until then it
    refuses (exit `5`) before anything is written: every write route, T4 (ADR-0015 decision 11);
    grids, T1 and T2 (rotated T7, one-direction T8, rule 8; T2 failed: exit `3`, rule 4); poly
    members, T3 (ADR-0015 decision 4); additive lot-0 `update` and the lot-0 override flag, T9 (rule
    9); openings, C4, C5 and C6 passed, and either C7 passed or C7 failed and C8 passed (rule 12),
    for `build`, `update` and `rollback` of a run with openings alike; opening changes in `update`,
    C9; non-rectangular wall openings, C2 (wall cutter) and C12 (rule 12); Position values, C2, one
    gate per table row (rule 11); the profile of every pad footing, pile cap (`members` `pile_cap`
    and `polygonal_caps`), strip footing, slab, wall and opening cutter, C1 (walls: ADR-0016
    Consequences; the other kinds: engineer, 2026-11-11); the rectangular wall cutter, C10
    (engineer, 2026-11-11); piles built as columns, C14 (engineer, 2026-11-11); the backup macro,
    To verify #13 (rule 2). Each gate holds one of three states, no result, passed or failed, with
    its evidence. Every gate is a constant in the CLI's code, per Tekla version, and opens only by
    a commit that the engineer merges, citing the test-model evidence recorded in
    `tekla/api-notes.md` (Tekla version, date, model). No command-line option, environment variable
    or file read at run time opens a gate (engineer, 2026-11-11). The version key is the full
    `tekla_version` the CLI prints, service pack included; a version with no recorded evidence
    keeps every gate closed. This list is complete: a To verify item not named here gates no route.
    Except for T4, To verify #13 and the opening gates, a gate covers `build` and `update` of its
    route only (engineer, 2026-11-11).

## Open questions

- ADR-0015 To verify T1–T10 (`tekla/api-notes.md`): how the API reads grid coordinate strings and
  rounds them, grid UDAs, polybeam arc read-back and point limit, 2026 level binding (first test on
  2026), string limits, rotated and one-direction grids, additive grid `Modify`, the model-wide
  `LOT` enumeration.
- ADR-0016 To verify C1–C16 (`tekla/api-notes.md`): composed concrete profiles and their axes,
  native-handle `Position` signs, contour read-back, UDAs on a cut, cut read-back, cascade delete,
  operative part never inserted or tagged, opening modify in place, wall cutters, flush cuts,
  work-plane side effects, UI copy of cuts, piles as columns, contour point limit, IFC entity of
  polygonal caps.
- Whether objects inserted before a crash, without `CommitChanges`, persist
  (`tekla/api-notes.md`, To verify #9).
- The backup macro (To verify #13) and the backup folder location (`XS_MODEL_BACKUP_DIRECTORY`)
  on the Tekla machine.
- UDA names: among `objects.inp` files the model folder is read first, so its definitions win;
  but an existing model keeps the definitions stored in its `environment.db` (update them with
  *Diagnose and change attribute definitions*). Confirm on the test model that `LOT`, `RUN_ID`,
  `SPEC_ID` are not already used with another type.
- Rule 9 extent of a one-direction grid (`y_lines` empty): defined in the commit that opens T8
  (recommended: the line length read back from Tekla, else refuse); until then T8 stays closed.
