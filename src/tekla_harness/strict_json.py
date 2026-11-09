"""Strict JSON profile shared with the C# reader (ADR-0010 Amendment 1, section 1).

RFC 8259 plus: no BOM, valid UTF-8, no duplicate keys (compared after unescaping), no NaN or
Infinity, no number that is not a finite double, no integer outside +-2^53, no lone surrogate or
U+0000 in a string, nesting depth at most 64, size at most 16 MiB. The corpus in
`tests/fixtures/strict-json/` is run by both readers.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

MAX_BYTES = 16 * 1024 * 1024
MAX_DEPTH = 64
MAX_INT = 2**53

_BAD_CHAR = re.compile("[\x00\ud800-\udfff]")


class StrictJsonError(ValueError):
    """The bytes are not JSON under the strict profile."""


def _reject_constant(name: str) -> Any:
    raise StrictJsonError(f"{name} is not allowed")


def _parse_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise StrictJsonError(f"number {text} is not a finite double")
    return value


def _parse_int(text: str) -> int:
    value = int(text)
    if abs(value) > MAX_INT:
        raise StrictJsonError(f"integer {text} is outside +-2^53")
    return value


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise StrictJsonError(f"duplicate key {key!r}")
        obj[key] = value
    return obj


def _check_string(text: str) -> None:
    if _BAD_CHAR.search(text):
        raise StrictJsonError("string contains a lone surrogate or U+0000")


def _check_tree(root: Any) -> None:
    """Iterative walk: depth and string content (no recursion on deep input)."""
    stack: list[tuple[Any, int]] = [(root, 1)]
    while stack:
        node, depth = stack.pop()
        if isinstance(node, str):
            _check_string(node)
        elif isinstance(node, dict):
            if depth > MAX_DEPTH:
                raise StrictJsonError(f"nesting depth exceeds {MAX_DEPTH}")
            for key, value in node.items():
                _check_string(key)
                stack.append((value, depth + 1))
        elif isinstance(node, list):
            if depth > MAX_DEPTH:
                raise StrictJsonError(f"nesting depth exceeds {MAX_DEPTH}")
            stack.extend((item, depth + 1) for item in node)


def loads_strict(data: bytes) -> Any:
    """Parse `data` under the strict profile or raise StrictJsonError."""
    if len(data) > MAX_BYTES:
        raise StrictJsonError("file is larger than 16 MiB")
    if data.startswith(b"\xef\xbb\xbf"):
        raise StrictJsonError("file starts with a UTF-8 BOM")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StrictJsonError(f"not valid UTF-8: {exc}") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_object,
            parse_constant=_reject_constant,
            parse_float=_parse_float,
            parse_int=_parse_int,
        )
    except StrictJsonError:
        raise
    except RecursionError as exc:
        raise StrictJsonError(f"nesting depth exceeds {MAX_DEPTH}") from exc
    except ValueError as exc:  # JSONDecodeError and int() digit-limit errors
        raise StrictJsonError(f"invalid JSON: {exc}") from exc
    _check_tree(value)
    return value
