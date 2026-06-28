"""ADR-052 §9 plot ``render(collection)`` behaviour-pinning contract — DEFERRED.

The §9 plot contract is an import-free, duck-typed, dual-interpreter (Python + R)
authoring contract: a plot script defines exactly ``def render(collection):``
(R: ``render <- function(collection)``), the harness injects a ``collection``
object, calls ``render(collection)``, and collects the return value. ADR-052 §15
freezes it with a *behaviour-pinning contract test* (a Python + R reference
``render(collection)`` that asserts the injected shape — ``collection.types`` /
``.items.open()`` / ``.open_one()``; ``item.type`` / ``.metadata`` strip-list /
``.open()`` native-payload-by-type — and the return handling: figure /
in-working-dir path / list / rejects ``None`` and other).

This test is intentionally a tracked placeholder, NOT the real assertions. The
plot contract + its 8-module runtime are being relocated out of the
``scistudio.ai.agent.mcp.tools_plot`` namespace under #1824 (a behaviour-
preserving move); the §9 shape and return contract are unchanged by that move,
but the relocated import home is not yet known. Writing the real harness-driven
assertions now would hard-code the wrong module path. The same test agent fills
this in once #1824 merges and the first-class home is fixed.

# TODO(#1824): write the §9 render(collection) behaviour-pinning contract test
#   (Python + R reference render(collection): injected-shape assertions +
#   return-handling assertions, per ADR-052 §9 / §15).
#   Out of scope here per ADR-052 §9 (plot contract relocation is in flight under
#   #1824; the relocated import home is unknown, so the real assertions are
#   deferred — no behaviour change to §9).
#   Followup: https://github.com/jiazhenz026/SciStudio/issues/1824
"""

from __future__ import annotations

import pytest

_PENDING = "ADR-052 §9 behavior-pinning test pending #1824 plot relocation"


@pytest.mark.skip(reason=_PENDING)
def test_plot_render_collection_injected_shape() -> None:
    """Placeholder: pin the injected ``collection`` shape + ``item.open()`` types.

    Filled after #1824 fixes the relocated home. Will assert ``collection.types``
    (tuple of distinct type names), ``collection.items`` (len/iterate/index),
    ``items.open(max_items=None)`` / ``items.open_one()``, and ``item.type`` /
    ``item.metadata`` (read-only, strip-listed) / ``item.open()`` returning the
    native payload by type (Array->ndarray, DataFrame->pandas, Series->Series-or-
    DataFrame, Text->str, Artifact->Path, CompositeData->dict).
    """
    raise NotImplementedError("deferred to #1824")  # pragma: no cover


@pytest.mark.skip(reason=_PENDING)
def test_plot_render_collection_return_contract() -> None:
    """Placeholder: pin the ``render(collection)`` return handling.

    Filled after #1824. Will assert a Matplotlib figure (has ``.savefig``) is
    saved, an in-working-dir path (str/Path) is collected, a list/tuple of those
    is each collected, and ``None`` -> ``ValueError`` / other -> ``TypeError``.
    """
    raise NotImplementedError("deferred to #1824")  # pragma: no cover
