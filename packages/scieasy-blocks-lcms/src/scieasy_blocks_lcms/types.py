"""LC-MS plugin types: ``MSRawFile``, ``PeakTable``, ``MIDTable``, ``SampleMetadata``.

Per master plan §2.4 LC-MS PLUGIN types section and
``docs/specs/phase11-lcms-block-spec.md`` §9 T-LCMS-002.

Forbidden by master plan: ``MSSpectrum(Series)`` and ``MSRun(Array)`` —
scan-level data is handled externally by ElMAVEN.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from scieasy.core.types.artifact import Artifact
from scieasy.core.types.dataframe import DataFrame


class MSRawFile(Artifact):
    """Raw LC-MS acquisition file (mzML / mzXML / .raw / .d folder).

    The actual scan data stays in the file. This class only records the
    path and minimal header metadata. ElMAVEN (or another external
    tool) handles parsing.

    Per master plan §2.4 the LC-MS plugin DOES NOT introduce
    ``MSSpectrum(Series)`` or ``MSRun(Array)`` — scan-level data is
    external. This is enforced by the absence of any such subclass in
    this module and by the ``test_no_msspectrum_class`` regression test.
    """

    class Meta(BaseModel):
        """Frozen Pydantic v2 metadata for :class:`MSRawFile`."""

        model_config = ConfigDict(frozen=True)

        format: str = Field(..., description='Acquisition file format: "mzML" | "mzXML" | "raw" | "d"')
        polarity: str | None = Field(None, description='Ionisation polarity: "+" | "-" | None if unknown')
        instrument: str | None = Field(None, description="Instrument model name (e.g. 'Q Exactive HF')")
        acquisition_date: datetime | None = Field(
            None, description="UTC datetime of acquisition; None if not in header"
        )
        sample_id: str | None = Field(
            None,
            description="Sample identifier; None if not derivable from filename",
        )


class PeakTable(DataFrame):
    """LC-MS feature / peak table.

    Produced by ElMAVEN, MZmine, XCMS, or a similar peak picker. Column
    names vary by source; the :attr:`Meta.source` field records which
    tool produced this table so downstream blocks can apply
    source-specific column-name heuristics.
    """

    class Meta(BaseModel):
        """Frozen Pydantic v2 metadata for :class:`PeakTable`."""

        model_config = ConfigDict(frozen=True)

        source: str = Field(..., description='Source tool: "ElMAVEN" | "MZmine" | "XCMS" | ...')
        polarity: str | None = Field(
            None,
            description='Ionisation polarity: "+" | "-" | None if mixed/unknown',
        )


class MIDTable(DataFrame):
    """Mass Isotopomer Distribution table (long format).

    Format (as produced by the AccuCor R package — the user's primary
    upstream tool, see ``phase11-lcms-block-spec.md`` §8 Q-3)::

        Compound    C13    H2    UL0    UL3    UL2    UL1    SE3
        cytosine    0      0     1.0    1.0    0.9995 1.0    0.9542
        cytosine    1      0     0.0    0.0    0.0    0.0    0.0029

    Each row is a ``(compound, isotopologue)`` combination; each sample
    is a column. Values are fractional abundance (sum to 1.0 per
    compound per sample, modulo rounding).
    """

    class Meta(BaseModel):
        """Frozen Pydantic v2 metadata for :class:`MIDTable`."""

        model_config = ConfigDict(frozen=True)

        tracer_atoms: list[str] = Field(
            default_factory=lambda: ["C13"],
            description=(
                "Tracer isotope atoms; default ['C13'] for the dominant "
                "single-tracer case. Multi-tracer experiments use e.g. "
                "['C13', 'H2']."
            ),
        )
        sample_columns: list[str] = Field(
            ...,
            description="Sample column names (e.g. ['UL0', 'UL3', 'SE3'])",
        )
        corrected: bool = Field(
            True,
            description="Whether natural-abundance correction has been applied",
        )
        correction_tool: str = Field("AccuCor", description="Name of the correction tool used")


class SampleMetadata(DataFrame):
    """Per-sample metadata (group, timepoint, replicate, etc.)."""

    class Meta(BaseModel):
        """Frozen Pydantic v2 metadata for :class:`SampleMetadata`."""

        model_config = ConfigDict(frozen=True)

        sample_id_column: str = Field(
            "sample_id",
            description="Column name that identifies each sample",
        )


def get_types() -> list[type]:
    """Entry-point function returning the four plugin types.

    Wired into ``scieasy.types`` entry_points (T-LCMS-021). Listed in
    the order ``[MSRawFile, PeakTable, MIDTable, SampleMetadata]`` so
    the TypeRegistry palette groups artifacts before frames.
    """
    return [MSRawFile, PeakTable, MIDTable, SampleMetadata]
