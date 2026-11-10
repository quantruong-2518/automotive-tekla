"""Context guard hook: warn at 200k tokens, hand off at 250k (UserPromptSubmit and Stop)."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

from conftest import HOOKS, LEGACY_CONSOLE_ENV, load_hook

SID = "sess-1"


@pytest.fixture
def cg():
    return load_hook("context_guard")


@pytest.fixture(autouse=True)
def tmp_marker_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    return tmp_path / "tmp"


def assistant(total: int, sidechain: bool = False) -> dict[str, Any]:
    return {
        "type": "assistant",
        "isSidechain": sidechain,
        "message": {
            "usage": {
                "input_tokens": 1,
                "cache_creation_input_tokens": total - 1 - 10,
                "cache_read_input_tokens": 10,
                "output_tokens": 999,
            }
        },
    }


def write_transcript(path: Path, entries: list[Any]) -> Path:
    lines = [e if isinstance(e, str) else json.dumps(e) for e in entries]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run_main(cg, monkeypatch, capsys, payload: dict[str, Any]) -> tuple[str, str]:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    cg.main()
    out = capsys.readouterr()
    return out.out, out.err


def ups(tp: Path, **extra: Any) -> dict[str, Any]:
    return {
        "hook_event_name": "UserPromptSubmit",
        "session_id": SID,
        "transcript_path": str(tp),
        **extra,
    }


def stop(tp: Path, **extra: Any) -> dict[str, Any]:
    return {"hook_event_name": "Stop", "session_id": SID, "transcript_path": str(tp), **extra}


def marker(tmp_marker_dir: Path, sid: str = SID) -> Path:
    return tmp_marker_dir / "claude-context-guard" / f"{sid}.handoff"


# ---- token count ----


def test_token_count_sums_input_and_cache_keys(cg, tmp_path):
    tp = write_transcript(tmp_path / "t.jsonl", [assistant(1234)])
    assert cg.token_count(str(tp)) == 1234


def test_missing_usage_keys_count_zero(cg, tmp_path):
    entry = {"type": "assistant", "message": {"usage": {"input_tokens": 7}}}
    tp = write_transcript(tmp_path / "t.jsonl", [entry])
    assert cg.token_count(str(tp)) == 7


def test_sidechain_lines_after_last_main_line_are_ignored(cg, tmp_path):
    tp = write_transcript(tmp_path / "t.jsonl", [assistant(100_000), assistant(300_000, sidechain=True)])
    assert cg.token_count(str(tp)) == 100_000


def test_last_main_line_wins(cg, tmp_path):
    tp = write_transcript(tmp_path / "t.jsonl", [assistant(300_000), assistant(50_000)])
    assert cg.token_count(str(tp)) == 50_000


def test_non_assistant_and_non_dict_usage_are_skipped(cg, tmp_path):
    bad = {"type": "assistant", "message": {"usage": "nope"}}
    user = {"type": "user", "message": {"usage": {"input_tokens": 9}}}
    tp = write_transcript(tmp_path / "t.jsonl", [assistant(5000), bad, user])
    assert cg.token_count(str(tp)) == 5000


def test_malformed_lines_are_skipped(cg, tmp_path):
    tp = write_transcript(tmp_path / "t.jsonl", [assistant(4000), "{not json", "[1,2]"])
    assert cg.token_count(str(tp)) == 4000


def test_missing_transcript_returns_none(cg, tmp_path):
    assert cg.token_count(str(tmp_path / "nope.jsonl")) is None


def test_no_qualifying_line_returns_none(cg, tmp_path):
    tp = write_transcript(tmp_path / "t.jsonl", [{"type": "user"}, "garbage"])
    assert cg.token_count(str(tp)) is None


def test_large_file_finds_qualifying_line_near_the_start(cg, tmp_path):
    filler = {"type": "user", "message": {"content": "x" * 1000}}
    entries: list[Any] = [assistant(123_456)] + [filler] * 6000  # about 6 MB
    tp = write_transcript(tmp_path / "t.jsonl", entries)
    assert tp.stat().st_size > 4 * 1024 * 1024
    assert cg.token_count(str(tp)) == 123_456


# ---- UserPromptSubmit ----


@pytest.mark.parametrize(
    ("tokens", "level"),
    [
        (199_999, None),
        (200_000, "warn"),
        (249_999, "warn"),
        (250_000, "handoff"),
    ],
)
def test_ups_boundaries(cg, monkeypatch, capsys, tmp_path, tokens, level):
    tp = write_transcript(tmp_path / "t.jsonl", [assistant(tokens)])
    out, _ = run_main(cg, monkeypatch, capsys, ups(tp))
    if level is None:
        assert out == ""
        return
    data = json.loads(out)
    assert "decision" not in data
    hso = data["hookSpecificOutput"]
    assert hso["hookEventName"] == "UserPromptSubmit"
    assert f"{tokens} tokens" in hso["additionalContext"]
    assert f"Context {tokens // 1000}k tokens" in data["systemMessage"]
    if level == "warn":
        assert "warn level" in data["systemMessage"]
        assert "Do not start a large new package" in hso["additionalContext"]
    else:
        assert "handoff limit" in data["systemMessage"]
        assert "/clear" in data["systemMessage"]
        assert ".handoff/INDEX.md" in hso["additionalContext"]


def test_ups_missing_transcript_prints_diagnostic_only(cg, monkeypatch, capsys, tmp_path):
    out, err = run_main(cg, monkeypatch, capsys, ups(tmp_path / "nope.jsonl"))
    assert out == "" and err.strip() != ""


def test_ups_malformed_lines_only_no_output(cg, monkeypatch, capsys, tmp_path):
    tp = write_transcript(tmp_path / "t.jsonl", ["{bad", "also bad"])
    out, err = run_main(cg, monkeypatch, capsys, ups(tp))
    assert out == "" and err.strip() != ""


def test_agent_id_skips_everything(cg, monkeypatch, capsys, tmp_path):
    tp = write_transcript(tmp_path / "t.jsonl", [assistant(300_000)])
    out, err = run_main(cg, monkeypatch, capsys, ups(tp, agent_id="a1"))
    assert out == "" and err == ""
    out, err = run_main(cg, monkeypatch, capsys, stop(tp, agent_id="a1"))
    assert out == "" and err == ""


# ---- Stop ----


def test_stop_blocks_once_then_silent(cg, monkeypatch, capsys, tmp_path, tmp_marker_dir):
    tp = write_transcript(tmp_path / "t.jsonl", [assistant(260_000)])
    out, _ = run_main(cg, monkeypatch, capsys, stop(tp))
    data = json.loads(out)
    assert data["decision"] == "block"
    assert "260000 tokens" in data["reason"]
    assert marker(tmp_marker_dir).is_file()
    out, _ = run_main(cg, monkeypatch, capsys, stop(tp))
    assert out == ""


def test_stop_boundary_249_999_does_not_block(cg, monkeypatch, capsys, tmp_path, tmp_marker_dir):
    tp = write_transcript(tmp_path / "t.jsonl", [assistant(249_999)])
    out, _ = run_main(cg, monkeypatch, capsys, stop(tp))
    assert out == "" and not marker(tmp_marker_dir).exists()


def test_stop_boundary_250_000_blocks(cg, monkeypatch, capsys, tmp_path):
    tp = write_transcript(tmp_path / "t.jsonl", [assistant(250_000)])
    out, _ = run_main(cg, monkeypatch, capsys, stop(tp))
    assert json.loads(out)["decision"] == "block"


def test_stop_hook_active_is_silent_and_creates_no_marker(cg, monkeypatch, capsys, tmp_path, tmp_marker_dir):
    tp = write_transcript(tmp_path / "t.jsonl", [assistant(300_000)])
    out, _ = run_main(cg, monkeypatch, capsys, stop(tp, stop_hook_active=True))
    assert out == "" and not marker(tmp_marker_dir).exists()


def test_marker_reset_below_warn_then_blocks_again(cg, monkeypatch, capsys, tmp_path, tmp_marker_dir):
    tp = tmp_path / "t.jsonl"
    write_transcript(tp, [assistant(260_000)])
    out, _ = run_main(cg, monkeypatch, capsys, stop(tp))
    assert json.loads(out)["decision"] == "block"
    write_transcript(tp, [assistant(30_000)])  # after /clear
    out, _ = run_main(cg, monkeypatch, capsys, stop(tp))
    assert out == "" and not marker(tmp_marker_dir).exists()
    write_transcript(tp, [assistant(270_000)])
    out, _ = run_main(cg, monkeypatch, capsys, stop(tp))
    assert json.loads(out)["decision"] == "block"


def test_marker_kept_between_warn_and_handoff(cg, monkeypatch, capsys, tmp_path, tmp_marker_dir):
    tp = tmp_path / "t.jsonl"
    write_transcript(tp, [assistant(260_000)])
    run_main(cg, monkeypatch, capsys, stop(tp))
    write_transcript(tp, [assistant(220_000)])
    run_main(cg, monkeypatch, capsys, stop(tp))
    assert marker(tmp_marker_dir).is_file()


@pytest.mark.parametrize("sid", ["../evil", "a/b", "", "x" * 129, "has space"])
def test_invalid_session_id_never_blocks(cg, monkeypatch, capsys, tmp_path, tmp_marker_dir, sid):
    tp = write_transcript(tmp_path / "t.jsonl", [assistant(300_000)])
    payload = {**stop(tp), "session_id": sid}
    for _ in range(2):
        out, err = run_main(cg, monkeypatch, capsys, payload)
        assert out == "" and err.strip() != ""
    assert not (tmp_marker_dir / "claude-context-guard").exists()


def test_stop_missing_transcript_no_output(cg, monkeypatch, capsys, tmp_path):
    out, err = run_main(cg, monkeypatch, capsys, stop(tmp_path / "nope.jsonl"))
    assert out == "" and err.strip() != ""


def test_marker_dir_is_under_tempfile_gettempdir(cg, monkeypatch, capsys, tmp_path, tmp_marker_dir):
    tp = write_transcript(tmp_path / "t.jsonl", [assistant(300_000)])
    run_main(cg, monkeypatch, capsys, stop(tp))
    assert marker(tmp_marker_dir).parent == Path(tempfile.gettempdir()) / "claude-context-guard"
    assert marker(tmp_marker_dir).is_file()


def test_unknown_event_is_silent(cg, monkeypatch, capsys, tmp_path):
    tp = write_transcript(tmp_path / "t.jsonl", [assistant(300_000)])
    out, _ = run_main(cg, monkeypatch, capsys, {**ups(tp), "hook_event_name": "SessionStart"})
    assert out == ""


# ---- end to end ----


def run_hook(payload: dict[str, Any], tmpdir: Path) -> subprocess.CompletedProcess[str]:
    import os

    env = {**os.environ, **LEGACY_CONSOLE_ENV, "TMPDIR": str(tmpdir)}
    return subprocess.run(
        [sys.executable, str(HOOKS / "context_guard.py")],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )


def test_end_to_end_user_prompt_submit(tmp_path):
    tp = write_transcript(tmp_path / "t.jsonl", [assistant(255_000)])
    proc = run_hook(ups(tp), tmp_path)
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "255k" in data["systemMessage"]


def test_end_to_end_non_ascii_transcript_path_under_a_legacy_console(tmp_path):
    folder = tmp_path / "t\u00ean-\u1ebf"  # U+1EBF is not in cp1252
    folder.mkdir()
    tp = write_transcript(folder / "t.jsonl", [assistant(255_000)])
    proc = run_hook(ups(tp), tmp_path)
    assert proc.returncode == 0
    assert proc.stderr == ""
    assert "255k" in json.loads(proc.stdout)["systemMessage"]


def test_end_to_end_stop(tmp_path):
    tp = write_transcript(tmp_path / "t.jsonl", [assistant(255_000)])
    proc = run_hook(stop(tp), tmp_path)
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["decision"] == "block"
    again = run_hook(stop(tp), tmp_path)
    assert again.returncode == 0 and again.stdout == ""


def test_end_to_end_garbage_stdin_exits_zero(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(HOOKS / "context_guard.py")],
        input="not json",
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0 and proc.stdout == ""


# ---- compact boundary, synthetic lines, text constants ----


def compact_line(post: Any = 25_583) -> dict[str, Any]:
    return {
        "type": "system",
        "subtype": "compact_boundary",
        "compactMetadata": {"trigger": "auto", "preTokens": 241_736, "postTokens": post},
    }


def synthetic_line() -> dict[str, Any]:
    zero = {"input_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    return {"type": "assistant", "message": {"model": "<synthetic>", "usage": zero}}


def test_compact_boundary_after_large_line_uses_post_tokens(cg, tmp_path):
    tp = write_transcript(tmp_path / "t.jsonl", [assistant(300_000), compact_line()])
    assert cg.token_count(str(tp)) == 25_583


def test_compact_boundary_without_int_post_tokens_gives_none(cg, tmp_path):
    tp = write_transcript(tmp_path / "t.jsonl", [assistant(300_000), compact_line("x")])
    assert cg.token_count(str(tp)) is None


def test_synthetic_line_is_skipped(cg, tmp_path):
    tp = write_transcript(tmp_path / "t.jsonl", [assistant(300_000), synthetic_line()])
    assert cg.token_count(str(tp)) == 300_000


def test_unmetered_line_is_skipped(cg, tmp_path):
    unmetered = {**assistant(5), "isUnmetered": True}
    tp = write_transcript(tmp_path / "t.jsonl", [assistant(300_000), unmetered])
    assert cg.token_count(str(tp)) == 300_000


def test_synthetic_line_keeps_marker(cg, monkeypatch, capsys, tmp_path, tmp_marker_dir):
    tp = write_transcript(tmp_path / "t.jsonl", [assistant(300_000)])
    run_main(cg, monkeypatch, capsys, stop(tp))
    assert marker(tmp_marker_dir).exists()
    write_transcript(tp, [assistant(300_000), synthetic_line()])
    run_main(cg, monkeypatch, capsys, stop(tp))
    assert marker(tmp_marker_dir).exists()


def test_texts_derive_from_constants(cg):
    assert str(cg.HANDOFF_TOKENS) in cg.HANDOFF_TEXT.format(n=1, limit=cg.HANDOFF_TOKENS)
    assert "wait for them to finish before asking for /clear" in cg.HANDOFF_TEXT


def test_messages_use_constants(cg, monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cg, "WARN_TOKENS", 100_000)
    monkeypatch.setattr(cg, "HANDOFF_TOKENS", 150_000)
    tp = write_transcript(tmp_path / "t.jsonl", [assistant(120_000)])
    out, _ = run_main(cg, monkeypatch, capsys, ups(tp))
    assert "100k" in out and "150k" in out and "200k" not in out and "250k" not in out
    assert "100000" in out and "150000" in out
