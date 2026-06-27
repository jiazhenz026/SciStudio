"""SubWorkflowBlock — authoring-only container (ADR-044).

ADR-044 makes ``SubWorkflowBlock`` an editor/parser-time concept only. A node of
this type references an external workflow file (``config.ref.path``) and exposes
the referenced file's ``exposed_ports`` so the parent canvas can wire to the
sub-pipeline as if it were a single block. The engine scheduler never observes a
``SubWorkflowBlock``: at run start the parser inline-flattens every reference
into the parent DAG (see :mod:`scistudio.workflow.flatten`).

This class therefore has no runtime behaviour — its :meth:`run` raises. The pre-
ADR-044 nested-execution stub (``_scheduler_factory``, ``_cleanup_callback``,
``_run_with_scheduler``, ``_sequential_execute``, ``input_mapping`` /
``output_mapping``) is deleted (FR-012); issue #890's nested-execution premise
is dissolved by this ADR rather than implemented.
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
    """Authoring-time container that references an external subworkflow file.

    The node renders a single collapsed pipeline on the parent canvas. Its
    effective ports are derived from the referenced file's ``exposed_ports``
    section (FR-004). It has no ``run()``-time behaviour: by the time the
    scheduler runs, :func:`scistudio.workflow.flatten.flatten_subworkflows` has
    replaced it with the referenced workflow's inner nodes (ADR-044 §3, §4).
    """

    name: ClassVar[str] = "Sub-Workflow"
    description: ClassVar[str] = "Reference a workflow file as a single authoring-time node (ADR-044)"

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

    # Ports are dynamic (per referenced file); the static ClassVars are empty
    # and :meth:`get_effective_input_ports` / :meth:`get_effective_output_ports`
    # override the base behaviour.
    input_ports: ClassVar[list[InputPort]] = []
    output_ports: ClassVar[list[OutputPort]] = []

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
        return self._effective_ports("input")

    def get_effective_output_ports(self) -> list[OutputPort]:
        return self._effective_ports("output")

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Never invoked: ADR-044 flattens this node away before dispatch.

        Raising here guards against a regression that lets a ``SubWorkflowBlock``
        reach the scheduler (which would violate SC-001).
        """
        raise RuntimeError(
            "SubWorkflowBlock is authoring-only (ADR-044); it must be inline-flattened "
            "before scheduler dispatch and must never reach run()."
        )


class SubWorkflowBroken(SubWorkflowBlock):
    """Marker emitted when a ``SubWorkflowBlock`` reference cannot resolve.

    ADR-044 §10 / FR-010: a missing or unreadable ``config.ref.path`` does not
    hard-fail editor load — the parser substitutes this marker so the rest
    of the canvas still renders (the editor shows it in the broken-ref style and
    offers a "locate file…" affordance). At run start the validator rejects any
    remaining marker so an unresolved reference cannot be dispatched.
    """

    type_name: ClassVar[str] = "subworkflow_broken"
    name: ClassVar[str] = "Sub-Workflow (broken reference)"
    description: ClassVar[str] = "Unresolved subworkflow reference marker (ADR-044 §10)"

    def get_effective_input_ports(self) -> list[InputPort]:
        return []

    def get_effective_output_ports(self) -> list[OutputPort]:
        return []
