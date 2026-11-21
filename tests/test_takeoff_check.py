"""`harness takeoff check` (E8d): the take-off on disk equals a fresh render and the AI slots hold no ids,
code, jargon or numbers of their own.

The work folder is `test_takeoff_render.make_world` (B1-piles and B1-caps `checked`; invented values),
rendered with `takeoff render --all` and `takeoff plan`, then edited by hand the way REVIEW-1 found
run 3's files edited.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from _part_fixtures import INPUT_PART
from tekla_harness.answers import record_answer
from tekla_harness.cli import main
from tekla_harness.schemas import validate
from test_takeoff_plan import PLAN, plan
from test_takeoff_render import EMPTY, caps_row, make_world, out_dir, render

CAPS, PILES = "02-B1-caps.md", "01-B1-piles.md"
RERUN = "rerun harness takeoff render"
RERUN_PLAN = "rerun harness takeoff plan"


def check(capsys: Any, work: Path, *flags: str) -> tuple[int, dict[str, Any] | None, str]:
    code = main(["takeoff", "check", str(work), *flags])
    cap = capsys.readouterr()
    return code, (json.loads(cap.out) if cap.out else None), cap.err


def rendered(tmp_path: Path, capsys: Any, **kwargs: Any) -> Path:
    """A work folder with `takeoff render --all` and `takeoff plan` done."""
    work = make_world(tmp_path, **kwargs)
    assert render(capsys, work, "--all")[0] == 0 and plan(capsys, work)[0] == 0
    return work


def fill(work: Path, name: str = CAPS, method: str = "Đọc mặt bằng.", reason: str = "Một tờ.") -> Path:
    """Replace the two slots of a part file by written text (the step after render)."""
    path = out_dir(work) / name
    text = path.read_text(encoding="utf-8")
    text = text.replace(f"<!-- ai:method -->\n{EMPTY}\n", f"<!-- ai:method -->\n{method}\n")
    path.write_text(
        text.replace(f"<!-- ai:reason -->\n{EMPTY}\n", f"<!-- ai:reason -->\n{reason}\n"), "utf-8"
    )
    return path


def written(tmp_path: Path, capsys: Any, **slots: str) -> Path:
    work = rendered(tmp_path, capsys)
    fill(work, PILES)
    fill(work, **slots)
    return work


def codes(doc: dict[str, Any] | None) -> list[tuple[str, str]]:
    assert doc is not None
    return [(p["code"], p["file"]) for p in doc["problems"]]


def edit(work: Path, name: str, old: str, new: str) -> None:
    path = out_dir(work) / name
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, old
    path.write_text(text.replace(old, new), encoding="utf-8")


def marker_line(work: Path, name: str, marker: str) -> int:
    lines = (out_dir(work) / name).read_text(encoding="utf-8").splitlines()
    return lines.index(marker) + 1


def snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in sorted(root.rglob("*")) if p.is_file()}


HAND_EDITS = {
    "c1_axes_typed_in_cell": (
        CAPS, "| K-1 | 1500x2400 | — | — |", "| K-1 | 1500x2400 | — | C, G tại 1 và 25 |"
    ),
    "m3_plan_value_without_ids": (PLAN, "| K-1 1500x2400 |", "| K-1 1800x2400 |"),
    "m4_beam_at_its_label": (PILES, "(model#02) · Q-005", "(model#02) · trục B · Q-005"),
    "m5_confidence_raised": (CAPS, "| F-001 | Trung bình |", "| F-001 | Cao |"),
    "non_blocking_in_status": (CAPS, "chờ trả lời (Q-003, Q-004)", "chờ trả lời (Q-002, Q-003, Q-004)"),
    "non_blocking_in_lot_cell": (PLAN, "| B1-caps | Q-003, Q-004 |", "| B1-caps | Q-002, Q-003, Q-004 |"),
    "lot_coverage_dropped": (PLAN, "| chặn mọi lô | — | Q-001 |", "| chặn mọi lô | — | — |"),
}  # fmt: skip


@pytest.mark.parametrize("case", list(HAND_EDITS))
def test_regression_review1_hand_edits(tmp_path, capsys, case):
    work = written(tmp_path, capsys)
    name, old, new = HAND_EDITS[case]
    edit(work, name, old, new)
    code, doc, _ = check(capsys, work)
    assert code == 1 and doc and doc["ok"] is False
    assert codes(doc) == [("generated_differs", name)]
    problem = doc["problems"][0]
    assert problem["line"] > 0
    assert (RERUN_PLAN if name == PLAN else RERUN) in problem["detail"]
    disk_line = (out_dir(work) / name).read_text(encoding="utf-8").splitlines()[problem["line"] - 1]
    assert f"found '{disk_line}'" in problem["detail"]  # the detail quotes the disk line and the fresh one
    assert "expected '" in problem["detail"]


def test_ok_rendered(tmp_path, capsys):
    work = written(
        tmp_path, capsys, method="Đọc mặt bằng 1500x2400.\n\nHai đoạn.", reason="Chỉ 1 tờ mặt bằng."
    )
    code, doc, err = check(capsys, work)
    assert (code, doc) == (0, {"command": "check", "ok": True, "files": 3, "problems": []}), err
    elsewhere = tmp_path / "elsewhere"
    assert main(["takeoff", "check", str(work), "--out", str(elsewhere)]) == 1  # no files there
    assert json.loads(capsys.readouterr().out)["files"] == 0
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    assert check(capsys, work, "--out", str(blocker))[0] == 2  # not a folder


def test_answer_after_render_needs_rerender(tmp_path, capsys):
    work = written(tmp_path, capsys)
    assert check(capsys, work)[0] == 0
    record_answer(work, "Q-004", "ghi trên bản vẽ", "tester", role="engineer")
    code, doc, _ = check(capsys, work)
    assert code == 1 and doc and (("generated_differs", CAPS) in codes(doc))  # § 5 now holds the answer
    assert all(c == "generated_differs" for c, _ in codes(doc))  # no hash moved, so no other problem
    assert (
        render(capsys, work, "--all")[0] == 0 and plan(capsys, work)[0] == 0
    )  # the rerender keeps the slots
    code, doc, _ = check(capsys, work)
    assert code == 0 and doc and doc["problems"] == []


def test_missing_and_unexpected_files(tmp_path, capsys):
    work = written(tmp_path, capsys)
    out = out_dir(work)
    (out / PLAN).unlink()
    (out / CAPS).rename(out / "05-B1-caps.md")  # a part file under the wrong number
    (out / "03-B1-old.md").write_text("old\n", encoding="utf-8")  # no such part
    (out / "notes.md").write_text("not a take-off file\n", encoding="utf-8")  # ignored
    code, doc, _ = check(capsys, work)
    assert code == 1 and doc and doc["files"] == 1  # only 01-B1-piles.md exists of the three expected
    assert sorted(codes(doc)) == sorted(
        [
            ("file_missing", PLAN),
            ("file_missing", CAPS),
            ("file_unexpected", "05-B1-caps.md"),
            ("file_unexpected", "03-B1-old.md"),
        ]
    )
    assert all(p["line"] is None for p in doc["problems"])
    (out / "05-B1-caps.md").unlink()
    (out / "03-B1-old.md").unlink()
    receipts = work / "parts" / INPUT_PART / "receipts.json"
    receipts.unlink()  # B1-piles is no longer eligible: its file is unexpected
    code, doc, _ = check(capsys, work)
    assert sorted(codes(doc)) == sorted(
        [("file_missing", PLAN), ("file_missing", CAPS), ("file_unexpected", PILES)]
    )
    for p in out.iterdir():
        p.unlink()
    out.rmdir()  # no folder at all: every expected file is missing, exit 1
    code, doc, _ = check(capsys, work)
    assert (
        code == 1 and doc and doc["files"] == 0 and codes(doc) == [("file_missing", n) for n in (PLAN, CAPS)]
    )


def test_slot_markers_and_empty_slot(tmp_path, capsys):
    work = rendered(tmp_path, capsys)  # the slots still hold the placeholder
    fill(work, PILES)
    code, doc, _ = check(capsys, work)
    assert code == 1 and doc and codes(doc) == [("ai_slot_empty", CAPS)] * 2
    body = [marker_line(work, CAPS, f"<!-- ai:{n} -->") + 1 for n in ("method", "reason")]
    assert [p["line"] for p in doc["problems"]] == body  # the body line of each slot
    fill(work)
    edit(work, CAPS, "<!-- ai:method -->\nĐọc mặt bằng.\n", "<!-- ai:method -->\n   \n")  # blank, not missing
    assert codes(check(capsys, work)[1]) == [("ai_slot_empty", CAPS)]
    edit(work, CAPS, "<!-- ai:method -->\n   \n", "<!-- ai:method -->\nĐọc mặt bằng.\n")
    base = (out_dir(work) / CAPS).read_text(encoding="utf-8")
    broken = {
        "missing": base.replace("<!-- /ai:method -->\n", ""),
        "doubled": base.replace("<!-- ai:method -->\n", "<!-- ai:method -->\n<!-- ai:method -->\n"),
        "out_of_order": base.replace("<!-- ai:method -->", "<!-- ai:TMP -->").replace(
            "<!-- ai:reason -->", "<!-- ai:method -->"
        ).replace("<!-- ai:TMP -->", "<!-- ai:reason -->"),
        "no_body_line": base.replace("<!-- ai:method -->\nĐọc mặt bằng.\n", "<!-- ai:method -->\n"),
    }  # fmt: skip
    for kind, text in broken.items():
        (out_dir(work) / CAPS).write_text(text, encoding="utf-8")
        code, doc, _ = check(capsys, work)
        # the markers are the only problem: no diff and no `ai_*` for a file whose slots cannot be read
        assert code == 1 and doc and {c for c, _ in codes(doc)} == {"slot_markers"}, kind
        assert {f for _, f in codes(doc)} == {CAPS}, kind


def test_ai_ids_code_and_jargon(tmp_path, capsys):
    ids = ["F-001", "Q-005", "T000471", "G-aaaaaaaaaa", "P000012", "R004", "V001", "model#02"]
    method = "\n".join(f"Dòng có {token} ở đây." for token in ids)
    reason = "\n".join(
        [
            "Lệnh `harness contents` đo lại.",
            "Chữ RR và Finding là từ nội bộ.",
            "Xem values.json và single_source.",
            "Từ founded, outlined, recentre không phải.",
            "Các findings và entries đã xem.",
            "Một dòng sạch.",
        ]
    )
    work = written(tmp_path, capsys, method=method, reason=reason)
    code, doc, _ = check(capsys, work)
    assert code == 1 and doc
    by = {
        c: [p for p in doc["problems"] if p["code"] == c]
        for c in ("ai_id", "ai_code", "ai_jargon", "ai_number")
    }
    assert {p["file"] for p in doc["problems"]} == {CAPS}
    method_start = marker_line(work, CAPS, "<!-- ai:method -->") + 1
    assert [p["line"] for p in by["ai_id"]] == list(
        range(method_start, method_start + len(ids))
    )  # one per line
    assert all(token in p["detail"] for token, p in zip(ids, by["ai_id"], strict=True))
    assert len(by["ai_code"]) == 1 and len(by["ai_jargon"]) == 3 and not by["ai_number"]
    lines = [p["line"] for p in by["ai_jargon"]]
    assert lines == [by["ai_code"][0]["line"] + 1, by["ai_code"][0]["line"] + 2, by["ai_code"][0]["line"] + 4]
    assert "findings" in by["ai_jargon"][2]["detail"] and "entries" in by["ai_jargon"][2]["detail"]  # m6
    assert "RR" in by["ai_jargon"][0]["detail"] and "Finding" in by["ai_jargon"][0]["detail"]
    assert "values.json" in by["ai_jargon"][1]["detail"] and "single_source" in by["ai_jargon"][1]["detail"]
    assert not {"founded", "outlined", "recentre"} & {w for p in by["ai_jargon"] for w in p["detail"].split()}


def test_regression_m5_channel_size_is_not_an_id(tmp_path, capsys):
    work = written(tmp_path, capsys, method="Thép U100 ở mép đài, thép U200 ở góc.", reason="Một tờ.")
    code, doc, _ = check(capsys, work)
    assert (code, doc and doc["problems"]) == (0, [])  # `U<n>` is a section name, no id of the harness


def test_mark_in_prose_is_not_an_id(tmp_path, capsys):
    work = make_world(tmp_path, [caps_row("R001", mark="R123")])  # a mark shaped like an id pattern
    assert render(capsys, work, "--all")[0] == 0 and plan(capsys, work)[0] == 0
    fill(work, PILES)
    fill(work, method="Đài R123 đặt trên cọc, đài G-1 cũng vậy.", reason="Đài R123 một tờ.")
    code, doc, _ = check(capsys, work)
    assert (code, doc and doc["problems"]) == (0, [])
    edit(work, CAPS, "Đài R123 đặt trên cọc, đài G-1 cũng vậy.", "Đài R124 đặt trên cọc.")
    assert codes(check(capsys, work)[1]) == [("ai_id", CAPS)]


def test_regression_m2_number_typed_in_slot(tmp_path, capsys):
    method = "Đọc mặt bằng, kích thước 1500x2400 ghi ở bảng.\nĐáy đài ở cao độ -2.750."
    work = written(tmp_path, capsys, method=method, reason="Gồm 4 loại, dài 50 m, ghi F-001.")
    code, doc, _ = check(capsys, work)
    assert code == 1 and doc
    numbers = [p for p in doc["problems"] if p["code"] == "ai_number"]
    assert [p["detail"] for p in numbers] == [  # M1: -2.750 is a number too (its absolute value is shown)
        "2.75 is in no generated line of this file",
        "4 is in no generated line of this file",
        "50 is in no generated line of this file",
    ]
    assert len({p["line"] for p in numbers[1:]}) == 1 and numbers[0]["line"] < numbers[1]["line"]
    assert numbers[0]["file"] == CAPS
    assert {p["code"] for p in doc["problems"]} == {"ai_number", "ai_id"}  # F-001 is an id, not a number too


def test_regression_m1_signed_numbers_compare_by_absolute_value(tmp_path, capsys):
    rows = [caps_row("R001"), caps_row("R002", field="level_top", value="-1.200", cites={})]
    work = rendered(tmp_path, capsys, rows=rows)
    fill(work, PILES)
    fill(work, method="Đỉnh đài ở -1.200 (xem bảng).", reason="Đáy cách đỉnh 1.200, cao độ (-1.200) ghi rõ.")
    code, doc, err = check(capsys, work)
    assert (code, doc and doc["problems"]) == (0, []), err  # -1.200 is shown; 1.2 is its absolute value
    fill_again = out_dir(work) / CAPS
    text = fill_again.read_text(encoding="utf-8").replace("(xem bảng)", "(sâu -3.4 m, +5)")
    fill_again.write_text(text, encoding="utf-8")
    code, doc, _ = check(capsys, work)
    assert code == 1 and doc
    assert [p["detail"] for p in doc["problems"]] == [
        "3.4 is in no generated line of this file",
        "5 is in no generated line of this file",
    ]


def test_regression_m10_text_does_not_depend_on_how_the_work_folder_is_typed(tmp_path, capsys, monkeypatch):
    """D2: the work folder is written as its path from the take-off folder, whatever the spelling or cwd."""
    work = make_world(tmp_path)
    out = out_dir(work)
    spellings = [(tmp_path, str(work)), (tmp_path, "work"), (work, "."), (out, "../work"), (out, str(work))]

    def run(*argv: str) -> dict[str, Any]:
        assert main(["takeoff", *argv]) == 0
        return json.loads(capsys.readouterr().out)

    monkeypatch.chdir(tmp_path)
    run("render", str(work), "--all")
    run("plan", str(work))
    fill(work, PILES)
    fill(work)
    first = {p.name: p.read_bytes() for p in out.iterdir()}
    assert "harness status ../work" in first[PLAN].decode("utf-8")
    assert not any(str(tmp_path).encode() in data for data in first.values())  # no absolute path in any file
    for cwd, spelling in spellings:
        monkeypatch.chdir(cwd)
        assert run("render", spelling, "--all")["written"] == [], (cwd, spelling)  # the same bytes
        assert run("plan", spelling)["written"] is False, (cwd, spelling)
        assert {p.name: p.read_bytes() for p in out.iterdir()} == first, (cwd, spelling)
        code = main(["takeoff", "check", spelling])
        assert (code, json.loads(capsys.readouterr().out)["problems"]) == (0, []), (cwd, spelling)
    # another take-off folder: another relative path, still no absolute one
    elsewhere = tmp_path / "x" / "y"
    monkeypatch.chdir(tmp_path)
    run("plan", str(work), "--out", str(elsewhere))
    assert "harness status ../../work" in (elsewhere / PLAN).read_text(encoding="utf-8")


def test_check_writes_nothing(tmp_path, capsys):
    work = written(tmp_path, capsys)
    edit(work, CAPS, "| F-001 | Trung bình |", "| F-001 | Cao |")
    (out_dir(work) / "03-B1-old.md").write_text("old\n", encoding="utf-8")
    before = snapshot(tmp_path)
    assert check(capsys, work)[0] == 1
    assert snapshot(tmp_path) == before  # not the text, not the mtime, not a new file
    (out_dir(work) / PLAN).unlink()
    before = snapshot(tmp_path)
    assert check(capsys, work, "--out", str(tmp_path / "nowhere"))[0] == 1
    assert check(capsys, work)[0] == 1
    assert snapshot(tmp_path) == before and not (tmp_path / "nowhere").exists()


def test_output_valid(tmp_path, capsys):
    work = written(tmp_path, capsys, reason="Tờ 4 loại.")
    edit(work, PILES, "| piles | — | mặt bằng 26 | — |", "| piles | — | mặt bằng 26 | B |")
    code, doc, _ = check(capsys, work)
    assert code == 1 and doc and validate("takeoff-output", doc) == []
    assert set(doc) == {"command", "ok", "files", "problems"} and doc["command"] == "check"
    assert all(set(p) == {"code", "file", "line", "detail"} for p in doc["problems"])
    found = {"code": "ai_number", "file": "04-B1-caps.md", "line": 14}
    example = {
        "command": "check",
        "ok": False,
        "files": 8,
        "problems": [{**found, "detail": "2600 is in no generated line of this file"}],
    }
    assert validate("takeoff-output", example) == []
    file_level = {"code": "file_missing", "file": "00-plan.md", "line": None, "detail": "no file"}
    assert validate("takeoff-output", {**example, "problems": [file_level]}) == []
    for bad in (
        {**example, "ok": "no"},
        {**example, "extra": 1},
        {**example, "problems": [{**file_level, "code": "other"}]},
        {**example, "problems": [{"code": "ai_id", "file": "x.md", "detail": "d"}]},  # no `line` key
    ):
        assert validate("takeoff-output", bad)
