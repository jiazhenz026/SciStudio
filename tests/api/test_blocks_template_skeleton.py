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


# ---------------------------------------------------------------------------
# Regression tests — ADR-036 audit P1-2.
#
# These do not depend on the real ``get_block_template`` implementation.
# They assert the FastAPI route table registers ``/template`` BEFORE the
# greedy ``/{block_type}`` so ``GET /api/blocks/template`` actually
# reaches the template handler instead of being interpreted as
# ``block_type="template"`` by ``get_block_schema``.
# ---------------------------------------------------------------------------


def test_template_route_registered_before_block_type() -> None:
    """``/template`` MUST be declared before ``/{block_type}``.

    See ADR-036 audit finding P1-2. Without this, the template endpoint
    is unreachable (``get_block_schema`` returns 404 with detail
    ``"Unknown block type: template"``).
    """
    from scieasy.api.routes.blocks import router

    paths_in_order = [r.path for r in router.routes]
    template = paths_in_order.index("/api/blocks/template")
    block_type = paths_in_order.index("/api/blocks/{block_type}")
    assert template < block_type, (
        "ADR-036 P1-2 regression: /template must precede /{block_type} so "
        f"FastAPI matches it first. Current order: {paths_in_order}"
    )


def test_template_route_resolves_to_template_handler_not_schema() -> None:
    """A live ``GET /api/blocks/template`` reaches ``get_block_template``.

    Skeleton raises NotImplementedError -> 500. If the catch-all is
    intercepting, we instead see 404 ("Unknown block type: template").
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from scieasy.api.deps import get_block_registry, get_type_registry
    from scieasy.api.routes.blocks import router

    app = FastAPI()
    app.include_router(router)
    # Provide stub dependencies; the template endpoint does not consume them
    # but get_block_schema would, and we do not want dependency-resolution
    # 500s masking the real signal.
    app.dependency_overrides[get_block_registry] = lambda: object()
    app.dependency_overrides[get_type_registry] = lambda: object()

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/blocks/template?kind=basic")
    assert response.status_code == 500, (
        f"Expected 500 from skeleton NotImplementedError in get_block_template, got "
        f"{response.status_code}: {response.text!r}. If this is 404 with detail "
        "'Unknown block type: template', the /{block_type} catch-all is "
        "intercepting — P1-2 regression."
    )
