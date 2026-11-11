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
    assert line == "[main] opus-xhigh · ● 167k/1M fresh"
    payload = main_payload(5000)
    payload["context_window"]["context_window_size"] = 200_000
    assert "5k/200k" in sl.render_main(payload)


def test_main_missing_effort_and_branch(sl):
    payload = main_payload()
    del payload["effort"]
    payload["worktree"] = {"branch": "feat/x"}
    line = ANSI.sub("", sl.render_main(payload))
    assert line == "[main] opus-- · ● 167k/1M fresh · feat/x"


def test_main_null_tokens_uncoloured(sl):
    for value in (None, "missing"):
        payload = main_payload(value)
        if value == "missing":
            del payload["context_window"]["total_input_tokens"]
        line = sl.render_main(payload)
        assert not {GREEN, YELLOW, RED} & set(ANSI.findall(line))
        assert ANSI.sub("", line) == "[main] opus-xhigh · \u2013/1M"


def test_missing_guard_module_is_uncoloured(sl, monkeypatch, tmp_path):
    monkeypatch.setattr(sl, "GUARD_PATH", tmp_path / "absent.py")
    main = sl.render_main(main_payload(300_000))
    assert not {GREEN, YELLOW, RED} & set(ANSI.findall(main))
    (row,) = rows(sl, [task(300_000)])
    assert not {GREEN, YELLOW, RED} & set(ANSI.findall(row["content"]))  # agent colour stays
    assert " · 300k · " in ANSI.sub("", row["content"])
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
    assert ANSI.sub("", row["content"]) == "executor sonnet5.5-high · ● 50k fresh · $2 · do work"


def test_subagent_fallback_names_and_missing_fields(sl):
    t = task(agentType=None, name="alice")
    del t["effort"]
    del t["model"]
    (row,) = rows(sl, [t])
    assert ANSI.sub("", row["content"]).startswith("alice --")
    t2 = task()
    del t2["agentType"]
    (row2,) = rows(sl, [t2])
    assert ANSI.sub("", row2["content"]).startswith("local_agent sonnet5.5-high")


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
    assert " sonnet5.5-3 · " in ANSI.sub("", row["content"])


def test_subagent_agent_colours_differ_and_avoid_freshness_colours(sl):
    names = ["executor", "doc-reader", "planner", "builder", "verifier", "reporter", "general-purpose"]
    colours = {sl.AGENT_COLOURS[n] for n in names}
    assert len(colours) == len(names)
    assert not {GREEN, YELLOW, RED} & {c.replace("1;", "") for c in colours}
    (row,) = rows(sl, [task(agentType="executor")])
    assert row["content"].startswith(f"{sl.AGENT_COLOURS['executor']}executor{RESET}")
    (other,) = rows(sl, [task(agentType="mystery")])
    assert other["content"].startswith(f"{sl.DEFAULT_AGENT_COLOUR}mystery{RESET}")


@pytest.mark.parametrize(
    ("model", "effort", "text"),
    [
        ("claude-sonnet-5-5", "medium", "sonnet5.5-med · ● 1k fresh · $2"),
        ("claude-opus-5-5", "high", "opus5.5-high · ● 1k fresh · $4"),
        ("claude-haiku-5-5", "low", "haiku5.5-low · ● 1k fresh · $0.1"),
        ("claude-future-9", "high", "future9-high · ● 1k fresh"),
    ],
)
def test_subagent_model_effort_and_price(sl, model, effort, text):
    (row,) = rows(sl, [task(1_000, model=model, effort=effort, description="")])
    assert ANSI.sub("", row["content"]).endswith(text)


def test_prices_share_one_colour_and_are_not_freshness_colours(sl):
    assert sl.PRICE_COLOUR not in {GREEN, YELLOW, RED, *sl.AGENT_COLOURS.values()}
    (row,) = rows(sl, [task()])
    assert f"{sl.PRICE_COLOUR}$2{RESET}" in row["content"]
    line = sl.render_main(main_payload(cost={"total_cost_usd": 4.2149}))
    assert f"{sl.PRICE_COLOUR}$4.21{RESET}" in line


def test_main_line_has_no_time_and_subagent_rows_have_no_time(sl):
    payload = main_payload(cost={"total_cost_usd": 1, "total_duration_ms": 4_800_000})
    assert "1h20m" not in ANSI.sub("", sl.render_main(payload))
    (row,) = rows(sl, [task(startTime=1_000_000_000_000)])
    assert re.search(r"\d+[smh]\b", ANSI.sub("", row["content"])) is None


def test_main_line_cost_limit_and_fast_mode(sl):
    payload = main_payload(
        93_000,
        model={"display_name": "Opus 5.5"},
        cost={"total_cost_usd": 4.2149},
        rate_limits={"five_hour": {"used_percentage": 7.2}, "seven_day": {"used_percentage": 46}},
        fast_mode=True,
    )
    line = ANSI.sub("", sl.render_main(payload))
    assert line == "[main] opus5.5\u26a1-xhigh · ● 93k/1M fresh · $4.21 · limit 7%|46%"


def test_main_worktree_tag(sl):
    assert ANSI.sub("", sl.render_main(main_payload())).startswith("[main] opus")
    linked = main_payload(worktree={"name": "w4-fp2"})
    assert ANSI.sub("", sl.render_main(linked)).startswith("[w4-fp2] opus")
    git_only = main_payload(workspace={"git_worktree": "executor-agent"})
    assert ANSI.sub("", sl.render_main(git_only)).startswith("[executor-agent] opus")


@pytest.mark.parametrize(
    ("used", "colour"), [(69, ""), (69.6, YELLOW), (70, YELLOW), (89, YELLOW), (90, RED), (100, RED)]
)
def test_main_rate_limit_colours(sl, used, colour):
    payload = main_payload(rate_limits={"seven_day": {"used_percentage": used}})
    line = sl.render_main(payload)
    label = f"{round(used)}%"
    assert (f"{colour}{label}{RESET}" if colour else f"limit {label}") in line


def test_main_line_skips_absent_or_malformed_extras(sl):
    payload = main_payload(
        cost={"total_cost_usd": "x"},
        rate_limits={"five_hour": {"used_percentage": True}, "seven_day": "no"},
        fast_mode="yes",
    )
    assert ANSI.sub("", sl.render_main(payload)) == "[main] opus-xhigh · ● 167k/1M fresh"
