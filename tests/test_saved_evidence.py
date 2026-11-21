"""saved evidence: `--save` of `harness geometry` / `harness contents`, `finding add --kind measured`.

The world is the one of test_contents (caps, piles, marks on model#01). Every test works on a copy.
"""

from __future__ import annotations

import hashlib
import json
import shlex
import shutil
from pathlib import Path
from typing import Any

import pytest

from _callout_fixtures import PROPOSED_FONT_TABLE, REL, write_structure
from tekla_harness import contents as contents_module
from tekla_harness.cli import main
from tekla_harness.findings import FindingError, add_finding, list_findings
from tekla_harness.intake import run_intake
from tekla_harness.saved_evidence import file_name, redo_command
from tekla_harness.schemas import validate
from test_contents import CAP, PILE, build_dxf, grids_doc

CONTENTS_ARGS = ["--sheet", "model#01", "--outline-layer", CAP, "--circle-layer", PILE, "--marks", r"DC-\d+"]


@pytest.fixture(scope="module")
def world(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("saved-evidence")
    inp = build_dxf(root)
    work = root / "work"
    run_intake(inp, work, "demo-evidence", knowledge=PROPOSED_FONT_TABLE)
    write_structure(inp, work)
    (work / "structure" / f"{REL}.grids.json").write_text(json.dumps(grids_doc()), encoding="utf-8")
    return root


@pytest.fixture
def root(world, tmp_path) -> Path:
    target = tmp_path / "copy"
    shutil.copytree(world, target)
    return target


def run(capsys, root: Path, *argv: str) -> tuple[int, str, str]:
    code = main([argv[0], str(root / "work"), *argv[1:]])
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def inv_sha(root: Path) -> str:
    inv = json.loads((root / "work" / "inventory.json").read_text(encoding="utf-8"))
    return {r["path"]: r["sha256"] for r in inv["files"]}[REL]


def save_contents(capsys, root: Path, *extra: str) -> tuple[dict[str, Any], str]:
    code, out, err = run(
        capsys, root, "contents", REL, *CONTENTS_ARGS, "--input-dir", str(root / "input"), "--save", *extra
    )
    assert code == 0, err
    saved = next(line for line in err.splitlines() if line.startswith("saved: "))
    return json.loads(out), saved.removeprefix("saved: ")


def save_geometry(capsys, root: Path, *extra: str) -> tuple[dict[str, Any], str]:
    code, out, err = run(
        capsys, root, "geometry", REL, "--sheet", "model#01", "--detail",
        "--input-dir", str(root / "input"), "--save", *extra,
    )  # fmt: skip
    assert code == 0, err
    saved = next(line for line in err.splitlines() if line.startswith("saved: "))
    return json.loads(out), saved.removeprefix("saved: ")


def big_caps(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [o for o in doc["outlines"] if o["symbols"]]


# --- --save ---------------------------------------------------------------------------------------------


def test_contents_save_writes_the_stdout_document_byte_for_byte(root, capsys):
    code, out, err = run(
        capsys, root, "contents", REL, *CONTENTS_ARGS, "--input-dir", str(root / "input"), "--save"
    )
    assert code == 0
    doc = json.loads(out)
    rel = err.split("saved: ", 1)[1].splitlines()[0]
    saved = root / "work" / rel
    assert saved.read_bytes() == out.encode("utf-8")
    material = "\0".join(
        (
            REL,
            inv_sha(root),
            json.dumps(doc["query"], sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        )
    )
    qhash = hashlib.sha256(material.encode("utf-8")).hexdigest()[:8]
    chash = hashlib.sha256(saved.read_bytes()).hexdigest()[:8]
    assert rel == f"geometry/contents-model-01-{qhash}-{chash}.json"
    assert file_name("contents", doc, inv_sha(root), saved.read_bytes()) == Path(rel).name


def test_geometry_save_names_sheets_and_bbox(root, capsys):
    _, rel = save_geometry(capsys, root)
    assert rel.startswith("geometry/geometry-model-01-") and rel.endswith(".json")
    code, _, err = run(
        capsys, root, "geometry", REL, "--bbox", "0", "0", "100000", "100000",
        "--input-dir", str(root / "input"), "--save",
    )  # fmt: skip
    assert code == 0 and "saved: geometry/geometry-bbox-" in err
    code, _, err = run(capsys, root, "geometry", REL, "--input-dir", str(root / "input"), "--save")
    assert code == 0 and "saved: geometry/geometry-all-" in err


def test_same_query_same_file_a_different_query_another(root, capsys):
    _, first = save_contents(capsys, root)
    before = (root / "work" / first).read_bytes()
    _, again = save_contents(capsys, root)
    assert again == first and (root / "work" / first).read_bytes() == before
    _, other = save_contents(capsys, root, "--max-long", "9000")
    assert other != first
    assert sorted(p.name for p in (root / "work" / "geometry").iterdir()) == sorted(
        [Path(first).name, Path(other).name]
    )


def test_without_save_nothing_is_written(root, capsys):
    before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
    code, out, err = run(capsys, root, "contents", REL, *CONTENTS_ARGS, "--input-dir", str(root / "input"))
    assert code == 0 and "saved:" not in err and out
    assert sorted(p.relative_to(root).as_posix() for p in root.rglob("*")) == before


def test_a_failed_read_saves_nothing(root, capsys):
    code, out, _ = run(
        capsys, root, "contents", REL, "--sheet", "model#99", "--outline-layer", CAP,
        "--circle-layer", PILE, "--input-dir", str(root / "input"), "--save",
    )  # fmt: skip
    assert code == 2 and out == "" and not (root / "work" / "geometry").exists()


# --- finding add --kind measured --------------------------------------------------------------------------


def measured(root: Path, source: str, items: list[str], **kw: Any) -> dict[str, str]:
    kw.setdefault("kind", "measured")
    kw.setdefault("file", REL)
    kw.setdefault("entries", [])
    kw.setdefault("value", "the pile caps of the sheet")
    return add_finding(root / "work", source=source, items=items, **kw)


def refused(root: Path, code: int, source: str, items: list[str], **kw: Any) -> str:
    path = root / "work" / "reader-findings.json"
    before = path.read_bytes() if path.exists() else None
    with pytest.raises(FindingError) as err:
        measured(root, source, items, **kw)
    assert err.value.exit_code == code, str(err.value)
    assert (path.read_bytes() if path.exists() else None) == before
    return str(err.value)


def findings(root: Path) -> list[dict[str, Any]]:
    return json.loads((root / "work" / "reader-findings.json").read_text(encoding="utf-8"))["findings"]


def test_a_measured_finding_records_the_evidence(root, capsys):
    doc, rel = save_contents(capsys, root)
    ids = [o["id"] for o in big_caps(doc)[:2]]
    assert measured(root, rel, ids, sheet="model#01", fields=["quantity=count"]) == {
        "id": "F-001",
        "status": "new",
    }
    stored = json.loads((root / "work" / "reader-findings.json").read_text(encoding="utf-8"))
    assert validate("reader-findings", stored) == []
    f = stored["findings"][0]
    assert f["kind"] == "measured" and f["entries"] == [] and f["decoded_by"] == []
    assert f["confidence"] == "medium" and f["fields"] == {"quantity": "count"} and f["sheet"] == "model#01"
    sha = hashlib.sha256((root / "work" / rel).read_bytes()).hexdigest()
    caps = {o["id"]: o for o in doc["outlines"]}
    assert f["evidence"] == {
        "source": rel,
        "sha256": sha,
        "command": "contents",
        "query": doc["query"],
        "items": [
            {
                k: caps[i][k]
                for k in ("id", "layer", "short", "long", "centre", "symbols", "invisible", "marks", "axes")
            }
            for i in ids
        ],
    }


def test_a_geometry_document_is_a_source_too(root, capsys):
    doc, rel = save_geometry(capsys, root)
    ids = [i["id"] for i in doc["regions"][0]["items"] if i["kind"] == "outline"][:1]
    assert ids
    measured(root, rel, ids, sheet="model#01", fields=["quantity=size"])
    assert findings(root)[0]["evidence"]["command"] == "geometry"


def test_confidence_can_only_be_lowered(root, capsys):
    doc, rel = save_contents(capsys, root)
    ids = [big_caps(doc)[0]["id"]]
    measured(root, rel, ids, confidence="low")
    assert findings(root)[0]["confidence"] == "low"
    assert "high" in refused(root, 2, rel, ids, confidence="high", value="other")


def test_entries_are_optional_but_checked_when_given(root, capsys):
    doc, rel = save_contents(capsys, root)
    ids = [big_caps(doc)[0]["id"]]
    index = json.loads((root / "work" / "text" / f"{REL}.json").read_text(encoding="utf-8"))
    entry = next(e for e in index["entries"] if e["confidence"] != "low")
    refused(root, 1, rel, ids, entries=["T999999"])

    def set_entry_confidence(value: str) -> None:
        for e in index["entries"]:
            if e["id"] == entry["id"]:
                e["confidence"] = value
        (root / "work" / "text" / f"{REL}.json").write_text(
            json.dumps(index, ensure_ascii=False), encoding="utf-8"
        )

    assert measured(root, rel, ids)["id"] == "F-001"  # no entry: medium
    assert findings(root)[0]["confidence"] == "medium" and findings(root)[0]["entries"] == []
    # an entry that backs no claim cannot lift the finding to high: its level, capped at medium
    for n, level in enumerate(("high", "medium", "low"), start=2):
        set_entry_confidence(level)
        measured(root, rel, ids, entries=[entry["id"]], value=f"value {level}")
        f = findings(root)[n - 1]
        assert [e["id"] for e in f["entries"]] == [entry["id"]]
        assert f["confidence"] == ("medium" if level == "high" else level)
    set_entry_confidence("high")
    measured(root, rel, ids, entries=[entry["id"]], value="lowered", confidence="medium")
    assert findings(root)[4]["confidence"] == "medium"
    assert "medium" in refused(root, 2, rel, ids, entries=[entry["id"]], value="raised", confidence="high")
    assert validate("reader-findings", json.loads((root / "work" / "reader-findings.json").read_text())) == []


def test_an_entry_that_backs_every_claim_gives_a_high_measured_finding(root, capsys):
    doc, rel = save_contents(capsys, root)
    ids = caps_with(doc, 2)[:2]
    n = len(ids)
    path = root / "work" / "text" / f"{REL}.json"
    index = json.loads(path.read_text(encoding="utf-8"))
    entry = next(e for e in index["entries"] if e["confidence"] != "low")
    entry["confidence"] = "high"
    entry["display_text"] = f"{n} piles"
    path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    claims = [f"count={n}"]
    measured(root, rel, ids, entries=[entry["id"]], claims=claims, value=f"{n} piles")
    assert findings(root)[0]["confidence"] == "high"
    # a claim no cited entry shows keeps it at medium (no error), as does having no claim at all
    measured(root, rel, ids, entries=[entry["id"]], claims=[f"count={n}", "short=1700"], value="1700 wide")
    assert findings(root)[1]["confidence"] == "medium"
    measured(root, rel, ids, entries=[entry["id"]], value="no claim")
    assert findings(root)[2]["confidence"] == "medium"
    # --confidence still only lowers
    measured(root, rel, ids, entries=[entry["id"]], claims=claims, value="lowered", confidence="low")
    assert findings(root)[3]["confidence"] == "low"


# --- numbers of --value must be backed ---------------------------------------------------------------


def test_a_number_of_the_value_with_no_claim_is_refused(root, capsys):
    doc, rel = save_contents(capsys, root)
    ids = caps_with(doc, 2)[:2]
    msg = refused(root, 1, rel, ids, value="9 piles d500", claims=["count=2"])
    assert "9" in msg and "500" in msg
    msg = refused(root, 1, rel, ids, value="2 piles d500", claims=["count=2"])  # d500 is the number 500
    assert "500" in msg and "9" not in msg
    assert "46" in refused(root, 1, rel, ids, value="46 piles")  # no claim at all
    assert measured(root, rel, ids, value="2 piles", claims=["count=2"])["status"] == "new"


def test_numbers_glued_to_a_letter_hash_or_hyphen_are_not_measurements(root, capsys):
    doc, rel = save_contents(capsys, root)
    ids = caps_with(doc, 2)[:2]
    for n, text in enumerate(("DC-1 x2", "DC-1 2 piles", "model#06 C30 A-3 KC-B1-09 2 piles"), start=1):
        assert measured(root, rel, ids, value=text, claims=["count=2"])["id"] == f"F-00{n}"
    refused(root, 1, rel, ids, value="DC-1 3 piles", claims=["count=2"])


def test_a_size_value_needs_both_numbers_backed(root, capsys):
    doc, rel = save_contents(capsys, root)
    a, b = caps_with(doc, 2)
    assert "3200" in refused(root, 1, rel, [a], value="1700x3200", claims=["short=1700"])
    assert "3200" in refused(root, 1, rel, [a], value="1700\u00d73200", claims=["short=1700"])
    assert "1700" in refused(root, 1, rel, [a], value="1700x3200", claims=["symbols=2"])
    ok = measured(root, rel, [a, b], value="1700x1700", claims=["short=1700", "long=1699.5"])
    assert ok["status"] == "new"
    assert measured(root, rel, [a, b], value="1701x1700", claims=["short=1700", "long=1699.5"])["id"]
    refused(root, 1, rel, [a, b], value="1702x1700", claims=["short=1700", "long=1699.5"])  # tol 1.0


def test_a_number_of_a_cited_entry_backs_the_value(root, capsys):
    doc, rel = save_contents(capsys, root)
    ids = caps_with(doc, 2)[:2]
    path = root / "work" / "text" / f"{REL}.json"
    index = json.loads(path.read_text(encoding="utf-8"))
    entry = next(e for e in index["entries"] if e["confidence"] != "low")
    entry["display_text"] = "pile d450 schedule"
    path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    assert measured(root, rel, ids, entries=[entry["id"]], value="piles d450")["status"] == "new"
    assert "451" in refused(root, 1, rel, ids, entries=[entry["id"]], value="piles d451")


def test_the_source_must_be_a_saved_document_of_the_file(root, capsys):
    doc, rel = save_contents(capsys, root)
    ids = [big_caps(doc)[0]["id"]]
    work = root / "work"
    assert "exist" in refused(root, 1, "geometry/contents-model-01-000000000000.json", ids)
    assert "geometry/" in refused(root, 2, "inventory.json", ids)
    assert "geometry/" in refused(root, 2, "geometry/../inventory.json", ids)
    assert "geometry/" in refused(root, 2, str((work / rel).resolve()), ids)
    bad = work / "geometry" / "contents-model-01-aaaaaaaaaaaa.json"
    bad.write_text("{not json", encoding="utf-8")
    assert "JSON" in refused(root, 1, "geometry/" + bad.name, ids)
    other = json.loads((work / rel).read_text(encoding="utf-8"))
    other["file"] = "plans/other.dxf"
    (work / "geometry" / "contents-model-01-bbbbbbbbbbbb.json").write_text(
        json.dumps(other), encoding="utf-8"
    )
    assert "its file is 'plans/other.dxf'" in refused(
        root, 1, "geometry/contents-model-01-bbbbbbbbbbbb.json", ids
    )
    wrong_kind = json.loads((work / rel).read_text(encoding="utf-8"))
    wrong_kind["kind"] = "dimensions"
    (work / "geometry" / "contents-model-01-cccccccccccc.json").write_text(
        json.dumps(wrong_kind), encoding="utf-8"
    )
    assert "geometry or contents" in refused(root, 1, "geometry/contents-model-01-cccccccccccc.json", ids)


def test_items_must_exist_in_the_document(root, capsys):
    doc, rel = save_contents(capsys, root)
    ids = [big_caps(doc)[0]["id"]]
    assert "G-0123456789" in refused(root, 1, rel, [*ids, "G-0123456789"])
    assert "twice" in refused(root, 2, rel, ids + ids)
    assert "--items" in refused(root, 2, rel, [])
    assert "G-" in refused(root, 2, rel, ["xyz"])
    code, _, err = run(
        capsys, root, "geometry", REL, "--sheet", "model#01", "--input-dir", str(root / "input"), "--save"
    )
    assert code == 0
    plain = err.split("saved: ", 1)[1].splitlines()[0]  # no --detail: the document lists no item ids
    assert "--detail" in refused(root, 1, plain, ["G-0123456789"])


def test_the_sheet_must_be_covered_by_the_query(root, capsys):
    doc, rel = save_contents(capsys, root)
    ids = [big_caps(doc)[0]["id"]]
    assert "model#02" in refused(root, 1, rel, ids, sheet="model#02")
    measured(root, rel, ids, sheet="model#01")


def test_a_document_saved_before_the_drawing_changed_is_refused(root, capsys):
    doc, rel = save_contents(capsys, root)
    ids = [big_caps(doc)[0]["id"]]
    path = root / "work" / "inventory.json"
    inventory = json.loads(path.read_text(encoding="utf-8"))
    for row in inventory["files"]:
        if row["path"] == REL:
            row["sha256"] = "0" * 64
    path.write_text(json.dumps(inventory), encoding="utf-8")
    assert "saved" in refused(root, 1, rel, ids)


def test_field_quantity_is_checked_and_evidence_flags_are_for_two_kinds(root, capsys):
    doc, rel = save_contents(capsys, root)
    ids = [big_caps(doc)[0]["id"]]
    assert "quantity" in refused(root, 2, rel, ids, fields=["quantity=weight"])
    with pytest.raises(FindingError) as err:
        add_finding(
            root / "work", kind="sheet_class", file=REL, sheet="model#01", entries=["T000001"], value="other",
            source=rel, items=ids,
        )  # fmt: skip
    assert err.value.exit_code == 2
    with pytest.raises(FindingError) as err:  # measured needs the source
        add_finding(root / "work", kind="measured", file=REL, entries=[], value="x")
    assert err.value.exit_code == 2


def test_the_same_measurement_is_recorded_once(root, capsys):
    doc, rel = save_contents(capsys, root)
    a, b = (o["id"] for o in big_caps(doc)[:2])
    assert measured(root, rel, [a])["status"] == "new"
    assert measured(root, rel, [a]) == {"id": "F-001", "status": "already_recorded"}
    assert measured(root, rel, [b]) == {"id": "F-002", "status": "new"}


def test_cross_check_with_one_entry_and_evidence(root, capsys):
    doc, rel = save_contents(capsys, root)
    ids = [big_caps(doc)[0]["id"]]
    index = json.loads((root / "work" / "text" / f"{REL}.json").read_text(encoding="utf-8"))
    one = index["entries"][0]["id"]
    kw: dict[str, Any] = {"kind": "cross_check", "entries": [one], "value": "schedule says 60, count is 58"}
    with pytest.raises(FindingError) as err:  # without evidence two entries are still needed
        add_finding(root / "work", file=REL, questions=["Q-001"], **kw)
    assert err.value.exit_code == 2 and "two entries" in str(err.value)
    with pytest.raises(FindingError) as err:
        add_finding(root / "work", file=REL, source=rel, items=ids, **kw)  # no --question
    assert err.value.exit_code == 2
    result = add_finding(root / "work", file=REL, source=rel, items=ids, questions=["Q-001"], **kw)
    assert result["status"] == "new"
    f = findings(root)[0]
    assert f["kind"] == "cross_check" and [i["id"] for i in f["evidence"]["items"]] == ids
    assert len(f["entries"]) == 1


def test_list_shows_the_evidence_and_marks_a_changed_source_stale(root, capsys):
    doc, rel = save_contents(capsys, root)
    ids = [big_caps(doc)[0]["id"]]
    measured(root, rel, ids)
    listed = list_findings(root / "work")
    f = listed["findings"][0]
    assert f["evidence"]["source"] == rel and [i["id"] for i in f["evidence"]["items"]] == ids
    assert f["stale"] is False and f["stale_reasons"] == [] and "redo" not in f
    path = root / "work" / rel
    path.write_bytes(path.read_bytes() + b" ")
    assert list_findings(root / "work")["findings"][0]["stale"] is True
    path.unlink()
    assert list_findings(root / "work")["findings"][0]["stale"] is True


def test_cli_add_and_list(root, capsys):
    doc, rel = save_contents(capsys, root)
    a, b = (o["id"] for o in big_caps(doc)[:2])
    work = str(root / "work")
    code = main(["finding", "add", work, "--kind", "measured", "--file", REL, "--sheet", "model#01",
                 "--source", rel, "--items", f"{a},{b}", "--value", "2 piles",
                 "--claim", "count=2", "--field", "quantity=count"])  # fmt: skip
    cap = capsys.readouterr()
    assert code == 0 and json.loads(cap.out) == {"id": "F-001", "status": "new"}
    code = main(["finding", "list", work, "--kind", "measured"])
    listed = json.loads(capsys.readouterr().out)
    assert code == 0 and [i["id"] for i in listed["findings"][0]["evidence"]["items"]] == [a, b]
    # a text kind still needs --entries
    code = main(["finding", "add", work, "--kind", "note_item", "--file", REL, "--value", "x",
                 "--field", "topic=other"])  # fmt: skip
    assert code == 2 and "--entries" in capsys.readouterr().err


def test_questions_md_still_runs_with_a_measured_finding(root, capsys):
    doc, rel = save_contents(capsys, root)
    measured(root, rel, [big_caps(doc)[0]["id"]])
    code, _, err = run(capsys, root, "questions-md")
    assert code == 0, err


# --- T24 review 1: claims, snapshots, sheets, immutable files, stale reasons --------------------------------


def plant(root: Path, doc: dict[str, Any]) -> str:
    """Write `doc` as `--save` would (its right name for the drawing's current sha), return the rel path."""
    data = (json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    name = file_name(str(doc["kind"]), doc, inv_sha(root), data)
    path = root / "work" / "geometry" / name
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(data)
    return f"geometry/{name}"


def caps_with(doc: dict[str, Any], symbols: int, short: float = 1700.0) -> list[str]:
    return [o["id"] for o in doc["outlines"] if o["symbols"] == symbols and o["short"] == short]


def two_sheet_geometry(capsys, root: Path) -> tuple[dict[str, Any], str]:
    code, out, err = run(
        capsys, root, "geometry", REL, "--sheet", "model#01", "model#02", "--detail",
        "--input-dir", str(root / "input"), "--save",
    )  # fmt: skip
    assert code == 0, err
    saved = next(ln for ln in err.splitlines() if ln.startswith("saved: "))
    return json.loads(out), saved.removeprefix("saved: ")


def test_a_claim_must_hold_for_every_cited_item(root, capsys):
    """M1: the '9 piles' of the review (the cap holds 2 here) is refused, naming the item and the field."""
    doc, rel = save_contents(capsys, root)
    a, b = caps_with(doc, 2)
    c = caps_with(doc, 1)[0]
    msg = refused(root, 1, rel, [a], claims=["symbols=9"])
    assert a in msg and "symbols" in msg and "9" in msg
    assert c in refused(root, 1, rel, [a, c], claims=["symbols=2"])  # the second item disagrees
    assert "symbols" in refused(root, 1, rel, [a], claims=["symbols=3"])  # exact, never within tol
    assert "count" in refused(root, 1, rel, [a, b], claims=["count=3"])
    assert "short" in refused(root, 1, rel, [a], claims=["short=1698"])  # tol is 1.0
    assert "long" in refused(root, 1, rel, [a], claims=["short=1700", "long=3200"])


def test_a_diameter_claim_needs_a_diameter_the_items_have(root, capsys):
    doc, rel = save_contents(capsys, root)
    a = caps_with(doc, 2)[0]
    assert "no diameter" in refused(root, 1, rel, [a], claims=["diameter=300"])
    g, grel = two_sheet_geometry(capsys, root)
    circle = next(i for i in g["regions"][0]["items"] if i["kind"] == "circle" and i["diameter"] == 300.0)
    assert "diameter" in refused(root, 1, grel, [circle["id"]], claims=["diameter=228"])
    assert "no symbols" in refused(root, 1, grel, [circle["id"]], claims=["symbols=1"])
    assert measured(root, grel, [circle["id"]], claims=["diameter=300"])["status"] == "new"


def test_claims_within_tol_and_exact_counts_are_recorded(root, capsys):
    doc, rel = save_contents(capsys, root)
    a, b = caps_with(doc, 2)
    done = measured(root, rel, [a, b], claims=["symbols=2", "short=1700", "long=1699.5", "count=2"])
    assert done == {"id": "F-001", "status": "new"}
    snaps = findings(root)[0]["evidence"]["items"]
    assert [i["id"] for i in snaps] == [a, b] and all(i["symbols"] == 2 for i in snaps)


def test_claim_usage_errors_exit_2(root, capsys):
    doc, rel = save_contents(capsys, root)
    a = caps_with(doc, 2)[0]
    for bad in (
        "weight=1",
        "symbols=2.5",
        "short=abc",
        "symbols=-1",
        "short=nan",
        "short=inf",
        "short",
        "count=",
    ):
        refused(root, 2, rel, [a], claims=[bad])
    assert "twice" in refused(root, 2, rel, [a], claims=["symbols=2", "symbols=2"])
    with pytest.raises(FindingError) as err:  # a claim needs the items it is checked against
        add_finding(root / "work", kind="note_item", file=REL, entries=["T000001"], value="x",
                    fields=["topic=other"], claims=["symbols=2"])  # fmt: skip
    assert err.value.exit_code == 2 and "--claim" in str(err.value)
    work = str(root / "work")
    argv = ["finding", "add", work, "--kind", "measured", "--file", REL, "--source", rel, "--items", a,
            "--value", "2 piles"]  # fmt: skip
    assert main([*argv, "--claim", "symbols=9"]) == 1
    assert "symbols" in capsys.readouterr().err
    assert not (root / "work" / "reader-findings.json").exists()
    assert main([*argv, "--claim", "symbols=2", "--claim", "short=1700"]) == 0
    assert "F-001" in capsys.readouterr().out


def test_evidence_items_are_snapshots_of_the_measured_fields(root, capsys):
    g, grel = two_sheet_geometry(capsys, root)
    items = g["regions"][1]["items"]
    circle = next(i for i in items if i["kind"] == "circle")
    outline = next(i for i in items if i["kind"] == "outline" and i["short"] == 1700.0)
    measured(root, grel, [circle["id"], outline["id"]], sheet="model#02")
    snaps = findings(root)[0]["evidence"]["items"]
    assert snaps[0] == {
        "id": circle["id"], "kind": "circle", "layer": circle["layer"], "sheet": "model#02",
        "space": circle["space"], "centre": circle["centre"], "diameter": circle["diameter"],
        "invisible": False,
    }  # fmt: skip
    assert snaps[1]["short"] == 1700.0 and "diameter" not in snaps[1] and "bbox" not in snaps[1]
    assert validate("reader-findings", json.loads((root / "work" / "reader-findings.json").read_text())) == []


def test_an_item_of_another_sheet_is_refused(root, capsys):
    """M3: the item sits on model#01 although the finding says model#02 (and the document covers both)."""
    g, grel = two_sheet_geometry(capsys, root)
    on1 = g["regions"][0]["items"][0]["id"]
    on2 = next(i["id"] for i in g["regions"][1]["items"] if i["kind"] == "outline")
    msg = refused(root, 1, grel, [on2, on1], sheet="model#02")
    assert on1 in msg and "model#01" in msg and "not on sheet model#02" in msg and on2 not in msg
    assert measured(root, grel, [on2], sheet="model#02")["status"] == "new"
    measured(root, grel, [on1, on2], value="no sheet given, no check")  # sheet None: not checked
    nosheet = json.loads(json.dumps(g))
    nosheet["regions"][1]["items"][0]["sheet"] = None  # a centre on no sheet frame
    rel = plant(root, nosheet)
    assert "no sheet" in refused(root, 1, rel, [nosheet["regions"][1]["items"][0]["id"]], sheet="model#02")


def test_the_query_must_cover_the_sheet(root, capsys):
    """`_covers` (mutants M04, M05): a sheet list without the sheet, a bbox query, a query for all sheets."""
    inp = ["--input-dir", str(root / "input")]
    code, out, err = run(capsys, root, "geometry", REL, "--sheet", "model#01", "--detail", *inp, "--save")
    assert code == 0, err
    doc, rel = json.loads(out), err.split("saved: ", 1)[1].splitlines()[0]
    item = doc["regions"][0]["items"][0]["id"]
    assert "does not cover sheet model#02" in refused(root, 1, rel, [item], sheet="model#02")
    code, out, err = run(
        capsys, root, "geometry", REL, "--bbox", "0", "0", "100000", "100000", "--detail", *inp, "--save"
    )
    assert code == 0, err
    box_rel = err.split("saved: ", 1)[1].splitlines()[0]
    box_item = json.loads(out)["regions"][0]["items"][0]["id"]
    assert "does not cover sheet model#01" in refused(root, 1, box_rel, [box_item], sheet="model#01")
    code, out, err = run(capsys, root, "geometry", REL, "--detail", *inp, "--save")
    assert code == 0, err
    everything = json.loads(out)
    all_rel = err.split("saved: ", 1)[1].splitlines()[0]
    one = next(i["id"] for r in everything["regions"] if r["sheet"] == "model#02" for i in r["items"])
    assert measured(root, all_rel, [one], sheet="model#02")["status"] == "new"


def test_a_source_that_fails_its_schema_is_refused(root, capsys):
    """M07: a document of the right name that does not validate is refused, not crashed on."""
    doc, _ = save_contents(capsys, root)
    broken = json.loads(json.dumps(doc))
    del broken["outlines"]
    rel = plant(root, broken)
    assert "invalid" in refused(root, 1, rel, ["G-0123456789"])


def test_evidence_flags_are_refused_on_other_kinds_with_usage(root, capsys):
    """M19: the refusal is the usage check (exit 2), not the schema check at write time."""
    doc, rel = save_contents(capsys, root)
    ids = caps_with(doc, 2)[:1]
    index = json.loads((root / "work" / "text" / f"{REL}.json").read_text(encoding="utf-8"))
    entry = index["entries"][0]["id"]
    for kind, extra in (("note_item", ["topic=other"]), ("structural_system", ["aspect=floors"])):
        with pytest.raises(FindingError) as err:
            add_finding(root / "work", kind=kind, file=REL, entries=[entry], value="x", fields=extra,
                        source=rel, items=ids)  # fmt: skip
        assert err.value.exit_code == 2 and "--source and --items are for kinds" in str(err.value)
    assert not (root / "work" / "reader-findings.json").exists()


def test_slug_of_several_sheets_joins_with_plus(root, capsys):
    base = {"file": REL, "query": {"sheet": ["model#05", "model#06"], "bbox": None}}
    assert file_name("geometry", base, "0" * 64, b"x").startswith("geometry-model-05+model-06-")
    _, rel = two_sheet_geometry(capsys, root)
    assert rel.startswith("geometry/geometry-model-01+model-02-")


def test_two_drawings_with_the_same_bytes_get_two_names():
    """m2: the query holds no file, so the name hashes the path."""
    query = {"sheet": ["model#01"], "bbox": None, "layer": None, "detail": True, "max": None, "tol": 1.0}
    a = file_name("geometry", {"file": "plans/A.dwg", "query": query}, "1" * 64, b"x")
    b = file_name("geometry", {"file": "plans/B.dwg", "query": query}, "1" * 64, b"x")
    assert a != b and a.split("-")[-2] != b.split("-")[-2]
    assert file_name("geometry", {"file": "plans/A.dwg", "query": query}, "2" * 64, b"x") != a
    assert file_name("geometry", {"file": "plans/A.dwg", "query": query}, "1" * 64, b"y") != a


def test_a_resave_with_new_bytes_writes_a_new_file_and_keeps_the_cited_one(root, capsys, monkeypatch):
    """M2: the tool changes (one warning sentence), the query and the drawing do not."""
    doc, rel = save_contents(capsys, root)
    a = caps_with(doc, 2)[0]
    measured(root, rel, [a])
    old_bytes = (root / "work" / rel).read_bytes()
    real = contents_module.contents

    def reworded(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = real(*args, **kwargs)
        result["warnings"].append("a sentence the next tool version prints")
        return result

    monkeypatch.setattr(contents_module, "contents", reworded)
    _, rel2 = save_contents(capsys, root)
    assert rel2 != rel and (root / "work" / rel).read_bytes() == old_bytes
    f = list_findings(root / "work")["findings"][0]
    assert f["stale"] is False and f["stale_reasons"] == [] and f["evidence"]["source"] == rel
    assert measured(root, rel2, [a])["id"] == "F-002"  # the new file is citable too, as another finding
    _, rel3 = save_contents(capsys, root)  # the same bytes again: the same file
    assert rel3 == rel2


def test_the_same_bytes_again_write_nothing(root, capsys):
    _, rel = save_contents(capsys, root)
    path = root / "work" / rel
    before = (path.stat().st_mtime_ns, sorted(p.name for p in path.parent.iterdir()))
    _, again = save_contents(capsys, root)
    assert again == rel and (path.stat().st_mtime_ns, sorted(p.name for p in path.parent.iterdir())) == before


def test_a_file_under_the_name_with_other_bytes_is_never_overwritten(root, capsys):
    _, rel = save_contents(capsys, root)
    path = root / "work" / rel
    path.write_bytes(path.read_bytes() + b" ")  # hand edit, the name stays
    edited = path.read_bytes()
    args = ["contents", REL, *CONTENTS_ARGS, "--input-dir", str(root / "input"), "--save"]
    code, out, err = run(capsys, root, *args)
    assert code == 1 and out == "" and "never overwritten" in err
    assert path.read_bytes() == edited


def test_a_hand_edited_source_is_refused(root, capsys):
    """m1: `symbols` edited in the saved file, the name unchanged."""
    doc, rel = save_contents(capsys, root)
    a = caps_with(doc, 2)[0]
    path = root / "work" / rel
    text = path.read_text(encoding="utf-8").replace('"symbols": 2', '"symbols": 5', 1)
    path.write_text(text, encoding="utf-8")
    msg = refused(root, 1, rel, [a], claims=["symbols=5"])
    assert "changed after it was saved" in msg and "harness contents" in msg and "--save" in msg


def test_a_document_under_another_name_is_refused(root, capsys):
    doc, rel = save_contents(capsys, root)
    a = caps_with(doc, 2)[0]
    other = (
        root / "work" / "geometry" / rel.split("/")[1].replace("contents-model-01-", "contents-model-01-ff")
    )
    other.write_bytes((root / "work" / rel).read_bytes())  # right bytes, a name that is not its own
    assert "not saved for this version" in refused(root, 1, "geometry/" + other.name, [a])


def test_the_inventory_changing_during_the_run_saves_nothing(root, capsys, monkeypatch):
    real = contents_module.contents

    def reintaken(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = real(*args, **kwargs)
        path = root / "work" / "inventory.json"
        inventory = json.loads(path.read_text(encoding="utf-8"))
        for row in inventory["files"]:
            if row["path"] == REL:
                row["sha256"] = "0" * 64
        path.write_text(json.dumps(inventory), encoding="utf-8")
        return result

    monkeypatch.setattr(contents_module, "contents", reintaken)
    args = ["contents", REL, *CONTENTS_ARGS, "--input-dir", str(root / "input"), "--save"]
    code, out, err = run(capsys, root, *args)
    assert code == 1 and out == "" and "changed while" in err
    assert not (root / "work" / "geometry").exists()


def test_a_write_error_is_an_environment_error(root, capsys):
    (root / "work" / "geometry").write_text("not a folder", encoding="utf-8")
    args = ["contents", REL, *CONTENTS_ARGS, "--input-dir", str(root / "input"), "--save"]
    code, out, err = run(capsys, root, *args)
    assert code == 3 and out == "" and "cannot write" in err


def test_stale_reasons_say_why_and_how_to_redo(root, capsys):
    doc, rel = save_contents(capsys, root)
    a = caps_with(doc, 2)[0]
    measured(root, rel, [a], sheet="model#01")
    work = root / "work"

    def only() -> dict[str, Any]:
        f = list_findings(work)["findings"][0]
        assert f["stale"] is bool(f["stale_reasons"])  # one flag, one explanation
        return f

    assert only()["stale_reasons"] == [] and "redo" not in only()
    path = work / rel
    good = path.read_bytes()
    path.write_bytes(good + b" ")
    f = only()
    assert [r["reason"] for r in f["stale_reasons"]] == ["evidence_changed"]
    assert rel in f["stale_reasons"][0]["detail"]
    assert f["redo"].startswith("harness contents ") and "--sheet 'model#01'" in f["redo"]
    assert f["redo"].count("--save") == 1
    path.unlink()
    assert [r["reason"] for r in only()["stale_reasons"]] == ["evidence_missing"]
    path.write_bytes(good)
    inv_path = work / "inventory.json"
    inventory = json.loads(inv_path.read_text(encoding="utf-8"))
    for row in inventory["files"]:
        if row["path"] == REL:
            row["sha256"] = "f" * 64
    inv_path.write_text(json.dumps(inventory), encoding="utf-8")
    f = only()
    assert [r["reason"] for r in f["stale_reasons"]] == ["drawing_changed"]
    assert (
        "re-intaken" in f["stale_reasons"][0]["detail"] and "ffffffffffff" in f["stale_reasons"][0]["detail"]
    )
    assert "harness contents" in f["redo"]
    inventory["files"] = [r for r in inventory["files"] if r["path"] != REL]
    inv_path.write_text(json.dumps(inventory), encoding="utf-8")
    assert "no longer in the inventory" in only()["stale_reasons"][0]["detail"]


@pytest.mark.parametrize(
    "argv",
    [
        [
            "contents",
            REL,
            *CONTENTS_ARGS,
            "--detail",
            "--max",
            "50",
            "--max-long",
            "9000.5",
            "--mark-radius",
            "2500",
        ],
        ["contents", REL, *CONTENTS_ARGS, "--dims"],
        ["geometry", REL, "--sheet", "model#01", "model#02", "--layer", CAP, PILE, "--detail", "--max", "30"],
        ["geometry", REL, "--bbox", "0", "0", "100000.5", "100000", "--tol", "2"],
        ["geometry", REL],
    ],
)
def test_the_redo_command_saves_the_same_query_again(root, capsys, argv):
    inp = ["--input-dir", str(root / "input")]
    code, out, err = run(capsys, root, *argv, *inp, "--save")
    assert code == 0, err
    rel = err.split("saved: ", 1)[1].splitlines()[0]
    doc = json.loads(out)
    command = redo_command(root / "work", doc["kind"], REL, doc["query"])
    parts = [p for p in shlex.split(command) if p not in ("harness", "[--input-dir", "DIR]")]
    assert parts[0] == doc["kind"] and parts[1] == str(root / "work")
    code = main([*parts, *inp])
    err = capsys.readouterr().err
    assert code == 0 and f"saved: {rel}" in err


# --- schema ---------------------------------------------------------------------------------------------


def _measured_example(example) -> dict[str, Any]:
    d = example("reader-findings")
    return next(f for f in d["findings"] if f["kind"] == "measured")


def test_the_example_holds_a_measured_finding(example):
    assert _measured_example(example)["entries"] == []
    assert validate("reader-findings", example("reader-findings")) == []


def _entries_of(example) -> list[Any]:
    return next(f for f in example("reader-findings")["findings"] if f["kind"] == "note_item")["entries"]


def test_schema_rules_of_evidence(example):
    def problems(mutate) -> list[Any]:
        d = example("reader-findings")
        mutate(next(f for f in d["findings"] if f["kind"] == "measured"))
        return validate("reader-findings", d)

    assert problems(lambda f: f.pop("evidence"))
    assert problems(lambda f: f["evidence"].update(items=[]))
    assert problems(lambda f: f["evidence"].update(items=["x"]))
    assert problems(lambda f: f["evidence"].update(command="dimensions"))
    assert problems(lambda f: f["evidence"].update(source="inventory.json"))
    assert problems(lambda f: f["evidence"].update(sha256="x"))
    assert problems(lambda f: f["fields"].update(quantity="weight"))
    assert problems(lambda f: f.update(confidence="high"))  # high needs at least one entry
    assert problems(lambda f: f.update(confidence="high", entries=_entries_of(example))) == []
    assert problems(lambda f: f.update(confidence="certain"))

    def text_with_evidence(d: dict[str, Any]) -> None:
        d["kind"] = "note_item"
        d["fields"] = {"topic": "other"}

    assert problems(text_with_evidence)  # evidence only on measured and cross_check

    d = example("reader-findings")
    next(f for f in d["findings"] if f["kind"] == "note_item")["confidence"] = "high"
    assert validate("reader-findings", d)  # only a measured finding may be high
    d = example("reader-findings")
    note = next(f for f in d["findings"] if f["kind"] == "note_item")
    note["entries"] = []
    assert validate("reader-findings", d)  # empty entries only for measured
    d = example("reader-findings")
    cross = next(f for f in d["findings"] if f["kind"] == "cross_check")
    cross["entries"] = cross["entries"][:1]
    assert validate("reader-findings", d)  # one entry needs the evidence
    cross["evidence"] = _measured_example(example)["evidence"]
    assert validate("reader-findings", d) == []
