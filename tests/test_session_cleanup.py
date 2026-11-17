"""SessionStart cleanup hook: remove provably safe leftover worktrees and branches, list the rest.

All tests run on temporary git repositories; the real repository is never touched.
"""

from __future__ import annotations

import json
import ntpath
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import HOOKS, LEGACY_CONSOLE_ENV, load_hook

FAR_FUTURE = 48 * 3600  # seconds added to "now" so freshly created worktrees count as idle


@pytest.fixture(autouse=True)
def git_env(monkeypatch):
    for key, value in {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
    }.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def cleanup_mod():
    return load_hook("session_cleanup")


def git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-c", "init.defaultBranch=master", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return proc.stdout.strip()


def commit(cwd: Path, name: str, text: str = "x\n") -> str:
    (cwd / name).write_text(text, encoding="utf-8")
    git(cwd, "add", name)
    git(cwd, "commit", "-q", "-m", f"add {name}")
    return git(cwd, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path) -> Path:
    main = tmp_path / "main"
    main.mkdir()
    git(main, "init", "-q")
    (main / ".gitignore").write_text(
        ".venv/\n__pycache__/\n*.pyc\nprojects/\nbin/\nscratch/\n", encoding="utf-8"
    )
    git(main, "add", ".gitignore")
    commit(main, "README.md")
    return main


def add_worktree(repo: Path, tmp_path: Path, name: str, branch: str | None = None) -> Path:
    path = tmp_path / "wts" / name
    path.parent.mkdir(exist_ok=True)
    git(repo, "worktree", "add", "-q", "-b", branch or f"fix/{name}", str(path))
    return path


def clean(mod, repo: Path, tmp_path: Path, **kw):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir(exist_ok=True)
    kw.setdefault("current", elsewhere)
    kw.setdefault("now", time.time() + FAR_FUTURE)
    kw.setdefault("sessions_dir", tmp_path / "no-sessions")
    return mod.cleanup(repo, **kw)


def use_real_ignore_rules(repo: Path) -> None:
    """The ignore lines of this repository that matter here: `projects/*` and the regenerable ones."""
    (repo / ".gitignore").write_text(
        "projects/*\n!projects/README.md\n__pycache__/\n*.py[cod]\n.venv/\nbin/\nobj/\n", encoding="utf-8"
    )
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-q", "-m", "real ignore rules")


def backdate(wt: Path, names: tuple[str, ...] = ("HEAD", "logs/HEAD"), hours: float = 48) -> None:
    admin = load_hook("session_cleanup").admin_dir(wt)
    assert admin is not None
    stamp = time.time() - hours * 3600
    for name in names:
        os.utime(admin / name, (stamp, stamp))


def removed_names(report) -> list[str]:
    return sorted(Path(r["target"]).name for r in report["removed_worktrees"])


def kept_for(report, name: str) -> dict:
    hits = [k for k in report["kept"] if k["target"] == name or k["target"].endswith("/" + name)]
    assert len(hits) == 1, report["kept"]
    return hits[0]


def worktree_paths(repo: Path) -> list[str]:
    """Worktree paths as git prints them, normalised: git prints `C:/x/y` where `str(Path)` is `C:\\x\\y`."""
    out = git(repo, "worktree", "list", "--porcelain")
    return [norm(line[len("worktree ") :]) for line in out.splitlines() if line.startswith("worktree ")]


def norm(path: str | Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


# --- worktrees: the all-pass case and one keep case per rule -------------------------------


def test_clean_merged_idle_worktree_is_removed(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    report = clean(cleanup_mod, repo, tmp_path)
    assert removed_names(report) == ["w1"]
    assert not wt.exists()
    assert str(wt) not in worktree_paths(repo)


def test_regenerable_ignored_files_do_not_block_a_plain_remove(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    (wt / ".venv" / "lib").mkdir(parents=True)
    (wt / ".venv" / "lib" / "x.py").write_text("x", encoding="utf-8")
    (wt / "src" / "__pycache__").mkdir(parents=True)
    (wt / "src" / "__pycache__" / "m.pyc").write_bytes(b"\0")
    (wt / "top.pyc").write_bytes(b"\0")
    (wt / "bin").mkdir()
    (wt / "bin" / "a.dll").write_bytes(b"\0")
    report = clean(cleanup_mod, repo, tmp_path)
    assert removed_names(report) == ["w1"]
    assert not wt.exists()


def test_non_regenerable_ignored_file_keeps_the_worktree(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    (wt / "projects" / "p1").mkdir(parents=True)
    (wt / "projects" / "p1" / "out.json").write_text("{}", encoding="utf-8")
    report = clean(cleanup_mod, repo, tmp_path)
    assert report["removed_worktrees"] == []
    assert wt.exists()
    assert "projects" in kept_for(report, "w1")["reason"]


def test_only_the_ignored_entry_itself_may_be_regenerable(cleanup_mod, repo, tmp_path):
    """With `bin/` partly tracked, an ignored `bin/out/` is listed on its own and is not `bin/`."""
    (repo / "bin").mkdir()
    (repo / "bin" / "tracked.txt").write_text("t", encoding="utf-8")
    git(repo, "add", "-f", "bin/tracked.txt")
    git(repo, "commit", "-q", "-m", "track bin file")
    wt = add_worktree(repo, tmp_path, "w1")
    (wt / "bin" / "out").mkdir()
    (wt / "bin" / "out" / "data.txt").write_text("precious", encoding="utf-8")
    report = clean(cleanup_mod, repo, tmp_path)
    assert wt.exists()
    assert "bin/out" in kept_for(report, "w1")["reason"]


def test_collapsed_ignored_directory_is_searched_for_non_regenerable_files(cleanup_mod, repo, tmp_path):
    """Git reports `docs/` as one ignored entry when it holds only ignored files: look inside it."""
    wt = add_worktree(repo, tmp_path, "w1")
    (wt / "docs" / "__pycache__").mkdir(parents=True)
    (wt / "docs" / "__pycache__" / "m.pyc").write_bytes(b"\0")
    (wt / "docs" / "scratch").mkdir()
    (wt / "docs" / "scratch" / "notes.txt").write_text("keep", encoding="utf-8")
    report = clean(cleanup_mod, repo, tmp_path)
    assert wt.exists()
    assert "docs/scratch" in kept_for(report, "w1")["reason"]


def test_modified_tracked_file_keeps_the_worktree(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    (wt / "README.md").write_text("changed\n", encoding="utf-8")
    report = clean(cleanup_mod, repo, tmp_path)
    assert wt.exists()
    assert "README.md" in kept_for(report, "w1")["reason"]


def test_untracked_file_keeps_the_worktree(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    (wt / "notes.txt").write_text("n", encoding="utf-8")
    report = clean(cleanup_mod, repo, tmp_path)
    assert wt.exists()
    assert "notes.txt" in kept_for(report, "w1")["reason"]


def test_unmerged_head_keeps_the_worktree(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    commit(wt, "work.txt")
    report = clean(cleanup_mod, repo, tmp_path)
    assert wt.exists()
    assert "merged" in kept_for(report, "w1")["reason"]


def test_head_merged_only_into_origin_master_is_enough(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    sha = commit(wt, "work.txt")
    git(repo, "update-ref", "refs/remotes/origin/master", sha)
    report = clean(cleanup_mod, repo, tmp_path)
    assert removed_names(report) == ["w1"]


def test_feat_worktree_is_never_merged_into_itself(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1", branch="feat/alpha")
    commit(wt, "work.txt")
    report = clean(cleanup_mod, repo, tmp_path)
    assert wt.exists()
    assert "merged" in kept_for(report, "w1")["reason"]


def test_feat_worktree_merged_into_another_feat_branch_is_removed(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1", branch="feat/alpha")
    commit(wt, "work.txt")
    git(repo, "branch", "feat/beta", "feat/alpha")
    report = clean(cleanup_mod, repo, tmp_path)
    assert removed_names(report) == ["w1"]


def test_recently_active_worktree_is_kept(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    report = clean(cleanup_mod, repo, tmp_path, now=time.time())
    assert wt.exists()
    assert "idle" in kept_for(report, "w1")["reason"]


def test_min_idle_hours_is_honoured(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    report = clean(cleanup_mod, repo, tmp_path, now=time.time() + 3 * 3600, min_idle_hours=2)
    assert removed_names(report) == ["w1"]
    assert not wt.exists()


def test_branch_name_in_a_handoff_file_keeps_the_worktree(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1", branch="fix/special-name")
    (repo / ".handoff").mkdir()
    (repo / ".handoff" / "topic.md").write_text("resume fix/special-name later", encoding="utf-8")
    report = clean(cleanup_mod, repo, tmp_path)
    assert wt.exists()
    assert "handoff" in kept_for(report, "w1")["reason"]


def test_directory_name_in_a_handoff_file_keeps_the_worktree(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1-dirname")
    (repo / ".handoff").mkdir()
    (repo / ".handoff" / "topic.md").write_text("see worktree w1-dirname", encoding="utf-8")
    report = clean(cleanup_mod, repo, tmp_path)
    assert wt.exists()
    assert "handoff" in kept_for(report, "w1-dirname")["reason"]


def test_main_worktree_is_never_removed(cleanup_mod, repo, tmp_path):
    report = clean(cleanup_mod, repo, tmp_path)
    assert report["removed_worktrees"] == []
    assert repo.exists()


def test_current_directory_worktree_is_kept(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    report = clean(cleanup_mod, repo, tmp_path, current=wt)
    assert wt.exists()
    assert "current" in kept_for(report, "w1")["reason"]


def test_worktree_containing_the_current_directory_is_kept(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    sub = wt / "deep" / "dir"
    sub.mkdir(parents=True)
    report = clean(cleanup_mod, repo, tmp_path, current=sub)
    assert wt.exists()
    assert "current" in kept_for(report, "w1")["reason"]


def test_worktree_inside_a_non_main_current_directory_is_kept(cleanup_mod, repo, tmp_path):
    outer = add_worktree(repo, tmp_path, "outer")
    inner = outer / "nested"
    git(repo, "worktree", "add", "-q", "-b", "fix/inner", str(inner))
    report = clean(cleanup_mod, repo, tmp_path, current=outer)
    assert inner.exists() and outer.exists()
    assert "current" in kept_for(report, "nested")["reason"]


def test_current_directory_inside_a_linked_worktree_keeps_the_worktrees_nested_below_it(
    cleanup_mod, repo, tmp_path
):
    outer = repo / ".claude" / "worktrees" / "A"
    git(repo, "worktree", "add", "-q", "-b", "A", str(outer))
    inner = outer / ".claude" / "worktrees" / "B"
    git(repo, "worktree", "add", "-q", "-b", "B", str(inner))
    report = clean(cleanup_mod, repo, tmp_path, current=outer)
    assert inner.exists()
    assert kept_for(report, "B")["reason"] == "current session directory"


def test_running_from_the_main_checkout_still_cleans_nested_worktrees(cleanup_mod, repo, tmp_path):
    nested = repo / ".claude" / "worktrees" / "w1"
    nested.parent.mkdir(parents=True)
    git(repo, "worktree", "add", "-q", "-b", "fix/w1", str(nested))
    (repo / ".git" / "info" / "exclude").write_text(".claude/worktrees/\n", encoding="utf-8")
    report = clean(cleanup_mod, repo, tmp_path, current=repo)
    assert removed_names(report) == ["w1"]


def test_locked_worktree_is_kept(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    git(repo, "worktree", "lock", str(wt))
    report = clean(cleanup_mod, repo, tmp_path)
    assert wt.exists()
    assert "locked" in kept_for(report, "w1")["reason"]


def test_worktree_directory_deleted_by_hand_does_not_crash(cleanup_mod, repo, tmp_path):
    gone = add_worktree(repo, tmp_path, "gone")
    other = add_worktree(repo, tmp_path, "other")
    subprocess.run(["rm", "-rf", str(gone)], check=True)
    report = clean(cleanup_mod, repo, tmp_path)
    assert removed_names(report) == ["other"]
    assert not other.exists()
    assert norm(gone) in worktree_paths(repo)  # kept for review: no `git worktree prune`


def test_git_refusal_keeps_the_worktree_and_never_forces(cleanup_mod, repo, tmp_path, monkeypatch):
    wt = add_worktree(repo, tmp_path, "w1")
    (wt / "late.txt").write_text("created after the status check", encoding="utf-8")
    monkeypatch.setattr(cleanup_mod, "unclean_reason", lambda *_a, **_k: None)
    other = add_worktree(repo, tmp_path, "w2")
    report = clean(cleanup_mod, repo, tmp_path)
    assert wt.exists()
    assert kept_for(report, "w1")["reason"].startswith("git refused:")
    assert not other.exists()  # one refusal does not stop the others


# --- branches ----------------------------------------------------------------------------


def test_merged_branch_is_deleted(cleanup_mod, repo, tmp_path):
    git(repo, "branch", "fix/old")
    report = clean(cleanup_mod, repo, tmp_path)
    assert [b["target"] for b in report["deleted_branches"]] == ["fix/old"]
    assert "fix/old" not in git(repo, "branch", "--list", "fix/*")


def test_unmerged_branch_is_kept(cleanup_mod, repo, tmp_path):
    git(repo, "checkout", "-q", "-b", "fix/wip")
    commit(repo, "wip.txt")
    git(repo, "checkout", "-q", "master")
    report = clean(cleanup_mod, repo, tmp_path)
    assert report["deleted_branches"] == []
    assert "merged" in kept_for(report, "fix/wip")["reason"]
    assert "fix/wip" in git(repo, "branch", "--list", "fix/*")


def test_branch_merged_only_into_origin_master_is_deleted(cleanup_mod, repo, tmp_path):
    git(repo, "checkout", "-q", "-b", "fix/pushed")
    sha = commit(repo, "p.txt")
    git(repo, "checkout", "-q", "master")
    git(repo, "update-ref", "refs/remotes/origin/master", sha)
    git(repo, "merge", "-q", "--ff-only", "fix/pushed")  # let `git branch -d` agree
    report = clean(cleanup_mod, repo, tmp_path)
    assert [b["target"] for b in report["deleted_branches"]] == ["fix/pushed"]


def test_feat_and_master_branches_are_never_deleted(cleanup_mod, repo, tmp_path):
    git(repo, "branch", "feat/keepme")
    report = clean(cleanup_mod, repo, tmp_path)
    assert report["deleted_branches"] == []
    out = git(repo, "branch", "--list")
    assert "feat/keepme" in out and "master" in out


def test_branch_checked_out_in_a_kept_worktree_is_not_deleted(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    (wt / "dirty.txt").write_text("d", encoding="utf-8")  # keeps the worktree
    report = clean(cleanup_mod, repo, tmp_path)
    assert report["deleted_branches"] == []
    assert "fix/w1" in git(repo, "branch", "--list", "fix/*")


def test_branch_of_a_removed_worktree_is_deleted_in_the_same_run(cleanup_mod, repo, tmp_path):
    add_worktree(repo, tmp_path, "w1")
    report = clean(cleanup_mod, repo, tmp_path)
    assert removed_names(report) == ["w1"]
    assert [b["target"] for b in report["deleted_branches"]] == ["fix/w1"]


def test_branch_mentioned_in_a_handoff_file_is_kept(cleanup_mod, repo, tmp_path):
    git(repo, "branch", "fix/remembered")
    (repo / ".handoff").mkdir()
    (repo / ".handoff" / "t.md").write_text("branch fix/remembered", encoding="utf-8")
    report = clean(cleanup_mod, repo, tmp_path)
    assert report["deleted_branches"] == []
    assert "handoff" in kept_for(report, "fix/remembered")["reason"]


def test_git_branch_refusal_is_kept_with_a_reason_and_never_forced(cleanup_mod, repo, tmp_path):
    """`old` is on master but not in the main checkout's HEAD (`side`): `git branch -d` refuses."""
    git(repo, "branch", "side", "HEAD")
    git(repo, "checkout", "-q", "side")
    git(repo, "checkout", "-q", "master")
    old = commit(repo, "second.txt")
    git(repo, "branch", "fix/old", old)
    git(repo, "checkout", "-q", "side")
    commit(repo, "side.txt")
    report = clean(cleanup_mod, repo, tmp_path)
    assert report["deleted_branches"] == []
    assert kept_for(report, "fix/old")["reason"].startswith("git refused:")
    assert "fix/old" in git(repo, "branch", "--list", "fix/*")


# --- dry run, log, output ------------------------------------------------------------------


def test_dry_run_changes_nothing_and_writes_no_log(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    git(repo, "branch", "fix/old")
    before = git(repo, "worktree", "list", "--porcelain")
    report = clean(cleanup_mod, repo, tmp_path, dry_run=True)
    assert removed_names(report) == ["w1"]
    assert sorted(b["target"] for b in report["deleted_branches"]) == ["fix/old", "fix/w1"]
    assert wt.exists()
    assert git(repo, "worktree", "list", "--porcelain") == before
    assert "fix/old" in git(repo, "branch", "--list", "fix/*")
    assert not (repo / ".git" / "claude-session-cleanup.jsonl").exists()


def test_actions_are_logged_one_json_line_each(cleanup_mod, repo, tmp_path):
    add_worktree(repo, tmp_path, "w1")
    git(repo, "branch", "fix/old")
    dirty = add_worktree(repo, tmp_path, "w2")
    (dirty / "x.txt").write_text("x", encoding="utf-8")
    clean(cleanup_mod, repo, tmp_path)
    log = repo / ".git" / "claude-session-cleanup.jsonl"
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert {r["action"] for r in rows} == {"removed_worktree", "deleted_branch", "kept"}
    for row in rows:
        assert set(row) >= {"ts", "action", "target", "reason", "head"}
    removed = next(r for r in rows if r["action"] == "removed_worktree")
    assert removed["target"].endswith("w1") and len(removed["head"]) == 40


def test_output_is_none_when_nothing_happened(cleanup_mod):
    report = {"removed_worktrees": [], "deleted_branches": [], "kept": []}
    assert cleanup_mod.build_output(report, dry_run=False) is None


def test_output_is_none_when_only_recent_items_are_kept(cleanup_mod):
    report = {
        "removed_worktrees": [],
        "deleted_branches": [],
        "kept": [
            {
                "kind": "worktree",
                "target": "/x",
                "reason": "idle 1h",
                "head": "a",
                "review": True,
                "idle": False,
            }
        ],
    }
    assert cleanup_mod.build_output(report, dry_run=False) is None


def test_output_lists_removed_and_kept_items(cleanup_mod, repo, tmp_path):
    add_worktree(repo, tmp_path, "w1")
    dirty = add_worktree(repo, tmp_path, "w2")
    (dirty / "x.txt").write_text("x", encoding="utf-8")
    out = cleanup_mod.build_output(clean(cleanup_mod, repo, tmp_path), dry_run=False)
    assert out is not None
    assert out["systemMessage"] == "Cleanup: removed 1 worktree(s), 1 branch(es); 1 kept for review."
    hook = out["hookSpecificOutput"]
    assert hook["hookEventName"] == "SessionStart"
    text = hook["additionalContext"]
    assert "w1" in text and "w2" in text and "x.txt" in text
    assert text.rstrip().endswith("never remove them without their confirmation.")
    assert "dry_run" not in out


def test_output_is_capped_at_twenty_item_lines(cleanup_mod):
    kept = [
        {
            "kind": "branch",
            "target": f"fix/b{i}",
            "reason": "not merged",
            "head": "a",
            "review": True,
            "idle": True,
        }
        for i in range(40)
    ]
    out = cleanup_mod.build_output(
        {"removed_worktrees": [], "deleted_branches": [], "kept": kept}, dry_run=False
    )
    assert out is not None
    lines = out["hookSpecificOutput"]["additionalContext"].splitlines()
    assert sum(1 for line in lines if line.startswith("- ")) <= 20
    assert "more" in out["hookSpecificOutput"]["additionalContext"]


def test_dry_run_output_carries_the_flag(cleanup_mod):
    report = {
        "removed_worktrees": [],
        "deleted_branches": [{"target": "fix/a", "reason": "merged", "head": "a"}],
        "kept": [],
    }
    out = cleanup_mod.build_output(report, dry_run=True)
    assert out is not None and out["dry_run"] is True


# --- review fixes: ignored files, prune, protected dirs, handoff names, live sessions, order --


def test_ignored_file_in_a_subdirectory_of_projects_keeps_the_worktree(cleanup_mod, repo, tmp_path):
    """`projects/*` ignores `projects/p1/`; its `bin/` child must not make it look regenerable."""
    use_real_ignore_rules(repo)
    wt = add_worktree(repo, tmp_path, "w1")
    (wt / "projects" / "p1" / "bin").mkdir(parents=True)
    (wt / "projects" / "p1" / "bin" / "x.json").write_text("{}", encoding="utf-8")
    report = clean(cleanup_mod, repo, tmp_path)
    assert report["removed_worktrees"] == []
    assert (wt / "projects" / "p1" / "bin" / "x.json").exists()
    assert "projects/p1" in kept_for(report, "w1")["reason"]


def test_regenerable_files_deep_in_the_tree_are_removable_with_the_real_ignore_rules(
    cleanup_mod, repo, tmp_path
):
    use_real_ignore_rules(repo)
    wt = add_worktree(repo, tmp_path, "w1")
    (wt / "src" / "pkg" / "__pycache__").mkdir(parents=True)
    (wt / "src" / "pkg" / "__pycache__" / "a.pyc").write_bytes(b"\0")
    report = clean(cleanup_mod, repo, tmp_path)
    assert removed_names(report) == ["w1"]


def test_prunable_worktree_is_kept_for_review_and_its_branch_survives(cleanup_mod, repo, tmp_path):
    gone = add_worktree(repo, tmp_path, "gone")
    subprocess.run(["rm", "-rf", str(gone)], check=True)
    report = clean(cleanup_mod, repo, tmp_path)
    item = kept_for(report, "gone")
    assert item["reason"] == "prunable: directory missing"
    assert item["review"] is True and item["idle"] is True
    assert norm(gone) in worktree_paths(repo)  # nothing was pruned
    assert report["deleted_branches"] == []
    assert "fix/gone" in git(repo, "branch", "--list", "fix/*")


def test_protected_directory_inside_a_worktree_keeps_it(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    report = clean(cleanup_mod, repo, tmp_path, current=repo, protected=[wt / "sub"])
    assert wt.exists()
    assert "current" in kept_for(report, "w1")["reason"]


def somewhere_else(tmp_path: Path) -> Path:
    """A process cwd that neither contains nor sits in any worktree (tmp_path itself contains them)."""
    folder = tmp_path / "elsewhere"
    folder.mkdir(exist_ok=True)
    return folder


def run_hook_in(cwd: Path, project: Path, stdin: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        **LEGACY_CONSOLE_ENV,
        "CLAUDE_PROJECT_DIR": str(project),
        "HOME": str(cwd / "no-home"),
    }
    return subprocess.run(
        [sys.executable, str(HOOKS / "session_cleanup.py"), *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=cwd,
        check=False,
    )


def test_hook_keeps_the_worktree_named_by_the_stdin_cwd(repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    backdate(wt)
    proc = run_hook_in(somewhere_else(tmp_path), repo, json.dumps({"cwd": str(wt)}), "--repo", str(repo))
    assert proc.returncode == 0
    assert wt.exists()


def test_hook_keeps_the_worktree_it_runs_in_even_when_the_project_dir_is_main(repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    backdate(wt)
    proc = run_hook_in(wt, repo, "{}", "--repo", str(repo))
    assert proc.returncode == 0
    assert wt.exists()


@pytest.mark.parametrize("stdin", ["", "not json", "[1]", '{"cwd": 5}'])
def test_hook_tolerates_empty_or_invalid_stdin(repo, tmp_path, stdin):
    wt = add_worktree(repo, tmp_path, "w1")
    backdate(wt)
    proc = run_hook_in(somewhere_else(tmp_path), repo, stdin, "--repo", str(repo))
    assert proc.returncode == 0
    assert not wt.exists()  # nothing protected it: removed as before


def test_bare_agent_id_in_a_handoff_file_keeps_the_worktree(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "agent-ab12cd34", branch="worktree-agent-ab12cd34")
    (repo / ".handoff").mkdir()
    (repo / ".handoff" / "topic.md").write_text("subagent ab12cd34 still has notes", encoding="utf-8")
    report = clean(cleanup_mod, repo, tmp_path)
    assert wt.exists()
    assert "handoff" in kept_for(report, "agent-ab12cd34")["reason"]


def write_session(folder: Path, name: str, data: object) -> None:
    folder.mkdir(exist_ok=True)
    (folder / name).write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


def test_live_session_cwd_inside_a_worktree_keeps_it(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    sessions = tmp_path / "sessions"
    write_session(sessions, "a.json", {"pid": os.getpid(), "cwd": str(wt / "sub")})
    report = clean(cleanup_mod, repo, tmp_path, sessions_dir=sessions)
    assert wt.exists()
    assert kept_for(report, "w1")["reason"] == "live session"


def test_dead_or_malformed_session_files_do_not_keep_a_worktree(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    sessions = tmp_path / "sessions"
    write_session(sessions, "dead.json", {"pid": dead.pid, "cwd": str(wt)})
    write_session(sessions, "bad.json", "{not json")
    write_session(sessions, "nopid.json", {"cwd": str(wt)})
    write_session(sessions, "strpid.json", {"pid": str(os.getpid()), "cwd": str(wt)})
    write_session(sessions, "zero.json", {"pid": 0, "cwd": str(wt)})
    report = clean(cleanup_mod, repo, tmp_path, sessions_dir=sessions)
    assert removed_names(report) == ["w1"]


def test_unreadable_handoff_file_keeps_the_worktree_and_the_branch(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    git(repo, "branch", "fix/old")
    (repo / ".handoff").mkdir()
    try:  # a dangling symlink is listed as a file, and reading it raises OSError
        (repo / ".handoff" / "broken.md").symlink_to(tmp_path / "missing-target")
    except OSError:
        pytest.skip("symlinks are not available here")
    report = clean(cleanup_mod, repo, tmp_path)
    assert wt.exists()
    assert "unreadable: .handoff/broken.md" in kept_for(report, "w1")["reason"]
    assert "unreadable: .handoff/broken.md" in kept_for(report, "fix/old")["reason"]
    assert report["deleted_branches"] == []


def test_handoff_file_with_an_upper_case_extension_is_a_mention_source(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    write_handoff(repo, "Topic.MD", "resume fix/w1 later")
    report = clean(cleanup_mod, repo, tmp_path)
    assert wt.exists()
    assert kept_for(report, "w1")["reason"] == "mentioned in .handoff/Topic.MD"


@pytest.mark.parametrize("where", [".handoff", ".coord"])
def test_dangling_symlink_as_a_mention_folder_keeps_the_worktree_and_the_branch(
    cleanup_mod, repo, tmp_path, where
):
    wt = add_worktree(repo, tmp_path, "w1")
    git(repo, "branch", "fix/old")
    folder = repo / ".handoff" if where == ".handoff" else repo.parent / ".coord"
    try:
        folder.symlink_to(tmp_path / "nowhere")
    except OSError:
        pytest.skip("symlinks are not available here")
    report = clean(cleanup_mod, repo, tmp_path)
    assert wt.exists()
    assert f"unreadable: {where}" in kept_for(report, "w1")["reason"]
    assert f"unreadable: {where}" in kept_for(report, "fix/old")["reason"]
    assert report["deleted_branches"] == []


@pytest.mark.parametrize("where", [".handoff", ".coord"])
def test_a_regular_file_in_place_of_a_mention_folder_keeps_the_worktree(cleanup_mod, repo, tmp_path, where):
    wt = add_worktree(repo, tmp_path, "w1")
    git(repo, "branch", "fix/old")
    folder = repo / ".handoff" if where == ".handoff" else repo.parent / ".coord"
    folder.write_text("not a folder", encoding="utf-8")
    report = clean(cleanup_mod, repo, tmp_path)
    assert wt.exists()
    assert f"unreadable: {where}" in kept_for(report, "w1")["reason"]
    assert f"unreadable: {where}" in kept_for(report, "fix/old")["reason"]
    assert report["deleted_branches"] == []


def test_checks_run_cheapest_first(cleanup_mod, repo, tmp_path):
    """A recent dirty worktree is 'not idle', not 'untracked'; a handoff mention beats a dirty tree."""
    fresh = add_worktree(repo, tmp_path, "fresh")
    (fresh / "x.txt").write_text("x", encoding="utf-8")
    noted = add_worktree(repo, tmp_path, "noted")
    (noted / "x.txt").write_text("x", encoding="utf-8")
    (repo / ".handoff").mkdir()
    (repo / ".handoff" / "t.md").write_text("see noted", encoding="utf-8")
    report = clean(cleanup_mod, repo, tmp_path, now=time.time())
    assert kept_for(report, "fresh")["reason"].startswith("not idle")
    assert kept_for(report, "noted")["reason"].startswith("not idle")
    report = clean(cleanup_mod, repo, tmp_path)  # idle now
    assert "handoff" in kept_for(report, "noted")["reason"]
    assert "untracked" in kept_for(report, "fresh")["reason"]


def test_only_head_and_reflog_decide_idleness_not_the_index(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    backdate(wt)
    admin = Path(git(wt, "rev-parse", "--absolute-git-dir"))
    now = time.time()
    os.utime(admin / "index", (now, now))
    report = clean(cleanup_mod, repo, tmp_path, now=now)
    assert removed_names(report) == ["w1"]


def test_each_action_is_logged_as_soon_as_it_succeeds(cleanup_mod, repo, tmp_path, monkeypatch):
    add_worktree(repo, tmp_path, "w1")
    git(repo, "branch", "fix/old")
    real = cleanup_mod.run_git

    def boom(args, cwd, *a, **k):
        if args[:2] == ["branch", "-d"]:
            raise RuntimeError("interrupted")
        return real(args, cwd, *a, **k)

    monkeypatch.setattr(cleanup_mod, "run_git", boom)
    with pytest.raises(RuntimeError):
        clean(cleanup_mod, repo, tmp_path)
    log = repo / ".git" / "claude-session-cleanup.jsonl"
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [r["action"] for r in rows] == ["removed_worktree"]


# --- the hook as Claude Code runs it -------------------------------------------------------


def run_hook(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project), "HOME": str(project / "no-home")}
    return subprocess.run(
        [sys.executable, str(HOOKS / "session_cleanup.py"), *args],
        input="{}",
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_hook_end_to_end_deletes_a_merged_branch_and_reports_it(repo, tmp_path):
    git(repo, "branch", "fix/old")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    proc = run_hook(elsewhere, "--repo", str(repo))
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["systemMessage"].startswith("Cleanup: removed 0 worktree(s), 1 branch(es)")
    assert "fix/old" not in git(repo, "branch", "--list", "fix/*")


def test_hook_dry_run_end_to_end_changes_nothing(repo, tmp_path):
    git(repo, "branch", "fix/old")
    proc = run_hook(tmp_path, "--dry-run", "--repo", str(repo))
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["dry_run"] is True
    assert "fix/old" in git(repo, "branch", "--list", "fix/*")
    assert not (repo / ".git" / "claude-session-cleanup.jsonl").exists()


def test_hook_is_silent_and_exits_zero_when_there_is_nothing_to_do(repo, tmp_path):
    proc = run_hook(tmp_path, "--repo", str(repo))
    assert proc.returncode == 0 and proc.stdout == ""


def test_hook_exits_zero_outside_a_git_repository(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    proc = run_hook(plain, "--repo", str(plain))
    assert proc.returncode == 0 and proc.stdout == ""


def test_hook_exits_zero_on_bad_arguments(tmp_path):
    proc = run_hook(tmp_path, "--repo")
    assert proc.returncode == 0


# --- second review: robustness, liveness, regenerable, hidden changes, wording ---------------


def test_one_unusable_session_file_does_not_hide_the_others(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    sessions = tmp_path / "sessions"
    write_session(sessions, "a-nul.json", {"pid": os.getpid(), "cwd": "bad\0path"})
    write_session(sessions, "b-ok.json", {"pid": os.getpid(), "cwd": str(wt)})
    report = clean(cleanup_mod, repo, tmp_path, sessions_dir=sessions)
    assert wt.exists()
    assert kept_for(report, "w1")["reason"] == "live session"


def test_a_pid_too_large_for_the_os_counts_as_alive(cleanup_mod, repo, tmp_path):
    assert cleanup_mod.pid_alive(2**100) is True
    wt = add_worktree(repo, tmp_path, "w1")
    sessions = tmp_path / "sessions"
    write_session(sessions, "big.json", {"pid": 2**100, "cwd": str(wt)})
    report = clean(cleanup_mod, repo, tmp_path, sessions_dir=sessions)
    assert wt.exists()
    assert kept_for(report, "w1")["reason"] == "live session"


@pytest.mark.parametrize("stdin", ["[" * 200000, '{"cwd": "a\\u0000b"}'])
def test_stdin_cwd_survives_pathological_input(cleanup_mod, monkeypatch, stdin):
    import io

    monkeypatch.setattr(cleanup_mod.sys, "stdin", io.StringIO(stdin))
    cleanup_mod.stdin_cwd()  # must not raise


def test_a_nul_byte_in_a_protected_directory_does_not_stop_cleanup(cleanup_mod, repo, tmp_path):
    add_worktree(repo, tmp_path, "w1")
    report = clean(cleanup_mod, repo, tmp_path, protected=[Path("a\0b")])
    assert removed_names(report) == ["w1"]


def test_the_sessions_folder_is_looked_up_at_call_time(cleanup_mod, repo, tmp_path, monkeypatch):
    wt = add_worktree(repo, tmp_path, "w1")
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    write_session(home / ".claude" / "sessions", "a.json", {"pid": os.getpid(), "cwd": str(wt)})
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    report = cleanup_mod.cleanup(repo, current=elsewhere, now=time.time() + FAR_FUTURE)
    assert wt.exists()
    assert kept_for(report, "w1")["reason"] == "live session"


def test_a_crash_is_swallowed_but_leaves_one_line_on_stderr(cleanup_mod, monkeypatch, capsys):
    def boom(argv):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(cleanup_mod, "main", boom)
    assert cleanup_mod.entry([]) == 0
    err = capsys.readouterr().err
    assert len(err.strip().splitlines()) == 1 and "kaboom" in err


def own_pid_domain() -> str | None:
    try:
        return str(Path("/proc/self/ns/pid").readlink())
    except OSError:
        return None


@pytest.mark.skipif(own_pid_domain() is None, reason="no /proc pid namespace link")
def test_a_session_from_another_pid_namespace_counts_as_alive(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    sessions = tmp_path / "sessions"
    write_session(sessions, "x.json", {"pid": dead.pid, "cwd": str(wt), "pidDomain": "pid:[1]"})
    report = clean(cleanup_mod, repo, tmp_path, sessions_dir=sessions)
    assert wt.exists()
    assert kept_for(report, "w1")["reason"] == "live session"


@pytest.mark.skipif(own_pid_domain() is None, reason="no /proc pid namespace link")
def test_a_dead_session_in_our_own_pid_namespace_is_ignored(cleanup_mod, repo, tmp_path):
    add_worktree(repo, tmp_path, "w1")
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    sessions = tmp_path / "sessions"
    wt_path = tmp_path / "wts" / "w1"
    write_session(sessions, "x.json", {"pid": dead.pid, "cwd": str(wt_path), "pidDomain": own_pid_domain()})
    report = clean(cleanup_mod, repo, tmp_path, sessions_dir=sessions)
    assert removed_names(report) == ["w1"]


def test_an_ignored_entry_under_projects_is_never_regenerable(cleanup_mod, repo, tmp_path):
    use_real_ignore_rules(repo)
    wt = add_worktree(repo, tmp_path, "w1")
    (wt / "projects" / "bin").mkdir(parents=True)
    (wt / "projects" / "bin" / "data.json").write_text("{}", encoding="utf-8")
    report = clean(cleanup_mod, repo, tmp_path)
    assert (wt / "projects" / "bin" / "data.json").exists()
    assert "projects/bin" in kept_for(report, "w1")["reason"]


def test_a_file_pattern_does_not_make_a_directory_regenerable(cleanup_mod, repo, tmp_path):
    use_real_ignore_rules(repo)
    wt = add_worktree(repo, tmp_path, "w1")
    (wt / "src" / "data.pyc").mkdir(parents=True)
    (wt / "src" / "data.pyc" / "precious.txt").write_text("keep", encoding="utf-8")
    report = clean(cleanup_mod, repo, tmp_path)
    assert (wt / "src" / "data.pyc" / "precious.txt").exists()
    assert "src/data.pyc" in kept_for(report, "w1")["reason"]


def test_untracked_files_count_even_when_git_is_configured_to_hide_them(cleanup_mod, repo, tmp_path):
    git(repo, "config", "status.showUntrackedFiles", "no")
    wt = add_worktree(repo, tmp_path, "w1")
    (wt / "notes.txt").write_text("keep", encoding="utf-8")
    report = clean(cleanup_mod, repo, tmp_path)
    assert wt.exists()
    assert "notes.txt" in kept_for(report, "w1")["reason"]


def test_a_bare_agent_id_in_a_handoff_file_keeps_the_branch(cleanup_mod, repo, tmp_path):
    git(repo, "branch", "worktree-agent-ab12cd34")
    git(repo, "branch", "worktree-notes")
    (repo / ".handoff").mkdir()
    (repo / ".handoff" / "t.md").write_text("agent ab12cd34 and notes remain", encoding="utf-8")
    report = clean(cleanup_mod, repo, tmp_path)
    assert report["deleted_branches"] == []
    assert "handoff" in kept_for(report, "worktree-agent-ab12cd34")["reason"]
    assert "handoff" in kept_for(report, "worktree-notes")["reason"]


@pytest.mark.parametrize("flag", ["--assume-unchanged", "--skip-worktree"])
def test_a_hidden_local_change_keeps_the_worktree(cleanup_mod, repo, tmp_path, flag):
    wt = add_worktree(repo, tmp_path, "w1")
    git(wt, "update-index", flag, "README.md")
    (wt / "README.md").write_text("precious edit\n", encoding="utf-8")
    report = clean(cleanup_mod, repo, tmp_path)
    assert wt.exists()
    assert kept_for(report, "w1")["reason"] == "hidden local change: README.md"


def test_dry_run_message_says_would(cleanup_mod):
    report = {
        "removed_worktrees": [{"target": "/x/w1", "reason": "r", "head": "h", "branch": "fix/w1"}],
        "deleted_branches": [{"target": "fix/a", "reason": "merged", "head": "a"}],
        "kept": [],
    }
    out = cleanup_mod.build_output(report, dry_run=True)
    assert out is not None
    assert (
        out["systemMessage"]
        == "Cleanup: would remove 1 worktree(s), would delete 1 branch(es); 0 kept for review."
    )


# --- review fixes ported from the frontend: ancestors, unreadable folders, named sources, capped dry-run --


def write_handoff(repo: Path, name: str, text: str) -> None:
    (repo / ".handoff").mkdir(exist_ok=True)
    (repo / ".handoff" / name).write_text(text, encoding="utf-8")


def write_coord(repo: Path, name: str, text: str) -> None:
    """The coordinator folder sits next to the main checkout: `<parent of the main checkout>/.coord/`."""
    (repo.parent / ".coord").mkdir(exist_ok=True)
    (repo.parent / ".coord" / name).write_text(text, encoding="utf-8")


def test_live_session_in_the_parent_of_the_worktrees_keeps_them(cleanup_mod, repo, tmp_path):
    """A coordinator started in the folder above `wts/` spawns its agents into the worktrees below it."""
    wt = add_worktree(repo, tmp_path, "w1")
    sessions = tmp_path / "sessions"
    write_session(sessions, "coord.json", {"pid": os.getpid(), "cwd": str(wt.parent)})
    report = clean(cleanup_mod, repo, tmp_path, sessions_dir=sessions)
    assert wt.exists()
    assert kept_for(report, "w1")["reason"] == "live session"


def test_dead_session_in_the_parent_of_the_worktrees_does_not_keep_them(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    sessions = tmp_path / "sessions"
    write_session(sessions, "coord.json", {"pid": dead.pid, "cwd": str(wt.parent)})
    report = clean(cleanup_mod, repo, tmp_path, sessions_dir=sessions)
    assert removed_names(report) == ["w1"]


@pytest.mark.parametrize("session_dir", ["", ".claude", ".claude/worktrees"])
def test_live_session_in_the_main_checkout_does_not_keep_nested_worktrees(
    cleanup_mod, repo, tmp_path, session_dir
):
    """Every session starts in the main checkout; it must not pin `.claude/worktrees/*` forever."""
    nested = repo / ".claude" / "worktrees" / "w1"
    git(repo, "worktree", "add", "-q", "-b", "w1", str(nested))
    folder = repo / session_dir
    sessions = tmp_path / "sessions"
    write_session(sessions, "main.json", {"pid": os.getpid(), "cwd": str(folder)})
    report = clean(cleanup_mod, repo, tmp_path, sessions_dir=sessions)
    assert removed_names(report) == ["w1"]


def test_live_session_below_a_nested_worktree_keeps_it(cleanup_mod, repo, tmp_path):
    """Only a session in the main checkout OUTSIDE any worktree is ignored; one inside the worktree counts."""
    nested = repo / ".claude" / "worktrees" / "w1"
    git(repo, "worktree", "add", "-q", "-b", "w1", str(nested))
    (nested / "sub").mkdir()
    sessions = tmp_path / "sessions"
    write_session(sessions, "a.json", {"pid": os.getpid(), "cwd": str(nested / "sub")})
    report = clean(cleanup_mod, repo, tmp_path, sessions_dir=sessions)
    assert nested.exists()
    assert kept_for(report, "w1")["reason"] == "live session"


def test_live_session_inside_a_linked_worktree_keeps_the_worktrees_nested_below_it(
    cleanup_mod, repo, tmp_path
):
    """The main-checkout exception stops at a worktree: a session in `A` pins `A/.claude/worktrees/B`."""
    outer = repo / ".claude" / "worktrees" / "A"
    git(repo, "worktree", "add", "-q", "-b", "A", str(outer))
    inner = outer / ".claude" / "worktrees" / "B"
    git(repo, "worktree", "add", "-q", "-b", "B", str(inner))
    sessions = tmp_path / "sessions"
    write_session(sessions, "a.json", {"pid": os.getpid(), "cwd": str(outer)})
    report = clean(cleanup_mod, repo, tmp_path, sessions_dir=sessions)
    assert inner.exists()
    assert kept_for(report, "B")["reason"] == "live session"


def test_keep_reasons_name_where_the_mention_came_from(cleanup_mod, repo, tmp_path):
    handoff_wt = add_worktree(repo, tmp_path, "w-handoff", branch="feat/in-handoff")
    coord_wt = add_worktree(repo, tmp_path, "w-coord", branch="feat/in-coord")
    write_handoff(repo, "x.md", "resume feat/in-handoff")
    write_coord(repo, "agents.md", "live: feat/in-coord")
    git(repo, "branch", "fix/old-handoff")
    git(repo, "branch", "fix/old-coord")
    write_handoff(repo, "y.md", "branch fix/old-handoff")
    write_coord(repo, "branches.md", "branch fix/old-coord")
    report = clean(cleanup_mod, repo, tmp_path)
    assert handoff_wt.exists() and coord_wt.exists()
    assert kept_for(report, "w-handoff")["reason"] == "mentioned in .handoff/x.md"
    assert kept_for(report, "w-coord")["reason"] == "mentioned in .coord/agents.md"
    assert kept_for(report, "fix/old-handoff")["reason"] == "mentioned in .handoff/y.md"
    assert kept_for(report, "fix/old-coord")["reason"] == "mentioned in .coord/branches.md"


def test_the_coordinator_ledger_keeps_the_worktree_and_the_branch(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1-dirname")
    git(repo, "branch", "fix/old")
    write_coord(repo, "agents.md", "see worktree w1-dirname and fix/old")
    report = clean(cleanup_mod, repo, tmp_path)
    assert wt.exists()
    assert report["deleted_branches"] == []


def test_a_coordinator_ledger_that_names_nothing_keeps_nothing(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    write_coord(repo, "agents.md", "nothing relevant")
    report = clean(cleanup_mod, repo, tmp_path)
    assert removed_names(report) == ["w1"]
    assert not wt.exists()


def test_missing_mention_folders_are_fine(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    assert not (repo / ".handoff").exists() and not (repo.parent / ".coord").exists()
    report = clean(cleanup_mod, repo, tmp_path)
    assert removed_names(report) == ["w1"]
    assert not wt.exists()


@pytest.mark.parametrize("where", [".handoff", ".coord"])
def test_unreadable_mention_folder_keeps_the_worktree_and_the_branch(cleanup_mod, repo, tmp_path, where):
    wt = add_worktree(repo, tmp_path, "w1")
    git(repo, "branch", "fix/old")
    folder = repo / ".handoff" if where == ".handoff" else repo.parent / ".coord"
    folder.mkdir()
    (folder / "x.md").write_text("nothing", encoding="utf-8")
    if not hasattr(os, "geteuid") or os.geteuid() == 0:
        pytest.skip("permissions are not enforced here (root or Windows)")
    folder.chmod(0)
    try:
        try:
            list(folder.iterdir())
        except PermissionError:
            pass
        else:
            pytest.skip("chmod 000 did not make the folder unreadable here")
        report = clean(cleanup_mod, repo, tmp_path)
    finally:
        folder.chmod(0o755)
    assert wt.exists()
    assert f"unreadable: {where}" in kept_for(report, "w1")["reason"]
    assert f"unreadable: {where}" in kept_for(report, "fix/old")["reason"]
    assert report["deleted_branches"] == []


def mention_folder(repo: Path, where: str) -> Path:
    return repo / ".handoff" if where == ".handoff" else repo.parent / ".coord"


@pytest.mark.parametrize("where", [".handoff", ".coord"])
def test_a_mention_in_a_subfolder_keeps_the_worktree_and_the_branch(cleanup_mod, repo, tmp_path, where):
    wt = add_worktree(repo, tmp_path, "w1-dirname")
    git(repo, "branch", "fix/old")
    nested = mention_folder(repo, where) / "tracks" / "deeper"
    nested.mkdir(parents=True)
    (nested / "T1.MD").write_text("worktree w1-dirname and fix/old", encoding="utf-8")
    report = clean(cleanup_mod, repo, tmp_path)
    assert wt.exists()
    assert kept_for(report, "w1-dirname")["reason"] == f"mentioned in {where}/tracks/deeper/T1.MD"
    assert report["deleted_branches"] == []


def test_a_coord_subfolder_that_names_nothing_keeps_nothing(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    (repo.parent / ".coord" / "tracks").mkdir(parents=True)
    (repo.parent / ".coord" / "tracks" / "t1.md").write_text("nothing relevant", encoding="utf-8")
    report = clean(cleanup_mod, repo, tmp_path)
    assert removed_names(report) == ["w1"]
    assert not wt.exists()


def symlink_dir(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are not available here")


@pytest.mark.parametrize("where", [".handoff", ".coord"])
def test_a_mention_behind_a_symlinked_subfolder_keeps_the_worktree_and_the_branch(
    cleanup_mod, repo, tmp_path, where
):
    wt = add_worktree(repo, tmp_path, "w1-dirname")
    git(repo, "branch", "fix/old")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "x.md").write_text("worktree w1-dirname and fix/old", encoding="utf-8")
    folder = mention_folder(repo, where)
    folder.mkdir(exist_ok=True)
    symlink_dir(folder / "link", outside)
    report = clean(cleanup_mod, repo, tmp_path)
    assert wt.exists()
    assert kept_for(report, "w1-dirname")["reason"] == f"mentioned in {where}/link/x.md"
    assert report["deleted_branches"] == []


def guard_scandir(monkeypatch, limit: int = 200) -> list[str]:
    """Count `os.scandir` calls; past `limit` fail the test instead of looping on."""
    calls: list[str] = []
    real = os.scandir

    def counted(path):
        calls.append(str(path))
        assert len(calls) <= limit, "the mention walk does not terminate"
        return real(path)

    monkeypatch.setattr(os, "scandir", counted)
    return calls


@pytest.mark.parametrize("where", [".handoff", ".coord"])
def test_a_symlink_loop_in_a_mention_folder_ends_and_a_mention_elsewhere_still_keeps(
    cleanup_mod, repo, tmp_path, monkeypatch, where
):
    wt = add_worktree(repo, tmp_path, "w1")
    folder = mention_folder(repo, where)
    (folder / "a").mkdir(parents=True)
    symlink_dir(folder / "a" / "loop", folder)
    (folder / "z.md").write_text("w1", encoding="utf-8")
    guard_scandir(monkeypatch)
    report = clean(cleanup_mod, repo, tmp_path)
    assert wt.exists()
    assert kept_for(report, "w1")["reason"] == f"mentioned in {where}/z.md"


@pytest.mark.parametrize("where", [".handoff", ".coord"])
def test_a_symlink_loop_in_a_mention_folder_with_no_mention_hits_nothing(
    cleanup_mod, repo, tmp_path, monkeypatch, where
):
    wt = add_worktree(repo, tmp_path, "w1")
    folder = mention_folder(repo, where)
    (folder / "a").mkdir(parents=True)
    symlink_dir(folder / "a" / "loop", folder)
    (folder / "a" / "t.md").write_text("nothing relevant", encoding="utf-8")
    guard_scandir(monkeypatch)
    report = clean(cleanup_mod, repo, tmp_path)
    assert removed_names(report) == ["w1"]
    assert not wt.exists()


def test_a_dangling_symlink_in_a_mention_subfolder_keeps_the_worktree(cleanup_mod, repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "w1")
    (repo.parent / ".coord").mkdir()
    symlink_dir(repo.parent / ".coord" / "link", tmp_path / "nowhere")
    report = clean(cleanup_mod, repo, tmp_path)
    assert wt.exists()
    assert kept_for(report, "w1")["reason"] == "mention source unreadable: .coord/link"


@pytest.mark.parametrize("where", [".handoff", ".coord"])
def test_a_subfolder_that_vanishes_mid_walk_keeps_the_worktree_and_the_branch(
    cleanup_mod, repo, tmp_path, monkeypatch, where
):
    wt = add_worktree(repo, tmp_path, "w1")
    git(repo, "branch", "fix/old")
    sub = mention_folder(repo, where) / "tracks"
    sub.mkdir(parents=True)
    (sub / "x.md").write_text("nothing", encoding="utf-8")
    real = os.scandir

    def vanishing(path):
        if Path(path) == sub:  # listed in its parent, gone when opened
            raise FileNotFoundError(2, "gone", str(path))
        return real(path)

    monkeypatch.setattr(os, "scandir", vanishing)
    report = clean(cleanup_mod, repo, tmp_path)
    assert wt.exists()
    assert kept_for(report, "w1")["reason"] == f"mention source unreadable: {where}/tracks"
    assert kept_for(report, "fix/old")["reason"] == f"mention source unreadable: {where}/tracks"
    assert report["deleted_branches"] == []


def test_the_mention_sources_are_walked_once_per_run(cleanup_mod, repo, tmp_path, monkeypatch):
    add_worktree(repo, tmp_path, "w1")
    add_worktree(repo, tmp_path, "w2")
    git(repo, "branch", "fix/old")
    git(repo, "branch", "fix/older")
    write_handoff(repo, "t.md", "nothing relevant")
    write_coord(repo, "t.md", "nothing relevant")
    calls = guard_scandir(monkeypatch)
    report = clean(cleanup_mod, repo, tmp_path)
    assert removed_names(report) == ["w1", "w2"]
    assert len(report["deleted_branches"]) == 4  # fix/w1, fix/w2, fix/old, fix/older
    assert sorted(Path(c).name for c in calls) == [".coord", ".handoff"]


@pytest.mark.parametrize("where", [".handoff", ".coord"])
def test_unreadable_mention_subfolder_keeps_the_worktree_and_the_branch(cleanup_mod, repo, tmp_path, where):
    wt = add_worktree(repo, tmp_path, "w1")
    git(repo, "branch", "fix/old")
    sub = mention_folder(repo, where) / "tracks"
    sub.mkdir(parents=True)
    (sub / "x.md").write_text("nothing", encoding="utf-8")
    if not hasattr(os, "geteuid") or os.geteuid() == 0:
        pytest.skip("permissions are not enforced here (root or Windows)")
    sub.chmod(0)
    try:
        try:
            list(sub.iterdir())
        except PermissionError:
            pass
        else:
            pytest.skip("chmod 000 did not make the folder unreadable here")
        report = clean(cleanup_mod, repo, tmp_path)
    finally:
        sub.chmod(0o755)
    assert wt.exists()
    assert f"unreadable: {where}/tracks" in kept_for(report, "w1")["reason"]
    assert f"unreadable: {where}/tracks" in kept_for(report, "fix/old")["reason"]
    assert report["deleted_branches"] == []


def kept_item(i: int, reason: str = "not merged") -> dict:
    return {
        "kind": "branch",
        "target": f"fix/b{i:04d}",
        "reason": reason,
        "head": "h",
        "review": True,
        "idle": True,
    }


def test_dry_run_lists_every_kept_item_without_pointing_at_a_log(cleanup_mod):
    report = {"removed_worktrees": [], "deleted_branches": [], "kept": [kept_item(i) for i in range(30)]}
    out = cleanup_mod.build_output(report, dry_run=True, main_path="/srv/repo")
    assert out is not None
    text = out["hookSpecificOutput"]["additionalContext"]
    assert all(f"fix/b{i:04d}:" in text for i in range(30))
    assert "cleanup log" not in text and "more; full list" not in text


def quote_path(path: str) -> str:
    return shlex.quote(path) if os.name != "nt" else subprocess.list2cmdline([path])


def unquote_path(text: str) -> str:
    return shlex.split(text)[0] if os.name != "nt" else text.strip().strip('"')


def test_dry_run_footer_quotes_the_repo_path_even_without_a_space(cleanup_mod):
    kept = [kept_item(i, "not merged " * 6) for i in range(300)]
    report = {"removed_worktrees": [], "deleted_branches": [], "kept": kept}
    tricky = "/srv/it's;$HOME"
    out = cleanup_mod.build_output(report, dry_run=True, main_path=tricky)
    assert out is not None
    footer = out["hookSpecificOutput"]["additionalContext"].split("\n\n")[0].splitlines()[-1]
    assert footer.endswith(f"--repo {quote_path(tricky)}")
    if os.name != "nt":
        assert unquote_path(footer.split("--repo ", 1)[1]) == tricky


def test_dry_run_caps_the_listing_and_points_at_the_full_command(cleanup_mod):
    kept = [kept_item(i, "not merged " * 6) for i in range(300)]
    report = {"removed_worktrees": [], "deleted_branches": [], "kept": kept}
    out = cleanup_mod.build_output(report, dry_run=True, main_path="/srv/my repo")
    assert out is not None
    text = out["hookSpecificOutput"]["additionalContext"]
    assert len(text) < 10_000
    assert "fix/b0000:" in text and "fix/b0299:" not in text
    assert "cleanup log" not in text
    shown = sum(1 for i in range(300) if f"fix/b{i:04d}:" in text)
    listing = text.split("\n\n")[0]
    assert listing.splitlines()[-1] == (
        f"\u2026 {300 - shown} more; full list: "
        f"python .claude/hooks/session_cleanup.py --dry-run --full --repo {quote_path('/srv/my repo')}"
    )
    assert len(listing) <= cleanup_mod.DRY_RUN_LIST_LIMIT  # the footer fits inside the cap
    assert text.endswith(cleanup_mod.REVIEW_REMINDER)
    assert out["systemMessage"].endswith("300 kept for review.")  # the summary still counts every item


def test_dry_run_full_flag_lists_everything_without_a_footer(cleanup_mod):
    kept = [kept_item(i, "not merged " * 6) for i in range(300)]
    report = {"removed_worktrees": [], "deleted_branches": [], "kept": kept}
    out = cleanup_mod.build_output(report, dry_run=True, main_path="/r", full=True)
    assert out is not None
    text = out["hookSpecificOutput"]["additionalContext"]
    assert all(f"fix/b{i:04d}:" in text for i in range(300))
    assert "more; full list" not in text
    assert cleanup_mod.parse_args(["--dry-run", "--full", "--repo", "/r"]) == (True, "/r", True)
    assert cleanup_mod.parse_args(["--dry-run"]) == (True, None, False)


def test_full_does_not_change_a_real_run_which_still_shortens_and_points_at_the_log(cleanup_mod):
    report = {"removed_worktrees": [], "deleted_branches": [], "kept": [kept_item(i) for i in range(30)]}
    out = cleanup_mod.build_output(report, dry_run=False, full=True)
    assert out is not None
    text = out["hookSpecificOutput"]["additionalContext"]
    assert "see the cleanup log in .git" in text
    assert "fix/b0029:" not in text and "full list" not in text


def test_dry_run_keeps_removals_ahead_of_kept_items_when_it_cuts(cleanup_mod):
    removed = [{"target": f"/x/w{i}", "reason": "r", "head": "h", "branch": f"fix/w{i}"} for i in range(3)]
    kept = [kept_item(i, "not merged " * 6) for i in range(300)]
    report = {"removed_worktrees": removed, "deleted_branches": [], "kept": kept}
    out = cleanup_mod.build_output(report, dry_run=True, main_path="/r")
    assert out is not None
    text = out["hookSpecificOutput"]["additionalContext"]
    assert all(f"worktree would be removed: /x/w{i}" in text for i in range(3))


def test_non_dry_run_truncation_still_points_at_the_log(cleanup_mod):
    report = {"removed_worktrees": [], "deleted_branches": [], "kept": [kept_item(i) for i in range(30)]}
    out = cleanup_mod.build_output(report, dry_run=False)
    assert out is not None
    text = out["hookSpecificOutput"]["additionalContext"]
    assert "see the cleanup log in .git" in text and "session_cleanup.py --dry-run" not in text


def test_the_hook_prints_the_full_list_command_with_the_main_checkout(
    cleanup_mod, repo, tmp_path, monkeypatch
):
    """End to end: the footer carries the main checkout, even when the hook runs from a worktree."""
    monkeypatch.setenv("GIT_COMMITTER_DATE", "2020-01-01T00:00:00")
    commit(repo, "old.txt")  # branches at this commit are idle
    monkeypatch.delenv("GIT_COMMITTER_DATE")
    names = [f"fix/a-fairly-long-branch-name-to-fill-the-listing-{i:04d}" for i in range(400)]
    for name in names:
        git(repo, "branch", name)
    wt = add_worktree(repo, tmp_path, "w1")
    # the branches are merged; a handoff keeps each one, so the listing is all "kept for review"
    write_handoff(repo, "all.md", "\n".join(names))
    proc = run_hook_in(somewhere_else(tmp_path), wt, "{}", "--dry-run")
    assert proc.returncode == 0 and proc.stderr == ""
    text = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
    assert len(text) < 10_000
    footer = next(line for line in text.splitlines() if "full list: " in line)
    command = footer.split("session_cleanup.py ", 1)[1]
    flags, shown_repo = command.split("--repo ", 1)
    # git prints `C:/x` where `str(Path)` is `C:\\x` on Windows, so compare folded keys
    assert cleanup_mod.path_key(unquote_path(shown_repo)) == cleanup_mod.path_key(repo)
    assert "--dry-run" in flags.split() and "--full" in flags.split()
    # the printed command really lists everything: no cap, no footer
    again = run_hook_in(
        somewhere_else(tmp_path), wt, "{}", *flags.split(), "--repo", unquote_path(shown_repo)
    )
    assert again.returncode == 0 and again.stderr == ""
    full = json.loads(again.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "more; full list" not in full
    assert all(f"{name}:" in full for name in names)


# --- Windows: path spelling, process liveness, console encoding --------------------------------


def test_path_key_folds_separators_and_case_the_windows_way(cleanup_mod):
    """Git prints `C:/Users/Me/wts/w1`, Python spells `c:\\users\\me\\WTS\\w1\\`: one key for both."""
    fold = cleanup_mod.fold_path
    spellings = ["C:/Users/Me/wts/w1", "c:\\users\\me\\WTS\\w1\\", "C:\\Users\\Me\\wts\\.\\w1"]
    assert {fold(text, ntpath) for text in spellings} == {"c:\\users\\me\\wts\\w1"}
    assert fold("/a/B/../b/c", os.path) == os.path.normcase("/a/b/c")


def test_key_within_is_a_whole_component_prefix_test_on_windows_spellings(cleanup_mod):
    fold, inside = cleanup_mod.fold_path, cleanup_mod.key_within

    def under(child: str, parent: str) -> bool:
        return inside(fold(child, ntpath), fold(parent, ntpath), ntpath)

    assert under("C:/Repo/wts/W1/sub", "c:\\repo\\wts\\w1")
    assert under("C:/repo/wts/w1", "C:\\REPO\\wts\\w1")  # equal paths
    assert not under("C:/repo/wts/w10", "C:/repo/wts/w1")  # a longer name is not a child
    assert not under("C:/repo", "C:/repo/wts/w1")
    assert under("c:/repo", "C:\\")  # a drive root contains everything on it
    assert not under("D:/repo", "C:\\")


class FakeKernel32:
    """Stands in for `ctypes.WinDLL("kernel32")`: records calls, returns scripted answers."""

    def __init__(self, handle: int, exit_code: int = 0, exit_code_ok: bool = True) -> None:
        self.handle, self.exit_code, self.exit_code_ok = handle, exit_code, exit_code_ok
        self.opened: list[tuple[int, bool, int]] = []
        self.closed: list[int] = []

    def OpenProcess(self, access: int, inherit: bool, pid: int) -> int:
        self.opened.append((access, inherit, pid))
        return self.handle

    def GetExitCodeProcess(self, handle: int, code_ref: object) -> int:
        code_ref._obj.value = self.exit_code  # type: ignore[attr-defined]
        return 1 if self.exit_code_ok else 0

    def CloseHandle(self, handle: int) -> int:
        self.closed.append(handle)
        return 1


@pytest.mark.parametrize(
    ("handle", "exit_code", "exit_ok", "last_error", "alive"),
    [
        (0, 0, True, 87, False),  # ERROR_INVALID_PARAMETER: no such pid
        (0, 0, True, 5, True),  # ERROR_ACCESS_DENIED: it exists
        (0, 0, True, 1, True),  # any other error: unsure, so alive
        (7, 259, True, 0, True),  # STILL_ACTIVE
        (7, 0, True, 0, False),  # exited, but a handle (a Popen) keeps the process object around
        (7, 1, True, 0, False),
        (7, 0, False, 0, True),  # cannot read the exit code: unsure, so alive
    ],
)
def test_windows_liveness_decision(cleanup_mod, handle, exit_code, exit_ok, last_error, alive):
    fake = FakeKernel32(handle, exit_code, exit_ok)
    assert cleanup_mod.windows_pid_alive(4242, fake, lambda: last_error) is alive
    assert fake.opened == [(0x1000, False, 4242)]  # PROCESS_QUERY_LIMITED_INFORMATION
    assert fake.closed == ([handle] if handle else [])  # every opened handle is closed


@pytest.mark.parametrize("pid", [0, -1, 2**32, 2**100])
def test_windows_liveness_never_truncates_a_pid_that_is_not_a_dword(cleanup_mod, pid):
    fake = FakeKernel32(0)
    assert cleanup_mod.windows_pid_alive(pid, fake, lambda: 87) is True
    assert fake.opened == []


def test_windows_liveness_is_alive_when_the_api_misbehaves(cleanup_mod):
    class Broken:
        def OpenProcess(self, *_a):
            raise OSError("boom")

    assert cleanup_mod.windows_pid_alive(1, Broken(), lambda: 0) is True


def test_hook_prints_non_ascii_paths_under_a_legacy_console_encoding(repo, tmp_path):
    wt = add_worktree(repo, tmp_path, "wt-\u1ebf", branch="fix/wt-e")  # U+1EBF is not in cp1252
    backdate(wt)
    proc = run_hook_in(somewhere_else(tmp_path), repo, "{}", "--repo", str(repo), "--dry-run")
    assert proc.returncode == 0
    assert proc.stderr == ""
    assert "wt-\u1ebf" in json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]


def test_admin_dir_follows_the_gitdir_pointer_for_a_non_ascii_worktree(tmp_path: Path) -> None:
    """The admin dir comes from the UTF-8 `gitdir:` pointer, not from decoded git output."""
    wt = tmp_path / "wt-ế"
    admin = tmp_path / "main" / ".git" / "worktrees" / "wt-ế"
    admin.mkdir(parents=True)
    wt.mkdir()
    (wt / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")
    assert load_hook("session_cleanup").admin_dir(wt) == admin
