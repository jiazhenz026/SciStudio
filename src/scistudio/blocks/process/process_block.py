"""ProcessBlock base — algorithm-driven data transformation.

ADR-027 D7 (setup/teardown lifecycle hooks): blocks with expensive
one-time initialisation (loading ML models, opening DB connections,
compiling regexes) override :meth:`ProcessBlock.setup` to do that work
once per :meth:`ProcessBlock.run`. The returned state is passed to
every :meth:`ProcessBlock.process_item` call as the third argument.
:meth:`ProcessBlock.teardown` runs in a ``finally`` block even on error.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, ClassVar

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig

if TYPE_CHECKING:
    from scistudio.core.types.collection import Collection


class ProcessBlock(Block):
    """Block for deterministic, algorithm-driven data transformations.

    Subclasses should set *algorithm* to a human-readable identifier for the
    transformation they perform.

    **Lifecycle hooks (ADR-027 D7)**: blocks with expensive one-time setup
    override :meth:`setup` to load resources once per ``run()``. The returned
    state is passed to every :meth:`process_item` call as the third argument.
    :meth:`teardown` runs in a ``finally`` block, even on error.

    **Tier 1 (ADR-020-Add5, ADR-027 D7)**: override :meth:`process_item` only
    with the signature ``(self, item, config, state=None)``. The default
    :meth:`run` iterates the primary input Collection, calls ``setup`` once,
    calls ``process_item`` per item with the shared ``state``, auto-flushes
    each result, packs into an output Collection, and calls ``teardown`` in
    a ``finally`` block. Peak memory = O(1 item).

    **Tier 2/3**: Override ``run()`` directly and use ``map_items()``,
    ``parallel_map()``, or ``pack()`` for Collection handling.
    """

    algorithm: ClassVar[str] = ""

    # ------------------------------------------------------------------
    # ADR-027 D7: lifecycle hooks
    # ------------------------------------------------------------------

    def setup(self, config: BlockConfig) -> Any:
        """Called once per :meth:`run` before iterating the input Collection.

        Override to load expensive resources that should be amortised across
        all items in this ``run()`` call. Examples: loading an ML model,
        opening a database connection, compiling a regex.

        The return value is passed to :meth:`process_item` as the third
        argument and to :meth:`teardown`.

        ADR-027 D7: ``setup`` receives only ``config``. It must not access
        ``inputs``. Blocks that need data-driven initialisation should do it
        lazily inside ``process_item`` and cache on the ``state`` object.

        Args:
            config: BlockConfig instance for this run.

        Returns:
            Any opaque "state" object the block needs across items. Default
            returns ``None``.
        """
        return None

    def teardown(self, state: Any) -> None:
        """Called once per :meth:`run` in a ``finally`` block, even on error.

        Override to release resources allocated in :meth:`setup`. Examples:
        closing a database connection, freeing GPU memory via
        ``torch.cuda.empty_cache()``.

        Default: no-op.

        Args:
            state: The value returned by :meth:`setup`. May be ``None`` if
                ``setup`` was not overridden.
        """
        return None

    # ------------------------------------------------------------------
    # ADR-027 D7: three-argument process_item
    # ------------------------------------------------------------------

    def process_item(self, item: Any, config: BlockConfig, state: Any = None) -> Any:
        """Tier 1 entry point: override for per-item processing.

        ADR-027 D7: signature is ``(self, item, config, state=None)``. The
        ``state`` argument is whatever :meth:`setup` returned; it is shared
        across all items in a single :meth:`run` call.

        The default :meth:`run` iterates the primary input Collection and
        calls this method for each item, auto-flushing each result. 80% of
        blocks only need to override this method.

        Pre-T-009 two-argument overrides ``(self, item, config)`` remain
        source-compatible: :meth:`run` inspects the override's signature and
        calls it with 2 args when no ``state`` parameter is present.

        Args:
            item: A single DataObject from the primary input Collection.
            config: BlockConfig for this run.
            state: The opaque state returned by :meth:`setup`. ``None`` when
                :meth:`setup` is not overridden.

        Returns:
            The transformed DataObject (or any value the framework auto-flushes).
        """
        raise NotImplementedError("Subclass must implement process_item()")

    # ------------------------------------------------------------------
    # ADR-027 D7: default run() with setup/teardown lifecycle
    # ------------------------------------------------------------------

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Default Tier 1 execution with setup/teardown lifecycle.

        Calls :meth:`setup` once before iterating the primary input
        Collection, calls :meth:`process_item` per item with the shared
        ``state``, auto-flushes each result, and packs into an output
        Collection on the first output port. :meth:`teardown` runs in a
        ``finally`` block so resources are released even when
        :meth:`process_item` raises.

        Subclasses that need custom iteration or multi-port logic should
        override this method directly (Tier 2/3). Such overrides are
        responsible for calling their own ``setup``/``teardown`` if they
        need the lifecycle semantics.
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

            # Fallback for non-Collection inputs (backward compatibility).
            result = self.process_item(primary, config, state) if takes_state else self.process_item(primary, config)
            output_name = effective_output_ports[0].name if effective_output_ports else "output"
            return {output_name: result}
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
