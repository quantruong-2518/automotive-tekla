"""sheet_text: read the text of ONE sheet compactly, and list the sheets of an intake work folder.

Three read-only functions over a work folder that `harness intake` and `harness read-structure` wrote
(`inventory.json`, `text/<path>.json`, `structure/<path>.sheets.json`). Nothing is written, nothing is
decoded or interpreted: entries are returned as the text index holds them (unknown or proposed
encodings keep their flags and stay as stored).

  list_sheets(work_dir)                      one row per detected sheet of every file: detector id, printed
                                             sheet number (with confidence) or null, frame bbox, text count,
                                             blocked text count, title candidates (keyword titles first)
  sheet_text(work_dir, file_rel, sheet_id)   the entries assigned to that sheet in reading order; with
                                             `unassigned=True` instead of a sheet id, the entries on no
                                             sheet or on several (sheet id 'unassigned')
  find_text(work_dir, contains)              the entries containing a text, over all sheets of all files
                                             (or, with `unassigned=True`, over the entries on no sheet)

Legacy-font gate (`text_gate.meaning_block_reason`, computed on the FULL text-index entry): every entry any
tool returns carries `meaning` ("allowed" | "blocked") and `blocked_reason`. A blocked entry is quoted
verbatim with its entry id; no meaning may be taken from it. `sheet_text` also reports the sheet's
`legacy_font_gate` (counts, styles, and the open question ids that ask for the encoding or, for
`legacy_ascii_suspect` entries, what the file's legacy-ASCII style holds: legacy_ascii_text, tool wave 3 W3).

Reading order: rows from the top of the sheet down (larger y first); two entries share a row when their
y differs from the y of the row's FIRST entry by at most 0.6 x the median text height of the sheet (heights
> 0 only; 0 when the sheet has none); inside a row, left to right (smaller x first). Ties break on the entry
id. Entries without a position go last, in id order, with row null. Rotated text is ordered by its anchor
like any other.

`contains` is a plain substring test after Unicode NFC + casefold on both sides. Diacritics are significant
('tầng' does not match 'tang'). Blocked entries are never matched, on any form of their text (tool wave 3,
W4: typing the stored legacy form of a word would otherwise read them); a search is incomplete over them
and says how many there were, a count that does not depend on the query. `sheet_text` output is
capped at `max_entries` (default DEFAULT_MAX_ENTRIES; unbounded with `contains`); the counts are always the
true ones and a truncated output carries a warning naming the `--max` that returns everything.

Shared with `callouts`: `load_inventory`, `load_file`, `sheet_label` and `ReaderError`.
Exit codes (AGENTS.md): 1 the work folder disagrees with itself or an output is invalid, 2 usage.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tekla_harness.questions import LEGACY_ASCII_CODE
from tekla_harness.schemas import validate
from tekla_harness.text_gate import BLOCK_REASONS, meaning_block_reason

SCHEMA_VERSION = "0.1"
STRUCTURE_DIR = "structure"
DEFAULT_MAX_ENTRIES = 400
MAX_TITLES = 5
TITLE_CHARS = 120
ROW_TOLERANCE = 0.6  # x median text height
UNASSIGNED = "unassigned"  # sheet id of the entries on no sheet or on several (--unassigned)
EXIT_INVALID, EXIT_USAGE = 1, 2
MAX_LISTED_PROBLEMS = 20
# registry codes that ask the engineer about the encoding of a file's text (they unblock the gate)
ENCODING_QUESTION_CODES = frozenset(
    {"font_encoding_proposed", "font_encoding_conflict", "text_encoding_hint", "encoding_unknown_non_ascii"}
)
REGISTRY_FILE = "question-registry.json"
LEGACY_ASCII_REASON = "legacy_ascii_suspect"  # the gate reason legacy_ascii_text questions cover (W3)
# title keywords, in rank order; matched as whole words (plural 's' allowed) on NFC + casefold text
TITLE_KEYWORDS = (
    "MẶT BẰNG", "MẶT CẮT", "MẶT ĐỨNG", "CHI TIẾT", "BỐ TRÍ", "THỐNG KÊ", "GHI CHÚ", "DANH MỤC",
    "PLAN", "SECTION", "ELEVATION", "DETAIL", "LAYOUT", "SCHEDULE", "NOTE", "DRAWING LIST", "INDEX",
)  # fmt: skip
_NUMBER = re.compile(r"[+-]?\d+(?:[.,]\d+)?")
_GRID_LABEL = re.compile(r"[^\W_]{1,3}")


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


def row_tolerance(entries: list[dict[str, Any]]) -> float:
    """ROW_TOLERANCE x the median text height of `entries` (heights > 0 only); 0 when there is none."""
    heights = [e["height"] for e in entries if e["height"] is not None and e["height"] > 0]
    return ROW_TOLERANCE * statistics.median(heights) if heights else 0.0


def reading_order(
    entries: list[dict[str, Any]], tol: float | None = None
) -> list[tuple[int | None, dict[str, Any]]]:
    """(row index, entry) in reading order; see the module docstring. `tol`: the row tolerance, by default
    `row_tolerance(entries)` (a region read passes its sheet's)."""
    if tol is None:
        tol = row_tolerance(entries)
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


_KEYWORD_PATTERNS = tuple(
    (kw, re.compile(r"(?<!\w)" + r"\s+".join(re.escape(w) for w in normalize(kw).split()) + r"s?(?!\w)"))
    for kw in TITLE_KEYWORDS
)


def _matching(
    ordered: list[tuple[int | None, dict[str, Any]]], contains: str
) -> list[tuple[int | None, dict[str, Any]]]:
    """The allowed entries whose display_text contains `contains` (NFC + casefold). A blocked entry is
    never compared, on any form of its text: matching it would read it (tool wave 3, W4)."""
    needle = normalize(contains)
    return [
        (r, e)
        for r, e in ordered
        if meaning_block_reason(e) is None and needle in normalize(e["display_text"])
    ]


def _hidden_warning(entries: list[dict[str, Any]]) -> list[str]:
    """One warning when a --contains filter left blocked entries out (whatever the query, so the line says
    nothing about their text)."""
    blocked = sum(meaning_block_reason(e) is not None for e in entries)
    if not blocked:
        return []
    return [
        f"{blocked} blocked (legacy-font) entries are never matched by --contains: read them without "
        "--contains or by entry id"
    ]


def _meaning(e: dict[str, Any]) -> dict[str, Any]:
    """`meaning` and `blocked_reason` of one full text-index entry (see text_gate)."""
    reason = meaning_block_reason(e)
    return {"meaning": "allowed" if reason is None else "blocked", "blocked_reason": reason}


def _compact(row: int | None, e: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "entry_id": e["id"],
        "row": row,
        "display_text": e["display_text"],
        **_meaning(e),
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


def _id_order(qid: str) -> tuple[int, str]:
    return len(qid), qid


def _font_question_ids(reasons: list[str], question_ids: list[str], legacy_ids: list[str]) -> list[str]:
    """The questions that cover these blocked reasons: the encoding questions when a reason an encoding
    answer can lift is present (none lifts `legacy_ascii_suspect`: ASCII stays ASCII in every encoding), and
    the file's legacy_ascii_text questions when `legacy_ascii_suspect` is (tool wave 3, W3; their answer
    records the engineer's reading of the style and decodes nothing)."""
    ids = set(question_ids) if any(r != LEGACY_ASCII_REASON for r in reasons) else set()
    if LEGACY_ASCII_REASON in reasons:
        ids |= set(legacy_ids)
    return sorted(ids, key=_id_order)


def _gate(
    entries: list[dict[str, Any]], question_ids: list[str], legacy_ids: list[str] | None = None
) -> dict[str, Any]:
    """The `legacy_font_gate` block over a set of full entries; `question_ids` per `_font_question_ids`, so
    a sheet with no blocked entry lists no question."""
    reasons = [r for r in (meaning_block_reason(e) for e in entries) if r is not None]
    styles = {e["style"] or "" for e in entries if meaning_block_reason(e) is not None}
    return {
        "blocked_entries": len(reasons),
        "by_reason": {r: reasons.count(r) for r in BLOCK_REASONS if r in reasons},
        "styles": sorted(styles),
        "question_ids": _font_question_ids(reasons, question_ids, legacy_ids or []),
    }


def _encoding_question_ids(inv: Inventory, file_rel: str) -> tuple[list[str], list[str], list[str]]:
    """(encoding ids, legacy_ascii_text ids, warnings): non-obsolete registry questions of this file asking
    about the text encoding, and those asking what a legacy-ASCII style holds."""
    path = inv.work / REGISTRY_FILE
    if not path.is_file():
        return [], [], [f"{REGISTRY_FILE} is missing: legacy_font_gate.question_ids is empty"]
    registry = read_json(path, REGISTRY_FILE)
    live = [
        q
        for q in registry.get("questions", {}).values()
        if q.get("file") == file_rel and q.get("status") != "obsolete"
    ]
    encoding = [q["id"] for q in live if q.get("code") in ENCODING_QUESTION_CODES]
    legacy = [q["id"] for q in live if q.get("code") == LEGACY_ASCII_CODE]
    return sorted(encoding, key=_id_order), sorted(legacy, key=_id_order), []


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


def _unassigned_entries(loaded: LoadedFile) -> list[dict[str, Any]]:
    """The entries on no sheet or on several (sheets document `unassigned`), each once, ids the index lacks
    left out."""
    assert loaded.text_index is not None and loaded.sheets is not None
    by_id = index_by_id(loaded.text_index)
    off_sheet = loaded.sheets["unassigned"]
    ids = dict.fromkeys([*off_sheet["text_ids"], *off_sheet["ambiguous_text_ids"]])
    return [by_id[tid] for tid in ids if tid in by_id]


def _space_key(space: str) -> tuple[bool, str]:
    return space != "model", space


def unassigned_order(entries: list[dict[str, Any]]) -> list[tuple[int | None, dict[str, Any]]]:
    """Reading order of entries from several spaces: model space first, then the layouts by name, each in
    `reading_order`; row numbers go on from one space to the next, so a row never mixes two spaces."""
    ordered: list[tuple[int | None, dict[str, Any]]] = []
    offset = 0
    for space in sorted({e["space"] for e in entries}, key=_space_key):
        part = reading_order([e for e in entries if e["space"] == space])
        rows = [r for r, _ in part if r is not None]
        ordered.extend((None if r is None else r + offset, e) for r, e in part)
        offset += max(rows) + 1 if rows else 0
    return ordered


def _title_keyword(text: str) -> str | None:
    norm = " ".join(normalize(text).split())
    return next((kw for kw, pattern in _KEYWORD_PATTERNS if pattern.search(norm)), None)


def _is_title_candidate(text: str) -> bool:
    """Not empty, not a grid label (1-3 letters or digits), not a bare number or year."""
    return bool(text) and not _GRID_LABEL.fullmatch(text) and not _NUMBER.fullmatch(text)


def _titles(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Title candidates: entries with a title keyword first, then the others, each by height, then id.
    A blocked entry never matches a keyword (no meaning may be taken from it)."""
    candidates = []
    for e in entries:
        text = " ".join(e["display_text"].split())
        if e["height"] is None or not _is_title_candidate(text):
            continue
        meaning = _meaning(e)
        keyword = _title_keyword(text) if meaning["meaning"] == "allowed" else None
        candidates.append((keyword is None, -e["height"], e["id"], text, keyword, e, meaning))
    candidates.sort(key=lambda c: c[:3])
    seen: set[str] = set()
    titles = []
    for _, _, _, text, keyword, e, meaning in candidates:
        if text in seen:
            continue
        seen.add(text)
        cut = len(text) > TITLE_CHARS
        titles.append(
            {
                "entry_id": e["id"],
                "display_text": text[:TITLE_CHARS] + ("…" if cut else ""),
                **meaning,
                "matched_keyword": keyword,
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
            "blocked_text_count": None,
        }
        files.append(entry)
        if loaded.skip is not None or loaded.text_index is None:
            entry.update(status="skipped", reason=loaded.skip)
            continue
        entry["text_entries"] = len(loaded.text_index["entries"])
        if loaded.sheets is None:
            entry.update(status="skipped", reason="no sheets document (run `harness read-structure`)")
            continue
        # the whole file, on a sheet or not (tool wave 2, fix 11)
        entry["blocked_text_count"] = sum(
            meaning_block_reason(e) is not None for e in loaded.text_index["entries"]
        )
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
                    "blocked_text_count": sum(meaning_block_reason(e) is not None for e in entries),
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


def truncation_warning(doc: dict[str, Any]) -> str | None:
    """One line naming the `--max` that returns everything, or None when the output is complete."""
    counts = doc["counts"]
    if not counts["truncated"]:
        return None
    return (
        f"sheet-text truncated: {counts['returned']} of {counts['matched']} matching entries returned "
        f"({counts['omitted']} omitted); rerun with --max {counts['assigned']} to get all of them"
    )


def _file_row(inv: Inventory, file_rel: str) -> dict[str, Any]:
    rows = [r for r in inv.doc["files"] if r["path"] == file_rel]
    if not rows:
        known = ", ".join(sorted(r["path"] for r in inv.doc["files"] if r["format"] in ("dwg", "dxf")))
        raise ReaderError(EXIT_USAGE, f"'{file_rel}' is not in inventory.json (DXF/DWG files: {known})")
    return rows[0]


def sheet_text(
    work_dir: Path | str,
    file_rel: str,
    sheet_id: str | None,
    *,
    contains: str | None = None,
    max_entries: int | None = None,
    check_inputs: bool = False,
    unassigned: bool = False,
    region: tuple[float, float, float, float] | None = None,
    include_hidden: bool = False,
) -> dict[str, Any]:
    """The text of one sheet in reading order. Raises ReaderError. See `load_file`.

    `include_hidden` (tool wave 4, package T fills it in): also return the entries that do not print, marked.

    `max_entries` None: DEFAULT_MAX_ENTRIES, or unbounded when `contains` filters (query.max_entries is the
    effective value, null = unbounded). `legacy_font_gate` covers ALL entries assigned to the sheet.
    `unassigned` (instead of a sheet id; tool wave 2, fix 4): the entries on no sheet or on several, as
    sheet `unassigned` with null layout and bbox; its `space` names the spaces of those entries (model
    first, then layouts by name, ', '-separated; 'none' when there is no such entry), and they are read in
    `unassigned_order`. This is how the text of a file without a detected sheet is reached.
    `region` (with a sheet id only): see `sheet_region`."""
    if include_hidden:
        raise NotImplementedError("tool wave 4 package T")
    if (sheet_id is None) == (not unassigned):
        raise ReaderError(EXIT_USAGE, "give either a sheet id or --unassigned, not both and not neither")
    if region is not None and unassigned:
        raise ReaderError(
            EXIT_USAGE, "a region reads a box of ONE sheet: give its sheet id, not --unassigned"
        )
    if max_entries is not None and max_entries < 1:
        raise ReaderError(EXIT_USAGE, "max_entries must be at least 1")
    inv = load_inventory(work_dir)
    loaded = load_file(inv, _file_row(inv, file_rel), check_inputs=check_inputs)
    if loaded.skip is not None or loaded.text_index is None:
        raise ReaderError(EXIT_USAGE, f"{file_rel} has no text to read: {loaded.skip}")
    if loaded.sheets is None:
        raise ReaderError(EXIT_USAGE, f"{file_rel}: " + "; ".join(loaded.warnings))
    tol = 0.0  # the sheet's row tolerance; a region read needs it (never with --unassigned)
    if unassigned:
        entries = _unassigned_entries(loaded)
        ordered = unassigned_order(entries)
        spaces = sorted({e["space"] for e in entries}, key=_space_key)
        sheet = {
            "sheet_id": UNASSIGNED,
            "space": ", ".join(spaces) or "none",
            "layout": None,
            "bbox": None,
            "sheet_number": None,
            "duplicate_of": None,
        }
    else:
        found = [s for s in loaded.sheets["sheets"] if s["sheet_id"] == sheet_id]
        if not found:
            ids = [s["sheet_id"] for s in loaded.sheets["sheets"]]
            shown = ", ".join(ids[:MAX_LISTED_PROBLEMS]) + (" ..." if len(ids) > MAX_LISTED_PROBLEMS else "")
            raise ReaderError(
                EXIT_USAGE,
                f"{file_rel} has no sheet '{sheet_id}' (sheets: {shown or 'none'}; "
                "--unassigned reads the text on no sheet)",
            )
        sh = found[0]
        entries = _sheet_entries(loaded, sh)
        tol = row_tolerance(entries)
        if region is None:
            ordered = reading_order(entries, tol)
        else:
            ordered = reading_order([e for e in entries if _in_box(e, region)], tol)
        sheet = {
            "sheet_id": sh["sheet_id"],
            "space": sh["space"],
            "layout": sh["layout"],
            "bbox": sh["bbox"],
            "sheet_number": printed_number(sh),
            "duplicate_of": sh["duplicate_of"],
        }
    hidden: list[str] = []
    if contains is not None and contains != "":
        matched = _matching(ordered, contains)
        hidden = _hidden_warning(entries)
    else:
        contains = None
        matched = ordered
        if max_entries is None:
            max_entries = DEFAULT_MAX_ENTRIES
    shown = matched if max_entries is None else matched[:max_entries]
    question_ids, legacy_ids, id_warnings = _encoding_question_ids(inv, file_rel)
    doc = {
        "schema_version": SCHEMA_VERSION,
        "kind": "sheet_text",
        "project_id": inv.doc["project_id"],
        "file": file_rel,
        "sheet": sheet,
        "query": {
            "contains": contains,
            "max_entries": max_entries,
            **({"unassigned": True} if unassigned else {}),
            **({"region": list(region)} if region is not None else {}),
        },
        "counts": {
            "assigned": len(entries),
            "matched": len(matched),
            "returned": len(shown),
            "omitted": len(matched) - len(shown),
            "truncated": len(shown) < len(matched),
        },
        "legacy_font_gate": _gate(entries, question_ids, legacy_ids),
        "entries": [_compact(r, e) for r, e in shown],
        "warnings": [*loaded.warnings, *id_warnings, *hidden],
    }
    if region is not None:
        rows, renumbered = _region_rows(shown, ordered, tol)
        doc["region"] = list(region)
        doc["rows"] = rows
        doc["entries"] = [_compact(renumbered[e["id"]], e) for _, e in shown]
        doc["warnings"].extend(_outside_warning(region, sheet))
    warning = truncation_warning(doc)
    if warning:
        doc["warnings"].append(warning)
    return _check_output(doc)


def find_text(
    work_dir: Path | str,
    contains: str,
    *,
    file_rel: str | None = None,
    max_hits: int | None = None,
    check_inputs: bool = False,
    unassigned: bool = False,
    include_hidden: bool = False,
) -> dict[str, Any]:
    """Every entry of every sheet of every file (or of `file_rel`) whose text contains `contains`.

    Hits come in file path, sheet and reading order. `max_hits` None: unbounded; `counts.hits` is always
    the true number. Blocked entries are never matched, on their stored, decoded or any normalised text
    (tool wave 3, W4): matching would read them. `counts.blocked_in_scope` is how many there are in the
    searched files or sheets, the same for every query, and `notes` says the search is incomplete over
    them. Entries on no sheet or on several sheets are not searched (counted separately).
    `unassigned` (tool wave 2, fix 4): search only those entries instead, in `unassigned_order`; hits carry
    sheet_id 'unassigned' and a null sheet_number, `counts.unassigned_entries_searched` says how many."""
    if include_hidden:
        raise NotImplementedError("tool wave 4 package T")
    if not contains:
        raise ReaderError(EXIT_USAGE, "find-text needs a non-empty --contains")
    if max_hits is not None and max_hits < 1:
        raise ReaderError(EXIT_USAGE, "max_hits must be at least 1")
    inv = load_inventory(work_dir)
    if file_rel is not None:
        rows = [_file_row(inv, file_rel)]
    else:
        rows = [r for r in sorted(inv.doc["files"], key=lambda r: r["path"]) if r["format"] in ("dwg", "dxf")]
    warnings: list[str] = []
    stale = stale_warning(inv)
    if stale:
        warnings.append(stale)
    needle = normalize(contains)
    files: list[dict[str, Any]] = []
    hits: list[dict[str, Any]] = []
    font_ids: set[str] = set()  # the questions covering the blocked entries in scope (W3)
    for row in rows:
        loaded = load_file(inv, row, check_inputs=check_inputs)
        warnings.extend(f"{loaded.rel}: {w}" for w in loaded.warnings)
        summary: dict[str, Any] = {
            "path": loaded.rel,
            "status": "searched",
            "reason": None,
            "sheets_searched": 0,
            "entries_searched": 0,
            "blocked_entries": 0,
            "unassigned_entries": None,
            "hits": 0,
        }
        files.append(summary)
        if loaded.skip is not None or loaded.text_index is None:
            summary.update(status="skipped", reason=loaded.skip)
            continue
        if loaded.sheets is None:
            summary.update(status="skipped", reason="no sheets document (run `harness read-structure`)")
            continue
        off_sheet = _unassigned_entries(loaded)
        summary["unassigned_entries"] = len(off_sheet)
        if unassigned:
            groups = [(UNASSIGNED, None, [e for _, e in unassigned_order(off_sheet)])]
        else:
            groups = [
                (
                    sh["sheet_id"],
                    printed_number(sh),
                    [e for _, e in reading_order(_sheet_entries(loaded, sh))],
                )
                for sh in loaded.sheets["sheets"]
            ]
            summary["sheets_searched"] = len(groups)
        reasons: list[str] = []
        for sheet_id, number, entries in groups:
            for e in entries:
                summary["entries_searched"] += 1
                reason = meaning_block_reason(e)
                if reason is not None:  # never compared (W4): reachable by id only
                    summary["blocked_entries"] += 1
                    reasons.append(reason)
                    continue
                if needle not in normalize(e["display_text"]):
                    continue
                summary["hits"] += 1
                hits.append(
                    {
                        "file": loaded.rel,
                        "sheet_id": sheet_id,
                        "sheet_number": number,
                        "entry_id": e["id"],
                        "display_text": e["display_text"],
                        "meaning": "allowed",
                        "blocked_reason": None,
                    }
                )
        if reasons:
            encoding_ids, legacy_ids, id_warnings = _encoding_question_ids(inv, loaded.rel)
            font_ids.update(_font_question_ids(reasons, encoding_ids, legacy_ids))
            warnings.extend(f"{loaded.rel}: {w}" for w in id_warnings)
    blocked = sum(f["blocked_entries"] for f in files)
    off_sheet_total = sum(f["unassigned_entries"] or 0 for f in files)
    shown = hits if max_hits is None else hits[:max_hits]
    notes = []
    if blocked:
        notes.append(
            f"{blocked} blocked entries (unknown, proposed or contradicted font encoding, or legacy-looking "
            "ASCII) in the searched scope are never matched, on any form of their text: this search is "
            "incomplete over them; read them by entry id or with sheet-text, and ask the engineer to approve "
            "the font row"
            + (f" (font questions: {', '.join(sorted(font_ids, key=_id_order))})" if font_ids else "")
        )
    doc = {
        "schema_version": SCHEMA_VERSION,
        "kind": "find_text",
        "project_id": inv.doc["project_id"],
        "query": {
            "contains": contains,
            "file": file_rel,
            "max_hits": max_hits,
            **({"unassigned": True} if unassigned else {}),
        },
        "counts": {
            "hits": len(hits),
            "returned": len(shown),
            "omitted": len(hits) - len(shown),
            "truncated": len(shown) < len(hits),
            "blocked_in_scope": blocked,
            "unassigned_entries_not_searched": 0 if unassigned else off_sheet_total,
            **({"unassigned_entries_searched": off_sheet_total} if unassigned else {}),
        },
        "files": files,
        "hits": shown,
        "notes": notes,
        "warnings": warnings,
    }
    return _check_output(doc)


def sheet_region(
    work_dir: Path | str,
    file_rel: str,
    sheet_id: str,
    region: tuple[float, float, float, float],
    *,
    contains: str | None = None,
    max_entries: int | None = None,
    check_inputs: bool = False,
) -> dict[str, Any]:
    """The entries of one sheet inside `region`, as `harness sheet-text W FILE SHEET --region x0,y0,x1,y1`
    prints them (tool wave 3, a5: a notes-table cell becomes a tool claim, not an eyeball one).

    `region` is x0, y0, x1, y1 in ABSOLUTE coordinates of the sheet's space (the entries' x/y and the
    list-sheets frame bbox; not relative to the frame), x0 < x1 and y0 < y1, all finite. An entry is in the
    box when its insertion point is (edges included); entries without a position never are. The result
    is a `sheet_text` document whose query carries `region`, with top-level `region` and `rows`:
      * rows: the box's entries in reading order (rows and their tolerance as `reading_order`, the
        tolerance taken from the WHOLE sheet's median text height), numbered over the returned entries
        (`entries[].row` indexes `rows`); a row's `y` is its first (topmost) entry's y in the box;
      * cells: inside a row, left to right, a new cell starts where the gap between neighbouring insertion
        x values exceeds that same tolerance; a cell joins its entries' display text with one space, is
        blocked when any entry is (the first blocked entry's reason), and spans x0..x1 (insertion x). A
        blank cell is never invented.
    `counts.assigned` and `legacy_font_gate` stay the whole sheet's (the gate is unchanged); `matched` is
    the box's entries passing `contains` (a blocked entry is never matched); `max_entries` as `sheet_text`.
    A box that misses the sheet's frame gets a warning. Raises ReaderError (2 for a bad region).
    """
    if len(region) != 4 or not all(math.isfinite(v) for v in region):
        raise ReaderError(EXIT_USAGE, f"region must be four finite numbers x0,y0,x1,y1, not {region}")
    x0, y0, x1, y1 = region
    if not (x0 < x1 and y0 < y1):
        raise ReaderError(EXIT_USAGE, f"region {region}: need x0 < x1 and y0 < y1 (the box's corners)")
    return sheet_text(
        work_dir,
        file_rel,
        sheet_id,
        contains=contains,
        max_entries=max_entries,
        check_inputs=check_inputs,
        region=(float(x0), float(y0), float(x1), float(y1)),
    )


def _in_box(entry: dict[str, Any], region: tuple[float, float, float, float]) -> bool:
    x, y = entry["position"]["x"], entry["position"]["y"]
    x0, y0, x1, y1 = region
    return x is not None and y is not None and x0 <= x <= x1 and y0 <= y <= y1


def _region_rows(
    shown: list[tuple[int | None, dict[str, Any]]],
    ordered: list[tuple[int | None, dict[str, Any]]],
    tol: float,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """(rows, entry id -> row index) over the returned entries; see `sheet_region`."""
    anchors: dict[int | None, float] = {}
    for r, e in ordered:  # a row's first entry in `reading_order` is its topmost (the y it was opened at)
        anchors[r] = max(anchors.get(r, e["position"]["y"]), e["position"]["y"])
    rows: list[dict[str, Any]] = []
    index: dict[int | None, int] = {}
    renumbered: dict[str, int] = {}
    last_x = 0.0
    for r, e in shown:
        x = e["position"]["x"]
        if r not in index:
            index[r] = len(rows)
            rows.append({"y": anchors[r], "cells": []})
        cells = rows[index[r]]["cells"]
        if not cells or x - last_x > tol:
            cells.append([])
        cells[-1].append(e)
        last_x = x
        renumbered[e["id"]] = index[r]
    for row in rows:
        row["cells"] = [_cell(group) for group in row["cells"]]
    return rows, renumbered


def _cell(entries: list[dict[str, Any]]) -> dict[str, Any]:
    reasons = [r for r in (meaning_block_reason(e) for e in entries) if r is not None]
    xs = [e["position"]["x"] for e in entries]
    return {
        "entry_ids": [e["id"] for e in entries],
        "display_text": " ".join(e["display_text"] for e in entries),
        "meaning": "blocked" if reasons else "allowed",
        "blocked_reason": reasons[0] if reasons else None,
        "x0": min(xs),
        "x1": max(xs),
    }


def _outside_warning(region: tuple[float, float, float, float], sheet: dict[str, Any]) -> list[str]:
    """A warning when the box does not overlap the sheet's frame (often a frame-relative box)."""
    bbox = sheet["bbox"]
    x0, y0, x1, y1 = region
    if bbox is None or (x0 <= bbox[2] and bbox[0] <= x1 and y0 <= bbox[3] and bbox[1] <= y1):
        return []
    return [
        f"region {list(region)} lies outside the frame of {sheet['sheet_id']} {bbox}: region coordinates "
        "are absolute (the entries' x/y and the list-sheets bbox), not relative to the frame"
    ]
