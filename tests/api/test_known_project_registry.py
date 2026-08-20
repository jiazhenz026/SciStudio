"""The known-project registry survives a file that a newer build wrote.

Issue #2073. ``~/.scistudio/projects.json`` outlives the runtime that reads it:
it survives uninstall and reinstall, and the desktop client's OTA rollback
(``startRuntimeWithRollback`` in ``desktop/main.js``) can put an *older* runtime
in front of a file a newer one wrote. Because ``_save_known_projects`` persists
every dataclass field, such a file carries keys the older
:class:`~scistudio.api.runtime.models.KnownProject` has never heard of.

What makes this worth pinning is where the failure landed, not that it happened.
``_load_known_projects`` runs from ``ApiRuntime.__init__``, which runs inside the
FastAPI lifespan, so one unrecognised key did not degrade the project list — it
aborted server startup. The desktop client then reported nothing but an HTTP
timeout, and because the offending file is user-level, every relaunch, reinstall
and further rollback read it again, with no route back for the user.

These tests hold the two halves that keep that from recurring: an unknown key is
ignored, and a single unusable entry costs that entry rather than the process.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scistudio.api.app import create_app
from scistudio.api.runtime import ApiRuntime


@pytest.fixture()
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A SciStudio home patched before any runtime is constructed.

    The registry has to exist on disk *before* ``ApiRuntime.__init__`` runs,
    which is why these tests patch home themselves instead of reusing the
    ``client`` fixture — that one builds the app against an empty home.
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    from scistudio.api import runtime as runtime_module

    monkeypatch.setattr(runtime_module.Path, "home", classmethod(lambda cls: fake_home))
    return fake_home


def _write_registry(home: Path, projects: list[dict]) -> None:
    registry_dir = home / ".scistudio"
    registry_dir.mkdir(parents=True, exist_ok=True)
    (registry_dir / "projects.json").write_text(json.dumps({"projects": projects}), encoding="utf-8")


def test_entry_from_a_newer_build_loads_without_its_unknown_fields(isolated_home: Path) -> None:
    """Keys this build has never heard of are dropped, and the entry survives."""
    _write_registry(
        isolated_home,
        [
            {
                "id": "project-1",
                "name": "Demo",
                "path": str(isolated_home / "demo"),
                "description": "written by a later build",
                "last_opened": "2026-08-20T00:00:00+00:00",
                # Whatever a future KnownProject grows. The real report carried
                # tutorial_source_kind/tutorial_source_id/tutorial_id from #2057.
                "some_field_added_later": "value",
                "another_field_added_later": None,
            }
        ],
    )

    runtime = ApiRuntime()

    assert set(runtime.known_projects) == {"project-1"}
    loaded = runtime.known_projects["project-1"]
    assert loaded.name == "Demo"
    assert loaded.description == "written by a later build"
    assert not hasattr(loaded, "some_field_added_later")


def test_an_unusable_entry_is_skipped_rather_than_fatal(isolated_home: Path, caplog: pytest.LogCaptureFixture) -> None:
    """A malformed entry costs that entry, and says so, rather than the registry."""
    _write_registry(
        isolated_home,
        [
            {"id": "usable", "name": "Usable", "path": str(isolated_home / "usable")},
            # ``name`` has no default, so this one cannot be constructed at all.
            {"id": "nameless", "path": str(isolated_home / "nameless")},
        ],
    )

    with caplog.at_level(logging.WARNING):
        runtime = ApiRuntime()

    assert set(runtime.known_projects) == {"usable"}
    assert "nameless" in caplog.text


def test_the_api_starts_against_a_registry_from_a_newer_build(isolated_home: Path) -> None:
    """The regression that actually mattered: the server comes up and serves.

    ``ApiRuntime`` is constructed inside the lifespan, so before #2073 an
    unrecognised key raised during startup and uvicorn exited instead of
    listening — which is the state a user could not recover from.
    """
    _write_registry(
        isolated_home,
        [
            {
                "id": "project-1",
                "name": "Demo",
                "path": str(isolated_home / "demo"),
                "some_field_added_later": None,
            }
        ],
    )

    with TestClient(create_app()) as client:
        assert client.get("/api/projects/").status_code == 200
