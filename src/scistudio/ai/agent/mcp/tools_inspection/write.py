"""Write-class inspection tool — ``update_block_config`` (ruamel round-trip).

Patch one block's configuration in a workflow YAML while preserving
comments and key order. Extracted from the original single-file
``tools_inspection.py`` (#1431, umbrella #1427). No behavior change.
"""

from __future__ import annotations

import contextlib
import logging
import os
import tempfile
from pathlib import Path
from typing import Annotated, Any

from filelock import FileLock, Timeout
from pydantic import Field

from scistudio.ai.agent.mcp._context import _resolve_project_path
from scistudio.ai.agent.mcp.server import mcp
from scistudio.ai.agent.mcp.tools_inspection._helpers import _LOCK_TIMEOUT_SECONDS
from scistudio.ai.agent.mcp.tools_inspection._models import UpdateBlockConfigResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# (c.6) update_block_config  (write-class, ruamel round-trip)
# ---------------------------------------------------------------------------


@mcp.tool(name="update_block_config", tags={"category:inspection", "write"})
async def update_block_config(
    workflow_path: Annotated[str, Field(description="Project-relative path under workflows/.")],
    block_id: Annotated[str, Field(description="Block id within the workflow.")],
    params: Annotated[
        dict[str, Any],
        Field(description="Dict of param keys to set or overwrite on the block's config."),
    ],
) -> UpdateBlockConfigResult:
    """Patch one block's configuration in a workflow YAML (preserves comments).

    Use when:
      - You want to change one block's params without re-emitting the
        whole workflow YAML.
      - You need to preserve user comments and key order.

    Do NOT use to:
      - Rewrite an entire workflow — use ``write_workflow`` (whole-file
        replace).
      - Edit ``workflows/*.yaml`` via Bash/Edit/Write — the
        protect_workflow_yaml hook (ADR-040 §3.6) will block such calls.
        This tool is the ONLY supported per-block-patch path.

    Uses ruamel.yaml round-trip mode to preserve formatting.
    """
    # TODO(#732): once workflow versioning API ships, share the lock
    # boundary with the canvas's optimistic-concurrency model.
    # Out of scope per ADR-040 §3.1 / phase: 2a I40a.
    # Followup: https://github.com/zjzcpj/SciStudio/issues/732.
    from ruamel.yaml import YAML

    p = _resolve_project_path(workflow_path)
    if not p.exists():
        raise FileNotFoundError(f"Workflow file not found: {p}")
    lock_path = str(p) + ".lock"
    yaml_rt = YAML(typ="rt")
    yaml_rt.preserve_quotes = True

    try:
        with FileLock(lock_path, timeout=_LOCK_TIMEOUT_SECONDS):
            old = p.read_text(encoding="utf-8")
            with p.open("r", encoding="utf-8") as fh:
                doc = yaml_rt.load(fh)
            if not isinstance(doc, dict):
                raise ValueError(f"Workflow YAML at {p} is not a mapping")
            wf_block = doc.get("workflow") or doc
            nodes = wf_block.get("nodes")
            if not isinstance(nodes, list):
                raise ValueError(f"Workflow YAML at {p} has no nodes list")
            target = None
            for node in nodes:
                if isinstance(node, dict) and node.get("id") == block_id:
                    target = node
                    break
            if target is None:
                raise KeyError(f"Block '{block_id}' not found in workflow {p}")
            config_node = target.get("config")
            if not isinstance(config_node, dict):
                target["config"] = dict(params)
            else:
                for key, value in params.items():
                    config_node[key] = value

            fd, tmp = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=str(p.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as out_fh:
                    yaml_rt.dump(doc, out_fh)
                bytes_written = Path(tmp).stat().st_size
                os.replace(tmp, p)
            except Exception:
                with contextlib.suppress(OSError):
                    os.unlink(tmp)
                raise
    except Timeout as exc:
        raise TimeoutError(f"update_block_config: could not acquire lock for {p}") from exc

    new = p.read_text(encoding="utf-8")
    diff_summary = f"{len(new.encode('utf-8'))} bytes (was {len(old.encode('utf-8'))})"
    logger.info("update_block_config: %s block=%s (%s)", p, block_id, diff_summary)
    return UpdateBlockConfigResult(
        block_id=block_id,
        diff_summary=diff_summary,
        bytes_written=bytes_written,
        workflow_path=str(p),
    )


__all__ = ["update_block_config"]
