# Reading linework: values, how they are drawn, tools, and when to use them

Status: final design note for the geometry toolset (T21–T24, built on branch `feat/reading-tools`;
T25–T27 proposed, not built), 2026-11-20. Engineer instruction
(chat, 2026-11-19): start from the expected outputs and the drawing knowledge, pick the right tools,
and specify in detail when and how each tool is used. Engineer, 2026-11-20: every new tool ships with
a standardised, slimmer reading workflow. That workflow is rev 10 of the `structural-drawing-reader`
skill (`dwg-lab/proposals/skills/rev10/`); this note is its rationale and the tools' contract in prose.

## 1. Problem

The rev 8 reading of project 01 took more than two hours, and most of the blocking questions it
raised were about values the drawing *shows as linework* but the reader could not read: cap sizes,
piles per cap, pile and cap positions, which axes carry members, the real width of block NX2. The
reader's tools read text only (`sheet-text`, `find-text`, `marks`, `callouts`, `dimensions`); its
reading record says "member geometry, pile positions inside caps: no tool" on four phase cards.

A spike on project 01 reproduced from linework alone, in one walk of the file (about 30 s): sheet
model#06 (NX1 pile-cap plan) holds 83 caps (closed polylines on one layer) and 262 piles (unique
circle centres): 800×1700 ×12 with 2 piles each, 1700×1700 ×46 with 3, 1700×2600 ×2 with 4,
1700×3200 ×23 with 4; 12·2 + 46·3 + 2·4 + 23·4 = 262, the pile total printed in the notes (the rev 8
reading held "262 vs 189" as an open contradiction). The stub plan model#08 holds 400×700 ×58 and
500×1000 ×25 = 83 stubs, the CC-1/CC-2 counts. NX2's pile plan model#05 holds 200 piles.

A first version of the spike got 204 piles: it read circle centres in OCS. 6157 circles and 3309
polylines of the file sit in mirrored inserts (extrusion 0,0,−1), whose stored x is negated. A
rendered image of three caps showed four piles where the numbers said two, which found the bug.
Two lessons are rules of the tools: every coordinate is converted to WCS, and a rendered region is
the cross-check of a geometry count.

## 2. What the Tekla model needs (summary of the value matrix)

The full matrix (101 rows, per member family × value, with the spec field or plan line that needs it)
is `drawing-value-matrix.md` (next to this note; written 2026-11-20). The values that decide whether a lot can be built:

| Family | Values | Usually drawn as |
|---|---|---|
| Grid | labels, spacings, which grid each block uses | axis lines + bubbles; dimension chains |
| Level | ±0.000, storey and local levels, foundation levels | level symbols; section dimensions; notes |
| Pile | position, diameter/section, count, length, head level | circle or block symbol on the pile plan; schedule; notes |
| Pile cap | position (axes + offset), plan size, depth, top level, mark, piles per cap | closed outline on the foundation plan; mark text inside or beside it; section dimensions |
| Ground/tie beam | axis, section (b×h), top level, mark | two parallel lines between caps; size text "(30x60)"; section |
| Column stub | position, section, top level, mark | closed outline on the stub plan; schedule |
| Slab on grade | extent, thickness, level, mesh | plan outline/hatch; note; section |
| Steel column | position, profile, orientation, base level | outline/symbol on the column plan; column table |
| Base plate, anchor bolts | plate size, bolt size/number/layout, grout | base detail (enlarged, other scale); anchor-bolt plan |
| Roof frame, bracing, purlins | positions, profiles, levels | frame elevations, roof plan; schedules |

Not drawn at all (decided at gates, not read): global origin, cast-unit type, base fixity, Tekla
profile and material strings, numbering, UDAs.

## 3. How these values are drawn (what the reader must know)

Facts from project 01 (spike, review runs) and the research notes
`steel-industrial-building-drawings.md`, `vn-structural-drawing-conventions.md`:

1. **Scale is checked, not assumed.** Coordinates are in drawing units (mm by the engineer's answer;
   the DXF header said inches). A plan size from `contents` is the real size only while the plan's grid
   spacing is dimension-backed; otherwise it is asked. **Details and sections are often drawn
   enlarged** in the same model space. Only a `dimensions` row with `override_value` or
   `expected_text_value` gives a ratio (that value ÷ `measured`); an automatic row prints its
   measurement × DIMLFAC, which `dimensions` does not report (proposed T26), so it confirms none. A
   linework size from a detail is recorded with a ratio (size = measured × ratio), or with an agreeing
   printed dimension, else it is asked.
2. **Members are layered.** One layer per member kind is usual (01: caps `DCE_BaoBeTong`, piles
   `DCE_Coc`, stubs `DCE_SUB-COLN_T---`, steel columns `COLUMN-BMB`, grids `DCE_Truc`). Layer names
   differ per office: the tools report counts per layer and the reader decides which layer is which
   member, citing a legend, a mark inside the outline, or the schedule. A layer's meaning is a
   judgement (a finding), never a tool default. A wrong choice shows in the output: on model#08 the
   circle layer chosen was the grid bubbles (Ø3000), and all 64 symbols fell outside every outline.
3. **Symbols are blocks.** A pile symbol is a block drawing many circles and squares (01: ~13
   identical Ø300 circles per pile, in two diameters, Ø228 and Ø300). Layer `0` inside a block takes
   the inserting layer. The tools expand blocks recursively and collapse identical copies (`copies`);
   concentric circles are one symbol.
4. **Caps, stubs, columns are closed outlines** (closed polylines in 01). Some offices draw them with
   loose lines or hatches: then the outline group is missing and the layer shows lines only (gap, §5).
5. **Beams are two parallel lines** with a mark and a size text beside them (gap, §5; on model#08 the
   beam marks `GM-…(30x60)` have no outline: `contents` lists them as `marks_unassigned`, unless one lies
   within `--mark-radius` of a stub and `GM` was given in `--marks`, when it lands on that stub; so
   `--marks` holds the marks of one member family only).
6. **Marks sit inside or beside the outline** (DC-1, CC-2). Not every outline carries its mark: on
   model#06, of 46 outlines of 1700×1700 with 3 piles only 23 hold the text DC-2, and the same text
   DC-2 also sits on 1700×3200 outlines. The tool shows `marks_seen` and `unmarked` per type and never
   copies a mark to an outline that holds none; a mark applies only to the outlines it was assigned to,
   and whether the unmarked ones are the same mark is the reader's judgement, checked against the
   schedule (C12).
7. **Positions are relative to grid axes.** Tekla needs axis label + offset, which `contents` computes
   from the sheet's grid groups (`structure/<file>.grids.json`): per outline, per grid family, the
   nearest labelled axis and the signed offset. An outline in no grid group (model#09: two) gets no
   axes and one warning.
8. **Repeated views exist** (01: the same grid frame on several sheets). Counts are per sheet; never
   add counts across sheets without checking that the sheets show different things.
9. **The invisible flag (group 60 = 1).** On project 01, model#06 has 18,602 invisible entities on layer DCE_Coc (`geo06.json`; the figure is per layer)
   and every column-stub outline of model#08 carries it. A check on the file found that most
   are hidden visibility states of dynamic blocks (AutoCAD hides them too); the cause is not stated further.
   `geometry` and `contents` count and report them; `render` does not draw them. A hidden outline can
   still be a printed member: the stubs of model#08 are drawn by other entities (outline and hatch) in
   the render. Rule: render the region of a counted invisible member; drawn there, the count stands
   and the finding says `counted from hidden outlines, confirmed by render`; nothing drawn, the
   member is not counted and that is recorded; where the render does not settle it, ask whether it prints.
   The tools' warning (reworded, commit `3550d03`) says: mostly hidden visibility states of dynamic blocks; `render` does not draw them; confirm a counted member with `render`.

## 4. Tool set

Existing (text): `sheet-text`, `find-text`, `marks`, `callouts`, `dimensions`, `unassigned-clusters`,
grid and level producers. New (linework), final CLI (`harness <command> --help` is the source of truth):

| Id | Command | Gives | Status |
|---|---|---|---|
| T21 | `harness geometry W F [--sheet ID …] [--bbox X0 Y0 X1 Y1] [--layer L …] [--detail] [--max N] [--tol T] [--input-dir D] [--save]` | per sheet or region: counts per layer (`circles`, `outlines`, `lines`, `arcs`, `hatches`, `hidden`, `invisible`, …); `circle_groups` (layer, diameter, count, copies); `outline_groups` (layer, short, long, count, copies, invisible); with `--detail` each item (id `G-…`, centre, size, angle) | built, read-only; `--save` takes the work lock |
| T22 | `harness contents W F --sheet ID --outline-layer L … --circle-layer L … [--marks REGEX] [--max-long N] [--mark-radius R] [--detail] [--max N] [--tol T] [--save]` | per outline: size, symbols inside, marks, nearest axis per grid family with signed offset, invisible flag; `summary` (layer, size, symbols → count, `marks_seen`, `unmarked`, `invisible`); `symbols` (total, inside, outside), `marks_unassigned`, `marks_ambiguous`, warnings | built, read-only |
| T23 | `harness render W F (--sheet ID \| --bbox X0 Y0 X1 Y1) [--tiles CxR] [--layer L …] [--max-px N] [--no-overlay] [--out-dir D]` | PNG of a region with coordinate ticks in drawing units, the pixel to coordinate transform, `entities_drawn`, `entities_pruned`, `entities_invisible` (ADR-0018) | built; writes only PNGs; model space only |
| T24 | `geometry\|contents --save`; `harness finding add --kind measured --source geometry/<name>.json --items G-… [--field quantity=count\|size\|position\|level\|spacing]`; `finding add --kind cross_check --entries T… --source … --items …` | geometry evidence stored in the work folder (name from the query and the drawing's sha256: the same query, the same file); a finding that cites item ids, `stale` in `finding list` when the saved file changes | built |
| T25 | parallel line pairs (beams), loose-line outlines | beam axis, width, length; outlines from joined lines | not built; when a project needs it |
| T26 | `dimensions` reports `dimlfac` and the printed value per row | a ratio for every dimension row, so a detail's linework size can be confirmed | proposed, not built |
| T27 | `contents --by-axis`, `--ids` | per-axis counts and the id list for `--items` | proposed, not built |

Every value from T21–T24 is **drawing-derived**: it carries sheet, item ids and a confidence stated once
in the skill's tools.md § Measured findings (`medium` without text entries; with an agreeing printed
entry the minimum of the entries' confidence; a disagreeing one makes a `cross_check` and a question),
and the engineer confirms it at gate 1. It replaces a question only when it answers it; otherwise it becomes evidence on the
question (`ask --supplement`).

Measured costs on project 01 (large DWG): `geometry` and `contents` ~30 s per call (one walk of the
file, whatever the filter); `render` ~5–18 s per region; ~1.5k image tokens per image; `geometry` JSON
~10 kB per sheet (read through a compact summary); `contents` JSON 60–80 kB for 83 outlines (always `--save` and print the summary only).

### 4.1 Render choice (measured, engineer asked for the best by time, tokens, readability, accuracy)

Benchmark on three regions of project 01 (`projects/_evals/render-bench-2026-11-20/REPORT.md`; ADR-0018):

| | ezdxf + matplotlib | ezdxf SVG + resvg-py (chosen) | Pillow only |
|---|---|---|---|
| Time, sheet / 4 caps / 1 cap | 9.6 / 2.9 / 2.2 s | 7.2 / 2.3 / 2.1 s | 6.7 / 2.5 / 2.1 s |
| Image tokens | ~1533 | ~1533 | ~1533 |
| Added install size | 53 MB | 3 MB | 20 MB + font |
| Pixel ↔ coordinate error | ~1 px | ≤ 0.12 px | ≤ 0.4 px |
| Hatch, linetypes, true fonts | yes | yes | no |
| Licences | permissive | MIT/Apache/BSD | permissive |

PyMuPDF (AGPL) and Qt (GPL, or LGPL and very large) are out for a proprietary repository. Tokens are
fixed by the image budget (long edge ≤ 1568 px), so the lever is the region size: a whole sheet is
~230 drawing units per pixel (overview only), four caps ~23, one cap ~3. Most render time is block
expansion, so the region is pruned before drawing (5–7× faster than drawing the whole file).
Settings: dark background, line weight ×2, coordinate ticks on the border. Limits: legacy TCVN3 text
renders garbled and ezdxf drops some dot-below diacritics: text is read with `sheet-text`, never from
an image; entities with group 60 = 1 are not drawn (§3 item 9).

## 5. When and how (the rev 10 workflow)

| Phase | Use | Replaces |
|---|---|---|
| 0 Reach | `geometry --save` once per file, `--sheet` listing every sheet of the file, read through a compact summary: layers, groups, `hidden`, `invisible`, warnings. A sheet with geometry but little text is not "near-empty" | the near-empty guess from text counts |
| 1 Orient | the same summaries classify plan sheets (caps and piles, stubs, column outlines) and show repeated sheets; each member layer's meaning is recorded with its evidence | classing a plan from its title only; guessing the member layer |
| 3 Frame | `contents` per member plan: per outline the nearest axis and offset; outlines in no grid group → finding and question | the manual occupancy count (T17, dropped) |
| 4 Members | `contents` per member plan: sizes, counts per type, piles per cap, marks per type (`marks_seen` vs `unmarked` judged by the reader); `render` of one region per type before any count is recorded; `dimensions` scale check before any size from a detail or section; one `measured` finding per type citing every outline id, with a `--claim` per number (a total is a hand sum of those findings) | reading sizes off text, "size: unread (no tool)", counting by marks |
| 6 Analyse | C11 from `contents` axes; C12 plan counts from `contents` against the schedule quantity (`cross_check` with one schedule entry plus the saved document) | the manual count chain (T18, narrowed to the schedule side) |

Rules: one `geometry` call per file serves every sheet (`--sheet A B C`; saved, read through a compact summary); one `contents` call per
member plan sheet, `--save`; render a region (a few caps), not a whole sheet, unless orienting; every
number cited in a finding comes from a command output, never from reading an image; text comes only
from the text index. What the tools do not cover (loose-line outlines, hatch-only members, beams,
details only in paper space, sections without a dimension row) stays `unread`, read by text, with a
question per family.

## 6. Acceptance and evaluation

Pre-registered on project 01 (contaminated: the comparison report already holds these values, so this
checks the tools, not the reader): model#06 cap groups 1700×1700 ×46, 1700×3200 ×23, 800×1700 ×12,
1700×2600 ×2; piles 262 on model#06, 200 on model#05; stubs on model#08 400×700 ×58, 500×1000 ×25;
`contents` on model#06: 12 caps with 2 piles, 46 with 3, 2 + 23 with 4, no pile outside a cap.
Result of the T22 review-2 runs (2026-11-20): model#06 matches every figure (262 symbols, 83 outlines,
0 outside); model#08 gives 58 and 25 stubs; model#09 gives two outlines, both in no grid group.

Run 3 (engineer, 2026-11-20): a fresh agent reads project 01 again with the new tools and the rev 10
skill, in a new folder, blind to COMPARE and the rev 4 / rev 8 outputs; report wall time, cost,
blocking questions, and accuracy against the comparison report's verified list, next to rev 4 and
rev 8. A clean evaluation on another development project (never `_heldout-*`) follows.
