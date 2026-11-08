from __future__ import annotations

import copy

import pytest

from tekla_harness.schemas import validate, validator


@pytest.mark.parametrize("name", ["spec", "project-state", "read-log"])
def test_examples_are_valid(name, example):
    assert validate(name, example(name)) == []


def test_unknown_schema_rejected():
    with pytest.raises(KeyError):
        validator("common")


# --- spec: schema rules ---------------------------------------------------------


def test_value_without_provenance_rejected(example):
    spec = example("spec")
    del spec["members"][0]["profile"]["provenance"]
    assert any("provenance" in p.message for p in validate("spec", spec))


def test_bad_confidence_rejected(example):
    spec = example("spec")
    spec["members"][0]["profile"]["confidence"] = "certain"
    assert validate("spec", spec)


def test_units_must_be_mm(example):
    spec = example("spec")
    spec["units"] = "m"
    assert validate("spec", spec)


def test_unknown_member_field_rejected(example):
    spec = example("spec")
    spec["members"][0]["colour"] = "red"
    assert validate("spec", spec)


# --- spec: semantic rules -------------------------------------------------------


def test_duplicate_spec_id(example):
    spec = example("spec")
    spec["members"][1]["spec_id"] = spec["members"][0]["spec_id"]
    assert any("duplicate spec_id" in p.message for p in validate("spec", spec))


def test_zero_length_member(example):
    spec = example("spec")
    spec["members"][0]["end"] = copy.deepcopy(spec["members"][0]["start"])
    assert any("less than 1 mm" in p.message for p in validate("spec", spec))


def test_low_confidence_needs_question(example):
    spec = example("spec")
    del spec["members"][2]["question_ids"]
    assert any("without a question_id" in p.message for p in validate("spec", spec))


def test_question_must_be_open(example):
    spec = example("spec")
    spec["open_questions"] = []
    assert any("not listed in open_questions" in p.message for p in validate("spec", spec))


# --- project-state --------------------------------------------------------------


def test_gate_decision_needs_engineer(example):
    state = example("project-state")
    del state["gates"]["g1_plan"]["decided_by"]
    assert validate("project-state", state)


# --- read-log -------------------------------------------------------------------


def test_failed_attempt_needs_error(example):
    log = example("read-log")
    del log["files"][0]["attempts"][0]["error"]
    assert validate("read-log", log)


@pytest.mark.parametrize("lot", [1.0, 2147483648, 9007199254740992])
def test_lot_must_be_int32(example, lot):
    spec = example("spec")
    spec["lot"] = lot
    assert any("lot" in p.path for p in validate("spec", spec))


def test_lot_int32_maximum_ok(example):
    spec = example("spec")
    spec["lot"] = 2147483647
    assert validate("spec", spec) == []


# --- ECMA-262 pattern semantics (ADR-0010 Amendment 1, review fix M1) --------------------


@pytest.mark.parametrize(
    ("pattern", "text", "ok"),
    [
        ("^[A-Z]+$", "AB", True),
        ("^[A-Z]+$", "AB\n", False),  # Python `$` matches before a final newline; ECMA's does not
        ("^(?!\\.{1,2}$)[^/\\\\]+$", "..\n", True),  # `[^/\\]` accepts \n; lookahead `$` is end of input
        ("^(?!\\.{1,2}$)[^/\\\\]+$", "..", False),
        ("^a.c$", "a\rc", False),  # ECMA `.` excludes every line terminator
        ("^a.c$", "a\u2028c", False),
        ("^a.c$", "abc", True),
        ("^[$]$", "$", True),  # `$` inside a class stays literal
        ("^\\$$", "$", True),  # escaped `$` stays literal
        ("^[.]$", "x", False),  # `.` inside a class stays literal
        ("\\S", " x ", True),
    ],
)
def test_pattern_uses_ecma_semantics(pattern, text, ok):
    from tekla_harness.schemas import ecma_regex

    assert bool(ecma_regex(pattern).search(text)) is ok


def test_spec_id_with_trailing_newline_rejected(example):
    spec = example("spec")
    spec["members"][1]["spec_id"] = spec["members"][0]["spec_id"] + "\n"
    assert any(p.path == "/members/1/spec_id" for p in validate("spec", spec))


def test_every_schema_pattern_translates():
    import json as _json

    from tekla_harness.schemas import ecma_regex, schema_dir

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "pattern" and isinstance(value, str):
                    yield value
                yield from walk(value)
        elif isinstance(node, list):
            for item in node:
                yield from walk(item)

    docs = [_json.loads(f.read_text("utf-8")) for f in schema_dir().glob("*.schema.json")]
    patterns = {p for doc in docs for p in walk(doc)}
    assert patterns
    for p in patterns:
        ecma_regex(p)
