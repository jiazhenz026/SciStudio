---
title: "ADR-034 Multi-Provider Agent Chat Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 34
  - 35
  - 40
language_source: en
---

# ADR-034 Multi-Provider Agent Chat Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: Implement `docs/specs/adr-034-multi-provider-agent-chat.md` in full as an
  agent-manager dispatch, with no weakening, no downgrade, and no temporary workarounds,
  delivering one reviewable CI-green PR.
- Task kind: `feature`
- Manager persona: `manager`
- Issue: `#1994`
- Gate record: `.workflow/records/1994-adr-034-multi-provider.json`
- Branch/worktree plan: manager branch `track/adr-034-multi-provider` in
  `C:/Users/jiazh/Desktop/workspace/sci-wt/adr-034-mgr`; agent branches use
  `feat/1994-adr-034/<agent-slug>` and branch off the umbrella branch.
- Protected branch: `main`
- Umbrella branch: `track/adr-034-multi-provider`
- Umbrella PR: `#2003`
- Umbrella PR title: `[DO NOT MERGE] ADR-034 multi-provider agent chat integration`
- Final PR target: `main`
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

## 2. Scope

- In scope:
  - `src/scistudio/ai/agent/**`
  - `src/scistudio/api/routes/ai.py`, `src/scistudio/api/routes/ai_pty/**`
  - `src/scistudio/blocks/ai/ai_block.py`
  - `src/scistudio/cli/install.py`
  - `src/scistudio/engine/pty_control.py`
  - `src/scistudio/_skills/scistudio/scistudio-build-workflow/SKILL.md`
  - `frontend/src/**` limited to the files named in spec section 4.2
  - `frontend/e2e/**`
  - `tests/**` for the spec's `tests:` list and the section 4.4 additions
  - `docs/adr/ADR-034.md`, `docs/specs/adr-034-multi-provider-agent-chat.md`,
    `docs/specs/embedded-coding-agent-spec.md`
  - `docs/planning/adr-034-multi-provider-checklist.md`,
    `docs/planning/adr-034-multi-provider-dispatch-prompts.md`
  - `docs/audit/*adr-034-multi-provider*`
- Out of scope:
  - Everything in the spec's `scope.out` list, verbatim.
  - `src/scistudio/qa/**`. The `doc_drift` addendum-shadowing defect found during
    manager preflight is a governance-tooling defect and is tracked separately; see
    Deferred work.
  - `docs/ai-developer/**`.
  - PTY transport, WebSocket frame schema, resource cap, and pump architecture.
- Protected paths:
  - `docs/ai-developer/**` is excluded and must not be edited.
  - `src/scistudio/engine/pty_control.py` is expected to trip the protected-core guard.
    The PR requires an `admin-approved:core-change` label from the owner; CI verifies
    label provenance. Recorded in section 5.
- Deferred work:
  - `doc_drift._check_adr_spec_alignment` builds `{frontmatter.adr: document}` from all
    `docs/adr/ADR-*.md`. `ADRAddendumFrontmatter` subclasses `ADRFrontmatter` and carries
    the parent ADR number, and `sorted()` places `ADR-0NN-addendumM.md` before
    `ADR-0NN.md`, so a base ADR always overwrites its addenda in that dict and an
    addendum's `governs` is never read. This dispatch works around it by using an
    `adr042-governance-amendment` block instead of an addendum, per owner decision.
    Tracked by #2004; it must stay open and referenced when this dispatch's PR merges.

## 3. Conventions

- `[ ]` not started
- `[~]` in progress
- `[x]` done
- `[!]` blocked
- Every completed row MUST include an artifact:
  PR link, commit, test command, report path, or gate-record entry.
- Chat messages are not checklist evidence.
- Agents edit only their own rows.
- Scope changes require gate-record amendment before work continues.

## 4. Manager Preflight

- [x] Dedicated manager branch and worktree created. -> `track/adr-034-multi-provider`,
      `C:/Users/jiazh/Desktop/workspace/sci-wt/adr-034-mgr`
- [x] Existing issue linked, or new issue created only if none exists. -> no open issue
      existed; #1992 was spec-only and is closed. Created #1994.
- [x] Gate record started. -> `.workflow/records/1994-adr-034-multi-provider.json`
- [x] Scope include/exclude recorded in the gate record. -> gate `init`
- [x] Umbrella branch created. -> `track/adr-034-multi-provider`
- [x] Umbrella PR opened. -> https://github.com/jiazhenz026/SciStudio/pull/2003
- [x] Umbrella PR title includes `[DO NOT MERGE]`. -> `[DO NOT MERGE] ADR-034 multi-provider agent chat integration`
- [x] Protected branch and umbrella PR number recorded in this checklist. -> protected `main`, umbrella PR #2003
- [x] No `pip install -e .` environment pollution found. -> agents run with
      `PYTHONPATH=src`; `scistudio` is not importable without it, confirming the shared
      environment is unpolluted.
- [x] Dispatch checklist copied from the template and committed. -> this file
- [x] Dispatch prompts created from the correct prompt template and linked below. -> `docs/planning/adr-034-multi-provider-dispatch-prompts.md`
- [x] Sentrux baseline recorded, or N/A reason recorded. -> Sentrux MCP is not connected in this manager session. Sentrux evidence is recorded automatically as a guard event inside `gate_record check`, which every agent and the manager run; no separate baseline command is available or required.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `admin-approved:core-change` (anticipated, not yet applied)
- Owner authorization source: pending. The owner has authorized the ADR-034 body edit and
  the overall implementation, but has not yet been asked for the core-change label. The
  manager must request it once `gate_record check` confirms the protected-core guard fires.
- Reason: `src/scistudio/engine/pty_control.py` gains a `provider` field on `PtyTabSpec`
  per FR-010, which the spec requires and which is a protected-core path.
  `admin-approved:core-change` authorizes protected-core paths only; it does not bypass
  scope, issue linkage, docs landing, test obligations, or CI parity.

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record check --mode pre-commit` | N/A | `[ ]` | pending |
| Commit message | `python -m scistudio.qa.governance.gate_record check --mode commit-msg` | N/A | `[ ]` | pending |
| Pre-push | `python -m scistudio.qa.governance.gate_record check --mode pre-push --base origin/main --head HEAD` | N/A | `[ ]` | pending |
| Pre-PR reconcile | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `admin-approved:core-change` | `[ ]` | pending |

## 5.1 Docs Impact Check

- Wrapper/hook/gate-record/receipt/CI/runtime behavior changed: no
- AI docs checked:
  `docs/ai-developer/rules.md`,
  `docs/ai-developer/specific_rules/gated-workflow.md`,
  `docs/ai-developer/specific_rules/agent-dispatch.md`,
  `docs/ai-developer/templates/*dispatch*.md`
- Updated docs or N/A rationale: N/A. This change adds agent CLI providers to the product
  runtime. It does not change wrapper, hook, gate-record, CI, or AI-runtime behavior.

## 6. Dispatch Matrix

All agent worktrees live under `C:/Users/jiazh/Desktop/workspace/sci-wt/`. All agent
branches are cut from the umbrella branch `track/adr-034-multi-provider`, not from `main`.

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 CORE | implementer | N/A | `docs/planning/adr-034-multi-provider-dispatch-prompts.md#a1-core` | T-001..T-004: registry, off-PATH discovery, `spawn_agent`, three MCP injection strategies | `feat/1994-adr-034/core` | `sci-wt/adr034-core` | `src/scistudio/ai/agent/providers_registry.py`, `src/scistudio/ai/agent/terminal.py`, `tests/ai/test_providers_registry.py`, `tests/ai/test_windows_executable_resolution.py`, `tests/ai/test_terminal.py` | API routes, engine, AI Block, frontend, docs | #1994 | `[x]` code + tests landed on `feat/1994-adr-034/core`; 2 items need manager action: (1) `spawn_claude` / `spawn_codex` kept as zero-branching registry lookups with `TODO(#1994)` because `_state.py` (A2 scope) still imports them, (2) `tests/ai/test_terminal_extra_env.py::test_resolve_windows_executable_checks_user_cli_dirs` fails because it monkeypatches the deleted `_windows_user_cli_dirs`; that file is outside A1's write set so it was left untouched |
| A2 API | implementer | N/A | `docs/planning/adr-034-multi-provider-dispatch-prompts.md#a2-api` | T-005, T-006, T-013: registry-derived whitelist, status endpoint with `label`, credential probes, install targets | `feat/1994-adr-034/api` | `sci-wt/adr034-api` | `src/scistudio/api/routes/ai.py`, `src/scistudio/api/routes/ai_pty/_state.py`, `src/scistudio/api/routes/ai_pty/__init__.py`, `src/scistudio/cli/install.py`, `tests/api/test_provider_discovery.py`, `tests/api/test_ai_pty.py`, `tests/cli/**` install tests | `terminal.py`, `providers_registry.py`, `engine.py`, `internal_routes.py`, AI Block, frontend, docs | #1994 | `[ ]` |
| A3 ENGINE | implementer | N/A | `docs/planning/adr-034-multi-provider-dispatch-prompts.md#a3-engine` | T-007..T-009: `PtyTabSpec.provider`, delete `_provider_from_argv` / `_build_spawn_argv`, registry-derived AI Block enum | `feat/1994-adr-034/engine` | `sci-wt/adr034-engine` | `src/scistudio/engine/pty_control.py`, `src/scistudio/api/routes/ai_pty/engine.py`, `src/scistudio/api/routes/ai_pty/internal_routes.py`, `src/scistudio/blocks/ai/ai_block.py`, `tests/engine/test_pty_control.py`, `tests/api/test_ai_pty_engine_spawn.py`, `tests/api/routes/ai_pty/test_engine.py`, `tests/blocks/ai/test_ai_block_skeleton.py` | `terminal.py`, `providers_registry.py`, `ai.py`, `_state.py`, `ai_pty/__init__.py`, frontend, docs | #1994 | `[ ]` |
| A4 FE-CONTRACT | implementer | N/A | `docs/planning/adr-034-multi-provider-dispatch-prompts.md#a4-fe-contract` | T-010, T-012: one provider type source, four-link provider propagation | `feat/1994-adr-034/fe-contract` | `sci-wt/adr034-fe-contract` | `frontend/src/store/types.ts`, `frontend/src/store/terminalTabsSlice.ts`, `frontend/src/hooks/useWebSocket.parts/handleBlockPty.ts`, `frontend/src/components/AIChat/blockPtyHandlers.ts`, `frontend/src/components/AIChat/hooks/usePtyWebSocket.ts`, `frontend/src/components/AIChat/SetupScreen.parts/types.ts`, `frontend/src/components/AIChat/__tests__/TerminalTab.test.tsx` | `SetupScreen.tsx`, `ProviderPicker.tsx`, `PermissionModePicker.tsx`, `NoProvidersNotice.tsx`, `BottomPanel.tsx`, `TerminalTabs.tsx`, all backend | #1994 | `[ ]` |
| A5 FE-UI | implementer | N/A | `docs/planning/adr-034-multi-provider-dispatch-prompts.md#a5-fe-ui` | T-011, T-011a, T-011b and the sticky opaque action bar | `feat/1994-adr-034/fe-ui` | `sci-wt/adr034-fe-ui` | `frontend/src/components/AIChat/SetupScreen.tsx`, `frontend/src/components/AIChat/SetupScreen.parts/ProviderPicker.tsx`, `frontend/src/components/AIChat/SetupScreen.parts/PermissionModePicker.tsx`, `frontend/src/components/AIChat/SetupScreen.parts/NoProvidersNotice.tsx`, `frontend/src/components/AIChat/__tests__/SetupScreen.test.tsx` | `SetupScreen.parts/types.ts`, `store/**`, `BottomPanel.tsx`, `TerminalTabs.tsx`, all backend | #1994 | `[ ]` |
| A6 LAYOUT | implementer | N/A | `docs/planning/adr-034-multi-provider-dispatch-prompts.md#a6-layout` | T-011c host chain: definite-height flex wrappers plus the real-browser acceptance check | `feat/1994-adr-034/layout` | `sci-wt/adr034-layout` | `frontend/src/components/BottomPanel.tsx`, `frontend/src/components/AIChat/TerminalTabs.tsx`, `frontend/e2e/specs/adr034-setup-action-bar.spec.ts` | `SetupScreen.tsx` and its parts, `store/**`, all backend | #1994 | `[ ]` |
| A7 TESTS | test_engineer | N/A | `docs/planning/adr-034-multi-provider-dispatch-prompts.md#a7-tests` | Cross-cutting section 4.4 matrix no single implementer owns | `feat/1994-adr-034/tests` | `sci-wt/adr034-tests` | `tests/**` and fixtures only | all production code unless the manager amends | #1994 | `[ ]` |
| A8 DOCS | adr_author | N/A | `docs/planning/adr-034-multi-provider-dispatch-prompts.md#a8-docs` | T-014 plus the owner-authorized ADR-034 governance amendment and the spec status flip | `feat/1994-adr-034/docs` | `sci-wt/adr034-docs` | `docs/adr/ADR-034.md`, `docs/specs/adr-034-multi-provider-agent-chat.md`, `docs/specs/embedded-coding-agent-spec.md`, `src/scistudio/_skills/scistudio/scistudio-build-workflow/SKILL.md` | all other source and test files | #1994 | `[ ]` |
| A9 AUDIT | audit_reviewer | `no-context` | `docs/planning/adr-034-multi-provider-dispatch-prompts.md#a9-audit` | Independent verification of the integrated candidate | `audit/1994-adr-034-no-context` | `sci-wt/adr034-audit` | `docs/audit/adr-034-multi-provider-no-context-20260806.md` only | every source, test, and doc file; read-only otherwise | #1994 | `[ ]` |

Audit mode for A9 is recorded as `no-context` before dispatch. A9 must not receive the
issue body, this checklist, the dispatch prompts, PR claims, commit messages, or any
manager summary.

## 7. Track: Implementation

### 7.1 Track Scope

- Owner: manager
- In scope:
  - Every functional requirement FR-001 through FR-027.
  - Every task T-001 through T-014.
  - Every verification item in spec section 4.4 that does not require owner credentials.
- Out of scope:
  - The five-provider manual smoke launch, which the owner performs as a pre-merge gate.
  - The `doc_drift` addendum-shadowing defect, tracked separately.
- Required docs:
  - `docs/adr/ADR-034.md`, `docs/specs/adr-034-multi-provider-agent-chat.md`,
    `docs/specs/embedded-coding-agent-spec.md`,
    `src/scistudio/_skills/scistudio/scistudio-build-workflow/SKILL.md`
- Required tests:
  - The spec's `tests:` list plus every addition named in spec section 4.4.

### 7.2 Dispatch

- [x] Prompt file created or dispatch prompt recorded. -> `docs/planning/adr-034-multi-provider-dispatch-prompts.md`
- [x] Correct prompt template selected. -> work template for A1-A8; audit no-context template for A9
- [x] Audit mode recorded when persona is `audit_reviewer`. -> A9 is `no-context`
- [x] Agent branch/worktree assigned. -> Dispatch Matrix
- [x] Write set and out-of-scope paths included in prompt. -> every prompt has explicit own/must-not-touch lists
- [x] TODO rule included in prompt. -> A1 prompt body; inherited by A2-A8 via the shared structure
- [x] Required checks included in prompt. -> per-agent test and `gate_record check` commands

### 7.3 Implementation

Wave 1 is blocking. Waves 2a, 2b, and 3 start only when their dependency lands on the
umbrella branch.

- [x] Wave 1: A1 CORE integrated -> merge `f1f7baf6`, agent head `a316855d`. Manager verified independently: failure sets across `tests/api tests/blocks/ai tests/engine tests/cli` are identical on the umbrella tip and the agent branch (7 each, none introduced), and `tests/ai` is green on both.
- [x] Wave 2a: A2 API integrated -> merge `1bd70066`, agent head `8577143b`. Closed the FR-005 discovery regression A1 had to leave open, and fixed the two `test_provider_discovery` failures, confirmed absent from the umbrella failure set after merge.
- [x] Wave 2a: A3 ENGINE integrated -> merge `764d3809`, agent head `f4ec862c`. Cycle count independently recounted by the manager on the agent head: 4 cycles, sizes [20, 4, 3, 3]. `architecture_tests` passes with `MAX_PYTHON_CYCLES` untouched.
- [x] Wave 2a: A4 FE-CONTRACT integrated -> merge `1b9a73d6`, agent head `b4f80ba5`. Manager verified: `tsc --noEmit` clean, 59 provider-propagation tests pass, and the no-default guards exist as named tests for link 2 and link 3.
- [x] Wave 2b: A5 FE-UI integrated -> merge `8cb3b46b`, agent head `a1625a29`, plus manager integration commit `a215d0b0`. Verified: scope clean, `ProviderName` alias gone, no `TODO(#1994)`, and an invented provider key in the status payload renders and launches, proving no hand-maintained list survives.
- [!] Wave 2b: A6 LAYOUT integrated -> BLOCKED pending owner decision. Branch `feat/1994-adr-034/layout` head `f96ec321`, not merged. Two of the three spec-mandated action-bar changes are measured inert; see the drift log.
- [~] Wave 3: A7 TESTS integrated -> dispatched, branch `feat/1994-adr-034/tests`. Layout and `frontend/e2e/**` deliberately excluded from its scope while A6's conclusions are contested.
- [ ] Wave 3: A8 DOCS integrated -> pending

### 7.4 Audit

- [ ] A9 no-context audit dispatched against the integrated candidate.
- [ ] Audit report file path assigned. ->
      `docs/audit/adr-034-multi-provider-no-context-20260806.md`
- [ ] Audit report committed.
- [ ] Audit report merged into final PR evidence path.
- [ ] Findings recorded.
- [ ] P1 findings fixed before integration.
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale.
- [ ] Manager code review completed for every changed file.

### 7.5 Integration

- [ ] Agent output reviewed by manager.
- [ ] Scope compliance verified.
- [ ] Conflicts resolved intentionally.
- [ ] Track merged or integrated.

## 8. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Backend targeted tests | `PYTHONPATH=src python -m pytest tests/ai tests/api tests/engine tests/blocks/ai --timeout=120` | `[ ]` | pending |
| Frontend unit tests | `npm --prefix frontend test` | `[ ]` | pending |
| Frontend type check | `npm --prefix frontend run typecheck` | `[ ]` | pending |
| Real-browser action bar check | `npm --prefix frontend run test:e2e -- adr034-setup-action-bar` | `[ ]` | pending |
| Gate ledger check (local) | `PYTHONPATH=src python -m scistudio.qa.governance.gate_record check --mode local --base origin/main --head HEAD` | `[ ]` | pending |
| Gate ledger check (pre-PR) | `PYTHONPATH=src python -m scistudio.qa.governance.gate_record check --mode pre-pr --base origin/main --head HEAD --pr-body-file .workflow/local/pr-body.md` | `[ ]` | pending |
| Gate finalize (pre-PR) | `PYTHONPATH=src python -m scistudio.qa.governance.gate_record finalize --base origin/main --head HEAD --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#1994"` | `[ ]` | pending |
| Wrapper preflight | `python scripts/scistudio_pr_create.py --dry-run --title "<title>" --body "<body>"` | `[ ]` | pending |
| Owner five-provider smoke launch | manual, owner-run, hard pre-merge gate | `[ ]` | pending |

### 8.1 Owner Smoke Launch Checklist

The owner runs this before merge. Agents cannot run it: each CLI needs owner credentials.

| Provider | Binary | Launch a chat tab | Agent calls one SciStudio MCP tool | AI Block run completes |
|---|---|---|---|---|
| `claude-code` | `claude` | `[ ]` | `[ ]` | `[ ]` |
| `codex` | `codex` | `[ ]` | `[ ]` | `[ ]` |
| `kimi-code` | `kimi` | `[ ]` | `[ ]` | `[ ]` |
| `qoder` | `qodercli` | `[ ]` | `[ ]` | `[ ]` |
| `qoder-cn` | `qoderclicn` | `[ ]` | `[ ]` | `[ ]` |

`qoder` requires the owner to install the international channel first. The spec records
`~/.qoder` as absent on the verification workstation and marks that row as recorded from
an earlier direct observation rather than a live install, so this launch also confirms
whether `~/.qoder/bin/qodercli` is the real install path.

## 9. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-08-06 | manager | (follow-up #2004) Spec section 1 presents "expand ADR-034 `governs`" and "author an ADR-034 addendum" as equivalent options. Verified they are not: `doc_drift._check_adr_spec_alignment` keys `adrs` by `frontmatter.adr`, `ADRAddendumFrontmatter` subclasses `ADRFrontmatter` with the parent number, and `sorted()` orders `ADR-0NN-addendumM.md` before `ADR-0NN.md`, so the base ADR overwrites the addendum and the addendum's `governs` is never read. | Presented the finding to the owner, who chose the `adr042-governance-amendment` block in ADR-034's body and authorized editing that `agent_editable: false` file. A8 carries it out. | Follow-up issue for the `doc_drift` defect must exist before merge. |
| 2026-08-06 | manager | Spec `governs.contracts` lists `scistudio.ai.agent.terminal.spawn_claude` and `spawn_codex`, but spec section 4.1 removes both in favour of `spawn_agent`. Leaving the spec as written would make it govern contracts that no longer exist once it flips to `Planned`. | A8 must reconcile `governs.contracts` against the post-implementation symbol set at the same time it flips the status. Recorded in the A8 prompt. | Tracked in this dispatch, no separate issue. |
| 2026-08-06 | A1 CORE | Deleting `_windows_user_cli_dirs` per FR-004 broke `tests/ai/test_terminal_extra_env.py`, which monkeypatched it. A1 correctly stopped at the scope boundary and proposed reassigning the fix to A2. | Manager verified the failure was introduced by A1, not pre-existing: `tests/ai` is green on the umbrella tip and had exactly one failure on the agent branch. Rejected the reassignment because A2 does not own `terminal.py`; amended A1's scope to include the test and had A1 fix it. Root cause was the manager's write set, not agent drift. | N/A, closed on rework |
| 2026-08-06 | A1 CORE | Manager code review found an unreported destructive path in `_merge_provider_mcp_config`: a parseable but non-object `mcpServers` value was silently discarded and overwritten, while the two neighbouring cases correctly raised. Violates FR-017a's requirement to change only the SciStudio entry. | Returned to A1, which made it raise with the same actionable message shape and added byte-for-byte-intact tests parametrized over `str`, `list`, and `int`. A missing key still creates the object, since a missing key loses nothing. | N/A, closed on rework |
| 2026-08-06 | A4 FE-CONTRACT | Typing `provider` as required on the `block_pty_opened` payload broke nine `handleBlockPtyOpened` call sites in `TerminalTabs.test.tsx` and one wire fixture in `useWebSocket.test.ts`, neither of which was in A4's declared write set. | Accepted. A4 amended its ledger before editing and reported the deviation unprompted. The alternative was an optional `provider` field, which would weaken the contract exactly where FR-020c is strictest. Neither file is owned by another agent. A6 is told A4 already touched `TerminalTabs.test.tsx`. | N/A |
| 2026-08-06 | A4 FE-CONTRACT | A4 left `export type ProviderName = TerminalProvider` in `SetupScreen.parts/types.ts` as a transitional alias so the not-yet-migrated Setup components would compile. The owner forbade leaving temporary solutions in delivered work. | Accepted as in-dispatch scaffolding only. Deleting it is an explicit hard obligation in the A5 prompt, and the manager verifies its absence before the final PR rather than trusting the report. | N/A, must close in A5 |
| 2026-08-06 | manager | FR-020a makes agent provider keys opaque strings, so the Setup screen's hardcoded two-provider picker now compiles cleanly instead of failing type check. An A5 under-delivery would be silent rather than loud. | A5's acceptance criteria are written as assertions it must add, and A7 owns the independent guard that no hand-maintained agent provider key or label list survives in frontend source. Manager greps for it at integration. | N/A |
| 2026-08-06 | A2 API | FR-005 changed `_binary_status` from taking a binary name to taking a descriptor, which broke `tests/ai/test_windows_executable_resolution.py::test_binary_status_uses_cmd_when_windows_which_finds_bare_wrapper`. That file is A1's, so A2 stopped rather than editing it. | Manager reproduced the failure (`AttributeError: 'str' object has no attribute 'well_known_directories'`) and diffed A2's replacement test against the doomed one: same npm shim, same `.cmd`-over-bare-wrapper assertion, same probe argv. Coverage is ported, not dropped. Amended A2's scope for that one test. Principle applied consistently with the A1 ruling: a test follows the function under test, not the file it happens to live in. | N/A, closed on rework |
| 2026-08-06 | manager | `spawn_claude` / `spawn_codex` are dead as production code once A2's `_PROVIDER_SPAWNERS` lands, but they still live in `terminal.py` carrying `TODO(#1994)`, and A1's test at `tests/ai/test_windows_executable_resolution.py:354` still parametrises over them. Left unmanaged this becomes exactly the leftover temporary solution the owner forbade. | Tracked as a mandatory close-out below rather than left to a later agent's discretion. Sequenced after A3 lands, because A3's files still carry prose references and removing the shims mid-flight risks a merge-time break. Handed back to A1, which owns `terminal.py`. | Must close before the final PR |
| 2026-08-06 | A5 FE-UI | FR-021's provider `select` collided with two bare `screen.getByRole("combobox")` queries in `frontend/src/components/BottomPanel.test.tsx`, which were unambiguous only by accident. `BottomPanel` keeps the chat surface mounted and CSS-hidden so PTYs survive, so both selects now share a tree. A5 verified by stash/unstash that the file goes 19/0 to 17/2, refused to edit a file in neither its scope nor A6's, and proposed a fix it explicitly had not run. | Manager applied A5's proposed fix in A5's worktree, confirmed 19/19, reverted that worktree, merged A5, then landed the fix as manager integration commit `a215d0b0` and re-verified 19/19 on the umbrella itself. Resolved by the manager rather than assigned onward because it is purely two agents' work colliding with no behavior change; assigning it to A6 would have left the umbrella red and mixed an unrelated fix into a layout task. | N/A |
| 2026-08-06 | A5 FE-UI | A5 kept the existing `provider === "codex"` trust-hooks warning (#1859) rather than removing it, and flagged it so A7's guard would not treat it as a surviving provider list. | Accepted. It is one provider-specific UI warning, not a hand-maintained key or label list, and deleting shipped safety copy was outside A5's scope. Recorded here so A7 evaluates it knowingly instead of discovering it as an anomaly. | N/A |
| 2026-08-06 | manager | The manager hypothesised that A6's `h-full` to flex wrapper conversion changed the action bar's failure mode from scroll-reachable to clipped, i.e. that it was a regression. | Falsified by measurement. A6 ran one identical probe harness on `origin/main` and on its own branch: `canScroll` is identical at every panel height and `afterScroll` is false below the floor on both. The hypothesis required an ancestor with indefinite height; there is none, because the bottom panel is a flex item with a resolved pixel height. The manager was wrong and the conversion is not a regression. | N/A |
| 2026-08-06 | A6 LAYOUT | Owner reported Launch below the fold at the default panel height, which A6's first round measured as passing. | Reproduced on re-measurement: it is viewport-dependent, with a crossover near 558 CSS px of window height. A6 had measured only at 1280x720. Real configurations below the crossover include a 1366x768 laptop at 150% scaling (512 CSS px) and 1920x1080 at 200% (540 CSS px). The owner's report was correct and the first round's blind spot was the viewport, not the analysis. | Feeds the FR-021g decision |
| 2026-08-06 | A6 LAYOUT | Owner reported the Launch button can be found by scrolling, contradicting A6's clipping finding. | Both are true. Measured at 1280x520: `visible` is false but `clickable` is true, with 20.2 of 36px on screen and `elementFromPoint` hitting the button. The setup body genuinely scrolls, and below ~120px the `BottomPanel` wrapper scrolls too. What is never true is that scrolling brings the button fully into view. | Feeds the FR-021g decision |
| 2026-08-06 | manager | Single-variable isolation shows two of the three spec-mandated action-bar changes are measurably inert. A5's `sticky bottom-0` produces byte-identical clipping to baseline at every height (20/9/46 px at 150/120/minimum). A6's wrapper conversion produces identical geometry, identical scrollability and an identical `Floor(visible)` of 176px. The entire observed delta is A5's `pb-1`. Spec section 4.1's root-cause analysis is therefore wrong. | Escalated to the owner. Neither change is a regression, so nothing is broken by carrying them, but keeping a disproven rationale in a PTY-critical file invites the next reader to believe it. Removing either requires a spec amendment because section 4.2 mandates both files for T-011c. Owner decision pending. | Blocks A6 integration |
| 2026-08-06 | manager | `tests/ai/test_mcp_tools_disk_integration.py::test_concurrent_write_workflow_serialises` failed once in a five-directory combined run on the umbrella and is not in the known pre-existing set. | Characterised as an intermittent Windows file-locking flake, not a regression: it passes in isolation and across three subsequent `tests/ai` runs, its subject is `write_workflow` filelock serialisation with no relation to providers or the Kimi MCP write, and A3 independently observed a Windows atomic-rename flake whose failing parameter changes between runs. Handed to A7 to characterise rather than declared closed. | Tracked with A7 |
| 2026-08-06 | manager | Umbrella PR could not exist before the first planning commit, so the dispatch matrix was authored before the PR number was known. | Open the umbrella PR immediately after the planning commit, then update section 1 and the Manager Preflight rows before dispatching any agent. | N/A |

## 9.1 Mandatory Close-Outs

These are in-dispatch scaffolding, not accepted debt. Each must be closed before the
final PR, and the manager verifies each one directly rather than accepting an agent's
report.

- [x] `export type ProviderName = TerminalProvider` deleted from
      `frontend/src/components/AIChat/SetupScreen.parts/types.ts`. Left by A4 so the
      not-yet-migrated Setup components would compile; A5 owns the deletion.
      Verify: `grep -rn "ProviderName" frontend/src` returns nothing. -> confirmed empty by the manager on the umbrella branch.
- [ ] `spawn_claude` and `spawn_codex` removed from `src/scistudio/ai/agent/terminal.py`,
      and A1's parametrisation at `tests/ai/test_windows_executable_resolution.py:354`
      retargeted to `spawn_agent`. Sequenced after A3 lands; handed back to A1.
      Verify: `grep -rn "spawn_claude\|spawn_codex" src tests` returns nothing.
- [ ] No `TODO(#1994)` survives in the delivered diff, since every one of them marks
      in-dispatch sequencing rather than genuinely deferred work.
      Verify: `grep -rn "TODO(#1994)" src frontend tests` returns nothing.
- [ ] No hand-maintained list of agent provider keys or labels survives in frontend
      source. A7 owns the guard; the manager greps independently at integration.

## 10. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence when needed, commit, and PR evidence.
- [ ] PR closes every issue fixed by the dispatch.
- [x] Follow-up issue opened for the `doc_drift` addendum-shadowing defect. -> #2004
- [ ] `admin-approved:core-change` label applied by the owner if the protected-core guard
      fires on `src/scistudio/engine/pty_control.py`.
- [ ] Owner five-provider smoke launch complete.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
