# A1: ADR-040 completeness + bugs + edge cases audit

**Date**: 2026-05-16
**Phase**: 3 (parallel audits)
**Auditor**: A1 (this report). Sibling auditors: A2 (MCP wiring + cross-doc consistency), A3 (agent-POV prompt/skill).
**Tracking branch**: `track/adr-040` @ `949476f` (after I40b merge #1059).
**Cascade umbrella**: #1011.
**Sub-issue**: #1060.
**Read-only**. No source or contract files modified by this PR.

---

## Summary

**Verdict**: **pass-with-fixes**.

The four-layer reliability stack (FastMCP migration, project-context injection, multi-skill split, prod-env provisioning + hooks + Codex MCP config) is implemented at the ADR-spec level and tracks the §3.x decision matrix faithfully. CI is green on every merged PR. However, three classes of issue should be fixed before the cascade ships:

1. **PR #1059 (I40b skill content) merged 3 unreconciled Codex findings (1×P1 + 2×P2) — confirmed in this audit by direct code/skill cross-reference.** The P1 (`run_block_tests` example uses `block_path` instead of `type_name`) will cause every agent following the `scieasy-write-block` skill to fail the test-run step. Manager's "A3 will catch them" deferral is exactly the kind of override that overnight-merge protocol forbids — A1 is recording this so the dispatcher can fix in-PR before ship, not after.
2. **9 naked `TODO[^(]` matches survive in `src/`** — violates the cascade ship-gate audit signal `grep -rn "TODO[^(]" src/` returns ZERO. Three of those are scaffold-template placeholders (legitimate, see B/F below); six are pre-existing tech debt that pre-date CLAUDE.md §7.6. The cascade should either retag them in this branch or explicitly exempt them.
3. **`scaffold_block` accepts a `category` argument but ignores it** in the template rendering path. The argument is documented as required (no default) but has no observable effect.

There are no architectural P1s. Implementation matches ADR §3.1–3.10 in every section. Below: per-dimension detail with file:line citations.

---

## A. ADR §3.x verbatim compliance

Per-section coverage against the implementation on `track/adr-040`.

### §3.1 FastMCP migration

- OK `fastmcp>=3.1,<4` declared in `pyproject.toml`.
- OK `src/scieasy/ai/agent/mcp/server.py` is FastMCP-backed: module-level `mcp: FastMCP = FastMCP(name="scieasy-mcp", version="0.1.0")` at `server.py:51`. The `MCPServer` lifecycle wrapper (`server.py:67-139`) preserves the public surface (`start`, `stop`, `serve`, `port`, `dispatch`, `_handle_client`) so `api/app.py::lifespan` and `mcp-bridge` don't need to change. ADR §3.1 fully delivered.
- OK `tools/list` enumerates from `await mcp.list_tools()` (`server.py:208-230`); `inputSchema` is generated from FastMCP `entry.parameters` (NOT the old `additionalProperties: true` stub).
- OK `_registry.py` deleted. Confirmed via `ls src/scieasy/ai/agent/mcp/` — no `_registry.py` present. No code path imports it.
- OK `compose_system_prompt._render_tool_catalog` reads FastMCP `list_tools()` (`system_prompt.py:163-211`). Codex P1 from PR #1053 (event-loop deadlock) addressed with thread-pool executor pattern at `system_prompt.py:171-186`. Properly reconciled.
- OK `finish_ai_block` ported (`tools_workflow.py:787+`). Returns `FinishAIBlockOK | FinishAIBlockError` Pydantic union per ADR §3.1.
- **Tool count**: confirmed **26** (5+7+4+10) by `grep -c "^@mcp.tool"` across all 4 tool modules. Matches ADR §2.4 / §5.1.

### §3.2 Tool descriptions + `next_step` content rewrite

- OK Every write-class tool result model carries `next_step: str` with a meaningful default. 8 write tools, 8 `next_step` fields:
  - `WriteWorkflowResult.next_step` → `validate_workflow` (tools_workflow.py:264)
  - `RunWorkflowResult.next_step` → `get_run_status` poll (tools_workflow.py:275)
  - `CancelRunResult.next_step` → confirm via `get_run_status` (tools_workflow.py:286)
  - `FinishAIBlockOK.next_step` → describes downstream watcher (tools_workflow.py:320)
  - `ScaffoldBlockResult.next_step` → edit + `reload_blocks` (tools_authoring.py:72)
  - `ReloadBlocksResult.next_step` → `list_blocks` + `run_block_tests` (tools_authoring.py:88)
  - `RunBlockTestsResult.next_step` → diagnose returncode (tools_authoring.py:105)
  - `UpdateBlockConfigResult.next_step` → confirm via `get_block_config` (tools_inspection.py:137)
- OK Docstring style — imperative first line, "Use when … / Do NOT use to …" sections present on the 8 tools spot-checked. Style guide adherence is consistent.

### §3.2a `warnings: list[str]` soft validation

- OK `ScaffoldBlockResult.warnings: list[str]` declared (tools_authoring.py:64-70). Field description quotes ADR-040 §3.2a verbatim.
- OK Detection logic at `tools_authoring.py:359-381`: generic-`DataObject` and unregistered-type warnings appended per port direction.
- WARN **Minor (P3)**: the `scaffold_block` return statement at `tools_authoring.py:392-396` does NOT pass `next_step=...`, so the field falls back to the Pydantic `default=`. Acceptable but defensive recommendation to pass explicit.
- WARN **Functional bug — P2**: `category: str` declared as required positional arg (tools_authoring.py:300) but **NEVER used inside the function body**. The `_SCAFFOLD_TEMPLATE.format(...)` call at `tools_authoring.py:385` only consumes `class_name`, `input_ports_block`, `output_ports_block`. Agents picking the wrong category get happy path with no warning AND no effect. Recommended fix: either route `category` into template selection (the documented intent), or drop the argument.
- OK `TODO(#1016)` companion (hard BlockRegistry rejection) present at `tools_authoring.py:360`, properly formed per CLAUDE.md §7.6.

### §3.3 Per-project dynamic context injection (closes #825)

- OK `_render_project_context(project_dir)` implemented at `system_prompt.py:213-321`. Field sources match the ADR §3.3 table verbatim.
- OK Performance budget claim: `os.scandir` lazy iteration is O(n); sort is O(n log n). At 10K workflows well under 100 ms.
- WARN **Cosmetic (P3)**: `_format_age` returns `"just now"` only for `seconds_ago < 0`. For `0 ≤ seconds_ago < 60` it returns `"0m ago"`. Minor.
- OK Splice via marker pair with stale-marker fallback that warns + appends — sound degradation.

### §3.4 Multi-skill split + wheel packaging

- OK `src/scieasy/_skills/scieasy/` exists with all 6 skill subdirectories.
- OK `_load_skill_md` switched to `importlib.resources` PRIMARY with legacy walk-up fallback (TODO(#1012)-tagged).
- OK `pyproject.toml [tool.setuptools.package-data]` includes `_skills/scieasy/**/*.md` and `agent_provisioning/templates/**/*`.
- OK Each task skill has YAML frontmatter triggering progressive disclosure.
- OK `scieasy-write-block` opens with the #875 block-reuse mandate verbatim.
- OK `tests/packaging/test_wheel_skills.py` flipped from skip to passing.

### §3.5 Prod-env CLAUDE.md + AGENTS.md provisioning

- OK Template at `src/scieasy/agent_provisioning/templates/claude_agents_md.md` (~60 LOC, content authored).
- OK `claude_agents_md.py::write_claude_agents_md` writes both files verbatim from the same template (identical content per ADR §3.5).
- OK `force=False` semantics preserve user customizations.

### §3.6 Project-scoped hooks

- OK `<project>/.claude/settings.json` schema matches ADR §3.6 structure (PreToolUse + PostToolUse arrays).
- OK All 6 hook scripts present + executable on POSIX.
- OK **MultiEdit coverage** (Codex P1 on PR #1047): every Edit|Write matcher includes `MultiEdit`. Verified at `hooks.py:104,106,117`. Codex P1 properly reconciled.
- OK **No-space redirect coverage** (Codex P1 on PR #1047): regex at `hook_enforce_list_blocks_before_block_write.py:36` is `r"(?:>>?\s*|\b(?:tee|cp\s+\S+)\s+)\S*blocks/\S+\.py"` — `>>?\s*` matches zero-or-more whitespace, so `echo x >blocks/new.py` IS caught.

### §3.7 Codex MCP provisioning

- OK `codex_config.py::write_codex_config` writes `<project>/.codex/config.toml` via shared `install._render_codex_block`.
- OK Output byte-identical to `scieasy install --target codex --scope project`.
- WARN **Minor (P3)**: the template file `templates/codex_config.toml` is referenced by comments but **never actually loaded** at runtime. Documentation-only.

### §3.8 Lifecycle auto-installation

- OK `install_project_agent_assets(project_dir, force=False) -> ProvisionResult` defined at `_orchestrate.py:64-149`.
- OK Wired at all 3 entry points: `ApiRuntime.create_project` (`api/runtime.py:612-631`), `ApiRuntime.open_project` (`api/runtime.py:725-743`), `cli/main.py::init` (lines 182-199).
- OK Degraded-mode contract per ADR §7 "non-fatal".
- OK `SCIEASY_PROVISION_VERSION = "0.1.0"` + marker file.
- WARN **Edge case (P2)**: upgrade flow NOT implemented — TODO(#1011)-tagged. Today: stale marker means no signal. Recommend `logger.info` on version drift.

### §3.9 Codex skill cross-install

- OK `_install_skill` cross-installs to both `.claude/skills/scieasy/` AND `.agents/skills/scieasy/` per scope.
- OK `_remove_skill` symmetric across both trees.
- OK `_install_codex` supports `--scope project`; the "force user-scope for codex" fallback removed.
- WARN **Codex P2 on PR #1049 NOT addressed**: `_find_skill_source` walk-up at `install.py:461-469` still looks at `parent / "skills" / MCP_SERVER_NAME` only — NOT at relocated `parent / "src" / "scieasy" / "_skills" / "scieasy"`.

### §3.10 Out of scope (explicit)

- OK Dev environment changes excluded — verified no edits to repo-root `CLAUDE.md`.
- OK Per-turn re-composition not attempted.
- OK Empirical eval framework not in scope.
- OK Codex hook coverage explicitly noted as upstream gap.

---

## B. Pydantic return model audit

Per-tool walkthrough — 26 tools, every return model, MCP wire round-trip.

### tools_workflow.py (10 tools)

| Tool | Return model | next_step? | Notes |
|---|---|---|---|
| `list_blocks` | `list[BlockSpecEnvelope]` | n/a (read) | List wrapper; envelope serialises correctly |
| `get_block_schema` | `BlockSchemaResult` | n/a | OK |
| `list_types` | `ListTypesResult` | n/a | OK |
| `get_workflow` | `WorkflowDefinitionEnvelope` | n/a | OK |
| `validate_workflow` | `ValidateWorkflowResult` | n/a | Shape: `{valid: bool, errors: list[str]}`. **Skill teaches wrong shape — see G** |
| `write_workflow` | `WriteWorkflowResult` | yes | OK |
| `run_workflow` | `RunWorkflowResult` | yes | OK |
| `cancel_run` | `CancelRunResult` | yes | OK |
| `get_run_status` | `GetRunStatusResult` | n/a | Shape: `{run_id, state, progress: {block_states: {...}}, errors: list[BlockErrorEntry]}`. **Skill teaches wrong shape — see G** |
| `finish_ai_block` | `FinishAIBlockOK \| FinishAIBlockError` | yes on OK | Union with `status` discriminator — FastMCP handles both variants |

### tools_authoring.py (5 tools)

| Tool | Return model | next_step? | warnings? | Notes |
|---|---|---|---|---|
| `read_block_source` | `ReadBlockSourceResult` | n/a | n/a | OK |
| `list_block_examples` | `list[BlockExampleEntry]` | n/a | n/a | OK |
| `scaffold_block` | `ScaffoldBlockResult` | yes (default) | yes | Unused `category` arg — see P2 |
| `reload_blocks` | `ReloadBlocksResult` | yes | n/a | OK |
| `run_block_tests` | `RunBlockTestsResult` | yes | n/a | OK at MCP layer. **Skill teaches wrong arg name — see G** |

### tools_inspection.py (7 tools)

All return correctly-typed `BaseModel`. `preview_data` chunked-read fix (Codex P1 PR #1053) addressed for DataFrame path; array path not deeply verified — A2 territory.

### tools_qa.py (4 tools)

All return correctly-typed `BaseModel`. `search_docs` sort-by-score (Codex P2 PR #1053) properly addressed at `tools_qa.py:178-185`.

**Pydantic verdict**: schemas are uniformly strict (no `additionalProperties=True` shortcuts). FastMCP auto-generates `inputSchema` from type hints. No P1 issues at the Pydantic / FastMCP wire level.

---

## C. Hook script edge cases

### `hook_deny_scieasy_cli.py` (PreToolUse / Bash)

- Regex: `r"^\s*(?:\S*/)?scieasy(?:\s|$)"`.
- OK Catches: `scieasy run`, `  scieasy run`, `/usr/local/bin/scieasy run`.
- BAD **P3 bypass**: `C:\Program Files\scieasy.EXE run` — `\S*/` doesn't match backslashes. Windows-path-prefixed invocation slips through. Low real-world impact (Claude Code uses POSIX paths in Bash on Windows).
- BAD **P2 bypass**: `env SCIEASY_DEV=1 scieasy run` and `cmd1 && scieasy run` — `^\s*` anchors at line start; preamble of `env ...` or `cmd1 && ` consumes positions 0-N, and `scieasy` no longer at start. Fix: regex `r"(?:^|\s|;|&|\|)\s*(?:\S*/)?scieasy(?:\s|$)"`.
- OK Exit code semantics correct (exit 2 on match).

### `hook_protect_workflow_yaml.py` (PreToolUse / Edit|Write|MultiEdit)

- Regex: `r"workflows/.*\.ya?ml$"`.
- OK Path normalization for Windows (`replace("\\", "/")`).
- BAD **P2**: regex unanchored — matches `archived_workflows/old.yaml`, `my_workflows/foo.yaml`. False positives on user directories named `*workflows*`. Fix: `r"(?:^|/)workflows/.*\.ya?ml$"`.

### `hook_enforce_list_blocks_before_block_write.py` (PreToolUse / multi-matcher)

- OK Multi-tool detection covers `scaffold_block` always-on, Edit/Write/MultiEdit anchored `blocks/*.py`, and Bash redirect/tee/cp patterns.
- OK No-space redirect `echo x >blocks/new.py` caught (Codex P1 reconciled).
- OK Documented bypasses (Python `-c`, `mv`, here-doc indirection) explicit in hook docstring + TODO(#1015) Layer 7 ACL placeholder.
- OK Session-marker path with `session_id` sanitization (line 99).
- OK Fail-closed: no session_id / no CLAUDE_PROJECT_DIR → marker `None` → block.
- OK No race (PreToolUse and PostToolUse serial in agent turn).
- WARN **P3**: cleanup of stale `.scieasy/.session-state/<old_session_id>/` directories on `open_project` NOT implemented. ADR §3.6 mentioned 7-day prune; practical impact negligible (empty marker files).

### `hook_mark_list_blocks_called.py` (PostToolUse / list_blocks)

- OK Idempotent (`mkdir exist_ok=True + .touch()`).
- OK Silent failure (PostToolUse can't block).
- OK Sanitizes session_id same as PreToolUse partner.

### `hook_remind_poll_status.py` (PostToolUse / run_workflow)

- OK Always exit 0.
- OK Includes `run_id` hint when available in `tool_response`.

### `hook_enforce_concrete_port_types.py` (PostToolUse / Edit|Write|MultiEdit|scaffold_block)

- OK AST parse with SyntaxError tolerance.
- OK Detects `PortSpec(...)` and `<module>.PortSpec(...)` call forms.
- OK Detects `type="DataObject"` (Constant) and bare `type=DataObject` (Name).
- BAD **P2**: misses `PortSpec(type=core.DataObject)` (`ast.Attribute` form). Real patterns: `from scieasy.core.types import DataObject; ...`. Fix: extend detection to `ast.Attribute` where `attr == "DataObject"`.
- BAD **P3**: aliased import `from ... import DataObject as DO` escapes. Bad-faith author bypass; not a real-world agent concern.
- OK `TODO(#1013)` for live TypeRegistry lookup properly tagged.

---

## D. `_render_project_context` edge cases

Verified by reading `system_prompt.py:213-321`:

| Scenario | Behavior | Verdict |
|---|---|---|
| 0 workflows | `workflow_count=0`; no recently-modified section | OK |
| 10000 workflows | <100ms (os.scandir lazy, O(n log n) sort) | OK Plausible |
| Corrupt git repo | Skip git section (both subprocess returncodes guarded) | OK |
| Non-git project | Skip git section (`.git/` existence check) | OK |
| Unicode project_name | Render verbatim via f-string | OK |
| Project name with backticks | Renders literally (no MD interpretation in prompt) | OK |
| mtime skew (future > now) | `_format_age` returns "just now" for negative | OK |
| BlockRegistry empty | Skip "Installed block plugins" line | OK |
| `project.yaml` missing | Falls back to `project_dir.name` | OK |
| `project.yaml` malformed | Caught at line 252 → dir-name fallback | OK |
| `project_dir = None` | Returns "No active SciEasy project" message | OK |
| Permission denied on workflows/ | OSError caught → 0 workflows | OK |

**No P1/P2 findings.** Only cosmetic `_format_age` zero-handling note (P3).

---

## E. `install_project_agent_assets` edge cases

| Scenario | Behavior | Verdict |
|---|---|---|
| Fresh project | All assets written; `ProvisionResult.written` ~17 entries | OK |
| Existing user-edited file | Preserved (`force=False`) | OK |
| Missing parent dir | `mkdir(parents=True, exist_ok=True)` defensive | OK |
| Permission denied | Caught; logged WARNING; sub-step continues; project opens | OK |
| Version-marker drift | Currently no detection — TODO(#1011) | WARN **P2** — recommend `logger.info` on version mismatch |
| Partial install (2/6 fail) | No rollback; recorded; idempotent top-up retries on next open | OK |
| Concurrent calls (race) | `mkdir exist_ok` safe; last writer wins; content identical → observably correct | OK |
| Symlink at destination | Follows; force=False preserves | OK |
| Read-only FS | First mkdir raises; orchestrator catches; project opens (ADR §7) | OK |
| Skill-source missing entirely | `_read_skill_source` returns placeholder with TODO(#1013) | OK Doesn't crash |
| `_render_codex_block` import failure | Local import → ImportError → orchestrator catches | OK |

**No P1 findings.** P2 on stale-version logging.

---

## F. TODO audit

`grep -rn "TODO[^(]" src/` — should return ZERO per checklist acceptance criteria. Returns **9 violations**:

- **`tools_authoring.py:239,242,256`**: inside `_SCAFFOLD_TEMPLATE` triple-quoted string — content WRITTEN INTO user-authored block files for the user to fill in. **Legitimate template content**, not project tech debt. **P3** — reword to `# TODO(scaffold-template):` or exclude path from audit grep.
- **`cli/templates/block_package/blocks.py.tpl:61`**: same — user-facing template. **Legitimate**. **P3**.
- **6 pre-existing tech debt** (pre-date CLAUDE.md §7.6 added 2026-05-16 in PR #1007):
  - `blocks/app/watcher.py:8`
  - `blocks/process/builtins/merge.py:70`
  - `blocks/subworkflow/subworkflow_block.py:38` (carries `#890` ref but not `TODO(#890):` form)
  - `cli/templates/block_package/blocks.py.tpl:61` (above)
  - `utils/logging.py:8` (carries `#827` ref but not in tagged form)
  - `utils/wrapping.py:14`
  - **P2** for cascade ship-gate: retag in this cascade OR document explicit exemption in checklist "Out-of-scope" section.

`grep -rn "TODO(#" src/` — verified 14 entries; spot-checked tracking refs:

- `#1011`, `#1012`, `#1013`, `#1015`, `#1016` — opened by manager Phase 0.4. Valid.
- `#732`: open, "Wire workflow-versioning lock". Valid.
- `#827`: open, structured-logging followup. Valid.

All `TODO(#NNNN)` references resolve to real, open issues. OK.

---

## G. Codex P1/P2 across all merged PRs

| PR | Findings | Disposition |
|---|---|---|
| #1027 (S40b skeleton) | None | OK |
| #1028 (S40d skeleton) | None | OK |
| #1029 (S40c skeleton) | None | OK |
| #1030 (S40a skeleton) | 2 P1 — fixed in same PR via manager hotfix per drift-log | OK Reconciled |
| #1034 (A40-skel report) | None | OK |
| #1042 (hook regex generalisation) | None | OK |
| #1043 (docs corrective sweep) | None on review; **1 CI red** (Workflow Gate Check). Merged anyway. | WARN P3 — bypassed CI gate; docs-only |
| #1047 (I40c provisioning) | 2 P1: MultiEdit matcher + no-space redirect | OK Both addressed in-PR |
| #1049 (I40d install) | 1 P2: fallback skill source pointer | WARN NOT addressed (P2.6) |
| #1053 (I40a FastMCP) | 2 P1 + 1 P2: event-loop, preview cap, search_docs ranking | OK All addressed |
| #1054 (Phase 2b research) | None | OK |
| #1058 (orphaned Codex reconcile) | None | OK |
| **#1059 (I40b skill content)** | **1 P1 + 2 P2** | **NOT addressed — see below** |

### PR #1059 unreconciled findings — confirmed P1 + 2 P2

Manager merged PR #1059 with rationale "A3 will catch them" — that defers fix latency, doesn't prevent shipping a known bug. Overnight-merge protocol per `feedback_audit_p1_override` and `feedback_wait_for_agent_done_before_merge` requires Codex P1/P2 in-PR reconcile.

**Confirmed by direct code/skill comparison**:

1. **P1 — `scieasy-write-block/SKILL.md:264` teaches wrong arg name `block_path`**:
   - Skill says: `mcp__scieasy__run_block_tests block_path=blocks/threshold_simple.py`
   - Code requires (`tools_authoring.py:431`): `async def run_block_tests(type_name: str = Field(...))`
   - **Impact**: every agent following this skill will call with `block_path=...`. FastMCP's strict `inputSchema` will reject — `unexpected keyword argument 'block_path'` or `type_name` missing. The *exact* failure mode the §3.2 + skill-as-canonical-teaching paradigm was meant to prevent.

2. **P2 — `scieasy-build-workflow/SKILL.md:262` documents stale `validate_workflow` envelope**:
   - Skill says: `validate_workflow returns {ok: bool, errors: list[ValidationError], next_step: str}`
   - Code returns (`tools_workflow.py:251`): `ValidateWorkflowResult(valid: bool, errors: list[str])` — no `ok`, no `next_step`, errors are plain strings.
   - **Impact**: agent references `result.ok` (doesn't exist) and `errors[i].message` (each is plain str). Silent mis-parse.

3. **P2 — `scieasy-debug-run/SKILL.md:38-55` documents stale `get_run_status` envelope**:
   - Skill says (flat): `{state, block_states, started_at, finished_at, error: str}`
   - Code returns (`tools_workflow.py:300`): `GetRunStatusResult(run_id, state, progress: dict, errors: list[BlockErrorEntry])` — block_states nested under `progress`, errors is a list of tracebacks (plural).
   - **Impact**: agent reads `result.block_states` (KeyError/AttributeError). Won't see `result.progress["block_states"]`. Won't see the `errors: list[BlockErrorEntry]` tracebacks. Diagnostic flow silently misses real data.

**Recommended action**: manager pushes ~30-line fix across the 3 skill files directly to `track/adr-040` (small-fix rule per playbook), OR dispatches a focused fix agent. Either way: **before cascade ship**, not after.

A40-skill audit (Phase 2c.5) should have caught these; checklist has it as `[ ]` — appears skipped or ran on an earlier draft. Drift log entry recommended.

---

## H. Acceptance criteria status

Cross-checked against `docs/planning/adr-040-checklist.md` "Acceptance criteria":

| Criterion | Status | Notes |
|---|---|---|
| All Phase 0-3.6 checkboxes ticked | WARN Many `[ ]` rows remain unchecked despite merges; **P2** checklist drift |
| Drift log resolved | OK 5 entries with Resolution lines |
| All 4 tracking-branch CI green | OK except PR #1043 (docs corrective sweep) 1 red |
| All Codex P1/P2 resolved | BAD 1 P1 + 2 P2 on #1059, 1 P2 on #1049 |
| `grep -rn "TODO[^(]" src/` → ZERO | BAD 9 matches (see F) |
| Every of 26 MCP tools enumerable | OK Verified |
| Fresh GUI project has all assets | (Phase 4 territory — untested here) |
| Phase 4: 13/14 cells PASS | (Phase 4 not yet run) |
| CHANGELOG mandatory metadata | OK Verified per ADR-040 entry |

---

## Findings (P1 — must fix; P2 — should fix; P3 — nice to have)

### P1 (3 — block ship)

- **P1.1**: `scieasy-write-block/SKILL.md:264` teaches `block_path=...` for `run_block_tests`; actual arg is `type_name`. Affected: `src/scieasy/_skills/scieasy/scieasy-write-block/SKILL.md`. Fix: replace argument name in example + surrounding prose.
- **P1.2**: `scieasy-build-workflow/SKILL.md:262` documents stale `validate_workflow` envelope `{ok, errors[ValidationError], next_step}`; actual is `{valid: bool, errors: list[str]}`. Affected: `src/scieasy/_skills/scieasy/scieasy-build-workflow/SKILL.md`.
- **P1.3**: `scieasy-debug-run/SKILL.md:38-55` documents stale `get_run_status` envelope (flat block_states, started_at/finished_at, error: str); actual has `progress.block_states` nested + `errors: list[BlockErrorEntry]`. Affected: `src/scieasy/_skills/scieasy/scieasy-debug-run/SKILL.md`.

### P2 (6 — should fix before ship)

- **P2.1**: `scaffold_block.category` arg accepted but unused. `src/scieasy/ai/agent/mcp/tools_authoring.py:299-401`. Fix: route into template selection or drop.
- **P2.2**: `hook_protect_workflow_yaml.py` regex unanchored → false positives on `*workflows/*`. Fix: `r"(?:^|/)workflows/.*\.ya?ml$"`.
- **P2.3**: `hook_deny_scieasy_cli.py` misses `env VAR=v scieasy ...` and `cmd && scieasy ...`. Fix: regex `r"(?:^|\s|;|&|\|)\s*..."` or shlex-parse argv.
- **P2.4**: `hook_enforce_concrete_port_types.py` misses `PortSpec(type=core.DataObject)` (Attribute). Fix: extend detection to `ast.Attribute attr=="DataObject"`.
- **P2.5**: 6 pre-existing naked TODOs in `src/`. Retag OR document exemption in checklist.
- **P2.6**: PR #1049 Codex P2 (`_find_skill_source` walk-up missing relocated path). 2-line `install.py` fix.

### P3 (8 — nice to have, accepted as-is)

- **P3.1**: `_format_age` returns `"0m ago"` for `0 ≤ s < 60` (cosmetic).
- **P3.2**: `scaffold_block` doesn't pass explicit `next_step=` in return (relies on default; defensive recommendation).
- **P3.3**: 3 scaffold-template TODOs (legitimate user-template content; reword or exclude from grep).
- **P3.4**: PR #1043 merged with red CI (docs-only; manager discretion).
- **P3.5**: No cleanup of stale `.scieasy/.session-state/<old>/` dirs (negligible disk impact).
- **P3.6**: `templates/codex_config.toml` is documentation-only — never loaded at runtime.
- **P3.7**: Checklist drift — many `[ ]` boxes unticked despite merges.
- **P3.8**: Windows-path `C:\...\scieasy.EXE` not caught by `deny_scieasy_cli` regex (low real-world impact).

---

## Recommendation for manager

Ordered fix dispatches BEFORE cascade ships:

1. **(BLOCKING) Fix PR #1059 skill drift — P1.1, P1.2, P1.3.** ~30 lines across 3 skill files. Manager pushes directly per "small ~10 line fix" rule OR dispatches quick fix agent. Land on `track/adr-040`. **Most important action.**
2. **(STRONGLY RECOMMENDED) Fix P2.1 (`scaffold_block.category` unused).** ~10 lines. Visible to every agent authoring a block.
3. **(STRONGLY RECOMMENDED) Fix P2.5 (6 pre-existing naked TODOs).** 5-line retagging OR explicit exemption in checklist. Either approach passes ship-gate audit signal.
4. **(SHOULD) Fix P2.2 + P2.3 + P2.4 (hook regex precision).** ~5 lines each; dispatch as single "hook hardening" fix agent in parallel with P1 work.
5. **(SHOULD) Fix P2.6 (PR #1049 P2).** 2 lines to `install.py` walk-up loop.
6. **(NICE) Tick checklist boxes for actually-done rows (P3.7).** Sweep before cascade ship so checklist = reality.
7. **(DEFERRED) P3.1-P3.6, P3.8** — accepted or follow-up issues.

**Ship readiness verdict**: cascade is **~85% ready**. Skill-content P1s are the only true blockers. Once they land (~30-60 min of work), all remaining items are P2/P3 polish.

**No architecture-level concerns.** The four-layer reliability stack is correctly implemented per ADR §3.1-3.10. The defects are content (skill bodies), discipline (TODO tagging), and hook-regex precision — none require revisiting the ADR.

Sibling A2 and A3 reports will likely confirm or extend findings here. A3 in particular should independently catch the P1.1-P1.3 from an agent-POV simulation; A2 should validate the FastMCP wire serialization and cross-doc consistency claims.
