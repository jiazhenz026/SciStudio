"""Issue #1306 regression — LoadImage parses OME-TIFF ``ImageDescription``.

ADR-043 FR-004 / FR-006: the
``scistudio-blocks-imaging.image.tiff.load`` capability advertises
``format_metadata_reads=("ome",)``. ``_load_tiff`` must call
``tifffile.TiffFile.ome_metadata`` / ``is_ome`` and populate
``Image.Meta.ome`` so the contract holds end-to-end.

These tests differ from ``test_format_capabilities.py``'s SC-003 test in
two ways:

1. They write the OME-TIFF directly with ``tifffile.imwrite(...,
   description=<ome_xml>)`` rather than going through ``SaveImage``, so
   the load path is exercised on an externally-authored OME-TIFF (e.g.
   a microscope export). This is the scenario #1306 describes.
2. They also exercise the negative branch — a plain TIFF returns
   ``meta.ome is None`` so the fix does not invent metadata where none
   exists (#1306 §Acceptance.2).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from scistudio_blocks_imaging.io.load_image import LoadImage
from scistudio_blocks_imaging.types import Image

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection


def _ome_xml_round_trip_available() -> bool:
    """Probe whether ``ome_types.to_xml`` + ``from_xml`` work in this env.

    Mirrors the guard in ``test_format_capabilities`` — Python 3.14 +
    older xsdata releases have a known serialization bug. CI runs on
    Python 3.11/3.13 where the round-trip works.
    """
    try:
        from ome_types import from_xml, to_xml
        from ome_types.model import OME, Pixels, PixelType
        from ome_types.model import Image as OMEImage
    except Exception:
        return False
    try:
        sample = OME(
            images=[
                OMEImage(
                    pixels=Pixels(
                        size_x=4,
                        size_y=3,
                        size_c=1,
                        size_z=1,
                        size_t=1,
                        dimension_order="XYCZT",
                        type=PixelType.UINT16,
                        physical_size_x=0.5,
                        physical_size_y=0.7,
                    )
                )
            ]
        )
        xml = to_xml(sample)
        recovered = from_xml(xml)
    except Exception:
        return False
    return bool(getattr(recovered, "images", None))


def _write_ome_tiff(path: Path, arr: np.ndarray, *, physical_size_x: float, physical_size_y: float) -> str:
    """Write an OME-TIFF with an explicit OME-XML ``ImageDescription``.

    Uses :func:`tifffile.imwrite`'s ``description=`` kwarg so tifffile
    treats the tag as OME-XML on read (``TiffFile.is_ome`` becomes True
    and ``TiffFile.ome_metadata`` returns the XML).

    Returns the serialized OME-XML string for assertion convenience.
    """
    import tifffile
    from ome_types import to_xml
    from ome_types.model import OME, Pixels, PixelType
    from ome_types.model import Image as OMEImage

    ome = OME(
        images=[
            OMEImage(
                pixels=Pixels(
                    size_x=arr.shape[1],
                    size_y=arr.shape[0],
                    size_c=1,
                    size_z=1,
                    size_t=1,
                    dimension_order="XYCZT",
                    type=PixelType.UINT16,
                    physical_size_x=physical_size_x,
                    physical_size_y=physical_size_y,
                )
            )
        ]
    )
    xml = to_xml(ome)
    tifffile.imwrite(str(path), arr, description=xml)
    return xml


def test_issue_1306_load_image_parses_ome_xml_from_image_description(tmp_path: Path) -> None:
    """#1306 / ADR-043 FR-004 + FR-006: an OME-TIFF authored externally
    (here via ``tifffile.imwrite(description=ome_xml)``) round-trips
    through ``LoadImage`` so ``Image.Meta.ome`` carries the source
    physical pixel sizes.

    Asserts ``image.meta.ome.images[0].pixels.physical_size_x`` matches
    the source per the issue's Acceptance §1 + §4.
    """
    if not _ome_xml_round_trip_available():
        pytest.skip(
            "ome_types.to_xml/from_xml round-trip is unavailable in this Python "
            "environment (known xsdata bug on Python 3.14); CI on 3.11/3.13 "
            "exercises this test path."
        )

    physical_size_x = 0.42
    physical_size_y = 0.84
    arr = np.arange(12, dtype=np.uint16).reshape(3, 4)
    out_path = tmp_path / "fixture.ome.tif"
    _write_ome_tiff(
        out_path,
        arr,
        physical_size_x=physical_size_x,
        physical_size_y=physical_size_y,
    )

    # Sanity: tifffile sees the tag as OME-XML (i.e. our fixture is
    # actually an OME-TIFF, not a plain TIFF).
    import tifffile

    with tifffile.TiffFile(str(out_path)) as tf:
        assert tf.is_ome, "fixture is not detected as OME-TIFF by tifffile.is_ome"
        assert tf.ome_metadata, "tifffile.ome_metadata is empty on the fixture"

    loaded = LoadImage().load(BlockConfig(params={"path": str(out_path)}))
    assert isinstance(loaded, Collection)
    image = loaded[0]
    assert isinstance(image, Image)

    assert image.meta is not None, "LoadImage produced an Image without Meta"
    assert image.meta.ome is not None, (
        "LoadImage did not parse OME-XML from ImageDescription "
        "(#1306 regression — capability advertises format_metadata_reads=ome)"
    )
    assert image.meta.ome.images, "Parsed OME has no images entry"
    pixels = image.meta.ome.images[0].pixels
    assert pixels.physical_size_x == pytest.approx(physical_size_x), (
        f"physical_size_x lost across OME-TIFF load: source={physical_size_x}, loaded={pixels.physical_size_x}"
    )
    assert pixels.physical_size_y == pytest.approx(physical_size_y), (
        f"physical_size_y lost across OME-TIFF load: source={physical_size_y}, loaded={pixels.physical_size_y}"
    )


def test_issue_1306_load_image_plain_tiff_returns_meta_ome_none(tmp_path: Path) -> None:
    """#1306 §Acceptance.2: plain TIFF (no OME-XML) returns
    ``meta.ome is None`` — the fix must not invent metadata where the
    source has none.
    """
    import tifffile

    arr = np.arange(12, dtype=np.uint16).reshape(3, 4)
    out_path = tmp_path / "plain.tif"
    # No ``description`` kwarg → no OME-XML in ImageDescription.
    tifffile.imwrite(str(out_path), arr)

    with tifffile.TiffFile(str(out_path)) as tf:
        # tifffile only auto-detects OME when an OME-XML header is
        # actually present; a vanilla imwrite produces a plain TIFF.
        assert not tf.is_ome, "fixture is unexpectedly tagged as OME-TIFF"

    loaded = LoadImage().load(BlockConfig(params={"path": str(out_path)}))
    image = loaded[0]
    assert image.meta is not None
    assert image.meta.ome is None, (
        "LoadImage populated Image.Meta.ome on a plain TIFF — the fix "
        "must not invent OME metadata where the source carries none."
    )
    # Source-file provenance is still set (pre-existing behaviour).
    assert image.meta.source_file == str(out_path)


def test_issue_1306_load_image_malformed_ome_xml_falls_back_to_none(tmp_path: Path) -> None:
    """#1306 defensive: ``_ome_from_tiff`` already swallows OME parse
    failures (returns ``None``) so a malformed OME-XML payload does not
    take down the entire load. Pin that behaviour so a future refactor
    cannot regress it.
    """
    import tifffile

    arr = np.arange(12, dtype=np.uint16).reshape(3, 4)
    out_path = tmp_path / "broken.ome.tif"
    # Description starts with the OME namespace so tifffile flags it as
    # OME-TIFF, but the body is incomplete XML → ome_types.from_xml fails.
    broken_xml = '<?xml version="1.0"?><OME xmlns="http://www.openmicroscopy.org/Schemas/OME/2016-06"><BrokenTag>'
    tifffile.imwrite(str(out_path), arr, description=broken_xml)

    # LoadImage must not raise — resilient fallback to meta.ome=None.
    loaded = LoadImage().load(BlockConfig(params={"path": str(out_path)}))
    image = loaded[0]
    assert image.meta is not None
    assert image.meta.ome is None
