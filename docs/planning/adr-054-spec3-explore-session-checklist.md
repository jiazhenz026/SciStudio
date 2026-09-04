---
title: "ADR-054 Spec 3 Explore Session Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# ADR-054 Spec 3 Explore Session Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: `Implement ADR-054 spec 2 and spec 3 in full, with a final adversarial test engineer and a no-context auditor, delivered as two PRs for owner review.`
- Task kind: `manager`
- Manager persona: `manager`
- Issue: `#2240`
- Gate record: `.workflow/records/2240-explore-session-dispatch.json`
- Branch/worktree plan: manager on `track/adr-054-spec3-explore-session` in
  `.worktrees/mgr-2240-spec3-explore`; agents on `feat/2240-*`, `test/2240-*`,
  `audit/2240-*` branches, one dedicated worktree each under `.worktrees/`.
- Protected branch: `main`
- Umbrella branch: `track/adr-054-spec3-explore-session`
- Umbrella PR: `#2241`
- Umbrella PR title: `[DO NOT MERGE] ADR-054 Spec 3: the Explore Session runtime`
- Final PR target: `track/adr-054-spec2-dependency-analysis`, retargeted to
  `main` once spec 2 merges. See §1.2.
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

### 1.1 Delivery Order

Spec 3 consumes spec 2. The spec 3 branch is cut from
`track/adr-054-spec2-dependency-analysis` and the manager merges spec 2's
integrated work forward as it lands, so the spec 3 diff contains only spec 3's
own change.

### 1.2 Stacked-Base Hazard

`ci.yml` fires only for pull requests whose base is `main` or `track/**`, which
is why the spec 3 PR targets the spec 2 track branch rather than a `feat/`
branch. Two consequences the owner must know before merging:

1. **Merge spec 2's PR first, then retarget spec 3's PR to `main`.** Merging
   spec 2 while spec 3 still points at the spec 2 track branch would let spec 3
   merge into an already-merged branch, where its commits never reach `main`
   and its closing keyword never fires.
2. Verify with
   `git log --oneline origin/main..origin/track/adr-054-spec3-explore-session`
   after the merge; a non-empty result means the work never landed.

## 2. Scope

- In scope:
  - `src/scistudio/explore/**` — session, kernel, bridge, notebook API,
    notebook store, queue, packaging, lineage.
  - `src/scistudio/__init__.py` — the three lazy notebook helpers.
  - `src/scistudio/core/versioning/_commit_ops.py` — plumbing commit to a ref.
  - `src/scistudio/core/lineage/{record,store,retention,environment}.py` — the
    `explore_sessions` anchor and cell-run records.
  - `src/scistudio/blocks/code/backends/notebook.py` — cell selection and
    packaged-mode environment.
  - `src/scistudio/blocks/base/interactive.py` — `on_new_input`.
  - `src/scistudio/engine/scheduler/_dispatch.py` — the policy and the packaged
    block's ask pause.
  - `src/scistudio/api/routes/explore.py`, `src/scistudio/api/ws.py`,
    `src/scistudio/api/project_layout.py`.
  - `pyproject.toml` — `ipykernel` and `jupyter_client`.
  - `tests/explore/**`, `tests/api/test_explore_routes.py`,
    `tests/blocks/base/test_interaction_policy.py`, `tests/core/**`,
    `tests/architecture/test_layer_deps.py`.
  - `docs/planning/adr-054-spec3-*`, `docs/audit/**`, `.workflow/records/2240-*.json`.
- Out of scope:
  - Every frontend path. `adr-054-explore-frontend` owns the Explore tab, the
    notebook shell, and every rendering decision.
  - The agent harness. `adr-054-agent-enablement` owns the skill, the panel and
    session tools, and the workspace focus.
  - The documentation revision. `adr-054-documentation` owns the architecture
    document, the package-development guides, and the generated reference.
  - `docs/specs/adr-054-*.md` — approved input, not work product.
  - `docs/architecture/**` — owner-controlled.
- Protected paths:
  - `src/scistudio/core/lineage/**`
  - `src/scistudio/core/versioning/_commit_ops.py`
  - `src/scistudio/blocks/base/interactive.py`
  - `src/scistudio/engine/scheduler/_dispatch.py`
  - Each touch is additive per spec §4.5. The final PR carries
    `admin-approved:core-change`, pre-approved by the owner.
- Deferred work:
  - N/A at dispatch time. Any deferral must be a `TODO(#NNN)` citing an issue.

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
- [x] Existing issue linked, or new issue created only if none exists.
      No open issue tracked the spec 3 runtime; `#2240` was created for it and
      is referenced from the ADR's tracking issue `#2209`.
- [x] Gate record started.
- [x] Scope include/exclude recorded in the gate record.
- [x] Umbrella branch created.
- [x] Umbrella PR opened. `#2241`.
- [x] Umbrella PR title includes `[DO NOT MERGE]`.
- [x] Protected branch and umbrella PR number recorded in this checklist.
- [x] No `pip install -e .` environment pollution found.
- [x] Dispatch checklist copied from the template and committed.
- [x] Dispatch prompts created from the correct prompt template and linked
      below.
- [x] Sentrux baseline recorded, or N/A reason recorded.
      N/A: Sentrux MCP is not connected in this session.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `admin-approved:core-change`
- Owner authorization source: `Owner chat, 2026-09-04: every label this work needs is pre-approved.`
- Reason: `Spec 3 modifies four protected core paths — lineage, the versioning commit ops, the interactive block base, and the engine's dispatch. Spec §4.5 records each as additive. This label authorizes the protected paths only; it is not a gate bypass.`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record check --mode pre-commit` | `admin-approved:core-change` | `[ ]` | |
| Commit message | `python -m scistudio.qa.governance.gate_record check --mode commit-msg` | `N/A` | `[ ]` | |
| Pre-push | `python -m scistudio.qa.governance.gate_record check --mode pre-push` | `admin-approved:core-change` | `[ ]` | |
| Pre-PR reconcile | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `admin-approved:core-change` | `[ ]` | |

## 5.1 Docs Impact Check

- Wrapper/hook/gate-record/receipt/CI/runtime behavior changed: `no`
- AI docs checked:
  `docs/ai-developer/rules.md`,
  `docs/ai-developer/specific_rules/gated-workflow.md`,
  `docs/ai-developer/specific_rules/agent-dispatch.md`,
  `docs/ai-developer/templates/*dispatch*.md`
- Updated docs or N/A rationale: `The governing spec landed in PR #2228. ADR-054's documentation spec owns the architecture document and the developer guides and is a separate delivery. CHANGELOG.md gains an entry for the new dependencies and the release-runbook note about rebuilding the bundled runtime.`

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| `S3-A1` | `implementer` | `N/A` | `docs/planning/adr-054-spec3-dispatch-prompts/s3-a1-notebook-store.md` | T-001 dependencies, T-005 notebook store | `feat/2240-notebook-store` | `.worktrees/s3-a1-notebook` | `pyproject.toml`, `src/scistudio/explore/notebook.py`, `tests/explore/test_notebook_store.py` | `tests/architecture/**`, every other explore module | `#2240` | `[x]` |
| `S3-A2` | `implementer` | `N/A` | `docs/planning/adr-054-spec3-dispatch-prompts/s3-a2-kernel.md` | T-002 kernel handle over `jupyter_client` | `feat/2240-kernel-handle` | `.worktrees/s3-a2-kernel` | `src/scistudio/explore/kernel.py`, `tests/explore/test_kernel_session.py` | `pyproject.toml`, every other explore module | `#2240` | `[x]` |
| `S3-A3` | `implementer` | `N/A` | `docs/planning/adr-054-spec3-dispatch-prompts/s3-a3-commit-plumbing.md` | T-009 plumbing commit to a ref with a temporary index; forced packing | `feat/2240-explore-commits` | `.worktrees/s3-a3-commits` | `src/scistudio/core/versioning/_commit_ops.py`, `tests/core/versioning/test_explore_ref_commits.py` | Every explore module, every other core path | `#2240` | `[ ]` |
| `S3-A4` | `implementer` | `N/A` | `docs/planning/adr-054-spec3-dispatch-prompts/s3-a4-on-new-input.md` | T-015a the `on_new_input` setting and the engine's remap policy | `feat/2240-on-new-input` | `.worktrees/s3-a4-policy` | `src/scistudio/blocks/base/interactive.py`, `src/scistudio/engine/scheduler/_dispatch.py`, `tests/blocks/base/test_interaction_policy.py` | Every explore module | `#2240` | `[x]` |
| `S3-B1` | `implementer` | `N/A` | `docs/planning/adr-054-spec3-dispatch-prompts/s3-b1-bridge.md` | T-003 bridge, T-004 notebook helpers, T-010 variable windows, T-011 env snapshot | `feat/2240-kernel-bridge` | `.worktrees/s3-b1-bridge` | `src/scistudio/explore/kernel_bridge.py`, `src/scistudio/explore/notebook_api.py`, `src/scistudio/__init__.py`, `src/scistudio/core/lineage/environment.py`, `tests/explore/test_kernel_bridge.py`, `tests/explore/test_notebook_api.py` | Every other explore module | `#2240` | `[x]` |
| `S3-B2` | `implementer` | `N/A` | `docs/planning/adr-054-spec3-dispatch-prompts/s3-b2-session-queue.md` | T-006 session open/list/close, T-007 queue, T-008 marks, T-016 kernel list and branch-switch retirement | `feat/2240-session-queue` | `.worktrees/s3-b2-session` | `src/scistudio/explore/session.py`, `src/scistudio/explore/queue.py`, `src/scistudio/api/project_layout.py`, `tests/explore/test_explore_session.py`, `tests/explore/test_queue_and_marks.py` | Every other explore module | `#2240` | `[ ]` |
| `S3-B3` | `implementer` | `N/A` | `docs/planning/adr-054-spec3-dispatch-prompts/s3-b3-block-calls.md` | T-012 block-call adapter in the kernel, including the interactive-block call | `feat/2240-block-calls` | `.worktrees/s3-b3-blockcall` | `src/scistudio/explore/block_call.py`, `tests/explore/test_block_call_adapter.py` | Every other explore module | `#2240` | `[ ]` |
| `S3-C1` | `implementer` | `N/A` | `docs/planning/adr-054-spec3-dispatch-prompts/s3-c1-lineage.md` | T-013 `explore_sessions`, cell-run records, block-call records, retention | `feat/2240-explore-lineage` | `.worktrees/s3-c1-lineage` | `src/scistudio/core/lineage/{record,store,retention}.py`, `src/scistudio/explore/lineage.py`, `tests/explore/test_explore_lineage.py` | Every other explore module | `#2240` | `[ ]` |
| `S3-C2` | `implementer` | `N/A` | `docs/planning/adr-054-spec3-dispatch-prompts/s3-c2-packaging.md` | T-014 packaging and the notebook backend's cell selection, T-015b the ask pause | `feat/2240-packaging` | `.worktrees/s3-c2-packaging` | `src/scistudio/explore/packaging.py`, `src/scistudio/blocks/code/backends/notebook.py`, `tests/explore/test_packaged_block.py` | Every other explore module | `#2240` | `[ ]` |
| `S3-C3` | `implementer` | `N/A` | `docs/planning/adr-054-spec3-dispatch-prompts/s3-c3-api.md` | T-017 session API routes and WebSocket events, and the FR-060 layer rule | `feat/2240-explore-api` | `.worktrees/s3-c3-api` | `src/scistudio/api/routes/explore.py`, `src/scistudio/api/ws.py`, `tests/api/test_explore_routes.py`, `tests/architecture/test_layer_deps.py` | Every explore module | `#2240` | `[ ]` |
| `S3-D1` | `test_engineer` | `N/A` | `docs/planning/adr-054-spec3-dispatch-prompts/s3-d1-adversarial.md` | Adversarial end-to-end coverage: kernel lifecycle against a real process, the marks, the refusals, the commits, packaging | `test/2240-adversarial` | `.worktrees/s3-d1-adversarial` | `tests/explore/**`, `tests/api/test_explore_routes.py` | Every production path. Report defects, do not fix them. | `#2240` | `[ ]` |
| `S3-E1` | `audit_reviewer` | `no-context` | `docs/planning/adr-054-spec3-dispatch-prompts/s3-e1-audit-no-context.md` | Independent audit of the explore subsystem against the repository's own documents | `audit/2240-no-context` | `.worktrees/s3-e1-audit-nc` | `docs/audit/2026-09-04-explore-session-no-context.md` | Every implementation and test path. Read-only. | `#2240` | `[ ]` |
| `S3-E2` | `audit_reviewer` | `with-context` | `docs/planning/adr-054-spec3-dispatch-prompts/s3-e2-audit-with-context.md` | Audit of the delivered spec 3 work against the spec, the issue, and this checklist | `audit/2240-with-context` | `.worktrees/s3-e2-audit-wc` | `docs/audit/2026-09-04-adr-054-spec3-with-context.md` | Every implementation and test path. Read-only. | `#2240` | `[ ]` |
| `S3-F1` | `implementer` | `N/A` | `docs/planning/adr-054-spec3-dispatch-prompts/s3-f1-fix.md` | Fix the P1 and P2 findings the audits and the adversarial test engineer produce | `fix/2240-audit-findings` | `.worktrees/s3-f1-fix` | Every in-scope production and test path | Everything else | `#2240` | `[ ]` |

For `test_engineer` rows, the write set should default to tests, fixtures,
validation scripts, e2e scenarios, audit evidence, and explicitly assigned
QA/governance tooling. Production code paths require a recorded scope
amendment.

## 7. Track: The Explore Session Runtime

### 7.1 Track Scope

- Owner: manager
- In scope:
  - The session service and the project layout it needs (FR-001 to FR-006,
    FR-036).
  - The kernel, the bridge, the three helpers, `%pip` and the environment
    re-snapshot, interrupt, restart, stop, and branch-switch retirement
    (FR-007 to FR-016).
  - The queue, the admission whitelist, coalescing, the observation call, the
    marks, run-stale, run-with-upstream, the shallow freeze bound (FR-017 to
    FR-026).
  - Storage and history through git plumbing on a dedicated ref (FR-027 to
    FR-036).
  - Packaging into a Code Block and the backend's cell selection (FR-037 to
    FR-043).
  - `on_new_input` for both block kinds and the packaged block's ask pause
    (FR-044 to FR-048).
  - Calling a block from a cell (FR-049 to FR-051).
  - Lineage: the `explore_sessions` anchor, cell-run and block-call records,
    retention (FR-052 to FR-055).
  - The API and its events (FR-056 to FR-058).
  - The dependencies and the layer rule (FR-059, FR-060).
- Out of scope:
  - Every rendering decision and every frontend file.
  - The agent harness and the documentation revision.
- Required docs:
  - `CHANGELOG.md` — the new runtime dependencies and the session surface.
  - The rest is N/A: the governing spec landed in PR #2228, and ADR-054's
    documentation spec owns the architecture document and the developer guides
    as a separate delivery.
- Required tests:
  - `tests/explore/test_kernel_session.py`
  - `tests/explore/test_block_call_adapter.py`
  - `tests/explore/test_packaged_block.py`
  - `tests/explore/test_explore_lineage.py`
  - `tests/api/test_explore_routes.py`
  - `tests/blocks/base/test_interaction_policy.py`
  - `tests/architecture/test_layer_deps.py`

### 7.2 Dispatch

- [x] Prompt file created or dispatch prompt recorded.
- [x] Correct prompt template selected.
- [x] Audit mode recorded when persona is `audit_reviewer`.
- [x] Agent branch/worktree assigned.
- [x] Write set and out-of-scope paths included in prompt.
- [x] TODO rule included in prompt.
- [x] Required checks included in prompt.

### 7.3 Implementation

- [x] `S3-A1` dependencies and the notebook store -> merged into the track branch.
  `pyproject.toml` (`ipykernel`, `jupyter_client`), `src/scistudio/explore/notebook.py`,
  `tests/explore/test_notebook_store.py` 86 passed with 100% statement coverage of the
  module, `CHANGELOG.md`. Every round-trip test starts from a notebook the store did not
  write, including a hand-edited file with two-space indent and unsorted keys.
  Gate ledger: `.workflow/records/2240-feat-2240-notebook-store.json`.
- [x] `S3-A2` kernel handle -> merged into the track branch.
  `src/scistudio/explore/kernel.py`, `tests/explore/test_kernel_session.py` 47 passed /
  1 skipped **against a real ipykernel 7.3.0** in an isolated venv outside the repo. The
  ADR-054 §5.2 interrupt blocker is resolved and inverted: signal mode ends a spinning
  cell within a tenth of a second on Windows, message mode is inert there, and the handle
  refuses message mode on Windows at construction. The assertion was mutation-checked.
  Gate ledger: `.workflow/records/2240-feat-2240-kernel-handle.json`.
- [ ] `S3-A3` plumbing commits to a ref -> artifact pending
- [x] `S3-A4` `on_new_input` and the remap policy -> `feat/2240-on-new-input` @ `1c279895c`; `tests/blocks/base/test_interaction_policy.py` 36 passed, `tests/engine` 522 passed 4 skipped, `tests/blocks` 1511 passed 8 skipped
- [x] `S3-B1` bridge, helpers, windows, environment snapshot -> `feat/2240-kernel-bridge`.
  `src/scistudio/explore/kernel_bridge.py`, `src/scistudio/explore/notebook_api.py`,
  `src/scistudio/__init__.py` (the three helpers, lazily), and
  `src/scistudio/core/lineage/environment.py` (snapshot by reference, FR-034).
  `tests/explore/test_kernel_bridge.py` + `tests/explore/test_notebook_api.py` 80 passed
  **against a real ipykernel 7.3.0** in the isolated venv outside the repo, and 72 passed /
  8 skipped under the repository venv, where the kernel tests skip and the pure ones still
  run. The two load-bearing tests: one fixture notebook source executed in session mode and
  in packaged mode with the outputs compared, and a bridge call proved to leave no cell by
  reading the kernel's own input history and execution counter back out of it. `%pip` is
  exercised as a real offline install into a throwaway virtual environment.
  Gate ledger: `.workflow/records/2240-feat-2240-kernel-bridge.json`.
- [ ] `S3-B2` session, queue, marks, kernel list -> artifact pending
- [ ] `S3-B3` block-call adapter -> artifact pending
- [ ] `S3-C1` lineage -> artifact pending
- [ ] `S3-C2` packaging and the backend's cell selection -> artifact pending
- [ ] `S3-C3` API routes, events, and the layer rule -> artifact pending
- [ ] `S3-D1` adversarial coverage -> artifact pending
- [ ] docs `CHANGELOG.md` -> artifact pending

### 7.4 Audit

- [ ] Audit agent assigned, or manager audit completed.
- [ ] Audit report file path assigned.
- [ ] Audit report committed.
- [ ] Audit report merged into final PR evidence path.
- [ ] Findings recorded.
- [ ] P1 findings fixed before integration.
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale.

### 7.5 Integration

- [ ] Agent output reviewed by manager.
- [ ] Scope compliance verified.
- [ ] Conflicts resolved intentionally.
- [ ] Track merged or integrated.

## 8. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Gate ledger check (local) | `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record check --mode local --base origin/track/adr-054-spec2-dependency-analysis --head HEAD` | `[ ]` | |
| Targeted tests | `PYTHONPATH=./src python -m pytest tests/explore tests/api/test_explore_routes.py tests/blocks/base/test_interaction_policy.py -q` | `[ ]` | |
| Pre-push gate check | `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record check --mode pre-push --base origin/track/adr-054-spec2-dependency-analysis --head HEAD` | `[ ]` | |
| Gate ledger check (pre-PR) | `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `[ ]` | |
| Gate finalize (pre-PR) | `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record finalize --commit SHA --pr-body-file .workflow/local/pr-body.md --closes "#2240"` | `[ ]` | |
| Wrapper preflight | `PYTHONPATH=./src python scripts/scistudio_pr_create.py --dry-run --title TITLE --body BODY` | `[ ]` | |

## 9. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-09-04 | manager | The layer-test edit is claimed by spec 2's `S2-B1` and by spec 3's FR-060 rule. | Spec 3's `S3-C3` owns the layer file and lands after spec 2's version is merged forward, so the two edits never race. | N/A |
| 2026-09-04 | manager | `ipykernel`, `jupyter_client`, and `nbconvert` are absent from the local `.venv`, and installing them was refused by the sandbox. | Real-kernel tests (FR-013, ADR-054 §5.2) skip locally and run only in CI, which installs from `pyproject.toml`. Agents were told to leave honestly-skipped tests rather than mocked-passing ones. | Verify the interrupt test actually ran in CI before calling FR-013 covered. |
| 2026-09-04 | `S3-A3` | The four plumbing functions had no binding onto `GitEngine`, and `git_engine.py` was outside the declared scope. | Manager amended the ledger to include `src/scistudio/core/versioning/git_engine.py` and sent the agent back to add the binding, the ADR-052 stability markers, and coverage for the public surface. | N/A |
| 2026-09-04 | `S3-A3` | `_commit_ops.py` cannot import `scistudio.stability`; `tests/core/test_git_engine.py::test_no_circular_import` loads the module under a stub package. | Stability markers move to the `git_engine.py` binding block. The agent added a guard test so the constraint fails at the point of change. | N/A |

## 10. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence when needed, commit, and PR evidence.
- [ ] PR closes every issue fixed by the dispatch.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
