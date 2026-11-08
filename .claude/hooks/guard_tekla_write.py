#!/usr/bin/env python3
"""PreToolUse guard: only the `builder` subagent may run tekla-cli write commands.

Reads the Claude Code hook payload on stdin. For Bash/PowerShell calls it finds every
`tekla-cli` invocation in the command. Any subcommand outside READ_SUBCOMMANDS is a
write (fail closed). A write from any agent other than `builder` is denied.

Exit 0 with no output  -> no decision; the normal permission flow applies.
Exit 0 with JSON deny  -> the tool call is blocked and the reason is shown to Claude.
Exit 2                 -> blocking error. Any crash (bad stdin, unexpected payload) exits 2,
                          so the guard fails closed by itself and does not depend on a
                          settings field. A non-zero exit other than 2 would NOT block.
Stdlib only, so it runs before the project environment exists.

Mentions of `tekla-cli` that are only data (`cat docs/tekla-cli-contract.md`,
`git commit -m "..."`, `grep tekla-cli`) are not invocations. A segment whose command word
is on the inert list is skipped, unless the command contains `$(` or a backtick, which can
run code even inside double quotes.

The CLI is also recognised under its .NET project name (`TeklaCli.exe`), and any
`dotnet run|exec|watch` counts as a write, because it can start the CLI without naming it
(RTI-0006, ADR-0007). `dotnet build|restore|clean` stay allowed.

Spec validation receipts (`*.receipt.json`, ADR-0010) are written only by
`harness validate spec` (RTI-0008). A command that names a receipt is denied for every agent,
builder included, unless it only reads (_INERT_COMMANDS, _RECEIPT_READERS) with no redirection
into a receipt; a receipt name piped into another command counts too. The
`Edit(**/*.receipt.json)` deny rule in settings covers the file tools. This narrows forgery but
does not close it: a script file, a glob that does not spell `.receipt.json`, or a directory
copy is not seen here.
"""

from __future__ import annotations

import json
import re
import shlex
import sys

WRITER_AGENT = "builder"
READ_SUBCOMMANDS = frozenset(
    {"info", "validate", "query", "selected", "export", "version", "help", "--help", "-h", "--version"}
)
SHELL_TOOLS = frozenset({"Bash", "PowerShell"})

# Executable name: tekla-cli(.exe), optionally with a Windows or POSIX path. The .NET default
# build names `TeklaCli.exe` / `tekla_cli` are matched too (RTI-0006), case-insensitive.
_EXE = re.compile(r"(?:^|[\\/])tekla[-_]?cli(?:\.exe)?$", re.IGNORECASE)
# Mentions of the tool that the tokenizer might miss (e.g. inside $(...) or & "...").
# A longer name such as `tekla-cli-contract.md` is a different word, not the tool (RTI-0005);
# `tekla-cli.exe`, `tekla-cli.cmd`, `tekla-cli'` and the project folder `tekla/TeklaCli` count.
_MENTION = re.compile(r"tekla[-_]?cli(?![-\w])", re.IGNORECASE)
# `dotnet run|exec|watch` can start the CLI without naming its exe (e.g. from inside the project
# folder). The contract forbids that route, so any such segment counts as a write (RTI-0006).
_DOTNET = re.compile(r"(?:^|[\\/])dotnet(?:\.exe)?$", re.IGNORECASE)
_DOTNET_RUN = frozenset({"run", "exec", "watch"})
# `dotnet <sub>` is inert only for these: they build, they do not start the CLI.
_DOTNET_INERT_SUBCOMMANDS = frozenset({"build", "restore", "clean"})
# Commands that only read or print their arguments. A tekla-cli mention after one of these
# is data, not an invocation. Anything not listed here is treated as possibly executing.
_INERT_COMMANDS = frozenset(
    {
        "cat", "head", "tail", "less", "more", "wc", "grep", "egrep", "fgrep", "rg", "echo",
        "printf", "ls", "dir", "type", "get-content", "select-string", "get-childitem",
        "write-output", "cd", "pushd", "set-location",
    }
)  # fmt: skip
# `git <sub>` is inert only for these subcommands, and never with `-c` (aliases can run code).
_GIT_INERT_SUBCOMMANDS = frozenset({"add", "commit", "diff", "log", "show", "status", "grep", "blame"})
_SUBSTITUTION = re.compile(r"\$\(|`")
# A spec validation receipt file name (RTI-0008), case-insensitive for Windows paths.
_RECEIPT = re.compile(r"\.receipt\.json", re.IGNORECASE)
RECEIPT_PRODUCER = "uv run harness validate spec <spec>"
# Commands that only test, compare or parse a receipt; with _INERT_COMMANDS they may name one.
_RECEIPT_READERS = frozenset(
    {
        "test", "[", "stat", "test-path", "jq", "diff", "cmp", "tr", "convertfrom-json",
        "select-object", "format-list", "format-table", "out-string", "measure-object",
    }
)  # fmt: skip
# Separators that end a statement; a pipeline feeds a receipt name only within one statement.
# Not `&`: the tokenizer also splits `2>&1`, `>&2` and `|&` at it (fail closed).
_STATEMENT_ENDS = frozenset({";", "&&", "||"})
_ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_]\w*=")
# Shell operators that start a new simple command.
_SEPARATORS = frozenset({";", "&&", "||", "|", "&", "(", ")", "{", "}", "`", "$("})


def _split(command: str) -> list[str]:
    """Tokenize loosely across bash and PowerShell; never raise.

    Every newline separates commands like `;` (RTI-0009), a bash backslash-newline too: in
    PowerShell a trailing backslash is part of a path, so joining lines would hide the next
    one. A split bash continuation fails closed. A newline inside quotes stays in its token.
    """
    lines = re.sub(r"\r?\n", " ; ", command)
    spaced = re.sub(r"(\$\(|&&|\|\||[;|&(){}`])", r" \1 ", lines)
    try:
        lexer = shlex.shlex(spaced, posix=True, punctuation_chars=False)
        lexer.whitespace_split = True
        lexer.commenters = ""
        lexer.escape = ""  # keep Windows backslashes in paths
        return list(lexer)
    except ValueError:  # unbalanced quotes
        return [t.strip("\"'") for t in spaced.split()]


def _segments(tokens: list[str]) -> list[list[str]]:
    """Split tokens into simple commands at shell operators."""
    segments: list[list[str]] = [[]]
    for tok in tokens:
        if tok in _SEPARATORS:
            segments.append([])
        else:
            segments[-1].append(tok)
    return [seg for seg in segments if seg]


def _command_word(segment: list[str]) -> tuple[str, int] | None:
    """Return (lowercased bare command name, index), skipping leading VAR=value words."""
    for i, tok in enumerate(segment):
        if _ENV_ASSIGNMENT.match(tok):
            continue
        name = re.split(r"[\\/]", tok)[-1].lower()
        return name.removesuffix(".exe"), i
    return None


def _is_inert(segment: list[str], substitution: bool) -> bool:
    """True if the segment only prints or searches its arguments (see _INERT_COMMANDS)."""
    if substitution:
        return False
    word = _command_word(segment)
    if word is None:
        return False
    name, idx = word
    if name in _INERT_COMMANDS:
        return True
    if name == "git":
        args = segment[idx + 1 :]
        sub = next((a for a in args if not a.startswith("-")), None)
        return sub in _GIT_INERT_SUBCOMMANDS and "-c" not in args
    if name == "dotnet":
        args = [a.lower() for a in segment[idx + 1 :]]
        sub = next((a for a in args if not a.startswith("-")), None)
        return sub in _DOTNET_INERT_SUBCOMMANDS and not _DOTNET_RUN.intersection(args)
    return False


def _is_dotnet_run(segment: list[str]) -> bool:
    """True if the segment runs `dotnet run|exec|watch` anywhere (fail closed: env, paths)."""
    return any(_DOTNET.search(t) for t in segment) and any(t.lower() in _DOTNET_RUN for t in segment)


def find_subcommands(command: str) -> list[str | None]:
    """Return the subcommand of each tekla-cli invocation (None if missing).

    A segment that mentions tekla-cli without a parseable invocation (e.g. `bash -c '...'`)
    yields "<unparsed>", which counts as a write.
    """
    substitution = bool(_SUBSTITUTION.search(command))
    found: list[str | None] = []
    for segment in _segments(_split(command)):
        if _is_inert(segment, substitution):
            continue
        if _is_dotnet_run(segment):
            found.append("<dotnet-run>")
            continue
        invoked = False
        for i, tok in enumerate(segment):
            if not _EXE.search(tok):
                continue
            invoked = True
            sub = None
            for nxt in segment[i + 1 :]:
                if nxt.startswith("-") and nxt.lower() not in READ_SUBCOMMANDS:
                    continue  # global option before the subcommand
                sub = nxt.lower()
                break
            found.append(sub)
        if not invoked and any(_MENTION.search(tok) for tok in segment):
            found.append("<unparsed>")
    return found


def _reads_only(segment: list[str], substitution: bool) -> bool:
    """True if the segment can only read a receipt it names or is piped (see _RECEIPT_READERS)."""
    if any(tok.lower().startswith("--output") for tok in segment):
        return False  # git diff/log/show --output=<file> writes a file
    if _is_inert(segment, substitution):
        return True
    word = _command_word(segment)
    return not substitution and word is not None and word[0] in _RECEIPT_READERS


def touches_receipt(command: str) -> bool:
    """True if the command may write or delete a `*.receipt.json` file (RTI-0008).

    A segment that names a receipt, or follows a `|` after one was named in the same
    statement, passes only if it reads only and no redirection targets the receipt: the token
    holds `>` (`x>r.receipt.json`, `2>r…`) or follows one. A statement ends at `;`, `&&` or
    `||` outside any `(…)` / `{…}` group, so grouping does not hide a pipe.
    """
    substitution = bool(_SUBSTITUTION.search(command))
    segment: list[str] = []
    named_before = False  # a receipt was named earlier in this statement
    fed = False  # a `|` follows that naming: later segments receive the receipt
    depth = 0
    for tok in [*_split(command), ";"]:
        if tok not in _SEPARATORS:
            segment.append(tok)
            continue
        if segment:
            named = [i for i, t in enumerate(segment) if _RECEIPT.search(t)]
            if (named or fed) and not _reads_only(segment, substitution):
                return True
            if any(">" in segment[i] or (i > 0 and segment[i - 1].endswith(">")) for i in named):
                return True
            named_before = named_before or bool(named)
        if tok in ("(", "{", "$("):
            depth += 1
        elif tok in (")", "}"):
            depth = max(depth - 1, 0)
        elif tok == "|":
            fed = fed or named_before
        elif tok in _STATEMENT_ENDS and depth == 0:
            named_before = fed = False
        segment = []
    return False


def _deny(reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def decide(payload: dict) -> dict | None:
    """Return a PreToolUse deny decision, or None for no decision."""
    if payload.get("tool_name") not in SHELL_TOOLS:
        return None
    command = str((payload.get("tool_input") or {}).get("command") or "")
    agent = payload.get("agent_type") or "main session"
    if touches_receipt(command):
        return _deny(
            f"Blocked: this command may write or delete a spec validation receipt "
            f"(*.receipt.json) from '{agent}'. Only `{RECEIPT_PRODUCER}` creates receipts "
            "(RTI-0008). Read or test a receipt with cat, ls, Test-Path or the Read tool; a "
            "missing or stale receipt goes back to doc-reader, which validates the spec."
        )
    writes = [s for s in find_subcommands(command) if s is None or s not in READ_SUBCOMMANDS]
    if not writes:
        return None
    if agent == WRITER_AGENT:
        return None
    shown = ", ".join(s or "<none>" for s in writes)
    return _deny(
        f"Blocked: tekla-cli write command ({shown}) from '{agent}'. "
        f"Only the '{WRITER_AGENT}' subagent may write to Tekla. "
        "Delegate this lot to the builder agent, or use a read subcommand "
        f"({', '.join(sorted(s for s in READ_SUBCOMMANDS if not s.startswith('-')))})."
    )


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            raise ValueError(f"hook payload must be a JSON object, got {type(payload).__name__}")
        decision = decide(payload)
    except Exception as exc:  # fail closed: exit 2 is the only non-zero code that blocks
        sys.stderr.write(f"guard_tekla_write: internal error, blocking the call: {exc!r}\n")
        return 2
    if decision is not None:
        sys.stdout.write(json.dumps(decision))
    return 0


if __name__ == "__main__":
    sys.exit(main())
