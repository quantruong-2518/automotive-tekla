"""Tool wave 4, package T: assertions on the EVAL-4 drawings, opt-in.

Set HARNESS_CORPUS_TESTS=1 and HARNESS_CORPUS_DXF_DIR to a folder holding the converted DXFs (the dwg2dxf
output, `271_3-story_house_14.2x19.7m.dxf` and `264_6-story_house_6x16.5m.dxf`). They parse untrusted
personal files and take about ten seconds each, so they never run by default.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tekla_harness.extract_text import extract_text
from tekla_harness.text_gate import meaning_block_reason

CORPUS_DIR = (
    Path(os.environ.get("HARNESS_CORPUS_DXF_DIR", "")) if os.environ.get("HARNESS_CORPUS_DXF_DIR") else None
)
needs_eval4 = pytest.mark.skipif(
    not (os.environ.get("HARNESS_CORPUS_TESTS") == "1" and CORPUS_DIR and CORPUS_DIR.is_dir()),
    reason="set HARNESS_CORPUS_TESTS=1 and HARNESS_CORPUS_DXF_DIR to the converted EVAL-4 DXFs",
)


@pytest.fixture(scope="module")
def index_271():
    assert CORPUS_DIR is not None
    return extract_text(CORPUS_DIR / "271_3-story_house_14.2x19.7m.dxf", converter="libredwg")


@needs_eval4
def test_271_title_attribs_with_group_60_do_not_print(index_271):
    # TALLY A1: T000678 (ATTRIB 9E3F9A) has group 60 = 1 and flag bit 1 clear
    by_handle = {e["handle"]: e for e in index_271["entries"] if e["handle"]}
    e = by_handle["9E3F9A"]
    assert (e["printed"], e["not_printed_reasons"], e["invisible"]) == (False, ["entity_invisible"], False)
    hidden = [e for e in index_271["entries"] if not e["printed"]]
    assert {r for e in hidden for r in e["not_printed_reasons"]} == {"entity_invisible"}
    assert len([e for e in hidden if e["handle"]]) == 232  # the EVAL-4 hidden list, by handle
    assert len(hidden) == 305  # plus 73 rebar callout copies inside anonymous blocks


@needs_eval4
def test_271_kinh_stays_blocked(index_271):
    # no font-evidence lift in this wave (review C1): the marks table lists the header ids as blocked
    kinh = [e for e in index_271["entries"] if e["raw_text"] == "K\xcdNH"]
    assert len(kinh) == 16 and all(meaning_block_reason(e) == "encoding_unknown" for e in kinh)
    assert all(e["font_file"] == "arial_3.ttf" for e in kinh)
    assert not any("unicode_by_font_evidence" in e["flags"] for e in index_271["entries"])
