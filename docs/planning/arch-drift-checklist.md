---
title: "Architecture Drift + Engine Collection Wrap Umbrella Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
language_source: en
---

# Architecture Drift + Engine Collection Wrap Umbrella Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request (revised 2026-05-21): scope narrowed to #1330 + #1332 only after manager push-back on P1-1 subprocess refactor size.
- Task kind: `manager` (umbrella coordinates two impl tracks)
- Manager persona: `manager`
- Issues:
  - `#1330` — engine: auto-wrap bare DataObject into length-one Collection (Track A closes)
  - `#1332` — engine: TypeRegistry filesystem scan for project/user `types/` dirs (Track B closes)
- Deferred from this umbrella (stay open as standalone issues):
  - `#1331` — P1-1 interactive subprocess: requires bidirectional IPC redesign + ADR, too large for overnight autonomous work
  - `#887` — P1-2 resource gating: owner directive keeps ARCHITECTURE §6 as final commitment; impl deferred to #887's own scope
- Gate record: `.workflow/records/1330-umbrella-arch-drift.json`
- Branch/worktree plan:
  - Manager worktree: `.claude/worktrees/umbrella-arch-drift` on `umbrella/arch-drift-and-collection-wrap`
  - Track A worktree: dispatch creates `.claude/worktrees/track-a-collection-wrap` on `fix/issue-1330-engine-collection-wrap`
  - Track B worktree: dispatch creates `.claude/worktrees/track-b-arch-drift-docs` on `docs/issue-1331-1332-arch-drift`
- Protected branch: `main`
- Umbrella branch: `umbrella/arch-drift-and-collection-wrap`
- Umbrella PR: `#<pending>` (created after first commit)
- Umbrella PR title: `[DO NOT MERGE] umbrella: architecture drift P1 fixes + engine Collection auto-wrap`
- Final PR target: `main`
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`

## 2. Scope

- In scope:
  - `src/scistudio/engine/runners/worker.py` (Track A)
  - `src/scistudio/engine/scheduler.py` (Track A)
  - `tests/engine/` (Track A)
  - `src/scistudio/core/types/registry.py` (Track B)
  - `src/scistudio/api/runtime.py` (Track B)
  - `tests/core/` (Track B)
  - `docs/planning/arch-drift-checklist.md` (manager)
  - `.workflow/records/1330-umbrella-arch-drift.json` (manager)
- Out of scope:
  - `docs/architecture/ARCHITECTURE.md` — owner directive 2026-05-21: ARCHITECTURE.md is the **final commitment**, do not weaken doc claims. impl must catch up.
  - Removing the six existing manual `Collection([result], item_type=X)` wraps in concrete blocks (`merge.py`, `split.py`, `code_block.py`, `process_block.py`, `app_block.py`, `ai_block.py`) — defer to follow-up cleanup PR per #1330 spec
  - Wiring `resource_manager.acquire()` into scheduler dispatch (P1-2 impl) — defer to #887
  - Refactoring interactive blocks to run in subprocess (P1-1 impl) — bidirectional IPC redesign + ADR needed; defer to #1331
- Protected paths:
  - `.workflow/records/1330-umbrella-arch-drift.json` (manager-owned governance file; `governance_touch=true` recorded)
- Deferred work:
  - `TODO(#887): wire per-block resource_request into scheduler.can_dispatch + acquire/release. ARCHITECTURE.md §6 stays as final commitment.`
  - `TODO(#1330): follow-up cleanup PR removes six manual Collection wraps in blocks/ after engine wrap soak-tests in production`
  - `TODO(#1331): refactor interactive blocks to subprocess execution. Needs bidirectional IPC channel design + ADR.`

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

- [x] Dedicated manager branch and worktree created. → `umbrella/arch-drift-and-collection-wrap` at `.claude/worktrees/umbrella-arch-drift`
- [x] Existing issues linked. → #1330, #1331, #1332, #887
- [x] Gate record started. → `.workflow/records/1330-umbrella-arch-drift.json`
- [x] Scope include/exclude recorded in the gate record.
- [x] Umbrella branch created.
- [ ] Umbrella PR opened.
- [ ] Umbrella PR title includes `[DO NOT MERGE]`.
- [ ] Protected branch and umbrella PR number recorded in this checklist.
- [x] No `pip install -e .` environment pollution found.
- [x] Dispatch checklist copied from the template and committed.
- [ ] Dispatch prompts created from the correct prompt template and linked below.
- [ ] Sentrux baseline recorded, or N/A reason recorded.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A`
- Owner authorization source: `N/A`
- Reason: `N/A` (no bypass needed)

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record pre-commit --staged` | `N/A` | `[ ]` | pending |
| Commit message | `python -m scistudio.qa.governance.gate_record commit-msg <commit-msg-file>` | `N/A` | `[ ]` | pending |
| Pre-push | `python -m scistudio.qa.governance.gate_record pre-push` | `N/A` | `[ ]` | pending |

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| Track-A | implementer | N/A | (inline below in §7.A) | engine Collection auto-wrap | `fix/issue-1330-engine-collection-wrap` | `.claude/worktrees/track-a-collection-wrap` | `src/scistudio/engine/runners/worker.py`, `src/scistudio/engine/scheduler.py`, `tests/engine/test_collection_wrap.py` (new) | `docs/architecture/ARCHITECTURE.md`, the six manual-wrap block files | `#1330` / `<PR-A pending>` | `[ ]` |
| Track-B | implementer | N/A | (inline below in §7.B) | TypeRegistry filesystem scan for project/user `types/` | `fix/issue-1332-types-scan` | `.claude/worktrees/track-b-types-scan` | `src/scistudio/core/types/registry.py`, `src/scistudio/api/runtime.py`, `tests/core/test_type_registry_scan_dirs.py` (new) | `docs/architecture/ARCHITECTURE.md`, anything outside TypeRegistry path | `#1332` / `<PR-B pending>` | `[ ]` |

## 7. Tracks

### 7.A Track A: Engine Collection Auto-Wrap (Closes #1330)

#### 7.A.1 Track Scope

- Owner: Track-A agent
- In scope:
  - Add helper `_normalize_outputs(outputs, output_ports)` in `src/scistudio/engine/runners/worker.py`
  - Call helper from worker subprocess path (between `block.run()` and `serialise_outputs`) and from in-process path in `src/scistudio/engine/scheduler.py` (before `self._block_outputs[node_id] = result`)
  - Tests: new `tests/engine/test_collection_wrap.py` with 3 regression tests:
    1. block returns bare DataObject on `is_collection=True` port → engine wraps into `Collection([value], item_type=type(value))`
    2. block returns Collection on `is_collection=True` port → engine no-op (no double-wrap)
    3. block returns bare DataObject on `is_collection=False` port → engine pass-through
- Out of scope:
  - Removing the six existing manual wraps (#1330 explicitly defers this to a follow-up PR after engine wrap soaks)
  - Touching ADR-020 (already matches proposed fix)
  - Touching `core/types/collection.py` or `port_accepts_type` (Add6 already covers)
  - ARCHITECTURE.md edits (Track B owns docs)
- Required docs:
  - N/A: `docs/architecture/ARCHITECTURE.md:1125-1127` already describes the contract correctly; impl now matches doc. Record N/A rationale in gate record `docs` stage.
- Required tests:
  - `tests/engine/test_collection_wrap.py` (3 tests above)

#### 7.A.2 Dispatch

- [ ] Prompt inline below (`§7.A.5`)
- [x] Correct prompt template selected: `agent-dispatch-prompt-template.md`
- [x] Agent branch/worktree assigned: `fix/issue-1330-engine-collection-wrap` at `.claude/worktrees/track-a-collection-wrap`
- [x] Write set and out-of-scope paths included in prompt.
- [x] TODO rule included in prompt.
- [x] Required checks included in prompt.

#### 7.A.3 Implementation

- [ ] `_normalize_outputs` helper added → `<artifact>`
- [ ] Worker subprocess call site wired → `<artifact>`
- [ ] In-process scheduler call site wired → `<artifact>`
- [ ] `tests/engine/test_collection_wrap.py` added (3 tests) → `<artifact>`

#### 7.A.4 Audit

- [ ] Manager review of Track-A diff before merge into umbrella.
- [ ] Audit report path: manager checklist row + Track-A PR commit messages
- [ ] Findings recorded: pending

#### 7.A.5 Integration

- [ ] Track-A PR opened against umbrella branch.
- [ ] Track-A PR CI green.
- [ ] Manager reviewed scope compliance.
- [ ] Track-A merged into umbrella.

### 7.B Track B: ARCHITECTURE.md Drift Fixes (Closes #1331, #1332; references #887)

#### 7.B.1 Track Scope

- Owner: Track-B agent
- In scope:
  - **§5.3 (line 771-786)**: Add explicit interactive-blocks-in-process exception. Cite [scheduler.py:341-344](src/scistudio/engine/scheduler.py#L341) comment + #591/#594 design rationale. The unqualified "Block logic runs outside the engine process" claim becomes "Non-interactive block logic runs outside the engine process" with a new paragraph describing the interactive exception.
  - **§6 (lines around 963, 1075, 1088)**: Revise resource-gating language. Current text claims block-declared CPU/GPU dispatch gating; actual behavior is OS memory watermark only (psutil L2). Update to describe the L2 watermark behavior as the current production gate, with L1 (block-declared resources) marked as planned. Reference [#887](https://github.com/zjzcpj/SciStudio/issues/887) as the impl tracker.
  - **§10 (line 1763)**: Mark `types/` row as "Planned. TypeRegistry currently scans built-ins and `scistudio.types` entry-points only; project-local `types/` filesystem scan is not implemented. See #1332."
  - **§10.5 (lines 1855-1864)**: Similarly mark user-wide `~/.scistudio/types/` scan as planned, referencing #1332.
- Out of scope:
  - All source code under `src/`
  - All tests under `tests/`
  - Other architecture sections beyond §5.3, §6, §10, §10.5
  - ADR-020 or ADR-018 text (no ADR changes needed)
  - Implementing TypeRegistry.add_scan_dir (defer to follow-up issue if owner demand surfaces)
- Required docs:
  - The change IS the docs update — primary artifact.
- Required tests:
  - N/A — docs-only task. Record N/A rationale in gate record `tests` stage. (Implementation-category test requirement does NOT apply to `docs` task-kind per [gated-workflow.md §3.4](docs/ai-developer/specific_rules/gated-workflow.md).)

#### 7.B.2 Dispatch

- [ ] Prompt inline below (`§7.B.5`)
- [x] Correct prompt template selected: `agent-dispatch-prompt-template.md`
- [x] Agent branch/worktree assigned: `docs/issue-1331-1332-arch-drift` at `.claude/worktrees/track-b-arch-drift-docs`
- [x] Write set and out-of-scope paths included in prompt.
- [x] TODO rule included in prompt.
- [x] Required checks included in prompt.

#### 7.B.3 Implementation

- [ ] §5.3 interactive-exception edit → `<artifact>`
- [ ] §6 resource gating clarified, #887 referenced → `<artifact>`
- [ ] §10 + §10.5 `types/` rows marked planned, #1332 referenced → `<artifact>`

#### 7.B.4 Audit

- [ ] Manager review of Track-B diff before merge into umbrella.
- [ ] Audit report path: manager checklist row + Track-B PR commit messages
- [ ] Findings recorded: pending

#### 7.B.5 Integration

- [ ] Track-B PR opened against umbrella branch.
- [ ] Track-B PR CI green.
- [ ] Manager reviewed scope compliance.
- [ ] Track-B merged into umbrella.

## 8. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Ruff (Track A) | `ruff check src/scistudio/engine/ tests/engine/test_collection_wrap.py` | `[ ]` | pending |
| Format (Track A) | `ruff format --check src/scistudio/engine/ tests/engine/test_collection_wrap.py` | `[ ]` | pending |
| Tests (Track A) | `pytest tests/engine/test_collection_wrap.py -v --timeout=60` | `[ ]` | pending |
| Doc lint (Track B) | `python scripts/audit/architecture_drift_check.py` or N/A | `[ ]` | pending |
| Full audit (manager) | `python -m scistudio.qa.audit.full_audit --repo-root . --format json` | `[ ]` | pending |
| Sentrux (manager) | `mcp__plugin_sentrux_sentrux__scan` | `[ ]` | pending |
| Umbrella PR CI green | GitHub Actions on umbrella PR | `[ ]` | pending |

## 9. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-05-21 | manager | None yet | — | — |

## 10. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux evidence when needed, commit, and PR evidence.
- [ ] Umbrella PR closes #1330, #1331, #1332 (with closing keywords).
- [ ] Umbrella PR references #887 with non-closing rationale.
- [ ] CI passed on umbrella PR.
- [ ] Checklist final state matches PR and gate record.
- [ ] Owner notified for `[DO NOT MERGE]` removal.
