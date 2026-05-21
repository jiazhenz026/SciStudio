"""SRS plugin types — :class:`SRSImage` (subclass of imaging plugin's ``Image``).

Per master plan §2.4, the SRS plugin defines exactly one type:

* :class:`SRSImage` — an imaging-plugin :class:`Image` with the spectral
  ``lambda`` axis required, plus an SRS-specific :class:`SRSImage.Meta`
  Pydantic model carrying digitizer parameters and laser/wavenumber metadata.

**There is intentionally no** ``RamanSpectrum(Series)`` **type** —
spectra are passed around as long-format DataFrames per master plan §2.4.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import ConfigDict

# Cross-plugin import per standards doc §Q5. ``Image`` lives in the
# imaging plugin (T-IMG-001).
from scistudio_blocks_imaging.types import Image  # type: ignore[import-not-found]

from scistudio.core.units import PhysicalQuantity


class SRSImage(Image):  # type: ignore[misc,valid-type]
    """Stimulated Raman Scattering image with required spectral axis.

    Extends the imaging plugin's :class:`Image` by:

    * tightening :attr:`required_axes` to ``frozenset({"y", "x", "lambda"})``;
    * inheriting :attr:`allowed_axes` from :class:`Image` so any combination
      of ``{t, z, c, lambda, y, x}`` remains valid as long as ``y/x/lambda``
      are present;
    * declaring an inner :class:`Meta` Pydantic model that extends
      ``Image.Meta`` with the nine SRS-specific fields locked in master
      plan §2.4 (wavenumbers, laser power, integration time, four
      digitizer parameters, pump/Stokes wavelengths).

    See ``docs/specs/phase11-srs-block-spec.md`` §9 T-SRS-001 for the full
    field table and acceptance criteria.
    """

    required_axes: ClassVar[frozenset[str]] = frozenset({"y", "x"})
    canonical_order: ClassVar[tuple[str, ...]] = ("t", "z", "c", "lambda", "y", "x")

    class Meta(Image.Meta):
        """Per-instance SRS metadata locked by the Phase 11 SRS spec."""

        model_config = ConfigDict(frozen=True, extra="forbid")

        wavenumbers_cm1: list[float] | None = None
        laser_power: float | None = None
        integration_time: PhysicalQuantity | None = None
        digitizer_bit_depth: int | None = None
        digitizer_voltage_range: float | None = None
        digitizer_offset: float | None = None
        digitizer_scale: float | None = None
        pump_wavelength_nm: float | None = None
        stokes_wavelength_nm: float | None = None

    def __init__(
        self,
        *,
        axes: list[str],
        shape: tuple[int, ...] | None = None,
        dtype: Any = None,
        chunk_shape: tuple[int, ...] | None = None,
        meta: Meta | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            axes=axes,
            shape=shape,
            dtype=dtype,
            chunk_shape=chunk_shape,
            meta=meta,
            **kwargs,
        )
        self._validate_wavenumbers_length()

    def _validate_wavenumbers_length(self) -> None:
        """Ensure metadata wavenumbers match the lambda axis length when known."""
        if self.meta is None or self.meta.wavenumbers_cm1 is None:
            return
        if self.shape is None:
            return

        if "lambda" not in self.axes:
            return  # no lambda axis — single-wavelength image, skip check
        lambda_axis = self.axes.index("lambda")
        lambda_size = self.shape[lambda_axis]
        if len(self.meta.wavenumbers_cm1) != lambda_size:
            raise ValueError(
                "SRSImage.Meta.wavenumbers_cm1 length must match the lambda axis size: "
                f"{len(self.meta.wavenumbers_cm1)} != {lambda_size}"
            )


def get_types() -> list[type]:
    """Plugin entry point — return the list of types contributed by this plugin.

    T-SRS-013 wires the final entry-point registration; T-SRS-001 provides
    the concrete type payload.
    """
    return [SRSImage]


__all__ = ["SRSImage", "get_types"]
