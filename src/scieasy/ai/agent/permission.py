"""Permission policy for agent tool calls.

The policy decides, for each tool call the agent attempts, whether the
hook bridge should auto-approve, auto-deny, or escalate to the user
via the WebSocket prompt (spec §3 D4, OQ6).

Phase 1 ships the stub :class:`PermissionPolicy` and the canonical
:data:`AUTO_APPROVE_NATIVE_TOOLS` set that T-ECA-110 will consume; the
runtime policy implementation (read-only-tool whitelist, MCP-read-tool
classification, ``ask`` escalation) lands in T-ECA-110.
"""

from __future__ import annotations

from typing import Any

from scieasy.ai.agent.provider import PermissionMode

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
read-only MCP tool subset) requires user approval in STRICT mode.

The set is exposed as a module-level constant so the permission policy
and the audit tooling share a single source of truth.
"""


class PermissionPolicy:
    """Decides whether a tool call should auto-approve, auto-deny, or ask.

    The policy is initialised with a :class:`PermissionMode`:

    * :attr:`PermissionMode.STRICT` — only :data:`AUTO_APPROVE_NATIVE_TOOLS`
      and read-class MCP tools auto-approve; everything else escalates.
    * :attr:`PermissionMode.BYPASS` — every tool auto-approves.

    Invariants:

    * A policy instance is immutable for the lifetime of one session
      (mode changes take effect on the next session start).
    * ``should_auto_approve`` is pure; it does not call out to the
      filesystem or network.
    """

    def __init__(self, mode: PermissionMode) -> None:
        """Construct a policy for the given mode.

        Parameters
        ----------
        mode
            The session-level permission mode.
        """
        self.mode: PermissionMode = mode

    def should_auto_approve(self, tool_name: str, tool_input: dict[str, Any]) -> bool:
        """Return ``True`` iff the tool call should bypass user approval.

        Parameters
        ----------
        tool_name
            The tool identifier as it appears in the provider's
            ``tool_use`` event.
        tool_input
            The tool's argument payload, used by future variants of
            the policy that inspect, for example, target paths.

        Returns
        -------
        bool
            ``True`` to auto-approve, ``False`` to escalate to the
            user.

        Raises
        ------
        NotImplementedError
            Always, in Phase 1. Implementation lands in T-ECA-110.
        """
        raise NotImplementedError("PermissionPolicy.should_auto_approve is implemented in T-ECA-110")
