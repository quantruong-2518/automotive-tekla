"""Build `read-log.json`: every read attempt for every input file. Nothing fails silently.

Usage:
    with timed_attempt("ezdxf") as attempt:
        doc = ezdxf.readfile(path)      # an exception marks the attempt failed and re-raises
    log.add_file(rel_path, sha, "dxf", [attempt], outcome="read", max_confidence="high")
    log.write(path)                     # validates against the schema first
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from tekla_harness.schemas import validate

SCHEMA_VERSION = "0.1"


class ReadLogError(ValueError):
    """The log would be incomplete or invalid; it is never written in that state."""


@dataclass
class Attempt:
    tool: str
    started_at: str
    status: str = "ok"
    duration_ms: int = 0
    error: str | None = None
    tool_version: str | None = None

    def fail(self, error: str, status: str = "failed") -> None:
        self.status, self.error = status, error

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"tool": self.tool, "status": self.status, "started_at": self.started_at}
        if self.tool_version:
            out["tool_version"] = self.tool_version
        out["duration_ms"] = self.duration_ms
        if self.error is not None:
            out["error"] = self.error
        return out


@contextmanager
def timed_attempt(tool: str, tool_version: str | None = None) -> Iterator[Attempt]:
    attempt = Attempt(tool, datetime.now().astimezone().isoformat(timespec="seconds"))
    attempt.tool_version = tool_version
    start = time.perf_counter()
    try:
        yield attempt
    except Exception as exc:
        attempt.fail(f"{type(exc).__name__}: {exc}")
        raise
    finally:
        attempt.duration_ms = int((time.perf_counter() - start) * 1000)


@dataclass
class ReadLog:
    project_id: str
    files: list[dict[str, Any]] = field(default_factory=list)

    def add_file(
        self,
        file: str,
        sha256: str,
        fmt: str,
        attempts: list[Attempt],
        outcome: str,
        max_confidence: str | None = None,
        encoding: str | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        if not attempts:
            raise ReadLogError(f"{file}: a file entry needs at least one attempt")
        silent = [a.tool for a in attempts if a.status != "ok" and not a.error]
        if silent:
            raise ReadLogError(f"{file}: attempts {silent} failed without an error message")
        if any(f["file"] == file for f in self.files):
            raise ReadLogError(f"{file}: already in the read log")
        entry: dict[str, Any] = {
            "file": file,
            "sha256": sha256,
            "format": fmt,
            "attempts": [a.as_dict() for a in attempts],
            "outcome": outcome,
        }
        if encoding:
            entry["encoding"] = encoding
        if max_confidence:
            entry["max_confidence"] = max_confidence
        if warnings:
            entry["warnings"] = list(warnings)
        self.files.append(entry)

    def as_dict(self) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, "project_id": self.project_id, "files": self.files}

    def write(self, path: Path) -> None:
        data = self.as_dict()
        problems = validate("read-log", data)
        if problems:
            details = "; ".join(f"{p.path or '/'}: {p.message}" for p in problems)
            raise ReadLogError(f"read log is invalid, not written: {details}")
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
