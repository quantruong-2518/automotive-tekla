from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from conftest import EXAMPLES
from tekla_harness.cli import main
from tekla_harness.schemas import validate


def _spec_copy(tmp_path: Path, name: str = "spec.json") -> Path:
    copy = tmp_path / name
    copy.write_bytes((EXAMPLES / "spec.example.json").read_bytes())
    return copy


def _write(tmp_path: Path, raw: bytes, name: str = "spec.json") -> Path:
    path = tmp_path / name
    path.write_bytes(raw)
    return path


def _example_text() -> str:
    return (EXAMPLES / "spec.example.json").read_text(encoding="utf-8")


def test_validate_ok(tmp_path, capsys):
    spec = _spec_copy(tmp_path)
    assert main(["validate", "spec", str(spec)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["results"][0]["valid"] is True
    assert out["results"][0]["receipt"] == str(tmp_path / "spec.json.receipt.json")


def test_validate_spec_writes_receipt(tmp_path, capsys):
    spec = _spec_copy(tmp_path)
    assert main(["validate", "spec", str(spec)]) == 0
    capsys.readouterr()
    written = json.loads((tmp_path / "spec.json.receipt.json").read_text(encoding="utf-8"))
    assert validate("spec-receipt", written) == []
    assert written["spec_sha256"] == hashlib.sha256(spec.read_bytes()).hexdigest()
    assert written["spec_file"] == "spec.json"
    example = json.loads((EXAMPLES / "spec-receipt.example.json").read_text(encoding="utf-8"))
    assert written["spec_sha256"] == example["spec_sha256"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["spec.json", "spec.json.receipt.json"]


def test_validate_other_schema_writes_no_receipt(tmp_path, capsys):
    path = _write(tmp_path, (EXAMPLES / "read-log.example.json").read_bytes(), "log.json")
    assert main(["validate", "read-log", str(path)]) == 0
    result = json.loads(capsys.readouterr().out)["results"][0]
    assert "receipt" not in result
    assert [p.name for p in tmp_path.iterdir()] == ["log.json"]


def test_stale_receipt_removed_when_spec_becomes_invalid(tmp_path, capsys):
    spec = _spec_copy(tmp_path)
    assert main(["validate", "spec", str(spec)]) == 0
    assert (tmp_path / "spec.json.receipt.json").is_file()
    spec.write_text('{"schema_version": "0.1"}', encoding="utf-8")
    capsys.readouterr()
    assert main(["validate", "spec", str(spec)]) == 1
    result = json.loads(capsys.readouterr().out)["results"][0]
    assert result["valid"] is False and result["receipt"] is None
    assert not (tmp_path / "spec.json.receipt.json").exists()


def test_stale_receipt_removed_when_spec_is_missing(tmp_path, capsys):
    stale = tmp_path / "gone.json.receipt.json"
    stale.write_text("{}", encoding="utf-8")
    assert main(["validate", "spec", str(tmp_path / "gone.json")]) == 1
    assert not stale.exists()


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        ("nan", lambda t: t.replace('"lot": 1', '"lot": NaN', 1)),
        ("duplicate lot", lambda t: t.replace('"lot": 1,', '"lot": 1, "lot": 1,', 1)),
        ("float lot", lambda t: t.replace('"lot": 1', '"lot": 1.0', 1)),
        ("lot above int32", lambda t: t.replace('"lot": 1', '"lot": 2147483648', 1)),
        ("lot above 2^53", lambda t: t.replace('"lot": 1', '"lot": 9007199254740993', 1)),
        ("bom", lambda t: "\ufeff" + t),
    ],
)
def test_strict_failures_get_no_receipt(tmp_path, capsys, label, mutate):
    text = _example_text()
    mutated = mutate(text)
    assert mutated != text, label
    spec = _write(tmp_path, mutated.encode("utf-8"))
    assert main(["validate", "spec", str(spec)]) == 1
    result = json.loads(capsys.readouterr().out)["results"][0]
    assert result["valid"] is False and result["errors"] and result["receipt"] is None
    assert [p.name for p in tmp_path.iterdir()] == ["spec.json"]


def test_lot_int32_boundary_is_accepted(tmp_path, capsys):
    spec = _write(tmp_path, _example_text().replace('"lot": 1', '"lot": 2147483647', 1).encode())
    assert main(["validate", "spec", str(spec)]) == 0


def test_invalid_utf8_gets_no_receipt(tmp_path, capsys):
    spec = _write(tmp_path, b'{"a":"\xff"}')
    assert main(["validate", "spec", str(spec)]) == 1
    assert not (tmp_path / "spec.json.receipt.json").exists()


def test_oversize_file_refused(tmp_path, capsys):
    spec = _write(tmp_path, b" " * (16 * 1024 * 1024 + 1))
    assert main(["validate", "spec", str(spec)]) == 1
    assert "16 MiB" in json.loads(capsys.readouterr().out)["results"][0]["errors"][0]["message"]


def test_multiple_files_mixed(tmp_path, capsys):
    good = _spec_copy(tmp_path, "good.json")
    bad = _write(tmp_path, b'{"schema_version": "0.1"}', "bad.json")
    assert main(["validate", "spec", str(good), str(bad)]) == 1
    results = json.loads(capsys.readouterr().out)["results"]
    assert [r["valid"] for r in results] == [True, False]
    assert (tmp_path / "good.json.receipt.json").is_file()
    assert not (tmp_path / "bad.json.receipt.json").exists()


def test_two_valid_files_get_own_receipts(tmp_path, capsys):
    a, b = _spec_copy(tmp_path, "a.json"), _spec_copy(tmp_path, "b.json")
    assert main(["validate", "spec", str(a), str(b)]) == 0
    assert (tmp_path / "a.json.receipt.json").is_file() and (tmp_path / "b.json.receipt.json").is_file()


def test_undeletable_stale_receipt_exits_3(tmp_path, capsys):
    spec = _spec_copy(tmp_path)
    stuck = tmp_path / "spec.json.receipt.json"
    stuck.mkdir()
    (stuck / "keep").write_text("x", encoding="utf-8")
    assert main(["validate", "spec", str(spec)]) == 3
    result = json.loads(capsys.readouterr().out)["results"][0]
    assert result["valid"] is False and result["receipt"] is None
    assert "receipt" in result["errors"][0]["message"]


def test_receipt_write_failure_exits_3(tmp_path, capsys, monkeypatch):
    spec = _spec_copy(tmp_path)

    def boom(*_a, **_k):
        raise OSError("disk says no")

    monkeypatch.setattr(os, "replace", boom)
    assert main(["validate", "spec", str(spec)]) == 3
    result = json.loads(capsys.readouterr().out)["results"][0]
    assert result["receipt"] is None and "disk says no" in result["errors"][0]["message"]
    assert [p.name for p in tmp_path.iterdir()] == ["spec.json"]


def test_env_error_wins_over_invalid(tmp_path, capsys):
    stuck = tmp_path / "a.json.receipt.json"
    stuck.mkdir()
    (stuck / "keep").write_text("x", encoding="utf-8")
    a = _spec_copy(tmp_path, "a.json")
    bad = _write(tmp_path, b"{}", "bad.json")
    assert main(["validate", "spec", str(a), str(bad)]) == 3


def test_validate_invalid_exit_1(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema_version": "0.1"}', encoding="utf-8")
    assert main(["validate", "spec", str(bad)]) == 1
    assert json.loads(capsys.readouterr().out)["results"][0]["errors"]


def test_unreadable_file_is_invalid(tmp_path, capsys):
    assert main(["validate", "read-log", str(tmp_path / "missing.json")]) == 1


def test_usage_error_exit_2(capsys):
    assert main(["validate", "nope", "x.json"]) == 2


def test_schema_names_include_the_wave2_schemas(capsys):
    for name in ("dimensions", "supplements"):
        assert main(["validate", name, str(EXAMPLES / f"{name}.example.json")]) == 0
    capsys.readouterr()


# --- tool wave 2 seam: flags and stubs (the packages implement them) ---------------------------


def test_dimensions_is_registered(tmp_path, capsys):
    # package P4 implemented it (tests/test_dimensions.py): a folder without inventory is a usage error
    assert main(["dimensions", str(tmp_path), "a.dxf"]) == 2
    assert "inventory.json" in capsys.readouterr().err


def test_dimensions_sheet_and_unassigned_exclude_each_other(tmp_path, capsys):
    assert main(["dimensions", str(tmp_path), "a.dxf", "--sheet", "model#01", "--unassigned"]) == 2


def test_sheet_text_needs_a_sheet_or_unassigned_not_both(tmp_path, capsys):
    assert main(["sheet-text", str(tmp_path), "a.dxf"]) == 2
    assert main(["sheet-text", str(tmp_path), "a.dxf", "model#01", "--unassigned"]) == 2
    err = capsys.readouterr().err
    assert "--unassigned" in err


def test_sheet_text_and_find_text_unassigned_reach_the_reader(tmp_path, capsys):
    # implemented by package P1 (tests in test_sheet_text); an empty folder is now a usage error
    assert main(["sheet-text", str(tmp_path), "a.dxf", "--unassigned"]) == 2
    assert main(["find-text", str(tmp_path), "--contains", "x", "--unassigned"]) == 2
    assert "not implemented yet" not in capsys.readouterr().err


def test_answer_role_must_be_known(tmp_path, capsys):
    argv = ["answer", str(tmp_path), "Q-001", "--text", "x", "--by", "me", "--role", "agent"]
    assert main(argv) == 2


def test_answer_without_a_role_is_a_usage_error(tmp_path, capsys):
    assert main(["answer", str(tmp_path), "Q-001", "--text", "x", "--by", "me"]) == 2
    assert "the following arguments are required: --role" in capsys.readouterr().err  # argparse refuses


def test_ask_supplement_without_a_registry_is_a_usage_error(tmp_path, capsys):
    argv = ["ask", str(tmp_path), "--supplement", "Q-001", "--where", "w", "--found", "", "--text", "t"]
    assert main(argv) == 2
    assert main(["ask", str(tmp_path), "--withdraw-supplement", "0123456789abcdef", "--reason", "r"]) == 2
    assert "not implemented" not in capsys.readouterr().err


def test_ask_supplement_refuses_code_and_blocking(tmp_path, capsys):
    base = ["ask", str(tmp_path), "--supplement", "Q-001", "--where", "w", "--found", "", "--text", "t"]
    assert main([*base, "--code", "my_code"]) == 2
    assert main([*base, "--blocking"]) == 2
    assert main(["ask", str(tmp_path), "--supplement", "Q-001", "--found", "", "--text", "t"]) == 2
    assert main(["ask", str(tmp_path), "--withdraw-supplement", "0123456789abcdef"]) == 2
    assert "--supplement" in capsys.readouterr().err


# --- tool wave 3 seam: flags and stubs (packages C and T implement them) -----------------------


def test_validate_reader_questions(capsys):
    assert main(["validate", "reader-questions", str(EXAMPLES / "reader-questions.example.json")]) == 0
    # a producer's document is a valid intake document, but not a reader one (several refs per question)
    assert main(["validate", "intake", str(EXAMPLES / "intake-questions.example.json")]) == 0
    assert main(["validate", "reader-questions", str(EXAMPLES / "intake-questions.example.json")]) == 1
    assert main(["validate", "reader-questions", str(EXAMPLES / "answers.example.json")]) == 1
    capsys.readouterr()


def test_ask_amend_is_implemented_and_needs_a_work_folder(tmp_path, capsys):
    # package C replaced the seam stub (exit 3): a folder without a registry is a usage error
    # (the behaviour itself: tests/test_ask.py)
    assert main(["ask", str(tmp_path), "--amend", "Q-001", "--text", "câu hỏi mới"]) == 2
    assert main(["ask", str(tmp_path), "--amend", "Q-001", "--places", "model#05 axis 3", "model#07"]) == 2
    err = capsys.readouterr().err
    assert "not implemented" not in err and "question-registry.json" in err and "Traceback" not in err


@pytest.mark.parametrize(
    "extra",
    [
        [],  # nothing to amend
        ["--text", "t", "--code", "reader_x"],
        ["--text", "t", "--where", "w"],
        ["--text", "t", "--found", "f"],
        ["--text", "t", "--blocking"],
        ["--text", "t", "--reason", "r"],
        ["--text", "t", "--file", "a.dxf"],
        ["--text", "t", "--sheet", "model#01"],
        ["--text", "t", "--withdraw", "Q-002"],
        ["--text", "t", "--supplement", "Q-002"],
        ["--text", " "],
        ["--places", " "],
    ],
)
def test_ask_amend_usage_errors(tmp_path, capsys, extra):
    assert main(["ask", str(tmp_path), "--amend", "Q-001", *extra]) == 2
    assert "not implemented" not in capsys.readouterr().err


def test_ask_places_only_with_amend(tmp_path, capsys):
    argv = ["ask", str(tmp_path), "--code", "reader_x", "--where", "w", "--found", "f", "--text", "t"]
    assert main([*argv, "--places", "model#05"]) == 2
    assert "--places" in capsys.readouterr().err


def test_sheet_text_region_reaches_the_reader(tmp_path, capsys):
    # package T implemented the seam stub: an empty folder is now a usage error from the reader
    argv = ["sheet-text", str(tmp_path), "a.dxf", "model#01", "--region", "60000,54000,70000,57000.5"]
    assert main(argv) == 2
    err = capsys.readouterr().err
    assert "inventory.json" in err and "not implemented" not in err and "Traceback" not in err


def test_sheet_text_region_takes_negative_model_coordinates_with_equals(tmp_path, capsys):
    # model-space boxes are often negative (286's rebar table sits near y -177151); argparse reads a
    # value starting with '-' after a space as an option, so the help names the '=' form
    argv = ["sheet-text", str(tmp_path), "a.dxf", "model#01", "--region=-5000,-178000,0,-176000"]
    assert main(argv) == 2
    assert "inventory.json" in capsys.readouterr().err
    assert main(["sheet-text", "--help"]) == 0
    assert "--region=-5000" in " ".join(capsys.readouterr().out.split())


@pytest.mark.parametrize(
    "region",
    ["1,2,3", "1,2,3,4,5", "a,2,3,4", "5,0,1,4", "0,5,4,1", "0,0,0,4", "nan,0,1,1", "0,0,inf,1"],
)
def test_sheet_text_region_must_be_a_box(tmp_path, capsys, region):
    assert main(["sheet-text", str(tmp_path), "a.dxf", "model#01", "--region", region]) == 2
    assert "--region" in capsys.readouterr().err


def test_sheet_text_region_needs_a_sheet_and_no_unassigned(tmp_path, capsys):
    assert main(["sheet-text", str(tmp_path), "a.dxf", "--region", "0,0,1,1"]) == 2
    assert main(["sheet-text", str(tmp_path), "a.dxf", "--unassigned", "--region", "0,0,1,1"]) == 2
    both = ["sheet-text", str(tmp_path), "a.dxf", "model#01", "--unassigned", "--region", "0,0,1,1"]
    assert main(both) == 2
    assert "not implemented" not in capsys.readouterr().err


@pytest.mark.parametrize(
    ("field", "says"),
    [("blocked_in_scope", "never matched"), ("blocked_entries_not_searchable", "stored text only")],
)
def test_find_text_reports_the_blocked_entries_in_scope(tmp_path, capsys, monkeypatch, field, says):
    # W4: package T emits blocked_in_scope and never matches a blocked entry; until then the old count
    # keeps its old warning
    from tekla_harness import cli

    doc = json.loads((EXAMPLES / "find-text.example.json").read_text(encoding="utf-8"))
    counts = doc["counts"]
    del counts["blocked_entries_not_searchable"]
    counts[field] = 7
    monkeypatch.setattr(cli, "find_text", lambda *args, **kwargs: doc)
    assert main(["find-text", str(tmp_path), "--contains", "x"]) == 0
    err = capsys.readouterr().err
    assert "7 blocked" in err and says in err


def test_answer_help_names_the_grid_system_missing_keys(capsys):
    assert main(["answer", "--help"]) == 0
    text = " ".join(capsys.readouterr().out.split())
    for key in ("dir1_labels", "dir1_spacings", "dir2_labels", "dir2_spacings", "sheet="):
        assert key in text
    assert "grid_answer_contradicts_drawing" in text
    assert "no_grid=yes" in text and "alone" in text  # ADR-0013 decision 2


def test_env_check_outputs_json(capsys):
    code = main(["env-check"])
    out = json.loads(capsys.readouterr().out)
    assert code in (0, 3)
    assert out["report"][0].startswith("Environment report")
