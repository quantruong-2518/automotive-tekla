"""The text of one take-off file `takeoff/<nn>-<part>.md` (E8b), generated from rows and records.

`TakeoffContext.load(work)` reads everything once: the manifest, the status rows, the findings, the
questions, the grid systems, `marks.json`, and (on demand, once per file) the text index and (once per source)
the saved geometry or contents documents. `render_part(ctx, part, slots)` is then pure text: every value,
confidence, status and reference comes from rows and records through `takeoff_cells`; only the two slots
(`method`, `reason`) are the AI's, kept as they are on disk. A cited record that is not loaded raises
`TakeoffError` (exit 1), never a guess.
"""

from __future__ import annotations

import os.path
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tekla_harness.findings import list_findings
from tekla_harness.part_receipts import load_manifest
from tekla_harness.part_sums import hand_sum_addends
from tekla_harness.part_values import _read_document, _read_saved, read_values
from tekla_harness.questions import GRID_MISSING_CODE, SELECT_CODE, SYSTEM_AXIS_CODE, load_ledger
from tekla_harness.questions_md import Item, _answer_block, _need_impact, load_items
from tekla_harness.saved_evidence import redo_command
from tekla_harness.sheet_text import index_by_id, load_file, load_inventory
from tekla_harness.status import PART_QUESTION_FILES, build_status, built_grid_answers, closure_state
from tekla_harness.takeoff_cells import (
    CONF_VI,
    NO_FINDING_VI,
    NONE_VI,
    QUESTION_STATE_VI,
    axes_cell,
    conf_text,
    field_cell,
    hand_sum_text,
    mark_confidence,
    positions,
    row_cell,
    row_confidence,
    status_line,
)

EXIT_INVALID = 1
ELIGIBLE = ("checked", "reviewed", "locked")
PLACEHOLDER = "_(chưa viết)_"
SLOTS = ("method", "reason")
_SLOT = re.compile(r"<!-- ai:(method|reason) -->\n(.*?)\n<!-- /ai:\1 -->", re.DOTALL)
ROLE_VI = {
    "plan": "mặt bằng", "schedule": "bảng thống kê", "detail": "chi tiết", "section": "mặt cắt",
    "notes": "ghi chú", "list": "danh mục",
}  # fmt: skip
HEADINGS = (
    "1. Mô tả và phương pháp bóc", "2. Kết quả", "3. Ref đối soát", "4. Độ tin cậy", "5. Chưa rõ",
    "6. Trạng thái", "7. Tọa độ cho 3D",
)  # fmt: skip
SIZE_FIELDS = ("size", "thickness", "depth", "length", "spacing")
COUNT_FIELDS = ("count_plan", "count_schedule", "piles_per_member")
LEVEL_FIELDS = ("level", "level_top", "level_bottom")
Z_FIELDS = (*LEVEL_FIELDS, "depth", "length")
DOC_FIELDS = {
    "contents": ("short", "long", "angle", "centre", "symbols", "axes"),
    "geometry": ("centre", "diameter", "short", "long", "angle"),
}
OUT_NAME = "takeoff"
MARKERS = tuple(m for n in SLOTS for m in (f"<!-- ai:{n} -->", f"<!-- /ai:{n} -->"))

Row = dict[str, Any]


class TakeoffError(Exception):
    """A run that cannot proceed; `exit_code` is the CLI exit code."""

    def __init__(self, exit_code: int, message: str) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def parse_slots(text: str) -> dict[str, str]:
    """The AI slots of a take-off file: name -> body, byte for byte between the marker lines."""
    slots: dict[str, str] = {}
    for m in _SLOT.finditer(text):
        slots.setdefault(m[1], m[2])
    return slots


def _problem(code: str, file: str, line: int | None, detail: str) -> dict[str, Any]:
    return {"code": code, "file": file, "line": line, "detail": detail}


def _markers(name: str, lines: list[str], slots: dict[str, str]) -> list[dict[str, Any]]:
    """A slot marker missing, doubled or out of order, or a slot with no body line."""
    found = {m: [i for i, ln in enumerate(lines, 1) if ln == m] for m in MARKERS}
    problems = [
        _problem(
            "slot_markers", name, at[1] if len(at) > 1 else None, f"{m} is {'doubled' if at else 'missing'}"
        )
        for m, at in found.items()
        if len(at) != 1
    ]
    if problems:
        return problems
    firsts = [found[m][0] for m in MARKERS]
    if firsts != sorted(firsts):
        return [_problem("slot_markers", name, min(firsts), "the slot markers are out of order")]
    return [
        _problem("slot_markers", name, found[f"<!-- ai:{n} -->"][0], f"ai:{n} has no body line")
        for n in SLOTS
        if n not in slots
    ]


def shown_path(work: Path, out: Path) -> str:
    """The work folder as the generated text names it: its path from the take-off folder `out`, in POSIX
    form (`../work`); the resolved POSIX path when no relative path exists (another drive on Windows). The
    same text for every spelling of the path, every working folder and every machine with the same layout."""
    try:
        return Path(os.path.relpath(work, out)).as_posix()
    except ValueError:
        return work.as_posix()


@dataclass
class TakeoffContext:
    work: Path
    shown: str  # the work folder from the take-off folder (`shown_path`), for the commands to rerun
    manifest: dict[str, Any]
    status: dict[str, dict[str, Any]]  # `harness status` parts[] by id
    findings: dict[str, dict[str, Any]]
    systems: dict[str, dict[str, Any]]
    items: dict[str, Item]
    missing: list[dict[str, str]]  # live registry questions that no question document carries
    questions: dict[str, dict[str, Any]]  # what E8a reads of a question: its answer, only when it is closed
    tagged: dict[str, set[str]]  # part id -> ids of the question documents' questions that hold it
    marks: dict[str, Any] | None
    rank: dict[str, int]  # non-bookkeeping parts by (order, id), 1-based
    project_id: str
    project_blocking_ids: list[str]  # `harness status`: the open blocking ids that block every part
    _inventory: Any = None
    _texts: dict[str, dict[str, str]] = field(default_factory=dict)
    _values: dict[str, list[Row]] = field(default_factory=dict)
    _saved: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def load(cls, work_dir: Path | str) -> TakeoffContext:
        """Raises TakeoffError, StatusError, ReaderError, QuestionsError, QuestionsMdError, FindingError and
        ManifestAccessError (each with its exit code, 3 for the last) and OSError."""
        work = Path(work_dir).resolve()
        status = build_status(work, verify=True)
        if "parts" not in status:
            raise TakeoffError(
                EXIT_INVALID, status.get("parts_error") or "no parts/manifest.json: nothing to render"
            )
        manifest = load_manifest(work)
        ledger = load_ledger(work, status["project_id"], create=False)
        closures, built = closure_state(work, ledger), built_grid_answers(work, ledger)
        items, missing = load_items(work, ledger.registry, ledger.answers)
        for item in items:
            item.closed_by = closures.accepted.get(item.key)
            item.blocking = item.blocking or item.key in closures.forced
            item.built = built
        tagged: dict[str, set[str]] = {}
        for name, schema in PART_QUESTION_FILES:
            for q in (_read_document(work, name, schema) or {}).get("questions", []):
                for part in q.get("parts", []):
                    tagged.setdefault(part, set()).add(q["id"])
        findings = {}
        if (work / "reader-findings.json").is_file():
            findings = {f["id"]: f for f in list_findings(work)["findings"]}
        grid = _read_document(work, "grid-systems.json", "grid-system")
        ranked = sorted(
            (p for p in manifest["parts"] if p["kind"] != "bookkeeping"), key=lambda p: (p["order"], p["id"])
        )
        return cls(
            work=work, shown=shown_path(work, work.parent / OUT_NAME), manifest=manifest,
            status={p["id"]: p for p in status["parts"]},
            findings=findings, systems={s["system_id"]: s for s in (grid or {}).get("systems", [])},
            items={i.id: i for i in items}, missing=missing,
            questions={i.id: {"answer": None if i.is_open else i.answer} for i in items},
            tagged=tagged, marks=_read_document(work, "marks.json", "marks"),
            rank={p["id"]: n for n, p in enumerate(ranked, start=1)},
            project_id=status["project_id"], project_blocking_ids=list(status["project_blocking_ids"]),
        )  # fmt: skip

    def values(self, part: dict[str, Any]) -> list[Row]:
        if part["id"] not in self._values:
            doc, problems = read_values(self.work, part["id"], part["kind"])
            if doc is None:
                raise TakeoffError(EXIT_INVALID, problems[0].detail)
            self._values[part["id"]] = doc["rows"]
        return self._values[part["id"]]

    def text(self, file: str, entry: str) -> str:
        """The display text of an entry; the file's text index is loaded once for every part."""
        if file not in self._texts:
            if self._inventory is None:
                self._inventory = load_inventory(self.work)
            row = next((r for r in self._inventory.doc["files"] if r["path"] == file), None)
            loaded = load_file(self._inventory, row) if row is not None else None
            if loaded is None or loaded.text_index is None:
                raise TakeoffError(
                    EXIT_INVALID, f"{file}: there is no text index to read the cited entries from"
                )
            index = index_by_id(loaded.text_index)
            self._texts[file] = {k: _one_line(e["display_text"]) for k, e in index.items()}
        if entry not in self._texts[file]:
            raise TakeoffError(EXIT_INVALID, f"{file}: entry {entry} is not in its text index")
        return self._texts[file][entry]

    def saved(self, source: str) -> dict[str, Any]:
        if source not in self._saved:
            doc = _read_saved(self.work, source)
            if doc is None:
                raise TakeoffError(
                    EXIT_INVALID, f"{source} is missing or is not a saved geometry or contents document"
                )
            self._saved[source] = doc
        return self._saved[source]


# --- small helpers ------------------------------------------------------------------------------------


def _subject(row: Row) -> str:
    return str(row.get("mark") or row["subject"])


def _one_line(text: str) -> str:
    """Whitespace, line breaks included, collapsed to single spaces (as `findings` do): a line break would
    split a table row or a bullet."""
    return " ".join(text.split())


def _cell(text: str) -> str:
    return _one_line(text).replace("|", "\\|")  # D1: a `|` inside a table cell


def _groups(rows: list[Row]) -> dict[str, list[Row]]:
    groups: dict[str, list[Row]] = {}
    for r in rows:
        groups.setdefault(_subject(r), []).append(r)
    return groups


def _finding_ids(rows: list[Row]) -> list[str]:
    ids = {f for r in rows for f in (r.get("cites") or {}).get("findings", [])}
    ids |= {t["finding"] for r in rows for t in (r.get("hand_sum") or {}).get("terms", []) if "finding" in t}
    return sorted(ids, key=lambda i: (len(i), i))


def _cited_items(rows: list[Row]) -> dict[str, list[str]]:
    """Saved document -> the item ids the rows cite, in first-cite order."""
    cited: dict[str, dict[str, None]] = {}
    for r in rows:
        geometry = (r.get("cites") or {}).get("geometry")
        if geometry:
            cited.setdefault(geometry["source"], {}).update(dict.fromkeys(geometry["items"]))
    return {source: list(ids) for source, ids in cited.items()}


def _check_cites(ctx: TakeoffContext, part: str, rows: list[Row]) -> None:
    for r in rows:
        for fid in _finding_ids([r]):
            if fid not in ctx.findings:
                raise TakeoffError(EXIT_INVALID, f"{part} {r['row']}: finding {fid} is not an active finding")
        for sid in (r.get("cites") or {}).get("grid_systems", []):
            if sid not in ctx.systems:
                raise TakeoffError(
                    EXIT_INVALID, f"{part} {r['row']}: grid system {sid} is not in grid-systems.json"
                )


def _sheet_label(ctx: TakeoffContext, file: str, sheet: str, ref: dict[str, Any] | None) -> str:
    number = ctx.text(file, ref["number_entry"]) if ref and ref.get("number_entry") else None
    title = ctx.text(file, ref["title_entry"]) if ref and ref.get("title_entry") else None
    if number is None:
        return f"tờ chưa có số hiệu ({sheet})" + (f" '{title}'" if title else "")
    return f"{number} '{title}'" if title else number


def _find_sheet(ctx: TakeoffContext, part: dict[str, Any], file: str, sheet: str) -> dict[str, Any] | None:
    for p in [part, *ctx.manifest["parts"]]:
        for ref in p.get("sheets", []):
            if (ref["file"], ref["sheet"]) == (file, sheet):
                return ref  # type: ignore[no-any-return]
    return None


def _ref(ctx: TakeoffContext, part: dict[str, Any], row: Row) -> str:
    cites, file, sheet = row.get("cites") or {}, row.get("file"), row.get("sheet")
    segments: list[str] = []
    if file and sheet:
        label = _sheet_label(ctx, file, sheet, _find_sheet(ctx, part, file, sheet))
        view = row.get("view")
        if view and "heading_entry" in view:
            label += f", hình '{ctx.text(file, view['heading_entry'])}'"
        elif view:
            label += ", hình 'khung " + " ".join(f"{v:g}" for v in view["bbox"]) + "'"
        segments.append(label)
    elif file:
        segments.append(f"ngoài khung tờ ({file})")
    segments += [f"chữ '{ctx.text(str(file), t)}' ({t})" for t in cites.get("entries", [])]
    geometry = cites.get("geometry")
    ids = [*cites.get("findings", []), *cites.get("questions", [])]
    if geometry:
        ids.append(f"{Path(geometry['source']).name} ({len(geometry['items'])} mục)")
    if ids:
        segments.append(", ".join(ids))
    return " · ".join(segments)


def _addends(ctx: TakeoffContext, part: str, row: Row) -> list[tuple[str, int]]:
    """(label, value) per term of the row's `hand_sum`, as `hand_sum_addends` gives them. A term that cannot
    be read raises `TakeoffError` (exit 1): the bullet is never left out."""
    terms, file = row["hand_sum"]["terms"], row.get("file")
    texts = {(file, t["entry"]): ctx.text(file, t["entry"]) for t in terms if "entry" in t and file}
    found = hand_sum_addends(row, ctx.findings, ctx.marks, texts)
    if len(found) != len(terms):
        raise TakeoffError(
            EXIT_INVALID, f"{part} {row['row']}: a hand_sum term cannot be read: rerun harness part check"
        )
    return found


# --- the sections -------------------------------------------------------------------------------------


def _method(ctx: TakeoffContext, part: dict[str, Any], cited: dict[str, list[str]]) -> list[str]:
    sheets = [
        f"  - {_sheet_label(ctx, s['file'], s['sheet'], s)} ({ROLE_VI[s['role']]})"
        for s in part.get("sheets", [])
    ]
    redo = []
    for source in cited:
        doc = ctx.saved(source)
        redo.append(f"  - `{redo_command(ctx.shown, doc['kind'], doc['file'], doc['query'])}`")
    return ["- Tờ đã đọc:", *(sheets or [f"  - {NONE_VI}"]), "- Lệnh đo lại:", *(redo or [f"  - {NONE_VI}"])]


def _tokens(ctx: TakeoffContext, subject: str, rows: list[Row]) -> list[str]:
    """D2: only the outlines the subject's rows cite are positions of the subject."""
    items: list[dict[str, Any]] = []
    tol = 0.0
    for source, ids in _cited_items(rows).items():
        doc = ctx.saved(source)
        if doc["kind"] == "contents":
            items += [o for o in doc["outlines"] if o["id"] in ids]
            tol = max(tol, doc["query"]["tol"])
    return positions(items, subject, tol)


def _results(ctx: TakeoffContext, part: str, rows: list[Row]) -> list[str]:
    f, q = ctx.findings, ctx.questions

    def fields(sel: list[Row], names: tuple[str, ...]) -> str:
        cells = [field_cell(x, f, q) for n in names if (x := [r for r in sel if r["field"] == n])]
        return _cell(", ".join(cells) or "—")

    groups = _groups(rows)
    lines = ["| ký hiệu | kích thước | số lượng | trục |", "| --- | --- | --- | --- |"]
    for subject, sel in groups.items():
        axes = _cell(axes_cell(sel, _tokens(ctx, subject, sel), f, q))
        lines.append(
            f"| {_cell(subject)} | {fields(sel, SIZE_FIELDS)} | {fields(sel, COUNT_FIELDS)} | {axes} |"
        )
    lines += ["", "| ký hiệu | vật liệu | cao độ | finding | độ tin cậy |", "| --- | --- | --- | --- | --- |"]
    for subject, sel in groups.items():
        ids = ", ".join(_finding_ids(sel)) or "—"
        conf = conf_text(mark_confidence(sel, f, ctx.systems))
        material, levels = fields(sel, ("material",)), fields(sel, LEVEL_FIELDS)
        lines.append(f"| {_cell(subject)} | {material} | {levels} | {ids} | {conf} |")
    other = [_one_line(f"- {_subject(r)} — {row_cell(r, f, q)}") for r in rows if r["field"] == "other"]
    sums = [
        _one_line(f"- {_subject(r)} — {hand_sum_text(_addends(ctx, part, r))}")
        for r in rows
        if "hand_sum" in r
    ]
    return [
        *lines,
        "",
        "**Khác**",
        *(other or [f"- {NONE_VI}"]),
        "",
        "**Cộng tay**",
        *(sums or [f"- {NONE_VI}"]),
    ]


def _confidence(ctx: TakeoffContext, rows: list[Row]) -> str:
    counts = [row_confidence(r, ctx.findings, ctx.systems) for r in rows]
    shown = [f"{counts.count(c)} {CONF_VI[c]}" for c in ("high", "medium", "low")]
    shown.append(f"{counts.count(None)} {NO_FINDING_VI}")
    overall = conf_text(mark_confidence(rows, ctx.findings, ctx.systems))
    return f"**{overall}** — {len(rows)} giá trị: {', '.join(shown)}"


def _unclear(ctx: TakeoffContext, part: dict[str, Any], rows: list[Row]) -> list[str]:
    ids = set(ctx.tagged.get(part["id"], set())) | set(part.get("producer_questions", []))
    ids |= {q for r in rows for q in (r.get("cites") or {}).get("questions", [])}
    live = sorted((ctx.items[i] for i in ids if i in ctx.items), key=lambda i: int(i.id[2:]))
    lines: list[str] = []
    for rank in (0, 1, 2):
        for item in live:
            if (0 if item.is_open and item.blocking else 1 if item.is_open else 2) != rank:
                continue
            state = (
                ("blocking" if item.blocking else "non_blocking")
                if item.is_open
                else "answered"
                if item.answer
                else "closed"
            )
            label = QUESTION_STATE_VI[state]
            head = f"- **{item.id}** ({label}): {_need_impact(item)[0]}"
            block = _answer_block(item.answer) if item.answer and not item.is_open else [""]
            lines += [head + block[0], *block[1:]]
    return lines or [NONE_VI]


def _x_y(ctx: TakeoffContext, file: str) -> str:
    open_ids = sorted(
        (
            i.id
            for i in ctx.items.values()
            if i.is_open
            and i.code in (SYSTEM_AXIS_CODE, SELECT_CODE, GRID_MISSING_CODE)
            and i.file in (None, file)
        ),
        key=lambda i: int(i[2:]),
    )
    return f"chưa có ({', '.join(open_ids)})" if open_ids else "có"


def _coordinates(ctx: TakeoffContext, rows: list[Row], cited: dict[str, list[str]]) -> list[str]:
    if not cited:
        return [NONE_VI]
    lines: list[str] = []
    for source, ids in cited.items():
        doc = ctx.saved(source)
        lines.append(f"- `{source}`: {len(ids)} mục, đầu {ids[0]}, cuối {ids[-1]}")
        counts = [
            f"{s}: {len({i for r in sel for i in _cited_items([r]).get(source, [])})}"
            for s, sel in _groups(rows).items()
        ]
        lines += [
            "  - theo ký hiệu: " + ", ".join(counts),
            "  - trường dùng: " + ", ".join(DOC_FIELDS[doc["kind"]]),
        ]
        if doc["kind"] == "contents":
            groups = sorted(
                {a["group_id"] for o in doc["outlines"] if o["id"] in ids for a in o.get("axes") or []}
            )
            lines.append(
                f"  - lưới: `structure/{doc['file']}.grids.json`, nhóm {', '.join(groups) or NONE_VI}"
            )
        lines.append(f"  - Tekla X/Y: {_x_y(ctx, doc['file'])}")
    z = [r for r in rows if r["field"] in Z_FIELDS]
    qs = sorted({q for r in z for q in (r.get("cites") or {}).get("questions", [])}, key=lambda i: int(i[2:]))
    seen = [
        _one_line(f"{_subject(r)} {row_cell(r, ctx.findings, ctx.questions)}")
        for r in z
        if r["state"] == "seen"
    ]
    lines.append(
        f"- Z: {' | '.join(seen)}" if seen else f"- Z: {NONE_VI}" + (f" ({', '.join(qs)})" if qs else "")
    )
    return lines


def render_part(ctx: TakeoffContext, part: dict[str, Any], slots: dict[str, str]) -> str:
    """The whole file of one part. `slots`: name -> body kept from the disk; a missing one is a new slot."""
    rows = ctx.values(part)
    _check_cites(ctx, part["id"], rows)
    cited = _cited_items(rows)

    def slot(name: str) -> list[str]:
        return [f"<!-- ai:{name} -->", slots.get(name, PLACEHOLDER), f"<!-- /ai:{name} -->"]

    refs = [_one_line(f"- {_subject(r)} — {row_cell(r, ctx.findings, ctx.questions)}") for r in rows]
    refs = [
        f"{line} — {ref}" if (ref := _ref(ctx, part, r)) else line for line, r in zip(refs, rows, strict=True)
    ]
    body = [
        [*_method(ctx, part, cited), "", *slot("method")],
        _results(ctx, part["id"], rows),
        refs or [NONE_VI],
        [_confidence(ctx, rows), "", *slot("reason")],
        _unclear(ctx, part, rows),
        [status_line(ctx.status[part["id"]])],
        _coordinates(ctx, rows, cited),
    ]
    lines = [f"# {ctx.rank[part['id']]:02d} — {part['id']}"]
    for heading, section in zip(HEADINGS, body, strict=True):
        lines += ["", f"## {heading}", "", *section]
    return "\n".join(lines) + "\n"
