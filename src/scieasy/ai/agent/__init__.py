"""Embedded coding agent runtime (ADR-033, Phase 1 scaffold).

This package owns the agent runtime backbone:

* :mod:`scieasy.ai.agent.provider` — :class:`AgentProvider` and
  :class:`AgentSession` Protocols, the :class:`ProviderStatus`
  dataclass, the :class:`PermissionMode` enum, and the base
  :class:`AgentEvent` envelope.
* :mod:`scieasy.ai.agent.errors` — canonical exception hierarchy
  (spec §4.2).
* :mod:`scieasy.ai.agent.binary_discovery` — CLI binary fallback
  search (T-ECA-102).
* :mod:`scieasy.ai.agent.stream_json` — NDJSON event parser
  (T-ECA-103).
* :mod:`scieasy.ai.agent.session` — :class:`AgentSessionManager`
  (T-ECA-106).
* :mod:`scieasy.ai.agent.permission` — :class:`PermissionPolicy`
  (T-ECA-110).
* :mod:`scieasy.ai.agent.transcript` — :class:`TranscriptWriter`
  (T-ECA-106).
* :mod:`scieasy.ai.agent.system_prompt` — three-tier prompt
  composition (T-ECA-204).
* :mod:`scieasy.ai.agent.claude_code` — :class:`ClaudeCodeProvider`
  (T-ECA-104).

Phase 1 ships only signatures and stubs; behaviour is added by the
follow-up implementation tickets listed above.
"""

from __future__ import annotations

from scieasy.ai.agent import errors
from scieasy.ai.agent.permission import AUTO_APPROVE_NATIVE_TOOLS, PermissionPolicy
from scieasy.ai.agent.provider import (
    AgentEvent,
    AgentProvider,
    AgentSession,
    PermissionMode,
    ProviderStatus,
)
from scieasy.ai.agent.session import AgentSessionManager
from scieasy.ai.agent.transcript import TranscriptWriter

__all__ = [
    "AUTO_APPROVE_NATIVE_TOOLS",
    "AgentEvent",
    "AgentProvider",
    "AgentSession",
    "AgentSessionManager",
    "PermissionMode",
    "PermissionPolicy",
    "ProviderStatus",
    "TranscriptWriter",
    "errors",
]
