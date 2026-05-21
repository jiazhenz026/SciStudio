"""SRSVCA — Vertex Component Analysis endmember extraction.

Walks the data simplex (Nascimento & Bioucas-Dias 2005) to pick
``n_components`` endmember spectra. The module-level helper
:func:`_extract_endmembers` is the test seam reused by :class:`SRSUnmix`
when no reference DataFrame is supplied.

See ``docs/specs/phase11-srs-block-spec.md`` §9 T-SRS-006.
"""

from __future__ import annotations

from typing import Any, ClassVar, cast

import numpy as np
import pyarrow as pa

from scistudio.blocks.base.block import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.dataframe import DataFrame
from scistudio.utils.constraints import has_axes
from scistudio_blocks_srs.types import SRSImage


def _extract_endmembers(
    item: SRSImage,
    n_components: int,
) -> tuple[np.ndarray, list[float]]:
    """Run VCA on ``item`` and return ``(endmembers, wavenumbers)``.

    Module-level so that :class:`SRSUnmix` can reuse it for the auto-VCA
    fallback. Output endmember matrix has shape ``(n_components, n_w)``
    and lists the **original** full-dimension pixel spectra at the chosen
    pixel indices. Wavenumbers come from ``item.meta.wavenumbers_cm1`` if
    set, else ``list(range(n_w))``.

    Algorithm: PCA pre-reduce → iterative simplex walk in the reduced
    subspace (``random_state=42``) → return original-dimension pixel
    spectra at chosen indices.
    """
    if n_components < 2:
        raise ValueError(f"SRSVCA: n_components must be >= 2, got {n_components}")

    lambda_pos = item.axes.index("lambda")
    cube = np.asarray(item.to_memory(), dtype=np.float64)
    moved = np.moveaxis(cube, lambda_pos, -1)
    n_w = moved.shape[-1]
    pixels = moved.reshape(-1, n_w)
    n_pixels = pixels.shape[0]

    if n_components > min(n_pixels, n_w):
        raise ValueError(f"SRSVCA: n_components={n_components} exceeds min(n_pixels={n_pixels}, n_w={n_w})")

    from sklearn.decomposition import PCA

    reduced = PCA(n_components=n_components, random_state=42).fit_transform(pixels)

    rng = np.random.default_rng(42)
    indices: list[int] = []
    basis = np.zeros((n_components, n_components), dtype=np.float64)
    for i in range(n_components):
        # Random unit vector, then project onto complement of current basis.
        w = rng.standard_normal(n_components)
        if i > 0:
            subspace = basis[:i]
            w = w - subspace.T @ (subspace @ w)
        norm = float(np.linalg.norm(w))
        if norm < 1e-12:
            # Degenerate projection; fall back to an axis vector.
            w = np.zeros(n_components)
            w[i] = 1.0
        else:
            w = w / norm
        projections = np.abs(reduced @ w)
        idx = int(np.argmax(projections))
        indices.append(idx)
        basis[i] = reduced[idx] / (np.linalg.norm(reduced[idx]) + 1e-12)

    endmembers = pixels[indices].astype(np.float64)

    wavenumbers: list[float]
    if item.meta is not None and item.meta.wavenumbers_cm1 is not None:
        wavenumbers = list(item.meta.wavenumbers_cm1)
    else:
        wavenumbers = [float(i) for i in range(n_w)]

    return endmembers, wavenumbers


class SRSVCA(ProcessBlock):
    """Endmember extraction via Vertex Component Analysis."""

    name: ClassVar[str] = "SRS VCA"
    type_name: ClassVar[str] = "srs.vca"
    description: ClassVar[str] = "Vertex Component Analysis endmember extraction."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "component_analysis"
    algorithm: ClassVar[str] = "vca"

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
            name="endmembers",
            accepted_types=[DataFrame],
            description="DataFrame with `endmember_id` index and wavenumber columns.",
        ),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "n_components": {"type": "integer", "default": 4, "minimum": 2},
        },
    }

    def process_item(
        self,
        item: SRSImage,
        config: BlockConfig,
        state: Any = None,
    ) -> DataFrame:
        """Call :func:`_extract_endmembers` and wrap as a SciStudio DataFrame."""
        n_components = int(config.get("n_components", 4))
        endmembers, wavenumbers = _extract_endmembers(item, n_components)

        # Build a pyarrow table with an explicit endmember_id column.
        column_data: dict[str, Any] = {
            "endmember_id": pa.array(list(range(endmembers.shape[0])), type=pa.int64()),
        }
        for col_idx, wn in enumerate(wavenumbers):
            column_data[str(wn)] = pa.array(endmembers[:, col_idx].tolist())
        table = pa.table(column_data)

        result = DataFrame(
            columns=list(table.column_names),
            row_count=table.num_rows,
            framework=item.framework.derive(),
        )
        result._arrow_table = table  # type: ignore[attr-defined]
        return cast(DataFrame, result)


__all__ = ["SRSVCA", "_extract_endmembers"]
