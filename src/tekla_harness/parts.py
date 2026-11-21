"""Part mode (ADR-0019): where the parts manifest lives, what a part id looks like, which ids it lists.

Only `parts[].id` is read here; the manifest's own schema check is `harness part manifest-check`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

MANIFEST_REL = "parts/manifest.json"
PART_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class ManifestError(Exception):
    """Something is at the manifest path but it is not a usable manifest (exit 1); names the file."""


class ManifestAccessError(Exception):
    """The operating system refused to check or read the manifest path (exit 3); names the file."""


def manifest_path(work: Path) -> Path:
    return work / MANIFEST_REL


def manifest_present(work: Path) -> bool:
    """True when anything exists at <work>/parts/manifest.json (file, directory, dangling symlink).

    The one test for part mode. It uses `lstat`, never `exists()`: that returns False on a permission error
    and would switch part mode off silently."""
    try:
        manifest_path(work).lstat()
    except (FileNotFoundError, NotADirectoryError):
        return False
    except OSError as exc:
        raise ManifestAccessError(f"cannot check {MANIFEST_REL} ({exc})") from exc
    return True


def part_ids(work: Path) -> frozenset[str] | None:
    """The ids in `parts[]` of the work folder's manifest, or None when there is no manifest.

    Raises ManifestError (not a regular file, not UTF-8 JSON, wrong shape) or ManifestAccessError."""
    if not manifest_present(work):
        return None
    path = manifest_path(work)
    try:
        if not path.is_file():
            raise ManifestError(f"{MANIFEST_REL} is not a regular file")
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ManifestError(f"{MANIFEST_REL} is not UTF-8 text ({exc.reason})") from exc
    except OSError as exc:
        raise ManifestAccessError(f"cannot read {MANIFEST_REL} ({exc})") from exc
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"{MANIFEST_REL} is not valid JSON ({exc})") from exc
    if not isinstance(doc, dict):
        raise ManifestError(f"{MANIFEST_REL} is not a JSON object")
    parts = doc.get("parts")
    if not isinstance(parts, list):
        raise ManifestError(f"{MANIFEST_REL} has no 'parts' list")
    ids: list[str] = []
    for index, part in enumerate(parts):
        part_id = part.get("id") if isinstance(part, dict) else None
        if not isinstance(part_id, str):
            raise ManifestError(f"{MANIFEST_REL} parts[{index}] has no string 'id'")
        ids.append(part_id)
    return frozenset(ids)
