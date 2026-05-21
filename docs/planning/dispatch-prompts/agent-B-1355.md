[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: implement ADR-039 Addendum 1 §11.3 (history-row click change) — remove the row-click → modal shortcut from list view and graph dot click; add explicit inline `[Diff]` button beside the existing `[Restore]` button on every history row.
- Task kind: feature
- Persona: implementer
- Issue: #1355
- Issue URL: https://github.com/zjzcpj/SciStudio/issues/1355
- Umbrella PR: [#1364](https://github.com/zjzcpj/SciStudio/pull/1364) `[DO NOT MERGE]` — target your sub-PR at the `umbrella/adr-039-addendum-1-impl` branch, NOT main
- Protected branch: main
- Umbrella branch: umbrella/adr-039-addendum-1-impl (note: rebase your branch onto the POST-PR-A umbrella before working)
- Agent branch: feat/issue-1355/inline-history-row-buttons
- Agent worktree: `.claude/worktrees/agent-B-1355/`
- Gate record: `.workflow/records/1355-inline-history-row-buttons.json`
- Checklist: `docs/planning/adr-039-addendum-1-impl-checklist.md` (edit only your own rows in `## 6` Agent B and `## 8.1` / `## 8.3`)

## Required Rules

Read and follow:

- The GitHub issue `#1355` and all owner instructions in it.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md
- docs/adr/ADR-039.md §11.3 (history click row) and §3.5b (graph rendering)

## Scope

You own ONLY these files:

**Frontend:**
- `frontend/src/components/Git/GitHistoryList.tsx`:
  - `handleRowClick` (around line 72-92) — DELETE its destructive side effect; the row click should NOT open `GitDiffModal`. The function can stay as a focus-only handler or be removed entirely if not used.
  - `onClick={() => handleRowClick(commit)}` on the row `<li>` (line 262) — remove or repurpose.
  - Row layout in the list (lines 247-310): ADD a `<button>` for `[Diff]` next to the existing `[Restore]` button (lines 295-306). Wire the Diff button to the same logic that previously opened the modal from row click (i.e. compute parent SHA + setDiffOpen). Make both buttons keyboard accessible (Tab + Enter); stop event propagation so they don't double-fire row-level handlers.
  - `onKeyDown` (line 121-132): keep `r` hotkey for restore. Optionally add `d` hotkey for diff (nice-to-have).
- `frontend/src/components/Git/GitGraph/interactions.ts`:
  - `onCommitClick` (lines 121-128): replace direct `onOpenDiff?.(sha)` with a focus-and-scroll-to-list behavior — call `setFocusedRow(idx)` and scroll the corresponding list row into view. Do NOT open the diff modal directly. Users get the inline buttons from the list view (`GitHistoryList.tsx::GitGraphPane` will need a small tweak to surface the buttons when in graph mode too — keep it minimal; the cleanest approach is to show a floating action chip OR scroll-and-focus the corresponding list row when graph mode shows a synced list/graph split).
  - If you choose the floating-chip design, keep the implementation compact (≤80 LOC).

**Tests:**
- `frontend/src/components/Git/__tests__/GitHistoryList.test.tsx`:
  - DELETE row-click → modal tests.
  - ADD: `[Diff]` button click opens `GitDiffModal`; `[Restore]` button still works; row click does NOT open the modal; both buttons reachable via keyboard.

**Docs:**
- `CHANGELOG.md` — add entry under `[Unreleased]` `### Changed` citing #1355.

You must NOT touch:

- Any file in Agent A's write set (stash code, auto-commit replacement, RunDetail.tsx hint text)
- Any file in Agent C's write set (`lineage/store.py`, `commits_reachable_only_from`/`tag` helpers, `branch_delete` route, `BranchPicker.tsx::handleDelete`)
- `docs/adr/ADR-039.md` (read-only)

If you need an out-of-scope path, stop and report back.

## Coordination

- You are not alone. Agent C runs in parallel on a disjoint file set; do not let your changes touch C's files.
- MUST work only on `feat/issue-1355/inline-history-row-buttons`.
- MUST work only in `.claude/worktrees/agent-B-1355/`.
- MUST NOT use `pip install -e .`.
- MUST target your PR to `umbrella/adr-039-addendum-1-impl`, NOT `main`.
- MUST NOT merge.
- Edit only your checklist rows.

## TODO And Deferral Rule

Deferred work must be tracked in the repo. Use `TODO(#NNN): <reason>` and cite an issue, ADR, spec, or follow-up ticket.

Known deferred items: the `d` hotkey for diff is nice-to-have; ship without if it costs you. If you defer, add `# TODO(#1355): d-key hotkey deferred to follow-up` in a code comment.

## Work To Do

1. Create your worktree off the post-PR-A umbrella: `git worktree add -b feat/issue-1355/inline-history-row-buttons .claude/worktrees/agent-B-1355 umbrella/adr-039-addendum-1-impl` (this assumes the manager has already merged PR-A; verify `git log umbrella/adr-039-addendum-1-impl --oneline | head` shows the PR-A merge commit before you start).
2. Start gate record: `python -m scistudio.qa.governance.gate_record start --task-kind feature --issue 1355 --slug inline-history-row-buttons --branch feat/issue-1355/inline-history-row-buttons --owner-directive "..." --include <list>`.
3. Read #1355 in full + ADR-039 §11.3.
4. Implement the changes per the write set.
5. Run the required checks.
6. Single commit (no 2-commit requirement on this PR).
7. Push and open PR via `scripts/scistudio_pr_create.py`. Body MUST include `Closes #1355`.
8. Finalize gate record.
9. Wait for CI green + Codex review.
10. Edit your checklist rows.
11. Report back.

## Required Tests And Checks

- `ruff check .` from agent worktree
- `pytest <relevant tests if any>` (mostly frontend-only PR; backend tests likely N/A)
- `cd frontend && npm test -- --run src/components/Git/__tests__/GitHistoryList.test.tsx`
- `python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json`
- Sentrux MCP scan + check_rules + health + session_end
- Chrome smoke (MANDATORY): start `scistudio gui`; open the Git tab; in list view, click a row → confirm no modal opens; click `[Diff]` on a row → modal opens; click `[Restore]` on a row → confirm dialog opens. In graph view, click a dot → confirm no modal opens directly. Save screenshot.

## Output Required

Before reporting done, provide:

- Changed file paths
- Commit SHA(s)
- Test/check output paths
- Sentrux delta
- Chrome smoke screenshot
- Checklist rows updated
- PR URL
- Any blocker

## Stop Conditions

Stop and report back if:

- The umbrella branch does NOT yet contain PR-A's merge commit — manager has not finished W1. Wait for manager signal.
- You need an out-of-scope file.
- CI or local checks fail unclearly.
- The floating-chip vs scroll-and-focus design choice for graph dot click feels wrong — propose both and let manager decide.
