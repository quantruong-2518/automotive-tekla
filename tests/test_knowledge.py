"""knowledge: the approved font-encoding table (ADR-0006 layer 2). Fixtures are written into tmp_path."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from tekla_harness.knowledge import (
    EMPTY_TABLE,
    FONT_ENCODINGS_HEADER,
    KnowledgeError,
    default_font_encodings,
    default_font_encodings_path,
    load_font_encodings,
)

HEADER = "pattern,applies_to,encoding,capital_font,status,evidence,source,decided_by,decided_on"


def row(**kw: str) -> list[str]:
    base = {
        "pattern": "VX*.TTF",
        "applies_to": "font_file",
        "encoding": "tcvn3",
        "capital_font": "",
        "status": "proposed",
        "evidence": "some counts",
        "source": "test",
        "decided_by": "",
        "decided_on": "",
    }
    base.update(kw)
    return [base[name] for name in FONT_ENCODINGS_HEADER]


def write(tmp_path: Path, rows: list[list[str]], header: str = HEADER) -> Path:
    path = tmp_path / "font-encodings.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(header + "\n")
        csv.writer(handle, lineterminator="\n").writerows(rows)
    return path


def approved(**kw: str) -> list[str]:
    return row(status="approved", decided_by="engineer", decided_on="2026-11-07", **kw)


# --- the shipped table --------------------------------------------------------------------


def test_shipped_table_loads_and_has_the_seed_rows():
    table = default_font_encodings()
    assert table is default_font_encodings()  # loaded once
    assert default_font_encodings_path().name == "font-encodings.csv"
    patterns = {(r.applies_to, r.pattern, r.encoding) for r in table.rows}
    assert ("font_file", "VHARIAL.TTF", "tcvn3") in patterns
    assert ("font_file", "vntimeh.shx", "tcvn3") in patterns
    assert ("font_file", "vn_vni.shx", "vni") in patterns
    # Regression: broad globs (VH*.TTF, vn*.shx) matched fonts with counter-evidence (VHELVCN.TTF
    # holds VNI text) or a different encoding (vn_vni.shx). Seed rows name only fonts with evidence.
    assert not any("*" in r.pattern for r in table.rows)
    assert not any(r.pattern.upper().startswith("*H") for r in table.rows)  # H suffix stays in font_hint


def test_header_constant_matches_the_documented_columns():
    assert ",".join(FONT_ENCODINGS_HEADER) == HEADER
    first_line = default_font_encodings_path().read_text(encoding="utf-8").splitlines()[0]
    assert first_line == HEADER


# --- loading and validation: bad rows are errors, never ignored ---------------------------------


def test_valid_rows_load(tmp_path):
    table = load_font_encodings(
        write(
            tmp_path, [row(), approved(pattern="a*", encoding="vni"), row(pattern="b", capital_font="true")]
        )
    )
    assert [r.pattern for r in table.rows] == ["VX*.TTF", "a*", "b"]
    assert table.rows[1].status == "approved" and table.rows[1].decided_by == "engineer"
    assert table.rows[2].capital_font is True and table.rows[0].capital_font is None


def test_empty_table_is_valid(tmp_path):
    assert load_font_encodings(write(tmp_path, [])).rows == ()
    assert EMPTY_TABLE.rows == ()


@pytest.mark.parametrize(
    ("rows", "header", "needle"),
    [
        ([], "pattern,applies_to,encoding", "header"),
        ([], HEADER + ",extra", "header"),
        ([["only", "three", "fields"]], HEADER, "9 fields"),
        ([row(pattern="")], HEADER, "pattern"),
        ([row(applies_to="layer")], HEADER, "applies_to"),
        ([row(encoding="utf16")], HEADER, "encoding"),
        ([row(encoding="unknown")], HEADER, "encoding"),
        ([row(capital_font="yes")], HEADER, "capital_font"),
        ([row(encoding="vni", capital_font="true")], HEADER, "capital_font"),
        ([row(status="maybe")], HEADER, "status"),
        ([row(status="approved")], HEADER, "decided_by"),
        ([row(status="approved", decided_by="x")], HEADER, "decided_on"),
        ([row(status="approved", decided_by="x", decided_on="07/11/2026")], HEADER, "decided_on"),
        ([row(status="approved", decided_by="x", decided_on="2026-13-40")], HEADER, "decided_on"),
        ([row(status="rejected")], HEADER, "decided_by"),
        ([row(decided_by="x", decided_on="2026-11-07")], HEADER, "proposed"),
        ([row(evidence="")], HEADER, "evidence"),
        ([row(source=" ")], HEADER, "source"),
        ([row(pattern=" VX*.TTF")], HEADER, "pattern"),
        ([row(), row(pattern="vx*.ttf", encoding="vni")], HEADER, "duplicate"),
    ],
)
def test_malformed_table_fails_loudly(tmp_path, rows, header, needle):
    with pytest.raises(KnowledgeError, match=needle):
        load_font_encodings(write(tmp_path, rows, header))


def test_error_names_the_file_and_line(tmp_path):
    path = write(tmp_path, [row(), row(encoding="utf16")])
    with pytest.raises(KnowledgeError, match=r"font-encodings\.csv:3"):
        load_font_encodings(path)


def test_missing_and_non_utf8_files_fail(tmp_path):
    with pytest.raises(KnowledgeError, match="cannot read"):
        load_font_encodings(tmp_path / "nope.csv")
    bad = tmp_path / "bad.csv"
    bad.write_bytes(HEADER.encode() + b"\n\xff\xfe\n")
    with pytest.raises(KnowledgeError, match="UTF-8"):
        load_font_encodings(bad)


def test_empty_file_fails(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    with pytest.raises(KnowledgeError, match="header"):
        load_font_encodings(path)


# --- matching -------------------------------------------------------------------------------------


def table_of(tmp_path, *rows):
    return load_font_encodings(write(tmp_path, list(rows)))


def test_only_approved_rows_decide(tmp_path):
    table = table_of(tmp_path, row(pattern="VH*.TTF"), approved(pattern="vn*.shx"))
    proposed_only = table.match("kt..1", "VHARIAL.TTF")
    assert proposed_only.encoding is None and proposed_only.patterns == ()
    assert [r.pattern for r in proposed_only.proposed] == ["VH*.TTF"]
    decided = table.match("TKT", "vntimeh.shx")
    assert decided.encoding == "tcvn3" and decided.patterns == ("vn*.shx",) and decided.proposed == ()


def test_rejected_rows_are_inert(tmp_path):
    table = table_of(tmp_path, row(status="rejected", decided_by="x", decided_on="2026-11-07"))
    m = table.match("s", "VXA.TTF")
    assert m.encoding is None and m.proposed == () and m.conflict == ()


def test_glob_is_case_insensitive_and_font_file_uses_the_leaf(tmp_path):
    table = table_of(tmp_path, approved(pattern="vh*.ttf"))
    assert table.match("s", "VHARIAL.TTF").encoding == "tcvn3"
    assert table.match("s", "C:\\fonts\\VHARIAL.TTF").encoding == "tcvn3"
    assert table.match("s", "/usr/share/vharial.ttf").encoding == "tcvn3"
    assert table.match("s", "arial.ttf").encoding is None
    assert table.match("VHARIAL.TTF", None).encoding is None  # a font_file row never reads the style name


def test_style_name_rows_read_the_style_name_only(tmp_path):
    table = table_of(tmp_path, approved(pattern="KT..*", applies_to="style_name"))
    assert table.match("kt..1", "arial.ttf").encoding == "tcvn3"
    assert table.match("other", "kt..1").encoding is None
    assert table.match(None, None).encoding is None


def test_missing_inputs_never_match(tmp_path):
    by_file = table_of(tmp_path, approved(pattern="*", applies_to="font_file"))
    assert by_file.match("s", None).encoding is None and by_file.match("s", "").encoding is None
    by_style = table_of(tmp_path, approved(pattern="*", applies_to="style_name"))
    assert by_style.match(None, "x.ttf").encoding is None and by_style.match("", "x.ttf").encoding is None


def test_agreeing_rows_decide_and_capital_font_is_taken_only_when_they_agree(tmp_path):
    table = table_of(
        tmp_path,
        approved(pattern="a*.ttf", capital_font="true"),
        approved(pattern="*b.ttf", capital_font="true"),
        approved(pattern="*c.ttf", capital_font="false"),
    )
    both = table.match("s", "ab.ttf")
    assert both.encoding == "tcvn3" and both.capital_font is True
    assert both.patterns == ("a*.ttf", "*b.ttf")
    clash = table.match("s", "ac.ttf")
    assert clash.encoding == "tcvn3" and clash.capital_font is None


def test_approved_rows_with_different_encodings_conflict(tmp_path):
    # vn*.shx and vn_vni.shx both match vn_vni.shx: stay undecided rather than pick one.
    table = table_of(tmp_path, approved(pattern="vn*.shx"), approved(pattern="vn_vni.shx", encoding="vni"))
    m = table.match("s", "vn_vni.shx")
    assert m.encoding is None and m.patterns == ()
    assert [r.pattern for r in m.conflict] == ["vn*.shx", "vn_vni.shx"]
    assert table.match("s", "vntimeh.shx").encoding == "tcvn3"


def test_proposed_rows_are_listed_even_beside_an_approved_row(tmp_path):
    table = table_of(tmp_path, approved(pattern="vn*.shx"), row(pattern="vn_vni.shx", encoding="vni"))
    m = table.match("s", "vn_vni.shx")
    assert m.encoding == "tcvn3"
    assert [r.pattern for r in m.proposed] == ["vn_vni.shx"]
