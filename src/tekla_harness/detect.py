"""detect_input: identify an input file's real format from its bytes and hash it.

The file name is only used to warn about a mismatch; the bytes decide. PDFs are reported as
`pdf` here: telling vector, scanned and mixed PDFs apart needs a PDF reader (later slice).
"""

from __future__ import annotations

import hashlib
import zipfile
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

# DWG header version string -> AutoCAD release that introduced it (ODA / AutoCAD docs).
DWG_RELEASES = {
    "AC1009": "R11/R12",
    "AC1012": "R13",
    "AC1014": "R14",
    "AC1015": "R2000",
    "AC1018": "R2004",
    "AC1021": "R2007",
    "AC1024": "R2010",
    "AC1027": "R2013",
    "AC1032": "R2018",
}
_EXTENSION_KINDS = {
    ".dwg": "dwg",
    ".dxf": "dxf",
    ".pdf": "pdf",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".tif": "image",
    ".tiff": "image",
    ".docx": "docx",
    ".xlsx": "xlsx",
}
_BINARY_DXF = b"AutoCAD Binary DXF\r\n\x1a\x00"
_IMAGE_MAGIC = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"II*\x00", b"MM\x00*")
_HEAD_BYTES = 4096


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_ascii_dxf(head: bytes) -> bool:
    """A DXF starts with group code 0 + SECTION, optionally after 999 comment pairs."""
    lines = [line.strip() for line in head.decode("latin-1").splitlines()]
    i = 0
    while i + 1 < len(lines) and lines[i] == "999":
        i += 2
    return i + 1 < len(lines) and lines[i] == "0" and lines[i + 1] == "SECTION"


def _zip_kind(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
    except zipfile.BadZipFile:
        return "other"
    if "word/document.xml" in names:
        return "docx"
    if "xl/workbook.xml" in names:
        return "xlsx"
    return "other"


def detect_file(path: Path) -> dict[str, Any]:
    """Return {file, sha256, size, kind, warnings, ...kind-specific fields}."""
    path = Path(path)
    with path.open("rb") as fh:
        head = fh.read(_HEAD_BYTES)
    info: dict[str, Any] = {
        "file": str(path),
        "sha256": sha256_file(path),
        "size": path.stat().st_size,
        "kind": "other",
        "warnings": [],
    }
    warnings: list[str] = info["warnings"]

    if not head:
        warnings.append("empty file")
    elif head[:2] == b"AC" and head[2:6].isdigit():
        version = head[:6].decode("ascii")
        release = DWG_RELEASES.get(version)
        info |= {"kind": "dwg", "dwg_version": version, "dwg_release": release}
        if release is None:
            warnings.append(f"unknown DWG version string {version}; converter support not verified")
    elif head.startswith(_BINARY_DXF):
        info |= {"kind": "dxf", "dxf_encoding": "binary"}
    elif _is_ascii_dxf(head):
        info |= {"kind": "dxf", "dxf_encoding": "ascii"}
    elif b"%PDF-" in head[:1024]:
        info["kind"] = "pdf"
    elif head.startswith(_IMAGE_MAGIC):
        info["kind"] = "image"
    elif head.startswith(b"PK\x03\x04"):
        info["kind"] = _zip_kind(path)

    expected = _EXTENSION_KINDS.get(path.suffix.lower())
    if head and expected is not None and expected != info["kind"]:
        warnings.append(
            f"file extension '{path.suffix}' suggests {expected}, content is {info['kind']}; content wins"
        )
    return info


def iter_input_files(paths: Iterable[Path]) -> Iterator[Path]:
    """Yield files; directories are walked recursively in sorted order."""
    for path in paths:
        path = Path(path)
        if path.is_dir():
            yield from sorted((p for p in path.rglob("*") if p.is_file()), key=lambda p: p.as_posix())
        else:
            yield path
