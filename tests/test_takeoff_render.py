"""`harness takeoff render` (E8b): one Vietnamese take-off file per eligible part, every value from rows.

The work folder is `_part_fixtures.build_part_work` (parts B1-piles and B1-caps on one drawing; invented
values). Modules under test are imported inside the tests, so each fails on its own while they are missing.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

from _part_fixtures import (
    INPUT_PART,
    MANIFEST,
    PART,
    REL,
    build_part_work,
    entry_ids,
    put_manifest,
    write_values,
)
from tekla_harness.answers import record_answer
from tekla_harness.ask import ask_question
from tekla_harness.cli import main
from tekla_harness.schemas import validate

HEADINGS = [
    "## 1. Mô tả và phương pháp bóc",
    "## 2. Kết quả",
    "## 3. Ref đối soát",
    "## 4. Độ tin cậy",
    "## 5. Chưa rõ",
    "## 6. Trạng thái",
    "## 7. Tọa độ cho 3D",
]
EMPTY = "_(chưa viết)_"
PILES_ROW = {
    "row": "R001", "subject": "piles", "field": "count_plan", "value": "26", "file": REL,
    "sheet": "model#02", "state": "seen", "cites": {"questions": ["Q-005"]},
}  # fmt: skip


def caps_row(row_id: str, **fields: Any) -> dict[str, Any]:
    from _part_fixtures import row

    return row(row_id, **fields)


def receipts_of(work: Path, part: str, *kinds: str, stored: dict[str, str] | None = None) -> None:
    """Receipts of `kinds` in order on the part's current hash (a locked one stores `stored` inputs)."""
    from tekla_harness.part_receipts import part_hash

    manifest = json.loads((work / MANIFEST).read_text(encoding="utf-8"))
    current = part_hash(work, manifest, part)
    review = {"round": 1, "verdict": "pass", "file": f"parts/{part}/review/r.md", "sha256": "a" * 64}
    receipts = [
        {
            "n": n, "kind": kind, "part_hash": current, "at": "2026-01-01T00:00:00Z", "tool_version": "0.1.0",
            "review": review if kind == "reviewed" else None, "reason": None,
            "inputs": (stored or {}) if kind == "locked" else None,
        }
        for n, kind in enumerate(kinds, start=1)
    ]  # fmt: skip
    path = work / "parts" / part / "receipts.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"schema_version": "0.1", "part": part, "receipts": receipts}
    assert validate("part-receipts", doc) == []
    path.write_text(json.dumps(doc), encoding="utf-8")


def make_world(
    base: Path, rows: list[dict[str, Any]] | None = None, *, piles: str | None = "checked"
) -> Path:
    """B1-caps `checked` with `rows` (default one size row); B1-piles with `piles` receipt kind or none."""
    work = build_part_work(base)
    write_values(work, rows if rows is not None else [caps_row("R001")])
    write_values(work, [PILES_ROW], INPUT_PART)
    receipts_of(work, PART, "checked")
    if piles:
        receipts_of(work, INPUT_PART, piles)
    return work


def render(capsys: Any, work: Path, *flags: str) -> tuple[int, dict[str, Any] | None, str]:
    code = main(["takeoff", "render", str(work), *flags])
    cap = capsys.readouterr()
    return code, (json.loads(cap.out) if cap.out else None), cap.err


def out_dir(work: Path) -> Path:
    return work.parent / "takeoff"


def read(work: Path, name: str) -> str:
    return (out_dir(work) / name).read_text(encoding="utf-8")


def fill_slots(work: Path, name: str, method: str, reason: str) -> Path:
    """Replace the two placeholder slots of a rendered file by written text."""
    path = out_dir(work) / name
    text = path.read_text(encoding="utf-8")
    text = text.replace(f"<!-- ai:method -->\n{EMPTY}\n", f"<!-- ai:method -->\n{method}\n")
    path.write_text(
        text.replace(f"<!-- ai:reason -->\n{EMPTY}\n", f"<!-- ai:reason -->\n{reason}\n"), "utf-8"
    )
    return path


def section(text: str, n: int) -> str:
    start = text.index(HEADINGS[n - 1])
    end = text.index(HEADINGS[n]) if n < len(HEADINGS) else len(text)
    return text[start:end]


def test_only_eligible_parts_render_others_removed(tmp_path, capsys):
    work = make_world(tmp_path, piles=None)  # B1-piles has no receipt: reading
    old = out_dir(work) / "01-B1-piles.md"
    old.parent.mkdir(parents=True)
    old.write_text("old", encoding="utf-8")
    code, doc, _ = render(capsys, work, "--all")
    assert code == 0 and doc
    assert doc["written"] == ["02-B1-caps.md"] and doc["unchanged"] == []
    assert doc["removed"] == ["01-B1-piles.md"] and not old.exists()
    assert doc["skipped"] == [{"part": INPUT_PART, "status": "reading"}]
    assert sorted(p.name for p in out_dir(work).iterdir()) == ["02-B1-caps.md"]
    code, doc, err = render(capsys, work, "--part", INPUT_PART)
    assert code == 1 and "B1-piles" in err and doc and doc["written"] == []
    assert render(capsys, work, "--part", "scout")[0] == 1  # bookkeeping: never eligible


def test_file_number_from_manifest_rank(tmp_path, capsys):
    work = make_world(tmp_path, piles="checked")
    code, doc, _ = render(capsys, work, "--all")
    assert (
        code == 0 and doc and doc["written"] == ["01-B1-piles.md", "02-B1-caps.md"]
    )  # scout, all-assembly: none
    assert read(work, "02-B1-caps.md").startswith("# 02 — B1-caps\n")
    fill_slots(work, "02-B1-caps.md", "Đọc mặt bằng.", "Một tờ.")  # written slots must follow the new number
    manifest = json.loads((work / MANIFEST).read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in manifest["parts"]}
    by_id[PART]["order"], by_id[INPUT_PART]["order"] = 1, 2  # caps first now (no input order check here)
    by_id[PART].pop("inputs")
    put_manifest(work, manifest)
    receipts_of(work, PART, "checked")
    receipts_of(work, INPUT_PART, "checked")
    code, doc, _ = render(capsys, work, "--all")
    assert code == 0 and doc
    assert doc["written"] == ["01-B1-caps.md", "02-B1-piles.md"]
    assert sorted(doc["removed"]) == ["01-B1-piles.md", "02-B1-caps.md"]  # the old numbers go
    from tekla_harness.takeoff_render import parse_slots

    assert parse_slots(read(work, "01-B1-caps.md")) == {"method": "Đọc mặt bằng.", "reason": "Một tờ."}


def test_headings_and_tables_fixed(tmp_path, capsys):
    work = make_world(tmp_path)
    assert render(capsys, work, "--part", PART)[0] == 0
    text = read(work, "02-B1-caps.md")
    positions = [text.index(h) for h in HEADINGS]
    assert positions == sorted(positions)
    assert "| ký hiệu | kích thước | số lượng | trục |" in text
    assert "| ký hiệu | vật liệu | cao độ | finding | độ tin cậy |" in text
    assert text.count("<!-- ai:method -->") == 1 and text.count("<!-- /ai:reason -->") == 1
    assert "Tờ đã đọc" in section(text, 1) and "Lệnh đo lại" in section(text, 1)
    assert "dựng được" not in text and "chưa khóa (đã kiểm)" in section(text, 6)


def test_every_value_comes_from_rows(tmp_path, capsys):
    rows = [
        caps_row("R001"),
        caps_row("R002", value="1600x2400", cites={"findings": ["F-001"]}),  # a second size: joined with |
        caps_row("R003", field="thickness", value=None, state="asked", cites={"questions": ["Q-004"]}),
        caps_row("R004", field="axes", value="G 3-4", cites={"findings": ["F-002"]}),
        caps_row("R005", field="level_top", value="+0.200", cites={}),
    ]
    work = make_world(tmp_path, rows)
    assert render(capsys, work, "--part", PART)[0] == 0
    text = read(work, "02-B1-caps.md")
    s2, s3, s4 = section(text, 2), section(text, 3), section(text, 4)
    line = next(ln for ln in s2.splitlines() if ln.startswith("| K-1 ") and "1500x2400" in ln)
    assert "1500x2400 \\| 1600x2400" in line and "dày chờ trả lời (Q-004)" in line  # D1: the | is escaped
    assert " | 1600x2400" not in line.replace("\\|", "")
    assert "G 3-4" not in s2 and "trục G 3-4" in s3  # a typed axes row shows in section 3 only
    assert "đỉnh +0.200" in s2  # a level cell holds its field label
    assert (
        "F-001, F-002" in s2 and "Trung bình" in s2
    )  # sorted cited ids, the lowest confidence of F-001/F-002
    assert "5 giá trị: 0 Cao, 3 Trung bình, 0 Thấp, 2 chưa ghi nhận" in s4


def test_refs_sheet_number_title_view_quote(tmp_path, capsys):
    base = tmp_path
    work = build_part_work(base)
    ids = entry_ids(work)
    manifest = json.loads((work / MANIFEST).read_text(encoding="utf-8"))
    sheet = next(p for p in manifest["parts"] if p["id"] == PART)["sheets"][0]
    sheet["number_entry"], sheet["title_entry"] = ids["D400"], ids["K-2"]
    put_manifest(work, manifest)
    cites = {"findings": ["F-001"], "entries": [ids["1500x2400"]]}
    row = caps_row("R001", cites=cites, view={"heading_entry": ids["K-1"]})
    write_values(work, [row])
    write_values(work, [PILES_ROW], INPUT_PART)
    receipts_of(work, PART, "checked")
    assert render(capsys, work, "--part", PART)[0] == 0
    s3 = section(read(work, "02-B1-caps.md"), 3)
    want = f"D400 'K-2', hình 'K-1' · chữ '1500x2400' ({ids['1500x2400']}) · F-001, Q-003"
    assert want in s3
    assert "D400 'K-2' (mặt bằng)" in section(read(work, "02-B1-caps.md"), 1)


def test_sheet_without_number_entry(tmp_path, capsys):
    work = make_world(tmp_path)
    assert render(capsys, work, "--part", PART)[0] == 0
    text = read(work, "02-B1-caps.md")
    assert "tờ chưa có số hiệu (model#01)" in section(text, 3)
    assert "tờ chưa có số hiệu (model#01)" in section(text, 1)


def test_section5_order_and_answers(tmp_path, capsys):
    work = make_world(tmp_path)
    ask_question(
        work, code="reader_level_unclear", where="model#01 K-3", found="a value", text="Cao độ nào?",
        file=REL, sheet="model#01", blocking=False, part=PART,
    )  # fmt: skip
    record_answer(work, "Q-004", "ghi trên bản vẽ", "tester", role="engineer")
    receipts_of(work, PART, "checked")  # the part's question set is in its hash
    assert render(capsys, work, "--part", PART)[0] == 0
    s5 = section(read(work, "02-B1-caps.md"), 5)
    marks = [s5.index(f"**Q-00{n}**") for n in (3, 6, 4)]
    assert marks == sorted(marks)  # open blocking, open non-blocking, answered
    assert "(chặn)" in s5 and "(không chặn)" in s5 and "(đã trả lời)" in s5
    assert "ghi trên bản vẽ" in s5 and "Q-005" not in s5  # the answer text; a question of another part


def test_slots_kept_on_rerender(tmp_path, capsys):
    from tekla_harness.takeoff_render import parse_slots

    work = make_world(tmp_path)
    assert render(capsys, work, "--part", PART)[0] == 0
    path = out_dir(work) / "02-B1-caps.md"
    text = path.read_text(encoding="utf-8")
    assert parse_slots(text) == {"method": EMPTY, "reason": EMPTY}
    edited = text.replace(
        f"<!-- ai:method -->\n{EMPTY}\n", "<!-- ai:method -->\nĐọc mặt bằng.\n\nDòng hai.\n"
    )
    edited = edited.replace(f"<!-- ai:reason -->\n{EMPTY}\n", "<!-- ai:reason -->\nMột dòng.\n")
    path.write_text(edited, encoding="utf-8")
    assert parse_slots(edited) == {"method": "Đọc mặt bằng.\n\nDòng hai.", "reason": "Một dòng."}
    code, doc, _ = render(capsys, work, "--part", PART)
    assert code == 0 and doc and doc["unchanged"] == ["02-B1-caps.md"]
    assert path.read_text(encoding="utf-8") == edited


def test_unchanged_file_not_rewritten(tmp_path, capsys):
    work = make_world(tmp_path)
    assert render(capsys, work, "--all")[0] == 0
    files = sorted(out_dir(work).iterdir())
    for p in files:
        os.utime(p, ns=(10**9, 10**9))
    code, doc, _ = render(capsys, work, "--all")
    assert code == 0 and doc and doc["written"] == [] and doc["unchanged"] == [p.name for p in files]
    assert {p.stat().st_mtime_ns for p in files} == {10**9}  # not touched
    write_values(work, [caps_row("R001", value="1800x2400")])  # the values changed: only that file is written
    receipts_of(work, PART, "checked")
    code, doc, _ = render(capsys, work, "--all")
    assert doc and doc["written"] == ["02-B1-caps.md"] and doc["unchanged"] == ["01-B1-piles.md"]


def test_one_text_index_load_for_all_parts(tmp_path, capsys, monkeypatch):
    import tekla_harness.takeoff_render as takeoff_render

    work = build_part_work(tmp_path)
    ids = entry_ids(work)
    manifest = json.loads((work / MANIFEST).read_text(encoding="utf-8"))
    for p in manifest["parts"]:
        for s in p.get("sheets", []):
            s["number_entry"] = ids["D400"]  # every part reads the same drawing's text
    put_manifest(work, manifest)
    write_values(work, [caps_row("R001", cites={"findings": ["F-001"], "entries": [ids["K-1"]]})])
    write_values(work, [PILES_ROW], INPUT_PART)
    receipts_of(work, PART, "checked")
    receipts_of(work, INPUT_PART, "checked")
    calls: list[str] = []
    real = takeoff_render.load_file

    def spy(inv: Any, row: dict[str, Any], **kw: Any) -> Any:
        calls.append(row["path"])
        return real(inv, row, **kw)

    monkeypatch.setattr(takeoff_render, "load_file", spy)
    code, doc, _ = render(capsys, work, "--all")
    assert code == 0 and doc and len(doc["written"]) == 2
    assert calls == [REL]  # two parts, one drawing: one load


def test_render_locked_and_output_valid(tmp_path, capsys):
    from tekla_harness.part_receipts import part_hash

    work = make_world(tmp_path)
    receipts_of(work, INPUT_PART, "checked", "reviewed", "locked")
    manifest = json.loads((work / MANIFEST).read_text(encoding="utf-8"))
    stored = {INPUT_PART: part_hash(work, manifest, INPUT_PART)}
    receipts_of(work, PART, "checked", "reviewed", "locked", stored=stored)
    code, doc, _ = render(capsys, work, "--all")
    assert code == 0 and doc and validate("takeoff-output", doc) == []
    assert doc["out"] == str(out_dir(work)) and doc["skipped"] == []
    s6 = section(read(work, "02-B1-caps.md"), 6)
    assert "chưa khóa" not in s6 and "chờ trả lời (Q-003, Q-004)" in s6  # locked; two open blocking questions
    assert "chặn mọi lô (00-plan)" in s6  # intake's Q-001 blocks every part
    example = {
        "command": "render", "out": "/p/takeoff", "written": ["04-B1-caps.md"],
        "unchanged": ["02-all-notes-materials.md"], "removed": ["05-B1-stubs.md"],
        "skipped": [{"part": "B2-caps", "status": "reading"}],
    }  # fmt: skip
    assert validate("takeoff-output", example) == []
    for bad in ({**example, "command": "plan"}, {**example, "written": "x"}, {**example, "extra": 1}):
        assert validate("takeoff-output", bad)
    assert validate("takeoff-output", {k: v for k, v in example.items() if k != "removed"})


def put_contents(work: Path) -> str:
    """A saved contents document with two outlines: G-aaaaaaaaaa marked K-1 and G-bbbbbbbbbb unmarked."""
    root = Path(__file__).resolve().parents[1] / "schemas" / "examples" / "contents.example.json"
    doc = json.loads(root.read_text(encoding="utf-8"))
    base = doc["outlines"][0]
    doc["file"] = REL

    def outline(gid: str, marks: list[dict[str, Any]], label: str) -> dict[str, Any]:
        out = copy.deepcopy(base)
        out["id"], out["marks"] = gid, marks
        out["axes"] = [{**a, "label": label if a["family_id"] == "F001" else a["label"]} for a in out["axes"]]
        return out

    doc["outlines"] = [
        outline("G-aaaaaaaaaa", [{"text": "K-1", "entry_id": "T000123", "distance": 650.0}], "B"),
        outline("G-bbbbbbbbbb", [], "Q"),
    ]
    assert validate("contents", doc) == []
    source = "geometry/contents-model-01-11111111-22222222.json"
    (work / source).parent.mkdir(exist_ok=True)
    (work / source).write_text(json.dumps(doc), encoding="utf-8")
    return source


def test_regression_d2_uncited_outline_not_in_axes_cell(tmp_path, capsys):
    work = build_part_work(tmp_path)
    source = put_contents(work)
    geometry = {"source": source, "items": ["G-aaaaaaaaaa"]}
    write_values(work, [caps_row("R001", cites={"findings": ["F-001"], "geometry": geometry})])
    write_values(work, [PILES_ROW], INPUT_PART)
    receipts_of(work, PART, "checked")
    assert render(capsys, work, "--part", PART)[0] == 0
    text = read(work, "02-B1-caps.md")
    line = next(ln for ln in section(text, 2).splitlines() if ln.startswith("| K-1 ") and "1500x2400" in ln)
    assert "B -5000" in line and "Q -5000" not in text  # the unmarked, uncited outline is in no cell
    s7 = section(text, 7)
    assert source in s7 and "1 mục" in s7 and "G-aaaaaaaaaa" in s7
    assert "Tekla X/Y: có" in s7 and "Z: không có" in s7
    assert "harness contents" in section(text, 1)  # the command to measure it again


def test_locked_actions_and_render_usage(tmp_path, capsys):
    import tekla_harness.cli as cli

    assert cli.LOCKED_ACTIONS["takeoff"] == frozenset({"render", "plan"})  # check is read-only
    work = make_world(tmp_path)
    assert render(capsys, work)[0] == 2  # neither --part nor --all
    assert render(capsys, work, "--part", PART, "--all")[0] == 2


def test_hand_sum_bullet_from_terms(tmp_path, capsys):
    work = build_part_work(tmp_path)
    entry = entry_ids(work)["26"]
    row = caps_row("R001", field="count_plan", value="26", hand_sum={"terms": [{"entry": entry}]})
    write_values(work, [row])
    write_values(work, [PILES_ROW], INPUT_PART)
    receipts_of(work, PART, "checked")
    assert render(capsys, work, "--part", PART)[0] == 0
    s2 = section(read(work, "02-B1-caps.md"), 2)
    assert f"- K-1 — cộng tay: {entry} 26 = 26" in s2.split("**Cộng tay**")[1]


def test_damaged_slot_marker_refuses_rerender(tmp_path, capsys):
    """M2: a damaged marker (or a slot with no body line) is exit 1 and nothing is written for any part."""
    work = make_world(tmp_path)
    assert render(capsys, work, "--all")[0] == 0
    path = fill_slots(work, "02-B1-caps.md", "Đọc mặt bằng.", "Một tờ.")
    write_values(work, [PILES_ROW | {"value": "28"}], INPUT_PART)  # the piles file would be rewritten
    receipts_of(work, INPUT_PART, "checked")
    good = path.read_text(encoding="utf-8")
    damages = {
        "closing marker": good.replace("<!-- /ai:reason -->", "<!-- /ai:reason-->"),
        "no body line": good.replace("<!-- ai:method -->\nĐọc mặt bằng.\n", "<!-- ai:method -->\n"),
    }
    for kind, text in damages.items():
        path.write_text(text, encoding="utf-8")
        os.utime(path, ns=(10**9, 10**9))
        piles = out_dir(work) / "01-B1-piles.md"
        os.utime(piles, ns=(10**9, 10**9))
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in out_dir(work).iterdir()}
        code, doc, err = render(capsys, work, "--all")
        assert code == 1 and doc is None, kind
        assert "02-B1-caps.md" in err and "slot markers" in err and "harness takeoff check" in err, kind
        after = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in out_dir(work).iterdir()}
        assert after == before, kind  # the written text is still there, and no part file moved
        code, _, _ = render(capsys, work, "--part", PART)
        assert code == 1, kind
        assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in out_dir(work).iterdir()} == before


def test_damaged_old_number_file_refuses_rerender(tmp_path, capsys):
    work = make_world(tmp_path)
    assert render(capsys, work, "--all")[0] == 0
    path = fill_slots(work, "02-B1-caps.md", "Đọc mặt bằng.", "Một tờ.")
    old = path.with_name("05-B1-caps.md")  # the part's file under an old number; the target is absent
    path.rename(old)
    old.write_text(old.read_text(encoding="utf-8").replace("<!-- ai:method -->\n", ""), encoding="utf-8")
    code, doc, err = render(capsys, work, "--all")
    assert code == 1 and doc is None and "05-B1-caps.md" in err
    assert old.exists() and not path.exists()


def test_regression_m1_line_break_in_a_value_stays_in_its_cell(tmp_path, capsys, monkeypatch):
    import tekla_harness.takeoff_render as takeoff_render

    rows = [
        caps_row("R001"),
        caps_row("R002", field="material", value="B25\nM350", cites={}),
        caps_row("R003", field="other", value="a\nb", cites={}),
    ]
    work = make_world(tmp_path, rows)
    assert render(capsys, work, "--part", PART)[0] == 0
    text = read(work, "02-B1-caps.md")
    s2 = section(text, 2)
    lines = [ln for ln in s2.splitlines() if "B25" in ln]
    assert len(lines) == 1 and lines[0].startswith("| K-1 | vật liệu B25 M350 |"), lines
    assert not any(ln.strip() == "b" or ln.startswith("M350") for ln in text.splitlines())  # no loose line
    assert "- K-1 — khác a b" in s2.split("**Khác**")[1]
    s3 = section(text, 3)
    assert "- K-1 — vật liệu B25 M350" in s3
    # an entry text with line breaks and tabs is one line wherever it is quoted
    real = takeoff_render.index_by_id

    def multi_line(index: Any) -> dict[str, Any]:
        return {k: {**e, "display_text": "tờ\n  A\tB"} for k, e in real(index).items()}

    monkeypatch.setattr(takeoff_render, "index_by_id", multi_line)
    ctx = takeoff_render.TakeoffContext.load(work)
    assert ctx.text(REL, entry_ids(work)["K-1"]) == "tờ A B"


def test_regression_m2_hand_sum_term_with_a_space_in_its_mark(tmp_path, capsys, monkeypatch):
    import tekla_harness.takeoff_render as takeoff_render

    work = build_part_work(tmp_path)
    row = caps_row("R001", field="count_plan", value="3", hand_sum={"terms": [{"marks": "K 1"}]})
    write_values(work, [row])
    write_values(work, [PILES_ROW], INPUT_PART)
    receipts_of(work, PART, "checked")
    monkeypatch.setattr(takeoff_render, "hand_sum_addends", lambda *_: [("marks K 1", 3)])
    assert render(capsys, work, "--part", PART)[0] == 0
    s2 = section(read(work, "02-B1-caps.md"), 2)
    assert "- K-1 — cộng tay: K 1 3 = 3" in s2.split("**Cộng tay**")[1]


def test_regression_m3_unreadable_hand_sum_term_is_an_error(tmp_path, capsys):
    work = build_part_work(tmp_path)  # no marks.json: the term cannot be read
    row = caps_row("R001", field="count_plan", value="3", hand_sum={"terms": [{"marks": "K-2"}]})
    write_values(work, [row])
    write_values(work, [PILES_ROW], INPUT_PART)
    receipts_of(work, PART, "checked")
    code, doc, err = render(capsys, work, "--part", PART)
    assert code == 1 and doc is None
    assert "B1-caps R001" in err and "hand_sum term cannot be read" in err
    assert not out_dir(work).exists()


def put_cited_contents(
    work: Path, rows: list[dict[str, Any]] | None = None, items: list[str] | None = None
) -> str:
    """A part whose first row cites the items of a saved contents document (so § 7 prints its lines)."""
    source = put_contents(work)
    geometry = {"source": source, "items": items or ["G-aaaaaaaaaa"]}
    first = caps_row("R001", cites={"findings": ["F-001"], "geometry": geometry})
    write_values(work, [first, *(rows or [])])
    write_values(work, [PILES_ROW], INPUT_PART)
    receipts_of(work, PART, "checked")
    return source


def test_regression_m7_first_and_last_item_are_in_citing_order(tmp_path, capsys):
    work = build_part_work(tmp_path)
    put_cited_contents(work, items=["G-bbbbbbbbbb", "G-aaaaaaaaaa"])
    assert render(capsys, work, "--part", PART)[0] == 0
    assert "2 mục, đầu G-bbbbbbbbbb, cuối G-aaaaaaaaaa" in section(read(work, "02-B1-caps.md"), 7)


def test_regression_m9_tekla_x_y_reads_the_open_axis_and_missing_grid_questions(tmp_path, capsys):
    from tekla_harness.questions import GRID_MISSING_CODE, SYSTEM_AXIS_CODE
    from test_takeoff_plan import add_questions

    for code, number in ((SYSTEM_AXIS_CODE, 911), (GRID_MISSING_CODE, 912)):
        base = tmp_path / code
        work = build_part_work(base)
        put_cited_contents(work)
        assert "Tekla X/Y: có" in section(render_text(capsys, work), 7)
        add_questions(work, ("grid-system", code, number), file="other.dxf")  # another file's question
        receipts_of(work, PART, "checked")
        assert "Tekla X/Y: có" in section(render_text(capsys, work), 7), code  # the file filter
        add_questions(work, ("grid-system", code, number + 10), file=REL)
        receipts_of(work, PART, "checked")
        assert f"Tekla X/Y: chưa có (Q-{number + 10})" in section(render_text(capsys, work), 7), code


def render_text(capsys: Any, work: Path) -> str:
    assert render(capsys, work, "--part", PART)[0] == 0
    return read(work, "02-B1-caps.md")


def test_regression_m9_unclear_lists_a_question_only_the_manifest_row_lists(tmp_path, capsys):
    from test_takeoff_plan import add_questions, list_in_manifest

    work = make_world(tmp_path)
    add_questions(work, ("callouts", "callout_ambiguous", 901))
    list_in_manifest(work, PART, ["Q-901"])  # no part's question tag holds it
    receipts_of(work, PART, "checked")
    assert "**Q-901** (chặn)" in section(render_text(capsys, work), 5)


def test_regression_m9_z_line_reads_only_seen_rows(tmp_path, capsys):
    work = build_part_work(tmp_path)
    asked = caps_row("R002", field="level_top", value=None, state="asked", cites={"questions": ["Q-004"]})
    put_cited_contents(work, [asked])
    assert "- Z: không có (Q-004)" in section(render_text(capsys, work), 7)


def test_regression_m8_question_words_come_from_takeoff_cells():
    import inspect

    from tekla_harness import takeoff_cells as tc
    from tekla_harness import takeoff_plan, takeoff_render

    assert tc.QUESTION_STATE_VI == {
        "blocking": "chặn", "non_blocking": "không chặn", "answered": "đã trả lời", "closed": "đã đóng",
    }  # fmt: skip
    assert tc.NONE_VI == "không có"
    for module in (takeoff_render, takeoff_plan):
        source = inspect.getsource(module)
        for word in (*tc.QUESTION_STATE_VI.values(), tc.NONE_VI):
            assert f'"{word}"' not in source, (module.__name__, word)  # no retyped literal


def test_regression_m10_shown_path_is_relative_to_the_take_off_folder(tmp_path, monkeypatch):
    import os.path

    from tekla_harness.takeoff_render import shown_path

    work = (tmp_path / "work").resolve()
    assert shown_path(work, work.parent / "takeoff") == "../work"
    assert shown_path(work, work.parent / "a" / "b") == "../../work"
    assert shown_path(work, work) == "."

    def other_drive(*_: Any, **__: Any) -> str:
        raise ValueError("path is on mount 'D:', start on mount 'C:'")

    monkeypatch.setattr(os.path, "relpath", other_drive)
    assert shown_path(work, work.parent / "takeoff") == work.as_posix()
