"""Global opaque-origin refusal and startup CORS validation (ADR-054)."""

from __future__ import annotations

from starlette._utils import get_route_path
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class RefuseOpaqueOriginMiddleware:
    """Refuse opaque-origin mutations before guards or edition routes run.

    This is deliberately independent of path and identity: a sandbox cannot
    mutate the backend using ambient cookies, even on self-authenticated paths.
    GET/HEAD/OPTIONS remain available for token-scoped modules and fonts.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Inspect all occurrences so duplicate headers cannot hide null.
        if (
            scope["type"] == "http"
            and scope["method"] in {"POST", "PUT", "PATCH", "DELETE"}
            and any(
                name.lower() == b"origin" and value.strip().lower() == b"null"
                for name, value in scope.get("headers", ())
            )
        ):
            await JSONResponse(
                {"detail": "Opaque Origin null is not allowed for mutating requests"},
                status_code=403,
            )(scope, receive, send)
            return
        await self.app(scope, receive, send)


def validate_cors_origins(origins: list[str]) -> None:
    """Reject unsafe global CORS grants; token routes set their own headers."""
    if any(origin.strip().lower() in {"*", "null"} for origin in origins):
        raise ValueError(
            "SCISTUDIO_CORS_ORIGINS must not contain * or null; configure explicit trusted origins instead"
        )


class PanelCORSMiddleware(CORSMiddleware):
    """Leave token CORS/preflight to routes that authenticate each request.

    Ordinary API requests retain Starlette's explicit-origin CORS behavior.
    The static exception is literal and segment-boundary matched, including
    under the configured ASGI root path. It grants no authentication itself.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = get_route_path(scope)
            if path.startswith("/api/panels/t/"):
                await self.app(scope, receive, send)
                return
        await super().__call__(scope, receive, send)
