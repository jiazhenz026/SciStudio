"""SPA fallback static file handler.

Returns index.html for any request path that does not match a real static
file.  Required for client-side routing: deep URLs like
``/projects/123/workflows`` must return the SPA shell, not 404.
"""

from __future__ import annotations

import os
from typing import cast

from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope


class SPAStaticFiles(StaticFiles):
    """Serve ``index.html`` for paths that do not match a real file.

    Known ``/api/*`` and ``/ws`` requests are handled by FastAPI route
    handlers registered *before* this mount. Unknown API/WebSocket paths must
    remain 404s instead of becoming ``index.html``.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        """Serve SPA routes, but never rewrite unknown API/WebSocket paths."""
        if _is_api_or_ws_path(path):
            raise HTTPException(status_code=404)
        return await super().get_response(path, scope)

    def lookup_path(self, path: str) -> tuple[str, os.stat_result | None]:
        """Return the real file if it exists, otherwise ``index.html``."""
        full_path, stat_result = super().lookup_path(path)
        if stat_result is None:
            if _is_api_or_ws_path(path):
                return full_path, stat_result
            return cast(tuple[str, os.stat_result | None], super().lookup_path("index.html"))
        return full_path, stat_result


def _is_api_or_ws_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lstrip("/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized == "api" or normalized.startswith("api/") or normalized == "ws" or normalized.startswith("ws/")
