---
title: "ADR-034 Multi-Provider Agent Chat Dispatch Prompts"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 34
  - 35
  - 40
language_source: en
---

# ADR-034 Multi-Provider Agent Chat Dispatch Prompts

Filled from `docs/ai-developer/templates/agent-dispatch-prompt-template.md` for A1 to A8,
and from `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`
for A9.

Checklist: `docs/planning/adr-034-multi-provider-checklist.md`.

## 0. Shared Cross-Agent Contracts

These are frozen at dispatch so agents working in parallel agree without talking to each
other. An agent that believes one of these is wrong MUST stop and report to the manager
rather than changing it unilaterally. Changing one of these silently breaks another
agent's assumptions and is a dispatch failure.

### 0.1 Registry public surface

A1 creates `src/scistudio/ai/agent/providers_registry.py`. A1 owns the internal design,
but the following import surface is a contract other agents code against:

```python
ProviderKind          # enum: AGENT, TERMINAL
McpInjection          # strategy descriptor: flag | codex_overrides | project_file
SystemPromptInjection # strategy descriptor: flag_file | ambient
CredentialProbe       # credential_path template + optional auth status argv
ProviderDescriptor    # key, label, kind, binary_candidates, well_known_dirs,
                      # config_root, config_root_env, mcp, system_prompt,
                      # credentials, bypass_argv
REGISTRY              # ordered ProviderRegistry instance

def get(key: str) -> ProviderDescriptor        # raises KeyError on unknown key
def agent_descriptors() -> tuple[ProviderDescriptor, ...]
def agent_keys() -> tuple[str, ...]            # registry order, agents only
def resolve_binary(descriptor) -> Path | None  # off-PATH aware, exact-name only
def spawn_agent(descriptor, ...) -> PtyProcess # in terminal.py, not the registry
```

`providers_registry.py` MUST NOT import from `scistudio.api` or `scistudio.blocks`.

Registry order is `claude-code`, `codex`, `kimi-code`, `qoder`, `qoder-cn`, then the
`user-terminal` TERMINAL-kind entry. `agent_keys()` excludes `user-terminal`.

### 0.2 `GET /api/ai/status` entry shape

```json
{"name": "kimi-code", "available": true, "version": "0.33.0",
 "logged_in": false, "label": "Kimi Code"}
```

`label` is new and additive per FR-020b. The other four fields keep their current names,
types, and meaning. One entry per `agent_keys()` element, in registry order.

### 0.3 `PtyTabSpec`

Gains `provider: str`. Drops `spawn_argv`; the manager preflight confirmed the spec's
finding that no consumer reads it. If an agent finds a live consumer, stop and report.

### 0.4 `block_pty_opened` WebSocket payload

Gains `provider: str`, carrying the provider the engine actually spawned. Every link
forwards it and no link substitutes a default: engine emit -> `handleBlockPty.ts` ->
`blockPtyHandlers.handleBlockPtyOpened` -> `addAiBlockTerminalTab`.

### 0.5 Frontend provider typing

Per FR-020a, agent provider keys are opaque strings validated at runtime against the
status payload. There is no hand-maintained TypeScript literal union of agent keys and no
frontend label map. `user-terminal` stays a literal because the frontend branches on it to
route between the chat and terminal surfaces.

### 0.6 Verified provider facts

The identity and adapter tables in spec section 1 are the authoritative input. Do not
re-derive them, do not guess a flag spelling, and do not "fix" a row. If a probe on the
local machine contradicts a row, stop and report to the manager; the spec records a
verification date and a contradiction is a real finding, not a licence to edit.

---

## A1 CORE

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement docs/specs/adr-034-multi-provider-agent-chat.md in full, with no
  weakening, no downgrade, and no temporary workarounds.
- Task kind: feature
- Persona: implementer
- Issue: #1994
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/1994
- Umbrella PR: see checklist section 1 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-034-multi-provider
- Agent branch: feat/1994-adr-034/core
- Agent worktree: C:/Users/jiazh/Desktop/workspace/sci-wt/adr034-core
- Gate record: your own, created with gate_record init for this branch
- Checklist: docs/planning/adr-034-multi-provider-checklist.md

## Required Rules

Read and follow:

- The GitHub issue #1994 and all owner instructions in it.
- docs/specs/adr-034-multi-provider-agent-chat.md, especially section 1 verified facts,
  FR-001 to FR-005, FR-007, FR-016 to FR-019, FR-025 to FR-027, sections 4.1 and 4.4.
- docs/planning/adr-034-multi-provider-dispatch-prompts.md section 0.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md

## Scope

You own only:

- src/scistudio/ai/agent/providers_registry.py (create)
- src/scistudio/ai/agent/terminal.py
- tests/ai/test_providers_registry.py (create)
- tests/ai/test_windows_executable_resolution.py (create)
- tests/ai/test_terminal.py

You must not touch:

- src/scistudio/api/**, src/scistudio/blocks/**, src/scistudio/engine/**,
  src/scistudio/cli/**
- frontend/**
- docs/**
- Any test file outside the list above.

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- You are not alone in this codebase. A2, A3, A4 start as soon as your work lands and code
  against the section 0.1 import surface. Providing that surface is part of your task.
- MUST work only on branch feat/1994-adr-034/core, cut from track/adr-034-multi-provider.
- MUST work only in worktree C:/Users/jiazh/Desktop/workspace/sci-wt/adr034-core.
- MUST NOT use `pip install -e .`. Run Python as `PYTHONPATH=src python ...`.
- Do not revert or overwrite other agents' work. Do not broaden scope.
- MUST NOT merge any PR.
- Edit only checklist row A1 CORE.

## TODO And Deferral Rule

Deferred work must be tracked in the repo. Use `TODO(#NNN): <reason>` citing an issue, ADR,
spec, or follow-up ticket. Do not leave hidden V1, MVP, or later work. The owner
explicitly forbade temporary solutions, so prefer stopping and reporting over deferring.

Known deferred items: N/A.

## Work To Do

1. T-001. Create `providers_registry.py` with the descriptor dataclasses named in the spec
   Key Entities table and the five agent descriptors plus the `user-terminal` entry,
   populated from the spec section 1 identity and adapter tables. `qoder` and `qoder-cn`
   MUST be two independent descriptor instances that share strategy fields, per FR-025 and
   FR-026; a shared construction helper is fine, one descriptor with two binary candidates
   is not. The module MUST NOT import from `scistudio.api` or `scistudio.blocks`.
2. T-002. Replace `_windows_user_cli_dirs()` with descriptor-supplied well-known
   directories on `resolve_windows_executable`, per FR-004. Matching MUST be exact binary
   name within a registered well-known directory, per FR-027, so `~/.qodersec/bin/
   qodercli.exe` is never selected. A missing channel binary MUST NOT resolve to the
   sibling channel's binary.
3. T-003. Replace `spawn_claude` / `spawn_codex` with one descriptor-driven `spawn_agent`,
   per FR-007. Delete the `if provider == ... elif ...` chains rather than extending them.
   Keep the old names only if a test genuinely depends on them, and if you keep them make
   them thin registry lookups with no branching; prefer removing them and updating the
   test.
4. T-004. Implement the three MCP injection strategies: explicit `--mcp-config` flag
   (`claude-code`, `qoder`, `qoder-cn`), Codex `-c` overrides (`codex`), and a
   project-scope file write (`kimi-code`). The payload stays the existing
   `_mcp_entry_payload(project_dir)` for all of them, per FR-018.
5. The Kimi write MUST NOT reuse `_ensure_mcp_config`. That helper rewrites the whole file,
   which is correct for `<project>/.scistudio/mcp.json` because SciStudio owns it, and
   destructive for `<project>/.kimi-code/mcp.json` because Kimi owns it and the user may
   have registered their own servers there. Implement read, merge only the SciStudio entry,
   atomic replace, per FR-017a. An existing-but-unparseable file MUST raise an actionable
   error and MUST NOT be overwritten, per FR-017b. Follow the merge-preserving precedent in
   `src/scistudio/cli/install.py`, not `_ensure_mcp_config`.
6. Honour `KIMI_CODE_HOME` for Kimi's config root. The CLI's own documentation instructs
   callers never to assume `~/.kimi-code`.
7. Do not use Qoder's `--append-system-prompt`. It takes literal text with no `@<file>`
   indirection and the composed prompt is unbounded. Both Qoder channels receive the
   prompt through `.agents/skills` like Codex does, per spec section 4.1. Skill
   provisioning is unchanged; add no new skills tree, per FR-019.
8. Add the tests listed under Required Tests below. Registry completeness must fail at test
   time, not at spawn time.

## Required Tests And Checks

- Registry unit tests: every agent descriptor declares a complete adapter definition; both
  Qoder channels present as distinct keys; `agent_keys()` excludes `user-terminal`.
- Argv snapshot test per provider asserting no provider's flag spelling appears in another
  provider's argv. `--dangerously-skip-permissions` in a Codex argv is a failure.
- Off-PATH discovery test using a fake home containing `.kimi-code/bin/`,
  `.qoder/bin/qodercli/`, and `.qoder-cn/bin/qoderclicn/`. Must not depend on the CLIs
  installed on this machine.
- Sidecar rejection test: a fake home with `.qodersec/bin/qodercli.exe` and no real Qoder
  install must resolve both Qoder channels to None.
- Channel isolation test: a fake home with only one Qoder channel must not resolve the
  other to the installed sibling.
- Kimi MCP merge test: seed `.kimi-code/mcp.json` with an unrelated server, inject, assert
  the unrelated entry survives and only the SciStudio entry changed. Companion test: a
  malformed file raises instead of being overwritten.
- `PYTHONPATH=src python -m pytest tests/ai --timeout=120`
- `PYTHONPATH=src python -m scistudio.qa.governance.gate_record check --base track/adr-034-multi-provider --head HEAD`
- Push your branch. Do not open a PR to main. The manager integrates.

N/A: no docs in your scope; A8 owns all documentation. No Sentrux CLI run; `gate_record
check` records Sentrux guard evidence.

## Output Required

Before reporting done, provide: changed file paths; tests and checks run with results; the
exact public names your module exports so A2/A3/A4 can import them; checklist row updated;
commit SHA; any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- A local probe contradicts a spec section 1 fact.
- You find a live consumer of `PtyTabSpec.spawn_argv`.
- Removing `spawn_claude` / `spawn_codex` breaks a caller outside your scope.
- The task conflicts with AGENTS.md, ADR, spec, or gate record.
- You cannot add or update required tests.
```

---

## A2 API

Identical Task Identity, Required Rules, Coordination, TODO, and Checks structure as A1,
with these substitutions.

- Agent branch: `feat/1994-adr-034/api`
- Agent worktree: `C:/Users/jiazh/Desktop/workspace/sci-wt/adr034-api`
- Spec focus: FR-003, FR-006, FR-008, FR-009, FR-020b, FR-023; tasks T-005, T-006, T-013.
- Depends on: A1 landed on the umbrella branch. Cut your branch after that.

You own only:

- `src/scistudio/api/routes/ai.py`
- `src/scistudio/api/routes/ai_pty/_state.py`
- `src/scistudio/api/routes/ai_pty/__init__.py`
- `src/scistudio/cli/install.py`
- `tests/api/test_provider_discovery.py`, `tests/api/test_ai_pty.py`, and the install CLI
  test module

You must not touch: `terminal.py`, `providers_registry.py`, `ai_pty/engine.py`,
`ai_pty/internal_routes.py`, `blocks/**`, `engine/**`, `frontend/**`, `docs/**`.

Work to do:

1. T-005. Derive `_VALID_PROVIDERS` and `_PROVIDER_SPAWNERS` from the registry, per FR-006.
   Delete the hand-maintained literals. The WebSocket rejection message MUST enumerate the
   accepted set, per FR-023. Update the WS contract docstring in `ai_pty/__init__.py`.
2. T-005. `GET /api/ai/status` returns one entry per `agent_keys()` in registry order, with
   the section 0.2 shape including the new `label` field, per FR-008 and FR-020b. The
   `user-terminal` pseudo-provider is excluded, per FR-003.
3. T-006. Descriptor-driven credential probes, per FR-009: credential file path check then
   the optional provider-owned auth status command. Both Qoder channels have no auth status
   command; login state comes from `.auth` under each channel's own config root.
4. Version probe MUST time out at 2 s and report `available: false` rather than blocking
   the endpoint, per the spec Edge Cases.
5. T-013. Extend `scistudio install` targets from the registry. Existing `claude` and
   `codex` targets keep working; an unknown target still errors.
6. Tests: status set equals `agent_keys()` rather than a frozen literal; per-provider
   logged-in tests using fake HOME fixtures; WS rejection message enumerates five
   providers; install CLI accepts old and new targets.

Stop and report if the registry surface you need is missing from A1's module, or if you
find any other module still holding a hardcoded provider list that is outside your scope.

---

## A3 ENGINE

Same structure. Substitutions:

- Agent branch: `feat/1994-adr-034/engine`
- Agent worktree: `C:/Users/jiazh/Desktop/workspace/sci-wt/adr034-engine`
- Spec focus: FR-010 to FR-015, FR-022; tasks T-007, T-008, T-009.
- Depends on: A1 landed on the umbrella branch.

You own only:

- `src/scistudio/engine/pty_control.py`
- `src/scistudio/api/routes/ai_pty/engine.py`
- `src/scistudio/api/routes/ai_pty/internal_routes.py`
- `src/scistudio/blocks/ai/ai_block.py`
- `tests/engine/test_pty_control.py`, `tests/api/test_ai_pty_engine_spawn.py`,
  `tests/api/routes/ai_pty/test_engine.py`, `tests/blocks/ai/test_ai_block_skeleton.py`

You must not touch: `terminal.py`, `providers_registry.py`, `routes/ai.py`,
`ai_pty/_state.py`, `ai_pty/__init__.py`, `cli/**`, `frontend/**`, `docs/**`.

`src/scistudio/engine/pty_control.py` is a protected-core path. The manager has recorded
that the PR will need an `admin-approved:core-change` label from the owner. Do not attempt
to apply a label and do not route around the guard; make the change the spec requires and
report the guard output.

Work to do:

1. T-007, ordered first per the spec's rollback note. Add `provider: str` to `PtyTabSpec`,
   accept it in the internal route and `open_engine_initiated_tab`, and delete
   `_provider_from_argv`, per FR-010 and FR-011. Drop `spawn_argv` from `PtyTabSpec`; the
   manager preflight confirmed no consumer reads it, but verify and stop if you find one.
2. Emit `provider` on the `block_pty_opened` payload, per section 0.4 and FR-020c. The
   frontend side of that chain belongs to A4; you own the emit side only.
3. T-008, only after T-007 is green. Delete `AIBlock._build_spawn_argv`, `_BYPASS_FLAG`,
   and `_discover_provider`, per FR-012. The worker MUST NOT compose provider argv, write
   system-prompt files, or write MCP config. This removes the orphaned temp-file leak
   required by FR-013.
4. T-008. `validate_config` rejects unknown providers against the registry. When the
   failure is a missing binary, the error names the provider and its expected binary and
   suggests no `scistudio install` command, per FR-014. That command wires SciStudio's MCP
   server and skills into a CLI the user already has; it cannot install the CLI, so
   suggesting it leaves discovery failing.
5. T-008. AI Block discovery MUST use the registry resolver, not bare `shutil.which`, per
   FR-005, so the chat path and the block path cannot disagree.
6. T-009. `AIBlock.config_schema` `provider` enum derived from `agent_keys()` with
   `claude-code` remaining the default, per FR-015. Existing workflow YAML carrying
   `provider: claude-code` must load unchanged.
7. Tests: replace `test_open_engine_tab_picks_codex_provider_from_argv` with a test
   asserting the engine uses the explicitly supplied provider and ignores argv; assert an
   AI Block run leaves no file in `<project>/.scistudio/.tmp/`; assert the missing-binary
   error names the provider and contains no `scistudio install` string; assert the enum
   lists five providers.

---

## A4 FE-CONTRACT

Same structure. Substitutions:

- Agent branch: `feat/1994-adr-034/fe-contract`
- Agent worktree: `C:/Users/jiazh/Desktop/workspace/sci-wt/adr034-fe-contract`
- Spec focus: FR-020, FR-020a, FR-020c, FR-022; tasks T-010, T-012.
- Depends on: A2 for the status `label` field and A3 for the `block_pty_opened` `provider`
  field. Both are frozen in section 0, so you may start once A1 lands and reconcile at
  integration.

You own only:

- `frontend/src/store/types.ts`
- `frontend/src/store/terminalTabsSlice.ts`
- `frontend/src/hooks/useWebSocket.parts/handleBlockPty.ts`
- `frontend/src/components/AIChat/blockPtyHandlers.ts`
- `frontend/src/components/AIChat/hooks/usePtyWebSocket.ts`
- `frontend/src/components/AIChat/SetupScreen.parts/types.ts`
- `frontend/src/components/AIChat/__tests__/TerminalTab.test.tsx`

You must not touch: `SetupScreen.tsx`, `ProviderPicker.tsx`, `PermissionModePicker.tsx`,
`NoProvidersNotice.tsx`, `BottomPanel.tsx`, `TerminalTabs.tsx`, any backend file, `docs/**`.

Work to do:

1. T-010. Collapse the three duplicated provider union types onto one source in
   `store/types.ts`, per FR-020. `SetupScreen.parts/types.ts` and the inline union in
   `usePtyWebSocket.ts` import or re-export it; they do not redeclare it.
2. T-010. Agent provider keys become opaque strings validated at runtime against the status
   payload, per FR-020a. Do not introduce a hand-maintained literal union of agent keys and
   do not add a frontend label map; labels come from the backend `label` field per FR-020b.
   Keep `user-terminal` a literal because the frontend branches on it for surface routing.
3. T-012. Thread `provider` through all four links, per FR-020c: the `block_pty_opened`
   payload type, the WS dispatch in `handleBlockPty.ts`, `handleBlockPtyOpened` in
   `blockPtyHandlers.ts`, and `addAiBlockTerminalTab` in `terminalTabsSlice.ts`. Remove the
   hardcoded `"claude-code"` in the slice. No link may substitute a default; a missing
   `provider` on the payload is an error, not a fallback.
4. Tests: an engine-initiated Kimi or Qoder tab records that provider end to end, and no
   single link silently substitutes a default.

Checks: `npm --prefix frontend run typecheck`, `npm --prefix frontend test`, then
`gate_record check`.

---

## A5 FE-UI

Same structure. Substitutions:

- Agent branch: `feat/1994-adr-034/fe-ui`
- Agent worktree: `C:/Users/jiazh/Desktop/workspace/sci-wt/adr034-fe-ui`
- Spec focus: FR-021, FR-021a to FR-021i; tasks T-011, T-011a, T-011b, and the SetupScreen
  half of T-011c.
- Depends on: A4 landed on the umbrella branch. You import the provider type from A4's
  single source; do not redeclare it.

You own only:

- `frontend/src/components/AIChat/SetupScreen.tsx`
- `frontend/src/components/AIChat/SetupScreen.parts/ProviderPicker.tsx`
- `frontend/src/components/AIChat/SetupScreen.parts/PermissionModePicker.tsx`
- `frontend/src/components/AIChat/SetupScreen.parts/NoProvidersNotice.tsx` (create)
- `frontend/src/components/AIChat/__tests__/SetupScreen.test.tsx`

You must not touch: `SetupScreen.parts/types.ts`, `store/**`, `BottomPanel.tsx`,
`TerminalTabs.tsx`, any backend file, `docs/**`.

Work to do:

1. T-011. Replace the provider radio list with a single `select` driven by the status
   payload, per FR-021. Labels come from the backend `label` field, not a frontend map.
2. T-011. List every supported agent including uninstalled ones, disabled and annotated
   `(not installed)`, per FR-021a. `available: true, logged_in: false` is selectable and
   annotated `(not logged in)`. Order available before unavailable, registry order within
   each group, per FR-021b.
3. T-011. No preselected provider. Initial value is a non-selectable `Choose provider…`
   placeholder and Launch stays disabled until the user picks one, per FR-021i.
4. T-011a. Add `NoProvidersNotice.tsx` and render it only in the loaded-and-all-unavailable
   branch, per FR-021c. It must not render while status is in flight or errored; those keep
   their existing loading and error treatments, per FR-021d. Name each agent by its
   user-facing product name, not its provider key. Do not add per-provider install commands.
5. T-011b. Relabel the permission picker to `Manual Approve` and `Bypass Permission` with
   no CLI flag name anywhere in the rendered output, per FR-021e. Keep a short
   plain-language caution on the bypass option. Stored `safe` / `dangerous` values and the
   launch payload are unchanged, per FR-021f.
6. Make the action bar `sticky bottom-0` with a fully opaque background, per FR-021g and
   FR-021h. The existing test asserting the action bar has no `bg-white` contradicts
   FR-021h and must be updated, not worked around. The host-chain half of this fix belongs
   to A6; you own the SetupScreen side only.
7. Tests: one select and no per-provider radio input; disabled and annotation states;
   available-first ordering; Launch disabled until a provider is chosen; the three status
   branches with the notice appearing only in loaded-and-all-unavailable; rendered
   permission text contains no `--` substring.

Note on test strength: jsdom performs no layout, so no test you write here proves the
action bar is actually reachable. That proof is A6's real-browser check. Do not claim it.

---

## A6 LAYOUT

Same structure. Substitutions:

- Agent branch: `feat/1994-adr-034/layout`
- Agent worktree: `C:/Users/jiazh/Desktop/workspace/sci-wt/adr034-layout`
- Spec focus: FR-021g, FR-021h; task T-011c host-chain half plus the acceptance evidence.
- Depends on: A5 landed on the umbrella branch, so the browser check exercises the whole fix.

You own only:

- `frontend/src/components/BottomPanel.tsx`
- `frontend/src/components/AIChat/TerminalTabs.tsx`
- `frontend/e2e/specs/adr034-setup-action-bar.spec.ts` (create)

You must not touch: `SetupScreen.tsx` or any `SetupScreen.parts/**` file, `store/**`, any
backend file, `docs/**`.

Work to do:

1. Convert the two CSS-hiding wrappers from percentage-height blocks into flex containers
   that pass a definite height down (`flex min-h-0 flex-1 flex-col` on the visible
   wrapper). `Lineage/RunDetail.tsx` is the working reference; it is *less* defensive than
   `SetupScreen` and works, which localises the defect to these two wrappers.
2. Change only layout classes. Do NOT change the mount structure or the `hidden` toggle.
   Those wrappers exist so `TerminalTabs` stays mounted across tab and surface switches;
   unmounting fires the WS cleanup hook and kills the live agent subprocess, losing the
   user's conversation.
3. `BottomPanel`'s content wrapper hosts Config, Logs, Plots, Lineage, and Git too. Scope
   the change to restoring a definite height, not to removing the scroll affordance.
   Lineage currently works, so a Lineage regression is the clearest signal you went too far.
4. Write `frontend/e2e/specs/adr034-setup-action-bar.spec.ts` as a real Playwright check
   asserting the Launch control is inside the visible panel viewport at the default panel
   height, the minimum panel height, and a restored persisted height smaller than the
   current default. Follow the existing specs in `frontend/e2e/specs/` for harness
   conventions.
5. The browser check must also switch surfaces and tabs with a live agent running and
   assert the PTY survives, per the spec risk note.

This is the one acceptance gate the spec explicitly says jsdom cannot provide. A passing
jsdom test is not evidence here and must not be reported as such.

---

## A7 TESTS

Same structure. Substitutions:

- Agent branch: `feat/1994-adr-034/tests`
- Agent worktree: `C:/Users/jiazh/Desktop/workspace/sci-wt/adr034-tests`
- Persona: `test_engineer`
- Depends on: A1 to A6 landed on the umbrella branch.

You own only: `tests/**` and test fixtures. Production code is out of scope by default for
this persona. If a spec requirement cannot be tested without a production change, stop and
report to the manager rather than editing production code.

Work to do:

1. Sweep spec section 4.4 and close every verification item the implementers did not
   already cover. Report which items you found already covered and by which test, so the
   manager can see the matrix is complete rather than assumed.
2. Assert the Success Criteria in spec section 5 that are mechanically checkable. In
   particular: no test asserts a hardcoded two-provider set; a repository search for a
   provider key outside the registry, tests, and documentation returns no spawn, status, or
   validation logic; the frontend contains no hand-maintained list of agent provider keys
   or labels.
3. Add the User Story 7 extensibility test: a fixture descriptor appended to the registry
   appears in `_VALID_PROVIDERS`, `/api/ai/status`, the AI Block config enum, and the
   frontend provider list with no other source edit.
4. Add the end-to-end four-link provider-propagation test if A4's coverage stops short of
   proving no link substitutes a default.

Do not weaken, skip, xfail, or loosen any existing assertion to make a suite pass. If an
existing test genuinely encodes behavior this spec replaces, say so explicitly in your
report with the reasoning, and change it deliberately rather than quietly.

---

## A8 DOCS

Same structure. Substitutions:

- Agent branch: `feat/1994-adr-034/docs`
- Agent worktree: `C:/Users/jiazh/Desktop/workspace/sci-wt/adr034-docs`
- Persona: `adr_author`
- Spec focus: FR-024; task T-014, plus the governance work the owner authorized.
- Depends on: A1 to A7 landed, because the spec's `governs` must match what actually exists.

You own only:

- `docs/adr/ADR-034.md`
- `docs/specs/adr-034-multi-provider-agent-chat.md`
- `docs/specs/embedded-coding-agent-spec.md`
- `src/scistudio/_skills/scistudio/scistudio-build-workflow/SKILL.md`

Work to do:

1. The owner authorized editing `docs/adr/ADR-034.md` despite `agent_editable: false`. Add
   a ` ```yaml adr042-governance-amendment ` block to its body expanding `governs` to cover
   every surface this spec touches: the registry module, `src/scistudio/api/routes/ai.py`,
   `src/scistudio/blocks/ai/ai_block.py`, `src/scistudio/cli/install.py`,
   `frontend/src/store/**`, and `frontend/src/components/BottomPanel.tsx`. Read
   `docs/adr/ADR-041.md` and `docs/adr/ADR-043.md` for the block's exact syntax, and
   `src/scistudio/qa/audit/_util.py` `_iter_governance_amendment_blocks` for the parser
   contract. The fence info string must be exactly `yaml adr042-governance-amendment`.
2. Do NOT author an ADR-034 addendum instead. The manager verified it would not work:
   `doc_drift._check_adr_spec_alignment` builds `{frontmatter.adr: document}`,
   `ADRAddendumFrontmatter` subclasses `ADRFrontmatter` carrying the parent ADR number, and
   `sorted()` orders `ADR-034-addendum1.md` before `ADR-034.md`, so the base ADR overwrites
   the addendum and its `governs` is never read.
3. Record the ADR-034 amendment content as a real decision record, not just a frontmatter
   edit: the provider registry decision, the verified adapter matrix, and the verification
   date 2026-08-06, per FR-024.
4. Flip `docs/specs/adr-034-multi-provider-agent-chat.md` from `Draft` to `Planned` and
   remove the section 1 "open item blocking Planned status" subsection, replacing it with a
   record of how the gap was closed.
5. Reconcile the spec's `governs.contracts` against the post-implementation symbol set.
   As written it lists `scistudio.ai.agent.terminal.spawn_claude` and `spawn_codex`, which
   section 4.1 removes. A `Planned` spec governing symbols that no longer exist will fail
   the closure audit. Check what A1 actually left in place and update the list to match.
6. Move `src/scistudio/ai/agent/providers_registry.py` and
   `frontend/src/components/AIChat/SetupScreen.parts/NoProvidersNotice.tsx` from
   `planned_governs` to `governs` now that they exist.
7. Update the `docs/specs/embedded-coding-agent-spec.md` locked-contract note's provider
   set, and the AI Block provider enum documented in the SKILL.md.
8. Run `PYTHONPATH=src python scripts/audit/generate_facts.py --check` if generated facts
   are implicated, and report the result.

Generated docs must stay generated. Do not hand-edit generated output.

---

## A9 AUDIT

Filled from `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`.

Audit mode: `no-context`, recorded in the checklist before dispatch.

This agent MUST NOT receive: issue #1994's body, this prompts file, the dispatch checklist,
umbrella or agent PR descriptions, commit messages, or any manager summary. It works only
from repository docs, code, tests, committed generated facts, and tool output it runs
itself.

- Agent branch: `audit/1994-adr-034-no-context`
- Agent worktree: `C:/Users/jiazh/Desktop/workspace/sci-wt/adr034-audit`
- Persona: `audit_reviewer`
- Write set: `docs/audit/adr-034-multi-provider-no-context-20260806.md` only. Read-only
  everywhere else. Report findings; do not fix.

The audit report must be committed as a repository file and merged into the final PR
evidence path. A report that exists only in chat is a dispatch failure.
