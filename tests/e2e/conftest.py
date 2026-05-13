"""E2e-specific pytest fixtures and configuration.

This conftest scopes any future end-to-end-only fixtures (browser drivers,
backend lifecycle helpers, run-artifact directories, etc.) to the
``tests/e2e/`` tree so they do not affect the default unit-test suite.

Per ADR-033 spec §8.5 T-ECA-501, this file is intentionally minimal at
scaffold time. Subsequent tickets fill in real fixtures:

- T-ECA-502 — test harness (Chrome automation, backend lifecycle).
- T-ECA-503 — golden reference outputs.
- T-ECA-505 — actual test logic.

Notes on xdist / coverage:

- The default ``pytest`` invocation excludes ``e2e`` tests via
  ``-m 'not e2e'`` (configured in ``pyproject.toml``), so e2e tests do
  not participate in the parallel ``pytest -n auto`` run in CI.
- When e2e tests are eventually executed they should run serially
  (no ``-n auto``) because they share global state (a live backend
  server and a single browser session). T-ECA-502 will document the
  recommended invocation.
- Coverage from e2e runs is informational only; the
  ``--cov-fail-under=85`` gate is satisfied by the unit-test job and
  e2e runs are expected to be invoked separately.
"""
