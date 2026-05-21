"""Watershed - distance / gradient / marker-based watershed (T-IMG-018)."""

from __future__ import annotations

from typing import Any, ClassVar, cast

import numpy as np

from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.core.types.array import Array
from scieasy.core.types.base import DataObject
from scieasy.core.types.collection import Collection
from scieasy_blocks_imaging.types import Image, Label, Mask

_WATERSHED_METHODS = frozenset({"distance", "gradient", "markers"})


class Watershed(ProcessBlock):
    """Watershed segmentation producing a :class:`Label` raster."""

    type_name: ClassVar[str] = "imaging.watershed"
    name: ClassVar[str] = "Watershed"
    description: ClassVar[str] = "Watershed segmentation (distance / gradient / markers)."
    subcategory: ClassVar[str] = "segmentation"
    algorithm: ClassVar[str] = "watershed"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], required=True),
        InputPort(name="mask", accepted_types=[Mask], required=False),
        InputPort(name="markers", accepted_types=[Label], required=False),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="label", accepted_types=[Label]),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["distance", "gradient", "markers"],
                "default": "distance",
            },
            "min_distance": {"type": "integer", "default": 10},
            "compactness": {"type": "number", "default": 0.0},
        },
    }

    def run(
        self,
        inputs: dict[str, Collection],
        config: BlockConfig,
    ) -> dict[str, Collection]:
        """Run watershed (Tier 2 - multi-input)."""
        images = _coerce_images(inputs.get("image"))
        masks = _expand_optional_masks(inputs.get("mask"), len(images))
        markers = _expand_optional_markers(inputs.get("markers"), len(images))

        labels: list[Label] = []
        for image, mask, marker in zip(images, masks, markers, strict=True):
            labels.append(cast(Label, self._auto_flush(self._segment_one(image, mask, marker, config))))
        return {"label": Collection(items=cast(list[DataObject], labels), item_type=Label)}

    def _segment_one(
        self,
        image: Image,
        mask: Mask | None,
        markers: Label | None,
        config: BlockConfig,
    ) -> Label:
        from skimage.filters import sobel
        from skimage.segmentation import watershed as sk_watershed

        method = str(config.get("method", "distance"))
        min_distance = int(config.get("min_distance", 10))
        compactness = float(config.get("compactness", 0.0))

        if method not in _WATERSHED_METHODS:
            raise ValueError(f"Watershed: unknown method {method!r}; expected one of {sorted(_WATERSHED_METHODS)}")
        if min_distance < 1:
            raise ValueError(f"Watershed: min_distance must be >= 1, got {min_distance}")
        if compactness < 0:
            raise ValueError(f"Watershed: compactness must be >= 0, got {compactness}")
        if method == "markers" and markers is None:
            raise ValueError("Watershed: method='markers' requires a 'markers' input")

        image_arr = np.asarray(image.to_memory(), dtype=np.float64)
        image_t, inverse_axes = _move_spatial_axes_last(image_arr, image.axes, "image")
        mask_t = _transpose_optional_mask(mask, image.axes)
        markers_t = _transpose_optional_markers(markers, image.axes)

        labelled = np.zeros(image_t.shape, dtype=np.int32)
        offset = 0
        extra_shape = image_t.shape[:-2]
        extra_indices = np.ndindex(extra_shape) if extra_shape else [()]
        for extra_idx in extra_indices:
            image_slice = image_t[extra_idx] if extra_shape else image_t
            mask_slice = mask_t[extra_idx] if mask_t is not None and extra_shape else mask_t
            markers_slice = markers_t[extra_idx] if markers_t is not None and extra_shape else markers_t

            if method == "distance":
                working_mask = _resolve_mask(image_slice, mask_slice)
                slice_labels = _distance_watershed(
                    working_mask,
                    min_distance=min_distance,
                    compactness=compactness,
                )
            elif method == "gradient":
                working_mask = _resolve_mask(image_slice, mask_slice)
                elevation = np.asarray(sobel(image_slice), dtype=np.float64)
                slice_labels = _flood_from_distance_seeds(
                    elevation,
                    working_mask,
                    min_distance=min_distance,
                    compactness=compactness,
                )
            else:
                assert markers_slice is not None
                slice_labels = np.asarray(
                    sk_watershed(
                        image_slice,
                        np.asarray(markers_slice, dtype=np.int32),
                        mask=np.asarray(mask_slice, dtype=bool) if mask_slice is not None else None,
                        compactness=compactness,
                    ),
                    dtype=np.int32,
                )

            positive = slice_labels > 0
            if positive.any():
                slice_labels = slice_labels.copy()
                slice_labels[positive] += offset
                offset = int(slice_labels.max())
            if extra_shape:
                labelled[extra_idx] = slice_labels
            else:
                labelled = slice_labels

        labels = np.transpose(labelled, inverse_axes)
        raster = Array(axes=list(image.axes), shape=labels.shape, dtype=labels.dtype)
        raster._data = labels  # type: ignore[attr-defined]
        # ADR-043 / spec FR-009 Mode C: Label output is shape-aligned with
        # the input Image (axes match image.axes), so ``ome`` MUST be
        # carried into the rebuilt ``Label.Meta``.
        return Label(
            slots={"raster": raster},
            framework=image.framework.derive(),
            meta=Label.Meta(
                source_file=getattr(image.meta, "source_file", None),
                n_objects=offset,
                ome=getattr(image.meta, "ome", None),
            ),
            user=dict(image.user),
        )


def _distance_watershed(
    mask: np.ndarray,
    *,
    min_distance: int,
    compactness: float,
) -> np.ndarray:
    from scipy import ndimage as ndi
    from skimage.segmentation import watershed as sk_watershed

    distance = np.asarray(ndi.distance_transform_edt(mask), dtype=np.float64)
    markers = _peak_markers(distance, mask, min_distance)
    return np.asarray(sk_watershed(-distance, markers, mask=mask, compactness=compactness), dtype=np.int32)


def _flood_from_distance_seeds(
    elevation: np.ndarray,
    mask: np.ndarray,
    *,
    min_distance: int,
    compactness: float,
) -> np.ndarray:
    from scipy import ndimage as ndi
    from skimage.segmentation import watershed as sk_watershed

    distance = np.asarray(ndi.distance_transform_edt(mask), dtype=np.float64)
    markers = _peak_markers(distance, mask, min_distance)
    return np.asarray(sk_watershed(elevation, markers, mask=mask, compactness=compactness), dtype=np.int32)


def _peak_markers(distance: np.ndarray, mask: np.ndarray, min_distance: int) -> np.ndarray:
    from skimage.feature import peak_local_max

    markers = np.zeros(distance.shape, dtype=np.int32)
    if not np.any(mask):
        return markers

    local_max = peak_local_max(distance, min_distance=min_distance, labels=mask)
    if local_max.size == 0:
        local_max = np.argwhere(distance == distance.max())[:1]
    for idx, coordinate in enumerate(local_max, start=1):
        markers[int(coordinate[0]), int(coordinate[1])] = idx
    return markers


def _resolve_mask(image_slice: np.ndarray, mask_slice: np.ndarray | None) -> np.ndarray:
    if mask_slice is not None:
        return np.asarray(mask_slice, dtype=bool)
    return np.asarray(image_slice > 0, dtype=bool)


def _move_spatial_axes_last(data: np.ndarray, axes: list[str], name: str) -> tuple[np.ndarray, np.ndarray]:
    if "y" not in axes or "x" not in axes:
        raise ValueError(f"Watershed: {name} axes must include 'y' and 'x'; got {axes}")
    y_index = axes.index("y")
    x_index = axes.index("x")
    perm = [idx for idx, axis in enumerate(axes) if axis not in {"y", "x"}] + [y_index, x_index]
    transposed = np.transpose(data, perm)
    return transposed, np.argsort(np.asarray(perm))


def _transpose_optional_mask(mask: Mask | None, image_axes: list[str]) -> np.ndarray | None:
    if mask is None:
        return None
    if mask.axes != image_axes:
        raise ValueError(f"Watershed: mask axes must match image axes {image_axes}, got {mask.axes}")
    transposed, _inverse = _move_spatial_axes_last(np.asarray(mask.to_memory(), dtype=bool), mask.axes, "mask")
    return transposed


def _transpose_optional_markers(markers: Label | None, image_axes: list[str]) -> np.ndarray | None:
    if markers is None:
        return None
    raster = _label_raster(markers)
    if raster.axes != image_axes:
        raise ValueError(f"Watershed: markers axes must match image axes {image_axes}, got {raster.axes}")
    transposed, _inverse = _move_spatial_axes_last(
        np.asarray(raster.to_memory(), dtype=np.int32), raster.axes, "markers"
    )
    return transposed


def _label_raster(label: Label) -> Array:
    raster = label.slots.get("raster")
    if raster is None or not isinstance(raster, Array):
        raise ValueError("Watershed: markers input requires a populated 'raster' slot")
    return cast(Array, raster)


def _coerce_images(value: Collection | Image | None) -> list[Image]:
    if value is None:
        raise ValueError("Watershed: missing required 'image' input")
    if isinstance(value, Image):
        return [value]
    if not isinstance(value, Collection):
        raise ValueError(f"Watershed: expected Image or Collection[Image], got {type(value).__name__}")

    images: list[Image] = []
    for item in value:
        if not isinstance(item, Image):
            raise ValueError(f"Watershed: image collection must contain Image items, got {type(item).__name__}")
        images.append(item)
    return images


def _expand_optional_masks(value: Collection | Mask | None, target_length: int) -> list[Mask | None]:
    return _expand_optional_inputs(value, target_length, Mask, "mask")


def _expand_optional_markers(value: Collection | Label | None, target_length: int) -> list[Label | None]:
    return _expand_optional_inputs(value, target_length, Label, "markers")


def _expand_optional_inputs(
    value: Collection | Any | None,
    target_length: int,
    expected_type: type,
    port_name: str,
) -> list[Any | None]:
    if value is None:
        return [None] * target_length
    if isinstance(value, expected_type):
        return [value] * target_length
    if not isinstance(value, Collection):
        raise ValueError(
            f"Watershed: expected {expected_type.__name__} or Collection[{expected_type.__name__}] for {port_name!r}, "
            f"got {type(value).__name__}"
        )

    items = list(value)
    for item in items:
        if not isinstance(item, expected_type):
            raise ValueError(
                f"Watershed: {port_name!r} collection must contain {expected_type.__name__} items, "
                f"got {type(item).__name__}"
            )
    if len(items) == 1:
        return items * target_length
    if len(items) != target_length:
        raise ValueError(
            f"Watershed: {port_name!r} collection length must be 1 or match image length {target_length}, "
            f"got {len(items)}"
        )
    return items


__all__ = ["Watershed"]
