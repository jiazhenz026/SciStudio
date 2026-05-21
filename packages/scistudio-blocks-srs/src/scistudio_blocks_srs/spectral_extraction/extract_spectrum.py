"""ExtractSpectrum — Label + :class:`SRSImage` → wide-format DataFrame.

Extracts per-ROI mean spectra from a Collection of SRSImages paired with
a Collection of Labels. Output is a wide-format DataFrame where each row
is a wavenumber and each column is a named spectrum (image_name + ROI id).
"""

from __future__ import annotations

import os
from typing import Any, ClassVar, cast

import numpy as np
import pyarrow as pa
from scistudio_blocks_imaging.types import Image, Label  # type: ignore[import-not-found]

from scistudio.blocks.base.block import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.array import Array
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio_blocks_srs.types import SRSImage


class ExtractSpectrum(ProcessBlock):
    """Extract per-region mean spectra into a wide-format DataFrame.

    Two input ports: ``image`` (required) and ``labels`` (optional).

    Output columns: ``wavenumber_cm1``, then one column per image-region
    combination named ``{image_name}_ROI{region_id}``.

    When no labels are provided, the entire image is averaged into a
    single column named ``{image_name}_mean``.
    """

    name: ClassVar[str] = "Extract Spectrum"
    type_name: ClassVar[str] = "srs.extract_spectrum"
    description: ClassVar[str] = (
        "Extract per-ROI mean spectra into a wide-format DataFrame (wavenumber_cm1, image_ROI1, image_ROI2, ...)."
    )
    version: ClassVar[str] = "0.2.0"
    subcategory: ClassVar[str] = "spectral"
    algorithm: ClassVar[str] = "extract_spectrum"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(
            name="image",
            accepted_types=[SRSImage, Image],
            description="Image with y/x/lambda axes (SRSImage or Image).",
        ),
        InputPort(
            name="labels",
            accepted_types=[Label],
            description="Optional Label raster; non-zero values define regions.",
            required=False,
        ),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(
            name="spectra",
            accepted_types=[DataFrame],
            description="Wide-format DataFrame: wavenumber_cm1 + one column per ROI.",
        ),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {},
    }

    def run(
        self,
        inputs: dict[str, Any],
        config: BlockConfig,
    ) -> dict[str, Any]:
        """Iterate input Collections, extract per-region mean spectra, build wide DataFrame."""
        images = _coerce_images(inputs.get("image"))
        labels_raw = inputs.get("labels")
        labels_list = _coerce_labels(labels_raw, len(images))

        # All images must share the same wavenumber axis.
        first = images[0]
        if "lambda" not in first.axes:
            raise ValueError("ExtractSpectrum: image must have a 'lambda' axis")
        lambda_axis = first.axes.index("lambda")
        n_lambda = first.shape[lambda_axis] if first.shape else 0
        wavenumbers = _get_wavenumbers(first, n_lambda)

        # Validate that all images have compatible lambda axes.
        for idx, image in enumerate(images):
            if "lambda" not in image.axes:
                raise ValueError(f"ExtractSpectrum: image[{idx}] is missing the 'lambda' axis")
            img_lambda = image.axes.index("lambda")
            img_n = image.shape[img_lambda] if image.shape else 0
            if img_n != n_lambda:
                raise ValueError(
                    f"ExtractSpectrum: image[{idx}] lambda size {img_n} != image[0] lambda size {n_lambda}"
                )

        # Build columns: wavenumber + one per image-region.
        columns: dict[str, pa.Array] = {
            "wavenumber_cm1": pa.array(wavenumbers, type=pa.float64()),
        }
        used_names: set[str] = set()

        for idx, image in enumerate(images):
            label = labels_list[idx]
            img_name = _derive_image_name(image, idx)
            spectra = _extract_spectra(image, label)
            for col_suffix, spectrum in spectra:
                col_name = _unique_column_name(f"{img_name}_{col_suffix}", used_names)
                used_names.add(col_name)
                columns[col_name] = pa.array(spectrum, type=pa.float64())

        table = pa.table(columns)
        result = DataFrame(
            columns=list(table.column_names),
            row_count=table.num_rows,
            framework=first.framework.derive(),
            data=table,
        )
        return {"spectra": result}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce_images(value: Any) -> list[Image]:
    if value is None:
        raise ValueError("ExtractSpectrum: missing required 'image' input")
    if isinstance(value, Image):
        return [value]
    if isinstance(value, Collection):
        items = [cast(Image, item) for item in value]
        if not items:
            raise ValueError("ExtractSpectrum: image collection is empty")
        return items
    raise ValueError(f"ExtractSpectrum: expected Image or Collection, got {type(value).__name__}")


def _coerce_labels(value: Any, expected: int) -> list[Label | None]:
    if value is None:
        return [None] * expected
    if isinstance(value, Label):
        if expected != 1:
            raise ValueError(f"ExtractSpectrum: got single Label but {expected} images; provide a Collection of Labels")
        return [value]
    if isinstance(value, Collection):
        items: list[Label | None] = [cast(Label, item) for item in value]
        if len(items) != expected:
            raise ValueError(
                f"ExtractSpectrum: labels Collection length ({len(items)}) != image Collection length ({expected})"
            )
        return items
    raise ValueError(f"ExtractSpectrum: unexpected labels type {type(value).__name__}")


def _get_image_data(image: Image) -> np.ndarray:
    """Load image data into memory as float64."""
    return np.asarray(image.to_memory(), dtype=np.float64)


def _get_label_data(label: Label) -> np.ndarray:
    """Get 2D integer label raster."""
    raster = label.slots.get("raster")
    if raster is None or not isinstance(raster, Array):
        raise ValueError("ExtractSpectrum: Label input requires a populated 'raster' slot")
    return np.asarray(raster.to_memory(), dtype=np.int32)


def _get_wavenumbers(image: Image, n_lambda: int) -> list[float]:
    """Retrieve wavenumber axis values, falling back to integer indices."""
    if image.meta is not None:
        wn = getattr(image.meta, "wavenumbers_cm1", None)
        if wn is not None:
            return list(wn)
    return [float(i) for i in range(n_lambda)]


def _unique_column_name(candidate: str, used: set[str]) -> str:
    """Return *candidate* if unused, otherwise append _2, _3, ... until unique."""
    if candidate not in used:
        return candidate
    counter = 2
    while f"{candidate}_{counter}" in used:
        counter += 1
    return f"{candidate}_{counter}"


def _derive_image_name(image: Image, index: int) -> str:
    """Derive a short column-friendly name from the image metadata or index."""
    if image.meta is not None and getattr(image.meta, "source_file", None):
        base = os.path.splitext(os.path.basename(image.meta.source_file))[0]
        # Sanitise for use as column name.
        return base.replace(" ", "_").replace("-", "_")
    return f"img{index}"


def _extract_spectra(
    image: Image,
    label: Label | None,
) -> list[tuple[str, list[float]]]:
    """Extract spectra from one image + optional label.

    Returns a list of (column_suffix, spectrum_values) pairs.
    """
    cube = _get_image_data(image)
    axes = image.axes

    if "lambda" not in axes:
        raise ValueError("ExtractSpectrum: image must have a 'lambda' axis")

    lambda_axis = axes.index("lambda")
    n_lambda = cube.shape[lambda_axis]

    # Reshape to (n_lambda, n_pixels) for easy masked averaging
    cube_lf = np.moveaxis(cube, lambda_axis, 0)  # (lambda, y, x)
    spatial_shape = cube_lf.shape[1:]
    cube_2d = cube_lf.reshape(n_lambda, -1)  # (lambda, n_pixels)

    results: list[tuple[str, list[float]]] = []

    if label is not None:
        label_data = _get_label_data(label)
        if label_data.shape != spatial_shape:
            raise ValueError(f"ExtractSpectrum: label shape {label_data.shape} != image spatial shape {spatial_shape}")
        label_flat = label_data.ravel()
        region_ids = np.unique(label_flat)
        region_ids = region_ids[region_ids != 0]  # skip background

        for rid in region_ids:
            pixel_mask = label_flat == rid
            mean_spectrum = cube_2d[:, pixel_mask].mean(axis=1)
            results.append((f"ROI{int(rid)}", mean_spectrum.tolist()))
    else:
        # No ROI: average all pixels
        mean_spectrum = cube_2d.mean(axis=1)
        results.append(("mean", mean_spectrum.tolist()))

    return results


__all__ = ["ExtractSpectrum"]
