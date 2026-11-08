"""Canonical value dump shared with the C# reader tests (ADR-0010 Amendment 1, §8).

One item per line, pre-order: `object <n>` then `key <utf16>` + value per member; `array <n>`;
`string <utf16>`; `int|float <IEEE-754 bits>`; `true`, `false`, `null`. `<utf16>` is the string's
UTF-16 code units as 4 lowercase hex digits each, concatenated (`-` for the empty string); bits are
16 lowercase hex digits. Expected dumps live in tests/fixtures/strict-json/values/<name>.txt.
"""

from __future__ import annotations

import struct
from typing import Any


def _utf16(text: str) -> str:
    data = text.encode("utf-16-le", "surrogatepass")
    units = [data[i + 1] << 8 | data[i] for i in range(0, len(data), 2)]
    return "".join(f"{u:04x}" for u in units) or "-"


def _bits(number: float) -> str:
    return f"{struct.unpack('<Q', struct.pack('<d', number))[0]:016x}"


def dump(value: Any) -> str:
    lines: list[str] = []
    stack: list[Any] = [value]
    while stack:
        node = stack.pop()
        if isinstance(node, tuple):  # ("key", text) marker
            lines.append(f"key {_utf16(node[1])}")
        elif node is True or node is False:
            lines.append("true" if node else "false")
        elif node is None:
            lines.append("null")
        elif isinstance(node, int):
            lines.append(f"int {_bits(float(node))}")
        elif isinstance(node, float):
            lines.append(f"float {_bits(node)}")
        elif isinstance(node, str):
            lines.append(f"string {_utf16(node)}")
        elif isinstance(node, list):
            lines.append(f"array {len(node)}")
            stack.extend(reversed(node))
        elif isinstance(node, dict):
            lines.append(f"object {len(node)}")
            for key, child in reversed(list(node.items())):
                stack.append(child)
                stack.append(("key", key))
        else:
            raise TypeError(f"unexpected {type(node).__name__}")
    return "\n".join(lines) + "\n"
