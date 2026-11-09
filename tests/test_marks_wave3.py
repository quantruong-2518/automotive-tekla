"""marks, tool wave 3 (package M): lintel marks with a length in brackets (`LT1(L=4700)`, drawing 267),
plan marks compared with RC detail headings (a4), and the per-file mark sets (W6). Synthetic drawings only
(see _marks_fixtures / _callout_fixtures)."""

from __future__ import annotations

from typing import Any

import pytest

from tekla_harness.marks import parse_mark

# --- lintel marks with a length (267 T003614 'LT1(L=4700)') ----------------------------------------------


@pytest.mark.parametrize(
    ("text", "mark", "numbers"),
    [
        ("LT1(L=4700)", "LT1", ["1"]),
        ("LT10(L=3700)", "LT10", ["10"]),
        ("LT3 (L = 1800)", "LT3", ["3"]),
        ("LT2-1(L=3200)", "LT2-1", ["2", "1"]),
        ("LT4(L=1,5)", "LT4", ["4"]),
    ],
)
def test_a_mark_with_a_length_in_brackets_is_the_mark(text, mark, numbers):
    m = parse_mark(text)
    assert m is not None and m.text == mark and list(m.numbers) == numbers
    assert m.size is None  # a length is no section


@pytest.mark.parametrize(
    "text", ["L=4700", "LT1(L=)", "LT1(L=4700", "LT1(L=4700) D2", "LT1(H=4700)", "(L=4700)"]
)
def test_not_a_mark_with_a_length(text):
    assert parse_mark(text) is None


def test_a_lintel_plan_mark_keeps_the_whole_line(tmp_path):
    from _marks_fixtures import build_marks_work
    from tekla_harness.marks import extract_marks

    work = build_marks_work(tmp_path, plan_texts=("LT1(L=4700)", "LT1(L=4700)", "LT2(L=3200)", "D1"))
    doc: dict[str, Any] = extract_marks(work, tmp_path / "input")
    lintels = [p for p in doc["plan_marks"] if p["mark"].startswith("LT")]
    assert [(p["mark"], p["display_text"], p["form"], p["size"]) for p in lintels] == [
        ("LT1", "LT1(L=4700)", "plain", None),
        ("LT1", "LT1(L=4700)", "plain", None),
        ("LT2", "LT2(L=3200)", "plain", None),
    ]
    assert {p["key"] for p in lintels} == {"lt1", "lt2"}
