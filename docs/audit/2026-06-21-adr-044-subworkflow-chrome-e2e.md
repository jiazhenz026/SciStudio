---
title: "ADR-044 SubWorkflowBlock — Live E2E Evidence"
status: Draft
owners:
  - "@jiazhenz026"
related_issue: 890
related_adrs:
  - 44
date: 2026-06-21
---

# ADR-044 SubWorkflowBlock — Live E2E Evidence

Live end-to-end verification of the ADR-044 implementation against a **running
umbrella build** (backend `uvicorn scistudio.api.app:create_app` on `:8001` with
`PYTHONPATH=src` from the umbrella worktree; Vite dev server on `:5175` proxying
`/api` + `/ws` → `:8001`). Driven in the owner's macOS Chrome via browser
automation. The pre-existing dev session (a different worktree on `:8000`/`:5173`)
was left untouched.

## 1. Live API E2E (curl against the running `:8001` server)

A real project was created via `POST /api/projects/`, then parent/child workflow
YAML written into it.

| Check | FR/SC | Result |
|---|---|---|
| `GET /api/workflows/main` → subworkflow node carries `resolved_ports` | FR-004 / D4 | ✅ `inputs:[raw_in]`, `outputs:[report]`, `broken:false`, `ref_path:subworkflows/child.yaml` |
| `GET /api/workflows/by-path?path=subworkflows/child.yaml` | US1 AS3 / P1-1 | ✅ returns the child workflow (`load_block`, `process_block`) |
| `GET /api/workflows/by-path?path=../../etc/passwd` | path safety | ✅ `400` (escape rejected) |
| `POST /api/workflows/import-subworkflow {source_path}` | FR-011 | ✅ copied to `subworkflows/`, returned `ref_path: subworkflows/adr044-ext.yaml` |
| `GET /api/workflows/brokenwf` (missing ref) | FR-010 | ✅ `resolved_ports.broken:true`, `ref_path:subworkflows/missing.yaml` |
| `POST /api/workflows/brokenwf/execute` (broken ref) | FR-010 / US6.3 | ✅ `422` with `"... subworkflow reference 'subworkflows/missing.yaml' could not be resolved"` (this run surfaced + fixed a 500→422 route gap) |

## 2. Browser Render E2E (owner's Chrome → `:5175`)

Opened the `adr044e2e` project and exercised the canvas:

1. **Healthy render (`main` workflow):** the `subworkflow_block` node renders as
   the **`SubWorkflowNode`** (pink, Package category icon) labelled `child` (the
   ref filename stem) — NOT the generic `BlockNode`. Confirms the P0 routing fix
   (`subworkflow_block`, not the bare `subworkflow`).
2. **Dynamic ports (FR-004):** zoom confirmed two exposed-port handles — an input
   handle (`raw_in`) on the left and an output handle (`report`) on the right —
   derived from the server `resolved_ports` surface.
3. **Double-click navigation (US1.3 / P1-1):** double-clicking the node opened the
   referenced **`child`** file in a new canvas tab, showing the child's inner
   blocks (`load_block` → `process_block`). The file lives under
   `subworkflows/child.yaml` and was opened via the new by-path load — proving the
   P1 fix (refs under `subworkflows/` open correctly, not mis-resolved to
   `workflows/<stem>`).
4. **Broken-ref render (FR-010):** the `brokenwf` workflow's node renders as a red
   **"Broken reference / subworkflows/missing.yaml"** node with a **"Locate file…"**
   affordance, while the rest of the canvas loads normally.

## 3. SC-007 (Chrome smoke) status

SC-007 (drop a SubWorkflowBlock, set `config.ref.path`, connect an exposed port,
persist + reload) is covered structurally by the above (render from a persisted
`config.ref.path`, exposed-port handles, reload-driven `resolved_ports`). Full
live execution of a flattened run (SC-001/SC-002 end-to-end through the scheduler)
is covered by `tests/integration/test_subworkflow_lineage.py` and the live API
checks above; a runnable child requires real executable blocks + input data and
is exercised by the integration suite rather than the browser smoke.

## Environment note

No `pip install -e .` was used; the backend ran with `PYTHONPATH=src` from the
umbrella worktree so the live server executed the umbrella code (verified: the
running `:8001` OpenAPI exposes `/api/workflows/by-path` and
`/api/workflows/import-subworkflow`, and `subworkflow_block` is in the block
palette).
