#!/usr/bin/env python3
"""SessionStart hook: remove leftover git worktrees and branches that are provably safe to lose.

Agent sessions leave worktrees and branches behind. On a fresh start this hook removes only the
ones that cannot lose work, and lists everything else for the engineer to decide. Deleting is hard
to reverse, so every rule errs toward keeping.

A worktree is removed only if ALL of these hold (otherwise it is kept, with the first failing reason):
  a. it is not the main worktree and not in use: none of the session's directories (the hook's stdin
     `cwd`, the process cwd, `CLAUDE_PROJECT_DIR`) is the worktree or inside it, no live session listed
     in `~/.claude/sessions/*.json` (undocumented; best effort) runs inside it, and it does not
     contain such a directory unless that is inside the main checkout;
  b. it is neither locked nor prunable (a prunable worktree, whose directory is gone, is only
     reported: this hook never runs `git worktree prune`);
  c. it is idle: the newest mtime of its admin files `HEAD` and `logs/HEAD` is older than
     `MIN_IDLE_HOURS`;
  d. neither its branch name, nor its directory name, nor either without the `worktree-` / `agent-`
     prefix appears in `.handoff/*.md` of the main checkout, and every such file is readable;
  e. `git status --porcelain --ignored=matching` lists nothing except entries that are themselves
     regenerable (`.venv/`, `__pycache__/`, `*.pyc`, `bin/`, ...): no modified, untracked or other
     ignored entry. Ignored directories are reported whole, so `projects/p1/` (ignored by
     `projects/*`) is kept even if it only holds a `bin/` folder;
  f. its HEAD is an ancestor of an integration ref other than its own branch (`origin/master`,
     `master`, any local `feat/*`): a `feat/*` worktree is never "merged into itself".
Checks run in that order, cheapest first. Removal is `git worktree remove` without `--force`; if
git refuses, the worktree is kept.

A local branch is deleted only with `git branch -d` (never `-D`) and only if it is not checked out in
a worktree (a prunable one still counts), is not `master` or `feat/*`, is an ancestor of
`origin/master` or `master`, and is not mentioned in `.handoff/*.md` (an unreadable file keeps it).

Every action is appended as one JSON line to `<git-common-dir>/claude-session-cleanup.jsonl` right
after it succeeds.
`--dry-run` decides and reports but changes nothing and writes no log. `--repo <path>` selects the
repository (default `CLAUDE_PROJECT_DIR` or the current directory).

Registered for the `startup` and `clear` sources only (a fresh start). Never blocks; always exits 0.
Stdlib only.
"""

from __future__ import annotations

import fnmatch
import json
import os
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

MIN_IDLE_HOURS = 24
INTEGRATION = ["origin/master", "master"]  # plus every local branch matching `feat/*`
REGENERABLE = [
    ".venv/",
    "__pycache__/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".mypy_cache/",
    "*.pyc",
    "node_modules/",
    "bin/",
    "obj/",
]
LOG_NAME = "claude-session-cleanup.jsonl"
GIT_TIMEOUT = 15
MAX_LINES = 20

REVIEW_REMINDER = (
    "Mention the kept-for-review items to the engineer once; never remove them without their confirmation."
)


class Worktree:
    """One entry of `git worktree list --porcelain` (a plain class: the hook is loaded by path)."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.head = ""
        self.branch = ""  # full ref, empty when detached
        self.locked = False
        self.prunable = False
        self.bare = False


def run_git(args: list[str], cwd: str | Path, timeout: int = GIT_TIMEOUT) -> tuple[int, str, str]:
    """(returncode, stdout, stderr); a git that cannot run is returncode 127, never an exception."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


def first_line(text: str) -> str:
    lines = text.strip().splitlines()
    return lines[0] if lines else "no message"


def list_worktrees(repo: str | Path) -> list[Worktree]:
    rc, out, _ = run_git(["worktree", "list", "--porcelain"], repo)
    if rc != 0:
        return []
    result: list[Worktree] = []
    for line in out.splitlines():
        key, _, value = line.partition(" ")
        if key == "worktree":
            result.append(Worktree(path=value))
        elif not result:
            continue
        elif key == "HEAD":
            result[-1].head = value
        elif key == "branch":
            result[-1].branch = value
        elif key == "locked":
            result[-1].locked = True
        elif key == "prunable":
            result[-1].prunable = True
        elif key == "bare":
            result[-1].bare = True
    return result


def is_regenerable(entry: str) -> bool:
    """True if the status entry itself (not a parent directory) is a regenerable path."""
    if entry.startswith("projects/"):  # engineer data: never regenerable, whatever its name
        return False
    is_dir = entry.endswith("/")
    name = entry.rstrip("/").rsplit("/", 1)[-1]
    for pattern in REGENERABLE:
        if pattern.endswith("/"):
            if is_dir and name == pattern[:-1]:
                return True
        elif not is_dir and fnmatch.fnmatchcase(name, pattern):
            return True
    return False


def unclean_reason(wt_path: str) -> str | None:
    """None when the worktree holds nothing but regenerable ignored entries, else why it is not clean."""
    rc, out, err = run_git(
        ["status", "--porcelain", "-z", "--untracked-files=normal", "--ignored=matching"], wt_path
    )
    if rc != 0:
        return f"git status failed: {first_line(err)}"
    entries = out.split("\0")
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        if code == "!!":
            if is_regenerable(path):
                continue
            return f"ignored file: {path}"
        if "R" in code or "C" in code:
            index += 1  # a rename or copy carries its source as the next field
        kind = "untracked file" if code == "??" else "uncommitted change"
        return f"{kind}: {path}"
    return hidden_change(wt_path)


def hidden_change(wt_path: str) -> str | None:
    """A path flagged assume-unchanged or skip-worktree: `git status` cannot see edits to it."""
    rc, out, err = run_git(["ls-files", "-v", "-z"], wt_path)
    if rc != 0:
        return f"git ls-files failed: {first_line(err)}"
    for entry in out.split("\0"):
        if len(entry) > 2 and (entry[0] == "S" or entry[0].islower()):
            return f"hidden local change: {entry[2:]}"
    return None


def newest_admin_mtime(wt_path: str) -> float | None:
    rc, out, _ = run_git(["rev-parse", "--absolute-git-dir"], wt_path)
    if rc != 0 or not out.strip():
        return None
    admin = Path(out.strip())
    times: list[float] = []
    for name in ("HEAD", "logs/HEAD"):
        try:
            times.append((admin / name).stat().st_mtime)
        except OSError:
            continue
    return max(times) if times else None


def within(child: Path, parent: Path) -> bool:
    return child == parent or parent in child.parents


def in_use(wt_path: str, session_dirs: Sequence[Path], main_path: str) -> bool:
    """A session directory is in this worktree, or (not in the main checkout) the worktree sits inside it."""
    wt, main = Path(wt_path).resolve(), Path(main_path).resolve()
    for directory in session_dirs:
        try:
            cur = directory.resolve()
        except (OSError, ValueError, RuntimeError):
            continue  # a path that cannot exist cannot hold a session
        if within(cur, wt) or (within(wt, cur) and not within(cur, main)):
            return True
    return False


def pid_alive(pid: int) -> bool:
    """Whether a process with this pid exists; when unsure, True (an extra keep is harmless)."""
    if sys.platform == "win32":  # os.kill(pid, 0) would terminate the process on Windows
        try:
            import ctypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.restype = ctypes.c_void_p
            handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if handle:
                kernel32.CloseHandle(ctypes.c_void_p(handle))
                return True
            return ctypes.get_last_error() == 5  # access denied: the process exists
        except Exception:
            return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (OverflowError, ValueError):
        return True  # a pid this OS cannot even express: unsure
    except OSError:
        return True  # PermissionError: it exists
    return True


def own_pid_domain() -> str | None:
    """Identity of this process's pid namespace (Linux), or None when it cannot be read."""
    try:
        return str(Path("/proc/self/ns/pid").readlink())
    except (OSError, ValueError):
        return None


def live_session_dirs(folder: Path) -> list[Path]:
    """`cwd` of each `<folder>/*.json` session file whose `pid` is alive; any unreadable file is ignored."""
    dirs: list[Path] = []
    try:
        files = sorted(folder.glob("*.json"))
    except Exception:
        return dirs
    domain_here = own_pid_domain()
    for file in files:
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            pid, cwd = data.get("pid"), data.get("cwd")
            if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
                continue
            if not isinstance(cwd, str) or not cwd:
                continue
            domain = data.get("pidDomain")
            foreign = isinstance(domain, str) and domain_here is not None and domain != domain_here
            if foreign or pid_alive(pid):  # a pid from another namespace cannot be checked here
                dirs.append(Path(cwd).resolve())
        except Exception:  # one bad session file must not hide the others
            continue
    return dirs


def handoff_reason(main_path: str, needles: list[str]) -> str | None:
    """Why `.handoff/*.md` keeps the target: a file mentions a needle, or a file cannot be read."""
    folder = Path(main_path) / ".handoff"
    try:
        files = sorted(folder.glob("*.md"))
    except OSError:
        return "handoff unreadable: .handoff"
    unreadable: str | None = None
    for file in files:
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            unreadable = unreadable or file.name
            continue
        if any(needle and needle in text for needle in needles):
            return f"mentioned in handoff .handoff/{file.name}"
    return f"handoff unreadable: .handoff/{unreadable}" if unreadable else None


def integration_refs(main_path: str) -> list[str]:
    refs: list[str] = []
    for name in INTEGRATION:
        full = f"refs/remotes/{name}" if name.startswith("origin/") else f"refs/heads/{name}"
        rc, _, _ = run_git(["rev-parse", "--verify", "-q", f"{full}^{{commit}}"], main_path)
        if rc == 0:
            refs.append(full)
    rc, out, _ = run_git(["for-each-ref", "--format=%(refname)", "refs/heads/feat/"], main_path)
    if rc == 0:
        refs.extend(line for line in out.splitlines() if line)
    return refs


def is_ancestor(commit: str, ref: str, cwd: str) -> bool:
    rc, _, _ = run_git(["merge-base", "--is-ancestor", commit, ref], cwd)
    return rc == 0


def short_ref(ref: str) -> str:
    return ref.removeprefix("refs/heads/")


class ActionLog:
    """Appends one JSON line per action to `<git-common-dir>/claude-session-cleanup.jsonl`, at once."""

    def __init__(self, main_path: str, now: float, enabled: bool) -> None:
        self.main_path = main_path
        self.stamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now))
        self.enabled = enabled
        self.path: Path | None = None

    def row(self, action: str, target: str, reason: str, head: str) -> None:
        if not self.enabled:
            return
        if self.path is None:
            rc, out, _ = run_git(["rev-parse", "--path-format=absolute", "--git-common-dir"], self.main_path)
            if rc != 0 or not out.strip():
                self.enabled = False
                return
            self.path = Path(out.strip()) / LOG_NAME
        entry = {"ts": self.stamp, "action": action, "target": target, "reason": reason, "head": head}
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass  # a log that cannot be written must not stop session start


def cleanup(
    repo: str | Path,
    current: Path | None = None,
    now: float | None = None,
    min_idle_hours: float = MIN_IDLE_HOURS,
    dry_run: bool = False,
    protected: Sequence[Path] = (),
    sessions_dir: Path | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Remove (or, in dry-run, report) the safe worktrees and branches; return what happened."""
    now = time.time() if now is None else now
    current = Path.cwd() if current is None else current
    session_dirs = [current, *protected]
    report: dict[str, list[dict[str, Any]]] = {"removed_worktrees": [], "deleted_branches": [], "kept": []}
    worktrees = list_worktrees(repo)
    if not worktrees:
        return report
    main = worktrees[0]
    refs = integration_refs(main.path)
    idle_limit = min_idle_hours * 3600
    if sessions_dir is None:
        try:
            sessions_dir = Path.home() / ".claude" / "sessions"  # undocumented; only ever adds keeps
        except (RuntimeError, OSError):
            sessions_dir = None
    live = live_session_dirs(sessions_dir) if sessions_dir is not None else []
    log = ActionLog(main.path, now, enabled=not dry_run)

    def keep(kind: str, target: str, reason: str, head: str, review: bool, idle: bool) -> None:
        report["kept"].append(
            {"kind": kind, "target": target, "reason": reason, "head": head, "review": review, "idle": idle}
        )
        if review:
            log.row("kept", target, reason, head)

    gone: set[str] = set()  # paths of worktrees removed (or, in dry-run, that would be)
    for wt in worktrees[1:]:
        if wt.bare:
            continue
        if in_use(wt.path, session_dirs, main.path):
            keep("worktree", wt.path, "current session directory", wt.head, review=False, idle=False)
            continue
        wt_root = Path(wt.path).resolve()
        if any(within(directory, wt_root) for directory in live):
            keep("worktree", wt.path, "live session", wt.head, review=False, idle=False)
            continue
        if wt.locked:
            keep("worktree", wt.path, "locked", wt.head, review=False, idle=False)
            continue
        if wt.prunable:  # never pruned here: the engineer decides (`git worktree prune`)
            keep("worktree", wt.path, "prunable: directory missing", wt.head, review=True, idle=True)
            continue
        mtime = newest_admin_mtime(wt.path)
        idle = mtime is not None and now - mtime > idle_limit
        reason = worktree_keep_reason(wt, main.path, refs, idle, mtime is None, min_idle_hours)
        if reason is None:
            removed = {
                "target": wt.path,
                "reason": "clean, merged, idle",
                "head": wt.head,
                "branch": short_ref(wt.branch),
            }
            if dry_run:
                gone.add(wt.path)
                report["removed_worktrees"].append(removed)
                continue
            rc, _, err = run_git(["worktree", "remove", wt.path], main.path)
            if rc == 0:
                gone.add(wt.path)
                report["removed_worktrees"].append(removed)
                log.row("removed_worktree", wt.path, removed["reason"], wt.head)
                continue
            reason = f"git refused: {first_line(err)}"
        keep("worktree", wt.path, reason, wt.head, review=True, idle=idle)

    delete_branches(report, worktrees, gone, main.path, refs, now, idle_limit, dry_run, log)
    return report


def worktree_keep_reason(
    wt: Worktree, main_path: str, refs: list[str], idle: bool, no_mtime: bool, min_idle_hours: float
) -> str | None:
    """First failing check among idle, handoff, status, merge (the caller checked the rest), else None."""
    if no_mtime:
        return "idle time unknown"
    if not idle:
        return f"not idle for {min_idle_hours:g}h yet"
    branch, name = short_ref(wt.branch), Path(wt.path).name
    needles = [branch, name, branch.removeprefix("worktree-"), name.removeprefix("agent-")]
    mention = handoff_reason(main_path, needles)
    if mention:
        return mention
    dirty = unclean_reason(wt.path)
    if dirty is not None:
        return dirty
    candidates = [r for r in refs if r != wt.branch]
    if not wt.head or not any(is_ancestor(wt.head, r, main_path) for r in candidates):
        return "HEAD not merged into origin/master, master or another feat/* branch"
    return None


def delete_branches(
    report: dict[str, list[dict[str, Any]]],
    worktrees: list[Worktree],
    gone: set[str],
    main_path: str,
    refs: list[str],
    now: float,
    idle_limit: float,
    dry_run: bool,
    log: ActionLog,
) -> None:
    rc, out, _ = run_git(
        ["for-each-ref", "--format=%(refname)%09%(objectname)%09%(committerdate:unix)", "refs/heads/"],
        main_path,
    )
    if rc != 0:
        return
    checked_out = {wt.branch for wt in worktrees if wt.path not in gone and wt.branch}
    masters = [r for r in refs if r in ("refs/remotes/origin/master", "refs/heads/master")]

    def keep(name: str, reason: str, sha: str, idle: bool) -> None:
        report["kept"].append(
            {"kind": "branch", "target": name, "reason": reason, "head": sha, "review": True, "idle": idle}
        )
        log.row("kept", name, reason, sha)

    for line in out.splitlines():
        ref, _, rest = line.partition("\t")
        sha, _, stamp = rest.partition("\t")
        name = short_ref(ref)
        if ref in checked_out or name == "master" or name.startswith("feat/"):
            continue  # policy keeps, nothing to review
        try:
            idle = now - float(stamp) > idle_limit
        except ValueError:
            idle = False
        if not any(is_ancestor(sha, m, main_path) for m in masters):
            keep(name, "not merged into origin/master or master", sha, idle)
            continue
        needles = [name, name.removeprefix("worktree-"), name.removeprefix("worktree-agent-")]
        mention = handoff_reason(main_path, needles)
        if mention:
            keep(name, mention, sha, idle)
            continue
        if not dry_run:
            rc, _, err = run_git(["branch", "-d", name], main_path)
            if rc != 0:
                keep(name, f"git refused: {first_line(err)}", sha, idle)
                continue
        report["deleted_branches"].append({"target": name, "reason": "merged into master", "head": sha})
        log.row("deleted_branch", name, "merged into master", sha)


def shorten(lines: list[str], limit: int) -> list[str]:
    if len(lines) <= limit:
        return lines
    return [*lines[: limit - 1], f"- ... and {len(lines) - (limit - 1)} more (see the cleanup log in .git)"]


def build_output(report: dict[str, list[dict[str, Any]]], dry_run: bool) -> dict[str, Any] | None:
    removed_wt, deleted = report["removed_worktrees"], report["deleted_branches"]
    review = [k for k in report["kept"] if k["review"] and k["idle"]]
    if not removed_wt and not deleted and not review:
        return None
    verb = "would be " if dry_run else ""
    removed_lines = [
        f"- worktree {verb}removed: {w['target']} ({w['branch'] or 'detached'})" for w in removed_wt
    ]
    removed_lines += [f"- branch {verb}deleted: {b['target']}" for b in deleted]
    kept_lines = [f"- kept for review, {k['kind']} {k['target']}: {k['reason']}" for k in review]
    kept_budget = min(len(kept_lines), MAX_LINES // 2)  # kept items must stay visible
    lines = shorten(removed_lines, MAX_LINES - kept_budget) + shorten(kept_lines, kept_budget)
    text = "\n".join(lines)
    if review:
        text += f"\n\n{REVIEW_REMINDER}"
    summary = (
        f"would remove {len(removed_wt)} worktree(s), would delete {len(deleted)} branch(es)"
        if dry_run
        else f"removed {len(removed_wt)} worktree(s), {len(deleted)} branch(es)"
    )
    out: dict[str, Any] = {
        "systemMessage": f"Cleanup: {summary}; {len(review)} kept for review.",
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text},
    }
    if dry_run:
        out["dry_run"] = True
    return out


def parse_args(argv: list[str]) -> tuple[bool, str | None]:
    dry_run = "--dry-run" in argv
    repo: str | None = None
    if "--repo" in argv:
        position = argv.index("--repo")
        if position + 1 < len(argv):
            repo = argv[position + 1]
    return dry_run, repo


def stdin_cwd() -> Path | None:
    """`cwd` from the hook's JSON on stdin; None when stdin is a terminal, empty, invalid or has no `cwd`."""
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return None
        data = json.loads(sys.stdin.read())
    except (OSError, ValueError, RecursionError):
        return None
    cwd = data.get("cwd") if isinstance(data, dict) else None
    return Path(cwd) if isinstance(cwd, str) and cwd else None


def main(argv: list[str]) -> int:
    dry_run, repo_arg = parse_args(argv)
    try:
        process_cwd: Path | None = Path.cwd()
    except OSError:
        process_cwd = None
    project_env = os.environ.get("CLAUDE_PROJECT_DIR")
    project = Path(project_env) if project_env else process_cwd
    repo = Path(repo_arg) if repo_arg else project
    if project is None or repo is None or not repo.is_dir():
        return 0
    protected = [d for d in (stdin_cwd(), process_cwd) if d is not None]
    out = build_output(cleanup(repo, current=project, protected=protected, dry_run=dry_run), dry_run)
    if out is not None:
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


def entry(argv: list[str]) -> int:
    try:
        return main(argv)
    except Exception as exc:  # a cleanup must never break session start
        sys.stderr.write(f"session_cleanup: skipped after {type(exc).__name__}: {exc}\n")
        return 0


if __name__ == "__main__":
    sys.exit(entry(sys.argv[1:]))
