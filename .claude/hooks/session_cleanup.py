#!/usr/bin/env python3
"""SessionStart hook: remove leftover git worktrees and branches that are provably safe to lose.

Agent sessions leave worktrees and branches behind. On a fresh start this hook removes only the
ones that cannot lose work, and lists everything else for the engineer to decide. Deleting is hard
to reverse, so every rule errs toward keeping.

A worktree is removed only if ALL of these hold (otherwise it is kept, with the first failing reason):
  a. it is not the main worktree, and not the session directory (the current directory is not in it;
     it does not contain the current directory unless that is the main checkout);
  b. it is neither locked nor prunable;
  c. `git status --porcelain --ignored` lists nothing except regenerable ignored paths (`.venv/`,
     `__pycache__/`, ...): no modified, untracked, or other ignored file (a `projects/` output stays);
  d. its HEAD is an ancestor of an integration ref other than its own branch (`origin/master`,
     `master`, any local `feat/*`): a `feat/*` worktree is never "merged into itself";
  e. it is idle: the newest mtime of its admin files `HEAD`, `index`, `logs/HEAD` is older than
     `MIN_IDLE_HOURS`;
  f. neither its branch name nor its directory name appears in `.handoff/*.md` of the main checkout.
Removal is `git worktree remove` without `--force`; if git refuses, the worktree is kept.

A local branch is deleted only with `git branch -d` (never `-D`) and only if it is not checked out in
a worktree, is not `master` or `feat/*`, is an ancestor of `origin/master` or `master`, and is not
mentioned in `.handoff/*.md`.

Every action is appended as one JSON line to `<git-common-dir>/claude-session-cleanup.jsonl`.
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
    is_dir = entry.endswith("/")
    name = entry.rstrip("/").rsplit("/", 1)[-1]
    for pattern in REGENERABLE:
        if pattern.endswith("/"):
            if is_dir and name == pattern[:-1]:
                return True
        elif fnmatch.fnmatchcase(name, pattern):
            return True
    return False


def first_non_regenerable(directory: Path, rel: str) -> str | None:
    """First path under a collapsed ignored directory that is not regenerable (symlinks are not followed)."""
    try:
        children = sorted(os.scandir(directory), key=lambda e: e.name)
    except OSError:
        return rel  # cannot look inside: keep
    for child in children:
        child_rel = f"{rel}{child.name}"
        if child.is_dir(follow_symlinks=False):
            child_rel += "/"
            if is_regenerable(child_rel):
                continue
            found = first_non_regenerable(Path(child.path), child_rel)
            if found is not None:
                return found
        elif not is_regenerable(child_rel):
            return child_rel
    return None


def unclean_reason(wt_path: str) -> str | None:
    """None when the worktree holds nothing but regenerable ignored paths, else why it is not clean."""
    rc, out, err = run_git(["status", "--porcelain", "-z", "--ignored"], wt_path)
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
            # git collapses a directory holding only ignored files into one entry: look inside it
            inner = first_non_regenerable(Path(wt_path) / path, path) if path.endswith("/") else path
            if inner is None:
                continue
            return f"ignored file: {inner}"
        if "R" in code or "C" in code:
            index += 1  # a rename or copy carries its source as the next field
        kind = "ignored file" if code == "!!" else "untracked file" if code == "??" else "uncommitted change"
        return f"{kind}: {path}"
    return None


def newest_admin_mtime(wt_path: str) -> float | None:
    rc, out, _ = run_git(["rev-parse", "--absolute-git-dir"], wt_path)
    if rc != 0 or not out.strip():
        return None
    admin = Path(out.strip())
    times: list[float] = []
    for name in ("HEAD", "index", "logs/HEAD"):
        try:
            times.append((admin / name).stat().st_mtime)
        except OSError:
            continue
    return max(times) if times else None


def within(child: Path, parent: Path) -> bool:
    return child == parent or parent in child.parents


def in_use(wt_path: str, current: Path, main_path: str) -> bool:
    """The session runs in this worktree, or (not in the main checkout) it sits inside the session dir."""
    wt, cur, main = Path(wt_path).resolve(), current.resolve(), Path(main_path).resolve()
    if within(cur, wt):
        return True
    return within(wt, cur) and not within(cur, main)


def handoff_files_mentioning(main_path: str, needles: list[str]) -> str | None:
    """Name of the first `.handoff/*.md` file containing any needle, else None."""
    folder = Path(main_path) / ".handoff"
    try:
        files = sorted(folder.glob("*.md"))
    except OSError:
        return None
    for file in files:
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(needle and needle in text for needle in needles):
            return file.name
    return None


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


def cleanup(
    repo: str | Path,
    current: Path | None = None,
    now: float | None = None,
    min_idle_hours: float = MIN_IDLE_HOURS,
    dry_run: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    """Remove (or, in dry-run, report) the safe worktrees and branches; return what happened."""
    now = time.time() if now is None else now
    current = Path.cwd() if current is None else current
    report: dict[str, list[dict[str, Any]]] = {"removed_worktrees": [], "deleted_branches": [], "kept": []}
    worktrees = list_worktrees(repo)
    if not worktrees:
        return report
    main = worktrees[0]
    refs = integration_refs(main.path)
    idle_limit = min_idle_hours * 3600

    def keep(kind: str, target: str, reason: str, head: str, review: bool, idle: bool) -> None:
        report["kept"].append(
            {"kind": kind, "target": target, "reason": reason, "head": head, "review": review, "idle": idle}
        )

    gone: set[str] = set()  # paths of worktrees removed, or pruned because their directory is gone
    for wt in worktrees[1:]:
        if wt.bare:
            continue
        if wt.prunable:
            gone.add(wt.path)  # `git worktree prune` below drops its metadata; nothing to review
            continue
        if in_use(wt.path, current, main.path):
            keep("worktree", wt.path, "current session directory", wt.head, review=False, idle=False)
            continue
        mtime = newest_admin_mtime(wt.path)  # read before `git status` can touch the index
        idle = mtime is not None and now - mtime > idle_limit
        reason = worktree_keep_reason(wt, main.path, refs, idle, mtime is None, min_idle_hours)
        if reason is None:
            if dry_run:
                gone.add(wt.path)
                report["removed_worktrees"].append(
                    {
                        "target": wt.path,
                        "reason": "clean, merged, idle",
                        "head": wt.head,
                        "branch": short_ref(wt.branch),
                    }
                )
                continue
            rc, _, err = run_git(["worktree", "remove", wt.path], main.path)
            if rc == 0:
                gone.add(wt.path)
                report["removed_worktrees"].append(
                    {
                        "target": wt.path,
                        "reason": "clean, merged, idle",
                        "head": wt.head,
                        "branch": short_ref(wt.branch),
                    }
                )
                continue
            reason = f"git refused: {first_line(err)}"
        keep("worktree", wt.path, reason, wt.head, review=not wt.locked, idle=idle)

    if not dry_run:
        run_git(["worktree", "prune"], main.path)

    delete_branches(report, worktrees, gone, main.path, refs, now, idle_limit, dry_run)

    if not dry_run:
        write_log(report, main.path, now)
    return report


def worktree_keep_reason(
    wt: Worktree, main_path: str, refs: list[str], idle: bool, no_mtime: bool, min_idle_hours: float
) -> str | None:
    """First failing rule among b, c, d, e, f (rule a is checked by the caller), else None."""
    if wt.locked:
        return "locked"
    dirty = unclean_reason(wt.path)
    if dirty is not None:
        return dirty
    candidates = [r for r in refs if r != wt.branch]
    if not wt.head or not any(is_ancestor(wt.head, r, main_path) for r in candidates):
        return "HEAD not merged into origin/master, master or another feat/* branch"
    if no_mtime:
        return "idle time unknown"
    if not idle:
        return f"not idle for {min_idle_hours:g}h yet"
    mention = handoff_files_mentioning(main_path, [short_ref(wt.branch), Path(wt.path).name])
    if mention:
        return f"mentioned in handoff .handoff/{mention}"
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
) -> None:
    rc, out, _ = run_git(
        ["for-each-ref", "--format=%(refname)%09%(objectname)%09%(committerdate:unix)", "refs/heads/"],
        main_path,
    )
    if rc != 0:
        return
    checked_out = {wt.branch for wt in worktrees if wt.path not in gone and wt.branch}
    masters = [r for r in refs if r in ("refs/remotes/origin/master", "refs/heads/master")]
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
            report["kept"].append(
                {
                    "kind": "branch",
                    "target": name,
                    "reason": "not merged into origin/master or master",
                    "head": sha,
                    "review": True,
                    "idle": idle,
                }
            )
            continue
        mention = handoff_files_mentioning(main_path, [name])
        if mention:
            report["kept"].append(
                {
                    "kind": "branch",
                    "target": name,
                    "reason": f"mentioned in handoff .handoff/{mention}",
                    "head": sha,
                    "review": True,
                    "idle": idle,
                }
            )
            continue
        if not dry_run:
            rc, _, err = run_git(["branch", "-d", name], main_path)
            if rc != 0:
                report["kept"].append(
                    {
                        "kind": "branch",
                        "target": name,
                        "reason": f"git refused: {first_line(err)}",
                        "head": sha,
                        "review": True,
                        "idle": idle,
                    }
                )
                continue
        report["deleted_branches"].append({"target": name, "reason": "merged into master", "head": sha})


def write_log(report: dict[str, list[dict[str, Any]]], main_path: str, now: float) -> None:
    rows: list[dict[str, str]] = []
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now))
    for item in report["removed_worktrees"]:
        rows.append(
            {
                "ts": stamp,
                "action": "removed_worktree",
                "target": item["target"],
                "reason": item["reason"],
                "head": item["head"],
            }
        )
    for item in report["deleted_branches"]:
        rows.append(
            {
                "ts": stamp,
                "action": "deleted_branch",
                "target": item["target"],
                "reason": item["reason"],
                "head": item["head"],
            }
        )
    for item in report["kept"]:
        if item["review"]:
            rows.append(
                {
                    "ts": stamp,
                    "action": "kept",
                    "target": item["target"],
                    "reason": item["reason"],
                    "head": item["head"],
                }
            )
    if not rows:
        return
    rc, out, _ = run_git(["rev-parse", "--path-format=absolute", "--git-common-dir"], main_path)
    if rc != 0 or not out.strip():
        return
    try:
        with (Path(out.strip()) / LOG_NAME).open("a", encoding="utf-8") as handle:
            handle.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    except OSError:
        pass  # a log that cannot be written must not stop session start


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
    out: dict[str, Any] = {
        "systemMessage": (
            f"Cleanup: removed {len(removed_wt)} worktree(s), {len(deleted)} branch(es); "
            f"{len(review)} kept for review."
        ),
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


def main(argv: list[str]) -> int:
    dry_run, repo_arg = parse_args(argv)
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())
    repo = Path(repo_arg) if repo_arg else project
    if not repo.is_dir():
        return 0
    out = build_output(cleanup(repo, current=project, dry_run=dry_run), dry_run)
    if out is not None:
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception:  # a cleanup must never break session start
        sys.exit(0)
