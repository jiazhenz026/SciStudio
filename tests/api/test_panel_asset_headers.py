"""The frame boundary, restated by the server that serves the document (#2229).

FR-008's boundary is real and tested from the host's side: ``panelFrame.ts``
sets ``sandbox="allow-scripts"`` and nothing else, so the framed document runs
at an opaque origin and cannot walk into the parent, read the application's
storage, or call the API with the person's credentials.

It rests on **one attribute on one code path**. The document itself is served
as ``text/html`` from the application's own origin by
``GET /api/panels/assets/{panel_id}/{asset_path}``, and a package panel or a
project panel that arrived with a shared project is therefore an HTML document
a browser will execute at the application origin if it is ever loaded outside
that frame — by direct navigation, by a link, by ``window.open``. The server
enforced nothing.

These tests pin the defence in depth. ``Content-Security-Policy: sandbox
allow-scripts`` restates the frame's own attribute as a property of the
document, so it holds however the document is reached; it is the *same* token
the frame already applies, so it removes nothing a mounted panel can do today.
``X-Content-Type-Options: nosniff`` and ``Referrer-Policy: no-referrer`` are
the standard pair, the second again mirroring what the frame already sets.

``X-Frame-Options`` is deliberately **not** here: the whole mechanism is a
document in a frame, and ``DENY`` would break it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

#: One built-in document and one non-document asset, so the assertions can say
#: which headers ride on everything and which ride on HTML alone.
DOCUMENT_PATH = "/api/panels/assets/core.base.fallback/index.html"
DECLARATION_PATH = "/api/panels/assets/core.base.fallback/panel.json"


class TestASevedPanelDocumentCarriesItsOwnBoundary:
    def test_the_document_is_sandboxed_by_the_response_as_well_as_by_the_frame(
        self,
        client: TestClient,
    ) -> None:
        response = client.get(DOCUMENT_PATH)

        assert response.status_code == 200
        assert response.headers["content-security-policy"] == "sandbox allow-scripts"

    def test_the_sandbox_token_is_the_frames_own(self, client: TestClient) -> None:
        """The header must not be stricter than ``PANEL_FRAME_SANDBOX``.

        A CSP that withheld ``allow-scripts`` would stop every panel from
        running, and one that added ``allow-same-origin`` would hand back the
        origin the whole boundary exists to withhold. It is the same token, for
        the same reason, in a second place.
        """
        policy = client.get(DOCUMENT_PATH).headers["content-security-policy"]

        assert "allow-scripts" in policy
        assert "allow-same-origin" not in policy

    def test_the_document_is_not_content_sniffed(self, client: TestClient) -> None:
        assert client.get(DOCUMENT_PATH).headers["x-content-type-options"] == "nosniff"

    def test_the_document_leaks_no_referrer(self, client: TestClient) -> None:
        assert client.get(DOCUMENT_PATH).headers["referrer-policy"] == "no-referrer"

    def test_the_route_does_not_forbid_framing(self, client: TestClient) -> None:
        """The mechanism *is* a framed document; ``DENY`` would break it."""
        assert "x-frame-options" not in client.get(DOCUMENT_PATH).headers


class TestEveryServedAssetIsHardened:
    @pytest.mark.parametrize("path", [DOCUMENT_PATH, DECLARATION_PATH])
    def test_nosniff_rides_on_every_asset(self, client: TestClient, path: str) -> None:
        """A ``.json`` a browser sniffed as HTML would be the same problem the
        document header exists to close, so the header is not conditional."""
        response = client.get(path)

        assert response.status_code == 200
        assert response.headers["x-content-type-options"] == "nosniff"

    def test_the_cross_origin_grant_survives_the_hardening(self, client: TestClient) -> None:
        """FR-021's grant and the hardening are on the same response, and the
        hardening must not have taken the grant away."""
        response = client.get(DOCUMENT_PATH, headers={"Origin": "null"})

        assert response.headers["access-control-allow-origin"] == "*"
        assert response.headers["cross-origin-resource-policy"] == "cross-origin"
        assert response.headers["content-security-policy"] == "sandbox allow-scripts"
