"""parts.py: the manifest path, the part id pattern and the ids a manifest lists (ADR-0019)."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from tekla_harness.parts import (
    MANIFEST_REL,
    PART_ID_RE,
    ManifestAccessError,
    ManifestError,
    manifest_path,
    manifest_present,
    part_ids,
)

needs_permissions = pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="chmod 000 does not stop this user (Windows or root)",
)


@contextmanager
def no_access(path: Path) -> Iterator[None]:
    path.chmod(0o000)
    try:
        yield
    finally:
        path.chmod(0o755 if path.is_dir() else 0o644)


def write(work: Path, text: str) -> None:
    manifest_path(work).parent.mkdir(parents=True, exist_ok=True)
    manifest_path(work).write_text(text, encoding="utf-8")


def test_the_manifest_lives_at_parts_manifest_json(tmp_path):
    assert MANIFEST_REL == "parts/manifest.json"
    assert manifest_path(tmp_path) == tmp_path / "parts" / "manifest.json"


def test_no_manifest_is_none_not_an_empty_set(tmp_path):
    assert part_ids(tmp_path) is None
    write(tmp_path, json.dumps({"parts": []}))
    assert part_ids(tmp_path) == frozenset()


def test_only_the_ids_are_read_and_other_fields_are_not_checked(tmp_path):
    write(
        tmp_path,
        json.dumps({"schema": "whatever", "parts": [{"id": "a-b", "kind": 7}, {"id": "all-assembly"}]}),
    )
    assert part_ids(tmp_path) == frozenset({"a-b", "all-assembly"})


@pytest.mark.parametrize("ok", ["a", "A_b-9", "0x", "all-grid-levels", "x" * 64])
def test_part_id_pattern_accepts(ok):
    assert PART_ID_RE.fullmatch(ok)


@pytest.mark.parametrize("bad", ["", "-x", "_x", "a b", "a/b", "é", "x" * 65, "a\n"])
def test_part_id_pattern_rejects(bad):
    assert not PART_ID_RE.fullmatch(bad)


@pytest.mark.parametrize(
    "text",
    ["", "{", "[]", "null", '{"parts": 3}', '{"parts": [1]}', '{"parts": [{}]}', '{"parts": [{"id": 3}]}'],
)
def test_an_unreadable_manifest_raises_naming_the_file(tmp_path, text):
    write(tmp_path, text)
    with pytest.raises(ManifestError, match=r"parts/manifest\.json"):
        part_ids(tmp_path)


def test_a_manifest_that_is_not_utf8_raises(tmp_path):
    manifest_path(tmp_path).parent.mkdir()
    manifest_path(tmp_path).write_bytes(b"\xff\xfe\x00")
    with pytest.raises(ManifestError, match=r"parts/manifest\.json"):
        part_ids(tmp_path)


# --- one rule for "is there a manifest" (DECISIONS § 4): anything at the path means part mode is on --------


def test_manifest_present_is_false_when_nothing_is_there(tmp_path):
    assert manifest_present(tmp_path) is False
    (tmp_path / "parts").mkdir()
    assert manifest_present(tmp_path) is False


def test_manifest_present_is_true_for_a_file(tmp_path):
    write(tmp_path, "{}")
    assert manifest_present(tmp_path) is True


def test_parts_that_is_a_regular_file_means_no_manifest(tmp_path):
    (tmp_path / "parts").write_text("not a folder", encoding="utf-8")
    assert manifest_present(tmp_path) is False
    assert part_ids(tmp_path) is None


def test_a_directory_at_the_manifest_path_is_a_manifest_error_not_no_manifest(tmp_path):
    manifest_path(tmp_path).mkdir(parents=True)
    assert manifest_present(tmp_path) is True
    with pytest.raises(ManifestError, match=r"parts/manifest\.json is not a regular file"):
        part_ids(tmp_path)


def test_a_dangling_symlink_at_the_manifest_path_is_a_manifest_error_not_no_manifest(tmp_path):
    manifest_path(tmp_path).parent.mkdir()
    try:
        manifest_path(tmp_path).symlink_to(tmp_path / "nowhere.json")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not permitted here")
    assert manifest_present(tmp_path) is True
    with pytest.raises(ManifestError, match=r"parts/manifest\.json is not a regular file"):
        part_ids(tmp_path)


@needs_permissions
def test_an_unreadable_parts_folder_is_an_access_error_not_no_manifest(tmp_path):
    write(tmp_path, json.dumps({"parts": [{"id": "a"}]}))
    with no_access(tmp_path / "parts"):
        with pytest.raises(ManifestAccessError, match=r"cannot check parts/manifest\.json"):
            manifest_present(tmp_path)
        with pytest.raises(ManifestAccessError, match=r"parts/manifest\.json"):
            part_ids(tmp_path)


@needs_permissions
def test_an_unreadable_manifest_file_is_an_access_error(tmp_path):
    write(tmp_path, json.dumps({"parts": [{"id": "a"}]}))
    with no_access(manifest_path(tmp_path)):
        assert manifest_present(tmp_path) is True
        with pytest.raises(ManifestAccessError, match=r"cannot read parts/manifest\.json"):
            part_ids(tmp_path)


def test_the_two_errors_are_not_the_same_class():
    assert not issubclass(ManifestAccessError, ManifestError)
    assert not issubclass(ManifestError, ManifestAccessError)


@pytest.mark.parametrize(
    ("text", "said"),
    [
        ("[]", "is not a JSON object"),
        ("null", "is not a JSON object"),
        ("{}", "has no 'parts' list"),
        ('{"parts": 3}', "has no 'parts' list"),
        ('{"parts": null}', "has no 'parts' list"),
        ('{"parts": [{"id": "a"}, 1]}', "parts[1] has no string 'id'"),
        ('{"parts": [{}]}', "parts[0] has no string 'id'"),
        ('{"parts": [{"id": 3}]}', "parts[0] has no string 'id'"),
        ("{", "is not valid JSON"),
        ("", "is not valid JSON"),
    ],
)
def test_a_malformed_manifest_says_in_plain_words_what_is_wrong(tmp_path, text, said):
    write(tmp_path, text)
    with pytest.raises(ManifestError) as err:
        part_ids(tmp_path)
    assert str(err.value).startswith(MANIFEST_REL) and said in str(err.value)
    assert "NoneType" not in str(err.value) and "indices" not in str(err.value)


def test_a_manifest_that_is_not_utf8_says_so(tmp_path):
    manifest_path(tmp_path).parent.mkdir()
    manifest_path(tmp_path).write_bytes(b"\xff\xfe\x00")
    with pytest.raises(ManifestError, match="not UTF-8"):
        part_ids(tmp_path)
