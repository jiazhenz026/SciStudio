"""Imaging plugin type classes (T-IMG-001)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

import numpy as np
from ome_types.model import OME
from pydantic import BaseModel, ConfigDict, field_validator

from scieasy.core.meta import ChannelInfo
from scieasy.core.types.array import Array
from scieasy.core.types.composite import CompositeData
from scieasy.core.types.dataframe import DataFrame
from scieasy.core.units import PhysicalQuantity


class Image(Array):
    """General-purpose microscopy image, 2D to 6D."""

    required_axes: ClassVar[frozenset[str]] = frozenset({"y", "x"})
    allowed_axes: ClassVar[frozenset[str] | None] = frozenset({"t", "z", "c", "lambda", "y", "x"})
    canonical_order: ClassVar[tuple[str, ...]] = ("t", "z", "c", "lambda", "y", "x")

    class Meta(BaseModel):
        """Per-instance imaging metadata."""

        # ADR-043 / spec adr-043-package-migration FR-006: ``ome`` is a typed
        # carrier for the canonical OME-XML metadata structure. Populated by
        # IO handlers (Bio-Formats, OME-TIFF, PNG/JPEG EXIF mapping) and
        # propagated through ProcessBlocks per the propagation contract
        # (FR-009 modes A/B/C). The default is ``None`` so existing call sites
        # constructing ``Image.Meta()`` remain backward-compatible.
        # Pydantic v2 needs ``arbitrary_types_allowed`` to embed the
        # ``ome_types`` model class because it is exposed as a non-BaseModel
        # subclass after compat shimming on some platforms; declare it
        # alongside ``frozen=True``.
        model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

        pixel_size: PhysicalQuantity | None = None
        z_spacing: PhysicalQuantity | None = None
        time_interval: PhysicalQuantity | None = None
        channels: list[ChannelInfo] | None = None
        wavelengths_nm: list[float] | None = None
        objective: str | None = None
        acquisition_date: datetime | None = None
        source_file: str | None = None
        instrument: str | None = None
        ome: OME | None = None

        @field_validator("channels", mode="before")
        @classmethod
        def _coerce_channels(cls, value: Any) -> Any:
            if value is None:
                return None
            if not isinstance(value, list):
                return value

            coerced: list[Any] = []
            for item in value:
                if isinstance(item, str):
                    coerced.append(ChannelInfo(name=item))
                else:
                    coerced.append(item)
            return coerced


class Mask(Image):
    """Binary mask image. Enforces ``dtype=bool`` at construction."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._validate_mask_dtype()

    def _validate_mask_dtype(self) -> None:
        """Enforce ``dtype == bool``."""
        if self.dtype is None:
            return
        if np.dtype(self.dtype) != np.dtype(bool):
            raise ValueError(f"Mask requires dtype=bool, got {self.dtype}")


class Label(CompositeData):
    """Label image with raster and/or polygon representation."""

    expected_slots: ClassVar[dict[str, type]] = {
        "raster": Array,
        "polygons": DataFrame,
    }

    class Meta(BaseModel):
        """Per-instance label-image metadata."""

        # ADR-043 / spec adr-043-package-migration FR-007: ``ome`` is added
        # explicitly here because ``Label.Meta`` inherits from
        # :class:`pydantic.BaseModel` directly (sibling of ``Image.Meta``,
        # not subclass). The field carries the source ``Image``'s OME
        # metadata across shape-preserving cross-type derivations (FR-009
        # Mode C, e.g. segmentation: ``Image → Label``).
        model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
        source_file: str | None = None
        n_objects: int | None = None
        ome: OME | None = None

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._validate_label_slots()

    @property
    def slots(self) -> dict[str, Any]:
        """Expose populated composite slots for downstream blocks/tests."""
        return self._slots

    def _validate_label_slots(self) -> None:
        """Enforce at least one of ``raster`` / ``polygons`` is set."""
        if self._slots.get("raster") is None and self._slots.get("polygons") is None:
            raise ValueError("Label requires at least one of raster or polygons to be non-None")


class Transform(Array):
    """Affine transform matrix."""

    required_axes: ClassVar[frozenset[str]] = frozenset({"row", "col"})
    allowed_axes: ClassVar[frozenset[str] | None] = frozenset({"row", "col"})
    canonical_order: ClassVar[tuple[str, ...]] = ("row", "col")

    class Meta(BaseModel):
        """Per-instance transform metadata."""

        model_config = ConfigDict(frozen=True)
        transform_type: str
        reference_shape: tuple[int, ...] | None = None

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._validate_transform_shape()

    def _validate_transform_shape(self) -> None:
        if self.shape is None:
            return
        if self.shape not in {(2, 3), (3, 3)}:
            raise ValueError(f"Transform shape must be (2, 3) or (3, 3), got {self.shape}")


__all__ = ["Image", "Label", "Mask", "Transform"]
