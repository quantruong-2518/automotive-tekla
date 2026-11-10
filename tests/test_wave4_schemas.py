"""Tool wave 4, seam: the new optional schema fields (`$id` stays 0.1)."""

from __future__ import annotations

import json
from pathlib import Path

SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"


def _schema(name: str) -> dict:
    return json.loads((SCHEMAS / f"{name}.schema.json").read_text("utf-8"))


def test_text_index_entry_declares_the_visibility_fields_as_optional():
    entry = _schema("text-index")["$defs"]["entry"]
    props = entry["properties"]
    assert props["printed"]["type"] == "boolean"
    assert props["not_printed_reasons"]["items"]["enum"] == [
        "entity_invisible",
        "attribute_invisible",
        "layer_off",
        "layer_frozen",
        "layer_no_plot",
    ]
    assert props["print_uncertain_reasons"]["items"]["enum"] == [
        "insert_invisible",
        "attmode_not_normal",
        "viewport_frozen",
        "defpoints_layer",
    ]
    assert not {"printed", "not_printed_reasons", "print_uncertain_reasons"} & set(entry["required"])


def test_marks_table_declares_blocked_header_entries_as_optional():
    table = _schema("marks")["$defs"]["table"]
    assert table["properties"]["blocked_header_entries"]["type"] == "array"
    assert "blocked_header_entries" not in table["required"]


def test_marks_cell_allows_a_header_placeholder_without_an_entry_id():
    cell = _schema("marks")["$defs"]["cell"]["properties"]["entry_id"]
    assert {"type": "null"} in cell["anyOf"]


def test_sheets_title_block_declares_job_number_like_sheet_number():
    defs = _schema("sheets")["$defs"]
    block = defs["title_block"]
    assert block["properties"]["job_number"]["anyOf"] == block["properties"]["sheet_number"]["anyOf"]
    assert "job_number" not in block["required"]
    assert "job_number" in defs["field_candidate"]["properties"]["field"]["enum"]


def test_schema_ids_stay_at_0_1():
    for name in ("text-index", "marks", "sheets"):
        assert _schema(name)["$id"].endswith(":0.1")
