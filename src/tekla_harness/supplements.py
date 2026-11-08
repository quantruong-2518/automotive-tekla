"""supplements: evidence the drawing-reader adds to a producer's question (`harness ask --supplement`).

Document `reader-supplements.json`, schema `supplements` (see its description for the key, the statuses and
the refusals). A supplement never changes the target question's blocking flag, answer or refs; questions.md
shows it under the question.

Tool wave 2 seam: reading returns nothing and writing is not implemented yet; package P3 implements both.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

SUPPLEMENTS_FILE = "reader-supplements.json"
NOT_YET = "harness ask --supplement is not implemented yet (tool wave 2, package P3)"


def load_supplements(work: Path) -> list[dict[str, Any]]:
    """Every supplement of the work folder, in the order added. Seam: none."""
    del work
    return []


def add_supplement(
    work_dir: Path | str,
    *,
    target_id: str,
    where: str,
    found: str,
    text: str,
    file: str | None = None,
    sheet: str | None = None,
) -> dict[str, str]:
    """Append one supplement; returns {key, target_id, status: new | already_supplemented}."""
    del work_dir, target_id, where, found, text, file, sheet
    raise NotImplementedError(NOT_YET)


def withdraw_supplement(work_dir: Path | str, key: str, reason: str) -> dict[str, str]:
    """Mark a supplement withdrawn (kept); returns {key, status: withdrawn | already_withdrawn}."""
    del work_dir, key, reason
    raise NotImplementedError(NOT_YET)
