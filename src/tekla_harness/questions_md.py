"""questions_md: `harness questions-md`, render questions.md (Vietnamese) from every question source.

`questions.md` is the engineer's view of the questions; the JSON documents stay the source of truth and
nothing is read back from the Markdown. No agent writes this file by hand any more: this command renders
it, deterministically (same work folder and same --out folder give the same bytes; no timestamps, no
absolute path of the machine).

Sources (all read-only):
  * every question document of `questions.QUESTION_DOCUMENTS` that exists (intake, read-structure, callouts,
    marks, grid-system, reader): the question text, refs, counts and subjects;
  * `question-registry.json` + `answers.json`: which question is live, its producer and blocking flag, and
    whether it is answered. The documents' own `answer` fields are NOT used (they can lag behind). An
    answer to a question gate 1 reads settles it only when the engineer gave it (status.answer_closes):
    a simulated or role-less one stays open with the answer shown; every answer that is not the
    engineer's is labelled "(mô phỏng)" or "(chưa rõ vai trò)". The engineer's words-only answer to a code
    that needs values to close (status.words_only: grid_system_missing) stays open too, shown as not closed;
  * `harness status` (`status.build_status`): the gate-1 reasons and the per-step counts;
  * `grid-systems.json` + its SVGs and `structure-summary.json`: the proposals shown next to the questions
    they inform. A proposal is always labelled "ĐỀ XUẤT — chưa xác nhận" and is never an answer. A
    grid_system_conflict that grid-systems.json left non-blocking with no closure while its `file_sets`
    are pending is shown as waiting for that file_set_relation question, never as closed;
  * `status.closure_state` (the closures `harness status` accepts): a closed question is not
    open; it is listed in section 4 with why it closed. `supplements.load_supplements`: the reader's active
    supplements are printed under the question they supplement, verbatim.

Layout: 1 Tóm tắt; 2 blocking open questions; 3 non-blocking open questions (both grouped by topic in the
order of `questions_md_vi.TOPICS`, inside a topic by file then id); 4 Đã trả lời; 5 stale answers. Wording
of the known codes is `questions_md_vi.CODES` (proposed copy, pending engineer review); a code without a row
(a reader code, a new producer code) prints its English `message` verbatim and is listed in
`untranslated_codes`. Ids, codes, keys, file names, `found` / `where` strings and commands are verbatim.

Paths in the Markdown are relative to the folder holding questions.md (the work folder is `work/` in the
standard layout `projects/<id>/{questions.md, work/}`); in commands the work folder is the literal
`<work_dir>`.

Stdout: {"path", "questions", "blocking_open", "by_topic", "untranslated_codes"}.

Exit codes (AGENTS.md): 0 ok, 1 a document is invalid or inconsistent, 2 not a work folder.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tekla_harness import supplements
from tekla_harness.questions import (
    AXIS_CODE,
    AXIS_DIRECTIONS,
    CONFLICT_CODE,
    CONTRADICTION_CODE,
    FILE_SET_CODE,
    GRID_ANSWER_KEYS,
    GRID_ANSWER_SHEET_KEY,
    GRID_MISSING_CODE,
    PREFIX_CODE,
    QUESTION_DOCUMENTS,
    SELECT_CODE,
    SYSTEM_AXIS_CODE,
    UNIT_CODES,
    UNITS,
    Closure,
    QuestionsError,
    active_answers,
    load_ledger,
    write_text_atomic,
)
from tekla_harness.questions_md_vi import CODES, TOPICS, topic_of
from tekla_harness.schemas import validate
from tekla_harness.status import (
    NOT_CLOSED_BY_AN_ANSWER,
    StatusError,
    answer_closes,
    answer_counts,
    build_status,
    closure_state,
    words_only,
)

COMMAND = "questions-md"
HELP = "render questions.md (Vietnamese) from every question source of a work folder"
EXIT_OK, EXIT_INVALID, EXIT_USAGE = 0, 1, 2
OUT_NAME = "questions.md"
WORK_PLACEHOLDER = "<work_dir>"
PROJECT_LEVEL = "(cả dự án)"
UNTRANSLATED = "(chưa có bản dịch)"
PROPOSAL = "ĐỀ XUẤT — chưa xác nhận"
MAX_SYSTEMS_PER_QUESTION = 6
MAX_UNIT_FAMILIES = 10
MAX_TEMPLATE_KEYS = 8
SYSTEM_ID = re.compile(r"\bS[0-9]{3,}\b")
FAMILY_ID = re.compile(r"\bF[0-9]{3,}\b")
# structure questions that ask about the grid as a whole: the systems of their file are shown next to them
GRID_PROPOSAL_CODES = frozenset({AXIS_CODE, "grid_gate1_confirmation"})
STEP_TITLES = {
    "intake": "nhập bản vẽ",
    "read-structure": "đọc tờ, lưới trục, cao độ",
    "callouts": "đọc ghi chú cấu kiện",
    "marks": "ký hiệu và bảng thống kê",
    "grid-system": "hệ lưới",
    "reader": "người đọc bản vẽ",
}
OUTPUT_TITLES = {"fresh": "mới", "stale": "cũ", "missing": "thiếu", "n/a": "—"}
# every line that tells how to answer says it is the engineer's own step, never an agent's (review M1)
ENGINEER_STEP_VI = "kỹ sư tự chạy, tác tử không chạy thay"
# who answered, when it is not the engineer (answers.json answered_by_role; none: recorded before roles)
ROLE_TITLES = {"simulated": "mô phỏng"}
NO_ROLE = "chưa rõ vai trò"
CLOSURE_TITLES = {
    "not_selected": "một trong hai hệ lưới không được chọn",
    "separate": "hai hệ lưới là hai công trình riêng",
    "units_answered": "đơn vị của file đã được trả lời",
    "rejected_systems_only": "mọi họ lưới nêu trong câu thuộc hệ lưới không được chọn",
    "other_file_set": "các file thuộc hai bộ bản vẽ khác nhau",
}


class QuestionsMdError(Exception):
    """A run that cannot proceed; `exit_code` is the CLI exit code."""

    def __init__(self, exit_code: int, message: str) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass
class Item:
    """One live question: the document's text plus the registry's state."""

    id: str
    key: str
    code: str
    blocking: bool
    file: str | None
    message: str
    count: int
    truncated: bool
    refs: list[dict[str, Any]]
    subjects: list[dict[str, Any]] | None
    source: str
    producer: str
    topic: str
    answer: dict[str, Any] | None
    closed_by: Closure | None = None
    supplements: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_open(self) -> bool:
        """Open until answered or closed (lifecycle), except that an answer never closes a code no answer
        closes, and a gate producer's question needs the engineer's answer (the same rules as `harness
        status`: status.answer_closes)."""
        if self.closed_by is not None:
            return False
        return not answer_closes(self.producer, self.code, self.answer)


@dataclass
class Context:
    """What the renderer needs besides the questions."""

    work_rel: str  # work folder relative to the folder holding questions.md, POSIX
    out_dir: Path
    work: Path
    systems: list[dict[str, Any]] = field(default_factory=list)
    grids_state: str = "missing"  # status of the grid-system outputs: fresh | stale | missing
    families: dict[str, dict[str, Any]] = field(default_factory=dict)  # file -> structure-summary grids
    select_ids: list[str] = field(default_factory=list)  # ids of the grid_system_select question(s)
    conflicts: dict[str, dict[str, Any]] = field(default_factory=dict)  # grid-systems.json conflicts by key
    pending_file_set: str | None = None  # id of the file_set_relation question grid-systems.json waits for
    unit_answers: list[dict[str, Any]] = field(default_factory=list)  # active answers with a unit value


@dataclass
class Rendered:
    path: Path
    text: str
    summary: dict[str, Any]


# --- small helpers --------------------------------------------------------------------------------


def _id_number(question_id: str) -> int:
    return int(question_id[2:])


def code_span(text: Any) -> str:
    """Inline code, verbatim: the fence outgrows any backtick run in the text; newlines become spaces."""
    text = re.sub(r"\r\n|\r|\n", " ", str(text))
    if not text.strip():
        return "(trống)"
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    if longest == 0:
        return f"`{text}`"
    fence = "`" * (longest + 1)
    return f"{fence} {text} {fence}"


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise QuestionsMdError(EXIT_INVALID, f"{path.name} cannot be read: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise QuestionsMdError(EXIT_INVALID, f"{path.name} is not valid JSON: {exc}") from exc


def _read_valid(path: Path, schema: str, kind: str | None = None) -> dict[str, Any]:
    doc = _read_json(path)
    problems = validate(schema, doc)
    if problems or not isinstance(doc, dict) or (kind is not None and doc.get("kind") != kind):
        why = problems[0].message if problems else f"kind is not '{kind}'"
        raise QuestionsMdError(EXIT_INVALID, f"{path.name} is invalid ({schema} schema): {why}")
    return doc


def _relative(target: Path, start: Path) -> str:
    return Path(os.path.relpath(target, start)).as_posix()


# --- loading --------------------------------------------------------------------------------------


def load_items(
    work: Path, registry: dict[str, Any], answers_doc: dict[str, Any]
) -> tuple[list[Item], list[dict[str, str]]]:
    """Live questions from the documents (state from the registry and answers.json), and the ids of live
    registry questions that no document carries (their command has to be rerun)."""
    entries = registry["questions"]
    active = active_answers(answers_doc)
    items: list[Item] = []
    seen: set[str] = set()
    for name in QUESTION_DOCUMENTS:
        path = work / name
        if not path.is_file():
            continue
        doc = _read_valid(path, "intake", "questions")
        for q in doc["questions"]:
            entry = entries.get(q["key"])
            if entry is None or entry["id"] != q["id"]:
                raise QuestionsMdError(
                    EXIT_INVALID,
                    f"{name}: question {q['id']} (key {q['key']}) is not in question-registry.json "
                    "with that id: rerun the command that wrote this document",
                )
            if entry["status"] == "obsolete" or q["key"] in seen:
                continue
            seen.add(q["key"])
            items.append(
                Item(
                    id=q["id"],
                    key=q["key"],
                    code=q["code"],
                    blocking=entry.get("blocking", True),
                    file=q["file"],
                    message=q["message"],
                    count=q["count"],
                    truncated=q["truncated"],
                    refs=q["refs"],
                    subjects=q.get("subjects"),
                    source=name,
                    producer=entry["producer"],
                    topic=topic_of(q["code"], entry["producer"]),
                    answer=active.get(q["key"]),
                )
            )
    missing = [
        {"id": e["id"], "code": e["code"], "producer": e["producer"]}
        for key, e in sorted(entries.items(), key=lambda kv: _id_number(kv[1]["id"]))
        if e["status"] != "obsolete" and key not in seen
    ]
    return items, missing


def _load_context(work: Path, out_dir: Path, status: dict[str, Any]) -> Context:
    ctx = Context(work_rel=_relative(work, out_dir), out_dir=out_dir, work=work)
    grid_step = next(p for p in status["producers"] if p["producer"] == "grid-system")
    ctx.grids_state = grid_step["outputs"]["status"]
    grid_path = work / "grid-systems.json"
    if grid_path.is_file():
        grid_doc = _read_valid(grid_path, "grid-system")
        ctx.systems = grid_doc["systems"]
        ctx.conflicts = {c["question_key"]: c for c in grid_doc["conflicts"] if c["question_key"]}
        file_sets = grid_doc.get("file_sets")
        if file_sets is not None and file_sets["status"] == "pending":
            ctx.pending_file_set = file_sets["question_id"]
    summary_path = work / "structure-summary.json"
    if summary_path.is_file():
        summary = _read_valid(summary_path, "intake", "structure_summary")
        ctx.families = {f["path"]: f["grids"] for f in summary["files"] if f.get("grids")}
    return ctx


# --- answer command -------------------------------------------------------------------------------


def answer_values(item: Item, answered_unit: str | None = None) -> list[str]:
    """`k=v` templates of the structured values `harness answer` requires for this code (see
    answers.check_values); a leading '?' marks an optional one. `answered_unit`: the unit already answered
    for the file, the only value `units_answer_contradicts_evidence` takes (it confirms that unit)."""
    if item.code == CONTRADICTION_CODE and answered_unit is not None:
        return [f"unit={answered_unit}"]
    if item.code in UNIT_CODES or item.code == CONTRADICTION_CODE:
        return ["unit=<" + "|".join(UNITS) + ">"]
    if item.code == AXIS_CODE:
        families: list[str] = []
        for ref in item.refs:
            for fid in FAMILY_ID.findall(ref["found"]):
                if fid not in families:
                    families.append(fid)
        return [f"{fid}=<X|Y>" for fid in (families[:MAX_TEMPLATE_KEYS] or ["<family_id>"])]
    if item.code == PREFIX_CODE:
        names = [s["name"] for s in item.subjects or []][:MAX_TEMPLATE_KEYS]
        return [f"{name}=<meaning>" for name in (names or ["<prefix>"])]
    if item.code == SYSTEM_AXIS_CODE:  # one value per direction (the subjects dir1, dir2), distinct axes
        return [f"{s['name']}=<X|Y>" for s in item.subjects or [{"name": n} for n in AXIS_DIRECTIONS]]
    if item.code == SELECT_CODE:
        return ["?systems=S001,S002", "?separate=S001,S002"]
    if item.code == FILE_SET_CODE:  # every file of the question exactly once, one set per building
        return ["set1=<file>,<file>", "?set2=<file>,..."]
    if item.code == GRID_MISSING_CODE:  # ADR-0013 §2: both directions, spacings one fewer than labels
        templates = {"labels": "<label>,<label>,...", "spacings": "<spacing>,..."}
        keys = [f"{key}={templates[key.split('_')[1]]}" for key in GRID_ANSWER_KEYS]
        return [*keys, f"?{GRID_ANSWER_SHEET_KEY}=<sheet id>"]
    return []


def answer_command(item: Item, answered_unit: str | None = None) -> str:
    """The command that records the engineer's answer (`--role engineer`: gate 1 counts no other role)."""
    parts = [f'uv run harness answer {WORK_PLACEHOLDER} {item.id} --text "..." --by "..." --role engineer']
    for value in answer_values(item, answered_unit):
        parts.append(f"[--value {value[1:]}]" if value.startswith("?") else f"--value {value}")
    return " ".join(parts)


# --- proposals ------------------------------------------------------------------------------------


def _system_lines(system: dict[str, Any], ctx: Context) -> list[str]:
    flags = ", ".join(code_span(f) for f in system["flags"]) or "không có"
    lines = [
        f"  - lưới {code_span(system['system_id'])} (độ tin cậy {code_span(system['confidence'])}; "
        f"cờ: {flags}), khoảng cách tính theo đơn vị bản vẽ:"
    ]
    for number, direction in enumerate(system["directions"], 1):
        lines.append(
            f"    - hướng {number}, nhãn {code_span(' '.join(direction['labels']))}: "
            f"{code_span(direction['coordinates'])}"
        )
    svg = ctx.work / system["svg"]
    if svg.is_file():
        lines.append(f"    - hình: {code_span(_relative(svg, ctx.out_dir))}")
    else:
        lines.append("    - hình: chưa có file hình (chạy lại `harness grid-system` không dùng --no-svg)")
    return lines


def grid_proposals(item: Item, ctx: Context) -> list[str]:
    """The grid systems that inform a grid question, verbatim from grid-systems.json (empty: none)."""
    if item.code.startswith("grid_system_"):
        # the select refs name system ids; an axis or conflict question names families (its key is stable
        # when systems are renumbered), so its systems come from grid-systems.json by question key
        wanted = {sid for ref in item.refs for sid in SYSTEM_ID.findall(ref["where"])}
        wanted |= {s["system_id"] for s in ctx.systems if s.get("axis_question_key") == item.key}
        conflict = ctx.conflicts.get(item.key)
        wanted |= set(conflict["systems"]) if conflict is not None else set()
        systems = [s for s in ctx.systems if s["system_id"] in wanted]
    elif item.code in GRID_PROPOSAL_CODES and item.file is not None:
        systems = [
            s for s in ctx.systems if any(c["file"] == item.file for c in s["evidence"]["contributors"])
        ]
    else:
        return []
    if not systems:
        return []
    shown = systems[:MAX_SYSTEMS_PER_QUESTION]
    head = f"- **{PROPOSAL}.** Lưới trục tìm được trong bản vẽ"
    if len(systems) > len(shown):
        head += f" (hiển thị {len(shown)}/{len(systems)} hệ lưới)"
    if ctx.grids_state != "fresh":
        head += f" — chú ý: kết quả hệ lưới đang {OUTPUT_TITLES.get(ctx.grids_state, ctx.grids_state)}"
    lines = [head + ":"]
    for system in shown:
        lines += _system_lines(system, ctx)
    return lines


def unit_proposals(file: str, ctx: Context) -> list[str]:
    """Grid spacing strings of the file's families in drawing units (structure-summary.json). The header
    `unit` label is deliberately not printed: it is the very thing the units question asks about."""
    grids = ctx.families.get(file)
    if not grids:
        return []
    distinct: dict[tuple[str, str, bool], int] = {}
    for fam in grids["families"]:
        if fam["coordinates"] is None:  # a family without spacings (one axis): nothing to propose
            continue
        key = (fam["labels"], fam["coordinates"], fam["complete"])
        distinct[key] = distinct.get(key, 0) + 1
    if not distinct:
        return []
    shown = list(distinct.items())[:MAX_UNIT_FAMILIES]
    head = f"- **{PROPOSAL}.** Khoảng cách lưới trục đọc được trong file này, tính theo đơn vị bản vẽ"
    if len(shown) < len(distinct):
        head += f" (hiển thị {len(shown)}/{len(distinct)} dạng khác nhau)"
    if grids["families_truncated"]:
        head += (
            f" (danh sách họ lưới trong structure-summary.json đã cắt: {len(grids['families'])}/"
            f"{grids['families_total']} họ)"
        )
    lines = [head + ":"]
    for (labels, coordinates, complete), times in shown:
        note = "" if complete else ", chưa đầy đủ"
        lines.append(f"  - nhãn {code_span(labels)}: {code_span(coordinates)} (xuất hiện {times} lần{note})")
    return lines


def answered_unit(item: Item, ctx: Context) -> str | None:
    """The one unit answered for the question's file (answers without a file count for every file)."""
    units = {
        str(a["values"]["unit"]) for a in ctx.unit_answers if a["file"] in (item.file, None) and a["values"]
    }
    return next(iter(units)) if len(units) == 1 else None


# --- one question ---------------------------------------------------------------------------------


def supplement_lines(item: Item) -> list[str]:
    """The reader's active supplements to this question, verbatim (`harness ask --supplement`)."""
    rows = [s for s in item.supplements if s.get("status") == "active"]
    if not rows:
        return []
    lines = ["- **Bổ sung của người đọc:**"]
    for s in rows:
        extra = ""
        if s.get("sheet"):
            extra += f" · tờ {code_span(s['sheet'])}"
        if s.get("file") is not None and s.get("file") != item.file:
            extra += f" · file {code_span(s['file'])}"
        lines.append(f"  - {code_span(s['where'])} — {code_span(s['found'])}{extra}: {code_span(s['text'])}")
    return lines


def closed_line(item: Item) -> str:
    """Section 4 line of a question closed without an answer of its own (lifecycle.closures)."""
    assert item.closed_by is not None
    where = code_span(item.file) if item.file is not None else PROJECT_LEVEL
    label = "CHẶN" if item.blocking else "không chặn"
    reason = item.closed_by.reason
    why = f"{CLOSURE_TITLES.get(reason, reason)} ({code_span(reason)})"
    by = f"; theo câu {item.closed_by.question_id}" if item.closed_by.question_id else ""
    return f"- {item.id} · {code_span(item.code)} · {where} · {label} — đã đóng: {why}{by}"


def _need_impact(item: Item) -> tuple[str, str, bool]:
    """(Cần gì, Ảnh hưởng, translated). A reader question is written in Vietnamese by the reader agent
    (`harness ask --text`) and always shows its own text verbatim: it is never 'untranslated'."""
    row = CODES.get(item.code)
    if item.producer == "reader":
        return (code_span(item.message), "do người đọc bản vẽ nêu ra; ghi trong câu hỏi.", True)
    if row is None:
        return (
            f"{UNTRANSLATED} Câu hỏi gốc (nguyên văn): {code_span(item.message)}",
            f"{UNTRANSLATED} xem câu hỏi gốc.",
            False,
        )
    return row[1], row[2], True


def pending_file_set(item: Item, ctx: Context) -> str | None:
    """The file_set_relation question id an open conflict waits for: grid-systems.json left it non-blocking
    with no closure while that question is pending. None otherwise: an open conflict is never shown as
    closed here (a real closure moves it to section 4), it says how to close it."""
    conflict = ctx.conflicts.get(item.key)
    if item.code != CONFLICT_CODE or item.blocking or conflict is None:
        return None
    if conflict["blocking"] or conflict["closed_by"] is not None:
        return None
    return ctx.pending_file_set


def question_lines(item: Item, ctx: Context, level: str = "#####") -> list[str]:
    need, impact, _ = _need_impact(item)
    label = "CHẶN" if item.blocking else "không chặn"
    lines = [
        f"{level} {item.id} · {code_span(item.code)} · {label}",
        f"- **File:** {code_span(item.file) if item.file is not None else PROJECT_LEVEL}",
        f"- **Cần gì:** {need}",
        f"- **Ảnh hưởng:** {impact}",
    ]
    source = code_span(f"{ctx.work_rel}/{item.source}")
    places = f"- **Số chỗ:** {item.count}"
    if item.truncated or len(item.refs) < item.count:
        places += f" (hiển thị {len(item.refs)}/{item.count}; danh sách đầy đủ ở {source})"
    lines.append(f"{places} · **Nguồn:** {source} · key {code_span(item.key)}")
    if item.subjects:
        shown = ", ".join(f"{code_span(s['name'])} ({s['count']})" for s in item.subjects)
        lines.append(f"- **Chủ đề:** {shown}")
    lines.append("- **Đã thấy (nguyên văn):**")
    for ref in item.refs:
        extra = ""
        if ref.get("sheet"):
            extra += f" · tờ {code_span(ref['sheet'])}"
        if ref.get("file") != item.file and ref.get("file") is not None:
            extra += f" · file {code_span(ref['file'])}"
        lines.append(f"  - {code_span(ref['where'])} — {code_span(ref['found'])}{extra}")
        if "message" in ref:
            lines.append(f"    - câu hỏi riêng của chỗ này (nguyên văn): {code_span(ref['message'])}")
    lines += grid_proposals(item, ctx)
    lines += supplement_lines(item)
    if item.answer is None:
        lines.append("- **Trả lời:** _chưa có_")
    elif item.code in NOT_CLOSED_BY_AN_ANSWER:  # a code no answer closes: show the answer, it closes nothing
        block = _answer_block(item.answer)
        lines.append(
            "- **Trả lời:** không đóng được câu này" + block[0].replace(" — trả lời", "; câu trả lời cũ", 1)
        )
        lines += block[1:]
    elif words_only(item.code, item.answer) and answer_counts(item.producer, item.answer):
        # the engineer's answer in words only to a code that needs values (ADR-0013 decision 2): not closed
        block = _answer_block(item.answer)
        values = " ".join(
            code_span(f"[--value {v[1:]}]" if v.startswith("?") else f"--value {v}")
            for v in answer_values(item)
        )
        lines.append(
            "- **Trả lời:** chưa đóng: câu trả lời chỉ có lời, không có giá trị lưới nên không dựng được hệ "
            f"lưới; kỹ sư trả lời lại kèm giá trị ({values})"
            + block[0].replace(" — trả lời", "; câu trả lời hiện có", 1)
        )
        lines += block[1:]
    else:  # not the engineer's answer to a question gate 1 reads (status.answer_counts): shown, not counted
        block = _answer_block(item.answer)
        lines.append(
            "- **Trả lời:** chưa tính vì không phải kỹ sư trả lời; kỹ sư tự trả lời lại"
            + block[0].replace(" — trả lời", "; câu trả lời hiện có", 1)
        )
        lines += block[1:]
    pending = pending_file_set(item, ctx)
    if pending is not None:
        rerun = code_span("harness grid-system " + WORK_PLACEHOLDER)
        lines.append(
            f"- **Trạng thái:** chưa chặn, đang chờ câu {pending} ({code_span(FILE_SET_CODE)}): hai hệ lưới "
            "nằm ở hai file bản vẽ khác nhau, có thể thuộc hai dự án riêng. Kỹ sư trả lời câu "
            f"{pending} trước ({ENGINEER_STEP_VI}), rồi chạy lại {rerun}; sau đó hai hệ "
            "chỉ được so với nhau khi cùng một bộ file."
        )
    elif item.code == CONFLICT_CODE:  # `harness answer` refuses it: it closes only through the select answer
        select = ", ".join(ctx.select_ids) or code_span(SELECT_CODE)
        systems_opt = code_span("--value systems=...")
        separate_opt = code_span("--value separate=Sxxx,Syyy")
        rerun = code_span("harness grid-system " + WORK_PLACEHOLDER)
        lines.append(
            f"- **Cách đóng ({ENGINEER_STEP_VI}):** câu này không trả lời trực tiếp. Kỹ sư trả lời câu "
            f"{select} ({code_span(SELECT_CODE)}) với {systems_opt} bỏ một trong hai hệ, hoặc {separate_opt} "
            f"nếu là hai toà nhà khác nhau (cả hai phải nằm trong systems); rồi chạy lại {rerun}."
        )
    else:
        # the engineer's own step, never an agent's (review M1): the label says so
        lines.append(
            f"- **Lệnh trả lời ({ENGINEER_STEP_VI}):** "
            f"{code_span(answer_command(item, answered_unit(item, ctx)))}"
        )
    return lines


# --- sections -------------------------------------------------------------------------------------


def _file_sort(file: str | None) -> tuple[int, str]:
    return (0, "") if file is None else (1, file)


def _topic_sections(items: list[Item], ctx: Context) -> list[str]:
    lines: list[str] = []
    for slug, title in TOPICS:
        group = [i for i in items if i.topic == slug]
        if not group:
            continue
        lines += ["", f"### {title} ({len(group)})"]
        by_file: dict[str | None, list[Item]] = {}
        for item in sorted(group, key=lambda i: (_file_sort(i.file), _id_number(i.id))):
            by_file.setdefault(item.file, []).append(item)
        for file, members in by_file.items():
            where = code_span(file) if file is not None else PROJECT_LEVEL
            lines += ["", f"#### {where} — {', '.join(m.id for m in members)}"]
            if slug == "units" and file is not None:
                proposal = unit_proposals(file, ctx)
                if proposal:
                    lines += ["", *proposal]
            for member in members:
                lines += ["", *question_lines(member, ctx)]
    return lines


def _value_text(value: Any) -> str:
    return ",".join(str(v) for v in value) if isinstance(value, list) else str(value)


def _role_label(answer: dict[str, Any]) -> str:
    """' (mô phỏng)' / ' (chưa rõ vai trò)' after a non-engineer answer; nothing after the engineer's."""
    role = answer.get("answered_by_role")
    if role == "engineer":
        return ""
    return f" ({ROLE_TITLES.get(role, str(role)) if role is not None else NO_ROLE})"


def _answer_block(answer: dict[str, Any]) -> list[str]:
    text = answer["answer_text"]
    values = ", ".join(f"{k}={_value_text(v)}" for k, v in sorted(answer["values"].items()))
    tail = f"{answer['answered_by']}, {answer['answered_on']}" + (
        f"; giá trị {code_span(values)}" if values else ""
    )
    head = " — trả lời" + _role_label(answer)
    if "\n" not in text and "\r" not in text:
        return [f"{head}: {code_span(text)} ({tail})"]
    fence = "`" * max(3, max((len(r) for r in re.findall(r"`+", text)), default=0) + 1)
    return [f"{head} ({tail}):", f"  {fence}text", *(f"  {ln}" for ln in text.splitlines()), f"  {fence}"]


def _answered_lines(items: list[Item]) -> list[str]:
    lines = []
    for item in sorted(items, key=lambda i: _id_number(i.id)):
        if item.closed_by is not None:
            lines.append(closed_line(item))
            continue
        assert item.answer is not None
        where = code_span(item.file) if item.file is not None else PROJECT_LEVEL
        label = "CHẶN" if item.blocking else "không chặn"
        head = f"- {item.id} · {code_span(item.code)} · {where} · {label}"
        block = _answer_block(item.answer)
        lines.append(head + block[0])
        lines += block[1:]
    return lines


STALE_PATTERNS = (
    (
        re.compile(r"the input file was (changed|removed) since the answer was given"),
        "file bản vẽ đã {0} sau khi trả lời",
    ),
    (
        re.compile(r"the latest (.+) run no longer raises this question"),
        "lần chạy `{0}` gần nhất không còn đặt câu hỏi này",
    ),
    (re.compile(r"the question was withdrawn: (.+)"), "câu hỏi đã được rút lại: {0}"),
)
STALE_WORDS = {"changed": "bị đổi", "removed": "bị xoá"}


def stale_reason_vi(reason: str) -> str:
    for pattern, template in STALE_PATTERNS:
        m = pattern.fullmatch(reason)
        if m:
            return template.format(*(STALE_WORDS.get(g, g) for g in m.groups()))
    return code_span(reason)


def _stale_lines(answers_doc: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    stale = [a for a in answers_doc["answers"] if a["status"] == "stale"]
    for a in sorted(stale, key=lambda a: (_id_number(a["question_id"]), a["answered_on"])):
        where = code_span(a["file"]) if a["file"] is not None else PROJECT_LEVEL
        block = _answer_block(a)
        reason = stale_reason_vi(a["stale_reason"])
        head = f"- {a['question_id']} · {code_span(a['code'])} · {where} — đã cũ vì: {reason}"
        lines.append(head + block[0].replace(" — trả lời", "; câu trả lời cũ", 1))
        lines += block[1:]
    return lines


# --- gate 1 reasons in Vietnamese ---------------------------------------------------------------------


def _step(label: str) -> str:
    return f"{STEP_TITLES.get(label, label)} ({code_span(label)})"


def _output_why(why: str) -> str:
    m = re.fullmatch(r"(.+) not found", why)
    if m:
        return f"không thấy {m.group(1)}"
    m = re.fullmatch(r"(.+) was built from another inventory.json \(intake reran since\)", why)
    if m:
        return f"{m.group(1)} được tạo từ inventory.json cũ, intake đã chạy lại"
    if why == "grid-systems.json was built before the latest answers it reads (units, axes, selection)":
        return "grid-systems.json được tạo trước các câu trả lời mới nhất mà nó đọc (đơn vị, trục, chọn hệ)"
    return code_span(why)


def _ids_vi(ids: str) -> str:
    return re.sub(r" and (\d+) more$", r" và \1 câu nữa", ids)


def _open_note(note: str | None) -> str:
    if not note:
        return ""
    m = re.fullmatch(
        r"; (\d+) of the producer's questions have no recorded blocking flag "
        r"\(rerun (.+)\) and count as blocking",
        note,
    )
    if m:
        return f"; {m.group(1)} câu hỏi chưa ghi cờ chặn (chạy lại {code_span(m.group(2))}), tính là chặn"
    return f" {code_span(note)}"


REASONS: tuple[tuple[re.Pattern[str], Callable[[re.Match[str]], str]], ...] = (
    (
        re.compile(r"grid systems: not checked, the grid-system outputs are (?P<st>\w+)"),
        lambda m: (
            f"hệ lưới: chưa kiểm tra được vì kết quả hệ lưới đang {OUTPUT_TITLES.get(m['st'], m['st'])}"
        ),
    ),
    (
        re.compile(r"grid systems: none found in the drawings.*"),
        lambda m: "hệ lưới: không tìm thấy lưới trục dùng được trong bản vẽ",
    ),
    (
        re.compile(r"levels: (?P<id>Q-\d+) (?P<code>\w+) \((?P<f>.+)\) is not answered"),
        lambda m: f"cao độ: {m['id']} {code_span(m['code'])} ({code_span(m['f'])}) chưa được trả lời",
    ),
    (
        re.compile(
            r"(?P<label>[\w-]+): (?P<n>\d+) blocking question\(s\) open \((?P<ids>.+?)\)(?P<note>; .*)?"
        ),
        lambda m: (
            f"{_step(m['label'])}: còn {m['n']} câu hỏi chặn chưa trả lời ({_ids_vi(m['ids'])})"
            f"{_open_note(m['note'])}"
        ),
    ),
    (
        re.compile(r"(?P<label>[\w-]+): outputs (?P<st>\w+) \((?P<why>.+)\); rerun (?P<cmd>.+)"),
        lambda m: (
            f"{_step(m['label'])}: kết quả đang {OUTPUT_TITLES.get(m['st'], m['st'])} "
            f"({_output_why(m['why'])}); chạy lại {code_span(m['cmd'])}"
        ),
    ),
)
# Reasons about units, grid systems and levels are written by `harness status` as one English sentence that
# names the question id and the exact command to run; they move with the gate rules, so they are shown
# verbatim after a Vietnamese category instead of being translated here.
CATEGORIES = (
    ("units", "đơn vị"),
    ("files", "file bản vẽ"),
    ("grid systems", "hệ lưới"),
    ("levels", "cao độ"),
    ("answers", "câu trả lời"),
    ("closures", "đóng câu hỏi"),
)


def reason_vi(reason: str) -> str:
    """A gate-1 reason from `harness status` in Vietnamese: the known shapes are translated, the others keep
    their English sentence (verbatim, in code) after a Vietnamese category."""
    for pattern, translate in REASONS:
        m = pattern.fullmatch(reason)
        if m:
            return translate(m)
    for prefix, category in CATEGORIES:
        if reason.startswith(prefix + ": "):
            return f"{category}: {code_span(reason[len(prefix) + 2 :])}"
    return f"{code_span(reason)} {UNTRANSLATED}"


# --- the document ---------------------------------------------------------------------------------


def _summary_lines(
    status: dict[str, Any],
    items: list[Item],
    missing: list[dict[str, str]],
    stale: int,
    ctx: Context,
    reasons: list[str],
) -> list[str]:
    blocking = [i for i in items if i.blocking]
    open_blocking = [i for i in blocking if i.is_open]
    open_other = [i for i in items if not i.blocking and i.is_open]
    ready = status["gate1"]["ready_for_gate1"]
    lines = [
        "## 1. Tóm tắt",
        "",
        f"- **Dự án:** {code_span(status['project_id'])}",
        f"- **Thư mục làm việc:** trong lệnh viết là `{WORK_PLACEHOLDER}`; đường dẫn trong file này tính "
        f"từ thư mục chứa file này, thư mục làm việc là {code_span(ctx.work_rel)}.",
        f"- **Số câu hỏi:** {len(items)} (chặn {len(blocking)}, không chặn {len(items) - len(blocking)})",
        f"- **Chặn đang mở:** {len(open_blocking)} · **không chặn đang mở:** {len(open_other)} · "
        f"**đã trả lời:** {len(items) - len(open_blocking) - len(open_other)} · "
        f"**câu trả lời đã cũ:** {stale}",
        f"- **Cổng 1:** {'SẴN SÀNG' if ready else 'CHƯA SẴN SÀNG'}"
        + ("" if ready else f" — {len(reasons)} lý do:"),
    ]
    lines += [f"  - {reason_vi(r)}" for r in reasons]
    if missing:
        listed = ", ".join(f"{m['id']} ({code_span(m['code'])})" for m in missing[:20])
        more = f" và {len(missing) - 20} câu nữa" if len(missing) > 20 else ""
        lines.append(
            f"- **Chú ý:** {len(missing)} câu hỏi có trong sổ câu hỏi (question-registry.json) nhưng không "
            f"có trong file câu hỏi nào nên chưa hiện ở dưới: {listed}{more}. Chạy lại lệnh đã tạo ra chúng "
            "(xem cột Lệnh bên dưới)."
        )
    lines += [
        "",
        "| Bước | Lệnh | Số câu hỏi | Chặn đang mở | Đã trả lời | Kết quả |",
        "|---|---|---|---|---|---|",
    ]
    for p in status["producers"]:
        q = p["questions"]
        lines.append(
            f"| {STEP_TITLES.get(p['producer'], p['producer'])} | {code_span(p['command'])} | {q['total']} "
            f"| {q['blocking_open']} | {q['answered']} | {OUTPUT_TITLES.get(p['outputs']['status'], '—')} |"
        )
    return lines


def render_questions_md(work_dir: Path | str, out: Path | str | None = None) -> Rendered:
    """Render questions.md for a work folder (see the module docstring). Raises QuestionsMdError."""
    work = Path(work_dir).resolve()
    if not work.is_dir():
        raise QuestionsMdError(EXIT_USAGE, f"not a work folder (not a folder): {work_dir}")
    out_path = Path(out).resolve() if out is not None else work.parent / OUT_NAME
    if out_path.is_dir():
        raise QuestionsMdError(EXIT_USAGE, f"--out {out} is a folder: name the questions.md file")
    try:
        status = build_status(work)
        ledger = load_ledger(work, status["project_id"], create=False)
        supplement_rows = supplements.load_supplements(work)
        closures = closure_state(work, ledger)  # the closures harness status accepts
    except (StatusError, QuestionsError) as exc:
        raise QuestionsMdError(exc.exit_code, str(exc)) from exc
    items, missing = load_items(work, ledger.registry, ledger.answers)
    by_target: dict[str, list[dict[str, Any]]] = {}
    for row in supplement_rows:
        by_target.setdefault(row["target_key"], []).append(row)
    for item in items:
        item.closed_by = closures.accepted.get(item.key)
        item.blocking = item.blocking or item.key in closures.forced  # a refused written closure blocks
        item.supplements = by_target.get(item.key, [])
    ctx = _load_context(work, out_path.parent, status)
    ctx.select_ids = sorted((i.id for i in items if i.code == SELECT_CODE), key=_id_number)
    ctx.unit_answers = [
        a
        for a in active_answers(ledger.answers).values()
        if a["code"] in UNIT_CODES and a["values"].get("unit")
    ]
    reasons = [r.replace(str(work), WORK_PLACEHOLDER) for r in status["gate1"]["reasons"]]
    stale = sum(1 for a in ledger.answers["answers"] if a["status"] == "stale")

    open_blocking = [i for i in items if i.blocking and i.is_open]
    open_other = [i for i in items if not i.blocking and i.is_open]
    answered = [i for i in items if not i.is_open]
    lines = [
        f"# Câu hỏi cho kỹ sư — {status['project_id']}",
        "",
        "File này do lệnh `uv run harness questions-md` tạo ra từ các file câu hỏi của thư mục làm việc; "
        "đừng sửa tay. Câu trả lời chỉ được ghi bằng `harness answer`: sửa file này không ghi nhận gì.",
        'Mục "Đã thấy" và "Đề xuất" là dữ liệu đọc từ bản vẽ, nguyên văn; đề xuất chưa phải câu trả lời.',
        "",
        *_summary_lines(status, items, missing, stale, ctx, reasons),
        "",
        f"## 2. Câu hỏi chặn đang mở ({len(open_blocking)})",
    ]
    lines += _topic_sections(open_blocking, ctx) if open_blocking else ["", "_Không có._"]
    lines += ["", f"## 3. Câu hỏi không chặn đang mở ({len(open_other)})"]
    lines += _topic_sections(open_other, ctx) if open_other else ["", "_Không có._"]
    lines += ["", f"## 4. Đã trả lời ({len(answered)})", ""]
    lines += _answered_lines(answered) if answered else ["_Chưa có._"]
    stale_lines = _stale_lines(ledger.answers)
    lines += ["", f"## 5. Câu trả lời đã cũ ({stale})", ""]
    lines += (
        [
            "Các câu trả lời này không còn dùng được (file bản vẽ đổi hoặc câu hỏi không còn được đặt). "
            "Nếu câu hỏi vẫn còn, nó nằm ở mục 2 hoặc 3 và cần trả lời lại.",
            "",
            *stale_lines,
        ]
        if stale_lines
        else ["_Không có._"]
    )
    text = "\n".join(lines) + "\n"

    by_topic = {slug: n for slug, _ in TOPICS if (n := sum(1 for i in items if i.topic == slug))}
    untranslated = sorted({i.code for i in items if i.code not in CODES and i.producer != "reader"})
    summary = {
        "path": str(out_path),
        "questions": len(items),
        "blocking_open": len(open_blocking),
        "by_topic": by_topic,
        "untranslated_codes": untranslated,
    }
    return Rendered(out_path, text, summary)


# --- the command ----------------------------------------------------------------------------------


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("work_dir", help="the intake work folder (--out of `harness intake`)")
    parser.add_argument(
        "--out",
        default=None,
        metavar="PATH",
        help="where to write questions.md (default: questions.md next to the work folder, i.e. "
        "<work_dir>/../questions.md)",
    )


def run(args: argparse.Namespace) -> int:
    try:
        rendered = render_questions_md(Path(args.work_dir), args.out)
        write_text_atomic(rendered.path, rendered.text)
    except QuestionsMdError as exc:
        print(f"harness {COMMAND}: {exc}", file=sys.stderr)
        return exc.exit_code
    except OSError as exc:
        print(f"harness {COMMAND}: cannot write questions.md: {exc}", file=sys.stderr)
        return 3
    print(json.dumps(rendered.summary, ensure_ascii=False, indent=2))
    return EXIT_OK
