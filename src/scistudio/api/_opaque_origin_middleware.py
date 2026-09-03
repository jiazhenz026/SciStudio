"""FR-021's other clause: only the panel asset route answers the opaque origin.

ADR-054 spec 1 FR-021 gives the merged panel asset route permission to answer
read-only cross-origin requests, and then says **"no other route MUST answer
such requests, which is what keeps the asset route the only thing a panel can
reach without the host."** That second clause was prose with nothing behind it
(#2229): a single global ``CORSMiddleware`` sits over the whole application, so
every route answers whichever origins it is configured for, and with
``SCISTUDIO_CORS_ORIGINS=*`` that is every origin there is.

**Which requester the clause is about.** A panel document is framed with
``sandbox="allow-scripts"`` and without ``allow-same-origin``, which puts it at
an *opaque* origin. An opaque origin serialises in the ``Origin`` header as the
literal string ``null``. That is the requester FR-021's rationale names: the
thing that must be able to reach the asset route and must not be able to reach
anything else. Enforcing the clause therefore means refusing ``Origin: null``
everywhere but the asset route.

**Why the clause cannot be enforced literally.** Read as "no other route
answers any cross-origin request", it contradicts the application: the dev
frontend is served from ``localhost:5173`` while the API answers on
``localhost:8000``, so every route answering that origin is how ``npm run dev``
works at all. The invariant enforced here is the operative one — the opaque
origin — and the wording of FR-021 is the manager's to settle (D-014).

**Why a guard rather than a narrower allow-list.** The default configuration
happens to satisfy the invariant, because ``null`` is not among the four
localhost origins. But that is an accident of the default, not a property: an
operator who sets ``SCISTUDIO_CORS_ORIGINS=*`` — or who lists ``null``
explicitly — loses it silently. A guard outside the CORS middleware makes the
invariant hold in every configuration, which is what a security property has to
do to be one.

The guard **removes** grant headers rather than refusing the request. A panel
that reaches a route it should not reach gets a response the browser will not
let it read, which is the same outcome as a refusal without inventing a status
code for a case the routes know nothing about.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

__all__ = ["OPAQUE_ORIGIN", "OpaqueOriginGuardMiddleware"]

#: The ``Origin`` value a document at an opaque origin sends — which is what a
#: panel in a ``sandbox="allow-scripts"`` frame is.
OPAQUE_ORIGIN = "null"

#: Response headers that grant a cross-origin reader access. Stripped as a set
#: rather than one by one so a future Starlette that adds another grant header
#: does not quietly reopen the hole; ``Vary`` is left alone because it is a
#: caching instruction rather than a grant.
_CROSS_ORIGIN_GRANT_PREFIXES = ("access-control-",)
_CROSS_ORIGIN_GRANT_HEADERS = frozenset({b"cross-origin-resource-policy"})


class OpaqueOriginGuardMiddleware:
    """Strip cross-origin grants from every response but the asset route's.

    A pure ASGI middleware rather than a ``BaseHTTPMiddleware``: it only needs
    to rewrite the headers on ``http.response.start``, and the asset route
    answers with a ``FileResponse``, which a ``BaseHTTPMiddleware`` would
    otherwise pull through an extra streaming layer for no reason.

    Installed *after* the CORS middleware so it sits outside it and sees the
    headers CORS has already set (Starlette runs middleware in reverse add
    order).
    """

    def __init__(self, app: ASGIApp, *, asset_route_prefix: str) -> None:
        self.app = app
        self.asset_route_prefix = asset_route_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        origin = _header(scope, b"origin")
        if origin != OPAQUE_ORIGIN:
            # No opaque origin, no question: an ordinary same-origin request
            # sends no `Origin` at all, and a browser origin is the CORS
            # middleware's to allow or refuse on its configured list.
            await self.app(scope, receive, send)
            return

        if scope.get("path", "").startswith(self.asset_route_prefix):
            # The one route FR-021 grants. Its own headers are set on the
            # response by `serve_panel_asset` and are left exactly as they are.
            await self.app(scope, receive, send)
            return

        async def send_without_cross_origin_grants(message: Message) -> None:
            if message["type"] == "http.response.start":
                message = dict(message)
                message["headers"] = [
                    (name, value) for name, value in message.get("headers", []) if not _is_grant(name)
                ]
            await send(message)

        logger.debug(
            "refusing the opaque origin on %s; FR-021 grants it only %s",
            scope.get("path", ""),
            self.asset_route_prefix,
        )
        await self.app(scope, receive, send_without_cross_origin_grants)


def _header(scope: Scope, name: bytes) -> str | None:
    """Return one request header from *scope*, decoded, or ``None``."""
    headers: Iterable[tuple[bytes, bytes]] = scope.get("headers", [])
    for key, value in headers:
        if key.lower() == name:
            return value.decode("latin-1")
    return None


def _is_grant(name: bytes) -> bool:
    """Whether *name* is a response header granting cross-origin access."""
    lowered = name.lower()
    return lowered in _CROSS_ORIGIN_GRANT_HEADERS or lowered.decode("latin-1").startswith(_CROSS_ORIGIN_GRANT_PREFIXES)
