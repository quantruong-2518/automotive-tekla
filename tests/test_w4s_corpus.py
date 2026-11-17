"""Tool wave 4, package S: assertions on the known drawings, opt-in.

Set HARNESS_CORPUS_TESTS=1 and HARNESS_CORPUS_DXF_DIR to a folder holding the converted DXFs (the dwg2dxf
output: `180_steel_building.dxf`, `271_3-story_house_14.2x19.7m.dxf`, `278_5-story_house_4.4x15.3m.dxf`,
`285_3-story_house_8.2x15m.dxf`). They parse untrusted personal files and take 5 to 40 seconds each, so they
never run by default. A file that is not in the folder skips its test.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from tekla_harness.extract_text import extract_text
from tekla_harness.levels import extract_levels
from tekla_harness.sheets import extract_sheets

CORPUS_DIR = (
    Path(os.environ.get("HARNESS_CORPUS_DXF_DIR", "")) if os.environ.get("HARNESS_CORPUS_DXF_DIR") else None
)
ENABLED = os.environ.get("HARNESS_CORPUS_TESTS") == "1" and CORPUS_DIR is not None and CORPUS_DIR.is_dir()
needs_corpus = pytest.mark.skipif(not ENABLED, reason="set HARNESS_CORPUS_TESTS=1 and HARNESS_CORPUS_DXF_DIR")


def _load(name: str) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    assert CORPUS_DIR is not None
    path = CORPUS_DIR / name
    if not path.is_file():
        pytest.skip(f"{name} is not in HARNESS_CORPUS_DXF_DIR")
    index = extract_text(path, converter="libredwg")
    return path, index, extract_sheets(path, index)


def _numbers(sheets: dict[str, Any]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for s in sheets["sheets"]:
        n = s["title_block"]["sheet_number"]
        out[s["sheet_id"]] = n["value"] if n else None
    return out


@needs_corpus
def test_180_numbers_come_from_the_drawing_number_labels_and_j01_is_the_job():
    _path, _index, sheets = _load("180_steel_building.dxf")
    assert sorted(v for v in _numbers(sheets).values() if v) == sorted(
        ["P-01", "P-01A", "P-01B", "P-02A", "P-02B", "P-04", "3D-1", "3D-2"]
    )
    assert {s["title_block"]["job_number"]["value"] for s in sheets["sheets"]} == {"J-01"}
    assert not [q for q in sheets["questions"] if q["code"] == "sheet_number_duplicate"]


@needs_corpus
def test_271_kc_00_frame_is_a_sheet_and_the_drawing_list_header_is_no_number():
    _path, _index, sheets = _load("271_3-story_house_14.2x19.7m.dxf")
    (kc00,) = [s for s in sheets["sheets"] if s["bbox"][:2] == pytest.approx([164846, 234376], abs=2)]
    assert kc00["bbox"] == pytest.approx([164846, 234376, 215925, 270497], abs=3)
    assert (kc00["title_block"]["sheet_number"] or {}).get("value") == "kc - 00"
    values = {c["value"] for s in sheets["sheets"] for c in s["title_block"]["candidates"]}
    assert "dm-00" not in values
    assert len(sheets["sheets"]) == 35


@needs_corpus
def test_278_levels_with_two_spaces_after_the_sign_have_their_storey_names():
    path, index, sheets = _load("278_5-story_house_4.4x15.3m.dxf")
    levels = extract_levels(path, index, sheets)
    by_value = {lv["value"]: lv["names"] for lv in levels["levels"]}
    for value in (0.0, 2.5, 5.5, 8.8, 12.1, 23.0, 26.15, 28.65):
        assert value in by_value, value
    assert any("1" in n for n in by_value[0.0])  # TẦNG 1
    assert not [q for q in levels["questions"] if q["code"] == "level_datum_not_found"]


@needs_corpus
def test_285_storey_names_beside_taller_name_texts():
    path, index, sheets = _load("285_3-story_house_8.2x15m.dxf")
    levels = extract_levels(path, index, sheets)
    names: dict[float, set[str]] = {}
    for c in levels["candidates"]:
        if c["name"] and c["value"]["value"] in (0.45, 4.35, 7.95):
            names.setdefault(c["value"]["value"], set()).add(c["name"]["value"].casefold())
    assert names[0.45] >= {"tầng 1"}
    assert names[4.35] >= {"tầng 2"}
    assert names[7.95] >= {"tầng 3"}
