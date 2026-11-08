"""extract_text: deterministic text index. Fixtures are built with ezdxf inside tmp_path.

No text from the sample drawings is used here (they are untrusted data). Legacy strings are built from
table facts: TCVN3 0xB5 is a-grave, 0xC6 is a-dot-below-breve; VNI 'a' + 0xF8 is a-grave and
'A' + 0xD8 is A-grave.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest
from ezdxf.enums import TextEntityAlignment
from ezdxf.filemanagement import new
from ezdxf.math import Vec2
from ezdxf.render.mleader import ConnectionSide
from ezdxf.tools.text import plain_mtext

from tekla_harness import extract_text as mod
from tekla_harness import read_dxf
from tekla_harness.cli import main
from tekla_harness.extract_text import MAX_BLOCK_DEPTH, extract_text, mtext_runs
from tekla_harness.knowledge import EMPTY_TABLE, KnowledgeError
from tekla_harness.schemas import validate
from test_knowledge import approved, row, table_of

REPO = Path(__file__).resolve().parents[1]
A_GRAVE_TCVN3 = "\xb5"
A_DOT_BREVE_TCVN3 = "\xc6"
D_STROKE_TCVN3 = "\xa7"  # capital D with stroke (single case)


def save(tmp_path: Path, doc: Any, name: str = "t.dxf") -> Path:
    path = tmp_path / name
    doc.saveas(path)
    return path


def build(tmp_path: Path, fn=None, *, version: str = "R2018", name: str = "t.dxf") -> Path:
    doc = new(version, setup=False)
    doc.styles.add(".VnTime", font="vntime.ttf")
    doc.styles.add(".VnTimeH", font="vntimeh.ttf")
    doc.styles.add("VNI-Times", font="vni-times.ttf")
    doc.styles.add("VntimeH", font="vntimeh.shx")
    doc.styles.add("Arial", font="arial.ttf")
    doc.styles.add("Simplex", font="simplex.shx")
    if fn:
        fn(doc)
    return save(tmp_path, doc, name)


def index(path: Path, *, status: str = "ok", **kwargs) -> dict[str, Any]:
    kwargs.setdefault("knowledge", EMPTY_TABLE)  # the shipped table is only used where a test says so
    result = extract_text(path, **kwargs)
    assert result["status"] == status, result.get("summary", {}).get("errors", result.get("error"))
    assert validate("text-index", result) == [], validate("text-index", result)
    json.dumps(result, allow_nan=False)  # strict JSON
    return result


def only(result: dict[str, Any], **match) -> dict[str, Any]:
    rows = [e for e in result["entries"] if all(e.get(k) == v for k, v in match.items())]
    assert len(rows) == 1, rows
    return rows[0]


def text_at(msp, text: str, style: str, **attribs) -> None:
    msp.add_text(text, dxfattribs={"style": style, "height": 2.5, "insert": (0, 0), **attribs})


# --- entity kinds ---------------------------------------------------------------------


def test_text_entry_has_every_field(tmp_path):
    def fn(doc):
        doc.layers.add("NOTES")
        doc.modelspace().add_text(
            "NOTE 1",
            dxfattribs={
                "style": "Arial",
                "height": 3.5,
                "insert": (10, 20),
                "rotation": 30,
                "layer": "NOTES",
            },
        )

    result = index(build(tmp_path, fn))
    e = only(result, entity_type="TEXT")
    assert e["id"] == "T000001"
    assert (e["space"], e["layout"], e["coordinate_frame"]) == ("model", "Model", "wcs")
    assert (e["layer"], e["layer_state"], e["style"], e["font_file"]) == ("NOTES", "on", "Arial", "arial.ttf")
    assert e["position"] == {"x": 10.0, "y": 20.0, "basis": "insert"}
    assert (e["height"], e["rotation"], e["alignment"]) == (3.5, 30.0, "LEFT")
    assert e["handle"]
    assert e["block_path"] == [] and e["tag"] is None
    assert e["raw_text"] == e["plain_text"] == e["decoded_text"] == e["display_text"] == "NOTE 1"
    assert e["provenance"] == {"file": str(tmp_path / "t.dxf"), "sheet": "unknown", "method": "dxf_entity"}
    assert e["decode"]["encoding_used"] == "unicode" and e["decode"]["source"] == "style_font"
    assert e["confidence"] == "high"
    assert result["status"] == "ok"
    assert result["summary"]["total_entries"] == 1


def test_mtext_has_raw_and_plain_text(tmp_path):
    raw = r"{\Fsimplex.shx|c1;GRID} {\H1.083x;LINE}\PSECOND \S1/2;"

    def fn(doc):
        doc.modelspace().add_mtext(raw, dxfattribs={"style": "Arial", "char_height": 2.5, "insert": (5, 6)})

    e = only(index(build(tmp_path, fn)), entity_type="MTEXT")
    assert e["raw_text"] == raw
    assert e["plain_text"] == plain_mtext(raw) == "GRID LINE\nSECOND 1/2"
    assert e["alignment"] == "TOP_LEFT" and e["height"] == 2.5
    assert e["decode"]["runs"] == 2 and e["decode"]["mixed_fonts"] is True
    assert "inline_font_unknown" in e["flags"]  # simplex.shx says nothing about the encoding


@pytest.mark.parametrize(
    "raw",
    [r"plain", r"a\Pb", r"{\H2x;big} small", r"\S1^2; m", r"\L under\l and \Oover\o", r"x\~y", "tab^Iend"],
)
def test_plain_text_matches_ezdxf_without_percent_codes(raw):
    assert "".join(r.text for r in mtext_runs(raw)).replace("\t", "    ") == plain_mtext(raw)


def test_attribs_nested_two_levels(tmp_path):
    def fn(doc):
        inner = doc.blocks.new("INNER")
        inner.add_text("in-inner", dxfattribs={"insert": (1, 1), "height": 2, "style": "Arial"})
        inner.add_attdef("TAG", (0, 0), text="d", dxfattribs={"height": 1})
        outer = doc.blocks.new("OUTER")
        outer.add_text("in-outer", dxfattribs={"insert": (10, 0), "height": 2, "style": "Arial"})
        outer.add_blockref("INNER", (5, 5), dxfattribs={"rotation": 90}).add_auto_attribs({"TAG": "nested"})
        msp = doc.modelspace()
        msp.add_blockref("OUTER", (100, 100), dxfattribs={"xscale": 2, "yscale": 2}).add_auto_attribs({})
        msp.add_blockref("INNER", (0, 0)).add_auto_attribs({"TAG": "top"})

    result = index(build(tmp_path, fn))
    top = only(result, raw_text="top")
    assert (top["entity_type"], top["tag"], top["block_name"], top["block_path"]) == (
        "ATTRIB",
        "TAG",
        "INNER",
        [],
    )
    assert top["handle"] and top["insert_handle"]
    nested = only(result, raw_text="nested")
    assert (nested["tag"], nested["block_name"], nested["block_path"]) == ("TAG", "INNER", ["OUTER"])
    assert nested["handle"] is None and nested["insert_handle"] is None  # virtual copies carry no handle
    assert nested["insert_handles"][0] is not None  # the top INSERT of OUTER is real
    leaf = only(result, raw_text="in-inner", block_path=["OUTER", "INNER"])
    assert leaf["position"]["x"] == pytest.approx(
        108.0
    )  # (1,1) rotated 90 -> (-1,1), +(5,5), x2 scale, +(100,100): WCS y is 112
    assert leaf["definition_handle"] and leaf["handle"] is None
    assert only(result, raw_text="in-outer")["position"]["x"] == pytest.approx(120)
    assert (
        result["summary"]["in_block_count"] == 4
    )  # nested attrib, in-outer, in-inner x2 (OUTER chain + INNER)
    assert [d["tag"] for d in result["attdefs"]] == ["TAG"]
    assert not any(e["raw_text"] == "d" for e in result["entries"])  # the ATTDEF default is not visible text


def test_attdef_flags_listed_not_indexed(tmp_path):
    def fn(doc):
        blk = doc.blocks.new("B")
        blk.add_attdef("CONST", (0, 0), text="fixed", dxfattribs={"flags": 2, "height": 1})
        blk.add_attdef("HIDDEN", (0, 1), text="h", dxfattribs={"flags": 1, "height": 1})

    result = index(build(tmp_path, fn))
    assert result["entries"] == []
    by_tag = {d["tag"]: d for d in result["attdefs"]}
    assert by_tag["CONST"]["constant"] is True and by_tag["HIDDEN"]["invisible"] is True
    assert by_tag["CONST"]["space"] == "block:B"


def test_invisible_attrib_is_kept_and_flagged(tmp_path):
    def fn(doc):
        doc.blocks.new("B").add_attdef("T", (0, 0), text="d", dxfattribs={"height": 1})
        ins = doc.modelspace().add_blockref("B", (0, 0)).add_auto_attribs({"T": "secret"})
        ins.attribs[0].dxf.flags = 1

    e = only(index(build(tmp_path, fn)), entity_type="ATTRIB")
    assert e["invisible"] is True and "attribute_invisible" in e["flags"]


def test_layout_text_is_in_paper_coordinates(tmp_path):
    def fn(doc):
        doc.layout("Layout1").add_text(
            "SHEET", dxfattribs={"style": "Arial", "height": 5, "insert": (400, 20)}
        )
        doc.modelspace().add_text("M", dxfattribs={"style": "Arial", "height": 5, "insert": (400, 20)})

    result = index(build(tmp_path, fn))
    sheet = only(result, raw_text="SHEET")
    assert (sheet["space"], sheet["layout"], sheet["coordinate_frame"]) == ("Layout1", "Layout1", "paper")
    assert sheet["provenance"]["sheet"] == "unknown"  # the printed sheet number is not read here
    assert only(result, raw_text="M")["coordinate_frame"] == "wcs"
    assert result["entries"][0]["space"] == "model"  # modelspace first, then layouts in tab order


def test_multileader_text(tmp_path):
    def fn(doc):
        ml = doc.modelspace().add_multileader_mtext("Standard")
        ml.set_content("LEAD {\\Fsimplex.shx;two}", style="Arial", char_height=2.5)
        ml.add_leader_line(ConnectionSide.left, [Vec2(0, 0), Vec2(10, 10)])
        ml.build(Vec2(50, 50))

    result = index(build(tmp_path, fn))
    e = only(result, entity_type="MULTILEADER")
    assert e["plain_text"] == "LEAD two"
    assert e["position"] == {"x": 50.0, "y": 50.0, "basis": "context_mtext_insert"}
    assert e["handle"] and e["height"] == 2.5


def test_dimension_override_and_placeholder_text(tmp_path):
    def fn(doc):
        msp = doc.modelspace()
        msp.add_linear_dim(base=(0, 5), p1=(0, 0), p2=(10, 0), text="OVR %%c20").render()
        msp.add_linear_dim(base=(0, 9), p1=(0, 0), p2=(10, 0), text="<> TYP").render()
        msp.add_linear_dim(base=(0, 12), p1=(0, 0), p2=(10, 0)).render()  # pure measurement

    result = index(build(tmp_path, fn))
    override = only(result, text_rule="override")
    assert override["entity_type"] == "DIMENSION" and override["handle"]
    assert override["display_text"] == "OVR Ø20" and override["special_codes"] == ["%%c"]
    assert override["provenance"]["method"] == "dxf_dimension_text"
    assert override["position"]["basis"] == "text_midpoint"
    assert only(result, text_rule="measured_with_text")["raw_text"] == "<> TYP"
    assert result["summary"]["dimensions_without_override"] == 1
    assert result["summary"]["by_entity_type"]["DIMENSION"] == 2
    assert not any(
        e["entity_type"] == "MTEXT" for e in result["entries"]
    )  # the dimension block is not walked


def test_multileader_block_content_attribute(tmp_path):
    def fn(doc):
        blk = doc.blocks.new("BUBBLE")
        blk.add_attdef("MARK", (0, 0), text="?", dxfattribs={"height": 1})
        ml = doc.modelspace().add_multileader_block("Standard")
        ml.set_content("BUBBLE")
        ml.set_attribute("MARK", "A1")
        ml.add_leader_line(ConnectionSide.left, [Vec2(0, 0), Vec2(5, 5)])
        ml.build(Vec2(30, 30))

    e = only(index(build(tmp_path, fn)), entity_type="MULTILEADER")
    assert e["raw_text"] == "A1" and e["tag"] == "MARK"
    assert "position_is_block_insert" in e["flags"]


def test_empty_text_is_counted_not_indexed(tmp_path):
    def fn(doc):
        msp = doc.modelspace()
        text_at(msp, "", "Arial")
        text_at(msp, "   ", "Arial")
        text_at(msp, "x", "Arial")

    result = index(build(tmp_path, fn))
    assert result["summary"]["total_entries"] == 1
    assert result["summary"]["empty_text_skipped"] == 2


# --- geometry hazards -----------------------------------------------------------------


def test_mirrored_insert_and_ocs_extrusion(tmp_path):
    def fn(doc):
        doc.blocks.new("B").add_text("in-b", dxfattribs={"insert": (5, 0), "height": 2, "style": "Arial"})
        msp = doc.modelspace()
        msp.add_blockref("B", (10, 0), dxfattribs={"xscale": -1})
        text_at(msp, "flipped", "Arial", insert=(5, 0), extrusion=(0, 0, -1))

    result = index(build(tmp_path, fn))
    assert only(result, raw_text="in-b")["position"]["x"] == pytest.approx(5.0)  # 10 - 5
    flipped = only(result, raw_text="flipped")
    assert flipped["position"]["x"] == pytest.approx(-5.0) and "non_default_extrusion" in flipped["flags"]


def test_aligned_text_reports_the_displayed_anchor(tmp_path):
    def fn(doc):
        t = doc.modelspace().add_text("CENTRED", dxfattribs={"style": "Arial", "height": 2.5})
        t.set_placement((3, 4), align=TextEntityAlignment.MIDDLE_CENTER)

    e = only(index(build(tmp_path, fn)), raw_text="CENTRED")
    assert e["position"] == {"x": 3.0, "y": 4.0, "basis": "align_point"}
    assert e["alignment"] == "MIDDLE_CENTER"


def test_layer_zero_in_a_block_takes_the_insert_layer(tmp_path):
    def fn(doc):
        doc.layers.add("GRID")
        doc.layers.add("OLD").off()
        doc.blocks.new("B").add_text(
            "t", dxfattribs={"insert": (0, 0), "layer": "0", "style": "Arial", "height": 1}
        )
        msp = doc.modelspace()
        msp.add_blockref("B", (0, 0), dxfattribs={"layer": "GRID"})
        msp.add_blockref("B", (0, 9), dxfattribs={"layer": "OLD"})

    rows = [e for e in index(build(tmp_path, fn))["entries"]]
    assert [(e["layer"], e["definition_layer"], e["layer_state"]) for e in rows] == [
        ("GRID", "0", "on"),
        ("OLD", "0", "off"),
    ]
    assert "layer_from_insert" in rows[0]["flags"] and "layer_off" in rows[1]["flags"]


# --- recursion guards -----------------------------------------------------------------


def test_depth_limit_is_counted(tmp_path):
    levels = MAX_BLOCK_DEPTH + 4

    def fn(doc):
        for i in range(levels):
            blk = doc.blocks.new(f"L{i}")
            blk.add_text(f"leaf{i}", dxfattribs={"insert": (0, 0), "height": 1, "style": "Arial"})
            if i + 1 < levels:
                blk.add_blockref(f"L{i + 1}", (1, 0))
        doc.modelspace().add_blockref("L0", (0, 0))

    result = index(build(tmp_path, fn))
    assert result["summary"]["total_entries"] == MAX_BLOCK_DEPTH
    assert max(len(e["block_path"]) for e in result["entries"]) == MAX_BLOCK_DEPTH
    assert result["summary"]["depth_limit_count"] == 1
    assert any("deeper" in w for w in result["warnings"])


def test_self_containing_block_is_cut(tmp_path):
    def fn(doc):
        blk = doc.blocks.new("LOOP")
        blk.add_text("once", dxfattribs={"insert": (0, 0), "height": 1, "style": "Arial"})
        blk.add_blockref("LOOP", (1, 1))
        doc.modelspace().add_blockref("LOOP", (0, 0))

    result = index(build(tmp_path, fn))
    assert result["summary"]["total_entries"] == 1
    assert result["summary"]["cycle_count"] == 1


def test_missing_block_and_xref_are_counted(tmp_path):
    def fn(doc):
        doc.modelspace().add_blockref("NOSUCH", (0, 0))
        doc.add_xref_def("other.dxf", "XR")
        doc.modelspace().add_blockref("XR", (0, 0))

    result = index(build(tmp_path, fn))
    assert result["summary"]["missing_block_inserts"] == 1
    assert result["summary"]["xref_inserts_skipped"] == 1


# --- legacy encodings -----------------------------------------------------------------


def test_tcvn3_in_a_lowercase_font_is_converted(tmp_path):
    raw = "m" + A_DOT_BREVE_TCVN3 + "t " + A_GRAVE_TCVN3

    def fn(doc):
        text_at(doc.modelspace(), raw, ".VnTime")

    e = only(index(build(tmp_path, fn)), entity_type="TEXT")
    assert e["raw_text"] == raw
    assert e["decoded_text"] == e["display_text"] == "mặt à"
    d = e["decode"]
    assert (d["encoding_used"], d["source"], d["capital_font"]) == ("tcvn3", "style_font", False)
    assert (d["case_uncertain"], d["ambiguous_count"], d["unmapped_count"], d["nfd_damaged"]) == (
        False,
        0,
        0,
        False,
    )
    assert e["confidence"] == "medium"  # anything decoded from a legacy encoding is capped at medium


def test_tcvn3_capital_font_uppercases_and_flags_lowercase_ascii(tmp_path):
    def fn(doc):
        msp = doc.modelspace()
        text_at(msp, D_STROKE_TCVN3 + A_GRAVE_TCVN3 + "T1", ".VnTimeH", insert=(0, 0))
        text_at(msp, A_GRAVE_TCVN3 + "ab", ".VnTimeH", insert=(0, 9))

    result = index(build(tmp_path, fn))
    clean = only(result, raw_text=D_STROKE_TCVN3 + A_GRAVE_TCVN3 + "T1")
    assert clean["decoded_text"] == "ĐÀT1" and clean["decode"]["capital_font"] is True
    assert clean["confidence"] == "medium"
    guess = only(result, raw_text=A_GRAVE_TCVN3 + "ab")
    assert guess["decode"]["case_uncertain"] is True and guess["decode"]["ambiguous_count"] == 2
    assert guess["confidence"] == "low"
    assert result["summary"]["case_uncertain_count"] == 1


def test_vni_text_is_converted(tmp_path):
    def fn(doc):
        text_at(doc.modelspace(), "a\xf8 A\xd8", "VNI-Times")

    e = only(index(build(tmp_path, fn)), entity_type="TEXT")
    assert e["decoded_text"] == "à À"
    assert e["decode"]["encoding_used"] == "vni" and e["confidence"] == "medium"


def test_special_codes_are_expanded_after_decoding(tmp_path):
    cases = {
        "%%C6a200": "Ø6a200",  # TCVN3: U+00D8 is a letter; expanding first would make it one
        "2%%c16": "2Ø16",
        "EL%%P0.00": "EL±0.00",
        "45%%d": "45°",
        "%%uUNDER%%u %%oOVER%%o": "UNDER OVER",
    }

    def fn(doc):
        msp = doc.modelspace()
        for i, raw in enumerate(cases):
            text_at(msp, raw, ".VnTimeH", insert=(0, 10 * i))

    result = index(build(tmp_path, fn))
    for raw, shown in cases.items():
        e = only(result, raw_text=raw)
        assert e["display_text"] == shown, raw
        assert e["decoded_text"] == e["plain_text"] == raw  # codes unexpanded until display
        # only literal lowercase letters count (the 'a' of '6a200'); the letter inside '%%c' is a code
        assert e["decode"]["ambiguous_count"] == (1 if raw == "%%C6a200" else 0)
        assert e["decode"]["unmapped_count"] == 0
    assert only(result, raw_text="2%%c16")["special_codes"] == ["%%c"]
    assert only(result, raw_text="%%uUNDER%%u %%oOVER%%o")["special_codes"] == ["%%u", "%%o"]


def test_vni_diameter_after_a_vowel_is_not_absorbed(tmp_path):
    def fn(doc):
        text_at(doc.modelspace(), "A%%c12", "VNI-Times")

    e = only(index(build(tmp_path, fn)), entity_type="TEXT")
    assert e["display_text"] == "AØ12"  # not 'A12' with A-grave: the code was never turned into byte 0xD8
    assert e["decode"]["unmapped_count"] == 0


def test_unknown_special_code_is_flagged_and_low(tmp_path):
    def fn(doc):
        text_at(doc.modelspace(), "x%%176y", "Arial")

    e = only(index(build(tmp_path, fn)), entity_type="TEXT")
    assert e["display_text"] == "x%%176y" and "unknown_special_code" in e["flags"]
    assert e["confidence"] == "low"


def test_mtext_inline_font_switch_between_unicode_and_tcvn3(tmp_path):
    raw = "Arial ạ {\\f.VnTime|b0|i0|c0|p34;m" + A_DOT_BREVE_TCVN3 + "t} end%%c5"

    def fn(doc):
        doc.modelspace().add_mtext(raw, dxfattribs={"style": "Arial", "char_height": 2.5})

    e = only(index(build(tmp_path, fn)), entity_type="MTEXT")
    assert e["decoded_text"] == "Arial ạ mặt end%%c5"
    assert e["display_text"] == "Arial ạ mặt endØ5"
    d = e["decode"]
    assert d["runs"] == 3 and d["mixed_fonts"] is True
    assert [r["encoding"] for r in d["run_details"]] == ["unicode", "tcvn3", "unicode"]
    assert [r["font_source"] for r in d["run_details"]] == ["style_font", "mtext_inline_font", "style_font"]
    assert (d["encoding_used"], d["source"]) == ("mixed", "mtext_inline_font")
    assert e["confidence"] == "medium" and "mixed_fonts" in e["flags"]


def test_mtext_legacy_style_with_unicode_inline_font(tmp_path):
    raw = "m" + A_DOT_BREVE_TCVN3 + "t {\\fArial|c0;m" + A_DOT_BREVE_TCVN3 + "t}"

    def fn(doc):
        doc.modelspace().add_mtext(raw, dxfattribs={"style": ".VnTime", "char_height": 2.5})

    e = only(index(build(tmp_path, fn)), entity_type="MTEXT")
    assert e["decoded_text"] == "mặt m" + A_DOT_BREVE_TCVN3 + "t"  # the Arial run is Unicode: kept as stored
    assert [r["encoding"] for r in e["decode"]["run_details"]] == ["tcvn3", "unicode"]


def test_font_unknown_never_converts_and_lowers_confidence(tmp_path):
    def fn(doc):
        msp = doc.modelspace()
        text_at(msp, "m" + A_DOT_BREVE_TCVN3 + "t", "VntimeH", insert=(0, 0))  # shx font, no dot: unknown
        text_at(msp, "T1 200", "Simplex", insert=(0, 9))
        text_at(msp, "abc", "VntimeH", insert=(0, 18))

    result = index(build(tmp_path, fn))
    bytes_ = only(result, raw_text="m" + A_DOT_BREVE_TCVN3 + "t")
    assert bytes_["decode"]["encoding_used"] == "unknown" and bytes_["decoded_text"] == bytes_["raw_text"]
    assert "encoding_unknown_non_ascii" in bytes_["flags"] and bytes_["confidence"] == "low"
    ascii_ = only(result, raw_text="T1 200")
    assert ascii_["decode"]["encoding_used"] == "unknown" and ascii_["confidence"] == "medium"
    assert only(result, raw_text="abc")["confidence"] == "low"  # a capital-font style: case is a guess
    assert result["summary"]["unknown_or_mixed_encoding_by_style"]["top"][0] == {
        "name": "VntimeH",
        "count": 2,
    }


def test_unicode_font_can_be_high_but_the_converter_cap_applies(tmp_path):
    def fn(doc):
        text_at(doc.modelspace(), "mặt", "Arial")

    path = build(tmp_path, fn)
    assert only(index(path), entity_type="TEXT")["confidence"] == "high"
    assert only(index(path, converter="oda"), entity_type="TEXT")["confidence"] == "high"
    capped = index(path, converter="libredwg")
    assert only(capped, entity_type="TEXT")["confidence"] == "medium"
    assert capped["file"]["confidence_cap"] == "medium"


def test_nfd_damaged_legacy_text_is_low(tmp_path):
    def fn(doc):
        # 'a' + U+0302: decomposed upstream. U+0302 is not one of the five tone marks that prove Unicode,
        # so it still means "damaged legacy text" (a tone mark would now be evidence of Unicode instead).
        text_at(doc.modelspace(), "a\u0302", ".VnTime")

    e = only(index(build(tmp_path, fn)), entity_type="TEXT")
    assert e["decode"]["nfd_damaged"] is True and e["confidence"] == "low"


def test_other_code_page_is_reencoded_before_conversion(tmp_path):
    doc = new("R2000", setup=False)
    doc.styles.add(".VnTime", font="vntime.ttf")
    doc.header["$DWGCODEPAGE"] = "ANSI_1258"
    doc.encoding = "cp1258"
    raw_bytes = b"m\xc6t \xb5"
    doc.modelspace().add_text(
        raw_bytes.decode("cp1258"), dxfattribs={"style": ".VnTime", "height": 2.5, "insert": (0, 0)}
    )
    path = save(tmp_path, doc)
    result = index(path)
    e = only(result, entity_type="TEXT")
    assert result["file"]["codepage"] == "cp1258"
    assert e["decoded_text"] == "mặt à"
    assert any("code page" in w for w in result["warnings"])


# --- Unicode evidence from code points ---------------------------------------------------


def test_vietnamese_unicode_letters_prove_unicode_whatever_the_font(tmp_path):
    def fn(doc):
        msp = doc.modelspace()
        text_at(msp, "Ký hiệu bản vẽ", "Simplex", insert=(0, 0))  # unknown font
        text_at(msp, "Ký hiệu bản vẽ", "VntimeH", insert=(0, 9))  # shx name with a capital hint, no encoding
        text_at(msp, "ĐỊNH VỊ", "Standard", insert=(0, 18))

    result = index(build(tmp_path, fn))
    for e in result["entries"]:
        d = e["decode"]
        assert (d["encoding_used"], d["source"]) == ("unicode", "codepoint_evidence")
        assert e["decoded_text"] == e["raw_text"]
        assert e["confidence"] == "medium"  # not high: the font is unknown
        assert "encoding_unknown_non_ascii" not in e["flags"]
        assert "unicode_evidence_contradicts_font" not in e["flags"]
        assert d["case_uncertain"] is False and d["capital_font"] is None
        assert [r["font_source"] for r in d["run_details"]] == ["codepoint_evidence"]
    assert result["summary"]["by_encoding_used"] == {"unicode": 3}


def test_unicode_in_a_legacy_font_style_is_not_converted_and_is_flagged(tmp_path):
    def fn(doc):
        text_at(doc.modelspace(), "m\u1eb7t " + A_GRAVE_TCVN3, ".VnTime")

    e = only(index(build(tmp_path, fn)), entity_type="TEXT")
    assert e["decode"]["encoding_used"] == "unicode" and e["decode"]["source"] == "codepoint_evidence"
    assert e["decoded_text"] == "m\u1eb7t " + A_GRAVE_TCVN3  # the byte-like character is left as stored
    assert "unicode_evidence_contradicts_font" in e["flags"] and e["confidence"] == "medium"


def test_a_tone_mark_alone_is_evidence(tmp_path):
    def fn(doc):
        text_at(doc.modelspace(), "a\u0301", "Simplex")

    e = only(index(build(tmp_path, fn)), entity_type="TEXT")
    assert e["decode"]["source"] == "codepoint_evidence" and e["decode"]["nfd_damaged"] is False


def test_a_known_unicode_font_keeps_its_own_source_and_confidence(tmp_path):
    def fn(doc):
        text_at(doc.modelspace(), "Ký hiệu", "Arial")

    e = only(index(build(tmp_path, fn)), entity_type="TEXT")
    assert (e["decode"]["encoding_used"], e["decode"]["source"]) == ("unicode", "style_font")
    assert e["confidence"] == "high" and "unicode_evidence_contradicts_font" not in e["flags"]


def test_legacy_bytes_without_evidence_are_still_converted(tmp_path):
    def fn(doc):
        text_at(doc.modelspace(), "m" + A_DOT_BREVE_TCVN3 + "t", ".VnTime")
        text_at(doc.modelspace(), "m" + A_DOT_BREVE_TCVN3 + "t", "Simplex", insert=(0, 9))

    result = index(build(tmp_path, fn))
    assert only(result, style=".VnTime")["decoded_text"] == "mặt"
    assert only(result, style="Simplex")["decode"]["encoding_used"] == "unknown"


def test_evidence_is_judged_per_run_in_an_mtext(tmp_path):
    raw = "{\\f.VnTime|c0;m" + A_DOT_BREVE_TCVN3 + "t} \u1ea1"

    def fn(doc):
        doc.modelspace().add_mtext(raw, dxfattribs={"style": "Simplex", "char_height": 2.5})

    e = only(index(build(tmp_path, fn)), entity_type="MTEXT")
    assert e["decoded_text"] == "mặt \u1ea1"
    d = e["decode"]
    assert [r["encoding"] for r in d["run_details"]] == ["tcvn3", "unicode"]
    assert [r["font_source"] for r in d["run_details"]] == ["mtext_inline_font", "codepoint_evidence"]
    assert (d["encoding_used"], d["source"]) == ("mixed", "codepoint_evidence")


def test_cp1258_decoding_of_tcvn3_bytes_is_not_mistaken_for_unicode(tmp_path):
    # In a cp1258 file ezdxf turns the TCVN3 byte 0xD0 into U+0110 (D-stroke): that is the code page's
    # view of a legacy byte, not Unicode text. Evidence is judged on the re-encoded bytes.
    doc = new("R2000", setup=False)
    doc.styles.add(".VnTime", font="vntime.ttf")
    doc.header["$DWGCODEPAGE"] = "ANSI_1258"
    doc.encoding = "cp1258"
    raw = b"m\xd0n".decode("cp1258")
    assert "\u0110" in raw
    doc.modelspace().add_text(raw, dxfattribs={"style": ".VnTime", "height": 2.5, "insert": (0, 0)})
    e = only(index(save(tmp_path, doc)), entity_type="TEXT")
    assert e["decode"]["encoding_used"] == "tcvn3" and e["decode"]["source"] == "style_font"
    assert e["decoded_text"] == "m\u00e9n"  # TCVN3 0xD0 is e-acute


def test_a_letter_the_code_page_cannot_hold_is_unicode_even_in_a_cp1258_file(tmp_path):
    doc = new("R2000", setup=False)
    doc.styles.add(".VnTime", font="vntime.ttf")
    doc.header["$DWGCODEPAGE"] = "ANSI_1258"
    doc.encoding = "cp1258"
    doc.modelspace().add_text(
        "m\\U+1EA1t", dxfattribs={"style": ".VnTime", "height": 2.5, "insert": (0, 0)}
    )  # an escape: cp1258 has no precomposed a-dot-below
    e = only(index(save(tmp_path, doc)), entity_type="TEXT")
    assert e["decoded_text"] == "m\u1ea1t" and e["decode"]["source"] == "codepoint_evidence"


def test_eth_in_vietnamese_unicode_is_flagged_never_replaced(tmp_path):
    def fn(doc):
        msp = doc.modelspace()
        text_at(msp, "\u00d0\u01b0\u1eddng", "Arial", insert=(0, 0))  # Eth + Vietnamese letters
        text_at(msp, "\u00d0\u01b0\u1eddng", "Simplex", insert=(0, 9))
        text_at(msp, "\u00d0 only", "Arial", insert=(0, 18))  # no Vietnamese letter: nothing to say
        text_at(msp, "D\u00d0", ".VnTime", insert=(0, 27))  # legacy byte 0xD0 (e-acute in TCVN3)

    result = index(build(tmp_path, fn))
    for style in ("Arial", "Simplex"):
        e = only(result, style=style, raw_text="\u00d0\u01b0\u1eddng")
        assert "eth_for_d_stroke" in e["flags"]
        assert e["decoded_text"] == "\u00d0\u01b0\u1eddng"  # not replaced with U+0110
    assert "eth_for_d_stroke" not in only(result, raw_text="\u00d0 only")["flags"]
    legacy = only(result, style=".VnTime")
    assert "eth_for_d_stroke" not in legacy["flags"] and legacy["decoded_text"] == "D\u00e9"


# --- knowledge table (ADR-0006 layer 2) -------------------------------------------------------


def knowledge_fixture(doc):
    doc.styles.add("kt..1", font="VHARIAL.TTF")
    text_at(doc.modelspace(), "m" + A_DOT_BREVE_TCVN3 + "t", "kt..1")


def test_an_approved_row_decodes_with_provenance(tmp_path):
    table = table_of(tmp_path, approved(pattern="VH*.TTF", capital_font="false"))
    e = only(index(build(tmp_path, knowledge_fixture), knowledge=table), entity_type="TEXT")
    d = e["decode"]
    assert (d["encoding_used"], d["source"]) == ("tcvn3", "knowledge_table")
    assert d["knowledge_patterns"] == ["VH*.TTF"]
    assert d["run_details"][0]["font_source"] == "knowledge_table"
    assert d["run_details"][0]["knowledge_pattern"] == "VH*.TTF"
    assert d["capital_font"] is False
    assert e["decoded_text"] == "mặt" and e["confidence"] == "medium"
    assert "proposed_knowledge_row" not in e["flags"]


def test_a_proposed_row_does_not_decode_but_is_flagged_and_reported(tmp_path):
    table = table_of(tmp_path, row(pattern="VH*.TTF", evidence="seen"))
    result = index(build(tmp_path, knowledge_fixture), knowledge=table)
    e = only(result, entity_type="TEXT")
    assert e["decode"]["encoding_used"] == "unknown" and e["decoded_text"] == e["raw_text"]
    assert e["decode"]["knowledge_patterns"] == []
    assert "proposed_knowledge_row" in e["flags"] and "encoding_unknown_non_ascii" in e["flags"]
    assert e["confidence"] == "low"
    (warning,) = [w for w in result["warnings"] if "PROPOSED knowledge row" in w]
    assert "VH*.TTF" in warning and "kt..1" in warning and "1 entr" in warning


def test_a_positive_font_hint_is_never_overridden_by_the_table(tmp_path):
    table = table_of(
        tmp_path,
        approved(pattern="*.ttf", encoding="unicode"),
        approved(pattern=".Vn*", applies_to="style_name", encoding="vni"),
    )

    def fn(doc):
        text_at(doc.modelspace(), "m" + A_DOT_BREVE_TCVN3 + "t", ".VnTime")

    e = only(index(build(tmp_path, fn), knowledge=table), entity_type="TEXT")
    assert (e["decode"]["encoding_used"], e["decode"]["source"]) == ("tcvn3", "style_font")
    assert e["decoded_text"] == "mặt" and e["decode"]["knowledge_patterns"] == []


def test_the_name_capital_hint_wins_over_a_row(tmp_path):
    table = table_of(tmp_path, approved(pattern="vntimeh.shx", capital_font="false"))

    def fn(doc):
        text_at(doc.modelspace(), "T" + A_GRAVE_TCVN3, "VntimeH")  # style name says capital font

    e = only(index(build(tmp_path, fn), knowledge=table), entity_type="TEXT")
    assert e["decode"]["capital_font"] is True and e["decoded_text"] == "T\u00c0"


def test_conflicting_approved_rows_decode_nothing_and_flag(tmp_path):
    table = table_of(tmp_path, approved(pattern="VH*.TTF"), approved(pattern="*ARIAL.TTF", encoding="vni"))
    e = only(index(build(tmp_path, knowledge_fixture), knowledge=table), entity_type="TEXT")
    assert e["decode"]["encoding_used"] == "unknown" and "knowledge_conflict" in e["flags"]
    assert e["decoded_text"] == e["raw_text"] and e["confidence"] == "low"


def test_rows_do_not_apply_to_inline_mtext_fonts(tmp_path):
    table = table_of(tmp_path, approved(pattern="VHARIAL.TTF"))

    def fn(doc):
        doc.modelspace().add_mtext(
            "{\\fVHARIAL.TTF|c0;m" + A_DOT_BREVE_TCVN3 + "t}",
            dxfattribs={"style": "Simplex", "char_height": 2.5},
        )

    e = only(index(build(tmp_path, fn), knowledge=table), entity_type="MTEXT")
    assert e["decode"]["encoding_used"] == "unknown" and "inline_font_unknown" in e["flags"]


def test_the_shipped_table_is_the_default(tmp_path):
    path = build(tmp_path, lambda doc: text_at(doc.modelspace(), "T1", "VntimeH"))
    result = extract_text(path)  # no knowledge argument
    assert validate("text-index", result) == []
    decode = result["entries"][0]["decode"]  # vntimeh.shx: approved TCVN3 row (engineer, 2026-11-07)
    assert (decode["encoding_used"], decode["source"]) == ("tcvn3", "knowledge_table")
    assert decode["knowledge_patterns"] == ["vntimeh.shx"]


def test_a_bad_default_table_raises(tmp_path, monkeypatch):
    def boom():
        raise KnowledgeError("table is malformed")

    monkeypatch.setattr(mod, "default_font_encodings", boom)
    with pytest.raises(KnowledgeError, match="malformed"):
        extract_text(build(tmp_path))


# --- TrueType family of the text style (tool wave 2, fix 2a) -------------------------------------


def family_style(doc, name: str, font: str, family: str | None) -> None:
    style = doc.styles.add(name, font=font)
    if family is not None:
        style.set_extended_font_data(family)


def test_the_ttf_family_decides_when_the_name_and_the_file_say_nothing(tmp_path):
    def fn(doc):
        family_style(doc, "kt..1", "VHAVAN_2.TTF", ".VnAvantH")
        text_at(doc.modelspace(), "M" + A_DOT_BREVE_TCVN3 + "T", "kt..1")

    e = only(index(build(tmp_path, fn)), entity_type="TEXT")
    d = e["decode"]
    assert (d["encoding_used"], d["source"]) == ("tcvn3", "style_family")
    assert d["run_details"][0]["font_source"] == "style_family" and d["capital_font"] is True
    assert e["decoded_text"] == "MẶT" and e["confidence"] == "medium"
    assert "encoding_unknown_non_ascii" not in e["flags"]


def test_an_mtext_whose_style_runs_are_decided_by_the_family_has_that_source(tmp_path):
    def fn(doc):
        family_style(doc, "kt..1", "VHAVAN_2.TTF", ".VnArial")
        doc.modelspace().add_mtext("m" + A_DOT_BREVE_TCVN3 + "t", dxfattribs={"style": "kt..1"})

    d = only(index(build(tmp_path, fn)), entity_type="MTEXT")["decode"]
    assert (d["encoding_used"], d["source"], d["capital_font"]) == ("tcvn3", "style_family", False)


def test_styles_without_a_usable_family_are_not_decoded_by_it(tmp_path):
    def fn(doc):
        family_style(doc, "noxdata", "VHAVAN_2.TTF", None)  # no ACAD XDATA at all
        family_style(doc, "empty", "VHAVAN_2.TTF", "")
        # ACAD XDATA with the family tag only: ezdxf's get_extended_font_data needs the 1071 flags tag
        # too and returns '' (ezdxf 1.4.5), so such a family is not read
        doc.styles.add("onetag", font="VHAVAN_2.TTF").set_xdata("ACAD", [(1000, ".VnAvantH")])
        msp = doc.modelspace()
        for i, style in enumerate(("noxdata", "empty", "onetag")):
            text_at(msp, "m" + A_DOT_BREVE_TCVN3 + "t", style, insert=(0, 9 * i))

    for e in index(build(tmp_path, fn))["entries"]:
        assert e["decode"]["encoding_used"] == "unknown", e["style"]
        assert "encoding_unknown_non_ascii" in e["flags"]


def test_a_unicode_family_never_overrides_an_approved_font_row(tmp_path):
    table = table_of(tmp_path, approved(pattern="VHARIAL.TTF"))

    def fn(doc):
        family_style(doc, "kt..1", "VHARIAL.TTF", "Arial")
        text_at(doc.modelspace(), "m" + A_DOT_BREVE_TCVN3 + "t", "kt..1")

    e = only(index(build(tmp_path, fn), knowledge=table), entity_type="TEXT")
    assert (e["decode"]["encoding_used"], e["decode"]["source"]) == ("tcvn3", "knowledge_table")
    assert e["decoded_text"] == "mặt"


def test_a_legacy_family_comes_before_the_knowledge_table(tmp_path):
    table = table_of(tmp_path, approved(pattern="VHAVAN_2.TTF", encoding="vni"))

    def fn(doc):
        family_style(doc, "kt..1", "VHAVAN_2.TTF", ".VnAvant")
        text_at(doc.modelspace(), "m" + A_DOT_BREVE_TCVN3 + "t", "kt..1")

    e = only(index(build(tmp_path, fn), knowledge=table), entity_type="TEXT")
    assert (e["decode"]["encoding_used"], e["decode"]["source"]) == ("tcvn3", "style_family")
    assert e["decode"]["knowledge_patterns"] == []


# --- ASCII text that looks like legacy Vietnamese (tool wave 2, fix 2b; default D2) -------------------

# Shapes seen in EVAL-2 (dwgshare 267 / 461, ASCII-only entries in legacy-font styles): a slash before a
# letter or brace ('4/g14', 'BT LO/ST #100'), and an uppercase tone letter S F R X J after a vowel
# ('chi tiESt kim thu seSt', 'haFn 200'). Invented strings of the same shapes are used here.
SUSPECT = ["4/g14", "/G10", "1/G16", "BT LO/ST #100", "3 L/}/{/SI %%c6", "chi tiESt kim thu seSt", "haFn 200",
           "coJC vaF", "DiJa", "tieRp", "keXt"]  # fmt: skip
# Structural ASCII that must stay readable: grid labels, marks, levels, dimensions, rebar callouts, units.
CLEAN = ["A", "Z", "D1", "C2", "+3.850", "4500", "%%c8a150", "4%%c16", "1/2", "%%c10a200/150",
         "D1.11(220X450)", "CB300-V", "S355JR", "HEA 300", "Rb = 115 kG/cm2", "q = 2 T/m2", "2800Kg/M2",
         "MPa", "kN/m", "M20", "d1", "Q235B", "2L65x8", "TB-01", "GHI CHU", "cU/pvc/pvc 2X4 e1,5",
         "Cu/XLPE/PVC 2(1X16)", "ROOF", "BASE PLATE", "CASE A"]  # fmt: skip


def suspect_fixture(style: str, *, sibling: str | None = None):
    def fn(doc):
        doc.styles.add("Plain", font="plain.shx")
        msp = doc.modelspace()
        for i, text in enumerate(SUSPECT + CLEAN):
            text_at(msp, text, style, insert=(0, 9 * i))
        if sibling is not None:
            text_at(msp, sibling, style, insert=(500, 0))

    return fn


def flagged(result: dict[str, Any]) -> dict[str, bool]:
    ascii_entries = (e for e in result["entries"] if e["raw_text"].isascii())
    return {e["raw_text"]: "legacy_ascii_suspect" in e["flags"] for e in ascii_entries}


@pytest.mark.parametrize("style", [".VnTime", "VNI-Times"])
def test_suspect_ascii_in_a_legacy_style_is_flagged_and_structural_ascii_is_not(tmp_path, style):
    result = index(build(tmp_path, suspect_fixture(style)))
    got = flagged(result)
    assert {t for t in SUSPECT if not got[t]} == set()
    assert {t for t in CLEAN if got[t]} == set()
    assert all(only(result, raw_text=t)["confidence"] == "low" for t in SUSPECT)


def test_an_approved_row_makes_a_legacy_style_too(tmp_path):
    table = table_of(tmp_path, approved(pattern="plain.shx"))
    got = flagged(index(build(tmp_path, suspect_fixture("Plain")), knowledge=table))
    assert all(got[t] for t in SUSPECT) and not any(got[t] for t in CLEAN)


def test_an_unknown_style_counts_only_with_a_non_ascii_sibling_of_unknown_encoding(tmp_path):
    with_sibling = flagged(index(build(tmp_path, suspect_fixture("Plain", sibling="/D\xc2/FU COC"))))
    assert all(with_sibling[t] for t in SUSPECT) and not any(with_sibling[t] for t in CLEAN)
    alone = flagged(index(build(tmp_path, suspect_fixture("Plain"), name="alone.dxf")))
    assert not any(alone.values())
    # a sibling proved Unicode by its code points is no evidence of a legacy font
    unicode_fixture = suspect_fixture("Plain", sibling="Ký hiệu")
    assert not any(flagged(index(build(tmp_path, unicode_fixture, name="u.dxf"))).values())


def test_a_unicode_style_is_never_suspect(tmp_path):
    got = flagged(index(build(tmp_path, suspect_fixture("Arial", sibling="b\xb6n v\xcf"))))
    assert not any(got.values())


def test_a_run_proved_unicode_is_not_suspect_even_in_a_suspect_style(tmp_path):
    # the '\\U+1EA1' escape is ASCII as stored but proves the run Unicode: its ASCII is plain ASCII
    def fn(doc):
        doc.styles.add("Plain", font="plain.shx")
        text_at(doc.modelspace(), "/D\xc2/FU COC", "Plain")  # a non-ASCII sibling of unknown encoding
        text_at(doc.modelspace(), "4/g14%%c\\U+1EA1", "Plain", insert=(0, 9))
        text_at(doc.modelspace(), "4/g14%%c", "Plain", insert=(0, 18))

    got = flagged(index(build(tmp_path, fn)))
    assert got == {"4/g14%%c\\U+1EA1": False, "4/g14%%c": True}


def test_a_sibling_in_another_style_does_not_count(tmp_path):
    def fn(doc):
        doc.styles.add("Plain", font="plain.shx")
        doc.styles.add("Other", font="other.shx")
        text_at(doc.modelspace(), "4/g14", "Plain")
        text_at(doc.modelspace(), "/D\xc2/FU COC", "Other", insert=(0, 9))
        text_at(doc.modelspace(), "1/G16", "Other", insert=(0, 18))

    got = flagged(index(build(tmp_path, fn)))
    assert got == {"4/g14": False, "1/G16": True}


def test_a_sibling_inside_a_block_counts(tmp_path):
    def fn(doc):
        doc.styles.add("Plain", font="plain.shx")
        blk = doc.blocks.new("NOTE")
        blk.add_text("/D\xc2/FU COC", dxfattribs={"style": "Plain", "height": 2.5})
        doc.modelspace().add_blockref("NOTE", (0, 50))
        text_at(doc.modelspace(), "4/g14", "Plain")

    assert flagged(index(build(tmp_path, fn))) == {"4/g14": True}


def test_mixed_mtext_runs_are_judged_run_by_run(tmp_path):
    def fn(doc):
        msp = doc.modelspace()
        # the suspect text sits in the legacy inline-font run: flagged
        msp.add_mtext("{\\f.VnTime|c0;4/g14} 4500", dxfattribs={"style": "Arial", "insert": (0, 0)})
        # the suspect text sits in the Unicode inline-font run of a legacy style: not flagged
        msp.add_mtext("{\\fArial|c0;4/g14} D1", dxfattribs={"style": ".VnTime", "insert": (0, 50)})
        # formatting codes and %% codes are not text: '\\P' and '%%c' never match
        msp.add_mtext("D1\\PC2 %%c16", dxfattribs={"style": ".VnTime", "insert": (0, 100)})

    result = index(build(tmp_path, fn))
    assert flagged(result) == {
        "{\\f.VnTime|c0;4/g14} 4500": True,
        "{\\fArial|c0;4/g14} D1": False,
        "D1\\PC2 %%c16": False,
    }


def test_special_codes_are_not_text_for_the_suspect_shapes(tmp_path):
    # 'a%%dS1': the code between 'a' and 'S' must not join them into the tone shape 'aS';
    # '%%uSo 1': the 'u' of the underline code is not a vowel of the text
    def fn(doc):
        text_at(doc.modelspace(), "a%%dS1", ".VnTime")
        text_at(doc.modelspace(), "%%uSo 1", ".VnTime", insert=(0, 9))

    assert flagged(index(build(tmp_path, fn))) == {"a%%dS1": False, "%%uSo 1": False}


# --- damaged bytes ------------------------------------------------------------------------------


def damaged_dxf(tmp_path: Path) -> Path:
    """A DXF whose TEXT holds bytes that are not valid UTF-8 (a mis-converted file)."""

    def fn(doc):
        text_at(doc.modelspace(), "ZZZZ ok", "Arial")
        text_at(doc.modelspace(), "clean", "Arial", insert=(0, 9))

    path = build(tmp_path, fn)
    path.write_bytes(path.read_bytes().replace(b"ZZZZ", b"b\xff\xfe"))
    return path


def test_undecodable_bytes_are_flagged_scrubbed_and_the_index_is_still_writable(tmp_path):
    result = index(damaged_dxf(tmp_path))
    bad = only(result, style="Arial", layer="0", handle=result["entries"][0]["handle"])
    assert "invalid_utf8_bytes" in bad["flags"] and bad["confidence"] == "low"
    assert "\ufffd" in bad["raw_text"] and "\ufffd" in bad["display_text"]
    assert (
        "invalid_utf8_bytes" not in result["entries"][1]["flags"]
        and result["entries"][1]["confidence"] == "high"
    )
    assert any("not valid UTF-8" in w for w in result["warnings"])
    json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")  # a surrogate would raise here


def test_cli_extract_text_writes_a_damaged_file(tmp_path, capsys):
    out = tmp_path / "t.json"
    assert main(["extract-text", str(damaged_dxf(tmp_path)), "--out", str(out)]) == 0
    capsys.readouterr()
    assert "\ufffd" in out.read_text(encoding="utf-8")


# --- file level -----------------------------------------------------------------------


def make_r12(tmp_path: Path, *, strip_handles: bool) -> Path:
    doc = new("R12", setup=False)
    doc.modelspace().add_text("R12 TEXT", dxfattribs={"height": 2.5, "insert": (1, 2)})
    path = save(tmp_path, doc, "r12.dxf")
    if strip_handles:
        text = path.read_text(encoding="utf-8")
        head, tables = text.split("SECTION\n  2\nTABLES", 1)  # the header's $HANDSEED also uses group 5
        text = head + "SECTION\n  2\nTABLES" + re.sub(r"(?m)^  5\n[0-9A-Fa-f]+\n", "", tables)
        text, n = re.subn(r"\$HANDLING\n\s*70\n\s*\d+\n", "$HANDLING\n 70\n     0\n", text)
        assert n == 1
        path.write_text(text, encoding="utf-8")
    return path


def test_r12_without_handles_gives_null_handles(tmp_path):
    result = index(make_r12(tmp_path, strip_handles=True))
    assert result["file"]["handles_reliable"] is False and result["file"]["dxf_version"] == "AC1009"
    assert only(result, entity_type="TEXT")["handle"] is None
    assert any("handles" in w for w in result["warnings"])


def test_r12_with_real_handles_keeps_them(tmp_path):
    result = index(make_r12(tmp_path, strip_handles=False))
    assert result["file"]["handles_reliable"] is True
    assert only(result, entity_type="TEXT")["handle"]


def test_a_failing_entity_gives_partial_and_a_listed_error(tmp_path, monkeypatch):
    def fn(doc):
        msp = doc.modelspace()
        text_at(msp, "fine one", "Arial", insert=(0, 0))
        text_at(msp, "BOOM", "Arial", insert=(0, 9))
        text_at(msp, "fine two", "Arial", insert=(0, 18))

    path = build(tmp_path, fn)
    original = mod._decode_text  # pyright: ignore[reportPrivateUsage]

    def boom(ctx, raw, *args, **kwargs):
        if raw == "BOOM":
            raise RuntimeError("synthetic failure")
        return original(ctx, raw, *args, **kwargs)

    monkeypatch.setattr(mod, "_decode_text", boom)
    result = index(path, status="partial")
    assert [e["raw_text"] for e in result["entries"]] == ["fine one", "fine two"]
    (error,) = result["summary"]["errors"]
    assert error["entity_type"] == "TEXT" and error["handle"] and "synthetic failure" in error["error"]
    assert result["summary"]["errors_total"] == 1


def test_unreadable_file_is_reported_not_raised(tmp_path):
    bad = tmp_path / "bad.dxf"
    bad.write_bytes(b"this is not a dxf")
    result = index(bad, status="unreadable")
    assert result["error"] and "entries" not in result


def test_unknown_converter_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="converter"):
        extract_text(build(tmp_path), converter="magic")


def test_output_is_deterministic(tmp_path):
    def fn(doc):
        doc.blocks.new("B").add_text("b", dxfattribs={"insert": (0, 0), "height": 1, "style": "Arial"})
        msp = doc.modelspace()
        for i in range(5):
            msp.add_blockref("B", (i, 0))
            text_at(msp, f"t{i}", "Arial", insert=(i, 5))

    path = build(tmp_path, fn)
    a, b = extract_text(path), extract_text(path)
    assert a["entries"] == b["entries"] and a["summary"] == b["summary"]
    assert [e["id"] for e in a["entries"]] == [f"T{i:06d}" for i in range(1, 11)]


def test_summary_counts(tmp_path):
    def fn(doc):
        doc.layers.add("A")
        doc.layers.add("B")
        msp = doc.modelspace()
        text_at(msp, "1", "Arial", layer="A")
        text_at(msp, "2", "Arial", layer="A")
        text_at(msp, "3", ".VnTime", layer="B")
        doc.layout("Layout1").add_text("4", dxfattribs={"style": "Arial", "height": 1, "layer": "A"})

    s = index(build(tmp_path, fn))["summary"]
    assert s["by_layer"]["top"] == [{"name": "A", "count": 3}, {"name": "B", "count": 1}]
    assert s["by_space"]["total_distinct"] == 2
    assert s["by_encoding_used"] == {"tcvn3": 1, "unicode": 3}
    assert s["by_entity_type"] == {"TEXT": 4}


def test_example_is_valid():
    path = REPO / "schemas" / "examples" / "text-index.example.json"
    example = json.loads(path.read_text(encoding="utf-8"))
    assert validate("text-index", example) == []
    assert example["schema_version"] == "0.1"


def test_dxf_unicode_escape_is_decoded_before_anything_else(tmp_path):
    def fn(doc):
        msp = doc.modelspace()
        text_at(msp, "%%UC\\U+1ED8T C1", "Arial", insert=(0, 0))
        text_at(msp, "a\\M+1ABCDb", "Arial", insert=(0, 9))
        doc.modelspace().add_mtext("M\\U+1ED8T", dxfattribs={"style": "Arial", "insert": (0, 20)})

    result = index(build(tmp_path, fn))
    column = only(result, raw_text="%%UC\\U+1ED8T C1")
    assert column["display_text"] == "CỘT C1" and "dxf_unicode_escape_decoded" in column["flags"]
    assert column["confidence"] == "high"
    mif = only(result, raw_text="a\\M+1ABCDb")
    assert "mif_escape_not_decoded" in mif["flags"] and mif["confidence"] == "low"
    assert only(result, entity_type="MTEXT")["plain_text"] == "MỘT"


# --- CLI: harness extract-text ---------------------------------------------------------------


def cli_fixture(tmp_path: Path) -> Path:
    def fn(doc):
        msp = doc.modelspace()
        for i in range(60):  # more entries than a summary should ever print
            text_at(msp, f"NOTE {i}", "Arial", insert=(0, 5 * i))
        text_at(msp, "m" + A_DOT_BREVE_TCVN3 + "t", ".VnTime", insert=(0, 400))

    return build(tmp_path, fn)


def test_cli_extract_text_writes_the_index_and_prints_a_small_summary(tmp_path, capsys):
    path = cli_fixture(tmp_path)
    out = tmp_path / "new-folder" / "text-index.json"  # the parent folder is created
    assert main(["extract-text", str(path), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    summary = json.loads(printed)
    assert len(printed) < 3000 and "entries" in summary and not isinstance(summary["entries"], list)
    assert summary["entries"] == 61 and summary["status"] == "ok" and summary["out"] == str(out)
    assert summary["by_encoding_used"] == {"tcvn3": 1, "unicode": 60}
    index_ = json.loads(out.read_text(encoding="utf-8"))
    assert validate("text-index", index_) == [] and len(index_["entries"]) == 61
    assert index_["file"]["converter"] == "none"


def test_cli_extract_text_converter_option(tmp_path, capsys):
    out = tmp_path / "t.json"
    assert (
        main(["extract-text", str(cli_fixture(tmp_path)), "--out", str(out), "--converter", "libredwg"]) == 0
    )
    capsys.readouterr()
    assert json.loads(out.read_text(encoding="utf-8"))["file"]["converter"] == "libredwg"
    assert main(["extract-text", str(cli_fixture(tmp_path)), "--out", str(out), "--converter", "nope"]) == 2


def test_cli_extract_text_exit_codes(tmp_path, capsys, monkeypatch):
    out = tmp_path / "t.json"
    assert main(["extract-text", str(tmp_path / "missing.dxf"), "--out", str(out)]) == 2  # usage
    assert main(["extract-text", str(cli_fixture(tmp_path))]) == 2  # --out is required
    broken = tmp_path / "broken.dxf"
    broken.write_text("0\nSECTION\n2\nENTITIES\n0\nLINE\n8\n", encoding="utf-8")
    assert main(["extract-text", str(broken), "--out", str(out)]) == 1  # ezdxf cannot open it
    assert json.loads(out.read_text(encoding="utf-8"))["status"] == "unreadable"
    assert "could not open" in capsys.readouterr().err
    assert (
        main(["extract-text", str(cli_fixture(tmp_path)), "--out", str(tmp_path)]) == 3
    )  # --out is a folder


def test_cli_extract_text_with_a_bad_knowledge_table_exits_1_and_writes_nothing(
    tmp_path, capsys, monkeypatch
):
    def boom():
        raise KnowledgeError("table is malformed")

    monkeypatch.setattr(mod, "default_font_encodings", boom)
    out = tmp_path / "t.json"
    assert main(["extract-text", str(cli_fixture(tmp_path)), "--out", str(out)]) == 1
    assert not out.exists() and "malformed" in capsys.readouterr().err


def test_cli_read_dxf_with_a_bad_knowledge_table_exits_1(tmp_path, capsys, monkeypatch):
    def boom():
        raise KnowledgeError("table is malformed")

    monkeypatch.setattr(read_dxf, "default_font_encodings", boom)
    assert main(["read-dxf", str(cli_fixture(tmp_path))]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "malformed" in captured.err


# --- corpus smoke test: opt-in only (parses untrusted personal files, slow) ------

SAMPLES = REPO / "dwg-lab" / "samples"
CORPUS = sorted(SAMPLES.rglob("*.dxf")) if SAMPLES.is_dir() else []
needs_corpus = pytest.mark.skipif(
    not (os.environ.get("HARNESS_CORPUS_TESTS") == "1" and CORPUS),
    reason="set HARNESS_CORPUS_TESTS=1 with dwg-lab/samples present",
)


@needs_corpus
def test_corpus_text_index_is_schema_valid_and_has_no_errors():
    for path in CORPUS:
        result = extract_text(path)
        assert validate("text-index", result) == [], path.name
        json.dumps(result, allow_nan=False)
        assert result["status"] in ("ok", "unreadable"), (path.name, result["summary"]["errors"][:2])
