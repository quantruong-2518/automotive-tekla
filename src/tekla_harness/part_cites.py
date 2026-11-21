"""part_cites: the citation checks (`cite_*`, `entry_*`) of `harness part check`.

A row of `values.json` may cite only records that exist, are active, are fresh and belong to the part or one
of its inputs, and text that is printed, readable and inside the part's scope (ADR-0019, E5a). Only the row's
`cites` are read here; the ids inside `hand_sum` terms are checked by `part_sums`.

Codes: `cite_unknown` (no such finding, question, entry of the row's `file`, saved file or saved item, or
grid system of grid-systems.json),
`cite_inactive` (a finding withdrawn, a question obsolete), `cite_stale` (the finding is stale in
`findings.list_findings`), `cite_foreign_part` (a reader finding or reader question held by neither the part
nor an input; untagged ones count as foreign; producer questions always pass; a grid system in no
`grid_system_ids` of the block of the part or of an input, when one of them has a block), `entry_blocked`
(`text_gate.meaning_block_reason`), `entry_not_printed` (`visibility.is_printed`), `entry_outside_part` (in no
`text_ids` of a scope sheet and no `entry_ids` of a scope cluster).
"""

from __future__ import annotations

from typing import Any

from tekla_harness.findings import _document_items
from tekla_harness.part_values import PartContext, Problem

READER = "reader"


def _held(ctx: PartContext) -> set[str]:
    """The parts whose records a row may cite: the part itself and its inputs."""
    return {ctx.part, *ctx.part_row.get("inputs", [])}


def _finding_problems(ctx: PartContext, rid: str, fid: str, held: set[str]) -> list[Problem]:
    finding = ctx.findings.get(fid)
    if finding is None:
        return [Problem("cite_unknown", rid, fid, f"{fid} is not in reader-findings.json")]
    problems: list[Problem] = []
    if finding["status"] != "active":
        reason = finding.get("withdrawn_reason", "no reason")
        problems.append(Problem("cite_inactive", rid, fid, f"{fid} was withdrawn ({reason})"))
    if finding["stale"]:
        reasons = "; ".join(r["detail"] for r in finding.get("stale_reasons", [])) or "stale"
        problems.append(Problem("cite_stale", rid, fid, f"{fid} is stale: {reasons}"))
    if finding.get("part") not in held:
        tag = finding.get("part") or "no part"
        problems.append(
            Problem("cite_foreign_part", rid, fid, f"{fid} belongs to {tag}, not {ctx.part} or an input")
        )
    return problems


def _question_problems(ctx: PartContext, rid: str, qid: str, held: set[str]) -> list[Problem]:
    entry = ctx.registry.get(qid)
    if entry is None:
        return [Problem("cite_unknown", rid, qid, f"{qid} is not in question-registry.json")]
    problems: list[Problem] = []
    inactive = entry["status"] == "obsolete"
    if inactive:
        reason = entry.get("withdrawn_reason") or entry.get("obsolete_reason") or "no reason"
        problems.append(Problem("cite_inactive", rid, qid, f"{qid} is obsolete ({reason})"))
    if entry["producer"] == READER:
        asked = ctx.questions.get(qid)
        if asked is None and inactive:
            return problems  # a withdrawn reader question leaves reader-questions.json: not also foreign
        parts = asked.get("parts", []) if asked is not None else []
        if not held & set(parts):
            tag = ", ".join(parts) or "no part"
            problems.append(
                Problem("cite_foreign_part", rid, qid, f"{qid} belongs to {tag}, not {ctx.part} or an input")
            )
    return problems


def _in_scope(ctx: PartContext, file: str, tid: str) -> bool:
    if any(tid in ctx.sheet_entries.get(key, ()) for key in ctx.scope.sheets if key[0] == file):
        return True
    return any(tid in ctx.cluster_entries.get(key, ()) for key in ctx.scope.clusters if key[0] == file)


def _entry_problems(ctx: PartContext, rid: str, file: str | None, tid: str) -> list[Problem]:
    entry = ctx.entries.get((file, tid)) if file is not None else None
    if entry is None:
        where = f"an entry of {file}" if file is not None else "an entry of a file (the row has none)"
        return [Problem("cite_unknown", rid, tid, f"{tid} is not {where}")]
    _, allowed, printed, _ = entry
    problems: list[Problem] = []
    if not allowed:
        problems.append(
            Problem("entry_blocked", rid, tid, f"{tid}: its meaning is blocked, quote it in a question")
        )
    if not printed:
        problems.append(
            Problem("entry_not_printed", rid, tid, f"{tid} is not printed: quote it in a question")
        )
    if not _in_scope(ctx, file, tid):  # type: ignore[arg-type]
        problems.append(
            Problem(
                "entry_outside_part", rid, tid, f"{tid} is in no sheet or cluster of {ctx.part} or its inputs"
            )
        )
    return problems


def _geometry_problems(ctx: PartContext, rid: str, geometry: dict[str, Any]) -> list[Problem]:
    source = geometry["source"]
    doc = ctx.saved.get(source)
    known = _document_items(doc) if doc is not None else {}
    problems: list[Problem] = []
    for item in geometry["items"]:
        if doc is None:
            problems.append(Problem("cite_unknown", rid, item, f"{item}: {source} is not a saved document"))
        elif item not in known:
            problems.append(Problem("cite_unknown", rid, item, f"{item} is not an item of {source}"))
    return problems


def _grid_system_problems(ctx: PartContext, rid: str, sid: str, allowed: set[str] | None) -> list[Problem]:
    if sid not in ctx.grid_systems:
        return [Problem("cite_unknown", rid, sid, f"{sid} is not a system of grid-systems.json")]
    if allowed is not None and sid not in allowed:
        return [
            Problem(
                "cite_foreign_part",
                rid,
                sid,
                f"{sid} is in no block of {ctx.part} or its inputs (their grid_system_ids: "
                f"{', '.join(sorted(allowed)) or 'none'})",
            )
        ]
    return []


def _block_systems(ctx: PartContext) -> set[str] | None:
    """The grid systems of the blocks of the part and its inputs; None when none of them has a block."""
    by_id = {p["id"]: p for p in ctx.manifest["parts"]}
    blocks = {
        by_id[part]["block"] for part in _held(ctx) if part in by_id and by_id[part].get("block") is not None
    }
    if not blocks:
        return None
    return {
        sid for block in ctx.manifest["blocks"] if block["id"] in blocks for sid in block["grid_system_ids"]
    }


def cite_problems(ctx: PartContext) -> list[Problem]:
    """The citation problems of every row."""
    held = _held(ctx)
    allowed = _block_systems(ctx)
    problems: list[Problem] = []
    for r in ctx.rows:
        rid, cites = r["row"], r.get("cites", {})
        for fid in cites.get("findings", []):
            problems += _finding_problems(ctx, rid, fid, held)
        for qid in cites.get("questions", []):
            problems += _question_problems(ctx, rid, qid, held)
        for tid in cites.get("entries", []):
            problems += _entry_problems(ctx, rid, r.get("file"), tid)
        if "geometry" in cites:
            problems += _geometry_problems(ctx, rid, cites["geometry"])
        for sid in cites.get("grid_systems", []):
            problems += _grid_system_problems(ctx, rid, sid, allowed)
    return problems
