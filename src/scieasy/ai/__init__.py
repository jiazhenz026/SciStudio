"""AI services package.

Phase 4 of ADR-033 removed the legacy single-call AI surfaces
(``scieasy.ai.config``, ``scieasy.ai.generation``, ``scieasy.ai.synthesis``,
``scieasy.ai.optimization``). The embedded coding agent now lives under
``scieasy.ai.agent`` and is exposed via the WebSocket / status routes in
``scieasy.api.routes.ai``. AIBlock keeps its own provider wrappers under
``scieasy.blocks.ai`` (ADR-033 §3 D9 narrow exception).
"""
