---
title: "ADR-048 PR Fix Dispatch Prompts"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 48
language_source: en
---

# ADR-048 PR Fix Dispatch Prompts

These are the manager-recorded dispatch prompts for the 2026-06-11 repair pass.

## SPEC1-FIX

[DISPATCH-TEMPLATE-V1: implementer]

- Repository: SciStudio
- Task kind: `bugfix`
- Persona: `implementer`
- Issue: #1574
- Umbrella PR: #1577 `[DO NOT MERGE] ADR-048 SPEC 1: extensible preview system`
- Branch: `track/adr-048-spec1-preview-system`
- Worktree: `C:\Users\<user>\Desktop\workspace\sci-wt\spec1-mgr`
- Gate record: `.workflow/records/1574-track-adr-048-spec1-preview-system.json`
- Checklist: `docs/planning/adr-048-pr-fix-dispatch-checklist.md`

Scope:

- Fix preview session resource parameter propagation for collection/composite child resources.
- Fix plot `export` resource behavior end-to-end, or remove the advertised export resource if the implementation contract requires no export resource.
- Add regression tests for every behavior fixed.
- Update docs/specs only where implementation behavior changes.
- Refresh gate ledger evidence for PR #1577.

Primary allowed write set:

- `src/scistudio/previewers/**`
- `src/scistudio/api/routes/**`
- `src/scistudio/api/schemas.py`
- `frontend/src/components/DataPreview.parts/**`
- `frontend/src/types/api.ts`
- `tests/previewers/**`
- `tests/api/**`
- `frontend/src/components/DataPreview.parts/*.test.tsx`
- `docs/specs/adr-048-preview-system.md`
- `.workflow/records/1574-track-adr-048-spec1-preview-system.json`
- `docs/planning/adr-048-pr-fix-dispatch-checklist.md`

Out of scope:

- SPEC 2 plot MCP runtime beyond preview export integration.
- SPEC 3 developer docs refresh.
- Gate/governance implementation under `src/scistudio/qa/governance/**`.
- `docs/ai-developer/**`.

Required tests/checks:

- Focused backend tests for child resource params and plot export.
- Focused frontend tests if `PreviewHost`/host API changes.
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr --base origin/main --head HEAD --pr-body-file .workflow/local/pr-body.md`

Stop if local hooks are blocked by issue #1584; do not use `--no-verify`.

## SPEC2-FIX

[DISPATCH-TEMPLATE-V1: implementer]

- Repository: SciStudio
- Task kind: `bugfix`
- Persona: `implementer`
- Issue: #1575
- Umbrella PR: #1580 `[DO NOT MERGE] ADR-048 SPEC 2: AI plot tools + preview-side plot jobs`
- Branch: `track/adr-048-spec2-plot-tools`
- Worktree: `C:\Users\<user>\Desktop\workspace\sci-wt\spec2-mgr`
- Gate record: `.workflow/records/1575-track-adr-048-spec2-plot-tools.json`
- Checklist: `docs/planning/adr-048-pr-fix-dispatch-checklist.md`

Scope:

- Enforce `plot.yaml` `script.path` confinement in `read_plot_source` and `run_plot_job`, not only in `validate_plot`.
- Enforce project-root confinement for `list_plot_targets(workflow_path=...)`.
- Add regression tests that reproduce path traversal attempts and prove rejection.
- Fix stale `current.*` artifact cleanup after failed reruns when feasible without broad refactor; otherwise add a tracked TODO with issue reference.
- Fix dynamic/effective output port target discovery when feasible without touching SPEC 1.
- Refresh gate ledger evidence for PR #1580.

Primary allowed write set:

- Plot MCP/tool/runtime implementation files discovered under `src/scistudio/**`
- Plot tests under `tests/**`
- `docs/specs/adr-048-ai-plot-tools.md`
- `.workflow/records/1575-track-adr-048-spec2-plot-tools.json`
- `docs/planning/adr-048-pr-fix-dispatch-checklist.md`

Out of scope:

- SPEC 1 previewer frontend/session resource fixes.
- SPEC 3 developer docs refresh.
- Gate/governance implementation under `src/scistudio/qa/governance/**`.
- `docs/ai-developer/**`.

Required tests/checks:

- Focused plot MCP/runtime tests for script path traversal and workflow path traversal.
- Focused tests for any stale-artifact or dynamic-target fix implemented.
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr --base origin/track/adr-048-spec1-preview-system --head HEAD --pr-body-file .workflow/local/pr-body.md`

Stop if local hooks are blocked by issue #1584; do not use `--no-verify`.

## SPEC3-FIX

[DISPATCH-TEMPLATE-V1: implementer]

- Repository: SciStudio
- Task kind: `docs`
- Persona: `implementer`
- Issue: #1576
- Umbrella PR: #1581 `[DO NOT MERGE] ADR-048 SPEC 3: developer docs delete-and-rewrite`
- Branch: `track/adr-048-spec3-docs`
- Worktree: `C:\Users\<user>\Desktop\workspace\sci-wt\spec3-mgr`
- Gate record: `.workflow/records/1576-track-adr-048-spec3-docs.json`
- Checklist: `docs/planning/adr-048-pr-fix-dispatch-checklist.md`

Scope:

- Fix active packaged skill/template drift:
  - `preview_data(ref)` must match actual `preview_data` tool signature requiring `fmt`.
  - `get_block_output` examples must match actual parameters and result envelope.
  - entry point examples must use callable factories such as `my_blocks:get_blocks`.
  - remove forbidden `pip install -e .` and `pip install -e ".[dev]"` guidance.
- Add regression tests that scan packaged skills/templates for these contracts.
- Update docs/specs only where current behavior requires it.
- Refresh gate ledger evidence for PR #1581.

Primary allowed write set:

- `src/scistudio/_skills/**`
- templates/scaffold docs discovered by search
- `tests/**` docs/skills/template contract tests
- `docs/specs/adr-048-developer-docs-refresh.md`
- `.workflow/records/1576-track-adr-048-spec3-docs.json`
- `docs/planning/adr-048-pr-fix-dispatch-checklist.md`

Out of scope:

- SPEC 1 preview runtime changes.
- SPEC 2 plot runtime changes.
- Gate/governance implementation under `src/scistudio/qa/governance/**`.
- `docs/ai-developer/**`.

Required tests/checks:

- Focused docs/skill/template contract tests.
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr --base origin/track/adr-048-spec2-plot-tools --head HEAD --pr-body-file .workflow/local/pr-body.md`

Stop if local hooks are blocked by issue #1584; do not use `--no-verify`.

## SPEC1-AUDIT-NO-CONTEXT

[DISPATCH-TEMPLATE-V1: audit-no-context]

Allowed audit surfaces: preview system docs, preview session/API/frontend code, and tests.
Do not read issues, PR pages, this checklist, dispatch prompts, manager reports, or chat context.
Report path: `docs/audit/2026-06-11-adr048-spec1-no-context.md`.

## SPEC2-AUDIT-NO-CONTEXT

[DISPATCH-TEMPLATE-V1: audit-no-context]

Allowed audit surfaces: plot tools docs, MCP/tool/runtime implementation, preview-side plot job code, and tests.
Do not read issues, PR pages, this checklist, dispatch prompts, manager reports, or chat context.
Report path: `docs/audit/2026-06-11-adr048-spec2-no-context.md`.

## SPEC3-AUDIT-NO-CONTEXT

[DISPATCH-TEMPLATE-V1: audit-no-context]

Allowed audit surfaces: developer docs, packaged skills, scaffold templates, and docs/skill/template tests.
Do not read issues, PR pages, this checklist, dispatch prompts, manager reports, or chat context.
Report path: `docs/audit/2026-06-11-adr048-spec3-no-context.md`.
