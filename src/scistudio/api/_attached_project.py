"""Bind an attached GUI view's requests to the project it attached to."""
# Maintainer context (kept outside generated API documentation):
# An ``open_gui`` deep link opens a second GUI client that attaches to the
# project the backend already has open (#2385). The backend has one active
# project, and workflow routes resolve through it, so if the session owner
# switches projects the attached page would read and write the new project
# while still showing the old one. The attached page sends the project id it
# verified in ``ATTACHED_PROJECT_HEADER`` on every API request; this middleware
# refuses any such request once the active project is a different one (or
# none), and the page detaches on that refusal. Requests without the header —
# the desktop window, the agent, plain browser tabs — are untouched.
# Development references: #2385.

from __future__ import annotations

import json
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

ATTACHED_PROJECT_HEADER = "x-scistudio-attached-project"
"""Header an attached GUI view sends with the project id it attached to."""

ATTACHED_PROJECT_CHANGED = "attached_project_changed"
"""``detail.error`` code of the 409 returned when the binding no longer holds."""


class AttachedProjectGuardMiddleware:
    """Refuse bound requests whose project is no longer the active one."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        attached = _header(scope, ATTACHED_PROJECT_HEADER)
        if attached is None:
            await self.app(scope, receive, send)
            return
        active = _active_project_id(scope)
        if attached == active:
            await self.app(scope, receive, send)
            return
        body = json.dumps(
            {
                "detail": {
                    "error": ATTACHED_PROJECT_CHANGED,
                    "message": (
                        "SciStudio no longer has the project this page attached to open; "
                        "the request was refused so it cannot touch another project."
                    ),
                    "attachedProjectId": attached,
                    "activeProjectId": active,
                }
            }
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 409,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def _header(scope: Scope, name: str) -> str | None:
    wanted = name.encode("latin-1")
    for key, value in scope.get("headers", []):
        if key.lower() == wanted:
            decoded = value.decode("latin-1").strip()
            return decoded or None
    return None


def _active_project_id(scope: Scope) -> str | None:
    app: Any = scope.get("app")
    runtime = getattr(getattr(app, "state", None), "runtime", None)
    project = getattr(runtime, "active_project", None)
    return getattr(project, "id", None)
