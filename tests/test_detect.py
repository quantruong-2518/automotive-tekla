"""detect_input: identify the real format of an input file from its bytes, not its name."""

from __future__ import annotations

import hashlib
import json
import zipfile

import pytest

from tekla_harness.cli import main
from tekla_harness.detect import detect_file, iter_input_files, sha256_file

ASCII_DXF = b"  0\nSECTION\n  2\nHEADER\n  9\n$ACADVER\n  1\nAC1032\n  0\nENDSEC\n  0\nEOF\n"


def write(tmp_path, name: str, data: bytes):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def make_zip(tmp_path, name: str, members: list[str]):
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        for member in members:
            zf.writestr(member, "<x/>")
    return path


def test_sha256_matches_hashlib(tmp_path):
    data = b"abc" * 100_000
    path = write(tmp_path, "a.bin", data)
    assert sha256_file(path) == hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize(
    ("header", "release"),
    [(b"AC1015", "R2000"), (b"AC1018", "R2004"), (b"AC1024", "R2010"), (b"AC1032", "R2018")],
)
def test_dwg_version_from_header(tmp_path, header, release):
    info = detect_file(write(tmp_path, "S-101.dwg", header + b"\x00" * 64))
    assert info["kind"] == "dwg"
    assert info["dwg_version"] == header.decode()
    assert info["dwg_release"] == release
    assert info["warnings"] == []


def test_unknown_dwg_version_is_warned_not_guessed(tmp_path):
    info = detect_file(write(tmp_path, "S-101.dwg", b"AC1099" + b"\x00" * 64))
    assert info["kind"] == "dwg"
    assert info["dwg_release"] is None
    assert any("AC1099" in w for w in info["warnings"])


def test_ascii_dxf(tmp_path):
    info = detect_file(write(tmp_path, "S-101.dxf", ASCII_DXF))
    assert info["kind"] == "dxf"
    assert info["dxf_encoding"] == "ascii"


def test_ascii_dxf_with_leading_comment(tmp_path):
    info = detect_file(write(tmp_path, "S-101.dxf", b"999\nmade by x\n" + ASCII_DXF))
    assert info["kind"] == "dxf"


def test_binary_dxf(tmp_path):
    info = detect_file(write(tmp_path, "S-101.dxf", b"AutoCAD Binary DXF\r\n\x1a\x00" + b"\x00" * 32))
    assert info["kind"] == "dxf"
    assert info["dxf_encoding"] == "binary"


def test_pdf(tmp_path):
    assert detect_file(write(tmp_path, "S-101.pdf", b"%PDF-1.7\n%...\n"))["kind"] == "pdf"


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("a.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 16),
        ("a.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 16),
        ("a.tif", b"II*\x00" + b"\x00" * 16),
        ("b.tif", b"MM\x00*" + b"\x00" * 16),
    ],
)
def test_images(tmp_path, name, data):
    assert detect_file(write(tmp_path, name, data))["kind"] == "image"


def test_docx_and_xlsx(tmp_path):
    docx = make_zip(tmp_path, "notes.docx", ["[Content_Types].xml", "word/document.xml"])
    xlsx = make_zip(tmp_path, "schedule.xlsx", ["[Content_Types].xml", "xl/workbook.xml"])
    other = make_zip(tmp_path, "bundle.zip", ["readme.txt"])
    assert detect_file(docx)["kind"] == "docx"
    assert detect_file(xlsx)["kind"] == "xlsx"
    assert detect_file(other)["kind"] == "other"


def test_extension_mismatch_is_warned(tmp_path):
    # A PDF someone renamed to .dwg: trust the bytes, flag the name.
    info = detect_file(write(tmp_path, "S-101.dwg", b"%PDF-1.4\n"))
    assert info["kind"] == "pdf"
    assert any("extension" in w for w in info["warnings"])


def test_empty_and_unknown_files(tmp_path):
    empty = detect_file(write(tmp_path, "empty.dwg", b""))
    assert empty["kind"] == "other"
    assert any("empty" in w for w in empty["warnings"])
    assert detect_file(write(tmp_path, "x.txt", b"hello"))["kind"] == "other"


def test_iter_input_files_is_sorted_and_recursive(tmp_path):
    (tmp_path / "b").mkdir()
    write(tmp_path / "b", "2.dxf", ASCII_DXF)
    write(tmp_path, "1.dxf", ASCII_DXF)
    write(tmp_path, "3.pdf", b"%PDF-1.7")
    names = [p.relative_to(tmp_path).as_posix() for p in iter_input_files([tmp_path])]
    assert names == ["1.dxf", "3.pdf", "b/2.dxf"]


def test_cli_detect_json(tmp_path, capsys):
    write(tmp_path, "S-101.dwg", b"AC1032" + b"\x00" * 64)
    write(tmp_path, "S-102.dxf", ASCII_DXF)
    assert main(["detect", str(tmp_path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [f["kind"] for f in out["files"]] == ["dwg", "dxf"]
    assert all(len(f["sha256"]) == 64 for f in out["files"])


def test_cli_detect_missing_path_exit_1(tmp_path, capsys):
    assert main(["detect", str(tmp_path / "missing.dwg")]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["errors"][0]["path"].endswith("missing.dwg")
