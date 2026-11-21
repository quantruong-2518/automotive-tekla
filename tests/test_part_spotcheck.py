"""`harness part spotcheck` (E9a, C11): a seeded, stratified sample of a locked part's `seen` rows, as a form
for the engineer (`P/spotcheck/X.md`) and a JSON for `answer-key` and `part score`
(`W/parts/X/spotcheck.json`).

The work folder is the real intake of `_part_fixtures.build_part_work`. Each test copies it, writes the rows
it needs, locks B1-piles and B1-caps with receipts on their current hashes and runs the real command.
"""

from __future__ import annotations

import importlib
import json
import shlex
import shutil
from pathlib import Path
from typing import Any

import pytest

from _part_fixtures import INPUT_PART, MANIFEST, PART, REL, build_part_work, entry_ids, row, write_values
from conftest import EXAMPLES
from tekla_harness import worklock
from tekla_harness.cli import LOCKED_ACTIONS, main
from tekla_harness.schemas import validate
from test_part_receipts import edit_json, h, lock, rec, write_receipts
from test_part_sums import add_measured

FORM_LINE = "Kết luận: [ ] Đúng [ ] Sai — giá trị đúng: ___ [ ] Không xem được"
# row id -> priority: F-003 is a measured finding of medium confidence, F-004 one of low confidence
PRIORITY = {"R003": 0, "R002": 1, "R005": 1}


def sample_module() -> Any:
    return importlib.import_module("tekla_harness.part_sample")


@pytest.fixture(scope="module")
def base_work(tmp_path_factory) -> Path:
    return build_part_work(tmp_path_factory.mktemp("partspot"))


@pytest.fixture
def work(base_work, tmp_path) -> Path:
    target = tmp_path / "work"
    shutil.copytree(base_work, target)
    return target


def run(capsys, work: Path, *more: str, seed: int = 7) -> tuple[int, dict[str, Any] | None, str]:
    code = main(["part", "spotcheck", str(work), "--part", PART, "--seed", str(seed), *more])
    cap = capsys.readouterr()
    return code, (json.loads(cap.out) if cap.out else None), cap.err


def spot_rows() -> list[dict[str, Any]]:
    """Twelve `seen` rows of four LISTED fields, each under a key of its own (mark K-<n>). R002 and R005 cite
    F-004 (measured, low), R003 cites F-003 (measured, medium); the others cite the text finding F-001."""
    fields = ["size"] * 4 + ["thickness"] * 3 + ["depth"] * 2 + ["level"] * 3
    cited = {"R002": "F-004", "R003": "F-003", "R005": "F-004"}
    return [
        row(
            f"R{n:03d}",
            mark=f"K-{n}",
            field=field,
            value=f"{1000 + n}",
            cites={"findings": [cited.get(f"R{n:03d}", "F-001")]},
        )
        for n, field in enumerate(fields, start=1)
    ]


def add_findings(work: Path) -> None:
    items = [{"id": "G-0000000001", "symbols": 4}]
    assert add_measured(work, items) == "F-003"
    assert add_measured(work, items) == "F-004"

    def confidence(doc: Any) -> None:
        by_id = {f["id"]: f for f in doc["findings"]}
        by_id["F-003"]["confidence"], by_id["F-004"]["confidence"] = "medium", "low"

    edit_json(work, "reader-findings.json", confidence)


def lock_part(work: Path, rows: list[dict[str, Any]] | None = None) -> None:
    """B1-caps holds `rows` (default `spot_rows`) and the findings; B1-piles and B1-caps are locked."""
    add_findings(work)
    write_values(work, spot_rows() if rows is None else rows)
    lock(work, INPUT_PART)
    lock(work, PART)


def spot(work: Path) -> dict[str, Any]:
    return json.loads((work / "parts" / PART / "spotcheck.json").read_text(encoding="utf-8"))


def form(work: Path) -> str:
    return (work.parent / "spotcheck" / f"{PART}.md").read_text(encoding="utf-8")


def snapshot(work: Path) -> dict[Path, tuple[bytes, int]]:
    files = [work / "parts" / PART / "spotcheck.json", work.parent / "spotcheck" / f"{PART}.md"]
    return {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files}


def test_refused_unless_locked(capsys, work):
    add_findings(work)
    write_values(work, spot_rows())
    current = h(work)
    states = {
        "reading": [],
        "checked": [rec("checked", current)],
        "reviewed": [rec("checked", current), rec("reviewed", current)],
    }
    for status, receipts in states.items():
        if receipts:
            write_receipts(work, PART, receipts)
        code, doc, err = run(capsys, work)
        assert (code, doc) == (1, None), status
        assert "locked" in err and status in err
        assert not (work / "parts" / PART / "spotcheck.json").exists()
        assert not (work.parent / "spotcheck").exists()
    lock(work, INPUT_PART)
    lock(work, PART)
    assert run(capsys, work)[0] == 0


def test_sample_stratified_and_deterministic(capsys, work):
    lock_part(work)
    stratified = sample_module().stratified
    pool = spot_rows()
    seen: set[tuple[str, ...]] = set()
    differs_from_review = False
    for seed in range(10):
        code, doc, err = run(capsys, work, seed=seed)
        assert (code, err) == (0, "") and doc
        expected = stratified(pool, 5, seed, f"{PART}:spot", lambda r: PRIORITY.get(r["row"], 2))
        assert doc["rows"] == [r["row"] for r in expected] and len(doc["rows"]) == 5
        assert doc["rows"] == sorted(doc["rows"])
        assert {r["field"] for r in spot(work)["rows"]} >= {"size", "thickness", "depth", "level"}
        again = run(capsys, work, seed=seed)[1]
        assert again == doc  # the same seed gives the same rows
        seen.add(tuple(doc["rows"]))
        review = stratified(pool, 5, seed, f"{PART}:review", lambda r: PRIORITY.get(r["row"], 2))
        differs_from_review |= [r["row"] for r in review] != doc["rows"]
    assert len(seen) > 1  # the seed moves the sample
    assert differs_from_review  # the salt is `spot`, not the review's
    assert len(run(capsys, work, "--n", "7")[1]["rows"]) == 7  # type: ignore[index]


def test_medium_measured_first(capsys, work):
    lock_part(work)
    for seed in range(10):
        code, doc, _ = run(capsys, work, seed=seed)
        assert code == 0 and doc
        # R003 (size, measured, medium) beats R002 (size, measured, low) and the text rows; R005 (thickness,
        # measured, low) beats the text rows of its field
        assert "R003" in doc["rows"] and "R005" in doc["rows"], seed


def test_small_part_all_seen_rows(capsys, work):
    rows = [
        row("R001"),
        row("R002", field="thickness", value="hs=800"),
        row("R003", field="depth", value="D400"),
        row("R004", field="level", value=None, state="asked", cites={"questions": ["Q-003"]}),
        row("R005", field="length", value=None, state="absent", file="<drop>", sheet="<drop>", cites={}),
        row("R006", mark="K-6", field="size", value="900x900"),
    ]
    lock_part(work, rows)
    code, doc, err = run(capsys, work, "--n", "2")
    assert (code, err) == (0, "") and doc
    assert doc["rows"] == ["R001", "R002", "R003", "R006"]  # every `seen` row, none asked or absent
    assert [r["row"] for r in spot(work)["rows"]] == doc["rows"]


def test_json_validates_and_carries_hash(capsys, work):
    ids = entry_ids(work)
    lock_part(work)
    rows = spot_rows()
    rows[2]["cites"]["entries"] = [ids["1500x2400"]]
    rows[2]["view"] = {"heading_entry": ids["K-1"]}
    write_values(work, rows)
    lock(work, PART)
    assert run(capsys, work)[0] == 0
    doc = spot(work)
    assert (
        validate("answer-key", doc) == []
        and validate(
            "answer-key", json.loads((EXAMPLES / "answer-key.example.json").read_text(encoding="utf-8"))
        )
        == []
    )
    assert doc["kind"] == "spotcheck" and doc["part"] == PART and doc["seed"] == 7 and doc["n"] == 5
    assert doc["schema_version"] == "0.1"
    assert doc["part_hash"] == h(work)  # `answer-key` accepts rows of this hash only
    assert [r["row"] for r in doc["rows"]] == run(capsys, work)[1]["rows"]  # type: ignore[index]
    by_id = {r["row"]: r for r in doc["rows"]}
    assert by_id["R003"] == {
        "row": "R003", "mark": "K-3", "field": "size", "value": "1003", "file": REL, "sheet": "model#01",
        "sheet_number": None, "sheet_title": None, "view": "K-1", "entries": [ids["1500x2400"]],
        "findings": ["F-003"],
    }  # fmt: skip
    assert run(capsys, work, "--n", "3")[0] == 0 and spot(work)["n"] == 3


def numbered_manifest(work: Path) -> dict[str, str]:
    """The manifest lists sheet number K-2 and title D400 for the part's first sheet."""
    ids = entry_ids(work)

    def numbered(manifest: Any) -> None:
        part = next(p for p in manifest["parts"] if p["id"] == PART)
        part["sheets"][0].update(number_entry=ids["K-2"], title_entry=ids["D400"])

    edit_json(work, str(MANIFEST), numbered)
    return ids


def test_md_lists_value_sheet_quote_command(capsys, work):
    ids = numbered_manifest(work)
    cites = {"findings": ["F-001"], "entries": [ids["1500x2400"]]}
    lock_part(work, [row(f"R{n:03d}", cites=cites, view={"heading_entry": ids["K-1"]}) for n in range(1, 4)])
    code, doc, _ = run(capsys, work, "--n", "2")
    assert code == 0 and doc and doc["rows"] == ["R001", "R002", "R003"]
    text = form(work)
    assert text.count(FORM_LINE) == 3
    # D3: the field noun of `part_conflicts`, one table for both commands
    assert "### 1. K-1 — kích thước\n" in text and "### 3. K-1 — kích thước\n" in text
    assert "Giá trị: 1500x2400" in text
    assert "Tờ: K-2, D400, K-1" in text  # sheet number, title, view
    assert f"Tệp: {REL}, tờ model#01" in text  # M2: the file and the sheet id are always named
    assert "Chữ trên bản vẽ: '1500x2400'" in text
    # M1: the command quotes the path like the code does, so the expectation holds on every platform
    command = (
        f"harness part answer-key {shlex.quote(str(work.resolve()))} --part {PART} --row R002 "
        '--verdict ok|wrong|cannot_tell [--correct "<giá trị đúng>"] --by "<tên kỹ sư>"'
    )
    assert command in text


def test_md_command_quotes_a_path_that_needs_it(capsys, base_work, tmp_path):
    odd = tmp_path / "my work's folder" / "work"  # a space and a quote: shlex.quote must wrap it
    shutil.copytree(base_work, odd)
    lock_part(odd)
    assert run(capsys, odd)[0] == 0
    quoted = shlex.quote(str(odd.resolve()))
    assert quoted.startswith("'") and quoted != str(odd.resolve())
    assert f"harness part answer-key {quoted} --part {PART} --row " in form(odd)


def test_md_names_file_and_sheet_without_manifest_entries(capsys, work):
    rows = [
        row("R001"),
        row("R002", mark="K-2", sheet="<drop>"),
        row("R003", mark="K-3", field="depth", value="D400", sheet="model#02"),
    ]
    lock_part(work, rows)
    code, doc, _ = run(capsys, work, "--n", "3")
    assert code == 0 and doc and doc["rows"] == ["R001", "R002", "R003"]
    text = form(work)
    assert text.count("Tờ: chưa rõ số hiệu, tiêu đề và hình") == 3  # the manifest gives none of the three
    assert f"Tệp: {REL}, tờ model#01\n" in text and f"Tệp: {REL}, tờ model#02\n" in text
    assert f"Tệp: {REL}, ngoài khung tờ\n" in text  # a row on no sheet


def test_md_shows_no_harness_internals(capsys, work):
    ids = entry_ids(work)
    index_path = work / "text" / f"{REL}.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    for e in index["entries"]:
        if e["display_text"] == "D400":
            e["printed"], e["not_printed_reasons"] = False, ["layer_off"]
    index_path.write_text(json.dumps(index), encoding="utf-8")
    rows = [row("R001", cites={"findings": ["F-001"], "entries": [ids["D400"]]})]
    lock_part(work, rows)
    assert run(capsys, work)[0] == 0
    text = form(work)
    assert "(chữ bị chặn hoặc không in)" in text and ids["D400"] not in text  # m9: no entry id
    assert spot(work)["part_hash"][:12] not in text and "seed" not in text  # m9: no hash, seed or n
    assert "mã băm" not in text


def test_ambiguous_keys_are_left_out_of_the_pool(capsys, work):
    rows = [
        row("R001", value="1500x2400"),
        row("R002", value="1500x2500"),  # same key as R001, another value: both are ambiguous
        row("R003", mark="K-2", value="900x900"),
        row("R004", mark="K-3", value="700x700"),
        row("R005", mark="K-3", value="700 x 700"),  # same key, the same value: fine
        row("R006", mark="K-4", field="depth", value="D400"),
        row("R007", mark="K-1", field="size", value=None, state="asked", cites={"questions": ["Q-003"]}),
    ]
    lock_part(work, rows)
    code, doc, err = run(capsys, work, "--n", "20")
    assert code == 0 and doc
    assert doc["rows"] == ["R003", "R004", "R005", "R006"]  # D1: neither R001 nor R002 is offered
    assert err.strip().splitlines() == ["harness part spotcheck: key_ambiguous: R001, R002"]
    assert "R001" not in form(work) and "R002" not in form(work)
    assert [r["row"] for r in spot(work)["rows"]] == doc["rows"]
    # a subject and a mark with the same casefold share a key too (m1)
    rows = [
        row("R001", mark="<drop>", subject="Piles", field="count_plan", value="26"),
        row("R002", mark="PILES", field="count_plan", value="4"),
        row("R003", mark="K-2", value="900x900"),
    ]
    write_values(work, rows)
    lock(work, PART)
    code, doc, err = run(capsys, work, "--n", "20")
    assert code == 0 and doc and doc["rows"] == ["R003"] and "key_ambiguous: R001, R002" in err


def test_rows_without_a_file_are_left_out_of_the_pool(capsys, work):
    rows = [row("R001"), row("R002", mark="K-2", file="<drop>", sheet="<drop>"), row("R003", mark="K-3")]
    lock_part(work, rows)
    code, doc, err = run(capsys, work, "--n", "20")
    assert code == 0 and doc
    assert doc["rows"] == ["R001", "R003"]  # D4: R002 names no file, so `answer-key` could not record it
    assert "no_file: R002" in err and "R002" not in form(work)
    assert all(r["file"] is not None for r in spot(work)["rows"])


def test_rerun_rewrites_a_form_that_is_not_utf8(capsys, work):
    lock_part(work)
    assert run(capsys, work)[0] == 0
    good = form(work)
    path = work.parent / "spotcheck" / f"{PART}.md"
    path.write_bytes(b"\xff\xfe not utf-8 \x80")
    code, _, err = run(capsys, work)
    assert (code, err) == (0, "")  # m6: no traceback; the damaged file differs from the text
    assert form(work) == good


def test_rerun_unchanged(capsys, work):
    lock_part(work)
    code, first, _ = run(capsys, work)
    assert code == 0
    before = snapshot(work)
    assert run(capsys, work) == (0, first, "")
    assert snapshot(work) == before  # same seed and hash: nothing rewritten, byte-identical
    assert "at" not in spot(work) and "T00:" not in form(work)  # no timestamp
    code, other, _ = run(capsys, work, seed=8)
    assert code == 0 and other and other["seed"] == 8 and spot(work)["seed"] == 8


def test_is_a_locked_action(capsys, work, monkeypatch):
    assert "spotcheck" in LOCKED_ACTIONS["part"]
    lock_part(work)
    monkeypatch.setenv(worklock.WAIT_ENV, "0")
    with worklock.work_lock(work, "holder-test"):
        code, doc, err = run(capsys, work)
    assert code == 3 and doc is None and "holder-test" in err
    assert not (work / "parts" / PART / "spotcheck.json").exists()
    monkeypatch.delenv(worklock.WAIT_ENV)
    assert run(capsys, work)[0] == 0
    assert (work / "parts" / PART / "spotcheck.json").is_file()
    assert (work.parent / "spotcheck" / f"{PART}.md").is_file()


def test_output_validates(capsys, work):
    lock_part(work)
    code, doc, err = run(capsys, work)
    assert (code, err) == (0, "") and doc and validate("part-output", doc) == []
    assert doc["command"] == "spotcheck" and doc["part"] == PART and doc["seed"] == 7
    assert doc["written"] == [f"parts/{PART}/spotcheck.json", f"../spotcheck/{PART}.md"]
    # a part that is not in the manifest, or a work folder without one, is exit 1 with no output
    bad = main(["part", "spotcheck", str(work), "--part", "nope", "--seed", "1"])
    assert bad == 1 and capsys.readouterr().out == ""
