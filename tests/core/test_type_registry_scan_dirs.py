"""Tests for :meth:`TypeRegistry.add_scan_dir` (issue #1332).

ARCHITECTURE.md §10 + §10.5 commit the runtime to discovering local custom
:class:`DataObject` subclasses from two filesystem locations:

- ``<project>/types/`` — project-local drop-in types
- ``~/.scistudio/types/`` — user-wide drop-in types shared across projects

Issue #1332 (P1, audit P1-3): the documentation claim was previously
implemented for :class:`BlockRegistry` only (``add_scan_dir`` + project +
user-wide wiring in :class:`ApiRuntime`); :class:`TypeRegistry` had only
built-ins + ``scistudio.types`` entry-points + optional monorepo. This
test module exercises the new :meth:`TypeRegistry.add_scan_dir` path and
the :meth:`ApiRuntime.refresh_type_registry` wiring that catches the impl
up to the doc commitment.
"""

from __future__ import annotations

import logging
from pathlib import Path
from textwrap import dedent

import pytest

from scistudio.core.types.registry import TypeRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_module(directory: Path, filename: str, body: str) -> Path:
    """Write *body* to ``directory/filename`` and return the path."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_text(dedent(body), encoding="utf-8")
    return path


_GOOD_MODULE = """
from scistudio.core.types.base import DataObject


class CustomDropInType(DataObject):
    \"\"\"Drop-in DataObject subclass used by the scan-dir tests.\"\"\"
"""


_TWO_TYPES_MODULE = """
from scistudio.core.types.base import DataObject


class FirstDropInType(DataObject):
    \"\"\"First drop-in DataObject.\"\"\"


class SecondDropInType(DataObject):
    \"\"\"Second drop-in DataObject.\"\"\"
"""


_BROKEN_MODULE = """
this is not valid python
"""


_NOT_A_DATAOBJECT_MODULE = """
class NotADataObject:
    \"\"\"Plain class — must not be registered.\"\"\"
"""


# ---------------------------------------------------------------------------
# Direct TypeRegistry tests
# ---------------------------------------------------------------------------


class TestAddScanDir:
    """``TypeRegistry.add_scan_dir`` + ``scan_all`` discover drop-in types."""

    def test_add_scan_dir_picks_up_drop_in_type(self, tmp_path: Path) -> None:
        """A DataObject subclass in a scanned dir is registered by scan_all."""
        scan_dir = tmp_path / "types"
        _write_module(scan_dir, "custom_type.py", _GOOD_MODULE)

        registry = TypeRegistry()
        registry.add_scan_dir(scan_dir)
        registry.scan_all()

        assert "CustomDropInType" in registry.all_types()
        # Sanity: built-ins still register (the new path must not displace them).
        assert "DataObject" in registry.all_types()
        assert "Array" in registry.all_types()

    def test_multiple_drop_in_types_per_file_register(self, tmp_path: Path) -> None:
        """A single drop-in file declaring two types registers both."""
        scan_dir = tmp_path / "types"
        _write_module(scan_dir, "two_types.py", _TWO_TYPES_MODULE)

        registry = TypeRegistry()
        registry.add_scan_dir(scan_dir)
        registry.scan_all()

        assert "FirstDropInType" in registry.all_types()
        assert "SecondDropInType" in registry.all_types()

    def test_nonexistent_scan_dir_is_skipped_silently(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A registered scan dir that does not exist must not raise."""
        missing = tmp_path / "does_not_exist"
        registry = TypeRegistry()
        registry.add_scan_dir(missing)

        with caplog.at_level(logging.DEBUG, logger="scistudio.core.types.registry"):
            registry.scan_all()  # must not raise

        # Built-ins still register and only the missing dir was a no-op.
        assert "DataObject" in registry.all_types()

    def test_underscore_prefixed_files_are_ignored(self, tmp_path: Path) -> None:
        """Drop-in files starting with ``_`` are skipped (private modules)."""
        scan_dir = tmp_path / "types"
        _write_module(scan_dir, "_private.py", _GOOD_MODULE)

        registry = TypeRegistry()
        registry.add_scan_dir(scan_dir)
        registry.scan_all()

        assert "CustomDropInType" not in registry.all_types()

    def test_import_error_warns_and_continues(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A broken drop-in logs a warning but does not crash scan_all.

        A second valid file in the same dir must still register.
        """
        scan_dir = tmp_path / "types"
        _write_module(scan_dir, "broken.py", _BROKEN_MODULE)
        _write_module(scan_dir, "good.py", _GOOD_MODULE)

        registry = TypeRegistry()
        registry.add_scan_dir(scan_dir)
        with caplog.at_level(logging.WARNING, logger="scistudio.core.types.registry"):
            registry.scan_all()

        assert "CustomDropInType" in registry.all_types()
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("broken.py" in (r.getMessage()) for r in warnings)

    def test_non_dataobject_classes_not_registered(self, tmp_path: Path) -> None:
        """Plain classes that are not DataObject subclasses must not register."""
        scan_dir = tmp_path / "types"
        _write_module(scan_dir, "plain.py", _NOT_A_DATAOBJECT_MODULE)

        registry = TypeRegistry()
        registry.add_scan_dir(scan_dir)
        registry.scan_all()

        assert "NotADataObject" not in registry.all_types()

    def test_drop_in_does_not_override_builtin(self, tmp_path: Path) -> None:
        """A drop-in cannot shadow built-ins — built-ins are registered first.

        We write a file that re-declares a class named ``DataObject`` (a
        DataObject subclass shadowing the builtin name). The drop-in pass
        must NOT replace the canonical builtin entry.
        """
        scan_dir = tmp_path / "types"
        _write_module(
            scan_dir,
            "shadowing.py",
            """
            from scistudio.core.types.base import DataObject as _RealDO


            class DataObject(_RealDO):  # noqa: D401 - intentional shadow
                \"\"\"Drop-in that tries to shadow the canonical DataObject.\"\"\"
            """,
        )

        registry = TypeRegistry()
        registry.add_scan_dir(scan_dir)
        registry.scan_all()

        # The built-in DataObject is the registered class, not the
        # shadow defined under ``_scistudio_type_dropin_*``.
        spec = registry.all_types()["DataObject"]
        assert spec.module_path == "scistudio.core.types.base"


# ---------------------------------------------------------------------------
# ApiRuntime wiring tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ``Path.home()`` (in the runtime module) to a per-test dir.

    The :class:`ApiRuntime` writes its registry under ``~/.scistudio``;
    this fixture isolates that side effect from the developer's real home.
    """
    fake = tmp_path / "home"
    fake.mkdir()

    from scistudio.api import runtime as runtime_module

    monkeypatch.setattr(runtime_module.Path, "home", classmethod(lambda cls: fake))
    return fake


class TestRuntimeWiring:
    """``ApiRuntime.refresh_type_registry`` wires both scan dirs."""

    def test_user_wide_types_dir_is_scanned_on_refresh(
        self,
        fake_home: Path,
    ) -> None:
        """``~/.scistudio/types`` drops in get picked up via refresh_type_registry."""
        from scistudio.api.runtime import ApiRuntime

        runtime = ApiRuntime()
        user_types_dir = fake_home / ".scistudio" / "types"
        _write_module(user_types_dir, "user_type.py", _GOOD_MODULE)

        runtime.refresh_type_registry()

        assert "CustomDropInType" in runtime.type_registry.all_types()

    def test_project_local_types_dir_is_scanned_on_open(
        self,
        fake_home: Path,
        tmp_path: Path,
    ) -> None:
        """Opening a project picks up ``<project>/types`` drop-ins.

        Issue #1332: :meth:`ApiRuntime.open_project` must call
        :meth:`refresh_type_registry` so the project's ``types/`` dir is
        scanned. Without that wiring this test would fail because the
        scan would happen at startup (when ``active_project is None``)
        and never re-run.
        """
        from scistudio.api.runtime import ApiRuntime

        parent = tmp_path / "workspace"
        parent.mkdir()
        runtime = ApiRuntime()
        project = runtime.create_project(name="Demo", description="", parent_path=str(parent))
        project_path = Path(project.path)
        _write_module(project_path / "types", "project_type.py", _GOOD_MODULE)

        # Open the project — refresh_type_registry must fire.
        runtime.open_project(str(project_path))

        assert "CustomDropInType" in runtime.type_registry.all_types()

    def test_switching_projects_does_not_leak_types(
        self,
        fake_home: Path,
        tmp_path: Path,
    ) -> None:
        """Switching from project A to project B does not retain A's types."""
        from scistudio.api.runtime import ApiRuntime

        parent = tmp_path / "workspace"
        parent.mkdir()
        runtime = ApiRuntime()
        project_a = runtime.create_project(name="Proj-A", description="", parent_path=str(parent))
        project_b = runtime.create_project(name="Proj-B", description="", parent_path=str(parent))
        a_path = Path(project_a.path)
        b_path = Path(project_b.path)

        _write_module(
            a_path / "types",
            "first.py",
            """
            from scistudio.core.types.base import DataObject


            class FirstDropInType(DataObject):
                pass
            """,
        )
        _write_module(
            b_path / "types",
            "second.py",
            """
            from scistudio.core.types.base import DataObject


            class SecondDropInType(DataObject):
                pass
            """,
        )

        runtime.open_project(str(a_path))
        assert "FirstDropInType" in runtime.type_registry.all_types()

        runtime.open_project(str(b_path))
        types = runtime.type_registry.all_types()
        assert "SecondDropInType" in types
        # A's type must not leak into B.
        assert "FirstDropInType" not in types
