"""Exception hierarchy for the embedded coding agent runtime.

These exceptions form the canonical error model for the agent subsystem
(spec ``docs/specs/embedded-coding-agent-spec.md`` §4.2). They are mapped
to HTTP status codes at the API boundary (``api/routes/ai.py``) and to
MCP JSON-RPC error frames at the MCP boundary.

The hierarchy is intentionally shallow: every leaf inherits from
:class:`AgentError`, and MCP-specific failures form a sub-tree under
:class:`MCPError` to allow MCP transports to filter on a single base.
"""

from __future__ import annotations


class AgentError(Exception):
    """Base class for every embedded coding agent failure.

    Catch this at process / request boundaries when a generic
    agent-domain handler is required. Specific call sites should catch
    the narrowest applicable subclass.
    """


class AgentNotInstalledError(AgentError):
    """Raised when the configured provider's binary cannot be found on PATH or the fallback search list."""


class AgentNotLoggedInError(AgentError):
    """Raised when the provider's binary is present but no OAuth credentials are configured."""


class AgentLaunchError(AgentError):
    """Raised when the agent subprocess fails to spawn or to emit its initial handshake event."""


class AgentSessionError(AgentError):
    """Raised on session-level failures (concurrent-chat cap reached, resume failed, unknown session id)."""


class AgentStreamError(AgentError):
    """Raised when the provider's stream-json output cannot be parsed (truncated frame, oversized line, non-UTF-8)."""


class PermissionDeniedError(AgentError):
    """Raised when the user denies a tool-use permission request via the hook bridge."""


class PermissionTimeoutError(AgentError):
    """Raised when a pending permission request exceeds the configured soft timeout (default 5 minutes)."""


class MCPError(AgentError):
    """Base class for MCP-tool-level failures surfaced through the SciEasy MCP server."""


class MCPToolNotFoundError(MCPError):
    """Raised when the agent invokes an MCP tool name that is not registered."""


class MCPInvalidInputError(MCPError):
    """Raised when an MCP tool call payload fails JSON-Schema validation against the tool's ``input_schema``."""


class MCPInternalError(MCPError):
    """Raised when an MCP tool implementation raises an unexpected internal exception."""


class MCPAtomicityError(MCPError):
    """Raised when an MCP write-tool's file-lock acquisition fails or a read-modify-write race is detected."""
