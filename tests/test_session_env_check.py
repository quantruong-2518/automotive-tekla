from __future__ import annotations


def fake_which(found: set[str]):
    return lambda tool: f"/bin/{tool}" if tool in found else None


def test_remote_session_is_a_problem(env_check):
    lines = env_check.report({"CLAUDE_CODE_REMOTE": "true"}, fake_which({"uv", "git", "tekla-cli"}))
    assert any("REMOTE" in line for line in lines)
    assert "No blocking problems." not in lines


def test_missing_tekla_cli_is_reported_not_blocking(env_check, monkeypatch):
    monkeypatch.setattr(env_check.platform, "system", lambda: "Windows")
    lines = env_check.report({}, fake_which({"uv", "git"}))
    assert any("tekla-cli: NOT FOUND" in line for line in lines)
    assert "No blocking problems." in lines


def test_missing_uv_is_blocking(env_check, monkeypatch):
    monkeypatch.setattr(env_check.platform, "system", lambda: "Windows")
    lines = env_check.report({}, fake_which({"git"}))
    assert any("uv not found" in line for line in lines)


def test_non_windows_is_flagged(env_check, monkeypatch):
    monkeypatch.setattr(env_check.platform, "system", lambda: "Linux")
    lines = env_check.report({}, fake_which({"uv", "git", "tekla-cli"}))
    assert any("Not Windows" in line for line in lines)
