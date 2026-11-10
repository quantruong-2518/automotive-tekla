"""Tool wave 4, package G: grid numbers on the EVAL-3 / EVAL-4 drawings (opt-in, never in CI).

Set HARNESS_CORPUS_TESTS=1 and HARNESS_CORPUS_DXF_DIR to a folder holding the converted DXFs (the dwg2dxf
output of 180, 264, 271, 278, 285 and 286; the files are the known EVAL-3 / EVAL-4 drawings under
dwg-lab/samples/L3-complex/). A test skips when its drawing is not in the folder.
"""

from __future__ import annotations

import os
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from tekla_harness.extract_text import extract_text
from tekla_harness.grids import extract_grids
from tekla_harness.sheets import extract_sheets

_DIR = os.environ.get("HARNESS_CORPUS_DXF_DIR")
CORPUS_DIR = Path(_DIR) if _DIR else None
ENABLED = os.environ.get("HARNESS_CORPUS_TESTS") == "1" and CORPUS_DIR is not None and CORPUS_DIR.is_dir()


@cache
def grids_of(prefix: str) -> dict[str, Any]:
    assert CORPUS_DIR is not None
    found = sorted(CORPUS_DIR.glob(f"{prefix}*.dxf"))
    if not found:
        pytest.skip(f"no {prefix}*.dxf in {CORPUS_DIR}")
    index = extract_text(found[0])
    return extract_grids(found[0], index, extract_sheets(found[0], index))


def families(doc: dict[str, Any]) -> list[tuple[str, str]]:
    """(labels, coordinates) of every family with a proposal (sheet ids are detector ids: not asserted)."""
    return [
        (f["proposal"]["labels"], f["proposal"]["coordinates"])
        for g in doc["groups"]
        for f in g["families"]
        if f["proposal"]
    ]


def labels_of(doc: dict[str, Any]) -> set[str]:
    return {
        a["label"]["value"] for g in doc["groups"] for f in g["families"] for a in f["axes"] if a["label"]
    }


needs_corpus = pytest.mark.skipif(not ENABLED, reason="set HARNESS_CORPUS_TESTS=1 and HARNESS_CORPUS_DXF_DIR")


@needs_corpus
def test_180_framing_plan_grid_is_read_from_obround_bubbles():
    found = families(grids_of("180"))
    assert ("7 6 5 4 3 2 1", "0 8200 8248 8018 3*8073") in found


@needs_corpus
def test_285_end_bubbles_pair_with_the_axis_lines():
    found = families(grids_of("285"))
    assert ("1 2 3 4 5", "0 3130 3540 3520 4590") in found
    assert not any(labels.startswith("a a") for labels, _ in found)


@needs_corpus
def test_278_star_axis_and_stacked_plans_and_no_elevation():
    doc = grids_of("278")
    assert ("1 2 2* 3 4", "0 5850 2060 2940 4150") in families(doc)
    assert not any(labels == "1 2* 2 4" for labels, _ in families(doc))  # the KT-08 elevation


@needs_corpus
def test_271_rebar_bubbles_are_no_axes():
    doc = grids_of("271")
    assert not labels_of(doc) & {"12", "14", "20"}


@needs_corpus
def test_264_non_grid_bubbles_are_no_axes():
    found = families(grids_of("264"))
    assert not any(labels in {"2 5 1", "2 4 1"} for labels, _ in found)
    assert any(labels == "2 1" for labels, _ in found)


@needs_corpus
def test_286_keeps_its_plan_grid():
    found = families(grids_of("286"))
    assert any(labels == "1 2 3" and coords in ("0 3400 3980", "0 3399.8 3980.1") for labels, coords in found)
    assert any(labels == "A B C" and coords == "0 4840 4190" for labels, coords in found)
