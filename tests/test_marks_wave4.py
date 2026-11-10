"""marks and callouts, tool wave 4 (package M). Synthetic drawings only (see _marks_fixtures)."""

from __future__ import annotations

import json
from collections import Counter
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
from tekla_harness.callouts import callout_part_ids, detail_label_ids, extract_callouts, member_mark
from tekla_harness.intake import run_intake
from tekla_harness.marks import extract_marks, parse_mark, parse_title_marks
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


# --- item 4 (F4c): steel profiles, detail labels and title-block cells are no marks ------------------------

PROFILES = [
    ("HEB-650", False),
    ("HEB 650", False),
    ("HEB700", False),
    ("IPE-300", False),
    ("ipe 200", False),
    ("IPEA-300", False),  # four letters
    ("HEA 100", False),
    ("UB-305", False),
    ("UC 254", False),
    ("UPN 80", False),
    ("UB-50", False),  # the smallest depth counted
    ("UB-49", True),
    ("UC1", True),  # a small number is a member, not a depth
    ("UB-5", True),
    ("HEB-1", True),
    ("HE-650", True),  # not a series
    ("IPE-49", True),  # below the smallest catalogue depth
    ("DET-2", False),
    ("DET2", False),
    ("det-12", False),
    ("DT-2", True),
    ("D1", True),
]


@pytest.mark.parametrize(("text", "is_mark"), PROFILES)
def test_steel_profiles_and_detail_labels_are_no_marks(text, is_mark):
    assert (parse_mark(text, case_uncertain=True) is not None) is is_mark


@pytest.mark.parametrize(("text", "is_mark"), [p for p in PROFILES if not p[0].upper().startswith("IPEA")])
def test_steel_profiles_and_detail_labels_are_no_member_mark_candidates(text, is_mark):
    # callouts' grammar takes at most three letters: IPEA-300 is never a candidate in the first place
    assert (member_mark(text, True) is not None) is is_mark


def test_profiles_are_listed_with_their_reason(tmp_path):
    work = build_marks_work(tmp_path, plan_texts=("D1", "HEB-650", "IPEA-300", "DET-2", "UC1"))
    marks = extract_marks(work, tmp_path / "input")
    assert {"D1", "UC1"} <= {p["mark"] for p in marks["plan_marks"]}
    assert not {"HEB-650", "IPEA-300", "DET-2"} & {p["mark"] for p in marks["plan_marks"]}
    (said,) = [w for w in marks["warnings"] if "steel_profile" in w]
    assert "steel_profile 2" in said and "detail_label 1" in said
    callouts = extract_callouts(work)
    codes = {r["reason_code"] for r in callouts["rejected"] if r["kind"] == "member_mark"}
    assert {"steel_profile", "detail_label"} <= codes


def test_a_detail_bubble_label_is_no_mark_but_a_member_next_to_a_detail_heading_is(tmp_path):
    """`DETAIL - A1` names a detail; the bubbles 'A1' on that sheet are its reference, not members. A
    family with other members (C1 C2 C3 and a heading `DETAIL - C1`) stays, and so does an A1 on a sheet with
    no such heading."""
    work = build_work(
        tmp_path,
        s1=["DETAIL - A1", "A1", "A1", "DETAIL - C1", "C1", "C2", "C3"],
        s2=["A1", "D4"],
        styled=[],
        paper=[],
    )
    marks = extract_marks(work, tmp_path / "input")
    by_sheet: dict[str, list[str]] = {}
    for p in marks["plan_marks"]:
        by_sheet.setdefault(p["sheet"], []).append(p["mark"])
    assert sorted(by_sheet["model#01"]) == ["C1", "C2", "C3"]
    assert sorted(by_sheet["model#02"]) == ["A1", "D4"]
    (said,) = [w for w in marks["warnings"] if "detail_label" in w]
    assert "detail_label 2" in said
    callouts = extract_callouts(work)
    marked = [(c["sheet"], c["display_text"]) for c in callouts["candidates"] if c["kind"] == "member_mark"]
    assert ("model#02", "A1") in marked and ("model#01", "A1") not in marked
    assert {("model#01", "C1"), ("model#01", "C2")} <= set(marked)
    assert sum(1 for r in callouts["rejected"] if r["reason_code"] == "detail_label") == 2


def add_title_block_candidates(work: Path, values: dict[str, tuple[str, str, str]]) -> None:
    """Add to sheet model#01 of a synthetic sheets.json one candidate per entry of `values`
    ({text: (field, evidence kind, label)}) on the text of that value, and a `job_number` sourced string."""
    sheets_path = work / "structure" / f"{REL}.sheets.json"
    sheets = load(sheets_path)
    index = load(work / "text" / f"{REL}.json")
    ids = {e["display_text"]: e for e in index["entries"]}
    block = sheets["sheets"][0]["title_block"]
    for text, (field, kind, label) in values.items():
        e = ids[text]
        label_id = None
        if kind == "adjacent_label":
            label_id = ids[label]["id"]
        block["candidates"].append(
            {
                "field": field,
                "value": text,
                "evidence": {
                    "kind": kind,
                    "key": label if kind == "adjacent_label" else "sheet_code_lower_right",
                    "value_text_id": e["id"],
                    "label_text_id": label_id,
                    "position": [e["position"]["x"], e["position"]["y"]],
                },
                "confidence": "low",
                "provenance": {"file": REL, "sheet": "model#01", "method": "dxf_entity"},
            }
        )
        if field == "job_number":
            block["job_number"] = {
                "value": text,
                "confidence": "low",
                "provenance": {"file": REL, "sheet": "model#01", "method": "dxf_entity"},
            }
    assert validate("sheets", sheets) == []
    sheets_path.write_text(json.dumps(sheets, ensure_ascii=False), encoding="utf-8")


def test_job_and_sheet_numbers_of_the_title_block_are_no_marks(tmp_path):
    """Package S fills `title_block.job_number` and the sheet-number candidates: their value texts are claimed
    by the title block, whatever mark family stands next to them (J-02, J-03 / P-02). A job number is claimed
    even when it was found by shape alone (the release for shape-only sheet codes does not apply to it)."""
    texts = ("DRAWING NO.:", "P-01", "P-02", "J-01", "J-02", "J-03", "D1")
    work = build_marks_work(tmp_path, plan_texts=texts)
    add_title_block_candidates(
        work,
        {
            "P-01": ("sheet_number", "adjacent_label", "DRAWING NO.:"),
            "J-01": ("job_number", "pattern", ""),
        },
    )
    marks = extract_marks(work, tmp_path / "input", check_inputs=True)
    plan = {p["mark"] for p in marks["plan_marks"]}
    assert "J-01" not in plan and "P-01" not in plan
    assert {"J-02", "J-03", "P-02", "D1"} <= plan
    callouts = extract_callouts(work, check_inputs=True)
    candidates = {c["display_text"] for c in callouts["candidates"] if c["kind"] == "member_mark"}
    assert "J-01" not in candidates and "P-01" not in candidates
    claimed = {
        r["display_text"] for r in callouts["rejected"] if r["reason_code"] == "claimed_by_title_block"
    }
    assert {"J-01", "P-01"} <= claimed


def _detail_entries(*items: tuple[str, str, str, bool]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """(entries, sheet_of) from (id, text, sheet id, printed)."""
    entries, sheet_of = [], {}
    for eid, text, sheet, printed in items:
        e: dict[str, Any] = {"id": eid, "display_text": text}
        if not printed:
            e["printed"] = False
        entries.append(e)
        if sheet:
            sheet_of[eid] = {"sheet_id": sheet}
    return entries, sheet_of


@pytest.mark.parametrize("heading", ["DETAIL - A1", "detail A1", "Detail: a1", "DETAIL-A 1"])
def test_detail_heading_forms(heading):
    entries, sheet_of = _detail_entries(("T000001", heading, "s1", True), ("T000002", "A1", "s1", True))
    assert detail_label_ids(entries, sheet_of) == {"T000002"}


@pytest.mark.parametrize(
    ("heading", "label"),
    [
        ("CHI TIẾT A1", "A1"),
        ("MẶT CẮT DT1", "DT1"),
        ("SECTION A1", "A1"),
        ("DETAIL OF A1", "A1"),
        ("DETAIL - A1 x", "A1"),
        ("DETAIL - A1", "A2"),  # another id
    ],
)
def test_other_headings_make_no_detail_id(heading, label):
    """A Vietnamese `chi tiết` / `mặt cắt` heading names a member or a cut (290 `MẶT CẮT DT1` heads the
    section of the member DT1): the text on that sheet stays a member."""
    entries, sheet_of = _detail_entries(("T000001", heading, "s1", True), ("T000002", label, "s1", True))
    assert detail_label_ids(entries, sheet_of) == set()


def test_detail_labels_need_a_printed_heading_of_their_own_sheet():

    entries, sheet_of = _detail_entries(
        ("T000001", "DETAIL - A1", "s1", False),  # does not print: names nothing
        ("T000002", "A1", "s1", True),
        ("T000003", "DETAIL - B2", "s1", True),
        ("T000004", "B2", "s2", True),  # another sheet
        ("T000005", "B2", "s1", True),
        ("T000006", "B2", "", True),  # on no sheet: its own group
        ("T000007", "DETAIL - A1", "", True),
        ("T000008", "A1", "", True),
        ("T000009", "A1", "s1", False),  # does not print: not a label (and not a mark)
    )
    assert detail_label_ids(entries, sheet_of) == {"T000005", "T000008"}
    # a prefix family with a member that is not a detail id is not a label family
    entries, sheet_of = _detail_entries(
        ("T000001", "DETAIL - A1", "s1", True),
        ("T000002", "A1", "s1", True),
        ("T000003", "A2", "s1", True),
    )
    assert detail_label_ids(entries, sheet_of) == set()
    # other prefixes on the same sheet do not matter
    entries, sheet_of = _detail_entries(
        ("T000001", "DETAIL - A1", "s1", True),
        ("T000002", "A1", "s1", True),
        ("T000003", "C2", "s1", True),
    )
    assert detail_label_ids(entries, sheet_of) == {"T000002"}


def test_a_hidden_detail_heading_leaves_its_bubbles_as_marks(tmp_path):
    work = build_work(tmp_path, s1=["DETAIL - A1", "A1", "A1", "C1"], s2=[], styled=[], paper=[])
    hide(work, {"DETAIL - A1"})
    marks = extract_marks(work, tmp_path / "input")
    assert sorted(p["mark"] for p in marks["plan_marks"]) == ["A1", "A1", "C1"]


def test_a_heading_on_a_duplicate_sheet_names_no_detail_of_the_texts_on_no_sheet(tmp_path):
    """The texts of a duplicate sheet are not scanned, so its heading must not turn up in the group of the
    texts that lie on no sheet."""
    work = build_work(tmp_path, s1=["DETAIL - A1"], s2=["A1"], styled=[], paper=[])
    path = work / "structure" / f"{REL}.sheets.json"
    sheets = load(path)
    first, second = sheets["sheets"][0], sheets["sheets"][1]
    first["duplicate_of"] = second["sheet_id"]
    a1 = entry_id(work, "A1")
    second["text_ids"] = [t for t in second["text_ids"] if t != a1]  # A1 lies on no sheet
    path.write_text(json.dumps(sheets, ensure_ascii=False), encoding="utf-8")
    marks = extract_marks(work, tmp_path / "input")
    assert "A1" in [p["mark"] for p in marks["plan_marks"]]
    callouts = extract_callouts(work)
    assert [c["display_text"] for c in callouts["candidates"] if c["kind"] == "member_mark"].count("A1") == 1


# --- item 5 (R items): section labels, headings glued to a count, pile caps, numbered footing families ----

SECTION_LABELS = [
    ("mc 1-1", False),
    ("MC 2-2", False),
    ("mc 12-12", False),
    ("mc 01-1", False),  # the numbers are compared as numbers
    ("mc 1-2", True),  # two different numbers: a sub-numbered mark
    ("mc1-1", True),  # no blank before the number: written as a mark
    ("D1-1", True),
    ("D1.1", True),
    ("mc 1.1", True),  # only a hyphen names a cut
    ("D 1-1", False),  # a letter, a blank and n-n is a cut label whatever the letters
    ("C - 1", True),
]


@pytest.mark.parametrize(("text", "is_mark"), SECTION_LABELS)
def test_section_cut_labels_are_no_marks(text, is_mark):
    assert (parse_mark(text) is not None) is is_mark


@pytest.mark.parametrize(
    ("text", "word", "marks"),
    [
        ("dẦm d2-7(sl= 01)", "dẦm", ["d2-7"]),
        ("dẦm d2-7 (sl= 01)", "dẦm", ["d2-7"]),
        ("DẦM D1(220x400)", "DẦM", ["D1"]),
        ("dẦm d2-7(sl= 01", "dẦm", ["d2-7"]),
        ("ĐÀi dm 1", "ĐÀi", ["dm 1"]),
        ("ĐÀI CỌC ĐC2", "ĐÀI CỌC", ["ĐC2"]),  # the longer word still wins
        ("đài móng DM3", "đài móng", ["DM3"]),
    ],
)
def test_headings_read_through_a_glued_bracket_and_the_pile_cap_word(text, word, marks):
    found = parse_title_marks(text)
    assert found is not None and found[0] == word and [m.text for m in found[1]] == marks


def test_pile_cap_labels_and_section_cuts_in_a_plan(tmp_path):
    work = build_marks_work(
        tmp_path, plan_texts=("D1", "ĐÀi dm 1", "ĐÀi dm 2", "mc 1-1", "mc 2-2", "dẦm d2-7(sl= 01)")
    )
    doc = extract_marks(work, tmp_path / "input", check_inputs=True)
    assert validate("marks", doc) == []
    plan = {p["mark"]: p for p in doc["plan_marks"]}
    assert "mc 1-1" not in plan and "mc 2-2" not in plan
    assert plan["dm 1"]["form"] == "title" and plan["d2-7"]["form"] == "title"
    sets = {s["family"]: s for s in doc["summary"]["mark_sets"]}
    assert sets["DM"]["members"] == ["dm 1", "dm 2"] and sets["DM"]["source"] == ["detail_heading"]
    (said,) = [w for w in doc["warnings"] if "section_label" in w]
    assert "section_label 2" in said


# --- item 5 (R-c): a one-row schedule drawn with lines (161 crane beam CB-01) ----------------------------


def build_one_row_work(base: Path, plan_texts: tuple[str, ...] = ("CB-01", "CB-02")) -> Path:
    """Tables with a keyword header and ONE data row: line grids (NAME | D (mm); CB-01 | 250; a person's name
    | a town; CB-07 | nothing; DẦM D5 | 250) and a text-aligned one with no lines (CB-09 | 300)."""
    root = base / "input"
    (root / "plans").mkdir(parents=True)
    doc = readfile(str(build_set(base, "src.dxf")))
    msp = doc.modelspace()
    head = (("NAME", None), ("D (mm)", None))
    cols = (3000.0, 2000.0)
    _styled_table(msp, 2000.0, cols, head, ((("CB-01", None), ("250", None)),))
    _styled_table(msp, 14000.0, cols, head, ((("Nguyen", None), ("Hanoi", None)),))
    _styled_table(msp, 38000.0, cols, head, ((("CB-07", None), ("", None)),))
    _styled_table(msp, 50000.0, cols, head, ((("DẦM D5", None), ("250", None)),))
    for i, text in enumerate(("NAME", "D (mm)")):  # text alignment, no lines
        msp.add_text(text, height=TH, dxfattribs={"insert": (26000.0 + i * 2000.0, 56000.0)})
    for i, text in enumerate(("CB-09", "300")):
        msp.add_text(text, height=TH, dxfattribs={"insert": (26000.0 + i * 2000.0, 56000.0 - 700.0)})
    for i, text in enumerate(plan_texts):
        msp.add_text(text, height=TH, dxfattribs={"insert": (PLAN_X, PLAN_TOP - i * PLAN_STEP)})
    doc.saveas(root / FIXTURE_REL)
    work = base / "work"
    run_intake(root, work, "demo-marks", knowledge=PROPOSED_FONT_TABLE)
    write_structure(root, work)
    return work


def test_a_one_row_line_grid_schedule_with_a_mark_shaped_cell_is_a_table(tmp_path):
    work = build_one_row_work(tmp_path)
    doc = extract_marks(work, tmp_path / "input", check_inputs=True)
    assert validate("marks", doc) == []
    first, second = doc["tables"]
    assert (first["detection"], second["detection"]) == ("line_grid", "line_grid")
    assert [len(t["rows"]) for t in doc["tables"]] == [1, 1]
    assert [[m["text"] for m in t["rows"][0]["marks"]] for t in doc["tables"]] == [["CB-01"], ["D5"]]
    (match,) = doc["matching"]
    assert {m["key"] for m in match["matched"]} == {"cb-01"}
    assert {m["key"] for m in match["schedule_only"]} == {"d5"}
    assert {m["key"] for m in match["plan_only"]} == {"cb-02", "cb-09"}  # CB-09: its table has no rows read
    # a name under NAME, a row with one cell only, and the one-row table with no lines stay unparsed
    reasons = sorted((u["anchor_text"], u["detection"], u["reason"]) for u in doc["unparsed_tables"])
    one = "fewer than two data rows with a cell in the mark column"
    assert reasons == [
        ("NAME", "line_grid", one),
        ("NAME", "line_grid", one),
        ("NAME", "text_alignment", "fewer than two data rows aligned under the header columns"),
    ]
    assert sorted(u["bbox"][0] for u in doc["unparsed_tables"] if u["detection"] == "line_grid") == [
        14000.0,
        38000.0,
    ]


# --- item 5 (271): a numbered run of texts a callout pattern claims is a mark family (bm-1 .. bm-7) --------


def test_a_run_of_numbered_plate_looking_texts_is_a_mark_family(tmp_path):
    work = build_marks_work(
        tmp_path, plan_texts=("bm-1", "bm-2", "bm-3", "bm-4", "BM12", "PL-1", "PL-2", "pl 7", "D1")
    )
    marks = extract_marks(work, tmp_path / "input", check_inputs=True)
    plan = sorted(p["mark"] for p in marks["plan_marks"] if p["mark"].lower().startswith(("bm", "pl", "d")))
    assert plan == [
        "D1",
        "bm-1",
        "bm-2",
        "bm-3",
        "bm-4",
    ]  # BM12, PL-1, PL-2, pl 7 are plates (no run of three)
    sets = {s["family"]: s for s in marks["summary"]["mark_sets"]}
    assert sets["BM"]["members"] == ["bm-1", "bm-2", "bm-3", "bm-4"]
    callouts = extract_callouts(work)
    plates = sorted(c["display_text"] for c in callouts["candidates"] if c["kind"] == "plate")
    assert plates == [
        "BM12",
        "PL-1",
        "PL-2",
        "bm-1",
        "bm-2",
        "bm-3",
        "bm-4",
        "pl 7",
    ]  # callouts keeps its view


def test_a_run_needs_three_consecutive_numbers_of_one_prefix_style_and_height(tmp_path):
    from tekla_harness.callouts import numbered_run_labels

    def entry(
        eid: str, text: str, style: str = "S", height: float = 3.5, printed: bool = True
    ) -> dict[str, Any]:
        e: dict[str, Any] = {"id": eid, "display_text": text, "style": style, "height": height}
        if not printed:
            e["printed"] = False
        return e

    sheet_of = {f"T{n:06d}": {"sheet_id": "s1"} for n in range(1, 40)}
    entries = [
        entry("T000001", "BM-1"),
        entry("T000002", "BM-2"),
        entry("T000003", "BM-4"),  # 1 2 4: no run of three
        entry("T000004", "PL-5"),
        entry("T000005", "PL-6"),
        entry("T000006", "PL-7"),  # a run
        entry("T000007", "PL-4", style="OTHER"),  # another style: not joined to the run 5 6 7
        entry("T000008", "BM-3", height=7.0),  # another height: not joined
        entry("T000009", "PL-11"),
        entry("T000010", "PL-12"),
        entry("T000011", "PL-13", printed=False),  # does not print: 11 12 13 is no run
        entry("T000012", "D1"),  # no callout pattern claims D1 D2 D3: marks already, no run to report
        entry("T000013", "D2"),
        entry("T000014", "D3"),
    ]
    assert numbered_run_labels(entries, sheet_of) == {"T000004", "T000005", "T000006"}
    sheet_of["T000005"] = {"sheet_id": "s2"}  # a run is per sheet
    assert numbered_run_labels(entries, sheet_of) == set()


# --- item 5 (R-f, 290): `dẦm d-n` labels repeated on one sheet are plan labels, not detail headings --------


def test_title_form_labels_that_repeat_on_a_sheet_are_plan_marks(tmp_path):
    work = build_work(
        tmp_path,
        s1=["dẦm d-1", "dẦm d-1", "dẦm d-2", "dẦm d-1", "C5"],  # a framing plan labelled with member words
        s2=["dẦm d-3"],  # one heading on another sheet: a detail title
        styled=[],
        paper=[],
    )
    marks = extract_marks(work, tmp_path / "input", check_inputs=True)
    assert validate("marks", marks) == []
    forms = sorted(
        (p["sheet"], p["mark"], p["form"]) for p in marks["plan_marks"] if p["mark"].startswith("d-")
    )
    assert forms == [
        ("model#01", "d-1", "plain"),
        ("model#01", "d-1", "plain"),
        ("model#01", "d-1", "plain"),
        ("model#01", "d-2", "plain"),  # d-2 stands once, but the sheet labels its beams with member words
        ("model#02", "d-3", "title"),
    ]
    assert all(p["title_member_word"] is None for p in marks["plan_marks"] if p["form"] == "plain")
    (match,) = marks["matching"]
    assert {m["key"] for m in match["plan_only"]} >= {"d-1", "d-2"}
    assert {m["key"] for m in match["schedule_only"]} == {"d-3"}
    (said,) = [w for w in marks["warnings"] if "plan labels" in w]
    assert "4 title-form" in said and "model#01" in said


def test_a_family_whose_titles_repeat_less_than_three_times_stays_headings(tmp_path):
    work = build_work(
        tmp_path,
        s1=["dẦm d-1", "dẦm d-1", "dẦm d-2", "dẦm d-3", "dẦm c-1", "dẦm c-1", "dẦm c-1"],
        styled=[],
        s2=[],
        paper=[],
    )
    marks = extract_marks(work, tmp_path / "input")
    forms = {(p["mark"], p["form"]) for p in marks["plan_marks"] if p["mark"][0] in "dc"}
    # c-1 stands three times (plan labels); d-1 twice is two views of one detail: headings
    assert forms == {("d-1", "title"), ("d-2", "title"), ("d-3", "title"), ("c-1", "plain")}
    (said,) = [w for w in marks["warnings"] if "plan labels" in w]
    assert "3 title-form" in said


def test_a_demoted_title_keeps_the_form_of_its_mark(tmp_path):
    work = build_work(
        tmp_path,
        s1=["dẦm d-4 (220x400)"] * 3 + ["dẦm d-5.1"] * 3 + ["dẦm d-6", "dẦm d-6", "dẦm D-6"],
        styled=[],
        s2=[],
        paper=[],
    )
    marks = extract_marks(work, tmp_path / "input", check_inputs=True)
    forms = Counter((p["mark"], p["form"]) for p in marks["plan_marks"] if p["mark"].lower().startswith("d-"))
    assert forms == {
        ("d-4", "with_size"): 3,
        ("d-5.1", "sub_number"): 3,
        ("d-6", "plain"): 2,
        ("D-6", "plain"): 1,
    }
    assert {p["size"]["text"] for p in marks["plan_marks"] if p["mark"] == "d-4"} == {"220x400"}


# --- review C1 (285 detail sheets): a quantity tail makes a title a detail heading ---------------------


@pytest.mark.parametrize(
    "heading",
    ["dẦm d1 (sl= 02)", "dẦm d1 (SL: 2)", "dẦm d1 sl= 02", "dẦm d1 số lượng 5 cái", "dẦm d1 (SỐ LƯỢNG: 5)"],
)
def test_a_title_with_a_quantity_tail_keeps_its_family_headings(tmp_path, heading):
    """285 KC-17: one heading with a count tail and two section labels `DẦM D1` under its cross-sections
    are three title-form texts of one mark on a DETAIL sheet: none is a plan label."""
    work = build_work(tmp_path, s1=[heading, "DẦM D1", "DẦM D1", "DẦM D2"], styled=[], s2=[], paper=[])
    marks = extract_marks(work, tmp_path / "input", check_inputs=True)
    forms = Counter((p["mark"].lower(), p["form"]) for p in marks["plan_marks"] if p["mark"][0] in "dD")
    assert forms == {("d1", "title"): 3, ("d2", "title"): 1}
    assert not [w for w in marks["warnings"] if "plan labels" in w]


def test_the_tail_exempts_only_its_own_family_on_its_own_sheet(tmp_path):
    work = build_work(
        tmp_path,
        # sheet 1: D1 has a tailed heading (detail sheet), C1 repeats with no tail (a plan)
        s1=["dẦm d1 (sl= 02)", "DẦM D1", "DẦM D1", "dẦm c1", "dẦm c1", "dẦm c1"],
        # sheet 2: a D1 plan, no tail anywhere on that sheet
        s2=["dẦm d1", "dẦm d1", "dẦm d1"],
        styled=[],
        paper=[],
    )
    marks = extract_marks(work, tmp_path / "input")
    forms = Counter((p["sheet"], p["mark"].lower(), p["form"]) for p in marks["plan_marks"])
    assert forms[("model#01", "d1", "title")] == 3
    assert forms[("model#01", "c1", "plain")] == 3
    assert forms[("model#02", "d1", "plain")] == 3


def test_a_word_that_merely_ends_in_sl_is_no_quantity_tail(tmp_path):
    work = build_work(tmp_path, s1=["dẦm d1 wsl= 2", "DẦM D1", "DẦM D1"], styled=[], s2=[], paper=[])
    marks = extract_marks(work, tmp_path / "input")
    assert {p["form"] for p in marks["plan_marks"] if p["mark"].lower() == "d1"} == {"plain"}
