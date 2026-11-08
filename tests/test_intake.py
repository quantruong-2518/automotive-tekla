"""harness intake: the whole Step 1 chain over a folder, with programmatic DXFs and fake converters.

Real converters are not on CI: the fake `dwg2dxf` is a Python script run as [sys.executable, script]
(as in test_convert.py). It copies a template DXF, or fails when the DWG name contains 'bad'.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest
from ezdxf.filemanagement import new

from conftest import EXAMPLES
from tekla_harness import intake as intake_mod
from tekla_harness.answers import record_answer
from tekla_harness.cli import main
from tekla_harness.intake import MAX_PROBE_REFS, IntakeError, run_intake
from tekla_harness.knowledge import EMPTY_TABLE, KnowledgeError
from tekla_harness.schemas import validate
from tekla_harness.worklock import work_lock
from test_knowledge import approved, row, table_of

DWG_BYTES = b"AC1032" + b"\x00" * 64
BIG_DWG_BYTES = b"AC1032" + b"\x00" * 20_000
FAKE_BODY = {
    "ok": "shutil.copy(TEMPLATE, out_path)",
    "errors": "shutil.copy(TEMPLATE, out_path); sys.stderr.write('ERROR: overflow\\nERROR: again\\n')",
    "empty": "import ezdxf; ezdxf.new('R2018').saveas(out_path)",
}


def fake_dwg2dxf(tmp_path: Path, template: Path, body: str = "ok") -> list[str]:
    """Fails (exit 1) for any DWG whose name contains 'bad'; otherwise runs FAKE_BODY[body]."""
    script = tmp_path / f"fake_dwg2dxf_{body}.py"
    script.write_text(
        textwrap.dedent(f"""\
            import os, shutil, sys
            TEMPLATE = {str(template)!r}
            out_path = sys.argv[sys.argv.index('-o') + 1]
            if 'bad' in os.path.basename(sys.argv[-1]):
                sys.stderr.write('fatal: bad header'); sys.exit(1)
            {FAKE_BODY[body]}
        """),
        encoding="utf-8",
    )
    return [sys.executable, str(script)]


def make_dxf(path: Path, units: int = 4, dims: int = 0) -> Path:
    doc = new("R2018")
    doc.header["$INSUNITS"] = units
    doc.header["$MEASUREMENT"] = 1
    msp = doc.modelspace()
    msp.add_line((0, 0), (6000, 0))
    for i in range(dims):  # typed-over text that differs from the geometry
        msp.add_linear_dim(base=(0, 3 + i), p1=(0, 0), p2=(1000, 0), text="9999").render()
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(path)
    return path


@pytest.fixture
def template(tmp_path) -> Path:
    return make_dxf(tmp_path / "template.dxf", units=6)


@pytest.fixture
def folder(tmp_path) -> Path:
    """Two DXFs (one with $INSUNITS=0), a good and a failing DWG, a PDF stub, a text file."""
    root = tmp_path / "input"
    make_dxf(root / "a.dxf", units=4)
    make_dxf(root / "sub" / "b.dxf", units=0)
    (root / "good.dwg").write_bytes(DWG_BYTES)
    (root / "sub" / "bad.dwg").write_bytes(DWG_BYTES)
    (root / "c.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    (root / "notes.txt").write_text("hello", encoding="utf-8")
    return root


def run(folder: Path, out: Path, template: Path, tmp_path: Path, **kw):
    kw.setdefault("dwg2dxf", fake_dwg2dxf(tmp_path, template))
    return run_intake(folder, out, "demo-intake", **kw)


def load(out: Path, name: str):
    return json.loads((out / name).read_text(encoding="utf-8"))


def tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def by_file(doc: dict, key: str = "files") -> dict[str, dict]:
    return {f.get("file") or f["path"]: f for f in doc[key]}


def stable_read_log(log: dict) -> dict:
    """Read log minus the only nondeterministic fields: attempt timestamps and durations."""
    log = json.loads(json.dumps(log))
    for f in log["files"]:
        for a in f["attempts"]:
            a.pop("started_at")
            a.pop("duration_ms")
    return log


@pytest.fixture
def done(folder, tmp_path, template):
    out = tmp_path / "work"
    return run(folder, out, template, tmp_path), out


# --- outputs ---------------------------------------------------------------------------------


def test_outputs_are_written_and_valid(done):
    result, out = done
    assert (out / "read-log.json").is_file()
    assert validate("read-log", load(out, "read-log.json")) == []
    assert validate("intake", load(out, "inventory.json")) == []
    assert validate("intake", load(out, "questions.json")) == []
    probes = sorted(p.relative_to(out).as_posix() for p in (out / "probe").rglob("*.json"))
    assert probes == ["probe/a.dxf.json", "probe/good.dwg.json", "probe/sub/b.dxf.json"]
    for p in probes:
        assert validate("dxf-probe", load(out, p)) == []
    assert (out / "converted" / "good.dxf").is_file()
    assert not (out / "converted" / "sub" / "bad.dxf").exists()
    assert result.summary["files"] == 6


def test_examples_are_valid():
    for name in ("intake", "intake-questions"):
        data = json.loads((EXAMPLES / f"{name}.example.json").read_text(encoding="utf-8"))
        assert validate("intake", data) == []


def test_inventory_rows(done):
    _, out = done
    rows = by_file(load(out, "inventory.json"))
    assert list(rows) == sorted(rows)
    a = rows["a.dxf"]
    assert (a["format"], a["converter"], a["confidence_cap"], a["outcome"]) == ("dxf", "none", "high", "read")
    assert a["units"] == {
        "value": "mm",
        "confidence": "medium",
        "flags": ["units_confirm"],
        "dimension_median": None,  # fewer than 3 modelspace linear dimensions
    }
    assert a["layouts"][0] == "Model" and a["modelspace_entity_total"] == 1
    assert a["probe"] == "probe/a.dxf.json" and a["converted"] is None and a["conversion"] is None
    assert a["dwg_version"] is None and a["dimension_override_differs"] == 0
    b = rows["sub/b.dxf"]
    assert b["units"]["value"] == "unknown" and "units_unknown" in b["units"]["flags"]
    good = rows["good.dwg"]
    assert (good["dwg_version"], good["converter"], good["confidence_cap"]) == (
        "AC1032",
        "libredwg",
        "medium",
    )
    assert good["converted"] == "converted/good.dxf" and good["probe"] == "probe/good.dwg.json"
    assert good["conversion"] == {"stderr_error_lines": 0, "stderr_warning_lines": 0, "stderr_tail": ""}
    bad = rows["sub/bad.dwg"]
    assert (bad["outcome"], bad["converter"], bad["confidence_cap"], bad["units"], bad["probe"]) == (
        "unreadable",
        None,
        None,
        None,
        None,
    )
    assert rows["c.pdf"]["format"] == "pdf" and rows["c.pdf"]["layouts"] is None
    assert rows["notes.txt"]["format"] == "other"
    summary = load(out, "inventory.json")["summary"]
    assert summary["by_format"] == {"dwg": 2, "dxf": 2, "other": 1, "pdf": 1}
    assert summary["by_outcome"] == {"read": 3, "unreadable": 3}


# --- read log ----------------------------------------------------------------------------------


def test_read_log_outcomes_attempts_and_formats(done):
    _, out = done
    files = by_file(load(out, "read-log.json"))
    assert files["a.dxf"]["outcome"] == "read" and files["a.dxf"]["max_confidence"] == "high"
    assert [a["tool"] for a in files["a.dxf"]["attempts"]] == ["ezdxf"]
    good = files["good.dwg"]
    assert [a["tool"] for a in good["attempts"]] == ["libredwg_dwg2dxf", "ezdxf"]
    assert good["outcome"] == "read" and good["max_confidence"] == "medium"
    assert any("fallback" in w for w in good["warnings"])
    bad = files["sub/bad.dwg"]
    assert bad["outcome"] == "unreadable" and "max_confidence" not in bad
    assert all(a["status"] == "failed" and "exit code 1" in a["error"] for a in bad["attempts"])
    pdf = files["c.pdf"]
    # Regression: an unread PDF must not be logged as 'pdf_mixed' (a guess about its content).
    assert pdf["format"] == "other" and pdf["outcome"] == "unreadable"
    assert any("not determined" in w for w in pdf["warnings"])
    (attempt,) = pdf["attempts"]
    assert attempt["status"] == "failed"
    assert attempt["error"] == "no reader implemented for pdf yet (roadmap)"
    assert files["notes.txt"]["attempts"][0]["error"] == "no reader implemented for other yet (roadmap)"


def test_converter_error_lines_make_the_file_partial(tmp_path, folder, template):
    out = tmp_path / "work"
    result = run(folder, out, template, tmp_path, dwg2dxf=fake_dwg2dxf(tmp_path, template, "errors"))
    good = by_file(load(out, "read-log.json"))["good.dwg"]
    assert good["outcome"] == "partial" and good["max_confidence"] == "medium"
    assert any("2 ERROR lines" in w for w in good["warnings"])
    codes = {q["code"]: q for q in load(out, "questions.json")["questions"]}
    assert codes["converter_errors"]["blocking"] is False
    assert codes["converter_errors"]["refs"][0]["file"] == "good.dwg"
    row = by_file(load(out, "inventory.json"))["good.dwg"]
    assert row["conversion"]["stderr_error_lines"] == 2 and "overflow" in row["conversion"]["stderr_tail"]
    assert result.summary["by_outcome"]["partial"] == 1


def test_empty_conversion_is_partial_low_and_blocking(tmp_path, template):
    root = tmp_path / "input"
    root.mkdir()
    (root / "big.dwg").write_bytes(BIG_DWG_BYTES)
    out = tmp_path / "work"
    result = run_intake(root, out, "demo-intake", dwg2dxf=fake_dwg2dxf(tmp_path, template, "empty"))
    entry = load(out, "read-log.json")["files"][0]
    assert entry["outcome"] == "partial" and entry["max_confidence"] == "low"
    assert [a["status"] for a in entry["attempts"]] == ["partial", "ok"]
    question = next(q for q in load(out, "questions.json")["questions"] if q["code"] == "conversion_empty")
    assert question["blocking"] is True and question["refs"][0]["file"] == "big.dwg"
    assert result.exit_code == 0


def test_oda_failure_falls_back_and_keeps_both_attempts(tmp_path, folder, template):
    out = tmp_path / "work"
    run(folder, out, template, tmp_path, oda=[str(tmp_path / "no-such-oda")])
    good = by_file(load(out, "read-log.json"))["good.dwg"]
    assert [a["tool"] for a in good["attempts"]] == ["oda_file_converter", "libredwg_dwg2dxf", "ezdxf"]
    assert good["attempts"][0]["status"] == "failed"


def test_unopenable_dxf_is_unreadable(tmp_path):
    root = tmp_path / "input"
    root.mkdir()
    (root / "broken.dxf").write_text("0\nSECTION\n2\nENTITIES\n0\nLINE\n8\n", encoding="utf-8")
    out = tmp_path / "work"
    result = run_intake(root, out, "demo-intake")
    entry = load(out, "read-log.json")["files"][0]
    assert entry["outcome"] == "unreadable" and entry["attempts"][0]["tool"] == "ezdxf"
    assert result.exit_code == 1 and result.summary["read_failures"] == ["broken.dxf"]
    codes = [q["code"] for q in load(out, "questions.json")["questions"]]
    assert codes == ["read_failed"]
    assert validate("dxf-probe", load(out, "probe/broken.dxf.json")) == []


# --- questions ---------------------------------------------------------------------------------


def test_one_units_question_per_dxf(done):
    _, out = done
    questions = load(out, "questions.json")["questions"]
    units = [q for q in questions if q["code"] == "units_confirm_all"]
    assert [q["file"] for q in units] == ["a.dxf", "good.dwg", "sub/b.dxf"]
    assert [q["code"] for q in questions[:3]] == ["units_confirm_all"] * 3
    assert all(q["blocking"] is True and q["truncated"] is False for q in units)
    assert [q["count"] for q in units] == [1, 1, 2]  # b.dxf: header ref + its folded units_unknown
    refs = {q["file"]: q["refs"][0] for q in units}
    assert all(r["file"] == f for f, r in refs.items())
    assert (refs["a.dxf"]["unit"], refs["a.dxf"]["confidence"], refs["a.dxf"]["flags"]) == (
        "mm",
        "medium",
        ["units_confirm"],
    )
    assert refs["good.dwg"]["unit"] == "m"
    assert "units_unknown" in refs["sub/b.dxf"]["flags"] and refs["sub/b.dxf"]["confidence"] == "low"
    assert not any(q["code"] == "units_confirm" for q in questions)  # subsumed, not repeated
    # one blocking units question per file: the probe's units_unknown is a ref of it, not a question
    assert not any(q["code"] in ("units_unknown", "units_conflict", "units_suspect") for q in questions)
    folded = next(q for q in units if q["file"] == "sub/b.dxf")["refs"][1]
    probe = load(out, "probe/sub/b.dxf.json")
    unknown = next(q for q in probe["questions"] if q["code"] == "units_unknown")
    assert (folded["where"], folded["found"]) == (unknown["where"], unknown["found"])  # verbatim
    assert folded["message"] == f"units_unknown: {unknown['message']}"


def test_units_evidence_folds_into_the_one_units_question_with_true_counts(tmp_path):
    """EVAL-1 F-04: file 267 had units_confirm_all + units_conflict + units_suspect (three blocking units
    questions from intake alone). Now one blocking question, the evidence verbatim in its refs."""
    root = tmp_path / "in"
    root.mkdir()
    doc = new("R2018")
    doc.header["$INSUNITS"] = 6  # metres ...
    doc.header["$MEASUREMENT"] = 0  # ... but an imperial measurement system: units_conflict
    for i in range(3):  # 4000 'm' dimensions: units_suspect
        doc.modelspace().add_linear_dim(base=(0, 3 + i), p1=(0, 0), p2=(4000 + i, 0)).render()
    doc.saveas(root / "m.dxf")
    run_intake(root, tmp_path / "work", "demo-units")
    questions = load(tmp_path / "work", "questions.json")["questions"]
    units = [q for q in questions if q["code"].startswith("units_")]
    assert [(q["code"], q["blocking"]) for q in units] == [("units_confirm_all", True)]
    (q,) = units
    probe = load(tmp_path / "work", "probe/m.dxf.json")
    evidence = [p for p in probe["questions"] if p["code"] in ("units_conflict", "units_suspect")]
    assert len(evidence) == 2 and q["count"] == 3 and not q["truncated"]
    assert [(r["where"], r["found"]) for r in q["refs"][1:]] == [(p["where"], p["found"]) for p in evidence]
    assert set(q["refs"][0]["flags"]) >= {"units_conflict", "units_suspect"}
    median = load(tmp_path / "work", "inventory.json")["files"][0]["units"]["dimension_median"]
    assert median == {"value": 4001.0, "count": 3}


def test_question_ids_order_and_blocking_summary(done):
    result, out = done
    doc = load(out, "questions.json")
    questions = doc["questions"]
    assert [q["id"] for q in questions] == [f"Q-{i:03d}" for i in range(1, len(questions) + 1)]
    assert [(q["code"], q["file"]) for q in questions] == [
        ("units_confirm_all", "a.dxf"),
        ("units_confirm_all", "good.dwg"),
        ("units_confirm_all", "sub/b.dxf"),
        ("read_failed", "sub/bad.dwg"),
        ("no_reader_implemented", "c.pdf"),
        ("no_reader_implemented", "notes.txt"),
        ("file_set_relation", None),  # project level, last: it never shifts the file questions' ids
    ]
    summary = load(out, "inventory.json")["summary"]
    assert summary["questions"] == len(questions) == result.summary["questions"]
    assert summary["blocking_questions"] == sum(q["blocking"] for q in questions) == 7
    assert doc["summary"] == {"questions": 7, "blocking_questions": 7, "answered": 0, "blocking_open": 7}
    assert all(q["answer"] is None and len(q["key"]) == 16 for q in questions)


def _file_set(out: Path) -> dict | None:
    found = [q for q in load(out, "questions.json")["questions"] if q["code"] == "file_set_relation"]
    assert len(found) <= 1
    return found[0] if found else None


def test_two_or_more_readable_drawing_files_raise_one_file_set_question(done):
    """EVAL-2 fix 5: one project-level "same set or separate projects?" question. One ref per readable
    DXF / DWG (`file` set: harness answer checks the answer's files against it); unreadable files and other
    formats are not in it."""
    _, out = done
    q = _file_set(out)
    assert q is not None
    assert (q["file"], q["blocking"], q["count"], q["truncated"]) == (None, True, 3, False)
    rows = {r["path"]: r["sha256"] for r in load(out, "inventory.json")["files"]}
    assert q["refs"] == [
        {"file": f, "where": f, "found": f"sha256 {rows[f]}"} for f in ("a.dxf", "good.dwg", "sub/b.dxf")
    ]
    assert "set1=" in q["message"]


def test_one_readable_drawing_file_raises_no_file_set_question(tmp_path):
    root = tmp_path / "input"
    make_dxf(root / "a.dxf")
    (root / "c.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    run_intake(root, tmp_path / "work", "demo-intake")
    assert _file_set(tmp_path / "work") is None


def test_the_file_set_question_is_answered_and_re_keyed_when_a_file_is_added(tmp_path):
    root = tmp_path / "input"
    make_dxf(root / "a.dxf")
    make_dxf(root / "b.dxf", units=6)
    work = tmp_path / "work"
    run_intake(root, work, "demo-intake")
    first = _file_set(work)
    assert first is not None and [r["file"] for r in first["refs"]] == ["a.dxf", "b.dxf"]
    record_answer(
        work, first["id"], "two buildings", "me", {"set1": "a.dxf", "set2": "b.dxf"}, role="engineer"
    )
    run_intake(root, work, "demo-intake")  # nothing changed: same key, same id, answer kept
    again = _file_set(work)
    assert again is not None and (again["id"], again["key"]) == (first["id"], first["key"])
    assert again["answer"]["values"] == {"set1": ["a.dxf"], "set2": ["b.dxf"]}
    make_dxf(root / "c.dxf")
    result = run_intake(root, work, "demo-intake")
    added = _file_set(work)
    assert added is not None and added["key"] != first["key"] and added["id"] != first["id"]
    assert [r["file"] for r in added["refs"]] == ["a.dxf", "b.dxf", "c.dxf"] and added["answer"] is None
    assert [a["question_id"] for a in result.summary["stale_answers"]] == [first["id"]]
    registry = load(work, "question-registry.json")["questions"]
    assert registry[first["key"]]["status"] == "obsolete"


def test_no_reader_question_is_blocking_and_one_per_file(done):
    _, out = done
    qs = [q for q in load(out, "questions.json")["questions"] if q["code"] == "no_reader_implemented"]
    assert all(q["blocking"] is True and "DXF or DWG" in q["message"] for q in qs)
    assert [(q["file"], q["refs"][0]["file"], q["refs"][0]["found"]) for q in qs] == [
        ("c.pdf", "c.pdf", "no reader implemented for pdf yet (roadmap)"),
        ("notes.txt", "notes.txt", "no reader implemented for other yet (roadmap)"),
    ]


def test_read_failed_question_names_the_conversion(done):
    _, out = done
    q = next(q for q in load(out, "questions.json")["questions"] if q["code"] == "read_failed")
    (ref,) = q["refs"]
    assert q["file"] == "sub/bad.dwg"
    assert ref["file"] == "sub/bad.dwg" and ref["where"] == "dwg conversion"
    assert "exit code 1" in ref["found"]


def test_probe_question_group_is_capped_with_true_count(tmp_path, template):
    root = tmp_path / "input"
    root.mkdir()
    make_dxf(root / "dims.dxf", dims=MAX_PROBE_REFS + 10)
    out = tmp_path / "work"
    run_intake(root, out, "demo-intake")
    q = next(q for q in load(out, "questions.json")["questions"] if q["code"] == "dimension_override_differs")
    assert q["count"] == MAX_PROBE_REFS + 10 and len(q["refs"]) == MAX_PROBE_REFS and q["truncated"] is True
    assert q["blocking"] is False
    assert load(out, "inventory.json")["files"][0]["dimension_override_differs"] == MAX_PROBE_REFS + 10


# --- safety, determinism, exit codes -----------------------------------------------------------


def test_input_folder_is_never_written(folder, tmp_path, template):
    before = tree(folder)
    run(folder, tmp_path / "work", template, tmp_path)
    assert tree(folder) == before


def test_deterministic_across_runs(folder, tmp_path, template):
    run(folder, tmp_path / "w1", template, tmp_path)
    run(folder, tmp_path / "w2", template, tmp_path)
    for name in ("inventory.json", "questions.json"):
        assert (tmp_path / "w1" / name).read_bytes() == (tmp_path / "w2" / name).read_bytes()
    assert stable_read_log(load(tmp_path / "w1", "read-log.json")) == stable_read_log(
        load(tmp_path / "w2", "read-log.json")
    )


def test_rerun_into_same_folder_leaves_no_stale_files(folder, tmp_path, template):
    out = tmp_path / "work"
    run(folder, out, template, tmp_path)
    (folder / "sub" / "b.dxf").unlink()
    (folder / "good.dwg").unlink()
    run(folder, out, template, tmp_path)
    assert not (out / "probe" / "sub").exists()
    assert not (out / "converted" / "good.dxf").exists()


@pytest.mark.parametrize("where", ["inside", "same"])
def test_work_folder_inside_or_equal_to_input_is_refused(folder, tmp_path, template, where):
    out = folder if where == "same" else folder / "work"
    before = tree(folder)
    with pytest.raises(IntakeError) as exc:
        run(folder, out, template, tmp_path)
    assert exc.value.exit_code == 2
    assert tree(folder) == before and not (folder / "work").exists()


def test_no_converter_with_dwg_is_environment_error_and_writes_nothing(folder, tmp_path, monkeypatch):
    monkeypatch.delenv("HARNESS_ODA_CONVERTER", raising=False)
    monkeypatch.delenv("HARNESS_DWG2DXF", raising=False)
    monkeypatch.setattr("tekla_harness.convert.shutil.which", lambda _name: None)
    out = tmp_path / "work"
    with pytest.raises(IntakeError) as exc:
        run_intake(folder, out, "demo-intake")
    assert exc.value.exit_code == 3 and not out.exists()


def test_no_converter_is_fine_without_dwg(tmp_path, monkeypatch):
    monkeypatch.delenv("HARNESS_ODA_CONVERTER", raising=False)
    monkeypatch.delenv("HARNESS_DWG2DXF", raising=False)
    monkeypatch.setattr("tekla_harness.convert.shutil.which", lambda _name: None)
    root = tmp_path / "input"
    make_dxf(root / "a.dxf")
    assert run_intake(root, tmp_path / "work", "demo-intake").exit_code == 0


def test_a_held_work_lock_is_an_intake_error_with_exit_3_and_writes_nothing(tmp_path):
    """run_intake promises IntakeError for exits 2 and 3: a held lock must not escape as WorkLockError."""
    root = tmp_path / "input"
    make_dxf(root / "a.dxf")
    work = tmp_path / "work"
    work.mkdir()
    with work_lock(work, "answer"), pytest.raises(IntakeError) as caught:
        run_intake(root, work, "demo-intake")
    assert caught.value.exit_code == 3 and "answer" in str(caught.value)
    assert not (work / "inventory.json").exists()


def test_exit_code_rule(done, folder, tmp_path):
    result, _ = done
    assert result.exit_code == 1  # bad.dwg is a supported format that could not be read
    assert result.summary["read_failures"] == ["sub/bad.dwg"]
    only_pdf = tmp_path / "pdf-only"
    only_pdf.mkdir()
    (only_pdf / "c.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    result = run_intake(only_pdf, tmp_path / "work2", "demo-intake")
    assert result.exit_code == 0  # no reader yet: unreadable plus a blocking question, not a read failure
    assert result.summary["blocking_questions"] == 1 and result.summary["by_outcome"] == {"unreadable": 1}


@pytest.mark.parametrize("project_id", ["Bad_ID", "x"])
def test_invalid_project_id_is_usage_error(folder, tmp_path, project_id):
    with pytest.raises(IntakeError) as exc:
        run_intake(folder, tmp_path / "work", project_id)
    assert exc.value.exit_code == 2


def test_missing_or_empty_input_is_usage_error(tmp_path):
    with pytest.raises(IntakeError) as exc:
        run_intake(tmp_path / "nope", tmp_path / "work", "demo-intake")
    assert exc.value.exit_code == 2
    (tmp_path / "empty").mkdir()
    with pytest.raises(IntakeError) as exc:
        run_intake(tmp_path / "empty", tmp_path / "work", "demo-intake")
    assert exc.value.exit_code == 2


def test_two_dwgs_converting_to_the_same_dxf_are_refused(tmp_path, template):
    root = tmp_path / "input"
    root.mkdir()
    (root / "a.dwg").write_bytes(DWG_BYTES)
    (root / "a").write_bytes(DWG_BYTES)  # content decides: also a DWG, also converts to a.dxf
    with pytest.raises(IntakeError) as exc:
        run_intake(root, tmp_path / "work", "demo-intake", dwg2dxf=fake_dwg2dxf(tmp_path, template))
    assert exc.value.exit_code == 2


# --- text index ----------------------------------------------------------------------------------

LEGACY_BYTES = "m\xc6t b\xbbng"  # TCVN3 bytes as latin-1 characters


def make_text_dxf(path: Path, texts: list[tuple[str, str, str]], xrefs: tuple[str, ...] = ()) -> Path:
    """texts: (text, style, font file). One TEXT per row, on its own style."""
    doc = new("R2018")
    doc.header["$INSUNITS"] = 4
    for name in xrefs:
        doc.add_xref_def(name, name.removesuffix(".dwg").upper())
    for i, (text, style, font) in enumerate(texts):
        if not doc.styles.has_entry(style):
            doc.styles.add(style, font=font)
        doc.modelspace().add_text(text, dxfattribs={"style": style, "height": 2.5, "insert": (0, 5 * i)})
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(path)
    return path


@pytest.fixture
def text_folder(tmp_path) -> Path:
    root = tmp_path / "input"
    make_text_dxf(
        root / "a.dxf",
        [
            ("ABC", ".VnTime", "vntime.ttf"),
            (LEGACY_BYTES, ".VnTime", "vntime.ttf"),  # decoded: TCVN3
            (LEGACY_BYTES, "kt..1", "VHARIAL.TTF"),  # unknown, matches a proposed row
            (LEGACY_BYTES, "kt..1", "VHARIAL.TTF"),
            (LEGACY_BYTES, "Simplex", "simplex.shx"),  # unknown, no row
            ("K\u00fd hi\u1ec7u", "Arial", "arial.ttf"),
        ],
    )
    make_text_dxf(root / "sub" / "b.dxf", [(LEGACY_BYTES, "kt..9", "VHARIAL.TTF")])
    return root


PROPOSED = row(pattern="VH*.TTF", evidence="seen in two drawings")


def test_text_index_is_written_per_probed_dxf_and_inventory_summarises_it(done):
    _, out = done
    docs = sorted(p.relative_to(out).as_posix() for p in (out / "text").rglob("*.json"))
    assert docs == ["text/a.dxf.json", "text/good.dwg.json", "text/sub/b.dxf.json"]
    for rel in docs:
        assert validate("text-index", load(out, rel)) == []
    rows = by_file(load(out, "inventory.json"))
    a = rows["a.dxf"]
    assert a["text_index"] == "text/a.dxf.json"
    assert a["text"] == {"entries": 0, "by_encoding_used": {}, "low_confidence": 0}
    assert rows["good.dwg"]["text_index"] == "text/good.dwg.json"
    for name in ("sub/bad.dwg", "c.pdf", "notes.txt"):
        assert rows[name]["text"] is None and rows[name]["text_index"] is None
    assert load(out, "text/good.dwg.json")["file"]["converter"] == "libredwg"


def test_inventory_text_summary_counts_entries_encodings_and_low_confidence(text_folder, tmp_path):
    out = tmp_path / "work"
    run_intake(text_folder, out, "demo-intake", knowledge=table_of(tmp_path, PROPOSED))
    a = by_file(load(out, "inventory.json"))["a.dxf"]
    assert a["text"] == {
        "entries": 6,
        "by_encoding_used": {"tcvn3": 2, "unicode": 1, "unknown": 3},
        "low_confidence": 3,  # the three unknown non-ASCII entries
    }


def test_questions_group_unknown_encodings_and_proposed_rows(text_folder, tmp_path):
    out = tmp_path / "work"
    run_intake(text_folder, out, "demo-intake", knowledge=table_of(tmp_path, PROPOSED))
    all_q = load(out, "questions.json")["questions"]
    proposed = [q for q in all_q if q["code"] == "font_encoding_proposed"]
    assert [q["file"] for q in proposed] == ["a.dxf", "sub/b.dxf"]  # one question per file
    assert all(q["blocking"] is False and len(q["refs"]) == 1 for q in proposed)
    assert "VH*.TTF" in proposed[0]["refs"][0]["where"] and "kt..1" in proposed[0]["refs"][0]["where"]
    assert "seen in two drawings" in proposed[0]["refs"][0]["found"]
    unknown = [q for q in all_q if q["code"] == "encoding_unknown_non_ascii"]
    assert [q["file"] for q in unknown] == ["a.dxf", "sub/b.dxf"]
    assert all(q["blocking"] is False for q in unknown)
    refs = {(r["file"], r["where"]): r["found"] for q in unknown for r in q["refs"]}
    assert set(refs) == {
        ("a.dxf", "text style kt..1"),
        ("a.dxf", "text style Simplex"),
        ("sub/b.dxf", "text style kt..9"),
    }
    assert (
        refs[("a.dxf", "text style kt..1")].startswith("2 entries")
        and "VHARIAL.TTF" in refs[("a.dxf", "text style kt..1")]
    )
    assert [q["count"] for q in unknown] == [2, 1]
    order = [q["code"] for q in all_q]
    # after the probe groups (and before conversion ones); the project-level file set question comes last
    assert order[-2:] == ["encoding_unknown_non_ascii", "file_set_relation"]


def test_an_approved_row_removes_the_unknown_question_for_its_styles(text_folder, tmp_path):
    out = tmp_path / "work"
    run_intake(text_folder, out, "demo-intake", knowledge=table_of(tmp_path, approved(pattern="VH*.TTF")))
    questions = load(out, "questions.json")["questions"]
    assert "font_encoding_proposed" not in {q["code"] for q in questions}
    refs = {
        (r["file"], r["where"])
        for q in questions
        if q["code"] == "encoding_unknown_non_ascii"
        for r in q["refs"]
    }
    assert refs == {("a.dxf", "text style Simplex")}
    text = load(out, "text/sub/b.dxf.json")
    assert text["entries"][0]["decode"]["source"] == "knowledge_table"
    assert text["entries"][0]["decoded_text"].startswith("mặt")


def test_unknown_question_group_is_capped_with_true_count(tmp_path):
    root = tmp_path / "input"
    texts = [(LEGACY_BYTES, f"S{i}", "simplex.shx") for i in range(MAX_PROBE_REFS + 5)]
    make_text_dxf(root / "many.dxf", texts)
    out = tmp_path / "work"
    run_intake(root, out, "demo-intake", knowledge=EMPTY_TABLE)
    q = next(q for q in load(out, "questions.json")["questions"] if q["code"] == "encoding_unknown_non_ascii")
    assert q["count"] == MAX_PROBE_REFS + 5 and len(q["refs"]) == MAX_PROBE_REFS and q["truncated"] is True


def test_default_knowledge_is_the_shipped_table(text_folder, tmp_path):
    out = tmp_path / "work"
    run_intake(text_folder, out, "demo-intake")
    codes = [q["code"] for q in load(out, "questions.json")["questions"]]
    # knowledge/font-encodings.csv approves VHARIAL.TTF as TCVN3: no proposed-row question, and the
    # kt..1 entries decode instead of staying unknown
    assert "font_encoding_proposed" not in codes
    a = by_file(load(out, "inventory.json"))["a.dxf"]
    assert a["text"]["by_encoding_used"] == {"tcvn3": 4, "unicode": 1, "unknown": 1}


def test_text_folder_is_cleared_on_rerun(text_folder, tmp_path):
    out = tmp_path / "work"
    run_intake(text_folder, out, "demo-intake", knowledge=EMPTY_TABLE)
    (text_folder / "sub" / "b.dxf").unlink()
    run_intake(text_folder, out, "demo-intake", knowledge=EMPTY_TABLE)
    assert not (out / "text" / "sub").exists()


def test_a_bad_knowledge_table_stops_the_run_and_writes_nothing(text_folder, tmp_path, monkeypatch):
    def boom():
        raise KnowledgeError("table is malformed")

    monkeypatch.setattr(intake_mod, "default_font_encodings", boom)
    out = tmp_path / "work"
    with pytest.raises(IntakeError, match="malformed") as caught:
        run_intake(text_folder, out, "demo-intake")
    assert caught.value.exit_code == 1 and not out.exists()


def test_xrefs_of_a_converted_dwg_are_looked_up_next_to_the_original_dwg(tmp_path):
    root = tmp_path / "input"
    root.mkdir()
    (root / "present.dwg").write_bytes(b"not a drawing")  # detected as 'other', never converted
    (root / "good.dwg").write_bytes(DWG_BYTES)
    make_text_dxf(root / "native.dxf", [], xrefs=("present.dwg",))
    template = make_text_dxf(tmp_path / "template.dxf", [], xrefs=("present.dwg", "missing.dwg"))
    out = tmp_path / "work"
    run_intake(root, out, "demo-intake", dwg2dxf=fake_dwg2dxf(tmp_path, template), knowledge=EMPTY_TABLE)
    xrefs = {x["name"]: x["resolved"] for x in load(out, "probe/good.dwg.json")["xrefs"]}
    assert xrefs == {"PRESENT": True, "MISSING": False}
    assert load(out, "probe/native.dxf.json")["xrefs"][0]["resolved"] is True
    (question,) = [q for q in load(out, "questions.json")["questions"] if q["code"] == "xref_unresolved"]
    assert [r["file"] for r in question["refs"]] == ["good.dwg"]
    assert "original drawing" in question["message"]


def test_text_partial_status_makes_the_file_partial(tmp_path, monkeypatch):
    root = tmp_path / "input"
    make_text_dxf(root / "a.dxf", [("ABC", "Standard", "txt")])
    real = intake_mod.extract_text

    def partial(*args, **kwargs):
        result = real(*args, **kwargs)
        result["status"] = "partial"
        result["summary"]["errors_total"] = 1
        result["summary"]["errors"] = [
            {"handle": None, "entity_type": "TEXT", "space": "model", "block_path": [], "error": "X: y"}
        ]
        return result

    monkeypatch.setattr(intake_mod, "extract_text", partial)
    out = tmp_path / "work"
    run_intake(root, out, "demo-intake", knowledge=EMPTY_TABLE)
    log = by_file(load(out, "read-log.json"))["a.dxf"]
    assert log["outcome"] == "partial" and any("text index" in w for w in log["warnings"])


def test_a_dxf_with_undecodable_bytes_is_still_written_and_flagged(tmp_path):
    root = tmp_path / "input"
    path = make_text_dxf(root / "damaged.dxf", [("ZZZZ", "Arial", "arial.ttf")])
    path.write_bytes(path.read_bytes().replace(b"ZZZZ", b"b\xff\xfe"))
    out = tmp_path / "work"
    run_intake(root, out, "demo-intake", knowledge=EMPTY_TABLE)
    assert (out / "text" / "damaged.dxf.json").read_text(encoding="utf-8").count("\ufffd") >= 1
    row_ = by_file(load(out, "inventory.json"))["damaged.dxf"]
    assert row_["text"] == {"entries": 1, "by_encoding_used": {"unicode": 1}, "low_confidence": 1}


# --- CLI ---------------------------------------------------------------------------------------


def test_cli_intake_exit_codes_and_summary(folder, tmp_path, template, capsys, monkeypatch):
    monkeypatch.setattr("tekla_harness.convert._split_command", lambda value: json.loads(value))
    monkeypatch.setenv("HARNESS_DWG2DXF", json.dumps(fake_dwg2dxf(tmp_path, template)))
    monkeypatch.delenv("HARNESS_ODA_CONVERTER", raising=False)
    out = tmp_path / "work"
    args = ["intake", str(folder), "--out", str(out), "--project-id", "demo-intake"]
    assert main(args) == 1
    summary = json.loads(capsys.readouterr().out)
    assert summary["files"] == 6 and summary["blocking_questions"] == 7  # 6 file questions + the file set
    assert summary["read_failures"] == ["sub/bad.dwg"]
    assert summary["outputs"]["inventory"] == str(out.resolve() / "inventory.json")
    assert main(["intake", str(folder), "--out", str(folder / "w"), "--project-id", "demo-intake"]) == 2
    assert main(["intake", str(folder)]) == 2  # --out and --project-id are required
    monkeypatch.delenv("HARNESS_DWG2DXF")
    monkeypatch.setattr("tekla_harness.convert.shutil.which", lambda _name: None)
    assert main(["intake", str(folder), "--out", str(tmp_path / "w3"), "--project-id", "demo-intake"]) == 3


def test_cli_validate_accepts_intake_documents(done, capsys):
    _, out = done
    assert main(["validate", "intake", str(out / "inventory.json"), str(out / "questions.json")]) == 0


def test_dwg2dxf_cli_prints_stderr_fields(tmp_path, template, capsys, monkeypatch):
    dwg = tmp_path / "input" / "S-101.dwg"
    dwg.parent.mkdir()
    dwg.write_bytes(DWG_BYTES)
    monkeypatch.setattr("tekla_harness.convert._split_command", lambda value: json.loads(value))
    monkeypatch.setenv("HARNESS_DWG2DXF", json.dumps(fake_dwg2dxf(tmp_path, template, "errors")))
    monkeypatch.delenv("HARNESS_ODA_CONVERTER", raising=False)
    assert main(["dwg2dxf", str(dwg), "--out-dir", str(tmp_path / "o")]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["stderr_error_lines"] == 2 and out["stderr_warning_lines"] == 0
    assert "overflow" in out["stderr_tail"]
