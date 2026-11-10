"""grid_system: consolidate the per-view grid families of every file into project GRID SYSTEMS (gate 1).

`build_grid_systems(work_dir, answers=None, write=False)` reads `inventory.json`,
`structure-summary.json` (only to check it was built from this inventory) and every
`structure/<file>.{grids,sheets}.json` that `harness read-structure` wrote, and returns a document that
validates against `schemas/grid-system.schema.json`. A grid system is one building's or structure's grid:
one or two directions of axes, each with ordered labels, spacings and a Tekla-style coordinate string.
Nothing here is confirmed: the engineer selects and confirms the systems at gate 1 (RTI-0003).

Rules (deterministic; the thresholds are heuristics, see the schema description):

1. Usable family: two or more axes, every axis labelled, labels unique, every spacing > 0. Others are
   listed in `unassigned_families` with the reason. A VIEW (grids.py group) contributes its usable
   families: two orthogonal ones (90 +- FAMILY_ANGLE_TOL degrees) form a two-direction contribution,
   one forms a single-direction contribution; any other mix gives one single-direction contribution per
   family (and a warning).
2. Two families AGREE when they share >= 2 labels, the shared labels run in the same (or reversed)
   order, and every distance between consecutive shared labels is equal within half the rounding step
   or within DRAFTING_TOL of the distance (the same test as grids.py cross-checks). Otherwise, with >= 2
   shared labels, they CONFLICT. The distances are compared in MILLIMETRES (each family scaled by its own
   file's answered unit, the rounding step too) when EVERY contributing file of the comparison, i.e. both
   families' files, has an active units answer that agrees; one building drawn in m in one file and in mm
   in another then merges. Otherwise they are compared in drawing units, as drawn.
3. Clusters: views (sorted: complete proposals first, then file, group) join the first cluster whose
   EVERY member they match direction by direction with the same label set ('same'). Spacings are never
   averaged: a system's spacings are its representative's (the cluster's first member); the largest
   relative difference to the other members is recorded (`max_relative_spread`).
4. Systems: clusters ranked by directions, independent views, views, axes, then file/group. Each cluster
   becomes a new system unless every one of its families is a label subset of a direction of an earlier
   system, agreeing with every full member of it: then it joins that system as a PARTIAL contributor
   (it confirms only some spacings, so it never counts towards independence). When it fits several
   earlier systems that conflict with one another it stays its own system (`ambiguous_subset`).
5. Independence: two views are not independent when they are in the same file and on the same sheet,
   on copied sheets (sheets.json duplicate_of), share a top-level block, or grids.py recorded their
   `other_view` evidence as not independent (text overlap); views of two files are not independent
   when the files have the same sha256. `independent_views` = connected groups of full contributors
   (conservative). Fewer than 2 -> `single_source`, confidence low.
6. Units: spacings stay in drawing units with the declared unit (the representative's). The `mm` block is
   filled only when every contributing file has active units answers (codes in UNIT_CODES, values
   {"unit": ...}; an answer without `file` applies to every file) and each file's answers agree with
   themselves; it is the representative's file unit that converts. Files of one system may answer
   different units (flag `answered_units_differ`): they were merged in mm. Otherwise mm is null with the
   reason. The declared header unit is never used to convert. The grid-spacing evidence of the units test
   (`files[].grid_spacing_median`, also read by `harness status`) is the median spacing of the file's PLAN
   systems (tool wave 4): a single-source system (a key plan) never decides while the file has a system with
   two or more independent views; a file with only single-source systems takes the median of its systems'
   medians.
7. Tekla X/Y: only from active `grid_family_axis_assignment` answers ({"<family_id>": "X"|"Y"}, bound
   to the answer's `file`; family ids restart in every file) that cover every direction of the system
   without contradiction; otherwise null. Also from the system's own `grid_system_axis_unassigned` answer,
   bound by its key, which names the representative families (file, view and family ids: axis_where),
   never the positional system id, so adding an unrelated file does not re-ask it.
8. Confidence is never above 'medium' (gate 1 decides).
9. File sets (intake's project-level file_set_relation, two or more readable drawing files): once it is
   answered (bound by key to the live question), views of two different sets never cluster, never join one
   system and their systems are never compared (no conflict, no relation). While it is open, a conflict
   between two systems with no file in common does not block ("pending Q-x"); a conflict inside one file
   always does. Without a live question (one readable file, or an older intake) nothing changes.
10. Who answered (tool wave 3): only an answer with `answered_by_role` engineer confirms units, assigns
   Tekla X/Y, selects systems, closes a conflict or answers the file sets. An answer an agent gave
   (simulated), or one recorded before roles, is a proposal: units and X/Y that only such answers give are
   `proposed_simulated` (nothing converted or assigned, the X/Y question keeps blocking), a select answer
   that would close a conflict is recorded as `proposed_closed_by` (the conflict keeps blocking), a file
   set answer leaves the sets pending; each is warned. A non-engineer unit is still tested against the
   drawing (units_answer_contradicts_evidence), but only the engineer's answer confirms it.
11. A grid from the engineer (ADR-0013): every read drawing file that no selected two-direction detected
   system covers gets a blocking `grid_system_missing` question (`found` quotes what grids.py found:
   bubbles, labels, axes; it depends on the drawing only, so the question keeps its key; the systems
   detected in the file and why they are not usable are in the message). An active ENGINEER answer to it
   with dir1/dir2 labels and spacings builds a system `source: engineer_answer` after the detected ones
   (no view, family or contributor; the answer is its provenance), which then goes through select, X/Y
   and units like any other, and is compared with every other system like two detected ones (rule 2 on
   its given directions, cumulative positions, no rounding step; file sets as in rule 9). While that
   answer is active the question stays raised (its answer would go stale otherwise). A non-engineer,
   words-only or malformed answer builds nothing (warned), and the question is raised only while the file
   has no usable system (so such an answer goes stale once the file is covered again). The engineer's
   `no_grid=yes` (alone: the file holds no plan that needs a grid) builds nothing and keeps the question
   raised, answered, while it stands; `harness status` closes the question on it. The given
   spacings are compared with the linear dimensions grids.py placed between two of the given axes
   (labels case-blind, spans as sums; DRAFTING_TOL): a disagreement raises a blocking
   `grid_answer_contradicts_drawing` quoting both, and a grid nothing could be checked against is warned.
   The ADR's "file with plan sheets" is every read drawing file: no tool classifies plan sheets yet.

`render_grid_system_svg(system)` draws one system (axes, bubbles, labels, spacing dimensions,
coordinate strings, units, the PROPOSAL banner) as plain SVG text; spacing labels that would overlap their
neighbour (estimated width 0.6 x font size x characters) are staggered onto further rows. With `write=True`
the SVGs go to `structure/grid-systems/<system_id>.svg` (the folder is cleared first; read-structure clears
`structure/` when it reruns).

`run_grid_systems(work_dir, svg=True)` is `harness grid-system`: it reads `answers.json` through the
question ledger (active answers only), builds and validates the document, registers its questions as
producer `grid-system` (`grid_system_questions`: one per (code, blocking flag, file); the project-level
`grid_system_select` has file null and one ref per system; a `grid_system_conflict` is keyed by both sides'
file, view and family ids and their shared labels only, so it keeps its id when units are answered or the
selection changes, and one the select answer settles carries `closed_by`), then writes the registry and
answers, then `grid-systems.json`, `grid-system-questions.json` and the SVGs (cleared and rewritten, or only
cleared with `svg=False`, so no `svg` path points at an old drawing).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import statistics
from collections import Counter
from dataclasses import dataclass, field
from itertools import pairwise, permutations
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from tekla_harness.answers import MAX_SPACING, NO_GRID_KEY, is_no_grid, spacing_in_range
from tekla_harness.grids import (
    DRAFTING_TOL,
    FAMILY_ANGLE_TOL,
    coordinate_string,
    fmt_number,
    implausible_spacing,
    rounding_step,
)
from tekla_harness.questions import (
    AXIS_CODE,
    AXIS_DIRECTIONS,
    CONFLICT_CODE,
    CONTRADICTION_CODE,
    FILE_SET_CODE,
    FILE_SET_KEY,
    GRID_ANSWER_KEYS,
    GRID_ANSWER_SHEET_KEY,
    GRID_CONTRADICTS_CODE,
    GRID_MISSING_CODE,
    ROLES,
    SELECT_CODE,
    SYSTEM_AXIS_CODE,
    UNIT_CODES,
    Closure,
    QuestionsError,
    dump_json,
    load_ledger,
    merged_question,
    question_group,
    question_key,
    questions_document,
    write_text_atomic,
)
from tekla_harness.read_dxf import implausible_dimensions
from tekla_harness.schemas import validate
from tekla_harness.sheets import SHEET_UNKNOWN, listed, min_conf, rnum

SCHEMA_VERSION = "0.1"
STRUCTURE_DIR = "structure"
GRID_SYSTEMS_DIR = "structure/grid-systems"
MAX_CONFIDENCE = "medium"  # 'high' is reserved for the engineer's confirmation at gate 1
MAX_QUESTIONS_PER_CODE = 100
BANNER = "PROPOSAL — not confirmed (gate 1)"
UNIT_TO_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "ft": 304.8}
EXIT_OK, EXIT_INVALID, EXIT_USAGE, EXIT_ENV = 0, 1, 2, 3
ENGINEER_ROLE = ROLES[0]  # answers.json answered_by_role of the engineer's own answer
PROPOSED = "proposed_simulated"  # a value that rests on an answer the engineer did not give
UNITS_NOT_ENGINEER = "units answered by a non-engineer role"
AXIS_NOT_ENGINEER = (
    "Tekla X / Y rest on an answer the engineer did not give (simulated, or no role recorded): it assigns "
    "nothing until the engineer answers"
)
MAX_LABELS_QUOTED = 30  # distinct bubble labels a grid_system_missing question quotes
MAX_DIFFERENCES_QUOTED = 20  # dimensions a grid_answer_contradicts_drawing question quotes

_REF_RE = re.compile(r"^(V\d{3,})/(F\d{3,}) on sheet ")


class GridSystemError(Exception):
    """A run that cannot proceed; `exit_code` is the CLI exit code (AGENTS.md)."""

    def __init__(self, exit_code: int, message: str) -> None:
        super().__init__(message)
        self.exit_code = exit_code


# --- inputs ----------------------------------------------------------------------------------------


@dataclass
class _Fam:
    file: str
    sheet: str
    group_id: str
    family_id: str
    labels: list[str]
    pos: dict[str, float]
    spacings: list[float]  # rounded, drawing units (grids.py spacing values)
    step: float
    angle: float
    complete: bool
    confidence: str
    factor: float | None = None  # mm per drawing unit; set only from this file's agreeing units answer

    def ref(self) -> dict[str, str]:
        return {
            "file": self.file,
            "sheet": self.sheet,
            "group_id": self.group_id,
            "family_id": self.family_id,
        }

    def label_text(self) -> str:
        return " ".join(self.labels)


@dataclass
class _View:
    file: str
    file_sha: str
    sheet: str
    group_id: str
    fams: list[_Fam]
    blocks: frozenset[str]

    @property
    def axes(self) -> int:
        return sum(len(f.labels) for f in self.fams)

    @property
    def complete(self) -> bool:
        return all(f.complete for f in self.fams)


@dataclass
class _FileCtx:
    path: str
    sha: str
    declared: str
    dup_root: dict[str, str] = field(default_factory=dict)
    not_independent: set[frozenset[str]] = field(default_factory=set)
    opaque: set[str] = field(default_factory=set)


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GridSystemError(EXIT_ENV, f"cannot read {label} {path}: {exc}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise GridSystemError(EXIT_INVALID, f"{label} {path} is not valid JSON: {exc}") from exc


def _load_checked(path: Path, schema: str, label: str) -> Any:
    data = _read_json(path, label)
    problems = validate(schema, data)
    if problems:
        details = "; ".join(f"{p.path or '/'}: {p.message}" for p in problems[:5])
        raise GridSystemError(EXIT_INVALID, f"{label} {path} is invalid ({schema} schema): {details}")
    return data


def _family(raw: dict[str, Any], file: str, group: dict[str, Any]) -> tuple[_Fam | None, str | None]:
    """A usable family, or None and the reason it cannot be used (None, None: a single axis)."""
    if raw["proposal"] is None:
        return None, None
    labels = [(a["label"] or {}).get("value") for a in raw["axes"]]
    if any(lbl is None for lbl in labels):
        return None, "an axis has no label"
    names = [str(lbl) for lbl in labels]
    dupes = sorted(lbl for lbl, n in Counter(names).items() if n > 1)
    if dupes:
        return None, f"duplicate label(s) {' '.join(dupes)}"
    spacings = [float(s["value"]["value"]) for s in raw["spacings"]]
    if any(v <= 0 for v in spacings):
        return None, "two labels at one offset (zero spacing)"
    confs = [a["confidence"] for a in raw["axes"]] + [s["value"]["confidence"] for s in raw["spacings"]]
    return (
        _Fam(
            file=file,
            sheet=group["sheet"],
            group_id=group["group_id"],
            family_id=raw["family_id"],
            labels=names,
            pos={lbl: float(a["offset"]) for lbl, a in zip(names, raw["axes"], strict=True)},
            spacings=spacings,
            step=rounding_step([float(s["measured"]) for s in raw["spacings"]]),
            angle=float(raw["angle_deg"]),
            complete=bool(raw["proposal"]["complete"]),
            confidence=min_conf(MAX_CONFIDENCE, *confs),
        ),
        None,
    )


def _orthogonal(a: _Fam, b: _Fam) -> bool:
    d = abs((a.angle - b.angle) % 180.0)
    return abs(d - 90.0) <= FAMILY_ANGLE_TOL


@dataclass
class _Inputs:
    project_id: str
    inventory_sha: str
    files: list[dict[str, Any]]
    ctx: dict[str, _FileCtx]
    views: list[_View]
    unassigned: list[dict[str, Any]]
    totals: Counter[str]
    warnings: list[str]
    inventory_units: dict[str, dict[str, Any] | None] = field(default_factory=dict)
    spacing_medians: dict[str, dict[str, Any] | None] = field(default_factory=dict)
    readable: int = 0  # DXF / DWG files intake read (outcome not 'unreadable'): file_set_relation needs 2+
    facts: dict[str, dict[str, Any]] = field(default_factory=dict)  # per read file: _grid_facts


def _grid_facts(grids: dict[str, Any]) -> dict[str, Any]:
    """What a grids document found, for the file's grid_system_missing question (`found`, which depends on the
    drawing only, so the question keeps its key and its answer) and for checking an engineer-given grid
    against the linear dimensions between its axes (ADR-0013 §5): every family's dimension_evidence, once."""
    s = grids["summary"]
    on_axes = {
        a["label"]["value"] for g in grids["groups"] for f in g["families"] for a in f["axes"] if a["label"]
    }
    unpaired = {b["label"] for b in grids["unpaired_bubbles"]["listed"] if b["label"]}
    dims: dict[tuple[Any, ...], dict[str, Any]] = {}
    for g in grids["groups"]:
        for f in g["families"]:
            for sp in f["spacings"]:
                for e in sp["dimension_evidence"]:
                    row = {**e, "sheet": g["sheet"], "where": f"{g['group_id']}/{f['family_id']}"}
                    key = (row["where"], e["handle"], e["from_label"], e["to_label"], e["displayed"])
                    dims.setdefault(key, row)
    found = (
        f"{s['bubbles_labelled']} labelled bubble(s), {s['bubbles_paired']} paired with a line, {s['axes']} "
        f"axis(es) in {s['families']} famil(ies); axis labels: {_labels_text(on_axes)}; unpaired bubble "
        f"labels: {_labels_text(unpaired)} ({grids['unpaired_bubbles']['count']} unpaired)"
    )
    return {"found": found, "dims": list(dims.values())}


def _labels_text(labels: set[str]) -> str:
    ordered = sorted(labels, key=lambda x: (len(x), x))
    more = f" (+{len(ordered) - MAX_LABELS_QUOTED} more)" if len(ordered) > MAX_LABELS_QUOTED else ""
    return (" ".join(ordered[:MAX_LABELS_QUOTED]) or "none") + more


def spacing_median(grids: dict[str, Any]) -> dict[str, Any] | None:
    """{"value", "count"}: the median positive grid spacing (drawing units) over every family of a grids
    document, as `harness read-structure` measured it; None when it has no spacing."""
    values = [
        float(s["value"]["value"])
        for g in grids["groups"]
        for fam in g["families"]
        for s in fam["spacings"]
        if float(s["value"]["value"]) > 0
    ]
    return {"value": float(statistics.median(values)), "count": len(values)} if values else None


def units_evidence(
    dimension_median: dict[str, Any] | None, spacing: dict[str, Any] | None, unit: str
) -> str | None:
    """Why the answered `unit` contradicts the drawing, or None: the median modelspace linear dimension
    (units_suspect test) or the median grid spacing (grid plausibility range) is implausible in `unit`."""
    found = [
        e for e in (implausible_dimensions(dimension_median, unit), implausible_spacing(spacing, unit)) if e
    ]
    return "; ".join(found) or None


def _load_inputs(work: Path) -> _Inputs:
    if not work.is_dir():
        raise GridSystemError(EXIT_USAGE, f"work folder not found (not a folder): {work}")
    inv_path = work / "inventory.json"
    if not inv_path.is_file():
        raise GridSystemError(EXIT_USAGE, f"{work} has no inventory.json: run `harness intake` first")
    summary_path = work / "structure-summary.json"
    if not summary_path.is_file():
        raise GridSystemError(
            EXIT_USAGE, f"{work} has no structure-summary.json: run `harness read-structure` first"
        )
    inventory_bytes = inv_path.read_bytes()
    inventory = _load_checked(inv_path, "intake", "inventory.json")
    if inventory["kind"] != "inventory":
        raise GridSystemError(EXIT_INVALID, "inventory.json has the wrong 'kind'")
    inventory_sha = hashlib.sha256(inventory_bytes).hexdigest()
    summary = _read_json(summary_path, "structure-summary.json")
    if not isinstance(summary, dict) or summary.get("inventory_sha256") != inventory_sha:
        raise GridSystemError(
            EXIT_INVALID,
            "structure-summary.json was not built from this inventory.json: rerun `harness read-structure`",
        )
    warnings: list[str] = []
    files: list[dict[str, Any]] = []
    ctxs: dict[str, _FileCtx] = {}
    views: list[_View] = []
    unassigned: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()
    inventory_units: dict[str, dict[str, Any] | None] = {}
    spacing_medians: dict[str, dict[str, Any] | None] = {}
    facts: dict[str, dict[str, Any]] = {}
    readable = 0
    root = work.resolve()
    for row in sorted(inventory["files"], key=lambda r: r["path"]):
        if row["format"] not in ("dwg", "dxf"):
            continue
        rel = row["path"]
        inventory_units[rel] = row["units"]
        readable += row["outcome"] != "unreadable"
        base = (root / STRUCTURE_DIR / rel).resolve()
        if root not in base.parents:
            raise GridSystemError(EXIT_INVALID, f"{rel}: path leaves the work folder")
        grids_path = Path(f"{base}.grids.json")
        sheets_path = Path(f"{base}.sheets.json")
        entry: dict[str, Any] = {
            "path": rel,
            "sha256": row["sha256"],
            "grids": None,
            "status": "no_grids",
            "declared_unit": None,
            "views": 0,
            "families_usable": 0,
            "grid_spacing_median": None,
        }
        files.append(entry)
        if not grids_path.is_file():
            continue
        if not sheets_path.is_file():
            raise GridSystemError(
                EXIT_INVALID, f"{rel}: grids document without a sheets document ({sheets_path})"
            )
        grids = _load_checked(grids_path, "grids", "grids document")
        sheets = _load_checked(sheets_path, "sheets", "sheets document")
        if grids["file"]["sha256"] != sheets["file"]["sha256"]:
            raise GridSystemError(EXIT_INVALID, f"{rel}: grids and sheets documents come from different DXFs")
        declared = grids["file"]["declared_units"]["name"]
        entry.update(
            grids=f"{STRUCTURE_DIR}/{rel}.grids.json",
            status="read",
            declared_unit=declared,
            views=len(grids["groups"]),
            grid_spacing_median=spacing_median(grids),
        )
        spacing_medians[rel] = entry["grid_spacing_median"]
        facts[rel] = _grid_facts(grids)
        ctx = _FileCtx(rel, row["sha256"], declared)
        ctx.dup_root = {s["sheet_id"]: s["duplicate_of"] for s in sheets["sheets"] if s["duplicate_of"]}
        ctxs[rel] = ctx
        for group in grids["groups"]:
            usable: list[_Fam] = []
            blocks: set[str] = set()
            for raw in group["families"]:
                blocks.update(a["line"]["block_path"][0] for a in raw["axes"] if a["line"]["block_path"])
                _evidence_links(raw, group["group_id"], ctx, warnings)
                fam, reason = _family(raw, rel, group)
                if fam is not None:
                    usable.append(fam)
                elif reason is not None:
                    totals["families_unassigned"] += 1
                    unassigned.append(
                        {
                            "file": rel,
                            "sheet": group["sheet"],
                            "group_id": group["group_id"],
                            "family_id": raw["family_id"],
                            "labels": " ".join((a["label"] or {}).get("value", "?") for a in raw["axes"]),
                            "reason": reason,
                        }
                    )
                else:
                    totals["single_axis_families"] += 1
            entry["families_usable"] += len(usable)
            totals["views"] += 1
            if not usable:
                continue
            frozen = frozenset(blocks)
            if len(usable) == 1 or (len(usable) == 2 and _orthogonal(*usable)):
                views.append(_View(rel, row["sha256"], group["sheet"], group["group_id"], usable, frozen))
            else:
                warnings.append(
                    f"{rel} {group['group_id']}: {len(usable)} usable families that are not one orthogonal "
                    "pair; each is used as a single direction"
                )
                views.extend(
                    _View(rel, row["sha256"], group["sheet"], group["group_id"], [f], frozen) for f in usable
                )
    return _Inputs(
        inventory["project_id"],
        inventory_sha,
        files,
        ctxs,
        views,
        unassigned,
        totals,
        warnings,
        inventory_units,
        spacing_medians,
        readable,
        facts,
    )


def _evidence_links(raw: dict[str, Any], gid: str, ctx: _FileCtx, warnings: list[str]) -> None:
    """Record grids.py's 'not independent' other_view evidence (e.g. sheets with near-identical texts)."""
    for s in raw["spacings"]:
        for e in s["evidence"]:
            if e["kind"] != "other_view":
                continue
            m = _REF_RE.match(e["ref"])
            if m is None:
                if gid not in ctx.opaque:
                    warnings.append(
                        f"{ctx.path} {gid}/{raw['family_id']}: other_view evidence ref cannot be parsed "
                        f"({e['ref'][:80]!r}); the view is counted as not independent of the others in its "
                        "file"
                    )
                ctx.opaque.add(gid)
            elif not e["independent"]:
                ctx.not_independent.add(frozenset((gid, m.group(1))))


# --- comparing families ----------------------------------------------------------------------------


@dataclass
class _Cmp:
    relation: str  # same | subset | superset | overlap | disjoint | conflict
    diffs: list[str]
    spread: float
    tolerated: bool  # a distance agreed only within DRAFTING_TOL (beyond half the rounding step)


def _compare(a: _Fam, b: _Fam) -> _Cmp:
    common = [lbl for lbl in a.labels if lbl in b.pos]
    if len(common) < 2:
        return _Cmp("disjoint", [], 0.0, False)
    seq = [b.pos[lbl] for lbl in common]
    if not (all(q > p for p, q in pairwise(seq)) or all(q < p for p, q in pairwise(seq))):
        other = " ".join(sorted(common, key=b.pos.__getitem__))
        return _Cmp("conflict", [f"label order {' '.join(common)} vs {other}"], 0.0, False)
    in_mm = a.factor is not None and b.factor is not None  # both files have an agreeing units answer
    fa, fb = (a.factor, b.factor) if in_mm and a.factor and b.factor else (1.0, 1.0)
    step = max(a.step * fa, b.step * fb)
    unit = " mm" if in_mm else ""
    diffs: list[str] = []
    spread, tolerated = 0.0, False
    for p, q in pairwise(common):
        da, db = abs(a.pos[q] - a.pos[p]) * fa, abs(b.pos[q] - b.pos[p]) * fb
        diff, big = abs(da - db), max(da, db)
        if big > 0:
            spread = max(spread, diff / big)
        if diff <= step / 2:
            continue
        if diff <= DRAFTING_TOL * big:
            tolerated = True
            continue
        diffs.append(f"{p}-{q}: {fmt_number(rnum(da))} vs {fmt_number(rnum(db))}{unit}")
    if diffs:
        return _Cmp("conflict", diffs, spread, tolerated)
    sa, sb = set(a.labels), set(b.labels)
    relation = "same" if sa == sb else "subset" if sa < sb else "superset" if sa > sb else "overlap"
    return _Cmp(relation, [], spread, tolerated)


def _assign(src: list[_Fam], dst: list[_Fam], allowed: frozenset[str]) -> list[int] | None:
    """Direction index in `dst` of each family of `src` (distinct), all relations in `allowed`."""
    if len(src) > len(dst):
        return None
    for perm in permutations(range(len(dst)), len(src)):
        if all(_compare(f, dst[j]).relation in allowed for f, j in zip(src, perm, strict=True)):
            return list(perm)
    return None


_SAME = frozenset({"same"})
_FITS = frozenset({"same", "subset"})


# --- clusters and systems --------------------------------------------------------------------------


@dataclass
class _Member:
    view: _View
    dirs: list[int]  # system direction of each of view.fams
    role: str  # full | partial


@dataclass
class _System:
    members: list[_Member]
    flags: set[str] = field(default_factory=set)
    subset_of: list[int] = field(default_factory=list)

    @property
    def rep(self) -> _View:
        return self.members[0].view

    def full(self) -> list[_Member]:
        return [m for m in self.members if m.role == "full"]

    def family_of(self, m: _Member, d: int) -> _Fam | None:
        for f, k in zip(m.view.fams, m.dirs, strict=True):
            if k == d:
                return f
        return None


def _linked(u: _View, v: _View, ctx: dict[str, _FileCtx]) -> bool:
    """True when the two views do not check each other independently."""
    if u.file != v.file:
        return u.file_sha == v.file_sha
    c = ctx[u.file]
    if u.sheet == v.sheet or c.dup_root.get(u.sheet, u.sheet) == c.dup_root.get(v.sheet, v.sheet):
        return True
    if u.blocks & v.blocks:
        return True
    if u.group_id in c.opaque or v.group_id in c.opaque:
        return True
    return frozenset((u.group_id, v.group_id)) in c.not_independent


def _components(views: list[_View], ctx: dict[str, _FileCtx]) -> list[int]:
    """1-based independence group of each view (union of 'not independent' links)."""
    parent = list(range(len(views)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(views)):
        for j in range(i + 1, len(views)):
            if _linked(views[i], views[j], ctx):
                parent[find(j)] = find(i)
    ids: dict[int, int] = {}
    return [ids.setdefault(find(i), len(ids) + 1) for i in range(len(views))]


def _clusters(views: list[_View], set_of: dict[str, int]) -> list[list[_Member]]:
    """`set_of`: file -> its file set (the file_set_relation answer); views of two sets never cluster."""
    ordered = sorted(views, key=lambda v: (not v.complete, v.file, v.group_id, v.fams[0].family_id))
    clusters: list[list[_Member]] = []
    for v in ordered:
        for members in clusters:
            rep = members[0].view
            if len(v.fams) != len(rep.fams) or set_of.get(v.file, 0) != set_of.get(rep.file, 0):
                continue
            dirs = _assign(v.fams, rep.fams, _SAME)
            if dirs is None:
                continue
            if all(_member_fits(v, dirs, m, _SAME) for m in members[1:]):
                members.append(_Member(v, dirs, "full"))
                break
        else:
            clusters.append([_Member(v, list(range(len(v.fams))), "full")])
    return clusters


def _member_fits(v: _View, dirs: list[int], m: _Member, allowed: frozenset[str]) -> bool:
    """Every family of `v` (mapped to directions `dirs`) relates to member m's family of that direction."""
    for f, d in zip(v.fams, dirs, strict=True):
        other = next((g for g, k in zip(m.view.fams, m.dirs, strict=True) if k == d), None)
        if other is None or _compare(f, other).relation not in allowed:
            return False
    return True


def _fits_system(cluster: list[_Member], s: _System) -> list[int] | None:
    """Directions of `s` for the cluster representative's families when every cluster member is a label
    subset of (or equal to) every full member of `s`, direction by direction; None otherwise."""
    rep = cluster[0].view
    dirs = _assign(rep.fams, s.rep.fams, _FITS)
    if dirs is None:
        return None
    for cm in cluster:
        mapped = [dirs[k] for k in cm.dirs]
        if not all(_member_fits(cm.view, mapped, sm, _FITS) for sm in s.full()):
            return None
    return dirs


def _system_conflict(a: _System, b: _System) -> tuple[list[tuple[_Fam, _Fam]], list[str]] | None:
    """The first pair of full members (representatives first) that disagree on a shared label pair: every
    conflicting family pair of those two members (a's family first) and every difference; None when the
    systems never disagree."""
    return _members_conflict([m.view.fams for m in a.full()], [m.view.fams for m in b.full()])


def _members_conflict(
    a: list[list[_Fam]], b: list[list[_Fam]]
) -> tuple[list[tuple[_Fam, _Fam]], list[str]] | None:
    """_system_conflict over the families of each full member (representative first) of two systems; an
    answer-built system has one member, its given directions (_given_fams)."""
    for fams_a in a:
        for fams_b in b:
            found: list[str] = []
            pairs: list[tuple[_Fam, _Fam]] = []
            for fa in fams_a:
                for fb in fams_b:
                    c = _compare(fa, fb)
                    if c.relation == "conflict":
                        pairs.append((fa, fb))
                        found.extend(c.diffs)
            if pairs:
                return pairs, found
    return None


def _side(f: _Fam) -> tuple[str, str, str]:
    return (f.file, f.group_id, f.family_id)


def _conflict_identity(pairs: list[tuple[_Fam, _Fam]]) -> tuple[str, str, _Fam]:
    """where / found of a grid_system_conflict question and the family whose file and sheet it is filed
    under. Built only from what does not change with an answer: the file, view and family ids of both
    sides and the labels they share, sides in sorted order (system ids are positional, and the difference
    text switches to millimetres once units are answered: both go into the message only)."""
    ordered = sorted(
        ((min(p, key=_side), max(p, key=_side)) for p in pairs), key=lambda p: (_side(p[0]), _side(p[1]))
    )
    first, second = ordered[0]
    where = " vs ".join(f"{f.file} {f.group_id}/{f.family_id}" for f in (first, second))
    found = "; ".join(
        f"{x.group_id}/{x.family_id} x {y.group_id}/{y.family_id}: shared labels "
        + " ".join(lbl for lbl in x.labels if lbl in y.pos)
        for x, y in ordered
    )
    return where, found, first


def _related(a: list[_Fam], b: list[_Fam]) -> bool:
    """The representative families of two systems share at least two labels in some direction."""
    return any(_compare(fa, fb).relation != "disjoint" for fa in a for fb in b)


def _same_set(a: str, b: str, set_of: dict[str, int]) -> bool:
    """Two systems are compared only when their representative files belong to one file set (a system never
    spans two)."""
    return set_of.get(a, 0) == set_of.get(b, 0)


def _closure(a: str, b: str, selected: set[str], separate: set[str]) -> str | None:
    """What a selection closes the conflict between systems a and b by: one of them left out, or both
    declared separate buildings; None when it stays open."""
    if a not in selected or b not in selected:
        return "not_selected"
    return "separate" if {a, b} <= separate else None


def _systems(
    clusters: list[list[_Member]], ctx: dict[str, _FileCtx], set_of: dict[str, int]
) -> list[_System]:
    def rank(members: list[_Member]) -> tuple[Any, ...]:
        rep = members[0].view
        indep = len(set(_components([m.view for m in members], ctx)))
        return (-len(rep.fams), -indep, -len(members), -rep.axes, rep.file, rep.group_id)

    systems: list[_System] = []
    for cluster in sorted(clusters, key=rank):
        fits = [
            (i, d)
            for i, s in enumerate(systems)
            if set_of.get(s.rep.file, 0) == set_of.get(cluster[0].view.file, 0)
            and (d := _fits_system(cluster, s)) is not None
        ]
        clash = any(
            _system_conflict(systems[i], systems[j]) is not None
            for x, (i, _) in enumerate(fits)
            for j, _ in fits[x + 1 :]
        )
        if fits and not clash:
            target, dirs = fits[0]
            for cm in cluster:
                systems[target].members.append(_Member(cm.view, [dirs[k] for k in cm.dirs], "partial"))
            continue
        system = _System(list(cluster))
        if fits:
            system.flags.add("ambiguous_subset")
            system.subset_of = [i for i, _ in fits]
        systems.append(system)
    return systems


# --- answers ---------------------------------------------------------------------------------------


def _active(answers: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [a for a in answers or [] if isinstance(a, dict) and a.get("status") == "active"]


def _by_engineer(answer: dict[str, Any]) -> bool:
    """The engineer gave this answer: `answered_by_role` engineer. A simulated answer, or one recorded before
    roles existed, only proposes (tool wave 3): it never confirms, assigns, selects or closes anything."""
    return answer.get("answered_by_role") == ENGINEER_ROLE


def _not_engineer(answer: dict[str, Any], what: str) -> str:
    return (
        f"the {answer.get('code')} answer {answer.get('key')!r} was given by a non-engineer role "
        f"({answer.get('answered_by_role') or 'none recorded'}): {what}"
    )


def units_by_file(
    answers: list[dict[str, Any]], files: list[str], warnings: list[str]
) -> dict[str, tuple[str, str | None]]:
    """Per file: (status, unit). status: answered | not_answered | disagree | invalid. `answers` must already
    be the ACTIVE ones (build_grid_systems filters; so does harness status)."""
    found: dict[str, set[str]] = {f: set() for f in files}
    invalid: set[str] = set()
    for a in answers:
        if a.get("code") not in UNIT_CODES:
            continue
        values = a.get("values")
        unit = values.get("unit") if isinstance(values, dict) else None
        target = a.get("file")
        applies = files if target is None else [target] if target in found else []
        if target is not None and not applies:
            warnings.append(
                f"units answer {a.get('key')!r} names file {target!r}, which has no grids document"
            )
        if unit not in UNIT_TO_MM:
            warnings.append(f"units answer {a.get('key')!r} has no valid unit (values {values!r}): not used")
            invalid.update(applies)
            continue
        for f in applies:
            found[f].add(str(unit))
    out: dict[str, tuple[str, str | None]] = {}
    for f in files:
        units = found[f]
        if f in invalid:
            out[f] = ("invalid", None)
        elif len(units) > 1:
            out[f] = ("disagree", None)
        elif units:
            out[f] = ("answered", next(iter(units)))
        else:
            out[f] = ("not_answered", None)
    return out


# the answers this module reads besides the units answers
CONSUMED_CODES = frozenset(
    {AXIS_CODE, SYSTEM_AXIS_CODE, SELECT_CODE, CONTRADICTION_CODE, FILE_SET_CODE, GRID_MISSING_CODE}
)


def consumed_answers_digest(answers: list[dict[str, Any]] | None) -> str:
    """sha256 over the active answers this module reads (units, family and system axis assignment, the
    grid_system_select answer, units contradiction confirmations, the file_set_relation answer, the
    grid_system_missing answers): code, file, key, values and who answered (`answered_by_role`, None when
    none was recorded). `harness status` compares it with the current answers.json to see whether
    grid-systems.json is stale. Who answered is part of it (ADR-0013 decision 6): only the engineer's
    answers decide here, so an engineer's answer that replaces a simulated one with the same values makes
    the document stale until grid-system reruns."""
    rows = sorted(
        (
            str(a.get("code")),
            str(a.get("file")),
            str(a.get("key")),
            json.dumps(a.get("values"), sort_keys=True),
            str(a.get("answered_by_role")),
        )
        for a in _active(answers)
        if a.get("code") in UNIT_CODES or a.get("code") in CONSUMED_CODES
    )
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode("utf-8")).hexdigest()


def _axis_answers(answers: list[dict[str, Any]], warnings: list[str]) -> dict[tuple[str, str], set[str]]:
    out: dict[tuple[str, str], set[str]] = {}
    for a in answers:
        if a.get("code") != AXIS_CODE:
            continue
        if a.get("file") is None:
            warnings.append(
                f"axis answer {a.get('key')!r} has no file: family ids restart in every file, not used"
            )
            continue
        values = a.get("values")
        if not isinstance(values, dict):
            warnings.append(f"axis answer {a.get('key')!r} has no family map in values: not used")
            continue
        for fid, axis in sorted(values.items()):
            if axis not in ("X", "Y"):
                warnings.append(f"axis answer {a.get('key')!r}: {fid} -> {axis!r} is not X or Y: not used")
                continue
            out.setdefault((str(a["file"]), str(fid)), set()).add(axis)
    return out


# --- output ----------------------------------------------------------------------------------------


class _Ask:
    def __init__(self) -> None:
        self.questions: list[dict[str, Any]] = []
        self.counts: Counter[str] = Counter()

    def __call__(
        self,
        code: str,
        message: str,
        where: str,
        found: str,
        file: str | None = None,
        sheet: str | None = None,
        *,
        blocking: bool = True,
    ) -> bool:
        """Add a question; False when the per-code cap dropped it (counted, not listed)."""
        self.counts[code] += 1
        if self.counts[code] > MAX_QUESTIONS_PER_CODE:
            return False
        q: dict[str, Any] = {
            "code": code,
            "blocking": blocking,
            "message": message,
            "where": where,
            "found": found,
        }
        if file is not None:
            q["file"] = file
        if sheet is not None:
            q["sheet"] = sheet
        self.questions.append(q)
        return True


def _raw_ref(q: dict[str, Any]) -> dict[str, Any]:
    """The ref a question of the document becomes in grid-system-questions.json (grid_system_questions)."""
    ref = {"file": q.get("file"), "where": q["where"], "found": q["found"]}
    if "sheet" in q:
        ref["sheet"] = q["sheet"]
    return ref


def _own_key(
    code: str, file: str | None, where: str, found: str, sheet: str | None, sha: dict[str, str]
) -> str:
    """Registry key of a question that is registered on its own (one ref), exactly as Ledger.sync computes
    it: answers are bound to THIS run's question by key, never by code alone."""
    q: dict[str, Any] = {"file": file, "where": where, "found": found}
    if sheet is not None:
        q["sheet"] = sheet
    return question_key(code, file, sha.get(file) if file is not None else None, [_raw_ref(q)])


def _select_refs(docs: list[dict[str, Any]], shas: dict[str, str]) -> list[dict[str, Any]]:
    """The refs of the project-level grid_system_select question: one per system. The question key hashes
    only where / found / sheet, and sheet ids (`model#01`) repeat across files, so `found` also names the
    representative's file and its inventory sha256: two systems from two files cannot swap S-ids under one
    key, and a systems= answer cannot select another building."""
    refs = []
    for d in docs:
        # a system built from an engineer answer has no representative family: its provenance names the file
        rep = d["directions"][0]["representative"] or d["directions"][0]["provenance"]
        file = rep["file"]
        found = f"{_system_found(d)} [file {file}, sha256 {shas.get(file, '?')[:16]}]"
        refs.append({"file": file, "where": d["system_id"], "found": found, "sheet": rep["sheet"]})
    return refs


def _axis_found(s: _System) -> str:
    """The directions of a system as its grid_system_axis_unassigned question names them (dir1, dir2). It does
    not depend on any answer, so the question keeps its key (and its answer) once it is answered."""
    return "; ".join(
        f"{AXIS_DIRECTIONS[d]}: {f.group_id}/{f.family_id} labels {f.label_text()}, "
        f"angle {fmt_number(rnum(f.angle))} deg"
        for d, f in enumerate(s.rep.fams)
    )


def axis_where(refs: list[dict[str, str]]) -> str:
    """`where` of a system's grid_system_axis_unassigned question, from its representative families (one
    ref per direction: file, group_id, family_id). System ids are positional (adding a file renumbers
    them), so the id is in the message only and the question keeps its key, and its answer, when an
    unrelated file is added (the conflict key does the same: _conflict_identity)."""
    return f"{refs[0]['file']} " + " x ".join(f"{r['group_id']}/{r['family_id']}" for r in refs)


def _answer_axis_where(file: str, answer_key: str) -> str:
    """`where` of the X/Y question of a system built from an engineer answer: the file and the key of the
    grid_system_missing question it answered (the answer is bound to that key; the system id is
    positional)."""
    return f"{file} {GRID_MISSING_CODE} {answer_key}"


def _doc_axis_where(d: dict[str, Any]) -> str:
    if d.get("source") == "engineer_answer":
        return _answer_axis_where(d["directions"][0]["provenance"]["file"], d["source_answer"]["key"])
    return axis_where([x["representative"] for x in d["directions"]])


def _system_axis_values(answer: dict[str, Any], n_dirs: int, sid: str, warnings: list[str]) -> dict[int, str]:
    """Direction index -> Tekla axis from a grid_system_axis_unassigned answer: every direction of the system,
    X or Y, distinct. Anything else (a words-only answer included) assigns nothing and is warned."""
    values = answer.get("values")
    names = AXIS_DIRECTIONS[:n_dirs]
    ok = (
        isinstance(values, dict)
        and set(values) == set(names)
        and all(v in ("X", "Y") for v in values.values())
        and len(set(values.values())) == len(values)
    )
    if not ok or not isinstance(values, dict):
        warnings.append(
            f"axis answer {answer.get('key')!r} for {sid} does not assign {', '.join(names)} to distinct "
            f"X / Y (values {values!r}): not used"
        )
        return {}
    return {AXIS_DIRECTIONS.index(k): str(v) for k, v in values.items()}


def _independent(s: _System, ctx: dict[str, _FileCtx]) -> int:
    return len(set(_components([m.view for m in s.full()], ctx)))


def _drop_strays(
    systems: list[_System], ctx: dict[str, _FileCtx]
) -> tuple[list[_System], list[tuple[_System, _System]]]:
    """(systems without the strays, [(stray, the system of its file that makes it one)]).

    The file's MAIN system is a two-direction system with three or more axes in each direction, from any
    number of views (EVAL-4 180: every plan is seen once, as a half of one grid). A STRAY is a system of ONE
    direction seen in ONE independent view (rebar or pile marks drawn like bubbles: EVAL-3 286 `b bt`, 290
    `8 1` / `6 1` / `3 16`; 3D views and details), in a file that has a main system. A Tekla grid needs two
    directions, and the file's grid is already a system; the stray is reported in `unassigned_families`,
    never silently dropped. A file without a main system keeps its small systems: they may be all it has."""
    strong = [s for s in systems if len(s.rep.fams) == 2 and min(len(f.labels) for f in s.rep.fams) >= 3]
    kept: list[_System] = []
    dropped: list[tuple[_System, _System]] = []
    for s in systems:
        stray = len(s.rep.fams) == 1 and _independent(s, ctx) < 2
        main = next(
            (m for m in strong if m is not s and any(x.view.file == s.rep.file for x in m.members)), None
        )
        if stray and main is not None:
            dropped.append((s, main))
        else:
            kept.append(s)
    return kept, dropped


def _plan_spacing_medians(systems: list[_System], ctx: dict[str, _FileCtx]) -> dict[str, dict[str, Any]]:
    """file -> {"value", "count"}: the median positive spacing (drawing units) of the file's PLAN systems.

    A system contributes its representative family in the file, once. A single-source system (fewer than two
    independent full views: a key plan, a stray detail) never decides while the file has a system with two
    or more independent views. A
    file whose systems are all single-source takes the median of its systems' medians (each system counts
    once). Files without a system are absent."""
    rows: dict[str, list[tuple[bool, list[float]]]] = {}
    for s in systems:
        single = len(set(_components([m.view for m in s.full()], ctx))) < 2
        seen: set[str] = set()
        for m in s.members:
            if m.view.file in seen:
                continue
            seen.add(m.view.file)
            values = [v for fam in m.view.fams for v in fam.spacings if v > 0]
            if values:
                rows.setdefault(m.view.file, []).append((single, values))
    out: dict[str, dict[str, Any]] = {}
    for file, items in rows.items():
        decisive = [vals for single, vals in items if not single]
        if decisive:
            pooled = [v for vals in decisive for v in vals]
            out[file] = {"value": float(statistics.median(pooled)), "count": len(pooled)}
        else:  # only single-source systems: each counts once, so a big key plan does not outvote the plans
            medians = [statistics.median(vals) for _, vals in items]
            out[file] = {"value": float(statistics.median(medians)), "count": sum(len(v) for _, v in items)}
    return out


def _contradictions(
    active: list[dict[str, Any]],
    statuses: dict[str, tuple[str, str | None]],
    inventory_units: dict[str, dict[str, Any] | None],
    sha: dict[str, str],
    spacing_medians: dict[str, dict[str, Any] | None],
    confirmers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Files whose answered unit fails the units_suspect magnitude test (read_dxf.implausible_dimensions) on
    the probe's median dimension, or the grid plausibility range (grids.implausible_spacing) on the median
    grid spacing of the file's families: one units_answer_contradicts_evidence each, quoting the answer(s)
    and the evidence. `confirmed`: this very question was answered with the same unit (a deliberate
    confirmation) by one of `confirmers` (the engineer's answers)."""
    out = []
    for path in sorted(statuses):
        status, unit = statuses[path]
        row = inventory_units.get(path) or {}
        if status != "answered" or unit is None:
            continue
        evidence = units_evidence(row.get("dimension_median"), spacing_medians.get(path), unit)
        if evidence is None:
            continue
        quotes = [
            f'{a.get("question_id")} {a.get("code")} unit={unit}: "{a.get("answer_text")}"'
            for a in active
            if a.get("code") in UNIT_CODES and a.get("file") in (path, None)
        ]
        where = "units answer vs drawing dimensions and grid spacings"
        found = f"answer {'; '.join(quotes)} | drawing: {evidence}"
        key = _own_key(CONTRADICTION_CODE, path, where, found, None, sha)
        confirmed = any(
            a.get("key") == key
            and a.get("code") == CONTRADICTION_CODE
            and isinstance(a.get("values"), dict)
            and a["values"].get("unit") == unit
            for a in confirmers
        )
        out.append({"file": path, "unit": unit, "where": where, "found": found, "confirmed": confirmed})
    return out


def _where(sid: str, f: _Fam) -> str:
    return f"{sid} ({f.file}, sheet {f.sheet}, {f.group_id}/{f.family_id})"


def _mm(spacings: list[float], factor: float) -> dict[str, Any]:
    values = [rnum(v * factor) for v in spacings]
    return {"spacings": values, "coordinates": coordinate_string(values)}


def _units_block(
    files: list[str],
    rep_file: str,
    declared: str,
    units: dict[str, tuple[str, str | None]],
    proposals: dict[str, str],
    flags: set[str],
) -> tuple[dict[str, Any], float | None]:
    """A system's `units` and the factor (mm per drawing unit) that converts its values, or None. Every
    contributing file needs its own agreeing engineer answer; files of one system may answer different units
    (they were merged in millimetres) and the representative's file converts its drawing values. Adds the
    units flags to `flags`."""
    statuses = [units[f] for f in files]
    reason: str | None = None
    if any(st == "disagree" for st, _ in statuses):
        reason = "units answers disagree"
    elif any(st == "contradicted" for st, _ in statuses):
        reason = "units answer contradicted by the drawing"
    elif any(st == "invalid" for st, _ in statuses):
        reason = "units answer invalid"
    elif any(units[f][0] == "not_answered" and f not in proposals for f in files):
        reason = "units not confirmed"
    elif any(units[f][0] == "not_answered" for f in files):
        reason = UNITS_NOT_ENGINEER  # every file has a unit, but some only from a non-engineer answer
    unit_answer = units[rep_file][1] if reason is None else None
    factor = UNIT_TO_MM[unit_answer] if unit_answer is not None else None
    if factor is None:
        flags.add("units_not_confirmed")
    elif len({u for _, u in statuses}) > 1:
        flags.add("answered_units_differ")
    if reason == UNITS_NOT_ENGINEER:
        unit_answer = units[rep_file][1] or proposals.get(rep_file)  # named, never converted
    status = (
        "confirmed" if factor is not None else PROPOSED if reason == UNITS_NOT_ENGINEER else "not_confirmed"
    )
    return {"declared": declared, "answered": unit_answer, "status": status, "reason": reason}, factor


def _tekla_grid(
    directions: list[dict[str, Any]], factor: float | None, axis_status: str
) -> dict[str, Any] | None:
    if factor is None or axis_status != "answered":
        return None
    tekla_grid: dict[str, Any] = {"unit": "mm"}
    for axis in ("x", "y"):
        dj = next((x for x in directions if x["tekla_axis"] == axis.upper()), None)
        tekla_grid[f"coordinate_{axis}"] = dj["mm"]["coordinates"] if dj else None
        tekla_grid[f"label_{axis}"] = " ".join(dj["labels"]) if dj else None
    return tekla_grid


def _axis_state(
    s: _System, axes: dict[tuple[str, str], set[str]], system_axes: dict[int, str] | None
) -> tuple[str, str | None, list[set[str]]]:
    """(status, reason, Tekla axes per direction): every contributing family of a direction must agree."""
    rep = s.rep
    per_dir: list[set[str]] = []
    for d in range(len(rep.fams)):
        got: set[str] = set()
        for m in s.members:
            f = s.family_of(m, d)
            if f is not None:
                got |= axes.get((f.file, f.family_id), set())
        if system_axes and d in system_axes:
            got.add(system_axes[d])
        per_dir.append(got)
    if any(len(g) > 1 for g in per_dir) or (
        len(per_dir) == 2 and all(len(g) == 1 for g in per_dir) and per_dir[0] == per_dir[1]
    ):
        return "contradictory", "axis answers contradict each other for this system", per_dir
    if any(not g for g in per_dir):
        return "not_answered", "no axis answer covers every direction", per_dir
    return "answered", None, per_dir


def _system_json(
    sid: str,
    s: _System,
    ctx: dict[str, _FileCtx],
    units: dict[str, tuple[str, str | None]],
    axes: dict[tuple[str, str], set[str]],
    system_axes: dict[int, str] | None = None,
    *,
    proposals: dict[str, str] | None = None,
    proposed_axes: dict[tuple[str, str], set[str]] | None = None,
    proposed_system_axes: dict[int, str] | None = None,
) -> dict[str, Any]:
    """`system_axes`: direction index -> Tekla axis from this system's own grid_system_axis_unassigned
    answer; unioned with the family answers (a disagreement is 'contradictory'). Both come from the
    engineer's answers only. `proposals` (file -> unit), `proposed_axes` and `proposed_system_axes` are what
    the answers of every role (non-engineer ones included) would give: a value that only they give is
    `proposed_simulated` and converts or assigns nothing."""
    proposals = proposals or {}
    rep = s.rep
    full = s.full()
    groups = _components([m.view for m in full], ctx)
    group_of = {id(m): g for m, g in zip(full, groups, strict=True)}
    independent = len(set(groups))
    flags = set(s.flags)
    if independent < 2:
        flags.add("single_source")
    if len(rep.fams) == 1:
        flags.add("single_direction")
    files = sorted({m.view.file for m in s.members})
    declared_set = {ctx[f].declared for f in files}
    declared = next(iter(declared_set)) if len(declared_set) == 1 else "mixed"
    if len(declared_set) > 1:
        flags.add("declared_units_differ")

    units_block, factor = _units_block(files, rep.file, declared, units, proposals, flags)

    axis_status, axis_reason, per_dir = _axis_state(s, axes, system_axes)
    if (
        axis_status != "answered"
        and _axis_state(s, proposed_axes or {}, proposed_system_axes)[0] == "answered"
    ):
        axis_status, axis_reason = PROPOSED, AXIS_NOT_ENGINEER
    if axis_status != "answered":
        flags.add("axis_unassigned")

    directions = []
    for d, rf in enumerate(rep.fams):
        spread, tolerated, count = 0.0, False, 0
        for m in s.members:
            f = s.family_of(m, d)
            if f is None:
                continue
            count += 1
            if f is not rf:
                c = _compare(f, rf)
                spread, tolerated = max(spread, c.spread), tolerated or c.tolerated
        if tolerated:
            flags.add("within_drafting_tolerance")
        if not rf.complete:
            flags.add("family_incomplete")
        conf = min_conf(MAX_CONFIDENCE, rf.confidence, "low" if not rf.complete else None)
        directions.append(
            {
                "labels": list(rf.labels),
                "spacings": [rnum(v) for v in rf.spacings],
                "coordinates": coordinate_string([rnum(v) for v in rf.spacings]),
                "unit": declared,
                "rounding_step": rf.step,
                "angle_deg": rnum(rf.angle),
                "max_relative_spread": rnum(spread),
                "families": count,
                "representative": rf.ref(),
                "provenance": {"file": rf.file, "sheet": rf.sheet, "method": "derived"},
                "confidence": conf,
                "tekla_axis": next(iter(per_dir[d])) if axis_status == "answered" else None,
                "mm": _mm(rf.spacings, factor) if factor is not None else None,
            }
        )
    low = flags & {"single_source", "ambiguous_subset", "family_incomplete"}
    confidence = min_conf(MAX_CONFIDENCE, *(x["confidence"] for x in directions), "low" if low else None)

    tekla_grid = _tekla_grid(directions, factor, axis_status)

    contributors = []
    for m in sorted(s.members, key=lambda m: (m.role != "full", m.view.file, m.view.group_id)):
        contributors.append(
            {
                "file": m.view.file,
                "sheet": m.view.sheet,
                "group_id": m.view.group_id,
                "role": m.role,
                "independence_group": group_of.get(id(m)),
                "families": [
                    {
                        "family_id": f.family_id,
                        "direction": d,
                        "labels": f.label_text(),
                        "complete": f.complete,
                    }
                    for f, d in sorted(zip(m.view.fams, m.dirs, strict=True), key=lambda x: x[1])
                ],
            }
        )
    return {
        "system_id": sid,
        "status": "proposal",
        "directions": directions,
        "evidence": {
            "views": len(s.members),
            "full_views": len(full),
            "partial_views": len(s.members) - len(full),
            "independent_views": independent,
            "sheets": len({(m.view.file, m.view.sheet) for m in s.members}),
            "files": len(files),
            "contributors": contributors,
        },
        "flags": sorted(flags),
        "confidence": confidence,
        "relations": {"compatible_with": [], "conflicts_with": [], "subset_of": []},
        "units": units_block,
        "axis_assignment": {"status": axis_status, "reason": axis_reason},
        "tekla_grid": tekla_grid,
        "svg": f"{GRID_SYSTEMS_DIR}/{sid}.svg",
        "note": "Proposal only: drawing-unit spacings of the representative family (never averaged). "
        "Confirm the system, its building, units and Tekla X/Y at gate 1.",
    }


# --- a grid system from the engineer's answer (ADR-0013) ----------------------------------------------


@dataclass
class _GivenGrid:
    """A structured grid_system_missing answer: labels and spacings (drawing units) of dir1 and dir2."""

    file: str
    answer: dict[str, Any]
    directions: list[tuple[list[str], list[float]]]
    sheet: str | None


def _given_spacing(value: Any) -> float | None:
    """A hand-written spacing as a float, or None when it is not a number, overflows a float (a 400-digit
    integer, review m1) or is not > 0 and at most MAX_SPACING."""
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if spacing_in_range(number) else None


def _given_grid(answer: dict[str, Any], file: str) -> tuple[_GivenGrid | None, str | None]:
    """The grid an active engineer answer gives (ADR-0013 §2), or None and why it builds nothing: words only
    (no value), or values that are not exactly the four keys (plus an optional sheet) with, per direction,
    at least two non-blank labels, distinct ignoring case, and one spacing fewer, each > 0 and at most
    MAX_SPACING (a number too large for a float included). Checked here as well as by `harness answer`:
    answers.json may have been written by hand."""
    values = answer.get("values")
    if answer.get("file") != file:
        return None, f"it names file {answer.get('file')!r}, not {file!r}"
    if not isinstance(values, dict) or not values:
        return None, "it is in words only (no dir1_labels / dir1_spacings / dir2_labels / dir2_spacings)"
    allowed = {*GRID_ANSWER_KEYS, GRID_ANSWER_SHEET_KEY}
    if set(values) - allowed or not set(GRID_ANSWER_KEYS) <= set(values):
        return None, f"its keys {', '.join(sorted(values))} are not {', '.join(GRID_ANSWER_KEYS)} [sheet]"
    directions: list[tuple[list[str], list[float]]] = []
    for name in AXIS_DIRECTIONS:
        labels, spacings = values[f"{name}_labels"], values[f"{name}_spacings"]
        if not (
            isinstance(labels, list)
            and len(labels) >= 2
            and all(isinstance(x, str) and x.strip() for x in labels)
            and len({x.strip().casefold() for x in labels}) == len(labels)  # case-blind: review m2
        ):
            return None, (
                f"{name}_labels is not two or more distinct (ignoring case), non-blank labels ({labels!r})"
            )
        numbers = [_given_spacing(v) for v in spacings] if isinstance(spacings, list) else []
        if not (isinstance(spacings, list) and len(spacings) == len(labels) - 1 and None not in numbers):
            shown = repr(spacings) if len(repr(spacings)) <= 200 else repr(spacings)[:200] + "..."
            return None, (
                f"{name}_spacings is not {len(labels) - 1} number(s) > 0 and at most {MAX_SPACING:.0f} "
                f"({shown})"
            )
        directions.append(([x.strip() for x in labels], [v for v in numbers if v is not None]))
    sheet = values.get(GRID_ANSWER_SHEET_KEY)
    if sheet is not None and not (isinstance(sheet, str) and sheet.strip()):
        return None, f"its sheet {sheet!r} is blank"
    return _GivenGrid(file, answer, directions, sheet.strip() if isinstance(sheet, str) else None), None


def _given_axis_found(grid: _GivenGrid) -> str:
    """`found` of the X/Y question of an answer-built system: its directions as the answer gives them."""
    return "; ".join(
        f"{AXIS_DIRECTIONS[d]}: labels {' '.join(labels)} (engineer answer)"
        for d, (labels, _) in enumerate(grid.directions)
    )


def _factor(units: dict[str, tuple[str, str | None]], file: str) -> float | None:
    """mm per drawing unit of a file with an agreeing engineer units answer; None otherwise."""
    status, unit = units[file]
    return UNIT_TO_MM[unit] if status == "answered" and unit is not None else None


def _given_fams(grid: _GivenGrid, factor: float | None) -> list[_Fam]:
    """The directions of an answer-built system as families, for the pairwise conflict check (ADR-0013
    decision 6, review M1): positions are the cumulative given spacings, with no rounding step (only the
    drafting tolerance applies), compared in millimetres when the file has an agreeing engineer units
    answer (`factor`), like a detected family. Their view and family ids name the answered question's key
    and the direction, never the positional system id, so a conflict question keeps its key."""
    key = str(grid.answer["key"])
    return [
        _Fam(
            file=grid.file,
            sheet=grid.sheet or SHEET_UNKNOWN,
            group_id=f"answer {key}",
            family_id=AXIS_DIRECTIONS[d],
            labels=list(labels),
            pos={lbl: sum(spacings[:k]) for k, lbl in enumerate(labels)},
            spacings=list(spacings),
            step=0.0,
            angle=0.0,
            complete=True,
            confidence=MAX_CONFIDENCE,
            factor=factor,
        )
        for d, (labels, spacings) in enumerate(grid.directions)
    ]


def _given_axes(n_dirs: int, system_axes: dict[int, str] | None) -> tuple[str, str | None]:
    """X/Y of an answer-built system: only from its own grid_system_axis_unassigned answer (it has no
    family a grid_family_axis_assignment answer could name)."""
    if system_axes and len(system_axes) == n_dirs:
        return "answered", None
    return "not_answered", "no axis answer covers every direction"


def _given_system_json(
    sid: str,
    grid: _GivenGrid,
    ctx: dict[str, _FileCtx],
    units: dict[str, tuple[str, str | None]],
    proposals: dict[str, str],
    system_axes: dict[int, str] | None,
    proposed_system_axes: dict[int, str] | None,
) -> dict[str, Any]:
    """A system with `source: engineer_answer`: no view, family or contributor; the answer is its provenance.
    It goes through the same gate-1 steps as a detected system (select, Tekla X/Y, units)."""
    flags: set[str] = set()
    declared = ctx[grid.file].declared
    units_block, factor = _units_block([grid.file], grid.file, declared, units, proposals, flags)
    axis_status, axis_reason = _given_axes(len(grid.directions), system_axes)
    if axis_status != "answered" and _given_axes(len(grid.directions), proposed_system_axes)[0] == "answered":
        axis_status, axis_reason = PROPOSED, AXIS_NOT_ENGINEER
    if axis_status != "answered":
        flags.add("axis_unassigned")
    qid = str(grid.answer.get("question_id"))
    directions = []
    for d, (labels, spacings) in enumerate(grid.directions):
        values = [rnum(v) for v in spacings]
        directions.append(
            {
                "labels": list(labels),
                "spacings": values,
                "coordinates": coordinate_string(values),
                "unit": declared,
                "rounding_step": None,
                "angle_deg": None,
                "max_relative_spread": 0.0,
                "families": 0,
                "representative": None,
                "provenance": {
                    "file": grid.file,
                    "sheet": grid.sheet or SHEET_UNKNOWN,
                    "method": "engineer_answer",
                    "question_id": qid,
                },
                "confidence": MAX_CONFIDENCE,
                "tekla_axis": (system_axes or {}).get(d) if axis_status == "answered" else None,
                "mm": _mm(spacings, factor) if factor is not None else None,
            }
        )
    return {
        "system_id": sid,
        "status": "proposal",
        "source": "engineer_answer",
        "source_answer": {"question_id": qid, "key": str(grid.answer["key"])},
        "directions": directions,
        "evidence": {
            "views": 0,
            "full_views": 0,
            "partial_views": 0,
            "independent_views": 0,
            "sheets": 1 if grid.sheet else 0,
            "files": 1,
            "contributors": [],
        },
        "flags": sorted(flags),
        "confidence": MAX_CONFIDENCE,
        "relations": {"compatible_with": [], "conflicts_with": [], "subset_of": []},
        "units": units_block,
        "axis_assignment": {"status": axis_status, "reason": axis_reason},
        "tekla_grid": _tekla_grid(directions, factor, axis_status),
        "svg": f"{GRID_SYSTEMS_DIR}/{sid}.svg",
        "note": f"Built from the engineer's answer {qid} ({GRID_MISSING_CODE}, ADR-0013), drawing units as "
        "given. Confirm the system, its building, units and Tekla X/Y at gate 1.",
    }


def _given_vs_dimensions(grid: _GivenGrid, dims: list[dict[str, Any]]) -> tuple[list[str], int]:
    """ADR-0013 §5: the linear dimensions grids.py placed between two axes whose labels (case-blind) are two
    labels of one given direction, compared with the distance the answer gives between them (a sum of
    spacings for a span). Returns the disagreements (beyond DRAFTING_TOL of the distance) and the number of
    dimensions compared. A dimension without a numeric value (not_numeric) compares nothing."""
    out: list[str] = []
    compared = 0
    for name, (labels, spacings) in zip(AXIS_DIRECTIONS, grid.directions, strict=True):
        pos = {lbl.casefold(): sum(spacings[:k]) for k, lbl in enumerate(labels)}
        for e in dims:
            a, b = (e["from_label"] or "").casefold(), (e["to_label"] or "").casefold()
            if a not in pos or b not in pos or a == b or e["displayed"] is None:
                continue
            compared += 1
            given, drawn = abs(pos[b] - pos[a]), abs(float(e["displayed"]))
            if abs(given - drawn) <= DRAFTING_TOL * max(given, drawn):
                continue
            text = f" text '{e['text']}'" if e["text"] not in ("", "<>") else ""
            out.append(
                f"{name} {e['from_label']}-{e['to_label']}: answer {fmt_number(rnum(given))} vs dimension "
                f"{e['handle'] or '?'}{text} = {fmt_number(rnum(drawn))} on sheet {e['sheet']} ({e['where']})"
            )
    return out, compared


def _ask_given_grids(
    ask: _Ask,
    docs: list[dict[str, Any]],
    systems: list[_System],
    selected: set[str],
    missing: dict[str, tuple[str, str, str]],
    engineer_answered: set[str],
    no_grid: set[str],
    given: list[_GivenGrid],
    given_ids: list[str],
    inputs: _Inputs,
    warnings: list[str],
) -> None:
    """ADR-0013 §1 and §5. grid_system_missing for every read file that no selected two-direction DETECTED
    system covers, and for every file whose engineer answer built a system or is no_grid=yes (`no_grid`)
    (`engineer_answered`: the question stays raised under its key, so the answer stays bound and the
    system it built stays: Ledger.sync makes an answer to a question no longer raised stale; an answer that
    builds nothing does not keep it raised). grid_answer_contradicts_drawing for every answer-built
    system that a linear dimension between two of its axes disagrees with; a system nothing could be
    checked against is warned."""
    usable: set[str] = set()
    detected: dict[str, list[str]] = {f: [] for f in missing}
    for d, s in zip(docs, systems, strict=False):  # the detected systems come first in docs
        files = {m.view.file for m in s.members}
        two = len(d["directions"]) == 2
        if two and d["system_id"] in selected:
            usable |= files
        state = "single direction" if not two else "usable" if d["system_id"] in selected else "not selected"
        labels = " x ".join(" ".join(x["labels"]) for x in d["directions"])
        for f in files:
            detected[f].append(f"{d['system_id']} {labels} ({state})")
    built = {grid.file: sid for sid, grid in zip(given_ids, given, strict=True)}
    for f, (where, found, _key) in missing.items():
        if f in usable and f not in engineer_answered:
            continue
        lead = ""
        if f in built:
            lead = (
                f"Answered: {built[f]} was built from the engineer's answer; it goes through "
                f"{SELECT_CODE}, Tekla X / Y and units like a detected system. "
            )
        elif f in no_grid:
            lead = (
                f"Answered: the engineer states that {f} holds no plan that needs a grid "
                f"({NO_GRID_KEY}=yes): no grid system is built for it. "
            )
        ask(
            GRID_MISSING_CODE,
            f"{lead}Gate 1: {f} has no usable grid system (two directions of at least two labelled axes "
            f"each, not left out by the engineer's {SELECT_CODE} answer). Systems detected in this file: "
            f"{'; '.join(detected[f][:20]) or 'none'}. Read the grid on the drawing and give its labels and "
            "spacings in drawing units, in drawing order: --value dir1_labels=1,2,3 --value "
            "dir1_spacings=3130,3540 --value dir2_labels=A,B --value dir2_spacings=4250 (one spacing fewer "
            "than labels in each direction), plus --value sheet=<sheet id> when it is read off one sheet. "
            f"When the file holds no plan that needs a grid (notes, details or sections only), answer "
            f"--value {NO_GRID_KEY}=yes alone instead. Only the engineer's answer (--role engineer) builds a "
            "grid system or closes this question; then rerun harness grid-system.",
            where,
            found,
            f,
        )
    for sid, grid in zip(given_ids, given, strict=True):
        qid = grid.answer.get("question_id")
        diffs, compared = _given_vs_dimensions(grid, inputs.facts[grid.file]["dims"])
        if not compared:
            warnings.append(
                f"{grid.file}: the grid given in {qid} ({sid}) was not checked against the drawing: no "
                "linear dimension lies between two of its axes"
            )
        if not diffs:
            continue
        more = (
            f" (+{len(diffs) - MAX_DIFFERENCES_QUOTED} more)" if len(diffs) > MAX_DIFFERENCES_QUOTED else ""
        )
        ask(
            GRID_CONTRADICTS_CODE,
            f"The grid the engineer gave for {grid.file} ({qid}, built as {sid}) disagrees with {len(diffs)} "
            "linear dimension(s) drawn between its axes (both values in found). Check the answer: answer "
            f"{GRID_MISSING_CODE} again with the right values, or answer this question to confirm that the "
            "answer is right and the drawing is wrong. It takes no value.",
            _answer_axis_where(grid.file, str(grid.answer["key"])),
            "; ".join(diffs[:MAX_DIFFERENCES_QUOTED]) + more,
            grid.file,
        )


def _file_sets(
    active: list[dict[str, Any]],
    file_set: tuple[str, str] | None,
    readable: int,
    files: list[str],
    warnings: list[str],
) -> tuple[dict[str, int], dict[str, Any] | None]:
    """file -> its set number, and the document's `file_sets`. `file_set`: (key, id) of the live intake
    file_set_relation question; its answer is bound by key. Without a live question every file is in set 0
    (one readable file: 'single'; two or more: an intake from before file sets, `file_sets` left out)."""
    if file_set is None:
        single = {"status": "single", "sets": None, "question_id": None} if readable < 2 else None
        return {}, single
    key, qid = file_set
    answer = next((a for a in active if a.get("code") == FILE_SET_CODE and a.get("key") == key), None)
    values = answer.get("values") if answer is not None else None
    ok = (
        isinstance(values, dict)
        and bool(values)
        and all(FILE_SET_KEY.fullmatch(str(k)) and isinstance(v, list) and v for k, v in values.items())
    )
    if answer is not None and not ok:
        warnings.append(
            f"{FILE_SET_CODE} answer {key!r} has no set1=... values (values {values!r}): not used"
        )
    if answer is None or not ok or not isinstance(values, dict):
        return {}, {"status": "pending", "sets": None, "question_id": qid}
    names = sorted(values, key=lambda k: int(str(k)[3:]))
    set_of = {str(f): int(str(k)[3:]) for k in names for f in values[k]}
    for k, f in enumerate(sorted(set(files) - set(set_of)), start=1):
        warnings.append(f"{f} is in no set of the {FILE_SET_CODE} answer: compared with no other file")
        set_of[f] = -k
    return set_of, {
        "status": "answered",
        "sets": [[str(f) for f in values[k]] for k in names],
        "question_id": qid,
    }


def build_grid_systems(
    work_dir: str | Path,
    *,
    answers: list[dict[str, Any]] | None = None,
    write: bool = False,
    file_set: tuple[str, str] | None = None,
) -> dict[str, Any]:
    """Grid systems of a read-structure work folder. Raises GridSystemError. See the module docstring.
    `file_set`: (registry key, id) of the live intake file_set_relation question, when there is one."""
    work = Path(work_dir)
    inputs = _load_inputs(work)
    warnings = list(inputs.warnings)
    active = _active(answers)
    # only the engineer's answers confirm, assign, select or close; the others are proposals (tool wave 3)
    engineer = [a for a in active if _by_engineer(a)]
    others = [a for a in active if not _by_engineer(a)]
    file_paths = [f["path"] for f in inputs.files if f["status"] == "read"]
    set_of, file_sets = _file_sets(engineer, file_set, inputs.readable, file_paths, warnings)
    for a in others:
        if file_set is not None and a.get("code") == FILE_SET_CODE and a.get("key") == file_set[0]:
            warnings.append(_not_engineer(a, "recorded, the file sets stay pending"))
    units = units_by_file(engineer, file_paths, warnings)
    proposals = {
        f: str(u)
        for f, (st, u) in units_by_file(others, file_paths, warnings).items()
        if st == "answered" and units[f][0] == "not_answered"
    }
    for f, u in sorted(proposals.items()):
        warnings.append(f"{f}: units {u} only from a non-engineer answer: proposed, converts nothing")
    axes = _axis_answers(engineer, warnings)
    proposed_axes = _axis_answers(active, [])
    sha = {f["path"]: f["sha256"] for f in inputs.files}

    # an answered unit that the drawing's own dimensions contradict converts nothing until the engineer
    # confirms it; a non-engineer unit is tested too (an agent builds on it), where no engineer answered
    probed = sorted(p for p, u in inputs.inventory_units.items() if u is not None)
    by_engineer, by_others = units_by_file(engineer, probed, []), units_by_file(others, probed, [])
    effective = {p: by_engineer[p] if by_engineer[p][0] != "not_answered" else by_others[p] for p in probed}
    # the grid-spacing units evidence is the median of the file's plan systems (a single-source key plan never
    # decides it), so systems are built once in drawing units before any answered unit converts anything
    kept, _ = _drop_strays(_systems(_clusters(inputs.views, set_of), inputs.ctx, set_of), inputs.ctx)
    plan_medians = _plan_spacing_medians(kept, inputs.ctx)
    for f in inputs.files:
        if f["status"] == "read":
            f["grid_spacing_median"] = plan_medians.get(f["path"])
            inputs.spacing_medians[f["path"]] = f["grid_spacing_median"]
    contradictions = _contradictions(
        active, effective, inputs.inventory_units, sha, inputs.spacing_medians, engineer
    )
    for c in contradictions:
        if not c["confirmed"] and units.get(c["file"], ("",))[0] == "answered":
            units[c["file"]] = ("contradicted", None)
    for f in inputs.files:
        st = units.get(f["path"])
        if f["path"] in proposals:
            st = (PROPOSED, proposals[f["path"]])
        f["units_answer"] = None if st is None else {"status": st[0], "unit": st[1]}

    for v in inputs.views:  # an agreeing units answer lets the matching compare this file in millimetres
        for f in v.fams:
            f.factor = _factor(units, f.file)
    systems, strays = _drop_strays(_systems(_clusters(inputs.views, set_of), inputs.ctx, set_of), inputs.ctx)
    ids = [f"S{k:03d}" for k in range(1, len(systems) + 1)]
    for stray, main in strays:
        rf = stray.rep.fams[0]
        inputs.totals["families_unassigned"] += 1
        inputs.unassigned.append(
            {
                "file": rf.file,
                "sheet": rf.sheet,
                "group_id": rf.group_id,
                "family_id": rf.family_id,
                "labels": rf.label_text(),
                "reason": "a family of one direction seen in one view, beside the file's grid "
                f"system {ids[systems.index(main)]}: not proposed as a grid system (rebar or pile marks, a "
                "3D view, a detail?)",
            }
        )
    place: dict[str, tuple[str, str | None]] = {}  # system -> (file, sheet) its questions are filed under
    sys_files: dict[str, list[str]] = {}  # system -> the drawing files it comes from

    # every read file's grid_system_missing question, keyed by the drawing alone (ADR-0013): an active
    # ENGINEER answer with structured values builds a system after the detected ones (their ids stay)
    missing: dict[str, tuple[str, str, str]] = {}  # file -> where, found, key
    engineer_answered: set[str] = set()
    no_grid: set[str] = set()  # files the engineer answered no_grid=yes for (ADR-0013 §2)
    given: list[_GivenGrid] = []
    for f in file_paths:
        where, found = f"{f}: no usable grid system", inputs.facts[f]["found"]
        key = _own_key(GRID_MISSING_CODE, f, where, found, None, sha)
        missing[f] = (where, found, key)
        answer = next((a for a in active if a.get("code") == GRID_MISSING_CODE and a.get("key") == key), None)
        if answer is None:
            continue
        if not _by_engineer(answer):
            warnings.append(_not_engineer(answer, "recorded, builds nothing"))
            continue
        if is_no_grid(answer.get("values")):  # the engineer: no plan that needs a grid; builds nothing
            no_grid.add(f)
            engineer_answered.add(f)  # the statement stays bound to the question while it stands
            continue
        grid, why = _given_grid(answer, f)
        if grid is None:  # the question is raised only while the file is not covered (review M2)
            warnings.append(f"the {GRID_MISSING_CODE} answer {key!r} for {f} builds nothing: {why}")
        else:
            engineer_answered.add(f)
            given.append(grid)
    given_ids = [f"S{k:03d}" for k in range(len(ids) + 1, len(ids) + len(given) + 1)]

    # each system's own X/Y question; its answer is bound by this run's key
    axis_found: dict[str, str] = {}
    axis_wheres: dict[str, str] = {}
    axis_keys: dict[str, str] = {}
    system_axes: dict[str, dict[int, str]] = {}
    proposed_system_axes: dict[str, dict[int, str]] = {}  # whatever role answered

    def bind_axes(sid: str, n_dirs: int) -> None:
        file, sheet = place[sid]
        axis_keys[sid] = _own_key(SYSTEM_AXIS_CODE, file, axis_wheres[sid], axis_found[sid], sheet, sha)
        answer = next(
            (a for a in active if a.get("code") == SYSTEM_AXIS_CODE and a.get("key") == axis_keys[sid]), None
        )
        if answer is not None:
            proposed_system_axes[sid] = _system_axis_values(answer, n_dirs, sid, warnings)
            if _by_engineer(answer):
                system_axes[sid] = proposed_system_axes[sid]
            else:
                warnings.append(_not_engineer(answer, f"recorded, assigns no Tekla X / Y to {sid}"))

    for sid, s in zip(ids, systems, strict=True):
        rf = s.rep.fams[0]
        place[sid], sys_files[sid] = (rf.file, rf.sheet), sorted({m.view.file for m in s.members})
        axis_found[sid] = _axis_found(s)
        axis_wheres[sid] = axis_where([f.ref() for f in s.rep.fams])
        bind_axes(sid, len(s.rep.fams))
    for sid, grid in zip(given_ids, given, strict=True):
        place[sid], sys_files[sid] = (grid.file, None), [grid.file]
        axis_found[sid] = _given_axis_found(grid)
        axis_wheres[sid] = _answer_axis_where(grid.file, str(grid.answer["key"]))
        bind_axes(sid, len(grid.directions))
    docs = [
        _system_json(
            sid,
            s,
            inputs.ctx,
            units,
            axes,
            system_axes.get(sid),
            proposals=proposals,
            proposed_axes=proposed_axes,
            proposed_system_axes=proposed_system_axes.get(sid),
        )
        for sid, s in zip(ids, systems, strict=True)
    ]
    docs += [
        _given_system_json(
            sid,
            grid,
            inputs.ctx,
            units,
            proposals,
            system_axes.get(sid),
            proposed_system_axes.get(sid),
        )
        for sid, grid in zip(given_ids, given, strict=True)
    ]
    all_ids = ids + given_ids

    used_families = {(m.view.file, f.family_id) for s in systems for m in s.members for f in m.view.fams}
    for file, fid in sorted(set(axes) - used_families):
        warnings.append(f"axis answer for {file} {fid} matches no family of any grid system")

    # the grid_system_select answer of THIS run's question (bound by key): which systems are used, which
    # are declared separate buildings
    # (only the engineer's answer selects; a non-engineer one is what it WOULD select: proposed_closed_by)
    selected, separate = set(all_ids), set()
    proposed: tuple[set[str], set[str]] | None = None
    select_key = question_key(SELECT_CODE, None, None, _select_refs(docs, sha)) if docs else None
    select = next((a for a in active if a.get("code") == SELECT_CODE and a.get("key") == select_key), None)
    if select is not None and isinstance(select.get("values"), dict):
        chosen, apart = set(all_ids), set()
        if isinstance(select["values"].get("systems"), list) and select["values"]["systems"]:
            chosen = {str(x) for x in select["values"]["systems"]}
        if isinstance(select["values"].get("separate"), list):
            apart = {str(x) for x in select["values"]["separate"]}
        for sid in sorted((chosen | apart) - set(all_ids)):
            warnings.append(f"the {SELECT_CODE} answer names {sid}, which is not a system of this run")
        if _by_engineer(select):
            selected, separate = chosen, apart
        else:
            proposed = (chosen, apart)
            warnings.append(_not_engineer(select, "recorded, selects and closes nothing"))

    ask = _Ask()
    clashes: list[tuple[str, str, str, str, str]] = []  # where, found, file, sheet, what differs (message)
    pairs: list[tuple[str, str]] = []
    # every system against every other, answer-built ones included (ADR-0013 decision 6): per system (in
    # all_ids order) its full members' families, its representative's, its files and its file-set file
    given_fams = [_given_fams(grid, _factor(units, grid.file)) for grid in given]
    members = [[m.view.fams for m in s.full()] for s in systems] + [[fams] for fams in given_fams]
    reps = [s.rep.fams for s in systems] + given_fams
    files_of = [{m.view.file for m in s.members} for s in systems] + [{grid.file} for grid in given]
    set_files = [s.rep.file for s in systems] + [grid.file for grid in given]
    waiting = file_sets is not None and file_sets["status"] == "pending"
    pending: list[bool] = []  # per clash: two systems with no file in common while the file sets are asked
    for i in range(len(all_ids)):
        for j in range(i + 1, len(all_ids)):
            if not _same_set(set_files[i], set_files[j], set_of):
                continue
            hit = _members_conflict(members[i], members[j])
            if hit is not None:
                docs[i]["relations"]["conflicts_with"].append(all_ids[j])
                docs[j]["relations"]["conflicts_with"].append(all_ids[i])
                fam_pairs, diffs = hit
                where, found, filed = _conflict_identity(fam_pairs)
                fa, fb = fam_pairs[0]
                what = f"{_where(all_ids[i], fa)} vs {_where(all_ids[j], fb)}: {'; '.join(diffs[:20])}"
                clashes.append((where, found, filed.file, filed.sheet, what))
                pairs.append((all_ids[i], all_ids[j]))
                pending.append(waiting and not files_of[i] & files_of[j])
            elif _related(reps[i], reps[j]):
                docs[i]["relations"]["compatible_with"].append(all_ids[j])
                docs[j]["relations"]["compatible_with"].append(all_ids[i])
    for k, s in enumerate(systems):
        docs[k]["relations"]["subset_of"] = [ids[i] for i in s.subset_of]

    if docs:
        ask(
            SELECT_CODE,
            "Gate 1: which of these grid systems are the project's grids, and which building or structure "
            "is each? None is used until confirmed. Structured values (optional): systems=S001,S002 (the "
            "systems the project uses; the others stop blocking) and separate=S001,S002 (selected systems "
            "that are different buildings: closes the conflicts between them).",
            listed(all_ids),
            "; ".join(_system_found(d) for d in docs[:20]),
        )
    else:
        warnings.append(
            "no grid system: no view has a usable grid family (see the grids documents' questions)"
        )
    conflicts: list[dict[str, Any]] = []
    for (where, found, file, sheet, what), (a, b), wait in zip(clashes, pairs, pending, strict=True):
        closed_by = _closure(a, b, selected, separate)
        # one select answer is active: when it is a non-engineer's, the engineer's selection is "all"
        would = _closure(a, b, *proposed) if proposed is not None else None
        base = (
            "Two grid systems use the same axis labels with different spacings or order, so they are kept "
            f"apart ({what}). Are they different buildings or structures, or is one of them wrong?"
        )
        if closed_by == "not_selected":
            message = (
                f"Not blocking: {a if a not in selected else b} is not among the selected systems. " + base
            )
        elif closed_by == "separate":
            message = (
                f"Not blocking: the {SELECT_CODE} answer declares {a} and {b} separate buildings. " + base
            )
        else:
            message = (
                f"{base} An answer here closes nothing: answer {SELECT_CODE} with systems= leaving one of "
                f"them out, or with separate={a},{b} when they are different buildings, then rerun "
                "harness grid-system."
            )
            if would is not None:
                message += (
                    f" A {SELECT_CODE} answer by a non-engineer role would close it ({would}); it closes "
                    "nothing until the engineer answers."
                )
            if wait and file_sets is not None:
                message = (
                    f"Not blocking yet: pending {file_sets['question_id']} ({FILE_SET_CODE}): the two "
                    "systems come from different drawing files, which may be separate projects; once that "
                    "question is answered they are compared only when they are in one set. " + message
                )
            for sid in (a, b):  # the flag asks for action: only while a conflict of the system is open
                d = docs[all_ids.index(sid)]
                d["flags"] = sorted({*d["flags"], "conflict"})
        blocking = closed_by is None and not wait
        raised = ask(CONFLICT_CODE, message, where, found, file, sheet, blocking=blocking)
        conflicts.append(
            {
                "systems": [a, b],
                "blocking": blocking,
                "closed_by": closed_by,
                **({"proposed_closed_by": would} if would is not None else {}),
                "question_key": _own_key(CONFLICT_CODE, file, where, found, sheet, sha) if raised else None,
            }
        )
    for d in docs:
        sid = d["system_id"]
        file, sheet = place[sid]
        if d["units"]["status"] != "confirmed":
            ask(
                "grid_system_units_unconfirmed",
                "Not blocking: answer the units_confirm_all question of each file (harness intake), then "
                "rerun harness grid-system. This grid system is in drawing units and no agreeing units "
                "answer covers every file it comes from.",
                sid,
                f"{d['units']['reason']}; "
                + "; ".join(
                    f"{f}: declared {inputs.ctx[f].declared}, answer {units[f][0]}"
                    for f in sys_files[sid][:20]
                ),
                file,
                sheet,
                blocking=False,
            )
        names = " and ".join(AXIS_DIRECTIONS[: len(d["directions"])])
        base = (
            f"Grid system {sid}: which direction of this grid system is Tekla X (lines parallel to Y) and "
            f"which is Y? Answer with --value for {names} as listed in found (e.g. dir1=X), or answer "
            "grid_family_axis_assignment per family."
        )
        status = d["axis_assignment"]["status"]
        if sid not in selected:
            blocking, message = False, f"Not blocking: {sid} is not among the selected systems. {base}"
        elif status == "answered":
            blocking, message = False, f"Not blocking: Tekla X / Y is assigned. {base}"
        else:
            blocking, message = True, f"{base} ({d['axis_assignment']['reason']})"
        raised = ask(
            SYSTEM_AXIS_CODE, message, axis_wheres[sid], axis_found[sid], file, sheet, blocking=blocking
        )
        d["axis_question_key"] = axis_keys[sid] if raised else None
    for c in contradictions:
        ask(
            CONTRADICTION_CODE,
            f"The units answer for this file ({c['unit']}) makes the drawing's own dimensions implausible "
            "(the units_suspect test: the median modelspace linear dimension must fall between 0.01 m and "
            "100 m; or the median grid spacing between 0.5 m and 30 m). Answer the file's units_confirm_all "
            "again with the right unit, or confirm this unit on "
            f"purpose by answering this question with --value unit={c['unit']}.",
            c["where"],
            c["found"],
            c["file"],
        )
    _ask_given_grids(
        ask, docs, systems, selected, missing, engineer_answered, no_grid, given, given_ids, inputs, warnings
    )
    for code, n in sorted(ask.counts.items()):
        if n > MAX_QUESTIONS_PER_CODE:
            warnings.append(f"{n} '{code}' questions; only the first {MAX_QUESTIONS_PER_CODE} are listed.")

    doc = {
        "schema_version": SCHEMA_VERSION,
        "project_id": inputs.project_id,
        "inventory_sha256": inputs.inventory_sha,
        "answers_sha256": consumed_answers_digest(answers),
        "heuristics": {
            "drafting_tolerance": DRAFTING_TOL,
            "orthogonal_tolerance_deg": FAMILY_ANGLE_TOL,
            "max_confidence": MAX_CONFIDENCE,
        },
        "files": inputs.files,
        "systems": docs,
        "unassigned_families": inputs.unassigned,
        "summary": {
            "files_read": len(file_paths),
            "views": inputs.totals["views"],
            "views_used": len({(m.view.file, m.view.group_id) for s in systems for m in s.members}),
            "single_axis_families": inputs.totals["single_axis_families"],
            "families_unassigned": inputs.totals["families_unassigned"],
            "systems": len(docs),
            "two_direction": sum(1 for d in docs if len(d["directions"]) == 2),
            "single_source": sum(1 for d in docs if "single_source" in d["flags"]),
            "conflicts": len(clashes),
        },
        "conflicts": conflicts,
        **({"file_sets": file_sets} if file_sets is not None else {}),
        "questions": ask.questions,
        "question_counts": dict(sorted(ask.counts.items())),
        "warnings": warnings,
    }
    if write:
        write_grid_system_svgs(work, docs)
    return doc


def _system_found(d: dict[str, Any]) -> str:
    dirs = " x ".join(" ".join(x["labels"]) for x in d["directions"])
    ev = d["evidence"]
    counts = f"{ev['views']} view(s), {ev['independent_views']} independent, {ev['files']} file(s)"
    return f"{d['system_id']}: {dirs} ({counts})"


def write_grid_system_svgs(work: Path, docs: list[dict[str, Any]]) -> None:
    """Clear `structure/grid-systems/` and draw every system into it."""
    out = work / GRID_SYSTEMS_DIR
    try:
        if out.exists():
            shutil.rmtree(out)  # rerun: no stale drawings
        out.mkdir(parents=True)
        for d in docs:
            (work / d["svg"]).write_text(render_grid_system_svg(d), encoding="utf-8")
    except OSError as exc:
        raise GridSystemError(EXIT_ENV, f"cannot write grid-system drawings into {out}: {exc}") from exc


def clear_grid_system_svgs(work: Path) -> None:
    out = work / GRID_SYSTEMS_DIR
    try:
        if out.exists():
            shutil.rmtree(out)
    except OSError as exc:
        raise GridSystemError(EXIT_ENV, f"cannot clear {out}: {exc}") from exc


# --- the command: numbered questions, documents, drawings ----------------------------------------------


# registered one question per item (never merged per file): their answers are bound to the item by key
OWN_QUESTION_CODES = frozenset(
    {SYSTEM_AXIS_CODE, CONFLICT_CODE, CONTRADICTION_CODE, GRID_MISSING_CODE, GRID_CONTRADICTS_CODE}
)


def grid_system_questions(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Raw questions (no id, key or answer yet) of a grid-systems document, blocking first, then code, then
    file. `grid_system_select` is a question about the whole project (file null) with one ref per system; its
    ref carries the representative's file and sheet. grid_system_axis_unassigned (one per system, `subjects`
    dir1/dir2), grid_system_conflict (one per pair) and units_answer_contradicts_evidence (one per file) are
    one question each; grid_system_units_unconfirmed is one per (blocking flag, file)."""
    out: list[dict[str, Any]] = []
    groups: dict[tuple[str, bool, str], list[tuple[str, dict[str, Any]]]] = {}
    by_where = {_doc_axis_where(d): d for d in doc["systems"]}
    for q in doc["questions"]:
        if q["code"] == SELECT_CODE:
            refs = _select_refs(doc["systems"], {f["path"]: f["sha256"] for f in doc["files"]})
            out.append(question_group(SELECT_CODE, q["blocking"], q["message"], refs, file=None))
            continue
        ref = _raw_ref(q)
        if q["code"] in OWN_QUESTION_CODES:
            subjects = None
            if q["code"] == SYSTEM_AXIS_CODE:
                dirs = by_where[q["where"]]["directions"]
                # a direction built from an engineer answer has no family: its one source is that answer
                subjects = [
                    {"name": AXIS_DIRECTIONS[k], "count": x["families"] or 1} for k, x in enumerate(dirs)
                ]
            out.append(
                question_group(
                    q["code"], q["blocking"], q["message"], [ref], file=q["file"], subjects=subjects
                )
            )
            continue
        groups.setdefault((q["code"], q["blocking"], q["file"]), []).append((q["message"], ref))
    out += [merged_question(code, blocking, file, items) for (code, blocking, file), items in groups.items()]
    return sorted(out, key=lambda q: (not q["blocking"], q["code"], q["file"] or ""))


def _link_conflicts(doc: dict[str, Any], questions: list[dict[str, Any]]) -> None:
    """After the registry gave the ids: each conflict names its question id, and a conflict question the
    grid_system_select answer closed carries `closed_by` {question_id of the select question, reason}. The
    same closures are derived by lifecycle.closures for `harness status` and `harness questions-md`."""
    id_of = {q["key"]: q["id"] for q in questions}
    select_id = next((q["id"] for q in questions if q["code"] == SELECT_CODE), None)
    by_key = {q["key"]: q for q in questions}
    for c in doc["conflicts"]:
        key = c["question_key"]
        c["question_id"] = id_of.get(key) if key is not None else None
        if key is not None and c["closed_by"] is not None and key in by_key:
            by_key[key]["closed_by"] = Closure(select_id, c["closed_by"]).as_dict()


@dataclass
class GridSystemsResult:
    exit_code: int
    summary: dict[str, Any]


def _stdout_question_counts(questions: list[dict[str, Any]], summary: dict[str, int]) -> dict[str, Any]:
    """The question counts `harness grid-system` prints: the questions document's own counts plus
    `blocking_without_engineer_answer` and a note. The document counts a question as answered when any answer
    is recorded for it, a simulated one included, while `harness status` keeps a question that only a
    non-engineer answered open for gate 1: a bare `blocking_open 0` read as "nothing left to answer"."""
    out: dict[str, Any] = dict(summary)
    out["blocking_without_engineer_answer"] = sum(
        1 for q in questions if q["blocking"] and not (q["answer"] and _by_engineer(q["answer"]))
    )
    out["counts_note"] = (
        "answered and blocking_open count any recorded answer, a simulated one included; "
        "blocking_without_engineer_answer counts the blocking questions the engineer has not answered "
        "(run `harness status` for what keeps gate 1 closed)"
    )
    return out


def run_grid_systems(work_dir: str | Path, *, svg: bool = True) -> GridSystemsResult:
    """`harness grid-system`: build the grid systems of a read-structure work folder from the active answers,
    register the questions (producer 'grid-system') and write `grid-systems.json`,
    `grid-system-questions.json` and, with `svg`, `structure/grid-systems/*.svg`. Raises GridSystemError.

    Everything is built and validated in memory first; then the registry and answers are written, then the
    documents, then the drawings, so a failure never leaves a document that uses an unknown question id."""
    work = Path(work_dir).resolve()
    if not work.is_dir():
        raise GridSystemError(EXIT_USAGE, f"work folder not found (not a folder): {work_dir}")
    try:
        ledger = load_ledger(work, None, create=False)
    except QuestionsError as exc:
        raise GridSystemError(exc.exit_code, str(exc)) from exc
    live_sets = sorted(
        (int(e["id"][2:]), k, e["id"])
        for k, e in ledger.registry["questions"].items()
        if e["code"] == FILE_SET_CODE
        and e["producer"] == "intake"
        and e["status"] != "obsolete"
        and e.get("blocking", True)
    )
    file_set = (live_sets[-1][1], live_sets[-1][2]) if live_sets else None
    doc = build_grid_systems(work, answers=ledger.answers["answers"], file_set=file_set)
    problems = validate("grid-system", doc)
    if problems:  # a bug here, not in the drawings: never write an invalid document
        details = "; ".join(f"{p.path or '/'}: {p.message}" for p in problems[:5])
        raise GridSystemError(EXIT_INVALID, f"grid-systems.json would be invalid, nothing written: {details}")
    if doc["project_id"] != ledger.registry["project_id"]:
        raise GridSystemError(
            EXIT_INVALID,
            f"inventory.json is for project '{doc['project_id']}', question-registry.json for "
            f"'{ledger.registry['project_id']}'",
        )
    hashes = {f["path"]: f["sha256"] for f in doc["files"]}
    # a conflict between two file sets is not compared any more BECAUSE of the engineer's file_set_relation
    # answer: its registry entry says so (a non-engineer answer leaves the sets pending: nothing retired)
    answered_sets = (doc.get("file_sets") or {}).get("status") == "answered"
    superseded = {CONFLICT_CODE: FILE_SET_CODE} if answered_sets else None
    try:
        questions = ledger.sync("grid-system", grid_system_questions(doc), hashes, superseded_by=superseded)
    except QuestionsError as exc:
        raise GridSystemError(exc.exit_code, str(exc)) from exc
    _link_conflicts(doc, questions)
    # the fingerprint of the answers AFTER sync: an answer to a question of this producer that is no longer
    # raised just went stale (it was not applied: answers bind by key), so a rerun is not reported as stale
    doc["answers_sha256"] = consumed_answers_digest(ledger.answers["answers"])
    qdoc = questions_document(doc["project_id"], questions)
    for name, schema, data in (
        ("grid-systems.json", "grid-system", doc),
        ("grid-system-questions.json", "intake", qdoc),
    ):
        problems = validate(schema, data)
        if problems:
            details = "; ".join(f"{p.path or '/'}: {p.message}" for p in problems[:5])
            raise GridSystemError(EXIT_INVALID, f"{name} would be invalid, nothing written: {details}")
    try:
        texts = {"grid-systems.json": dump_json(doc), "grid-system-questions.json": dump_json(qdoc)}
        for text in texts.values():
            text.encode("utf-8")
    except (ValueError, UnicodeEncodeError) as exc:
        raise GridSystemError(
            EXIT_INVALID, f"grid-system output cannot be written as strict JSON: {exc}"
        ) from exc
    try:
        ledger.write()  # the registry is written before any document that uses its ids
        for name, text in texts.items():
            write_text_atomic(work / name, text)
    except OSError as exc:
        raise GridSystemError(EXIT_ENV, f"cannot write into {work}: {exc}") from exc
    if svg:
        write_grid_system_svgs(work, doc["systems"])
    else:
        clear_grid_system_svgs(work)
    summary = {
        "project_id": doc["project_id"],
        **doc["summary"],
        "grid_systems": [
            {
                "system_id": d["system_id"],
                "directions": [" ".join(x["labels"]) for x in d["directions"]],
                "confidence": d["confidence"],
                "flags": d["flags"],
                "independent_views": d["evidence"]["independent_views"],
                "units": d["units"]["status"],
                "axis_assignment": d["axis_assignment"]["status"],
                "svg": d["svg"] if svg else None,
            }
            for d in doc["systems"]
        ],
        **_stdout_question_counts(questions, qdoc["summary"]),
        "question_counts": doc["question_counts"],
        "stale_answers": ledger.stale_answers(),
        "warnings": doc["warnings"],
        "outputs": {
            "grid_systems": str(work / "grid-systems.json"),
            "questions": str(work / "grid-system-questions.json"),
            "svg_dir": str(work / GRID_SYSTEMS_DIR) if svg else None,
            "registry": str(work / "question-registry.json"),
        },
    }
    return GridSystemsResult(EXIT_OK, summary)


# --- SVG -------------------------------------------------------------------------------------------


def _t(
    x: float,
    y: float,
    text: str,
    size: int = 13,
    anchor: str = "start",
    weight: str = "normal",
    fill: str = "#111",
    cls: str | None = None,
) -> str:
    mark = f' class="{cls}"' if cls else ""
    return (
        f'<text{mark} x="{x:.2f}" y="{y:.2f}" font-family="monospace" font-size="{size}" '
        f'text-anchor="{anchor}" font-weight="{weight}" fill="{fill}">{escape(text)}</text>'
    )


SPACING_FONT = 11
CHAR_WIDTH = 0.6  # estimated glyph width as a fraction of the font size (monospace)
LABEL_GAP = 3.0  # clear space kept between two spacing labels
ROW_STEP = 14.0  # distance between staggered rows of spacing labels


def label_width(text: str, size: int = SPACING_FONT) -> float:
    return CHAR_WIDTH * size * len(text)


def _stagger(centers: list[float], extents: list[float]) -> list[int]:
    """Row of each label, in order, greedily: the first row whose last label is clear of it (labels are
    `extents` long, centred on `centers`, both along the dimension line)."""
    ends: list[float] = []  # far edge of the last label of each row
    rows: list[int] = []
    for c, e in zip(centers, extents, strict=True):
        for r, end in enumerate(ends):
            if c - e / 2 >= end + LABEL_GAP:
                ends[r] = c + e / 2
                rows.append(r)
                break
        else:
            ends.append(c + e / 2)
            rows.append(len(ends) - 1)
    return rows


def _vertical(d: dict[str, Any]) -> bool:
    """Drawn as vertical lines (positions along x): Tekla X when assigned, else lines closer to 90 deg."""
    if d.get("tekla_axis") in ("X", "Y"):
        return d["tekla_axis"] == "X"
    if d["angle_deg"] is None:  # an engineer-given grid has no drawn direction: drawn in listed order
        return False
    return abs((float(d["angle_deg"]) % 180.0) - 90.0) < 45.0


def _cumulative(spacings: list[float]) -> list[float]:
    out = [0.0]
    for s in spacings:
        out.append(out[-1] + float(s))
    return out


def render_grid_system_svg(system: dict[str, Any]) -> str:
    """Deterministic plain SVG of one grid system (no scripts, links or external fonts)."""
    dirs = system["directions"]
    vert = [d for d in dirs if _vertical(d)]
    horiz = [d for d in dirs if not _vertical(d)]
    if len(vert) > 1 or len(horiz) > 1:  # both directions resolve the same way: draw in listed order
        vert, horiz = dirs[:1], dirs[1:2]
    v = vert[0] if vert else None
    h = horiz[0] if horiz else None
    vp = _cumulative(v["spacings"]) if v else []
    hp = _cumulative(h["spacings"]) if h else []
    left, top, aw, ah, r = 150.0, 190.0, 660.0, 420.0, 15.0
    ext_x, ext_y = (vp[-1] if vp else 0.0), (hp[-1] if hp else 0.0)
    scales = [aw / ext_x] if ext_x > 0 else []
    scales += [ah / ext_y] if ext_y > 0 else []
    scale = min(scales) if scales else 1.0
    used_w = ext_x * scale if v else aw
    used_h = ext_y * scale if h else ah
    x0, y0 = left, top + used_h  # y0: the first horizontal line (positions grow upwards)

    footer = _footer(system, v, h)
    v_texts = [fmt_number(float(x)) for x in v["spacings"]] if v else []
    v_mid = [(a + b) / 2 * scale for a, b in pairwise(vp)]
    v_rows = _stagger(v_mid, [label_width(t) for t in v_texts])
    extra_h = ROW_STEP * (max(v_rows, default=0))  # staggered rows push the footer down
    h_texts = [fmt_number(float(x)) for x in h["spacings"]] if h else []
    h_mid = [(a + b) / 2 * scale for a, b in pairwise(hp)]
    h_cols = _stagger(h_mid, [float(SPACING_FONT)] * len(h_texts))  # labels are one line high
    col_w = max((label_width(t) for t in h_texts), default=0.0) + LABEL_GAP * 2
    width = max(1000, int(left + used_w + 20 + 28 + 10 + col_w * (max(h_cols, default=0) + 1) + 20))
    height = int(top + used_h + 90 + extra_h + 20 * len(footer) + 20)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>',
        f'<rect x="0" y="0" width="{width}" height="46" fill="#b00020"/>',
        _t(width / 2, 30, BANNER, 20, "middle", "bold", "#ffffff"),
        _t(
            20,
            74,
            f"Grid system {system['system_id']} — confidence {system['confidence']}",
            16,
            weight="bold",
        ),
        _t(20, 96, "flags: " + (", ".join(system["flags"]) or "none"), 12),
    ]
    dash = 'stroke="#1f4e9c" stroke-width="1.2" stroke-dasharray="14 4 2 4"'
    if v:
        y_a, y_b = top - 20.0, top + used_h + 20.0
        for p, lbl in zip(vp, v["labels"], strict=True):
            x = x0 + p * scale
            parts.append(f'<line x1="{x:.2f}" y1="{y_a:.2f}" x2="{x:.2f}" y2="{y_b:.2f}" {dash}/>')
            parts.append(
                f'<circle cx="{x:.2f}" cy="{y_a - r:.2f}" r="{r:.2f}" fill="#ffffff" stroke="#111"/>'
            )
            parts.append(_t(x, y_a - r + 4.5, lbl, 12, "middle"))
        yd = y_b + 28.0
        parts.append(
            f'<line x1="{x0:.2f}" y1="{yd:.2f}" x2="{x0 + ext_x * scale:.2f}" y2="{yd:.2f}" stroke="#444"/>'
        )
        for p in vp:
            x = x0 + p * scale
            parts.append(
                f'<line x1="{x:.2f}" y1="{yd - 5:.2f}" x2="{x:.2f}" y2="{yd + 5:.2f}" stroke="#444"/>'
            )
        for mid, text, row in zip(v_mid, v_texts, v_rows, strict=True):
            parts.append(_t(x0 + mid, yd + 18 + row * ROW_STEP, text, SPACING_FONT, "middle", cls="spacing"))
    if h:
        x_a, x_b = left - 20.0, left + used_w + 20.0
        for p, lbl in zip(hp, h["labels"], strict=True):
            y = y0 - p * scale
            parts.append(f'<line x1="{x_a:.2f}" y1="{y:.2f}" x2="{x_b:.2f}" y2="{y:.2f}" {dash}/>')
            parts.append(
                f'<circle cx="{x_a - r:.2f}" cy="{y:.2f}" r="{r:.2f}" fill="#ffffff" stroke="#111"/>'
            )
            parts.append(_t(x_a - r, y + 4.5, lbl, 12, "middle"))
        xd = x_b + 28.0
        parts.append(
            f'<line x1="{xd:.2f}" y1="{y0:.2f}" x2="{xd:.2f}" y2="{y0 - ext_y * scale:.2f}" stroke="#444"/>'
        )
        for p in hp:
            y = y0 - p * scale
            parts.append(
                f'<line x1="{xd - 5:.2f}" y1="{y:.2f}" x2="{xd + 5:.2f}" y2="{y:.2f}" stroke="#444"/>'
            )
        for mid, text, col in zip(h_mid, h_texts, h_cols, strict=True):
            parts.append(_t(xd + 10 + col * col_w, y0 - mid + 4, text, SPACING_FONT, cls="spacing"))
    y = top + used_h + 90.0 + extra_h
    for line in footer:
        parts.append(_t(20, y, line, 12))
        y += 20.0
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _footer(system: dict[str, Any], v: dict[str, Any] | None, h: dict[str, Any] | None) -> list[str]:
    units = system["units"]
    lines = []
    for name, d in (("vertical lines", v), ("horizontal lines", h)):
        if d is None:
            continue
        axis = d.get("tekla_axis") or "not assigned"
        lines.append(f"{name}: labels {' '.join(d['labels'])}   (Tekla axis: {axis})")
        lines.append(f"  coordinates {d['coordinates']}   [drawing units, declared {d['unit']}]")
        mm = d.get("mm")
        lines.append(
            f"  mm: {mm['coordinates']}"
            if mm
            else f"  mm: not available ({units.get('reason') or 'units not confirmed'})"
        )
    ev = system["evidence"]
    lines.append(
        f"evidence: {ev['views']} view(s) ({ev['full_views']} full, {ev['partial_views']} partial), "
        f"{ev['independent_views']} independent, {ev['sheets']} sheet(s), {ev['files']} file(s)"
    )
    lines.append(
        "Spacings are not averaged; positions are drawn to scale from the first axis of each direction."
    )
    return lines
