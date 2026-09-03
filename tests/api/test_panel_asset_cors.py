"""FR-021's cross-origin half: the asset route answers the panel, nothing else does.

ADR-054 spec 1 FR-021 says the merged asset route "MUST answer read-only
cross-origin requests, because a panel at an opaque origin fetches bulk assets
from it directly, and no other route MUST answer such requests, which is what
keeps the asset route the only thing a panel can reach without the host."

`tests/panels/test_panel_asset_route.py` covers the confinement half of FR-021
in full. This file covers the half nothing tested (#2229), and it is worth
saying precisely what "such requests" is read as here, because the literal
clause and the application disagree:

* **A panel's origin is opaque.** ``sandbox="allow-scripts"`` without
  ``allow-same-origin`` puts the framed document at an opaque origin, which
  serialises in the ``Origin`` header as the string ``null``. That is the
  requester FR-021's rationale is about: the thing that must reach the asset
  route and nothing else.
* **The dev frontend's origin is also cross-origin**, and every route must
  answer it — that is how ``npm run dev`` at ``localhost:5173`` talks to the
  API at ``localhost:8000`` at all. So FR-021's clause cannot hold for *all*
  cross-origin requests without breaking the application.

What is enforced, and what these tests pin, is therefore the operative reading:
**no route but the asset route answers the opaque origin**, in every CORS
configuration including ``SCISTUDIO_CORS_ORIGINS=*``. The wording of FR-021 is
the manager's to settle (D-014); this file makes the code's actual invariant
explicit rather than leaving prose the code contradicts.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from scistudio.api.app import create_app

#: The origin a document in a ``sandbox="allow-scripts"`` frame presents.
OPAQUE_ORIGIN = "null"

#: A configured browser origin, to prove the guard is aimed at the opaque
#: origin and not at cross-origin requests in general.
DEV_ORIGIN = "http://localhost:5173"

#: Routes that must not answer the opaque origin. Status is deliberately not
#: asserted: a 404 or a 422 that carries ``Access-Control-Allow-Origin`` is
#: still a route that answered, and the header is the whole question.
NON_ASSET_ROUTES = [
    "/api/panels",
    "/api/panels/choices",
    "/api/blocks",
    "/api/workflows",
    "/api/projects/current",
    "/api/types",
]


@pytest.fixture()
def wildcard_client(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """A client whose CORS configuration is the permissive one.

    ``SCISTUDIO_CORS_ORIGINS=*`` is the configuration in which the global
    middleware answers every origin, so it is the configuration in which
    FR-021's invariant has to be enforced rather than merely happen to hold.
    """
    monkeypatch.setenv("SCISTUDIO_CORS_ORIGINS", "*")
    with TestClient(create_app()) as test_client:
        yield test_client


def _allows_cross_origin(response: object) -> bool:
    """Whether *response* grants a cross-origin reader access to its body."""
    headers = response.headers  # type: ignore[attr-defined]
    return "access-control-allow-origin" in headers


class TestTheAssetRouteAnswersThePanel:
    """The half FR-021 requires to be true."""

    def test_the_asset_route_answers_the_opaque_origin(self, client: TestClient) -> None:
        response = client.get(
            "/api/panels/assets/core.base.fallback/index.html",
            headers={"Origin": OPAQUE_ORIGIN},
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "*"
        assert response.headers["cross-origin-resource-policy"] == "cross-origin"

    def test_the_asset_route_answers_the_opaque_origin_under_a_wildcard_config(
        self,
        wildcard_client: TestClient,
    ) -> None:
        response = wildcard_client.get(
            "/api/panels/assets/core.base.fallback/index.html",
            headers={"Origin": OPAQUE_ORIGIN},
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "*"


class TestNoOtherRouteAnswersThePanel:
    """The half nothing enforced."""

    @pytest.mark.parametrize("route", NON_ASSET_ROUTES)
    def test_no_other_route_answers_the_opaque_origin(self, client: TestClient, route: str) -> None:
        response = client.get(route, headers={"Origin": OPAQUE_ORIGIN})

        assert not _allows_cross_origin(response), (
            f"{route} answered the opaque origin a sandboxed panel presents; FR-021 makes the "
            "asset route the only thing a panel can reach without going through the host"
        )

    @pytest.mark.parametrize("route", NON_ASSET_ROUTES)
    def test_no_other_route_answers_the_opaque_origin_under_a_wildcard_config(
        self,
        wildcard_client: TestClient,
        route: str,
    ) -> None:
        """``SCISTUDIO_CORS_ORIGINS=*`` is where the invariant used to vanish.

        In the default configuration it held only because ``null`` is not in
        the allow-list, which is an accident of the default rather than an
        enforced property.
        """
        response = wildcard_client.get(route, headers={"Origin": OPAQUE_ORIGIN})

        assert not _allows_cross_origin(response), (
            f"{route} answered the opaque origin because the CORS allow-list was widened; "
            "FR-021's invariant must not be a property of the configuration"
        )

    def test_a_preflight_from_the_opaque_origin_is_not_granted(self, wildcard_client: TestClient) -> None:
        """A refused simple request the browser was told it could make is worse
        than one it was told it could not, so the preflight is refused too."""
        response = wildcard_client.options(
            "/api/panels",
            headers={
                "Origin": OPAQUE_ORIGIN,
                "Access-Control-Request-Method": "GET",
            },
        )

        assert not _allows_cross_origin(response)


class TestTheApplicationStillWorks:
    """The narrowing is aimed at the opaque origin, not at CORS."""

    @pytest.mark.parametrize("route", NON_ASSET_ROUTES)
    def test_the_dev_frontend_origin_is_still_answered(self, client: TestClient, route: str) -> None:
        """``npm run dev`` serves the frontend from a different port to the API,
        so every route answering ``localhost:5173`` is how the application runs
        at all."""
        response = client.get(route, headers={"Origin": DEV_ORIGIN})

        assert response.headers.get("access-control-allow-origin") == DEV_ORIGIN

    @pytest.mark.parametrize("route", NON_ASSET_ROUTES)
    def test_a_same_origin_request_is_unaffected(self, client: TestClient, route: str) -> None:
        """No ``Origin`` header, no cross-origin question, nothing stripped."""
        response = client.get(route)

        assert response.status_code < 500
