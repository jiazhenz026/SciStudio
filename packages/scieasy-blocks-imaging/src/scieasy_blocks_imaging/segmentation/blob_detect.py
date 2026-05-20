"""BlobDetect - LoG / DoG / DoH blob detection (T-IMG-020)."""

from __future__ import annotations

from typing import Any, ClassVar, cast

import numpy as np

from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.core.types.array import Array
from scieasy.core.types.base import DataObject
from scieasy.core.types.collection import Collection
from scieasy_blocks_imaging.types import Image, Label

_BLOB_METHODS = frozenset({"LoG", "DoG", "DoH"})


class BlobDetect(ProcessBlock):
    """Blob detection producing a :class:`Label` raster of disks."""

    type_name: ClassVar[str] = "imaging.blob_detect"
    name: ClassVar[str] = "Blob Detect"
    description: ClassVar[str] = "Blob detection via Laplacian-of-Gaussian / DoG / DoH."
    subcategory: ClassVar[str] = "segmentation"
    algorithm: ClassVar[str] = "blob_detect"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="label", accepted_types=[Label]),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["LoG", "DoG", "DoH"],
                "default": "LoG",
            },
            "min_sigma": {"type": "number", "default": 1.0},
            "max_sigma": {"type": "number", "default": 30.0},
            "num_sigma": {"type": "integer", "default": 10},
            "threshold": {"type": "number", "default": 0.1},
        },
        "required": ["method"],
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Override Tier 1 run so the output collection carries ``Label`` items."""
        images = _coerce_images(inputs.get("image"))
        labels = [cast(Label, self._auto_flush(self.process_item(image, config))) for image in images]
        return {"label": Collection(items=cast(list[DataObject], labels), item_type=Label)}

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Label:
        """Detect blobs and return as a :class:`Label`."""
        method = str(config.get("method", "LoG"))
        min_sigma = float(config.get("min_sigma", 1.0))
        max_sigma = float(config.get("max_sigma", 30.0))
        num_sigma = int(config.get("num_sigma", 10))
        threshold = float(config.get("threshold", 0.1))

        if method not in _BLOB_METHODS:
            raise ValueError(f"BlobDetect: unknown method {method!r}; expected one of {sorted(_BLOB_METHODS)}")
        if min_sigma <= 0 or max_sigma <= 0:
            raise ValueError("BlobDetect: min_sigma and max_sigma must be > 0")
        if max_sigma < min_sigma:
            raise ValueError("BlobDetect: max_sigma must be >= min_sigma")
        if num_sigma < 1:
            raise ValueError("BlobDetect: num_sigma must be >= 1")
        if threshold < 0:
            raise ValueError("BlobDetect: threshold must be >= 0")

        detector = _resolve_blob_detector(method)
        data = np.asarray(item.to_memory(), dtype=np.float64)
        transposed, inverse_axes = _move_spatial_axes_last(data, item.axes)
        labelled = np.zeros(transposed.shape, dtype=np.int32)

        next_label = 1
        extra_shape = transposed.shape[:-2]
        extra_indices = np.ndindex(extra_shape) if extra_shape else [()]
        for extra_idx in extra_indices:
            slice_2d = transposed[extra_idx] if extra_shape else transposed
            slice_labels = np.zeros(slice_2d.shape, dtype=np.int32)
            blobs = np.asarray(_run_detector(detector, method, slice_2d, min_sigma, max_sigma, num_sigma, threshold))
            for blob in blobs:
                y = round(float(blob[0]))
                x = round(float(blob[1]))
                radius = max(1, int(np.ceil(float(blob[-1]) * np.sqrt(2.0))))
                rr, cc = _disk_indices(y, x, radius, slice_2d.shape)
                slice_labels[rr, cc] = next_label
                next_label += 1
            if extra_shape:
                labelled[extra_idx] = slice_labels
            else:
                labelled = slice_labels

        labels = np.transpose(labelled, inverse_axes)
        raster = Array(axes=list(item.axes), shape=labels.shape, dtype=labels.dtype)
        raster._data = labels  # type: ignore[attr-defined]
        # ADR-043 / spec FR-009 Mode C: Label output preserves the spatial
        # coordinate system of the source Image (axes match item.axes),
        # so ``ome`` MUST be carried into the rebuilt ``Label.Meta``.
        return Label(
            slots={"raster": raster},
            framework=item.framework.derive(),
            meta=Label.Meta(
                source_file=getattr(item.meta, "source_file", None),
                n_objects=next_label - 1,
                ome=getattr(item.meta, "ome", None),
            ),
            user=dict(item.user),
        )


def _resolve_blob_detector(method: str) -> Any:
    from skimage.feature import blob_dog, blob_doh, blob_log

    if method == "LoG":
        return blob_log
    if method == "DoG":
        return blob_dog
    if method == "DoH":
        return blob_doh
    raise ValueError(f"BlobDetect: unknown method {method!r}")  # pragma: no cover


def _run_detector(
    detector: Any,
    method: str,
    slice_2d: np.ndarray,
    min_sigma: float,
    max_sigma: float,
    num_sigma: int,
    threshold: float,
) -> Any:
    kwargs: dict[str, Any] = {
        "min_sigma": min_sigma,
        "max_sigma": max_sigma,
        "threshold": threshold,
    }
    if method != "DoG":
        kwargs["num_sigma"] = num_sigma
    return detector(slice_2d, **kwargs)


def _move_spatial_axes_last(data: np.ndarray, axes: list[str]) -> tuple[np.ndarray, np.ndarray]:
    if "y" not in axes or "x" not in axes:
        raise ValueError(f"BlobDetect: image axes must include 'y' and 'x'; got {axes}")
    y_index = axes.index("y")
    x_index = axes.index("x")
    perm = [idx for idx, axis in enumerate(axes) if axis not in {"y", "x"}] + [y_index, x_index]
    transposed = np.transpose(data, perm)
    inverse = np.argsort(np.asarray(perm))
    return transposed, cast(np.ndarray, inverse)


def _disk_indices(center_y: int, center_x: int, radius: int, shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    from skimage.draw import disk

    rr, cc = disk((center_y, center_x), radius, shape=shape)
    return cast(np.ndarray, rr), cast(np.ndarray, cc)


def _coerce_images(value: Collection | Image | None) -> list[Image]:
    if value is None:
        raise ValueError("BlobDetect: missing required 'image' input")
    if isinstance(value, Image):
        return [value]
    if not isinstance(value, Collection):
        raise ValueError(f"BlobDetect: expected Image or Collection[Image], got {type(value).__name__}")

    images: list[Image] = []
    for item in value:
        if not isinstance(item, Image):
            raise ValueError(f"BlobDetect: image collection must contain Image items, got {type(item).__name__}")
        images.append(item)
    return images


__all__ = ["BlobDetect"]
