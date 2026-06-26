"""ADR-051: the interaction capability for data-processing blocks.

An interactive block pauses mid-workflow, opens a block-owned window onto its
real input data, takes a data-dependent decision from the user, and computes
its outputs from it. Interaction is a *capability* any block category can carry
(ADR-051 §2), expressed by mixing in :class:`InteractiveMixin` and declaring
``execution_mode = ExecutionMode.INTERACTIVE``. There is deliberately no
``InteractiveBlock`` base class — interactivity is layered onto an existing
category (e.g. :class:`~scistudio.blocks.process.process_block.ProcessBlock`)
rather than placed on the category axis.

The capability gives a block three things (ADR-051 §2):

* :attr:`InteractiveMixin.interactive_panel` — a :class:`PanelManifest` naming
  the frontend window component, served and resolved through the same
  same-origin mechanism ADR-048 uses for previewer components (ADR-051 §4).
* :meth:`InteractiveMixin.prepare_prompt` — turns the real input data into the
  JSON-safe, window-sized view the panel renders, plus optional heavy
  intermediate work carried forward as storage references (never in memory).
* ``run`` — the block's own, inherited from its category; on the compute phase
  it reads the user's decision from ``config["interactive_response"]`` and
  produces the block's outputs (ADR-051 §3).

The registry binds the capability and the execution mode together at scan time
(see :func:`scistudio.blocks.registry._capability._validate_interactive_capability`):
a block that declares one without the other, omits ``prepare_prompt``, or omits
a valid :class:`PanelManifest` is rejected at load time (FR-002).

Runtime isolation (ADR-051 §3): the two halves run in two worker subprocesses
on either side of an engine-held pause — the prompt phase builds the view and
exits, the engine holds the pause with nothing resident, then a fresh compute
phase runs ``run`` with the decision injected. This module only defines the
contract; the two-phase orchestration lives in the engine scheduler and runners.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, runtime_checkable

from scistudio.core.storage.ref import StorageReference

if TYPE_CHECKING:
    from scistudio.blocks.base.config import BlockConfig

# Panel API compatibility version. Mirrors ADR-048's ``PREVIEWER_API_VERSION``
# (:data:`scistudio.previewers.models.PREVIEWER_API_VERSION`); the frontend
# panel host refuses to mount a manifest whose major version differs.
PANEL_API_VERSION = "1"

# Config keys the engine threads into the compute phase (ADR-051 §3).
# ``INTERACTIVE_RESPONSE_KEY`` carries the user's decision and IS recorded in
# lineage (FR-011); ``INTERACTIVE_INTERMEDIATE_KEY`` carries engine-held storage
# references for reuse and is EXCLUDED from lineage (scratch, not provenance).
INTERACTIVE_RESPONSE_KEY = "interactive_response"
INTERACTIVE_INTERMEDIATE_KEY = "interactive_intermediate"


@dataclass(frozen=True)
class PanelManifest:
    """Same-origin descriptor for a block's interactive window component.

    Mirrors ADR-048's :class:`~scistudio.previewers.models.FrontendManifest`
    shape, extended only as the panel requires (an optional declared
    ``response_schema``). The frontend resolves a core panel from
    :attr:`panel_id` against its built-in panel registry, and a package panel by
    dynamically importing :attr:`module_url` (same-origin, ADR-048 §4); core
    panels leave ``module_url`` empty because they are bundled, not wheel-served.

    Attributes:
        panel_id: Stable id of the window component, e.g.
            ``"core.interactive.data_router"``. The frontend resolution key.
        module_url: Backend-relative URL the frontend imports a package panel
            module from (``/api/...``); remote URLs are rejected. Empty for
            core panels resolved from the built-in registry.
        export_name: Named export inside the module to mount.
        css: Optional backend-relative CSS asset URLs.
        version: Panel bundle version (fingerprint or semver).
        api_version: Panel API compatibility version; must match
            :data:`PANEL_API_VERSION` (major) to mount without a diagnostic.
        response_schema: Optional JSON-schema-like declaration of the response
            shape the panel returns; advisory metadata for the panel host.
        asset_root: Filesystem directory a package confines its panel assets
            under. Never serialized to the frontend; used only by a backend
            asset validator for path confinement (mirrors ADR-048 FR-024).
    """

    panel_id: str
    module_url: str = ""
    export_name: str = "default"
    css: tuple[str, ...] = ()
    version: str = "0"
    api_version: str = PANEL_API_VERSION
    response_schema: dict[str, Any] | None = None
    asset_root: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Wire shape sent to the frontend. ``asset_root`` is intentionally omitted."""
        data: dict[str, Any] = {
            "panel_id": self.panel_id,
            "module_url": self.module_url,
            "export_name": self.export_name,
            "css": list(self.css),
            "version": self.version,
            "api_version": self.api_version,
        }
        if self.response_schema is not None:
            data["response_schema"] = self.response_schema
        return data


@dataclass(frozen=True)
class InteractivePrompt:
    """The return of :meth:`InteractiveMixin.prepare_prompt` (ADR-051 §2).

    Attributes:
        panel_payload: A JSON-safe, window-sized view of the data the panel
            renders (a downsampled trace, a summary table, selectable items).
            Reducing the data to something a person can look at is the block's
            job; the runtime rejects a payload that is not plain JSON (FR-004).
        intermediate: Optional storage references to heavy intermediate work the
            block wants to reuse in the compute phase. Carried engine-side across
            the pause, never sent to the browser, and excluded from lineage
            (ADR-051 §3 / FR-010). Empty when the compute phase rebuilds entirely
            from inputs, config, and the decision.
    """

    panel_payload: dict[str, Any]
    intermediate: tuple[StorageReference, ...] = ()


class InteractiveMixin:
    """The capability mixed into a block to make it interactive (ADR-051 §2).

    A block becomes interactive by inheriting this mixin and declaring
    ``execution_mode = ExecutionMode.INTERACTIVE``. The registry rejects either
    half without the other at scan time (FR-002). Subclasses MUST set the
    :attr:`interactive_panel` ClassVar and MAY override :meth:`prepare_prompt`
    (the default raises). ``run`` is inherited from the block's category and is
    where the user's decision is consumed on the compute phase.
    """

    #: The window this block opens (ADR-051 §4). Subclasses MUST set this.
    interactive_panel: ClassVar[PanelManifest]

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt | dict[str, Any]:
        """Turn the real input data into what the window should show.

        Runs in an isolated worker subprocess (ADR-051 §3). Receives the block's
        full input collections (one interaction spans the whole input, FR-005)
        and the resolved config. Returns an :class:`InteractivePrompt` carrying
        the JSON-safe ``panel_payload`` and optional intermediate storage
        references. A bare ``dict`` return is treated as the ``panel_payload``
        with no intermediate, for blocks that need no heavy reuse.
        """
        raise NotImplementedError(
            f"{type(self).__name__} declares execution_mode=INTERACTIVE and "
            f"InteractiveMixin but does not implement prepare_prompt() (ADR-051)."
        )


@runtime_checkable
class SupportsInteraction(Protocol):
    """Structural protocol used to validate the interaction capability.

    A block satisfies it when it carries an :attr:`interactive_panel` manifest
    and a ``prepare_prompt`` method. The registry uses
    :class:`InteractiveMixin` inheritance for the hard biconditional check and
    this protocol for duck-typed validation of the required members (FR-002).
    """

    interactive_panel: PanelManifest

    def prepare_prompt(self, inputs: dict[str, Any], config: Any) -> Any: ...


def coerce_prompt(result: InteractivePrompt | dict[str, Any]) -> InteractivePrompt:
    """Normalize a ``prepare_prompt`` return to an :class:`InteractivePrompt`.

    A block may return a bare ``dict`` (the panel payload, no intermediate) or a
    full :class:`InteractivePrompt`. Used by the worker prompt phase so block
    authors are not forced to import the dataclass for the simple case.
    """
    if isinstance(result, InteractivePrompt):
        return result
    if isinstance(result, dict):
        return InteractivePrompt(panel_payload=result)
    raise TypeError(
        "prepare_prompt must return an InteractivePrompt or a dict panel payload, "
        f"got {type(result).__name__} (ADR-051)."
    )


def serialise_storage_ref(ref: StorageReference) -> dict[str, Any]:
    """Serialize a :class:`StorageReference` to a JSON-safe dict (intermediate channel)."""
    return {
        "backend": ref.backend,
        "path": ref.path,
        "format": ref.format,
        "metadata": ref.metadata,
    }


def deserialise_storage_ref(data: dict[str, Any]) -> StorageReference:
    """Reconstruct a :class:`StorageReference` from its serialized dict."""
    return StorageReference(
        backend=data["backend"],
        path=data["path"],
        format=data.get("format"),
        metadata=data.get("metadata"),
    )


def load_intermediate(config: BlockConfig | dict[str, Any]) -> tuple[StorageReference, ...]:
    """Return the engine-threaded intermediate storage references, if any.

    Helper for an interactive block's ``run`` (compute phase) to read back the
    references its ``prepare_prompt`` persisted, without re-deriving the wire
    shape. Returns an empty tuple when the block produced no intermediate.
    """
    raw: Any
    if isinstance(config, dict):
        raw = config.get(INTERACTIVE_INTERMEDIATE_KEY)
    else:
        raw = config.get(INTERACTIVE_INTERMEDIATE_KEY) if hasattr(config, "get") else None
    if not raw:
        return ()
    refs: list[StorageReference] = []
    for item in raw:
        if isinstance(item, StorageReference):
            refs.append(item)
        elif isinstance(item, dict):
            refs.append(deserialise_storage_ref(item))
    return tuple(refs)


__all__ = [
    "INTERACTIVE_INTERMEDIATE_KEY",
    "INTERACTIVE_RESPONSE_KEY",
    "PANEL_API_VERSION",
    "InteractiveMixin",
    "InteractivePrompt",
    "PanelManifest",
    "SupportsInteraction",
    "coerce_prompt",
    "deserialise_storage_ref",
    "load_intermediate",
    "serialise_storage_ref",
]
