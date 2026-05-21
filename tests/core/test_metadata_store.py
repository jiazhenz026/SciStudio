"""Tests for the ADR-038 deprecation-shim :class:`MetadataStore`.

Pre-ADR-038 these tests exercised a live SQLite store at
``<project>/metadata.db``. Phase D38-2.3 collapses that store into the
unified :class:`~scistudio.core.lineage.LineageStore`; the legacy
``MetadataStore`` symbol is now a thin shim whose responsibilities are:

* Preserve the public method surface (``put`` / ``put_wire`` / ``get`` /
  ``get_wire`` / ``get_by_storage_path`` / ``ancestors`` / ``descendants``
  / ``list_by_type`` / ``list_by_workflow`` / ``vacuum`` / ``delete`` /
  ``close``) so out-of-scope callers (``ai/agent/mcp/tools_*``) keep
  importing without ImportError.
* Emit a one-time :class:`DeprecationWarning` so consumers know to
  migrate.
* Make writes silent no-ops — the authoritative writer is now the
  :class:`~scistudio.core.lineage.LineageRecorder`.
* Delegate reads to the active project's :class:`LineageStore` (via the
  :class:`ApiRuntime` singleton). Without an active store, reads return
  ``None`` / ``[]``.

These tests fault-inject an in-memory :class:`LineageStore` via the
``scistudio.api.deps._runtime`` import path so the shim's read delegation
can be verified end-to-end without booting the full FastAPI app.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import pytest

import scistudio.core.metadata_store as _ms
from scistudio.core.lineage.record import DataObjectRow
from scistudio.core.lineage.store import LineageStore
from scistudio.core.metadata_store import (
    MetadataStore,
    _set_active_lineage_store,
    get_metadata_store,
    set_metadata_store,
)

# ---------------------------------------------------------------------------
# Test fixtures + helpers
# ---------------------------------------------------------------------------


def _make_wire_dict(
    *,
    object_id: str = "obj-001",
    type_chain: list[str] | None = None,
    derived_from: str | None = None,
    created_at: str = "2026-04-12T00:00:00+00:00",
    backend: str | None = "zarr",
    path: str | None = "/data/zarr/test.zarr",
) -> dict[str, Any]:
    """Build a wire-format dict matching what :func:`_serialise_one` produces."""
    if type_chain is None:
        type_chain = ["Image", "Array", "DataObject"]
    return {
        "backend": backend,
        "path": path,
        "format": None,
        "metadata": {
            "type_chain": type_chain,
            "framework": {
                "object_id": object_id,
                "derived_from": derived_from,
                "created_at": created_at,
                "source": "",
                "lineage_id": None,
            },
            "meta": None,
            "user": {},
        },
    }


@pytest.fixture
def lineage_store() -> LineageStore:
    """Provide an in-memory unified store and register it as active."""
    store = LineageStore(":memory:")
    previous = _ms._active_store
    _set_active_lineage_store(store)
    try:
        yield store
    finally:
        _set_active_lineage_store(previous)
        store.close()


@pytest.fixture
def shim() -> MetadataStore:
    """Reset the global one-time DeprecationWarning latch and yield a shim."""
    saved = _ms._WARNED
    _ms._WARNED = False
    yield MetadataStore(db_path=None)
    _ms._WARNED = saved


# ---------------------------------------------------------------------------
# Deprecation surface
# ---------------------------------------------------------------------------


class TestDeprecationWarning:
    """The shim fires a one-time DeprecationWarning per process."""

    def test_constructor_warns_first_time(self) -> None:
        saved = _ms._WARNED
        _ms._WARNED = False
        try:
            with warnings.catch_warnings(record=True) as captured:
                warnings.simplefilter("always", DeprecationWarning)
                MetadataStore(db_path=None)
            messages = [str(w.message) for w in captured if issubclass(w.category, DeprecationWarning)]
            assert any("ADR-038" in m or "deprecated" in m.lower() for m in messages)
        finally:
            _ms._WARNED = saved

    def test_warning_fires_only_once_per_process(self) -> None:
        saved = _ms._WARNED
        _ms._WARNED = False
        try:
            with warnings.catch_warnings(record=True) as captured:
                warnings.simplefilter("always", DeprecationWarning)
                MetadataStore(db_path=None)
                MetadataStore(db_path=None)
                store = MetadataStore(db_path=None)
                store.put_wire(_make_wire_dict())
            depr = [w for w in captured if issubclass(w.category, DeprecationWarning)]
            assert len(depr) == 1
        finally:
            _ms._WARNED = saved


# ---------------------------------------------------------------------------
# Writes are no-ops
# ---------------------------------------------------------------------------


class TestWritesAreNoops:
    """The shim never modifies the unified store on write calls."""

    def test_put_wire_does_not_touch_lineage_store(
        self,
        shim: MetadataStore,
        lineage_store: LineageStore,
    ) -> None:
        shim.put_wire(_make_wire_dict(object_id="should-not-land"))
        assert lineage_store.count("data_objects") == 0

    def test_put_wire_if_missing_is_a_noop(
        self,
        shim: MetadataStore,
        lineage_store: LineageStore,
    ) -> None:
        shim.put_wire_if_missing(_make_wire_dict(object_id="x"))
        assert lineage_store.count("data_objects") == 0

    def test_delete_is_a_noop(self, shim: MetadataStore) -> None:
        # Should never raise even when no store is configured.
        shim.delete("missing")

    def test_vacuum_returns_zero(self, shim: MetadataStore) -> None:
        assert shim.vacuum(existing_paths=set()) == 0

    def test_close_is_a_noop(self, shim: MetadataStore) -> None:
        shim.close()  # idempotent / no exception


# ---------------------------------------------------------------------------
# Reads delegate to LineageStore.data_objects
# ---------------------------------------------------------------------------


class TestReadDelegation:
    """Reads delegate to the active unified store's ``data_objects`` table."""

    def _insert(self, store: LineageStore, **overrides: Any) -> dict[str, Any]:
        wire = _make_wire_dict(**overrides)
        framework = wire["metadata"]["framework"]
        type_chain = wire["metadata"]["type_chain"]
        store.upsert_data_object(
            DataObjectRow(
                object_id=framework["object_id"],
                type_name=type_chain[0],
                wire_payload=wire,
                created_at=framework["created_at"],
                backend=wire["backend"],
                storage_path=wire["path"],
                derived_from=framework["derived_from"],
            )
        )
        return wire

    def test_get_wire_returns_wire_dict(
        self,
        shim: MetadataStore,
        lineage_store: LineageStore,
    ) -> None:
        wire = self._insert(lineage_store, object_id="abc")
        assert shim.get_wire("abc") == wire

    def test_get_wire_returns_none_when_missing(
        self,
        shim: MetadataStore,
        lineage_store: LineageStore,
    ) -> None:
        assert shim.get_wire("nope") is None

    def test_get_wire_without_active_store_returns_none(self) -> None:
        saved = _ms._WARNED
        _ms._WARNED = False
        previous = _ms._active_store
        _set_active_lineage_store(None)
        try:
            shim = MetadataStore(db_path=None)
            assert shim.get_wire("anything") is None
        finally:
            _set_active_lineage_store(previous)
            _ms._WARNED = saved

    def test_get_reconstructs_dataobject(
        self,
        shim: MetadataStore,
        lineage_store: LineageStore,
    ) -> None:
        self._insert(
            lineage_store,
            object_id="reconstruct-me",
            type_chain=["DataObject"],
        )
        obj = shim.get("reconstruct-me")
        assert obj is not None
        assert obj.framework.object_id == "reconstruct-me"

    def test_get_by_storage_path_returns_dataobject(
        self,
        shim: MetadataStore,
        lineage_store: LineageStore,
    ) -> None:
        self._insert(
            lineage_store,
            object_id="by-path",
            path="/data/zarr/lookup.zarr",
            type_chain=["DataObject"],
        )
        obj = shim.get_by_storage_path("/data/zarr/lookup.zarr")
        assert obj is not None
        assert obj.framework.object_id == "by-path"

    def test_get_wire_by_storage_path(
        self,
        shim: MetadataStore,
        lineage_store: LineageStore,
    ) -> None:
        wire = self._insert(
            lineage_store,
            object_id="by-path-wire",
            path="/data/zarr/wire_path.zarr",
        )
        assert shim.get_wire_by_storage_path("/data/zarr/wire_path.zarr") == wire

    def test_ancestors_walks_derived_from(
        self,
        shim: MetadataStore,
        lineage_store: LineageStore,
    ) -> None:
        self._insert(lineage_store, object_id="gp", derived_from=None)
        self._insert(lineage_store, object_id="parent", derived_from="gp")
        self._insert(lineage_store, object_id="child", derived_from="parent")

        chain = shim.ancestors("child")
        assert [c["object_id"] for c in chain] == ["child", "parent", "gp"]
        # Backwards-compat: shim emits ``block_id=None``.
        assert all(c["block_id"] is None for c in chain)

    def test_descendants_walks_forward(
        self,
        shim: MetadataStore,
        lineage_store: LineageStore,
    ) -> None:
        self._insert(lineage_store, object_id="root", derived_from=None)
        self._insert(lineage_store, object_id="c1", derived_from="root")
        self._insert(lineage_store, object_id="c2", derived_from="root")

        rows = shim.descendants("root")
        assert {r["object_id"] for r in rows} == {"root", "c1", "c2"}

    def test_list_by_type(
        self,
        shim: MetadataStore,
        lineage_store: LineageStore,
    ) -> None:
        self._insert(lineage_store, object_id="img-1", type_chain=["Image", "Array"])
        self._insert(lineage_store, object_id="img-2", type_chain=["Image", "Array"])
        self._insert(lineage_store, object_id="df-1", type_chain=["DataFrame"])

        rows = shim.list_by_type("Image")
        assert {r["object_id"] for r in rows} == {"img-1", "img-2"}

    def test_empty_database_reads_return_empty(
        self,
        shim: MetadataStore,
        lineage_store: LineageStore,
    ) -> None:
        assert shim.get_wire("x") is None
        assert shim.get("x") is None
        assert shim.ancestors("x") == []
        assert shim.descendants("x") == []
        assert shim.list_by_type("Image") == []
        assert shim.list_by_workflow("wf") == []


# ---------------------------------------------------------------------------
# Singleton accessors
# ---------------------------------------------------------------------------


class TestSingletonAccessors:
    def test_default_is_none(self) -> None:
        original = get_metadata_store()
        try:
            set_metadata_store(None)
            assert get_metadata_store() is None
        finally:
            set_metadata_store(original)

    def test_set_and_get(self, shim: MetadataStore) -> None:
        original = get_metadata_store()
        try:
            set_metadata_store(shim)
            assert get_metadata_store() is shim
        finally:
            set_metadata_store(original)


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------


class TestRepr:
    def test_repr_mentions_deprecation(self, shim: MetadataStore) -> None:
        assert "deprecated_shim" in repr(shim)

    def test_repr_with_path(self, tmp_path: Path) -> None:
        saved = _ms._WARNED
        _ms._WARNED = False
        try:
            shim = MetadataStore(db_path=tmp_path / "metadata.db")
            text = repr(shim)
            assert "deprecated_shim" in text
            assert "metadata.db" in text
        finally:
            _ms._WARNED = saved
