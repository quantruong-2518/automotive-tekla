"""Statusline script: main session line and per-subagent rows, coloured by context freshness."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from conftest import HOOKS, LEGACY_CONSOLE_ENV, load_hook

GREEN, YELLOW, RED, RESET = "\033[32m", "\033[33m", "\033[31m", "\033[0m"
ANSI = re.compile(r"\033\[[0-9;]*m")
BOUNDARIES = [
    (199_999, GREEN, "fresh"),
    (200_000, YELLOW, "warn"),
    (249_999, YELLOW, "warn"),
    (250_000, RED, "handoff"),
]


@pytest.fixture
def sl():
    return load_hook("statusline")


def main_payload(tokens: Any = 167_000, **extra: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "model": {"display_name": "Opus"},
        "effort": {"level": "xhigh"},
        "context_window": {"total_input_tokens": tokens, "context_window_size": 1_000_000},
    }
    data.update(extra)
    return data


def task(tokens: int = 50_000, **extra: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": "t1",
        "type": "local_agent",
        "agentType": "executor",
        "status": "running",
        "description": "do work",
        "label": "x",
        "model": "claude-sonnet-5-5",
        "effort": "high",
        "tokenCount": tokens,
    }
    data.update(extra)
    return data


def rows(sl, tasks: list[dict[str, Any]], columns: int = 120) -> list[dict[str, Any]]:
    return [json.loads(x) for x in sl.render_subagents({"columns": columns, "tasks": tasks})]


@pytest.mark.parametrize(("tokens", "colour", "label"), BOUNDARIES)
def test_main_colour_boundaries(sl, tokens, colour, label):
    line = sl.render_main(main_payload(tokens))
    assert f"{colour}● {tokens // 1000}k/1M {label}{RESET}" in line


@pytest.mark.parametrize(("tokens", "colour", "label"), BOUNDARIES)
def test_subagent_colour_boundaries(sl, tokens, colour, label):
    (row,) = rows(sl, [task(tokens)])
    assert f"{colour}● {tokens // 1000}k {label}{RESET}" in row["content"]


def test_main_line_layout_and_window(sl):
    line = ANSI.sub("", sl.render_main(main_payload(167_000)))
    assert line == "Opus · xhigh · ● 167k/1M fresh"
    payload = main_payload(5000)
    payload["context_window"]["context_window_size"] = 200_000
    assert "5k/200k" in sl.render_main(payload)


def test_main_missing_effort_and_branch(sl):
    payload = main_payload()
    del payload["effort"]
    payload["worktree"] = {"branch": "feat/x"}
    line = ANSI.sub("", sl.render_main(payload))
    assert line == "Opus · - · ● 167k/1M fresh · feat/x"


def test_main_null_tokens_uncoloured(sl):
    for value in (None, "missing"):
        payload = main_payload(value)
        if value == "missing":
            del payload["context_window"]["total_input_tokens"]
        line = sl.render_main(payload)
        assert "\033" not in line
        assert line == "Opus · xhigh · \u2013/1M"


def test_missing_guard_module_is_uncoloured(sl, monkeypatch, tmp_path):
    monkeypatch.setattr(sl, "GUARD_PATH", tmp_path / "absent.py")
    assert "\033" not in sl.render_main(main_payload(300_000))
    (row,) = rows(sl, [task(300_000)])
    assert "\033" not in row["content"]
    assert "300k" in row["content"]


def test_thresholds_come_from_loaded_module(sl, monkeypatch, tmp_path):
    fake = tmp_path / "fake_guard.py"
    fake.write_text("WARN_TOKENS = 10\nHANDOFF_TOKENS = 20\n", encoding="utf-8")
    monkeypatch.setattr(sl, "GUARD_PATH", fake)
    assert GREEN in sl.render_main(main_payload(9))
    assert YELLOW in sl.render_main(main_payload(10))
    assert RED in sl.render_main(main_payload(20))
    assert sl.load_thresholds() == (10, 20)


def test_subagent_model_shortening_and_row(sl):
    (row,) = rows(sl, [task(50_000)])
    assert row["id"] == "t1"
    assert ANSI.sub("", row["content"]) == "executor · sonnet-5-5 · high · ● 50k fresh · do work"


def test_subagent_fallback_names_and_missing_fields(sl):
    t = task(agentType=None, name="alice")
    del t["effort"]
    del t["model"]
    (row,) = rows(sl, [t])
    assert ANSI.sub("", row["content"]).startswith("alice · - · - · ")
    t2 = task()
    del t2["agentType"]
    (row2,) = rows(sl, [t2])
    assert ANSI.sub("", row2["content"]).startswith("local_agent · ")


def test_truncation_counts_visible_chars_only(sl):
    (row,) = rows(sl, [task(description="d" * 300)], columns=40)
    visible = ANSI.sub("", row["content"])
    assert len(visible) == 40
    assert visible.endswith("…")
    assert GREEN in row["content"]


def test_no_truncation_when_it_fits(sl):
    (row,) = rows(sl, [task()], columns=500)
    assert "…" not in row["content"]


def test_non_running_task_still_rendered(sl):
    out = rows(sl, [task(id="a", status="completed"), task(id="b")])
    assert [r["id"] for r in out] == ["a", "b"]


@pytest.mark.parametrize("raw", ["", "not json", "[]", "null", '{"tasks": "x"}', '{"tasks": [1]}'])
def test_malformed_stdin_prints_nothing(sl, raw, capsys, monkeypatch):
    for argv in ([], ["--subagents"]):
        monkeypatch.setattr(sys, "stdin", __import__("io").StringIO(raw))
        assert sl.main(argv) == 0
        assert capsys.readouterr().out == ""


def run(payload: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HOOKS / "statusline.py"), *args],
        input=payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, **LEGACY_CONSOLE_ENV},
        timeout=30,
        check=False,
    )


def test_end_to_end_main():
    proc = run(json.dumps(main_payload(250_000)))
    assert proc.returncode == 0
    assert proc.stderr == ""
    assert proc.stdout.count("\n") == 1
    assert f"{RED}● 250k/1M handoff{RESET}" in proc.stdout


def test_end_to_end_subagents():
    payload = {"columns": 100, "tasks": [task(200_000), task(id="t2", status="completed")]}
    proc = run(json.dumps(payload), "--subagents")
    assert proc.returncode == 0
    assert proc.stderr == ""
    lines = [json.loads(x) for x in proc.stdout.splitlines()]
    assert [x["id"] for x in lines] == ["t1", "t2"]
    assert YELLOW in lines[0]["content"]


def test_end_to_end_subagents_non_ascii_input_survives_a_legacy_console():
    payload = {"columns": 100, "tasks": [task(200_000, description="tên \u1ebf")]}
    proc = run(json.dumps(payload, ensure_ascii=False), "--subagents")
    assert proc.stderr == ""
    assert "tên \u1ebf" in json.loads(proc.stdout)["content"]


def test_end_to_end_malformed():
    for args in ((), ("--subagents",)):
        proc = run("{{{", *args)
        assert (proc.returncode, proc.stdout, proc.stderr) == (0, "", "")


def test_file_is_where_expected():
    assert Path(HOOKS / "statusline.py").is_file()


def test_subagent_numeric_effort_is_shown(sl):
    (row,) = rows(sl, [task(effort=3)])
    assert " · 3 · " in ANSI.sub("", row["content"])
