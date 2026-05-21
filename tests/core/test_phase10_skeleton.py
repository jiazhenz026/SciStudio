"""Smoke tests for the Phase 10 skeleton files (PR #261).

These tests guard the contract documented in
``docs/specs/phase10-implementation-standards.md``:

1. Every skeleton module is importable at module-load time.
2. Every public name is exposed as documented.
3. Calling any placeholder method raises ``NotImplementedError`` with a
   message that cites the implementing ticket so future agents can find
   the right place to fill in.

When a follow-up ticket (T-003 / T-004 / T-010 / T-011) lands its
implementation, that ticket must REPLACE these smoke assertions with the
real per-feature tests listed in the standards doc. This file is
explicitly a temporary scaffold — the standards doc names the
replacement test files (e.g. ``tests/core/test_units.py`` for T-003).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# T-003 / ADR-027 D6 + Addendum 1 §4 — PhysicalQuantity
#
# The PhysicalQuantity skeleton smoke tests that previously lived here
# were removed when T-003 landed its real implementation. See
# ``tests/core/test_units.py`` for the replacement test suite.
# ``test_all_skeletons_co_importable`` below still imports
# ``PhysicalQuantity`` so the cross-skeleton check remains meaningful.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# T-004 / ADR-027 D5 — FrameworkMeta + scistudio.core.meta module
#
# T-004 has landed; the smoke tests that lived here have been replaced by
# the real per-feature suite in ``tests/core/test_framework_meta.py``.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# T-010 / ADR-027 D4 companion — scistudio.utils.constraints
#
# T-010 has landed; the smoke tests that lived here have been replaced by
# the real per-feature suite in ``tests/utils/test_constraints.py``. The
# cross-skeleton co-import check below still exercises the constraints
# module's public surface.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# T-011 / ADR-027 D3 — scistudio.utils.axis_iter.iterate_over_axes
#
# T-011 has landed; the smoke tests that lived here have been replaced by
# the real per-feature suite in ``tests/utils/test_axis_iter.py``. The
# cross-skeleton co-import check below still exercises the axis_iter
# module's public surface.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Cross-skeleton contract checks
# ---------------------------------------------------------------------------


def test_all_skeletons_co_importable() -> None:
    """The PR description claims all 5 skeletons import together
    cleanly. Guard that claim. T-004 has landed, so the
    ``scistudio.core.meta`` symbols (``FrameworkMeta``, ``ChannelInfo``,
    ``with_meta_changes``) are real implementations rather than
    placeholders, but the import-surface contract still applies."""
    from scistudio.core.meta import ChannelInfo, FrameworkMeta, with_meta_changes
    from scistudio.core.meta.framework import FrameworkMeta as FrameworkMetaDirect
    from scistudio.core.units import PhysicalQuantity
    from scistudio.utils.axis_iter import iterate_over_axes
    from scistudio.utils.constraints import has_axes, has_exact_axes, has_shape

    assert FrameworkMeta is FrameworkMetaDirect
    assert PhysicalQuantity is not None
    assert ChannelInfo is not None
    assert callable(with_meta_changes)
    assert callable(iterate_over_axes)
    assert callable(has_axes)
    assert callable(has_exact_axes)
    assert callable(has_shape)
