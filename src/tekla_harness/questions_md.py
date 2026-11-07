"""questions_md: `harness questions-md`, render questions.md from every question source.

STUB (2026-11-07): the command is registered so packages can be built independently; the module owner
replaces this file. Until then the command exits 3.
"""

from __future__ import annotations

import argparse
import sys

COMMAND = "questions-md"
HELP = "render questions.md (Vietnamese) from every question source of a work folder"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("work_dir", help="the intake work folder")


def run(args: argparse.Namespace) -> int:
    print(f"harness {COMMAND}: not implemented yet", file=sys.stderr)
    return 3
