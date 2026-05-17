# Agent provisioning (ADR-040 §5.3)

This page describes the per-project agent assets that SciEasy installs
automatically at project creation and on every `open_project` /
`scieasy init` invocation.

## What gets installed

Every SciEasy project receives the following set of agent-facing files
the first time it is created or opened:

```
<project>/
  CLAUDE.md                                # Claude Code agent guide (ADR-040 §3.5)
  AGENTS.md                                # Codex agent guide (byte-identical to CLAUDE.md)
  .claude/
    settings.json                          # Claude Code PreToolUse + PostToolUse hook config
    .scieasy-provision-version             # Version marker (current: 0.1.0)
    hooks/
      deny_scieasy_cli.py                  # PreToolUse / Bash — blocks `scieasy <subcommand>`
      protect_workflow_yaml.py             # PreToolUse / Edit|Write — blocks workflows/*.yaml writes
      enforce_list_blocks_before_block_write.py
                                           # PreToolUse — requires list_blocks call before authoring a block
      remind_poll_status.py                # PostToolUse / run_workflow — stderr reminder to poll
      mark_list_blocks_called.py           # PostToolUse / list_blocks — writes session marker
      enforce_concrete_port_types.py       # PostToolUse — stderr-warns on DataObject ports
    skills/scieasy/                        # 6 task-scoped Claude Code skills
      scieasy/SKILL.md                     # base index
      scieasy-build-workflow/SKILL.md
      scieasy-write-block/SKILL.md
      scieasy-debug-run/SKILL.md
      scieasy-inspect-data/SKILL.md
      scieasy-project-qa/SKILL.md
  .agents/skills/scieasy/                  # 6 task-scoped Codex skills (mirror of .claude/skills/)
    scieasy/SKILL.md
    ... (5 more)
  .codex/
    config.toml                            # project-scope MCP server config
```

All filesystem-only — no network, no daemons, no external binaries.

## When provisioning runs

Three entry points all converge on
`scieasy.agent_provisioning.install_project_agent_assets`:

1. `ApiRuntime.create_project` (the GUI/HTTP path) — runs AFTER git init,
   BEFORE `open_project`. The initial commit is clean; provisioned files
   land in the user's second commit (on the first manual checkpoint).
2. `ApiRuntime.open_project` (every open) — runs AFTER git re-init,
   BEFORE the MCP port publishes. Idempotent top-up: missing assets are
   restored, user-customized assets are preserved.
3. `scieasy init <name>` (CLI parity per ADR-039 §6) — same ordering:
   git init → provisioning → final echo.

Failures are non-fatal per ADR-040 §7. The provisioning function returns
a `ProvisionResult` dataclass that records `written` / `skipped` /
`failed` per-path; partial failure logs a WARNING and the project still
opens.

## Idempotency contract (`force=False` default)

With `force=False`:

- A file that already exists at the target path is **preserved
  verbatim**. The user is free to customize CLAUDE.md, hook scripts,
  skills, `.codex/config.toml`, and the hook `settings.json` — none will
  be clobbered on subsequent project opens.
- Missing files are restored from the bundled template.

With `force=True` (currently used only via tests; no UI/CLI surface yet):

- Every canonical file is overwritten from the template. User edits are
  lost.

A future Phase 3 design (#1011) may introduce hash-based "preserve only
if user-edited" semantics so canonical defaults can evolve while still
respecting customization. The current contract is conservative:
existence-check only.

## Disabling provisioning

There is no global opt-out flag (yet). Per-asset disabling is
file-system-driven:

- **All hooks**: delete `<project>/.claude/settings.json` (Claude Code
  reads only this file; the scripts themselves do nothing without
  registered matchers). On next `open_project`, the file is restored —
  to make the disable permanent, also delete or recreate the file as an
  empty `{}` and `chmod -w` so subsequent provisioning skips it (the
  idempotency check is `Path.exists`).
- **Individual hooks**: edit `settings.json` to remove the offending
  matcher entry. The idempotent default preserves your edit.
- **Skills**: edit or delete individual `SKILL.md` files; on next open
  they are restored only if missing.
- **CLAUDE.md / AGENTS.md content**: edit freely; preserved on next open.

To temporarily disable provisioning entirely for debugging, monkeypatch
`scieasy.agent_provisioning.install_project_agent_assets` to a no-op.
Production users should not need this.

## Version marker

`<project>/.claude/.scieasy-provision-version` records the SciEasy
provisioning template version (`SCIEASY_PROVISION_VERSION`, currently
`0.1.0`). When the constant bumps in a future SciEasy release, an
upgrade flow (Phase 3 / #1011) will compare this marker to the new
constant and decide which canonical files to re-write. For 0.1.0, the
marker is rewritten on every run and is not yet used for upgrade
decisions.

## Development vs production environment boundary

ADR-040 §3.5 is explicit about the boundary:

- **SciEasy source repo `CLAUDE.md` (this file's parent dir)**: rules
  for *developing* SciEasy itself — gate workflow, ADR discipline, PR
  process, repo structure. ~800 lines.
- **Provisioned `<project>/CLAUDE.md`**: rules for an agent *using* a
  SciEasy project — MCP-only access, block-reuse discipline, workflow
  YAML through schema. ~50 lines.

The two are intentionally distinct. An end-user agent does not need to
know how to run `gate.py`, and a SciEasy contributor does not need to
have MCP-only access enforced on their dev machine.

## Cross-link to install.py (ADR-040 §3.9)

`<project>/.codex/config.toml` is rendered by
`scieasy.cli.install._render_codex_block(project_dir)` — the same
function `scieasy install --target codex --scope project` calls. The
auto-provisioned file is byte-identical to what an explicit
`scieasy install` would emit. A dedicated test
(`tests/agent_provisioning/test_codex_config.py::test_codex_config_matches_install_render`)
enforces this contract.

User-scope `~/.codex/config.toml` (written by `scieasy install --scope user`)
continues to work as a fallback for sessions opened outside any
SciEasy project. Codex 2026 walks both files; the project-scope entry
wins inside a SciEasy project tree.

## Known limitations

- **Codex hook system** has documented gaps (ADR-040 §3.10) — the 6
  hooks govern Claude Code only. The `AGENTS.md` file gives Codex the
  same prose-level guidance, but matcher-driven blocking is
  Claude-Code-specific until Codex hooks mature.
- **Layer 7 ACL on `<project>/blocks/`** (`#1015`) — hook-layer
  enforcement has known blind spots (exotic Bash writes, `python -c`,
  `mv`). True bulletproof enforcement requires filesystem ACLs and is
  out of scope per ADR-040 §3.10.
- **BlockRegistry runtime DataObject rejection** (`#1016`) — current
  hook is advisory (stderr warn); hard rejection is a future ADR.
- **Skill body content** — the 5 task-scoped SKILL.md files ship as
  placeholders on this implementation cut; Phase 2c (`#1013`) authors
  the real bodies. The base `scieasy` skill ships the legacy monolithic
  content as a fallback.
- **Windows hook execution** — CI is Ubuntu-only; settings.json
  invokes `python` explicitly so the executable bit is unused on
  Windows. Manual Windows verification is captured in the I40c PR.
