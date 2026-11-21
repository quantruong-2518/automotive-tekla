# Steel industrial buildings on RC foundations

Read in phase 4 (and for the load path in phase 1) when the set shows a single-storey steel
frame building: factory, warehouse, workshop. Source of every row:
`docs/research/steel-industrial-building-drawings.md` (cited as `§n` and `S#`). **Rule** = verified
in a primary source; **look for** = what such drawings usually carry, to be read from this set;
**ask** = no verified source, so the value comes from the drawing's own words or the engineer.
The sources are UK and US practice plus draft Vietnamese standards; no Vietnamese manufacturer
set was read, so the project's legend overrules every row here.

## The structure an engineer expects

Load path (expectation, not a rule: confirm each link on the set), vertical: sheeting → purlins → rafters → columns → base plates and anchor bolts →
pedestals or pile caps → piles. Lateral, across: the frame itself (moment connections at eaves
and apex). Lateral, along: roof bracing → eaves member → wall bracing → foundations. Cranes:
rail → runway beam → bracket or stepped column → base.

| Part | Rule (verified) | Look for | Ask |
|---|---|---|---|
| Primary frame | A portal frame has moment-resisting eaves and apex connections; pre-engineered frames are shop-welded built-up I members, constant or tapered, bolted on site (§1; S1, S2, S4) | frame cross-section per frame line or per frame type; start and end depth of each member; splice positions; haunch | which depth a haunch or taper dimension starts from: three meanings exist (S1 3.2) |
| End-wall frame | may be posts with simply supported rafters instead of a portal (§1; S1 2.11) | closer columns on the gable elevation | whether the end frame is a full frame (future extension) |
| Purlins, girts | cold-formed Z or C, simple-span or continuous (§1; S4, S1) | spacing, lap, flange direction, thickness in the schedule | the field order of the designation; nominal or base-metal thickness (§4) |
| Eaves member | terms and sections differ by supplier (§7 disagreement) | member at eaves level on roof plan and side elevation | its section and role |
| Sag rods, flange braces | exist as labelled items; a flange brace runs from a purlin or girt to the frame's inner flange (§1; S1, S4) | thin rods between purlins; short angles near the frame flange | whether they are modelled |
| Bracing | roof and wall bracing in chosen bays; rod, cable or angle; a wind portal where an opening prevents diagonals (§1; S1, S4) | crossed bays on roof plan and wall elevations; bracing legend | member type and end connection where the legend is silent |
| Crane | light cranes sit on column brackets (§1; S1 2.4) | crane data note, top-of-rail level, bracket and runway beam marks, crane stop | capacity, levels and marks not printed |
| Mezzanine, canopy | no source opened | their own framing plan and levels | everything not printed |

## The sheets and what each gives a model

No source states a reading order; this order follows the load path (inference, §2).

| Sheet | Gives | Note |
|---|---|---|
| Anchor bolt (column base) plan | column grid, base type per column, bolt pattern, finished-floor or base-of-steel level | the base type letter links each column to its base detail (§2; S6, one sample set) |
| Base details | plate size and thickness, bolt diameter and count, projection, hook or anchor plate, grout, shear key, stiffeners | levels: top of concrete, grout, underside of plate |
| Frame cross-sections | member marks and sections, eave height, ridge, slope, clearances | dimensions may be to the outside of steel (`steel line`), not to grid lines (§1; S4 1.2) |
| Roof and wall framing | purlin and girt positions, sections, laps | — |
| Bracing plans and elevations | braced bays, members | — |
| Crane sheets | runway beam, bracket, rail level | — |
| Connection details | end plates, bolts, welds | may be left to the fabricator: then say so, with the note's entry |
| Section or member schedule | built-up plate sizes, rolled sections, grades, quantities | a table that lists purlins or bracing is evidence that those parts exist even when no sheet draws them (edge case E04) |

A set that stops at the column bases is a foundation-interface set: phases 4–6 cover the bases
and everything below; every link above is `absent` with a blocking scope question.

## Column bases: pinned or fixed

- **Rule.** The detail alone does not show fixity. A base with four bolts is still analysed as
  pinned in UK practice, the four bolts being for erection stability; a fixed base is a design
  choice stated by the designer (§3; S1 3.6, 12.1, 12.2).
- So K12 records the base as `pinned` or `fixed` only when an allowed entry says so (a note, a
  label on the detail, a reaction table with a moment column) or the engineer answers. Stiffeners
  or gussets on a base are quoted as what the detail shows, never as "fixed".
- Anchor bolts: quote diameter, count per base, grade or standard, length, projection, bottom
  type as printed. Bolt length and embedment may be on the foundation sheets and not on the
  steel sheets: in US PEB practice the steel supplier gives the diameter and the foundation engineer the anchorage
  (§3; S4 3.1, S6); UK practice differs (S1 12.5). Two values for one bolt on the two sheet series → `cross_check`.
- The draft TCVN 5575 names four anchor-bolt shapes (L-shaped, with anchor plate, straight,
  conical head) (§3; S7, draft). A shape is read from the detail and quoted, not inferred.

## Where the steel meets the concrete

Compare the steel sheets with the RC sheets of the same block, item by item (checks C2–C5):

| Item | Steel sheets | RC sheets | Mismatch |
|---|---|---|---|
| Grid | axes on the base plan | axes on pile, cap and ground-floor plans | blocking question quoting both |
| Count | column bases per block | pedestals or caps per block | question (a cap may carry no column; a column may sit on a ground beam) |
| Level | underside of base plate, grout | top of pedestal or cap | question; the difference is not computed by you |
| Anchor bolts | diameter, pattern | cast-in detail, if drawn | `cross_check` |
| Datum | finished floor or `±0.000` on the frame section | `±0.000` and absolute level on the RC notes | question when the two series state different pairs |

Piles and caps: a pile cap joins the pile heads and spreads the load (§5; S8, draft). Cut-off
level, head embedment, pedestal size, tie beams and slab joints have no verified source here:
each is quoted where printed (edge case E23) or asked.

## Section text

No source read gives the field order of a built-up tapered section or of a `Z`/`C` purlin
designation (§4). Read the order from the set's own section table or legend; without one, ask
with the texts quoted. The `H`/`I` + four numbers form is a collision (conventions.md).

For planning only, never for reading: Tekla Structures 2026 names variable-depth and welded I
profiles `I_VAR_A…`, `HI…`, cold-formed `Z…`, `C…`, and has base-plate components 1004, 1014,
1042 and 1068 (tapered column) (§6; S9, S11, S12). A drawing's section text is mapped to these
by `planner` at gate 2 and stays `unvalidated` until checked in the installed environment.

## Vietnamese terms

Seen in a draft standard text (§1; S7, S8): `khung ngang`, `cột khung`, `xà ngang`, `vì kèo`,
`xà gồ mái`, `hệ giằng`, `giằng đứng`, `dầm đỡ cầu trục`, `bu lông neo`, `bản đế`, `chân cột`,
`đài cọc`. Trade words with no source read: `kèo` alone, `xà gồ tường`, `cổ cột`, `giằng móng`,
`vai cột`, `nách kèo`, `giằng cánh`. Both groups are search words; neither assigns a role to a mark.
