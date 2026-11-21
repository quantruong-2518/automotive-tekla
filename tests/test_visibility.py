"""Tool wave 4, seam: the visibility helper every producer asks whether an entry prints."""

from __future__ import annotations

from types import MappingProxyType

from tekla_harness.visibility import is_printed, not_printed_reasons


def test_absent_printed_field_counts_as_printed():
    assert is_printed({}) is True
    assert is_printed({"id": "T000001"}) is True


def test_only_an_explicit_false_is_not_printed():
    assert is_printed({"printed": False}) is False
    assert is_printed({"printed": True}) is True
    for odd in (None, 0, "", "false", []):  # never a truthiness guess
        assert is_printed({"printed": odd}) is True


def test_not_printed_reasons_returns_a_copy_and_defaults_to_empty():
    assert not_printed_reasons({}) == []
    entry = {"printed": False, "not_printed_reasons": ["layer_off", "entity_invisible"]}
    got = not_printed_reasons(entry)
    assert got == ["layer_off", "entity_invisible"]
    got.append("x")
    assert entry["not_printed_reasons"] == ["layer_off", "entity_invisible"]
    assert not_printed_reasons({"not_printed_reasons": None}) == []


def test_helper_accepts_any_mapping():
    assert is_printed(MappingProxyType({"printed": False})) is False
    assert not_printed_reasons(MappingProxyType({"not_printed_reasons": ["layer_frozen"]})) == [
        "layer_frozen"
    ]
