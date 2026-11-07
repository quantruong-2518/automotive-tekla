"""findings: `harness finding`, record a reader finding tied to extracted entries.

STUB (2026-11-07): the command is registered so packages can be built independently; the module owner
replaces this file. Until then the command exits 3.
"""

from __future__ import annotations

import argparse
import sys

COMMAND = "finding"
HELP = "record a drawing-reader finding tied to extracted entries (reader-findings.json)"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("work_dir", help="the intake work folder")


def run(args: argparse.Namespace) -> int:
    print(f"harness {COMMAND}: not implemented yet", file=sys.stderr)
    return 3
