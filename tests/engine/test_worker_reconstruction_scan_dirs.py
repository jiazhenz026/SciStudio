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

    def test_builtins_scan_failure_is_not_swallowed(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Codex P2 on PR #1386 — built-in scan failures MUST propagate.

        ``_get_type_registry`` previously wrapped the whole ``scan_all()``
        call in ``contextlib.suppress(Exception)`` so a single broken
        plugin would not prevent reconstruction. The same suppress also
        swallowed any failure inside ``scan_builtins()`` and cached a
        partially-initialised singleton, silently degrading every
        subsequent typed reconstruction to bare ``DataObject``.

        After the fix ``scan_builtins()`` is called outside the
        suppress block, so an injected failure surfaces here rather
        than at a downstream resolve() call site.
        """
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.delenv("SCISTUDIO_PROJECT_DIR", raising=False)
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        # Inject a failure inside ``TypeRegistry.scan_builtins`` to prove
        # the suppress no longer covers built-in registration.
        from scistudio.core.types.registry import TypeRegistry

        def _boom(self: TypeRegistry) -> None:
            raise RuntimeError("synthetic built-in failure for #1365 regression")

        monkeypatch.setattr(TypeRegistry, "scan_builtins", _boom)

        with pytest.raises(RuntimeError, match="synthetic built-in failure"):
            _get_type_registry()

        # Singleton must not be cached after the failure — a subsequent
        # call (with the monkeypatch undone by the fixture) must rebuild.
        assert serialization_module._registry_instance is None

    def test_plugin_scan_failure_is_swallowed(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Symmetric guarantee: a broken plugin entry-point or drop-in
        scan MUST still be best-effort, so the worker can reconstruct
        core types even when one plugin is misbehaving.
        """
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.delenv("SCISTUDIO_PROJECT_DIR", raising=False)
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        from scistudio.core.types.registry import TypeRegistry

        def _boom(self: TypeRegistry) -> None:
            raise RuntimeError("synthetic plugin failure")

        # Break entry-point scan; built-ins must still register.
        monkeypatch.setattr(TypeRegistry, "_scan_entrypoint_types", _boom)

        registry = _get_type_registry()
        # Built-ins are present despite the plugin failure.
        assert "DataObject" in registry.all_types()
        assert "Array" in registry.all_types()

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
        # Absolutified by LocalRunner before export (Codex P2 on PR #1386).
        assert env.get("SCISTUDIO_PROJECT_DIR") == str(project_dir.resolve())

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
        # Absolutified by LocalRunner before export (Codex P2 on PR #1386).
        assert env.get("SCISTUDIO_PROJECT_DIR") == str(project_dir.resolve())
        assert parent_cwd in env.get("PYTHONPATH", "").split(os.pathsep)

    @patch("scistudio.engine.runners.local.asyncio.create_subprocess_exec")
    def test_relative_project_dir_is_absolutified_before_export(
        self,
        mock_create_sub: AsyncMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Codex P2 on PR #1386 — a relative ``config['project_dir']`` MUST
        be absolutified before landing on ``SCISTUDIO_PROJECT_DIR``.

        The worker subprocess is started with ``cwd=project_dir`` (see
        the assignment a few lines above the env block in
        ``LocalRunner.run``). If we passed a relative path through
        verbatim, the worker would later resolve
        ``Path(project_dir_env) / "types"`` against its own (already-
        switched) cwd, producing ``<project>/<project>/types`` and
        silently missing every project drop-in type.
        """
        mock_create_sub.return_value = _make_async_proc(json.dumps({"outputs": {}}).encode(), b"", 0)
        runner = LocalRunner()

        project_root = tmp_path / "rel-root"
        project_root.mkdir()
        monkeypatch.chdir(tmp_path)
        relative_project_dir = "rel-root"

        class FakeBlock:
            pass

        asyncio.run(runner.run(FakeBlock(), {}, {"project_dir": relative_project_dir}))

        call_kwargs = mock_create_sub.call_args.kwargs
        env = call_kwargs.get("env")
        assert env is not None
        exported = env.get("SCISTUDIO_PROJECT_DIR")
        assert exported is not None
        # The exported value must be an absolute path, not the original relative one.
        assert Path(exported).is_absolute(), f"expected absolute path, got: {exported!r}"
        # And it must resolve to the same real directory the test created.
        assert Path(exported) == project_root.resolve()
