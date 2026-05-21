"""Rendering blocks for the imaging plugin."""

from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, ClassVar, cast

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.collection import Collection
from scistudio_blocks_imaging.types import Image, Label, Mask

_SPATIAL_AXES = ("y", "x")


class RenderPseudoColor(ProcessBlock):
    """Map a single-channel :class:`Image` through a colour LUT to a PNG :class:`Artifact`."""

    type_name: ClassVar[str] = "imaging.render_pseudo_color"
    name: ClassVar[str] = "Render Pseudo-color"
    description: ClassVar[str] = "Map a single-channel image through a colour LUT to a PNG artifact."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "visualization"
    algorithm: ClassVar[str] = "render_pseudo_color"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], description="Single-channel image."),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="artifact", accepted_types=[Artifact], description="Rendered PNG artifact."),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "lut": {"type": "string", "default": "viridis"},
            "vmin": {"type": ["number", "null"], "default": None},
            "vmax": {"type": ["number", "null"], "default": None},
        },
    }

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Artifact:
        plt = _matplotlib_pyplot()
        lut = str(config.get("lut", "viridis"))
        _validate_lut(lut)
        plane = _single_plane(item)
        path = _temp_path(".png")
        plt.imsave(path, plane, cmap=lut, vmin=config.get("vmin"), vmax=config.get("vmax"))
        return _artifact(path, mime_type="image/png", description="Pseudo-colored image", source=item)


class RenderOverlay(ProcessBlock):
    """Overlay :class:`Label` or :class:`Mask` outlines on an intensity :class:`Image`."""

    type_name: ClassVar[str] = "imaging.render_overlay"
    name: ClassVar[str] = "Render Overlay"
    description: ClassVar[str] = "Overlay Label / Mask outlines on an intensity image."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "visualization"
    algorithm: ClassVar[str] = "render_overlay"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], description="Background intensity image."),
        InputPort(name="overlay", accepted_types=[Label, Mask], description="Label or Mask to overlay."),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="artifact", accepted_types=[Artifact], description="Rendered artifact."),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "alpha": {"type": "number", "default": 0.5, "minimum": 0.0, "maximum": 1.0},
            "outline_only": {"type": "boolean", "default": True},
        },
    }

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Artifact:
        raise ValueError("RenderOverlay requires both 'image' and 'overlay' inputs via run()")

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        image_input = inputs["image"]
        overlay_input = inputs["overlay"]

        if isinstance(image_input, Collection) or isinstance(overlay_input, Collection):
            images = _require_collection(image_input, "image")
            overlays = _require_overlay_collection(overlay_input, "overlay")
            results = [
                _render_overlay(image, overlay, config)
                for image, overlay in _broadcast_pairs(images, overlays, "RenderOverlay")
            ]
            return {"artifact": Collection(items=cast(list[Any], results), item_type=Artifact)}

        return {"artifact": _render_overlay(cast(Image, image_input), _coerce_overlay(overlay_input), config)}


class RenderMontage(ProcessBlock):
    """Tile multiple frames / channels into a single montage :class:`Artifact`."""

    type_name: ClassVar[str] = "imaging.render_montage"
    name: ClassVar[str] = "Render Montage"
    description: ClassVar[str] = "Tile multiple frames / channels into a single montage image."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "visualization"
    algorithm: ClassVar[str] = "render_montage"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], description="Multi-frame image."),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="artifact", accepted_types=[Artifact], description="Montage PNG."),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "axis": {"type": "string", "default": "t"},
            "ncols": {"type": ["integer", "null"], "default": None, "minimum": 1},
        },
    }

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Artifact:
        tiles = _tiles_from_image(item, axis=str(config.get("axis", "t")))
        montage = _compose_montage(tiles, ncols=_positive_int_or_none(config.get("ncols")))
        plt = _matplotlib_pyplot()
        path = _temp_path(".png")
        plt.imsave(path, montage, cmap="gray")
        return _artifact(path, mime_type="image/png", description="Image montage", source=item)

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        image_input = inputs["image"]
        if isinstance(image_input, Collection):
            tiles = [_single_plane(item) for item in _require_collection(image_input, "image")]
            montage = _compose_montage(tiles, ncols=_positive_int_or_none(config.get("ncols")))
            plt = _matplotlib_pyplot()
            path = _temp_path(".png")
            plt.imsave(path, montage, cmap="gray")
            first = image_input[0] if len(image_input) else None
            return {
                "artifact": _artifact(
                    path,
                    mime_type="image/png",
                    description="Collection montage",
                    source=cast(Image | None, first),
                )
            }
        return super().run(inputs, config)


class RenderMovie(ProcessBlock):
    """Encode a time-series :class:`Image` as an MP4 :class:`Artifact`."""

    type_name: ClassVar[str] = "imaging.render_movie"
    name: ClassVar[str] = "Render Movie"
    description: ClassVar[str] = "Encode a time-series image as an MP4 movie artifact."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "visualization"
    algorithm: ClassVar[str] = "render_movie"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], description="Time-series image."),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="artifact", accepted_types=[Artifact], description="MP4 artifact."),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "fps": {"type": "integer", "default": 10, "minimum": 1},
            "codec": {"type": "string", "default": "libx264"},
        },
    }

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Artifact:
        import imageio.v2 as imageio

        fps = int(config.get("fps", 10))
        if fps < 1:
            raise ValueError("RenderMovie: fps must be >= 1")

        frames = [_to_rgb_uint8(frame) for frame in _frames_from_image(item, axis="t")]
        path = _temp_path(".mp4")
        imageio.mimwrite(path, cast(Any, frames), fps=fps, codec=str(config.get("codec", "libx264")))
        return _artifact(path, mime_type="video/mp4", description="Rendered movie", source=item)


class RenderHistogram(ProcessBlock):
    """Render a pixel intensity histogram as a PNG / SVG :class:`Artifact`."""

    type_name: ClassVar[str] = "imaging.render_histogram"
    name: ClassVar[str] = "Render Histogram"
    description: ClassVar[str] = "Render a pixel intensity histogram as a PNG / SVG artifact."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "visualization"
    algorithm: ClassVar[str] = "render_histogram"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], description="Input image."),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="artifact", accepted_types=[Artifact], description="Histogram artifact."),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "bins": {"type": "integer", "default": 256, "minimum": 2},
            "format": {"type": "string", "enum": ["png", "svg"], "default": "png"},
        },
    }

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Artifact:
        plt = _matplotlib_pyplot()
        bins = int(config.get("bins", 256))
        if bins < 2:
            raise ValueError("RenderHistogram: bins must be >= 2")

        extension = str(config.get("format", "png"))
        path = _temp_path(f".{extension}")
        fig, ax = plt.subplots()
        ax.hist(_image_data(item).ravel(), bins=bins)
        ax.set_xlabel("Intensity")
        ax.set_ylabel("Count")
        fig.savefig(path, format=extension, dpi=150, bbox_inches="tight")
        plt.close(fig)
        mime_type = "image/svg+xml" if extension == "svg" else "image/png"
        return _artifact(path, mime_type=mime_type, description="Histogram plot", source=item)


def _render_overlay(image: Image, overlay: Label | Mask, config: BlockConfig) -> Artifact:
    plt = _matplotlib_pyplot()
    alpha = float(config.get("alpha", 0.5))
    if not 0.0 <= alpha <= 1.0:
        raise ValueError("RenderOverlay: alpha must be between 0.0 and 1.0")

    outline_only = bool(config.get("outline_only", True))
    image_plane = _single_plane(image)
    overlay_plane = _overlay_plane(overlay)
    if overlay_plane.shape != image_plane.shape:
        raise ValueError(
            f"RenderOverlay: overlay shape must match image plane shape ({overlay_plane.shape} vs {image_plane.shape})"
        )

    from skimage.segmentation import find_boundaries

    mask = find_boundaries(overlay_plane) if outline_only else overlay_plane > 0
    rgb = np.repeat(_normalize_plane(image_plane)[..., None], 3, axis=2)
    rgb[mask] = (1.0 - alpha) * rgb[mask] + alpha * np.array([1.0, 0.0, 0.0], dtype=np.float64)

    path = _temp_path(".png")
    plt.imsave(path, np.clip(rgb, 0.0, 1.0))
    return _artifact(path, mime_type="image/png", description="Overlay rendering", source=image)


def _artifact(path: Path, *, mime_type: str, description: str, source: Image | None) -> Artifact:
    framework = source.framework.derive() if source is not None else None
    user = dict(source.user) if source is not None else {}
    return Artifact(file_path=path, mime_type=mime_type, description=description, framework=framework, user=user)


def _matplotlib_pyplot() -> Any:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _validate_lut(lut: str) -> None:
    import matplotlib

    try:
        matplotlib.colormaps[lut]
    except KeyError as exc:
        raise ValueError(f"RenderPseudoColor: unknown LUT {lut!r}") from exc


def _tiles_from_image(image: Image, *, axis: str) -> list[np.ndarray]:
    data = _image_data(image)
    if axis not in image.axes:
        raise ValueError(f"RenderMontage: axis {axis!r} not in image axes {image.axes}")

    axis_index = image.axes.index(axis)
    tiles: list[np.ndarray] = []
    for index in range(data.shape[axis_index]):
        slicer: list[slice | int] = [slice(None)] * data.ndim
        slicer[axis_index] = index
        tiles.append(_plane_from_array(np.asarray(data[tuple(slicer)]), [name for name in image.axes if name != axis]))
    return tiles


def _frames_from_image(image: Image, *, axis: str) -> list[np.ndarray]:
    data = _image_data(image)
    if axis not in image.axes:
        raise ValueError(f"RenderMovie: axis {axis!r} not in image axes {image.axes}")

    axis_index = image.axes.index(axis)
    frames: list[np.ndarray] = []
    for index in range(data.shape[axis_index]):
        slicer: list[slice | int] = [slice(None)] * data.ndim
        slicer[axis_index] = index
        frames.append(_plane_from_array(np.asarray(data[tuple(slicer)]), [name for name in image.axes if name != axis]))
    return frames


def _compose_montage(tiles: list[np.ndarray], *, ncols: int | None) -> np.ndarray:
    if not tiles:
        raise ValueError("RenderMontage: at least one tile is required")

    normalized_tiles = [_normalize_plane(tile) for tile in tiles]
    height = max(tile.shape[0] for tile in normalized_tiles)
    width = max(tile.shape[1] for tile in normalized_tiles)
    columns = ncols or int(np.ceil(np.sqrt(len(normalized_tiles))))
    rows = int(np.ceil(len(normalized_tiles) / columns))
    montage = np.zeros((rows * height, columns * width), dtype=np.float64)

    for index, tile in enumerate(normalized_tiles):
        row = index // columns
        col = index % columns
        y0 = row * height
        x0 = col * width
        montage[y0 : y0 + tile.shape[0], x0 : x0 + tile.shape[1]] = tile
    return montage


def _single_plane(image: Image) -> np.ndarray:
    return _plane_from_array(_image_data(image), image.axes)


def _plane_from_array(data: np.ndarray, axes: list[str]) -> np.ndarray:
    if all(axis in axes for axis in _SPATIAL_AXES):
        slicer: list[slice | int] = []
        for axis_name, axis_size in zip(axes, data.shape, strict=True):
            if axis_name in _SPATIAL_AXES:
                slicer.append(slice(None))
            elif axis_name in {"c", "lambda"} and axis_size > 1:
                raise ValueError(
                    f"Visualization blocks require a single channel/spectrum per rendered plane, got axis {axis_name!r}"
                )
            else:
                slicer.append(0)
        plane = np.asarray(data[tuple(slicer)])
    elif data.ndim == 2:
        plane = np.asarray(data)
    else:
        raise ValueError(f"Visualization blocks require a spatial 2D plane, got axes {axes} and shape {data.shape}")

    if plane.ndim != 2:
        raise ValueError(f"Visualization blocks require a 2D plane after slicing, got shape {plane.shape}")
    return plane.astype(np.float64, copy=False)


def _overlay_plane(overlay: Label | Mask) -> np.ndarray:
    if isinstance(overlay, Mask):
        return _plane_from_array(_image_data(overlay).astype(np.uint8, copy=False), overlay.axes)

    raster = overlay.slots.get("raster")
    if raster is None or not isinstance(raster, Array):
        raise ValueError("RenderOverlay: Label input requires a populated 'raster' slot")
    return _plane_from_array(_array_data(raster), list(raster.axes))


def _normalize_plane(plane: np.ndarray) -> np.ndarray:
    arr = np.asarray(plane, dtype=np.float64)
    min_value = float(np.min(arr))
    max_value = float(np.max(arr))
    if np.isclose(min_value, max_value):
        return np.zeros_like(arr, dtype=np.float64)
    return (arr - min_value) / (max_value - min_value)


def _to_rgb_uint8(plane: np.ndarray) -> np.ndarray:
    normalized = _normalize_plane(plane)
    rgb = np.repeat(normalized[..., None], 3, axis=2)
    return np.asarray(np.clip(rgb * 255.0, 0.0, 255.0), dtype=np.uint8)


def _positive_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("RenderMontage: ncols must be a positive integer")
    return int(value)


def _image_data(image: Image) -> np.ndarray:
    if image.storage_ref is None and hasattr(image, "_data") and getattr(image, "_data", None) is not None:
        return np.asarray(image._data)  # type: ignore[attr-defined]
    return np.asarray(image.to_memory())


def _array_data(array: Array) -> np.ndarray:
    if array.storage_ref is None and hasattr(array, "_data") and getattr(array, "_data", None) is not None:
        return np.asarray(array._data)  # type: ignore[attr-defined]
    return np.asarray(array.to_memory())


def _temp_path(suffix: str) -> Path:
    with NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        return Path(handle.name)


def _require_collection(raw: Any, port_name: str) -> list[Image]:
    if not isinstance(raw, Collection):
        raise ValueError(f"{port_name!r} must be a Collection when any visualization input is a Collection")
    items: list[Image] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Image):
            raise ValueError(f"{port_name!r} item[{index}] must be Image, got {type(item).__name__}")
        items.append(item)
    return items


def _coerce_overlay(raw: Any) -> Label | Mask:
    if not isinstance(raw, (Label, Mask)):
        raise ValueError(f"RenderOverlay: overlay must be Label or Mask, got {type(raw).__name__}")
    return raw


def _require_overlay_collection(raw: Any, port_name: str) -> list[Label | Mask]:
    if not isinstance(raw, Collection):
        raise ValueError(f"{port_name!r} must be a Collection when any visualization input is a Collection")
    items: list[Label | Mask] = []
    for index, item in enumerate(raw):
        if not isinstance(item, (Label, Mask)):
            raise ValueError(f"{port_name!r} item[{index}] must be Label or Mask, got {type(item).__name__}")
        items.append(item)
    return items


def _broadcast_pairs(
    images: list[Image],
    overlays: list[Label | Mask],
    block_name: str,
) -> list[tuple[Image, Label | Mask]]:
    if len(images) == len(overlays):
        return list(zip(images, overlays, strict=True))
    if len(images) == 1:
        return [(images[0], overlay) for overlay in overlays]
    if len(overlays) == 1:
        return [(image, overlays[0]) for image in images]
    raise ValueError(
        f"{block_name}: Collection inputs must have the same length or one side must have length 1 "
        f"(got {len(images)} vs {len(overlays)})"
    )


__all__ = [
    "RenderHistogram",
    "RenderMontage",
    "RenderMovie",
    "RenderOverlay",
    "RenderPseudoColor",
]
