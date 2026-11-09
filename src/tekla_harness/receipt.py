"""Spec validation receipt (ADR-0010 Amendment 1, sections 3-5).

`harness validate spec` writes `<spec name>.receipt.json` next to a spec that passed. The C# CLI
builds only from a spec whose exact bytes hash to the receipt's `spec_sha256`.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from tekla_harness import __version__
from tekla_harness.schemas import validate, validator

# Bump whenever check_spec or the strict JSON profile gets stricter.
SPEC_RULES_VERSION = 1


class ReceiptError(Exception):
    """The receipt we built does not satisfy its own schema (a bug, not a user error)."""


def _spec_schema_id() -> str:
    return cast(str, cast(dict[str, Any], validator("spec").schema)["$id"])


def receipt_path(spec: Path) -> Path:
    return spec.with_name(spec.name + ".receipt.json")


def build_receipt(
    spec_bytes: bytes, spec_name: str, *, now: Callable[[], datetime] | None = None
) -> dict[str, Any]:
    moment = (now or (lambda: datetime.now(UTC)))().astimezone(UTC)
    return {
        "schema_version": "0.1",
        "spec_file": spec_name,
        "spec_sha256": hashlib.sha256(spec_bytes).hexdigest(),
        "spec_schema_id": _spec_schema_id(),
        "validator": {
            "name": "tekla_harness",
            "version": __version__,
            "rules_version": SPEC_RULES_VERSION,
        },
        "validated_at": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def write_receipt(spec: Path, spec_bytes: bytes, *, now: Callable[[], datetime] | None = None) -> Path:
    """Write the receipt for exactly `spec_bytes`; atomic, UTF-8, no BOM, LF."""
    built = build_receipt(spec_bytes, spec.name, now=now)
    problems = validate("spec-receipt", built)
    if problems:
        raise ReceiptError("; ".join(f"{p.path}: {p.message}" for p in problems))
    target = receipt_path(spec)
    payload = (json.dumps(built, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=target.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        Path(tmp_name).replace(target)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return target
