"""marks: `harness marks`, member marks and schedule tables, plan-to-schedule matching.

STUB (2026-11-07): the command is registered so packages can be built independently; the module owner
replaces this file. Until then the command exits 3.
"""

from __future__ import annotations

import argparse
import sys

COMMAND = "marks"
HELP = "member marks and schedule tables, plan-to-schedule matching"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("work_dir", help="the intake work folder")


def run(args: argparse.Namespace) -> int:
    print(f"harness {COMMAND}: not implemented yet", file=sys.stderr)
    return 3
