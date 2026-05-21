"""Public testing utilities for SciStudio block developers.

This module provides :class:`BlockTestHarness`, a test helper that
validates block contracts and supports smoke-test execution without
boilerplate setup.  See ADR-026 for design rationale.

Usage::

    from scistudio.testing import BlockTestHarness

    harness = BlockTestHarness(MyBlock)
    errors = harness.validate_block()
    assert not errors

    result = harness.smoke_test(inputs={"input": some_collection})
    assert "output" in result
"""

from __future__ import annotations

from scistudio.testing.harness import BlockTestHarness

__all__ = ["BlockTestHarness"]
