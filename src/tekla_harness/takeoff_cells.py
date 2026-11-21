"""Cells of the take-off files, computed from rows, findings and questions (E8a).

Pure functions: plain dicts in, strings out, no I/O. Every cell of a take-off file comes from here, so a
hand edit cannot put a wrong confidence (run-3 M5), a typed axes value (C1) or a label position (M4) in it.

Shapes (all plain dicts):
- row: one `part-values` row {mark, field, state, value, cites {findings, questions, grid_systems}, hand_sum}.
- findings: {finding id: {confidence, stale}}. systems: {system id: {confidence}} (cited grid systems).
- questions: {question id: {answer}}; a truthy `answer` is the question's active answer.
- A cited id that is missing from its map raises KeyError: a caller that did not load it must fail loudly.
- entry: one family entry of a `contents` outline {family_id, label, offset, nearest_unlabelled_offset}.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from tekla_harness.findings import CONFIDENCE_RANK

FIELD_VI = {
    "size": "",
    "thickness": "dày",
    "depth": "cao",
    "length": "dài",
    "spacing": "nhịp",
    "count_plan": "mặt bằng",
    "count_schedule": "bảng",
    "piles_per_member": "cọc/cấu kiện",
    "level": "cao độ",
    "level_top": "đỉnh",
    "level_bottom": "đáy",
    "material": "vật liệu",
    "axes": "trục",
    "start_axes": "trục đầu",
    "end_axes": "trục cuối",
    "other": "khác",
}
CONF_VI = {"high": "Cao", "medium": "Trung bình", "low": "Thấp"}
NO_FINDING_VI = "chưa ghi nhận"
BLOCKS_EVERY_LOT_VI = "chặn mọi lô"
CHECK_FAILED_VI = "kiểm tra lại báo lỗi"
INPUT_CHECK_FAILED_VI = "đầu vào kiểm tra lại báo lỗi"
QUESTION_STATE_VI = {
    "blocking": "chặn", "non_blocking": "không chặn", "answered": "đã trả lời", "closed": "đã đóng",
}  # fmt: skip
NONE_VI = "không có"
MARKS_LABEL = "marks "  # the label `hand_sum_addends` gives a term that sums a mark's count
STATUS_VI = {
    "checked": "đã kiểm",
    "reviewed": "đã soát lại",
    "stale_input": "đầu vào đã đổi",
    "receipts_invalid": "biên nhận lỗi",
    "reading": "đang đọc",
    "reopened": "đã mở lại",
}
DASH = "—"
SHEET_COORDS = "tọa độ tờ"
MAX_TOKENS = 6
AXES_FIELDS = ("axes", "start_axes", "end_axes")

Row = Mapping[str, Any]


def _lowest(confidences: Iterable[str]) -> str | None:
    return min(confidences, key=lambda c: CONFIDENCE_RANK[c], default=None)


def row_confidence(row: Row, findings: Mapping[str, Any], systems: Mapping[str, Any]) -> str | None:
    """Lowest confidence of the cited findings, the `hand_sum` finding terms and the cited grid systems;
    None when the row cites none of them. A cited id missing from `findings` or `systems` raises KeyError."""
    cites = row.get("cites") or {}
    found = list(cites.get("findings") or [])
    found += [t["finding"] for t in (row.get("hand_sum") or {}).get("terms", []) if "finding" in t]
    found_conf = [findings[f]["confidence"] for f in found]
    system_conf = [systems[s]["confidence"] for s in cites.get("grid_systems") or []]
    return _lowest(found_conf + system_conf)


def mark_confidence(
    rows: Iterable[Row], findings: Mapping[str, Any], systems: Mapping[str, Any]
) -> str | None:
    """Lowest confidence over the rows of a mark; None when no row has one."""
    return _lowest(c for c in (row_confidence(r, findings, systems) for r in rows) if c)


def conf_text(confidence: str | None) -> str:
    return CONF_VI[confidence] if confidence else NO_FINDING_VI


def _ids(cites: Mapping[str, Any], key: str) -> list[str]:
    return list(cites.get(key) or [])


def value_cell(row: Row, findings: Mapping[str, Any], questions: Mapping[str, Any]) -> str:
    """The cell of one row without its field label. A stale cited finding, or a stale finding inside a
    `hand_sum` term, replaces the state text; a cited finding missing from `findings` raises KeyError."""
    cites = row.get("cites") or {}
    qs, fs = _ids(cites, "questions"), _ids(cites, "findings")
    terms = (row.get("hand_sum") or {}).get("terms", [])
    stale = [
        f
        for f in dict.fromkeys([*fs, *(t["finding"] for t in terms if "finding" in t)])
        if findings[f]["stale"]
    ]
    qtext = ", ".join(qs)
    value = row.get("value")
    if stale:
        text = f"đã cũ ({', '.join(stale)})"
    elif row["state"] == "seen":
        text = str(value)
    elif row["state"] == "asked":
        text = f"chờ trả lời ({qtext})" if value is None else f"{value}? ({qtext})"
    elif row["state"] == "unread":
        text = f"chưa đọc được ({qtext})"
    else:
        refs = " | ".join(x for x in (qtext, ", ".join(fs)) if x)
        text = f"không có trên bản vẽ ({refs})" if refs else "không có trên bản vẽ"
    answered = ", ".join(q for q in qs if (questions.get(q) or {}).get("answer"))
    if answered and row["state"] in ("asked", "unread"):
        text += f" — đã có trả lời {answered}, chưa cập nhật (§ 5)"
    elif answered:
        text += f" — đã trả lời {answered} (§ 5)"
    return text


def row_cell(row: Row, findings: Mapping[str, Any], questions: Mapping[str, Any]) -> str:
    """The cell text of one row: the field label, then the value or the state text."""
    return f"{FIELD_VI.get(row['field'], row['field'])} {value_cell(row, findings, questions)}".strip()


def field_cell(rows: Iterable[Row], findings: Mapping[str, Any], questions: Mapping[str, Any]) -> str:
    """The cell of several rows of one field: their `row_cell` texts joined ` | `."""
    return " | ".join(row_cell(r, findings, questions) for r in rows)


def axes_token(entry: Row, tol: float) -> str:
    """One family entry of a `contents` outline. An unlabelled line is named from its nearest label."""
    label, offset, nuo = entry["label"], entry["offset"], entry["nearest_unlabelled_offset"]
    if nuo is not None:
        base = f"trục không nhãn ({label} {offset - nuo:+.0f})"
        return f"{base} {nuo:+.0f}" if abs(nuo) >= tol else base
    if label is None:
        raise ValueError("a family with no labelled axis has no token: leave it out (item_token does)")
    return f"{label} {offset:+.0f}" if abs(offset) >= tol else str(label)


def item_token(item: Row, tol: float) -> str:
    """The position of one outline: its family tokens by `family_id`, joined ` / `. A family with no labelled
    axis names no line and is left out; with none left the token is `tọa độ tờ`."""
    labelled = [a for a in item.get("axes") or [] if a["label"] is not None]
    axes = sorted(labelled, key=lambda a: str(a["family_id"]))
    return " / ".join(axes_token(a, tol) for a in axes) or SHEET_COORDS


def _natural(text: str) -> list[tuple[int, int, str]]:
    return [(0, int(p), "") if p.isdigit() else (1, 0, p.casefold()) for p in re.split(r"(\d+)", text) if p]


def _fold(text: str) -> str:
    return unicodedata.normalize("NFC", text.strip()).casefold()


def positions(items: Iterable[Row], mark: str, tol: float) -> list[str]:
    """Distinct position tokens, natural order, of the outlines carrying `mark` or no mark."""
    wanted = _fold(mark)
    tokens = set()
    for item in items:
        texts = [_fold(str(m["text"])) for m in item.get("marks") or []]
        if not texts or wanted in texts:
            tokens.add(item_token(item, tol))
    return sorted(tokens, key=lambda t: (_natural(t), t))


def axes_cell(
    rows: Sequence[Row],
    tokens: Sequence[str],
    findings: Mapping[str, Any],
    questions: Mapping[str, Any],
) -> str:
    """The trục cell: geometry tokens, else start/end axes rows. A typed `axes` row never fills it."""
    if tokens:
        extra = len(tokens) - MAX_TOKENS
        return "; ".join(tokens[:MAX_TOKENS]) + (f" … (+{extra}, § 7)" if extra > 0 else "")
    start = [value_cell(r, findings, questions) for r in rows if r["field"] == "start_axes"]
    end = [value_cell(r, findings, questions) for r in rows if r["field"] == "end_axes"]
    if start or end:
        return f"{' | '.join(start) or '—'} → {' | '.join(end) or '—'}"
    pending = [r for r in rows if r["field"] in AXES_FIELDS and r["state"] in ("unread", "asked")]
    qs = sorted({q for r in pending for q in _ids(r.get("cites") or {}, "questions")})
    return f"chưa đọc được ({', '.join(qs)})" if qs else "—"


def status_line(part: Row) -> str:
    """Section 6 of a take-off file, from one `status.parts[]` entry. Non-blocking questions never appear. A
    part with `check_failed`, or whose input failed its check (`input_check_failed`), is never `dựng được`,
    whatever its `ready` says. The part's own `check_failed` wins over its inputs'."""
    if part.get("ready") and not part.get("check_failed") and not part.get("input_check_failed"):
        return "dựng được"
    reasons = []
    if part.get("status") != "locked":
        reasons.append(f"chưa khóa ({STATUS_VI[part['status']]})")
    if part.get("blocking_open_ids"):
        reasons.append(f"chờ trả lời ({', '.join(part['blocking_open_ids'])})")
    if part.get("blocked_by_project"):
        reasons.append(f"{BLOCKS_EVERY_LOT_VI} (00-plan)")
    if part.get("check_failed"):
        reasons.append(CHECK_FAILED_VI)  # the hash says ready, `part check` does not
    elif part.get("input_check_failed"):
        reasons.append(f"{INPUT_CHECK_FAILED_VI} ({', '.join(part['input_check_failed'])})")
    return " · ".join(reasons)


def hand_sum_text(addends: Sequence[tuple[str, int]]) -> str:
    """`cộng tay: F-012 14 + F-013 12 = 26`. A term shows its bare id: the text up to the first space; a
    `marks <mark>` term shows the mark whole, because a mark may hold a space."""

    def shown(label: str) -> str:
        return label[len(MARKS_LABEL) :] if label.startswith(MARKS_LABEL) else label.split(None, 1)[0]

    terms = " + ".join(f"{shown(f)} {n}" for f, n in addends)
    return f"cộng tay: {terms} = {sum(n for _, n in addends)}"
