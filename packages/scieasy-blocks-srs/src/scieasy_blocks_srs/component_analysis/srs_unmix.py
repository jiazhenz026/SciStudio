"""SRSUnmix — NNLS spectral unmixing with explicit mode selector.

Two inputs (image, optional references) → two outputs (abundance maps,
endmembers DataFrame). Overrides :meth:`run` directly because the default
``ProcessBlock.run`` only handles a single input port.

Modes:
- ``nnls``: requires ``references`` input; raises ``ValueError`` if missing.
- ``vca_nnls``: extracts endmembers via VCA first, then NNLS; ignores references.

See ``docs/specs/phase11-srs-block-spec.md`` §9 T-SRS-007.
"""

from __future__ import annotations

import logging
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
from scieasy_blocks_srs.component_analysis.srs_vca import _extract_endmembers
from scieasy_blocks_srs.types import SRSImage

_LOGGER = logging.getLogger(__name__)


class SRSUnmix(ProcessBlock):
    """NNLS unmixing of an :class:`SRSImage` against reference spectra.

    Use ``mode="nnls"`` for reference-based unmixing (references required).
    Use ``mode="vca_nnls"`` for automatic endmember extraction via VCA.
    """

    name: ClassVar[str] = "SRS Unmix"
    type_name: ClassVar[str] = "srs.unmix"
    description: ClassVar[str] = "NNLS spectral unmixing with explicit mode selector (nnls or vca_nnls)."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "component_analysis"
    algorithm: ClassVar[str] = "nnls_unmix"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(
            name="image",
            accepted_types=[SRSImage],
            description="SRSImage with y/x/lambda axes.",
            constraint=has_axes("y", "x", "lambda"),
            constraint_description="image must carry y/x/lambda axes",
        ),
        InputPort(
            name="references",
            accepted_types=[DataFrame],
            description="Endmember reference DataFrame; required in nnls mode, ignored in vca_nnls mode.",
            required=False,
        ),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(
            name="abundance_maps",
            accepted_types=[Collection],
            description="Collection[Image] of per-endmember 2D abundance maps.",
        ),
        OutputPort(
            name="endmembers",
            accepted_types=[DataFrame],
            description="Endmember DataFrame (passthrough or VCA-extracted).",
        ),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["nnls", "vca_nnls"],
                "default": "nnls",
                "title": "Mode",
                "description": "nnls: requires references input. vca_nnls: auto-extracts endmembers via VCA.",
                "ui_priority": 0,
            },
            "auto_vca_n_components": {"type": "integer", "default": 4, "minimum": 2},
        },
    }

    def run(
        self,
        inputs: dict[str, Any],
        config: BlockConfig,
    ) -> dict[str, Any]:
        """Iterate the image input, dispatch to ``_unmix_one``, pack outputs."""
        image_in = inputs.get("image")
        if image_in is None:
            raise ValueError("SRSUnmix: missing required 'image' input")

        if isinstance(image_in, SRSImage):
            items = [image_in]
        elif isinstance(image_in, Collection):
            items = [cast(SRSImage, obj) for obj in image_in]
        else:
            raise ValueError(
                f"SRSUnmix: image input must be SRSImage or Collection[SRSImage], got {type(image_in).__name__}"
            )
        if not items:
            raise ValueError("SRSUnmix: image collection is empty")

        ref_input = inputs.get("references")

        all_abundance_maps: list[Image] = []
        last_endmembers_df: DataFrame | None = None
        for item in items:
            maps, endmembers_df = self._unmix_one(item, ref_input, config)
            all_abundance_maps.extend(maps)
            last_endmembers_df = endmembers_df

        collection = Collection(
            items=cast(list[DataObject], all_abundance_maps),
            item_type=Image,
        )
        assert last_endmembers_df is not None  # non-empty items guaranteed above
        return {"abundance_maps": collection, "endmembers": last_endmembers_df}

    def _unmix_one(
        self,
        item: SRSImage,
        ref_input: Any,
        config: BlockConfig,
    ) -> tuple[list[Image], DataFrame]:
        """Per-image NNLS solve.

        Returns ``(abundance_image_list, endmember_dataframe)``.
        """
        from scipy.optimize import nnls

        # Resolve reference endmembers based on explicit mode.
        mode = str(config.get("mode", "nnls"))
        references: np.ndarray
        wavenumbers: list[float]

        if mode == "nnls":
            ref_df = _first_reference_df(ref_input)
            if ref_df is None:
                raise ValueError(
                    "SRSUnmix: mode='nnls' requires the 'references' input to be connected. "
                    "Either provide reference spectra or switch to mode='vca_nnls'."
                )
            references, wavenumbers = _references_from_dataframe(ref_df)
        elif mode == "vca_nnls":
            n = int(config.get("auto_vca_n_components", 4))
            _LOGGER.info(
                "SRSUnmix: mode='vca_nnls', extracting %d endmembers via VCA.",
                n,
            )
            references, wavenumbers = _extract_endmembers(item, n)
        else:
            raise ValueError(f"SRSUnmix: unknown mode {mode!r}; expected 'nnls' or 'vca_nnls'")

        n_endmembers, n_w_refs = references.shape

        # Reshape image to (n_pixels, n_w) with lambda last.
        lambda_pos = item.axes.index("lambda")
        cube = np.asarray(item.to_memory(), dtype=np.float64)
        moved = np.moveaxis(cube, lambda_pos, -1)
        spatial_shape = moved.shape[:-1]
        n_w = moved.shape[-1]
        if n_w != n_w_refs:
            raise ValueError(
                f"SRSUnmix: reference wavenumber count {n_w_refs} does not match image lambda length {n_w}"
            )
        flat = moved.reshape(-1, n_w)
        n_pixels = flat.shape[0]

        # Per-pixel NNLS.
        abundances = np.zeros((n_pixels, n_endmembers), dtype=np.float64)
        a_matrix = references.T  # shape (n_w, n_endmembers)
        for i in range(n_pixels):
            solution, _residual = nnls(a_matrix, flat[i])
            abundances[i] = solution

        # If the image is not purely 2D spatial, collapse leading axes to (y, x)
        # by treating the first two spatial dims as y/x and any others as extras.
        # Per spec: each abundance map is 2D Image axes=["y","x"]. If there are
        # extra leading spatial dims (e.g. t, z, c), reshape by flattening them.
        # Simpler approach: always produce one Image per endmember with shape
        # equal to the full spatial_shape and axes matching item.axes minus lambda.
        spatial_axes = [ax for ax in item.axes if ax != "lambda"]
        if len(spatial_shape) != len(spatial_axes):
            raise ValueError("SRSUnmix: internal shape/axes mismatch after moving lambda axis")

        # ADR-043 FR-009 Mode C — legitimate ome drop.
        # Endmember abundance maps share y/x with the source SRSImage, but
        # the spectral (lambda) axis is replaced by a derived ``endmember_id``
        # index — OME channel / pixel-dimension descriptions no longer apply
        # to a per-endmember 2D map. Per spec adr-043-package-migration
        # FR-009 Mode C, when the cross-type output drops spectral alignment
        # with the source, leaving ``meta=None`` is the documented behavior.
        maps: list[Image] = []
        ab_cube = abundances.reshape(*spatial_shape, n_endmembers).astype(np.float32)
        for k in range(n_endmembers):
            data_k = ab_cube[..., k]
            img = Image(
                axes=list(spatial_axes),
                shape=data_k.shape,
                dtype=data_k.dtype,
                framework=item.framework.derive(),
                meta=None,
                user=dict(item.user),
                storage_ref=None,
            )
            img._data = data_k  # type: ignore[attr-defined]
            maps.append(img)

        endmember_df = _endmembers_to_dataframe(references, wavenumbers, item.framework.derive())
        return maps, endmember_df


def _first_reference_df(ref_input: Any) -> DataFrame | None:
    if ref_input is None:
        return None
    if isinstance(ref_input, DataFrame):
        return ref_input
    if isinstance(ref_input, Collection):
        items = list(ref_input)
        if not items:
            return None
        first = items[0]
        if not isinstance(first, DataFrame):
            raise ValueError(
                f"SRSUnmix: references collection must contain DataFrame items, got {type(first).__name__}"
            )
        return first
    raise ValueError(f"SRSUnmix: references must be DataFrame or Collection[DataFrame], got {type(ref_input).__name__}")


def _references_from_dataframe(df: DataFrame) -> tuple[np.ndarray, list[float]]:
    table = getattr(df, "_arrow_table", None)
    if table is None:
        raise ValueError("SRSUnmix: references DataFrame has no backing arrow table; cannot unmix")
    columns = list(table.column_names)
    # Drop an optional 'endmember_id' column from the feature matrix.
    feature_cols = [c for c in columns if c != "endmember_id"]
    if not feature_cols:
        raise ValueError("SRSUnmix: references DataFrame has no feature columns")
    matrix = np.asarray(
        [table.column(c).to_pylist() for c in feature_cols], dtype=np.float64
    ).T  # shape (n_endmembers, n_w)
    wavenumbers: list[float] = []
    for c in feature_cols:
        try:
            wavenumbers.append(float(c))
        except ValueError:
            wavenumbers.append(float(len(wavenumbers)))
    return matrix, wavenumbers


def _endmembers_to_dataframe(
    endmembers: np.ndarray,
    wavenumbers: list[float],
    framework: Any,
) -> DataFrame:
    column_data: dict[str, Any] = {
        "endmember_id": pa.array(list(range(endmembers.shape[0])), type=pa.int64()),
    }
    for col_idx, wn in enumerate(wavenumbers):
        column_data[str(wn)] = pa.array(endmembers[:, col_idx].tolist())
    table = pa.table(column_data)
    result = DataFrame(
        columns=list(table.column_names),
        row_count=table.num_rows,
        framework=framework,
    )
    result._arrow_table = table  # type: ignore[attr-defined]
    return cast(DataFrame, result)


__all__ = ["SRSUnmix"]
