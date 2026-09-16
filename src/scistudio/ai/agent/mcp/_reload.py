"""The registry-invalidation event, as an MCP tool can signal it."""
# Maintainer context (kept outside generated API documentation):
# The registry-invalidation event, as an MCP tool can signal it.
#
# ADR-053 FR-062 is written in terms of *events* that invalidate a registry, not
# in terms of a method name: a caller names what happened and the refresh set is
# decided in one place. On the API side that place is
# ``ApiRuntime.refresh_all_registries()``. An MCP tool cannot call it — an
# :class:`~scistudio.ai.agent.mcp._context.MCPContext` exposes the two registries
# as read-only properties over whatever runtime installed it and carries no
# refresh method — so this module is the same idea on the agent side: two tools
# (``reload_blocks`` and ``promote_to_user_library``) name the event and share
# one definition of what it rebuilds.
#
# Refreshing *in place* is what makes it reach the palette. Under the FastAPI
# process the context is a read-through adapter over the live ``ApiRuntime``, so
# ``hot_reload()`` and ``rescan()`` here mutate the very registries
# ``GET /api/blocks/`` reads — which is the in-process half of FR-065. The
# standalone-bridge half is in :mod:`scistudio.ai.agent.mcp.runtime`.
#
# Previewers are deliberately outside the reach: the context does not carry the
# preview service, and widening the Protocol to add it would change every context
# implementation for a surface the agent does not read.
# Development references: ADR-053, FR-062, FR-065.

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

logger = logging.getLogger(__name__)

#: WS event the GUI already listens on to refresh its palette and schemas.
BLOCKS_RELOADED_EVENT_TYPE = "blocks.reloaded"


def refresh_context_registries(ctx: Any) -> tuple[list[str], list[str]]:
    """Rebuild both registries *ctx* holds, in place.

    Returns ``(added, removed)`` block type names so a caller can report what
    the event changed. The registry is keyed by display name; the reported names
    are each spec's ``type_name``, the string ``list_blocks`` / ``get_block_schema``
    and a workflow's ``block_type`` use.
    """
    # Development references: #2405.
    # The standalone runtime's ``block_registry`` property rebuilds on a
    # drop-in change before returning, which would take the "before" snapshot
    # after the rebuild and report nothing. Read the registry it wraps.
    registry = getattr(ctx, "_block_registry", None) or ctx.block_registry
    before = _block_type_names(registry)
    ctx.block_registry.hot_reload()
    ctx.type_registry.rescan()
    after = _block_type_names(ctx.block_registry)
    return sorted(after - before), sorted(before - after)


def dropin_failure_dicts(registry: Any) -> list[dict[str, str]]:
    """Return the drop-in files the last scan refused, as plain dicts (ADR-053 FR-015)."""
    recorded = registry.dropin_failures() if hasattr(registry, "dropin_failures") else []
    return [asdict(failure) for failure in recorded]


def _block_type_names(registry: Any) -> set[str]:
    """Return the ``type_name`` of every registered block (display name as fallback)."""
    return {getattr(spec, "type_name", "") or key for key, spec in registry.all_specs().items()}


async def broadcast_blocks_reloaded(
    ctx: Any,
    *,
    added: list[str],
    removed: list[str],
    source: str = "agent",
) -> None:
    """Tell connected GUI clients the block catalogue changed.

    Best-effort by design: a headless or standalone context has no event bus
    and simply skips, and a broadcast failure must not fail the tool call that
    already succeeded on disk.
    """
    event_bus = getattr(ctx, "event_bus", None)
    if event_bus is None:
        return
    try:
        from scistudio.engine.events import EngineEvent

        reloaded = sorted(ctx.block_registry.all_specs().keys())
        await event_bus.emit(
            EngineEvent(
                event_type=BLOCKS_RELOADED_EVENT_TYPE,
                data={
                    "added": added,
                    "removed": removed,
                    "reloaded": reloaded,
                    "source": source,
                    "dropin_failures": dropin_failure_dicts(ctx.block_registry),
                },
            )
        )
    except Exception:
        logger.exception("%s broadcast failed", BLOCKS_RELOADED_EVENT_TYPE)


__all__ = [
    "BLOCKS_RELOADED_EVENT_TYPE",
    "broadcast_blocks_reloaded",
    "dropin_failure_dicts",
    "refresh_context_registries",
]
