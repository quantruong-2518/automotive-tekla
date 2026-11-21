"""`harness takeoff plan` (E8c): `takeoff/00-plan.md`, the parts by rank and the lots with what blocks them.

Fully generated from the `TakeoffContext` and the cells of `takeoff_cells` (no AI slot); written only when the
text differs. The `chặn mọi lô` row is `project_blocking_ids` as `harness status` gives it (no union);
after the `L<nn>` rows, one row per bookkeeping part that holds open blocking ids. An open blocking
question that is in no row is an internal error (exit 3). A part that is not eligible has no file and no
result: its values are never read. stdout is one JSON document (`takeoff-output` `$defs/plan`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tekla_harness.questions import write_text_atomic
from tekla_harness.questions_md import _need_impact
from tekla_harness.schemas import validate
from tekla_harness.takeoff_cells import (
    BLOCKS_EVERY_LOT_VI,
    DASH,
    NO_FINDING_VI,
    NONE_VI,
    QUESTION_STATE_VI,
    conf_text,
    field_cell,
    mark_confidence,
    status_line,
    value_cell,
)
from tekla_harness.takeoff_render import (
    ELIGIBLE,
    SIZE_FIELDS,
    TakeoffContext,
    TakeoffError,
    _cell,
    _check_cites,
    _groups,
)

EXIT_OK, EXIT_ENV = 0, 3
PLAN_FILE = "00-plan.md"
MAX_RESULTS = 3
TIMES = "\N{MULTIPLICATION SIGN}"
COUNT_FIELD = "count_plan"
TITLE_VI = "# 00 — Kế hoạch bóc bản vẽ — {project_id}"
SECTIONS_VI = ("Kết luận", "Thứ tự các phần", "Các lô", "Câu hỏi mở", "Nguồn")
CONCLUSION_VI = (
    "- {parts} phần, {rendered} phần đã có file bóc tách, {ready} phần sẵn sàng để dựng.",
    "- {blocking_open} câu hỏi chặn còn mở, trong đó {project_blocking} câu " + BLOCKS_EVERY_LOT_VI + ".",
    "- Mọi giá trị nằm trong file của từng phần; các bảng dưới đây chỉ tóm tắt.",
)
PARTS_HEADER_VI = ("#", "phần", "file", "kết quả chính", "độ tin cậy", "trạng thái")
LOTS_HEADER_VI = ("lô", "phần", "chặn bởi")
MISSING_VI = (
    "- **{id}** ("
    + QUESTION_STATE_VI["blocking"]
    + "): chưa có trong file câu hỏi nào — chạy lại lệnh đã tạo ra câu này."
)
SOURCES_VI = (
    "- Trạng thái các phần và câu hỏi: `harness status {shown}`.",
    "- File của từng phần: `harness takeoff render {shown}`.",
    "- File này do `harness takeoff plan {shown}` sinh ra; không sửa tay, chạy lại lệnh để cập nhật.",
)


def _qid(question_id: str) -> int:
    return int(question_id[2:])


def _table(header: tuple[str, ...], rows: list[list[str]]) -> list[str]:
    lines = [f"| {' | '.join(header)} |", f"| {' | '.join('---' for _ in header)} |"]
    return lines + [f"| {' | '.join(cells)} |" for cells in rows]


def _main_results(ctx: TakeoffContext, part: dict[str, Any]) -> tuple[str, str]:
    """(kết quả chính, độ tin cậy) of an eligible part: up to three subjects, then `(+k)`."""
    rows = ctx.values(part)
    _check_cites(ctx, part["id"], rows)
    f, q = ctx.findings, ctx.questions
    shown = []
    for subject, sel in _groups(rows).items():
        sizes = ", ".join(
            field_cell(x, f, q) for n in SIZE_FIELDS if (x := [r for r in sel if r["field"] == n])
        )
        counts = " | ".join(value_cell(r, f, q) for r in sel if r["field"] == COUNT_FIELD)
        shown.append(" ".join(t for t in (subject, sizes, f"{TIMES}{counts}" if counts else "") if t))
    extra = len(shown) - MAX_RESULTS
    result = "; ".join(shown[:MAX_RESULTS]) + (f" (+{extra})" if extra > 0 else "")
    return _cell(result or DASH), conf_text(mark_confidence(rows, f, ctx.systems)) if rows else NO_FINDING_VI


def _open_blocking(ctx: TakeoffContext) -> list[str]:
    return [i.id for i in ctx.items.values() if i.is_open and i.blocking]


def _lots(ctx: TakeoffContext) -> list[tuple[str, str, list[str]]]:
    """(lot, part, blocking ids): the project row (`project_blocking_ids` as status gives it), then `L<nn>`
    per part by rank, then one row (lot `—`) per bookkeeping part that holds open blocking ids. An open
    blocking question that no row holds raises `TakeoffError` (exit 3): `harness status` owns what blocks
    what."""
    numbered = [(f"L{n:02d}", i, list(ctx.status[i]["blocking_open_ids"])) for i, n in ctx.rank.items()]
    bookkeeping = [
        (DASH, p["id"], list(ctx.status[p["id"]]["blocking_open_ids"]))
        for p in sorted(ctx.manifest["parts"], key=lambda p: (p["order"], p["id"]))
        if p["kind"] == "bookkeeping" and ctx.status[p["id"]]["blocking_open_ids"]
    ]
    lots = [(BLOCKS_EVERY_LOT_VI, DASH, list(ctx.project_blocking_ids)), *numbered, *bookkeeping]
    held = {q for _, _, ids in lots for q in ids}
    if lost := sorted(set(_open_blocking(ctx)) - held, key=_qid):
        raise TakeoffError(
            EXIT_ENV, f"internal: the open blocking questions {', '.join(lost)} are in no row of the lots"
        )
    return lots


def _summary(ctx: TakeoffContext) -> dict[str, int]:
    lots = _lots(ctx)
    return {
        "parts": len(ctx.rank),
        "rendered": sum(ctx.status[i]["status"] in ELIGIBLE for i in ctx.rank),
        "ready": sum(bool(ctx.status[i]["ready"]) for i in ctx.rank),
        "blocking_open": len(set(_open_blocking(ctx)) | {q for _, _, ids in lots for q in ids}),
        "project_blocking": len(ctx.project_blocking_ids),
    }


def render_plan(ctx: TakeoffContext) -> str:
    """The whole text of `00-plan.md`."""
    parts = {p["id"]: p for p in ctx.manifest["parts"]}
    numbers = _summary(ctx)
    open_items = sorted(
        (i for i in ctx.items.values() if i.is_open), key=lambda i: (not i.blocking, _qid(i.id))
    )
    lots = _lots(ctx)
    rows = []
    for part_id, n in ctx.rank.items():
        eligible = ctx.status[part_id]["status"] in ELIGIBLE
        name = f"{n:02d}-{part_id}.md"
        link = f"[{name}]({name})" if eligible else DASH
        result, confidence = _main_results(ctx, parts[part_id]) if eligible else (DASH, DASH)
        rows.append([f"{n:02d}", part_id, link, result, confidence, _cell(status_line(ctx.status[part_id]))])
    lot_rows = [[lot, part, ", ".join(ids) or DASH] for lot, part, ids in lots]
    in_a_lot = {q for _, _, ids in lots for q in ids}
    state = {True: QUESTION_STATE_VI["blocking"], False: QUESTION_STATE_VI["non_blocking"]}
    questions = [f"- **{i.id}** ({state[i.blocking]}): {_need_impact(i)[0]}" for i in open_items]
    questions += [MISSING_VI.format(id=q["id"]) for q in ctx.missing if q["id"] in in_a_lot]
    body = [
        [line.format(**numbers) for line in CONCLUSION_VI],
        _table(PARTS_HEADER_VI, rows),
        _table(LOTS_HEADER_VI, lot_rows),
        questions or [NONE_VI],
        [line.format(shown=ctx.shown) for line in SOURCES_VI],
    ]
    lines = [TITLE_VI.format(project_id=ctx.project_id)]
    for heading, section in zip(SECTIONS_VI, body, strict=True):
        lines += ["", f"## {heading}", "", *section]
    return "\n".join(lines) + "\n"


def run_plan(ctx: TakeoffContext, out: Path) -> int:
    """Write `out/00-plan.md` when its text differs and print the summary. Raises TakeoffError."""
    text = render_plan(ctx)
    path = out / PLAN_FILE
    written = not (path.is_file() and path.read_text(encoding="utf-8") == text)
    if written:
        out.mkdir(parents=True, exist_ok=True)
        write_text_atomic(path, text)
    doc = {"command": "plan", "out": str(out), "written": written, **_summary(ctx)}
    problems = validate("takeoff-output", doc)
    if problems:
        raise TakeoffError(EXIT_ENV, f"internal: the output does not match its schema: {problems[0].message}")
    print(json.dumps(doc, ensure_ascii=False, indent=2))
    return EXIT_OK
