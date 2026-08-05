"""Tests for the post-run artifact retention trigger (#1983).

Retention is wired to the completion of a successful run because that is the
moment the "keep the most recent successful run" rule gains a new run to keep.
A scientist should not have to remember to invoke a cleanup command — the 16 GB
that motivated #1983 accumulated precisely because nobody ever did.
"""

from __future__ import annotations

import pytest

from scistudio.api.runtime import _runs


class _Project:
    def __init__(self, path: str) -> None:
        self.path = path


class _Runtime:
    def __init__(self, path: str | None) -> None:
        self.active_project = _Project(path) if path is not None else None


def test_retention_is_enabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(_runs._RETENTION_ENV_VAR, raising=False)

    assert _runs._artifact_retention_enabled() is True


@pytest.mark.parametrize("value", ["0", "false", "off", "no", "OFF", " false "])
def test_retention_can_be_switched_off(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(_runs._RETENTION_ENV_VAR, value)

    assert _runs._artifact_retention_enabled() is False


def test_schedule_sweeps_inline_without_a_running_loop(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    monkeypatch.delenv(_runs._RETENTION_ENV_VAR, raising=False)
    seen: list[str] = []
    monkeypatch.setattr(_runs, "_reclaim_artifacts_blocking", lambda project_dir: seen.append(project_dir))

    _runs._schedule_artifact_retention(_Runtime("/tmp/project"))

    assert seen == ["/tmp/project"]


def test_schedule_is_a_no_op_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_runs._RETENTION_ENV_VAR, "off")
    seen: list[str] = []
    monkeypatch.setattr(_runs, "_reclaim_artifacts_blocking", lambda project_dir: seen.append(project_dir))

    _runs._schedule_artifact_retention(_Runtime("/tmp/project"))

    assert seen == []


def test_schedule_is_a_no_op_without_an_active_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(_runs._RETENTION_ENV_VAR, raising=False)
    seen: list[str] = []
    monkeypatch.setattr(_runs, "_reclaim_artifacts_blocking", lambda project_dir: seen.append(project_dir))

    _runs._schedule_artifact_retention(_Runtime(None))

    assert seen == []
