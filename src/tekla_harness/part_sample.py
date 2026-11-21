"""`harness part chain`, `harness part review-sample` (E7), the seeded sampler `stratified`.

Both actions are read-only. `chain` gives the assembler, per member part of a block in load-path order, its
count rows with their numbers and hand-sum addends, the products `count_plan x piles_per_member` per mark and
two sums; it compares nothing. `review-sample` gives the part reviewer blind prompts: each names the place
(the sheet number, else the sheet id and the file; the view) and asks for one value, and holds neither the
value nor a cite nor an entry id (a fixed English template per kind, filled with a fixed phrase for the field
and the mark or subject). A sheet number, view or mark or subject that gives the row's value away is left out.

Exit codes: 0 ok, 1 the manifest, the block, a part or its `values.json` is unusable, 2 usage (the work folder
or the part id), 3 the operating system refused a file. Stdout is the `chain` or `review_sample` definition of
`part-output`.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections.abc import Callable
from typing import Any

from tekla_harness.findings import _numbers
from tekla_harness.part_rules import LISTED
from tekla_harness.part_sums import hand_sum_addends
from tekla_harness.part_values import ContextStop, PartContext, Problem, load_context
from tekla_harness.parts import ManifestAccessError
from tekla_harness.parts_manifest import _os_errors_are_environment, _read_manifest
from tekla_harness.schemas import _load_all, validate
from tekla_harness.sheet_text import ReaderError, load_inventory

EXIT_OK, EXIT_INVALID, EXIT_ENV = 0, 1, 3
COMMAND = "part"
CHAIN_FIELDS = ("count_plan", "count_schedule", "piles_per_member")
SMALL_POOL = 8  # a pool of this many rows or fewer is sampled whole
DEFAULT_N = 8
# One fixed template per prompt kind; `{field}` and `{who}` are the only gaps (no value, cite or entry id).
# `{who}` is " for <mark or subject>", or empty when that text would give the value away.
VALUE_PROMPT = "what {field} does the drawing give{who}? Cite the entry ids."
ABSENCE_PROMPT = "does the drawing give a {field}{who}? Answer yes or no, and cite the entry ids if yes."
OUTSIDE_PROMPT = "what {field} does the text outside the sheet frames give{who}? Cite the entry ids."
# One fixed English phrase per field of the `part-values` enum, for the `{field}` gap of the templates.
FIELD_PHRASE = {
    "size": "size",
    "thickness": "thickness",
    "depth": "depth",
    "length": "length",
    "count_plan": "number on the plan",
    "count_schedule": "number in the schedule",
    "piles_per_member": "number of piles per member",
    "level": "level",
    "level_top": "top level",
    "level_bottom": "bottom level",
    "material": "material",
    "axes": "set of axes",
    "start_axes": "set of start axes",
    "end_axes": "set of end axes",
    "spacing": "spacing",
    "other": "value",
}


def _plain(n: float) -> int | float:
    return int(n) if float(n).is_integer() else n


# --- the sampler ------------------------------------------------------------------------------------------


def _field_order() -> list[str]:
    """The LISTED fields in the order of the `field` enum of `part-values`."""
    enum = _load_all()[0]["part-values"]["$defs"]["row"]["properties"]["field"]["enum"]
    return [f for f in enum if f in LISTED]


def stratified(
    rows: list[dict[str, Any]],
    n: int,
    seed: int,
    salt: str,
    priority: Callable[[dict[str, Any]], int] | None = None,
) -> list[dict[str, Any]]:
    """A seeded sample of `rows` (dicts with `row` and `field`), by row id. A pool of `SMALL_POOL` rows or
    fewer is returned whole. Otherwise `max(n, the distinct LISTED fields of the pool)` rows: one per LISTED
    field (in enum order, a seeded choice among that field's rows of the lowest `priority(row)`; none given:
    all equal), then a seeded shuffle of the rest. The same rows, seed and salt give the same sample."""
    pool = sorted(rows, key=lambda r: r["row"])
    if len(pool) <= SMALL_POOL:
        return pool
    rng = random.Random(f"{seed}:{salt}")
    rank = priority or (lambda _row: 0)
    chosen: dict[str, dict[str, Any]] = {}
    for name in _field_order():
        of_field = [r for r in pool if r["field"] == name]
        if of_field:
            best = min(rank(r) for r in of_field)
            pick = rng.choice([r for r in of_field if rank(r) == best])
            chosen[pick["row"]] = pick
    rest = [r for r in pool if r["row"] not in chosen]
    rng.shuffle(rest)
    chosen.update((r["row"], r) for r in rest[: max(n, len(chosen)) - len(chosen)])
    return [chosen[row_id] for row_id in sorted(chosen)]


# --- chain ------------------------------------------------------------------------------------------------


def _chain_row(ctx: PartContext, row: dict[str, Any]) -> dict[str, Any]:
    value = row["value"]
    numbers = _numbers(value) if value is not None else []
    findings = {fid: f for fid, f in ctx.findings.items() if f["status"] == "active"}
    entry_text = {
        key: text for key, (text, allowed, printed, _) in ctx.entries.items() if allowed and printed
    }
    addends = hand_sum_addends(row, findings, ctx.marks, entry_text)
    return {
        "row": row["row"],
        "mark": row.get("mark"),
        "subject": row.get("subject"),
        "field": row["field"],
        "value": value,
        "number": _plain(numbers[0]) if len(numbers) == 1 else None,
        "state": row["state"],
        "addends": [{"term": term, "value": n} for term, n in addends],
    }


def _chain_part(work_dir: str, part: dict[str, Any]) -> dict[str, Any]:
    ctx = load_context(work_dir, part["id"])
    rows = [
        _chain_row(ctx, r) for r in sorted(ctx.rows, key=lambda r: r["row"]) if r["field"] in CHAIN_FIELDS
    ]
    by_mark: dict[str, dict[str, list[int | float]]] = {}
    for r in rows:
        if r["mark"] is not None and r["number"] is not None:
            by_mark.setdefault(r["mark"], {}).setdefault(r["field"], []).append(r["number"])
    # a mark counts all its count_plan rows (the rows of the sum below); it has a product only when its
    # piles_per_member rows give one distinct number
    products = [
        {
            "mark": mark,
            "count_plan": _plain(sum(f["count_plan"])),
            "piles_per_member": f["piles_per_member"][0],
            "product": _plain(sum(f["count_plan"]) * f["piles_per_member"][0]),
        }
        for mark, f in by_mark.items()
        if "count_plan" in f and len(set(f.get("piles_per_member", []))) == 1
    ]
    plans = [
        r["number"] for r in rows if r["field"] == "count_plan" and r["mark"] and r["number"] is not None
    ]
    sums = {
        "count_plan": _plain(sum(plans)) if plans else None,
        "count_x_piles": _plain(sum(p["product"] for p in products)) if products else None,
    }
    return {"part": part["id"], "order": part["order"], "rows": rows, "products": products, "sums": sums}


def _manifest(work_dir: str) -> tuple[Any, dict[str, Any]]:
    """(the resolved work folder, the manifest). Raises ContextStop when the manifest is unusable."""
    with _os_errors_are_environment():
        work = load_inventory(work_dir).work
    manifest, found = _read_manifest(work)
    if manifest is None:
        raise ContextStop([Problem("manifest_invalid", None, None, "; ".join(p[4] for p in found[:3]))])
    return work, manifest


def build_chain(work_dir: str, block: str) -> dict[str, Any]:
    """The `chain` document of block `block`. Raises ContextStop, ReaderError and ManifestAccessError."""
    work, manifest = _manifest(work_dir)
    if block not in {b["id"] for b in manifest["blocks"]}:
        raise ContextStop(
            [Problem("block_unknown", None, block, f"'{block}' is not in blocks[] of the manifest")]
        )
    members = [p for p in manifest["parts"] if p["kind"] == "member" and p.get("block") == block]
    members.sort(key=lambda p: (p["order"], p["id"]))
    return {
        "command": "chain",
        "block": block,
        "parts": [_chain_part(str(work), p) for p in members],
    }


# --- review-sample ----------------------------------------------------------------------------------------


def _entry_text(ctx: PartContext, file: str | None, entry_id: str | None) -> str | None:
    """The text of an entry a prompt may quote: readable and printed, else None (never a blocked text)."""
    entry = ctx.entries.get((file, entry_id)) if file is not None and entry_id is not None else None  # type: ignore[arg-type]
    return entry[0] if entry is not None and entry[1] and entry[2] else None


def _number_entry(ctx: PartContext, file: str | None, sheet: str | None) -> str | None:
    """`number_entry` of the manifest's listing of the sheet: the part's own first, then its input parts'."""
    by_id = {p["id"]: p for p in ctx.manifest["parts"]}
    listed = [ctx.part_row] + [by_id[i] for i in ctx.part_row.get("inputs", []) if i in by_id]
    return next(
        (
            s["number_entry"]
            for p in listed
            for s in p.get("sheets", [])
            if (s["file"], s["sheet"]) == (file, sheet) and "number_entry" in s
        ),
        None,
    )


def _gives_away(text: str, value: str | None) -> bool:
    """True when `text` (a sheet number, view heading or subject) shares a number with the row's value or
    holds the value's casefolded text: the prompt must leave it out. A row without a value gives none away."""
    if value is None:
        return False
    shown = value.strip().casefold()
    return bool(set(_numbers(text)) & set(_numbers(value))) or (bool(shown) and shown in text.casefold())


def _place(number: str | None, file: str | None, sheet: str | None, view: str | None) -> str:
    """The place the prompt starts with: the sheet number, else the sheet id and the file (the keys of the
    prompt), then the view."""
    if number:
        sheet_part = f"Sheet {number}"
    elif sheet:
        sheet_part = f"Sheet {sheet} of {file}" if file else f"Sheet {sheet}"
    else:
        sheet_part = f"File {file}" if file else ""
    return ", ".join(([sheet_part] if sheet_part else []) + ([f"view '{view}'"] if view else []))


def _prompt(ctx: PartContext, row: dict[str, Any], kind: str) -> dict[str, Any]:
    file, sheet = row.get("file"), row.get("sheet")
    value = row.get("value")

    def kept(text: str | None) -> str | None:
        return None if text is None or _gives_away(text, value) else text

    number = kept(_entry_text(ctx, file, _number_entry(ctx, file, sheet)))
    view = kept(_entry_text(ctx, file, row.get("view", {}).get("heading_entry")))
    mark, subject = row.get("mark"), row.get("subject")
    who = kept(mark or subject)
    if who is None:  # the text the prompt would name gives the value away: its key is null too
        mark, subject = (None, subject) if mark else (mark, None)
    where = _place(number, file, sheet, view)
    template = {"value": VALUE_PROMPT, "absence": ABSENCE_PROMPT, "outside_frame": OUTSIDE_PROMPT}[kind]
    body = template.format(field=FIELD_PHRASE[row["field"]], who=f" for {who}" if who else "")
    text = f"{where}: {body}" if where else f"{body[:1].upper()}{body[1:]}"
    return {
        "row": row["row"],
        "kind": kind,
        "mark": mark,
        "subject": subject,
        "field": row["field"],
        "file": file,
        "sheet": sheet,
        "sheet_number": number,
        "view": view,
        "prompt": text,
    }


def _outside_frame(ctx: PartContext, row: dict[str, Any]) -> bool:
    """True when a cited entry of the row lies in an unassigned cluster of the row's file."""
    cited = set(row.get("cites", {}).get("entries", []))
    return any(
        file == row.get("file") and cited & ids for (file, _sheet, _side), ids in ctx.cluster_entries.items()
    )


def build_review_sample(work_dir: str, part: str, seed: int, n: int | None) -> dict[str, Any]:
    """The `review_sample` document. Raises ContextStop, ReaderError and ManifestAccessError."""
    ctx = load_context(work_dir, part)
    pool = [r for r in ctx.rows if r["state"] in ("seen", "asked")]
    sampled = stratified(pool, n or DEFAULT_N, seed, f"{part}:review")
    taken = {r["row"] for r in sampled}
    prompts = [_prompt(ctx, r, "value") for r in sampled]
    absent = sorted((r for r in ctx.rows if r["state"] == "absent"), key=lambda r: r["row"])
    if absent:
        pick = random.Random(f"{seed}:{part}:absence").choice(absent)
        prompts.append(_prompt(ctx, pick, "absence"))
    outside = sorted(
        (r for r in pool if r["row"] not in taken and _outside_frame(ctx, r)), key=lambda r: r["row"]
    )
    if outside:
        pick = random.Random(f"{seed}:{part}:outside").choice(outside)
        prompts.append(_prompt(ctx, pick, "outside_frame"))
    return {"command": "review_sample", "part": part, "seed": seed, "prompts": prompts}


# --- the handlers -----------------------------------------------------------------------------------------


def _emit(action: str, build: Callable[[], dict[str, Any]]) -> int:
    """Print the document `build` returns; map its errors to the exit codes of the module."""
    try:
        doc = build()
        invalid = validate("part-output", doc)
        if invalid:
            shown = "; ".join(f"{p.path}: {p.message}" for p in invalid[:3])
            raise ReaderError(EXIT_INVALID, f"internal error: output is invalid: {shown}")
    except ContextStop as stop:
        for p in stop.problems:
            print(f"harness {COMMAND} {action}: {p.code}: {p.detail}", file=sys.stderr)
        return EXIT_INVALID
    except ReaderError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except ManifestAccessError as exc:
        print(f"harness {COMMAND} {action}: {exc}", file=sys.stderr)
        return EXIT_ENV
    except OSError as exc:
        print(f"harness {COMMAND} {action}: cannot read the work folder: {exc}", file=sys.stderr)
        return EXIT_ENV
    print(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False))
    return EXIT_OK


def run_chain(args: argparse.Namespace) -> int:
    """`harness part chain W --block B`: read-only."""
    return _emit("chain", lambda: build_chain(args.work_dir, args.block))


def run_review_sample(args: argparse.Namespace) -> int:
    """`harness part review-sample W --part X --seed S [--n N]`: read-only."""
    return _emit("review-sample", lambda: build_review_sample(args.work_dir, args.part, args.seed, args.n))
