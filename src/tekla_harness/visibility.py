"""Whether a text-index entry prints (tool wave 4, V1).

`extract-text` writes `printed: false` plus `not_printed_reasons` on an entry that does not print
(docs/research/dxf-invisible-text.md). Every producer asks through these two functions, so an index written
before the field existed (no `printed` key) reads as printed and nothing changes for it. Entries whose
visibility is only uncertain keep `printed` absent or true and list `print_uncertain_reasons` instead.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def is_printed(entry: Mapping[str, Any]) -> bool:
    """False only when the entry says `printed: false`; absent or anything else counts as printed."""
    return entry.get("printed") is not False


def not_printed_reasons(entry: Mapping[str, Any]) -> list[str]:
    """The entry's `not_printed_reasons` (a copy; empty when absent or null)."""
    return list(entry.get("not_printed_reasons") or [])
