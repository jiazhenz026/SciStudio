"""Category (c) MCP tools — run and data inspection (7 tools).

ADR-040 §3.1 FastMCP migration, I40a Phase 2a implementation.

The 7 tools are:

Read-class (6): ``get_block_output``, ``inspect_data``, ``preview_data``,
``get_lineage``, ``get_block_config``, ``get_block_logs``.
Write-class (1): ``update_block_config``.

Per the Phase 2 audit checklist, ``inspect_data`` and ``preview_data``
must never load > 8 MiB into RAM.

Sub-package layout (#1431, umbrella #1427 — pure structural refactor):

* :mod:`._helpers` — shared constants (caps, thumbnail dims, lock
  timeout) and ``_ref_from_dict``.
* :mod:`._models` — Pydantic envelopes for every tool return type.
* :mod:`._preview` — preview helpers (``_preview_dataframe``,
  ``_preview_array``, ``_preview_series``, ``_preview_text``,
  ``_preview_artifact``, ``_grayscale_png``).
* :mod:`.read` — 6 read-class tools.
* :mod:`.write` — ``update_block_config`` (the lone write-class tool).

The package-level API re-exports the canonical tool functions, Pydantic
models, and test-visible helper constants used by the MCP server.
"""

from __future__ import annotations

# Sub-modules with @mcp.tool decorators must be imported for their
# side-effects (FastMCP tool registration). Read+write both decorate
# the shared ``server.mcp`` instance.
from scistudio.ai.agent.mcp.tools_inspection import (  # noqa: F401
    _helpers,
    _models,
    _preview,
)
from scistudio.ai.agent.mcp.tools_inspection import (
    read as _read_module,  # noqa: F401  # side-effect import: @mcp.tool registrations
)
from scistudio.ai.agent.mcp.tools_inspection import (
    write as _write_module,  # noqa: F401  # side-effect import: @mcp.tool registrations
)
from scistudio.ai.agent.mcp.tools_inspection._helpers import (
    _BLOCK_LOG_TRUNCATE_BYTES,
    _DATAFRAME_PREVIEW_ROWS,
    _LOCK_TIMEOUT_SECONDS,
    _MAX_PREVIEW_BYTES,
    _SERIES_PREVIEW_POINTS,
    _TEXT_PREVIEW_CHARS,
    _THUMBNAIL_MAX_DIM,
    _ref_from_dict,
)
from scistudio.ai.agent.mcp.tools_inspection._models import (
    GetBlockConfigResult,
    GetBlockLogsResult,
    GetBlockOutputResult,
    GetLineageResult,
    InspectDataResult,
    LineageEdge,
    LineageNode,
    PreviewDataResult,
    TypeChainInfo,
    UpdateBlockConfigResult,
)
from scistudio.ai.agent.mcp.tools_inspection._preview import (
    _grayscale_png,
    _preview_array,
    _preview_artifact,
    _preview_dataframe,
    _preview_series,
    _preview_text,
)
from scistudio.ai.agent.mcp.tools_inspection.read import (
    get_block_config,
    get_block_logs,
    get_block_output,
    get_lineage,
    inspect_data,
    preview_data,
)
from scistudio.ai.agent.mcp.tools_inspection.write import update_block_config

__all__ = [  # noqa: RUF022 — grouped by role (constants / helpers / models / tools)
    # ---- package-level constants + helpers for cross-module + test use ----
    "_BLOCK_LOG_TRUNCATE_BYTES",
    "_DATAFRAME_PREVIEW_ROWS",
    "_LOCK_TIMEOUT_SECONDS",
    "_MAX_PREVIEW_BYTES",
    "_SERIES_PREVIEW_POINTS",
    "_TEXT_PREVIEW_CHARS",
    "_THUMBNAIL_MAX_DIM",
    "_grayscale_png",
    "_preview_array",
    "_preview_artifact",
    "_preview_dataframe",
    "_preview_series",
    "_preview_text",
    "_ref_from_dict",
    # ---- Pydantic models ----
    "GetBlockConfigResult",
    "GetBlockLogsResult",
    "GetBlockOutputResult",
    "GetLineageResult",
    "InspectDataResult",
    "LineageEdge",
    "LineageNode",
    "PreviewDataResult",
    "TypeChainInfo",
    "UpdateBlockConfigResult",
    # ---- 7 MCP tool functions ----
    "get_block_config",
    "get_block_logs",
    "get_block_output",
    "get_lineage",
    "inspect_data",
    "preview_data",
    "update_block_config",
]
