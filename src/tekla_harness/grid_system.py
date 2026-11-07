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
   reason. The declared header unit is never used to convert.
7. Tekla X/Y: only from active `grid_family_axis_assignment` answers ({"<family_id>": "X"|"Y"}, bound
   to the answer's `file`; family ids restart in every file) that cover every direction of the system
   without contradiction; otherwise null.
8. Confidence is never above 'medium' (gate 1 decides).

`render_grid_system_svg(system)` draws one system (axes, bubbles, labels, spacing dimensions,
coordinate strings, units, the PROPOSAL banner) as plain SVG text; spacing labels that would overlap their
neighbour (estimated width 0.6 x font size x characters) are staggered onto further rows. With `write=True`
the SVGs go to `structure/grid-systems/<system_id>.svg` (the folder is cleared first; read-structure clears
`structure/` when it reruns).

`run_grid_systems(work_dir, svg=True)` is `harness grid-system`: it reads `answers.json` through the
question ledger (active answers only), builds and validates the document, registers its questions as
producer `grid-system` (`grid_system_questions`: one per (code, blocking flag, file); the project-level
`grid_system_select` has file null and one ref per system), then writes the registry and answers, then
`grid-systems.json`, `grid-system-questions.json` and the SVGs (cleared and rewritten, or only cleared
with `svg=False`, so no `svg` path points at an old drawing).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections import Counter
from dataclasses import dataclass, field
from itertools import pairwise, permutations
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from tekla_harness.grids import (
    DRAFTING_TOL,
    FAMILY_ANGLE_TOL,
    coordinate_string,
    fmt_number,
    rounding_step,
)
from tekla_harness.questions import (
    AXIS_CODE,
    SELECT_CODE,
    UNIT_CODES,
    QuestionsError,
    dump_json,
    load_ledger,
    merged_question,
    question_group,
    questions_document,
    write_text_atomic,
)
from tekla_harness.schemas import validate
from tekla_harness.sheets import listed, min_conf, rnum

SCHEMA_VERSION = "0.1"
STRUCTURE_DIR = "structure"
GRID_SYSTEMS_DIR = "structure/grid-systems"
MAX_CONFIDENCE = "medium"  # 'high' is reserved for the engineer's confirmation at gate 1
MAX_QUESTIONS_PER_CODE = 100
BANNER = "PROPOSAL — not confirmed (gate 1)"
UNIT_TO_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "ft": 304.8}
EXIT_OK, EXIT_INVALID, EXIT_USAGE, EXIT_ENV = 0, 1, 2, 3

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
    root = work.resolve()
    for row in sorted(inventory["files"], key=lambda r: r["path"]):
        if row["format"] not in ("dwg", "dxf"):
            continue
        rel = row["path"]
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
        )
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
    return _Inputs(inventory["project_id"], inventory_sha, files, ctxs, views, unassigned, totals, warnings)


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


def _clusters(views: list[_View]) -> list[list[_Member]]:
    ordered = sorted(views, key=lambda v: (not v.complete, v.file, v.group_id, v.fams[0].family_id))
    clusters: list[list[_Member]] = []
    for v in ordered:
        for members in clusters:
            rep = members[0].view
            if len(v.fams) != len(rep.fams):
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


def _system_conflict(a: _System, b: _System) -> tuple[_Fam, _Fam, list[str]] | None:
    """First conflicting pair of full-member families (representatives first), with every difference of
    that member pair; None when the systems never disagree on a shared label pair."""
    for ma in a.full():
        for mb in b.full():
            found: list[str] = []
            first: tuple[_Fam, _Fam] | None = None
            for fa in ma.view.fams:
                for fb in mb.view.fams:
                    c = _compare(fa, fb)
                    if c.relation == "conflict":
                        first = first or (fa, fb)
                        found.extend(c.diffs)
            if first is not None:
                return first[0], first[1], found
    return None


def _related(a: _System, b: _System) -> bool:
    return any(_compare(fa, fb).relation != "disjoint" for fa in a.rep.fams for fb in b.rep.fams)


def _systems(clusters: list[list[_Member]], ctx: dict[str, _FileCtx]) -> list[_System]:
    def rank(members: list[_Member]) -> tuple[Any, ...]:
        rep = members[0].view
        indep = len(set(_components([m.view for m in members], ctx)))
        return (-len(rep.fams), -indep, -len(members), -rep.axes, rep.file, rep.group_id)

    systems: list[_System] = []
    for cluster in sorted(clusters, key=rank):
        fits = [(i, d) for i, s in enumerate(systems) if (d := _fits_system(cluster, s)) is not None]
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


def consumed_answers_digest(answers: list[dict[str, Any]] | None) -> str:
    """sha256 over the active answers this module reads (units and axis assignment): code, file, key, values.
    `harness status` compares it with the current answers.json to see whether grid-systems.json is stale."""
    rows = sorted(
        (
            str(a.get("code")),
            str(a.get("file")),
            str(a.get("key")),
            json.dumps(a.get("values"), sort_keys=True),
        )
        for a in _active(answers)
        if a.get("code") in UNIT_CODES or a.get("code") == AXIS_CODE
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
    ) -> None:
        self.counts[code] += 1
        if self.counts[code] > MAX_QUESTIONS_PER_CODE:
            return
        q: dict[str, Any] = {
            "code": code,
            "blocking": True,
            "message": message,
            "where": where,
            "found": found,
        }
        if file is not None:
            q["file"] = file
        if sheet is not None:
            q["sheet"] = sheet
        self.questions.append(q)


def _where(sid: str, f: _Fam) -> str:
    return f"{sid} ({f.file}, sheet {f.sheet}, {f.group_id}/{f.family_id})"


def _mm(spacings: list[float], factor: float) -> dict[str, Any]:
    values = [rnum(v * factor) for v in spacings]
    return {"spacings": values, "coordinates": coordinate_string(values)}


def _system_json(
    sid: str,
    s: _System,
    ctx: dict[str, _FileCtx],
    units: dict[str, tuple[str, str | None]],
    axes: dict[tuple[str, str], set[str]],
) -> dict[str, Any]:
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

    # units: every contributing file needs its own agreeing answer; files of one system may answer different
    # units (they were merged in millimetres) and the representative's file converts its drawing values
    statuses = [units[f] for f in files]
    reason: str | None = None
    if any(st == "disagree" for st, _ in statuses):
        reason = "units answers disagree"
    elif any(st == "invalid" for st, _ in statuses):
        reason = "units answer invalid"
    elif any(st == "not_answered" for st, _ in statuses):
        reason = "units not confirmed"
    unit_answer = units[rep.file][1] if reason is None else None
    factor = UNIT_TO_MM[unit_answer] if unit_answer is not None else None
    if factor is None:
        flags.add("units_not_confirmed")
    elif len({u for _, u in statuses}) > 1:
        flags.add("answered_units_differ")

    # axis assignment: every contributing family of a direction must agree
    per_dir: list[set[str]] = []
    for d in range(len(rep.fams)):
        got: set[str] = set()
        for m in s.members:
            f = s.family_of(m, d)
            if f is not None:
                got |= axes.get((f.file, f.family_id), set())
        per_dir.append(got)
    if any(len(g) > 1 for g in per_dir) or (
        len(per_dir) == 2 and all(len(g) == 1 for g in per_dir) and per_dir[0] == per_dir[1]
    ):
        axis_status, axis_reason = "contradictory", "axis answers contradict each other for this system"
    elif any(not g for g in per_dir):
        axis_status, axis_reason = "not_answered", "no axis answer covers every direction"
    else:
        axis_status, axis_reason = "answered", None
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

    tekla_grid: dict[str, Any] | None = None
    if factor is not None and axis_status == "answered":
        tekla_grid = {"unit": "mm"}
        for axis in ("x", "y"):
            dj = next((x for x in directions if x["tekla_axis"] == axis.upper()), None)
            tekla_grid[f"coordinate_{axis}"] = dj["mm"]["coordinates"] if dj else None
            tekla_grid[f"label_{axis}"] = " ".join(dj["labels"]) if dj else None

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
        "units": {
            "declared": declared,
            "answered": unit_answer,
            "status": "confirmed" if factor is not None else "not_confirmed",
            "reason": reason,
        },
        "axis_assignment": {"status": axis_status, "reason": axis_reason},
        "tekla_grid": tekla_grid,
        "svg": f"{GRID_SYSTEMS_DIR}/{sid}.svg",
        "note": "Proposal only: drawing-unit spacings of the representative family (never averaged). "
        "Confirm the system, its building, units and Tekla X/Y at gate 1.",
    }


def build_grid_systems(
    work_dir: str | Path, *, answers: list[dict[str, Any]] | None = None, write: bool = False
) -> dict[str, Any]:
    """Grid systems of a read-structure work folder. Raises GridSystemError. See the module docstring."""
    work = Path(work_dir)
    inputs = _load_inputs(work)
    warnings = list(inputs.warnings)
    active = _active(answers)
    file_paths = [f["path"] for f in inputs.files if f["status"] == "read"]
    units = units_by_file(active, file_paths, warnings)
    axes = _axis_answers(active, warnings)
    for f in inputs.files:
        st = units.get(f["path"])
        f["units_answer"] = None if st is None else {"status": st[0], "unit": st[1]}

    for v in inputs.views:  # an agreeing units answer lets the matching compare this file in millimetres
        for f in v.fams:
            status, unit = units[f.file]
            if status == "answered" and unit is not None:
                f.factor = UNIT_TO_MM[unit]
    systems = _systems(_clusters(inputs.views), inputs.ctx)
    ids = [f"S{k:03d}" for k in range(1, len(systems) + 1)]
    docs = [_system_json(sid, s, inputs.ctx, units, axes) for sid, s in zip(ids, systems, strict=True)]

    used = {(m.view.file, f.family_id) for s in systems for m in s.members for f in m.view.fams}
    for file, fid in sorted(set(axes) - used):
        warnings.append(f"axis answer for {file} {fid} matches no family of any grid system")

    ask = _Ask()
    clashes: list[tuple[str, str, str, str]] = []
    for i in range(len(systems)):
        for j in range(i + 1, len(systems)):
            hit = _system_conflict(systems[i], systems[j])
            if hit is not None:
                docs[i]["relations"]["conflicts_with"].append(ids[j])
                docs[j]["relations"]["conflicts_with"].append(ids[i])
                fa, fb, diffs = hit
                where = f"{_where(ids[i], fa)} vs {_where(ids[j], fb)}"
                clashes.append((where, "; ".join(diffs[:20]), fa.file, fa.sheet))
            elif _related(systems[i], systems[j]):
                docs[i]["relations"]["compatible_with"].append(ids[j])
                docs[j]["relations"]["compatible_with"].append(ids[i])
    for k, s in enumerate(systems):
        docs[k]["relations"]["subset_of"] = [ids[i] for i in s.subset_of]
        if docs[k]["relations"]["conflicts_with"]:
            docs[k]["flags"] = sorted({*docs[k]["flags"], "conflict"})

    if docs:
        ask(
            "grid_system_select",
            "Gate 1: which of these grid systems are the project's grids, and which building or structure is "
            "each? None is used until confirmed.",
            listed(ids),
            "; ".join(_system_found(d) for d in docs[:20]),
        )
    else:
        warnings.append(
            "no grid system: no view has a usable grid family (see the grids documents' questions)"
        )
    for where, found, file, sheet in clashes:
        ask(
            "grid_system_conflict",
            "Two grid systems use the same axis labels with different spacings or order, so they are kept "
            "apart. Are they different buildings or structures, or is one of them wrong?",
            where,
            found,
            file,
            sheet,
        )
    for d, s in zip(docs, systems, strict=True):
        rf = s.rep.fams[0]
        if d["units"]["status"] != "confirmed":
            ask(
                "grid_system_units_unconfirmed",
                "This grid system is in drawing units and no agreeing units answer covers every file it "
                "comes from. What unit are the drawing coordinates in?",
                d["system_id"],
                f"{d['units']['reason']}; "
                + "; ".join(
                    f"{f}: declared {inputs.ctx[f].declared}, answer {units[f][0]}"
                    for f in sorted({m.view.file for m in s.members})[:20]
                ),
                rf.file,
                rf.sheet,
            )
        if d["axis_assignment"]["status"] != "answered":
            ask(
                "grid_system_axis_unassigned",
                "Which direction of this grid system is Tekla X (lines parallel to Y) and which is Y?",
                d["system_id"],
                f"{d['axis_assignment']['reason']}; "
                + "; ".join(
                    f"{x['representative']['group_id']}/{x['representative']['family_id']}: labels "
                    f"{' '.join(x['labels'])}, angle {fmt_number(x['angle_deg'])} deg"
                    for x in d["directions"]
                ),
                rf.file,
                rf.sheet,
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


def grid_system_questions(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Raw questions (no id, key or answer yet) of a grid-systems document: one per (code, blocking flag,
    file), blocking first, then code, then file. `grid_system_select` is a question about the whole project
    (file null) with one ref per system; its ref carries the representative's file and sheet."""
    out: list[dict[str, Any]] = []
    groups: dict[tuple[str, bool, str], list[tuple[str, dict[str, Any]]]] = {}
    for q in doc["questions"]:
        if q["code"] == SELECT_CODE:
            refs = []
            for d in doc["systems"]:
                rep = d["directions"][0]["representative"]
                refs.append(
                    {
                        "file": rep["file"],
                        "where": d["system_id"],
                        "found": _system_found(d),
                        "sheet": rep["sheet"],
                    }
                )
            out.append(question_group(SELECT_CODE, q["blocking"], q["message"], refs, file=None))
            continue
        ref = {"file": q["file"], "where": q["where"], "found": q["found"]}
        if "sheet" in q:
            ref["sheet"] = q["sheet"]
        groups.setdefault((q["code"], q["blocking"], q["file"]), []).append((q["message"], ref))
    out += [merged_question(code, blocking, file, items) for (code, blocking, file), items in groups.items()]
    return sorted(out, key=lambda q: (not q["blocking"], q["code"], q["file"] or ""))


@dataclass
class GridSystemsResult:
    exit_code: int
    summary: dict[str, Any]


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
    doc = build_grid_systems(work, answers=ledger.answers["answers"])
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
    try:
        questions = ledger.sync("grid-system", grid_system_questions(doc), hashes)
    except QuestionsError as exc:
        raise GridSystemError(exc.exit_code, str(exc)) from exc
    qdoc = questions_document(doc["project_id"], questions)
    problems = validate("intake", qdoc)
    if problems:
        details = "; ".join(f"{p.path or '/'}: {p.message}" for p in problems[:5])
        raise GridSystemError(
            EXIT_INVALID, f"grid-system-questions.json would be invalid, nothing written: {details}"
        )
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
        **qdoc["summary"],
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
