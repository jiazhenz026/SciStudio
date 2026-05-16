# CLI integration — use `claude` or `codex` against SciEasy projects

This guide is for developers who want to drive SciEasy projects from
**their own** terminal CLI (the user-installed `claude` or `codex`),
**outside** the SciEasy GUI. The GUI's embedded coding agent already
does this internally; CLI integration exposes the same MCP surface plus
a SciEasy-aware skill to any compatible client.

The result: `pip install scieasy && scieasy install --all && claude`
in a project dir, and your CLI immediately has 25 SciEasy tools plus a
skill describing how to use them.

## Quick start

```bash
# 1. Install SciEasy.
pip install scieasy   # or pip install -e . from a source checkout

# 2. Wire up your CLI of choice. --all installs claude + codex + skill at user scope.
scieasy install --all

# 3. cd into a SciEasy project and launch your CLI.
cd ~/work/my-microplastics-project
claude          # or: codex
```

In the chat, try: "list all available block types in this project". The
CLI should call `mcp__scieasy__list_blocks` via the bridge and return
the actual registry.

## The pieces

There are four moving parts behind the curtain.

### 1. `scieasy mcp-bridge` (stdio adapter)

A small subprocess invoked by `claude` / `codex`. Reads JSON-RPC frames
from its stdin and writes responses to its stdout, proxying to a
SciEasy MCP server. Two modes (auto-selected at startup):

- **Attached mode** — a SciEasy backend is already running for this
  project (you have `scieasy gui` or `scieasy serve` open in another
  terminal). The bridge connects to the backend's local socket and
  every CLI shares the same project state. Writes from the CLI
  (`write_workflow`, `update_block_config`) are visible to the GUI on
  the next read.
- **Standalone mode** — no backend is running. The bridge spins up an
  in-process MCP server itself, scoped to
  `$SCIEASY_PROJECT_DIR` (or the current working directory if it
  contains a `project.yaml`). The block + type registries are scanned
  from disk at startup (~1-2 s); after that, tool calls are served
  directly. Tear-down happens on stdin EOF.

The bridge is **stateless across invocations** in standalone mode: each
`claude` session that wasn't started while a backend was running gets
its own in-process MCP server. Writes are persisted to disk, so two
standalone bridges see each other's writes on the next read — but they
don't share an in-memory run history. If you need shared run state,
launch the backend first (`scieasy serve` or `scieasy gui`).

### 2. `scieasy install`

A Typer subcommand that wires the MCP server into a CLI's config file.
Targets and behaviours:

| Target / scope            | File(s) mutated                                                            |
|---------------------------|----------------------------------------------------------------------------|
| `claude` / `user`         | `~/.claude.json` (`mcpServers`)                                            |
| `claude` / `project`      | `<cwd>/.mcp.json` (`mcpServers`)                                           |
| `codex` / `user`          | `~/.codex/config.toml` (`[mcp_servers.scieasy]`)                           |
| `codex` / `project`       | `<cwd>/.codex/config.toml` (`[mcp_servers.scieasy]`, pins `SCIEASY_PROJECT_DIR`) |
| `skill` / `user`          | `~/.claude/skills/scieasy/` AND `~/.agents/skills/scieasy/`                |
| `skill` / `project`       | `<cwd>/.claude/skills/scieasy/` AND `<cwd>/.agents/skills/scieasy/`        |
| `--all` (chosen scope)    | All of the above                                                           |

All operations are **idempotent**; re-running produces a `noop` result.
Use `--remove` to undo any install.

`--skill` installs the bundle into BOTH provider trees (Claude
`.claude/skills/` AND Codex `.agents/skills/`) under the chosen scope.
This is per ADR-040 §3.9: a single `scieasy install --skill` call
serves whichever CLI the user reaches for next without forcing them to
pick a provider up front.

Examples:

```bash
# User-scope claude + skill, but skip codex.
scieasy install --target claude --scope user --skill

# Project-scope claude only (writes <cwd>/.mcp.json).
scieasy install --target claude --scope project

# Project-scope codex (writes <cwd>/.codex/config.toml). Requires
# Codex CLI 2026+ which discovers project-scope config files.
scieasy install --target codex --scope project

# Convenience.
scieasy install --all

# Reverse anything.
scieasy install --target claude --scope user --remove
scieasy install --all --remove
```

> **Codex project-scope requires Codex CLI 2026+.** Earlier Codex
> versions only read `~/.codex/config.toml`. If you're on an older
> Codex, use `--scope user` instead — the project's
> `SCIEASY_PROJECT_DIR` is still pinned in the user-scope env table.

### 3. SciEasy skill

A directory `scieasy/_skills/scieasy/` (packaged with the wheel; see
`pyproject.toml` `[tool.setuptools.package-data]`) containing:

- `SKILL.md` — frontmatter + body describing identity, core concepts,
  the 25 tools, working principles, and pointers to project docs.
- Task sub-skills (`scieasy-build-workflow/`, `scieasy-write-block/`,
  `scieasy-debug-run/`, `scieasy-inspect-data/`, `scieasy-project-qa/`)
  per ADR-040 §3.4.

`scieasy install --skill` cross-installs the bundle into BOTH provider
trees so any compatible CLI sees the skill:

- Claude Code auto-discovers `~/.claude/skills/<name>/SKILL.md`
  (user) and `<cwd>/.claude/skills/<name>/SKILL.md` (project) and
  surfaces them in the slash-command picker.
- Codex auto-discovers `~/.agents/skills/<name>/SKILL.md` (user) and
  `<cwd>/.agents/skills/<name>/SKILL.md` (project). The skill body is also the **single source of
truth** for the embedded GUI agent's system prompt: at session start
the GUI reads `skills/scieasy/SKILL.md` (with the tool catalog
re-synthesised from the live registry) and uses it as the
`--append-system-prompt` payload. If the skill file changes, both the
GUI and any external claude see the change after a restart.

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

**The CLI can't find tools / says no SciEasy MCP server.**

- Confirm install: `scieasy install --target claude --scope user`
  should report `installed` or `noop`.
- Check the config file: `cat ~/.claude.json` should contain
  `"mcpServers": { "scieasy": ... }` near the top.
- Check `scieasy` is on PATH: `which scieasy` (or `where scieasy` on
  Windows) should return a path. If not, the bridge can't launch.

**Standalone bridge fails with "no project is currently open".**

The bridge resolves `$SCIEASY_PROJECT_DIR` from the env, falling back
to the current working directory if it contains `project.yaml`. If
both are absent, project-scoped tools error with a clear message —
this is intentional. Either `cd` into a SciEasy project or set
`SCIEASY_PROJECT_DIR` in the CLI's MCP-server `env` block.

**Stale port file / socket on Windows.**

When a SciEasy backend crashes, the `<project>/.scieasy/mcp.sock.port`
sentinel may be left behind. The bridge attempts the connect anyway
and, on failure, falls back to standalone mode automatically with a
note on stderr.

**Codex MCP add removes my custom TOML formatting.**

The install command tries to preserve other keys in
`~/.codex/config.toml`, but it does normalise the `[mcp_servers.scieasy]`
block to a canonical layout. If you've heavily customised the file,
inspect the diff before/after.

## Git compatibility (ADR-039)

SciEasy bundles a portable `git` binary at `<install>/resources/git/bin/git[.exe]`
(MinGit on Windows, static-built `git` on macOS/Linux) for its own source
version control operations. The bundled binary is used by the in-process
`GitEngine` subprocess wrapper at `src/scieasy/core/versioning/git_engine.py`.

External `git` interactions remain fully supported and unblocked:

- SciEasy does **not** lock `.git/`. Users can run any external `git` CLI in
  parallel from a terminal, GUI tool (GitHub Desktop, GitKraken, JetBrains
  built-in git, VS Code), or AI agent's shell — and SciEasy's `workflow_watcher`
  (ADR-034 Phase 2, extended by ADR-039 §3.8) detects the resulting
  `.git/HEAD` change and refreshes its UI cache.
- The `scieasy gui` developer CLI (non-desktop-bundled installs) falls back
  to the user's system `git` if no bundled binary is present.

### Commit-message prefix convention

The GUI History panel filters commits by message prefix per ADR-039 §3.4 and
§3.4a. External tools and CI should honor the same convention so the human +
agent + auto layers stay visually distinguishable:

| Prefix | Meaning | GUI default visibility | Icon |
|---|---|---|---|
| `auto:` | Pre-run squash commit emitted by SciEasy when the working tree is dirty at Run time | **Hidden** under default "Manual milestones" filter | small grey dot in graph |
| `agent:` | Commit authored by an AI agent (ADR-034 embedded coding agent, ADR-035 AI Block, or any programmatic flow). Format: `agent: <summary> (session=<chat_or_block_run_id>)` | Visible | 🤖 |
| *(no prefix)* | Manual user commit | Visible | 👤 |

When an external tool or script makes commits inside a SciEasy project, prefer
the no-prefix form for human-driven changes. Reserve `auto:` and `agent:` for
their specific machine-driven contexts so the filter remains meaningful.

## Out of scope

- A hosted / shared SciEasy backend across machines.
- Auto-injecting the SciEasy tools into existing `claude` conversations
  (the install is per-project / per-user, not per-conversation).
- A SciEasy plugin marketplace.

## See also

- `docs/adr/ADR.md` ADR-033 — embedded coding agent architecture.
- `docs/adr/ADR-038.md` — unified run lineage database (supersedes ADR-032).
- `docs/adr/ADR-039.md` — git-backed source version control.
- `docs/specs/eca-spike-codex-format.md` — Codex provider parity notes.
- `docs/guides/ai-chat.md` — user-facing AI chat guide for the GUI.
- `CLAUDE.md` — non-negotiable project principles (repo root).
