"""E6w: the surface of the six later `harness part` actions (flags, locks, stdout `$defs`).

The bodies belong to E6b, E7, E9a and E9b; here only the wiring is fixed. The stdout examples are the spec's
(invented values), and each is checked against its `$def` of `part-output`.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

import tekla_harness.cli as cli
from tekla_harness.schemas import validate

W = "W"
FLAGS: dict[str, list[str]] = {
    "chain": ["--block", "B1"],
    "review-sample": ["--part", "B1-caps", "--seed", "7", "--n", "4"],
    "conflicts": [],
    "spotcheck": ["--part", "B1-caps", "--seed", "7", "--n", "5"],
    "answer-key": [
        "--part",
        "B1-caps",
        "--row",
        "R012",
        "--verdict",
        "wrong",
        "--by",
        "An",
        "--correct",
        "x",
    ],
    "score": ["--answer-key", "key.json"],
}


def parse(action: str, *flags: str):
    return cli.build_parser().parse_args(["part", action, W, *flags])


def test_six_actions_parse_their_flags():
    chain = parse("chain", *FLAGS["chain"])
    assert (chain.action, chain.work_dir, chain.block) == ("chain", W, "B1")
    sample = parse("review-sample", *FLAGS["review-sample"])
    assert (sample.part, sample.seed, sample.n) == ("B1-caps", 7, 4)
    assert parse("review-sample", "--part", "B1-caps", "--seed", "0").n is None
    assert parse("conflicts").action == "conflicts"
    spot = parse("spotcheck", *FLAGS["spotcheck"])
    assert (spot.part, spot.seed, spot.n) == ("B1-caps", 7, 5)
    assert parse("spotcheck", "--part", "B1-caps", "--seed", "1").n is None
    key = parse("answer-key", *FLAGS["answer-key"])
    assert (key.part, key.row, key.verdict, key.by, key.correct, key.text) == (
        "B1-caps",
        "R012",
        "wrong",
        "An",
        "x",
        None,
    )
    full = parse(
        "answer-key", "--part", "P", "--row", "R1000", "--verdict", "ok", "--by", "An", "--text", "t"
    )
    assert (full.row, full.verdict, full.correct, full.text) == ("R1000", "ok", None, "t")
    for verdict in ("ok", "wrong", "cannot_tell"):
        assert parse("answer-key", "--part", "P", "--row", "R001", "--verdict", verdict, "--by", "An")
    score = parse("score", *FLAGS["score"])
    assert score.answer_key == "key.json" and parse("score").answer_key is None
    for action, flags in FLAGS.items():
        assert callable(parse(action, *flags).handler)


@pytest.mark.parametrize(
    "action, flags",
    [
        ("review-sample", ["--part", "P", "--seed", "-1"]),
        ("review-sample", ["--part", "P", "--seed", "x"]),
        ("review-sample", ["--part", "P", "--seed", "1", "--n", "0"]),
        ("review-sample", ["--part", "P", "--seed", "1", "--n", "-2"]),
        ("review-sample", ["--part", "P", "--seed", "1", "--n", "many"]),
        ("review-sample", ["--part", "P"]),
        ("spotcheck", ["--part", "P", "--seed", "-1"]),
        ("spotcheck", ["--part", "P", "--seed", "1", "--n", "0"]),
        ("answer-key", ["--part", "P", "--row", "R12", "--verdict", "ok", "--by", "An"]),
        ("answer-key", ["--part", "P", "--row", "r012", "--verdict", "ok", "--by", "An"]),
        ("answer-key", ["--part", "P", "--row", "R012\n", "--verdict", "ok", "--by", "An"]),
        ("answer-key", ["--part", "P", "--row", "R012", "--verdict", "maybe", "--by", "An"]),
        ("answer-key", ["--part", "P", "--row", "R012", "--verdict", "ok", "--by", "  "]),
        ("answer-key", ["--part", "P", "--row", "R012", "--verdict", "ok", "--by", ""]),
        ("chain", []),
    ],
)
def test_bad_seed_n_row_by_exit_2(tmp_path, capsys, action, flags):
    assert cli.main(["part", action, str(tmp_path), *flags]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "usage" in captured.err
    assert not (tmp_path / "parts").exists()


def test_writer_actions_are_locked():
    """`conflicts`, `spotcheck` and `answer-key` write the work folder (E6b, E9a, E9b), so they take the lock
    with `receipt`; `chain`, `review-sample` and `score` read only."""
    locked = {"receipt", "conflicts", "spotcheck", "answer-key"}
    assert cli.LOCKED_ACTIONS["part"] == frozenset(locked)
    receipt = cli.build_parser().parse_args(["part", "receipt", W, "--part", "P", "--kind", "checked"])
    assert cli._lock_target(receipt) == Path(W)
    for action in ("conflicts", "spotcheck", "answer-key"):
        assert cli._lock_target(parse(action, *FLAGS[action])) == Path(W), action
    for action in ("chain", "review-sample", "score"):
        assert cli._lock_target(parse(action, *FLAGS[action])) is None, action


# --- the stdout examples of the spec, checked against their `$defs` ---------------------------------------

EXAMPLES: dict[str, dict[str, Any]] = {
    "conflicts": {
        "command": "conflicts",
        "conflicts": 1,
        "questions": [
            {"id": "Q-041", "code": "part_value_conflict", "blocking": True, "parts": ["B1-caps", "B1-stubs"]}
        ],
        "duplicates": [
            {
                "kind": "question",
                "ids": ["Q-031", "Q-036"],
                "parts": ["B1-caps", "B1-stubs"],
                "blocking_differs": False,
            }
        ],
        "obsolete": ["Q-038"],
        "skipped_parts": ["B2-caps"],
    },
    "chain": {
        "command": "chain",
        "block": "B1",
        "parts": [
            {
                "part": "B1-piles",
                "order": 3,
                "rows": [
                    {
                        "row": "R002",
                        "mark": None,
                        "subject": "piles",
                        "field": "count_plan",
                        "value": "26",
                        "number": 26,
                        "state": "seen",
                        "addends": [
                            {"term": "F-012 symbols", "value": 14},
                            {"term": "F-013 symbols", "value": 12},
                        ],
                    }
                ],
                "products": [],
                "sums": {"count_plan": None, "count_x_piles": None},
            },
            {
                "part": "B1-caps",
                "order": 4,
                "rows": [
                    {
                        "row": "R001",
                        "mark": "K-1",
                        "subject": None,
                        "field": "piles_per_member",
                        "value": None,
                        "number": None,
                        "state": "absent",
                        "addends": [],
                    }
                ],
                "products": [{"mark": "K-1", "count_plan": 4, "piles_per_member": 2, "product": 8}],
                "sums": {"count_plan": 4, "count_x_piles": 8},
            },
        ],
    },
    "review_sample": {
        "command": "review_sample",
        "part": "B1-caps",
        "seed": 7,
        "prompts": [
            {
                "row": "R001",
                "kind": "value",
                "mark": "K-2",
                "subject": None,
                "field": "size",
                "file": "plans.dxf",
                "sheet": "model#05",
                "sheet_number": "S-05",
                "view": "MẶT BẰNG",
                "prompt": "Sheet S-05, view 'MẶT BẰNG': what size does the drawing give for K-2? "
                "Cite the entry ids.",
            },
            {
                "row": "R004",
                "kind": "absence",
                "mark": None,
                "subject": "piles",
                "field": "count_plan",
                "file": None,
                "sheet": None,
                "sheet_number": None,
                "view": None,
                "prompt": "Is there a count of piles on the drawing?",
            },
        ],
    },
    "spotcheck": {
        "command": "spotcheck",
        "part": "B1-caps",
        "seed": 7,
        "rows": ["R001", "R004", "R007", "R010", "R012"],
        "written": ["parts/B1-caps/spotcheck.json", "../spotcheck/B1-caps.md"],
    },
    "answer_key": {
        "command": "answer_key",
        "written": True,
        "key": {
            "part": "B1-caps",
            "file": "plans.dxf",
            "sheet": "model#05",
            "subject": "k-2",
            "field": "size",
        },
        "superseded": 0,
    },
    "score": {
        "command": "score",
        "answer_key": "/w/answer-key.json",
        "parts": [
            {"part": "B1-caps", "checked": 5, "agree": 4, "differ": 1, "missing": 0, "cannot_tell": 0},
        ],
        "total": {"checked": 5, "agree": 4, "differ": 1, "missing": 0, "cannot_tell": 0},
    },
}


def _paths(node: Any, path: tuple[Any, ...] = ()):
    """Every object of the document, as a path of keys and indexes."""
    if isinstance(node, dict):
        yield path
        for key, value in node.items():
            yield from _paths(value, (*path, key))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _paths(value, (*path, i))


def _at(doc: Any, path: tuple[Any, ...]) -> Any:
    for step in path:
        doc = doc[step]
    return doc


def test_part_output_examples_validate():
    schema = json.loads(
        (Path(cli.__file__).parents[2] / "schemas" / "part-output.schema.json").read_text("utf-8")
    )
    assert {"conflicts", "chain", "review_sample", "spotcheck", "answer_key", "score"} <= set(schema["$defs"])
    for name, example in EXAMPLES.items():
        assert validate("part-output", example) == [], name
        assert example["command"] == name
        # every object of the document: all keys required, no key beyond them
        for path in _paths(example):
            extra = copy.deepcopy(example)
            _at(extra, path)["unexpected"] = 1
            assert validate("part-output", extra), f"{name}: extra key accepted at {path}"
            for key in _at(example, path):
                short = copy.deepcopy(example)
                del _at(short, path)[key]
                assert validate("part-output", short), f"{name}: {key} not required at {path}"
        # a document of another command never passes as this one
        other = copy.deepcopy(example)
        other["command"] = "chain" if name != "chain" else "score"
        assert validate("part-output", other), name

    def accepts(name: str, path: tuple[Any, ...], value: Any) -> bool:
        doc = copy.deepcopy(EXAMPLES[name])
        parent = _at(doc, path[:-1])
        parent[path[-1]] = value
        return validate("part-output", doc) == []

    # nullable: chain mark, subject, number, value, sums; prompts mark, subject, file, sheet, sheet_number,
    # view; key.sheet. Not nullable: the rest.
    row = ("parts", 0, "rows", 0)
    for key in ("mark", "subject", "number", "value"):
        assert accepts("chain", (*row, key), None), key
    for key in ("count_plan", "count_x_piles"):
        assert accepts("chain", ("parts", 1, "sums", key), None), key
    for key in ("row", "field", "state", "addends"):
        assert not accepts("chain", (*row, key), None), key
    for key in ("part", "order", "rows", "products", "sums"):
        assert not accepts("chain", ("parts", 0, key), None), key
    for key in ("mark", "subject", "file", "sheet", "sheet_number", "view"):
        assert accepts("review_sample", ("prompts", 0, key), None), key
    for key in ("row", "kind", "field", "prompt"):
        assert not accepts("review_sample", ("prompts", 0, key), None), key
    assert accepts("answer_key", ("key", "sheet"), None)
    for key in ("part", "file", "subject", "field"):
        assert not accepts("answer_key", ("key", key), None), key
    # enums
    assert not accepts("conflicts", ("duplicates", 0, "kind"), "other")
    assert accepts("conflicts", ("duplicates", 0, "kind"), "finding")
    for kind in ("value", "absence", "outside_frame"):
        assert accepts("review_sample", ("prompts", 0, "kind"), kind)
    assert not accepts("review_sample", ("prompts", 0, "kind"), "other")
    # counts are not negative
    assert not accepts("spotcheck", ("seed",), -1)
    assert not accepts("score", ("total", "agree"), -1)
