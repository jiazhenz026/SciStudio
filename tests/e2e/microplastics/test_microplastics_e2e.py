"""Phase 5 end-to-end acceptance test — scaffold stub.

This module is a placeholder created by T-ECA-501. It exists solely to
verify that the ``e2e`` pytest marker collects correctly and that the
default test run excludes it.

The real test body — driving the SciEasy embedded coding agent through
the microplastics SRS spectrum-extraction notebook reproduction — will
be written by:

- T-ECA-502 — test harness (Chrome automation, backend lifecycle,
  transcript capture).
- T-ECA-503 — golden reference outputs.
- T-ECA-505 — the test logic that compares run outputs against goldens
  within tolerance.

See ``docs/specs/embedded-coding-agent-spec.md`` §8.5 for the full
contract.
"""

from __future__ import annotations

import pytest


@pytest.mark.e2e
@pytest.mark.skip(
    reason=(
        "Scaffold stub from T-ECA-501. The real microplastics e2e test is "
        "implemented by T-ECA-502 (harness), T-ECA-503 (goldens), and "
        "T-ECA-505 (test logic). This stub exists only to verify pytest "
        "collection of the `e2e` marker."
    )
)
def test_microplastics_e2e_scaffold() -> None:
    """Placeholder; intentionally skipped until T-ECA-505 lands."""
    # No body — the @pytest.mark.skip decorator prevents execution.
    raise AssertionError("Unreachable: this test is marked skip.")
