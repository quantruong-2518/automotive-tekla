"""takeoff_cells: every cell of a take-off file is computed from rows, findings and questions (E8a).

Plain dicts in, strings out. All values are invented. Names marked regression pin a run-3 hand-edit error:
C1 (typed axes against geometry), M4 (a beam placed at its label), M5 (a low-confidence value shown medium).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unicodedata
from typing import Any

import pytest

from tekla_harness import takeoff_cells as tc

FINDINGS = {
    "F-001": {"confidence": "high", "stale": False},
    "F-002": {"confidence": "low", "stale": False},
    "F-003": {"confidence": "medium", "stale": True},
}
SYSTEMS = {"S001": {"confidence": "low"}, "S002": {"confidence": "high"}}


def _row(
    field: str = "size", state: str = "seen", value: str | None = "400x400", **cites: Any
) -> dict[str, Any]:
    return {"mark": "K1", "field": field, "state": state, "value": value, "cites": cites}


def test_regression_m5_confidence_is_lowest_cited() -> None:
    row = _row(findings=["F-001", "F-002"])
    assert tc.row_confidence(row, FINDINGS, SYSTEMS) == "low"
    hand = _row()
    hand["hand_sum"] = {"terms": [{"finding": "F-001"}, {"finding": "F-003"}, {"marks": ["K1"]}]}
    assert tc.row_confidence(hand, FINDINGS, SYSTEMS) == "medium"
    grid = _row(findings=["F-001"], grid_systems=["S001"])
    assert tc.row_confidence(grid, FINDINGS, SYSTEMS) == "low"
    assert tc.mark_confidence([_row(findings=["F-001"]), grid], FINDINGS, SYSTEMS) == "low"
    assert tc.mark_confidence([_row(findings=["F-001"])], FINDINGS, SYSTEMS) == "high"


def test_cited_id_missing_from_its_map_raises() -> None:
    # A dropped id would raise the shown confidence: the caller must fail loudly instead.
    with pytest.raises(KeyError):
        tc.row_confidence(_row(findings=["F-001", "F-999"]), FINDINGS, SYSTEMS)
    with pytest.raises(KeyError):
        tc.row_confidence(_row(findings=["F-001"], grid_systems=["S009"]), FINDINGS, SYSTEMS)
    with pytest.raises(KeyError):
        tc.row_confidence(_row(findings=["F-001"], grid_systems=["S001"]), FINDINGS, {})
    hand = _row()
    hand["hand_sum"] = {"terms": [{"finding": "F-001"}, {"finding": "F-999"}]}
    with pytest.raises(KeyError):
        tc.row_confidence(hand, FINDINGS, SYSTEMS)
    with pytest.raises(KeyError):
        tc.value_cell(_row(findings=["F-999"]), FINDINGS, {})


def test_row_without_finding_prints_chua_co_finding() -> None:
    row = _row()
    assert tc.row_confidence(row, FINDINGS, SYSTEMS) is None
    assert tc.mark_confidence([row], FINDINGS, SYSTEMS) is None
    assert tc.NO_FINDING_VI == "chưa ghi nhận"
    assert tc.conf_text(None) == "chưa ghi nhận"
    assert [tc.conf_text(c) for c in ("high", "medium", "low")] == ["Cao", "Trung bình", "Thấp"]
    assert tc.CONF_VI == {"high": "Cao", "medium": "Trung bình", "low": "Thấp"}
    assert tc.FIELD_VI["size"] == "" and tc.FIELD_VI["start_axes"] == "trục đầu"


def test_state_cells() -> None:
    q = {"Q-007": {"answer": None}}
    assert tc.row_cell(_row(), FINDINGS, q) == "400x400"
    assert tc.row_cell(_row("depth", value="600"), FINDINGS, q) == "cao 600"
    asked = _row("thickness", "asked", None, questions=["Q-007"])
    assert tc.row_cell(asked, FINDINGS, q) == "dày chờ trả lời (Q-007)"
    guess = _row("thickness", "asked", "250", questions=["Q-007"])
    assert tc.row_cell(guess, FINDINGS, q) == "dày 250? (Q-007)"
    unread = _row("count_plan", "unread", None, questions=["Q-007"])
    assert tc.row_cell(unread, FINDINGS, q) == "mặt bằng chưa đọc được (Q-007)"
    absent = _row("count_schedule", "absent", None, questions=["Q-007"], findings=["F-001"])
    assert tc.row_cell(absent, FINDINGS, q) == "bảng không có trên bản vẽ (Q-007 | F-001)"
    two = [_row("depth", value="600"), _row("depth", value="700")]
    assert tc.field_cell(two, FINDINGS, q) == "cao 600 | cao 700"
    assert tc.value_cell(_row("depth", value="600"), FINDINGS, q) == "600"
    assert tc.field_cell([], FINDINGS, q) == ""


def test_stale_finding_prints_da_cu() -> None:
    row = _row("length", value="5000", findings=["F-001", "F-003"])
    assert tc.row_cell(row, FINDINGS, {}) == "dài đã cũ (F-003)"


def test_stale_hand_sum_finding_term_prints_da_cu() -> None:
    hand = _row("count_plan", value="26")
    hand["hand_sum"] = {"terms": [{"finding": "F-001"}, {"finding": "F-003"}, {"marks": ["K1"]}]}
    assert tc.row_cell(hand, FINDINGS, {}) == "mặt bằng đã cũ (F-003)"
    both = _row("count_plan", value="26", findings=["F-003"])
    both["hand_sum"] = {"terms": [{"finding": "F-003"}, {"entry": "E-1"}]}
    assert tc.value_cell(both, FINDINGS, {}) == "đã cũ (F-003)"
    fresh = _row("count_plan", value="26")
    fresh["hand_sum"] = {"terms": [{"finding": "F-001"}]}
    assert tc.value_cell(fresh, FINDINGS, {}) == "26"


def test_answered_question_points_to_section_5() -> None:
    q = {"Q-007": {"answer": {"value": "x"}}, "Q-008": {"answer": None}}
    row = _row("depth", value="600", questions=["Q-007", "Q-008"])
    assert tc.row_cell(row, FINDINGS, q) == "cao 600 — đã trả lời Q-007 (§ 5)"
    absent = _row("depth", "absent", None, questions=["Q-007"])
    assert tc.row_cell(absent, FINDINGS, q) == "cao không có trên bản vẽ (Q-007) — đã trả lời Q-007 (§ 5)"


def test_answered_question_on_open_row_says_not_updated() -> None:
    q = {"Q-007": {"answer": {"value": "x"}}, "Q-008": {"answer": None}}
    asked = _row("depth", "asked", None, questions=["Q-007"])
    assert (
        tc.row_cell(asked, FINDINGS, q)
        == "cao chờ trả lời (Q-007) — đã có trả lời Q-007, chưa cập nhật (§ 5)"
    )
    unread = _row("depth", "unread", None, questions=["Q-007", "Q-008"])
    assert tc.row_cell(unread, FINDINGS, q) == (
        "cao chưa đọc được (Q-007, Q-008) — đã có trả lời Q-007, chưa cập nhật (§ 5)"
    )
    guess = _row("depth", "asked", "600", questions=["Q-007"])
    assert tc.row_cell(guess, FINDINGS, q).endswith(" — đã có trả lời Q-007, chưa cập nhật (§ 5)")
    unanswered = _row("depth", "asked", None, questions=["Q-008"])
    assert tc.row_cell(unanswered, FINDINGS, q) == "cao chờ trả lời (Q-008)"


def test_axes_token_offsets_and_tol() -> None:
    assert tc.axes_token({"label": "B", "offset": 0.0, "nearest_unlabelled_offset": None}, 50) == "B"
    assert tc.axes_token({"label": "B", "offset": 30.0, "nearest_unlabelled_offset": None}, 50) == "B"
    assert tc.axes_token({"label": "B", "offset": -120.4, "nearest_unlabelled_offset": None}, 50) == "B -120"
    near = {"label": "3", "offset": 1000.0, "nearest_unlabelled_offset": 40.0}
    assert tc.axes_token(near, 50) == "trục không nhãn (3 +960)"
    far = {"label": "3", "offset": 1000.0, "nearest_unlabelled_offset": 300.0}
    assert tc.axes_token(far, 50) == "trục không nhãn (3 +700) +300"
    on_tol = {"label": "3", "offset": 1000.0, "nearest_unlabelled_offset": 50.0}
    assert tc.axes_token(on_tol, 50) == "trục không nhãn (3 +950) +50"
    assert tc.axes_token({"label": "B", "offset": 50.0, "nearest_unlabelled_offset": None}, 50) == "B +50"


def test_regression_c1_unlabelled_line_token() -> None:
    entry = {"label": "D", "offset": -6000.0, "nearest_unlabelled_offset": 0.0}
    assert tc.axes_token(entry, 50) == "trục không nhãn (D -6000)"
    item = {
        "marks": [{"text": "P1"}],
        "axes": [
            {"family_id": "f2", "label": "2", "offset": 250.0, "nearest_unlabelled_offset": 0.0},
            {"family_id": "f1", "label": "E", "offset": -7000.0, "nearest_unlabelled_offset": 0.0},
        ],
    }
    assert tc.item_token(item, 50) == "trục không nhãn (E -7000) / trục không nhãn (2 +250)"
    assert tc.item_token({"marks": [], "axes": []}, 50) == "tọa độ tờ"


def test_family_without_labelled_axis_is_left_out() -> None:
    unlabelled = {"family_id": "f1", "label": None, "offset": 300.0, "nearest_unlabelled_offset": None}
    labelled = {"family_id": "f2", "label": "4", "offset": 0.0, "nearest_unlabelled_offset": None}
    assert tc.item_token({"axes": [unlabelled, labelled]}, 50) == "4"
    assert tc.item_token({"axes": [unlabelled]}, 50) == tc.SHEET_COORDS == "tọa độ tờ"
    with pytest.raises(ValueError):
        tc.axes_token(unlabelled, 50)


def _item(mark: str | None, label: str) -> dict[str, Any]:
    marks = [{"text": mark}] if mark else []
    return {
        "marks": marks,
        "axes": [{"family_id": "f", "label": label, "offset": 0.0, "nearest_unlabelled_offset": None}],
    }


def test_positions_by_mark_capped_at_6() -> None:
    items = [_item("K1", "10"), _item("k1", "4"), _item("K2", "9"), _item(None, "1"), _item("K1", "2")]
    assert tc.positions(items, "K1", 50) == ["1", "2", "4", "10"]
    ties = [_item(None, label) for label in ("b", "B", "a1", "A1")]
    assert tc.positions(ties, "K1", 50) == ["A1", "a1", "B", "b"]
    tokens = [str(n) for n in range(1, 9)]
    cell = tc.axes_cell([], tokens, FINDINGS, {})
    assert cell == "1; 2; 3; 4; 5; 6 … (+2, § 7)"
    assert tc.axes_cell([], tokens[:6], FINDINGS, {}) == "1; 2; 3; 4; 5; 6"


def test_positions_order_does_not_depend_on_hash_seed() -> None:
    code = (
        "import json\n"
        "from tekla_harness import takeoff_cells as tc\n"
        "ax = lambda s: {'marks': [], 'axes': [{'family_id': 'f', 'label': s, 'offset': 0.0,"
        " 'nearest_unlabelled_offset': None}]}\n"
        "items = [ax(s) for s in ('b', 'B', 'a1', 'A1', 'a 01', 'A 1', 'c', 'C')]\n"
        "print(json.dumps(tc.positions(items, 'K1', 50)))\n"
    )
    outputs = set()
    for seed in range(8):
        env = {**os.environ, "PYTHONHASHSEED": str(seed)}
        run = subprocess.run(
            [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True
        )
        outputs.add(run.stdout.strip())
    assert len(outputs) == 1
    assert json.loads(outputs.pop()) == ["A1", "a1", "A 1", "a 01", "B", "b", "C", "c"]


def test_positions_match_marks_after_nfc_normalisation() -> None:
    composed = unicodedata.normalize("NFC", "D\u1ea6M-1")
    decomposed = unicodedata.normalize("NFD", composed)
    assert composed != decomposed
    assert tc.positions([_item(decomposed, "1")], composed, 50) == ["1"]
    assert tc.positions([_item(composed, "1")], decomposed, 50) == ["1"]
    assert tc.positions([_item(decomposed, "1")], "DẦM-2", 50) == []


def test_regression_m4_typed_axes_row_never_in_cell() -> None:
    typed = _row("axes", value="D, E tại 2 và 9")
    assert tc.axes_cell([typed], [], FINDINGS, {}) == "—"
    assert tc.axes_cell([typed], ["B"], FINDINGS, {}) == "B"
    unread = _row("axes", "unread", None, questions=["Q-009"])
    assert tc.axes_cell([typed, unread], [], FINDINGS, {}) == "chưa đọc được (Q-009)"
    asked = _row("axes", "asked", None, questions=["Q-011"])
    assert tc.axes_cell([typed, asked], [], FINDINGS, {}) == "chưa đọc được (Q-011)"
    start = _row("start_axes", value="A/1")
    assert tc.axes_cell([typed, start], [], FINDINGS, {}) == "A/1 → —"


def test_start_end_cell() -> None:
    start, end = _row("start_axes", value="A/1"), _row("end_axes", value="A/3")
    assert tc.axes_cell([end, start], [], FINDINGS, {}) == "A/1 → A/3"
    asked = _row("end_axes", "asked", None, questions=["Q-010"])
    assert tc.axes_cell([start, asked], [], FINDINGS, {}) == "A/1 → chờ trả lời (Q-010)"
    assert tc.axes_cell([start, end], ["B"], FINDINGS, {}) == "B"


def test_start_end_cell_needs_findings_and_questions() -> None:
    stale = _row("start_axes", value="A/1", findings=["F-003"])
    assert tc.axes_cell([stale], [], FINDINGS, {}) == "đã cũ (F-003) → —"
    q = {"Q-010": {"answer": {"value": "x"}}}
    end = _row("end_axes", "asked", None, questions=["Q-010"])
    assert tc.axes_cell([end], [], FINDINGS, q) == (
        "— → chờ trả lời (Q-010) — đã có trả lời Q-010, chưa cập nhật (§ 5)"
    )
    with pytest.raises(TypeError):
        tc.axes_cell([stale], [])  # type: ignore[call-arg]  # pyright: ignore[reportCallIssue]


def test_status_line_never_lists_non_blocking() -> None:
    assert tc.status_line({"status": "locked", "ready": True, "blocking_open_ids": []}) == "dựng được"
    part = {
        "status": "checked",
        "ready": False,
        "blocking_open_ids": ["Q-004", "Q-005"],
        "blocked_by_project": True,
    }
    assert tc.status_line(part) == "chưa khóa (đã kiểm) · chờ trả lời (Q-004, Q-005) · chặn mọi lô (00-plan)"
    locked = {
        "status": "locked",
        "ready": False,
        "blocking_open_ids": ["Q-004"],
        "open_ids": ["Q-004", "Q-006"],
    }
    assert tc.status_line(locked) == "chờ trả lời (Q-004)"


def test_status_texts_are_public_vietnamese_constants() -> None:
    assert tc.BLOCKS_EVERY_LOT_VI == "chặn mọi lô"
    assert tc.STATUS_VI == {
        "checked": "đã kiểm",
        "reviewed": "đã soát lại",
        "stale_input": "đầu vào đã đổi",
        "receipts_invalid": "biên nhận lỗi",
        "reading": "đang đọc",
        "reopened": "đã mở lại",
    }
    assert tc.DASH == "—"
    for status, text in tc.STATUS_VI.items():
        assert tc.status_line({"status": status, "ready": False}) == f"chưa khóa ({text})"
    assert tc.status_line({"status": "locked", "ready": False, "blocked_by_project": True}) == (
        f"{tc.BLOCKS_EVERY_LOT_VI} (00-plan)"
    )
    with pytest.raises(KeyError):
        tc.status_line({"status": "unheard_of", "ready": False})


def test_status_line_never_says_buildable_for_a_part_whose_check_failed() -> None:
    assert tc.CHECK_FAILED_VI == "kiểm tra lại báo lỗi"
    # the hash alone says ready; the check says no (status --verify sets both fields)
    failed = {"status": "locked", "ready": False, "check_failed": True, "blocking_open_ids": []}
    assert tc.status_line(failed) == tc.CHECK_FAILED_VI
    both = {**failed, "blocking_open_ids": ["Q-004"], "blocked_by_project": True}
    assert (
        tc.status_line(both)
        == f"chờ trả lời (Q-004) · {tc.BLOCKS_EVERY_LOT_VI} (00-plan) · {tc.CHECK_FAILED_VI}"
    )
    # a ready flag that disagrees with check_failed never wins: no buildable text for a failed check
    assert tc.status_line({"status": "locked", "ready": True, "check_failed": True}) == tc.CHECK_FAILED_VI
    assert tc.status_line({"status": "locked", "ready": True, "check_failed": False}) == "dựng được"
    assert tc.status_line({"status": "locked", "ready": False, "check_failed": False}) == ""
    unlocked = {"status": "checked", "ready": False, "check_failed": True}
    assert tc.status_line(unlocked) == f"chưa khóa (đã kiểm) · {tc.CHECK_FAILED_VI}"


def test_status_line_names_the_input_whose_check_failed() -> None:
    assert tc.INPUT_CHECK_FAILED_VI == "đầu vào kiểm tra lại báo lỗi"
    part = {"status": "locked", "ready": False, "check_failed": False, "input_check_failed": ["B1-a", "B1-b"]}
    assert tc.status_line(part) == f"{tc.INPUT_CHECK_FAILED_VI} (B1-a, B1-b)"
    # never buildable, even when `ready` disagrees
    assert tc.status_line({**part, "ready": True}) == f"{tc.INPUT_CHECK_FAILED_VI} (B1-a, B1-b)"
    # the part's own failed check wins over its inputs'
    assert tc.status_line({**part, "check_failed": True}) == tc.CHECK_FAILED_VI
    # it joins the other reasons
    waiting = {**part, "blocking_open_ids": ["Q-004"]}
    assert tc.status_line(waiting) == f"chờ trả lời (Q-004) · {tc.INPUT_CHECK_FAILED_VI} (B1-a, B1-b)"
    assert tc.status_line({**part, "input_check_failed": []}) == ""


def test_status_line_works_for_every_status() -> None:
    from tekla_harness.part_receipts import STATUSES

    for status in STATUSES:  # the plan lists parts that are not eligible too
        line = tc.status_line({"status": status, "ready": False})
        assert line.startswith("chưa khóa (") if status != "locked" else line == ""


def test_hand_sum_text() -> None:
    assert tc.hand_sum_text([("F-012", 14), ("F-013", 12)]) == "cộng tay: F-012 14 + F-013 12 = 26"
    assert tc.hand_sum_text([("F-012", 5)]) == "cộng tay: F-012 5 = 5"


def test_hand_sum_text_shows_the_bare_id() -> None:
    addends = [("F-012 symbols", 14), ("T000471", 3), ("DC-1 symbols", 2)]
    assert tc.hand_sum_text(addends) == "cộng tay: F-012 14 + T000471 3 + DC-1 2 = 19"


def test_hand_sum_text_keeps_a_mark_with_a_space() -> None:
    assert tc.hand_sum_text([("marks K 1", 3)]) == "cộng tay: K 1 3 = 3"
    assert tc.hand_sum_text([("marks K 1", 3), ("marks K 2", 4)]) == "cộng tay: K 1 3 + K 2 4 = 7"
    assert tc.hand_sum_text([("F-012 symbols", 14), ("marks K-1", 2)]) == "cộng tay: F-012 14 + K-1 2 = 16"


ENGLISH_WORDS = re.compile(r"\b(finding|lot|checked|reviewed|stale_input|receipts_invalid)\b", re.IGNORECASE)


def test_no_cell_text_holds_an_english_word() -> None:
    q = {"Q-007": {"answer": {"value": "x"}}, "Q-008": {"answer": None}}
    cells = [
        tc.conf_text(None),
        *(tc.conf_text(c) for c in tc.CONF_VI),
        tc.NO_FINDING_VI,
        tc.BLOCKS_EVERY_LOT_VI,
    ]
    cells += [*tc.CONF_VI.values(), *tc.FIELD_VI.values(), *tc.STATUS_VI.values(), tc.SHEET_COORDS]
    for state in ("seen", "asked", "unread", "absent"):
        for value in (None, "600"):
            row = _row("depth", state, value, questions=["Q-007", "Q-008"], findings=["F-001", "F-003"])
            cells += [tc.row_cell(row, FINDINGS, q), tc.value_cell(row, FINDINGS, {})]
            cells.append(
                tc.axes_cell([_row("start_axes", state, value, questions=["Q-007"])], [], FINDINGS, q)
            )
    cells += [tc.axes_cell([_row("axes", "asked", None, questions=["Q-007"])], [], FINDINGS, q)]
    for status in (*tc.STATUS_VI, "locked"):
        part = {"status": status, "ready": False, "blocking_open_ids": ["Q-004"], "blocked_by_project": True}
        cells.append(tc.status_line(part))
    cells.append(tc.status_line({"status": "locked", "ready": True}))
    cells.append(tc.hand_sum_text([("F-012 symbols", 14), ("T000471", 3)]))
    cells.append(tc.item_token({"axes": []}, 50))
    assert all(isinstance(c, str) for c in cells)
    assert [c for c in cells if ENGLISH_WORDS.search(c)] == []
