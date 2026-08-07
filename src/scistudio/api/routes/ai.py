"""Provider discovery endpoints for the embedded coding agent.

ADR-034 Phase 2 trimmed this module down to the single ``/api/ai/status``
endpoint introduced in Phase 1.2. The legacy pre-ADR-033 single-call
surfaces (``/api/ai/generate-block``, ``/api/ai/suggest-workflow``,
``/api/ai/optimize-params``) and their associated request/response
schemas were deleted along with ``scistudio.ai.generation`` and
``scistudio.ai.optimization`` — they fed an AI workflow path that the
PTY-tab embedded agent now replaces end-to-end.

ADR-053 spec 2 adds ``/api/ai/availability`` beside it. The two are
deliberately not merged: ``/status`` answers presence for the chat Setup
screen's dropdown and costs nothing beyond a ``--version`` probe, while
``/availability`` grades the same rows into the four states a surface that
is about to *spend* a user's session needs, which requires a real billed
call to each provider. A caller that only wants to order a dropdown should
not pay for that.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from scistudio.ai.agent import availability as agent_availability
from scistudio.ai.agent.providers_registry import ProviderDescriptor, agent_descriptors, resolve_binary
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


#: Wall-clock budget for every provider-owned subprocess probe. A provider
#: binary that exists but whose ``--version`` hangs must be reported
#: ``available: false`` rather than stalling the endpoint (ADR-034 spec §2
#: Edge Cases).
_PROBE_TIMEOUT_SECONDS = 2


@router.get("/status")
async def provider_status() -> dict[str, Any]:
    """Return per-provider availability for the embedded coding agent.

    ADR-034 Phase 1.2 + multi-provider (FR-008, FR-020b): the frontend's Setup
    screen needs to know which CLI agents are installed and logged in so it can
    order, disable, and annotate the provider dropdown.

    One entry per **agent** provider, in registry order. The ``user-terminal``
    pseudo-provider is excluded (FR-003) — it is launched from its own
    bottom-panel surface, not from the chat Setup screen. Response shape::

        {
          "providers": [
            {"name": "claude-code", "available": true,  "version": "2.1.141",
             "logged_in": true,  "label": "Claude Code"},
            {"name": "kimi-code",   "available": false, "version": null,
             "logged_in": false, "label": "Kimi Code"}
          ]
        }

    ``label`` is additive per FR-020b: display names come from the backend so
    adding a provider needs no frontend edit. The other four fields keep their
    original names, types, and meaning.

    All probes are best-effort and bounded by a
    :data:`_PROBE_TIMEOUT_SECONDS` subprocess timeout — the endpoint must never
    block the API or 500. Probes run on worker threads and concurrently across
    providers so the endpoint's latency stays flat as the registry grows rather
    than scaling with the provider count; ``asyncio.gather`` preserves registry
    order in the result.
    """
    return {"providers": await _status_rows()}


async def _status_rows() -> list[dict[str, Any]]:
    """Probe every registered agent provider concurrently, in registry order."""
    descriptors = agent_descriptors()
    providers = await asyncio.gather(*(asyncio.to_thread(_probe_provider, d) for d in descriptors))
    return list(providers)


@router.get("/availability")
async def agent_availability_report(
    refresh: Annotated[
        bool,
        Query(description="Bypass the memoised report and re-probe every provider."),
    ] = False,
) -> dict[str, Any]:
    """Return graded agent availability for any surface that needs a working agent.

    ADR-053 spec 2, FR-031 to FR-036. Where ``GET /api/ai/status`` reports
    whether each CLI is present and logged in, this endpoint answers the
    question a surface about to start an agent session actually has: will a
    call work *right now*? Response shape::

        {
          "state": "ready",
          "providers": [
            {"key": "claude-code", "label": "Claude Code",
             "state": "ready", "cause": null},
            {"key": "codex", "label": "Codex",
             "state": "call_failed", "cause": "quota exceeded"}
          ]
        }

    Per-provider ``state`` is one of ``not_installed``, ``not_authenticated``,
    ``call_failed``, ``ready``. The first two are read off the same status rows
    ``/api/ai/status`` returns, so there is no second discovery path; the last
    two are separated by a live minimal call through the provider's own CLI,
    because a credential file on disk and a successful ``--version`` do not
    establish that a request will succeed. ``cause`` is populated only for
    ``call_failed`` and never carries reinstall guidance.

    The aggregate ``state`` is ``ready`` when **any** provider is ready, so one
    unconfigured CLI never blocks a user who has a working one; otherwise it is
    the most actionable state present, ranked ``call_failed`` >
    ``not_authenticated`` > ``not_installed``.

    Live calls are billed requests, so the report is memoised briefly and shared
    across surfaces. Pass ``refresh=true`` behind an explicit retry control.
    Every probe is bounded and runs concurrently: a slow or hanging provider is
    reported as a failed call rather than holding the response.
    """
    report = await agent_availability.probe_availability(_status_rows, refresh=refresh)
    return report.as_dict()


def _probe_provider(descriptor: ProviderDescriptor) -> dict[str, Any]:
    """Probe one registered agent provider's binary and login state.

    Every per-CLI fact this needs — binary names, off-PATH install directories,
    config root and its environment override, credential file, auth status
    command — is read off ``descriptor``. There is no ``if provider == …``
    chain, which is what makes a sixth provider a registry row (FR-001).
    """
    binary, available, version = _binary_status(descriptor)
    return {
        "name": descriptor.key,
        "available": available,
        "version": version,
        "logged_in": _provider_logged_in(descriptor, binary),
        "label": descriptor.label,
    }


def _binary_status(descriptor: ProviderDescriptor) -> tuple[str | None, bool, str | None]:
    """Return ``(binary, available, version_string_or_None)`` for *descriptor*.

    Available iff the registry resolver finds the binary AND
    ``<binary> --version`` completes within :data:`_PROBE_TIMEOUT_SECONDS` with
    non-empty output. Version is the trimmed stdout (stderr when stdout is
    empty).

    FR-005: discovery goes through :func:`~...providers_registry.resolve_binary`,
    the same resolver the spawn path and the AI Block path use, so the three can
    never disagree about whether a provider is installed. That matters most for
    the CLIs that are never on PATH — Kimi Code and both Qoder channels live
    only in their well-known install directories, which are descriptor data.
    ``shutil.which`` and ``Path.home()`` are resolved here and passed in rather
    than left to the registry's defaults, so this module stays the single
    monkeypatch seam the status tests drive.
    """
    resolved = resolve_binary(descriptor, which=shutil.which, home=Path.home())
    if resolved is None:
        return None, False, None
    binary = str(resolved)
    try:
        result = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return binary, False, None
    version = (result.stdout or result.stderr or "").strip()
    if not version:
        return binary, False, None
    return binary, True, version


def _provider_logged_in(descriptor: ProviderDescriptor, binary: str | None) -> bool:
    """Descriptor-driven login probe (FR-009).

    Two ordered steps, both declared by ``descriptor.credentials``:

    1. **Credential file presence** under the provider's own resolved config
       root. This covers Linux/Windows and the macOS file-fallback path, and it
       is the only signal both Qoder channels expose — neither ships a
       machine-readable auth status command, so login state comes from ``.auth``
       under ``~/.qoder`` / ``~/.qoder-cn`` respectively. Each channel reads its
       own root, so one logged-in channel never marks the other logged in.
    2. **The provider-owned auth status command**, when the descriptor declares
       one. Asking the CLI to inspect its own auth state is what lets SciStudio
       detect keychain/keyring-stored credentials (current Codex builds) without
       probing the macOS Keychain itself.

    Absent both signals — or a descriptor with no credential probe at all — the
    provider reports not logged in, which is selectable in the picker: the user
    completes the CLI's own login flow inside the PTY.
    """
    probe = descriptor.credentials
    if probe is None:
        return False
    credential_file = descriptor.credential_file(home=Path.home())
    if credential_file is not None and credential_file.is_file():
        return True
    if not binary or not probe.auth_status_argv:
        return False
    return _auth_status_command_logged_in([binary, *probe.auth_status_argv])


def _auth_status_command_logged_in(argv: list[str]) -> bool:
    """Run a provider-owned auth-status command with a short timeout."""
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0
