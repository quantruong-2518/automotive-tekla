"""Tool wave 4, package T, V1: the text_visibility_uncertain question of one file (read_dxf).

One non-blocking question per file whose printed entries list `print_uncertain_reasons`: a count per reason,
the first five entries as examples. Fixtures are built with ezdxf inside tmp_path.
"""

from __future__ import annotations

from tekla_harness.read_dxf import MAX_VISIBILITY_EXAMPLES, text_visibility_questions
from test_extract_text import build, index, text_at


def uncertain_fixture(doc):
    doc.header["$ATTMODE"] = 2
    doc.blocks.new("B").add_attdef("T", (0, 0), text="d", dxfattribs={"height": 1})
    msp = doc.modelspace()
    for i in range(7):
        msp.add_blockref("B", (0, 9 * i)).add_auto_attribs({"T": f"attr {i}"})
    text_at(msp, "on defpoints", "Arial", layer="Defpoints", insert=(50, 0))
    text_at(msp, "plain", "Arial", insert=(50, 20))


def test_one_non_blocking_question_per_file_counts_each_reason_and_lists_five_examples(tmp_path):
    result = index(build(tmp_path, uncertain_fixture))
    questions = text_visibility_questions(result, "dir/a.dxf")
    assert len(questions) == 1
    q = questions[0]
    assert (q["code"], q["blocking"], q["file"]) == ("text_visibility_uncertain", False, "dir/a.dxf")
    assert q["count"] == 8 and q["truncated"] is True  # 7 attributes (ATTMODE) + 1 on Defpoints
    assert all(r["file"] == "dir/a.dxf" for r in q["refs"])
    per_reason = {r["where"]: r["found"] for r in q["refs"] if r["where"].startswith("reason ")}
    assert per_reason == {
        "reason attmode_not_normal": "7 entries",
        "reason defpoints_layer": "1 entry",
    }
    examples = [r for r in q["refs"] if not r["where"].startswith("reason ")]
    assert len(examples) == MAX_VISIBILITY_EXAMPLES == 5
    ids = [r["found"].split(":")[0] for r in examples]
    assert ids == sorted(ids) and all(i.startswith("T0") for i in ids)  # the first entries in id order
    assert "attmode_not_normal" in examples[0]["where"]
    assert q["refs"][: len(per_reason)] == [r for r in q["refs"] if r["where"].startswith("reason ")]


def test_few_uncertain_entries_are_all_listed_and_not_truncated(tmp_path):
    def fn(doc):
        text_at(doc.modelspace(), "one", "Arial", layer="Defpoints")
        text_at(doc.modelspace(), "two", "Arial", layer="Defpoints", insert=(0, 9))

    q = text_visibility_questions(index(build(tmp_path, fn)), "a.dxf")[0]
    assert q["count"] == 2 and q["truncated"] is False
    assert [r["found"] for r in q["refs"] if not r["where"].startswith("reason ")] == [
        "T000001: one",
        "T000002: two",
    ]


def test_no_uncertain_entry_means_no_question(tmp_path):
    def fn(doc):
        text_at(doc.modelspace(), "hidden", "Arial", invisible=1)
        text_at(doc.modelspace(), "shown", "Arial", insert=(0, 9))

    assert text_visibility_questions(index(build(tmp_path, fn)), "a.dxf") == []


def test_a_not_printed_entry_with_uncertain_leftovers_is_not_counted(tmp_path):
    def fn(doc):
        doc.header["$ATTMODE"] = 0
        doc.blocks.new("B").add_attdef("T", (0, 0), text="d", dxfattribs={"height": 1})
        ins = doc.modelspace().add_blockref("B", (0, 0)).add_auto_attribs({"T": "x"})
        ins.attribs[0].dxf.invisible = 1

    assert text_visibility_questions(index(build(tmp_path, fn)), "a.dxf") == []


def test_an_index_without_the_fields_raises_no_question():
    old = {"entries": [{"id": "T000001", "display_text": "x", "flags": []}]}
    assert text_visibility_questions(old, "a.dxf") == []


def test_an_entry_that_says_it_is_not_printed_is_never_counted():
    # a hand-written index: the extractor never lists uncertain reasons on a not-printed entry, but a reader
    # of any index must still leave it out
    uncertain = ["defpoints_layer"]
    entries = [
        {
            "id": "T000001",
            "display_text": "a",
            "layer": "L",
            "printed": False,
            "print_uncertain_reasons": uncertain,
        },
        {
            "id": "T000002",
            "display_text": "b",
            "layer": "L",
            "printed": True,
            "print_uncertain_reasons": uncertain,
        },
    ]
    (q,) = text_visibility_questions({"entries": entries}, "a.dxf")
    assert q["count"] == 1 and q["refs"][-1]["found"] == "T000002: b"
