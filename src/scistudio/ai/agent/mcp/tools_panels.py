"""MCP tools for panels and MiniApps (4 tools)."""
# Maintainer context (kept outside generated API documentation):
# Category (g) MCP tools — the agent's half of the MiniApp loop (4 tools).
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
# * ``list_panels`` lists every panel that already exists (#2441, #2445) — MiniApps,
#   interactive panels, and preview panels, each with the kinds its descriptor
#   declares — so the agent can reuse one, or find one for a block output's type,
#   instead of guessing from the file tree. It reads the same discovery
#   ``open_miniapp`` reads (:func:`_discover`), which is the registry
#   ``GET /api/panels/catalog`` serves: the runtime's panel service, brought up to
#   date with disk first, so every listed ``miniapp`` panel opens and anything
#   that opens is listed (#2421, #2465). A standalone MCP session with no panel
#   service runs the same discovery itself.
# * ``wait_for_answers`` (#2447, MiniApp FR-053) waits for the user to submit a
#   MiniApp questionnaire and returns the answers. An agent in a SciStudio
#   terminal is told about a submit in its own chat; an agent in the user's own
#   AI app (External AI / WebMCP) has no such channel, so it waits here. It only
#   reads ``answers.json``, the source of truth the submit route writes, so a
#   cancelled or timed-out wait loses nothing.
#
# ``validate_panel`` also runs the questionnaire check whenever the directory
# holds a questionnaire, so a questionnaire cannot pass validation untested.
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

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Annotated, Any, cast

from pydantic import BaseModel, Field

from scistudio.ai.agent.mcp._context import _resolve_project_path, _resolve_project_root, get_context
from scistudio.ai.agent.mcp.server import mcp
from scistudio.core.dropins import panel_scan_dirs
from scistudio.panels.descriptor import PANEL_CONTEXTS, PanelDescriptor, parse_descriptor
from scistudio.panels.files import validate_external_references
from scistudio.panels.questionnaire import ANSWERS_FILE, QUESTIONNAIRE_FILE, check_questionnaire
from scistudio.panels.registry import PanelRegistry, discover_panels
from scistudio.panels.targets import type_chain
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

#: Bounds on the ``invalid`` half of a ``list_panels`` result. A panels tier
#: full of half-written directories must not drown the list the agent asked for.
_MAX_INVALID_DIRECTORIES = 20
_MAX_DIAGNOSTICS_PER_DIRECTORY = 5
_MAX_DIAGNOSTIC_CHARS = 500


#: ``wait_for_answers`` bounds, in seconds.
WAIT_DEFAULT_SECONDS = 300
WAIT_MAX_SECONDS = 1800
_WAIT_POLL_SECONDS = 1.0

SUBMITTED = "submitted"
TIMED_OUT = "timed_out"


class QuestionnaireReport(BaseModel):
    """What ``validate_panel``'s questionnaire check exercised."""

    questions: int = Field(description="How many questions questionnaire.json declares (0 when it did not parse).")
    statuses_exercised: list[str] = Field(
        default_factory=list,
        description="Answer statuses the sample submits produced: answered, decide_for_me, skipped.",
    )
    round_trip: bool = Field(
        description=(
            "True when sample submits — mixed answers, 'Decide for me' on every question, and nothing "
            "answered — each produced a well-formed answers.json document with one entry per question."
        )
    )


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
    questionnaire: QuestionnaireReport | None = Field(
        default=None,
        description=(
            "Present when the directory holds questionnaire.json or a page using the Questionnaire component; "
            "its problems are in errors."
        ),
    )
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


class PanelSummary(BaseModel):
    """One discovered panel in a ``list_panels`` result."""

    panel_id: str = Field(
        description="The panel id — the directory name under panels/; open_miniapp takes it for a 'miniapp' panel."
    )
    name: str = Field(description="Display name from panel.json (the id when none is declared).")
    description: str = Field(default="", description="Description from panel.json.")
    kinds: list[str] = Field(
        description=(
            "The contexts panel.json declares, in the order 'preview', 'interactive', 'miniapp'. A panel "
            "may declare several: 'miniapp' opens in a MiniApp tab (open_miniapp), 'interactive' is the "
            "page of an interactive block, 'preview' is a previewer the workspace routes data outputs to."
        )
    )
    tier: str = Field(description="Owner tier: 'project', 'user', 'package', or 'core'.")
    package: str | None = Field(
        default=None,
        description="Name of the package entry point that ships the panel; None outside the package tier.",
    )
    types: list[str] = Field(
        description=(
            "Declared data types, verbatim, e.g. 'Image' or 'Collection[Image]'. A MiniApp declares exactly "
            "one; a preview panel at least one; an interactive panel may declare none."
        )
    )
    entry: str = Field(description="The page the host loads, relative to the panel directory.")
    has_python: bool = Field(description="True when the directory carries a panel.py.")
    path: str = Field(description="Panel directory: project-relative when inside the project, absolute otherwise.")
    priority: int | None = Field(
        default=None,
        description=(
            "Preview routing priority from panel.json (higher wins among previewers for the same type); "
            "None for a panel that does not declare the 'preview' context."
        ),
    )


class InvalidPanelDirectory(BaseModel):
    """A directory under a panels tier that discovery skipped."""

    panel_id: str = Field(description="The directory name — the id discovery expected.")
    tier: str = Field(description="Tier the directory sits in: 'project' or 'user'.")
    path: str = Field(description="The directory: project-relative when inside the project, absolute otherwise.")
    diagnostics: list[str] = Field(
        description="Why discovery skipped it, naming the rule and the field to fix. Bounded; run validate_panel for the full text."
    )


class ListPanelsResult(BaseModel):
    """Result envelope for ``list_panels``."""

    panels: list[PanelSummary] = Field(
        description=(
            "Every discovered panel matching the filters, sorted by name. Only panels whose kinds include "
            "'miniapp' open with open_miniapp."
        )
    )
    kind: str | None = Field(
        default=None,
        description="The kind filter that was applied, or None when every kind is listed.",
    )
    data_type: str | None = Field(
        default=None,
        description="The data_type filter that was applied, or None when every type is listed.",
    )
    invalid: list[InvalidPanelDirectory] = Field(
        default_factory=list,
        description=(
            "Directories under the project and user panels tiers that discovery skipped. They are "
            "not panels of any kind until fixed. Not filtered by kind or data_type."
        ),
    )
    invalid_truncated: int = Field(
        default=0,
        description="How many further skipped directories were left out of ``invalid`` to keep the result bounded.",
    )
    next_step: str = Field(
        default=(
            "To show a listed panel whose kinds include 'miniapp' on a block output, call open_miniapp with its "
            "panel_id; the output's type must match its declared type. Interactive and preview panels are not "
            "opened with open_miniapp: an interactive panel opens from its block, and a preview panel is chosen "
            "by the workspace when it previews a matching output. To fix an entry in invalid, edit it and run "
            "validate_panel on its path."
        ),
        description="Suggested next MCP call.",
    )


def _discover(ctx: Any) -> PanelRegistry:
    """The panel catalog ``open_miniapp`` and ``list_panels`` share.

    Inside the application this is the runtime panel service's catalog, the one
    the workspace opens panels from, brought up to date with the panel folders
    first. A standalone session has no panel service and runs the same
    discovery against the live type registry.
    """
    get_service = getattr(ctx, "get_panel_service", None)
    if callable(get_service):
        service = get_service()
        service.ensure_fresh()
        return cast(PanelRegistry, service.registry())
    return discover_panels(
        getattr(ctx, "project_dir", None),
        registered_types=tuple(ctx.type_registry.all_types().keys()),
    )


def _display_path(path: Path, project_root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _claim_accepts(ctx: Any, claim: str, data_type: str) -> bool:
    """True when a declared type ``claim`` accepts an output of ``data_type``.

    The rule is ``scistudio.panels.miniapp._check_type``'s, applied to a type
    name instead of a frozen output: a claim of ``T`` accepts ``T`` or a subtype,
    ``Collection[T]`` a collection whose item type is ``T`` or a subtype, and
    bare ``Collection`` any collection.
    """
    claim = claim.strip()
    if claim.startswith("Collection[") and claim.endswith("]"):
        name, is_collection = claim[11:-1].strip(), True
    elif claim == "Collection":
        name, is_collection = "", True
    else:
        name, is_collection = claim, False
    requested = data_type.strip()
    if requested == "Collection" or (requested.startswith("Collection[") and requested.endswith("]")):
        if not is_collection:
            return False
        item_type = requested[11:-1].strip() if requested != "Collection" else ""
        chain = type_chain(ctx, item_type) if item_type else ()
        return not name or name == item_type or name in chain
    if is_collection:
        return False
    return name == requested or name in type_chain(ctx, requested)


def _accepts(ctx: Any, panel: PanelDescriptor, data_type: str) -> bool:
    """True when any of the panel's declared types accepts an output of ``data_type``.

    A panel declaring no types (an interactive panel may) matches no data type.
    """
    return any(_claim_accepts(ctx, claim, data_type) for claim in panel.types)


def _invalid_directories(
    ctx: Any, registry: PanelRegistry, project_root: Path
) -> tuple[list[InvalidPanelDirectory], int]:
    """Directories in the project and user panels tiers that discovery skipped."""
    discovered = {panel.root for panel in registry.panels.values()} | {panel.root for panel in registry.shadowed}
    roots = panel_scan_dirs(getattr(ctx, "project_dir", None))
    tiers = [(roots[0], OwnerKind.PROJECT.value), (roots[-1], OwnerKind.USER.value)]
    found: list[InvalidPanelDirectory] = []
    skipped = 0
    seen: set[Path] = set()
    for root, tier in tiers:
        if root in seen or not root.is_dir():
            continue
        seen.add(root)
        for child in sorted(root.iterdir()):
            if not child.is_dir() or child.name.startswith(".") or child.resolve() in discovered:
                continue
            if len(found) >= _MAX_INVALID_DIRECTORIES:
                skipped += 1
                continue
            prefix = f"{child}: "
            notes = [entry[len(prefix) :] for entry in registry.diagnostics if entry.startswith(prefix)]
            notes = notes or ["not discovered as a panel; run validate_panel on this directory"]
            found.append(
                InvalidPanelDirectory(
                    panel_id=child.name,
                    tier=tier,
                    path=_display_path(child, project_root),
                    diagnostics=[note[:_MAX_DIAGNOSTIC_CHARS] for note in notes[:_MAX_DIAGNOSTICS_PER_DIRECTORY]],
                )
            )
    return found, skipped


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

      - You have written or changed a MiniApp questionnaire. When the directory
        holds ``questionnaire.json`` (or a page using the ``Questionnaire``
        component) this also runs the questionnaire check: the spec is valid,
        every question has a type the component draws and "Decide for me",
        no question is required, the page wires ``Questionnaire``,
        ``questionnaire.json`` and ``scistudio.submitAnswers`` together, and
        sample submits produce a well-formed ``answers.json``. Fix every error
        it names and run it again until ``valid`` is True.

    Do NOT use to:
      - Check a page's JavaScript in general — beyond the questionnaire wiring
        this reads ``panel.json`` and scans the page files for external
        references; it never runs the page.
      - List MiniApps or other panels — use ``list_panels``.
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

    checked = check_questionnaire(directory, panel_id=panel.id, contexts=tuple(panel.contexts), entry=panel.entry)
    report = (
        QuestionnaireReport(
            questions=checked.question_count,
            statuses_exercised=checked.statuses_exercised,
            round_trip=checked.round_trip,
        )
        if checked.present
        else None
    )
    return ValidatePanelResult(
        path=str(directory),
        valid=not checked.errors,
        panel_id=panel.id,
        contexts=list(panel.contexts),
        types=list(panel.types),
        entry=panel.entry,
        has_python=panel.has_python,
        questionnaire=report,
        errors=[f"{directory}: {error}" for error in checked.errors],
        warnings=[f"{directory}: {note}" for note in notes],
    )


@mcp.tool(name="list_panels", tags={"category:panels", "read"})
async def list_panels(
    kind: Annotated[
        str | None,
        Field(
            description=(
                "Only list panels declaring this context: 'miniapp', 'interactive', or 'preview'. Omit to list every kind."
            )
        ),
    ] = None,
    data_type: Annotated[
        str | None,
        Field(
            description=(
                "Only list panels that accept an output of this type, e.g. 'Image' or 'Collection[Image]' — a "
                "panel declaring a parent type is included. Panels declaring no types are left out. Omit to list all."
            )
        ),
    ] = None,
) -> ListPanelsResult:
    """List the panels that already exist — MiniApps, interactive panels, previewers — and the directories that failed discovery.

    Use when:
      - The user asks what MiniApps, interactive panels, or previewers they
        have, or asks to open or change an existing one and you need its
        ``panel_id``.
      - Before writing a new panel, to check whether one for that data type
        already exists — pass the block output's type as ``data_type`` and the
        kind you would write as ``kind``.
      - A panel the user expects is missing: ``invalid`` names the directories
        discovery skipped and why.

    Do NOT use to:
      - Check one directory in full — use ``validate_panel``; ``invalid`` only
        carries a bounded excerpt of its diagnostics.
      - Open a MiniApp — use ``open_miniapp`` with the ``panel_id`` of a listed
        panel whose ``kinds`` include ``miniapp``. Interactive and preview
        panels are not opened with ``open_miniapp``.
      - Find the block outputs a panel can open on — use ``get_block_output``.

    Each panel's ``kinds`` are the contexts its ``panel.json`` declares; a panel
    may declare several. The list covers the project, user, package, and core
    tiers, reading the same discovery ``open_miniapp`` reads and the same
    registry the panel catalog serves: every listed panel whose ``kinds``
    include ``miniapp`` is one ``open_miniapp`` accepts. Where two tiers ship
    the same id, only the one that wins (project over user over package over
    core) is listed. Raises ``ValueError`` for an unknown ``kind`` and
    ``RuntimeError`` when no project is open.
    """
    wanted_kind = kind.strip() if kind and kind.strip() else None
    if wanted_kind is not None and wanted_kind not in PANEL_CONTEXTS:
        raise ValueError(f"Unknown panel kind '{kind}'. Pass one of {list(PANEL_CONTEXTS)}, or omit kind.")
    ctx = get_context()
    project_root = _resolve_project_root(ctx)
    registry = _discover(ctx)
    wanted = data_type.strip() if data_type and data_type.strip() else None

    panels = [
        PanelSummary(
            panel_id=panel.id,
            name=panel.name or panel.id,
            description=panel.description,
            kinds=[context for context in PANEL_CONTEXTS if context in panel.contexts],
            tier=panel.owner_kind.value,
            package=panel.owner_name if panel.owner_kind is OwnerKind.PACKAGE else None,
            types=list(panel.types),
            entry=panel.entry,
            has_python=panel.has_python,
            path=_display_path(panel.root, project_root),
            priority=panel.priority if "preview" in panel.contexts else None,
        )
        for panel in sorted(registry.panels.values(), key=lambda p: ((p.name or p.id).lower(), p.id))
        if (wanted_kind is None or wanted_kind in panel.contexts) and (wanted is None or _accepts(ctx, panel, wanted))
    ]
    invalid, truncated = _invalid_directories(ctx, registry, project_root)
    return ListPanelsResult(
        panels=panels, kind=wanted_kind, data_type=wanted, invalid=invalid, invalid_truncated=truncated
    )


class WaitForAnswersResult(BaseModel):
    """Result envelope for ``wait_for_answers``."""

    status: str = Field(description="'submitted' when answers are ready; 'timed_out' when the wait ended first.")
    panel_id: str = Field(description="The MiniApp whose questionnaire was waited on.")
    answers_path: str = Field(description="answers.json: project-relative when inside the project, absolute otherwise.")
    waited_seconds: float = Field(description="How long this call waited.")
    submitted_at: str | None = Field(default=None, description="When the user submitted (UTC, ISO 8601).")
    title: str | None = Field(default=None, description="The questionnaire title.")
    answers: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "One entry per question, in order: {id, type, prompt, status, value?, label?, labels?, other?}. "
            "status is 'answered', 'decide_for_me' (choose for the user), or 'skipped' (choose sensibly). "
            "Empty unless status is 'submitted'."
        ),
    )
    detail: str = Field(description="What happened.")
    next_step: str = Field(description="What to do now.")


def _questionnaire_dir(ctx: Any, panel_id: str) -> Path:
    panel = _discover(ctx).get(panel_id)
    if panel is not None:
        return Path(panel.root)
    candidate = _resolve_project_root(ctx) / "panels" / panel_id
    if candidate.is_dir():
        return candidate
    raise KeyError(
        f"No MiniApp with id '{panel_id}' was found. Pass the directory name under panels/, "
        "and run validate_panel on it first."
    )


def _fresh_answers(directory: Path) -> dict[str, Any] | None:
    """The answers document when it was submitted after the questionnaire was last written."""
    answers, spec = directory / ANSWERS_FILE, directory / QUESTIONNAIRE_FILE
    try:
        if not answers.is_file() or (spec.is_file() and answers.stat().st_mtime < spec.stat().st_mtime):
            return None
        document = json.loads(answers.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return document if isinstance(document, dict) and isinstance(document.get("answers"), list) else None


@mcp.tool(name="wait_for_answers", tags={"category:panels", "read"})
async def wait_for_answers(
    panel_id: Annotated[
        str,
        Field(
            description="Id of the MiniApp whose questionnaire the user is filling in — the directory name under panels/."
        ),
    ],
    timeout_seconds: Annotated[
        int,
        Field(
            ge=1,
            le=WAIT_MAX_SECONDS,
            description=f"How long to wait for the submit, in seconds. Defaults to {WAIT_DEFAULT_SECONDS}.",
        ),
    ] = WAIT_DEFAULT_SECONDS,
) -> WaitForAnswersResult:
    """Wait for the user to submit a MiniApp questionnaire, then return the answers.

    Use when:
      - You have written a MiniApp questionnaire, ``validate_panel`` passes, and
        the user has it open. Call this right away; it returns as soon as they
        press Submit.
      - You are working from the user's own AI app (External AI mode). An agent
        in a SciStudio terminal session is told about the submit in its chat and
        does not need this.

    Do NOT use to:
      - Check the questionnaire — that is ``validate_panel``.
      - Read answers you were already told about — read ``answers.json``.

    Returns immediately when ``answers.json`` is newer than
    ``questionnaire.json``, so a submit made before this call is not missed and
    answers to an older questionnaire are not mistaken for new ones.

    If the result is ``timed_out`` the user has not finished yet. Tell the user
    that your watch on the questionnaire timed out, and ask them to tell you once
    they have filled it in and pressed Submit; then read the answers (call this
    again, or read ``answers.json``). Nothing is lost by the timeout or by
    cancelling this call: the submit writes ``answers.json`` whenever it happens.
    Raises ``KeyError`` for an unknown MiniApp and ``RuntimeError`` when no
    project is open.
    """
    ctx = get_context()
    project_root = _resolve_project_root(ctx)
    directory = _questionnaire_dir(ctx, panel_id)
    display = _display_path(directory / ANSWERS_FILE, project_root)
    started = time.monotonic()
    deadline = started + timeout_seconds
    while True:
        document = _fresh_answers(directory)
        if document is not None:
            return WaitForAnswersResult(
                status=SUBMITTED,
                panel_id=panel_id,
                answers_path=display,
                waited_seconds=round(time.monotonic() - started, 1),
                submitted_at=document.get("submitted_at"),
                title=document.get("title"),
                answers=document["answers"],
                detail=f"The user submitted the questionnaire for '{panel_id}'.",
                next_step=(
                    "Build the MiniApp from these answers. Where status is 'decide_for_me' or 'skipped', choose "
                    "sensibly yourself. Then run validate_panel."
                ),
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        await asyncio.sleep(min(_WAIT_POLL_SECONDS, remaining))
    return WaitForAnswersResult(
        status=TIMED_OUT,
        panel_id=panel_id,
        answers_path=display,
        waited_seconds=round(time.monotonic() - started, 1),
        detail=f"No submit arrived for '{panel_id}' within {timeout_seconds} seconds.",
        next_step=(
            "Tell the user your watch on the questionnaire timed out, and ask them to tell you once they have "
            "filled it in and pressed Submit. Then call wait_for_answers again or read answers_path."
        ),
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
    registry = _discover(ctx)
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
    "InvalidPanelDirectory",
    "ListPanelsResult",
    "OpenMiniAppResult",
    "PanelSummary",
    "QuestionnaireReport",
    "ValidatePanelResult",
    "WaitForAnswersResult",
    "list_panels",
    "open_miniapp",
    "validate_panel",
    "wait_for_answers",
]
