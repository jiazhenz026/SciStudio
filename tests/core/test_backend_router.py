"""Tests for BackendRouter — type-to-backend MRO resolution."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import ClassVar

import pytest

from scistudio.core.storage.arrow_backend import ArrowBackend
from scistudio.core.storage.backend_router import BackendRouter, get_router
from scistudio.core.storage.zarr_backend import ZarrBackend
from scistudio.core.types.array import Array


class Image(Array):
    """T-006 shim for the removed core ``Image`` class (T-008 migration)."""

    required_axes: ClassVar[frozenset[str]] = frozenset({"y", "x"})


class TestResolveDirectType:
    """BackendRouter.resolve — direct type lookup."""

    def test_resolve_direct_type(self) -> None:
        router = get_router()
        name, backend = router.resolve(Array)
        assert name == "zarr"
        assert isinstance(backend, ZarrBackend)

    def test_resolve_series_type_to_arrow(self) -> None:
        from scistudio.core.types.series import Series

        router = get_router()
        name, backend = router.resolve(Series)
        assert name == "arrow"
        assert isinstance(backend, ArrowBackend)


class TestResolveSubclassViaMRO:
    """BackendRouter.resolve — subclass falls back to ancestor via MRO."""

    def test_resolve_subclass_via_mro(self) -> None:
        router = get_router()
        name, backend = router.resolve(Image)
        assert name == "zarr"
        assert isinstance(backend, ZarrBackend)


class TestResolveUnregisteredRaises:
    """BackendRouter.resolve — unregistered type raises KeyError."""

    def test_resolve_unregistered_raises(self) -> None:
        router = BackendRouter()
        with pytest.raises(KeyError, match="No storage backend registered"):
            router.resolve(int)


class TestDefaultRouterCoverage:
    """get_router() has all 6 core types registered."""

    def test_default_router_coverage(self) -> None:
        from scistudio.core.types.artifact import Artifact
        from scistudio.core.types.composite import CompositeData
        from scistudio.core.types.dataframe import DataFrame
        from scistudio.core.types.series import Series
        from scistudio.core.types.text import Text

        router = get_router()
        for data_type in [Array, Series, DataFrame, Text, Artifact, CompositeData]:
            name, backend = router.resolve(data_type)
            assert isinstance(name, str)
            assert backend is not None


class TestExtensionFor:
    """BackendRouter.extension_for — correct file extensions."""

    def test_extension_for_array(self) -> None:
        router = get_router()
        assert router.extension_for(Array) == ".zarr"

    def test_extension_for_dataframe(self) -> None:
        from scistudio.core.types.dataframe import DataFrame

        router = get_router()
        assert router.extension_for(DataFrame) == ".parquet"

    def test_extension_for_series(self) -> None:
        from scistudio.core.types.series import Series

        router = get_router()
        assert router.extension_for(Series) == ".parquet"

    def test_extension_for_text(self) -> None:
        from scistudio.core.types.text import Text

        router = get_router()
        assert router.extension_for(Text) == ".txt"

    def test_extension_for_composite(self) -> None:
        from scistudio.core.types.composite import CompositeData

        router = get_router()
        assert router.extension_for(CompositeData) == ""


class TestBackendNameFor:
    """BackendRouter.backend_name_for — correct backend name strings."""

    def test_backend_name_for_array(self) -> None:
        router = get_router()
        assert router.backend_name_for(Array) == "zarr"

    def test_backend_name_for_dataframe(self) -> None:
        from scistudio.core.types.dataframe import DataFrame

        router = get_router()
        assert router.backend_name_for(DataFrame) == "arrow"

    def test_backend_name_for_series(self) -> None:
        from scistudio.core.types.series import Series

        router = get_router()
        assert router.backend_name_for(Series) == "arrow"

    def test_backend_name_for_text(self) -> None:
        from scistudio.core.types.text import Text

        router = get_router()
        assert router.backend_name_for(Text) == "filesystem"


class TestSingletonIdentity:
    """get_router() returns the same instance on repeated calls."""

    def test_singleton_identity(self) -> None:
        r1 = get_router()
        r2 = get_router()
        assert r1 is r2


class TestNoCircularImport:
    """Regression for #1335 — backend_router and core.types.base import in any order.

    The pre-#1335 graph had ``core.types <-> core.storage.backend_router`` as a
    10-module strongly connected component because ``backend_router`` imported
    six concrete ``core.types`` classes inside ``_build_default_router``. #1335
    moved those imports to ``scistudio.core.storage._defaults``; #1342 (round-4
    no-cycles) then fully inverted the edge — the default wiring now lives in
    ``core.types._backend_defaults`` and ``backend_router`` holds only a builder
    callback — so ``backend_router`` has *no* AST edge into ``core.types.*``.

    This test spawns a fresh Python subprocess for each import order so the
    module cache is clean, and asserts the import succeeds either way.
    """

    @pytest.mark.parametrize(
        "order",
        [
            (
                "scistudio.core.storage.backend_router",
                "scistudio.core.types.base",
            ),
            (
                "scistudio.core.types.base",
                "scistudio.core.storage.backend_router",
            ),
        ],
        ids=["router-first", "types-first"],
    )
    def test_no_circular_import(self, order: tuple[str, str]) -> None:
        code = f"import {order[0]}; import {order[1]}; print('ok')"
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"Import order {order!r} raised:\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )
        assert result.stdout.strip() == "ok"


class TestBackendRouterHasNoTypesImport:
    """Lock in the cycle-free state of ``backend_router.py``.

    Regression for #1335 and #1342 — ``backend_router.py`` must not import
    ``scistudio.core.types.*`` *anywhere* (module-top OR a lazy function body).
    #1342 (round-4 no-cycles) removed the residual ``backend_router ->
    _defaults -> core.types`` edge by inverting it: the default
    ``type -> backend`` wiring now lives in ``core.types._backend_defaults``,
    which hands ``get_router`` a builder *callback* via
    :func:`set_default_builder`. ``_defaults`` no longer exists. This guard
    prevents a future refactor from silently re-introducing the cycle.
    """

    def test_backend_router_has_no_types_import_anywhere(self) -> None:
        import ast

        from scistudio.core.storage import backend_router

        source = Path(backend_router.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)

        # AST-based so the module's own docstrings/comments (which mention
        # ``core.types._backend_defaults`` for explanation) do not trip the
        # guard — only real import statements count.
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
            elif isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)

        forbidden = [
            mod
            for mod in imported
            if mod.startswith("scistudio.core.types") or mod.startswith("scistudio.core.storage._defaults")
        ]
        assert not forbidden, (
            f"backend_router.py imports {forbidden!r} (module-top or lazy). This "
            f"re-introduces the core.types <-> backend_router cycle (#1335 / #1342)."
        )

    def test_default_builder_callback_is_registered_by_types_side(self) -> None:
        # Importing core.types runs its __init__, which imports
        # _backend_defaults, which calls set_default_builder. After that the
        # default router resolves the six core types — without backend_router
        # ever importing a concrete type.
        import scistudio.core.types  # noqa: F401
        from scistudio.core.storage import backend_router
        from scistudio.core.types.array import Array

        assert backend_router._default_builder is not None
        assert backend_router.get_router().resolve(Array)[0] == "zarr"
