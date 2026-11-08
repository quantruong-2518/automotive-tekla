"""`harness questions-md`: the deterministic renderer of questions.md, over a synthetic work folder.

The world: two synthetic DXF drawings taken through intake, read-structure, callouts and grid-system (the
tests/test_status.py pattern). `harness marks` has no output yet, so the marks step stays missing.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest

from _dxf_fixtures import build_set
from tekla_harness import ask as ask_module
from tekla_harness import questions_md_vi
from tekla_harness.answers import check_values, record_answer
from tekla_harness.ask import ask_question
from tekla_harness.callouts import run_callouts
from tekla_harness.cli import main
from tekla_harness.grid_system import run_grid_systems
from tekla_harness.intake import run_intake
from tekla_harness.questions import QUESTION_DOCUMENTS, SELECT_CODE, empty_answers
from tekla_harness.questions_md import (
    Item,
    answer_command,
    code_span,
    reason_vi,
    render_questions_md,
)
from tekla_harness.status import build_status
from tekla_harness.structure import read_structure

PROJECT = "demo-questions-md"

# Question codes the producers can raise today (intake / read_dxf, sheets, grids, levels, callouts,
# grid_system), kept here so a new code without a Vietnamese row fails this file.
PRODUCER_CODES = (  # noqa: SIM905
    "units_confirm_all units_confirm units_conflict units_suspect units_unknown xref_unresolved "
    "font_encoding_conflict text_encoding_hint font_encoding_proposed unreadable_objects "
    "dimension_override_differs multiple_scales probe_section_failed encoding_unknown_non_ascii "
    "units_answer_contradicts_evidence conversion_empty converter_errors read_failed no_reader_implemented "
    "sheets_not_detected sheet_number_missing revision_missing texts_unassigned texts_ambiguous_sheet "
    "sheet_frames_overlap sheet_frame_ambiguous sheet_frame_candidates_rejected sheet_number_duplicate "
    "sheet_content_duplicate title_field_conflict "
    "grid_label_duplicate grid_axis_layer_mismatch grid_label_kind_mixed grid_label_order_nonmonotonic "
    "grid_label_sequence_gap grid_rotated grid_none_found grid_family_axis_assignment "
    "grid_gate1_confirmation grid_axis_label_conflict grid_axis_not_parallel grid_axis_skewed "
    "grid_two_bubble_axis grid_units_doubt grid_non_orthogonal grid_label_order_mismatch "
    "grid_dimension_override_mismatch grid_label_missing grid_axis_unlabelled grid_scale_differs "
    "grid_spacing_cross_sheet_mismatch grid_spacing_drafting_tolerance "
    "level_storey_selection level_none_found level_finished_vs_structural level_datum_not_found "
    "level_decimals_nonstandard level_name_conflict level_value_out_of_range level_negative_storey "
    "level_single_occurrence "
    "callout_ambiguous grade_legacy_mapping member_mark_prefix_meaning "
    "grid_system_select grid_system_conflict grid_system_units_unconfirmed grid_system_axis_unassigned "
    "file_set_relation"
).split()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def documents(work: Path) -> list[dict[str, Any]]:
    return [
        q for name in QUESTION_DOCUMENTS if (work / name).is_file() for q in load(work / name)["questions"]
    ]


def sections(text: str) -> dict[str, str]:
    """Body of each `## N.` section, by its number."""
    parts = re.split(r"^## (\d+)\. ", text, flags=re.MULTILINE)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


@pytest.fixture(scope="module")
def base_world(tmp_path_factory) -> Path:
    base = tmp_path_factory.mktemp("qmd")
    root = base / "input"
    root.mkdir()
    build_set(root, "set.dxf")
    build_set(root, "other.dxf", sheet2_number="S-777")
    work = base / "work"
    run_intake(root, work, PROJECT)
    read_structure(work, root)
    run_callouts(work, root)
    run_grid_systems(work)
    return base


@pytest.fixture
def world(base_world, tmp_path) -> Path:
    """The work folder of a private copy (questions.md goes next to it, in the copy)."""
    target = tmp_path / "w"
    shutil.copytree(base_world, target)
    return target / "work"


def render(work: Path) -> str:
    rendered = render_questions_md(work)
    return rendered.text


# --- the Vietnamese table --------------------------------------------------------------------------


def test_every_producer_code_has_a_row_with_a_known_topic():
    topics = {slug for slug, _ in questions_md_vi.TOPICS}
    missing = [c for c in PRODUCER_CODES if c not in questions_md_vi.CODES]
    assert missing == []
    assert {t for t, _, _ in questions_md_vi.CODES.values()} <= topics
    assert all(need.strip() and impact.strip() for _, need, impact in questions_md_vi.CODES.values())


def test_codes_other_producers_own_all_have_a_row():
    exact = [code for codes, _ in ask_module.OTHER_OWNERS.values() for code in codes]
    assert [c for c in exact if c not in questions_md_vi.CODES] == []


def test_every_code_raised_in_the_world_has_a_row(world):
    codes = {q["code"] for q in documents(world)}
    assert codes
    assert codes <= set(questions_md_vi.CODES)
    assert render_questions_md(world).summary["untranslated_codes"] == []


def test_table_copy_is_marked_as_proposed():
    assert "PROPOSED engineer-facing copy, pending engineer review" in (questions_md_vi.__doc__ or "")


# --- the document ----------------------------------------------------------------------------------


def test_default_output_next_to_the_work_folder_and_summary(world, capsys):
    assert main(["questions-md", str(world)]) == 0
    summary = json.loads(capsys.readouterr().out)
    out = world.parent / "questions.md"
    assert Path(summary["path"]) == out and out.is_file()
    docs = documents(world)
    assert summary["questions"] == len(docs)
    assert summary["blocking_open"] == sum(1 for q in docs if q["blocking"] and q["answer"] is None)
    assert sum(summary["by_topic"].values()) == len(docs)
    assert summary["untranslated_codes"] == []
    assert list(summary["by_topic"]) == [s for s, _ in questions_md_vi.TOPICS if s in summary["by_topic"]]


def test_out_option_and_atomic_write(world, tmp_path, capsys):
    target = tmp_path / "elsewhere" / "q.md"
    assert main(["questions-md", str(world), "--out", str(target)]) == 0
    capsys.readouterr()
    assert target.is_file() and not (world.parent / "questions.md").exists()
    assert not list(target.parent.glob("*.tmp"))


def test_identical_inputs_give_identical_bytes_in_two_places(base_world, tmp_path):
    texts = []
    for name in ("one", "two-with-a-longer-path"):
        target = tmp_path / name / "w"
        shutil.copytree(base_world, target)
        work = target / "work"
        first = render(work)
        assert render(work) == first  # twice in one place
        assert str(target) not in first and str(tmp_path) not in first and "/tmp/" not in first
        texts.append(first)
    assert texts[0] == texts[1]


def test_blocking_open_come_before_non_blocking_and_answered_last(world):
    text = render(world)
    heads = [m.group(0) for m in re.finditer(r"^## \d\. .*$", text, flags=re.MULTILINE)]
    assert [h.split("(")[0].strip() for h in heads] == [
        "## 1. Tóm tắt",
        "## 2. Câu hỏi chặn đang mở",
        "## 3. Câu hỏi không chặn đang mở",
        "## 4. Đã trả lời",
        "## 5. Câu trả lời đã cũ",
    ]
    body = sections(text)
    blocking = {q["id"] for q in documents(world) if q["blocking"]}
    in2 = set(re.findall(r"^##### (Q-\d+) · .* · CHẶN$", body["2"], flags=re.MULTILINE))
    in3 = set(re.findall(r"^##### (Q-\d+) · .* · không chặn$", body["3"], flags=re.MULTILINE))
    assert in2 == blocking and in3 and not (in3 & blocking)


def test_topics_follow_the_fixed_order_and_files_then_ids(world):
    body = sections(render(world))["2"]
    titles = dict(questions_md_vi.TOPICS)
    seen = [t for t in re.findall(r"^### (.*) \(\d+\)$", body, flags=re.MULTILINE)]
    order = [titles[s] for s, _ in questions_md_vi.TOPICS]
    assert seen == [t for t in order if t in seen] and len(seen) >= 2
    for topic_body in re.split(r"^### ", body, flags=re.MULTILINE)[1:]:
        heads = re.findall(r"^#### (.*)$", topic_body, flags=re.MULTILINE)
        files = [h.rsplit(" — ", 1)[0] for h in heads]
        key = [(f != "(cả dự án)", f) for f in files]
        assert key == sorted(key)
        for head in heads:
            ids = head.rsplit(" — ", 1)[1].split(", ")
            assert ids == sorted(ids, key=lambda i: int(i[2:]))


def test_one_heading_per_file_lists_every_id_of_that_file_in_the_topic(world):
    body = sections(render(world))["2"]
    file_heads = re.findall(r"^#### (.*) — (Q-.*)$", body, flags=re.MULTILINE)
    for topic_body in re.split(r"^### ", body, flags=re.MULTILINE)[1:]:
        heads = re.findall(r"^#### (.*) — (Q-.*)$", topic_body, flags=re.MULTILINE)
        assert len({f for f, _ in heads}) == len(heads)  # one heading per file
        ids_under = re.findall(r"^##### (Q-\d+) ", topic_body, flags=re.MULTILINE)
        assert sorted(i for _, ids in heads for i in ids.split(", ")) == sorted(ids_under)
    assert file_heads


def test_project_level_question_shows_whole_project(world):
    text = render(world)
    select = next(q for q in documents(world) if q["code"] == SELECT_CODE)
    assert select["file"] is None
    block = re.search(rf"^##### {select['id']} .*?(?=^#####? |\Z)", text, flags=re.MULTILINE | re.DOTALL)
    assert block and "- **File:** (cả dự án)" in block.group(0)
    assert re.search(rf"^#### \(cả dự án\) — .*{select['id']}", text, flags=re.MULTILINE)


def test_found_where_and_counts_are_verbatim(world):
    text = render(world)
    for q in documents(world):
        assert f"##### {q['id']} · {code_span(q['code'])}" in text
        assert f"key {code_span(q['key'])}" in text
        for ref in q["refs"]:
            assert f"{code_span(ref['where'])} — {code_span(ref['found'])}" in text
        assert f"**Số chỗ:** {q['count']}" in text


def test_truncated_question_shows_how_many_of_the_total(world):
    path = world / "structure-questions.json"
    doc = load(path)
    victim = next(q for q in doc["questions"] if q["refs"])
    victim["count"], victim["truncated"] = len(victim["refs"]) + 12, True
    path.write_text(json.dumps(doc), encoding="utf-8")
    text = render(world)
    assert f"hiển thị {len(victim['refs'])}/{victim['count']}" in text


def test_code_span_survives_backticks_and_blank_text():
    assert code_span("a `b` c") == "`` a `b` c ``"
    assert code_span("plain") == "`plain`"
    assert code_span("") == "(trống)"
    assert code_span("two\nlines") == "`two lines`"


# --- answers ----------------------------------------------------------------------------------------


def test_answered_question_moves_to_the_answered_section(world):
    docs = documents(world)
    victim = next(q for q in docs if q["code"] == "units_confirm_all")
    before = sections(render(world))
    assert f"##### {victim['id']} " in before["2"]
    record_answer(
        world,
        victim["id"],
        "Đơn vị là mm, theo kích thước 5000 trên tờ 1",
        "Kỹ sư A",
        {"unit": "mm"},
        role="engineer",
    )
    after = sections(render(world))
    assert f"##### {victim['id']} " not in after["2"] + after["3"]
    line = next(ln for ln in after["4"].splitlines() if ln.startswith(f"- {victim['id']} "))
    assert code_span("Đơn vị là mm, theo kích thước 5000 trên tờ 1") in line
    assert "Kỹ sư A" in line and "unit=mm" in line


def test_multi_line_answer_is_kept_verbatim_in_a_block(world):
    victim = next(q for q in documents(world) if q["code"] == "units_confirm_all")
    text = "dòng một\ndòng hai"
    record_answer(world, victim["id"], text, "A", {"unit": "mm"}, role="engineer")
    body = sections(render(world))["4"]
    assert "  dòng một\n  dòng hai\n" in body


def test_stale_answers_are_listed_with_their_reason(world):
    victim = next(q for q in documents(world) if q["code"] == "units_confirm_all")
    record_answer(world, victim["id"], "mm", "A", {"unit": "mm"}, role="engineer")
    answers = load(world / "answers.json")
    answers["answers"][0]["status"] = "stale"
    answers["answers"][0]["stale_reason"] = "the input file was changed since the answer was given"
    (world / "answers.json").write_text(json.dumps(answers), encoding="utf-8")
    body = sections(render(world))
    assert "(1)" in re.search(r"^## 5\. .*$", render(world), flags=re.MULTILINE).group(0)  # type: ignore[union-attr]
    assert victim["id"] in body["5"] and "bị đổi" in body["5"] and "`mm`" in body["5"]
    assert f"##### {victim['id']} " in body["2"]  # asked again


def test_answer_templates_name_the_values_answers_py_requires(world):
    rendered = render(world)
    docs = documents(world)
    questions = {q["id"]: q for q in docs}
    assert rendered
    checked_codes = set()
    for q in docs:
        item = Item(
            id=q["id"], key=q["key"], code=q["code"], blocking=q["blocking"], file=q["file"],
            message=q["message"], count=q["count"], truncated=q["truncated"], refs=q["refs"],
            subjects=q.get("subjects"), source="x", producer="intake", topic="x", answer=None,
        )  # fmt: skip
        command = answer_command(item)
        assert command.startswith(f'uv run harness answer <work_dir> {q["id"]} --text "..." --by "..."')
        values = {}
        axes = iter("XYXY")  # distinct axes: a system's directions cannot take the same one
        for token in re.findall(r"(?<!\[)--value (\S+)", command):
            key, _, value = token.partition("=")
            files = ",".join(r["file"] for r in q["refs"])  # file_set_relation: every file of the question
            sample = {
                "<mm|cm|m|in|ft>": "mm",
                "<X|Y>": next(axes),
                "<meaning>": "column",
                "<file>,<file>": files,
            }
            sample = sample.get(value, value)
            values[key] = sample
        assert check_values(q["code"], values) == [], (command, questions[q["id"]]["code"])
        checked_codes.add(q["code"])
    assert {
        "units_confirm_all",
        "grid_family_axis_assignment",
        SELECT_CODE,
        "file_set_relation",
    } <= checked_codes


def test_member_mark_prefix_template_names_every_subject():
    item = Item(
        id="Q-009", key="k" * 16, code="member_mark_prefix_meaning", blocking=True, file="a.dxf",
        message="m", count=2, truncated=False, refs=[],
        subjects=[{"name": "C", "count": 1}, {"name": "B", "count": 1}],
        source="callouts-questions.json", producer="callouts", topic="marks", answer=None,
    )  # fmt: skip
    assert answer_command(item).endswith("--value C=<meaning> --value B=<meaning>")


# --- proposals -------------------------------------------------------------------------------------


def test_grid_questions_show_the_systems_and_svg_path(world):
    text = render(world)
    systems = load(world / "grid-systems.json")["systems"]
    select = next(q for q in documents(world) if q["code"] == SELECT_CODE)
    block = re.search(rf"^##### {select['id']} .*?(?=^#####? |\Z)", text, flags=re.MULTILINE | re.DOTALL)
    assert block
    proposal = block.group(0)
    assert "ĐỀ XUẤT — chưa xác nhận" in proposal
    for system in systems:
        for direction in system["directions"]:
            assert code_span(direction["coordinates"]) in proposal
        assert code_span(f"work/{system['svg']}") in proposal


def test_units_questions_show_drawing_unit_spacings_without_the_header_unit(world):
    summary = load(world / "structure-summary.json")
    first = summary["files"][0]
    assert first["grids"]["families"]
    text = render(world)
    heading = re.search(
        rf"^#### {re.escape(code_span(first['path']))} — .*?(?=^### |\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    units_topic = sections(text)["2"].split("### Đơn vị bản vẽ", 1)[1].split("\n### ", 1)[0]
    assert heading and "ĐỀ XUẤT — chưa xác nhận" in units_topic
    block = next(b for b in units_topic.split("#### ")[1:] if b.startswith(code_span(first["path"]))).split(
        "#####", 1
    )[0]
    for fam in first["grids"]["families"]:
        if fam["coordinates"] is None:  # a single-axis family has no spacings: nothing is proposed
            assert "`None`" not in block
            continue
        assert code_span(fam["coordinates"]) in block
    assert not re.search(r"\b(mm|cm|ft)\b", block)  # the header unit label is deliberately not printed


# --- the status summary -----------------------------------------------------------------------------


def test_summary_states_gate_one_and_reasons_in_vietnamese(world):
    body = sections(render(world))["1"]
    assert "CHƯA SẴN SÀNG" in body
    assert "chặn chưa trả lời" in body or "đơn vị:" in body
    assert "(không thấy marks.json, marks-questions.json)" in body or "marks" in body
    assert "| Bước | Lệnh |" in body
    assert str(world.parent) not in body
    # the gate reasons' answer commands carry the work folder as the placeholder, in argparse order
    assert re.search(r"harness answer <work_dir> Q-\d+ --text", body)


def test_known_reason_shapes_are_translated_and_unknown_stay_verbatim():
    assert "và 6 câu nữa" in reason_vi(
        "read-structure: 16 blocking question(s) open (Q-001, Q-002 and 6 more)"
    )
    assert "kết quả đang cũ" in reason_vi(
        "grid-system: outputs stale (grid-systems.json was built from another inventory.json "
        "(intake reran since)); rerun harness grid-system <work_dir>"
    )
    assert reason_vi("levels: Q-018 level_storey_selection (a b.dxf) is not answered") == (
        "cao độ: Q-018 `level_storey_selection` (`a b.dxf`) chưa được trả lời"
    )
    # units / grid-system sentences move with the gate rules: a Vietnamese category, the sentence verbatim
    sentence = 'set.dxf is not confirmed: harness answer Q-001 --text "..." --by "..."'
    assert reason_vi("units: " + sentence) == "đơn vị: " + code_span(sentence)
    assert reason_vi("grid systems: S001 and S002 conflict (Q-024)").startswith("hệ lưới: `S001 and S002")
    assert reason_vi("something new") == "`something new` (chưa có bản dịch)"


def test_live_question_missing_from_every_document_is_flagged(world):
    (world / "grid-system-questions.json").unlink()
    body = sections(render(world))["1"]
    assert "không có trong file câu hỏi nào" in body


# --- codes without a row ----------------------------------------------------------------------------


def test_reader_questions_print_as_written_and_unknown_codes_are_listed(world):
    inventory = load(world / "inventory.json")["files"][0]["path"]
    ask_question(
        world, code="reader_custom_gap", where="sheet 3, top left", found="the arrow points nowhere",
        text="Mũi tên ở tờ 3 chỉ vào cấu kiện nào?", file=inventory, blocking=True,
    )  # fmt: skip
    path = world / "structure-questions.json"
    doc = load(path)
    doc["questions"][0]["code"] = "mark_sequence_hole"  # a code a producer might raise tomorrow
    path.write_text(json.dumps(doc), encoding="utf-8")
    rendered = render_questions_md(world)
    # a reader question is the reader's own (Vietnamese) text: printed as written, never "untranslated"
    assert rendered.summary["untranslated_codes"] == ["mark_sequence_hole"]
    assert code_span("Mũi tên ở tờ 3 chỉ vào cấu kiện nào?") in rendered.text
    assert code_span(doc["questions"][0]["message"]) in rendered.text
    assert rendered.text.count("(chưa có bản dịch)") == 2  # need + impact of the unknown producer code
    assert rendered.summary["by_topic"]["reader"] == 1 and rendered.summary["by_topic"]["marks"] == 1


# --- exit codes --------------------------------------------------------------------------------------


def test_exit_codes(world, tmp_path, capsys):
    assert main(["questions-md", str(world)]) == 0
    capsys.readouterr()
    # 2: not a work folder
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main(["questions-md", str(empty)]) == 2
    assert main(["questions-md", str(tmp_path / "nope")]) == 2
    assert main(["questions-md", str(world), "--out", str(world)]) == 2
    err = capsys.readouterr().err
    assert "not a work folder" in err and "is a folder" in err
    # 1: an invalid question document (the stand-in the status tests write is not a questions document)
    (world / "marks-questions.json").write_text("{}", encoding="utf-8")
    assert main(["questions-md", str(world)]) == 1
    assert "marks-questions.json" in capsys.readouterr().err


def test_question_unknown_to_the_registry_is_exit_1(world, capsys):
    path = world / "structure-questions.json"
    doc = load(path)
    doc["questions"][0]["key"] = "0" * 16
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert main(["questions-md", str(world)]) == 1
    assert "not in question-registry.json" in capsys.readouterr().err


def test_obsolete_questions_are_not_rendered(world):
    registry = load(world / "question-registry.json")
    key, entry = next((k, e) for k, e in registry["questions"].items() if e["code"] == "units_confirm_all")
    entry["status"] = "obsolete"
    (world / "question-registry.json").write_text(json.dumps(registry), encoding="utf-8")
    assert f"##### {entry['id']} " not in render(world)
    assert key  # silence the unused name


# --- agreement with `harness status` ---------------------------------------------------------------


def test_blocking_open_agrees_with_the_status_step_table(world):
    rendered = render_questions_md(world)
    status = build_status(world)
    assert rendered.summary["blocking_open"] == sum(
        p["questions"]["blocking_open"] for p in status["producers"]
    )
    row_counts = re.findall(r"^\| [^|]+ \| `[^|]+` \| (\d+) \| (\d+) \| (\d+) \|", rendered.text, re.M)
    assert [int(r[1]) for r in row_counts] == [p["questions"]["blocking_open"] for p in status["producers"]]


def test_a_legacy_answer_to_a_conflict_question_leaves_it_open(world):
    conflict = next(q for q in documents(world) if q["code"] == "grid_system_conflict")
    answers = empty_answers(PROJECT)
    answers["answers"].append(
        {
            "key": conflict["key"],
            "question_id": conflict["id"],
            "code": conflict["code"],
            "file": conflict["file"],
            "answer_text": "hai toà nhà khác nhau",
            "values": {},
            "answered_by": "A",
            "answered_by_role": "engineer",
            "answered_on": "2026-11-07",
            "status": "active",
        }
    )
    (world / "answers.json").write_text(json.dumps(answers), encoding="utf-8")
    rendered = render_questions_md(world)
    body = sections(rendered.text)
    assert f"##### {conflict['id']} " in body["2"] and conflict["id"] not in body["4"]
    assert "không đóng được câu này; câu trả lời cũ" in body["2"]
    assert code_span("hai toà nhà khác nhau") in body["2"]
    assert rendered.summary["blocking_open"] == sum(
        p["questions"]["blocking_open"] for p in build_status(world)["producers"]
    )


def test_contradiction_template_offers_only_the_unit_already_answered():
    item = Item(
        id="Q-050", key="c" * 16, code="units_answer_contradicts_evidence", blocking=True, file="a.dxf",
        message="m", count=1, truncated=False, refs=[], subjects=None,
        source="grid-system-questions.json", producer="grid-system", topic="units", answer=None,
    )  # fmt: skip
    command = answer_command(item, "cm")
    assert command.endswith("--value unit=cm") and check_values(item.code, {"unit": "cm"}) == []
    assert "<mm|cm|m|in|ft>" in answer_command(item)  # no unit answered yet: the generic form


# --- tool wave 2 seam: file sets, closures, supplements ----------------------------------------------


def test_file_set_template_names_the_sets_answers_py_requires():
    item = Item(
        id="Q-060", key="f" * 16, code="file_set_relation", blocking=True, file=None,
        message="m", count=2, truncated=False,
        refs=[{"file": f, "where": f, "found": "x"} for f in ("a.dxf", "b.dxf")],
        subjects=None, source="questions.json", producer="intake", topic="convert", answer=None,
    )  # fmt: skip
    command = answer_command(item)
    assert command.endswith("--value set1=<file>,<file> [--value set2=<file>,...]")
    assert check_values("file_set_relation", {"set1": "a.dxf,b.dxf"}) == []
    assert questions_md_vi.topic_of("file_set_relation", "intake") == "convert"


def first_blocking_open(world: Path) -> dict[str, Any]:
    return next(q for q in documents(world) if q["blocking"] and q["answer"] is None)


def test_a_closed_question_leaves_the_open_sections(world, monkeypatch):
    from tekla_harness import lifecycle
    from tekla_harness.questions import Closure

    target = first_blocking_open(world)
    before = render_questions_md(world)
    monkeypatch.setattr(
        lifecycle, "closures", lambda work, ledger: {target["key"]: Closure("Q-001", "units_answered")}
    )
    rendered = render_questions_md(world)
    body = sections(rendered.text)
    assert f"##### {target['id']} " not in body["2"] and f"##### {target['id']} " not in body["3"]
    (line,) = [ln for ln in body["4"].splitlines() if ln.startswith(f"- {target['id']} ")]
    assert "đã đóng" in line and "Q-001" in line and code_span("units_answered") in line
    assert rendered.summary["blocking_open"] == before.summary["blocking_open"] - 1
    assert rendered.summary["blocking_open"] == sum(
        p["questions"]["blocking_open"] for p in build_status(world)["producers"]
    )


def test_reader_supplements_show_under_their_question(world, monkeypatch):
    from tekla_harness import supplements

    target = first_blocking_open(world)
    rows = [
        {
            "key": "1" * 16, "target_key": target["key"], "target_id": target["id"],
            "target_code": target["code"], "target_producer": "intake", "file": None,
            "file_sha256": None, "sheet": "model#01", "where": "góc phải", "found": "+3.850",
            "text": "Ghi chú `đơn vị` là mm.", "status": "active",
        },
        {
            "key": "2" * 16, "target_key": target["key"], "target_id": target["id"],
            "target_code": target["code"], "target_producer": "intake", "file": None,
            "file_sha256": None, "sheet": None, "where": "rút lại", "found": "",
            "text": "không dùng", "status": "withdrawn", "withdrawn_reason": "sai",
        },
    ]  # fmt: skip
    monkeypatch.setattr(supplements, "load_supplements", lambda work: rows)
    body = sections(render(world))["2"]
    block = re.split(r"\n#{2,5} ", body[body.index(f"##### {target['id']} ") :], maxsplit=1)[0]
    assert "- **Bổ sung của người đọc:**" in block
    assert code_span("Ghi chú `đơn vị` là mm.") in block and code_span("góc phải") in block
    assert "tờ `model#01`" in block
    assert code_span("rút lại") not in block


# --- answer provenance (P3): the printed command names the engineer role -------------------------------


def test_every_printed_answer_command_names_the_engineer_role_once_after_by(world):
    commands = re.findall(r"- \*\*Lệnh trả lời:\*\* `([^`]+)`", render(world))
    assert commands
    for c in commands:
        assert c.count("--role") == 1, c
        assert '--by "..." --role engineer' in c, c
