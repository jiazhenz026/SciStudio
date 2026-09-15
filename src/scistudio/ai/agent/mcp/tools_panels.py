"""MCP tools for panels and MiniApps (2 tools)."""
# Maintainer context (kept outside generated API documentation):
# Category (g) MCP tools — the agent's half of the MiniApp loop (2 tools).
#
# ``docs/specs/adr-054-miniapp.md`` FR-029/FR-030. The MiniApp skill tells the
# agent to write a panel directory, check it, and then put it in front of the
# user. Those last two steps are the only ones the agent cannot do with a file
# write, so they are tools:
#
# * ``validate_panel`` runs the same two checks discovery runs — the descriptor
#   parse and the external-reference scan — against one directory, and hands
#   back what discovery would have swallowed into a registry-wide diagnostics
#   list. The agent needs the text of the diagnostic, not a boolean, because the
#   diagnostic names the field to fix.
# * ``open_miniapp`` asks the workspace to open a MiniApp tab. The agent has no
#   way to open a tab: ``open_gui`` only hands back a URL for the agent's own
#   browser tooling, and everything else the agent does is a file write the GUI
#   notices asynchronously. This tool emits the ``panel.open_miniapp`` event the realtime
#   layer forwards, which is the one channel from the agent back into the open
#   workspace.
#
# **Why the no-workspace case is a result rather than a silent success.**
# ``broadcast_blocks_reloaded`` swallows a missing event bus, and it is right to:
# the block registry changed on disk whether or not anyone was watching. An
# ``open_miniapp`` that nobody received achieved nothing at all, and an agent
# that believes it opened a tab will tell the user to look at a tab that is not
# there. So this tool checks for a realtime channel, then asks
# :func:`scistudio.engine.gui_presence.any_connected`, and reports
# ``opened=False`` with a machine-readable ``reason`` when there is no channel
# (``no_event_bus``) or no workspace (``no_workspace``) to open into. It is deliberately in-band rather than a raise: nothing went
# wrong, the answer is simply "no window is open".
#
# Layering: ``scistudio.ai`` may not import ``scistudio.api`` (import-linter), so
# the event-type string is a bare module constant here exactly as
# ``BLOCKS_RELOADED_EVENT_TYPE`` is in :mod:`scistudio.ai.agent.mcp._reload`, and
# the realtime layer keeps its own copy in its outbound set. Workspace presence
# travels through :mod:`scistudio.engine.gui_presence`, which sits below both.
# Development references: #2288, #2354, ADR-054, FR-029, FR-030,
# docs/specs/adr-054-miniapp.md.

from __future__ import annotations

import logging
from typing import Annotated

from pydantic import BaseModel, Field

from scistudio.ai.agent.mcp._context import _resolve_project_path, get_context
from scistudio.ai.agent.mcp.server import mcp
from scistudio.panels.descriptor import parse_descriptor
from scistudio.panels.files import validate_external_references
from scistudio.panels.registry import PanelRegistry, discover_panels
from scistudio.previewers.models import OwnerKind

logger = logging.getLogger(__name__)

#: Realtime event the workspace listens on to open or focus a MiniApp tab.
#: Duplicated as a bare string in ``scistudio.api.ws``'s outbound set, the same
#: way ``blocks.reloaded`` is: the AI layer may not import the API layer, and
#: ``scistudio.engine.events`` is frozen to the ADR-035/036 vocabulary.
PANEL_OPEN_MINIAPP_EVENT_TYPE = "panel.open_miniapp"

#: ``reason`` values on an ``open_miniapp`` result that did not open anything.
NO_WORKSPACE = "no_workspace"
NO_EVENT_BUS = "no_event_bus"
BROADCAST_FAILED = "broadcast_failed"

_MINIAPP_CONTEXT = "miniapp"


class ValidatePanelResult(BaseModel):
    """Result envelope for ``validate_panel``."""

    path: str = Field(description="Absolute path of the panel directory that was checked.")
    valid: bool = Field(description="True when no error diagnostic was raised; warnings may still be present.")
    panel_id: str | None = Field(
        default=None,
        description="The descriptor's id, or None when the descriptor could not be parsed.",
    )
    contexts: list[str] = Field(
        default_factory=list,
        description="Declared contexts (preview / interactive / miniapp). Empty when the parse failed.",
    )
    types: list[str] = Field(
        default_factory=list,
        description="Declared data types. A MiniApp declares exactly one.",
    )
    entry: str | None = Field(default=None, description="The page the host loads, relative to the directory.")
    has_python: bool = Field(default=False, description="True when the directory carries a panel.py.")
    errors: list[str] = Field(
        default_factory=list,
        description=(
            "Diagnostics that stop this directory being discovered as a panel. Each names the "
            "FR it fails and the field to fix. Fix these before opening the panel."
        ),
    )
    warnings: list[str] = Field(
        default_factory=list,
        description=(
            "Diagnostics that do not stop discovery — an unpinned CDN reference, a soft "
            "descriptor note. Worth fixing; not fatal."
        ),
    )


class OpenMiniAppResult(BaseModel):
    """Result envelope for ``open_miniapp``."""

    opened: bool = Field(
        description=(
            "True only when the request reached an open workspace. False means no tab was "
            "opened and ``reason`` says why — never tell the user to look at a tab on a "
            "False result."
        )
    )
    panel_id: str = Field(description="The MiniApp that was asked for.")
    workflow_id: str = Field(description="Workflow holding the block whose output the MiniApp opens on.")
    block_id: str = Field(description="Block whose output the MiniApp opens on.")
    port: str = Field(description="Output port of that block.")
    reason: str | None = Field(
        default=None,
        description=(
            "None on success. 'no_workspace' when no SciStudio window is connected, "
            "'no_event_bus' when this runtime has no realtime channel at all (a standalone "
            "bridge session), 'broadcast_failed' when the event could not be delivered."
        ),
    )
    detail: str = Field(description="What happened, in words worth repeating to the user.")
    next_step: str = Field(
        default=(
            "If opened is True, tell the user the MiniApp is open on that output and ask what "
            "they want to change about it. If opened is False, do NOT claim it opened: say the "
            "MiniApp is ready and name the panel id so they can open it from the MiniApps tab."
        ),
        description="Suggested next MCP call and what to tell the user.",
    )


def _workspace_connected() -> bool:
    """True when at least one SciStudio workspace holds a realtime connection.

    Imported at call time rather than at module import: this is a lookup into the
    engine's process-wide presence registry, and keeping it local keeps the tool
    module importable (and therefore every tool in it registered) in a runtime
    that never starts the realtime layer.
    """
    from scistudio.engine import gui_presence

    return bool(gui_presence.any_connected())


def _miniapp_ids(registry: PanelRegistry) -> list[str]:
    """Ids of every discovered panel declaring the ``miniapp`` context."""
    return sorted(panel_id for panel_id, panel in registry.panels.items() if _MINIAPP_CONTEXT in panel.contexts)


@mcp.tool(name="validate_panel", tags={"category:panels", "read"})
async def validate_panel(
    path: Annotated[
        str,
        Field(
            description=(
                "Project-relative (or absolute, inside the project) path of the panel "
                "directory holding panel.json — for a MiniApp, 'panels/<panel_id>'."
            )
        ),
    ],
) -> ValidatePanelResult:
    """Check one panel directory the way discovery checks it.

    Use when:
      - You have just written or edited a MiniApp or panel directory and want
        the diagnostics before you open it. Always run this before telling the
        user a MiniApp is ready.
      - A MiniApp does not appear in the MiniApps tab and you need to know
        which descriptor rule the directory fails.

    Do NOT use to:
      - Check a page's JavaScript — this reads ``panel.json`` and scans the page
        files for external references; it never runs the page.
      - List panels — the MiniApps tab and ``GET /api/panels/catalog`` own that.
      - Check a block — use ``run_block_tests``.

    Returns the diagnostics rather than raising on an invalid panel: the text of
    the diagnostic names the field to fix. ``errors`` non-empty means the
    directory would not be discovered at all; ``warnings`` are worth fixing but
    do not stop it. Raises ``RuntimeError`` when no project is open,
    ``PermissionError`` for a path outside the project, and
    ``NotADirectoryError`` when the path is not a directory.
    """
    directory = _resolve_project_path(path)
    if not directory.is_dir():
        raise NotADirectoryError(
            f"'{path}' is not a directory. Pass the panel directory holding panel.json, e.g. 'panels/<panel_id>'."
        )

    ctx = get_context()
    registered_types = tuple(ctx.type_registry.all_types().keys())
    try:
        panel, notes = parse_descriptor(
            directory,
            owner_kind=OwnerKind.PROJECT,
            owner_name="project",
            registered_types=registered_types,
        )
    except (ValueError, OSError, TypeError) as exc:
        return ValidatePanelResult(path=str(directory), valid=False, errors=[f"{directory}: {exc}"])

    try:
        notes.extend(validate_external_references(panel.root))
    except (ValueError, OSError) as exc:
        return ValidatePanelResult(
            path=str(directory),
            valid=False,
            panel_id=panel.id,
            contexts=list(panel.contexts),
            types=list(panel.types),
            entry=panel.entry,
            has_python=panel.has_python,
            errors=[f"{directory}: {exc}"],
        )

    return ValidatePanelResult(
        path=str(directory),
        valid=True,
        panel_id=panel.id,
        contexts=list(panel.contexts),
        types=list(panel.types),
        entry=panel.entry,
        has_python=panel.has_python,
        warnings=[f"{directory}: {note}" for note in notes],
    )


@mcp.tool(name="open_miniapp", tags={"category:panels", "write"})
async def open_miniapp(
    panel_id: Annotated[
        str,
        Field(description="Id of a panel declaring the 'miniapp' context — the directory name under panels/."),
    ],
    workflow_id: Annotated[
        str,
        Field(description="Workflow holding the block whose output the MiniApp opens on."),
    ],
    block_id: Annotated[
        str,
        Field(description="Node id of that block in the workflow (not its label)."),
    ],
    port: Annotated[
        str,
        Field(description="Name of the block output port the MiniApp opens on."),
    ],
) -> OpenMiniAppResult:
    """Ask the open workspace to open a MiniApp tab on a block output.

    Use when:
      - You have written and validated a MiniApp and want the user to see it
        running on their data, rather than telling them where to click.
      - The user asks to see an existing MiniApp on a particular block output.

    Do NOT use to:
      - Open the GUI itself, or open a URL in your own browser — that is
        ``open_gui``.
      - Show a static figure — that is ``run_plot_job``.
      - Open a MiniApp you have not run ``validate_panel`` on.

    The block must already have a successful run whose output on ``port``
    matches the MiniApp's declared type; the workspace reports a mismatch when
    it opens the tab.

    Never reports success it did not have: with no workspace connected the
    result is ``opened=False`` with ``reason='no_workspace'``, and in a
    standalone bridge session (no realtime channel at all) it is
    ``reason='no_event_bus'``. Either way the user must be told the MiniApp is
    ready rather than that a tab opened. Raises
    ``KeyError`` for an unknown panel id and ``ValueError`` for a panel that
    does not declare the ``miniapp`` context.
    """
    ctx = get_context()
    # The live type registry rather than a fresh scan: discovery validates each
    # panel's declared types against it, and the one the tools already share is
    # both the cheaper and the more accurate answer to "what is registered".
    registry = discover_panels(ctx.project_dir, registered_types=tuple(ctx.type_registry.all_types().keys()))
    panel = registry.get(panel_id)
    if panel is None:
        known = _miniapp_ids(registry)
        raise KeyError(
            f"No panel with id '{panel_id}' was discovered. "
            f"MiniApps available: {known or 'none'}. "
            "Check the directory name under panels/ and run validate_panel on it."
        )
    if _MINIAPP_CONTEXT not in panel.contexts:
        raise ValueError(
            f"Panel '{panel_id}' declares contexts {list(panel.contexts)} and cannot be opened as a MiniApp. "
            'Add "miniapp" to its panel.json contexts, with exactly one entry in types.'
        )

    target = {"panel_id": panel_id, "workflow_id": workflow_id, "block_id": block_id, "port": port}

    # The channel is checked before the workspace (#2422). A standalone bridge
    # session has no realtime channel, and no window could ever connect to it,
    # so its honest answer is ``no_event_bus``. ``no_workspace`` is for a server
    # that has the channel while no window holds a connection.
    event_bus = getattr(ctx, "event_bus", None)
    if event_bus is None:
        return OpenMiniAppResult(
            **target,
            opened=False,
            reason=NO_EVENT_BUS,
            detail=(
                f"This session has no realtime channel to the workspace, so the tab cannot be "
                f"opened from here. The MiniApp '{panel_id}' is ready and opens from the "
                f"MiniApps tab on that block output."
            ),
        )

    if not _workspace_connected():
        return OpenMiniAppResult(
            **target,
            opened=False,
            reason=NO_WORKSPACE,
            detail=(
                f"No SciStudio workspace is open, so nothing can be opened into. The MiniApp "
                f"'{panel_id}' is ready: it opens from the MiniApps tab on that block output "
                f"once a workspace is open."
            ),
        )

    try:
        from scistudio.engine.events import EngineEvent

        await event_bus.emit(EngineEvent(event_type=PANEL_OPEN_MINIAPP_EVENT_TYPE, block_id=block_id, data=target))
    except Exception as exc:
        logger.exception("%s broadcast failed", PANEL_OPEN_MINIAPP_EVENT_TYPE)
        return OpenMiniAppResult(
            **target,
            opened=False,
            reason=BROADCAST_FAILED,
            detail=(
                f"The request to open '{panel_id}' could not be delivered to the workspace "
                f"({type(exc).__name__}: {exc}). The MiniApp itself is fine; it opens from the "
                f"MiniApps tab on that block output."
            ),
        )

    return OpenMiniAppResult(
        **target,
        opened=True,
        detail=(
            f"Asked the workspace to open '{panel_id}' on {block_id}.{port}. "
            "An already-open tab for the same MiniApp and output is focused rather than duplicated."
        ),
    )


__all__ = [
    "BROADCAST_FAILED",
    "NO_EVENT_BUS",
    "NO_WORKSPACE",
    "PANEL_OPEN_MINIAPP_EVENT_TYPE",
    "OpenMiniAppResult",
    "ValidatePanelResult",
    "open_miniapp",
    "validate_panel",
]
