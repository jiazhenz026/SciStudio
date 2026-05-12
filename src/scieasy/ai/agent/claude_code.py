"""Claude Code provider implementation.

Conforms to :class:`scieasy.ai.agent.provider.AgentProvider`; wraps the
locally-installed ``claude`` CLI as a subprocess and exposes its
stream-JSON output as canonical :class:`scieasy.ai.agent.provider.AgentEvent`
instances.

Phase 1 ships the stub class; T-ECA-104 implements:

* binary discovery via :func:`scieasy.ai.agent.binary_discovery.find_binary`;
* ``--version`` + login-state probing;
* subprocess spawn with the canonical flag set (``--output-format
  stream-json --verbose --append-system-prompt @<file> --mcp-config
  @<file> [--resume <id>] [--model <m>]``);
* multi-turn stdin write + group-kill on cancel;
* temp-file lifecycle for the prompt and MCP config files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from scieasy.ai.agent.provider import (
    AgentProvider,
    AgentSession,
    PermissionMode,
    ProviderStatus,
)


class ClaudeCodeProvider:
    """Provider for the ``@anthropic-ai/claude-code`` CLI.

    Structural conformance with :class:`AgentProvider` (PEP 544) is
    verified at the type level — see ``_PROTOCOL_CONFORMANCE`` below.
    Phase 1 leaves the methods as stubs; T-ECA-104 implements them.
    """

    name: ClassVar[str] = "claude-code"
    binary_name: ClassVar[str] = "claude"

    @classmethod
    def discover(cls) -> ProviderStatus:
        """Locate the ``claude`` binary and probe version + login state.

        Returns
        -------
        ProviderStatus
            Discovery result.

        Raises
        ------
        NotImplementedError
            Always, in Phase 1. Implementation lands in T-ECA-104.
        """
        raise NotImplementedError("ClaudeCodeProvider.discover is implemented in T-ECA-104")

    def start_session(
        self,
        *,
        project_dir: Path,
        system_prompt: str,
        mcp_config: dict[str, Any],
        resume_session_id: str | None,
        permission_mode: PermissionMode,
    ) -> AgentSession:
        """Spawn a ``claude`` subprocess and return a live session handle.

        Parameters
        ----------
        project_dir
            Absolute path to the SciEasy project workspace.
        system_prompt
            Composed system prompt to pass via ``--append-system-prompt``.
        mcp_config
            MCP configuration dict; serialised to a temp file and passed
            via ``--mcp-config``.
        resume_session_id
            Optional prior session id for ``--resume``.
        permission_mode
            Selects strict per-call approval vs. bypass mode.

        Returns
        -------
        AgentSession
            Live session.

        Raises
        ------
        NotImplementedError
            Always, in Phase 1. Implementation lands in T-ECA-104.
        """
        raise NotImplementedError("ClaudeCodeProvider.start_session is implemented in T-ECA-104")


# Type-level conformance check: assigning the class to an
# ``AgentProvider``-typed name catches Protocol drift at mypy time
# without requiring runtime ``isinstance`` machinery.
_PROTOCOL_CONFORMANCE: type[AgentProvider] = ClaudeCodeProvider
