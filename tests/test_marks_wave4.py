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
from tekla_harness.callouts import callout_part_ids, extract_callouts, member_mark
from tekla_harness.intake import run_intake
from tekla_harness.marks import extract_marks, parse_mark
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


# --- item 3 (F4a): rebar-callout ATTRIBs, strength classes and signed levels are no member marks ----------


def build_attrib_work(
    base: Path, blocks: dict[str, tuple[str, ...]], inserts: list[tuple[str, dict[str, str]]]
):
    """Synthetic drawing: `blocks` maps a block name to its ATTDEF tags; `inserts` lists (block, {tag: value})
    placed in a column at x 46000 on sheet S-101 (so the texts sit on the model-space frame)."""
    from _marks_fixtures import PLAN_STEP, PLAN_TOP, PLAN_X, TH

    root = base / "input"
    (root / "plans").mkdir(parents=True)
    doc = readfile(str(build_set(base, "src.dxf")))
    for name, tags in blocks.items():
        block = doc.blocks.new(name)
        for i, tag in enumerate(tags):
            block.add_attdef(tag, (0.0, -i * 450.0), text="?", height=TH)
    msp = doc.modelspace()
    for i, (name, values) in enumerate(inserts):
        ref = msp.add_blockref(name, (PLAN_X, PLAN_TOP - i * 3 * PLAN_STEP))
        ref.add_auto_attribs(values)
    doc.saveas(root / FIXTURE_REL)
    work = base / "work"
    run_intake(root, work, "demo-marks", knowledge=PROPOSED_FONT_TABLE)
    write_structure(root, work)
    return work


REBAR_BLOCKS = {
    "REBAR": ("THEP", "KHOANGCACH", "SH"),  # 278-like tags
    "BARTAG": ("SH", "DK", "KC"),  # 285-like: no bar tag among THEP / KHOANGCACH, a spacing value instead
    "TITLE": ("NAME", "NO"),  # a block that is not a callout
}
REBAR_INSERTS: list[tuple[str, dict[str, str]]] = [
    ("REBAR", {"THEP": "D10", "KHOANGCACH": "a150", "SH": "2"}),
    ("REBAR", {"THEP": "D12", "KHOANGCACH": "A200", "SH": "D"}),
    ("BARTAG", {"SH": "t1", "DK": "D6", "KC": "a200"}),
    ("BARTAG", {"SH": "t2", "DK": "D6", "KC": "a600x600"}),
    ("TITLE", {"NAME": "D3", "NO": "7"}),
]


@pytest.fixture(scope="module")
def attrib_world(tmp_path_factory) -> tuple[Path, Path]:
    root = tmp_path_factory.mktemp("w4attrib")
    return build_attrib_work(root, REBAR_BLOCKS, REBAR_INSERTS), root


def test_attribs_of_a_rebar_callout_block_are_no_plan_marks(attrib_world):
    work, root = attrib_world
    doc = extract_marks(work, root / "input", check_inputs=True)
    assert validate("marks", doc) == []
    assert sorted(p["mark"] for p in doc["plan_marks"]) == ["D3"]  # only the title block's NAME stays
    (said,) = [w for w in doc["warnings"] if "callout_part" in w]
    assert "callout_part 7" in said and "'D10' (T0" in said  # the count per reason, examples with entry ids
    assert said.count("(T0") == 5  # at most five examples


def test_attribs_of_a_rebar_callout_block_are_no_member_mark_candidate(attrib_world):
    work, _ = attrib_world
    doc = extract_callouts(work, check_inputs=True)
    assert validate("callouts", doc) == []
    assert [c["display_text"] for c in doc["candidates"] if c["kind"] == "member_mark"] == ["D3"]
    parts = [r for r in doc["rejected"] if r["reason_code"] == "callout_part"]
    assert sorted(r["display_text"] for r in parts) == ["A200", "D10", "D12", "D6", "D6"]  # upper case only
    assert doc["summary"]["rejected_by_reason"]["callout_part"] == 5


def test_callout_part_ids_group_by_insert_not_by_block_name():
    def attrib(eid: str, tag: str, text: str, handle: str, outer: tuple[str, ...] = ()) -> dict[str, Any]:
        return {
            "id": eid, "entity_type": "ATTRIB", "space": "model", "layout": "Model", "tag": tag,
            "display_text": text, "insert_handle": handle, "insert_handles": list(outer),
        }  # fmt: skip

    entries = [
        attrib("T000001", "NAME", "D1", "A1"),  # same block name elsewhere, no spacing: stays a mark
        attrib("T000002", "NAME", "D2", "A2"),
        attrib("T000003", "X", "a100", "A2"),  # A2 carries a spacing value: both its ATTRIBs are parts
        attrib("T000004", "THEP", "D8", "A3"),  # a bar tag alone
        attrib("T000005", "NAME", "D9", "A4", ("OUT",)),  # nested under another insert chain ...
        attrib("T000006", "X", "A150", "A4", ("OTHER",)),  # ... with the same own handle: not the same insert
        {**attrib("T000007", "NAME", "a150", ""), "insert_handle": None},  # no insert handle: not grouped
        attrib("T000008", "NAME", "A1", "A5"),  # a letter and one digit is a mark or a label, no spacing
        attrib("T000009", "NO", "A1234", "A5"),  # nor four digits
        attrib("T000010", "NAME", "thep", "A6"),  # a bar tag as a VALUE is not a tag
    ]
    assert callout_part_ids(entries) == {"T000002", "T000003", "T000004", "T000006"}


GRADE_AND_LEVEL = [
    ("RB 500", False),
    ("RB500", False),
    ("RB-500", False),
    ("CB 400", False),
    ("cb 300", False),
    ("SD 500", False),
    ("RB 5", True),  # a grade prefix but no yield class
    ("RB 501", True),
    ("D 500", True),  # not a grade prefix
    ("cos -300", False),
    ("COS -300", False),
    ("cos-300", True),  # no blank before the minus: a hyphenated mark
    ("cos - 300", True),
    ("C - 1", True),
    ("D1", True),
]


def test_a_sub_numbered_text_is_no_strength_class():
    """A strength class is one number; `RB 500.1` has a second number and stays a (sub-numbered) mark."""
    assert parse_mark("RB 500.1") is not None
    assert parse_mark("RB 500") is None


@pytest.mark.parametrize(("text", "is_mark"), GRADE_AND_LEVEL)
def test_grade_and_level_tokens_are_no_marks(text, is_mark):
    assert (parse_mark(text, case_uncertain=True) is not None) is is_mark


@pytest.mark.parametrize(("text", "is_mark"), GRADE_AND_LEVEL)
def test_grade_and_level_tokens_are_no_member_mark_candidates(text, is_mark):
    assert (member_mark(text, True) is not None) is is_mark


def test_a_grade_token_in_a_plan_is_listed_with_its_reason(tmp_path):
    work = build_marks_work(tmp_path, plan_texts=("D1", "RB 500", "COS -300", "C2"))
    marks = extract_marks(work, tmp_path / "input")
    assert {"C2", "D1"} <= {p["mark"] for p in marks["plan_marks"]}
    assert not {"RB 500", "COS -300"} & {p["mark"] for p in marks["plan_marks"]}
    (said,) = [w for w in marks["warnings"] if "grade_token" in w]
    assert "grade_token 1" in said and "level_token 1" in said
    callouts = extract_callouts(work)
    tokens = {r["reason_code"]: r["display_text"] for r in callouts["rejected"] if r["kind"] == "member_mark"}
    assert (tokens["grade_token"], tokens["level_token"]) == ("RB 500", "COS -300")
