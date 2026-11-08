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

`build_gate_work` builds a second, smaller world for the schedule gate (tables E, F, G below).

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


# --- the schedule gate (tool wave 2, fix 8) --------------------------------------------------------
# Four line-grid tables on sheet S-101, each header cell (text, style); style BLOCKED_STYLE blocks
# non-ASCII text. KÍNH stands for a header word in a legacy font the gate blocks.
KINH = "KÍNH"
BLOCKED_H = "45ç0"  # a size cell whose text the gate blocks
BLOCKED_SUB = "(ký)"  # a second, blocked text in table E's mark-column header cell, under the keyword
# table E: keyword header, one blocked header cell that is not the mark column; row E2's h cell blocked
E_X, E_COLS = 2000.0, (3000.0, 2000.0, 2000.0, 2000.0)
E_HEADER = (("KÝ HIỆU", None), ("b", None), ("h", None), (KINH, BLOCKED_STYLE))
E_ROWS = (
    (("E1", None), ("220", None), ("300", None), ("16", None)),
    (("E2", None), ("220", None), (BLOCKED_H, BLOCKED_STYLE), ("18", None)),
    (("E3", None), ("200", None), ("400", None), ("20", None)),
)
# table F: no keyword; the mark column's header is allowed text, another header cell is blocked (it may
# be the h column: only b is named)
F_X, F_COLS = 14000.0, (3000.0, 2000.0, 2000.0)
F_HEADER = (("SỐ HIỆU", None), (KINH, BLOCKED_STYLE), ("b", None))
F_ROWS = ((("F1", None), ("16", None), ("2", None)), (("F2", None), ("18", None), ("4", None)))
# table G: no keyword; the mark column's header is blocked, the other header cell is allowed
G_X, G_COLS = 26000.0, (3000.0, 2000.0)
G_HEADER = (("Abçd", BLOCKED_STYLE), ("SL", None))
G_ROWS = ((("G1", None), ("2", None)), (("G2", None), ("4", None)))
# table H: no keyword and no blocked header text: not a schedule (as likely the space between plan lines)
H_X, H_COLS = 34000.0, (3000.0, 2000.0)
H_HEADER = (("TT", None), ("SL", None))
H_ROWS = ((("H1", None), ("2", None)), (("H2", None), ("4", None)))
GATE_TOP, GATE_ROW = 56000.0, 800.0
GATE_PLAN = ("E1(220x300)", "E2(220x450)", "E3", "F1(200x300)", "F2", "G1", "D1", "LT1", "C1")


def _styled_table(msp, x0: float, cols: tuple[float, ...], header, rows) -> None:
    _grid_lines(msp, x0, GATE_TOP, cols, len(rows) + 1, GATE_ROW)
    centres = []
    x = x0
    for w in cols:
        centres.append(x + w / 2)
        x += w
    for i, cells in enumerate((header, *rows)):
        for cx, (text, style) in zip(centres, cells, strict=True):
            _cell_text(msp, text, cx, GATE_TOP - GATE_ROW * i - GATE_ROW / 2, style)


def _swap(header, old: str, new: str):
    return tuple((new if text == old else text, style) for text, style in header)


def build_gate_work(
    base: Path,
    plan_texts: tuple[str, ...] = GATE_PLAN,
    *,
    blocked_word: str = KINH,
    g_mark_header: str = "Abçd",
) -> Path:
    """Tables E, F, G, H and `plan_texts` on sheet S-101: `base/input` and `base/work` (intake + sheets).
    Returns the work folder; the DXF is native (lines need --input-dir). `blocked_word` replaces KÍNH in
    the E and F headers and `g_mark_header` table G's mark-column header (both in BLOCKED_STYLE)."""
    root = base / "input"
    (root / "plans").mkdir(parents=True)
    doc = readfile(str(build_set(base, "src.dxf")))
    doc.styles.add(BLOCKED_STYLE, font="vntimeh.shx")
    msp = doc.modelspace()
    _styled_table(msp, E_X, E_COLS, _swap(E_HEADER, KINH, blocked_word), E_ROWS)
    msp.add_text(BLOCKED_SUB, height=TH / 2, dxfattribs={"style": BLOCKED_STYLE}).set_placement(
        (E_X + E_COLS[0] / 2, GATE_TOP - GATE_ROW * 0.85), align=TextEntityAlignment.MIDDLE_CENTER
    )
    _styled_table(msp, F_X, F_COLS, _swap(F_HEADER, KINH, blocked_word), F_ROWS)
    _styled_table(msp, G_X, G_COLS, _swap(G_HEADER, "Abçd", g_mark_header), G_ROWS)
    _styled_table(msp, H_X, H_COLS, H_HEADER, H_ROWS)
    for i, text in enumerate(plan_texts):
        msp.add_text(text, height=TH, dxfattribs={"insert": (PLAN_X, PLAN_TOP - i * PLAN_STEP)})
    doc.saveas(root / REL)
    work = base / "work"
    run_intake(root, work, PROJECT, knowledge=PROPOSED_FONT_TABLE)
    write_structure(root, work)
    return work
