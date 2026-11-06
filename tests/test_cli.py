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


def test_env_check_outputs_json(capsys):
    code = main(["env-check"])
    out = json.loads(capsys.readouterr().out)
    assert code in (0, 3)
    assert out["report"][0].startswith("Environment report")
