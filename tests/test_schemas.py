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


def test_code_enums_match_their_schema_copies():
    """ROLES and CLOSURE_REASONS are repeated in schemas; a change to one side must reach the other."""
    from tekla_harness.questions import CLOSURE_REASONS, ROLES

    def enum_at(name: str, *path: str) -> set[str]:
        node: dict = validator(name).schema  # type: ignore[assignment]
        for key in path:
            node = node[key]
        return set(node["enum"])

    assert enum_at("answers", "$defs", "answer", "properties", "answered_by_role") == set(ROLES)
    intake = ("$defs", "question", "properties", "closed_by", "properties", "reason")
    status = ("properties", "gate1", "properties", "closed", "items", "properties", "reason")
    assert enum_at("intake", *intake) == set(CLOSURE_REASONS)
    assert enum_at("status", *status) == set(CLOSURE_REASONS)


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


# --- tool wave 3 seam: new codes and fields (all optional, $id stays 0.1) -------------------------


GRID_ANSWER_VALUES = {
    "dir1_labels": ["1", "2", "3"],
    "dir1_spacings": [3130, 3540.5],
    "dir2_labels": ["A", "B"],
    "dir2_spacings": [4250],
}


def test_answers_grid_system_missing_values(example):
    doc = example("answers")
    answer = doc["answers"][0]
    answer.update(code="grid_system_missing", file="S-101.dwg", values=dict(GRID_ANSWER_VALUES))
    assert validate("answers", doc) == []
    answer["values"]["sheet"] = "model#05"
    assert validate("answers", doc) == []
    answer["values"] = {}  # words only: recorded, builds nothing
    assert validate("answers", doc) == []
    for bad in (
        {k: v for k, v in GRID_ANSWER_VALUES.items() if k != "dir2_spacings"},
        {**GRID_ANSWER_VALUES, "dir1_spacings": [3130, 0]},
        {**GRID_ANSWER_VALUES, "dir1_labels": "1,2,3"},
        {**GRID_ANSWER_VALUES, "dir1_labels": ["1"], "dir1_spacings": []},
        {**GRID_ANSWER_VALUES, "dir1_labels": ["1", "1", "2"]},
        {**GRID_ANSWER_VALUES, "dir3_labels": ["X", "Y"]},
        {**GRID_ANSWER_VALUES, "sheet": ""},
    ):
        answer["values"] = bad
        assert validate("answers", doc), bad
    answer.update(code="grid_answer_contradicts_drawing", values={"unit": "mm"})
    assert validate("answers", doc)  # takes no value
    answer["values"] = {}
    assert validate("answers", doc) == []


def test_registry_obsolete_reason_only_on_obsolete_entries(example):
    doc = example("question-registry")
    entries = list(doc["questions"].values())
    obsolete = next(e for e in entries if e["status"] == "obsolete")
    live = next(e for e in entries if e["status"] != "obsolete")
    obsolete["obsolete_reason"] = "the latest intake run no longer raises it"
    assert validate("question-registry", doc) == []
    live["obsolete_reason"] = "the input file changed since the question was raised"
    assert validate("question-registry", doc)
    del live["obsolete_reason"]
    obsolete["obsolete_reason"] = ""
    assert validate("question-registry", doc)


def test_grid_system_answer_example_and_detected_guards(example):
    doc = example("grid-system-answer")
    assert validate("grid-system", doc) == []
    answered = next(s for s in doc["systems"] if s.get("source") == "engineer_answer")
    assert answered["evidence"]["contributors"] == []
    assert answered["directions"][0]["representative"] is None
    codes = {q["code"] for q in doc["questions"]}
    assert {"grid_system_missing", "grid_answer_contradicts_drawing"} <= codes

    no_answer = copy.deepcopy(doc)
    del next(s for s in no_answer["systems"] if s.get("source") == "engineer_answer")["source_answer"]
    assert validate("grid-system", no_answer)
    detected_with_answer = copy.deepcopy(doc)
    detected = next(s for s in detected_with_answer["systems"] if s.get("source") != "engineer_answer")
    detected["source_answer"] = answered["source_answer"]
    assert validate("grid-system", detected_with_answer)
    for mutate in (
        lambda s: s["evidence"].update(contributors=[]),
        lambda s: s["evidence"].update(views=0),
        lambda s: s["directions"][0].update(representative=None),
        lambda s: s["directions"][0].update(families=0),
    ):
        bad = copy.deepcopy(doc)
        mutate(next(s for s in bad["systems"] if s.get("source") != "engineer_answer"))
        assert validate("grid-system", bad)
    bad = copy.deepcopy(doc)
    answered_bad = next(s for s in bad["systems"] if s.get("source") == "engineer_answer")
    answered_bad["directions"][0]["provenance"]["method"] = "derived"
    assert validate("grid-system", bad)


def test_grid_system_proposed_simulated_statuses(example):
    doc = example("grid-system")
    system = doc["systems"][0]
    system["units"] = {
        "declared": "mm",
        "answered": "mm",
        "status": "proposed_simulated",
        "reason": "units answered by a non-engineer role",
    }
    system["axis_assignment"] = {"status": "proposed_simulated", "reason": "simulated answer Q-024"}
    doc["conflicts"][0]["proposed_closed_by"] = "separate"
    assert validate("grid-system", doc) == []
    doc["conflicts"][0]["closed_by"] = "proposed_simulated"  # never a closure reason
    assert validate("grid-system", doc)
    doc["conflicts"][0]["closed_by"] = None
    doc["conflicts"][0]["proposed_closed_by"] = "answered"
    assert validate("grid-system", doc)


def test_marks_mark_sets_and_compared_with(example):
    doc = example("marks")
    doc["summary"]["mark_sets"] = [
        {
            "file": "plans/set.dxf",
            "family": "D",
            "members": ["D1", "D2", "D9"],
            "complete": True,
            "source": ["schedule", "plan_marks"],
        },
        {
            "file": "plans/set.dxf",
            "family": "B",
            "members": ["B7"],
            "complete": False,
            "source": ["plan_marks"],
        },
    ]
    file_match = doc["matching"][0]
    file_match["detail_headings"] = 1
    file_match["matched"][0]["compared_with"] = "schedule"
    heading = {"entry_id": "T000070", "sheet": "model#02", "text": "DẦM D2 (SL= 02)"}
    file_match["matched"][2].update(compared_with="detail_heading", schedule=[], detail_headings=[heading])
    file_match["plan_only"][0]["compared_with"] = "none"
    file_match["schedule_only"][0]["compared_with"] = "schedule"
    assert validate("marks", doc) == []

    for path, value in (
        (("summary", "mark_sets", 0, "complete"), "yes"),
        (("summary", "mark_sets", 0, "source"), []),
        (("summary", "mark_sets", 0, "source"), ["guess"]),
        (("summary", "mark_sets", 0, "members"), []),
        (("matching", 0, "plan_only", 0, "compared_with"), "both"),
        (("matching", 0, "matched", 0, "compared_with"), "none"),
        (("matching", 0, "matched", 2, "detail_headings"), []),
    ):
        bad = copy.deepcopy(doc)
        node = bad
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value
        assert validate("marks", bad), path
    bad = copy.deepcopy(doc)
    bad["matching"][0]["matched"][0]["schedule"] = []  # a schedule match keeps its schedule row
    assert validate("marks", bad)


def test_callouts_unparsed_code_rejected_and_unparsed_question(example):
    doc = example("callouts")
    unparsed = next(c for c in doc["candidates"] if c["parsed"] is None)
    parsed = next(c for c in doc["candidates"] if c["parsed"] is not None)
    unparsed["unparsed_code"] = "symbol_glyph_unverified"
    doc["rejected"] = [
        {
            "file": unparsed["file"],
            "sheet": "model#01",
            "entry_id": "T000099",
            "display_text": "KC-03",
            "reason_code": "claimed_by_title_block",
            "reason": "the text is the sheet number of the title block",
        }
    ]
    doc["summary"]["unparsed_by_code"] = {"symbol_glyph_unverified": 1}
    doc["summary"]["rejected"] = 1
    doc["summary"]["rejected_by_reason"] = {"claimed_by_title_block": 1}
    doc["question_counts"]["callout_unparsed"] = 2
    assert validate("callouts", doc) == []

    bad = copy.deepcopy(doc)
    next(c for c in bad["candidates"] if c["id"] == parsed["id"])["unparsed_code"] = "notation_unverified"
    assert validate("callouts", bad)  # a parsed candidate has no unparsed code
    bad = copy.deepcopy(doc)
    next(c for c in bad["candidates"] if c["id"] == unparsed["id"])["unparsed_code"] = "decoded_u_grave"
    assert validate("callouts", bad)
    bad = copy.deepcopy(doc)
    del bad["rejected"][0]["reason"]
    assert validate("callouts", bad)  # nothing is rejected without a reason


def test_sheet_text_region_rows(example):
    doc = example("sheet-region")
    assert validate("sheet-text", doc) == []
    cells = [c for r in doc["rows"] for c in r["cells"]]
    assert any(c["meaning"] == "blocked" for c in cells)
    bad = copy.deepcopy(doc)
    del bad["rows"]
    assert validate("sheet-text", bad)  # a region query always returns its rows
    bad = copy.deepcopy(doc)
    bad["rows"][0]["cells"][0]["entry_ids"] = []
    assert validate("sheet-text", bad)
    bad = copy.deepcopy(doc)
    bad["query"]["region"] = [0, 0, 1]
    assert validate("sheet-text", bad)
    plain = example("sheet-text")
    plain["rows"] = doc["rows"]
    assert validate("sheet-text", plain)  # rows only answer a region query


def test_find_text_blocked_in_scope(example):
    found = example("find-text")
    found["counts"]["blocked_in_scope"] = 3
    del found["counts"]["blocked_entries_not_searchable"]
    assert validate("sheet-text", found) == []
    found["counts"]["blocked_in_scope"] = -1
    assert validate("sheet-text", found)
    del found["counts"]["blocked_in_scope"]  # one of the two blocked counts is always there
    assert validate("sheet-text", found)


def test_reader_questions_schema(example):
    doc = example("reader-questions")
    assert validate("reader-questions", doc) == []
    assert validate("intake", doc) == []  # the reader document stays a questions document
    amended = next(q for q in doc["questions"] if q.get("amendments"))
    assert amended["places"]
    for mutate in (
        lambda q: q["refs"].append(dict(q["refs"][0])),
        lambda q: q["amendments"].append({"at": 9}),
        lambda q: q["amendments"].append({"at": 0, "text": "x"}),
        lambda q: q.update(places=[]),
        lambda q: q.update(count=2),
    ):
        bad = copy.deepcopy(doc)
        mutate(next(q for q in bad["questions"] if q["id"] == amended["id"]))
        assert validate("reader-questions", bad)
    bad = copy.deepcopy(doc)
    bad["kind"] = "inventory"
    assert validate("reader-questions", bad)


def test_status_gate1_closed_may_be_empty(example):
    # W5: status always writes gate1.closed (package C). Required in the schema only once status.py does:
    # making it required here broke tests/test_ask.py (status omits an empty list today).
    doc = example("status")
    doc["gate1"]["closed"] = []
    assert validate("status", doc) == []


def test_wave3_schemas_keep_id_0_1():
    for name in ("reader-questions", "grid-system", "marks", "callouts", "sheet-text", "answers"):
        schema: dict = validator(name).schema  # type: ignore[assignment]
        assert schema["$id"] == f"urn:tekla-harness:schema:{name}:0.1"


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


# --- run journal (ADR-0012) ---------------------------------------------------------------


def test_run_journal_example_valid(example):
    assert validate("run-journal", example("run-journal")) == []


def test_run_journal_inserting_entry_has_no_guid(example):
    journal = example("run-journal")
    journal["invocations"][0]["objects"][0]["state"] = "inserting"
    assert validate("run-journal", journal)
    journal["invocations"][0]["objects"][0]["guid"] = None
    assert validate("run-journal", journal) == []


def test_run_journal_inserted_entry_needs_guid(example):
    journal = example("run-journal")
    journal["invocations"][0]["objects"][1]["guid"] = None
    assert validate("run-journal", journal)


@pytest.mark.parametrize("run_id", ["r1", "-R1", "R 1", "R1\n", "R" * 33, ""])
def test_run_journal_rejects_bad_run_id(example, run_id):
    journal = example("run-journal")
    journal["run_id"] = run_id
    assert validate("run-journal", journal)


def test_run_journal_rejects_uppercase_guid(example):
    journal = example("run-journal")
    journal["invocations"][0]["objects"][0]["guid"] = "3F2504E0-4F89-11D3-9A0C-0305E82C3301"
    assert validate("run-journal", journal)


def test_run_journal_golden_matches_schema_and_python_bytes():
    """The C# writer's output (tests/fixtures/run-journal/golden.json, checked byte for byte in
    xunit) is a valid journal and equals Python's json.dumps of the same content."""
    import json as _json

    from conftest import EXAMPLES, REPO

    golden = (REPO / "tests" / "fixtures" / "run-journal" / "golden.json").read_bytes()
    data = _json.loads(golden)
    assert validate("run-journal", data) == []
    assert data == _json.loads((EXAMPLES / "run-journal.example.json").read_text("utf-8"))
    assert golden == (_json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
