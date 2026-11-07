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
    render_grid_system_svg,
)
from tekla_harness.grids import coordinate_string
from tekla_harness.intake import dump_json
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


def _row(path: str, digest: str, example: Any) -> dict[str, Any]:
    row = copy.deepcopy(example("intake")["files"][0])
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
        self.rows.append(_row(path, sha(content or path), self.example))

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
    assert all(q["blocking"] for q in doc["questions"])


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
    assert q["blocking"] and "S001" in q["where"] and "S002" in q["where"]
    assert "A-B" in q["found"] and "1-2" in q["found"]
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
    assert len(q) == 1 and q[0]["blocking"] and "S001" in q[0]["where"]
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
    assert ("mm" in conflict["found"]) == (len(answers) == 2)  # a millimetre comparison says so
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


def test_answers_digest_covers_only_the_active_units_and_axis_answers():
    base = [ans("units_suspect", "a.dxf", {"unit": "cm"})]
    digest = consumed_answers_digest(base)
    assert consumed_answers_digest([*base, ans("grid_system_select", None, {})]) == digest
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
    assert "grid_system_axis_unassigned" not in codes(doc)


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
