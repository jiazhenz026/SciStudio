"""Minimal sanity checks for the fixture package's own surface.

These run as part of the core test session (the fixture src is on sys.path
via tests/conftest.py) and only assert the fixture exposes the factories
and types the core machinery tests rely on.
"""

from __future__ import annotations


def test_factories_expose_expected_shape() -> None:
    import scistudio_blocks_fixture as pkg

    info, blocks = pkg.get_block_package()
    assert info.name == "scistudio-blocks-fixture"
    assert pkg.LoadImageFixture in blocks
    assert pkg.SaveDataFixture in blocks
    assert pkg.FixtureNoop in blocks

    types = pkg.get_types()
    assert {t.__name__ for t in types} == {"Image", "Mask", "Label"}

    specs = pkg.get_previewers()
    assert {s.previewer_id for s in specs} == {"fixture.image.viewer", "fixture.label.viewer"}


def test_image_constructs_from_ndim() -> None:
    from scistudio_blocks_fixture.types import Image

    img = Image(shape=(5, 5), ndim=2, dtype="uint8")
    assert img.axes == ["y", "x"]
    assert img.shape == (5, 5)
