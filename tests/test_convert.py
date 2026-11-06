"""dwg_to_dxf fallback chain (ADR-0005), proven with fake converter executables.

Real ODA / LibreDWG binaries are not on CI. Each fake is a Python script run as
`[sys.executable, script]`, so the tests run the same on Windows and Linux.
"""

from __future__ import annotations

import json
import sys
import textwrap

import pytest
from ezdxf.filemanagement import new, readfile

from tekla_harness.cli import main
from tekla_harness.convert import NoConverterError, dwg_to_dxf

# What each fake does. ODA is called as: <exe> in_dir out_dir version type recurse audit filter
# dwg2dxf is called as: <exe> -y -o out.dxf in.dwg
BEHAVIOURS = {
    "ok": "shutil.copy(TEMPLATE, out_path)",
    "exit_1": "sys.stderr.write('fatal: bad header'); sys.exit(1)",
    "timeout": "time.sleep(30)",
    "no_output": "pass",
    "garbage_output": "open(out_path, 'w').write('this is not a dxf')",
    "binary_output": "open(out_path, 'wb').write(bytes(range(256)) * 8)",
    "truncated_output": "open(out_path, 'w').write(open(TEMPLATE).read()[:500])",
}


def fake_converter(tmp_path, kind: str, behaviour: str, template) -> list[str]:
    if kind == "oda":
        out_path = "os.path.join(sys.argv[2], os.path.splitext(sys.argv[7])[0] + '.dxf')"
    else:
        out_path = "sys.argv[sys.argv.index('-o') + 1]"
    script = tmp_path / f"fake_{kind}_{behaviour}.py"
    script.write_text(
        textwrap.dedent(f"""\
            import os, shutil, sys, time
            TEMPLATE = {str(template)!r}
            out_path = {out_path}
            {BEHAVIOURS[behaviour]}
        """),
        encoding="utf-8",
    )
    return [sys.executable, str(script)]


@pytest.fixture
def template(tmp_path):
    path = tmp_path / "template.dxf"
    doc = new("R2018")
    doc.modelspace().add_line((0, 0), (6000, 0))
    doc.saveas(path)
    return path


@pytest.fixture
def dwg(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    path = input_dir / "S-101.dwg"
    path.write_bytes(b"AC1032" + b"\x00" * 64)
    return path


@pytest.fixture
def out_dir(tmp_path):
    path = tmp_path / "work"
    path.mkdir()
    return path


def test_oda_success_keeps_high_cap(tmp_path, template, dwg, out_dir):
    result = dwg_to_dxf(dwg, out_dir, oda=fake_converter(tmp_path, "oda", "ok", template))
    assert result.dxf == out_dir / "S-101.dxf"
    assert result.converter == "oda_file_converter"
    assert result.confidence_cap == "high"
    assert [a.status for a in result.attempts] == ["ok"]
    assert result.dxf is not None
    readfile(result.dxf)


@pytest.mark.parametrize(
    ("behaviour", "error_part"),
    [
        ("exit_1", "exit code 1"),
        ("timeout", "timed out"),
        ("no_output", "no DXF"),
        ("garbage_output", "cannot be opened"),
        ("binary_output", "cannot be opened"),
        ("truncated_output", "cannot be opened"),
    ],
)
def test_oda_failure_falls_back_to_libredwg_with_medium_cap(
    tmp_path, template, dwg, out_dir, behaviour, error_part
):
    result = dwg_to_dxf(
        dwg,
        out_dir,
        oda=fake_converter(tmp_path, "oda", behaviour, template),
        dwg2dxf=fake_converter(tmp_path, "dwg2dxf", "ok", template),
        timeout=2,
    )
    first, second = result.attempts
    assert first.tool == "oda_file_converter" and first.status == "failed"
    assert error_part in (first.error or "")
    assert second.tool == "libredwg_dwg2dxf" and second.status == "ok"
    assert result.converter == "libredwg_dwg2dxf"
    assert result.confidence_cap == "medium"
    assert any("fallback" in w for w in result.warnings)


def test_missing_binary_is_a_recorded_failure(tmp_path, template, dwg, out_dir):
    result = dwg_to_dxf(
        dwg,
        out_dir,
        oda=[str(tmp_path / "does-not-exist" / "ODAFileConverter")],
        dwg2dxf=fake_converter(tmp_path, "dwg2dxf", "ok", template),
    )
    assert result.attempts[0].status == "failed"
    assert "not found" in (result.attempts[0].error or "")
    assert result.converter == "libredwg_dwg2dxf"


def test_both_fail_means_unreadable(tmp_path, template, dwg, out_dir):
    result = dwg_to_dxf(
        dwg,
        out_dir,
        oda=fake_converter(tmp_path, "oda", "exit_1", template),
        dwg2dxf=fake_converter(tmp_path, "dwg2dxf", "garbage_output", template),
    )
    assert result.dxf is None
    assert result.converter is None
    assert result.confidence_cap is None
    assert all(a.status == "failed" and a.error for a in result.attempts)
    assert not (out_dir / "S-101.dxf").exists()  # garbage is never left as if it were a result
    assert any("DXF or PDF" in w for w in result.warnings)


def test_no_converter_configured_is_environment_error(dwg, out_dir, monkeypatch):
    monkeypatch.delenv("HARNESS_ODA_CONVERTER", raising=False)
    monkeypatch.delenv("HARNESS_DWG2DXF", raising=False)
    monkeypatch.setattr("tekla_harness.convert.shutil.which", lambda _name: None)
    with pytest.raises(NoConverterError):
        dwg_to_dxf(dwg, out_dir)


def test_input_folder_is_never_written(tmp_path, template, dwg, out_dir):
    before = sorted(p.name for p in dwg.parent.iterdir())
    dwg_to_dxf(dwg, out_dir, oda=fake_converter(tmp_path, "oda", "ok", template))
    assert sorted(p.name for p in dwg.parent.iterdir()) == before


def test_out_dir_inside_input_is_refused(tmp_path, template, dwg):
    with pytest.raises(ValueError, match="input"):
        dwg_to_dxf(dwg, dwg.parent, oda=fake_converter(tmp_path, "oda", "ok", template))


def test_cli_exit_codes(tmp_path, template, dwg, out_dir, capsys, monkeypatch):
    oda_ok = fake_converter(tmp_path, "oda", "ok", template)
    oda_bad = fake_converter(tmp_path, "oda", "exit_1", template)
    # The CLI takes one executable path; wrap the fake in the env var form used on real machines.
    monkeypatch.setattr("tekla_harness.convert._split_command", lambda value: json.loads(value))

    monkeypatch.setenv("HARNESS_ODA_CONVERTER", json.dumps(oda_ok))
    monkeypatch.delenv("HARNESS_DWG2DXF", raising=False)
    assert main(["dwg2dxf", str(dwg), "--out-dir", str(out_dir)]) == 0
    assert json.loads(capsys.readouterr().out)["converter"] == "oda_file_converter"

    monkeypatch.setenv("HARNESS_ODA_CONVERTER", json.dumps(oda_bad))
    assert main(["dwg2dxf", str(dwg), "--out-dir", str(tmp_path / "work2")]) == 1
    assert json.loads(capsys.readouterr().out)["dxf"] is None

    monkeypatch.delenv("HARNESS_ODA_CONVERTER")
    monkeypatch.setattr("tekla_harness.convert.shutil.which", lambda _name: None)
    assert main(["dwg2dxf", str(dwg), "--out-dir", str(tmp_path / "work3")]) == 3
