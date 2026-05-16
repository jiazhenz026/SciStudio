"""Prod-env agent provisioning module (ADR-040 §3.5-3.8).

Owns the orchestration that writes per-project agent assets (CLAUDE.md +
AGENTS.md, Claude Code hooks, multi-skill split, Codex MCP config) at
project lifecycle events (create_project / open_project / cli init).

This package is intentionally narrow — it is filesystem-only (no API, no
engine, no block-registry imports) and runs as a non-fatal degraded-mode
operation per ADR §7. Failures log at WARNING; the project still opens.

S40c (this skeleton) defines the module shape with NotImplementedError
bodies. I40c (Phase 2a, #1013) fills in real implementations.
"""

from scieasy.agent_provisioning._orchestrate import (
    SCIEASY_PROVISION_VERSION,
    ProvisionResult,
    install_project_agent_assets,
)

__all__ = [
    "SCIEASY_PROVISION_VERSION",
    "ProvisionResult",
    "install_project_agent_assets",
]
