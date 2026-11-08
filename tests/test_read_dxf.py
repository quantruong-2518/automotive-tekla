"""read_dxf: deterministic DXF probe. Fixtures are built with ezdxf inside tmp_path."""

from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path

import pytest
from ezdxf.filemanagement import new, readfile
from ezdxf.version import __version__ as EZDXF_VERSION

from tekla_harness import read_dxf
from tekla_harness.cli import main
from tekla_harness.knowledge import EMPTY_TABLE, KnowledgeError
from tekla_harness.read_dxf import (
    MAGNITUDE_MAX_M,
    MAGNITUDE_MIN_M,
    MAX_DIM_QUESTIONS,
    MAX_DIM_ROWS,
    MAX_NAMED_BLOCKS,
    probe_dxf,
)
from tekla_harness.schemas import validate
from test_knowledge import approved, row, table_of

REPO = Path(__file__).resolve().parents[1]
SAMPLES = REPO / "dwg-lab" / "samples"

AUTO = object()


def save(tmp_path, doc, name: str = "t.dxf") -> Path:
    path = tmp_path / name
    doc.saveas(path)
    return path


def make(tmp_path, build=None, *, units: int | None = 4, measurement=AUTO, name: str = "t.dxf") -> Path:
    """measurement: AUTO follows the unit system of `units`, so a fixture is self-consistent."""
    doc = new("R2018")
    if units is None:
        del doc.header["$INSUNITS"]
    else:
        doc.header["$INSUNITS"] = units
    if measurement is AUTO:
        doc.header["$MEASUREMENT"] = 0 if units in (1, 2) else 1
    elif measurement is None:
        del doc.header["$MEASUREMENT"]
    else:
        doc.header["$MEASUREMENT"] = measurement
    if build:
        build(doc)
    return save(tmp_path, doc, name)


def probe(path, **kwargs) -> dict:
    result = probe_dxf(path, **kwargs)
    assert validate("dxf-probe", result) == [], validate("dxf-probe", result)
    json.dumps(result, allow_nan=False)  # strict JSON: no NaN / Infinity anywhere
    return result


def codes(result: dict, *, blocking: bool | None = None) -> list[str]:
    return [q["code"] for q in result["questions"] if blocking is None or q["blocking"] is blocking]


def question(result: dict, code: str) -> dict:
    return next(q for q in result["questions"] if q["code"] == code)


def inject_into_entities(path: Path, raw: str) -> None:
    """Add raw group-code text at the start of the ENTITIES section."""
    text = path.read_text(encoding="utf-8")
    marker = "ENTITIES\n"
    at = text.index(marker, text.index("SECTION\n  2\nENTITIES")) + len(marker)
    path.write_text(text[:at] + raw + text[at:], encoding="utf-8")


def inject_into_objects(path: Path, raw: str) -> None:
    """Add raw group-code text at the end of the OBJECTS section (after the root dictionary)."""
    text = path.read_text(encoding="utf-8")
    end = text.index("  0\nENDSEC", text.index("SECTION\n  2\nOBJECTS\n"))
    path.write_text(text[:end] + raw + text[end:], encoding="utf-8")


def patch_header(path: Path, var: str, group: int, value: str) -> None:
    text = path.read_text(encoding="utf-8")
    pattern = rf"{re.escape(var)}\n\s*\d+\n[^\n]*\n"
    patched, n = re.subn(pattern, f"{var}\n{group:3d}\n{value}\n", text, count=1)
    assert n == 1, var
    path.write_text(patched, encoding="utf-8")


def set_header_point(path: Path, var: str, point: tuple[float, float, float]) -> None:
    """ezdxf rewrites $EXTMIN/$EXTMAX when saving, so patch the saved text."""
    lines = path.read_text(encoding="utf-8").split("\n")
    at = lines.index(var)
    for i, value in enumerate(point):
        lines[at + 2 + 2 * i] = repr(float(value))
    path.write_text("\n".join(lines), encoding="utf-8")


# --- schema ---------------------------------------------------------------------


def test_example_is_valid(example):
    assert validate("dxf-probe", example("dxf-probe")) == []


def test_ok_status_needs_all_sections(example):
    data = example("dxf-probe")
    del data["units"]
    assert validate("dxf-probe", data)


def test_unreadable_status_needs_error(example):
    data = example("dxf-probe")
    data["status"] = "unreadable"
    assert validate("dxf-probe", data)


def test_partial_status_needs_section_errors(example):
    data = example("dxf-probe")
    data["status"] = "partial"
    assert validate("dxf-probe", data)
    data["section_errors"] = [{"section": "layers", "error": "KeyError: 'x'"}]
    del data["layers"]
    assert validate("dxf-probe", data) == []


# --- file facts -----------------------------------------------------------------


def test_file_facts(tmp_path):
    path = make(tmp_path)
    result = probe(path)
    assert result["status"] == "ok"
    assert result["file"]["path"] == str(path)
    assert len(result["file"]["sha256"]) == 64
    assert result["file"]["ezdxf_version"] == EZDXF_VERSION
    assert result["file"]["dxf_version"] == "AC1032"
    assert result["file"]["handles_reliable"] is True
    assert [a["tool"] for a in result["attempts"]] == ["ezdxf"]
    assert result["attempts"][0]["status"] == "ok"
    assert "section_errors" not in result


@pytest.mark.parametrize(
    ("converter", "cap"), [(None, "high"), ("none", "high"), ("oda", "high"), ("libredwg", "medium")]
)
def test_confidence_cap_follows_converter(tmp_path, converter, cap):
    kwargs = {} if converter is None else {"converter": converter}
    result = probe(make(tmp_path), **kwargs)
    assert result["file"]["confidence_cap"] == cap
    assert result["units"]["confidence"] == "medium"  # header units alone are never 'high' (M1a)


def test_unknown_converter_rejected(tmp_path):
    with pytest.raises(ValueError, match="converter"):
        probe_dxf(make(tmp_path), converter="autocad")


# --- units ----------------------------------------------------------------------


@pytest.mark.parametrize(("code", "value"), [(1, "in"), (2, "ft"), (4, "mm"), (5, "cm"), (6, "m")])
def test_units_from_header(tmp_path, code, value):
    result = probe(make(tmp_path, units=code))
    units = result["units"]
    assert (units["value"], units["header_code"], units["source"]) == (value, code, "header")
    assert units["evidence"]
    assert units["confidence"] == "medium"
    assert "units_unknown" not in codes(result)
    assert "units_conflict" not in codes(result)


def test_known_units_always_ask_for_confirmation_non_blocking(tmp_path):
    result = probe(make(tmp_path))
    q = question(result, "units_confirm")
    assert q["blocking"] is False
    assert "$INSUNITS" in q["where"]
    assert codes(result, blocking=True) == []


def test_missing_insunits_is_unknown_and_blocking(tmp_path):
    path = make(tmp_path, units=None)
    assert "$INSUNITS" not in readfile(path).header  # the fixture really has no variable
    result = probe(path)
    assert result["units"]["value"] == "unknown"
    assert result["units"]["header_code"] is None
    assert result["units"]["confidence"] == "low"
    assert codes(result, blocking=True) == ["units_unknown"]
    assert "units_confirm" not in codes(result)


def test_insunits_zero_is_unknown_and_blocking(tmp_path):
    result = probe(make(tmp_path, units=0))
    assert result["units"]["value"] == "unknown"
    assert result["units"]["header_code"] == 0
    q = question(result, "units_unknown")
    assert q["blocking"] is True
    assert q["found"] == "0"
    assert "$INSUNITS" in q["where"]


@pytest.mark.parametrize("code", [3, 7, 13, 14, 20])
def test_units_outside_building_set_are_unknown_not_nearest(tmp_path, code):
    result = probe(make(tmp_path, units=code))
    assert result["units"]["value"] == "unknown"
    assert result["units"]["header_code"] == code
    assert "units_unknown" in codes(result, blocking=True)


@pytest.mark.parametrize("code", [-1, -20, -21, 21, 99])
def test_invalid_insunits_codes_are_unknown_with_null_code(tmp_path, code):
    # ezdxf decodes negative codes by wrapping around its list: -21 would read as 'mm'
    result = probe(make(tmp_path, units=code, measurement=1))
    units = result["units"]
    assert (units["value"], units["header_code"], units["confidence"]) == ("unknown", None, "low")
    assert any(str(code) in line for line in units["evidence"])
    assert question(result, "units_unknown")["blocking"] is True
    assert question(result, "units_unknown")["found"] == str(code)


def test_float_insunits_in_header_is_unknown(tmp_path):
    path = make(tmp_path)
    patch_header(path, "$INSUNITS", 40, "6.9")  # a float where an integer code is required
    units = probe(path)["units"]
    assert (units["value"], units["header_code"]) == ("unknown", None)
    assert any("6.9" in line for line in units["evidence"])


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(0, 0), (1, 1), (6, 6), (20, 20), (6.0, 6), (-1, None), (21, None), (6.9, None), (True, None),
     (False, None), ("6", None), (None, None), (float("nan"), None), (float("inf"), None)],
)  # fmt: skip
def test_insunits_validation(raw, expected):
    assert read_dxf._valid_insunits(raw) == expected


def test_units_never_inferred_from_geometry(tmp_path):
    def build(doc):
        doc.modelspace().add_line((0, 0), (6000, 0))

    result = probe(make(tmp_path, build, units=None))
    assert result["units"]["value"] == "unknown"
    assert result["extents"] is None  # the header holds no extents; none are recomputed from the line


# --- units trust: MEASUREMENT conflict and magnitude plausibility -----------------


def test_measurement_conflict_lowers_confidence_and_blocks(tmp_path):
    result = probe(make(tmp_path, units=6, measurement=0))  # metres declared, imperial measurement
    assert result["units"]["value"] == "m"
    assert result["units"]["confidence"] == "low"
    q = question(result, "units_conflict")
    assert q["blocking"] is True
    assert "INSUNITS=6" in q["found"]
    assert "MEASUREMENT=0" in q["found"]


def test_imperial_unit_with_metric_measurement_conflicts(tmp_path):
    result = probe(make(tmp_path, units=1, measurement=1))
    assert "units_conflict" in codes(result, blocking=True)
    assert result["units"]["confidence"] == "low"


def test_missing_measurement_is_no_conflict(tmp_path):
    result = probe(make(tmp_path, units=6, measurement=None))
    assert "units_conflict" not in codes(result)
    assert result["units"]["confidence"] == "medium"


def add_model_dims(doc, length: float, n: int = 3, **kwargs):
    for i in range(n):
        add_dim(doc, length=length + i, render=False, **kwargs)


@pytest.mark.parametrize(
    ("units", "value", "length"),
    [(6, "m", 400), (1, "in", 4400), (4, "mm", 5), (2, "ft", 5000)],  # 400 m; 112 m; 6 mm; 1.5 km
)
def test_implausible_magnitude_is_suspect_and_blocking(tmp_path, units, value, length):
    result = probe(make(tmp_path, lambda doc: add_model_dims(doc, length), units=units))
    assert result["units"]["value"] == value  # the heuristic only raises a question
    assert result["units"]["confidence"] == "low"
    q = question(result, "units_suspect")
    assert q["blocking"] is True
    assert "median" in q["found"]
    assert str(MAGNITUDE_MIN_M) in q["found"] and f"{MAGNITUDE_MAX_M:g}" in q["found"]
    assert any("median" in line for line in result["units"]["evidence"])


def test_dimension_median_is_kept_for_every_unit_and_retested_with_another_unit(tmp_path):
    result = probe(make(tmp_path, lambda doc: add_model_dims(doc, 4000), units=6))  # m declared
    median = result["units"]["dimension_median"]
    assert median == {"value": 4001.0, "count": 3}
    # the same test as units_suspect, for the unit an engineer answers instead of the declared one
    assert read_dxf.implausible_dimensions(median, "mm") is None  # 4 m
    evidence = read_dxf.implausible_dimensions(median, "m")
    assert evidence is not None and "4001 drawing units = 4001 m in m" in evidence
    assert read_dxf.implausible_dimensions(None, "m") is None
    unknown = probe(make(tmp_path, lambda doc: add_model_dims(doc, 4000), units=0, name="u.dxf"))
    assert unknown["units"]["value"] == "unknown" and unknown["units"]["dimension_median"] == median
    few = probe(make(tmp_path, lambda doc: add_model_dims(doc, 4000, n=2), name="few.dxf"))
    assert few["units"]["dimension_median"] is None


def test_plausible_magnitude_is_not_suspect(tmp_path):
    result = probe(make(tmp_path, lambda doc: add_model_dims(doc, 3000), units=4))
    assert "units_suspect" not in codes(result)
    assert result["units"]["confidence"] == "medium"
    assert any("median" in line and "3001" in line for line in result["units"]["evidence"])


def test_mm_connection_detail_is_not_suspect(tmp_path):
    # Regression: real mm steel connection details have a median dimension of ~40 mm;
    # the first lower bound (0.05 m) raised a false blocking units_suspect on them.
    result = probe(make(tmp_path, lambda doc: add_model_dims(doc, 40), units=4))
    assert "units_suspect" not in codes(result)


def test_magnitude_check_is_skipped_with_fewer_than_three_dimensions(tmp_path):
    result = probe(make(tmp_path, lambda doc: add_model_dims(doc, 400, n=2), units=6))
    assert "units_suspect" not in codes(result)
    assert any("skipped" in line and "3" in line for line in result["units"]["evidence"])


def test_magnitude_uses_actual_measurement_when_present(tmp_path):
    def build(doc):
        for _ in range(3):  # ezdxf measures 400, group 42 says 4: the stored value wins
            add_dim(doc, length=400, render=False, actual=4.0)

    result = probe(make(tmp_path, build, units=6))
    assert "units_suspect" not in codes(result)


def test_magnitude_counts_only_modelspace_linear_dimensions(tmp_path):
    def build(doc):
        add_model_dims(doc, 3000, n=3)  # plausible in mm
        for i in range(5):  # huge paper-space dims must not move the median
            add_dim(doc, length=900000 + i, layout=doc.layouts.get("Layout1"), render=False)

    result = probe(make(tmp_path, build, units=4))
    assert "units_suspect" not in codes(result)


# --- extents, layouts, viewports ------------------------------------------------


def test_extents_from_header_or_null(tmp_path):
    path = make(tmp_path)
    assert probe(path)["extents"] is None  # empty drawing: header holds the +-1e20 placeholders
    set_header_point(path, "$EXTMIN", (0, 0, 0))
    set_header_point(path, "$EXTMAX", (6000, 2000, 0))
    assert probe(path)["extents"] == {"min": [0, 0, 0], "max": [6000, 2000, 0], "source": "header"}


def add_vp(layout, view_height: float, *, vp_id: int | None = None):
    vp = layout.add_viewport(center=(5, 5), size=(10, 10), view_center_point=(0, 0), view_height=view_height)
    if vp_id is not None:
        vp.dxf.id = vp_id
    return vp


def add_overall(layout, *, vp_id: int | None = 1):
    """The paper-space viewport a real layout lists first."""
    return add_vp(layout, 10, vp_id=vp_id)


def layout1(result: dict) -> dict:
    return next(layout for layout in result["layouts"] if layout["name"] == "Layout1")


def test_layouts_and_viewports(tmp_path):
    def build(doc):
        doc.modelspace().add_line((0, 0), (1, 1))
        doc.modelspace().add_circle((0, 0), 1)
        layout = doc.layouts.get("Layout1")
        layout.add_line((0, 0), (1, 0))
        add_overall(layout)
        layout.add_viewport(center=(5, 5), size=(10, 10), view_center_point=(3, 4), view_height=100)

    result = probe(make(tmp_path, build))
    by_name = {layout["name"]: layout for layout in result["layouts"]}
    assert by_name["Model"]["is_model"] is True
    assert by_name["Model"]["entity_counts"] == {"LINE": 1, "CIRCLE": 1}
    assert by_name["Model"]["entity_total"] == 2
    paper = by_name["Layout1"]
    assert paper["is_model"] is False
    assert paper["entity_counts"]["LINE"] == 1
    overall, vp = paper["viewports"]
    assert overall["is_overall"] is True
    assert vp["scale"] == pytest.approx(0.1)
    assert vp["target"] == [0.0, 0.0, 0.0]
    assert vp["view_height"] == pytest.approx(100)
    assert vp["is_overall"] is False
    assert vp["handle"]


def test_first_viewport_is_overall_even_with_id_zero(tmp_path):
    def build(doc):
        layout = doc.layouts.get("Layout1")
        add_vp(layout, 8.5, vp_id=0)  # converted DWGs list id-0 viewports
        add_vp(layout, 500, vp_id=0)
        add_vp(layout, 250, vp_id=0)

    paper = layout1(probe(make(tmp_path, build)))
    assert [vp["is_overall"] for vp in paper["viewports"]] == [True, False, False]


def test_lone_user_viewport_with_id_two_or_more_is_not_overall(tmp_path):
    def build(doc):
        add_vp(doc.layouts.get("Layout1"), 100, vp_id=2)

    (vp,) = layout1(probe(make(tmp_path, build)))["viewports"]
    assert vp["is_overall"] is False


def test_viewport_with_zero_view_height_has_null_scale_and_reason(tmp_path):
    def build(doc):
        add_vp(doc.layouts.get("Layout1"), 0, vp_id=2)

    (vp,) = layout1(probe(make(tmp_path, build)))["viewports"]
    assert vp["scale"] is None
    assert vp["scale_note"]


def test_non_finite_viewport_numbers_become_null(tmp_path):
    def build(doc):
        vp = add_vp(doc.layouts.get("Layout1"), 100, vp_id=2)
        vp.dxf.view_target_point = (float("inf"), 0, 0)

    (vp,) = layout1(probe(make(tmp_path, build)))["viewports"]
    assert vp["target"] is None


# --- layers ---------------------------------------------------------------------


def test_layer_flags_and_separate_entity_counts(tmp_path):
    def build(doc):
        doc.layers.add("OFF", color=1).off()
        doc.layers.add("FROZEN", color=2).freeze()
        doc.layers.add("LOCKED", color=3).lock()
        doc.layers.add("USED", color=4)
        msp = doc.modelspace()
        msp.add_line((0, 0), (1, 1), dxfattribs={"layer": "USED"})
        msp.add_line((0, 0), (2, 1), dxfattribs={"layer": "USED"})
        doc.layouts.get("Layout1").add_line((0, 0), (1, 1), dxfattribs={"layer": "USED"})
        block = doc.blocks.new("B1")
        block.add_line((0, 0), (1, 1), dxfattribs={"layer": "USED"})
        block.add_line((0, 0), (1, 2), dxfattribs={"layer": "NOT_IN_TABLE"})

    result = probe(make(tmp_path, build))
    layers = {layer["name"]: layer for layer in result["layers"]}
    assert (layers["OFF"]["on"], layers["FROZEN"]["frozen"], layers["LOCKED"]["locked"]) == (
        False,
        True,
        True,
    )
    assert layers["USED"]["on"] is True
    assert layers["USED"]["entities"] == {"modelspace": 2, "layouts": 1, "blocks": 1}
    assert layers["NOT_IN_TABLE"]["defined"] is False
    assert layers["NOT_IN_TABLE"]["entities"]["blocks"] == 1
    assert layers["0"]["defined"] is True
    assert result["entities_without_layer"] == 0


def test_entity_without_layer_is_counted_not_put_on_a_fake_layer(tmp_path):
    path = make(tmp_path)
    inject_into_entities(path, "  0\nFOOBAR_THING\n  5\nF00A\n100\nAcDbEntity\n")  # no group 8
    result = probe(path)
    assert result["entities_without_layer"] == 1
    assert all(layer["name"] != "(unknown)" for layer in result["layers"])
    assert any("without a layer" in w for w in result["warnings"])
    (row,) = result["unreadable_objects"]
    assert row["dxftype"] == "FOOBAR_THING" and row["by_layer"] == {}


# --- blocks ---------------------------------------------------------------------


def test_blocks_insert_counts_and_attributes(tmp_path):
    def build(doc):
        plain = doc.blocks.new("PLAIN")
        plain.add_line((0, 0), (1, 1))
        tagged = doc.blocks.new("TAGGED")
        tagged.add_attdef("MARK", (0, 0), "?")
        unused = doc.blocks.new("UNUSED")
        unused.add_line((0, 0), (1, 1))
        msp = doc.modelspace()
        msp.add_blockref("PLAIN", (0, 0))
        msp.add_blockref("PLAIN", (5, 0))
        msp.add_blockref("TAGGED", (0, 5)).add_auto_attribs({"MARK": "C1"})
        doc.layouts.get("Layout1").add_blockref("PLAIN", (0, 0))
        nested = doc.blocks.new("NESTED")
        nested.add_blockref("PLAIN", (0, 0))

    blocks = probe(make(tmp_path, build))["blocks"]
    by_name = {b["name"]: b for b in blocks["named"]}
    assert by_name["PLAIN"] == {
        "name": "PLAIN",
        "insert_count": 4,
        "dynamic_insert_count": 0,
        "has_attdef": False,
        "has_attrib": False,
    }
    assert by_name["TAGGED"]["has_attdef"] is True
    assert by_name["TAGGED"]["has_attrib"] is True
    assert by_name["UNUSED"]["insert_count"] == 0
    assert not any(name.startswith("*") for name in by_name)
    assert blocks["truncated"] is False


def test_anonymous_blocks_are_counted_not_listed(tmp_path):
    def build(doc):
        doc.modelspace().add_linear_dim(base=(0, 3), p1=(0, 0), p2=(1000, 0)).render()

    blocks = probe(make(tmp_path, build))["blocks"]
    assert blocks["anonymous"]["count"] >= 1
    assert all(not b["name"].startswith("*") for b in blocks["named"])


def test_block_list_truncation_is_flagged_and_warned(tmp_path):
    def build(doc):
        for i in range(MAX_NAMED_BLOCKS + 3):
            doc.blocks.new(f"B{i:04d}")

    result = probe(make(tmp_path, build))
    blocks = result["blocks"]
    assert (blocks["named_total"], blocks["truncated"]) == (MAX_NAMED_BLOCKS + 3, True)
    assert len(blocks["named"]) == MAX_NAMED_BLOCKS == 500
    assert any("blocks" in w and "truncated" in w for w in result["warnings"])


def build_dynamic(doc, *, resolvable: bool = True):
    source = doc.blocks.new("DYN")
    source.add_line((0, 0), (1, 1))
    doc.appids.add("AcDbBlockRepBTag")
    for name in ("*U1", "*U2"):
        anon = doc.blocks.new(name)
        anon.add_line((0, 0), (1, 1))
        if resolvable:
            anon.block_record.set_xdata("AcDbBlockRepBTag", [(1005, source.block_record.dxf.handle)])
        doc.modelspace().add_blockref(name, (0, 0))
    doc.modelspace().add_blockref("DYN", (9, 9))


def test_dynamic_block_inserts_are_attributed_to_the_source_block(tmp_path):
    assert read_dxf._dynamic_sources(readfile(make(tmp_path, build_dynamic))) == {"*u1": "DYN", "*u2": "DYN"}
    result = probe(make(tmp_path, build_dynamic))
    (dyn,) = [b for b in result["blocks"]["named"] if b["name"] == "DYN"]
    assert dyn["insert_count"] == 3  # 1 direct + 2 through *U1 and *U2
    assert dyn["dynamic_insert_count"] == 2
    anonymous = result["blocks"]["anonymous"]
    assert anonymous["attributed_dynamic"] == 2
    assert anonymous["unresolved_dynamic"] == 0
    assert not any("dynamic" in w for w in result["warnings"])


def test_dynamic_block_true_name_xdata_is_the_fallback_source(tmp_path):
    def build(doc):
        build_dynamic(doc, resolvable=False)
        doc.appids.add("AcDbDynamicBlockTrueName")
        doc.blocks.get("*U1").block_record.set_xdata("AcDbDynamicBlockTrueName", [(1000, "DYN")])
        doc.blocks.get("*U2").block_record.set_xdata("AcDbDynamicBlockTrueName", [(1000, "NO_SUCH_BLOCK")])

    result = probe(make(tmp_path, build))
    (dyn,) = [b for b in result["blocks"]["named"] if b["name"] == "DYN"]
    assert (dyn["insert_count"], dyn["dynamic_insert_count"]) == (2, 1)  # *U2 names no existing block
    assert result["blocks"]["anonymous"]["unresolved_dynamic"] == 1


def test_unresolvable_dynamic_inserts_are_counted_and_warned(tmp_path):
    result = probe(make(tmp_path, lambda doc: build_dynamic(doc, resolvable=False)))
    (dyn,) = [b for b in result["blocks"]["named"] if b["name"] == "DYN"]
    assert (dyn["insert_count"], dyn["dynamic_insert_count"]) == (1, 0)
    anonymous = result["blocks"]["anonymous"]
    assert (anonymous["insert_count"], anonymous["unresolved_dynamic"]) == (2, 2)
    assert any("dynamic" in w and "2" in w for w in result["warnings"])


def test_dynamic_attribs_count_for_the_source_block(tmp_path):
    def build(doc):
        build_dynamic(doc)
        doc.blocks.get("DYN").add_attdef("MARK", (0, 0), "?")
        ref = doc.modelspace().add_blockref("*U2", (4, 4))
        ref.add_attrib("MARK", "X", (4, 4))

    (dyn,) = [b for b in probe(make(tmp_path, build))["blocks"]["named"] if b["name"] == "DYN"]
    assert dyn["has_attdef"] is True and dyn["has_attrib"] is True


def test_undecodable_bytes_in_a_name_are_scrubbed_with_a_warning(tmp_path):
    path = make(tmp_path, lambda doc: doc.layers.add("LAYERZZZZ"))
    path.write_bytes(path.read_bytes().replace(b"LAYERZZZZ", b"LAYER\xff\xfe"))
    result = probe(path)
    assert any(layer["name"] == "LAYER\ufffd\ufffd" for layer in result["layers"])
    assert any("not valid UTF-8" in w for w in result["warnings"])
    json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")


# --- xrefs ----------------------------------------------------------------------


def test_xref_resolution_only_next_to_the_dxf(tmp_path):
    def build(doc):
        doc.add_xref_def("present.dwg", "XR_OK")
        doc.add_xref_def("C:\\proj\\sub\\also_present.dwg", "XR_WIN")
        doc.add_xref_def("..\\elsewhere\\missing.dwg", "XR_GONE")

    (tmp_path / "present.dwg").write_bytes(b"x")
    (tmp_path / "also_present.dwg").write_bytes(b"x")
    result = probe(make(tmp_path, build))
    xrefs = {x["name"]: x for x in result["xrefs"]}
    assert xrefs["XR_OK"]["resolved"] is True
    assert xrefs["XR_WIN"]["resolved"] is True
    assert xrefs["XR_WIN"]["path"] == "C:\\proj\\sub\\also_present.dwg"
    assert xrefs["XR_GONE"]["resolved"] is False
    blocking = [q for q in result["questions"] if q["code"] == "xref_unresolved"]
    assert [q["blocking"] for q in blocking] == [True]
    assert "XR_GONE" in blocking[0]["where"]
    assert blocking[0]["found"] == "..\\elsewhere\\missing.dwg"


def test_xref_not_looked_up_in_other_folders(tmp_path):
    def build(doc):
        doc.add_xref_def("sub/deep.dwg", "XR_DEEP")

    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "deep.dwg").write_bytes(b"x")  # only reachable via the stored path
    assert probe(make(tmp_path, build))["xrefs"][0]["resolved"] is False


def test_xref_dir_replaces_the_dxf_folder_for_converted_files(tmp_path):
    def build(doc):
        doc.add_xref_def("present.dwg", "XR_OK")
        doc.add_xref_def("missing.dwg", "XR_GONE")

    original = tmp_path / "original"
    original.mkdir()
    (original / "present.dwg").write_bytes(b"x")
    converted = tmp_path / "work" / "converted"
    converted.mkdir(parents=True)
    path = make(converted, build)
    default = {x["name"]: x["resolved"] for x in probe(path)["xrefs"]}
    assert default == {"XR_OK": False, "XR_GONE": False}  # next to the converted DXF: nothing there
    result = probe(path, xref_dir=original)
    assert {x["name"]: x["resolved"] for x in result["xrefs"]} == {"XR_OK": True, "XR_GONE": False}
    (gone,) = [q for q in result["questions"] if q["code"] == "xref_unresolved"]
    assert "XR_GONE" in gone["where"] and "original" in gone["message"]


def test_xref_dir_none_keeps_looking_next_to_the_dxf(tmp_path):
    def build(doc):
        doc.add_xref_def("present.dwg", "XR_OK")

    (tmp_path / "present.dwg").write_bytes(b"x")
    assert probe(make(tmp_path, build), xref_dir=None)["xrefs"][0]["resolved"] is True


# --- text styles and encoding hints ---------------------------------------------


def test_text_styles_and_shx_flag(tmp_path):
    def build(doc):
        doc.styles.new("ROMANS", dxfattribs={"font": "romans.shx", "bigfont": "gbcbig.shx"})
        doc.styles.new("ARIAL", dxfattribs={"font": "arial.ttf"})

    styles = {s["name"]: s for s in probe(make(tmp_path, build))["text_styles"]}
    assert styles["ROMANS"]["is_shx_like"] is True
    assert styles["ROMANS"]["bigfont"] == "gbcbig.shx"
    assert styles["ARIAL"]["is_shx_like"] is False
    assert set(styles["ARIAL"]) == {"name", "font", "bigfont", "family", "is_shx_like", "capital_font"}


def test_legacy_vietnamese_fonts_are_hints_only(tmp_path):
    def build(doc):
        doc.styles.new("VNTIME", dxfattribs={"font": ".VnTime.ttf"})
        doc.styles.new("VNI", dxfattribs={"font": "VNI-Times.ttf"})
        doc.styles.new("PLAIN", dxfattribs={"font": "arial.ttf"})

    result = probe(make(tmp_path, build), knowledge=EMPTY_TABLE)
    hints = {h["style"]: h for h in result["text_encoding_hints"]}
    assert hints["VNTIME"]["encoding_hint"] == "tcvn3"
    assert hints["VNI"]["encoding_hint"] == "vni"
    assert "PLAIN" not in hints
    assert {h["kind"] for h in hints.values()} == {"hint"}
    assert {h["source"] for h in hints.values()} == {"font_hint"}
    assert {h["knowledge_pattern"] for h in hints.values()} == {None}
    assert any(q["code"] == "text_encoding_hint" and not q["blocking"] for q in result["questions"])


def test_encoding_hint_asks_once_per_style_and_lists_the_matched_fields(tmp_path):
    # Regression: a real drawing had 19 hint questions because every matching field
    # of one style raised its own question. Now: one row and one question per style.
    def build(doc):
        doc.styles.new(".VnTime", dxfattribs={"font": ".VnTime.ttf"})

    result = probe(make(tmp_path, build), knowledge=EMPTY_TABLE)
    hints = [h for h in result["text_encoding_hints"] if h["style"] == ".VnTime"]
    asked = [q for q in result["questions"] if q["code"] == "text_encoding_hint"]
    assert len(hints) == 1
    assert hints[0]["matched"] == [
        {"field": "name", "value": ".VnTime"},
        {"field": "font", "value": ".VnTime.ttf"},
    ]
    assert len(asked) == 1


def test_probe_uses_the_same_rules_as_font_hint(tmp_path):
    # One source of truth: encoding.font_hint decides, so the bigfont and the old 'vni_' / 'vni '
    # prefixes are not hints (font_hint does not use or accept them). The TrueType family is (fix 2a).
    def build(doc):
        st = doc.styles.new("VIAFAMILY", dxfattribs={"font": ""})
        st.set_extended_font_data(".VnArial")
        doc.styles.new("BIG", dxfattribs={"font": "romans.shx", "bigfont": ".VnTime.shx"})
        doc.styles.new("VNI_STYLE", dxfattribs={"font": "romans.shx"})
        doc.styles.new("VNI STYLE2", dxfattribs={"font": "romans.shx"})

    result = probe(make(tmp_path, build), knowledge=EMPTY_TABLE)
    assert [h["style"] for h in result["text_encoding_hints"]] == ["VIAFAMILY"]
    assert [q["where"] for q in result["questions"] if q["code"] == "text_encoding_hint"] == [
        "text style VIAFAMILY, family"
    ]


def test_the_ttf_family_gives_a_hint_with_its_field(tmp_path):
    def build(doc):
        doc.styles.new("kt..1", dxfattribs={"font": "VHAVAN_2.TTF"}).set_extended_font_data(".VnAvantH")
        doc.styles.new("kt..2", dxfattribs={"font": "VHAVAN_2.TTF"})  # no XDATA
        doc.styles.new(".VnTime", dxfattribs={"font": ".VnTime.ttf"}).set_extended_font_data(".VnTime")
        doc.styles.new("kt..3", dxfattribs={"font": "VHARIAL.TTF"}).set_extended_font_data("Arial")

    result = probe(make(tmp_path, build), knowledge=table_of(tmp_path, approved(pattern="VHARIAL.TTF")))
    hints = {h["style"]: h for h in result["text_encoding_hints"]}
    assert hints["kt..1"]["encoding_hint"] == "tcvn3" and hints["kt..1"]["source"] == "font_hint"
    assert hints["kt..1"]["matched"] == [{"field": "family", "value": ".VnAvantH"}]
    assert hints["kt..1"]["capital_font"] is True
    assert "kt..2" not in hints
    assert hints[".VnTime"]["matched"] == [
        {"field": "name", "value": ".VnTime"},
        {"field": "font", "value": ".VnTime.ttf"},
        {"field": "family", "value": ".VnTime"},
    ]
    # a Unicode-looking family never decides: the approved font row does
    assert hints["kt..3"]["source"] == "knowledge_table"
    assert hints["kt..3"]["matched"] == [{"field": "font", "value": "VHARIAL.TTF"}]
    styles = {s["name"]: s for s in result["text_styles"]}
    assert (styles["kt..1"]["family"], styles["kt..1"]["capital_font"]) == (".VnAvantH", True)
    assert (styles["kt..2"]["family"], styles["kt..2"]["capital_font"]) == ("", None)
    assert validate("dxf-probe", result) == []


def test_capital_font_hint_is_recorded_for_every_style(tmp_path):
    def build(doc):
        doc.styles.new(".VnTimeH", dxfattribs={"font": "vntimeh.ttf"})
        doc.styles.new(".VnTime", dxfattribs={"font": "vntime.ttf"})
        doc.styles.new("VntimeH", dxfattribs={"font": "vntimeh.shx"})  # H hint, but no encoding hint
        doc.styles.new("ARIAL", dxfattribs={"font": "arial.ttf"})

    result = probe(make(tmp_path, build), knowledge=EMPTY_TABLE)
    capital = {s["name"]: s["capital_font"] for s in result["text_styles"]}
    assert capital[".VnTimeH"] is True and capital[".VnTime"] is False
    assert capital["VntimeH"] is True  # no hint row for it, yet the capital hint is kept
    assert capital["ARIAL"] is None
    assert "VntimeH" not in {h["style"] for h in result["text_encoding_hints"]}
    hints = {h["style"]: h for h in result["text_encoding_hints"]}
    assert hints[".VnTimeH"]["capital_font"] is True and hints[".VnTime"]["capital_font"] is False


def test_approved_knowledge_row_gives_a_hint_with_provenance(tmp_path):
    def build(doc):
        doc.styles.new("kt..1", dxfattribs={"font": "VHARIAL.TTF"})

    table = table_of(tmp_path, approved(pattern="VH*.TTF", capital_font="false"))
    result = probe(make(tmp_path, build), knowledge=table)
    (hint,) = [h for h in result["text_encoding_hints"] if h["style"] == "kt..1"]
    assert hint["encoding_hint"] == "tcvn3" and hint["source"] == "knowledge_table"
    assert hint["knowledge_pattern"] == "VH*.TTF"
    assert hint["matched"] == [{"field": "font", "value": "VHARIAL.TTF"}]
    assert hint["capital_font"] is False
    assert {s["name"]: s["capital_font"] for s in result["text_styles"]}["kt..1"] is False
    assert [q["code"] for q in result["questions"] if q["code"].startswith(("text_enc", "font_enc"))] == [
        "text_encoding_hint"
    ]


def test_proposed_knowledge_row_changes_nothing_but_asks_with_its_evidence(tmp_path):
    def build(doc):
        doc.styles.new("kt..1", dxfattribs={"font": "VHARIAL.TTF"})
        doc.styles.new("kt..2", dxfattribs={"font": "VHARIALB.TTF"})
        doc.styles.new("other", dxfattribs={"font": "arial.ttf"})

    table = table_of(tmp_path, row(pattern="VH*.TTF", evidence="seen 3 times"), row(pattern="vn*.shx"))
    result = probe(make(tmp_path, build), knowledge=table)
    assert result["text_encoding_hints"] == []
    assert not [q for q in result["questions"] if q["code"] == "text_encoding_hint"]
    (question,) = [q for q in result["questions"] if q["code"] == "font_encoding_proposed"]
    assert question["blocking"] is False  # one question for the row, covering both styles
    assert "VH*.TTF" in question["where"] and "kt..1" in question["where"] and "kt..2" in question["where"]
    assert "other" not in question["where"]
    assert "seen 3 times" in question["found"] and "test" in question["found"]  # evidence and source


def test_a_positive_font_hint_is_never_overridden_by_the_table(tmp_path):
    def build(doc):
        doc.styles.new(".VnTime", dxfattribs={"font": "vntime.ttf"})
        doc.styles.new("VNI-Times", dxfattribs={"font": "vni.ttf"})

    table = table_of(
        tmp_path,
        approved(pattern="*.ttf", encoding="unicode"),
        approved(pattern=".vn*", applies_to="style_name", encoding="vni"),
        row(pattern="vni.ttf", encoding="tcvn3"),
    )
    result = probe(make(tmp_path, build), knowledge=table)
    hints = {h["style"]: h for h in result["text_encoding_hints"]}
    assert hints[".VnTime"]["encoding_hint"] == "tcvn3" and hints[".VnTime"]["source"] == "font_hint"
    assert hints["VNI-Times"]["encoding_hint"] == "vni" and hints["VNI-Times"]["source"] == "font_hint"
    assert not [q for q in result["questions"] if q["code"] == "font_encoding_proposed"]


def test_conflicting_approved_rows_leave_the_style_undecided_and_ask(tmp_path):
    def build(doc):
        doc.styles.new("S", dxfattribs={"font": "vn_vni.shx"})

    table = table_of(tmp_path, approved(pattern="vn*.shx"), approved(pattern="vn_vni.shx", encoding="vni"))
    result = probe(make(tmp_path, build), knowledge=table)
    assert result["text_encoding_hints"] == []
    (question,) = [q for q in result["questions"] if q["code"] == "font_encoding_conflict"]
    assert not question["blocking"] and "vn*.shx" in question["found"] and "vn_vni.shx" in question["found"]


def test_the_shipped_table_is_used_by_default(tmp_path):
    def build(doc):
        doc.styles.new("TKT", dxfattribs={"font": "vntimeh.shx"})

    result = probe(make(tmp_path, build))  # no knowledge argument: knowledge/font-encodings.csv
    assert not [q for q in result["questions"] if q["code"] == "font_encoding_proposed"]
    (hint,) = [h for h in result["text_encoding_hints"] if h["style"] == "TKT"]  # approved 2026-11-07
    got = (hint["encoding_hint"], hint["source"], hint["knowledge_pattern"])
    assert got == ("tcvn3", "knowledge_table", "vntimeh.shx")


def test_a_bad_default_knowledge_table_raises_instead_of_a_section_error(tmp_path, monkeypatch):
    def boom():
        raise KnowledgeError("table is malformed")

    monkeypatch.setattr(read_dxf, "default_font_encodings", boom)
    with pytest.raises(KnowledgeError, match="malformed"):
        probe_dxf(make(tmp_path))


# --- unreadable objects ---------------------------------------------------------

PROXY = (
    "  0\nACAD_PROXY_ENTITY\n  5\nF001\n100\nAcDbEntity\n  8\nPROXY_LAYER\n100\nAcDbProxyEntity\n 90\n498\n"
)
OLE = "  0\nOLE2FRAME\n  5\nF002\n100\nAcDbEntity\n  8\nOLE_LAYER\n100\nAcDbOle2Frame\n"
UNKNOWN = "  0\nFOOBAR_THING\n  5\nF003\n100\nAcDbEntity\n  8\nODD\n"
SOLID = "  0\n3DSOLID\n  5\nF006\n100\nAcDbEntity\n  8\nSOLIDS\n100\nAcDbModelerGeometry\n 70\n1\n  1\nSAT\n"
TABLE = "  0\nACAD_TABLE\n  5\nF004\n100\nAcDbEntity\n  8\nTABLE_LAYER\n100\nAcDbBlockReference\n  2\n*T1\n"
FIELD = "  0\nFIELD\n  5\nF100\n330\n0\n100\nAcDbField\n  1\n_evaluator_id\n"
SCALE_OBJ = "  0\nSCALE\n  5\nF101\n330\n0\n100\nAcDbScale\n"


def test_unreadable_objects_are_listed_explicitly(tmp_path):
    path = make(tmp_path)
    inject_into_entities(path, PROXY + PROXY.replace("F001", "F005") + OLE + UNKNOWN + TABLE + SOLID)
    result = probe(path)
    rows = {r["dxftype"]: r for r in result["unreadable_objects"]}
    assert rows["ACAD_PROXY_ENTITY"]["kind"] == "proxy"
    assert rows["ACAD_PROXY_ENTITY"]["count"] == 2
    assert rows["ACAD_PROXY_ENTITY"]["by_layer"] == {"PROXY_LAYER": 2}
    assert rows["OLE2FRAME"]["kind"] == "ole"
    assert rows["3DSOLID"]["kind"] == "acis"
    assert rows["FOOBAR_THING"]["kind"] == "unknown"
    assert rows["ACAD_TABLE"]["kind"] == "acad_table"
    assert rows["ACAD_TABLE"]["by_layer"] == {"TABLE_LAYER": 1}
    assert all(q["blocking"] is False for q in result["questions"] if q["code"] == "unreadable_objects")
    assert codes(result).count("unreadable_objects") == len(rows)


def test_clean_drawing_has_no_unreadable_objects(tmp_path):
    result = probe(make(tmp_path, lambda doc: doc.modelspace().add_line((0, 0), (1, 1))))
    assert result["unreadable_objects"] == []


def test_raw_objects_are_counted_by_type_and_only_content_bearing_ones_ask(tmp_path):
    path = make(tmp_path)
    inject_into_objects(path, FIELD + FIELD.replace("F100", "F102") + SCALE_OBJ)
    result = probe(path)
    unparsed = {r["dxftype"]: r["count"] for r in result["unparsed_objects"]}
    assert unparsed["FIELD"] == 2
    assert unparsed["SCALE"] == 1
    fields = [r for r in result["unreadable_objects"] if r["dxftype"] == "FIELD"]
    assert [(r["kind"], r["count"], r["by_layer"]) for r in fields] == [("unknown", 2, {})]
    assert not [r for r in result["unreadable_objects"] if r["dxftype"] == "SCALE"]
    assert codes(result).count("unreadable_objects") == 1


# --- dimension audit ------------------------------------------------------------


def add_dim(
    doc,
    *,
    text: str | None = None,
    length: float = 1000,
    override: dict | None = None,
    layout=None,
    render: bool = True,
    actual: float | None = None,
):
    target = doc.modelspace() if layout is None else layout
    kwargs = {} if text is None else {"text": text}
    dim = target.add_linear_dim(base=(0, 3), p1=(0, 0), p2=(length, 0), override=override, **kwargs)
    if render:
        dim.render()
    if actual is not None:
        dim.dimension.dxf.actual_measurement = actual
    return dim.dimension.dxf.handle


def add_angular(doc, *, text: str, override: dict | None = None, actual: float | None = None):
    dim = doc.modelspace().add_angular_dim_3p(
        base=(0, 5), center=(0, 0), p1=(3, 0), p2=(0, 3), text=text, override=override
    )
    dim.render()
    if actual is not None:
        dim.dimension.dxf.actual_measurement = actual
    return dim.dimension.dxf.handle


def audit_rows(result: dict) -> dict[str, dict]:
    return {row["handle"]: row for row in result["dimension_audit"]["rows"]}


def one_row(tmp_path, build) -> dict:
    handle: list[str] = []
    probe_result = probe(make(tmp_path, lambda doc: handle.append(build(doc))))
    return audit_rows(probe_result)[handle[0]]


def test_dimension_text_rules(tmp_path):
    handles: dict[str, str] = {}

    def build(doc):
        handles["measured"] = add_dim(doc)
        handles["empty_arrow"] = add_dim(doc, text="<>")
        handles["suppressed"] = add_dim(doc, text=" ")
        handles["override"] = add_dim(doc, text="1000")
        handles["with_text"] = add_dim(doc, text="<> TYP")

    result = probe(make(tmp_path, build))
    rows = audit_rows(result)
    assert rows[handles["measured"]]["text_rule"] == "measured"
    assert rows[handles["measured"]]["measured"] == pytest.approx(1000)
    assert rows[handles["empty_arrow"]]["text_rule"] == "measured"
    assert rows[handles["suppressed"]]["text_rule"] == "suppressed"
    assert rows[handles["override"]]["text_rule"] == "override"
    assert rows[handles["with_text"]]["text_rule"] == "measured_with_text"
    assert rows[handles["with_text"]]["status"] == "ok"
    assert result["dimension_audit"]["total"] == 5
    assert result["dimension_audit"]["by_text_rule"]["measured"] == 2
    assert rows[handles["override"]]["layout"] == "Model"


def test_override_that_differs_is_flagged_and_equal_is_ok(tmp_path):
    handles: dict[str, str] = {}

    def build(doc):
        handles["same"] = add_dim(doc, text="1000")
        handles["same_decimal"] = add_dim(doc, text="1000.0")
        handles["differs"] = add_dim(doc, text="1200")
        handles["rounded"] = add_dim(doc, length=1000.4, text="1000", override={"dimdec": 0})
        handles["words"] = add_dim(doc, text="TYP")
        handles["comma"] = add_dim(doc, text="1,000")
        handles["mtext"] = add_dim(doc, text="{\\A1;1000}")

    result = probe(make(tmp_path, build))
    rows = audit_rows(result)
    assert rows[handles["same"]]["status"] == "ok"
    assert rows[handles["same_decimal"]]["status"] == "ok"
    assert rows[handles["differs"]]["status"] == "override_differs"
    assert rows[handles["differs"]]["override_value"] == 1200
    assert rows[handles["rounded"]]["status"] == "ok"
    assert rows[handles["words"]]["status"] == "not_numeric"
    assert rows[handles["comma"]]["status"] == "not_numeric"  # '1,000' is ambiguous: never guessed
    assert rows[handles["mtext"]]["status"] == "ok"
    flagged = [q for q in result["questions"] if q["code"] == "dimension_override_differs"]
    assert [q["where"] for q in flagged] == [f"Model, DIMENSION {handles['differs']}"]
    assert flagged[0]["found"] == "1200"
    assert "tolerance" in result["dimension_audit"]["tolerance_rule"].lower()


def test_dimlfac_is_applied_before_comparing(tmp_path):
    handles: dict[str, str] = {}

    def build(doc):
        handles["scaled_ok"] = add_dim(doc, text="2000", override={"dimlfac": 2.0})
        handles["scaled_bad"] = add_dim(doc, text="1000", override={"dimlfac": 2.0})

    rows = audit_rows(probe(make(tmp_path, build)))
    assert rows[handles["scaled_ok"]]["status"] == "ok"
    assert rows[handles["scaled_ok"]]["expected_text_value"] == pytest.approx(2000)
    assert rows[handles["scaled_bad"]]["status"] == "override_differs"


def test_zero_dimlfac_is_not_compared(tmp_path):
    row = one_row(tmp_path, lambda doc: add_dim(doc, text="1", override={"dimlfac": 0.0}))
    assert row["status"] == "not_compared"
    assert "DIMLFAC" in row["note"]


def test_negative_dimlfac_in_modelspace_is_compared_only_with_group_42_as_proof(tmp_path):
    handles: dict[str, str] = {}

    def build(doc):
        handles["proved"] = add_dim(doc, text="1000", override={"dimlfac": -75.0}, actual=1000.0)
        handles["proved_bad"] = add_dim(doc, text="1200", override={"dimlfac": -75.0}, actual=1000.0)
        handles["unproved"] = add_dim(doc, text="1000", override={"dimlfac": -75.0})

    rows = audit_rows(probe(make(tmp_path, build)))
    assert rows[handles["proved"]]["status"] == "ok"
    assert rows[handles["proved"]]["expected_text_value"] == pytest.approx(1000)
    assert "factor 1" in rows[handles["proved"]]["note"]
    assert rows[handles["proved_bad"]]["status"] == "override_differs"
    assert rows[handles["unproved"]]["status"] == "not_compared"
    assert "DIMLFAC" in rows[handles["unproved"]]["note"]


def test_negative_dimlfac_in_a_layout_is_not_compared(tmp_path):
    row = one_row(
        tmp_path,
        lambda doc: add_dim(
            doc, text="1", override={"dimlfac": -75.0}, layout=doc.layouts.get("Layout1"), actual=1000.0
        ),
    )
    assert row["status"] == "not_compared"


def test_dimension_in_layout_and_ordinate(tmp_path):
    handles: dict[str, str] = {}

    def build(doc):
        handles["paper"] = add_dim(doc, text="999", layout=doc.layouts.get("Layout1"))
        ordinate = doc.modelspace().add_ordinate_x_dim((100, 50), (100, 80))
        ordinate.render()
        handles["ordinate"] = ordinate.dimension.dxf.handle
        overridden = doc.modelspace().add_ordinate_x_dim((100, 50), (100, 80), text="100")
        overridden.render()
        handles["ordinate_text"] = overridden.dimension.dxf.handle

    rows = audit_rows(probe(make(tmp_path, build)))
    assert rows[handles["paper"]]["layout"] == "Layout1"
    assert rows[handles["paper"]]["status"] == "override_differs"
    assert rows[handles["ordinate"]]["status"] == "ok"  # no override text: nothing to compare
    assert rows[handles["ordinate_text"]]["dim_type"] == "ordinate"
    assert rows[handles["ordinate_text"]]["status"] == "not_compared"
    assert "scalar" in rows[handles["ordinate_text"]]["note"]


def test_radius_and_diameter_overrides_are_compared(tmp_path):
    handles: dict[str, str] = {}

    def build(doc):
        radius = doc.modelspace().add_radius_dim(center=(0, 0), radius=500, angle=45, text="500")
        radius.render()
        handles["radius"] = radius.dimension.dxf.handle
        diameter = doc.modelspace().add_diameter_dim(center=(0, 0), radius=500, angle=45, text="900")
        diameter.render()
        handles["diameter"] = diameter.dimension.dxf.handle

    rows = audit_rows(probe(make(tmp_path, build)))
    assert (rows[handles["radius"]]["dim_type"], rows[handles["radius"]]["status"]) == ("radius", "ok")
    assert (rows[handles["diameter"]]["dim_type"], rows[handles["diameter"]]["status"]) == (
        "diameter",
        "override_differs",
    )


def test_linear_dimlunit_not_decimal_is_not_compared(tmp_path):
    row = one_row(tmp_path, lambda doc: add_dim(doc, text="1000", override={"dimlunit": 4}))
    assert row["status"] == "not_compared"
    assert "DIMLUNIT" in row["note"]


# angular dimensions: DIMAUNIT decides, DIMLUNIT does not
@pytest.mark.parametrize(
    ("override", "text", "status", "expected"),
    [
        ({}, "90", "ok", 90.0),
        ({}, "80", "override_differs", 90.0),
        ({"dimaunit": 2, "dimadec": 0}, "100", "ok", 100.0),  # 90 degrees = 100 grads
        ({"dimaunit": 2, "dimadec": 0}, "90", "override_differs", 100.0),
        ({"dimaunit": 3, "dimadec": 4}, "1.5708", "ok", math.pi / 2),
        ({"dimaunit": 3, "dimadec": 4}, "90", "override_differs", math.pi / 2),
        ({"dimlunit": 4}, "90", "ok", 90.0),  # DIMLUNIT is for linear dimensions only
    ],
)
def test_angular_dimensions_follow_dimaunit(tmp_path, override, text, status, expected):
    row = one_row(tmp_path, lambda doc: add_angular(doc, text=text, override=override))
    assert row["dim_type"] == "angular_3p"
    assert row["status"] == status
    assert row["expected_text_value"] == pytest.approx(expected, abs=1e-6)


@pytest.mark.parametrize(("aunit", "word"), [(1, "minutes"), (4, "surveyor")])
def test_angular_dms_and_surveyor_are_not_compared_with_the_right_reason(tmp_path, aunit, word):
    row = one_row(tmp_path, lambda doc: add_angular(doc, text="90", override={"dimaunit": aunit}))
    assert row["status"] == "not_compared"
    assert f"DIMAUNIT {aunit}" in row["note"] and word in row["note"]


# group 42 (actual measurement) cross-check
def test_group_42_is_exposed_and_agreeing_values_compare_normally(tmp_path):
    row = one_row(tmp_path, lambda doc: add_dim(doc, text="1000", actual=1000.0))
    assert row["actual_measurement"] == 1000.0
    assert row["measurement_agrees"] is True
    assert row["status"] == "ok"


def test_group_42_disagreement_makes_every_row_not_compared(tmp_path):
    """Whatever the text rule: a measurement group 42 contradicts is never 'ok' (review F2 item 2)."""
    handles: dict[str, str] = {}

    def build(doc):
        handles["linear"] = add_dim(doc, text="1000", actual=1500.0)
        handles["plain"] = add_dim(doc, actual=1500.0)
        handles["with_text"] = add_dim(doc, text="<> TYP", actual=1500.0)
        handles["suppressed"] = add_dim(doc, text=" ", actual=1500.0)
        handles["words"] = add_dim(doc, text="SEE PLAN", actual=1500.0)
        handles["angular_deg"] = add_angular(doc, text="90", actual=90.0)  # radians expected, degrees stored

    result = probe(make(tmp_path, build))
    rows = audit_rows(result)
    assert rows[handles["linear"]]["status"] == "not_compared"
    assert "actual" in rows[handles["linear"]]["note"] and "1500" in rows[handles["linear"]]["note"]
    assert rows[handles["linear"]]["measurement_agrees"] is False
    assert rows[handles["linear"]]["override_value"] == 1000.0  # the typed value is still reported
    assert rows[handles["angular_deg"]]["status"] == "not_compared"
    for name in ("plain", "with_text", "suppressed", "words"):
        assert rows[handles[name]]["measurement_agrees"] is False
        assert rows[handles[name]]["status"] == "not_compared", name
        assert "1500" in rows[handles[name]]["note"]
    assert rows[handles["words"]]["override_value"] is None
    assert any("group 42" in w and "6" in w for w in result["warnings"])


def test_group_42_may_be_geometry_times_a_positive_dimlfac(tmp_path):
    # real files store group 42 as geometry * DIMLFAC; that is consistent, not a disagreement
    handles: dict[str, str] = {}

    def build(doc):
        handles["scaled"] = add_dim(doc, text="500", override={"dimlfac": 0.5}, actual=500.0)
        handles["scaled_bad"] = add_dim(doc, text="1000", override={"dimlfac": 0.5}, actual=500.0)
        handles["raw_only"] = add_dim(doc, text="500", override={"dimlfac": 0.5}, actual=1000.0)

    rows = audit_rows(probe(make(tmp_path, build)))
    assert rows[handles["scaled"]]["measurement_agrees"] is True
    assert rows[handles["scaled"]]["status"] == "ok"
    assert rows[handles["scaled_bad"]]["status"] == "override_differs"
    assert rows[handles["raw_only"]]["status"] == "not_compared"  # geometry stored although DIMLFAC is 0.5
    assert "unclear" in rows[handles["raw_only"]]["note"]


def test_group_42_angular_in_radians_agrees(tmp_path):
    row = one_row(tmp_path, lambda doc: add_angular(doc, text="90", actual=math.pi / 2))
    assert row["measurement_agrees"] is True
    assert row["status"] == "ok"


# dimensions inside block definitions
def build_block_dims(doc):
    block = doc.blocks.new("DETAIL")
    dim = block.add_linear_dim(base=(0, 3), p1=(0, 0), p2=(1000, 0), text="1200")
    dim.render()
    block.add_linear_dim(base=(0, 3), p1=(0, 0), p2=(1000, 0)).render()
    doc.modelspace().add_blockref("DETAIL", (0, 0))
    doc.modelspace().add_blockref("DETAIL", (5000, 0))
    add_dim(doc)
    return dim.dimension.dxf.handle


def test_dimensions_in_block_definitions_are_audited_counted_and_warned(tmp_path):
    handle: list[str] = []
    result = probe(make(tmp_path, lambda doc: handle.append(build_block_dims(doc))))
    audit = result["dimension_audit"]
    assert (audit["total"], audit["in_blocks"]) == (3, 2)
    row = audit_rows(result)[handle[0]]
    assert row["layout"] == "block:DETAIL"
    assert row["status"] == "override_differs"
    flagged = question(result, "dimension_override_differs")
    assert "block:DETAIL" in flagged["where"]
    assert any("block definitions" in w and "2" in w for w in result["warnings"])


def test_no_block_dimensions_means_in_blocks_zero_and_no_warning(tmp_path):
    result = probe(make(tmp_path, lambda doc: add_dim(doc)))
    assert result["dimension_audit"]["in_blocks"] == 0
    assert not any("block definitions" in w for w in result["warnings"])


def test_measure_dimension_is_the_probe_row_without_seq(tmp_path, monkeypatch):
    """Tool wave 2 seam: the public per-dimension measurement `harness dimensions` will use."""
    from ezdxf.entities import Dimension
    from ezdxf.filemanagement import readfile

    from tekla_harness.read_dxf import measure_dimension

    handles: dict[str, str] = {}

    def build(doc):
        handles["measured"] = add_dim(doc)
        handles["differs"] = add_dim(doc, text="1200")
        handles["words"] = add_dim(doc, text="TYP")
        handles["negative"] = add_dim(doc, text="1000", override={"dimlfac": -75.0}, actual=1000.0)

    path = make(tmp_path, build)
    rows = audit_rows(probe(path))
    doc = readfile(path)

    def dim_of(handle: str) -> Dimension:
        entity = doc.entitydb[handle]
        assert isinstance(entity, Dimension)
        return entity

    for name, handle in handles.items():
        row = measure_dimension(dim_of(handle), layout="Model", is_model=True, handles_ok=True)
        assert row == {k: v for k, v in rows[handle].items() if k != "seq"}, name
    # conservative defaults: no handle, and a negative DIMLFAC is not proven outside modelspace
    row = measure_dimension(dim_of(handles["negative"]))
    assert row["handle"] is None and row["status"] == "not_compared" and row["layout"] == ""

    def boom(self):
        raise RuntimeError("bad geometry")

    monkeypatch.setattr(Dimension, "get_measurement", boom)
    row = measure_dimension(dim_of(handles["differs"]), layout="Model", is_model=True)
    assert row["status"] == "error" and row["note"] == "RuntimeError: bad geometry"
    assert row["dim_type"] == "linear" and row["text"] == "1200"


# non-finite and out-of-range numbers
def test_400_digit_override_is_not_numeric_and_output_is_strict_json(tmp_path):
    row = one_row(tmp_path, lambda doc: add_dim(doc, text="9" * 400))
    assert row["status"] == "not_numeric"
    assert row["override_value"] is None
    assert "range" in row["note"]


def test_dimdec_out_of_range_is_not_compared(tmp_path):
    row = one_row(tmp_path, lambda doc: add_dim(doc, text="1000", override={"dimdec": 99}))
    assert row["status"] == "not_compared"
    assert "DIMDEC" in row["note"]


def test_error_row_keeps_the_real_dimension_type(tmp_path, monkeypatch):
    handle: list[str] = []
    path = make(tmp_path, lambda doc: handle.append(add_dim(doc, text="1200")))

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(read_dxf, "_decimals", boom)
    result = probe(path)
    row = audit_rows(result)[handle[0]]
    assert row["status"] == "error"
    assert row["dim_type"] == "linear"
    assert "RuntimeError: boom" in row["note"]
    assert any("could not be audited" in w for w in result["warnings"])


def test_dimension_rows_are_capped_but_counts_are_full(tmp_path):
    def build(doc):
        for _ in range(MAX_DIM_ROWS + 20):
            add_dim(doc, render=False)
        add_dim(doc, text="1", render=False)  # flagged rows are listed first, so truncation cannot hide them

    result = probe(make(tmp_path, build))
    audit = result["dimension_audit"]
    assert audit["total"] == MAX_DIM_ROWS + 21
    assert MAX_DIM_ROWS == 200
    assert len(audit["rows"]) == 200
    assert audit["truncated"] is True
    assert audit["max_rows"] == 200
    assert audit["by_status"]["override_differs"] == 1
    assert audit["rows"][0]["status"] == "override_differs"
    assert any("truncated" in w for w in result["warnings"])


def test_questions_cover_all_flagged_rows_not_only_the_listed_ones(tmp_path):
    flagged = MAX_DIM_ROWS + 30

    def build(doc):
        for _ in range(flagged):
            add_dim(doc, text="1", render=False)

    result = probe(make(tmp_path, build))
    assert len(result["dimension_audit"]["rows"]) == MAX_DIM_ROWS
    assert codes(result).count("dimension_override_differs") == flagged  # 230 questions, not 200
    assert flagged < MAX_DIM_QUESTIONS


def test_question_count_is_capped_with_a_warning(tmp_path):
    def build(doc):
        for _ in range(MAX_DIM_QUESTIONS + 5):
            add_dim(doc, text="1", render=False)

    result = probe(make(tmp_path, build))
    assert codes(result).count("dimension_override_differs") == MAX_DIM_QUESTIONS == 500
    assert any("505" in w and "500" in w for w in result["warnings"])


def test_dimension_audit_empty_when_no_dimensions(tmp_path):
    audit = probe(make(tmp_path))["dimension_audit"]
    assert (audit["total"], audit["rows"], audit["truncated"], audit["in_blocks"]) == (0, [], False, 0)


# --- scales ---------------------------------------------------------------------


def test_multiple_dimscale_is_flagged(tmp_path):
    def build(doc):
        add_dim(doc, override={"dimscale": 50})
        add_dim(doc, override={"dimscale": 100})
        add_dim(doc, override={"dimscale": 100})

    result = probe(make(tmp_path, build))
    scales = result["scales"]
    assert {s["value"]: s["count"] for s in scales["dimscale"]} == {50: 1, 100: 2}
    assert scales["multiple_dimscale"] is True
    assert scales["multiple_scales"] is True
    assert "multiple_scales" in codes(result)


def test_dimscale_and_viewport_scale_are_not_pooled(tmp_path):
    def build(doc):
        add_dim(doc, override={"dimscale": 100})
        layout = doc.layouts.get("Layout1")
        add_overall(layout)
        add_vp(layout, 1000)  # scale 0.01 = 1:100, the same drawing scale as DIMSCALE 100

    result = probe(make(tmp_path, build))
    assert result["scales"]["multiple_scales"] is False
    assert [s["value"] for s in result["scales"]["viewport_scales"]] == [pytest.approx(0.01)]
    assert "multiple_scales" not in codes(result)


def test_unused_default_dimstyles_do_not_raise_the_flag(tmp_path):
    def build(doc):
        doc.dimstyles.duplicate_entry("Standard", "OTHER").dxf.dimscale = 25
        add_dim(doc)

    scales = probe(make(tmp_path, build))["scales"]
    assert scales["multiple_scales"] is False
    assert {s["name"]: s["dimscale"] for s in scales["dimstyles"]}["OTHER"] == 25


def test_multiple_viewport_scales_are_flagged(tmp_path):
    def build(doc):
        layout = doc.layouts.get("Layout1")
        add_overall(layout)
        add_vp(layout, 100)
        add_vp(layout, 200)

    result = probe(make(tmp_path, build))
    scales = result["scales"]
    assert scales["multiple_viewport_scales"] is True
    assert scales["multiple_scales"] is True
    found = question(result, "multiple_scales")["found"]
    assert len(set(found.split(", "))) == 2  # two different-looking values, never "0.01, 0.01"


def test_viewport_scales_that_differ_only_by_float_noise_are_one_scale(tmp_path):
    def build(doc):
        layout = doc.layouts.get("Layout1")
        add_overall(layout)
        add_vp(layout, 100)
        add_vp(layout, 100.0000001)

    scales = probe(make(tmp_path, build))["scales"]
    assert scales["multiple_viewport_scales"] is False
    assert [s["count"] for s in scales["viewport_scales"]] == [2]


def test_group_scales_tolerance_and_reciprocals():
    groups = read_dxf._group_scales([0.01, 0.0100001, 100.0, 0.02, 0.02])
    assert sorted(g["count"] for g in groups) == [2, 3]  # 0.01 ~ 0.0100001 ~ 100 (1:100 reciprocal); 0.02
    big = next(g for g in groups if g["count"] == 3)
    assert big["members"] == [0.01, 0.0100001, 100.0]
    assert read_dxf._group_scales([]) == []
    assert len(read_dxf._group_scales([0.01, 0.0102])) == 2  # 2 % apart is a real difference


# --- handles (R12) --------------------------------------------------------------


def make_r12(tmp_path, *, strip_handles: bool) -> Path:
    doc = new("R12")
    add_dim(doc, text="1200")
    path = save(tmp_path, doc, "r12.dxf")
    if strip_handles:
        text = path.read_text(encoding="utf-8")
        head, tables = text.split("SECTION\n  2\nTABLES", 1)  # the header's $HANDSEED also uses group 5
        text = head + "SECTION\n  2\nTABLES" + re.sub(r"(?m)^  5\n[0-9A-Fa-f]+\n", "", tables)
        text, n = re.subn(r"\$HANDLING\n\s*70\n\s*\d+\n", "$HANDLING\n 70\n     0\n", text)
        assert n == 1
        path.write_text(text, encoding="utf-8")
    return path


def test_r12_without_handles_reports_null_handles_not_synthesized_ones(tmp_path):
    result = probe(make_r12(tmp_path, strip_handles=True))
    assert result["file"]["dxf_version"] == "AC1009"
    assert result["file"]["handles_reliable"] is False
    assert any("handles" in w for w in result["warnings"])
    (row,) = result["dimension_audit"]["rows"]
    assert row["handle"] is None
    assert row["seq"] == 1
    assert "#1" in question(result, "dimension_override_differs")["where"]


def test_r12_with_real_handles_keeps_them(tmp_path):
    result = probe(make_r12(tmp_path, strip_handles=False))
    assert result["file"]["handles_reliable"] is True
    (row,) = result["dimension_audit"]["rows"]
    assert row["handle"]


# --- no section failure may crash the probe ------------------------------------


@pytest.mark.parametrize(
    ("func", "section"),
    [
        ("_layers", "layers"),
        ("_text_styles", "text_styles"),
        ("_blocks", "blocks"),
        ("_extents", "extents"),
        ("_xrefs", "xrefs"),
        ("_layouts", "layouts"),
    ],
)
def test_a_failing_section_gives_partial_status_not_a_crash(tmp_path, monkeypatch, func, section):
    def boom(*_args, **_kwargs):
        raise RuntimeError(f"{func} blew up")

    path = make(tmp_path, lambda doc: add_dim(doc))
    monkeypatch.setattr(read_dxf, func, boom)
    result = probe(path)
    assert result["status"] == "partial"
    (err,) = [e for e in result["section_errors"] if e["section"] == section]
    assert f"{func} blew up" in err["error"]
    assert section not in result  # an absent section, never an empty one that looks like a fact
    assert "units" in result  # the other sections are still there
    failed = [q for q in result["questions"] if q["code"] == "probe_section_failed"]
    assert failed and all(q["blocking"] for q in failed)


def test_failing_scan_marks_every_dependent_section(tmp_path, monkeypatch):
    def boom(_doc):
        raise RuntimeError("scan blew up")

    path = make(tmp_path)
    monkeypatch.setattr(read_dxf, "_scan", boom)
    result = probe(path)
    sections = {e["section"] for e in result["section_errors"]}
    assert {
        "scan",
        "layouts",
        "layers",
        "blocks",
        "unreadable_objects",
        "dimension_audit",
        "scales",
    } <= sections
    assert "units" in result and "xrefs" in result


def test_failing_dimension_audit_keeps_units_and_skips_the_magnitude_check(tmp_path, monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("audit blew up")

    path = make(tmp_path, lambda doc: add_model_dims(doc, 400), units=6)
    monkeypatch.setattr(read_dxf, "_audit_all", boom)
    result = probe(path)
    assert result["status"] == "partial"
    assert any("skipped" in line for line in result["units"]["evidence"])


# --- unreadable file ------------------------------------------------------------


def test_unreadable_dxf_reports_error_in_json(tmp_path):
    path = tmp_path / "bad.dxf"
    path.write_text("this is not a dxf at all\n", encoding="utf-8")
    result = probe(path)
    assert result["status"] == "unreadable"
    assert result["error"]
    assert result["attempts"][0]["status"] == "failed"
    assert result["attempts"][0]["error"]
    assert result["file"]["dxf_version"] is None
    assert len(result["file"]["sha256"]) == 64
    assert "units" not in result


# --- CLI ------------------------------------------------------------------------


def run_cli(capsys, *argv) -> tuple[int, dict | None, str]:
    code = main(["read-dxf", *map(str, argv)])
    captured = capsys.readouterr()
    return code, json.loads(captured.out) if captured.out.strip() else None, captured.err


def no_constants(name: str):
    raise ValueError(f"non-standard JSON constant {name}")


def test_cli_ok_prints_one_valid_json_document(tmp_path, capsys):
    code, out, _ = run_cli(capsys, make(tmp_path))
    assert code == 0
    assert out is not None
    assert validate("dxf-probe", out) == []


def test_cli_output_is_strict_json_even_for_a_400_digit_override(tmp_path, capsys):
    path = make(tmp_path, lambda doc: add_dim(doc, text="9" * 400))
    assert main(["read-dxf", str(path)]) == 0
    stdout = capsys.readouterr().out
    json.loads(stdout, parse_constant=no_constants)  # raises on NaN / Infinity
    assert "Infinity" not in stdout and "NaN" not in stdout


def test_cli_refuses_to_print_non_finite_numbers(tmp_path, capsys, monkeypatch):
    result = probe_dxf(make(tmp_path))
    result["extents"] = {"min": [0, 0, 0], "max": [float("inf"), 0, 0], "source": "header"}
    monkeypatch.setattr("tekla_harness.cli.probe_dxf", lambda *_a, **_k: result)
    code = main(["read-dxf", str(tmp_path / "t.dxf")])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert "non-finite" in captured.err.lower()


def test_cli_unknown_units_still_exits_zero_with_blocking_question(tmp_path, capsys):
    code, out, _ = run_cli(capsys, make(tmp_path, units=None))
    assert code == 0
    assert out is not None
    assert out["units"]["value"] == "unknown"
    assert any(q["blocking"] and q["code"] == "units_unknown" for q in out["questions"])


def test_cli_converter_option(tmp_path, capsys):
    code, out, _ = run_cli(capsys, make(tmp_path), "--converter", "libredwg")
    assert code == 0
    assert out is not None
    assert out["file"]["converter"] == "libredwg"
    assert out["file"]["confidence_cap"] == "medium"


def test_cli_unreadable_exits_one_with_json_and_stderr_note(tmp_path, capsys):
    bad = tmp_path / "bad.dxf"
    bad.write_text("garbage\n", encoding="utf-8")
    code, out, err = run_cli(capsys, bad)
    assert code == 1
    assert out is not None
    assert out["status"] == "unreadable"
    assert "bad.dxf" in err


def test_cli_partial_exits_zero_and_shows_the_errors(tmp_path, capsys, monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("layers blew up")

    monkeypatch.setattr(read_dxf, "_layers", boom)
    code, out, err = run_cli(capsys, make(tmp_path))
    assert code == 0
    assert out is not None and out["status"] == "partial"
    assert out["section_errors"][0]["section"] == "layers"
    assert "layers" in err and "partial" in err


def test_cli_missing_file_is_usage_error(tmp_path, capsys):
    code, out, err = run_cli(capsys, tmp_path / "nope.dxf")
    assert code == 2
    assert out is None
    assert "nope.dxf" in err


def test_cli_bad_converter_is_usage_error(tmp_path, capsys):
    code, _, _ = run_cli(capsys, make(tmp_path), "--converter", "autocad")
    assert code == 2


def test_cli_unhashable_file_is_environment_error(tmp_path, capsys, monkeypatch):
    def deny(_path, converter="none"):
        raise PermissionError("denied")

    monkeypatch.setattr("tekla_harness.cli.probe_dxf", deny)
    code, out, err = run_cli(capsys, make(tmp_path))
    assert code == 3
    assert out is None
    assert "denied" in err


# --- small curated fixture: facts, not just schema validity ---------------------


def test_curated_drawing_facts(tmp_path):
    def build(doc):
        doc.layers.add("S-BEAM", color=1)
        doc.layers.add("S-ANNO", color=2)
        msp = doc.modelspace()
        for i in range(4):
            msp.add_line((0, i * 3000), (6000, i * 3000), dxfattribs={"layer": "S-BEAM"})
        add_dim(doc, length=6000, text="6050")  # typed over: differs from the 6000 geometry
        add_dim(doc, length=3000)
        add_dim(doc, length=3000)
        bubble = doc.blocks.new("GRID-BUBBLE")
        bubble.add_attdef("NO", (0, 0), "?")
        for i in range(3):
            msp.add_blockref("GRID-BUBBLE", (i * 6000, -500)).add_auto_attribs({"NO": str(i)})
        layout = doc.layouts.get("Layout1")
        add_overall(layout)
        add_vp(layout, 6000)

    result = probe(make(tmp_path, build))
    assert result["units"]["value"] == "mm" and result["units"]["confidence"] == "medium"
    assert codes(result, blocking=True) == []
    layers = {layer["name"]: layer for layer in result["layers"]}
    assert layers["S-BEAM"]["entities"]["modelspace"] == 4
    (bubble,) = [b for b in result["blocks"]["named"] if b["name"] == "GRID-BUBBLE"]
    assert (bubble["name"], bubble["insert_count"], bubble["has_attrib"]) == ("GRID-BUBBLE", 3, True)
    audit = result["dimension_audit"]
    assert (audit["total"], audit["by_status"]) == (3, {"ok": 2, "override_differs": 1})
    viewports = layout1(result)["viewports"]
    assert [vp["is_overall"] for vp in viewports] == [True, False]
    assert [s["value"] for s in result["scales"]["viewport_scales"]] == [pytest.approx(10 / 6000)]


# --- corpus smoke test: opt-in only (parses untrusted personal files, slow) ------

CORPUS = sorted(SAMPLES.rglob("*.dxf")) if SAMPLES.is_dir() else []
CORPUS_ENABLED = os.environ.get("HARNESS_CORPUS_TESTS") == "1"
needs_corpus = pytest.mark.skipif(
    not (CORPUS_ENABLED and CORPUS), reason="set HARNESS_CORPUS_TESTS=1 with dwg-lab/samples present"
)


@needs_corpus
def test_corpus_probe_is_schema_valid():
    for path in CORPUS:
        result = probe_dxf(path)
        assert validate("dxf-probe", result) == [], path.name
        json.dumps(result, allow_nan=False)
        assert "units" in result or result["status"] == "unreadable", path.name


KNOWN_GAP = pytest.mark.xfail(
    strict=True,
    reason="433: header 'in' but metric-looking geometry; its median |linear dimension| is 5 m (group 42), "
    "indistinguishable from legitimate drawings: the median heuristic cannot catch it",
)


@needs_corpus
@pytest.mark.parametrize(
    "name",
    [
        "267_4-story_house_complete_project.dxf",
        pytest.param("433_townhouse_12m_x_20.6m.dxf", marks=KNOWN_GAP),
    ],
)
def test_corpus_wrong_units_are_caught(name):
    (path,) = [p for p in CORPUS if p.name == name]
    result = probe_dxf(path)
    assert result["units"]["confidence"] == "low"
    assert {"units_conflict", "units_suspect"} & set(codes(result, blocking=True))
