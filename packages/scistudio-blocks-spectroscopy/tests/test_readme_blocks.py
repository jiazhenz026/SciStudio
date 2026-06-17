"""README/code consistency: the README block table must not drift from the
registered block roster."""

from __future__ import annotations

from pathlib import Path

import scistudio_blocks_spectroscopy as pkg

_README = Path(__file__).resolve().parents[1] / "README.md"


def test_readme_lists_every_registered_block() -> None:
    """Every registered block class name appears in the README, and the README
    introduces no block name that is not registered."""
    _info, blocks = pkg.get_block_package()
    registered = {cls.__name__ for cls in blocks}
    assert len(registered) == 26

    readme = _README.read_text(encoding="utf-8")
    for name in registered:
        assert name in readme, f"README does not document registered block {name!r}"


def test_readme_documents_both_types() -> None:
    readme = _README.read_text(encoding="utf-8")
    assert "Spectrum(Series)" in readme
    assert "SpectralDataset(CompositeData)" in readme
