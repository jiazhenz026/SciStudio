"""Trivial fixture DataObject subtypes mirroring a real domain package.

These types carry ZERO scientific behaviour. They exist only so core
machinery tests (serialization round-trip, registry/type discovery, IO
capability dispatch, previewer routing, port typing) have a stand-in
plugin type to exercise instead of the now-decoupled domain packages
(imaging / lcms / spectroscopy / srs).

Structure mirrors a real domain package's ``types.py`` (e.g. the standalone
``scistudio-blocks-imaging`` package):

* :class:`Image` — an ``Array`` subtype (the imaging ``Image`` analogue).
* :class:`Mask` — a boolean ``Array`` subtype.
* :class:`Label` — a ``CompositeData`` subtype with a ``raster`` slot.

The only deliberate divergence from the real imaging ``Image`` is a
lenient ``__init__`` that synthesises default ``axes`` from ``ndim`` /
``shape`` when ``axes`` is omitted, so terse fixture call sites such as
``Image(shape=(5, 5), ndim=2, dtype="uint8")`` construct without having
to spell out ``axes=["y", "x"]`` every time.
"""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
from pydantic import BaseModel, ConfigDict

from scistudio.core.types.array import Array
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame


class Image(Array):
    """Fixture image type — a general 2D-to-6D ``Array`` stand-in."""

    required_axes: ClassVar[frozenset[str]] = frozenset({"y", "x"})
    allowed_axes: ClassVar[frozenset[str] | None] = frozenset({"t", "z", "c", "lambda", "y", "x"})
    canonical_order: ClassVar[tuple[str, ...]] = ("t", "z", "c", "lambda", "y", "x")

    class Meta(BaseModel):
        """Per-instance fixture image metadata."""

        model_config = ConfigDict(frozen=True)
        source_file: str | None = None

    @staticmethod
    def _default_axes(ndim: int) -> list[str]:
        if ndim == 2:
            return ["y", "x"]
        if ndim == 3:
            return ["c", "y", "x"]
        if ndim == 4:
            return ["t", "c", "y", "x"]
        if ndim == 5:
            return ["t", "z", "c", "y", "x"]
        if ndim == 6:
            return ["t", "z", "c", "lambda", "y", "x"]
        raise ValueError(f"Image: cannot infer default axes for ndim={ndim}")

    def __init__(self, *, axes: list[str] | None = None, shape: tuple[int, ...] | None = None, **kwargs: Any) -> None:
        if axes is None:
            ndim = kwargs.pop("ndim", None)
            if ndim is None and shape is not None:
                ndim = len(shape)
            if ndim is None:
                raise ValueError("Image requires either axes, shape, or ndim")
            axes = self._default_axes(int(ndim))
        else:
            kwargs.pop("ndim", None)
        super().__init__(axes=axes, shape=shape, **kwargs)


class Mask(Image):
    """Fixture boolean mask. Enforces ``dtype=bool`` at construction."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if self.dtype is not None and np.dtype(self.dtype) != np.dtype(bool):
            raise ValueError(f"Mask requires dtype=bool, got {self.dtype}")


class Label(CompositeData):
    """Fixture label type — a ``CompositeData`` with a ``raster`` slot."""

    expected_slots: ClassVar[dict[str, type]] = {
        "raster": Array,
        "polygons": DataFrame,
    }

    class Meta(BaseModel):
        """Per-instance fixture label metadata."""

        model_config = ConfigDict(frozen=True)
        source_file: str | None = None
        n_objects: int | None = None

    @property
    def slots(self) -> dict[str, Any]:
        """Expose populated composite slots for downstream blocks/tests."""
        return self._slots


__all__ = ["Image", "Label", "Mask"]
