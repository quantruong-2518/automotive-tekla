"""`cites.grid_systems[]` of a `part-values` row and its check by `harness part check` (E5a-5).

The work folder is `_part_fixtures.build_part_work`; `grid-systems.json` is the schema example (systems S001
and S002), copied into it. A grid-system cite is a citation only: only the codes `cite_unknown` and
`cite_foreign_part` of the cited system id are compared, whatever else the row raises.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from _part_fixtures import MANIFEST, PART, build_part_work, row, run_check, write_values
from tekla_harness.schemas import validate

EXAMPLES = Path(__file__).resolve().parent.parent / "schemas" / "examples"


@pytest.fixture(scope="module")
def base_work(tmp_path_factory) -> Path:
    return build_part_work(tmp_path_factory.mktemp("partgrid"))


@pytest.fixture
def work(base_work, tmp_path) -> Path:
    target = tmp_path / "work"
    shutil.copytree(base_work, target)
    return target


def put_systems(work: Path, *, block_ids: list[str] | None = None) -> None:
    """Write `grid-systems.json` (the schema example: S001, S002); `block_ids`: `grid_system_ids` of B1."""
    shutil.copy(EXAMPLES / "grid-system.example.json", work / "grid-systems.json")
    if block_ids is not None:
        path = work / MANIFEST
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["blocks"][0]["grid_system_ids"] = block_ids
        path.write_text(json.dumps(doc), encoding="utf-8")


def grid_row(*ids: str, row_id: str = "R002") -> dict[str, Any]:
    """A `seen` row of K-1 that cites F-001 and the grid systems `ids`."""
    return row(row_id, field="spacing", cites={"findings": ["F-001"], "grid_systems": list(ids)})


def grid_codes(doc: dict[str, Any] | None) -> list[tuple[str, str | None, str | None]]:
    """The problems about a cited grid system: `cite_unknown` and `cite_foreign_part` whose id is `S...`."""
    assert doc is not None
    return [
        (p["code"], p["row"], p["id"])
        for p in doc["problems"]
        if p["code"] in ("cite_unknown", "cite_foreign_part") and str(p["id"]).startswith("S")
    ]


def test_known_id_of_the_block_is_clean(capsys, work):
    put_systems(work, block_ids=["S001"])
    write_values(work, [grid_row("S001")])
    code, doc, err = run_check(capsys, work)
    assert (code, err) == (0, "") and grid_codes(doc) == []


def test_unknown_id_and_prefix_of_a_known_one(capsys, work):
    put_systems(work, block_ids=["S001", "S002"])
    # S0010 only starts like S001: it is no system of the file
    write_values(work, [grid_row("S001", "S099", "S0010")])
    code, doc, _ = run_check(capsys, work)
    assert code == 1 and grid_codes(doc) == [
        ("cite_unknown", "R002", "S0010"),
        ("cite_unknown", "R002", "S099"),
    ]
    assert doc and "S099" in next(p["detail"] for p in doc["problems"] if p["id"] == "S099")


def test_id_is_matched_whole_not_by_prefix_of_a_system_of_the_file(capsys, work):
    put_systems(work, block_ids=["S001", "S0020"])
    path = work / "grid-systems.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["systems"][1]["system_id"] = "S0020"  # S002 only starts like S0020
    path.write_text(json.dumps(doc), encoding="utf-8")
    write_values(work, [grid_row("S001", "S002", "S0020")])
    code, doc, _ = run_check(capsys, work)
    assert code == 1 and grid_codes(doc) == [("cite_unknown", "R002", "S002")]


def test_file_absent_every_cited_id_is_unknown(capsys, work):
    assert not (work / "grid-systems.json").exists()
    write_values(work, [grid_row("S001", "S002"), grid_row("S001", row_id="R003")])
    code, doc, _ = run_check(capsys, work)
    assert code == 1 and grid_codes(doc) == [
        ("cite_unknown", "R002", "S001"),
        ("cite_unknown", "R002", "S002"),
        ("cite_unknown", "R003", "S001"),
    ]


def test_system_of_another_block_is_foreign(capsys, work):
    put_systems(work, block_ids=["S001"])
    write_values(work, [grid_row("S001", "S002")])
    code, doc, _ = run_check(capsys, work)
    assert code == 1 and grid_codes(doc) == [("cite_foreign_part", "R002", "S002")]
    # the block of the part's input counts too
    path = work / MANIFEST
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["blocks"].append({"id": "B2", "grid_system_ids": ["S002"], "origin_note": "Block B2"})
    manifest["parts"][1]["block"] = "B2"  # B1-piles, the input of B1-caps
    path.write_text(json.dumps(manifest), encoding="utf-8")
    code, doc, _ = run_check(capsys, work)
    assert grid_codes(doc) == []


def test_part_without_a_block_accepts_any_existing_id(capsys, work):
    put_systems(work, block_ids=[])
    write_values(work, [grid_row("S001", "S002")], "scout")  # bookkeeping, no input, no block
    _, doc, _ = run_check(capsys, work, "scout")
    assert grid_codes(doc) == []
    write_values(work, [grid_row("S001", "S077")], "scout")
    _, doc, _ = run_check(capsys, work, "scout")
    assert grid_codes(doc) == [("cite_unknown", "R002", "S077")]
    # a part whose input has a block is held to it
    write_values(work, [grid_row("S001")], "all-assembly")
    _, doc, _ = run_check(capsys, work, "all-assembly")
    assert grid_codes(doc) == [("cite_foreign_part", "R002", "S001")]


def test_invalid_file_is_input_invalid_only_when_a_row_cites_a_system(capsys, work):
    (work / "grid-systems.json").write_text('{"schema_version": "0.1"}', encoding="utf-8")
    write_values(work, [row("R002", field="spacing")])
    code, doc, err = run_check(capsys, work)
    assert (code, err) == (0, "") and grid_codes(doc) == []  # not read: no row cites a system
    write_values(work, [grid_row("S001")])
    code, doc, err = run_check(capsys, work)
    assert code == 1 and doc is not None  # E5 review 1, D2: the stop problem, JSON on stdout
    assert [p["code"] for p in doc["problems"]] == ["input_invalid"]
    assert "grid-systems.json is invalid (grid-system)" in doc["problems"][0]["detail"]


def test_a_grid_system_cite_backs_nothing(capsys, work):
    put_systems(work, block_ids=["S001"])
    only = row("R002", field="spacing", cites={"grid_systems": ["S001"]})
    write_values(work, [only])
    code, doc, _ = run_check(capsys, work)
    assert code == 1 and doc is not None
    codes = {p["code"] for p in doc["problems"]}
    # `seen` still needs a finding or an entry, and the number 1500 has no source
    assert {"row_state", "number_unbacked"} <= codes
    assert grid_codes(doc) == []


def test_schema_pattern_unique_and_closed_keys():
    def rows(cites: dict[str, Any]) -> dict[str, Any]:
        return {"schema_version": "0.1", "part": PART, "rows": [row("R001", cites=cites)]}

    assert validate("part-values", rows({"grid_systems": ["S001", "S0012"]})) == []
    assert validate("part-values", rows({"grid_systems": ["S1"]}))
    assert validate("part-values", rows({"grid_systems": ["s001"]}))
    assert validate("part-values", rows({"grid_systems": ["S001", "S001"]}))
    assert validate("part-values", rows({"grid_system": ["S001"]}))
    assert validate("part-values", rows({"grid_systems": "S001"}))


def test_example_has_a_grid_system_row():
    doc = json.loads((EXAMPLES / "part-values.example.json").read_text(encoding="utf-8"))
    assert validate("part-values", doc) == []
    last = doc["rows"][-1]
    assert last["subject"] == "grid S001 A-B" and last["cites"]["grid_systems"] == ["S001"]
