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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harness", description="Tekla AI Harness tooling")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate", help="validate JSON files against a schema")
    p_val.add_argument("schema", choices=[n for n in SCHEMA_NAMES if n != "common"])
    p_val.add_argument("files", nargs="+")
    p_val.set_defaults(func=_cmd_validate)

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
