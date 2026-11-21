"""unassigned_clusters: text printed outside every sheet frame goes to a frame by position (read-only).

The work folder is a real `run_intake` of a DXF with loose text; the sheets document is then replaced by two
synthetic frames so every position rule is exercised on known coordinates.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from ezdxf.filemanagement import new

from tekla_harness.cli import main
from tekla_harness.intake import dump_json, run_intake
from tekla_harness.knowledge import EMPTY_TABLE
from tekla_harness.sheet_text import STRUCTURE_DIR, ReaderError, unassigned_clusters
from tekla_harness.sheet_text import _locate as _locate_raw

REL = "loose.dxf"
# frame A [0,0,1000,1000] (model#01), frame B [2000,0,3000,1000] (model#02)
POINTS = {
    "below_a1": (100, -50),  # gap 50
    "below_a2": (500, -300),  # gap 300
    "blocked": (900, -100),  # gap 100; unknown encoding: blocked, still carried
    "right_b": (3200, 500),  # beside B, gap 200
    "none": (1500, -500),  # x in no range, y in no range
    "tie": (1500, 500),  # y in both ranges: A right gap 500 = B left gap 500
    "hidden": (100, -700),  # below A but does not print
    "above_b": (2500, 1400),  # above B, gap 400
}


@pytest.fixture(scope="module")
def work(tmp_path_factory) -> Path:
    base = tmp_path_factory.mktemp("clusters")
    root = base / "input"
    root.mkdir()
    doc = new("R2018", setup=True)
    msp = doc.modelspace()
    for name, (x, y) in POINTS.items():
        text = "C1 b\xb6n" if name == "blocked" else name
        msp.add_text(text, height=250, dxfattribs={"insert": (x, y)})
    doc.saveas(root / REL)
    out = base / "work"
    run_intake(root, out, "demo-clusters", knowledge=EMPTY_TABLE)
    path = out / "text" / f"{REL}.json"
    index = json.loads(path.read_text(encoding="utf-8"))
    ids = {e["display_text"] if e["display_text"] in POINTS else "blocked": e["id"] for e in index["entries"]}
    for e in index["entries"]:
        if e["id"] == ids["hidden"]:
            e["printed"] = False
    path.write_text(json.dumps(index), encoding="utf-8")

    def sheet(sid: str, bbox: list[float], number: str, space: str = "model") -> dict[str, Any]:
        return {
            "sheet_id": sid,
            "space": space,
            "layout": "Model" if space == "model" else space,
            "bbox": bbox,
            "title_block": {"sheet_number": {"value": number, "confidence": "high"}},
            "text_ids": [],
        }

    sheets = {
        "schema_version": "0.1",
        "file": index["file"],
        "sheets": [
            sheet("model#02", [2000.0, 0.0, 3000.0, 1000.0], "S-2"),
            sheet("model#01", [0.0, 0.0, 1000.0, 1000.0], "S-1"),
            # a paper frame that would capture model text if spaces were mixed
            sheet("Layout1#01", [0.0, -2000.0, 1000.0, -10.0], "P-1", space="Layout1"),
        ],
        "unassigned": {"text_ids": sorted(ids.values()), "ambiguous_text_ids": []},
    }
    (out / STRUCTURE_DIR).mkdir()
    (out / STRUCTURE_DIR / f"{REL}.sheets.json").write_text(dump_json(sheets), encoding="utf-8")
    (base / "ids.json").write_text(json.dumps(ids), encoding="utf-8")
    return out


def ids_map(work: Path) -> dict[str, str]:
    return json.loads((work.parent / "ids.json").read_text(encoding="utf-8"))


def ids_of(work: Path, *names: str) -> list[str]:
    return sorted(ids_map(work)[n] for n in names)


def by_key(doc: dict[str, Any]) -> dict[tuple[str | None, str], dict[str, Any]]:
    return {(c["sheet_id"], c["side"]): c for c in doc["clusters"]}


def test_entries_go_to_the_nearest_frame_by_range(work):
    doc = unassigned_clusters(work)
    clusters = by_key(doc)
    assert set(clusters) == {
        ("model#01", "below"),
        ("model#01", "right"),
        ("model#02", "right"),
        ("model#02", "above"),
        (None, "none"),
    }
    assert [(c["sheet_id"], c["side"]) for c in doc["clusters"]] == [
        ("model#01", "below"),
        ("model#01", "right"),
        ("model#02", "above"),
        ("model#02", "right"),
        (None, "none"),
    ]
    below = clusters[("model#01", "below")]
    assert below["entry_ids"] == ids_of(work, "below_a1", "below_a2", "blocked")
    assert (below["file"], below["sheet_number"], below["entry_count"]) == (
        REL,
        {"value": "S-1", "confidence": "high"},
        3,
    )
    assert (below["gap_min"], below["gap_max"]) == (50.0, 300.0)
    assert clusters[("model#02", "right")]["entry_ids"] == ids_of(work, "right_b")
    assert clusters[("model#02", "right")]["gap_min"] == 200.0
    above = clusters[("model#02", "above")]
    assert (above["entry_ids"], above["gap_min"], above["gap_max"]) == (ids_of(work, "above_b"), 400.0, 400.0)


def test_tie_goes_to_the_lower_sheet_id(work):
    clusters = by_key(unassigned_clusters(work))
    assert clusters[("model#01", "right")]["entry_ids"] == ids_of(work, "tie")
    assert clusters[("model#01", "right")]["gap_min"] == 500.0


def test_entry_in_no_range_is_one_cluster_without_a_sheet(work):
    none = by_key(unassigned_clusters(work))[(None, "none")]
    assert none["entry_ids"] == ids_of(work, "none")
    assert none["sheet_number"] is None and none["gap_min"] is None and none["gap_max"] is None


def test_cluster_bbox_covers_its_entry_positions(work):
    below = by_key(unassigned_clusters(work))[("model#01", "below")]
    assert below["bbox"] == [100.0, -300.0, 900.0, -50.0]


def test_totals_count_printed_excluded_and_sides(work):
    doc = unassigned_clusters(work)
    assert doc["totals"] == {
        "printed_unassigned": 7,
        "not_printed_excluded": 1,
        "blocked": 1,
        "by_side": {"below": 3, "above": 1, "left": 0, "right": 2, "inside": 0, "none": 1},
        "clusters": 5,
    }
    every = [i for c in doc["clusters"] for i in c["entry_ids"]]
    assert ids_map(work)["hidden"] not in every and len(every) == 7


def test_blocked_entries_are_flagged_never_decoded(work):
    below = by_key(unassigned_clusters(work))[("model#01", "below")]
    assert below["blocked_entry_ids"] == ids_of(work, "blocked")
    assert "C1" not in json.dumps(below)  # no text of any entry is returned


def test_file_filter_and_unknown_file(work):
    assert unassigned_clusters(work, file_rel=REL)["totals"]["printed_unassigned"] == 7
    with pytest.raises(ReaderError) as exc:
        unassigned_clusters(work, file_rel="nope.dxf")
    assert exc.value.exit_code == 2


def test_writes_nothing(work):
    before = sorted((p.relative_to(work), p.stat().st_mtime_ns) for p in work.rglob("*") if p.is_file())
    unassigned_clusters(work)
    after = sorted((p.relative_to(work), p.stat().st_mtime_ns) for p in work.rglob("*") if p.is_file())
    assert before == after


def test_missing_sheets_document_is_skipped_with_a_warning(work, tmp_path):
    copy = tmp_path / "copy"
    shutil.copytree(work, copy)
    (copy / STRUCTURE_DIR / f"{REL}.sheets.json").unlink()
    doc = unassigned_clusters(copy)
    assert doc["clusters"] == [] and any("read-structure" in w for w in doc["warnings"])


def test_cli_prints_json_and_help_lists_it(work, capsys):
    assert main(["unassigned-clusters", str(work)]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["kind"] == "unassigned_clusters" and doc["totals"]["printed_unassigned"] == 7
    assert main(["unassigned-clusters", str(work), "--file", "nope.dxf"]) == 2
    assert main(["unassigned-clusters", str(work / "missing")]) == 2


def _copy_with(work: Path, tmp_path: Path, edit) -> Path:
    copy = tmp_path / "copy"
    shutil.copytree(work, copy)
    edit(copy)
    return copy


def test_entry_inside_a_frame_box_is_side_inside(work, tmp_path):
    tie = ids_map(work)["tie"]
    sheets_path = work / STRUCTURE_DIR / f"{REL}.sheets.json"

    def edit(copy: Path) -> None:
        path = copy / STRUCTURE_DIR / f"{REL}.sheets.json"
        doc = json.loads(sheets_path.read_text(encoding="utf-8"))
        doc["unassigned"]["text_ids"].remove(tie)
        doc["unassigned"]["ambiguous_text_ids"] = [tie]
        for s in doc["sheets"]:
            if s["sheet_id"] == "model#01":
                s["bbox"] = [0.0, 0.0, 1600.0, 1000.0]
        path.write_text(json.dumps(doc), encoding="utf-8")

    doc = unassigned_clusters(_copy_with(work, tmp_path, edit))
    inside = by_key(doc)[("model#01", "inside")]
    assert inside["entry_ids"] == [tie] and inside["gap_min"] == 0.0
    assert doc["totals"]["by_side"]["inside"] == 1


def test_entry_without_a_position_goes_to_none_and_not_to_its_bbox(work, tmp_path):
    ids = ids_map(work)

    def edit(copy: Path) -> None:
        path = copy / "text" / f"{REL}.json"
        index = json.loads(path.read_text(encoding="utf-8"))
        for e in index["entries"]:
            if e["id"] == ids["above_b"]:
                e["position"]["x"] = e["position"]["y"] = None
        path.write_text(json.dumps(index), encoding="utf-8")

    clusters = by_key(unassigned_clusters(_copy_with(work, tmp_path, edit)))
    none = clusters[(None, "none")]
    assert none["entry_ids"] == sorted([ids["none"], ids["above_b"]])
    assert none["bbox"] == [1500.0, -500.0, 1500.0, -500.0]
    assert ("model#02", "above") not in clusters


def test_file_naming_a_non_drawing_is_a_usage_error(work, tmp_path):
    def edit(copy: Path) -> None:
        path = copy / "inventory.json"
        inv = json.loads(path.read_text(encoding="utf-8"))
        inv["files"].append({**inv["files"][0], "path": "notes.pdf", "format": "pdf"})
        path.write_text(json.dumps(inv), encoding="utf-8")

    copy = _copy_with(work, tmp_path, edit)
    with pytest.raises(ReaderError) as exc:
        unassigned_clusters(copy, file_rel="notes.pdf")
    assert exc.value.exit_code == 2 and "not a DXF/DWG" in str(exc.value)


def test_gaps_and_bbox_are_rounded(work, tmp_path):
    def edit(copy: Path) -> None:
        path = copy / STRUCTURE_DIR / f"{REL}.sheets.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        for s in doc["sheets"]:
            if s["sheet_id"] == "model#01":
                s["bbox"][1] = 0.1 + 0.2  # float noise below the frame edge
        path.write_text(json.dumps(doc), encoding="utf-8")

    below = by_key(unassigned_clusters(_copy_with(work, tmp_path, edit)))[("model#01", "below")]
    assert below["gap_min"] == 50.3 and below["gap_max"] == 300.3


def _locate(x: float, y: float, frames: list[dict[str, Any]]) -> tuple[dict[str, Any], str, float | None]:
    frame, side, gap = _locate_raw(x, y, frames)
    assert frame is not None
    return frame, side, gap


def _frame(sid, bbox):
    return {"sheet_id": sid, "bbox": bbox}


A = _frame("model#01", [0.0, 0.0, 1000.0, 1000.0])
B = _frame("model#02", [2000.0, 0.0, 3000.0, 1000.0])
C = _frame("model#03", [0.0, 2000.0, 1000.0, 3000.0])


def test_locate_compares_x_and_y_range_candidates_by_gap():
    # (2100, 2200): x in B's range (above B, gap 1200) and y in C's range (right of C, gap 1100)
    frame, side, gap = _locate(2100.0, 2200.0, [B, C])
    assert (frame["sheet_id"], side, gap) == ("model#03", "right", 1100.0)
    # (2950, 2050): above B gap 1050 beats right of C gap 1950
    frame, side, gap = _locate(2950.0, 2050.0, [C, B])
    assert (frame["sheet_id"], side, gap) == ("model#02", "above", 1050.0)


def test_locate_inside_and_ties():
    frame, side, gap = _locate(500.0, 500.0, [A])
    assert (frame["sheet_id"], side, gap) == ("model#01", "inside", 0.0)
    overlap = _frame("model#10", [400.0, 400.0, 1400.0, 1400.0])
    frame, side, gap = _locate(500.0, 500.0, [overlap, A])  # in both boxes: lower id
    assert (frame["sheet_id"], side) == ("model#01", "inside")
    nine, ten = _frame("model#9", A["bbox"]), _frame("model#10", A["bbox"])
    assert _locate(500.0, -10.0, [ten, nine])[0]["sheet_id"] == "model#9"  # numeric, not string order
    assert _locate_raw(1500.0, 1500.0, [A, B]) == (None, "none", None)
