"""Permission policy for agent tool calls.

The policy decides, for each tool call the agent attempts, whether the
hook bridge should auto-approve, auto-deny, or escalate to the user
via the WebSocket prompt (spec §3 D4, OQ6).

T-ECA-110 ships the runtime policy (read-only-tool whitelist + bypass mode)
and the **pending-decision registry** used by the permission-check
endpoint to await the user's decision delivered over the chat WebSocket.

Design summary (spec §5 T-ECA-110):

* The hook fires on the CC subprocess side, but the user is in the
  frontend. ``POST /api/ai/permission-check`` creates an
  :class:`asyncio.Event` keyed by a fresh ``request_id`` and waits on it;
  the frontend's ``POST /api/ai/permission-decision`` (or the
  ``permission_decision`` WS message) calls
  :func:`signal_decision`, which sets the Event and stores the decision
  payload. The check endpoint then consumes the payload and returns it
  to the bridge.
* The registry is module-level (single FastAPI process; ADR-033 §3 D5.2
  is explicitly single-user). For multi-process deployments the registry
  would need to move to Redis, but that is out of scope.

Auto-approve policy (STRICT mode):

* Native CC tools in :data:`AUTO_APPROVE_NATIVE_TOOLS` always auto-approve.
* SciEasy MCP read tools (name prefix :data:`MCP_TOOL_PREFIX`, mutation
  classification ``"read"`` in the MCP :data:`TOOL_REGISTRY`)
  auto-approve per ADR-033 §3 D2.2. SciEasy MCP write tools require
  user approval. Unknown MCP names also require approval (fail-closed).
* Everything else (Edit, Write, Bash, WebFetch, etc., and any non-SciEasy
  MCP tools) requires user approval.

In :attr:`PermissionMode.BYPASS` mode the policy returns ``True`` for
every tool, matching ``--dangerously-skip-permissions`` semantics.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from scieasy.ai.agent.provider import PermissionMode

logger = logging.getLogger(__name__)


MCP_TOOL_PREFIX: str = "mcp__scieasy__"
"""Prefix Claude Code applies to SciEasy MCP tool names.

The MCP convention is ``mcp__<server>__<tool>`` (see
``docs/specs/eca-spike-hook-protocol.md`` and the spec §3 D2.2). The
SciEasy MCP server registers itself as ``scieasy`` in the static
``mcp.json`` emitted by :func:`scieasy.ai.agent.config_files.write_mcp_config`,
so SciEasy tool names always appear as ``mcp__scieasy__<tool>`` in
the ``tool_use`` event. Stripping this prefix yields the bare tool
name registered in :data:`scieasy.ai.agent.mcp._registry.TOOL_REGISTRY`.

Non-SciEasy MCP servers (if a user wires one up via Claude Code's
own MCP config) will not match this prefix and will fall through to
user approval — the policy intentionally fails closed for them.
"""


AUTO_APPROVE_NATIVE_TOOLS: frozenset[str] = frozenset(
    {
        "Read",
        "Glob",
        "Grep",
        "WebSearch",
        "TodoWrite",
        "NotebookRead",
        "BashOutput",
        "KillShell",
    }
)
"""Claude Code native tools that are always auto-approved in strict mode.

These are the eight read-only / state-free natives identified in spec
§5 T-ECA-110. Any tool name outside this set (and outside the
read-only MCP tool subset, which Phase 2 will populate) requires user
approval in STRICT mode.

The set is exposed as a module-level constant so the permission policy
and the audit tooling share a single source of truth.
"""


# ---------------------------------------------------------------------------
# Tunables.
# Defined at module level so tests can monkeypatch them down to fractions
# of a second without the production default being affected.
# ---------------------------------------------------------------------------

DECISION_TIMEOUT_SECONDS: float = 300.0
"""Default soft timeout for a pending permission decision (spec §3 OQ6).

After this many seconds with no user response, the permission-check
endpoint resolves with ``{action: "deny", reason: "timed_out"}``. The
constant is module-level so tests can monkeypatch it via
``monkeypatch.setattr(permission, "DECISION_TIMEOUT_SECONDS", 0.5)``.
"""


class PermissionPolicy:
    """Decides whether a tool call should auto-approve, auto-deny, or ask.

    Construct with a :class:`PermissionMode`:

    * :attr:`PermissionMode.STRICT` — only :data:`AUTO_APPROVE_NATIVE_TOOLS`
      auto-approve in v1; everything else escalates.
    * :attr:`PermissionMode.BYPASS` — every tool auto-approves.

    Invariants:

    * A policy instance is immutable for the lifetime of one session
      (mode changes take effect on the next session start).
    * :meth:`should_auto_approve` is pure; it does not call out to the
      filesystem or network.
    """

    def __init__(self, mode: PermissionMode) -> None:
        """Construct a policy for the given mode."""
        self.mode: PermissionMode = mode

    def should_auto_approve(self, tool_name: str, tool_input: dict[str, Any]) -> bool:
        """Return ``True`` iff the tool call should bypass user approval.

        Parameters
        ----------
        tool_name
            The tool identifier as it appears in the provider's
            ``tool_use`` event.
        tool_input
            The tool's argument payload. Currently unused; reserved for
            future variants of the policy that inspect target paths
            (e.g. allow-list a sandbox subdir).

        Returns
        -------
        bool
            ``True`` to auto-approve, ``False`` to escalate.

        Notes
        -----
        MCP read-tool auto-approve (per ADR-033 §3 D2.2 / T-ECA-110) is
        sourced from :func:`scieasy.ai.agent.mcp._registry.lookup` so the
        permission policy and the MCP dispatcher share one source of
        truth. Adding or removing a tool in the registry automatically
        updates the auto-approve set — they cannot drift.

        The lookup fails closed:

        * Tool not present in the registry → require approval.
        * Tool mutation classification is anything other than ``"read"`` →
          require approval.
        """
        # ``tool_input`` is intentionally unused in v1 — see docstring.
        del tool_input
        if self.mode is PermissionMode.BYPASS:
            return True
        if self.mode is PermissionMode.STRICT:
            if tool_name in AUTO_APPROVE_NATIVE_TOOLS:
                return True
            if tool_name.startswith(MCP_TOOL_PREFIX):
                # Import locally to avoid a top-level import cycle: the
                # MCP registry imports from ``scieasy.ai.agent.mcp.tools_*``
                # which transitively import scieasy.runtime, and we do
                # not want to pay that cost at module import time.
                from scieasy.ai.agent.mcp._registry import lookup

                bare = tool_name[len(MCP_TOOL_PREFIX) :]
                entry = lookup(bare)
                if entry is not None and entry.mutation == "read":
                    return True
            return False
        # Defensive: PermissionMode is a closed enum but extending it
        # later should not silently auto-approve.
        return False


# ---------------------------------------------------------------------------
# Pending-decision registry.
#
# Used by ``POST /api/ai/permission-check`` and signaled by
# ``POST /api/ai/permission-decision`` (and the equivalent
# ``permission_decision`` WS message). The registry is module-private to
# enforce that the lifecycle goes through ``register`` / ``signal`` /
# ``consume`` rather than direct dict manipulation.
# ---------------------------------------------------------------------------


_PendingEntry = tuple[asyncio.Event, dict[str, Any]]
"""(event, decision_slot) per ``request_id``. ``decision_slot`` is empty
until ``signal_decision`` fills it; ``consume_pending_decision`` pops it."""


_pending_decisions: dict[str, _PendingEntry] = {}


def register_pending_decision(request_id: str | None = None) -> tuple[str, asyncio.Event]:
    """Create a fresh pending-decision entry and return ``(request_id, event)``.

    Parameters
    ----------
    request_id
        Optional pre-generated identifier. If ``None``, a UUID4 hex
        string is used. Tests pass an explicit value for determinism;
        the permission-check endpoint passes ``None`` so each call gets
        a unique id.

    Returns
    -------
    (str, asyncio.Event)
        The id (callers must include it in the ``permission_request``
        broadcast so the frontend can echo it back) and the Event the
        caller awaits.
    """
    rid = request_id if request_id is not None else uuid.uuid4().hex
    if rid in _pending_decisions:
        # Re-using an id is a bug; warn loudly rather than silently
        # overwrite the previous Event.
        logger.warning("register_pending_decision: id %s already pending; overwriting", rid)
    event = asyncio.Event()
    _pending_decisions[rid] = (event, {})
    return rid, event


def signal_decision(
    request_id: str,
    decision: str,
    reason: str | None = None,
) -> bool:
    """Mark the pending decision as resolved.

    Parameters
    ----------
    request_id
        The id returned by :func:`register_pending_decision`.
    decision
        Either ``"approve"`` or ``"deny"``. No other values are
        accepted; the caller (the WS or REST handler) is responsible
        for validating client input before calling.
    reason
        Optional human-readable reason for a deny; surfaced to the hook
        bridge's stderr and ultimately to the user.

    Returns
    -------
    bool
        ``True`` if the id was known and the event was set, ``False``
        if the id is unknown (e.g. already consumed or never
        registered).
    """
    entry = _pending_decisions.get(request_id)
    if entry is None:
        logger.warning("signal_decision: unknown request_id %s", request_id)
        return False
    event, slot = entry
    slot["decision"] = decision
    if reason is not None:
        slot["reason"] = reason
    event.set()
    logger.info("signal_decision: %s -> %s", request_id, decision)
    return True


def consume_pending_decision(request_id: str) -> dict[str, Any] | None:
    """Pop and return the decision payload, or ``None`` if not registered.

    Idempotent: a second call with the same ``request_id`` returns
    ``None``. Callers should invoke this only after awaiting the Event
    returned by :func:`register_pending_decision`.
    """
    entry = _pending_decisions.pop(request_id, None)
    if entry is None:
        return None
    _, slot = entry
    return dict(slot)


def _reset_registry_for_tests() -> None:
    """Clear all pending decisions. Test-only; not part of the public API.

    Used by the ``test_permission`` test module to ensure a clean slate
    between tests within the same pytest worker (the registry is
    module-level and otherwise persists).
    """
    _pending_decisions.clear()
