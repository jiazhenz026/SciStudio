"""``finish_ai_block`` tool — write-class (ADR-035 §3.5 path (a)).

Signal the active AI Block that all declared outputs have been written.
Extracted from the original single-file ``tools_workflow.py`` (#1431,
umbrella #1427). No behavior change.
"""

from __future__ import annotations

import datetime
import json
import logging
import uuid
from typing import Annotated

from pydantic import Field

from scistudio.ai.agent.mcp.server import mcp
from scistudio.ai.agent.mcp.tools_workflow._helpers import _resolve_ai_block_run_dir
from scistudio.ai.agent.mcp.tools_workflow._models import (
    FinishAIBlockError,
    FinishAIBlockOK,
)

logger = logging.getLogger(__name__)


# Synthesised module ID for log correlation.
_TOOL_MODULE_ID = f"mcp-workflow-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# (a.10) finish_ai_block  (write-class, ADR-035 §3.5)
# ---------------------------------------------------------------------------


@mcp.tool(name="finish_ai_block", tags={"category:workflow", "write"})
async def finish_ai_block(
    outputs: Annotated[
        dict[str, str] | None,
        Field(
            description=(
                "{port_name: absolute_or_project_relative_path} for every declared output port. "
                "None is accepted and treated as {} (FileWatcher path will validate via expected_path)."
            ),
        ),
    ] = None,
) -> FinishAIBlockOK | FinishAIBlockError:
    """Signal the active AI Block that all declared outputs have been written.

    Use when:
      - You're an AI Block worker that has finished writing every output
        file declared in the block's port manifest. Call this exactly once.

    Do NOT use to:
      - Signal partial completion — the AI Block treats the signal as
        terminal. If you can't produce an output, raise an error in your
        worker code instead.
      - Call from outside an AI Block context — returns
        ``not_in_ai_block_context`` error envelope per ADR-035 §3.5.

    The tool writes ``signals/finish_ai_block.json`` under the active
    run dir; the CompletionWatcher polls for that file and transitions
    the block from PAUSED → RUNNING for output validation. Atomic write
    (tempfile + os.replace) — partial writes cannot deceive the watcher.

    Error codes:
      - ``not_in_ai_block_context`` — no active AI Block run dir.
      - ``invalid_outputs`` — outputs is not dict[str, str].
      - ``already_finished`` — signal file already exists for this run.
      - ``io_error`` — disk-level write failure.
    """
    run_dir = _resolve_ai_block_run_dir()
    if run_dir is None:
        return FinishAIBlockError(
            code="not_in_ai_block_context",
            message=(
                "finish_ai_block can only be called from inside an AI Block. "
                "No active AI Block run dir was found via MCPContext.ai_block_run_dir "
                "or the SCISTUDIO_AI_BLOCK_RUN_DIR environment variable."
            ),
        )

    if outputs is None:
        outputs_norm: dict[str, str] = {}
    elif isinstance(outputs, dict):
        bad = [(k, type(v).__name__) for k, v in outputs.items() if not isinstance(k, str) or not isinstance(v, str)]
        if bad:
            return FinishAIBlockError(
                code="invalid_outputs",
                message=(f"finish_ai_block: outputs must be dict[str, str]. Bad entries (key, value-type): {bad}"),
            )
        outputs_norm = dict(outputs)
    else:
        return FinishAIBlockError(
            code="invalid_outputs",
            message=(f"finish_ai_block: outputs must be a dict, got {type(outputs).__name__}"),
        )

    signals_dir = run_dir / "signals"
    try:
        signals_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return FinishAIBlockError(
            code="io_error",
            message=f"finish_ai_block: failed to create signals dir: {exc}",
        )

    signal_path = signals_dir / "finish_ai_block.json"
    if signal_path.exists():
        return FinishAIBlockError(
            code="already_finished",
            message=(f"finish_ai_block has already been called for this AI Block run. Existing signal: {signal_path}"),
        )

    payload = {
        "outputs": outputs_norm,
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
    }
    body = json.dumps(payload, indent=2, sort_keys=True)
    # Resolve ``_atomic_write_text`` lazily via the package namespace so
    # ``monkeypatch.setattr(tools_workflow, "_atomic_write_text", ...)`` in
    # tests (see ``test_finish_ai_block_io_error_returns_envelope``) reaches
    # the real call site. Refactor preservation #1431 (umbrella #1427).
    from scistudio.ai.agent.mcp import tools_workflow as _pkg

    try:
        _pkg._atomic_write_text(signal_path, body)
    except OSError as exc:
        return FinishAIBlockError(
            code="io_error",
            message=f"finish_ai_block: failed to write signal file: {exc}",
        )

    logger.info(
        "finish_ai_block: wrote signal %s with %d output(s)",
        signal_path,
        len(outputs_norm),
    )
    return FinishAIBlockOK(signal_path=str(signal_path))


__all__: list[str] = [
    "_TOOL_MODULE_ID",
    "finish_ai_block",
]
