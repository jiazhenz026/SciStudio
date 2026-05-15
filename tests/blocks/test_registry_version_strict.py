"""Tests for ADR-038 §3.3 strict version-resolution behaviour (D38-3.2).

Closes audit D38-3.1a P1-2: ``_resolve_distribution_version`` previously
returned the historical ``"unknown"`` fallback when no distribution could
be found. ADR §3.3 mandates this fails loudly so every lineage row
carries a real version for reproducibility.
"""

from __future__ import annotations

import pytest

from scieasy.blocks.base.block import Block
from scieasy.blocks.registry import (
    BlockRegistrationError,
    _resolve_distribution_version,
)


def _make_block_with_module(module_name: str) -> type:
    cls = type(
        "TestBlock",
        (Block,),
        {
            "name": "TestBlock",
            "description": "test",
            "input_ports": [],
            "output_ports": [],
            "config_schema": {"type": "object", "properties": {}},
            "run": lambda self, inputs, config: {},
        },
    )
    cls.__module__ = module_name
    return cls


class TestStrictVersionResolution:
    def test_scieasy_namespace_returns_scieasy_version(self) -> None:
        from scieasy import __version__ as scieasy_version

        cls = _make_block_with_module("scieasy.blocks.io.loaders.load_data")
        assert _resolve_distribution_version(cls) == str(scieasy_version)

    def test_dropin_synthetic_module_returns_scieasy_version(self) -> None:
        from scieasy import __version__ as scieasy_version

        cls = _make_block_with_module("_scieasy_dropin_my_block_1234567890")
        assert _resolve_distribution_version(cls) == str(scieasy_version)

    def test_unknown_module_raises_block_registration_error(self) -> None:
        """ADR §3.3: removing the ``"unknown"`` default — raise loudly."""
        cls = _make_block_with_module("totally_unknown_namespace_xyz")

        with pytest.raises(BlockRegistrationError, match="cannot resolve distribution version"):
            _resolve_distribution_version(cls)

    def test_empty_module_name_raises(self) -> None:
        """A class with no ``__module__`` cannot be resolved either."""
        cls = _make_block_with_module("")
        with pytest.raises(BlockRegistrationError):
            _resolve_distribution_version(cls)
