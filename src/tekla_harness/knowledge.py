"""knowledge: approved knowledge tables (ADR-0006, layer 2), starting with `font-encodings.csv`.

A table is a CSV in the repository `knowledge/` folder, reviewed like code. Rule: ONLY `approved` rows
change behaviour. A `proposed` row never changes a decoding; callers use it to raise a question that
shows its evidence. A `rejected` row is kept as memory and does nothing. An engineer approves a row by
editing `status`, `decided_by` and `decided_on` in a reviewed commit; nothing here writes a table.

A malformed table raises `KnowledgeError`: a bad row is never skipped, because a skipped row would
silently change what the harness reads.

Font-encoding rows say which legacy Vietnamese encoding a text style uses when the font NAME rules in
`encoding.font_hint` cannot tell. They are consulted only after `font_hint` returned "unknown", and
never override a positive `font_hint`. Patterns are case-insensitive globs (`fnmatch`): a `style_name`
row matches the text style name, a `font_file` row matches the leaf of the style's font file name.
"""

from __future__ import annotations

import csv
import fnmatch
import io
from dataclasses import dataclass
from datetime import date
from functools import cache
from importlib import resources
from pathlib import Path, PureWindowsPath
from typing import Literal, cast

FONT_ENCODINGS_FILE = "font-encodings.csv"
FONT_ENCODINGS_HEADER = (
    "pattern",
    "applies_to",
    "encoding",
    "capital_font",
    "status",
    "evidence",
    "source",
    "decided_by",
    "decided_on",
)
_APPLIES_TO = ("style_name", "font_file")
_ENCODINGS = ("tcvn3", "vni", "unicode")
_STATUSES = ("proposed", "approved", "rejected")
_REPO_KNOWLEDGE = Path(__file__).resolve().parents[2] / "knowledge"

TableEncoding = Literal["tcvn3", "vni", "unicode"]


class KnowledgeError(Exception):
    """A knowledge table that cannot be read or does not validate."""


@dataclass(frozen=True)
class FontEncodingRow:
    line: int  # 1-based line of the row in the file (the header is line 1)
    pattern: str
    applies_to: str  # style_name | font_file
    encoding: TableEncoding
    capital_font: bool | None
    status: str  # proposed | approved | rejected
    evidence: str
    source: str
    decided_by: str
    decided_on: str

    def cite(self) -> str:
        return f"{self.applies_to} '{self.pattern}' -> {self.encoding} ({self.status})"


@dataclass(frozen=True)
class FontMatch:
    """What the table says about one text style.

    `encoding` is set only by approved rows that agree. Approved rows that disagree on the encoding
    are a `conflict`: `encoding` stays None (never guess) and the caller flags it. `proposed` rows
    are evidence for a question, never a decision.
    """

    encoding: TableEncoding | None = None
    capital_font: bool | None = None
    rows: tuple[FontEncodingRow, ...] = ()  # the approved rows that decided
    conflict: tuple[FontEncodingRow, ...] = ()
    proposed: tuple[FontEncodingRow, ...] = ()

    @property
    def patterns(self) -> tuple[str, ...]:
        return tuple(r.pattern for r in self.rows)


def _glob(pattern: str, value: str) -> bool:
    return fnmatch.fnmatchcase(value.casefold(), pattern.casefold())


@dataclass(frozen=True)
class FontEncodingTable:
    rows: tuple[FontEncodingRow, ...] = ()

    def match(self, style_name: str | None, font_file: str | None) -> FontMatch:
        leaf = PureWindowsPath(font_file).name if font_file else ""
        subjects = {"style_name": style_name or "", "font_file": leaf}
        hits = [r for r in self.rows if subjects[r.applies_to] and _glob(r.pattern, subjects[r.applies_to])]
        approved = [r for r in hits if r.status == "approved"]
        proposed = tuple(r for r in hits if r.status == "proposed")
        if len({r.encoding for r in approved}) > 1:
            return FontMatch(conflict=tuple(approved), proposed=proposed)
        if not approved:
            return FontMatch(proposed=proposed)
        capitals = {r.capital_font for r in approved if r.capital_font is not None}
        return FontMatch(
            encoding=approved[0].encoding,
            capital_font=capitals.pop() if len(capitals) == 1 else None,
            rows=tuple(approved),
            proposed=proposed,
        )


EMPTY_TABLE = FontEncodingTable()


def default_font_encodings_path() -> Path:
    """`knowledge/font-encodings.csv` in a checkout; the packaged copy in an installed wheel."""
    if _REPO_KNOWLEDGE.is_dir():
        return _REPO_KNOWLEDGE / FONT_ENCODINGS_FILE
    return Path(str(resources.files("tekla_harness") / "knowledge_files" / FONT_ENCODINGS_FILE))


@cache
def default_font_encodings() -> FontEncodingTable:
    """The shipped table, loaded once per process."""
    return load_font_encodings(default_font_encodings_path())


def load_font_encodings(path: str | Path) -> FontEncodingTable:
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise KnowledgeError(f"cannot read knowledge table {path}: {exc}") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise KnowledgeError(f"{path} is not UTF-8: {exc}") from exc
    try:
        records = list(csv.reader(io.StringIO(text, newline="")))
    except csv.Error as exc:
        raise KnowledgeError(f"{path}: not valid CSV: {exc}") from exc
    if not records or tuple(records[0]) != FONT_ENCODINGS_HEADER:
        raise KnowledgeError(f"{path}:1: header must be exactly {','.join(FONT_ENCODINGS_HEADER)}")
    rows: list[FontEncodingRow] = []
    seen: dict[tuple[str, str], int] = {}
    for number, fields in enumerate(records[1:], start=2):
        if not fields:  # a blank line is not a row
            continue
        where = f"{path.name}:{number}"
        row = _parse_row(where, number, fields)
        key = (row.applies_to, row.pattern.casefold())
        if key in seen:
            raise KnowledgeError(
                f"{where}: duplicate row for {row.applies_to} '{row.pattern}' (line {seen[key]})"
            )
        seen[key] = number
        rows.append(row)
    return FontEncodingTable(tuple(rows))


def _parse_row(where: str, number: int, fields: list[str]) -> FontEncodingRow:
    if len(fields) != len(FONT_ENCODINGS_HEADER):
        raise KnowledgeError(f"{where}: expected {len(FONT_ENCODINGS_HEADER)} fields, got {len(fields)}")
    f = dict(zip(FONT_ENCODINGS_HEADER, fields, strict=True))
    if not f["pattern"] or f["pattern"] != f["pattern"].strip():
        raise KnowledgeError(f"{where}: pattern must be non-empty without leading or trailing spaces")
    if f["applies_to"] not in _APPLIES_TO:
        raise KnowledgeError(f"{where}: applies_to must be one of {', '.join(_APPLIES_TO)}")
    if f["encoding"] not in _ENCODINGS:
        raise KnowledgeError(f"{where}: encoding must be one of {', '.join(_ENCODINGS)}")
    if f["capital_font"] not in ("true", "false", ""):
        raise KnowledgeError(f"{where}: capital_font must be true, false or blank")
    if f["capital_font"] and f["encoding"] != "tcvn3":
        raise KnowledgeError(f"{where}: capital_font only applies to tcvn3 rows")
    if f["status"] not in _STATUSES:
        raise KnowledgeError(f"{where}: status must be one of {', '.join(_STATUSES)}")
    for column in ("evidence", "source"):
        if not f[column].strip():
            raise KnowledgeError(f"{where}: {column} must not be blank")
    if f["status"] == "proposed":
        if f["decided_by"] or f["decided_on"]:
            raise KnowledgeError(f"{where}: a proposed row must have blank decided_by and decided_on")
    else:
        if not f["decided_by"].strip():
            raise KnowledgeError(f"{where}: a {f['status']} row needs decided_by")
        try:
            date.fromisoformat(f["decided_on"])
        except ValueError as exc:
            raise KnowledgeError(f"{where}: decided_on must be an ISO date (YYYY-MM-DD)") from exc
    capital = {"true": True, "false": False, "": None}[f["capital_font"]]
    return FontEncodingRow(
        line=number,
        pattern=f["pattern"],
        applies_to=f["applies_to"],
        encoding=cast(TableEncoding, f["encoding"]),
        capital_font=capital,
        status=f["status"],
        evidence=f["evidence"],
        source=f["source"],
        decided_by=f["decided_by"],
        decided_on=f["decided_on"],
    )
