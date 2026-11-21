"""`harness part check`: the number checks `number_unbacked` and `token_unbacked` (ADR-0019, E5a).

Every number and every glued token a part reader types into a row's `value` must be found in a source the
row cites: a cited entry's text, a cited finding's value, entries and evidence items, the items of a cited
saved document, and (an `asked` row only) a cited question's message and `found`. The work folder is the one
of `_part_fixtures`; a source the fixture cannot build (an entry of another text, a measured finding, a
saved geometry document) is put into the loaded `PartContext` with `dataclasses.replace`, and the check
runs on it directly.
"""

from __future__ import annotations

import dataclasses
import importlib
import shutil
from pathlib import Path
from typing import Any

import pytest

from _part_fixtures import (
    PART,
    REL,
    build_part_work,
    entry_ids,
    row,
    run_check,
    write_values,
)
from tekla_harness.ask import ask_question

CODES = ("number_unbacked", "token_unbacked")
NEW_ENTRY = (REL, "T999991")  # an entry the fixture does not have


def mod(name: str) -> Any:
    """A module under test, imported when a test runs (the red commit has no function yet)."""
    return importlib.import_module(f"tekla_harness.{name}")


@pytest.fixture(scope="module")
def base_work(tmp_path_factory) -> Path:
    return build_part_work(tmp_path_factory.mktemp("partnumbers"))


@pytest.fixture
def work(base_work, tmp_path) -> Path:
    target = tmp_path / "work"
    shutil.copytree(base_work, target)
    return target


def mine(doc: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The number problems of a check document."""
    assert doc is not None
    return [p for p in doc["problems"] if p["code"] in CODES]


def check(capsys, work: Path, *rows: dict[str, Any]) -> list[dict[str, Any]]:
    write_values(work, list(rows))
    _, doc, _ = run_check(capsys, work)
    return mine(doc)


def context(work: Path, rows: list[dict[str, Any]], **more: Any) -> Any:
    """The loaded context of `rows`, with `more` (findings, saved, entries: added to the loaded ones)."""
    write_values(work, rows)
    ctx = mod("part_values").load_context(work, PART)
    changes = {k: {**getattr(ctx, k), **v} for k, v in more.items()}
    return dataclasses.replace(ctx, **changes)


def run(ctx: Any) -> list[tuple[str, str | None, str]]:
    return [(p.code, p.row, p.detail) for p in mod("part_numbers").number_problems(ctx)]


def measured(*, tol: float = 2.0, texts: tuple[str, ...] = (), **item: Any) -> dict[str, Any]:
    """A finding with evidence: one snapshot item (`item`) and the saved query's `tol`."""
    return {
        "id": "F-900", "kind": "measured", "status": "active", "value": "x", "part": PART,
        "entries": [{"id": f"T00000{i}", "display_text": t} for i, t in enumerate(texts)],
        "evidence": {
            "source": "geometry/x.json", "query": {"tol": tol}, "items": [{"id": "G-0123456789", **item}],
        },
    }  # fmt: skip


def test_numbers_backed_by_entry_finding_or_items_within_tol(work, capsys):
    ids = entry_ids(work)
    cites_entry = {"entries": [ids["1500x2400"]]}
    # entry text: both numbers of '1500x2400', exactly; 1501 is no number of it
    assert check(capsys, work, row(cites=cites_entry), row("R002", field="other", value="1500")) == []
    near = check(capsys, work, row(value="1501", cites=cites_entry))
    assert [(p["code"], p["row"], p["detail"]) for p in near] == [
        ("number_unbacked", "R001", "1501 is in no cited source")
    ]
    # the value and the entry texts of a cited finding (F-001 has both)
    assert check(capsys, work, row(cites={"findings": ["F-001"]})) == []
    # F-002 has the text of K-1 and the value 'foundation': no number
    both = check(capsys, work, row(cites={"findings": ["F-002"]}))
    assert [p["detail"] for p in both] == ["1500 is in no cited source", "2400 is in no cited source"]

    # evidence items: short, long, diameter, symbols, len(items), within the saved query's tol
    f = measured(tol=2.0, texts=("1500x2400",), short=1000.0, long=3000.5, diameter=400.0, symbols=7)
    here = lambda v: context(work, [row(value=v, cites={"findings": ["F-900"]})], findings={"F-900": f})  # noqa: E731
    for backed in ("1001", "1000", "2999", "D399", "402", "7", "1"):  # tol 2; 7 = symbols, 1 = len(items)
        assert run(here(backed)) == [], backed
    assert [d for _, _, d in run(here("1003"))] == ["1003 is in no cited source"]
    # a text number is exact: 2401 is within tol of 2400 but a text number never gets the tol
    assert [d for _, _, d in run(here("2401"))] == ["2401 is in no cited source"]
    assert run(here("2400")) == []
    # an item number is not exact
    assert run(here("1002")) == [] and run(here("1002.5")) != []
    # symbols and the item count are not measures: no tolerance (7 symbols do not back 8, nor 5)
    assert [d for _, _, d in run(here("8"))] == ["8 is in no cited source"]
    assert [d for _, _, d in run(here("5"))] == ["5 is in no cited source"]

    # a cited saved document: its items' numbers within its own query's tol
    doc = {
        "kind": "geometry",
        "query": {"tol": 1.0},
        "regions": [{"items": [{"id": "G-0123456789", "diameter": 400.0}]}],
    }
    geo = {"geometry": {"source": "geometry/x.json", "items": ["G-0123456789"]}}
    saved = lambda v: context(  # noqa: E731
        work, [row(value=v, cites=geo)], saved={"geometry/x.json": doc}
    )
    assert run(saved("D401")) == [] and run(saved("400")) == []
    assert [d for _, _, d in run(saved("402"))] == ["402 is in no cited source"]
    # an item the document does not list backs nothing (cite_unknown reports it)
    unlisted = {"geometry": {**geo["geometry"], "items": ["G-ffffffffff"]}}
    other = context(work, [row(value="400", cites=unlisted)], saved={"geometry/x.json": doc})
    assert run(other) == [("number_unbacked", "R001", "400 is in no cited source")]


def test_symbols_and_count_back_a_number_only_exactly(work):
    """The tolerance is for `short`, `long` and `diameter`; a count backs only its own number, as
    `findings._unbacked_numbers` has it."""
    f = measured(tol=2.0, short=1000.0, symbols=7)  # one item: the item count is 1
    here = lambda v: context(work, [row(value=v, cites={"findings": ["F-900"]})], findings={"F-900": f})  # noqa: E731
    for backed in ("7", "1", "1002", "998"):
        assert run(here(backed)) == [], backed
    for unbacked in ("8", "6", "5", "2", "3", "1002.5"):
        assert run(here(unbacked)) != [], unbacked
    doc = {
        "kind": "geometry",
        "query": {"tol": 2.0},
        "regions": [
            {"items": [{"id": "G-0123456789", "symbols": 4}, {"id": "G-0123456780", "diameter": 400.0}]}
        ],
    }
    geo = {"geometry": {"source": "geometry/x.json", "items": ["G-0123456789", "G-0123456780"]}}
    saved = lambda v: context(  # noqa: E731
        work, [row(value=v, cites=geo)], saved={"geometry/x.json": doc}
    )
    for backed in (
        "4",
        "2",
        "400",
        "402",
    ):  # symbols and the count (2 items) exactly, the diameter within tol
        assert run(saved(backed)) == [], backed
    for unbacked in ("3", "5", "1"):
        assert [d for _, _, d in run(saved(unbacked))] == [f"{unbacked} is in no cited source"], unbacked


def test_glued_tokens_need_a_quote(work, capsys):
    values = mod("part_values")
    assert values.glued_tokens("D400 400x600 (SL: 6) 26 hs=200") == []
    assert values.glued_tokens("-1.200 2Ø16 -0,450 C30/37 24M 1-1") == [
        "-1.200", "2Ø16", "-0,450", "C30/37", "24M", "1-1",
    ]  # fmt: skip

    def one(value: str, text: str, **row_more: Any) -> list[tuple[str, str | None, str]]:
        entries = {NEW_ENTRY: (text, True, True, "model#01")}
        r = row(value=value, cites={"entries": [NEW_ENTRY[1]]}, **row_more)
        return run(context(work, [r], entries=entries))

    # -0,450 against +0,450: the number 450 is backed, the sign is part of the token
    assert one("+0,450", "+0,450") == []
    assert one("-0,450", "-0,450") == []
    wrong_sign = one("-0,450", "+0,450")
    assert [(c, r) for c, r, _ in wrong_sign] == [("token_unbacked", "R001")]
    assert "-0,450" in wrong_sign[0][2]
    # a quote ends on a token boundary and ignores case
    assert one("24m", "24M") == [] and one("C30/37", "beton C30/37, B500") == []
    assert "token_unbacked" in [c for c, _, _ in one("C30/37", "C30/370")]  # cut mid-token
    assert [c for c, _, _ in one("2Ø16", "2Ø20")] == ["token_unbacked"]
    # one token backs, the other does not: one problem for the other
    assert [d for _, _, d in one("-1.200 -3.400", "-1.200")] == ["'-3.400' quotes no cited source text"]
    # a token split over two entries is quoted by neither alone
    split = {NEW_ENTRY: ("-1.", True, True, None), (REL, "T999992"): ("200", True, True, None)}
    r = row(value="-1.200", cites={"entries": ["T999991", "T999992"]})
    assert [c for c, _, _ in run(context(work, [r], entries=split))] == ["token_unbacked"]

    # through the command: the fixture's '-1.200' (model#02) is quoted by its entry, not by a finding of K-1
    ids = entry_ids(work)
    level = row(field="level", value="-1.200", cites={"entries": [ids["-1.200"]]})
    assert check(capsys, work, level) == []
    loose = check(capsys, work, row(field="level", value="-1.200", cites={"findings": ["F-001"]}))
    assert [p["code"] for p in loose] == ["token_unbacked"]


def test_regression_value_without_a_source(work, capsys):
    """A value typed from memory (no cited source holds it) was accepted before this check existed."""
    ids = entry_ids(work)
    typed = row("R004", field="level_top", value="1500", cites={"entries": [ids["K-1"]]})
    write_values(work, [typed, row("R005", mark="K-2", field="size", cites={"findings": ["F-001"]})])
    code, doc, _ = run_check(capsys, work)
    assert code == 1
    assert [(p["code"], p["row"], p["id"]) for p in mine(doc)] == [("number_unbacked", "R004", None)]
    assert mine(doc)[0]["detail"] == "1500 is in no cited source"
    # a repeated number is one problem
    twice = check(capsys, work, row(value="1600x1600", cites={"entries": [ids["K-1"]]}))
    assert [p["detail"] for p in twice] == ["1600 is in no cited source"]
    # a row with a hand_sum is checked by its sum, not by its sources
    summed = row(value="26", cites={}, hand_sum={"terms": [{"marks": "P-1"}]})
    assert run(context(work, [summed])) == []
    # a null value has no number
    assert run(context(work, [row(state="unread", value=None, cites={"questions": ["Q-003"]})])) == []


def test_asked_candidate_backed_by_its_question(work, capsys):
    made = ask_question(
        work, code="reader_level_unclear", where="model#01 K-2 top", found="level 1450 mm, -1.250",
        text="Cao độ đỉnh là 1540?", file=REL, sheet="model#01", blocking=True, part=PART,
    )  # fmt: skip
    qid = made["id"]
    asked = lambda v, **kw: row(state="asked", value=v, cites={"questions": [qid]}, **kw)  # noqa: E731
    # the candidate in the question's message or in a ref's found
    assert check(capsys, work, asked("1540")) == []
    assert check(capsys, work, asked("1450")) == []
    assert check(capsys, work, asked("-1.250", field="level")) == []
    other = check(capsys, work, asked("1460"))
    assert [(p["code"], p["detail"]) for p in other] == [("number_unbacked", "1460 is in no cited source")]
    # a seen row gets nothing from a question: it must cite what it read
    seen = check(capsys, work, row(value="1450", cites={"questions": [qid], "findings": ["F-002"]}))
    assert [p["code"] for p in seen] == ["number_unbacked"]
    seen_token = check(
        capsys, work, row(field="level", value="-1.250", cites={"questions": [qid], "findings": ["F-002"]})
    )
    assert [p["code"] for p in seen_token] == ["token_unbacked"]
    # the sources of a row, by kind
    ctx = context(work, [asked("1450")])
    assert [s.label for s in mod("part_values").sources(ctx, ctx.rows[0])] == [qid]
    ctx = context(work, [row(value="1450", cites={"questions": [qid]})])
    assert mod("part_values").sources(ctx, ctx.rows[0]) == []
