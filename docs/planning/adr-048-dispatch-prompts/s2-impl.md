# Dispatch Prompt — S2-impl (ADR-048 SPEC 2 AI plot tools + preview-side plot jobs)

[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity
- Repository: SciStudio
- Owner request: Implement ADR-048 SPEC 2 in full (no v1 reductions) — 6 MCP plot tools, plot.yaml + Python/R templates, preview-side plot runtime writing to the preview cache, the `scistudio-write-plot` skill + provisioning, and all pinned count-test updates.
- Task kind: feature · Persona: implementer
- Issue: #1575 — https://github.com/zjzcpj/SciStudio/issues/1575
- Umbrella PR: (SPEC 2, stacked on SPEC 1) — manager opens it; base = `track/adr-048-spec1-preview-system`
- Protected branch: main · Umbrella branch: track/adr-048-spec2-plot-tools
- Agent branch: feat/adr-048-plot-tools (ALREADY CREATED by manager)
- Agent worktree: C:/Users/<user>/Desktop/workspace/sci-wt/s2-impl (ALREADY CREATED)
- Gate record (manager-owned): .workflow/records/1575-track-adr-048-spec2-plot-tools.json
- Checklist: docs/planning/adr-048-implementation-checklist.md

## Setup
```bash
cd "C:/Users/<user>/Desktop/workspace/sci-wt/s2-impl"
# editable install points at the MAIN checkout; test YOUR code with PYTHONPATH + SCISTUDIO_DEV=1 (CI parity):
export PP="C:/Users/<user>/Desktop/workspace/sci-wt/s2-impl/src"
SCISTUDIO_DEV=1 PYTHONPATH="$PP" python -c "import scistudio; from scistudio.previewers import models; print('ok')"
```
Do NOT use `pip install -e .`. Work ONLY in this worktree. Your base branch already contains SPEC 1 (`src/scistudio/previewers/**`).

## Required Rules
- AGENTS.md, docs/ai-developer/rules.md, docs/ai-developer/personas/implementer.md
- docs/adr/ADR-048.md (§5 plot-job contract, §9 AI tools), docs/specs/adr-048-ai-plot-tools.md (YOUR CONTRACT — FR-001..FR-035, SC-001..SC-010, plot.yaml schema, templates), docs/planning/adr-048-ai-plot-tools-scope.md (current-code map).

## Scope — you own ONLY
- `src/scistudio/ai/agent/mcp/tools_plot/**` (NEW), `src/scistudio/ai/agent/mcp/__init__.py` (add import), `src/scistudio/ai/agent/mcp/server.py` + `system_prompt.py` (only if a `category:plot` needs registering/rendering), `src/scistudio/ai/agent/mcp/_context.py` (only a narrow Protocol addition if needed for target discovery)
- `src/scistudio/_skills/scistudio/SKILL.md`, `src/scistudio/_skills/scistudio/scistudio-write-plot/SKILL.md` (NEW)
- `src/scistudio/agent_provisioning/skills.py`, `src/scistudio/agent_provisioning/_orchestrate.py`
- `src/scistudio/cli/install.py`
- `docs/cli-integration.md`
- `pyproject.toml` (only if a non-`.md` asset needs package-data)
- tests: `tests/ai/test_mcp_fastmcp.py`, `tests/ai/test_mcp_tools_plot.py` (NEW), `tests/integration/test_phase2_mcp_end_to_end.py`, `tests/ai/test_system_prompt.py`, `tests/api/test_preview_plot_jobs.py` (NEW), `tests/packaging/test_wheel_skills.py`, `tests/agent_provisioning/test_skills.py`, `tests/agent_provisioning/test_orchestrate.py`, `tests/cli/test_install.py`

## You MUST NOT touch (out of scope / protected)
- `src/scistudio/blocks/**` — PROTECTED. You REUSE the CodeBlock runner by IMPORT ONLY (e.g. `from scistudio.blocks.code._backends_registry import run_codeblock_process`), never editing it. If you need to change blocks/, STOP and report.
- `src/scistudio/previewers/**`, `src/scistudio/api/**`, `frontend/**`, `packages/**` (SPEC 1 — read-only here). If you need a change there, STOP and report.
- Any other protected path (core/engine/workflow/utils/qa). If you need an out-of-scope file, STOP and report.

## VERIFIED integration facts (confirm against the real code)
- MCP: module-scope `mcp = FastMCP(...)` in `src/scistudio/ai/agent/mcp/server.py`; tools register via `@mcp.tool(name=..., tags={"category:<cat>", "write"})` (omit `write` → read). `tools/list` derives category from the `category:` tag + mutation from `write`. Eager imports live in `src/scistudio/ai/agent/mcp/__init__.py` — add your tool module there. Study `tools_authoring.py::scaffold_block` as the write-tool pattern (Pydantic result with `next_step` + `warnings`, `_resolve_project_path` confinement). Use `get_context()` (`_context.py`: `MCPContext` has `block_registry`, `type_registry`, `project_dir`, `active_workflow_id`, and `workflow_runs`) for project/workflow access; use `_resolve_project_path` for ALL path args.
- Add a new `category:plot`. `tests/ai/test_system_prompt.py` + `system_prompt.py` `category_titles` must learn the new category (e.g. "### (e) Plot authoring"); the prompt's static tool catalog fallback must list the plot tools.
- Tool count is currently **27**, asserted in `tests/ai/test_mcp_fastmcp.py` (`_EXPECTED_TOOL_NAMES` set + `len == 27`) and `tests/integration/test_phase2_mcp_end_to_end.py` (`len == 27`). Adding 6 plot tools → **33**: update both.
- Skills: `agent_provisioning/skills.py::_SKILL_NAMES` has 6 names; `write_skills` cross-installs to `.claude/skills` + `.agents/skills` = 12 files. Adding `scistudio-write-plot` → 7 names / 14 files. Update `tests/agent_provisioning/test_skills.py` (names + written count 12→14), `tests/agent_provisioning/test_orchestrate.py` (12→14), `tests/packaging/test_wheel_skills.py` (`_TASK_SKILLS` 5→6). `pyproject.toml` package-data `_skills/scistudio/**/*.md` already ships the new skill.
- CodeBlock runner reuse (IMPORT ONLY): `scistudio.blocks.code._backends_registry.run_codeblock_process` — call it KEYWORD-ONLY: `run_codeblock_process(*, argv=..., cwd=..., env_delta=..., timeout_seconds=...)` (the helper's signature is keyword-only; raises `CodeBlockTimeoutError`); interpreter resolution in `interpreters.py`; R via `runners/r_runner.py` / `backends/r_quarto.py`.
- Workflow targets: workflows live at `<project>/workflows/*.yaml`; `scistudio.workflow.serializer.load_yaml` → `WorkflowDefinition` with `NodeDef(id, block_type, config)`. Latest outputs: in-memory `ctx.workflow_runs[run_id].scheduler._block_outputs[block_id][port]` (see `tools_inspection/read.py::get_block_output`) and/or the lineage store (`.scistudio/lineage.db`). Derive a stable `target_id` from workflow_path + node_id + output_port; NEVER bind by block label alone.
- SPEC 1 PlotPreviewer contract (already in your base branch — read `src/scistudio/previewers/fallbacks.py` `plot_previewer` / `core.plot.basic`): it renders PNG/JPEG/SVG(sanitized)/PDF artifacts. Your `run_plot_job` writes display-only artifacts to `.scistudio/previews/<workflow_id>/<node_id>/<output_port>/<plot_id>/current.*` + `current.json` (the cache layout ADR-048 §5 specifies). Confirm the exact preview-cache path helper the preview system uses (grep `previews` under `src/scistudio/previewers/` and `src/scistudio/api/runtime/`) and reuse it so `PlotPreviewer` can find your artifacts.

## Work To Do (implement docs/specs/adr-048-ai-plot-tools.md IN FULL — FR-001..FR-035)
1. `src/scistudio/ai/agent/mcp/tools_plot/` package: `__init__.py` (registration side-effects + re-exports), `models.py` (Pydantic `PlotTarget`, `PlotManifest`/plot.yaml model, `PlotRunResult`, scaffold/validate result models — all write/run results expose `next_step`), `targets.py` (target discovery + deterministic `target_id`), `scaffold.py` (Python/R templates + file creation, refuse overwrite without `overwrite=true`), `validation.py` (manifest schema, path confinement, target existence, output formats, language, entrypoint shape, runner availability diagnostics), `runtime.py` (preview-side execution reusing `run_codeblock_process`, confined cwd, cache writes + `current.json`, timeout/output-size/file-count caps, sanitized errors, status), `examples.py` (curated matplotlib/seaborn/ggplot2 examples).
2. The 6 MCP tools (all `tags={"category:plot", ...}`): `list_plot_targets`, `scaffold_plot` (write), `list_plot_examples`, `read_plot_source`, `validate_plot`, `run_plot_job` (write/run). `scaffold_plot`/`run_plot_job` return `next_step`. Register via import in `mcp/__init__.py`.
3. plot.yaml strict versioned schema + Python `render(collection, context)` and R `render <- function(collection, context)` templates (exact shapes in the spec §3). Context helpers: bounded `to_dataframe(collection, max_rows=...)`, `plt` (matplotlib), `save_figure`/`save_plot` (PNG/JPEG/SVG/PDF). Plot scripts receive the selected collection; NO workflow-mutation APIs.
4. Plot execution writes ONLY display-only artifacts to the preview cache; current-overwrite; `current.json` records manifest/script path+hash, target, input collection ids, run id, runner, created time, outputs, status, sanitized error. MUST NOT register workflow nodes, edit workflow YAML, create downstream collections, or claim lineage (verify in a test).
5. `scistudio-write-plot` skill (mirror `scistudio-write-block/SKILL.md` structure): discover targets → scaffold → edit → validate → run; explicitly state plot jobs are preview-only, never workflow DAG nodes, never bind by label alone. Add it to the base `SKILL.md` index + static tool catalog fallback. Add to `_SKILL_NAMES`; update provisioning/install + all count tests.
6. `docs/cli-integration.md`: add the plot skill + the 6 plot tools to the inventory/counts.
7. Tests: new `tests/ai/test_mcp_tools_plot.py` (target listing/uniqueness, scaffold create+overwrite-refuse+path-traversal-reject, examples, read requires exactly one of plot_id/path, validation success/failure cases, run success with SVG output, sanitized failure, timeout/size caps), new `tests/api/test_preview_plot_jobs.py` (current.* + current.json written; rerun overwrites; failed rerun records failure; no workflow/lineage/downstream mutation; artifact consumable by `core.plot.basic`). R execution: validate manifest always; run only if Rscript available else `pytest.importorskip`/skip-if-unavailable or a mocked runner. Update the count tests (33 tools / 7 skills / 14 files / _TASK_SKILLS).

## Required checks (run from worktree; all green) — use SCISTUDIO_DEV=1 + PYTHONPATH for CI parity
```bash
WT="C:/Users/<user>/Desktop/workspace/sci-wt/s2-impl"
SCISTUDIO_DEV=1 PYTHONPATH="$WT/src" python -m pytest tests/ai/test_mcp_fastmcp.py tests/ai/test_mcp_tools_plot.py tests/integration/test_phase2_mcp_end_to_end.py tests/ai/test_system_prompt.py tests/api/test_preview_plot_jobs.py tests/packaging/test_wheel_skills.py tests/agent_provisioning/test_skills.py tests/agent_provisioning/test_orchestrate.py tests/cli/test_install.py -q --no-cov -p no:cacheprovider -m "not requires_r"
ruff check src/scistudio/ai/agent/mcp/tools_plot src/scistudio/agent_provisioning src/scistudio/cli tests/ai/test_mcp_tools_plot.py tests/api/test_preview_plot_jobs.py
ruff format --check src/scistudio/ai/agent/mcp/tools_plot tests/ai/test_mcp_tools_plot.py tests/api/test_preview_plot_jobs.py
SCISTUDIO_DEV=1 PYTHONPATH="$WT/src" python -m mypy src/scistudio/ai/agent/mcp/tools_plot
```
Fix everything until green. Any deferral needs a `# TODO(#NNN)` tracked reference. NO v1 reductions.

## Commit + deliver (NO PR, NO gate_record — manager owns those)
Commit with trailers:
```
feat(ai): ADR-048 SPEC 2 — preview-side plot jobs + 6 MCP plot tools + scistudio-write-plot

<body>

Refs #1575
Gate-Record: .workflow/records/1575-track-adr-048-spec2-plot-tools.json
Task-Kind: feature
Issue: #1575
Assisted-by: claude-code:claude-fable-5
```
Then `git push -u origin feat/adr-048-plot-tools`.

## Output Required
- Changed/created file paths.
- The 6 tool signatures + result models (with `next_step`), the plot.yaml schema, and the preview-cache path/`current.json` shape your runtime writes (so the smoke tests + PlotPreviewer align).
- How `run_plot_job` reuses the CodeBlock runner without editing blocks/ and without DAG/lineage effects.
- Test/lint/mypy outputs with pass counts (note R skip status).
- Commit SHA + branch (confirm pushed). Any blocker/scope issue.

## Stop Conditions
Stop and report if: you need a protected/out-of-scope file (esp. blocks/, previewers/, api/); the PlotPreviewer/cache contract is insufficient; tests can't be made green for unclear reasons.
