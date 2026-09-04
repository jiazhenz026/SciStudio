"""Notebook analysis for an explore session (ADR-054 §6.1, §6.2).

An explore session keeps a notebook, and a notebook lets a person edit a cell,
re-run it, and leave every cell below showing a number computed from the old
value with nothing on screen saying so. The answer ADR-054 chose is a dependency
graph over the cells, with **written order** as the authority so that
``df = df.dropna()`` keeps working: a cell that reads a name depends on the
nearest enabled cell above it that changes that name.

This package holds the analysis that produces that graph. It is a table with one
row per cell: what a cell **reads** is found statically from the source, and what
a cell **changes** is observed when it runs, by fingerprinting the namespace
before and after. The static assignments stand in as the estimate only until the
cell has run, and the graph uses the union of the two so that an observation can
add a definer and never remove one.

The graph never changes how the notebook executes. Execution semantics are
Jupyter's: a cell reads whatever the kernel namespace holds at that moment, and
nothing is rebound or re-run on the graph's account. The graph describes, marks,
and selects; the session decides what to do with that.

The package is pure Python over the standard library — no IPython, no notebook
format library, no static-analysis package — and imports nothing from SciStudio
beyond stability markers, so the session, the API layer, and the kernel adapter
can all import it without a layering question. ``tests/architecture/test_layer_deps.py``
asserts the constraint.
"""

from __future__ import annotations

from scistudio.explore.dependency_analysis import (
    ANALYSIS_VERSION,
    BUILTIN_NAMES,
    AnalysisFlag,
    BlockCall,
    CellFacts,
    CellFlag,
    DependencyGraph,
    Edge,
    EdgeOrigin,
    OutputDeclaration,
    SliceResult,
    UnresolvedRead,
    VersionEdge,
    VersionNode,
    analyse_cell,
    analyse_cells,
    build_graph,
    source_hash,
)

__all__ = [
    "ANALYSIS_VERSION",
    "BUILTIN_NAMES",
    "AnalysisFlag",
    "BlockCall",
    "CellFacts",
    "CellFlag",
    "DependencyGraph",
    "Edge",
    "EdgeOrigin",
    "OutputDeclaration",
    "SliceResult",
    "UnresolvedRead",
    "VersionEdge",
    "VersionNode",
    "analyse_cell",
    "analyse_cells",
    "build_graph",
    "source_hash",
]
