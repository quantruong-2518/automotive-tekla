from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOKS = REPO / ".claude" / "hooks"
EXAMPLES = REPO / "schemas" / "examples"
# A Windows console without UTF-8: the hooks' own stdin, stdout and stderr must not depend on it.
LEGACY_CONSOLE_ENV = {"PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"}


def load_hook(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, HOOKS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def guard() -> ModuleType:
    return load_hook("guard_tekla_write")


@pytest.fixture
def env_check() -> ModuleType:
    return load_hook("session_env_check")


@pytest.fixture
def example():
    def _load(name: str) -> dict:
        return json.loads((EXAMPLES / f"{name}.example.json").read_text(encoding="utf-8"))

    return _load
