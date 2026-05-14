"""ADR-036 §3.3 — Python lint endpoint test stubs.

xfail markers will be removed by Phase 2A implementation agent (I36a).
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_lint_clean_returns_empty() -> None:
    """POST /api/lint/python with ``print('ok')\\n`` returns ``diagnostics: []``."""
    raise NotImplementedError


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_lint_unused_import() -> None:
    """``import os\\n`` returns one diagnostic with code starting with "F401"."""
    raise NotImplementedError


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_lint_syntax_error() -> None:
    """``def foo(\\n`` returns one diagnostic with code "E999" (or ruff equivalent)."""
    raise NotImplementedError


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_lint_ruff_missing() -> None:
    """When ``subprocess.run`` raises ``FileNotFoundError``, response is empty + has note.

    Monkeypatch ``subprocess.run`` to raise; assert
    ``response.json() == {"diagnostics": [], "note": "ruff unavailable on server"}``.
    """
    raise NotImplementedError


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_lint_ruff_timeout() -> None:
    """When ``subprocess.run`` raises ``TimeoutExpired``, response is empty + has note."""
    raise NotImplementedError


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_lint_diagnostic_shape() -> None:
    """Every returned diagnostic has line/column/end_line/end_column/code/severity/message.

    Send a snippet that triggers exactly one diagnostic; assert the
    response shape field-by-field. This guards the contract the React
    side maps straight into Monaco's IMarkerData.
    """
    raise NotImplementedError
