"""text_gate: the legacy-font gate on one text-index entry."""

from __future__ import annotations

from typing import Any

import pytest

from tekla_harness.text_gate import BLOCK_REASONS, meaning_allowed, meaning_block_reason


def entry(
    raw: str, encoding: str = "unicode", flags: tuple[str, ...] = (), runs: tuple[str, ...] = ()
) -> dict[str, Any]:
    return {
        "raw_text": raw,
        "flags": list(flags),
        "decode": {"encoding_used": encoding, "run_details": [{"encoding": r} for r in runs]},
    }


@pytest.mark.parametrize("encoding", ["unknown", "tcvn3", "vni", "unicode", "mixed"])
def test_ascii_raw_text_is_always_allowed(encoding):
    assert meaning_allowed(entry("D1.1(220X350) %%c16a200", encoding, ("proposed_knowledge_row",)))


@pytest.mark.parametrize(
    ("e", "reason"),
    [
        (entry("b\xaan v\xcf", "unknown"), "encoding_unknown"),
        (entry("b\xaan v\xcf", "mixed", runs=("unicode", "unknown")), "encoding_unknown"),
        (entry("b\xaan v\xcf", "unknown", ("proposed_knowledge_row",)), "encoding_proposed"),
        (entry("b\xaan v\xcf", "tcvn3", ("knowledge_conflict",)), "knowledge_conflict"),
        (entry("bản vẽ", "tcvn3", ("unicode_evidence_contradicts_font",)), "encoding_contradiction"),
    ],
)
def test_non_ascii_text_of_unsettled_encoding_is_blocked(e, reason):
    assert meaning_block_reason(e) == reason and reason in BLOCK_REASONS


@pytest.mark.parametrize("encoding", ["unknown", "tcvn3", "vni"])
def test_ascii_text_flagged_as_legacy_looking_is_blocked(encoding):
    # extract_text flags pure-ASCII text of a legacy-font style that looks like legacy Vietnamese (fix 2b)
    e = entry("4/g14", encoding, ("legacy_ascii_suspect", "proposed_knowledge_row"))
    assert meaning_block_reason(e) == "legacy_ascii_suspect" and "legacy_ascii_suspect" in BLOCK_REASONS
    assert meaning_allowed(entry("D1", encoding))


@pytest.mark.parametrize("encoding", ["unicode", "tcvn3", "vni"])
def test_non_ascii_text_of_a_decided_encoding_is_allowed(encoding):
    assert meaning_allowed(entry("bản vẽ", encoding))
    assert meaning_allowed(entry("bản vẽ", "mixed", runs=("unicode", encoding)))


# --- tool wave 4, V2: the font-evidence flag lifts only encoding_unknown ---------------------------------


@pytest.mark.parametrize(
    ("e", "reason"),
    [
        (entry("K\xcdNH", "unknown", ("unicode_by_font_evidence",)), None),
        (entry("K\xcdNH", "mixed", ("unicode_by_font_evidence",), runs=("unicode", "unknown")), None),
        (
            entry("K\xcdNH", "unknown", ("unicode_by_font_evidence", "proposed_knowledge_row")),
            "encoding_proposed",
        ),
        (
            entry("K\xcdNH", "unknown", ("unicode_by_font_evidence", "knowledge_conflict")),
            "knowledge_conflict",
        ),
        (
            entry("K\xcdNH", "unknown", ("unicode_by_font_evidence", "unicode_evidence_contradicts_font")),
            "encoding_contradiction",
        ),
        (
            entry("4/g14", "unknown", ("unicode_by_font_evidence", "legacy_ascii_suspect")),
            "legacy_ascii_suspect",
        ),
        (entry("K\xcdNH", "unknown"), "encoding_unknown"),
        (entry("K\xcdNH", "mixed", runs=("unicode", "unknown")), "encoding_unknown"),
    ],
)
def test_the_font_evidence_flag_lifts_encoding_unknown_and_nothing_else(e, reason):
    assert meaning_block_reason(e) == reason
