# How a Tekla Structures model is built from 2D drawings: primary-source note for lot planning

Purpose: ground the future `tekla-conversion-plan` skill (modelling roadmap: lots, sequence, approach).
Retrieved 2026-11-06. Everything downloaded was treated as untrusted data and only read, never executed.
PDF copies were kept outside the repo (agent scratchpad, `research-tekla/pdf/`); nothing else was written.

Evidence tags used below:

* **[PDF]** read from the downloaded official PDF text, cited as `S1 p.N` (PDF page = printed page number).
* **[HTML]** raw page downloaded with `curl` and grepped (the page text itself).
* **[fetch]** read through WebFetch, which returns a *model-written summary* of the page, not the raw text.
  Treat as likely-correct but not exact; component names from this route were re-checked against raw HTML.
* **[search]** only seen in a search-engine snippet. Listed as **unverified** and never used as a rule.
* **unverified** = not confirmed from a primary page. **not found** = searched, nothing.

## Sources

| ID | Source (all Tekla/Trimble first-party) | Tekla version | Route |
|---|---|---|---|
| S1 | *Create models*, https://support.tekla.com/dist/sxf/document/TS_MOD_2025_en_Create_models.pdf | 2025 (Mar 2025) | PDF |
| S2 | *Manage Tekla Structures*, https://support.tekla.com/dist/sxf/document/TS_MGE_2025_en_Manage_Tekla_Structures.pdf | 2025 (Mar 2025) | PDF |
| S3 | *Plan and track projects*, https://support.tekla.com/dist/sxf/document/TS_PLA_2025_en_Plan_and_track_projects.pdf | 2025 (Mar 2025) | PDF |
| S4 | Reference models and compatible formats, https://support.tekla.com/doc/tekla-structures/2025/int_reference_models | 2025 (mod. 19 Jan 2026) | HTML + fetch |
| S5 | Insert a reference model, https://support.tekla.com/doc/tekla-structures/2025/int_inserting_a_reference_model | 2025 | fetch |
| S6 | Import 2D or 3D DWG or DXF files, https://support.tekla.com/doc/tekla-structures/2025/int_importing_dwg_dxf_files | 2025 | HTML + fetch |
| S7 | DWG and DXF, https://support.tekla.com/doc/tekla-structures/2026/int_dwg_and_dxf | 2026 | fetch |
| S8 | Convert IFC objects into native Tekla Structures objects, https://support.tekla.com/doc/tekla-structures/2025/int_conversion_management | 2025 | HTML + fetch |
| S9 | Enhanced IFC interoperability (release note), https://support.tekla.com/doc/tekla-structures/2026/rel_int_enhanced_ifc_interoperability | 2026 | fetch |
| S10 | Insert IFC models as reference models, https://support.tekla.com/doc/tekla-structures/2025/int_ifc_import | 2025 | fetch |
| S11 | Grid From Parts (Tekla Warehouse extension), https://support.tekla.com/help/tekla-structures/not-version-specific/grid_from_parts | not version-specific | fetch |
| S12 | DWG reference file not visible, https://support.tekla.com/article/dwg-reference-file-not-visible | not version-specific | fetch |
| S13 | Define and update UDAs, https://support.tekla.com/doc/tekla-structures/2026/sys_customizing_uda | 2026 | fetch (same text in S2 p.144-146) |
| S14 | Properties of objects.inp files, https://support.tekla.com/doc/tekla-structures/2026/sys_objects_inp_properties | 2026 | HTML + fetch |
| S15 | Maximum length of UDA (article), https://support.tekla.com/article/maximum-length-of-user-defined-attribute-uda | not version-specific | HTML |
| S16 | Customize the original profile catalog, https://support.tekla.com/doc/tekla-structures/2025/mod_profiles | 2025 | fetch |
| S17 | Customize the new profile catalog, https://support.tekla.com/doc/tekla-structures/2025/adm_customize_profile_catalog | 2025 (mod. 16 Feb 2026) | fetch |
| S18 | Start Tekla Structures, https://support.tekla.com/doc/tekla-structures/2025/gen_start_tekla_structures | 2025 | fetch |
| S19 | Overview of environments, roles, and configurations, https://support.tekla.com/doc/tekla-structures/2026/ins_configurations_environments_roles | 2026 | fetch |
| S20 | Opened Tekla Structures for the first time and profiles are not showing, https://support.tekla.com/article/opened-tekla-structures-for-the-first-time-and-profiles-are-not-showing | not version-specific | fetch |
| S21 | Localization release notes, https://support.tekla.com/doc/tekla-structures/2026/rel_localization_notes | 2026 | fetch |
| S22 | Phases and lots to tasks (extension), https://support.tekla.com/help/tekla-structures/not-version-specific/phases_and_lots_to_tasks | not version-specific | fetch |
| S23 | Sequencer, https://support.tekla.com/doc/tekla-structures/2025/mod_defining_sequences | 2025 | fetch (also S3 p.170-172) |
| S24 | Phase Manager, https://support.tekla.com/doc/tekla-structures/2025/mod_dividing_the_model_into_phases | 2025 | fetch (also S3 p.164-166) |
| S25 | Lotting, https://support.tekla.com/doc/tekla-structures/2025/mod_defining_lots | 2025 | HTML (also S3 p.167-169) |
| S26 | Task Manager, https://support.tekla.com/doc/tekla-structures/2025/tm_intro_task_manager | 2025 | fetch (also S3 p.139-163) |
| S27 | Shear tab connections, https://support.tekla.com/doc/tekla-structures/2025/com_steel_shear_tabs | 2025 | HTML |
| S28 | End plate connections and details, https://support.tekla.com/doc/tekla-structures/2026/com_steel_end_plates | 2026 | HTML |
| S29 | Base plates, https://support.tekla.com/doc/tekla-structures/2026/com_steel_base_plates | 2026 | HTML |
| S30 | Moment connections, https://support.tekla.com/doc/tekla-structures/2025/com_steel_moment_connections | 2025 | HTML |
| S31 | Std bracing connection (67) and related bracing list, https://support.tekla.com/doc/tekla-structures/2025/det_bracing_std_bracing | 2025 | HTML |
| S32 | Detect changes between reference model versions, https://support.tekla.com/doc/tekla-structures/2024/int_detecting_changes_in_reference_model | 2024 | fetch |
| S33 | Basic Modeling for Precast - Tutorials (index of 11 videos), https://support.tekla.com/article/basic-modeling-for-precast-tutorials | 2019-2026, US Imperial environment | fetch |
| S34 | Tekla Open API Grid class, https://developer.tekla.com/doc/tekla-structures/2025/grid-class-52622 | 2025 | fetch |
| S35 | Tekla Open API Beam class, https://developer.tekla.com/doc/tekla-structures/2025/beam-class-51968 | 2025 | fetch |
| S36 | Tekla Open API ModelObject.SetUserProperty overloads, https://developer.tekla.com/doc/tekla-structures/2026/set-user-property-method-72023 | 2026 | fetch |
| S37 | Insert drawing and adjust grid (video page), https://support.tekla.com/video/import_drawing_adjust_grid | 2021 / 2018i | fetch (page has text description only) |

Version note: guides S1-S3 are the 2025 edition. The harness targets an unknown Tekla version (open question in
`docs/tekla-cli-contract.md`). Menu names in 2024/2026 may differ slightly; re-check against the installed version.

## 1. Recommended modelling order and workflow

**Tekla's own statements (cited):**

1. Set up the workspace before modelling: define units and decimals; modify the grid ("create a modular grid if needed");
   create views; resize the work area; learn the coordinate system and shift the work plane for sloped structures.
   (S1 p.19-20)
2. Chapter order in the *Create models* guide is itself the product's intended build-up: parts (p.209-348) -> details
   on parts such as bolts, welds, cuts and fittings (p.349-) -> assemblies (p.425) -> cast units (p.440) -> pours (p.454)
   -> reinforcement (p.479) -> construction objects. S1 p.209 says: parts are "the building blocks of the physical model";
   concrete parts "need to be reinforced" once created; points and construction objects are aids.
3. Components (connections/details) use existing parts: parts shown blue in a component dialog "should already exist
   in the model before you create the component"; yellow parts are created by the component. (S1 p.783)
4. Numbering has two timings: the plan comes first, the run comes later (see 6 and 11). You "do not need to number the
   model before you create general arrangement drawings", but fabrication drawings and accurate reports need numbers.
   (S1 p.733-734)
5. Phase Manager example: "First create a basic model that includes, for example, the columns. This is phase 1."
   Other users then model other parts of the building as later phases. Phases "are often used to indicate erection
   sequences". (S3 p.164, S24)
6. Model identical areas once and copy them; "you may even be able to add connections before copying the area".
   Example: a column with base plate and cap plate, copied to all locations; whole identical floors copied to other levels.
   (S1 p.208)
7. Large-model tips: keep the model near the origin and use base points for site coordinates; keep the work area small;
   use view filters; do not number the whole model in one go. (S1 p.206-207)

**Steel building (cited items marked; the rest is practice):**

| # | Step | Basis |
|---|---|---|
| 1 | Environment, units, base point, work area, views | S1 p.19, p.206 (cited) |
| 2 | Grid and levels (Z elevations) | S1 p.19-27 (cited) |
| 3 | Default part properties incl. numbering series, class, material | S1 p.735 "include the numbering series in the default part properties ... before you start modeling" (cited) |
| 4 | Columns (with base plates as details) | S3 p.164 example only; "columns first" is an example, not a rule (practice) |
| 5 | Primary beams, rafters | practice, unverified as an official order |
| 6 | Bracing, then secondary steel (purlins, girts) | practice, unverified |
| 7 | Plates / stiffeners as parts when no component fits | S1 p.781 custom components (cited for the option) |
| 8 | Connections and details via components (AutoConnection per framing condition) | S1 p.780-783, p.803 (cited) |
| 9 | Bolts, welds, cuts, fits not made by components | S1 p.349- (cited chapter order) |
| 10 | Assemblies (main part, sub-assemblies) | S1 p.425 (cited) |
| 11 | Checks (section 10), numbering, then drawings and reports | S1 p.733 (cited) |

The Tekla learning path (steel e-learning: columns, beams, rafters and bracing, base plates, connections, clashes,
stiffeners and cuts, drawings) appeared only as a search snippet; the page redirects to YouTube and was not read: **unverified**.

**Cast-in-place concrete (official example, S1 p.477-479, quoted order):**
1. Use an existing engineering/architectural model or drawing as a reference model.
2. If IFC: convert needed concrete structures to native objects, check the result, fix profile/material/cast unit type.
3. Otherwise model cast-in-place parts "by tracing over the reference model".
4. Set a pour phase number per part (0 horizontal, 1 vertical in the example).
5. View/check pour objects in a pour view. 6. Adjust pour phases or add pour breaks. 7. Define pour sequence numbers
   or Organizer categories. 8. Calculate pour units. 9. Set concrete mix/status properties. 10. Categorise pours in
   Organizer. 11. Optionally schedule in Task Manager. 12. Create GA drawings for pour units.
   Reinforcement fits between geometry and pour units (S1 p.479: reinforce "once you have created a model of concrete parts").

**Precast concrete:** the official tutorial index lists eleven videos in this order: Setup Model, Creating Foundations,
Creating Walls, Creating Columns Beams and Spandrels, Modeling Double Tee Slabs, Modeling stairs, Modeling cuts and
blockouts, Modeling reinforcement, Creating drawings, Editing drawings, Publishing output files (S33; US Imperial
environment, versions 2019-2026). This is a teaching order, not a rule. Cast-unit guidance: set cast unit type (numbering
depends on it), and model beams and interior walls "from left to right, bottom to top" and exterior walls (wall layout)
clockwise because casting direction affects numbering (S1 p.441-442).

## 2. Grids

**Definition (S1 p.20-27, 2025):**

* A grid is "a three-dimensional complex of horizontal and vertical planes", shown with dash-and-dot lines. Rectangular and
  radial grids exist. Several grids can coexist ("a large-scale grid for the entire structure, and smaller grids for some
  detailed sections"). Single grid lines can be added to an existing grid (between lines, or between two picked points).
* Creation: `Edit` tab -> `Grid` -> `Create rectangular grid` or `Create radial grid`; a new model already gets one
  rectangular grid from the saved standard properties. Double-click to modify. Property files: `*.grd` (rectangular),
  `*.rgrd` (radial).
* **Coordinates box (rectangular)**: X = grid lines vertical to the work plane, Y = horizontal, Z = elevations.
  Max 1024 characters. "Use a zero at the start to represent a grid on the 0,0 coordinate and spaces as separators."
  **X and Y entries are relative to the previous entry; Z entries are absolute** distances from the work plane origin.
  Both `0 4000 4000` and `0 2*4000` "create three grid lines with the spacing of 4000". By this rule `0 4*6000` means five
  lines at 6000 spacing (derived from the documented `n*d` form; that exact string is not printed in the docs).
* **Labels box**: names shown in views. Names in the X box belong to lines parallel to the y axis (and vice versa); the Z
  box names levels parallel to the work plane. Label boxes may be left empty.
* **Origin** offsets the grid from the *work plane* origin, not the global origin. **Line extensions** set how far lines
  extend. **Magnetic grid plane**: objects bound to grid lines follow if a line moves. UDAs on the grid can drive drawing grid labels.
* **Radial grid**: Radial values = curved lines (single radius must be >0), Angular values = straight lines (negative angles
  allowed), Elevations = levels; same relative/absolute rules. An alternative "Radial Grid" component exists, whose curved
  lines "are not truly curved but straight".
* New line between lines 1 and 2 is auto-labelled `12*`. Very large grids with labels always visible can slow Tekla
  (advanced option `XS_ADJUST_GRID_LABELS`).
* **Open API** (S34, 2025): `Grid` has `CoordinateX/Y/Z`, `LabelX/Y/Z`, `ExtensionLeft/RightX/Y/Z`, `IsMagnetic`, `Origin`, `Name`,
  inherits `Insert()`. Constructor defaults: `CoordinateX "0.00 4*3000.00"`, `CoordinateY "0.00 5*6000.00"`,
  `CoordinateZ "0.00 6000.00 8000.00 9000.00"`, `LabelX "A B C D E"`, `LabelY "1 2 3 4 5 6"`, `LabelZ "+0 +6000 +8000 +9000"`.
  The `n*d` syntax is therefore usable from the API, and levels are labelled like `+6000`.
  Whether the API grid uses the same relative/absolute interpretation as the UI is **unverified** (not stated on the page).

**Creating grids from a DWG/IFC reference:**

| Route | What the source says | Limit |
|---|---|---|
| Manual from reading | Enter coordinate strings in the property pane (above) | Needs spacings from the extractor (X/Y as spacings, Z absolute) |
| Insert a 2D DWG as reference and adjust the Tekla grid lines to match it | Video page, versions 2021/2018i: "importing a 2D reference drawing ... as an overlay to adjust the Tekla grid lines" (S37) | Manual; no written steps on the page |
| `Grid From Parts` (Warehouse extension) | Builds a grid from existing columns/beams, also from selected IFC objects: intersection at each vertical member, elevations at member ends/tops; first grid A/1 starts at the bottom-most, left-most column; sloping members get no lines; "Get From All" works only for native members; no licence/edition stated (S11) | Needs members to exist first; derives grid from members, not from reference grid lines; page lists Default environment, v21.1/2016 era |
| IFC reference + manual | Reference-model grids "might be different from the one in the model" (community guide, secondary; not used as a rule) | - |
| Import building storeys/spaces from IFC | Possible "when both the reference model and the Tekla Structures model contain one building each" (S3 p.128) | Levels as Building hierarchy storeys, not grid planes |
| Tekla Structural Designer DXF grid import | Appeared in search only; different product (**unverified**) | - |
| DWG/DXF import tool | Creates construction lines or part profiles, no surfaces (S6) | Does not create grid objects |

**No built-in command that turns DWG/DXF grid lines into a Tekla grid object was found** (searched support.tekla.com for
"create grid from reference model / DWG / IFC", Warehouse grid extensions). Conclusion for the harness: extract grids
deterministically from the DWG (the harness already plans `grids.json`), have the engineer confirm, then create the
grid through `Grid.Insert()` or the UI from coordinate strings.

## 3. Reference models and conversion paths

* **Insert**: `File` -> `Import` -> `Insert reference model` (or `Reference models` side pane -> `Add model`). Location by
  `Model origin`, `Work plane` or `Base point` (from Project properties); offset; scale (for DWG/DXF "define the measurement
  unit in AutoCAD and save the file", then Tekla scales correctly); rotation around Z; group, phase, title. Data is copied to
  `datastorage\ref`. Do not delete and re-insert to update: use change detection. Avoid inserting far from the origin; use a base point. (S5)
* **Formats** (S4, 2025): `.dwg`, `.dxf` ("supported version ACAD2023 and earlier"), `.ifc/.ifczip/.ifcxml`, SketchUp (2021
  and earlier), IGES, LandXML, MicroStation, PDF, STEP, TrimBIM, others. Files are converted by TrimBimConverter to `.trb`
  stored in the model folder; a reference cache is created. The page states **no licence/edition requirement**.
* **DWG pitfalls**: a DWG with AutoCAD proxy objects can show nothing; fixes include exploding proxies or `DXFOUT` to R12 DXF
  (S12). The version table is in S7 (`AC1032` = 2018-2023, `AC1027` = 2013-2017, ...). Clash check is not possible with DXF
  files because DXF has no part ID (S7); S1 p.715 lists DWG as supported in clash check.
* **DWG/DXF import tool** (`File` -> `Import` -> `DWG/DXF`, S6): converts 2D/3D objects to *construction lines* (`Reference
  lines`) or *parts* with a plate/beam profile ("only metric profiles"); `Use 2D import` for flat input. Limits: a profile must
  be the only object in the file, a closed polyline; no surfaces; "not available in all Tekla Structures configurations"
  (the configuration list was not found: **unverified** which editions).
* **Convert IFC objects** (S8, 2025): `File` -> `Settings` -> `IFC object conversion settings`; command `Convert IFC objects`
  on the `Manage` tab, or conversion *change management*. Converts most linear objects (beams, columns, braces, plates, slabs,
  footings, walls) either as an *extrusion* (part with extruded profile) or an *item* (3D shape). Profile mapping by "Profile
  name" or "Dimensions" (fallback to the other); `Check` shows `Missing Profiles`/`Missing Materials`; mapping files
  `TeklaStructuresCatalogProfiles.txt`, `TeklaStructuresCatalogMaterials.txt`, `MappedProfiles-default.txt`,
  `MappedMaterials-default.txt` in the model's attributes folder. Converted objects get class 990-996 (990 parametric with
  name ... 996 B-rep via `Convert B-rep object`). Limits: native profiles need IFC2x3 Coordination view 2.0, otherwise items;
  bolts, reinforcement, welds are not converted; only SweptSolid/Brep/CSG/Clipping; chamfers and profile offsets may convert wrongly.
  IFC4 conversion: unsupported in 2025 (S8) but supported from 2026 (S9). **There is no IFC input from 2D drawings**: both
  paths need a model, not drawings.
* **Relevance to MCS**: the input is 2D DWG. Tekla offers no official "2D drawing to 3D model" conversion; DWG is a tracing
  aid (S1 p.478 "model by tracing over the reference model") or a source for lines. Searched: "convert 2D drawing to 3D
  model Tekla", Warehouse grid/DWG extensions; third-party Warehouse tools were not assessed (not first-party docs).

## 4. Profile catalog and name syntax

* Two profile kinds: **fixed** (pre-manufactured, "environment-specific") and **parametric** (predefined shape, user-set
  dimensions). Profile can be typed directly in the `Profile` box if you know the name; otherwise `Select Profile` dialog;
  by default only profile types matching the part's material are shown. "Use industry standardized values only" restricts
  parametric dimensions. (S1 p.322-324)
* **Syntax of parametric names**: prefix plus dimensions joined by `*` or `-`. Printed in S1 p.992-1001, e.g. `Lh*b*t`, `Uh*b*t`,
  `Ch*b*t`, `Th-s-t-b`, `HIh-s-t*b`, `Dd`, `Ph*t`, `Ph*b*t`, `B_WLD_A h*b*s*t`, `HKh-s-t*b-c`. The plate form is printed as `PLh*b` with
  "h=height, b=thickness (smaller=b)". Examples of real values appear only in passing: `PL200*20`, `BL200*20` (S1 p.236,
  p.190), `HEA400` (S35), wildcard `HE?400` and `IPE*`/`HEA*` (S1 p.194, p.671). **Parameter order of `PL` and `BL`
  must not be guessed from the drawing callout**: `profitab.inp` has a sorting-order setting whose example shows both
  `PLT200*10` and `PLT10*200` normalise to one form depending on setting (S2 p.299).
* **How a parametric prefix is defined** (`profitab.inp`, S2 p.298-299): one row per prefix,
  `Prefix ! Type ! SO ! Z ! MI ! MA ! G3-NAME ! Z3-NAME !`, e.g. `PNL_A ! USER ! 0 ! ! 2 ! 3 !1Gen.RectChamfer !h*b-[c]`.
  `MI`/`MA` = min/max number of parameters; `Z` = unit (0 mm, 1 inch, 2 feet, 3 cm, 4 m). Cross-section files are `.clb`.
* **Catalog files**: `profdb.bin` (profiles), `profitab.inp` (parametric names), `matdb.bin` (materials), `rebar_database.inp`,
  `mesh_database.inp`, `screwdb.db`, `assdb.db`, `.cnv` conversion files, under `Environments\<env>\profil` (S2 p.74-76).
  Two catalogs exist: the *original* and the *new profile catalog* (groups instead of rules; switch with
  `XS_USE_OLD_PROFILE_CATALOG`). In the new catalog "the profile name must be unique and must not contain spaces" (S17).
  Rules/groups are read top to bottom and use wildcards (S16).
* **Environment dependence**: fixed profiles are environment-specific (S1 p.322); a blank-project environment has no profiles
  (S20). "Illegal profile" in Diagnose means the environment or the model's own `profdb.bin`/`profitab.inp` differ (S1 p.730).
* **Mapping a drawing callout to a catalog name**: *no built-in feature maps free-text drawing callouts to profile names*
  (searched profile mapping, conversion, `profdb`). What exists: (a) IFC-conversion mapping files and `Check` (above);
  (b) `prfexp_<software>.cnv` which converts profile names *on export* ("HEA100 to HE100A for DSTV", S2 p.75); (c) material
  aliases (section 5). So the harness's own `profile_map` (workflow step 9) stays necessary, and `tekla-cli validate`
  should check every mapped name against the open model's catalog. Whether a name resolves can only be known in the installed environment.
* **Standard shapes**: `HEA`, `IPE` appear as prefixes in examples; US `W` shapes, Vietnamese/JIS/Chinese shape naming
  and Vietnamese cold-formed (`C`, `Z`) naming were **not read on any page**: **unverified**. Export an actual catalog
  (`File` -> `Catalogs` -> `Profile catalog`, `Export`) from the company environment to get the truth.
* Part `Name` max 61 characters (S1 p.213, p.216). `Finish` is free text.

## 5. Material catalog, grades, rebar grades, environments

* Material types: Steel, Concrete, Timber, Miscellaneous (cannot be added or changed); stored in `matdb.bin`. Grades can be
  added/copied/modified; each grade has **three alternative names** (the General tab) and "Show aliases" in `Select
  Material` converts an alias to the standard name when chosen. A modified catalog is saved in the model folder and applies to
  that model only unless exported/imported. (S2 p.262-265, S1 p.324-325)
* Rebar: separate **rebar catalog** (`rebar_database.inp`, per environment, default saved in the model folder); `Grade` and
  `Size` are mandatory fields; meshes in `mesh_database.inp`; in the blank environment bars are "undefined". (S2 p.376-377)
  Rebar grade is part of "identical reinforcement" for numbering (S1 p.739).
* Material-name conversion for exports uses `matexp_<software>.cnv` (e.g. `S235JR` to `FE360B` for DSTV, S2 p.75).
* **Environments**: an environment defines materials, grades, profiles, drawing/component settings, and `.ini` settings for
  a locale (S19). Only "Blank" is named on S18/S19. The localization release notes (S21, 2026) list four environments
  (France, Finland, US, Switzerland) and say nothing about Asia. Search snippets mentioned "India" and "South-East Asia"
  environments from a legacy taxonomy page that did not load: **unverified**.
* **Is there a Vietnam environment? Not found on any Tekla page read** (searched: environment lists, localization notes,
  Warehouse, "Vietnam"/"TCVN"). **Open question for MCS**: which environment and role do they run, which Tekla version,
  and can they export their profile and material catalogs and `objects.inp`? What Vietnamese detailers typically use is
  **unverified** (no first-party source).

## 6. Classes, names, numbering, phases, lots, Organizer, sequencing

* **Class**: groups parts; colour by class when Object representation uses `Color by class`. Range 0-14 gives distinct colours;
  above 14 repeats 1-14 (S1 p.671-672). **Class does not affect numbering** (S1 p.738). IFC conversion reserves 990-996 (S8).
  The spec's `^[0-9]{1,3}$` allows 990-996: avoid them for harness classes.
* **Numbering series** = prefix + start number (e.g. `P` + 1001 gives P1001, P1002...). Parts and assemblies have separate
  series; set in part properties (`Numbering series`) or assembly properties; concrete cast units use the `Cast unit` section.
  Official planning table: Beam PB/AB, Vertical brace PVB/AVB, Horizontal brace PHB/AHB, Rafter PR/AR, Purlin PP/AP, Column
  PC/AC, Plate (no prefix, assign a start number). Use wide, non-overlapping start numbers (floor 1 = 1000, floor 2 = 2000);
  overlapping series leave one object unnumbered; plan before modelling; do not change conventions mid-project. (S1 p.734-737, p.741)
* **Identical parts** get the same number when geometry (within tolerance), casting direction, series, profile, material,
  finish and shortening match. Optional extra criteria in `Numbering Setup`: part name, orientation, assembly name, assembly
  phase, reinforcement, etc.; UDAs with `special_flag yes` also split numbers. (S1 p.738-740)
* **Running numbering**: `Number modified objects` or `Number series of selected objects` -> `Numbering preview` -> `Assign
  numbers`; recommended: split by area/phase and object type. (S1 p.748-749). Control numbers can encode an erection order
  (S1 p.764-770, 6-wall example).
* **Phases**: `Manage` -> `Phases`; objects take the *current* phase; phases can be locked, used in views, reports and copying
  between models, and optionally in numbering (`XS_ENABLE_PHASE_OPTION_IN_NUMBERING`). (S3 p.164-166, S1 p.740)
* **Tekla "Lotting" is a different concept from a harness lot**: it groups *assemblies for transport*, with a lot number,
  name and max weight; a part belongs to one lot only; template attributes `LOT_NUMBER`/`LOT_NAME`. (S3 p.167-169, S25).
  The extension "Phases and lots to tasks" turns phases/lots into Task Manager tasks and needs GA drawings and the Full or
  Construction Management configuration (S22). Name clash risk with the harness term "lot" and UDA `LOT` (section 9).
* **Organizer**: location categories (project/site/building/section/floor via boundary boxes, can use a grid), property
  categories (UDA values), custom categories (rules). An "uncategorized" category catches the rest. Location data is written
  only to the highest-level assemblies. Tekla says numbering "is not just another way of classifying parts. To classify,
  use Organizer, user-defined attributes, or colors" (S3 p.35-37, S1 p.777).
* **Building hierarchy**: project > site > building > section > storey > space, follows IFC spatial structure; storeys are
  horizontal planes at an elevation, objects assigned by centre point (columns by bottom-edge centre). (S3 p.128-131)
* **Sequencer** (erection order): integer UDA in `objects.inp` Part attributes, sequence name equals UDA name; parts are
  clicked in order; one part can be in several sequences; does not work on reference-model objects. (S23, S3 p.170-172)
* **Task Manager**: tasks with dates, linked to objects, dependencies without cycles, object order per task (`2-1` = second
  task, first object), import/export of Primavera/MS Project schedules; configuration/licence availability not stated (S26, S3 p.139-163).

## 7. Concrete: parts, pours, reinforcement

* Concrete parts: column, beam, polybeam, spiral beam, panel/wall, slab, lofted slab, pad footing, strip footing; also
  steel parts and `items`. Each modelled concrete part is its own cast unit; several parts are merged with `Create cast
  unit`. Cast unit type must be `Cast in place` or `Precast` (numbering and pours depend on it). Cast unit main part =
  largest concrete volume. (S1 p.211, p.440-442)
* **Pour management** is a cast-in-place feature, off by default in new models in most roles, enabled with advanced option
  `XS_ENABLE_POUR_MANAGEMENT` (reopen model; do not disable mid-project). Terms: *pour object* (touching cast-in-place parts
  with same grade and pour phase merged), *pour unit* (pour object + reinforcement, embeds, bolts), *pour* (group poured at
  once), *pour break* (splits a pour object). Pour phase 0/1 example splits horizontal and vertical structures; `Calculate
  pour units` fills pour units; precast cast units must be added manually. Pour management is "mainly targeted at
  contractors for quantity take-off, planning, and on-site activities". (S1 p.454-478)
* **Reinforcement** methods: reinforcement components ("recommend ... whenever possible"; adaptive), **rebar sets** (adaptive,
  attached to a part or pour object), **single bar**, **bar group**, **Rebar shape catalog**, meshes, strands, splices,
  rebar assemblies. Shapes are recognised via **Rebar shape manager** (`RebarShapeRules.xml`) or hard-coded types mapped in
  `rebar_schedule_config.inp`; unknown shapes become `UNKNOWN`. Cover thickness, hooks, layers, running numbers are modelled
  properties. (S1 p.479-620)
* Identical rebar numbers depend on bar geometry, series, size, grade and bending radius (S1 p.739). Rebar can change cast-unit
  numbering when `Reinforcing bars` is ticked in numbering setup (S1 p.749).
* **What is normally modelled vs left to 2D drawings**: *not found* in Tekla sources (searched: Create models, precast
  tutorial index, workflow pages). Practice-level only: rebar is usually the last and most error-prone layer; a first harness
  version should stop at concrete geometry, cast unit type, pour phase, then treat rebar as a separate, later phase
  (**unverified as industry practice**).

## 8. Common steel connection components

Names and numbers below are exactly as printed on the pages (raw HTML grep; some numbers repeat across different names, so
**always identify a component by name and number together and confirm it in the target environment**, because the component
set differs by environment and version).

* Shear tab (S27, 2025): `Shear plate simple (35)`, `Shear plate simple (146)`, `Shear plate (34)`, `Shear plate (103)`, `Welded tee (32)`,
  `Stiffened shear plate (17)`, `Full depth shear plate (81)`, `Column with shear plate (131)`, `Two sided shear plate (118)`.
* End plate (S28, 2026): `End plate (29)`, `End plate (101)`, `End plate (144)`, `Simple end plate (32)`, `Stiffened end plate (27)`,
  `Two sided end plate (24)`, `Two sided end plate (115)`, `Two sided end plate (142)`, `End plate detail (1002)`, `Connection plate (1026)`.
* Moment (S30, 2025): `Moment connection (130)`, `Bolted moment connection (134)`, `Moment connection (181)`.
* Base plate (S29, 2026): `Simple base plate (55)`, `U.S. Base plate connection (71)`, `Base plate (1004)`, `Stiffened base plate (1014)`,
  `Web stiffened base plate (1016)`, `Simple base plate 2 (1031)`, `Base plate (1042)`, `Circular base plates (1052)`, `Box column base plate (1066)`.
* Bracing (S31, 2025): `Std bracing connection (67)`, `Welded gusset (10)`, `Bolted gusset (11)`, `Bracing cross (19)`, `Tube gusset (20)`,
  `Tube crossing (22)`, `Portal bracing (105)`, `Central gusset (169)`, `Bolted gusset (196)`. `Bolted gusset (11)` connects 1 to 10 braces
  (page title confirmed in 2026 HTML; selection order: main part first, then each brace).
* `Two sided clip angle (143)` appears as the example dialog in S1 p.782; clip-angle, seated and splice categories were not listed here.
* **How components work** (S1 p.780-783): connection components connect two or more parts and create cuts, fittings, parts,
  bolts and welds; detail components add to one part (base plates); detailing components create assemblies (stairs, frames).
  They adapt when parts change and move/copy with their parts. Property values come from manual entry, AutoDefaults, automatic
  options or `joints.def`. Create order: pick the main part, then secondary parts, via the dialog's `Create`.
* **AutoConnection** applies rule groups per *framing condition* (e.g. beam to beam web/flange), "individually, in phases, or
  project-wide"; Tekla recommends building a test model with all connection conditions first (S1 p.803-804). `Connection
  code` UDA can feed these rules (S1 p.343).
* **Components vs manual plates**: Tekla gives no explicit decision rule. Supported reasons to prefer a component: it creates
  all related objects, adapts to model changes, and can be applied by rule (cited above). Manual plates/custom components
  are the route when no system component fits (S1 p.781, p.845). Which components exist in MCS's environment and how
  `Component` insertion works in the Open API were **not researched**: **unverified**; the harness spec currently has no
  connection object.

## 9. User-defined attributes (UDAs)

* Defined in `objects.inp` text files. Create your own in the **model, project or firm** folder; "Do not copy the global
  `objects.inp` files" in `..\environments\common\inp\` (updates can be lost). Read order: model, project (`XS_PROJECT`), firm
  (`XS_FIRM`), system (`XS_SYSTEM`), inp (`XS_INP`); on a duplicate name the first file read wins. Use suffixes such as
  `objects_harness.inp` to keep several files in one folder. (S13, S2 p.144-146)
* **Name rules**: unique; max **19 characters** (only the first 19 are compared); case-sensitive; no spaces or reserved
  characters; project-specific names should use the `P_` prefix; a UDA must have one definition for all object types; do not
  change the definition of an existing UDA, create a new one. (S13)
* **Definition fields** (S14): `attribute` (copyable) or `unique_attribute` (non-copyable); `attribute_name`; `label_text`;
  `value_type` (`string`, `integer`, `float`, `option`, `date`, ...); `field_format` (`%s`/`%d`); `special_flag` (`yes`/`no`:
  for parts, whether the attribute affects numbering); `value("...", 2)` = default not stored in database (recommended).
  `string` max **79 characters** in S14 vs **255** in S15 (see "Where sources disagree").
* **Applying a new/changed definition to an existing model**: `File` -> `Diagnose & repair` -> `Diagnose and change attribute
  definitions`. Definitions are merged into `environment.db`; on conflict the `environment.db` copy wins. (S13)
* **Harness implications (proposals, not decisions):**
  * `LOT`, `RUN_ID`, `SPEC_ID` fit the 19-character limit but do not follow the `P_` recommendation; whether they already exist in the
    installed global `objects*.inp` was **not checked** (no install access): grep the environment `inp` folder, closes the open
    question in `docs/tekla-cli-contract.md`.
  * Set `special_flag` to `no` on all three: with `yes`, differing `SPEC_ID` values would force otherwise identical parts to
    receive different position numbers (S1 p.740).
  * `unique_attribute` for `SPEC_ID`/`RUN_ID` would stop copies from inheriting tags (S14); decide with the engineer.
  * Tekla's own Lotting feature uses "lot" for transport batches. Whether it stores membership in a UDA named like `LOT` is
    **unverified**; consider `P_LOT`-style names or `HLOT` to avoid confusion with S25.
  * Open API: `ModelObject.SetUserProperty(string, double|int|string)` and, since 2023, `SetUserProperties` exist (S36;
    the 2023 release note was seen only as a search snippet). Whether setting a UDA not defined in `objects.inp` is silently
    ignored and whether it must follow `Insert()` is **unverified** (only a blog claims "insert first").

## 10. Model quality checks and change management

* **Clash Check Manager** (S1 p.714-725): finds collisions and too-close objects within native models, within reference models and
  between them; clearances configurable; "you can also use the sections and floors created in Organizer to run a controlled
  clash check". Reference formats allowed: IFC, IFC4, DWG, DGN, SKP, `.tekla` (not DXF). Results can be saved and printed.
* **Numbering checks**: `Numbering preview` shows proposed numbers and overlaps before `Assign numbers`; numbering history log;
  question mark `?` on labels means numbering out of date (S1 p.734, p.751-760). Overlapping series are warned about (p.737).
* **Diagnose & repair** (S1 p.729-730): `File` -> `Diagnose & repair` -> diagnose commands; detects empty assemblies, parts not
  in any assembly, illegal profile/material/bolt/rebar size or grade (usually wrong environment or catalog files), solid
  errors (also in the session history log as "Solid error"), and updates UDA definitions (section 9).
* **Compare parts/assemblies**: `Edit` -> `Compare` -> `Compare parts`/`Compare assemblies` reports whether two objects get the
  same number and why not (S1 p.726-727).
* **Inquire / part labels / custom inquiry** to read properties and UDAs; `Model search` (S1 p.681, p.705, p.727).
* **Reference-model change detection** (S32, 2024): compares two stored versions of an IFC-based reference model (or Tekla
  models exported to IFC at least twice) at object level with statuses Changed/Unchanged/Inserted/Deleted, a comparison set,
  Excel export, old vs new values. Only two versions at a time. A cited mechanism for verifying a lot is therefore: export
  IFC after each lot (the harness `verifier` already exports IFC), insert as reference, compare with the previous export.
  Whether this works smoothly for harness-created native objects was not tested: **unverified**.
* **Protecting approved lots**: Phase Manager can lock parts, bolts, welds and reference models by phase; locked objects
  cannot be modified or deleted, only non-numbering UDAs change; assemblies, cast units and pour units are not locked this
  way (S3 p.165, S24). Phase-per-lot would make this possible (proposal).
* **Model Sharing / multi-user**: relevant to pours (re-enable pour management before write-out) but not researched further.

## 11. Implications for an optimal lot sequence

Status: **cited** = a source states it; **example** = a source shows it as an example only; **practice** = engineering
practice not stated by Tekla; **proposal** = harness design decision for the engineer to approve.

| # | Rule | Basis | Status |
|---|---|---|---|
| 1 | Lot 0 = environment check, units, base point, grid and levels, views; engineer confirms grid/levels before any member | S1 p.19-20 setup order; engineer gate is the harness's own (workflow "mandatory section" of gate 1) | cited + proposal. **Gap**: `spec.schema.json` and the `tekla-cli` contract have no grid/level object or command |
| 2 | Decide numbering prefixes/start numbers, class and material defaults before the first member; write them into default part properties | S1 p.735, p.777 | cited. **Gap**: lot spec has no prefix/start-number field |
| 3 | Validate catalogs first: every profile, material, component name must exist in the open environment (`tekla-cli validate`) | S1 p.730 "Illegal profile/material"; S8 mapping `Check` | cited |
| 4 | Columns (and footings/base plates) before beams | S3 p.164 (columns = phase 1 example) | example; load-path logic is practice |
| 5 | Then primary beams/rafters, bracing, secondary steel (purlins, girts) | none from Tekla | practice, unverified |
| 6 | Connections after the members they join; use components by framing condition, test on a sample model | S1 p.783, p.803 | cited |
| 7 | Prefer modelling a typical bay/floor once and copying | S1 p.208 | cited (copy is not a `tekla-cli` command: proposal) |
| 8 | Concrete order: reference/convert -> geometry -> cast unit type -> pour phase -> pour objects/breaks -> pour sequence -> rebar -> GA | S1 p.477-479 | cited |
| 9 | Precast: foundations, walls, columns/beams, slabs, stairs, cuts/blockouts, rebar; model left to right, bottom to top | S33; S1 p.442 | example (tutorial) + cited (direction) |
| 10 | Modelling order is not erection order: erection sequence is assigned afterwards with Sequencer/Task Manager/phases | S23, S26, S24 | cited (separate tools) |
| 11 | Number last per lot or zone, never the whole model at once; preview before assign; before fabrication drawings, not before GA | S1 p.733, p.748, p.207 | cited |
| 12 | Check each lot: numbering preview, clash check (use Organizer floors/sections), Diagnose model, IFC export + change detection | section 10 | cited |
| 13 | Keep coordinates small near the origin; use base points for site coordinates | S1 p.206, base points section | cited (affects doc-reader mm output) |
| 14 | Keep harness classes out of 990-996; remember colours repeat every 14 | S8, S1 p.672 | cited |
| 15 | Harness UDAs: `special_flag no`, <=19 chars, new names, applied via Diagnose & repair; avoid confusion with Tekla Lotting | S13, S14, S25 | cited + proposal |
| 16 | Map harness lot -> Tekla phase (and lock approved phases) so engineer-approved lots cannot be edited by accident | S24 lock; harness lot mapping | proposal |
| 17 | One lot should stay small enough for the engineer's 3D check and not exceed practical pour/numbering sizes (too many parts in one pour object slows the model) | S1 p.461 | cited (pours); lot size is practice |

## Where sources disagree

| Topic | Source A | Source B | Handling |
|---|---|---|---|
| IFC4 in IFC object conversion | S8 (2025): IFC4.0/4.1 and newer "not supported" | S9 (2026): "IFC4.0 format and any newer IFC4 formats are now supported" | Depends on version; S10 (2025) says IFC4 can be *inserted* |
| UDA string value length | S14 (2026): `string` max 79 characters | S15: 255 characters; 79 only up to 2023 SP7; option values 60 (from 2023 SP3) | S15 is the newer, version-qualified statement; confirm in installed version |
| UDA name length | 19 characters (S13, S14, S15) | IFC property-copy table: UDA name max 20 characters, must exist in `objects.inp` (S8) | Use 19 |
| DWG/DXF version | Older pages: ACAD2012 (search snippet of 2020 page) | S4/S7: ACAD2023 and earlier | Use the installed version's page |
| Material types | Search snippet: "reinforcing bar type no longer available from 2021" | S2 p.262 lists Steel, Concrete, Timber, Miscellaneous | Use S2 |
| Profile mapping in/out | `prfexp_*.cnv` maps names on export only | Import side: only IFC `MappedProfiles-default.txt` found | No general import mapping |
| Shear tab list (fetch summary vs raw HTML) | WebFetch lists differed in 3 names | Raw HTML (S27) | Raw HTML used |

## Open questions and gaps (biggest first)

1. Tekla version, environment, role of MCS; whether a Vietnam/Asia environment exists; export of their catalogs and `objects.inp`.
2. Profile name syntax for the company catalog (HEA/IPE/W/JIS/cold-formed, plate order `PL`): only generic syntax verified.
3. Order within steel (beams, bracing, secondary) and typical rebar modelling scope: not found in Tekla sources.
4. Edition/licence requirement of DWG/DXF import and `Convert IFC objects`: pages only say "not available in all configurations".
5. Open API specifics for components, UDA set-before-insert, work-plane assumptions: not read.
6. Uptake of `LOT` UDA vs Tekla Lotting: unverified.
7. Third-party Warehouse tools for DWG-to-model were not assessed (not first-party documentation).
