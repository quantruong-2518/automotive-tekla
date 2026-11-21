"""`harness part spotcheck W --part X --seed S [--n N]` (E9a, C11): the sample of a locked part's `seen` rows
that the engineer checks against the drawing.

Writes `W/parts/X/spotcheck.json` (schema `answer-key`, `kind: spotcheck`: the rows, where each is read and
the part hash they were drawn at) and the form `P/spotcheck/X.md` (`P` is the folder above the work folder).
The pool is the part's `seen` rows that name a file, minus those whose key (`part_score`) is shared with a
`seen` row of a different value: `answer-key` could not record the first and the score could not tell the
second apart, so each is named on stderr (`no_file: …`, `key_ambiguous: …`) and never offered. The sample is
`part_sample.stratified` over the pool with the salt `X:spot`: one row per LISTED field, chosen among that
field's rows of the lowest priority (measured of medium confidence, other measured, the rest); the other slots
are a seeded draw. The same seed and part hash give the same two files; a file that already holds the text is
not rewritten, and neither carries a timestamp.

Exit codes: 0 written or unchanged, 1 the part is not `locked`, or the manifest, a part or its `values.json`
is unusable, 2 usage, 3 the operating system refused a file. Stdout is the `spotcheck` definition of
`part-output`. The lock is taken by `cli`.
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path
from typing import Any

from tekla_harness.part_conflicts import FIELD_NOUN_VI
from tekla_harness.part_receipts import PartStates
from tekla_harness.part_rules import _linework
from tekla_harness.part_sample import _entry_text, _manifest, stratified
from tekla_harness.part_score import ambiguous_rows
from tekla_harness.part_values import ContextStop, PartContext, Problem, load_context
from tekla_harness.parts import ManifestAccessError
from tekla_harness.questions import dump_json, write_text_atomic
from tekla_harness.schemas import validate
from tekla_harness.sheet_text import ReaderError
from tekla_harness.takeoff_cells import row_confidence

EXIT_OK, EXIT_INVALID, EXIT_ENV = 0, 1, 3
DEFAULT_N = 5
JSON_NAME, FORM_DIR = "spotcheck.json", "spotcheck"
NOT_QUOTABLE = "chữ bị chặn hoặc không in"
VERDICT_CHOICES = "ok|wrong|cannot_tell"


def _priority(ctx: PartContext, row: dict[str, Any]) -> int:
    """0: measured (cites geometry or a finding with `evidence`) whose lowest confidence is `medium`; 1: other
    measured; 2: the rest."""
    if not _linework(ctx, row):
        return 2
    try:
        confidence = row_confidence(row, ctx.findings, ctx.grid_systems)
    except KeyError as exc:
        raise ReaderError(
            EXIT_INVALID,
            f"{ctx.part} {row['row']}: cites {exc} that is not loaded (run `harness part check`)",
        ) from exc
    return 0 if confidence == "medium" else 1


def _sheet_entry(ctx: PartContext, file: str | None, sheet: str | None, key: str) -> str | None:
    """`key` (`number_entry` or `title_entry`) of the manifest's listing of the sheet: the part's own first,
    then its input parts'."""
    by_id = {p["id"]: p for p in ctx.manifest["parts"]}
    listed = [ctx.part_row] + [by_id[i] for i in ctx.part_row.get("inputs", []) if i in by_id]
    return next(
        (
            s[key]
            for p in listed
            for s in p.get("sheets", [])
            if (s["file"], s["sheet"]) == (file, sheet) and key in s
        ),
        None,
    )


def _spot_row(ctx: PartContext, row: dict[str, Any]) -> dict[str, Any]:
    file, sheet, cites = row.get("file"), row.get("sheet"), row.get("cites", {})
    who = {"mark": row["mark"]} if "mark" in row else {"subject": row["subject"]}
    return {
        "row": row["row"],
        **who,
        "field": row["field"],
        "value": row["value"],
        "file": file,
        "sheet": sheet,
        "sheet_number": _entry_text(ctx, file, _sheet_entry(ctx, file, sheet, "number_entry")),
        "sheet_title": _entry_text(ctx, file, _sheet_entry(ctx, file, sheet, "title_entry")),
        "view": _entry_text(ctx, file, row.get("view", {}).get("heading_entry")),
        "entries": list(cites.get("entries", [])),
        "findings": list(cites.get("findings", [])),
    }


def _quoted(ctx: PartContext, file: str | None, entry_id: str) -> str:
    text = _entry_text(ctx, file, entry_id)
    return f"'{text}'" if text else f"({NOT_QUOTABLE})"


def _form(ctx: PartContext, doc: dict[str, Any]) -> str:
    """The engineer's form (Vietnamese): a block per sampled row and the command that records the verdict."""
    lines = [
        f"# Kiểm tra mẫu: {doc['part']}",
        "",
        f"Phần `{doc['part']}`",
        "",
        "Mở bản vẽ ở tờ và hình ghi dưới mỗi dòng, so giá trị với bản vẽ rồi đánh dấu một ô ở dòng Kết luận.",
        "Điều phối viên ghi kết luận bằng lệnh kèm theo, theo lời kỹ sư.",
    ]
    for i, r in enumerate(doc["rows"], start=1):
        label = FIELD_NOUN_VI.get(r["field"], r["field"])
        where = ", ".join(x for x in (r["sheet_number"], r["sheet_title"], r["view"]) if x)
        if r["file"] is None:
            in_file = "chưa rõ"
        elif r["sheet"] is None:
            in_file = f"{r['file']}, ngoài khung tờ"
        else:
            in_file = f"{r['file']}, tờ {r['sheet']}"
        quotes = "; ".join(_quoted(ctx, r["file"], t) for t in r["entries"])
        command = (
            f"harness part answer-key {shlex.quote(str(ctx.work))} --part {shlex.quote(doc['part'])} "
            f'--row {r["row"]} --verdict {VERDICT_CHOICES} [--correct "<giá trị đúng>"] --by "<tên kỹ sư>"'
        )
        lines += [
            "",
            f"### {i}. {r.get('mark') or r['subject']}" + (f" — {label}" if label else ""),
            "",
            f"- Giá trị: {r['value']}",
            f"- Tờ: {where or 'chưa rõ số hiệu, tiêu đề và hình'}",
            f"- Tệp: {in_file}",
            f"- Chữ trên bản vẽ: {quotes or 'không trích dẫn chữ nào'}",
            "- Kết luận: [ ] Đúng [ ] Sai — giá trị đúng: ___ [ ] Không xem được",
            f"- Lệnh ghi: `{command}`",
        ]
    return "\n".join(lines) + "\n"


def _write_if_changed(path: Path, text: str) -> None:
    if path.is_file() and path.read_text(encoding="utf-8", errors="replace") == text:
        return
    write_text_atomic(path, text)


def _pool(ctx: PartContext, notes: list[str]) -> list[dict[str, Any]]:
    """The rows that may be sampled; `notes` gets the stderr lines for the rows left out."""
    seen = [r for r in ctx.rows if r["state"] == "seen"]
    no_file = [r["row"] for r in seen if r.get("file") is None]
    if no_file:
        notes.append(f"no_file: {', '.join(no_file)}")
    seen = [r for r in seen if r.get("file") is not None]
    ambiguous = ambiguous_rows(ctx.part, seen)
    if ambiguous:
        notes.append(f"key_ambiguous: {', '.join(ambiguous)}")
    return [r for r in seen if r["row"] not in ambiguous]


def build_spotcheck(
    work_dir: str, part: str, seed: int, n: int | None, notes: list[str] | None = None
) -> dict[str, Any]:
    """Write the two files and return the stdout document; `notes` gets the stderr lines. Raises ContextStop,
    ReaderError, ManifestAccessError and OSError."""
    work, manifest = _manifest(work_dir)
    states = PartStates(work, manifest)
    status = states.status(part)
    if status != "locked":
        raise ContextStop(
            [
                Problem(
                    "part_not_locked", None, part, f"part '{part}' is {status}, not locked: nothing to sample"
                )
            ]
        )
    ctx = load_context(work, part)
    size = n or DEFAULT_N
    pool = _pool(ctx, [] if notes is None else notes)
    sample = stratified(pool, size, seed, f"{part}:spot", lambda r: _priority(ctx, r))
    doc = {
        "schema_version": "0.1", "kind": "spotcheck", "part": part, "part_hash": states.hash(part),
        "seed": seed, "n": size, "rows": [_spot_row(ctx, r) for r in sample],
    }  # fmt: skip
    invalid = validate("answer-key", doc)
    if invalid:
        shown = "; ".join(f"{p.path}: {p.message}" for p in invalid[:3])
        raise ReaderError(EXIT_INVALID, f"internal error: spotcheck.json is invalid: {shown}")
    _write_if_changed(Path(work) / "parts" / part / JSON_NAME, dump_json(doc))
    _write_if_changed(Path(work).parent / FORM_DIR / f"{part}.md", _form(ctx, doc))
    out = {
        "command": "spotcheck", "part": part, "seed": seed, "rows": [r["row"] for r in sample],
        "written": [f"parts/{part}/{JSON_NAME}", f"../{FORM_DIR}/{part}.md"],
    }  # fmt: skip
    invalid = validate("part-output", out)
    if invalid:
        shown = "; ".join(f"{p.path}: {p.message}" for p in invalid[:3])
        raise ReaderError(EXIT_INVALID, f"internal error: output is invalid: {shown}")
    return out


def run_spotcheck(args: argparse.Namespace) -> int:
    """The handler of `harness part spotcheck` (the lock is taken by `cli`)."""
    notes: list[str] = []
    try:
        out = build_spotcheck(args.work_dir, args.part, args.seed, args.n, notes)
    except ContextStop as stop:
        for p in stop.problems:
            print(f"harness part spotcheck: {p.code}: {p.detail}", file=sys.stderr)
        return EXIT_INVALID
    except ReaderError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except ManifestAccessError as exc:
        print(f"harness part spotcheck: {exc}", file=sys.stderr)
        return EXIT_ENV
    except OSError as exc:
        print(f"harness part spotcheck: cannot read or write the work folder: {exc}", file=sys.stderr)
        return EXIT_ENV
    for line in notes:
        print(f"harness part spotcheck: {line}", file=sys.stderr)
    print(json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False))
    return EXIT_OK
