"""sheet_text: read the text of ONE sheet compactly, and list the sheets of an intake work folder.

Two read-only functions over a work folder that `harness intake` and `harness read-structure` wrote
(`inventory.json`, `text/<path>.json`, `structure/<path>.sheets.json`). Nothing is written, nothing is
decoded or interpreted: entries are returned as the text index holds them (unknown or proposed
encodings keep their flags).

  list_sheets(work_dir)                      one row per detected sheet of every file: detector id, printed
                                             sheet number (with confidence) or null, frame bbox, text count,
                                             the largest texts as title candidates
  sheet_text(work_dir, file_rel, sheet_id)   the entries assigned to that sheet in reading order

Reading order: rows from the top of the sheet down (larger y first); two entries share a row when their
y differs from the y of the row's FIRST entry by at most 0.6 x the median text height of the sheet (heights
> 0 only; 0 when the sheet has none); inside a row, left to right (smaller x first). Ties break on the entry
id. Entries without a position go last, in id order, with row null. Rotated text is ordered by its anchor
like any other.

`contains` is a plain substring test after Unicode NFC + casefold on both sides. Diacritics are significant
('tầng' does not match 'tang'). Output is capped at `max_entries`; the counts are always the true ones.

Shared with `callouts`: `load_inventory`, `load_file`, `sheet_label` and `ReaderError`.
Exit codes (AGENTS.md): 1 the work folder disagrees with itself or an output is invalid, 2 usage.
"""

from __future__ import annotations

import hashlib
import json
import statistics
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tekla_harness.schemas import validate

SCHEMA_VERSION = "0.1"
STRUCTURE_DIR = "structure"
DEFAULT_MAX_ENTRIES = 400
MAX_TITLES = 5
TITLE_CHARS = 120
ROW_TOLERANCE = 0.6  # x median text height
EXIT_INVALID, EXIT_USAGE = 1, 2
MAX_LISTED_PROBLEMS = 20


class ReaderError(Exception):
    """A request that cannot be answered; `exit_code` follows AGENTS.md (1 inconsistent/invalid, 2 usage)."""

    def __init__(self, exit_code: int, message: str) -> None:
        super().__init__(message)
        self.exit_code = exit_code


# --- loading ---------------------------------------------------------------------------------------


@dataclass
class LoadedFile:
    """One inventory row with its documents. `skip` is set when there is nothing to read."""

    rel: str
    row: dict[str, Any]
    skip: str | None = None
    text_index: dict[str, Any] | None = None
    sheets: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class Inventory:
    work: Path
    doc: dict[str, Any]
    sha256: str


def _details(problems: list[Any]) -> str:
    shown = [f"{p.path}: {p.message}" for p in problems[:3]]
    more = f" (+{len(problems) - 3} more)" if len(problems) > 3 else ""
    return "; ".join(shown) + more


def read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise ReaderError(EXIT_INVALID, f"{label} cannot be read: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ReaderError(EXIT_INVALID, f"{label} is not valid JSON: {exc}") from exc


def _read_checked(path: Path, schema: str, label: str, *, full: bool = True) -> Any:
    """Parse a document. `full`: validate it against its schema (seconds for a big text index);
    otherwise only the version is checked."""
    doc = read_json(path, label)
    if full:
        problems = validate(schema, doc)
        if problems:
            raise ReaderError(
                EXIT_INVALID, f"{label} is invalid against the {schema} schema: {_details(problems)}"
            )
    elif not isinstance(doc, dict) or doc.get("schema_version") != SCHEMA_VERSION:
        raise ReaderError(EXIT_INVALID, f"{label} is not a {schema} document of version {SCHEMA_VERSION}")
    return doc


def _inside(work: Path, rel: str, what: str) -> Path:
    path = (work / rel).resolve()
    if path != work and work not in path.parents:
        raise ReaderError(EXIT_INVALID, f"{what} '{rel}' is outside the work folder")
    return path


def load_inventory(work_dir: Path | str) -> Inventory:
    work = Path(work_dir).resolve()
    if not work.is_dir():
        raise ReaderError(EXIT_USAGE, f"work folder not found (not a folder): {work_dir}")
    path = work / "inventory.json"
    if not path.is_file():
        raise ReaderError(EXIT_USAGE, f"{work} has no inventory.json: run `harness intake` first")
    doc = _read_checked(path, "intake", "inventory.json")
    if doc.get("kind") != "inventory":
        raise ReaderError(EXIT_INVALID, "inventory.json has the wrong 'kind'")
    return Inventory(work, doc, hashlib.sha256(path.read_bytes()).hexdigest())


def load_file(inv: Inventory, row: dict[str, Any], *, check_inputs: bool = False) -> LoadedFile:
    """Load the text index and sheets document of one inventory row. Raises ReaderError when they disagree.

    `check_inputs`: validate both against their schemas (slow on big files). The default only checks the
    version and that both documents were built from the same DXF (sha256)."""
    rel = row["path"]
    loaded = LoadedFile(rel, row)
    if row["format"] not in ("dwg", "dxf"):
        loaded.skip = f"no text index for format {row['format']}"
        return loaded
    if row["text_index"] is None:
        loaded.skip = "no text index was computed for this file (see read-log.json)"
        return loaded
    ti_path = _inside(inv.work, row["text_index"], f"{rel}: text index")
    if not ti_path.is_file():
        raise ReaderError(EXIT_INVALID, f"{rel}: text index {row['text_index']} is missing")
    index = _read_checked(ti_path, "text-index", f"{rel}: text index", full=check_inputs)
    if index["status"] == "unreadable":
        loaded.skip = f"the text index is unreadable: {index.get('error', 'no reason given')}"
        return loaded
    loaded.text_index = index
    sheets_rel = f"{STRUCTURE_DIR}/{rel}.sheets.json"
    sheets_path = _inside(inv.work, sheets_rel, f"{rel}: sheets document")
    if not sheets_path.is_file():
        loaded.warnings.append(f"{sheets_rel} is missing: run `harness read-structure` (sheets unknown)")
        return loaded
    sheets = _read_checked(sheets_path, "sheets", f"{rel}: {sheets_rel}", full=check_inputs)
    if sheets["file"]["sha256"] != index["file"]["sha256"]:
        raise ReaderError(
            EXIT_INVALID,
            f"{rel}: {sheets_rel} was built from another DXF than the text index "
            "(sha256 differs): rerun `harness read-structure`",
        )
    loaded.sheets = sheets
    return loaded


def stale_warning(inv: Inventory) -> str | None:
    """A warning when structure-summary.json was built from another inventory.json."""
    path = inv.work / "structure-summary.json"
    if not path.is_file():
        return None
    try:
        recorded = json.loads(path.read_text(encoding="utf-8")).get("inventory_sha256")
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        return "structure-summary.json cannot be read: cannot check that structure/ is current"
    if recorded != inv.sha256:
        return "structure/ is stale: structure-summary.json was built from another inventory.json"
    return None


def index_by_id(text_index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {e["id"]: e for e in text_index["entries"]}


def printed_number(sheet: dict[str, Any]) -> dict[str, str] | None:
    """{'value', 'confidence'} of the title block's sheet number, or None when none was settled."""
    number = sheet["title_block"]["sheet_number"]
    return None if number is None else {"value": number["value"], "confidence": number["confidence"]}


def sheet_label(sheet: dict[str, Any] | None) -> str:
    """provenance.sheet: the printed sheet number as read, else 'unknown'. The detector id never stands in."""
    if sheet is None:
        return "unknown"
    number = sheet["title_block"]["sheet_number"]
    return "unknown" if number is None else number["value"]


# --- reading order -------------------------------------------------------------------------------------


def reading_order(entries: list[dict[str, Any]]) -> list[tuple[int | None, dict[str, Any]]]:
    """(row index, entry) in reading order; see the module docstring."""
    heights = [e["height"] for e in entries if e["height"] is not None and e["height"] > 0]
    tol = ROW_TOLERANCE * statistics.median(heights) if heights else 0.0
    placed = sorted(
        (e for e in entries if e["position"]["y"] is not None),
        key=lambda e: (-e["position"]["y"], e["id"]),
    )
    rows: list[list[dict[str, Any]]] = []
    anchor = 0.0
    for e in placed:
        y = e["position"]["y"]
        if not rows or anchor - y > tol:
            rows.append([])
            anchor = y
        rows[-1].append(e)
    ordered: list[tuple[int | None, dict[str, Any]]] = []
    for i, row in enumerate(rows):
        row.sort(key=lambda e: (e["position"]["x"] is None, e["position"]["x"] or 0.0, e["id"]))
        ordered.extend((i, e) for e in row)
    ordered.extend((None, e) for e in sorted((e for e in entries if e["position"]["y"] is None), key=_id))
    return ordered


def _id(entry: dict[str, Any]) -> str:
    return entry["id"]


def normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


def _compact(row: int | None, e: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": e["id"],
        "row": row,
        "display_text": e["display_text"],
        "encoding": e["decode"]["encoding_used"],
        "confidence": e["confidence"],
        "flags": list(e["flags"]),
    }
    if e["decode"]["case_uncertain"]:
        out["case_uncertain"] = True
    out.update(
        layer=e["layer"],
        style=e["style"],
        x=e["position"]["x"],
        y=e["position"]["y"],
        height=e["height"],
        rotation=e["rotation"],
        entity_type=e["entity_type"],
    )
    if e["entity_type"] == "ATTRIB":
        out.update(tag=e["tag"], block_name=e["block_name"])
    return out


# --- public functions ------------------------------------------------------------------------------------


def _check_output(doc: dict[str, Any]) -> dict[str, Any]:
    problems = validate("sheet-text", doc)
    if problems:
        raise ReaderError(EXIT_INVALID, f"internal error: output is invalid: {_details(problems)}")
    return doc


def _sheet_entries(loaded: LoadedFile, sheet: dict[str, Any]) -> list[dict[str, Any]]:
    assert loaded.text_index is not None
    by_id = index_by_id(loaded.text_index)
    return [by_id[tid] for tid in sheet["text_ids"] if tid in by_id]


def _titles(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    titles = []
    ranked = sorted(
        (e for e in entries if e["height"] is not None and e["display_text"].strip()),
        key=lambda e: (-e["height"], e["id"]),
    )
    for e in ranked:
        text = " ".join(e["display_text"].split())
        if text in seen:
            continue
        seen.add(text)
        cut = len(text) > TITLE_CHARS
        titles.append(
            {
                "entry_id": e["id"],
                "display_text": text[:TITLE_CHARS] + ("…" if cut else ""),
                "height": e["height"],
                "truncated": cut,
            }
        )
        if len(titles) == MAX_TITLES:
            break
    return titles


def list_sheets(work_dir: Path | str, *, check_inputs: bool = False) -> dict[str, Any]:
    """Every detected sheet of every file of the work folder. Raises ReaderError. See `load_file`."""
    inv = load_inventory(work_dir)
    warnings: list[str] = []
    stale = stale_warning(inv)
    if stale:
        warnings.append(stale)
    files = []
    for row in sorted(inv.doc["files"], key=lambda r: r["path"]):
        if row["format"] not in ("dwg", "dxf"):
            continue
        loaded = load_file(inv, row, check_inputs=check_inputs)
        warnings.extend(f"{loaded.rel}: {w}" for w in loaded.warnings)
        entry: dict[str, Any] = {
            "path": loaded.rel,
            "status": "listed",
            "reason": None,
            "text_entries": None,
            "unassigned_text": None,
            "sheets": None,
        }
        files.append(entry)
        if loaded.skip is not None or loaded.text_index is None:
            entry.update(status="skipped", reason=loaded.skip)
            continue
        entry["text_entries"] = len(loaded.text_index["entries"])
        if loaded.sheets is None:
            entry.update(status="skipped", reason="no sheets document (run `harness read-structure`)")
            continue
        sheets = []
        for sh in loaded.sheets["sheets"]:
            entries = _sheet_entries(loaded, sh)
            sheets.append(
                {
                    "sheet_id": sh["sheet_id"],
                    "space": sh["space"],
                    "layout": sh["layout"],
                    "bbox": sh["bbox"],
                    "detection_confidence": sh["detection"]["confidence"],
                    "sheet_number": printed_number(sh),
                    "duplicate_of": sh["duplicate_of"],
                    "text_count": len(entries),
                    "titles": _titles(entries),
                }
            )
        entry["sheets"] = sheets
        entry["unassigned_text"] = len(loaded.sheets["unassigned"]["text_ids"]) + len(
            loaded.sheets["unassigned"]["ambiguous_text_ids"]
        )
    listed = [f for f in files if f["status"] == "listed"]
    doc = {
        "schema_version": SCHEMA_VERSION,
        "kind": "sheet_list",
        "project_id": inv.doc["project_id"],
        "files": files,
        "summary": {
            "files": len(files),
            "listed": len(listed),
            "skipped": len(files) - len(listed),
            "sheets": sum(len(f["sheets"]) for f in listed),
            "text_entries": sum(f["text_entries"] or 0 for f in files),
        },
        "warnings": warnings,
    }
    return _check_output(doc)


def sheet_text(
    work_dir: Path | str,
    file_rel: str,
    sheet_id: str,
    *,
    contains: str | None = None,
    max_entries: int = DEFAULT_MAX_ENTRIES,
    check_inputs: bool = False,
) -> dict[str, Any]:
    """The text of one sheet in reading order. Raises ReaderError. See `load_file`."""
    if max_entries < 1:
        raise ReaderError(EXIT_USAGE, "max_entries must be at least 1")
    inv = load_inventory(work_dir)
    rows = [r for r in inv.doc["files"] if r["path"] == file_rel]
    if not rows:
        known = ", ".join(sorted(r["path"] for r in inv.doc["files"] if r["format"] in ("dwg", "dxf")))
        raise ReaderError(EXIT_USAGE, f"'{file_rel}' is not in inventory.json (DXF/DWG files: {known})")
    loaded = load_file(inv, rows[0], check_inputs=check_inputs)
    if loaded.skip is not None or loaded.text_index is None:
        raise ReaderError(EXIT_USAGE, f"{file_rel} has no text to read: {loaded.skip}")
    if loaded.sheets is None:
        raise ReaderError(EXIT_USAGE, f"{file_rel}: " + "; ".join(loaded.warnings))
    found = [s for s in loaded.sheets["sheets"] if s["sheet_id"] == sheet_id]
    if not found:
        ids = [s["sheet_id"] for s in loaded.sheets["sheets"]]
        shown = ", ".join(ids[:MAX_LISTED_PROBLEMS]) + (" ..." if len(ids) > MAX_LISTED_PROBLEMS else "")
        raise ReaderError(EXIT_USAGE, f"{file_rel} has no sheet '{sheet_id}' (sheets: {shown or 'none'})")
    sh = found[0]
    ordered = reading_order(_sheet_entries(loaded, sh))
    if contains is not None and contains != "":
        needle = normalize(contains)
        matched = [(r, e) for r, e in ordered if needle in normalize(e["display_text"])]
    else:
        contains = None
        matched = ordered
    shown = matched[:max_entries]
    doc = {
        "schema_version": SCHEMA_VERSION,
        "kind": "sheet_text",
        "project_id": inv.doc["project_id"],
        "file": file_rel,
        "sheet": {
            "sheet_id": sh["sheet_id"],
            "space": sh["space"],
            "layout": sh["layout"],
            "bbox": sh["bbox"],
            "sheet_number": printed_number(sh),
            "duplicate_of": sh["duplicate_of"],
        },
        "query": {"contains": contains, "max_entries": max_entries},
        "counts": {
            "assigned": len(ordered),
            "matched": len(matched),
            "returned": len(shown),
            "omitted": len(matched) - len(shown),
            "truncated": len(shown) < len(matched),
        },
        "entries": [_compact(r, e) for r, e in shown],
        "warnings": list(loaded.warnings),
    }
    return _check_output(doc)
