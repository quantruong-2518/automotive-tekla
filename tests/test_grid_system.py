"""grid_system: project grid systems from the per-view grid families (synthetic fixtures only)."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest

from tekla_harness.grid_system import (
    BANNER,
    CHAR_WIDTH,
    GridSystemError,
    build_grid_systems,
    consumed_answers_digest,
    grid_system_questions,
    render_grid_system_svg,
    run_grid_systems,
)
from tekla_harness.grids import coordinate_string
from tekla_harness.intake import dump_json
from tekla_harness.questions import empty_registry, question_key
from tekla_harness.schemas import validate

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "schemas" / "examples" / "grid-system.example.json"


def gs_problems(doc: dict[str, Any]) -> list[str]:
    return [f"{p.path}: {p.message}" for p in validate("grid-system", doc)]


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# --- fixture builders ------------------------------------------------------------------------------


def fam(
    fid: str,
    labels: list[str],
    spacings: list[float],
    *,
    angle: float = 90.0,
    block: str | None = None,
    complete: bool = True,
    evidence: list[dict[str, Any]] | None = None,
    conf: str = "medium",
    offsets: list[float] | None = None,
) -> dict[str, Any]:
    if offsets is None:
        offsets = [0.0]
        for s in spacings:
            offsets.append(offsets[-1] + s)
    return {
        "fid": fid,
        "labels": labels,
        "offsets": offsets,
        "angle": angle,
        "block": block,
        "complete": complete,
        "evidence": evidence or [],
        "conf": conf,
    }


def view(gid: str, sheet: str, *families: dict[str, Any]) -> dict[str, Any]:
    return {"gid": gid, "sheet": sheet, "families": list(families)}


def _prov(file: str, sheet: str, method: str = "dxf_entity") -> dict[str, Any]:
    return {"file": file, "sheet": sheet, "method": method}


def _family_json(
    spec: dict[str, Any], file: str, sheet: str, unit: str, counter: list[int]
) -> dict[str, Any]:
    vertical = spec["angle"] == 90.0
    axes = []
    for lbl, off in zip(spec["labels"], spec["offsets"], strict=True):
        counter[0] += 1
        start, end = ([off, 0.0], [off, 30000.0]) if vertical else ([0.0, off], [30000.0, off])
        axes.append(
            {
                "axis_id": f"G{counter[0]:04d}",
                "label": {"value": lbl, "provenance": _prov(file, sheet), "confidence": spec["conf"]},
                "offset": off,
                "line": {
                    "start": start,
                    "end": end,
                    "handle": None,
                    "layer": "S-GRID",
                    "linetype": "DASHDOT",
                    "block_path": [spec["block"]] if spec["block"] else [],
                },
                "bubbles": [],
                "pairing": "line",
                "angle_deviation_deg": 0.0,
                "confidence": spec["conf"],
            }
        )
    spacings = []
    rounded = []
    for k in range(len(spec["offsets"]) - 1):
        measured = spec["offsets"][k + 1] - spec["offsets"][k]
        rounded.append(round(measured, 6))
        spacings.append(
            {
                "from_label": spec["labels"][k],
                "to_label": spec["labels"][k + 1],
                "measured": measured,
                "value": {
                    "value": round(measured, 6),
                    "provenance": _prov(file, sheet, "derived"),
                    "confidence": spec["conf"],
                },
                "dimension_evidence": [],
                "evidence": spec["evidence"] if k == 0 else [],
            }
        )
    proposal = None
    if len(axes) >= 2:
        proposal = {
            "status": "proposal",
            "coordinates": coordinate_string([v for v in rounded if v > 0]),
            "labels": " ".join(spec["labels"]),
            "unit": unit,
            "unit_confidence": "medium",
            "rounding_step": 1.0,
            "max_rounding_residual": 0.0,
            "complete": spec["complete"],
            "note": "synthetic",
        }
    return {
        "family_id": spec["fid"],
        "direction": [0.0, 1.0] if vertical else [1.0, 0.0],
        "normal": [1.0, 0.0] if vertical else [0.0, 1.0],
        "angle_deg": spec["angle"],
        "axes": axes,
        "spacings": spacings,
        "proposal": proposal,
        "unlabelled_lines": [],
    }


def _row(path: str, digest: str, example: Any, median: dict[str, Any] | None = None) -> dict[str, Any]:
    row = copy.deepcopy(example("intake")["files"][0])
    row["units"]["dimension_median"] = median  # none unless a test sets it: no contradiction test
    stem = path
    row.update(
        path=path,
        sha256=digest,
        probe=f"probe/{stem}.json",
        text_index=f"text/{stem}.json",
        converted=f"converted/{stem}.dxf",
    )
    return row


class Work:
    """A work folder with inventory.json, structure-summary.json and structure/<file>.{grids,sheets}.json."""

    def __init__(self, root: Path, example: Any) -> None:
        self.root = root
        self.example = example
        self.rows: list[dict[str, Any]] = []

    def add_file(
        self,
        path: str,
        views: list[dict[str, Any]],
        *,
        unit: str = "mm",
        duplicates: dict[str, str] | None = None,
        content: str | None = None,
        median: dict[str, Any] | None = None,
    ) -> None:
        duplicates = duplicates or {}
        dxf_sha = sha("dxf:" + (content or path))
        counter = [0]
        groups = []
        for v in views:
            groups.append(
                {
                    "group_id": v["gid"],
                    "sheet": v["sheet"],
                    "space": "model",
                    "bbox": [0.0, 0.0, 30000.0, 30000.0],
                    "families": [_family_json(f, path, v["sheet"], unit, counter) for f in v["families"]],
                }
            )
        file_obj = {
            "path": path,
            "sha256": dxf_sha,
            "confidence_cap": "medium",
            "declared_units": {"insunits": 4, "name": unit},
        }
        grids = {
            "schema_version": "0.1",
            "file": file_obj,
            "groups": groups,
            "cross_checks": [],
            "unpaired_bubbles": {"count": 0, "listed": []},
            "summary": {
                "circles": 0,
                "bubbles_labelled": 0,
                "bubbles_ambiguous_label": 0,
                "bubbles_other_text": 0,
                "bubbles_paired": 0,
                "axes": counter[0],
                "groups": len(groups),
                "families": sum(len(g["families"]) for g in groups),
                "isolated_axes": 0,
                "dimensions_linear": 0,
                "dimensions_matched": 0,
                "walk_skipped": {},
            },
            "questions": [],
            "warnings": [],
            "question_counts": {},
        }
        sheet_ids = sorted({v["sheet"] for v in views if v["sheet"] != "unknown"} | set(duplicates))
        sheets = {
            "schema_version": "0.1",
            "file": file_obj,
            "sheets": [
                {
                    "sheet_id": sid,
                    "space": "model",
                    "layout": "Model",
                    "coordinate_frame": "wcs",
                    "bbox": [0.0, 0.0, 84100.0, 59400.0],
                    "detection": {"method": "frame_rectangle", "confidence": "medium", "evidence": []},
                    "model_windows": [],
                    "text_ids": [],
                    "title_block": {"sheet_number": None, "revision": None, "candidates": []},
                    "duplicate_of": duplicates.get(sid),
                }
                for sid in sheet_ids
            ],
            "unassigned": {"text_ids": [], "ambiguous_text_ids": []},
            "drawing_list": {"status": "not_searched"},
            "summary": {
                "sheet_count": len(sheet_ids),
                "by_method": {"frame_rectangle": len(sheet_ids)},
                "text_entries": 0,
                "assigned": 0,
                "unassigned": 0,
                "ambiguous": 0,
                "frame_candidates_rejected": 0,
            },
            "questions": [],
            "warnings": [],
        }
        assert validate("grids", grids) == []
        assert validate("sheets", sheets) == []
        base = self.root / "structure" / path
        base.parent.mkdir(parents=True, exist_ok=True)
        Path(f"{base}.grids.json").write_text(json.dumps(grids), encoding="utf-8")
        Path(f"{base}.sheets.json").write_text(json.dumps(sheets), encoding="utf-8")
        self.rows.append(_row(path, sha(content or path), self.example, median))

    def finish(self) -> Path:
        inv = copy.deepcopy(self.example("intake"))
        inv["project_id"] = "demo-project"
        inv["files"] = sorted(self.rows, key=lambda r: r["path"])
        assert validate("intake", inv) == []
        data = dump_json(inv).encode("utf-8")
        (self.root / "inventory.json").write_bytes(data)
        summary = {"kind": "structure_summary", "inventory_sha256": hashlib.sha256(data).hexdigest()}
        (self.root / "structure-summary.json").write_text(json.dumps(summary), encoding="utf-8")
        return self.root


def ans(code: str, file: str | None, values: dict[str, Any], status: str = "active") -> dict[str, Any]:
    return {
        "key": f"{code}:{file}",
        "question_id": "Q-001",
        "code": code,
        "file": file,
        "answer_text": "synthetic",
        "values": values,
        "answered_by": "engineer",
        "answered_by_role": "engineer",
        "answered_on": "2026-11-06",
        "status": status,
    }


LETTERS = ["A", "B", "C", "D"]
LETTER_SP = [6000.0, 6000.0, 4500.0]
NUMBERS = ["1", "2", "3"]
NUMBER_SP = [7200.0, 7200.0]


def plan(gid: str, sheet: str, fid0: int, **kw: Any) -> dict[str, Any]:
    """A two-direction plan: letter axes (horizontal lines) x number axes (vertical lines)."""
    return view(
        gid,
        sheet,
        fam(f"F{fid0:03d}", LETTERS, LETTER_SP, angle=0.0, **kw),
        fam(f"F{fid0 + 1:03d}", NUMBERS, NUMBER_SP, angle=90.0, **kw),
    )


def expand(coordinates: str) -> int:
    """Number of relative entries in a Tekla coordinate string ('0 2*6000 4500' -> 4: 0 + 3 spacings)."""
    n = 0
    for tok in coordinates.split():
        m = re.fullmatch(r"(\d+)\*(.+)", tok)
        n += int(m.group(1)) if m else 1
    return n


def codes(doc: dict[str, Any]) -> list[str]:
    return [q["code"] for q in doc["questions"]]


def check_invariants(doc: dict[str, Any]) -> None:
    assert gs_problems(doc) == []
    for s in doc["systems"]:
        assert s["confidence"] in ("medium", "low")
        for d in s["directions"]:
            assert len(d["labels"]) == expand(d["coordinates"])
            assert len(d["labels"]) == len(d["spacings"]) + 1


# --- tests -----------------------------------------------------------------------------------------


def test_one_system_across_three_independent_views(tmp_path, example):
    w = Work(tmp_path, example)
    w.add_file(
        "plans.dxf", [plan("V001", "model#01", 1), plan("V002", "model#02", 3), plan("V003", "model#03", 5)]
    )
    doc = build_grid_systems(w.finish())
    check_invariants(doc)
    assert len(doc["systems"]) == 1
    s = doc["systems"][0]
    assert s["system_id"] == "S001"
    ev = s["evidence"]
    assert (ev["views"], ev["full_views"], ev["independent_views"], ev["sheets"], ev["files"]) == (
        3,
        3,
        3,
        3,
        1,
    )
    assert "single_source" not in s["flags"]
    assert s["confidence"] == "medium"
    assert sorted(d["coordinates"] for d in s["directions"]) == ["0 2*6000 4500", "0 2*7200"]
    assert {d["unit"] for d in s["directions"]} == {"mm"}
    assert len(ev["contributors"]) == 3
    assert {f["family_id"] for c in ev["contributors"] for f in c["families"]} == {
        f"F00{k}" for k in range(1, 7)
    }
    assert codes(doc).count("grid_system_select") == 1
    assert "grid_system_conflict" not in codes(doc)
    blocking = {q["code"] for q in doc["questions"] if q["blocking"]}
    assert blocking == {"grid_system_select", "grid_system_axis_unassigned"}  # units: intake's question


@pytest.mark.parametrize("how", ["duplicate_of", "same_block", "same_sheet", "evidence_not_independent"])
def test_copies_only_give_single_source_low(tmp_path, example, how):
    w = Work(tmp_path, example)
    kw: dict[str, Any] = {}
    second_sheet = "model#02"
    duplicates = None
    second_kw: dict[str, Any] = {}
    if how == "duplicate_of":
        duplicates = {"model#02": "model#01"}
    elif how == "same_block":
        kw = second_kw = {"block": "PLAN_BLOCK"}
    elif how == "same_sheet":
        second_sheet = "model#01"
    else:
        ref = "V001/F001 on sheet model#01: agrees (not independent: copied sheets)"
        ev = [{"kind": "other_view", "agrees": True, "independent": False, "ref": ref}]
        second_kw = {"evidence": ev}
    w.add_file(
        "plans.dxf",
        [plan("V001", "model#01", 1, **kw), plan("V002", second_sheet, 3, **second_kw)],
        duplicates=duplicates,
    )
    doc = build_grid_systems(w.finish())
    check_invariants(doc)
    assert len(doc["systems"]) == 1
    s = doc["systems"][0]
    assert s["evidence"]["full_views"] == 2
    assert s["evidence"]["independent_views"] == 1
    assert "single_source" in s["flags"]
    assert s["confidence"] == "low"


def test_single_view_is_single_source(tmp_path, example):
    w = Work(tmp_path, example)
    w.add_file("plans.dxf", [plan("V001", "model#01", 1)])
    s = build_grid_systems(w.finish())["systems"][0]
    assert "single_source" in s["flags"] and s["confidence"] == "low"


def test_unparsable_evidence_ref_is_not_independent_and_warned(tmp_path, example):
    ev = [{"kind": "other_view", "agrees": True, "independent": True, "ref": "something else"}]
    w = Work(tmp_path, example)
    w.add_file("plans.dxf", [plan("V001", "model#01", 1), plan("V002", "model#02", 3, evidence=ev)])
    doc = build_grid_systems(w.finish())
    assert doc["systems"][0]["evidence"]["independent_views"] == 1
    assert any("cannot be parsed" in x for x in doc["warnings"])


def test_two_structures_same_labels_different_spacings_are_separate(tmp_path, example):
    other = [
        view(
            gid,
            sheet,
            fam(f"F{k:03d}", ["A", "B", "C"], [3600.0, 4800.0], angle=0.0),
            fam(f"F{k + 1:03d}", NUMBERS, [5400.0, 5400.0], angle=90.0),
        )
        for gid, sheet, k in (("V003", "model#03", 5), ("V004", "model#04", 7))
    ]
    w = Work(tmp_path, example)
    w.add_file("plans.dxf", [plan("V001", "model#01", 1), plan("V002", "model#02", 3), *other])
    doc = build_grid_systems(w.finish())
    check_invariants(doc)
    assert len(doc["systems"]) == 2
    s1, s2 = doc["systems"]
    groups1 = {c["group_id"] for c in s1["evidence"]["contributors"]}
    groups2 = {c["group_id"] for c in s2["evidence"]["contributors"]}
    assert groups1 == {"V001", "V002"} and groups2 == {"V003", "V004"}
    assert s1["relations"]["conflicts_with"] == ["S002"] and s2["relations"]["conflicts_with"] == ["S001"]
    conflicts = [q for q in doc["questions"] if q["code"] == "grid_system_conflict"]
    assert len(conflicts) == 1
    q = conflicts[0]
    assert q["blocking"] and "S001" in q["message"] and "S002" in q["message"]
    assert "A-B" in q["message"] and "1-2" in q["message"]
    assert q["where"] == "plans.dxf V001/F001 vs plans.dxf V003/F005"  # no positional system id
    # never averaged: each system keeps its own drawn spacings
    assert {d["coordinates"] for d in s2["directions"]} == {"0 3600 4800", "0 2*5400"}


@pytest.mark.parametrize(("second", "together"), [(6001.2, True), (6001.3, False)])
def test_drafting_tolerance_boundary(tmp_path, example, second, together):
    w = Work(tmp_path, example)
    w.add_file(
        "plans.dxf",
        [
            view(
                "V001",
                "model#01",
                fam("F001", ["A", "B", "C"], [6000.0, 4500.0], angle=0.0),
                fam("F002", NUMBERS, NUMBER_SP),
            ),
            view(
                "V002",
                "model#02",
                fam("F003", ["A", "B", "C"], [second, 4500.0], angle=0.0),
                fam("F004", NUMBERS, NUMBER_SP),
            ),
        ],
    )
    doc = build_grid_systems(w.finish())
    check_invariants(doc)
    if together:
        assert len(doc["systems"]) == 1
        s = doc["systems"][0]
        assert "within_drafting_tolerance" in s["flags"]
        letters = next(d for d in s["directions"] if d["labels"][0] == "A")
        assert letters["spacings"] == [6000.0, 4500.0]  # the representative's, never an average
        assert 0 < letters["max_relative_spread"] <= 2e-4
    else:
        assert len(doc["systems"]) == 2
        assert "grid_system_conflict" in codes(doc)


def test_partial_view_joins_but_does_not_count_as_independent(tmp_path, example):
    w = Work(tmp_path, example)
    partial = view(
        "V002", "model#02", fam("F003", ["B", "C"], [6000.0], angle=0.0), fam("F004", NUMBERS, NUMBER_SP)
    )
    w.add_file("plans.dxf", [plan("V001", "model#01", 1), partial])
    doc = build_grid_systems(w.finish())
    check_invariants(doc)
    assert len(doc["systems"]) == 1
    ev = doc["systems"][0]["evidence"]
    assert (ev["views"], ev["full_views"], ev["partial_views"], ev["independent_views"]) == (2, 1, 1, 1)
    assert [c["role"] for c in ev["contributors"]] == ["full", "partial"]


def test_single_direction_view_and_subset_of_two_direction_system(tmp_path, example):
    w = Work(tmp_path, example)
    lone = view("V003", "model#03", fam("F005", LETTERS, LETTER_SP, angle=0.0))
    other = view("V004", "model#04", fam("F006", ["P", "Q", "R"], [8100.0, 8100.0], angle=0.0))
    w.add_file("plans.dxf", [plan("V001", "model#01", 1), plan("V002", "model#02", 3), lone, other])
    doc = build_grid_systems(w.finish())
    check_invariants(doc)
    assert len(doc["systems"]) == 2
    s1, s2 = doc["systems"]
    assert s1["evidence"]["partial_views"] == 1 and len(s1["directions"]) == 2
    assert len(s2["directions"]) == 1 and "single_direction" in s2["flags"]


def test_subset_of_two_conflicting_systems_stays_apart(tmp_path, example):
    def v(gid: str, sheet: str, k: int, labels: list[str], sp: list[float]) -> dict[str, Any]:
        return view(
            gid, sheet, fam(f"F{k:03d}", labels, sp, angle=0.0), fam(f"F{k + 1:03d}", NUMBERS, NUMBER_SP)
        )

    xabc = ["X", "A", "B", "C"]
    w = Work(tmp_path, example)
    w.add_file(
        "plans.dxf",
        [
            v("V001", "model#01", 1, xabc, [3000.0, 6000.0, 6000.0]),
            v("V002", "model#02", 3, xabc, [3000.0, 6000.0, 6000.0]),
            v("V003", "model#03", 5, xabc, [3900.0, 6000.0, 6000.0]),
            v("V004", "model#04", 7, xabc, [3900.0, 6000.0, 6000.0]),
            v("V005", "model#05", 9, ["A", "B", "C"], [6000.0, 6000.0]),
        ],
    )
    doc = build_grid_systems(w.finish())
    check_invariants(doc)
    assert len(doc["systems"]) == 3
    s3 = doc["systems"][2]
    assert "ambiguous_subset" in s3["flags"] and s3["confidence"] == "low"
    assert s3["relations"]["subset_of"] == ["S001", "S002"]
    assert doc["systems"][0]["relations"]["conflicts_with"] == ["S002"]


def test_zero_spacing_family_is_unassigned(tmp_path, example):
    bad = fam("F003", ["A", "X", "B"], [], angle=0.0, offsets=[0.0, 0.0, 6000.0])
    w = Work(tmp_path, example)
    w.add_file("plans.dxf", [plan("V001", "model#01", 1), view("V002", "model#02", bad)])
    doc = build_grid_systems(w.finish())
    check_invariants(doc)
    assert len(doc["systems"]) == 1
    un = doc["unassigned_families"]
    assert [u["family_id"] for u in un] == ["F003"] and "one offset" in un[0]["reason"]


def test_cross_file_system_counts_files_independently(tmp_path, example):
    w = Work(tmp_path, example)
    w.add_file("a/plans.dxf", [plan("V001", "model#01", 1)])
    w.add_file("b/plans.dxf", [plan("V001", "model#01", 1)])
    doc = build_grid_systems(w.finish())
    check_invariants(doc)
    s = doc["systems"][0]
    assert (s["evidence"]["files"], s["evidence"]["independent_views"]) == (2, 2)
    assert "single_source" not in s["flags"]


def test_identical_file_content_is_not_independent(tmp_path, example):
    w = Work(tmp_path, example)
    w.add_file("a/plans.dxf", [plan("V001", "model#01", 1)], content="same")
    w.add_file("b/plans.dxf", [plan("V001", "model#01", 1)], content="same")
    s = build_grid_systems(w.finish())["systems"][0]
    assert s["evidence"]["independent_views"] == 1 and "single_source" in s["flags"]


# --- units and axis answers ------------------------------------------------------------------------


def _cm_work(tmp_path, example, files=("plans.dxf",)) -> Path:
    w = Work(tmp_path, example)
    for f in files:
        w.add_file(
            f,
            [
                view(
                    "V001",
                    "model#01",
                    fam("F001", LETTERS, [600.0, 600.0, 450.0], angle=0.0),
                    fam("F002", NUMBERS, [720.0, 720.0]),
                ),
                view(
                    "V002",
                    "model#02",
                    fam("F003", LETTERS, [600.0, 600.0, 450.0], angle=0.0),
                    fam("F004", NUMBERS, [720.0, 720.0]),
                ),
            ],
            unit="mm",
        )
    return w.finish()


def test_units_not_answered_gives_no_mm_and_a_blocking_question(tmp_path, example):
    doc = build_grid_systems(_cm_work(tmp_path, example))
    check_invariants(doc)
    s = doc["systems"][0]
    assert all(d["mm"] is None for d in s["directions"])
    assert s["units"]["status"] == "not_confirmed" and s["units"]["reason"] == "units not confirmed"
    assert "units_not_confirmed" in s["flags"]
    q = [q for q in doc["questions"] if q["code"] == "grid_system_units_unconfirmed"]
    # evidence only: the file's units_confirm_all (intake) is the one blocking units question
    assert len(q) == 1 and not q[0]["blocking"] and "S001" in q[0]["where"]
    assert "units_confirm_all" in q[0]["message"]
    assert s["tekla_grid"] is None


def test_units_answer_converts_to_mm(tmp_path, example):
    work = _cm_work(tmp_path, example)
    answers = [
        ans("units_suspect", "plans.dxf", {"unit": "cm"}),
        ans("units_suspect", "plans.dxf", {"unit": "m"}, status="superseded"),
    ]
    doc = build_grid_systems(work, answers=answers)
    check_invariants(doc)
    s = doc["systems"][0]
    assert s["units"] == {"declared": "mm", "answered": "cm", "status": "confirmed", "reason": None}
    mm = {d["labels"][0]: d["mm"] for d in s["directions"]}
    assert mm["A"] == {"spacings": [6000.0, 6000.0, 4500.0], "coordinates": "0 2*6000 4500"}
    assert mm["1"] == {"spacings": [7200.0, 7200.0], "coordinates": "0 2*7200"}
    assert "grid_system_units_unconfirmed" not in codes(doc)
    # drawing-unit values are kept as drawn
    assert next(d for d in s["directions"] if d["labels"][0] == "A")["coordinates"] == "0 2*600 450"


def test_project_wide_units_answer_applies_and_conflicting_answers_do_not(tmp_path, example):
    work = _cm_work(tmp_path, example)
    doc = build_grid_systems(work, answers=[ans("units_confirm_all", None, {"unit": "cm"})])
    assert doc["systems"][0]["units"]["status"] == "confirmed"
    doc = build_grid_systems(
        work,
        answers=[
            ans("units_confirm_all", None, {"unit": "cm"}),
            ans("grid_units_doubt", "plans.dxf", {"unit": "m"}),
        ],
    )
    s = doc["systems"][0]
    assert s["units"]["status"] == "not_confirmed" and all(d["mm"] is None for d in s["directions"])
    assert "disagree" in s["units"]["reason"]


def test_a_file_without_a_units_answer_keeps_the_system_unconfirmed(tmp_path, example):
    work = _cm_work(tmp_path, example, files=("a.dxf", "b.dxf"))
    one = build_grid_systems(work, answers=[ans("units_suspect", "a.dxf", {"unit": "cm"})])
    s = one["systems"][0]
    assert s["units"]["reason"] == "units not confirmed" and all(d["mm"] is None for d in s["directions"])
    assert s["evidence"]["files"] == 2  # b.dxf is compared in drawing units and still merges


def _two_unit_work(tmp_path, example, *, mm_scale: float = 1000.0) -> Path:
    """One building: a_m.dxf draws it in metres (header m), b_mm.dxf in millimetres (header mm)."""
    w = Work(tmp_path, example)
    for path, unit, k in (("a_m.dxf", "m", 1.0), ("b_mm.dxf", "mm", mm_scale)):
        letters = [round(x * k, 6) for x in (6.0, 6.0, 4.5)]
        numbers = [round(x * k, 6) for x in (7.2, 7.2)]
        w.add_file(
            path,
            [
                view(
                    "V001",
                    "model#01",
                    fam("F001", LETTERS, letters, angle=0.0),
                    fam("F002", NUMBERS, numbers),
                )
            ],
            unit=unit,
        )
    return w.finish()


M_MM = [ans("units_suspect", "a_m.dxf", {"unit": "m"}), ans("units_suspect", "b_mm.dxf", {"unit": "mm"})]


def test_one_building_in_m_and_mm_merges_when_every_file_has_an_agreeing_answer(tmp_path, example):
    doc = build_grid_systems(_two_unit_work(tmp_path, example), answers=M_MM)
    check_invariants(doc)
    assert [s["system_id"] for s in doc["systems"]] == ["S001"] and doc["summary"]["conflicts"] == 0
    s = doc["systems"][0]
    assert s["evidence"]["files"] == 2 and s["evidence"]["independent_views"] == 2
    assert s["units"] == {"declared": "mixed", "answered": "m", "status": "confirmed", "reason": None}
    assert {"declared_units_differ", "answered_units_differ"} <= set(s["flags"])
    mm = {d["labels"][0]: d["mm"] for d in s["directions"]}
    assert mm["A"] == {"spacings": [6000.0, 6000.0, 4500.0], "coordinates": "0 2*6000 4500"}
    assert mm["1"] == {"spacings": [7200.0, 7200.0], "coordinates": "0 2*7200"}
    # drawing-unit values stay the representative's (a_m.dxf sorts first), as drawn
    assert next(d for d in s["directions"] if d["labels"][0] == "A")["coordinates"] == "0 2*6 4.5"
    assert all(d["max_relative_spread"] == 0 for d in s["directions"])
    assert "grid_system_conflict" not in codes(doc)


@pytest.mark.parametrize(
    "answers",
    [
        [],  # drawing units: 6 vs 6000
        [ans("units_suspect", "a_m.dxf", {"unit": "m"})],  # b_mm.dxf has no answer
        [ans("units_suspect", "b_mm.dxf", {"unit": "mm"})],  # a_m.dxf has no answer
        [ans("units_suspect", "a_m.dxf", {"unit": "m"}), ans("units_suspect", "b_mm.dxf", {"unit": "m"})],
    ],
    ids=["none", "only-m", "only-mm", "wrong-pair"],
)
def test_without_two_agreeing_answers_the_same_building_stays_two_systems(tmp_path, example, answers):
    doc = build_grid_systems(_two_unit_work(tmp_path, example), answers=answers)
    check_invariants(doc)
    assert [s["system_id"] for s in doc["systems"]] == ["S001", "S002"] and doc["summary"]["conflicts"] == 1
    (conflict,) = [q for q in doc["questions"] if q["code"] == "grid_system_conflict"]
    assert conflict["blocking"]
    # no millimetre comparison: a lone answer converts nothing, and in "wrong-pair" b_mm.dxf (6000 units
    # read as metres) is contradicted by its own grid spacings
    assert "mm" not in conflict["found"]
    assert ("units_answer_contradicts_evidence" in codes(doc)) == (len(answers) == 2)
    assert all(s["evidence"]["files"] == 1 for s in doc["systems"])


def test_identical_numbers_with_different_answered_units_are_not_the_same_building(tmp_path, example):
    work = _cm_work(tmp_path, example, files=("a.dxf", "b.dxf"))  # both draw 600 / 720 ...
    answers = [ans("units_suspect", "a.dxf", {"unit": "cm"}), ans("units_suspect", "b.dxf", {"unit": "mm"})]
    doc = build_grid_systems(work, answers=answers)  # ... but one is cm (6000 mm), the other mm (600 mm)
    assert len(doc["systems"]) == 2 and doc["summary"]["conflicts"] == 1
    assert [s["units"]["status"] for s in doc["systems"]] == ["confirmed", "confirmed"]
    assert [s["units"]["answered"] for s in doc["systems"]] == ["cm", "mm"]
    same = build_grid_systems(
        work,
        answers=[
            ans("units_suspect", "a.dxf", {"unit": "mm"}),
            ans("units_suspect", "b.dxf", {"unit": "mm"}),
        ],
    )
    assert len(same["systems"]) == 1 and same["systems"][0]["units"]["answered"] == "mm"


def test_answers_digest_covers_only_the_active_answers_grid_system_reads():
    base = [ans("units_suspect", "a.dxf", {"unit": "cm"})]
    digest = consumed_answers_digest(base)
    assert consumed_answers_digest([*base, ans("grid_label_missing", "a.dxf", {})]) == digest
    for code, values in (
        ("grid_system_select", {"systems": ["S001"]}),
        ("grid_system_axis_unassigned", {"dir1": "X"}),
        ("units_answer_contradicts_evidence", {"unit": "cm"}),
    ):
        assert consumed_answers_digest([*base, ans(code, None, values)]) != digest, code
    assert (
        consumed_answers_digest([*base, ans("units_suspect", "a.dxf", {"unit": "m"}, "superseded")]) == digest
    )
    assert consumed_answers_digest([ans("units_suspect", "a.dxf", {"unit": "m"})]) != digest
    assert (
        consumed_answers_digest([*base, ans("grid_family_axis_assignment", "a.dxf", {"F001": "X"})]) != digest
    )
    assert consumed_answers_digest(None) == consumed_answers_digest([])


def test_axis_assignment_answer(tmp_path, example):
    work = _cm_work(tmp_path, example)
    answers = [
        ans("units_suspect", "plans.dxf", {"unit": "cm"}),
        ans("grid_family_axis_assignment", "plans.dxf", {"F001": "Y", "F002": "X"}),
    ]
    doc = build_grid_systems(work, answers=answers)
    check_invariants(doc)
    s = doc["systems"][0]
    axes = {d["labels"][0]: d["tekla_axis"] for d in s["directions"]}
    assert axes == {"A": "Y", "1": "X"}
    assert s["axis_assignment"]["status"] == "answered"
    assert s["tekla_grid"] == {
        "unit": "mm",
        "coordinate_x": "0 2*7200",
        "label_x": "1 2 3",
        "coordinate_y": "0 2*6000 4500",
        "label_y": "A B C D",
    }
    (axis,) = [q for q in doc["questions"] if q["code"] == "grid_system_axis_unassigned"]
    assert not axis["blocking"]  # still raised (its answer keeps its key), no longer blocking


def test_axis_assignment_missing_or_contradictory(tmp_path, example):
    work = _cm_work(tmp_path, example)
    doc = build_grid_systems(work)
    s = doc["systems"][0]
    assert all(d["tekla_axis"] is None for d in s["directions"])
    assert s["axis_assignment"]["status"] == "not_answered" and "axis_unassigned" in s["flags"]
    assert any(q["code"] == "grid_system_axis_unassigned" and q["blocking"] for q in doc["questions"])
    # only one direction answered: still unassigned
    half = build_grid_systems(work, answers=[ans("grid_family_axis_assignment", "plans.dxf", {"F001": "Y"})])
    assert half["systems"][0]["axis_assignment"]["status"] == "not_answered"
    # V001 says F001 is Y, V002 says its letter family F003 is X
    bad = build_grid_systems(
        work,
        answers=[ans("grid_family_axis_assignment", "plans.dxf", {"F001": "Y", "F002": "X", "F003": "X"})],
    )
    s = bad["systems"][0]
    assert s["axis_assignment"]["status"] == "contradictory"
    assert all(d["tekla_axis"] is None for d in s["directions"])
    # an axis answer without a file cannot be bound to a family (ids restart per file)
    nofile = build_grid_systems(work, answers=[ans("grid_family_axis_assignment", None, {"F001": "Y"})])
    assert nofile["systems"][0]["axis_assignment"]["status"] == "not_answered"
    assert any("no file" in x for x in nofile["warnings"])


# --- gate-1 questions: one X/Y question per system, rejected systems, conflicts, contradicted units -----


def keyed(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """The raw questions of a document with the registry key Ledger.sync gives them."""
    sha = {f["path"]: f["sha256"] for f in doc["files"]}
    return [
        {**q, "key": question_key(q["code"], q["file"], sha.get(q["file"]) if q["file"] else None, q["refs"])}
        for q in grid_system_questions(doc)
    ]


def answer_to(
    doc: dict[str, Any], code: str, values: dict[str, Any], where: str | None = None
) -> dict[str, Any]:
    """An active answer bound (by key) to this run's question of `code` (whose first ref is at `where`)."""
    (q,) = [q for q in keyed(doc) if q["code"] == code and where in (None, subject(q))]
    return {**ans(code, q["file"], values), "key": q["key"]}


def subject(q: dict[str, Any]) -> str:
    """What a question is about: an axis question's system id (in its message; its `where` names the
    representative families, so its key survives renumbering), else its (first) `where`."""
    if q["code"] == "grid_system_axis_unassigned":
        m = re.search(r"Grid system (S\d+):", q["message"])
        assert m, q["message"]
        return m.group(1)
    return q["refs"][0]["where"] if "refs" in q else q["where"]


def blocking_of(doc: dict[str, Any]) -> list[tuple[str, str]]:
    return sorted((q["code"], subject(q)[:4]) for q in doc["questions"] if q["blocking"])


def _two_buildings(tmp_path: Path, example: Any) -> Path:
    """S001 (A-D x 1-3) and S002 (A-C x 1-3, other spacings): the same labels, a conflict."""
    other = [
        view(
            gid,
            sheet,
            fam(f"F{k:03d}", ["A", "B", "C"], [3600.0, 4800.0], angle=0.0),
            fam(f"F{k + 1:03d}", NUMBERS, [5400.0, 5400.0], angle=90.0),
        )
        for gid, sheet, k in (("V003", "model#03", 5), ("V004", "model#04", 7))
    ]
    w = Work(tmp_path, example)
    w.add_file("plans.dxf", [plan("V001", "model#01", 1), plan("V002", "model#02", 3), *other])
    return w.finish()


def test_one_axis_question_per_system_answered_by_direction_and_kept_once_answered(tmp_path, example):
    work = _two_buildings(tmp_path, example)
    doc = build_grid_systems(work)
    axis = [q for q in keyed(doc) if q["code"] == "grid_system_axis_unassigned"]
    assert [(subject(q), q["count"], q["blocking"]) for q in axis] == [
        ("S001", 1, True),
        ("S002", 1, True),
    ]
    assert axis[0]["refs"][0]["where"] == "plans.dxf V001/F001 x V001/F002"  # families, not the system id
    assert axis[0]["subjects"] == [{"name": "dir1", "count": 2}, {"name": "dir2", "count": 2}]
    assert (
        axis[0]["refs"][0]["found"]
        == "dir1: V001/F001 labels A B C D, angle 0 deg; dir2: V001/F002 labels 1 2 3, angle 90 deg"
    )
    assert [s["axis_question_key"] for s in doc["systems"]] == [q["key"] for q in axis]
    answer = answer_to(doc, "grid_system_axis_unassigned", {"dir1": "Y", "dir2": "X"}, "S001")
    after = build_grid_systems(work, answers=[answer])
    s1 = after["systems"][0]
    assert s1["axis_assignment"]["status"] == "answered"
    assert [d["tekla_axis"] for d in s1["directions"]] == ["Y", "X"]
    again = {subject(q): q for q in keyed(after) if q["code"] == "grid_system_axis_unassigned"}
    assert [again[subject(q)]["key"] for q in axis] == [q["key"] for q in axis]  # same keys
    assert (again["S001"]["blocking"], again["S002"]["blocking"]) == (False, True)
    # an answer bound to another key, or that does not assign every direction, assigns nothing
    for wrong in (
        {**answer, "key": "0" * 16},
        {**answer, "values": {"dir1": "Y"}},
        {**answer, "values": {"dir1": "X", "dir2": "X"}},
        {**answer, "values": {}},
    ):
        out = build_grid_systems(work, answers=[wrong])
        assert out["systems"][0]["axis_assignment"]["status"] == "not_answered", wrong["values"]
    assert any(
        "not used" in w for w in build_grid_systems(work, answers=[{**answer, "values": {}}])["warnings"]
    )


def test_systems_outside_the_selection_raise_no_blocking_question(tmp_path, example):
    work = _two_buildings(tmp_path, example)
    doc = build_grid_systems(work)
    assert blocking_of(doc) == [
        ("grid_system_axis_unassigned", "S001"),
        ("grid_system_axis_unassigned", "S002"),
        ("grid_system_conflict", "plan"),
        ("grid_system_select", "S001"),
    ]
    select = answer_to(doc, "grid_system_select", {"systems": ["S001"]})
    after = build_grid_systems(work, answers=[select])
    assert blocking_of(after) == [("grid_system_axis_unassigned", "S001"), ("grid_system_select", "S001")]
    assert after["conflicts"] == [
        {
            "systems": ["S001", "S002"],
            "blocking": False,
            "closed_by": "not_selected",
            "question_key": next(q["key"] for q in keyed(after) if q["code"] == "grid_system_conflict"),
        }
    ]
    # a select answer to an older question (another key: the system ids may mean other systems) is not used
    stale = build_grid_systems(work, answers=[{**select, "key": "f" * 16}])
    assert blocking_of(stale) == blocking_of(doc)


def test_a_conflict_closes_only_on_structured_values(tmp_path, example):
    """EVAL-1 F-26: words in the select answer ("S004/S005 are variant views of 267, not used") or an answer
    to the conflict question itself never close the conflict or the axis questions."""
    work = _two_buildings(tmp_path, example)
    doc = build_grid_systems(work)
    words = {**answer_to(doc, "grid_system_select", {}), "answer_text": "S002 is a variant view, not used"}
    conflict = answer_to(doc, "grid_system_conflict", {})
    after = build_grid_systems(work, answers=[words, conflict])
    assert blocking_of(after) == blocking_of(doc)
    assert after["conflicts"][0]["blocking"] and after["conflicts"][0]["closed_by"] is None
    separate = answer_to(
        doc, "grid_system_select", {"systems": ["S001", "S002"], "separate": ["S001", "S002"]}
    )
    apart = build_grid_systems(work, answers=[separate])
    assert apart["conflicts"][0]["closed_by"] == "separate" and not apart["conflicts"][0]["blocking"]
    assert ("grid_system_conflict", "plan") not in blocking_of(apart)
    assert ("grid_system_axis_unassigned", "S002") in blocking_of(
        apart
    )  # a selected building still needs X/Y


# --- question lifecycle: stable conflict ids, closures (tool wave 2, fix 5a) ---------------------------


def _ledger_work(work: Path) -> Path:
    """Give a Work folder an empty question registry, as `harness intake` would have left it."""
    registry = empty_registry("demo-project")
    (work / "question-registry.json").write_text(json.dumps(registry), encoding="utf-8")
    return work


def _set_answers(work: Path, answers: list[dict[str, Any]]) -> None:
    doc = {"schema_version": "0.1", "project_id": "demo-project", "answers": answers}
    assert validate("answers", doc) == []
    (work / "answers.json").write_text(json.dumps(doc), encoding="utf-8")


def _gs_questions(work: Path) -> list[dict[str, Any]]:
    return json.loads((work / "grid-system-questions.json").read_text(encoding="utf-8"))["questions"]


def _one(questions: list[dict[str, Any]], code: str) -> dict[str, Any]:
    (q,) = [q for q in questions if q["code"] == code]
    return q


def test_a_conflict_keeps_its_id_across_a_units_answer_and_a_separate_rerun(tmp_path, example):
    """EVAL-2 fix 5: the conflict key hashed the difference text, which switches to millimetres once the
    units are answered, so the same conflict came back under a new Q-id."""
    work = _ledger_work(_two_buildings(tmp_path, example))
    run_grid_systems(work, svg=False)
    first = _one(_gs_questions(work), "grid_system_conflict")
    assert first["blocking"] and "closed_by" not in first
    # identity: both sides' file and family ids and the shared labels; no system id, no difference text
    ref = first["refs"][0]
    assert ref["where"] == "plans.dxf V001/F001 vs plans.dxf V003/F005"
    assert (
        ref["found"]
        == "V001/F001 x V003/F005: shared labels A B C; V001/F002 x V003/F006: shared labels 1 2 3"
    )
    assert "S001" in first["message"] and "A-B: 6000 vs 3600" in first["message"]

    units = {
        **ans("units_confirm_all", "plans.dxf", {"unit": "mm"}),
        "key": "1" * 16,
        "question_id": "Q-900",
    }
    _set_answers(work, [units])
    run_grid_systems(work, svg=False)
    in_mm = _one(_gs_questions(work), "grid_system_conflict")
    assert (in_mm["id"], in_mm["key"]) == (first["id"], first["key"])
    assert "A-B: 6000 vs 3600 mm" in in_mm["message"]

    select = _one(_gs_questions(work), "grid_system_select")
    separate = {
        **ans("grid_system_select", None, {"systems": ["S001", "S002"], "separate": ["S001", "S002"]}),
        "key": select["key"],
        "question_id": select["id"],
    }
    _set_answers(work, [units, separate])
    run_grid_systems(work, svg=False)
    closed = _one(_gs_questions(work), "grid_system_conflict")
    assert (closed["id"], closed["key"]) == (first["id"], first["key"])
    assert not closed["blocking"]
    assert closed["closed_by"] == {"question_id": select["id"], "reason": "separate"}
    doc = json.loads((work / "grid-systems.json").read_text(encoding="utf-8"))
    (conflict,) = doc["conflicts"]
    assert conflict["question_id"] == first["id"] and conflict["closed_by"] == "separate"
    # the relation stays a fact; the flag that asks for action clears
    assert all("conflict" not in s["flags"] for s in doc["systems"])
    assert doc["systems"][0]["relations"]["conflicts_with"] == ["S002"]


def test_a_conflict_left_out_of_the_selection_keeps_its_id_and_is_closed(tmp_path, example):
    work = _ledger_work(_two_buildings(tmp_path, example))
    run_grid_systems(work, svg=False)
    first = _one(_gs_questions(work), "grid_system_conflict")
    select = _one(_gs_questions(work), "grid_system_select")
    chosen = {
        **ans("grid_system_select", None, {"systems": ["S001"]}),
        "key": select["key"],
        "question_id": select["id"],
    }
    _set_answers(work, [chosen])
    run_grid_systems(work, svg=False)
    closed = _one(_gs_questions(work), "grid_system_conflict")
    assert closed["id"] == first["id"] and not closed["blocking"]
    assert closed["closed_by"] == {"question_id": select["id"], "reason": "not_selected"}
    doc = json.loads((work / "grid-systems.json").read_text(encoding="utf-8"))
    assert "conflict" not in doc["systems"][0]["flags"]


def test_an_open_conflict_keeps_the_conflict_flag(tmp_path, example):
    work = _ledger_work(_two_buildings(tmp_path, example))
    run_grid_systems(work, svg=False)
    doc = json.loads((work / "grid-systems.json").read_text(encoding="utf-8"))
    assert all("conflict" in s["flags"] for s in doc["systems"])
    (conflict,) = doc["conflicts"]
    assert conflict["question_id"] == _one(_gs_questions(work), "grid_system_conflict")["id"]


def test_the_conflict_identity_lists_its_sides_in_file_order_not_system_order(tmp_path, example):
    """S001 (two views) is in b.dxf, S002 (one view) in a.dxf: the key must not depend on which system
    ranks first, so the sides are sorted by file, view and family."""
    w = Work(tmp_path, example)
    w.add_file("b.dxf", [plan("V001", "model#01", 1), plan("V002", "model#02", 3)])
    other = view(
        "V001",
        "model#01",
        fam("F001", ["A", "B", "C"], [3600.0, 4800.0], angle=0.0),
        fam("F002", NUMBERS, [5400.0, 5400.0], angle=90.0),
    )
    w.add_file("a.dxf", [other])
    doc = build_grid_systems(w.finish())
    assert doc["systems"][0]["directions"][0]["representative"]["file"] == "b.dxf"
    (q,) = [q for q in doc["questions"] if q["code"] == "grid_system_conflict"]
    assert q["where"] == "a.dxf V001/F001 vs b.dxf V001/F001" and q["file"] == "a.dxf"
    assert q["found"].startswith("V001/F001 x V001/F001: shared labels A B C")


def test_an_answer_to_an_old_style_conflict_key_goes_stale_once(tmp_path, example):
    """Conflict keys changed with fix 5a: an existing answer to the old key goes stale on the first run and
    the conflict is asked under a new id; the next run changes nothing."""
    work = _ledger_work(_two_buildings(tmp_path, example))
    files = json.loads((work / "inventory.json").read_text(encoding="utf-8"))["files"]
    digest = files[0]["sha256"]
    old_ref = {
        "file": "plans.dxf",
        "where": "S001 (plans.dxf, sheet model#01, V001/F001) vs S002 (plans.dxf, sheet model#03, V003/F005)",
        "found": "A-B: 6000 vs 3600; B-C: 6000 vs 4800; 1-2: 7200 vs 5400; 2-3: 7200 vs 5400",
        "sheet": "model#01",
    }
    old_key = question_key("grid_system_conflict", "plans.dxf", digest, [old_ref])
    registry = empty_registry("demo-project")
    registry["questions"][old_key] = {
        "id": "Q-001",
        "code": "grid_system_conflict",
        "file": "plans.dxf",
        "producer": "grid-system",
        "status": "answered",
        "first_seen_run": 1,
        "last_seen_run": 1,
        "blocking": True,
        "file_sha256": digest,
    }
    registry["next_id"], registry["runs"] = 2, 1
    (work / "question-registry.json").write_text(json.dumps(registry), encoding="utf-8")
    old = {**ans("grid_system_conflict", "plans.dxf", {}), "key": old_key, "question_id": "Q-001"}
    _set_answers(work, [old])
    result = run_grid_systems(work, svg=False)
    assert [a["question_id"] for a in result.summary["stale_answers"]] == ["Q-001"]
    new = _one(_gs_questions(work), "grid_system_conflict")
    assert new["id"] != "Q-001" and new["answer"] is None
    answers_after = (work / "answers.json").read_bytes()
    run_grid_systems(work, svg=False)
    assert (work / "answers.json").read_bytes() == answers_after
    assert _one(_gs_questions(work), "grid_system_conflict")["id"] == new["id"]


# --- file sets: systems are compared only within one set (fix 5d) --------------------------------------

FILE_SET_KEY, FILE_SET_ID = "e" * 16, "Q-950"


def _other_building(gid: str, sheet: str, k: int) -> dict[str, Any]:
    """A-C x 1-3 with other spacings than plan(): a conflict with it on the shared labels."""
    return view(
        gid,
        sheet,
        fam(f"F{k:03d}", ["A", "B", "C"], [3600.0, 4800.0], angle=0.0),
        fam(f"F{k + 1:03d}", NUMBERS, [5400.0, 5400.0], angle=90.0),
    )


def _with_file_set(work: Path) -> Path:
    """A registry holding the live intake file_set_relation question (as harness intake raises it)."""
    registry = empty_registry("demo-project")
    registry["questions"][FILE_SET_KEY] = {
        "id": FILE_SET_ID,
        "code": "file_set_relation",
        "file": None,
        "producer": "intake",
        "status": "open",
        "first_seen_run": 1,
        "last_seen_run": 1,
        "blocking": True,
        "file_sha256": None,
    }
    registry["next_id"], registry["runs"] = 951, 1
    (work / "question-registry.json").write_text(json.dumps(registry), encoding="utf-8")
    return work


def _file_set_answer(**sets: list[str]) -> dict[str, Any]:
    return {**ans("file_set_relation", None, sets), "key": FILE_SET_KEY, "question_id": FILE_SET_ID}


def _two_files(tmp_path: Path, example: Any, second: dict[str, Any] | None = None) -> Path:
    """a.dxf: plan() twice (A-D x 1-3); b.dxf: `second` twice (default: the conflicting A-C x 1-3)."""
    w = Work(tmp_path, example)
    w.add_file("a.dxf", [plan("V001", "model#01", 1), plan("V002", "model#02", 3)])
    make = (lambda g, s, k: second) if second is not None else _other_building
    w.add_file("b.dxf", [make("V001", "model#01", 1), make("V002", "model#02", 3)])
    return w.finish()


def _gs_doc(work: Path) -> dict[str, Any]:
    return json.loads((work / "grid-systems.json").read_text(encoding="utf-8"))


def test_a_cross_file_conflict_waits_for_the_file_set_answer_and_keeps_its_id(tmp_path, example):
    work = _with_file_set(_two_files(tmp_path, example))
    run_grid_systems(work, svg=False)
    pending = _one(_gs_questions(work), "grid_system_conflict")
    assert not pending["blocking"] and "closed_by" not in pending
    assert pending["message"].startswith(f"Not blocking yet: pending {FILE_SET_ID} (file_set_relation)")
    doc = _gs_doc(work)
    assert doc["file_sets"] == {"status": "pending", "sets": None, "question_id": FILE_SET_ID}
    assert doc["conflicts"][0]["blocking"] is False and doc["conflicts"][0]["closed_by"] is None
    # one set: the files are one project, the conflict blocks under the same id
    _set_answers(work, [_file_set_answer(set1=["a.dxf", "b.dxf"])])
    run_grid_systems(work, svg=False)
    one = _one(_gs_questions(work), "grid_system_conflict")
    assert (one["id"], one["key"], one["blocking"]) == (pending["id"], pending["key"], True)
    assert _gs_doc(work)["file_sets"] == {
        "status": "answered",
        "sets": [["a.dxf", "b.dxf"]],
        "question_id": FILE_SET_ID,
    }


def test_files_of_two_sets_are_never_compared(tmp_path, example):
    work = _with_file_set(_two_files(tmp_path, example))
    _set_answers(work, [_file_set_answer(set1=["a.dxf"], set2=["b.dxf"])])
    run_grid_systems(work, svg=False)
    doc = _gs_doc(work)
    assert doc["file_sets"] == {
        "status": "answered",
        "sets": [["a.dxf"], ["b.dxf"]],
        "question_id": FILE_SET_ID,
    }
    assert doc["conflicts"] == [] and "grid_system_conflict" not in [q["code"] for q in _gs_questions(work)]
    assert [s["relations"] for s in doc["systems"]] == [
        {"compatible_with": [], "conflicts_with": [], "subset_of": []}
    ] * 2


def test_the_same_grid_in_two_sets_stays_two_systems(tmp_path, example):
    """Two projects drawn on one grid module must not merge into one system (nor confirm each other)."""
    work = _with_file_set(_two_files(tmp_path, example, second=plan("V001", "model#01", 1)))
    _set_answers(work, [_file_set_answer(set1=["a.dxf", "b.dxf"])])
    run_grid_systems(work, svg=False)
    assert [s["evidence"]["files"] for s in _gs_doc(work)["systems"]] == [2]
    _set_answers(work, [_file_set_answer(set1=["b.dxf"], set2=["a.dxf"])])
    run_grid_systems(work, svg=False)
    doc = _gs_doc(work)
    assert [s["evidence"]["files"] for s in doc["systems"]] == [1, 1]
    assert {s["directions"][0]["representative"]["file"] for s in doc["systems"]} == {"a.dxf", "b.dxf"}
    assert doc["file_sets"]["sets"] == [["b.dxf"], ["a.dxf"]]


def test_a_conflict_inside_one_file_blocks_while_the_file_set_answer_is_pending(tmp_path, example):
    w = Work(tmp_path, example)
    w.add_file("a.dxf", [plan("V001", "model#01", 1), _other_building("V002", "model#02", 3)])
    w.add_file("b.dxf", [view("V001", "model#01", fam("F001", ["X", "Y"], [5000.0]))])
    work = _with_file_set(w.finish())
    run_grid_systems(work, svg=False)
    conflict = _one(_gs_questions(work), "grid_system_conflict")
    assert conflict["blocking"] and "pending" not in conflict["message"]


def test_without_a_live_file_set_question_cross_file_conflicts_block(tmp_path, example):
    """An intake run before fix 5d raised no file_set_relation: nothing would ever release a pending
    conflict, so it blocks as before."""
    work = _ledger_work(_two_files(tmp_path, example))
    run_grid_systems(work, svg=False)
    assert _one(_gs_questions(work), "grid_system_conflict")["blocking"]
    assert "file_sets" not in _gs_doc(work)


def test_one_readable_drawing_file_is_a_single_file_set(tmp_path, example):
    work = _ledger_work(_two_buildings(tmp_path, example))
    run_grid_systems(work, svg=False)
    assert _gs_doc(work)["file_sets"] == {"status": "single", "sets": None, "question_id": None}


def test_the_answers_digest_covers_the_file_set_answer():
    base = [ans("units_suspect", "a.dxf", {"unit": "cm"})]
    with_sets = [*base, _file_set_answer(set1=["a.dxf"])]
    assert consumed_answers_digest(with_sets) != consumed_answers_digest(base)


def test_a_units_answer_the_drawing_contradicts_blocks_until_confirmed(tmp_path, example):
    w = Work(tmp_path, example)
    w.add_file("plans.dxf", [plan("V001", "model#01", 1)], median={"value": 6000.0, "count": 5})
    work = w.finish()
    metres = {**ans("units_confirm_all", "plans.dxf", {"unit": "m"}), "answer_text": "it is metres"}
    doc = build_grid_systems(work, answers=[metres])
    assert doc["files"][0]["units_answer"] == {"status": "contradicted", "unit": None}
    s = doc["systems"][0]
    assert s["units"]["reason"] == "units answer contradicted by the drawing" and s["tekla_grid"] is None
    assert all(d["mm"] is None for d in s["directions"])
    (q,) = [q for q in doc["questions"] if q["code"] == "units_answer_contradicts_evidence"]
    assert q["blocking"] and q["file"] == "plans.dxf"
    assert 'Q-001 units_confirm_all unit=m: "it is metres"' in q["found"]  # the answer, quoted
    assert "6000 drawing units = 6000 m in m" in q["found"]  # and the evidence
    confirm = answer_to(doc, "units_answer_contradicts_evidence", {"unit": "m"})
    ok = build_grid_systems(work, answers=[metres, confirm])
    assert ok["systems"][0]["units"]["status"] == "confirmed"
    wrong = build_grid_systems(work, answers=[metres, {**confirm, "values": {"unit": "mm"}}])
    assert wrong["systems"][0]["units"]["status"] == "not_confirmed"
    mm = build_grid_systems(work, answers=[ans("units_confirm_all", "plans.dxf", {"unit": "mm"})])
    assert "units_answer_contradicts_evidence" not in codes(mm)  # 6 m: plausible
    assert mm["systems"][0]["units"]["status"] == "confirmed"


def test_a_units_answer_the_grid_spacings_contradict_blocks_without_dimension_evidence(tmp_path, example):
    """Header mm, drawing really in metres, fewer than 3 linear dimensions (median null): the spacing test
    under the ANSWERED unit still blocks (6 units = 0.006 m)."""
    w = Work(tmp_path, example)
    w.add_file(
        "plans.dxf",
        [
            view(
                "V001",
                "model#01",
                fam("F001", ["A", "B", "C"], [6.0, 6.0]),
                fam("F002", ["1", "2"], [7.0], angle=0.0),
            )
        ],
        median=None,
    )
    work = w.finish()
    mm = {**ans("units_confirm_all", "plans.dxf", {"unit": "mm"}), "answer_text": "it is mm"}
    doc = build_grid_systems(work, answers=[mm])
    assert doc["files"][0]["grid_spacing_median"] == {"value": 6.0, "count": 3}
    assert doc["files"][0]["units_answer"] == {"status": "contradicted", "unit": None}
    assert validate("grid-system", doc) == []
    (q,) = [q for q in doc["questions"] if q["code"] == "units_answer_contradicts_evidence"]
    assert q["blocking"] and q["file"] == "plans.dxf"
    assert 'Q-001 units_confirm_all unit=mm: "it is mm"' in q["found"]
    assert "median grid spacing 6 drawing units = 0.006 m in mm over 3 spacing(s)" in q["found"]
    assert doc["systems"][0]["tekla_grid"] is None
    # the same unit confirmed on the contradiction question closes it; a plausible unit never raises it
    confirm = answer_to(doc, "units_answer_contradicts_evidence", {"unit": "mm"})
    ok = build_grid_systems(work, answers=[mm, confirm])
    assert ok["systems"][0]["units"]["status"] == "confirmed"
    metres = build_grid_systems(work, answers=[ans("units_confirm_all", "plans.dxf", {"unit": "m"})])
    assert "units_answer_contradicts_evidence" not in codes(metres)  # 6 m: plausible
    assert metres["systems"][0]["units"]["status"] == "confirmed"


def test_select_key_changes_when_two_systems_swap_files(tmp_path, example):
    """Sheet ids (model#01) repeat across files: the select key must name the representative's file, or an
    old systems=S001 answer would select the other building after the S-ids swap."""
    doc = build_grid_systems(_two_unit_work(tmp_path, example))
    assert [s["system_id"] for s in doc["systems"]] == ["S001", "S002"]
    assert len({s["directions"][0]["representative"]["sheet"] for s in doc["systems"]}) == 1

    def select_key(d: dict[str, Any]) -> str:
        (q,) = [q for q in grid_system_questions(d) if q["code"] == "grid_system_select"]
        return question_key("grid_system_select", None, None, q["refs"])

    swapped = copy.deepcopy(doc)
    a, b = swapped["systems"]
    for da, db in zip(a["directions"], b["directions"], strict=True):
        da["representative"]["file"], db["representative"]["file"] = (
            db["representative"]["file"],
            da["representative"]["file"],
        )
    assert select_key(swapped) != select_key(doc)
    (q,) = [q for q in grid_system_questions(doc) if q["code"] == "grid_system_select"]
    assert all(f"[file {r['file']}, sha256 " in r["found"] for r in q["refs"])


# --- provenance: an answer the engineer did not give proposes, never confirms (tool wave 3) -------------


def sim(answer: dict[str, Any], role: str | None = "simulated") -> dict[str, Any]:
    """The same answer, recorded by an agent standing in for the engineer (or, role None, before roles)."""
    out = {k: v for k, v in answer.items() if k != "answered_by_role"}
    return out if role is None else {**out, "answered_by_role": role}


@pytest.mark.parametrize("role", ["simulated", None])
def test_a_non_engineer_units_answer_converts_nothing(tmp_path, example, role):
    work = _cm_work(tmp_path, example)
    doc = build_grid_systems(work, answers=[sim(ans("units_suspect", "plans.dxf", {"unit": "cm"}), role)])
    check_invariants(doc)
    s = doc["systems"][0]
    assert s["units"] == {
        "declared": "mm",
        "answered": "cm",
        "status": "proposed_simulated",
        "reason": "units answered by a non-engineer role",
    }
    assert all(d["mm"] is None for d in s["directions"]) and s["tekla_grid"] is None
    assert "units_not_confirmed" in s["flags"]
    assert doc["files"][0]["units_answer"] == {"status": "proposed_simulated", "unit": "cm"}
    (q,) = [q for q in doc["questions"] if q["code"] == "grid_system_units_unconfirmed"]
    assert not q["blocking"]  # still raised: the units question it points to stays open
    # the engineer's own answer confirms
    ok = build_grid_systems(work, answers=[ans("units_suspect", "plans.dxf", {"unit": "cm"})])
    assert ok["systems"][0]["units"]["status"] == "confirmed"


def test_one_non_engineer_file_keeps_the_units_proposed_and_merges_nothing(tmp_path, example):
    work = _cm_work(tmp_path, example, files=("a.dxf", "b.dxf"))
    answers = [
        ans("units_suspect", "a.dxf", {"unit": "cm"}),
        sim(ans("units_suspect", "b.dxf", {"unit": "cm"})),
    ]
    s = build_grid_systems(work, answers=answers)["systems"][0]
    assert (s["units"]["status"], s["units"]["reason"]) == (
        "proposed_simulated",
        "units answered by a non-engineer role",
    )
    assert all(d["mm"] is None for d in s["directions"])
    # an engineer answer that disagrees, or none for a file, still wins over a proposal as the reason
    none = build_grid_systems(work, answers=[sim(ans("units_suspect", "a.dxf", {"unit": "cm"}))])
    assert none["systems"][0]["units"]["reason"] == "units not confirmed"
    # one building in m and mm merges in millimetres only on the engineer's answers
    split = build_grid_systems(_two_unit_work(tmp_path / "u", example), answers=[M_MM[0], sim(M_MM[1])])
    assert [s["system_id"] for s in split["systems"]] == ["S001", "S002"]
    # a file the engineer answered is not a proposal, whatever another role says on another question
    both = [
        *answers[:1],
        sim(ans("units_confirm_all", "a.dxf", {"unit": "cm"})),
        answers[0] | {"file": "b.dxf"},
    ]
    doc = build_grid_systems(work, answers=both)
    assert [f["units_answer"] for f in doc["files"]] == [{"status": "answered", "unit": "cm"}] * 2
    assert doc["systems"][0]["units"]["status"] == "confirmed"


@pytest.mark.parametrize("role", ["simulated", None])
def test_a_non_engineer_axis_answer_assigns_nothing_and_its_question_still_blocks(tmp_path, example, role):
    work = _cm_work(tmp_path, example)
    doc = build_grid_systems(work)
    system_answer = sim(answer_to(doc, "grid_system_axis_unassigned", {"dir1": "Y", "dir2": "X"}), role)
    family_answer = sim(ans("grid_family_axis_assignment", "plans.dxf", {"F001": "Y", "F002": "X"}), role)
    for answer in (system_answer, family_answer):
        out = build_grid_systems(work, answers=[ans("units_suspect", "plans.dxf", {"unit": "cm"}), answer])
        check_invariants(out)
        s = out["systems"][0]
        assert s["axis_assignment"]["status"] == "proposed_simulated", answer["code"]
        assert "engineer" in s["axis_assignment"]["reason"]
        assert all(d["tekla_axis"] is None for d in s["directions"]) and s["tekla_grid"] is None
        assert "axis_unassigned" in s["flags"]
        (q,) = [q for q in out["questions"] if q["code"] == "grid_system_axis_unassigned"]
        assert q["blocking"]
    # an engineer answer next to a contradicting non-engineer one decides alone
    engineer = answer_to(doc, "grid_system_axis_unassigned", {"dir1": "Y", "dir2": "X"})
    both = build_grid_systems(work, answers=[engineer, sim(family_answer, role) | {"values": {"F001": "X"}}])
    assert both["systems"][0]["axis_assignment"]["status"] == "answered"


@pytest.mark.parametrize("role", ["simulated", None])
def test_a_non_engineer_select_answer_closes_no_conflict(tmp_path, example, role):
    work = _two_buildings(tmp_path, example)
    doc = build_grid_systems(work)
    for values, would in (
        ({"systems": ["S001"]}, "not_selected"),
        ({"systems": ["S001", "S002"], "separate": ["S001", "S002"]}, "separate"),
    ):
        after = build_grid_systems(work, answers=[sim(answer_to(doc, "grid_system_select", values), role)])
        check_invariants(after)
        assert blocking_of(after) == blocking_of(doc), values
        (c,) = after["conflicts"]
        assert (c["blocking"], c["closed_by"], c["proposed_closed_by"]) == (True, None, would)
        assert any("non-engineer" in w and "grid_system_select" in w for w in after["warnings"])
    engineer = build_grid_systems(work, answers=[answer_to(doc, "grid_system_select", {"systems": ["S001"]})])
    assert "proposed_closed_by" not in engineer["conflicts"][0]
    assert "proposed_closed_by" not in doc["conflicts"][0]
    # one system declared separate is not two separate buildings: nothing would close
    half = {"systems": ["S001", "S002"], "separate": ["S001"]}
    after = build_grid_systems(work, answers=[sim(answer_to(doc, "grid_system_select", half), role)])
    assert "proposed_closed_by" not in after["conflicts"][0]
    eng_half = build_grid_systems(work, answers=[answer_to(doc, "grid_system_select", half)])
    assert eng_half["conflicts"][0]["closed_by"] is None and eng_half["conflicts"][0]["blocking"]


def test_a_non_engineer_file_set_answer_keeps_the_sets_pending(tmp_path, example):
    work = _with_file_set(_two_files(tmp_path, example))
    _set_answers(work, [sim(_file_set_answer(set1=["a.dxf"], set2=["b.dxf"]))])
    run_grid_systems(work, svg=False)
    doc = _gs_doc(work)
    assert doc["file_sets"] == {"status": "pending", "sets": None, "question_id": FILE_SET_ID}
    (c,) = doc["conflicts"]  # still compared, and waiting for the engineer's answer
    assert c["blocking"] is False and c["closed_by"] is None
    assert any("non-engineer" in w and "file_set_relation" in w for w in doc["warnings"])


def test_a_conflict_retired_by_the_engineer_file_set_answer_says_so(tmp_path, example):
    work = _with_file_set(_two_files(tmp_path, example))
    run_grid_systems(work, svg=False)
    conflict = _one(_gs_questions(work), "grid_system_conflict")
    _set_answers(work, [_file_set_answer(set1=["a.dxf"], set2=["b.dxf"])])
    run_grid_systems(work, svg=False)
    registry = json.loads((work / "question-registry.json").read_text(encoding="utf-8"))
    entry = registry["questions"][conflict["key"]]
    assert entry["status"] == "obsolete"
    assert entry["obsolete_reason"] == "superseded by an answer to file_set_relation"


def test_a_conflict_gone_while_a_non_engineer_file_set_answer_is_active_was_not_superseded(tmp_path, example):
    """The sets stay pending under a non-engineer answer, so a conflict that goes away (here: b.dxf's grid
    redrawn, same file) went for another reason."""
    work = _with_file_set(_two_files(tmp_path, example))
    _set_answers(work, [sim(_file_set_answer(set1=["a.dxf"], set2=["b.dxf"]))])
    run_grid_systems(work, svg=False)
    conflict = _one(_gs_questions(work), "grid_system_conflict")
    w = Work(work, example)
    w.add_file("a.dxf", [plan("V001", "model#01", 1), plan("V002", "model#02", 3)])
    w.add_file("b.dxf", [plan("V001", "model#01", 1), plan("V002", "model#02", 3)])  # same content (sha)
    w.finish()
    run_grid_systems(work, svg=False)
    registry = json.loads((work / "question-registry.json").read_text(encoding="utf-8"))
    entry = registry["questions"][conflict["key"]]
    assert entry["obsolete_reason"] == "the latest grid-system run no longer raises it"


def test_a_non_engineer_confirmation_of_a_contradicted_unit_confirms_nothing(tmp_path, example):
    w = Work(tmp_path, example)
    w.add_file("plans.dxf", [plan("V001", "model#01", 1)], median={"value": 6000.0, "count": 5})
    work = w.finish()
    metres = ans("units_confirm_all", "plans.dxf", {"unit": "m"})
    doc = build_grid_systems(work, answers=[metres])
    confirm = answer_to(doc, "units_answer_contradicts_evidence", {"unit": "m"})
    out = build_grid_systems(work, answers=[metres, sim(confirm)])
    assert out["systems"][0]["units"]["status"] == "not_confirmed"
    assert out["files"][0]["units_answer"] == {"status": "contradicted", "unit": None}
    # a non-engineer unit the drawing contradicts is still flagged (it is what an agent would build on)
    proposed = build_grid_systems(work, answers=[sim(metres)])
    assert "units_answer_contradicts_evidence" in codes(proposed)
    assert proposed["files"][0]["units_answer"] == {"status": "proposed_simulated", "unit": "m"}
    assert proposed["systems"][0]["units"]["reason"] == "units answered by a non-engineer role"


# --- SVG -------------------------------------------------------------------------------------------


def test_svg_is_well_formed_and_written(tmp_path, example):
    w = Work(tmp_path, example)
    w.add_file("plans.dxf", [plan("V001", "model#01", 1), plan("V002", "model#02", 3)])
    work = w.finish()
    stale = work / "structure" / "grid-systems" / "S009.svg"
    stale.parent.mkdir(parents=True)
    stale.write_text("old", encoding="utf-8")
    doc = build_grid_systems(work, write=True)
    s = doc["systems"][0]
    svg = render_grid_system_svg(s)
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    text = " ".join(t.text or "" for t in root.iter() if t.tag.endswith("text"))
    for lbl in [*LETTERS, *NUMBERS]:
        assert re.search(rf"(^|\s){re.escape(lbl)}(\s|$)", text)
    assert BANNER in svg and BANNER == "PROPOSAL — not confirmed (gate 1)"
    assert "0 2*6000 4500" in svg and "0 2*7200" in svg and "mm" in svg
    assert "<script" not in svg and "@import" not in svg and "href" not in svg
    assert (work / s["svg"]).read_text(encoding="utf-8") == svg
    assert not stale.exists()


def test_svg_escapes_labels_and_handles_one_direction(tmp_path, example):
    w = Work(tmp_path, example)
    w.add_file("plans.dxf", [view("V001", "model#01", fam("F001", LETTERS, LETTER_SP, angle=0.0))])
    s = copy.deepcopy(build_grid_systems(w.finish())["systems"][0])
    s["directions"][0]["labels"][0] = 'A<&"'
    ET.fromstring(render_grid_system_svg(s))


def spacing_boxes(svg: str) -> list[tuple[str, str, tuple[float, float, float, float]]]:
    """(text, anchor, (left, top, right, bottom)) of every spacing label, from the estimated text width."""
    boxes = []
    for el in ET.fromstring(svg).iter():
        if not el.tag.endswith("text") or el.get("class") != "spacing":
            continue
        text, size, anchor = el.text or "", float(el.get("font-size", "0")), el.get("text-anchor", "start")
        x, y, w = float(el.get("x", "0")), float(el.get("y", "0")), CHAR_WIDTH * size * len(text)
        left = x - w / 2 if anchor == "middle" else x
        boxes.append((text, anchor, (left, y - size, left + w, y)))
    return boxes


def overlaps(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def narrow_system(tmp_path, example, spacings: list[float]) -> dict[str, Any]:
    labels = [chr(ord("A") + i) for i in range(len(spacings) + 1)]
    w = Work(tmp_path, example)
    w.add_file(
        "plans.dxf",
        [
            view(
                "V001",
                "model#01",
                fam("F001", labels, spacings, angle=0.0),
                fam("F002", [str(i + 1) for i in range(len(spacings) + 1)], spacings),
            )
        ],
    )
    return build_grid_systems(w.finish())["systems"][0]


@pytest.mark.parametrize(
    "spacings",
    [
        [6000.0, 360.0, 317.7, 6000.0],
        [6000.0, 360.0, 317.7, 280.0, 300.0, 6000.0],  # three narrow ones in a row need a third row
        [6000.0, 6000.0, 6000.0],
    ],
)
def test_svg_spacing_labels_never_overlap(tmp_path, example, spacings):
    svg = render_grid_system_svg(narrow_system(tmp_path, example, spacings))
    boxes = spacing_boxes(svg)
    assert len(boxes) == 2 * len(spacings)  # both directions, every spacing
    for i, (ta, _, a) in enumerate(boxes):
        for tb, _, b in boxes[i + 1 :]:
            assert not overlaps(a, b), (ta, tb)
    root = ET.fromstring(svg)
    width, height = float(root.get("width", "0")), float(root.get("height", "0"))
    assert all(b[0] >= 0 and b[2] <= width and b[3] <= height for _, _, b in boxes)


def test_svg_staggers_only_when_labels_would_collide(tmp_path, example):
    crowded = spacing_boxes(
        render_grid_system_svg(narrow_system(tmp_path, example, [6000.0, 360.0, 317.7, 6000.0]))
    )
    bottom_rows = {b[3] for _, anchor, b in crowded if anchor == "middle"}  # dimension line under the plan
    side_columns = {b[0] for _, anchor, b in crowded if anchor == "start"}  # dimension line beside it
    assert len(bottom_rows) == 2 and len(side_columns) == 2
    plain = spacing_boxes(render_grid_system_svg(narrow_system(tmp_path / "p", example, [6000.0] * 3)))
    assert len({b[3] for _, anchor, b in plain if anchor == "middle"}) == 1
    assert len({b[0] for _, anchor, b in plain if anchor == "start"}) == 1


def test_svg_footer_moves_below_staggered_rows(tmp_path, example):
    system = narrow_system(tmp_path, example, [6000.0, 360.0, 317.7, 6000.0])
    root = ET.fromstring(render_grid_system_svg(system))
    footer_top = min(
        float(t.get("y", "0")) - 12
        for t in root.iter()
        if t.tag.endswith("text") and (t.text or "").startswith("vertical")
    )
    lowest_label = max(b[3] for _, _, b in spacing_boxes(render_grid_system_svg(system)))
    assert lowest_label < footer_top


# --- determinism, inputs, example ------------------------------------------------------------------


def test_deterministic(tmp_path, example):
    w = Work(tmp_path, example)
    w.add_file("b.dxf", [plan("V001", "model#01", 1), plan("V002", "model#02", 3)])
    w.add_file("a.dxf", [plan("V001", "model#01", 1)])
    work = w.finish()
    first = dump_json(build_grid_systems(work))
    assert dump_json(build_grid_systems(work)) == first
    s = json.loads(first)["systems"][0]
    assert s["directions"][0]["representative"]["file"] == "a.dxf"  # sorted inputs
    assert [x["system_id"] for x in json.loads(first)["systems"]] == ["S001"]


def test_stale_or_missing_inputs(tmp_path, example):
    with pytest.raises(GridSystemError) as exc:
        build_grid_systems(tmp_path)
    assert exc.value.exit_code == 2
    w = Work(tmp_path, example)
    w.add_file("plans.dxf", [plan("V001", "model#01", 1)])
    work = w.finish()
    (work / "structure-summary.json").write_text(json.dumps({"inventory_sha256": "0" * 64}), encoding="utf-8")
    with pytest.raises(GridSystemError) as exc:
        build_grid_systems(work)
    assert exc.value.exit_code == 1 and "read-structure" in str(exc.value)


def test_example_is_valid():
    doc = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert gs_problems(doc) == []
    ET.fromstring(render_grid_system_svg(doc["systems"][0]))
