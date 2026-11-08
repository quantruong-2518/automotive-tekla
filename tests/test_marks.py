"""marks: member marks, schedule tables and plan-to-schedule matching. Grammar tests are unit tests on
`parse_mark` / `parse_title` / `header_keyword`; the rest runs on a real intake work folder (synthetic
drawing, see _marks_fixtures)."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest

from _marks_fixtures import BLOCKED_H, BLOCKED_SUB, KINH, PROJECT, build_gate_work, build_marks_work
from tekla_harness.callouts import run_callouts
from tekla_harness.cli import main
from tekla_harness.marks import (
    extract_marks,
    header_keyword,
    mark_key,
    marks_questions,
    parse_mark,
    parse_title,
    run_marks,
)
from tekla_harness.schemas import validate
from tekla_harness.sheet_text import ReaderError
from tekla_harness.status import build_status

REL = "plans/set.dxf"
TIMES = chr(0xD7)  # the multiplication sign


@pytest.fixture(scope="module")
def base(tmp_path_factory) -> Path:
    """The synthetic world: `input/` and `work/` (intake + sheets document)."""
    root = tmp_path_factory.mktemp("marks")
    build_marks_work(root)
    return root


@pytest.fixture(scope="module")
def doc(base) -> dict[str, Any]:
    return extract_marks(base / "work", base / "input", check_inputs=True)


@pytest.fixture
def world(base, tmp_path) -> tuple[Path, Path]:
    """(input folder, work folder) of a private copy."""
    shutil.copytree(base, tmp_path / "w")
    return tmp_path / "w" / "input", tmp_path / "w" / "work"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def plan(doc: dict[str, Any], mark: str) -> list[dict[str, Any]]:
    return [p for p in doc["plan_marks"] if p["mark"] == mark]


def table_with(doc: dict[str, Any], header: str) -> dict[str, Any]:
    (t,) = [t for t in doc["tables"] if any(h["display_text"] == header for h in t["header"])]
    return t


def matching(doc: dict[str, Any]) -> dict[str, Any]:
    (m,) = [m for m in doc["matching"] if m["file"] == REL]
    return m


# --- mark grammar ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "mark", "numbers", "separators", "suffix"),
    [
        ("D1", "D1", ["1"], [""], ""),
        ("D1.1", "D1.1", ["1", "1"], ["", "."], ""),
        ("D1-1", "D1-1", ["1", "1"], ["", "-"], ""),
        ("D1a", "D1a", ["1"], [""], "a"),
        ("D1.9A", "D1.9A", ["1", "9"], ["", "."], "A"),
        ("C-01", "C-01", ["01"], ["-"], ""),
        ("GTM- 1", "GTM- 1", ["1"], ["- "], ""),
        ("gm1", "gm1", ["1"], [""], ""),
    ],
)
def test_mark_forms(text, mark, numbers, separators, suffix):
    m = parse_mark(text)
    assert m is not None
    assert (m.text, m.numbers, m.separators, m.suffix, m.size) == (
        mark,
        tuple(numbers),
        tuple(separators),
        suffix,
        None,
    )


@pytest.mark.parametrize(
    ("text", "mark", "b", "h"),
    [
        ("D1.1(220X350)", "D1.1", 220, 350),
        ("D1(220x500)", "D1", 220, 500),
        ("C1 (220x220)", "C1", 220, 220),
        ("C1 (220" + TIMES + "220)", "C1", 220, 220),
        ("D2 ( 200 x 400 )", "D2", 200, 400),
    ],
)
def test_mark_with_section_keeps_the_numbers_as_written(text, mark, b, h):
    m = parse_mark(text)
    assert m is not None and m.text == mark
    assert m.size is not None and (m.size["b"], m.size["h"]) == (b, h)  # drawing units, not converted


@pytest.mark.parametrize(
    "text",
    ["a200", "s150", "KC-01", "I300", "M20", "BM12", "S1 (h=120)", "D1.1.1", "DẦM D1", "1", "D", "D1 D2"],
)
def test_not_marks(text):
    assert parse_mark(text) is None


def test_keys_fold_case_and_whitespace_but_keep_separators():
    assert mark_key("GTM- 1") == "gtm-1" and mark_key("gtm1") == "gtm1"
    assert mark_key("D1.1") != mark_key("D1-1")
    assert parse_mark("D1.1").structure == parse_mark("D1-1").structure  # type: ignore[union-attr]
    assert parse_mark("D11").structure != parse_mark("D1.1").structure  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("text", "word", "mark"),
    [
        ("DẦM D1.1", "DẦM", "D1.1"),
        ("DẦM  D1.1", "DẦM", "D1.1"),
        ("CỘT C1", "CỘT", "C1"),
        ("ĐÀI CỌC DC1", "ĐÀI CỌC", "DC1"),
        ("GIẰNG MÓNG GM1", "GIẰNG MÓNG", "GM1"),
        ("BEAM B1", "BEAM", "B1"),
        ("COLUMN C1 (300x300)", "COLUMN", "C1"),
        ("chi tiết dầm D2-1 TL 1/25", "dầm", "D2-1"),
    ],
)
def test_title_member_words(text, word, mark):
    found = parse_title(text)
    assert found is not None and found[0] == word and found[1].text == mark


@pytest.mark.parametrize("text", ["MẶT BẰNG ĐỊNH VỊ CỘT T1", "CỘT TẦNG 1", "DẦM", "BEAMS B1"])
def test_not_titles(text):
    assert parse_title(text) is None


@pytest.mark.parametrize(
    ("text", "priority"),
    [
        ("KÝ HIỆU", 0),
        ("ký hiệu", 0),
        ("KÝ HIỆU:", 0),
        ("MARK", 0),
        ("TÊN CẤU KIỆN", 1),
        ("MEMBER", 1),
        ("TÊN", 2),
        ("NAME", 2),
        ("NAME (mm)", 2),
        ("DRAWING NAME", None),
        ("TÊN BẢN VẼ", None),
        ("KY HIEU", None),  # diacritics are significant
    ],
)
def test_header_keywords_match_the_whole_cell(text, priority):
    assert header_keyword(text) == priority


# --- the work folder: marks and tables -------------------------------------------------------------


def test_document_is_schema_valid(doc):
    assert validate("marks", doc) == []
    assert doc["files"][0]["line_grid"]["status"] == "read"


def test_example_is_valid(example):
    assert validate("marks", example("marks")) == []


@pytest.mark.parametrize(
    "damage",
    [
        lambda d: d["plan_marks"][0].update(confidence="high"),
        lambda d: d["plan_marks"][0].update(form="title"),  # a title needs its member word
        lambda d: next(t for t in d["tables"] if t["header_blocked"]).update(mark_column=0),
        lambda d: d["question_counts"].update(callout_ambiguous=1),  # another producer's code
    ],
)
def test_schema_rejects_damaged_documents(example, damage):
    doc = example("marks")
    damage(doc)
    assert validate("marks", doc)


def test_plan_marks_of_each_form(doc):
    (d2,) = plan(doc, "D2")
    assert d2["form"] == "with_size" and d2["size"] == {"b": 220, "h": 500, "text": "220x500"}
    (d11,) = plan(doc, "D1.1")
    assert d11["form"] == "with_size" and d11["lexical"]["separators"] == ["", "."]
    (d1a,) = plan(doc, "D1a")
    assert d1a["form"] == "plain" and d1a["in_callouts"] is True
    assert plan(doc, "gm1")[0]["in_callouts"] is False  # callouts lists upper-case prefixes only
    assert not plan(doc, "KC-01") and not plan(doc, "a200") and not plan(doc, "I300")
    assert all(p["confidence"] in ("medium", "low") for p in doc["plan_marks"])


def test_title_word_is_evidence_not_a_prefix_meaning(doc):
    (c2,) = plan(doc, "C2")
    assert c2["form"] == "title" and c2["title_member_word"] == {"word": "COLUMN", "confidence": "medium"}
    (d3,) = plan(doc, "D3")
    assert d3["title_member_word"]["word"] == "DẦM"
    # the prefix is still asked: a title word never answers it
    (q,) = [q for q in marks_questions(doc) if q["code"] == "member_mark_prefix_meaning"]
    assert {"C", "D"} <= {s["name"] for s in q["subjects"]}
    assert "COLUMN" not in json.dumps(q["subjects"]) and "answer" not in q  # no meaning taken from it
    assert {"COLUMN C2", "DẦM D3"} <= {r["found"] for r in q["refs"]}  # quoted as evidence, verbatim


def test_line_grid_table(doc):
    t = table_with(doc, "KÝ HIỆU")
    assert t["detection"] == "line_grid" and t["header_blocked"] is False
    assert [c["role"] for c in t["columns"]] == ["mark", "b", "h"]
    assert [[m["text"] for m in r["marks"]] for r in t["rows"]] == [["D1"], ["D2"], ["D1-1"], ["D9"]]
    assert t["rows"][1]["size"]["b"] == 220 and t["rows"][1]["size"]["h"] == 450
    assert t["confidence"] == "medium"
    schedule_ids = {c["entry_id"] for r in t["rows"] for c in r["cells"]}
    assert not schedule_ids & {p["text_ref"]["entry_id"] for p in doc["plan_marks"]}  # never a plan mark too


def test_text_aligned_steel_style_table(doc):
    t = table_with(doc, "NAME")
    assert t["detection"] == "text_alignment"
    assert [h["display_text"] for h in t["header"]] == ["NAME", "D (mm)", "TW (mm)", "BF (mm)", "TF (mm)"]
    rows = [[c["display_text"] for c in r["cells"]] for r in t["rows"]]
    assert rows == [["C1", "300", "6", "150", "8"], ["C2", "250", "5", "175", "8"]]
    assert [c["column"] for c in t["rows"][0]["cells"]] == [0, 1, 2, 3, 4]
    assert t["mark_column"] == 0 and all(r["size"] is None for r in t["rows"])


def test_blocked_header_table(doc):
    (t,) = [t for t in doc["tables"] if t["header_blocked"]]
    assert t["detection"] == "line_grid" and t["mark_column"] is None and t["confidence"] == "low"
    assert t["header_block_reasons"] and all(h["meaning"] == "blocked" for h in t["header"])
    assert t["blocked_columns"] == []  # a header-blocked table lists no column apart
    assert all(c["meaning"] == "blocked" for r in t["rows"] for c in r["cells"])
    assert all(not r["marks"] for r in t["rows"])
    blocked = [b for b in doc["blocked_marks"] if b["table"] == t["id"]]
    assert [b["display_text"] for b in blocked] == ["D7", "D8"]
    assert all(b["reason"].startswith("header_blocked:") for b in blocked)
    m = matching(doc)
    assert "d8" not in {x["key"] for x in m["matched"] + m["plan_only"] + m["schedule_only"]}
    assert {x["key"] for x in m["plan_only"]} >= {"d7"}  # the plan D7 is not matched to the blocked row


def test_blocked_text_is_never_paraphrased(doc):
    questions = marks_questions(doc)
    text = json.dumps(questions, ensure_ascii=False)
    assert "Ab\u00e7d" not in text and "D8" not in text


def test_unparsed_table(doc):
    (u,) = doc["unparsed_tables"]
    assert u["anchor_text"] == "MARK" and u["detection"] == "text_alignment"
    assert "fewer than two data rows" in u["reason"]


# --- matching ---------------------------------------------------------------------------------------


def test_exact_match_schedule_only_and_plan_only(doc):
    m = matching(doc)
    assert [x["key"] for x in m["matched"]] == ["c1", "c2", "d1", "d2"]
    assert [x["key"] for x in m["schedule_only"]] == ["d1-1", "d9"]
    assert {"b5", "d1.1", "d1a", "d3", "gm1"} <= {x["key"] for x in m["plan_only"]}
    assert all(x["confidence"] in ("medium", "low") for x in m["matched"])


def test_dotted_and_dashed_marks_are_variants_never_matched(doc):
    m = matching(doc)
    (variant,) = m["notation_variants"]
    assert [x["key"] for x in variant["marks"]] == ["d1-1", "d1.1"]
    assert variant["structure"] == {"prefix": "d", "numbers": [1, 1], "suffix": ""}
    assert "d1.1" not in {x["key"] for x in m["matched"]} and "d1-1" not in {x["key"] for x in m["matched"]}
    (q,) = [q for q in marks_questions(doc) if q["code"] == "mark_notation_equivalence"]
    assert q["blocking"] is True and q["file"] == REL
    assert q["subjects"] == [{"name": "D1-1 / D1.1", "count": 2}]


def test_size_conflict_question_quotes_both_entries(doc):
    (c,) = matching(doc)["size_conflicts"]
    assert c["mark"] == "D2" and c["plan_size"] == {"b": 220, "h": 500}
    assert (c["schedule_size"]["b"], c["schedule_size"]["h"]) == (220, 450)
    (q,) = [q for q in marks_questions(doc) if q["code"] == "mark_size_conflict"]
    assert q["blocking"] is True
    ref = q["refs"][0]
    assert c["plan_entry_id"] in ref["where"] and c["schedule_entry_id"] in ref["where"]


def test_question_counts(doc):
    prefixes = {p["lexical"]["prefix"].upper() for p in doc["plan_marks"]}
    assert doc["question_counts"] == {
        "mark_notation_equivalence": 1,
        "mark_size_conflict": 1,
        "member_mark_prefix_meaning": len(prefixes),
        "schedule_table_unparsed": 1,
    }


def test_without_input_dir_a_native_dxf_falls_back_to_text_alignment(base):
    doc = extract_marks(base / "work")
    assert validate("marks", doc) == []
    assert doc["files"][0]["line_grid"]["status"] == "unavailable"
    assert any("line grids not read" in w for w in doc["warnings"])
    assert {t["detection"] for t in doc["tables"]} == {"text_alignment"}
    assert not any(t["header_blocked"] for t in doc["tables"])  # blocked headers need a grid


# --- the command ------------------------------------------------------------------------------------


def test_run_writes_documents_and_question_ids_are_stable(world):
    root, work = world
    first = run_marks(work, root)
    assert first.exit_code == 0 and first.summary["questions"] == 4
    q1 = load(work / "marks-questions.json")
    assert validate("intake", q1) == [] and validate("marks", load(work / "marks.json")) == []
    second = run_marks(work, root)
    q2 = load(work / "marks-questions.json")
    assert [(q["id"], q["key"]) for q in q1["questions"]] == [(q["id"], q["key"]) for q in q2["questions"]]
    assert second.summary["blocking_open"] == 3  # with member_mark_prefix_meaning
    registry = load(work / "question-registry.json")
    assert {
        e["producer"] for e in registry["questions"].values() if e["code"].startswith(("mark", "member_mark"))
    } == {"marks"}


def test_cli_exit_codes(world, capsys, tmp_path):
    root, work = world
    assert main(["marks", str(work), "--input-dir", str(root)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["project_id"] == PROJECT and out["tables"] == 3
    assert main(["marks", str(tmp_path / "nowhere")]) == 2
    (work / "question-registry.json").unlink()
    assert main(["marks", str(work)]) == 2
    capsys.readouterr()


def test_cli_refuses_a_changed_input(world, capsys):
    root, work = world
    dxf = root / REL
    dxf.write_bytes(dxf.read_bytes() + b"\n")
    assert main(["marks", str(work), "--input-dir", str(root)]) == 1
    assert "changed since intake" in capsys.readouterr().err


def test_extract_on_a_folder_without_inventory(tmp_path):
    with pytest.raises(ReaderError) as exc:
        extract_marks(tmp_path)
    assert exc.value.exit_code == 2


def test_status_sees_marks_fresh_after_a_run(tmp_path):
    work = build_marks_work(tmp_path, full=True)
    root = tmp_path / "input"
    run_callouts(work, root)
    before = {p["producer"]: p for p in build_status(work)["producers"]}
    assert before["marks"]["outputs"]["status"] == "missing"
    run_marks(work, root)
    after = {p["producer"]: p for p in build_status(work)["producers"]}
    assert after["marks"]["outputs"]["status"] == "fresh"
    assert after["marks"]["questions"]["blocking_open"] == 3


# --- review fixes ---------------------------------------------------------------------------------


def test_rotated_header_keyword_is_an_unparsed_table_not_a_crash(tmp_path, capsys):
    """A header keyword that is not an upright cell text used to raise StopIteration (traceback, exit 1)."""
    from ezdxf.filemanagement import readfile

    from _callout_fixtures import write_structure
    from _dxf_fixtures import build_set
    from tekla_harness.intake import run_intake

    root = tmp_path / "input"
    (root / "plans").mkdir(parents=True)
    dxf = readfile(str(build_set(tmp_path, "src.dxf")))
    msp = dxf.modelspace()
    msp.add_text("MARK", height=350, dxfattribs={"insert": (14000.0, 44000.0), "rotation": 90.0})
    msp.add_text("D1", height=350, dxfattribs={"insert": (14000.0, 43000.0)})
    msp.add_text("D2", height=350, dxfattribs={"insert": (14000.0, 42300.0)})
    dxf.saveas(root / REL)
    work = tmp_path / "work"
    run_intake(root, work, "demo-rot")
    write_structure(root, work)

    code = main(["marks", str(work)])  # native DXF without --input-dir: text alignment only
    capsys.readouterr()
    assert code == 0
    out = load(work / "marks.json")
    assert any("rotated" in u["reason"] for u in out["unparsed_tables"])


# --- tool wave 2: the schedule gate per column (fix 8) and the counts (fix 11) ---------------------------

NO_PLAN_SIZE = "the plan mark has no size"
NO_SIZE_COLUMN = "the schedule table has no size column"
SIZE_HEADER_BLOCKED = "the schedule header cells that could name a size column are blocked"
SIZE_CELLS_BLOCKED = "the schedule size cells are blocked"


@pytest.fixture(scope="module")
def gate_base(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("gate")
    build_gate_work(root)
    return root


@pytest.fixture(scope="module")
def gate(gate_base) -> dict[str, Any]:
    return extract_marks(gate_base / "work", gate_base / "input", check_inputs=True)


def header_entry(table: dict[str, Any], text: str) -> dict[str, Any]:
    (h,) = [h for h in table["header"] if h["display_text"] == text]
    return h


def matched(doc: dict[str, Any], key: str) -> dict[str, Any]:
    (m,) = [m for m in matching(doc)["matched"] if m["key"] == key]
    return m


def test_gate_document_is_schema_valid(gate):
    assert validate("marks", gate) == []
    assert gate["files"][0]["line_grid"]["status"] == "read"


def test_a_blocked_header_cell_outside_the_mark_column_goes_to_blocked_columns(gate):
    t = table_with(gate, "KÝ HIỆU")
    kinh = header_entry(t, KINH)
    assert kinh["meaning"] == "blocked"
    assert t["header_blocked"] is False and t["mark_column"] == 0 and t["header_block_reasons"] == []
    assert t["blocked_columns"] == [
        {"column": 3, "entry_id": kinh["entry_id"], "reason": kinh["block_reason"]}
    ]
    # a blocked text under the keyword, in the mark column's own header cell: the keyword names the
    # column, so it neither blocks the table nor is a blocked column
    assert header_entry(t, BLOCKED_SUB)["meaning"] == "blocked"
    assert header_entry(t, BLOCKED_SUB)["column"] == 0
    assert [c["role"] for c in t["columns"]] == ["mark", "b", "h", None]
    assert [[m["text"] for m in r["marks"]] for r in t["rows"]] == [["E1"], ["E2"], ["E3"]]
    for row in t["rows"]:  # numeric cells under the allowed headers stay allowed
        for cell in row["cells"]:
            assert cell["meaning"] == ("blocked" if cell["display_text"] == BLOCKED_H else "allowed")
    assert t["rows"][0]["size"]["b"] == 220 and t["rows"][0]["size"]["h"] == 300
    assert t["rows"][1]["size"] is None  # its h cell is blocked


def test_a_keywordless_grid_with_a_blocked_header_cell_is_read_on_its_mark_column(gate):
    """Before wave 2 one blocked header cell (KÍNH) blocked the whole table and its marks."""
    t = table_with(gate, "SỐ HIỆU")
    kinh = header_entry(t, KINH)
    assert t["header_blocked"] is False and t["mark_column"] == 0
    assert t["blocked_columns"] == [
        {"column": 1, "entry_id": kinh["entry_id"], "reason": kinh["block_reason"]}
    ]
    assert t["confidence"] == "low"  # the mark column is not named by a keyword
    assert [c["role"] for c in t["columns"]] == ["mark", None, "b"]
    assert [[m["text"] for m in r["marks"]] for r in t["rows"]] == [["F1"], ["F2"]]
    assert all(c["meaning"] == "allowed" for r in t["rows"] for c in r["cells"])
    assert not [b for b in gate["blocked_marks"] if b["table"] == t["id"]]
    assert {"f1", "f2"} <= {m["key"] for m in matching(gate)["matched"]}
    assert matched(gate, "f1")["confidence"] == "low"


def test_a_blocked_mark_column_header_still_blocks_the_table(gate):
    (t,) = [t for t in gate["tables"] if t["header_blocked"]]
    assert {h["display_text"] for h in t["header"]} == {"Abçd", "SL"}
    assert t["mark_column"] is None and t["confidence"] == "low" and t["blocked_columns"] == []
    assert [b["display_text"] for b in gate["blocked_marks"] if b["table"] == t["id"]] == ["G1", "G2"]
    assert "g1" not in {m["key"] for m in matching(gate)["matched"]}


def test_a_keywordless_grid_without_blocked_header_text_is_no_schedule(gate):
    """Mark-shaped texts between drawn lines, under a header with neither a keyword nor blocked text,
    are as likely a plan region: no table, and the texts stay plan marks."""
    assert not [t for t in gate["tables"] if any(h["display_text"] == "TT" for h in t["header"])]
    assert len(gate["tables"]) == 3
    assert {"h1", "h2"} <= {p["key"] for p in gate["plan_marks"]}


def test_every_match_says_whether_its_size_was_compared(doc, gate):
    assert matched(doc, "d2")["size_compared"] is True and "size_not_compared_reason" not in matched(
        doc, "d2"
    )
    assert matched(doc, "d1")["size_compared"] is False
    assert matched(doc, "d1")["size_not_compared_reason"] == NO_PLAN_SIZE
    assert matched(doc, "c1")["size_not_compared_reason"] == NO_SIZE_COLUMN
    assert matched(doc, "c2")["size_not_compared_reason"] == NO_PLAN_SIZE  # 'COLUMN C2' has no section
    assert matched(gate, "e1")["size_compared"] is True  # same size: compared, no conflict
    assert not matching(gate)["size_conflicts"]
    assert matched(gate, "e2")["size_not_compared_reason"] == SIZE_CELLS_BLOCKED
    assert matched(gate, "e3")["size_not_compared_reason"] == NO_PLAN_SIZE
    assert matched(gate, "f1")["size_not_compared_reason"] == SIZE_HEADER_BLOCKED


def test_summary_counts_size_comparisons(doc, gate):
    assert doc["summary"]["size_comparisons"] == {
        "compared": 1,
        "not_compared": 3,
        "by_reason": {NO_PLAN_SIZE: 2, NO_SIZE_COLUMN: 1},
    }
    s = gate["summary"]["size_comparisons"]
    assert (s["compared"], s["not_compared"]) == (1, 4)
    assert s["by_reason"] == {NO_PLAN_SIZE: 2, SIZE_CELLS_BLOCKED: 1, SIZE_HEADER_BLOCKED: 1}


def test_summary_counts_per_sheet(doc, gate):
    rows = doc["summary"]["by_sheet"]
    assert [(r["file"], r["sheet"]) for r in rows] == [(REL, "model#01")]
    (r,) = rows
    assert r["sheet_number"]["value"] == "S-101"
    s = doc["summary"]
    assert {k: r[k] for k in s["by_file"][0] if k in r} == {
        k: s[k]
        for k in ("plan_marks", "tables", "header_blocked_tables", "rows", "unparsed_tables", "blocked_marks")
    } | {"file": REL}
    assert (r["header_blocked_tables"], r["unparsed_tables"], r["blocked_marks"]) == (1, 1, 2)
    (g,) = gate["summary"]["by_sheet"]
    assert (g["tables"], g["header_blocked_tables"], g["rows"], g["blocked_marks"]) == (3, 1, 7, 2)


def test_summary_per_sheet_keeps_marks_on_no_sheet_apart(base, tmp_path):
    shutil.copytree(base, tmp_path / "w")
    work = tmp_path / "w" / "work"
    path = work / "structure" / f"{REL}.sheets.json"
    sheets = load(path)
    index = load(work / "text" / f"{REL}.json")
    off = {e["id"] for e in index["entries"] if e["display_text"] in ("B5", "gm1")}
    for sh in sheets["sheets"]:
        sh["text_ids"] = [i for i in sh["text_ids"] if i not in off]
    path.write_text(json.dumps(sheets), encoding="utf-8")
    out = extract_marks(work, tmp_path / "w" / "input")
    rows = {r["sheet"]: r for r in out["summary"]["by_sheet"]}
    assert list(rows) == ["model#01", None]
    assert rows[None]["plan_marks"] == 2 and rows[None]["sheet_number"] is None
    assert rows[None]["tables"] == 0
    assert sum(r["plan_marks"] for r in rows.values()) == out["summary"]["plan_marks"]
    assert validate("marks", out) == []


# --- tool wave 2: marks asks what every plan-mark prefix means (fix 1b) ---------------------------------


def prefix_question(doc: dict[str, Any]) -> dict[str, Any]:
    (q,) = [q for q in marks_questions(doc) if q["code"] == "member_mark_prefix_meaning"]
    return q


def test_every_plan_mark_prefix_gets_one_blocking_question_per_file(gate):
    q = prefix_question(gate)
    assert q["blocking"] is True and q["file"] == REL
    names = [s["name"] for s in q["subjects"]]
    assert names == sorted(names) and {"C", "D", "LT"} <= set(names)
    plan_prefixes = {p["lexical"]["prefix"].upper() for p in gate["plan_marks"]}
    assert set(names) == plan_prefixes  # plan marks only: G2 (blocked schedule cell) adds nothing
    lt = next(s for s in q["subjects"] if s["name"] == "LT")
    assert lt["count"] == 1 and lt["examples"] == [{"mark": "LT1", "count": 1}]
    assert q["count"] == sum(s["count"] for s in q["subjects"]) == len(gate["plan_marks"])
    assert all(r["where"].startswith("plan mark prefix ") and r["file"] == REL for r in q["refs"])
    assert {r.get("sheet") for r in q["refs"]} == {"model#01"}
    assert gate["question_counts"]["member_mark_prefix_meaning"] == len(names)


def test_prefixes_fold_case_and_titles_count(doc):
    q = prefix_question(doc)
    subjects = {s["name"]: s for s in q["subjects"]}
    assert "GM" in subjects and subjects["GM"]["examples"] == [{"mark": "gm1", "count": 1}]
    assert {"mark": "D3", "count": 1} in subjects["D"]["examples"]  # from the title 'DẦM D3'
    assert "KC" not in subjects and "I" not in subjects  # a sheet code and a section label are no marks


def test_prefix_refs_are_capped_but_counts_stay_true(gate, monkeypatch):
    import tekla_harness.marks as marks_mod

    monkeypatch.setattr(marks_mod, "MAX_PREFIX_REFS", 1)
    q = prefix_question(gate)
    e = next(s for s in q["subjects"] if s["name"] == "E")
    assert e["count"] == 3 and sum(r["where"].startswith("plan mark prefix E,") for r in q["refs"]) == 1
    assert q["truncated"] is True and q["count"] == len(gate["plan_marks"])


def test_old_callouts_prefix_answer_goes_stale_once_and_marks_asks_anew(tmp_path):
    """D6: the question moved from callouts to marks; an answer given to callouts' question goes stale
    (asked again), and marks' question never collides with the old registry key."""
    from tekla_harness.answers import record_answer

    work = build_gate_work(tmp_path)
    root = tmp_path / "input"
    seeded = _seed_callouts_prefix_answer(work)
    run_callouts(work, root)
    answers = {a["question_id"]: a for a in load(work / "answers.json")["answers"]}
    assert answers[seeded]["status"] == "stale"
    assert "no longer raises" in answers[seeded]["stale_reason"]
    run_marks(work, root)
    q = next(
        q
        for q in load(work / "marks-questions.json")["questions"]
        if q["code"] == "member_mark_prefix_meaning"
    )
    assert q["id"] != seeded and q["answer"] is None
    registry = load(work / "question-registry.json")["questions"]
    assert registry[q["key"]]["producer"] == "marks"
    record_answer(work, q["id"], "C cot", "A. Nguyen", {"C": "column"}, role="engineer")
    run_callouts(work, root)  # callouts no longer touches it
    run_marks(work, root)
    again = next(
        q
        for q in load(work / "marks-questions.json")["questions"]
        if q["code"] == "member_mark_prefix_meaning"
    )
    assert again["id"] == q["id"] and again["answer"]["values"] == {"C": "column"}


def _seed_callouts_prefix_answer(work: Path) -> str:
    """What a pre-wave-2 callouts run left behind: its prefix question with an active answer (the key is
    callouts' old ref wording). Returns the question id."""
    from tekla_harness.callouts import extract_callouts
    from tekla_harness.questions import dump_json, load_ledger, question_key, write_text_atomic

    ledger = load_ledger(work, None, create=False)
    sha = next(r["sha256"] for r in load(work / "inventory.json")["files"] if r["path"] == REL)
    # the refs callouts built before wave 2: per prefix (sorted), its first 10 member marks
    by_prefix: dict[str, list[dict[str, Any]]] = {}
    for c in extract_callouts(work)["candidates"]:
        if c["kind"] == "member_mark":
            by_prefix.setdefault(c["lexical"]["prefix"], []).append(c)
    refs = [
        {
            "file": REL,
            "where": f"prefix {prefix}, text entry {c['text_ref']['entry_id']}",
            "found": " ".join(c["display_text"].split()),
            "sheet": c["sheet"],
        }
        for prefix in sorted(by_prefix)
        for c in by_prefix[prefix][:10]
    ]
    key = question_key("member_mark_prefix_meaning", REL, sha, refs)
    reg = ledger.registry
    qid = f"Q-{reg['next_id']:03d}"
    reg["questions"][key] = {
        "id": qid,
        "code": "member_mark_prefix_meaning",
        "file": REL,
        "producer": "callouts",
        "status": "answered",
        "first_seen_run": reg["runs"],
        "last_seen_run": reg["runs"],
        "blocking": True,
        "file_sha256": sha,
    }
    reg["next_id"] += 1
    ledger.answers["answers"].append(
        {
            "question_id": qid,
            "key": key,
            "code": "member_mark_prefix_meaning",
            "file": REL,
            "answer_text": "C cot",
            "values": {"C": "column"},
            "answered_by": "A. Nguyen",
            "answered_by_role": "engineer",
            "answered_on": "2026-11-01",
            "status": "active",
        }
    )
    ledger.check()
    write_text_atomic(work / "question-registry.json", dump_json(ledger.registry))
    write_text_atomic(work / "answers.json", dump_json(ledger.answers))
    return qid


def test_a_table_added_to_another_file_does_not_re_key_this_files_questions(doc):
    """Table ids (S001..) number the tables across all files: questions must not quote them, or a table
    added to file A re-keys file B's mark_notation_equivalence / mark_size_conflict."""
    import copy

    from tekla_harness.questions import question_key

    def keys(d: dict[str, Any]) -> dict[str, str]:
        return {
            q["code"]: question_key(q["code"], q["file"], None, q["refs"])
            for q in marks_questions(d)
            if q["file"] == REL
        }

    before = keys(doc)
    assert "mark_notation_equivalence" in before
    refs = [r for q in marks_questions(doc) for r in q["refs"]]
    assert any("schedule table (header text entry T" in r["found"] + r["where"] for r in refs)
    assert not any(re.search(r"\bS\d{3}\b", r["found"] + r["where"]) for r in refs)

    shifted = copy.deepcopy(doc)
    extra = copy.deepcopy(shifted["tables"][0])
    extra["file"] = "0-another-file.dxf"
    renum = {t["id"]: f"S{n:03d}" for n, t in enumerate([extra, *shifted["tables"]], start=1)}
    for t in shifted["tables"]:
        t["id"] = renum[t["id"]]
    extra["id"] = "S001"
    shifted["tables"].insert(0, extra)
    for match in shifted["matching"]:
        for v in match["notation_variants"]:
            for m in v["marks"]:
                for s in m["schedule"]:
                    s["table"] = renum[s["table"]]
        for c in match["size_conflicts"]:
            c["table"] = renum[c["table"]]
    assert {t["id"] for t in shifted["tables"] if t["file"] == REL} != {
        t["id"] for t in doc["tables"] if t["file"] == REL
    }
    assert keys(shifted) == before
