"""Authoring-time block that references another workflow file.

A :class:`SubWorkflowBlock` node points at an external workflow file and shows
that file's exposed input/output ports, so the parent canvas can wire to the
referenced pipeline as if it were a single block. It exists only while editing
and parsing a workflow: when a run starts, the parser replaces each reference
with the referenced workflow's own nodes (see
:mod:`scistudio.workflow.flatten`), so the scheduler never sees a
:class:`SubWorkflowBlock`. The class therefore has no run-time behaviour — its
:meth:`run` always raises.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort

if TYPE_CHECKING:
    from scistudio.core.types.collection import Collection

logger = logging.getLogger(__name__)


class SubWorkflowBlock(Block):
    """A collapsed reference to another workflow, shown as one node.

    Drop this on a canvas and point it at a workflow file to reuse that whole
    pipeline as a single step. Its input and output ports are taken from the
    referenced file's exposed-ports section, so you can wire to it like any
    other block. It does nothing at run time: before the scheduler runs,
    :func:`scistudio.workflow.flatten.flatten_subworkflows` swaps the node for
    the referenced workflow's inner nodes.

    Example:
        >>> block = SubWorkflowBlock({"ref": {"path": "pipelines/clean.yaml"}})
        >>> block.get_effective_input_ports()  # ports exposed by clean.yaml
    """

    name: ClassVar[str] = "Sub-Workflow"
    """Display name shown for this block in the palette and on its node."""
    description: ClassVar[str] = "Reference a workflow file as a single authoring-time node"
    """One-line description shown in the block palette."""

    # ADR-044 §5: a SubWorkflowBlock stores only a *reference* to an external
    # file (``config.ref.path``), never an embedded copy. ``ref.path`` is a
    # nested key (NOT a top-level ``file_browser`` widget) so the serializer's
    # path-relativify machinery leaves it untouched; it stays project-relative
    # on disk and is resolved against the project root by the flattener and the
    # effective-ports resolver.
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "ref": {
                "type": "object",
                "title": "Subworkflow reference",
                "properties": {
                    "path": {
                        "type": "string",
                        "title": "Subworkflow file",
                        "description": "Project-relative path to the referenced workflow YAML.",
                        "ui_widget": "subworkflow_picker",
                        "ui_priority": 0,
                    },
                },
            },
        },
    }
    """Form schema for the block's config: just the referenced workflow file."""

    # Ports are dynamic (per referenced file); the static ClassVars are empty
    # and :meth:`get_effective_input_ports` / :meth:`get_effective_output_ports`
    # override the base behaviour.
    input_ports: ClassVar[list[InputPort]] = []
    """Empty by default; the effective input ports come from the referenced file."""
    output_ports: ClassVar[list[OutputPort]] = []
    """Empty by default; the effective output ports come from the referenced file."""

    # -- ADR-044 FR-004: dynamic ports from the referenced exposed_ports -------

    def _ref_path(self) -> str | None:
        ref = self.config.get("ref")
        if isinstance(ref, dict):
            path = ref.get("path")
            if isinstance(path, str) and path.strip():
                return path
        return None

    def _base_dir(self) -> str:
        """Resolve the project root used to resolve ``config.ref.path``.

        Mirrors ``workflow.validator._project_dir_for_workflow``: an explicit
        ``project_dir`` (under ``params`` or top-level config) when present,
        else the current working directory. The API route resolves the
        authoritative typed surface with the runtime registry; this method is
        the block-local best-effort path (accept-any types).
        """
        params = self.config.get("params")
        if isinstance(params, dict) and params.get("project_dir"):
            return str(params["project_dir"])
        top_level = self.config.get("project_dir")
        if top_level:
            return str(top_level)
        return "."

    def _effective_ports(self, direction: str) -> list[Any]:
        from scistudio.workflow.subworkflow_ports import resolve_port_surface

        surface = resolve_port_surface(self._ref_path(), self._base_dir(), registry=None)
        entries = surface["inputs"] if direction == "input" else surface["outputs"]
        ports: list[Any] = []
        for entry in entries:
            if direction == "input":
                ports.append(InputPort(name=entry["name"], accepted_types=[], required=False))
            else:
                ports.append(OutputPort(name=entry["name"], accepted_types=[]))
        return ports

    def get_effective_input_ports(self) -> list[InputPort]:
        """Return the input ports declared by the referenced workflow file.

        Returns:
            One :class:`InputPort` per input the referenced workflow exposes;
            empty when the reference is missing or cannot be read.
        """
        return self._effective_ports("input")

    def get_effective_output_ports(self) -> list[OutputPort]:
        """Return the output ports declared by the referenced workflow file.

        Returns:
            One :class:`OutputPort` per output the referenced workflow exposes;
            empty when the reference is missing or cannot be read.
        """
        return self._effective_ports("output")

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Never runs: this block is replaced before the scheduler dispatches it.

        A :class:`SubWorkflowBlock` is flattened into the referenced workflow's
        nodes before execution, so this method should never be called. It raises
        to catch the bug where an un-flattened node reaches the scheduler.

        Args:
            inputs: Unused.
            config: Unused.

        Raises:
            RuntimeError: Always, because this block must be flattened before
                dispatch.
        """
        raise RuntimeError(
            "SubWorkflowBlock is authoring-only (ADR-044); it must be inline-flattened "
            "before scheduler dispatch and must never reach run()."
        )


class SubWorkflowBroken(SubWorkflowBlock):
    """Marker node used when a sub-workflow reference cannot be resolved.

    When a :class:`SubWorkflowBlock`'s referenced file is missing or unreadable,
    the parser substitutes this marker instead of failing the whole editor load,
    so the rest of the canvas still renders (the editor shows it in a broken-ref
    style and offers a "locate file…" option). At run start the validator
    rejects any remaining marker, so an unresolved reference can never be
    dispatched.
    """

    type_name: ClassVar[str] = "subworkflow_broken"
    """Stable identifier used to recognise this marker block type."""
    name: ClassVar[str] = "Sub-Workflow (broken reference)"
    """Display name shown for the broken-reference marker."""
    description: ClassVar[str] = "Unresolved subworkflow reference marker"
    """One-line description shown in the block palette."""

    def get_effective_input_ports(self) -> list[InputPort]:
        """Return no input ports (a broken reference exposes none)."""
        return []

    def get_effective_output_ports(self) -> list[OutputPort]:
        """Return no output ports (a broken reference exposes none)."""
        return []
