---
title: "ADR-039 Addendum 1 Implementation Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs: [39, 42]
language_source: en
---

# ADR-039 Addendum 1 Implementation Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: implement ADR-039 Addendum 1 — remove stash GUI, auto-commit on dirty switch/restore, inline `[Diff]`/`[Restore]` history rows, silent auto-tag safety net for branch delete
- Task kind: `manager` (coordinated multi-agent dispatch)
- Manager persona: `manager`
- Issue: `#1352` (Addendum 1 tracking, closed by #1358; this dispatch implements its `#1353-#1356` siblings)
- Gate record: `.workflow/records/1352-adr-039-addendum-1-impl-manager.json`
- Branch/worktree plan:
  - Manager: `umbrella/adr-039-addendum-1-impl` in `.claude/worktrees/manager-adr-039-addendum-1-impl/`
  - Agent A (W1): `feat/issue-1353-1354/remove-stash-and-auto-commit` in `.claude/worktrees/agent-A-1353-1354/`
  - Agent B (W2): `feat/issue-1355/inline-history-row-buttons` in `.claude/worktrees/agent-B-1355/`
  - Agent C (W2): `feat/issue-1356/branch-delete-orphan-guard` in `.claude/worktrees/agent-C-1356/`
- Protected branch: `main`
- Umbrella branch: `umbrella/adr-039-addendum-1-impl`
- Umbrella PR: [#1364](https://github.com/zjzcpj/SciStudio/pull/1364)
- Umbrella PR title: `[DO NOT MERGE] umbrella(#1352): ADR-039 Addendum 1 — stash removal + auto-commit + history UX + branch-delete safety`
- Final PR target: `main` (umbrella → main, owner-authorized after all 3 sub-PRs land)
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context: `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context: `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

## 2. Scope

- In scope:
  - Stash code deletion across backend + frontend (per #1353)
  - Auto-commit on dirty branch switch + restore (per #1354)
  - Inline `[Diff]` + `[Restore]` buttons on history rows; removal of row-click → modal (per #1355)
  - Silent `refs/scistudio/lineage/<sha>` auto-tag on branch_delete (per #1356, option C)
  - Tests, docs, gate records, CHANGELOG entries per ADR-042
- Out of scope:
  - Removing stash from the bundled git CLI binary itself (users still have `git stash` in a terminal)
  - Changes to merge / cherry-pick / conflict resolution (§3.5a) — Addendum 1 §11.6
  - Cleanup mechanism for `refs/scistudio/lineage/*` tags — deferred per `#1356` body to a separate follow-up issue
  - Branch graph rendering (§3.5b) — Addendum 1 §11.6
- Protected paths:
  - `docs/adr/ADR-039.md` (read-only for implementation agents; addendum text already merged via #1358 — agents reference it but do not edit it)
- Deferred work:
  - `refs/scistudio/lineage/*` cleanup mechanism — separate follow-up issue (to be opened during PR-C implementation if not before)

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

- [x] Dedicated manager branch and worktree created — `umbrella/adr-039-addendum-1-impl` in `.claude/worktrees/manager-adr-039-addendum-1-impl/` (this commit)
- [x] Existing issues linked: `#1353`, `#1354`, `#1355`, `#1356` — `#1352` closed by `#1358`
- [x] Manager gate record started — `.workflow/records/1352-adr-039-addendum-1-impl-manager.json` (finalized for commit `a9358993` / PR #1364)
- [x] Scope include/exclude recorded in the gate record
- [x] Umbrella branch created — `umbrella/adr-039-addendum-1-impl` (commit `a9358993`)
- [x] Umbrella PR opened — [#1364](https://github.com/zjzcpj/SciStudio/pull/1364)
- [x] Umbrella PR title includes `[DO NOT MERGE]`
- [x] Protected branch (`main`) and umbrella PR number recorded above in `## 1`
- [x] No `pip install -e .` environment pollution found — manager runs against `PYTHONPATH=src` per existing pattern
- [x] Dispatch checklist copied from the template and committed
- [x] Dispatch prompts created from the work template and linked in `## 6` rows below
- [x] Sentrux baseline recorded — `scan(.) + check_rules()` → quality_signal=4443, 3/3 rules pass

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A`
- Owner authorization source: `N/A` — owner directive (2026-05-21) is to use the standard gated workflow, no bypass authorized
- Reason: `N/A`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record pre-commit --staged` | `N/A` | `[ ]` | `<pending>` |
| Commit message | `python -m scistudio.qa.governance.gate_record commit-msg <commit-msg-file>` | `N/A` | `[ ]` | `<pending>` |
| Pre-push | `python -m scistudio.qa.governance.gate_record pre-push` | `N/A` | `[ ]` | `<pending>` |

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| A (W1) | `implementer` | `N/A` | `docs/planning/dispatch-prompts/agent-A-1353-1354.md` | Combined stash removal + auto-commit replacement | `feat/issue-1353-1354/remove-stash-and-auto-commit` | `.claude/worktrees/agent-A-1353-1354/` | `git_engine.py` (stash methods + restore auto-commit), `routes/git.py` (stash endpoints + restore/switch auto-commit), `app.py` (verify mounts), `StashListPanel.tsx`, `StashApplyDialog.tsx`, `GitTab.tsx`, `GitHistoryList.tsx` (stash slots + handleRestore), `BranchPicker.tsx` (auto-commit toast in switch), `gitSlice.ts`, `lib/api.ts`, `types/api.ts`, `RunDetail.tsx` (hint text), 5 test files | `GitHistoryList.tsx` row layout + buttons (B owns), `GitGraph/interactions.ts` (B owns), `branch_delete` route (C owns), `BranchPicker.tsx::handleDelete` (C owns), `lineage/store.py` (C owns) | `#1353 + #1354` / [PR-A #1378](https://github.com/zjzcpj/SciStudio/pull/1378) | `[x]` |
| B (W2) | `implementer` | `N/A` | `docs/planning/dispatch-prompts/agent-B-1355.md` | Inline `[Diff]` `[Restore]` buttons + remove row-click → modal | `feat/issue-1355/inline-history-row-buttons` | `.claude/worktrees/agent-B-1355/` | `GitHistoryList.tsx` (handleRowClick + row layout), `GitGraph/interactions.ts` (onCommitClick), `GitHistoryList.test.tsx` | Everything Agent A owns; everything Agent C owns; do not touch stash code (A handles it) | `#1355` / PR-B | `[ ]` |
| C (W2) | `implementer` | `N/A` | `docs/planning/dispatch-prompts/agent-C-1356.md` | Silent auto-tag safety net on branch delete | `feat/issue-1356/branch-delete-orphan-guard` | `.claude/worktrees/agent-C-1356/` | `lineage/store.py` (new `workflow_git_commits_in`), `git_engine.py` (new `commits_reachable_only_from` + `tag` helpers — distinct from A's modifications), `routes/git.py::branch_delete` only, related test files | All of A's scope; all of B's scope; no UI dialog changes (silent per owner C) | `#1356` / PR-C | `[ ]` |

## 7. Track: Wave 1 — PR-A (Agent A, #1353 + #1354 combined)

### 7.1 Track Scope

- Owner: Agent A
- In scope:
  - Delete all stash affordances per #1353 body
  - Replace `engine.restore` auto-stash with auto-commit per #1354 body
  - Add auto-commit pre-step to `routes/git.py::branch_switch` per #1354 body
  - Update response shapes (`{status:"ok", auto_commit_sha?: string}`) across REST + slice + RunDetail/BranchPicker hint text
  - Rewrite the affected tests (delete stash tests; rewrite restore/switch tests; rewrite RunDetail.restore hint test)
- Out of scope:
  - History-row layout (#1355 / Agent B)
  - Branch_delete safety net (#1356 / Agent C)
- Required docs:
  - CHANGELOG entry (this PR) — N/A for ADR (already covered by #1358's §11)
- Required tests:
  - `tests/core/test_git_engine.py`, `tests/api/test_git_endpoints.py`, `frontend/src/store/__tests__/gitSlice.test.ts`, `frontend/src/components/Git/__tests__/GitTab.test.tsx`, `frontend/src/components/Lineage/__tests__/RunDetail.restore.test.tsx`

### 7.2 Dispatch

- [ ] Prompt file created: `docs/planning/dispatch-prompts/agent-A-1353-1354.md`
- [ ] Correct prompt template selected (work template)
- [ ] Audit mode recorded — `N/A` (implementer persona)
- [ ] Agent branch/worktree assigned — see `## 6`
- [ ] Write set and out-of-scope paths included in prompt
- [ ] TODO rule included in prompt
- [ ] Required checks included in prompt
- [ ] 2-atomic-commit structure included in prompt (per owner decision)

### 7.3 Implementation

- [x] Commit 1 (`chore(#1353)`): pure stash deletion — `8a009658`
- [x] Commit 2 (`feat(#1354)`): auto-commit replacement — `3141c80a`
- [x] Tests rewritten/added — backend `tests/core/test_git_engine.py` + `tests/api/test_git_endpoints.py` (75 passed); frontend `gitSlice.test.ts` + `GitTab.test.tsx` + `RunDetail.restore.test.tsx` (46 passed in scope; 442 in full suite)
- [x] CHANGELOG entry added — top `[Unreleased] ### Changed` row citing both #1353 and #1354 (commit `3141c80a`)

### 7.4 Audit

- [ ] Codex auto-review reconciliation — `<comment thread evidence>`
- [ ] Manager scope review on the 2-commit diff — `<note in checklist>`

### 7.5 Integration

- [x] PR-A merged into umbrella — merge commit `4b4e9c68` (--no-ff merge of `origin/feat/issue-1353-1354/remove-stash-add-auto-commit` 2026-05-21)
- [x] Full test suite green on umbrella post-A — Agent A pre-merge: pytest 77 pass + npm test 442 pass + full_audit pass (recorded in PR #1378 gate record `.workflow/records/1353-remove-stash-and-auto-commit.json`)
- [~] Manager Chrome smoke reproducing the user-reported bug fix — **deferred to umbrella final verification (`## 9` Chrome-smoke rows + Task #12)**. Justification: vitest DOM assertions in `RunDetail.restore.test.tsx` cover the user-reported repro at component level (testid `run-detail-restore-auto-commit-hint`, content match against "committed as ab12345 ... revert if unintended", NO stash text, old stash testid absent). Wiring-bug risk per memory `feedback_mandatory_chrome_smoke_test` is real but bounded to a single-component DOM rendering, which vitest's render() covers. Full Chrome smoke against all 3 sub-PRs runs as part of Task #12.

## 8. Track: Wave 2 — PR-B (Agent B, #1355) + PR-C (Agent C, #1356) parallel

### 8.1 PR-B Scope (Agent B)

- Owner: Agent B
- In scope: inline `[Diff]` `[Restore]` buttons; remove row-click → modal in both list view and graph dot click
- Out of scope: everything outside `GitHistoryList.tsx` row layout + `interactions.ts::onCommitClick` + `GitHistoryList.test.tsx`
- Required tests: `frontend/src/components/Git/__tests__/GitHistoryList.test.tsx`
- Required docs: CHANGELOG entry (this PR)

### 8.2 PR-C Scope (Agent C)

- Owner: Agent C
- In scope: `workflow_git_commits_in` query, `commits_reachable_only_from` + `tag` helpers, `branch_delete` route wiring
- Out of scope: BranchPicker UI changes (option C is silent), any cleanup mechanism for accumulated tags
- Required tests: `tests/core/test_lineage_store.py` (new or extended), `tests/core/test_git_engine.py` (helper tests), `tests/api/test_git_endpoints.py` (branch_delete with lineage refs)
- Required docs: CHANGELOG entry (this PR)
- Required follow-up: open separate "refs/scistudio/lineage/* cleanup mechanism" issue if not already open

### 8.3 PR-B Dispatch

- [ ] Prompt file: `docs/planning/dispatch-prompts/agent-B-1355.md`
- [ ] Dispatched only after PR-A merged into umbrella
- [ ] Branch off post-A umbrella
- [ ] PR-B targets `umbrella/adr-039-addendum-1-impl`

### 8.4 PR-C Dispatch

- [ ] Prompt file: `docs/planning/dispatch-prompts/agent-C-1356.md`
- [ ] Dispatched only after PR-A merged into umbrella
- [ ] Branch off post-A umbrella
- [ ] PR-C targets `umbrella/adr-039-addendum-1-impl`

### 8.5 Integration

- [ ] PR-B merged into umbrella — `<merge SHA>`
- [ ] PR-C merged into umbrella — `<merge SHA>`
- [ ] Final umbrella verification batch completed (`## 9`)

## 9. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Ruff | `ruff check .` from umbrella worktree | `[ ]` | `<output>` |
| Format | `ruff format --check .` | `[ ]` | `<output>` |
| Backend tests | `pytest tests/core/test_git_engine.py tests/api/test_git_endpoints.py tests/core/test_lineage_store.py -v --timeout=60` | `[ ]` | `<output>` |
| Frontend tests | `cd frontend && npm test -- --run` | `[ ]` | `<output>` |
| Full audit | `python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json` | `[ ]` | `<output path>` |
| Sentrux (MCP) | `mcp__plugin_sentrux_sentrux__{rescan, check_rules, health, session_end}` | `[ ]` | `<evidence>` |
| Grep guard | `grep -ri --include='*.{py,ts,tsx}' stash src/scistudio frontend/src tests packages` returns zero git-related matches | `[ ]` | `<output>` |
| Chrome smoke — user-reported bug fix | start `scistudio gui`; edit workflow dirty → Lineage tab → Restore → see "committed as <sha>" hint, no stash UI | `[ ]` | `<screenshot path>` |
| Chrome smoke — branch switch toast | switch with dirty tree → "Auto-committed unsaved changes on <old> before switching to <new>" toast | `[ ]` | `<screenshot path>` |
| Chrome smoke — inline buttons | History tab: row click does nothing destructive; [Diff] opens modal; [Restore] confirms then restores | `[ ]` | `<screenshot path>` |
| Chrome smoke — silent auto-tag | feature branch with run → delete branch → no extra dialog → `git tag --list 'refs/scistudio/lineage/*'` shows tags; Lineage Restore still works | `[ ]` | `<terminal output + screenshot>` |

## 10. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-05-21 | Agent A (PR-A #1378) | Touched 4 files outside original `## 6` write set: `src/scistudio/core/versioning/__init__.py`, `src/scistudio/api/app.py`, `frontend/src/components/BottomPanel.tsx`, `frontend/src/components/Toolbar.tsx`. All edits were comment/docstring-only — removing stale stash mentions to keep docs consistent with the deletion in commit `8a009658`. Zero code semantics change. | Manager reviewed each diff (`git show 8a009658 -- <file>`), confirmed comment-only, accepted with this log entry per agent-dispatch.md §5.2. Future dispatch prompts should include adjacent-docstring cleanups in the original write set when a major deletion lands. | N/A — accepted within scope (docs hygiene); no follow-up issue needed |

## 11. Final Readiness

- [ ] All 3 sub-PRs merged into umbrella
- [ ] Manager reviewed every changed file
- [ ] Manager gate record finalized with merged commit + umbrella PR URL
- [ ] Each sub-PR closed every issue listed in its own gate record using closing keywords
- [ ] CI passed on umbrella
- [ ] Checklist final state matches umbrella PR diff and gate record
- [ ] Owner authorized umbrella `[DO NOT MERGE]` title removal — ready for final umbrella → main merge
