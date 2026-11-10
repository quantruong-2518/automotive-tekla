"""Synthetic title blocks for the sheets tests of tool wave 4 (package S).

The cell layout copies the proportions of a real two-row title block (a job cell above a drawing-number
cell, the value of each centred in its cell and set larger than its label) without any of its text.
Units are mm; every frame is a plain closed rectangle, so no frame block is involved.
"""

from __future__ import annotations

from typing import Any

from ezdxf.enums import TextEntityAlignment
from ezdxf.filemanagement import new

FW, FH = 84100.0, 59469.0  # an A1-shaped frame (ratio 1.414)
LABEL_H, VALUE_H = 328.0, 574.0
# cell origin, relative to the frame's lower left corner
CELL = (FW - 14000.0, 1500.0)


def add_frame(msp: Any, x: float, y: float = 0.0, notes: int = 8) -> None:
    msp.add_lwpolyline([(x, y), (x + FW, y), (x + FW, y + FH), (x, y + FH)], close=True)
    for i in range(notes):
        msp.add_text(f"NOTE {i}", height=350, dxfattribs={"insert": (x + 3000, y + 6000 + i * 1200)})


def _centred(msp: Any, text: str, at: tuple[float, float], height: float) -> None:
    msp.add_text(text, height=height).set_placement(at, align=TextEntityAlignment.CENTER)


def add_cells(msp: Any, x: float, y: float) -> None:
    """The cell lines of the two-row title block whose lower left corner is (x, y)."""
    w, h1, h2 = 12667.0, 1508.0, 4020.0
    for ly, x1 in ((0.0, x + w), (h1, x + w), (h2, x + w)):
        msp.add_line((x, y + ly), (x1, y + ly))
    msp.add_line((x, y), (x, y + h2))
    msp.add_line((x + w, y), (x + w, y + h2))
    msp.add_line((x + 9046.0, y + h1), (x + 9046.0, y + h2))


def add_title_block(
    msp: Any,
    frame_x: float,
    number: str,
    job: str,
    *,
    frame_y: float = 0.0,
    number_label: str = "DRAWING NO.:",
    job_label: str = "JOB NO.:",
    lines: bool = True,
) -> None:
    """Drawing-number cell (label top left, value centred below-right) under a job cell (same pattern)."""
    cx, cy = frame_x + CELL[0], frame_y + CELL[1]
    if lines:
        add_cells(msp, cx, cy)
    msp.add_text(number_label, height=LABEL_H, dxfattribs={"insert": (cx + 413.0, cy + 936.0)})
    _centred(msp, number, (cx + 7460.0, cy + 456.0), VALUE_H)
    msp.add_text(job_label, height=LABEL_H, dxfattribs={"insert": (cx + 413.0, cy + 3448.0)})
    _centred(msp, job, (cx + 4641.0, cy + 1910.0), VALUE_H)


def sheet_set(frames: int = 2) -> tuple[Any, Any]:
    doc = new("R2018", setup=True)
    doc.header["$INSUNITS"] = 4
    return doc, doc.modelspace()
