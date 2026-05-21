"""SRSICA — FastICA on per-pixel spectra.

Structurally identical to :class:`SRSPCA` with FastICA in place of PCA.
The ``method`` enum has only one valid value (``"fastica"``); the
single-element enum is intentional and reserves the field for future
addenda.

See ``docs/specs/phase11-srs-block-spec.md`` §9 T-SRS-009.
"""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np

from scistudio.blocks.base.block import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio.utils.constraints import has_axes
from scistudio_blocks_srs.component_analysis.srs_pca import (
    _get_wavenumbers,
    _loadings_to_dataframe,
    _scores_to_image_collection,
    _single_srs_image,
)
from scistudio_blocks_srs.types import SRSImage

ALLOWED_METHODS: tuple[str, ...] = ("fastica",)


class SRSICA(ProcessBlock):
    """Independent Component Analysis on per-pixel spectra (FastICA only)."""

    name: ClassVar[str] = "SRS ICA"
    type_name: ClassVar[str] = "srs.ica"
    description: ClassVar[str] = "FastICA on per-pixel spectra."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "component_analysis"
    algorithm: ClassVar[str] = "fastica"

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
            name="ic_maps",
            accepted_types=[Collection],
            description="Collection[Image] of per-IC 2D score maps.",
        ),
        OutputPort(
            name="components",
            accepted_types=[DataFrame],
            description="Component DataFrame with `ic_id` index and wavenumber columns.",
        ),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "n_components": {"type": "integer", "default": 4, "minimum": 1},
            "method": {
                "type": "string",
                "enum": list(ALLOWED_METHODS),
                "default": "fastica",
            },
        },
    }

    def run(
        self,
        inputs: dict[str, Any],
        config: BlockConfig,
    ) -> dict[str, Any]:
        """Run FastICA and emit IC maps + components."""
        from sklearn.decomposition import FastICA

        method = str(config.get("method", "fastica"))
        if method not in ALLOWED_METHODS:
            raise ValueError(f"SRSICA: method must be one of {ALLOWED_METHODS}, got {method!r}")

        item = _single_srs_image(inputs.get("image"), "SRSICA")
        n_components = int(config.get("n_components", 4))

        lambda_pos = item.axes.index("lambda")
        cube = np.asarray(item.to_memory(), dtype=np.float64)
        moved = np.moveaxis(cube, lambda_pos, -1)
        spatial_shape = moved.shape[:-1]
        n_w = moved.shape[-1]
        if n_components > n_w:
            raise ValueError(f"SRSICA: n_components={n_components} exceeds n_wavenumbers={n_w}")
        flat = moved.reshape(-1, n_w)

        ica = FastICA(n_components=n_components, random_state=42)
        scores = ica.fit_transform(flat)  # (n_pixels, n_components)
        components = np.asarray(ica.components_, dtype=np.float64)  # (n_components, n_w)

        spatial_axes = [ax for ax in item.axes if ax != "lambda"]
        maps = _scores_to_image_collection(scores, spatial_shape, spatial_axes, item.framework.derive())
        wavenumbers = _get_wavenumbers(item, n_w)
        components_df = _loadings_to_dataframe(components, wavenumbers, "ic_id", item.framework.derive())
        return {"ic_maps": maps, "components": components_df}


__all__ = ["ALLOWED_METHODS", "SRSICA"]
