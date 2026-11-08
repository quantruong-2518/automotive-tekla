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


# --- tool wave 2 seam: additive fields (all optional, $id stays 0.1) ------------------------------


@pytest.mark.parametrize("name", ["dimensions", "supplements"])
def test_new_schema_examples_are_valid(name, example):
    assert validate(name, example(name)) == []


def test_new_schemas_keep_id_0_1():
    for name in ("dimensions", "supplements"):
        schema: dict = validator(name).schema  # type: ignore[assignment]
        assert schema["$id"] == f"urn:tekla-harness:schema:{name}:0.1"


def test_supplement_withdrawn_needs_a_reason_and_file_needs_its_sha(example):
    doc = example("supplements")
    del doc["supplements"][1]["withdrawn_reason"]
    assert validate("supplements", doc)
    doc = example("supplements")
    doc["supplements"][0]["file_sha256"] = None
    assert validate("supplements", doc)
    doc = example("supplements")
    doc["supplements"][0]["target_producer"] = "reader"
    assert validate("supplements", doc)


def test_dimensions_are_never_converted(example):
    doc = example("dimensions")
    doc["units"]["converted"] = True
    assert validate("dimensions", doc)


def test_text_index_style_family_source_and_ascii_flag(example):
    doc = example("text-index")
    decode = doc["entries"][0]["decode"]
    decode["source"] = "style_family"
    decode["run_details"][0]["font_source"] = "style_family"
    doc["entries"][0]["flags"] = ["legacy_ascii_suspect"]
    assert validate("text-index", doc) == []
    decode["source"] = "family_guess"
    assert validate("text-index", doc)


def test_probe_hint_matched_on_family(example):
    doc = example("dxf-probe")
    doc["text_encoding_hints"][0]["matched"] = [{"field": "family", "value": ".VnAvantH"}]
    assert validate("dxf-probe", doc) == []
    doc["text_encoding_hints"][0]["matched"] = [{"field": "bigfont", "value": "x"}]
    assert validate("dxf-probe", doc)


def test_sheet_text_unassigned_sheet_and_ascii_reason(example):
    doc = example("sheet-text")
    doc["sheet"] = {
        "sheet_id": "unassigned",
        "space": "model",
        "layout": None,
        "bbox": None,
        "sheet_number": None,
        "duplicate_of": None,
    }
    doc["query"]["unassigned"] = True
    doc["entries"][0]["meaning"] = "blocked"
    doc["entries"][0]["blocked_reason"] = "legacy_ascii_suspect"
    doc["legacy_font_gate"]["by_reason"] = {"legacy_ascii_suspect": 1}
    assert validate("sheet-text", doc) == []
    doc["sheet"]["sheet_id"] = "model#01"  # a real sheet still needs its layout and frame
    assert validate("sheet-text", doc)


def test_sheet_list_and_find_text_new_counts(example):
    listing = example("sheet-list")
    listing["files"][0]["blocked_text_count"] = 3
    assert validate("sheet-text", listing) == []
    found = example("find-text")
    found["query"]["unassigned"] = True
    found["counts"]["unassigned_entries_searched"] = 7
    found["hits"][0]["sheet_id"] = "unassigned"
    assert validate("sheet-text", found) == []


def test_levels_blocked_candidates(example):
    doc = example("levels")
    doc["blocked_candidates"] = [
        {"entry_id": "T000012", "line": 0, "value_text": "+3.850", "reason": "encoding_unknown"}
    ]
    doc["summary"]["blocked_candidates"] = 1
    assert validate("levels", doc) == []
    doc["blocked_candidates"][0]["reason"] = "nope"
    assert validate("levels", doc)


def test_marks_blocked_columns_size_compared_and_by_sheet(example):
    doc = example("marks")
    doc["tables"][0]["blocked_columns"] = [{"column": 2, "entry_id": "T000061", "reason": "encoding_unknown"}]
    match = doc["matching"][0]["matched"][0]
    match["size_compared"] = False
    match["size_not_compared_reason"] = "plan_size_missing"
    doc["summary"]["by_sheet"] = [
        {"file": "plans/set.dxf", "sheet": "model#01", "plan_marks": 3, "tables": 1}
    ]
    doc["summary"]["size_comparisons"] = {"compared": 1, "not_compared": 1}
    assert validate("marks", doc) == []
    match["size_compared"] = True  # a compared size has no reason for not comparing
    assert validate("marks", doc)


def test_callouts_unparsed_by_reason_and_ascii_reason(example):
    doc = example("callouts")
    doc["summary"]["unparsed_by_reason"] = {"no verified pattern": 2}
    doc["blocked_entries"][0]["reason"] = "legacy_ascii_suspect"
    assert validate("callouts", doc) == []


def test_intake_question_closed_by_and_ref_families(example):
    doc = example("intake-questions")
    q = doc["questions"][0]
    q["closed_by"] = {"question_id": "Q-002", "reason": "units_answered"}
    q["refs"][0]["families"] = ["F001", "F002"]
    assert validate("intake", doc) == []
    q["closed_by"] = {"question_id": None, "reason": "rejected_systems_only"}
    assert validate("intake", doc) == []
    q["closed_by"] = {"question_id": None, "reason": "because"}
    assert validate("intake", doc)


def test_answers_role_and_file_set_values(example):
    doc = example("answers")
    answer = doc["answers"][0]
    answer["answered_by_role"] = "simulated"
    assert validate("answers", doc) == []
    answer["answered_by_role"] = "agent"
    assert validate("answers", doc)
    answer["answered_by_role"] = "engineer"
    answer.update(code="file_set_relation", file=None, values={"set1": ["a.dwg", "b.dwg"], "set2": ["c.dwg"]})
    assert validate("answers", doc) == []
    answer["values"] = {"group1": ["a.dwg"]}
    assert validate("answers", doc)
    answer["values"] = {"set1": []}
    assert validate("answers", doc)


def test_reader_findings_decoded_by_and_list_summary(example):
    doc = example("reader-findings")
    doc["findings"][0]["decoded_by"] = [
        {
            "source": "knowledge_table",
            "knowledge_pattern": "vntimeh.shx",
            "row_status": "approved",
            "decided_on": "2026-11-07",
            "entries": ["T000001"],
        }
    ]
    doc["summary"] = {"by_class": {"general_notes": 1}}
    assert validate("reader-findings", doc) == []
    doc["findings"][0]["decoded_by"][0]["row_status"] = "maybe"
    assert validate("reader-findings", doc)


def test_grid_system_conflict_question_id_and_file_sets(example):
    doc = example("grid-system")
    doc["conflicts"][0]["question_id"] = "Q-023"
    doc["file_sets"] = {
        "status": "answered",
        "sets": [["a.dwg", "b.dwg"], ["c.dwg"]],
        "question_id": "Q-030",
    }
    assert validate("grid-system", doc) == []
    doc["file_sets"] = {"status": "pending", "sets": None, "question_id": "Q-030"}
    assert validate("grid-system", doc) == []


def test_status_gate1_closed_and_non_engineer_answers(example):
    doc = example("status")
    doc["gate1"]["closed"] = [{"id": "Q-005", "reason": "units_answered"}]
    doc["gate1"]["non_engineer_answers"] = [
        {"question_id": "Q-001", "code": "units_confirm_all", "file": "S-101.dwg", "role": "simulated"}
    ]
    assert validate("status", doc) == []
    doc["gate1"]["closed"] = [{"id": "Q-005", "reason": "answered"}]
    assert validate("status", doc)


@pytest.mark.parametrize(
    ("name", "schema"),
    [
        ("text-index", "text-index"),
        ("dxf-probe", "dxf-probe"),
        ("sheet-text", "sheet-text"),
        ("sheet-list", "sheet-text"),
        ("find-text", "sheet-text"),
        ("levels", "levels"),
        ("marks", "marks"),
        ("callouts", "callouts"),
        ("intake-questions", "intake"),
        ("answers", "answers"),
        ("reader-findings", "reader-findings"),
        ("grid-system", "grid-system"),
        ("status", "status"),
    ],
)
def test_current_outputs_still_validate_without_the_new_fields(example, name, schema):
    assert validate(schema, example(name)) == []
