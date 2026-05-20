"""SRSPCA — Principal Component Analysis along the spectral axis.

Two outputs: per-PC ``Collection[Image]`` score maps + ``DataFrame`` of
loadings indexed by ``pc_id``. Overrides :meth:`run` directly.

See ``docs/specs/phase11-srs-block-spec.md`` §9 T-SRS-008.
"""

from __future__ import annotations

from typing import Any, ClassVar, cast

import numpy as np
import pyarrow as pa
from scieasy_blocks_imaging.types import Image  # type: ignore[import-not-found]

from scieasy.blocks.base.block import BlockConfig
from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.core.types.base import DataObject
from scieasy.core.types.collection import Collection
from scieasy.core.types.dataframe import DataFrame
from scieasy.utils.constraints import has_axes
from scieasy_blocks_srs.types import SRSImage


class SRSPCA(ProcessBlock):
    """PCA on per-pixel spectra of an :class:`SRSImage`."""

    name: ClassVar[str] = "SRS PCA"
    type_name: ClassVar[str] = "srs.pca"
    description: ClassVar[str] = "Principal Component Analysis on per-pixel spectra."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "component_analysis"
    algorithm: ClassVar[str] = "pca"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(
            name="image",
            accepted_types=[SRSImage],
            description="SRSImage with y/x/lambda axes.",
            constraint=has_axes("y", "x", "lambda"),
            constraint_description="image must carry y/x/lambda axes",
        ),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(
            name="pc_maps",
            accepted_types=[Collection],
            description="Collection[Image] of per-PC 2D score maps.",
        ),
        OutputPort(
            name="loadings",
            accepted_types=[DataFrame],
            description="Loadings DataFrame with `pc_id` index and wavenumber columns.",
        ),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "n_components": {"type": "integer", "default": 5, "minimum": 1},
            "scale": {"type": "boolean", "default": True},
        },
    }

    def run(
        self,
        inputs: dict[str, Any],
        config: BlockConfig,
    ) -> dict[str, Any]:
        """Reshape, optionally scale, fit PCA, emit score maps + loadings."""
        from sklearn.decomposition import PCA
        from sklearn.preprocessing import StandardScaler

        item = _single_srs_image(inputs.get("image"), "SRSPCA")
        n_components = int(config.get("n_components", 5))
        scale = bool(config.get("scale", True))

        lambda_pos = item.axes.index("lambda")
        cube = np.asarray(item.to_memory(), dtype=np.float64)
        moved = np.moveaxis(cube, lambda_pos, -1)
        spatial_shape = moved.shape[:-1]
        n_w = moved.shape[-1]
        if n_components > n_w:
            raise ValueError(f"SRSPCA: n_components={n_components} exceeds n_wavenumbers={n_w}")
        flat = moved.reshape(-1, n_w)

        if scale:
            flat = StandardScaler().fit_transform(flat)

        pca = PCA(n_components=n_components, random_state=42)
        scores = pca.fit_transform(flat)  # (n_pixels, n_components)
        loadings = np.asarray(pca.components_, dtype=np.float64)  # (n_components, n_w)

        spatial_axes = [ax for ax in item.axes if ax != "lambda"]
        maps = _scores_to_image_collection(scores, spatial_shape, spatial_axes, item.framework.derive())

        wavenumbers = _get_wavenumbers(item, n_w)
        loadings_df = _loadings_to_dataframe(loadings, wavenumbers, "pc_id", item.framework.derive())
        return {"pc_maps": maps, "loadings": loadings_df}


def _single_srs_image(value: Any, block_name: str) -> SRSImage:
    if value is None:
        raise ValueError(f"{block_name}: missing required 'image' input")
    if isinstance(value, SRSImage):
        return value
    if isinstance(value, Collection):
        items = list(value)
        if not items:
            raise ValueError(f"{block_name}: image collection is empty")
        if len(items) > 1:
            raise ValueError(f"{block_name}: multi-item collections are not supported; got {len(items)}")
        first = items[0]
        if not isinstance(first, SRSImage):
            raise ValueError(f"{block_name}: collection must contain SRSImage items, got {type(first).__name__}")
        return first
    raise ValueError(f"{block_name}: image input must be SRSImage or Collection[SRSImage], got {type(value).__name__}")


def _get_wavenumbers(item: SRSImage, n_w: int) -> list[float]:
    if item.meta is not None and item.meta.wavenumbers_cm1 is not None:
        return list(item.meta.wavenumbers_cm1)
    return [float(i) for i in range(n_w)]


def _scores_to_image_collection(
    scores: np.ndarray,
    spatial_shape: tuple[int, ...],
    spatial_axes: list[str],
    framework: Any,
) -> Collection:
    # ADR-043 FR-009 Mode C — legitimate ome drop.
    # PC score maps are NOT spatially equivalent to the source SRSImage: the
    # spectral (lambda) axis is replaced by a derived ``pc_id`` index, so
    # OME pixel-axis ordering / channel descriptions / detector annotations
    # no longer apply. Per spec adr-043-package-migration FR-009 Mode C, when
    # the cross-type output drops spatial alignment with the source, leaving
    # ``meta=None`` (or a Meta without ``ome``) is the documented behavior.
    # This is reused by ``SRSICA`` for IC score maps for the same reason.
    n_components = scores.shape[1]
    cube = scores.reshape(*spatial_shape, n_components).astype(np.float32)
    maps: list[Image] = []
    for k in range(n_components):
        data_k = cube[..., k]
        img = Image(
            axes=list(spatial_axes),
            shape=data_k.shape,
            dtype=data_k.dtype,
            framework=framework,
            meta=None,
            user={},
            storage_ref=None,
        )
        img._data = data_k  # type: ignore[attr-defined]
        maps.append(img)
    return Collection(items=cast(list[DataObject], maps), item_type=Image)


def _loadings_to_dataframe(
    loadings: np.ndarray,
    wavenumbers: list[float],
    id_column: str,
    framework: Any,
) -> DataFrame:
    column_data: dict[str, Any] = {
        id_column: pa.array(list(range(loadings.shape[0])), type=pa.int64()),
    }
    for col_idx, wn in enumerate(wavenumbers):
        column_data[str(wn)] = pa.array(loadings[:, col_idx].tolist())
    table = pa.table(column_data)
    result = DataFrame(
        columns=list(table.column_names),
        row_count=table.num_rows,
        framework=framework,
    )
    result._arrow_table = table  # type: ignore[attr-defined]
    return cast(DataFrame, result)


__all__ = ["SRSPCA"]
