"""harness extract-sheets / extract-grids / extract-levels / read-structure.

Fixtures are programmatic: `_dxf_fixtures.build_set` is the drawing, `run_intake` produces the work
folder that `read-structure` consumes. A fake `dwg2dxf` (test_intake) covers the converted-DXF path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from _dxf_fixtures import build_set
from tekla_harness import structure as structure_mod
from tekla_harness.cli import main
from tekla_harness.intake import run_intake
from tekla_harness.schemas import validate
from tekla_harness.structure import MAX_STRUCTURE_REFS, read_structure
from test_intake import fake_dwg2dxf, tree

DWG_BYTES = b"AC1032" + b"\x00" * 64


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def run_cli(capsys, *argv: str) -> tuple[int, dict | None, str]:
    """(exit code, stdout JSON or None, stderr)."""
    code = main(list(argv))
    cap = capsys.readouterr()
    return code, (json.loads(cap.out) if cap.out.strip() else None), cap.err


@pytest.fixture
def drawing(tmp_path) -> Path:
    return build_set(tmp_path, "drawing.dxf")


@pytest.fixture
def text_index(drawing, tmp_path, capsys) -> Path:
    out = tmp_path / "text.json"
    assert main(["extract-text", str(drawing), "--out", str(out)]) == 0
    capsys.readouterr()
    return out


@pytest.fixture
def sheets(drawing, text_index, tmp_path, capsys) -> Path:
    out = tmp_path / "sheets.json"
    assert main(["extract-sheets", str(drawing), "--text-index", str(text_index), "--out", str(out)]) == 0
    capsys.readouterr()
    return out


# --- extract-sheets ------------------------------------------------------------------------------


def test_extract_sheets_happy(capsys, drawing, text_index, tmp_path):
    out = tmp_path / "sub" / "sheets.json"
    code, summary, err = run_cli(
        capsys, "extract-sheets", str(drawing), "--text-index", str(text_index), "--out", str(out)
    )
    assert code == 0 and err == ""
    doc = load(out)
    assert validate("sheets", doc) == []
    assert [s["sheet_id"] for s in doc["sheets"]] == ["model#01", "model#02", "Plot#01"]
    assert summary is not None
    assert summary["out"] == str(out) and summary["file"] == str(drawing)
    assert summary["sheets"]["count"] == 3
    assert summary["sheets"]["sheet_numbers"] == {"found": 3, "missing": 0, "by_confidence": {"medium": 3}}
    assert summary["questions"]["total"] == len(doc["questions"])
    assert summary["questions"]["blocking"] == sum(1 for q in doc["questions"] if q["blocking"])
    assert summary["warnings"] == doc["warnings"]
    assert "title_block" not in json.dumps(summary)  # small: the full result is only in --out


def test_extract_sheets_is_deterministic(capsys, drawing, text_index, tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    for out in (a, b):
        assert main(["extract-sheets", str(drawing), "--text-index", str(text_index), "--out", str(out)]) == 0
    assert a.read_bytes() == b.read_bytes()


def test_sheets_dxf_sha_mismatch_exit_1_and_nothing_written(capsys, text_index, tmp_path):
    other = build_set(tmp_path, "other.dxf", sheet2_number="S-999")
    out = tmp_path / "sheets.json"
    code, summary, err = run_cli(
        capsys, "extract-sheets", str(other), "--text-index", str(text_index), "--out", str(out)
    )
    assert code == 1 and summary is None
    assert "sha256" in err and "does not match" in err
    assert not out.exists()


def test_sheets_missing_dxf_is_usage_error(capsys, text_index, tmp_path):
    code, _, err = run_cli(
        capsys,
        "extract-sheets",
        str(tmp_path / "nope.dxf"),
        "--text-index",
        str(text_index),
        "--out",
        str(tmp_path / "o.json"),
    )
    assert code == 2 and "not a file" in err


def test_sheets_missing_text_index_is_usage_error(capsys, drawing, tmp_path):
    code, _, err = run_cli(
        capsys,
        "extract-sheets",
        str(drawing),
        "--text-index",
        str(tmp_path / "nope.json"),
        "--out",
        str(tmp_path / "o.json"),
    )
    assert code == 2 and "not a file" in err


def test_sheets_text_index_must_validate(capsys, drawing, text_index, tmp_path):
    bad = load(text_index)
    del bad["entries"]
    bad_path = tmp_path / "bad-text.json"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    out = tmp_path / "o.json"
    code, _, err = run_cli(
        capsys, "extract-sheets", str(drawing), "--text-index", str(bad_path), "--out", str(out)
    )
    assert code == 1 and "text index" in err and not out.exists()


def test_sheets_text_index_not_json(capsys, drawing, tmp_path):
    bad_path = tmp_path / "bad-text.json"
    bad_path.write_text("{not json", encoding="utf-8")
    code, _, err = run_cli(
        capsys,
        "extract-sheets",
        str(drawing),
        "--text-index",
        str(bad_path),
        "--out",
        str(tmp_path / "o.json"),
    )
    assert code == 1 and "not valid JSON" in err


def test_unreadable_text_index_is_exit_1(capsys, drawing, text_index, tmp_path):
    unreadable = load(text_index)
    unreadable.pop("entries")
    unreadable["status"] = "unreadable"
    unreadable["error"] = "boom"
    unreadable.pop("summary", None)
    p = tmp_path / "unreadable.json"
    p.write_text(json.dumps(unreadable), encoding="utf-8")
    code, _, err = run_cli(
        capsys,
        "extract-sheets",
        str(drawing),
        "--text-index",
        str(p),
        "--out",
        str(tmp_path / "o.json"),
    )
    assert code == 1 and "unreadable" in err


def test_sheets_output_is_validated_before_writing(monkeypatch, capsys, drawing, text_index, tmp_path):
    monkeypatch.setattr(structure_mod, "extract_sheets", lambda *a, **k: {"schema_version": "0.1"})
    out = tmp_path / "o.json"
    code, _, err = run_cli(
        capsys, "extract-sheets", str(drawing), "--text-index", str(text_index), "--out", str(out)
    )
    assert code == 1 and "sheets" in err and "invalid" in err and not out.exists()


# --- extract-grids / extract-levels --------------------------------------------------------------


def test_extract_grids_happy(capsys, drawing, text_index, sheets, tmp_path):
    out = tmp_path / "grids.json"
    code, summary, err = run_cli(
        capsys,
        "extract-grids",
        str(drawing),
        "--text-index",
        str(text_index),
        "--sheets",
        str(sheets),
        "--out",
        str(out),
    )
    assert code == 0 and err == ""
    doc = load(out)
    assert validate("grids", doc) == []
    assert summary is not None
    assert summary["out"] == str(out)
    grids = summary["grids"]
    assert grids["groups"] == len(doc["groups"])
    assert grids["families_total"] == doc["summary"]["families"] == len(grids["families"])
    coords = {f["coordinates"] for f in grids["families"]}
    assert "0 3*6000" in coords and "0 5000 4500" in coords
    first = next(f for f in grids["families"] if f["coordinates"] == "0 3*6000")
    assert first["labels"] == "1 2 3 4" and first["sheet"] == "model#01"
    assert summary["questions"]["blocking"] >= 2  # grid_family_axis_assignment, grid_gate1_confirmation


def test_extract_levels_happy(capsys, drawing, text_index, sheets, tmp_path):
    out = tmp_path / "levels.json"
    code, summary, err = run_cli(
        capsys,
        "extract-levels",
        str(drawing),
        "--text-index",
        str(text_index),
        "--sheets",
        str(sheets),
        "--out",
        str(out),
    )
    assert code == 0 and err == ""
    doc = load(out)
    assert validate("levels", doc) == []
    assert summary is not None
    levels = summary["levels"]
    assert levels["levels_total"] == len(doc["levels"]) and levels["candidates"] == len(doc["candidates"])
    by_text = {lv["value_text"]: lv for lv in levels["levels"]}
    assert by_text["+3.600"]["count"] >= 2 and by_text["+3.600"]["value"] == 3.6
    assert summary["questions"]["blocking"] >= 1  # level_finished_vs_structural


@pytest.mark.parametrize("command", ["extract-grids", "extract-levels"])
def test_sheets_from_another_file_exit_1(capsys, command, drawing, text_index, tmp_path):
    other = build_set(tmp_path, "other.dxf", sheet2_number="S-999")
    other_text = tmp_path / "other-text.json"
    assert main(["extract-text", str(other), "--out", str(other_text)]) == 0
    other_sheets = tmp_path / "other-sheets.json"
    assert (
        main(["extract-sheets", str(other), "--text-index", str(other_text), "--out", str(other_sheets)]) == 0
    )
    capsys.readouterr()
    out = tmp_path / "o.json"
    code, summary, err = run_cli(
        capsys,
        command,
        str(drawing),
        "--text-index",
        str(text_index),
        "--sheets",
        str(other_sheets),
        "--out",
        str(out),
    )
    assert code == 1 and summary is None
    assert "sheets" in err and "sha256" in err
    assert not out.exists()


@pytest.mark.parametrize("command", ["extract-grids", "extract-levels"])
def test_text_index_from_another_file_exit_1(capsys, command, text_index, sheets, tmp_path):
    other = build_set(tmp_path, "other.dxf", sheet2_number="S-999")
    code, _, err = run_cli(
        capsys,
        command,
        str(other),
        "--text-index",
        str(text_index),
        "--sheets",
        str(sheets),
        "--out",
        str(tmp_path / "o.json"),
    )
    assert code == 1 and "does not match" in err


@pytest.mark.parametrize("command", ["extract-grids", "extract-levels"])
def test_invalid_sheets_document_exit_1(capsys, command, drawing, text_index, sheets, tmp_path):
    bad = load(sheets)
    del bad["sheets"]
    bad_path = tmp_path / "bad-sheets.json"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    code, _, err = run_cli(
        capsys,
        command,
        str(drawing),
        "--text-index",
        str(text_index),
        "--sheets",
        str(bad_path),
        "--out",
        str(tmp_path / "o.json"),
    )
    assert code == 1 and "sheets" in err and "invalid" in err


@pytest.mark.parametrize("command", ["extract-grids", "extract-levels"])
def test_missing_sheets_file_is_usage_error(capsys, command, drawing, text_index, tmp_path):
    code, _, err = run_cli(
        capsys,
        command,
        str(drawing),
        "--text-index",
        str(text_index),
        "--sheets",
        str(tmp_path / "nope.json"),
        "--out",
        str(tmp_path / "o.json"),
    )
    assert code == 2 and "not a file" in err


@pytest.mark.parametrize("command", ["extract-grids", "extract-levels"])
def test_sheets_option_is_required(capsys, command, drawing, text_index, tmp_path):
    code, _, _ = run_cli(
        capsys, command, str(drawing), "--text-index", str(text_index), "--out", str(tmp_path / "o.json")
    )
    assert code == 2


@pytest.mark.parametrize("command", ["extract-grids", "extract-levels"])
def test_output_of_grids_and_levels_is_validated(
    monkeypatch, capsys, command, drawing, text_index, sheets, tmp_path
):
    name = "extract_grids" if command == "extract-grids" else "extract_levels"
    monkeypatch.setattr(structure_mod, name, lambda *a, **k: {"schema_version": "0.1"})
    out = tmp_path / "o.json"
    code, _, err = run_cli(
        capsys,
        command,
        str(drawing),
        "--text-index",
        str(text_index),
        "--sheets",
        str(sheets),
        "--out",
        str(out),
    )
    assert code == 1 and "invalid" in err and not out.exists()


# --- read-structure ------------------------------------------------------------------------------


@pytest.fixture
def folder(tmp_path) -> Path:
    """A drawing set, a DWG (fake-converted to the same drawing), a corrupt DXF and a PDF stub."""
    root = tmp_path / "input"
    root.mkdir()
    build_set(root, "set.dxf")
    (root / "conv.dwg").write_bytes(DWG_BYTES)
    (root / "broken.dxf").write_text("0\nSECTION\n2\nENTITIES\n0\nLINE\n8\n", encoding="utf-8")
    (root / "c.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    return root


def rs(work: Path):
    """read-structure over a `work` fixture folder (its input folder is the sibling 'input')."""
    return read_structure(work, work.parent / "input")


@pytest.fixture
def work(folder, tmp_path) -> Path:
    (tmp_path / "tpl").mkdir()
    template = build_set(tmp_path / "tpl", "template.dxf")
    out = tmp_path / "work"
    run_intake(folder, out, "demo-structure", dwg2dxf=fake_dwg2dxf(tmp_path, template))
    return out


def test_read_structure_end_to_end(work, capsys):
    inventory_before = (work / "inventory.json").read_bytes()
    questions_before = (work / "questions.json").read_bytes()
    code, summary, err = run_cli(
        capsys, "read-structure", str(work), "--input-dir", str(work.parent / "input")
    )
    assert code == 0, err
    assert summary is not None
    assert summary["files"] == 4 and summary["processed"] == 2 and summary["skipped"] == 2
    for rel in ("conv.dwg", "set.dxf"):
        for kind, schema in (("sheets", "sheets"), ("grids", "grids"), ("levels", "levels")):
            doc = load(work / "structure" / f"{rel}.{kind}.json")
            assert validate(schema, doc) == []
    assert not (work / "structure" / "broken.dxf.sheets.json").exists()
    assert not (work / "structure" / "c.pdf.sheets.json").exists()
    assert validate("intake", load(work / "structure-questions.json")) == []
    assert validate("intake", load(work / "structure-summary.json")) == []
    assert (work / "inventory.json").read_bytes() == inventory_before  # intake owns these two
    assert (work / "questions.json").read_bytes() == questions_before
    assert summary["outputs"]["questions"] == str(work / "structure-questions.json")
    assert "skipped" in err and "broken.dxf" in err  # the reason is logged, not swallowed


def test_read_structure_matches_the_single_commands(work, capsys, tmp_path):
    assert main(["read-structure", str(work), "--input-dir", str(work.parent / "input")]) == 0
    capsys.readouterr()
    text = work / "text" / "conv.dwg.json"
    dxf = work / "converted" / "conv.dxf"
    s, g, lv = tmp_path / "s.json", tmp_path / "g.json", tmp_path / "l.json"
    assert main(["extract-sheets", str(dxf), "--text-index", str(text), "--out", str(s)]) == 0
    assert (
        main(["extract-grids", str(dxf), "--text-index", str(text), "--sheets", str(s), "--out", str(g)]) == 0
    )
    assert (
        main(["extract-levels", str(dxf), "--text-index", str(text), "--sheets", str(s), "--out", str(lv)])
        == 0
    )
    assert s.read_bytes() == (work / "structure" / "conv.dwg.sheets.json").read_bytes()
    assert g.read_bytes() == (work / "structure" / "conv.dwg.grids.json").read_bytes()
    assert lv.read_bytes() == (work / "structure" / "conv.dwg.levels.json").read_bytes()


def test_summary_content(work):
    assert rs(work).exit_code == 0
    doc = load(work / "structure-summary.json")
    rows = {f["path"]: f for f in doc["files"]}
    assert list(rows) == sorted(rows) == ["broken.dxf", "c.pdf", "conv.dwg", "set.dxf"]
    assert doc["project_id"] == "demo-structure"
    assert doc["kind"] == "structure_summary"
    s = rows["set.dxf"]
    assert s["status"] == "processed" and s["reason"] is None
    assert s["outputs"] == {
        "sheets": "structure/set.dxf.sheets.json",
        "grids": "structure/set.dxf.grids.json",
        "levels": "structure/set.dxf.levels.json",
    }
    assert s["sheets"]["count"] == 3
    assert s["sheets"]["sheet_numbers"] == {"found": 3, "missing": 0, "by_confidence": {"medium": 3}}
    fams = {f["coordinates"]: f for f in s["grids"]["families"]}
    assert fams["0 3*6000"]["labels"] == "1 2 3 4" and fams["0 3*6000"]["sheet"] == "model#01"
    assert fams["0 3*6000"]["unit"] == "mm" and fams["0 3*6000"]["confidence"] in ("low", "medium", "high")
    assert s["grids"]["families_total"] == len(s["grids"]["families"]) >= 2
    single = [f for f in s["grids"]["families"] if f["coordinates"] is None]  # the skewed one-axis family
    assert single and all(f["axes"] == 1 and f["unit"] is None and f["complete"] is None for f in single)
    assert fams["0 3*6000"]["complete"] is False and fams["0 3*6000"]["confidence"] == "low"
    levels = {lv["value_text"]: lv for lv in s["levels"]["levels"]}
    assert levels["+3.600"]["count"] >= 2 and levels["+3.600"]["value"] == 3.6
    assert (
        s["questions"]["total"]
        == s["questions"]["sheets"] + s["questions"]["grids"] + s["questions"]["levels"]
    )
    assert s["questions"]["blocking"] >= 3
    broken, pdf = rows["broken.dxf"], rows["c.pdf"]
    assert broken["status"] == "skipped" and "could not" in broken["reason"].lower()
    assert broken["sheets"] is None and broken["outputs"] is None and broken["questions"] is None
    assert pdf["status"] == "skipped" and "pdf" in pdf["reason"]
    assert doc["summary"]["files"] == 4 and doc["summary"]["processed"] == 2


def test_summary_records_the_intake_state_it_was_built_from(work):
    import hashlib

    rs(work)
    doc = load(work / "structure-summary.json")
    assert doc["inventory_sha256"] == hashlib.sha256((work / "inventory.json").read_bytes()).hexdigest()
    assert "first_question_number" not in doc  # ids come from the registry now


def test_question_ids_continue_after_intake(work):
    rs(work)
    intake_ids = [q["id"] for q in load(work / "questions.json")["questions"]]
    struct = load(work / "structure-questions.json")["questions"]
    ids = [q["id"] for q in struct]
    highest = max(int(i[2:]) for i in intake_ids)
    assert ids == [f"Q-{n:03d}" for n in range(highest + 1, highest + 1 + len(ids))]
    assert not set(ids) & set(intake_ids)


def test_question_ids_come_from_the_registry_counter(work):
    registry = load(work / "question-registry.json")
    registry["next_id"] = 121  # a gap: ids are never reused, so allocation continues from next_id
    (work / "question-registry.json").write_text(json.dumps(registry), encoding="utf-8")
    rs(work)
    struct = load(work / "structure-questions.json")["questions"]
    assert struct[0]["id"] == "Q-121"
    assert load(work / "question-registry.json")["next_id"] == 121 + len(struct)


def test_one_question_per_code_blocking_and_file(work):
    rs(work)
    questions = load(work / "structure-questions.json")["questions"]
    keys = [(q["code"], q["blocking"], q["file"]) for q in questions]
    assert len(keys) == len(set(keys))
    assert keys == sorted(keys, key=lambda k: (not k[1], k[0], k[2]))  # blocking first, code, file
    per_file = {}
    for kind in ("sheets", "grids", "levels"):
        for rel in ("conv.dwg", "set.dxf"):
            per_file[(rel, kind)] = load(work / "structure" / f"{rel}.{kind}.json")["questions"]
    for q in questions:
        assert q["count"] == len(q["refs"]) and q["truncated"] is False
        assert q["file"] in ("conv.dwg", "set.dxf")
        for ref in q["refs"]:
            assert ref["file"] == q["file"]
            assert {"where", "found"} <= ref.keys()
    gate1 = [q for q in questions if q["code"] == "grid_gate1_confirmation"]
    assert [q["file"] for q in gate1] == ["conv.dwg", "set.dxf"] and all(q["blocking"] for q in gate1)
    total_source = sum(len(v) for v in per_file.values())
    assert sum(q["count"] for q in questions) == total_source


def test_refs_carry_the_detector_sheet(work):
    rs(work)
    questions = load(work / "structure-questions.json")["questions"]
    sheet_refs = [r for q in questions for r in q["refs"] if "sheet" in r]
    assert sheet_refs and all(r["sheet"] for r in sheet_refs)
    source = (
        load(work / "structure" / "set.dxf.sheets.json")["questions"]
        + load(work / "structure" / "set.dxf.grids.json")["questions"]
    )
    expected = {(q["code"], q["sheet"]) for q in source if "sheet" in q}
    got = {
        (q["code"], r["sheet"])
        for q in questions
        for r in q["refs"]
        if "sheet" in r and r["file"] == "set.dxf"
    }
    assert expected <= got


def test_refs_are_capped_with_the_true_count(work, monkeypatch):
    monkeypatch.setattr(structure_mod, "MAX_STRUCTURE_REFS", 1)
    rs(work)
    questions = load(work / "structure-questions.json")["questions"]
    once = [q for q in questions if q["code"] == "level_single_occurrence"]
    assert [(q["file"], q["count"], len(q["refs"]), q["truncated"]) for q in once] == [
        ("conv.dwg", 2, 1, True),
        ("set.dxf", 2, 1, True),
    ]
    assert validate("intake", load(work / "structure-questions.json")) == []
    assert MAX_STRUCTURE_REFS == 50


def test_read_structure_is_deterministic(work):
    rs(work)
    first = tree(work)
    rs(work)
    again = tree(work)
    # the registry counts producer runs; every other document is byte-identical
    assert {k: v for k, v in again.items() if k != "question-registry.json"} == {
        k: v for k, v in first.items() if k != "question-registry.json"
    }
    assert json.loads(again["question-registry.json"])["runs"] == 3  # intake + two read-structure runs


def test_stale_structure_files_are_removed(work):
    (work / "structure").mkdir()
    (work / "structure" / "old.dxf.sheets.json").write_text("{}", encoding="utf-8")
    rs(work)
    assert not (work / "structure" / "old.dxf.sheets.json").exists()


def test_refuses_a_folder_without_inventory(tmp_path, capsys):
    (tmp_path / "empty").mkdir()
    code, _, err = run_cli(capsys, "read-structure", str(tmp_path / "empty"))
    assert code == 2 and "inventory.json" in err and "intake" in err
    assert not (tmp_path / "empty" / "structure").exists()


def test_refuses_a_missing_folder(tmp_path, capsys):
    code, _, err = run_cli(capsys, "read-structure", str(tmp_path / "nope"))
    assert code == 2 and "not a folder" in err


def test_refuses_a_folder_without_questions(work, capsys):
    (work / "questions.json").unlink()
    code, _, err = run_cli(capsys, "read-structure", str(work), "--input-dir", str(work.parent / "input"))
    assert code == 2 and "questions.json" in err


def test_invalid_inventory_is_exit_1(work, capsys):
    doc = load(work / "inventory.json")
    del doc["files"]
    (work / "inventory.json").write_text(json.dumps(doc), encoding="utf-8")
    code, _, err = run_cli(capsys, "read-structure", str(work), "--input-dir", str(work.parent / "input"))
    assert code == 1 and "inventory.json" in err and not (work / "structure").exists()


def test_changed_input_dxf_is_exit_1_and_nothing_is_written(work, folder, capsys):
    build_set(folder, "set.dxf", sheet2_number="S-999")  # the native DXF changed after intake
    code, summary, err = run_cli(
        capsys, "read-structure", str(work), "--input-dir", str(work.parent / "input")
    )
    assert code == 1 and summary is None
    assert "set.dxf" in err and "sha256" in err
    assert not (work / "structure").exists()
    assert not (work / "structure-questions.json").exists()
    assert not (work / "structure-summary.json").exists()


def test_missing_text_index_file_is_exit_1(work, capsys):
    (work / "text" / "conv.dwg.json").unlink()
    code, _, err = run_cli(capsys, "read-structure", str(work), "--input-dir", str(work.parent / "input"))
    assert code == 1 and "text/conv.dwg.json" in err and not (work / "structure").exists()


def test_inventory_paths_cannot_leave_the_work_folder(work, capsys):
    doc = load(work / "inventory.json")
    for row in doc["files"]:
        if row["path"] == "conv.dwg":
            row["text_index"] = "../../etc/passwd"
    (work / "inventory.json").write_text(json.dumps(doc), encoding="utf-8")
    code, _, err = run_cli(capsys, "read-structure", str(work), "--input-dir", str(work.parent / "input"))
    assert code == 1 and "outside the work folder" in err


def test_ids_survive_a_rerun_of_intake_and_read_structure(work, folder, tmp_path):
    rs(work)
    first = {q["key"]: q["id"] for q in load(work / "structure-questions.json")["questions"]}
    intake_first = {q["key"]: q["id"] for q in load(work / "questions.json")["questions"]}
    (tmp_path / "tpl2").mkdir()
    template = build_set(tmp_path / "tpl2", "template.dxf")
    run_intake(folder, work, "demo-structure", dwg2dxf=fake_dwg2dxf(tmp_path, template))
    rs(work)
    assert {q["key"]: q["id"] for q in load(work / "structure-questions.json")["questions"]} == first
    assert {q["key"]: q["id"] for q in load(work / "questions.json")["questions"]} == intake_first
    assert not set(first.values()) & set(intake_first.values())


def test_native_dxf_with_no_structure_gives_valid_empty_outputs(tmp_path):
    root = tmp_path / "input"
    root.mkdir()
    from ezdxf.filemanagement import new

    doc = new("R2018")
    doc.header["$INSUNITS"] = 4
    doc.modelspace().add_line((0, 0), (10, 0))
    doc.saveas(root / "plain.dxf")
    out = tmp_path / "work"
    run_intake(root, out, "demo-plain")
    result = read_structure(out, root)
    assert result.exit_code == 0
    assert validate("intake", load(out / "structure-questions.json")) == []
    assert validate("intake", load(out / "structure-summary.json")) == []
    row = load(out / "structure-summary.json")["files"][0]
    assert row["status"] == "processed" and row["sheets"]["count"] == 0
    assert row["grids"]["families_total"] == 0 and row["levels"]["levels_total"] == 0
    codes = {q["code"] for q in load(out / "structure-questions.json")["questions"]}
    assert "grid_none_found" in codes


# --- provenance paths and true counts (review regressions) --------------------------------------


def test_no_output_names_the_absolute_input_folder(work, folder):
    assert rs(work).exit_code == 0
    raw = {str(folder), str(folder.resolve()), folder.resolve().as_posix()}
    needles = raw | {json.dumps(n)[1:-1] for n in raw}  # JSON escapes the backslashes of a Windows path
    for path in sorted(work.rglob("*.json")):
        text = path.read_text(encoding="utf-8")
        assert not any(n in text for n in needles), path
    sheets = load(work / "structure" / "set.dxf.sheets.json")
    assert sheets["file"]["path"] == "set.dxf"
    assert load(work / "text" / "conv.dwg.json")["file"]["path"] == "conv.dwg"  # the DWG, input-relative
    grids = load(work / "structure" / "set.dxf.grids.json")
    label = grids["groups"][0]["families"][0]["axes"][0]["label"]
    assert label["provenance"]["file"] == "set.dxf"


def test_a_native_dxf_needs_the_input_folder(work, capsys):
    code, summary, err = run_cli(capsys, "read-structure", str(work))
    assert code == 2 and summary is None
    assert "set.dxf" in err and "--input-dir" in err
    assert not (work / "structure").exists()


def test_grid_question_refs_carry_the_grid_families_they_cite(work):
    """Fix 5b: lifecycle closes a read-structure question only when every family it cites belongs to an
    unselected grid system, so each grid ref names its families (not part of the key)."""
    assert rs(work).exit_code == 0
    grids = load(work / "structure" / "set.dxf.grids.json")
    usable = sorted(f["family_id"] for g in grids["groups"] for f in g["families"] if len(f["axes"]) >= 2)
    questions = [q for q in load(work / "structure-questions.json")["questions"] if q["file"] == "set.dxf"]
    by_code = {q["code"]: q for q in questions}
    assert by_code["grid_family_axis_assignment"]["refs"][0]["families"] == usable
    missing = by_code["grid_label_missing"]["refs"][0]
    assert missing["families"] == [missing["where"].split("/")[1].split()[0]]
    for q in questions:
        for ref in q["refs"]:
            if not q["code"].startswith("grid_") or q["code"] == "grid_units_doubt":
                assert "families" not in ref, q["code"]
            elif "families" in ref:
                assert set(ref["families"]) <= set(usable) | {
                    f["family_id"] for g in grids["groups"] for f in g["families"]
                }


def _family_questions(n: int, missing: int | None = None) -> list[tuple[dict, list[str] | None]]:
    return [
        (
            {
                "code": "grid_label_duplicate",
                "blocking": True,
                "message": "m",
                "where": f"V001/F{k:03d}",
                "found": "A",
            },
            None if k == missing else [f"F{k:03d}"],
        )
        for k in range(1, n + 1)
    ]


def test_truncated_refs_still_cover_every_cited_family():
    from collections import Counter

    (q,) = structure_mod._consolidate([("a.dxf", _family_questions(MAX_STRUCTURE_REFS + 10), Counter())])
    assert q["truncated"] and len(q["refs"]) == MAX_STRUCTURE_REFS and q["count"] == MAX_STRUCTURE_REFS + 10
    assert q["refs"][0]["families"] == ["F001"]
    # the last listed ref also carries the families of the refs that were not listed
    assert q["refs"][-1]["families"] == [
        f"F{k:03d}" for k in range(MAX_STRUCTURE_REFS, MAX_STRUCTURE_REFS + 11)
    ]
    union = {f for r in q["refs"] for f in r["families"]}
    assert union == {f"F{k:03d}" for k in range(1, MAX_STRUCTURE_REFS + 11)}


@pytest.mark.parametrize("case", ["extractor_unlisted", "unlisted_ref_without_family"])
def test_a_question_whose_families_are_not_all_known_carries_none(case):
    from collections import Counter

    n = MAX_STRUCTURE_REFS + 10
    if case == "extractor_unlisted":  # the grids extractor counted more than it listed: unknown families
        per_file = [("a.dxf", _family_questions(3), Counter({"grid_label_duplicate": 5}))]
    else:
        per_file = [("a.dxf", _family_questions(n, missing=n), Counter())]
    (q,) = structure_mod._consolidate(per_file)
    assert q["truncated"] and all("families" not in r for r in q["refs"])


def test_consolidated_counts_include_questions_an_extractor_did_not_list(work, monkeypatch):
    from tekla_harness import levels as levels_mod

    monkeypatch.setattr(levels_mod, "MAX_QUESTIONS_PER_CODE", 1)
    rs(work)
    once = next(
        q
        for q in load(work / "structure-questions.json")["questions"]
        if q["code"] == "level_single_occurrence" and q["file"] == "set.dxf"
    )
    doc = load(work / "structure" / "set.dxf.levels.json")
    assert len([q for q in doc["questions"] if q["code"] == "level_single_occurrence"]) == 1
    assert doc["question_counts"]["level_single_occurrence"] == 2
    assert once["count"] == 2 and len(once["refs"]) == 1 and once["truncated"] is True
    row = next(f for f in load(work / "structure-summary.json")["files"] if f["path"] == "set.dxf")
    assert row["questions"]["levels"] == sum(doc["question_counts"].values())
