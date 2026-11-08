from __future__ import annotations

from pathlib import Path

import pytest

from tekla_harness.strict_json import MAX_BYTES, StrictJsonError, loads_strict

CORPUS = Path(__file__).parent / "fixtures" / "strict-json"
ACCEPT = sorted((CORPUS / "accept").glob("*.json"))
REJECT = sorted((CORPUS / "reject").glob("*.json"))


def test_corpus_is_discovered():
    assert len(ACCEPT) >= 9 and len(REJECT) >= 40


@pytest.mark.parametrize("path", ACCEPT, ids=lambda p: p.name)
def test_accept_corpus_loads(path):
    loads_strict(path.read_bytes())


@pytest.mark.parametrize("path", REJECT, ids=lambda p: p.name)
def test_reject_corpus_raises(path):
    with pytest.raises(StrictJsonError):
        loads_strict(path.read_bytes())


def test_error_is_a_value_error():
    assert issubclass(StrictJsonError, ValueError)


def test_size_cap():
    ok = b'"' + b"a" * (MAX_BYTES - 2) + b'"'
    assert len(ok) == MAX_BYTES
    assert loads_strict(ok) == "a" * (MAX_BYTES - 2)
    with pytest.raises(StrictJsonError, match="16 MiB"):
        loads_strict(ok + b" ")


def test_depth_64_accepted_65_rejected():
    assert loads_strict(b"[" * 64 + b"]" * 64)
    with pytest.raises(StrictJsonError, match="depth"):
        loads_strict(b"[" * 65 + b"]" * 65)


def test_depth_counts_objects_too():
    deep = b'{"a":' * 64 + b"1" + b"}" * 64
    assert loads_strict(deep)
    with pytest.raises(StrictJsonError, match="depth"):
        loads_strict(b'{"a":' * 65 + b"1" + b"}" * 65)


def test_very_deep_input_is_a_strict_error_not_recursion_error():
    with pytest.raises(StrictJsonError):
        loads_strict(b"[" * 200_000)
    with pytest.raises(StrictJsonError):
        loads_strict(b"[" * 200_000 + b"]" * 200_000)


def test_number_forms():
    values = loads_strict((CORPUS / "accept" / "number_forms.json").read_bytes())
    assert values[0] == 0 and values[1] == 0
    assert values[6] == 2**53 and isinstance(values[6], int)
    assert values[7] == -(2**53) and isinstance(values[7], int)
    assert values[3] == -1.5e10


def test_decoded_values():
    assert loads_strict(b'{"a":1,"A":2}') == {"a": 1, "A": 2}
    assert loads_strict('"đầm"'.encode()) == "đầm"
    assert loads_strict(b'["\\ud83d\\ude00"]') == ["\U0001f600"]


def test_huge_integer_digit_string_rejected():
    with pytest.raises(StrictJsonError):
        loads_strict(b"[" + b"9" * 5000 + b"]")


def test_message_names_the_problem():
    with pytest.raises(StrictJsonError, match="duplicate key 'a'"):
        loads_strict(b'{"a":1,"a":2}')
    with pytest.raises(StrictJsonError, match="BOM"):
        loads_strict(b"\xef\xbb\xbf{}")


# --- value parity with the C# reader (ADR-0010 Amendment 1, review fix M2) ---------------

VALUES = CORPUS / "values"


def test_every_accept_file_has_expected_values():
    assert sorted(p.stem for p in ACCEPT) == sorted(p.stem for p in VALUES.glob("*.txt"))


@pytest.mark.parametrize("path", ACCEPT, ids=lambda p: p.name)
def test_accept_corpus_values_match_canonical_dump(path):
    from strict_json_values import dump

    expected = (VALUES / f"{path.stem}.txt").read_bytes().decode("utf-8")
    assert dump(loads_strict(path.read_bytes())) == expected


def test_dump_distinguishes_negative_zero_and_int():
    from strict_json_values import dump

    assert dump(loads_strict(b"[-0, -0.0, 1, 1.0]")).splitlines() == [
        "array 4",
        "int 0000000000000000",
        "float 8000000000000000",
        "int 3ff0000000000000",
        "float 3ff0000000000000",
    ]
