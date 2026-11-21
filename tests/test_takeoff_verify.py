"""`harness takeoff render | plan` read the status with `--verify` (E5b-4, DECISIONS § 18 D1): a part whose
`harness part check` fails never reads `dựng được`, whatever its receipts and hash say.

The work folder is `_part_fixtures.build_part_work` (parts B1-piles and B1-caps on one drawing; invented
values), both parts locked. Its gate 1 has project reasons of its own (units, grids ...), so `open_gate`
clears them for the status, and the parts can read `ready` the way they do in a finished project.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from _part_fixtures import INPUT_PART, MANIFEST, PART, build_part_work, entry_ids, row, write_values
from tekla_harness import status as status_module
from tekla_harness import takeoff_cells, takeoff_plan, takeoff_render
from tekla_harness.cli import main
from tekla_harness.part_check import check_part
from tekla_harness.part_receipts import part_hash
from tekla_harness.schemas import validate
from tekla_harness.takeoff_cells import CHECK_FAILED_VI
from tekla_harness.takeoff_render import TakeoffContext

BUILDABLE = "dựng được"
GOOD_CAPS = row("R001")  # K-1 1500x2400 as the cited finding F-001 prints it
BAD_CAPS = row("R001", value="1600x2400")  # a size no cited source prints: the part check refuses it


@pytest.fixture
def open_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """No project reason and no open blocking question for the status: only the receipts and the part check
    decide whether a part reads `ready`. The plan cross-checks the open blocking questions against the status
    rows (an id in no row is exit 3), so its list is cleared the same way."""
    real = status_module._part_rows

    def cleared(work: Path, open_by_label: dict[str, list[str]], project_reasons: list[str]) -> Any:
        return real(work, {label: [] for label in open_by_label}, [])

    monkeypatch.setattr(status_module, "_part_rows", cleared)
    monkeypatch.setattr(takeoff_plan, "_open_blocking", lambda ctx: [])


def lock(work: Path, part: str, stored: dict[str, str] | None = None) -> None:
    """checked, reviewed, locked on the part's current hash (the hash holds values.json: write it first)."""
    manifest = json.loads((work / MANIFEST).read_text(encoding="utf-8"))
    current = part_hash(work, manifest, part)
    review = {"round": 1, "verdict": "pass", "file": f"parts/{part}/review/r.md", "sha256": "a" * 64}
    receipts = [
        {
            "n": n, "kind": kind, "part_hash": current, "at": "2026-01-01T00:00:00Z", "tool_version": "0.1.0",
            "review": review if kind == "reviewed" else None, "reason": None,
            "inputs": (stored or {}) if kind == "locked" else None,
        }
        for n, kind in enumerate(("checked", "reviewed", "locked"), start=1)
    ]  # fmt: skip
    path = work / "parts" / part / "receipts.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"schema_version": "0.1", "part": part, "receipts": receipts}
    assert validate("part-receipts", doc) == []
    path.write_text(json.dumps(doc), encoding="utf-8")


def locked_world(base: Path, caps: dict[str, Any], piles_value: str = "26") -> Path:
    """B1-piles (count `piles_value`) and B1-caps (rows `caps`) both locked, on the hashes of their current
    files."""
    work = build_part_work(base)
    piles = row(
        "R001",
        mark="P-1",
        field="count_plan",
        value=piles_value,
        sheet="model#02",
        cites={"questions": ["Q-005"], "entries": [entry_ids(work)["26"]]},
    )  # fmt: skip: a count the drawing prints, with the blocking question of its part
    write_values(work, [piles], INPUT_PART)
    write_values(work, [caps])
    manifest = json.loads((work / MANIFEST).read_text(encoding="utf-8"))
    lock(work, INPUT_PART)
    lock(work, PART, {INPUT_PART: part_hash(work, manifest, INPUT_PART)})
    return work


def run(capsys: Any, *argv: str) -> tuple[int, dict[str, Any], str]:
    code = main(["takeoff", *argv])
    cap = capsys.readouterr()
    return code, json.loads(cap.out) if cap.out else {}, cap.err


def part_file(work: Path, name: str) -> str:
    return (work.parent / "takeoff" / name).read_text(encoding="utf-8")


def state_section(text: str) -> str:
    """Section 6 of a part file."""
    return text[text.index("## 6. Trạng thái") : text.index("## 7. Tọa độ cho 3D")]


def plan_rows(work: Path) -> dict[str, str]:
    """part id -> the status cell of its row in the plan's order table."""
    lines = (work.parent / "takeoff" / "00-plan.md").read_text(encoding="utf-8").splitlines()
    start = lines.index("## Thứ tự các phần") + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    body = [ln for ln in lines[start:end] if ln.startswith("|")][2:]
    cells = [[c.strip() for c in ln.strip("|").split(" | ")] for ln in body]
    return {c[1]: c[5] for c in cells}


def test_the_world_reads_ready_when_the_check_passes(tmp_path, capsys, open_gate):
    work = locked_world(tmp_path, GOOD_CAPS)
    assert check_part(work, PART)["ok"] is True and check_part(work, INPUT_PART)["ok"] is True
    ctx = TakeoffContext.load(work)
    assert ctx.status[PART]["ready"] is True and ctx.status[PART]["check_failed"] is False
    assert ctx.status[INPUT_PART]["ready"] is True
    code, doc, _ = run(capsys, "render", str(work), "--all")
    assert code == 0 and validate("takeoff-output", doc) == []
    assert all(BUILDABLE in state_section(part_file(work, n)) for n in ("01-B1-piles.md", "02-B1-caps.md"))
    code, doc, _ = run(capsys, "plan", str(work))
    assert code == 0 and doc["ready"] == 2
    assert plan_rows(work) == {INPUT_PART: BUILDABLE, PART: BUILDABLE}


def test_a_part_whose_check_fails_never_reads_buildable_in_render_or_plan(tmp_path, capsys, open_gate):
    work = locked_world(tmp_path, BAD_CAPS)  # locked on the hash of the file it has now
    assert check_part(work, PART)["ok"] is False
    plain = status_module.build_status(work)  # the hash alone: ready
    assert {p["id"]: p["ready"] for p in plain["parts"]}[PART] is True
    code, doc, _ = run(capsys, "render", str(work), "--all")
    assert code == 0 and validate("takeoff-output", doc) == []
    caps, piles = part_file(work, "02-B1-caps.md"), part_file(work, "01-B1-piles.md")
    assert BUILDABLE not in caps and state_section(caps).strip().endswith(CHECK_FAILED_VI)
    assert BUILDABLE in state_section(piles)  # the part that passes is not touched
    code, doc, _ = run(capsys, "plan", str(work))
    assert code == 0 and validate("takeoff-output", doc) == [] and doc["ready"] == 1
    assert plan_rows(work) == {INPUT_PART: BUILDABLE, PART: CHECK_FAILED_VI}
    text = (work.parent / "takeoff" / "00-plan.md").read_text(encoding="utf-8")
    assert "1 phần sẵn sàng để dựng" in text


def test_the_context_loads_the_status_with_verify(tmp_path, monkeypatch, open_gate):
    work = locked_world(tmp_path, BAD_CAPS)
    seen: list[dict[str, Any]] = []
    real = takeoff_render.build_status

    def spy(work_dir: Path | str, **kwargs: Any) -> dict[str, Any]:
        seen.append(kwargs)
        return real(work_dir, **kwargs)

    monkeypatch.setattr(takeoff_render, "build_status", spy)
    ctx = TakeoffContext.load(work)
    assert seen == [{"verify": True}]
    assert ctx.status[PART]["check_failed"] is True and ctx.status[PART]["ready"] is False


def test_a_part_whose_input_fails_its_check_never_reads_buildable_in_render_or_plan(
    tmp_path, capsys, open_gate
):
    input_failed = takeoff_cells.INPUT_CHECK_FAILED_VI
    work = locked_world(tmp_path, GOOD_CAPS, piles_value="27")  # the drawing prints 26: the check refuses 27
    assert check_part(work, INPUT_PART)["ok"] is False and check_part(work, PART)["ok"] is True
    ctx = TakeoffContext.load(work)
    assert ctx.status[PART]["input_check_failed"] == [INPUT_PART] and ctx.status[PART]["ready"] is False
    code, doc, _ = run(capsys, "render", str(work), "--all")
    assert code == 0 and validate("takeoff-output", doc) == []
    caps, piles = part_file(work, "02-B1-caps.md"), part_file(work, "01-B1-piles.md")
    assert BUILDABLE not in caps and state_section(caps).strip().endswith(f"{input_failed} ({INPUT_PART})")
    assert BUILDABLE not in piles and state_section(piles).strip().endswith(CHECK_FAILED_VI)
    code, doc, _ = run(capsys, "plan", str(work))
    assert code == 0 and validate("takeoff-output", doc) == [] and doc["ready"] == 0
    assert plan_rows(work) == {
        INPUT_PART: CHECK_FAILED_VI,
        PART: f"{input_failed} ({INPUT_PART})",
    }
