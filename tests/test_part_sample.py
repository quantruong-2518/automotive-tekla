"""`harness part chain` (C8) and `harness part review-sample` (C9), plus the seeded sampler `stratified` (E7).

The work folder is the real intake of `_part_fixtures.build_part_work` plus a text left of sheet 1 (`OUT-2`,
in the unassigned cluster `(REL, model#01, left)`), two sheet numbers (`S-05`, `S-06`) and three view headings
that hold a size, a level and a type (`PLAN K-1 1500x2400`, `FFL -1.200`, `TYPE KB-9`). Each test copies it,
rewrites the manifest and the `values.json` files it needs and runs the real command. The sampler tests call
`stratified` on plain rows.
"""

from __future__ import annotations

import importlib
import json
import shutil
import string
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from _part_fixtures import (
    INPUT_PART,
    PART,
    REL,
    TEXTS,
    build_part_work,
    entry_ids,
    part_manifest,
    put_manifest,
    row,
    write_values,
)
from tekla_harness.cli import main
from tekla_harness.schemas import validate
from test_part_sums import add_measured


def ps() -> Any:
    """The module under test, imported when a test runs (the red commit has no sampler yet)."""
    return importlib.import_module("tekla_harness.part_sample")


@pytest.fixture(scope="module")
def base_work(tmp_path_factory) -> Path:
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(TEXTS, "OUT-2", (-30000, 50000))
        for at, text in enumerate(("S-05", "S-06", "PLAN K-1 1500x2400", "FFL -1.200", "TYPE KB-9")):
            patch.setitem(TEXTS, text, (62000, 54000 - 500 * at))  # on sheet 1, below the other texts
        return build_part_work(tmp_path_factory.mktemp("partsample"))


@pytest.fixture
def work(base_work, tmp_path) -> Path:
    target = tmp_path / "work"
    shutil.copytree(base_work, target)
    return target


def run(capsys, *argv: str) -> tuple[int, dict[str, Any] | None, str]:
    code = main(["part", *argv])
    cap = capsys.readouterr()
    return code, (json.loads(cap.out) if cap.out else None), cap.err


def chain(capsys, work: Path, block: str = "B1") -> tuple[int, dict[str, Any] | None, str]:
    return run(capsys, "chain", str(work), "--block", block)


def sample(capsys, work: Path, *more: str, part: str = PART, seed: int = 7):
    return run(capsys, "review-sample", str(work), "--part", part, "--seed", str(seed), *more)


def count_row(row_id: str, mark: str | None, field: str, value: str | None, **more: Any) -> dict[str, Any]:
    """A row of a count field of mark `mark` (or the subject `piles` when `mark` is None)."""
    fields: dict[str, Any] = {"field": field, "value": value, "cites": {}, **more}
    if mark is None:
        fields.update(mark="<drop>", subject="piles")
    else:
        fields["mark"] = mark
    return row(row_id, **fields)


def two_blocks(work: Path) -> None:
    """The fixture manifest plus a second member part of B1 with the same order as B1-caps (listed after it,
    its id sorts before), block B2 with a part, and a cross part."""
    manifest = part_manifest(work)
    sheet = {"file": REL, "sheet": "model#02", "role": "plan"}
    manifest["blocks"].append({"id": "B2", "grid_system_ids": [], "origin_note": "Block B2: its own grid"})
    manifest["parts"] += [
        {"id": "B1-beams", "kind": "member", "block": "B1", "family": "beams", "order": 2, "sheets": [sheet]},
        {"id": "B2-caps", "kind": "member", "block": "B2", "family": "caps", "order": 0, "sheets": [sheet]},
        {"id": "all-grid-levels", "kind": "cross", "order": 1, "sheets": [sheet]},
    ]
    put_manifest(work, manifest)


# --- chain ------------------------------------------------------------------------------------------------


def test_chain_order_fields_numbers(capsys, work):
    two_blocks(work)
    write_values(work, [count_row("R001", "K-1", "count_plan", "13")], INPUT_PART)
    write_values(
        work,
        [
            row("R009", field="size"),  # not a count field
            count_row("R004", "K-2", "piles_per_member", "3"),
            count_row("R002", "K-1", "count_schedule", "14 nos"),
            count_row("R003", "K-2", "count_plan", "6+7"),  # two numbers: none
            count_row("R005", None, "count_plan", None, state="asked"),  # nothing read
            count_row("R001", "K-1", "count_plan", "13", state="asked"),
        ],
        "B1-beams",
    )
    write_values(work, [], PART)
    code, doc, err = chain(capsys, work)
    assert (code, err) == (0, "") and doc and doc["command"] == "chain" and doc["block"] == "B1"
    # by (order, id): B1-piles (1), then B1-beams and B1-caps (both 2, the id breaks the tie)
    assert [p["part"] for p in doc["parts"]] == [INPUT_PART, "B1-beams", PART]
    assert [p["order"] for p in doc["parts"]] == [1, 2, 2]
    beams = doc["parts"][1]
    # rows by row id; the number is the one number of the value, else null
    assert [(r["row"], r["field"], r["value"], r["number"], r["state"]) for r in beams["rows"]] == [
        ("R001", "count_plan", "13", 13, "asked"),
        ("R002", "count_schedule", "14 nos", 14, "seen"),
        ("R003", "count_plan", "6+7", None, "seen"),
        ("R004", "piles_per_member", "3", 3, "seen"),
        ("R005", "count_plan", None, None, "asked"),
    ]
    assert [(r["mark"], r["subject"]) for r in beams["rows"]][-1] == (None, "piles")
    assert beams["rows"][0]["mark"] == "K-1" and beams["rows"][0]["subject"] is None
    assert all(r["addends"] == [] for r in beams["rows"])
    assert doc["parts"][2]["rows"] == []


def test_chain_addends_products_sums(capsys, work):
    ids = entry_ids(work)
    items = [{"id": "G-0000000001", "symbols": 4}, {"id": "G-0000000002", "symbols": 3}]
    assert add_measured(work, items) == "F-003"
    terms = [{"finding": "F-003", "of": "symbols"}, {"entry": ids["26"]}]
    hand = count_row("R002", None, "count_plan", "33", hand_sum={"terms": terms})
    broken = count_row(
        "R003", None, "count_schedule", "5", hand_sum={"terms": [{"finding": "F-099", "of": "items"}]}
    )
    write_values(work, [count_row("R001", "K-1", "count_plan", "13"), hand, broken], INPUT_PART)
    write_values(
        work,
        [
            count_row("R001", "K-1", "count_plan", "13"),
            count_row("R002", "K-2", "count_plan", "45"),
            count_row("R003", "K-1", "piles_per_member", "2"),
            count_row("R004", "K-2", "piles_per_member", "3"),
            count_row("R005", "K-3", "count_plan", "9"),  # no piles per member: no product
            count_row("R006", None, "count_plan", "7"),  # a subject row: not in the sums
            # a mark split across sheets: K-1 counts add up (13 + 5); K-2 has two piles per member: no product
            count_row("R007", "K-1", "count_plan", "5", sheet="model#02"),
            count_row("R008", "K-2", "piles_per_member", "4", sheet="model#02"),
            # two rows with the same piles per member are one distinct number: a product
            count_row("R009", "K-4", "count_plan", "4"),
            count_row("R010", "K-4", "piles_per_member", "2"),
            count_row("R011", "K-4", "piles_per_member", "2", sheet="model#02"),
        ],
    )
    code, doc, _ = chain(capsys, work)
    assert code == 0 and doc
    piles, caps = doc["parts"]
    assert piles["rows"][1]["addends"] == [
        {"term": "F-003 symbols", "value": 7},
        {"term": ids["26"], "value": 26},
    ]
    assert piles["rows"][2]["addends"] == []  # a term that does not resolve: never a partial list
    assert piles["products"] == [] and piles["sums"] == {"count_plan": 13, "count_x_piles": None}
    # the product of a mark counts every count_plan row of it, so the sums describe the same caps
    assert caps["products"] == [
        {"mark": "K-1", "count_plan": 18, "piles_per_member": 2, "product": 36},
        {"mark": "K-4", "count_plan": 4, "piles_per_member": 2, "product": 8},
    ]
    assert caps["sums"] == {"count_plan": 76, "count_x_piles": 44}  # 13 + 45 + 9 + 5 + 4; 36 + 8
    assert [r["addends"] for r in caps["rows"]] == [[]] * 11
    # a withdrawn finding gives no addend: the term of F-003 does not resolve
    assert main(["finding", "withdraw", str(work), "F-003", "--reason", "test", "--part", PART]) == 0
    capsys.readouterr()
    code, doc, _ = chain(capsys, work)
    assert code == 0 and doc and doc["parts"][0]["rows"][1]["addends"] == []


def test_chain_unknown_block_1(capsys, work):
    code, doc, err = chain(capsys, work, "B9")
    assert (code, doc) == (1, None) and "B9" in err
    # no manifest: the same exit
    put_manifest(work, None)
    code, doc, err = chain(capsys, work)
    assert (code, doc) == (1, None) and "manifest" in err
    # a member part of the block without values.json (or with an invalid one): exit 1, no output
    put_manifest(work, part_manifest(work))
    write_values(work, [row()], PART)
    write_values(work, None, INPUT_PART)
    code, doc, err = chain(capsys, work)
    assert (code, doc) == (1, None) and "values.json" in err
    write_values(work, "{", INPUT_PART)
    assert chain(capsys, work)[0] == 1


def test_chain_skips_other_blocks_and_cross_parts(capsys, work):
    two_blocks(work)
    rows = [count_row("R001", "K-1", "count_plan", "13")]
    for part in (INPUT_PART, "B1-beams", PART, "B2-caps", "all-grid-levels", "scout"):
        write_values(work, rows, part)
    code, doc, _ = chain(capsys, work)
    assert code == 0 and doc
    assert [p["part"] for p in doc["parts"]] == [INPUT_PART, "B1-beams", PART]
    code, doc, _ = chain(capsys, work, "B2")
    assert code == 0 and doc and [p["part"] for p in doc["parts"]] == ["B2-caps"]
    assert doc["parts"][0]["order"] == 0


# --- sampler ----------------------------------------------------------------------------------------------


def pool(fields: list[str]) -> list[dict[str, Any]]:
    return [{"row": f"R{n:03d}", "field": f, "state": "seen"} for n, f in enumerate(fields, start=1)]


# 20 rows: nine LISTED fields (size x4, thickness x3, depth x2, ...) and two others
SPREAD = pool(
    ["size"] * 4 + ["thickness"] * 3 + ["depth"] * 2
    + ["length", "count_plan", "count_schedule", "level", "axes", "spacing"]
    + ["material", "other", "other", "other"]
)  # fmt: skip


def ids_of(rows: list[dict[str, Any]]) -> list[str]:
    return [r["row"] for r in rows]


def test_stratified_one_per_listed_field_deterministic():
    stratified = ps().stratified
    listed = {
        "size",
        "thickness",
        "depth",
        "length",
        "count_plan",
        "count_schedule",
        "level",
        "axes",
        "spacing",
    }
    got = stratified(SPREAD, 5, 7, "B1-caps:review")
    # n is below the nine LISTED fields: one row each, in row-id order, none of material or other
    assert len(got) == 9 and {r["field"] for r in got} == listed
    assert ids_of(got) == sorted(ids_of(got))
    assert ids_of(stratified(SPREAD, 5, 7, "B1-caps:review")) == ids_of(got)  # the same seed, the same rows
    assert ids_of(stratified(list(reversed(SPREAD)), 5, 7, "B1-caps:review")) == ids_of(got)  # pool by row id
    # n above the LISTED fields: n rows, the first nine still one per field
    more = stratified(SPREAD, 14, 7, "B1-caps:review")
    assert len(more) == 14 and listed <= {r["field"] for r in more}
    # the seed and the salt both move the choice
    seeds = {tuple(ids_of(stratified(SPREAD, 14, s, "x"))) for s in range(6)}
    salts = {tuple(ids_of(stratified(SPREAD, 14, 7, f"salt{k}"))) for k in range(6)}
    assert len(seeds) > 1 and len(salts) > 1
    # the choice per field takes the rows of the lowest priority
    ranked = stratified(SPREAD, 5, 7, "x", priority=lambda r: 0 if r["row"] == "R003" else 1)
    assert "R003" in ids_of(ranked) and sum(r["field"] == "size" for r in ranked) == 1
    for seed in range(5):
        picked = stratified(SPREAD, 5, seed, "x", priority=lambda r: 0 if r["row"] in ("R002", "R007") else 1)
        assert {"R002", "R007"} <= set(ids_of(picked))


def test_stratified_golden_sample():
    """The sample itself is pinned: the `random` docs promise only `random()` across Python versions."""
    stratified = ps().stratified
    assert ids_of(stratified(SPREAD, 5, 7, "B1-caps:review")) == [
        "R002", "R006", "R009", "R010", "R011", "R012", "R013", "R014", "R015",
    ]  # fmt: skip
    assert ids_of(stratified(SPREAD, 12, 7, "B1-caps:review")) == [
        "R001", "R002", "R003", "R006", "R009", "R010", "R011", "R012", "R013", "R014", "R015", "R017",
    ]  # fmt: skip


def test_small_pool_gives_all_rows():
    stratified = ps().stratified
    eight = pool(["size", "size", "size", "thickness", "thickness", "depth", "other", "other"])
    assert ids_of(stratified(list(reversed(eight)), 2, 3, "x")) == ids_of(eight)  # eight rows: all
    nine = pool(["size", "size", "size", "thickness", "thickness", "depth", "other", "other", "other"])
    assert len(stratified(nine, 2, 3, "x")) == 3  # nine rows: max(n, 3 LISTED fields)
    assert stratified([], 5, 3, "x") == []


# --- review-sample ----------------------------------------------------------------------------------------


ABSENT: dict[str, Any] = {"state": "absent", "file": "<drop>", "sheet": "<drop>", "cites": {}}


def caps_rows(ids: dict[str, str]) -> list[dict[str, Any]]:
    """Fifteen rows: thirteen value rows (R002 cites the text `OUT-2` outside the frames, R010 is asked and
    has no file), two absent rows."""
    spec = [
        ("K-1", "size", "1500x2400"), ("K-2", "size", "900x900"), ("K-1", "thickness", "hs=800"),
        ("K-2", "thickness", "hs=900"), ("K-1", "depth", "D400"), ("K-2", "depth", "D500"),
        ("K-1", "level", "-1.200"),
    ]  # fmt: skip
    rows = [row(f"R{n:03d}", mark=m, field=f, value=v) for n, (m, f, v) in enumerate(spec, start=1)]
    rows[1] = row(
        "R002", mark="K-2", field="size", value="900x900", sheet="<drop>", cites={"entries": [ids["OUT-2"]]}
    )
    rows += [
        row("R008", mark="K-9", field="length", value=None, **ABSENT),
        row("R009", mark="K-8", field="spacing", value=None, **ABSENT),
        row("R010", mark="<drop>", subject="piles", field="count_plan", value="26", state="asked",
            file="<drop>", sheet="<drop>", cites={}),
    ]  # fmt: skip
    rows += [row(f"R{n:03d}", mark="K-5", field="axes", value=f"A-{n}") for n in range(11, 16)]
    return rows


def left_cluster(work: Path) -> None:
    """B1-caps lists the cluster of the text left of sheet 1."""
    manifest = part_manifest(work)
    next(p for p in manifest["parts"] if p["id"] == PART)["clusters"] = [
        {"file": REL, "sheet": "model#01", "side": "left"}
    ]
    put_manifest(work, manifest)


def kinds(doc: dict[str, Any]) -> list[str]:
    return [p["kind"] for p in doc["prompts"]]


def test_outputs_validate_read_only(capsys, work):
    left_cluster(work)
    write_values(work, caps_rows(entry_ids(work)))
    write_values(work, [count_row("R001", "K-1", "count_plan", "13")], INPUT_PART)
    snapshot = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in work.rglob("*") if p.is_file()}
    code, doc, err = sample(capsys, work)
    assert (code, err) == (0, "") and doc and validate("part-output", doc) == []
    assert doc["command"] == "review_sample" and doc["part"] == PART and doc["seed"] == 7
    code, doc, err = chain(capsys, work)
    assert (code, err) == (0, "") and doc and validate("part-output", doc) == []
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in work.rglob("*") if p.is_file()} == snapshot
    # the seed decides: the same seed gives the same document
    first = sample(capsys, work, "--n", "4")[1]
    assert first and sample(capsys, work, "--n", "4")[1] == first


def test_absence_and_outside_frame_prompts(capsys, work):
    left_cluster(work)
    rows = caps_rows(entry_ids(work))
    write_values(work, rows)
    in_sample, out_of_sample = 0, 0
    for seed in range(8):
        code, doc, _ = sample(capsys, work, "--n", "8", seed=seed)
        assert code == 0 and doc
        values = [p["row"] for p in doc["prompts"] if p["kind"] == "value"]
        absence = [p for p in doc["prompts"] if p["kind"] == "absence"]
        outside = [p for p in doc["prompts"] if p["kind"] == "outside_frame"]
        assert len(values) == 8 and values == sorted(values) and len(absence) == 1
        assert absence[0]["row"] in ("R008", "R009") and absence[0]["file"] is None
        assert absence[0]["prompt"].startswith("Does the drawing give a ")  # no file, no sheet: no place
        if "R002" in values:  # sampled as a value: not offered again
            in_sample += 1
            assert outside == []
        else:
            out_of_sample += 1
            assert [p["row"] for p in outside] == ["R002"] and outside[0]["sheet"] is None
            assert outside[0]["prompt"] == (  # a file and no sheet: the file names the place
                f"File {REL}: what size does the text outside the sheet frames give for K-2? "
                "Cite the entry ids."
            )
        assert kinds(doc) == ["value"] * 8 + ["absence"] + ["outside_frame"] * len(outside)
    assert in_sample and out_of_sample  # both cases were run
    # eight rows with a value and no absent row: all are sampled, so nothing is left for the other kinds
    write_values(work, [r for r in rows if r["row"] <= "R007" or r["row"] == "R010"])
    assert kinds(sample(capsys, work)[1]) == ["value"] * 8  # type: ignore[index]
    # no absent row and no row outside the frames: only value prompts
    write_values(work, [r for r in rows if r["state"] != "absent" and r["row"] != "R002"])
    assert set(kinds(sample(capsys, work)[1])) == {"value"}  # type: ignore[index]


def test_prompt_keys_only_no_value(capsys, work):
    ids = entry_ids(work)
    left_cluster(work)
    rows = caps_rows(ids)
    write_values(work, rows)
    seed = next(s for s in range(20) if "outside_frame" in kinds(sample(capsys, work, seed=s)[1]))  # type: ignore[arg-type]
    first = sample(capsys, work, seed=seed)[1]
    assert first and set(kinds(first)) == {"value", "absence", "outside_frame"}
    # the same rows with other values and other cites: the prompts are the same (the values never reach them)
    other = {"entries": [ids["1500x2400"]]}
    changed = [
        {
            **r,
            "value": None if r["value"] is None else "77",
            "cites": r["cites"] if r["row"] == "R002" or not r["cites"] else other,
        }
        for r in rows
    ]
    write_values(work, changed)
    second = sample(capsys, work, seed=seed)[1]
    assert second and [p["prompt"] for p in second["prompts"]] == [p["prompt"] for p in first["prompts"]]
    keys = {"row", "kind", "mark", "subject", "field", "file", "sheet", "sheet_number", "view", "prompt"}
    assert all(set(p) == keys for p in first["prompts"] + second["prompts"])
    # each template holds only the placeholders field and who: no value, cite or entry id, no digit
    mod = ps()
    for template in (mod.VALUE_PROMPT, mod.ABSENCE_PROMPT, mod.OUTSIDE_PROMPT):
        names = {name for _, name, _, _ in string.Formatter().parse(template) if name}
        assert names == {"field", "who"} and not any(ch.isdigit() for ch in template)


def block_texts(work: Path) -> None:
    """K-2 is font-blocked (its meaning may not be read) and D400 does not print."""
    path = work / "text" / f"{REL}.json"
    index = json.loads(path.read_text(encoding="utf-8"))
    for e in index["entries"]:
        if e["display_text"] == "K-2":
            e["flags"] = ["legacy_ascii_suspect"]
        if e["display_text"] == "D400":
            e["printed"] = False
            e["not_printed_reasons"] = ["layer_off"]
    path.write_text(json.dumps(index), encoding="utf-8")


def test_sheet_number_from_manifest_entry(capsys, work):
    block_texts(work)
    ids = entry_ids(work)
    manifest = part_manifest(work)
    parts = {p["id"]: p for p in manifest["parts"]}
    own, upstream = parts[PART]["sheets"][0], parts[INPUT_PART]["sheets"][0]
    upstream["number_entry"] = ids["S-05"]  # the sheet of an input part: its number is found too
    own["views"] = [
        {"heading_entry": ids["P-1"]},
        {"heading_entry": ids["D400"]},
        {"bbox": [0, 0, 1000, 500]},
    ]
    put_manifest(work, manifest)
    rows = [
        row("R001", field="size", view={"heading_entry": ids["P-1"]}),
        row("R002", mark="P-1", field="count_plan", value="26", sheet="model#02",
            cites={"entries": [ids["P-1"]]}),
        row("R003", mark="K-2", field="level", value="-1.200", view={"bbox": [0, 0, 1000, 500]}),
        row("R004", mark="K-2", field="depth", value="D400", view={"heading_entry": ids["D400"]}),
    ]  # fmt: skip
    write_values(work, rows)

    def prompts() -> dict[str, dict[str, Any]]:
        code, doc, _ = sample(capsys, work)
        assert code == 0 and doc and validate("part-output", doc) == []
        return {p["row"]: p for p in doc["prompts"]}

    got = prompts()
    assert [(got[r]["sheet_number"], got[r]["view"]) for r in ("R001", "R002", "R003", "R004")] == [
        (None, "P-1"), ("S-05", None), (None, None), (None, None),  # D400 does not print: never quoted
    ]  # fmt: skip
    # no number: the prompt starts with the sheet id and the file (the keys), then the view
    assert got["R001"]["prompt"] == (
        f"Sheet model#01 of {REL}, view 'P-1': what size does the drawing give for K-1? Cite the entry ids."
    )
    assert got["R002"]["prompt"] == (
        "Sheet S-05: what number on the plan does the drawing give for P-1? Cite the entry ids."
    )
    assert got["R003"]["prompt"] == (
        f"Sheet model#01 of {REL}: what level does the drawing give for K-2? Cite the entry ids."
    )
    assert (got["R001"]["file"], got["R001"]["sheet"]) == (REL, "model#01")
    own["number_entry"] = ids["S-06"]  # the own sheet names its number: both parts of the place
    put_manifest(work, manifest)
    assert prompts()["R001"]["prompt"].startswith("Sheet S-06, view 'P-1': what size")
    own["number_entry"] = ids["K-2"]  # a font-blocked text is never quoted
    put_manifest(work, manifest)
    assert prompts()["R001"]["sheet_number"] is None


def test_location_text_that_gives_the_value_is_withheld(capsys, work):
    """A sheet number, view or subject that shares a number with the row's value, or holds its text (case
    ignored), is left out of the prompt and null in its keys; the others are quoted as before."""
    ids = entry_ids(work)
    manifest = part_manifest(work)
    own = next(p for p in manifest["parts"] if p["id"] == PART)["sheets"][0]
    own["number_entry"] = ids["26"]
    own["views"] = [{"heading_entry": ids[t]} for t in ("PLAN K-1 1500x2400", "FFL -1.200", "TYPE KB-9")]
    put_manifest(work, manifest)

    def at(row_id: str, key: str, **fields: Any) -> dict[str, Any]:
        return row(row_id, view={"heading_entry": ids[key]}, **fields)

    write_values(
        work,
        [
            at("R001", "PLAN K-1 1500x2400", field="size", value="1500x2400"),  # a number of the value
            at("R002", "FFL -1.200", mark="K-2", field="level", value="-1.200"),  # the text, no number
            at("R003", "TYPE KB-9", mark="K-2", field="material", value="kb-9"),  # the text, case ignored
            at("R004", "PLAN K-1 1500x2400", mark="K-3", field="size", value="900x900"),  # no relation
            row("R005", mark="P-1", field="count_plan", value="26"),  # the sheet number is the value
            row("R006", mark="<drop>", subject="grid S001 A-B", field="axes", value="A-B"),  # the subject
        ],
    )
    code, doc, err = sample(capsys, work)
    assert (code, err) == (0, "") and doc and validate("part-output", doc) == []
    got = {p["row"]: p for p in doc["prompts"]}
    place = f"Sheet model#01 of {REL}"
    assert [(got[r]["sheet_number"], got[r]["view"]) for r in sorted(got)] == [
        ("26", None), ("26", None), ("26", None), ("26", "PLAN K-1 1500x2400"), (None, None), ("26", None),
    ]  # fmt: skip
    assert got["R001"]["prompt"] == "Sheet 26: what size does the drawing give for K-1? Cite the entry ids."
    assert got["R002"]["prompt"] == "Sheet 26: what level does the drawing give for K-2? Cite the entry ids."
    assert (
        got["R003"]["prompt"] == "Sheet 26: what material does the drawing give for K-2? Cite the entry ids."
    )
    assert got["R004"]["prompt"] == (
        "Sheet 26, view 'PLAN K-1 1500x2400': what size does the drawing give for K-3? Cite the entry ids."
    )
    assert got["R005"]["prompt"] == (
        f"{place}: what number on the plan does the drawing give for P-1? Cite the entry ids."
    )
    # the subject is withheld too: the prompt names the field and the place only
    assert (got["R006"]["subject"], got["R006"]["mark"]) == (None, None)
    assert got["R006"]["prompt"] == "Sheet 26: what set of axes does the drawing give? Cite the entry ids."
    own_value = {"R001": "1500x2400", "R002": "-1.200", "R003": "kb-9", "R005": "26", "R006": "a-b"}
    for r, value in own_value.items():  # the value of a row is in no part of its prompt
        assert value not in got[r]["prompt"].casefold()


def test_outside_frame_matches_the_rows_file():
    """Entry ids repeat across files: a cluster of file B must not mark a row of file A."""
    stub = SimpleNamespace(cluster_entries={("b.dxf", "model#01", "left"): {"T000001", "T000002"}})
    outside = ps()._outside_frame
    cited = {"cites": {"entries": ["T000002", "T000009"]}}
    assert outside(stub, {"file": "b.dxf", **cited}) is True
    assert outside(stub, {"file": "a.dxf", **cited}) is False
    assert outside(stub, {"file": None, **cited}) is False
    assert outside(stub, {"file": "b.dxf", "cites": {"entries": ["T000009"]}}) is False
    assert outside(stub, {"file": "b.dxf", "cites": {}}) is False


def test_every_field_has_one_fixed_phrase():
    """The prompt names a field by one English phrase, not by the field id."""
    from tekla_harness.schemas import _load_all

    phrases = ps().FIELD_PHRASE
    enum = _load_all()[0]["part-values"]["$defs"]["row"]["properties"]["field"]["enum"]
    assert set(phrases) == set(enum) and len(set(phrases.values())) == len(enum)
    assert not any("_" in phrase for phrase in phrases.values())
    assert phrases["count_plan"] == "number on the plan"
    assert phrases["count_schedule"] == "number in the schedule"
    assert phrases["level_top"] == "top level"
