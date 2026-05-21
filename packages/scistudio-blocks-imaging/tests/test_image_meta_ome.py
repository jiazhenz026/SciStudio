"""ADR-043 / FR-006, FR-007 — Image.Meta.ome / Label.Meta.ome round-trip tests.

Per spec adr-043-package-migration:

- FR-006: ``Image.Meta`` gains ``ome: ome_types.model.OME | None = None``.
  Field must be readable/writable via construction and via
  :meth:`Image.with_meta`.
- FR-007: ``Label.Meta`` gains the same field. Label.Meta inherits
  :class:`pydantic.BaseModel` directly (not Image.Meta), so the field
  is added explicitly.
- Cross-package inheritance: ``SRSImage.Meta`` inherits ``Image.Meta``
  via ``class Meta(Image.Meta)``, so it automatically picks up the new
  ``ome`` field. This is exercised in
  :func:`test_srsimage_meta_inherits_ome_field`.
"""

from __future__ import annotations

import numpy as np
import pytest
from ome_types.model import OME, Pixels, PixelType
from ome_types.model import Image as OMEImage
from scistudio_blocks_imaging.types import Image, Label

from scistudio.core.types.array import Array


def _make_ome(physical_size_x: float = 0.5, size_x: int = 10, size_y: int = 20) -> OME:
    """Build a minimal OME structure for testing."""
    return OME(
        images=[
            OMEImage(
                pixels=Pixels(
                    size_x=size_x,
                    size_y=size_y,
                    size_c=1,
                    size_z=1,
                    size_t=1,
                    dimension_order="XYCZT",
                    type=PixelType.UINT8,
                    physical_size_x=physical_size_x,
                    physical_size_y=physical_size_x,
                )
            )
        ]
    )


# ---------------------------------------------------------------------------
# FR-006: Image.Meta.ome field
# ---------------------------------------------------------------------------


def test_image_meta_accepts_ome_field() -> None:
    """``Image.Meta`` accepts an OME object via construction."""
    ome = _make_ome()
    meta = Image.Meta(ome=ome)
    assert meta.ome is ome
    assert meta.ome.images[0].pixels.physical_size_x == 0.5


def test_image_meta_ome_defaults_to_none() -> None:
    """``Image.Meta()`` (no args) leaves ``ome`` as None — backward compat."""
    meta = Image.Meta()
    assert meta.ome is None
    # Other existing fields still default to None too.
    assert meta.pixel_size is None
    assert meta.source_file is None


def test_image_meta_ome_roundtrip_via_model_dump() -> None:
    """``Image.Meta.model_dump()`` and reconstruction preserve ``ome`` payload."""
    ome = _make_ome(physical_size_x=0.42)
    meta = Image.Meta(ome=ome)
    dumped = meta.model_dump()
    assert "ome" in dumped
    # Round-trip via construction (validates the field is round-trippable).
    meta2 = Image.Meta.model_validate(dumped)
    assert meta2.ome is not None
    assert meta2.ome.images[0].pixels.physical_size_x == pytest.approx(0.42)


def test_image_construction_carries_ome() -> None:
    """An :class:`Image` constructed with ``Meta(ome=...)`` exposes it."""
    ome = _make_ome()
    img = Image(axes=["y", "x"], shape=(20, 10), dtype="uint8", meta=Image.Meta(ome=ome))
    assert img.meta is not None
    assert img.meta.ome is ome


def test_image_with_meta_propagates_ome() -> None:
    """``Image.with_meta`` preserves the ``ome`` field across the immutable update.

    Spec FR-006 acceptance: ``Image.with_meta(ome=...)`` must work.
    """
    img = Image(axes=["y", "x"], shape=(20, 10), dtype="uint8", meta=Image.Meta())
    assert img.meta.ome is None
    ome = _make_ome()
    img2 = img.with_meta(ome=ome)
    assert img2.meta is not None
    assert img2.meta.ome is ome
    # Original is unchanged (frozen / immutable update contract).
    assert img.meta.ome is None


def test_image_with_meta_preserves_pre_existing_ome_when_updating_other_fields() -> None:
    """When updating an unrelated field via ``with_meta``, ``ome`` survives."""
    ome = _make_ome()
    img = Image(
        axes=["y", "x"],
        shape=(20, 10),
        dtype="uint8",
        meta=Image.Meta(ome=ome, source_file="orig.tif"),
    )
    img2 = img.with_meta(source_file="new.tif")
    assert img2.meta is not None
    assert img2.meta.source_file == "new.tif"
    # ome propagated by ``with_meta``'s "all fields preserved unless overridden"
    # contract.
    assert img2.meta.ome is ome


# ---------------------------------------------------------------------------
# FR-007: Label.Meta.ome field
# ---------------------------------------------------------------------------


def test_label_meta_accepts_ome_field() -> None:
    """``Label.Meta`` accepts an OME object via construction.

    FR-007 explicit addition: Label.Meta inherits BaseModel directly
    (not Image.Meta), so this test ensures the field was added in the
    right class body.
    """
    ome = _make_ome()
    meta = Label.Meta(ome=ome)
    assert meta.ome is ome


def test_label_meta_ome_defaults_to_none() -> None:
    meta = Label.Meta()
    assert meta.ome is None
    assert meta.source_file is None
    assert meta.n_objects is None


def test_label_meta_ome_roundtrip_via_model_dump() -> None:
    ome = _make_ome(physical_size_x=0.3)
    meta = Label.Meta(ome=ome)
    dumped = meta.model_dump()
    assert "ome" in dumped
    meta2 = Label.Meta.model_validate(dumped)
    assert meta2.ome is not None
    assert meta2.ome.images[0].pixels.physical_size_x == pytest.approx(0.3)


def test_label_meta_inheritance_chain() -> None:
    """Label.Meta is a sibling of Image.Meta (both BaseModel subclasses);
    Label.Meta does NOT inherit from Image.Meta."""
    from pydantic import BaseModel

    assert issubclass(Label.Meta, BaseModel)
    # Label.Meta MUST NOT be a subclass of Image.Meta (per spec FR-007:
    # current code has Label.Meta sibling to Image.Meta; this test pins
    # that fact so future refactors don't silently collapse them).
    assert not issubclass(Label.Meta, Image.Meta)


# ---------------------------------------------------------------------------
# Cross-package: SRSImage.Meta inherits the new ome field automatically.
# ---------------------------------------------------------------------------


def test_srsimage_meta_inherits_ome_field() -> None:
    """``SRSImage.Meta`` inherits ``Image.Meta`` via ``class Meta(Image.Meta)``
    so it automatically picks up the new ``ome`` field — no SRS-package
    change required.

    Skipped when the SRS package isn't installed/importable.
    """
    srs_types = pytest.importorskip("scistudio_blocks_srs.types")
    SRSImage = srs_types.SRSImage  # noqa: N806 — re-exposing class identity, name follows class

    # Pin the inheritance chain.
    assert issubclass(SRSImage.Meta, Image.Meta), (
        "SRSImage.Meta must inherit Image.Meta so ADR-043 typed Meta additions propagate automatically."
    )

    # Verify the field is available on the SRS subclass.
    ome = _make_ome()
    meta = SRSImage.Meta(ome=ome)
    assert meta.ome is ome


# ---------------------------------------------------------------------------
# Pydantic edge cases / typed-meta-fields integration.
# ---------------------------------------------------------------------------


def test_image_meta_class_is_subclass_of_array_base_meta_pattern() -> None:
    """Image.Meta remains a pydantic BaseModel and is reachable via the
    Image type. This guards against accidental Meta-class removal."""
    from pydantic import BaseModel

    assert isinstance(Image.Meta, type)
    assert issubclass(Image.Meta, BaseModel)
    # Image's MRO includes Array (so existing Array.Meta machinery still works).
    assert Array in Image.__mro__


def test_image_meta_ome_field_is_declared_in_model_fields() -> None:
    """Pydantic's model_fields includes the new ``ome`` entry — used by
    the registry / capability fidelity validation
    (``MetadataFidelity.validate_typed_meta_fields``)."""
    assert "ome" in Image.Meta.model_fields
    assert "ome" in Label.Meta.model_fields


def test_image_meta_ome_accepts_none_explicitly() -> None:
    """Explicit ``ome=None`` is accepted (frozen-model edge case)."""
    meta = Image.Meta(ome=None)
    assert meta.ome is None


def test_numpy_data_roundtrip_does_not_disturb_ome() -> None:
    """Synthesizing data and reading back via ``Image`` keeps ``ome`` intact."""
    ome = _make_ome()
    arr = np.zeros((20, 10), dtype=np.uint8)
    img = Image(axes=["y", "x"], shape=arr.shape, dtype="uint8", meta=Image.Meta(ome=ome))
    img._data = arr  # type: ignore[attr-defined]
    assert img.meta.ome.images[0].pixels.physical_size_x == 0.5
