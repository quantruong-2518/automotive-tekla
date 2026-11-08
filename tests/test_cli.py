from __future__ import annotations

import json

from conftest import EXAMPLES
from tekla_harness.cli import main


def test_validate_ok(capsys):
    assert main(["validate", "spec", str(EXAMPLES / "spec.example.json")]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["results"][0]["valid"] is True


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


def test_env_check_outputs_json(capsys):
    code = main(["env-check"])
    out = json.loads(capsys.readouterr().out)
    assert code in (0, 3)
    assert out["report"][0].startswith("Environment report")
