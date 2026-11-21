"""parts_manifest: `harness part manifest-check W`, the structural checks of the parts manifest (ADR-0019).

In part mode the scout writes `W/parts/manifest.json` (schema `parts-manifest`): which part reader reads which
sheets, tables and clusters. This command tells the scout whether the manifest is complete and well formed
before any part reader starts. It reads the work folder and writes nothing, so it takes no lock.
(`harness part receipt` is the one action that writes: `part_receipts.write_part_receipt`, under the
work-folder lock.)

A sheet is a (file, sheet id) pair of `harness list-sheets`; a cluster is the (file, sheet id, side) triple of
`harness unassigned-clusters`. Parts of kind `bookkeeping` and `no_sheet` are exempt from the coverage, cap
and block rules (they neither cover a sheet nor count for the size cap or for the blocks of a sheet). The
three warnings (copied plans, grid origin, revision from a table) are not here; `warnings` stays empty.

The kind and the id of a part must agree (`part_kind_mismatch`): the fixed ids carry their kind, a cross part
over the size cap is split as `<fixed id>-<text>` with `split_of` naming the fixed id (it also satisfies
`cross_part_missing`), and a member id is `<block>-<family>` or `<block>-<family>-<text>`. The sheets
of every part, whatever its kind, must exist (`sheet_unknown`). A DWG/DXF that `list-sheets` skips (no text
index, or an unreadable one) is `file_unread` unless a `no_sheet` part names it in `files[]`. A `files[]` item
on a part that is not `no_sheet`, or naming a file that `list-sheets` does not skip (read as sheets, or not an
input file), is `files_entry_unused` (the part, the file; both reasons in one row).

Printed entries of a sheet are what `harness sheet-text W FILE SHEET` returns with no filter and no
limit (`counts.matched`): the entries assigned to the sheet that print. The text index of each file is loaded
once: for its sheets and for its clusters (`sheet_text.file_clusters`).

References the manifest makes are checked against the same load: a `tables[]` item on a sheet that
`list-sheets` does not print is `sheet_unknown`; a cluster (in `clusters[]` or in a table) that
`unassigned-clusters` does not report is `cluster_unknown`; a table whose sheet is not in its part's
`sheets[]` or whose cluster is not in its part's `clusters[]` is `table_outside_part` (not raised again for a
sheet or cluster that is unknown); `number_entry`, `title_entry`, a view's `heading_entry` and a table's
`header_entries` that the sheet (for a table in a cluster: the cluster) does not hold are `entry_unknown`, one
row per field and id; a block id listed twice is `duplicate_block_id` (part null, the id in the detail).

A reader finding (`part`) or reader question (`parts[]`) that names a part the manifest does not list is
`record_part_unknown` (one row per part, `file` and `sheet` null, the record ids in the detail): no part check
would read it. Withdrawn findings do not count. The detail names the commands that clear it
(`harness finding withdraw … --part X`, `harness ask --withdraw … --part X`). The files are read only when the
manifest passed its schema; an absent file means no records, one that is not readable JSON of its schema is
exit 1 and one the operating system refuses is exit 3 (a message naming the file on stderr, no JSON).

A part's `order` must be above the `order` of each of its inputs (`order_not_after_input`), and each
`grid_system_ids` entry of a block must be a `system_id` of `grid-systems.json` (`grid_system_unknown`; with
the file absent every listed id is unknown, an invalid file is exit 1; the file is read only when a block
lists an id).

Three warnings read the drawings (they run on every check, a manifest that passed its schema only):
`grid_origin_other_block` and `linework_duplicate` (`part_warnings.py`; `--input-dir` is where a native DXF
lives) and `revision_from_table` (a revision candidate of `sheets.json` outside the title-block zone of its
sheet: `u >= 1 - CORNER_U or v <= CORNER_V`, 0.75 and 0.20). Each has an id (`warnings[].id`, the fields
joined by `|`). The manifest's `acks[] {warning, question?, reason?}` clears the warning whose id equals
`ack.warning` exactly (`acked`, `ack`). An ack that names no warning is `ack_unmatched`, two acks of one id
are `ack_duplicate`, a `question` that is no id of `question-registry.json` (any status) is
`ack_question_unknown`.
A sheet a warning could not test is in `skipped[] {code, file, sheet, reason}`, never a failure.
The two measuring rules use the answered unit only (the active `units_confirm_all` answer of the file; the
declared unit is never a fall-back). A file with in-scope sheets and no active answer is `unit_unanswered`
(the file; "answer the units question of `<file>` first"); one whose answer cannot be read (the answers
ledger, or active answers with no single valid unit) is `unit_answer_unread` (the file; the warning text).
No ack clears either, and the rules skip the file's sheets as `unit_unknown`.

Output (schema `part-output`, `$defs.manifest_check`): `{ok, sheets: {total, covered}, parts, problems:
[{code, part, file, sheet, detail}], warnings: [{id, code, part, file, sheet, detail, acked, ack}], skipped}`,
problems sorted by (code, part, file, sheet, detail), warnings by id. `ok` is true exactly when the exit code
is 0: no problem and every warning acknowledged.
Exit codes: 0 ok; 1 problems or an unacknowledged warning (a missing manifest, a path that is not a regular
file, bytes that are not strict UTF-8 JSON and a schema failure are each one `schema` problem; an invalid
grid-systems.json or question registry is exit 1 with a message on stderr and no JSON); 2 usage error (no work
folder, no inventory.json, no `question-registry.json`: run `harness intake <input_dir> --out W`, a DWG/DXF
without its `structure/<file>.sheets.json`: run `harness read-structure`); 3 the operating system refused to
check or read the manifest or an input file (a message on stderr, no JSON). The own errors of `read_geometry`
keep their exit code (2 usage, 1 invalid, 3 environment), with a message on stderr and no JSON.
The manifest path follows the one rule of `parts.py` (`manifest_present`, `lstat`).
"""

from __future__ import annotations

import argparse
import json
import re
import stat
import sys
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tekla_harness import part_warnings
from tekla_harness.ask import _load_reader_doc
from tekla_harness.findings import FindingError, _load_doc
from tekla_harness.parts import (
    MANIFEST_REL,
    PART_ID_RE,  # noqa: F401  the schema keeps its own copy of the pattern; a test holds the two equal
    ManifestAccessError,
    manifest_present,
)
from tekla_harness.questions import REGISTRY_FILE, QuestionsError
from tekla_harness.schemas import validate
from tekla_harness.sheet_text import (
    EXIT_USAGE,
    ReaderError,
    file_clusters,
    index_by_id,
    load_file,
    load_inventory,
)
from tekla_harness.sheets import CORNER_U, CORNER_V, _reading_position, _right_angle, box_center, text_box
from tekla_harness.strict_json import StrictJsonError, loads_strict
from tekla_harness.visibility import is_printed

COMMAND = "part"
ANSWER_VERDICTS = ("ok", "wrong", "cannot_tell")
HELP = (
    "part-mode tools (ADR-0019): manifest-check, check, receipt, chain, review-sample, conflicts, spotcheck, "
    "answer-key, score"
)
MAX_SHEETS = 4  # a part reads at most this many sheets ...
MAX_PRINTED_ENTRIES = 1500  # ... and at most this many printed entries over them (a heuristic, G7)
CROSS_PARTS = ("all-grid-levels", "all-notes-materials")  # fixed ids of kind cross
BOOKKEEPING_PARTS = ("scout", "all-assembly")  # fixed ids of kind bookkeeping
NO_SHEET_PARTS = ("all-no-sheet",)  # fixed id of kind no_sheet
FIXED_KINDS = {
    **{pid: "cross" for pid in CROSS_PARTS},
    **{pid: "bookkeeping" for pid in BOOKKEEPING_PARTS},
    **{pid: "no_sheet" for pid in NO_SHEET_PARTS},
}
MAX_RECORD_IDS = 10  # record ids named in the detail of one record_part_unknown
EXEMPT_KINDS = frozenset({"bookkeeping", "no_sheet"})
EXIT_OK, EXIT_INVALID, EXIT_ENV = 0, 1, 3
GRID_SYSTEMS_FILE = "grid-systems.json"

REVISION = "revision_from_table"
NO_POSITION = "no_position"

SheetKey = tuple[str, str]  # (file, sheet id)
ClusterKey = tuple[str, str | None, str]  # (file, sheet id or None, side)
Problem = tuple[str, str | None, str | None, str | None, str]  # (code, part, file, sheet, detail)


@dataclass(frozen=True)
class _Revision:
    """A `revision` candidate of a sheet's title block: the text entry that carries it and where that sits in
    the frame, read along the text (`uv`: None when the entry is not in the index or has no position)."""

    entry: str | None
    value: str
    uv: tuple[float, float] | None


@dataclass
class _Scan:
    """What one load of the inputs gives: per sheet its printed count and the ids of its entries that the text
    index holds; per cluster of `harness unassigned-clusters` its entry ids; the DWG/DXF files with no text to
    read, with the reason."""

    counts: dict[SheetKey, int] = field(default_factory=dict)
    entries: dict[SheetKey, set[str]] = field(default_factory=dict)
    clusters: dict[ClusterKey, set[str]] = field(default_factory=dict)
    skipped: dict[str, str] = field(default_factory=dict)  # DWG/DXF `list-sheets` skips: path -> reason
    revisions: dict[SheetKey, list[_Revision]] = field(default_factory=dict)
    project_id: str = ""


def sheet_printed_counts(work_dir: Path | str, notes: list[str] | None = None) -> dict[SheetKey, int]:
    """Every sheet `harness list-sheets` prints, with its printed entries (`sheet-text` `counts.matched`
    with no filter and no limit). One load of each file. A file that cannot be listed adds a line to `notes`.
    Raises ReaderError: the errors of list-sheets, a DWG/DXF without its sheets document as usage (2), and an
    input file the operating system refuses as environment (3)."""
    return _scan_inputs(work_dir, notes).counts


def _scan_inputs(work_dir: Path | str, notes: list[str] | None = None) -> _Scan:
    """`sheet_printed_counts` and the entries and clusters of the same load (the errors are its errors)."""
    with _os_errors_are_environment():
        inv = load_inventory(work_dir)
    scan = _Scan(project_id=inv.doc["project_id"])
    for row in sorted(inv.doc["files"], key=lambda r: r["path"]):
        if row["format"] not in ("dwg", "dxf"):
            continue
        with _os_errors_are_environment():
            loaded = load_file(inv, row)
        if notes is not None:
            notes.extend(f"{loaded.rel}: {w}" for w in loaded.warnings)
        if loaded.skip is not None or loaded.text_index is None:
            scan.skipped[loaded.rel] = loaded.skip or "no text index"
            if notes is not None:
                notes.append(f"{loaded.rel}: skipped: {loaded.skip}")
            continue
        if loaded.sheets is None:  # load_file put the reason (no sheets document) in its warnings
            raise ReaderError(EXIT_USAGE, f"{loaded.rel}: " + "; ".join(loaded.warnings))
        by_id = index_by_id(loaded.text_index)
        for sheet in loaded.sheets["sheets"]:
            key = (loaded.rel, sheet["sheet_id"])
            held = [tid for tid in sheet["text_ids"] if tid in by_id]
            scan.counts[key] = sum(is_printed(by_id[tid]) for tid in held)
            scan.entries[key] = set(held)
            scan.revisions[key] = _revisions(sheet, by_id)
        for cluster in file_clusters(loaded)[0]:
            scan.clusters[(cluster["file"], cluster["sheet_id"], cluster["side"])] = set(cluster["entry_ids"])
    return scan


def _revisions(sheet: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> list[_Revision]:
    """Every `revision` candidate of the sheet's title block, chosen or not, with its place in the frame."""
    found = []
    for cand in (sheet.get("title_block") or {}).get("candidates") or []:
        if cand["field"] != "revision":
            continue
        eid = cand["evidence"].get("value_text_id")
        found.append(_Revision(eid, cand["value"], _frame_position(sheet["bbox"], by_id.get(eid))))
    return found


def _frame_position(bbox: list[float], entry: dict[str, Any] | None) -> tuple[float, float] | None:
    """(u, v) of the centre of a text in the sheet frame, read along the text (sheets.py); None when the text
    has no position or the frame has no area."""
    if entry is None or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        return None
    box = text_box(entry)
    if box is None:
        return None
    frame = (bbox[0], bbox[1], bbox[2], bbox[3])
    return _reading_position(frame, box_center(box), _right_angle(entry) or 0)


@contextmanager
def _os_errors_are_environment() -> Iterator[None]:
    """A ReaderError that the shared loaders raised from an OSError becomes exit 3 (the other readers keep
    their exit 1)."""
    try:
        yield
    except ReaderError as exc:
        if isinstance(exc.__cause__, OSError):
            raise ReaderError(EXIT_ENV, str(exc)) from exc
        raise


@contextmanager
def _record_errors_are_reader_errors() -> Iterator[None]:
    """The loaders of the reader's findings and questions raise their own errors, and fold an OSError into
    exit 1. Here the file stays named in the message, an OSError is exit 3 and the rest is exit 1."""
    try:
        yield
    except (FindingError, QuestionsError) as exc:
        code = EXIT_ENV if isinstance(exc.__cause__, OSError) else exc.exit_code
        raise ReaderError(code, str(exc)) from exc


def _read_manifest(work: Path) -> tuple[dict[str, Any] | None, list[Problem]]:
    """(the manifest, []) when it parses and matches the schema, else (None, the `schema` problems).
    Raises ManifestAccessError when the operating system refuses to check or read the path (exit 3)."""
    if not manifest_present(work):
        return None, [_schema(f"{MANIFEST_REL} is missing: the scout writes it before part mode starts")]
    path = work / MANIFEST_REL
    try:
        try:
            regular = stat.S_ISREG(path.stat().st_mode)
        except FileNotFoundError:  # a dangling symlink: something is there, and it is not a file
            regular = False
        if not regular:  # decided before any open: a named pipe would block it
            return None, [_schema(f"{MANIFEST_REL} is not a regular file")]
        data = path.read_bytes()
    except OSError as exc:
        raise ManifestAccessError(f"cannot read {MANIFEST_REL} ({exc})") from exc
    try:
        doc = loads_strict(data)
    except StrictJsonError as exc:
        return None, [_schema(f"{MANIFEST_REL} is not valid JSON: {exc}")]
    found = validate("parts-manifest", doc)
    if found:
        return None, [_schema(f"{p.path or '/'}: {p.message}") for p in found]
    return doc, []


def _schema(detail: str) -> Problem:
    return ("schema", None, None, None, detail)


def _pairs(part: dict[str, Any]) -> list[SheetKey]:
    """The distinct sheets of a part, in listed order."""
    return list(dict.fromkeys((s["file"], s["sheet"]) for s in part.get("sheets", [])))


def _cluster_key(cluster: dict[str, Any]) -> ClusterKey:
    return (cluster["file"], cluster["sheet"], cluster["side"])


def _cycle_members(inputs: dict[str, set[str]]) -> dict[str, set[str]]:
    """For each part on a cycle of `inputs`, the parts on that cycle with it (itself included)."""
    reach: dict[str, set[str]] = {}
    for start in inputs:
        seen: set[str] = set()
        stack = list(inputs[start])
        while stack:
            node = stack.pop()
            if node not in seen:
                seen.add(node)
                stack.extend(inputs.get(node, ()))
        reach[start] = seen
    return {
        pid: {other for other in reach[pid] if pid in reach[other]} for pid in inputs if pid in reach[pid]
    }


def _is_split_id(pid: str, stem: str) -> bool:
    """`pid` is `<stem>-` and some text (an empty suffix is no text)."""
    return pid.startswith(f"{stem}-") and pid != f"{stem}-"


def _stands_for(part: dict[str, Any], fixed: str) -> bool:
    """The part is the cross part `fixed` or a split of it: id `<fixed>-<text>`, `split_of` naming `fixed`."""
    return part["kind"] == "cross" and (
        part["id"] == fixed or (part.get("split_of") == fixed and _is_split_id(part["id"], fixed))
    )


def _kind_mismatch(part: dict[str, Any]) -> str | None:
    """Why the kind and the id of a part disagree (None when they agree). Fixed ids: `FIXED_KINDS`. A cross
    part with another id is `<fixed id>-<text>` with `split_of` naming that fixed id. A member id is
    `<block>-<family>` or `<block>-<family>-<text>` (not checked while block or family is missing:
    `block_unknown` says so). The text after a dash is any text but not none."""
    pid, kind = part["id"], part["kind"]
    if pid in FIXED_KINDS:
        if kind != FIXED_KINDS[pid]:
            return f"the fixed id '{pid}' is for kind {FIXED_KINDS[pid]}, not {kind}"
        return None
    if kind == "cross":
        split_of = part.get("split_of")
        if split_of not in CROSS_PARTS:
            return f"a cross part with another id than {', '.join(CROSS_PARTS)} needs split_of naming one"
        if not _is_split_id(pid, split_of):
            return f"a split of '{split_of}' has the id '{split_of}-<letter>'"
        return None
    if kind != "member":
        return f"kind {kind} has the fixed id {', '.join(c for c, k in FIXED_KINDS.items() if k == kind)}"
    block, family = part.get("block"), part.get("family")
    if block is None or family is None:
        return None
    stem = f"{block}-{family}"
    if pid != stem and not _is_split_id(pid, stem):
        return f"a member id is '{stem}' or '{stem}-<letter>' (block-family)"
    return None


def _structure_problems(
    manifest: dict[str, Any], counts: dict[SheetKey, int], clusters: set[ClusterKey]
) -> tuple[list[Problem], int]:
    """(the problems, how many sheets are covered)."""
    parts: list[dict[str, Any]] = manifest["parts"]
    block_ids = {b["id"] for b in manifest["blocks"]}
    problems: list[Problem] = []

    ids: dict[str, int] = {}
    for p in parts:
        ids[p["id"]] = ids.get(p["id"], 0) + 1
    for pid, n in ids.items():
        if n > 1:
            problems.append(("duplicate_part_id", pid, None, None, f"the part id is listed {n} times"))

    for cross in CROSS_PARTS:
        if not any(_stands_for(p, cross) for p in parts):
            problems.append(("cross_part_missing", cross, None, None, f"no part '{cross}' of kind cross"))
    for bookkeeping in BOOKKEEPING_PARTS:
        if not any(p["kind"] == "bookkeeping" and p["id"] == bookkeeping for p in parts):
            problems.append(
                (
                    "bookkeeping_part_missing",
                    bookkeeping,
                    None,
                    None,
                    f"no part '{bookkeeping}' of kind bookkeeping",
                )
            )

    for p in parts:
        reason = _kind_mismatch(p)
        if reason is not None:
            problems.append(("part_kind_mismatch", p["id"], None, None, reason))

    inputs: dict[str, set[str]] = {}
    for p in parts:
        known = inputs.setdefault(p["id"], set())
        for ref in p.get("inputs", []):
            if ref in ids:
                known.add(ref)
            else:
                problems.append(("input_unknown", p["id"], None, None, f"input '{ref}' is not a part id"))
    for pid, members in _cycle_members(inputs).items():
        detail = (
            "the part is its own input"
            if members == {pid}
            else f"inputs form a cycle: {', '.join(sorted(members))}"
        )
        problems.append(("input_cycle", pid, None, None, detail))

    for p in parts:
        if p["kind"] != "member":
            continue
        reasons = []
        if p.get("block") is None:
            reasons.append("a member part needs a block")
        elif p["block"] not in block_ids:
            reasons.append(f"block '{p['block']}' is not in blocks[]")
        if p.get("family") is None:
            reasons.append("a member part needs a family")
        if reasons:
            problems.append(("block_unknown", p["id"], None, None, "; ".join(reasons)))

    sheet_parts = [p for p in parts if p["kind"] not in EXEMPT_KINDS]
    covered: set[SheetKey] = set()
    for p in parts:
        for key in _pairs(p):
            if key not in counts:
                problems.append(
                    ("sheet_unknown", p["id"], key[0], key[1], "no such sheet in `harness list-sheets`")
                )
            elif p["kind"] not in EXEMPT_KINDS:
                covered.add(key)
    for file, sheet in sorted(set(counts) - covered):
        problems.append(("sheet_uncovered", None, file, sheet, "no part lists this sheet"))

    blocks_of: dict[SheetKey, set[str]] = {}
    for p in sheet_parts:
        if p["kind"] == "member" and p.get("block") in block_ids:
            for key in _pairs(p):
                blocks_of.setdefault(key, set()).add(p["block"])
    for (file, sheet), blocks in sorted(blocks_of.items()):
        if len(blocks) > 1:
            problems.append(
                (
                    "sheet_in_two_blocks",
                    None,
                    file,
                    sheet,
                    f"listed by member parts of blocks {', '.join(sorted(blocks))}",
                )
            )

    parts_of: dict[ClusterKey, set[str]] = {}
    for p in parts:
        for c in p.get("clusters", []):
            parts_of.setdefault(_cluster_key(c), set()).add(p["id"])
    for file, sheet, side in sorted(clusters, key=lambda k: (k[0], k[1] or "", k[2])):
        owners = parts_of.get((file, sheet, side), set())
        where = f"cluster side '{side}' of {sheet or 'no sheet'}"
        if not owners:
            problems.append(("cluster_uncovered", None, file, sheet, f"{where} is in no part"))
        elif len(owners) > 1:
            problems.append(
                (
                    "cluster_in_two_parts",
                    None,
                    file,
                    sheet,
                    f"{where} is in parts {', '.join(sorted(owners))}",
                )
            )

    for p in sheet_parts:
        keys = _pairs(p)
        entries = sum(counts.get(k, 0) for k in keys)
        if len(keys) > MAX_SHEETS or entries > MAX_PRINTED_ENTRIES:
            problems.append(
                (
                    "part_over_cap",
                    p["id"],
                    None,
                    None,
                    f"{len(keys)} sheets (cap {MAX_SHEETS}), "
                    f"{entries} printed entries (cap {MAX_PRINTED_ENTRIES}): split the part",
                )
            )
    return problems, len(covered)


def _where(sheet: str | None, side: str) -> str:
    return f"cluster side '{side}' of {sheet or 'no sheet'}"


def _entry_problems(
    part_id: str, file: str, sheet: str | None, fields: list[tuple[str, str]], held: set[str], where: str
) -> list[Problem]:
    return [
        ("entry_unknown", part_id, file, sheet, f"{name} '{entry}' is not an entry of {where}")
        for name, entry in fields
        if entry not in held
    ]


def _reference_problems(manifest: dict[str, Any], scan: _Scan) -> list[Problem]:
    """The references of the manifest that point at nothing, or outside their part: tables on unknown sheets,
    unknown clusters, tables outside the part's own sheets and clusters, unknown entry ids, duplicate block
    ids."""
    problems: list[Problem] = []
    block_counts: dict[str, int] = {}
    for b in manifest["blocks"]:
        block_counts[b["id"]] = block_counts.get(b["id"], 0) + 1
    for bid, n in block_counts.items():
        if n > 1:
            detail = f"the block id '{bid}' is listed {n} times"
            problems.append(("duplicate_block_id", None, None, None, detail))

    for p in manifest["parts"]:
        pid = p["id"]
        listed_sheets = set(_pairs(p))
        listed_clusters = {_cluster_key(c) for c in p.get("clusters", [])}
        for ref in p.get("sheets", []):
            key = (ref["file"], ref["sheet"])
            if key not in scan.entries:
                continue  # sheet_unknown is raised for it
            fields = [(n, ref[n]) for n in ("number_entry", "title_entry") if n in ref]
            views = ref.get("views", [])
            fields += [("heading_entry", v["heading_entry"]) for v in views if "heading_entry" in v]
            where = f"sheet {key[1]}"
            problems += _entry_problems(pid, key[0], key[1], fields, scan.entries[key], where)
        for c in p.get("clusters", []):
            if _cluster_key(c) not in scan.clusters:
                problems.append(_cluster_unknown(pid, c))
        for t in p.get("tables", []):
            headers = [("header_entries", e) for e in t["header_entries"]]
            if "cluster" in t:
                c = t["cluster"]
                ckey = _cluster_key(c)
                if ckey not in scan.clusters:
                    problems.append(_cluster_unknown(pid, c))
                    continue
                where = _where(c["sheet"], c["side"])
                if ckey not in listed_clusters:
                    detail = f"table in {where} is not in the part's clusters[]"
                    problems.append(("table_outside_part", pid, c["file"], c["sheet"], detail))
                problems += _entry_problems(pid, c["file"], c["sheet"], headers, scan.clusters[ckey], where)
            else:
                key = (t["file"], t["sheet"])
                if key not in scan.entries:
                    detail = "table on a sheet that `harness list-sheets` does not print"
                    problems.append(("sheet_unknown", pid, key[0], key[1], detail))
                    continue
                if key not in listed_sheets:
                    detail = f"table on sheet {key[1]} is not in the part's sheets[]"
                    problems.append(("table_outside_part", pid, key[0], key[1], detail))
                where = f"sheet {key[1]}"
                problems += _entry_problems(pid, key[0], key[1], headers, scan.entries[key], where)
    return problems


def _cluster_unknown(part_id: str, cluster: dict[str, Any]) -> Problem:
    detail = f"{_where(cluster['sheet'], cluster['side'])} is not reported by `harness unassigned-clusters`"
    return ("cluster_unknown", part_id, cluster["file"], cluster["sheet"], detail)


def _unread_problems(manifest: dict[str, Any], skipped: dict[str, str]) -> list[Problem]:
    """A DWG/DXF that `harness list-sheets` skips is read by nobody unless a `no_sheet` part names it in
    `files[]`: one `file_unread` for each."""
    named = {f for p in manifest["parts"] if p["kind"] == "no_sheet" for f in p.get("files", [])}
    return [
        (
            "file_unread",
            None,
            file,
            None,
            f"`harness list-sheets` skips the file ({reason}); no sheet part reads it: "
            "name it in files[] of a no_sheet part, or fix the file and rerun intake",
        )
        for file, reason in sorted(skipped.items())
        if file not in named
    ]


def _files_problems(manifest: dict[str, Any], skipped: dict[str, str]) -> list[Problem]:
    """A `files[]` item is read only on a `no_sheet` part, and only when `harness list-sheets` skips the file
    (it is in `skipped`: no text index, or an unreadable one). Any other item is `files_entry_unused`: one row
    for each part and file, with both reasons when both apply."""
    problems: list[Problem] = []
    for p in manifest["parts"]:
        for file in sorted(set(p.get("files", []))):
            reasons = []
            if p["kind"] != "no_sheet":
                reasons.append(
                    f"files[] is read on a no_sheet part only, and '{p['id']}' is kind {p['kind']}"
                )
            if file not in skipped:
                reasons.append(
                    "`harness list-sheets` does not skip this file (it is read as sheets, or is not an "
                    "input DWG/DXF)"
                )
            if reasons:
                problems.append(("files_entry_unused", p["id"], file, None, "; ".join(reasons)))
    return problems


def _record_problems(work: Path, manifest: dict[str, Any], project_id: str) -> list[Problem]:
    """A part that a reader finding (`part`) or reader question (`parts[]`) names and the manifest does not
    list is read by no part check: one `record_part_unknown` for each, naming the records. A withdrawn finding
    does not count (withdrawn questions are no longer in reader-questions.json); the problem's detail names
    the commands that clear it. An absent file means no records. Raises ReaderError: a file that is not
    readable JSON of its schema is exit 1, one the operating system refuses is exit 3."""
    listed = {p["id"] for p in manifest["parts"]}
    tagged: dict[str, set[str]] = {}
    with _record_errors_are_reader_errors():
        findings = _load_doc(work, None)
        questions = _load_reader_doc(work, project_id)
    for f in [] if findings is None else findings["findings"]:
        if f["status"] != "withdrawn" and f.get("part") is not None and f["part"] not in listed:
            tagged.setdefault(f["part"], set()).add(f["id"])
    for q in questions["questions"]:
        for part_id in q.get("parts", []):
            if part_id not in listed:
                tagged.setdefault(part_id, set()).add(q["id"])
    problems: list[Problem] = []
    for part_id, ids in sorted(tagged.items()):
        shown = sorted(ids)
        names = ", ".join(shown[:MAX_RECORD_IDS]) + (", …" if len(shown) > MAX_RECORD_IDS else "")
        detail = (
            f"tagged on {names} but not in {MANIFEST_REL}: withdraw each with "
            f"`harness finding withdraw … --part {part_id}` or `harness ask --withdraw … --part {part_id}`, "
            "or list the part in the manifest"
        )
        problems.append(("record_part_unknown", part_id, None, None, detail))
    return problems


def _read_document(path: Path, schema: str) -> dict[str, Any] | None:
    """A work-folder document checked against its schema; None when it does not exist. Raises ReaderError: a
    file that is not readable JSON of its schema is exit 1, one the operating system refuses is exit 3."""
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ReaderError(EXIT_ENV, f"{path.name} cannot be read: {exc}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReaderError(EXIT_INVALID, f"{path.name} is not valid JSON: {exc}") from exc
    found = validate(schema, doc)
    if found:
        shown = "; ".join(f"{p.path or '/'}: {p.message}" for p in found[:3])
        raise ReaderError(EXIT_INVALID, f"{path.name} is invalid against the {schema} schema: {shown}")
    return doc


def _order_problems(manifest: dict[str, Any]) -> list[Problem]:
    """A part is read after its inputs: its `order` must be above the order of each input (an input id that
    no part has is `input_unknown`; with two parts of one id the higher order counts)."""
    order: dict[str, int] = {}
    for p in manifest["parts"]:
        order[p["id"]] = max(order.get(p["id"], p["order"]), p["order"])
    return [
        (
            "order_not_after_input",
            p["id"],
            None,
            None,
            f"order {p['order']} is not above order {order[ref]} of its input '{ref}'",
        )
        for p in manifest["parts"]
        for ref in p.get("inputs", [])
        if ref in order and p["order"] <= order[ref]
    ]


def _grid_system_problems(work: Path, manifest: dict[str, Any]) -> list[Problem]:
    """Each `grid_system_ids` entry of a block must be a `system_id` of `grid-systems.json`. The file is read
    only when a block lists an id; absent, every listed id is unknown; invalid, the check stops (exit 1)."""
    listed = [(b["id"], sid) for b in manifest["blocks"] for sid in b["grid_system_ids"]]
    if not listed:
        return []
    doc = _read_document(work / GRID_SYSTEMS_FILE, "grid-system")
    held = None if doc is None else {s["system_id"] for s in doc["systems"]}
    why = (
        f"but {GRID_SYSTEMS_FILE} is missing (run `harness grid-system`)"
        if held is None
        else f"which {GRID_SYSTEMS_FILE} does not hold"
    )
    return [
        ("grid_system_unknown", None, None, None, f"block '{block}' lists grid system '{sid}', {why}")
        for block, sid in listed
        if held is None or sid not in held
    ]


def _revision_warnings(
    manifest: dict[str, Any], scan: _Scan
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(warnings, skipped): a `revision` candidate of a sheet of any part whose text sits outside the
    title-block zone of the frame, `u >= 1 - CORNER_U or v <= CORNER_V` (the right band and the bottom band;
    sheets.py), is a revision read from some other table. A candidate with no position is skipped."""
    warnings: dict[str, dict[str, Any]] = {}
    skipped: list[dict[str, Any]] = []
    for file, sheet in sorted({k for p in manifest["parts"] for k in _pairs(p)}):
        for rev in scan.revisions.get((file, sheet), []):
            if rev.uv is None or rev.entry is None:
                skipped.append({"code": REVISION, "file": file, "sheet": sheet, "reason": NO_POSITION})
                continue
            u, v = rev.uv
            if u >= 1 - CORNER_U or v <= CORNER_V:
                continue
            wid = f"{REVISION}|{file}|{sheet}|{rev.entry}"
            warnings[wid] = {
                "id": wid,
                "code": REVISION,
                "part": None,
                "file": file,
                "sheet": sheet,
                "detail": (
                    f"revision '{rev.value}' ({rev.entry}) sits at u {u:.3f}, v {v:.3f} of the sheet, "
                    f"outside the title-block zone (u >= {1 - CORNER_U:g} or v <= {CORNER_V:g}): "
                    "a revision read from another table?"
                ),
            }
    return list(warnings.values()), skipped


def _known_sheets_only(manifest: dict[str, Any], counts: dict[SheetKey, int]) -> dict[str, Any]:
    """The manifest as the two drawing rules read it: a sheet that `list-sheets` does not print is left out
    (`sheet_unknown` says so; the rules read the inventory and would stop on a file it does not list)."""
    parts = [
        {**p, "sheets": [s for s in p["sheets"] if (s["file"], s["sheet"]) in counts]} if "sheets" in p else p
        for p in manifest["parts"]
    ]
    return {**manifest, "parts": parts}


def _unit_answer_problems(manifest: dict[str, Any], notes: list[str]) -> list[Problem]:
    """One problem per note the rules collected, filed under the manifest's file that the note starts with:
    `unit_unanswered` for a file with no active units answer, else `unit_answer_unread` (the note is the
    detail: `<file>: <warning text>`)."""
    files = sorted({s["file"] for p in manifest["parts"] for s in p.get("sheets", [])}, key=len, reverse=True)
    problems: list[Problem] = []
    for note in notes:
        file = next((f for f in files if note.startswith(f"{f}: ")), None)
        if file is not None and note == part_warnings.unanswered_note(file):
            problems.append(("unit_unanswered", None, file, None, part_warnings.unanswered_text(file)))
        else:
            problems.append(("unit_answer_unread", None, file, None, note))
    return problems


def _drawing_warnings(
    work: Path, manifest: dict[str, Any], scan: _Scan, input_dir: Path | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[Problem]]:
    """(warnings sorted by id, skipped sorted, problems), the three rules together. A file with no active
    units answer is skipped by the two measuring rules and is a `unit_unanswered` problem (DECISIONS 12, D1);
    one whose answer cannot be read is a `unit_answer_unread` problem (DECISIONS 7, item 6). Raises
    ReaderError (the rules' own codes pass through; an OSError behind one is exit 3)."""
    known = _known_sheets_only(manifest, scan.counts)
    unit_notes: list[str] = []
    with _os_errors_are_environment():
        grid_w, grid_s = part_warnings.grid_origin_warnings(work, known, unit_notes)
        line_w, line_s = part_warnings.linework_warnings(work, known, input_dir, unit_notes)
    rev_w, rev_s = _revision_warnings(manifest, scan)
    warnings = sorted([*grid_w, *line_w, *rev_w], key=lambda w: w["id"])
    seen = {(s["file"], s["sheet"], s["code"], s["reason"]): s for s in [*grid_s, *line_s, *rev_s]}
    return warnings, [seen[k] for k in sorted(seen)], _unit_answer_problems(known, unit_notes)


def _registry_missing(work: Path) -> ReaderError:
    return ReaderError(
        EXIT_USAGE, f"{REGISTRY_FILE} is missing: run `harness intake <input_dir> --out {work}` first"
    )


def _require_registry(work: Path) -> None:
    """A work folder always holds `question-registry.json` (`harness intake` writes it): without it the
    folder is broken, and neither the unit answers nor the acks can be checked. Raises ReaderError (usage)."""
    if not (work / REGISTRY_FILE).is_file():
        raise _registry_missing(work)


def _registry_ids(work: Path) -> set[str]:
    """The question ids of `question-registry.json`, whatever their status. Raises ReaderError: usage when
    the file is absent, invalid or environment as `_read_document`."""
    doc = _read_document(work / REGISTRY_FILE, "question-registry")
    if doc is None:
        raise _registry_missing(work)
    return {e["id"] for e in doc["questions"].values()}


def _apply_acks(
    work: Path, manifest: dict[str, Any], warnings: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[Problem]]:
    """Mark each warning whose id equals an ack's `warning` exactly as acked (`ack`: its question and reason).
    The problems: an ack naming no current warning, two acks of one id, a question that is no registry id."""
    acks: list[dict[str, Any]] = manifest.get("acks", [])
    problems: list[Problem] = []
    by_id: dict[str, list[dict[str, Any]]] = {}
    for ack in acks:
        by_id.setdefault(ack["warning"], []).append(ack)
    known = {w["id"] for w in warnings}
    for wid, group in by_id.items():
        if wid not in known:
            problems.append(("ack_unmatched", None, None, None, f"ack '{wid}' matches no warning"))
        if len(group) > 1:
            detail = f"{len(group)} acks name '{wid}': one ack per warning"
            problems.append(("ack_duplicate", None, None, None, detail))
    questions = {a["question"] for a in acks if "question" in a}
    registry = _registry_ids(work) if questions else set()
    for ack in acks:
        if "question" in ack and ack["question"] not in registry:
            detail = (
                f"ack '{ack['warning']}' names question {ack['question']}, "
                f"which {REGISTRY_FILE} does not hold"
            )
            problems.append(("ack_question_unknown", None, None, None, detail))
    out = []
    for w in warnings:
        first = by_id.get(w["id"], [None])[0]
        ack = None if first is None else {k: first[k] for k in ("question", "reason") if k in first}
        out.append({**w, "acked": first is not None, "ack": ack})
    return out, problems


def _sort_key(problem: Problem) -> tuple[str, ...]:
    return tuple("" if v is None else v for v in problem)


def manifest_check(
    work_dir: Path | str, notes: list[str] | None = None, input_dir: Path | str | None = None
) -> dict[str, Any]:
    """The check document of the work folder's parts manifest. Raises ReaderError (usage: no work folder, no
    inventory.json, no question registry or no sheets document; invalid: grid-systems.json, the question
    registry, the findings and question files, or what `read_geometry` raises; environment: an input file
    the operating system refuses) and ManifestAccessError (the manifest path). `notes`: diagnostics for stderr
    (a file that could not be listed). `input_dir`: where a native DXF lives (the linework rule reads it)."""
    work = Path(work_dir)
    scan = _scan_inputs(work, notes)
    _require_registry(work)
    counts = scan.counts
    manifest, problems = _read_manifest(work.resolve())
    covered = 0
    warnings: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    if manifest is not None:
        problems, covered = _structure_problems(manifest, counts, set(scan.clusters))
        problems += _reference_problems(manifest, scan)
        problems += _unread_problems(manifest, scan.skipped)
        problems += _files_problems(manifest, scan.skipped)
        problems += _record_problems(work.resolve(), manifest, scan.project_id)
        problems += _order_problems(manifest)
        problems += _grid_system_problems(work.resolve(), manifest)
        found, skipped, unit_problems = _drawing_warnings(
            work, manifest, scan, None if input_dir is None else Path(input_dir)
        )
        problems += unit_problems
        warnings, ack_problems = _apply_acks(work.resolve(), manifest, found)
        problems += ack_problems
    unique: Iterable[Problem] = sorted(set(problems), key=_sort_key)
    doc: dict[str, Any] = {
        "command": "manifest-check",
        "ok": not problems and all(w["acked"] for w in warnings),
        "sheets": {"total": len(counts), "covered": covered},
        "parts": 0 if manifest is None else len(manifest["parts"]),
        "problems": [{"code": c, "part": p, "file": f, "sheet": s, "detail": d} for c, p, f, s, d in unique],
        "warnings": warnings,
        "skipped": skipped,
    }
    invalid = validate("part-output", doc)
    if invalid:
        shown = "; ".join(f"{p.path}: {p.message}" for p in invalid[:3])
        raise ReaderError(EXIT_INVALID, f"internal error: output is invalid: {shown}")
    return doc


# --- command ----------------------------------------------------------------------------------------


def add_arguments(parser: argparse.ArgumentParser) -> None:
    from tekla_harness.part_receipts import KINDS, VERDICTS  # part_receipts imports this module

    sub = parser.add_subparsers(
        dest="action",
        required=True,
        metavar="{manifest-check,check,receipt,chain,review-sample,conflicts,spotcheck,answer-key,score}",
    )
    p_check = sub.add_parser(
        "manifest-check",
        help="check the parts manifest (W/parts/manifest.json) against the sheets and clusters of the work "
        "folder, and warn about misfiled or copied plans and a revision read from the wrong table; "
        "read-only; exit 0 ok, 1 problems or an unacknowledged warning, 2 usage, 3 a file the system "
        "refuses to read",
    )
    p_check.add_argument("work_dir", help="the --out folder of `harness intake`")
    p_check.add_argument(
        "--input-dir", help="the intake input folder (needed when a drawing is a native DXF file)"
    )
    p_check.set_defaults(handler=_run_manifest_check)
    p_part = sub.add_parser(
        "check",
        help="check W/parts/<part>/values.json: every row's state, sheet, citations and numbers; read-only; "
        "exit 0 ok, 1 problems, 2 usage, 3 a file the system refuses to read",
    )
    p_part.add_argument("work_dir", help="the --out folder of `harness intake`")
    p_part.add_argument("--part", required=True, help="the part id (parts[].id of the manifest)")
    p_part.set_defaults(handler=_run_check)
    p_receipt = sub.add_parser(
        "receipt",
        help="record one stage of a part in W/parts/<part>/receipts.json (append-only, bound to the part "
        "hash): checked, reviewed, locked or reopened; takes the work-folder lock; exit 0 written or already "
        "recorded, 1 a precondition failed (nothing written), 2 usage, 3 a file the system refuses",
    )
    p_receipt.add_argument("work_dir", help="the --out folder of `harness intake`")
    p_receipt.add_argument("--part", required=True, help="the part id (parts[].id of the manifest)")
    p_receipt.add_argument("--kind", required=True, choices=KINDS, help="the stage to record")
    p_receipt.add_argument(
        "--review", help="reviewed: the file W/parts/<part>/review/round-<N>/review.md (its sha256 is stored)"
    )
    p_receipt.add_argument("--round", type=int, help="reviewed: the review round N (1 or more)")
    p_receipt.add_argument("--verdict", choices=VERDICTS, help="reviewed: the verdict of the round")
    p_receipt.add_argument("--reason", help="reopened: why the locked part is open again (not empty)")
    p_receipt.set_defaults(handler=_run_receipt)
    _add_later_actions(sub)


def _seed(text: str) -> int:
    if not re.fullmatch(r"[0-9]+", text):
        raise argparse.ArgumentTypeError(f"{text!r} is not a whole number of 0 or more")
    return int(text)


def _count(text: str) -> int:
    if not re.fullmatch(r"[0-9]+", text) or int(text) < 1:
        raise argparse.ArgumentTypeError(f"{text!r} is not a whole number of 1 or more")
    return int(text)


def _row_id(text: str) -> str:
    if not re.fullmatch(r"R[0-9]{3,}", text):
        raise argparse.ArgumentTypeError(f"{text!r} is not a row id (R followed by 3 or more digits)")
    return text


def _name(text: str) -> str:
    if not text.strip():
        raise argparse.ArgumentTypeError("must not be blank")
    return text


def _add_later_actions(sub: Any) -> None:
    """The six actions whose bodies come later (E6b, E7, E9a, E9b): final flags, stub handlers (E6w)."""

    def action(name: str, help_text: str, handler: Any) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("work_dir", help="the --out folder of `harness intake`")
        p.set_defaults(handler=handler)
        return p

    def part_sample(p: argparse.ArgumentParser) -> None:
        p.add_argument("--part", required=True, help="the part id (parts[].id of the manifest)")
        p.add_argument("--seed", type=_seed, required=True, help="the sampling seed (an integer, 0 or more)")
        p.add_argument("--n", type=_count, help="the sample size (an integer, 1 or more)")

    p = action(
        "chain",
        "the member parts of one block in order, with each part's count rows, hand-sum addends, cap "
        "products and sums; read-only (E7)",
        _run_chain,
    )
    p.add_argument("--block", required=True, help="the block id (parts[].block of the manifest)")
    part_sample(
        action(
            "review-sample",
            "a seeded sample of a part's rows as blind prompts for a reviewer; read-only (E7)",
            _run_review_sample,
        )
    )
    action(
        "conflicts",
        "raise a question for each value that two parts state differently; takes the work-folder lock (E6b)",
        _run_conflicts,
    )
    part_sample(
        action(
            "spotcheck",
            "write a seeded spot-check sample and checklist of a locked part; takes the work-folder lock "
            "(E9a)",
            _run_spotcheck,
        )
    )
    p = action(
        "answer-key",
        "record the engineer's verdict on one sampled row in W/answer-key.json; takes the work-folder lock "
        "(E9b)",
        _run_answer_key,
    )
    p.add_argument("--part", required=True, help="the part id (parts[].id of the manifest)")
    p.add_argument("--row", type=_row_id, required=True, help="the row id, e.g. R012")
    p.add_argument("--verdict", required=True, choices=ANSWER_VERDICTS, help="the engineer's verdict")
    p.add_argument("--by", type=_name, required=True, help="who checked the row (not blank)")
    p.add_argument("--correct", help="wrong: the value the drawing gives")
    p.add_argument("--text", help="the engineer's words, kept as they are")
    p = action(
        "score",
        "score a re-read against the answer key (agree, differ, missing, cannot_tell); read-only (E9b)",
        _run_score,
    )
    p.add_argument("--answer-key", help="the key file (default W/answer-key.json)")


def _run_manifest_check(args: argparse.Namespace) -> int:
    notes: list[str] = []
    try:
        doc = manifest_check(args.work_dir, notes, Path(args.input_dir) if args.input_dir else None)
    except ReaderError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except ManifestAccessError as exc:
        print(f"harness {COMMAND} {args.action}: {exc}", file=sys.stderr)
        return EXIT_ENV
    except OSError as exc:
        print(f"harness {COMMAND} {args.action}: cannot read the work folder: {exc}", file=sys.stderr)
        return EXIT_ENV
    for note in notes:
        print(note, file=sys.stderr)
    print(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False))
    if not doc["ok"]:
        unacked = sum(not w["acked"] for w in doc["warnings"])
        print(
            f"harness {COMMAND} {args.action}: {len(doc['problems'])} problem(s), "
            f"{unacked} unacknowledged warning(s)",
            file=sys.stderr,
        )
        return EXIT_INVALID
    return EXIT_OK


def _run_check(args: argparse.Namespace) -> int:
    from tekla_harness.part_check import check_part  # part_check imports this module

    try:
        doc = check_part(args.work_dir, args.part)
    except ReaderError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except ManifestAccessError as exc:
        print(f"harness {COMMAND} {args.action}: {exc}", file=sys.stderr)
        return EXIT_ENV
    except OSError as exc:
        print(f"harness {COMMAND} {args.action}: cannot read the work folder: {exc}", file=sys.stderr)
        return EXIT_ENV
    print(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False))
    if not doc["ok"]:
        print(f"harness {COMMAND} {args.action}: {len(doc['problems'])} problem(s)", file=sys.stderr)
        return EXIT_INVALID
    return EXIT_OK


def _run_receipt(args: argparse.Namespace) -> int:
    from tekla_harness.part_receipts import write_part_receipt  # part_receipts imports this module
    from tekla_harness.receipt import ReceiptError

    try:
        doc = write_part_receipt(
            args.work_dir, args.part, args.kind,
            review=args.review, review_round=args.round, verdict=args.verdict, reason=args.reason,
        )  # fmt: skip
    except ReaderError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except ManifestAccessError as exc:
        print(f"harness {COMMAND} {args.action}: {exc}", file=sys.stderr)
        return EXIT_ENV
    except ReceiptError as exc:  # a bug: the receipt built does not satisfy its own schema
        print(
            f"harness {COMMAND} {args.action}: internal error: the receipt built is invalid: {exc}",
            file=sys.stderr,
        )
        return EXIT_INVALID
    except OSError as exc:
        print(
            f"harness {COMMAND} {args.action}: cannot read or write the work folder: {exc}", file=sys.stderr
        )
        return EXIT_ENV
    print(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False))
    if doc["refused"] is not None:
        print(f"harness {COMMAND} {args.action}: refused: {doc['refused']}", file=sys.stderr)
        return EXIT_INVALID
    if not doc["written"]:
        print(
            f"harness {COMMAND} {args.action}: already recorded (receipt {doc['receipt']['n']})",
            file=sys.stderr,
        )
    return EXIT_OK


def _run_chain(args: argparse.Namespace) -> int:
    from tekla_harness.part_sample import run_chain

    return run_chain(args)


def _run_review_sample(args: argparse.Namespace) -> int:
    from tekla_harness.part_sample import run_review_sample

    return run_review_sample(args)


def _run_conflicts(args: argparse.Namespace) -> int:
    from tekla_harness.part_conflicts import run_conflicts

    return run_conflicts(args)


def _run_spotcheck(args: argparse.Namespace) -> int:
    from tekla_harness.part_spotcheck import run_spotcheck

    return run_spotcheck(args)


def _run_answer_key(args: argparse.Namespace) -> int:
    from tekla_harness.part_score import run_answer_key

    return run_answer_key(args)


def _run_score(args: argparse.Namespace) -> int:
    from tekla_harness.part_score import run_score

    return run_score(args)


def run(args: argparse.Namespace) -> int:
    return int(args.handler(args))
