"""`harness` command line.

Output contract (AGENTS.md): JSON on stdout, diagnostics on stderr.
Exit codes: 0 ok, 1 validation failure, 2 usage error, 3 environment error.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from tekla_harness import __version__, findings, marks, questions_md
from tekla_harness.answers import parse_values, record_answer
from tekla_harness.ask import ask_question, withdraw_question
from tekla_harness.cache import ReadCache
from tekla_harness.callouts import run_callouts
from tekla_harness.convert import DEFAULT_TIMEOUT_S, NoConverterError, dwg_to_dxf
from tekla_harness.detect import detect_file, iter_input_files
from tekla_harness.extract_text import extract_text
from tekla_harness.grid_system import GridSystemError, run_grid_systems
from tekla_harness.intake import IntakeError, run_intake
from tekla_harness.knowledge import KnowledgeError
from tekla_harness.questions import QuestionsError
from tekla_harness.read_dxf import CONVERTER_CAPS, probe_dxf
from tekla_harness.schemas import SCHEMA_NAMES, validate
from tekla_harness.sheet_text import (
    DEFAULT_MAX_ENTRIES,
    ReaderError,
    find_text,
    list_sheets,
    sheet_text,
    truncation_warning,
)
from tekla_harness.status import StatusError, build_status
from tekla_harness.structure import StructureError, read_structure, run_extractor
from tekla_harness.worklock import WorkLockError, work_lock

EXIT_OK, EXIT_INVALID, EXIT_USAGE, EXIT_ENV = 0, 1, 2, 3
# Commands that write a work folder hold its lock for their whole run (ADR-0011). intake takes it itself,
# inside run_intake, after its usage checks; `finding` locks only for add and withdraw.
LOCKED_COMMANDS = frozenset(
    {"read-structure", "callouts", "marks", "grid-system", "answer", "ask", "questions-md"}
)
LOCKED_ACTIONS = {"finding": frozenset({"add", "withdraw"})}
_ENV_HOOK = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "session_env_check.py"


def _cmd_validate(args: argparse.Namespace) -> int:
    results = []
    for path in args.files:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            results.append({"file": path, "valid": False, "errors": [{"path": "", "message": str(exc)}]})
            continue
        problems = validate(args.schema, data)
        results.append({"file": path, "valid": not problems, "errors": [p.as_dict() for p in problems]})
    print(json.dumps({"schema": args.schema, "results": results}, ensure_ascii=False, indent=2))
    return EXIT_OK if all(r["valid"] for r in results) else EXIT_INVALID


def _cmd_env_check(_: argparse.Namespace) -> int:
    if not _ENV_HOOK.is_file():
        print(f"environment check script not found: {_ENV_HOOK}", file=sys.stderr)
        return EXIT_ENV
    spec = importlib.util.spec_from_file_location("session_env_check", _ENV_HOOK)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    lines = module.report()
    ok = "No blocking problems." in lines
    print(json.dumps({"ok": ok, "report": lines}, ensure_ascii=False, indent=2))
    return EXIT_OK if ok else EXIT_ENV


def _cmd_detect(args: argparse.Namespace) -> int:
    files, errors = [], []
    for path in iter_input_files(Path(p) for p in args.paths):
        try:
            files.append(detect_file(path))
        except OSError as exc:
            errors.append({"path": str(path), "message": str(exc)})
    print(json.dumps({"files": files, "errors": errors}, ensure_ascii=False, indent=2))
    return EXIT_INVALID if errors else EXIT_OK


def _cmd_dwg2dxf(args: argparse.Namespace) -> int:
    if args.refresh and not args.cache_dir:
        print("--refresh needs --cache-dir", file=sys.stderr)
        return EXIT_USAGE
    try:
        result = dwg_to_dxf(
            Path(args.dwg),
            Path(args.out_dir),
            oda=[args.oda] if args.oda else None,
            dwg2dxf=[args.dwg2dxf] if args.dwg2dxf else None,
            timeout=args.timeout,
            cache=ReadCache(Path(args.cache_dir)) if args.cache_dir else None,
            refresh=args.refresh,
        )
    except NoConverterError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ENV
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    except OSError as exc:  # e.g. a refresh that cannot delete a locked entry
        print(str(exc), file=sys.stderr)
        return EXIT_ENV
    out = {
        "dwg": str(result.dwg),
        "dxf": str(result.dxf) if result.dxf else None,
        "converter": result.converter,
        "confidence_cap": result.confidence_cap,
        "attempts": [a.as_dict() for a in result.attempts],
        "warnings": result.warnings,
        "stderr_error_lines": result.stderr_error_lines,
        "stderr_warning_lines": result.stderr_warning_lines,
        "stderr_tail": result.stderr_tail,
        "cache": result.cache,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return EXIT_OK if result.dxf else EXIT_INVALID


def _cmd_read_dxf(args: argparse.Namespace) -> int:
    path = Path(args.dxf)
    if not path.is_file():
        print(f"not a file: {path}", file=sys.stderr)
        return EXIT_USAGE
    try:
        result = probe_dxf(path, converter=args.converter)
    except OSError as exc:
        print(f"cannot read {path}: {exc}", file=sys.stderr)
        return EXIT_ENV
    except KnowledgeError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    problems = validate("dxf-probe", result)
    if problems:  # a bug in the probe, not in the drawing: never print an invalid document
        for p in problems:
            print(f"probe output invalid at {p.path or '/'}: {p.message}", file=sys.stderr)
        return EXIT_INVALID
    try:
        text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    except ValueError as exc:  # NaN / Infinity is not JSON: a probe bug, never print it
        print(f"probe output contains a non-finite number: {exc}", file=sys.stderr)
        return EXIT_INVALID
    print(text)
    if result["status"] == "unreadable":
        print(f"{path}: ezdxf could not open the file: {result['error']}", file=sys.stderr)
        return EXIT_INVALID
    if result["status"] == "partial":
        for e in result["section_errors"]:
            print(f"{path}: status partial, section {e['section']}: {e['error']}", file=sys.stderr)
    return EXIT_OK


def _cmd_extract_text(args: argparse.Namespace) -> int:
    path, out = Path(args.dxf), Path(args.out)
    if not path.is_file():
        print(f"not a file: {path}", file=sys.stderr)
        return EXIT_USAGE
    try:
        result = extract_text(path, converter=args.converter)
    except OSError as exc:
        print(f"cannot read {path}: {exc}", file=sys.stderr)
        return EXIT_ENV
    except KnowledgeError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    problems = validate("text-index", result)
    if problems:  # a bug in the extractor, not in the drawing: never write an invalid document
        for p in problems:
            print(f"text index invalid at {p.path or '/'}: {p.message}", file=sys.stderr)
        return EXIT_INVALID
    try:
        text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    except ValueError as exc:  # NaN / Infinity is not JSON: an extractor bug, never write it
        print(f"text index contains a non-finite number: {exc}", file=sys.stderr)
        return EXIT_INVALID
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"cannot write {out}: {exc}", file=sys.stderr)
        return EXIT_ENV
    summary = result.get("summary")
    print(
        json.dumps(
            {
                "file": str(path),
                "out": str(out),
                "status": result["status"],
                "entries": summary["total_entries"] if summary else 0,
                "by_encoding_used": summary["by_encoding_used"] if summary else {},
                "by_confidence": summary["by_confidence"] if summary else {},
                "errors_total": summary["errors_total"] if summary else 0,
                "warnings": result.get("warnings", []),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if result["status"] == "unreadable":
        print(f"{path}: ezdxf could not open the file: {result['error']}", file=sys.stderr)
        return EXIT_INVALID
    if result["status"] == "partial" and summary:
        for e in summary["errors"][:10]:
            print(f"{path}: status partial, {e['entity_type']}: {e['error']}", file=sys.stderr)
    return EXIT_OK


def _cmd_intake(args: argparse.Namespace) -> int:
    try:
        result = run_intake(
            Path(args.input_dir),
            Path(args.out),
            args.project_id,
            oda=[args.oda] if args.oda else None,
            dwg2dxf=[args.dwg2dxf] if args.dwg2dxf else None,
            timeout=args.timeout,
        )
    except IntakeError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    print(json.dumps(result.summary, ensure_ascii=False, indent=2))
    for rel in result.summary["read_failures"]:
        print(f"{rel}: could not be read (see read-log.json)", file=sys.stderr)
    return result.exit_code


def _cmd_extract_structure(args: argparse.Namespace) -> int:
    kind = args.command.removeprefix("extract-")
    sheets = Path(args.sheets) if kind != "sheets" else None
    try:
        summary = run_extractor(kind, Path(args.dxf), Path(args.text_index), Path(args.out), sheets)
    except StructureError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return EXIT_OK


def _cmd_read_structure(args: argparse.Namespace) -> int:
    try:
        result = read_structure(Path(args.work_dir), Path(args.input_dir) if args.input_dir else None)
    except StructureError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    print(json.dumps(result.summary, ensure_ascii=False, indent=2))
    for item in result.summary["skipped_files"]:
        print(f"{item['path']}: skipped: {item['reason']}", file=sys.stderr)
    return result.exit_code


def _cmd_list_sheets(args: argparse.Namespace) -> int:
    try:
        doc = list_sheets(Path(args.work_dir))
    except ReaderError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    print(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False))
    return EXIT_OK


def _cmd_sheet_text(args: argparse.Namespace) -> int:
    try:
        doc = sheet_text(
            Path(args.work_dir), args.file, args.sheet_id, contains=args.contains, max_entries=args.max
        )
    except ReaderError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    warning = truncation_warning(doc)
    if warning:
        print(warning, file=sys.stderr)
    print(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False))
    return EXIT_OK


def _cmd_find_text(args: argparse.Namespace) -> int:
    try:
        doc = find_text(Path(args.work_dir), args.contains, file_rel=args.file, max_hits=args.max)
    except ReaderError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    counts = doc["counts"]
    if counts["truncated"]:
        print(
            f"find-text truncated: {counts['returned']} of {counts['hits']} hits returned; "
            f"rerun with --max {counts['hits']} (or without --max) to get all of them",
            file=sys.stderr,
        )
    if counts["blocked_entries_not_searchable"]:
        print(
            f"find-text: {counts['blocked_entries_not_searchable']} blocked (legacy-font) entries were "
            "matched on their stored text only: the search is incomplete over them",
            file=sys.stderr,
        )
    print(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False))
    return EXIT_OK


def _cmd_callouts(args: argparse.Namespace) -> int:
    try:
        result = run_callouts(Path(args.work_dir), Path(args.input_dir) if args.input_dir else None)
    except ReaderError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    print(json.dumps(result.summary, ensure_ascii=False, indent=2))
    return result.exit_code


def _cmd_grid_system(args: argparse.Namespace) -> int:
    try:
        result = run_grid_systems(Path(args.work_dir), svg=not args.no_svg)
    except GridSystemError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    print(json.dumps(result.summary, ensure_ascii=False, indent=2))
    return result.exit_code


def _cmd_status(args: argparse.Namespace) -> int:
    try:
        doc = build_status(Path(args.work_dir))
    except StatusError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    print(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False))
    return EXIT_OK


def _cmd_answer(args: argparse.Namespace) -> int:
    try:
        result = record_answer(
            Path(args.work_dir), args.question_id, args.text, args.by, parse_values(args.value)
        )
    except QuestionsError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    print(json.dumps(result, ensure_ascii=False, indent=2))
    for item in result["not_refreshed"]:
        print(f"{item['file']}: not refreshed: {item['reason']}", file=sys.stderr)
    return EXIT_OK


def _cmd_ask(args: argparse.Namespace) -> int:
    try:
        if args.withdraw is not None:
            extra = [
                f"--{name}"
                for name in ("code", "file", "sheet", "where", "found", "text")
                if getattr(args, name) is not None
            ] + (["--blocking"] if args.blocking else [])
            if extra or args.reason is None:
                raise QuestionsError(
                    2, "--withdraw takes only --reason" + (f" (got {', '.join(extra)})" if extra else "")
                )
            result = withdraw_question(Path(args.work_dir), args.withdraw, args.reason)
        else:
            missing = [
                f"--{name}" for name in ("code", "where", "found", "text") if getattr(args, name) is None
            ]
            if missing or args.reason is not None:
                raise QuestionsError(
                    2,
                    f"missing {', '.join(missing)}" if missing else "--reason goes with --withdraw only",
                )
            result = ask_question(
                Path(args.work_dir),
                code=args.code,
                where=args.where,
                found=args.found,
                text=args.text,
                file=args.file,
                sheet=args.sheet,
                blocking=args.blocking,
            )
    except QuestionsError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    if result["status"] == "already_asked":
        print(f"{result['id']}: already asked", file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harness", description="Tekla AI Harness tooling")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate", help="validate JSON files against a schema")
    p_val.add_argument("schema", choices=[n for n in SCHEMA_NAMES if n != "common"])
    p_val.add_argument("files", nargs="+")
    p_val.set_defaults(func=_cmd_validate)

    p_det = sub.add_parser("detect", help="identify input file formats from their bytes and hash them")
    p_det.add_argument("paths", nargs="+", help="files or folders (walked recursively)")
    p_det.set_defaults(func=_cmd_detect)

    p_dwg = sub.add_parser("dwg2dxf", help="convert one DWG to DXF: ODA, then LibreDWG (ADR-0005)")
    p_dwg.add_argument("dwg")
    p_dwg.add_argument("--out-dir", required=True, help="must not be inside the input folder")
    p_dwg.add_argument("--oda", help="ODAFileConverter executable (default: $HARNESS_ODA_CONVERTER, PATH)")
    p_dwg.add_argument("--dwg2dxf", help="LibreDWG dwg2dxf executable (default: $HARNESS_DWG2DXF, PATH)")
    p_dwg.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S, help="seconds per converter")
    p_dwg.add_argument(
        "--cache-dir",
        help="project read cache (ADR-0008), e.g. projects/<id>/.cache; no cache when omitted",
    )
    p_dwg.add_argument("--refresh", action="store_true", help="ignore a cached result, recompute, overwrite")
    p_dwg.set_defaults(func=_cmd_dwg2dxf)

    p_dxf = sub.add_parser("read-dxf", help="probe one DXF: units, layouts, layers, xrefs, dimension audit")
    p_dxf.add_argument("dxf")
    p_dxf.add_argument(
        "--converter",
        choices=list(CONVERTER_CAPS),
        default="none",
        help="tool that produced this DXF from a DWG (sets the confidence cap, ADR-0005); default none",
    )
    p_dxf.set_defaults(func=_cmd_read_dxf)

    p_txt = sub.add_parser(
        "extract-text",
        help="index every text of one DXF (TEXT, MTEXT, ATTRIB, MULTILEADER, dimension overrides) as JSON",
    )
    p_txt.add_argument("dxf")
    p_txt.add_argument("--out", required=True, help="the full text-index JSON is written here")
    p_txt.add_argument(
        "--converter",
        choices=list(CONVERTER_CAPS),
        default="none",
        help="tool that produced this DXF from a DWG (sets the confidence cap, ADR-0005); default none",
    )
    p_txt.set_defaults(func=_cmd_extract_text)

    p_int = sub.add_parser(
        "intake",
        help="detect, convert and probe a whole input folder: read-log.json, inventory.json, questions.json",
    )
    p_int.add_argument("input_dir", help="read-only; the work folder must not be inside it")
    p_int.add_argument("--out", required=True, help="work folder for the outputs")
    p_int.add_argument("--project-id", required=True, help="a-z, 0-9 and '-', e.g. demo-warehouse")
    p_int.add_argument("--oda", help="ODAFileConverter executable (default: $HARNESS_ODA_CONVERTER, PATH)")
    p_int.add_argument("--dwg2dxf", help="LibreDWG dwg2dxf executable (default: $HARNESS_DWG2DXF, PATH)")
    p_int.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S, help="seconds per converter")
    p_int.set_defaults(func=_cmd_intake)

    for kind, what in (
        ("sheets", "split one DXF into sheets and read title-block candidates"),
        ("grids", "find the grid axes of one DXF and propose Tekla coordinate strings"),
        ("levels", "list the level (elevation) candidates of one DXF"),
    ):
        p_ext = sub.add_parser(f"extract-{kind}", help=what)
        p_ext.add_argument("dxf")
        p_ext.add_argument(
            "--text-index", required=True, help="text index of this very DXF (harness extract-text / intake)"
        )
        if kind != "sheets":
            p_ext.add_argument(
                "--sheets", required=True, help="sheets.json of this very DXF (extract-sheets)"
            )
        p_ext.add_argument("--out", required=True, help="the full result JSON is written here")
        p_ext.set_defaults(func=_cmd_extract_structure)

    p_str = sub.add_parser(
        "read-structure",
        help="sheets, grids and levels of every DXF that intake probed: structure/, structure-questions.json",
    )
    p_str.add_argument("work_dir", help="the --out folder of a previous `harness intake` run")
    p_str.add_argument(
        "--input-dir", help="the input folder of that intake run (needed when it holds native DXF files)"
    )
    p_str.set_defaults(func=_cmd_read_structure)

    p_ls = sub.add_parser(
        "list-sheets",
        help="every sheet of every drawing of a work folder: detector id, printed number, frame, text count",
    )
    p_ls.add_argument(
        "work_dir", help="the --out folder of `harness intake` (after `harness read-structure`)"
    )
    p_ls.set_defaults(func=_cmd_list_sheets)

    p_st = sub.add_parser(
        "sheet-text", help="the text of ONE sheet in reading order (stdout is the JSON); see list-sheets"
    )
    p_st.add_argument("work_dir")
    p_st.add_argument("file", help="input-relative path of the drawing, as in inventory.json")
    p_st.add_argument("sheet_id", help="detector sheet id from list-sheets, e.g. model#01")
    p_st.add_argument("--contains", help="keep only entries whose text contains this (NFC, case-insensitive)")
    p_st.add_argument(
        "--max",
        type=int,
        default=None,
        help=f"entries returned at most (default {DEFAULT_MAX_ENTRIES}; unbounded with --contains)",
    )
    p_st.set_defaults(func=_cmd_sheet_text)

    p_ft = sub.add_parser(
        "find-text",
        help="search every sheet of every drawing (or one) for a text: hits with file, sheet, entry id",
    )
    p_ft.add_argument(
        "work_dir", help="the --out folder of `harness intake` (after `harness read-structure`)"
    )
    p_ft.add_argument(
        "--contains", required=True, help="substring to find (NFC, case-insensitive, diacritics significant)"
    )
    p_ft.add_argument("--file", help="search only this drawing (input-relative path, as in inventory.json)")
    p_ft.add_argument("--max", type=int, default=None, help="hits returned at most (default: all)")
    p_ft.set_defaults(func=_cmd_find_text)

    p_cal = sub.add_parser(
        "callouts",
        help="rebar, steel, plate, bolt and member-mark candidates: callouts.json, callouts-questions.json",
    )
    p_cal.add_argument(
        "work_dir", help="the --out folder of `harness intake` (after `harness read-structure`)"
    )
    p_cal.add_argument(
        "--input-dir",
        help="the intake input folder: its DXF/DWG files must still match inventory.json (sha256)",
    )
    p_cal.set_defaults(func=_cmd_callouts)

    p_gs = sub.add_parser(
        "grid-system",
        help="project grid systems (gate 1 proposal): grid-systems.json, grid-system-questions.json, SVGs",
    )
    p_gs.add_argument(
        "work_dir", help="the --out folder of `harness intake` (after `harness read-structure`)"
    )
    p_gs.add_argument(
        "--no-svg",
        action="store_true",
        help="do not draw structure/grid-systems/*.svg (old drawings are removed)",
    )
    p_gs.set_defaults(func=_cmd_grid_system)

    p_sta = sub.add_parser(
        "status",
        help="questions, stale answers, output freshness per producer, and gate 1 readiness (read-only)",
    )
    p_sta.add_argument("work_dir", help="the --out folder of `harness intake`")
    p_sta.set_defaults(func=_cmd_status)

    p_ans = sub.add_parser(
        "answer",
        help="record the ENGINEER's answer to a question (run by the engineer or on their instruction)",
        description=(
            "Record an engineer's answer to a question of a work folder, bound to the question's stable "
            "key. This command is meant to be run by the engineer, or on the engineer's explicit "
            "instruction with the engineer's own words. An agent must never invent or paraphrase an "
            "answer. A second answer to the same question supersedes the first. Structured values "
            "(--value): units_confirm_all (the one blocking units question per file) and the units "
            "evidence codes need unit=mm|cm|m|in|ft; units_answer_contradicts_evidence takes unit= equal to "
            "the unit already answered (to confirm it; else re-answer units_confirm_all); "
            "grid_system_axis_unassigned takes one value per direction named in the question, "
            "dir1=X|Y and dir2=X|Y, distinct; grid_family_axis_assignment takes <family_id>=X|Y; "
            "member_mark_prefix_meaning takes <prefix>=<meaning>; grid_system_select takes optional "
            "systems=S001,S002 (the systems the project uses) and separate=S001,S002 (selected systems "
            "that are different buildings, which closes their conflict); grid_system_conflict cannot be "
            "answered: answer grid_system_select instead; every other question takes no value. Rerun "
            "harness grid-system after a units, select or axis answer. A question whose file changed since "
            "it was raised is refused: rerun the command that raised it. Exit codes: 1 invalid values or "
            "changed file, 2 unknown or obsolete question, blank text or name."
        ),
    )
    p_ans.add_argument("work_dir", help="the --out folder of `harness intake`")
    p_ans.add_argument("question_id", help="e.g. Q-003, from a questions document")
    p_ans.add_argument("--text", required=True, help="the engineer's answer, verbatim")
    p_ans.add_argument("--by", required=True, help="who answered")
    p_ans.add_argument(
        "--value", action="append", default=[], metavar="K=V", help="structured value, repeatable (see above)"
    )
    p_ans.set_defaults(func=_cmd_answer)

    p_ask = sub.add_parser(
        "ask",
        help="raise (or withdraw) a drawing-reader question through the registry; prints its id",
        description=(
            "The drawing-reader agent raises a question here instead of inventing an id. One question per "
            "(code, blocking, file, where): asking the same place again prints the same id (already_asked). "
            "--file is an inventory path (omit it for a project-level question); --code is your own "
            "lowercase snake_case code (not one a producer owns, exit 2); --text is the question in "
            "Vietnamese, printed verbatim in questions.md. "
            "--withdraw Q-id --reason '...' retires a reader question. Questions go to "
            "reader-questions.json; answer them with `harness answer`. Exit codes: 1 file not in the "
            "inventory or invalid documents, 2 usage or a code owned by a producer."
        ),
    )
    p_ask.add_argument("work_dir", help="the --out folder of `harness intake`")
    p_ask.add_argument("--code", help="the question's own code, lowercase snake_case")
    p_ask.add_argument("--file", help="input-relative path as listed in inventory.json; omit for the project")
    p_ask.add_argument("--sheet", help="the detector sheet id (model#01, <layout>#01)")
    p_ask.add_argument("--where", help="where in the drawing; one question per distinct value")
    p_ask.add_argument("--found", help="what was found there (may be empty)")
    p_ask.add_argument("--text", help="the question, in Vietnamese (printed verbatim in questions.md)")
    p_ask.add_argument("--blocking", action="store_true", help="the question blocks gate 1 until answered")
    p_ask.add_argument("--withdraw", metavar="Q-ID", help="retire this reader question (needs --reason)")
    p_ask.add_argument("--reason", help="why the question is withdrawn")
    p_ask.set_defaults(func=_cmd_ask)

    # Commands whose module owns its arguments and its run (add_arguments / run / COMMAND / HELP).
    for module in (marks, questions_md, findings):
        p_mod = sub.add_parser(module.COMMAND, help=module.HELP)
        module.add_arguments(p_mod)
        p_mod.set_defaults(func=module.run)

    p_env = sub.add_parser("env-check", help="report whether this machine can run the harness")
    p_env.set_defaults(func=_cmd_env_check)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse exits 2 on usage errors, 0 on --help/--version
        return int(exc.code or 0)
    try:
        target = _lock_target(args)
        if target is None:
            return args.func(args)
        command = " ".join([args.command, *([args.action] if args.command in LOCKED_ACTIONS else [])])
        with work_lock(target, command):
            return args.func(args)
    except WorkLockError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code


def _lock_target(args: argparse.Namespace) -> Path | None:
    """The work folder this command must lock; None for a read-only command, or when the folder does not
    exist (the command then writes nothing and reports its own usage error)."""
    action = getattr(args, "action", None)
    if args.command not in LOCKED_COMMANDS and action not in LOCKED_ACTIONS.get(args.command, ()):
        return None
    work = Path(args.work_dir)
    return work if work.is_dir() else None


if __name__ == "__main__":
    sys.exit(main())
