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

from _callout_fixtures import COLUMN_X, REL, S1_TEXTS, build_work
from tekla_harness.schemas import validate
from tekla_harness.sheet_text import (
    MAX_TITLES,
    ReaderError,
    list_sheets,
    normalize,
    reading_order,
    sheet_text,
)


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
        src = by_id[out["id"]]
        assert out["display_text"] == src["display_text"]  # never re-decoded here
        assert out["encoding"] == src["decode"]["encoding_used"]
        assert out["flags"] == src["flags"] and out["confidence"] == src["confidence"]
        assert (out["x"], out["y"]) == (src["position"]["x"], src["position"]["y"])
        assert set(out) - {"tag", "block_name", "case_uncertain"} == {
            "id", "row", "display_text", "encoding", "confidence", "flags", "layer", "style",
            "x", "y", "height", "rotation", "entity_type",
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
    assert [e["id"] for e in doc["entries"]] == [e["id"] for e in full["entries"][:5]]
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


@pytest.mark.parametrize("name", ["sheet-list", "sheet-text"])
def test_examples_are_valid(example, name):
    assert validate("sheet-text", example(name)) == []


def test_schema_rejects_damaged_documents(example):
    doc = example("sheet-text")
    doc["entries"][0]["decoded_text"] = "x"  # only compact fields
    assert validate("sheet-text", doc)
    doc = example("sheet-text")
    doc["kind"] = "sheet_other"
    assert validate("sheet-text", doc)
    doc = example("sheet-list")
    doc["files"][0]["sheets"][0]["titles"] *= 6  # at most five
    assert validate("sheet-text", doc)
