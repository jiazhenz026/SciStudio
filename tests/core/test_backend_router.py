"""Tests for BackendRouter — type-to-backend MRO resolution."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import ClassVar

import pytest

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
    six concrete ``core.types`` classes inside ``_build_default_router``. The
    surgical fix in #1335 moves those imports to
    ``scistudio.core.storage._defaults`` so ``backend_router`` no longer has
    *any* AST edge into ``core.types.*``.

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


class TestBackendRouterHasNoTypesTopLevelImport:
    """Lock in the cycle-free state of ``backend_router.py``.

    Regression for #1335 — ``backend_router.py`` must have ZERO module-top
    imports of ``scistudio.core.types.*`` or ``scistudio.core.storage._defaults``.
    The only ``_defaults`` import is the lazy one inside ``get_router()``'s
    function body. This guard prevents a future refactor from silently
    re-introducing the cycle by pulling a type or ``_defaults`` import back to
    module top level.
    """

    def test_backend_router_has_no_types_top_level_import(self) -> None:
        from scistudio.core.storage import backend_router

        source = Path(backend_router.__file__).read_text(encoding="utf-8")

        # Strip the get_router function body so the lazy import inside it
        # doesn't count as a "top-level" import.
        body_match = re.search(
            r"^def get_router\(.*?\n((?: {4}.*?\n|\n)+)",
            source,
            re.MULTILINE,
        )
        assert body_match is not None, "Could not locate get_router() body in source"
        source_without_get_router_body = source.replace(body_match.group(1), "")

        forbidden_patterns = [
            r"^from\s+scistudio\.core\.types",
            r"^import\s+scistudio\.core\.types",
            r"^from\s+scistudio\.core\.storage\._defaults",
            r"^import\s+scistudio\.core\.storage\._defaults",
        ]
        for pattern in forbidden_patterns:
            matches = re.findall(pattern, source_without_get_router_body, re.MULTILINE)
            assert not matches, (
                f"backend_router.py has forbidden module-top import matching "
                f"{pattern!r}: {matches!r}. This re-introduces the #1335 "
                f"core.types <-> backend_router cycle."
            )
