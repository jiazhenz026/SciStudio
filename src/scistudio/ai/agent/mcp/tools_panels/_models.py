"""Result envelopes for the four panel tools (ADR-054 spec 5 FR-014 to FR-018).

Kept beside the tools rather than in :mod:`scistudio.panels`: these are the
*agent's* view of a panel — paths it can open, a URL it can browse to, and the
next call to make — not the panel subsystem's own types, and putting them in the
subsystem would make the panel runtime carry a dependency on how one client
prefers to be told things.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "DiscoveredPanelEntry",
    "ListPanelExamplesResult",
    "PanelExampleEntry",
    "ReadPanelSourceResult",
    "ReloadPanelsResult",
    "ScaffoldPanelResult",
]


class ScaffoldPanelResult(BaseModel):
    """Result envelope for ``scaffold_panel`` (FR-014, FR-015)."""

    panel_id: str = Field(description="The scaffolded panel's stable id.")
    tier: str = Field(description="Tier the panel was written into: 'project' or 'user'.")
    directory: str = Field(description="Absolute path of the panel directory.")
    declaration_path: str = Field(description="Absolute path of the written panel.json.")
    document_path: str = Field(description="Absolute path of the written entry document.")
    harness_path: str = Field(
        description=(
            "Absolute path of the standalone harness. Open this file directly in a browser "
            "(file:// URL) to see the panel render over stub data and to capture what it emits."
        )
    )
    harness_url: str | None = Field(
        default=None,
        description=(
            "The harness's URL on the running GUI, once the panel is registered by reload_panels. "
            "None when no GUI server is reachable for this session; use harness_path instead."
        ),
    )
    files_written: list[str] = Field(
        default_factory=list, description="The three files written, in declaration/document/harness order."
    )
    capability: str = Field(description="The declared capability: 'displaying' or 'producing'.")
    target_types: list[str] = Field(default_factory=list, description="The recorded type names the panel claims.")
    warnings: list[str] = Field(
        default_factory=list,
        description=(
            "Soft advisory notes to review before editing: unregistered target types, a displaying "
            "capability that makes the harness's emission pane permanently empty, and the like."
        ),
    )
    next_step: str = Field(
        default=(
            "Open harness_path in a browser (use open_gui plus harness_url when the GUI is running) and "
            "confirm the panel renders and emits. Edit document_path, then call reload_panels to register it."
        ),
        description="Suggested next action after scaffolding.",
    )


class ReadPanelSourceResult(BaseModel):
    """Result envelope for ``read_panel_source`` (FR-016)."""

    panel_id: str = Field(description="The panel's id.")
    tier: str = Field(description="The tier the panel resolved from: core, package, user, or project.")
    directory: str = Field(description="Absolute path of the panel directory it resolved from.")
    declaration: dict[str, Any] = Field(description="The validated panel.json body, as the runtime read it.")
    entry: str = Field(description="The entry document's filename inside the directory.")
    document: str = Field(description="Full text of the entry document.")
    document_path: str = Field(description="Absolute path of the entry document.")
    harness_path: str | None = Field(default=None, description="Absolute path of the panel's harness, when it has one.")
    read_only: bool = Field(
        description=(
            "True for the core and package tiers, which are read-only: edit one by copying it into the "
            "project or user tier under the same id, which shadows the original."
        )
    )
    shadowed_tiers: list[str] = Field(
        default_factory=list,
        description="Tiers that also declare this id and lost the shadowing order, highest-priority first.",
    )


class PanelExampleEntry(BaseModel):
    """One entry in the ``list_panel_examples`` result."""

    example_id: str = Field(description="Stable id of the example, usable as a directory name.")
    display_name: str = Field(description="The example's display name.")
    capability: str = Field(description="'displaying' or 'producing'.")
    target_types: list[str] = Field(default_factory=list, description="Recorded type names the example claims.")
    description: str = Field(default="", description="One line saying what the example demonstrates.")
    path: str = Field(description="Absolute path of the example's directory.")
    document_path: str = Field(description="Absolute path of the example's entry document.")
    source: str = Field(description="Where the example came from. Always 'corpus' today.")


class ListPanelExamplesResult(BaseModel):
    """Result envelope for ``list_panel_examples`` (FR-017)."""

    examples: list[PanelExampleEntry] = Field(default_factory=list, description="The examples found.")
    count: int = Field(description="Number of examples returned.")
    searched: list[str] = Field(
        default_factory=list, description="The directories that were searched, whether or not they existed."
    )
    diagnostics: list[str] = Field(
        default_factory=list, description="Why a searched location contributed nothing, when it did not."
    )
    next_step: str = Field(
        default=(
            "Read an example with read_panel_source, or copy its directory into your tier under a new "
            "panel_id. Call scaffold_panel when none of them is close enough to start from."
        ),
        description="Suggested next action.",
    )


class DiscoveredPanelEntry(BaseModel):
    """One panel the registry rebuild found."""

    panel_id: str = Field(description="The panel's id.")
    display_name: str = Field(description="The name a person sees in the panel palette.")
    tier: str = Field(description="Tier it resolved from: core, package, user, or project.")
    capability: str = Field(description="'displaying' or 'producing'.")
    target_types: list[str] = Field(default_factory=list, description="Recorded type names the panel claims.")
    directory: str = Field(description="Absolute path of the panel directory.")
    entry: str = Field(description="The entry document's filename.")
    api_version: str = Field(description="The panel API version the declaration states.")
    owner: str = Field(default="", description="Declaring distribution, for a package-tier panel.")


class ReloadPanelsResult(BaseModel):
    """Result envelope for ``reload_panels`` (FR-018)."""

    panels: list[DiscoveredPanelEntry] = Field(default_factory=list, description="Every panel after the rebuild.")
    count: int = Field(description="Number of panels discovered.")
    added: list[str] = Field(default_factory=list, description="Panel ids the rebuild added.")
    removed: list[str] = Field(default_factory=list, description="Panel ids the rebuild dropped.")
    diagnostics: list[str] = Field(
        default_factory=list,
        description=(
            "Every refusal from the scan, in discovery order: a declaration missing a field, a duplicate "
            "id inside one tier, a provider that would not import. A broken panel is a diagnostic here, "
            "never a failed reload."
        ),
    )
    shadowed: list[str] = Field(
        default_factory=list,
        description="'<panel_id> (<tier>)' for each declaration a lower tier shadowed.",
    )
    reached_running_gui: bool = Field(
        description=(
            "Whether the rebuild reached the preview service the running GUI reads. False means the rebuild "
            "was process-local: the panel is registered for this agent session, and the GUI picks it up on "
            "its own next rebuild."
        )
    )
    next_step: str = Field(
        default=(
            "If your panel is missing, read diagnostics for the refusal naming its directory. Otherwise open "
            "the panel from the data it targets, or read it back with read_panel_source."
        ),
        description="Suggested next action after a rebuild.",
    )
