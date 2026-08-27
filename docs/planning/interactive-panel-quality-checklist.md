---
title: "Interactive Panel Quality Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 51
language_source: en
---

# Interactive Panel Quality Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: `AI-written interactive blocks are poor quality — a user was locked in a panel with no continue/cancel button; make the runtime unlockable and teach and validate the panel contract.`
- Task kind: `manager`
- Manager persona: `manager`
- Issue: `#2195`, `#2196`, `#2197`
- Gate record: `.workflow/records/2195-track-interactive-panel-quality.json`
- Branch/worktree plan: `manager on track/interactive-panel-quality in .worktrees/mgr-interactive-panel; one agent branch + worktree per issue`
- Protected branch: `main`
- Umbrella branch: `track/interactive-panel-quality`
- Umbrella PR: `#2198`
- Umbrella PR title: `[DO NOT MERGE] track: interactive panel quality`
- Final PR target: `main — three independent agent PRs, one per issue (owner-directed)`
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

### 1.1 Owner-Directed Deviation: Agent PRs Target `main`

`agent-dispatch.md` §2 defaults dispatched agents to the umbrella branch. The
owner directed three independent PRs instead, one per issue. The three write
sets are disjoint after the sequencing in §2, so there is no integration surface
that needs an umbrella merge, and a PR based on `track/**` would not fire the
issue-closing keywords that each of these PRs must carry.

The manager therefore explicitly assigns each agent its own final PR to `main`,
which `agent-dispatch.md` §4 permits ("MUST NOT target your PR to the protected
branch unless the manager explicitly assigns that final PR"). The umbrella
branch and `[DO NOT MERGE]` umbrella PR are still created, and carry this
checklist, the dispatch prompts, and the manager gate record.

## 2. Scope

- In scope:
  - `frontend/src/App.parts/InteractiveModals.tsx` and
    `frontend/src/App.parts/InteractiveModals.parts/**` — host-owned escape hatch.
  - `src/scistudio/blocks/registry/**`, `src/scistudio/ai/agent/mcp/**`,
    `src/scistudio/workflow/validator.py`,
    `src/scistudio/agent_provisioning/**` — interactive contract validation.
  - `src/scistudio/_skills/**`, `src/scistudio/_agent_reference/block-contract.md`,
    `src/scistudio/cli/templates/**` — panel authoring skill and scaffold.
  - `docs/planning/interactive-panel-quality-*` — manager checklist and prompts.
- Out of scope:
  - The panel host API version and the `PanelModule` contract. No `apiVersion`
    bump in any of the three tracks.
  - Host-owned Continue / decision plumbing (`host.setDecision`). Continue stays
    the panel's responsibility.
  - Error-surface redesign (copy button, failure-code display in the UI).
  - Executing panel modules in a JS runtime. The backend depends on no JS
    runtime and this dispatch does not introduce one.
- Protected paths:
  - `src/scistudio/blocks/**` — A2 edits `src/scistudio/blocks/registry/`.
    Requires `admin-approved:core-change` on PR #2196, verified in CI.
- Deferred work:
  - N/A at dispatch time. Agents record deferrals as `TODO(#NNN)`.

### 2.1 Manager Sequencing: `src/scistudio/ai/agent/mcp/tools_authoring.py`

Both A2 and A3 have a natural claim on this file: `ReloadBlocksResult` (line 83)
and `scaffold_block` (line 319) live in it. Two agents owning one file is a
hard fail, so the manager sequences it:

- **A2 owns `tools_authoring.py` exclusively.** It edits `ReloadBlocksResult`
  and `reload_blocks`.
- **A3 must not open it.** A3 implements the interactive scaffold as a
  self-contained helper plus templates and exposes one entry point, reporting
  its signature.
- **The manager applies the `scaffold_block` wiring** (category value +
  delegation to A3's helper) on A3's branch after #2196 merges, then re-runs
  A3's checks. Recorded in §9 when done.

### 2.2 Merge Order

Discovered after dispatch, from A3's report. The three PRs are not
independent at merge time:

1. **#2199 (A1)** — independent. Mergeable on its own, in any order.
2. **#2201 (A2)** — must merge **before** #2200. Two of A3's remaining
   steps need A2's files present.
3. **#2200 (A3)** — must not merge until two follow-ups land on its branch,
   both of which require #2201 first:
   - **Skill provisioning registration.** A skill directory only ships into a
     project when it is listed in `_SKILL_NAMES`
     (`src/scistudio/agent_provisioning/skills.py`), `_expected_skill_paths()`
     (`_orchestrate.py`, with its count), and `templates/claude_agents_md.md`,
     with paired count updates in `tests/agent_provisioning/test_skills.py` and
     `tests/packaging/test_wheel_skills.py`. Those are A2's declared write set,
     so A3 correctly did not touch them. **Without this the new skill exists in
     the wheel but no agent is ever given it** — the deliverable is incomplete
     until it lands. A2 also edits `_orchestrate.py`, so doing this before
     #2201 merges would conflict.
   - **`scaffold_block` wiring** (§2.1). A3's skill documents
     `scaffold_block(category="interactive")`, which only becomes true after
     the wiring. A3 hedged the skill text with a working manual fallback, so
     the skill is honest either way, but the wiring is still a merge blocker.

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

- [x] Dedicated manager branch and worktree created. -> `track/interactive-panel-quality` in `.worktrees/mgr-interactive-panel`
- [x] Existing issue linked, or new issue created only if none exists. -> searched open issues for `interactive` / `panel`; only #2013 and #1849 are adjacent and neither covers this; created #2195, #2196, #2197
- [x] Gate record started. -> `.workflow/records/2195-track-interactive-panel-quality.json`
- [x] Scope include/exclude recorded in the gate record. -> `docs/planning/**`, `.workflow/records/**`
- [x] Umbrella branch created. -> `track/interactive-panel-quality`
- [x] Umbrella PR opened. -> #2198
- [x] Umbrella PR title includes `[DO NOT MERGE]`.
- [x] Protected branch and umbrella PR number recorded in this checklist. -> §1
- [x] No `pip install -e .` environment pollution found. -> restated in every dispatch prompt
- [x] Dispatch checklist copied from the template and committed.
- [x] Dispatch prompts created from the correct prompt template and linked below. -> §6
- [x] Sentrux baseline recorded, or N/A reason recorded. -> Sentrux MCP is not connected in the manager session and the CLI is not on PATH; each agent's `gate_record check` records the guard event for its own diff, which is where Sentrux evidence lands per ADR-042 Addendum 6

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A`
- Owner authorization source: `N/A`
- Reason: `No bypass requested or used. PR #2196 needs admin-approved:core-change for src/scistudio/blocks/registry/, which is a protected-path authorization, not a gate bypass.`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record check --mode pre-commit` | `N/A` | `[ ]` | `pending` |
| Commit message | `python -m scistudio.qa.governance.gate_record check --mode commit-msg` | `N/A` | `[ ]` | `pending` |
| Pre-push | `python -m scistudio.qa.governance.gate_record check --mode pre-push` | `N/A` | `[ ]` | `pending` |
| Pre-PR reconcile | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file <body-file>` | `N/A` | `[ ]` | `pending` |

## 5.1 Docs Impact Check

- Wrapper/hook/gate-record/receipt/CI/runtime behavior changed: `yes`
- AI docs checked:
  `docs/ai-developer/rules.md`,
  `docs/ai-developer/specific_rules/gated-workflow.md`,
  `docs/ai-developer/specific_rules/agent-dispatch.md`,
  `docs/ai-developer/templates/*dispatch*.md`
- Updated docs or N/A rationale: `A2 adds a provisioned PostToolUse hook, which changes AI-runtime behavior; A2 must record whether the four AI docs above need updates and land the update or an N/A rationale in its own ledger. The manager verifies this at integration.`

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| `A1` | `implementer` | `N/A` | `docs/planning/interactive-panel-quality-dispatch-prompts/a1-escape-hatch.md` | Host-owned escape hatch + no silent null | `fix/2195-panel-escape-hatch` | `.worktrees/fix-2195-panel-escape-hatch` | `frontend/src/App.parts/InteractiveModals.tsx`, `frontend/src/App.parts/InteractiveModals.parts/**` | all backend, all skills/docs, panel host API version | `#2195` | `#2199` `[x]` |
| `A2` | `implementer` | `N/A` | `docs/planning/interactive-panel-quality-dispatch-prompts/a2-contract-validation.md` | Shared contract validation at 3 surfaces | `feat/2196-interactive-contract-validation` | `.worktrees/feat-2196-interactive-validation` | `src/scistudio/blocks/registry/**`, `src/scistudio/ai/agent/mcp/tools_authoring.py`, `src/scistudio/ai/agent/mcp/_reload.py`, `src/scistudio/workflow/validator.py`, `src/scistudio/agent_provisioning/**`, `tests/**` | `frontend/**`, `src/scistudio/_skills/**`, `src/scistudio/_agent_reference/**`, `src/scistudio/cli/templates/**` | `#2196` | `#2201` `[x]` |
| `A3` | `implementer` | `N/A` | `docs/planning/interactive-panel-quality-dispatch-prompts/a3-authoring-skill.md` | Panel authoring skill + scaffold template + doc fixes | `docs/2197-panel-authoring-skill` | `.worktrees/docs-2197-panel-authoring-skill` | `src/scistudio/_skills/**`, `src/scistudio/_agent_reference/block-contract.md`, `src/scistudio/cli/templates/**`, new scaffold helper module, `frontend/src/App.parts/InteractiveModals.parts/panelModuleLoader.ts` (comment only), `tests/**` | `src/scistudio/ai/agent/mcp/tools_authoring.py` (§2.1), `src/scistudio/blocks/**`, all other frontend behavior | `#2197` | `#2200` `[~]` |

For `test_engineer` rows, the write set should default to tests, fixtures,
validation scripts, e2e scenarios, audit evidence, and explicitly assigned
QA/governance tooling. Production code paths require a recorded scope
amendment.

## 7. Track: A1 — Host-Owned Escape Hatch (#2195)

### 7.1 Track Scope

- Owner: `A1`
- In scope:
  - Host-drawn title bar with block name and a close (X) control on the panel
    modal; X and ESC both drive the existing `onCancel`.
  - Replace the `return null` branch in `InteractiveModals.tsx` (lines 148-154)
    with the visible error surface + Cancel that `DynamicPanel` already renders.
- Out of scope:
  - `PANEL_HOST_API_VERSION`, `PanelHostApi`, `PanelModule` — no contract or
    version change; existing panels must need no edits.
  - Host-owned Continue or `host.setDecision`.
  - Any backend file.
- Required docs:
  - No public contract changes. Record a docs N/A rationale in the ledger unless
    the agent finds a doc that describes the modal's affordances.
- Required tests:
  - `frontend/src/App.parts/InteractiveModals.parts/DynamicPanel.test.tsx` and/or
    a sibling test: ESC and X cancel a mounted exit-less panel; the
    no-`module_url` manifest renders the error surface with a working Cancel;
    core panels and the tutorial panel are unchanged.

### 7.2 Dispatch

- [x] Prompt file created or dispatch prompt recorded.
- [x] Correct prompt template selected.
- [x] Audit mode recorded when persona is `audit_reviewer`. -> N/A, implementer
- [x] Agent branch/worktree assigned.
- [x] Write set and out-of-scope paths included in prompt.
- [x] TODO rule included in prompt.
- [x] Required checks included in prompt.

### 7.3 Implementation

- [x] Title-bar X + ESC escape hatch -> PR #2199, commit `1d1e8d9ae`, `frontend/src/App.parts/InteractiveModals.parts/DynamicPanel.tsx`
- [x] `return null` branch replaced with error surface + Cancel -> PR #2199, commit `1d1e8d9ae`, `frontend/src/App.parts/InteractiveModals.tsx`
- [x] Tests -> `frontend/src/App.parts/InteractiveModals.test.tsx` (new, 6 tests), `frontend/src/App.parts/InteractiveModals.parts/DynamicPanel.test.tsx` (+7 tests)
- [x] Stale asset-route comments and fixtures corrected (follow-up from A3's finding) -> PR #2199, commit `d3c1f1c93`, 5 lines across `panelModuleLoader.ts` (111, 126), `panelModuleLoader.test.ts:12`, `DynamicPanel.test.tsx:12`, `InteractiveModals.test.tsx:117`
- [x] Docs updated or N/A recorded -> docs N/A in `.workflow/records/2195-fix-2195-panel-escape-hatch.json`; no ADR, spec, or guide documents the interactive modal's chrome, and ADR-051 US3/FR-012 already promise the affordance this restores

### 7.4 Audit

- [ ] Audit agent assigned, or manager audit completed.
- [ ] Audit report file path assigned.
- [ ] Audit report committed.
- [ ] Audit report merged into final PR evidence path.
- [ ] Findings recorded.
- [ ] P1 findings fixed before integration.
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale.

### 7.5 Integration

- [x] Agent output reviewed by manager. -> manager read the full production diff of `InteractiveModals.tsx` and `DynamicPanel.tsx` on PR #2199, not the agent summary; verified `InteractivePrompt.blockType` is a required field (`frontend/src/store/types.ts:280`) so the title-bar name cannot be undefined
- [x] Scope compliance verified. -> diff touches only `InteractiveModals.tsx`, `InteractiveModals.parts/**`, their tests, and the agent's own ledger; `panelModuleLoader.ts` untouched, so A3's comment fix is unaffected; `PANEL_HOST_API_VERSION`, `PanelHostApi`, and `PanelModule` unchanged
- [x] Conflicts resolved intentionally. -> none; A2 and A3 own disjoint paths
- [ ] Track merged or integrated. -> PR #2199 open against `main`, CI 16/16 green including `Frontend`, awaiting owner review and merge; independent of the #2201 -> #2200 order in §2.2

#### 7.5.1 Manager Review Findings

- **Residual gap, not a regression.** A prompt carrying no `panel_manifest` at
  all still renders nothing and leaves the block `PAUSED` with only the Toolbar
  Stop control. That was true before this change too, and the registry refuses
  to load an interactive block without a valid manifest, so it is not reachable
  through the documented path. #2196's validation closes the upstream cause.
- **Follow-up folded in, not split out.** A3 found three more instances of the
  stale `/api/interactive/panels/...` route in A1's directory; A1 fixed those
  plus a fourth in the test file it had authored this task, which A3 could not
  have seen. Line 8 was deliberately left alone so #2200 keeps sole ownership of
  it and the two PRs do not collide on that line. Comment and fixture strings
  only; no assertion changed except the fixture URL text.
- **New UX risk introduced by the fix.** ESC now cancels the block from
  anywhere in the panel, discarding whatever the user had built up in it (a long
  labelling pass, a region selection). Before this change ESC did nothing. The
  X control is deliberate; ESC is easy to hit by accident. Raised with the owner
  for a decision — options were to keep it, confirm before cancelling on ESC, or
  drop ESC and keep X only. **Owner reviewed the tradeoff and chose to keep the
  current behaviour.** No change to #2199. Recorded here so the decision is
  durable.

## 8. Track: A2 — Interactive Contract Validation (#2196)

### 8.1 Track Scope

- Owner: `A2`
- In scope:
  - One shared validation implementation: manifest/filesystem checks and static
    panel-module source checks, at two severities (hard error vs `Warning:`).
  - Surface 1: registry scan collects rejection reasons; `reload_blocks` returns
    them instead of dropping blocks silently.
  - Surface 2: the same checks reach `scistudio.workflow.validator`, so
    `validate_workflow`, `write_workflow` verification, and run start refuse a
    hard-invalid interactive block.
  - Surface 3: a provisioned PostToolUse hook whose matcher covers panel
    `.js`/`.mjs`, not only `blocks/*.py`.
- Out of scope:
  - Executing the panel module. No JS runtime dependency.
  - A `scistudio` CLI entry point (the embedded agent is denied the CLI).
  - Frontend, skills, agent-reference docs, scaffold templates.
- Required docs:
  - `docs/package-development/blocks.md` if the validation changes what a package
    author must satisfy; the four AI docs in §5.1 if the new hook changes
    AI-runtime behavior; otherwise explicit N/A rationales.
- Required tests:
  - Per-check tests at both severities; one test per surface (`reload_blocks`
    rejection reporting, workflow-validator diagnostics, hook matcher).

### 8.2 Dispatch

- [x] Prompt file created or dispatch prompt recorded.
- [x] Correct prompt template selected.
- [x] Audit mode recorded when persona is `audit_reviewer`. -> N/A, implementer
- [x] Agent branch/worktree assigned.
- [x] Write set and out-of-scope paths included in prompt.
- [x] TODO rule included in prompt.
- [x] Required checks included in prompt.

### 8.3 Implementation

- [x] Shared validation implementation -> PR #2201, `src/scistudio/blocks/base/panel_contract.py`
- [x] Surface 1: `reload_blocks` rejection reporting -> PR #2201, `src/scistudio/blocks/registry/{__init__,_capability,_scan}.py`, `src/scistudio/ai/agent/mcp/tools_authoring.py`
- [x] Surface 2: workflow validator diagnostics -> PR #2201, `src/scistudio/workflow/validator.py` (Check 11)
- [x] Surface 3: PostToolUse hook covering panel JS -> PR #2201, `src/scistudio/agent_provisioning/templates/hook_check_panel_contract.py`, registered in `hooks.py` / `codex_config.py` / `_orchestrate.py`
- [x] Tests -> `tests/blocks/test_panel_contract.py`, `tests/blocks/test_registry_rejections.py`, `tests/workflow/test_validator_panel_contract.py`, `tests/agent_provisioning/test_hook_panel_contract_parity.py`
- [x] Docs updated or N/A recorded -> `docs/specs/adr-051-interactive-blocks.md` (FR-016/017/018), `docs/package-development/blocks.md`, `docs/agent-provisioning.md`, `CHANGELOG.md`
- [x] `admin-approved:core-change` requested on the PR -> requested, NOT self-applied; see §8.5.1

### 8.4 Audit

- [ ] Audit agent assigned, or manager audit completed.
- [ ] Audit report file path assigned.
- [ ] Audit report committed.
- [ ] Audit report merged into final PR evidence path.
- [ ] Findings recorded.
- [ ] P1 findings fixed before integration.
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale.

### 8.5 Integration

- [x] Agent output reviewed by manager. -> manager read the `workflow/validator.py` hunk and verified the new Check 11 sits after the `registry is None` early return (`validator.py:326`), so a registry-less call cannot crash on it; verified the registry never scans staged tutorial sources (no `tutorials` reference anywhere in `blocks/registry/`), which is what makes finding 2 below safe
- [x] Scope compliance verified. -> 26 files, all inside the declared write set plus the docs the dispatch required; `scaffold_block` untouched, so the §2.1 sequencing held
- [x] Conflicts resolved intentionally. -> `_orchestrate.py` is touched by both A2 and A3's pending follow-up; resolved by merge order (§2.2), not by editing either branch
- [ ] Track merged or integrated. -> PR #2201 open against `main`, CI 16/16 green, blocked on the owner applying `admin-approved:core-change`

#### 8.5.1 Manager Review Findings

- **Label deliberately not self-applied.** The agent's `gh` token authenticates
  as the repository owner, so a label it applied would have recorded as
  owner-granted authorization for a protected-core change the owner never
  reviewed — defeating the provenance check CI performs. Leaving it off was the
  right call. **Owner action required on #2201.**
- **Tutorial finding accepted, no product change needed.** The shipped
  `review_labels.py` declares an `asset_root` that does not exist in the
  repository; `tutorial.yaml:597` copies `assets/panels/review_labels` to
  `blocks/review_labels_panel` at deploy time, so the path resolves only in a
  deployed project. The manager confirmed independently that the registry
  scans project `blocks/` directories and never the packaged tutorial sources,
  so the staged file is a template that is never validated in place. Adjusting
  the test to deploy the pair first is correct; realigning the source layout is
  not required.
- **CSS severity deviation accepted.** The issue listed `css` resolution among
  the deterministic hard errors on the rationale that those "fail at runtime
  with certainty". A missing stylesheet does not: `injectManifestCss` appends
  the `<link>`, it 404s, and the panel still mounts. Making it a hard error
  would refuse a workflow that runs correctly. Off-origin CSS stays a hard
  error; a CSS file absent from disk is an advisory. The agent applied the
  issue's own stated principle rather than its literal table — correct.
- **Two pre-existing containment bugs fixed as a side effect,** reported by the
  agent: Tier 1/2 scanning abandoned the rest of a file or package when one
  class was refused, and Tier 3 had no containment at all, so a single bad class
  dropped an entire source package behind one log line. In scope as the same
  silent-drop defect this issue targets.

## 9. Track: A3 — Panel Authoring Skill And Scaffold (#2197)

### 9.1 Track Scope

- Owner: `A3`
- In scope:
  - A dedicated interactive-panel authoring skill under
    `src/scistudio/_skills/scistudio/`, routed from `scistudio-write-block`.
  - An interactive scaffold: block `.py` with a correctly filled `PanelManifest`
    plus a panel module skeleton with default export, `apiVersion`, `mount`
    returning `{ unmount }`, and wired confirm and cancel controls.
  - Documentation fixes in `block-contract.md` (default export; exact
    `module_url` shape and filename) and the stale route comment in
    `panelModuleLoader.ts` line 8 (comment text only).
- Out of scope:
  - `src/scistudio/ai/agent/mcp/tools_authoring.py` — see §2.1. Expose a helper;
    the manager wires it.
  - Any frontend behavior change. The loader edit is a comment.
  - The validation implementation itself (A2 owns it); route to it only.
- Required docs:
  - `src/scistudio/_agent_reference/block-contract.md`, the new skill file, and
    `docs/package-development/blocks.md` if the panel contract text lives there
    too.
- Required tests:
  - Scaffold output shape: the generated block registers and the generated panel
    module satisfies the contract checks.

### 9.2 Dispatch

- [x] Prompt file created or dispatch prompt recorded.
- [x] Correct prompt template selected.
- [x] Audit mode recorded when persona is `audit_reviewer`. -> N/A, implementer
- [x] Agent branch/worktree assigned.
- [x] Write set and out-of-scope paths included in prompt.
- [x] TODO rule included in prompt.
- [x] Required checks included in prompt.

### 9.3 Implementation

- [x] Panel authoring skill -> PR #2200, `src/scistudio/_skills/scistudio/scistudio-write-panel/SKILL.md`, routed from `scistudio-write-block/SKILL.md` and the base `SKILL.md` index
- [x] Interactive scaffold helper + templates -> PR #2200, `src/scistudio/ai/agent/mcp/panel_scaffold.py`, `src/scistudio/cli/templates/interactive_block/{block.py.tpl,panel.mjs.tpl}`
- [x] `block-contract.md` default-export and `module_url` fixes -> PR #2200, `src/scistudio/_agent_reference/block-contract.md`
- [x] `panelModuleLoader.ts` route comment fix -> PR #2200 (line 8 only; two more found at 114 and 129, see §9.5.1)
- [x] Tests -> `tests/ai/test_panel_scaffold.py` (17 tests)
- [ ] Skill provisioning registration -> BLOCKED on #2201 merging; see §2.2
- [ ] Manager wires `scaffold_block` after #2196 merges (§2.1) -> BLOCKED on #2201 merging

### 9.4 Audit

- [ ] Audit agent assigned, or manager audit completed.
- [ ] Audit report file path assigned.
- [ ] Audit report committed.
- [ ] Audit report merged into final PR evidence path.
- [ ] Findings recorded.
- [ ] P1 findings fixed before integration.
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale.

### 9.5 Integration

- [x] Agent output reviewed by manager. -> manager reviewed the 10-file diff; the scaffold helper lives in a new module and imports nothing from `tools_authoring.py`, so the §2.1 sequencing held
- [x] Scope compliance verified. -> only the declared paths; the single frontend edit is 5 lines of comment in `panelModuleLoader.ts`, no behavior
- [x] Conflicts resolved intentionally. -> the pending provisioning step touches `_orchestrate.py`, which A2 also edits; resolved by merge order (§2.2)
- [ ] Track merged or integrated. -> PR #2200 open, CI 16/16 green, but NOT mergeable until the two follow-ups in §2.2 land

#### 9.5.1 Manager Review Findings

- **The deliverable is incomplete as merged-ready.** The skill ships in the
  wheel (`_skills/scistudio/**/*.md` is already a glob) but is not provisioned
  into any project until it is registered in three files that belong to A2's
  write set. The agent stopped at the scope boundary and reported instead of
  crossing it, which is correct behaviour, but #2200 must not merge in this
  state or the skill will exist and never be delivered to an agent.
- **Two more stale route comments** at `panelModuleLoader.ts:114` and `:129`,
  inside `isSameOriginModuleUrl`'s doc comment, still name the nonexistent
  `/api/interactive/panels/...` route, and the fixture URLs in
  `panelModuleLoader.test.ts:12` and `DynamicPanel.test.tsx:12` model the same
  wrong shape. All four are in A1's directory. Folded into the A1 track rather
  than opened as a separate issue; recorded in §11.
- **`docs/package-development/blocks.md` correctly needed nothing from A3** — it
  does not document the interactive panel contract at all. A2 added that
  document's interactive section instead, which is the right home.
- **Unrelated CI flake found and filed.** The `Frontend` job fails
  intermittently on `main` in `OpenAsDialog.test.tsx` /
  `BringInMyWorkDialog.test.tsx` (dialogs from #2112). Filed as #2203 so it does
  not train reviewers to rerun red CI on these three PRs without reading it.

## 10. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Gate ledger check (local) | `python -m scistudio.qa.governance.gate_record check --mode local --base origin/main --head HEAD` | `[ ]` | `pending` |
| Targeted tests | `per-track, recorded with gate_record amend --test-path` | `[ ]` | `pending` |
| Pre-push gate check | `python -m scistudio.qa.governance.gate_record check --mode pre-push --base origin/main --head HEAD` | `[ ]` | `pending` |
| Gate ledger check (pre-PR) | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `[ ]` | `pending` |
| Gate finalize (pre-PR) | `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#<issue>"` | `[ ]` | `pending` |
| Wrapper preflight | `python scripts/scistudio_pr_create.py --dry-run --title "<title>" --body "<body>"` | `[ ]` | `pending` |
| Frontend smoke (A1) | `manager-run desktop smoke on a paused interactive block` | `[ ]` | `pending` |

## 11. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| `2026-08-26` | `manager` | `agent-dispatch.md §2 defaults agent PRs to the umbrella branch; owner directed three independent PRs to main.` | `Manager explicitly assigns each agent its own final PR to main per §4 of the same rules; umbrella branch and [DO NOT MERGE] PR still created for visibility and to carry this checklist.` | `Recorded in §1.1` |
| `2026-08-26` | `manager` | `A2 and A3 both have a claim on src/scistudio/ai/agent/mcp/tools_authoring.py.` | `Sequenced: A2 owns the file; A3 exposes a helper and the manager wires scaffold_block after #2196 merges.` | `Recorded in §2.1; row in §9.3` |
| `2026-08-27` | `A3` | `Skill provisioning registration (skills.py, _orchestrate.py, claude_agents_md.md) is required for A3's deliverable but sits in A2's write set. A3 stopped at the boundary and reported.` | `Correct behaviour, not drift. Manager adds it to A3's branch after #2201 merges; merge order recorded in §2.2.` | `§2.2, §9.3, §9.5.1` |
| `2026-08-27` | `A3` | `Found two further stale route comments at panelModuleLoader.ts:114 and :129 plus two wrong-shape test fixture URLs, all in A1's directory.` | `Folded into the A1 track as a follow-up on #2199 rather than a separate issue — comment-only, same defect as the line 8 fix.` | `§7.3, §9.5.1` |
| `2026-08-27` | `manager` | `Frontend CI job flakes on main in OpenAsDialog / BringInMyWorkDialog (from #2112), unrelated to this dispatch.` | `Filed as its own issue rather than absorbed into any of the three PRs.` | `#2203` |
| `2026-08-27` | `owner` | `ESC now cancels a block and discards in-panel work, a new mis-press risk introduced by #2199 (§7.5.1).` | `Owner reviewed the tradeoff and chose to keep the current behaviour; no change to #2199.` | `Closed` |

## 12. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence when needed, commit, and PR evidence.
- [ ] PR closes every issue fixed by the dispatch.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
