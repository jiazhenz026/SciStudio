"""The interaction capability for data-processing blocks.

An interactive block pauses mid-workflow, opens a block-owned window onto its
real input data, takes a data-dependent decision from the user, and computes its
outputs from that decision. Interaction is a *capability* any block category can
carry, not a category of its own: a block becomes interactive by mixing in
:class:`InteractiveMixin` and declaring ``execution_mode =
ExecutionMode.INTERACTIVE``. There is deliberately no ``InteractiveBlock`` base
class — interactivity is layered onto an existing category (for example
:class:`~scistudio.blocks.process.process_block.ProcessBlock`).

The capability gives a block three things:

* :attr:`InteractiveMixin.interactive_panel` — a :class:`PanelManifest` naming
  the frontend window component the block opens.
* :meth:`InteractiveMixin.prepare_prompt` — turns the real input data into the
  JSON-safe, window-sized view the panel renders, plus optional heavy
  intermediate work carried forward as storage references (never in memory).
* ``run`` — inherited from the block's category; on the compute phase it reads
  the user's decision from ``config["interactive_response"]`` and produces the
  block's outputs.

The registry binds the capability and the execution mode together when it scans
blocks: a block that declares one without the other, omits ``prepare_prompt``,
or omits a valid :class:`PanelManifest` is rejected at load time.

The two halves run in two worker subprocesses on either side of an engine-held
pause: the prompt phase builds the view and exits, the engine holds the pause
with nothing resident, then a fresh compute phase runs ``run`` with the decision
injected. This module only defines the contract; the two-phase orchestration
lives in the engine scheduler and runners.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, runtime_checkable

from scistudio.core.meta._display_name import resolve_display_name
from scistudio.core.storage.ref import StorageReference
from scistudio.stability import provisional

if TYPE_CHECKING:
    from scistudio.blocks.base.config import BlockConfig

# The frontend panel host refuses to mount a manifest whose major version
# differs from this.
PANEL_API_VERSION = "1"
"""Panel API compatibility version.

A :class:`PanelManifest` whose major version differs from this is refused by the
frontend panel host. Bump it when the panel contract changes incompatibly.
"""

# Config keys the engine threads into the compute phase. The response key
# carries the user's decision and is recorded in lineage; the intermediate key
# carries engine-held storage references for reuse and is excluded from lineage.
INTERACTIVE_RESPONSE_KEY = "interactive_response"
"""Config key under which an interactive block's run reads the user's decision.

On the compute phase the engine places the value the user chose in the panel at
``config[INTERACTIVE_RESPONSE_KEY]``. This decision is recorded in the run's
lineage.
"""
INTERACTIVE_INTERMEDIATE_KEY = "interactive_intermediate"

# ADR-051 interaction memory: a block config may carry a remembered decision so
# future runs skip the dialog and compute directly. The record is
# ``{"enabled": bool, "decision": <interactive_response>, "signature": <input
# signature>}``; the frontend writes it on confirm (when the user opts in) and
# the engine reads it on dispatch. Stored in node config (frontend owns the
# workflow definition); the engine never writes it back.
INTERACTIVE_MEMORY_KEY = "interactive_memory"


@provisional(since="0.3.1")
@dataclass(frozen=True)
class PanelManifest:
    """Describes the frontend window component a block opens for interaction.

    An interactive block declares one of these as its ``interactive_panel`` to
    name the window the user sees. A built-in (core) panel is resolved by
    :attr:`panel_id` against the frontend's built-in registry; a package-provided
    panel is loaded by importing :attr:`module_url` from the backend (same-origin
    only — remote URLs are rejected). Core panels leave ``module_url`` empty
    because they ship with the app.

    Example:
        >>> manifest = PanelManifest(panel_id="core.interactive.data_router")
    """

    panel_id: str
    """Stable id of the window component (e.g. ``"core.interactive.data_router"``).

    For a core panel this is the frontend's resolution key.
    """

    module_url: str = ""
    """Backend-relative URL (``/api/...``) to import a package panel module from.

    Remote URLs are rejected. Left empty for built-in core panels.
    """

    export_name: str = "default"
    """Named export inside the module to mount as the panel component."""

    css: tuple[str, ...] = ()
    """Optional backend-relative URLs of CSS assets the panel needs."""

    version: str = "0"
    """Panel bundle version (a fingerprint or semver string)."""

    api_version: str = PANEL_API_VERSION
    """Panel API compatibility version; its major must match :data:`PANEL_API_VERSION`."""

    response_schema: dict[str, Any] | None = None
    """Optional declaration of the response shape the panel returns.

    A JSON-schema-like description; advisory metadata for the panel host, not
    enforced by the runtime.
    """

    asset_root: str | None = None
    """Filesystem directory a package confines its panel assets under.

    Never sent to the frontend; used only by a backend validator to keep asset
    paths confined to the package.
    """

    @provisional(since="0.3.1")
    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-safe wire form of this manifest sent to the frontend.

        :attr:`asset_root` is intentionally omitted (it is a backend-only path),
        and :attr:`response_schema` is included only when it is set.

        Returns:
            A dict with the manifest's frontend-facing fields.
        """
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


@provisional(since="0.3.1")
@dataclass(frozen=True)
class InteractivePrompt:
    """What :meth:`InteractiveMixin.prepare_prompt` returns to drive the panel.

    Bundles the window-sized view the panel renders together with any heavy
    intermediate results the block wants to reuse afterwards, without putting those
    heavy results in memory or on the wire.

    Example:
        >>> prompt = InteractivePrompt(panel_payload={"items": ["a", "b"]})
    """

    panel_payload: dict[str, Any]
    """JSON-safe, window-sized view of the data the panel renders.

    Reducing the data to something a person can look at (a downsampled trace, a
    summary table, a list of selectable items) is the block's responsibility; the runtime
    rejects a payload that is not plain JSON.
    """

    intermediate: tuple[StorageReference, ...] = ()
    """Storage references to heavy intermediate work to reuse in the compute phase.

    Carried by the engine across the pause, never sent to the browser, and
    excluded from lineage. Leave empty when the compute phase rebuilds entirely
    from the inputs, config, and the user's decision.
    """


@provisional(since="0.3.1")
class InteractiveMixin:
    """Mix-in that makes a block interactive.

    Inherit this alongside a block category and declare ``execution_mode =
    ExecutionMode.INTERACTIVE`` to turn an ordinary block into one that pauses to
    ask the user a question. The registry rejects a block that declares one of
    these without the other. A subclass MUST set the :attr:`interactive_panel`
    class attribute and SHOULD override :meth:`prepare_prompt` (the default
    raises). The block's own ``run`` — inherited from its category — consumes the
    user's decision on the compute phase.

    Example:
        >>> from scistudio.blocks.base import (
        ...     ExecutionMode,
        ...     InteractiveMixin,
        ...     PanelManifest,
        ... )
        >>> class PickOne(InteractiveMixin):  # doctest: +SKIP
        ...     execution_mode = ExecutionMode.INTERACTIVE
        ...     interactive_panel = PanelManifest(panel_id="core.interactive.data_router")
        ...     def prepare_prompt(self, inputs, config):
        ...         return {"items": [str(i) for i in inputs]}
    """

    interactive_panel: ClassVar[PanelManifest]
    """The window this block opens. A subclass MUST set it to a :class:`PanelManifest`."""

    @provisional(since="0.3.1")
    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt | dict[str, Any]:
        """Turn the real input data into what the window should show.

        Runs in an isolated worker subprocess. Receives the block's full input
        collections (one interaction spans the whole input) and the resolved
        config, and returns what the panel needs.

        Args:
            inputs: The block's input collections, keyed by input-port name.
            config: The block's resolved configuration.

        Returns:
            An :class:`InteractivePrompt` carrying the JSON-safe
            ``panel_payload`` and any intermediate storage references. A bare
            ``dict`` is accepted as shorthand for a payload with no intermediate.

        Raises:
            NotImplementedError: If the subclass does not override this method.
        """
        raise NotImplementedError(
            f"{type(self).__name__} declares execution_mode=INTERACTIVE and "
            f"InteractiveMixin but does not implement prepare_prompt()."
        )

    @provisional(since="0.3.1")
    def remap_saved_decision(
        self,
        saved_decision: dict[str, Any],
        saved_signature: dict[str, list[str]],
        current_signature: dict[str, list[str]],
    ) -> dict[str, Any] | None:
        """Re-resolve a remembered decision against the current inputs.

        Interaction memory lets a block skip its dialog on a re-run by replaying
        the user's earlier decision. The engine calls this on dispatch with the
        decision the user saved, the input fingerprint captured when they saved
        it, and the fingerprint of the current inputs.

        The default policy reuses the saved decision only when the input
        fingerprint is unchanged (same items, same order per port) — safe for a
        plain re-run, and it never replays a stale decision. Override it to remap
        a decision by item identity so it survives reordering or partial input
        changes.

        Args:
            saved_decision: The decision (an ``interactive_response``) the user
                saved earlier.
            saved_signature: Input fingerprint captured when the decision was
                saved, mapping each port name to its ordered item labels.
            current_signature: Fingerprint of the current inputs, in the same
                shape.

        Returns:
            The ``interactive_response`` to apply automatically (skipping the
            pause and the panel), or ``None`` to fall back to opening the panel.
        """
        if saved_signature == current_signature:
            return saved_decision
        return None


@runtime_checkable
class SupportsInteraction(Protocol):
    """Structural protocol used to validate the interaction capability.

    A block satisfies it when it carries an :attr:`interactive_panel` manifest
    and a ``prepare_prompt`` method. The registry uses
    :class:`InteractiveMixin` inheritance for the hard biconditional check and
    this protocol for duck-typed validation of the required members (FR-002).

    Internal (ADR-052 §4.8): registry-validation protocol, not author surface.
    """

    interactive_panel: PanelManifest

    def prepare_prompt(self, inputs: dict[str, Any], config: Any) -> Any: ...


def coerce_prompt(result: InteractivePrompt | dict[str, Any]) -> InteractivePrompt:
    """Normalize a ``prepare_prompt`` return to an :class:`InteractivePrompt`.

    A block may return a bare ``dict`` (the panel payload, no intermediate) or a
    full :class:`InteractivePrompt`. Used by the worker prompt phase so block
    authors are not forced to import the dataclass for the simple case.

    Internal (ADR-052 §4.8): worker prompt-phase normalizer, not author surface.
    """
    if isinstance(result, InteractivePrompt):
        return result
    if isinstance(result, dict):
        return InteractivePrompt(panel_payload=result)
    raise TypeError(
        "prepare_prompt must return an InteractivePrompt or a dict panel payload, "
        f"got {type(result).__name__} (ADR-051)."
    )


def interactive_item_label(item: Any, index: int) -> str:
    """Best-effort human label for one input item shown in an interactive panel.

    Interactive panels (DataRouter, PairEditor) list a block's input items for
    the user to route or reorder. A generic ``item_<index>`` is meaningless when
    the user is matching items by which file they came from, so this delegates
    to :func:`scistudio.core.meta._display_name.resolve_display_name` — the
    single canonical precedence authority shared with the previewer/API path
    (#1812) — and supplies ``item_<index>`` as the last-resort fallback.
    """
    return resolve_display_name(item, fallback=f"item_{index}")


def interactive_input_signature(inputs: dict[str, Any]) -> dict[str, list[str]]:
    """A stable, JSON-safe identity fingerprint of an interactive block's inputs.

    Maps each input port to the ordered list of its items' labels (the source
    filename via :func:`interactive_item_label`). Two runs whose inputs carry
    the same files in the same order per port produce equal signatures — the
    basis for reusing a remembered decision and skipping the dialog (ADR-051
    interaction memory). Computed generically for every interactive block, so a
    package-provided block inherits the behaviour without extra code.
    """
    from scistudio.core.types.collection import Collection

    signature: dict[str, list[str]] = {}
    for port, value in inputs.items():
        if isinstance(value, Collection):
            signature[port] = [interactive_item_label(item, i) for i, item in enumerate(value)]
        else:
            signature[port] = [interactive_item_label(value, 0)]
    return signature


def load_interactive_memory(config: Any) -> dict[str, Any] | None:
    """Read an enabled remembered-decision record from a block config.

    Looks in ``config[INTERACTIVE_MEMORY_KEY]`` and
    ``config['params'][INTERACTIVE_MEMORY_KEY]`` (block configs carry user
    fields in either place). Returns the record dict
    (``{enabled, decision, signature}``) or ``None`` when memory is absent or
    disabled.
    """
    record: Any = None
    if isinstance(config, dict):
        record = config.get(INTERACTIVE_MEMORY_KEY)
        if record is None and isinstance(config.get("params"), dict):
            record = config["params"].get(INTERACTIVE_MEMORY_KEY)
    if not isinstance(record, dict) or not record.get("enabled"):
        return None
    return record


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


@provisional(since="0.3.1")
def load_intermediate(config: BlockConfig | dict[str, Any]) -> tuple[StorageReference, ...]:
    """Return the intermediate storage references the engine carried across the pause.

    Convenience for an interactive block's ``run`` (the compute phase) to read
    back the references its :meth:`InteractiveMixin.prepare_prompt` stored,
    without re-deriving the wire shape by hand.

    Args:
        config: The block's config — a :class:`BlockConfig` or a plain dict.

    Returns:
        The stored storage references as a tuple, empty when the block produced
        no intermediate.
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


# Public author surface (ADR-052 §4.8). All provisional. The kept symbols are
# re-exported from the ``scistudio.blocks.base`` root (the canonical path).
# Demoted to internal (deep-path importable, out of ``__all__``):
# ``SupportsInteraction``, ``coerce_prompt``, ``serialise_storage_ref``,
# ``deserialise_storage_ref``, ``INTERACTIVE_INTERMEDIATE_KEY``.
__all__ = [
    "INTERACTIVE_RESPONSE_KEY",
    "PANEL_API_VERSION",
    "InteractiveMixin",
    "InteractivePrompt",
    "PanelManifest",
    "load_intermediate",
]
