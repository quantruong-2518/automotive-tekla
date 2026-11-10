"""Tool wave 4, package T, V1: `printed`, `not_printed_reasons`, `print_uncertain_reasons` on each entry.

Rule (docs/research/dxf-invisible-text.md section 8): group 60 on the entity, ATTRIB/ATTDEF flag bit 1 and
the effective layer being off, frozen or plot 0 keep an entry off the printed sheet; an INSERT's group 60
over its content, `$ATTMODE` != 1, a layer frozen in a viewport and `Defpoints` are only uncertain (the entry
stays printed). Fixtures are built with ezdxf inside tmp_path; no sample drawing text is used.
"""

from __future__ import annotations

from typing import Any

import pytest
from ezdxf.math import Vec2
from ezdxf.render.mleader import ConnectionSide

from tekla_harness.visibility import is_printed, not_printed_reasons
from test_extract_text import build, index, only, text_at


def printed_state(e: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
    return e["printed"], e["not_printed_reasons"], e["print_uncertain_reasons"]


# --- hard reasons ---------------------------------------------------------------------


def test_every_entry_carries_the_three_fields_and_a_plain_one_prints(tmp_path):
    def fn(doc):
        text_at(doc.modelspace(), "PLAIN", "Arial")

    e = only(index(build(tmp_path, fn)), entity_type="TEXT")
    assert printed_state(e) == (True, [], [])
    assert is_printed(e) and not_printed_reasons(e) == []


@pytest.mark.parametrize("kind", ["TEXT", "MTEXT"])
def test_group_60_hides_text_and_mtext(tmp_path, kind):
    def fn(doc):
        msp = doc.modelspace()
        if kind == "TEXT":
            text_at(msp, "HIDDEN", "Arial", invisible=1)
            text_at(msp, "SHOWN", "Arial", insert=(0, 9))
        else:
            msp.add_mtext("HIDDEN", dxfattribs={"style": "Arial", "invisible": 1, "insert": (0, 0)})
            msp.add_mtext("SHOWN", dxfattribs={"style": "Arial", "insert": (0, 9)})

    result = index(build(tmp_path, fn))
    assert printed_state(only(result, plain_text="HIDDEN")) == (False, ["entity_invisible"], [])
    assert printed_state(only(result, plain_text="SHOWN")) == (True, [], [])
    assert not is_printed(only(result, plain_text="HIDDEN"))


def test_group_60_hides_an_attrib_apart_from_its_flag_bit(tmp_path):
    # TALLY A1: ATTRIB 9E3F9A has group 60 = 1 and flag bit 1 clear: it was indexed `invisible: false`
    def fn(doc):
        doc.blocks.new("TITLE").add_attdef("T", (0, 0), text="d", dxfattribs={"height": 1})
        ins = doc.modelspace().add_blockref("TITLE", (0, 0)).add_auto_attribs({"T": "stale title"})
        ins.attribs[0].dxf.invisible = 1

    e = only(index(build(tmp_path, fn)), entity_type="ATTRIB")
    assert printed_state(e) == (False, ["entity_invisible"], [])
    assert e["invisible"] is False  # `invisible` stays the flag bit 1 only
    assert e["flags"] == [] or "attribute_invisible" not in e["flags"]


def test_attrib_flag_bit_1_hides_it_and_keeps_its_flag(tmp_path):
    def fn(doc):
        doc.blocks.new("B").add_attdef("T", (0, 0), text="d", dxfattribs={"height": 1})
        ins = doc.modelspace().add_blockref("B", (0, 0)).add_auto_attribs({"T": "secret"})
        ins.attribs[0].dxf.flags = 1

    e = only(index(build(tmp_path, fn)), entity_type="ATTRIB")
    assert printed_state(e) == (False, ["attribute_invisible"], [])
    assert e["invisible"] is True and "attribute_invisible" in e["flags"]


def test_both_attrib_signals_list_both_reasons_in_a_fixed_order(tmp_path):
    def fn(doc):
        doc.layers.add("OLD").off()
        doc.blocks.new("B").add_attdef("T", (0, 0), text="d", dxfattribs={"height": 1})
        ins = doc.modelspace().add_blockref("B", (0, 0)).add_auto_attribs({"T": "secret"})
        ins.attribs[0].dxf.flags = 1
        ins.attribs[0].dxf.invisible = 1
        ins.attribs[0].dxf.layer = "OLD"

    e = only(index(build(tmp_path, fn)), entity_type="ATTRIB")
    assert e["not_printed_reasons"] == ["entity_invisible", "attribute_invisible", "layer_off"]


def test_group_60_hides_a_multileader_and_a_dimension(tmp_path):
    def fn(doc):
        msp = doc.modelspace()
        ml = msp.add_multileader_mtext("Standard")
        ml.set_content("LEAD", style="Arial", char_height=2.5)
        ml.add_leader_line(ConnectionSide.left, [Vec2(0, 0), Vec2(10, 10)])
        ml.build(Vec2(50, 50))
        ml.multileader.dxf.invisible = 1
        dim = msp.add_linear_dim(base=(0, 5), p1=(0, 0), p2=(10, 0), text="OVR")
        dim.render()
        dim.dimension.dxf.invisible = 1
        msp.add_linear_dim(base=(0, 9), p1=(0, 0), p2=(10, 0), text="OVR2").render()

    result = index(build(tmp_path, fn))
    assert printed_state(only(result, entity_type="MULTILEADER")) == (False, ["entity_invisible"], [])
    assert printed_state(only(result, plain_text="OVR")) == (False, ["entity_invisible"], [])
    assert printed_state(only(result, plain_text="OVR2")) == (True, [], [])


def test_a_multileader_block_attribute_follows_the_multileader_group_60(tmp_path):
    def fn(doc):
        blk = doc.blocks.new("BUBBLE")
        blk.add_attdef("MARK", (0, 0), text="?", dxfattribs={"height": 1})
        ml = doc.modelspace().add_multileader_block("Standard")
        ml.set_content("BUBBLE")
        ml.set_attribute("MARK", "A1")
        ml.add_leader_line(ConnectionSide.left, [Vec2(0, 0), Vec2(5, 5)])
        ml.build(Vec2(30, 30))
        ml.multileader.dxf.invisible = 1

    e = only(index(build(tmp_path, fn)), entity_type="MULTILEADER")
    assert printed_state(e) == (False, ["entity_invisible"], [])


@pytest.mark.parametrize(
    ("setup", "reason", "state"),
    [
        (lambda layer: layer.off(), "layer_off", "off"),
        (lambda layer: layer.freeze(), "layer_frozen", "frozen"),
        (lambda layer: setattr(layer.dxf, "plot", 0), "layer_no_plot", "on"),
    ],
)
def test_the_layer_off_frozen_or_not_plotted_hides_the_text(tmp_path, setup, reason, state):
    def fn(doc):
        setup(doc.layers.add("X"))
        text_at(doc.modelspace(), "ON X", "Arial", layer="X")
        text_at(doc.modelspace(), "ON 0", "Arial", insert=(0, 9))

    result = index(build(tmp_path, fn))
    hidden = only(result, plain_text="ON X")
    assert printed_state(hidden) == (False, [reason], [])
    assert hidden["layer_state"] == state
    if reason != "layer_no_plot":
        assert reason in hidden["flags"]  # the existing flag stays as it was
    assert printed_state(only(result, plain_text="ON 0")) == (True, [], [])


def test_a_layer_both_off_and_not_plotted_lists_both(tmp_path):
    def fn(doc):
        layer = doc.layers.add("X")
        layer.off()
        layer.dxf.plot = 0
        text_at(doc.modelspace(), "T", "Arial", layer="X")

    e = only(index(build(tmp_path, fn)), entity_type="TEXT")
    assert e["not_printed_reasons"] == ["layer_off", "layer_no_plot"]


def test_layer_bit_2_frozen_in_new_viewports_is_not_frozen(tmp_path):
    def fn(doc):
        layer = doc.layers.add("X")
        layer.dxf.flags = 2  # "frozen by default in new viewports" (Autodesk LAYER group 70)
        text_at(doc.modelspace(), "T", "Arial", layer="X")

    assert printed_state(only(index(build(tmp_path, fn)), entity_type="TEXT")) == (True, [], [])


def test_a_layer_0_child_takes_the_state_of_the_insert_layer(tmp_path):
    # the effective layer rule the text index already uses (schema: `layer` is the effective layer)
    def fn(doc):
        doc.layers.add("GRID")
        doc.layers.add("OLD").off()
        doc.blocks.new("B").add_text(
            "t", dxfattribs={"insert": (0, 0), "layer": "0", "style": "Arial", "height": 1}
        )
        msp = doc.modelspace()
        msp.add_blockref("B", (0, 0), dxfattribs={"layer": "GRID"})
        msp.add_blockref("B", (0, 9), dxfattribs={"layer": "OLD"})

    rows = index(build(tmp_path, fn))["entries"]
    assert [printed_state(e) for e in rows] == [(True, [], []), (False, ["layer_off"], [])]


def test_a_block_child_with_group_60_is_hidden_through_the_copy(tmp_path):
    def fn(doc):
        doc.blocks.new("B").add_text(
            "inner", dxfattribs={"insert": (0, 0), "style": "Arial", "height": 1, "invisible": 1}
        )
        doc.modelspace().add_blockref("B", (0, 0))

    assert printed_state(only(index(build(tmp_path, fn)), plain_text="inner")) == (
        False,
        ["entity_invisible"],
        [],
    )


# --- uncertain reasons: kept printed --------------------------------------------------


def test_an_invisible_insert_leaves_its_content_printed_but_uncertain(tmp_path):
    def fn(doc):
        doc.blocks.new("B").add_attdef("T", (0, 0), text="d", dxfattribs={"height": 1})
        inner = doc.blocks.new("IN")
        inner.add_text("in-text", dxfattribs={"insert": (0, 0), "style": "Arial", "height": 1})
        inner.add_blockref("B", (1, 1)).add_auto_attribs({"T": "in-attrib"})
        outer = doc.blocks.new("OUT")
        outer.add_blockref("IN", (0, 0))
        msp = doc.modelspace()
        msp.add_blockref("B", (0, 0), dxfattribs={"invisible": 1}).add_auto_attribs({"T": "top-attrib"})
        msp.add_blockref("OUT", (50, 0), dxfattribs={"invisible": 1})
        msp.add_blockref("B", (0, 50)).add_auto_attribs({"T": "shown-attrib"})

    result = index(build(tmp_path, fn))
    for text in ("top-attrib", "in-text", "in-attrib"):
        assert printed_state(only(result, plain_text=text)) == (True, [], ["insert_invisible"]), text
    assert printed_state(only(result, plain_text="shown-attrib")) == (True, [], [])


def test_a_hard_reason_beats_the_uncertain_one(tmp_path):
    def fn(doc):
        doc.blocks.new("B").add_attdef("T", (0, 0), text="d", dxfattribs={"height": 1})
        ins = (
            doc.modelspace()
            .add_blockref("B", (0, 0), dxfattribs={"invisible": 1})
            .add_auto_attribs({"T": "x"})
        )
        ins.attribs[0].dxf.invisible = 1

    e = only(index(build(tmp_path, fn)), entity_type="ATTRIB")
    assert printed_state(e) == (False, ["entity_invisible"], [])


@pytest.mark.parametrize("mode", [0, 2])
def test_attmode_not_normal_makes_every_attribute_uncertain_and_keeps_it_printed(tmp_path, mode):
    def fn(doc):
        doc.header["$ATTMODE"] = mode
        doc.blocks.new("B").add_attdef("T", (0, 0), text="d", dxfattribs={"height": 1})
        msp = doc.modelspace()
        ins = msp.add_blockref("B", (0, 0)).add_auto_attribs({"T": "flagged"})
        ins.attribs[0].dxf.flags = 1  # ATTDISP overrides the invisible mode (Autodesk): not settled
        msp.add_blockref("B", (0, 9)).add_auto_attribs({"T": "plain"})
        text_at(msp, "TEXT", "Arial", insert=(0, 20))

    result = index(build(tmp_path, fn))
    assert printed_state(only(result, plain_text="flagged")) == (True, [], ["attmode_not_normal"])
    assert printed_state(only(result, plain_text="plain")) == (True, [], ["attmode_not_normal"])
    assert printed_state(only(result, plain_text="TEXT")) == (True, [], [])
    assert only(result, plain_text="flagged")["invisible"] is True  # the flag itself is unchanged


def test_attmode_1_or_missing_adds_nothing(tmp_path):
    def fn(doc):
        doc.header["$ATTMODE"] = 1
        doc.blocks.new("B").add_attdef("T", (0, 0), text="d", dxfattribs={"height": 1})
        doc.modelspace().add_blockref("B", (0, 0)).add_auto_attribs({"T": "plain"})

    assert printed_state(only(index(build(tmp_path, fn)), plain_text="plain")) == (True, [], [])


def test_group_60_still_hides_under_attmode_2(tmp_path):
    def fn(doc):
        doc.header["$ATTMODE"] = 2
        doc.blocks.new("B").add_attdef("T", (0, 0), text="d", dxfattribs={"height": 1})
        ins = doc.modelspace().add_blockref("B", (0, 0)).add_auto_attribs({"T": "x"})
        ins.attribs[0].dxf.invisible = 1

    assert printed_state(only(index(build(tmp_path, fn)), entity_type="ATTRIB")) == (
        False,
        ["entity_invisible"],
        [],
    )


@pytest.mark.parametrize("name", ["Defpoints", "DEFPOINTS", "defpoints"])
def test_defpoints_is_uncertain_in_any_case(tmp_path, name):
    # ezdxf sets the plot flag of Defpoints to 0 on every load ("AutoCAD requires a plot flag = 0"), so the
    # file's own value is not visible: the layer name alone is the uncertainty, never layer_no_plot
    def fn(doc):
        text_at(doc.modelspace(), "ON DEF", "Arial", layer=name)

    result = index(build(tmp_path, fn))
    assert printed_state(only(result, entity_type="TEXT")) == (True, [], ["defpoints_layer"])


def test_defpoints_that_is_also_off_is_not_printed(tmp_path):
    def fn(doc):
        doc.layers.get("Defpoints").off()
        text_at(doc.modelspace(), "ON DEF", "Arial", layer="Defpoints")

    assert printed_state(only(index(build(tmp_path, fn)), entity_type="TEXT")) == (False, ["layer_off"], [])


def viewport_fixture(frozen: list[str]):
    def fn(doc):
        doc.layers.add("VPF")
        doc.layers.add("OTHER")
        doc.modelspace().add_text("model vpf", dxfattribs={"layer": "VPF", "style": "Arial", "height": 2})
        doc.modelspace().add_text("model other", dxfattribs={"layer": "OTHER", "style": "Arial", "height": 2})
        layout = doc.layout("Layout1")
        layout.add_text("paper vpf", dxfattribs={"layer": "VPF", "style": "Arial", "height": 2})
        vp = layout.add_viewport(center=(100, 100), size=(80, 60), view_center_point=(0, 0), view_height=50)
        vp.frozen_layers = frozen

    return fn


def test_a_layer_frozen_in_a_viewport_makes_model_space_text_uncertain(tmp_path):
    result = index(build(tmp_path, viewport_fixture(["VPF"])))
    assert printed_state(only(result, plain_text="model vpf")) == (True, [], ["viewport_frozen"])
    assert printed_state(only(result, plain_text="model other")) == (True, [], [])
    # a viewport freeze does not touch the layout's own (paper space) text
    assert printed_state(only(result, plain_text="paper vpf")) == (True, [], [])


def test_no_viewport_freeze_means_no_reason(tmp_path):
    result = index(build(tmp_path, viewport_fixture([])))
    assert all(printed_state(e) == (True, [], []) for e in result["entries"])


def test_viewport_freeze_names_match_case_insensitively(tmp_path):
    result = index(build(tmp_path, viewport_fixture(["vpf"])))
    assert printed_state(only(result, plain_text="model vpf")) == (True, [], ["viewport_frozen"])


def test_a_globally_frozen_layer_is_not_printed_not_merely_uncertain(tmp_path):
    def fn(doc):
        viewport_fixture(["VPF"])(doc)
        doc.layers.get("VPF").freeze()

    result = index(build(tmp_path, fn))
    assert printed_state(only(result, plain_text="model vpf")) == (False, ["layer_frozen"], [])


def test_uncertain_reasons_come_in_a_fixed_order(tmp_path):
    def fn(doc):
        doc.header["$ATTMODE"] = 0
        doc.blocks.new("B").add_attdef("T", (0, 0), text="d", dxfattribs={"height": 1})
        ins = doc.modelspace().add_blockref("B", (0, 0), dxfattribs={"invisible": 1})
        ins.add_auto_attribs({"T": "x"})
        ins.attribs[0].dxf.layer = "Defpoints"

    e = only(index(build(tmp_path, fn)), entity_type="ATTRIB")
    assert e["print_uncertain_reasons"] == ["insert_invisible", "attmode_not_normal", "defpoints_layer"]
