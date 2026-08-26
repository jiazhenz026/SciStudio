"""The API wait budgets must stay under pytest-timeout's per-test kill (#2186).

`tests/api/helpers.py` polls for a condition and gives up after a budget. That
budget is a *failure-detection* bound: the poll returns the instant its
condition holds, so a generous one costs nothing when things work and only
changes how long a genuine hang takes to report.

There is a ceiling, though, and it is not obvious from the helper. pytest-timeout
hard-kills any single test at `timeout = 60` (pyproject.toml, the ADR-040
preflight that exists for Windows subprocess/asyncio hangs). A helper budget at
or above that can never elapse: the test dies first and reports a thread dump
instead of a clean assertion, which is strictly harder to read than the failure
it was meant to replace.

So the two numbers are coupled, in opposite directions, with nothing linking
them in code. This test is the link. It is here rather than in the helper
because raising the budget is the natural response to a flaky wait, and the
ceiling is the thing the person doing it will not think to check.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from tests.api.helpers import STEP_TIMEOUT, WORKFLOW_TIMEOUT

REPO_ROOT = Path(__file__).resolve().parents[2]

# Setup, teardown and the assertions around the wait all share the per-test
# budget, so the wait cannot be allowed to consume it entirely.
HEADROOM_SECONDS = 10.0


def _per_test_timeout() -> float:
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    timeout = config["tool"]["pytest"]["ini_options"]["timeout"]
    return float(timeout)


@pytest.mark.parametrize(
    ("name", "budget"),
    [("WORKFLOW_TIMEOUT", WORKFLOW_TIMEOUT), ("STEP_TIMEOUT", STEP_TIMEOUT)],
)
def test_budget_can_actually_elapse(name: str, budget: float) -> None:
    ceiling = _per_test_timeout()
    assert budget + HEADROOM_SECONDS <= ceiling, (
        f"{name} is {budget}s against a {ceiling}s per-test kill. It can never "
        "elapse: pytest-timeout kills the test first and reports a thread dump "
        "instead of this helper's assertion. Either lower it, or raise "
        "pyproject.toml's `timeout` deliberately — that kill is what stops a "
        "hung Windows subprocess from wedging the whole run."
    )


def test_budgets_are_generous_enough_to_survive_a_loaded_machine() -> None:
    """The regression this guards is a revert, not a typo.

    At 5 s and 10 s, seven to nine API tests failed under a full-suite parallel
    run on a 32-core Windows box while passing in CI and passing alone — the
    machine was busy, not broken. Anything back down at that scale reintroduces
    it, and it reintroduces it *only* on machines fast enough to run the suite
    wide, which is the worst possible place for it to hide.
    """
    assert WORKFLOW_TIMEOUT >= 30.0
    assert STEP_TIMEOUT >= 20.0
