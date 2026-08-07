"""ADR-036 §3.5 (I36c) — reload-on-save hook for blocks/*.py and types/*.py.

Covers the contract:
  - Saving a clean ``blocks/foo.py`` triggers ``refresh_all_registries()``
    and emits a ``blocks.reloaded`` engine event.
  - Saving a syntactically broken ``blocks/foo.py`` saves the file but
    does NOT trigger reload (lint diagnostics non-empty).
  - Saving a non-Python file (or a ``.py`` outside the drop-in tiers) is a
    no-op for the hook.

ADR-053 FR-062 / #2022 widened the hook twice: ``{project}/types`` is a
drop-in tier exactly as ``{project}/blocks`` is, so a save there now reaches
the hook at all; and the reload is the unified ``refresh_all_registries()``
rather than ``block_registry.hot_reload()``, so a type or previewer change is
picked up the way a block change is. The behavioural half of that is pinned in
``tests/api/test_registry_reload_symmetry.py``; these tests pin the hook's own
gating, which is why they moved from spying on ``hot_reload`` to spying on the
entry point that replaced it.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scistudio.api.routes import projects as projects_module


def _open(client: TestClient, project_path: Path) -> str:
    """Create + open a project so the runtime tracks active_project."""
    response = client.post(
        "/api/projects/",
        json={"name": "T", "description": "", "path": str(project_path)},
    )
    assert response.status_code == 200, response.text
    project_id = str(response.json()["id"])
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

    from scistudio.engine import events as events_module

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
    """Clean blocks/<name>.py PUT -> refresh_all_registries + blocks.reloaded."""
    pid = _open(client, project_parent / "p_clean")
    _ensure_blocks_dir(client, pid)

    runtime = client.app.state.runtime
    reload_calls = {"count": 0}

    original_refresh = runtime.refresh_all_registries

    def _spy_refresh() -> None:
        reload_calls["count"] += 1
        original_refresh()

    monkeypatch.setattr(runtime, "refresh_all_registries", _spy_refresh)

    clean_source = "x = 1\n"
    r = client.put(
        f"/api/projects/{pid}/file?path=blocks/clean_block.py",
        json={"content": clean_source},
    )
    assert r.status_code == 200, r.text
    saved = r.json()
    assert saved["state_version"] > 0
    assert saved["entity_id"] == "blocks/clean_block.py"

    assert reload_calls["count"] == 1, "refresh_all_registries was not called for a clean blocks/*.py save"

    file_changed = [evt for evt in captured_events if evt["type"] == projects_module.FILE_CHANGED_EVENT_TYPE]
    assert len(file_changed) == 1
    assert file_changed[0]["data"]["version"] == saved["state_version"]
    assert file_changed[0]["data"]["entity_id"] == "blocks/clean_block.py"

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

    def _spy_refresh() -> None:
        reload_calls["count"] += 1

    monkeypatch.setattr(runtime, "refresh_all_registries", _spy_refresh)

    # SyntaxError on purpose. ruff catches this as E999.
    broken_source = "def oops(:\n    pass\n"
    r = client.put(
        f"/api/projects/{pid}/file?path=blocks/broken_block.py",
        json={"content": broken_source},
    )
    assert r.status_code == 200, r.text
    saved = r.json()
    assert saved["state_version"] > 0
    assert saved["entity_id"] == "blocks/broken_block.py"

    assert reload_calls["count"] == 0, "the reload must not run when lint reports diagnostics"

    file_changed = [evt for evt in captured_events if evt["type"] == projects_module.FILE_CHANGED_EVENT_TYPE]
    assert len(file_changed) == 1
    assert file_changed[0]["data"]["version"] == saved["state_version"]
    assert file_changed[0]["data"]["entity_id"] == "blocks/broken_block.py"

    blocks_reloaded = [evt for evt in captured_events if evt["type"] == "blocks.reloaded"]
    assert blocks_reloaded == [], f"blocks.reloaded must NOT fire when lint flags the file; saw: {blocks_reloaded}"


def test_non_blocks_py_does_not_reload(
    client: TestClient,
    project_parent: Path,
    captured_events: list[dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A clean ``.py`` outside the drop-in tiers is a no-op for the hook."""
    pid = _open(client, project_parent / "p_outside")

    runtime = client.app.state.runtime
    reload_calls = {"count": 0}
    monkeypatch.setattr(
        runtime,
        "refresh_all_registries",
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


def test_project_dropin_dir_helper_classifies_both_tiers(tmp_path: Path) -> None:
    """ADR-053 FR-062 / #2022: ``types/`` reaches the hook, ``docs/`` does not."""
    project_root = tmp_path / "proj"
    (project_root / "types").mkdir(parents=True)
    (project_root / "docs").mkdir()

    assert projects_module._project_dropin_dir(project_root, project_root / "blocks" / "foo.py") == "blocks"
    assert projects_module._project_dropin_dir(project_root, project_root / "types" / "foo.py") == "types"
    assert projects_module._project_dropin_dir(project_root, project_root / "docs" / "foo.py") is None
    assert projects_module._project_dropin_dir(project_root, project_root / "types" / "notes.md") is None
    assert projects_module._project_dropin_dir(None, project_root / "types" / "foo.py") is None
