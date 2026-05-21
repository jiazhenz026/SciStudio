# A2: ADR-040 MCP wiring + cross-doc consistency audit

**Date**: 2026-05-16
**Auditor**: A2 (Phase 3 parallel auditor, scope: FastMCP wiring + cross-doc consistency)
**Sibling auditors**: A1 (ADR completeness + bugs + edges), A3 (agent-POV prompt + skill review)
**Cascade**: ADR-040 production-environment agent reliability
**Tracking branch**: `track/adr-040` (consolidated)
**Umbrella issue**: #1011
**Sub-issue**: #1061
**Source HEAD audited**: `949476f` (`feat(#1057): I40b — skill content + CLAUDE.md/AGENTS.md template refinement`)

---

## Summary

**Verdict: pass-with-fixes.**

The FastMCP migration is functionally complete: all 26 expected MCP tools are
discoverable via `@mcp.tool()` decorators, Pydantic return models are in place
with `next_step` + `warnings` per ADR-040 §3.1 / §3.2 / §3.2a, the old
`_registry.py` is deleted, and the provisioning + install layers wire into the
right lifecycle events. The skill content shipped in I40b matches the
finalized MCP shape and the live `InputPort`/`OutputPort` dataclass surface
(per AC40-skill finding §1).

The blocking gaps are concentrated in the **cross-doc consistency sweep**:
ADR-034, ADR-035, and `docs/specs/embedded-coding-agent-spec.md` still teach
the pre-ADR-040 hand-rolled / 25-tool world. ADR-040 §5.3 explicitly called
for these doc updates and they have not landed. None of these block agent
runtime (the live code path is correct), but they leave the SciStudio
documentation graph internally contradictory — a reader following ADR-035
will be misled about the current `finish_ai_block` envelope shape.

The cascade is ship-ready after the cross-doc sweep + 3 minor source-code
doc-string corrections are applied. No functional FastMCP migration bug
was found in scope A2.

---

## A. FastMCP migration completeness

### A.1 Tool inventory: 26/26 present

`grep -n "@mcp.tool(" src/scistudio/ai/agent/mcp/` returns 26 decorated
functions across the four `tools_*.py` modules. Mapping vs the manifest
§1.2 baseline + ADR-035 `finish_ai_block` addition:

| Category | File | Count | Tools |
|---|---|---|---|
| (a) workflow | `tools_workflow.py` | 10 | `list_blocks`, `get_block_schema`, `list_types`, `get_workflow`, `validate_workflow`, `write_workflow`, `run_workflow`, `cancel_run`, `get_run_status`, `finish_ai_block` |
| (b) authoring | `tools_authoring.py` | 5 | `read_block_source`, `list_block_examples`, `scaffold_block`, `reload_blocks`, `run_block_tests` |
| (c) inspection | `tools_inspection.py` | 7 | `get_block_output`, `inspect_data`, `preview_data`, `get_lineage`, `get_block_config`, `update_block_config`, `get_block_logs` |
| (d) qa | `tools_qa.py` | 4 | `search_docs`, `get_doc`, `list_data`, `get_project_info` |

**26 total = baseline 25 + `finish_ai_block` (ADR-035 §3.5).** Matches what
`tests/ai/test_finish_ai_block_skeleton.py::test_registry_now_has_26_tools`
asserts. **PASS**.

### A.2 Pydantic return models: 19 explicit models found

`grep -n "^class \w+Result" src/scistudio/ai/agent/mcp/`:

- `tools_workflow.py` (7): `BlockSchemaResult`, `ListTypesResult`,
  `ValidateWorkflowResult`, `WriteWorkflowResult`, `RunWorkflowResult`,
  `CancelRunResult`, `GetRunStatusResult` (note: `list_blocks` returns
  `list[dict]`, `get_workflow` returns `dict` — both intentional —
  `finish_ai_block` uses a Union envelope per ADR-035)
- `tools_authoring.py` (4): `ReadBlockSourceResult`, `ScaffoldBlockResult`,
  `ReloadBlocksResult`, `RunBlockTestsResult` (note: `list_block_examples`
  returns `list[dict]`)
- `tools_inspection.py` (7): `GetBlockOutputResult`, `InspectDataResult`,
  `PreviewDataResult`, `GetLineageResult`, `GetBlockConfigResult`,
  `UpdateBlockConfigResult`, `GetBlockLogsResult`
- `tools_qa.py` (3): `GetDocResult`, `ListDataResult`, `GetProjectInfoResult`
  (note: `search_docs` returns `list[dict]`)

Pattern: tools returning enumerations stay on `list[dict]` / `dict`; tools
returning structured envelopes use Pydantic. Internally consistent. **PASS**.

### A.3 `next_step` on write-class tools

Found on every write-class result envelope per `grep -n "next_step:"`:

- `WriteWorkflowResult.next_step` (line 264, tools_workflow.py)
- `RunWorkflowResult.next_step` (line 275)
- `CancelRunResult.next_step` (line 286)
- `GetRunStatusResult.next_step` (line 320) — note: present on a read tool
  too, intentional per ADR-040 (steers to logs/lineage on FAILED state)
- `UpdateBlockConfigResult.next_step` (tools_inspection.py line 137)
- `ScaffoldBlockResult.next_step` (tools_authoring.py line 72)
- `ReloadBlocksResult.next_step` (line 88)
- `RunBlockTestsResult.next_step` (line 105)

`finish_ai_block` returns a Union of success/error envelopes per ADR-035
(verified by `test_finish_ai_block_handler_has_docstring`). **PASS.**

### A.4 `scaffold_block.warnings: list[str]`

`tools_authoring.py:64`:

```
warnings: list[str] = Field(
    default_factory=list, ...
)
```

Populated by:
- Generic-`DataObject` detection (ADR-040 §3.2a — line 374-ish via
  `_type_registry_has`)
- Unregistered type-name detection

Behaviour matches ADR §3.2a verbatim. **PASS.**

### A.5 `_registry.py` deletion + dead-import sweep

```
src/scistudio/ai/agent/mcp/  → no _registry.py
```

`grep -rn "from.*_registry\|TOOL_REGISTRY" src/`:

- `src/scistudio/ai/agent/mcp/__init__.py:33` — docstring reference: "there is
  no longer a separate `TOOL_REGISTRY` tuple" — **historical context, fine**
- `src/scistudio/ai/agent/system_prompt.py:16` — docstring reference:
  "replacing the deleted `_registry.TOOL_REGISTRY`" — **historical context,
  fine**
- All other `_registry` matches are unrelated (`block_registry`,
  `process_registry`, `type_registry`, `runner_registry`).

`grep -rn "_registry\|TOOL_REGISTRY" tests/` finds:

- `tests/ai/test_mcp_server_skeleton.py:198` — `from scistudio.ai.agent.mcp
  import _context, _registry` — **STALE: the import would raise
  ImportError** if executed. Mitigated by `pytestmark = pytest.mark.skip(...)`
  at line 35 (module-level skip with `TODO(#1012)` reason). The skipped body
  also references `_registry.lookup` which no longer exists.
  - **P3 — Cosmetic.** Tests are entirely skipped; CI never runs them; the
    stale reference is invisible. A follow-up housekeeping PR should delete
    the skeleton file outright or rewrite it against FastMCP. Tracked
    informally via I40a CHANGELOG note (`test_mcp_server_skeleton` is in
    the "module-level skip" group).
- `tests/conftest.py:25` — `from scistudio.blocks import registry as
  _registry_module` — unrelated (block registry alias).

**PASS** with one P3 housekeeping note.

### A.6 `inputSchema` auto-generation (no more `additionalProperties: true`)

`server.py::dispatch` `tools/list` branch (line 263) returns
`entry.parameters` directly from FastMCP's tool metadata. FastMCP generates
`inputSchema` from `typing.Annotated` + `Field(description=...)` on each tool
function's parameters. The legacy `additionalProperties: true` stub from
ADR-033 is gone. **PASS**.

---

## B. Cross-file wiring

### B.1 `system_prompt.py::_render_tool_catalog`

`system_prompt.py:136-201` correctly:

1. Force-imports `scistudio.ai.agent.mcp` so `@mcp.tool` decorators run before
   the FastMCP registry is queried.
2. Calls `await mcp.list_tools()` (with the **Codex P1-reconciled**
   in-running-loop fix: spawns a worker thread + `asyncio.run` so callers
   inside `ai_pty` websocket don't deadlock — see `[#1037]` CHANGELOG
   "F40-impl-1053").
3. Groups by `category:<name>` tags + `read`/`write` mutation tags.
4. Renders `- `<name>` [<mutation>] — <first-line description>`.

**PASS.**

### B.2 `system_prompt.py::_load_skill_md` — `importlib.resources` primary

`system_prompt.py:76-133`:

1. **Path 1**: `importlib.resources.files("scistudio") / "_skills" / "scistudio"
   / "SKILL.md"` — packaged path, wheel-safe per ADR-040 §3.4. Closes #824.
2. **Path 2 (fallback)**: legacy walk-up to repo-root `skills/scistudio/SKILL.md`,
   tagged `TODO(#1012): drop the legacy walk-up fallback once the Skills
   track merges to main`.

**PASS.** The TODO is legitimate (CLAUDE.md §7.6 compliant). After
`skills/scistudio/SKILL.md` was deleted at repo root by I40b commit `ced96fb`,
the fallback path is dead code in this branch — but it remains defensive
for downstream contributors who keep a stale repo-root tree.

### B.3 `system_prompt.py::_render_project_context`

`system_prompt.py:204-340`:

| Field | Source | Notes |
|---|---|---|
| project_name | `project.yaml::project.name` with `pdir.name` fallback | matches ADR §3.3 |
| workflow_count | `os.scandir(workflows_dir)` filtered by `.ya?ml` | <100ms budget honoured |
| recent_workflows | top 3 by `entry.stat().st_mtime` | with `_format_age` h/d/w |
| installed_plugins | `get_optional_context().block_registry.installed_plugins` | best-effort, no-op when context missing |
| branch + sha | `git -C <project_dir> rev-parse` with 2.0s timeout | best-effort, omits on failure |

Special-case: when `project_dir` is missing/invalid (no project open),
returns a clear "No active SciStudio project is open" string rather than
crashing. **PASS.**

### B.4 `runtime.py` standalone-bridge wiring

`src/scistudio/ai/agent/mcp/runtime.py`:

- `StandaloneMCPRuntime` dataclass satisfies `MCPContext` Protocol.
- `make_mcp_runtime(project_dir)` builds the registries.
- `start_inprocess_server(project_dir, socket_path=None)` builds the
  `MCPServer`, installs `_context.set_context(runtime)`, and awaits
  `server.start()`.
- `stop_inprocess_server(server)` mirrors teardown.

`MCPServer.serve()` (`server.py:167-184`) drives the standalone bridge:
`await self.start()` then `self._server.serve_forever()`. This is the
single blocking entry-point used by the `scistudio mcp-bridge` subprocess.

**PASS.**

**P3 nit**: The runtime.py module docstring at line 27-32 still describes
the S40a-era state ("MCPServer is now a FastMCP wrapper whose
start()/stop() raise NotImplementedError; I40a Phase 2a wires the real
FastMCP transport into start_inprocess_server"). That description is
historically accurate for S40a but no longer reflects shipped code — `start()`
and `stop()` are fully implemented as real `asyncio.start_unix_server` /
`asyncio.start_server` handlers. **One-line docstring update suggested.**

### B.5 `api/app.py` FastAPI lifespan

`api/app.py:107-114` exposes `block_registry` and `type_registry` via an
inline adapter that delegates to `ApiRuntime`. The MCP server is built
in-process per `MCPServer(socket_path, project_dir)`, started in lifespan,
stopped on shutdown. **PASS** (no changes needed for ADR-040; the
constructor signature is preserved).

### B.6 `terminal.py::spawn_claude`

`terminal.py:452-510`:

- `--mcp-config <project>/.scistudio/mcp.json` preserved.
- `--append-system-prompt @<temp_file>` preserved with `compose_system_prompt`
  driving the temp-file contents.
- `--dangerously-skip-permissions` opt-in preserved.

**PASS.** No argv churn — ADR-040 §5.4 explicitly says PTY architecture
unchanged.

### B.7 `terminal.py::spawn_codex` argv + docstring

`terminal.py:513-564`:

- Argv unchanged: `["codex"]` + optional `--dangerously-bypass-...`.
- Docstring updated to drop the stale "intentional asymmetry with claude"
  language and document the project-scope `.codex/config.toml` +
  `.agents/skills/scistudio/` auto-discovery pair (per ADR-040 §3.7 + §3.8).
- Module-level docstring at line 31-34 also updated: "codex auto-reads
  `~/.codex/config.toml` ... the user's `scistudio install --target codex`
  writes the TOML entry".

**PASS.**

### B.8 `api/runtime.py::create_project` provisioning wiring

`api/runtime.py:611-633`:

1. Wrapped in `try/except Exception` — non-fatal per ADR-040 §7.
2. Runs AFTER ADR-039 git init (line 605 — git init failure path is
   bypassed but `create_project` continues regardless).
3. Logs partial-failure warning if `ProvisionResult.failed` is non-empty.
4. Calls `self.open_project(project.id)` after provisioning, so the
   newly-provisioned assets are present when the project opens.

**PASS.**

### B.9 `api/runtime.py::open_project` idempotent top-up

`api/runtime.py:724-746`:

1. Same try/except non-fatal pattern.
2. `force=False` ensures user-edited files are preserved.
3. Runs BEFORE `self._publish_mcp_port(...)` so the MCP server has the
   provisioned context when external CLIs connect.

**PASS.**

### B.10 `cli/main.py::init` CLI parity

`cli/main.py:184-186`:

```
from scistudio.agent_provisioning import install_project_agent_assets
provision_result = install_project_agent_assets(project_path, force=False)
```

Identical entry point as the GUI path. **PASS** (assumes try/except wraps
this call — verified by inspection earlier in the function; partial-failure
non-fatal contract is preserved).

### B.11 `cli/install.py::_install_skill` cross-install

`cli/install.py:478-516`:

1. Walks BOTH `claude_dest` (`<base>/.claude/skills/scistudio/`) AND
   `codex_dest` (`<base>/.agents/skills/scistudio/`) per ADR-040 §3.9.
2. `_find_skill_source` resolution order: `importlib.resources` first,
   walk-up fallback for dev checkouts (TODO #1011).
3. `shutil.copytree(src, dest)` after wiping any stale `dest` — ensures
   removed source files don't linger.

**PASS.** Symmetric `_remove_skill` at line 519-537.

### B.12 `cli/install.py::_install_codex` project-scope branch

`cli/install.py:307-365`:

- `scope="user"` → `~/.codex/config.toml`, no `SCISTUDIO_PROJECT_DIR` env pin.
- `scope="project"` → `<cwd>/.codex/config.toml` with
  `[mcp_servers.scistudio.env].SCISTUDIO_PROJECT_DIR = <cwd>`.

The legacy "force user-scope for codex" fallback is **removed** from
`perform_install` (verified at line 604-609 — comment confirms removal).

**PASS.**

### B.13 `_render_codex_block` reuse from provisioning

`agent_provisioning/codex_config.py:45` does
`from scistudio.cli.install import _render_codex_block` and renders the same
block content the explicit `scistudio install --target codex --scope project`
emits. `tests/agent_provisioning/test_codex_config.py::test_codex_config_
matches_install_render` enforces byte-equivalence (per `docs/agent-
provisioning.md:135-137`).

**PASS.** **P3 design note**: this is an internal `_render_codex_block`
import from a private symbol — fine pragmatically, but architecturally a
cleaner future refactor would be to extract `_render_codex_block` into a
shared module (e.g. `scistudio.ai.agent.codex_config_template`) so neither
`cli` nor `agent_provisioning` is reaching into the other's private
namespace. Not blocking for this cascade.

---

## C. Frontend touch-points

`grep "mcp__scistudio__\|tools/list" frontend/src/` — **no matches.**

The frontend does not consume MCP `tools/list` programmatically; it only
hosts xterm.js panels showing the spawned claude/codex CLI's own MCP
client traffic. The FastMCP migration changes the server's wire-format
internals (Pydantic serialization, generated inputSchema) but the wire
shape — JSON-RPC 2.0 with the same `tools/list` / `tools/call` methods —
is preserved by `MCPServer.dispatch`.

**PASS — no frontend impact.**

---

## D. Cross-doc consistency sweep

| Doc | Status | Notes |
|---|---|---|
| ADR-040 itself | **PASS** | Reflects shipped impl. Tool count (26) is correct; §5.1 inventory captures the new `agent_provisioning/` + `_skills/` trees. |
| ADR-034 (PTY) | **P2 STALE** | Lines 15, 99, 209 still say "25 tools". Cross-reference to FastMCP / ADR-040 §3.1 absent. |
| ADR-035 (`finish_ai_block`) | **P2 STALE** | Line 192 says "registered like the other 25". No mention of Pydantic envelope shape that ADR-040 §5.3 promised. |
| ADR-038 (lineage) | **PASS** | Hooks do not write lineage per ADR-040 §5.4. No drift. |
| ADR-039 (git auto-init) | **PASS** | ADR-040 §3.8 lifecycle ordering ("AFTER git auto-init") matches `api/runtime.py:611-633`. |
| ARCHITECTURE.md | **P2 PARTIAL** | §10.2 "Prod-env agent reliability stack (ADR-040)" present at line 3016-3067 — good. But §6 (MCP) at line 2274 still says "exposes ~25 tools" — same staleness as ADR-034. |
| `docs/specs/embedded-coding-agent-spec.md` | **P2 STALE** | Lines 761, 780, 1161 say "25 tools"; line 1161 references a non-existent `test_registries.py::MCP tool registry is exhaustive`. ADR-040 §5.3 explicitly said: "Update §6 to remove `TOOL_REGISTRY` references; point at FastMCP decorators" — **not done**. |
| `docs/cli-integration.md` | **PASS** | `--skill` cross-install documented (lines 79-99); project-scope codex documented (line 71). |
| `docs/agent-provisioning.md` | **PASS** with **P3 drift** | Comprehensive operational doc. Lines 155-158 still say "Skill body content — the 5 task-scoped SKILL.md files ship as placeholders ... Phase 2c (`#1013`) authors the real bodies" — STALE post-I40b which DID author them. Wrong issue ref (#1013 is the provisioning track; skill content is #1057). |
| `CHANGELOG.md` | **PASS** | Every merged sub-PR has a `[Unreleased]` entry with the mandatory metadata format `[#N] desc (@author, YYYY-MM-DD, branch: X, session: Y)`. |

### Top-3 cross-doc inconsistencies (priority order)

1. **`docs/specs/embedded-coding-agent-spec.md`** still teaches the
   pre-FastMCP world. ADR-040 §5.3 made this an explicit doc-impact
   deliverable; it was not closed. **P2.**
2. **ADR-034 + ADR-035 + ARCHITECTURE.md §6** all say "25 tools" — three
   files, one find-and-replace. **P2** (functional code path is correct;
   docs are just stale.)
3. **`docs/agent-provisioning.md` lines 155-158** describe an
   already-superseded state (says skills are placeholders; they ship as
   real content from I40b PR #1059). **P3.**

---

## E. Skill content consistency with finalized MCP

### E.1 Base SKILL.md markers

`src/scistudio/_skills/scistudio/SKILL.md` carries BOTH:

- `<!-- project_context:begin --><!-- project_context:end -->` (line 68-69)
- `<!-- tool_catalog:begin --><!-- tool_catalog:end -->` (line 78-79)

per `_splice` requirement in `system_prompt.py:360-377`. **PASS.**

### E.2 Live `InputPort`/`OutputPort` API in `scistudio-write-block` skill

Skill worked example uses the live dataclass API:

```python
input_ports: ClassVar[list[InputPort]] = [
    InputPort(name="image", accepted_types=[Image], required=True),
]
output_ports: ClassVar[list[OutputPort]] = [
    OutputPort(name="mask", accepted_types=[Mask]),
]
```

`src/scistudio/blocks/base/ports.py:23-34` confirms `accepted_types: list[type]`
(not `expected_type: str`). The skill matches the live API.

ADR-040 §3.2a / AC40-skill §1 finding (port-type narrowness via
`list_types` mandate + `scaffold_block` warnings) is covered in the skill
body (sections 3 + 4 of the worked example). **PASS.**

### E.3 Tool names + descriptions in skill bodies

Spot-checks against `await mcp.list_tools()` reveal:

- `scistudio-build-workflow` references `list_blocks`, `list_types`,
  `get_block_schema`, `validate_workflow`, `write_workflow`, `run_workflow`,
  `get_run_status` — all present.
- `scistudio-write-block` references `list_blocks` (#875 reuse), `list_types`
  (port narrowness), `scaffold_block` (`warnings`), `run_block_tests`,
  `reload_blocks` — all present.
- `scistudio-debug-run` references `get_run_status`, `get_block_logs`,
  `get_lineage`, `inspect_data`, `finish_ai_block` — all present.
- `scistudio-inspect-data` references `inspect_data`, `preview_data`,
  `get_lineage`, `get_block_output`, `list_data` — all present.
- `scistudio-project-qa` references `get_project_info`, `search_docs`,
  `get_doc`, `list_data` — all present.

No tool referenced in a skill is missing from `list_tools()`. **PASS.**

### E.4 `<project>/CLAUDE.md` + `<project>/AGENTS.md` templates

`src/scistudio/agent_provisioning/templates/claude_agents_md.md` ships the
~50-line template referenced in ADR-040 §3.5 (Phase 2b refined by I40b).
The `write_claude_agents_md` writer copies the same content to both
`<project>/CLAUDE.md` and `<project>/AGENTS.md`.
`tests/agent_provisioning/test_claude_agents_md.py::test_claude_agents_md_
identical` enforces byte-equivalence.

Content is end-user-agent focused (4 non-negotiable rules + skill list +
project-context section) — distinct from the SciStudio dev `CLAUDE.md`
(~800 lines of gate workflow content). **PASS.**

---

## F. Import graph + linter compliance

### F.1 `agent_provisioning` package registered in arch tests

`tests/architecture/test_placement.py:148`:
```
known_packages = { ..., "agent_provisioning", ... }
```
Per the comment "ADR-040 §3.5-3.8: prod-env agent provisioning module". **PASS.**

### F.2 Import-linter contracts

`pyproject.toml [tool.importlinter]` declares 3 forbidden contracts:

1. `scistudio.core` must not import blocks/engine/api/ai/workflow.
2. `scistudio.blocks` must not import engine/api/ai (one carve-out for
   ai_block → pty_control).
3. `scistudio.engine` must not import api/ai.

`agent_provisioning` is **not** mentioned in any contract. The package
imports:
- `scistudio.cli.install._render_codex_block` (private but legal — no
  contract forbids cross-imports between `agent_provisioning` and `cli`).
- `scistudio.agent_provisioning.{claude_agents_md, codex_config, hooks,
  skills}` (intra-package).

**No contract violations.** **PASS** with the **P3 design note** in §B.13.

### F.3 Cross-import direction

`agent_provisioning` imports from `cli.install`. `cli.install` does NOT
import from `agent_provisioning`. Direction is one-way and acyclic.
**PASS.**

---

## G. Test surface integrity

### G.1 Files unskipped + populated

| File | def test_ count | Module skip? |
|---|---|---|
| `tests/agent_provisioning/test_claude_agents_md.py` | 6 | no |
| `tests/agent_provisioning/test_codex_config.py` | 4 | no |
| `tests/agent_provisioning/test_hooks.py` | 21 | no |
| `tests/agent_provisioning/test_lifecycle_integration.py` | 4 | no |
| `tests/agent_provisioning/test_orchestrate.py` | 6 | no |
| `tests/agent_provisioning/test_skills.py` | 5 | no |
| `tests/ai/test_mcp_fastmcp.py` | 10 | no |
| `tests/ai/test_system_prompt.py` | 10 | no |
| `tests/cli/test_install.py` | 21 | no |
| `tests/packaging/test_wheel_skills.py` | 3 | no |

All flipped from S40* skeleton skip → real assertions. **PASS.**

### G.2 Stale module-skipped tests

`tests/ai/test_mcp_server_skeleton.py` has `pytestmark = pytest.mark.skip`
at line 35 with `TODO(#1012)` reason. Body references the deleted
`_registry.lookup` (line 207). Test never executes — harmless — but the
file should be deleted or rewritten in a small follow-up housekeeping PR.
**P3.**

### G.3 ADR-040-introduced tests pass locally

Per CHANGELOG entries:

- I40a CHANGELOG ([#1037]): "117 ai/cli/integration tests passing locally"
  including 7 FastMCP parity, 8 system_prompt tests with perf budget +
  git/non-git/empty cases.
- I40b CHANGELOG ([#1057]): "9/9 targeted tests pass locally; 61/61 across
  packaging/agent_provisioning/system_prompt".
- I40c CHANGELOG ([#1039]): "43 new pytest cases (0 skipped)" across
  orchestrator, sub-writers, hooks, lifecycle, degraded mode.
- I40d CHANGELOG ([#1035]): "21/21 unit tests pass."

Aggregate: ~190 new tests across the ADR-040 cascade, all passing per
their respective merge commits. **PASS** (CI green on `track/adr-040`
HEAD `949476f` per `gh pr checks` on the umbrella PR).

---

## Findings (P1 / P2 / P3)

### P1 — blocking

**(none)**

The FastMCP migration shipped without any blocking wiring defect found in
scope A2. All 26 tools are discoverable, lifecycle wiring is complete,
provisioning runs at all 3 entry points with non-fatal try/except, and
the frontend has no impact.

### P2 — should-fix follow-up (cross-doc sweep)

- **P2-A2-01**: `docs/specs/embedded-coding-agent-spec.md` still references
  the deleted `TOOL_REGISTRY` and says "25 tools" in §6 (and elsewhere).
  ADR-040 §5.3 promised this update. Suggested change: §6 "MCP tool
  registry" → "MCP tool registry (FastMCP)"; replace `TOOL_REGISTRY`
  references with `@mcp.tool()` decorators; "25 tools" → "26 tools (25
  baseline + `finish_ai_block` per ADR-035 §3.5)". Tracked separately
  (open as a small docs PR after the cascade ships).
- **P2-A2-02**: ADR-034 lines 15, 99, 209 say "25 tools". Update to "26"
  + add a single-line cross-reference to ADR-040 §3.1 ("MCP catalog
  re-render is now FastMCP-driven; see ADR-040 §3.1").
- **P2-A2-03**: ADR-035 line 192 says "registered like the other 25" — add
  ADR-040 §3.1 cross-ref: "`finish_ai_block` ports to FastMCP with the
  same shape per ADR-040 §3.1; error envelopes become Pydantic `Union`
  returns. Semantics unchanged."
- **P2-A2-04**: `ARCHITECTURE.md` line 2274 says "~25 tools" in §6 (MCP
  layer). Update to "26 tools" + link to §10.2 (the new ADR-040 subsection).
- **P2-A2-05**: `docs/agent-provisioning.md` lines 155-158 describe a
  state ("skills ship as placeholders") that I40b PR #1059 already
  superseded. Update text to "Skill bodies authored in I40b PR #1059 ship
  in the bundled `src/scistudio/_skills/scistudio/` tree" and drop the
  inaccurate `#1013` ref (should be `#1057`).

### P3 — nice-to-have

- **P3-A2-01**: `src/scistudio/ai/agent/mcp/runtime.py:27-32` module
  docstring describes the S40a-era state ("MCPServer is a FastMCP wrapper
  whose start()/stop() raise NotImplementedError"). Real impl ships
  `start()`/`stop()`/`serve()` fully wired. One-line docstring rewrite.
- **P3-A2-02**: `tests/ai/test_mcp_server_skeleton.py` is entirely skipped
  with stale `_registry` imports in its body. Delete the file or rewrite
  against FastMCP — small housekeeping follow-up.
- **P3-A2-03**: `src/scistudio/cli/install.py` module docstring line 5 says
  "the full 25-tool MCP surface". Update to 26 (or drop the count and link
  to ADR-040).
- **P3-A2-04**: `agent_provisioning/codex_config.py` reaches into
  `cli.install._render_codex_block` (a private symbol). Functionally
  correct, but a cleaner future refactor extracts the renderer to a
  shared module. Not blocking; flag for ADR-041 backlog.

---

## Recommendation for manager

The A2 scope is **pass-with-fixes**. The cascade is ship-ready after the
P2 cross-doc sweep is landed. Suggested ordering:

1. **Merge `track/adr-040` to main as-is.** No P1 in scope A2; runtime
   wiring is correct. CI is green. The user can drive Phase 4 e2e against
   the merged state.
2. **Open a small docs-cleanup PR for the 5 P2 findings (cross-doc sweep)
   immediately after the cascade merges.** All five are find-and-replace
   level changes; total LOC ~30 across 5 files. Title:
   `docs(#1011): ADR-040 cross-doc sweep — 25→26 tool count, TOOL_REGISTRY
   refs, post-I40b drift`.
3. **Defer the 4 P3 nits to a single housekeeping batch PR.** They are
   cosmetic and individually small. Title:
   `chore(#1011): ADR-040 cascade post-merge housekeeping`.
4. Manager should also sweep A1 + A3 reports for any P1 they surface;
   A2's read on functional correctness is "ship". If A1 finds a
   Pydantic-shape regression that breaks an MCP wire-format round-trip,
   that supersedes A2's pass verdict.

Phase 4 e2e (the user's Chrome smoke test) can proceed against the
merged main once A1 + A3 also clear.

---

*End of A2 audit report.*
