"""Write CLAUDE.md + AGENTS.md sub-step (ADR-040 §3.5).

Both files are written verbatim from a single template at
``src/scieasy/agent_provisioning/templates/claude_agents_md.md``. Claude
Code reads ``<project>/CLAUDE.md``; Codex reads ``<project>/AGENTS.md``;
content is identical on both sides to ensure symmetric agent behavior.

S40c skeleton: NotImplementedError stub. I40c (#1013) implements.
"""

from __future__ import annotations

from pathlib import Path


def write_claude_agents_md(
    project_dir: Path,
    *,
    force: bool = False,
) -> list[str]:
    """Write ``<project>/CLAUDE.md`` and ``<project>/AGENTS.md``.

    Inputs:
      project_dir : Path to project root.
      force       : True to overwrite existing files; False to preserve.

    Outputs (returned list of relative paths actually written):
      - "CLAUDE.md"
      - "AGENTS.md"

    Idempotency (force=False default):
      If a target already exists, this function does NOT overwrite it.
      The path is omitted from the return list — caller categorizes it
      as ``skipped`` in ``ProvisionResult``.

    Error handling:
      May raise OSError / PermissionError on a failing write. The
      orchestrator catches and records in ``ProvisionResult.failed``;
      callers do not see this exception.

    Template source:
      The single template file lives at
      ``src/scieasy/agent_provisioning/templates/claude_agents_md.md``.
      I40c will load via ``importlib.resources.files("scieasy")
      / "agent_provisioning" / "templates" / "claude_agents_md.md"``
      so the template survives wheel installation (#824 precedent).
    """
    # TODO(#1013): I40c Phase 2a — implement per ADR §3.5.
    #   Out of scope per ADR-040 §3.5 (S40c skeleton).
    #   Followup: https://github.com/zjzcpj/SciEasy/issues/1013.
    raise NotImplementedError("S40c skeleton — I40c impl in Phase 2a (#1013)")
