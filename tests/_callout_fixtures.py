"""A real intake work folder around one synthetic drawing set, for sheet_text / callouts.

`build_work` takes `_dxf_fixtures.build_set` (two framed model sheets, printed numbers S-101 / S-102, and a
paper-space sheet S-201), adds callout-like texts (invented here, none from sample drawings) to each sheet,
runs the real `run_intake` and writes the real sheets document (`extract_sheets`) under `structure/`.
The input folder is `input/plans/set.dxf`, so the inventory path is `plans/set.dxf`.

Texts of sheet 1 (S-101) are placed in one column at x = 62000, y = 57000 downwards in steps of 500 (text
height 350, so every text is its own reading-order row); two extra texts share a row at the top.
"""

from __future__ import annotations

import json
from pathlib import Path

from ezdxf.filemanagement import readfile

from _dxf_fixtures import build_set
from tekla_harness.intake import dump_json, run_intake
from tekla_harness.knowledge import FontEncodingRow, FontEncodingTable
from tekla_harness.sheets import extract_sheets

# The fixtures need a font whose non-ASCII text is blocked and which carries a proposed knowledge
# row (vntimeh.shx). They pin this table instead of the shipped `knowledge/font-encodings.csv`, whose
# rows the engineer approves over time: approving a row must not change what these fixtures test.
PROPOSED_FONT_TABLE = FontEncodingTable(
    (FontEncodingRow(2, "vntimeh.shx", "font_file", "tcvn3", None, "proposed", "test row", "tests", "", ""),)
)

REL = "plans/set.dxf"
COLUMN_X = 62000.0
TOP_Y = 57000.0
STEP = 500.0

# (text as stored in the DXF)
S1_TEXTS = [
    "4%%c16",  # COUNT_DIA
    "%%c8a150",  # DIA_SPACING
    "%%c8a100/200",  # DIA_SPACING with a middle spacing
    "13%%c8a100",  # count in front of a spacing form
    "4%%c18 + 2%%c16",  # plus join
    "%%c8@150",  # '@' spacing
    "%%c8A150",  # capital A spacing
    "L=1800",  # bar length
    "2%%c16 L=1800",  # a verified callout and an ambiguous length in one line
    "%%c10",  # diameter sign + number only
    "%%c8a1",  # near miss: spacing needs 2-3 digits
    "A4%%c16",  # glued to a word: no candidate
    "⌀16",  # diameter sign U+2300 is not in the verified set: no candidate
    "CB300-V",
    "CB400V",
    "CB240-T",
    "CB350-V",  # near miss
    "CB240-V",  # near miss: pair not in the verified grade list
    "CII",
    "A-III",
    "AIII",
    "CCT34",
    "XCT 38",
    "CCT52",  # near miss
    "CCT38Mn",
    "SS400",
    "Q235B",
    "S355JR",
    "2 L 65 x 8",
    "L100x100x10",
    "457x191x82 UB",
    "H300x150x6.5x9",
    "I300",
    "HEA 300",
    "W14x90",
    "PL 12x200x450",
    "BM12",
    "4M20 8.8",
    "M20",
    "BOLT 10.9 M24",
    "8.8",  # a bare class is not a bolt
    "lỗ %%c22",
    "C1",
    "C2",
    "D1",
    "DP1",
    "GM1",
    "M1",
    "Đ1",
    "KC-01",  # a sheet code, not a member
    "S1 (h=120)",  # not the whole text of a mark: no candidate
]
S1_ROW_PAIR = [("ROW-B", COLUMN_X + 4000.0, TOP_Y + 1000.0), ("ROW-A", COLUMN_X, TOP_Y + 920.0)]
# styles: (name, font file)
STYLES = [
    ("VntimeH", "vntimeh.shx"),  # unknown encoding
    (".VnTimeH", "vntimeh.ttf"),  # TCVN3 capital font
]
# (text, style) placed after the plain column
STYLED = [
    ("4Ø16", "VntimeH"),  # literal O-stroke in an unknown encoding
    ("4%%c16", "VntimeH"),  # the same through %%c: fine
    ("d1", ".VnTimeH"),  # lowercase ASCII in a capital font: case uncertain
    ("4%%c16 t\u00aan", "VntimeH"),  # non-ASCII that cannot prove Unicode, in an unknown encoding
]
S2_TEXTS = ["4%%c16", "C1", "TB-01", "%%c8a150"]
PAPER_TEXTS = ["2%%c14", "C3"]


def build_work(
    base: Path,
    *,
    s1: list[str] | None = None,
    styled: list[tuple[str, str]] | None = None,
    s2: list[str] | None = None,
    paper: list[str] | None = None,
) -> Path:
    """Build `base/input` and `base/work`; returns the work folder. The text lists default to the
    module constants (a smaller set is used to generate the schema examples)."""
    root = base / "input"
    (root / "plans").mkdir(parents=True)
    src = build_set(base, "src.dxf")
    doc = readfile(str(src))
    for name, font in STYLES:
        doc.styles.add(name, font=font)
    msp = doc.modelspace()
    y = TOP_Y
    for text in S1_TEXTS if s1 is None else s1:
        msp.add_text(text, height=350, dxfattribs={"insert": (COLUMN_X, y)})
        y -= STEP
    for text, style in STYLED if styled is None else styled:
        msp.add_text(text, height=350, dxfattribs={"insert": (COLUMN_X, y), "style": style})
        y -= STEP
    for text, x, yy in S1_ROW_PAIR:
        msp.add_text(text, height=350, dxfattribs={"insert": (x, yy)})
    for i, text in enumerate(S2_TEXTS if s2 is None else s2):
        msp.add_text(text, height=350, dxfattribs={"insert": (90000.0 + 62000.0, TOP_Y - i * STEP)})
    plot = doc.layouts.get("Plot")
    for i, text in enumerate(PAPER_TEXTS if paper is None else paper):
        plot.add_text(text, height=3.5, dxfattribs={"insert": (100.0, 250.0 - 10 * i)})
    doc.saveas(root / REL)
    (root / "notes.txt").write_text("not a drawing", encoding="utf-8")
    work = base / "work"
    run_intake(root, work, "demo-callouts", knowledge=PROPOSED_FONT_TABLE)
    write_structure(root, work)
    return work


def write_structure(root: Path, work: Path) -> None:
    """What `read-structure` would write for sheets, without grids and levels (those extractors change
    independently of these readers): `structure/<path>.sheets.json` only."""
    index = json.loads((work / "text" / f"{REL}.json").read_text(encoding="utf-8"))
    sheets = extract_sheets(root / REL, index)
    target = work / "structure" / f"{REL}.sheets.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dump_json(sheets), encoding="utf-8")
