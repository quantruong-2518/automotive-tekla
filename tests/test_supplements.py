"""`harness ask --supplement`: the drawing-reader adds evidence to a producer's question (EVAL-2 fix 7).

The world (test_ask.py's): one synthetic DXF through intake and read-structure, so the registry holds intake
and read-structure questions. A supplement never changes the target question.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from _dxf_fixtures import build_set
from tekla_harness.answers import record_answer
from tekla_harness.ask import ask_question
from tekla_harness.cli import main
from tekla_harness.intake import run_intake
from tekla_harness.questions import QuestionsError
from tekla_harness.questions_md import QuestionsMdError, render_questions_md
from tekla_harness.schemas import validate
from tekla_harness.status import build_status
from tekla_harness.structure import read_structure
from tekla_harness.supplements import (
    SUPPLEMENTS_FILE,
    add_supplement,
    load_supplements,
    supplement_key,
    withdraw_supplement,
)

PROJECT = "demo-supplements"
FILE = "set.dxf"
LEDGER = ("question-registry.json", "answers.json")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def run_cli(capsys, *argv: str) -> tuple[int, Any, str]:
    code = main(list(argv))
    cap = capsys.readouterr()
    return code, (json.loads(cap.out) if cap.out.strip() else None), cap.err


@pytest.fixture(scope="module")
def base_world(tmp_path_factory) -> Path:
    base = tmp_path_factory.mktemp("supplements")
    root = base / "input"
    root.mkdir()
    build_set(root, FILE)
    run_intake(root, base / "work", PROJECT)
    read_structure(base / "work", root)
    return base


@pytest.fixture
def work(base_world, tmp_path) -> Path:
    target = tmp_path / "w"
    shutil.copytree(base_world, target)
    return target / "work"


def entry_of(work: Path, code: str, producer: str) -> tuple[str, dict[str, Any]]:
    """(key, registry entry) of the first live question of this code and producer."""
    for key, e in load(work / "question-registry.json")["questions"].items():
        if e["code"] == code and e["producer"] == producer and e["status"] != "obsolete":
            return key, e
    raise AssertionError(f"no {producer} {code} question")


def target(work: Path) -> tuple[str, dict[str, Any]]:
    return entry_of(work, "level_finished_vs_structural", "structure")


def snapshot(work: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in work.glob("*.json")}


def supplement(work: Path, where: str = "section A-A", **kw: Any) -> dict[str, str]:
    if "target_id" not in kw:
        kw["target_id"] = target(work)[1]["id"]
    args: dict[str, Any] = {
        "where": where,
        "found": "+3.850 SÀN TẦNG 2",
        "text": "Mặt cắt A-A ghi +3.850 là cao độ sàn tầng 2.",
        "file": FILE,
        "sheet": "model#01",
    }
    return add_supplement(work, **{**args, **kw})


def refused(work: Path, code: int, **kw: Any) -> str:
    before = snapshot(work)
    with pytest.raises(QuestionsError) as caught:
        supplement(work, **kw)
    assert caught.value.exit_code == code, str(caught.value)
    assert snapshot(work) == before  # nothing written
    return str(caught.value)


# --- add --------------------------------------------------------------------------------------------


def test_a_new_supplement_is_recorded_and_changes_nothing_else(work):
    key, entry = target(work)
    before = snapshot(work)
    gate_before = build_status(work)
    result = supplement(work)
    assert result["status"] == "new" and result["target_id"] == entry["id"]
    sha = {r["path"]: r["sha256"] for r in load(work / "inventory.json")["files"]}[FILE]
    assert result["key"] == supplement_key(key, FILE, sha, "section A-A")
    doc = load(work / SUPPLEMENTS_FILE)
    assert validate("supplements", doc) == []
    assert doc["kind"] == "reader_supplements" and doc["project_id"] == PROJECT
    assert doc["supplements"] == [
        {
            "key": result["key"], "target_key": key, "target_id": entry["id"],
            "target_code": "level_finished_vs_structural", "target_producer": "structure", "file": FILE,
            "file_sha256": sha, "sheet": "model#01", "where": "section A-A", "found": "+3.850 SÀN TẦNG 2",
            "text": "Mặt cắt A-A ghi +3.850 là cao độ sàn tầng 2.", "status": "active",
        }
    ]  # fmt: skip
    after = snapshot(work)
    del after[SUPPLEMENTS_FILE]
    assert after == before  # registry, answers and question documents untouched
    assert build_status(work) == gate_before  # never changes blocking or answers
    assert not list(work.glob("*.tmp"))


def test_the_key_hashes_target_file_sha_and_where():
    payload = json.dumps(["a" * 16, "f.dxf", "b" * 64, "w"], separators=(",", ":"), ensure_ascii=True)
    expected = hashlib.sha256(payload.encode("ascii")).hexdigest()[:16]
    assert supplement_key("a" * 16, "f.dxf", "b" * 64, "w") == expected
    variants = {
        supplement_key("c" * 16, "f.dxf", "b" * 64, "w"),
        supplement_key("a" * 16, "g.dxf", "b" * 64, "w"),
        supplement_key("a" * 16, "f.dxf", "d" * 64, "w"),
        supplement_key("a" * 16, "f.dxf", "b" * 64, "x"),
        supplement_key("a" * 16, None, None, "w"),
    }
    assert expected not in variants and len(variants) == 5


def test_the_same_place_again_is_already_supplemented_and_writes_nothing(work):
    first = supplement(work)
    before = snapshot(work)
    again = supplement(work, found="other words", text="Ghi chú khác.", sheet="model#02")
    assert again == {"key": first["key"], "target_id": first["target_id"], "status": "already_supplemented"}
    assert snapshot(work) == before


def test_another_where_or_a_project_level_note_is_another_supplement(work):
    first = supplement(work)
    second = supplement(work, where="section B-B")
    third = supplement(work, file=None, sheet=None)
    assert len({first["key"], second["key"], third["key"]}) == 3
    rows = load(work / SUPPLEMENTS_FILE)["supplements"]
    assert [r["key"] for r in rows] == [first["key"], second["key"], third["key"]]  # in the order added
    assert rows[2]["file"] is None and rows[2]["file_sha256"] is None and rows[2]["sheet"] is None


def test_an_answered_target_can_still_be_supplemented(work):
    _, entry = target(work)
    record_answer(work, entry["id"], "kết cấu", "eng", role="engineer")
    assert supplement(work)["status"] == "new"


def test_refusals(work):
    assert "unknown question id" in refused(work, 2, target_id="Q-999")
    for field in ("where", "text"):
        assert f"--{field}" in refused(work, 2, **{field: "  "})
    for field in ("file", "sheet"):
        assert f"--{field}" in refused(work, 2, **{field: " "})
    assert "inventory.json" in refused(work, 1, file="nope.dxf")


def test_a_reader_question_cannot_be_supplemented(work):
    asked = ask_question(work, code="reader_gap", where="W", found="", text="?", file=FILE)
    message = refused(work, 2, target_id=asked["id"])
    assert "reader" in message and "harness ask" in message


def test_an_obsolete_target_is_refused(work):
    key, entry = target(work)
    registry = load(work / "question-registry.json")
    registry["questions"][key]["status"] = "obsolete"
    (work / "question-registry.json").write_text(json.dumps(registry), encoding="utf-8")
    assert "obsolete" in refused(work, 2, target_id=entry["id"])


def test_a_work_folder_without_a_registry_is_a_usage_error(tmp_path):
    with pytest.raises(QuestionsError) as caught:
        add_supplement(tmp_path, target_id="Q-001", where="w", found="", text="t")
    assert caught.value.exit_code == 2


# --- stale and withdraw -------------------------------------------------------------------------------


def test_a_supplement_goes_stale_when_its_target_goes_obsolete(work):
    key, _ = target(work)
    supplement(work)
    assert [s["status"] for s in load_supplements(work)] == ["active"]
    registry = load(work / "question-registry.json")
    registry["questions"][key]["status"] = "obsolete"
    (work / "question-registry.json").write_text(json.dumps(registry), encoding="utf-8")
    assert [s["status"] for s in load_supplements(work)] == ["stale"]
    assert load(work / SUPPLEMENTS_FILE)["supplements"][0]["status"] == "active"  # computed, never stored


def test_withdraw_keeps_the_supplement_with_its_reason(work):
    added = supplement(work)
    assert withdraw_supplement(work, added["key"], " trùng ") == {"key": added["key"], "status": "withdrawn"}
    (row,) = load(work / SUPPLEMENTS_FILE)["supplements"]
    assert row["status"] == "withdrawn" and row["withdrawn_reason"] == "trùng"
    assert validate("supplements", load(work / SUPPLEMENTS_FILE)) == []
    before = snapshot(work)
    assert withdraw_supplement(work, added["key"], "again")["status"] == "already_withdrawn"
    assert snapshot(work) == before
    assert [s["status"] for s in load_supplements(work)] == ["withdrawn"]
    assert "withdrawn" in refused(work, 2)  # the same place cannot be supplemented again


def test_withdraw_refusals(work):
    with pytest.raises(QuestionsError) as caught:
        withdraw_supplement(work, "0123456789abcdef", "r")
    assert caught.value.exit_code == 2  # no supplements yet
    supplement(work)
    for key, reason in (
        ("0123456789abcdef", "r"),
        (load(work / SUPPLEMENTS_FILE)["supplements"][0]["key"], " "),
    ):
        with pytest.raises(QuestionsError) as caught:
            withdraw_supplement(work, key, reason)
        assert caught.value.exit_code == 2


def test_an_invalid_supplements_document_is_refused(work):
    (work / SUPPLEMENTS_FILE).write_text('{"schema_version": "0.1"}', encoding="utf-8")
    with pytest.raises(QuestionsError) as caught:
        load_supplements(work)
    assert caught.value.exit_code == 1
    assert "is invalid" in refused(work, 1)
    with pytest.raises(QuestionsMdError) as rendered:
        render_questions_md(work)
    assert rendered.value.exit_code == 1


# --- questions.md and the command ---------------------------------------------------------------------


def test_questions_md_shows_active_supplements_under_their_question(work):
    _, entry = target(work)
    supplement(work)
    gone = supplement(work, where="góc trái", text="không dùng nữa")
    withdraw_supplement(work, gone["key"], "sai chỗ")
    text = render_questions_md(work).text
    block = text[text.index(f"##### {entry['id']} ") :].split("\n#####", 1)[0]
    assert "- **Bổ sung của người đọc:**" in block
    assert "Mặt cắt A-A ghi +3.850 là cao độ sàn tầng 2." in block and "`section A-A`" in block
    assert "không dùng nữa" not in text


def test_cli_supplement_and_withdraw(work, capsys):
    _, entry = target(work)
    argv = [
        "ask",
        str(work),
        "--supplement",
        entry["id"],
        "--where",
        "w",
        "--found",
        "",
        "--text",
        "Ghi chú.",
    ]
    code, out, err = run_cli(capsys, *argv)
    assert code == 0 and out["status"] == "new" and out["target_id"] == entry["id"] and err == ""
    code, again, err = run_cli(capsys, *argv)
    assert code == 0 and again["status"] == "already_supplemented" and "already supplemented" in err
    code, out, _ = run_cli(capsys, "ask", str(work), "--withdraw-supplement", again["key"], "--reason", "r")
    assert code == 0 and out == {"key": again["key"], "status": "withdrawn"}
    argv[3] = "Q-999"
    code, out, err = run_cli(capsys, *argv)
    assert code == 2 and out is None and "unknown question id" in err
