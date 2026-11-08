"""Gate 1 and questions.md after the tool wave 2 review (package F3).

1. Only the engineer's answer settles a question of a gate producer (intake, read-structure, grid-system,
   reader): a simulated or role-less answer leaves it open in `harness status` and in questions.md, where
   the answer is shown with its role.
2. A grid-system conflict waiting for the file-set answer is pending, not closed, in questions.md.

The two-sheet world is test_status.py's; the one-grid files are built here (one grid per file, so two
files with the same labels and different spacings conflict across files).
"""

# ruff: noqa: F811

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest
from ezdxf.filemanagement import new

from _dxf_fixtures import _bubble_block, _frame, _frame_block, _grid, _level, _level_block, _save
from tekla_harness.answers import record_answer
from tekla_harness.questions import empty_answers
from tekla_harness.questions_md import Item, _answered_lines, code_span, render_questions_md
from tekla_harness.status import build_status
from test_status import (  # noqa: F401  (pytest fixtures, used by name)
    CONFLICT_CODE,
    answer_blocking,
    answer_select,
    base_world,
    by_label,
    find,
    load,
    questions_of,
    ready,
    ready_world,
    rerun_all,
    world,
)

ENGINEER_STEP = "the engineer runs: "
MD_ENGINEER = "kỹ sư tự chạy, tác tử không chạy thay"


def sections(text: str) -> dict[str, str]:
    parts = re.split(r"^## (\d+)\. ", text, flags=re.MULTILINE)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


def block_of(text: str, qid: str) -> str:
    """The `##### Q-...` block of a question in questions.md."""
    start = text.index(f"##### {qid} ")
    return re.split(r"\n#{2,5} ", text[start:], maxsplit=1)[0]


def one_grid(path: Path, xs: list[float], number: str) -> Path:
    """A one-sheet DXF (mm) with one grid: vertical axes at `xs`, labelled 1..n, and lettered rows."""
    doc = new("R2018", setup=True)
    doc.header["$INSUNITS"] = 4
    doc.layers.add("S-GRID")
    doc.layers.add("AXIS_BUBBLES")
    _frame_block(doc)
    _bubble_block(doc)
    _level_block(doc)
    msp = doc.modelspace()
    _frame(msp, 0.0, number, "A")
    _grid(msp, 0.0, xs, loose_horizontal=False)
    _level(msp, (40000, 40000), "+0.000")
    _level(msp, (40000, 43000), "+3.600")
    return _save(doc, path)


@pytest.fixture(scope="module")
def two_files_base(tmp_path_factory) -> Path:
    """a.dxf and b.dxf: same labels, one spacing differs, so their systems conflict across files while the
    file_set_relation question is open."""
    base = tmp_path_factory.mktemp("two-files")
    root = base / "input"
    root.mkdir()
    one_grid(root / "a.dxf", [0, 6000, 12000, 18000], "S-101")
    one_grid(root / "b.dxf", [0, 6000, 12000, 18500], "S-201")
    rerun_all(root, base / "work")
    return base


@pytest.fixture
def two_files(two_files_base, tmp_path) -> tuple[Path, Path]:
    target = tmp_path / "t"
    shutil.copytree(two_files_base, target)
    return target / "input", target / "work"


# --- 1. only the engineer's answer settles a gate producer's question ------------------------------------


def strip_role(work: Path, question_id: str) -> None:
    doc = load(work / "answers.json")
    for a in doc["answers"]:
        if a["question_id"] == question_id:
            a.pop("answered_by_role", None)
    (work / "answers.json").write_text(json.dumps(doc), encoding="utf-8")


@pytest.mark.parametrize(("role", "label"), [("simulated", "(mô phỏng)"), (None, "(chưa rõ vai trò)")])
def test_a_non_engineer_answer_leaves_a_blocking_question_open(world, role, label):
    """Review probe p1: a simulated answer to Q-017 level_finished_vs_structural moved read-structure
    blocking_open from 14 to 13 and the question from section 2 to section 4, with no role shown."""
    _, work = world
    q = find(questions_of(work, "structure-questions.json"), "level_finished_vs_structural", "set.dxf")
    before = by_label(build_status(work))["read-structure"]
    assert q["id"] in before["blocking_open_ids"]
    record_answer(work, q["id"], "structural (agent guess)", "agent", role="simulated")
    if role is None:
        strip_role(work, q["id"])
    status = build_status(work)
    after = by_label(status)["read-structure"]
    assert after["questions"]["blocking_open"] == before["questions"]["blocking_open"]
    assert after["questions"]["answered"] == before["questions"]["answered"]
    assert q["id"] in after["blocking_open_ids"]
    assert status["gate1"]["ready_for_gate1"] is False
    rendered = render_questions_md(work)
    body = sections(rendered.text)
    assert f"##### {q['id']} " in body["2"]
    assert not [ln for ln in body["4"].splitlines() if ln.startswith(f"- {q['id']} ")]
    block = block_of(rendered.text, q["id"])
    assert label in block and code_span("structural (agent guess)") in block
    assert f"**Lệnh trả lời ({MD_ENGINEER}):**" in block
    assert rendered.summary["blocking_open"] == sum(
        p["questions"]["blocking_open"] for p in status["producers"]
    )


def test_the_engineer_answer_settles_it_and_shows_no_role_label(world):
    _, work = world
    q = find(questions_of(work, "structure-questions.json"), "level_finished_vs_structural", "set.dxf")
    record_answer(work, q["id"], "structural (agent guess)", "agent", role="simulated")
    before = by_label(build_status(work))["read-structure"]["questions"]
    record_answer(work, q["id"], "structural", "the engineer", role="engineer")
    after = by_label(build_status(work))
    assert after["read-structure"]["questions"]["blocking_open"] == before["blocking_open"] - 1
    assert after["read-structure"]["questions"]["answered"] == before["answered"] + 1
    assert q["id"] not in after["read-structure"]["blocking_open_ids"]
    body = sections(render_questions_md(work).text)
    assert f"##### {q['id']} " not in body["2"] + body["3"]
    (line,) = [ln for ln in body["4"].splitlines() if ln.startswith(f"- {q['id']} ")]
    assert "mô phỏng" not in line and "chưa rõ vai trò" not in line


def inject_answered(work: Path, producer: str, code: str, role: str) -> str:
    registry = load(work / "question-registry.json")
    path = work / "answers.json"
    answers = load(path) if path.is_file() else empty_answers(registry["project_id"])
    number = registry["next_id"]
    qid, key = f"Q-{number:03d}", f"{number:016x}"
    registry["questions"][key] = {
        "id": qid, "code": code, "file": "set.dxf", "producer": producer, "status": "answered",
        "first_seen_run": 1, "last_seen_run": 1, "blocking": True, "file_sha256": None,
    }  # fmt: skip
    registry["next_id"] = number + 1
    answers["answers"].append(
        {
            "key": key, "question_id": qid, "code": code, "file": "set.dxf", "answer_text": "x",
            "values": {}, "answered_by": "agent", "answered_by_role": role, "answered_on": "2026-11-08",
            "status": "active",
        }
    )  # fmt: skip
    (work / "question-registry.json").write_text(json.dumps(registry), encoding="utf-8")
    (work / "answers.json").write_text(json.dumps(answers), encoding="utf-8")
    return qid


@pytest.mark.parametrize(
    ("label", "producer", "code", "settled"),
    [
        ("callouts", "callouts", "callout_ambiguous", True),  # not read by gate 1: any answer settles it
        ("marks", "marks", "mark_unparsed", True),
        ("intake", "intake", "read_failed", False),
        ("read-structure", "structure", "grid_label_missing", False),
        ("grid-system", "grid-system", "grid_system_select", False),
        ("reader", "reader", "reader_gap", False),
    ],
)
def test_only_gate_producers_need_the_engineers_answer(world, label, producer, code, settled):
    _, work = world
    before = by_label(build_status(work))[label]["questions"]
    qid = inject_answered(work, producer, code, "simulated")
    after = by_label(build_status(work))[label]
    assert after["questions"]["total"] == before["total"] + 1
    assert after["questions"]["answered"] == before["answered"] + settled
    assert after["questions"]["blocking_open"] == before["blocking_open"] + (not settled)
    assert (qid in after["blocking_open_ids"]) is not settled


def item(producer: str, role: str | None) -> Item:
    answer = {
        "answer_text": "x", "values": {}, "answered_by": "agent", "answered_on": "2026-11-08",
        **({"answered_by_role": role} if role else {}),
    }  # fmt: skip
    return Item(
        id="Q-070", key="7" * 16, code="mark_unparsed", blocking=True, file="a.dxf", message="m",
        count=1, truncated=False, refs=[], subjects=None, source="marks-questions.json",
        producer=producer, topic="marks", answer=answer,
    )  # fmt: skip


def test_an_answered_line_names_a_non_engineer_role():
    """Section 4: a non-gate question answered by a simulation is settled but says who answered."""
    simulated, legacy, engineer = item("marks", "simulated"), item("marks", None), item("marks", "engineer")
    assert not simulated.is_open and not legacy.is_open and not engineer.is_open
    assert "(mô phỏng)" in _answered_lines([simulated])[0]
    assert "(chưa rõ vai trò)" in _answered_lines([legacy])[0]
    assert (
        "mô phỏng" not in _answered_lines([engineer])[0] and "vai trò" not in _answered_lines([engineer])[0]
    )
    assert item("structure", "simulated").is_open and not item("structure", "engineer").is_open


# --- 2. a conflict pending on the file sets is not "closed" -------------------------------------------


def test_a_conflict_pending_on_the_file_sets_says_so_and_not_that_it_closed(two_files):
    """Review probe p2b: questions.md said the pending conflict was closed by the select answer."""
    _, work = two_files
    doc = load(work / "grid-systems.json")
    assert doc["file_sets"]["status"] == "pending"
    (conflict,) = doc["conflicts"]
    assert conflict["blocking"] is False and conflict["closed_by"] is None
    text = render_questions_md(work).text
    block = block_of(text, conflict["question_id"])
    assert f"##### {conflict['question_id']} " in sections(text)["3"]
    file_set = doc["file_sets"]["question_id"]
    assert f"đang chờ câu {file_set} ({code_span('file_set_relation')})" in block, block
    assert "đã đóng" not in block and "không còn chặn" not in block
    assert MD_ENGINEER in block


def test_a_non_blocking_conflict_with_no_closure_and_no_pending_file_set_shows_how_to_close(two_files):
    """Fail closed: without a closure or a pending file set, the block says how to close it."""
    _, work = two_files
    doc = load(work / "grid-systems.json")
    doc["file_sets"]["status"] = "answered"  # the pending reason is gone; nothing closed the conflict
    (work / "grid-systems.json").write_text(json.dumps(doc), encoding="utf-8")
    block = block_of(render_questions_md(work).text, doc["conflicts"][0]["question_id"])
    assert "đang chờ" not in block and "đã đóng" not in block and "không còn chặn" not in block
    assert "- **Cách đóng" in block and "Trạng thái" not in block


def test_a_conflict_the_select_answer_closed_is_listed_as_closed(ready):
    _, work = ready
    conflict = find(questions_of(work, "grid-system-questions.json"), CONFLICT_CODE)
    (line,) = [
        ln
        for ln in sections(render_questions_md(work).text)["4"].splitlines()
        if ln.startswith(f"- {conflict['id']} ")
    ]
    assert "đã đóng" in line and code_span("separate") in line
