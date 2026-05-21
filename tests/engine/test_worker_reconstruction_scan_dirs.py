"""Tests for #1365 — worker reconstruction sees project/user scan dirs.

Two layers exercised:

1. :func:`scistudio.core.types.serialization._get_type_registry` — the
   worker-side singleton — must register the same
   ``<project>/types`` + ``~/.scistudio/types`` scan dirs that
   :meth:`scistudio.api.runtime.ApiRuntime.refresh_type_registry`
   wires for the API path. The project root is discovered via the
   ``SCISTUDIO_PROJECT_DIR`` environment variable (the same contract
   used by :mod:`scistudio.cli.mcp_bridge` and the agent provisioning
   layer). Without this, a workflow that uses a drop-in
   :class:`DataObject` subclass under ``<project>/types`` resolves on
   the API side but the worker subprocess silently falls back to base
   :class:`DataObject` during reconstruction.

2. :class:`scistudio.engine.runners.local.LocalRunner` must propagate
   ``SCISTUDIO_PROJECT_DIR`` to the worker subprocess env so the
   worker can find the project's ``types/`` dir without needing the
   FastAPI runtime in-process.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from textwrap import dedent
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from scistudio.core.types import serialization as serialization_module
from scistudio.core.types.base import DataObject
from scistudio.core.types.serialization import _get_type_registry, _reconstruct_one
from scistudio.engine.runners.local import LocalRunner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_DROPIN_MODULE = """
from scistudio.core.types.base import DataObject


class ProjectDropInType(DataObject):
    \"\"\"Project-local drop-in DataObject used by the worker reconstruction tests.\"\"\"
"""


_USER_DROPIN_MODULE = """
from scistudio.core.types.base import DataObject


class UserDropInType(DataObject):
    \"\"\"User-wide drop-in DataObject used by the worker reconstruction tests.\"\"\"
"""


def _write_module(directory: Path, filename: str, body: str) -> Path:
    """Write *body* to ``directory/filename`` and return the path."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_text(dedent(body), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _reset_registry_singleton() -> Any:
    """Clear the worker-side TypeRegistry singleton between tests.

    The serialization module caches a process-singleton ``TypeRegistry``;
    without an explicit reset, the first test in this module would warm
    the singleton with whatever scan dirs the surrounding environment
    happens to have, and subsequent tests would not pick up their own
    isolated drop-in dirs.
    """
    serialization_module._registry_instance = None
    yield
    serialization_module._registry_instance = None


# ---------------------------------------------------------------------------
# Layer 1 — _get_type_registry consults project + user scan dirs
# ---------------------------------------------------------------------------


class TestGetTypeRegistryScanDirs:
    """``_get_type_registry`` wires project + user scan dirs (#1365)."""

    def test_project_dir_env_registers_project_types_dir(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``SCISTUDIO_PROJECT_DIR`` → ``<project>/types`` is scanned.

        This is the heart of the #1365 fix: when the API runtime opens a
        project, ``LocalRunner`` propagates the project path via
        ``SCISTUDIO_PROJECT_DIR``; the worker's ``_get_type_registry``
        adds ``<project>/types`` to the registry's scan dirs before the
        first ``reconstruct_inputs`` call.
        """
        project_dir = tmp_path / "my-project"
        _write_module(project_dir / "types", "project_type.py", _DROPIN_MODULE)
        # Isolate Path.home() so the user-wide dir does not bleed in.
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("SCISTUDIO_PROJECT_DIR", str(project_dir))
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        registry = _get_type_registry()

        assert "ProjectDropInType" in registry.all_types()
        # Built-ins must still register (the new path must not displace them).
        assert "DataObject" in registry.all_types()

    def test_user_wide_types_dir_is_always_scanned(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``~/.scistudio/types`` is scanned even without ``SCISTUDIO_PROJECT_DIR``.

        CLI standalone runs and tests do not always have a project root;
        the user-wide dir must still register so plugin authors and end
        users can rely on a stable shared types location.
        """
        fake_home = tmp_path / "home"
        _write_module(fake_home / ".scistudio" / "types", "user_type.py", _USER_DROPIN_MODULE)
        monkeypatch.delenv("SCISTUDIO_PROJECT_DIR", raising=False)
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        registry = _get_type_registry()

        assert "UserDropInType" in registry.all_types()

    def test_empty_project_dir_env_is_treated_as_unset(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Whitespace-only ``SCISTUDIO_PROJECT_DIR`` does not add a junk dir.

        Matches the ``mcp_bridge`` contract — both consumers strip and
        treat an empty value as "not set".
        """
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("SCISTUDIO_PROJECT_DIR", "   ")
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        # Must not raise; registry is built with only the user-wide dir.
        registry = _get_type_registry()
        assert "DataObject" in registry.all_types()

    def test_worker_reconstruct_one_finds_project_drop_in(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """End-to-end #1365: a wire-format payload referencing a project
        drop-in type reconstructs as the concrete subclass.

        Before #1365 was fixed, ``_reconstruct_one`` saw an unknown
        chain and fell back to bare ``DataObject``. After the fix the
        worker singleton has the project's ``types/`` dir wired and
        :meth:`TypeRegistry.resolve` returns the concrete drop-in.
        """
        project_dir = tmp_path / "ws"
        _write_module(project_dir / "types", "wf_type.py", _DROPIN_MODULE)
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("SCISTUDIO_PROJECT_DIR", str(project_dir))
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        # Force the singleton to scan with our env var set.
        _get_type_registry()

        payload = {
            "backend": None,
            "path": None,
            "format": None,
            "metadata": {
                "type_chain": ["DataObject", "ProjectDropInType"],
                "framework": {},
                "meta": None,
                "user": {},
            },
        }
        obj = _reconstruct_one(payload)

        # Concrete drop-in class, NOT base DataObject fallback.
        assert type(obj).__name__ == "ProjectDropInType"
        assert isinstance(obj, DataObject)


# ---------------------------------------------------------------------------
# Layer 2 — LocalRunner propagates SCISTUDIO_PROJECT_DIR to worker env
# ---------------------------------------------------------------------------


def _make_async_proc(stdout: bytes, stderr: bytes, returncode: int) -> AsyncMock:
    proc = AsyncMock()
    proc.pid = 9999
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    return proc


class TestLocalRunnerPropagatesProjectDirEnv:
    """``LocalRunner`` injects ``SCISTUDIO_PROJECT_DIR`` into worker env (#1365)."""

    @patch("scistudio.engine.runners.local.asyncio.create_subprocess_exec")
    def test_project_dir_env_propagated_when_active_project(
        self,
        mock_create_sub: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """``config['project_dir']`` lands on the worker subprocess env.

        Without this propagation the worker-side ``_get_type_registry``
        does not know which project root to scan and falls back to the
        user-wide dir only.
        """
        mock_create_sub.return_value = _make_async_proc(json.dumps({"outputs": {}}).encode(), b"", 0)
        runner = LocalRunner()
        project_dir = tmp_path / "project-root"
        project_dir.mkdir()

        class FakeBlock:
            pass

        asyncio.run(runner.run(FakeBlock(), {}, {"project_dir": str(project_dir)}))

        call_kwargs = mock_create_sub.call_args.kwargs
        env = call_kwargs.get("env")
        assert env is not None, "worker env must be set when project_dir is known"
        assert env.get("SCISTUDIO_PROJECT_DIR") == str(project_dir)

    @patch("scistudio.engine.runners.local.asyncio.create_subprocess_exec")
    def test_project_dir_env_absent_without_active_project(
        self,
        mock_create_sub: AsyncMock,
    ) -> None:
        """No ``project_dir`` → no ``SCISTUDIO_PROJECT_DIR`` injection.

        Standalone CLI runs inherit the parent env unchanged; if the
        parent already exported the var (e.g. inside a Codex/Claude
        agent-provisioning context) the worker will see it via the
        default parent inheritance path, not via this explicit override.
        """
        mock_create_sub.return_value = _make_async_proc(json.dumps({"outputs": {}}).encode(), b"", 0)
        runner = LocalRunner()

        class FakeBlock:
            pass

        asyncio.run(runner.run(FakeBlock(), {}, {}))

        call_kwargs = mock_create_sub.call_args.kwargs
        # When no project is active, LocalRunner passes env=None and the
        # subprocess inherits the parent's env unchanged.
        assert call_kwargs.get("env") is None

    @patch("scistudio.engine.runners.local.asyncio.create_subprocess_exec")
    def test_project_dir_env_coexists_with_pythonpath_override(
        self,
        mock_create_sub: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Both the PYTHONPATH override and ``SCISTUDIO_PROJECT_DIR`` land.

        Regression guard: the two env-fixup blocks must compose, not
        clobber each other.
        """
        mock_create_sub.return_value = _make_async_proc(json.dumps({"outputs": {}}).encode(), b"", 0)
        runner = LocalRunner()
        project_dir = tmp_path / "project-root"
        project_dir.mkdir()
        parent_cwd = os.getcwd()

        class FakeBlock:
            pass

        asyncio.run(runner.run(FakeBlock(), {}, {"project_dir": str(project_dir)}))

        call_kwargs = mock_create_sub.call_args.kwargs
        env = call_kwargs.get("env")
        assert env is not None
        assert env.get("SCISTUDIO_PROJECT_DIR") == str(project_dir)
        assert parent_cwd in env.get("PYTHONPATH", "").split(os.pathsep)
