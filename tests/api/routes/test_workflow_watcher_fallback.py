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


def test_first_party_workflow_write_suppresses_stale_watcher_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    yaml_path = project / "workflows" / "first-party.yaml"
    yaml_path.parent.mkdir(parents=True)
    yaml_path.write_text("id: first-party\nnodes: []\nedges: []\n", encoding="utf-8")
    runtime = _runtime_for_project(project, monkeypatch)
    version = runtime.bump_workflow_version("first-party")
    runtime.mark_workflow_first_party_write("first-party", version)

    handler, captured = _handler(project, runtime)
    yaml_path.unlink()
    handler.on_any_event(FileDeletedEvent(str(yaml_path)))

    assert captured == []
