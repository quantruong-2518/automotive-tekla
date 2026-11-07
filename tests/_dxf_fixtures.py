"""Synthetic DXF drawing sets for the sheets / grids / levels tests, built with ezdxf.

No text, block or layer name comes from the sample drawings (they are untrusted data). Units are mm.

`build_set` draws, in model space, two A1-shaped title-block frames (84100 x 59400, the frame block's
geometry offset far from its base point) side by side, each with a plan grid:
  - vertical axes 1..4 at 6000 (sheet 2: axis 3-4 is 6500, for the cross-sheet question),
  - horizontal axes A..C at 5000 / 4500,
  - bubbles r = 400: sheet 1 vertical as INSERT + ATTRIB, sheet 1 horizontal as CIRCLE + loose TEXT,
    sheet 2 all INSERT + ATTRIB,
  - sheet 1: a skewed axis '5' (10 degrees off vertical), a dimension 1-2 overridden to '6500' and a
    measured dimension 2-3,
  - sheet 2: a fifth vertical line on the grid layer with an empty bubble (missing label),
  - levels: sheet 1 '+0.000', '+3.600' (with a level symbol), '+7.200', 'TẦNG 2 +3.600';
    sheet 2 'TẦNG 2 +3.650' (conflicting duplicate), '+7.200'.
A paper-space layout 'Plot' holds an ATTRIB title block (no frame rectangle) and a viewport that shows a
model-space note outside both frames.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from ezdxf.enums import TextEntityAlignment
from ezdxf.filemanagement import new

FRAME_W, FRAME_H = 84100.0, 59400.0
OFFSET = (500000.0, 300000.0)  # where the frame block's geometry sits in block coordinates
R = 400.0
TH = 350.0
SHEET2_X = 90000.0


def _frame_block(doc: Any) -> None:
    blk = doc.blocks.new("TB_FRAME")
    ox, oy = OFFSET
    blk.add_lwpolyline(
        [(ox, oy), (ox + FRAME_W, oy), (ox + FRAME_W, oy + FRAME_H), (ox, oy + FRAME_H)], close=True
    )
    blk.add_lwpolyline(
        [
            (ox + 2000, oy + 1000),
            (ox + FRAME_W - 1000, oy + 1000),
            (ox + FRAME_W - 1000, oy + FRAME_H - 1000),
            (ox + 2000, oy + FRAME_H - 1000),
        ],
        close=True,
    )
    tx, ty = ox + FRAME_W - 15000, oy + 3000
    blk.add_text("SHEET NO.", height=TH, dxfattribs={"insert": (tx, ty)})
    blk.add_attdef("SHEET_NO", (tx + 5000, ty), dxfattribs={"height": TH})
    blk.add_text("REV", height=TH, dxfattribs={"insert": (tx, ty + 1000)})
    blk.add_attdef("REV", (tx + 5000, ty + 1000), dxfattribs={"height": TH})
    blk.add_text("DATE", height=TH, dxfattribs={"insert": (tx, ty + 2000)})
    blk.add_text("TEMPLATE-ONLY", height=TH, dxfattribs={"insert": (tx + 3000, ty + 2000)})
    blk.add_text("SCALE", height=TH, dxfattribs={"insert": (tx, ty + 3000)})


def _bubble_block(doc: Any) -> None:
    blk = doc.blocks.new("AXIS_BUBBLE")
    blk.add_circle((0, 0), R)
    blk.add_attdef("AXIS_NO", (0, 0), dxfattribs={"height": TH}).set_placement(
        (0, 0), align=TextEntityAlignment.MIDDLE_CENTER
    )


def _level_block(doc: Any) -> None:
    blk = doc.blocks.new("LVL_MARK")
    blk.add_solid([(0, 0), (-250, 250), (250, 250)])
    blk.add_line((-300, 250), (1200, 250))


def _frame(msp: Any, x: float, number: str, rev: str) -> None:
    ins = msp.add_blockref("TB_FRAME", (x - OFFSET[0], -OFFSET[1]))
    ins.add_auto_attribs({"SHEET_NO": number, "REV": rev})
    tx, ty = x + FRAME_W - 15000, 3000
    msp.add_text("1:100", height=TH, dxfattribs={"insert": (tx + 3000, ty + 3000)})


def _bubble_insert(msp: Any, c: tuple[float, float], label: str) -> None:
    ins = msp.add_blockref("AXIS_BUBBLE", c)
    ins.add_auto_attribs({"AXIS_NO": label})


def _bubble_loose(msp: Any, c: tuple[float, float], label: str | None) -> None:
    msp.add_circle(c, R, dxfattribs={"layer": "AXIS_BUBBLES"})
    if label is not None:
        msp.add_text(label, height=TH, dxfattribs={"layer": "AXIS_BUBBLES"}).set_placement(
            c, align=TextEntityAlignment.MIDDLE_CENTER
        )


def _grid(msp: Any, x0: float, xs: list[float], loose_horizontal: bool) -> list[float]:
    """Vertical axes at x0 + 10000 + xs, horizontal axes at y 10000 / 15000 / 19500. Returns world xs."""
    gx = [x0 + 10000 + v for v in xs]
    ys = [10000.0, 15000.0, 19500.0]
    attribs = {"layer": "S-GRID", "linetype": "DASHDOT"}
    y_lo, y_hi = 7000.0, 22500.0
    for label, x in zip(("1", "2", "3", "4"), gx, strict=True):
        msp.add_line((x, y_lo), (x, y_hi), dxfattribs=attribs)
        _bubble_insert(msp, (x, y_lo - R), label)
    x_lo, x_hi = gx[0] - 3000, gx[-1] + 3000
    for label, y in zip(("A", "B", "C"), ys, strict=True):
        msp.add_line((x_lo, y), (x_hi, y), dxfattribs=attribs)
        if loose_horizontal:
            _bubble_loose(msp, (x_lo - R, y), label)
        else:
            _bubble_insert(msp, (x_lo - R, y), label)
    return gx


def _level(msp: Any, at: tuple[float, float], text: str) -> None:
    msp.add_text(text, height=TH, dxfattribs={"insert": at})


def build_set(tmp_path: Path, name: str = "set.dxf", *, sheet2_number: str = "S-102") -> Path:
    doc = new("R2018", setup=True)
    doc.header["$INSUNITS"] = 4
    doc.layers.add("S-GRID")
    doc.layers.add("AXIS_BUBBLES")
    _frame_block(doc)
    _bubble_block(doc)
    _level_block(doc)
    msp = doc.modelspace()

    # sheet 1
    _frame(msp, 0.0, "S-101", "A")
    gx = _grid(msp, 0.0, [0, 6000, 12000, 18000], loose_horizontal=True)
    # skewed axis '5': from near axis 4 bottom, 10 degrees off vertical
    sx, sy = gx[3] + 3000, 7000.0
    length = 15500.0
    ex, ey = sx + length * math.sin(math.radians(10)), sy + length * math.cos(math.radians(10))
    msp.add_line((sx, sy), (ex, ey), dxfattribs={"layer": "S-GRID", "linetype": "DASHDOT"})
    ux, uy = math.sin(math.radians(10)), math.cos(math.radians(10))
    _bubble_insert(msp, (sx - R * ux, sy - R * uy), "5")
    # dimensions along the vertical family (measured across x)
    msp.add_linear_dim(
        base=(gx[0], 4000), p1=(gx[0], 7000), p2=(gx[1], 7000), text="6500", dimstyle="Standard"
    ).render()
    msp.add_linear_dim(base=(gx[1], 4000), p1=(gx[1], 7000), p2=(gx[2], 7000), dimstyle="Standard").render()
    _level(msp, (40000, 40000), "+0.000")
    _level(msp, (40000, 43000), "+3.600")
    msp.add_blockref("LVL_MARK", (39800, 43000 - 250))
    _level(msp, (40000, 46000), "+7.200")
    _level(msp, (50000, 43000), "TẦNG 2 +3.600")

    # sheet 2
    _frame(msp, SHEET2_X, sheet2_number, "A")
    gx2 = _grid(msp, SHEET2_X, [0, 6000, 12000, 18500], loose_horizontal=False)
    x5 = gx2[3] + 6000
    msp.add_line((x5, 7000), (x5, 22500), dxfattribs={"layer": "S-GRID", "linetype": "DASHDOT"})
    _bubble_loose(msp, (x5, 7000 - R), None)
    _level(msp, (SHEET2_X + 40000, 43000), "TẦNG 2 +3.650")
    _level(msp, (SHEET2_X + 40000, 46000), "+7.200")

    # model note outside both frames, shown by the layout's viewport
    msp.add_text("GENERAL NOTE", height=TH, dxfattribs={"insert": (300000, 1000)})

    # paper-space sheet with an ATTRIB title block, no frame rectangle
    plot = doc.layouts.new("Plot")
    tb = doc.blocks.new("TB_PAPER")
    tb.add_attdef("SHEET_NO", (0, 0), dxfattribs={"height": 3.5})
    tb.add_attdef("REV", (0, 10), dxfattribs={"height": 3.5})
    tb.add_attdef("TITLE", (0, 20), dxfattribs={"height": 3.5})
    ref = plot.add_blockref("TB_PAPER", (700, 20))
    ref.add_auto_attribs({"SHEET_NO": "S-201", "REV": "B", "TITLE": "GENERAL NOTES"})
    plot.add_viewport(center=(300, 300), size=(400, 200), view_center_point=(300000, 1000), view_height=4000)
    return _save(doc, tmp_path / name)


def _save(doc: Any, path: Path) -> Path:
    doc.saveas(path)
    return path
