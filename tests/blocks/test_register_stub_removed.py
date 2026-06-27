"""Regression test for T-TRK-002: confirm the register stub is not exported.

The Phase 11 master plan §2.5 sub-1a + standards doc §9.1 T-TRK-002 deleted
``src/scistudio/blocks/process/builtins/register.py`` because it was a 1-line
docstring placeholder with no class body. Image registration belongs in
``scistudio-blocks-imaging`` (T-IMG-027/028/029 per the imaging spec); the core
``process/builtins/`` directory is reserved for plain DataObject collection
ops.

This test guards against accidental re-export of a register stub from the
``process/builtins`` package ``__init__`` during the Phase 11 plugin cascade.

NOTE on scope: this file is added under universal rule §6.10 (doc-external
changes restricted, but permitted when tests reveal missing things) to
satisfy the ``Verify Workflow Compliance`` CI gate which requires every
``src/`` change to be paired with a ``tests/`` change. The standards doc
T-TRK-002 §f originally said "New tests: none", but the CI gate makes a
single-line regression test strictly necessary. Called out in the PR body
per §6.10.
"""

from __future__ import annotations

import importlib

import scistudio.blocks.process.builtins as builtins_pkg


def test_builtins_init_does_not_export_register_block() -> None:
    """``process/builtins/__init__.py`` must not re-export a RegisterBlock symbol."""
    exported = getattr(builtins_pkg, "__all__", [])
    assert "RegisterBlock" not in exported, (
        "process/builtins/__init__.py must not export RegisterBlock after T-TRK-002."
    )
    assert "register" not in exported, (
        "process/builtins/__init__.py must not export the deleted `register` submodule name after T-TRK-002."
    )
    assert not hasattr(builtins_pkg, "RegisterBlock"), (
        "process/builtins/__init__.py must not import RegisterBlock after T-TRK-002."
    )


def test_builtins_init_only_exports_collection_ops() -> None:
    """``__all__`` is the current built-in process block set — no RegisterBlock.

    #1781: the collection filter/slice/split blocks were retired (superseded by
    the interactive DataRouter); MergeCollection remains. MergeBlock/SplitBlock
    are DataFrame-level placeholders kept importable but out of the palette.
    """
    expected = {
        "DataRouter",
        "MergeBlock",
        "MergeCollection",
        "PairEditor",
        "SplitBlock",
    }
    actual = set(getattr(builtins_pkg, "__all__", []))
    assert "RegisterBlock" not in actual
    # The retired collection blocks must not reappear.
    assert "FilterCollection" not in actual
    assert "SliceCollection" not in actual
    assert "SplitCollection" not in actual
    assert actual == expected, f"Expected __all__ == {expected}; got {actual}"
    # Importable check — these names should resolve on the package.
    for name in expected:
        assert hasattr(builtins_pkg, name), f"{name} missing from builtins package"

    # Reload to be defensive against test ordering.
    importlib.reload(builtins_pkg)
