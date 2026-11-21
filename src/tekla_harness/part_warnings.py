"""Warnings of the part manifest check that read the drawings, not the manifest (E4b).

`grid_origin_other_block`: a plan sheet filed under one building block whose grid lines up with the
sheets of another block is probably misfiled, and a part reader would build on the wrong origin.
The rule reads `structure/<file>.grids.json`.

`linework_duplicate`: a plan of one block whose outlines and symbols are a copy of another block's plan
(same positions from the grid origin) gave wrong member sizes; both part readers must see the twin. The
rule reads the drawing (one `read_geometry` walk per file).

Both rules measure in drawing units: 1 mm is `geometry._UNIT_TOL[unit]`, the unit being the file's answered
one only (the engineer's `units_confirm_all` answer; the declared unit of `inventory.json` is never a
fall-back). A file without an answered unit is skipped as `unit_unknown`, never guessed: with no active
answer the rules pass `unanswered_note(file)` to their `notes` (`harness part manifest-check` raises
`unit_unanswered`), and with an answer that cannot be read they pass the warning text (`unit_answer_unread`).
Pure functions: nothing is written. `harness part manifest-check` runs them (`parts_manifest.py`) and
`revision_from_table` beside them.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tekla_harness.contents import DEFAULT_MAX_LONG_MM
from tekla_harness.dimensions import _answered_unit
from tekla_harness.geometry import _UNIT_TOL, _cell, read_geometry
from tekla_harness.grids import FAMILY_ANGLE_TOL
from tekla_harness.sheet_text import STRUCTURE_DIR, Inventory, _file_row, load_inventory, read_json

GRID_ORIGIN = "grid_origin_other_block"
LINEWORK = "linework_duplicate"
UNIT_UNKNOWN = "unit_unknown"
FEW_ITEMS = "few_items"
MIN_OTHER_SHEETS = 2  # sheets of another block a sheet must line up with before it is a warning
LINEWORK_MIN_ITEMS = 10  # items a sheet needs on a part's layers before it is compared
LINEWORK_RATIO = 0.90  # share of the larger signature that two sheets must have in common to warn

SheetKey = tuple[str, str]


@dataclass(frozen=True)
class GridRef:
    """The first labelled axis with a line of a family: enough to place the drawing origin
    (`position - offset * normal`)."""

    label: str
    position: float  # midpoint coordinate of the line (x for an x family, y for a y family)
    offset: float
    normal: float  # the +-1 component of the family normal along the family's direction


@dataclass(frozen=True)
class GridFamily:
    direction: str  # "x": vertical axes (normal nearer x); "y": horizontal axes
    axes: tuple[tuple[str, float], ...]  # (label, position) of the axes with a label and a line
    origin_axis: GridRef | None


@dataclass(frozen=True)
class PlanGrid:
    families: tuple[GridFamily, GridFamily]  # sorted: x family first, then y family

    def family(self, direction: str) -> GridFamily:
        return next(f for f in self.families if f.direction == direction)


def _angle_mod_180(angle: float) -> float:
    return angle % 180.0


def _near(angle: float, target: float) -> bool:
    """`angle` is within FAMILY_ANGLE_TOL of `target` degrees, both modulo 180 (a line has no sense)."""
    diff = abs(_angle_mod_180(angle) - target)
    return min(diff, 180.0 - diff) <= FAMILY_ANGLE_TOL


def _axes(fam: dict[str, Any]) -> list[dict[str, Any]]:
    return [ax for ax in fam["axes"] if ax.get("label") and ax.get("line")]


def _family(fam: dict[str, Any], direction: str) -> GridFamily:
    axes: list[tuple[str, float]] = []
    seen: set[str] = set()
    origin: GridRef | None = None
    index = 0 if direction == "x" else 1
    for ax in _axes(fam):
        label = str(ax["label"]["value"])
        start, end = ax["line"]["start"], ax["line"]["end"]
        mid = (float(start[index]) + float(end[index])) / 2
        if origin is None:
            origin = GridRef(label, mid, float(ax["offset"]), float(fam["normal"][index]))
        if label not in seen:  # a label drawn twice on one family keeps its first line
            seen.add(label)
            axes.append((label, mid))
    return GridFamily(direction, tuple(axes), origin)


def _is_plan_pair(group: dict[str, Any]) -> bool:
    fams = group["families"]
    if len(fams) != 2:
        return False
    diff = abs(_angle_mod_180(float(fams[0]["angle_deg"])) - _angle_mod_180(float(fams[1]["angle_deg"])))
    return abs(min(diff, 180.0 - diff) - 90.0) <= FAMILY_ANGLE_TOL


def _plan_grid(doc: dict[str, Any], sheet: str) -> PlanGrid | str:
    pairs = [g for g in doc["groups"] if g["sheet"] == sheet and _is_plan_pair(g)]
    if not pairs:
        return "no_plan_grid"
    counts = [sum(len(_axes(f)) for f in g["families"]) for g in pairs]
    best = max(counts)
    if counts.count(best) > 1:
        return "several_plan_grids"
    chosen = pairs[counts.index(best)]
    built = []
    for fam in chosen["families"]:
        angle = float(fam["angle_deg"])
        if _near(angle, 0.0):
            built.append(_family(fam, "y"))
        elif _near(angle, 90.0):
            built.append(_family(fam, "x"))
        else:
            return "rotated_grid"
    built.sort(key=lambda f: f.direction)
    return PlanGrid((built[0], built[1]))


def _load(work: Path, file: str) -> dict[str, Any] | None:
    rel = f"{STRUCTURE_DIR}/{file}.grids.json"
    if not (work / rel).is_file():
        return None
    return read_json(work / rel, rel)


def plan_grid(work: Path, file: str, sheet: str) -> PlanGrid | str:
    """The sheet's plan grid, or the skipped reason: `no_grids_document`, `no_plan_grid`,
    `several_plan_grids` or `rotated_grid`.

    The plan grid is the group of the sheet with exactly two families 90 degrees apart (within
    FAMILY_ANGLE_TOL); of several, the one with the most labelled axes (a tie is `several_plan_grids`).
    Raises ReaderError when the grids document is unreadable."""
    doc = _load(work, file)
    return "no_grids_document" if doc is None else _plan_grid(doc, sheet)


def in_scope_sheets(manifest: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(file, sheet, block) of every sheet of a member part with a known block, minus the sheets listed
    under two blocks (`sheet_in_two_blocks`). Sorted."""
    block_ids = {b["id"] for b in manifest.get("blocks", [])}
    blocks_of: dict[SheetKey, set[str]] = {}
    for part in manifest["parts"]:
        if part["kind"] != "member" or part.get("block") not in block_ids:
            continue
        for s in part.get("sheets", []):
            blocks_of.setdefault((s["file"], s["sheet"]), set()).add(part["block"])
    return sorted((f, s, next(iter(b))) for (f, s), b in blocks_of.items() if len(b) == 1)


def unanswered_text(file: str) -> str:
    """The detail of the problem `unit_unanswered`: the file has no active units answer."""
    return f"answer the units question of `{file}` first"


def unanswered_note(file: str) -> str:
    """The note `file_unit` adds for a file with no active units answer: `<file>: <unanswered_text>`."""
    return f"{file}: {unanswered_text(file)}"


def file_unit(inv: Inventory, file: str, notes: list[str] | None = None) -> str | None:
    """The unit of a file: the answered one (`units_confirm_all`), never the declared one. None, with a line
    added to `notes`, when the file has no active answer (`unanswered_note`) or the answer cannot be read (the
    ledger, or active answers with no single valid unit: each warning text is added as `<file>: <text>`).
    Raises ReaderError when the inventory does not list the file."""
    _file_row(inv, file)
    unread: list[str] = []
    answered = _answered_unit(inv, file, unread)
    if unread:
        if notes is not None:
            notes += [text if text.startswith(f"{file}: ") else f"{file}: {text}" for text in unread]
        return None
    if answered not in _UNIT_TOL:
        if notes is not None:
            notes.append(unanswered_note(file))
        return None
    return answered


def _aligned(a: PlanGrid, b: PlanGrid, tol: float) -> tuple[str, list[str]] | None:
    """The direction and shared labels in which the two grids coincide: at least one shared label and
    every shared label within `tol` (1 mm in drawing units). x is tried before y."""
    for direction in ("x", "y"):
        pa, pb = dict(a.family(direction).axes), dict(b.family(direction).axes)
        shared = sorted(set(pa) & set(pb))
        if shared and all(abs(pa[k] - pb[k]) <= tol for k in shared):
            return direction, shared
    return None


def grid_origin_warnings(
    work: Path, manifest: dict[str, Any], notes: list[str] | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(warnings, skipped), each sorted; reads the grids documents only.

    A sheet of block B warns once per other block B2 when its plan grid lines up with at least two
    sheets of B2 (same file) and with none of the other sheets of B. `skipped` lists the sheets with no
    usable plan grid or whose file has no known unit (`code`, `file`, `sheet`, `reason`). `manifest` is
    trusted to be schema valid. `notes`: see `file_unit`. Raises ReaderError when `inventory.json` is
    unreadable or lacks a file."""
    scope = in_scope_sheets(manifest)
    block_of = {(f, s): b for f, s, b in scope}
    warnings: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    files = sorted({f for f, _, _ in scope})
    if not files:
        return warnings, skipped
    inv = load_inventory(work)
    for file in files:
        unit = file_unit(inv, file, notes)
        if unit is None:
            skipped += [
                {"code": GRID_ORIGIN, "file": file, "sheet": s, "reason": UNIT_UNKNOWN}
                for f, s, _ in scope
                if f == file
            ]
            continue
        tol = _UNIT_TOL[unit]
        doc = _load(work, file)
        grids: dict[str, PlanGrid] = {}
        for f, sheet, _ in scope:
            if f != file:
                continue
            found = "no_grids_document" if doc is None else _plan_grid(doc, sheet)
            if isinstance(found, str):
                skipped.append({"code": GRID_ORIGIN, "file": file, "sheet": sheet, "reason": found})
            else:
                grids[sheet] = found
        for sheet, grid in sorted(grids.items()):
            block = block_of[(file, sheet)]
            aligned = {t: a for t, g in grids.items() if t != sheet and (a := _aligned(grid, g, tol))}
            own = [t for t in aligned if block_of[(file, t)] == block]
            if own:
                continue
            for other in sorted({block_of[(file, t)] for t in aligned}):
                names = sorted(t for t in aligned if block_of[(file, t)] == other)
                if len(names) < MIN_OTHER_SHEETS:
                    continue
                direction, labels = aligned[names[0]]
                warnings.append(
                    {
                        "id": f"{GRID_ORIGIN}|{file}|{sheet}|{other}",
                        "code": GRID_ORIGIN,
                        "part": None,
                        "file": file,
                        "sheet": sheet,
                        "detail": (
                            f"listed under {block}; aligned on {direction} ({' '.join(labels)}) with "
                            f"{len(names)} sheet(s) of {other} ({', '.join(names)}), {len(own)} of {block}"
                        ),
                    }
                )
    warnings.sort(key=lambda w: w["id"])
    skipped.sort(key=lambda s: (s["file"], s["sheet"], s["code"], s["reason"]))
    return warnings, skipped


def _origin(grid: PlanGrid) -> tuple[float, float] | None:
    """The drawing origin (x, y) a plan grid implies: per family, the first labelled axis with a line gives
    `position - offset * normal`. None when a family has no such axis."""
    x, y = grid.family("x").origin_axis, grid.family("y").origin_axis
    if x is None or y is None:
        return None
    return x.position - x.offset * x.normal, y.position - y.offset * y.normal


@dataclass(frozen=True)
class _Member:
    """A member part that can be tested: its block, layers (outline then symbol) and plan sheets."""

    id: str
    block: str
    layers: tuple[str, ...]
    sheets: tuple[SheetKey, ...]


def _plan_sheets(part: dict[str, Any], block_of: dict[SheetKey, str]) -> set[SheetKey]:
    return {
        (s["file"], s["sheet"])
        for s in part.get("sheets", [])
        if s.get("role") == "plan" and (s["file"], s["sheet"]) in block_of
    }


def _members(manifest: dict[str, Any], block_of: dict[SheetKey, str], block_ids: set[str]) -> list[_Member]:
    """The member parts with a block of the manifest and at least one layer, with their plan sheets that are
    in scope."""
    found = []
    for part in manifest["parts"]:
        layers = part.get("layers") or {}
        names = tuple(dict.fromkeys([*layers.get("outline", []), *layers.get("symbol", [])]))
        if part["kind"] == "member" and part.get("block") in block_ids and names:
            found.append(
                _Member(part["id"], part["block"], names, tuple(sorted(_plan_sheets(part, block_of))))
            )
    return found


def _signature(
    items: list[Any], layers: tuple[str, ...], origin: tuple[float, float], tol: float, max_long: float
) -> Counter[tuple[Any, ...]]:
    """The multiset of the items on `layers` (case-blind): kind, size and centre from `origin`, rounded to
    `tol`. An outline longer than `max_long` is a frame and is left out."""
    folded = {name.casefold() for name in layers}
    ox, oy = origin

    def r(value: float) -> int:
        return _cell(value, tol)

    keys: Counter[tuple[Any, ...]] = Counter()
    for i in items:
        layer = i.layer.casefold()
        if layer not in folded:
            continue
        cx, cy = i.centre
        if i.kind == "circle":
            keys[(layer, "c", r(i.diameter or 0.0), r(cx - ox), r(cy - oy))] += 1
        elif i.kind == "outline" and (i.long or 0.0) <= max_long:
            keys[(layer, "o", r(i.short or 0.0), r(i.long or 0.0), r(cx - ox), r(cy - oy))] += 1
    return keys


@dataclass
class _Outcome:
    warnings: list[dict[str, Any]]
    skipped: dict[SheetKey, str]  # sheet -> reason, a sheet no pair could test
    thin: set[SheetKey]  # sheets with too few items in some pair
    tested: set[SheetKey]  # sheets that took part in a compared pair


def _compare_file(
    work: Path,
    inv: Inventory,
    file: str,
    pairs: list[tuple[_Member, SheetKey, SheetKey]],
    block_of: dict[SheetKey, str],
    input_dir: Path | None,
    out: _Outcome,
    notes: list[str] | None,
) -> None:
    unit = file_unit(inv, file, notes)
    sheets = sorted({k for _, s, t in pairs for k in (s, t)})
    if unit is None:
        out.skipped.update({k: UNIT_UNKNOWN for k in sheets})
        return
    tol = _UNIT_TOL[unit]
    doc = _load(work, file)
    origins: dict[SheetKey, tuple[float, float]] = {}
    for key in sheets:
        found = "no_grids_document" if doc is None else _plan_grid(doc, key[1])
        origin = None if isinstance(found, str) else _origin(found)
        if origin is not None:
            origins[key] = origin
        else:
            out.skipped[key] = found if isinstance(found, str) else "no_plan_grid"
    pairs = [(m, s, t) for m, s, t in pairs if s in origins and t in origins]
    if not pairs:
        return
    read = read_geometry(
        work,
        file,
        sheet=sorted({k[1] for k in origins}),
        layer=list(dict.fromkeys(name for m, _, _ in pairs for name in m.layers)),
        max_rows=10**9,
        tol=tol,
        input_dir=input_dir,
    )
    max_long = DEFAULT_MAX_LONG_MM * tol
    sigs: dict[tuple[str, SheetKey], Counter[tuple[Any, ...]]] = {}
    for m, s, t in pairs:
        for key in (s, t):
            if (m.id, key) not in sigs:
                region = read.regions.get(key[1])
                items = [] if region is None else list(region.items.values())
                sigs[(m.id, key)] = _signature(items, m.layers, origins[key], tol, max_long)
        a, b = sigs[(m.id, s)], sigs[(m.id, t)]
        few = [k for k, sig in ((s, a), (t, b)) if sum(sig.values()) < LINEWORK_MIN_ITEMS]
        if few:
            out.thin.update(few)
            continue
        out.tested.update((s, t))
        size = max(sum(a.values()), sum(b.values()))
        common = sum((a & b).values())
        ratio = common / size
        if ratio >= LINEWORK_RATIO:
            out.warnings.append(
                {
                    "id": f"{LINEWORK}|{m.id}|{file}|{s[1]}|{t[1]}",
                    "code": LINEWORK,
                    "part": m.id,
                    "file": file,
                    "sheet": s[1],
                    "detail": (
                        f"layers {', '.join(m.layers)}: {common} of {size} items equal {t[1]} "
                        f"({block_of[t]}) from the grid origin, ratio {ratio:.3f}"
                    ),
                }
            )


def linework_warnings(
    work: Path,
    manifest: dict[str, Any],
    input_dir: Path | None = None,
    notes: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(warnings, skipped), each sorted; one `read_geometry` walk per file.

    For each member part P with layers, each plan sheet s of P is compared with each plan sheet t of a member
    part of another block (same file): both sheets are read on P's layers, as `(layer, size, centre from the
    plan grid's origin)` multisets, frames left out. Warns when `ratio = |A and B| / max(|A|, |B|)` is at
    least LINEWORK_RATIO and both hold LINEWORK_MIN_ITEMS items; the twin part gets its own warning from its
    own pass. `skipped` lists the sheets that no pair could test (`code`, `file`, `sheet`, `reason`):
    `unit_unknown`, the plan-grid reasons of `plan_grid`, or `few_items`. `manifest` is trusted to be schema
    valid. `notes`: see `file_unit`. Raises ReaderError when a file cannot be read; `input_dir` is where a
    native DXF lives."""
    block_of = {(f, s): b for f, s, b in in_scope_sheets(manifest)}
    block_ids = {b["id"] for b in manifest.get("blocks", [])}
    every = sorted(
        {
            k
            for part in manifest["parts"]
            if part["kind"] == "member" and part.get("block") in block_ids
            for k in _plan_sheets(part, block_of)
        }
    )
    by_file: dict[str, list[tuple[_Member, SheetKey, SheetKey]]] = {}
    for m in _members(manifest, block_of, block_ids):
        for s in m.sheets:
            by_file.setdefault(s[0], []).extend(
                (m, s, t) for t in every if t[0] == s[0] and t != s and block_of[t] != m.block
            )
    out = _Outcome([], {}, set(), set())
    if by_file:
        inv = load_inventory(work)
        for file in sorted(by_file):
            _compare_file(work, inv, file, by_file[file], block_of, input_dir, out, notes)
    for key in sorted(out.thin - out.tested - set(out.skipped)):
        out.skipped[key] = FEW_ITEMS
    skipped = [
        {"code": LINEWORK, "file": f, "sheet": s, "reason": reason}
        for (f, s), reason in sorted(out.skipped.items())
    ]
    out.warnings.sort(key=lambda w: w["id"])
    return out.warnings, skipped
