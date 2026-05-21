"""Tests for RunnerRegistry — language-to-runner mapping."""

from __future__ import annotations

import pytest

from scistudio.blocks.code.runner_registry import RunnerRegistry
from scistudio.blocks.code.runners.python_runner import PythonRunner


class _FakeRunner:
    """Fake runner for testing registration."""

    pass


class TestRunnerRegistry:
    """RunnerRegistry — register, get, defaults, all_runners."""

    def test_register_and_get(self) -> None:
        reg = RunnerRegistry()
        reg.register("python", _FakeRunner)
        assert reg.get("python") is _FakeRunner

    def test_get_case_insensitive(self) -> None:
        reg = RunnerRegistry()
        reg.register("python", _FakeRunner)
        assert reg.get("PYTHON") is _FakeRunner
        assert reg.get("Python") is _FakeRunner

    def test_get_unknown_raises(self) -> None:
        reg = RunnerRegistry()
        with pytest.raises(KeyError, match="No runner registered for language 'fortran'"):
            reg.get("fortran")

    def test_register_defaults(self) -> None:
        reg = RunnerRegistry()
        reg.register_defaults()
        assert reg.get("python") is PythonRunner
        assert reg.get("r") is not None
        assert reg.get("julia") is not None

    def test_all_runners(self) -> None:
        reg = RunnerRegistry()
        reg.register("python", _FakeRunner)
        result = reg.all_runners()
        assert result == {"python": _FakeRunner}

    def test_all_runners_returns_copy(self) -> None:
        reg = RunnerRegistry()
        reg.register("python", _FakeRunner)
        copy = reg.all_runners()
        copy["new"] = _FakeRunner
        assert "new" not in reg.all_runners()
