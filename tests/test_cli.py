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


def test_env_check_outputs_json(capsys):
    code = main(["env-check"])
    out = json.loads(capsys.readouterr().out)
    assert code in (0, 3)
    assert out["report"][0].startswith("Environment report")
