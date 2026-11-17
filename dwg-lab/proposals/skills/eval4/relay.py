"""EVAL-4 relay filter: copy a simulator's answers into a project, keeping only what the runner may see.

Usage: python dwg-lab/proposals/skills/eval4/relay.py <simulator relayed-answers.json> <project-dir>

Writes <project-dir>/relayed-answers.json with, per answer, only `question_id`, `code`, `text` and
`values` (no `basis`, no `trap`, nothing else), and the top-level `arm` and `answered_by`. Answers with an
empty `text` are dropped. Refuses to overwrite an existing file. EVAL-4 protocol §6.3.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

KEEP = ("question_id", "code", "text", "values")


def relay(source: Path, project: Path) -> Path:
    doc = json.loads(source.read_text(encoding="utf-8"))
    answers = [{k: a.get(k, {} if k == "values" else None) for k in KEEP} for a in doc["answers"]]
    answers = [a for a in answers if a["text"]]
    out = project / "relayed-answers.json"
    if out.exists():
        raise SystemExit(f"refusing: {out} exists")
    body = {"arm": doc.get("arm"), "answered_by": doc.get("answered_by"), "answers": answers}
    out.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    leaked = {k for a in answers for k in a} - set(KEEP)
    assert not leaked, leaked
    return out


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    print(relay(Path(sys.argv[1]), Path(sys.argv[2])))
