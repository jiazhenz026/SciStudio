# A1 Audit — ADR-040 Completeness + Bugs + Edge Cases

**Date**: 2026-05-16
**Auditor**: A1 (Phase 3 parallel audit, opus)
**Scope**: ADR-040 production-environment agent reliability cascade
**PRs reviewed**: #1053 (I40a FastMCP impl), #1058 (I40a Codex reconcile), #1047 (I40c provisioning), #1049 (I40d install-parity), #1054 (AC40-skill blueprint), #1059 (I40b skill content), #1064 (scaffold `accepted_types` fix — OPEN)
**Tracking branch reviewed**: `track/adr-040` @ `949476f` (latest)
**Checklist rows verified**: 38 / 38 in scope for A1
**Test runs**: `PYTHONPATH=src pytest tests/ai/ tests/agent_provisioning/ tests/cli/test_install.py -n auto --timeout=60 --no-cov` → 175 passed / 90 skipped / 0 failed.

## Summary

**pass-with-fixes**. The FastMCP migration, provisioning module, hooks scaffolding, lifecycle wiring, install-parity refactor, and CLAUDE.md/AGENTS.md/skills content all landed and all targeted tests pass. However, four release-blocking-or-near-blocking issues remain after the merged PRs:

1. **P1** — `hook_enforce_concrete_port_types.py` AST-scans for `PortSpec(...)` calls, but SciEasy's actual block contract uses `InputPort(name=..., accepted_types=[T])` / `OutputPort(...)`. The hook will NEVER fire on a real `blocks/*.py` file → the §3.6 PostToolUse port-type advisory layer is dead code.
2. **P1** — Open PR #1064 (`accepted_types=[T]` scaffold fix, issue #1063) is NOT yet on `track/adr-040`. Until merged, every block scaffolded via `mcp__scieasy__scaffold_block` with custom ports produces a syntax-valid but contract-broken module (`type=<X>` is not a `Port` field).
3. **P1** — Skill content (`scieasy-write-block/SKILL.md`, `scieasy-debug-run/SKILL.md`, `scieasy-build-workflow/SKILL.md`) teaches stale/wrong Pydantic field contracts that Codex flagged on PR #1059 (`block_path=` vs `type_name=`, `{ok, errors, next_step}` vs `ValidateWorkflowResult(valid, errors)`, top-level `block_states/error` vs `progress.block_states / errors: list`). Agents following these examples will emit invalid MCP calls and mis-handle status envelopes.
4. **P1** — `_render_tool_catalog`'s `ThreadPoolExecutor` deadlock workaround in `system_prompt.py` still suffers the issue Codex P1 on PR #1058 flagged: `with ThreadPoolExecutor(...) as pool: pool.submit(_list_in_thread).result(timeout=5.0)` — context-manager exit calls `shutdown(wait=True)` which blocks waiting for the hung worker, so the 5-second timeout does not guarantee fail-fast.

Three P2 findings, two P3 findings, plus the standard tech-debt log. None of the §3.x ADR decisions are absent; all are implemented but with the residual defects above.

## Per-§3 ADR compliance

### §3.1 FastMCP migration

**Status: implemented (residual P1).**

- `src/scieasy/ai/agent/mcp/server.py` (334 LOC) wires `mcp = FastMCP(name="scieasy-mcp", version="0.1.0")` at module scope; `MCPServer` lifecycle wrapper preserves the ADR-033-era `start/stop/serve` surface for the FastAPI lifespan + standalone bridge runtime.
- `_registry.py` deleted from `src/scieasy/ai/agent/mcp/` (verified via `ls`). `_render_tool_catalog` in `system_prompt.py` enumerates via `await mcp.list_tools()`.
- `__init__.py` eagerly imports `tools_workflow / tools_authoring / tools_inspection / tools_qa` so `@mcp.tool()` decorators register at package import time. Verified: `python -c "import asyncio; from scieasy.ai.agent.mcp.server import mcp; print(len(asyncio.run(mcp.list_tools())))"` → 26.
- `dispatch` distinguishes `METHOD_NOT_FOUND` (-32601) from `INVALID_PARAMS` (-32602) on unknown-tool calls. Pre-checks via `await mcp.list_tools()` then routes through `mcp.call_tool`.
- `inputSchema` generation: every tool returns `{additionalProperties: False, properties: {...}, required: [...], type: 'object'}`. Verified live — no `additionalProperties: True` regression.
- `_serialise_result` falls back through `structured_content → content[].text → str(block)` — handles both old + new FastMCP `ToolResult` shapes.

**Residual P1 (Codex on PR #1058 — NOT fixed despite "accepted" Codex reply on PR #1053):**

`src/scieasy/ai/agent/system_prompt.py:160-169`:
```python
with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
    tools = pool.submit(_list_in_thread).result(timeout=5.0)
```
When the worker hangs past 5s, `result(timeout=5.0)` raises `TimeoutError` — then the `with` block exits, calling `pool.shutdown(wait=True)` implicitly, which **still blocks waiting for the hung worker**. Net effect: a hung `mcp.list_tools()` will hang `compose_system_prompt` indefinitely in the async-PTY-spawn path, defeating the timeout.

**Fix**: use `pool.shutdown(wait=False, cancel_futures=True)` explicitly inside a `try/except TimeoutError:` block, or use `asyncio.wait_for` with a fresh loop in a daemon thread.

### §3.2 Tool description + `next_step` rewrite

**Status: implemented.**

- 26-tool catalog regenerated. All 8 write-class tools carry a `next_step: str` field on their Pydantic result model. Verified via `tests/ai/test_mcp_fastmcp.py::test_write_class_tools_have_next_step`:
  - `write_workflow` → `WriteWorkflowResult.next_step` ("Call `mcp__scieasy__validate_workflow` …")
  - `run_workflow` → `RunWorkflowResult.next_step` ("Poll `mcp__scieasy__get_run_status` …")
  - `cancel_run` → `CancelRunResult.next_step`
  - `finish_ai_block` → `FinishAIBlockOK.next_step` (Error envelope has no `next_step` — intentional)
  - `scaffold_block` → `ScaffoldBlockResult.next_step`
  - `reload_blocks` → `ReloadBlocksResult.next_step`
  - `run_block_tests` → `RunBlockTestsResult.next_step`
  - `update_block_config` → `UpdateBlockConfigResult.next_step`
- Docstrings follow the §3.2 "Use when … Do NOT use to …" style guide.

### §3.2a `scaffold_block` `warnings: list[str]`

**Status: implemented (P1 + P2 caveats).**

- `tools_authoring.scaffold_block` now accepts widened signature: `name, category, input_ports: dict | None, output_ports: dict | None`. Both default to `None`, normalised to `{}` inside the body.
- `ScaffoldBlockResult.warnings: list[str]` field present.
- §3.2a soft-validation logic: generic-`DataObject` detection + unregistered-type detection both emit warning strings.
- Tests: `test_scaffold_block_warns_on_generic_dataobject_port` + `test_scaffold_block_warns_on_unregistered_type` both pass.

**P1 (issue #1063, PR #1064 OPEN — NOT yet merged into `track/adr-040`):**

`_SCAFFOLD_TEMPLATE` at `tools_authoring.py:271,278` emits:
```python
InputPort(name='in', type=DataObject, required=True),
```
But the real contract (`src/scieasy/blocks/base/ports.py:17`): `Port.accepted_types: list[type]` — no `type=` field exists. Scaffolded blocks fail to import with `TypeError: __init__() got an unexpected keyword argument 'type'`. PR #1064 (`fix(#1063): scaffold template uses accepted_types=[T] not type=T`, commit `043cc5b`) is the fix.

**P2** — The `_type_registry_has(ctx, type_name)` helper falls back through `has()` → `all_types()` swallowing `Exception`. On a missing context (e.g. unit test stub without `type_registry`), it silently treats every type as "unregistered" — which is actually correct for the `test_scaffold_block_warns_on_unregistered_type` test, but masks real misconfiguration in prod. Recommend adding a debug-log when both paths fail.

### §3.2a hook-side enforcement (`hook_enforce_concrete_port_types.py`)

**Status: implemented BUT DEAD CODE — P1.**

`src/scieasy/agent_provisioning/templates/hook_enforce_concrete_port_types.py:89-96`:
```python
if isinstance(func, ast.Name):
    if func.id != "PortSpec":
        continue
elif isinstance(func, ast.Attribute):
    if func.attr != "PortSpec":
        continue
```

But the real Block contract uses `InputPort(name=..., accepted_types=[...])` / `OutputPort(...)`:
- `src/scieasy/blocks/base/ports.py:24` — `class InputPort(Port)`
- `src/scieasy/blocks/base/ports.py:33` — `class OutputPort(Port)`
- `src/scieasy/ai/agent/mcp/tools_authoring.py:271,278` — scaffold template uses `InputPort(...)` / `OutputPort(...)`

Grep over `src/scieasy/`: `PortSpec` appears only in (a) this hook source, (b) the obsolete `block_base_template.py` (line 27 explicitly says "the port classes are `InputPort`/`OutputPort` (no `PortSpec`)"), and (c) one docstring reference in `api/routes/blocks.py:168`. **The runtime contract uses no `PortSpec` class.**

Result: the §3.2a L5 PostToolUse port-type advisory layer **always returns empty findings** on real block files → silently fails to enforce the rule. Combined with the §3.2a soft-validation path being bypassed when the agent writes a block via Edit/Write/Bash (which is the entire reason the hook exists), the port-type policy has no enforcement layer left.

**Fix**: rewrite the AST scan to target `InputPort(...)` / `OutputPort(...)` calls and check the `accepted_types` keyword arg for `[DataObject]` / `[]` / missing.

### §3.3 `_render_project_context`

**Status: implemented + correct (P2 caveat).**

- New `src/scieasy/ai/agent/system_prompt.py::_render_project_context(project_dir) -> str`.
- All §3.3 field-source-table cases handled: `project_name` (yaml fallback to `pdir.name`), `workflow_count` (os.scandir), `installed_plugins` (BlockRegistry best-effort), `branch`/`sha` (subprocess with 2s timeout, omits on failure), top-3 recent workflows.
- Empty-workflows branch: `if workflow_count == 1: ... else: f"{count} workflows on disk"` — handles 0 + N cases gracefully.
- Non-project guard: `if not project_dir or not Path(project_dir).is_dir(): return "No active SciEasy project is open. …"`.
- Non-git: `if (pdir / ".git").exists():` guard prevents subprocess spawn.
- Perf: uses `os.scandir` (single syscall iteration). Verified manually with a 1000-workflow tmpdir: <50ms.
- Tests: 8 tests in `test_system_prompt.py` cover git/non-git/empty/perf/marker-splice — all pass.

**P2 — corrupt-git case:**

When `.git/` exists but is corrupt (e.g. truncated index or `HEAD` pointing to non-existent ref), `git rev-parse --abbrev-ref HEAD` may return non-zero with stderr. Current code:
```python
if branch_proc.returncode == 0:
    branch = branch_proc.stdout.strip() or None
```
Handles returncode!=0 (`branch` stays None) — OK. But the 2-second timeout may not fire on a process that lights up `git` warnings to stderr without ever exiting (e.g. lock-file contention from a stale `.git/index.lock`). `timeout=2.0` covers most cases. Not a blocker, but worth a regression test.

**P3 — special-char project_name:**

`project_name` is interpolated unescaped into markdown headers: `lines.append(f"**Project:** {project_name}")`. A `name` like `foo \n## fake-section` could inject markdown structure. Low-impact (the system prompt is local + trusted) but technically an injection vector if a hostile `project.yaml` ever ships.

### §3.4 Multi-skill split + wheel packaging

**Status: implemented.**

- `src/scieasy/_skills/scieasy/` tree exists with 1 base + 5 task skills (SKILL.md each).
- `system_prompt._load_skill_md` prefers `importlib.resources.files("scieasy") / "_skills" / "scieasy" / "SKILL.md"` with legacy walk-up fallback (TODO #1012-tagged for cleanup).
- `pyproject.toml [tool.setuptools.package-data]` includes `scieasy = [..., "_skills/scieasy/**/*.md"]` (verified via `cat pyproject.toml | grep package-data -A2`).
- `agent_provisioning.skills.write_skills` cross-installs all 6 files to both `.claude/skills/scieasy/<name>/SKILL.md` and `.agents/skills/scieasy/<name>/SKILL.md` (12 paths total).

**P1 — skill content drift from real models** (Codex on PR #1059, NOT addressed):

`src/scieasy/_skills/scieasy/scieasy-write-block/SKILL.md:264`:
```
mcp__scieasy__run_block_tests block_path=blocks/threshold_simple.py
```
The actual MCP tool signature is `run_block_tests(type_name: str)` (`tools_authoring.py:447`). Agents following this worked example will emit `block_path=…` → FastMCP inputSchema rejection.

`src/scieasy/_skills/scieasy/scieasy-build-workflow/SKILL.md:261-262`:
```
`validate_workflow` returns `{ok: bool, errors: list[ValidationError],
next_step: str}`.
```
Actual: `ValidateWorkflowResult(valid: bool, errors: list[str])` — no `ok`, no `next_step`. Agents reading `result.ok` get `None`.

`src/scieasy/_skills/scieasy/scieasy-debug-run/SKILL.md:39-43`:
```
state: ..., block_states: {...}, ..., error: str | null
```
Actual: `GetRunStatusResult(run_id, state, progress: {block_states: {...}}, errors: list[BlockErrorEntry])`. Agents reading top-level `block_states` / `error` get `KeyError`.

**Fix**: rewrite the affected sections in PR-or-followup. Codex flagged all three on #1059 and they were not addressed.

### §3.5 CLAUDE.md / AGENTS.md template

**Status: implemented.**

- Single source-of-truth file at `src/scieasy/agent_provisioning/templates/claude_agents_md.md`.
- `agent_provisioning.claude_agents_md.write_claude_agents_md` writes both `<project>/CLAUDE.md` and `<project>/AGENTS.md` verbatim from this template.
- Content (~75 lines) covers identity, MCP-only rule, hook awareness, skill index, `next_step`/`warnings` reading discipline, project-cwd handling, ADR-039 git tracking.
- Tests: `test_claude_agents_md.py` confirms both files written, identical bytes, idempotent top-up preserves user edits.

### §3.6 Project-scoped hooks

**Status: implemented (P1 on `hook_enforce_concrete_port_types.py` — see §3.2a above).**

- 6 hook templates land at `src/scieasy/agent_provisioning/templates/` (verified):
  - `hook_deny_scieasy_cli.py` (PreToolUse / Bash)
  - `hook_protect_workflow_yaml.py` (PreToolUse / Edit|Write|MultiEdit)
  - `hook_enforce_list_blocks_before_block_write.py` (PreToolUse / Edit|Write|MultiEdit|Bash|mcp__scieasy__scaffold_block)
  - `hook_remind_poll_status.py` (PostToolUse / mcp__scieasy__run_workflow)
  - `hook_mark_list_blocks_called.py` (PostToolUse / mcp__scieasy__list_blocks)
  - `hook_enforce_concrete_port_types.py` (PostToolUse / Edit|Write|MultiEdit|mcp__scieasy__scaffold_block)
- `agent_provisioning.hooks.write_hooks` writes `.claude/settings.json` (with all 3 PreToolUse + 3 PostToolUse matchers, MultiEdit included per Codex P1 on PR #1047) plus copies the 6 scripts to `<project>/.claude/hooks/`.
- `_build_settings_json` builds the matcher table; verified at `test_hooks.py::test_write_hooks_creates_settings_json` (passes).
- MultiEdit fix (Codex P1 on PR #1047) **is** in place: `_build_settings_json` interleaves `"Edit|Write|MultiEdit"` and `"Edit|Write|MultiEdit|Bash|mcp__scieasy__scaffold_block"`.
- No-space redirect fix (Codex P1 on PR #1047) **is** in place: `_BASH_WRITE_RE` accepts `>>?\s*` (zero whitespace) so `echo x >blocks/y.py` is caught.

### §3.7 `<project>/.codex/config.toml`

**Status: implemented.**

- `agent_provisioning.codex_config.write_codex_config` writes `<project>/.codex/config.toml`.
- Implementation reuses `scieasy.cli.install._render_codex_block(project_dir.resolve())` so the auto-provisioned TOML is byte-identical to `scieasy install --target codex --scope project` output.
- Idempotent: `if dest.exists() and not force: return []`.
- Template at `src/scieasy/agent_provisioning/templates/codex_config.toml` is documentation-only (header carries `TODO(#1013)` noting the real content is `_render_codex_block`-generated).

### §3.8 `install_project_agent_assets` orchestrator

**Status: implemented (P2).**

- Top-level entry at `src/scieasy/agent_provisioning/_orchestrate.py::install_project_agent_assets(project_dir, *, force=False) -> ProvisionResult`.
- Per-step isolation: failure in `claude_agents_md` / `hooks` / `skills` / `codex_config` is recorded in `ProvisionResult.failed` and remaining steps still run.
- `SCIEASY_PROVISION_VERSION = "0.1.0"` constant exposed; marker file written at `<project>/.claude/.scieasy-provision-version`.
- Lifecycle wired at:
  - `src/scieasy/api/runtime.py:618-635` (create_project, after ADR-039 git init)
  - `src/scieasy/api/runtime.py:732-749` (open_project idempotent top-up)
  - `src/scieasy/cli/main.py:184-200` (CLI init)
- Tests in `test_lifecycle_integration.py` cover create-project, open-project idempotency (with user-edited CLAUDE.md preserved), CLI init.

**P2 — version-marker write semantics under partial failure:**

`_orchestrate.py:130-148`: the version marker is written **even when sub-steps fail**. Future upgrade logic (OQ-1 / Phase 3) compares marker against `SCIEASY_PROVISION_VERSION` to decide whether to top up. If hook-script generation failed (e.g. `importlib.resources` race on first install), the marker still records "0.1.0 fully installed" — preventing the next `open_project` from retrying.

**Fix**: only write the marker when `result.failed == []`, or write a per-step manifest so partial states are observable.

**P3 — no rollback on partial install:**

If `write_skills` succeeds but `write_codex_config` raises, the project ends up with skills but no Codex MCP config and no clean way to retry without `force=True`. Acceptable for v1 (ADR §7 explicitly says "non-fatal"), but a future enhancement could record per-step success in the marker.

### §3.9 `scieasy install --skill` cross-install + Codex project-scope

**Status: implemented.**

- `src/scieasy/cli/install.py`:
  - `_codex_config_path(scope, cwd) -> Path` accepts both `"user"` (→ `~/.codex/config.toml`) and `"project"` (→ `<cwd>/.codex/config.toml`).
  - The "force user-scope for codex" fallback at the legacy `install.py:489-498` is **removed** (verified — `perform_install` now calls `_install_codex(scope, cwd)` directly for both scopes; comment explicitly notes the legacy removal).
  - `_install_skill(scope, cwd) -> list[InstallResult]` cross-installs to both `.claude/skills/scieasy/` AND `.agents/skills/scieasy/` (2 entries returned per call).
  - `_remove_skill` symmetric.
- `perform_install`'s docstring updated for ADR-040 §3.7 + §3.9.

**P2 — legacy walk-up fallback inside `_find_skill_source`:**

When `importlib.resources.files("scieasy")` is unavailable AND a repo-root `skills/scieasy/SKILL.md` exists, `_find_skill_source` returns the legacy tree — which post-cascade contains only `examples/`, not the new 6-file structure. After the Skills track merged via PR #1059, this is dormant — but the fallback should be removed (TODO #1011 already filed). Codex P2 on PR #1049 flagged this.

### §3.10 Out-of-scope items properly TODO-tagged

**Status: pass-with-noise.**

`grep -rn "TODO[^(]" src/` returns **9 hits**. Breakdown:

| Path | Line | Status |
|---|---|---|
| `src/scieasy/ai/agent/mcp/tools_authoring.py` | 239, 242, 256 | Inside `_SCAFFOLD_TEMPLATE` triple-quoted string — content emitted INTO scaffolded user code (`"""TODO: describe what this block does."""` etc.). Acceptable. |
| `src/scieasy/blocks/app/watcher.py` | 8 | Pre-existing; not introduced by ADR-040. |
| `src/scieasy/blocks/process/builtins/merge.py` | 70 | Pre-existing. |
| `src/scieasy/blocks/subworkflow/subworkflow_block.py` | 38 | Pre-existing — references `#890`. |
| `src/scieasy/cli/templates/block_package/blocks.py.tpl` | 61 | Pre-existing — emitted into user templates. |
| `src/scieasy/utils/logging.py` | 8 | Pre-existing — references `#827`. |
| `src/scieasy/utils/wrapping.py` | 14 | Pre-existing — no issue reference. |

ADR-040 cascade introduces **zero new untagged TODOs** in src/. All TODOs added by I40a/c/d/b carry `(#NNN)` references. The 9 grep hits are either pre-existing tech debt (out of scope) or template-string content (intentional). **CLAUDE.md §7.6 compliance for this cascade: PASS.**

## Pydantic model walk

26 tools × Pydantic return models cross-checked. All write-class tools (8) carry `next_step`. All Pydantic field descriptions present. Serialization → MCP wire round-trip exercised by `tests/integration/test_phase2_mcp_end_to_end.py` (3 tests pass).

| Tool | Return model | next_step? | warnings? | Findings |
|---|---|---|---|---|
| list_blocks | `list[BlockSpecEnvelope]` | N/A (read) | N/A | OK |
| get_block_schema | `BlockSchemaResult` | N/A (read) | — | OK |
| list_types | `ListTypesResult` | N/A (read) | — | OK |
| get_workflow | `WorkflowDefinitionEnvelope` | N/A (read) | — | OK |
| validate_workflow | `ValidateWorkflowResult(valid, errors)` | NO (intentional) | — | Skill content P1 — see §3.4 |
| write_workflow | `WriteWorkflowResult` | YES | — | OK |
| run_workflow | `RunWorkflowResult` | YES | — | OK |
| cancel_run | `CancelRunResult` | YES | — | OK |
| get_run_status | `GetRunStatusResult` | NO (intentional read) | — | Skill content P1 — see §3.4 |
| finish_ai_block | `FinishAIBlockOK \| FinishAIBlockError` | YES on OK | — | OK |
| read_block_source | `ReadBlockSourceResult` | N/A (read) | — | OK |
| list_block_examples | `list[BlockExampleEnvelope]` | N/A (read) | — | OK |
| scaffold_block | `ScaffoldBlockResult` | YES | YES | P1 §3.2a hook DEAD CODE + open PR #1064 |
| reload_blocks | `ReloadBlocksResult` | YES | — | OK |
| run_block_tests | `RunBlockTestsResult` | YES | — | Skill content uses wrong arg `block_path` |
| get_block_output | `GetBlockOutputResult` | N/A (read) | — | OK |
| inspect_data | `InspectDataResult` | N/A (read) | — | OK |
| preview_data | `PreviewDataResult` | N/A (read) | — | OK (Codex P1 preview-cap fixed in #1058) |
| get_lineage | `GetLineageResult` | N/A (read) | — | OK |
| get_block_config | `GetBlockConfigResult` | N/A (read) | — | OK |
| update_block_config | `UpdateBlockConfigResult` | YES | — | OK |
| get_block_logs | `GetBlockLogsResult` | N/A (read) | — | OK |
| search_docs | (returns dict list) | N/A (read) | — | OK (Codex P2 sort fixed in #1058) |
| get_doc | `GetDocResult` | N/A (read) | — | OK |
| list_data | `ListDataResult` | N/A (read) | — | OK |
| get_project_info | `GetProjectInfoResult` | N/A (read) | — | OK |

Single shape-issue: `update_block_config`'s result is also documented as "write-class" in the §3.2 style guide but the model is fine — `next_step` field is present.

## Hook script edge cases

### `deny_scieasy_cli.py`

Regex: `r"^\s*(?:\S*/)?scieasy(?:\s|$)"`.

| Test vector | Caught? | Comment |
|---|---|---|
| `scieasy run` | YES | obvious |
| `  scieasy run` | YES | leading whitespace allowed |
| `./scieasy run` | YES | `\S*/` matches `./` |
| `/usr/local/bin/scieasy run` | YES | absolute path |
| `scieasy` (no args) | YES | `\s|$` catches EOL |
| `SCIEASY=1 scieasy run` | NO | env-var prefix bypasses `^\s*` |
| `python -m scieasy run` | NO | Bash uses `python`, regex anchored to `scieasy` first word |
| `cd foo && scieasy run` | NO | second cmd in chain not anchored |
| `xargs scieasy < list.txt` | NO | xargs prefix bypasses |

Known limitation per ADR §3.6 "exotic Bash bypass" disclaimer + #1015 deferral. Acceptable for v1.

### `protect_workflow_yaml.py`

Regex: `r"workflows/.*\.ya?ml$"` (case-insensitive).

| Test vector | Caught? |
|---|---|
| `workflows/main.yaml` | YES |
| `workflows/sub/run.yml` | YES |
| `/abs/path/to/workflows/x.yaml` | YES |
| `..\\workflows\\x.yaml` (Windows) | YES (replaced `\\` → `/`) |
| `Workflows/x.yaml` | YES (re.IGNORECASE) |
| `notworkflows/x.yaml` | YES (.* matches `notworkflows/x.` then `yaml` anchored — actually NO because regex is `workflows/`, prefix matching against `notworkflows/x.yaml` — the regex finds `workflows/x.yaml` substring) | actually MATCHES because `search` not `match` |
| `workflows-backup/x.yaml` | YES (`workflows` token + `/` + arbitrary `.*` + `.yaml`) — actually NO; regex is `workflows/` literal slash |

Minor: `re.search` with `workflows/` substring catches `notworkflows-old/foo.yaml` as a false positive (substring match). Low-impact: edits to any `*/workflows/*.yaml` were probably intended to flow through MCP anyway.

### `enforce_list_blocks_before_block_write.py`

Block-file regex: `r"(?:^|/)blocks/[^/]+\.py$"` — anchored to `/blocks/` or string start.
Bash write regex: `r"(?:>>?\s*|\b(?:tee|cp\s+\S+)\s+)\S*blocks/\S+\.py"`.

| Test vector (Bash) | Caught? |
|---|---|
| `echo x > blocks/y.py` | YES |
| `echo x >blocks/y.py` | YES (no-space, Codex P1 fix on #1047) |
| `echo x >> blocks/y.py` | YES |
| `tee blocks/y.py < input.txt` | YES |
| `cp src.py blocks/y.py` | YES |
| `python -c "open('blocks/y.py','w').write(...)"` | NO (known) |
| `mv tmp.py blocks/y.py` | NO (known) |
| `cat > blocks/y.py <<EOF` | YES (`>` + path) |
| `sh -c "echo x > blocks/y.py"` | YES (`>` + path inside quoted args still matches `re.search`) |

Session-marker logic:
- `session_id` from stdin payload; if missing → fail-closed (block).
- Path-traversal guard: `re.search(r"[\\/\x00]", session_id)` → reject session_ids containing slashes / nulls. **Good.**
- Project-dir from `CLAUDE_PROJECT_DIR` env var; if missing → fail-closed.
- Marker path: `<project>/.scieasy/.session-state/<session_id>/list_blocks_called`. Gitignored via `.scieasy/`.

**Race condition:** between `mark_list_blocks_called.py` (PostToolUse) writing the marker and `enforce_list_blocks_before_block_write.py` (PreToolUse) reading it. Claude Code serializes hooks per tool call, so the PreToolUse of a block-write always runs after the PostToolUse of any prior `list_blocks`. No race in practice.

**Stale marker on session reuse:** Claude Code may reuse a `session_id` if the user resumes a session via `claude --resume`. The marker persists across resume — agent may write a block hours later without re-listing. Acceptable per ADR §3.6 ("session-keyed"), but the operational doc should mention manual cleanup if the user wants a fresh enforcement.

### `remind_poll_status.py`

Always exit 0. Reads `tool_response` for `run_id` / `runId` (camelCase fallback — kind). Prints reminder text on stderr. No edge cases.

### `mark_list_blocks_called.py`

Always exit 0. Best-effort marker write. Reuses the same `session_id` sanitization. If marker write fails (e.g. permission denied), prints warning to stderr (Claude Code captures + may surface to user). **OK.**

### `hook_enforce_concrete_port_types.py`

**P1 — see §3.2a above. AST scans for `PortSpec` which does NOT exist in the runtime contract. Hook is dead code.**

Secondary issue: `_target_file` uses `tool_response.get("file_path") or tool_response.get("path")`. The `ScaffoldBlockResult.path` field IS named `path`, but FastMCP serializes the result through `_serialise_result` → `content[].text` (JSON-encoded structured content). It's unclear whether Claude Code surfaces the structured content as `tool_response.path` or as `tool_response.content[0].text` (then needs re-decode). Worth verifying empirically with a live Chrome smoke once §3.2a hook is rewritten.

## `_render_project_context` edge cases

| Case | Behavior | Status |
|---|---|---|
| `project_dir = None` | Returns "No active SciEasy project is open." text | OK |
| `project_dir` non-existent | Same fallback | OK |
| 0 workflows | `**Workflows:** 0 workflows on disk` | OK |
| 1 workflow | `**Workflows:** 1 workflow on disk` (singular) | OK |
| 10000 workflows | Uses `os.scandir`; <100ms verified | OK |
| Corrupt `.git/` (no HEAD ref) | `git rev-parse` returns non-zero → branch=None → section omitted | OK |
| Non-git project | `.git/` not present → section omitted | OK |
| `project_name` with newlines / markdown | Interpolated verbatim → markdown injection (P3) | P3 |
| `project.yaml` malformed YAML | `yaml.safe_load` raises → caught + fallback to `pdir.name` | OK |
| `project.yaml` valid but no `project.name` | Fallback to `pdir.name` | OK |
| `installed_plugins` missing context | Catches `Exception` → empty list → section omitted | OK |
| BlockRegistry empty | `installed_plugins=[]` → section omitted | OK |
| mtime skew (future-dated files) | `_format_age(negative)` returns "just now" | OK |
| Git lock-file contention (`.git/index.lock`) | 2s subprocess timeout → branch=None | acceptable; not deterministic |

Special-case missed: when `project.yaml::project.name` is non-string (e.g. number), `str(meta["name"])` coerces silently. OK.

## `install_project_agent_assets` edge cases

| Case | Behavior | Status |
|---|---|---|
| Fresh project (no prior files) | Writes all expected paths; marker = "0.1.0" | OK |
| User-edited CLAUDE.md, force=False | `if dest.exists() and not force: continue` → preserved | OK (verified by test) |
| User-edited file, force=True | Overwritten | OK |
| Missing parent dir (`.claude/`) | `dest.parent.mkdir(parents=True, exist_ok=True)` inside each writer | OK |
| Permission denied on write | Caught at orchestrator's per-step try/except → ProvisionResult.failed populated | OK |
| `write_hooks` fails entirely | Other steps still run; marker still writes | **P2 — see §3.8** |
| Version-marker drift (existing marker != current) | No upgrade logic (deferred to OQ-1) | acceptable per ADR |
| Partial install rollback | None (deferred to v2) | acceptable per ADR §7 |
| Concurrent `open_project` calls | Last write wins per file; no file-lock | acceptable (single-process API) |
| Non-existent `project_dir` | `project_dir.mkdir(parents=True, exist_ok=True)` creates it | OK |

## TODO audit

`grep -rn "TODO[^(]" src/` → 9 matches. After excluding `_SCAFFOLD_TEMPLATE` string content (intentional content emitted into user code, 3 matches), 6 matches remain. None are introduced by ADR-040 cascade — all are pre-existing. CLAUDE.md §7.6 compliance for this cascade: **PASS**.

```
src/scieasy/blocks/app/watcher.py:8                     # pre-existing
src/scieasy/blocks/process/builtins/merge.py:70         # pre-existing
src/scieasy/blocks/subworkflow/subworkflow_block.py:38  # pre-existing (refs #890)
src/scieasy/cli/templates/block_package/blocks.py.tpl:61  # template content
src/scieasy/utils/logging.py:8                          # pre-existing (refs #827)
src/scieasy/utils/wrapping.py:14                        # pre-existing
```

ADR-040-introduced TODOs (sampled — all carry `(#NNN)`):
- `_orchestrate.py:34`: `TODO(#1011): version-marker UPGRADE flow ...`
- `system_prompt.py:91`: `TODO(#1012): drop this branch once src/scieasy/_skills/scieasy/SKILL.md ships on main ...`
- `tools_authoring.py:367`: `TODO(#1016): hard BlockRegistry-level rejection of generic DataObject ports ...`
- `hook_enforce_list_blocks_before_block_write.py:17`: `TODO(#1015): Layer 7 filesystem ACL on <project>/blocks/ ...`
- `hook_enforce_concrete_port_types.py:14`: `TODO(#1016): BlockRegistry runtime rejection of DataObject-typed ports ...`
- `install.py:434`: `TODO(#1011): Once the packaged src/scieasy/_skills/ tree is canonical ...`

## Tool count + naming

`await mcp.list_tools()` → 26 entries. Test `test_fastmcp_lists_26_tools` passes with explicit expected-set check.

Names match `_EXPECTED_TOOL_NAMES` set verbatim:
- workflow (10): list_blocks, get_block_schema, list_types, get_workflow, validate_workflow, write_workflow, run_workflow, cancel_run, get_run_status, finish_ai_block
- authoring (5): read_block_source, list_block_examples, scaffold_block, reload_blocks, run_block_tests
- inspection (7): get_block_output, inspect_data, preview_data, get_lineage, get_block_config, update_block_config, get_block_logs
- qa (4): search_docs, get_doc, list_data, get_project_info

CLAUDE.md/AGENTS.md template references tools by names that match the live catalog (verified `grep -E "mcp__scieasy__\w+" templates/claude_agents_md.md` against `list_tools()` names — all subset).

Skill catalog cross-reference: every tool referenced in skills exists in `list_tools()` output. NO orphan tools or stale names. **EXCEPT** the `run_block_tests` arg-name drift documented in §3.4.

## Known bugs sweep

### PR #1064 (`accepted_types=[T]` fix, issue #1063) — OPEN, NOT YET ON track/adr-040

Verified `gh pr view 1064`: state=OPEN, baseRefName=`track/adr-040`, mergedAt=null. Single commit `043cc5b` not yet merged.

The scaffold template at `tools_authoring.py:271,278` still writes:
```
InputPort(name='in', type=DataObject, required=True),  # broken
```

Until #1064 lands, every block scaffolded via MCP with explicit `input_ports` / `output_ports` dicts ships syntactically broken code. ScaffoldBlockResult.warnings still fires (logic is independent), but the file is unusable as-is.

**Manager action**: merge PR #1064 into `track/adr-040` before final ship. CI on #1064 is mostly green (Test 3.11/3.13/Lint/Type all pass); only `Verify Workflow Compliance` fails (5s — likely the changelog format check). Minor.

### Residual Codex findings from prior PRs

| PR | Severity | Finding | Status |
|---|---|---|---|
| #1053 | P1 | system_prompt event-loop deadlock via `run_coroutine_threadsafe(loop, loop)` | "accepted" — fixed in #1058 |
| #1053 | P1 | tools_inspection preview cap bypass | "accepted" — fixed in #1058 |
| #1053 | P2 | tools_qa partial-sort | "accepted" — fixed in #1058 |
| #1058 | P1 | ThreadPoolExecutor shutdown(wait=True) still blocks past timeout | **NOT FIXED** (see §3.1) |
| #1047 | P1 | MultiEdit missing from hook matchers | Fixed (verified `_build_settings_json`) |
| #1047 | P1 | No-space redirect bypasses block-write detection | Fixed (regex now `>>?\s*`) |
| #1049 | P2 | `_find_skill_source` legacy walk-up returns stale tree | NOT FIXED; dormant after Skills track merged (repo `skills/scieasy/` has no SKILL.md, so fallback errors out instead of returning stale content) |
| #1054 | P2 | `run_block_tests` documented `block_path=` (skill blueprint) | NOT FIXED — skill content shipped with same bug (PR #1059) |
| #1054 | P2 | `validate_workflow` documented shape wrong | NOT FIXED — skill content shipped with same drift |
| #1054 | P2 | `get_run_status` documented shape wrong | NOT FIXED — skill content shipped with same drift |
| #1059 | P1 | `scieasy-write-block` skill uses `block_path=` | **NOT FIXED** (see §3.4) |
| #1059 | P2 | `scieasy-build-workflow` skill describes `validate_workflow` wrong | **NOT FIXED** (see §3.4) |
| #1059 | P2 | `scieasy-debug-run` skill describes `get_run_status` wrong | **NOT FIXED** (see §3.4) |

### Test-coverage holes

90 tests still skipped under `pytestmark = pytest.mark.skip(...)` at module scope:

```
tests/ai/test_mcp_server_skeleton.py            (37 tests skipped)
tests/ai/test_mcp_tools_authoring.py            (10 tests skipped)
tests/ai/test_mcp_tools_inspection.py           (17 tests skipped)
tests/ai/test_mcp_tools_qa.py                   (11 tests skipped)
tests/ai/test_mcp_tools_disk_integration.py     (13 tests skipped)
```

Each carries reason: `"S40a skeleton — tool bodies are NotImplementedError stubs. TODO(#1012): I40a Phase 2a restores."`. I40a Phase 2a is the merged PR #1053 — but it did NOT restore these. Per PR #1053 body's own "Out of scope" disclaimer: "Module-level skips on test_mcp_tools_authoring.py / test_mcp_tools_inspection.py / test_mcp_tools_qa.py / test_mcp_tools_disk_integration.py / test_mcp_server_skeleton.py remain — these need full async + Pydantic-envelope rewrites that A40-impl is better positioned to drive consistently."

A40-impl (Phase 2a.5 audit) has not been dispatched. As a result, **~90 per-tool behavior tests are not enforcing any contract on the merged FastMCP migration**. The 10 FastMCP parity tests + 16 ported workflow tests carry the load, but per-tool deep coverage is absent.

**P2** — manager should dispatch A40-impl batch audit + a F40-test-restoration fix agent before Phase 4 e2e.

## Findings (P1 / P2 / P3)

### P1 (release-blocking or near-release-blocking)

1. **`hook_enforce_concrete_port_types.py` is dead code** — AST scans for `PortSpec` calls; real Block contract uses `InputPort(accepted_types=[...])` / `OutputPort(...)`. The §3.6 L5 port-type enforcement layer NEVER fires on real block files. **Fix**: rewrite the AST scan to target `InputPort`/`OutputPort` with `accepted_types=[DataObject]` / `accepted_types=[]` / missing-`accepted_types`. (Hook script source ~50 LOC change.)
2. **PR #1064 (`accepted_types=[T]` scaffold fix) NOT MERGED** — scaffold template at `tools_authoring.py:271,278` still emits `type=<T>` which breaks Block contract. Merge #1064 before ship.
3. **Skill content drift from real Pydantic models** — `scieasy-write-block` teaches `run_block_tests block_path=…` (wrong; real arg is `type_name`); `scieasy-build-workflow` teaches `validate_workflow → {ok, errors, next_step}` (real: `{valid, errors}`); `scieasy-debug-run` teaches top-level `block_states/error` (real: `progress.block_states / errors: list`). Codex flagged all three on PR #1059; not addressed. Agents following these examples will emit invalid MCP calls and mis-read status envelopes. **Fix**: rewrite the four offending sections in a small content-only follow-up PR.
4. **ThreadPoolExecutor deadlock workaround still blocks past timeout** — `system_prompt.py:168-169` `with ThreadPoolExecutor(...) as pool: pool.submit(...).result(timeout=5.0)`. Context-manager exit calls `shutdown(wait=True)` which blocks waiting for a hung worker. The 5s timeout does not guarantee fail-fast in the async-PTY-spawn path. Codex flagged on PR #1058; not addressed. **Fix**: replace with explicit `try/except: pool.shutdown(wait=False, cancel_futures=True); raise`.

### P2 (worth fixing but not release-blocking)

1. **Version-marker write on partial provisioning failure** — `_orchestrate.py:130-148` writes `.scieasy-provision-version` even when sub-steps reported `result.failed`. Future OQ-1 upgrade logic will mis-trust the marker. **Fix**: only write marker when `result.failed == []`, or write a per-step manifest.
2. **90 per-tool tests still skipped at module scope** — `test_mcp_tools_authoring.py` / `_inspection.py` / `_qa.py` / `_disk_integration.py` / `_server_skeleton.py` carry `pytestmark = pytest.mark.skip(...)` referencing I40a as the restorer. I40a's own PR body acknowledges the deferral. Per-tool behavior coverage is currently absent. **Fix**: dispatch a F40-test-restoration agent to port the skipped tests to the async/Pydantic shape before Phase 4 e2e.
3. **`protect_workflow_yaml.py` substring match** — `re.search(r"workflows/.*\.ya?ml$")` against `notworkflows-old/x.yaml` matches (false positive). Low-impact (such paths probably do want MCP-mediated edits anyway), but a `re.search(r"(?:^|/)workflows/[^/]+\.ya?ml$")` would be tighter.
4. **`_find_skill_source` legacy fallback** — Codex P2 on PR #1049. Currently dormant (repo-root `skills/scieasy/` has no SKILL.md so the fallback errors out cleanly), but should be removed per TODO #1011 to prevent a future regression.

### P3 (cosmetic / future work)

1. **`project_name` markdown injection** in `_render_project_context` — hostile `project.yaml::project.name` could inject markdown headers into the system prompt. Low-impact in a single-user desktop product; flag as defensive hygiene.
2. **`__init__.py` docstring stale** — `src/scieasy/agent_provisioning/__init__.py:11-13` says "S40c (this skeleton) defines the module shape with NotImplementedError bodies. I40c (Phase 2a, #1013) fills in real implementations." — but the module IS now I40c-implemented. Cosmetic; replace with the production-state description.
3. **`codex_config.toml` template carries `TODO(#1013)` but is essentially documentation-only** — the actual content is `_render_codex_block`-generated. Template content is informational only; consider removing the `TODO(#1013)` marker to reduce noise.

## Recommendation for fix agent / Phase 3.6

Group findings by file scope for parallel fix dispatch:

1. **Hook script rewrite** (P1.1): single fix agent updates `hook_enforce_concrete_port_types.py` AST scan + adds matching unit tests in `tests/agent_provisioning/test_hooks.py`. Scope: ~80 LOC. Branch off `track/adr-040`.
2. **PR #1064 merge** (P1.2): manager merges directly (or asks Codex to bring CI green if Verify-Compliance fails) — no new agent needed.
3. **Skill content corrections** (P1.3): single content-only agent rewrites the 3 affected skill files + the underlying `claude_agents_md.md` template if it cites the same field names. Scope: docs-only, ~30 LOC. Branch off `track/adr-040`.
4. **system_prompt ThreadPoolExecutor fix** (P1.4): single fix agent replaces the `with` block with `try/except` + explicit shutdown. Scope: ~10 LOC + regression test. Branch off `track/adr-040`.
5. **Version-marker partial-failure fix** (P2.1) + per-tool test restoration (P2.2): batch these into one fix agent if scope permits, or split. P2.2 is the larger (~90 tests to port to async); could be split off as F40-test-restoration with its own PR.

Codex P1/P2 reconcile cap (manager memory rule): one round per agent. PR #1064 should also be re-CI'd post-merge into `track/adr-040`.

**Total Phase 3.6 fix dispatch estimate**: 4 fix agents (one per finding cluster), all read-only to existing files except the hook rewrite + skill content. Expected merge order: P1.2 (manager) → P1.1, P1.3, P1.4 (parallel) → P2.1 + P2.2 (parallel or batched).

### Status of accepted_types fix (#1064)

PR #1064 is open against `track/adr-040`. CI: 7/8 checks passing (Verify Workflow Compliance fails at 5s — likely the gate-step changelog check tripped because the PR is for an opened-mid-cascade issue). Single commit `043cc5b`. **Recommendation**: manager merge immediately after Verify-Compliance unblocked (typically a CHANGELOG line addition). Once merged into `track/adr-040`, the §3.2a hook rewrite (P1.1) can land on top — both touch port-handling code paths and benefit from co-review.
