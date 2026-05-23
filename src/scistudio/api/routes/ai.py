"""Provider discovery endpoint for the embedded coding agent.

ADR-034 Phase 2 trimmed this module down to the single ``/api/ai/status``
endpoint introduced in Phase 1.2. The legacy pre-ADR-033 single-call
surfaces (``/api/ai/generate-block``, ``/api/ai/suggest-workflow``,
``/api/ai/optimize-params``) and their associated request/response
schemas were deleted along with ``scistudio.ai.generation`` and
``scistudio.ai.optimization`` — they fed an AI workflow path that the
PTY-tab embedded agent now replaces end-to-end.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from scistudio.ai.agent.terminal import resolve_windows_executable
from scistudio.api.deps import get_runtime
from scistudio.api.runtime import ApiRuntime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])

RuntimeDep = Annotated[ApiRuntime, Depends(get_runtime)]


class ActiveContextRequest(BaseModel):
    """Payload for ``POST /api/ai/active-context``.

    ADR-040 Addendum 5 / #1488. ``workflow_id`` is the id the GUI is
    currently editing; ``None`` clears the runtime field (e.g. the user
    closed the editor pane). Empty strings are normalised to ``None``
    inside :meth:`ApiRuntime.set_active_workflow_id`.
    """

    workflow_id: str | None = None


class ActiveContextResponse(BaseModel):
    """Echo of the now-current ``active_workflow_id``."""

    workflow_id: str | None = None


@router.post("/active-context", response_model=ActiveContextResponse)
async def set_active_context(
    payload: ActiveContextRequest,
    runtime: RuntimeDep,
) -> ActiveContextResponse:
    """Update the active workflow id surfaced to the AI chat agent.

    ADR-040 Addendum 5 / #1488. The frontend posts here whenever the
    user opens, switches, or closes a workflow in the editor; the
    value is persisted to ``<project>/.scistudio/active_workflow.json``
    so it survives backend restart, and is surfaced to the chat agent
    via the ``get_active_workflow_context`` MCP tool.
    """
    runtime.set_active_workflow_id(payload.workflow_id)
    return ActiveContextResponse(workflow_id=runtime.active_workflow_id)


@router.get("/status")
async def provider_status() -> dict[str, Any]:
    """Return per-provider availability for the embedded coding agent.

    ADR-034 Phase 1.2: the frontend's Setup screen needs to know which
    CLI agents are installed and logged in so it can disable buttons
    and surface install instructions.  The locked response shape::

        {
          "providers": [
            {"name": "claude-code", "available": true,  "version": "2.1.141", "logged_in": true},
            {"name": "codex",       "available": false, "version": null,      "logged_in": false}
          ]
        }

    All probes are best-effort and bounded by a 2 s subprocess timeout
    — the endpoint must never block the API or 500.
    """
    return {
        "providers": [
            _probe_claude(),
            _probe_codex(),
        ]
    }


def _probe_claude() -> dict[str, Any]:
    """Probe ``claude`` binary + credentials."""
    available, version = _binary_status("claude")
    logged_in = _claude_logged_in()
    return {
        "name": "claude-code",
        "available": available,
        "version": version,
        "logged_in": logged_in,
    }


def _probe_codex() -> dict[str, Any]:
    """Probe ``codex`` binary + credentials.

    Codex stores its auth in ``~/.codex/auth.json`` after
    ``codex login``; presence of that file is treated as "looks logged
    in" for the frontend gate.  Codex may evolve its auth storage
    format; if so this probe gets bumped.
    """
    available, version = _binary_status("codex")
    auth_file = Path.home() / ".codex" / "auth.json"
    return {
        "name": "codex",
        "available": available,
        "version": version,
        "logged_in": auth_file.is_file(),
    }


def _binary_status(name: str) -> tuple[bool, str | None]:
    """Return ``(available, version_string_or_None)`` for ``name``.

    Available iff ``shutil.which`` finds the binary AND ``<name> --version``
    completes within 2 s with non-empty stdout.  Version is the trimmed
    stdout.
    """
    binary = resolve_windows_executable(name, which=shutil.which)
    if not binary:
        return False, None
    try:
        result = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False, None
    version = (result.stdout or result.stderr or "").strip()
    if not version:
        return False, None
    return True, version


def _claude_logged_in() -> bool:
    """Heuristic: does claude appear to have stored credentials?

    Order of probes:

    1. ``~/.claude/.credentials.json`` exists — covers Linux / Windows
       and the macOS file-fallback path.
    2. On macOS, ``security find-generic-password`` against either of
       the two known service names (``Claude Code-credentials`` is the
       current name; ``claude-code`` was used briefly).  Bounded by a
       2 s timeout so a slow Keychain doesn't hang the endpoint.
    """
    if (Path.home() / ".claude" / ".credentials.json").is_file():
        return True
    if sys.platform != "darwin":
        return False
    for service in ("Claude Code-credentials", "claude-code"):
        try:
            result = subprocess.run(
                ["security", "find-generic-password", "-s", service],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError):
            continue
        if result.returncode == 0:
            return True
    return False
