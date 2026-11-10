"""EVAL-5 deterministic metrics for one evaluated project folder (pre-registered 2026-11-10; EVAL-4 metrics
with one fix: the engineer-rerun diagnostic also reads an answer-built system's file from its directions).

Usage: uv run python dwg-lab/proposals/skills/eval5/metrics.py <project-dir> [--prose FILE ...]

<project-dir> holds `work/` (the harness work folder) and the prose deliverables (`01-analysis.md`,
`02-plan.md` by default; `--prose` replaces that list). Prints one JSON document on stdout; exit 0 ok,
2 usage error, 3 missing work folder. Read-only.

Metrics (definitions are part of the EVAL-5 protocol, EVAL-5-PROTOCOL.md §4; M1-M5 as in EVAL-3 with its
pre-run amendments folded in, M6 new):
  M1 blocked_share     per drawing file: non-ASCII text entries whose meaning is blocked by the legacy-font
                       gate (`text_gate.meaning_block_reason`) / all non-ASCII text entries. ASCII entries
                       blocked by any later rule are counted apart (`ascii_blocked`), not in the share.
  M2 producer_values   entry ids cited by producer outputs (levels, grids, callouts, marks) outside their
                       `blocked*` lists that are blocked in the text index of the same file. Must be 0.
  M3 prose_leaks       candidate leaks: a run of 3 words (>= 2 with Vietnamese letters) obtained by
                       decoding a BLOCKED entry (TCVN3 and VNI tried) that appears in the prose but in
                       no ALLOWED entry of the project and not in the BACKGROUND vocabulary. Candidates
                       are adjudicated by the judges; the confirmed count must be 0.
  M4 gate1_blockers    open blocking questions in the registry, classed by code into `content` or
                       `procedural` (table below, fixed before the run); `unclassified` is reported and counts
                       as procedural for the pass bar (conservative).
  M5 questions         registry counts by status and by producer.

Pre-run amendment (2026-11-08, before any EVAL-3 output existed; EVAL-3-PROTOCOL.md §4):
  M4 status view       the M4 above reads the registry's `blocking` flag, which a producer may set to false
                       for a closure that `harness status` refuses (every closure is refused when its closing
                       answer is simulated). `M4_status` counts what status counts: open blocking questions of
                       the gate-1 producers after status's own closure and answer checks, classed as above.
                       It is the pass-bar M4. `M4_status_if_engineer` repeats it on a temporary copy of the
                       work folder whose simulated answers are relabelled engineer: a diagnostic only, to show
                       what the closures would do with real engineer answers. The registry-based M4 stays,
                       as `M4_gate1_blockers`, for comparison with the eval-2 dry run.
  Criterion-5 share    (second amendment, 2026-11-09, still before any EVAL-3 output) review fix F3 made
                       `harness status` count only engineer answers for the gate-1 producers, so `M4_status`
                       keeps every question the simulator answered open and lowers the procedural share.
                       `M4_criterion5_share` is the larger of the two shares (`M4_status`,
                       `M4_status_if_engineer`; None counts as 0): the stricter number decides criterion 5.
  M6 unasked_blocked   blocked text no question names: entries blocked by the legacy-font gate whose file
                       has no live (non-obsolete) registry question with a code covering the block reason
                       (frozen map M6_COVERING_CODES; computed from text index + registry, not from a reader).
                       Per file and total; criterion 8 needs total 0.
  M3 background        `--background-repo` points the background vocabulary at the repo copy whose skills
                       were under test (rev 5), instead of this script's own repo.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from tekla_harness.encoding import convert_legacy
from tekla_harness.text_gate import meaning_block_reason

# M4 classification, fixed before the run. Content = the answer changes what is modelled or where.
CONTENT_CODES = frozenset(
    {
        # tool wave 3 codes, classified at EVAL-5 pre-registration (names fixed in wave3/DESIGN.md)
        "grid_system_missing",
        "grid_answer_contradicts_drawing",
        "sheet_number_gap",
        "callout_unparsed",
        "legacy_ascii_text",
        "units_confirm",
        "units_confirm_all",
        "units_conflict",
        "units_suspect",
        "units_unknown",
        "units_answer_contradicts_evidence",
        "grid_units_doubt",
        "grid_system_units_unconfirmed",
        "grid_axis_label_conflict",
        "grid_axis_not_parallel",
        "grid_axis_skewed",
        "grid_axis_unlabelled",
        "grid_dimension_override_mismatch",
        "grid_family_axis_assignment",
        "grid_label_duplicate",
        "grid_label_kind_mixed",
        "grid_label_missing",
        "grid_label_order_mismatch",
        "grid_label_order_nonmonotonic",
        "grid_label_sequence_gap",
        "grid_non_orthogonal",
        "grid_none_found",
        "grid_rotated",
        "grid_scale_differs",
        "grid_spacing_cross_sheet_mismatch",
        "grid_spacing_drafting_tolerance",
        "grid_system_axis_unassigned",
        "grid_system_conflict",
        "grid_system_select",
        "grid_two_bubble_axis",
        "level_datum_not_found",
        "level_decimals_nonstandard",
        "level_finished_vs_structural",
        "level_name_conflict",
        "level_negative_storey",
        "level_none_found",
        "level_single_occurrence",
        "level_storey_selection",
        "level_value_out_of_range",
        "mark_notation_equivalence",
        "mark_size_conflict",
        "member_mark_prefix_meaning",
        "callout_ambiguous",
        "schedule_table_unparsed",
        "grade_legacy_mapping",
        "dimension_override_differs",
        "file_set_relation",
        "reader",
        "grid_axis_layer_mismatch",
        "reader_scope_drawings_missing",
        "reader_level_storey_selection",
        "reader_answer_contradicts_drawing",
        "reader_grid_extent",
        "reader_file_set_relation",
        "reader_general_notes_missing",
    }
)
PROCEDURAL_CODES = frozenset(
    {
        "grid_gate1_confirmation",
        "sheet_number_missing",
        "sheet_number_duplicate",
        "revision_missing",
        "title_field_conflict",
        "texts_unassigned",
        "texts_ambiguous_sheet",
        "sheet_frame_ambiguous",
        "sheet_frame_candidates_rejected",
        "sheet_frames_overlap",
        "sheet_content_duplicate",
        "sheets_not_detected",
        "converter_errors",
        "conversion_empty",
        "read_failed",
        "probe_section_failed",
        "unreadable_objects",
        "no_reader_implemented",
        "multiple_scales",
        "xref_unresolved",
        "font_encoding_proposed",
        "font_encoding_conflict",
        "encoding_unknown_non_ascii",
        "text_encoding_hint",
        "reader_drawing_list_missing",
        "reader_sheet_class_blocked",
    }
)
# Background vocabulary for M3: phrases the agents are taught by the harness itself (skills, Vietnamese
# question copy, conventions research). A phrase found there is not evidence of reading blocked text.
BACKGROUND = (
    ".claude/skills",
    "src/tekla_harness/questions_md_vi.py",
    "docs/research/vn-structural-drawing-conventions.md",
)

ENTRY_ID = re.compile(r"^T\d{6}$")
WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _non_ascii(text: str | None) -> bool:
    return any(ord(c) > 127 for c in text or "")


def _norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def text_indexes(work: Path) -> dict[str, dict[str, Any]]:
    """Drawing file (relative path as in `work/text/<rel>.json`) -> text index document."""
    root = work / "text"
    return {str(p.relative_to(root))[: -len(".json")]: _load(p) for p in sorted(root.rglob("*.json"))}


def m1_blocked_share(indexes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for rel, doc in indexes.items():
        non_ascii = [e for e in doc["entries"] if _non_ascii(e.get("raw_text"))]
        blocked = [e for e in non_ascii if meaning_block_reason(e)]
        ascii_blocked = sum(
            1 for e in doc["entries"] if not _non_ascii(e.get("raw_text")) and meaning_block_reason(e)
        )
        out[rel] = {
            "entries": len(doc["entries"]),
            "non_ascii": len(non_ascii),
            "non_ascii_blocked": len(blocked),
            "blocked_share": round(len(blocked) / len(non_ascii), 4) if non_ascii else None,
            "by_reason": dict(Counter(meaning_block_reason(e) for e in blocked)),
            "ascii_blocked": ascii_blocked,
        }
    return out


def _blocked_ids(indexes: dict[str, dict[str, Any]]) -> dict[str, set[str]]:
    return {rel: {e["id"] for e in doc["entries"] if meaning_block_reason(e)} for rel, doc in indexes.items()}


def _cited_ids(node: Any, file: str | None, sink: list[tuple[str | None, str, str]], path: str) -> None:
    """Collect (file, entry id, json path) outside any key that starts with 'blocked'."""
    if isinstance(node, dict):
        here = node.get("file") if isinstance(node.get("file"), str) else file
        for key, value in node.items():
            if key.startswith("blocked"):
                continue
            if isinstance(value, str) and ENTRY_ID.match(value):
                sink.append((here, value, f"{path}.{key}"))
            else:
                _cited_ids(value, here, sink, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            if isinstance(value, str) and ENTRY_ID.match(value):
                sink.append((file, value, f"{path}[{i}]"))
            else:
                _cited_ids(value, file, sink, f"{path}[{i}]")


def _match_file(file: str | None, files: list[str]) -> str | None:
    if file is None:
        return files[0] if len(files) == 1 else None
    stem = file.rsplit(".", 1)[0]
    hits = [f for f in files if f == file or f.rsplit(".", 1)[0] == stem]
    return hits[0] if len(hits) == 1 else None


def m2_producer_values(work: Path, indexes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    blocked = _blocked_ids(indexes)
    files = sorted(indexes)
    sources: list[tuple[Path, str | None]] = []
    for name in ("callouts.json", "marks.json"):
        if (work / name).exists():
            sources.append((work / name, None))
    structure = work / "structure"
    if structure.exists():
        for p in sorted(structure.rglob("*.json")):
            kind = p.name.split(".")[-2] if p.name.count(".") >= 2 else ""
            if kind in {"levels", "grids"}:
                rel = str(p.relative_to(structure))[: -len(f".{kind}.json")]
                sources.append((p, rel))
    hits: list[dict[str, str]] = []
    unresolved = 0
    for path, rel in sources:
        sink: list[tuple[str | None, str, str]] = []
        _cited_ids(_load(path), rel, sink, "$")
        for file, eid, where in sink:
            target = _match_file(file, files)
            if target is None:
                unresolved += 1
                continue
            if eid in blocked.get(target, set()):
                hits.append(
                    {"source": str(path.relative_to(work)), "file": target, "entry_id": eid, "at": where}
                )
    return {"count": len(hits), "hits": hits[:200], "unresolved_citations": unresolved}


def _decodings(raw: str) -> list[str]:
    out = []
    for enc in ("tcvn3", "vni"):
        try:
            out.append(convert_legacy(raw, enc).text)  # type: ignore[arg-type]
        except ValueError:
            continue
    return out


def _phrases(text: str) -> set[str]:
    words = WORD.findall(_norm(text))
    return {
        f"{a} {b} {c}"
        for a, b, c in zip(words, words[1:], words[2:], strict=False)
        if sum(_non_ascii(w) for w in (a, b, c)) >= 2
    }


def _background(repo: Path) -> str:
    parts = []
    for name in BACKGROUND:
        path = repo / name
        files = sorted(path.rglob("*.md")) if path.is_dir() else [path]
        parts += [" ".join(WORD.findall(_norm(f.read_text(encoding="utf-8")))) for f in files if f.exists()]
    return " \n ".join(parts)


def m3_prose_leaks(indexes: dict[str, dict[str, Any]], prose: dict[str, str], repo: Path) -> dict[str, Any]:
    allowed_text = " \n ".join(
        " ".join(WORD.findall(_norm(e.get("display_text") or "")))
        for doc in indexes.values()
        for e in doc["entries"]
        if not meaning_block_reason(e)
    )
    allowed_text += " \n " + _background(repo)
    candidates: dict[str, set[str]] = defaultdict(set)
    for rel, doc in indexes.items():
        for e in doc["entries"]:
            if meaning_block_reason(e) and _non_ascii(e.get("raw_text")):
                for decoded in _decodings(e.get("display_text") or e["raw_text"]):
                    for phrase in _phrases(decoded):
                        if phrase not in allowed_text:
                            candidates[phrase].add(f"{rel}#{e['id']}")
    leaks = []
    for name, body in prose.items():
        norm_lines = [" ".join(WORD.findall(_norm(line))) for line in body.splitlines()]
        for phrase, sources in sorted(candidates.items()):
            for lineno, line in enumerate(norm_lines, 1):
                if phrase in line:
                    leaks.append({"doc": name, "line": lineno, "phrase": phrase, "from": sorted(sources)[:5]})
    return {"candidate_count": len(leaks), "candidates": leaks[:300]}


def m4_m5_questions(work: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    path = work / "question-registry.json"
    if not path.exists():
        return {"error": "no question-registry.json"}, {"error": "no question-registry.json"}
    questions = list(_load(path)["questions"].values())
    open_blocking = [q for q in questions if q.get("status") == "open" and q.get("blocking")]
    classes: dict[str, list[str]] = {"content": [], "procedural": [], "unclassified": []}
    for q in open_blocking:
        code = q["code"]
        cls = (
            "content"
            if code in CONTENT_CODES
            else "procedural"
            if code in PROCEDURAL_CODES
            else "unclassified"
        )
        classes[cls].append(f"{q['id']}:{code}")
    total = len(open_blocking)
    procedural = len(classes["procedural"]) + len(classes["unclassified"])
    m4 = {
        "open_blocking": total,
        "procedural_share": round(procedural / total, 4) if total else None,
        **{k: {"count": len(v), "ids": v} for k, v in classes.items()},
    }
    m5 = {
        "total": len(questions),
        "by_status": dict(Counter(q.get("status") for q in questions)),
        "by_producer": dict(Counter(q.get("producer") for q in questions)),
        "by_code": dict(Counter(q["code"] for q in questions).most_common()),
    }
    return m4, m5


def _classify(codes: list[tuple[str, str]]) -> dict[str, Any]:
    classes: dict[str, list[str]] = {"content": [], "procedural": [], "unclassified": []}
    for qid, code in codes:
        cls = (
            "content"
            if code in CONTENT_CODES
            else "procedural"
            if code in PROCEDURAL_CODES
            else "unclassified"
        )
        classes[cls].append(f"{qid}:{code}")
    total = len(codes)
    procedural = len(classes["procedural"]) + len(classes["unclassified"])
    return {
        "open_blocking": total,
        "procedural_share": round(procedural / total, 4) if total else None,
        **{k: {"count": len(v), "ids": v} for k, v in classes.items()},
    }


def m4_status_view(work: Path) -> dict[str, Any]:
    """Open blocking questions of the gate-1 producers as `harness status` counts them (all ids, no cap)."""
    from tekla_harness import status
    from tekla_harness.questions import active_answers, load_ledger

    inventory = _load(work / "inventory.json")
    ledger = load_ledger(work, inventory["project_id"], create=False)
    active = active_answers(ledger.answers)
    state = status.closure_state(work, ledger)
    closed = frozenset(state.accepted)
    by_id = {e["id"]: e["code"] for e in ledger.registry["questions"].values()}
    out: dict[str, Any] = {"by_producer": {}}
    gate: list[tuple[str, str]] = []
    labels = dict(status.PRODUCERS)
    for label in status.GATE_PRODUCERS:
        _counts, open_ids = status._question_counts(
            ledger.registry, active, labels[label], closed, state.forced
        )
        out["by_producer"][label] = len(open_ids)
        gate += [(qid, by_id[qid]) for qid in open_ids]
    out.update(_classify(gate))
    out["closures_accepted"] = len(state.accepted)
    out["closures_refused"] = len(state.reasons)
    return out


def m4_status_if_engineer(work: Path) -> dict[str, Any]:
    """Diagnostic: M4_status on a temporary copy whose simulated answers are relabelled engineer."""
    import shutil
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "work"
        shutil.copytree(work, copy, ignore=shutil.ignore_patterns("converted", "probe", ".harness.lock*"))
        answers_path = copy / "answers.json"
        if answers_path.exists():
            doc = _load(answers_path)
            for answer in doc.get("answers", []):
                if answer.get("answered_by_role") == "simulated":
                    answer["answered_by_role"] = "engineer"
            answers_path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return m4_status_view(copy)


# M6 frozen at pre-registration: which question codes name which block reason. A blocked entry counts as
# "named" when its file has a live (non-obsolete) registry question with a covering code. Computed from the
# text index and the registry only, never from a harness reader, so the tools under test cannot redefine it.
M6_COVERING_CODES: dict[str, frozenset[str]] = {
    **{
        reason: frozenset(
            {
                "font_encoding_proposed",
                "font_encoding_conflict",
                "text_encoding_hint",
                "encoding_unknown_non_ascii",
            }
        )
        for reason in (
            "encoding_unknown",
            "encoding_proposed",
            "encoding_contradiction",
            "knowledge_conflict",
        )
    },
    "legacy_ascii_suspect": frozenset({"legacy_ascii_text"}),
}


def m4_engineer_rerun(work: Path) -> dict[str, Any]:
    """Diagnostic for criterion 7: on a temporary copy with simulated answers relabelled engineer, rerun
    `harness grid-system`, then report the files that gained a grid system built from an answer
    (`source: engineer_answer`) and M4_status on that copy."""
    import shutil
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "work"
        shutil.copytree(work, copy, ignore=shutil.ignore_patterns("converted", "probe", ".harness.lock*"))
        answers_path = copy / "answers.json"
        if answers_path.exists():
            doc = _load(answers_path)
            for answer in doc.get("answers", []):
                if answer.get("answered_by_role") == "simulated":
                    answer["answered_by_role"] = "engineer"
            answers_path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        # converted DXFs are needed by grid-system: link them back in
        if (work / "converted").exists():
            (copy / "converted").symlink_to((work / "converted").resolve(), target_is_directory=True)
        run = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; from tekla_harness.cli import main; sys.exit(main(sys.argv[1:]))",
                "grid-system",
                str(copy),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        gs_path = copy / "grid-systems.json"
        engineer_files: list[str] = []
        if gs_path.exists():
            gs = _load(gs_path)
            for system in gs.get("systems", []):
                if system.get("source") == "engineer_answer":
                    # an answer-built system has no members: its file is in each direction's provenance
                    # (EVAL-5 under-reported it as [] because it read only `members`)
                    files = {m.get("file") for m in system.get("members", []) if m.get("file")}
                    files |= {
                        d.get("provenance", {}).get("file")
                        for d in system.get("directions", [])
                        if d.get("provenance", {}).get("file")
                    }
                    engineer_files.extend(sorted(files))
        view = m4_status_view(copy) if run.returncode in (0, 1) else None
        return {
            "grid_system_exit": run.returncode,
            "grid_system_stderr_tail": run.stderr.strip().splitlines()[-3:],
            "files_with_engineer_grid": sorted(set(engineer_files)),
            "M4_status_after_rerun": view,
        }


def m6_unasked_blocked(work: Path, indexes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Blocked entries whose file has no live question with a code that covers their block reason."""
    registry = _load(work / "question-registry.json")
    live: dict[str, set[str]] = {}
    for e in registry["questions"].values():
        if e.get("status") != "obsolete" and e.get("file"):
            live.setdefault(e["file"], set()).add(e["code"])
    out: dict[str, Any] = {"total": 0, "by_file": {}}
    for rel, doc in indexes.items():
        codes = live.get(rel, set())
        by_reason: dict[str, int] = {}
        for entry in doc["entries"]:
            reason = meaning_block_reason(entry)
            if reason is None:
                continue
            if not (M6_COVERING_CODES.get(reason, frozenset()) & codes):
                by_reason[reason] = by_reason.get(reason, 0) + 1
        n = sum(by_reason.values())
        out["by_file"][rel] = {"unasked_entries": n, "by_reason": by_reason}
        out["total"] += n
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--prose", nargs="*", default=None)
    parser.add_argument(
        "--background-repo",
        type=Path,
        default=Path(__file__).resolve().parents[4],
        help="repo whose skills were under test (M3 background vocabulary); default: this script's repo",
    )
    args = parser.parse_args(argv)
    project: Path = args.project_dir
    work = project / "work"
    if not (work / "text").is_dir():
        print(f"no work/text folder under {project}", file=sys.stderr)
        return 3
    names = args.prose if args.prose is not None else ["01-analysis.md", "02-plan.md"]
    prose = {n: (project / n).read_text(encoding="utf-8") for n in names if (project / n).exists()}
    missing = [n for n in names if n not in prose]
    indexes = text_indexes(work)
    m4, m5 = m4_m5_questions(work)
    doc = {
        "project": project.name,
        "prose_read": sorted(prose),
        "prose_missing": missing,
        "M1_blocked_share": m1_blocked_share(indexes),
        "M2_producer_values_from_blocked": m2_producer_values(work, indexes),
        "M3_prose_leak_candidates": m3_prose_leaks(indexes, prose, args.background_repo),
        "M3_background_repo": str(args.background_repo),
        "M4_gate1_blockers": m4,
        "M4_status": m4_status_view(work),
        "M4_status_if_engineer": m4_status_if_engineer(work),
        "M5_questions": m5,
        "M6_unasked_blocked": m6_unasked_blocked(work, indexes),
        "M4_engineer_rerun_diagnostic": m4_engineer_rerun(work),
    }
    doc["M4_criterion5_share"] = max(
        doc["M4_status"]["procedural_share"] or 0.0, doc["M4_status_if_engineer"]["procedural_share"] or 0.0
    )
    json.dump(doc, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
