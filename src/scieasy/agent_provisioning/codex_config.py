"""Write project-scope Codex MCP config (ADR-040 §3.7).

Writes ``<project>/.codex/config.toml`` with a single
``[mcp_servers.scieasy]`` block + nested ``[mcp_servers.scieasy.env]``
table pinning ``SCIEASY_PROJECT_DIR`` to the absolute project path.

Codex 2026 walks from project root to cwd loading every
``.codex/config.toml`` — so the project-scope file takes precedence over
``~/.codex/config.toml`` for sessions opened inside this project. Combined
with ADR §3.5's ``AGENTS.md``, this brings Codex prod-env to parity with
Claude Code: no argv changes in ``spawn_codex`` needed.

Implementation MUST reuse ``install._render_codex_block(project_dir)``
from ``src/scieasy/cli/install.py`` so the §3.7 auto-provisioned TOML is
byte-identical to what ``scieasy install --target codex --scope project``
emits (Install-parity track owns the function). This is the contract
contractually enforced by integration test in I40c+I40d.

Trust-model note: Codex honors project-scope ``.codex/config.toml`` only
for projects the user has marked trusted. First-open prompt is acceptable
UX per ADR §3.7.

S40c skeleton: NotImplementedError stub. I40c (#1013) implements.
"""

from __future__ import annotations

from pathlib import Path


def write_codex_config(
    project_dir: Path,
    *,
    force: bool = False,
) -> list[str]:
    """Write ``<project>/.codex/config.toml``.

    Inputs:
      project_dir : Path to project root (absolute path is encoded into
                    the TOML as the ``SCIEASY_PROJECT_DIR`` env var value).
      force       : True to overwrite; False to preserve.

    Outputs (returned list):
      - ".codex/config.toml"

    Idempotency (force=False):
      Preserves existing file. Note: a user-managed project-scope
      config may legitimately exist; preserving it is the safe default.
      I40c may evolve to a structural merge ("only inject our
      ``[mcp_servers.scieasy]`` block if absent") in Phase 3 if user
      reports surface — flag for Phase 3 design.

    TOML content (per ADR §3.7):
      [mcp_servers.scieasy]
      command = "<sys.executable>"
      args = ["-m", "scieasy", "mcp-bridge"]

      [mcp_servers.scieasy.env]
      SCIEASY_PROJECT_DIR = "<absolute project path>"

    Implementation note for I40c:
      Import ``_render_codex_block`` from ``scieasy.cli.install`` and
      pass ``project_dir`` so the same string is emitted as
      ``scieasy install --target codex --scope project`` would emit
      against the same cwd. This is the §3.7 / §3.9 unification point.

    Error handling:
      OSError / PermissionError on write surfaces to orchestrator as
      a ``ProvisionResult.failed`` entry.
    """
    # TODO(#1013): I40c Phase 2a — implement per ADR §3.7.
    #   Out of scope per ADR-040 §3.7 (S40c skeleton).
    #   Followup: https://github.com/zjzcpj/SciEasy/issues/1013.
    raise NotImplementedError("S40c skeleton — I40c impl in Phase 2a (#1013)")
