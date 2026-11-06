"""read-log builder: every entry it writes must validate against schemas/read-log.schema.json."""

from __future__ import annotations

import json

import pytest

from tekla_harness.readlog import ReadLog, ReadLogError, timed_attempt
from tekla_harness.schemas import validate

SHA = "0" * 64


def test_written_log_validates(tmp_path):
    log = ReadLog("demo-warehouse")
    with timed_attempt("oda_file_converter") as failed:
        failed.fail("converter not installed")
    with timed_attempt("libredwg_dwg2dxf", tool_version="0.13") as ok:
        pass
    log.add_file("S-101.dwg", SHA, "dwg", [failed, ok], outcome="read", max_confidence="medium")
    out = tmp_path / "read-log.json"
    log.write(out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert validate("read-log", data) == []
    attempts = data["files"][0]["attempts"]
    assert attempts[0]["status"] == "failed" and attempts[0]["error"] == "converter not installed"
    assert attempts[1]["status"] == "ok" and "error" not in attempts[1]
    assert attempts[1]["duration_ms"] >= 0


def test_exception_inside_attempt_is_recorded_and_reraised():
    with pytest.raises(RuntimeError), timed_attempt("ezdxf") as attempt:
        raise RuntimeError("boom")
    assert attempt.status == "failed"
    assert "boom" in (attempt.error or "")


def test_failed_attempt_needs_an_error():
    with timed_attempt("ezdxf") as attempt:
        attempt.status = "failed"  # no error text: must not be written silently
    log = ReadLog("demo-warehouse")
    with pytest.raises(ReadLogError):
        log.add_file("a.dxf", SHA, "dxf", [attempt], outcome="unreadable")


def test_entry_without_attempts_is_rejected():
    with pytest.raises(ReadLogError):
        ReadLog("demo-warehouse").add_file("a.dxf", SHA, "dxf", [], outcome="read")


def test_invalid_log_is_not_written(tmp_path):
    log = ReadLog("Not A Valid Id")
    with timed_attempt("ezdxf") as ok:
        pass
    log.add_file("a.dxf", SHA, "dxf", [ok], outcome="read")
    out = tmp_path / "read-log.json"
    with pytest.raises(ReadLogError):
        log.write(out)
    assert not out.exists()


def test_same_file_twice_is_rejected():
    log = ReadLog("demo-warehouse")
    with timed_attempt("ezdxf") as ok:
        pass
    log.add_file("a.dxf", SHA, "dxf", [ok], outcome="read")
    with pytest.raises(ReadLogError):
        log.add_file("a.dxf", SHA, "dxf", [ok], outcome="read")
