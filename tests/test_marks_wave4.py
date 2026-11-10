"""marks and callouts, tool wave 4 (package M). Synthetic drawings only (see _marks_fixtures)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from ezdxf.filemanagement import readfile

from _callout_fixtures import PROPOSED_FONT_TABLE, build_work, write_structure
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
    build_marks_work,
)
from tekla_harness.callouts import extract_callouts
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


# --- item 1: text that does not print is no mark and no callout ------------------------------------------


def hide(work: Path, texts: set[str], reasons: tuple[str, ...] = ("entity_invisible",)) -> int:
    """Mark every text-index entry whose display_text is in `texts` as not printed (what package T writes)."""
    path = work / "text" / f"{REL}.json"
    index = load(path)
    n = 0
    for entry in index["entries"]:
        if entry["display_text"] in texts:
            entry["printed"] = False
            entry["not_printed_reasons"] = list(reasons)
            n += 1
    path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    return n


def entry_id(work: Path, text: str) -> str:
    (e,) = [e for e in load(work / "text" / f"{REL}.json")["entries"] if e["display_text"] == text]
    return e["id"]


def test_a_mark_that_does_not_print_is_no_plan_mark(tmp_path):
    work = build_marks_work(tmp_path, plan_texts=("D1", "D5", "D5", "C7", "gm3"))
    assert hide(work, {"D5"}) == 2
    doc = extract_marks(work, tmp_path / "input", check_inputs=True)
    assert validate("marks", doc) == []
    plan = [p["mark"] for p in doc["plan_marks"]]
    assert "D5" not in plan and {"D1", "C7", "gm3"} <= set(plan)
    said = "2 text entries that do not print (not_printed_reasons: entity_invisible 2)"
    assert any(said in w for w in doc["warnings"])
    assert "d5" not in {k["key"] for m in doc["matching"] for k in m["plan_only"] + m["matched"]}


def test_a_text_index_without_the_printed_field_reads_as_printed(tmp_path):
    work = build_marks_work(tmp_path, plan_texts=("D1", "D5"))
    doc = extract_marks(work, tmp_path / "input")
    assert "D5" in [p["mark"] for p in doc["plan_marks"]]
    assert not any("do not print" in w for w in doc["warnings"])


def test_uncertain_visibility_alone_keeps_the_entry(tmp_path):
    """`print_uncertain_reasons` and `printed: true` keep the entry: only `printed: false` excludes."""
    work = build_marks_work(tmp_path, plan_texts=("D1", "D5"))
    path = work / "text" / f"{REL}.json"
    index = load(path)
    for entry in index["entries"]:
        if entry["display_text"] == "D5":
            entry["print_uncertain_reasons"] = ["attmode_not_normal"]
        if entry["display_text"] == "D1":
            entry["printed"] = True
    path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    doc = extract_marks(work, tmp_path / "input")
    assert {"D1", "D5"} <= {p["mark"] for p in doc["plan_marks"]}


def test_a_header_keyword_that_does_not_print_anchors_no_table(tmp_path):
    work = build_marks_work(tmp_path)
    visible = extract_marks(work, tmp_path / "input")
    assert any(h["display_text"] == "KÝ HIỆU" for t in visible["tables"] for h in t["header"])
    hide(work, {"KÝ HIỆU"})
    doc = extract_marks(work, tmp_path / "input")
    assert not any(h["display_text"] == "KÝ HIỆU" for t in doc["tables"] for h in t["header"])


def test_callouts_skip_text_that_does_not_print(tmp_path):
    work = build_work(tmp_path, s1=["4%%c16", "C1", "C9", "%%c8a150"], styled=[], s2=[], paper=[])
    visible = extract_callouts(work)
    assert {c["display_text"] for c in visible["candidates"]} >= {"C9", "C1"}
    assert hide(work, {"C9", "4Ø16"}) == 2
    doc = extract_callouts(work, check_inputs=True)
    assert validate("callouts", doc) == []
    shown = {c["display_text"] for c in doc["candidates"]}
    assert "C9" not in shown and "4Ø16" not in shown and "C1" in shown
    assert any("2 text entries that do not print" in w for w in doc["warnings"])
    assert doc["files"][0]["scanned"] == visible["files"][0]["scanned"] - 2


def test_a_hidden_footing_label_is_no_family_evidence(tmp_path):
    """footing_m_labels: M8 is a bolt size, a member mark only next to a printed M7 (a footing family)."""
    work = build_work(tmp_path, s1=["M6", "M7", "M8"], styled=[], s2=[], paper=[])
    m8 = entry_id(work, "M8")
    doc = extract_callouts(work)
    assert [c["kind"] for c in doc["candidates"] if c["text_ref"]["entry_id"] == m8] == ["member_mark"]
    hide(work, {"M7"})
    doc = extract_callouts(work)
    assert [c["kind"] for c in doc["candidates"] if c["text_ref"]["entry_id"] == m8] == ["bolt"]


def _released(neighbour_printed: bool) -> set[str]:
    """A shape-only title-block candidate `P-01` and another text `P-02` of the same prefix, style and
    height that no candidate took: the candidate is released (a mark) only while `P-02` prints."""
    from tekla_harness.callouts import _released_pattern_values
    from tekla_harness.sheet_text import LoadedFile

    def entry(eid: str, text: str, printed: bool = True) -> dict[str, Any]:
        e: dict[str, Any] = {"id": eid, "display_text": text, "style": "S", "height": 3.5}
        if not printed:
            e["printed"] = False
        return e

    index = {"entries": [entry("T000001", "P-01"), entry("T000002", "P-02", neighbour_printed)]}
    cand = {
        "field": "sheet_number",
        "value": "P-01",
        "evidence": {"kind": "pattern", "value_text_id": "T000001", "label_text_id": None},
    }
    sheets = {"sheets": [{"text_ids": ["T000001", "T000002"], "title_block": {"candidates": [cand]}}]}
    loaded = LoadedFile("a.dxf", {}, None, index, sheets)
    return _released_pattern_values(loaded)


def test_a_hidden_neighbour_is_no_mark_family_for_a_title_block_value():
    assert _released(True) == {"T000001"}
    assert _released(False) == set()


def test_hidden_text_does_not_set_the_line_tolerance_of_a_space():
    from tekla_harness.marks import LINE_TOL, _space_tolerances

    def entry(height: float, printed: bool = True) -> dict[str, Any]:
        e: dict[str, Any] = {"space": "model", "height": height}
        if not printed:
            e["printed"] = False
        return e

    entries = [entry(350.0), entry(350.0), entry(350.0)] + [entry(9000.0, printed=False)] * 5
    assert _space_tolerances(entries) == {"model": LINE_TOL * 350.0}
    assert _space_tolerances(entries[3:]) == {}  # a space whose texts all stay hidden has no tolerance
