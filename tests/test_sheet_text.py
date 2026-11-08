"""sheet_text: list_sheets and sheet_text over a real intake work folder (see _callout_fixtures).

The work folder is built once per module with the real `run_intake` and `extract_sheets`. Tests that damage a
folder work on a copy.
"""

from __future__ import annotations

import json
import shutil
import unicodedata
from pathlib import Path
from typing import Any

import pytest
from ezdxf.filemanagement import new

from _callout_fixtures import COLUMN_X, REL, S1_TEXTS, build_work
from tekla_harness.cli import main
from tekla_harness.intake import dump_json, run_intake
from tekla_harness.knowledge import EMPTY_TABLE
from tekla_harness.schemas import validate
from tekla_harness.sheet_text import (
    DEFAULT_MAX_ENTRIES,
    MAX_TITLES,
    STRUCTURE_DIR,
    ReaderError,
    find_text,
    list_sheets,
    normalize,
    reading_order,
    sheet_text,
    truncation_warning,
)
from tekla_harness.sheets import extract_sheets
from tekla_harness.text_gate import BLOCK_REASONS, meaning_block_reason


@pytest.fixture(scope="module")
def work(tmp_path_factory) -> Path:
    return build_work(tmp_path_factory.mktemp("sheet-text"))


@pytest.fixture
def damaged(work, tmp_path) -> Path:
    """A copy of the work folder a test may break."""
    target = tmp_path / "copy"
    shutil.copytree(work, target)
    return target


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def text_index(work: Path) -> dict[str, Any]:
    return load(work / "text" / f"{REL}.json")


def entry(
    eid: str, x: float | None, y: float | None, height: float | None = 10.0, text: str = "t"
) -> dict[str, Any]:
    return {"id": eid, "position": {"x": x, "y": y}, "height": height, "display_text": text}


# --- list_sheets ----------------------------------------------------------------------------------


def test_list_sheets_one_row_per_sheet_with_printed_numbers(work):
    doc = list_sheets(work, check_inputs=True)
    assert validate("sheet-text", doc) == []
    assert doc["kind"] == "sheet_list" and doc["project_id"] == "demo-callouts"
    assert [f["path"] for f in doc["files"]] == [REL]  # notes.txt is not a drawing
    sheets = {s["sheet_id"]: s for s in doc["files"][0]["sheets"]}
    assert list(sheets) == ["model#01", "model#02", "Plot#01"]
    assert sheets["model#01"]["sheet_number"] == {"value": "S-101", "confidence": "medium"}
    assert sheets["model#02"]["sheet_number"]["value"] == "S-102"
    assert sheets["Plot#01"]["sheet_number"]["value"] == "S-201"
    assert sheets["model#01"]["bbox"] == [0.0, 0.0, 84100.0, 59400.0]
    assert sheets["model#01"]["detection_confidence"] == "medium"
    assert sheets["model#01"]["duplicate_of"] is None
    assert doc["summary"] == {
        "files": 1,
        "listed": 1,
        "skipped": 0,
        "sheets": 3,
        "text_entries": len(text_index(work)["entries"]),
    }
    total = sum(s["text_count"] for s in sheets.values())
    assert total + doc["files"][0]["unassigned_text"] == doc["files"][0]["text_entries"]


def test_titles_are_the_largest_distinct_texts_max_five(work):
    sheet = list_sheets(work)["files"][0]["sheets"][0]
    titles = sheet["titles"]
    assert 1 <= len(titles) <= MAX_TITLES
    heights = [t["height"] for t in titles]
    assert heights == sorted(heights, reverse=True)
    texts = [t["display_text"] for t in titles]
    assert len(texts) == len(set(texts))  # identical texts once


def test_long_title_is_cut_and_marked(damaged):
    index = load(damaged / "text" / f"{REL}.json")
    biggest = max(index["entries"], key=lambda e: e["height"] or 0)
    biggest["display_text"] = "word " * 60
    biggest["height"] = 99999.0
    (damaged / "text" / f"{REL}.json").write_text(json.dumps(index), encoding="utf-8")
    titles = [t for s in list_sheets(damaged)["files"][0]["sheets"] for t in s["titles"] if t["truncated"]]
    assert titles and titles[0]["display_text"].endswith("…") and len(titles[0]["display_text"]) <= 121


def test_nothing_absolute_in_the_outputs(work):
    for doc in (list_sheets(work), sheet_text(work, REL, "model#01")):
        dumped = json.dumps(doc, ensure_ascii=False)
        assert str(work.parent) not in dumped and "/tmp" not in dumped


def test_missing_sheets_document_skips_the_file_with_a_warning(damaged):
    (damaged / "structure" / f"{REL}.sheets.json").unlink()
    doc = list_sheets(damaged)
    assert validate("sheet-text", doc) == []
    row = doc["files"][0]
    assert (row["status"], row["sheets"]) == ("skipped", None)
    assert row["text_entries"] > 0 and "read-structure" in row["reason"]
    assert any("sheets.json is missing" in w for w in doc["warnings"])


def test_stale_structure_is_warned(damaged, work):
    summary = {"inventory_sha256": "0" * 64}
    (damaged / "structure-summary.json").write_text(json.dumps(summary), encoding="utf-8")
    assert any("stale" in w for w in list_sheets(damaged)["warnings"])
    import hashlib

    good = {"inventory_sha256": hashlib.sha256((damaged / "inventory.json").read_bytes()).hexdigest()}
    (damaged / "structure-summary.json").write_text(json.dumps(good), encoding="utf-8")
    assert not any("stale" in w for w in list_sheets(damaged)["warnings"])


def test_sheets_built_from_another_dxf_is_refused(damaged):
    path = damaged / "structure" / f"{REL}.sheets.json"
    sheets = load(path)
    sheets["file"]["sha256"] = "f" * 64
    path.write_text(json.dumps(sheets), encoding="utf-8")
    with pytest.raises(ReaderError) as err:
        list_sheets(damaged)
    assert err.value.exit_code == 1 and "sha256" in str(err.value)


def test_a_text_index_path_leaving_the_work_folder_is_refused(damaged):
    path = damaged / "inventory.json"
    inv = load(path)
    for row in inv["files"]:
        if row["text_index"]:
            row["text_index"] = "../elsewhere.json"
    path.write_text(json.dumps(inv), encoding="utf-8")
    with pytest.raises(ReaderError) as err:
        list_sheets(damaged)
    assert err.value.exit_code == 1 and "outside the work folder" in str(err.value)


def test_missing_inventory_and_folder_are_usage_errors(tmp_path):
    with pytest.raises(ReaderError) as err:
        list_sheets(tmp_path / "nope")
    assert err.value.exit_code == 2
    (tmp_path / "empty").mkdir()
    with pytest.raises(ReaderError) as err:
        list_sheets(tmp_path / "empty")
    assert err.value.exit_code == 2 and "inventory.json" in str(err.value)


# --- sheet_text -----------------------------------------------------------------------------------


def expected_column() -> list[str]:
    return [t.replace("%%c", "Ø") for t in S1_TEXTS]


def test_sheet_text_entries_are_compact_and_in_reading_order(work):
    doc = sheet_text(work, REL, "model#01", check_inputs=True)
    assert validate("sheet-text", doc) == []
    assert doc["file"] == REL
    assert doc["sheet"]["sheet_number"] == {"value": "S-101", "confidence": "medium"}
    index = text_index(work)
    sheet = next(
        s for s in load(work / "structure" / f"{REL}.sheets.json")["sheets"] if s["sheet_id"] == "model#01"
    )
    assert doc["counts"] == {
        "assigned": len(sheet["text_ids"]),
        "matched": len(sheet["text_ids"]),
        "returned": len(sheet["text_ids"]),
        "omitted": 0,
        "truncated": False,
    }
    by_id = {e["id"]: e for e in index["entries"]}
    for out in doc["entries"]:
        src = by_id[out["entry_id"]]
        assert out["display_text"] == src["display_text"]  # never re-decoded here
        assert out["encoding"] == src["decode"]["encoding_used"]
        assert out["flags"] == src["flags"] and out["confidence"] == src["confidence"]
        assert (out["x"], out["y"]) == (src["position"]["x"], src["position"]["y"])
        assert set(out) - {"tag", "block_name", "case_uncertain"} == {
            "entry_id", "row", "display_text", "meaning", "blocked_reason", "encoding", "confidence",
            "flags", "layer", "style", "x", "y", "height", "rotation", "entity_type",
        }  # fmt: skip
        assert ("tag" in out) == (src["entity_type"] == "ATTRIB")
    column = [
        e["display_text"] for e in doc["entries"] if e["x"] == COLUMN_X and e["display_text"] != "ROW-A"
    ]
    assert column[: len(S1_TEXTS)] == expected_column()  # y descending, one row each
    rows = [e["row"] for e in doc["entries"]]
    assert rows == sorted(rows)


def test_entries_of_one_row_read_left_to_right_even_when_y_differs_a_little(work):
    texts = [e["display_text"] for e in sheet_text(work, REL, "model#01")["entries"]]
    # ROW-B is 80 units higher than ROW-A (< 0.6 x 350) but to its right: same row, A first
    assert texts.index("ROW-A") + 1 == texts.index("ROW-B")


def test_attrib_entries_carry_tag_and_block_name(work):
    entries = sheet_text(work, REL, "model#01")["entries"]
    attribs = [e for e in entries if e["entity_type"] == "ATTRIB"]
    assert attribs and {"SHEET_NO"} <= {e["tag"] for e in attribs}
    assert all(e["block_name"] for e in attribs)
    assert all("tag" not in e for e in entries if e["entity_type"] != "ATTRIB")


def test_unknown_encoding_is_returned_as_stored_with_its_flags(work):
    entries = sheet_text(work, REL, "model#01")["entries"]
    odd = [e for e in entries if "encoding_unknown_non_ascii" in e["flags"]]
    assert odd and all(e["encoding"] == "unknown" and e["confidence"] == "low" for e in odd)
    assert any("tªn" in e["display_text"] for e in odd)  # the legacy-looking byte is not decoded here
    uncertain = [e for e in entries if e.get("case_uncertain")]
    assert uncertain and all(e["display_text"] == "d1" or e["encoding"] != "unicode" for e in uncertain)
    assert all("case_uncertain" not in e for e in entries if e not in uncertain)


def test_contains_is_case_insensitive_and_keeps_diacritics(work):
    def hits(term: str) -> list[str]:
        return [e["display_text"] for e in sheet_text(work, REL, "model#01", contains=term)["entries"]]

    assert hits("tầng") == ["TẦNG 2 +3.600"]  # lowercase query, uppercase text
    assert hits("TẦNG 2") == ["TẦNG 2 +3.600"]
    assert hits("TANG") == []  # diacritics are significant
    assert hits(unicodedata.normalize("NFD", "tầng")) == ["TẦNG 2 +3.600"]  # decomposed query
    assert normalize("TẦNG") == normalize(unicodedata.normalize("NFD", "tầng"))
    doc = sheet_text(work, REL, "model#01", contains="tầng")
    assert doc["query"]["contains"] == "tầng"
    assert doc["counts"]["matched"] == 1 and doc["counts"]["assigned"] > 1
    assert hits("") == hits("")  # empty filter = no filter
    assert sheet_text(work, REL, "model#01", contains="")["query"]["contains"] is None


def test_truncation_keeps_true_counts(work):
    full = sheet_text(work, REL, "model#01")
    doc = sheet_text(work, REL, "model#01", max_entries=5)
    assert [e["entry_id"] for e in doc["entries"]] == [e["entry_id"] for e in full["entries"][:5]]
    n = full["counts"]["assigned"]
    assert doc["counts"] == {"assigned": n, "matched": n, "returned": 5, "omitted": n - 5, "truncated": True}
    # the filter is applied before the cut
    filtered = sheet_text(work, REL, "model#01", contains="C", max_entries=2)
    all_c = sheet_text(work, REL, "model#01", contains="C")["counts"]["matched"]
    assert filtered["counts"]["matched"] == all_c > 2
    assert filtered["counts"]["returned"] == 2 and filtered["counts"]["omitted"] == all_c - 2


def test_sheet_without_a_printed_number_is_reachable_by_detector_id(damaged):
    path = damaged / "structure" / f"{REL}.sheets.json"
    sheets = load(path)
    for sh in sheets["sheets"]:
        sh["title_block"]["sheet_number"] = None
    path.write_text(json.dumps(sheets), encoding="utf-8")
    doc = sheet_text(damaged, REL, "model#02")
    assert doc["sheet"]["sheet_number"] is None and doc["entries"]


def test_bad_requests_are_usage_errors_that_say_what_exists(work):
    with pytest.raises(ReaderError) as err:
        sheet_text(work, "plans/other.dxf", "model#01")
    assert err.value.exit_code == 2 and REL in str(err.value)
    with pytest.raises(ReaderError) as err:
        sheet_text(work, REL, "model#99")
    assert err.value.exit_code == 2 and "model#01" in str(err.value)
    with pytest.raises(ReaderError) as err:
        sheet_text(work, "notes.txt", "model#01")
    assert err.value.exit_code == 2
    with pytest.raises(ReaderError) as err:
        sheet_text(work, REL, "model#01", max_entries=0)
    assert err.value.exit_code == 2


def test_sheet_text_is_deterministic(work):
    assert sheet_text(work, REL, "Plot#01") == sheet_text(work, REL, "Plot#01")
    assert list_sheets(work) == list_sheets(work)


# --- reading order (unit) -------------------------------------------------------------------------


def test_rows_anchor_on_their_first_entry_so_they_cannot_drift():
    # heights 10 -> tolerance 6. y 100 and 95 share a row; 90 is 10 below the row's anchor: a new row
    # (comparing with the previous entry would chain all four into one)
    items = [
        entry("T000001", 5, 100),
        entry("T000002", 1, 95),
        entry("T000003", 3, 90),
        entry("T000004", 2, 85),
    ]
    got = [(r, e["id"]) for r, e in reading_order(items)]
    assert got == [(0, "T000002"), (0, "T000001"), (1, "T000004"), (1, "T000003")]


def test_ties_break_on_id_and_missing_positions_go_last():
    items = [
        entry("T000009", None, None),
        entry("T000004", 1, 50),
        entry("T000003", 1, 50),
        entry("T000002", None, 10),
        entry("T000001", 2, None),
    ]
    got = [(r, e["id"]) for r, e in reading_order(items)]
    assert got[:2] == [(0, "T000003"), (0, "T000004")]
    assert got[2] == (1, "T000002")  # y but no x: placed, after x-bearing entries of its row
    assert got[3:] == [(None, "T000001"), (None, "T000009")]


def test_zero_or_missing_heights_give_exact_rows():
    items = [entry("T000001", 0, 10, height=None), entry("T000002", 1, 9.9999, height=0.0)]
    assert [r for r, _ in reading_order(items)] == [0, 1]


def test_check_inputs_validates_the_documents(damaged):
    path = damaged / "text" / f"{REL}.json"
    index = load(path)
    del index["attempts"]
    path.write_text(json.dumps(index), encoding="utf-8")
    assert list_sheets(damaged)["files"][0]["sheets"]  # default: version and sha256 only
    with pytest.raises(ReaderError) as err:
        list_sheets(damaged, check_inputs=True)
    assert err.value.exit_code == 1 and "text-index" in str(err.value)
    index["schema_version"] = "9.9"
    path.write_text(json.dumps(index), encoding="utf-8")
    with pytest.raises(ReaderError):
        list_sheets(damaged)


# --- schema ------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["sheet-list", "sheet-text", "find-text"])
def test_examples_are_valid(example, name):
    assert validate("sheet-text", example(name)) == []


def test_schema_rejects_damaged_documents(example):
    doc = example("sheet-text")
    doc["entries"][0]["decoded_text"] = "x"  # only compact fields
    assert validate("sheet-text", doc)
    doc = example("sheet-text")
    doc["entries"][0]["id"] = doc["entries"][0].pop("entry_id")  # the key is entry_id everywhere
    assert validate("sheet-text", doc)
    doc = example("sheet-text")
    doc["entries"][0]["blocked_reason"] = "because"
    assert validate("sheet-text", doc)
    doc = example("find-text")
    del doc["counts"]["blocked_entries_not_searchable"]
    assert validate("sheet-text", doc)
    doc = example("sheet-text")
    doc["kind"] = "sheet_other"
    assert validate("sheet-text", doc)
    doc = example("sheet-list")
    doc["files"][0]["sheets"][0]["titles"] *= 6  # at most five
    assert validate("sheet-text", doc)


# --- legacy-font gate -----------------------------------------------------------------------------


def patch_entries(work: Path, patches: dict[str, dict[str, Any]]) -> None:
    """Overwrite top-level fields of text-index entries by id (`unicode: True` also marks the decode
    as Unicode, so non-ASCII text is allowed)."""
    path = work / "text" / f"{REL}.json"
    index = load(path)
    for e in index["entries"]:
        patch = dict(patches.get(e["id"], {}))
        if patch.pop("unicode", False):
            e["decode"]["encoding_used"] = "unicode"
        e.update(patch)
    path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")


def by_text(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {e["display_text"]: e for e in doc["entries"]}


def test_entries_carry_meaning_and_blocked_reason(work):
    got = by_text(sheet_text(work, REL, "model#01"))
    assert got["TẦNG 2 +3.600"]["meaning"] == "allowed"  # Unicode
    assert got["TẦNG 2 +3.600"]["blocked_reason"] is None
    assert got["CB300-V"]["meaning"] == "allowed"  # ASCII, unknown encoding: nothing to decode
    assert got["4Ø16"]["meaning"] in ("allowed", "blocked")
    odd = [e for e in got.values() if "encoding_unknown_non_ascii" in e["flags"]]
    assert odd and all(e["meaning"] == "blocked" and e["blocked_reason"] in BLOCK_REASONS for e in odd)
    raw = {e["id"]: e["raw_text"] for e in text_index(work)["entries"]}
    proposed = [e for e in got.values() if "proposed_knowledge_row" in e["flags"]]
    assert {e["blocked_reason"] for e in proposed if not raw[e["entry_id"]].isascii()} == {
        "encoding_proposed"
    }
    # ASCII raw text in a proposed-row style stays allowed (%%c is ASCII in raw_text)
    assert [e for e in proposed if raw[e["entry_id"]].isascii() and e["meaning"] == "allowed"]
    # blocked text is returned as stored, not decoded
    assert any("tªn" in e["display_text"] for e in odd + proposed)


def test_gate_reasons_follow_the_full_entry(damaged):
    ids = {e["display_text"]: e["entry_id"] for e in sheet_text(damaged, REL, "model#01")["entries"]}
    conflict = ids["CB300-V"]
    contradiction = ids["C1"]
    patch_entries(
        damaged,
        {
            conflict: {"raw_text": "CB300-V\u00aa", "flags": ["knowledge_conflict"]},
            contradiction: {"raw_text": "C1\u00aa", "flags": ["unicode_evidence_contradicts_font"]},
        },
    )
    got = {e["entry_id"]: e for e in sheet_text(damaged, REL, "model#01")["entries"]}
    assert got[conflict]["blocked_reason"] == "knowledge_conflict"
    assert got[contradiction]["blocked_reason"] == "encoding_contradiction"
    assert got[contradiction]["meaning"] == "blocked"


def test_legacy_font_gate_block_counts_styles_and_question_ids(work):
    doc = sheet_text(work, REL, "model#01")
    gate = doc["legacy_font_gate"]
    blocked = [e for e in doc["entries"] if e["meaning"] == "blocked"]
    assert gate["blocked_entries"] == len(blocked) > 0
    assert gate["by_reason"] == {
        r: sum(e["blocked_reason"] == r for e in blocked)
        for r in BLOCK_REASONS
        if any(e["blocked_reason"] == r for e in blocked)
    }
    assert gate["styles"] == sorted({e["style"] for e in blocked})
    registry = load(work / "question-registry.json")["questions"]
    codes = {
        "font_encoding_proposed",
        "font_encoding_conflict",
        "text_encoding_hint",
        "encoding_unknown_non_ascii",
    }
    assert gate["question_ids"] == sorted(
        q["id"] for q in registry.values() if q["code"] in codes and q["file"] == REL
    )
    assert gate["question_ids"]  # the fixture raises them
    # a sheet without blocked text still reports the file's questions and zero entries
    clean = sheet_text(work, REL, "Plot#01")["legacy_font_gate"]
    assert clean["blocked_entries"] == 0 and clean["by_reason"] == {} and clean["styles"] == []


def test_gate_counts_the_whole_sheet_not_only_the_returned_entries(work):
    full = sheet_text(work, REL, "model#01")["legacy_font_gate"]
    one = sheet_text(work, REL, "model#01", contains="CB300", max_entries=1)
    assert one["legacy_font_gate"] == full and one["counts"]["returned"] == 1


def test_question_ids_skip_obsolete_other_files_and_other_codes(damaged):
    path = damaged / "question-registry.json"
    registry = load(path)

    def add(key: str, qid: str, code: str, file: str, status: str = "open") -> None:
        registry["questions"][key * 16] = {
            "id": qid, "code": code, "file": file, "producer": "intake", "status": status,
            "first_seen_run": 1, "last_seen_run": 1,
        }  # fmt: skip

    add("a", "Q-090", "font_encoding_conflict", REL)
    add("b", "Q-091", "text_encoding_hint", REL, "obsolete")
    add("c", "Q-092", "font_encoding_proposed", "other.dxf")
    add("d", "Q-093", "units_confirm_all", REL)
    add("e", "Q-1000", "font_encoding_proposed", REL, "answered")
    path.write_text(json.dumps(registry), encoding="utf-8")
    ids = sheet_text(damaged, REL, "model#01")["legacy_font_gate"]["question_ids"]
    assert ids == ["Q-003", "Q-004", "Q-005", "Q-090", "Q-1000"]  # numeric order, answered kept


def test_missing_registry_warns_and_lists_no_questions(damaged):
    (damaged / "question-registry.json").unlink()
    doc = sheet_text(damaged, REL, "model#01")
    assert doc["legacy_font_gate"]["question_ids"] == []
    assert any("question-registry.json is missing" in w for w in doc["warnings"])


def test_blocked_text_is_never_decoded_or_translated(work):
    doc = sheet_text(work, REL, "model#01")
    index = {e["id"]: e for e in text_index(work)["entries"]}
    for e in doc["entries"]:
        if e["meaning"] == "blocked":
            assert e["display_text"] == index[e["entry_id"]]["display_text"]


# --- one key, titles, truncation ------------------------------------------------------------------------


def test_entry_id_is_the_key_in_both_tools(work):
    sheet = list_sheets(work)["files"][0]["sheets"][0]
    entries = sheet_text(work, REL, "model#01")["entries"]
    assert all("id" not in e and e["entry_id"].startswith("T") for e in entries)
    assert {t["entry_id"] for t in sheet["titles"]} <= {e["entry_id"] for e in entries}


def test_titles_prefer_keywords_and_drop_grid_labels_numbers_and_years(damaged):
    index = text_index(damaged)
    first = [e for e in index["entries"] if e["position"]["x"] == COLUMN_X][:7]
    texts = ["1", "B2", "2017", "12.5", "mặt bằng  tầng 1", "SECTION A-A", "Notes"]
    heights = [900.0, 900.0, 900.0, 900.0, 100.0, 200.0, 50.0]
    patch_entries(
        damaged,
        {
            e["id"]: {"display_text": t, "raw_text": t, "height": h, "flags": [], "unicode": True}
            for e, t, h in zip(first, texts, heights, strict=True)
        },
    )
    sheet = list_sheets(damaged)["files"][0]["sheets"][0]
    titles = sheet["titles"]
    got = [(t["display_text"], t["matched_keyword"]) for t in titles[:3]]
    assert got == [("SECTION A-A", "SECTION"), ("mặt bằng tầng 1", "MẶT BẰNG"), ("Notes", "NOTE")]
    shown = {t["display_text"] for t in titles}
    assert not shown & {"1", "B2", "2017", "12.5"}
    assert all(t["matched_keyword"] is None for t in titles[3:]) and len(titles) == MAX_TITLES
    assert all(t["meaning"] == "allowed" and t["blocked_reason"] is None for t in titles)
    assert validate("sheet-text", list_sheets(damaged)) == []


def test_keywords_match_whole_words_in_nfd_and_english(damaged):
    index = text_index(damaged)
    first = [e for e in index["entries"] if e["position"]["x"] == COLUMN_X][:4]
    texts = [
        unicodedata.normalize("NFD", "CHI TIẾT DẦM"),
        "Drawing List",
        "PLANT ROOM",  # 'plan' at the start of another word is not a keyword
        "foundation plan",
    ]
    fields = {"height": 500.0, "flags": [], "unicode": True}
    patch_entries(
        damaged,
        {e["id"]: {"display_text": t, "raw_text": t, **fields} for e, t in zip(first, texts, strict=True)},
    )
    got = {
        t["display_text"]: t["matched_keyword"]
        for t in list_sheets(damaged)["files"][0]["sheets"][0]["titles"]
    }
    assert got[unicodedata.normalize("NFD", "CHI TIẾT DẦM")] == "CHI TIẾT"
    assert got["Drawing List"] == "DRAWING LIST"
    assert got["PLANT ROOM"] is None
    assert got["foundation plan"] == "PLAN"


def test_blocked_titles_get_no_keyword_and_sheets_count_blocked_text(damaged):
    ids = {e["display_text"]: e["id"] for e in text_index(damaged)["entries"]}
    victim = ids["CB300-V"]
    patch_entries(
        damaged,
        {
            victim: {
                "display_text": "PLAN\u00aa", "raw_text": "PLAN\u00aa", "height": 9999.0,
                "flags": ["proposed_knowledge_row"],
            }
        },
    )  # fmt: skip
    sheet = list_sheets(damaged)["files"][0]["sheets"][0]
    top = sheet["titles"][0]
    assert top["entry_id"] == victim and top["meaning"] == "blocked"
    assert top["blocked_reason"] == "encoding_proposed" and top["matched_keyword"] is None
    expected = sheet_text(damaged, REL, "model#01")["legacy_font_gate"]["blocked_entries"]
    assert sheet["blocked_text_count"] == expected
    assert list_sheets(damaged)["files"][0]["sheets"][2]["blocked_text_count"] == 0


def test_truncation_adds_a_warning_naming_the_max_that_returns_everything(work):
    doc = sheet_text(work, REL, "model#01", max_entries=5)
    n = doc["counts"]["assigned"]
    line = truncation_warning(doc)
    assert line and f"--max {n}" in line and "\n" not in line
    assert line in doc["warnings"]
    full = sheet_text(work, REL, "model#01", max_entries=n)
    assert truncation_warning(full) is None and full["warnings"] == []


def test_default_cap_applies_without_a_filter_and_not_with_one(work, monkeypatch):
    import tekla_harness.sheet_text as module

    monkeypatch.setattr(module, "DEFAULT_MAX_ENTRIES", 5)
    plain = sheet_text(work, REL, "model#01")
    assert plain["query"]["max_entries"] == 5 and plain["counts"]["truncated"]
    every = sheet_text(work, REL, "model#01", contains="c")
    assert every["query"]["max_entries"] is None
    assert every["counts"]["matched"] > 5 and not every["counts"]["truncated"]
    capped = sheet_text(work, REL, "model#01", contains="c", max_entries=2)
    assert capped["query"]["max_entries"] == 2 and capped["counts"]["truncated"]


# --- find_text ------------------------------------------------------------------------------------------


def two_file_work(work: Path, target: Path) -> Path:
    """A copy of `work` whose inventory also lists plans/zz.dxf (a copy of the first drawing's documents)."""
    shutil.copytree(work, target)
    second = "plans/zz.dxf"
    inv = load(target / "inventory.json")
    row = next(r for r in inv["files"] if r["path"] == REL)
    twin = json.loads(json.dumps(row))
    twin["path"] = second
    twin["text_index"] = row["text_index"].replace("set.dxf", "zz.dxf")
    inv["files"].append(twin)
    (target / "inventory.json").write_text(json.dumps(inv), encoding="utf-8")
    shutil.copy(target / "text" / f"{REL}.json", target / twin["text_index"])
    shutil.copy(target / "structure" / f"{REL}.sheets.json", target / "structure" / f"{second}.sheets.json")
    return target


def test_find_text_searches_every_sheet_of_one_file(work):
    doc = find_text(work, "c1", check_inputs=True)
    assert validate("sheet-text", doc) == [] and doc["kind"] == "find_text"
    assert [(h["sheet_id"], h["display_text"]) for h in doc["hits"]] == [
        ("model#01", "C1"),
        ("model#02", "C1"),
    ]
    first = doc["hits"][0]
    assert first["file"] == REL and first["sheet_number"]["value"] == "S-101"
    assert first["meaning"] == "allowed" and first["blocked_reason"] is None
    assert first["entry_id"] in {e["entry_id"] for e in sheet_text(work, REL, "model#01")["entries"]}
    assert doc["counts"]["hits"] == 2 and doc["query"] == {"contains": "c1", "file": None, "max_hits": None}


def test_find_text_over_two_files_and_the_file_filter(work, tmp_path):
    target = two_file_work(work, tmp_path / "two")
    doc = find_text(target, "C1")
    assert [h["file"] for h in doc["hits"]] == [REL, REL, "plans/zz.dxf", "plans/zz.dxf"]
    assert [f["path"] for f in doc["files"]] == [REL, "plans/zz.dxf"]
    assert [f["hits"] for f in doc["files"]] == [2, 2] and doc["counts"]["hits"] == 4
    only = find_text(target, "C1", file_rel="plans/zz.dxf")
    assert {h["file"] for h in only["hits"]} == {"plans/zz.dxf"} and only["counts"]["hits"] == 2
    assert only["query"]["file"] == "plans/zz.dxf"


def test_find_text_keeps_diacritics_and_nfc(work):
    hits = [h["display_text"] for h in find_text(work, "tầng")["hits"]]
    assert "TẦNG 2 +3.600" in hits and all("TẦNG" in h for h in hits)
    assert find_text(work, unicodedata.normalize("NFD", "TẦNG"))["hits"] == find_text(work, "tầng")["hits"]
    assert find_text(work, "tang")["counts"]["hits"] == 0


def test_find_text_counts_blocked_entries_and_says_the_search_is_incomplete(work):
    doc = find_text(work, "zzz-no-such-text")
    assert doc["counts"]["hits"] == 0
    blocked = sum(
        s["legacy_font_gate"]["blocked_entries"]
        for s in (sheet_text(work, REL, sid) for sid in ("model#01", "model#02", "Plot#01"))
    )
    assert doc["counts"]["blocked_entries_not_searchable"] == blocked > 0
    assert doc["files"][0]["blocked_entries"] == blocked
    assert doc["notes"] and "incomplete" in doc["notes"][0]
    assert doc["counts"]["unassigned_entries_not_searched"] == doc["files"][0]["unassigned_entries"]


def test_find_text_marks_a_blocked_hit(work):
    hit = find_text(work, "tªn")["hits"]
    assert hit and all(h["meaning"] == "blocked" and h["blocked_reason"] for h in hit)
    assert any("tªn" in h["display_text"] for h in hit)  # matched on the stored text, not decoded


def test_find_text_max_keeps_true_counts(work):
    doc = find_text(work, "c", max_hits=2)
    assert doc["counts"]["returned"] == 2 and doc["counts"]["truncated"]
    assert doc["counts"]["hits"] == find_text(work, "c")["counts"]["hits"] > 2
    assert doc["counts"]["omitted"] == doc["counts"]["hits"] - 2


def test_find_text_skips_files_without_sheets_and_says_why(work, tmp_path):
    target = two_file_work(work, tmp_path / "two")
    (target / "structure" / "plans" / "zz.dxf.sheets.json").unlink()
    doc = find_text(target, "C1")
    rows = {f["path"]: f for f in doc["files"]}
    assert rows["plans/zz.dxf"]["status"] == "skipped" and "read-structure" in rows["plans/zz.dxf"]["reason"]
    assert rows[REL]["status"] == "searched" and {h["file"] for h in doc["hits"]} == {REL}
    assert any("zz.dxf" in w and "missing" in w for w in doc["warnings"])


def test_find_text_usage_errors(work):
    bad: list[dict[str, Any]] = [
        {"contains": ""},
        {"contains": "x", "max_hits": 0},
        {"contains": "x", "file_rel": "nope.dxf"},
    ]
    for kwargs in bad:
        with pytest.raises(ReaderError) as err:
            find_text(work, **kwargs)
        assert err.value.exit_code == 2


def test_find_text_is_deterministic(work):
    assert find_text(work, "c") == find_text(work, "c")


# --- CLI ------------------------------------------------------------------------------------------------


def run_cli(capsys, *argv: str) -> tuple[int, Any, str]:
    code = main(list(argv))
    cap = capsys.readouterr()
    return code, (json.loads(cap.out) if cap.out.strip() else None), cap.err


def test_cli_sheet_text_warns_on_stderr_when_truncated(work, capsys):
    code, doc, err = run_cli(capsys, "sheet-text", str(work), REL, "model#01", "--max", "3")
    assert code == 0 and doc["counts"]["truncated"]
    assert f"--max {doc['counts']['assigned']}" in err and len(err.strip().splitlines()) == 1
    code, doc, err = run_cli(capsys, "sheet-text", str(work), REL, "model#01", "--max", "1000")
    assert code == 0 and err == "" and not doc["counts"]["truncated"]


def test_cli_sheet_text_contains_has_no_default_cap(work, capsys):
    code, doc, err = run_cli(capsys, "sheet-text", str(work), REL, "model#01", "--contains", "c")
    assert code == 0 and err == "" and doc["query"]["max_entries"] is None


def test_cli_find_text(work, capsys):
    code, doc, err = run_cli(capsys, "find-text", str(work), "--contains", "c1", "--file", REL)
    assert code == 0 and doc["kind"] == "find_text" and validate("sheet-text", doc) == []
    assert doc["counts"]["hits"] == 2 and "incomplete" in err  # blocked entries are called out on stderr
    code, doc, err = run_cli(capsys, "find-text", str(work), "--contains", "c", "--max", "1")
    assert code == 0 and doc["counts"]["truncated"] and "truncated" in err
    for argv in (
        ["find-text", str(work), "--contains", ""],
        ["find-text", str(work), "--contains", "x", "--max", "0"],
    ):
        code, out, err = run_cli(capsys, *argv)
        assert code == 2 and out is None and err


# --- sheet-less text: --unassigned (tool wave 2, fix 4) ---------------------------------------------------

LOOSE = "loose.dxf"


@pytest.fixture(scope="module")
def loose(tmp_path_factory) -> Path:
    """A work folder with one drawing on which no sheet is detected: every entry is unassigned."""
    base = tmp_path_factory.mktemp("loose")
    root = base / "input"
    root.mkdir()
    doc = new("R2018", setup=True)
    msp = doc.modelspace()
    msp.add_text("GHI CHU", height=250, dxfattribs={"insert": (0, 1000)})
    msp.add_text("C1", height=250, dxfattribs={"insert": (0, 0)})
    msp.add_text("C1 b\xb6n", height=250, dxfattribs={"insert": (3000, 0)})  # unknown encoding: blocked
    doc.saveas(root / LOOSE)
    work = base / "work"
    run_intake(root, work, "demo-loose", knowledge=EMPTY_TABLE)
    index = load(work / "text" / f"{LOOSE}.json")
    sheets = extract_sheets(root / LOOSE, index)
    assert sheets["sheets"] == [] and len(sheets["unassigned"]["text_ids"]) == 3
    (work / STRUCTURE_DIR).mkdir()
    (work / STRUCTURE_DIR / f"{LOOSE}.sheets.json").write_text(dump_json(sheets), encoding="utf-8")
    return work


def test_sheet_text_unassigned_reaches_the_text_of_a_sheetless_file(loose):
    doc = sheet_text(loose, LOOSE, None, unassigned=True, check_inputs=True)
    assert validate("sheet-text", doc) == []
    assert doc["sheet"] == {
        "sheet_id": "unassigned",
        "space": "model",
        "layout": None,
        "bbox": None,
        "sheet_number": None,
        "duplicate_of": None,
    }
    assert doc["query"] == {"unassigned": True, "contains": None, "max_entries": DEFAULT_MAX_ENTRIES}
    rows = [(e["row"], e["display_text"]) for e in doc["entries"]]
    assert rows == [(0, "GHI CHU"), (1, "C1"), (1, "C1 b\xb6n")]
    assert doc["counts"]["assigned"] == 3 and doc["legacy_font_gate"]["blocked_entries"] == 1
    assert doc["entries"][2]["meaning"] == "blocked"
    only_c1 = sheet_text(loose, LOOSE, None, unassigned=True, contains="c1")
    assert only_c1["counts"]["matched"] == 2 and only_c1["query"]["max_entries"] is None


def test_find_text_unassigned_searches_only_the_unassigned_entries(loose, work):
    doc = find_text(loose, "c1", unassigned=True, check_inputs=True)
    assert validate("sheet-text", doc) == []
    assert [(h["sheet_id"], h["sheet_number"], h["display_text"]) for h in doc["hits"]] == [
        ("unassigned", None, "C1"),
        ("unassigned", None, "C1 b\xb6n"),
    ]
    assert doc["query"] == {"contains": "c1", "file": None, "max_hits": None, "unassigned": True}
    counts = doc["counts"]
    assert counts["unassigned_entries_searched"] == 3 and counts["unassigned_entries_not_searched"] == 0
    assert counts["blocked_entries_not_searchable"] == 1
    assert doc["files"][0] == {
        "path": LOOSE,
        "status": "searched",
        "reason": None,
        "sheets_searched": 0,
        "entries_searched": 3,
        "blocked_entries": 1,
        "unassigned_entries": 3,
        "hits": 2,
    }
    # without the flag the same file has nothing to search, as before
    plain = find_text(loose, "c1")
    assert plain["hits"] == [] and plain["counts"]["unassigned_entries_not_searched"] == 3
    assert "unassigned" not in plain["query"] and "unassigned_entries_searched" not in plain["counts"]
    # a file with sheets: the entries on its sheets are not searched
    on_sheets = {h["entry_id"] for h in find_text(work, "c1")["hits"]}
    off_sheets = {h["entry_id"] for h in find_text(work, "c1", unassigned=True)["hits"]}
    assert on_sheets and not on_sheets & off_sheets


def test_unassigned_takes_ambiguous_entries_once_and_skips_unknown_ids(damaged):
    path = damaged / STRUCTURE_DIR / f"{REL}.sheets.json"
    sheets = load(path)
    entries = text_index(damaged)["entries"]
    ids = [e["id"] for e in entries if e["space"] == "model"]
    plot = next(e["id"] for e in entries if e["space"] == "Plot")
    sheets["unassigned"] = {"text_ids": [ids[0], plot, "T999999"], "ambiguous_text_ids": [ids[1], ids[0]]}
    path.write_text(json.dumps(sheets), encoding="utf-8")
    doc = sheet_text(damaged, REL, None, unassigned=True)
    assert [e["entry_id"] for e in doc["entries"]][:2] in ([ids[0], ids[1]], [ids[1], ids[0]])
    assert doc["counts"]["assigned"] == 3
    assert doc["sheet"]["space"] == "model, Plot"  # model space first, then the layouts by name
    model_rows = [e["row"] for e in doc["entries"][:2]]
    assert doc["entries"][2]["entry_id"] == plot and doc["entries"][2]["row"] == max(model_rows) + 1
    found = find_text(damaged, "%", unassigned=True)
    assert found["counts"]["unassigned_entries_searched"] == 3 == found["files"][0]["unassigned_entries"]


def test_a_sheet_request_carries_no_unassigned_key(work):
    query = sheet_text(work, REL, "model#01")["query"]
    assert query == {"contains": None, "max_entries": DEFAULT_MAX_ENTRIES}


def test_unassigned_and_a_sheet_id_exclude_each_other(loose):
    for sheet_id, unassigned in (("model#01", True), (None, False)):
        with pytest.raises(ReaderError) as err:
            sheet_text(loose, LOOSE, sheet_id, unassigned=unassigned)
        assert err.value.exit_code == 2


def test_cli_unassigned(loose, capsys):
    code, doc, _ = run_cli(capsys, "sheet-text", str(loose), LOOSE, "--unassigned")
    assert code == 0 and doc["sheet"]["sheet_id"] == "unassigned" and doc["counts"]["assigned"] == 3
    code, doc, _ = run_cli(capsys, "find-text", str(loose), "--contains", "C1", "--unassigned")
    assert code == 0 and doc["counts"]["hits"] == 2
    code, out, err = run_cli(capsys, "sheet-text", str(loose), LOOSE, "model#01", "--unassigned")
    assert code == 2 and out is None and "--unassigned" in err


# --- list-sheets: blocked text per file (tool wave 2, fix 11) ----------------------------------------------


def test_list_sheets_counts_the_blocked_text_of_the_whole_file(work, loose, damaged):
    row = list_sheets(work)["files"][0]
    blocked_on_sheets = sum(s["blocked_text_count"] for s in row["sheets"])
    every = sum(meaning_block_reason(e) is not None for e in text_index(work)["entries"])
    assert row["blocked_text_count"] == every >= blocked_on_sheets > 0
    assert list_sheets(loose)["files"][0]["blocked_text_count"] == 1  # all of it unassigned
    (damaged / STRUCTURE_DIR / f"{REL}.sheets.json").unlink()
    skipped = list_sheets(damaged)["files"][0]
    assert skipped["status"] == "skipped" and skipped["blocked_text_count"] is None
