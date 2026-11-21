"""`harness takeoff`: the take-off files of the parts (E8).

`render W (--part X | --all) [--out DIR]` writes `takeoff/<nn>-<part>.md` for each eligible part (status
checked, reviewed or locked); everything in it is generated from rows and records except the two AI slots,
which are kept from the file on disk. `plan [--out DIR]` (E8c) writes `00-plan.md`: every part with its
status and the open blocking questions in the lots they block. `check [--out DIR]` (E8d, read-only) compares
every file with a fresh render and checks the AI slots for ids, code, jargon and numbers of their own.
stdout is one JSON document; exit codes: 0 ok, 1 a part is not eligible, a cited record is missing or the
check found problems, 2 usage, 3 environment.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from tekla_harness.findings import FindingError
from tekla_harness.part_values import BOOKKEEPING
from tekla_harness.parts import ManifestAccessError
from tekla_harness.questions import QuestionsError, write_text_atomic
from tekla_harness.questions_md import QuestionsMdError
from tekla_harness.schemas import validate
from tekla_harness.sheet_text import ReaderError
from tekla_harness.status import StatusError
from tekla_harness.takeoff_check import run_check
from tekla_harness.takeoff_plan import run_plan
from tekla_harness.takeoff_render import (
    ELIGIBLE,
    OUT_NAME,
    TakeoffContext,
    TakeoffError,
    _markers,
    parse_slots,
    render_part,
    shown_path,
)

COMMAND = "takeoff"
HELP = "Write the take-off files of the parts (render), the plan of the lots (plan) or check them (check)."
EXIT_OK, EXIT_INVALID, EXIT_USAGE, EXIT_ENV = 0, 1, 2, 3
ERRORS = (
    TakeoffError, StatusError, ReaderError, QuestionsError, QuestionsMdError, FindingError,
    ManifestAccessError,
)  # fmt: skip


def add_arguments(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True, metavar="ACTION")
    render = actions.add_parser("render", help="Write takeoff/<nn>-<part>.md for each eligible part.")
    render.add_argument("work_dir", help="The work folder (holds parts/manifest.json).")
    which = render.add_mutually_exclusive_group(required=True)
    which.add_argument("--part", help="Render this part only.")
    which.add_argument(
        "--all", action="store_true", help="Render every eligible part; remove the stale files."
    )
    render.add_argument("--out", help="The folder of the files (default: takeoff/ beside the work folder).")
    render.set_defaults(handler=_render)
    plan = actions.add_parser(
        "plan",
        help="Write 00-plan.md: every part with its status, and the lots with the questions that block them.",
    )
    plan.add_argument("work_dir", help="The work folder (holds parts/manifest.json).")
    plan.add_argument("--out", help="The folder of the file (default: takeoff/ beside the work folder).")
    plan.set_defaults(handler=_plan)
    check = actions.add_parser(
        "check",
        help="Check that the files equal a fresh render and that the AI slots hold no ids, code, jargon or "
        "numbers of their own (read-only).",
    )
    check.add_argument("work_dir", help="The work folder (holds parts/manifest.json).")
    check.add_argument("--out", help="The folder of the files (default: takeoff/ beside the work folder).")
    check.set_defaults(handler=_check)


def _files(out: Path, part: str) -> list[Path]:
    pattern = re.compile(rf"^\d{{2,}}-{re.escape(part)}\.md$")
    return sorted(p for p in out.iterdir() if p.is_file() and pattern.match(p.name)) if out.is_dir() else []


def _slots(out: Path, name: str, part: str) -> dict[str, str]:
    """The slots of the target file, else of the file the part had under another number; `{}` when no such
    file exists. A file with damaged markers raises `TakeoffError` (exit 1): its text is never replaced."""
    target = out / name
    for path in [target, *(p for p in _files(out, part) if p != target)]:
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            slots = parse_slots(text)
            if problems := _markers(path.name, text.splitlines(), slots):
                raise TakeoffError(
                    EXIT_INVALID,
                    f"{path.name}: the AI slot markers are damaged ({problems[0]['detail']}): fix them, "
                    "then rerun (harness takeoff check lists them)",
                )
            return slots
    return {}


def _out_folder(args: argparse.Namespace, ctx: TakeoffContext) -> Path | None:
    """The folder of the files; None (after a message) when `--out` names something that is not a folder.
    Sets `ctx.shown`, the work folder as the generated text names it."""
    out = Path(args.out).resolve() if args.out else ctx.work.parent / OUT_NAME
    if out.exists() and not out.is_dir():
        print(f"harness takeoff {args.action}: --out {args.out} is not a folder", file=sys.stderr)
        return None
    ctx.shown = shown_path(ctx.work, out)  # the commands in the text run from the take-off folder
    return out


def _plan(args: argparse.Namespace) -> int:
    ctx = TakeoffContext.load(args.work_dir)
    out = _out_folder(args, ctx)
    return EXIT_USAGE if out is None else run_plan(ctx, out)


def _check(args: argparse.Namespace) -> int:
    ctx = TakeoffContext.load(args.work_dir)
    out = _out_folder(args, ctx)
    return EXIT_USAGE if out is None else run_check(ctx, out)


def _render(args: argparse.Namespace) -> int:
    ctx = TakeoffContext.load(args.work_dir)
    out = _out_folder(args, ctx)
    if out is None:
        return EXIT_USAGE
    parts = {p["id"]: p for p in ctx.manifest["parts"]}
    skipped = [
        {"part": i, "status": ctx.status[i]["status"]}
        for i in ctx.rank
        if ctx.status[i]["status"] not in ELIGIBLE and (args.all or i == args.part)
    ]
    problem = None
    if args.part and args.part not in parts:
        problem = f"unknown part {args.part}"
    elif args.part and parts[args.part]["kind"] == BOOKKEEPING:
        problem = f"part {args.part} is bookkeeping: it has no take-off file"
    elif args.part and skipped:
        problem = f"part {args.part} is {skipped[0]['status']}: only checked, reviewed or locked parts render"
    texts: dict[str, str] = {}
    removed: list[Path] = []
    if problem is None:
        wanted = [i for i in ctx.rank if i == args.part or (args.all and ctx.status[i]["status"] in ELIGIBLE)]
        for i in wanted:
            name = f"{ctx.rank[i]:02d}-{i}.md"
            texts[name] = render_part(ctx, parts[i], _slots(out, name, i))
            removed += [p for p in _files(out, i) if p.name != name]
        if args.all:
            removed += [p for s in skipped for p in _files(out, s["part"])]
    written, unchanged = [], []
    for name, text in texts.items():
        path = out / name
        if path.is_file() and path.read_text(encoding="utf-8") == text:
            unchanged.append(name)
            continue
        out.mkdir(parents=True, exist_ok=True)
        write_text_atomic(path, text)
        written.append(name)
    for path in removed:
        path.unlink()
    doc: dict[str, Any] = {
        "command": "render", "out": str(out), "written": written, "unchanged": unchanged,
        "removed": sorted(p.name for p in removed), "skipped": skipped,
    }  # fmt: skip
    problems = validate("takeoff-output", doc)
    if problems:
        raise TakeoffError(EXIT_ENV, f"internal: the output does not match its schema: {problems[0].message}")
    print(json.dumps(doc, ensure_ascii=False, indent=2))
    if problem:
        print(f"harness takeoff render: {problem}", file=sys.stderr)
        return EXIT_INVALID
    return EXIT_OK


def run(args: argparse.Namespace) -> int:
    try:
        return int(args.handler(args))
    except ERRORS as exc:
        print(f"harness takeoff {args.action}: {exc}", file=sys.stderr)
        return int(getattr(exc, "exit_code", EXIT_ENV))
    except OSError as exc:
        print(f"harness takeoff {args.action}: {exc}", file=sys.stderr)
        return EXIT_ENV
