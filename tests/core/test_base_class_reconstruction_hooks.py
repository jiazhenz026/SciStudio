"""Tests for the six base-class reconstruction hooks (T-013 + T-014).

Exercises the ``reconstruct_extra_kwargs`` / ``serialise_extra_metadata``
classmethod pair that T-013 adds to :class:`DataObject`,
:class:`Array`, :class:`Series`, :class:`DataFrame`, :class:`Text`,
:class:`Artifact`, and :class:`CompositeData` per ADR-027 Addendum 1
§2 ("D11' companion").

The hooks are the contract that lets :func:`_reconstruct_one` /
:func:`_serialise_one` round-trip each base class's constructor-
specific kwargs through the JSON wire format without a giant
``isinstance`` chain inside the worker subprocess.

T-013 shipped the :mod:`scistudio.core.types.serialization` module as a
stub whose bodies raised :class:`NotImplementedError`; T-014 replaced
those bodies with the full implementation. The composite-section
tests in this file therefore exercise the real round-trip instead of
the old stub-raises behaviour (T-014 deleted the
``test_composite_*_raises_until_t014`` and
``test_serialization_stub_*_raises`` tests).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.base import DataObject
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series
from scistudio.core.types.text import Text

# ---------------------------------------------------------------------------
# DataObject base hooks (defaults return empty dict)
# ---------------------------------------------------------------------------


def test_dataobject_default_hooks_return_empty_dict() -> None:
    """The base class hook defaults are intentionally no-ops.

    Plain :class:`DataObject` only takes the four standard slots
    (``storage_ref``, ``framework``, ``meta``, ``user``) and therefore
    has no extras to round-trip. Concrete base classes override.
    """
    assert DataObject.reconstruct_extra_kwargs({}) == {}
    assert DataObject.reconstruct_extra_kwargs({"junk": 1}) == {}

    obj = DataObject()
    assert DataObject.serialise_extra_metadata(obj) == {}


def test_dataobject_hooks_are_classmethods() -> None:
    """Both hooks are classmethods and can be called off the type itself."""
    import inspect

    # classmethod objects expose __self__ == the class after binding.
    cls_kwargs_fn = DataObject.__dict__["reconstruct_extra_kwargs"]
    cls_md_fn = DataObject.__dict__["serialise_extra_metadata"]
    assert isinstance(cls_kwargs_fn, classmethod)
    assert isinstance(cls_md_fn, classmethod)
    # And calling them on the class works without an instance.
    assert inspect.signature(DataObject.reconstruct_extra_kwargs).parameters
    assert inspect.signature(DataObject.serialise_extra_metadata).parameters


# ---------------------------------------------------------------------------
# Array hooks
# ---------------------------------------------------------------------------


def test_arrayreconstruct_extra_kwargs_returns_correct_fields() -> None:
    """Array extracts axes/shape/dtype/chunk_shape and tuplifies shape fields."""
    metadata = {
        "axes": ["t", "z", "y", "x"],
        "shape": [10, 20, 64, 64],
        "dtype": "uint16",
        "chunk_shape": [1, 1, 64, 64],
    }
    kwargs = Array.reconstruct_extra_kwargs(metadata)

    assert kwargs == {
        "axes": ["t", "z", "y", "x"],
        "shape": (10, 20, 64, 64),
        "dtype": "uint16",
        "chunk_shape": (1, 1, 64, 64),
    }
    # Shape and chunk_shape must be tuples, not lists.
    assert isinstance(kwargs["shape"], tuple)
    assert isinstance(kwargs["chunk_shape"], tuple)


def test_arrayreconstruct_extra_kwargs_handles_metadata_only() -> None:
    """Array with no shape / chunk_shape round-trips as None, not empty tuple."""
    metadata = {"axes": ["y", "x"], "dtype": None}
    kwargs = Array.reconstruct_extra_kwargs(metadata)
    assert kwargs["axes"] == ["y", "x"]
    assert kwargs["shape"] is None
    assert kwargs["dtype"] is None
    assert kwargs["chunk_shape"] is None


def test_arrayserialise_extra_metadata_returns_correct_fields() -> None:
    """Array emits JSON-clean lists for shape fields and a stringified dtype."""
    arr = Array(
        axes=["y", "x"],
        shape=(32, 48),
        dtype="float32",
        chunk_shape=(32, 48),
    )
    md = Array.serialise_extra_metadata(arr)
    assert md == {
        "axes": ["y", "x"],
        "shape": [32, 48],
        "dtype": "float32",
        "chunk_shape": [32, 48],
    }
    assert isinstance(md["shape"], list)
    assert isinstance(md["chunk_shape"], list)
    assert isinstance(md["dtype"], str)


def test_array_round_trip_via_hooks() -> None:
    """Serialise then reconstruct an Array via the hook pair; verify equality."""
    original = Array(
        axes=["t", "z", "c", "y", "x"],
        shape=(5, 10, 3, 256, 256),
        dtype="uint8",
        chunk_shape=(1, 1, 1, 256, 256),
    )
    md = Array.serialise_extra_metadata(original)
    kwargs = Array.reconstruct_extra_kwargs(md)
    reconstructed = Array(**kwargs)

    assert reconstructed.axes == original.axes
    assert reconstructed.shape == original.shape
    assert reconstructed.dtype == original.dtype
    assert reconstructed.chunk_shape == original.chunk_shape


def test_array_round_trip_metadata_only_none_fields() -> None:
    """Metadata-only Array (shape=None, chunk_shape=None) round-trips cleanly."""
    original = Array(axes=["y", "x"])
    md = Array.serialise_extra_metadata(original)
    kwargs = Array.reconstruct_extra_kwargs(md)
    reconstructed = Array(**kwargs)

    assert reconstructed.axes == ["y", "x"]
    assert reconstructed.shape is None
    assert reconstructed.dtype is None
    assert reconstructed.chunk_shape is None


# ---------------------------------------------------------------------------
# Series hooks
# ---------------------------------------------------------------------------


def test_seriesreconstruct_extra_kwargs_returns_correct_fields() -> None:
    metadata = {
        "index_name": "wavenumber",
        "value_name": "intensity",
        "length": 2048,
    }
    assert Series.reconstruct_extra_kwargs(metadata) == metadata


def test_seriesserialise_extra_metadata_returns_correct_fields() -> None:
    series = Series(index_name="time", value_name="voltage", length=1000)
    md = Series.serialise_extra_metadata(series)
    assert md == {
        "index_name": "time",
        "value_name": "voltage",
        "length": 1000,
    }


def test_series_round_trip_via_hooks() -> None:
    original = Series(index_name="mz", value_name="intensity", length=4096)
    md = Series.serialise_extra_metadata(original)
    kwargs = Series.reconstruct_extra_kwargs(md)
    reconstructed = Series(**kwargs)

    assert reconstructed.index_name == original.index_name
    assert reconstructed.value_name == original.value_name
    assert reconstructed.length == original.length


def test_series_round_trip_with_missing_fields() -> None:
    """Missing optional fields round-trip as ``None``."""
    md: dict = {}
    kwargs = Series.reconstruct_extra_kwargs(md)
    reconstructed = Series(**kwargs)
    assert reconstructed.index_name is None
    assert reconstructed.value_name is None
    assert reconstructed.length is None


# ---------------------------------------------------------------------------
# DataFrame hooks
# ---------------------------------------------------------------------------


def test_dataframereconstruct_extra_kwargs_returns_correct_fields() -> None:
    metadata = {
        "columns": ["a", "b", "c"],
        "row_count": 42,
        "schema": {"a": "int64", "b": "float64", "c": "string"},
    }
    kwargs = DataFrame.reconstruct_extra_kwargs(metadata)
    assert kwargs == {
        "columns": ["a", "b", "c"],
        "row_count": 42,
        "schema": {"a": "int64", "b": "float64", "c": "string"},
    }


def test_dataframeserialise_extra_metadata_returns_correct_fields() -> None:
    df = DataFrame(columns=["x", "y"], row_count=100, schema={"x": "int", "y": "float"})
    md = DataFrame.serialise_extra_metadata(df)
    assert md == {
        "columns": ["x", "y"],
        "row_count": 100,
        "schema": {"x": "int", "y": "float"},
    }


def test_dataframe_round_trip_via_hooks() -> None:
    original = DataFrame(
        columns=["peak_mz", "peak_intensity", "retention_time"],
        row_count=5000,
        schema={"peak_mz": "float64", "peak_intensity": "float64", "retention_time": "float64"},
    )
    md = DataFrame.serialise_extra_metadata(original)
    kwargs = DataFrame.reconstruct_extra_kwargs(md)
    reconstructed = DataFrame(**kwargs)

    assert reconstructed.columns == original.columns
    assert reconstructed.row_count == original.row_count
    assert reconstructed.schema == original.schema


def test_dataframe_round_trip_empty_defaults() -> None:
    """A DataFrame reconstructed from an empty metadata dict has empty column/schema."""
    kwargs = DataFrame.reconstruct_extra_kwargs({})
    reconstructed = DataFrame(**kwargs)
    assert reconstructed.columns == []
    assert reconstructed.row_count is None
    assert reconstructed.schema == {}


# ---------------------------------------------------------------------------
# Text hooks
# ---------------------------------------------------------------------------


def test_textreconstruct_extra_kwargs_returns_correct_fields() -> None:
    metadata = {"content": "hello", "format": "markdown", "encoding": "utf-16"}
    kwargs = Text.reconstruct_extra_kwargs(metadata)
    assert kwargs == {
        "content": "hello",
        "format": "markdown",
        "encoding": "utf-16",
    }


def test_textreconstruct_extra_kwargs_applies_defaults() -> None:
    """Missing format/encoding fall back to the constructor defaults."""
    kwargs = Text.reconstruct_extra_kwargs({})
    assert kwargs == {"content": None, "format": "plain", "encoding": "utf-8"}


def test_textserialise_extra_metadata_returns_correct_fields() -> None:
    text = Text(content="ABC", format="plain", encoding="utf-8")
    md = Text.serialise_extra_metadata(text)
    assert md == {"content": "ABC", "format": "plain", "encoding": "utf-8"}


def test_text_round_trip_via_hooks() -> None:
    original = Text(content="# Heading\n\nbody", format="markdown", encoding="utf-8")
    md = Text.serialise_extra_metadata(original)
    kwargs = Text.reconstruct_extra_kwargs(md)
    reconstructed = Text(**kwargs)

    assert reconstructed.content == original.content
    assert reconstructed.format == original.format
    assert reconstructed.encoding == original.encoding


# ---------------------------------------------------------------------------
# Artifact hooks
# ---------------------------------------------------------------------------


def test_artifactreconstruct_extra_kwargs_returns_correct_fields() -> None:
    metadata = {
        "file_path": "/tmp/report.pdf",
        "mime_type": "application/pdf",
        "description": "Quarterly report",
    }
    kwargs = Artifact.reconstruct_extra_kwargs(metadata)
    assert kwargs["file_path"] == Path("/tmp/report.pdf")
    assert isinstance(kwargs["file_path"], Path)
    assert kwargs["mime_type"] == "application/pdf"
    assert kwargs["description"] == "Quarterly report"


def test_artifactreconstruct_extra_kwargs_handles_none_path() -> None:
    """A missing file_path round-trips as ``None``, not ``Path('.')``."""
    kwargs = Artifact.reconstruct_extra_kwargs({})
    assert kwargs["file_path"] is None
    assert kwargs["mime_type"] is None
    assert kwargs["description"] == ""


def test_artifactserialise_extra_metadata_returns_correct_fields() -> None:
    artifact = Artifact(
        file_path=Path("/tmp/output.bin"),
        mime_type="application/octet-stream",
        description="binary dump",
    )
    md = Artifact.serialise_extra_metadata(artifact)
    # file_path must be stringified (JSON-clean).
    assert md["file_path"] == str(Path("/tmp/output.bin"))
    assert isinstance(md["file_path"], str)
    assert md["mime_type"] == "application/octet-stream"
    assert md["description"] == "binary dump"


def test_artifact_round_trip_via_hooks() -> None:
    original = Artifact(
        file_path=Path("/data/figure.png"),
        mime_type="image/png",
        description="test figure",
    )
    md = Artifact.serialise_extra_metadata(original)
    # Verify the wire format is JSON-clean (no Path objects).
    import json

    json.dumps(md)  # must not raise

    kwargs = Artifact.reconstruct_extra_kwargs(md)
    reconstructed = Artifact(**kwargs)

    assert reconstructed.file_path == original.file_path
    assert reconstructed.mime_type == original.mime_type
    assert reconstructed.description == original.description


def test_artifact_round_trip_none_path() -> None:
    """Artifact with file_path=None round-trips cleanly."""
    original = Artifact(file_path=None, mime_type="text/plain", description="")
    md = Artifact.serialise_extra_metadata(original)
    assert md["file_path"] is None
    kwargs = Artifact.reconstruct_extra_kwargs(md)
    reconstructed = Artifact(**kwargs)
    assert reconstructed.file_path is None


# ---------------------------------------------------------------------------
# CompositeData slots — round-4 no-cycles (#1342)
#
# CompositeData no longer overrides ``serialise_extra_metadata`` /
# ``reconstruct_extra_kwargs``. Its slots are nested ``DataObject``s, and the
# recursion that (de)serialises them is owned by the serialiser itself
# (``_serialise_one`` / ``_reconstruct_one`` handle the CompositeData case) so
# the type does not import the serialiser back — that edge closed a
# core.types-internal import cycle. These tests exercise the slot recursion
# through the serialiser entry points (the wire format is unchanged).
# ---------------------------------------------------------------------------


def _composite_ref():
    from scistudio.core.storage.ref import StorageReference

    return StorageReference(backend="composite", path="/tmp/c")


def test_composite_reconstruct_recurses_through_serialiser() -> None:
    """``_reconstruct_one`` rebuilds each composite slot as its own typed object."""
    from scistudio.core.types.serialization import _reconstruct_one

    payload = {
        "backend": "composite",
        "path": "/tmp/c",
        "format": None,
        "metadata": {
            "type_chain": ["DataObject", "CompositeData"],
            "framework": {},
            "meta": None,
            "user": {},
            "slots": {
                "image": {
                    "backend": None,
                    "path": None,
                    "format": None,
                    "metadata": {
                        "type_chain": ["DataObject", "Array"],
                        "framework": {},
                        "meta": None,
                        "user": {},
                        "axes": ["y", "x"],
                        "shape": [4, 4],
                        "dtype": "uint8",
                    },
                }
            },
        },
    }
    rebuilt = _reconstruct_one(payload)

    assert isinstance(rebuilt, CompositeData)
    assert set(rebuilt.slot_names) == {"image"}
    assert isinstance(rebuilt.get("image"), Array)
    assert rebuilt.get("image").axes == ["y", "x"]
    assert rebuilt.get("image").shape == (4, 4)


def test_composite_reconstruct_empty_slots() -> None:
    """No (or missing) ``slots`` ⇒ an empty composite."""
    from scistudio.core.types.serialization import _reconstruct_one

    base_md = {
        "type_chain": ["DataObject", "CompositeData"],
        "framework": {},
        "meta": None,
        "user": {},
    }
    envelope = {"backend": "composite", "path": "/tmp/c", "format": None}

    rebuilt_missing = _reconstruct_one({**envelope, "metadata": base_md})
    assert isinstance(rebuilt_missing, CompositeData)
    assert set(rebuilt_missing.slot_names) == set()

    rebuilt_empty = _reconstruct_one({**envelope, "metadata": {**base_md, "slots": {}}})
    assert set(rebuilt_empty.slot_names) == set()


def test_composite_serialise_recurses_through_serialiser() -> None:
    """``_serialise_one`` writes a full wire-format payload per slot."""
    from scistudio.core.storage.ref import StorageReference
    from scistudio.core.types.serialization import _serialise_one

    inner = Array(
        axes=["y", "x"],
        shape=(4, 4),
        dtype="uint8",
        storage_ref=StorageReference(backend="zarr", path="/tmp/slot.zarr"),
    )
    composite = CompositeData(slots={"img": inner}, storage_ref=_composite_ref())

    slots = _serialise_one(composite)["metadata"]["slots"]
    assert set(slots.keys()) == {"img"}
    inner_payload = slots["img"]
    assert "metadata" in inner_payload
    assert inner_payload["metadata"]["type_chain"] == ["DataObject", "Array"]
    assert inner_payload["metadata"]["axes"] == ["y", "x"]
    assert inner_payload["metadata"]["shape"] == [4, 4]


def test_composite_serialise_empty_slots() -> None:
    """An empty composite serialises with ``slots == {}``."""
    from scistudio.core.types.serialization import _serialise_one

    empty = CompositeData(storage_ref=_composite_ref())
    assert _serialise_one(empty)["metadata"]["slots"] == {}


def test_composite_round_trip_through_serialiser() -> None:
    """Full composite round-trip via ``_serialise_one`` / ``_reconstruct_one``.

    Acceptance for CompositeData: a composite with multiple slot types
    (Array + Series + DataFrame) round-trips into an equivalent composite on
    the receiving side — with the recursion owned by the serialiser.
    """
    from scistudio.core.storage.ref import StorageReference
    from scistudio.core.types.serialization import _reconstruct_one, _serialise_one

    image = Array(
        axes=["y", "x"],
        shape=(8, 8),
        dtype="uint8",
        storage_ref=StorageReference(backend="zarr", path="/tmp/img.zarr"),
    )
    trace = Series(
        index_name="time",
        value_name="voltage",
        length=100,
        storage_ref=StorageReference(backend="arrow", path="/tmp/trace.arrow"),
    )
    peaks = DataFrame(
        columns=["mz", "intensity"],
        row_count=50,
        storage_ref=StorageReference(backend="arrow", path="/tmp/peaks.arrow"),
    )
    composite = CompositeData(
        slots={"image": image, "trace": trace, "peaks": peaks},
        storage_ref=_composite_ref(),
    )

    rebuilt = _reconstruct_one(_serialise_one(composite))

    assert isinstance(rebuilt, CompositeData)
    assert set(rebuilt.slot_names) == {"image", "trace", "peaks"}
    assert isinstance(rebuilt.get("image"), Array)
    assert rebuilt.get("image").axes == ["y", "x"]
    assert rebuilt.get("image").shape == (8, 8)
    assert isinstance(rebuilt.get("trace"), Series)
    assert rebuilt.get("trace").length == 100
    assert isinstance(rebuilt.get("peaks"), DataFrame)
    assert rebuilt.get("peaks").row_count == 50


# ---------------------------------------------------------------------------
# serialization module — public surface
# ---------------------------------------------------------------------------


def test_serialization_module_imports() -> None:
    """The module must be importable and expose both helpers.

    The signatures were locked by T-013 and remain locked after T-014
    replaced the stub bodies with the real implementation.
    """
    from scistudio.core.types import serialization
    from scistudio.core.types.serialization import _reconstruct_one, _serialise_one

    assert callable(_reconstruct_one)
    assert callable(_serialise_one)
    assert hasattr(serialization, "_reconstruct_one")
    assert hasattr(serialization, "_serialise_one")


def test_serialization_reconstruct_round_trips_bare_dataobject() -> None:
    """Positive smoke test for the real :func:`_reconstruct_one` body.

    Replaces the T-013 ``test_serialization_stub_reconstruct_raises``.
    """
    from scistudio.core.types.serialization import _reconstruct_one

    obj = _reconstruct_one(
        {
            "backend": None,
            "path": None,
            "format": None,
            "metadata": {
                "type_chain": ["DataObject"],
                "framework": {},
                "meta": None,
                "user": {},
            },
        }
    )
    assert type(obj) is DataObject


def test_serialization_serialise_round_trips_bare_dataobject() -> None:
    """Positive smoke test for the real :func:`_serialise_one` body.

    Replaces the T-013 ``test_serialization_stub_serialise_raises``.
    ADR-031 Addendum 1: storage_ref is required for serialisation.
    """
    from scistudio.core.storage.ref import StorageReference
    from scistudio.core.types.serialization import _serialise_one

    obj = DataObject(storage_ref=StorageReference(backend="zarr", path="/tmp/test.zarr"))
    payload = _serialise_one(obj)
    assert payload["metadata"]["type_chain"] == ["DataObject"]
    assert payload["metadata"]["meta"] is None
    assert payload["metadata"]["user"] == {}


def test_serialization_serialise_rejects_none_storage_ref() -> None:
    """ADR-031 Addendum 1: _serialise_one rejects DataObject without storage_ref."""
    from scistudio.core.types.serialization import _serialise_one

    with pytest.raises(ValueError, match="storage_ref is None"):
        _serialise_one(DataObject())


# ---------------------------------------------------------------------------
# Cross-class discovery: all six base classes declare both hooks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "base_class",
    [DataObject, Array, Series, DataFrame, Text, Artifact, CompositeData],
)
def test_all_six_base_classes_have_both_hooks(base_class: type) -> None:
    """Every core base class must declare both hook classmethods.

    This is the contract T-014's worker relies on: it calls
    ``cls.reconstruct_extra_kwargs(md)`` and
    ``type(obj).serialise_extra_metadata(obj)`` unconditionally,
    trusting that every registered type provides them (inherited from
    the :class:`DataObject` default if not overridden).
    """
    assert hasattr(base_class, "reconstruct_extra_kwargs")
    assert hasattr(base_class, "serialise_extra_metadata")
    # Must be classmethods (callable off the class directly).
    assert callable(base_class.reconstruct_extra_kwargs)
    assert callable(base_class.serialise_extra_metadata)
    # Default behaviour on an empty metadata dict must not raise
    # (except for CompositeData, whose empty-slots short-circuit is
    # already verified above — but even there, {} should be safe).
    result = base_class.reconstruct_extra_kwargs({})
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Plugin-subclass override pattern (documented in ADR-027 Addendum 1 §2)
# ---------------------------------------------------------------------------


class _PluginArray(Array):
    """Hypothetical plugin subclass that adds an extra geometry field."""

    @classmethod
    def reconstruct_extra_kwargs(cls, metadata: dict) -> dict:
        kwargs = super().reconstruct_extra_kwargs(metadata)
        kwargs["_plugin_extra"] = metadata.get("plugin_extra", "default")
        return kwargs

    @classmethod
    def serialise_extra_metadata(cls, obj: _PluginArray) -> dict:
        md = super().serialise_extra_metadata(obj)
        md["plugin_extra"] = getattr(obj, "_plugin_extra", "default")
        return md


def test_plugin_subclass_can_override_and_super() -> None:
    """Plugin subclasses chain via ``super()`` to pick up parent extras.

    ADR-027 Addendum 1 §2 documents this as the override pattern:
    plugin subclasses that add geometry-like fields outside the ``Meta``
    Pydantic model override ``reconstruct_extra_kwargs`` and call
    ``super().reconstruct_extra_kwargs(metadata)`` to inherit the
    parent class's extras, then extend the returned dict.
    """
    metadata = {
        "axes": ["y", "x"],
        "shape": [8, 8],
        "dtype": "uint8",
        "chunk_shape": None,
        "plugin_extra": "hyperspectral",
    }
    kwargs = _PluginArray.reconstruct_extra_kwargs(metadata)
    # Parent-class extras are present.
    assert kwargs["axes"] == ["y", "x"]
    assert kwargs["shape"] == (8, 8)
    assert kwargs["dtype"] == "uint8"
    assert kwargs["chunk_shape"] is None
    # Plugin extra is added on top.
    assert kwargs["_plugin_extra"] == "hyperspectral"
