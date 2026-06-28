"""Re-point an existing plot at a new workflow output.

A plot binds one-to-one to a single ``node_id`` + ``output_port``. When the
original block is deleted and re-created it gets a fresh ``node_id``, so the
plot's target goes stale ("broken target") and its data no longer resolves.
``relink_plot`` lets the owner aim an existing plot at a freshly discovered target
without recreating the plot or rewriting its render script.

The relink stays strictly one-to-one: it replaces only the manifest's ``target``
block from a single ``target_id`` (resolved exactly like ``scaffold_plot``). It
never touches the render script or any other manifest field, and it never binds a
plot to more than one source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from scistudio.plot._context import PlotRuntimeContext
from scistudio.plot.models import PlotManifest, PlotManifestTarget
from scistudio.plot.scaffold import render_manifest_yaml
from scistudio.plot.targets import resolve_target_by_id
from scistudio.plot.validation import (
    load_plot,
    validate_plot,
)


class PlotRelinkError(ValueError):
    """Raised when a relink request cannot be satisfied.

    Signals that the requested ``target_id`` does not resolve to any discoverable
    target. A subclass of :class:`ValueError`.
    """


@dataclass
class RelinkOutcome:
    """The result of relinking a plot to a new target.

    Reports the re-written manifest and a fresh validation of the relinked plot,
    so a caller can confirm that a previously broken target now resolves.
    """

    plot_id: str
    """Id of the relinked plot."""
    manifest_path: Path
    """Absolute path of the manifest that was re-written."""
    manifest: PlotManifest
    """The updated manifest after the target was replaced."""
    valid: bool
    """``True`` when the relinked plot validates with no errors."""
    errors: list[str] = field(default_factory=list)
    """Validation errors for the relinked plot, if any."""
    warnings: list[str] = field(default_factory=list)
    """Validation warnings for the relinked plot, if any."""


def relink_plot(ctx: PlotRuntimeContext, plot_id: str, target_id: str) -> RelinkOutcome:
    """Re-point an existing plot at a new target and re-validate it.

    Loads ``plots/<plot_id>/plot.yaml``, resolves ``target_id`` the same way
    ``scaffold_plot`` does, replaces only the manifest's ``target`` block, writes
    the manifest back, then re-validates so the caller can confirm the target now
    resolves. Every other manifest field and the render script are left untouched.

    Args:
        ctx: The injected runtime context.
        plot_id: Id of the existing plot to relink.
        target_id: Id of the new target to bind (from ``list_plot_targets``).

    Returns:
        A :class:`RelinkOutcome` with the updated manifest and a fresh validation.

    Raises:
        PlotNotFoundError: When the plot does not exist.
        PlotRelinkError: When ``target_id`` does not resolve to a discoverable
            target.
    """
    # Load existing manifest (raises PlotNotFoundError when missing).
    loaded = load_plot(ctx, plot_id=plot_id)

    target = resolve_target_by_id(ctx, target_id)
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
    outcome = validate_plot(ctx, plot_id=plot_id)
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
