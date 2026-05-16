# A40-skel: ADR-040 Skeleton Audit Report

> Read-only audit by A40-skel on 2026-05-16. Covers PR #1030 (S40a FastMCP),
> PR #1027 (S40b skill structure), PR #1029 (S40c provisioning),
> PR #1028 (S40d install-parity).
>
> Audit method: per-PR diff inspection + cross-track wiring trace +
> Codex auto-review reconciliation + scope/discipline checks against
> `docs/adr/ADR-040.md` and `docs/planning/adr-040-code-scope.md`.
> Issue: #1033. Gate task: `20260516-183105-a40-skel-adr-040-skeleton-audit`.

## Summary

| PR | Track | Verdict | P1 | P2 | P3 |
|---|---|---|---|---|---|
| #1030 | FastMCP (S40a) | **NEEDS-FIX** | 2 | 2 | 2 |
| #1027 | Skill structure (S40b) | **READY** | 0 | 0 | 1 |
| #1029 | Provisioning (S40c) | **READY** (CI flake on unrelated test) | 0 | 1 | 1 |
| #1028 | Install-parity (S40d) | **READY** | 0 | 1 | 1 |

**Aggregate**: 2 P1, 4 P2, 5 P3. All P1 findings sit on PR #1030 and align
1:1 with the two `chatgpt-codex-connector[bot]` P1 inline comments — both
have direct evidence in PR #1030's CI logs.

---

## Per-PR findings

### PR #1030 (S40a FastMCP)

**Branch**: `feat/issue-1023/adr-040-s40a-fastmcp-skeleton` → `track/adr-040/fastmcp`.
**Size**: +2128 / -2143, 23 changed files. **Mergeability**: `UNSTABLE`.

#### A. Diff verification

Touched files match the FastMCP-track owner-file list in
`docs/planning/adr-040-code-scope.md` §1.1:

- `pyproject.toml` (+1 dep) ✓
- `src/scieasy/ai/agent/mcp/__init__.py` (docstring + re-export) ✓
- `src/scieasy/ai/agent/mcp/_registry.py` **DELETED** ✓ (per ADR §3.1)
- `src/scieasy/ai/agent/mcp/runtime.py` (lifecycle wrapper updates) ✓
- `src/scieasy/ai/agent/mcp/server.py` (rewrite to FastMCP wrapper) ✓
- `src/scieasy/ai/agent/mcp/tools_{authoring,inspection,qa,workflow}.py` (4 tool modules) ✓
- `src/scieasy/ai/agent/system_prompt.py` (rewrite per §3.3) ✓
- 10 test files (1 added: `tests/ai/test_mcp_fastmcp.py`; 9 modified)

No out-of-scope files modified. No frontend, no `core/`, no
`api/runtime.py`, no `cli/install.py`. ✓

#### B. NotImplementedError + TODO compliance

Every stub body in `mcp/server.py`, `system_prompt.py`, and all 4
`tools_*.py` modules raises `NotImplementedError` with detailed
`# TODO(#1012):` comment blocks describing the impl approach. CLAUDE.md
§7.6 form (`TODO(#NNNN): <reason> — Out of scope per <ref>. Followup:
<link>.`) is honoured throughout. Sampled examples:
- `system_prompt.py::_load_skill_md` lines 87-99
- `mcp/server.py::MCPServer.start` lines 167-180
- `mcp/tools_authoring.py::scaffold_block` (extended block explaining
  the §3.2a port-spec arg widening)

Test-side skip pragmas all reference `#1012`. ✓

#### C. Signature contract compliance

- **26 `@mcp.tool()` decorators** — verified count via the per-module
  tool listings (10 + 5 + 7 + 4 = 26). ADR §1 + manifest §1.2
  authoritative count. ✓
- **Pydantic return models** — declared at the top of each tool module
  (`WriteWorkflowResult`, `ScaffoldBlockResult`, `RunWorkflowResult`,
  etc.). `next_step` field present on all write-class models.
  `warnings: list[str]` present on `ScaffoldBlockResult`. ✓
- **`scaffold_block` signature widening (§3.2a + manifest §8.6)** —
  signature now accepts `input_ports: Annotated[dict[str, dict[str, Any]] | None, Field(...)] = None`
  and `output_ports: ...` per ADR §3.2a. Default is `None` (correctly
  avoiding mutable default trap; docstring documents normalisation to
  `{}` inside body). ✓
- **`_MCPPlaceholder` no-op decorator** — placeholder at module scope
  (`server.py:62-92`) returns the wrapped function unchanged so tool
  modules import cleanly without `fastmcp` installed during this S40a
  CI run. Confirmed it does NOT leak into runtime usage — its only
  surface is the decorator API; `list_tools()` itself raises
  `NotImplementedError`.

#### D. CI status

| Check | Status |
|---|---|
| Lint & Format | SUCCESS |
| Type Check | SUCCESS |
| Architecture Tests | SUCCESS |
| Import Contracts | SUCCESS |
| Frontend | SUCCESS |
| Verify Workflow Compliance | SUCCESS |
| **Test (Python 3.11)** | **FAILURE** |
| **Test (Python 3.13)** | **FAILURE** |

CI failures are NOT preexisting flakes — both test runs error out on
the exact NotImplementedError raised by `compose_system_prompt()`
because `_load_skill_md()` now unconditionally raises. The error chain
visible in CI logs:

```
src/scieasy/blocks/ai/ai_block.py:467: RuntimeError
  AIBlock bootstrap failed: cannot write system prompt or MCP config:
  S40a skeleton — importlib.resources skill load lands in I40a Phase 2a.
```

This blast-radius extends from `terminal.py::_write_system_prompt_tempfile`
to `AIBlock` bootstrap — the dispatch explicitly called out
`AIBlock`/`terminal.py` consumers in §1.4 of the manifest.

#### E. Codex auto-review reconciliation

Two P1 inline comments from `chatgpt-codex-connector[bot]`:

1. **P1 — `src/scieasy/ai/agent/mcp/server.py:186` (Restore MCP server startup path)**:
   `MCPServer.start()` raises `NotImplementedError`. `start_inprocess_server`
   (mcp/runtime.py) awaits `server.start()` and `api/app.py` lifespan
   awaits `mcp_server.start()` → standalone `mcp-bridge` crashes
   immediately, FastAPI lifespan silently disables MCP after logging an
   error. Disposition: **ACCEPT — P1**. Cross-references CI failure
   evidence. Manager fix: restore legacy hand-rolled server behavior
   inside `start()` (or guard with a no-op + log line) until I40a wires
   FastMCP, so backend boot + bridge boot both stay live during the
   cascade.

2. **P1 — `src/scieasy/ai/agent/system_prompt.py:113` (Keep system-prompt composition functional)**:
   `compose_system_prompt()` always fails because `_load_skill_md()`
   raises unconditionally. `terminal.py::_write_system_prompt_tempfile`
   and `AIBlock` bootstrap both depend on this helper, so claude/codex
   launches fail before execution. Disposition: **ACCEPT — P1**.
   Confirmed by CI logs. Manager fix: keep legacy walk-up resolver as
   the body and only mark the importlib.resources switch as the future
   change (TODO comment but functional body), OR fall back to
   reading the still-in-tree `skills/scieasy/SKILL.md` until S40b's
   relocated SKILL.md is wired in. Either preserves backward
   compatibility during the skeleton phase.

Per manager note: 0 reviews/comments = passed; PR #1030 has 2 P1
comments — failed Codex review. Per
`feedback_audit_p1_override`: dispatcher MUST fix P1 in-PR (not
defer to followup) per overnight merge protocol.

#### F. Test stub quality

- **9 test files carry module-level `pytestmark = pytest.mark.skip(...)`**:
  `test_finish_ai_block.py`, `test_mcp_server_skeleton.py`,
  `test_mcp_tools_workflow.py`, `test_mcp_tools_authoring.py`,
  `test_mcp_tools_inspection.py`, `test_mcp_tools_qa.py`,
  `test_mcp_tools_disk_integration.py`, `tests/cli/test_mcp_bridge.py`,
  `tests/integration/test_phase2_mcp_end_to_end.py`. The dispatch
  enumerated 3 (`test_mcp_fastmcp.py`, `test_system_prompt.py`,
  `test_mcp_server_skeleton.py`); the agent broadened to 9 because the
  S40a `NotImplementedError` regression in `_load_skill_md` /
  `_render_tool_catalog` would otherwise propagate into every tool
  test. Each skip carries `TODO(#1012)` reason text. **Finding P2 —
  scope discipline**: broader-than-spec skip is a symptom of the
  P1 NotImplementedError problem; fixing P1 likely allows narrowing
  the skip set back to the originally-enumerated 3.

- `tests/ai/test_system_prompt.py` was extended in-place (not
  module-skipped) with FastMCP-shape skipped tests — good shape.
- `tests/ai/test_mcp_fastmcp.py` (new, +76 LOC) scaffolds 7 skipped
  parity tests anchored to ADR-040 §3.1/§3.2/§3.2a contract clauses.
  Docstrings are sufficient for I40a to flip skip→pass without
  re-deriving design. ✓
- `tests/ai/test_finish_ai_block_skeleton.py` correctly converts
  `@pytest.mark.xfail(run=False)` → `@pytest.mark.skip(...)` and
  rewrites registry-shape assertions to `mcp.list_tools()` shape.

#### Findings summary (PR #1030)

| ID | Severity | Location | Finding |
|---|---|---|---|
| F1030-1 | **P1** | `mcp/server.py::MCPServer.start` | NotImplementedError breaks FastAPI lifespan + standalone bridge. Codex flagged. CI evidence. |
| F1030-2 | **P1** | `system_prompt.py::_load_skill_md` | NotImplementedError breaks `compose_system_prompt` → `terminal.py` → `AIBlock` bootstrap. Codex flagged. CI evidence. |
| F1030-3 | P2 | Module-level skips × 9 | Broader than dispatched 3-file scope; reflects the P1 regressions. Should re-narrow after F1030-1/F1030-2 fixes land. |
| F1030-4 | P2 | `mcp/server.py::MCPServer.stop` + `_load_skill_md` companions (`_render_tool_catalog`, `_render_project_context`) | Same pattern: `NotImplementedError` bodies that are reachable from current production callsites. Fix in same pass as F1030-1/F1030-2. |
| F1030-5 | P3 | `mcp/__init__.py` docstring | Updated 25→26 in some prose but `tools_workflow` "10 tools (includes finish_ai_block)" still phrased loosely (manifest §8.5 noted "9 vs 10"). Cosmetic; will normalize in I40a docstring pass. |
| F1030-6 | P3 | `_MCPPlaceholder` | Survives I40a impl phase only if `fastmcp` is unconditionally present; once `fastmcp>=3.1,<4` is installed (added to deps in this PR), the placeholder becomes dead code. Track for I40a cleanup. |

---

### PR #1027 (S40b skill structure)

**Branch**: `feat/issue-1024/adr-040-s40b-skill-structure` → `track/adr-040/skills` (note: base IS the skills tracking branch despite dispatch checklist line 278 saying "off main"; tracking branch was set up retroactively per checklist §0.5 Skills row).
**Size**: +119 / -1, 9 files. **Mergeability**: `CLEAN`.

#### A. Diff verification

| File | Status | Notes |
|---|---|---|
| `CHANGELOG.md` | +1 | Entry added |
| `pyproject.toml` | +1 / -1 | `[tool.setuptools.package-data]` widened to include `_skills/scieasy/**/*.md`. Surgical edit; no other sections touched. ✓ |
| `src/scieasy/_skills/scieasy/SKILL.md` | NEW | 18 LOC; frontmatter `name: scieasy`, identity stub, `<!-- project_context:begin/end -->` markers present ✓ |
| `src/scieasy/_skills/scieasy/scieasy-{build-workflow,debug-run,inspect-data,project-qa,write-block}/SKILL.md` | NEW × 5 | 14-17 LOC each; frontmatter `name` + `description` populated ✓ |
| `tests/packaging/test_wheel_skills.py` | NEW | Skipped regression scaffold with `TODO(#1011)` ✓ |

Strictly markdown + packaging metadata + one skipped test. Zero Python
source code touched. Scope is tighter than even the dispatch — perfect.

#### B. TODO compliance

Every new file carries an HTML comment block flagging Phase 2c
(`TODO(#1011)`) for the actual content authoring. The
`<!-- project_context:begin/end -->` markers in `_skills/scieasy/SKILL.md`
are intentionally empty — the splice target for FastMCP's
`_render_project_context` per ADR §3.3. ✓

#### C. Signature contract compliance

- Frontmatter parses (`name:` and `description:` keys present, valid
  YAML block). ✓
- Base SKILL.md has both required marker block pairs:
  - `<!-- project_context:begin -->` / `<!-- project_context:end -->` ✓
  - **`<!-- tool_catalog:begin -->` / `<!-- tool_catalog:end -->` is
    NOT present.** Note this is a known cross-track timing dependency:
    S40a's `system_prompt.py` documents that the splice happens against
    these markers (constants `_TOOL_CATALOG_BEGIN`/`_TOOL_CATALOG_END`),
    but the legacy `skills/scieasy/SKILL.md` (still on disk at repo
    root) carries them. When S40a's `_load_skill_md` switches to
    `importlib.resources` on this S40b-relocated file, the tool_catalog
    splice will fail. **Finding P3 — F1027-1**: I40b (Phase 2c)
    must add the `<!-- tool_catalog -->` marker pair when it authors
    the base body; until then the relocation alone breaks splice
    semantics. Phase-ordered — not S40b's job to fix.

#### D. CI status

All checks PASSED including Test (Python 3.11) + Test (Python 3.13) +
Type Check + Architecture Tests + CodeQL. ✓

#### E. Codex auto-review reconciliation

0 reviews, 0 inline comments. **Codex passed.** ✓

#### F. Test stub quality

`tests/packaging/test_wheel_skills.py` is a single skipped test with a
reference impl in the docstring (`from importlib.resources import
files; ... .read_text("utf-8"); assert "scieasy" in content`). I40b can
flip skip→pass without re-deriving the assertion. ✓

#### Findings summary (PR #1027)

| ID | Severity | Location | Finding |
|---|---|---|---|
| F1027-1 | P3 | `_skills/scieasy/SKILL.md` | No `<!-- tool_catalog -->` marker — required by S40a/I40a's splice but Phase 2c (I40b) authors the full body. Track for I40b dispatch. |

---

### PR #1029 (S40c provisioning)

**Branch**: `feat/issue-1025/adr-040-s40c-provisioning-skeleton` → `track/adr-040/provisioning`.
**Size**: +1114 / -0, 25 changed files. **Mergeability**: `UNSTABLE` (CI flake on unrelated test).

#### A. Diff verification

Owned-file scope from manifest §2.1 covered with surgical precision:

- `src/scieasy/agent_provisioning/` package — 7 new modules
  (`__init__.py`, `_orchestrate.py`, `claude_agents_md.py`, `hooks.py`,
  `skills.py`, `codex_config.py`, `templates/*` × 7) ✓
- `src/scieasy/agent_provisioning/templates/` — 6 hook templates +
  `claude_agents_md.md` + `codex_config.toml`. Confirmed 6 hooks per
  ADR §3.6 (not 3 — see code-scope §8.3 / §5):
  `hook_deny_scieasy_cli.py`, `hook_protect_workflow_yaml.py`,
  `hook_enforce_list_blocks_before_block_write.py`,
  `hook_remind_poll_status.py`, `hook_mark_list_blocks_called.py`,
  `hook_enforce_concrete_port_types.py` ✓
- `src/scieasy/api/runtime.py` — +48 LOC, narrow wiring inside
  `create_project` (after ADR-039 git init block, before
  `self.open_project()`) AND `open_project` (after ADR-039 re-init,
  before `_publish_mcp_port`). Existing ADR-039 / ADR-038 logic
  untouched. ✓
- `src/scieasy/cli/main.py` — +24 LOC; insertion after the existing
  git-init `typer.echo(f"WARNING: git auto-init errored: {exc}", ...)`
  and before final success echo. ✓
- `tests/agent_provisioning/` — 6 new test files (`test_claude_agents_md.py`,
  `test_codex_config.py`, `test_hooks.py`, `test_lifecycle_integration.py`,
  `test_orchestrate.py`, `test_skills.py`) — matches dispatch ✓
- `tests/architecture/test_placement.py` — single-line whitelist add for
  `agent_provisioning` package (manager fix commit `c269269`). ✓

#### B. TODO compliance

All NotImplementedError bodies carry `TODO(#1013)` with detailed impl
plans. Hook templates that defer the hard-enforcement decision carry
`TODO(#1015)` (Layer 7 ACL) and `TODO(#1016)` (BlockRegistry runtime
rejection of `DataObject`-typed ports) per the ADR-040 §3.10 deferral
list. Sampled:

- `_orchestrate.py::install_project_agent_assets` (lines 91-105) — full
  impl plan documented before the raise ✓
- `hook_deny_scieasy_cli.py` — exits 0 unconditionally; module docstring
  explicitly says "MUST NOT exit 2 — a half-finished blocker would
  break every Bash call in a provisioned project". Strong scope
  discipline ✓
- `hook_enforce_list_blocks_before_block_write.py` — carries both
  `TODO(#1013)` AND `TODO(#1015)` (correct per dispatch §3.6) ✓
- `hook_enforce_concrete_port_types.py` — carries `TODO(#1016)` ✓

#### C. Signature contract compliance

- `SCIEASY_PROVISION_VERSION = "0.1.0-skeleton"` constant defined ✓
- `ProvisionResult` dataclass with `written/skipped/failed/version`
  fields ✓
- **Lifecycle wiring guards `NotImplementedError`** — both
  `runtime.py::create_project`, `runtime.py::open_project`, and
  `cli/main.py::init` wrap `install_project_agent_assets()` in
  `try ... except NotImplementedError: pass` so CI stays green during
  the skeleton phase. Per dispatch §3.8 "non-fatal" semantics. ✓
- **ADR-039 ordering preserved** — provisioning runs AFTER git init,
  matching manifest §2.2 directive and ADR §3.8 requirement that
  provisioned files become part of the initial commit (today an
  implementation detail handled in I40c since the call is no-op).
- ADR-039 lifecycle code at `api/runtime.py:598-610` + `:686-701` is
  untouched (insertion at lines 612-636 + 727-749). ✓

#### D. CI status

| Check | Status |
|---|---|
| Lint & Format | SUCCESS |
| Type Check | SUCCESS |
| Architecture Tests | SUCCESS (manager fix commit `c269269`) |
| Import Contracts | SUCCESS |
| Frontend | SUCCESS |
| **Test (Python 3.11)** | **FAILURE — known flake** |
| Test (Python 3.13) | SUCCESS |

The Python 3.11 failure is `tests/api/test_workflows.py::test_cancel_block_and_cancel_workflow_propagate_terminal_states`:
`assert <BlockState.DONE: 'done'> == <BlockState.CANCELLED: 'cancelled'>`.

**This test is NOT touched by PR #1029** (verified via `git log
pr-1029-prov -- tests/api/test_workflows.py` — last touch is
`b244010` on main, predates this PR). It's a sleep/timing race in the
cancellation propagation test that has surfaced intermittently — the
parallel `Test (Python 3.13)` job ran the same test and passed,
confirming flake nature. **Finding P2 — F1029-1**: flake unrelated to
PR; manager should re-run CI on PR #1029 to confirm pass after
verification.

#### E. Codex auto-review reconciliation

0 reviews, 0 inline comments. **Codex passed.** ✓

#### F. Test stub quality

Every new test file in `tests/agent_provisioning/` carries skipped
tests with docstring test plans referencing the corresponding orchestration
sub-step. Per spot check of `test_orchestrate.py` and `test_hooks.py`:
each test has a `@pytest.mark.skip(reason="...")` decorator with
`TODO(#1013)`. Docstrings adequate for I40c flip. ✓

#### Findings summary (PR #1029)

| ID | Severity | Location | Finding |
|---|---|---|---|
| F1029-1 | P2 | CI Test (Python 3.11) | Unrelated flake on `test_cancel_block_and_cancel_workflow_propagate_terminal_states`. Recommend manager re-run. Not blocking. |
| F1029-2 | P3 | `_orchestrate.py::SCIEASY_PROVISION_VERSION` | Uses `TODO(#1011)` for version bump rather than a dedicated tracking issue. Strictly aligns with the umbrella; could be refined but acceptable. |

---

### PR #1028 (S40d install-parity)

**Branch**: `feat/issue-1026/adr-040-s40d-install-skeleton` → `track/adr-040/install-parity`.
**Size**: +176 / -13, 3 changed files. **Mergeability**: `CLEAN`.

#### A. Diff verification

Strictly within manifest §3.1 owned files:

- `src/scieasy/cli/install.py` — +118 / -13. Surgical edits add
  TODO-comment blocks above `_codex_config_path`, `_install_codex`,
  `_skill_dest`, `_install_skill`, `_remove_skill`, and the
  `perform_install` codex fallback branch. **Return type of
  `_install_skill` / `_remove_skill` widened from `InstallResult` to
  `list[InstallResult]`** to support cross-install in I40d. ✓
- `tests/cli/test_install.py` — +54 LOC, 5 new skipped tests covering
  the contract widening. ✓
- `CHANGELOG.md` — entry added ✓
- No other files touched (no `__main__.py`, no `terminal.py`, no
  `cli/main.py`, no MCP files). ✓

#### B. TODO compliance + dispatch fidelity

S40d preserved legacy bodies INSIDE the touched functions — explicitly
called out in the dispatch as a judgment call: dispatch said
"`MCP_SERVER_NAME`, `_mcp_entry_payload`, `_scieasy_command_for_env`,
`_render_codex_block` signatures UNCHANGED (preserves `__main__.py` +
`terminal.py` consumers). S40d kept legacy bodies inline per its
judgment call — flag this as a deviation from 'pure NotImplementedError
skeleton' pattern."

Per audit: this is the **correct** deviation. PRs #1030 and the
`__main__.py` test consumers (per manifest §3.4 callsites) would
break under a pure NotImplementedError approach (cf. PR #1030's
identical regression). S40d's preserved-bodies approach kept CI green
and downstream consumers functional. ✓

All TODO comments carry `TODO(#1014)` with file:line and impl plan
references. ✓

#### C. Signature contract compliance

- `MCP_SERVER_NAME`, `_mcp_entry_payload`, `_scieasy_command_for_env`,
  `_render_codex_block` — UNCHANGED. ✓ (Verified via diff.)
- `_install_skill` signature: `(scope: str, cwd: Path) -> list[InstallResult]`
  (return type widened) ✓ — `perform_install` correctly uses
  `results.extend(...)` not `results.append(...)` (line 600).
- `_remove_skill` signature: same widening ✓
- "Force user-scope for codex" fallback at lines 484-498 retained
  inline with `TODO(#1014)` markers above and inside, awaiting I40d
  removal. ✓

#### D. CI status

ALL checks PASSED. ✓

#### E. Codex auto-review reconciliation

0 reviews, 0 inline comments. **Codex passed.** ✓

#### F. Test stub quality

5 skipped tests at `tests/cli/test_install.py:233-281`:

1. `test_install_skill_cross_install_user_scope` — both `.claude/skills/` AND `.agents/skills/`
2. `test_install_skill_cross_install_project_scope` — same for project scope
3. `test_remove_skill_cross_removal` — symmetric cleanup
4. `test_install_codex_project_scope_writes_local_config` — Codex 2026 project-scope
5. `test_perform_install_codex_no_longer_forces_user_scope` — assertion that "wrote to user scope" detail no longer surfaces

Each test has a multi-line comment describing the expected post-impl
assertion. Adequate for I40d flip. ✓

#### Findings summary (PR #1028)

| ID | Severity | Location | Finding |
|---|---|---|---|
| F1028-1 | P2 | `cli/install.py::_install_skill`/`_remove_skill` | Return type widening (InstallResult → list[InstallResult]) is a public-ish surface change, technically backward-incompatible if any downstream consumer outside this module called them. Grep confirms only `perform_install` calls these inside `install.py`. Low risk but worth a flag for the audit/integration phase. |
| F1028-2 | P3 | `cli/install.py:484-498` | "Force user-scope for codex" fallback block left intact with TODO. Phase 2 (I40d) removes. Per dispatch this is correct. |

---

## Cross-track wiring findings

### W1 — `_load_skill_md` ↔ relocated SKILL.md timing

S40a's `_load_skill_md()` in `system_prompt.py` documents
`importlib.resources.files("scieasy") / "_skills" / "scieasy" / "SKILL.md"`
as the future path. S40b ships the file at exactly that location with
`pyproject.toml` package-data entry. **But the two PRs target different
bases** (#1030 → `track/adr-040/fastmcp`; #1027 →
`track/adr-040/skills`). When I40a fills in `_load_skill_md()` against
its tracking branch, the SKILL.md isn't there until skills track
merges. This is the cross-PR coordination risk flagged in the dispatch.
**Finding C1 — P3 / phase risk**: Manager should sequence merges:
S40b skills track lands FIRST in either main or the FastMCP tracking
branch (manager merges skills track), then I40a impl can `read_text()`
real content. Pre-impl, the broken `_load_skill_md` is the F1030-2 P1.

### W2 — `_registry.py` deletion vs Install-parity callsite

`_registry.py` was deleted by S40a (PR #1030). The manifest §1.3
listed 6 callsites; verified all 6 are FastMCP-track owned and were
updated in the same PR. **`install.py` does not import `_registry`** —
confirmed by grep on PR #1028's `cli/install.py`. ✓ Cross-track
deletion is clean.

### W3 — `_render_codex_block` reuse

Provisioning track's `agent_provisioning/codex_config.py` will (in
I40c) call `install._render_codex_block(project_dir)`. S40d preserved
`_render_codex_block` signature unchanged. ✓ Cross-track contract
preserved.

### W4 — `pyproject.toml` overlap

S40a edits `[project] dependencies` (adds `fastmcp`); S40b edits
`[tool.setuptools.package-data]` (adds `_skills/scieasy/**/*.md`).
Different sections → no conflict.

**BUT**: when these tracking branches eventually merge into main,
both pyproject edits land together. Verified by `git diff main pr-1030
-- pyproject.toml` + `git diff main pr-1027 -- pyproject.toml`: edits
are at lines 33 (fastmcp dep) and 97-98 (package-data) respectively;
no overlap. ✓ Flag for Phase 3.5 integration audit as resolved.

### W5 — `<!-- tool_catalog -->` markers (cross-track gap, see F1027-1)

S40b's relocated `_skills/scieasy/SKILL.md` doesn't include
`<!-- tool_catalog:begin/end -->` markers (Phase 2c I40b adds full
body). When I40a runs against the relocated file, the
`_splice` call in `compose_system_prompt` won't find target markers
and will fail open or insert nothing depending on `_splice`
implementation. **Finding C2 — P3 / phase risk**: Phase 2c dispatch
must include the tool_catalog markers in addition to the
project_context markers when authoring the base SKILL.md body.

---

## Codex auto-review reconcile (consolidated)

| PR | Codex reviews | Codex comments | Disposition |
|---|---|---|---|
| #1030 | 1 (summary) | 2 (P1) | Both P1: **ACCEPT — fix-in-PR** per overnight merge protocol. Reflected as F1030-1 + F1030-2. |
| #1027 | 0 | 0 | passed |
| #1029 | 0 | 0 | passed |
| #1028 | 0 | 0 | passed |

No P2 or below from Codex on any PR. No deferred findings.

---

## Recommendation for manager

### Merge readiness

- **PR #1027 (S40b)**: READY. Merge into `track/adr-040/skills` after
  one manager-confirmed CI re-run (currently green). No fix dispatch
  needed.
- **PR #1028 (S40d)**: READY. Merge into `track/adr-040/install-parity`
  immediately. No fix dispatch needed.
- **PR #1029 (S40c)**: READY conditional on CI re-run resolving the
  Python 3.11 flake on `test_cancel_block_and_cancel_workflow_...`.
  Re-run `gh workflow run` or push an empty commit to retrigger.
  Architecture test whitelist fix already landed (`c269269`).
- **PR #1030 (S40a)**: **NEEDS-FIX**. Two Codex P1 + 2 CI failures
  trace to the same root cause: `compose_system_prompt()` and
  `MCPServer.start()` raise NotImplementedError, breaking
  `terminal.py` / `ai_block.py` / `api/app.py` lifespan / standalone
  bridge. Cannot merge into `track/adr-040/fastmcp` until fixed.

### Recommended Phase 1.6 fix dispatch

Single F40-skel agent (or manager hotfix) on PR #1030 with:

1. **F1030-1 fix**: restore `MCPServer.start()` / `MCPServer.stop()`
   to the legacy hand-rolled behavior (or a no-op + warning log) so
   FastAPI lifespan + standalone bridge keep working. Mark the legacy
   bodies with `TODO(#1012): I40a Phase 2a — replace with FastMCP
   serve loop.`
2. **F1030-2 fix**: restore `_load_skill_md()` to the legacy walk-up
   resolver targeting the still-on-disk `skills/scieasy/SKILL.md` at
   repo root. Mark with `TODO(#1012): I40a Phase 2a — switch to
   importlib.resources once S40b's relocated SKILL.md is reachable on
   this branch.` Restore `compose_system_prompt()` body to call legacy
   `_render_tool_catalog()` returning a placeholder string (or read
   from the existing TOOL_REGISTRY shadow — but `_registry.py` was
   deleted, so a minimal hardcoded fallback string is the cheapest
   path). The S40a docstring already documents the intent.
3. **F1030-3 fix-through**: re-narrow `tests/**` module-level skips
   from 9 back to the dispatched 3 (`test_mcp_fastmcp.py`,
   `test_system_prompt.py`, `test_mcp_server_skeleton.py`) once the
   regressions are gone — every other test should pass against the
   restored legacy bodies.

### Top 3 manager actions (priority order)

1. **Dispatch F40-skel-1030** fixing F1030-1 + F1030-2 + F1030-3 in
   PR #1030, in-PR, per overnight merge protocol. Audit P1 override
   (per memory `feedback_audit_p1_override`).
2. **Re-run CI on PR #1029** to confirm Python 3.11 flake clears.
   Once green, merge into `track/adr-040/provisioning`.
3. **Merge PR #1027 + PR #1028** into their respective tracking
   branches now — both READY, no fix needed. Sequence: S40b skills
   first, then S40d install-parity (no inter-dep).

### Phase 2 dispatch readiness

Once Phase 1.6 closes:
- I40a (FastMCP impl) can dispatch against `track/adr-040/fastmcp`
  with S40a skeleton merged.
- I40c (Provisioning impl) can dispatch against
  `track/adr-040/provisioning` with S40c merged.
- I40d (Install-parity impl) can dispatch against
  `track/adr-040/install-parity` with S40d merged.
- Skills content (Phase 2c, I40b) waits for the Phase 2b skill-design
  investigation per the checklist.

No Phase 2 dispatch should proceed until PR #1030 is fixed and merged.
