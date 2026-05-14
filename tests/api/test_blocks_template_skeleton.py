"""ADR-036 §3.12 — block template endpoint test stubs.

xfail markers will be removed by Phase 2C implementation agent (I36c).
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_template_basic_returns_python_with_correct_imports() -> None:
    """GET /api/blocks/template?kind=basic returns Python content with the right imports.

    Assert the response body's ``content`` field contains the literal
    string ``"from scieasy.blocks.base import"`` and references the
    ``Block`` class. The exact import line may evolve (S36 used the
    real exports, not the dispatch's literal ``BlockSpec, PortSpec``
    spec — see comment at the top of
    ``src/scieasy/blocks/_templates/block_base_template.py``).
    """
    raise NotImplementedError


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_template_basic_has_run_marker() -> None:
    """The template content contains the ``# >>> EDIT THIS <<<`` marker.

    This is the user-visible "start typing here" pointer. If it
    disappears, the new-block UX silently regresses.
    """
    raise NotImplementedError


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_template_unknown_kind_400() -> None:
    """GET with kind="frobnicator" returns HTTP 400."""
    raise NotImplementedError
