"""The citation checks of `harness part check` (`part_cites`, E5a): every id a row of `values.json` cites
exists, is active, is fresh, belongs to the part or its inputs, and every cited entry is printed, readable and
inside the part's scope.

The work folder is the real intake of `_part_fixtures.build_part_work`, plus two texts outside the frames
(`OUT-1` right of sheet 2, `OUT-2` left of sheet 1: the unassigned clusters `(REL, model#02, right)` and
`(REL, model#01, left)`). Each test copies it and changes one thing. Only the codes of this module are
compared.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from _part_fixtures import (
    INPUT_PART,
    PART,
    REL,
    TEXTS,
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
from tekla_harness.ask import ask_question, withdraw_question
from tekla_harness.cli import main
from tekla_harness.findings import add_finding, withdraw_finding

Triple = tuple[str, str | None, str | None]


@pytest.fixture(scope="module")
def base_work(tmp_path_factory) -> Path:
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(TEXTS, "OUT-1", (200000, 50000))
        patch.setitem(TEXTS, "OUT-2", (-30000, 50000))
        return build_part_work(tmp_path_factory.mktemp("partcites"))


@pytest.fixture
def work(base_work, tmp_path) -> Path:
    target = tmp_path / "work"
    shutil.copytree(base_work, target)
    return target


def cite_codes(doc: dict[str, Any] | None) -> list[Triple]:
    """The problems of this module: `cite_*` and `entry_*`."""
    return [p for p in problems(doc) if p[0].startswith(("cite_", "entry_"))]


def edit_json(path: Path, change: Any) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    change(doc)
    path.write_text(json.dumps(doc), encoding="utf-8")


def seen(row_id: str, field: str, **cites: Any) -> dict[str, Any]:
    """A `seen` row of K-1 on the part's own sheet that cites `cites` (the field keeps the row keys apart)."""
    return row(row_id, field=field, cites=cites)


def test_cited_ids_unknown_inactive_stale(capsys, work):
    rows = [
        row("R001", cites={"findings": ["F-099"], "questions": ["Q-099"], "entries": ["T999999"]}),
        # F-002 backs the value 'foundation' (a sheet_class finding), F-001 backs '1500x2400'
        row(
            "R002",
            field="thickness",
            value="foundation",
            cites={"findings": ["F-002"], "questions": ["Q-004"]},
        ),
        row("R003", field="depth", cites={"findings": ["F-001"], "questions": ["Q-003"]}),
    ]
    write_values(work, rows[1:])
    code, doc, err = run_check(capsys, work)
    assert (code, err) == (0, "") and doc and doc["problems"] == []  # active, fresh, the part's own
    write_values(work, rows)
    withdraw_finding(work, "F-002", "test", part=PART)
    withdraw_question(work, "Q-004", "test", part=PART)
    code, doc, _ = run_check(capsys, work)
    assert code == 1 and cite_codes(doc) == [
        ("cite_inactive", "R002", "F-002"),
        ("cite_inactive", "R002", "Q-004"),
        ("cite_unknown", "R001", "F-099"),
        ("cite_unknown", "R001", "Q-099"),
        ("cite_unknown", "R001", "T999999"),
    ]
    # a withdrawn reader question is gone from reader-questions.json: inactive only, never also foreign
    assert doc and all(p["code"] != "cite_foreign_part" for p in doc["problems"])
    # the drawing changed after F-001 was recorded: stale (and so is the withdrawn F-002)
    edit_json(
        work / "reader-findings.json",
        lambda d: [f.update(file_sha256="0" * 64) for f in d["findings"]],
    )
    code, doc, _ = run_check(capsys, work)
    assert code == 1 and cite_codes(doc) == [
        ("cite_inactive", "R002", "F-002"),
        ("cite_inactive", "R002", "Q-004"),
        ("cite_stale", "R002", "F-002"),
        ("cite_stale", "R003", "F-001"),
        ("cite_unknown", "R001", "F-099"),
        ("cite_unknown", "R001", "Q-099"),
        ("cite_unknown", "R001", "T999999"),
    ]
    stale = [p for p in doc["problems"] if p["code"] == "cite_stale" and p["id"] == "F-001"] if doc else []
    assert stale and "drawing" in stale[0]["detail"]


def test_geometry_id_unknown(capsys, work, base_work):
    inputs = str(base_work.parent / "input")
    code = main(
        ["geometry", str(work), REL, "--sheet", "model#01", "--detail", "--save", "--input-dir", inputs]
    )
    cap = capsys.readouterr()
    assert code == 0, cap.err
    source = next(line for line in cap.err.splitlines() if line.startswith("saved: ")).removeprefix("saved: ")
    ids = [i["id"] for r in json.loads(cap.out)["regions"] for i in r.get("items", [])]
    assert ids, "the fixture drawing must give the geometry document at least one item"
    missing = "G-0000000000"
    assert missing not in ids
    rows = [
        seen("R001", "size", geometry={"source": source, "items": [ids[0]]}),
        seen("R002", "thickness", geometry={"source": source, "items": [ids[0], missing]}),
        seen("R003", "depth", geometry={"source": "geometry/not-saved.json", "items": ["G-0123456789"]}),
        seen("R004", "length", geometry={"source": source, "items": [missing]}),
    ]
    write_values(work, rows)
    code, doc, _ = run_check(capsys, work)
    assert code == 1 and cite_codes(doc) == [
        ("cite_unknown", "R002", missing),
        ("cite_unknown", "R003", "G-0123456789"),
        ("cite_unknown", "R004", missing),
    ]
    details = {p["row"]: p["detail"] for p in doc["problems"] if p["code"] == "cite_unknown"} if doc else {}
    assert source in details["R002"] and "geometry/not-saved.json" in details["R003"]
    # a saved file that is not a geometry or contents document is as good as no file
    edit_json(work / source, lambda d: d.update(kind="other"))
    _, doc, _ = run_check(capsys, work)
    assert {p[1] for p in cite_codes(doc)} == {"R001", "R002", "R003", "R004"}


def test_foreign_and_untagged_reader_records_producer_questions_pass(capsys, work):
    ids = entry_ids(work)

    def finding(text: str, part: str) -> str:
        return add_finding(
            work, kind="note_item", file=REL, entries=[ids[text]], value=text, sheet="model#01",
            fields=["topic=other"], part=part,
        )["id"]  # fmt: skip

    untagged_finding = finding("D400", PART)
    input_finding = finding("K-2", INPUT_PART)
    foreign_finding = finding("K-1", "all-assembly")

    def question(code: str, part: str) -> str:
        return ask_question(
            work, code=code, where="model#01 K-2", found="a value", text="Giá trị nào?", file=REL,
            sheet="model#01", blocking=False, part=part,
        )["id"]  # fmt: skip

    untagged_question = question("reader_untagged_unclear", PART)
    foreign_question = question("reader_foreign_unclear", "all-assembly")
    # the two records lose their part tag, as a record written before the tag existed has none
    edit_json(
        work / "reader-findings.json",
        lambda d: [f.pop("part") for f in d["findings"] if f["id"] == untagged_finding],
    )
    edit_json(
        work / "reader-questions.json",
        lambda d: [q.pop("parts") for q in d["questions"] if q["id"] == untagged_question],
    )
    rows = [
        row("R001", cites={"findings": ["F-001", input_finding], "questions": ["Q-003", "Q-005"]}),
        row("R002", field="thickness", cites={"findings": [untagged_finding, foreign_finding]}),
        row("R003", field="depth", cites={"questions": [untagged_question, foreign_question]}),
        # intake's own questions are producer questions: no part, no problem
        row("R004", field="length", cites={"findings": ["F-001"], "questions": ["Q-001", "Q-002"]}),
    ]
    write_values(work, rows)
    code, doc, _ = run_check(capsys, work)
    assert code == 1 and cite_codes(doc) == [
        ("cite_foreign_part", "R002", untagged_finding),
        ("cite_foreign_part", "R002", foreign_finding),
        ("cite_foreign_part", "R003", untagged_question),
        ("cite_foreign_part", "R003", foreign_question),
    ]
    detail = doc["problems"][0]["detail"] if doc else ""
    assert PART in detail  # names the part the record has to belong to
    # a part with no inputs: the input part's records are foreign too
    manifest = part_manifest(work)
    next(p for p in manifest["parts"] if p["id"] == PART).pop("inputs")
    put_manifest(work, manifest)
    write_values(work, rows[:1])
    _, doc, _ = run_check(capsys, work)
    assert cite_codes(doc) == [
        ("cite_foreign_part", "R001", input_finding),
        ("cite_foreign_part", "R001", "Q-005"),
    ]


def test_entry_blocked_not_printed_outside(capsys, work):
    ids = entry_ids(work)

    def mark(index: dict[str, Any]) -> None:
        for e in index["entries"]:
            if e["display_text"] == "K-2":
                e["flags"] = ["legacy_ascii_suspect"]  # meaning may not be taken from it
            if e["display_text"] == "D400":
                e["printed"] = False
                e["not_printed_reasons"] = ["layer_off"]

    edit_json(work / "text" / f"{REL}.json", mark)
    manifest = part_manifest(work)
    next(p for p in manifest["parts"] if p["id"] == PART).pop("inputs")  # sheet 2 is no longer in scope
    put_manifest(work, manifest)
    rows = [
        row("R001", field="size", cites={"entries": [ids["1500x2400"]]}),
        row("R002", field="thickness", cites={"entries": [ids["K-2"]]}),
        row("R003", field="depth", cites={"entries": [ids["D400"]]}),
        row("R004", field="length", cites={"entries": [ids["P-1"]]}),
        row("R005", field="level", file="<drop>", sheet="<drop>", cites={"entries": [ids["K-1"]]}),
        row("R006", field="axes", cites={"entries": [ids["K-2"], ids["1500x2400"]]}),
    ]
    write_values(work, rows)
    code, doc, _ = run_check(capsys, work)
    assert code == 1 and cite_codes(doc) == [
        ("cite_unknown", "R005", ids["K-1"]),  # an entry is an entry of the row's file: no file, no entry
        ("entry_blocked", "R002", ids["K-2"]),
        ("entry_blocked", "R006", ids["K-2"]),
        ("entry_not_printed", "R003", ids["D400"]),
        ("entry_outside_part", "R004", ids["P-1"]),
    ]
    # the input part is listed again: the entry of its sheet is inside
    put_manifest(work, part_manifest(work))
    _, doc, _ = run_check(capsys, work)
    assert [p for p in cite_codes(doc) if p[0] == "entry_outside_part"] == []


def test_cluster_and_input_entries_in_scope(capsys, work):
    ids = entry_ids(work)

    def manifest(own: bool, inputs: bool) -> dict[str, Any]:
        m = part_manifest(work)
        parts = {p["id"]: p for p in m["parts"]}
        parts[PART]["clusters"] = [{"file": REL, "sheet": "model#01", "side": "left"}] if own else []
        if inputs:
            parts[INPUT_PART]["clusters"] = [{"file": REL, "sheet": "model#02", "side": "right"}]
        return m

    rows = [
        entry_row(work, "R001", "size", "K-1"),  # the part's own sheet
        entry_row(work, "R002", "thickness", "P-1"),  # the input part's sheet
        entry_row(work, "R003", "depth", "OUT-2"),  # the part's own cluster
        entry_row(work, "R004", "length", "OUT-1"),  # the input part's cluster
    ]
    write_values(work, rows)
    put_manifest(work, manifest(own=True, inputs=True))
    code, doc, err = run_check(capsys, work)
    assert (code, err) == (0, "") and doc and doc["problems"] == []
    # the input part lists no cluster: its text is outside; the sheets and the own cluster still count
    put_manifest(work, manifest(own=True, inputs=False))
    code, doc, _ = run_check(capsys, work)
    assert code == 1 and cite_codes(doc) == [("entry_outside_part", "R004", ids["OUT-1"])]
    # no cluster at all: both texts are outside, the texts of the sheets are not
    put_manifest(work, manifest(own=False, inputs=False))
    _, doc, _ = run_check(capsys, work)
    assert cite_codes(doc) == [
        ("entry_outside_part", "R003", ids["OUT-2"]),
        ("entry_outside_part", "R004", ids["OUT-1"]),
    ]


def test_cluster_sheet_is_for_rows_only_not_for_cited_entries(capsys, work):
    """D1: a sided cluster opens its own entries and lets a row be written on its sheet, but the other texts
    of that sheet are outside the part (`entry_outside_part`), and the row is not `row_outside_part`."""
    ids = entry_ids(work)
    manifest = part_manifest(work)
    part = next(p for p in manifest["parts"] if p["id"] == PART)
    part.pop("inputs")
    part["sheets"] = []
    part["clusters"] = [{"file": REL, "sheet": "model#02", "side": "below"}]
    put_manifest(work, manifest)
    # '26' sits inside the frame of model#02, not below it: no cluster holds it
    write_values(work, [entry_row(work, "R001", "size", "26", sheet="model#02")])
    code, doc, _ = run_check(capsys, work)
    assert code == 1 and doc
    assert cite_codes(doc) == [("entry_outside_part", "R001", ids["26"])]
    assert [p for p in problems(doc) if p[0] == "row_outside_part"] == []  # a row may be read in the cluster
