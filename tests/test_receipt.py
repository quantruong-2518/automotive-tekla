from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from conftest import EXAMPLES
from tekla_harness import __version__, receipt
from tekla_harness.receipt import SPEC_RULES_VERSION, build_receipt, receipt_path, write_receipt
from tekla_harness.schemas import validate

SPEC = EXAMPLES / "spec.example.json"
FIXED = datetime(2026, 11, 7, 9, 0, 0, 123456, tzinfo=UTC)


def _spec_copy(tmp_path: Path) -> Path:
    copy = tmp_path / "spec.json"
    copy.write_bytes(SPEC.read_bytes())
    return copy


def test_receipt_path_is_next_to_spec():
    assert receipt_path(Path("/a/b/spec.json")) == Path("/a/b/spec.json.receipt.json")


def test_build_receipt_fields():
    data = SPEC.read_bytes()
    built = build_receipt(data, "spec.json", now=lambda: FIXED)
    assert built == {
        "schema_version": "0.1",
        "spec_file": "spec.json",
        "spec_sha256": hashlib.sha256(data).hexdigest(),
        "spec_schema_id": receipt._spec_schema_id(),
        "validator": {"name": "tekla_harness", "version": __version__, "rules_version": SPEC_RULES_VERSION},
        "validated_at": "2026-11-07T09:00:00Z",
    }
    assert validate("spec-receipt", built) == []


def test_clock_is_converted_to_utc():
    from datetime import timedelta, timezone

    local = datetime(2026, 11, 7, 16, 0, 0, tzinfo=timezone(timedelta(hours=7)))
    assert build_receipt(b"{}", "s.json", now=lambda: local)["validated_at"] == "2026-11-07T09:00:00Z"


def test_default_clock_format():
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", build_receipt(b"{}", "s.json")["validated_at"])


def test_write_receipt_file_format(tmp_path):
    spec = _spec_copy(tmp_path)
    out = write_receipt(spec, spec.read_bytes(), now=lambda: FIXED)
    assert out == tmp_path / "spec.json.receipt.json"
    raw = out.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw and raw.endswith(b"\n")
    assert validate("spec-receipt", json.loads(raw)) == []
    assert sorted(p.name for p in tmp_path.iterdir()) == ["spec.json", "spec.json.receipt.json"]


def test_write_receipt_replaces_existing(tmp_path):
    spec = _spec_copy(tmp_path)
    receipt_path(spec).write_text("old", encoding="utf-8")
    write_receipt(spec, spec.read_bytes())
    assert json.loads(receipt_path(spec).read_text(encoding="utf-8"))["spec_file"] == "spec.json"


def test_failed_replace_leaves_no_temp_file_and_no_receipt(tmp_path, monkeypatch):
    spec = _spec_copy(tmp_path)

    def boom(*_a, **_k):
        raise OSError("disk says no")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError, match="disk says no"):
        write_receipt(spec, spec.read_bytes())
    assert [p.name for p in tmp_path.iterdir()] == ["spec.json"]


def test_receipt_failing_its_own_schema_is_not_written(tmp_path, monkeypatch):
    spec = _spec_copy(tmp_path)
    monkeypatch.setattr(receipt, "SPEC_RULES_VERSION", 0)
    with pytest.raises(receipt.ReceiptError):
        write_receipt(spec, spec.read_bytes())
    assert [p.name for p in tmp_path.iterdir()] == ["spec.json"]


def test_example_receipt_hash_matches_spec_example():
    """Cross-language anchor: the C# tests read the same example receipt."""
    expected = json.loads((EXAMPLES / "spec-receipt.example.json").read_text(encoding="utf-8"))
    actual = hashlib.sha256(SPEC.read_bytes()).hexdigest()
    assert actual == expected["spec_sha256"], (
        "schemas/examples/spec.example.json changed: update spec_sha256 in "
        "schemas/examples/spec-receipt.example.json to " + actual
    )


def test_receipt_of_example_matches_example_receipt(tmp_path):
    spec = tmp_path / "spec.example.json"
    spec.write_bytes(SPEC.read_bytes())
    built = json.loads(write_receipt(spec, spec.read_bytes()).read_text(encoding="utf-8"))
    expected = json.loads((EXAMPLES / "spec-receipt.example.json").read_text(encoding="utf-8"))
    assert {k: v for k, v in built.items() if k != "validated_at"} == {
        k: v for k, v in expected.items() if k != "validated_at"
    }


# --- review fixes (ADR-0010 Amendment 1, m1) -------------------------------------------


def test_backslash_file_name_gets_no_receipt_and_no_traceback(tmp_path, capsys):
    import json as _json
    import sys as _sys

    from tekla_harness.cli import main

    if _sys.platform == "win32":
        pytest.skip("a backslash is a path separator on Windows")
    spec = tmp_path / "a\\b.json"
    spec.write_bytes((EXAMPLES / "spec.example.json").read_bytes())
    assert main(["validate", "spec", str(spec)]) == 1
    result = _json.loads(capsys.readouterr().out)["results"][0]
    assert result["valid"] is False and result["receipt"] is None
    assert not receipt.receipt_path(spec).exists()


def test_unreadable_spec_is_an_environment_error(tmp_path, capsys):
    from tekla_harness.cli import main

    folder = tmp_path / "spec.json"
    folder.mkdir()
    assert main(["validate", "spec", str(folder)]) == 3


def test_missing_spec_is_invalid_not_environment(tmp_path, capsys):
    from tekla_harness.cli import main

    assert main(["validate", "spec", str(tmp_path / "missing.json")]) == 1
