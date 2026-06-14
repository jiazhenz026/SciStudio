"""Spectroscopy library matching block (FR-121..FR-126).

One block, :class:`MatchSpectralLibrary`. It matches query spectra against a
library represented as a ``SpectralDataset`` (no separate library type, FR-122)
using a selectable similarity/distance method and emits a ranked ``matches``
table.

All matching math (cosine/pearson/spectral angle/euclidean) is pure numpy; no
scipy is required.
"""

from __future__ import annotations

from typing import Any, ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio_blocks_spectroscopy.types import SpectralDataset, Spectrum


class MatchSpectralLibrary(ProcessBlock):
    """Rank library spectra against each query spectrum."""

    type_name: ClassVar[str] = "spectroscopy.match_spectral_library"
    name: ClassVar[str] = "Match Spectral Library"
    description: ClassVar[str] = "Match query spectra against a SpectralDataset library using a selectable method."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "library_matching"
    algorithm: ClassVar[str] = "match_spectral_library"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(
            name="spectra",
            accepted_types=[Spectrum],
            is_collection=True,
            required=True,
            description="Query spectra.",
        ),
        InputPort(
            name="library",
            accepted_types=[SpectralDataset],
            required=True,
            description="Library represented as a SpectralDataset.",
        ),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="matches", accepted_types=[DataFrame]),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": [
                    "cosine_similarity",
                    "pearson_correlation",
                    "spectral_angle",
                    "euclidean_distance",
                ],
                "default": "cosine_similarity",
                "title": "Matching method",
            },
            "top_k": {"type": "integer", "default": 1, "minimum": 1, "title": "Top K matches"},
            "grid_policy": {
                "type": "string",
                "enum": ["error", "interpolate_library_to_query"],
                "default": "error",
                "title": "Grid/unit compatibility policy",
            },
        },
        "required": ["method"],
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Match queries against the library (FR-121..FR-126).

        Implementation plan:
          1. spectra = inputs['spectra']; library = inputs['library'] -> split its
             `index`/`spectra` slots into library spectra keyed by spectrum_id.
          2. Apply grid_policy: 'error' fail/non-success on incompatible grids or
             units; otherwise interpolate library onto query grid (FR-126).
          3. method (numpy): cosine = a.b/(|a||b|); pearson = corrcoef; spectral
             angle = arccos(cosine); euclidean = norm(a-b). rank 1 = best match
             regardless of similarity- vs distance-orientation (FR-125).
          4. Keep top_k per query; emit matches rows {spectrum_id,
             library_spectrum_id, method, rank, score, status} (FR-124).
        Edge cases: empty library; incompatible grids; ties in score.
        Test plan: test_library_matching_blocks.py::test_match_ranks_top_k,
          ::test_match_errors_on_incompatible_grid.
        """
        raise NotImplementedError("skeleton — implement per FR-121..FR-126; see comment above")


BLOCKS: list[type] = [MatchSpectralLibrary]

__all__ = ["BLOCKS", "MatchSpectralLibrary"]
