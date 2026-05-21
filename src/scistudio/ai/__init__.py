"""AI services package.

Phase 4 of ADR-033 removed the legacy single-call AI surfaces
(``scistudio.ai.config``, ``scistudio.ai.generation``, ``scistudio.ai.synthesis``,
``scistudio.ai.optimization``). The embedded coding agent now lives under
``scistudio.ai.agent`` and is exposed via the WebSocket / status routes in
``scistudio.api.routes.ai``. AIBlock keeps its own provider wrappers under
``scistudio.blocks.ai`` (ADR-033 §3 D9 narrow exception).
"""
