"""`harness part manifest-check W`: structural checks of the parts manifest (ADR-0019, E4a).

The work folder is a real `run_intake` of a synthetic DXF with loose text; the sheets document is then
replaced by six synthetic frames (two blocks, notes, grids) and two clusters of loose text. The valid manifest
is the shipped example, so the example and the checks cannot drift apart. Each problem test changes one
thing in it.
"""

from __future__ import annotations

import copy
import importlib
import json
import os
import shutil
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from ezdxf.filemanagement import new

from conftest import EXAMPLES
from tekla_harness.answers import record_answer
from tekla_harness.cli import _lock_target, build_parser, main
from tekla_harness.intake import dump_json, run_intake
from tekla_harness.knowledge import EMPTY_TABLE
from tekla_harness.parts import PART_ID_RE
from tekla_harness.schemas import validate
from tekla_harness.sheet_text import STRUCTURE_DIR, list_sheets, sheet_text
from tekla_harness.worklock import work_lock

REL = "plans/set.dxf"
MANIFEST = Path("parts") / "manifest.json"
# (sheet number, texts); the second text of sheet 2 does not print
SHEET_TEXTS = {
    1: ["s1k1", "s1k2", "s1k3"],
    2: ["s2k1", "s2k2", "s2k3"],
    3: ["s3k1", "s3k2"],
    4: ["s4k1"],
    5: ["s5k1", "s5k2"],
    6: ["s6k1"],
}
PRINTED = {1: 3, 2: 2, 3: 2, 4: 1, 5: 2, 6: 1}


def pm() -> Any:
    """The module under test, imported when a test runs (the red commit has no module yet)."""
    return importlib.import_module("tekla_harness.parts_manifest")


@pytest.fixture(scope="module")
def work(tmp_path_factory) -> Path:
    base = tmp_path_factory.mktemp("parts")
    root = base / "input"
    (root / "plans").mkdir(parents=True)
    doc = new("R2018", setup=True)
    msp = doc.modelspace()
    for n, texts in SHEET_TEXTS.items():
        for k, text in enumerate(texts):
            msp.add_text(text, height=50, dxfattribs={"insert": ((n - 1) * 2000 + 100, 900 - 100 * k)})
    msp.add_text("c-below", height=50, dxfattribs={"insert": (100, -50)})
    msp.add_text("c-none", height=50, dxfattribs={"insert": (-5000, -5000)})
    doc.saveas(root / REL)
    out = base / "work"
    run_intake(root, out, "demo-parts", knowledge=EMPTY_TABLE)
    path = out / "text" / f"{REL}.json"
    index = json.loads(path.read_text(encoding="utf-8"))
    ids = {e["display_text"]: e["id"] for e in index["entries"]}
    for e in index["entries"]:
        if e["id"] == ids["s2k2"]:
            e["printed"] = False
    path.write_text(json.dumps(index), encoding="utf-8")

    def sheet(n: int) -> dict[str, Any]:
        x = (n - 1) * 2000.0
        return {
            "sheet_id": f"model#{n:02d}",
            "space": "model",
            "layout": "Model",
            "coordinate_frame": {"origin": [x, 0.0], "rotation_deg": 0.0},
            "bbox": [x, 0.0, x + 1000.0, 1000.0],
            "detection": {"confidence": "medium", "method": "test"},
            "model_windows": [],
            "text_ids": [ids[t] for t in SHEET_TEXTS[n]],
            "title_block": {"sheet_number": {"value": f"S-{n}01", "confidence": "high"}},
            "duplicate_of": None,
        }

    sheets = {
        "schema_version": "0.1",
        "file": index["file"],
        "sheets": [sheet(n) for n in SHEET_TEXTS],
        "unassigned": {"text_ids": [ids["c-below"], ids["c-none"]], "ambiguous_text_ids": []},
    }
    (out / STRUCTURE_DIR / "plans").mkdir(parents=True)
    (out / STRUCTURE_DIR / f"{REL}.sheets.json").write_text(dump_json(sheets), encoding="utf-8")
    write_grid_systems(out, ["S001", "S002"])
    questions = json.loads((out / "questions.json").read_text(encoding="utf-8"))["questions"]
    (units,) = [q for q in questions if q["code"] == "units_confirm_all" and q["file"] == REL]
    record_answer(out, units["id"], "mm", "A. Nguyen", {"unit": "mm"}, role="engineer")
    return out


def write_grid_systems(work: Path, system_ids: list[str]) -> None:
    """A schema-valid grid-systems.json that holds `system_ids` (the shipped example, systems renamed)."""
    doc = json.loads((EXAMPLES / "grid-system.example.json").read_text(encoding="utf-8"))
    doc["systems"] = [{**doc["systems"][0], "system_id": sid} for sid in system_ids]
    assert validate("grid-system", doc) == []
    (work / "grid-systems.json").write_text(json.dumps(doc), encoding="utf-8")


def shipped_manifest() -> dict[str, Any]:
    return json.loads((EXAMPLES / "parts-manifest.example.json").read_text(encoding="utf-8"))


def example_manifest() -> dict[str, Any]:
    """The shipped example without its acks and its `files[]`: the acks name warnings that this work folder
    does not raise, and the file `files[]` names is no skipped file of it (`files_entry_unused`)."""
    manifest = shipped_manifest()
    del manifest["acks"]
    del part(manifest, "all-no-sheet")["files"]
    return manifest


def part(manifest: dict[str, Any], part_id: str) -> dict[str, Any]:
    return next(p for p in manifest["parts"] if p["id"] == part_id)


def sheet_ref(sheet: str, role: str = "plan") -> dict[str, Any]:
    return {"file": REL, "sheet": sheet, "role": role}


def put(work: Path, manifest: dict[str, Any] | str | None) -> None:
    path = work / MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    if manifest is None:
        path.unlink(missing_ok=True)
    else:
        path.write_text(manifest if isinstance(manifest, str) else json.dumps(manifest), encoding="utf-8")


def check(capsys, work: Path, manifest: dict[str, Any] | str | None) -> tuple[int, dict[str, Any], str]:
    put(work, manifest)
    code = main(["part", "manifest-check", str(work)])
    cap = capsys.readouterr()
    return code, json.loads(cap.out), cap.err


def keys(out: dict[str, Any]) -> list[tuple[Any, ...]]:
    return [(p["code"], p["part"], p["file"], p["sheet"]) for p in out["problems"]]


def problems_of(capsys, work: Path, mutate: Callable[[dict[str, Any]], None]) -> list[tuple[Any, ...]]:
    manifest = example_manifest()
    mutate(manifest)
    code, out, _ = check(capsys, work, manifest)
    assert validate("part-output", out) == []
    assert out["ok"] is False and code == 1
    return keys(out)


@pytest.fixture
def copied(work, tmp_path) -> Path:
    """A copy of the work folder a test may damage."""
    target = tmp_path / "copy"
    shutil.copytree(work, target)
    return target


# --- the valid manifest ------------------------------------------------------------------------------------


def test_example_validates_against_its_schema():
    assert validate("parts-manifest", shipped_manifest()) == []


def test_valid_two_block_manifest_is_ok(capsys, work):
    code, out, err = check(capsys, work, example_manifest())
    assert (code, err) == (0, "")
    assert out == {
        "command": "manifest-check",
        "ok": True,
        "sheets": {"total": 6, "covered": 6},
        "parts": 10,
        "problems": [],
        "warnings": [],
        # no grids document: nothing can be tested; the cap plans are model#01 and model#03
        "skipped": [
            {"code": code, "file": REL, "sheet": sheet, "reason": "no_grids_document"}
            for sheet, code in (
                ("model#01", "grid_origin_other_block"),
                ("model#01", "linework_duplicate"),
                ("model#02", "grid_origin_other_block"),
                ("model#03", "grid_origin_other_block"),
                ("model#03", "linework_duplicate"),
                ("model#04", "grid_origin_other_block"),
            )
        ],
    }
    assert validate("part-output", out) == []


def test_ack_needs_a_question_or_a_reason():
    manifest = example_manifest()
    manifest["acks"] = [{"warning": "linework_duplicate"}]
    assert validate("parts-manifest", manifest)


def test_a_part_without_order_is_a_schema_problem_that_names_order(capsys, work):
    manifest = example_manifest()
    drop_order(manifest)
    assert validate("parts-manifest", manifest)
    code, out, _ = check(capsys, work, manifest)
    assert code == 1 and [p["code"] for p in out["problems"]] == ["schema"]
    assert "order" in out["problems"][0]["detail"]


def test_the_schema_id_pattern_is_the_one_of_the_shared_rule():
    schema = json.loads((EXAMPLES.parent / "parts-manifest.schema.json").read_text(encoding="utf-8"))
    assert schema["$defs"]["part_id"]["pattern"] == PART_ID_RE.pattern


def test_the_example_shows_every_shape_of_the_schema():
    manifest = shipped_manifest()
    parts = manifest["parts"]
    views = [v for p in parts for s in p.get("sheets", []) for v in s.get("views", [])]
    tables = [t for p in parts for t in p.get("tables", [])]
    assert any("heading_entry" in v for v in views) and any("bbox" in v for v in views)
    assert any("sheet" in t for t in tables) and any("cluster" in t for t in tables)
    assert any(c["sheet"] is None for p in parts for c in p.get("clusters", []))
    assert any("question" in a for a in manifest["acks"]) and any("reason" in a for a in manifest["acks"])
    for field in (
        "split_of",
        "expected_sources",
        "producer_questions",
        "marks_regex",
        "layers",
        "inputs",
        "files",
    ):
        assert any(field in p for p in parts), field
    assert {p["kind"] for p in parts} == {"cross", "member", "no_sheet", "bookkeeping"}


def test_part_output_rejects_a_stray_key(capsys, work):
    _, out, _ = check(capsys, work, example_manifest())
    out["extra"] = 1
    assert validate("part-output", out)
    del out["extra"]
    out["problems"] = [{"code": "schema", "part": None, "file": None, "sheet": None}]  # no detail
    assert validate("part-output", out)
    row = {"code": "schema", "part": None, "file": None, "sheet": None, "detail": "x"}
    out["problems"] = [row]
    assert validate("part-output", out) == []
    out["problems"] = [{**row, "extra": 1}]
    assert validate("part-output", out)


# --- printed counts ----------------------------------------------------------------------------------------


def test_printed_count_is_sheet_text_matched_with_no_filter(work):
    counts = pm().sheet_printed_counts(work)
    assert counts == {(REL, f"model#{n:02d}"): c for n, c in PRINTED.items()}
    for (file, sheet), n in counts.items():
        assert sheet_text(work, file, sheet)["counts"]["matched"] == n
    assert sheet_text(work, REL, "model#02", include_hidden=True)["counts"]["matched"] == 3


def test_sheets_are_the_ones_list_sheets_prints(work):
    listed = {(f["path"], s["sheet_id"]) for f in list_sheets(work)["files"] for s in f["sheets"]}
    assert set(pm().sheet_printed_counts(work)) == listed


# --- one test per problem code -----------------------------------------------------------------------------


def test_schema_problem_for_a_missing_manifest(capsys, work):
    code, out, err = check(capsys, work, None)
    assert code == 1 and out["ok"] is False
    assert out["problems"][0]["code"] == "schema" and out["problems"][0]["part"] is None
    assert "manifest.json" in out["problems"][0]["detail"] and err
    assert validate("part-output", out) == []


def test_schema_problem_for_an_unparsable_manifest(capsys, work):
    code, out, _ = check(capsys, work, "{not json")
    assert code == 1 and out["problems"][0]["code"] == "schema"
    assert "JSON" in out["problems"][0]["detail"]


def test_schema_problem_for_a_manifest_that_is_not_an_object(capsys, work):
    code, out, _ = check(capsys, work, "[]")
    assert code == 1 and [p["code"] for p in out["problems"]] == ["schema"]


EXTRA_FIELD_PLACES: list[tuple[str, Callable[[dict[str, Any]], dict[str, Any]]]] = [
    ("top", lambda m: m),
    ("block", lambda m: m["blocks"][0]),
    ("part", lambda m: part(m, "ALPHA-piles")),
    ("sheet", lambda m: part(m, "ALPHA-piles")["sheets"][0]),
    ("view", lambda m: part(m, "ALPHA-piles")["sheets"][0]["views"][0]),
    ("table", lambda m: part(m, "ALPHA-caps")["tables"][0]),
    ("cluster", lambda m: part(m, "ALPHA-piles")["clusters"][0]),
    ("layers", lambda m: part(m, "ALPHA-piles")["layers"]),
]


@pytest.mark.parametrize(("name", "place"), EXTRA_FIELD_PLACES, ids=[n for n, _ in EXTRA_FIELD_PLACES])
def test_an_extra_field_anywhere_is_a_schema_problem(capsys, work, name, place):
    manifest = example_manifest()
    place(manifest)["value"] = "4 piles"
    assert validate("parts-manifest", manifest)
    code, out, _ = check(capsys, work, manifest)
    assert code == 1 and out["problems"] and {p["code"] for p in out["problems"]} == {"schema"}
    assert "value" in out["problems"][0]["detail"]


def test_an_extra_field_in_an_ack_is_a_schema_problem():
    manifest = example_manifest()
    manifest["acks"] = [{"warning": "x", "reason": "y", "value": 1}]
    assert validate("parts-manifest", manifest)


def drop_order(manifest: dict[str, Any]) -> None:
    del part(manifest, "ALPHA-piles")["order"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m: part(m, "scout").update(kind="expert"),
        lambda m: part(m, "scout").update(id="bad id"),
        lambda m: part(m, "ALPHA-piles")["sheets"][0].update(role="elevation"),
        lambda m: part(m, "ALPHA-piles")["clusters"][0].update(side="up"),
        lambda m: part(m, "ALPHA-piles").update(order=-1),
        drop_order,
        lambda m: part(m, "ALPHA-piles").update(expected_sources=["guess"]),
        lambda m: part(m, "ALPHA-piles")["sheets"][0].update(number_entry="X1"),
        lambda m: m.update(schema_version="0.2"),
    ],
    ids=["kind", "id", "role", "side", "order", "order-missing", "source", "entry", "version"],
)
def test_bad_values_are_schema_problems(capsys, work, mutate):
    manifest = example_manifest()
    mutate(manifest)
    code, out, _ = check(capsys, work, manifest)
    assert code == 1 and {p["code"] for p in out["problems"]} == {"schema"}


def test_duplicate_part_id(capsys, work):
    def mutate(m):
        m["parts"].append(copy.deepcopy(part(m, "ALPHA-caps")))

    assert problems_of(capsys, work, mutate) == [("duplicate_part_id", "ALPHA-caps", None, None)]


def test_sheet_unknown_for_a_sheet_not_listed(capsys, work):
    def mutate(m):
        part(m, "ALPHA-caps")["sheets"].append(sheet_ref("model#09"))

    assert problems_of(capsys, work, mutate) == [("sheet_unknown", "ALPHA-caps", REL, "model#09")]


def test_sheet_unknown_for_a_file_not_listed(capsys, work):
    def mutate(m):
        part(m, "ALPHA-caps")["sheets"].append({"file": "other.dxf", "sheet": "model#01", "role": "plan"})

    assert problems_of(capsys, work, mutate) == [("sheet_unknown", "ALPHA-caps", "other.dxf", "model#01")]


def test_sheet_uncovered(capsys, work):
    manifest = example_manifest()
    part(manifest, "all-grid-levels")["sheets"] = []
    code, out, _ = check(capsys, work, manifest)
    assert (code, keys(out)) == (1, [("sheet_uncovered", None, REL, "model#06")])
    assert out["sheets"] == {"total": 6, "covered": 5}


def test_cluster_uncovered(capsys, work):
    def mutate(m):
        part(m, "ALPHA-piles")["clusters"] = []
        part(m, "ALPHA-piles")["tables"] = []  # its table in that cluster would be outside the part

    assert problems_of(capsys, work, mutate) == [("cluster_uncovered", None, REL, "model#01")]


def test_cluster_without_a_sheet_is_uncovered_with_a_null_sheet(capsys, work):
    def mutate(m):
        part(m, "all-no-sheet")["clusters"] = []

    problems = problems_of(capsys, work, mutate)
    assert problems == [("cluster_uncovered", None, REL, None)]


def test_cluster_in_two_parts(capsys, work):
    def mutate(m):
        part(m, "BETA-piles")["clusters"] = [{"file": REL, "sheet": "model#01", "side": "below"}]

    assert problems_of(capsys, work, mutate) == [("cluster_in_two_parts", None, REL, "model#01")]


def test_cluster_listed_twice_in_one_part_is_not_in_two_parts(capsys, work):
    manifest = example_manifest()
    clusters = part(manifest, "ALPHA-piles")["clusters"]
    clusters.append(dict(clusters[0]))
    code, out, _ = check(capsys, work, manifest)
    assert (code, out["problems"]) == (0, [])


def test_cluster_side_is_part_of_the_identity(capsys, work):
    def mutate(m):
        part(m, "ALPHA-piles")["clusters"][0]["side"] = "above"

    assert problems_of(capsys, work, mutate) == [
        ("cluster_uncovered", None, REL, "model#01"),  # the listed side is another cluster ...
        ("cluster_unknown", "ALPHA-piles", REL, "model#01"),  # ... that unassigned-clusters does not report
        ("table_outside_part", "ALPHA-piles", REL, "model#01"),  # and the table's cluster is no longer listed
    ]


@pytest.mark.parametrize("missing", ["all-grid-levels", "all-notes-materials"])
def test_cross_part_missing(capsys, work, missing):
    def mutate(m):
        other = part(m, "all-notes-materials" if missing == "all-grid-levels" else "all-grid-levels")
        gone = part(m, missing)
        other["sheets"].extend(gone["sheets"])
        m["parts"].remove(gone)
        for p in m["parts"]:
            p["inputs"] = [i for i in p.get("inputs", []) if i != missing]

    assert problems_of(capsys, work, mutate) == [("cross_part_missing", missing, None, None)]


def test_cross_part_with_the_wrong_kind_is_missing(capsys, work):
    def mutate(m):
        part(m, "all-grid-levels")["kind"] = "member"
        part(m, "all-grid-levels").update(block="ALPHA", family="grid")

    assert ("cross_part_missing", "all-grid-levels", None, None) in problems_of(capsys, work, mutate)


@pytest.mark.parametrize("missing", ["scout", "all-assembly"])
def test_bookkeeping_part_missing(capsys, work, missing):
    def mutate(m):
        m["parts"].remove(part(m, missing))
        for p in m["parts"]:
            p["inputs"] = [i for i in p.get("inputs", []) if i != missing]

    assert problems_of(capsys, work, mutate) == [("bookkeeping_part_missing", missing, None, None)]


def test_input_unknown(capsys, work):
    def mutate(m):
        part(m, "ALPHA-caps")["inputs"].append("ghost")

    assert problems_of(capsys, work, mutate) == [("input_unknown", "ALPHA-caps", None, None)]


def test_input_cycle_names_every_part_on_the_cycle(capsys, work):
    def mutate(m):
        part(m, "ALPHA-piles")["inputs"] = ["ALPHA-caps"]

    assert problems_of(capsys, work, mutate) == [
        ("input_cycle", "ALPHA-caps", None, None),
        ("input_cycle", "ALPHA-piles", None, None),
        ("order_not_after_input", "ALPHA-piles", None, None),  # piles (2) would wait on caps (3)
    ]


def test_input_cycle_of_a_part_on_itself(capsys, work):
    def mutate(m):
        part(m, "BETA-piles")["inputs"] = ["BETA-piles"]

    assert problems_of(capsys, work, mutate) == [
        ("input_cycle", "BETA-piles", None, None),
        ("order_not_after_input", "BETA-piles", None, None),  # an order is not above itself
    ]


def test_a_cycle_detail_names_only_the_parts_on_the_cycle(capsys, work):
    manifest = example_manifest()
    part(manifest, "ALPHA-piles")["inputs"] = ["ALPHA-caps", "all-grid-levels"]
    _, out, _ = check(capsys, work, manifest)
    details = {p["part"]: p["detail"] for p in out["problems"] if p["code"] == "input_cycle"}
    assert details == {
        "ALPHA-caps": "inputs form a cycle: ALPHA-caps, ALPHA-piles",
        "ALPHA-piles": "inputs form a cycle: ALPHA-caps, ALPHA-piles",
    }


def test_a_part_that_only_waits_on_a_cycle_is_not_on_it(capsys, work):
    def mutate(m):
        part(m, "ALPHA-piles")["inputs"] = ["ALPHA-caps"]
        part(m, "all-assembly")["inputs"] = ["ALPHA-caps", "BETA-caps"]

    rows = problems_of(capsys, work, mutate)
    assert [k[1] for k in rows if k[0] == "input_cycle"] == ["ALPHA-caps", "ALPHA-piles"]


def test_block_unknown_when_the_block_is_not_listed(capsys, work):
    def mutate(m):
        part(m, "BETA-caps")["block"] = "GAMMA"

    assert problems_of(capsys, work, mutate) == [
        ("block_unknown", "BETA-caps", None, None),
        ("part_kind_mismatch", "BETA-caps", None, None),  # and its id does not start with GAMMA-caps
    ]


def test_block_unknown_when_a_member_has_no_block(capsys, work):
    def mutate(m):
        del part(m, "BETA-caps")["block"]

    assert problems_of(capsys, work, mutate) == [("block_unknown", "BETA-caps", None, None)]


def test_block_unknown_when_a_member_has_no_family(capsys, work):
    def mutate(m):
        del part(m, "BETA-caps")["family"]

    assert problems_of(capsys, work, mutate) == [("block_unknown", "BETA-caps", None, None)]


def test_a_cross_part_needs_neither_block_nor_family(capsys, work):
    code, out, _ = check(capsys, work, example_manifest())
    assert code == 0 and "block" not in part(example_manifest(), "all-grid-levels")
    assert out["problems"] == []


def test_sheet_in_two_blocks(capsys, work):
    def mutate(m):
        part(m, "BETA-caps")["sheets"].append(sheet_ref("model#01"))

    assert problems_of(capsys, work, mutate) == [("sheet_in_two_blocks", None, REL, "model#01")]


def test_a_cross_part_may_share_a_sheet_with_a_member_part(capsys, work):
    manifest = example_manifest()
    part(manifest, "all-notes-materials")["sheets"].append(sheet_ref("model#01"))
    code, out, _ = check(capsys, work, manifest)
    assert (code, out["problems"]) == (0, [])


def test_one_sheet_may_serve_several_parts_of_one_block(capsys, work):
    code, _out, _ = check(capsys, work, example_manifest())
    assert code == 0  # model#01 is in ALPHA-piles and ALPHA-caps


def test_cap_of_four_sheets_passes_and_five_fails(capsys, work):
    manifest = example_manifest()
    notes = part(manifest, "all-notes-materials")
    notes["sheets"] = [sheet_ref(f"model#0{n}") for n in (1, 2, 3, 4)]
    part(manifest, "all-grid-levels")["sheets"] = [sheet_ref("model#05"), sheet_ref("model#06")]
    code, out, _ = check(capsys, work, manifest)
    assert (code, out["problems"]) == (0, [])
    notes["sheets"].append(sheet_ref("model#05"))
    code, out, _ = check(capsys, work, manifest)
    assert code == 1 and keys(out) == [("part_over_cap", "all-notes-materials", None, None)]
    assert "5 sheets" in out["problems"][0]["detail"] and "10 printed entries" in out["problems"][0]["detail"]


def test_a_sheet_listed_twice_in_a_part_counts_once_for_the_cap(capsys, work):
    manifest = example_manifest()
    part(manifest, "all-notes-materials")["sheets"] = [sheet_ref("model#05")] * 5
    code, out, _ = check(capsys, work, manifest)
    assert (code, out["problems"]) == (0, [])


def inflate(work: Path, sheet: str, extra: int) -> None:
    """Add `extra` printed entries to a sheet of a work folder copy."""
    index_path = work / "text" / f"{REL}.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    sheets_path = work / STRUCTURE_DIR / f"{REL}.sheets.json"
    sheets = json.loads(sheets_path.read_text(encoding="utf-8"))
    target = next(s for s in sheets["sheets"] if s["sheet_id"] == sheet)
    template = index["entries"][0]
    for i in range(extra):
        entry = copy.deepcopy(template)
        entry["id"] = f"T9{len(index['entries']):05d}"
        entry["display_text"] = f"x{i}"
        index["entries"].append(entry)
        target["text_ids"].append(entry["id"])
    index_path.write_text(json.dumps(index), encoding="utf-8")
    sheets_path.write_text(json.dumps(sheets), encoding="utf-8")


def test_cap_of_1500_printed_entries_passes_and_1501_fails(capsys, copied):
    manifest = example_manifest()
    part(manifest, "all-notes-materials")["sheets"] = [sheet_ref("model#05")]
    inflate(copied, "model#05", 1498)  # 2 printed + 1498 = 1500
    code, out, _ = check(capsys, copied, manifest)
    assert (code, out["problems"]) == (0, [])
    inflate(copied, "model#05", 1)
    code, out, _ = check(capsys, copied, manifest)
    assert code == 1 and keys(out) == [("part_over_cap", "all-notes-materials", None, None)]
    assert (
        "1 sheets" in out["problems"][0]["detail"] and "1501 printed entries" in out["problems"][0]["detail"]
    )


def test_entries_are_summed_over_the_sheets_of_a_part(capsys, copied):
    manifest = example_manifest()
    part(manifest, "all-notes-materials")["sheets"] = [sheet_ref("model#05"), sheet_ref("model#06")]
    inflate(copied, "model#05", 1497)  # 2 + 1497 + 1 (model#06) = 1500
    code, out, _ = check(capsys, copied, manifest)
    assert (code, out["problems"]) == (0, [])
    inflate(copied, "model#06", 1)
    code, out, _ = check(capsys, copied, manifest)
    assert keys(out) == [("part_over_cap", "all-notes-materials", None, None)]


def test_hidden_entries_do_not_count_for_the_cap(capsys, copied):
    manifest = example_manifest()
    part(manifest, "all-notes-materials")["sheets"] = [sheet_ref("model#05")]
    inflate(copied, "model#05", 1498)
    index_path = copied / "text" / f"{REL}.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    extra = copy.deepcopy(index["entries"][0])
    extra.update(id="T999999", printed=False)
    index["entries"].append(extra)
    index_path.write_text(json.dumps(index), encoding="utf-8")
    sheets_path = copied / STRUCTURE_DIR / f"{REL}.sheets.json"
    sheets = json.loads(sheets_path.read_text(encoding="utf-8"))
    next(s for s in sheets["sheets"] if s["sheet_id"] == "model#05")["text_ids"].append("T999999")
    sheets_path.write_text(json.dumps(sheets), encoding="utf-8")
    code, out, _ = check(capsys, copied, manifest)
    assert (code, out["problems"]) == (0, [])


def test_bookkeeping_and_no_sheet_parts_are_exempt_from_sheet_rules(capsys, work):
    manifest = example_manifest()
    scout = part(manifest, "scout")
    scout["sheets"] = [
        sheet_ref(f"model#0{n}") for n in range(1, 7)
    ]  # six sheets: no cap for the exempt kinds
    part(manifest, "all-no-sheet")["sheets"] = [sheet_ref("model#01")]
    part(manifest, "all-assembly")["sheets"] = [sheet_ref("model#01"), sheet_ref("model#03")]  # two blocks
    code, out, _ = check(capsys, work, manifest)
    assert (code, out["problems"]) == (0, [])


@pytest.mark.parametrize("exempt", ["scout", "all-assembly", "all-no-sheet"])
def test_sheet_unknown_for_the_sheets_of_an_exempt_part(capsys, work, exempt):
    def mutate(m):
        part(m, exempt)["sheets"] = [sheet_ref("model#01"), sheet_ref("model#99")]

    assert problems_of(capsys, work, mutate) == [("sheet_unknown", exempt, REL, "model#99")]


def test_exempt_parts_do_not_cover_sheets(capsys, work):
    manifest = example_manifest()
    part(manifest, "all-grid-levels")["sheets"] = []
    part(manifest, "scout")["sheets"] = [sheet_ref("model#06")]
    _code, out, _ = check(capsys, work, manifest)
    assert keys(out) == [("sheet_uncovered", None, REL, "model#06")]
    assert out["sheets"]["covered"] == 5


def test_exempt_parts_do_not_make_a_sheet_belong_to_two_blocks(capsys, work):
    manifest = example_manifest()
    part(manifest, "all-no-sheet")["block"] = "BETA"
    part(manifest, "all-no-sheet")["sheets"] = [sheet_ref("model#01")]
    code, out, _ = check(capsys, work, manifest)
    assert (code, out["problems"]) == (0, [])


# --- references into the tables, clusters, entries and blocks of the manifest (review 1: M3, D3, F1, D6) ---


def table_on(sheet: str, entry: str) -> dict[str, Any]:
    return {"file": REL, "sheet": sheet, "header_entries": [entry]}


def table_in(sheet: str | None, side: str, entry: str) -> dict[str, Any]:
    return {"cluster": {"file": REL, "sheet": sheet, "side": side}, "header_entries": [entry]}


def rows(capsys, work: Path, mutate: Callable[[dict[str, Any]], None]) -> list[dict[str, Any]]:
    manifest = example_manifest()
    mutate(manifest)
    code, out, _ = check(capsys, work, manifest)
    assert code == 1 and validate("part-output", out) == []
    return out["problems"]


def test_sheet_unknown_for_a_table_on_a_sheet_not_listed(capsys, work):
    def mutate(m):
        part(m, "ALPHA-caps")["tables"].append(table_on("model#09", "T000999"))

    found = rows(capsys, work, mutate)
    assert [(p["code"], p["part"], p["file"], p["sheet"]) for p in found] == [
        ("sheet_unknown", "ALPHA-caps", REL, "model#09")
    ]  # no entry_unknown and no table_outside_part for a sheet that does not exist
    assert found[0]["detail"] == "table on a sheet that `harness list-sheets` does not print"


def test_sheet_unknown_for_a_table_in_a_file_not_listed(capsys, work):
    def mutate(m):
        part(m, "ALPHA-caps")["tables"].append(
            {"file": "other.dxf", "sheet": "model#01", "header_entries": ["T000001"]}
        )

    assert problems_of(capsys, work, mutate) == [("sheet_unknown", "ALPHA-caps", "other.dxf", "model#01")]


def test_table_outside_part_for_a_sheet_the_part_does_not_list(capsys, work):
    def mutate(m):
        part(m, "ALPHA-caps")["tables"].append(table_on("model#03", "T000007"))

    found = rows(capsys, work, mutate)
    assert [(p["code"], p["part"], p["file"], p["sheet"]) for p in found] == [
        ("table_outside_part", "ALPHA-caps", REL, "model#03")
    ]
    assert "sheets[]" in found[0]["detail"]


def test_table_outside_part_for_a_cluster_the_part_does_not_list(capsys, work):
    def mutate(m):
        part(m, "BETA-caps")["tables"].append(table_in("model#01", "below", "T000013"))

    found = rows(capsys, work, mutate)
    assert [(p["code"], p["part"], p["file"], p["sheet"]) for p in found] == [
        ("table_outside_part", "BETA-caps", REL, "model#01")
    ]  # the table does not make BETA-caps a second owner of the cluster
    assert "clusters[]" in found[0]["detail"]


def test_a_table_whose_sheet_and_cluster_the_part_lists_is_inside_the_part(capsys, work):
    code, out, _ = check(capsys, work, example_manifest())  # the example has both kinds of table
    assert (code, out["problems"]) == (0, [])


def test_cluster_unknown_for_a_triple_unassigned_clusters_does_not_report(capsys, work):
    def mutate(m):
        part(m, "ALPHA-piles")["clusters"].append({"file": REL, "sheet": "model#02", "side": "below"})

    found = rows(capsys, work, mutate)
    assert [(p["code"], p["part"], p["file"], p["sheet"]) for p in found] == [
        ("cluster_unknown", "ALPHA-piles", REL, "model#02")
    ]
    assert found[0]["detail"] == (
        "cluster side 'below' of model#02 is not reported by `harness unassigned-clusters`"
    )


def test_cluster_unknown_for_the_cluster_of_a_table(capsys, work):
    def mutate(m):
        part(m, "BETA-caps")["tables"].append(table_in("model#02", "below", "T000004"))

    assert problems_of(capsys, work, mutate) == [("cluster_unknown", "BETA-caps", REL, "model#02")]


def test_cluster_unknown_for_a_file_not_listed_with_a_null_sheet(capsys, work):
    def mutate(m):
        part(m, "all-no-sheet")["clusters"].append({"file": "other.dxf", "sheet": None, "side": "none"})

    found = rows(capsys, work, mutate)
    assert [(p["code"], p["part"], p["file"], p["sheet"]) for p in found] == [
        ("cluster_unknown", "all-no-sheet", "other.dxf", None)
    ]
    assert found[0]["detail"] == (
        "cluster side 'none' of no sheet is not reported by `harness unassigned-clusters`"
    )


def test_an_unknown_cluster_listed_by_two_parts_is_not_in_two_parts(capsys, work):
    ghost = {"file": REL, "sheet": "model#02", "side": "above"}

    def mutate(m):
        part(m, "ALPHA-piles")["clusters"].append(dict(ghost))
        part(m, "BETA-piles")["clusters"] = [dict(ghost)]

    assert problems_of(capsys, work, mutate) == [
        ("cluster_unknown", "ALPHA-piles", REL, "model#02"),
        ("cluster_unknown", "BETA-piles", REL, "model#02"),
    ]


def entry_row(capsys, work: Path, mutate: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    found = rows(capsys, work, mutate)
    assert [p["code"] for p in found] == ["entry_unknown"], found
    return found[0]


def test_entry_unknown_for_a_number_entry_the_text_index_lacks(capsys, work):
    def mutate(m):
        part(m, "ALPHA-piles")["sheets"][0]["number_entry"] = "T000999"

    row = entry_row(capsys, work, mutate)
    assert (row["part"], row["file"], row["sheet"]) == ("ALPHA-piles", REL, "model#01")
    assert "number_entry" in row["detail"] and "T000999" in row["detail"]


def test_entry_unknown_for_a_title_entry(capsys, work):
    def mutate(m):
        part(m, "ALPHA-piles")["sheets"][0]["title_entry"] = "T000999"

    row = entry_row(capsys, work, mutate)
    assert "title_entry" in row["detail"] and row["sheet"] == "model#01"


def test_entry_unknown_for_a_heading_entry(capsys, work):
    def mutate(m):
        part(m, "ALPHA-piles")["sheets"][0]["views"][0]["heading_entry"] = "T000999"

    row = entry_row(capsys, work, mutate)
    assert "heading_entry" in row["detail"] and row["sheet"] == "model#01"


def test_entry_unknown_for_an_entry_that_is_on_another_sheet(capsys, work):
    def mutate(m):
        part(m, "ALPHA-piles")["sheets"][0]["number_entry"] = "T000007"  # in the index, on model#03

    row = entry_row(capsys, work, mutate)
    assert (row["part"], row["sheet"]) == ("ALPHA-piles", "model#01") and "T000007" in row["detail"]


def test_entry_unknown_for_a_table_header_on_a_sheet(capsys, work):
    def mutate(m):
        part(m, "ALPHA-caps")["tables"][0]["header_entries"].append("T000999")

    row = entry_row(capsys, work, mutate)
    assert (row["part"], row["file"], row["sheet"]) == ("ALPHA-caps", REL, "model#02")
    assert "header_entries" in row["detail"] and "T000999" in row["detail"]


def test_entry_unknown_for_a_table_header_of_another_sheet(capsys, work):
    def mutate(m):
        part(m, "ALPHA-caps")["tables"][0]["header_entries"] = ["T000001"]  # on model#01, not model#02

    assert entry_row(capsys, work, mutate)["sheet"] == "model#02"


def test_entry_unknown_for_a_table_header_outside_its_cluster(capsys, work):
    def mutate(m):
        part(m, "ALPHA-piles")["tables"][0]["header_entries"] = ["T000014"]  # the cluster below holds T000013

    row = entry_row(capsys, work, mutate)
    assert (row["part"], row["file"], row["sheet"]) == ("ALPHA-piles", REL, "model#01")
    assert "T000014" in row["detail"]


def test_entry_unknown_for_a_cluster_table_header_that_is_on_the_sheet_but_not_in_the_cluster(capsys, work):
    def mutate(m):
        part(m, "ALPHA-piles")["tables"][0]["header_entries"] = ["T000001"]  # on model#01, not in its cluster

    row = entry_row(capsys, work, mutate)
    assert (row["part"], row["file"], row["sheet"]) == ("ALPHA-piles", REL, "model#01")
    assert "T000001" in row["detail"]


def test_entry_unknown_rows_of_two_fields_are_two_rows(capsys, work):
    def mutate(m):
        ref = part(m, "ALPHA-piles")["sheets"][0]
        ref["number_entry"] = ref["title_entry"] = "T000999"

    found = rows(capsys, work, mutate)
    assert [p["code"] for p in found] == ["entry_unknown", "entry_unknown"]
    assert {"number_entry" in p["detail"] for p in found} == {True, False}


def test_duplicate_block_id(capsys, work):
    def mutate(m):
        m["blocks"].append(copy.deepcopy(m["blocks"][0]))

    found = rows(capsys, work, mutate)
    assert [(p["code"], p["part"], p["file"], p["sheet"]) for p in found] == [
        ("duplicate_block_id", None, None, None)
    ]
    assert "'ALPHA'" in found[0]["detail"] and "2 times" in found[0]["detail"]


def test_the_text_index_and_the_sheets_document_are_read_once_per_file(work, monkeypatch):
    import tekla_harness.sheet_text as sheet_text_module

    put(work, example_manifest())
    real = sheet_text_module.read_json
    seen: list[str] = []

    def counting(path: Path, label: str) -> Any:
        seen.append(Path(path).as_posix())
        return real(path, label)

    monkeypatch.setattr(sheet_text_module, "read_json", counting)
    assert pm().manifest_check(work)["ok"] is True
    assert sum(p.endswith(f"/text/{REL}.json") for p in seen) == 1, seen
    assert sum(p.endswith(f"{REL}.sheets.json") for p in seen) == 1, seen


# --- kind rules, split cross parts, unread files (review 1: D1, D2, D4) ---------------------------------


def rename(manifest: dict[str, Any], old: str, new: str) -> None:
    part(manifest, old)["id"] = new
    for p in manifest["parts"]:
        p["inputs"] = [new if i == old else i for i in p.get("inputs", [])]


def mismatches(capsys, work: Path, mutate: Callable[[dict[str, Any]], None]) -> list[str]:
    manifest = example_manifest()
    mutate(manifest)
    code, out, _ = check(capsys, work, manifest)
    assert validate("part-output", out) == []
    assert code == (1 if out["problems"] else 0)
    return [p["part"] for p in out["problems"] if p["code"] == "part_kind_mismatch"]


def as_member(p: dict[str, Any]) -> None:
    p.update(kind="member", block="ALPHA", family="grid")


@pytest.mark.parametrize(
    ("mutate", "bad"),
    [
        (lambda m: as_member(part(m, "all-grid-levels")), "all-grid-levels"),
        (lambda m: part(m, "all-notes-materials").update(kind="bookkeeping"), "all-notes-materials"),
        (lambda m: part(m, "scout").update(kind="cross"), "scout"),
        (lambda m: part(m, "all-assembly").update(kind="no_sheet"), "all-assembly"),
        (lambda m: part(m, "all-no-sheet").update(kind="bookkeeping"), "all-no-sheet"),
        (lambda m: part(m, "ALPHA-caps").update(kind="cross"), "ALPHA-caps"),
        (lambda m: part(m, "ALPHA-caps").update(kind="no_sheet"), "ALPHA-caps"),
        (lambda m: part(m, "ALPHA-caps").update(kind="bookkeeping"), "ALPHA-caps"),
        (lambda m: part(m, "ALPHA-caps").update(family="slabs"), "ALPHA-caps"),
        (lambda m: part(m, "ALPHA-caps").update(block="BETA"), "ALPHA-caps"),
        (
            lambda m: part(m, "ALPHA-caps").update(family="cap"),
            "ALPHA-caps",
        ),  # a prefix, not a part of the id
        (lambda m: rename(m, "ALPHA-caps", "NX1-everything"), "NX1-everything"),
        (lambda m: split_with_empty_suffix(m), "all-grid-levels-"),
        (lambda m: rename(m, "ALPHA-caps", "ALPHA-caps-"), "ALPHA-caps-"),
    ],
    ids=[
        "cross-id-member",
        "cross-id-bookkeeping",
        "scout-cross",
        "assembly-no-sheet",
        "no-sheet-id-bookkeeping",
        "member-id-cross",
        "member-id-no-sheet",
        "member-id-bookkeeping",
        "family-differs",
        "block-differs",
        "family-prefix",
        "free-id",
        "split-empty-suffix",
        "member-empty-suffix",
    ],
)
def test_part_kind_mismatch(capsys, work, mutate, bad):
    assert mismatches(capsys, work, mutate) == [bad]


def test_a_member_split_id_with_a_letter_is_no_mismatch(capsys, work):
    assert mismatches(capsys, work, lambda m: None) == []  # the example has ALPHA-piles and ALPHA-piles-b


def test_a_member_without_block_or_family_is_block_unknown_not_a_kind_mismatch(capsys, work):
    def mutate(m):
        del part(m, "ALPHA-caps")["family"]

    assert mismatches(capsys, work, mutate) == []


def test_a_member_part_of_a_block_that_is_not_listed_is_block_unknown_not_a_kind_mismatch(capsys, work):
    def mutate(m):
        rename(m, "ALPHA-caps", "GAMMA-caps")
        part(m, "GAMMA-caps").update(block="GAMMA")

    assert mismatches(capsys, work, mutate) == []


def split_grid_levels(m: dict[str, Any]) -> dict[str, Any]:
    """all-grid-levels becomes all-grid-levels-a (kind cross, split_of the fixed id)."""
    rename(m, "all-grid-levels", "all-grid-levels-a")
    split = part(m, "all-grid-levels-a")
    split["split_of"] = "all-grid-levels"
    return split


def test_a_cross_part_over_the_cap_is_split_and_the_manifest_is_ok(capsys, work):
    manifest = example_manifest()
    notes = part(manifest, "all-notes-materials")
    notes["sheets"] = [sheet_ref(f"model#0{n}") for n in (1, 2, 3, 4)]
    manifest["parts"].append(
        {
            "id": "all-notes-materials-a",
            "kind": "cross",
            "order": 1,
            "sheets": [sheet_ref("model#05")],
            "split_of": "all-notes-materials",
        }
    )
    assert validate("parts-manifest", manifest) == []
    code, out, _ = check(capsys, work, manifest)
    assert (code, out["problems"]) == (0, [])


def test_cross_part_missing_is_satisfied_by_a_part_whose_split_of_is_the_fixed_id(capsys, work):
    manifest = example_manifest()
    split_grid_levels(manifest)  # no part has the id all-grid-levels any more
    code, out, _ = check(capsys, work, manifest)
    assert (code, out["problems"]) == (0, [])


def test_two_split_parts_may_replace_the_fixed_id(capsys, work):
    manifest = example_manifest()
    first = split_grid_levels(manifest)
    second = copy.deepcopy(first)
    second.update(id="all-grid-levels-b", sheets=[sheet_ref("model#05")])
    manifest["parts"].append(second)
    part(manifest, "all-notes-materials")["sheets"] = [sheet_ref("model#04")]
    code, out, _ = check(capsys, work, manifest)
    assert (code, out["problems"]) == (0, [])


def test_a_split_of_the_other_cross_id_does_not_satisfy_cross_part_missing(capsys, work):
    def mutate(m):
        split_grid_levels(m)["split_of"] = "all-notes-materials"

    found = problems_of(capsys, work, mutate)
    assert ("cross_part_missing", "all-grid-levels", None, None) in found
    assert ("part_kind_mismatch", "all-grid-levels-a", None, None) in found  # the id is not <split_of>-...


def split_with_empty_suffix(m: dict[str, Any]) -> None:
    """The split id is the fixed id and a dash, with no text after it."""
    split_grid_levels(m)
    rename(m, "all-grid-levels-a", "all-grid-levels-")


def test_a_fixed_cross_part_whose_split_of_names_the_other_fixed_id_does_not_satisfy_both(capsys, work):
    def mutate(m):
        gone = part(m, "all-notes-materials")
        part(m, "all-grid-levels")["sheets"].extend(gone["sheets"])  # four sheets, at the cap
        m["parts"].remove(gone)
        for p in m["parts"]:
            p["inputs"] = [i for i in p.get("inputs", []) if i != "all-notes-materials"]
        part(m, "all-grid-levels")["split_of"] = "all-notes-materials"

    found = problems_of(capsys, work, mutate)
    assert ("cross_part_missing", "all-notes-materials", None, None) in found


def test_a_split_with_an_empty_suffix_does_not_satisfy_cross_part_missing(capsys, work):
    found = problems_of(capsys, work, split_with_empty_suffix)
    assert ("cross_part_missing", "all-grid-levels", None, None) in found
    assert ("part_kind_mismatch", "all-grid-levels-", None, None) in found


def test_a_split_part_of_the_wrong_kind_does_not_satisfy_cross_part_missing(capsys, work):
    def mutate(m):
        as_member(split_grid_levels(m))

    found = problems_of(capsys, work, mutate)
    assert ("cross_part_missing", "all-grid-levels", None, None) in found
    assert ("part_kind_mismatch", "all-grid-levels-a", None, None) in found


def test_a_cross_part_with_a_free_id_and_no_split_of_is_a_kind_mismatch(capsys, work):
    manifest = example_manifest()
    del split_grid_levels(manifest)["split_of"]
    _code, out, _ = check(capsys, work, manifest)
    found = [p for p in out["problems"] if p["code"] == "part_kind_mismatch"]
    assert [p["part"] for p in found] == ["all-grid-levels-a"] and "needs split_of" in found[0]["detail"]


def test_a_split_of_that_names_no_fixed_id_is_a_kind_mismatch(capsys, work):
    def mutate(m):
        split_grid_levels(m)["split_of"] = "ALPHA-piles"

    assert mismatches(capsys, work, mutate) == ["all-grid-levels-a"]


UNREAD = "plans/skipped.dxf"


def add_unread_file(work: Path, rel: str = UNREAD) -> None:
    """A second DWG/DXF in inventory.json that has no text index: `harness list-sheets` skips it."""
    path = work / "inventory.json"
    inv = json.loads(path.read_text(encoding="utf-8"))
    row = copy.deepcopy(next(r for r in inv["files"] if r["path"] == REL))
    row.update(path=rel, text_index=None)
    inv["files"].append(row)
    path.write_text(json.dumps(inv), encoding="utf-8")


def test_file_unread_for_a_file_list_sheets_skips(capsys, copied):
    add_unread_file(copied)
    code, out, err = check(capsys, copied, example_manifest())
    assert code == 1 and validate("part-output", out) == []
    assert keys(out) == [("file_unread", None, UNREAD, None)]
    assert "no_sheet" in out["problems"][0]["detail"] and "files[]" in out["problems"][0]["detail"]
    assert out["sheets"] == {"total": 6, "covered": 6}
    assert f"{UNREAD}: skipped" in err


def test_a_no_sheet_part_that_names_the_file_clears_file_unread(capsys, copied):
    add_unread_file(copied)
    manifest = example_manifest()
    part(manifest, "all-no-sheet")["files"] = [UNREAD]
    assert validate("parts-manifest", manifest) == []
    code, out, _ = check(capsys, copied, manifest)
    assert (code, out["problems"]) == (0, [])


def test_a_part_of_another_kind_that_names_the_file_does_not_clear_file_unread(capsys, copied):
    add_unread_file(copied)
    manifest = example_manifest()
    part(manifest, "scout")["files"] = [UNREAD]
    code, out, _ = check(capsys, copied, manifest)
    assert code == 1 and keys(out) == [
        ("file_unread", None, UNREAD, None),
        ("files_entry_unused", "scout", UNREAD, None),  # and the entry is no use on that part
    ]


def test_a_no_sheet_part_clears_only_the_files_it_names(capsys, copied):
    add_unread_file(copied)
    manifest = example_manifest()
    part(manifest, "all-no-sheet")["files"] = ["plans/other.dxf"]
    code, out, _ = check(capsys, copied, manifest)
    assert code == 1 and keys(out) == [
        ("file_unread", None, UNREAD, None),
        ("files_entry_unused", "all-no-sheet", "plans/other.dxf", None),  # not in the inventory
    ]


def test_files_entry_unused_for_a_file_list_sheets_reads(capsys, copied):
    manifest = example_manifest()
    part(manifest, "all-no-sheet")["files"] = [REL]  # read normally: its sheets are the sheet parts' business
    code, out, _ = check(capsys, copied, manifest)
    assert code == 1 and validate("part-output", out) == []
    assert keys(out) == [("files_entry_unused", "all-no-sheet", REL, None)]
    assert "list-sheets" in out["problems"][0]["detail"] and "skip" in out["problems"][0]["detail"]


def test_files_entry_unused_for_a_file_that_is_not_in_the_inventory(capsys, work):
    manifest = example_manifest()
    part(manifest, "all-no-sheet")["files"] = ["plans/nowhere.dxf"]
    code, out, _ = check(capsys, work, manifest)
    assert code == 1 and keys(out) == [("files_entry_unused", "all-no-sheet", "plans/nowhere.dxf", None)]


@pytest.mark.parametrize("holder", ["scout", "all-grid-levels", "ALPHA-caps"])
def test_files_entry_unused_for_a_part_that_is_not_no_sheet(capsys, copied, holder):
    add_unread_file(copied)
    manifest = example_manifest()
    part(manifest, "all-no-sheet")["files"] = [UNREAD]  # this one reads the file
    part(manifest, holder)["files"] = [UNREAD]
    code, out, _ = check(capsys, copied, manifest)
    assert code == 1 and validate("part-output", out) == []
    assert keys(out) == [("files_entry_unused", holder, UNREAD, None)]
    assert "no_sheet" in out["problems"][0]["detail"] and holder in out["problems"][0]["detail"]


def test_a_files_entry_with_both_faults_is_one_row_with_both_reasons(capsys, work):
    manifest = example_manifest()
    part(manifest, "scout")["files"] = [REL]
    code, out, _ = check(capsys, work, manifest)
    assert code == 1 and keys(out) == [("files_entry_unused", "scout", REL, None)]
    assert out["problems"][0]["detail"].count("; ") == 1


def test_one_row_for_each_part_and_file_of_files_entry_unused(capsys, work):
    manifest = example_manifest()
    part(manifest, "all-no-sheet")["files"] = ["plans/b.dxf", "plans/a.dxf"]
    code, out, _ = check(capsys, work, manifest)
    assert code == 1 and keys(out) == [
        ("files_entry_unused", "all-no-sheet", "plans/a.dxf", None),
        ("files_entry_unused", "all-no-sheet", "plans/b.dxf", None),
    ]


def test_a_files_entry_that_names_a_skipped_file_on_a_no_sheet_part_is_used(capsys, copied):
    add_unread_file(copied)
    manifest = shipped_manifest()  # its no_sheet part names plans/legacy.dxf: make that file a skipped one
    del manifest["acks"]
    add_unread_file(copied, "plans/legacy.dxf")
    part(manifest, "all-no-sheet")["files"].append(UNREAD)
    code, out, _ = check(capsys, copied, manifest)
    assert (code, out["problems"]) == (0, [])


def test_a_set_of_skipped_files_alone_is_not_ok(capsys, copied):
    path = copied / "inventory.json"
    inv = json.loads(path.read_text(encoding="utf-8"))
    for r in inv["files"]:
        r["text_index"] = None
    path.write_text(json.dumps(inv), encoding="utf-8")
    manifest = example_manifest()
    for p in manifest["parts"]:
        p.pop("sheets", None)
        p.pop("tables", None)
        p.pop("clusters", None)
    code, out, _ = check(capsys, copied, manifest)
    assert code == 1 and out["sheets"] == {"total": 0, "covered": 0}
    assert keys(out) == [("file_unread", None, REL, None)]


def test_file_unread_for_an_unreadable_text_index(capsys, copied):
    path = copied / "text" / f"{REL}.json"
    index = json.loads(path.read_text(encoding="utf-8"))
    index.update(status="unreadable", error="cannot parse")
    path.write_text(json.dumps(index), encoding="utf-8")
    manifest = example_manifest()
    for p in manifest["parts"]:
        p.pop("sheets", None)
        p.pop("tables", None)
        p.pop("clusters", None)
    code, out, _ = check(capsys, copied, manifest)
    assert code == 1 and keys(out) == [("file_unread", None, REL, None)]
    assert "cannot parse" in out["problems"][0]["detail"]


# --- gaps the hand mutants of the E4a review found (m6) ---------------------------------------------------

OTHER = "plans/set2.dxf"


def add_second_file(work: Path) -> None:
    """A second DXF with the same six frames and the same two clusters (same sheet ids, same sides)."""
    path = work / "inventory.json"
    inv = json.loads(path.read_text(encoding="utf-8"))
    row = copy.deepcopy(next(r for r in inv["files"] if r["path"] == REL))
    row.update(path=OTHER, text_index=f"text/{OTHER}.json")
    inv["files"].append(row)
    path.write_text(json.dumps(inv), encoding="utf-8")
    shutil.copy(work / "text" / f"{REL}.json", work / "text" / f"{OTHER}.json")
    shutil.copy(work / STRUCTURE_DIR / f"{REL}.sheets.json", work / STRUCTURE_DIR / f"{OTHER}.sheets.json")
    ledger = work / "answers.json"  # the units answer of the first file, given again for the second
    answers = json.loads(ledger.read_text(encoding="utf-8"))
    given = next(a for a in answers["answers"] if a["file"] == REL)
    answers["answers"].append({**given, "key": "f" * len(given["key"]), "file": OTHER})
    ledger.write_text(json.dumps(answers), encoding="utf-8")


def read_other_file(
    manifest: dict[str, Any], sheets: list[str], clusters: list[tuple[str | None, str]]
) -> None:
    """A member part of block ALPHA that reads `sheets` and `clusters` (sheet, side) of the second file."""
    manifest["parts"].append(
        {
            "id": "ALPHA-other",
            "kind": "member",
            "block": "ALPHA",
            "family": "other",
            "order": 3,
            "sheets": [{"file": OTHER, "sheet": s, "role": "plan"} for s in sheets],
            "clusters": [{"file": OTHER, "sheet": s, "side": side} for s, side in clusters],
        }
    )


def test_the_same_sheet_ids_of_a_second_file_are_not_covered_by_the_first(capsys, copied):
    add_second_file(copied)
    code, out, _ = check(capsys, copied, example_manifest())
    assert code == 1 and validate("part-output", out) == []
    assert keys(out) == [
        ("cluster_uncovered", None, OTHER, None),
        ("cluster_uncovered", None, OTHER, "model#01"),
        *[("sheet_uncovered", None, OTHER, f"model#0{n}") for n in range(1, 7)],
    ]
    assert out["sheets"] == {"total": 12, "covered": 6}


def test_a_second_file_that_lists_only_model_01_leaves_the_rest_of_it_uncovered(capsys, copied):
    add_second_file(copied)
    manifest = example_manifest()
    read_other_file(manifest, ["model#01"], [("model#01", "below")])
    code, out, _ = check(capsys, copied, manifest)
    assert code == 1
    assert keys(out) == [
        ("cluster_uncovered", None, OTHER, None),
        *[("sheet_uncovered", None, OTHER, f"model#0{n}") for n in range(2, 7)],
    ]


def test_each_file_covers_its_own_sheets_and_clusters_with_the_same_ids(capsys, copied):
    add_second_file(copied)
    manifest = example_manifest()
    read_other_file(manifest, ["model#01", "model#02", "model#03", "model#04"], [("model#01", "below")])
    read_other_file(manifest, ["model#05", "model#06"], [(None, "none")])
    manifest["parts"][-1]["id"], manifest["parts"][-1]["family"] = "ALPHA-other-b", "other"
    code, out, _ = check(capsys, copied, manifest)
    assert (code, out["problems"]) == (0, [])
    assert out["sheets"] == {"total": 12, "covered": 12}


def test_cluster_unknown_for_a_triple_of_a_file_not_listed(capsys, work):
    def mutate(m):
        part(m, "ALPHA-piles")["clusters"].append(
            {"file": "plans/absent.dxf", "sheet": "model#01", "side": "below"}
        )

    found = rows(capsys, work, mutate)
    assert [(p["code"], p["part"], p["file"], p["sheet"]) for p in found] == [
        ("cluster_unknown", "ALPHA-piles", "plans/absent.dxf", "model#01")
    ]


def test_sheet_in_two_blocks_counts_member_parts_only(capsys, work):
    manifest = example_manifest()
    notes = part(manifest, "all-notes-materials")
    notes["block"] = "BETA"
    notes["sheets"].append(sheet_ref("model#01"))  # model#01 belongs to ALPHA
    code, out, _ = check(capsys, work, manifest)
    assert (code, out["problems"]) == (0, [])


def test_the_cap_counts_the_sheets_that_do_not_exist_too(capsys, work):
    manifest = example_manifest()
    manifest_notes = part(manifest, "all-notes-materials")
    manifest_notes["sheets"] = [sheet_ref(f"model#0{n}") for n in (1, 2, 3, 5)] + [sheet_ref("model#09")]
    code, out, _ = check(capsys, work, manifest)
    assert code == 1
    assert keys(out) == [
        ("part_over_cap", "all-notes-materials", None, None),
        ("sheet_unknown", "all-notes-materials", REL, "model#09"),
    ]
    assert "5 sheets" in out["problems"][0]["detail"] and "9 printed entries" in out["problems"][0]["detail"]


def test_parts_counts_the_rows_of_the_manifest_not_the_distinct_ids(capsys, work):
    manifest = example_manifest()
    manifest["parts"].append(copy.deepcopy(part(manifest, "ALPHA-caps")))
    code, out, _ = check(capsys, work, manifest)
    assert code == 1 and len(manifest["parts"]) == 11 and out["parts"] == 11


def test_a_file_without_a_text_index_is_named_on_stderr(capsys, copied):
    add_unread_file(copied)
    code, _out, err = check(capsys, copied, example_manifest())
    assert code == 1 and f"{UNREAD}: skipped: no text index was computed" in err


def drop_sheet_of_table(manifest: dict[str, Any]) -> None:
    del part(manifest, "ALPHA-caps")["tables"][0]["sheet"]


def table_with_both(manifest: dict[str, Any]) -> None:
    part(manifest, "ALPHA-caps")["tables"][0]["cluster"] = {"file": REL, "sheet": "model#01", "side": "below"}


def cluster_table_with(**extra: Any) -> Callable[[dict[str, Any]], None]:
    """A table with a `cluster` and `file` or `sheet` beside it (a cluster table holds neither)."""

    def mutate(manifest: dict[str, Any]) -> None:
        table = table_in("model#01", "below", "T000009")
        table.update(extra)
        part(manifest, "BETA-caps")["tables"].append(table)

    return mutate


def beta_cluster_table(**cluster: Any) -> Callable[[dict[str, Any]], None]:
    def mutate(manifest: dict[str, Any]) -> None:
        table = table_in("model#01", "below", "T000009")
        table["cluster"].update(cluster)
        part(manifest, "BETA-caps")["tables"].append(table)

    return mutate


@pytest.mark.parametrize(
    "mutate",
    [
        drop_sheet_of_table,
        table_with_both,
        cluster_table_with(file=REL),
        cluster_table_with(sheet="model#01"),
        lambda m: part(m, "ALPHA-caps")["sheets"][0]["views"].append({"bbox": [0, 0, 1000]}),
        lambda m: part(m, "ALPHA-caps")["sheets"][0]["views"].append({"bbox": [0, 0, 1000, 500, 1]}),
        lambda m: part(m, "ALPHA-caps")["sheets"][0].update(sheet="model01"),
        lambda m: m["blocks"][0].update(grid_system_ids=["G1"]),
        lambda m: part(m, "ALPHA-caps").update(producer_questions=["Q1"]),
        beta_cluster_table(sheet="model01"),
        beta_cluster_table(side="up"),
        beta_cluster_table(file=""),
    ],
    ids=[
        "table-file-only",
        "table-sheet-and-cluster",
        "table-cluster-and-file",
        "table-cluster-and-sheet",
        "bbox-3",
        "bbox-5",
        "sheet-no-number",
        "grid-system-id",
        "producer-question",
        "cluster-sheet",
        "cluster-side",
        "cluster-file",
    ],
)
def test_more_bad_values_are_schema_problems(capsys, work, mutate):
    manifest = example_manifest()
    mutate(manifest)
    assert validate("parts-manifest", manifest)
    code, out, _ = check(capsys, work, manifest)
    assert code == 1 and {p["code"] for p in out["problems"]} == {"schema"}


# --- records of a part the manifest does not list ----------------------------------------------------------

ORPHAN, OTHER_ORPHAN = "ALPHA-gone", "BETA-gone"


def record_finding(capsys, work: Path, part_id: str, value: str = "v") -> str:
    """A reader finding tagged with `part_id`, written through `harness finding add` (no manifest: any id)."""
    put(work, None)
    entry = json.loads((work / "text" / f"{REL}.json").read_text(encoding="utf-8"))["entries"][0]["id"]
    argv = ["finding", "add", str(work), "--kind", "structural_system", "--file", REL, "--entries", entry]
    code = main([*argv, "--value", value, "--field", "aspect=floors", "--part", part_id])
    cap = capsys.readouterr()
    assert code == 0, cap.err
    return str(json.loads(cap.out)["id"])


def record_question(capsys, work: Path, *part_ids: str) -> str:
    """A reader question held by `part_ids`, written through `harness ask` (no manifest: any id)."""
    put(work, None)
    argv = ["ask", str(work), "--code", "label_unclear", "--file", REL, "--sheet", "model#01"]
    argv += ["--where", "grid A", "--found", "A or 4?", "--text", "Is this A or 4?"]
    qid = ""
    for part_id in part_ids:
        code = main([*argv, "--part", part_id])
        cap = capsys.readouterr()
        assert code == 0, cap.err
        qid = json.loads(cap.out)["id"]
    return qid


def withdraw_finding_record(capsys, work: Path, finding_id: str, part_id: str) -> None:
    put(work, None)
    argv = ["finding", "withdraw", str(work), finding_id, "--reason", "wrong", "--part", part_id]
    assert main(argv) == 0
    capsys.readouterr()


def orphan_rows(capsys, work: Path) -> list[dict[str, Any]]:
    code, out, _ = check(capsys, work, example_manifest())
    assert validate("part-output", out) == []
    rows = [p for p in out["problems"] if p["code"] == "record_part_unknown"]
    assert code == (1 if rows else 0) and {p["code"] for p in out["problems"]} <= {"record_part_unknown"}
    return rows


def test_no_findings_and_no_questions_file_give_no_record_part_unknown(capsys, copied):
    assert not (copied / "reader-findings.json").exists()
    assert not (copied / "reader-questions.json").exists()
    assert orphan_rows(capsys, copied) == []


def test_a_finding_of_a_listed_part_is_not_an_orphan(capsys, copied):
    record_finding(capsys, copied, "ALPHA-piles")
    assert orphan_rows(capsys, copied) == []


def test_a_finding_tagged_with_a_part_the_manifest_does_not_list_is_named(capsys, copied):
    fid = record_finding(capsys, copied, ORPHAN)
    (row,) = orphan_rows(capsys, copied)
    assert (row["part"], row["file"], row["sheet"]) == (ORPHAN, None, None)
    assert f"tagged on {fid} but not in parts/manifest.json" in row["detail"]


def test_a_withdrawn_finding_does_not_count(capsys, copied):
    fid = record_finding(capsys, copied, ORPHAN)
    withdraw_finding_record(capsys, copied, fid, ORPHAN)
    assert (
        json.loads((copied / "reader-findings.json").read_text(encoding="utf-8"))["findings"][0]["status"]
        == "withdrawn"
    )
    assert orphan_rows(capsys, copied) == []


def test_a_withdrawn_finding_does_not_hide_an_active_one_of_the_same_part(capsys, copied):
    gone = record_finding(capsys, copied, ORPHAN, "first")
    withdraw_finding_record(capsys, copied, gone, ORPHAN)
    live = record_finding(capsys, copied, ORPHAN, "second")
    (row,) = orphan_rows(capsys, copied)
    assert live in row["detail"] and gone not in row["detail"]


def test_a_question_held_by_a_part_the_manifest_does_not_list_is_named(capsys, copied):
    qid = record_question(capsys, copied, ORPHAN)
    (row,) = orphan_rows(capsys, copied)
    assert (row["part"], row["file"], row["sheet"]) == (ORPHAN, None, None)
    assert f"tagged on {qid} but not in parts/manifest.json" in row["detail"]


def test_a_question_with_one_listed_and_one_unlisted_part_names_only_the_unlisted(capsys, copied):
    qid = record_question(capsys, copied, "ALPHA-piles", ORPHAN)
    held = json.loads((copied / "reader-questions.json").read_text(encoding="utf-8"))["questions"][0]["parts"]
    assert held == ["ALPHA-piles", ORPHAN]
    (row,) = orphan_rows(capsys, copied)
    assert row["part"] == ORPHAN and qid in row["detail"]


def test_a_question_whose_parts_are_all_listed_is_not_an_orphan(capsys, copied):
    record_question(capsys, copied, "ALPHA-piles", "BETA-caps")
    assert orphan_rows(capsys, copied) == []


def test_one_row_per_unknown_part_naming_its_findings_and_questions_sorted(capsys, copied):
    f_first = record_finding(capsys, copied, ORPHAN, "first")
    f_second = record_finding(capsys, copied, ORPHAN, "second")
    q_first = record_question(capsys, copied, ORPHAN)
    f_other = record_finding(capsys, copied, OTHER_ORPHAN)
    rows = orphan_rows(capsys, copied)
    assert [r["part"] for r in rows] == [ORPHAN, OTHER_ORPHAN]
    assert f"tagged on {f_first}, {f_second}, {q_first} but not in parts/manifest.json" in rows[0]["detail"]
    assert f"tagged on {f_other} but" in rows[1]["detail"]


def test_a_finding_and_a_question_of_the_same_part_share_one_row(capsys, copied):
    fid = record_finding(capsys, copied, ORPHAN)
    qid = record_question(capsys, copied, ORPHAN)
    (row,) = orphan_rows(capsys, copied)
    assert f"tagged on {fid}, {qid} but" in row["detail"]


def test_the_detail_lists_at_most_ten_ids_then_an_ellipsis(capsys, copied):
    ids = [record_finding(capsys, copied, ORPHAN, f"v{n}") for n in range(11)]
    (row,) = orphan_rows(capsys, copied)
    assert ids[10] not in row["detail"]
    assert f"tagged on {', '.join(ids[:10])}, … but not in" in row["detail"]


def test_exactly_ten_ids_have_no_ellipsis(capsys, copied):
    for n in range(10):
        record_finding(capsys, copied, ORPHAN, f"v{n}")
    (row,) = orphan_rows(capsys, copied)
    assert ", … but not in" not in row["detail"] and "F-010 but not in" in row["detail"]


def test_the_detail_names_the_commands_that_clear_the_orphan(capsys, copied):
    record_finding(capsys, copied, ORPHAN)
    (row,) = orphan_rows(capsys, copied)
    assert "harness finding withdraw" in row["detail"] and f"--part {ORPHAN}" in row["detail"]
    assert "harness ask --withdraw" in row["detail"]


def test_records_are_not_read_when_the_manifest_fails_its_schema(capsys, copied):
    record_finding(capsys, copied, ORPHAN)
    manifest = example_manifest()
    manifest["schema_version"] = "0.2"
    code, out, _ = check(capsys, copied, manifest)
    assert code == 1 and {p["code"] for p in out["problems"]} == {"schema"}


@pytest.mark.parametrize(
    ("name", "tool"), [("reader-findings.json", "finding"), ("reader-questions.json", "ask")]
)
def test_a_corrupt_record_file_is_exit_1_naming_the_file_with_no_json(capsys, copied, name, tool):
    put(copied, example_manifest())
    (copied / name).write_text("{ not json", encoding="utf-8")
    code, out, err = raw(capsys, copied)
    assert (code, out) == (1, "") and name in err and "Traceback" not in err


@pytest.mark.parametrize(("name", "doc"), [("reader-findings.json", {"x": 1}), ("reader-questions.json", [])])
def test_a_record_file_that_breaks_its_schema_is_exit_1_naming_the_file(capsys, copied, name, doc):
    put(copied, example_manifest())
    (copied / name).write_text(json.dumps(doc), encoding="utf-8")
    code, out, err = raw(capsys, copied)
    assert (code, out) == (1, "") and name in err


# --- output form, usage errors, locking --------------------------------------------------------------------


def test_problems_are_sorted_and_two_runs_give_the_same_bytes(capsys, work):
    manifest = example_manifest()
    part(manifest, "ALPHA-caps")["sheets"].append(sheet_ref("model#09"))
    part(manifest, "ALPHA-caps")["inputs"].append("ghost")
    part(manifest, "BETA-caps")["block"] = "GAMMA"
    part(manifest, "ALPHA-piles")["clusters"] = []
    part(manifest, "scout")["sheets"] = []
    part(manifest, "all-notes-materials")["sheets"] = [sheet_ref(f"model#0{n}") for n in range(1, 6)]
    manifest["parts"].reverse()
    put(work, manifest)
    outs = []
    for _ in range(2):
        assert main(["part", "manifest-check", str(work)]) == 1
        outs.append(capsys.readouterr().out)
    assert outs[0] == outs[1]
    out = json.loads(outs[0])
    assert [p["code"] for p in out["problems"]] == [
        "block_unknown",
        "cluster_uncovered",
        "input_unknown",
        "part_kind_mismatch",
        "part_over_cap",
        "sheet_unknown",
        "table_outside_part",
    ]
    assert keys(out) == sorted(keys(out), key=lambda k: tuple("" if v is None else v for v in k))


def test_problems_of_one_code_are_sorted_by_part_then_file_then_sheet(capsys, work):
    manifest = example_manifest()
    for pid in ("BETA-caps", "ALPHA-caps", "BETA-piles"):
        part(manifest, pid)["inputs"] = ["ghost"]
    part(manifest, "all-grid-levels")["sheets"] = []
    part(manifest, "all-notes-materials")["sheets"] = []
    manifest["parts"].reverse()
    _, out, _ = check(capsys, work, manifest)
    assert keys(out) == [
        ("input_unknown", "ALPHA-caps", None, None),
        ("input_unknown", "BETA-caps", None, None),
        ("input_unknown", "BETA-piles", None, None),
        ("sheet_uncovered", None, REL, "model#05"),
        ("sheet_uncovered", None, REL, "model#06"),
    ]


def test_a_problem_that_two_rows_of_one_part_share_is_listed_once(capsys, work):
    manifest = example_manifest()
    part(manifest, "ALPHA-caps")["inputs"].append("ghost")
    manifest["parts"].append(copy.deepcopy(part(manifest, "ALPHA-caps")))
    _, out, _ = check(capsys, work, manifest)
    assert keys(out) == [
        ("duplicate_part_id", "ALPHA-caps", None, None),
        ("input_unknown", "ALPHA-caps", None, None),
    ]


def test_output_does_not_depend_on_the_order_of_the_parts(capsys, work):
    manifest = example_manifest()
    part(manifest, "ALPHA-caps")["sheets"].append(sheet_ref("model#09"))
    part(manifest, "BETA-caps")["inputs"].append("ghost")
    _, first, _ = check(capsys, work, manifest)
    manifest["parts"].reverse()
    _, second, _ = check(capsys, work, manifest)
    assert first == second


def test_missing_work_folder_is_a_usage_error(capsys, tmp_path):
    code = main(["part", "manifest-check", str(tmp_path / "nope")])
    cap = capsys.readouterr()
    assert code == 2 and cap.out == "" and "nope" in cap.err


def test_work_folder_without_an_inventory_is_a_usage_error(capsys, tmp_path):
    code = main(["part", "manifest-check", str(tmp_path)])
    cap = capsys.readouterr()
    assert code == 2 and cap.out == "" and "inventory.json" in cap.err


# --- the manifest path and how it is read (one shared rule, exit 3 for the operating system) -------------


def raw(capsys, work: Path) -> tuple[int, str, str]:
    """Run the command and return (exit code, stdout, stderr) without parsing stdout."""
    code = main(["part", "manifest-check", str(work)])
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def only_problem(out: str) -> dict[str, Any]:
    doc = json.loads(out)
    assert validate("part-output", doc) == []
    assert [p["code"] for p in doc["problems"]] == ["schema"] and doc["ok"] is False
    return doc["problems"][0]


needs_permissions = pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="chmod 000 is no barrier on Windows or for root",
)


@needs_permissions
def test_an_unreadable_manifest_is_exit_3_with_no_json(capsys, copied):
    put(copied, example_manifest())
    path = copied / MANIFEST
    path.chmod(0)
    try:
        code, out, err = raw(capsys, copied)
    finally:
        path.chmod(0o644)
    assert (code, out) == (3, "") and "manifest.json" in err and "Traceback" not in err


@needs_permissions
def test_an_unreadable_parts_folder_is_exit_3_with_no_json(capsys, copied):
    put(copied, example_manifest())
    folder = copied / MANIFEST.parent
    folder.chmod(0)
    try:
        code, out, err = raw(capsys, copied)
    finally:
        folder.chmod(0o755)
    assert (code, out) == (3, "") and "manifest.json" in err and "Traceback" not in err


def test_a_directory_at_the_manifest_path_is_a_schema_problem(capsys, copied):
    put(copied, None)
    (copied / MANIFEST).mkdir(parents=True)
    code, out, _ = raw(capsys, copied)
    problem = only_problem(out)
    assert code == 1 and "is not a regular file" in problem["detail"]
    assert str(copied) not in problem["detail"]


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_a_dangling_symlink_at_the_manifest_path_is_not_a_regular_file(capsys, copied):
    put(copied, None)
    (copied / MANIFEST).symlink_to(copied / "nowhere.json")
    code, out, _ = raw(capsys, copied)
    problem = only_problem(out)
    assert code == 1 and "is not a regular file" in problem["detail"]
    assert str(copied) not in problem["detail"]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no named pipes here")
def test_a_fifo_at_the_manifest_path_is_a_schema_problem_and_does_not_hang(capsys, copied):
    put(copied, None)
    path = copied / MANIFEST
    mkfifo = getattr(os, "mkfifo", None)  # by name: the type checker has no `os.mkfifo` on Windows
    assert mkfifo is not None  # the skipif above guarantees it
    mkfifo(path)
    result: list[tuple[int, str, str]] = []
    thread = threading.Thread(target=lambda: result.append(raw(capsys, copied)), daemon=True)
    thread.start()
    thread.join(10)
    if thread.is_alive():  # today's code blocks in open(): release it, then fail
        fd = os.open(path, os.O_RDWR)
        os.close(fd)
        thread.join(5)
        pytest.fail("the command hangs on a named pipe at the manifest path")
    code, out, _ = result[0]
    problem = only_problem(out)
    assert code == 1 and "is not a regular file" in problem["detail"]


def test_a_missing_manifest_detail_has_no_absolute_path(capsys, work):
    put(work, None)
    code, out, _ = raw(capsys, work)
    problem = only_problem(out)
    assert code == 1 and "is missing" in problem["detail"] and str(work) not in problem["detail"]


def test_a_manifest_that_is_not_utf_8_is_a_schema_problem(capsys, work):
    path = work / MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'{"schema_version": "0.1", "blocks": [], "parts": [], "x": "\xff\xfe"}')
    try:
        code, out, _ = raw(capsys, work)
    finally:
        path.unlink()
    problem = only_problem(out)
    assert code == 1 and "UTF-8" in problem["detail"] and str(work) not in problem["detail"]


def test_a_duplicate_key_in_the_manifest_is_a_schema_problem(capsys, work):
    text = '{"schema_version": "0.1", "schema_version": "0.1", "blocks": [], "parts": []}'
    code, out, _ = check(capsys, work, text)
    assert code == 1 and [p["code"] for p in out["problems"]] == ["schema"]
    assert "duplicate key 'schema_version'" in out["problems"][0]["detail"]


def test_nan_in_the_manifest_is_a_schema_problem(capsys, work):
    manifest = example_manifest()
    part(manifest, "ALPHA-caps")["sheets"][0]["views"] = [{"bbox": [0, 0, float("nan"), 500]}]
    code, out, _ = check(capsys, work, json.dumps(manifest))
    assert code == 1 and [p["code"] for p in out["problems"]] == ["schema"]
    assert "NaN is not allowed" in out["problems"][0]["detail"]


# --- inputs that cannot be read -------------------------------------------------------------------------


def test_a_missing_sheets_document_is_a_usage_error_not_a_manifest_problem(capsys, copied):
    (copied / STRUCTURE_DIR / f"{REL}.sheets.json").unlink()
    put(copied, example_manifest())
    code, out, err = raw(capsys, copied)
    assert (code, out) == (2, "") and "read-structure" in err and "sheets.json" in err


@needs_permissions
@pytest.mark.parametrize("target", ["text-index", "inventory"])
def test_an_unreadable_input_file_is_exit_3_with_no_json(capsys, copied, target):
    put(copied, example_manifest())
    path = copied / ("inventory.json" if target == "inventory" else f"text/{REL}.json")
    path.chmod(0)
    try:
        code, out, err = raw(capsys, copied)
    finally:
        path.chmod(0o644)
    assert (code, out) == (3, "") and path.name in err and "Traceback" not in err


@needs_permissions
def test_an_unreadable_work_folder_is_exit_3_without_a_traceback(capsys, copied):
    put(copied, example_manifest())
    copied.chmod(0)
    try:
        code, out, err = raw(capsys, copied)
    finally:
        copied.chmod(0o755)
    assert (code, out) == (3, "") and err and "Traceback" not in err


@needs_permissions
@pytest.mark.parametrize("name", ["reader-findings.json", "reader-questions.json"])
def test_an_unreadable_record_file_is_exit_3_naming_the_file(capsys, copied, name):
    if name == "reader-findings.json":
        record_finding(capsys, copied, "ALPHA-piles")
    else:
        record_question(capsys, copied, "ALPHA-piles")
    put(copied, example_manifest())
    path = copied / name
    path.chmod(0)
    try:
        code, out, err = raw(capsys, copied)
    finally:
        path.chmod(0o644)
    assert (code, out) == (3, "") and name in err and "Traceback" not in err


def test_the_command_runs_the_handler_of_its_action(work):
    args = build_parser().parse_args(["part", "manifest-check", str(work)])
    assert args.handler is pm()._run_manifest_check


def test_the_command_writes_nothing(capsys, work):
    put(work, example_manifest())
    before = {p: p.read_bytes() for p in sorted(work.rglob("*")) if p.is_file()}
    main(["part", "manifest-check", str(work)])
    capsys.readouterr()
    assert {p: p.read_bytes() for p in sorted(work.rglob("*")) if p.is_file()} == before


def test_part_is_classified_per_action_and_manifest_check_takes_no_lock(capsys, work):
    import tekla_harness.cli as cli

    assert cli.LOCKED_ACTIONS["part"] == frozenset({"receipt", "conflicts", "spotcheck", "answer-key"})
    args = build_parser().parse_args(["part", "manifest-check", str(work)])
    assert args.command == "part" and args.action == "manifest-check"
    assert _lock_target(args) is None
    put(work, example_manifest())
    with work_lock(work, "grid-system"):  # a writer holds the work folder
        assert main(["part", "manifest-check", str(work)]) == 0
    capsys.readouterr()


def test_every_part_action_is_checked_against_the_locked_list():
    """A new `part` action must be put on the locked list or stay read-only on purpose."""
    import argparse

    import tekla_harness.cli as cli

    part_parser = next(
        a for a in build_parser()._actions if isinstance(a, argparse._SubParsersAction)
    ).choices["part"]
    actions = next(a for a in part_parser._actions if isinstance(a, argparse._SubParsersAction)).choices
    read_only = {"manifest-check", "check", "chain", "review-sample", "score"}
    assert set(actions) == read_only | set(cli.LOCKED_ACTIONS["part"])


# --- E4b-1: the drawing warnings, acks, `skipped`, the exit rule, order, grid systems ---------------------

SHEETS_DOC = f"{STRUCTURE_DIR}/{REL}.sheets.json"
TEXT_DOC = f"text/{REL}.json"
ENTRY_OF = {"s1k1": 0, "s1k2": 1}  # texts of sheet 1, in the order of SHEET_TEXTS[1]


def entry_id(work: Path, text: str) -> str:
    index = json.loads((work / TEXT_DOC).read_text(encoding="utf-8"))
    return next(e["id"] for e in index["entries"] if e["display_text"] == text)


def candidate(work: Path, text: str, field: str, value: str = "B") -> dict[str, Any]:
    eid = entry_id(work, text)
    return {
        "field": field,
        "value": value,
        "evidence": {
            "kind": "adjacent_label",
            "key": field.upper(),
            "value_text_id": eid,
            "label_text_id": None,
            "position": [0.0, 0.0],
        },
        "confidence": "medium",
        "provenance": {
            "file": REL,
            "sheet": "model#01",
            "method": "dxf_entity",
            "region": {"bbox": [0, 0, 1, 1]},
        },
    }


def place(work: Path, text: str, u: float, v: float) -> None:
    """Move an indexed text of sheet 1 (frame 0..1000 on both axes) to (u, v); its box is a point."""
    path = work / TEXT_DOC
    index = json.loads(path.read_text(encoding="utf-8"))
    for e in index["entries"]:
        if e["display_text"] == text:
            e["position"] = {"x": u * 1000.0, "y": v * 1000.0, "basis": "text_midpoint"}
    path.write_text(json.dumps(index), encoding="utf-8")


def set_candidates(work: Path, cands: list[dict[str, Any]]) -> None:
    path = work / SHEETS_DOC
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["sheets"][0]["title_block"]["candidates"] = cands
    path.write_text(json.dumps(doc), encoding="utf-8")


def revision_at(work: Path, u: float, v: float, text: str = "s1k1") -> str:
    """A `revision` candidate at (u, v) on sheet 1; returns the id of the warning it should raise."""
    place(work, text, u, v)
    set_candidates(work, [candidate(work, text, "revision")])
    return f"revision_from_table|{REL}|model#01|{entry_id(work, text)}"


def warnings_of(out: dict[str, Any]) -> list[str]:
    return [w["id"] for w in out["warnings"]]


def test_revision_outside_the_zone_warns(capsys, copied):
    wid = revision_at(copied, 0.434, 0.589)
    # a title field that is not a revision, and a revision inside the zone, raise nothing
    set_candidates(
        copied,
        [
            candidate(copied, "s1k1", "revision"),
            candidate(copied, "s1k2", "scale", "1:50"),
        ],
    )
    place(copied, "s1k2", 0.5, 0.5)
    code, out, err = check(capsys, copied, example_manifest())
    assert code == 1 and out["ok"] is False and out["problems"] == []
    assert validate("part-output", out) == []
    assert warnings_of(out) == [wid]
    w = out["warnings"][0]
    assert (w["code"], w["part"], w["file"], w["sheet"], w["acked"], w["ack"]) == (
        "revision_from_table",
        None,
        REL,
        "model#01",
        False,
        None,
    )
    assert "0.434" in w["detail"] and "0.589" in w["detail"]
    assert "1 unacknowledged warning(s)" in err


def test_a_revision_candidate_that_was_not_chosen_still_counts(capsys, copied):
    place(copied, "s1k1", 0.4, 0.6)
    place(copied, "s1k2", 0.9, 0.9)
    set_candidates(
        copied, [candidate(copied, "s1k2", "revision"), candidate(copied, "s1k1", "revision", "C")]
    )
    code, out, _ = check(capsys, copied, example_manifest())
    assert code == 1 and warnings_of(out) == [
        f"revision_from_table|{REL}|model#01|{entry_id(copied, 's1k1')}"
    ]


@pytest.mark.parametrize(
    ("u", "v", "warns"),
    [
        (0.75, 0.5, False),  # the right band starts at u = 0.75
        (0.749, 0.5, True),
        (0.9, 0.9, False),
        (0.5, 0.20, False),  # the bottom band ends at v = 0.20
        (0.5, 0.201, True),
        (0.1, 0.05, False),
        (0.5, 0.5, True),
    ],
)
def test_revision_in_right_or_bottom_band_is_quiet(capsys, copied, u, v, warns):
    wid = revision_at(copied, u, v)
    code, out, _ = check(capsys, copied, example_manifest())
    assert warnings_of(out) == ([wid] if warns else [])
    assert code == (1 if warns else 0)


def test_revision_without_a_position_is_skipped(capsys, copied):
    set_candidates(copied, [candidate(copied, "s1k1", "revision")])
    doc = json.loads((copied / SHEETS_DOC).read_text(encoding="utf-8"))
    doc["sheets"][0]["title_block"]["candidates"][0]["evidence"]["value_text_id"] = "T999999"
    (copied / SHEETS_DOC).write_text(json.dumps(doc), encoding="utf-8")
    code, out, _ = check(capsys, copied, example_manifest())
    assert code == 0 and out["warnings"] == []
    assert {"code": "revision_from_table", "file": REL, "sheet": "model#01", "reason": "no_position"} in out[
        "skipped"
    ]


def test_a_revision_outside_the_zone_warns_on_a_sheet_of_any_part(capsys, copied):
    """Sheet 1 is only a notes sheet of a cross part: the rule covers every part, not the members."""
    manifest = example_manifest()
    for pid in ("ALPHA-piles", "ALPHA-piles-b", "ALPHA-caps"):
        part(manifest, pid)["sheets"] = [sheet_ref("model#02")]
    part(manifest, "all-grid-levels")["sheets"].append(sheet_ref("model#01", "notes"))
    wid = revision_at(copied, 0.5, 0.5)
    _, out, _ = check(capsys, copied, manifest)
    assert wid in warnings_of(out)


def test_two_revisions_without_a_position_are_one_skipped_row(capsys, copied):
    set_candidates(copied, [candidate(copied, "s1k1", "revision"), candidate(copied, "s1k2", "revision")])
    doc = json.loads((copied / SHEETS_DOC).read_text(encoding="utf-8"))
    for c in doc["sheets"][0]["title_block"]["candidates"]:
        c["evidence"]["value_text_id"] = "T999999"
    (copied / SHEETS_DOC).write_text(json.dumps(doc), encoding="utf-8")
    code, out, _ = check(capsys, copied, example_manifest())
    row = {"code": "revision_from_table", "file": REL, "sheet": "model#01", "reason": "no_position"}
    assert code == 0 and out["skipped"].count(row) == 1


def test_unacked_exits_1(capsys, copied):
    wid = revision_at(copied, 0.5, 0.5)
    code, out, err = check(capsys, copied, example_manifest())
    assert (code, out["ok"]) == (1, False) and out["problems"] == []
    assert "1 unacknowledged warning(s)" in err
    manifest = example_manifest()
    manifest["acks"] = [{"warning": wid, "reason": "the abbreviation table, no revision"}]
    code, out, err = check(capsys, copied, manifest)
    assert (code, out["ok"], err) == (0, True, "")
    assert out["warnings"][0]["acked"] is True


@pytest.mark.parametrize("kind", ["reason", "question", "both"])
def test_ack_by_question_or_reason_clears(capsys, copied, kind):
    wid = revision_at(copied, 0.5, 0.5)
    registry = json.loads((copied / "question-registry.json").read_text(encoding="utf-8"))
    qid = next(iter(registry["questions"].values()))["id"]
    ack: dict[str, Any] = {"warning": wid}
    if kind in ("reason", "both"):
        ack["reason"] = "accepted"
    if kind in ("question", "both"):
        ack["question"] = qid
    manifest = example_manifest()
    manifest["acks"] = [ack]
    code, out, _ = check(capsys, copied, manifest)
    assert (code, out["ok"], out["problems"]) == (0, True, [])
    assert out["warnings"][0]["acked"] is True
    assert out["warnings"][0]["ack"] == {k: v for k, v in ack.items() if k != "warning"}


def test_an_ack_names_a_warning_by_its_exact_id_only(capsys, copied):
    wid = revision_at(copied, 0.5, 0.5)
    manifest = example_manifest()
    manifest["acks"] = [
        {"warning": "revision_from_table", "reason": "by code"},
        {"warning": wid[:-2], "reason": "by prefix"},
        {"warning": wid + "x", "reason": "by a longer id"},
    ]
    code, out, _ = check(capsys, copied, manifest)
    assert code == 1 and out["warnings"][0]["acked"] is False
    assert [p["code"] for p in out["problems"]] == ["ack_unmatched"] * 3
    assert all(p["part"] is None for p in out["problems"])
    assert {p["detail"] for p in out["problems"]} >= {f"ack '{wid}x' matches no warning"}


def test_ack_unmatched_duplicate_unknown_are_problems(capsys, copied):
    wid = revision_at(copied, 0.5, 0.5)
    manifest = example_manifest()
    manifest["acks"] = [
        {"warning": wid, "reason": "first"},
        {"warning": wid, "reason": "second"},
        {"warning": "linework_duplicate|ghost|a.dxf|model#01|model#02", "reason": "no such warning"},
        {"warning": wid, "question": "Q-999"},
    ]
    code, out, _ = check(capsys, copied, manifest)
    assert code == 1 and validate("part-output", out) == []
    assert sorted(p["code"] for p in out["problems"]) == [
        "ack_duplicate",
        "ack_question_unknown",
        "ack_unmatched",
    ]
    by_code = {p["code"]: p["detail"] for p in out["problems"]}
    assert wid in by_code["ack_duplicate"] and "3" in by_code["ack_duplicate"]
    assert "Q-999" in by_code["ack_question_unknown"]
    assert "ghost" in by_code["ack_unmatched"]


def test_two_acks_of_one_id_are_a_duplicate(capsys, copied):
    wid = revision_at(copied, 0.5, 0.5)
    manifest = example_manifest()
    manifest["acks"] = [{"warning": wid, "reason": "first"}, {"warning": wid, "reason": "second"}]
    code, out, _ = check(capsys, copied, manifest)
    assert code == 1 and validate("part-output", out) == []
    assert keys(out) == [("ack_duplicate", None, None, None)]
    assert "2 acks" in out["problems"][0]["detail"]


def test_a_question_of_any_status_is_known(capsys, copied):
    wid = revision_at(copied, 0.5, 0.5)
    path = copied / "question-registry.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    entry = next(iter(registry["questions"].values()))
    entry["status"] = "obsolete"
    path.write_text(json.dumps(registry), encoding="utf-8")
    manifest = example_manifest()
    manifest["acks"] = [{"warning": wid, "question": entry["id"]}]
    code, out, _ = check(capsys, copied, manifest)
    assert (code, out["problems"]) == (0, [])


def test_acks_without_warnings_are_unmatched(capsys, work):
    manifest = shipped_manifest()  # its acks name warnings that this work folder does not raise
    code, out, _ = check(capsys, work, manifest)
    assert code == 1
    assert [p["code"] for p in out["problems"]].count("ack_unmatched") == 2


# --- the wiring of the two rules that read the drawings ---------------------------------------------------


def grid_world(work: Path) -> str:
    """Grids on sheets 1 and 2 (block ALPHA) and 3 (block BETA), all on one row: sheet 3 lines up with two
    sheets of ALPHA and with none of BETA. Returns the id of the warning of sheet 3."""
    from test_part_warnings import group, write_grids

    write_grids(work, [group(f"model#0{n}") for n in (1, 2, 3)], REL)
    return f"grid_origin_other_block|{REL}|model#03|ALPHA"


def test_grid_origin_warning_is_wired_and_unacked_exits_1(capsys, copied, monkeypatch):
    monkeypatch.setattr("tekla_harness.part_warnings.linework_warnings", lambda *a, **k: ([], []))
    wid = grid_world(copied)
    code, out, _ = check(capsys, copied, example_manifest())
    assert code == 1 and warnings_of(out) == [wid] and out["problems"] == []
    assert out["warnings"][0]["code"] == "grid_origin_other_block"
    assert {
        "code": "grid_origin_other_block",
        "file": REL,
        "sheet": "model#04",
        "reason": "no_plan_grid",
    } in out["skipped"]
    manifest = example_manifest()
    manifest["acks"] = [{"warning": wid, "reason": "the grids of the two blocks share one origin"}]
    code, out, _ = check(capsys, copied, manifest)
    assert (code, out["ok"]) == (0, True) and out["warnings"][0]["acked"] is True


def test_linework_warning_and_skips_are_wired_with_the_input_dir(capsys, copied, monkeypatch, tmp_path):
    seen: list[Any] = []
    warning = {
        "id": f"linework_duplicate|BETA-caps|{REL}|model#03|model#01",
        "code": "linework_duplicate",
        "part": "BETA-caps",
        "file": REL,
        "sheet": "model#03",
        "detail": "layers S-CAP-OUT: 30 of 30 items equal model#01 (ALPHA)",
    }
    skip = {"code": "linework_duplicate", "file": REL, "sheet": "model#04", "reason": "few_items"}

    def stub(
        work: Path, manifest: dict[str, Any], input_dir: Path | None = None, notes: list[str] | None = None
    ):
        seen.append((work, input_dir))
        return [warning], [skip]

    monkeypatch.setattr("tekla_harness.part_warnings.linework_warnings", stub)
    put(copied, example_manifest())
    code = main(["part", "manifest-check", str(copied), "--input-dir", str(tmp_path / "in")])
    out = json.loads(capsys.readouterr().out)
    assert code == 1 and seen == [(copied, tmp_path / "in")]
    assert out["warnings"] == [{**warning, "acked": False, "ack": None}]
    assert skip in out["skipped"] and validate("part-output", out) == []
    main(["part", "manifest-check", str(copied)])
    capsys.readouterr()
    assert seen[1][1] is None


def test_a_reader_error_of_the_geometry_walk_passes_through(capsys, copied):
    grid_world(copied)  # origins and a unit: the cap layers of the example are read from the native DXF
    put(copied, example_manifest())
    code, out, err = raw(capsys, copied)  # no --input-dir: a native DXF cannot be opened
    assert (code, out) == (2, "") and "--input-dir" in err


def check_with_input(
    capsys, copied: Path, work: Path, manifest: dict[str, Any]
) -> tuple[int, dict[str, Any], str]:
    """`check` with `--input-dir`, so that the linework rule can open the native DXF."""
    put(copied, manifest)
    code = main(["part", "manifest-check", str(copied), "--input-dir", str(work.parent / "input")])
    cap = capsys.readouterr()
    return code, json.loads(cap.out), cap.err


def test_the_shipped_example_acks_warnings_that_exist(capsys, copied, work):
    """Acks name warning ids, not codes: with the two warnings it names raised, and the question it cites
    in the registry, the example passes `ack_unmatched` and `ack_question_unknown`."""
    grid_world(copied)
    revision_at(copied, 0.5, 0.5)
    add_unread_file(copied, "plans/legacy.dxf")  # the file that the example's no_sheet part takes over
    code, out, _ = check_with_input(capsys, copied, work, shipped_manifest())
    codes = [p["code"] for p in out["problems"]]
    assert "ack_unmatched" not in codes and "ack_question_unknown" not in codes
    assert (code, out["ok"]) == (0, True)
    assert [w["acked"] for w in out["warnings"]] == [True, True] and validate("part-output", out) == []


def test_check_writes_nothing(capsys, copied, work):
    grid_world(copied)
    revision_at(copied, 0.5, 0.5)
    put(copied, example_manifest())

    def tree() -> dict[Path, bytes]:
        roots = (copied, work.parent / "input")
        return {p: p.read_bytes() for root in roots for p in sorted(root.rglob("*")) if p.is_file()}

    before = tree()
    inputs = str(work.parent / "input")
    assert main(["part", "manifest-check", str(copied), "--input-dir", inputs]) == 1
    capsys.readouterr()
    assert tree() == before


def test_output_validates_against_part_output(capsys, copied, work):
    gid = grid_world(copied)
    rid = revision_at(copied, 0.3, 0.7)
    manifest = example_manifest()
    manifest["acks"] = [{"warning": rid, "reason": "table of abbreviations"}]
    put(copied, manifest)
    code = main(["part", "manifest-check", str(copied), "--input-dir", str(work.parent / "input")])
    out = json.loads(capsys.readouterr().out)
    assert validate("part-output", out) == []
    assert warnings_of(out) == sorted([gid, rid]) and code == 1
    assert [w["acked"] for w in out["warnings"]] == [w == rid for w in warnings_of(out)]
    assert out["skipped"] == sorted(
        out["skipped"], key=lambda s: (s["file"], s["sheet"], s["code"], s["reason"])
    )


# --- order, grid systems (E4a review 1, D6) ---------------------------------------------------------------


@pytest.mark.parametrize(("order", "flagged"), [(1, True), (2, True), (3, False)])
def test_order_not_after_input(capsys, work, order, flagged):
    """ALPHA-caps has the input ALPHA-piles of order 2: an equal or lower order is a problem."""
    manifest = example_manifest()
    part(manifest, "ALPHA-caps")["order"] = order
    code, out, _ = check(capsys, work, manifest)
    rows = [k for k in keys(out) if k[0] == "order_not_after_input"]
    assert rows == ([("order_not_after_input", "ALPHA-caps", None, None)] if flagged else [])
    assert code == (1 if flagged else 0)
    if flagged:
        detail = next(p["detail"] for p in out["problems"] if p["code"] == "order_not_after_input")
        assert "ALPHA-piles" in detail and str(order) in detail and "2" in detail


def test_order_is_checked_for_every_input(capsys, work):
    manifest = example_manifest()
    part(manifest, "all-assembly")["order"] = 3  # inputs: ALPHA-caps (3) and BETA-caps (3)
    _, out, _ = check(capsys, work, manifest)
    details = [p["detail"] for p in out["problems"] if p["code"] == "order_not_after_input"]
    assert (
        len(details) == 2
        and any("ALPHA-caps" in d for d in details)
        and any("BETA-caps" in d for d in details)
    )


def test_grid_system_unknown_for_an_id_grid_systems_json_does_not_hold(capsys, copied):
    manifest = example_manifest()
    manifest["blocks"][0]["grid_system_ids"] = ["S001", "S777"]
    code, out, _ = check(capsys, copied, manifest)
    assert code == 1 and keys(out) == [("grid_system_unknown", None, None, None)]
    detail = out["problems"][0]["detail"]
    assert "ALPHA" in detail and "S777" in detail
    assert detail.endswith("which grid-systems.json does not hold") and "missing" not in detail


def test_every_listed_grid_system_is_unknown_when_the_file_is_absent(capsys, copied):
    (copied / "grid-systems.json").unlink()
    code, out, _ = check(capsys, copied, example_manifest())
    assert code == 1 and keys(out) == [("grid_system_unknown", None, None, None)] * 2
    assert {"S001", "S002"} == {s for p in out["problems"] for s in ("S001", "S002") if s in p["detail"]}
    assert sorted(p["detail"] for p in out["problems"]) == [
        f"block '{block}' lists grid system '{sid}', but grid-systems.json is missing "
        "(run `harness grid-system`)"
        for block, sid in (("ALPHA", "S001"), ("BETA", "S002"))
    ]


def test_an_invalid_grid_systems_file_is_exit_1_naming_the_file(capsys, copied):
    put(copied, example_manifest())
    (copied / "grid-systems.json").write_text(json.dumps({"systems": []}), encoding="utf-8")
    code, out, err = raw(capsys, copied)
    assert (code, out) == (1, "") and "grid-systems.json" in err and "Traceback" not in err
    (copied / "grid-systems.json").write_text("{ not json", encoding="utf-8")
    code, out, err = raw(capsys, copied)
    assert (code, out) == (1, "") and "grid-systems.json" in err


@needs_permissions
def test_an_unreadable_grid_systems_file_is_exit_3(capsys, copied):
    put(copied, example_manifest())
    path = copied / "grid-systems.json"
    path.chmod(0)
    try:
        code, out, err = raw(capsys, copied)
    finally:
        path.chmod(0o644)
    assert (code, out) == (3, "") and "grid-systems.json" in err


@needs_permissions
def test_an_unreadable_grids_document_is_exit_3(capsys, copied):
    grid_world(copied)
    put(copied, example_manifest())
    path = copied / "structure" / f"{REL}.grids.json"
    path.chmod(0)
    try:
        code, out, err = raw(capsys, copied)
    finally:
        path.chmod(0o644)
    assert (code, out) == (3, "") and "grids.json" in err


def test_a_cycle_is_also_an_order_problem(capsys, work):
    manifest = example_manifest()
    part(manifest, "ALPHA-piles")["inputs"].append("ALPHA-caps")  # piles (2) would wait on caps (3)
    _, out, _ = check(capsys, work, manifest)
    codes = [p["code"] for p in out["problems"]]
    assert "input_cycle" in codes and "order_not_after_input" in codes


# --- unit answers that cannot be read (DECISIONS 7, item 6) -----------------------------------------------


def test_an_unreadable_answers_ledger_is_a_problem_and_the_file_is_skipped(capsys, copied, work):
    grid_world(copied)
    (copied / "answers.json").write_text("{not json", encoding="utf-8")
    code, out, _ = check_with_input(capsys, copied, work, example_manifest())
    assert code == 1 and out["ok"] is False and validate("part-output", out) == []
    assert keys(out) == [("unit_answer_unread", None, REL, None)]
    assert "answers.json" in out["problems"][0]["detail"] and REL in out["problems"][0]["detail"]
    assert out["warnings"] == []  # the declared mm is not used: no grid warning
    assert {
        "code": "grid_origin_other_block",
        "file": REL,
        "sheet": "model#03",
        "reason": "unit_unknown",
    } in out["skipped"]


def test_a_file_without_a_units_answer_is_a_problem_and_the_declared_unit_is_not_used(capsys, copied, work):
    """D1: the declared unit is mm, and the grids line up; with no answer neither rule measures."""
    grid_world(copied)
    (copied / "answers.json").unlink()
    inv = json.loads((copied / "inventory.json").read_text(encoding="utf-8"))
    row = next(r for r in inv["files"] if r["path"] == REL)
    row["units"] = {**(row["units"] or {}), "value": "mm"}
    (copied / "inventory.json").write_text(json.dumps(inv), encoding="utf-8")
    manifest = example_manifest()
    manifest["acks"] = [{"warning": "unit_unanswered", "reason": "by code"}]
    code, out, _ = check_with_input(capsys, copied, work, manifest)
    assert code == 1 and out["ok"] is False and validate("part-output", out) == []
    assert [p for p in keys(out) if p[0] != "ack_unmatched"] == [("unit_unanswered", None, REL, None)]
    problem = next(p for p in out["problems"] if p["code"] == "unit_unanswered")
    assert problem["detail"] == f"answer the units question of `{REL}` first"
    assert out["warnings"] == []
    assert {
        "code": "grid_origin_other_block",
        "file": REL,
        "sheet": "model#03",
        "reason": "unit_unknown",
    } in out["skipped"]


def test_a_missing_question_registry_is_a_usage_error_before_the_rules(capsys, copied):
    put(copied, example_manifest())
    (copied / "question-registry.json").unlink()
    code, out, err = raw(capsys, copied)
    assert (code, out) == (2, "") and "question-registry.json is missing" in err and "intake" in err
    manifest = example_manifest()
    manifest["acks"] = [{"warning": "revision_from_table|x|y|z", "question": "Q-001"}]
    put(copied, manifest)
    code, out, err = raw(capsys, copied)
    assert (code, out) == (2, "") and "intake" in err


def test_conflicting_unit_answers_are_a_problem_that_no_ack_clears(capsys, copied, work, monkeypatch):
    def conflicting(*args: Any, **kwargs: Any) -> Any:
        answers = [
            {"key": f"k{i}", "status": "active", "code": "units_confirm_all", "file": REL, "values": v}
            for i, v in enumerate(({"unit": "mm"}, {"unit": "m"}))
        ]
        return type("Ledger", (), {"answers": {"answers": answers}})()

    monkeypatch.setattr("tekla_harness.dimensions.load_ledger", conflicting)
    grid_world(copied)
    manifest = example_manifest()
    manifest["acks"] = [{"warning": "unit_answer_unread", "reason": "by code"}]
    code, out, _ = check_with_input(capsys, copied, work, manifest)
    assert code == 1 and out["warnings"] == []
    assert [p for p in keys(out) if p[0] == "unit_answer_unread"] == [("unit_answer_unread", None, REL, None)]
    detail = next(p["detail"] for p in out["problems"] if p["code"] == "unit_answer_unread")
    assert "no single valid unit" in detail and REL in detail
    assert "ack_unmatched" in [p["code"] for p in out["problems"]]
