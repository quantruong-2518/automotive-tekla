"""Content-addressed read cache (ADR-0007): keys, integrity, atomic writes, self-ignoring dir."""

from __future__ import annotations

import hashlib
import json

import pytest

from tekla_harness.cache import CACHEDIR_TAG_SIGNATURE, ReadCache, action_key
from tekla_harness.schemas import validate

MATERIAL = {"action": "demo", "input_sha256": "a" * 64, "tool": {"name": "x", "sha256": "b" * 64}}


@pytest.fixture
def cache(tmp_path):
    return ReadCache(tmp_path / "cache")


@pytest.fixture
def blob(tmp_path):
    path = tmp_path / "out.dxf"
    path.write_bytes(b"0\nSECTION\n0\nEOF\n")
    return path


# --- keys -----------------------------------------------------------------------------


def test_key_ignores_dict_order():
    reordered = {"tool": {"sha256": "b" * 64, "name": "x"}, "input_sha256": "a" * 64, "action": "demo"}
    assert action_key(MATERIAL) == action_key(reordered)


@pytest.mark.parametrize(
    "change",
    [
        {"action": "other"},
        {"input_sha256": "c" * 64},
        {"tool": {"name": "x", "sha256": "d" * 64}},
        {"extra": 1},
    ],
)
def test_any_material_change_changes_key(change):
    assert action_key(MATERIAL) != action_key({**MATERIAL, **change})


def test_key_is_domain_separated():
    plain = hashlib.sha256(json.dumps(MATERIAL, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert action_key(MATERIAL) != plain


def test_key_rejects_floats_and_non_json():
    # Floats have no single canonical text form; keys must be built from str/int/bool/None.
    with pytest.raises(TypeError):
        action_key({"x": 1.5})
    with pytest.raises(TypeError):
        action_key({"x": object()})


# --- round trip -----------------------------------------------------------------------


def test_put_then_get(cache, blob):
    key = action_key(MATERIAL)
    assert cache.get(key) is None
    cache.put(key, MATERIAL, {"out.dxf": blob}, {"converter": "x"})
    entry = cache.get(key)
    assert entry is not None
    assert entry.result == {"converter": "x"}
    assert entry.output_path("out.dxf").read_bytes() == blob.read_bytes()


def test_entry_file_validates_against_schema(cache, blob):
    key = action_key(MATERIAL)
    cache.put(key, MATERIAL, {"out.dxf": blob}, {"converter": "x"})
    data = json.loads(cache.entry_path(key).read_text(encoding="utf-8"))
    assert validate("cache-entry", data) == []


def test_identical_outputs_are_stored_once(cache, blob):
    cache.put(action_key(MATERIAL), MATERIAL, {"out.dxf": blob}, {})
    other = {**MATERIAL, "action": "other"}
    cache.put(action_key(other), other, {"out.dxf": blob}, {})
    assert len([p for p in (cache.root / "cas").rglob("*") if p.is_file()]) == 1


def test_put_same_key_twice_is_safe(cache, blob):
    key = action_key(MATERIAL)
    cache.put(key, MATERIAL, {"out.dxf": blob}, {"n": 1})
    cache.put(key, MATERIAL, {"out.dxf": blob}, {"n": 2})
    entry = cache.get(key)
    assert entry is not None and entry.result == {"n": 2}


def test_cache_dir_is_self_ignoring(cache, blob):
    cache.put(action_key(MATERIAL), MATERIAL, {"out.dxf": blob}, {})
    tag = (cache.root / "CACHEDIR.TAG").read_text(encoding="utf-8")
    assert tag.startswith(CACHEDIR_TAG_SIGNATURE)
    assert (cache.root / ".gitignore").read_text(encoding="utf-8").strip() == "*"


# --- integrity: every read is verified; anything wrong is a miss ----------------------


def _stored_blob(cache):
    return next(p for p in (cache.root / "cas").rglob("*") if p.is_file())


def test_corrupt_blob_is_a_miss_and_is_removed(cache, blob, capsys):
    key = action_key(MATERIAL)
    cache.put(key, MATERIAL, {"out.dxf": blob}, {})
    stored = _stored_blob(cache)
    stored.write_bytes(stored.read_bytes().replace(b"EOF", b"EOX"))
    assert cache.get(key) is None
    assert not cache.entry_path(key).exists()
    assert not stored.exists()
    assert "discarded" in capsys.readouterr().err


def test_missing_blob_is_a_miss(cache, blob):
    key = action_key(MATERIAL)
    cache.put(key, MATERIAL, {"out.dxf": blob}, {})
    _stored_blob(cache).unlink()
    assert cache.get(key) is None


@pytest.mark.parametrize("damage", ["truncate", "garbage", "empty"])
def test_damaged_entry_is_a_miss(cache, blob, damage):
    key = action_key(MATERIAL)
    cache.put(key, MATERIAL, {"out.dxf": blob}, {})
    path = cache.entry_path(key)
    text = path.read_text(encoding="utf-8")
    path.write_text({"truncate": text[: len(text) // 2], "garbage": "not json", "empty": ""}[damage])
    assert cache.get(key) is None
    assert not path.exists()


def test_entry_under_the_wrong_key_is_a_miss(cache, blob):
    key = action_key(MATERIAL)
    cache.put(key, MATERIAL, {"out.dxf": blob}, {})
    other_key = action_key({**MATERIAL, "action": "other"})
    target = cache.entry_path(other_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(cache.entry_path(key).read_bytes())
    assert cache.get(other_key) is None


def test_leftover_temp_files_are_ignored(cache, blob):
    key = action_key(MATERIAL)
    cache.put(key, MATERIAL, {"out.dxf": blob}, {})
    entry_dir = cache.entry_path(key).parent
    (entry_dir / ".tmp-crashed-writer").write_text("half a json", encoding="utf-8")
    assert cache.get(key) is not None


def test_invalid_key_is_rejected(cache):
    with pytest.raises(ValueError):
        cache.get("../../etc/passwd")
