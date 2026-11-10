"""Tool wave 4, seam: the `text_visibility_uncertain` code and the `--include-hidden` flag with its stubs."""

from __future__ import annotations

from pathlib import Path

import pytest

from _callout_fixtures import REL, build_work
from tekla_harness import questions, questions_md_vi
from tekla_harness.cli import main
from tekla_harness.sheet_text import find_text, sheet_text


def test_text_visibility_uncertain_is_a_registered_code_with_vietnamese_copy():
    assert questions.TEXT_VISIBILITY_CODE == "text_visibility_uncertain"
    topic, need, impact = questions_md_vi.CODES["text_visibility_uncertain"]
    assert topic in {slug for slug, _ in questions_md_vi.TOPICS}
    assert need.strip() and impact.strip()


@pytest.fixture(scope="module")
def work(tmp_path_factory) -> Path:
    return build_work(tmp_path_factory.mktemp("wave4-seam"))


def test_include_hidden_is_stubbed_for_package_t(work):
    with pytest.raises(NotImplementedError, match="tool wave 4 package T"):
        sheet_text(work, REL, "model#01", include_hidden=True)
    with pytest.raises(NotImplementedError, match="tool wave 4 package T"):
        find_text(work, "S", include_hidden=True)


def test_default_calls_are_unchanged_by_the_new_keyword(work):
    assert sheet_text(work, REL, "model#01", include_hidden=False)["kind"] == "sheet_text"
    assert find_text(work, "S-101", include_hidden=False)["counts"]["hits"] >= 1


@pytest.mark.parametrize(
    "argv",
    [
        ["sheet-text", "{w}", REL, "model#01", "--include-hidden"],
        ["sheet-text", "{w}", REL, "model#01", "--include-hidden", "--region=0,0,10,10"],
        ["find-text", "{w}", "--contains", "S", "--include-hidden"],
    ],
)
def test_cli_flag_reaches_the_stub_and_exits_3(work, argv, capsys):
    code = main([a.replace("{w}", str(work)) for a in argv])
    assert code == 3
    assert "tool wave 4 package T" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["sheet-text", "find-text"])
def test_help_names_the_flag(command, capsys):
    assert main([command, "--help"]) == 0
    out = " ".join(capsys.readouterr().out.split())
    assert "--include-hidden" in out and "also show entries that do not print (marked)" in out
