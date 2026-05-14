"""ADR-034 Phase 2: assert the pre-ADR-033 single-call AI endpoints are gone.

The legacy endpoints ``/api/ai/generate-block``, ``/api/ai/suggest-workflow``,
and ``/api/ai/optimize-params`` fed an AI workflow path that the embedded
PTY-tab coding agent now replaces end-to-end. They should return ``404
Not Found`` — anything else means a regression that re-exposed the
deleted surface.

The new ``/api/ai/status`` endpoint must still be present so the Phase
1.2 / 1.3 setup screen can probe provider availability.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/ai/generate-block",
        "/api/ai/suggest-workflow",
        "/api/ai/optimize-params",
    ],
)
def test_legacy_ai_endpoints_return_404(client: TestClient, endpoint: str) -> None:
    """POST to a deleted endpoint must yield 404 or 405, not 200/500/501.

    FastAPI returns 405 (Method Not Allowed) for unknown paths under a
    mounted router when the prefix matches (``/api/ai``) and 404 when the
    path is entirely unknown. Either is acceptable here — both indicate
    the endpoint is gone — but 200/2xx or 500/5xx would mean the legacy
    handler is back.
    """
    response = client.post(endpoint, json={})
    assert response.status_code in (404, 405), (
        f"{endpoint} returned {response.status_code}; expected 404 or 405. "
        "If you're re-exposing a legacy AI endpoint, please consult ADR-034."
    )


def test_status_endpoint_still_present(client: TestClient) -> None:
    """``/api/ai/status`` (Phase 1.2) must still respond."""
    response = client.get("/api/ai/status")
    assert response.status_code == 200
    payload = response.json()
    assert "providers" in payload
    assert isinstance(payload["providers"], list)
