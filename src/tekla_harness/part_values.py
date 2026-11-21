"""part_values: `W/parts/<X>/values.json` (schema `part-values`) and the context `harness part check` runs on.

A part reader types its values into `values.json`, one row per mark and field. `load_context(work, part)`
reads everything a check may need, once: the manifest and the part's row, the scope of the part and of its
inputs (the (file, sheet) pairs and (file, sheet, side) clusters its `sheets[]`, `tables[]` and `clusters[]`
list; a sided cluster adds its sheet to `Scope.row_sheets` only), the rows, the findings (with `stale`),
the question registry and the reader questions by id, the
entries of every scope file (`(file, id) -> (text, allowed, printed, sheet)`, one text-index load per file),
`marks.json` and the saved geometry or contents documents the rows and findings cite. The checks of
`part_check`, `part_cites`, `part_numbers`, `part_sums` and `part_rules` only read it.

Reading rules: a file that is not there is absent; any other `OSError` is exit 3; bytes that are not strict
UTF-8 JSON or fail their schema stop the check with the problem `input_invalid` (`values.json` instead gives
`values_invalid`; both are JSON with exit 1, `ContextStop`).
"""

from __future__ import annotations

import re
import stat
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tekla_harness.findings import (
    _NUMBER,
    _TIMES,
    FindingError,
    _document_items,
    _numbers,
    is_quote,
    list_findings,
)
from tekla_harness.parts import PART_ID_RE
from tekla_harness.parts_manifest import _os_errors_are_environment, _read_manifest
from tekla_harness.schemas import validate
from tekla_harness.sheet_text import (
    EXIT_USAGE,
    ReaderError,
    index_by_id,
    load_file,
    load_inventory,
    unassigned_clusters,
)
from tekla_harness.strict_json import StrictJsonError, loads_strict
from tekla_harness.text_gate import meaning_block_reason
from tekla_harness.visibility import is_printed

EXIT_INVALID, EXIT_ENV = 1, 3
VALUES_NAME = "values.json"
BOOKKEEPING = "bookkeeping"
SheetKey = tuple[str, str]  # (file, sheet id)
ClusterKey = tuple[str, str | None, str]  # (file, sheet id or None, side)
Entry = tuple[str, bool, bool, str | None]  # (display text, meaning allowed, printed, sheet id or None)


@dataclass(frozen=True)
class Problem:
    """One finding of a check. `row`: the row id; `id`: the cited or owning record id; each may be None."""

    code: str
    row: str | None
    id: str | None
    detail: str

    def sort_key(self) -> tuple[str, str, str, str]:
        return (self.code, self.row or "", self.id or "", self.detail)

    def as_dict(self) -> dict[str, str | None]:
        return {"code": self.code, "row": self.row, "id": self.id, "detail": self.detail}


class ContextStop(Exception):
    """The check cannot go on: the problems (`manifest_invalid`, `part_unknown`, `values_invalid`,
    `input_invalid`) end it."""

    def __init__(self, problems: list[Problem]) -> None:
        super().__init__("; ".join(p.detail for p in problems))
        self.problems = problems


@dataclass(frozen=True)
class Scope:
    sheets: frozenset[SheetKey]  # the (file, sheet) pairs of `sheets[]` and `tables[]`: all their texts
    clusters: frozenset[ClusterKey]
    # `sheets` plus the sheet of every sided cluster: where a row may be written (a row has no `side`). A
    # cluster opens its own `entry_ids`, never the other texts of its sheet.
    row_sheets: frozenset[SheetKey] = frozenset()


@dataclass(frozen=True)
class PartContext:
    work: Path
    part: str
    manifest: dict[str, Any]
    part_row: dict[str, Any]
    own: Scope  # the part's own sheets, tables and clusters
    inputs: Scope  # the same for every part in `part_row["inputs"]`
    views: dict[SheetKey, list[dict[str, Any]]]  # the part's listed `views[]` per sheet
    rows: list[dict[str, Any]]
    findings: dict[str, dict[str, Any]]  # by id, each with `stale`
    registry: dict[str, dict[str, Any]]  # question-registry entries by question id
    questions: dict[str, dict[str, Any]]  # reader-questions.json by question id
    entries: dict[tuple[str, str], Entry]  # (file, entry id) of every scope file
    sheet_entries: dict[SheetKey, frozenset[str]]  # `text_ids` of each scope sheet
    cluster_entries: dict[ClusterKey, frozenset[str]]  # `entry_ids` of each scope cluster
    marks: dict[str, Any] | None
    saved: dict[str, dict[str, Any]]  # saved geometry or contents documents by source path
    grid_systems: dict[str, dict[str, Any]] = field(default_factory=dict)  # `systems[]` of grid-systems.json

    @property
    def scope(self) -> Scope:
        """The part's own scope plus its inputs'."""
        return Scope(
            self.own.sheets | self.inputs.sheets,
            self.own.clusters | self.inputs.clusters,
            self.own.row_sheets | self.inputs.row_sheets,
        )


def _read_bytes(work: Path, rel: str) -> bytes | None:
    """The bytes of `work/rel`, None when it is not there. Raises ReaderError(3) for another OSError."""
    try:
        return (work / rel).read_bytes()
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError as exc:
        raise ReaderError(EXIT_ENV, f"cannot read {rel} ({exc})") from exc


def _read_document(work: Path, rel: str, schema: str) -> dict[str, Any] | None:
    """A document that may be absent. Raises ReaderError (3 unreadable; 1 not strict JSON or not `schema`)."""
    data = _read_bytes(work, rel)
    if data is None:
        return None
    try:
        doc = loads_strict(data)
    except StrictJsonError as exc:
        raise ReaderError(EXIT_INVALID, f"{rel} is not valid JSON: {exc}") from exc
    problems = validate(schema, doc)
    if problems:
        raise ReaderError(
            EXIT_INVALID, f"{rel} is invalid ({schema}): {problems[0].path}: {problems[0].message}"
        )
    return doc  # type: ignore[no-any-return]


def _input_document(work: Path, rel: str, schema: str) -> dict[str, Any] | None:
    """`_read_document` for the check: a malformed document stops it with `input_invalid` (the part reader
    cannot fix a tool-written file in `values.json`), the other errors keep their exit code."""
    try:
        return _read_document(work, rel, schema)
    except ReaderError as exc:
        if exc.exit_code == EXIT_INVALID:
            raise ContextStop([Problem("input_invalid", None, None, str(exc))]) from exc
        raise


def read_values(work: Path, part: str, kind: str) -> tuple[dict[str, Any] | None, list[Problem]]:
    """(the values document, []) when `parts/<part>/values.json` parses and matches the schema and its
    `part`, else (None, one `values_invalid` problem). A bookkeeping part may have no file: zero rows."""
    rel = f"parts/{part}/{VALUES_NAME}"

    def invalid(detail: str) -> tuple[None, list[Problem]]:
        return None, [Problem("values_invalid", None, None, detail)]

    path = work / rel
    try:
        try:
            regular = stat.S_ISREG(path.stat().st_mode)
        except (FileNotFoundError, NotADirectoryError):
            if kind == BOOKKEEPING:
                return {"schema_version": "0.1", "part": part, "rows": []}, []
            return invalid(f"{rel} is missing: the part reader writes it")
        if not regular:  # decided before any open: a named pipe would block it
            return invalid(f"{rel} is not a regular file")
        data = path.read_bytes()
    except OSError as exc:
        raise ReaderError(EXIT_ENV, f"cannot read {rel} ({exc})") from exc
    try:
        doc = loads_strict(data)
    except StrictJsonError as exc:
        return invalid(f"{rel} is not valid JSON: {exc}")
    found = validate("part-values", doc)
    if found:
        return invalid(f"{rel}: " + "; ".join(f"{p.path or '/'}: {p.message}" for p in found[:3]))
    if doc["part"] != part:
        return invalid(f"{rel}: part is '{doc['part']}', not '{part}'")
    return doc, []


def _scope(parts: list[dict[str, Any]]) -> tuple[Scope, dict[SheetKey, list[dict[str, Any]]]]:
    sheets: set[SheetKey] = set()
    clusters: set[ClusterKey] = set()
    views: dict[SheetKey, list[dict[str, Any]]] = {}
    for p in parts:
        for s in p.get("sheets", []):
            sheets.add((s["file"], s["sheet"]))
            views.setdefault((s["file"], s["sheet"]), []).extend(s.get("views", []))
        for t in p.get("tables", []):
            if "cluster" in t:
                clusters.add((t["cluster"]["file"], t["cluster"]["sheet"], t["cluster"]["side"]))
            else:
                sheets.add((t["file"], t["sheet"]))
        clusters.update((c["file"], c["sheet"], c["side"]) for c in p.get("clusters", []))
    row_sheets = sheets | {(f, s) for f, s, _ in clusters if s is not None}
    return Scope(frozenset(sheets), frozenset(clusters), frozenset(row_sheets)), views


def load_context(work_dir: Path | str, part: str) -> PartContext:
    """Everything the checks of `part` read. Raises ReaderError (usage 2: a part id that does not match
    PART_ID_RE, no work folder or inventory.json, a scope file without its sheets document; environment 3:
    a file the operating system refuses) and ManifestAccessError (3), and ContextStop when the manifest, the
    part, `values.json` or a findings, questions, registry, marks or grid-systems document is unusable."""
    work = Path(work_dir)
    if not PART_ID_RE.fullmatch(part):
        raise ReaderError(EXIT_USAGE, f"--part '{part}' must match {PART_ID_RE.pattern}")
    with _os_errors_are_environment():
        inv = load_inventory(work)
    work = inv.work
    manifest, found = _read_manifest(work)
    if manifest is None:
        raise ContextStop([Problem("manifest_invalid", None, None, "; ".join(p[4] for p in found[:3]))])
    part_row = next((p for p in manifest["parts"] if p["id"] == part), None)
    if part_row is None:
        raise ContextStop(
            [Problem("part_unknown", None, part, f"'{part}' is not in parts[] of the manifest")]
        )
    values, problems = read_values(work, part, part_row["kind"])
    if values is None:
        raise ContextStop(problems)

    by_id = {p["id"]: p for p in manifest["parts"]}
    own, views = _scope([part_row])
    inputs, _ = _scope([by_id[i] for i in part_row.get("inputs", []) if i in by_id])
    scope = Scope(
        own.sheets | inputs.sheets, own.clusters | inputs.clusters, own.row_sheets | inputs.row_sheets
    )

    findings_doc = None
    if _read_bytes(work, "reader-findings.json") is not None:  # unreadable -> exit 3 here, not "no findings"
        try:
            findings_doc = list_findings(work)
        except FindingError as exc:
            if exc.exit_code == EXIT_INVALID:
                raise ContextStop([Problem("input_invalid", None, None, str(exc))]) from exc
            raise ReaderError(exc.exit_code, str(exc)) from exc
    registry_doc = _input_document(work, "question-registry.json", "question-registry")
    questions_doc = _input_document(work, "reader-questions.json", "reader-questions")
    marks = _input_document(work, "marks.json", "marks")

    files = {f for f, _ in scope.sheets} | {f for f, _, _ in scope.clusters}
    entries: dict[tuple[str, str], Entry] = {}
    sheet_entries: dict[SheetKey, frozenset[str]] = {}
    for row in sorted(inv.doc["files"], key=lambda r: r["path"]):
        rel = row["path"]
        if row["format"] not in ("dwg", "dxf") or rel not in files:
            continue
        with _os_errors_are_environment():
            loaded = load_file(inv, row)
        if loaded.text_index is None:
            continue
        if loaded.sheets is None:
            raise ReaderError(EXIT_USAGE, f"{rel}: " + "; ".join(loaded.warnings))
        sheet_of: dict[str, str] = {}
        for sheet in loaded.sheets["sheets"]:
            sheet_entries[(rel, sheet["sheet_id"])] = frozenset(sheet["text_ids"])
            for tid in sheet["text_ids"]:
                sheet_of.setdefault(tid, sheet["sheet_id"])
        for tid, e in index_by_id(loaded.text_index).items():
            entries[(rel, tid)] = (
                e["display_text"],
                meaning_block_reason(e) is None,
                is_printed(e),
                sheet_of.get(tid),
            )
    cluster_entries: dict[ClusterKey, frozenset[str]] = {}
    for file in sorted({f for f, _, _ in scope.clusters}):
        with _os_errors_are_environment():
            found_clusters = unassigned_clusters(work, file_rel=file)["clusters"]
        for c in found_clusters:
            cluster_entries[(c["file"], c["sheet_id"], c["side"])] = frozenset(c["entry_ids"])

    findings = {f["id"]: f for f in (findings_doc or {}).get("findings", [])}
    registry = {q["id"]: q for q in (registry_doc or {}).get("questions", {}).values()}
    questions = {q["id"]: q for q in (questions_doc or {}).get("questions", [])}
    saved: dict[str, dict[str, Any]] = {}
    sources = {r["cites"]["geometry"]["source"] for r in values["rows"] if "geometry" in r.get("cites", {})}
    sources |= {f["evidence"]["source"] for f in findings.values() if "evidence" in f}
    for source in sorted(sources):
        doc = _read_saved(work, source)
        if doc is not None:
            saved[source] = doc
    grid_systems: dict[str, dict[str, Any]] = {}
    if any(r.get("cites", {}).get("grid_systems") for r in values["rows"]):  # read only when a row cites one
        systems_doc = _input_document(work, "grid-systems.json", "grid-system")
        grid_systems = {s["system_id"]: s for s in (systems_doc or {}).get("systems", [])}
    return PartContext(
        work, part, manifest, part_row, own, inputs, views, values["rows"], findings, registry, questions,
        entries, sheet_entries, cluster_entries, marks, saved, grid_systems,
    )  # fmt: skip


def _read_saved(work: Path, source: str) -> dict[str, Any] | None:
    """A saved geometry or contents document; None when it is not there or not usable (a cite of it is then
    `cite_unknown`). Raises ReaderError(3) for an OSError other than not-found."""
    data = _read_bytes(work, source)
    if data is None:
        return None
    try:
        doc = loads_strict(data)
    except StrictJsonError:
        return None
    if not isinstance(doc, dict) or doc.get("kind") not in ("geometry", "contents"):
        return None
    return doc if validate(doc["kind"], doc) == [] else None


# --- sources of a row: what a number or a glued token of its value is looked up in ------------------------

_ITEM_NUMBERS = ("short", "long", "diameter")
_DIGIT = re.compile(r"\d")


@dataclass(frozen=True)
class Source:
    """One cited record as a place a value is read in. `texts`: strings whose standalone numbers back a number
    exactly and whose wording backs a quote; `items`: measures (short, long, diameter) that back a number
    within `tol`; `exact`: counts (symbols, the item count) that back a number only exactly."""

    label: str  # the cited id (a finding, question or entry id, or the saved document's path)
    texts: tuple[str, ...] = ()
    items: tuple[float, ...] = ()
    tol: float = 0.0
    exact: tuple[float, ...] = ()


def _item_numbers(items: list[dict[str, Any]]) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """(the measures, within tol; the symbols and the item count, exact) of a list of items."""
    measures = [float(i[k]) for i in items for k in _ITEM_NUMBERS if i.get(k) is not None]
    counts = [float(i["symbols"]) for i in items if i.get("symbols") is not None]
    return tuple(measures), (*counts, float(len(items)))


def _finding_source(finding: dict[str, Any]) -> Source:
    texts = [finding["value"]] if isinstance(finding.get("value"), str) else []
    texts += [e["display_text"] for e in finding.get("entries", [])]
    evidence = finding.get("evidence")
    if evidence is None:
        return Source(finding["id"], tuple(texts))
    measures, counts = _item_numbers(evidence["items"])
    return Source(finding["id"], tuple(texts), measures, float(evidence["query"]["tol"]), counts)


def sources(ctx: PartContext, row: dict[str, Any]) -> list[Source]:
    """The sources of one row, in the order it cites them: its entries (of `row.file`), findings, saved
    geometry items and, for an `asked` row only, its questions (`message` and each ref's `found`). A cited
    record that does not exist is no source (the citation check reports it)."""
    cites = row.get("cites", {})
    found: list[Source] = []
    file: str | None = row.get("file")
    entry_ids: list[str] = cites.get("entries", []) if file is not None else []
    for tid in entry_ids:
        entry = ctx.entries.get((file or "", tid))
        if entry is not None:
            found.append(Source(tid, (entry[0],)))
    found += [_finding_source(ctx.findings[f]) for f in cites.get("findings", []) if f in ctx.findings]
    geometry = cites.get("geometry")
    doc = ctx.saved.get(geometry["source"]) if geometry else None
    if geometry and doc is not None:
        listed = _document_items(doc)
        picked = [listed[i] for i in geometry["items"] if i in listed]
        measures, counts = _item_numbers(picked)
        found.append(Source(geometry["source"], (), measures, float(doc["query"]["tol"]), counts))
    if row["state"] == "asked":
        for qid in cites.get("questions", []):
            q = ctx.questions.get(qid)
            if q is not None:
                found.append(Source(qid, (q["message"], *(r["found"] for r in q["refs"]))))
    return found


def glued_tokens(value: str) -> list[str]:
    """The whitespace tokens of `value` with a digit outside every standalone number (after `NxM` is split):
    `-1.200`, `2Ø16`, `-0,450`, `C30/37`, `24M`, `1-1`. `D400` is the number 400 and `400x600` the numbers
    400 and 600: neither is glued."""
    glued: list[str] = []
    for token in value.split():
        split = _TIMES.sub(" ", token)
        covered = {i for m in _NUMBER.finditer(split) for i in range(*m.span(1))}
        if any(m.start() not in covered for m in _DIGIT.finditer(split)):
            glued.append(token)
    return glued


def same_value(a: str, b: str) -> bool:
    """Two values say the same: equal after NFC, case folding, removing whitespace and `\u00d7` -> `x`; else
    the standalone numbers (`findings._numbers`) of both exist and are equal as sorted lists, so `(SL: 7)` is
    `7` and `1500x2400` is `2400x1500`, but `B22.5(M300)` is not `B25(M350)` (no number: the text decides)."""

    def text(value: str) -> str:
        return "".join(unicodedata.normalize("NFC", value).casefold().split()).replace("\u00d7", "x")

    if text(a) == text(b):
        return True
    na, nb = _numbers(a), _numbers(b)
    return bool(na) and bool(nb) and sorted(na) == sorted(nb)


def backs(source: Source, value: float | str) -> bool:
    """A number: equal to a standalone number of a source text or to a count (`exact`), or within the
    source's `tol` of a measure (`items`). A string (a glued token): a quote of a source text, case-blind
    (`findings.is_quote`)."""
    if isinstance(value, str):
        return any(is_quote(value.casefold(), t.casefold()) for t in source.texts)
    return (
        any(value in _numbers(t) for t in source.texts)
        or value in source.exact
        or any(abs(value - n) <= source.tol for n in source.items)
    )
