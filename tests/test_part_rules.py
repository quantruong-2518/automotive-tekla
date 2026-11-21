"""`harness part check`: the text-rule checks of `part_rules.text_problems` (ADR-0019, E5c).

Coverage (`sheet_uncovered`, `mark_missing`, `marks_regex_invalid`), blocking questions on listed values
(`listed_*`, `low_without_question`), the claim form of a finding, unaccented search terms, the family
linework question and the verbatim values (`value_not_verbatim`, `note_quote_unmatched`). Every test builds a
`PartContext` directly (keyword arguments, no DXF) with invented records and calls the hook. Each test holds a
positive control (a record the rule flags), so none passes on a hook that finds nothing.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from tekla_harness.part_values import PartContext, Scope

PART = "B1-caps"
F = "plans/set.dxf"
S1, S2, S3 = "model#01", "model#02", "model#03"
EMPTY = Scope(frozenset(), frozenset())
FONT = "font_encoding_proposed"
NOTE = "node: n; basis: single_source; alt: a"


def mod() -> Any:
    """The module under test, imported when a test runs (the red commit has no `LISTED` yet)."""
    return importlib.import_module("tekla_harness.part_rules")


def make(**more: Any) -> PartContext:
    base: dict[str, Any] = {
        "work": Path(), "part": PART, "manifest": {},
        "part_row": {"id": PART, "kind": "member", "order": 1},
        "own": EMPTY, "inputs": EMPTY, "views": {}, "rows": [], "findings": {}, "registry": {},
        "questions": {}, "entries": {}, "sheet_entries": {}, "cluster_entries": {}, "marks": None,
        "saved": {},
    }  # fmt: skip
    base.update(more)
    return PartContext(**base)


def run(ctx: PartContext, *codes: str) -> list[tuple[str, str | None, str | None]]:
    """(code, row, id) of the problems of `codes` (all when none is named), sorted as `check_part` sorts."""
    found = [(p.code, p.row, p.id) for p in mod().text_problems(ctx) if not codes or p.code in codes]
    return sorted(found, key=lambda t: (t[0], t[1] or "", t[2] or ""))


def details(ctx: PartContext, code: str) -> list[str]:
    return [p.detail for p in mod().text_problems(ctx) if p.code == code]


def finding(fid: str = "F-001", **more: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": fid, "kind": "sheet_class", "status": "active", "file": F, "file_sha256": "0" * 64,
        "sheet": S1, "entries": [], "value": "x", "fields": {}, "questions": [], "confidence": "medium",
        "note": NOTE, "part": PART, "stale": False,
    }  # fmt: skip
    base.update(more)
    return base


def question(qid: str, code: str = "reader_size_unclear", **more: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": qid, "key": "0" * 16, "code": code, "blocking": True, "file": F, "message": "Which one?",
        "count": 1, "truncated": False, "refs": [{"where": S1, "found": "a value"}], "answer": None,
        "parts": [PART],
    }  # fmt: skip
    base.update(more)
    return base


def registered(qid: str, code: str = "reader_size_unclear", **more: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": qid,
        "code": code,
        "status": "open",
        "producer": "reader",
        "blocking": True,
    }
    entry.update(more)
    return entry


def row(rid: str = "R001", **more: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "row": rid, "mark": "K-1", "field": "count_plan", "value": "(SL: 6)", "file": F, "sheet": S1,
        "state": "seen", "cites": {},
    }  # fmt: skip
    base.update(more)
    return base


def entries(*items: tuple[str, str, str | None]) -> dict[tuple[str, str], tuple[str, bool, bool, str | None]]:
    """(entry id, text, sheet) -> the `entries` of a context."""
    return {(F, tid): (text, True, True, sheet) for tid, text, sheet in items}


def evidence(**item: Any) -> dict[str, Any]:
    return {
        "source": "geometry/g.json", "sha256": "0" * 64, "command": "geometry", "query": {"tol": 2.0},
        "items": [{"id": "G-0123456789", **item}],
    }  # fmt: skip


def test_sheet_uncovered_unless_a_row_or_own_finding():
    part_row = {"id": PART, "kind": "member", "order": 1, "sheets": [
        {"file": F, "sheet": S1, "role": "plan"},
        {"file": F, "sheet": S2, "role": "plan"},
        {"file": F, "sheet": S3, "role": "plan"},
    ]}  # fmt: skip
    ctx = make(
        part_row=part_row,
        rows=[row(sheet=S2)],
        findings={
            "F-001": finding(sheet=S3),
            "F-002": finding("F-002", sheet=S1, part="other"),  # another part's finding covers nothing
            "F-003": finding("F-003", sheet=S1, status="withdrawn"),
        },
    )
    assert run(ctx, "sheet_uncovered") == [("sheet_uncovered", None, None)]
    assert S1 in details(ctx, "sheet_uncovered")[0]
    covered = make(part_row=part_row, rows=[row(sheet=S1), row("R002", sheet=S2), row("R003", sheet=S3)])
    assert run(covered, "sheet_uncovered") == []


def test_mark_missing_casefold_regex():
    plan = [
        {"file": F, "sheet": S1, "mark": "K-2", "text_ref": {"file": F, "entry_id": "T000001"}},
        {"file": F, "sheet": S1, "mark": "K-3", "text_ref": {"file": F, "entry_id": "T000002"}},
        {"file": F, "sheet": S1, "mark": "P-1", "text_ref": {"file": F, "entry_id": "T000003"}},
        {"file": F, "sheet": S1, "mark": "K-10", "text_ref": {"file": F, "entry_id": "T000004"}},
        {"file": F, "sheet": S2, "mark": "K-9", "text_ref": {"file": F, "entry_id": "T000005"}},
    ]
    tables = [{"file": F, "sheet": S1, "rows": [{"marks": [
        {"entry_id": "T000006", "text": "K-4", "shape": "mark"},
        {"entry_id": "T000007", "text": "K-5 (new)", "shape": "other"},
    ]}]}]  # fmt: skip
    part_row = {"id": PART, "kind": "member", "order": 1, "marks_regex": r"K-\d"}
    ctx = make(
        part_row=part_row,
        own=Scope(frozenset({(F, S1)}), frozenset()),
        marks={"plan_marks": plan, "tables": tables},
        rows=[row(mark="k-2")],  # casefold: covers the plan mark K-2
    )
    found = run(ctx, "mark_missing")
    assert found == [("mark_missing", None, None)] * 2
    text = " ".join(details(ctx, "mark_missing"))
    assert "K-3" in text and "K-4" in text
    assert not any(m in text for m in ("K-2", "P-1", "K-10", "K-9", "K-5"))  # row, regex, other sheet, shape
    assert (
        run(
            make(part_row={"id": PART, "kind": "member", "order": 1}, marks={"plan_marks": plan}),
            "mark_missing",
        )
        == []
    )


def test_marks_regex_invalid():
    marks = {
        "plan_marks": [
            {"file": F, "sheet": S1, "mark": "K-3", "text_ref": {"file": F, "entry_id": "T000002"}}
        ]
    }
    own = Scope(frozenset({(F, S1)}), frozenset())
    bad = make(
        part_row={"id": PART, "kind": "member", "order": 1, "marks_regex": "K-("}, own=own, marks=marks
    )
    assert run(bad, "marks_regex_invalid", "mark_missing") == [("marks_regex_invalid", None, None)]
    assert "K-(" in details(bad, "marks_regex_invalid")[0]
    good = make(
        part_row={"id": PART, "kind": "member", "order": 1, "marks_regex": "K-[0-9]"}, own=own, marks=marks
    )
    assert run(good, "marks_regex_invalid", "mark_missing") == [("mark_missing", None, None)]


def test_listed_single_source_needs_a_blocking_question():
    ents = entries(("T000001", "(SL: 6)", S1))
    registry = {"Q-001": registered("Q-001")}
    one = row(cites={"entries": ["T000001"]})
    asks = row("R002", cites={"entries": ["T000001"], "questions": ["Q-001"]})
    ctx = make(rows=[one, asks], entries=ents, registry=registry)
    assert run(ctx, "listed_needs_blocking") == [("listed_needs_blocking", "R001", None)]
    other = row("R003", field="material", cites={"entries": ["T000001"]})  # not LISTED: no question needed
    assert run(make(rows=[other], entries=ents), "listed_needs_blocking") == []
    via_finding = row("R004", cites={"findings": ["F-001"]})  # a question of a cited finding counts
    ctx = make(
        rows=[via_finding],
        findings={"F-001": finding(value="(SL: 6)", questions=["Q-001"])},
        registry=registry,
    )
    assert run(ctx, "listed_needs_blocking") == []


def test_two_keys_or_an_agreeing_count_pair_suffice():
    ents = entries(
        ("T000001", "(SL: 6)", S1), ("T000002", "(SL: 6)", S2), ("T000003", "(SL: 7)", S2),
        ("T000004", "(SL: 6)", S1), ("T000005", "(SL: 6)", None),
    )  # fmt: skip
    two = row("R001", cites={"entries": ["T000001", "T000002"]})  # two sheets: two keys
    same_sheet = row("R002", cites={"entries": ["T000001", "T000004"]})  # one key
    cluster = row("R003", cites={"entries": ["T000001", "T000005"]})  # a sheet and a cluster: two keys
    unbacked = row("R004", cites={"entries": ["T000001", "T000003"]})  # 2nd key's text does not back 6
    ctx = make(
        rows=[two, same_sheet, cluster, unbacked],
        entries=ents,
        cluster_entries={(F, None, "none"): frozenset({"T000005"})},
    )
    assert run(ctx, "listed_needs_blocking") == [
        ("listed_needs_blocking", "R002", None),
        ("listed_needs_blocking", "R004", None),
    ]
    # a count_plan and a count_schedule row of one mark with equal single numbers: one extra key each
    plan = row("R005", mark="DC-1", field="count_plan", cites={"entries": ["T000001"]})
    schedule = row("R006", mark="dc-1", field="count_schedule", sheet=S2, cites={"entries": ["T000002"]})
    assert run(make(rows=[plan, schedule], entries=ents), "listed_needs_blocking") == []
    differs = row(
        "R007", mark="DC-2", field="count_schedule", value="(SL: 7)", sheet=S2, cites={"entries": ["T000003"]}
    )
    lone = row("R008", mark="DC-2", field="count_plan", cites={"entries": ["T000001"]})
    assert run(make(rows=[lone, differs], entries=ents), "listed_needs_blocking") == [
        ("listed_needs_blocking", "R007", None),
        ("listed_needs_blocking", "R008", None),
    ]
    # the finding's own `basis: two_sources` is not trusted; a `high` finding is two keys
    claimed = finding(value="(SL: 6)", note="node: n; basis: two_sources; alt: a")
    high = finding("F-002", value="(SL: 6)", confidence="high")
    ctx = make(
        rows=[row(cites={"findings": ["F-001"]}), row("R002", cites={"findings": ["F-002"]})],
        findings={"F-001": claimed, "F-002": high},
    )
    assert run(ctx, "listed_needs_blocking") == [("listed_needs_blocking", "R001", None)]


def test_listed_asked_unread_absent_need_a_blocking_question():
    registry = {"Q-001": registered("Q-001")}
    states = ("asked", "unread", "absent")
    bare = [
        row(f"R00{i}", state=s, value=None if s != "asked" else "(SL: 6)") for i, s in enumerate(states, 1)
    ]
    assert run(make(rows=bare), "listed_needs_blocking") == [
        ("listed_needs_blocking", f"R00{i}", None) for i in (1, 2, 3)
    ]
    asked = [
        row(f"R00{i}", state=s, value=None, cites={"questions": ["Q-001"]}) for i, s in enumerate(states, 1)
    ]
    assert run(make(rows=asked, registry=registry), "listed_needs_blocking") == []
    free = [
        row(f"R00{i}", field=f, state="asked", value=None) for i, f in enumerate(("material", "other"), 1)
    ]
    assert run(make(rows=free), "listed_needs_blocking") == []  # material and other are not LISTED
    assert run(make(rows=[row(field="level", state="unread", value=None)]), "listed_needs_blocking") != []


def test_listed_row_citing_non_blocking_question():
    registry = {"Q-001": registered("Q-001"), "Q-002": registered("Q-002", blocking=False)}
    direct = row("R001", state="asked", value=None, cites={"questions": ["Q-002"]})
    through = row("R002", state="asked", value=None, cites={"findings": ["F-001"]})
    fine = row("R003", state="asked", value=None, cites={"questions": ["Q-001"]})
    material = row("R004", field="material", state="asked", value=None, cites={"questions": ["Q-002"]})
    ctx = make(
        rows=[direct, through, fine, material],
        registry=registry,
        findings={"F-001": finding(questions=["Q-002"])},
    )
    assert run(ctx, "listed_question_not_blocking") == [
        ("listed_question_not_blocking", "R001", "Q-002"),
        ("listed_question_not_blocking", "R002", "Q-002"),
    ]
    assert [r for _, r, _ in run(ctx, "listed_needs_blocking")] == ["R001", "R002"]  # nothing blocks either
    # a registry entry written before `blocking` existed counts as blocking (schema, `harness status`)
    old = registered("Q-003")
    del old["blocking"]
    legacy = row("R005", state="asked", value=None, cites={"questions": ["Q-003"]})
    ctx = make(rows=[legacy], registry={"Q-003": old})
    assert run(ctx, "listed_needs_blocking", "listed_question_not_blocking") == []


def test_regression_non_blocking_question_on_a_pile_count():
    code = "reader_pile_count_unclear"
    cites = {"questions": ["Q-001"]}
    loose = make(
        rows=[row(mark="P-1", field="piles_per_member", state="asked", value=None, cites=cites)],
        registry={"Q-001": registered("Q-001", code, blocking=False)},
    )
    assert run(loose, "listed_question_not_blocking", "listed_needs_blocking") == [
        ("listed_needs_blocking", "R001", None),
        ("listed_question_not_blocking", "R001", "Q-001"),
    ]
    blocking = make(
        rows=[row(mark="P-1", field="piles_per_member", state="asked", value=None, cites=cites)],
        registry={"Q-001": registered("Q-001", code)},
    )
    assert run(blocking, "listed_question_not_blocking", "listed_needs_blocking") == []


def test_low_finding_needs_a_non_font_question():
    registry = {"Q-001": registered("Q-001", FONT), "Q-002": registered("Q-002")}
    found = {
        "F-001": finding("F-001", confidence="low"),
        "F-002": finding("F-002", confidence="low", questions=["Q-001"]),  # a font question only
        "F-003": finding("F-003", confidence="low", questions=["Q-001", "Q-002"]),
        "F-004": finding("F-004", confidence="medium"),
        "F-005": finding("F-005", confidence="low", part="other"),
        "F-006": finding("F-006", confidence="low", status="withdrawn"),
    }
    ctx = make(findings=found, registry=registry)
    assert run(ctx, "low_without_question") == [
        ("low_without_question", None, "F-001"),
        ("low_without_question", None, "F-002"),
    ]


def test_regression_withdrawn_question_through_a_finding_blocks_nothing():
    """A question a cited finding names counts only while it is live: an obsolete one blocks nothing."""
    cited = {"findings": ["F-001"]}
    live = {"Q-009": registered("Q-009")}
    gone = {"Q-009": registered("Q-009", status="obsolete")}
    gone_loose = {"Q-009": registered("Q-009", status="obsolete", blocking=False)}
    found = {"F-001": finding(value="x", questions=["Q-009"])}
    seen = row(field="size", value="x", cites=cited)  # one source key: a blocking question is needed
    asked = row("R002", field="size", mark="K-2", state="asked", value=None, cites=cited)
    unread = row("R003", field="size", mark="K-3", state="unread", value=None, cites=cited)
    absent = row("R004", field="size", mark="K-4", state="absent", value=None, cites=cited)
    rows = [seen, asked, unread, absent]
    bare = ("listed_needs_blocking",)
    assert run(make(rows=rows, findings=found, registry=live), *bare) == []  # the control: a live one blocks
    every = [("listed_needs_blocking", f"R00{n}", None) for n in (1, 2, 3, 4)]
    assert run(make(rows=rows, findings=found, registry=gone), *bare) == every
    # the obsolete question is no "non-blocking question" either: that code would carry a misleading detail
    both = ("listed_needs_blocking", "listed_question_not_blocking")
    assert run(make(rows=rows, findings=found, registry=gone_loose), *both) == every
    # a live blocking question beside the obsolete one still blocks
    two = {"F-001": finding(value="x", questions=["Q-009", "Q-010"])}
    registry = {**gone, "Q-010": registered("Q-010")}
    assert run(make(rows=rows, findings=two, registry=registry), *bare) == []


def test_regression_low_finding_with_only_an_obsolete_question():
    registry = {"Q-001": registered("Q-001"), "Q-002": registered("Q-002", status="obsolete")}
    found = {
        "F-001": finding("F-001", confidence="low", questions=["Q-002"]),  # only an obsolete question
        "F-002": finding("F-002", confidence="low", questions=["Q-001"]),  # a live one: fine
        "F-003": finding("F-003", confidence="low", questions=["Q-002", "Q-001"]),
    }
    assert run(make(findings=found, registry=registry), "low_without_question") == [
        ("low_without_question", None, "F-001")
    ]


def test_mark_missing_uses_the_sheets_and_tables_only_not_a_cluster_sheet():
    """D1: a sided cluster opens its own entries, not the whole sheet it sits beside: its sheet is in
    `row_sheets` (a row may be written there) but no mark of that sheet is demanded."""
    part_row = {"id": PART, "kind": "member", "order": 1, "marks_regex": r"K-\d+"}
    marks = {"plan_marks": [{"mark": "K-1", "file": F, "sheet": S1}]}
    sheets = frozenset({(F, S1)})
    clusters = frozenset({(F, S1, "below")})
    only_cluster = Scope(frozenset(), clusters, sheets)
    ctx = make(part_row=part_row, own=only_cluster, marks=marks)
    assert run(ctx, "mark_missing") == []
    ctx = make(part_row=part_row, own=Scope(sheets, clusters, sheets), marks=marks)  # the control
    assert run(ctx, "mark_missing") == [("mark_missing", None, None)]


def without_note(f: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in f.items() if k != "note"}


def test_claim_form_fields():
    notes = {
        "F-001": "node: n; basis: single_source; alt: a",
        "F-002": "basis: single_source; alt: a",
        "F-003": "node: n; alt: a",
        "F-004": "node: n; basis: single_source",
        "F-005": "node: n; basis: guess; alt: a",
        "F-006": "node: n; basis: single_sourced; alt: a",
        "F-007": "node:; basis: two_sources; alt:",
    }
    found = {k: finding(k, kind="measured", note=v) for k, v in notes.items()}
    found["F-008"] = without_note(finding("F-008", kind="measured"))  # no note: every field is missing
    found["F-009"] = finding("F-009", kind="note_item", note="block: no claim form here")
    found["F-010"] = finding("F-010", kind="cross_check", note="x", part="other")
    ctx = make(findings=found)
    assert run(ctx, "claim_form") == [("claim_form", None, f"F-00{n}") for n in (2, 3, 4, 5, 6, 7, 8)]
    by_id = {p.id: p.detail for p in mod().text_problems(ctx) if p.code == "claim_form"}
    assert "node" in by_id["F-002"] and "basis" in by_id["F-003"] and "alt" in by_id["F-004"]
    assert all(w in by_id["F-008"] for w in ("node", "basis", "alt"))


def test_note_item_starts_block():
    found = {
        "F-001": finding("F-001", kind="note_item", note="block: concrete C30"),
        "F-002": finding("F-002", kind="note_item", note="level: +0,450"),
        "F-003": finding("F-003", kind="note_item", note="a block: b"),
        "F-004": finding("F-004", kind="note_item", note="x", part="other"),
        "F-005": finding("F-005", kind="note_item", status="withdrawn", note="x"),
        "F-006": without_note(finding("F-006")),  # a sheet_class: the claim form's business
    }
    ctx = make(findings=found)
    assert run(ctx, "note_item_prefix") == [
        ("note_item_prefix", None, "F-002"),
        ("note_item_prefix", None, "F-003"),
    ]
    nonote = without_note(finding("F-007", kind="note_item"))
    assert run(make(findings={"F-007": nonote}), "note_item_prefix") == [("note_item_prefix", None, "F-007")]


def test_search_record_needs_unaccented_twins():
    q1 = question("Q-001", message="searched 'kèo', 'keo', 'mái'")  # misses 'mai'
    q2 = question("Q-002", message="ok", refs=[{"where": S1, "found": 'Searched: “dầm”, "dam", “bê tông”'}])
    q3 = question(
        "Q-003", message="searched ('kèo', 'keo') and Searched (all clusters): 'KÈO'", parts=["other"]
    )
    f1 = finding("F-001", note="searched: 'Ống', 'ong'; searched 'tôn', 'KEO'")  # two records, one flaws
    ctx = make(
        questions={"Q-001": q1, "Q-002": q2, "Q-003": q3}, findings={"F-001": f1},
        rows=[row(note="searched 'đà' 'thép'")],
    )  # fmt: skip
    assert run(ctx, "search_unaccented") == [
        ("search_unaccented", None, "F-001"),
        ("search_unaccented", None, "Q-001"),
        ("search_unaccented", None, "Q-002"),
        ("search_unaccented", "R001", None),
    ]  # Q-003 belongs to another part; every other record has its twins
    text = {p.id or p.row: p.detail for p in mod().text_problems(ctx) if p.code == "search_unaccented"}
    assert "'mai'" in text["Q-001"] and "'keo'" not in text["Q-001"]
    assert "'be tong'" in text["Q-002"] and "'dam'" not in text["Q-002"]
    assert "'ton'" in text["F-001"] and "'ong'" not in text["F-001"]
    assert "'da'" in text["R001"] and "'thep'" in text["R001"]
    clean = make(questions={"Q-001": question("Q-001", message="searched 'kèo', 'keo', 'KÈO'")})
    assert run(clean, "search_unaccented") == []


def test_regression_absence_without_the_unaccented_term():
    absent = row(field="material", state="absent", value=None, note="searched 'kèo' on every sheet: no hit")
    ctx = make(rows=[absent], entries=entries(("T000001", "keo", S1)))  # the twin has hits: still a problem
    assert run(ctx, "search_unaccented") == [("search_unaccented", "R001", None)]
    assert "keo" in details(ctx, "search_unaccented")[0]
    fixed = row(field="material", state="absent", value=None, note="searched 'kèo', 'keo': no hit")
    assert run(make(rows=[fixed]), "search_unaccented") == []


def test_d_with_stroke_maps_to_d():
    def flagged(text: str) -> list[str]:
        return details(make(questions={"Q-001": question("Q-001", message=text)}), "search_unaccented")

    assert "'di'" in flagged("searched 'đi'")[0]  # đ -> d (a decomposition would keep it)
    assert "'Da'" in flagged("searched 'Đà'")[0]  # Đ -> D
    assert flagged("searched 'đà', 'da'") == []
    assert flagged("searched 'Đà', 'da'") == []  # casefold
    assert len(flagged("searched 'đà', 'dà'")) == 1  # 'dà' has no twin 'da'


def test_searched_without_quoted_terms_is_no_record():
    quiet = question("Q-001", message="unassigned_searched: yes; searched nothing; Searched: yes")
    assert run(make(questions={"Q-001": quiet}), "search_unaccented") == []
    noisy = question("Q-001", message="unassigned_searched: yes; searched 'kèo'")
    assert run(make(questions={"Q-001": noisy}), "search_unaccented") == [
        ("search_unaccented", None, "Q-001")
    ]


def test_family_linework_twice_and_needless():
    code = "reader_family_linework"
    qs = {f"Q-00{n}": question(f"Q-00{n}", code) for n in (1, 2, 3)}
    registry = {f"Q-00{n}": registered(f"Q-00{n}", code) for n in (1, 2, 3)}
    ents = entries(("T000001", "1200", S1), ("T000002", "1200", S2))
    measured = finding("F-001", value="1200", evidence=evidence(short=1200.0))
    one_key = row("R001", field="size", value="1200", cites={"findings": ["F-001"]})
    two_keys = row("R002", field="size", value="1200", cites={"findings": ["F-001"], "entries": ["T000002"]})
    base: dict[str, Any] = {"findings": {"F-001": measured}, "entries": ents}

    twice = make(questions=dict(list(qs.items())[:2]), registry=registry, rows=[one_key], **base)
    assert run(twice, "family_linework_twice", "family_linework_needless") == [
        ("family_linework_twice", None, "Q-002")
    ]
    gone = {**registry, "Q-002": registered("Q-002", code, status="obsolete")}  # a withdrawn one is not live
    assert run(make(questions=dict(list(qs.items())[:2]), registry=gone, rows=[one_key], **base),
               "family_linework_twice", "family_linework_needless") == []  # fmt: skip

    only = {"Q-001": qs["Q-001"]}
    needless = make(questions=only, registry=registry, rows=[two_keys], **base)
    assert run(needless, "family_linework_twice", "family_linework_needless") == [
        ("family_linework_needless", None, "Q-001")
    ]
    mixed = make(
        questions=only, registry=registry, rows=[one_key, two_keys], **base
    )  # one row needs a second key
    assert run(mixed, "family_linework_needless") == []
    assert run(make(questions=only, registry=registry), "family_linework_needless") == []  # no rows at all
    assert run(make(rows=[two_keys], **base), "family_linework_needless") == []  # no such question


def test_regression_family_question_is_needed_when_no_row_uses_linework():
    """E5 review 1, m3: `all()` over zero linework rows was true, so the question was called needless."""
    code = "reader_family_linework"
    unread = row("R001", field="size", state="unread", value=None, cites={"questions": ["Q-001"]})
    ctx = make(
        questions={"Q-001": question("Q-001", code)},
        registry={"Q-001": registered("Q-001", code)},
        rows=[unread],
    )
    assert run(ctx, "family_linework_needless") == []


def test_regression_researched_is_no_search_record():
    """E5 review 1, m2: `searched` inside a word (`researched`, `unsearched`) is no search record."""

    def flagged(text: str) -> list[tuple[str, str | None, str | None]]:
        return run(make(questions={"Q-001": question("Q-001", message=text)}), "search_unaccented")

    assert flagged("researched 'kèo'") == []
    assert flagged("unsearched 'kèo'") == []
    assert flagged("Searched: 'kèo'") == [("search_unaccented", None, "Q-001")]


def test_regression_an_asked_count_gives_its_partner_no_pair_key():
    """E5 review 1, m1: only a `seen` partner row is the second source of an agreeing count pair."""
    ents = entries(("T000001", "(SL: 6)", S1))
    registry = {"Q-001": registered("Q-001")}
    plan = row("R001", mark="DC-1", field="count_plan", cites={"entries": ["T000001"]})
    asked = row(
        "R002", mark="DC-1", field="count_schedule", sheet=S2, state="asked", cites={"questions": ["Q-001"]}
    )
    ctx = make(rows=[plan, asked], entries=ents, registry=registry)
    assert run(ctx, "listed_needs_blocking") == [("listed_needs_blocking", "R001", None)]
    # the same pair with a seen partner is still two keys (the other tests pin it), and an asked row that
    # is the plan row gives the schedule row nothing either
    seen = row("R003", mark="DC-1", field="count_schedule", sheet=S2, cites={"entries": ["T000001"]})
    assert run(make(rows=[plan, seen], entries=ents), "listed_needs_blocking") == []
    asked_plan = row("R004", mark="DC-1", field="count_plan", state="asked", cites={"questions": ["Q-001"]})
    assert run(make(rows=[asked_plan, seen], entries=ents, registry=registry), "listed_needs_blocking") == [
        ("listed_needs_blocking", "R003", None)
    ]


def test_regression_marks_regex_matches_case_blind():
    """E5 review 1, m7 and D3: a legacy-font mark decoded in another case (`k-1`) is still demanded."""
    plan = [{"file": F, "sheet": S1, "mark": "k-1", "text_ref": {"file": F, "entry_id": "T000001"}}]
    part_row = {"id": PART, "kind": "member", "order": 1, "marks_regex": r"K-\d+"}
    own = Scope(frozenset({(F, S1)}), frozenset())
    ctx = make(part_row=part_row, own=own, marks={"plan_marks": plan, "tables": []})
    assert run(ctx, "mark_missing") == [("mark_missing", None, None)]
    covered = make(
        part_row=part_row, own=own, marks={"plan_marks": plan, "tables": []}, rows=[row(mark="K-1")]
    )
    assert run(covered, "mark_missing") == []


def test_regression_quote_on_no_entry():
    ents = entries(("T000001", "(SL: 6)", S1), ("T000002", "unrelated", S1))
    typed = row(value="(SL: 60)", cites={"entries": ["T000001"]})  # a number the entry does not hold
    elsewhere = row("R002", value="(SL: 6)", cites={"entries": ["T000002"]})
    nothing = row("R003", value="(SL: 6)")
    right = row("R004", value="(SL: 6)", cites={"entries": ["T000001"]})
    ctx = make(rows=[typed, elsewhere, nothing, right], entries=ents)
    assert run(ctx, "value_not_verbatim") == [("value_not_verbatim", f"R00{n}", None) for n in (1, 2, 3)]


def test_value_verbatim_casefold_and_join():
    ents = entries(
        ("T000001", "NÉT CẮT 1-1", S1),
        ("T000002", "Level", S1),
        ("T000003", "+0,450", S1),
        ("T000004", "Nét cắt", S1),
    )
    nfd = "Ne\u0301t cắt 1-1"  # typed decomposed: the same text for a reader
    rows = [
        row("R001", value="Nét cắt 1-1", cites={"entries": ["T000001"]}),
        row("R002", value="Level +0,450", cites={"entries": ["T000002", "T000003"]}),
        row("R003", value="+0,450 Level", cites={"entries": ["T000002", "T000003"]}),  # reading order matters
        row("R004", value=nfd, cites={"entries": ["T000001"]}),
        row("R005", value="Nét cắt 2-2", cites={"entries": ["T000004"]}),
    ]  # fmt: skip
    ctx = make(rows=rows, entries=ents)
    assert run(ctx, "value_not_verbatim") == [
        ("value_not_verbatim", "R003", None),
        ("value_not_verbatim", "R005", None),
    ]


def test_note_quote_unmatched():
    ents = entries(("T000001", "D400 and C30/37", S1))
    cites = {"entries": ["T000001"]}
    note = "reads 'D400', “c30/37” and \u2018ghost\u2019; also \"phantom\" and “x” but not the reader's note"
    ctx = make(rows=[row(note=note, cites=cites)], entries=ents)
    assert run(ctx, "note_quote_unmatched") == [("note_quote_unmatched", "R001", None)] * 2
    text = " ".join(details(ctx, "note_quote_unmatched"))
    assert "ghost" in text and "phantom" in text and "D400" not in text and "c30" not in text.lower()
    quiet = row(note="reads 'D400' and “c30/37”, the reader's note", cites=cites)
    assert run(make(rows=[quiet], entries=ents), "note_quote_unmatched") == []


def test_measured_and_sum_rows_skip_it():
    ents = entries(("T000001", "text", S1))
    measured = finding("F-001", value="1500", evidence=evidence(short=1200.0, long=1500.0))
    by_finding = row("R001", field="size", value="1.2 x 1.5 m", cites={"findings": ["F-001"]})
    by_geometry = row(
        "R002",
        field="size",
        value="1200",
        cites={"geometry": {"source": "geometry/g.json", "items": ["G-0123456789"]}},
    )
    summed = row("R003", value="13", cites={}, hand_sum={"terms": [{"marks": "K-1"}]})
    control = row("R004", field="size", value="1.2 x 1.5 m", cites={"entries": ["T000001"]})
    ctx = make(rows=[by_finding, by_geometry, summed, control], findings={"F-001": measured}, entries=ents)
    assert run(ctx, "value_not_verbatim") == [("value_not_verbatim", "R004", None)]
    asked = row("R005", state="asked", value="(SL: 3)", cites={"entries": ["T000001"]})
    assert run(make(rows=[asked], entries=ents), "value_not_verbatim") == []  # only a `seen` row is checked


def test_listed_is_every_field_but_material_and_other():
    schema = json.loads(
        (Path(__file__).parent.parent / "schemas" / "part-values.schema.json").read_text("utf-8")
    )
    fields = set(schema["$defs"]["row"]["properties"]["field"]["enum"])
    assert isinstance(mod().LISTED, frozenset)
    assert fields - {"material", "other"} == mod().LISTED
