"""`harness part conflicts W` (E6b): two parts that read one mark, one system or one measurement
differently become one Vietnamese question that tags both parts; duplicates are listed, never asked.

The work folder is the one of `_part_fixtures` (parts B1-caps and B1-piles of block B1, the findings F-001
and F-002 and the questions Q-003 to Q-005; Q-001 and Q-002 are intake's, so the first conflict is Q-006).
Rows, findings and manifests are invented; the command runs through `cli.main`, as the engineer runs it.
"""

from __future__ import annotations

import copy
import json
import shutil
import unicodedata
from pathlib import Path
from typing import Any

import pytest

from _part_fixtures import (
    INPUT_PART,
    PART,
    REL,
    build_part_work,
    entry_ids,
    part_manifest,
    put_manifest,
    row,
    write_values,
)
from tekla_harness.ask import ask_question
from tekla_harness.cli import main
from tekla_harness.findings import add_finding, withdraw_finding
from tekla_harness.part_rules import LISTED
from tekla_harness.questions_md_vi import topic_of
from tekla_harness.schemas import validate

CONFLICTS = "part-conflicts-questions.json"
SHEET = "model#01"
G1, G2 = "G-0000000001", "G-0000000002"
EVIDENCE = {
    "source": "geometry/contents-model-01-0123456789ab.json", "sha256": "b" * 64, "command": "contents",
    "query": {
        "sheet": SHEET, "outline_layers": ["S-CAP"], "circle_layers": ["S-PILE"], "max_long": 20000.0,
        "marks": "K-\\d+", "mark_radius": 3000.0, "detail": False, "max": None, "tol": 1.0,
    },
}  # fmt: skip


@pytest.fixture(scope="module")
def base_work(tmp_path_factory) -> Path:
    return build_part_work(tmp_path_factory.mktemp("partconflicts"))


@pytest.fixture
def work(base_work, tmp_path) -> Path:
    target = tmp_path / "work"
    shutil.copytree(base_work, target)
    return target


def conflicts(capsys: Any, work: Path) -> tuple[int, dict[str, Any] | None, str]:
    """Run `harness part conflicts` and return (exit code, the parsed stdout or None when empty, stderr)."""
    code = main(["part", "conflicts", str(work)])
    cap = capsys.readouterr()
    return code, (json.loads(cap.out) if cap.out else None), cap.err


def run_ok(capsys: Any, work: Path) -> dict[str, Any]:
    code, out, err = conflicts(capsys, work)
    assert code == 0, err
    assert out is not None and validate("part-output", out) == []
    return out


def two_parts(caps: list[dict[str, Any]], piles: list[dict[str, Any]], work: Path) -> None:
    write_values(work, caps, PART)
    write_values(work, piles, INPUT_PART)


def both_read(work: Path) -> None:
    """Both parts have a `values.json` (the same K-1 size), so neither is skipped and no value conflicts."""
    two_parts([row(value="1500x2400")], [row(value="1500x2400")], work)


def written(work: Path) -> dict[str, Any]:
    return json.loads((work / CONFLICTS).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def registry_entries(work: Path) -> list[dict[str, Any]]:
    doc = json.loads((work / "question-registry.json").read_text(encoding="utf-8"))
    return [e for e in doc["questions"].values() if e["producer"] == "part-conflicts"]


def add_record(work: Path, kind: str, part: str, value: str, **more: Any) -> str:
    """Record a finding of `kind` for `part` in reader-findings.json (a copy of F-001 with `more` set);
    returns its id."""
    path = work / "reader-findings.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    fid = f"F-{doc['next_id']:03d}"
    finding = copy.deepcopy(next(f for f in doc["findings"] if f["id"] == "F-001"))
    finding.update(id=fid, kind=kind, part=part, value=value, **more)
    doc["findings"].append(finding)
    doc["next_id"] += 1
    assert validate("reader-findings", doc) == []
    path.write_text(json.dumps(doc), encoding="utf-8")
    return fid


def add_measured(
    work: Path,
    part: str,
    value: str,
    kind: str = "measured",
    quantity: str = "count",
    items: tuple[str, ...] = (G1, G2),
) -> str:
    extra = {"questions": ["Q-003"]} if kind == "cross_check" else {"entries": []}
    return add_record(
        work, kind, part, value, fields={"quantity": quantity},
        evidence={**EVIDENCE, "items": [{"id": i} for i in items]}, **extra,
    )  # fmt: skip


def add_system(
    work: Path,
    part: str,
    value: str,
    aspect: str = "frame_type",
    kind: str = "structural_system",
    **more: Any,
) -> str:
    return add_record(
        work,
        kind,
        part,
        value,
        fields={"aspect": aspect} if kind != "note_item" else {"topic": "other"},
        **more,
    )


def add_block_b2(work: Path) -> None:
    """A second block B2 with the member part B2-caps (its `values.json` is the caller's)."""
    manifest = part_manifest(work)
    manifest["blocks"].append({"id": "B2", "grid_system_ids": [], "origin_note": "Block B2: its own grid"})
    manifest["parts"].append(
        {
            "id": "B2-caps", "kind": "member", "block": "B2", "family": "caps", "order": 4,
            "sheets": [{"file": REL, "sheet": "model#02", "role": "plan"}],
        }
    )  # fmt: skip
    put_manifest(work, manifest)


def answer(capsys: Any, work: Path, qid: str) -> None:
    code = main(["answer", str(work), qid, "--text", "It is 1500x2400.", "--by", "eng", "--role", "engineer"])
    capsys.readouterr()
    assert code == 0


def question_of(work: Path, qid: str) -> dict[str, Any]:
    return next(q for q in written(work)["questions"] if q["id"] == qid)


def test_value_conflict_one_question_tagging_both_parts(work, capsys):
    two_parts([row(value="1500x2400")], [row(value="900x900")], work)
    out = run_ok(capsys, work)
    assert out["conflicts"] == 1 and out["duplicates"] == [] and out["obsolete"] == []
    assert out["skipped_parts"] == []
    assert out["questions"] == [
        {"id": "Q-006", "code": "part_value_conflict", "blocking": True, "parts": [PART, INPUT_PART]}
    ]
    q = written(work)["questions"][0]
    assert validate("intake", written(work)) == []
    assert q["id"] == "Q-006" and q["parts"] == [PART, INPUT_PART] and q["file"] == REL
    assert q["message"] == (
        "Hai phần ghi khác nhau kích thước của K-1 (khối B1): B1-caps (R001) '1500x2400'; "
        "B1-piles (R001) '900x900'. Giá trị nào đúng theo bản vẽ?"
    )
    assert [(r["where"], r["found"], r["file"], r["sheet"]) for r in q["refs"]] == [
        (f"B1-caps k-1 size {SHEET}", "1500x2400", REL, SHEET),
        (f"B1-piles k-1 size {SHEET}", "900x900", REL, SHEET),
    ]  # `where` holds what survives a re-read, the row ids are in the message
    assert [(e["id"], e["status"]) for e in registry_entries(work)] == [("Q-006", "open")]


def test_same_value_rows_raise_nothing(work, capsys):
    two_parts(
        [row("R001", value="1500x2400"), row("R002", field="count_plan", value="(SL: 7)")],
        [row("R001", value="1500 \u00d7 2400"), row("R002", field="count_plan", value="7")],
        work,
    )
    out = run_ok(capsys, work)
    assert out["conflicts"] == 0 and out["questions"] == []
    assert written(work)["questions"] == []  # the document is written even with no conflict
    assert registry_entries(work) == []


def test_same_mark_in_another_block_is_no_conflict(work, capsys):
    add_block_b2(work)
    write_values(work, [row(value="1500x2400")], PART)
    write_values(work, [row(value="900x900")], "B2-caps")
    out = run_ok(capsys, work)
    assert out["conflicts"] == 0 and out["skipped_parts"] == [INPUT_PART]
    write_values(work, [row(value="900x900")], INPUT_PART)  # the same block: now a conflict
    out = run_ok(capsys, work)
    assert [q["parts"] for q in out["questions"]] == [[PART, INPUT_PART]]


def test_blocking_follows_listed_field(work, capsys):
    fields = sorted(
        json.loads((Path(__file__).parents[1] / "schemas" / "part-values.schema.json").read_text("utf-8"))[
            "$defs"
        ]["row"]["properties"]["field"]["enum"]
    )
    caps = [row(f"R{n:03d}", mark=f"K-{n}", field=f, value="10") for n, f in enumerate(fields, start=1)]
    piles = [row(f"R{n:03d}", mark=f"K-{n}", field=f, value="20") for n, f in enumerate(fields, start=1)]
    two_parts(caps, piles, work)
    out = run_ok(capsys, work)
    assert out["conflicts"] == len(fields)
    by_field = {}
    for q, wq in zip(out["questions"], written(work)["questions"], strict=True):
        by_field[wq["refs"][0]["where"].split()[2]] = q["blocking"]  # "<part> <mark> <field> <sheet>"
    assert by_field == {f: f in LISTED for f in fields}
    assert not by_field["material"] and not by_field["other"] and by_field["size"]


def test_null_value_rows_ignored(work, capsys):
    two_parts(
        [
            row("R001", value="1500x2400"),
            row("R002", mark="K-2", value="800x800", state="asked", cites={"questions": ["Q-004"]}),
            row("R003", mark="K-3", value="400x400"),
        ],
        [
            row("R001", value=None, state="unread", cites={"questions": ["Q-005"]}),
            row("R002", mark="K-2", value="900x900"),
            row("R003", mark="K-3", value=None, state="absent", cites={}),
        ],
        work,
    )
    out = run_ok(capsys, work)
    assert out["conflicts"] == 1  # only K-2: an `asked` value counts, a null value does not
    q = written(work)["questions"][0]
    assert "K-2" in q["message"] and [r["found"] for r in q["refs"]] == ["800x800", "900x900"]


def test_system_conflict(work, capsys):
    both_read(work)
    a = add_system(work, PART, "pile foundation")
    add_system(work, INPUT_PART, "raft foundation", "foundation_type")  # another aspect: no conflict
    out = run_ok(capsys, work)
    assert out["conflicts"] == 0
    b = add_system(work, INPUT_PART, "raft foundation")
    add_system(work, PART, "grid of caps", kind="note_item")  # a note never conflicts
    add_system(work, INPUT_PART, "other grid", kind="note_item")
    out = run_ok(capsys, work)
    assert [(q["code"], q["blocking"], q["parts"]) for q in out["questions"]] == [
        ("part_system_conflict", False, [PART, INPUT_PART])
    ]
    q = written(work)["questions"][0]
    assert [(r["where"], r["found"], r["sheet"]) for r in q["refs"]] == [
        (f"{PART} {REL} {SHEET} frame_type", "pile foundation", SHEET),
        (f"{INPUT_PART} {REL} {SHEET} frame_type", "raft foundation", SHEET),
    ]
    assert (
        f"{PART} ({a}) 'pile foundation'" in q["message"]
        and f"{INPUT_PART} ({b}) 'raft foundation'" in q["message"]
    )
    write_values(work, [row(cites={"findings": [b]})], INPUT_PART)  # a listed row cites it: blocking
    out = run_ok(capsys, work)
    assert [(q["id"], q["blocking"]) for q in out["questions"]] == [("Q-006", True)]


def test_regression_cross_check_sharing_items_is_no_conflict(work, capsys):
    both_read(work)
    add_measured(work, PART, "4")
    add_measured(work, INPUT_PART, "5", kind="cross_check")  # shares G1 and G2, another value: no conflict
    out = run_ok(capsys, work)
    assert out["conflicts"] == 0 and out["questions"] == []
    b = add_measured(work, INPUT_PART, "5")  # a measured one is
    out = run_ok(capsys, work)
    assert [(q["code"], q["blocking"], q["parts"]) for q in out["questions"]] == [
        ("part_measure_conflict", False, [PART, INPUT_PART])
    ]
    q = written(work)["questions"][0]
    assert [r["where"] for r in q["refs"]] == [f"{PART} {G1} {G2}", f"{INPUT_PART} {G1} {G2}"]
    assert b in q["message"]  # the finding id is in the message, not in the key
    add_measured(work, INPUT_PART, "4")  # the same value as the caps one: that pair raises nothing
    assert run_ok(capsys, work)["conflicts"] == 1


def test_rerun_same_ids_and_keys(work, capsys):
    two_parts([row(value="1500x2400")], [row(value="900x900")], work)
    first = run_ok(capsys, work)
    doc = written(work)
    registry = (work / "question-registry.json").read_text(encoding="utf-8")
    second = run_ok(capsys, work)
    assert second == first
    assert written(work) == doc
    assert (
        json.loads((work / "question-registry.json").read_text("utf-8"))["next_id"]
        == json.loads(registry)["next_id"]
    )
    assert [(e["id"], e["status"]) for e in registry_entries(work)] == [("Q-006", "open")]


def test_duplicate_questions_listed_not_asked(work, capsys):
    both_read(work)
    ask_question(
        work,
        code="reader_size_unclear",
        where="model#01 K-9",
        found="a value",
        text="Giá trị nào?",
        file=REL,
        sheet=SHEET,
        blocking=False,
        part=INPUT_PART,
    )  # fmt: skip  (same code, file and sheet as Q-003 of B1-caps: Q-006)
    ask_question(
        work,
        code="reader_size_unclear",
        where="model#02 P-1",
        found="a value",
        text="Giá trị nào?",
        file=REL,
        sheet="model#02",
        blocking=True,
        part=INPUT_PART,
    )  # fmt: skip  (another sheet: no duplicate)
    ids = entry_ids(work)
    add_finding(
        work,
        kind="note_item",
        file=REL,
        entries=[ids["1500x2400"]],
        value="1500x2400",
        sheet=SHEET,
        fields=["topic=other"],
        part=INPUT_PART,
        note="block: cap size as printed",
    )  # fmt: skip  (cites the entry of F-001)
    out = run_ok(capsys, work)
    assert out["conflicts"] == 0 and out["questions"] == []
    # F-001 is cited by a listed row of B1-caps (the size of K-1), F-003 by none: their flags differ
    assert out["duplicates"] == [
        {
            "kind": "question",
            "ids": ["Q-003", "Q-006"],
            "parts": [PART, INPUT_PART],
            "blocking_differs": True,
        },
        {
            "kind": "finding",
            "ids": ["F-001", "F-003"],
            "parts": [PART, INPUT_PART],
            "blocking_differs": True,
        },
    ]
    assert written(work)["questions"] == [] and registry_entries(work) == []


def test_resolved_conflict_goes_obsolete(work, capsys):
    two_parts([row(value="1500x2400")], [row(value="900x900")], work)
    assert [q["id"] for q in run_ok(capsys, work)["questions"]] == ["Q-006"]
    write_values(work, [row(value="1500x2400")], INPUT_PART)
    out = run_ok(capsys, work)
    assert out["conflicts"] == 0 and out["questions"] == [] and out["obsolete"] == ["Q-006"]
    assert [(e["id"], e["status"]) for e in registry_entries(work)] == [("Q-006", "obsolete")]
    assert written(work)["questions"] == []


def test_outputs_valid_records_same(work, capsys):
    both_read(work)
    write_values(work, [row(value="900x900")], INPUT_PART)
    add_system(work, PART, "pile foundation")
    watched = ("parts/B1-caps/values.json", "parts/B1-piles/values.json", "reader-findings.json",
               "reader-questions.json")  # fmt: skip
    before = {name: (work / name).read_bytes() for name in watched}
    out = run_ok(capsys, work)
    assert {name: (work / name).read_bytes() for name in watched} == before  # never edits what it reads
    doc = written(work)
    assert validate("intake", doc) == []
    assert [(q["id"], q["code"], q["blocking"], q.get("parts")) for q in doc["questions"]] == [
        (q["id"], q["code"], q["blocking"], q["parts"]) for q in out["questions"]
    ]
    assert out["conflicts"] == len(out["questions"]) == doc["summary"]["questions"]
    assert {e["id"] for e in registry_entries(work)} == {q["id"] for q in out["questions"]}


def test_missing_values_skipped_invalid_exit_1_nothing_written(work, capsys):
    write_values(work, [row(value="1500x2400")], PART)
    out = run_ok(capsys, work)  # B1-piles has no values.json
    assert out["skipped_parts"] == [INPUT_PART] and out["conflicts"] == 0
    (work / CONFLICTS).unlink()
    registry = (work / "question-registry.json").read_bytes()
    write_values(work, "{not json", INPUT_PART)
    code, stdout, err = conflicts(capsys, work)
    assert code == 1 and stdout is None and INPUT_PART in err
    assert not (work / CONFLICTS).exists() and (work / "question-registry.json").read_bytes() == registry


def test_topic_of_routes_part_conflicts_before_the_code_prefixes():
    assert topic_of("member_mark_prefix_meaning", "part-conflicts") == "part-conflicts"
    assert topic_of("grid_system_conflict", "part-conflicts") == "part-conflicts"
    assert topic_of("member_mark_prefix_meaning", "callouts") != "part-conflicts"


# --- review 1 (E6-fix-1) ------------------------------------------------------------------------------------

NOUN_VI = {
    "size": "kích thước", "thickness": "chiều dày", "depth": "chiều cao", "length": "chiều dài",
    "spacing": "khoảng cách", "count_plan": "số lượng trên mặt bằng",
    "count_schedule": "số lượng trong bảng thống kê",
    "piles_per_member": "số cọc mỗi cấu kiện", "level": "cao độ", "level_top": "cao độ đỉnh",
    "level_bottom": "cao độ đáy", "material": "vật liệu", "axes": "trục", "start_axes": "trục đầu",
    "end_axes": "trục cuối", "other": "giá trị",
}  # fmt: skip


def test_regression_partial_plan_counts_on_two_sheets_are_no_conflict(work, capsys):
    """P1 / M1: two parts count one mark on the plan sheets they read; the counts add up."""
    two_parts(
        [row(field="count_plan", value="13", sheet="model#01")],
        [row(field="count_plan", value="45", sheet="model#02")],
        work,
    )
    out = run_ok(capsys, work)
    assert out["conflicts"] == 0 and out["questions"] == [] and registry_entries(work) == []
    write_values(work, [row(field="count_plan", value="45", sheet="model#01")], INPUT_PART)  # the same sheet
    out = run_ok(capsys, work)
    assert [(q["code"], q["blocking"], q["parts"]) for q in out["questions"]] == [
        ("part_value_conflict", True, [PART, INPUT_PART])
    ]


def test_plan_count_key_holds_the_file_too(work, capsys):
    """D1: the (file, sheet) of a plan count is the key; one sheet name in two files is two places."""
    two_parts(
        [row(field="count_plan", value="13")],
        [row(field="count_plan", value="45", file="plans/other.dxf")],
        work,
    )
    assert run_ok(capsys, work)["conflicts"] == 0


def test_other_fields_conflict_across_sheets(work, capsys):
    """D1 is for `count_plan` only: a size of one mark on two sheets is still two readings of one thing."""
    two_parts([row(value="1500x2400", sheet="model#01")], [row(value="900x900", sheet="model#02")], work)
    out = run_ok(capsys, work)
    assert out["conflicts"] == 1
    assert [r["where"] for r in written(work)["questions"][0]["refs"]] == [
        f"{PART} k-1 size model#01",
        f"{INPUT_PART} k-1 size model#02",
    ]


def test_row_without_a_sheet_has_a_dash_in_where(work, capsys):
    two_parts(
        [row(value="1500x2400", sheet="<drop>", file="<drop>")],
        [row(value="900x900", sheet="<drop>", file="<drop>")],
        work,
    )
    run_ok(capsys, work)
    assert [r["where"] for r in written(work)["questions"][0]["refs"]] == [
        f"{PART} k-1 size -",
        f"{INPUT_PART} k-1 size -",
    ]


def test_measure_conflict_needs_one_quantity(work, capsys):
    """P2 / M2 (D2): a size and a count that share an item never differ; two counts do."""
    both_read(work)
    size = add_measured(work, PART, "1500x2400", quantity="size", items=(G1,))
    write_values(work, [row(cites={"findings": ["F-001", size]})], PART)  # a listed row cites it
    add_measured(work, INPUT_PART, "14", quantity="count")
    out = run_ok(capsys, work)
    assert out["conflicts"] == 0 and out["questions"] == []
    add_measured(work, INPUT_PART, "9", quantity="size", items=(G1,))  # the same quantity as the first
    out = run_ok(capsys, work)
    assert [(q["code"], q["blocking"]) for q in out["questions"]] == [("part_measure_conflict", True)]


def test_measure_conflict_compares_findings_with_no_quantity(work, capsys):
    """D2: the quantity is optional; two findings that both lack it are compared."""
    both_read(work)
    for part, value in ((PART, "4"), (INPUT_PART, "5")):
        add_record(
            work, "measured", part, value, fields={}, evidence={**EVIDENCE, "items": [{"id": G1}]}, entries=[]
        )
    assert run_ok(capsys, work)["conflicts"] == 1
    add_measured(work, PART, "6", quantity="count", items=(G1,))  # a count against two with none: nothing
    assert run_ok(capsys, work)["conflicts"] == 1


def test_renumbered_row_keeps_the_question_and_its_answer(work, capsys):
    """P3 / M3, rule 1: the same conflict in re-read rows (other row ids) is the same question."""
    two_parts([row("R001", value="1500x2400")], [row("R001", value="900x900")], work)
    assert [q["id"] for q in run_ok(capsys, work)["questions"]] == ["Q-006"]
    answer(capsys, work, "Q-006")
    write_values(work, [row("R007", value="900x900")], INPUT_PART)
    write_values(work, [row("R004", value="1500x2400")], PART)
    out = run_ok(capsys, work)
    assert [q["id"] for q in out["questions"]] == ["Q-006"] and out["obsolete"] == []
    q = question_of(work, "Q-006")
    assert q["answer"] is not None and "R007" in q["message"] and "R004" in q["message"]
    assert [(e["id"], e["status"]) for e in registry_entries(work)] == [("Q-006", "answered")]


def test_renumbered_row_keeps_the_question_case_and_spaces_of_the_mark(work, capsys):
    two_parts([row(mark="K-1", value="1500x2400")], [row(mark="k-1", value="900x900")], work)
    run_ok(capsys, work)
    answer(capsys, work, "Q-006")
    write_values(work, [row("R002", mark="K-1 ", value="900x900")], INPUT_PART)
    out = run_ok(capsys, work)
    assert [q["id"] for q in out["questions"]] == ["Q-006"] and question_of(work, "Q-006")["answer"]


def test_rerecorded_finding_keeps_the_system_question(work, capsys):
    """P3 / M3, rule 2: a finding recorded again under a new F-id is the same question."""
    both_read(work)
    add_system(work, PART, "pile foundation")
    old = add_system(work, INPUT_PART, "raft foundation")
    assert [q["id"] for q in run_ok(capsys, work)["questions"]] == ["Q-006"]
    answer(capsys, work, "Q-006")
    new = add_system(work, INPUT_PART, "raft foundation")
    withdraw_finding(work, old, "recorded again", INPUT_PART)
    out = run_ok(capsys, work)
    assert [q["id"] for q in out["questions"]] == ["Q-006"] and out["obsolete"] == []
    q = question_of(work, "Q-006")
    assert q["answer"] is not None and new in q["message"] and old not in q["message"]


def test_rerecorded_finding_keeps_the_measure_question(work, capsys):
    """P3 / M3, rule 3."""
    both_read(work)
    add_measured(work, PART, "4")
    old = add_measured(work, INPUT_PART, "5")
    assert [q["id"] for q in run_ok(capsys, work)["questions"]] == ["Q-006"]
    answer(capsys, work, "Q-006")
    new = add_measured(work, INPUT_PART, "5")
    withdraw_finding(work, old, "recorded again", INPUT_PART)
    out = run_ok(capsys, work)
    assert [q["id"] for q in out["questions"]] == ["Q-006"] and out["obsolete"] == []
    q = question_of(work, "Q-006")
    assert q["answer"] is not None and new in q["message"] and old not in q["message"]


def test_listing_names_every_row_of_a_part_that_reads_the_value(work, capsys):
    two_parts(
        [row("R001", value="1500x2400"), row("R003", value="1500x2400", sheet="model#02")],
        [row("R002", value="900x900")],
        work,
    )
    run_ok(capsys, work)
    assert (
        "B1-caps (R001, R003) '1500x2400'; B1-piles (R002) '900x900'"
        in written(work)["questions"][0]["message"]
    )


def test_system_conflict_needs_one_block(work, capsys):
    """D5: one notes sheet can give two blocks two foundation types."""
    add_block_b2(work)
    write_values(work, [row(value="1500x2400")], PART)
    write_values(work, [row(value="1500x2400")], INPUT_PART)
    write_values(work, [row(value="1500x2400")], "B2-caps")
    add_system(work, PART, "pile foundation", "foundation_type")
    add_system(work, "B2-caps", "raft foundation", "foundation_type")
    assert run_ok(capsys, work)["conflicts"] == 0
    add_system(work, INPUT_PART, "raft foundation", "foundation_type")  # B1-piles is in block B1 too
    out = run_ok(capsys, work)
    assert [q["parts"] for q in out["questions"]] == [[PART, INPUT_PART]]


def test_system_same_aspect_two_sheets_is_no_conflict(work, capsys):
    both_read(work)
    add_system(work, PART, "pile foundation", sheet="model#01")
    add_system(work, INPUT_PART, "raft foundation", sheet="model#02")
    assert run_ok(capsys, work)["conflicts"] == 0


def test_message_names_the_quantity_in_vietnamese(work, capsys):
    fields = sorted(NOUN_VI)
    caps = [row(f"R{n:03d}", mark=f"K-{n}", field=f, value="10") for n, f in enumerate(fields, start=1)]
    piles = [row(f"R{n:03d}", mark=f"K-{n}", field=f, value="20") for n, f in enumerate(fields, start=1)]
    two_parts(caps, piles, work)
    run_ok(capsys, work)
    messages = {q["refs"][0]["where"].split()[2]: q["message"] for q in written(work)["questions"]}
    assert sorted(messages) == fields
    for n, field in enumerate(fields, start=1):
        assert messages[field].startswith(f"Hai phần ghi khác nhau {NOUN_VI[field]} của K-{n} (khối B1): "), (
            field
        )


def test_subject_key_normalised(work, capsys):
    """m1: a mark or subject that differs only by spaces or Unicode form is the same key."""
    nfc = "cọc khoan nhồi"
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfc != nfd
    two_parts(
        [
            row("R001", mark="K-1", value="1500x2400"),
            row("R002", mark="<drop>", subject=nfc, field="count_plan", value="3"),
        ],
        [
            row("R001", mark="K-1 ", value="900x900"),
            row("R002", mark="<drop>", subject=nfd, field="count_plan", value="4"),
        ],
        work,
    )
    out = run_ok(capsys, work)
    assert out["conflicts"] == 2
    assert {q["refs"][0]["where"].split()[1] for q in written(work)["questions"]} == {"k-1", nfc.split()[0]}


def test_one_part_two_values_raises_nothing(work, capsys):
    two_parts(
        [row("R001", value="1500x2400"), row("R002", value="900x900")],
        [row(mark="K-2", value="400x400")],
        work,
    )
    assert run_ok(capsys, work)["conflicts"] == 0


def test_withdrawn_finding_raises_nothing(work, capsys):
    both_read(work)
    add_system(work, PART, "pile foundation")
    old = add_system(work, INPUT_PART, "raft foundation")
    withdraw_finding(work, old, "wrong note", INPUT_PART)
    assert run_ok(capsys, work)["conflicts"] == 0


def test_non_listed_row_citation_is_not_blocking(work, capsys):
    two_parts([row(value="1500x2400")], [row(value="1500x2400")], work)
    add_system(work, PART, "pile foundation")
    b = add_system(work, INPUT_PART, "raft foundation")
    write_values(work, [row(field="material", value="C30", cites={"findings": [b]})], INPUT_PART)
    out = run_ok(capsys, work)
    assert [(q["code"], q["blocking"]) for q in out["questions"]] == [("part_system_conflict", False)]


def test_hand_sum_citation_is_blocking(work, capsys):
    both_read(work)
    add_measured(work, PART, "4")
    b = add_measured(work, INPUT_PART, "5")
    out = run_ok(capsys, work)
    assert [q["blocking"] for q in out["questions"]] == [False]
    write_values(
        work,
        [row(field="count_plan", value="5", cites={}, hand_sum={"terms": [{"finding": b, "of": "items"}]})],
        INPUT_PART,
    )
    out = run_ok(capsys, work)
    assert [(q["id"], q["blocking"]) for q in out["questions"]] == [("Q-006", True)]


def test_skipped_part_contributes_no_findings(work, capsys):
    both_read(work)
    add_system(work, PART, "pile foundation")
    manifest = part_manifest(work)
    manifest["parts"].append(
        {
            "id": "B1-extra", "kind": "member", "block": "B1", "family": "extra", "order": 4,
            "sheets": [{"file": REL, "sheet": "model#02", "role": "plan"}],
        }
    )  # fmt: skip
    put_manifest(work, manifest)
    add_system(work, "B1-extra", "raft foundation")  # a part with no values.json: not read yet
    out = run_ok(capsys, work)
    assert out["conflicts"] == 0 and out["skipped_parts"] == ["B1-extra"]
