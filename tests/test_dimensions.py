"""dimensions: `harness dimensions`, every DIMENSION of one drawing with what it measures and prints.

The world is `_dxf_fixtures.build_set` (sheet 1 has a dimension overridden to '6500' over 6000 and a
measured one) plus, invented here: an override dimension inside a block inside a block (INSERT scale 1),
an angular dimension, a dimension outside every sheet and one in the paper-space layout 'Plot'."""

from __future__ import annotations

import hashlib
import json
import re
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
from tekla_harness.text_gate import meaning_block_reason

DIM_LAYER = "S-DIM"
NESTED_AT = (20000.0, 30000.0)
MOVED_TEXT_AT = (11000.0, 1500.0)
ZERO_HOST = "S-DIM-HOST"  # layer of the INSERT whose block content is on layer 0
ZERO_AT = (60000.0, 20000.0)
TOTAL = 9


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
    # layer 0 inside blocks takes the layer of the INSERT that places it (AutoCAD's rule), recursively:
    # DIMS_ZERO's dimension is on layer 0; DIMS_ZERO_OUTER places it once on layer 0 (so the outer
    # INSERT's layer ZERO_HOST applies) and once on S-DIM
    doc.layers.add(ZERO_HOST)
    zero = doc.blocks.new("DIMS_ZERO")
    zero.add_linear_dim(
        base=(0, 1000), p1=(0, 0), p2=(2500, 0), text="1234", dimstyle="Standard", dxfattribs={"layer": "0"}
    ).render()
    zero_outer = doc.blocks.new("DIMS_ZERO_OUTER")
    zero_outer.add_blockref("DIMS_ZERO", (0, 0), dxfattribs={"layer": "0"})
    zero_outer.add_blockref("DIMS_ZERO", (0, 3000), dxfattribs={"layer": DIM_LAYER})
    msp.add_blockref("DIMS_ZERO_OUTER", ZERO_AT, dxfattribs={"layer": ZERO_HOST})
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


def test_layer_zero_in_a_block_takes_the_layer_of_its_insert(base, doc):
    """The schema has one layer field: it holds the effective layer (the stored one is not reported)."""
    zero = rows(doc, text="1234")
    assert sorted(r["layer"] for r in zero) == [DIM_LAYER, ZERO_HOST]
    assert all(r["block_path"] == ["DIMS_ZERO_OUTER", "DIMS_ZERO"] for r in zero)
    (top,) = rows(doc, text="6500")
    assert top["layer"] == "0" and top["block_path"] == []  # layer 0 at top level stays 0
    host = dimensions(base / "work", REL, layer=ZERO_HOST.lower(), input_dir=base / "input")
    assert [r["text"] for r in host["dimensions"]] == ["1234"]


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
    assert {r["sheet"] for r in on["dimensions"]} == {"model#01"} and on["counts"]["matched"] == 7
    assert on["counts"]["dimensions"] == TOTAL
    off = dimensions(work, REL, unassigned=True, input_dir=inp)
    assert [r["sheet"] for r in off["dimensions"]] == [None] and off["query"]["unassigned"] is True
    layer = dimensions(work, REL, layer="s-dim", input_dir=inp)
    assert {r["layer"] for r in layer["dimensions"]} == {DIM_LAYER} and layer["counts"]["matched"] == 3
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


# --- review fixes: block content is measured on its definition, a disagreement is never 'ok' -----------

ROT_AT = (40000.0, 30000.0)
ROT_LENGTH = 4000.0
BLOCKED_STYLE = "VntimeH"  # font vntimeh.shx: encoding unknown, so non-ASCII text is blocked
BLOCKED_TEXT = "250 cöa"  # as sample 270's '250 cöa' (TCVN3 for 'cửa'), invented here
TEXT_TWIN_AT = (ROT_AT[0] + 3125.0, 25501.875)  # ezdxf's text midpoint of the '250' dimension


def build_rotated_dxf(base: Path) -> Path:
    """A linear dimension with no stored angle (group 50 absent, as in sample 270's block *U1792) in a
    block inserted at rotation 90, once directly and once inside an outer block, plus once scaled by 2.
    The virtual copy of a rotated one measures about 0 (ezdxf projects it on the default angle 0)."""
    root = base / "input"
    (root / "plans").mkdir(parents=True)
    doc = readfile(str(build_set(base, "src.dxf")))
    block = doc.blocks.new("ROT_DIM")
    for y, text in ((0.0, "<>"), (1000.0, "4100")):
        dim = block.add_linear_dim(
            base=(0, y + 500), p1=(0, y), p2=(ROT_LENGTH, y), text=text, dimstyle="Standard"
        )
        dim.render()
        dim.dimension.dxf.actual_measurement = ROT_LENGTH  # group 42, as 270 stores it
    outer = doc.blocks.new("ROT_OUTER")
    outer.add_blockref("ROT_DIM", (0, 0), dxfattribs={"rotation": 90})
    msp = doc.modelspace()
    msp.add_blockref("ROT_DIM", ROT_AT, dxfattribs={"rotation": 90})
    msp.add_blockref("ROT_OUTER", (ROT_AT[0] + 10000, ROT_AT[1]))
    msp.add_blockref("ROT_DIM", (ROT_AT[0], ROT_AT[1] + 10000), dxfattribs={"xscale": 2, "yscale": 2})
    # a measured-text dimension whose group 42 contradicts its geometry (270 has 4 such angular ones)
    bad = msp.add_linear_dim(base=(ROT_AT[0], 20500), p1=(ROT_AT[0], 20000), p2=(ROT_AT[0] + 1000, 20000))
    bad.render()
    bad.dimension.dxf.actual_measurement = 1500.0
    # override texts in a legacy font whose encoding is unknown: blocked by the text gate
    doc.styles.add(BLOCKED_STYLE, font="vntimeh.shx")
    # a TEXT with the same words at the '250' dimension's text midpoint: only DIMENSION entries link
    msp.add_text("250", height=100, dxfattribs={"insert": TEXT_TWIN_AT})
    for x, text in ((0, BLOCKED_TEXT), (3000, "250")):
        msp.add_linear_dim(
            base=(ROT_AT[0] + x, 25500),
            p1=(ROT_AT[0] + x, 25000),
            p2=(ROT_AT[0] + x + 250, 25000),
            text=text,
            dimstyle="Standard",
            override={"dimtxsty": BLOCKED_STYLE},
        ).render()
    doc.saveas(root / REL)
    # ezdxf always writes group 50 (angle 0.0) of a rotated dimension; 270 omits it: drop it as 270 does
    path = root / REL
    pattern = r"\n 50\n0\.0\n(100\nAcDbRotatedDimension\n)"
    text, n = re.subn(pattern, r"\n\1", path.read_text(encoding="utf-8"))
    assert n >= 2
    path.write_text(text, encoding="utf-8")
    return root


@pytest.fixture(scope="module")
def rot_base(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("rot")
    inp = build_rotated_dxf(root)
    work = root / "work"
    run_intake(inp, work, "demo-rot", knowledge=PROPOSED_FONT_TABLE)
    write_structure(inp, work)
    return root


@pytest.fixture(scope="module")
def rot(rot_base) -> dict[str, Any]:
    return dimensions(rot_base / "work", REL, input_dir=rot_base / "input")


def index_entries(base: Path) -> list[dict[str, Any]]:
    text = (base / "work" / "text" / f"{REL}.json").read_text(encoding="utf-8")
    return [e for e in json.loads(text)["entries"] if e["entity_type"] == "DIMENSION"]


def test_block_content_is_measured_on_its_definition_not_on_the_rotated_copy(rot):
    """Review F2 item 2: on 270 the copy of a rotated INSERT measured 2.9e-08 against group 42 = 4000
    with status 'ok'. The definition is measured; the copy still gives the layout, sheet and layer."""
    assert validate("dimensions", rot) == []
    inside = [r for r in rot["dimensions"] if r["block_path"]]
    assert len(inside) == 6  # two dimensions x three INSERT occurrences
    for r in inside:
        assert r["measured"] == pytest.approx(ROT_LENGTH)
        assert r["measurement_agrees"] is True
        assert r["handle"] is None  # a placement of the definition, not the definition itself
        assert r["layout"] == "Model" and r["sheet"] == "model#01"
    assert {tuple(r["block_path"]) for r in inside} == {("ROT_DIM",), ("ROT_OUTER", "ROT_DIM")}
    over = [r for r in inside if r["text"] == "4100"]
    assert {r["status"] for r in over} == {"override_differs"}
    assert all(r["expected_text_value"] == pytest.approx(ROT_LENGTH) for r in over)
    assert {r["status"] for r in inside if r["text"] == "<>"} == {"ok"}


def test_every_disagreeing_row_is_not_compared_whatever_its_text_rule(rot):
    """The module docstring's promise: a measurement group 42 contradicts is never reported 'ok'."""
    (bad,) = [r for r in rot["dimensions"] if r["actual_measurement"] == 1500.0]
    assert bad["text_rule"] == "measured" and bad["measurement_agrees"] is False
    assert bad["status"] == "not_compared" and "group 42" in bad["note"]
    for r in rot["dimensions"]:
        if r["measurement_agrees"] is False:
            assert r["status"] == "not_compared" and r["note"]


def test_an_override_text_the_gate_blocks_is_linked_and_not_read(rot, rot_base):
    """Review F2 item 4: '250 cöa' in a legacy font was echoed raw with nothing saying it is blocked.
    The row names its text-index entry and the gate's verdict; its value is not read."""
    by_text = {e["raw_text"]: e for e in index_entries(rot_base) if not e["block_path"]}
    (blocked,) = rows(rot, text=BLOCKED_TEXT)
    reason = meaning_block_reason(by_text[BLOCKED_TEXT])  # the knowledge table proposes this font's row
    assert reason is not None
    assert blocked["text_entry"] == {
        "entry_id": by_text[BLOCKED_TEXT]["id"],
        "meaning": "blocked",
        "block_reason": reason,
    }
    assert blocked["status"] == "not_compared" and blocked["override_value"] is None
    assert blocked["expected_text_value"] is None and blocked["tolerance"] is None
    assert "blocked" in blocked["note"] and reason in blocked["note"]
    index = json.loads((rot_base / "work" / "text" / f"{REL}.json").read_text(encoding="utf-8"))
    (twin,) = [e for e in index["entries"] if e["entity_type"] == "TEXT" and e["raw_text"] == "250"]
    assert twin["position"]["x"] == pytest.approx(by_text["250"]["position"]["x"])  # precondition: a tie
    assert twin["position"]["y"] == pytest.approx(by_text["250"]["position"]["y"])
    (plain,) = rows(rot, text="250")  # ASCII in the same font: allowed, compared as before
    assert plain["text_entry"] == {
        "entry_id": by_text["250"]["id"],
        "meaning": "allowed",
        "block_reason": None,
    }
    assert plain["status"] == "ok" and plain["override_value"] == 250.0
    assert validate("dimensions", rot) == []


def test_every_dimension_text_links_its_own_text_index_entry(rot, rot_base):
    """Block content too: each placement of a block's override text is its own index entry."""
    entries = index_entries(rot_base)
    over = [r for r in rot["dimensions"] if r["text"] == "4100"]
    ids = [r["text_entry"]["entry_id"] for r in over]
    assert len(set(ids)) == len(over) == 3
    by_id = {e["id"]: e for e in entries}
    assert sorted(tuple(by_id[i]["block_path"]) for i in ids) == sorted(tuple(r["block_path"]) for r in over)
    # two placements of ROT_DIM: the rotated one at ROT_AT, the scaled one 10000 higher; each its own entry
    rotated, scaled = [by_id[r["text_entry"]["entry_id"]] for r in over if r["block_path"] == ["ROT_DIM"]]
    assert rotated["position"]["y"] < ROT_AT[1] + 9000 < scaled["position"]["y"]
    for r in rot["dimensions"]:
        if r["text_rule"] in ("measured", "suppressed") and r["text"] in ("", "<>", " "):
            assert r["text_entry"] is None  # no text of its own: the index has no entry
    assert not any("no text-index entry" in w for w in rot["warnings"])


def test_a_dimension_text_missing_from_the_index_is_counted_not_dropped(rot_base, tmp_path, monkeypatch):
    """Without its index entry a text is reported (text_entry null) and counted in a warning; a blocked
    text then cannot be recognised, so the warning says the gate was not applied."""
    from tekla_harness import dimensions as dims_mod

    shutil.copytree(rot_base, tmp_path / "w")
    work, inp = tmp_path / "w" / "work", tmp_path / "w" / "input"
    path = work / "text" / f"{REL}.json"
    index = json.loads(path.read_text(encoding="utf-8"))
    kept = [e for e in index["entries"] if not (e["entity_type"] == "DIMENSION" and e["raw_text"] == "4100")]
    assert len(kept) == len(index["entries"]) - 3
    monkeypatch.setattr(dims_mod, "load_file", _with_entries(dims_mod.load_file, kept))
    out = dimensions(work, REL, input_dir=inp)
    over = [r for r in out["dimensions"] if r["text"] == "4100"]
    assert len(over) == 3 and all(r["text_entry"] is None for r in over)
    assert all(r["status"] == "override_differs" for r in over)  # read as before: nothing says blocked
    (warning,) = [w for w in out["warnings"] if "no text-index entry" in w]
    assert "3 dimension text(s)" in warning
    assert rows(out, text="250")[0]["text_entry"] is not None
    assert validate("dimensions", out) == []


def test_a_blocked_override_that_looks_numeric_is_not_read():
    """The gate wins over a value already parsed (e.g. '250' plus a non-ASCII space in a legacy font)."""
    from tekla_harness.dimensions import _gate_override

    row = {
        "text_rule": "override",
        "override_value": 250.0,
        "expected_text_value": 250.0,
        "tolerance": 0.005,
        "status": "ok",
        "note": "DIMLFAC -1 is negative",
        "text_entry": {"entry_id": "T000001", "meaning": "blocked", "block_reason": "encoding_unknown"},
    }
    _gate_override(row)
    assert (row["override_value"], row["expected_text_value"], row["tolerance"]) == (None, None, None)
    assert row["status"] == "not_compared"
    assert row["note"].startswith("the override text is blocked") and row["note"].endswith("is negative")


def _with_entries(load_file: Any, entries: list[dict[str, Any]]) -> Any:
    """load_file whose text index keeps only `entries` (the drawing's sha256 check stays real)."""

    def patched(*args: Any, **kwargs: Any) -> Any:
        loaded = load_file(*args, **kwargs)
        loaded.text_index["entries"] = entries
        return loaded

    return patched
