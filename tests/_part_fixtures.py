"""A real intake work folder, a parts manifest, findings and questions for the `harness part check` tests.

`build_part_work` takes `_dxf_fixtures.build_set` (two framed model sheets) and adds invented texts: on
`model#01` the marks K-1, K-2 and the texts '1500x2400', 'D400'; on `model#02` the mark P-1, the text '26'
and '-1.200'. It runs the real `run_intake` and writes the real sheets document. The inventory path of the
drawing is `plans/set.dxf`.

`part_manifest(work)` is a valid manifest of one block with the parts B1-caps (the part under test: sheet
`model#01` with a heading view, a cluster outside every frame), B1-piles (its input, sheet `model#02`) and
the fixed parts. `record_records(work)` records, with `--part`, two findings and two questions of B1-caps and
one question of B1-piles. `write_values`, `run_check`, `row` and `entry_row` are the helpers every part-check
test file uses; a test that expects a clean result builds rows that every check accepts (what a row cites
exists and backs its value). The others (`put_manifest`, `entry_ids`) build the work folder.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ezdxf.filemanagement import readfile

from _callout_fixtures import REL, write_structure
from _dxf_fixtures import build_set
from tekla_harness.ask import ask_question
from tekla_harness.cli import main
from tekla_harness.findings import add_finding
from tekla_harness.intake import run_intake
from tekla_harness.knowledge import EMPTY_TABLE

PROJECT = "demo-part-check"
PART = "B1-caps"
INPUT_PART = "B1-piles"
MANIFEST = Path("parts") / "manifest.json"
# text -> (x, y): sheet 1 is the frame at x 0..84100, sheet 2 at x 90000..
TEXTS = {
    "K-1": (62000, 57000),
    "1500x2400": (62000, 56500),
    "K-2": (62000, 56000),
    "D400": (62000, 55500),
    "P-1": (100000, 50000),
    "26": (100000, 49500),
    "-1.200": (100000, 49000),
}


def build_part_work(base: Path) -> Path:
    """Build `base/input` and `base/work` (intake + the sheets document); returns the work folder, with the
    manifest and the records of `part_manifest` / `record_records` already in place."""
    root = base / "input"
    (root / "plans").mkdir(parents=True)
    doc = readfile(str(build_set(base, "src.dxf")))
    msp = doc.modelspace()
    for text, at in TEXTS.items():
        msp.add_text(text, height=350, dxfattribs={"insert": at})
    doc.saveas(root / REL)
    work = base / "work"
    run_intake(root, work, PROJECT, knowledge=EMPTY_TABLE)
    write_structure(root, work)
    put_manifest(work, part_manifest(work))
    record_records(work)
    return work


def entry_ids(work: Path) -> dict[str, str]:
    """display text -> entry id of the drawing's text index."""
    index = json.loads((work / "text" / f"{REL}.json").read_text(encoding="utf-8"))
    return {e["display_text"]: e["id"] for e in index["entries"]}


def part_manifest(work: Path) -> dict[str, Any]:
    ids = entry_ids(work)

    def sheet(n: int, role: str = "plan", **more: Any) -> dict[str, Any]:
        return {"file": REL, "sheet": f"model#{n:02d}", "role": role, **more}

    return {
        "schema_version": "0.1",
        "blocks": [{"id": "B1", "grid_system_ids": [], "origin_note": "Block B1: its own grid"}],
        "parts": [
            {"id": "scout", "kind": "bookkeeping", "order": 0},
            {
                "id": INPUT_PART,
                "kind": "member",
                "block": "B1",
                "family": "piles",
                "order": 1,
                "sheets": [sheet(2)],
            },
            {
                "id": PART,
                "kind": "member",
                "block": "B1",
                "family": "caps",
                "order": 2,
                "inputs": [INPUT_PART],
                "sheets": [sheet(1, views=[{"heading_entry": ids["K-1"]}, {"bbox": [0, 0, 1000, 500]}])],
                "clusters": [{"file": REL, "sheet": None, "side": "none"}],
            },
            {"id": "all-assembly", "kind": "bookkeeping", "order": 3, "inputs": [PART]},
        ],
    }


def put_manifest(work: Path, manifest: dict[str, Any] | str | None) -> None:
    path = work / MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    if manifest is None:
        path.unlink(missing_ok=True)
    else:
        path.write_text(manifest if isinstance(manifest, str) else json.dumps(manifest), encoding="utf-8")


def record_records(work: Path) -> None:
    """F-001 (note_item) and F-002 (sheet_class) of B1-caps; Q-003 and Q-004 of B1-caps and Q-005 of B1-piles
    (the questions Q-001 and Q-002 are intake's)."""
    ids = entry_ids(work)
    add_finding(
        work, kind="note_item", file=REL, entries=[ids["1500x2400"]], value="1500x2400", sheet="model#01",
        fields=["topic=other"], part=PART, note="block: cap size as printed",
    )  # fmt: skip
    add_finding(
        work, kind="sheet_class", file=REL, entries=[ids["K-1"]], value="foundation", sheet="model#01",
        part=PART, note="node: sheet class; basis: single_source; alt: none",
    )  # fmt: skip
    for code, where, part in (
        ("reader_size_unclear", "model#01 K-1", PART),
        ("reader_level_unclear", "model#01 K-2", PART),
        ("reader_pile_count_unclear", "model#02 P-1", INPUT_PART),
    ):
        ask_question(
            work, code=code, where=where, found="a value", text="Giá trị nào?", file=REL, sheet=where[:8],
            blocking=True, part=part,
        )  # fmt: skip


def row(row_id: str = "R001", **fields: Any) -> dict[str, Any]:
    """A valid `seen` row of K-1 on model#01 citing F-001 (1500x2400); `fields` override or add keys
    (a value of the string '<drop>' removes the key). Unless `cites` names `questions`, a `seen` row also
    cites the blocking question Q-003: a listed value on one source key needs one (`listed_needs_blocking`).
    """
    out: dict[str, Any] = {
        "row": row_id, "mark": "K-1", "field": "size", "value": "1500x2400", "file": REL,
        "sheet": "model#01", "state": "seen", "cites": {"findings": ["F-001"]},
    }  # fmt: skip
    for key, value in fields.items():
        if value == "<drop>":
            out.pop(key, None)
        else:
            out[key] = value
    if out["state"] == "seen" and isinstance(out.get("cites"), dict):  # a listed value on one source key
        out["cites"] = {"questions": ["Q-003"], **out["cites"]}
    return out


def entry_row(work: Path, row_id: str, field: str, text: str, **fields: Any) -> dict[str, Any]:
    """A valid `seen` row whose value is the text of the entry it cites (`text` is a text of the drawing's
    index), so the number and token checks find it in the cited source; `fields` override as in `row`."""
    return row(row_id, field=field, value=text, cites={"entries": [entry_ids(work)[text]]}, **fields)


def write_values(
    work: Path, rows: list[dict[str, Any]] | str | None, part: str = PART, *, doc_part: str | None = None
) -> Path:
    """Write `parts/<part>/values.json`: a document of `rows`, raw text, or (None) no file. `doc_part`: the
    `part` inside the document when it is not the folder's."""
    path = work / "parts" / part / "values.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if rows is None:
        path.unlink(missing_ok=True)
    elif isinstance(rows, str):
        path.write_text(rows, encoding="utf-8")
    else:
        doc = {"schema_version": "0.1", "part": doc_part or part, "rows": rows}
        path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def run_check(capsys: Any, work: Path, part: str = PART) -> tuple[int, dict[str, Any] | None, str]:
    """Run `harness part check` and return (exit code, the parsed stdout or None when empty, stderr)."""
    code = main(["part", "check", str(work), "--part", part])
    cap = capsys.readouterr()
    return code, (json.loads(cap.out) if cap.out else None), cap.err


def problems(doc: dict[str, Any] | None) -> list[tuple[str, str | None, str | None]]:
    assert doc is not None
    return [(p["code"], p["row"], p["id"]) for p in doc["problems"]]
