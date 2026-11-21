# Single-storey steel industrial building (portal frame / PEB on RC pile foundations): drawing set, bases, Tekla components

Retrieved 2026-11-19. Purpose: ground the `structural-drawing-reader` skill for a portal-frame or pre-engineered
building (PEB) steel superstructure on reinforced-concrete pile foundations, so a Tekla Structures model can be built
without guessing. Each fact is meant to become a rule (only if verified) or a question to the engineer (if not).
This file changes no skill, schema or rule (AGENTS.md principle 7). Target Tekla version: 2026.

## How to read this file

- **Grades**: A = standards body, institute, ministry draft, or Tekla/Trimble first-party documentation;
  B = manufacturer technical document; C = sales sheet, blog, trade page, search snippet.
- **Evidence route** (shown in the Verified column):
  - **verified (PDF)** = I downloaded the PDF, extracted the text and read the sentence or figure label.
  - **verified (HTML)** = I downloaded the raw HTML page and found the string.
  - **verified (fetch)** = read through WebFetch, which returns a model-written summary of the page, not the raw text.
    Likely correct, not exact. Do not copy strings from it into a rule without re-checking.
  - **unverified** = search snippet only, my own inference, or not found.
- Everything downloaded was treated as untrusted data, kept in the session scratchpad, and only read, never executed.
  No page contained instructions I acted on.
- Numeric design values (bolt counts, thicknesses, laps, depths) appear only as "what to look for", never as rules.
- Caveat on origin: P252 is a UK/BS 5950 publication (2004). Nucor and the sample set are US manufacturers (imperial
  units, AISC/MBMA practice). The Vietnamese standard is a draft. No Vietnamese PEB manufacturer set was found.

## 1. Anatomy of a portal-frame / PEB building

| Claim | What the reader looks for on the drawing | Src | Verified |
|---|---|---|---|
| A portal frame is columns and horizontal or pitched rafters joined by moment-resisting connections; a portal building is a series of unbraced transverse frames braced longitudinally | Frame cross-section sheet with one frame line repeated at the bay spacing; bracing only in longitudinal bays | S2, S3 | verified (fetch) |
| The major connections are the eaves and apex connections, both moment-resisting | Bolted end-plate or splice at knee and ridge; the frame is not pinned at these two points | S2, S1 3.13 | verified (fetch) / verified (PDF) |
| Eaves haunch: cut from a hot-rolled section or fabricated from plate; apex haunch usually fabricated from plates | Deepened section under the rafter at the column; apex splice plates | S1 3.4, 3.5 | verified (PDF) |
| "Depth of the haunch" has at least three meanings (from rafter/column centre-line intersection, from rafter underside, from rafter top); length may be from centre-line or column face | A dimension line on the haunch: check which datum it starts from before using it | S1 3.2 | verified (PDF) |
| PEB primary members: columns, rafters and canopy beams are shop-welded built-up I shapes, constant depth or tapered, with base plates, clips and splice plates for a fully field-bolted assembly | Member marks on the frame sheet with start and end depth; splice locations; flange and web plate sizes | S4 5.2.1 | verified (PDF) |
| "Primary" = members that carry loads to the foundation; "secondary" = purlins, girts, struts, bracing, beams carrying cladding load to the primary frame | Sheet titles and member legend: primary frame vs roof/wall framing | S4 5.1.1, 5.1.2 | verified (PDF) |
| Hot-rolled vs tapered built-up is a manufacturer/designer choice; no source gives a rule for which applies | Section designation text on the frame sheet (see section 4) | S1, S4 | unverified (as a rule) |
| End-wall (gable) frames may be posts with simply-supported rafters rather than a portal frame; posts span from foundation to the roof plan bracing | Smaller columns at close spacing on the end elevation; rafter on top of posts | S1 2.11 | verified (PDF) |
| PEB end-wall columns and rafters may be built-up I, WF or roll-formed C | End-wall frame sheet (the sample set labels it "Endwall") | S4 5.2.1, S6 | verified (PDF) |
| The term "wind post" was not found on the pages read; the pages say "gable posts" / "gable frames" | Treat "wind post" as an engineer-confirmed synonym only | S3 | unverified |
| Purlins and girts (side rails) are roll-formed Z or C sections, simple-span or continuous; UK practice has purlins continuous over rafters | Purlin plan with lap/continuity notes; Z or C mark and thickness | S4 5.3.1, S1 3.15 | verified (PDF) |
| Eave strut: PEB = roll- or brake-formed C section; UK = hot-rolled or hollow section between column flanges | Member at eaves level on the roof plan and side elevation | S4 5.3.3, S1 3.10 | verified (PDF), sources differ (section 7) |
| Eaves beam (UK term) is usually cold-formed and supports sheeting, walls and gutter; an eaves beam strut stops it twisting | A cold-formed member at the eaves with a short strut to the first purlin | S1 3.11, 3.12 | verified (PDF) |
| Sag rods / sag bars and diagonal ties exist as labelled items on the UK typical-details figure | Thin rods between purlins or girts on the roof plan and side elevation | S1 Fig 3.1 | verified (PDF) (figure labels only) |
| Flange braces (PEB): angle bracing from the web of a purlin or girt to the compression flange of the primary member; UK equivalent is column and rafter stays | Short angle at an angle to the frame flange near purlin/girt level | S4 5.3.5, S1 3.7 | verified (PDF) |
| Bracing: roof (plan) bracing and wall (vertical) bracing; wind portal frames replace diagonals where openings are large | Cross marks in bays at the building ends on roof and wall elevations; "X Brace" labels in the sample set | S1 3.9, S6 | verified (PDF) |
| Wind bracing in PEB is diagonal cable, rod or angle; cable and rod are adjustable, angle is not | Bracing legend: cable/rod/angle symbol, eyebolt or threaded end | S4 5.3.4 | verified (PDF) |
| Plan bracing should connect to the top of the gable posts; the eaves strut carries roof-bracing force to wall bracing | Roof plan: bracing bay at the end, strut along the eaves | S3, S2 | verified (fetch) |
| Light crane (up to about 20 t, UK): brackets on columns carry the crane rails; ties or rigid bases may be used to limit frame spread | Bracket or corbel on the column; crane data note; tie at eaves | S1 2.4 | verified (PDF) |
| Vendor catalogue of top-running crane details: runway beam to bracket, runway beam to column bracing (braced and unbraced bay), double bracket, auxiliary column, stepped column, crane stop, hook bolt, floating rail clamp, monorail | Crane detail sheet titles of this kind | S5 | verified (PDF) (titles only) |
| Canopy beams are built-up I shapes in the PEB spec; framed openings carry jamb/header framing and are listed in an accessory schedule | Accessory schedule with opening size and quantity; canopy on frame sheet | S4 5.2.1, S6 | verified (PDF) |
| PEB wall panels need a base angle, base angle flash or base girt fixed to concrete by the contractor | Base angle on the wall elevation / slab edge detail | S4 5.3.6 | verified (PDF) |
| Mezzanine framing, floor beams and columns | No source opened | none | unverified |
| Dimension terms (PEB): width = steel line to steel line of sidewall girts; length similar; eave height = finished floor to top of eave strut or purlin at the steel line; bay = frame centre to frame centre | The dimensions on the plan and cross-section: "steel line", "out/out of steel" | S4 1.2, S6 | verified (PDF) |

Vietnamese terms (only those I saw in a Vietnamese standard text; the TCVN draft is the vocabulary source here):

| Term in the text | English meaning | Where seen | Src | Verified |
|---|---|---|---|---|
| khung ngang, cột khung, xà ngang dạng giàn hoặc tiết diện bụng đặc | transverse frame, frame column, rafter/beam as truss or solid web | cl. 4.2.6 | S7 | verified (PDF) |
| hệ giằng (giữa các cột và các giàn), giằng đứng | bracing system, vertical bracing | cl. 4.2.6, 15.4 | S7 | verified (PDF) |
| xà gồ mái | roof purlin | cl. 4.2.6 | S7 | verified (PDF) |
| vì kèo (giàn đỡ vì kèo) | roof truss (supporting trusses) | cl. 4.2.6 | S7 | verified (PDF) |
| kết cấu đỡ cầu trục; dầm đỡ cầu trục | crane-supporting structure; crane runway beam | cl. 4.2.6, 15.6 | S7 | verified (PDF) |
| bu lông neo (chữ L, có bản neo, thẳng, đầu côn) | anchor bolt (L-shaped, with anchor plate, straight, conical head) | App. I.2.1 | S7 | verified (PDF) |
| bản đế, chân cột | base plate, column foot | cl. 8.6 | S7 | verified (PDF) |
| đài cọc (đài cao, đài thấp) | pile cap (high, low) | cl. 3.13 | S8 | verified (PDF) |
| "kèo" alone = rafter, "xà gồ tường" = girt, "dầm cầu trục" (without "đỡ"), "bản mã chân cột", "cổ cột", "giằng móng", "vữa không co" | rafter, girt, runway beam, base plate, pedestal, tie beam, non-shrink grout | not in a source I opened | none | unverified (search tool's own translation or trade usage) |

## 2. The usual drawing set and reading order

| Claim | What the reader looks for on the drawing | Src | Verified |
|---|---|---|---|
| A PEB manufacturer issues: anchor bolt drawings and reactions, final erection drawings, approval drawings on specified jobs, permit drawings on request | Sheet-set index; drawing status stamp (preliminary / approval / construction / erector) | S4 4.1.1-4.1.3 | verified (PDF) |
| Permit drawings show engineering design details, critical clearances, key connections, material specifications and lateral-force elements (bracing, diaphragm, shear wall layouts) | The sheet that shows where bracing is allowed to go | S4 4.1.2 | verified (PDF) |
| This manufacturer does not supply shop fabrication drawings, as-built drawings or electronic drawing files | Absence of shop drawings: the modeller will have to detail connections | S4 4.1.4, 4.1.6 | verified (PDF) |
| Sample manufacturer set (preliminary, sales only, not for construction, imperial): anchor rod plan with rod diameter/quantity table; reaction tables per frame line; anchor-rod section details per base type; cross-section at frame lines; structural and architectural elevations of all four walls; accessory schedule | The same sheet types in a real set; sheet numbering such as "F1 of 4" | S6 | verified (PDF) (a sales set, not construction information) |
| Anchor rod plan: gives out/out of steel, bay dimensions, base types A/B/C/D per column, finished-floor elevation, and notes | Column marks linked to base detail letters | S6 | verified (PDF) |
| Reaction sheets: per frame, columns on gridlines, load groups, components labelled H, V, L; units stated | Table per frame line (end-wall and interior frames separately) | S6 | verified (PDF) |
| Frame cross-section: eave height, widths out/out of steel, clearances referred to finished-floor elevation; clearances "approximate" until final design | Cross-section with haunch and apex geometry, slope as rise per 12 | S6 | verified (PDF) |
| UK typical-details figure shows three views: cross-section with restraints, roof steelwork plan, side elevation | Same three views in a design set | S1 Fig 3.1 | verified (PDF) |
| Roof framing/purlin plan, bracing plans, girt/wall elevations, member/section schedule, connection details, sheeting as separate sheets | Sheet titles | none | unverified |
| Erection drawings "show anchor bolt settings, transverse cross-sections, sidewall, endwall and roof framing, flashing and sheeting" | Contents of the final set | search snippet | unverified |
| Where the erection manual and the erection drawings conflict, the drawings take precedence | Order-of-precedence note | search snippet | unverified |
| Reading order for a model (inference, no source states one): grids and anchor-rod plan, then base details, frame cross-section, roof plan, wall elevations, bracing, crane sheets, connection details, schedule | n/a | n/a | unverified |

What each sheet contributes to a model (inference from the rows above, to be confirmed on the real set):

| Sheet | Positions | Sections | Levels | Orientation |
|---|---|---|---|---|
| Anchor rod plan | Column grid, rod pattern, steel line offsets | Rod diameter only | Finished-floor and base-of-steel elevation, rod projection | Pattern axes vs grid |
| Frame cross-section | Eave and apex points | Column, rafter marks, tapered start/end | Eave height, ridge | Haunch side, slope direction |
| Roof/wall framing | Purlin and girt spacing | Z/C mark, thickness | Eaves level | Z/C flange direction, lap side |
| Bracing | Bay, node points | Rod/cable/angle | Connection heights | n/a |
| Crane sheets | Bracket and runway beam position | Runway beam, rail | Top of rail, bracket level | n/a |

All rows in this second table: unverified.

## 3. Column bases

| Claim | What the reader looks for on the drawing | Src | Verified |
|---|---|---|---|
| In most portal frames a nominally pinned base is provided, because a moment-resisting base is costly; a rigid base needs a bigger base detail and foundation | The designer's base type label or analysis note; reactions with or without a base moment | S1 3.6, 12.1; S2; S3 | verified (PDF) / verified (fetch) |
| A base with four bolts is still analysed as pinned; four bolts are used for stability during erection | Four rods on a base does NOT prove the base is fixed | S1 3.6, 12.2 | verified (PDF) |
| For serviceability checks a pinned base may be given some stiffness (up to 20% of column stiffness is quoted) | A note in the analysis report; not visible on the detail | S1 (SLS note) | verified (PDF) |
| Rigid base figure: "Nominally rigid, moment resisting base with gusset plates for high moments" | Gusset plates or stiffeners on the base plate, wider rod spread | S1 Fig 12.3 | verified (PDF) (caption only) |
| A moment base may be required only at the fire limit state even if pinned at ULS; a special detail is shown | Fire-boundary note, larger plate and bolts at the wall near a boundary | S1 3.6, 12.1 | verified (PDF) |
| **No source lets a reader decide pinned vs fixed from the detail alone.** P252 says the choice comes from the design stage and analysis; the detail (rod count, plate size) is consistent with either | Ask the engineer; look for "pinned"/"fixed" in the notes or a moment column in the reaction table | S1 | verified (PDF) |
| The sample reaction tables list H, V, L per column only; a moment term is not seen | Whether a moment reaction is tabulated at fixed bases | S6 | unverified (inference) |
| Responsibility: steelwork contractor usually details base plate and holding-down bolts; contract documents must say who designs the bolts | Note on anchor design responsibility | S1 12.5 | verified (PDF) |
| PEB: rod size is set by shear and tension at underside of base plate; rod length and load transfer are set by the foundation engineer; rods are not supplied by the manufacturer | Note "Anchor bolts to be designed by foundation engineer using diameters shown in the table" | S4 3.1, S6 | verified (PDF) |
| Anchor rod callout (what to look for): diameter, quantity table, material grade note (ASTM F1554 Gr. 36 unless noted), projection, edge distance in the base section | Rod table + section detail | S6 | verified (PDF) |
| Anchor bolt types in the TCVN draft: L-shaped, with anchor plate, straight, conical head; cast-in vs post-installed; "calculated" vs "constructive" bolts | Hook or plate at the rod bottom on the detail | S7 App. I | verified (PDF) (draft, normative appendix) |
| Anchor plates or angles (to join rod pairs) are used to anchor the bolts in the foundation | Plate at rod bottom | S1 12.1, 12.5 | verified (PDF) |
| Oversize holes with washers are often used to help rod location tolerance | Hole size note | S1 12.5 | verified (PDF) |
| Anchor rod setting tolerances refer to the AISC Code of Standard Practice; a tolerance table sits on the sample sheet | Tolerance box on the anchor rod sheet | S6 | verified (PDF) |
| Leveling plates are not supplied unless the order calls for them | "Leveling plate" in notes or bill | S4 3.1.3 | verified (PDF) |
| Grout: thickness, grout hole, non-shrink product name | Notes at the base section | none read | unverified (as drawing content) |
| Shear key under base plate; horizontal reaction at the base resisted by passive soil, a tie in the floor slab, or a tie across the building | Slab tie rod, shear key, strut between bases | S1 12.3 | verified (PDF) |
| Level of underside of base plate = "base of steel" elevation, shown in the base detail (sample: base of steel at the finished-floor elevation) | Elevation note per base type | S6 | verified (PDF) (one sample) |
| Rod pattern symbols on the anchor plan mark the pattern centre line, not an individual rod | Symbol legend | search snippet | unverified |
| AISC Design Guide 1: four rods "as required by OSHA"; guide scope on moment bases | n/a | S12 | not opened (403) |

## 4. Built-up tapered I and cold-formed notation

| Claim | What the reader looks for on the drawing | Src | Verified |
|---|---|---|---|
| Tapered built-up members are plates welded together: constant or tapered web, flanges as plates; the PEB spec sets minimum plate thickness (numbers not repeated here) | Plate sizes in the member schedule | S4 5.1.3, 5.2.1 | verified (PDF) |
| Tapered-member design guidance (AISC DG 25, web-tapered I members, metal-building proportions): scope seen only in a search snippet | n/a | S13 | not opened; unverified |
| No manufacturer document read states a field order for a built-up tapered section (depth-start ~ depth-end x web + flange width x thickness) | Ask which order the drawing uses and whether depth is overall or web-only | none | unverified |
| Tekla catalogue syntax for variable-depth I is `I_VAR_Ah1-ht*b1-bt*s*t`; welded I with two heights is `HIh1-h2-s-t*b`; built-up `I_BLT_Ah-b1-s1-t1*h2-b2-s2-t2` | This is Tekla's catalogue pattern, not drawing notation | S9 | verified (HTML) |
| Z or C purlin designations such as `Z200x2.0`, `C200x65x20x2.0` | Field order (depth, flange, lip, thickness) and thickness basis (nominal vs base metal) | none | unverified |
| A Tekla page says `CMF-C20320` is a C section 203 mm deep, 63 mm flange, 2 mm thick (manufacturer code for rails) | Manufacturer-specific code; do not generalise | S10 | verified (fetch) |
| Metsec-style "first three digits = depth, then Z/C, then thickness code" (e.g. `232 Z 18`) | Only if the supplier is that manufacturer | search snippet | unverified |
| Z and C sections are cold-formed purlins and girts in the PEB spec; a minimum thickness for cold-formed secondary members is given (number not repeated) | Thickness in the schedule | S4 5.1.3, 5.3.1 | verified (PDF) |

## 5. RC foundation and steel interface

| Claim | What the reader looks for on the drawing | Src | Verified |
|---|---|---|---|
| Pile cap (đài cọc) = beam or slab connecting pile heads and distributing the superstructure load; "high" if the base is above ground, "low" if on or in the ground | Cap plan and section on the foundation sheets | S8 cl. 3.13 | verified (PDF) |
| Pile head is by default "free" in the soil-structure model; other head conditions may be considered in some cases | Designer note on pile-head fixity | S8 7.1.1.2 | verified (PDF) (draft) |
| In practice the pile head is joined to the pile cap, which restrains rotation in whole or in part | n/a | S8 App. I.2.3 | verified (PDF) (draft) |
| Pile head embedment length into the cap and the pile cut-off level | A cut-off elevation and a pile-head detail | none | not found; unverified |
| Pad footings for light industrial buildings: horizontal base force resisted by passive pressure, slab tie or building-width tie | Tie bars in the slab or between caps | S1 12.3, 12.6 | verified (PDF) |
| Pedestal / stub column (cổ cột), ground / tie beam (giằng móng) between caps | Pedestal size, top level, anchor rod cage | none | unverified (no source opened) |
| Slab-on-ground with contraction and expansion joints | Joint layout on the slab sheet | none | unverified |
| Datum: PEB eave height is measured from the finished floor even for curbs or column recesses; the sample sheet puts base of steel at the finished-floor elevation | Level of finished floor vs top of pedestal vs underside of base plate | S4 1.2.3, S6 | verified (PDF) |
| Relationship of ±0.000 (architectural) to finished floor and to the steel datum, and grout thickness between pedestal and plate | Level notes on the foundation and frame sheets | none | unverified |
| Foundation is not designed by the manufacturer; the foundation engineer owns rod length and embedment | Separate foundation drawings with their own revision | S4 3.1.1, 3.2 | verified (PDF) |

## 6. What Tekla Structures needs (Tekla User Assistance, mostly 2026)

Pages reached on `help.trimble.com` (the old `support.tekla.com` address redirects there).

| Claim | What the reader looks for on the drawing | Src | Verified |
|---|---|---|---|
| The 2026 Base plates page lists 13 components, among them Simple base plate (55), Base plate (1004), Stiffened base plate (1014), Web stiffened base plate (1016), Base plate (1042), Circular base plates (1052), Box column base plate (1066), Tapered column base plate (1068) | Base detail type: plain, stiffened, box column, tapered column | S11 (2026) | verified (HTML) for names found in raw HTML; others verified (fetch) |
| Base plate (1004) creates a base plate connected to a column end, with optional shim plates, leveling plate, grout, shear key, extra plates for rods, anchor rods, bolts, welds | Shear key, leveling plate, shim, grout on the detail | S12 (2026 page modified 12 Dec 2025) | verified (HTML) for the creation sentence and tab terms; object list from 2025 page, verified (fetch) |
| Anchor rods tab: Rod profile, Nut profile, Washer profile, Plate washer, Cast plate, Grout; "Base plate with" Bolts / anchor rods / custom component; hook types and bolting direction; grout cast unit type is "Cast in place" and no grout by default | Rod bottom type (hook, plate), nut and washer, grout thickness | S12, S14 | verified (HTML) for tab terms; option details verified (fetch) |
| Rod length and length above plate have default values in Tekla; these are Tekla defaults, not facts from a drawing | Rod length and projection callouts must be entered from the drawing | S12 (2025) | verified (fetch) |
| Stiffened base plate (1014): web plate and flange plate stiffeners, shear key, Parts/Parameters/Bolts/Stiffeners/Anchor rods/Extra plates tabs | Stiffeners at flange and web on a rigid-looking base | S14 (2025) | verified (fetch) |
| Tapered column base plate (1068) "creates a base plate detail to a tapered column"; its own help page was not reached (URL 404) | Tapered column bottom (PEB column tapers to the base) | S11 (2026) | verified (HTML) (one sentence only) |
| Tapered beam (S98) creates a tapered or straight built-up beam with I shape from plates (web plate, two flange profiles, height and slope) | Built-up rafter or column modelled as plates | S15 (2026 sentence); 2025 inputs | verified (HTML) sentence; inputs verified (fetch) |
| Profile catalog patterns (2026): `I_VAR_Ah1-ht*b1-bt*s*t`, `I_BLT_Ah-b1-s1-t1*h2-b2-s2-t2`, `HIh1-h2-s-t*b`, `HIh1-h2-s-t1*b1-t2*b2`, `Z h*b*t`, `Z_VAR_A h1*b1*b2-s-h2*b3`, `C h*b*t`, `C_BUILT h*b*s*t`, `C_VAR_A h1*b1-s-h2*b2`, `BENTZ h*b*d*t[-a]` | Section designation on the drawing must be mapped to one of these | S9 (2026, page modified 6 Dec 2022) | verified (HTML) for I_VAR_A, I_BLT_A, HIh1-h2, Z h*b*t, Z_VAR_A, BENTZ, C_BUILT, C_VAR_A; rest verified (fetch) |
| The name "PHI" is not on the 2026 profile page | Do not assume a `PHI` profile exists | S9 | verified (HTML) (absent) |
| Open API subtype names include welded symmetrical I with altering height (1004) and cold-rolled Z (3001) and C (9002) (2025) | n/a (API route, for `tekla-cli`) | S16 | verified (fetch) |
| Component "Generation of purlins (50)" creates multiple profiles used as wall or roof purlins; spacing, overlap and orientation inputs | Purlin spacing, lap, flange direction | S17 (2026) | verified (fetch) |
| Cold rolled (CMF) rails: naming parts "PURLIN" and "RAIL" is recommended or drawings may come out with the wrong orientation; page is not version-specific | Part name in the model | S10 | verified (fetch) |
| Component numbers and names can differ by version and environment; check the installed configuration | n/a | S9, S11 | unverified (not stated on pages read) |

## 7. Questions, disagreements, gaps

### Unverified forms that must become engineer questions

1. Is each base pinned or fixed? Where does the designer state it (note, analysis report, reaction table with moment)?
2. Rod count on a base: does the designer treat four-rod bases as pinned (P252 says UK practice does)?
3. Depth convention of tapered members (overall vs web, centre-line vs face of column) and field order of the section text.
4. Z/C designation order and thickness basis (nominal vs base metal); flange direction and lap rules.
5. Which standard and grade apply to plates, rods and bolts shown on the set (no equivalence assumed).
6. Datum chain: ±0.000, finished-floor level, top of pedestal, grout thickness, underside of base plate.
7. Who supplies rods, leveling plates, and shop drawings (Nucor says: not the manufacturer for rods and shop drawings).
8. Pile cut-off level and head embedment into the cap; pedestal and tie-beam geometry; slab joint layout.
9. Whether purlin-to-rafter and bracing connections are drawn or left to the fabricator.
10. Crane data: capacity, rail top level, bracket drawings, runway beam marks; mezzanine and canopy loads.
11. Vietnamese terms in section 1 marked unverified (kèo, xà gồ tường, cổ cột, giằng móng).

### Where sources disagree

- Eave strut: P252 = hot-rolled or hollow section between column flanges (3.10); Nucor = roll- or brake-formed C
  section (5.3.3). Treat the term as supplier-specific.
- "Primary" vs "secondary": Nucor counts hot-rolled and cold-formed columns as primary if they carry load to the foundation (5.1.1).
- "Anchor length": Nucor and the sample set give it to the foundation engineer (S4 3.1.1, S6); P252 says the contract
  documents must state who designs the bolts (12.5).
- "Wind post" (Vietnamese/Asian PEB term, unverified) vs "gable post" (P252, S3).

### Not verified / not opened

- AISC Design Guide 1 (aisc.org landing page returned 403; the four-rod/OSHA remark and base types are search snippets only); Design Guide 25 and MBMA manual (landing/snippets only; paid).
- Tekla Tapered column base plate (1068) help page (guessed URL returned 404); component numbers other than those quoted.
- Vietnamese: TCVN 5575:2024 final text (403), TCVN 10304 final text, any Vietnamese PEB maker's drawing set or glossary, the moc.gov.vn industrial building guide (download failed, 3 attempts stopped).
- SCI/Steel Buildings in Europe single-storey guides, SN045a base classification: search snippets only.
- Anchor template, pretension, grout specification, expansion joints, pile cut-off: no primary source found.

## Sources

| # | Source | Grade | Verified |
|---|---|---|---|
| S1 | SCI P252, "Design of Single-Span Steel Portal Frames to BS 5950-1:2000" (2004): https://www.SteelConstruction.info/images/4/44/SCI_P252.pdf | A | verified (PDF), sections 2.4, 2.11, 3.1-3.16, 5.5, 12.1-12.6 read |
| S2 | steelconstruction.info, Portal frames: https://steelconstruction.info/Portal_frames | A | verified (fetch) |
| S3 | steelconstruction.info, Engineering students' guide to single storey buildings: https://www.steelconstruction.info/Engineering_students'_guide_to_single_storey_buildings | A | verified (fetch) |
| S4 | Nucor Building Systems, Specification Guide section 3.0: https://www.nucorbuildingsystems.com/wp-content/uploads/2019/01/03_00.pdf | B | verified (PDF) |
| S5 | Nucor Building Systems, Cranes section 4.6 (table of contents of crane details): https://www.nucorbuildingsystems.com/wp-content/uploads/2019/01/04_06.pdf | B | verified (PDF), titles only |
| S6 | Toro Steel Buildings, sales drawing set (preliminary, not for construction, US units): https://www.torosteelbuildings.com/wp-content/uploads/2025/11/SalesDrawings.pdf | C | verified (PDF), used only as a sheet-type example |
| S7 | IBST draft "TCVN 5575:202x" for comments: https://ibst.vn/upload/documents/file_upload/1635738694Du-thao-xin-y-kien-TCVN-5575-202x.pdf | A (draft) | verified (PDF), clauses 4.2.6, 8.6, 15.4, 15.6, App. I read |
| S8 | IBST draft pile foundation standard (draft 08/05/2023): https://ibst.vn/upload/documents/file_upload/1683708278TCVN-TK-Mong-coc-2022-V20.pdf | A (draft) | verified (PDF), cl. 3.13, 7.1.1.2, I.2.3 read |
| S9 | Tekla Structures 2026, Predefined parametric profiles: https://help.trimble.com/doc/tekla-structures/2026/mod_available_parametric_profiles | A (Tekla 2026) | verified (HTML) |
| S10 | Tekla, CMF cold rolled - Important information (not version-specific): https://help.trimble.com/help/tekla-structures/not-version-specific/cmf-cold-rolled-important | A | verified (fetch) |
| S11 | Tekla Structures 2026, Base plates: https://help.trimble.com/doc/tekla-structures/2026/com_steel_base_plates | A (Tekla 2026) | verified (HTML) |
| S12 | Tekla Structures 2026, Base plate (1004): https://help.trimble.com/doc/tekla-structures/2026/detail_1004_help (2025 page also read: https://help.trimble.com/doc/tekla-structures/2025/detail_1004_help) | A (Tekla 2026/2025) | verified (HTML) 2026; details verified (fetch) 2025 |
| S13 | AISC Design Guide 25 and Design Guide 1 (landing pages): https://www.aisc.org/Design-Guide-25-Frame-Design-Using-Nonprismatic-Members-Second-Edition and https://www.aisc.org/Design-Guide-1-Base-Plate-and-Anchor-Rod-Design-Second-Edition | A (paid) | not opened (403) |
| S14 | Tekla Structures 2025, Stiffened base plate (1014) and Base plate (1042): https://help.trimble.com/doc/tekla-structures/2025/detail_1014_help , https://help.trimble.com/doc/tekla-structures/2025/detail_1042_help | A (Tekla 2025) | verified (fetch); 1042 2026 page confirmed in raw HTML |
| S15 | Tekla Structures 2026/2025, Tapered beam (S98): https://help.trimble.com/doc/tekla-structures/2026/det_built_up_components_s98 | A | verified (HTML) one sentence; 2025 inputs verified (fetch) |
| S16 | Tekla Open API 2025, ProfileItemProfileItemSubTypeEnum: https://developer.tekla.com/doc/tekla-structures/2025/profile-item-profile-item-sub-type-enum-enumeration-46791 | A | verified (fetch) |
| S17 | Tekla Structures 2026, Generation of purlins (50): https://help.trimble.com/doc/tekla-structures/2026/modtool_50_help | A | verified (fetch) |
| S18 | Search snippets (Metsec nomenclature, MBMA para 3.2.2, NY master specification, OSHA four-rod remark, VN thesis on fixed bases, IDEA StatiCa example) | C | unverified, never used alone |
