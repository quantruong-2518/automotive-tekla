"""dimensions: `harness dimensions`, every DIMENSION of one drawing with what it measures and prints.

The world is `_dxf_fixtures.build_set` (sheet 1 has a dimension overridden to '6500' over 6000 and a
measured one) plus, invented here: an override dimension inside a block inside a block (INSERT scale 1),
an angular dimension, a dimension outside every sheet and one in the paper-space layout 'Plot'."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from ezdxf.filemanagement import readfile

from _callout_fixtures import PROPOSED_FONT_TABLE, REL, write_structure
from _dxf_fixtures import build_set
from tekla_harness.answers import record_answer
from tekla_harness.cli import main
from tekla_harness.dimensions import dimensions
from tekla_harness.intake import run_intake
from tekla_harness.schemas import validate
from tekla_harness.sheet_text import ReaderError

DIM_LAYER = "S-DIM"
NESTED_AT = (20000.0, 30000.0)
MOVED_TEXT_AT = (11000.0, 1500.0)
TOTAL = 7


def build_dims_dxf(base: Path) -> Path:
    root = base / "input"
    (root / "plans").mkdir(parents=True)
    doc = readfile(str(build_set(base, "src.dxf")))
    doc.layers.add(DIM_LAYER)
    inner = doc.blocks.new("DIMS_INNER")
    inner.add_linear_dim(
        base=(0, 1000),
        p1=(0, 0),
        p2=(3000, 0),
        text="3500",
        dimstyle="Standard",
        dxfattribs={"layer": DIM_LAYER},
    ).render()
    outer = doc.blocks.new("DIMS_OUTER")
    outer.add_blockref("DIMS_INNER", (100, 100))
    msp = doc.modelspace()
    msp.add_blockref("DIMS_OUTER", NESTED_AT)
    msp.add_angular_dim_2l(
        base=(30500, 30500),
        line1=((30000, 30000), (31000, 30000)),
        line2=((30000, 30000), (31000, 31000)),
        dimstyle="EZ_CURVED",
        dxfattribs={"layer": DIM_LAYER},
    ).render()
    msp.add_linear_dim(
        base=(250000, 101000), p1=(250000, 100000), p2=(252000, 100000), dimstyle="Standard"
    ).render()
    # measured points below every sheet, its text moved onto sheet 1: the text decides the sheet
    msp.add_linear_dim(
        base=(10000, -19000),
        p1=(10000, -20000),
        p2=(12000, -20000),
        location=MOVED_TEXT_AT,
        dimstyle="Standard",
    ).render()
    doc.layouts.get("Plot").add_linear_dim(
        base=(100, 120), p1=(100, 100), p2=(150, 100), dimstyle="Standard"
    ).render()
    doc.add_xref_def("other.dxf", "XREF1")  # an INSERT the walk cannot expand: reported, not dropped
    msp.add_blockref("XREF1", (0, 0))
    doc.saveas(root / REL)
    return root


@pytest.fixture(scope="module")
def base(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("dims")
    inp = build_dims_dxf(root)
    work = root / "work"
    run_intake(inp, work, "demo-dims", knowledge=PROPOSED_FONT_TABLE)
    write_structure(inp, work)
    return root


@pytest.fixture
def world(base, tmp_path) -> tuple[Path, Path]:
    shutil.copytree(base, tmp_path / "w")
    return tmp_path / "w" / "input", tmp_path / "w" / "work"


@pytest.fixture(scope="module")
def doc(base) -> dict[str, Any]:
    return dimensions(base / "work", REL, input_dir=base / "input")


def rows(doc: dict[str, Any], **match: Any) -> list[dict[str, Any]]:
    return [r for r in doc["dimensions"] if all(r[k] == v for k, v in match.items())]


def test_document_is_schema_valid_and_counts_add_up(doc):
    assert validate("dimensions", doc) == []
    c = doc["counts"]
    assert c["dimensions"] == c["matched"] == c["returned"] == len(doc["dimensions"]) == TOTAL
    assert (c["omitted"], c["truncated"]) == (0, False)
    assert sum(c["by_status"].values()) == sum(c["by_text_rule"].values()) == TOTAL
    assert doc["warnings"] == [f"{REL}: some INSERTs were not expanded: {{'xref': 1}}"]
    assert doc["query"] == {"sheet": None, "unassigned": False, "layer": None, "max": None}
    assert doc["file"] == REL and doc["project_id"] == "demo-dims"


def test_measured_value_next_to_the_override_text(doc):
    (over,) = rows(doc, text="6500")
    assert over["text_rule"] == "override" and over["status"] == "override_differs"
    assert over["measured"] == pytest.approx(6000.0) and over["override_value"] == 6500.0
    assert over["expected_text_value"] == pytest.approx(6000.0)
    assert over["sheet"] == "model#01" and over["layout"] == "Model" and over["block_path"] == []
    assert over["handle"] is not None
    plain = [r for r in rows(doc, sheet="model#01", block_path=[]) if r["text_rule"] == "measured"]
    assert any(r["dim_type"] == "linear" and r["measured"] == pytest.approx(6000.0) for r in plain)


def test_a_dimension_nested_in_inserts_carries_its_block_path(doc):
    (nested,) = rows(doc, block_path=["DIMS_OUTER", "DIMS_INNER"])
    assert nested["handle"] is None  # a virtual copy: its definition has the handle
    assert nested["layout"] == "Model" and nested["sheet"] == "model#01"
    assert nested["text"] == "3500" and nested["override_value"] == 3500.0
    assert nested["measured"] == pytest.approx(3000.0) and nested["status"] == "override_differs"
    assert nested["layer"] == DIM_LAYER


def test_angular_values_are_as_declared_never_converted(doc):
    (ang,) = rows(doc, dim_type="angular")
    assert ang["measured"] == pytest.approx(45.0)  # degrees, as ezdxf measures; no unit applied
    assert doc["units"] == {"declared": "mm", "answered": None, "converted": False}


def test_sheet_of_each_dimension(doc):
    assert {r["sheet"] for r in doc["dimensions"]} == {"model#01", "Plot#01", None}
    (paper,) = rows(doc, sheet="Plot#01")
    assert paper["layout"] == "Plot"
    (off,) = rows(doc, sheet=None)
    assert off["layout"] == "Model"
    (moved,) = [r for r in doc["dimensions"] if r["measured"] == pytest.approx(2000.0) and r["sheet"]]
    assert moved["sheet"] == "model#01"  # its text is on sheet 1, its measured points on no sheet


def test_filters_and_true_counts(base):
    work, inp = base / "work", base / "input"
    on = dimensions(work, REL, sheet="model#01", input_dir=inp)
    assert {r["sheet"] for r in on["dimensions"]} == {"model#01"} and on["counts"]["matched"] == 5
    assert on["counts"]["dimensions"] == TOTAL
    off = dimensions(work, REL, unassigned=True, input_dir=inp)
    assert [r["sheet"] for r in off["dimensions"]] == [None] and off["query"]["unassigned"] is True
    layer = dimensions(work, REL, layer="s-dim", input_dir=inp)
    assert {r["layer"] for r in layer["dimensions"]} == {DIM_LAYER} and layer["counts"]["matched"] == 2
    assert layer["query"]["layer"] == "s-dim"
    cut = dimensions(work, REL, max_rows=1, input_dir=inp)
    c = cut["counts"]
    assert (c["matched"], c["returned"], c["omitted"], c["truncated"]) == (TOTAL, 1, TOTAL - 1, True)
    assert sum(c["by_status"].values()) == TOTAL  # over the matched rows, not the returned ones
    assert any(f"--max {TOTAL}" in w for w in cut["warnings"])
    full = dimensions(work, REL, max_rows=TOTAL, input_dir=inp)
    assert full["counts"]["truncated"] is False and not any("--max" in w for w in full["warnings"])
    for d in (on, off, layer, cut, full):
        assert validate("dimensions", d) == []


def test_block_content_keeps_the_conservative_measure_flags(base, monkeypatch):
    """Only a dimension placed directly in model space may prove a negative DIMLFAC means factor 1."""
    from tekla_harness import dimensions as dims_mod
    from tekla_harness.read_dxf import measure_dimension

    calls: list[dict[str, Any]] = []

    def spy(dim: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return measure_dimension(dim, **kwargs)

    monkeypatch.setattr(dims_mod, "measure_dimension", spy)
    dimensions(base / "work", REL, input_dir=base / "input")
    flags = {(c["layout"], c["is_model"], c["in_block"], c["handles_ok"]) for c in calls}
    assert flags == {("Model", True, False, True), ("Model", False, True, True), ("Plot", False, False, True)}


def test_units_declared_unknown_is_null(world):
    inp, work = world
    path = work / "inventory.json"
    inv = json.loads(path.read_text(encoding="utf-8"))
    (row,) = [r for r in inv["files"] if r["path"] == REL]
    row["units"]["value"] = "unknown"
    path.write_text(json.dumps(inv), encoding="utf-8")
    assert dimensions(work, REL, input_dir=inp)["units"]["declared"] is None


def test_answered_unit_reads_only_this_files_confirm_answers(world, monkeypatch):
    from tekla_harness import dimensions as dims_mod

    inp, work = world

    def answers(*items: tuple[str, str | None, dict[str, str]]) -> Any:
        doc = {
            "answers": [
                {"key": f"k{i}", "status": "active", "code": c, "file": f, "values": v}
                for i, (c, f, v) in enumerate(items)
            ]
        }
        return lambda *a, **k: type("L", (), {"answers": doc})()

    confirm = "units_confirm_all"
    cases = [
        ((confirm, "other.dxf", {"unit": "m"}), ("units_conflict", REL, {"unit": "cm"})),
        ((confirm, REL, {"unit": "mm"}), (confirm, REL, {"unit": "m"})),
        ((confirm, REL, {"unit": "furlong"}),),
    ]
    for items, warned in zip(cases, (False, True, True), strict=True):
        monkeypatch.setattr(dims_mod, "load_ledger", answers(*items))
        out = dimensions(work, REL, input_dir=inp)
        assert out["units"]["answered"] is None
        assert any("no single valid unit" in w for w in out["warnings"]) is warned


def test_a_missing_registry_leaves_the_answer_unread_with_a_warning(world):
    inp, work = world
    (work / "question-registry.json").unlink()
    out = dimensions(work, REL, input_dir=inp)
    assert out["units"]["answered"] is None
    assert any("units answer was not read" in w for w in out["warnings"])


def test_input_dir_without_the_drawing_is_a_usage_error(base, tmp_path):
    with pytest.raises(ReaderError) as exc:
        dimensions(base / "work", REL, input_dir=tmp_path)
    assert exc.value.exit_code == 2 and "DXF not found" in str(exc.value)


def test_answered_unit_is_reported_not_applied(world):
    inp, work = world
    qs = json.loads((work / "questions.json").read_text(encoding="utf-8"))["questions"]
    (q,) = [q for q in qs if q["code"] == "units_confirm_all" and q["file"] == REL]
    record_answer(work, q["id"], "mm", "A. Nguyen", {"unit": "mm"}, role="engineer")
    out = dimensions(work, REL, input_dir=inp)
    assert out["units"] == {"declared": "mm", "answered": "mm", "converted": False}
    (over,) = rows(out, text="6500")
    assert over["measured"] == pytest.approx(6000.0)


def snapshot(folder: Path) -> dict[str, str]:
    return {
        str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def test_read_only_nothing_written(world, capsys):
    inp, work = world
    before = snapshot(work)
    assert main(["dimensions", str(work), REL, "--input-dir", str(inp)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["kind"] == "dimensions" and validate("dimensions", out) == []
    assert snapshot(work) == before  # no lock file, no output


def test_native_dxf_without_input_dir_is_a_usage_error(base, capsys):
    assert main(["dimensions", str(base / "work"), REL]) == 2
    assert "--input-dir" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("extra", "code"),
    [
        (["--sheet", "model#99"], 2),
        (["--max", "0"], 2),
        (["--sheet", "model#01", "--unassigned"], 2),
    ],
)
def test_cli_usage_errors(base, capsys, extra, code):
    argv = ["dimensions", str(base / "work"), REL, "--input-dir", str(base / "input"), *extra]
    assert main(argv) == code
    assert capsys.readouterr().err


def test_file_not_in_inventory_and_folder_without_inventory(base, tmp_path):
    with pytest.raises(ReaderError) as exc:
        dimensions(base / "work", "plans/other.dxf", input_dir=base / "input")
    assert exc.value.exit_code == 2
    with pytest.raises(ReaderError) as exc:
        dimensions(tmp_path, REL)
    assert exc.value.exit_code == 2


def test_sheet_filter_needs_the_sheets_document(world):
    inp, work = world
    (work / "structure" / f"{REL}.sheets.json").unlink()
    with pytest.raises(ReaderError) as exc:
        dimensions(work, REL, input_dir=inp, sheet="model#01")
    assert exc.value.exit_code == 2
    with pytest.raises(ReaderError) as exc:
        dimensions(work, REL, input_dir=inp, unassigned=True)
    assert exc.value.exit_code == 2
    out = dimensions(work, REL, input_dir=inp)
    assert {r["sheet"] for r in out["dimensions"]} == {None}
    assert any("sheets.json is missing" in w for w in out["warnings"])
    assert validate("dimensions", out) == []


def test_a_changed_drawing_is_refused(world):
    inp, work = world
    dxf = inp / REL
    dxf.write_bytes(dxf.read_bytes() + b"\n")
    with pytest.raises(ReaderError) as exc:
        dimensions(work, REL, input_dir=inp)
    assert exc.value.exit_code == 1
