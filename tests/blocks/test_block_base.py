"""Tests for Block ABC — validate(), postprocess(), terminate_grace_sec.

The worker-side block state machine (``Block.state`` / ``Block.transition`` /
``_VALID_TRANSITIONS``) was removed in #1334; the engine-owned
``DAGScheduler._block_states`` is the authoritative state machine (ADR-018
§8.1). The corresponding ``TestBlockTransition`` /
``TestBlockTransitionCancelledSkipped`` classes were deleted with it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pytest

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.core.storage.flush_context import clear, set_output_dir
from scistudio.core.types.array import Array
from scistudio.core.types.dataframe import DataFrame


@pytest.fixture(autouse=True)
def _flush_context(tmp_path):
    """ADR-031 Addendum 1: auto_flush now hard-gates on output_dir."""
    set_output_dir(str(tmp_path))
    yield
    clear()


# ---------------------------------------------------------------------------
# Local test fixture subclass.
#
# ADR-027 D2: the core ``Image`` class was removed in T-006; domain
# specializations live in plugin packages. These tests need an Array
# subclass that accepts the legacy ``shape=/ndim=/dtype=`` construction
# shape, so we declare a minimal fixture subclass here. This mirrors the
# pattern already used in ``tests/core/test_types.py``.
# ---------------------------------------------------------------------------


class Image(Array):
    """Local 2D Array test fixture (not the plugin ``Image``).

    Declares ``required_axes = {"y", "x"}`` so it exercises the
    schema-enforcement code path while accepting the legacy
    ``shape=/ndim=/dtype=`` kwargs used by the pre-T-006 tests.
    """

    required_axes: ClassVar[frozenset[str]] = frozenset({"y", "x"})

    def __init__(
        self,
        *,
        shape: tuple[int, ...] | None = None,
        ndim: int | None = None,
        dtype: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(axes=["y", "x"], shape=shape, dtype=dtype, **kwargs)


class _DummyBlock(Block):
    """Minimal concrete Block subclass for testing."""

    name: ClassVar[str] = "Dummy"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Array]),
        InputPort(name="optional", accepted_types=[DataFrame], required=False),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="result", accepted_types=[Array]),
    ]

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        return {"result": inputs.get("image")}


class _ConstrainedBlock(Block):
    """Block with a constraint function on its input port."""

    name: ClassVar[str] = "Constrained"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(
            name="data",
            accepted_types=[Array],
            constraint=lambda v: hasattr(v, "shape") and v.shape is not None,
            constraint_description="Must have non-None shape",
        ),
    ]
    output_ports: ClassVar[list[OutputPort]] = []

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        return {}


class _EmptyAcceptBlock(Block):
    """Block with an input port that accepts any type."""

    name: ClassVar[str] = "EmptyAccept"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="anything", accepted_types=[]),
    ]
    output_ports: ClassVar[list[OutputPort]] = []

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        return {}


class TestBlockValidate:
    """Block.validate — port contract checking."""

    def test_validate_correct_input(self) -> None:
        block = _DummyBlock()
        img = Image(shape=(10, 10), ndim=2, dtype="float64")
        assert block.validate({"image": img}) is True

    def test_validate_missing_required_port(self) -> None:
        block = _DummyBlock()
        with pytest.raises(ValueError, match="Required input port 'image' is missing"):
            block.validate({})

    def test_validate_optional_port_missing(self) -> None:
        block = _DummyBlock()
        img = Image(shape=(10, 10), ndim=2, dtype="float64")
        assert block.validate({"image": img}) is True

    def test_validate_wrong_type_raises(self) -> None:
        block = _DummyBlock()
        df = DataFrame(columns=["a"], row_count=1)
        with pytest.raises(ValueError, match="Port 'image'"):
            block.validate({"image": df})

    def test_validate_subtype_accepted(self) -> None:
        block = _DummyBlock()
        img = Image(shape=(10, 10), ndim=2, dtype="float64")
        assert block.validate({"image": img}) is True

    def test_validate_constraint_passes(self) -> None:
        block = _ConstrainedBlock()
        arr = Array(axes=["x"], shape=(5,), dtype="float64")
        assert block.validate({"data": arr}) is True

    def test_validate_constraint_fails(self) -> None:
        block = _ConstrainedBlock()
        arr = Array(axes=["x"], shape=None, dtype="float64")
        with pytest.raises(ValueError, match="constraint failed"):
            block.validate({"data": arr})

    def test_validate_empty_accepted_types(self) -> None:
        block = _EmptyAcceptBlock()
        assert block.validate({"anything": "literally anything"}) is True


class TestBlockPostprocess:
    """Block.postprocess — default passthrough."""

    def test_postprocess_passthrough(self) -> None:
        block = _DummyBlock()
        outputs = {"result": "value"}
        assert block.postprocess(outputs) is outputs


class TestTerminateGraceSec:
    """ADR-019: terminate_grace_sec ClassVar."""

    def test_default_value(self) -> None:
        block = _DummyBlock()
        assert block.terminate_grace_sec == 5.0

    def test_custom_subclass(self) -> None:
        class CustomBlock(Block):
            name: ClassVar[str] = "Custom"
            terminate_grace_sec: ClassVar[float] = 10.0

            def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
                return {}

        block = CustomBlock()
        assert block.terminate_grace_sec == 10.0


class TestValidateCollectionTransparency:
    """Issue #129: Block.validate() correctly validates Collection inputs via item_type."""

    def test_validate_collection_with_matching_item_type(self) -> None:
        """Collection[Image] should pass validation for a port accepting Array."""
        from scistudio.core.types.collection import Collection

        block = _DummyBlock()
        img = Image(shape=(10, 10), ndim=2, dtype="float64")
        c = Collection([img])
        # Collection[Image] -> port accepts Array -> Image is subtype of Array -> pass
        assert block.validate({"image": c}) is True

    def test_validate_collection_with_wrong_item_type(self) -> None:
        """Collection[DataFrame] should fail validation for a port accepting Array."""
        from scistudio.core.types.collection import Collection

        block = _DummyBlock()
        df = DataFrame(columns=["a"], row_count=1)
        c = Collection([df])
        with pytest.raises(ValueError, match="Collection item type"):
            block.validate({"image": c})

    def test_validate_collection_exact_item_type(self) -> None:
        """Collection[Image] should pass validation for a port accepting Image."""
        from scistudio.core.types.collection import Collection

        class _ImageBlock(Block):
            name: ClassVar[str] = "ImageOnly"
            input_ports: ClassVar[list[InputPort]] = [
                InputPort(name="img", accepted_types=[Image]),
            ]
            output_ports: ClassVar[list[OutputPort]] = []

            def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
                return {}

        block = _ImageBlock()
        img = Image(shape=(5, 5), ndim=2, dtype="uint8")
        c = Collection([img])
        assert block.validate({"img": c}) is True

    def test_validate_collection_empty_accepted_types(self) -> None:
        """Collection should pass validation for a port accepting anything."""
        from scistudio.core.types.collection import Collection

        block = _EmptyAcceptBlock()
        img = Image(shape=(5, 5), ndim=2, dtype="uint8")
        c = Collection([img])
        assert block.validate({"anything": c}) is True


class TestCollectionUtilities:
    """ADR-020: pack(), unpack(), unpack_single(), map_items(), parallel_map()."""

    def test_pack_creates_collection(self) -> None:
        from scistudio.core.types.collection import Collection

        items = [Image(shape=(10, 10), ndim=2, dtype="float64")]
        result = Block.pack(items, item_type=Image)
        assert isinstance(result, Collection)
        assert result.length == 1
        assert result.item_type is Image

    def test_unpack_returns_list(self) -> None:
        from scistudio.core.types.collection import Collection

        img = Image(shape=(5, 5), ndim=2, dtype="uint8")
        c = Collection([img], item_type=Image)
        items = Block.unpack(c)
        assert isinstance(items, list)
        assert len(items) == 1
        assert items[0] is img

    def test_unpack_single(self) -> None:
        from scistudio.core.types.collection import Collection

        img = Image(shape=(5, 5), ndim=2, dtype="uint8")
        c = Collection([img])
        result = Block.unpack_single(c)
        assert result is img

    def test_unpack_single_multi_raises(self) -> None:
        from scistudio.core.types.collection import Collection

        items = [
            Image(shape=(5, 5), ndim=2, dtype="uint8"),
            Image(shape=(3, 3), ndim=2, dtype="uint8"),
        ]
        c = Collection(items)
        with pytest.raises(ValueError, match="single-item"):
            Block.unpack_single(c)

    def test_map_items(self) -> None:
        from scistudio.core.types.collection import Collection

        items = [
            Image(shape=(5, 5), ndim=2, dtype="uint8"),
            Image(shape=(3, 3), ndim=2, dtype="float32"),
        ]
        c = Collection(items)
        result = Block.map_items(lambda x: x, c)
        assert isinstance(result, Collection)
        assert result.length == 2


class TestAutoFlush:
    """Block._auto_flush — auto-persistence of in-memory DataObjects."""

    def teardown_method(self) -> None:
        """Clear flush context after each test."""
        from scistudio.core.storage.flush_context import clear

        clear()

    def test_auto_flush_non_dataobject(self) -> None:
        """Non-DataObject values pass through unchanged."""
        result = Block._auto_flush("just a string")
        assert result == "just a string"

    def test_auto_flush_already_has_ref(self) -> None:
        """DataObject with an existing StorageReference passes through."""
        from scistudio.core.storage.ref import StorageReference

        img = Image(shape=(5, 5), ndim=2, dtype="float64")
        img.storage_ref = StorageReference(backend="zarr", path="/tmp/test.zarr")
        result = Block._auto_flush(img)
        assert result is img

    def test_auto_flush_no_context_returns_as_is(self) -> None:
        """Without flush context, _auto_flush returns object as-is."""
        from scistudio.core.storage.flush_context import clear

        clear()
        img = Image(shape=(5, 5), ndim=2, dtype="float64")
        result = Block._auto_flush(img)
        assert result is img

    def test_auto_flush_with_context_persists(self, tmp_path: object) -> None:
        """With flush context set, _auto_flush writes data and sets storage_ref.

        ADR-031: uses a storage-backed Image (written to zarr first)
        instead of the former ``_data`` backdoor.
        """
        import numpy as np
        import zarr

        from scistudio.core.storage.flush_context import set_output_dir
        from scistudio.core.storage.ref import StorageReference

        output_dir = str(tmp_path)
        set_output_dir(output_dir)

        # Write data to zarr, then create an Image with storage_ref.
        zarr_path = str(Path(output_dir) / "test.zarr")
        zarr.save(zarr_path, np.ones((3, 3), dtype="float64"))
        ref = StorageReference(backend="zarr", path=zarr_path, metadata={"shape": [3, 3], "dtype": "float64"})
        img = Image(shape=(3, 3), ndim=2, dtype="float64", storage_ref=ref)

        result = Block._auto_flush(img)
        assert result is img
        assert result.storage_ref is not None
        assert result.storage_ref.backend == "zarr"


class TestVariadicPorts:
    """ADR-029 D8: variadic_inputs / variadic_outputs ClassVars and
    config-driven get_effective_*_ports() overrides."""

    def test_static_block_defaults(self) -> None:
        """Non-variadic blocks have both flags False by default."""
        block = _DummyBlock()
        assert type(block).variadic_inputs is False
        assert type(block).variadic_outputs is False

    def test_static_block_effective_ports_unchanged(self) -> None:
        """Static block returns class-level port list unchanged."""
        block = _DummyBlock()
        assert block.get_effective_input_ports() == list(_DummyBlock.input_ports)
        assert block.get_effective_output_ports() == list(_DummyBlock.output_ports)

    def test_variadic_block_with_no_config_falls_back_to_classvars(self) -> None:
        """Variadic block with no config port list falls back to class-level ports."""

        class _VariadicBlock(Block):
            name: ClassVar[str] = "Variadic"
            variadic_inputs: ClassVar[bool] = True
            variadic_outputs: ClassVar[bool] = True
            input_ports: ClassVar[list[InputPort]] = [
                InputPort(name="default_in", accepted_types=[Array]),
            ]
            output_ports: ClassVar[list[OutputPort]] = [
                OutputPort(name="default_out", accepted_types=[Array]),
            ]

            def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
                return {}

        block = _VariadicBlock()
        assert block.get_effective_input_ports() == list(_VariadicBlock.input_ports)
        assert block.get_effective_output_ports() == list(_VariadicBlock.output_ports)

    def test_variadic_block_reads_input_ports_from_config(self) -> None:
        """Variadic block reads input_ports from config when present."""

        class _VariadicBlock(Block):
            name: ClassVar[str] = "VariadicConfigIn"
            variadic_inputs: ClassVar[bool] = True
            variadic_outputs: ClassVar[bool] = False
            input_ports: ClassVar[list[InputPort]] = []
            output_ports: ClassVar[list[OutputPort]] = []

            def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
                return {}

        config = {
            "input_ports": [
                {"name": "img", "types": ["DataObject"]},
                {"name": "mask", "types": ["DataObject"]},
            ]
        }
        block = _VariadicBlock(config=config)
        ports = block.get_effective_input_ports()
        assert len(ports) == 2
        assert ports[0].name == "img"
        assert ports[1].name == "mask"

    def test_variadic_block_reads_output_ports_from_config(self) -> None:
        """Variadic block reads output_ports from config when present."""

        class _VariadicBlock(Block):
            name: ClassVar[str] = "VariadicConfigOut"
            variadic_inputs: ClassVar[bool] = False
            variadic_outputs: ClassVar[bool] = True
            input_ports: ClassVar[list[InputPort]] = []
            output_ports: ClassVar[list[OutputPort]] = []

            def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
                return {}

        config = {
            "output_ports": [
                {"name": "result", "types": ["DataObject"]},
                {"name": "summary", "types": ["DataObject"]},
            ]
        }
        block = _VariadicBlock(config=config)
        ports = block.get_effective_output_ports()
        assert len(ports) == 2
        assert ports[0].name == "result"
        assert ports[1].name == "summary"

    def test_allowed_input_types_default_empty(self) -> None:
        """Block.allowed_input_types defaults to empty list."""
        assert _DummyBlock.allowed_input_types == []
        assert _DummyBlock.allowed_output_types == []

    def test_port_count_limits_default_none(self) -> None:
        """min/max port count limits default to None."""
        assert _DummyBlock.min_input_ports is None
        assert _DummyBlock.max_input_ports is None
        assert _DummyBlock.min_output_ports is None
        assert _DummyBlock.max_output_ports is None


class TestVariadicPortCountLimits:
    """ADR-029 Addendum 1: validate() enforces min/max port count limits."""

    def test_validate_rejects_below_min_input_ports(self) -> None:
        """Validation fails when input port count is below min_input_ports."""
        from scistudio.core.types.base import DataObject

        class _MinInputBlock(Block):
            name: ClassVar[str] = "MinInput"
            variadic_inputs: ClassVar[bool] = True
            min_input_ports: ClassVar[int | None] = 2
            input_ports: ClassVar[list[InputPort]] = []
            output_ports: ClassVar[list[OutputPort]] = []

            def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
                return {}

        # Only 1 port configured, min is 2 — provide the required input value
        block = _MinInputBlock(config={"input_ports": [{"name": "a", "types": ["DataObject"]}]})
        with pytest.raises(ValueError, match="below minimum 2"):
            block.validate({"a": DataObject()})

    def test_validate_rejects_above_max_input_ports(self) -> None:
        """Validation fails when input port count exceeds max_input_ports."""
        from scistudio.core.types.base import DataObject

        class _MaxInputBlock(Block):
            name: ClassVar[str] = "MaxInput"
            variadic_inputs: ClassVar[bool] = True
            max_input_ports: ClassVar[int | None] = 2
            input_ports: ClassVar[list[InputPort]] = []
            output_ports: ClassVar[list[OutputPort]] = []

            def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
                return {}

        # 3 ports configured, max is 2
        block = _MaxInputBlock(
            config={
                "input_ports": [
                    {"name": "a", "types": ["DataObject"]},
                    {"name": "b", "types": ["DataObject"]},
                    {"name": "c", "types": ["DataObject"]},
                ]
            }
        )
        with pytest.raises(ValueError, match="exceeds maximum 2"):
            block.validate({"a": DataObject(), "b": DataObject(), "c": DataObject()})

    def test_validate_accepts_within_input_port_limits(self) -> None:
        """Validation passes when input port count is within min/max range."""
        from scistudio.core.types.base import DataObject

        class _BoundedInputBlock(Block):
            name: ClassVar[str] = "BoundedInput"
            variadic_inputs: ClassVar[bool] = True
            min_input_ports: ClassVar[int | None] = 1
            max_input_ports: ClassVar[int | None] = 3
            input_ports: ClassVar[list[InputPort]] = []
            output_ports: ClassVar[list[OutputPort]] = []

            def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
                return {}

        block = _BoundedInputBlock(
            config={
                "input_ports": [
                    {"name": "a", "types": ["DataObject"]},
                    {"name": "b", "types": ["DataObject"]},
                ]
            }
        )
        assert block.validate({"a": DataObject(), "b": DataObject()}) is True

    def test_validate_rejects_below_min_output_ports(self) -> None:
        """Validation fails when output port count is below min_output_ports."""

        class _MinOutputBlock(Block):
            name: ClassVar[str] = "MinOutput"
            variadic_outputs: ClassVar[bool] = True
            min_output_ports: ClassVar[int | None] = 2
            input_ports: ClassVar[list[InputPort]] = []
            output_ports: ClassVar[list[OutputPort]] = []

            def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
                return {}

        block = _MinOutputBlock(config={"output_ports": [{"name": "a", "types": ["DataObject"]}]})
        with pytest.raises(ValueError, match="below minimum 2"):
            block.validate({})

    def test_validate_rejects_above_max_output_ports(self) -> None:
        """Validation fails when output port count exceeds max_output_ports."""

        class _MaxOutputBlock(Block):
            name: ClassVar[str] = "MaxOutput"
            variadic_outputs: ClassVar[bool] = True
            max_output_ports: ClassVar[int | None] = 1
            input_ports: ClassVar[list[InputPort]] = []
            output_ports: ClassVar[list[OutputPort]] = []

            def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
                return {}

        block = _MaxOutputBlock(
            config={
                "output_ports": [
                    {"name": "a", "types": ["DataObject"]},
                    {"name": "b", "types": ["DataObject"]},
                ]
            }
        )
        with pytest.raises(ValueError, match="exceeds maximum 1"):
            block.validate({})

    def test_validate_no_limits_allows_any_count(self) -> None:
        """Without min/max limits, any port count is valid."""
        from scistudio.core.types.base import DataObject

        class _UnlimitedBlock(Block):
            name: ClassVar[str] = "Unlimited"
            variadic_inputs: ClassVar[bool] = True
            variadic_outputs: ClassVar[bool] = True
            input_ports: ClassVar[list[InputPort]] = []
            output_ports: ClassVar[list[OutputPort]] = []

            def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
                return {}

        inputs = {f"p{i}": DataObject() for i in range(5)}
        block = _UnlimitedBlock(
            config={
                "input_ports": [{"name": f"p{i}", "types": ["DataObject"]} for i in range(5)],
                "output_ports": [{"name": f"o{i}", "types": ["DataObject"]} for i in range(5)],
            }
        )
        assert block.validate(inputs) is True
