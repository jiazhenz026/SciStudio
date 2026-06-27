"""Green-today consumer coverage for the #1811 single-value→Collection fix.

#1811 makes the engine wrap every single-value block output into a
length-one :class:`Collection` (ADR-020 §3: "a single item is represented
as a length-one Collection"). The wire shape of a single value therefore
changes from a bare ``{backend, path, format, metadata}`` reference to a
``{_collection: True, items: [...], item_type: ...}`` envelope.

Three downstream consumers read the single-value **wire** shape and had no
existing coverage of the length-one-Collection path, so a silent behaviour
change could slip through (the exact gap this work targets):

- ``ApiRuntime.register_output_payload`` (preview registration): a single
  value must register as a ``data_ref`` (frontend single-item viewer), not
  a ``kind="collection"`` payload that the frontend reroutes to a grid
  previewer.
- ``tools_plot.targets._looks_like_collection`` (plot target hint): a
  single value must report ``is_collection=False``.

The third consumer, ``tools_inspection.get_block_output``, is covered next
to its FastMCP context fixture in
``tests/ai/test_mcp_tools_inspection.py``.

Each test builds the wire payload through the **real** engine output codec
(:func:`_normalize_outputs` -> :func:`serialise_outputs`) so it tracks the
fix automatically: it passes on today's bare-wire path and fails the moment
the engine wraps single values. The Option-2 migration — treat a length-one
Collection as a single value in these single-item-oriented consumers — then
restores each to green. This is the "green today, red after the engine
flip, green after migration" ratchet that bounds the fix's blast radius.

References: ADR-020 §3; #1811.
"""

from __future__ import annotations

import numpy as np
import zarr

from scistudio.blocks.base.ports import OutputPort
from scistudio.core.storage.ref import StorageReference
from scistudio.core.types.array import Array
from scistudio.engine.runners.worker import _normalize_outputs, serialise_outputs


def _single_value_wire(tmp_path) -> dict:
    """Return the engine wire payload for a single value on an is_collection=False port.

    Drives the real output codec so the returned shape is whatever the
    engine actually produces: a bare reference today, a length-one
    ``_collection`` envelope once #1811 lands.
    """
    zarr_path = str(tmp_path / "single.zarr")
    zarr.save(zarr_path, np.zeros((4, 4), dtype="uint8"))
    arr = Array(
        axes=["y", "x"],
        shape=(4, 4),
        dtype="uint8",
        storage_ref=StorageReference(backend="zarr", path=zarr_path),
    )
    ports = [OutputPort(name="out", accepted_types=[Array], is_collection=False)]
    outputs: dict = {"out": arr}
    _normalize_outputs(outputs, ports)
    return serialise_outputs(outputs, str(tmp_path))["out"]


class TestPreviewRegistrationSingleValue:
    """``register_output_payload`` must keep a single value a single-item ref."""

    def test_single_value_registers_as_data_ref_not_collection(self, tmp_path, monkeypatch) -> None:
        """A single block output should register as a ``data_ref`` so the
        frontend opens the single-item viewer — not a ``kind="collection"``
        payload that reroutes to a collection/grid previewer.

        Green today (bare wire -> ``data_ref``). When the engine wraps single
        values it becomes a length-one ``_collection`` and
        ``register_output_payload`` would emit ``kind="collection"`` — the
        Option-2 migration unwraps length-one collections back to a single
        ``data_ref``.
        """
        from scistudio.api import runtime as runtime_module

        # Self-contained ApiRuntime: redirect the registry dir into tmp_path
        # exactly like tests/api/conftest.py, so no real ~/.scistudio is touched.
        monkeypatch.setattr(runtime_module.Path, "home", classmethod(lambda cls: tmp_path))
        rt = runtime_module.ApiRuntime()

        result = rt.register_output_payload(_single_value_wire(tmp_path))

        assert isinstance(result, dict)
        assert "data_ref" in result, f"single value should register as a data_ref; got {result!r}"
        assert result.get("kind") != "collection"
        assert result.get("type_name") == "Array"


class TestPlotTargetSingleValue:
    """``_looks_like_collection`` must report a single value as non-collection."""

    def test_single_value_is_not_a_collection_target(self, tmp_path) -> None:
        """A single block output should yield ``is_collection=False`` for the
        plot target hint. Green today (bare wire); after the engine wraps the
        value the length-one ``_collection`` must still report ``False`` under
        Option 2 (a length-one Collection is semantically a single value).
        """
        from scistudio.ai.agent.mcp.tools_plot.targets import _looks_like_collection

        assert _looks_like_collection(_single_value_wire(tmp_path)) is False
