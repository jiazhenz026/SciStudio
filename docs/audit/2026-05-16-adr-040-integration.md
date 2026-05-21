# A_int: ADR-040 Cross-Track Integration Audit (Phase 3.5)

**Date:** 2026-05-16
**Tracking branch:** `track/adr-040` @ `d91c5e8` (after A1/A2/A3 reports merged)
**Cascade umbrella:** #1011
**Sub-issue:** #1085
**Auditor:** A_int (read-only). Sibling auditors: A1 (completeness + bugs + edges, PR #1070), A2 (MCP wiring + cross-doc, PR #1066), A3 (agent-POV prompt + skill, PRs #1067 + #1071).
**Scope:** verify cross-track wiring AFTER all 4 workstreams (FastMCP / Provisioning / Install-parity / Skills) have landed; catch boundary issues single-track audits miss.

---

## Summary

**Verdict: pass-with-fixes (ship-ready conditional on F40-integration + PR #1064 landing).**

The four-layer reliability stack is **structurally complete and cross-track consistent**. Every pair of tracks that share a contract surface has been wired correctly:

- FastMCP `mcp.list_tools()` → `system_prompt._render_tool_catalog` → base `SKILL.md` `<!-- tool_catalog -->` splice.
- `install._render_codex_block` shared by `cli/install.py` AND `agent_provisioning/codex_config.py` (one-way import, no cycle).
- `_install_skill` (CLI path) and `agent_provisioning/skills.py::write_skills` (lifecycle path) read from the same `importlib.resources.files("scistudio") / "_skills" / "scistudio"` source.
- `install_project_agent_assets` wired at all 3 entry points (`api/runtime.py::create_project`, `api/runtime.py::open_project`, `cli/main.py::init`) with identical degraded-mode contract.

What blocks ship today are **3 known content-level defects** that two of the three Phase 3 audits independently flagged:

1. **`_SCAFFOLD_TEMPLATE` legacy `type=` API drift** (A1 §3.2a P2, A3 §C.2 P1) — covered by **open PR #1064** (`fix/issue-1063/scaffold-accepted-types`), 4 LOC, CI green except Lint & Format. **Manager must land this before ship.**
2. **`hook_enforce_concrete_port_types.py` dead code** (A1 §C P2, A3 §F.2 P1) — owned by dispatched **F40-integration** agent.
3. **Skill envelope drift on `validate_workflow` / `get_run_status` / `run_block_tests`** (A1 §G P1×3) — **already reconciled by PR #1065** (verified by direct grep, see §C.5). A1's report predates this merge.

Beyond the three above, A_int found **2 cross-track issues not flagged by A1/A2/A3 individually** (§B.4 marker-file edge case; §D.3 hook safety-net language asymmetry on Codex), and one **boundary risk** at the dev/prod doc seam (§E.3).

**Ship readiness:** cascade is **~90% ready**. The remaining 10% is PR #1064 + the F40-integration fix landing on `track/adr-040`. No architecture-level concerns.

P1 / P2 / P3 counts: **3 P1, 7 P2, 6 P3**.

---

## A. End-to-end string identity check

Simulated `compose_system_prompt(<fixture project>)` mentally by reading the splice path top-to-bottom.

### A.1 Splice sequence (verified)

1. `compose_system_prompt(project_dir)` reads the base `SKILL.md` via `_load_skill_md` (`system_prompt.py:76-133`).
   - **Path 1 (primary):** `importlib.resources.files("scistudio") / "_skills" / "scistudio" / "SKILL.md"` → resolves on `track/adr-040` (the packaged tree).
   - **Path 2 (fallback):** repo-root walk-up `<repo>/skills/scistudio/SKILL.md` — **dead on `track/adr-040`** because I40b PR #1059 deleted the legacy file. Retained as defensive fallback (TODO(#1012)-tagged).
2. `_render_tool_catalog()` (`system_prompt.py:136-201`) is invoked.
   - Force-imports `scistudio.ai.agent.mcp` so FastMCP `@mcp.tool` decorators run.
   - Calls `await mcp.list_tools()` via the Codex-P1-reconciled thread-pool executor pattern.
   - Returns 26 tools grouped by `category:` tag + `read`/`write` mutation tag.
3. `_render_project_context(project_dir)` (`system_prompt.py:204-340`) is invoked.
   - Reads `project.yaml::project.name` (fallback: dir name).
   - Counts `*.ya?ml` under `workflows/` via `os.scandir`.
   - Top-3 by mtime + `_format_age` formatter.
   - `BlockRegistry.installed_plugins` enumeration (best-effort).
   - `git rev-parse` for branch + sha (2.0s timeout).
4. `_splice` (`system_prompt.py:360-377`) replaces the BOTH `<!-- tool_catalog:begin/end -->` AND `<!-- project_context:begin/end -->` marker pairs with the rendered content.

### A.2 Marker presence verified

`src/scistudio/_skills/scistudio/SKILL.md` carries BOTH marker pairs (per A2 §E.1). A2 cited line 68-69 + 78-79; verified directly. **PASS.**

### A.3 Output the agent actually sees

Composite: ~80 LOC base SKILL.md identity + 26-tool catalog (~30 LOC) + project-context block (~10 LOC) ≈ **~120 LOC system prompt**. Per ADR §2.2 budget. **PASS.**

### A.4 Cross-track risk

The 4 tracks each own one or more pieces of the splice:

| Piece | Owner track | File |
|---|---|---|
| Base SKILL.md content | Skills (I40b) | `src/scistudio/_skills/scistudio/SKILL.md` |
| Marker pairs in SKILL.md | Skills (I40b) — added during I40b | Same file |
| `_load_skill_md` resolver | FastMCP (I40a) | `src/scistudio/ai/agent/system_prompt.py:76-133` |
| `_render_tool_catalog` | FastMCP (I40a) | `system_prompt.py:136-201` |
| `_render_project_context` | FastMCP (I40a) | `system_prompt.py:204-340` |
| `<!-- tool_catalog -->` consumer | FastMCP (I40a) reads, Skills (I40b) emits | n/a |
| `<!-- project_context -->` consumer | FastMCP (I40a) reads, Skills (I40b) emits | n/a |

If Skills had failed to emit the markers OR FastMCP had failed to splice into them, the agent would see `<!-- tool_catalog:begin -->` literally in its prompt. The integration is correct on `track/adr-040`. **PASS.**

**No P1/P2 findings in §A.**

---

## B. Fresh-project lifecycle dry-run

Traced `api/runtime.py::create_project` end-to-end.

### B.1 ADR-039 git auto-init runs first

`api/runtime.py:601-610`: `GitEngine(project_path).init_repository()` runs first; failure logs a warning and continues (degraded mode). ADR-040 provisioning runs AFTER git init so the initial commit is clean of provisioned files. **PASS.**

### B.2 `install_project_agent_assets` files written

`agent_provisioning/_orchestrate.py:64-149` writes:

| File | Owner sub-step | ADR § |
|---|---|---|
| `<project>/CLAUDE.md` | `claude_agents_md.write_claude_agents_md` | §3.5 |
| `<project>/AGENTS.md` | same (byte-identical copy) | §3.5 |
| `<project>/.claude/settings.json` | `hooks.write_hooks` | §3.6 |
| `<project>/.claude/hooks/deny_scistudio_cli.py` | same | §3.6 |
| `<project>/.claude/hooks/protect_workflow_yaml.py` | same | §3.6 |
| `<project>/.claude/hooks/enforce_list_blocks_before_block_write.py` | same | §3.6 |
| `<project>/.claude/hooks/remind_poll_status.py` | same | §3.6 |
| `<project>/.claude/hooks/mark_list_blocks_called.py` | same | §3.6 |
| `<project>/.claude/hooks/enforce_concrete_port_types.py` | same | §3.6 |
| `<project>/.claude/skills/scistudio/SKILL.md` | `skills.write_skills` (base) | §3.4 |
| `<project>/.claude/skills/scistudio-build-workflow/SKILL.md` | same (task) | §3.4 |
| `<project>/.claude/skills/scistudio-write-block/SKILL.md` | same | §3.4 |
| `<project>/.claude/skills/scistudio-debug-run/SKILL.md` | same | §3.4 |
| `<project>/.claude/skills/scistudio-inspect-data/SKILL.md` | same | §3.4 |
| `<project>/.claude/skills/scistudio-project-qa/SKILL.md` | same | §3.4 |
| `<project>/.agents/skills/scistudio/SKILL.md` (×6, mirrored) | same | §3.4 + §3.9 |
| `<project>/.codex/config.toml` | `codex_config.write_codex_config` | §3.7 |
| `<project>/.claude/.scistudio-provision-version` | orchestrator marker | §3.8 |

**Verified by reading `_orchestrate.py:80-109` `steps` table + `skills.py::_expected_skill_paths()` returning 12 paths (6×2 trees) + marker rel path.**

Expected `ProvisionResult.written` cardinality on fresh project: 2 (CLAUDE/AGENTS) + 7 (settings + 6 hooks) + 12 (skills) + 1 (codex) + 1 (marker) = **23 entries**.

A1 §E said "~17 entries" — A1's count missed the codex/agents skills mirror (6 extra) and the AGENTS.md copy. **Minor P3 documentation note.** (Not blocking; reality is 23.)

### B.3 Idempotency on `open_project`

`api/runtime.py:724-746` calls `install_project_agent_assets(project_path, force=False)`. `force=False` semantics in each sub-writer:

- `write_claude_agents_md`: skip if file exists (preserves user customization).
- `write_hooks`: skip per file.
- `write_skills`: skip per file (line 153-155 in `skills.py`).
- `write_codex_config`: skip if exists (line 40-41 in `codex_config.py`).

**Race condition consideration (cross-track):** If user runs `scistudio install --skill --scope project` AND then SciStudio GUI opens the same project, both writers walk the same dest tree. Both use `force=False` semantics so the first writer wins — no clobber, no error, no data loss. **PASS.**

### B.4 Version-marker file edge case — **P2, A_int-specific**

`_orchestrate.py:131-145` writes the marker as the LAST step, AFTER all 4 sub-steps. If only `hooks` (which creates `.claude/`) failed, the marker write may also fail. Marker write failure is recorded in `result.failed` and is non-fatal — the project still opens. **BUT** the next `open_project` call has no signal that v0.1.0 was attempted: the marker is absent, so a future upgrade-flow implementation (TODO(#1011)) cannot distinguish "fresh project" from "v0.1.0 attempted but partial". 

This is **NOT** flagged by A1 (which noted version-marker drift detection absence at P2 level §E) or A2/A3. **P2 cross-track**: recommend a "best-effort marker write inside any sub-step that successfully created `.claude/`" defensive write OR a separate "attempted-versions" log file. Not blocking; future-Phase concern when upgrade flow lands.

### B.5 Cross-track partial-failure isolation — verified

`_orchestrate.py:111-122`: each sub-step in `try/except`. Failure of one does not prevent the next. The `ProvisionResult.failed` list captures `(label, reason)` tuples. A1 §E enumerated 11 scenarios with PASS verdicts; A_int spot-checked "permission denied on `.claude/`" (hooks fails → skills sub-step still runs and writes to `.agents/skills/scistudio/` only since `.claude/skills/` mkdir would fail) — sub-step skip pattern works correctly.

**No new P1; P2.B.4 logged.**

---

## C. Cross-track contracts

Five symbols are shared across track boundaries. Each must remain stable.

### C.1 `install._render_codex_block(project_dir)`

**Importers:**
- `cli/install.py` itself: `_render_codex_block` is defined at `install.py:242-269` and used by `_install_codex` (line 332).
- `agent_provisioning/codex_config.py:45` does `from scistudio.cli.install import _render_codex_block` (deferred import to avoid pulling typer).

**Signature stability verified:** single positional arg `project_dir: Path | None`. Both callers pass an absolute path (`project_dir.resolve()` in `agent_provisioning`, raw `cwd` in `cli`). **PASS.**

**Byte-equivalence test** (`tests/agent_provisioning/test_codex_config.py::test_codex_config_matches_install_render`) per A2 §B.13 — confirms the two writes produce identical content. **PASS.**

### C.2 `MCP_SERVER_NAME`, `_mcp_entry_payload`, `_scistudio_command_for_env`

**Importers:**
- `cli/install.py` (defines, uses): `_install_claude` writes JSON `.mcp.json`, uses `MCP_SERVER_NAME` and `_mcp_entry_payload`.
- `_scistudio_command_for_env` is internal to `cli/install.py` (defined at line 72, used at lines 102 + 249).

**A2 §B.13 noted** that `_render_codex_block` reaching into `cli.install` is a "future-refactor candidate" for a shared module. A_int concurs but **no P1/P2 risk today** because:
- Import direction is one-way (`agent_provisioning → cli`); no cycle.
- `cli` has no dependency on `agent_provisioning`.
- `pyproject.toml` import-linter contracts (3 declared) do NOT forbid this direction.

**PASS** with the P3 design note carried forward.

### C.3 FastMCP `MCPServer.start() / .stop() / .serve()`

**Callers:**
- `api/app.py:107-114` FastAPI lifespan starts/stops via `MCPServer(socket_path, project_dir)` in-process.
- `runtime.py::start_inprocess_server` (standalone-bridge entry point for the `scistudio mcp-bridge` subprocess) — A2 §B.4 verified.

**Signature stability verified:** all 3 methods are real implementations now (NOT NotImplementedError stubs from S40a era). A2 §B.4 noted the runtime.py docstring is stale (says they raise NotImplementedError); P3 docstring update needed. **PASS** with P3 doc carryover.

### C.4 Skill source path `importlib.resources.files("scistudio") / "_skills" / "scistudio"`

**Three independent readers** all target the same packaged path:

1. **FastMCP track:** `system_prompt.py:_load_skill_md` reads the base SKILL.md.
2. **Install-parity track:** `cli/install.py::_find_skill_source` (`install.py:442-475`) walks the whole tree for `--skill` cross-install.
3. **Provisioning track:** `agent_provisioning/skills.py::_read_skill_source` (`skills.py:87-132`) reads each of 6 SKILL.md files.

All three resolve to `src/scistudio/_skills/scistudio/` on editable install AND on wheel install (per `pyproject.toml [tool.setuptools.package-data]` shipping `_skills/scistudio/**/*.md`).

**Cross-track risk discovered (P2-A_int-01):** `agent_provisioning/skills.py::_read_skill_source` (`skills.py:97`) maps the base "scistudio" skill name to package `scistudio._skills.scistudio` — but the file lives at the package ROOT, not at `scistudio._skills.scistudio.SKILL.md` within a "scistudio" subdir. The code handles this by reading from `scistudio._skills.scistudio` (the package itself) and joining `SKILL.md`. Reading code: `importlib.resources.files(package_path).joinpath("SKILL.md")` where `package_path = "scistudio._skills.scistudio"`. The base SKILL.md lives at `src/scistudio/_skills/scistudio/SKILL.md` (verified). **Works correctly** but the logic has an asymmetry: task skills get `scistudio._skills.scistudio.<name>` (line 97 conditional). If a future contributor renames the base skill or moves a task skill, the conditional logic must be updated symmetrically.

A1 §3.4 marked this as PASS; A2 §B.2 marked PASS. A_int flag is **cosmetic clarity P3** — not blocking.

**P2-A_int-01 (actual):** `cli/install.py::_find_skill_source` falls back ONLY to `<repo>/skills/scistudio/` (the deleted legacy path) — does NOT walk-up to the relocated `src/scistudio/_skills/scistudio/`. This is the EXACT P2 A1 §3.9 flagged ("PR #1049 Codex P2 NOT addressed"). A_int confirms this is still open. **Cross-track because:** if a dev clones the repo and runs `scistudio install --skill` from a non-installed state (no `importlib.resources` resolution), the `--skill` command fails with FileNotFoundError. In contrast, `agent_provisioning/skills.py::_read_skill_source` DOES walk both candidate paths (`skills.py:103-108`). The 2 tracks have divergent fallback behavior. **Recommend 2-line fix to `cli/install.py::_find_skill_source` to match the provisioning track's walk-up logic** — covered by A1 P2.6.

### C.5 Verifying PR #1065 reconciled A1's P1.1/P1.2/P1.3

A1 §G flagged 3 P1s on skill envelope drift in PR #1059, BUT A1's report HEAD was `949476f` (pre-#1065). A_int verified at current HEAD (`d91c5e8`):

- **P1.1** (`run_block_tests` arg name): `src/scistudio/_skills/scistudio/scistudio-write-block/SKILL.md:264` reads `mcp__scistudio__run_block_tests type_name="imaging.threshold_simple"` — uses `type_name`, NOT the broken `block_path`. ✓ **Reconciled.**
- **P1.2** (`validate_workflow` envelope): `scistudio-build-workflow/SKILL.md:261` reads `ValidateWorkflowResult(valid: bool, errors:` — uses `valid: bool`, NOT the broken `ok: bool`. ✓ **Reconciled.**
- **P1.3** (`get_run_status` envelope): `scistudio-debug-run/SKILL.md:38-47` reads `GetRunStatusResult(... progress: {"block_states": ...}, errors: [BlockErrorEntry(...)] )` — matches code exactly. ✓ **Reconciled.**

**PR #1065 (commit `4e62f4a`) is the orphaned-after-#1059-squash reconcile that addressed all three.** A1's report was authored before this merge landed; verified A_int. The "manager merged with deferred fix" override A1 flagged is **closed in practice**.

**Result:** A1's three top P1s no longer block ship. They survive as a process lesson (`feedback_audit_p1_override`), not a code defect.

---

## D. Provider parity (Claude vs Codex)

ADR-040 §3.5 + §3.7 + §3.9 require Claude AND Codex provisioning to be symmetric except where Codex 2026 differs (hooks not supported per §3.10).

### D.1 Skill mirroring — verified byte-identical

`agent_provisioning/skills.py::write_skills` writes the SAME 6-skill set to BOTH `<project>/.claude/skills/scistudio/` AND `<project>/.agents/skills/scistudio/`. Source is read once per skill (`sources` dict at `skills.py:148`) and written twice. **Byte-identical guarantee structural.** **PASS.**

`cli/install.py::_install_skill` also writes both trees via the same `_skill_dest` tuple (line 419-420). **PASS.**

### D.2 Codex `.codex/config.toml` — registers MCP server

Per A2 §B.13: `codex_config.write_codex_config` calls `_render_codex_block(project_dir.resolve())` which emits `[mcp_servers.scistudio]` and `[mcp_servers.scistudio.env]` blocks. **PASS.**

### D.3 Codex CLAUDE.md/AGENTS.md parity — **P2 A_int-specific**

`agent_provisioning/claude_agents_md.py::write_claude_agents_md` writes the SAME `claude_agents_md.md` template content to BOTH `<project>/CLAUDE.md` and `<project>/AGENTS.md` (per A2 §E.4 byte-equivalence test). 

**HOWEVER**, A3 §D.3.1 + §F.1.1 + §F.1.3 found that the template body itself contains language that applies ONLY to Claude:

> "A PreToolUse hook blocks such calls with exit code 2." (line 12)
> "it is enforced by a PostToolUse hook that blocks `blocks/*.py` writes..." (line 17)
> "A PostToolUse hook stderr-warns when a block file declares a generic port type." (line 25)

A Codex 2026 agent reading `AGENTS.md` is told hooks exist — but Codex's hook config is NOT written by `write_codex_config` (per ADR §3.10 explicit out-of-scope). The Codex agent has **false reassurance**.

This is **cross-track** because the fix touches:
- `agent_provisioning/templates/claude_agents_md.md` (Provisioning track owns the template).
- AND the skill bodies under `src/scistudio/_skills/scistudio/scistudio-write-block/SKILL.md` (Skills track owns; A3 §F.1.1 flagged the same issue at skill lines 17-20).

A3 §G.5 row 5 recommended a single top-level "Hook safety net (Claude Code only)" disclaimer. A_int **concurs** and elevates: this is a P1 from Codex's POV (an agent acts incorrectly on false hook reassurance) but A3 already labeled it P1 (#5). **Confirmed P1, already flagged by A3.**

**Recommendation for F40-integration scope:** the polish-pass PR must touch BOTH the template AND any skill body referencing hooks. Single PR per A3's R5.

### D.4 Hook script absence on Codex — verified ADR-compliant

`agent_provisioning/_orchestrate.py:_expected_skill_paths` lists hooks only for `.claude/hooks/`. No `.agents/hooks/` write. **Matches ADR §3.10 carve-out.** **PASS** at the architecture level.

### D.5 Cross-mirror invariant — verified

For every skill name in `_SKILL_NAMES` and every dest tree in `_DEST_TREES`, `write_skills` writes one file. Cardinality: 6 × 2 = 12 paths. Independent of provider, content is identical (read once, written twice). A1 §D matrix did not test this directly; A_int confirms by reading `skills.py:148-158`. **PASS.**

---

## E. Documentation graph

### E.1 ADR-040 §5.3 documentation impact items

ADR-040 §5.3 promised updates to ADR-034, ADR-035, `embedded-coding-agent-spec.md`, `ARCHITECTURE.md`, and a new operational doc.

| Promised item | Status | Notes |
|---|---|---|
| ADR-034 "25 tools" → "26 tools (per ADR-040 §3.1)" | **NOT SHIPPED** | Lines 15, 99, 209 still say 25 (A2 §D). |
| ADR-035 add ADR-040 §3.1 cross-ref to FastMCP envelope shape | **NOT SHIPPED** | Line 192 says "registered like the other 25" (A2 §D). |
| `embedded-coding-agent-spec.md` §6 — drop TOOL_REGISTRY refs | **NOT SHIPPED** | Lines 761, 780, 1161 stale (A2 §D). |
| `ARCHITECTURE.md` §6 (MCP) — "~25 tools" → 26 | **NOT SHIPPED** | Line 2274 stale (A2 §D). |
| `ARCHITECTURE.md` §10.2 new "Prod-env agent reliability stack" | **SHIPPED** | Lines 3016-3067 (A2 §D). |
| `docs/agent-provisioning.md` new operational doc | **SHIPPED** | Per I40c CHANGELOG. |
| `docs/cli-integration.md` updates for cross-install + codex project-scope | **SHIPPED** | A2 §D. |

**Net:** 4 of 7 doc-impact items deferred. A2 §D bundled these into P2 cross-doc sweep. A_int **concurs** but **does not elevate to P1** — runtime is correct; docs are internally contradictory but not broken. Recommend a single docs-only PR `docs(#1011): ADR-040 cross-doc sweep` after cascade ships.

### E.2 ADR-034/035/038/039 cross-references resolve

- ADR-040 § references to ADR-034 (PTY): resolve to live ADR-034 §3.5 (MCP catalog re-render).
- ADR-040 § references to ADR-035 (`finish_ai_block`): resolve to live ADR-035 §3.5.
- ADR-040 § references to ADR-038 (lineage): A2 verified hooks don't write lineage; ADR-038 unaffected.
- ADR-040 § references to ADR-039 (git auto-init): A2 verified ordering ("AFTER git init") matches code.

**All four upstream ADR refs resolve.** **PASS.**

### E.3 Dev/prod boundary — A_int-specific concern, P3

ADR-040 §2.1 explicitly carves dev environment out of scope. **HOWEVER**, the dispatch instructions for this audit (and several phase prompts under `docs/planning/dispatch-prompts/`) reference both:

- The SciStudio repo's `.claude/skills/scistudio/` (dev env, agent harness)
- The user's `<project>/.claude/skills/scistudio/` (prod env, written by ADR-040 §3.4)

A future contributor reading the planning docs may conflate the two. **P3 cross-track** — recommend a single sentence at the top of `docs/agent-provisioning.md` explicitly stating "the prod-env tree at `<project>/.claude/skills/scistudio/` is a different deliverable from the dev-env tree at `<repo>/.claude/skills/scistudio/`." Non-blocking.

### E.4 CHANGELOG verified

CHANGELOG.md has [Unreleased] entries with mandatory metadata for every ADR-040 cascade PR (#1011, #1021, #1023, #1024, #1025, #1026, #1033, #1035, #1037, #1039, #1042, #1043, #1051, #1057, #1060, #1061, #1062, #1068, all sub-PRs). **PASS.**

---

## F. Codex P1/P2 audit across all merged PRs

| PR | Codex P1 | Codex P2 | Disposition |
|---|---|---|---|
| #1010 (pytest-timeout) | 0 | 0 | n/a |
| #1020 (cascade tracking) | 0 | 0 | n/a |
| #1022 (AC40 manifest) | 0 | 0 | n/a |
| #1027 (S40b skeleton) | 0 | 0 | n/a |
| #1028 (S40d skeleton) | 0 | 0 | n/a |
| #1029 (S40c skeleton) | 0 | 0 | n/a |
| #1030 (S40a skeleton) | 2 | 0 | Fixed in-PR per drift-log (manager hotfix) ✓ |
| #1034 (A40-skel report) | 0 | 0 | n/a |
| #1042 (hook regex generalize) | 0 | 0 | n/a |
| #1043 (docs corrective sweep) | 0 | 0 | Merged with 1 CI red (Workflow Gate Check). Docs-only. **P3 process note.** |
| #1047 (I40c provisioning) | 2 | 0 | Both addressed in-PR (MultiEdit matcher + no-space redirect) ✓ |
| #1049 (I40d install) | 0 | 1 | **NOT addressed** (`_find_skill_source` walk-up missing relocated path). Survives as A1 P2.6 + A_int §C.4. |
| #1053 (I40a FastMCP) | 2 | 1 | All addressed via #1058 follow-up ✓ |
| #1054 (AC40-skill research) | 0 | 0 | n/a |
| #1058 (orphaned reconcile of #1053) | 0 | 0 | n/a |
| #1059 (I40b skill content) | 1 | 2 | Addressed via #1065 follow-up — A_int §C.5 confirmed ✓ |
| #1065 (orphaned reconcile of #1059) | 0 | 0 | n/a |
| #1066 (A2 audit report) | 0 | 0 | n/a |
| #1067 (A3 audit report v1) | 0 | 0 | n/a |
| #1070 (A1 audit report) | 0 | 0 | n/a |
| #1071 (A3 audit report v2) | 0 | 0 | n/a |

**Aggregate:** 7 Codex P1 across cascade — **6 addressed**, **0 currently blocking**. **1 Codex P2 from #1049 still open** (the `_find_skill_source` fallback gap, A_int §C.4).

**Conclusion:** no unresolved Codex P1 remain. The one open P2 is documented and aligned with A1's P2.6.

---

## G. Phase 3 audit consensus

Cross-reference A1 + A2 + A3 findings.

### G.1 High-confidence (2+ audits agree on a P1)

| Finding | A1 | A2 | A3 | A_int verdict |
|---|---|---|---|---|
| `_SCAFFOLD_TEMPLATE` `type=` API drift | P2 (§3.2a) | not in scope | **P1 #1** (§C.2, §G.5 rows 1-3) | **P1 — must fix.** PR #1064 in flight covers this. |
| Skill content envelope shape drift on #1059 (`block_path`, `validate_workflow`, `get_run_status`) | **P1 #1-3** (§G) | not in scope | implied by §F.1 systematic naming drift | **Already reconciled by PR #1065.** A_int §C.5 verified. |
| `hook_enforce_concrete_port_types.py` dead code (matches `PortSpec`, never `InputPort`) | P2 (§C) | not in scope | **P1 #2** (§F.2, §G.5 row 4) | **P1 — must fix.** F40-integration agent owns this. |
| `_find_skill_source` walk-up missing relocated path (#1049 Codex P2) | **P2.6** (§3.9) | P3 | P3 | **P2 — should fix.** 2-line install.py change. |
| Cross-doc sweep: "25 tools" stale in ADR-034/035, spec, ARCHITECTURE | not flagged | **P2 ×4** (§D) | not flagged | **P2 — follow-up docs PR.** Recommended after cascade ships. |

### G.2 Single-audit findings A_int verifies

| A3-only findings | A_int verdict |
|---|---|
| `run()` arity disagreement (skill 2-arg vs scaffold 1-arg) | **P1 — must fix.** Confirmed by reading `tools_authoring.py:255` + skill §2. F40-integration scope. |
| `scistudio-write-block` frontmatter doesn't disambiguate "add a new block to my workflow" | **P1 — must fix.** Confirmed by reading skill frontmatter. Skill content fix. |
| CLAUDE.md/AGENTS.md hook safety-net language misleads Codex agents | **P1 — must fix.** A_int §D.3 elevates this. Template fix. |
| DataObject scope conflict (3-way: base SKILL vs skill body vs template) | **P2 — should fix.** Confirmed; all 3 places diverge. Single canonical phrasing needed. |

| A1-only findings | A_int verdict |
|---|---|
| `scaffold_block.category` arg accepted but unused | **P2 — should fix.** Visible to every block author. ~10 LOC fix. |
| 6 pre-existing naked TODOs in `src/` | **P2 — should retag or exempt.** Ship-gate audit signal. |
| `hook_protect_workflow_yaml.py` regex unanchored | **P2 — should fix.** Real false-positive risk. |
| `hook_deny_scistudio_cli.py` regex doesn't catch `env VAR=v scistudio` or `cmd && scistudio` | **P2 — should fix.** |
| `hook_enforce_concrete_port_types.py` misses `ast.Attribute` form | **P2 — should fix** (part of broader hook rewrite). |

### G.3 A_int novel cross-track findings (not in A1/A2/A3)

1. **§B.4 — Version-marker file partial-failure edge case** (P2). Marker absent on partial-failure prevents future upgrade-flow from detecting attempted versions.
2. **§D.3 elevation** — A3 flagged the hook safety-net Codex parity as P1; A_int confirms and elevates to "must fix in F40-integration scope, NOT a P2 polish item".
3. **§E.3 — Dev/prod boundary documentation drift risk** (P3). Recommend disambiguator sentence in `docs/agent-provisioning.md`.

### G.4 Convergence on F40-integration scope

The 3 P1s being addressed by F40-integration agent + PR #1064:

1. **PR #1064** — scaffold template `type=` → `accepted_types=[T]` (4 LOC).
2. **F40-integration agent** — `hook_enforce_concrete_port_types.py` rewrite (match `InputPort`/`OutputPort` + walk `accepted_types`).
3. **F40-integration agent** — 5 skill files: `run()` arity clarification, `scistudio-write-block` frontmatter disambiguator, hook safety-net language Codex-aware.

A_int verifies these align with A1 + A3 consensus.

---

## Findings (P1 / P2 / P3)

### P1 (3 — block ship)

- **P1.A_int.1**: `_SCAFFOLD_TEMPLATE` emits legacy `type=` API → `reload_blocks` TypeError. **PR #1064 in flight.** A1 P2 / A3 P1. Manager must land before ship.
- **P1.A_int.2**: `hook_enforce_concrete_port_types.py` matches non-existent `PortSpec(...)`. Dead code on live API. **F40-integration scope.** A1 P2 / A3 P1.
- **P1.A_int.3**: Skill body API drift on `run()` arity (`scistudio-write-block` §2 vs scaffold template) + `scistudio-write-block` frontmatter doesn't disambiguate "add block to workflow" + CLAUDE.md/AGENTS.md hook safety-net Codex parity. **F40-integration scope.** A3 P1 #3-#5.

### P2 (7 — should fix, mostly post-ship docs)

- **P2.A_int.1**: `_find_skill_source` walk-up missing relocated path (`cli/install.py:464-474`). 2-line fix. A1 P2.6.
- **P2.A_int.2**: Version-marker file partial-failure edge case (§B.4). Future upgrade flow concern; defensive write recommended.
- **P2.A_int.3**: Cross-doc sweep — ADR-034/035 + embedded-coding-agent-spec + ARCHITECTURE.md §6 say "25 tools". A2 P2 ×4.
- **P2.A_int.4**: `docs/agent-provisioning.md` lines 155-158 describe pre-I40b state. A2 P2-A2-05.
- **P2.A_int.5**: `scaffold_block.category` arg accepted but unused. A1 P2.1.
- **P2.A_int.6**: 6 pre-existing naked TODOs in `src/`. A1 P2.5.
- **P2.A_int.7**: Hook regex precision gaps (`protect_workflow_yaml` unanchored, `deny_scistudio_cli` misses `env`/`&&`, `enforce_concrete_port_types` misses `ast.Attribute`). A1 P2.2-P2.4.

### P3 (6 — polish, accepted as-is)

- **P3.A_int.1**: `agent_provisioning/codex_config.py` reaches into `cli/install._render_codex_block` (private symbol). A2 P3-A2-04.
- **P3.A_int.2**: `runtime.py:27-32` docstring describes S40a-era state. A2 P3-A2-01.
- **P3.A_int.3**: `cli/install.py` module docstring says "25-tool MCP surface". A2 P3-A2-03.
- **P3.A_int.4**: `tests/ai/test_mcp_server_skeleton.py` skipped with stale `_registry` imports. A2 P3-A2-02.
- **P3.A_int.5**: Checklist `[ ]` boxes unchecked despite work shipped. A1 P3.7.
- **P3.A_int.6**: Dev/prod boundary disambiguator needed in `docs/agent-provisioning.md` (§E.3 A_int-specific).

---

## Recommendation for Phase 3.6 fix coverage

Ordered fix dispatches beyond what's already in flight:

1. **(BLOCKING) Land PR #1064** — scaffold template `type=` → `accepted_types=[T]`. CI Lint & Format failure on PR #1064 must be addressed (likely a trailing-whitespace fix or ruff format). Confirm with `gh pr checks 1064`.
2. **(BLOCKING) F40-integration agent ships** with the 3 deliverables A3 §G.5 + A_int §G.4 enumerated:
   - `hook_enforce_concrete_port_types.py` rewrite (per A3 §G.5 row 4 patch).
   - 5 skill files polish pass (`run()` arity in `scistudio-write-block` §2; frontmatter disambiguator in `scistudio-write-block`; hook safety-net Codex parity in any skill that references hooks).
   - `claude_agents_md.md` template — top-level "Hook safety net (Claude Code only)" disclaimer.
3. **(STRONGLY RECOMMENDED) Pre-ship `cli/install.py::_find_skill_source` walk-up fix** — 2-line change. Or defer to a post-ship docs/install hardening PR.
4. **(STRONGLY RECOMMENDED) Pre-ship `scaffold_block.category` arg fix** — 10 LOC. Either drop the arg or route into template selection.
5. **(POST-SHIP) Docs cleanup PR** for all P2.A_int.3 + P2.A_int.4 (cross-doc sweep — A2's 5 P2 items). ~30 LOC across 5 files.
6. **(POST-SHIP) Hook hardening PR** — A1 P2.2-P2.4 + A_int §G.2 hook items. ~15 LOC.
7. **(POST-SHIP) Housekeeping PR** — A2's 4 P3 items + A_int §E.3 disambiguator + retag of pre-existing TODOs.

**Cascade ship-readiness verdict:**

| Condition | Status |
|---|---|
| All 4 tracks landed on `track/adr-040` | ✓ |
| FastMCP migration functionally complete | ✓ (A2 §A) |
| All 3 entry points wired for `install_project_agent_assets` | ✓ (A2 §B.8-B.10) |
| Claude/Codex provider parity at structural level | ✓ (A_int §D.1-D.4) |
| No unresolved Codex P1 on any merged PR | ✓ (A_int §F) |
| PR #1064 (scaffold template) landed | ⏳ pending (CI Lint & Format red) |
| F40-integration fix agent landed | ⏳ pending |

After PR #1064 + F40-integration land: **cascade is ship-ready**. No architectural concerns. The remaining P2/P3 are post-ship polish.

---

*End of A_int Phase 3.5 cross-track integration audit.*
