# PR-B (#1355) Chrome smoke evidence

- Date: 2026-05-21
- Backend: `python -m scistudio gui --port 8801 --no-browser` from `feat/issue-1355/inline-history-row-buttons` worktree.
- Frontend bundle: `frontend/dist/` produced by `npm run build` (vite v6.4.2) against the same worktree.
- Test project: `smoke-1356` (recent workspace from prior PR-C session); has two commits on `main` (`e5f7840` feature tip + `035df2e` initial).

## Cases executed

| Case | Action | Expected | Observed | Result |
|---|---|---|---|---|
| 1 | List view: click `[data-testid="git-history-row-e5f7840"]` (the `<li>` body) | No `GitDiffModal` opens; row stays focusable. | `modalAfterRowClick=false`, `rowRole=null` (removed), `rowTabIndex=0` (preserved). | PASS |
| 2 | List view: click `[data-testid="git-history-row-diff-e5f7840"]` (new `[Diff]` button) | `GitDiffModal` opens. | After 200ms: `git-diff-modal`, `git-diff-close`, `git-diff-viewer` all present in DOM. | PASS |
| 3 | List view: click `[data-testid="git-history-row-restore-e5f7840"]` (existing `[Restore]` button) | `window.confirm` is called with the restore message; diff modal NOT reopened. | `confirmCalls=["Restore files from commit e5f7840? ..."]`, `modalReopened=false`. | PASS |
| 4 | Graph view: dispatch click on `[data-testid="git-graph-dot-b6274c6"]` (SVG dot) | No `GitDiffModal` opens. | `modalOpenAfterDotClick=false`. | PASS |
| 5 | Graph view: focus `[data-testid="git-graph-scroll"]` and press `Enter` | No `GitDiffModal` opens (previously the Codex #952 path that this PR supersedes). | `modalOpenAfterEnter=false`. | PASS |
| 6 | List view: focus the `<li>` and press `d` hotkey | `GitDiffModal` opens. | `modalAfterDHotkey=true`. | PASS |
| 7 | List view: focus the `<li>` and press `r` hotkey | `window.confirm` called once. | `confirmAfterRHotkey=true`. | PASS |

## Visible UI

`docs/audit/1355-chrome-smoke-list-view.png` — full-screen capture with the
Git tab in List view showing the new inline `Diff` and `Restore this version`
buttons on both commit rows. No modal is open in the screenshot (row-click
test was the most recent interaction).

## What was NOT exercised

- Multi-row navigation in graph view with arrow keys — no behavior change in
  scope; only Enter/Space were changed for #1355.
- Diff modal close path (already covered by `GitDiffModal` tests in the
  vitest suite).
