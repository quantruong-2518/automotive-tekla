"""Load the JSON Schemas in `schemas/` and validate artefacts against them."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

SCHEMA_NAMES = (
    "common",
    "spec",
    "project-state",
    "read-log",
    "dxf-probe",
    "intake",
    "text-index",
    "sheets",
    "grids",
    "levels",
    "sheet-text",
    "callouts",
    "answers",
    "question-registry",
    "grid-system",
    "status",
    "cache-entry",
    "spec-receipt",
)
_REPO_SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"


@dataclass(frozen=True)
class Problem:
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "message": self.message}


def schema_dir() -> Path:
    """Repo `schemas/` in a checkout; the packaged copy in an installed wheel."""
    if _REPO_SCHEMAS.is_dir():
        return _REPO_SCHEMAS
    return Path(str(resources.files("tekla_harness") / "schema_files"))


@cache
def _load_all() -> tuple[dict[str, dict[str, Any]], Registry]:
    schemas: dict[str, dict[str, Any]] = {}
    registry: Registry = Registry()
    for name in SCHEMA_NAMES:
        doc = json.loads((schema_dir() / f"{name}.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(doc)
        schemas[name] = doc
        registry = registry.with_resource(doc["$id"], Resource.from_contents(doc))
    return schemas, registry


def validator(name: str) -> Draft202012Validator:
    if name not in SCHEMA_NAMES or name == "common":
        raise KeyError(f"unknown schema '{name}'; choose from {', '.join(SCHEMA_NAMES[1:])}")
    schemas, registry = _load_all()
    return Draft202012Validator(schemas[name], registry=registry)


def validate(name: str, data: Any) -> list[Problem]:
    """Schema errors first; semantic checks only run on schema-valid data."""
    problems = [
        Problem("/" + "/".join(str(p) for p in err.absolute_path), err.message)
        for err in sorted(validator(name).iter_errors(data), key=lambda e: list(e.absolute_path))
    ]
    if not problems and name == "spec":
        problems = check_spec(data)
    return problems


def check_spec(spec: dict[str, Any]) -> list[Problem]:
    """Rules JSON Schema cannot express."""
    problems: list[Problem] = []
    seen: dict[str, int] = {}
    open_questions = set(spec["open_questions"])
    for i, member in enumerate(spec["members"]):
        here = f"/members/{i}"
        sid = member["spec_id"]
        if sid in seen:
            problems.append(
                Problem(f"{here}/spec_id", f"duplicate spec_id '{sid}' (also /members/{seen[sid]})")
            )
        seen.setdefault(sid, i)

        a, b = member["start"], member["end"]
        if math.dist((a["x"], a["y"], a["z"]), (b["x"], b["y"], b["z"])) < 1.0:
            problems.append(Problem(here, "start and end are less than 1 mm apart"))

        low = [k for k, v in member.items() if isinstance(v, dict) and v.get("confidence") == "low"]
        qids = member.get("question_ids", [])
        if low and not qids:
            problems.append(Problem(here, f"low-confidence field(s) {', '.join(low)} without a question_id"))
        for q in qids:
            if q not in open_questions:
                problems.append(Problem(f"{here}/question_ids", f"'{q}' is not listed in open_questions"))
    return problems
