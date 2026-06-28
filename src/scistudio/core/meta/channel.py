"""Frozen descriptor for one data-acquisition channel.

``ChannelInfo`` lives in ``scistudio.core.meta`` because several plugin
packages (imaging, spectral, and others) need to compose it. Keeping it in
core means those plugins never have to import one another just to share this
small descriptor.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from scistudio.stability import stable


@stable(since="0.3.1")
class ChannelInfo(BaseModel):
    """One acquisition channel's descriptive properties.

    Plugin ``Meta`` classes use this to describe per-channel properties such as
    excitation/emission wavelength and dye (for example
    ``FluorImage.Meta.channels`` or ``SRSImage.Meta``). Every field except
    ``name`` is optional, so an author fills in only what they have. The model
    is frozen (immutable), so it serialises to and from JSON cleanly when an
    object travels between processes.

    Example:
        >>> dapi = ChannelInfo(
        ...     name="DAPI",
        ...     dye="Hoechst 33342",
        ...     excitation_nm=358.0,
        ...     emission_nm=461.0,
        ... )
        >>> dapi.name
        'DAPI'
    """

    model_config = ConfigDict(frozen=True)

    name: str
    """Human-readable channel label (e.g. ``"DAPI"``, ``"GFP"``, ``"Cy5"``)."""
    dye: str | None = None
    """Dye or fluorophore name (e.g. ``"Hoechst 33342"``), if known."""
    excitation_nm: float | None = None
    """Excitation peak wavelength in nanometres, if known."""
    emission_nm: float | None = None
    """Emission peak wavelength in nanometres, if known."""
