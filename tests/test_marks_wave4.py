"""marks and callouts, tool wave 4 (package M). Synthetic drawings only (see _marks_fixtures)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from ezdxf.filemanagement import readfile

from _callout_fixtures import PROPOSED_FONT_TABLE, write_structure
from _callout_fixtures import REL as FIXTURE_REL
from _dxf_fixtures import build_set
from _marks_fixtures import (
    BLOCKED_STYLE,
    KINH,
    PLAN_STEP,
    PLAN_TOP,
    PLAN_X,
    TH,
    _styled_table,
    build_gate_work,
)
from tekla_harness.intake import run_intake
from tekla_harness.marks import extract_marks
from tekla_harness.schemas import validate
from tekla_harness.text_gate import meaning_block_reason

REL = "plans/set.dxf"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def table_with(doc: dict[str, Any], header: str) -> dict[str, Any]:
    (t,) = [t for t in doc["tables"] if any(h["display_text"] == header for h in t["header"])]
    return t


def blocked_ids(work: Path) -> set[str]:
    index = load(work / "text" / f"{REL}.json")
    return {e["id"] for e in index["entries"] if meaning_block_reason(e)}


def cited_ids(node: Any, out: list[str]) -> None:
    """Entry ids cited outside every key that starts with 'blocked' (the EVAL-4 M2 rule), rows left out."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key.startswith("blocked") or key == "rows":
                continue
            if isinstance(value, str) and value.startswith("T") and value[1:].isdigit():
                out.append(value)
            else:
                cited_ids(value, out)
    elif isinstance(node, list):
        for value in node:
            if isinstance(value, str) and value.startswith("T") and value[1:].isdigit():
                out.append(value)
            else:
                cited_ids(value, out)


# --- item 2: a blocked header cell's entry id goes to blocked_header_entries (M2) ----------------------


@pytest.fixture(scope="module")
def gate_world(tmp_path_factory) -> tuple[Path, dict[str, Any]]:
    root = tmp_path_factory.mktemp("w4gate")
    work = build_gate_work(root)
    return work, extract_marks(work, root / "input", check_inputs=True)


def test_blocked_header_cells_keep_a_placeholder_and_their_id_moves(gate_world):
    work, doc = gate_world
    blocked = blocked_ids(work)
    assert blocked  # the fixture does have blocked header text
    assert validate("marks", doc) == []
    for t in doc["tables"]:
        placeholders = [h for h in t["header"] if h["meaning"] == "blocked"]
        assert all(h["entry_id"] is None for h in placeholders), t["id"]
        assert all(h["entry_id"] is not None for h in t["header"] if h["meaning"] == "allowed")
        listed = t["blocked_header_entries"]
        assert len(listed) == len(placeholders) and set(listed) <= blocked
        assert listed == sorted(listed)
    seen: list[str] = []
    cited_ids({k: v for k, v in doc.items() if k != "plan_marks"}, seen)
    assert not set(seen) & blocked  # nothing blocked is cited outside a blocked* key


def test_a_blocked_non_mark_column_header_is_in_blocked_columns_and_blocked_header_entries(gate_world):
    _, doc = gate_world
    t = table_with(doc, "KÝ HIỆU")
    (kinh,) = [h for h in t["header"] if h["display_text"] == KINH]
    assert kinh["entry_id"] is None and kinh["meaning"] == "blocked" and kinh["column"] == 3
    (column,) = t["blocked_columns"]
    assert column["column"] == 3 and column["entry_id"] in t["blocked_header_entries"]
    assert len(t["blocked_header_entries"]) == 2  # KÍNH and the blocked text under the keyword


def test_a_header_blocked_table_lists_its_blocked_cells_and_is_still_reported(gate_world):
    _, doc = gate_world
    t = table_with(doc, "Abçd")
    assert t["header_blocked"] is True and t["mark_column"] is None
    assert [h["display_text"] for h in t["header"]] == ["Abçd", "SL"]
    assert len(t["blocked_header_entries"]) == 1
    assert [b["display_text"] for b in doc["blocked_marks"] if b["table"] == t["id"]] == ["G1", "G2"]


def build_all_blocked_header_work(base: Path) -> Path:
    """One line-grid table whose two header cells are both blocked (legacy-font text), rows G1 / G2."""
    root = base / "input"
    (root / "plans").mkdir(parents=True)
    doc = readfile(str(build_set(base, "src.dxf")))
    doc.styles.add(BLOCKED_STYLE, font="vntimeh.shx")
    msp = doc.modelspace()
    header = (("Ab\u00e7d", BLOCKED_STYLE), ("Xy\u00e8z", BLOCKED_STYLE))
    rows = ((("G1", None), ("2", None)), (("G2", None), ("4", None)))
    _styled_table(msp, 2000.0, (3000.0, 2000.0), header, rows)
    for i, text in enumerate(("G1", "G2")):
        msp.add_text(text, height=TH, dxfattribs={"insert": (PLAN_X, PLAN_TOP - i * PLAN_STEP)})
    doc.saveas(root / FIXTURE_REL)
    work = base / "work"
    run_intake(root, work, "demo-marks", knowledge=PROPOSED_FONT_TABLE)
    write_structure(root, work)
    return work


def test_a_table_whose_header_cells_are_all_blocked_is_still_reported(tmp_path):
    """Both header cells blocked: header[] holds two placeholders, the table is header-blocked, and its
    mark-shaped cells are still listed in blocked_marks."""
    work = build_all_blocked_header_work(tmp_path)
    doc = extract_marks(work, tmp_path / "input")
    assert validate("marks", doc) == []
    (t,) = doc["tables"]
    assert t["header_blocked"] is True and len(t["header"]) == 2
    assert all(h["entry_id"] is None and h["meaning"] == "blocked" for h in t["header"])
    assert len(t["blocked_header_entries"]) == 2 and set(t["blocked_header_entries"]) <= blocked_ids(work)
    assert [b["display_text"] for b in doc["blocked_marks"]] == ["G1", "G2"]
    seen: list[str] = []
    cited_ids({k: v for k, v in doc.items() if k != "plan_marks"}, seen)
    assert not set(seen) & blocked_ids(work)
