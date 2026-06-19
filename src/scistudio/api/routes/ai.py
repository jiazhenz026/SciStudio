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
    binary, available, version = _binary_status("claude")
    logged_in = _claude_logged_in(binary)
    return {
        "name": "claude-code",
        "available": available,
        "version": version,
        "logged_in": logged_in,
    }


def _probe_codex() -> dict[str, Any]:
    """Probe ``codex`` binary + credentials.

    Codex stores its auth in ``~/.codex/auth.json`` after
    ``codex login`` when file-based storage is selected. Current Codex
    builds may also store credentials in the OS keychain/keyring, so we
    ask the provider-owned ``codex login status`` command before falling
    back to file presence.
    """
    binary, available, version = _binary_status("codex")
    return {
        "name": "codex",
        "available": available,
        "version": version,
        "logged_in": _codex_logged_in(binary),
    }


def _binary_status(name: str) -> tuple[str | None, bool, str | None]:
    """Return ``(binary, available, version_string_or_None)`` for ``name``.

    Available iff ``shutil.which`` finds the binary AND ``<name> --version``
    completes within 2 s with non-empty stdout.  Version is the trimmed
    stdout.
    """
    binary = resolve_windows_executable(name, which=shutil.which)
    if not binary:
        return None, False, None
    try:
        result = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return binary, False, None
    version = (result.stdout or result.stderr or "").strip()
    if not version:
        return binary, False, None
    return binary, True, version


def _claude_logged_in(binary: str | None) -> bool:
    """Heuristic: does claude appear to have stored credentials?

    Order of probes:

    1. ``~/.claude/.credentials.json`` exists — covers Linux / Windows
       and the macOS file-fallback path.
    2. ``claude auth status --json`` exits 0 — asks the provider CLI to
       inspect its own auth state instead of probing macOS Keychain
       directly from SciStudio.
    """
    if (Path.home() / ".claude" / ".credentials.json").is_file():
        return True
    if not binary:
        return False
    return _auth_status_command_logged_in([binary, "auth", "status", "--json"])


def _codex_logged_in(binary: str | None) -> bool:
    """Heuristic: does codex appear to have stored credentials?"""
    auth_file = Path.home() / ".codex" / "auth.json"
    if auth_file.is_file():
        return True
    if not binary:
        return False
    return _auth_status_command_logged_in([binary, "login", "status"])


def _auth_status_command_logged_in(argv: list[str]) -> bool:
    """Run a provider-owned auth-status command with a short timeout."""
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0
