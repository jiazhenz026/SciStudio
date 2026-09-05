"""Category (g) MCP tools — panel authoring (4 tools, ADR-054 spec 5).

Read-class (2): ``read_panel_source``, ``list_panel_examples``.
Write-class (2): ``scaffold_panel``, ``reload_panels``.

All four register on the shared FastMCP instance with ``tags={"category:panel",
...}``, the same way every other group does. They *use* the panel registry that
ADR-054 spec 1 landed; they do not change it. A panel is registered by existing
as a directory in a tier, which is what lets an agent register one by writing
three files and asking for a rebuild.

**Why a rebuild can be process-local.** The MCP context Protocol
(:class:`scistudio.ai.agent.mcp._context.MCPContext`) deliberately carries the
two registries and nothing else, and the FastAPI adapter that implements it in
production forwards no preview service. ``reload_panels`` therefore asks the
context for one and falls back to the process-global service when the context
has none, reporting which it reached on ``reached_running_gui`` rather than
claiming a reach it does not have. Widening the Protocol is
``docs/planning/adr-054-assembly-followups.md`` (S5-B2), not this change.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field

from scistudio.ai.agent.mcp._context import get_context
from scistudio.ai.agent.mcp.server import mcp

# The same question ``scaffold_block`` asks about a port's type, asked by the
# same helper rather than by a second copy of it.
from scistudio.ai.agent.mcp.tools_authoring import _type_registry_has
from scistudio.ai.agent.mcp.tools_panels._models import (
    DiscoveredPanelEntry,
    ListPanelExamplesResult,
    PanelExampleEntry,
    ReadPanelSourceResult,
    ReloadPanelsResult,
    ScaffoldPanelResult,
)
from scistudio.ai.agent.mcp.tools_panels._scaffold import HARNESS_FILENAME, scaffold_panel_files
from scistudio.core.dropins import panel_roots
from scistudio.core.panels import (
    PANEL_DECLARATION_FILENAME,
    PanelCapability,
    PanelDeclarationError,
    PanelTier,
    read_panel_declaration,
)

logger = logging.getLogger(__name__)

#: The tiers a tool may write into. Core and package are read-only (spec 1
#: FR-026): editing one is copying it down into a writable tier under the same
#: id, which is what makes the copy shadow the original.
_WRITABLE_TIERS = ("project", "user")

#: Where the examples corpus lives. One directory of panel directories, read the
#: same way any other tier root is read. The corpus entries themselves are
#: ADR-054 spec 5 T-008's; this tool returns them when they are there and says
#: so when they are not.
_EXAMPLES_SUBPATH = ("_user_guide", "examples")


# ---------------------------------------------------------------------------
# Shared resolution helpers
# ---------------------------------------------------------------------------


def _project_dir() -> Path | None:
    return get_context().project_dir


def _tier_root(tier: str) -> Path:
    """Return the writable ``panels/`` root for *tier*.

    Raises:
        ValueError: *tier* is not writable, or is ``project`` with no project
            open.
    """
    normalised = tier.strip().lower()
    if normalised not in _WRITABLE_TIERS:
        raise ValueError(
            f"tier {tier!r} is not writable. Write into {' or '.join(repr(t) for t in _WRITABLE_TIERS)}; "
            f"the core and package tiers are read-only, and a panel is edited by copying it down into a "
            f"writable tier under the same panel_id, which shadows the original."
        )
    project_dir = _project_dir()
    roots = panel_roots(project_dir)
    if normalised == "project":
        if project_dir is None:
            raise ValueError(
                "no project is open, so there is no project tier to write into. Open a project, or pass "
                "tier='user' to write into the user library."
            )
        return roots[0]
    return roots[-1]


def _preview_service(*, refresh: bool) -> tuple[Any, bool]:
    """Return ``(service, reached_running_gui)``.

    The context is asked first, because under the FastAPI process its service is
    the one the GUI reads and a rebuild there is a rebuild the person sees. When
    it carries none, the process-global service is used and the caller is told
    the rebuild was process-local rather than being left to assume otherwise.
    """
    from scistudio.panels import get_preview_service

    ctx = get_context()
    accessor = getattr(ctx, "refresh_preview_service" if refresh else "get_preview_service", None)
    if callable(accessor):
        try:
            return accessor(), True
        except Exception:  # pragma: no cover - a runtime that has the name but cannot serve it
            logger.warning("panel tools: the runtime's preview service could not be used", exc_info=True)
    return get_preview_service(project_dir=_project_dir(), refresh=refresh), False


def _entry(panel: Any) -> DiscoveredPanelEntry:
    manifest = panel.manifest
    return DiscoveredPanelEntry(
        panel_id=manifest.panel_id,
        display_name=manifest.display_name or manifest.panel_id,
        tier=panel.tier.value,
        capability=manifest.capability.value,
        target_types=list(manifest.target_types),
        directory=str(panel.directory),
        entry=manifest.entry,
        api_version=manifest.api_version,
        owner=panel.owner_name,
    )


def _gui_base_url() -> str | None:
    """The running GUI's base URL, or ``None``.

    The same environment variable ``open_gui`` reads, so the URL this tool hands
    back and the URL that tool hands back are the same URL.
    """
    url = os.environ.get("SCISTUDIO_ENGINE_API_URL", "").strip()
    return url.rstrip("/") or None


# ---------------------------------------------------------------------------
# (g.1) scaffold_panel  (write)
# ---------------------------------------------------------------------------


@mcp.tool(name="scaffold_panel", tags={"category:panel", "write"})
async def scaffold_panel(
    panel_id: Annotated[
        str,
        Field(description="Stable, unique id, e.g. 'myproj.pick_baseline'. Also the directory name."),
    ],
    target_types: Annotated[
        list[str],
        Field(description="Recorded data type names this panel claims, e.g. ['Series']. Call list_types first."),
    ],
    capability: Annotated[
        str,
        Field(description="'displaying' (renders only) or 'producing' (renders and can emit code back)."),
    ] = "producing",
    tier: Annotated[
        str,
        Field(description="'project' (this project only) or 'user' (your library, every project)."),
    ] = "project",
    display_name: Annotated[str, Field(description="The name a person sees in the panel palette.")] = "",
    emit_target: Annotated[
        str,
        Field(description="The plain Python name a producing panel rebinds when it emits, e.g. 'selection'."),
    ] = "selection",
    overwrite: Annotated[
        bool,
        Field(description="Replace an existing panel directory's three files. Refuses by default."),
    ] = False,
) -> ScaffoldPanelResult:
    """Write a new panel into a tier: declaration, document, and stub harness.

    Use when:
      - The person wants a window onto their data that no registered panel
        gives them — a picker, a region selector, a custom table.
      - You are about to hand-write a panel directory. Do not; this writes the
        declaration the runtime validates and a document that already speaks
        the handshake.

    Do NOT use to:
      - Edit a registered panel — read it with ``read_panel_source`` and write
        the file back yourself.
      - Add a block — use ``scaffold_block``.

    Writes exactly three files into ``<tier>/panels/<panel_id>/``: ``panel.json``,
    ``index.html`` (a working skeleton, not a placeholder), and ``harness.html``.

    **Open the harness.** It loads the document, feeds it representative data for
    each declared target type, stands in for the host, and shows what the panel
    emits. That loop is the reason a panel is a plain HTML document; a panel you
    have not opened is a panel you have not written. Use ``harness_path``
    directly, or ``open_gui`` plus ``harness_url`` once ``reload_panels`` has
    registered it.

    Then edit ``document_path`` and call ``reload_panels``.
    """
    try:
        declared_capability = PanelCapability(capability.strip().lower())
    except ValueError as exc:
        raise ValueError(
            f"capability {capability!r} is not one of "
            f"{', '.join(repr(member.value) for member in PanelCapability)}. A displaying panel renders what "
            f"it is given; a producing panel can also emit code back."
        ) from exc

    root = _tier_root(tier)
    types = tuple(name.strip() for name in target_types if name and name.strip())
    scaffolded = scaffold_panel_files(
        root,
        panel_id=panel_id.strip(),
        display_name=display_name.strip() or panel_id.strip(),
        target_types=types,
        capability=declared_capability,
        tier=tier.strip().lower(),
        emit_target=emit_target.strip() or "selection",
        overwrite=overwrite,
    )

    warnings: list[str] = []
    if not types:
        warnings.append(
            "No target_types were declared. A panel with no target type is only reachable from a block that "
            "names it; a panel meant to be resolved by the type of the data needs at least one."
        )
    else:
        ctx = get_context()
        for name in types:
            if not _type_registry_has(ctx, name):
                warnings.append(
                    f"target type {name!r} is not in the type registry. Call list_types and use the recorded "
                    f"name, or the panel will never be resolved for anything."
                )
    if declared_capability is PanelCapability.DISPLAYING:
        warnings.append(
            "This panel is displaying, so it is granted no outbound path and the harness's emission pane "
            "stays empty by design. Scaffold it as producing if it is meant to hand a value back."
        )

    base_url = _gui_base_url()
    return ScaffoldPanelResult(
        panel_id=scaffolded.manifest.panel_id,
        tier=scaffolded.tier,
        directory=str(scaffolded.directory),
        declaration_path=str(scaffolded.declaration_path),
        document_path=str(scaffolded.document_path),
        harness_path=str(scaffolded.harness_path),
        harness_url=f"{base_url}{scaffolded.harness_url_path}" if base_url else None,
        files_written=[
            str(scaffolded.declaration_path),
            str(scaffolded.document_path),
            str(scaffolded.harness_path),
        ],
        capability=scaffolded.manifest.capability.value,
        target_types=list(scaffolded.manifest.target_types),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# (g.2) read_panel_source  (read)
# ---------------------------------------------------------------------------


@mcp.tool(name="read_panel_source", tags={"category:panel", "read"})
async def read_panel_source(
    panel_id: Annotated[str, Field(description="Id of a registered panel, from reload_panels.")],
) -> ReadPanelSourceResult:
    """Return a registered panel's declaration and document, and which tier won.

    Use when:
      - You are about to change a panel and need its current source.
      - You want a working panel to copy: read a built-in one, then write it
        into your tier under a new id.

    Do NOT use to:
      - List what exists — use ``reload_panels``.
      - Read a block — use ``read_block_source``.

    Resolves through the four-tier order (project, user, package, core), so what
    comes back is what the application would mount. ``read_only`` is true for the
    core and package tiers: change one of those by writing your copy into the
    project or user tier under the same id, which shadows it.
    """
    service, _ = _preview_service(refresh=False)
    discovery = service.panels
    panel = discovery.get(panel_id)
    if panel is None:
        known = ", ".join(sorted(discovery.panels)) or "none"
        raise KeyError(f"no panel with id {panel_id!r} is registered. Registered ids: {known}.")

    document_path = panel.entry_path
    harness_path = panel.directory / HARNESS_FILENAME
    shadowed = [other.tier.value for other in discovery.shadowed if other.panel_id == panel_id]
    return ReadPanelSourceResult(
        panel_id=panel.manifest.panel_id,
        tier=panel.tier.value,
        directory=str(panel.directory),
        declaration=panel.manifest.to_declaration_dict(),
        entry=panel.manifest.entry,
        document=document_path.read_text(encoding="utf-8"),
        document_path=str(document_path),
        harness_path=str(harness_path) if harness_path.is_file() else None,
        read_only=panel.tier in (PanelTier.CORE, PanelTier.PACKAGE),
        shadowed_tiers=shadowed,
    )


# ---------------------------------------------------------------------------
# (g.3) list_panel_examples  (read)
# ---------------------------------------------------------------------------


def _examples_root() -> Path:
    import scistudio

    package_root = Path(next(iter(scistudio.__path__)))
    return package_root.joinpath(*_EXAMPLES_SUBPATH)


@mcp.tool(name="list_panel_examples", tags={"category:panel", "read"})
async def list_panel_examples(
    capability: Annotated[
        str | None,
        Field(description="Keep only 'displaying' or 'producing' examples. None returns every example."),
    ] = None,
) -> ListPanelExamplesResult:
    """List the worked panel examples in the shipped corpus.

    Use when:
      - You are about to write a panel and want a pattern that already works —
        how a displaying panel renders an envelope, how a producing one emits.

    Do NOT use to:
      - List registered panels — use ``reload_panels``.
      - Read a specific panel's source — use ``read_panel_source``.

    Each entry names the example's directory, so you can copy it into your tier
    under a new ``panel_id`` and edit from there. An empty result is not an
    error: it means this build ships no panel example yet, and the built-in
    panels are the next best pattern (``read_panel_source`` on any ``core.*``
    id).
    """
    root = _examples_root()
    examples: list[PanelExampleEntry] = []
    diagnostics: list[str] = []

    wanted: PanelCapability | None = None
    if capability is not None and capability.strip():
        try:
            wanted = PanelCapability(capability.strip().lower())
        except ValueError as exc:
            raise ValueError(
                f"capability {capability!r} is not one of "
                f"{', '.join(repr(member.value) for member in PanelCapability)}."
            ) from exc

    if not root.is_dir():
        diagnostics.append(f"the examples corpus directory {root} does not exist in this build")
    else:
        for directory in sorted(root.iterdir()):
            if not directory.is_dir() or not (directory / PANEL_DECLARATION_FILENAME).is_file():
                continue
            try:
                manifest = read_panel_declaration(directory)
            except PanelDeclarationError as exc:
                diagnostics.append(exc.message)
                continue
            if wanted is not None and manifest.capability is not wanted:
                continue
            examples.append(
                PanelExampleEntry(
                    example_id=directory.name,
                    display_name=manifest.display_name or manifest.panel_id,
                    capability=manifest.capability.value,
                    target_types=list(manifest.target_types),
                    description=_example_description(directory),
                    path=str(directory),
                    document_path=str(directory / manifest.entry),
                    source="corpus",
                )
            )

    if not examples and not diagnostics:
        diagnostics.append(
            f"the examples corpus at {root} holds no panel example yet; read a built-in panel with "
            f"read_panel_source (for example 'core.series.basic') for a working pattern"
        )

    return ListPanelExamplesResult(
        examples=examples,
        count=len(examples),
        searched=[str(root)],
        diagnostics=diagnostics,
    )


def _example_description(directory: Path) -> str:
    """First non-heading line of the example's README, or an empty string."""
    readme = directory / "README.md"
    if not readme.is_file():
        return ""
    try:
        for line in readme.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                return stripped
    except OSError:  # pragma: no cover - defensive
        return ""
    return ""


# ---------------------------------------------------------------------------
# (g.4) reload_panels  (write)
# ---------------------------------------------------------------------------


@mcp.tool(name="reload_panels", tags={"category:panel", "write"})
async def reload_panels() -> ReloadPanelsResult:
    """Rebuild the panel registry and return every panel it found.

    Use when:
      - You have written, edited, copied or deleted a panel directory. A
        directory added to a tier takes effect on the next rebuild, and this is
        that rebuild — there is no other trigger.

    Do NOT use to:
      - Reload blocks or types — use ``reload_blocks``.

    Returns the panels with their tier, capability and target types, plus every
    refusal the scan produced. A broken declaration is a diagnostic naming the
    directory and the field, never a failed reload: one bad panel must not cost
    you the rest of the tier. If the panel you just wrote is missing, read
    ``diagnostics`` first.
    """
    before, _ = _preview_service(refresh=False)
    before_ids = set(before.panels.panels)

    service, reached = _preview_service(refresh=True)
    discovery = service.panels
    entries = [_entry(panel) for panel in sorted(discovery.all_panels(), key=lambda p: p.manifest.panel_id)]
    after_ids = set(discovery.panels)

    return ReloadPanelsResult(
        panels=entries,
        count=len(entries),
        added=sorted(after_ids - before_ids),
        removed=sorted(before_ids - after_ids),
        diagnostics=list(discovery.diagnostics),
        shadowed=[f"{panel.manifest.panel_id} ({panel.tier.value})" for panel in discovery.shadowed],
        reached_running_gui=reached,
    )


__all__ = ["list_panel_examples", "read_panel_source", "reload_panels", "scaffold_panel"]
