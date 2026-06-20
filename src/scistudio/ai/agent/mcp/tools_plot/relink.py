"""Relink a plot to a new workflow output target (bug#7).

A plot binds 1:1 to one ``node_id`` + ``output_port`` (``PlotManifestTarget``).
When the original block is deleted and re-created it gets a fresh ``node_id``,
so the plot's target goes stale ("broken target") and its data no longer
resolves. ``relink_plot`` lets the owner point an existing plot at a freshly
discovered target without recreating the plot or its render script.

This stays strictly 1:1: it rewrites only the manifest ``target`` block from a
single ``target_id`` (resolved exactly like ``scaffold_plot``). It never edits
the render script, the script binding shape, or any other manifest field.
Multi-source binding (many blocks -> one plot) is explicitly out of scope here.

This module sits beside :mod:`scaffold` (pure helpers, no MCP decorators) so the
HTTP route and any future MCP tool can both reuse it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from scistudio.ai.agent.mcp.tools_plot.models import PlotManifest, PlotManifestTarget
from scistudio.ai.agent.mcp.tools_plot.scaffold import render_manifest_yaml
from scistudio.ai.agent.mcp.tools_plot.targets import resolve_target_by_id
from scistudio.ai.agent.mcp.tools_plot.validation import (
    load_plot,
    validate_plot,
)


class PlotRelinkError(ValueError):
    """Raised when a relink request cannot be satisfied (unknown target_id)."""


@dataclass
class RelinkOutcome:
    """Outcome of relinking a plot's data source.

    ``manifest`` is the updated, re-written manifest. ``valid`` plus
    ``errors``/``warnings`` reflect a fresh validation of the relinked plot so
    callers can confirm a previously broken target is now valid.
    """

    plot_id: str
    manifest_path: Path
    manifest: PlotManifest
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def relink_plot(plot_id: str, target_id: str) -> RelinkOutcome:
    """Re-point an existing plot at a new ``target_id`` (bug#7, strict 1:1).

    Loads ``plots/<plot_id>/plot.yaml``, resolves ``target_id`` the same way
    ``scaffold_plot`` does, replaces only the manifest ``target`` block, writes
    the manifest back, then re-validates so the caller can see the (now)
    resolved target.

    Raises :class:`~scistudio.ai.agent.mcp.tools_plot.validation.PlotNotFoundError`
    when the plot does not exist and :class:`PlotRelinkError` when ``target_id``
    does not resolve to a discoverable target.
    """
    # Load existing manifest (raises PlotNotFoundError when missing).
    loaded = load_plot(plot_id=plot_id)

    target = resolve_target_by_id(target_id)
    if target is None:
        raise PlotRelinkError(
            f"unknown target_id {target_id!r}: choose a block output from list_plot_targets. "
            "A plot must bind to a node_id + output_port, never a label."
        )

    manifest = loaded.manifest
    # Replace ONLY the target block; every other field is preserved verbatim.
    updated = manifest.model_copy(
        update={
            "target": PlotManifestTarget(
                workflow_path=target.workflow_path,
                workflow_id=target.workflow_id,
                node_id=target.node_id,
                output_port=target.output_port,
                display_label=target.node_label,
            )
        }
    )

    loaded.manifest_path.write_text(render_manifest_yaml(updated), encoding="utf-8")

    # Re-validate the relinked plot so a previously broken target reports valid.
    outcome = validate_plot(plot_id=plot_id)
    return RelinkOutcome(
        plot_id=updated.id,
        manifest_path=loaded.manifest_path,
        manifest=outcome.manifest or updated,
        valid=outcome.valid,
        errors=list(outcome.errors),
        warnings=list(outcome.warnings),
    )


__all__ = [
    "PlotRelinkError",
    "RelinkOutcome",
    "relink_plot",
]
