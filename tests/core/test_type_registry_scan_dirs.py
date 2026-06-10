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

    def test_drop_in_load_class_round_trip(self, tmp_path: Path) -> None:
        """Regression: #1343 — drop-in module must be importable via load_class.

        Before #1343 was fixed, the drop-in scanner created a synthetic
        ``_scistudio_type_dropin_<stem>_<mtime>`` module via
        :func:`importlib.util.spec_from_file_location` but never inserted
        it into :data:`sys.modules`. :meth:`TypeRegistry.register_class`
        then stored ``cls.__module__`` (the synthetic name) in
        :attr:`TypeSpec.module_path`. Any subsequent call to
        :meth:`TypeRegistry.load_class` — which does
        ``importlib.import_module(spec.module_path)`` — raised
        :class:`ModuleNotFoundError`, leaving every scanned drop-in type
        registerable but unloadable. This test exercises the full
        round-trip (scan → register → load_class) for both the legacy
        ``str``-resolve path and the ADR-027 D11 ``type_chain``-resolve
        path that worker reconstruction uses.
        """
        import sys

        scan_dir = tmp_path / "types"
        _write_module(scan_dir, "round_trip_type.py", _GOOD_MODULE)

        registry = TypeRegistry()
        registry.add_scan_dir(scan_dir)
        registry.scan_all()

        # The spec is stored under the synthetic module name; that name
        # MUST be present in sys.modules so importlib can find it.
        spec = registry.all_types()["CustomDropInType"]
        assert spec.module_path.startswith("_scistudio_type_dropin_round_trip_type_")
        assert spec.module_path in sys.modules

        # Legacy str path: load_class must return the concrete class, not
        # raise ModuleNotFoundError (#1343 P1 regression).
        loaded = registry.load_class("CustomDropInType")
        assert loaded.__name__ == "CustomDropInType"
        assert isinstance(loaded, type)

        # ADR-027 D11 type_chain path used by worker reconstruction:
        # ``resolve(["DataObject", "CustomDropInType"])`` walks from
        # rightmost to leftmost and must return the drop-in class.
        from scistudio.core.types.base import DataObject

        resolved = registry.resolve(["DataObject", "CustomDropInType"])
        assert resolved is loaded
        assert issubclass(resolved, DataObject) and resolved is not DataObject

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

    def test_module_name_unique_across_scan_dirs_same_stem_and_mtime(
        self, tmp_path: Path
    ) -> None:
        """Regression for #1374: same-stem files in two scan dirs must not collide.

        Before #1374, the synthetic module name was built from
        ``stem + int(mtime)`` only. Two files with the same stem from
        different scan dirs would get the same synthetic name, so the second
        file's module would silently overwrite the first in sys.modules and
        its classes would be registered under the wrong TypeSpec.

        The fix adds a per-path hash component so the names are always unique
        regardless of stem and mtime.
        """
        import sys

        # Create two scan dirs each containing a file named "custom_type.py"
        # that defines a *differently-named* class. Use identical mtimes to
        # maximise the chance of a collision under the old scheme.
        dir_a = tmp_path / "dir_a"
        dir_b = tmp_path / "dir_b"

        _write_module(
            dir_a,
            "custom_type.py",
            """
from scistudio.core.types.base import DataObject


class TypeFromDirA(DataObject):
    \"\"\"Drop-in from dir_a.\"\"\"
""",
        )
        _write_module(
            dir_b,
            "custom_type.py",
            """
from scistudio.core.types.base import DataObject


class TypeFromDirB(DataObject):
    \"\"\"Drop-in from dir_b.\"\"\"
""",
        )

        # Force both files to the same mtime to reproduce the #1374 collision.
        import os

        fixed_mtime = 1_700_000_000.0
        for d in (dir_a, dir_b):
            p = d / "custom_type.py"
            os.utime(p, (fixed_mtime, fixed_mtime))

        registry = TypeRegistry()
        registry.add_scan_dir(dir_a)
        registry.add_scan_dir(dir_b)
        registry.scan_all()

        all_types = registry.all_types()
        # Both classes must be registered.
        assert "TypeFromDirA" in all_types, "TypeFromDirA should be registered"
        assert "TypeFromDirB" in all_types, "TypeFromDirB should be registered"

        # Their module paths must differ (path-hash disambiguates them).
        spec_a = all_types["TypeFromDirA"]
        spec_b = all_types["TypeFromDirB"]
        assert spec_a.module_path != spec_b.module_path, (
            f"Module paths collided: {spec_a.module_path!r} == {spec_b.module_path!r}"
        )

        # Both must be loadable (present in sys.modules).
        assert spec_a.module_path in sys.modules, f"{spec_a.module_path!r} missing from sys.modules"
        assert spec_b.module_path in sys.modules, f"{spec_b.module_path!r} missing from sys.modules"

        # load_class must return the correct class from each module.
        cls_a = registry.load_class("TypeFromDirA")
        cls_b = registry.load_class("TypeFromDirB")
        assert cls_a.__name__ == "TypeFromDirA"
        assert cls_b.__name__ == "TypeFromDirB"
        assert cls_a is not cls_b


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
