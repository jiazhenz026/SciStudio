"""Category (a) MCP tools — workflow inspection and execution (10 tools).

ADR-040 §3.1 FastMCP migration, I40a Phase 2a implementation. All tool
functions are decorated with ``@mcp.tool(name=..., tags={...})`` and
return Pydantic result models with ``next_step: str`` on write-class
tools per ADR-040 §3.2.

The 10 tools are:

Read-class (6): ``list_blocks``, ``get_block_schema``, ``list_types``,
``get_workflow``, ``validate_workflow``, ``get_run_status``.

Write-class (4): ``write_workflow``, ``run_workflow``, ``cancel_run``,
``finish_ai_block`` (ADR-035 §3.5 path (a)).

Per ADR-040 §3.2 style guide, each docstring is an imperative
one-liner followed by a "Use when … / Do NOT use to …" anti-pattern
section, and each write-class result model carries ``next_step``
pointing at the canonical follow-up tool.

Sub-package layout (#1431, umbrella #1427 — pure structural refactor):

* :mod:`._helpers` — shared lock timeout, dict/diff/path helpers, runtime accessor.
* :mod:`._errors` — run-level ``block_error`` capture state + subscriber.
* :mod:`._models` — Pydantic envelopes for every tool return type.
* :mod:`.read` — 6 read-class tools.
* :mod:`.write` — 3 write-class tools (write_workflow / run_workflow / cancel_run).
* :mod:`.finish_ai_block` — ``finish_ai_block`` tool (ADR-035 §3.5).

The package preserves the legacy ``tools_workflow`` import surface:
every public name (tool functions, Pydantic models, internal helpers
referenced by other modules or tests) is re-exported below so that
``from scistudio.ai.agent.mcp.tools_workflow import X`` continues to work
for any X that was reachable before the refactor.
"""

from __future__ import annotations

# Sub-modules with @mcp.tool decorators must be imported for their
# side-effects (FastMCP tool registration). Read+write+finish_ai_block
# all decorate the shared ``server.mcp`` instance.
from scistudio.ai.agent.mcp.tools_workflow import (  # noqa: F401
    _errors,
    _helpers,
    _models,
)
from scistudio.ai.agent.mcp.tools_workflow import (
    finish_ai_block as _finish_ai_block_module,  # noqa: F401  # side-effect import
)
from scistudio.ai.agent.mcp.tools_workflow import (
    read as _read_module,  # noqa: F401  # side-effect import: @mcp.tool registrations
)
from scistudio.ai.agent.mcp.tools_workflow import (
    write as _write_module,  # noqa: F401  # side-effect import: @mcp.tool registrations
)
from scistudio.ai.agent.mcp.tools_workflow._errors import (
    _collect_run_errors,
    _ensure_error_subscriber,
    _error_subscriber_installed,
    _run_block_errors,
)
from scistudio.ai.agent.mcp.tools_workflow._helpers import (
    _LOCK_TIMEOUT_SECONDS,
    _atomic_write_text,
    _diff_summary,
    _get_workflow_runtime,
    _looks_like_inline_yaml,
    _port_to_dict,
    _resolve_ai_block_run_dir,
    _spec_signature,
    _spec_to_dict,
)
from scistudio.ai.agent.mcp.tools_workflow._models import (
    ActiveWorkflowContextResult,
    BlockErrorEntry,
    BlockSchemaResult,
    BlockSummary,
    CancelRunResult,
    EditWorkflowResult,
    FinishAIBlockError,
    FinishAIBlockOK,
    GetRunStatusResult,
    ListBlocksResult,
    ListTypesResult,
    RunWorkflowResult,
    TypeEntry,
    ValidateWorkflowResult,
    WorkflowDefinitionEnvelope,
    WriteWorkflowResult,
)
from scistudio.ai.agent.mcp.tools_workflow.finish_ai_block import (
    _TOOL_MODULE_ID,
    finish_ai_block,
)
from scistudio.ai.agent.mcp.tools_workflow.read import (
    get_active_workflow_context,
    get_block_schema,
    get_run_status,
    get_workflow,
    list_blocks,
    list_types,
    validate_workflow,
)
from scistudio.ai.agent.mcp.tools_workflow.write import (
    WorkflowEdit,
    cancel_run,
    edit_workflow,
    run_workflow,
    write_workflow,
)

__all__ = [  # noqa: RUF022 — grouped by role (helpers / models / tools)
    # ---- internal helpers preserved for cross-module + test use ----
    "_LOCK_TIMEOUT_SECONDS",
    "_TOOL_MODULE_ID",
    "_atomic_write_text",
    "_collect_run_errors",
    "_diff_summary",
    "_ensure_error_subscriber",
    "_error_subscriber_installed",
    "_get_workflow_runtime",
    "_looks_like_inline_yaml",
    "_port_to_dict",
    "_resolve_ai_block_run_dir",
    "_run_block_errors",
    "_spec_signature",
    "_spec_to_dict",
    # ---- Pydantic models ----
    "ActiveWorkflowContextResult",
    "BlockErrorEntry",
    "BlockSchemaResult",
    "BlockSummary",
    "CancelRunResult",
    "EditWorkflowResult",
    "FinishAIBlockError",
    "FinishAIBlockOK",
    "GetRunStatusResult",
    "ListBlocksResult",
    "ListTypesResult",
    "RunWorkflowResult",
    "TypeEntry",
    "ValidateWorkflowResult",
    "WorkflowDefinitionEnvelope",
    "WorkflowEdit",
    "WriteWorkflowResult",
    # ---- 12 MCP tool functions ----
    "cancel_run",
    "edit_workflow",
    "finish_ai_block",
    "get_active_workflow_context",
    "get_block_schema",
    "get_run_status",
    "get_workflow",
    "list_blocks",
    "list_types",
    "run_workflow",
    "validate_workflow",
    "write_workflow",
]
