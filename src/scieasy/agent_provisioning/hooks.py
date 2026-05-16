"""Write project-scoped hook config + scripts (ADR-040 §3.6).

Provisions ``<project>/.claude/settings.json`` and the 6 hook scripts at
``<project>/.claude/hooks/`` for Claude Code's hook system.

Per ADR §3.6, the hook set is:

  PreToolUse (3):
    - hook_deny_scieasy_cli.py                      (matcher: Bash)
    - hook_protect_workflow_yaml.py                 (matcher: Edit|Write)
    - hook_enforce_list_blocks_before_block_write.py
        (matcher: Edit|Write|Bash|mcp__scieasy__scaffold_block)

  PostToolUse (3):
    - hook_remind_poll_status.py                    (matcher: mcp__scieasy__run_workflow)
    - hook_mark_list_blocks_called.py               (matcher: mcp__scieasy__list_blocks)
    - hook_enforce_concrete_port_types.py
        (matcher: Edit|Write|mcp__scieasy__scaffold_block)

Hook scripts read JSON from stdin (Claude Code's hook stdin contract);
exit code 2 blocks the tool call (PreToolUse only); exit code 0 passes.
Codex's hook system has documented gaps (ADR §3.10) — these hooks govern
Claude Code only.

S40c skeleton: NotImplementedError stub + 6 hook templates as exit-0
placeholders. I40c (#1013) authors real hook bodies.
"""

from __future__ import annotations

from pathlib import Path


def write_hooks(
    project_dir: Path,
    *,
    force: bool = False,
) -> list[str]:
    """Write ``<project>/.claude/settings.json`` + 6 hook scripts.

    Inputs:
      project_dir : Path to project root.
      force       : True to overwrite; False to preserve user edits.

    Outputs (returned list of relative paths actually written):
      - ".claude/settings.json"
      - ".claude/hooks/deny_scieasy_cli.py"
      - ".claude/hooks/protect_workflow_yaml.py"
      - ".claude/hooks/enforce_list_blocks_before_block_write.py"
      - ".claude/hooks/remind_poll_status.py"
      - ".claude/hooks/mark_list_blocks_called.py"
      - ".claude/hooks/enforce_concrete_port_types.py"

    Idempotency (force=False default):
      Each file is checked for existence before write. Already-present
      files are omitted from the return list. settings.json in particular
      may have user-added hook entries — DO NOT clobber.

    Hook templates source:
      Source-of-truth templates live at
      ``src/scieasy/agent_provisioning/templates/hook_*.py``. I40c will
      load each via ``importlib.resources`` (wheel-safe per #824) and
      copy to ``<project>/.claude/hooks/<name>.py`` (template prefix
      stripped). On POSIX, chmod +x is applied; on Windows, file is
      written as-is (Python interpreter is invoked explicitly in the
      settings.json command lines so the executable bit is not required).

    Error handling:
      May raise on filesystem failures. The orchestrator catches and
      records in ``ProvisionResult.failed``.

    Marker directory:
      The runtime marker directory ``<project>/.scieasy/.session-state/``
      (used by ``enforce_list_blocks_before_block_write.py`` /
      ``mark_list_blocks_called.py``) is gitignored by ADR-039's default
      .gitignore via the ``.scieasy/`` rule (per manifest §2.7).
      Creation of the directory itself is the hook's job (lazy on first
      ``mark_list_blocks_called`` invocation), not this provisioner's.
    """
    # TODO(#1013): I40c Phase 2a — implement per ADR §3.6.
    #   Out of scope per ADR-040 §3.6 (S40c skeleton).
    #   Followup: https://github.com/zjzcpj/SciEasy/issues/1013.
    raise NotImplementedError("S40c skeleton — I40c impl in Phase 2a (#1013)")
