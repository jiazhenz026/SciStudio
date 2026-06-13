---
title: "ADR-048 PR1577 Final Blocker Fix Checklist"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs:
  - 48
language_source: en
---

# ADR-048 PR1577 Final Blocker Fix Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: Fix all final ADR-048 PR #1577 blockers and submit a repair PR.
- Task kind: `bugfix`
- Manager persona: `manager`
- Issue: `#1644`, with closures for `#1623` and `#1594` if fixed.
- Gate record: `.workflow/records/1644-pr1577-adr048-final-blockers.json`
- Branch/worktree plan:
  `fix/pr1577-adr048-final-blockers` at
  `C:/Users/jiazh/Desktop/workspace/sci-wt/fix-pr1577-adr048-blockers`
- Protected branch: `main`
- Integration target branch: `track/adr-048-spec1-preview-system` (PR #1577)
- Final PR target: `track/adr-048-spec1-preview-system`
- Final PR: https://github.com/zjzcpj/SciStudio/pull/1645
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`

## 2. Scope

- In scope:
  - Plot job reachability from public user/AI paths to `PreviewHost` and
    `PlotPreviewer`.
  - MCP inspection preview no-compat cleanup or explicit ADR/spec narrowing.
  - Installed-package `scistudio.previewers` entry point discovery.
  - ADR-048 final viewer e2e scenario/evidence.
  - Stale claim/docs cleanup for #1623, #1592, `PlotPreviewPanel`, and compat
    language.
- Out of scope:
  - Merging PR #1577 or this fix PR.
  - Broad UI redesign outside the minimal plot affordance required for ADR-048.
  - Unrelated dependency/security cleanup.
- Protected paths:
  - N/A expected; if touched, manager must amend the ledger before editing.
- Deferred work:
  - N/A unless a new owner-approved follow-up issue is created.

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

- [x] Dedicated manager branch and worktree created. -> branch
  `fix/pr1577-adr048-final-blockers`.
- [x] Existing issues linked or new issue created only if none exists. -> #1644,
  #1623, #1594.
- [x] Gate record started. ->
  `.workflow/records/1644-pr1577-adr048-final-blockers.json`.
- [x] Scope include/exclude recorded in the gate record. -> gate `init`.
- [x] Dispatch checklist committed. -> this file.
- [x] Dispatch prompts created from the correct prompt template and linked below.
      -> `docs/planning/adr-048-pr1577-fix-dispatch-plot.md`,
      `docs/planning/adr-048-pr1577-fix-dispatch-compat.md`,
      `docs/planning/adr-048-pr1577-fix-dispatch-packaging-e2e.md`.
- [x] Sentrux baseline recorded, or N/A reason recorded. ->
      `mcp__sentrux.scan` quality_signal `4555`; `mcp__sentrux.check_rules`
      passed 3 available architectural rules with 0 violations.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A`
- Owner authorization source: `N/A`
- Reason: `N/A`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record check --mode pre-commit` | N/A | `[x]` | passed; tier=1 checks=`architecture_tests`, `deferral_discipline`, `format_check`, `frontend`, `full_audit`, `import_contracts`, `lint_format`, `type_check`; reconciliation passed |
| Commit message | `python -m scistudio.qa.governance.gate_record commit-msg .workflow/local/commit-msg-1644.txt` | N/A | `[x]` | passed; reconciliation passed |
| Pre-push | `python -m scistudio.qa.governance.gate_record check --mode pre-push --base origin/track/adr-048-spec1-preview-system --head HEAD` | N/A | `[x]` | passed; tier=1 checks=`architecture_tests`, `deferral_discipline`, `format_check`, `frontend`, `full_audit`, `import_contracts`, `lint_format`, `python_tests`, `semantic_dup`, `type_check`; reconciliation passed |
| Pre-PR reconcile | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body-1644.md` | N/A | `[x]` | passed; tier=1 checks=`architecture_tests`, `deferral_discipline`, `format_check`, `frontend`, `full_audit`, `import_contracts`, `lint_format`, `python_tests`, `semantic_dup`, `type_check`; reconciliation passed |

## 5.1 Docs Impact Check

- Wrapper/hook/gate-record/receipt/CI/runtime behavior changed: `no`
- AI docs checked:
  `docs/ai-developer/rules.md`,
  `docs/ai-developer/specific_rules/gated-workflow.md`,
  `docs/ai-developer/specific_rules/agent-dispatch.md`,
  `docs/ai-developer/templates/*dispatch*.md`
- Updated docs or N/A rationale: `N/A - no AI workflow behavior changes`.

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| PLOT | implementer | N/A | `docs/planning/adr-048-pr1577-fix-dispatch-plot.md` | Plot reachability design/patch | inherited/forked | forked | plot API/MCP/frontend tests | compat cleanup, pyproject | #1644/#1623 | `[x]` -> `run_plot_job` now returns `data_ref`/`preview_target`; `DataPreview` runs plot and mounts `PreviewHost`; tests listed in Section 10 |
| COMPAT | implementer | N/A | `docs/planning/adr-048-pr1577-fix-dispatch-compat.md` | MCP inspection no-compat cleanup + spec text | inherited/forked | forked | tools_inspection/docs/tests | plot UI, pyproject | #1644/#1594 | `[x]` -> `tools_inspection` stale compat text removed; `adr-048-preview-system` FR-027 narrowed; tests listed in Section 10 |
| PKG-E2E | test_engineer | N/A | `docs/planning/adr-048-pr1577-fix-dispatch-packaging-e2e.md` | previewer entry point + viewer e2e evidence | inherited/forked | forked | pyproject/tests/e2e docs | plot/MCP internals | #1644 | `[x]` -> `packages/scistudio-blocks-imaging/tests/test_previewer_registration.py`, `docs/ai-developer/e2e/2026-06-13-adr048-pr1577-viewers.md`; tests listed in Section 10 |

## 7. Track: Plot Reachability

- [x] User/AI plot public entry point produces or returns a routed
      `plot_artifact` preview target. -> `PlotRunResult.data_ref` and
      `PlotRunResult.preview_target`; `tests/ai/test_mcp_tools_plot.py`.
- [x] Production frontend has a minimal affordance or host path that calls
      `runPlotJob -> plotTargetFromRunResponse -> PreviewHost`. ->
      `frontend/src/components/DataPreview.tsx`; covered by
      `DataPreview.test.tsx`.
- [x] Tests prove public path, not only isolated REST helper path. ->
      `tests/api/test_plot_preview_wiring.py`,
      `tests/ai/test_mcp_tools_plot.py::test_run_python_svg_success`, and
      `frontend/src/components/DataPreview.test.tsx`.

## 8. Track: No-Compat Cleanup

- [x] MCP inspection `preview_data` no longer claims or uses retained
      compatibility-adapter behavior, or an explicit owner-approved narrowing is
      recorded. -> canonical bounded MCP read wording in
      `src/scistudio/ai/agent/mcp/tools_inspection/**`.
- [x] Spec/docs no longer prescribe stale compatibility wrappers. ->
      `docs/specs/adr-048-preview-system.md` no longer allows ADR-048 REST
      compat adapters.
- [x] Tests updated for the canonical behavior. ->
      `tests/ai/test_mcp_tools_inspection.py`.

## 9. Track: Packaging And E2E

- [x] `scistudio.previewers` entry point group works in installed-package mode.
      -> `packages/scistudio-blocks-imaging/pyproject.toml` already declares
      `[project.entry-points."scistudio.previewers"]`; tested by
      `test_pyproject_declares_installed_previewer_entry_point` and
      `test_installed_entry_point_registers_imaging_previewers`.
- [x] Regression test fails without the entry point and passes with it. ->
      `packages/scistudio-blocks-imaging/tests/test_previewer_registration.py`
      now asserts the installed metadata group and exercises
      `PreviewerRegistry.load_packages(include_monorepo=False)` through an
      `importlib.metadata.EntryPoint`.
- [x] Final ADR-048 viewer e2e scenario/evidence created in worktree. ->
      `docs/ai-developer/e2e/2026-06-13-adr048-pr1577-viewers.md` covers
      DataFrame, Array, Series, Text, Artifact, CompositeData, Collection,
      Image/Label package previewers, and Plot. Section 7 records an automated
      routed-session sweep pass; Chrome extension control was verified in this
      Codex session, but no GUI screenshots were captured because the scenario
      verifies the routed preview session API and installed previewer discovery.

## 10. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Gate ledger check (local) | `python -m scistudio.qa.governance.gate_record check --mode local --base origin/track/adr-048-spec1-preview-system --head HEAD --pr-body-file .workflow/local/pr-body-1644.md` | `[x]` | passed; mode=local tier=2 checks=`format_check`, `full_audit`, `lint_format`; reconciliation passed |
| Targeted tests | task-specific pytest/vitest/e2e commands | `[x]` | `$env:PYTHONPATH='src;packages/scistudio-blocks-imaging/src'; python -m pytest tests/api/test_previewers.py tests/api/test_plot_preview_wiring.py tests/ai/test_mcp_tools_plot.py tests/ai/test_mcp_tools_inspection.py -q --no-cov --timeout=60` -> passed (`1 skipped`: Rscript not on PATH). `$env:PYTHONPATH='src;packages/scistudio-blocks-imaging/src'; python -m pytest packages/scistudio-blocks-imaging/tests/test_previewer_registration.py -q --no-cov --timeout=60` -> `16 passed`. `npm --prefix frontend test -- src/components/DataPreview.test.tsx src/lib/api/__tests__/plotPreview.test.ts src/lib/api/__tests__/api-surface.test.ts` -> `17 passed` with existing active-context stderr. `npm --prefix frontend run typecheck` -> passed. `python -m ruff check ...` -> passed. `git diff --check` -> passed. |
| Gate ledger check (pre-PR) | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --base origin/track/adr-048-spec1-preview-system --head HEAD --pr-body-file .workflow/local/pr-body-1644.md` | `[x]` | passed; mode=pre-pr tier=1 checks=`architecture_tests`, `deferral_discipline`, `format_check`, `frontend`, `full_audit`, `import_contracts`, `lint_format`, `python_tests`, `semantic_dup`, `type_check`; reconciliation passed |
| Gate finalize (pre-PR) | `python -m scistudio.qa.governance.gate_record finalize --base origin/track/adr-048-spec1-preview-system --head HEAD --commit <sha> --pr-body-file .workflow/local/pr-body-1644.md --closes "#1644"` | `[x]` | passed; finalize mode=pre-PR tier=1; ledger is PR-ready |
| Wrapper preflight | `python scripts/scistudio_pr_create.py --base track/adr-048-spec1-preview-system --head fix/pr1577-adr048-final-blockers --title "fix(#1644): wire ADR-048 final blockers" --body-file .workflow/local/pr-body-1644.md` | `[x]` | passed; wrapper pre-flight clean and created PR #1645 |

## 11. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|

## 12. Final Readiness

- [x] All dispatched agents have final outputs.
- [x] Manager reviewed every changed file.
- [x] Gate record includes issue, scope, plan, docs, tests, checks, commit, and
      PR evidence.
- [x] PR closes every issue fixed by the dispatch. -> PR #1645 body closes
      #1644, #1623, and #1594.
- [~] CI passed. -> PR #1645 checks started; waiting for GitHub Actions.
- [x] Checklist final state matches PR and gate record.
