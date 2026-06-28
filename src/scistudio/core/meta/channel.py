"""ChannelInfo — Pydantic BaseModel describing one acquisition channel.

Implements ADR-027 D5 / Addendum 1 §3 (Meta Pydantic constraints).

``ChannelInfo`` lives in ``scistudio.core.meta`` because multiple plugin
packages will need to compose it (``scistudio-blocks-imaging``,
``scistudio-blocks-spectral``, ...). Keeping it in core means plugins
never have to import from each other to share this primitive
descriptor — see ADR-027 D5 §"Question 3" for the rationale.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from scistudio.stability import stable


@stable(since="0.3.1")
class ChannelInfo(BaseModel):
    """Description of one acquisition channel.

    Used by ``FluorImage.Meta``, ``SRSImage.Meta``, and similar plugin
    ``Meta`` classes that need to describe per-channel properties
    (excitation wavelength, emission wavelength, dye, etc.).

    All fields are optional except ``name`` so plugin authors can fill
    in only what they have. The model is frozen so it round-trips
    through Pydantic JSON serialisation cleanly per ADR-027 Addendum 1
    §3.

    Attributes:
        name: Human-readable channel label (e.g. ``"DAPI"``, ``"GFP"``,
            ``"Cy5"``). Required.
        dye: Optional dye name (e.g. ``"Hoechst 33342"``).
        excitation_nm: Optional excitation peak wavelength in
            nanometres.
        emission_nm: Optional emission peak wavelength in nanometres.

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
    dye: str | None = None
    excitation_nm: float | None = None
    emission_nm: float | None = None
