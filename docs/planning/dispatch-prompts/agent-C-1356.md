[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: implement ADR-039 Addendum 1 §11.4 line for #1356 — silent auto-tag safety net on branch delete (option C, owner-decided 2026-05-21). Before deleting a branch whose tip commits are referenced by `runs.workflow_git_commit`, SciStudio silently creates `refs/scistudio/lineage/<sha>` per orphaned commit, then proceeds with the delete. No user-visible dialog change.
- Task kind: bugfix
- Persona: implementer
- Issue: #1356
- Issue URL: https://github.com/zjzcpj/SciStudio/issues/1356
- Umbrella PR: #<pending — see checklist `## 1`> `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: umbrella/adr-039-addendum-1-impl (rebase onto post-PR-A umbrella)
- Agent branch: feat/issue-1356/branch-delete-orphan-guard
- Agent worktree: `.claude/worktrees/agent-C-1356/`
- Gate record: `.workflow/records/1356-branch-delete-orphan-guard.json`
- Checklist: `docs/planning/adr-039-addendum-1-impl-checklist.md` (edit only `## 6` Agent C and `## 8.2` / `## 8.4`)

## Required Rules

Read and follow:

- The GitHub issue `#1356` and all owner instructions in it. The decision is **option C auto-tag silent safety net** — no warn/confirm dialog.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/bug-fix.md
- docs/ai-developer/personas/implementer.md
- docs/adr/ADR-039.md §11.4 row for #1356 and §11.6 (out-of-scope clarifications)

## Scope

You own ONLY these files:

**Backend:**
- `src/scistudio/core/lineage/store.py` — ADD method `workflow_git_commits_in(sha_list: list[str]) -> set[str]`. Single SQL `SELECT DISTINCT workflow_git_commit FROM runs WHERE workflow_git_commit IN (...)`. Handle empty input (return empty set without a SQL call).
- `src/scistudio/core/versioning/git_engine.py` — ADD method `commits_reachable_only_from(branch: str) -> list[str]` after line 507 (after `branch_delete`). Use `git rev-list <branch> --not <all-other-refs>`. Also ADD method `tag(name: str, target_sha: str, force: bool = False) -> None` using `git update-ref refs/scistudio/lineage/<sha> <sha>` (idempotent — `update-ref` overwrites, so re-running is safe). DO NOT touch any existing method that Agent A modified — your additions go in a new region of the file.
- `src/scistudio/api/routes/git.py::branch_delete` (lines 374-382 — verify after PR-A merge) — wrap the existing call:
  ```python
  orphan_candidates = engine.commits_reachable_only_from(name)
  if orphan_candidates:
      referenced = lineage_store.workflow_git_commits_in(list(orphan_candidates))
      for sha in referenced:
          engine.tag(f"refs/scistudio/lineage/{sha}", sha)
  engine.branch_delete(name, force=force)
  ```
  The endpoint needs access to `lineage_store` — read how `runtime.lineage_store` is exposed in `request.app.state.runtime`.

**Tests (REQUIRED):**
- `tests/core/test_lineage_store.py` (new file OR extend existing) — `workflow_git_commits_in` returns intersection of input SHAs and DB SHAs; empty input → empty set; SHAs absent in DB are filtered out.
- `tests/core/test_git_engine.py` — ADD tests for `commits_reachable_only_from` (fixture: A-B-C on main, A-B-D on feature; feature deletion candidate = [D] only). ADD tests for `tag` (idempotent, ref appears under `refs/scistudio/lineage/`).
- `tests/api/test_git_endpoints.py` — REWRITE `test_branch_delete_endpoint` to cover the new flow: a feature branch with a lineage-referenced tip → tag created → branch deleted → tag still resolves SHA after delete. Add a negative-case test: clean delete (no lineage reference) leaves no `refs/scistudio/lineage/*` tags.

**Docs:**
- `CHANGELOG.md` — entry under `[Unreleased]` `### Fixed` citing #1356.

**Follow-up issue (REQUIRED if not already open):**
- Open or verify-existence-of a tracking issue for `refs/scistudio/lineage/*` cleanup mechanism (the deferred item per #1356 body). Cite it as a TODO in the new code:
  ```python
  # TODO(#NNNN): cleanup mechanism for accumulated refs/scistudio/lineage/* tags
  #   Out of scope per ADR-039 §11.4 row #1356.
  #   Followup: <issue URL>
  ```

You must NOT touch:

- Any file in Agent A's write set (stash code, auto-commit replacement, RunDetail.tsx hint)
- Any file in Agent B's write set (GitHistoryList row layout, GitGraph interactions)
- `frontend/src/components/Git/BranchPicker.tsx::handleDelete` — option C is silent; the existing `window.confirm` stays unchanged
- `docs/adr/ADR-039.md` (read-only)

If you need an out-of-scope path, stop and report back.

## Coordination

- You are not alone. Agent B runs in parallel on a disjoint file set.
- MUST work only on `feat/issue-1356/branch-delete-orphan-guard`.
- MUST work only in `.claude/worktrees/agent-C-1356/`.
- MUST NOT use `pip install -e .`.
- MUST target your PR to `umbrella/adr-039-addendum-1-impl`, NOT `main`.
- MUST NOT merge.
- Edit only your checklist rows.

## TODO And Deferral Rule

Deferred work must be tracked in the repo. Use `TODO(#NNN): <reason>` and cite an issue, ADR, spec, or follow-up ticket.

Known deferred items: cleanup mechanism for `refs/scistudio/lineage/*` accumulation — open a separate issue, cite it in a TODO comment in your new code, and reference it in the CHANGELOG entry.

## Work To Do

1. Create worktree off post-PR-A umbrella: `git worktree add -b feat/issue-1356/branch-delete-orphan-guard .claude/worktrees/agent-C-1356 umbrella/adr-039-addendum-1-impl`.
2. Start gate record.
3. Read #1356 in full + ADR-039 §11.4 row for #1356.
4. Open the cleanup-mechanism follow-up issue first (so you can cite the real number in your TODO comment).
5. Implement the changes per the write set.
6. Run required checks.
7. Single commit.
8. Push and open PR via `scripts/scistudio_pr_create.py`. Body MUST include `Closes #1356`.
9. Finalize gate record.
10. Wait for CI green + Codex review.
11. Edit your checklist rows.
12. Report back.

## Required Tests And Checks

- `ruff check .`
- `ruff format --check .`
- `pytest tests/core/test_lineage_store.py tests/core/test_git_engine.py tests/api/test_git_endpoints.py -v --timeout=60`
- `python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json`
- Sentrux MCP scan + check_rules + health + session_end
- Chrome smoke (MANDATORY): start `scistudio gui`; create a project; create a feature branch; run a workflow on it; switch back to main; click the trash icon on the feature branch in BranchPicker; confirm:
  - The existing `window.confirm` dialog appears (NOT a new dialog).
  - After confirming, the branch disappears from BranchPicker.
  - In a terminal in the project root: `git tag --list 'refs/scistudio/lineage/*'` shows a tag for the orphaned SHA.
  - Open Lineage tab; click "Restore this run's workflow" on the run from the deleted branch; it still succeeds.

## Output Required

Before reporting done, provide:

- Changed file paths
- Commit SHA(s)
- New tracking issue number for the cleanup mechanism follow-up
- Test/check output paths
- Sentrux delta
- Chrome smoke screenshots + `git tag --list` terminal output
- Checklist rows updated
- PR URL
- Any blocker

## Stop Conditions

Stop and report back if:

- The umbrella branch does NOT yet contain PR-A's merge commit — manager has not finished W1. Wait.
- You need an out-of-scope file (especially BranchPicker.tsx::handleDelete — silent per option C).
- CI or local checks fail unclearly.
- `lineage_store` is not accessible from `routes/git.py` via `request.app.state.runtime.lineage_store` — propose how to inject it before implementing.
- `git update-ref` semantics for `refs/scistudio/lineage/*` cause unexpected interactions with the branch graph rendering (§3.5b) — these refs should be filtered out of branch listings; if they aren't, surface that as a separate finding.
