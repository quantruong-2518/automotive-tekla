"""A real intake work folder around one synthetic drawing set, for `harness marks`.

`build_marks_work` takes `_dxf_fixtures.build_set` (sheet S-101 is the model-space frame at x 0..84100) and
adds, on sheet S-101, texts and lines invented here (none from sample drawings):

  * table A, line grid of LINEs, header 'KÝ HIỆU | b | h', rows D1 220 300 / D2 220 450 / D1-1 220 350 /
    D9 200 300;
  * table B, text alignment only (no lines), steel style 'NAME | D (mm) | TW (mm) | BF (mm) | TF (mm)',
    rows C1 and C2;
  * table C, line grid drawn inside a block, header in an unknown-encoding font with non-ASCII text
    (blocked), rows D7 and D8;
  * an unreadable table: header 'MARK | QTY' with a single row B7 5;
  * plan marks in a column at x = 46000 (see PLAN_TEXTS).

It runs the real `run_intake` and writes the real sheets document (`_callout_fixtures.write_structure`);
`full=True` runs the real `read_structure` instead (grids and levels too, for `harness status`). The DXF is
native, so its lines are read only with `--input-dir`.
"""

from __future__ import annotations

from pathlib import Path

from ezdxf.enums import TextEntityAlignment
from ezdxf.filemanagement import readfile

from _callout_fixtures import PROPOSED_FONT_TABLE, REL, write_structure
from _dxf_fixtures import build_set
from tekla_harness.intake import run_intake
from tekla_harness.structure import read_structure

PROJECT = "demo-marks"
TH = 350.0
BLOCKED_STYLE = "VntimeH"  # font vntimeh.shx: encoding unknown, so non-ASCII text is blocked

# table A: line grid at x 2000.., top y 56000; column widths, row height
A_X, A_TOP, A_COLS, A_ROW = 2000.0, 56000.0, (3000.0, 2000.0, 2000.0), 800.0
A_HEADER = ("KÝ HIỆU", "b", "h")
A_ROWS = (("D1", "220", "300"), ("D2", "220", "450"), ("D1-1", "220", "350"), ("D9", "200", "300"))

# table B: text alignment, no lines
B_X, B_Y, B_DX, B_PITCH = 14000.0, 50000.0, 2000.0, 700.0
B_HEADER = ("NAME", "D (mm)", "TW (mm)", "BF (mm)", "TF (mm)")
B_ROWS = (("C1", "300", "6", "150", "8"), ("C2", "250", "5", "175", "8"))

# table C: line grid inside a block, blocked header
C_X, C_TOP, C_COLS, C_ROW = 26000.0, 56000.0, (3000.0, 2000.0), 800.0
C_HEADER = ("Ab\u00e7d", "Xy\u00e8z")  # invented non-ASCII words in an unknown-encoding font
C_ROWS = (("D7", "2"), ("D8", "4"))

# unreadable table: one data row
D_X, D_Y = 14000.0, 44000.0
D_HEADER = ("MARK", "QTY")
D_ROW = ("B7", "5")

PLAN_X, PLAN_TOP, PLAN_STEP = 46000.0, 37000.0, 600.0
PLAN_TEXTS = (
    "D1",
    "D2(220x500)",
    "D1.1(220X350)",
    "C1 (220x220)",
    "COLUMN C2",
    "DẦM D3",
    "D1a",
    "B5",
    "D7",
    "gm1",
    "KC-01",  # a sheet code
    "a200",  # a spacing
    "I300",  # a callouts section label
)


def _cell_text(msp, text: str, x: float, y: float, style: str | None = None) -> None:
    attribs = {"style": style} if style else {}
    msp.add_text(text, height=TH, dxfattribs=attribs).set_placement(
        (x, y), align=TextEntityAlignment.MIDDLE_CENTER
    )


def _grid_lines(layout, x0: float, top: float, cols: tuple[float, ...], rows: int, row_h: float) -> None:
    xs = [x0]
    for w in cols:
        xs.append(xs[-1] + w)
    ys = [top - i * row_h for i in range(rows + 1)]
    for y in ys:
        layout.add_line((xs[0], y), (xs[-1], y))
    for x in xs:
        layout.add_line((x, ys[0]), (x, ys[-1]))


def _table(msp, x0, top, cols, row_h, header, rows, style=None) -> None:
    centres = []
    x = x0
    for w in cols:
        centres.append(x + w / 2)
        x += w
    for cx, text in zip(centres, header, strict=True):
        _cell_text(msp, text, cx, top - row_h / 2, style)
    for i, row in enumerate(rows, start=1):
        for cx, text in zip(centres, row, strict=True):
            _cell_text(msp, text, cx, top - row_h * i - row_h / 2)


def build_marks_dxf(base: Path, plan_texts: tuple[str, ...] = PLAN_TEXTS) -> Path:
    root = base / "input"
    (root / "plans").mkdir(parents=True)
    doc = readfile(str(build_set(base, "src.dxf")))
    doc.styles.add(BLOCKED_STYLE, font="vntimeh.shx")
    msp = doc.modelspace()
    _grid_lines(msp, A_X, A_TOP, A_COLS, len(A_ROWS) + 1, A_ROW)
    _table(msp, A_X, A_TOP, A_COLS, A_ROW, A_HEADER, A_ROWS)
    for i, text in enumerate(B_HEADER):
        msp.add_text(text, height=TH, dxfattribs={"insert": (B_X + i * B_DX, B_Y)})
    for r, row in enumerate(B_ROWS, start=1):
        for i, text in enumerate(row):
            msp.add_text(text, height=TH, dxfattribs={"insert": (B_X + i * B_DX, B_Y - r * B_PITCH)})
    grid = doc.blocks.new("SCHED_GRID")
    _grid_lines(grid, 0.0, 0.0, C_COLS, len(C_ROWS) + 1, C_ROW)
    msp.add_blockref("SCHED_GRID", (C_X, C_TOP))
    _table(msp, C_X, C_TOP, C_COLS, C_ROW, C_HEADER, C_ROWS, style=BLOCKED_STYLE)
    for i, text in enumerate(D_HEADER):
        msp.add_text(text, height=TH, dxfattribs={"insert": (D_X + i * B_DX, D_Y)})
    for i, text in enumerate(D_ROW):
        msp.add_text(text, height=TH, dxfattribs={"insert": (D_X + i * B_DX, D_Y - B_PITCH)})
    for i, text in enumerate(plan_texts):
        msp.add_text(text, height=TH, dxfattribs={"insert": (PLAN_X, PLAN_TOP - i * PLAN_STEP)})
    doc.saveas(root / REL)
    return root


def build_marks_work(base: Path, *, full: bool = False, plan_texts: tuple[str, ...] = PLAN_TEXTS) -> Path:
    """Build `base/input` and `base/work` (intake + sheets, or the full read-structure); returns the work
    folder."""
    root = build_marks_dxf(base, plan_texts)
    work = base / "work"
    run_intake(root, work, PROJECT, knowledge=PROPOSED_FONT_TABLE)
    if full:
        read_structure(work, root)
    else:
        write_structure(root, work)
    return work
