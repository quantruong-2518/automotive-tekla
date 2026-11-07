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

from tekla_harness import __version__
from tekla_harness.cache import ReadCache
from tekla_harness.convert import DEFAULT_TIMEOUT_S, NoConverterError, dwg_to_dxf
from tekla_harness.detect import detect_file, iter_input_files
from tekla_harness.schemas import SCHEMA_NAMES, validate

EXIT_OK, EXIT_INVALID, EXIT_USAGE, EXIT_ENV = 0, 1, 2, 3
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
    out = {
        "dwg": str(result.dwg),
        "dxf": str(result.dxf) if result.dxf else None,
        "converter": result.converter,
        "confidence_cap": result.confidence_cap,
        "attempts": [a.as_dict() for a in result.attempts],
        "warnings": result.warnings,
        "cache": result.cache,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return EXIT_OK if result.dxf else EXIT_INVALID


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
        help="project read cache (ADR-0007), e.g. projects/<id>/.cache; no cache when omitted",
    )
    p_dwg.add_argument("--refresh", action="store_true", help="ignore a cached result, recompute, overwrite")
    p_dwg.set_defaults(func=_cmd_dwg2dxf)

    p_env = sub.add_parser("env-check", help="report whether this machine can run the harness")
    p_env.set_defaults(func=_cmd_env_check)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse exits 2 on usage errors, 0 on --help/--version
        return int(exc.code or 0)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
