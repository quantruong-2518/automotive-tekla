"""`harness part answer-key` and `harness part score` (E9b, C11): record the engineer's verdict on a sampled
row under a key that survives a reread, and score a work folder against it.

The work folder is the real intake of `_part_fixtures.build_part_work`. Each test copies it, writes the rows
it needs, locks B1-piles and B1-caps, samples them with the real `part spotcheck` and runs the real commands.
"""

from __future__ import annotations

import json
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Any

import pytest

from _part_fixtures import INPUT_PART, MANIFEST, PART, REL, build_part_work, row, write_values
from conftest import EXAMPLES
from tekla_harness.cli import LOCKED_ACTIONS, main
from tekla_harness.schemas import validate
from test_part_receipts import h, lock, rec, write_receipts
from test_part_spotcheck import add_findings

# row number -> (mark, field, value): seven keys; the numbers are the row ids R001 to R007
KEYS = {
    1: ("K-1", "size", "1500x2400"),
    2: ("K-1", "thickness", "800"),
    3: ("K-2", "depth", "400"),
    4: ("K-2", "level", "-1.200"),
    5: ("K-2", "size", "900x900"),
    6: ("K-3", "size", "700x700"),
    7: ("K-4", "size", "600x600"),
}
AT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


@pytest.fixture(scope="module")
def base_work(tmp_path_factory) -> Path:
    return build_part_work(tmp_path_factory.mktemp("partscore"))


@pytest.fixture
def work(base_work, tmp_path) -> Path:
    target = tmp_path / "work"
    shutil.copytree(base_work, target)
    return target


def key_rows(first: int = 1, cited: str = "F-001", lower: bool = False) -> list[dict[str, Any]]:
    """One `seen` row per key; ids from R{first}; `lower` writes the marks in lower case."""
    return [
        row(
            f"R{first + n - 1:03d}",
            mark=mark.lower() if lower else mark,
            field=field,
            value=value,
            cites={"findings": [cited]},
        )
        for n, (mark, field, value) in KEYS.items()
    ]


def spotcheck(capsys, work: Path, n: int = 20) -> None:
    """Sample the part's rows; the command's stdout is dropped."""
    assert main(["part", "spotcheck", str(work), "--part", PART, "--seed", "7", "--n", str(n)]) == 0
    capsys.readouterr()


def sampled(capsys, work: Path, rows: list[dict[str, Any]] | None = None) -> None:
    """The rows are written, B1-piles and B1-caps locked, and every `seen` row sampled."""
    add_findings(work)
    write_values(work, key_rows() if rows is None else rows)
    lock(work, INPUT_PART)
    lock(work, PART)
    spotcheck(capsys, work, 20)


def ak(
    capsys, work: Path, row_id: str, verdict: str, *more: str, by: str = "An Nguyen"
) -> tuple[int, dict[str, Any] | None, str]:
    code = main(
        [
            "part",
            "answer-key",
            str(work),
            "--part",
            PART,
            "--row",
            row_id,
            "--verdict",
            verdict,
            "--by",
            by,
            *more,
        ]
    )
    cap = capsys.readouterr()
    return code, (json.loads(cap.out) if cap.out else None), cap.err


def score(capsys, work: Path, *more: str) -> tuple[int, dict[str, Any] | None, str]:
    code = main(["part", "score", str(work), *more])
    cap = capsys.readouterr()
    return code, (json.loads(cap.out) if cap.out else None), cap.err


def key_path(work: Path) -> Path:
    return work / "answer-key.json"


def key_doc(work: Path) -> dict[str, Any]:
    return json.loads(key_path(work).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def record_all(capsys, work: Path, only: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7)) -> None:
    """The verdicts of the score test: R002 wrong (the drawing gives 900), R005 cannot_tell, the rest ok."""
    for n in only:
        rid = f"R{n:03d}"
        more = ("--correct", "900") if n == 2 else ()
        verdict = "wrong" if n == 2 else "cannot_tell" if n == 5 else "ok"
        assert ak(capsys, work, rid, verdict, *more)[0] == 0


def reread(work: Path, rows: list[dict[str, Any]]) -> None:
    """A later read of the part: every row id and finding id is new."""
    write_values(work, rows)


def tree(root: Path) -> dict[str, tuple[bytes, int]]:
    return {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in sorted(root.rglob("*")) if p.is_file()}


def test_answer_key_refuses_unlocked_unsampled_stale(capsys, work):
    sampled(capsys, work)
    # the part is `checked`, not locked
    write_receipts(work, PART, [rec("checked", h(work))])
    code, doc, err = ak(capsys, work, "R001", "ok")
    assert (code, doc) == (1, None) and "part_not_locked" in err and "checked" in err
    lock(work, PART)
    # a row of the part that the sample does not hold, and no sample at all
    spotcheck(capsys, work, 2)
    sample = json.loads((work / "parts" / PART / "spotcheck.json").read_text(encoding="utf-8"))
    held = {r["row"] for r in sample["rows"]}
    assert held == {f"R{n:03d}" for n in range(1, 8)}  # a pool of 8 or fewer is sampled whole
    code, doc, err = ak(capsys, work, "R008", "ok")
    assert (code, doc) == (1, None) and "row_not_sampled" in err
    (work / "parts" / PART / "spotcheck.json").unlink()
    code, doc, err = ak(capsys, work, "R001", "ok")
    assert (code, doc) == (1, None) and "row_not_sampled" in err
    # the sample was drawn at an older hash: the part was edited and locked again
    spotcheck(capsys, work, 20)
    rows = key_rows()
    rows[0]["value"] = "1600x2400"
    write_values(work, rows)
    lock(work, PART)
    code, doc, err = ak(capsys, work, "R001", "ok")
    assert (code, doc) == (1, None) and "spotcheck_stale" in err
    # a row that names no file cannot form a key: the sample leaves it out (D4), and the guard stays for a
    # sample edited by hand
    write_values(work, [row("R001", file="<drop>", sheet="<drop>")])
    lock(work, PART)
    spotcheck(capsys, work, 20)
    code, doc, err = ak(capsys, work, "R001", "ok")
    assert (code, doc) == (1, None) and "row_not_sampled" in err
    force_sampled(work)
    code, doc, err = ak(capsys, work, "R001", "ok")
    assert (code, doc) == (1, None) and "row names no file" in err
    assert not key_path(work).exists()  # nothing was recorded


def test_wrong_needs_correct_usage(capsys, work):
    sampled(capsys, work)
    for verdict, more in (
        ("wrong", ()),
        ("wrong", ("--correct", " ")),
        ("ok", ("--correct", "900")),
        ("cannot_tell", ("--correct", "900")),
    ):
        code, doc, err = ak(capsys, work, "R001", verdict, *more)
        assert (code, doc) == (2, None) and "usage" in err, (verdict, more)
    assert not key_path(work).exists()
    code, doc, err = ak(capsys, work, "R001", "wrong", "--correct", "900")
    assert code == 0 and doc and doc["written"] is True


def test_new_verdict_supersedes_same_one_not_written(capsys, work):
    sampled(capsys, work)
    code, doc, err = ak(capsys, work, "R001", "ok", "--text", "Đúng, khớp bản vẽ", by="Nguyễn Văn An")
    assert (code, err) == (0, "") and doc
    assert doc == {
        "command": "answer_key", "written": True, "superseded": 0,
        "key": {"part": PART, "file": REL, "sheet": "model#01", "subject": "k-1", "field": "size"},
    }  # fmt: skip
    first = key_path(work).read_bytes()
    # the same verdict again, by someone else and with other words: nothing is written
    code, doc, _ = ak(capsys, work, "R001", "ok", "--text", "again", by="Lê Thị B")
    assert code == 0 and doc and doc["written"] is False and doc["superseded"] == 0
    assert key_path(work).read_bytes() == first
    # another verdict on the same key supersedes the active one; the old row stays
    code, doc, _ = ak(capsys, work, "R001", "wrong", "--correct", "1600x2400")
    assert code == 0 and doc and doc["written"] is True and doc["superseded"] == 1
    rows = key_doc(work)["rows"]
    assert [r["status"] for r in rows] == ["superseded", "active"]
    assert [r["verdict"] for r in rows] == ["ok", "wrong"]
    assert rows[0]["by"] == "Nguyễn Văn An" and rows[0]["engineer_text"] == "Đúng, khớp bản vẽ"
    assert rows[1]["correct"] == "1600x2400" and rows[1]["engineer_text"] is None
    # the same wrong verdict again is not written; a different correct value is
    again = key_path(work).read_bytes()
    assert ak(capsys, work, "R001", "wrong", "--correct", "1600x2400")[1]["written"] is False  # type: ignore[index]
    assert key_path(work).read_bytes() == again
    code, doc, _ = ak(capsys, work, "R001", "wrong", "--correct", "1700x2400")
    assert code == 0 and doc and doc["written"] is True and doc["superseded"] == 1
    assert [r["status"] for r in key_doc(work)["rows"]] == ["superseded", "superseded", "active"]
    # a verdict on another key supersedes nothing
    assert ak(capsys, work, "R002", "ok")[1]["superseded"] == 0  # type: ignore[index]


def test_key_validates(capsys, work):
    sampled(capsys, work)
    assert ak(capsys, work, "R001", "ok")[0] == 0
    assert ak(capsys, work, "R002", "wrong", "--correct", "900", "--text", "bản vẽ ghi 900")[0] == 0
    doc = key_doc(work)
    assert validate("answer-key", doc) == []
    assert doc["schema_version"] == "0.1" and doc["kind"] == "answer_key"
    first, second = doc["rows"]
    assert AT.match(first["at"])
    assert {k: v for k, v in first.items() if k != "at"} == {
        "part": PART, "file": REL, "sheet": "model#01", "subject": "k-1", "field": "size", "row": "R001",
        "verdict": "ok", "correct": None, "engineer_text": None, "by": "An Nguyen",
        "value_shown": "1500x2400", "status": "active", "part_hash": h(work), "seed": 7,
    }  # fmt: skip
    assert second["part_hash"] == h(work) and second["seed"] == 7  # D5: the reading and the draw it judged
    assert second["verdict"] == "wrong" and second["correct"] == "900" and second["value_shown"] == "800"
    assert second["engineer_text"] == "bản vẽ ghi 900"
    example = json.loads((EXAMPLES / "answer-key-file.example.json").read_text(encoding="utf-8"))
    assert validate("answer-key", example) == [] and example["kind"] == "answer_key"
    assert (
        validate("answer-key", json.loads((EXAMPLES / "answer-key.example.json").read_text(encoding="utf-8")))
        == []
    )  # the spot-check branch still holds

    def broken(change: Any) -> list[Any]:
        copy = json.loads(json.dumps(doc))
        change(copy["rows"][1])
        return validate("answer-key", copy)

    assert broken(lambda r: r.update(correct=None))  # wrong needs a correct value
    assert broken(lambda r: r.update(verdict="ok"))  # ok takes none
    assert broken(lambda r: r.update(status="open"))
    assert broken(lambda r: r.update(by=""))
    assert broken(lambda r: r.update(finding="F-001"))  # never an id in the row
    assert broken(lambda r: r.update(subject=""))


def test_score_agree_differ_missing_cannot_tell(capsys, work):
    sampled(capsys, work)
    assert ak(capsys, work, "R001", "wrong", "--correct", "1")[0] == 0  # superseded below: counted once
    record_all(capsys, work)
    rows = key_rows(101, "F-009", lower=True)
    rows[1]["value"] = "900"  # R102: the corrected value of the key
    rows[2]["value"] = "450"  # R103: the key says 400
    del rows[3]  # R104: the level row is gone
    # R106 keeps its value but a second row of its key (R108) differs; R107 has an asked row of the same key
    rows.insert(5, row("R108", mark="K-3", field="size", value="710x700", cites={"findings": ["F-009"]}))
    rows.append(
        row("R109", mark="K-4", field="size", value=None, state="asked", cites={"questions": ["Q-003"]})
    )
    reread(work, rows)
    code, doc, err = score(capsys, work)
    assert code == 0, "a differ is a measure, not a failure"  # exit 0 whatever the differ count
    assert doc and err == ""
    counts = {"checked": 7, "agree": 3, "differ": 2, "missing": 1, "cannot_tell": 1}
    assert doc["parts"] == [{"part": PART, **counts}]
    assert doc["total"] == counts
    # agree: R001 (case-blind mark), R002 (the corrected value 900 is what the reread gives), R007 (the asked
    # row does not count); differ: R003 and R106/R108 (STRICT: one differing row under the key is enough);
    # missing: R004; cannot_tell: R005
    assert doc["answer_key"] == str(key_path(work).resolve())


def test_regression_reread_with_new_finding_ids_is_scored(capsys, work):
    sampled(capsys, work)
    record_all(capsys, work, only=(1, 2, 3, 4))
    rows = key_rows(201, "F-099", lower=True)[:4]  # every row id and F-id new; the marks in lower case
    rows[1]["value"] = "900"  # the corrected value of R002
    reread(work, rows)
    code, doc, _ = score(capsys, work)
    assert code == 0 and doc
    assert doc["total"] == {"checked": 4, "agree": 4, "differ": 0, "missing": 0, "cannot_tell": 0}
    assert {r["subject"] for r in key_doc(work)["rows"]} == {"k-1", "k-2"}  # the key holds casefolded marks


def test_benchmark_copy_scores_another_work_folder(capsys, work, base_work, tmp_path):
    sampled(capsys, work)
    for n in (1, 2, 3):
        assert ak(capsys, work, f"R{n:03d}", "ok")[0] == 0
    bench = tmp_path / "benchmark" / "demo" / "answer-key.json"
    bench.parent.mkdir(parents=True)
    shutil.copy(key_path(work), bench)
    other = tmp_path / "later-run"
    shutil.copytree(base_work, other)  # another work folder: no key of its own, nothing locked
    rows = key_rows(301, "F-050")
    rows[1]["value"] = "850"
    write_values(other, rows)
    code, doc, err = score(capsys, other, "--answer-key", str(bench))
    assert (code, err) == (0, "") and doc
    assert doc["answer_key"] == str(bench.resolve())
    assert doc["total"] == {"checked": 3, "agree": 2, "differ": 1, "missing": 0, "cannot_tell": 0}
    code, doc, err = score(capsys, other)  # no key in the work folder, none named
    assert (code, doc) == (1, None) and "key file not found" in err
    code, doc, err = score(capsys, other, "--answer-key", str(tmp_path / "nope.json"))
    assert (code, doc) == (1, None) and "key file not found" in err


def test_score_read_only(capsys, work, tmp_path):
    sampled(capsys, work)
    record_all(capsys, work)
    bench = tmp_path / "bench.json"
    shutil.copy(key_path(work), bench)
    reread(work, key_rows(101, "F-009"))
    assert "score" not in LOCKED_ACTIONS["part"] and "answer-key" in LOCKED_ACTIONS["part"]
    before, bench_before = tree(work), tree(tmp_path)
    assert score(capsys, work)[0] == 0 and score(capsys, work, "--answer-key", str(bench))[0] == 0
    assert tree(work) == before and tree(tmp_path) == bench_before  # nothing written, nothing touched


def test_outputs_validate(capsys, work):
    sampled(capsys, work)
    code, doc, _ = ak(capsys, work, "R001", "ok")
    assert code == 0 and doc and validate("part-output", doc) == []
    code, doc, _ = ak(capsys, work, "R002", "wrong", "--correct", "900")
    assert code == 0 and doc and validate("part-output", doc) == []
    assert ak(capsys, work, "R001", "ok")[1]["written"] is False  # type: ignore[index]
    code, doc, err = score(capsys, work)
    assert (code, err) == (0, "") and doc and validate("part-output", doc) == []
    assert doc["total"]["checked"] == 2 and doc["total"]["missing"] == 0
    assert score(capsys, work)[0] == 0
    # the values of the scored part are unusable, the manifest lists no such part, the folder has no manifest:
    # every key of the part is `missing`, with one stderr line per cause, and the exit stays 0
    values = work / "parts" / PART / "values.json"
    values_text = values.read_text(encoding="utf-8")
    values.write_text("{", encoding="utf-8")
    code, doc, err = score(capsys, work)
    assert code == 0 and doc and doc["total"]["missing"] == 2 and doc["total"]["agree"] == 0
    assert len(err.strip().splitlines()) == 1 and PART in err and "values" in err
    gone = json.loads(key_path(work).read_text(encoding="utf-8"))
    for r in gone["rows"]:
        r["part"] = "B9-gone"
    stray = work.parent / "stray.json"
    stray.write_text(json.dumps(gone), encoding="utf-8")
    code, doc, err = score(capsys, work, "--answer-key", str(stray))
    assert code == 0 and doc and doc["parts"][0]["part"] == "B9-gone" and doc["total"]["missing"] == 2
    assert len(err.strip().splitlines()) == 1 and "B9-gone" in err
    manifest = work / MANIFEST
    text = manifest.read_text(encoding="utf-8")
    manifest.write_text("{", encoding="utf-8")  # an invalid manifest keeps the loader's exit code
    assert score(capsys, work)[0] == 1
    manifest.unlink()
    code, doc, err = score(capsys, work)
    assert code == 0 and doc and doc["total"]["missing"] == 2
    assert len(err.strip().splitlines()) == 1 and "manifest" in err
    manifest.write_text(text, encoding="utf-8")
    values.write_text(values_text, encoding="utf-8")  # the part is locked again
    # exit 1 only for a key file that is invalid
    good = key_path(work).read_text(encoding="utf-8")
    spot = (work / "parts" / PART / "spotcheck.json").read_text(encoding="utf-8")
    twice = json.loads(good)
    twice["rows"].append({**twice["rows"][0], "verdict": "cannot_tell"})  # m2: two active rows, one key
    for bad in ("{", "[]", spot, good.replace('"verdict": "ok"', '"verdict": "maybe"'), json.dumps(twice)):
        key_path(work).write_text(bad, encoding="utf-8")
        code, doc, err = score(capsys, work)
        assert (code, doc) == (1, None) and err.strip(), bad[:20]
        if bad == json.dumps(twice):
            assert "two active verdicts under one key" in err
        assert ak(capsys, work, "R003", "ok")[0] == 1  # the writer does not append to an invalid key file
        assert key_path(work).read_text(encoding="utf-8") == bad


def force_sampled(work: Path) -> None:
    """Put every `seen` row of the part's values into `spotcheck.json`. The sample itself leaves out the rows
    `answer-key` would refuse; this is the file it reads when the sample was edited by hand."""
    path = work / "parts" / PART / "spotcheck.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    values = json.loads((work / "parts" / PART / "values.json").read_text(encoding="utf-8"))
    doc["rows"] = [
        {
            "row": r["row"], **({"mark": r["mark"]} if "mark" in r else {"subject": r["subject"]}),
            "field": r["field"], "value": r["value"], "file": r.get("file"), "sheet": r.get("sheet"),
            "sheet_number": None, "sheet_title": None, "view": None, "entries": [], "findings": ["F-001"],
        }
        for r in values["rows"]
        if r["state"] == "seen"
    ]  # fmt: skip
    path.write_text(json.dumps(doc), encoding="utf-8")


def test_answer_key_refuses_two_rows_under_one_key(capsys, work):
    """P1: one mark at two grid positions, both read: the key cannot tell them apart."""
    rows = [
        row("R001", cites={"findings": ["F-001"]}),
        row("R002", value="1500x2500", cites={"findings": ["F-001"]}),
        row("R003", mark="K-2", value="900x900", cites={"findings": ["F-001"]}),
        row("R004", mark="K-3", value="700x700", cites={"findings": ["F-001"]}),
        row("R005", mark="K-3", value="700 x 700", cites={"findings": ["F-001"]}),  # the same value twice
        row("R006", mark="<drop>", subject="Piles", field="count_plan", value="26"),
        row("R007", mark="PILES", field="count_plan", value="4"),  # m1: same casefold as the subject
    ]
    sampled(capsys, work, rows)
    force_sampled(work)
    for rid in ("R001", "R002", "R006", "R007"):
        code, doc, err = ak(capsys, work, rid, "ok")
        assert (code, doc) == (1, None) and "key_ambiguous" in err, rid
        assert not key_path(work).exists()  # nothing is written, nothing is superseded
    code, doc, err = ak(capsys, work, "R001", "ok")
    assert "R001, R002" in err and "cannot tell them apart" in err
    # rows of one key with the same value are no ambiguity
    assert ak(capsys, work, "R004", "ok")[0] == 0 and ak(capsys, work, "R003", "ok")[0] == 0
    assert len(key_doc(work)["rows"]) == 2


def test_answer_key_checks_the_sampled_row_against_values(capsys, work):
    """P5: the part hash does not cover `spotcheck.json`; its row must match the part's values."""
    sampled(capsys, work)
    path = work / "parts" / PART / "spotcheck.json"
    original = path.read_text(encoding="utf-8")

    def edited(change: Any) -> str:
        doc = json.loads(original)
        change(next(r for r in doc["rows"] if r["row"] == "R001"))
        return json.dumps(doc)

    changes = {
        "value": lambda r: r.update(value="9999x9999"),
        "field": lambda r: r.update(field="thickness"),
        "mark": lambda r: r.update(mark="K-9"),
        "who": lambda r: (r.pop("mark"), r.update(subject="K-1")),
        "file": lambda r: r.update(file="other.dxf"),
        "sheet": lambda r: r.update(sheet="model#02"),
        "row": lambda r: r.update(row="R050"),  # a row `values.json` does not hold
    }
    for name, change in changes.items():
        path.write_text(edited(change), encoding="utf-8")
        rid = "R050" if name == "row" else "R001"
        code, doc, err = ak(capsys, work, rid, "ok")
        assert (code, doc) == (1, None) and "spotcheck_stale" in err, name
        assert not key_path(work).exists(), name
    path.write_text(original, encoding="utf-8")
    assert ak(capsys, work, "R001", "ok")[0] == 0  # the untouched sample records
    assert key_doc(work)["rows"][0]["value_shown"] == "1500x2400"


def test_a_new_value_shown_is_a_new_verdict(capsys, work):
    """M7: the same verdict on the same key but on another value is written and supersedes."""
    sampled(capsys, work)
    assert ak(capsys, work, "R001", "ok")[1]["written"] is True  # type: ignore[index]
    rows = key_rows()
    rows[0]["value"] = "1600x2400"
    write_values(work, rows)
    lock(work, PART)
    spotcheck(capsys, work)
    code, doc, _ = ak(capsys, work, "R001", "ok")
    assert code == 0 and doc and doc["written"] is True and doc["superseded"] == 1
    assert [r["value_shown"] for r in key_doc(work)["rows"]] == ["1500x2400", "1600x2400"]


def test_a_sample_of_another_part_is_refused(capsys, work):
    """M12: a `spotcheck.json` copied from another part's folder holds no row of this part."""
    sampled(capsys, work)
    path = work / "parts" / PART / "spotcheck.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["part"] = INPUT_PART
    path.write_text(json.dumps(doc), encoding="utf-8")
    code, doc, err = ak(capsys, work, "R001", "ok")
    assert (code, doc) == (1, None) and "row_not_sampled" in err and not key_path(work).exists()


def test_two_active_verdicts_under_one_key_are_refused(capsys, work):
    sampled(capsys, work)
    assert ak(capsys, work, "R001", "ok")[0] == 0
    doc = key_doc(work)
    doc["rows"].append({**doc["rows"][0], "verdict": "cannot_tell"})
    path = work.parent / "merged.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    code, out, err = score(capsys, work, "--answer-key", str(path))  # P2: one key would count twice
    assert (code, out) == (1, None) and "two active verdicts under one key" in err


def test_the_key_ignores_unicode_form_and_spacing(capsys, work):
    """m7: a reread that writes the subject in NFD, or with a doubled space, is still scored."""
    nfc = unicodedata.normalize("NFC", "Đài móng M1")
    rows = [row("R001", mark=nfc), row("R002", mark="K-2", value="900x900")]
    sampled(capsys, work, rows)
    assert ak(capsys, work, "R001", "ok")[0] == 0
    assert key_doc(work)["rows"][0]["subject"] == nfc.casefold()
    reread(work, [row("R101", mark=unicodedata.normalize("NFD", "Đài  móng M1"))])
    code, doc, _ = score(capsys, work)
    assert code == 0 and doc and doc["total"] == {
        "checked": 1, "agree": 1, "differ": 0, "missing": 0, "cannot_tell": 0,
    }  # fmt: skip


def test_an_asked_row_with_a_candidate_value_does_not_count(capsys, work):
    """M9: an `asked` row may carry a candidate value; only `seen` rows are the reading."""
    sampled(capsys, work)
    assert ak(capsys, work, "R001", "ok")[0] == 0
    reread(
        work,
        [row("R101", value=None, state="asked", cites={"questions": ["Q-003"]}) | {"value": "9999x9999"}],
    )
    code, doc, _ = score(capsys, work)
    assert code == 0 and doc and doc["total"]["missing"] == 1 and doc["total"]["differ"] == 0


def test_the_two_examples_agree(capsys):
    spot = json.loads((EXAMPLES / "answer-key.example.json").read_text(encoding="utf-8"))
    keyed = json.loads((EXAMPLES / "answer-key-file.example.json").read_text(encoding="utf-8"))
    by_row = {r["row"]: r for r in spot["rows"]}
    for r in keyed["rows"]:  # m8: one row id means one file, sheet, subject and field in both
        sampled_row = by_row[r["row"]]
        who = sampled_row.get("mark") or sampled_row["subject"]
        assert (r["file"], r["sheet"], r["subject"], r["field"]) == (
            sampled_row["file"], sampled_row["sheet"], who.casefold(), sampled_row["field"],
        )  # fmt: skip
        assert (r["part_hash"], r["seed"]) == (spot["part_hash"], spot["seed"])  # D5
