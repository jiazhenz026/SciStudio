"""SRSKMeansCluster — k-means clustering of pixel spectra → :class:`Label`.

Two outputs: a :class:`Label` raster and a centroid :class:`DataFrame`
indexed by ``cluster_id``. Overrides :meth:`run` directly.

See ``docs/specs/phase11-srs-block-spec.md`` §9 T-SRS-010.
"""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
from scieasy_blocks_imaging.types import Label  # type: ignore[import-not-found]

from scieasy.blocks.base.block import BlockConfig
from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.core.types.array import Array
from scieasy.core.types.dataframe import DataFrame
from scieasy.utils.constraints import has_axes
from scieasy_blocks_srs.component_analysis.srs_pca import (
    _get_wavenumbers,
    _loadings_to_dataframe,
    _single_srs_image,
)
from scieasy_blocks_srs.types import SRSImage

ALLOWED_INIT: tuple[str, ...] = ("k-means++", "random")


class SRSKMeansCluster(ProcessBlock):
    """K-means clustering of per-pixel spectra into a :class:`Label`."""

    name: ClassVar[str] = "SRS K-Means Cluster"
    type_name: ClassVar[str] = "srs.kmeans"
    description: ClassVar[str] = "K-means clustering of per-pixel spectra."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "component_analysis"
    algorithm: ClassVar[str] = "kmeans"

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
            name="labels",
            accepted_types=[Label],
            description="Label raster of cluster assignments (int32).",
        ),
        OutputPort(
            name="centroids",
            accepted_types=[DataFrame],
            description="Centroid DataFrame with `cluster_id` index.",
        ),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "n_clusters": {"type": "integer", "default": 4, "minimum": 2},
            "init": {
                "type": "string",
                "enum": list(ALLOWED_INIT),
                "default": "k-means++",
            },
            "n_init": {"type": "integer", "default": 10, "minimum": 1},
        },
    }

    def run(
        self,
        inputs: dict[str, Any],
        config: BlockConfig,
    ) -> dict[str, Any]:
        """Reshape ``(n_pixels, n_w)``, fit KMeans, build Label + centroids."""
        from sklearn.cluster import KMeans

        item = _single_srs_image(inputs.get("image"), "SRSKMeansCluster")
        n_clusters = int(config.get("n_clusters", 4))
        init = str(config.get("init", "k-means++"))
        n_init = int(config.get("n_init", 10))

        if init not in ALLOWED_INIT:
            raise ValueError(f"SRSKMeansCluster: init must be one of {ALLOWED_INIT}, got {init!r}")

        lambda_pos = item.axes.index("lambda")
        cube = np.asarray(item.to_memory(), dtype=np.float64)
        moved = np.moveaxis(cube, lambda_pos, -1)
        spatial_shape = moved.shape[:-1]
        n_w = moved.shape[-1]
        flat = moved.reshape(-1, n_w)

        km = KMeans(
            n_clusters=n_clusters,
            init=init,
            n_init=n_init,
            random_state=42,
        )
        labels_flat = km.fit_predict(flat)
        labels_nd = labels_flat.reshape(spatial_shape).astype(np.int32)

        spatial_axes = [ax for ax in item.axes if ax != "lambda"]
        raster = Array(
            axes=list(spatial_axes),
            shape=labels_nd.shape,
            dtype=labels_nd.dtype,
            framework=item.framework.derive(),
        )
        raster._data = labels_nd  # type: ignore[attr-defined]

        # ADR-043 FR-009 Mode C — Image-domain → Label is a shape-preserving
        # cross-type derivation (cluster assignments share the source's y/x
        # spatial layout), so the source SRSImage's OME metadata MUST be
        # propagated onto the Label output per spec FR-011.
        label_obj = Label(
            slots={"raster": raster},
            framework=item.framework.derive(),
            meta=Label.Meta(
                source_file=getattr(item.meta, "source_file", None) if item.meta is not None else None,
                n_objects=n_clusters,
                ome=getattr(item.meta, "ome", None) if item.meta is not None else None,
            ),
            user=dict(item.user),
        )

        centers = np.asarray(km.cluster_centers_, dtype=np.float64)
        wavenumbers = _get_wavenumbers(item, n_w)
        centroids_df = _loadings_to_dataframe(centers, wavenumbers, "cluster_id", item.framework.derive())
        return {"labels": label_obj, "centroids": centroids_df}


__all__ = ["ALLOWED_INIT", "SRSKMeansCluster"]
