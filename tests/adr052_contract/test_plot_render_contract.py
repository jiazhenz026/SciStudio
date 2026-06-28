"""DEFERRED: §9 plot render(collection) behavior-pinning contract test.

ADR-052 §9 / spec §9 + §15 define the import-free, dual-interpreter (Python + R)
``render(collection)`` authoring contract and require a *behavior-pinning*
contract test (a reference ``render(collection)`` asserting the injected shape --
``collection.types`` / ``.items`` / ``.open()`` / ``.open_one()``;
``item.type`` / ``.metadata`` strip-list / ``.open()`` native-payload-by-type --
and the return handling: figure / in-working-dir path / list / rejects).

This is intentionally NOT written yet. The contract lives in the harness under
``scistudio.ai.agent.mcp.tools_plot._harness`` and is being relocated to a
first-class home by #1824 (a behavior-preserving move that severs the
``ai.agent.mcp`` coupling). The relocated import path is unknown until #1824
merges, and the §9 shape/return contract is unchanged by that move, so the real
assertions are deferred to avoid binding to the soon-to-move module path. The
manager continues this agent after #1824 merges (per the dispatch).

# TODO(#1824): implement the §9 render(collection) behavior-pinning test (Python
#   + R reference render) once the plot contract is relocated to its first-class
#   home. Pin: collection.types / collection.items.open()/open_one(); item.type
#   in {Array,DataFrame,Series,Text,Artifact,CompositeData}; item.metadata
#   strip-list {backend,format,path,storage_ref,storage,type_chain,item_type,
#   slots}; item.open() native payloads (Array->ndarray, DataFrame->DataFrame,
#   Series->Series|DataFrame, Text->str, Artifact->Path, CompositeData->dict);
#   return handling (figure with .savefig / in-dir path / list-of-those; None
#   -> ValueError, other -> TypeError).
#   Out of scope here per ADR-052 §9 (relocation pending #1824).
#   Followup: https://github.com/jiazhenz026/SciStudio/issues/1824
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="ADR-052 §9 behavior-pinning test pending #1824 plot relocation"
)


def test_plot_render_collection_contract() -> None:  # pragma: no cover - deferred
    """Placeholder for the §9 render(collection) behavior-pinning contract (#1824)."""
    raise NotImplementedError("deferred to #1824 plot relocation (ADR-052 §9)")
