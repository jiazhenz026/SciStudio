---
title: "ADR-048 PR1577 Plot Reachability Dispatch"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs:
  - 48
language_source: en
---

# ADR-048 PR1577 Plot Reachability Dispatch

Persona: `implementer`
Task kind: `bugfix`
Issues: #1644, #1623
Base: PR #1577 head (`track/adr-048-spec1-preview-system`)

## Task

Fix the plot reachability blocker from the final PR #1577 audit:
`run_plot_job` artifacts must be reachable from the public user/AI path and
render through `PreviewHost` / core `PlotPreviewer`, not only through isolated
REST helper tests.

## Write Set

- `src/scistudio/api/routes/plots.py`
- `src/scistudio/api/runtime/_data.py`
- `src/scistudio/ai/agent/mcp/tools_plot/**`
- `frontend/src/components/DataPreview.parts/**`
- `frontend/src/components/DataPreview.tsx`
- `frontend/src/lib/api/**`
- `frontend/src/types/api.ts`
- `tests/api/test_plot_preview_wiring.py`
- `tests/api/test_preview_plot_jobs.py`
- `tests/ai/test_mcp_tools_plot.py`
- `frontend/src/**/*.test.*`

## Out Of Scope

- MCP inspection/no-compat cleanup.
- `pyproject.toml` entry point fix.
- Broad app-shell redesign not needed for minimal ADR-048 reachability.
- Merging PR #1577 or any PR.

## Required Result

- Implement or propose the minimal patch.
- Add/update tests so the public path is covered.
- Do not defer the public UI/AI path as "pane placement" unless there is a
  tracked owner-approved follow-up and the remaining contract is still usable.
- If you edit files, report changed paths and exact test commands run.
