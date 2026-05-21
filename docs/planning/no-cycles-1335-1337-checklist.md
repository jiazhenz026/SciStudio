---
title: "No-Cycles Umbrella (#1335 + #1337) Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
language_source: en
---

# No-Cycles Umbrella (#1335 + #1337) Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: `Fix circular-import #1335 + #1337 in an umbrella; leave #1336 open at P0.`
- Task kind: `manager`
- Manager persona: `manager`
- Issue: `#1335` (primary, in gate record) + `#1337` (closed by umbrella PR body)
- Gate record: `.workflow/records/1335-1337-no-cycles-umbrella.json`
- Branch/worktree plan:
  - Manager: branch `track/no-cycles-1335-1337`, worktree `.claude/worktrees/manager-no-cycles`
  - Agents: branch pattern `fix/<issue>-<scope>`, worktree pattern `.claude/worktrees/fix-<issue>`
- Protected branch: `main`
- Umbrella branch: `track/no-cycles-1335-1337`
- Umbrella PR: `#<pending>`
- Umbrella PR title: `[DO NOT MERGE] fix(#1335,#1337): break circular imports (5 → 2 sentrux clusters)`
- Final PR target: `main` (manager merges umbrella → main only on explicit owner authorization)
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

## 2. Scope

- In scope (umbrella):
  - `.sentrux/rules.toml` — ratchet `max_cycles` 5 → 2 in umbrella merge commit
  - `docs/planning/no-cycles-1335-1337-checklist.md` — this file
  - `.workflow/records/1335-1337-no-cycles-umbrella.json` — manager gate record
  - `docs/audit/2026-05-21-no-cycles-umbrella-sentrux.json` — sentrux baseline + post evidence
- Out of scope:
  - `#1336` — stays OPEN at P0; do not touch `blocks/registry.py`, `ai/agent/mcp/*`, `blocks/ai/ai_block.py`, etc.
  - `pyproject.toml` `import-linter` contracts — `no_cycles` deferred to #1341 (blocked-by #1336)
  - Entry-point migration for backends (#1335 Option C) — out of scope; tracked at #1342
  - Removing the 17 pre-existing lazy-import bandaids — separate cleanup, not this umbrella
- Protected paths:
  - `.github/workflows/*` — no CI changes in this umbrella
  - `pyproject.toml` — left untouched
- Deferred work:
  - `TODO(#1342)` comment at the lazy import in `backend_router.get_router` — set by Track B agent
  - `#1341` — `no_cycles` import-linter contract (blocked-by #1336)
  - `#1342` — eliminate the lazy import added by Track B (path a or path b)

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

- [x] Dedicated manager branch and worktree created. → `.claude/worktrees/manager-no-cycles` on `track/no-cycles-1335-1337`
- [x] Existing issues linked, or new issues created only if none exist. → #1335 (existing), #1337 (existing), #1341 (new — `no_cycles` follow-up), #1342 (new — lazy-import tech debt)
- [x] Gate record started. → `.workflow/records/1335-1337-no-cycles-umbrella.json`
- [x] Scope include/exclude recorded in the gate record. → plan + amend stages done
- [x] Umbrella branch created. → `track/no-cycles-1335-1337` off `origin/main` (814141b6)
- [ ] Umbrella PR opened. → pending push of gate record + checklist
- [ ] Umbrella PR title includes `[DO NOT MERGE]`. → pending
- [x] Protected branch and umbrella PR number recorded in this checklist. → `main` / `#<pending>`
- [x] No `pip install -e .` environment pollution found. → manager uses `PYTHONPATH=src python -m …`; agents instructed similarly
- [ ] Dispatch checklist copied from the template and committed. → committing now
- [ ] Dispatch prompts created from the correct prompt template and linked below. → pending Track A + Track B dispatch
- [x] Sentrux baseline recorded. → `docs/audit/2026-05-21-no-cycles-umbrella-sentrux.json` + gate record `sentrux` block

### 4.1 Housekeeping on #1336 (P1 → P0)

- [x] P0 label verified to exist (`#B60205`, "Critical — system unusable"). → `gh label list`
- [x] `gh issue edit 1336 --remove-label P1 --add-label P0`. → https://github.com/zjzcpj/SciStudio/issues/1336
- [x] Rationale comment posted on #1336. → https://github.com/zjzcpj/SciStudio/issues/1336#issuecomment-4506128278
- [x] Cross-link to #1341 (`no_cycles` follow-up) posted on #1336. → https://github.com/zjzcpj/SciStudio/issues/1336#issuecomment-4506131388

### 4.2 Follow-up issues opened

- [x] `#1341` — Add `no_cycles` import-linter contract once #1336 lands (audit-followup, architecture, P3)
- [x] `#1342` — Eliminate lazy import in `core.storage.backend_router.get_router` (tech-debt, audit-followup, architecture, P3)

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `admin-approved:ai-override`
- Owner authorization source: chat on 2026-05-21 — owner selected "Authorize admin-approved:ai-override for this one umbrella setup push (Recommended)" in response to manager AskUserQuestion about chicken-and-egg umbrella push validation.
- Reason: ADR-042 `pre-push` and `pr-ready` validators require all 6 stages done + full_audit evidence (`require_final_evidence=True`); the umbrella's `commit_and_submit_pr` stage cannot complete before the PR exists. Bypass is scoped to TWO commands ONLY: the initial `git push -u origin track/no-cycles-1335-1337` and the initial `gh pr create` that opens the `[DO NOT MERGE]` umbrella PR. All subsequent commits/pushes (agent PRs, ratchet merge, finalize) use the standard non-bypass workflow.
- Scope of bypass: initial umbrella setup ONLY. Agent PRs (Track A `#1337`, Track B `#1335`) must NOT use this bypass label; they are normal implementer PRs with full gate evidence at PR open time.
- PR label applied: `admin-approved:ai-override` on the umbrella PR (so CI's gate validator recognizes the bypass).

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit (preflight commit) | `python -m scistudio.qa.governance.gate_record pre-commit --staged` | N/A — passed clean | `[x]` | `gate_record: pass` |
| Commit message (preflight commit) | `python -m scistudio.qa.governance.gate_record commit-msg <commit-msg-file>` | N/A | `[x]` | commit `36bac1d3` accepted |
| Pre-push (initial umbrella setup) | `SCISTUDIO_GATE_BYPASS_LABELS=admin-approved:ai-override git push -u origin track/no-cycles-1335-1337` | `admin-approved:ai-override` (chat-authorized, this push only) | `[ ]` | `<push output>` |
| Pre-PR (initial umbrella PR open) | `SCISTUDIO_GATE_BYPASS_LABELS=admin-approved:ai-override gh pr create ... --label admin-approved:ai-override` | `admin-approved:ai-override` (chat-authorized, this PR only) | `[ ]` | `<PR URL>` |
| All later commits/pushes (agent PRs, ratchet merge, finalize) | normal gate hooks | N/A | `[ ]` | `<runs without bypass>` |

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| `A-1337` | `implementer` | `N/A` | `docs/planning/dispatch-prompts/fix-1337-pair-cycles.md` | Break git_binary↔git_engine + platform↔process_handle pairs via shared-types extractions (`errors.py`, `exit_info.py`; brief said `_common.py` — see gate-record amendment) | `fix/1337-pair-cycles` | `.claude/worktrees/fix-1337` | `core/versioning/errors.py` (new), `core/versioning/git_binary.py`, `core/versioning/git_engine.py`, `engine/runners/exit_info.py` (new), `engine/runners/platform.py`, `engine/runners/process_handle.py`, `tests/core/test_git_engine.py`, `tests/engine/test_process_handle.py`, `docs/adr/ADR-039.md`, `docs/adr/ADR-019.md` (governs.contracts), own gate record | `.sentrux/rules.toml`, `pyproject.toml`, `core/types/`, `core/storage/`, `blocks/`, `ai/`, `frontend/` | `#1337` / `#<pending>` | `[~]` |
| `A-1335` | `implementer` | `N/A` | `docs/planning/dispatch-prompts/fix-1335-router-defaults.md` | Extract `core/storage/_defaults.py` to break core.types ↔ backend_router cycle; insert `TODO(#1342)` at lazy-import site | `fix/1335-router-defaults` | `.claude/worktrees/fix-1335` | `core/storage/_defaults.py` (new), `core/storage/backend_router.py`, `core/storage/__init__.py` (only if needed), `tests/core/test_backend_router.py`, own gate record | `core/types/*.py`, `tests/blocks/test_auto_flush_composite.py`, `.sentrux/rules.toml`, `pyproject.toml`, `core/versioning/`, `engine/runners/`, `blocks/`, `ai/`, `frontend/` | `#1335` / `#<pending>` | `[ ]` |

## 7. Track A — Fix #1337 (pair D + pair E)

### 7.1 Track Scope

- Owner: `A-1337` implementer agent
- In scope:
  - Pair D — `core/versioning/git_binary.py` ↔ `core/versioning/git_engine.py` cycle (lazy `GitError` import + lazy `GitBinary` import)
  - Pair E — `engine/runners/platform.py` ↔ `engine/runners/process_handle.py` cycle (TYPE_CHECKING + 6 lazy `ProcessExitInfo` imports + module-top `PlatformOps` import)
- Out of scope:
  - `core/types/`, `core/storage/`, `blocks/`, `ai/`, `frontend/`
  - `.sentrux/rules.toml` (manager handles ratchet)
  - `pyproject.toml` (`no_cycles` contract deferred to #1341)
- Required docs:
  - `_common.py` docstrings cite governing ADR (ADR-039 for git, ADR-019 for runners — agent verifies)
  - No spec/ADR change required (surgical refactor, public API preserved)
- Required tests:
  - `tests/core/test_git_engine.py::test_no_circular_import` (new, regression)
  - `tests/engine/test_process_handle.py::test_no_circular_import` (new, regression)
  - All existing tests in `tests/core/test_git_engine.py`, `tests/engine/test_*.py`, `tests/api/test_workflow_run_git.py`, `tests/blocks/test_tier1_dropin_subprocess.py` must pass unchanged.

### 7.2 Dispatch

- [x] Prompt file created at `docs/planning/dispatch-prompts/fix-1337-pair-cycles.md`. → committed by manager preflight
- [x] Correct prompt template selected (`agent-dispatch-prompt-template.md`). → verified at top of dispatch prompt
- [x] Audit mode recorded when persona is `audit_reviewer`. → N/A (implementer)
- [x] Agent branch/worktree assigned. → `fix/1337-pair-cycles` / `.claude/worktrees/fix-1337`
- [x] Write set and out-of-scope paths included in prompt. → §Scope section of prompt
- [x] TODO rule included in prompt. → §TODO And Deferral Rule of prompt
- [x] Required checks included in prompt. → §Required Tests And Checks of prompt

### 7.3 Implementation

- [x] Create `src/scistudio/core/versioning/errors.py` with `GitError`. (Brief said `_common.py`; renamed to public `errors.py` so griffe-based audit fact resolution picks up the symbol — gate record amended with rationale.) → see commit on `fix/1337-pair-cycles`
- [x] `git_engine.py`: replace `class GitError` with `from .errors import GitError`; convert lazy `from .git_binary import GitBinary` (line ~91) to module-top. → see commit
- [x] `git_binary.py`: replace lazy `from .git_engine import GitError` (line ~156) with module-top `from .errors import GitError`. → see commit
- [x] `core/versioning/__init__.py`: verify `GitError` re-export still resolves. → existing re-export `from scistudio.core.versioning.git_engine import GitEngine, GitError` unchanged; runtime smoke test in regression `test_no_circular_import` confirms `git_engine.GitError.__module__ == "scistudio.core.versioning.errors"` and `__init__.GitError` is the same object.
- [x] Create `src/scistudio/engine/runners/exit_info.py` with `ProcessExitInfo`. (Brief said `_common.py`; renamed to public `exit_info.py` for same audit-fact reason.) → see commit
- [x] `process_handle.py`: replace `ProcessExitInfo` definition with import from `exit_info`; keep `from .platform import PlatformOps, get_platform_ops`. → see commit
- [x] `platform.py`: delete TYPE_CHECKING import (line ~19) + 6 lazy imports (lines ~88,147,197,268,315,355); add single module-top `from .exit_info import ProcessExitInfo`. → see commit
- [x] `engine/runners/__init__.py`: verify `ProcessExitInfo` re-export still resolves. → existing re-export `from scistudio.engine.runners.process_handle import ProcessExitInfo` unchanged; runtime smoke test in regression `test_no_circular_import` confirms `ProcessExitInfo.__module__ == "scistudio.engine.runners.exit_info"` and `engine.runners.ProcessExitInfo` is the same object.
- [x] Add `test_no_circular_import` regression test in each pair. → `tests/core/test_git_engine.py::test_no_circular_import` + `tests/engine/test_process_handle.py::test_no_circular_import`
- [x] Run targeted pytest + ruff + sentrux MCP rescan locally; expected `clusters` drops to 3. → 434 passed / 5 skipped / 8 xfailed; sentrux clusters: 5 → 3 (Pair D + Pair E gone); evidence in `.workflow/records/1337-pair-cycles-sentrux.json`
- [x] Update ADR-039 `governs.contracts` and ADR-019 `governs.contracts` (+ ADR-019 `governs.files`) to point at the new canonical contract locations (`errors.GitError`, `exit_info.ProcessExitInfo`). Required for `doc_drift.phantom-contract`, `closure.unresolved-contract-claim`, `signature_drift.missing-symbol` to pass — gate record amended with rationale. → see commit

### 7.4 Audit

- [ ] Audit agent assigned, or manager audit completed. → `<manager audit>`
- [ ] Audit report file path assigned. → `docs/audit/2026-05-21-track-a-1337-audit.md`
- [ ] Audit report committed.
- [ ] Audit report merged into final PR evidence path.
- [ ] Findings recorded.
- [ ] P1 findings fixed before integration.
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale.

### 7.5 Integration

- [ ] Agent output reviewed by manager.
- [ ] Scope compliance verified (no files outside write set touched).
- [ ] Conflicts resolved intentionally.
- [ ] Track merged or integrated into umbrella branch. → `<merge commit>`

## 8. Track B — Fix #1335 (core.types ↔ backend_router)

### 8.1 Track Scope

- Owner: `A-1335` implementer agent
- In scope:
  - Extract `_build_default_router()` from `backend_router.py` into a new `core/storage/_defaults.py`
  - Rewrite `get_router()` in `backend_router.py` as a lazy-singleton accessor that lazy-imports `_defaults.build_default` inside the function body
  - Insert `TODO(#1342)` comment at the lazy import (issue body for #1342 spells out the resolution paths)
- Out of scope:
  - `core/types/*.py` — Track B MUST NOT touch any types module
  - `tests/blocks/test_auto_flush_composite.py` — monkeypatch must keep working unchanged
  - `core/versioning/`, `engine/runners/`, `blocks/`, `ai/`, `frontend/`
  - `.sentrux/rules.toml`, `pyproject.toml`
- Required docs:
  - `_defaults.py` docstring cites governing ADR (ADR-031 for storage — agent verifies)
  - No spec/ADR change required (surgical refactor, public API preserved)
- Required tests:
  - `tests/core/test_backend_router.py::test_no_circular_import` (new, regression)
  - `tests/core/test_backend_router.py::test_singleton_identity` (new, regression for lazy singleton)
  - All existing `tests/core/test_backend_router.py` + `tests/blocks/test_auto_flush_composite.py` must pass unchanged.

### 8.2 Dispatch

- [ ] Prompt file created at `docs/planning/dispatch-prompts/fix-1335-router-defaults.md`.
- [ ] Correct prompt template selected (`agent-dispatch-prompt-template.md`).
- [ ] Audit mode recorded when persona is `audit_reviewer`. → N/A (implementer)
- [ ] Agent branch/worktree assigned. → `fix/1335-router-defaults` / `.claude/worktrees/fix-1335`
- [ ] Write set and out-of-scope paths included in prompt.
- [ ] TODO rule included in prompt (`TODO(#1342)` at lazy-import site).
- [ ] Required checks included in prompt.

### 8.3 Implementation

- [ ] Create `src/scistudio/core/storage/_defaults.py` with `build_default()` (moves body of `_build_default_router()`). → `<commit>`
- [ ] `backend_router.py`: delete `_build_default_router()` + 6 lazy type imports (lines 53-78); rewrite `get_router()` as lazy-singleton + add `TODO(#1342)` comment. → `<commit>`
- [ ] `core/storage/__init__.py`: verify `get_router` re-export still works. → `<commit>`
- [ ] Add `test_no_circular_import` + `test_singleton_identity` regression tests. → `<commit>`
- [ ] Run targeted pytest + ruff + sentrux MCP rescan locally; expected `clusters` drops to 4 (after this fix alone) or 2 (after Track A also lands). → `<output>`

### 8.4 Audit

- [ ] Audit agent assigned, or manager audit completed. → `<manager audit>`
- [ ] Audit report file path assigned. → `docs/audit/2026-05-21-track-b-1335-audit.md`
- [ ] Audit report committed.
- [ ] Audit report merged into final PR evidence path.
- [ ] Findings recorded.
- [ ] P1 findings fixed before integration.
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale.
- [ ] **R1 verified**: `backend_router.py` has no module-top edge to `_defaults` or `core.types.*` (re-running `scripts/find_cycles.py` confirms this SCC is gone).
- [ ] **R2 verified**: `tests/blocks/test_auto_flush_composite.py` runs unchanged (monkeypatch target still resolves).

### 8.5 Integration

- [ ] Agent output reviewed by manager.
- [ ] Scope compliance verified (no `core/types/*.py` files touched).
- [ ] Conflicts resolved intentionally.
- [ ] Track merged or integrated into umbrella branch. → `<merge commit>`

## 9. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| `<YYYY-MM-DD>` | `<agent>` | `<what drifted>` | `<manager action>` | `<issue/TODO/N/A>` |

## 10. Verification Evidence (umbrella, post-integration)

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Ruff | `ruff check .` | `[ ]` | `<output path or summary>` |
| Format | `ruff format --check .` | `[ ]` | `<output path or summary>` |
| Tests | `pytest tests/core/ tests/engine/ tests/blocks/test_auto_flush_composite.py tests/api/test_workflow_run_git.py --timeout=60` | `[ ]` | `<output path or summary>` |
| Full audit | `python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json` | `[ ]` | `docs/audit/full-audit-latest.json` |
| Sentrux MCP | `mcp__plugin_sentrux_sentrux__rescan / dsm / health / session_end` | `[ ]` | `docs/audit/2026-05-21-no-cycles-umbrella-sentrux.json` (after_state field) |
| Cycle script | `python scripts/find_cycles.py` (from main worktree; expected: 2 SCCs both inside #1336) | `[ ]` | `<output snippet>` |
| Cold-import probe | `cd src && python -c "import time, importlib, sys; …"` (compare against baseline) | `[ ]` | `<timings in umbrella PR body>` |
| Public-symbol smoke | `python -c "from scistudio.core.versioning.git_engine import GitError; from scistudio.core.storage.backend_router import get_router; from scistudio.engine.runners.process_handle import ProcessExitInfo; print('ok')"` | `[ ]` | `<output>` |
| End-to-end | `docs/ai-developer/skills/scistudio-e2e-test/` checkpoint + git versioning + subprocess block scenario | `[ ]` | `<screenshot or scenario log>` |

## 11. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux evidence, commit, and PR evidence.
- [ ] PR closes every issue fixed by the dispatch (`Closes #1335`, `Closes #1337`).
- [ ] Cross-links to #1341 (`no_cycles` follow-up) and #1342 (lazy-import tech debt) in PR body (do NOT close).
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
- [ ] Owner authorized removing `[DO NOT MERGE]` from umbrella PR title before final merge. → `<chat link or comment>`
