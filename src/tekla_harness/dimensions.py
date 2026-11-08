"""dimensions: `harness dimensions`, the DIMENSION entities of one drawing with measured vs printed values.

Read-only (no work-folder lock). Output: schema `dimensions` on stdout. Rows come from
`read_dxf.measure_dimension`; values stay in the drawing's units, never converted.

Tool wave 2 seam: the command is registered and exits 3 (not implemented yet); package P4 implements it.
"""

from __future__ import annotations

import argparse
import sys

COMMAND = "dimensions"
HELP = "every DIMENSION of one drawing: measured value, printed text, override, layer, sheet (read-only)"
EXIT_ENV = 3


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "work_dir", help="the --out folder of `harness intake` (after `harness read-structure`)"
    )
    parser.add_argument("file", help="input-relative path of the drawing, as in inventory.json")
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--sheet", help="only this detector sheet id (see list-sheets), e.g. model#01")
    where.add_argument(
        "--unassigned", action="store_true", help="only dimensions on no sheet or on several sheets"
    )
    parser.add_argument("--layer", help="only this layer (case-insensitive)")
    parser.add_argument("--max", type=int, default=None, help="rows returned at most (default: all)")
    parser.add_argument(
        "--input-dir", help="the intake input folder (needed when the drawing is a native DXF file)"
    )


def run(args: argparse.Namespace) -> int:
    del args
    print(f"harness {COMMAND}: not implemented yet (tool wave 2, package P4)", file=sys.stderr)
    return EXIT_ENV
