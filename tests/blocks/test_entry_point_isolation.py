"""Regression tests for test-session entry-point isolation (#1933).

``tests/conftest.py`` neutralizes the ambient ``scistudio.blocks`` entry-point
group so the suite behaves like a clean, core-only install regardless of stale
editable ``*.dist-info`` metadata or locally-installed domain packages leaking
their entry points into the interpreter. Core registers its first-party palette
in ``_scan_builtins``; the ``scistudio.blocks`` group is reserved for
third-party plugins (``BlockRegistry._scan_tier2`` / ADR-025), so a clean
install exposes zero entries. These tests lock that isolation in.
"""

from __future__ import annotations

import importlib.metadata
from unittest.mock import MagicMock, patch

from scistudio.blocks.registry import BlockRegistry

_ISOLATED_GROUP = "scistudio.blocks"


def _select(group: str) -> list:
    eps = importlib.metadata.entry_points()
    if hasattr(eps, "select"):
        return list(eps.select(group=group))
    return list(eps.get(group, []))  # pragma: no cover - Python < 3.10 fallback


def _make_mock_block_class(name: str) -> type:
    """A minimal ``Block`` subclass stamped under the ``scistudio.*`` namespace.

    Mirrors ``tests/blocks/test_registry.py`` so distribution-version resolution
    reads ``scistudio.__version__`` instead of raising.
    """
    from scistudio.blocks.base.block import Block

    cls = type(
        name,
        (Block,),
        {
            "name": name,
            "description": f"Mock {name}",
            "version": "0.1.0",
            "input_ports": [],
            "output_ports": [],
            "config_schema": {"type": "object", "properties": {}},
            "run": lambda self, inputs, config: {},
        },
    )
    cls.__module__ = "scistudio.blocks._mock_for_entry_point_isolation_tests"
    return cls


def test_ambient_scistudio_blocks_group_is_isolated() -> None:
    """The session must expose zero ambient ``scistudio.blocks`` entry points.

    Fails without the conftest isolation whenever a stale editable
    ``*.dist-info`` or a locally-installed domain package leaks entries into the
    interpreter — the exact condition that breaks registry tests locally while
    CI stays green.
    """
    assert _select(_ISOLATED_GROUP) == []


def test_group_kwarg_form_is_also_isolated() -> None:
    """``entry_points(group=...)`` is isolated too, not only the no-arg +
    ``.select`` path that ``_scan_tier2`` uses."""
    assert list(importlib.metadata.entry_points(group=_ISOLATED_GROUP)) == []


def test_other_entry_point_groups_are_preserved() -> None:
    """Isolation is surgical: only ``scistudio.blocks`` is removed. Other groups
    (here ``console_scripts``, always populated by pytest/coverage) pass
    through untouched."""
    assert _select("console_scripts"), "unrelated entry-point groups must be preserved"


def test_default_scan_has_no_retired_collection_blocks() -> None:
    """Integration guard: a default scan never resurrects retired collection
    blocks from leaked or stale ``scistudio.blocks`` entries (#1781)."""
    reg = BlockRegistry()
    reg.scan()
    names = set(reg.all_specs())
    for retired in ("Filter Collection", "Slice Collection", "Split Collection"):
        assert retired not in names, f"{retired!r} leaked back into the palette: {sorted(names)}"
    # Sanity: the genuine first-party palette is still present.
    for expected in ("Load", "Save", "Data Router", "Merge Collection", "Pair Editor"):
        assert expected in names, f"{expected!r} missing from palette: {sorted(names)}"


def test_per_test_injection_still_overrides_isolation() -> None:
    """Tier 2 tests inject their own entry points by patching
    ``importlib.metadata.entry_points``; ``mock.patch`` restores the isolation
    wrapper afterwards, so per-test injection is unaffected by the session-wide
    filter."""
    block_cls = _make_mock_block_class("InjectedIsolationBlock")

    ep = MagicMock()
    ep.name = "injected"
    ep.value = "mock_module:injected"
    ep.load.return_value = [block_cls]
    mock_eps = MagicMock()
    mock_eps.select.return_value = [ep]

    reg = BlockRegistry()
    with patch("importlib.metadata.entry_points", return_value=mock_eps):
        reg._scan_tier2()

    assert reg.get_spec("InjectedIsolationBlock") is not None

    # After the patch exits, the isolation wrapper is back in force.
    assert _select(_ISOLATED_GROUP) == []
