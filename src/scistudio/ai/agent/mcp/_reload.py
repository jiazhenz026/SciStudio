"""The registry-invalidation event, as an MCP tool can signal it.

ADR-053 FR-062 is written in terms of *events* that invalidate a registry, not
in terms of a method name: a caller names what happened and the refresh set is
decided in one place. On the API side that place is
``ApiRuntime.refresh_all_registries()``. An MCP tool cannot call it — an
:class:`~scistudio.ai.agent.mcp._context.MCPContext` exposes the two registries
as read-only properties over whatever runtime installed it and carries no
refresh method — so this module is the same idea on the agent side: two tools
(``reload_blocks`` and ``promote_to_user_library``) name the event and share
one definition of what it rebuilds.

Refreshing *in place* is what makes it reach the palette. Under the FastAPI
process the context is a read-through adapter over the live ``ApiRuntime``, so
``hot_reload()`` and ``rescan()`` here mutate the very registries
``GET /api/blocks/`` reads — which is the in-process half of FR-065. The
standalone-bridge half is in :mod:`scistudio.ai.agent.mcp.runtime`.

Previewers are deliberately outside the reach: the context does not carry the
preview service, and widening the Protocol to add it would change every context
implementation for a surface the agent does not read.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: WS event the GUI already listens on to refresh its palette and schemas.
BLOCKS_RELOADED_EVENT_TYPE = "blocks.reloaded"


def refresh_context_registries(ctx: Any) -> tuple[list[str], list[str]]:
    """Rebuild both registries *ctx* holds, in place.

    Returns ``(added, removed)`` block type names so a caller can report what
    the event changed.
    """
    before = set(ctx.block_registry.all_specs().keys())
    ctx.block_registry.hot_reload()
    ctx.type_registry.rescan()
    after = set(ctx.block_registry.all_specs().keys())
    return sorted(after - before), sorted(before - after)


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
                data={"added": added, "removed": removed, "reloaded": reloaded, "source": source},
            )
        )
    except Exception:
        logger.exception("%s broadcast failed", BLOCKS_RELOADED_EVENT_TYPE)


__all__ = [
    "BLOCKS_RELOADED_EVENT_TYPE",
    "broadcast_blocks_reloaded",
    "refresh_context_registries",
]
