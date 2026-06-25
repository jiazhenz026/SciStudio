"""Cellpose-based segmentation using ProcessBlock setup/teardown."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any, ClassVar, cast

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.array import Array
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio_blocks_imaging.types import Image, Label

logger = logging.getLogger(__name__)


class CellposeSegment(ProcessBlock):
    """Flagship segmentation block using cellpose deep learning models."""

    type_name: ClassVar[str] = "imaging.cellpose_segment"
    name: ClassVar[str] = "Cellpose Segmentation"
    description: ClassVar[str] = (
        "Cellpose deep-learning cell segmentation (FLAGSHIP). "
        "Loads the cellpose model once per run via setup()/teardown()."
    )
    subcategory: ClassVar[str] = "segmentation"
    algorithm: ClassVar[str] = "cellpose"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="images", accepted_types=[Image], is_collection=True, required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="labels", accepted_types=[Label], is_collection=True),
        OutputPort(name="masks", accepted_types=[Image], is_collection=True),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "model": {
                "type": "string",
                "enum": ["cyto3", "cyto2", "nuclei", "custom"],
                "default": "cyto3",
            },
            "diameter": {"type": "number", "default": 30.0, "minimum": 0.0},
            "flow_threshold": {
                "type": "number",
                "default": 0.4,
                "minimum": 0.0,
                "maximum": 1.0,
            },
            "cellprob_threshold": {"type": "number", "default": 0.0},
            "use_gpu": {"type": "boolean", "default": False},
            "channels": {"type": "array", "default": [0, 0]},
            "custom_model_path": {"type": "string"},
        },
    }

    def setup(self, config: BlockConfig) -> Any:
        """Load the cellpose model once per run (ADR-027 D7).

        Supports both the legacy cellpose v2 API (``models.Cellpose``) and the
        newer v3+ API where only ``models.CellposeModel`` is available.  When
        ``models.Cellpose`` is absent the block falls back to
        ``CellposeModel(model_type=...)`` which provides an identical
        ``eval()`` interface.
        """
        models = _import_cellpose_models()
        model_name = str(config.get("model", "cyto3"))
        use_gpu = bool(config.get("use_gpu", False))
        if model_name == "custom":
            path = config.get("custom_model_path")
            if not path:
                raise ValueError("model=custom requires custom_model_path")
            return models.CellposeModel(pretrained_model=path, gpu=use_gpu)
        if hasattr(models, "Cellpose"):
            return models.Cellpose(model_type=model_name, gpu=use_gpu)
        # cellpose v3+: Cellpose wrapper removed; CellposeModel accepts model_type directly.
        logger.debug(
            "cellpose.models.Cellpose not found; falling back to CellposeModel(model_type=%r) "
            "(cellpose v3+ API detected)",
            model_name,
        )
        return models.CellposeModel(model_type=model_name, gpu=use_gpu)

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Override Tier 1 run so the output collection carries ``Label`` items
        and a parallel ``masks`` collection of raw integer-label images."""
        images = _coerce_images(inputs.get("images"))
        state = self.setup(config)
        try:
            labels_list: list[Label] = []
            masks_list: list[Image] = []
            for image in images:
                label = self.process_item(image, config, state)
                labels_list.append(cast(Label, self._auto_flush(label)))

                # Extract raster data as standalone Image for masks port.
                # ADR-043 / spec FR-009 Mode C: the mask image is
                # shape-aligned with the source image's spatial axes
                # (y, x), so ``ome`` is carried into the rebuilt
                # ``Image.Meta`` per the propagation contract. Cellpose
                # collapses every non-spatial axis (t, z, c, lambda) to
                # a single center plane via ``_center_spatial_slice``,
                # so the output's OME ``size_t``/``size_z``/``size_c``
                # are collapsed to 1 to match the 2D label raster
                # (Codex P1 reconciliation 2026-05-20).
                raster_data = label.slots["raster"]._data  # type: ignore[attr-defined]
                mask_img = Image(
                    axes=["y", "x"],
                    shape=tuple(raster_data.shape),
                    dtype=raster_data.dtype,
                    framework=image.framework.derive(),
                    meta=Image.Meta(
                        source_file=getattr(image.meta, "source_file", None),
                        ome=_collapse_non_spatial_ome_to_2d(getattr(image.meta, "ome", None)),
                    ),
                    user=dict(image.user),
                )
                mask_img._data = raster_data  # type: ignore[attr-defined]
                masks_list.append(cast(Image, self._auto_flush(mask_img)))

            return {
                "labels": Collection(items=cast(list[DataObject], labels_list), item_type=Label),
                "masks": Collection(items=cast(list[DataObject], masks_list), item_type=Image),
            }
        finally:
            self.teardown(state)

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Label:
        """Segment one image using the model loaded in :meth:`setup`."""
        if state is None:
            raise RuntimeError("CellposeSegment.process_item called without state")

        diameter = float(config.get("diameter", 30.0))
        flow_threshold = float(config.get("flow_threshold", 0.4))
        cellprob_threshold = float(config.get("cellprob_threshold", 0.0))
        channels = _coerce_channels(config.get("channels", [0, 0]))

        data_2d = _center_spatial_slice(_image_data(item))
        masks, *_ = state.eval(
            data_2d,
            diameter=diameter,
            channels=channels,
            flow_threshold=flow_threshold,
            cellprob_threshold=cellprob_threshold,
        )
        labels = np.asarray(masks)
        if not np.issubdtype(labels.dtype, np.integer):
            labels = labels.astype(np.int32)

        raster = Array(axes=["y", "x"], shape=labels.shape, dtype=labels.dtype)
        raster._data = labels  # type: ignore[attr-defined]
        # ADR-043 / spec FR-009 Mode C: Label output preserves the spatial
        # coordinate system of the source Image (y, x raster), so ``ome``
        # is carried into the rebuilt ``Label.Meta``. Cellpose collapses
        # every non-spatial axis (t, z, c, lambda) to a single center
        # plane via ``_center_spatial_slice``, so OME ``size_t`` /
        # ``size_z`` / ``size_c`` are collapsed to 1 to match the 2D
        # label raster (Codex P1 reconciliation 2026-05-20).
        return Label(
            slots={"raster": raster},
            framework=item.framework.derive(),
            meta=Label.Meta(
                source_file=getattr(item.meta, "source_file", None),
                n_objects=int(labels.max()) if labels.size else 0,
                ome=_collapse_non_spatial_ome_to_2d(getattr(item.meta, "ome", None)),
            ),
            user=dict(item.user),
        )

    def teardown(self, state: Any) -> None:
        """Release GPU memory when applicable (Q-IMG-2)."""
        if state is None:
            return
        if bool(getattr(state, "gpu", False)):
            _maybe_empty_torch_cuda_cache()


def _import_cellpose_models() -> Any:
    try:
        from cellpose import models
    except ImportError as exc:
        raise ImportError(
            "CellposeSegment requires the 'cellpose' package, which is not installed. "
            "Open the Python terminal in SciStudio and run:\n"
            "    pip install cellpose\n"
            "It installs into the SciStudio plugin environment this block runs in."
        ) from exc
    return models


def _maybe_empty_torch_cuda_cache() -> None:
    try:
        import torch
    except ImportError:
        return

    if torch.cuda.is_available():
        logger.debug("Clearing torch CUDA cache after CellposeSegment teardown")
        torch.cuda.empty_cache()


def _coerce_images(value: Collection | Image | None) -> list[Image]:
    if value is None:
        raise ValueError("CellposeSegment: missing required 'images' input")
    if isinstance(value, Image):
        return [value]
    if not isinstance(value, Collection):
        raise ValueError(f"CellposeSegment: expected Image or Collection[Image], got {type(value).__name__}")

    images: list[Image] = []
    for item in value:
        if not isinstance(item, Image):
            raise ValueError(f"CellposeSegment: images must contain Image items, got {type(item).__name__}")
        images.append(item)
    if not images:
        raise ValueError("CellposeSegment: images collection is empty")
    return images


def _coerce_channels(value: object) -> list[int]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 2:
        raise ValueError("CellposeSegment: channels must be a two-element sequence")

    channels: list[int] = []
    for entry in value:
        if isinstance(entry, bool) or not isinstance(entry, (int, np.integer)):
            raise ValueError("CellposeSegment: channels entries must be integers")
        channels.append(int(entry))
    return channels


def _image_data(image: Image) -> np.ndarray:
    if image.storage_ref is None and hasattr(image, "_data") and getattr(image, "_data", None) is not None:
        return np.asarray(image._data)  # type: ignore[attr-defined]
    return np.asarray(image.to_memory())


def _center_spatial_slice(data: np.ndarray) -> np.ndarray:
    if data.ndim <= 2:
        return data
    slicer = (*tuple(size // 2 for size in data.shape[:-2]), slice(None), slice(None))
    return np.asarray(data[slicer])


def _collapse_non_spatial_ome_to_2d(ome: Any) -> Any:
    """Return a deep-copied OME with ``size_t`` / ``size_z`` / ``size_c`` set to 1.

    CellposeSegment reduces any non-2D input to a single center
    ``(y, x)`` plane via :func:`_center_spatial_slice`. The output
    Label / mask Image is 2D, so the propagated OME must reflect that
    by collapsing every non-spatial axis to size 1. In-plane sampling
    (``physical_size_x`` / ``physical_size_y`` / ``size_x`` /
    ``size_y``) is preserved verbatim.

    Reconciles Codex P1 review on PR #1302 (2026-05-20): "for inputs
    with t/z/c dimensions greater than 1, the output label is 2D while
    OME still advertises the original higher-dimensional sizes".
    """
    if ome is None:
        return None
    new_ome = ome.model_copy(deep=True)
    if not new_ome.images:
        return new_ome
    pixels = new_ome.images[0].pixels
    for attr in ("size_t", "size_z", "size_c"):
        if hasattr(pixels, attr):
            setattr(pixels, attr, 1)
    return new_ome


__all__ = ["CellposeSegment"]
