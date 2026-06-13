# CLI integration — use `claude` or `codex` against SciStudio projects

This guide is for developers who want to drive SciStudio projects from
**their own** terminal CLI (the user-installed `claude` or `codex`),
**outside** the SciStudio GUI. The GUI's embedded coding agent already
does this internally; CLI integration exposes the same MCP surface plus
a SciStudio-aware skill to any compatible client.

The result: `pip install scistudio && scistudio install --all && claude`
in a project dir, and your CLI immediately has 33 SciStudio tools plus a
skill describing how to use them.

## Quick start

```bash
# 1. Install SciStudio.
pip install scistudio
# Source checkout development should use an isolated env plus PYTHONPATH=src,
# not an editable install from a shared worktree.

# 2. Wire up your CLI of choice. --all installs claude + codex + skill at user scope.
scistudio install --all

# 3. cd into a SciStudio project and launch your CLI.
cd ~/work/my-microplastics-project
claude          # or: codex
```

In the chat, try: "list all available block types in this project". The
CLI should call `mcp__scistudio__list_blocks` via the bridge and return
the actual registry.

## The pieces

There are four moving parts behind the curtain.

### 1. `scistudio mcp-bridge` (stdio adapter)

A small subprocess invoked by `claude` / `codex`. Reads JSON-RPC frames
from its stdin and writes responses to its stdout, proxying to a
SciStudio MCP server. Two modes (auto-selected at startup):

- **Attached mode** — a SciStudio backend is already running for this
  project (you have `scistudio gui` or `scistudio serve` open in another
  terminal). The bridge connects to the backend's local socket and
  every CLI shares the same project state. Writes from the CLI
  (`write_workflow`, `update_block_config`) are visible to the GUI on
  the next read.
- **Standalone mode** — no backend is running. The bridge spins up an
  in-process MCP server itself, scoped to
  `$SCISTUDIO_PROJECT_DIR` (or the current working directory if it
  contains a `project.yaml`). The block + type registries are scanned
  from disk at startup (~1-2 s); after that, tool calls are served
  directly. Tear-down happens on stdin EOF.

The bridge is **stateless across invocations** in standalone mode: each
`claude` session that wasn't started while a backend was running gets
its own in-process MCP server. Writes are persisted to disk, so two
standalone bridges see each other's writes on the next read — but they
don't share an in-memory run history. If you need shared run state,
launch the backend first (`scistudio serve` or `scistudio gui`).

### 2. `scistudio install`

A Typer subcommand that wires the MCP server into a CLI's config file.
Targets and behaviours:

| Target / scope            | File(s) mutated                                                       |
|---------------------------|-----------------------------------------------------------------------|
| `claude` / `user`         | `~/.claude.json` (`mcpServers`)                                       |
| `claude` / `project`      | `<cwd>/.mcp.json` (`mcpServers`)                                      |
| `codex` / `user`          | `~/.codex/config.toml` (`[mcp_servers.scistudio]`)                      |
| `codex` / `project`       | `<cwd>/.codex/config.toml` (`[mcp_servers.scistudio]`) — Codex 2026     |
| `skill` / `user`          | `~/.claude/skills/scistudio/` AND `~/.agents/skills/scistudio/`           |
| `skill` / `project`       | `<cwd>/.claude/skills/scistudio/` AND `<cwd>/.agents/skills/scistudio/`   |
| `--all` (user scope)      | All of the above                                                       |

All operations are **idempotent**; re-running produces a `noop` result.
Use `--remove` to undo any install.

The `--skill` flag **cross-installs** the SciStudio skill tree to both
Claude (`.claude/skills/scistudio/`) and Codex (`.agents/skills/scistudio/`)
providers in a single call — both CLIs use identical `SKILL.md` format
(frontmatter + progressive-disclosure body), and the cross-install costs
one extra `shutil.copytree` per scope (ADR-040 §3.9).

Examples:

```bash
# User-scope claude + cross-installed skill (both providers).
scistudio install --target claude --scope user --skill

# Project-scope claude only (writes <cwd>/.mcp.json).
scistudio install --target claude --scope project

# Project-scope codex MCP entry — writes <cwd>/.codex/config.toml
# (Codex 2026 walks from project root loading every .codex/config.toml).
scistudio install --target codex --scope project

# User-scope codex MCP entry.
scistudio install --target codex

# Convenience.
scistudio install --all

# Reverse anything.
scistudio install --target claude --scope user --remove
scistudio install --all --remove
```

> **Codex 2026 project-scope support.** Codex 2026 introduced
> `<project>/.codex/config.toml` discovery (Codex walks from the project
> root loading every `.codex/config.toml` it finds). Older Codex
> releases honoured only user-scope `~/.codex/config.toml`. Passing
> `--target codex --scope project` writes a project-scope MCP entry
> that takes effect once Codex is launched inside that project, with
> `SCISTUDIO_PROJECT_DIR` pinned via the `[mcp_servers.scistudio.env]`
> table. Codex's "trusted projects" model means the first open after
> install may prompt for trust acceptance — one-time UX friction.

### 3. SciStudio skill

A packaged directory `src/scistudio/_skills/scistudio/` (per ADR-040 §3.4,
bundled with the wheel and installed by `scistudio install --skill`)
containing:

- `SKILL.md` — base identity + thin pointer index to the 6 task-scoped
  sub-skills.
- `scistudio-build-workflow/SKILL.md`, `scistudio-write-block/SKILL.md`,
  `scistudio-debug-run/SKILL.md`, `scistudio-inspect-data/SKILL.md`,
  `scistudio-project-qa/SKILL.md`, `scistudio-write-plot/SKILL.md`
  (ADR-048 SPEC 2 — preview-only plot authoring) — JIT-loaded task skills
  with progressive-disclosure semantics (frontmatter `description`
  triggers body load on demand).

Per ADR-040 §3.9, `scistudio install --skill` **cross-installs** the
entire 7-file tree to both providers:

- Claude Code reads `~/.claude/skills/scistudio/` (user) or
  `<project>/.claude/skills/scistudio/` (project).
- Codex reads `~/.agents/skills/scistudio/` (user) or
  `<project>/.agents/skills/scistudio/` (project).

Both providers auto-discover skills at session start and surface them
in their respective slash-command pickers. The base `SKILL.md` body is
also the **single source of truth** for the embedded GUI agent's system
prompt: at session start the GUI reads the packaged tree (via
`importlib.resources`) and uses it as the `--append-system-prompt`
payload. If a skill file changes, both the GUI and any external
claude/codex see the change after a restart.

If the SKILL.md file is missing at runtime (e.g. a wheel install
without packaged skill data), the GUI falls back to an inline copy of
the prompt body and logs a warning.

### 4. This documentation

You're reading it. The README links here under "Developer
integrations".

## How modes interact (GUI + CLI side by side)

| Scenario | Where state lives |
|---|---|
| GUI running, no CLI | Backend in-memory + on-disk. |
| GUI running, CLI launched in same project | CLI's bridge enters **attached** mode and shares the backend. Writes visible to the GUI on next read. |
| GUI not running, CLI launched | CLI's bridge enters **standalone** mode. The CLI has its own runtime. Persisted state (workflow YAMLs, blocks, data) is shared via disk; live run state is not. |
| Two CLIs, no GUI | Each CLI runs its own standalone runtime. Reads from the same disk; in-flight run state is per-process. |
| Two CLIs + GUI | All three share the GUI's backend in attached mode. |

In short: **persisted state is always shared**; **live run state is
shared whenever the backend is up**.

## Troubleshooting

**The CLI can't find tools / says no SciStudio MCP server.**

- Confirm install: `scistudio install --target claude --scope user`
  should report `installed` or `noop`.
- Check the config file: `cat ~/.claude.json` should contain
  `"mcpServers": { "scistudio": ... }` near the top.
- Check `scistudio` is on PATH: `which scistudio` (or `where scistudio` on
  Windows) should return a path. If not, the bridge can't launch.

**Standalone bridge fails with "no project is currently open".**

The bridge resolves `$SCISTUDIO_PROJECT_DIR` from the env, falling back
to the current working directory if it contains `project.yaml`. If
both are absent, project-scoped tools error with a clear message —
this is intentional. Either `cd` into a SciStudio project or set
`SCISTUDIO_PROJECT_DIR` in the CLI's MCP-server `env` block.

**Stale port file / socket on Windows.**

When a SciStudio backend crashes, the `<project>/.scistudio/mcp.sock.port`
sentinel may be left behind. The bridge attempts the connect anyway
and, on failure, falls back to standalone mode automatically with a
note on stderr.

**Codex MCP add removes my custom TOML formatting.**

The install command tries to preserve other keys in the target file
(either `~/.codex/config.toml` for user scope or
`<cwd>/.codex/config.toml` for project scope per Codex 2026), but it
does normalise the `[mcp_servers.scistudio]` block to a canonical
layout. If you've heavily customised the file, inspect the diff
before/after.

## Git compatibility (ADR-039)

SciStudio bundles a portable `git` binary at `<install>/resources/git/bin/git[.exe]`
(MinGit on Windows, static-built `git` on macOS/Linux) for its own source
version control operations. The bundled binary is used by the in-process
`GitEngine` subprocess wrapper at `src/scistudio/core/versioning/git_engine.py`.

External `git` interactions remain fully supported and unblocked:

- SciStudio does **not** lock `.git/`. Users can run any external `git` CLI in
  parallel from a terminal, GUI tool (GitHub Desktop, GitKraken, JetBrains
  built-in git, VS Code), or AI agent's shell — and SciStudio's `workflow_watcher`
  (ADR-034 Phase 2, extended by ADR-039 §3.8) detects the resulting
  `.git/HEAD` change and refreshes its UI cache.
- The `scistudio gui` developer CLI (non-desktop-bundled installs) falls back
  to the user's system `git` if no bundled binary is present.

### Commit-message prefix convention

The GUI History panel filters commits by message prefix per ADR-039 §3.4 and
§3.4a. External tools and CI should honor the same convention so the human +
agent + auto layers stay visually distinguishable:

| Prefix | Meaning | GUI default visibility | Icon |
|---|---|---|---|
| `auto:` | Pre-run squash commit emitted by SciStudio when the working tree is dirty at Run time | **Hidden** under default "Manual milestones" filter | small grey dot in graph |
| `agent:` | Commit authored by an AI agent (ADR-034 embedded coding agent, ADR-035 AI Block, or any programmatic flow). Format: `agent: <summary> (session=<chat_or_block_run_id>)` | Visible | 🤖 |
| *(no prefix)* | Manual user commit | Visible | 👤 |

When an external tool or script makes commits inside a SciStudio project, prefer
the no-prefix form for human-driven changes. Reserve `auto:` and `agent:` for
their specific machine-driven contexts so the filter remains meaningful.

## Out of scope

- A hosted / shared SciStudio backend across machines.
- Auto-injecting the SciStudio tools into existing `claude` conversations
  (the install is per-project / per-user, not per-conversation).
- A SciStudio plugin marketplace.

## See also

- `docs/adr/ADR-033.md` — embedded coding agent architecture.
- `docs/adr/ADR-038.md` — unified run lineage database (supersedes ADR-032).
- `docs/adr/ADR-039.md` — git-backed source version control.
- `docs/adr/ADR-040.md` — CLI skill and MCP integration.
- `CLAUDE.md` — non-negotiable project principles (repo root).
