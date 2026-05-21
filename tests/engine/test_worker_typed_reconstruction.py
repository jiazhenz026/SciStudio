"""Tests for the T-014 worker subprocess typed reconstruction path.

Exercises :func:`scistudio.core.types.serialization._reconstruct_one` and
:func:`~scistudio.core.types.serialization._serialise_one` (the core
round-trip helpers), plus :func:`scistudio.engine.runners.worker.reconstruct_inputs`
and :func:`~scistudio.engine.runners.worker.serialise_outputs` (the worker
wrappers that dispatch per-item).

Per ADR-027 D11 + Addendum 1 §1, the worker subprocess must return
typed :class:`~scistudio.core.types.base.DataObject` instances (e.g. an
:class:`~scistudio.core.types.array.Array`). Lazy loading is preserved at
the method level: reconstructed instances have ``storage_ref`` set
but do not read payload data until ``to_memory()`` / ``sel()`` /
``iter_over()`` is called (ADR-031 D2: ViewProxy eliminated).

T-014 is the *capstone* of Phase 10 — these tests exercise the final
layer that stitches together every previous ticket (T-005 three
slots, T-006 Array axes, T-007 base-class audit, T-012 TypeRegistry
resolve, T-013 hook pairs).

Plugin reconstruction is not exercised end-to-end because no plugin
packages exist in this repo. Tests use the six core base classes
(``Array``, ``Series``, ``DataFrame``, ``Text``, ``Artifact``,
``CompositeData``) plus local fixture subclasses with their own
Pydantic ``Meta`` model to exercise the ``cls.Meta.model_validate``
path of :func:`_reconstruct_one`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pytest
from pydantic import BaseModel, ConfigDict

from scistudio.core.meta import FrameworkMeta
from scistudio.core.storage.ref import StorageReference
from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.serialization import (
    _get_type_registry,
    _reconstruct_one,
    _serialise_one,
)
from scistudio.core.types.series import Series
from scistudio.core.types.text import Text
from scistudio.engine.runners.worker import reconstruct_inputs, serialise_outputs


def _ref(path: str = "/tmp/test.zarr", backend: str = "zarr") -> StorageReference:
    """Create a minimal StorageReference for test objects."""
    return StorageReference(backend=backend, path=path)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _FixtureMeta(BaseModel):
    """Small frozen Pydantic Meta model for fixture subclasses.

    Exercises the :func:`_reconstruct_one` ``cls.Meta.model_validate``
    path without pulling in any plugin package.
    """

    model_config = ConfigDict(frozen=True)

    label: str = ""
    count: int = 0


class _ArrayWithMeta(Array):
    """Array fixture subclass with a typed Meta for reconstruction tests."""

    Meta: ClassVar[type[BaseModel] | None] = _FixtureMeta


class _RestrictedArray(Array):
    """Array fixture subclass with tight ``allowed_axes`` for error-path tests.

    Must live at module scope so :meth:`TypeRegistry.load_class` can
    reimport it by module path during :func:`_reconstruct_one`.
    """

    allowed_axes: ClassVar[frozenset[str] | None] = frozenset({"y", "x"})


def _reset_registry_singleton() -> None:
    """Clear the serialization module's TypeRegistry singleton.

    Called between tests that register fixture subclasses so the next
    ``_get_type_registry`` call picks up a fresh scan. Core built-ins
    are re-registered by ``scan_builtins``, and fixture classes are
    re-registered explicitly via ``register_class``.
    """
    from scistudio.core.types import serialization

    serialization._registry_instance = None


def _register_fixture(cls: type) -> None:
    """Force-register a fixture subclass in the serialization singleton."""
    _reset_registry_singleton()
    registry = _get_type_registry()
    registry.register_class(cls)


# ---------------------------------------------------------------------------
# _reconstruct_one — class resolution and slot population
# ---------------------------------------------------------------------------


class TestReconstructOne:
    def test_returns_typed_instance_for_array_chain(self) -> None:
        """type_chain=['DataObject','Array'] resolves to Array."""
        payload = {
            "backend": "zarr",
            "path": "/data/x.zarr",
            "format": "zarr",
            "metadata": {
                "type_chain": ["DataObject", "Array"],
                "framework": {},
                "meta": None,
                "user": {},
                "axes": ["y", "x"],
                "shape": [16, 16],
                "dtype": "uint8",
                "chunk_shape": None,
            },
        }
        obj = _reconstruct_one(payload)

        assert isinstance(obj, Array)
        # ADR-031 D2: ViewProxy eliminated. Typed DataObject is the only path.
        assert obj.axes == ["y", "x"]
        assert obj.shape == (16, 16)

    def test_with_storage_ref(self) -> None:
        """backend+path populate StorageReference on the returned instance."""
        payload = {
            "backend": "zarr",
            "path": "/data/img.zarr",
            "format": "zarr",
            "metadata": {
                "type_chain": ["DataObject", "Array"],
                "axes": ["y", "x"],
            },
        }
        obj = _reconstruct_one(payload)

        assert obj.storage_ref is not None
        assert obj.storage_ref.backend == "zarr"
        # StorageReference normalises the path to POSIX forward slashes.
        assert obj.storage_ref.path == "/data/img.zarr"
        assert obj.storage_ref.format == "zarr"

    def test_no_storage_ref_when_backend_or_path_missing(self) -> None:
        """Payload with ``backend=None`` produces ``storage_ref=None``."""
        payload = {
            "backend": None,
            "path": None,
            "format": None,
            "metadata": {
                "type_chain": ["DataObject", "Array"],
                "axes": ["y", "x"],
            },
        }
        obj = _reconstruct_one(payload)

        assert obj.storage_ref is None
        assert isinstance(obj, Array)
        assert obj.axes == ["y", "x"]

    def test_falls_back_to_dataobject_for_unknown_type_chain(self) -> None:
        """Unknown chain → bare :class:`DataObject` rather than crashing."""
        payload = {
            "backend": None,
            "path": None,
            "format": None,
            "metadata": {
                "type_chain": ["NoSuchTypeEver", "AlsoNotRegistered"],
                "framework": {},
                "meta": None,
                "user": {},
            },
        }
        obj = _reconstruct_one(payload)

        # Falls all the way back to plain DataObject when the chain is
        # completely unrecognised. Array would also be acceptable if the
        # registry happened to contain DataObject, but we want to exercise
        # the "nothing matches" path explicitly.
        assert type(obj) is DataObject

    def test_framework_meta_validated(self) -> None:
        """framework field round-trips as a FrameworkMeta with the original object_id."""
        original_id = "abc123def456"
        payload = {
            "backend": None,
            "path": None,
            "format": None,
            "metadata": {
                "type_chain": ["DataObject"],
                "framework": {
                    "object_id": original_id,
                    "source": "unit-test",
                    "lineage_id": "run-1",
                },
                "meta": None,
                "user": {},
            },
        }
        obj = _reconstruct_one(payload)

        assert isinstance(obj.framework, FrameworkMeta)
        assert obj.framework.object_id == original_id
        assert obj.framework.source == "unit-test"
        assert obj.framework.lineage_id == "run-1"

    def test_meta_none_when_no_meta_class(self) -> None:
        """Classes with ``Meta=None`` (all six core bases) produce ``meta=None``."""
        payload = {
            "backend": None,
            "path": None,
            "format": None,
            "metadata": {
                "type_chain": ["DataObject", "Array"],
                "meta": {"ignored": "value"},
                "axes": ["y", "x"],
            },
        }
        obj = _reconstruct_one(payload)

        # Array.Meta is None — the meta sidecar is ignored.
        assert obj.meta is None

    def test_meta_populated_when_meta_class_declared(self) -> None:
        """Fixture subclass with a Meta ClassVar gets a validated Meta instance."""
        _register_fixture(_ArrayWithMeta)
        try:
            payload = {
                "backend": None,
                "path": None,
                "format": None,
                "metadata": {
                    "type_chain": ["DataObject", "Array", "_ArrayWithMeta"],
                    "framework": {},
                    "meta": {"label": "sample-A", "count": 7},
                    "user": {},
                    "axes": ["y", "x"],
                    "shape": [32, 32],
                    "dtype": "float32",
                    "chunk_shape": None,
                },
            }
            obj = _reconstruct_one(payload)

            assert isinstance(obj, _ArrayWithMeta)
            assert isinstance(obj.meta, _FixtureMeta)
            assert obj.meta.label == "sample-A"
            assert obj.meta.count == 7
        finally:
            _reset_registry_singleton()

    def test_user_dict_preserved_and_copied(self) -> None:
        """user slot round-trips and is an independent copy."""
        user_payload = {"experiment": "E1", "tags": ["a", "b"]}
        payload = {
            "backend": None,
            "path": None,
            "format": None,
            "metadata": {
                "type_chain": ["DataObject", "Array"],
                "user": user_payload,
                "axes": ["y", "x"],
            },
        }
        obj = _reconstruct_one(payload)

        assert obj.user == {"experiment": "E1", "tags": ["a", "b"]}
        # Mutating the returned dict must not affect the original payload.
        obj.user["experiment"] = "mutated"
        assert user_payload["experiment"] == "E1"

    def test_rejects_non_dict_payload(self) -> None:
        """Calling the helper with a non-dict raises ValueError."""
        with pytest.raises(ValueError, match="dict payload_item"):
            _reconstruct_one("not a dict")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _serialise_one — shape of the emitted metadata sidecar
# ---------------------------------------------------------------------------


class TestSerialiseOne:
    def test_rejects_non_dataobject(self) -> None:
        """Calling the helper with a non-DataObject raises ValueError."""
        with pytest.raises(ValueError, match="DataObject"):
            _serialise_one("not a DataObject")  # type: ignore[arg-type]

    def test_writes_full_metadata_sidecar(self) -> None:
        """_serialise_one emits type_chain + framework + meta + user + extras."""
        arr = Array(axes=["y", "x"], shape=(8, 8), dtype="uint8")
        arr._storage_ref = StorageReference(backend="zarr", path="/tmp/x.zarr", format="zarr")

        payload = _serialise_one(arr)
        md = payload["metadata"]

        assert payload["backend"] == "zarr"
        assert payload["path"] == "/tmp/x.zarr"
        assert payload["format"] == "zarr"
        assert md["type_chain"] == ["DataObject", "Array"]
        assert isinstance(md["framework"], dict)
        assert "object_id" in md["framework"]
        assert md["meta"] is None
        assert md["user"] == {}
        assert md["axes"] == ["y", "x"]
        assert md["shape"] == [8, 8]
        assert md["dtype"] == "uint8"

    def test_storage_ref_none_raises_valueerror(self) -> None:
        """ADR-031 Addendum 1: _serialise_one rejects objects without storage_ref."""
        arr = Array(axes=["y", "x"])
        with pytest.raises(ValueError, match="storage_ref is None"):
            _serialise_one(arr)


# ---------------------------------------------------------------------------
# Round-trip: _serialise_one → _reconstruct_one → equality
# ---------------------------------------------------------------------------


class TestSerialiseReconstructRoundTrip:
    def test_array_round_trip(self) -> None:
        original = Array(
            axes=["t", "z", "c", "y", "x"],
            shape=(5, 10, 3, 256, 256),
            dtype="uint16",
            chunk_shape=(1, 1, 1, 256, 256),
            user={"source": "microscope"},
            storage_ref=_ref("/tmp/arr.zarr"),
        )
        payload = _serialise_one(original)
        rebuilt = _reconstruct_one(payload)

        assert isinstance(rebuilt, Array)
        assert rebuilt.axes == original.axes
        assert rebuilt.shape == original.shape
        assert rebuilt.dtype == original.dtype
        assert rebuilt.chunk_shape == original.chunk_shape
        assert rebuilt.framework.object_id == original.framework.object_id
        assert rebuilt.user == original.user

    def test_series_round_trip(self) -> None:
        original = Series(
            index_name="wavenumber",
            value_name="intensity",
            length=4096,
            storage_ref=_ref("/tmp/ser.arrow", "arrow"),
        )
        payload = _serialise_one(original)
        rebuilt = _reconstruct_one(payload)

        assert isinstance(rebuilt, Series)
        assert rebuilt.index_name == "wavenumber"
        assert rebuilt.value_name == "intensity"
        assert rebuilt.length == 4096
        assert rebuilt.framework.object_id == original.framework.object_id

    def test_dataframe_round_trip(self) -> None:
        original = DataFrame(
            columns=["peak_mz", "intensity", "rt"],
            row_count=500,
            schema={"peak_mz": "float64", "intensity": "float64", "rt": "float64"},
            storage_ref=_ref("/tmp/df.arrow", "arrow"),
        )
        payload = _serialise_one(original)
        rebuilt = _reconstruct_one(payload)

        assert isinstance(rebuilt, DataFrame)
        assert rebuilt.columns == original.columns
        assert rebuilt.row_count == original.row_count
        assert rebuilt.schema == original.schema

    def test_text_round_trip(self) -> None:
        original = Text(
            content="# Report\n\nbody",
            format="markdown",
            encoding="utf-8",
            storage_ref=_ref("/tmp/text.txt", "filesystem"),
        )
        payload = _serialise_one(original)
        rebuilt = _reconstruct_one(payload)

        assert isinstance(rebuilt, Text)
        assert rebuilt.content == original.content
        assert rebuilt.format == original.format
        assert rebuilt.encoding == original.encoding

    def test_artifact_round_trip(self) -> None:
        original = Artifact(
            file_path=Path("/data/report.pdf"),
            mime_type="application/pdf",
            description="quarterly report",
        )
        payload = _serialise_one(original)
        # JSON-clean wire format (must not raise).
        import json

        json.dumps(payload)

        rebuilt = _reconstruct_one(payload)
        assert isinstance(rebuilt, Artifact)
        assert rebuilt.file_path == original.file_path
        assert rebuilt.mime_type == original.mime_type
        assert rebuilt.description == original.description

    def test_composite_round_trip_with_slots(self) -> None:
        """Composite with multiple slots round-trips including nested reconstruction."""
        arr = Array(
            axes=["y", "x"],
            shape=(4, 4),
            dtype="uint8",
            storage_ref=_ref("/tmp/c_arr.zarr"),
        )
        ser = Series(
            index_name="time",
            value_name="voltage",
            length=100,
            storage_ref=_ref("/tmp/c_ser.arrow", "arrow"),
        )
        df = DataFrame(
            columns=["a", "b"],
            row_count=10,
            schema={"a": "int", "b": "float"},
            storage_ref=_ref("/tmp/c_df.arrow", "arrow"),
        )
        composite = CompositeData(
            slots={"image": arr, "trace": ser, "peaks": df},
            storage_ref=_ref("/tmp/composite.dat"),
        )

        payload = _serialise_one(composite)
        rebuilt = _reconstruct_one(payload)

        assert isinstance(rebuilt, CompositeData)
        assert set(rebuilt.slot_names) == {"image", "trace", "peaks"}
        assert isinstance(rebuilt.get("image"), Array)
        assert rebuilt.get("image").axes == ["y", "x"]
        assert rebuilt.get("image").shape == (4, 4)
        assert isinstance(rebuilt.get("trace"), Series)
        assert rebuilt.get("trace").length == 100
        assert isinstance(rebuilt.get("peaks"), DataFrame)
        assert rebuilt.get("peaks").row_count == 10

    def test_composite_round_trip_empty_slots(self) -> None:
        """Empty composite round-trips without hitting the nested path."""
        composite = CompositeData(storage_ref=_ref("/tmp/empty_composite.dat"))
        payload = _serialise_one(composite)
        rebuilt = _reconstruct_one(payload)

        assert isinstance(rebuilt, CompositeData)
        assert rebuilt.slot_names == []

    def test_round_trip_preserves_deep_user_metadata(self) -> None:
        """User dict with nested lists and primitives survives round-trip."""
        original = Array(
            axes=["y", "x"],
            shape=(2, 2),
            dtype="uint8",
            user={
                "experiment_id": "E-42",
                "tags": ["alpha", "beta"],
                "params": {"threshold": 0.5, "iterations": 10},
            },
            storage_ref=_ref("/tmp/user_meta.zarr"),
        )
        payload = _serialise_one(original)
        rebuilt = _reconstruct_one(payload)

        assert rebuilt.user == original.user


# ---------------------------------------------------------------------------
# worker.reconstruct_inputs — dispatcher cases
# ---------------------------------------------------------------------------


class TestReconstructInputs:
    def test_dict_of_typed_items(self) -> None:
        """Full payload dict with multiple typed inputs."""
        payload = {
            "inputs": {
                "image": {
                    "backend": "zarr",
                    "path": "/data/img.zarr",
                    "metadata": {
                        "type_chain": ["DataObject", "Array"],
                        "axes": ["y", "x"],
                        "shape": [16, 16],
                        "dtype": "uint8",
                    },
                },
                "signal": {
                    "backend": "arrow",
                    "path": "/data/sig.arrow",
                    "metadata": {
                        "type_chain": ["DataObject", "Series"],
                        "index_name": "time",
                        "value_name": "voltage",
                        "length": 1024,
                    },
                },
            }
        }
        result = reconstruct_inputs(payload)

        assert isinstance(result["image"], Array)
        assert result["image"].axes == ["y", "x"]
        assert isinstance(result["signal"], Series)
        assert result["signal"].length == 1024

    def test_returns_typed_dataobject(self) -> None:
        """Regression guard: the return type is the typed class (ADR-031 D2)."""
        payload = {
            "inputs": {
                "image": {
                    "backend": "zarr",
                    "path": "/data/img.zarr",
                    "metadata": {
                        "type_chain": ["DataObject", "Array"],
                        "axes": ["y", "x"],
                    },
                }
            }
        }
        result = reconstruct_inputs(payload)
        assert isinstance(result["image"], Array)

    def test_collection_dispatch(self) -> None:
        """Collection payload is reconstructed into a Collection of typed items."""
        payload = {
            "inputs": {
                "stack": {
                    "_collection": True,
                    "item_type": "Array",
                    "items": [
                        {
                            "backend": "zarr",
                            "path": f"/data/slice_{i}.zarr",
                            "metadata": {
                                "type_chain": ["DataObject", "Array"],
                                "axes": ["y", "x"],
                                "shape": [8, 8],
                                "dtype": "uint8",
                            },
                        }
                        for i in range(3)
                    ],
                }
            }
        }
        result = reconstruct_inputs(payload)

        collection = result["stack"]
        assert isinstance(collection, Collection)
        assert collection.item_type is Array
        assert collection.length == 3
        for item in collection:
            assert isinstance(item, Array)
            assert item.axes == ["y", "x"]
            assert item.shape == (8, 8)

    def test_scalar_pass_through(self) -> None:
        """Non-DataObject inputs (scalars, strings) pass through untouched."""
        payload = {
            "inputs": {
                "threshold": 0.5,
                "label": "run-1",
                "flags": [True, False],
                "nothing": None,
            }
        }
        result = reconstruct_inputs(payload)
        assert result == {
            "threshold": 0.5,
            "label": "run-1",
            "flags": [True, False],
            "nothing": None,
        }

    def test_empty_inputs(self) -> None:
        """Payload without ``inputs`` key returns an empty dict."""
        assert reconstruct_inputs({"block_class": "mod.Block"}) == {}


# ---------------------------------------------------------------------------
# worker.serialise_outputs — dispatcher cases
# ---------------------------------------------------------------------------


class TestSerialiseOutputs:
    def test_serialises_dataobject_via_helper(self, tmp_path) -> None:
        """A typed DataObject output is run through _serialise_one."""
        import numpy as np
        import zarr

        zarr_path = str(tmp_path / "arr.zarr")
        zarr.save(zarr_path, np.zeros((4, 4), dtype="uint8"))
        arr = Array(
            axes=["y", "x"],
            shape=(4, 4),
            dtype="uint8",
            storage_ref=_ref(zarr_path),
        )
        result = serialise_outputs({"image": arr}, str(tmp_path))

        md = result["image"]["metadata"]
        assert md["type_chain"] == ["DataObject", "Array"]
        assert md["axes"] == ["y", "x"]
        assert md["shape"] == [4, 4]
        assert md["dtype"] == "uint8"
        # framework slot is populated.
        assert "framework" in md
        assert "object_id" in md["framework"]

    def test_serialises_collection_via_helper(self, tmp_path) -> None:
        """Collection outputs wrap per-item payloads with ``_collection: True``."""
        import numpy as np
        import zarr

        zarr_path1 = str(tmp_path / "arr1.zarr")
        zarr_path2 = str(tmp_path / "arr2.zarr")
        zarr.save(zarr_path1, np.zeros((2, 2), dtype="uint8"))
        zarr.save(zarr_path2, np.zeros((4, 4), dtype="uint8"))
        arr1 = Array(axes=["y", "x"], shape=(2, 2), dtype="uint8", storage_ref=_ref(zarr_path1))
        arr2 = Array(axes=["y", "x"], shape=(4, 4), dtype="uint8", storage_ref=_ref(zarr_path2))
        col = Collection([arr1, arr2], item_type=Array)

        result = serialise_outputs({"stack": col}, str(tmp_path))
        stack_payload = result["stack"]

        assert stack_payload["_collection"] is True
        assert stack_payload["item_type"] == "Array"
        assert len(stack_payload["items"]) == 2
        for item_payload in stack_payload["items"]:
            assert item_payload["metadata"]["type_chain"] == ["DataObject", "Array"]

    def test_scalar_pass_through(self) -> None:
        """Scalars and primitives are emitted as-is."""
        outputs = {"n": 42, "name": "hello", "flag": True, "nothing": None}
        assert serialise_outputs(outputs, "") == outputs

    def test_empty_outputs(self) -> None:
        assert serialise_outputs({}, "") == {}


# ---------------------------------------------------------------------------
# End-to-end: serialise_outputs → reconstruct_inputs
# ---------------------------------------------------------------------------


class TestSerialiseOutputsRoundTrip:
    def test_round_trip_array(self, tmp_path) -> None:
        import numpy as np
        import zarr

        zarr_path = str(tmp_path / "rt.zarr")
        zarr.save(zarr_path, np.zeros((16, 16), dtype="float32"))
        original = Array(
            axes=["y", "x"],
            shape=(16, 16),
            dtype="float32",
            storage_ref=_ref(zarr_path),
        )
        wire = serialise_outputs({"out": original}, str(tmp_path))

        # Feed the serialised wire format back in as a reconstruct_inputs payload.
        payload = {"inputs": wire}
        inputs = reconstruct_inputs(payload)
        rebuilt = inputs["out"]

        assert isinstance(rebuilt, Array)
        assert rebuilt.axes == original.axes
        assert rebuilt.shape == original.shape
        assert rebuilt.dtype == original.dtype

    def test_round_trip_collection(self, tmp_path) -> None:
        import numpy as np
        import zarr

        items = []
        for i in range(3):
            zarr_path = str(tmp_path / f"col_{i}.zarr")
            zarr.save(zarr_path, np.zeros((2, 2), dtype="uint8"))
            items.append(Array(axes=["y", "x"], shape=(2, 2), dtype="uint8", storage_ref=_ref(zarr_path)))
        col = Collection(items, item_type=Array)
        wire = serialise_outputs({"stack": col}, str(tmp_path))
        inputs = reconstruct_inputs({"inputs": wire})

        rebuilt: Collection = inputs["stack"]
        assert isinstance(rebuilt, Collection)
        assert rebuilt.length == 3
        assert rebuilt.item_type is Array
        for rebuilt_item in rebuilt:
            assert isinstance(rebuilt_item, Array)
            assert rebuilt_item.axes == ["y", "x"]
            assert rebuilt_item.shape == (2, 2)


# ---------------------------------------------------------------------------
# Typed-instance API availability after reconstruction
# ---------------------------------------------------------------------------


class TestReconstructedInstanceBehaviour:
    def test_isinstance_of_typed_class(self) -> None:
        payload = _serialise_one(
            Array(axes=["y", "x"], shape=(8, 8), dtype="uint8", storage_ref=_ref()),
        )
        rebuilt = _reconstruct_one(payload)

        assert isinstance(rebuilt, Array)
        assert isinstance(rebuilt, DataObject)

    def test_supports_with_meta(self) -> None:
        """Reconstructed instance exposes the with_meta immutable update."""
        _register_fixture(_ArrayWithMeta)
        try:
            original = _ArrayWithMeta(
                axes=["y", "x"],
                shape=(2, 2),
                dtype="uint8",
                meta=_FixtureMeta(label="v1", count=1),
                storage_ref=_ref(),
            )
            payload = _serialise_one(original)
            rebuilt = _reconstruct_one(payload)

            assert isinstance(rebuilt, _ArrayWithMeta)
            assert isinstance(rebuilt.meta, _FixtureMeta)

            # with_meta returns a new instance with updated meta fields
            # and a freshly-derived framework.
            updated = rebuilt.with_meta(count=99)
            assert updated.meta is not None
            assert updated.meta.count == 99  # type: ignore[attr-defined]
            # rebuilt is unchanged.
            assert rebuilt.meta.count == 1
        finally:
            _reset_registry_singleton()

    def test_does_not_load_payload_eagerly(self) -> None:
        """storage_ref is set but to_memory() is not called during reconstruction.

        We use a payload pointing at a non-existent path: if reconstruction
        were eager, the Zarr backend would raise; since reconstruction is
        lazy at the method level, we only see the failure if we explicitly
        call to_memory().
        """
        payload = {
            "backend": "zarr",
            "path": "/nonexistent/definitely/not/there.zarr",
            "format": "zarr",
            "metadata": {
                "type_chain": ["DataObject", "Array"],
                "axes": ["y", "x"],
                "shape": [8, 8],
                "dtype": "uint8",
            },
        }

        # Reconstruction must not touch the backend.
        obj = _reconstruct_one(payload)
        assert obj.storage_ref is not None
        assert obj.storage_ref.path.endswith("there.zarr")
        # The object exists and exposes its metadata-level attributes
        # without any I/O against the (non-existent) storage.
        assert obj.axes == ["y", "x"]
        assert obj.shape == (8, 8)


# ---------------------------------------------------------------------------
# _get_type_registry singleton semantics
# ---------------------------------------------------------------------------


class TestTypeRegistrySingleton:
    def test_singleton_returns_same_instance(self) -> None:
        """Repeated calls return the same registry instance."""
        _reset_registry_singleton()
        r1 = _get_type_registry()
        r2 = _get_type_registry()
        assert r1 is r2

    def test_singleton_registers_core_builtins(self) -> None:
        """After warm-up the six core base classes are all registered."""
        _reset_registry_singleton()
        registry = _get_type_registry()
        names: set[str] = set(registry.all_types().keys())
        for core_name in ("DataObject", "Array", "Series", "DataFrame", "Text", "Artifact", "CompositeData"):
            assert core_name in names

    def test_singleton_can_resolve_type_chain(self) -> None:
        """resolve(type_chain) works off the singleton instance."""
        _reset_registry_singleton()
        registry = _get_type_registry()
        cls: Any = registry.resolve(["DataObject", "Array"])
        assert cls is Array

    def test_singleton_scans_monorepo_types_in_dev_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SCISTUDIO_DEV=1 enables monorepo plugin type discovery in workers."""
        from scistudio.core.types.registry import TypeRegistry

        calls: list[bool] = []

        def fake_scan(self: TypeRegistry) -> None:
            calls.append(True)

        _reset_registry_singleton()
        monkeypatch.setenv("SCISTUDIO_DEV", "1")
        monkeypatch.setattr(TypeRegistry, "_scan_monorepo_types", fake_scan)

        _get_type_registry()

        assert calls == [True]

    def test_singleton_skips_monorepo_types_outside_dev_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Worker registry keeps release entry-point behaviour when not in dev mode."""
        from scistudio.core.types.registry import TypeRegistry

        calls: list[bool] = []

        def fake_scan(self: TypeRegistry) -> None:
            calls.append(True)

        _reset_registry_singleton()
        monkeypatch.delenv("SCISTUDIO_DEV", raising=False)
        monkeypatch.setattr(TypeRegistry, "_scan_monorepo_types", fake_scan)

        _get_type_registry()

        assert calls == []


# ---------------------------------------------------------------------------
# Construction failures are wrapped with class context
# ---------------------------------------------------------------------------


class TestReconstructionErrors:
    def test_construction_failure_wrapped_with_class_name(self) -> None:
        """Class ``__init__`` failures surface with the offending class name.

        Forces an axes-schema violation on the module-level
        :class:`_RestrictedArray` fixture (which tightens
        ``allowed_axes`` to ``{"y", "x"}``). Passing ``axes=["t"]``
        trips :meth:`Array._validate_axes`, and
        :func:`_reconstruct_one` must wrap the resulting ``ValueError``
        with a message that includes the class name so operators can
        find the broken payload quickly.
        """
        _register_fixture(_RestrictedArray)
        try:
            payload = {
                "backend": None,
                "path": None,
                "format": None,
                "metadata": {
                    "type_chain": ["DataObject", "Array", "_RestrictedArray"],
                    "axes": ["t"],  # not in allowed_axes → schema violation
                },
            }
            with pytest.raises(ValueError, match="Failed to reconstruct _RestrictedArray"):
                _reconstruct_one(payload)
        finally:
            _reset_registry_singleton()
