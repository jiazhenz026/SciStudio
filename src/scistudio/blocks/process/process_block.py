"""ProcessBlock -- the base class for item-by-item data transformations.

A block with expensive one-time initialisation (loading an ML model, opening a
database connection, compiling a regex) overrides :meth:`ProcessBlock.setup`
so that work runs once per :meth:`ProcessBlock.run`. The value ``setup``
returns is passed to every :meth:`ProcessBlock.process_item` call as the third
argument, and :meth:`ProcessBlock.teardown` runs afterwards in a ``finally``
block, even when an item raises.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, ClassVar

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.stability import stable

if TYPE_CHECKING:
    from scistudio.core.types.collection import Collection


# Lifecycle hooks and the process_item override contract are specified in
# ADR-027 D7 / ADR-020-Add5.
@stable(since="0.3.1")
class ProcessBlock(Block):
    """Transform every item of a Collection with a deterministic algorithm.

    Subclass this for row-by-row or item-by-item transforms (filtering,
    normalising, feature extraction). The base :meth:`run` streams the primary
    input Collection one item at a time, so peak memory stays at roughly one
    item regardless of how large the dataset is.

    To implement a block, pick one of two levels of control:

    - **Common case** -- override :meth:`process_item` with the signature
      ``(self, item, config, state=None)``. The base :meth:`run` does the rest:
      one :meth:`setup` call, one :meth:`process_item` per item with the shared
      ``state``, auto-flush of each result, packing into the output Collection,
      and :meth:`teardown` in a ``finally`` block.
    - **Full control** -- override :meth:`run` directly and use ``map_items()``,
      ``parallel_map()``, or ``pack()`` to build the output Collection yourself.

    Ports: reads the primary (first) input Collection and emits one output
    Collection of the same length on the first output port. Config: this base
    class reads no config fields of its own; a subclass declares whatever
    ``config`` keys its :meth:`process_item` consumes.

    Set the class attribute :attr:`algorithm` to a human-readable identifier
    for the transform.

    Example:
        >>> class Doubler(ProcessBlock):
        ...     algorithm = "doubler"
        ...     def process_item(self, item, config, state=None):
        ...         return item * 2
    """

    # Stability: stable (ADR-052 §5).
    algorithm: ClassVar[str] = ""
    """Human-readable identifier for the transform this block performs.

    Set this on each subclass (for example ``algorithm = "normalise"``). It
    labels the block's transform in metadata; it does not affect execution.
    """

    # ------------------------------------------------------------------
    # ADR-027 D7: lifecycle hooks
    # ------------------------------------------------------------------

    @stable(since="0.3.1")
    def setup(self, config: BlockConfig) -> Any:
        """Run once at the start of :meth:`run`, before any item is processed.

        Override this to load expensive resources that should be paid for once
        and shared across every item in this run -- for example loading an ML
        model, opening a database connection, or compiling a regex. The base
        implementation does nothing and returns ``None``.

        ``setup`` receives only ``config``; it cannot see the input data. A
        block that needs data-driven initialisation should do it lazily inside
        :meth:`process_item` and cache the result on the ``state`` object.

        Args:
            config: The block configuration for this run.

        Returns:
            Any value the block wants to reuse across items (its "state"). It is
            passed unchanged to every :meth:`process_item` call and to
            :meth:`teardown`. Defaults to ``None``.
        """
        return None

    @stable(since="0.3.1")
    def teardown(self, state: Any) -> None:
        """Run once at the end of :meth:`run`, even if an item raised.

        Override this to release whatever :meth:`setup` allocated -- for
        example closing a database connection or freeing GPU memory with
        ``torch.cuda.empty_cache()``. It runs inside a ``finally`` block, so it
        is called whether the run succeeds or fails. The base implementation
        does nothing.

        Args:
            state: The value :meth:`setup` returned. It is ``None`` when
                :meth:`setup` was not overridden.
        """
        return None

    # ------------------------------------------------------------------
    # ADR-027 D7: three-argument process_item
    # ------------------------------------------------------------------

    @stable(since="0.3.1")
    def process_item(self, item: Any, config: BlockConfig, state: Any = None) -> Any:
        """Transform a single item; override this for the common case.

        This is the one method most blocks need to write. The base :meth:`run`
        iterates the primary input Collection and calls this method once per
        item, auto-flushing each returned value. The base implementation raises
        :class:`NotImplementedError`, so a subclass must provide its own.

        The recommended signature is ``(self, item, config, state=None)``, where
        ``state`` is whatever :meth:`setup` returned and is shared across every
        item in one :meth:`run` call. A two-argument override
        ``(self, item, config)`` is also accepted: :meth:`run` inspects the
        signature and omits ``state`` when the override does not declare it.

        Args:
            item: One DataObject from the primary input Collection.
            config: The block configuration for this run.
            state: The value :meth:`setup` returned, shared across all items.
                ``None`` when :meth:`setup` was not overridden.

        Returns:
            The transformed value for this item. The framework auto-flushes it
            and packs it into the output Collection.

        Raises:
            NotImplementedError: If the subclass does not override this method.

        Example:
            >>> class Doubler(ProcessBlock):
            ...     algorithm = "doubler"
            ...     def process_item(self, item, config, state=None):
            ...         return item * 2
        """
        raise NotImplementedError("Subclass must implement process_item()")

    # ------------------------------------------------------------------
    # ADR-027 D7: default run() with setup/teardown lifecycle
    # ------------------------------------------------------------------

    @stable(since="0.3.1")
    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Stream the primary input Collection through :meth:`process_item`.

        This is the default execution path for the common case. It calls
        :meth:`setup` once, then calls :meth:`process_item` for each item of the
        primary (first) input Collection with the shared ``state``, auto-flushes
        each result, and packs the results into a single output Collection on
        the first output port. :meth:`teardown` runs in a ``finally`` block, so
        resources are released even when :meth:`process_item` raises. Peak
        memory stays at roughly one item.

        Override this method directly when you need full control -- custom
        iteration, multiple output ports, or batching. Such an override is
        responsible for calling its own :meth:`setup` / :meth:`teardown` if it
        wants the lifecycle behaviour.

        Args:
            inputs: Mapping of input port name to its Collection. The first
                value is treated as the primary input to iterate.
            config: The block configuration for this run.

        Returns:
            Mapping of the first output port name to a Collection holding the
            processed items.
        """
        from scistudio.core.types.collection import Collection

        primary = next(iter(inputs.values()))

        # ADR-027 D7: lifecycle hook — run setup once before iteration.
        state = self.setup(config)

        # Backward-compat safety net (Question 5 in the T-009 standards):
        # inspect the override's signature. Pre-T-009 two-arg overrides
        # ``(self, item, config)`` do not declare a ``state`` parameter and
        # must be called with 2 positional args; new three-arg overrides
        # are called with the shared ``state``.
        takes_state = self._process_item_takes_state()

        # ADR-028 Addendum 1 D5: read the per-instance effective output ports
        # so dynamic blocks (e.g. ``LoadData``) get their config-driven port
        # name instead of the static ClassVar declaration.
        effective_output_ports = self.get_effective_output_ports()

        try:
            # If primary is a Collection, iterate and process each item.
            if isinstance(primary, Collection):
                results = []
                for item in primary:
                    result = self.process_item(item, config, state) if takes_state else self.process_item(item, config)
                    result = self._auto_flush(result)
                    results.append(result)
                output_name = effective_output_ports[0].name if effective_output_ports else "output"
                # #876: infer item_type from results so parent-typed outputs
                # (e.g. SRSImage in -> Image out) are not rejected by
                # Collection.__init__'s strict isinstance check. Fall back to
                # primary.item_type only when results is empty so the empty
                # Collection still carries a meaningful type label.
                out_collection = Collection(results) if results else Collection([], item_type=primary.item_type)
                return {output_name: out_collection}

            # Fallback for a bare (non-Collection) primary input: treat it as a
            # single item and still emit a length-one Collection so the output
            # honours the ADR-020 §3 transport contract (#1811) even when a bare
            # value reaches the block directly (e.g. a legacy wire payload).
            result = self.process_item(primary, config, state) if takes_state else self.process_item(primary, config)
            result = self._auto_flush(result)
            output_name = effective_output_ports[0].name if effective_output_ports else "output"
            return {output_name: Collection([result])}
        finally:
            # ADR-027 D7: teardown always runs, even on exception.
            self.teardown(state)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _process_item_takes_state(self) -> bool:
        """Return True if this block's ``process_item`` accepts a ``state`` arg.

        Used by :meth:`run` to stay backward-compatible with pre-T-009
        subclasses that override ``process_item(self, item, config)`` with
        only two arguments. New subclasses should use the three-argument
        form ``process_item(self, item, config, state=None)``.
        """
        try:
            sig = inspect.signature(self.process_item)
        except (TypeError, ValueError):
            # Builtins or C extensions with no introspectable signature —
            # assume modern 3-arg form and let normal call failures surface.
            return True

        params = sig.parameters
        if "state" in params:
            return True
        # If the override accepts ``*args``, it can absorb ``state`` as an
        # extra positional argument, so the 3-arg call site is safe.
        return any(p.kind is inspect.Parameter.VAR_POSITIONAL for p in params.values())
