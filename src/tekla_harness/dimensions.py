"""dimensions: `harness dimensions`, the DIMENSION entities of one drawing with measured vs printed values.

Read-only (no work-folder lock, nothing written). Output: schema `dimensions` on stdout.

`dimensions(work_dir, file_rel, ...)` opens the drawing of one inventory row: the converted DXF in the work
folder for a DWG, the input file for a native DXF (from `--input-dir`, as `harness marks` resolves it; a
native DXF without `--input-dir` is a usage error). The DXF must be the one the text index was built from
(sha256), else exit 1. Every DIMENSION is walked in layout tab order, also inside INSERTs (nested ones too,
`sheets.Walker`): a dimension inside a block is reported once per INSERT that places it (handle null,
`block_path` from the outermost INSERT inwards, `layout` the INSERT's layout).

Each row is `read_dxf.measure_dimension` (the probe's dimension_audit rules: text rule, measured value,
group 42, override value, tolerance, status) plus layer, sheet and block path. Values stay in the drawing's
units as stored, never converted, whatever unit the header declares or the engineer answered: `units`
only reports both. Angular dimensions keep ezdxf's measurement (degrees) and group 42 (radians). Only a
dimension placed directly in model space is passed as `is_model` (a negative DIMLFAC may then be proven
to mean factor 1); block content keeps the conservative default. Block content is measured on its block
definition (ezdxf `origin_of_copy`), in the block's own units: an INSERT's rotation or scale does not
change the value (the printed text does not change either); ezdxf's virtual copy only gives the sheet
and the layer. A row whose group 42 disagrees with the measurement is `not_compared`, whatever its text
rule.

Layer: the effective layer. Inside a block, a dimension on layer 0 takes the layer of the INSERT that
places it, resolved through nested INSERTs (AutoCAD's layer-0 rule); `--layer` filters on it. The schema
has one layer field, so the stored layer of such a dimension (0) is not reported.

Sheet: the detector sheet holding the dimension's text midpoint (else its definition point), by
`sheets.SheetLocator` on the sheets document; null on no sheet, on several, or without a sheets document.
`--sheet` and `--unassigned` need the sheets document (exit 2 without it, or for an unknown sheet id).

Exit codes: 0 ok, 1 inconsistent work folder or invalid output, 2 usage, 3 the DXF cannot be read (I/O).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from ezdxf.lldxf.const import DXFError

from tekla_harness.marks import _dxf_path
from tekla_harness.questions import UNITS_CONFIRM_CODE, QuestionsError, active_answers, load_ledger
from tekla_harness.read_dxf import measure_dimension
from tekla_harness.schemas import validate
from tekla_harness.sheet_text import (
    EXIT_INVALID,
    EXIT_USAGE,
    SCHEMA_VERSION,
    ReaderError,
    _details,
    _file_row,
    load_file,
    load_inventory,
)
from tekla_harness.sheets import SHEET_UNKNOWN, SheetLocator, Walker, layout_spaces, open_checked

COMMAND = "dimensions"
HELP = "every DIMENSION of one drawing: measured value, printed text, override, layer, sheet (read-only)"
EXIT_ENV = 3
UNITS = frozenset({"mm", "cm", "m", "in", "ft"})
_WALKED = frozenset({"DIMENSION", "INSERT"})  # INSERTs only to resolve layer 0 of their content


def _effective_layer(stored: Any, owner: int, insert_layers: dict[int, str | None]) -> str | None:
    """The layer an entity is drawn on: inside a block, layer 0 takes the effective layer of the INSERT
    that places it (AutoCAD's layer-0 rule, so recursively through nested INSERTs); otherwise as stored."""
    layer = None if stored is None else str(stored)
    if layer == "0" and owner in insert_layers:
        return insert_layers[owner]
    return layer


def _definition(copy: Any) -> Any:
    """The block-definition DIMENSION a virtual copy comes from (through nested INSERTs), else the copy.

    The copy's own measurement is not used: ezdxf transforms its points, but a linear dimension stored
    without an angle (group 50 absent, read as 0) keeps measuring along x, so in an INSERT rotated by 90
    degrees it measures about 0 (sample 270, block *U1792: 2.9e-08 for group 42 = 4000)."""
    origin = getattr(copy, "origin_of_copy", None)
    return copy if origin is None else origin


def _anchor(dim: Any) -> tuple[float | None, float | None]:
    """Where a dimension sits for the sheet test: its text midpoint, else its definition point."""
    for name in ("text_midpoint", "defpoint"):
        point = dim.dxf.get(name)
        if point is not None:
            return float(point[0]), float(point[1])
    return None, None


def _answered_unit(inv: Any, file_rel: str, warnings: list[str]) -> str | None:
    """The unit of the file's active units_confirm_all answer (read only), else None with a warning."""
    try:
        ledger = load_ledger(inv.work, inv.doc["project_id"], create=False)
    except QuestionsError as exc:
        warnings.append(f"the units answer was not read: {exc}")
        return None
    units = {
        (a.get("values") or {}).get("unit")
        for a in active_answers(ledger.answers).values()
        if a["code"] == UNITS_CONFIRM_CODE and a["file"] == file_rel
    }
    if not units:
        return None
    if len(units) > 1 or not units <= UNITS:
        warnings.append(f"{file_rel}: the active {UNITS_CONFIRM_CODE} answers give no single valid unit")
        return None
    return str(next(iter(units)))


def _open(inv: Any, loaded: Any, input_dir: Path | None) -> Any:
    path, why = _dxf_path(inv.work, loaded, input_dir)
    if path is None:
        raise ReaderError(EXIT_USAGE, f"{loaded.rel}: {why}")
    if not path.is_file():
        code = EXIT_INVALID if loaded.row["format"] == "dwg" else EXIT_USAGE
        raise ReaderError(code, f"{loaded.rel}: DXF not found: {path}")
    try:
        return open_checked(path, loaded.text_index)
    except ValueError as exc:
        raise ReaderError(EXIT_INVALID, f"{loaded.rel}: {exc}") from exc
    except DXFError as exc:
        raise ReaderError(EXIT_INVALID, f"{loaded.rel}: the DXF cannot be read: {exc}") from exc
    except OSError as exc:
        raise ReaderError(EXIT_ENV, f"{loaded.rel}: the DXF cannot be read: {exc}") from exc


def dimensions(
    work_dir: Path | str,
    file_rel: str,
    *,
    sheet: str | None = None,
    unassigned: bool = False,
    layer: str | None = None,
    max_rows: int | None = None,
    input_dir: Path | str | None = None,
    check_inputs: bool = False,
) -> dict[str, Any]:
    """The dimensions document of one drawing (nothing written). Raises ReaderError."""
    if sheet is not None and unassigned:
        raise ReaderError(EXIT_USAGE, "give --sheet or --unassigned, not both")
    if max_rows is not None and max_rows < 1:
        raise ReaderError(EXIT_USAGE, "--max must be at least 1")
    inv = load_inventory(work_dir)
    loaded = load_file(inv, _file_row(inv, file_rel), check_inputs=check_inputs)
    if loaded.skip is not None or loaded.text_index is None:
        raise ReaderError(EXIT_USAGE, f"{file_rel} cannot be read: {loaded.skip}")
    warnings = [f"{file_rel}: {w}" for w in loaded.warnings]
    if (sheet is not None or unassigned) and loaded.sheets is None:
        raise ReaderError(
            EXIT_USAGE, f"--sheet / --unassigned need the sheets document: {'; '.join(warnings)}"
        )
    if sheet is not None:
        assert loaded.sheets is not None
        ids = [s["sheet_id"] for s in loaded.sheets["sheets"]]
        if sheet not in ids:
            raise ReaderError(
                EXIT_USAGE, f"{file_rel} has no sheet '{sheet}' (sheets: {', '.join(ids) or 'none'})"
            )
    doc = _open(inv, loaded, None if input_dir is None else Path(input_dir).resolve())
    handles_ok = bool(loaded.text_index["file"]["handles_reliable"])
    locator = None if loaded.sheets is None else SheetLocator(loaded.sheets)
    walker = Walker(doc, handles_ok)
    rows: list[dict[str, Any]] = []
    for space, layout, is_model in layout_spaces(doc):
        insert_layers: dict[int, str | None] = {}  # INSERT occurrence serial -> its effective layer
        for placed in walker.walk(layout, space, _WALKED):
            dim = placed.entity
            effective = _effective_layer(dim.dxf.get("layer"), placed.owner, insert_layers)
            if dim.dxftype() == "INSERT":
                insert_layers[placed.serial] = effective
                continue
            block_path = list(placed.block_path)
            row = measure_dimension(
                _definition(dim) if block_path else dim,
                layout=str(layout.name),
                is_model=is_model and not block_path,
                in_block=bool(block_path),
                handles_ok=handles_ok,
            )
            if block_path:
                row["handle"] = None  # a placement of the definition, not the definition itself
            on: str | None = None
            if locator is not None:
                x, y = _anchor(dim)
                found = locator.locate(space, x, y)
                on = None if found == SHEET_UNKNOWN else found
            row.update(layer=effective, sheet=on, block_path=block_path)
            rows.append(row)
    if walker.skipped:
        warnings.append(f"{file_rel}: some INSERTs were not expanded: {dict(sorted(walker.skipped.items()))}")
    folded = None if layer is None else layer.casefold()
    matched = [
        r
        for r in rows
        if (sheet is None or r["sheet"] == sheet)
        and (not unassigned or r["sheet"] is None)
        and (folded is None or (r["layer"] or "").casefold() == folded)
    ]
    shown = matched if max_rows is None else matched[:max_rows]
    if len(shown) < len(matched):
        warnings.append(
            f"dimensions truncated: {len(shown)} of {len(matched)} matching dimensions returned; rerun with "
            f"--max {len(matched)} to get all of them"
        )
    declared = (loaded.row["units"] or {}).get("value")
    out = {
        "schema_version": SCHEMA_VERSION,
        "kind": "dimensions",
        "project_id": inv.doc["project_id"],
        "file": file_rel,
        "query": {"sheet": sheet, "unassigned": unassigned, "layer": layer, "max": max_rows},
        "units": {
            "declared": None if declared in (None, "unknown") else declared,
            "answered": _answered_unit(inv, file_rel, warnings),
            "converted": False,
        },
        "counts": {
            "dimensions": len(rows),
            "matched": len(matched),
            "returned": len(shown),
            "omitted": len(matched) - len(shown),
            "truncated": len(shown) < len(matched),
            "by_status": dict(sorted(Counter(r["status"] for r in matched).items())),
            "by_text_rule": dict(sorted(Counter(r["text_rule"] for r in matched).items())),
        },
        "dimensions": shown,
        "warnings": warnings,
    }
    problems = validate("dimensions", out)
    if problems:
        raise ReaderError(EXIT_INVALID, f"internal error: output is invalid: {_details(problems)}")
    return out


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
    try:
        doc = dimensions(
            Path(args.work_dir),
            args.file,
            sheet=args.sheet,
            unassigned=args.unassigned,
            layer=args.layer,
            max_rows=args.max,
            input_dir=Path(args.input_dir) if args.input_dir else None,
        )
    except ReaderError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    for warning in doc["warnings"]:
        if warning.startswith("dimensions truncated"):
            print(warning, file=sys.stderr)
    print(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False))
    return 0
