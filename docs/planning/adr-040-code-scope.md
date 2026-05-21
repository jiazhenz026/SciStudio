# ADR-040 Code-Scope Manifest

> Per-track owner-file manifest for the ADR-040 cascade. Authored by code-scope investigation agent AC40 on 2026-05-16.
> Source: per-file `Read` + `Grep` of the SciStudio repo at main commit `4b6c54d`.
> Audience: Phase 1 skeleton agents (S40a/b/c/d) and Phase 2a impl agents (I40a/c/d).
> ADR: [../adr/ADR-040.md](../adr/ADR-040.md). Checklist: [./adr-040-checklist.md](./adr-040-checklist.md). Plan: `~/.claude/plans/bubbly-popping-frost.md`.

## How to use this file

1. Read only your track's section. Cross-track dependencies are surfaced in §6 Cross-cutting.
2. Limit writes to your track's "Owned files" list. Anything else is out-of-scope and must be left untouched (or TODO-tagged with a tracking issue per CLAUDE.md §7.6).
3. Cross-reference §8 Suspicious findings before any edit — pre-discovered ambiguities and stale comments are flagged there, not "discovered and fixed" inline.
4. Discrepancies between this manifest and ADR-040 §5.1 inventory are normal and explicit: §5.1 lists future-state files; this manifest documents current-state files. The mapping is in each track section.

---

## 1. Track FastMCP

### 1.1 Owned files (writable by S40a / I40a)

| File | LOC | Purpose |
|---|---|---|
| `src/scistudio/ai/agent/mcp/__init__.py` | 38 | Package init; re-exports `MCPServer` |
| `src/scistudio/ai/agent/mcp/_context.py` | 203 | `MCPContext` Protocol + global getter/setter + path-traversal helpers |
| `src/scistudio/ai/agent/mcp/_registry.py` | 279 | `ToolEntry` dataclass + `TOOL_REGISTRY` tuple (26 entries) — **deleted by FastMCP migration per ADR-040 §3.1** |
| `src/scistudio/ai/agent/mcp/runtime.py` | 203 | `StandaloneMCPRuntime` + `make_mcp_runtime` + `start_inprocess_server` for the standalone bridge |
| `src/scistudio/ai/agent/mcp/server.py` | 251 | Hand-rolled `MCPServer` class (asyncio JSON-RPC 2.0, line-delimited framing) — **rewritten by ADR-040 §3.1 to thin FastMCP wrapper** |
| `src/scistudio/ai/agent/mcp/tools_authoring.py` | 242 | 5 tools (b-category): `read_block_source`, `list_block_examples`, `scaffold_block`, `reload_blocks`, `run_block_tests` |
| `src/scistudio/ai/agent/mcp/tools_inspection.py` | 566 | 7 tools (c-category): `get_block_output`, `inspect_data`, `preview_data`, `get_lineage`, `get_block_config`, `update_block_config`, `get_block_logs` |
| `src/scistudio/ai/agent/mcp/tools_qa.py` | 233 | 4 tools (d-category): `search_docs`, `get_doc`, `list_data`, `get_project_info` |
| `src/scistudio/ai/agent/mcp/tools_workflow.py` | 752 | 10 tools (a-category): `list_blocks`, `get_block_schema`, `list_types`, `get_workflow`, `validate_workflow`, `write_workflow`, `run_workflow`, `cancel_run`, `get_run_status`, **`finish_ai_block`** (ADR-035 §3.5 — 26th tool) |
| `src/scistudio/ai/agent/system_prompt.py` | 166 | `compose_system_prompt` + `_load_skill_md` + `_render_tool_catalog` + `_splice_catalog` |

### 1.2 Tool count — VERIFIED

**Authoritative count = 26 tools** (counted via `ToolEntry(` occurrences in `_registry.py`: 26 entries declared at lines 65, 73, 80, 87, 94, 101, 108, 115, 122, 130, 137, 144, 151, 158, 166, 173, 180, 187, 194, 201, 208, 215, 222, 229, 236, 246).

- 25 baseline tools (5+5+5+10? — see breakdown below) + 1 (`finish_ai_block`, ADR-035 §3.5, present in `_registry.py:246-252`).
- Test `tests/ai/test_system_prompt.py:28` asserts `len(TOOL_REGISTRY) == 26`.
- Test `tests/ai/test_finish_ai_block_skeleton.py:30` also asserts `len(_registry.TOOL_REGISTRY) == 26`.

Breakdown by category (from `_registry.py` declaration order):

| Category | Count | Tools |
|---|---|---|
| `workflow` (read) | 6 | `list_blocks`, `get_block_schema`, `list_types`, `get_workflow`, `validate_workflow`, `get_run_status` |
| `workflow` (write) | 4 | `write_workflow`, `run_workflow`, `cancel_run`, `finish_ai_block` |
| `authoring` (read) | 2 | `read_block_source`, `list_block_examples` |
| `authoring` (write) | 3 | `scaffold_block`, `reload_blocks`, `run_block_tests` |
| `inspection` (read) | 6 | `get_block_output`, `inspect_data`, `preview_data`, `get_lineage`, `get_block_config`, `get_block_logs` |
| `inspection` (write) | 1 | `update_block_config` |
| `qa` (read) | 4 | `search_docs`, `get_doc`, `list_data`, `get_project_info` |
| **Total** | **26** | |

**Correction to checklist Phase 0.5 note**: the checklist row at line 116 says "Tool count is 27 (25 baseline + finish_ai_block)" — that arithmetic is wrong. 25 + 1 = 26, matching ADR-040 §1 and the live registry. This is flagged in §8 Suspicious findings as a docs/checklist inconsistency, not a code bug.

The `_registry.py` module docstring (line 1) says "25 tools" — also stale. Flagged in §8.

### 1.3 Exported symbols (FastMCP migration must preserve or fully replace)

**`src/scistudio/ai/agent/mcp/__init__.py`**
- `__all__ = ["MCPServer"]` (line 38) — re-exports `MCPServer` from `server.py`. Phase 1 must re-export the FastMCP server class under the same name OR update the one consumer (none in `src/` — only tests in `tests/ai/test_mcp_server_skeleton.py:115-119`).

**`src/scistudio/ai/agent/mcp/_context.py`**
- `MCPContext` (Protocol class, line 41) — structural typing protocol; FastMCP migration MUST preserve since tools depend on it.
- `set_context(ctx)` (line 61), `get_context()` (line 75), `get_optional_context()` (line 94)
- `_resolve_project_root(ctx)` (line 99), `_safe_under(root, target)` (line 112), `_resolve_project_path(target)` (line 141) — path-traversal guards used by 6+ tools.
- `__all__` exports (line 191): `MCPContext`, `_resolve_project_path`, `_resolve_project_root`, `_safe_under`, `get_context`, `get_optional_context`, `set_context`.

**`src/scistudio/ai/agent/mcp/_registry.py`** (DELETED by ADR §3.1)
- `ToolEntry` (dataclass, line 33-58), `TOOL_REGISTRY` (tuple, line 63-253), `lookup(name)` (line 256), `all_names()` (line 264), `by_category()` (line 274).
- **Callsites to fix** (all imports of `_registry` must move to a FastMCP `list_tools()` call or be deleted):
  - `src/scistudio/ai/agent/mcp/server.py:36` (`from scistudio.ai.agent.mcp import _registry`)
  - `src/scistudio/ai/agent/mcp/server.py:218` (`for entry in _registry.TOOL_REGISTRY`)
  - `src/scistudio/ai/agent/mcp/server.py:226` (`entry = _registry.lookup(name)`)
  - `src/scistudio/ai/agent/system_prompt.py:117` (`from scistudio.ai.agent.mcp._registry import TOOL_REGISTRY`)
  - `tests/ai/test_system_prompt.py:7` (`from scistudio.ai.agent.mcp._registry import TOOL_REGISTRY, all_names`)
  - `tests/ai/test_finish_ai_block_skeleton.py:20-30` (`from ... import _registry; _registry.TOOL_REGISTRY`)

**`src/scistudio/ai/agent/mcp/runtime.py`**
- `StandaloneMCPRuntime` (dataclass, line 43), `_build_block_registry` (line 82), `_build_type_registry` (line 94), `make_mcp_runtime` (line 103), `default_socket_path` (line 133), `start_inprocess_server` (line 145), `stop_inprocess_server` (line 187).
- Adapts standalone bridge runtime to current `MCPServer`. ADR §5.2 line 597 calls out this file as needing ~40 LOC of FastMCP adaptation.

**`src/scistudio/ai/agent/mcp/server.py`** (REWRITTEN by ADR §3.1)
- Class `MCPServer` (line 49): `__init__`, `start`, `stop`, `port` property, `_handle_client`, `dispatch`.
- Free functions `_ok` (line 246), `_error_response` (line 250).
- Constants `_PARSE_ERROR`, `_INVALID_REQUEST`, `_METHOD_NOT_FOUND`, `_INVALID_PARAMS`, `_INTERNAL_ERROR` (lines 42-46) — JSON-RPC 2.0 error codes; FastMCP wraps these so most callers won't notice, but the standalone-bridge accept loop in `runtime.py:145-184` directly drives `server.start()`/`server.stop()`.

**`src/scistudio/ai/agent/mcp/tools_workflow.py`** (10 tools)
- `list_blocks` (189), `get_block_schema` (209), `list_types` (242), `get_workflow` (263), `validate_workflow` (306), `write_workflow` (347), `run_workflow` (444), `cancel_run` (482), `get_run_status` (522), `finish_ai_block` (642).
- Helpers (PRIVATE — preserve): `_ensure_error_subscriber` (57), `_collect_run_errors` (99), `_spec_to_dict` (118), `_port_to_dict` (134), `_atomic_write_text` (147), `_diff_summary` (171), `_looks_like_inline_yaml` (298), `_get_workflow_runtime` (426), `_resolve_ai_block_run_dir` (609).

**`src/scistudio/ai/agent/mcp/tools_authoring.py`** (5 tools)
- `read_block_source` (25), `list_block_examples` (87), `scaffold_block` (158), `reload_blocks` (193), `run_block_tests` (210).
- Helper: `_snake_to_camel` (154); `_SCAFFOLD_TEMPLATE` module-level string constant.
- **Note for ADR §3.2a**: current `scaffold_block(name, category) -> dict[str, Any]` does NOT accept `input_ports` / `output_ports`. ADR §3.2a example signature with port specs + `warnings: list[str]` is a contract widening — Phase 1/2 skeleton must add the new parameters or the warnings logic has no input to inspect.

**`src/scistudio/ai/agent/mcp/tools_inspection.py`** (7 tools)
- `get_block_output`, `inspect_data`, `preview_data`, `get_lineage`, `get_block_config`, `update_block_config`, `get_block_logs`.

**`src/scistudio/ai/agent/mcp/tools_qa.py`** (4 tools)
- `search_docs`, `get_doc`, `list_data`, `get_project_info`.

**`src/scistudio/ai/agent/system_prompt.py`**
- Public: `compose_system_prompt(project_dir: Path) -> str` (line 39) — `project_dir` is currently UNUSED (#825).
- Private: `_load_skill_md()` (line 72), `_render_tool_catalog()` (line 108), `_splice_catalog(skill_md, catalog)` (line 143).
- Module constants: `_TOOL_CATALOG_BEGIN = "<!-- tool_catalog:begin -->"` (33), `_TOOL_CATALOG_END = "<!-- tool_catalog:end -->"` (34).
- `__all__ = ["compose_system_prompt"]` (line 36).

### 1.4 Callsites of public APIs

**`compose_system_prompt`** (Grep result `src/`):
- `src/scistudio/ai/agent/terminal.py:433` — lazy import inside `_write_system_prompt_tempfile(project_dir: Path)`.
- `src/scistudio/ai/agent/terminal.py:435` — invocation: `prompt = compose_system_prompt(project_dir)`.
- `src/scistudio/ai/agent/terminal.py:469` — docstring cross-ref.

**`MCPServer`** (Grep result `src/`):
- `src/scistudio/ai/agent/mcp/__init__.py:36` (re-export).
- `src/scistudio/ai/agent/mcp/runtime.py:36` (`if TYPE_CHECKING:`), `:162` (lazy import inside `start_inprocess_server`), `:178` (instantiation).
- `src/scistudio/api/app.py` (lifespan — instantiation point; verify in Phase 1).

**`TOOL_REGISTRY` / `_registry.lookup` / `_registry.all_names`** — see §1.3 above (6 callsites total).

### 1.5 Test files touching this track

| Test file | Relevant content |
|---|---|
| `tests/ai/test_system_prompt.py` (48 LOC) | All 4 tests assert behavior that survives FastMCP migration: `compose_system_prompt` reads SKILL.md, injects full catalog, is idempotent, uses marker block. Tool-name assertions iterate `all_names()` — must adapt to FastMCP `list_tools()` enumeration. |
| `tests/ai/test_mcp_server_skeleton.py` | Asserts `MCPServer` has `__init__`, `start`, `stop`, `dispatch` methods (all async). FastMCP replaces these — skeleton phase must decide: keep the shape, or rewrite tests to target FastMCP's surface. ADR §5.2 line 590 (-180 +60 LOC for `server.py`) implies rewrite. |
| `tests/ai/test_mcp_tools_workflow.py` | Per-tool behavior tests. Survive migration only if tool function signatures + return shapes preserved (FastMCP wraps Python functions). |
| `tests/ai/test_mcp_tools_authoring.py` | Same. Note `scaffold_block` test will need extension for new `input_ports`/`output_ports` + `warnings` per ADR §3.2a. |
| `tests/ai/test_mcp_tools_inspection.py` | Same. |
| `tests/ai/test_mcp_tools_qa.py` | Same. |
| `tests/ai/test_mcp_tools_disk_integration.py` | Cross-tool disk-level integration. Should survive without change if FastMCP preserves wire shape. |
| `tests/ai/test_finish_ai_block.py` | Behavior test for `finish_ai_block`. |
| `tests/ai/test_finish_ai_block_skeleton.py` | Asserts `TOOL_REGISTRY` length = 26 and the entry is registered — adapt to FastMCP `list_tools()` once `_registry.py` is deleted. |

### 1.6 TypeRegistry surface for §3.2a

- `TypeRegistry` class: `src/scistudio/core/types/registry.py:69`.
- Public methods touched by `list_types`: `all_types()` (referenced at `tools_workflow.py:245`).
- `scan_all(include_monorepo: bool = False)` (line 426), `scan_builtins()` (line 288).
- **MCP `list_types` tool already exists** (`tools_workflow.py:242`); ADR §3.2a's "Otherwise pick from list_types()" warning text references an existing tool — no new tool needed. The §3.2a soft-validation logic just needs to call `ctx.type_registry.has(type_name)` (verify the method exists; if not, `name in ctx.type_registry.all_types()`).

### 1.7 Frontend touchpoints

`Grep mcp__scistudio|tools/list|MCPServer` over `frontend/src/` returns **zero matches**. Frontend has no MCP-tool-name references and no TypeScript types referencing the catalog. FastMCP migration is backend-only from the frontend's perspective.

### 1.8 ADR-040 §5.1 / §5.2 mapping for FastMCP track

| ADR-040 §5.2 row | Current file | Status |
|---|---|---|
| `pyproject.toml` (+5 LOC, fastmcp dep + package-data) | `pyproject.toml` lines 17- (`dependencies`) | No `fastmcp` entry today; needs add |
| `server.py` (-180 +60) | `src/scistudio/ai/agent/mcp/server.py` (251 LOC) | Hand-rolled, replace with FastMCP wrapper |
| `_registry.py` (-279) | `src/scistudio/ai/agent/mcp/_registry.py` (279 LOC) | Delete after migration |
| `tools_workflow.py` (±150) | 752 LOC | Convert all 10 tools to `@mcp.tool()` + Pydantic returns |
| `tools_authoring.py` (±80) | 242 LOC | Same for 5 tools; add ADR §3.2a port-spec args |
| `tools_inspection.py` (±120) | 566 LOC | Same for 7 tools |
| `tools_qa.py` (±60) | 233 LOC | Same for 4 tools |
| `system_prompt.py` (±100) | 166 LOC | `_load_skill_md` → `importlib.resources`; add `_render_project_context`; `_render_tool_catalog` reads FastMCP |
| `runtime.py` (±40) | 203 LOC | Adapt standalone-bridge to FastMCP server |

### 1.9 Out-of-scope for FastMCP track

Do **not** touch:
- `src/scistudio/core/**` — frozen contracts (per CLAUDE.md §7.3, agent-manager skill).
- `src/scistudio/blocks/base/**` — foundational block classes.
- `src/scistudio/engine/runners/**` — scheduler.
- `frontend/src/**` — out of scope (no MCP touchpoints).
- `src/scistudio/api/runtime.py::create_project` / `::open_project` / `::init` — owned by Provisioning track.
- `src/scistudio/cli/install.py` — owned by Install-parity track.
- `skills/scistudio/SKILL.md` body content — owned by Skills track (Phase 2b). FastMCP can SHRINK the file via the relocation in §3.4, but the body content stays for Phase 2b.
- ADRs, specs, CHANGELOG (only the gate workflow's own CHANGELOG entry).

---

## 2. Track Provisioning

### 2.1 Owned files (writable by S40c / I40c)

| File | Action | Reason |
|---|---|---|
| `src/scistudio/agent_provisioning/` (new module) | Create | ADR §3.8; new orchestration module |
| `src/scistudio/agent_provisioning/__init__.py` | Create | |
| `src/scistudio/agent_provisioning/_orchestrate.py` | Create | `install_project_agent_assets` entry point |
| `src/scistudio/agent_provisioning/claude_agents_md.py` | Create | Writes `<project>/CLAUDE.md` + `<project>/AGENTS.md` |
| `src/scistudio/agent_provisioning/hooks.py` | Create | Writes `.claude/settings.json` + hook scripts |
| `src/scistudio/agent_provisioning/skills.py` | Create | Writes 6 skill files to both providers' trees |
| `src/scistudio/agent_provisioning/codex_config.py` | Create | Writes `<project>/.codex/config.toml` |
| `src/scistudio/agent_provisioning/templates/*` | Create | Source-of-truth template files |
| `src/scistudio/api/runtime.py` | Modify (narrow) | Wire `install_project_agent_assets` into `create_project` and `open_project` |
| `src/scistudio/cli/main.py::init` | Modify (narrow) | Same wiring for CLI path |
| `src/scistudio/ai/agent/terminal.py::spawn_codex` | Modify (docstring only) | Drop stale "intentional asymmetry" comment per ADR §5.2 |
| `tests/agent_provisioning/` (new directory) | Create | Per ADR §5.1 |

### 2.2 Current `create_project` shape (provisioning wiring point)

File: `src/scistudio/api/runtime.py`. Method: `ApiRuntime.create_project(self, name, description="", parent_path=None) -> KnownProject` at line **506**.

Key landmarks for ADR §3.8 wiring:
- Line **507-510**: `_safe_parent_dir(parent_path)` + project_path resolution + existence check.
- Line **517-529**: Directory scaffold (10 subdirs: `workflows`, `data/raw`, `data/zarr`, `data/parquet`, `data/artifacts`, `data/exchange`, `blocks`, `types`, `.scistudio`, `logs`). ADR §3.8 adds new dirs (`.claude/hooks/`, `.claude/skills/scistudio/<6>`, `.agents/skills/scistudio/<6>`, `.codex/`).
- Line **531-538**: `project_id` + `KnownProject` construction.
- Line **539-551**: `project.yaml` write.
- Line **561-567**: `workflows/main.yaml` scaffold (issue #879). Best-effort.
- Line **568-569**: `self.known_projects[project.id] = project; self._save_known_projects()`.
- Lines **570-610**: **ADR-039 git auto-init** (live, not skeleton). `GitEngine(project_path)` + `engine.is_repository()` guard + `engine.init_repository()` + degraded-mode logging.
- Line **611**: `self.open_project(project.id)` — triggers `open_project` flow.

**ADR §3.8 wiring point**: `install_project_agent_assets(project_path, force=False)` is called AFTER git auto-init (line 610) and BEFORE `self.open_project()` (line 611). Ordering matters: per ADR §3.8, provisioning files (CLAUDE.md, AGENTS.md) should be part of the initial git commit. ADR-039 already created the initial commit at line 603 (`engine.init_repository`). So **insertion order**: line 610 → `install_project_agent_assets(...)` → optional `engine.commit(...)` for provisioned files → `self.open_project(...)`. **Open question for I40c**: should provisioned files be committed inside `init_repository` (requires extending the helper) or post-init with a follow-up commit? ADR §3.8 does not specify. Recommend follow-up commit; flag in I40c change plan.

### 2.3 Current `open_project` shape (idempotent top-up wiring point)

File: `src/scistudio/api/runtime.py`. Method: `ApiRuntime.open_project(self, project_id_or_path: str) -> KnownProject` at line **655**.

Key landmarks:
- Lines **656-665**: Resolve project (by id or by path); update `last_opened`; persist `known_projects`.
- Line **666**: `self.active_project = candidate`.
- Lines **667-669**: `self.data_catalog = {}; self.refresh_block_registry(); self._init_metadata_store(...)`.
- Line **675**: `self._init_lineage_store(...)` (ADR-038).
- Lines **676-701**: **ADR-039 re-init hook** — opt-out via `<project>/.scistudio/no_git` marker; otherwise `GitEngine(...).init_repository(...)` if `.git/` missing.
- Line **705**: `self._publish_mcp_port(...)`.

**ADR §3.8 idempotent top-up**: insert `install_project_agent_assets(project_path, force=False)` after line 701 (after the git re-init block, before MCP port publish). `force=False` is the contract — existing user-edited files NOT overwritten. The `<project>/.claude/.scistudio-provision-version` marker file (ADR §3.8) governs version-driven upgrades; OQ-1 in ADR §8 is deferred to Phase 3 design.

### 2.4 Current `cli/main.py::init` shape (CLI wiring point)

File: `src/scistudio/cli/main.py`. Function: `init(name: str = typer.Argument("my_project", ...)) -> None` at line **93** (Typer command).

Key landmarks:
- Lines **96-99**: Path check; abort if exists.
- Lines **105-118**: Same 10-subdir scaffold as `ApiRuntime.create_project`.
- Lines **120-127**: `project.yaml` write.
- Lines **129-174**: **ADR-039 git auto-init** (live). Same `GitEngine` + degraded-mode pattern. Differences from API path: surfaces success/failure via `typer.echo` instead of `logger`.
- Line **176**: `typer.echo(f"Created project workspace: {name}/")`.

**ADR §3.8 wiring point**: insert `install_project_agent_assets(project_path, force=False)` after line 174 (git init complete) and before line 176 (final success message). I40c can choose to surface provisioning success via additional `typer.echo` calls for symmetry; ADR §3.8 says failures are non-fatal — log at WARNING. Match the existing degraded-mode pattern at lines 163-174.

### 2.5 `spawn_claude` / `spawn_codex` argv shape (verbatim)

File: `src/scistudio/ai/agent/terminal.py`. Verified at commit `4b6c54d`.

**`spawn_claude`** (line 452-510). Argv block (lines 492-501):

```python
argv = [
    "claude",
    "--append-system-prompt",
    f"@{prompt_path}",
    "--mcp-config",
    str(mcp_config),
]
if dangerous:
    argv.append("--dangerously-skip-permissions")
```

**`spawn_codex`** (line 513-559). Argv block (lines 547-550):

```python
argv = ["codex"]
if dangerous:
    argv.append("--dangerously-bypass-approvals-and-sandbox")
```

**Confirmation**: ADR-040 §2.7's "no `--mcp-config`, no `--append-system-prompt`" claim is verified. The stale "intentional asymmetry with claude" comment is at **lines 529-536** (inside the docstring); ADR §3.8 / §5.2 calls for dropping it.

**File discovery for Claude Code**: spawned with `cwd=project_dir` (line 504). Claude Code's hooks/skills/CLAUDE.md/AGENTS.md discovery is `cwd`-relative — so hooks at `<project>/.claude/settings.json` fire automatically once provisioned.

**File discovery for Codex**: same `cwd=project_dir` (line 553). Codex walks from project root to cwd loading `.codex/config.toml`, `AGENTS.md`, `.agents/skills/` (per ADR §2.7). No argv changes needed once provisioning lands.

**`extra_env` parameter** (both functions): threaded through `PtyProcess`. Used by ADR-035 §3.5 path (a) for `SCISTUDIO_AI_BLOCK_RUN_DIR`. ADR-040 hooks do NOT need extra env — `$CLAUDE_PROJECT_DIR` is supplied by Claude Code itself.

### 2.6 GUI spawn path (Chrome → API → spawn)

File: `src/scistudio/api/routes/ai_pty.py`. Function: `_spawn(provider, project_dir, dangerous, extra_env)` at line **346**.

Routing:
- `provider == "claude-code"` → `spawn_claude(...)` (line 365).
- `provider == "codex"` → `spawn_codex(...)` (line 367).
- Other → raises `ValueError`.

WS route at line **62**: user-launched path. The frontend Terminal tab connects to `WS /api/ai/pty/{tab_id}`; the route validates query params, calls `_spawn`, and pumps bytes both ways. This route is **FROZEN per ADR-034** (do not modify).

Engine-initiated path: ADR-035 §3.10 skeleton at lines 372+ for AI Block tab spawning. Same `_spawn` helper.

### 2.7 `<session_id>` hook stdin payload

`Grep session_id|sessionId` over `src/scistudio/ai/agent/` returns **zero matches**. No existing session_id handling in SciStudio code today.

**Source of `session_id`** (ADR §3.6): Claude Code's hook system passes a JSON object on stdin to each hook command. The `session_id` is one field in that payload. Verified independently against Claude Code's hooks documentation cited in ADR-040 §10 sources. Hook scripts read stdin via `json.load(sys.stdin)` — see `enforce_list_blocks_before_block_write.py` and `mark_list_blocks_called.py` in ADR §3.6.

**Marker path**: `<project>/.scistudio/.session-state/<session_id>/list_blocks_called` (ADR §3.6 line 432). `.scistudio/` is gitignored already via `src/scistudio/core/versioning/gitignore_template.py:35` — `.session-state/` under it is therefore covered. **No gitignore change required.**

### 2.8 ADR-038 lineage.db touch-points

`lineage.db` lives at `<project>/.scistudio/lineage.db` per ADR-038 §3.5. Wired via `ApiRuntime._init_lineage_store(...)` (called at `runtime.py:675`).

**ADR-040 §7.3 invariant**: "Hooks do not write lineage." Verified — none of the 6 hook scripts in ADR §3.6 reach for lineage. The Provisioning track must NOT introduce a lineage.db dependency in the hook scripts. The marker file at `.session-state/<session_id>/list_blocks_called` is a plain `Path.touch()`, no DB.

### 2.9 Existing project directory scaffold (for diff vs ADR §3.8)

Created by both `create_project` (`api/runtime.py:517-529`) and `cli/main.py::init` (`cli/main.py:105-118`):

```
<project>/
├── workflows/
├── data/{raw,zarr,parquet,artifacts,exchange}/
├── blocks/
├── types/
├── .scistudio/        # gitignored
├── logs/
├── project.yaml
└── workflows/main.yaml    # ADR §3.8: present; #879
```

After ADR-039 git auto-init, also has `.git/`, `.gitignore`, README (per `init_repository`).

**ADR-040 §3.8 adds**:
- `<project>/CLAUDE.md` (top-level, ~50 lines per §3.5)
- `<project>/AGENTS.md` (identical content)
- `<project>/.claude/settings.json` (hook config per §3.6)
- `<project>/.claude/hooks/*.py` (6 hook scripts per §3.6)
- `<project>/.claude/skills/scistudio/<6 dirs>/SKILL.md`
- `<project>/.agents/skills/scistudio/<6 dirs>/SKILL.md`
- `<project>/.codex/config.toml`
- `<project>/.claude/.scistudio-provision-version` (version marker)
- `<project>/.scistudio/.session-state/` (gitignored runtime marker dir)

**None of these exist in the current scaffold**. ADR §2.6 confirmed `grep -r PreToolUse src/` finds zero hook scripts.

### 2.10 Test files touching this track

| Test file | Relevant content |
|---|---|
| `tests/api/test_projects.py` | `create_project` HTTP integration. Adapt for new directories/files present after provisioning. |
| `tests/api/test_open_project_degraded_modes.py` | ADR-039 + ADR-038 degraded-mode integration. Phase 3 must add a `provisioning_failure` degraded mode case. |
| `tests/cli/test_init_git_init.py` (44 LOC) | `scistudio init` git auto-init test. Adapt for new provisioned files. |
| `tests/api/test_ai_pty.py` | PTY spawn integration. Spawn-time argv/cwd unaffected by provisioning but the spawned shell will now see hooks fire. |
| `tests/api/test_ai_pty_engine_spawn.py` | Engine-initiated AI Block spawn — same. |
| `tests/agent_provisioning/test_*.py` (new) | Per ADR §5.1. 6 test files. |

### 2.11 Out-of-scope for Provisioning track

Do **not** touch:
- `src/scistudio/ai/agent/mcp/**` — owned by FastMCP track.
- `src/scistudio/cli/install.py` — owned by Install-parity track.
- `src/scistudio/core/versioning/**` — frozen ADR-039 surface; only modify if a NEW `.gitignore` line is needed (it isn't — `.scistudio/` already covers `.session-state/`).
- `src/scistudio/blocks/**`, `src/scistudio/engine/**`, `src/scistudio/core/**` — frozen contracts.
- `frontend/src/**` — out of scope.
- `skills/scistudio/SKILL.md` body content — Skills track.
- ADR-040 itself, ADR-038, ADR-039, CHANGELOG.

---

## 3. Track Install-parity

### 3.1 Owned files (writable by S40d / I40d)

| File | Action | Reason |
|---|---|---|
| `src/scistudio/cli/install.py` | Modify | ADR §3.9 cross-install + Codex project-scope branch + remove "force user-scope" fallback |
| `tests/cli/test_install.py` | Modify | Add cross-install + project-scope codex test cases |

### 3.2 `install.py` current shape (verbatim line numbers)

File: `src/scistudio/cli/install.py` (574 LOC).

**Constants** (line 41):
```python
MCP_SERVER_NAME = "scistudio"
```

**`InstallResult` dataclass** (line 44-61): `(target, scope, path, action, detail)`.

**Helpers**:
- `_scistudio_command_for_env() -> tuple[str, list[str]]` (line 69-88): returns `(sys.executable, ["-m", "scistudio"])`. Hotfix 2026-05-14 changed from `shutil.which("scistudio")` to `sys.executable -m scistudio` to avoid stale-PATH bug. **Preserve**.
- `_mcp_entry_payload(project_dir: Path | None) -> dict` (line 91-106): builds `{command, args, env}` entry for Claude/Codex config files.
- `_atomic_write_json(path, payload)` (line 109-114): write-then-rename.

**Claude target**:
- `_claude_user_config_path()` (122) → `Path.home() / ".claude.json"`.
- `_claude_project_config_path(cwd)` (126) → `cwd / ".mcp.json"`.
- `_install_claude(scope, cwd)` (130-167): mutates `mcpServers.scistudio` in either user or project config; returns `InstallResult`.
- `_remove_claude(scope, cwd)` (170-200): symmetric removal.

**Codex target**:
- `_codex_config_path()` (208) → `Path.home() / ".codex" / "config.toml"`. **HARD-CODED to user scope today** — ADR §3.9 needs a project-scope variant: `cwd / ".codex" / "config.toml"`.
- `_format_toml_string(s)` (212): TOML basic-string escaper.
- `_render_codex_block(project_dir: Path | None) -> str` (222-240): renders `[mcp_servers.scistudio]` block. Same shape ADR §3.7 reuses for `<project>/.codex/config.toml`.
  ```python
  command, prefix_args = _scistudio_command_for_env()
  args_literal = json.dumps([*prefix_args, "mcp-bridge"])
  lines = [
      f"[mcp_servers.{MCP_SERVER_NAME}]",
      f"command = {_format_toml_string(command)}",
      f"args = {args_literal}",
  ]
  if project_dir is not None:
      lines.append("")
      lines.append(f"[mcp_servers.{MCP_SERVER_NAME}.env]")
      lines.append(f"SCISTUDIO_PROJECT_DIR = {_format_toml_string(str(project_dir))}")
  return "\n".join(lines) + "\n"
  ```
- `_strip_codex_block(existing)` (249-284): removes `[mcp_servers.scistudio]` + nested `[.env]` from existing TOML text.
- `_install_codex(scope, cwd)` (287-331): writes the TOML block to `~/.codex/config.toml` regardless of scope. **Currently does not support project scope.**
- `_remove_codex(scope, cwd)` (334-351): symmetric.

**Skill target** (Claude only today):
- `_skill_dest(scope, cwd)` (359-364): returns `~/.claude/skills/scistudio` (user) or `<cwd>/.claude/skills/scistudio` (project). **No `.agents/skills/` path today.**
- `_find_skill_source()` (367-393): walks up from `__file__` to find `<repo>/skills/scistudio/SKILL.md`. **Fails for wheel install (#824)** — ADR §3.4 fixes via `importlib.resources`.
- `_install_skill(scope, cwd)` (396-416): `shutil.copytree(src, dest)`. **Single destination; ADR §3.9 needs second destination (`~/.agents/skills/scistudio`).**
- `_remove_skill(scope, cwd)` (419-424): `shutil.rmtree(dest)`. Single destination.

**Orchestration** (line 432):
```python
def perform_install(*, target, scope, skill, do_all, remove, cwd=None) -> list[InstallResult]:
```

**The "force user-scope for codex" fallback** (ADR §2.7 + §3.9):

Located at **lines 487-498**. Verbatim:

```python
elif tgt == "codex":
    # Codex has no project-scope config file; force user-scope
    # for codex even when the user picked --scope project for
    # claude. Surface that fact in the result's detail.
    results.append(_remove_codex("user", cwd) if remove else _install_codex("user", cwd))
    if scope == "project":
        results[-1] = InstallResult(
            target=results[-1].target,
            scope=results[-1].scope,
            path=results[-1].path,
            action=results[-1].action,
            detail=results[-1].detail + " (codex has no project-scope config file; wrote to user scope)",
        )
```

(ADR §3.9 cites "install.py:489-498" — current line range is 487-498. The 2-line drift is from intervening edits; the semantic block is what matters.)

**Per ADR §3.9**: this fallback must be REMOVED. Replace with a real project-scope branch that writes to `<cwd>/.codex/config.toml`. `_codex_config_path()` will need a `(scope, cwd) -> Path` signature OR `_install_codex` builds the path itself based on scope.

### 3.3 Typer wiring

- `_emit_results(results)` (line 510): prints `[target/scope] action: path` + detail.
- `_typer_command(target, scope, skill, do_all, remove)` (line 517-560): Typer entry point. Calls `perform_install` and emits results.
- `register(app)` (line 563): mounts as `scistudio install`.

### 3.4 Callsites of install.py internals

`Grep _install_skill|_install_codex|_render_codex_block|MCP_SERVER_NAME|_mcp_entry_payload|_scistudio_command_for_env` across repo:

| Callsite | What it imports |
|---|---|
| `src/scistudio/__main__.py` | (Phase 1014 fix) — imports `MCP_SERVER_NAME`, `_mcp_entry_payload`, `_scistudio_command_for_env` for the bridge entry-point. **Verify** these survive ADR §3.9 changes. |
| `src/scistudio/ai/agent/terminal.py:418` | `from scistudio.cli.install import MCP_SERVER_NAME, _mcp_entry_payload` — used by `_ensure_mcp_config` to write `<project>/.scistudio/mcp.json` for `--mcp-config`. **Must keep**. |
| `tests/cli/test_install.py` | Tests for all install paths. |
| `tests/cli/test_dunder_main.py` | Tests for `__main__.py` consumers. |
| `skills/scistudio/SKILL.md` | Documentation references. |

### 3.5 Skill source-path resolution (#824 wheel-install bug)

Current `_find_skill_source` (`install.py:367-393`) walks up from `Path(__file__).resolve().parents` looking for a `skills/scistudio/SKILL.md` sibling. The same pattern is in `system_prompt.py::_load_skill_md`.

**Failure mode for wheel installs**: `skills/` lives at repo root, NOT inside `src/scistudio/`. When pip installs the wheel, `skills/` does not land in `site-packages/`. The walk-up logic hits `site-packages/` (no `skills/` sibling), then walks further up to the venv root, then to `/`, then raises `FileNotFoundError`.

**ADR §3.4 fix**: relocate `skills/` → `src/scistudio/_skills/` and use `importlib.resources`:

```python
from importlib.resources import files
def _load_skill_md() -> str:
    return (files("scistudio") / "_skills" / "scistudio" / "SKILL.md").read_text("utf-8")
```

Both `system_prompt.py::_load_skill_md` AND `install.py::_find_skill_source` switch. Add `[tool.setuptools.package-data] scistudio = ["_skills/scistudio/**/*.md"]` to `pyproject.toml`.

**Note**: the relocation is owned by Skills track (Phase 2 in ADR §6); Install-parity track only updates `_find_skill_source` to call the new location, which is a 1-line change.

### 3.6 `~/.agents/skills/` references

`Grep .agents/skills|~/.agents` returns **zero hits in src/**. Only matches are in `docs/planning/adr-040-checklist.md`, `docs/adr/ADR-040.md`, `CHANGELOG.md`. Confirms ADR-040 §2.7 — SciStudio installs nothing at `~/.agents/skills/` today. ADR §3.9 adds this as a parallel destination in `_install_skill`/`_remove_skill`.

### 3.7 Test files touching this track

`tests/cli/test_install.py` (225 LOC). Existing test coverage:
- `test_install_claude_idempotent` — line 48.
- Claude project-scope env var pin (line 92-98).
- `test_install_codex_idempotent` — line 106.
- TOML format assertions (line 113).

**Phase 4 must add**:
- Cross-install across `.claude/skills/` + `.agents/skills/` for all 6 skill files.
- `_remove_skill` symmetry across both paths.
- Codex project-scope branch: `scistudio install --target codex --scope project` writes `<cwd>/.codex/config.toml`.
- Removed fallback: assertion that "wrote to user scope" detail no longer surfaces at project scope.

### 3.8 ADR-040 §3.7 vs §3.9 — note for I40d

ADR §3.7 (Codex MCP at `<project>/.codex/config.toml`) and ADR §3.9 (cross-install) overlap: both write to `<project>/.codex/config.toml`. The split:

- **§3.7** is the **auto-provisioning** path (Provisioning track owns the call site at `install_project_agent_assets`).
- **§3.9** is the **CLI power-user** path (Install-parity track owns the `scistudio install --target codex --scope project` branch).

They MUST produce identical TOML output. Both reuse `_render_codex_block` (Install-parity track owns). Provisioning track depends on Install-parity track exporting `_render_codex_block` cleanly (already public in module scope). No circular dep — Provisioning imports from `install`, not the reverse.

### 3.9 Out-of-scope for Install-parity track

Do **not** touch:
- `src/scistudio/ai/agent/mcp/**` — FastMCP track.
- `src/scistudio/api/runtime.py`, `src/scistudio/cli/main.py::init`, `src/scistudio/agent_provisioning/**` — Provisioning track.
- `src/scistudio/__main__.py` — only modify if a public symbol it imports changes name; otherwise leave alone.
- `src/scistudio/ai/agent/terminal.py` — Provisioning track owns the docstring edit at line 529-536; Install-parity track must keep `_mcp_entry_payload` import surface stable.
- `src/scistudio/core/**`, `src/scistudio/blocks/**`, `src/scistudio/engine/**` — frozen.
- `frontend/src/**` — out of scope.
- ADRs/specs/CHANGELOG (only gate-workflow CHANGELOG entry).

---

## 4. Track Skills (light pass — Phase 2b owns deep skill-design)

### 4.1 Owned files (writable by Skills track in Phase 2b)

| File | Action | Reason |
|---|---|---|
| `skills/scistudio/SKILL.md` (current, 372 LOC) | Relocate + rewrite | ADR §3.4 — move to `src/scistudio/_skills/scistudio/SKILL.md`, shrink to ~50 LOC base |
| `src/scistudio/_skills/scistudio/SKILL.md` (new) | Create | Thin base index per ADR §3.4 |
| `src/scistudio/_skills/scistudio/scistudio-build-workflow/SKILL.md` (new) | Create | Task skill |
| `src/scistudio/_skills/scistudio/scistudio-write-block/SKILL.md` (new) | Create | Task skill (embeds #875 block-reuse rule + §3.4 port-type rule) |
| `src/scistudio/_skills/scistudio/scistudio-debug-run/SKILL.md` (new) | Create | Task skill |
| `src/scistudio/_skills/scistudio/scistudio-inspect-data/SKILL.md` (new) | Create | Task skill |
| `src/scistudio/_skills/scistudio/scistudio-project-qa/SKILL.md` (new) | Create | Task skill |
| `pyproject.toml` | Modify (narrow) | Add `[tool.setuptools.package-data]` entry for `_skills/scistudio/**/*.md` |

### 4.2 Current `skills/scistudio/SKILL.md` structure

File: `skills/scistudio/SKILL.md` at **repo root** (372 LOC).

**Frontmatter** (lines 1-7): YAML with `name: scistudio` + description.

**Body structure**:
- `# SciStudio` (line 9): identity heading.
- `## Identity & scope` (line ~13)
- `## Environment assumptions (read first)` (line ~21): the 4 hard rules — backend running, MCP attached, prefer MCP over CLI, cwd = project root.
- `<!-- tool_catalog:begin -->` at **line 156**.
- `<!-- tool_catalog:end -->` at **line 220**.
- `## See also` at end.

**Identity continuity needs for Phase 2b**:
- Preserve `name: scistudio` frontmatter (compose_system_prompt + install.py both depend on it).
- Preserve `<!-- tool_catalog:begin/end -->` markers (system_prompt.py:33-34 splices into them).
- Add a new `<!-- project_context:begin/end -->` marker pair (ADR §3.3) — owned by FastMCP track for the renderer; Skills track must include the marker in the base SKILL.md so the splice has a target.

### 4.3 Skill-source resolution today

Both `system_prompt.py::_load_skill_md` and `install.py::_find_skill_source` walk up from `__file__` looking for `skills/scistudio/SKILL.md` at repo root.

After ADR §3.4 relocation, both switch to `importlib.resources.files("scistudio") / "_skills" / "scistudio" / "SKILL.md"`. Phase 2 (per ADR §6) owns the relocation; Phase 1 (FastMCP) updates `system_prompt.py`; Phase 4 (Install-parity) updates `install.py`.

### 4.4 Examples subdirectory

`skills/scistudio/examples/` exists. Phase 2b should decide whether to keep this in `_skills/scistudio/examples/` or move per-task examples under each task skill's directory. Out of scope here — flag for Phase 2b skill-design investigation.

### 4.5 Out-of-scope for Skills track

Do **not** touch:
- Anything outside `skills/scistudio/` (legacy) and `src/scistudio/_skills/` (post-relocation).
- `pyproject.toml` outside the single `[tool.setuptools.package-data]` addition (do not bump versions, add new tools, etc.).
- Any Python source — Skills track is content-only (markdown).
- `system_prompt.py`, `install.py` — those edits are owned by FastMCP / Install-parity tracks.

---

## 5. Track Hook Scripts (sub-track of Provisioning — §3.6)

The 6 hook scripts in ADR §3.6 are **template files** owned by Provisioning track. Listed separately for clarity.

| Template | Hook type | Matcher | Purpose |
|---|---|---|---|
| `hook_deny_scistudio_cli.py` | PreToolUse | `Bash` | Block `scistudio` CLI calls (closes #875 CLI-vs-MCP half) |
| `hook_protect_workflow_yaml.py` | PreToolUse | `Edit\|Write` | Block direct edits to `workflows/*.yaml` |
| `hook_enforce_list_blocks_before_block_write.py` | PreToolUse | `Edit\|Write\|Bash\|mcp__scistudio__scaffold_block` | Closes #875 block-reuse half via session-keyed marker |
| `hook_remind_poll_status.py` | PostToolUse | `mcp__scistudio__run_workflow` | Inject reminder to poll `get_run_status` |
| `hook_mark_list_blocks_called.py` | PostToolUse | `mcp__scistudio__list_blocks` | Write session marker for §3.6 enforcement |
| `hook_enforce_concrete_port_types.py` | PostToolUse | `Edit\|Write\|mcp__scistudio__scaffold_block` | AST-scan blocks for `DataObject`-typed ports (#§3.2a L5) |

All Python; all read stdin JSON payload from Claude Code; exit code 2 = block; exit code 0 = pass.

**Note**: ADR-040 §3.8 inventory mentions 3 hook scripts (line 475: "3 hook scripts"). The detailed §3.6 spec actually defines 6. Flagged in §8 Suspicious findings as ADR-internal inconsistency. The 6-count is authoritative (matches §3.6 body); §3.8 line 475 is shorthand.

---

## 6. Cross-cutting

### 6.1 `tests/conftest.py`

`tests/conftest.py` (60 LOC) patches `BlockRegistry._scan_builtins` at collection time to register two test-only blocks (`NoopBlock`, `NoopIOBlock`) + a `tmp_project_dir` fixture (uses `tmp_path`). All ADR-040 impl tests can rely on `tmp_project_dir` as the base for tests that need a project skeleton.

### 6.2 `tests/fixtures/`

| Fixture | Purpose |
|---|---|
| `noop_block.py` | `NoopBlock` for `process_block` alias |
| `noop_io_block.py` | `NoopIOBlock` for `io_block` alias |
| `test_images.py` | Image-data fixtures |
| `test_noop_block.py` | Smoke tests for the noop blocks |

No ADR-040-specific shared fixtures needed beyond `tmp_project_dir`; each track may add fixtures in `tests/<track>/conftest.py` if reusable.

### 6.3 `import-linter` contracts (`pyproject.toml`)

Three forbidden contracts:

1. `scistudio.core` may not import `scistudio.blocks`, `scistudio.engine`, `scistudio.api`, `scistudio.ai`, `scistudio.workflow`. Exception: `scistudio.core.lineage.recorder -> scistudio.engine.events` (TYPE_CHECKING only).
2. `scistudio.blocks` may not import `scistudio.engine`, `scistudio.api`, `scistudio.ai`. Exception: `scistudio.blocks.ai.ai_block -> scistudio.engine.pty_control`.
3. `scistudio.engine` may not import `scistudio.api`, `scistudio.ai`.

**Impact on ADR-040**:
- `src/scistudio/agent_provisioning/` is a new top-level subpackage. It does not appear in any contract — no constraint. Recommend Phase 3 (Provisioning) add a contract: `scistudio.agent_provisioning` may not import `scistudio.api` (provisioning is filesystem-only) — flag for ADR-040 audit but not a blocking requirement.
- `scistudio.ai.agent.mcp` may freely import `scistudio.ai.agent.system_prompt` (no contract). FastMCP migration introduces no new dep edges.
- `src/scistudio/_skills/` is data, not a Python package — no import-linter implications.

### 6.4 mypy strict-mode boundaries

`pyproject.toml [tool.mypy]`:
- `python_version = "3.11"` — pinned (zarr 3.2+ uses PEP 695 syntax requires 3.12+; that's the only known constraint).
- `disallow_untyped_defs = true` — strict typing enforced for all `scistudio.*` modules.
- `ignore_missing_imports = true` — third-party stubs may be missing.
- Overrides for `zarr` (skip imports).

**Impact on ADR-040**:
- New module `src/scistudio/agent_provisioning/` falls under the same `disallow_untyped_defs = true` regime. Skeleton agents must add full type annotations.
- `fastmcp` is a new dependency (Phase 1). Confirm `fastmcp` ships type stubs; if not, add to mypy ignore-missing-imports override list.

### 6.5 CI parity command

`.github/workflows/ci.yml` line ~94 (PR #1010 baseline):
```
timeout 600 pytest -n auto --timeout=60 --timeout-method=thread
```

Post-PR #1010, `--timeout=60` is in `pyproject.toml [tool.pytest.ini_options]` so plain `pytest --timeout=60 -n auto` is equivalent. All agents MUST use `--timeout=60` per checklist §0.3.

### 6.6 Coverage gate

`pyproject.toml`: `--cov-fail-under=70` (temporarily lowered post-PR #808 rollback). New code in `src/scistudio/agent_provisioning/`, the FastMCP-rewritten `mcp/` files, and `install.py` extensions all contribute to the coverage gate. Skeleton phase tests typically `@pytest.mark.skip` so coverage of skeleton stubs is zero — acceptable (skipped tests don't lower coverage). Impl phase must restore coverage.

### 6.7 Per-track out-of-scope file lists (consolidated)

| Track | Must NOT touch |
|---|---|
| FastMCP | `core/**`, `blocks/base/**`, `engine/runners/**`, `frontend/**`, `api/runtime.py::create_project`, `api/runtime.py::open_project`, `cli/install.py`, `skills/scistudio/SKILL.md` body, ADRs/specs/CHANGELOG. |
| Provisioning | `ai/agent/mcp/**`, `cli/install.py`, `core/versioning/**` (read-only ref), `blocks/**`, `engine/**`, `core/**`, `frontend/**`, `skills/scistudio/SKILL.md` body, ADRs/specs/CHANGELOG. |
| Install-parity | `ai/agent/mcp/**`, `api/runtime.py`, `cli/main.py::init`, `agent_provisioning/**`, `__main__.py` (unless symbol-renaming forces a follow-up), `ai/agent/terminal.py` (only Provisioning may touch docstring), `core/**`, `blocks/**`, `engine/**`, `frontend/**`, ADRs/specs/CHANGELOG. |
| Skills | Anything outside `skills/scistudio/` and `src/scistudio/_skills/`; Python source; `system_prompt.py`; `install.py`. |
| Hook scripts | Same as Provisioning (sub-track). |

### 6.8 Tracking-branch + PR target convention (from checklist §0.5)

All agent feature branches target the appropriate tracking branch (NOT main):
- FastMCP track → `track/adr-040/fastmcp` (seeded `dbfc257`, umbrella PR #1017).
- Provisioning track → `track/adr-040/provisioning` (seeded `7f0ed35`, umbrella PR #1018).
- Install-parity track → `track/adr-040/install-parity` (seeded `a4f600e`, umbrella PR #1019).
- Skills track → `track/adr-040/skills` (created Phase 2b).

This manifest's own PR is a docs PR and targets `main` directly (per dispatch prompt §6 step 7).

---

## 7. ADR-040 §5.1 vs current-tree discrepancy table

| ADR-040 §5.1 / §5.2 row | Current-tree reality | Action by impl agents |
|---|---|---|
| §5.1 "new file: `src/scistudio/ai/agent/mcp/_context.py`" — NOT in inventory | **EXISTS today** (203 LOC) | No action: this is a current-tree file ADR didn't enumerate. FastMCP migration keeps it intact. |
| §5.1 "new file: `src/scistudio/ai/agent/mcp/__init__.py`" — NOT in inventory | **EXISTS today** (38 LOC) | Minor edit only — drop the "25 tools" stale phrasing. |
| §5.2 row "`install.py:489-498`" force-user-scope fallback | Actual line range: **487-498** at commit `4b6c54d` | Line numbers drift between ADR drafting (2026-05-15) and now. Use **the verbatim block** as the search anchor — quoted in §3.2 above. |
| ADR-039 git auto-init "skeleton" | **PRODUCTION LIVE** at `api/runtime.py:598-610` + `:686-701` + `cli/main.py:155-174` | Provisioning track inserts AFTER git init; verify ordering doesn't break ADR-039's initial-commit semantics. |
| ADR §3.8 "3 hook scripts" (line 475) | ADR §3.6 actually defines **6 hook scripts** | Authoritative count: 6 (matches §3.6 detail). Flag in §8. |
| ADR §1 / many "26 tools" | Live registry: **26 ToolEntry** entries (verified by `tests/ai/test_system_prompt.py:28`) | Authoritative: 26. Checklist Phase 0.5 note ("27") is the only stale doc — flag in §8. |
| `_registry.py:1` docstring "25 tools" | Live: 26 entries. | Doc string is stale — fold into FastMCP migration delete (the file goes away). Flag in §8. |
| `__init__.py` docstring "25 tool functions" (line ~14) | Live: 26 tools. | Same — file remains post-migration, must update or strip docstring during Phase 1 cleanup. Flag in §8. |
| `server.py:54`, `:188`, `:209` docstrings "25 tools" | Live: 26. | Same — `server.py` is REWRITTEN by FastMCP migration so stale strings disappear. |

---

## 8. Suspicious findings

### 8.1 Stale "25 tools" comments scattered through the codebase

The codebase was authored when there were 25 baseline tools; ADR-035 added a 26th (`finish_ai_block`). Multiple comments/docstrings still say "25 tools":

- `src/scistudio/ai/agent/mcp/_registry.py:1` — module docstring ("single source of truth for the 25 tools").
- `src/scistudio/ai/agent/mcp/_registry.py:267-268` — `all_names()` docstring ("25 baseline tools + finish_ai_block ... = 26 tools").
- `src/scistudio/ai/agent/mcp/__init__.py:14` — "T-ECA-202..205 (implementation) — fills in the 25 tool functions".
- `src/scistudio/ai/agent/mcp/__init__.py:19` — "The 25 tools are split across four modules".
- `src/scistudio/ai/agent/mcp/__init__.py:26` — `tools_inspection` docstring claims **"7 tools"** which IS correct.
- `src/scistudio/ai/agent/mcp/__init__.py:23` — `tools_workflow` claims **"9 tools"** but actually has **10** (10 = 9 + `finish_ai_block`).
- `src/scistudio/ai/agent/mcp/server.py:7,54,188,209` — "25 tools" / "25 registered tools".
- `src/scistudio/ai/agent/mcp/runtime.py:12,16` — "25 MCP tools".
- `src/scistudio/cli/install.py:4` — comment header refers to "25-tool MCP surface".

These are all stale. Most disappear naturally as files are rewritten/deleted by FastMCP migration. None are code bugs (they're comments). **Do not fix in this manifest's PR** — let track agents update during their own PRs.

### 8.2 Checklist Phase 0.5 says "27 tools"

`docs/planning/adr-040-checklist.md:116`:

> Tool count is **27** (25 baseline + `finish_ai_block` from ADR-035 §3.5 skeleton, already in `_registry.py:246-252`), ADR says 26

The arithmetic is wrong: 25 + 1 = 26. The registry has 26 entries, the test asserts 26, ADR-040 says 26. Recommend manager corrects the checklist row to "26 (correctly enumerated in ADR §1 and tests)". Not a blocker for AC40 PR.

### 8.3 ADR §3.8 vs §3.6 hook-count drift

ADR-040 §3.8 line 475 lists provisioning outputs as including `<project>/.claude/hooks/*.py` and bullet-summarizes as **"3 hook scripts (§3.6)"** in surrounding prose. But §3.6 itself defines 3 PreToolUse + 3 PostToolUse = **6 hooks**. The §3.8 bullet is shorthand; the §3.6 list is authoritative. Provisioning track must implement all 6.

### 8.4 ADR §2.7 line number "install.py:489-498" is off by 2

ADR-040 §2.7 says the "force user-scope for codex" comment is at `install.py:489-498`. Current code has the block at lines **487-498** (verified at commit `4b6c54d`). Drift is from edits intervening between ADR drafting (2026-05-15) and now. Cited verbatim in §3.2 above for unambiguous reference. Not a blocker.

### 8.5 `_registry.py` docstring undercounts `tools_workflow` (9 vs 10)

`src/scistudio/ai/agent/mcp/__init__.py:23` says `tools_workflow` has "9 tools". Actually 10 (after ADR-035 added `finish_ai_block` to the workflow category). Stale comment; cleaned up naturally during FastMCP migration.

### 8.6 ADR §3.2a `scaffold_block` signature widening

ADR §3.2a's example signature is:
```python
@mcp.tool(name="scaffold_block")
async def scaffold_block(name, category, input_ports, output_ports, ...) -> ScaffoldBlockResult:
```

Current signature (`tools_authoring.py:158`) is:
```python
def scaffold_block(name: str, category: str) -> dict[str, Any]:
```

Adding `input_ports` and `output_ports` is a contract widening required for the `warnings` field to have inputs to scan. This is a **design implication, not a code bug**. Phase 1/2 agents (S40a/I40a) must:
1. Decide what the port-spec args look like (likely `dict[str, dict]` per port, with `type` + maybe `description`).
2. Update tests in `tests/ai/test_mcp_tools_authoring.py`.
3. Ensure the FastMCP-generated `inputSchema` correctly reflects the new args.

Flag for Phase 1 audit (A40-skel) — verify the skeleton signatures match what Phase 2 impl needs.

### 8.7 ADR-035 `finish_ai_block` category placement

`finish_ai_block` is registered under category `"workflow"` (`_registry.py:248`) with mutation `"write"`. The ADR-040 §3.4 skill split groups skills by MCP category, but `finish_ai_block` is a fundamentally different concern from `write_workflow`/`run_workflow` — it's an AI-Block-internal signaling tool. This is **not a bug** — the category is correctly "workflow" — but it's an awkward fit for the `scistudio-build-workflow` skill split. Phase 2b skill-design investigation should decide whether to call it out under a dedicated section in `scistudio-write-block` (it's most relevant to AI Block authoring) or in `scistudio-debug-run`.

### 8.8 (none — all flagged items above are docs/comment drift, no source bugs)

No source-level bugs surfaced during this investigation. The FastMCP migration is a contract-preserving rewrite; the Provisioning track is greenfield; the Install-parity track is well-scoped widening + a single removed fallback.

---

## 9. Phase 1 dispatch readiness checklist

Skeleton agents (S40a/b/c/d) can dispatch with this manifest + ADR-040 §3.x + their track's checklist row, no greps required, provided:

- [x] Tool count verified (26).
- [x] All public/private symbols of `mcp/` enumerated.
- [x] All callsites of `compose_system_prompt`, `MCPServer`, `TOOL_REGISTRY`, `_registry.lookup`, install.py internals listed.
- [x] All test files touching each track enumerated.
- [x] `create_project` / `open_project` / `init` wiring points pinpointed with line numbers.
- [x] `spawn_claude` / `spawn_codex` argv quoted verbatim.
- [x] Stale "force user-scope" fallback quoted verbatim with line range.
- [x] Existing project scaffold enumerated; delta vs ADR §3.8 explicit.
- [x] `~/.agents/skills/` absent in src today confirmed.
- [x] Frontend MCP touchpoints absent confirmed.
- [x] Import-linter contracts inventoried; `agent_provisioning/` impact noted.
- [x] mypy strict-mode boundaries inventoried.
- [x] Per-track out-of-scope file lists enumerated.
- [x] Suspicious findings (docs/comment drift only, no code bugs) flagged.

Ready for Phase 1 dispatch.
