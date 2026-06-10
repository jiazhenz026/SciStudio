"""ADR-045 watcher fallback tests for workflow state changes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from watchdog.events import FileDeletedEvent, FileModifiedEvent

from scistudio.api import runtime as runtime_module
from scistudio.api.routes.workflow_watcher import _WorkflowFileHandler
from scistudio.api.runtime import ApiRuntime, KnownProject


def _runtime_for_project(project: Path, monkeypatch: pytest.MonkeyPatch) -> ApiRuntime:
    fake_home = project.parent / "home"
    fake_home.mkdir(exist_ok=True)
    monkeypatch.setattr(runtime_module.Path, "home", classmethod(lambda cls: fake_home))
    runtime = ApiRuntime()
    runtime.active_project = KnownProject(
        id="watcher-project",
        name="Watcher Project",
        path=str(project),
    )
    runtime.reset_version_state_for_project(project)
    return runtime


def _handler(project: Path, runtime: ApiRuntime) -> tuple[_WorkflowFileHandler, list[dict[str, Any]]]:
    captured: list[dict[str, Any]] = []
    handler = _WorkflowFileHandler(
        project_dir=project,
        broadcast=lambda payload: captured.append(payload),
        loop=None,
        runtime=runtime,
    )
    return handler, captured


def test_external_workflow_write_emits_versioned_external_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    yaml_path = project / "workflows" / "external.yaml"
    yaml_path.parent.mkdir(parents=True)
    yaml_path.write_text("id: external\nnodes: []\nedges: []\n", encoding="utf-8")
    runtime = _runtime_for_project(project, monkeypatch)
    baseline = runtime.current_workflow_version("external")

    handler, captured = _handler(project, runtime)
    yaml_path.write_text("id: external\ndescription: changed\nnodes: []\nedges: []\n", encoding="utf-8")
    handler.on_any_event(FileModifiedEvent(str(yaml_path)))

    assert len(captured) == 1
    payload = captured[0]
    assert payload["type"] == "workflow.changed"
    assert payload["entity_class"] == "workflow"
    assert payload["entity_id"] == "external"
    assert payload["workflow_id"] == "external"
    assert payload["source"] == "external"
    assert payload["source_id"] is None
    assert payload["kind"] == "modified"
    assert payload["version"] == baseline + 1
    assert payload["timestamp"]


def test_first_party_workflow_write_suppresses_only_exact_echo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    yaml_path = project / "workflows" / "first-party.yaml"
    yaml_path.parent.mkdir(parents=True)
    yaml_path.write_text("id: first-party\nnodes: []\nedges: []\n", encoding="utf-8")
    runtime = _runtime_for_project(project, monkeypatch)
    version = runtime.bump_workflow_version("first-party")
    runtime.mark_workflow_first_party_write("first-party", version, path=yaml_path, kind="modified")

    handler, captured = _handler(project, runtime)
    handler.on_any_event(FileModifiedEvent(str(yaml_path)))
    assert captured == []

    yaml_path.write_text(
        "id: first-party\ndescription: external after first party\nnodes: []\nedges: []\n",
        encoding="utf-8",
    )
    handler.on_any_event(FileModifiedEvent(str(yaml_path)))

    assert len(captured) == 1
    payload = captured[0]
    assert payload["source"] == "external"
    assert payload["version"] == version + 1


def test_runtime_mode_ignores_legacy_self_write_deque(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-045 §5.1 #3 (NARROW) / #1461: with a runtime wired, the workflow
    handler suppresses self-writes via the version-vector signature only — the
    legacy ``(path, mtime, size)`` deque is NOT consulted.

    We register a deque self-write (``mark_self_write``) but DO NOT register a
    first-party version signature. Pre-narrowing the deque alone would suppress
    the event; post-narrowing the runtime path ignores the deque, so the event
    is emitted as a normal external change.
    """
    project = tmp_path / "project"
    yaml_path = project / "workflows" / "deque-only.yaml"
    yaml_path.parent.mkdir(parents=True)
    yaml_path.write_text("id: deque-only\nnodes: []\nedges: []\n", encoding="utf-8")
    runtime = _runtime_for_project(project, monkeypatch)
    baseline = runtime.current_workflow_version("deque-only")

    handler, captured = _handler(project, runtime)
    # Modify the file so the disk-version delayed-echo guard passes (new
    # mtime > cached), isolating the deque as the only possible suppressor.
    yaml_path.write_text("id: deque-only\ndescription: changed\nnodes: []\nedges: []\n", encoding="utf-8")
    # Populate ONLY the legacy deque (with the new content's signature) — no
    # first-party version signature is registered.
    handler.mark_self_write(yaml_path)
    handler.on_any_event(FileModifiedEvent(str(yaml_path)))

    # The deque is bypassed in runtime mode → event still emitted.
    assert len(captured) == 1
    assert captured[0]["source"] == "external"
    assert captured[0]["version"] == baseline + 1


def test_fallback_mode_still_uses_self_write_deque(tmp_path: Path) -> None:
    """ADR-045 §5.1 #3: the deque remains the only first-party signal in the
    runtime-less (drift-detector / degraded) path, so it must still suppress."""
    project = tmp_path / "project"
    yaml_path = project / "workflows" / "fallback.yaml"
    yaml_path.parent.mkdir(parents=True)
    yaml_path.write_text("id: fallback\nnodes: []\nedges: []\n", encoding="utf-8")

    captured: list[dict[str, Any]] = []
    handler = _WorkflowFileHandler(
        project_dir=project,
        broadcast=lambda payload: captured.append(payload),
        loop=None,
        runtime=None,
    )
    handler.mark_self_write(yaml_path)
    handler.on_any_event(FileModifiedEvent(str(yaml_path)))
    assert captured == []


def test_first_party_workflow_delete_suppresses_exact_delete_echo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    yaml_path = project / "workflows" / "deleted-first-party.yaml"
    yaml_path.parent.mkdir(parents=True)
    yaml_path.write_text("id: deleted-first-party\nnodes: []\nedges: []\n", encoding="utf-8")
    runtime = _runtime_for_project(project, monkeypatch)
    version = runtime.bump_workflow_version("deleted-first-party")
    yaml_path.unlink()
    runtime.mark_workflow_first_party_write("deleted-first-party", version, path=yaml_path, kind="deleted")

    handler, captured = _handler(project, runtime)
    handler.on_any_event(FileDeletedEvent(str(yaml_path)))

    assert captured == []
