"""The warnings of the part manifest check that read the drawings (E4b).

`grid_origin_other_block`: a hand-written grids document. `linework_duplicate`: `_dxf_fixtures.build_set`
(sheet 1 = model#01, sheet 2 = model#02 from x 90000) plus, invented here, layers of caps, piles, beams,
columns and ties drawn on sheet 1 and copied (translated by the sheet distance) to sheet 2. Both kinds of test
resolve the unit of a file from the work folder's `inventory.json`, as `harness geometry` does.
"""

from __future__ import annotations

import copy
import json
import shutil
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from ezdxf.filemanagement import readfile

from _callout_fixtures import PROPOSED_FONT_TABLE, REL, write_structure
from _dxf_fixtures import SHEET2_X, build_set
from tekla_harness import part_warnings
from tekla_harness.answers import record_answer
from tekla_harness.intake import run_intake
from tekla_harness.part_warnings import (
    PlanGrid,
    grid_origin_warnings,
    in_scope_sheets,
    plan_grid,
)

FILE = "plans.dxf"
ROW_Y = {"A": 1000.0, "B": 7100.0, "C": 14400.0}  # one row of plan sheets: y axes shared
COLUMN_X = {"1": 2000.0, "2": 9300.0}  # the columns of model#00; model#NN is shifted by NN * 100000


def axis(
    label: str | None, line: tuple[tuple[float, float], tuple[float, float]], offset: float
) -> dict[str, Any]:
    return {
        "axis_id": "G0001",
        "label": None if label is None else {"value": label},
        "offset": offset,
        "line": {"start": list(line[0]), "end": list(line[1])},
    }


def family(kind: str, axes: dict[str, float], angle: float | None = None) -> dict[str, Any]:
    """`kind` x: vertical axes (normal along x, angle 90); y: horizontal axes (normal along y, angle 0)."""
    if kind == "x":
        rows = [axis(k, ((v, 0.0), (v, 90000.0)), v - 500.0) for k, v in axes.items()]
        return {
            "family_id": "F1",
            "normal": [1.0, 0.0],
            "angle_deg": 90.0 if angle is None else angle,
            "axes": rows,
            "unlabelled_lines": [],
        }
    rows = [axis(k, ((0.0, v), (90000.0, v)), v - 1000.0) for k, v in axes.items()]
    return {
        "family_id": "F2",
        "normal": [0.0, 1.0],
        "angle_deg": 0.0 if angle is None else angle,
        "axes": rows,
        "unlabelled_lines": [],
    }


def group(
    sheet: str, *, x: dict[str, float] | None = None, y: dict[str, float] | None = None
) -> dict[str, Any]:
    """Two families. Each sheet sits at its own x (side by side in one row) unless `x` is given."""
    shift = 100000.0 * int(sheet.split("#")[1])
    cols = {k: v + shift for k, v in COLUMN_X.items()} if x is None else x
    return {
        "group_id": "V001",
        "sheet": sheet,
        "families": [family("x", cols), family("y", ROW_Y if y is None else y)],
    }


def write_grids(work: Path, groups: list[dict[str, Any]], file: str = FILE) -> None:
    path = work / "structure" / f"{file}.grids.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"schema_version": "0.1", "file": {"path": file}, "groups": groups}
    path.write_text(json.dumps(doc), encoding="utf-8")


def skip(sheet: str, reason: str) -> dict[str, str]:
    return {"code": "grid_origin_other_block", "file": FILE, "sheet": sheet, "reason": reason}


def part(pid: str, block: str | None, sheets: list[tuple[str, str]], kind: str = "member") -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": pid,
        "kind": kind,
        "order": 1,
        "sheets": [{"file": f, "sheet": s, "role": "plan"} for f, s in sheets],
    }
    if block is not None:
        row.update(block=block, family="caps")
    return row


def manifest(filing: dict[str, list[str]], file: str = FILE) -> dict[str, Any]:
    """filing: block -> sheets of `file`, one member part per block."""
    return {
        "schema_version": "0.1",
        "blocks": [{"id": b, "grid_system_ids": []} for b in filing],
        "parts": [part(f"{b}-caps", b, [(file, s) for s in sheets]) for b, sheets in filing.items()],
    }


def test_grid_origin_warns_for_two_aligned_sheets_of_another_block_and_none_own(tmp_path):
    write_grids(
        tmp_path,
        [
            group("model#01", y=ROW_Y),
            group("model#02", y={"A": 1001.0, "B": 7100.0, "C": 14400.0}),  # 1 mm off: still aligned
            group("model#03", y={"A": 1005.0, "B": 7100.0}),  # 5 mm off on a shared label: not aligned
            group("model#05", y=ROW_Y),  # listed under B2, lines up with block B1
        ],
    )
    warnings, skipped = grid_origin_warnings(
        tmp_path, manifest({"B1": ["model#01", "model#02", "model#03"], "B2": ["model#05"]})
    )
    assert skipped == []
    assert [w["id"] for w in warnings] == [f"grid_origin_other_block|{FILE}|model#05|B1"]
    w = warnings[0]
    assert (w["code"], w["part"], w["file"], w["sheet"]) == (
        "grid_origin_other_block",
        None,
        FILE,
        "model#05",
    )
    assert set(w) == {"id", "code", "part", "file", "sheet", "detail"}
    assert w["detail"] == (
        "listed under B2; aligned on y (A B C) with 2 sheet(s) of B1 (model#01, model#02), 0 of B2"
    )


def test_grid_origin_one_file_only(tmp_path):
    write_grids(tmp_path, [group("model#05")], file="plans.dxf")
    write_grids(tmp_path, [group("model#01"), group("model#02")], file="other.dxf")
    both = {
        "schema_version": "0.1",
        "blocks": [{"id": "B1", "grid_system_ids": []}, {"id": "B2", "grid_system_ids": []}],
        "parts": [
            part("B1-caps", "B1", [("other.dxf", "model#01"), ("other.dxf", "model#02")]),
            part("B2-caps", "B2", [("plans.dxf", "model#05")]),
        ],
    }
    assert grid_origin_warnings(tmp_path, both) == ([], [])


def test_grid_origin_quiet_with_one_aligned_or_any_own(tmp_path):
    write_grids(
        tmp_path,
        [
            group("model#01", y=ROW_Y),
            group("model#02", y={"A": 1005.0, "B": 7100.0}),  # 5 mm off: not aligned with model#05
            group("model#05", y=ROW_Y),
            group("model#06", y=ROW_Y),  # B2 as well: model#05 has an own aligned sheet
            group("model#07", y=ROW_Y),
        ],
    )
    # only model#01 aligns with model#05 among B1 -> quiet
    one = manifest({"B1": ["model#01", "model#02"], "B2": ["model#05"]})
    assert grid_origin_warnings(tmp_path, one) == ([], [])
    # two aligned B1 sheets, but model#05 has an own aligned sheet (model#06) -> quiet for model#05
    own = manifest({"B1": ["model#01", "model#07"], "B2": ["model#05", "model#06"]})
    assert grid_origin_warnings(tmp_path, own) == ([], [])


def test_grid_origin_quiet_when_two_blocks_share_one_row(tmp_path):
    write_grids(
        tmp_path,
        [group(f"model#0{i}", y=ROW_Y) for i in range(1, 5)],
    )
    filing = {"B1": ["model#01", "model#02"], "B2": ["model#03", "model#04"]}
    assert grid_origin_warnings(tmp_path, manifest(filing)) == ([], [])


def test_grid_origin_skips_no_several_rotated_plan_grids(tmp_path):
    one_family = {"group_id": "V9", "sheet": "model#02", "families": [family("y", ROW_Y)]}
    rotated = group("model#03")
    rotated["families"] = [family("x", COLUMN_X, angle=120.0), family("y", ROW_Y, angle=30.0)]
    wrapped = group("model#08")  # 179.6 degrees is a horizontal axis, 89.6 a vertical one
    wrapped["families"] = [family("x", COLUMN_X, angle=89.6), family("y", ROW_Y, angle=179.6)]
    big = group("model#05")
    small = group("model#05", y={"A": 1.0, "B": 2.0})
    small["families"][0]["axes"] = small["families"][0]["axes"][:1]
    tie_a, tie_b = group("model#06"), group("model#06", y={"A": 1.0, "B": 2.0, "C": 3.0})  # 5 and 5 labels
    write_grids(
        tmp_path,
        [group("model#01"), one_family, rotated, wrapped, small, big, tie_a, tie_b],
    )
    filing = {
        "B1": ["model#01", "model#02", "model#03", "model#04", "model#05", "model#06", "model#08"],
        "B2": ["model#07"],
    }
    warnings, skipped = grid_origin_warnings(tmp_path, manifest(filing))
    assert warnings == []
    assert skipped == [
        skip("model#02", "no_plan_grid"),
        skip("model#03", "rotated_grid"),
        skip("model#04", "no_plan_grid"),
        skip("model#06", "several_plan_grids"),
        skip("model#07", "no_plan_grid"),
    ]
    # the larger of two grids on one sheet (model#05) is the plan grid; 179.6 / 89.6 are not rotated
    assert isinstance(plan_grid(tmp_path, FILE, "model#05"), PlanGrid)
    assert isinstance(plan_grid(tmp_path, FILE, "model#08"), PlanGrid)


def test_missing_grids_document_is_skipped(tmp_path):
    result = grid_origin_warnings(tmp_path, manifest({"B1": ["model#01"]}))
    assert result == (
        [],
        [skip("model#01", "no_grids_document")],
    )
    assert plan_grid(tmp_path, FILE, "model#01") == "no_grids_document"


def test_plan_grid_keeps_axes_and_the_origin_axis(tmp_path):
    g = group("model#01", y={"A": 1000.0, "B": 7100.0})
    g["families"][1]["axes"].insert(0, axis(None, ((0.0, 500.0), (90000.0, 500.0)), 0.0))  # no label
    write_grids(tmp_path, [g])
    grid = plan_grid(tmp_path, FILE, "model#01")
    assert isinstance(grid, PlanGrid)
    by_dir = {f.direction: f for f in grid.families}
    assert set(by_dir) == {"x", "y"}
    assert dict(by_dir["y"].axes) == {"A": 1000.0, "B": 7100.0}
    assert dict(by_dir["x"].axes) == {k: v + 100000.0 for k, v in COLUMN_X.items()}
    ref = by_dir["y"].origin_axis
    assert ref is not None
    assert (ref.label, ref.position, ref.offset, ref.normal) == ("A", 1000.0, 0.0, 1.0)
    xref = by_dir["x"].origin_axis
    assert xref is not None and (xref.label, xref.position, xref.normal) == ("1", 102000.0, 1.0)


def test_in_scope_sheets_are_member_sheets_minus_those_in_two_blocks():
    m = {
        "schema_version": "0.1",
        "blocks": [{"id": "B1", "grid_system_ids": []}, {"id": "B2", "grid_system_ids": []}],
        "parts": [
            part("scout", None, [], kind="bookkeeping"),
            part("cross", None, [(FILE, "model#09")], kind="cross"),
            part("B1-caps", "B1", [(FILE, "model#01"), (FILE, "model#02")]),
            part("B2-caps", "B2", [(FILE, "model#02"), (FILE, "model#03")]),
            part("B2-piles", "B2", [(FILE, "model#03")]),
        ],
    }
    assert in_scope_sheets(m) == [(FILE, "model#01", "B1"), (FILE, "model#03", "B2")]


# ---- the unit of a file (both rules): inventory.json, answered else declared, never guessed ----


def read_inventory(work: Path) -> dict[str, Any]:
    return json.loads((work / "inventory.json").read_text(encoding="utf-8"))


def set_unit(work: Path, file: str, unit: str | None) -> None:
    """Rewrite the declared unit of `file` in the inventory (None: no probed units at all)."""
    inv = read_inventory(work)
    row = next(r for r in inv["files"] if r["path"] == file)
    row["units"] = None if unit is None else {**row["units"], "value": unit}
    (work / "inventory.json").write_text(json.dumps(inv), encoding="utf-8")


@pytest.fixture(autouse=True)
def _inventory(tmp_path, world):
    """A work folder made by `tmp_path` alone holds the inventory of the hand-written grids tests: the real
    intake row of the world's drawing, filed as `plans.dxf` and `other.dxf`, declared in millimetres."""
    inv = read_inventory(world)
    template = next(r for r in inv["files"] if r["path"] == REL)
    inv["files"] = [{**copy.deepcopy(template), "path": name} for name in (FILE, "other.dxf")]
    (tmp_path / "inventory.json").write_text(json.dumps(inv), encoding="utf-8")
    # a readable answers ledger: an unreadable one leaves a file without a unit
    shutil.copy(world / "question-registry.json", tmp_path / "question-registry.json")


@pytest.fixture(autouse=True)
def answered(monkeypatch) -> dict[str, str]:
    """The answered unit of each hand-written file (millimetres). A file that is not in the dict (the world's
    drawing, or one removed from it) is read from the answers ledger, as the command does."""
    units = {FILE: "mm", "other.dxf": "mm"}
    real = part_warnings._answered_unit

    def stub(inv: Any, file: str, warnings: list[str]) -> str | None:
        return units[file] if file in units else real(inv, file, warnings)

    monkeypatch.setattr(part_warnings, "_answered_unit", stub)
    return units


def unanswered(file: str) -> str:
    return f"{file}: answer the units question of `{file}` first"


def test_grid_origin_bound_follows_the_unit(tmp_path, answered):
    ys = {"A": 1000.0, "B": 7100.0}
    write_grids(
        tmp_path,
        [
            group("model#01", y=ys),
            group("model#02", y={"A": 1000.5, "B": 7100.0}),  # 0.5 off: 1 mm in drawing units of mm
            group("model#05", y=ys),
        ],
    )
    filing = manifest({"B1": ["model#01", "model#02"], "B2": ["model#05"]})
    warnings, _ = grid_origin_warnings(tmp_path, filing)
    assert [w["sheet"] for w in warnings] == ["model#05"]
    answered[FILE] = "cm"  # 1 mm is 0.1: model#02 no longer lines up, one sheet of B1 is too few
    assert grid_origin_warnings(tmp_path, filing) == ([], [])


def test_grid_origin_answered_unit_wins_over_declared(tmp_path, monkeypatch):
    ys = {"A": 1000.0, "B": 7100.0}
    write_grids(
        tmp_path,
        [group("model#01", y=ys), group("model#02", y={"A": 1000.5, "B": 7100.0}), group("model#05", y=ys)],
    )
    filing = manifest({"B1": ["model#01", "model#02"], "B2": ["model#05"]})
    monkeypatch.setattr(part_warnings, "_answered_unit", lambda inv, file, warnings: "cm")
    assert grid_origin_warnings(tmp_path, filing) == ([], [])


@pytest.mark.parametrize("declared", ["mm", "unknown", "unitless", None])
def test_grid_origin_without_an_answer_is_skipped_whatever_the_declared_unit(tmp_path, answered, declared):
    """Units come from the engineer's answer only: the declared unit is never a fall-back (D1)."""
    del answered[FILE]  # no active units answer in the ledger
    write_grids(tmp_path, [group("model#01"), group("model#02"), group("model#05")])
    set_unit(tmp_path, FILE, declared)
    notes: list[str] = []
    warnings, skipped = grid_origin_warnings(
        tmp_path, manifest({"B1": ["model#01", "model#02"], "B2": ["model#05"]}), notes
    )
    assert warnings == []
    assert skipped == [skip(s, "unit_unknown") for s in ("model#01", "model#02", "model#05")]
    assert notes == [unanswered(FILE)]


def test_the_declared_unit_does_not_change_the_bound_of_an_answered_file(tmp_path, answered):
    ys = {"A": 1000.0, "B": 7100.0}
    write_grids(
        tmp_path,
        [group("model#01", y=ys), group("model#02", y={"A": 1000.5, "B": 7100.0}), group("model#05", y=ys)],
    )
    filing = manifest({"B1": ["model#01", "model#02"], "B2": ["model#05"]})
    set_unit(tmp_path, FILE, "m")  # declared metres, answered millimetres: 1 mm is 1.0
    warnings, _ = grid_origin_warnings(tmp_path, filing)
    assert [w["sheet"] for w in warnings] == ["model#05"]


def unread_answer(inv: Any, file: str, warnings: list[str]) -> None:
    warnings.append(f"{file}: the active units_confirm_all answers give no single valid unit")


def test_file_unit_does_not_fall_back_to_the_declared_unit_after_an_unread_answer(tmp_path, monkeypatch):
    """The declared unit of `plans.dxf` is mm; an answer that cannot be read leaves no unit at all."""
    inv = part_warnings.load_inventory(tmp_path)
    assert part_warnings.file_unit(inv, FILE) == "mm"
    monkeypatch.setattr(part_warnings, "_answered_unit", unread_answer)
    notes: list[str] = []
    assert part_warnings.file_unit(inv, FILE, notes) is None
    assert notes == [f"{FILE}: the active units_confirm_all answers give no single valid unit"]
    assert part_warnings.file_unit(inv, FILE) is None  # notes are optional


def test_file_unit_without_an_answer_is_none_not_the_declared_unit(tmp_path, answered):
    """The declared unit of `plans.dxf` is mm; with no answer there is no unit, and the note says why."""
    del answered[FILE]
    inv = part_warnings.load_inventory(tmp_path)
    notes: list[str] = []
    assert part_warnings.file_unit(inv, FILE, notes) is None
    assert notes == [unanswered(FILE)]
    assert part_warnings.file_unit(inv, FILE) is None  # notes are optional
    answered[FILE] = "m"
    assert part_warnings.file_unit(inv, FILE) == "m"


def test_the_rules_skip_a_file_with_an_unread_answer_and_pass_the_notes_on(tmp_path, monkeypatch):
    monkeypatch.setattr(part_warnings, "_answered_unit", unread_answer)
    write_grids(tmp_path, [group("model#01"), group("model#02"), group("model#05")])
    notes: list[str] = []
    warnings, skipped = grid_origin_warnings(
        tmp_path, manifest({"B1": ["model#01", "model#02"], "B2": ["model#05"]}), notes
    )
    assert warnings == [] and [s["reason"] for s in skipped] == ["unit_unknown"] * 3
    assert notes == [f"{FILE}: the active units_confirm_all answers give no single valid unit"]


def test_a_note_names_the_file_when_the_ledger_text_does_not(tmp_path, monkeypatch):
    def ledger_unreadable(inv: Any, file: str, warnings: list[str]) -> None:
        warnings.append("the units answer was not read: answers.json is damaged")

    monkeypatch.setattr(part_warnings, "_answered_unit", ledger_unreadable)
    notes: list[str] = []
    assert part_warnings.file_unit(part_warnings.load_inventory(tmp_path), FILE, notes) is None
    assert notes == [f"{FILE}: the units answer was not read: answers.json is damaged"]


# ---- linework_duplicate: a drawing built with `build_set`, items copied from sheet 1 to sheet 2 ----

CODE = "linework_duplicate"
CAP, PILE, BEAM, RES, COL, TIE = "S-CAP", "S-PILE", "S-BEAM", "S-RES", "S-COL", "S-TIE"
SHEET_1, SHEET_2 = "model#01", "model#02"


def ring(cx: float, cy: float, long: float, short: float) -> list[tuple[float, float]]:
    return [
        (cx - long / 2, cy - short / 2),
        (cx + long / 2, cy - short / 2),
        (cx + long / 2, cy + short / 2),
        (cx - long / 2, cy + short / 2),
    ]


def plan_axes(kind: str, rows: list[tuple[str | None, float, float]]) -> dict[str, Any]:
    """rows: (label, position, offset from the family's first axis)."""
    if kind == "x":
        axes = [axis(lab, ((v, 0.0), (v, 50000.0)), off) for lab, v, off in rows]
        return {
            "family_id": "F1",
            "normal": [1.0, 0.0],
            "angle_deg": 90.0,
            "axes": axes,
            "unlabelled_lines": [],
        }
    axes = [axis(lab, ((0.0, v), (90000.0, v)), off) for lab, v, off in rows]
    return {"family_id": "F2", "normal": [0.0, 1.0], "angle_deg": 0.0, "axes": axes, "unlabelled_lines": []}


def world_grids() -> list[dict[str, Any]]:
    """Origin (5000, 8000) on sheet 1 and (95000, 8000) on sheet 2. The first axis of sheet 1's x family has
    no label, so its origin comes from the second axis and its offset."""
    one = [
        plan_axes("x", [(None, 5000.0, 0.0), ("1", 11000.0, 6000.0), ("2", 17000.0, 12000.0)]),
        plan_axes("y", [("A", 8000.0, 0.0), ("B", 14000.0, 6000.0)]),
    ]
    two = [
        plan_axes("x", [("1", 95000.0, 0.0), ("2", 101000.0, 6000.0), ("3", 107000.0, 12000.0)]),
        plan_axes("y", [("A", 8000.0, 0.0), ("B", 14000.0, 6000.0)]),
    ]
    return [
        {"group_id": "V1", "sheet": SHEET_1, "families": one},
        {"group_id": "V2", "sheet": SHEET_2, "families": two},
    ]


def draw_world(path: Path) -> None:
    """Items on sheet 1, copied to sheet 2 (translated by SHEET2_X) unless said otherwise."""
    doc = readfile(str(path))
    for name in (CAP, PILE, BEAM, RES, COL, TIE):
        doc.layers.add(name)
    msp = doc.modelspace()

    def outline(layer: str, cx: float, cy: float, long: float, short: float, dx: float) -> None:
        msp.add_lwpolyline(ring(cx + dx, cy, long, short), close=True, dxfattribs={"layer": layer})

    for dx in (0.0, SHEET2_X):
        for i in range(8):  # 8 caps with a pile each
            cx, cy = 10000.0 + 6000.0 * (i % 4), 12000.0 + 7000.0 * (i // 4)
            outline(CAP, cx, cy, 1700.0, 1700.0, dx)
            msp.add_circle((cx + dx, cy + 3000.0), 200.0, dxfattribs={"layer": PILE})
        for i in range(16):  # sheet 2: two of the 16 resized
            size = 1000.0 if dx and i in (3, 11) else 900.0
            outline(RES, 8000.0 + 3500.0 * (i % 8), 26000.0 + 4000.0 * (i // 8), 1500.0, size, dx)
        for i in range(9):  # 9 columns and a frame-sized outline
            outline(COL, 45000.0 + 3000.0 * (i % 3), 10000.0 + 3000.0 * (i // 3), 1000.0, 1000.0, dx)
        outline(COL, 40000.0, 30000.0, 30000.0, 20000.0, dx)
        for i in range(5):
            msp.add_circle((60000.0 + 1500.0 * i + dx, 20000.0), 150.0, dxfattribs={"layer": TIE})
    for i in range(20):  # beams: sheet 1 only
        outline(BEAM, 6000.0 + 3000.0 * i, 40000.0, 2500.0, 300.0, 0.0)
    doc.saveas(path)


@pytest.fixture(scope="module")
def world(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("linework")
    inp = root / "input"
    (inp / "plans").mkdir(parents=True)
    shutil.copy(build_set(root, "src.dxf"), inp / REL)
    draw_world(inp / REL)
    work = root / "work"
    run_intake(inp, work, "demo-warnings", knowledge=PROPOSED_FONT_TABLE)
    write_structure(inp, work)
    path = work / "structure" / f"{REL}.grids.json"
    doc = {"schema_version": "0.1", "file": {"path": REL}, "groups": world_grids()}
    path.write_text(json.dumps(doc), encoding="utf-8")
    questions = json.loads((work / "questions.json").read_text(encoding="utf-8"))["questions"]
    (units,) = [q for q in questions if q["code"] == "units_confirm_all" and q["file"] == REL]
    record_answer(work, units["id"], "mm", "A. Nguyen", {"unit": "mm"}, role="engineer")
    return work


def lw_part(
    pid: str,
    block: str,
    sheets: list[str],
    *,
    outline: list[str] | None = None,
    symbol: list[str] | None = None,
) -> dict[str, Any]:
    layers = {k: v for k, v in (("outline", outline), ("symbol", symbol)) if v}
    row = part(pid, block, [(REL, s) for s in sheets])
    row["layers"] = layers
    return row


def lw_manifest(*parts: dict[str, Any]) -> dict[str, Any]:
    blocks = sorted({p["block"] for p in parts})
    return {
        "schema_version": "0.1",
        "blocks": [{"id": b, "grid_system_ids": []} for b in blocks],
        "parts": list(parts),
    }


def run(world: Path, *parts: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return part_warnings.linework_warnings(world, lw_manifest(*parts), world.parent / "input")


def lw_skip(sheet: str, reason: str) -> dict[str, str]:
    return {"code": CODE, "file": REL, "sheet": sheet, "reason": reason}


def caps_pair() -> list[dict[str, Any]]:
    return [
        lw_part("B1-caps", "B1", [SHEET_1], outline=[CAP], symbol=[PILE]),
        lw_part("B2-caps", "B2", [SHEET_2], outline=[CAP], symbol=[PILE]),
    ]


@pytest.mark.parametrize("declared", ["mm", "unknown", None])
def test_a_file_without_an_answer_is_skipped_not_guessed(world, tmp_path, monkeypatch, declared):
    work = tmp_path / "work"
    shutil.copytree(world, work)
    (work / "answers.json").unlink()  # the units answer of the world's drawing is gone
    set_unit(work, REL, declared)
    monkeypatch.setattr(part_warnings, "read_geometry", lambda *a, **k: pytest.fail("the file was read"))
    notes: list[str] = []
    warnings, skipped = part_warnings.linework_warnings(
        work, lw_manifest(*caps_pair()), world.parent / "input", notes
    )
    assert warnings == []
    assert skipped == [lw_skip(SHEET_1, "unit_unknown"), lw_skip(SHEET_2, "unit_unknown")]
    assert notes == [unanswered(REL)]


def test_linework_duplicate_warns_for_a_copied_plan_in_another_block(world):
    warnings, skipped = run(world, *caps_pair())
    assert skipped == []
    assert [w["id"] for w in warnings] == [
        f"{CODE}|B1-caps|{REL}|{SHEET_1}|{SHEET_2}",  # both parts of the pair get a warning
        f"{CODE}|B2-caps|{REL}|{SHEET_2}|{SHEET_1}",
    ]
    first, second = warnings
    assert set(first) == {"id", "code", "part", "file", "sheet", "detail"}
    assert (first["code"], first["part"], first["file"], first["sheet"]) == (CODE, "B1-caps", REL, SHEET_1)
    assert (
        first["detail"]
        == "layers S-CAP, S-PILE: 16 of 16 items equal model#02 (B2) from the grid origin, ratio 1.000"
    )
    assert (
        second["detail"]
        == "layers S-CAP, S-PILE: 16 of 16 items equal model#01 (B1) from the grid origin, ratio 1.000"
    )


def test_linework_uses_the_part_layers_only(world):
    # sheet 1 alone carries 20 beams; a part on the beam layer must not dilute the caps' signature
    beams = lw_part("B1-beams", "B1", [SHEET_1], outline=[BEAM])
    warnings, skipped = run(world, *caps_pair(), beams)
    assert skipped == []
    assert [w["part"] for w in warnings] == ["B1-caps", "B2-caps"]
    assert all("16 of 16 items" in w["detail"] for w in warnings)


def test_linework_quiet_below_the_ratio(world):
    # 14 of 16 outlines equal after two are resized: 0.875
    res = [lw_part(f"B{n}-res", f"B{n}", [s], outline=[RES]) for n, s in ((1, SHEET_1), (2, SHEET_2))]
    assert run(world, *res) == ([], [])


def test_linework_ignores_same_block_pairs(world):
    one_block = lw_part("B1-caps", "B1", [SHEET_1, SHEET_2], outline=[CAP], symbol=[PILE])
    assert run(world, one_block) == ([], [])
    two_parts = [
        lw_part("B1-caps", "B1", [SHEET_1], outline=[CAP], symbol=[PILE]),
        lw_part("B1-more", "B1", [SHEET_2], outline=[CAP], symbol=[PILE]),
    ]
    assert run(world, *two_parts) == ([], [])


def test_linework_drops_frames_and_skips_few_items(world):
    # 9 columns and a 30000 x 20000 frame per sheet: the frame is no item, 9 is too few
    cols = [lw_part(f"B{n}-cols", f"B{n}", [s], outline=[COL]) for n, s in ((1, SHEET_1), (2, SHEET_2))]
    assert run(world, *cols) == ([], [lw_skip(SHEET_1, "few_items"), lw_skip(SHEET_2, "few_items")])
    # 5 identical ties per sheet: below the item minimum, however alike
    ties = [lw_part(f"B{n}-ties", f"B{n}", [s], symbol=[TIE]) for n, s in ((1, SHEET_1), (2, SHEET_2))]
    assert run(world, *ties) == ([], [lw_skip(SHEET_1, "few_items"), lw_skip(SHEET_2, "few_items")])


def test_linework_skips_a_sheet_without_a_plan_grid(world, tmp_path):
    work = tmp_path / "work"
    shutil.copytree(world, work)
    path = work / "structure" / f"{REL}.grids.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["groups"] = doc["groups"][:1]  # sheet 2 has no grid
    path.write_text(json.dumps(doc), encoding="utf-8")
    warnings, skipped = part_warnings.linework_warnings(
        work, lw_manifest(*caps_pair()), world.parent / "input"
    )
    assert warnings == []
    assert skipped == [lw_skip(SHEET_2, "no_plan_grid")]


def test_a_part_whose_block_is_not_a_block_id_takes_no_part_in_the_rule(world):
    """B9 is no block of the manifest: its part must not be compared, not even a sheet with itself."""
    filing = lw_manifest(*caps_pair())
    filing["parts"].append(lw_part("B9-caps", "B9", [SHEET_2], outline=[CAP], symbol=[PILE]))
    assert [b["id"] for b in filing["blocks"]] == ["B1", "B2"]
    warnings, _ = part_warnings.linework_warnings(world, filing, world.parent / "input")
    assert [w["part"] for w in warnings] == ["B1-caps", "B2-caps"]
    assert not any(w["id"].endswith(f"|{SHEET_2}|{SHEET_2}") for w in warnings)


def test_a_plan_sheet_of_a_part_with_an_unknown_block_is_no_plan_sheet_of_another_block(world):
    """model#02 is in scope through B2-caps (a schedule there); only B9-caps, whose block is no block id of
    the manifest, lists it as a plan: B1-caps must find no sheet to compare with."""
    filing = lw_manifest(*caps_pair())
    filing["parts"][1]["sheets"][0]["role"] = "schedule"
    filing["parts"].append(lw_part("B9-caps", "B9", [SHEET_2], outline=[CAP], symbol=[PILE]))
    assert part_warnings.linework_warnings(world, filing, world.parent / "input") == ([], [])


def test_linework_pairs_sheets_of_one_file_only(world, tmp_path):
    work = tmp_path / "work"
    shutil.copytree(world, work)
    inv = read_inventory(work)
    template = next(r for r in inv["files"] if r["path"] == REL)
    inv["files"].append({**copy.deepcopy(template), "path": "other.dxf"})
    (work / "inventory.json").write_text(json.dumps(inv), encoding="utf-8")
    pair = [
        lw_part("B1-caps", "B1", [SHEET_1], outline=[CAP], symbol=[PILE]),
        lw_part("B2-caps", "B2", [SHEET_2], outline=[CAP], symbol=[PILE]),
    ]
    pair[1]["sheets"][0]["file"] = "other.dxf"  # same sheet name, another file
    assert part_warnings.linework_warnings(work, lw_manifest(*pair), world.parent / "input") == ([], [])


def test_the_signature_puts_noisy_copies_in_one_cell():
    """32775.8 - 32763.3 and -88493.3 - -88505.8 are one 12.5 mm offset up to float noise."""

    def one(centre: float, origin: float) -> Counter[tuple[Any, ...]]:
        item = SimpleNamespace(kind="outline", layer="S-CAP", centre=(centre, 0.0), short=1.0, long=1.0)
        return part_warnings._signature([item], (CAP,), (origin, 0.0), 1.0, 1e9)

    assert one(32775.8, 32763.3) == one(-88493.3, -88505.8)


def test_the_signature_tells_circles_of_two_diameters_apart():
    def circle(diameter: float) -> Counter[tuple[Any, ...]]:
        item = SimpleNamespace(kind="circle", layer="S-PILE", centre=(10.0, 20.0), diameter=diameter)
        return part_warnings._signature([item], (PILE,), (0.0, 0.0), 1.0, 1e9)

    assert circle(200.0) != circle(300.0)
    assert circle(200.0) == circle(200.0)


def stub_signatures(monkeypatch, left: Counter[Any], right: Counter[Any]) -> None:
    """Sheet 1 (origin x 5000) gets `left`, sheet 2 (origin x 95000) gets `right`."""
    monkeypatch.setattr(
        part_warnings,
        "_signature",
        lambda items, layers, origin, tol, max_long: left if origin[0] < 50000.0 else right,
    )


def test_linework_ratio_of_exactly_point_nine_warns(world, monkeypatch):
    ten = Counter(range(10))
    stub_signatures(monkeypatch, ten, Counter(range(9)) + Counter({"other": 1}))  # 9 common of 10
    warnings, _ = run(world, *caps_pair())
    assert [w["part"] for w in warnings] == ["B1-caps", "B2-caps"]
    assert "9 of 10 items" in warnings[0]["detail"] and "ratio 0.900" in warnings[0]["detail"]


def test_linework_ratio_is_taken_against_the_larger_signature(world, monkeypatch):
    ten = Counter(range(10))
    stub_signatures(monkeypatch, ten, ten + Counter(range(100, 110)))  # 10 common of max(10, 20)
    assert run(world, *caps_pair()) == ([], [])
