"""T-IMG-019 CellposeSegment implementation tests."""

from __future__ import annotations

import builtins
import importlib
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from scistudio_blocks_imaging import get_blocks
from scistudio_blocks_imaging.segmentation.cellpose_segment import CellposeSegment
from scistudio_blocks_imaging.types import Image, Label

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection
from scistudio.core.types.registry import TypeRegistry
from scistudio.core.types.serialization import _reconstruct_one, _serialise_one

_INT32_DTYPE = np.dtype(np.int32)


def _make_image(arr: np.ndarray, axes: list[str], *, source_file: str = "sample.tif") -> Image:
    image = Image(
        axes=axes,
        shape=arr.shape,
        dtype=arr.dtype,
        meta=Image.Meta(source_file=source_file),
    )
    image._data = arr  # type: ignore[attr-defined]
    return image


class _FakeCellposeModel:
    def __init__(
        self,
        *,
        model_type: str | None = None,
        pretrained_model: str | None = None,
        gpu: bool,
        mask_dtype: np.dtype[Any] = _INT32_DTYPE,
        max_label: int = 2,
    ) -> None:
        self.model_type = model_type
        self.pretrained_model = pretrained_model
        self.gpu = gpu
        self.mask_dtype = mask_dtype
        self.max_label = max_label
        self.eval_calls: list[tuple[np.ndarray, dict[str, Any]]] = []

    def eval(self, data: np.ndarray, **kwargs: Any) -> tuple[np.ndarray, None, None, None]:
        arr = np.asarray(data)
        self.eval_calls.append((arr.copy(), dict(kwargs)))
        labels = np.zeros(arr.shape, dtype=self.mask_dtype)
        if arr.size:
            labels.flat[0] = 1
        if arr.size > 1:
            labels.flat[-1] = self.max_label
        return labels, None, None, None


class _FakeModelsFactory:
    def __init__(self, *, mask_dtype: np.dtype[Any] = _INT32_DTYPE, max_label: int = 2) -> None:
        self.mask_dtype = mask_dtype
        self.max_label = max_label
        self.created: list[_FakeCellposeModel] = []

    def build_default(self, *, model_type: str, gpu: bool) -> _FakeCellposeModel:
        model = _FakeCellposeModel(
            model_type=model_type,
            gpu=gpu,
            mask_dtype=self.mask_dtype,
            max_label=self.max_label,
        )
        self.created.append(model)
        return model

    def build_custom(self, *, pretrained_model: str, gpu: bool) -> _FakeCellposeModel:
        model = _FakeCellposeModel(
            pretrained_model=pretrained_model,
            gpu=gpu,
            mask_dtype=self.mask_dtype,
            max_label=self.max_label,
        )
        self.created.append(model)
        return model


def _patch_fake_models(monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> _FakeModelsFactory:
    factory = _FakeModelsFactory(**kwargs)
    models = SimpleNamespace(
        Cellpose=factory.build_default,
        CellposeModel=factory.build_custom,
    )
    monkeypatch.setattr(
        "scistudio_blocks_imaging.segmentation.cellpose_segment._import_cellpose_models",
        lambda: models,
    )
    return factory


def _patch_fake_models_no_cellpose_wrapper(monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> _FakeModelsFactory:
    """Simulate cellpose v3+ where models.Cellpose is absent.

    Only ``CellposeModel`` is exposed on the namespace so ``hasattr(models, 'Cellpose')``
    returns False and the fallback branch in ``setup()`` is exercised.
    """
    factory = _FakeModelsFactory(**kwargs)

    def _build_model_from_type(*, model_type: str, gpu: bool) -> _FakeCellposeModel:
        return factory.build_default(model_type=model_type, gpu=gpu)

    # Intentionally omit 'Cellpose' to exercise the v3+ fallback path.
    models = SimpleNamespace(CellposeModel=_build_model_from_type)
    monkeypatch.setattr(
        "scistudio_blocks_imaging.segmentation.cellpose_segment._import_cellpose_models",
        lambda: models,
    )
    return factory


def test_t_img_019_module_importable() -> None:
    importlib.import_module("scistudio_blocks_imaging.segmentation.cellpose_segment")


def test_t_img_019_class_has_required_classvars() -> None:
    assert hasattr(CellposeSegment, "type_name")
    assert hasattr(CellposeSegment, "name")
    assert hasattr(CellposeSegment, "subcategory")
    assert hasattr(CellposeSegment, "config_schema")


def test_cellpose_class_exists_in_palette() -> None:
    assert CellposeSegment in get_blocks()


def test_cellpose_setup_loads_model_once(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = _patch_fake_models(monkeypatch)
    state = CellposeSegment().setup(BlockConfig(params={"model": "cyto3"}))
    assert len(factory.created) == 1
    assert state is factory.created[0]
    assert state.model_type == "cyto3"


def test_cellpose_process_item_uses_state_model(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = _patch_fake_models(monkeypatch)
    block = CellposeSegment()
    state = block.setup(BlockConfig(params={"model": "cyto2"}))
    image = _make_image(np.arange(2 * 3 * 5 * 5, dtype=np.float32).reshape(2, 3, 5, 5), ["t", "z", "y", "x"])

    label = block.process_item(image, BlockConfig(params={"diameter": 17.5}), state)

    eval_input, eval_kwargs = factory.created[0].eval_calls[0]
    assert eval_input.shape == (5, 5)
    assert eval_kwargs["diameter"] == 17.5
    assert isinstance(label, Label)
    assert label.slots["raster"].shape == (5, 5)


def test_cellpose_teardown_releases_state(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "scistudio_blocks_imaging.segmentation.cellpose_segment._maybe_empty_torch_cuda_cache",
        lambda: calls.append("empty"),
    )

    CellposeSegment().teardown(SimpleNamespace(gpu=True))

    assert calls == ["empty"]


def test_cellpose_collection_input_runs_setup_once(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = _patch_fake_models(monkeypatch)
    teardown_calls: list[Any] = []
    monkeypatch.setattr(
        CellposeSegment,
        "teardown",
        lambda self, state: teardown_calls.append(state),
    )

    block = CellposeSegment()
    images = Collection(
        items=[
            _make_image(np.ones((5, 5), dtype=np.float32), ["y", "x"], source_file="a.tif"),
            _make_image(np.full((5, 5), 2.0, dtype=np.float32), ["y", "x"], source_file="b.tif"),
        ],
        item_type=Image,
    )
    result = block.run({"images": images}, BlockConfig(params={"model": "nuclei"}))

    assert len(factory.created) == 1
    assert len(factory.created[0].eval_calls) == 2
    assert teardown_calls == [factory.created[0]]
    assert result["labels"].item_type is Label
    assert len(result["labels"]) == 2


def test_cellpose_returns_collection_of_label(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_fake_models(monkeypatch)
    block = CellposeSegment()
    images = Collection(items=[_make_image(np.ones((4, 4), dtype=np.float32), ["y", "x"])], item_type=Image)

    result = block.run({"images": images}, BlockConfig(params={}))

    assert isinstance(result["labels"][0], Label)


def test_cellpose_label_raster_dtype_int(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_fake_models(monkeypatch, mask_dtype=np.dtype(np.float32))
    block = CellposeSegment()
    state = block.setup(BlockConfig(params={}))
    label = block.process_item(
        _make_image(np.ones((4, 4), dtype=np.float32), ["y", "x"]), BlockConfig(params={}), state
    )
    raster = label.slots["raster"]

    assert raster is not None
    assert np.issubdtype(np.dtype(raster.dtype), np.integer)


def test_cellpose_use_gpu_false_default(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = _patch_fake_models(monkeypatch)

    CellposeSegment().setup(BlockConfig(params={}))

    assert factory.created[0].gpu is False


def test_cellpose_use_gpu_true_calls_torch_empty_cache_in_teardown(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "scistudio_blocks_imaging.segmentation.cellpose_segment._maybe_empty_torch_cuda_cache",
        lambda: calls.append("empty"),
    )

    CellposeSegment().teardown(SimpleNamespace(gpu=True))

    assert calls == ["empty"]


def test_cellpose_missing_dependency_raises_friendly_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__

    def _missing_cellpose(
        name: str, globals: Any = None, locals: Any = None, fromlist: Any = (), level: int = 0
    ) -> Any:
        if name == "cellpose":
            raise ImportError("missing cellpose")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _missing_cellpose)

    with pytest.raises(ImportError, match=r"requires the \[cellpose\] extra"):
        CellposeSegment().setup(BlockConfig(params={}))


def test_cellpose_diameter_param_passed_to_eval(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = _patch_fake_models(monkeypatch)
    block = CellposeSegment()
    state = block.setup(BlockConfig(params={}))

    block.process_item(
        _make_image(np.ones((6, 6), dtype=np.float32), ["y", "x"]),
        BlockConfig(params={"diameter": 42.0}),
        state,
    )

    assert factory.created[0].eval_calls[0][1]["diameter"] == 42.0


def test_cellpose_flow_threshold_param_passed_to_eval(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = _patch_fake_models(monkeypatch)
    block = CellposeSegment()
    state = block.setup(BlockConfig(params={}))

    block.process_item(
        _make_image(np.ones((6, 6), dtype=np.float32), ["y", "x"]),
        BlockConfig(params={"flow_threshold": 0.7, "cellprob_threshold": -1.5, "channels": [1, 2]}),
        state,
    )

    eval_kwargs = factory.created[0].eval_calls[0][1]
    assert eval_kwargs["flow_threshold"] == 0.7
    assert eval_kwargs["cellprob_threshold"] == -1.5
    assert eval_kwargs["channels"] == [1, 2]


def test_cellpose_meta_n_objects_populated(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_fake_models(monkeypatch, max_label=5)
    block = CellposeSegment()
    state = block.setup(BlockConfig(params={}))

    label = block.process_item(
        _make_image(np.ones((5, 5), dtype=np.float32), ["y", "x"]), BlockConfig(params={}), state
    )

    assert label.meta is not None
    assert label.meta.n_objects == 5


def test_cellpose_custom_model_requires_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_fake_models(monkeypatch)

    with pytest.raises(ValueError, match="custom_model_path"):
        CellposeSegment().setup(BlockConfig(params={"model": "custom"}))


def test_cellpose_round_trip_serialise(monkeypatch: pytest.MonkeyPatch) -> None:
    import scistudio.core.types.serialization as serialization_module

    _patch_fake_models(monkeypatch)
    registry = TypeRegistry()
    registry.scan_builtins()
    registry.register_class(Label)
    previous_registry = serialization_module._registry_instance
    serialization_module._registry_instance = registry
    try:
        block = CellposeSegment()
        state = block.setup(BlockConfig(params={}))
        label = block.process_item(
            _make_image(np.ones((5, 5), dtype=np.float32), ["y", "x"]), BlockConfig(params={}), state
        )
        payload = _serialise_one(label)
        restored = _reconstruct_one(payload)
    finally:
        serialization_module._registry_instance = previous_registry

    assert type(restored) is Label
    assert restored.meta == label.meta


@pytest.mark.requires_cellpose
def test_cellpose_optional_dependency_marker_smoke() -> None:
    pytest.importorskip("cellpose")


# ---------------------------------------------------------------------------
# Fallback path tests (#419): cellpose v3+ API where models.Cellpose is absent
# ---------------------------------------------------------------------------


def test_cellpose_setup_falls_back_to_cellpose_model_when_wrapper_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """setup() must use CellposeModel when models.Cellpose is not available (v3+ API)."""
    factory = _patch_fake_models_no_cellpose_wrapper(monkeypatch)

    state = CellposeSegment().setup(BlockConfig(params={"model": "cyto3"}))

    assert len(factory.created) == 1
    assert state is factory.created[0]
    assert state.model_type == "cyto3"


def test_cellpose_setup_fallback_respects_model_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fallback path passes the configured model_type to CellposeModel."""
    factory = _patch_fake_models_no_cellpose_wrapper(monkeypatch)

    CellposeSegment().setup(BlockConfig(params={"model": "nuclei"}))

    assert factory.created[0].model_type == "nuclei"


def test_cellpose_setup_fallback_respects_gpu_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fallback path forwards use_gpu=True to CellposeModel."""
    factory = _patch_fake_models_no_cellpose_wrapper(monkeypatch)

    CellposeSegment().setup(BlockConfig(params={"model": "cyto2", "use_gpu": True}))

    assert factory.created[0].gpu is True


def test_cellpose_setup_fallback_emits_debug_log(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Fallback path emits a DEBUG log to make the API detection visible."""
    import logging

    _patch_fake_models_no_cellpose_wrapper(monkeypatch)

    with caplog.at_level(logging.DEBUG, logger="scistudio_blocks_imaging.segmentation.cellpose_segment"):
        CellposeSegment().setup(BlockConfig(params={"model": "cyto3"}))

    debug_messages = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("CellposeModel" in msg for msg in debug_messages), (
        f"Expected a DEBUG log mentioning CellposeModel, got: {debug_messages}"
    )


def test_cellpose_setup_uses_wrapper_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """When models.Cellpose is present, setup() must use it (legacy v2 path unchanged)."""
    factory = _patch_fake_models(monkeypatch)

    state = CellposeSegment().setup(BlockConfig(params={"model": "cyto2"}))

    # The wrapper was called, not CellposeModel (build_custom was NOT called)
    assert len(factory.created) == 1
    assert state.model_type == "cyto2"


def test_cellpose_run_works_end_to_end_with_fallback_api(monkeypatch: pytest.MonkeyPatch) -> None:
    """Full run() succeeds when the cellpose v3+ fallback path is active."""
    _patch_fake_models_no_cellpose_wrapper(monkeypatch)
    block = CellposeSegment()
    images = Collection(
        items=[_make_image(np.ones((4, 4), dtype=np.float32), ["y", "x"])],
        item_type=Image,
    )

    result = block.run({"images": images}, BlockConfig(params={"model": "cyto3"}))

    assert "labels" in result
    assert isinstance(result["labels"][0], Label)
