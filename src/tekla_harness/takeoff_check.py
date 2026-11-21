"""`harness takeoff check` (E8d): the take-off on disk equals a fresh render and the AI slots stay the AI's.

Read-only. Every eligible part and `00-plan.md` is rendered once from one `TakeoffContext`, the part files
with the slots read from disk, and compared to the file. A written slot may hold no id, no code, no jargon
and no number that no generated line of its file shows (the prose rule of run 3's `check_takeoff.py`; its
ids, status, cover and shape rules hold by construction). stdout is one JSON document (`takeoff-output`
`$defs/check`); exit 0 ok, 1 problems.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tekla_harness.findings import _TIMES
from tekla_harness.schemas import validate
from tekla_harness.takeoff_plan import PLAN_FILE, render_plan
from tekla_harness.takeoff_render import (
    ELIGIBLE,
    PLACEHOLDER,
    SLOTS,
    TakeoffContext,
    TakeoffError,
    _markers,
    _problem,
    _subject,
    parse_slots,
    render_part,
)

EXIT_OK, EXIT_INVALID, EXIT_ENV = 0, 1, 3
JARGON = (
    "RR", "single_source", "two_sources", "axes", "centre", "found", "finding", "values.json", "cites",
    "hand_sum", "cluster", "outline", "entry", "scout", "reader", "manifest",
)  # fmt: skip
_JARGON = (
    re.compile(  # a listed word, its plural (`findings`, `centres`) or `entries`; `founded` still passes
        rf"(?<![\w.])(?:{'|'.join(map(re.escape, JARGON))})(?:e?s)?(?!\w)|(?<![\w.])entries(?!\w)",
        re.IGNORECASE,
    )
)
# A number of a slot or of a generated line, sign kept (a level below zero is a number).
_SIGNED = re.compile(r"(?<![\w#.\-])([-+]?\d+(?:\.\d+)?)(?![\w#\-])")
# The id formats the harness mints: findings F-012, questions Q-012, geometry items G-<10 hex>, text entries
# T<6>, marks P<6>, part-values rows R<3+>, grid view groups V<3>, sheets <space>#<nn>.
_ID = re.compile(
    r"(?<![\w-])(?:F-\d{3,}|Q-\d{3,}|G-[0-9a-f]{10}|T\d{6}|P\d{6}|R\d{3,}|V\d{3}|[^\W_][\w.-]*#\d{2,})(?!\w)"
)
_FILE = re.compile(r"^\d{2,}-.+\.md$")
Problem = dict[str, Any]


def _numbers(text: str) -> list[float]:
    """The standalone numbers of a text, signs kept, in order (see _SIGNED)."""
    return [float(m[1]) for m in _SIGNED.finditer(_TIMES.sub(" ", text))]


def _prose(name: str, lines: list[str], slots: dict[str, str], fresh: str, marks: set[str]) -> list[Problem]:
    """The `ai_*` problems of the slots of one file."""
    problems = []
    inside, generated = False, []
    for line in fresh.splitlines():
        inside = (inside or line.startswith("<!-- ai:")) and not line.startswith("<!-- /ai:")
        if not inside and not line.startswith(("#", "<!-- /ai:")):  # a heading number is not a value
            generated += _numbers(line)
    shown = {abs(n) for n in generated}
    for slot in SLOTS:
        start = lines.index(f"<!-- ai:{slot} -->") + 2
        if slots[slot].strip() in ("", PLACEHOLDER):
            problems.append(_problem("ai_slot_empty", name, start, f"ai:{slot} is empty or not written"))
            continue
        for at, text in enumerate(slots[slot].splitlines(), start):
            if "`" in text:
                problems.append(_problem("ai_code", name, at, "a backtick: commands are generated"))
            if ids := [m[0] for m in _ID.finditer(text) if m[0] not in marks]:
                problems.append(_problem("ai_id", name, at, f"id in a slot: {', '.join(ids)}"))
            if words := [m[0] for m in _JARGON.finditer(text)]:
                problems.append(_problem("ai_jargon", name, at, f"jargon: {', '.join(words)}"))
            problems += [
                _problem(
                    "ai_number",
                    name,
                    at,
                    f"{int(n) if n.is_integer() else n} is in no generated line of this file",
                )
                for n in dict.fromkeys(abs(n) for n in _numbers(text))
                if n not in shown
            ]
    return problems


def _rerun(name: str) -> str:
    return "rerun harness takeoff plan" if name == PLAN_FILE else "rerun harness takeoff render"


def _first_difference(disk: str, fresh: str, rerun: str) -> Problem | None:
    old, new = disk.splitlines(), fresh.splitlines()
    for at in range(max(len(old), len(new))):
        a, b = (old[at] if at < len(old) else ""), (new[at] if at < len(new) else "")
        if a != b:
            return {"line": at + 1, "detail": f"expected '{b}', found '{a}'; {rerun}"}
    return None


def check_files(ctx: TakeoffContext, out: Path) -> tuple[int, list[Problem]]:
    """(files checked, problems): the expected files that exist on disk, and what is wrong with the folder."""
    parts = {p["id"]: p for p in ctx.manifest["parts"]}
    expected = {PLAN_FILE: None} | {
        f"{n:02d}-{i}.md": parts[i] for i, n in ctx.rank.items() if ctx.status[i]["status"] in ELIGIBLE
    }
    on_disk = (
        sorted(p.name for p in out.iterdir() if p.is_file() and _FILE.match(p.name)) if out.is_dir() else []
    )
    problems = [
        _problem("file_missing", n, None, f"no such file: {_rerun(n)}") for n in expected if n not in on_disk
    ]
    problems += [
        _problem("file_unexpected", n, None, "no part of the manifest has this file name: delete it")
        for n in on_disk
        if n not in expected
    ]
    files = [n for n in on_disk if n in expected]
    for name in files:
        disk = (out / name).read_text(encoding="utf-8")
        lines, part = disk.splitlines(), expected[name]
        if part is None:
            fresh, slots, marks = render_plan(ctx), {}, set()
        else:
            slots = parse_slots(disk)
            if marker := _markers(name, lines, slots):
                problems += marker  # slots that cannot be read: no diff and no prose check
                continue
            fresh = render_part(ctx, part, slots)
            marks = {_subject(r) for r in ctx.values(part)}
        if diff := _first_difference(disk, fresh, _rerun(name)):
            problems.append(_problem("generated_differs", name, diff["line"], diff["detail"]))
        if part is not None:
            problems += _prose(name, lines, slots, fresh, marks)
    return len(files), sorted(problems, key=lambda p: (p["file"], p["line"] or 0, p["code"]))


def run_check(ctx: TakeoffContext, out: Path) -> int:
    """Print the check and return 0 ok, 1 problems. Raises TakeoffError."""
    files, problems = check_files(ctx, out)
    doc = {"command": "check", "ok": not problems, "files": files, "problems": problems}
    invalid = validate("takeoff-output", doc)
    if invalid:
        raise TakeoffError(EXIT_ENV, f"internal: the output does not match its schema: {invalid[0].message}")
    print(json.dumps(doc, ensure_ascii=False, indent=2))
    return EXIT_INVALID if problems else EXIT_OK
