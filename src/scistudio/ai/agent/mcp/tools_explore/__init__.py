"""Category (h) MCP tools — the explore session (ADR-054 spec 5 FR-019 to FR-024).

Importing this package runs the ``@mcp.tool`` decorators in :mod:`tools` as a
side effect, registering the seven ``category:session`` tools on the shared
FastMCP instance. The eager import lives in ``scistudio.ai.agent.mcp.__init__``
alongside the other tool groups.

The seven are the loop ADR-054 §8.3 asks for: ``open_explore_session`` gets the
agent a notebook over real data, ``read_notebook`` and ``get_bindings`` say what
is there, ``append_cell`` and ``run_cell`` are the write-and-see cycle, and
``check_packaging`` and ``package_notebook`` turn the result into a block.

Every one of them is a call to the session API with the workspace focus resolved
first. None reaches the kernel, the notebook file, or the execution queue
(FR-024); :mod:`scistudio.ai.agent.mcp.tools_explore._service` is the only place
that holds a reference to the session service, and the test suite asserts the
whole package's import graph against that rule.
"""

from __future__ import annotations

# Side-effect import: registers the seven @mcp.tool functions.
from scistudio.ai.agent.mcp.tools_explore._models import (
    AppendCellResult,
    BindingModel,
    BoundRunModel,
    BoundRunPortModel,
    CellModel,
    CellOutputModel,
    CheckPackagingResult,
    DeclaredOutputModel,
    GetBindingsResult,
    GraphEdgeModel,
    NotebookGraphModel,
    OpenExploreSessionResult,
    PackagedPortModel,
    PackageNotebookResult,
    PackagingProblemModel,
    ReadNotebookResult,
    RunCellResult,
    UnresolvedReadModel,
)
from scistudio.ai.agent.mcp.tools_explore.tools import (
    append_cell,
    check_packaging,
    get_bindings,
    open_explore_session,
    package_notebook,
    read_notebook,
    run_cell,
)

__all__ = [
    "AppendCellResult",
    "BindingModel",
    "BoundRunModel",
    "BoundRunPortModel",
    "CellModel",
    "CellOutputModel",
    "CheckPackagingResult",
    "DeclaredOutputModel",
    "GetBindingsResult",
    "GraphEdgeModel",
    "NotebookGraphModel",
    "OpenExploreSessionResult",
    "PackageNotebookResult",
    "PackagedPortModel",
    "PackagingProblemModel",
    "ReadNotebookResult",
    "RunCellResult",
    "UnresolvedReadModel",
    "append_cell",
    "check_packaging",
    "get_bindings",
    "open_explore_session",
    "package_notebook",
    "read_notebook",
    "run_cell",
]
