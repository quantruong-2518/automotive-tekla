# 0018. Render drawing regions with the ezdxf SVG backend and resvg-py

- Status: accepted
- Date: 2026-11-20
- Decided by: orchestrator on measurement; the engineer asked for the option that is best by time,
  tokens, readability for the agent and accuracy (chat, 2026-11-20)

## Context

The drawing reader reads text only. On project 01 it could not see linework (cap outlines, pile
symbols), and a geometry count can be wrong in ways only a picture shows: a spike counted 2 piles in
caps that have 4, because mirrored inserts store circle centres in OCS. The reader needs an image
of a drawing region, mapped to drawing coordinates, to look at what the numbers describe and to
cross-check counts. Claude reads PNG, not SVG. Nothing on the machine rasterises today (no
matplotlib, Pillow, PyMuPDF or system tool).

The repository is proprietary (LICENSE), so AGPL and GPL dependencies are excluded, and LGPL ones
are avoided.

## Options measured

Three regions of project 01 (a whole sheet, four caps, one cap); report and scripts in
`projects/_evals/render-bench-2026-11-20/` (git-ignored archive).

| | ezdxf + matplotlib | ezdxf SVG + resvg-py | Pillow-only rasteriser |
|---|---|---|---|
| Time, sheet / 4 caps / 1 cap | 9.6 / 2.9 / 2.2 s | 7.2 / 2.3 / 2.1 s | 6.7 / 2.5 / 2.1 s |
| Image tokens (long edge ≤ 1568 px) | ~1533 | ~1533 | ~1533 |
| Added install size | 53 MB | 3 MB (resvg-py) + 22 MB (Pillow, needed by the ezdxf frontend) = 25 MB | 20 MB + a font |
| Pixel ↔ coordinate error | ~1 px | ≤ 0.12 px (page laid out at 10 px per mm) | ≤ 0.4 px |
| Hatch, linetypes, fonts | yes | yes | no |
| Licences | permissive | MIT (Rust crates MIT/Apache/BSD) | permissive |
| Windows wheel | yes | yes (abi3) | yes |

PyMuPDF (AGPL) and the Qt backends (GPL, or LGPL and hundreds of MB) were not considered further.

## Decision

`harness render` draws a region with ezdxf's drawing add-on and its SVG backend, and rasterises the
SVG with `resvg-py` (runtime dependency, about 3 MB). Rules:

- Only the region is drawn: entities whose box misses the region are skipped before drawing (per
  block box × insert matrix). Drawing the whole file instead costs 5-7× more on project 01 (28.7 s
  against 5.5 s, and 30.1 s against 4.5 s, for two regions; review 1).
- The PNG fits the model's image budget (long edge ≤ 1568 px, area ≤ 1.15 MP), so every image costs
  about 1.5k tokens; detail comes from a smaller region, not a larger image.
- Dark background, line weight × 2, drawing-unit ticks on the border; the output states the pixel
  to drawing-coordinate transform.
- Text is never read from an image: legacy TCVN3 text renders garbled and some dot-below
  diacritics are dropped. Numbers in findings come from command outputs, not from pictures.

## Known limits and open points (review 2)

- The dash pattern of an XLINE or RAY starts at the edge of the clip box, which moves with the region: the
  dashes may shift between tiles. The positions of solid geometry are exact. Anchoring the phase to the base
  point needs the pattern length in drawing units, which the frontend scales internally; not done.
- Open: to be checked in AutoCAD by the engineer. Does freezing layer 0 hide the layer-0 content of blocks
  whose INSERT is on a layer that is on? `render` and `geometry` follow the INSERT's layer for such content and
  never read layer 0's own state. Behaviour unchanged until the check.
- The invisible flag (group 60) on project 01 is mostly the hidden visibility states of dynamic blocks, which
  AutoCAD does not show either; `render` does not offer to draw them.

## Consequences

- Two new runtime dependencies, `resvg-py` and `pillow`; pinned in `uv.lock`. Measured with `du` on the
  Linux venv site-packages: resvg_py 3 MB + dist-info 1 MB; PIL 6 MB + pillow.libs 15 MB + dist-info 1 MB.
- Pillow is a runtime dependency only because ezdxf's drawing frontend imports it (ezdxf `draw` extra);
  our code does not call it. The benchmark venv had it through matplotlib, so the 3 MB figure measured
  above left it out.
- Fonts resolve differently on Windows (Arial and others available): text widths may differ from
  the Linux measurement; check on the Tekla machine.
- If resvg-py stops being maintained, the Pillow-only rasteriser is the fallback (no hatch, no
  linetypes).
