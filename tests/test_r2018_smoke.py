"""A synthetic DXF R2018 (AC1032) goes through intake and read-structure (tool wave 4, seam)."""

from __future__ import annotations

import json

from ezdxf.filemanagement import new

from tekla_harness.cli import main
from tekla_harness.schemas import validate


def test_r2018_dxf_goes_through_intake_and_read_structure(tmp_path, capsys):
    inp = tmp_path / "input"
    inp.mkdir()
    doc = new("R2018")
    assert doc.dxfversion == "AC1032"
    msp = doc.modelspace()
    msp.add_text("SMOKE R2018 NOTE", height=250, dxfattribs={"insert": (100.0, 100.0)})
    msp.add_line((0, 0), (5000, 0))
    doc.saveas(inp / "r2018.dxf")
    work = tmp_path / "work"
    assert main(["intake", str(inp), "--out", str(work), "--project-id", "smoke-r2018"]) == 0
    assert main(["read-structure", str(work), "--input-dir", str(inp)]) == 0
    capsys.readouterr()
    index = json.loads((work / "text" / "r2018.dxf.json").read_text("utf-8"))
    assert validate("text-index", index) == []
    assert [e["display_text"] for e in index["entries"]] == ["SMOKE R2018 NOTE"]
