---
title: "ADR-054 Assembly Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# ADR-054 Assembly Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: `Host the ADR-054 spec 4 and spec 5 implementation, land them as two track PRs, then integrate specs 1 through 5, run browser e2e and visual verification, and deliver the whole of ADR-054 as one standalone review PR.`
- Task kind: `manager`
- Manager persona: `manager`
- Issue: `#2253`, `#2254` (implementation), `#2209` (ADR tracking)
- Gate record: `.workflow/records/2253-adr-054-assembly.json`
- Branch/worktree plan: manager on `track/adr-054-integration` in
  `.worktrees/mgr-054`; spec tracks on `track/adr-054-spec4-explore-frontend`
  (`.worktrees/s4-track`) and `track/adr-054-spec5-agent-enablement`
  (`.worktrees/s5-track`); agents on `feat/2253-*`, `feat/2254-*`,
  `test/*`, `audit/*`, `fix/*` branches, one dedicated worktree each under
  `.worktrees/`.
- Protected branch: `main`
- Umbrella branch: `track/adr-054-integration`
- Umbrella PR: `#2255`
- Umbrella PR title: `[DO NOT MERGE] ADR-054: assembly of specs 1-5`
- Final PR target: `main`. See §1.2 — the umbrella PR **is** the final review
  PR and is retitled once the assembly is verified.
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

### 1.1 Delivery Order

Specs 1, 2 and 3 already exist as track branches with open PRs (#2238, #2246,
#2251). None of them contained the others: spec 1 and spec 2 were both cut
from `main` and spec 3 from spec 2. `track/adr-054-integration` is cut from
`main` and merges all three, so specs 4 and 5 are built on one base that
contains the panel contract, the analysis, and the session runtime at once.

Spec 4 and spec 5 are dispatched in parallel, because spec 4 is almost
entirely `frontend/**` and spec 5 is almost entirely
`src/scistudio/ai/agent/mcp/**`, `src/scistudio/_skills/**` and
`src/scistudio/_agent_reference/**`. Their one overlap is the workspace-focus
report, resolved in §1.3.

Both track branches then merge back into `track/adr-054-integration`, where
the browser e2e and the visual verification run against the assembled whole.

### 1.2 One Umbrella PR, Then One Review PR

The owner asked for a single standalone review PR carrying the whole of
ADR-054. `#2255` is opened as the `[DO NOT MERGE]` umbrella PR that the
dispatch rules require, and is retitled to the final review PR only after:

1. spec 4 and spec 5 have merged into `track/adr-054-integration`;
2. `gate_record check --mode pre-pr` passes on the assembled branch;
3. CI is green on `#2255`;
4. the browser e2e and the visual verification have run and their evidence is
   committed.

Until every one of those is true the title keeps `[DO NOT MERGE]`.

### 1.3 The Spec 4 / Spec 5 Overlap

Spec 5 FR-001 requires the frontend to report the workspace focus along the
existing active-workflow channel, and names `frontend/src/explore/**` — a
spec 4 path — as the file it changes. The two halves are split by owner:

- **Spec 4 owns the caller.** It writes the `reportWorkspaceFocus` helper and
  calls it on every active-tab change, sending the `mode` and identifiers spec
  5 FR-001 names.
- **Spec 5 owns the channel.** It widens the route, the persistence, the
  runtime record, and the context tool to accept and report those fields.

Neither agent touches the other's half. The wire between them is asserted by
an integration test the manager adds on `track/adr-054-integration` after both
merge; until then spec 4's report reaches a route that ignores the extra
fields, which is harmless and is the reason the split is safe.

### 1.4 Stacked-Base Hazard

`ci.yml` fires only for pull requests whose base is `main` or `track/**`. Both
spec PRs target `track/adr-054-integration`, which matches, so both get a CI
signal. Two consequences:

1. The spec 4 and spec 5 PRs must merge into `track/adr-054-integration`
   **before** `#2255` merges to `main`. Merging `#2255` first would strand
   them on a branch whose commits never reach `main`.
2. Verify with `git log --oneline origin/main..origin/track/adr-054-integration`
   before the final merge; the spec 4 and spec 5 commits must be present.

### 1.5 The Three Predecessor PRs

`#2238`, `#2246` and `#2251` are merged onto `track/adr-054-integration` by
merge commits, so `#2255` carries their content. They stay open as the review
record of each spec's own dispatch. Once `#2255` merges, each becomes
redundant and closes; their issues (`#2229`, `#2231`, `#2240`) are closed by
`#2255`'s body, not by theirs.

## 2. Scope

- In scope:
  - Spec 4 — `frontend/src/explore/**`, `frontend/src/store/exploreSlice.ts`,
    the tab union in `store/types.ts` and `ProjectWorkspace.tsx`, the canvas
    and tree context menus, the block-palette insert-call action, the
    interactive-modal retirement, `frontend/e2e/specs/adr054-explore.spec.ts`.
  - Spec 5 — `src/scistudio/ai/agent/mcp/tools_panels/**`,
    `tools_explore/**`, the workspace focus through `api/routes/ai.py`,
    `api/runtime/_projects.py` and `mcp/runtime.py`,
    `src/scistudio/_skills/**`, `src/scistudio/_agent_reference/**`,
    `src/scistudio/agent_provisioning/**`, `tests/ai/**`.
  - Manager — the merges onto `track/adr-054-integration`, this checklist,
    `docs/planning/adr-054-assembly-dispatch-prompts/**`, `docs/audit/**`,
    `.workflow/records/**`, the e2e evidence, and the follow-up register.
- Out of scope:
  - The documentation revision (`#2236`, spec 6) — the architecture document,
    the seven `docs/package-development/` guides, the generated reference.
    Explicitly excluded by the owner's directive.
  - `docs/specs/adr-054-*.md` — approved input, not work product.
  - `docs/architecture/**` — owner-controlled.
  - Reworking specs 1, 2 or 3 beyond what integration and audit findings force.
- Protected paths:
  - `src/scistudio/blocks/base/interactive.py`,
    `src/scistudio/engine/scheduler/_dispatch.py`,
    `src/scistudio/core/lineage/**`,
    `src/scistudio/core/versioning/_commit_ops.py`,
    `src/scistudio/blocks/registry/**` — all carried in from specs 1 and 3.
    The final PR carries `admin-approved:core-change`; see §5.
- Deferred work:
  - Follow-ups are **not** opened as issues. Per the owner's directive every
    one lands in `docs/planning/adr-054-assembly-followups.md` for the owner
    to triage. A `TODO` in code cites an existing issue or that file's entry.

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

- [x] Dedicated manager branch and worktree created.
      `track/adr-054-integration` in `.worktrees/mgr-054`.
- [x] Existing issue linked, or new issue created only if none exists.
      No open issue tracked spec 4 or spec 5 implementation; `#2253` and
      `#2254` were created and reference the ADR's tracking issue `#2209`.
      These are the implementation issues the owner's directive permits.
- [x] Gate record started.
      `.workflow/records/2253-adr-054-assembly.json`
- [x] Scope include/exclude recorded in the gate record.
- [x] Umbrella branch created. `track/adr-054-integration`
- [x] Umbrella PR opened. `#2255`
- [x] Umbrella PR title includes `[DO NOT MERGE]`.
- [x] Protected branch and umbrella PR number recorded in this checklist.
- [x] No `pip install -e .` environment pollution found.
      Every worktree runs with `PYTHONPATH=./src`.
- [x] Dispatch checklist copied from the template and committed.
- [ ] Dispatch prompts created from the correct prompt template and linked
      below.
- [ ] Sentrux baseline recorded, or N/A reason recorded.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `admin-approved:core-change`
- Owner authorization source: owner directive, this session —
  `"我去睡觉了，你自主工作，除了开额外issue外其余行为均预先批准。"`
  (I am going to sleep; work autonomously — every action is pre-approved
  except opening extra issues.)
- Reason: specs 1 and 3 change `blocks/base/interactive.py`,
  `blocks/registry/**`, `engine/scheduler/_dispatch.py`,
  `core/lineage/**` and `core/versioning/_commit_ops.py`. Every one of those
  is named in the approved specs' own `governs.files`, so the label attests
  that the change is what the approved spec asks for. CI verifies who applied
  it. It is **not** a broad gate bypass: scope, issue linkage, docs landing,
  test obligations and CI parity are all still enforced.

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `gate_record check --mode pre-commit` | `N/A` | `[x]` | No commit-time hook is installed since #2150. |
| Commit message | `gate_record check --mode commit-msg` | `N/A` | `[x]` | Folded into `pre-pr`/`ci` since #2150. |
| Pre-push | `gate_record check --mode pre-push` | `N/A` | `[ ]` | Installed hook is a fast allow shim. |
| Pre-PR reconcile | `gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `admin-approved:core-change` | `[ ]` | pending |

## 5.1 Docs Impact Check

- Wrapper/hook/gate-record/receipt/CI/runtime behavior changed: `no`
- AI docs checked:
  `docs/ai-developer/rules.md`,
  `docs/ai-developer/specific_rules/gated-workflow.md`,
  `docs/ai-developer/specific_rules/agent-dispatch.md`,
  `docs/ai-developer/templates/*dispatch*.md`
- Updated docs or N/A rationale: N/A — this dispatch changes no wrapper, hook,
  gate-record, CI or AI-runtime behaviour. Spec 5 adds MCP tools and a skill,
  which are agent *capabilities*, not the gate workflow; their catalogs are
  updated inside spec 5's own scope.

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| `S4-A1` | `implementer` | `N/A` | `docs/planning/adr-054-assembly-dispatch-prompts/s4-a1-tab-and-slice.md` | Explore tab member, store slice, API types, event routing, layout (T-001 to T-003), plus spec 5 FR-001's frontend half | `feat/2253-explore-tab-shell` | `.worktrees/s4-a1` | tab union, slice, api types, workspace, context menus, workspace-focus report | notebook shell, panels, pause | `#2253` | `[x]` |
| `S4-A2` | `implementer` | `N/A` | `docs/planning/adr-054-assembly-dispatch-prompts/s4-a2-notebook-shell.md` | Notebook shell, cell editors, output renderer, marks, cell commands (T-004 to T-007) | `feat/2253-notebook-shell` | `.worktrees/s4-a2` | `frontend/src/explore/Notebook*`, `CellEditor`, `OutputRenderer`, `CellMarks` | tab union, panels, pause | `#2253` | `[x]` |
| `S4-A3` | `implementer` | `N/A` | `docs/planning/adr-054-assembly-dispatch-prompts/s4-a3-panels-and-pause.md` | Variable strip, panel slots, emission, pause tab, modal retirement (T-008 to T-011) | `feat/2253-panels-and-pause` | `.worktrees/s4-a3` | `VariableStrip`, `PanelSlots`, `InteractiveModals` deletion | notebook shell internals, graph | `#2253` | `[x]` |
| `S4-A4` | `implementer` | `N/A` | `docs/planning/adr-054-assembly-dispatch-prompts/s4-a4-packaging-and-graph.md` | Packaging report, packaged node badge, kernel list, graph view, palette insert-call (T-012 to T-015) | `feat/2253-packaging-and-graph` | `.worktrees/s4-a4` | `PackagingReport`, `GraphView`, `SessionToolbar` kernel half, `BlockNode`, `BlockPalette` | tab union, notebook shell, pause | `#2253` | `[ ]` |
| `S5-B1` | `implementer` | `N/A` | `docs/planning/adr-054-assembly-dispatch-prompts/s5-b1-workspace-focus.md` | Workspace focus: route, persistence, runtime record, context tool, refusal (T-001, T-002) | `feat/2254-workspace-focus` | `.worktrees/s5-b1` | `api/routes/ai.py`, `api/runtime/_projects.py`, `mcp/runtime.py`, `_context.py`, `_focus.py`, `tools_workflow/read.py`, `_models.py`, `api/app.py`, `api/runtime/__init__.py` | tools_panels, tools_explore, skills | `#2254` -> PRs `#2258`, `#2259` | `[x]` |
| `S5-B2` | `implementer` | `N/A` | `docs/planning/adr-054-assembly-dispatch-prompts/s5-b2-panel-tools.md` | Panel reference, block-contract rewrite, panel tools with the stub harness (T-003, T-004) | `feat/2254-panel-tools` | `.worktrees/s5-b2` | `mcp/tools_panels/**`, `_agent_reference/panel-contract.md`, `block-contract.md` | focus, session tools, skills | `#2254` | `[x]` |
| `S5-B3` | `implementer` | `N/A` | `docs/planning/adr-054-assembly-dispatch-prompts/s5-b3-session-tools.md` | Session tools over the session API (T-006) | `feat/2254-session-tools` | `.worktrees/s5-b3` | `mcp/tools_explore/**`, `mcp/server.py` registration | focus internals, panel tools, skills | `#2254` | `[x]` |
| `S5-B4` | `implementer` | `N/A` | `docs/planning/adr-054-assembly-dispatch-prompts/s5-b4-skills-and-counts.md` | Panel skill, block skill, base skill, provisioning counts, examples, catalogs (T-005, T-007, T-008, T-009) | `feat/2254-skills-and-counts` | `.worktrees/s5-b4` | `_skills/**`, `agent_provisioning/**`, `tools_authoring.py`, count assertions | tools_panels, tools_explore implementation | `#2254` | `[x]` T-005/T-007/T-008/T-009 complete at the live **47** tools in eight groups (S5-B2's panel group and S5-B3's session group both counted); the five count-assertion sites consolidated into one declaration, `tests/mcp_tool_expectations.py`, and `test_write_class_tools_have_next_step` derived from the registry's `write` tag (S5-B3's F-B3-7). Follow-ups F-B4-1..F-B4-10, of which F-B4-8/9/10 are one chain — see *The three above are one chain* in the register. F-B4-10 fixed here under a manager scope grant. **PR still not opened**: with that flake gone the run now reaches the serial phase and exceeds F-B4-8's 600s cap, so `check` reports "reconciliation passed" while `finalize` refuses the same event as stale — four consecutive ledger events `fail`/`unknown`/`fail`/`unknown`. The fix is in `gate_record/checks.py`, outside this agent's write set |
| `S4-D1` | `test_engineer` | `N/A` | `docs/planning/adr-054-assembly-dispatch-prompts/s4-d1-adversarial.md` | Adversarial tests against the assembled spec 4 frontend | `test/2253-adversarial` | `.worktrees/s4-d1` | `frontend/**/*.test.tsx`, `frontend/e2e/**`, fixtures | production frontend code | `#2253` | `[ ]` |
| `S5-D1` | `test_engineer` | `N/A` | `docs/planning/adr-054-assembly-dispatch-prompts/s5-d1-adversarial.md` | Adversarial tests against the assembled spec 5 agent surface | `test/2254-adversarial` | `.worktrees/s5-d1` | `tests/ai/**`, `tests/agent_provisioning/**`, fixtures | production code | `#2254` | `[ ]` |
| `S4-E1` | `audit_reviewer` | `no-context` | `docs/planning/adr-054-assembly-dispatch-prompts/s4-e1-audit-no-context.md` | Independent audit of the Explore frontend | `audit/2253-no-context` | `.worktrees/s4-e1` | `docs/audit/<date>-adr-054-spec4-no-context.md` | every source path | `#2253` | `[ ]` |
| `S5-E1` | `audit_reviewer` | `no-context` | `docs/planning/adr-054-assembly-dispatch-prompts/s5-e1-audit-no-context.md` | Independent audit of the agent enablement surface | `audit/2254-no-context` | `.worktrees/s5-e1` | `docs/audit/<date>-adr-054-spec5-no-context.md` | every source path | `#2254` | `[ ]` |
| `INT-E1` | `audit_reviewer` | `no-context` | `docs/planning/adr-054-assembly-dispatch-prompts/int-e1-audit-no-context.md` | Independent audit of the assembled ADR-054 whole | `audit/2255-assembly-no-context` | `.worktrees/int-e1` | `docs/audit/<date>-adr-054-assembly-no-context.md` | every source path | `#2255` | `[ ]` |

Rows are added for fix agents as findings land.

## 7. Track: Spec 4 — The Explore Frontend

### 7.1 Track Scope

- Owner: `S4-A1` .. `S4-A4`, audited by `S4-E1`, adversarially tested by `S4-D1`
- In scope:
  - `frontend/src/explore/**` (new), `frontend/src/store/exploreSlice.ts` (new)
  - `frontend/src/store/types.ts`, `frontend/src/types/api.ts`,
    `frontend/src/types/ui.ts`
  - `frontend/src/App.parts/ProjectWorkspace.tsx`, `frontend/src/App.tsx`
  - `frontend/src/hooks/useWebSocket.parts/dispatchEvent.ts`
  - `frontend/src/components/WorkflowCanvas.tsx` and `.parts/**`
  - `frontend/src/components/nodes/BlockNode.tsx`
  - `frontend/src/components/ProjectTree.tsx` and `.parts/**`
  - `frontend/src/components/BlockPalette.tsx` and `.parts/**`
  - `frontend/src/components/DataPreview.tsx`
  - deletion of `frontend/src/App.parts/InteractiveModals.tsx` and `.parts/**`
  - `frontend/e2e/specs/adr054-explore.spec.ts`
- Out of scope:
  - Every `src/scistudio/**` path. The backend is specs 1, 2, 3 and 5.
  - `docs/specs/**`, `docs/architecture/**`.
- Required docs:
  - N/A for the tranche — spec 6 (`#2236`) owns the human documentation. Each
    agent records `--docs-na "user-docs:owned by ADR-054 spec 6, issue #2236"`.
- Required tests:
  - `frontend/src/explore/**/*.test.tsx` per component,
    `frontend/src/store/exploreSlice.test.ts`,
    the dispatch test, and `frontend/e2e/specs/adr054-explore.spec.ts`.

### 7.2 Dispatch

- [ ] Prompt file created or dispatch prompt recorded.
- [ ] Correct prompt template selected.
- [ ] Audit mode recorded when persona is `audit_reviewer`.
- [ ] Agent branch/worktree assigned.
- [ ] Write set and out-of-scope paths included in prompt.
- [ ] TODO rule included in prompt.
- [ ] Required checks included in prompt.

### 7.3 Implementation

- [x] `S4-A1` tab member, slice, API types, event routing, layout, context menus
  -> `feat/2253-explore-tab-shell`; `npm run test` 205 files / 2414 tests green,
  `npm run lint` 0 errors, `npm run build` succeeds; findings F-A1-001 to
  F-A1-008 in `docs/planning/adr-054-assembly-followups.md`
- [x] `S4-A2` notebook shell, cell editors, output renderer, marks, commands -> `feat/2253-notebook-shell`, gate record `.workflow/records/2253-feat-2253-notebook-shell.json`; 105 tests across `NotebookShell.test.tsx`, `CellEditor.test.tsx`, `OutputRenderer.test.tsx`, `CellMarks.test.tsx`, `SessionToolbar.runControls.test.tsx`; findings F-A2-001 to F-A2-008
- [ ] `S4-A3` variable strip, panel slots, emission, pause tab, modal deleted -> `<artifact>`
- [ ] `S4-A4` packaging report, node badge, kernel list, graph view, palette -> `<artifact>`
- [ ] `S4-D1` adversarial test suite -> `<artifact>`
- [ ] docs N/A recorded in each gate ledger -> `<artifact>`

### 7.4 Audit

- [ ] Audit agent assigned, or manager audit completed.
- [ ] Audit report file path assigned.
- [ ] Audit report committed.
- [ ] Audit report merged into final PR evidence path.
- [ ] Findings recorded.
- [ ] P1 findings fixed before integration.
- [ ] P2/P3 findings fixed or registered in the follow-up file.

### 7.5 Integration

- [ ] Agent output reviewed by manager.
- [ ] Scope compliance verified.
- [ ] Conflicts resolved intentionally.
- [ ] Track merged into `track/adr-054-integration`.

## 8. Track: Spec 5 — Agent Enablement

### 8.1 Track Scope

- Owner: `S5-B1` .. `S5-B4`, audited by `S5-E1`, adversarially tested by `S5-D1`
- In scope:
  - `src/scistudio/api/routes/ai.py`, `src/scistudio/api/runtime/_projects.py`
  - `src/scistudio/ai/agent/mcp/runtime.py`, `_context.py`, `server.py`,
    `tools_workflow/read.py`, `tools_authoring.py`
  - `src/scistudio/ai/agent/mcp/tools_panels/**` (new)
  - `src/scistudio/ai/agent/mcp/tools_explore/**` (new)
  - `src/scistudio/_skills/scistudio/**`
  - `src/scistudio/_agent_reference/**`
  - `src/scistudio/agent_provisioning/**`
  - `docs/specs/embedded-coding-agent-spec.md` (tool catalog only)
  - `tests/ai/**`, `tests/agent_provisioning/**`
- Out of scope:
  - Every `frontend/**` path, including the focus report itself (spec 4 owns
    the caller — see §1.3).
  - `docs/architecture/**` — the tool table lands with spec 6 (`#2236`).
  - `src/scistudio/explore/**` — spec 3's runtime. The session tools *call* the
    session API; they do not change it.
- Required docs:
  - `src/scistudio/_agent_reference/panel-contract.md` (new),
    `block-contract.md` (panel section rewritten),
    `public-api.md`, `data-types.md`, `README.md`,
    `docs/specs/embedded-coding-agent-spec.md` catalog.
- Required tests:
  - `tests/ai/test_workspace_focus.py`, `tests/ai/test_mcp_tools_panels.py`,
    `tests/ai/test_mcp_tools_explore.py`, the moved count assertions in
    `tests/ai/test_mcp_fastmcp.py`, `test_mcp_server_skeleton.py`,
    `test_finish_ai_block_skeleton.py`, and
    `tests/agent_provisioning/test_skills.py`.

### 8.2 Dispatch

- [ ] Prompt file created or dispatch prompt recorded.
- [ ] Correct prompt template selected.
- [ ] Audit mode recorded when persona is `audit_reviewer`.
- [ ] Agent branch/worktree assigned.
- [ ] Write set and out-of-scope paths included in prompt.
- [ ] TODO rule included in prompt.
- [ ] Required checks included in prompt.

### 8.3 Implementation

- [x] `S5-B1` workspace focus: route, persistence, runtime, context tool, refusal -> PR `#2258` (`feat/2254-workspace-focus`, base `track/adr-054-spec5-agent-enablement`), commit `1b387ff`, gate `.workflow/records/2254-feat-2254-workspace-focus.json` (post-PR finalized, tier 1, reconciliation passed); `PYTHONPATH=./src python -m pytest tests/ai/test_workspace_focus.py -q` -> 31 passed. The refusal helper S5-B3 imports is `scistudio.ai.agent.mcp._focus.resolve_session_path`. Follow-up PR `#2259` (`feat/2254-focus-test-cost`, gate `.workflow/records/2254-focus-test-cost.json`, post-PR finalized) cuts that module from ~40s to ~13s and removes a nested-app race; it landed after `#2258` was merged. CI on `#2258`: ten jobs green, both `Test` jobs failing for causes that reproduce on the base track with no spec 5 code in it — follow-up `F-B1-4` and the `#2251` row in §9.
- [x] `S5-B2` panel reference, block-contract rewrite, panel tools, harness -> PR #2257 (`feat/2254-panel-tools`, base `track/adr-054-spec5-agent-enablement`); tools `scaffold_panel`, `read_panel_source`, `list_panel_examples`, `reload_panels`; `tests/ai/test_mcp_tools_panels.py` (30 passed, harness opened in chromium and an emission captured); gate `.workflow/records/2254-feat-2254-panel-tools.json`; follow-ups F-1..F-7 in `docs/planning/adr-054-assembly-followups.md`
- [x] `S5-B3` session tools over the session API -> PR #2261 (`feat/2254-session-tools`, base `track/adr-054-spec5-agent-enablement`), commit `7b8f80c`; tools `open_explore_session`, `read_notebook`, `append_cell`, `run_cell`, `get_bindings`, `check_packaging`, `package_notebook` (tags `category:session` + `read`/`write`), registered in `src/scistudio/ai/agent/mcp/__init__.py` rather than `server.py` (S5-B2's F-5); `PYTHONPATH=./src python -m pytest tests/ai/test_mcp_tools_explore.py -q` -> 70 passed; gate `.workflow/records/2254-feat-2254-session-tools.json` (post-PR finalized, tier 1, reconciliation passed); follow-ups F-B3-1..F-B3-11 in `docs/planning/adr-054-assembly-followups.md`. **`await mcp.list_tools()` now returns 47** (36 + 4 panel + 7 session), and the six count assertions across five files are S5-B4's T-009 row (F-B3-8). CI run 33958351227: 9 jobs pass; Test (3.11) fails only on the six count assertions (6 failed, 9443 passed), Test (3.13) adds F-B1-4's 600s parallel-phase timeout, and Frontend fails on `OpenAsDialog.test.tsx` (F-B3-11) which this branch cannot touch — it changes no `frontend/**` path. The branch merged the moved track at `6a2a98c`: GitHub runs no `pull_request` workflow for a PR whose merge commit cannot be created, so #2261 had no CI at all while it conflicted with its base.
- [x] `S5-B4` skills, provisioning counts, examples, catalogs -> branch
  `feat/2254-skills-and-counts`. `scistudio-write-panel` added (task skills 6->7,
  written files 14->16, moved in six places); the block and base skills carry the
  packaged-notebook shape, the panel routing and the workspace-focus rule; the
  examples corpus gains a displaying panel, a producing panel and a packaged
  notebook, all reachable through `list_block_examples` and, for the panels,
  through S5-B2's `list_panel_examples`; the tool count moves to **47** across
  five assertion sites now reading one declaration
  (`tests/mcp_tool_expectations.py`), plus a new `tests/ai/test_tool_catalogs.py`
  asserting every registered tool name appears in each catalog with the
  architecture document excluded per #2236. Follow-ups F-B4-1..F-B4-10 in
  `docs/planning/adr-054-assembly-followups.md`
- [ ] `S5-D1` adversarial test suite -> `<artifact>`

### 8.4 Audit

- [ ] Audit agent assigned, or manager audit completed.
- [ ] Audit report file path assigned.
- [ ] Audit report committed.
- [ ] Audit report merged into final PR evidence path.
- [ ] Findings recorded.
- [ ] P1 findings fixed before integration.
- [ ] P2/P3 findings fixed or registered in the follow-up file.

### 8.5 Integration

- [ ] Agent output reviewed by manager.
- [ ] Scope compliance verified.
- [ ] Conflicts resolved intentionally.
- [ ] Track merged into `track/adr-054-integration`.

## 9. Track: The Assembly

### 9.1 Track Scope

- Owner: manager, audited by `INT-E1`
- In scope:
  - The merges of specs 1 to 5 onto `track/adr-054-integration`.
  - The spec 4 / spec 5 focus-wire integration test (§1.3).
  - The browser e2e run and the visual verification, with committed evidence.
  - `docs/planning/adr-054-assembly-followups.md`.
- Out of scope:
  - Any new feature work. Integration fixes only.

### 9.2 Predecessor Merges

- [x] `main` -> `track/adr-054-integration` (base cut at `56b73f03d`).
- [x] spec 1 `track/adr-054-spec1-panel-contract` merged.
      One conflict: `tests/architecture/test_layer_deps.py`.
- [x] spec 2 `track/adr-054-spec2-dependency-analysis` merged.
      Commit `<see git log>` — `scistudio.previewers` renamed to
      `scistudio.panels` in the explore layer rule.
- [x] spec 3 `track/adr-054-spec3-explore-session` merged.
      Four conflicts, all union merges: the `interactive.py` import block, the
      `PANEL_API_VERSION` redeclaration (spec 1's core-layer import wins), the
      `__all__` commentary, the `_dispatch.py` import list, and the layer-deps
      explore paragraph and rule.
- [ ] spec 4 `track/adr-054-spec4-explore-frontend` merged.
- [ ] spec 5 `track/adr-054-spec5-agent-enablement` merged.

### 9.3 Known Inherited Failures

| PR | Failure | Owner | Status |
|---|---|---|---|
| `#2238` | `Verify Workflow Compliance` — `guard.core_change_guard` wants `admin-approved:core-change` | manager, §5 | `[ ]` |
| `#2251` | `tests/explore/test_explore_session.py::test_a_kernel_killed_from_outside_is_reported_dead_and_offers_a_restart` fails on Linux CI (`_process_gone` false) | fix agent | `[x]` |

`#2251` was **not** a test defect after the manager's zombie fix — it was
`KernelHandle` believing `jupyter_client`. Fixed by PR **#2262**
(`fix/2240-kernel-death-detection`), which makes liveness two independent
readings: `Popen.poll()` is `waitpid(pid, WNOHANG)`, and Linux withholds a
killed multi-threaded process from `wait` while its sibling threads exit even
though `/proc` already reports state `Z`, so the library answered "still
running" about a corpse. Evidence: on the branch point `fa678c7ff` (run
33957302816) `Test (Python 3.11)` failed on exactly that assertion; on
`151738a87` (run 33957753781) `Test (Python 3.11)` **passes**. `Test (Python
3.13)` still fails on both, for the unrelated pre-existing parallel-phase
stall recorded as `FK-005` in the follow-up register — that one is the
assembly's blocker, not this fix's.

### 9.3.1 Carried Work The Manager Owes At Integration

Work a fix agent identified but could not execute, because the target file
lives on a branch it was not allowed to touch. Each is the manager's to apply
when the branches meet.

- [ ] **FC-002 — carry the safe asset-URL pattern into the panel scaffold.**
      `fix/2229-panel-codeql-findings` fixed a real `javascript:`-URL hole in
      `core.plot.basic/index.html` with a `safeAssetUrl(value, dataPrefixes)`
      allowlist chosen per element. The same pattern belongs in
      `src/scistudio/ai/agent/mcp/tools_panels/_scaffold.py`, `_stubs.py` and
      `src/scistudio/_agent_reference/panel-contract.md`, because
      `scaffold_panel` writes every future authored panel from that skeleton
      and the reference is what teaches the agent. Those three files are
      S5-B2's and live on the spec 5 track, so the fix agent could not reach
      them. **Apply when the spec 5 track merges into integration**, and add a
      test that a freshly scaffolded panel carries the pattern — otherwise the
      next authored panel reintroduces the finding this dispatch just closed.

### 9.4 Verification

- [~] Focus-wire integration test added and passing.
      Manual field-by-field check done and passing: spec 4's
      `WorkspaceFocusPayload` (`frontend/src/lib/api/ai.ts`) and spec 5's
      `WorkspaceFocusModel` (`src/scistudio/api/routes/ai.py`) carry the same
      seven fields — `mode`, `workflow_id`, `session_path`, `bound_run_id`,
      `current_cell_id`, `paused_node_id`, `paused_run_id` — with nothing
      extra on either side. The automated assertion still lands at
      integration; a manual check is evidence that today is right, not that
      tomorrow stays right. Response-half gap recorded as M-004.
- [ ] `gate_record check --mode pre-pr` passes on the assembled branch.
- [ ] Browser e2e scenario run; evidence committed.
- [ ] Visual verification run; screenshots committed.
- [ ] CI green on `#2255`.
- [ ] `#2255` retitled to the final review PR.

## 10. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Gate ledger check (local) | `gate_record check --mode local --base origin/main --head HEAD` | `[ ]` | pending |
| Targeted tests | `pytest tests/panels tests/explore tests/api tests/ai tests/architecture`; `npm test` in `frontend/` | `[ ]` | pending |
| Pre-push gate check | `gate_record check --mode pre-push --base origin/main --head HEAD` | `[ ]` | pending |
| Gate ledger check (pre-PR) | `gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `[ ]` | pending |
| Gate finalize (pre-PR) | `gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#2253"` | `[ ]` | pending |
| Wrapper preflight | `python scripts/scistudio_pr_create.py --dry-run` | `[ ]` | pending |
| Browser e2e | `docs/ai-developer/skills/scistudio-e2e-test/SKILL.md` scenario | `[ ]` | pending |

## 11. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| `2026-09-05` | manager | Spec 5 FR-001 names `frontend/src/explore/**`, a spec 4 path | Split by owner: spec 4 writes the caller, spec 5 the channel; manager adds the wire test at integration | §1.3 |

## 12. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence when needed, commit, and PR evidence.
- [ ] PR closes every issue fixed by the dispatch.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
- [ ] Follow-up register handed to the owner.
