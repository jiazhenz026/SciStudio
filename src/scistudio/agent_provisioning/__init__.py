"""Install project-local agent configuration and support files.

Provisioning runs when a project is created or opened. Failures log a warning
and return a degraded result; they do not prevent the project from opening.
"""
# Maintainer context (kept outside generated API documentation):
# Prod-env agent provisioning module (ADR-040 §3.5-3.8).
#
# Owns the orchestration that writes per-project agent assets (CLAUDE.md +
# AGENTS.md, Claude Code hooks, multi-skill split, Codex MCP config) at
# project lifecycle events (create_project / open_project / cli init).
#
# This package is intentionally narrow — it is filesystem-only (no API, no
# engine, no block-registry imports) and runs as a non-fatal degraded-mode
# operation per ADR §7. Failures log at WARNING; the project still opens.
#
# S40c (this skeleton) defines the module shape with NotImplementedError
# bodies. I40c (Phase 2a, #1013) fills in real implementations.
# Development references: #1013, ADR-040.

from scistudio.agent_provisioning._orchestrate import (
    SCISTUDIO_PROVISION_VERSION,
    ProvisionResult,
    install_project_agent_assets,
)

__all__ = [
    "SCISTUDIO_PROVISION_VERSION",
    "ProvisionResult",
    "install_project_agent_assets",
]
