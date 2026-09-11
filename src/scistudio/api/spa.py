"""SPA fallback static file handler, with the served page's runtime bootstrap.

Any request path that does not match a real static file returns
``index.html``, so deep links such as ``/projects/123/workflows`` reach the
app instead of a 404. Unknown ``/api`` and ``/ws`` paths stay 404s.

The served ``index.html``, and only that document, carries a small bootstrap
script:

* the mount prefix, when the app is served under one
  (``window.__SCISTUDIO_BASE_PATH__``), so the already-built app learns it at
  runtime without a rebuild;
* the per-launch WebMCP bridge session token
  (``window.__SCISTUDIO_WEBMCP_TOKEN__``), on every mount;
* the capability declaration an edition passes to ``create_app``
  (``window.__SCISTUDIO_CAPABILITIES__``), emitted only when a capability is on.

Every value is serialized so it cannot close the script element. Hashed asset
files are served byte-identical, so caching and update packaging are
unaffected.
"""
# Maintainer context (kept outside generated API documentation): the base path
# is ADR-055 Spec 0 (FR-002, FR-003), the bridge token Spec 1 (FR-006), and the
# capability declaration the identity seam (decision 2d) with the Spec 4
# versioned shape. The frontend reads it in frontend/src/lib/capabilities.ts.
# Development references: ADR-055, FR-002, FR-003, FR-006, Spec 0, Spec 1, Spec 4,
# docs/specs/adr-055-identity-seam.md, docs/specs/adr-055-enterprise-support.md.

from __future__ import annotations

import json
import os
import re
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

if TYPE_CHECKING:
    from scistudio.api.seam import Capabilities

_HEAD_OPEN = re.compile(r"<head[^>]*>", re.IGNORECASE)
_HTML_OPEN = re.compile(r"<html[^>]*>", re.IGNORECASE)


class SPAStaticFiles(StaticFiles):
    """Serve ``index.html`` for paths that do not match a real file.

    Known ``/api/*`` and ``/ws`` requests are handled by FastAPI route
    handlers registered *before* this mount. Unknown API/WebSocket paths must
    remain 404s instead of becoming ``index.html``.
    """

    def __init__(
        self,
        *,
        base_path: str = "",
        webmcp_session_token: str = "",
        capabilities: Capabilities | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        # Normalized mount prefix ("" or "/prefix") from app.state.root_path.
        self._base_path = base_path
        # Per-launch WebMCP bridge session token (ADR-055 Spec 1 FR-006);
        # "" disables the token bootstrap assignment.
        self._webmcp_session_token = webmcp_session_token
        # Capability declaration (identity seam, decision 2d), serialized once;
        # "" (every capability off) disables the assignment.
        self._capabilities_json = (
            _script_safe_json(capabilities.to_bootstrap())
            if capabilities is not None and capabilities.any_enabled
            else ""
        )

    async def get_response(self, path: str, scope: Scope) -> Response:
        """Serve SPA routes, but never rewrite unknown API/WebSocket paths."""
        if _is_api_or_ws_path(path):
            raise HTTPException(status_code=404)
        templated = self._base_path or self._webmcp_session_token or self._capabilities_json
        if templated and scope.get("method", "GET") == "GET":
            full_path, stat_result = self.lookup_path(path)
            if stat_result is not None:
                if os.path.isdir(full_path):
                    # Directory URL: the redirect-to-trailing-slash stays with
                    # StaticFiles; only the actually-served index.html document
                    # is templated.
                    if scope.get("path", "").endswith("/"):
                        index_candidate = os.path.join(full_path, "index.html")
                        if os.path.isfile(index_candidate):
                            return _templated_index_response(
                                index_candidate,
                                self._base_path,
                                self._webmcp_session_token,
                                self._capabilities_json,
                            )
                elif os.path.basename(full_path) == "index.html":
                    # Direct index.html request or SPA fallback (lookup_path
                    # already resolved a missing path to index.html).
                    return _templated_index_response(
                        full_path, self._base_path, self._webmcp_session_token, self._capabilities_json
                    )
        return await super().get_response(path, scope)

    def lookup_path(self, path: str) -> tuple[str, os.stat_result | None]:
        """Return the real file if it exists, otherwise ``index.html``."""
        full_path, stat_result = super().lookup_path(path)
        if stat_result is None:
            if _is_api_or_ws_path(path):
                return full_path, stat_result
            return cast(tuple[str, os.stat_result | None], super().lookup_path("index.html"))
        return full_path, stat_result


def _script_safe_json(value: Any) -> str:
    """Serialize ``value`` as a JSON literal safe inside an inline ``<script>``.

    ``json.dumps`` alone would let a string such as ``</script>`` close the
    element; escaping ``<``, ``>`` and ``&`` (and the two JavaScript line
    terminators) as ``\\uXXXX`` keeps the literal inert while it still parses
    to the same value.
    """
    text = json.dumps(value, separators=(",", ":"))
    for raw, escaped in (
        ("<", "\\u003c"),
        (">", "\\u003e"),
        ("&", "\\u0026"),
        ("\u2028", "\\u2028"),
        ("\u2029", "\\u2029"),
    ):
        text = text.replace(raw, escaped)
    return text


def _templated_index_response(
    index_path: str, base_path: str, webmcp_session_token: str = "", capabilities_json: str = ""
) -> Response:
    """Serve ``index.html`` with the runtime bootstrap injected.

    Four injections, placed immediately after ``<head>`` (falling back to
    ``<html>``, then the top of the document) so they take effect before any
    module script or asset reference:

    * ``<base href="<prefix>/">`` (only when a prefix is configured) — the
      Vite build uses ``base: "./"``, so asset references are
      document-relative; on a deep SPA route (``/p/projects/foo``) they would
      otherwise resolve to ``/p/projects/assets/...`` and hit the SPA
      fallback instead of the static file. The base element pins resolution
      to the prefix root. Root-absolute URLs (``/api/...``) and full
      WebSocket URLs are unaffected by ``<base>``, so the API/WS contract is
      unchanged. The empty prefix emits no ``<base>``.
    * ``window.__SCISTUDIO_BASE_PATH__`` (only when a prefix is configured) —
      the runtime prefix the frontend base-path module reads.
    * ``window.__SCISTUDIO_WEBMCP_TOKEN__`` (when a bridge session token is
      configured) — the per-launch WebMCP bridge session token, injected on
      every mount including the default root mount.
    * ``window.__SCISTUDIO_CAPABILITIES__`` (only when an edition turned a
      capability on) — the versioned capability declaration of the identity
      seam, already serialized by :func:`_script_safe_json`, so no user name
      or route path in it can close the script element.

    ``json.dumps`` keeps each JS value a safely quoted string literal;
    ``html.escape`` does the same for the attribute context.
    ``Cache-Control: no-cache`` because the body no longer matches the file
    on disk — a cached unprefixed shell must never be reused under a
    prefixed deployment, and a cached page must never carry a stale session
    token.
    """
    # Development references: FR-002, FR-003, FR-006, Spec 0, Spec 1.
    html = Path(index_path).read_text(encoding="utf-8")
    injection = ""
    if base_path:
        base_href = escape(f"{base_path}/", quote=True)
        injection += f'<base href="{base_href}">'
    assignments = ""
    # Every value goes through the same script-safe serialization, so an
    # operator-configured prefix containing ``</script>`` cannot close the
    # element either (#2322 no-context audit P3-2).
    if base_path:
        assignments += f"window.__SCISTUDIO_BASE_PATH__ = {_script_safe_json(base_path)};"
    if webmcp_session_token:
        assignments += f"window.__SCISTUDIO_WEBMCP_TOKEN__ = {_script_safe_json(webmcp_session_token)};"
    if capabilities_json:
        assignments += f"window.__SCISTUDIO_CAPABILITIES__ = {capabilities_json};"
    injection += f"<script>{assignments}</script>"
    for pattern in (_HEAD_OPEN, _HTML_OPEN):
        match = pattern.search(html)
        if match is not None:
            html = f"{html[: match.end()]}{injection}{html[match.end() :]}"
            break
    else:
        html = f"{injection}{html}"
    return Response(
        content=html,
        media_type="text/html",
        headers={"Cache-Control": "no-cache"},
    )


def _is_api_or_ws_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lstrip("/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized == "api" or normalized.startswith("api/") or normalized == "ws" or normalized.startswith("ws/")
