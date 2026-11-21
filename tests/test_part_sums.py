"""The hand-sum checks of `harness part check` (E5a-4): `hand_sum_invalid`, `hand_sum_mismatch` and the
`cite_unknown` of an id inside a `hand_sum` term.

The work folder is the one of `_part_fixtures` (K-1, K-2, D400 and the texts '1500x2400', '26', '-1.200').
The tests call `part_sums.sum_problems` on a loaded context, so the other checks of the merge (citations,
numbers) never add a problem here. Measured findings and plan marks are written into the copy of the work
folder: a measured finding is a record of `reader-findings.json` (its evidence snapshots the items), the
marks come from the real `harness marks` with a few more K-2 added.
"""

from __future__ import annotations

import copy
import importlib
import json
import shutil
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from _part_fixtures import (
    PART,
    REL,
    build_part_work,
    entry_ids,
    part_manifest,
    put_manifest,
    row,
    run_check,
    write_values,
)
from tekla_harness.cli import main
from tekla_harness.findings import withdraw_finding
from tekla_harness.part_values import PartContext, Problem, load_context
from tekla_harness.schemas import validate

SHEET = "model#01"
F_SYMBOLS = "F-003"  # two items: symbols 4 and 3
F_BARE = "F-004"  # two items: one without `symbols`
G1, G2 = "G-0000000001", "G-0000000002"
QUERY = {
    "sheet": SHEET, "outline_layers": ["S-CAP"], "circle_layers": ["S-PILE"], "max_long": 20000.0,
    "marks": "K-\\d+", "mark_radius": 3000.0, "detail": False, "max": None, "tol": 1.0,
}  # fmt: skip


@pytest.fixture(scope="module")
def base_work(tmp_path_factory) -> Path:
    return build_part_work(tmp_path_factory.mktemp("partsums"))


@pytest.fixture
def work(base_work, tmp_path) -> Path:
    target = tmp_path / "work"
    shutil.copytree(base_work, target)
    return target


def add_measured(work: Path, items: list[dict[str, Any]]) -> str:
    """Record a measured finding of B1-caps whose evidence holds `items`; returns its id."""
    path = work / "reader-findings.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    fid = f"F-{doc['next_id']:03d}"
    finding = copy.deepcopy(next(f for f in doc["findings"] if f["id"] == "F-001"))
    source = work / "geometry" / "contents-model-01-0123456789ab.json"  # a missing source makes it stale
    source.parent.mkdir(exist_ok=True)
    source.write_text("{}", encoding="utf-8")
    finding.update(
        id=fid, kind="measured", entries=[], value="the caps of the sheet", fields={"quantity": "count"},
        evidence={
            "source": "geometry/contents-model-01-0123456789ab.json", "sha256": sha256(b"{}").hexdigest(),
            "command": "contents", "query": QUERY, "items": items,
        },
    )  # fmt: skip
    finding.pop("decoded_by")
    doc["findings"].append(finding)
    doc["next_id"] += 1
    assert validate("reader-findings", doc) == []
    path.write_text(json.dumps(doc), encoding="utf-8")
    return fid


def with_findings(work: Path) -> None:
    """F-003 (symbols 4 + 3 on two items) and F-004 (the second item has no `symbols`)."""
    assert add_measured(work, [{"id": G1, "symbols": 4}, {"id": G2, "symbols": 3}]) == F_SYMBOLS
    assert add_measured(work, [{"id": G1, "symbols": 4}, {"id": G2}]) == F_BARE


def with_marks(work: Path) -> None:
    """marks.json of the real `harness marks`, plus: K-2 twice more and `k-2` on model#01 (4 in all), and
    K-2 on model#02 (it must not count for model#01)."""
    assert main(["marks", str(work)]) == 0
    path = work / "marks.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    k2 = next(p for p in doc["plan_marks"] if p["mark"] == "K-2")
    for n, (mark, sheet) in enumerate(
        [("K-2", SHEET), ("K-2", SHEET), ("k-2", SHEET), ("K-2", "model#02")], start=5
    ):
        doc["plan_marks"].append({**copy.deepcopy(k2), "id": f"P{n:06d}", "mark": mark, "sheet": sheet})
    assert validate("marks", doc) == []
    path.write_text(json.dumps(doc), encoding="utf-8")


def sum_row(
    row_id: str, subject: str, value: str | None, terms: list[dict[str, Any]], **more: Any
) -> dict[str, Any]:
    """A `seen` row `subject` / `count_plan` on model#01 whose value is the total of `terms`."""
    fields: dict[str, Any] = {
        "mark": "<drop>", "subject": subject, "field": "count_plan", "value": value, "cites": {},
        "hand_sum": {"terms": terms},
    }  # fmt: skip
    fields.update(more)
    return row(row_id, **fields)


def run_sums(work: Path, rows: list[dict[str, Any]]) -> list[Problem]:
    write_values(work, rows)
    mod = importlib.import_module("tekla_harness.part_sums")
    ctx: PartContext = load_context(work, PART)
    found: list[Problem] = mod.sum_problems(ctx)
    return sorted(found, key=Problem.sort_key)


def in_sheet(ctx: PartContext, tid: str) -> None:
    """Make the entry `tid` a text of the part's own sheet (a term entry is checked for scope like a cite)."""
    ctx.sheet_entries[(REL, SHEET)] = ctx.sheet_entries[(REL, SHEET)] | {tid}


def codes(found: list[Problem]) -> list[tuple[str, str | None, str | None]]:
    return [(p.code, p.row, p.id) for p in found]


def detail_of(found: list[Problem], code: str) -> str:
    (one,) = [p for p in found if p.code == code]
    return one.detail


SYMBOLS = {"finding": F_SYMBOLS, "of": "symbols"}
ITEMS = {"finding": F_SYMBOLS, "of": "items"}


def test_hand_sum_terms(work):
    with_findings(work)
    with_marks(work)
    ids = entry_ids(work)
    entry = {"entry": ids["26"]}
    marks = {"marks": "K-2"}
    # every kind of term, and a sum of three kinds: 7 symbols + 26 + 4 marks of model#01
    good = [
        sum_row("R001", "marks", "4", [marks]),  # casefold (`k-2`), this sheet only (not model#02's K-2)
        sum_row("R002", "symbols", "7", [SYMBOLS]),  # 4 + 3 symbols, not the 2 items
        sum_row("R003", "items", "2", [ITEMS]),
        sum_row("R004", "entry", "26", [entry]),
        sum_row("R005", "three kinds", "37", [SYMBOLS, entry, marks]),
        sum_row("R006", "unit", "7 pcs", [SYMBOLS]),  # a unit around the one number is as printed
        sum_row("R007", "decimal", "7.0", [SYMBOLS]),
        sum_row("R008", "empty", "0", [{"marks": "no such mark"}]),  # no plan mark: a sum of zero
    ]
    assert run_sums(work, good) == []
    # the same terms with a wrong total: each kind is recomputed, the detail lists its addend
    bad = [
        sum_row("R001", "marks", "5", [marks]),
        sum_row("R002", "symbols", "2", [SYMBOLS]),
        sum_row("R003", "items", "7", [ITEMS]),
        sum_row("R004", "entry", "27", [entry]),
        sum_row("R005", "three kinds", "36", [SYMBOLS, entry, marks]),
    ]
    found = run_sums(work, bad)
    assert codes(found) == [("hand_sum_mismatch", f"R00{n}", None) for n in range(1, 6)]
    by_row = {p.row: p.detail for p in found}
    assert "K-2" in by_row["R001"] and "4" in by_row["R001"] and "5" in by_row["R001"]
    assert f"{F_SYMBOLS} symbols: 7" in by_row["R002"]
    assert f"{F_SYMBOLS} items: 2" in by_row["R003"]
    assert "T0" in by_row["R004"] and "26" in by_row["R004"]
    assert all(s in by_row["R005"] for s in (f"{F_SYMBOLS} symbols: 7", "26", "K-2", "37"))


def test_hand_sum_mismatch_and_invalid(capsys, work):
    with_findings(work)
    ids = entry_ids(work)
    wrong = [
        sum_row("R001", "a", "6", [SYMBOLS]),
        sum_row("R002", "b", "7 of 12", [SYMBOLS]),  # a second number: the value is not exactly [total]
        sum_row("R003", "c", "7 pcs (2)", [SYMBOLS]),
        sum_row("R004", "d", "many", [SYMBOLS]),  # no number
        sum_row("R005", "e", "7 7", [SYMBOLS]),
        sum_row("R006", "f", None, [SYMBOLS], state="asked", cites={"questions": ["Q-003"]}),  # no value
        sum_row("R007", "g", "7", [SYMBOLS]),  # the right one
    ]
    found = run_sums(work, wrong)
    assert codes(found) == [("hand_sum_mismatch", f"R00{n}", None) for n in (1, 2, 3, 4, 5)]
    assert "7 of 12" in detail_of([p for p in found if p.row == "R002"], "hand_sum_mismatch")

    invalid = [
        sum_row("R001", "a", "7", [{"finding": "F-001", "of": "items"}]),  # a note_item: no evidence
        sum_row("R002", "b", "7", [{"finding": F_BARE, "of": "symbols"}]),  # an item without symbols
        sum_row("R003", "c", "7", [{"marks": "K-2"}], sheet="<drop>"),  # marks need the row's sheet
        sum_row("R004", "d", "7", [{"entry": ids["1500x2400"]}]),  # two integers
        sum_row("R005", "e", "7", [{"entry": ids["-1.200"]}]),  # none
        sum_row("R006", "f", "7", [{"marks": "K-2"}]),  # no marks.json in this work folder
        sum_row("R007", "g", "99", [{"entry": ids["26"]}, {"entry": ids["1500x2400"]}]),
    ]
    found = run_sums(work, invalid)
    # a total that cannot be computed is no mismatch: R007 is invalid only, though 99 is not 26
    assert codes(found) == [
        ("hand_sum_invalid", "R001", "F-001"),
        ("hand_sum_invalid", "R002", F_BARE),
        ("hand_sum_invalid", "R003", None),
        ("hand_sum_invalid", "R004", ids["1500x2400"]),
        ("hand_sum_invalid", "R005", ids["-1.200"]),
        ("hand_sum_invalid", "R006", None),
        ("hand_sum_invalid", "R007", ids["1500x2400"]),
    ]
    by_row = {p.row: p.detail for p in found}
    assert "evidence" in by_row["R001"] and G2 in by_row["R002"] and "symbols" in by_row["R002"]
    assert "sheet" in by_row["R003"] and "marks.json" in by_row["R006"]
    assert "integer" in by_row["R004"] and "integer" in by_row["R005"]

    # a text that holds one number which is not an integer
    write_values(work, [sum_row("R001", "h", "2", [{"entry": ids["26"]}])])
    ctx = load_context(work, PART)
    ctx.entries[(REL, ids["26"])] = ("2.5", True, True, SHEET)
    ctx.entries[(REL, "T999998")] = ("3 and 4", True, True, SHEET)
    in_sheet(ctx, "T999998")
    ctx.rows[:] = [
        sum_row("R001", "h", "2", [{"entry": ids["26"]}]),
        sum_row("R002", "i", "3", [{"entry": "T999998"}]),
    ]
    mod = importlib.import_module("tekla_harness.part_sums")
    found = sorted(mod.sum_problems(ctx), key=Problem.sort_key)
    assert codes(found) == [("hand_sum_invalid", "R001", ids["26"]), ("hand_sum_invalid", "R002", "T999998")]

    # `harness part check` merges them: one run, exit 1, the codes in the document
    write_values(work, [sum_row("R001", "a", "6", [SYMBOLS]), invalid[0]])
    code, doc, _ = run_check(capsys, work)
    assert code == 1 and doc and validate("part-output", doc) == []
    assert {p["code"] for p in doc["problems"]} >= {"hand_sum_mismatch", "hand_sum_invalid"}


def test_hand_sum_term_cites_unknown_id(work):
    with_findings(work)
    ids = entry_ids(work)
    rows = [
        sum_row("R001", "a", "7", [{"finding": "F-099", "of": "symbols"}]),
        sum_row("R002", "b", "7", [{"entry": "T999999"}]),
        sum_row("R003", "c", "7", [SYMBOLS, {"finding": "F-098", "of": "items"}]),  # one known, one not
        sum_row(
            "R004", "d", "7", [{"entry": ids["26"]}], file="<drop>", sheet="<drop>"
        ),  # no file to look in
        sum_row("R005", "e", "7", [SYMBOLS]),  # fine
    ]
    found = run_sums(work, rows)
    # a term that cannot be resolved gives cite_unknown and no mismatch (the total is not defined)
    assert codes(found) == [
        ("cite_unknown", "R001", "F-099"),
        ("cite_unknown", "R002", "T999999"),
        ("cite_unknown", "R003", "F-098"),
        ("cite_unknown", "R004", ids["26"]),
    ]
    assert all(p.detail for p in found)


def test_hand_sum_entry_term_must_be_readable_and_printed(work):
    """A font-blocked text is quoted, never read; a text that is not printed is no count: neither adds."""
    ids = entry_ids(work)
    tid = ids["26"]
    rows = [sum_row("R001", "a", "26", [{"entry": tid}])]  # the sum is 26: true when the text may be read
    write_values(work, rows)
    mod = importlib.import_module("tekla_harness.part_sums")
    ctx = load_context(work, PART)
    assert mod.sum_problems(ctx) == []  # the control: a readable, printed entry
    for flags, word in (((False, True), "blocked"), ((True, False), "not printed")):
        ctx = load_context(work, PART)
        ctx.entries[(REL, tid)] = ("26", *flags, SHEET)
        found = sorted(mod.sum_problems(ctx), key=Problem.sort_key)
        # the total is undefined: invalid only, no mismatch
        assert codes(found) == [("hand_sum_invalid", "R001", tid)], flags
        assert word in found[0].detail and tid in found[0].detail
    # one bad term among good ones: the whole row is invalid
    ctx = load_context(work, PART)
    ctx.entries[(REL, tid)] = ("26", False, True, SHEET)
    ctx.rows[:] = [sum_row("R001", "a", "27", [{"entry": ids["26"]}, {"entry": "T999998"}])]
    ctx.entries[(REL, "T999998")] = ("1", True, True, SHEET)
    in_sheet(ctx, "T999998")
    found = mod.sum_problems(ctx)
    assert codes(found) == [("hand_sum_invalid", "R001", tid)]


def edit_findings(work: Path, change: Any) -> None:
    path = work / "reader-findings.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    change(doc)
    path.write_text(json.dumps(doc), encoding="utf-8")


def test_regression_hand_sum_term_ids_get_the_cite_checks(work):
    """A term's finding or entry is checked like a row cite: withdrawn, stale, another part's, outside the
    part. The total is then undefined: the row gets the cite problem and no mismatch, even a wrong value."""
    with_findings(work)
    ids = entry_ids(work)
    tid = ids["26"]  # on model#02, a sheet only the input part lists
    wrong = "99"  # not the sum of any term below

    def one(row_id: str, term: dict[str, Any]) -> dict[str, Any]:
        return sum_row(row_id, row_id, wrong, [term])

    # the controls: the same terms are clean while the records are active, fresh, the part's and in scope
    clean = [one("R001", SYMBOLS), one("R002", {"entry": tid})]
    assert codes(run_sums(work, clean)) == [
        ("hand_sum_mismatch", "R001", None),
        ("hand_sum_mismatch", "R002", None),
    ]
    # P3: the input part is not listed any more, so model#02 is outside the part
    manifest = part_manifest(work)
    next(p for p in manifest["parts"] if p["id"] == PART).pop("inputs")
    put_manifest(work, manifest)
    found = run_sums(work, clean)
    assert codes(found) == [("entry_outside_part", "R002", tid), ("hand_sum_mismatch", "R001", None)]
    assert str(tid) in found[0].detail and PART in found[0].detail
    put_manifest(work, part_manifest(work))
    # P2: the finding belongs to a part that is neither this one nor an input
    edit_findings(
        work, lambda d: next(f for f in d["findings"] if f["id"] == F_SYMBOLS).update(part="all-assembly")
    )
    found = run_sums(work, clean)
    assert codes(found) == [("cite_foreign_part", "R001", F_SYMBOLS), ("hand_sum_mismatch", "R002", None)]
    assert "all-assembly" in found[0].detail
    edit_findings(work, lambda d: next(f for f in d["findings"] if f["id"] == F_SYMBOLS).pop("part"))
    assert codes(run_sums(work, clean))[0] == ("cite_foreign_part", "R001", F_SYMBOLS)  # untagged: foreign
    edit_findings(work, lambda d: next(f for f in d["findings"] if f["id"] == F_SYMBOLS).update(part=PART))
    # a stale finding: the drawing changed after it was recorded
    edit_findings(
        work, lambda d: next(f for f in d["findings"] if f["id"] == F_SYMBOLS).update(file_sha256="0" * 64)
    )
    found = run_sums(work, clean)
    assert codes(found) == [("cite_stale", "R001", F_SYMBOLS), ("hand_sum_mismatch", "R002", None)]
    edit_findings(
        work,
        lambda d: next(f for f in d["findings"] if f["id"] == F_SYMBOLS).update(
            file_sha256=d["findings"][0]["file_sha256"]
        ),
    )
    # P1: the finding is withdrawn
    withdraw_finding(work, F_SYMBOLS, "test", part=PART)
    found = run_sums(work, clean)
    assert ("cite_inactive", "R001", F_SYMBOLS) in codes(found)
    assert not [p for p in found if p.code == "hand_sum_mismatch" and p.row == "R001"]
    assert "withdrawn" in next(p for p in found if p.code == "cite_inactive").detail
    # one bad term among good ones: the row has the cite problem and no mismatch
    rows = [sum_row("R001", "a", wrong, [{"finding": F_BARE, "of": "items"}, SYMBOLS])]
    found = run_sums(work, rows)
    assert codes(found) == [("cite_inactive", "R001", F_SYMBOLS)]


def test_regression_one_cite_problem_when_cited_twice(capsys, work):
    """A row that cites F-003 directly and inside a term gets one cite_inactive, not two."""
    with_findings(work)
    withdraw_finding(work, F_SYMBOLS, "test", part=PART)
    r = sum_row("R001", "a", "7", [SYMBOLS], cites={"findings": [F_SYMBOLS]})
    write_values(work, [r])
    code, doc, _ = run_check(capsys, work)
    assert code == 1 and doc
    inactive = [p for p in doc["problems"] if p["code"] == "cite_inactive"]
    assert [(p["row"], p["id"]) for p in inactive] == [("R001", F_SYMBOLS)]


def _plain_docs() -> tuple[dict[str, Any], dict[str, Any], dict[tuple[str, str], str]]:
    findings = {"F-012": {"evidence": {"items": [{"id": G1, "symbols": 8}, {"id": G2, "symbols": 6}]}}}
    plan = [
        {"file": "a.json", "sheet": "s1", "mark": "K-2"},
        {"file": "a.json", "sheet": "s1", "mark": "k-2"},
        {"file": "a.json", "sheet": "s2", "mark": "K-2"},
        {"file": "b.json", "sheet": "s1", "mark": "K-2"},
    ]
    return findings, {"plan_marks": plan}, {("a.json", "T000470"): "26"}


def _plain_row(*terms: dict[str, Any]) -> dict[str, Any]:
    return {"row": "R001", "file": "a.json", "sheet": "s1", "hand_sum": {"terms": list(terms)}}


def test_addends_per_term_kind():
    from tekla_harness.part_sums import hand_sum_addends

    findings, marks_doc, entry_text = _plain_docs()
    row = _plain_row(
        {"finding": "F-012", "of": "symbols"},
        {"finding": "F-012", "of": "items"},
        {"marks": "K-2"},
        {"entry": "T000470"},
    )
    # one (term, value) per term in term order; the term text holds no value; marks: this file and sheet only
    assert hand_sum_addends(row, findings, marks_doc, entry_text) == [
        ("F-012 symbols", 14),
        ("F-012 items", 2),
        ("marks K-2", 2),
        ("T000470", 26),
    ]


def test_addends_empty_on_invalid_or_no_hand_sum():
    from tekla_harness.part_sums import hand_sum_addends

    findings, marks_doc, entry_text = _plain_docs()
    findings["F-013"] = {"evidence": {"items": [{"id": G1}]}}  # no symbols
    findings["F-014"] = {}  # not measured
    good = {"finding": "F-012", "of": "items"}
    assert hand_sum_addends({"row": "R001", "file": "a.json"}, findings, marks_doc, entry_text) == []
    bad_terms = [
        {"finding": "F-099", "of": "items"},  # unknown finding
        {"finding": "F-013", "of": "symbols"},
        {"finding": "F-014", "of": "items"},
        {"entry": "T999999"},  # unknown entry (or not readable: the caller leaves it out)
    ]
    for bad in bad_terms:  # never a partial list: the good term before and after is dropped too
        assert hand_sum_addends(_plain_row(good, bad, good), findings, marks_doc, entry_text) == []
    marks_row = _plain_row(good, {"marks": "K-2"})
    assert hand_sum_addends(marks_row, findings, None, entry_text) == []  # no marks.json
    no_sheet = {**marks_row, "sheet": None}
    assert hand_sum_addends(no_sheet, findings, marks_doc, entry_text) == []


def test_addends_match_hand_total(work):
    from tekla_harness.part_sums import hand_sum_addends, hand_total

    with_findings(work)
    with_marks(work)
    ids = entry_ids(work)
    terms = [SYMBOLS, ITEMS, {"entry": ids["26"]}, {"marks": "K-2"}]
    write_values(work, [sum_row("R001", "three kinds", "37", terms)])
    ctx = load_context(work, PART)
    (r,) = [r for r in ctx.rows if r["row"] == "R001"]
    total, _, problems = hand_total(ctx, r)
    assert problems == [] and total == 7 + 2 + 26 + 4
    entry_text = {k: v[0] for k, v in ctx.entries.items() if v[1] and v[2]}
    addends = hand_sum_addends(r, ctx.findings, ctx.marks, entry_text)
    assert [t for t, _ in addends][:2] == [f"{F_SYMBOLS} symbols", f"{F_SYMBOLS} items"]
    assert sum(v for _, v in addends) == total
