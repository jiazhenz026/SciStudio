"""Tests for engine-side Collection wrap normalization (#1330).

ADR-020 §3 requires every value crossing a block boundary to be a
:class:`Collection`. The engine — not the block — is responsible for
honouring that contract. ``_normalize_outputs`` in
:mod:`scistudio.engine.runners.worker` performs the wrap at the output
boundary.

These tests exercise the helper directly (unit-level) since the wrap
logic is independent of the runner protocol. The two call sites
(worker subprocess pre-``serialise_outputs`` and scheduler in-process
pre-``_block_outputs`` storage) both delegate to this helper.
"""

from __future__ import annotations

from scistudio.blocks.base.ports import OutputPort
from scistudio.core.types.array import Array
from scistudio.core.types.collection import Collection
from scistudio.engine.runners.worker import _normalize_outputs


def _make_array() -> Array:
    """Return a bare :class:`Array` with deterministic axes/shape."""
    return Array(axes=["y", "x"], shape=(4, 4), dtype="uint8")


class TestEngineWrapsBareDataObject:
    """Bare DataObject on an ``is_collection=True`` port is auto-wrapped."""

    def test_engine_wraps_bare_dataobject_on_is_collection_port(self) -> None:
        """Block returns ``{"out": bare_array}`` for an ``is_collection`` port;
        the post-normalize value is ``Collection([bare_array], item_type=Array)``.

        This is the core ADR-020 §3 contract enforcement gap from #1330.
        """
        bare = _make_array()
        ports = [
            OutputPort(name="out", accepted_types=[Array], is_collection=True),
        ]
        outputs: dict = {"out": bare}

        _normalize_outputs(outputs, ports)

        wrapped = outputs["out"]
        assert isinstance(wrapped, Collection)
        assert len(wrapped) == 1
        assert wrapped[0] is bare
        # item_type=type(value) per #1330 spec — matches ai_block.py:532
        # precedent. Subclass narrowing is stable under Add6.
        assert wrapped.item_type is Array


class TestEngineUnpacksBareListOfDataObjects:
    """Bare ``list[DataObject]`` on an ``is_collection=True`` port is packed."""

    def test_engine_packs_bare_list_of_dataobjects_into_collection(self) -> None:
        """Block returns ``{"out": [a, b, c]}`` (native Python list) for an
        ``is_collection=True`` port; post-normalize value is
        ``Collection([a, b, c], item_type=Array)``.

        ADR-020 §3 says "multi-file or multi-object input is represented
        as a longer Collection" — bare lists must be packed by engine so
        the block can return native shapes without doing the wrap itself.
        Without this branch the list would fall through unwrapped or be
        wrapped as a single 1-item Collection containing the list itself
        (which fails Collection's homogeneity check). Owner directive
        2026-05-21 option (a).
        """
        a, b, c = _make_array(), _make_array(), _make_array()
        ports = [
            OutputPort(name="out", accepted_types=[Array], is_collection=True),
        ]
        outputs: dict = {"out": [a, b, c]}

        _normalize_outputs(outputs, ports)

        packed = outputs["out"]
        assert isinstance(packed, Collection)
        assert len(packed) == 3
        assert packed[0] is a
        assert packed[1] is b
        assert packed[2] is c
        assert packed.item_type is Array

    def test_engine_leaves_empty_list_alone(self) -> None:
        """Empty list cannot infer item_type from its first element. ADR-020
        Add6 forbids empty Collection without explicit item_type. The
        engine must NOT silently invent an item_type from the port; let
        the existing serialisation/validation layer surface a clear error.
        """
        ports = [
            OutputPort(name="out", accepted_types=[Array], is_collection=True),
        ]
        outputs: dict = {"out": []}

        _normalize_outputs(outputs, ports)

        assert outputs["out"] == []

    def test_engine_leaves_mixed_list_alone(self) -> None:
        """A list containing a non-DataObject element does not match the
        bare-list-of-DataObject pattern. Leave it alone so downstream
        validation can produce a clear error rather than masking the
        intent with a partial wrap.
        """
        bare = _make_array()
        ports = [
            OutputPort(name="out", accepted_types=[Array], is_collection=True),
        ]
        outputs: dict = {"out": [bare, "not a DataObject"]}

        _normalize_outputs(outputs, ports)

        # Pass through — not packed into a Collection
        assert outputs["out"] == [bare, "not a DataObject"]


class TestEngineDoesNotDoubleWrap:
    """Existing Collection passes through unchanged (identity preserved)."""

    def test_engine_does_not_double_wrap_existing_collection(self) -> None:
        """Block returns ``{"out": Collection([a, b])}``; post-normalize value
        is the SAME Collection instance (identity check) with ``len=2``.

        This guards the six existing manual self-wraps in concrete blocks
        (merge.py / split.py / code_block.py / process_block.py /
        app_block.py / ai_block.py) — engine normalization must be a no-op
        when the block already wrapped.
        """
        a, b = _make_array(), _make_array()
        original = Collection([a, b], item_type=Array)
        ports = [
            OutputPort(name="out", accepted_types=[Array], is_collection=True),
        ]
        outputs: dict = {"out": original}

        _normalize_outputs(outputs, ports)

        assert outputs["out"] is original
        assert len(outputs["out"]) == 2


class TestEngineWrapsBareOnNonCollectionPort:
    """#1811: a bare DataObject on an ``is_collection=False`` port IS wrapped.

    This reverses the original #1330 behaviour (single-value ports kept the
    bare wire format). ADR-020 §3 makes the Collection-as-transport contract
    unconditional; ``is_collection`` is a UI hint only (collection-guide.md)
    and no longer gates the wrap.
    """

    def test_engine_wraps_bare_on_non_collection_port(self) -> None:
        """Block returns ``{"out": bare_array}`` for an ``is_collection=False``
        port; post-normalize value is a length-one Collection.
        """
        bare = _make_array()
        ports = [
            OutputPort(name="out", accepted_types=[Array], is_collection=False),
        ]
        outputs: dict = {"out": bare}

        _normalize_outputs(outputs, ports)

        wrapped = outputs["out"]
        assert isinstance(wrapped, Collection)
        assert len(wrapped) == 1
        assert wrapped[0] is bare


class TestEngineNormalizeEdgeCases:
    """Defensive coverage: unknown port, sentinel keys, non-DataObject values."""

    def test_unknown_port_name_is_left_alone(self) -> None:
        """Sentinel-style keys like ``__scistudio_env__`` (no matching port)
        must not be touched. ADR-038 §5.2 lifts that sentinel into event
        data downstream; corrupting it here would break lineage.
        """
        ports = [
            OutputPort(name="out", accepted_types=[Array], is_collection=True),
        ]
        env_payload = {"python_version": "3.11.0"}
        outputs: dict = {"__scistudio_env__": env_payload}

        _normalize_outputs(outputs, ports)

        assert outputs["__scistudio_env__"] is env_payload

    def test_non_dataobject_value_on_collection_port_is_left_alone(self) -> None:
        """Wire-format dicts and scalars are not DataObject instances and
        must NOT be wrapped (would corrupt them into Collections of dicts).
        ``serialise_outputs`` already pass-through-serialises plain values.
        """
        wire_format = {"backend": "zarr", "path": "/data/x.zarr"}
        ports = [
            OutputPort(name="out", accepted_types=[Array], is_collection=True),
        ]
        outputs: dict = {"out": wire_format, "count": 5}

        _normalize_outputs(outputs, ports)

        assert outputs["out"] is wire_format
        assert outputs["count"] == 5

    def test_idempotent_on_second_call(self) -> None:
        """Calling ``_normalize_outputs`` twice on the same dict is a no-op
        on the second call (Collection input passes through unchanged).
        """
        bare = _make_array()
        ports = [
            OutputPort(name="out", accepted_types=[Array], is_collection=True),
        ]
        outputs: dict = {"out": bare}

        _normalize_outputs(outputs, ports)
        first_pass = outputs["out"]
        _normalize_outputs(outputs, ports)
        second_pass = outputs["out"]

        assert first_pass is second_pass
        assert isinstance(second_pass, Collection)
        assert len(second_pass) == 1
