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
beyond the stability markers and its own two modules, so the session, the API
layer, and the kernel adapter can all import it without a layering question.
``tests/architecture/test_layer_deps.py`` asserts the constraint.

What this façade re-exports, and what it deliberately does not: the static facts,
the graph, the queries, and the metadata codec are re-exported here; the
fingerprint half is imported from :mod:`scistudio.explore.fingerprint` instead.
That module is named after its main function, so re-exporting ``fingerprint``
here would rebind the package attribute of the same name from the module to the
function and quietly break ``from scistudio.explore import fingerprint``. The
observation types travel with the function they belong to rather than being split
across two spellings::

    from scistudio.explore import build_graph, decode_cell_record
    from scistudio.explore.fingerprint import ObservedChange, compare_namespaces, fingerprint

The spec names both module paths among its contracts, so neither import is a
second-class route.
"""

from __future__ import annotations

from scistudio.explore.dependency_analysis import (
    ANALYSIS_VERSION,
    BLOCK_CALL_PATHS,
    BUILTIN_NAMES,
    CELL_RECORD_KEY,
    INPUT_CALL_PATH,
    OUTPUT_CALL_PATH,
    AnalysisFlag,
    BlockCall,
    CellFacts,
    CellFlag,
    DependencyGraph,
    Edge,
    EdgeOrigin,
    LoadedCell,
    OutputDeclaration,
    SliceResult,
    UnresolvedRead,
    VersionEdge,
    VersionNode,
    analyse_cell,
    analyse_cells,
    build_graph,
    decode_cell_record,
    encode_cell_record,
    encode_notebook_record,
    notebook_record_version,
    observation_flags,
    source_hash,
)

__all__ = [
    "ANALYSIS_VERSION",
    "BLOCK_CALL_PATHS",
    "BUILTIN_NAMES",
    "CELL_RECORD_KEY",
    "INPUT_CALL_PATH",
    "OUTPUT_CALL_PATH",
    "AnalysisFlag",
    "BlockCall",
    "CellFacts",
    "CellFlag",
    "DependencyGraph",
    "Edge",
    "EdgeOrigin",
    "LoadedCell",
    "OutputDeclaration",
    "SliceResult",
    "UnresolvedRead",
    "VersionEdge",
    "VersionNode",
    "analyse_cell",
    "analyse_cells",
    "build_graph",
    "decode_cell_record",
    "encode_cell_record",
    "encode_notebook_record",
    "notebook_record_version",
    "observation_flags",
    "source_hash",
]
