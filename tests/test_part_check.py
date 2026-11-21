"""`harness part check W --part X`: the frame of the part gate (ADR-0019, E5a): the `part-values` schema, the
loader, the row checks, the output and the exit codes.

The work folder is a real `run_intake` of a synthetic set with a manifest, findings and questions recorded
with `--part` (`_part_fixtures`). Each test copies it and changes one thing. The checks of citations,
numbers, hand sums and text rules have their own test files; here they are the empty stubs, or a hook that
returns one problem.
"""

from __future__ import annotations

import copy
import importlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from _part_fixtures import (
    INPUT_PART,
    MANIFEST,
    PART,
    REL,
    build_part_work,
    entry_ids,
    entry_row,
    part_manifest,
    problems,
    put_manifest,
    row,
    run_check,
    write_values,
)
from conftest import EXAMPLES
from tekla_harness.cli import build_parser, main
from tekla_harness.schemas import validate


def mod(name: str) -> Any:
    """A module under test, imported when a test runs (the red commit has no module yet)."""
    return importlib.import_module(f"tekla_harness.{name}")


@pytest.fixture(scope="module")
def base_work(tmp_path_factory) -> Path:
    return build_part_work(tmp_path_factory.mktemp("partcheck"))


@pytest.fixture
def work(base_work, tmp_path) -> Path:
    target = tmp_path / "work"
    shutil.copytree(base_work, target)
    return target


needs_permissions = pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="chmod 000 is no barrier on Windows or for root",
)


def example_schema(name: str) -> Any:
    return json.loads((EXAMPLES.parent / f"{name}.schema.json").read_text(encoding="utf-8"))


def example_values() -> dict[str, Any]:
    return json.loads((EXAMPLES / "part-values.example.json").read_text(encoding="utf-8"))


# --- the schema --------------------------------------------------------------------------------------------


def test_values_example_valid_unknown_keys_fail():
    doc = example_values()
    assert validate("part-values", doc) == []
    places: list[tuple[Any, ...]] = [
        (),
        ("rows", 0),
        ("rows", 0, "view"),  # heading_entry
        ("rows", 1, "view"),  # bbox
        ("rows", 0, "cites"),
        ("rows", 2, "cites", "geometry"),
        ("rows", 2, "hand_sum"),
        ("rows", 2, "hand_sum", "terms", 0),  # {finding, of}
        ("rows", 1, "hand_sum", "terms", 0),  # {marks}
        ("rows", 2, "hand_sum", "terms", 2),  # {entry}
    ]
    for place in places:
        stray = copy.deepcopy(doc)
        node: Any = stray
        for step in place:
            node = node[step]
        node["unknown_key"] = 1
        assert validate("part-values", stray), place
    shapes = {
        "mark and subject": lambda d: d["rows"][0].update(subject="piles"),
        "neither mark nor subject": lambda d: d["rows"][0].pop("mark"),
        "sheet without file": lambda d: d["rows"][3].update(sheet="model#05"),
        "bad row id": lambda d: d["rows"][0].update(row="R1"),
        "unknown field": lambda d: d["rows"][0].update(field="width"),
        "unknown state": lambda d: d["rows"][0].update(state="guessed"),
        "empty value": lambda d: d["rows"][0].update(value=""),
        "value too long": lambda d: d["rows"][0].update(value="x" * 301),
        "no value key": lambda d: d["rows"][0].pop("value"),
        "bad finding id": lambda d: d["rows"][0]["cites"].update(findings=["F-1"]),
        "bad question id": lambda d: d["rows"][0]["cites"].update(questions=["Q-1"]),
        "bad entry id": lambda d: d["rows"][0]["cites"].update(entries=["T1"]),
        "bad geometry source": lambda d: d["rows"][2]["cites"]["geometry"].update(source="x/a.json"),
        "geometry without items": lambda d: d["rows"][2]["cites"]["geometry"].update(items=[]),
        "empty terms": lambda d: d["rows"][1]["hand_sum"].update(terms=[]),
        "term of two kinds": lambda d: d["rows"][1]["hand_sum"]["terms"][0].update(entry="T000001"),
        "part mismatch is not the schema's": lambda d: d.update(part="bad part"),
    }
    for name, mutate in shapes.items():
        broken = copy.deepcopy(doc)
        mutate(broken)
        assert validate("part-values", broken), name
    assert example_schema("part-values")["$id"].endswith("part-values:0.1")


def test_the_example_shows_every_shape_of_the_schema():
    doc = example_values()
    rows = doc["rows"]
    assert {r["state"] for r in rows} == {"seen", "asked", "unread", "absent"}
    assert any("subject" in r for r in rows) and any("mark" in r for r in rows)
    assert any("geometry" in r.get("cites", {}) for r in rows) and any("note" in r for r in rows)
    views = [r["view"] for r in rows if "view" in r]
    assert any("heading_entry" in v for v in views) and any("bbox" in v for v in views)
    terms = [t for r in rows for t in r.get("hand_sum", {}).get("terms", [])]
    assert any("finding" in t for t in terms) and any("marks" in t for t in terms)
    assert any("entry" in t for t in terms)
    assert any(r.get("sheet", "x") is None for r in rows)


# --- values_invalid and the stops ---------------------------------------------------------------------------


def test_missing_values_problem_not_for_bookkeeping(capsys, work):
    write_values(work, None)
    code, doc, _ = run_check(capsys, work)
    assert code == 1 and problems(doc) == [("values_invalid", None, None)]
    assert (
        doc
        and "values.json" in doc["problems"][0]["detail"]
        and str(work) not in doc["problems"][0]["detail"]
    )
    assert doc["counts"] == {k: 0 for k in doc["counts"]}
    for part in ("scout", "all-assembly"):  # kind bookkeeping: no file is zero rows
        code, doc, err = run_check(capsys, work, part)
        assert (code, err) == (0, "") and doc
        assert doc["ok"] and doc["counts"]["rows"] == 0 and doc["problems"] == []
    write_values(work, [], "scout")  # a file that is there is read like any other
    write_values(work, [row()], "scout")
    code, doc, _ = run_check(capsys, work, "scout")
    assert code == 1 and "row_outside_part" in [p[0] for p in problems(doc)]  # read like any other file


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        '{"schema_version": "0.1", "part": "B1-caps", "rows": [], "rows": []}',  # duplicate key
        '{"schema_version": "0.1", "part": "B1-caps", "rows": [{"row": "R001"}]}',  # schema
        '{"schema_version": "0.2", "part": "B1-caps", "rows": []}',
    ],
)
def test_values_invalid_cases(capsys, work, text):
    write_values(work, text)
    code, doc, _ = run_check(capsys, work)
    assert code == 1 and problems(doc) == [("values_invalid", None, None)]
    assert doc and str(work) not in doc["problems"][0]["detail"]


def test_values_of_another_part_is_invalid(capsys, work):
    """The file's `part` must be the checked part: a copy of B1-piles's file in B1-caps's folder."""
    write_values(work, [row()], PART, doc_part=INPUT_PART)
    code, doc, _ = run_check(capsys, work)
    assert code == 1 and problems(doc) == [("values_invalid", None, None)]
    assert doc and INPUT_PART in doc["problems"][0]["detail"]


def test_values_that_is_not_a_regular_file_is_invalid(capsys, work):
    path = write_values(work, None)
    path.mkdir()
    code, doc, _ = run_check(capsys, work)
    assert code == 1 and problems(doc) == [("values_invalid", None, None)]


def test_unknown_part_1_bad_id_2_no_manifest_invalid(capsys, work):
    code, doc, _ = run_check(capsys, work, "B9-nothing")
    assert code == 1 and problems(doc) == [("part_unknown", None, "B9-nothing")]
    assert doc and doc["part"] == "B9-nothing" and doc["counts"]["rows"] == 0
    for bad in ("bad id!", "-x", "x" * 65):
        code, doc, err = run_check(capsys, work, bad)
        assert (code, doc) == (2, None) and "--part" in err
    put_manifest(work, None)
    code, doc, _ = run_check(capsys, work)
    assert code == 1 and problems(doc) == [("manifest_invalid", None, None)]
    assert doc and "manifest.json" in doc["problems"][0]["detail"]
    broken = part_manifest(work)
    del broken["parts"][0]["order"]
    put_manifest(work, broken)
    code, doc, _ = run_check(capsys, work)
    assert code == 1 and problems(doc) == [("manifest_invalid", None, None)]
    assert doc and "order" in doc["problems"][0]["detail"]
    put_manifest(work, "{")
    code, doc, _ = run_check(capsys, work)
    assert code == 1 and problems(doc) == [("manifest_invalid", None, None)]


def test_no_work_folder_or_inventory_is_a_usage_error(capsys, work, tmp_path):
    code, doc, err = run_check(capsys, tmp_path / "missing")
    assert (code, doc) == (2, None) and err
    (work / "inventory.json").unlink()
    code, doc, err = run_check(capsys, work)
    assert (code, doc) == (2, None) and "inventory.json" in err


@needs_permissions
def test_manifest_access_error_exits_3(capsys, work):
    path = work / MANIFEST
    path.chmod(0)
    try:
        code, doc, err = run_check(capsys, work)
    finally:
        path.chmod(0o644)
    assert (code, doc) == (3, None) and "manifest.json" in err and "Traceback" not in err


@needs_permissions
@pytest.mark.parametrize(
    "name",
    ["parts/B1-caps/values.json", "reader-findings.json", "reader-questions.json", "question-registry.json"],
)
def test_an_unreadable_input_is_exit_3(capsys, work, name):
    write_values(work, [row()])
    path = work / name
    path.chmod(0)
    try:
        code, doc, err = run_check(capsys, work)
    finally:
        path.chmod(0o644)
    assert (code, doc) == (3, None) and Path(name).name in err and "Traceback" not in err


@pytest.mark.parametrize("text", ["{", "[]", '{"schema_version": "0.1"}'])
@pytest.mark.parametrize(
    "name", ["reader-findings.json", "reader-questions.json", "question-registry.json", "marks.json"]
)
def test_a_malformed_record_document_is_the_stop_problem_input_invalid(capsys, work, name, text):
    """E5 review 1, D2: a tool-written document that is not JSON or fails its schema is a JSON answer with
    exit 1 (never exit 1 with nothing on stdout); the detail names the file; no hash, counts of zero."""
    write_values(work, [row()])
    (work / name).write_text(text, encoding="utf-8")
    code, doc, err = run_check(capsys, work)
    assert code == 1 and doc and problems(doc) == [("input_invalid", None, None)]
    assert name in doc["problems"][0]["detail"] and "Traceback" not in err
    assert doc["hash"] is None and doc["ok"] is False and doc["counts"]["rows"] == 0
    assert validate("part-output", doc) == []


def test_a_malformed_grid_systems_document_is_input_invalid(capsys, work):
    write_values(work, [row(cites={"grid_systems": ["S001"]})])
    (work / "grid-systems.json").write_text("{", encoding="utf-8")
    code, doc, _ = run_check(capsys, work)
    assert code == 1 and doc and problems(doc) == [("input_invalid", None, None)]
    assert "grid-systems.json" in doc["problems"][0]["detail"]


def test_a_malformed_record_document_does_not_hide_values_invalid(capsys, work):
    """`values_invalid` is raised before the records are read; its hash needs them, so it is null then and the
    answer is still JSON (exit 1 with no JSON never happens)."""
    write_values(work, None)
    (work / "reader-questions.json").write_text("{", encoding="utf-8")
    code, doc, _ = run_check(capsys, work)
    assert code == 1 and doc and problems(doc) == [("values_invalid", None, None)] and doc["hash"] is None
    assert validate("part-output", doc) == []


# --- row checks --------------------------------------------------------------------------------------------


def test_a_valid_file_is_ok(capsys, work):
    write_values(
        work,
        [
            row(),
            row(
                "R002",
                mark="K-2",
                field="level_top",
                value=None,
                state="asked",
                cites={"questions": ["Q-004"]},
            ),
        ],
    )
    code, doc, err = run_check(capsys, work)
    assert (code, err) == (0, "") and doc
    assert doc["ok"] and doc["problems"] == [] and doc["counts"]["rows"] == 2


def test_row_duplicate(capsys, work):
    rows = [
        row("R001"),
        row("R001", mark="K-2"),  # the row id again
        row("R002"),  # the key of R001 again: file, sheet, mark, field
        row("R003", field="thickness"),  # another field: fine
        row("R004", sheet="model#01", subject="K-1", mark="<drop>"),  # a subject is not a mark
    ]
    write_values(work, rows)
    code, doc, _ = run_check(capsys, work)
    dups = [p for p in doc["problems"] if p["code"] == "row_duplicate"] if doc else []
    assert code == 1 and [(p["code"], p["row"], p["id"]) for p in dups] == [
        ("row_duplicate", "R001", None),
        ("row_duplicate", "R002", None),
    ]
    assert "R001" in dups[1]["detail"]
    # the same mark and field on another sheet, or with another file, is a different key
    write_values(
        work,
        [
            row("R001"),
            row("R002", sheet="model#02"),
            row("R003", sheet=None, state="asked", value=None, cites={"questions": ["Q-003"]}),
        ],
    )
    code, doc, _ = run_check(capsys, work)
    assert [p for p in problems(doc) if p[0] == "row_duplicate"] == []


@pytest.mark.parametrize(
    ("fields", "ok"),
    [
        ({}, True),
        ({"cites": {"entries": ["T000041"]}}, True),
        ({"cites": {"geometry": {"source": "geometry/x.json", "items": ["G-0123456789"]}}}, True),
        ({"cites": {}, "hand_sum": {"terms": [{"marks": "K-1"}]}}, True),
        ({"cites": {"questions": ["Q-003"]}}, False),  # seen with only a question: no source
        ({"cites": {}}, False),
        ({"value": None}, False),
        ({"file": "<drop>", "sheet": "<drop>"}, False),
        ({"state": "asked", "value": None, "cites": {"questions": ["Q-003"]}}, True),
        ({"state": "asked", "value": "1500x2400", "cites": {"questions": ["Q-003"]}}, True),
        ({"state": "asked", "value": None, "cites": {"findings": ["F-001"]}}, False),
        ({"state": "unread", "value": None, "cites": {"questions": ["Q-003"]}}, True),
        ({"state": "unread", "value": "1", "cites": {"questions": ["Q-003"]}}, False),
        ({"state": "unread", "value": None, "cites": {}}, False),
        ({"state": "absent", "value": None, "cites": {"findings": ["F-001"]}}, True),
        ({"state": "absent", "value": None, "cites": {"questions": ["Q-003"]}}, True),
        ({"state": "absent", "value": None, "cites": {"entries": ["T000041"]}}, False),
        ({"state": "absent", "value": "1", "cites": {"findings": ["F-001"]}}, False),
    ],
)
def test_state_rules(capsys, work, fields, ok):
    write_values(work, [row(**fields)])
    code, doc, _ = run_check(capsys, work)
    # only the row_state problems: a valid case may still raise a problem of another check (a citation to
    # a document the fixture does not hold, a number no source backs)
    found = [p for p in problems(doc) if p[0] == "row_state"]
    assert found == ([] if ok else [("row_state", "R001", None)])
    if found:
        assert code == 1


def test_state_rules_name_every_reason(capsys, work):
    write_values(work, [row(value=None, cites={}, file="<drop>", sheet="<drop>")])
    _, doc, _ = run_check(capsys, work)
    state = [p for p in doc["problems"] if p["code"] == "row_state"] if doc else []
    assert len(state) == 1
    detail = state[0]["detail"]
    assert "value" in detail and "file" in detail and "finding, entry, geometry or hand_sum" in detail


def test_row_outside_part(capsys, work):
    rows = [
        row("R001"),  # a sheet of the part
        row("R002", mark="K-2", sheet="model#02"),  # a sheet only the input part lists
        row("R003", mark="K-3", sheet="model#09"),  # a sheet nobody lists
        row("R004", mark="K-4", file="other.dxf"),
        row("R005", mark="K-5", sheet=None),  # the part lists a cluster outside every frame
        row("R006", mark="K-6", view={"heading_entry": entry_ids(work)["K-1"]}),  # a listed view
        row("R007", mark="K-7", view={"bbox": [0, 0, 1000, 500]}),  # a listed view
        row("R008", mark="K-8", view={"heading_entry": "T999999"}),  # a view the manifest does not list
        row("R009", mark="K-9", file="<drop>", sheet="<drop>", cites={"entries": ["T000041"]}, state="seen"),
    ]
    write_values(work, rows)
    code, doc, _ = run_check(capsys, work)
    outside = [p[1] for p in problems(doc) if p[0] == "row_outside_part"]
    assert outside == ["R002", "R003", "R004", "R008"] and code == 1
    r002 = (
        [p for p in doc["problems"] if p["code"] == "row_outside_part" and p["row"] == "R002"] if doc else []
    )
    assert len(r002) == 1 and "input part" in r002[0]["detail"]
    # without the cluster, a file with no sheet is outside too
    manifest = part_manifest(work)
    next(p for p in manifest["parts"] if p["id"] == PART)["clusters"] = []
    put_manifest(work, manifest)
    write_values(work, [row("R001", sheet=None), row("R002", mark="K-2", file="<drop>", sheet="<drop>")])
    _, doc, _ = run_check(capsys, work)
    assert [p[1] for p in problems(doc) if p[0] == "row_outside_part"] == ["R001"]


def test_row_outside_part_scope_of_a_table_and_a_table_cluster(capsys, work):
    manifest = part_manifest(work)
    part = next(p for p in manifest["parts"] if p["id"] == PART)
    ids = entry_ids(work)
    part["tables"] = [
        {"file": REL, "sheet": "model#02", "header_entries": [ids["P-1"]]},
        {"cluster": {"file": REL, "sheet": "model#03", "side": "below"}, "header_entries": [ids["P-1"]]},
    ]
    put_manifest(work, manifest)
    write_values(
        work,
        [
            row("R001", sheet="model#02"),
            row("R002", mark="K-2", sheet="model#03"),
            row("R003", mark="K-3", sheet="model#04"),
        ],
    )
    _, doc, _ = run_check(capsys, work)
    assert [p[1] for p in problems(doc) if p[0] == "row_outside_part"] == ["R003"]


# --- the output --------------------------------------------------------------------------------------------


def test_rule_hook_merged(capsys, work, monkeypatch):
    write_values(work, [row()])
    part_values = mod("part_values")
    hooks = {
        "part_cites": ("cite_problems", "cite_unknown"),
        "part_numbers": ("number_problems", "number_unbacked"),
        "part_sums": ("sum_problems", "hand_sum_mismatch"),
        "part_rules": ("text_problems", "claim_form"),
    }
    seen: list[Any] = []
    for module, (name, code) in hooks.items():

        def hook(ctx: Any, code: str = code) -> list[Any]:
            seen.append(ctx)
            return [part_values.Problem(code, "R001", "Z-9", f"from the {code} hook")]

        monkeypatch.setattr(mod(module), name, hook)
    code, doc, _ = run_check(capsys, work)
    assert code == 1 and doc and not doc["ok"]
    assert [p["code"] for p in doc["problems"]] == sorted(c for _, c in hooks.values())
    assert all(isinstance(ctx, part_values.PartContext) for ctx in seen) and len(seen) == 4
    assert validate("part-output", doc) == []
    # merged with a row problem, then sorted as one list
    write_values(work, [row(value=None)])
    _, doc, _ = run_check(capsys, work)
    codes = [p["code"] for p in doc["problems"]] if doc else []
    assert codes == sorted(codes) and "row_state" in codes and "claim_form" in codes


def test_valid_part_with_real_citations_is_clean(capsys, work, base_work):
    """Every kind of citation at once, each real: a saved geometry document, a finding, an entry and a true
    hand sum over the marks of marks.json. Every check accepts it: exit 0 and no problem."""
    inputs = str(base_work.parent / "input")
    code = main(
        ["geometry", str(work), REL, "--sheet", "model#01", "--detail", "--save", "--input-dir", inputs]
    )
    cap = capsys.readouterr()
    assert code == 0, cap.err
    source = next(line for line in cap.err.splitlines() if line.startswith("saved: ")).removeprefix("saved: ")
    saved = json.loads((work / source).read_text(encoding="utf-8"))
    circle = next(i for r in saved["regions"] for i in r["items"] if i["kind"] == "circle")
    assert main(["marks", str(work)]) == 0
    capsys.readouterr()
    rows = [
        row("R001"),  # cites the finding F-001, whose value is '1500x2400'
        row(
            "R002",
            field="depth",
            value=f"{circle['diameter']:g}",
            cites={"geometry": {"source": source, "items": [circle["id"]]}},
        ),
        entry_row(work, "R003", "level", "K-2", mark="K-2"),
        row(  # one plan mark K-1 on model#01 in marks.json: the sum is true
            "R004",
            mark="<drop>",
            subject="caps",
            field="count_plan",
            value="1",
            cites={},
            hand_sum={"terms": [{"marks": "K-1"}]},
        ),
    ]
    write_values(work, rows)
    code, doc, err = run_check(capsys, work)
    assert doc and doc["problems"] == [], doc
    assert (code, err) == (0, "") and doc["ok"]


def test_output_validates(capsys, work):
    schema = example_schema("part-output")
    codes = schema["$defs"]["check"]["properties"]["problems"]["items"]["properties"]["code"]["enum"]
    pc = mod("part_check")
    assert set(pc.PROBLEM_CODES) == set(codes) and len(pc.PROBLEM_CODES) == len(codes) == 31
    assert "input_invalid" in codes
    rows = [
        row("R001"),
        row("R002", mark="K-2", field="level_top", value=None, state="asked", cites={"questions": ["Q-004"]}),
        row("R003", mark="K-2", field="depth", value=None, state="unread", cites={"questions": ["Q-003"]}),
        row(
            "R004",
            mark="K-2",
            field="size",
            value=None,
            state="absent",
            cites={"findings": ["F-001"], "questions": ["Q-003"]},
        ),
        row("R005", mark="K-3", state="unread", value="5"),  # a problem
    ]
    write_values(work, rows)
    code, doc, _ = run_check(capsys, work)
    assert code == 1 and doc and validate("part-output", doc) == []
    assert doc["counts"] == {
        "rows": 5,
        "seen": 1,
        "asked": 1,
        "unread": 2,
        "absent": 1,
        "findings": 2,
        "questions": 2,
    }
    assert doc["command"] == "check" and doc["part"] == PART and doc["ok"] is False
    assert list(doc["problems"][0]) == ["code", "row", "id", "detail"]
    keys = [(p["code"], p["row"] or "", p["id"] or "", p["detail"]) for p in doc["problems"]]
    assert keys == sorted(keys)
    write_values(work, rows[:4])
    code, doc, err = run_check(capsys, work)
    assert (code, err) == (0, "") and doc and doc["ok"] and doc["problems"] == []
    # a withdrawn finding and a withdrawn question are not counted
    from tekla_harness.ask import withdraw_question
    from tekla_harness.findings import withdraw_finding

    withdraw_finding(work, "F-002", "test", part=PART)
    withdraw_question(work, "Q-003", "test", part=PART)
    _, doc, _ = run_check(capsys, work)
    assert doc and doc["counts"]["findings"] == 1 and doc["counts"]["questions"] == 1


def test_the_part_output_stays_a_discriminated_union(capsys, work):
    write_values(work, [row()])
    _, doc, _ = run_check(capsys, work)
    assert doc and validate("part-output", doc) == []
    doc["extra"] = 1
    assert validate("part-output", doc)
    del doc["extra"]
    doc["problems"] = [{"code": "no_such_code", "row": None, "id": None, "detail": "x"}]
    assert validate("part-output", doc)
    doc["problems"] = [{"code": "row_state", "row": None, "id": None}]  # no detail
    assert validate("part-output", doc)


def test_manifest_check_carries_command(capsys, work):
    code = main(["part", "manifest-check", str(work)])
    out = json.loads(capsys.readouterr().out)
    assert out["command"] == "manifest-check" and code in (0, 1)
    assert validate("part-output", out) == []
    del out["command"]
    assert validate("part-output", out)
    out["command"] = "check"  # the other document's discriminator on this document's shape
    assert validate("part-output", out)


def test_check_writes_nothing(capsys, work):
    write_values(work, [row(), row("R002")])
    before = {p: p.read_bytes() for p in sorted(work.rglob("*")) if p.is_file()}
    run_check(capsys, work)
    run_check(capsys, work, "B9-nothing")
    assert {p: p.read_bytes() for p in sorted(work.rglob("*")) if p.is_file()} == before


def test_the_command_is_read_only_and_takes_no_lock(capsys, work):
    import tekla_harness.cli as cli
    from tekla_harness.worklock import work_lock

    assert cli.LOCKED_ACTIONS["part"] == frozenset({"receipt", "conflicts", "spotcheck", "answer-key"})
    args = build_parser().parse_args(["part", "check", str(work), "--part", PART])
    assert args.command == "part" and args.action == "check" and args.part == PART
    assert cli._lock_target(args) is None
    write_values(work, [row()])
    with work_lock(work, "grid-system"):  # a writer holds the work folder
        assert main(["part", "check", str(work), "--part", PART]) == 0
    capsys.readouterr()


def test_part_is_required(capsys, work):
    assert main(["part", "check", str(work)]) == 2
    assert "--part" in capsys.readouterr().err


def test_load_context_holds_what_the_checks_read(work):
    write_values(work, [row()])
    ctx = mod("part_values").load_context(work, PART)
    ids = entry_ids(work)
    assert ctx.part == PART and ctx.part_row["id"] == PART and [r["row"] for r in ctx.rows] == ["R001"]
    assert ctx.own.sheets == {(REL, "model#01")} and ctx.inputs.sheets == {(REL, "model#02")}
    assert ctx.scope.sheets == {(REL, "model#01"), (REL, "model#02")}
    assert ctx.own.clusters == {(REL, None, "none")} and ctx.inputs.clusters == frozenset()
    assert ctx.views[(REL, "model#01")] == [{"heading_entry": ids["K-1"]}, {"bbox": [0, 0, 1000, 500]}]
    assert sorted(ctx.findings) == ["F-001", "F-002"] and ctx.findings["F-001"]["stale"] is False
    assert {"Q-003", "Q-004", "Q-005"} <= set(ctx.questions) and {"Q-001", "Q-003"} <= set(ctx.registry)
    assert ctx.entries[(REL, ids["1500x2400"])] == ("1500x2400", True, True, "model#01")
    assert ctx.entries[(REL, ids["P-1"])][3] == "model#02"
    assert ids["K-1"] in ctx.sheet_entries[(REL, "model#01")]
    assert ctx.cluster_entries.get((REL, None, "none"), frozenset()) == frozenset()
    assert ctx.marks is None and ctx.saved == {}
    with pytest.raises(AttributeError):  # frozen
        ctx.part = "x"  # type: ignore[misc]


def test_check_output_carries_the_part_hash(capsys, work):
    receipts = mod("part_receipts")
    write_values(work, [row()])
    code, doc, _ = run_check(capsys, work)
    manifest = json.loads((work / "parts" / "manifest.json").read_text(encoding="utf-8"))
    assert code == 0 and doc and doc["hash"] == receipts.part_hash(work, manifest, PART)
    assert validate("part-output", doc) == []
    write_values(
        work, [row(), row("R002", field="thickness", value="foundation", cites={"findings": ["F-002"]})]
    )
    _, changed, _ = run_check(capsys, work)  # the hash is the part's, not the check's: new bytes, new hash
    assert changed and changed["hash"] != doc["hash"]
    del changed["hash"]  # the document requires it
    assert validate("part-output", changed)
    # a problem does not hide it, and `values_invalid` (the file is missing) still has one
    write_values(work, [row(state="unread")])
    code, doc, _ = run_check(capsys, work)
    assert code == 1 and doc and doc["hash"] == receipts.part_hash(work, manifest, PART)
    write_values(work, None)
    code, doc, _ = run_check(capsys, work)
    assert code == 1 and doc and problems_codes(doc) == ["values_invalid"]
    assert doc["hash"] == receipts.part_hash(work, manifest, PART)
    path = write_values(work, None)
    path.mkdir()  # not a regular file: still a hash, and no hang
    _, doc, _ = run_check(capsys, work)
    assert doc and doc["hash"] == receipts.part_hash(work, manifest, PART)


def problems_codes(doc: dict[str, Any]) -> list[str]:
    return [p["code"] for p in doc["problems"]]


def test_check_hash_is_null_when_the_manifest_or_the_part_is_missing(capsys, work):
    _, doc, _ = run_check(capsys, work, "B9-nothing")
    assert doc and problems_codes(doc) == ["part_unknown"] and doc["hash"] is None
    assert validate("part-output", doc) == []
    put_manifest(work, "not json")
    _, doc, _ = run_check(capsys, work)
    assert doc and problems_codes(doc) == ["manifest_invalid"] and doc["hash"] is None
    assert validate("part-output", doc) == []
