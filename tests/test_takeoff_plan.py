"""`harness takeoff plan` (E8c): `00-plan.md`, the parts in rank order and the lots with what blocks them.

The work folder is `test_takeoff_render.make_world` (B1-piles and B1-caps `checked`; invented values).
Q-001 is the project-wide units question; Q-003 and Q-004 block B1-caps, Q-005 blocks B1-piles;
Q-002 is non-blocking.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from _part_fixtures import INPUT_PART, MANIFEST, PART, PROJECT, put_manifest
from tekla_harness.ask import ask_question
from tekla_harness.cli import main
from tekla_harness.questions import questions_document
from tekla_harness.schemas import validate
from tekla_harness.takeoff_cells import BLOCKS_EVERY_LOT_VI, status_line
from tekla_harness.takeoff_render import TakeoffContext
from test_takeoff_render import make_world, out_dir, receipts_of

PLAN = "00-plan.md"
DASH = "—"


def plan(capsys: Any, work: Path, *flags: str) -> tuple[int, dict[str, Any] | None, str]:
    code = main(["takeoff", "plan", str(work), *flags])
    cap = capsys.readouterr()
    return code, (json.loads(cap.out) if cap.out else None), cap.err


def read_plan(work: Path) -> str:
    return (out_dir(work) / PLAN).read_text(encoding="utf-8")


def section(text: str, name: str) -> list[str]:
    lines = text.splitlines()
    start = lines.index(f"## {name}") + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    return [ln for ln in lines[start:end] if ln]


def table(text: str, name: str) -> list[list[str]]:
    """The body rows of the table of a section, each as its cells."""
    rows = [ln for ln in section(text, name) if ln.startswith("|")][2:]
    return [[c.strip() for c in ln.strip("|").split(" | ")] for ln in rows]


def add_questions(
    work: Path, *entries: tuple[str, str, int], documents: bool = True, file: str = "set.dxf"
) -> None:
    """Open blocking questions (producer, code, number) of the callouts, marks or grid-system step that no
    part tags, about `file`; `documents=False`: in the registry only (no question document carries them)."""
    path = work / "question-registry.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    for producer, code, number in entries:
        key = f"{number:016x}"
        registry["questions"][key] = {
            "id": f"Q-{number}", "code": code, "file": file, "producer": producer, "status": "open",
            "first_seen_run": 1, "last_seen_run": 1, "blocking": True, "file_sha256": None,
        }  # fmt: skip
        if not documents:
            continue
        document = work / f"{producer}-questions.json"
        doc = (
            json.loads(document.read_text(encoding="utf-8"))
            if document.is_file()
            else questions_document(registry["project_id"], [])
        )
        doc["questions"].append(
            {
                "id": f"Q-{number}", "key": key, "code": code, "blocking": True, "file": file,
                "message": "Chưa rõ ký hiệu.", "count": 1, "truncated": False,
                "refs": [{"file": file, "where": "model#01", "found": "a value"}], "answer": None,
            }
        )  # fmt: skip
        document.write_text(json.dumps(doc), encoding="utf-8")
    registry["next_id"] = max(registry["next_id"], *(n + 1 for _, _, n in entries))
    path.write_text(json.dumps(registry), encoding="utf-8")


def list_in_manifest(work: Path, part: str, ids: list[str]) -> None:
    manifest = json.loads((work / MANIFEST).read_text(encoding="utf-8"))
    next(p for p in manifest["parts"] if p["id"] == part)["producer_questions"] = ids
    put_manifest(work, manifest)


def test_every_part_listed_with_status(tmp_path, capsys):
    work = make_world(tmp_path)
    code, doc, _ = plan(capsys, work)
    assert code == 0 and doc and doc["written"] is True
    text = read_plan(work)
    assert text.startswith(f"# 00 — Kế hoạch bóc bản vẽ — {PROJECT}\n")
    ctx = TakeoffContext.load(work)
    rows = table(text, "Thứ tự các phần")
    assert [r[:2] for r in rows] == [["01", INPUT_PART], ["02", PART]]  # no scout, no all-assembly
    assert [r[5] for r in rows] == [status_line(ctx.status[i]) for i in (INPUT_PART, PART)]
    assert "chưa khóa (đã kiểm)" in rows[1][5] and "chờ trả lời (Q-003, Q-004)" in rows[1][5]
    assert rows[1][3] == "K-1 1500x2400" and rows[1][4] == "Trung bình"  # main result and confidence
    assert section(text, "Kết luận")[0] == "- 2 phần, 2 phần đã có file bóc tách, 0 phần sẵn sàng để dựng."
    assert f"4 câu hỏi chặn còn mở, trong đó 1 câu {BLOCKS_EVERY_LOT_VI}" in section(text, "Kết luận")[1]
    assert f"`harness status ../{work.name}`" in "\n".join(section(text, "Nguồn"))  # relative to takeoff/


def test_links_only_eligible_files(tmp_path, capsys):
    work = make_world(tmp_path, piles=None)  # B1-piles has no receipt: reading
    assert plan(capsys, work)[0] == 0
    rows = {r[1]: r for r in table(read_plan(work), "Thứ tự các phần")}
    assert rows[PART][2] == "[02-B1-caps.md](02-B1-caps.md)"
    assert rows[INPUT_PART][2] == DASH and rows[INPUT_PART][3] == DASH  # reading: no file, no result
    assert rows[INPUT_PART][5].startswith("chưa khóa (đang đọc)")  # needs STATUS_VI["reading"]
    assert sorted(p.name for p in out_dir(work).iterdir()) == [PLAN]  # plan never writes a part file


def test_rerun_unchanged(tmp_path, capsys):
    work = make_world(tmp_path)
    assert plan(capsys, work)[0] == 0
    path = out_dir(work) / PLAN
    os.utime(path, ns=(10**9, 10**9))
    code, doc, _ = plan(capsys, work)
    assert code == 0 and doc and doc["written"] is False
    assert path.stat().st_mtime_ns == 10**9  # not touched
    elsewhere = tmp_path / "elsewhere"
    code, doc, _ = plan(capsys, work, "--out", str(elsewhere))
    assert code == 0 and doc and doc["written"] is True and doc["out"] == str(elsewhere)
    assert (elsewhere / PLAN).read_text(encoding="utf-8") == path.read_text(encoding="utf-8")
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    assert plan(capsys, work, "--out", str(blocker))[0] == 2  # not a folder


def test_regression_lot_cells_only_open_blocking(tmp_path, capsys):
    work = make_world(tmp_path)
    ask_question(
        work, code="reader_level_unclear", where="model#01 K-3", found="a value", text="Cao độ nào?",
        file=None, sheet=None, blocking=False, part=PART,
    )  # fmt: skip
    receipts_of(work, PART, "checked")  # the part's question set is in its hash
    assert plan(capsys, work)[0] == 0
    text = read_plan(work)
    lots = {r[0]: r[2] for r in table(text, "Các lô")}
    assert lots["L02"] == "Q-003, Q-004" and lots["L01"] == "Q-005"  # Q-006 (non-blocking) is in no lot
    assert "Q-006" not in "\n".join(section(text, "Các lô"))
    assert any(ln.startswith("- **Q-006** (không chặn)") for ln in section(text, "Câu hỏi mở"))


def test_regression_lot_coverage_every_open_blocking_question(tmp_path, capsys):
    work = make_world(tmp_path)
    add_questions(work, ("callouts", "callout_ambiguous", 901), ("marks", "mark_unparsed", 902))
    list_in_manifest(work, PART, ["Q-901"])  # a part lists the callouts question; no part lists Q-902
    held = dict(code="reader_size_unclear", where="model#01 K-3", found="a value", text="Kích thước nào?")
    bookkeeping = ask_question(work, **held, blocking=True, part="scout")["id"]  # no L<nn> row has it
    receipts_of(work, PART, "checked")
    receipts_of(work, INPUT_PART, "checked")
    code, doc, _ = plan(capsys, work)
    assert code == 0 and doc
    text = read_plan(work)
    rows = table(text, "Các lô")
    open_blocking = [ln.split("**")[1] for ln in section(text, "Câu hỏi mở") if "(chặn)" in ln]
    assert {"Q-901", "Q-902", bookkeeping} <= set(open_blocking)
    covered = {q for r in rows for q in r[2].split(", ")}
    assert set(open_blocking) <= covered  # no gap: each open blocking question is in a row
    assert rows[0] == [BLOCKS_EVERY_LOT_VI, DASH, "Q-001, Q-902"]  # D1: project_blocking_ids, no union
    assert [r[:2] for r in rows[1:]] == [["L01", INPUT_PART], ["L02", PART], [DASH, "scout"]]
    assert rows[2][2] == "Q-003, Q-004, Q-901" and rows[3][2] == bookkeeping  # the bookkeeping part's own row
    assert "all-assembly" not in "\n".join(section(text, "Các lô"))  # a part with no open id has no row
    assert bookkeeping not in rows[0][2]
    assert doc["project_blocking"] == 2  # the ids of the project row


def test_regression_open_blocking_id_in_no_row_is_an_internal_error(tmp_path, capsys, monkeypatch):
    import tekla_harness.takeoff_render as takeoff_render
    from tekla_harness.takeoff_plan import render_plan
    from tekla_harness.takeoff_render import TakeoffError

    work = make_world(tmp_path)
    ctx = TakeoffContext.load(work)
    ctx.project_blocking_ids = []  # Q-001 is open and blocking, and no other row holds it
    with pytest.raises(TakeoffError) as caught:
        render_plan(ctx)
    assert caught.value.exit_code == 3 and "internal" in str(caught.value) and "Q-001" in str(caught.value)
    real = takeoff_render.build_status

    def without_project_row(path: Path, **kwargs: Any) -> dict[str, Any]:
        return {**real(path, **kwargs), "project_blocking_ids": []}

    monkeypatch.setattr(takeoff_render, "build_status", without_project_row)
    code, doc, err = plan(capsys, work)
    assert code == 3 and doc is None and "internal" in err
    assert not (out_dir(work) / PLAN).exists()  # nothing written


def test_project_row_is_project_blocking_ids(tmp_path, capsys):
    work = make_world(tmp_path)
    add_questions(work, ("marks", "mark_unparsed", 902))
    add_questions(work, ("callouts", "callout_ambiguous", 903), documents=False)  # no document: not an item
    receipts_of(work, PART, "checked")
    receipts_of(work, INPUT_PART, "checked")
    code, doc, _ = plan(capsys, work)
    assert code == 0 and doc
    ctx = TakeoffContext.load(work)
    assert ctx.project_id == PROJECT and ctx.project_blocking_ids == ["Q-001", "Q-902", "Q-903"]
    text = read_plan(work)
    rows = table(text, "Các lô")
    assert rows[0] == [BLOCKS_EVERY_LOT_VI, DASH, ", ".join(ctx.project_blocking_ids)]  # first row
    assert [r[0] for r in rows[1:]] == ["L01", "L02"]
    assert all(set(c) <= set("Q-0123456789, —") for r in rows for c in (r[2],))  # only ids or the dash
    # m4: Q-903 is in the registry but in no question document: listed once, and counted
    open_lines = section(text, "Câu hỏi mở")
    assert any(ln.startswith("- **Q-903** (chặn): chưa có trong file câu hỏi nào") for ln in open_lines)
    assert f"6 câu hỏi chặn còn mở, trong đó 3 câu {BLOCKS_EVERY_LOT_VI}" in section(text, "Kết luận")[1]
    assert doc["blocking_open"] == 6 and doc["project_blocking"] == 3


def test_open_questions_blocking_first(tmp_path, capsys):
    work = make_world(tmp_path)
    assert plan(capsys, work)[0] == 0
    lines = section(read_plan(work), "Câu hỏi mở")
    ids = [ln.split("**")[1] for ln in lines]
    assert ids == ["Q-001", "Q-003", "Q-004", "Q-005", "Q-002"]  # blocking by id, then Q-002
    assert [ln.split("(")[1].split(")")[0] for ln in lines] == ["chặn"] * 4 + ["không chặn"]
    assert all(ln.split("): ", 1)[1] for ln in lines)  # each has its need text


def test_output_validates(tmp_path, capsys):
    work = make_world(tmp_path)
    code, doc, _ = plan(capsys, work)
    assert code == 0 and doc and validate("takeoff-output", doc) == []
    assert doc == {
        "command": "plan", "out": str(out_dir(work)), "written": True, "parts": 2, "rendered": 2,
        "ready": 0, "blocking_open": 4, "project_blocking": 1,
    }  # fmt: skip
    example = {
        "command": "plan", "out": "/p/takeoff", "written": True, "parts": 9, "rendered": 7, "ready": 2,
        "blocking_open": 14, "project_blocking": 5,
    }  # fmt: skip
    assert validate("takeoff-output", example) == []
    for bad in ({**example, "written": "x"}, {**example, "extra": 1}, {**example, "parts": -1}):
        assert validate("takeoff-output", bad)
    assert validate("takeoff-output", {k: v for k, v in example.items() if k != "ready"})
