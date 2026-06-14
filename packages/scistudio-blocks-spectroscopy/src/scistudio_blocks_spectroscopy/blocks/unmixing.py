"""Spectroscopy spectral unmixing block (FR-104..FR-112).

One block, :class:`SpectralUnmixing`. It fits each sample spectrum as a linear
combination of reference spectra and emits a wide ``coefficients`` table plus a
``fit_quality`` table. It does NOT output fitted/residual/component spectra or a
new result type in this draft (FR-112).

``scipy.optimize.nnls`` is lazy-imported inside the run body for the
non-negative methods; unconstrained least squares uses ``numpy.linalg.lstsq``.
"""

from __future__ import annotations

from typing import Any, ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio_blocks_spectroscopy.types import Spectrum


class SpectralUnmixing(ProcessBlock):
    """Linearly unmix sample spectra into reference-component coefficients."""

    type_name: ClassVar[str] = "spectroscopy.spectral_unmixing"
    name: ClassVar[str] = "Spectral Unmixing"
    description: ClassVar[str] = "Fit each sample as a linear mix of references; emit coefficients + fit quality."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "unmixing"
    algorithm: ClassVar[str] = "spectral_unmixing"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(
            name="spectra",
            accepted_types=[Spectrum],
            is_collection=True,
            required=True,
            description="Sample spectra to unmix.",
        ),
        InputPort(
            name="references",
            accepted_types=[Spectrum],
            is_collection=True,
            required=True,
            description="Reference component spectra.",
        ),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="coefficients", accepted_types=[DataFrame]),
        OutputPort(name="fit_quality", accepted_types=[DataFrame]),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": [
                    "least_squares",
                    "non_negative_least_squares",
                    "sum_to_one_non_negative_least_squares",
                ],
                "default": "least_squares",
                "title": "Unmixing method",
            },
            "component_label_source": {
                "type": "string",
                "default": "spectrum_id",
                "title": "Component label source",
                "description": "Reference field used to name coefficient columns.",
            },
            "grid_policy": {
                "type": "string",
                "enum": ["error", "interpolate_references_to_sample"],
                "default": "error",
                "title": "Grid compatibility policy",
            },
        },
        "required": ["method"],
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Unmix samples into reference coefficients (FR-104..FR-112).

        Implementation plan:
          1. spectra = inputs['spectra']; references = inputs['references'].
          2. Apply grid_policy: 'error' fail on incompatible grids, else
             numpy.interp references onto each sample grid (FR-111).
          3. Build design matrix A (references as columns); solve per method —
             least_squares: numpy.linalg.lstsq; non_negative_least_squares: lazy
             scipy.optimize.nnls; sum_to_one_nnls: augment with a large-weight
             ones row then nnls.
          4. coefficients: wide DataFrame, one row per sample, columns
             {spectrum_id, method, <one per reference>}; column names generated
             from component_label_source, deterministic/table-safe/collision-free
             (FR-108, FR-109).
          5. fit_quality: one row per sample {spectrum_id, method, status,
             residual_norm, rmse, n_components, r2?} (FR-110).
          6. Return {'coefficients': dataframe_collection(coef_df),
             'fit_quality': dataframe_collection(quality_df)}.
        Edge cases: duplicate reference labels (dedupe column names); singular A
          (ill_conditioned status); zero references.
        Test plan: test_unmixing_blocks.py::test_unmixing_wide_coefficients,
          ::test_unmixing_collision_free_columns,
          ::test_unmixing_fit_quality_rows.
        """
        raise NotImplementedError("skeleton — implement per FR-104..FR-112; see comment above")


BLOCKS: list[type] = [SpectralUnmixing]

__all__ = ["BLOCKS", "SpectralUnmixing"]
