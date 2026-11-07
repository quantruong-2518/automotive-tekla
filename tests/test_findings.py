"""findings: `harness finding add | withdraw | list` over a real intake work folder (see _callout_fixtures).

The world is built once per module: sheet S-101 (model#01) holds a notes block, sheet S-102 (model#02) other
texts, and the styled texts of the fixture give entries the legacy-font gate blocks (T000043, T000046:
unknown encoding, proposed knowledge row; the registry carries the font questions for them). Tests that
write work on a copy.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from _callout_fixtures import REL, build_work
from tekla_harness.cli import main
from tekla_harness.findings import FindingError, add_finding, list_findings, withdraw_finding
from tekla_harness.schemas import validate

NOTES = ["GENERAL NOTES", "Concrete grade C30/37 for all", "foundations   and columns"]
HEAD, CONCRETE, REST = "T000040", "T000041", "T000042"  # on model#01
BLOCKED = "T000043"  # model#01, unknown encoding + proposed row
BLOCKED2 = "T000046"
OTHER_SHEET = "T000050"  # 'C1' on model#02
LOW = "T000045"  # 'd1', confidence low
ASCII_PROPOSED = "T000044"  # '4%%c16' with a proposed row, but ASCII raw text: allowed


@pytest.fixture(scope="module")
def world(tmp_path_factory) -> Path:
    return build_work(tmp_path_factory.mktemp("findings"), s1=NOTES)


@pytest.fixture
def work(world, tmp_path) -> Path:
    target = tmp_path / "copy"
    shutil.copytree(world, target)
    return target


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def doc(work: Path) -> dict[str, Any]:
    return load(work / "reader-findings.json")


def add(work: Path, **kw: Any) -> dict[str, str]:
    kw.setdefault("file", REL)
    kw.setdefault("entries", [CONCRETE])
    return add_finding(work, **kw)


def refused(work: Path, code: int, **kw: Any) -> str:
    before = (
        (work / "reader-findings.json").read_bytes() if (work / "reader-findings.json").exists() else None
    )
    with pytest.raises(FindingError) as err:
        add(work, **kw)
    assert err.value.exit_code == code, str(err.value)
    after = (work / "reader-findings.json").read_bytes() if (work / "reader-findings.json").exists() else None
    assert before == after  # nothing written
    return str(err.value)


def edit_index(work: Path, edits: dict[str, dict[str, Any]]) -> None:
    path = work / "text" / f"{REL}.json"
    index = load(path)
    for e in index["entries"]:
        if e["id"] in edits:
            e.update(edits[e["id"]])
    path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")


def cli(capsys, *argv: str) -> tuple[int, str, str]:
    code = main(["finding", *argv])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# --- happy paths ----------------------------------------------------------------------------------------


def test_sheet_class_is_recorded_with_the_entries_text_and_sha(work):
    result = add(work, kind="sheet_class", sheet="model#01", entries=[HEAD], value="general_notes")
    assert result == {"id": "F-001", "status": "new"}
    d = doc(work)
    assert validate("reader-findings", d) == []
    assert d["kind"] == "reader_findings" and d["project_id"] == "demo-callouts" and d["next_id"] == 2
    f = d["findings"][0]
    sha = {r["path"]: r["sha256"] for r in load(work / "inventory.json")["files"]}[REL]
    assert f["file_sha256"] == sha and f["sheet"] == "model#01" and f["status"] == "active"
    assert f["entries"] == [{"id": HEAD, "display_text": "GENERAL NOTES"}]
    assert f["confidence"] == "medium" and f["fields"] == {} and f["questions"] == []
    assert not list(work.glob("*.tmp"))


def test_note_item_quote_across_entries_ignores_whitespace_runs(work):
    # the second entry stores 'foundations   and columns'; the quote may use single spaces
    result = add(
        work,
        kind="note_item",
        sheet="model#01",
        entries=[CONCRETE, REST],
        value="Concrete grade C30/37 for all foundations and columns",
        fields=["topic=concrete_class"],
    )
    assert result["status"] == "new"
    f = doc(work)["findings"][0]
    assert f["fields"] == {"topic": "concrete_class"}
    assert f["entries"][1]["display_text"] == "foundations   and columns"  # copied verbatim


def test_note_item_may_quote_a_part_of_one_entry(work):
    add(work, kind="note_item", entries=[CONCRETE], value="C30/37", fields=["topic=concrete_class"])
    assert doc(work)["findings"][0]["sheet"] is None


def test_structural_system_may_span_sheets_of_one_file(work):
    add(
        work,
        kind="structural_system",
        entries=[CONCRETE, OTHER_SHEET],
        value="two-storey frame",
        fields=["aspect=floors"],
    )
    f = doc(work)["findings"][0]
    assert f["sheet"] is None and [e["id"] for e in f["entries"]] == [CONCRETE, OTHER_SHEET]


def test_cross_check_needs_two_entries_and_a_question(work):
    ok = add(
        work,
        kind="cross_check",
        entries=[CONCRETE, OTHER_SHEET],
        value="the note and the schedule disagree",
        questions=["Q-001"],
    )
    assert ok["id"] == "F-001" and doc(work)["findings"][0]["questions"] == ["Q-001"]
    one = refused(work, 2, kind="cross_check", entries=[CONCRETE], value="x", questions=["Q-001"])
    assert "two entries" in one
    assert "--question" in refused(work, 2, kind="cross_check", entries=[CONCRETE, REST], value="x")


def test_an_ascii_entry_with_a_proposed_row_is_allowed(work):
    add(work, kind="structural_system", entries=[ASCII_PROPOSED], value="v", fields=["aspect=floors"])


# --- usage ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kw",
    [
        {"kind": "sheet_class", "value": "general_notes"},  # no sheet
        {"kind": "sheet_class", "sheet": "model#01", "value": "kitchen"},  # not in the list
        {"kind": "sheet_class", "sheet": "model#01", "value": "other"},  # other needs a note
        {"kind": "note_item", "value": "C30/37"},  # no topic
        {"kind": "note_item", "value": "C30/37", "fields": ["topic=paint"]},
        {"kind": "structural_system", "value": "v", "fields": ["aspect=colour"]},
        {"kind": "structural_system", "value": "v", "fields": ["aspect"]},
        {"kind": "structural_system", "value": " ", "fields": ["aspect=floors"]},
        {"kind": "structural_system", "value": "v", "fields": ["aspect=floors"], "confidence": "high"},
        {"kind": "structural_system", "value": "v", "fields": ["aspect=floors"], "entries": ["X1"]},
        {"kind": "structural_system", "value": "v", "fields": ["aspect=floors"], "entries": [REST, REST]},
        {"kind": "structural_system", "value": "v", "fields": ["aspect=floors"], "questions": ["Q1"]},
        {"kind": "nonsense", "value": "v"},
    ],
)
def test_usage_errors_exit_2(work, kw):
    refused(work, 2, **kw)


def test_sheet_class_other_with_a_note(work):
    add(work, kind="sheet_class", sheet="model#01", entries=[HEAD], value="other", note="a legend sheet")
    assert doc(work)["findings"][0]["note"] == "a legend sheet"


# --- refusals that depend on the work folder ------------------------------------------------------------


def test_note_value_must_be_a_verbatim_quote(work):
    msg = refused(
        work,
        1,
        kind="note_item",
        entries=[CONCRETE],
        value="Concrete class is C30/37",  # a paraphrase
        fields=["topic=concrete_class"],
    )
    assert "verbatim" in msg
    # a quote is case-sensitive and must not reorder
    refused(
        work, 1, kind="note_item", entries=[CONCRETE], value="CONCRETE GRADE", fields=["topic=concrete_class"]
    )
    refused(
        work,
        1,
        kind="note_item",
        entries=[REST, CONCRETE],
        value="Concrete grade C30/37 for all foundations and columns",
        fields=["topic=concrete_class"],
    )


def test_entry_on_another_sheet_is_refused(work):
    msg = refused(work, 1, kind="sheet_class", sheet="model#01", entries=[OTHER_SHEET], value="foundation")
    assert OTHER_SHEET in msg and "model#01" in msg


def test_unknown_sheet_entry_file_and_question(work):
    assert "model#09" in refused(work, 1, kind="sheet_class", sheet="model#09", value="foundation")
    assert "T009999" in refused(
        work, 1, kind="structural_system", entries=["T009999"], value="v", fields=["aspect=floors"]
    )
    assert "other.dxf" in refused(
        work, 1, kind="structural_system", file="other.dxf", value="v", fields=["aspect=floors"]
    )
    assert "Q-999" in refused(
        work, 1, kind="structural_system", value="v", fields=["aspect=floors"], questions=["Q-999"]
    )


def test_obsolete_question_is_refused(work):
    path = work / "question-registry.json"
    registry = load(path)
    for entry in registry["questions"].values():
        if entry["id"] == "Q-001":
            entry["status"] = "obsolete"
    path.write_text(json.dumps(registry), encoding="utf-8")
    assert "obsolete" in refused(
        work, 1, kind="structural_system", value="v", fields=["aspect=floors"], questions=["Q-001"]
    )


def test_blocked_entry_is_refused_with_reason_and_font_questions(work):
    msg = refused(
        work,
        1,
        kind="sheet_class",
        sheet="model#01",
        entries=[HEAD, BLOCKED, BLOCKED2],
        value="general_notes",
    )
    assert BLOCKED in msg and BLOCKED2 in msg and HEAD not in msg
    assert "encoding_proposed" in msg
    # the font questions of the file, ids from the registry
    assert "Q-003 (font_encoding_proposed" in msg and "Q-005 (encoding_unknown_non_ascii" in msg
    assert "harness ask" in msg


@pytest.mark.parametrize(
    ("patch", "reason"),
    [
        ({"flags": ["knowledge_conflict"]}, "knowledge_conflict"),
        ({"flags": ["unicode_evidence_contradicts_font"]}, "encoding_contradiction"),
        ({"decode": {"encoding_used": "unknown", "run_details": []}}, "encoding_unknown"),
    ],
)
def test_every_gate_reason_blocks_a_non_ascii_entry(work, patch, reason):
    index = load(work / "text" / f"{REL}.json")
    entry = next(e for e in index["entries"] if e["id"] == REST)
    patch = {"raw_text": "tªn", **patch}
    if "decode" in patch:
        patch["decode"] = {**entry["decode"], **patch["decode"]}
    edit_index(work, {REST: patch})
    msg = refused(work, 1, kind="structural_system", entries=[REST], value="v", fields=["aspect=floors"])
    assert reason in msg and REST in msg


def test_no_font_question_in_the_registry_is_said(work):
    path = work / "question-registry.json"
    registry = load(path)
    registry["questions"] = {
        k: v
        for k, v in registry["questions"].items()
        if v["code"]
        not in (
            "font_encoding_proposed",
            "text_encoding_hint",
            "encoding_unknown_non_ascii",
            "font_encoding_conflict",
        )
    }
    path.write_text(json.dumps(registry), encoding="utf-8")
    msg = refused(work, 1, kind="structural_system", entries=[BLOCKED], value="v", fields=["aspect=floors"])
    assert "no font question is registered" in msg


def test_sheets_document_missing_refuses_a_sheet_finding(work):
    (work / "structure" / f"{REL}.sheets.json").unlink()
    assert "read-structure" in refused(
        work, 1, kind="sheet_class", sheet="model#01", entries=[HEAD], value="general_notes"
    )
    add(work, kind="structural_system", value="v", fields=["aspect=floors"])  # no sheet needed


# --- confidence -----------------------------------------------------------------------------------------


def test_confidence_is_the_minimum_and_can_only_be_lowered(work):
    add(work, kind="structural_system", entries=[CONCRETE, LOW], value="v", fields=["aspect=floors"])
    assert doc(work)["findings"][0]["confidence"] == "low"  # one low entry
    msg = refused(
        work,
        1,
        kind="structural_system",
        entries=[LOW],
        value="w",
        fields=["aspect=floors"],
        confidence="medium",
    )
    assert "lowered" in msg
    add(
        work,
        kind="structural_system",
        entries=[CONCRETE],
        value="x",
        fields=["aspect=floors"],
        confidence="low",
    )
    assert doc(work)["findings"][1]["confidence"] == "low"


def test_confidence_is_never_high(work):
    edit_index(work, {CONCRETE: {"confidence": "high"}})
    add(work, kind="structural_system", entries=[CONCRETE], value="v", fields=["aspect=floors"])
    assert doc(work)["findings"][0]["confidence"] == "medium"


# --- ids, withdraw, duplicates, stale -------------------------------------------------------------------


def test_ids_are_never_reused_after_a_withdraw(work):
    add(work, kind="sheet_class", sheet="model#01", entries=[HEAD], value="general_notes")
    assert withdraw_finding(work, "F-001", "wrong sheet") == {"id": "F-001", "status": "withdrawn"}
    second = add(work, kind="sheet_class", sheet="model#01", entries=[HEAD], value="foundation")
    assert second["id"] == "F-002"  # the withdrawn class no longer blocks a new one
    d = doc(work)
    assert [f["id"] for f in d["findings"]] == ["F-001", "F-002"] and d["next_id"] == 3
    assert d["findings"][0]["status"] == "withdrawn"
    assert d["findings"][0]["withdrawn_reason"] == "wrong sheet"
    assert validate("reader-findings", d) == []
    before = (work / "reader-findings.json").read_bytes()
    assert withdraw_finding(work, "F-001", "again") == {"id": "F-001", "status": "already_withdrawn"}
    assert (work / "reader-findings.json").read_bytes() == before
    assert doc(work)["findings"][0]["withdrawn_reason"] == "wrong sheet"
    # a withdrawn finding is added again under a new id
    third = add(work, kind="sheet_class", sheet="model#01", entries=[HEAD], value="foundation")
    assert third["status"] == "already_recorded" and third["id"] == "F-002"


def test_withdraw_errors_are_usage(work):
    with pytest.raises(FindingError) as err:
        withdraw_finding(work, "F-001", "x")  # no document yet
    assert err.value.exit_code == 2
    add(work, kind="structural_system", value="v", fields=["aspect=floors"])
    for fid, reason in (("F-009", "x"), ("F-001", "  ")):
        with pytest.raises(FindingError) as err:
            withdraw_finding(work, fid, reason)
        assert err.value.exit_code == 2


def test_adding_the_same_finding_again_changes_nothing(work):
    kw = {"kind": "structural_system", "value": "v", "fields": ["aspect=floors"]}
    first = add(work, **kw)
    before = (work / "reader-findings.json").read_bytes()
    assert add(work, **kw) == {"id": first["id"], "status": "already_recorded"}
    assert (work / "reader-findings.json").read_bytes() == before
    add(work, **{**kw, "value": "w"})  # another value is another finding
    assert [f["id"] for f in doc(work)["findings"]] == ["F-001", "F-002"]


def test_a_sheet_has_one_active_class(work):
    add(work, kind="sheet_class", sheet="model#01", entries=[HEAD], value="general_notes")
    msg = refused(work, 1, kind="sheet_class", sheet="model#01", entries=[HEAD], value="foundation")
    assert "F-001" in msg and "withdraw" in msg


def test_stale_after_an_inventory_change_and_add_refuses_nothing_for_it(work):
    add(work, kind="structural_system", value="v", fields=["aspect=floors"])
    assert [f["stale"] for f in list_findings(work)["findings"]] == [False]
    path = work / "inventory.json"
    inventory = load(path)
    for row in inventory["files"]:
        if row["path"] == REL:
            row["sha256"] = "0" * 64
    path.write_text(json.dumps(inventory), encoding="utf-8")
    listing = list_findings(work)
    assert [f["stale"] for f in listing["findings"]] == [True]
    assert load(work / "reader-findings.json")["findings"][0].get("stale") is None  # not stored
    second = add(work, kind="structural_system", value="w", fields=["aspect=floors"])
    assert second["id"] == "F-002"
    assert doc(work)["findings"][1]["file_sha256"] == "0" * 64
    assert [f["stale"] for f in list_findings(work)["findings"]] == [True, False]


def test_list_filters_and_empty_document(work):
    empty = list_findings(work)
    assert empty["findings"] == [] and empty["next_id"] == 1 and empty["project_id"] == "demo-callouts"
    assert not (work / "reader-findings.json").exists()  # list writes nothing
    add(work, kind="structural_system", value="v", fields=["aspect=floors"])
    add(work, kind="sheet_class", sheet="model#01", entries=[HEAD], value="general_notes")
    assert [f["id"] for f in list_findings(work, kind="sheet_class")["findings"]] == ["F-002"]
    assert list_findings(work, file="other.dxf")["findings"] == []
    assert len(list_findings(work, file=REL)["findings"]) == 2


def test_another_projects_document_is_refused(work):
    add(work, kind="structural_system", value="v", fields=["aspect=floors"])
    d = doc(work)
    d["project_id"] = "another-project"
    (work / "reader-findings.json").write_text(json.dumps(d), encoding="utf-8")
    assert "another-project" in refused(
        work, 1, kind="structural_system", value="w", fields=["aspect=floors"]
    )


def test_an_invalid_stored_document_is_refused(work):
    (work / "reader-findings.json").write_text('{"schema_version": "0.1"}', encoding="utf-8")
    assert "invalid" in refused(work, 1, kind="structural_system", value="w", fields=["aspect=floors"])


def test_the_document_is_deterministic(work, tmp_path):
    other = tmp_path / "other"
    shutil.copytree(work, other)
    for w in (work, other):
        add(w, kind="sheet_class", sheet="model#01", entries=[HEAD], value="general_notes")
        add(w, kind="structural_system", value="v", fields=["aspect=floors"])
    assert (work / "reader-findings.json").read_bytes() == (other / "reader-findings.json").read_bytes()


def test_no_work_folder_or_inventory_is_usage(tmp_path):
    with pytest.raises(FindingError) as err:
        add(tmp_path / "missing", kind="structural_system", value="v", fields=["aspect=floors"])
    assert err.value.exit_code == 2
    with pytest.raises(FindingError) as err:
        add(tmp_path, kind="structural_system", value="v", fields=["aspect=floors"])  # no inventory.json
    assert err.value.exit_code == 2


# --- schema ---------------------------------------------------------------------------------------------


def test_example_is_valid(example):
    assert validate("reader-findings", example("reader-findings")) == []


def _example_problems(example, mutate) -> list[Any]:
    d = example("reader-findings")
    mutate(d)
    return validate("reader-findings", d)


def test_schema_rejects_the_rules_it_states(example):
    def finding(d: dict[str, Any], i: int) -> dict[str, Any]:
        return d["findings"][i]

    assert _example_problems(example, lambda d: finding(d, 0).update(value="kitchen"))
    assert _example_problems(example, lambda d: finding(d, 0).update(sheet=None))
    assert _example_problems(example, lambda d: finding(d, 1).update(fields={}))
    assert _example_problems(example, lambda d: finding(d, 1).update(fields={"topic": "paint"}))
    assert _example_problems(example, lambda d: finding(d, 2).update(fields={}))
    assert _example_problems(example, lambda d: finding(d, 3).update(questions=[]))
    assert _example_problems(example, lambda d: finding(d, 3).update(entries=finding(d, 3)["entries"][:1]))
    assert _example_problems(example, lambda d: finding(d, 0).update(confidence="high"))
    assert _example_problems(example, lambda d: finding(d, 0).update(withdrawn_reason="x"))
    assert _example_problems(example, lambda d: finding(d, 2).pop("withdrawn_reason"))
    assert _example_problems(example, lambda d: finding(d, 0).update(entries=[]))


# --- CLI ------------------------------------------------------------------------------------------------


def test_cli_add_list_withdraw(work, capsys):
    code, out, err = cli(
        capsys, "add", str(work), "--kind", "sheet_class", "--file", REL, "--sheet", "model#01",
        "--entries", HEAD, "--value", "general_notes",
    )  # fmt: skip
    assert (code, json.loads(out)) == (0, {"id": "F-001", "status": "new"}) and err == ""
    code, out, err = cli(
        capsys, "add", str(work), "--kind", "note_item", "--file", REL, "--entries", f"{CONCRETE},{REST}",
        "--value", "Concrete grade C30/37 for all foundations and columns", "--field", "topic=concrete_class",
        "--question", "Q-001", "--note", "general notes",
    )  # fmt: skip
    assert code == 0 and json.loads(out)["id"] == "F-002"
    code, out, _ = cli(capsys, "list", str(work), "--kind", "note_item")
    listing = json.loads(out)
    assert code == 0 and [f["id"] for f in listing["findings"]] == ["F-002"]
    assert listing["findings"][0]["stale"] is False and listing["findings"][0]["note"] == "general notes"
    code, out, _ = cli(capsys, "withdraw", str(work), "F-001", "--reason", "wrong")
    assert (code, json.loads(out)["status"]) == (0, "withdrawn")
    code, out, _ = cli(capsys, "withdraw", str(work), "F-001", "--reason", "wrong")
    assert (code, json.loads(out)["status"]) == (0, "already_withdrawn")


def test_cli_repeat_add_says_so_on_stderr(work, capsys):
    argv = ("add", str(work), "--kind", "structural_system", "--file", REL, "--entries", REST,
            "--value", "v", "--field", "aspect=floors")  # fmt: skip
    assert cli(capsys, *argv)[0] == 0
    code, out, err = cli(capsys, *argv)
    assert code == 0 and json.loads(out)["status"] == "already_recorded" and "already recorded" in err


def test_cli_exit_codes(work, capsys):
    base = ("add", str(work), "--file", REL, "--entries", BLOCKED, "--value", "v")
    code, out, err = cli(capsys, *base, "--kind", "structural_system", "--field", "aspect=floors")
    assert code == 1 and out == "" and "blocked" in err and not (work / "reader-findings.json").exists()
    assert cli(capsys, *base, "--kind", "structural_system")[0] == 2  # no aspect
    assert cli(capsys, *base)[0] == 2  # no --kind (argparse)
    assert (
        cli(capsys, *base, "--kind", "structural_system", "--confidence", "high")[0] == 2
    )  # argparse choices
    assert cli(capsys, "withdraw", str(work), "F-001", "--reason", "x")[0] == 2
    assert cli(capsys, "add", str(work / "nope"), "--kind", "structural_system", "--file", REL,
               "--entries", REST, "--value", "v", "--field", "aspect=floors")[0] == 2  # fmt: skip
    assert cli(capsys)[0] == 2  # no action


# --- review fixes -----------------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["C30/3", "0/37 f", "30/37", "oncrete", "Concrete grade C30/37 for al"])
def test_note_item_quote_cut_mid_token_is_refused(work, value):
    message = refused(
        work, 1, kind="note_item", entries=[CONCRETE], value=value, fields=["topic=concrete_class"]
    )
    assert "word boundaries" in message


@pytest.mark.parametrize("value", ["C30/37", "grade C30/37 for", "Concrete", "all", "C30/37 for all"])
def test_note_item_quote_at_token_boundaries_is_accepted(work, value):
    result = add(work, kind="note_item", entries=[CONCRETE], value=value, fields=["topic=concrete_class"])
    assert result["status"] == "new"


def test_a_write_failure_is_exit_3_not_a_traceback(work, capsys):
    (work / "reader-findings.json").mkdir()  # the atomic replace onto a folder fails with an OSError
    code, _, err = cli(
        capsys, "add", str(work), "--kind", "structural_system", "--file", REL, "--entries", CONCRETE,
        "--value", "v", "--field", "aspect=floors",
    )  # fmt: skip
    assert code == 3 and "cannot write" in err and "Traceback" not in err


def test_a_corrupt_next_id_is_refused(work):
    add(work, kind="structural_system", value="v", fields=["aspect=floors"])
    add(work, kind="structural_system", value="w", fields=["aspect=floors"])
    d = doc(work)
    d["next_id"] = 2  # F-002 exists: the next allocation would reuse its id
    (work / "reader-findings.json").write_text(json.dumps(d), encoding="utf-8")
    message = refused(work, 1, kind="structural_system", value="x", fields=["aspect=floors"])
    assert "next_id 2 is not above the highest id F-002" in message
    with pytest.raises(FindingError) as err:
        list_findings(work)
    assert err.value.exit_code == 1
