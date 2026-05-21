"""SPA fallback static file handler.

Returns index.html for any request path that does not match a real static
file.  Required for client-side routing: deep URLs like
``/projects/123/workflows`` must return the SPA shell, not 404.
"""

from __future__ import annotations

import os

from starlette.staticfiles import StaticFiles


class SPAStaticFiles(StaticFiles):
    """Serve ``index.html`` for paths that do not match a real file.

    All ``/api/*`` and ``/ws`` requests are handled by FastAPI route
    handlers registered *before* this mount, so they are never
    intercepted by the SPA fallback.
    """

    def lookup_path(self, path: str) -> tuple[str, os.stat_result | None]:
        """Return the real file if it exists, otherwise ``index.html``."""
        full_path, stat_result = super().lookup_path(path)
        if stat_result is None:
            return super().lookup_path("index.html")
        return full_path, stat_result
