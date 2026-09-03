"""The explore subsystem: notebook dependency analysis and runtime observation.

This package implements ADR-054 §6.1/§6.2 as specified in
``docs/specs/adr-054-notebook-dependency-analysis.md``:

- :mod:`scistudio.explore.dependency_analysis` — per-cell static facts
  (``symtable`` + a single ``ast`` walk), the dependency graph over enabled
  cells with edge origins and version nodes, the four queries (downstream set,
  backward slice, changed set, written-order definer), the closed
  :class:`AnalysisFlag` enumeration, and the cell-metadata record codec.
- :mod:`scistudio.explore.fingerprint` — the bounded fingerprint, the
  namespace comparison that produces a cell's observed changed set, and the
  source-hash-keyed observation record.

The package is **not** one of the canonical public roots of ADR-052 (spec
assumption A-009): the frozen surface inventory is unchanged, and every public
symbol carries a stability marker so that promoting the package later is a
listing change rather than a decoration pass. Everything here is
``provisional`` while the explore-session and explore-frontend specs land on
top of it.
"""

from __future__ import annotations

from scistudio.explore.dependency_analysis import (
    ANALYSIS_VERSION,
    METADATA_KEY,
    AnalysisFlag,
    AnalysisRecord,
    BlockCall,
    CellFacts,
    DependencyGraph,
    Edge,
    EdgeOrigin,
    FlagDetail,
    OutputDeclaration,
    SliceResult,
    UnresolvedRead,
    VersionEdge,
    VersionNode,
    analyze_cell,
    build_graph,
    hash_source,
    load_cell,
    read_cell_enabled,
    read_cell_record,
    read_notebook_analysis_version,
    write_cell_record,
    write_notebook_record,
)
from scistudio.explore.fingerprint import (
    FINGERPRINT_NAMESPACE_TIME_BUDGET_SECONDS,
    FINGERPRINT_SAMPLE_SIZE,
    FINGERPRINT_SIZE_BOUND,
    Fingerprint,
    ObservedChange,
    compare_namespaces,
    fingerprint,
    fingerprint_namespace,
    unpredicted_changes,
)

__all__ = [
    "ANALYSIS_VERSION",
    "FINGERPRINT_NAMESPACE_TIME_BUDGET_SECONDS",
    "FINGERPRINT_SAMPLE_SIZE",
    "FINGERPRINT_SIZE_BOUND",
    "METADATA_KEY",
    "AnalysisFlag",
    "AnalysisRecord",
    "BlockCall",
    "CellFacts",
    "DependencyGraph",
    "Edge",
    "EdgeOrigin",
    "Fingerprint",
    "FlagDetail",
    "ObservedChange",
    "OutputDeclaration",
    "SliceResult",
    "UnresolvedRead",
    "VersionEdge",
    "VersionNode",
    "analyze_cell",
    "build_graph",
    "compare_namespaces",
    "fingerprint",
    "fingerprint_namespace",
    "hash_source",
    "load_cell",
    "read_cell_enabled",
    "read_cell_record",
    "read_notebook_analysis_version",
    "unpredicted_changes",
    "write_cell_record",
    "write_notebook_record",
]
