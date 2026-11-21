"""dwg_to_dxf with the read cache: a hit must be indistinguishable from a fresh run in
provenance and confidence, and must never hide a change that could alter the result."""

from __future__ import annotations

import hashlib
import json
import sys
import textwrap

import pytest
from ezdxf.filemanagement import new

from tekla_harness import convert
from tekla_harness.cache import ReadCache
from tekla_harness.cli import main
from tekla_harness.convert import dwg_to_dxf

ODA_OUT = "os.path.join(sys.argv[2], os.path.splitext(sys.argv[7])[0] + '.dxf')"
LIBRE_OUT = "sys.argv[sys.argv.index('-o') + 1]"


def fake(tmp_path, name: str, out_expr: str, ok: bool, template, variant: str = "") -> list[str]:
    """A converter that appends one line to <name>.calls on every run."""
    calls = tmp_path / f"{name}.calls"
    body = "shutil.copy(TEMPLATE, out_path)" if ok else "sys.stderr.write('fatal'); sys.exit(1)"
    script = tmp_path / f"{name}.py"
    script.write_text(
        textwrap.dedent(f"""\
            import os, shutil, sys
            TEMPLATE = {str(template)!r}
            open({str(calls)!r}, 'a').write('x\\n')
            out_path = {out_expr}
            {body}
            # {variant}
        """),
        encoding="utf-8",
    )
    return [sys.executable, str(script)]


def info(result) -> dict:
    assert result.cache is not None, "a cache was passed, so the result must report it"
    return result.cache


def calls(tmp_path, name: str) -> int:
    path = tmp_path / f"{name}.calls"
    return len(path.read_text().splitlines()) if path.exists() else 0


@pytest.fixture
def template(tmp_path):
    path = tmp_path / "template.dxf"
    doc = new("R2018")
    doc.modelspace().add_line((0, 0), (6000, 0))
    doc.saveas(path)
    return path


@pytest.fixture
def dwg(tmp_path):
    (tmp_path / "input").mkdir()
    path = tmp_path / "input" / "S-101.dwg"
    path.write_bytes(b"AC1032" + b"\x00" * 64)
    return path


@pytest.fixture
def cache(tmp_path):
    return ReadCache(tmp_path / "project" / ".cache")


def test_second_run_is_a_hit_and_runs_no_converter(tmp_path, template, dwg, cache):
    oda = fake(tmp_path, "oda", ODA_OUT, True, template)
    first = dwg_to_dxf(dwg, tmp_path / "w1", oda=oda, cache=cache)
    second = dwg_to_dxf(dwg, tmp_path / "w2", oda=oda, cache=cache)
    assert first.cache == {"hit": False, "key": info(second)["key"]}
    assert info(second)["hit"] is True
    assert calls(tmp_path, "oda") == 1
    assert second.dxf == (tmp_path / "w2" / "S-101.dxf").resolve()
    assert first.dxf is not None and second.dxf is not None
    assert second.dxf.read_bytes() == first.dxf.read_bytes()


@pytest.fixture
def no_path_converters(monkeypatch):
    monkeypatch.delenv("HARNESS_ODA_CONVERTER", raising=False)
    monkeypatch.delenv("HARNESS_DWG2DXF", raising=False)
    monkeypatch.setattr("tekla_harness.convert.shutil.which", lambda _name: None)


def test_hit_preserves_provenance_and_cap(tmp_path, template, dwg, cache, no_path_converters):
    libre = fake(tmp_path, "libre", LIBRE_OUT, True, template)  # LibreDWG is the only converter
    fresh = dwg_to_dxf(dwg, tmp_path / "w1", dwg2dxf=libre, cache=cache)
    hit = dwg_to_dxf(dwg, tmp_path / "w2", dwg2dxf=libre, cache=cache)
    assert info(hit)["hit"] is True
    assert hit.converter == fresh.converter == "libredwg_dwg2dxf"
    assert hit.confidence_cap == fresh.confidence_cap == "medium"
    assert [a.as_dict() for a in hit.attempts] == [a.as_dict() for a in fresh.attempts]
    assert hit.warnings == fresh.warnings
    assert any("not configured" in w for w in hit.warnings)


def test_fallback_after_a_failure_is_never_cached(tmp_path, template, dwg, cache):
    """Review C1: a transient ODA failure must not pin the medium LibreDWG result."""
    oda, flag = switchable_oda(tmp_path, template)  # same bytes throughout: same key
    libre = fake(tmp_path, "libre", LIBRE_OUT, True, template)
    flag.touch()
    for out in ("w1", "w2"):
        result = dwg_to_dxf(dwg, tmp_path / out, oda=oda, dwg2dxf=libre, cache=cache, timeout=1)
        assert result.converter == "libredwg_dwg2dxf" and info(result)["hit"] is False
        assert any("not cached because oda_file_converter failed" in w for w in result.warnings)
    assert calls(tmp_path, "oda") == 2
    flag.unlink()  # ODA recovers; the key is unchanged, so only a pinned entry could hit
    healed = dwg_to_dxf(dwg, tmp_path / "w3", oda=oda, dwg2dxf=libre, cache=cache)
    assert info(healed)["hit"] is False and healed.confidence_cap == "high"
    assert calls(tmp_path, "oda") == 3


def test_cache_stores_the_validated_output_not_the_delivered_copy(
    tmp_path, template, dwg, cache, monkeypatch
):
    """Review C2: another run writing the same output name must not end up in our entry."""
    real_deliver = convert._deliver

    def racing_deliver(src, dst):
        delivered = real_deliver(src, dst)
        delivered.write_bytes(b"another run's DXF")  # a concurrent run with the same stem
        return delivered

    monkeypatch.setattr(convert, "_deliver", racing_deliver)
    oda = fake(tmp_path, "oda", ODA_OUT, True, template)
    dwg_to_dxf(dwg, tmp_path / "w1", oda=oda, cache=cache)
    monkeypatch.setattr(convert, "_deliver", real_deliver)
    hit = dwg_to_dxf(dwg, tmp_path / "w2", oda=oda, cache=cache)
    assert info(hit)["hit"] is True
    assert hit.dxf is not None and hit.dxf.read_bytes() == template.read_bytes()


def test_key_and_converters_see_one_snapshot_of_the_input(tmp_path, template, dwg, cache, monkeypatch):
    """Review M5: the input changing during the run must not desynchronise key and output."""
    seen = tmp_path / "seen.sha"
    script = tmp_path / "oda_hash.py"
    script.write_text(
        textwrap.dedent(f"""\
            import hashlib, os, shutil, sys
            src = os.path.join(sys.argv[1], sys.argv[7])
            open({str(seen)!r}, 'w').write(hashlib.sha256(open(src, 'rb').read()).hexdigest())
            out = os.path.join(sys.argv[2], os.path.splitext(sys.argv[7])[0] + '.dxf')
            shutil.copy({str(template)!r}, out)
        """),
        encoding="utf-8",
    )
    original = dwg.read_bytes()
    real_try = convert._try

    def editing_try(*args, **kwargs):
        dwg.write_bytes(b"AC1032" + b"\x07" * 64)  # the engineer saves a new revision mid-run
        return real_try(*args, **kwargs)

    monkeypatch.setattr(convert, "_try", editing_try)
    result = dwg_to_dxf(dwg, tmp_path / "w1", oda=[sys.executable, str(script)], cache=cache)
    entry = json.loads(cache.entry_path(info(result)["key"]).read_text(encoding="utf-8"))
    assert seen.read_text() == entry["action"]["input_sha256"] == hashlib.sha256(original).hexdigest()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX launcher script")
def test_bare_command_name_is_resolved_and_hashed(tmp_path, template, dwg, cache, monkeypatch):
    """Review M6: replacing the executable found on PATH must invalidate."""
    script = fake(tmp_path, "libre", LIBRE_OUT, True, template)[1]
    bindir = tmp_path / "bin"
    bindir.mkdir()
    launcher = bindir / "dwg2dxf"
    launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
    launcher.chmod(0o755)
    monkeypatch.setenv("PATH", str(bindir))
    monkeypatch.delenv("HARNESS_ODA_CONVERTER", raising=False)
    monkeypatch.delenv("HARNESS_DWG2DXF", raising=False)
    assert dwg_to_dxf(dwg, tmp_path / "w1", dwg2dxf=["dwg2dxf"], cache=cache).converter == "libredwg_dwg2dxf"
    launcher.write_text(launcher.read_text() + "# upgraded\n", encoding="utf-8")
    assert info(dwg_to_dxf(dwg, tmp_path / "w2", dwg2dxf=["dwg2dxf"], cache=cache))["hit"] is False


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX PATH lookup")
def test_bare_name_hashes_the_file_that_runs_not_a_cwd_decoy(tmp_path, template, dwg, cache, monkeypatch):
    """A bare name runs from PATH, so a same-named file in the cwd must not be what is hashed."""
    script = fake(tmp_path, "libre", LIBRE_OUT, True, template)[1]
    bindir, cwd = tmp_path / "bin", tmp_path / "cwd"
    bindir.mkdir()
    cwd.mkdir()
    launcher = bindir / "dwg2dxf"
    launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
    launcher.chmod(0o755)
    (cwd / "dwg2dxf").write_text("decoy, never run\n", encoding="utf-8")
    monkeypatch.chdir(cwd)
    monkeypatch.setenv("PATH", str(bindir))
    monkeypatch.delenv("HARNESS_ODA_CONVERTER", raising=False)
    monkeypatch.delenv("HARNESS_DWG2DXF", raising=False)
    dwg_to_dxf(dwg, tmp_path / "w1", dwg2dxf=["dwg2dxf"], cache=cache)
    launcher.write_text(launcher.read_text() + "# upgraded\n", encoding="utf-8")
    assert info(dwg_to_dxf(dwg, tmp_path / "w2", dwg2dxf=["dwg2dxf"], cache=cache))["hit"] is False


def _corrupt_result(cache, key, change):
    path = cache.entry_path(key)
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d["result"].pop("converter"),
        lambda d: d["result"].update(confidence_cap="medium"),  # ODA result claiming medium
        lambda d: d["result"].update(warnings="abc"),
        lambda d: d["result"].update(warnings=[1]),
        lambda d: d["result"].update(attempts=[]),
        lambda d: d["result"].update(attempts=["x"]),
        lambda d: d["result"]["attempts"][0].update(status="failed", error="boom"),
        lambda d: d["outputs"][0].update(name="other.dxf"),
        lambda d: d.update(outputs=[]),
        lambda d: d["action"].update(input_sha256=1.5),
    ],
    ids=["no-converter", "cap-mismatch", "warnings-str", "warnings-int", "no-attempts",
         "attempt-not-dict", "failed-attempt", "wrong-output-name", "no-outputs", "float-in-action"],
)  # fmt: skip
def test_well_formed_but_wrong_entry_is_discarded_and_recomputed(tmp_path, template, dwg, cache, change):
    """Review M4: no recorded result is served unless a fresh run could have produced it."""
    oda = fake(tmp_path, "oda", ODA_OUT, True, template)
    key = info(dwg_to_dxf(dwg, tmp_path / "w1", oda=oda, cache=cache))["key"]
    _corrupt_result(cache, key, change)
    again = dwg_to_dxf(dwg, tmp_path / "w2", oda=oda, cache=cache)
    assert info(again)["hit"] is False
    assert again.converter == "oda_file_converter" and again.confidence_cap == "high"
    assert calls(tmp_path, "oda") == 2
    assert info(dwg_to_dxf(dwg, tmp_path / "w3", oda=oda, cache=cache))["hit"] is True  # rewritten


def test_unreadable_blob_is_a_miss_and_keeps_the_entry(tmp_path, template, dwg, cache, monkeypatch):
    oda = fake(tmp_path, "oda", ODA_OUT, True, template)
    key = info(dwg_to_dxf(dwg, tmp_path / "w1", oda=oda, cache=cache))["key"]

    def locked(_path):
        raise PermissionError("in use by another process")

    monkeypatch.setattr("tekla_harness.cache.sha256_file", locked)
    assert cache.get(key) is None
    assert cache.entry_path(key).exists()


def test_newly_available_converter_invalidates(tmp_path, template, dwg, cache, monkeypatch):
    """Regression guard: a LibreDWG-only result must not be served once ODA is available."""
    monkeypatch.delenv("HARNESS_ODA_CONVERTER", raising=False)
    monkeypatch.delenv("HARNESS_DWG2DXF", raising=False)
    monkeypatch.setattr("tekla_harness.convert.shutil.which", lambda _name: None)
    libre = fake(tmp_path, "libre", LIBRE_OUT, True, template)
    first = dwg_to_dxf(dwg, tmp_path / "w1", dwg2dxf=libre, cache=cache)
    assert first.converter == "libredwg_dwg2dxf"

    oda = fake(tmp_path, "oda", ODA_OUT, True, template)
    second = dwg_to_dxf(dwg, tmp_path / "w2", oda=oda, dwg2dxf=libre, cache=cache)
    assert info(second)["hit"] is False
    assert second.converter == "oda_file_converter"
    assert second.confidence_cap == "high"
    assert calls(tmp_path, "oda") == 1


def test_changed_converter_binary_invalidates(tmp_path, template, dwg, cache):
    dwg_to_dxf(dwg, tmp_path / "w1", oda=fake(tmp_path, "oda", ODA_OUT, True, template), cache=cache)
    upgraded = fake(tmp_path, "oda", ODA_OUT, True, template, variant="v2")  # same path, new bytes
    again = dwg_to_dxf(dwg, tmp_path / "w2", oda=upgraded, cache=cache)
    assert info(again)["hit"] is False
    assert calls(tmp_path, "oda") == 2


def test_changed_input_content_invalidates(tmp_path, template, dwg, cache):
    oda = fake(tmp_path, "oda", ODA_OUT, True, template)
    dwg_to_dxf(dwg, tmp_path / "w1", oda=oda, cache=cache)
    dwg.write_bytes(b"AC1032" + b"\x01" * 64)
    assert info(dwg_to_dxf(dwg, tmp_path / "w2", oda=oda, cache=cache))["hit"] is False


def test_paths_are_not_part_of_the_key(tmp_path, template, dwg, cache):
    """Same bytes under another name or folder is the same action; output takes the new name."""
    oda = fake(tmp_path, "oda", ODA_OUT, True, template)
    dwg_to_dxf(dwg, tmp_path / "w1", oda=oda, cache=cache)
    renamed = dwg.parent / "S-101-copy.dwg"
    renamed.write_bytes(dwg.read_bytes())
    hit = dwg_to_dxf(renamed, tmp_path / "elsewhere", oda=oda, cache=cache, timeout=7)
    assert info(hit)["hit"] is True
    assert hit.dxf == (tmp_path / "elsewhere" / "S-101-copy.dxf").resolve()


@pytest.mark.parametrize("component", ["code", "ezdxf"])
def test_code_and_oracle_versions_are_in_the_key(tmp_path, template, dwg, cache, monkeypatch, component):
    oda = fake(tmp_path, "oda", ODA_OUT, True, template)
    dwg_to_dxf(dwg, tmp_path / "w1", oda=oda, cache=cache)
    if component == "code":
        monkeypatch.setattr(convert, "_code_digest", lambda: "f" * 64)
    else:
        monkeypatch.setattr(convert, "EZDXF_VERSION", "0.0.0-test")
    assert info(dwg_to_dxf(dwg, tmp_path / "w2", oda=oda, cache=cache))["hit"] is False


def test_failures_are_not_cached(tmp_path, template, dwg, cache):
    oda = fake(tmp_path, "oda", ODA_OUT, False, template)
    libre = fake(tmp_path, "libre", LIBRE_OUT, False, template)
    for out in ("w1", "w2"):
        result = dwg_to_dxf(dwg, tmp_path / out, oda=oda, dwg2dxf=libre, cache=cache)
        assert result.dxf is None and info(result)["hit"] is False
    assert calls(tmp_path, "oda") == 2 and calls(tmp_path, "libre") == 2
    assert not (cache.root / "ac").exists() or not any((cache.root / "ac").rglob("*.json"))


def test_refresh_recomputes(tmp_path, template, dwg, cache):
    oda = fake(tmp_path, "oda", ODA_OUT, True, template)
    dwg_to_dxf(dwg, tmp_path / "w1", oda=oda, cache=cache)
    again = dwg_to_dxf(dwg, tmp_path / "w2", oda=oda, cache=cache, refresh=True)
    assert info(again)["hit"] is False
    assert calls(tmp_path, "oda") == 2
    assert info(dwg_to_dxf(dwg, tmp_path / "w3", oda=oda, cache=cache))["hit"] is True


def switchable_oda(tmp_path, template):
    """ODA fake whose bytes never change; it fails while <tmp>/oda.broken exists."""
    flag = tmp_path / "oda.broken"
    script = tmp_path / "oda_switch.py"
    script.write_text(
        textwrap.dedent(f"""\
            import os, shutil, sys
            open({str(tmp_path / "oda.calls")!r}, 'a').write('x\\n')
            if os.path.exists({str(flag)!r}):
                sys.stderr.write('license server down'); sys.exit(1)
            out = os.path.join(sys.argv[2], os.path.splitext(sys.argv[7])[0] + '.dxf')
            shutil.copy({str(template)!r}, out)
        """),
        encoding="utf-8",
    )
    return [sys.executable, str(script)], flag


def test_refresh_that_fails_leaves_no_old_result(tmp_path, template, dwg, cache):
    """Review M3b: --refresh is the documented fix for an in-place upgrade; a failed recompute
    must not leave the old success to be served on the next run."""
    oda, flag = switchable_oda(tmp_path, template)
    key = info(dwg_to_dxf(dwg, tmp_path / "w1", oda=oda, cache=cache))["key"]
    flag.touch()
    failed = dwg_to_dxf(dwg, tmp_path / "w2", oda=oda, cache=cache, refresh=True)
    assert failed.dxf is None
    assert not cache.entry_path(key).exists()
    assert dwg_to_dxf(dwg, tmp_path / "w3", oda=oda, cache=cache).dxf is None  # not a stale hit


def test_refresh_while_oda_fails_does_not_downgrade(tmp_path, template, dwg, cache):
    """Review M3a: refreshing during an ODA outage must not record a medium fallback."""
    oda, flag = switchable_oda(tmp_path, template)
    libre = fake(tmp_path, "libre", LIBRE_OUT, True, template)
    dwg_to_dxf(dwg, tmp_path / "w1", oda=oda, dwg2dxf=libre, cache=cache)
    flag.touch()
    assert dwg_to_dxf(dwg, tmp_path / "w2", oda=oda, dwg2dxf=libre, cache=cache, refresh=True).converter == (
        "libredwg_dwg2dxf"
    )
    flag.unlink()
    healed = dwg_to_dxf(dwg, tmp_path / "w3", oda=oda, dwg2dxf=libre, cache=cache)
    assert info(healed)["hit"] is False and healed.confidence_cap == "high"


def test_cache_write_failure_keeps_the_conversion(tmp_path, template, dwg, cache, monkeypatch):
    def full_disk(*_args, **_kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(ReadCache, "put", full_disk)
    result = dwg_to_dxf(dwg, tmp_path / "w1", oda=fake(tmp_path, "oda", ODA_OUT, True, template), cache=cache)
    assert result.dxf is not None and result.confidence_cap == "high"
    assert any("not cached" in w for w in result.warnings)


def test_no_cache_means_no_cache_field_hit(tmp_path, template, dwg):
    oda = fake(tmp_path, "oda", ODA_OUT, True, template)
    result = dwg_to_dxf(dwg, tmp_path / "w1", oda=oda)
    assert result.cache is None


def test_cache_inside_input_is_refused(tmp_path, template, dwg):
    oda = fake(tmp_path, "oda", ODA_OUT, True, template)
    with pytest.raises(ValueError, match="input"):
        dwg_to_dxf(dwg, tmp_path / "w1", oda=oda, cache=ReadCache(dwg.parent / ".cache"))


def test_cache_that_contains_the_input_is_refused(tmp_path, template, dwg):
    """Review m7: --cache-dir projects/<id> would tag the whole project as a cache."""
    oda = fake(tmp_path, "oda", ODA_OUT, True, template)
    with pytest.raises(ValueError, match="contains the input"):
        dwg_to_dxf(dwg, tmp_path / "w1", oda=oda, cache=ReadCache(tmp_path))


def test_foreign_non_empty_folder_is_refused(tmp_path, template, dwg):
    project = tmp_path / "project"
    project.mkdir()
    (project / "02-plan.md").write_text("plan", encoding="utf-8")
    oda = fake(tmp_path, "oda", ODA_OUT, True, template)
    with pytest.raises(ValueError, match="not a read cache"):
        dwg_to_dxf(dwg, tmp_path / "w1", oda=oda, cache=ReadCache(project))
    assert not (project / "CACHEDIR.TAG").exists()


def test_cli_refresh_without_cache_dir_is_a_usage_error(tmp_path, dwg, capsys):
    assert main(["dwg2dxf", str(dwg), "--out-dir", str(tmp_path / "w"), "--refresh"]) == 2
    assert "--refresh needs --cache-dir" in capsys.readouterr().err


# --- merge with main: converter ERROR lines and empty output (ADR-0005 amendment) -----


def test_error_lines_result_round_trips_with_its_lowered_cap(tmp_path, template, dwg, cache):
    oda = _raw_fake(
        tmp_path,
        "oda_err",
        f"""\
        import os, shutil, sys
        sys.stderr.write("ERROR: bad string in block\\nERROR: text truncated\\nWarning: font\\n")
        shutil.copy({str(template)!r}, os.path.join(sys.argv[2], os.path.splitext(sys.argv[7])[0] + '.dxf'))
    """,
    )
    fresh = dwg_to_dxf(dwg, tmp_path / "w1", oda=oda, cache=cache)
    hit = dwg_to_dxf(dwg, tmp_path / "w2", oda=oda, cache=cache)
    assert fresh.confidence_cap == "medium" and fresh.stderr_error_lines == 2
    assert info(hit)["hit"] is True, "a lowered cap must replay, not be discarded as inconsistent"
    assert (hit.confidence_cap, hit.stderr_error_lines, hit.stderr_warning_lines, hit.stderr_tail) == (
        fresh.confidence_cap,
        fresh.stderr_error_lines,
        fresh.stderr_warning_lines,
        fresh.stderr_tail,
    )
    assert hit.warnings == fresh.warnings


def test_replayed_cap_must_match_the_recorded_error_lines(tmp_path, template, dwg, cache):
    oda = fake(tmp_path, "oda", ODA_OUT, True, template)
    key = info(dwg_to_dxf(dwg, tmp_path / "w1", oda=oda, cache=cache))["key"]
    _corrupt_result(cache, key, lambda d: d["result"].update(stderr_error_lines=3))  # cap stays high
    assert info(dwg_to_dxf(dwg, tmp_path / "w2", oda=oda, cache=cache))["hit"] is False


def test_empty_output_from_a_large_dwg_is_never_cached(tmp_path, dwg, cache):
    dwg.write_bytes(b"AC1032" + b"\x00" * (20 * 1024))
    empty = tmp_path / "empty.dxf"
    new("R2018").saveas(empty)
    oda = fake(tmp_path, "oda", ODA_OUT, True, empty)
    for out in ("w1", "w2"):
        result = dwg_to_dxf(dwg, tmp_path / out, oda=oda, cache=cache)
        assert result.confidence_cap == "low" and info(result)["hit"] is False
        assert any("was partial" in w for w in result.warnings)
    assert calls(tmp_path, "oda") == 2


# --- review round 2 ------------------------------------------------------------------


def _raw_fake(tmp_path, name: str, body: str) -> list[str]:
    script = tmp_path / f"{name}.py"
    script.write_text(textwrap.dedent(body), encoding="utf-8")
    return [sys.executable, str(script)]


def _leftover_work_dirs(prefix: str) -> set[str]:
    import tempfile
    from pathlib import Path

    return {p.name for p in Path(tempfile.gettempdir()).glob(f"{prefix}*")}


@pytest.fixture
def private_tempdir(tmp_path, monkeypatch):
    """The converter's temp folders go to a folder of this test only: the shared system temp folder also
    holds other processes' folders (parallel test runs), which made the leftover check flaky."""
    import tempfile

    private = tmp_path / "systemp"
    private.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(private))
    return private


@pytest.mark.parametrize("exit_code", [0, 1])
def test_non_utf8_converter_output_is_a_recorded_failure(tmp_path, template, dwg, exit_code, private_tempdir):
    """Review N1: bytes that are not UTF-8 on stderr must not crash the chain."""
    before = _leftover_work_dirs("oda_file_converter-")
    oda = _raw_fake(
        tmp_path,
        "oda_bytes",
        f"""\
        import sys
        sys.stderr.buffer.write(b"\\xff\\xfe l\\xe1i \\x81")
        sys.exit({exit_code})
    """,
    )
    libre = fake(tmp_path, "libre", LIBRE_OUT, True, template)
    result = dwg_to_dxf(dwg, tmp_path / "w1", oda=oda, dwg2dxf=libre)
    assert result.attempts[0].status == "failed" and result.attempts[0].error
    assert result.converter == "libredwg_dwg2dxf"
    assert _leftover_work_dirs("oda_file_converter-") == before == set()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX exec format error")
def test_unexecutable_converter_is_a_recorded_failure(tmp_path, template, dwg):
    """Review N1: an OSError other than not-found (exec format error) is an attempt failure."""
    bogus = tmp_path / "ODAFileConverter"
    bogus.write_bytes(b"\x00\x01not an executable")
    bogus.chmod(0o755)
    libre = fake(tmp_path, "libre", LIBRE_OUT, True, template)
    result = dwg_to_dxf(dwg, tmp_path / "w1", oda=[str(bogus)], dwg2dxf=libre)
    assert result.attempts[0].status == "failed"
    assert result.converter == "libredwg_dwg2dxf"


def test_work_folder_is_removed_when_try_raises(tmp_path, template, dwg, monkeypatch, private_tempdir):
    before = _leftover_work_dirs("oda_file_converter-")

    def boom(*_args, **_kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(convert.subprocess, "run", boom)
    with pytest.raises(RuntimeError):
        dwg_to_dxf(dwg, tmp_path / "w1", oda=fake(tmp_path, "oda", ODA_OUT, True, template))
    assert _leftover_work_dirs("oda_file_converter-") == before == set()


def test_locked_entry_makes_refresh_fail_loudly(tmp_path, template, dwg, cache, monkeypatch):
    """Review N2: if refresh cannot delete the old entry, it must not pretend it did."""
    oda = fake(tmp_path, "oda", ODA_OUT, True, template)
    key = info(dwg_to_dxf(dwg, tmp_path / "w1", oda=oda, cache=cache))["key"]
    real_unlink = convert.Path.unlink

    def locked_unlink(self, *args, **kwargs):
        if self == cache.entry_path(key):
            raise PermissionError("in use by another process")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(convert.Path, "unlink", locked_unlink)
    with pytest.raises(OSError, match="refresh"):
        dwg_to_dxf(dwg, tmp_path / "w2", oda=oda, cache=cache, refresh=True)


def test_cache_failure_of_any_kind_still_delivers_the_dxf(tmp_path, template, dwg, cache, monkeypatch):
    """Review N3: the cache is an optimisation; a bug in it must not cost the conversion."""

    def broken_put(*_args, **_kwargs):
        raise RuntimeError("bug in put")

    monkeypatch.setattr(ReadCache, "put", broken_put)
    result = dwg_to_dxf(dwg, tmp_path / "w1", oda=fake(tmp_path, "oda", ODA_OUT, True, template), cache=cache)
    assert result.dxf is not None and result.dxf.is_file()
    assert any("not cached" in w and "RuntimeError" in w for w in result.warnings)


def test_hit_and_fresh_deliver_files_alike(tmp_path, template, dwg, cache):
    """Review N4: a hit must not hand out the blob's private mode or old timestamp."""
    oda = fake(tmp_path, "oda", ODA_OUT, True, template)
    fresh = dwg_to_dxf(dwg, tmp_path / "w1", oda=oda, cache=cache)
    hit = dwg_to_dxf(dwg, tmp_path / "w2", oda=oda, cache=cache)
    assert fresh.dxf is not None and hit.dxf is not None and info(hit)["hit"] is True
    assert hit.dxf.stat().st_mode == fresh.dxf.stat().st_mode
    assert hit.dxf.stat().st_mtime >= fresh.dxf.stat().st_mtime


def test_stray_temp_file_does_not_block_a_new_cache(tmp_path, template, dwg):
    """Review N5: a killed writer's temp file in a not-yet-tagged cache is ours, not foreign."""
    root = tmp_path / "project" / ".cache"
    root.mkdir(parents=True)
    (root / ".tmp-abc123").write_text("half", encoding="utf-8")
    oda = fake(tmp_path, "oda", ODA_OUT, True, template)
    assert dwg_to_dxf(dwg, tmp_path / "w1", oda=oda, cache=ReadCache(root)).dxf is not None


def test_blob_vanishing_after_get_is_a_miss(tmp_path, template, dwg, cache, monkeypatch):
    """Review N6: a blob deleted between verification and delivery must not crash."""
    oda = fake(tmp_path, "oda", ODA_OUT, True, template)
    dwg_to_dxf(dwg, tmp_path / "w1", oda=oda, cache=cache)
    real_get = ReadCache.get

    def get_then_lose_blob(self, key):
        entry = real_get(self, key)
        if entry is not None:
            entry.output_path("output.dxf").unlink()
        return entry

    monkeypatch.setattr(ReadCache, "get", get_then_lose_blob)
    again = dwg_to_dxf(dwg, tmp_path / "w2", oda=oda, cache=cache)
    assert again.dxf is not None and info(again)["hit"] is False


@pytest.mark.parametrize(
    "change",
    [
        {"duration_ms": "slow"},
        {"duration_ms": -1},
        {"tool": 7},
        {"started_at": None},
        {"error": 5},
        {"tool_version": ["x"]},
    ],
)
def test_attempt_field_types_are_checked_on_replay(tmp_path, template, dwg, cache, change):
    """Review N7."""
    oda = fake(tmp_path, "oda", ODA_OUT, True, template)
    key = info(dwg_to_dxf(dwg, tmp_path / "w1", oda=oda, cache=cache))["key"]
    _corrupt_result(cache, key, lambda d: d["result"]["attempts"][0].update(change))
    assert info(dwg_to_dxf(dwg, tmp_path / "w2", oda=oda, cache=cache))["hit"] is False


def test_code_digest_covers_every_tekla_harness_module_convert_uses():
    """Review gap: dropping a module from _CODE_FILES must fail a test."""
    import inspect

    used = set()
    for value in vars(convert).values():
        module = inspect.getmodule(value)
        if module is not None and module.__name__.startswith("tekla_harness."):
            used.add(module.__name__.rsplit(".", 1)[1] + ".py")
    assert used <= set(convert._CODE_FILES), used - set(convert._CODE_FILES)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PATHEXT lookup")
def test_bare_name_resolves_through_pathext_on_windows(tmp_path, template, dwg, cache, monkeypatch):
    """Review gap: the production OS resolves `dwg2dxf` to `dwg2dxf.cmd` via PATHEXT."""
    script = fake(tmp_path, "libre", LIBRE_OUT, True, template)[1]
    bindir = tmp_path / "bin"
    bindir.mkdir()
    launcher = bindir / "dwg2dxf.cmd"
    launcher.write_text(f'@"{sys.executable}" "{script}" %*\n', encoding="utf-8")
    monkeypatch.setenv("PATH", str(bindir))
    monkeypatch.delenv("HARNESS_ODA_CONVERTER", raising=False)
    monkeypatch.delenv("HARNESS_DWG2DXF", raising=False)
    assert dwg_to_dxf(dwg, tmp_path / "w1", dwg2dxf=["dwg2dxf"], cache=cache).converter == "libredwg_dwg2dxf"
    launcher.write_text(launcher.read_text() + "rem upgraded\n", encoding="utf-8")
    assert info(dwg_to_dxf(dwg, tmp_path / "w2", dwg2dxf=["dwg2dxf"], cache=cache))["hit"] is False


def test_cli_cache_dir_and_refresh(tmp_path, template, dwg, capsys):
    oda = fake(tmp_path, "oda", ODA_OUT, True, template)
    cache_dir = tmp_path / "project" / ".cache"
    base = ["dwg2dxf", str(dwg), "--oda", oda[1], "--cache-dir", str(cache_dir)]
    # The CLI takes one executable; run the fake through the interpreter via a launcher file.
    launcher = tmp_path / ("oda.cmd" if sys.platform == "win32" else "oda.sh")
    if sys.platform == "win32":
        launcher.write_text(f'@"{sys.executable}" "{oda[1]}" %*\n', encoding="utf-8")
    else:
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{oda[1]}" "$@"\n', encoding="utf-8")
        launcher.chmod(0o755)
    base[3] = str(launcher)

    assert main([*base, "--out-dir", str(tmp_path / "w1")]) == 0
    assert json.loads(capsys.readouterr().out)["cache"]["hit"] is False
    assert main([*base, "--out-dir", str(tmp_path / "w2")]) == 0
    assert json.loads(capsys.readouterr().out)["cache"]["hit"] is True
    assert main([*base, "--out-dir", str(tmp_path / "w3"), "--refresh"]) == 0
    assert json.loads(capsys.readouterr().out)["cache"]["hit"] is False
