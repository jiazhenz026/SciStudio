"""ADR-036 §3.5 (I36c) — reload-on-save hook for blocks/*.py.

Covers the contract:
  - Saving a clean ``blocks/foo.py`` triggers ``BlockRegistry.hot_reload()``
    and emits a ``blocks.reloaded`` engine event.
  - Saving a syntactically broken ``blocks/foo.py`` saves the file but
    does NOT trigger reload (lint diagnostics non-empty).
  - Saving a non-Python file (or a ``.py`` outside ``blocks/``) is a no-op
    for the hook.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scieasy.api.routes import projects as projects_module


def _open(client: TestClient, project_path: Path) -> str:
    """Create + open a project so the runtime tracks active_project."""
    response = client.post(
        "/api/projects/",
        json={"name": "T", "description": "", "path": str(project_path)},
    )
    assert response.status_code == 200, response.text
    project_id = response.json()["id"]
    client.get(f"/api/projects/{project_id}")
    return project_id


def _ensure_blocks_dir(client: TestClient, project_id: str) -> Path:
    project_root = Path(client.app.state.runtime.known_projects[project_id].path)
    blocks_dir = project_root / "blocks"
    blocks_dir.mkdir(exist_ok=True)
    return blocks_dir


@pytest.fixture()
def captured_events(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Capture every EngineEvent emitted via runtime.event_bus.emit.

    We patch the EventBus.emit method so we observe ALL events without
    coupling to a specific subscriber.
    """
    captured: list[dict] = []

    from scieasy.engine import events as events_module

    original_emit = events_module.EventBus.emit

    async def _spy_emit(self, event):  # type: ignore[no-untyped-def]
        captured.append({"type": event.event_type, "data": dict(event.data or {})})
        await original_emit(self, event)

    monkeypatch.setattr(events_module.EventBus, "emit", _spy_emit)
    return captured


def test_clean_block_save_triggers_reload_and_event(
    client: TestClient,
    project_parent: Path,
    captured_events: list[dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clean blocks/<name>.py PUT -> hot_reload + blocks.reloaded event."""
    pid = _open(client, project_parent / "p_clean")
    _ensure_blocks_dir(client, pid)

    runtime = client.app.state.runtime
    reload_calls = {"count": 0}

    original_hot_reload = runtime.block_registry.hot_reload

    def _spy_hot_reload() -> None:
        reload_calls["count"] += 1
        original_hot_reload()

    monkeypatch.setattr(runtime.block_registry, "hot_reload", _spy_hot_reload)

    clean_source = "x = 1\n"
    r = client.put(
        f"/api/projects/{pid}/file?path=blocks/clean_block.py",
        json={"content": clean_source},
    )
    assert r.status_code == 200, r.text

    assert reload_calls["count"] == 1, "hot_reload was not called for a clean blocks/*.py save"

    blocks_reloaded = [evt for evt in captured_events if evt["type"] == "blocks.reloaded"]
    assert len(blocks_reloaded) == 1, (
        f"Expected exactly one blocks.reloaded event; saw types: {[evt['type'] for evt in captured_events]}"
    )
    payload = blocks_reloaded[0]["data"]
    assert "added" in payload
    assert "removed" in payload
    assert "reloaded" in payload
    assert "clean_block.py" in payload["reloaded"]


def test_broken_block_save_does_not_reload_or_emit(
    client: TestClient,
    project_parent: Path,
    captured_events: list[dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Syntactically broken blocks/*.py is saved but reload + event are skipped.

    We ensure ruff is on PATH (skip otherwise) — without ruff, lint
    soft-fails to "no diagnostics" and the hook would reload anyway.
    """
    if shutil.which("ruff") is None:
        pytest.skip("ruff not on PATH; lint soft-fails so this test is meaningless")

    pid = _open(client, project_parent / "p_broken")
    _ensure_blocks_dir(client, pid)

    runtime = client.app.state.runtime
    reload_calls = {"count": 0}

    def _spy_hot_reload() -> None:
        reload_calls["count"] += 1

    monkeypatch.setattr(runtime.block_registry, "hot_reload", _spy_hot_reload)

    # SyntaxError on purpose. ruff catches this as E999.
    broken_source = "def oops(:\n    pass\n"
    r = client.put(
        f"/api/projects/{pid}/file?path=blocks/broken_block.py",
        json={"content": broken_source},
    )
    assert r.status_code == 200, r.text

    assert reload_calls["count"] == 0, "hot_reload should not run when lint reports diagnostics"

    blocks_reloaded = [evt for evt in captured_events if evt["type"] == "blocks.reloaded"]
    assert blocks_reloaded == [], f"blocks.reloaded must NOT fire when lint flags the file; saw: {blocks_reloaded}"


def test_non_blocks_py_does_not_reload(
    client: TestClient,
    project_parent: Path,
    captured_events: list[dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A clean ``.py`` outside ``blocks/`` is a no-op for the hook."""
    pid = _open(client, project_parent / "p_outside")

    runtime = client.app.state.runtime
    reload_calls = {"count": 0}
    monkeypatch.setattr(
        runtime.block_registry,
        "hot_reload",
        lambda: reload_calls.__setitem__("count", reload_calls["count"] + 1),
    )

    # Write a .py at project root (allowlist permits .py).
    r = client.put(
        f"/api/projects/{pid}/file?path=top_level_script.py",
        json={"content": "x = 1\n"},
    )
    assert r.status_code == 200, r.text
    assert reload_calls["count"] == 0
    assert not any(evt["type"] == "blocks.reloaded" for evt in captured_events)


def test_is_under_project_blocks_dir_helper(tmp_path: Path) -> None:
    """Unit-level coverage for the path-classification helper."""
    project_root = tmp_path / "proj"
    (project_root / "blocks").mkdir(parents=True)
    yes = project_root / "blocks" / "foo.py"
    yes.write_text("x=1")
    assert projects_module._is_under_project_blocks_dir(project_root, yes) is True

    not_py = project_root / "blocks" / "notes.md"
    not_py.write_text("# hi")
    assert projects_module._is_under_project_blocks_dir(project_root, not_py) is False

    outside = project_root / "scratch.py"
    outside.write_text("x=1")
    assert projects_module._is_under_project_blocks_dir(project_root, outside) is False

    # None project_root short-circuits.
    assert projects_module._is_under_project_blocks_dir(None, yes) is False
