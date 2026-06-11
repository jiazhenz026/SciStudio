# ADR-048 SPEC 2 AI Plot Tools Impact Scope

## Summary

This report scopes SPEC 2 for ADR-048: AI MCP plot authoring tools, the packaged
`scistudio-write-plot` skill, provisioning, and AI-facing documentation. The
governing design is the current `docs/adr/ADR-048.md` in this worktree: plot
jobs are preview-side artifacts, not workflow blocks or DAG nodes, and Section
9 requires `scistudio-write-plot` plus six MCP tools
(`list_plot_targets`, `scaffold_plot`, `list_plot_examples`,
`read_plot_source`, `validate_plot`, `run_plot_job`) (`docs/adr/ADR-048.md:390`).

The current implementation gives SPEC 2 a clear pattern to follow:

- MCP tools register by decorating async functions on the shared FastMCP
  instance and relying on eager imports to populate `mcp.list_tools()`
  (`src/scistudio/ai/agent/mcp/server.py:51`,
  `src/scistudio/ai/agent/mcp/__init__.py:42`).
- Tool return schemas are Pydantic models, and write-class tools conventionally
  expose `next_step` (`src/scistudio/ai/agent/mcp/tools_authoring.py:54`,
  `tests/ai/test_mcp_fastmcp.py:88`).
- Skills are packaged under `src/scistudio/_skills/scistudio/**`, shipped in
  wheels by the package-data glob, and installed flat into both Claude and
  Codex skill trees (`pyproject.toml:124`,
  `src/scistudio/agent_provisioning/skills.py:59`).
- Plot tooling should mirror the block-authoring guardrails and call sequence,
  but it must avoid block-specific assumptions: no `blocks/*.py`, no
  `Block` subclass, no `reload_blocks`, no workflow-node insertion, and no
  output lineage claims.

## Current Surfaces

### MCP registration and packaging

- `src/scistudio/ai/agent/mcp/server.py`: owns the module-scope FastMCP
  instance (`mcp = FastMCP(...)`) and JSON-RPC transport wrapper. `tools/list`
  derives each tool's category and mutation from FastMCP tags
  (`src/scistudio/ai/agent/mcp/server.py:263`).
- `src/scistudio/ai/agent/mcp/__init__.py`: eagerly imports workflow,
  authoring, inspection, and QA modules so `@mcp.tool` decorators run at import
  time (`src/scistudio/ai/agent/mcp/__init__.py:42`).
- `src/scistudio/ai/agent/mcp/tools_workflow/__init__.py`: newer package-style
  surface for a multi-file tool category, with side-effect imports for
  registration and re-exports for compatibility
  (`src/scistudio/ai/agent/mcp/tools_workflow/__init__.py:39`).
- `src/scistudio/ai/agent/mcp/tools_authoring.py`: older single-module
  category for block authoring. It defines Pydantic result envelopes and
  decorates five tool functions (`src/scistudio/ai/agent/mcp/tools_authoring.py:38`,
  `src/scistudio/ai/agent/mcp/tools_authoring.py:119`).
- `tests/ai/test_mcp_fastmcp.py`: pins exact tool names/count, write-class
  `next_step`, input-schema generation, and `scaffold_block` signature
  (`tests/ai/test_mcp_fastmcp.py:33`, `tests/ai/test_mcp_fastmcp.py:78`).
- `tests/integration/test_phase2_mcp_end_to_end.py`: validates the transport
  handshake, `tools/list`, and `tools/call` round trip
  (`tests/integration/test_phase2_mcp_end_to_end.py:60`).

SPEC 2 should add a new plot-specific MCP category rather than adding these
tools to generic block authoring. A package-style layout such as
`src/scistudio/ai/agent/mcp/tools_plot/` is likely cleaner than another
large single file because plot tooling will need schemas, templates, path
helpers, validation, target discovery, and execution.

### Block authoring workflow to mirror or avoid

Current block authoring teaches a deliberate sequence:

- `list_blocks` is the authoritative reuse/discovery tool
  (`src/scistudio/ai/agent/mcp/tools_workflow/read.py:51`).
- `scaffold_block` writes `blocks/<name>.py`, returns warnings plus
  `next_step`, and validates port choices softly
  (`src/scistudio/ai/agent/mcp/tools_authoring.py:317`).
- `reload_blocks` rescans the registry after block source edits
  (`src/scistudio/ai/agent/mcp/tools_authoring.py:420`).
- `run_block_tests` runs a targeted `tests/blocks/test_<type>.py` subprocess
  (`src/scistudio/ai/agent/mcp/tools_authoring.py:447`).
- `scistudio-write-block` makes the sequence explicit and tells agents not to
  confuse block-file authoring with adding a workflow node
  (`src/scistudio/_skills/scistudio/scistudio-write-block/SKILL.md:21`,
  `src/scistudio/_skills/scistudio/scistudio-write-block/SKILL.md:242`).

Plot authoring should mirror:

- discovery before creation;
- scaffold-first writes;
- structured warnings and `next_step`;
- project-root path confinement via `_resolve_project_path`
  (`src/scistudio/ai/agent/mcp/_context.py:147`);
- read/validate/run before declaring ready;
- explicit anti-pattern language in the skill.

Plot authoring should avoid:

- `list_blocks` as the required discovery step. Plot targets are workflow
  output targets, not reusable block types.
- `reload_blocks`; plot manifests/scripts are not registry-loaded block
  classes.
- `run_block_tests` naming or semantics. Plot jobs need `validate_plot` and
  `run_plot_job`, not `tests/blocks/test_*.py`.
- writing workflow YAML or node config. ADR-048 says plot jobs must not mutate
  workflow definitions, data objects, lineage, or downstream outputs
  (`docs/adr/ADR-048.md:385`).

### Agent provisioning and skill installation

- Packaged skill source lives under `src/scistudio/_skills/scistudio/`.
  `pyproject.toml` ships `_skills/scistudio/**/*.md` in the wheel
  (`pyproject.toml:124`).
- `src/scistudio/agent_provisioning/skills.py` has the canonical project
  provisioning list `_SKILL_NAMES`; it installs skills flat to
  `<project>/.claude/skills/<name>/SKILL.md` and
  `<project>/.agents/skills/<name>/SKILL.md`
  (`src/scistudio/agent_provisioning/skills.py:59`,
  `src/scistudio/agent_provisioning/skills.py:145`).
- `src/scistudio/agent_provisioning/_orchestrate.py` runs skills as one step
  among CLAUDE/AGENTS docs, hooks, and Codex config
  (`src/scistudio/agent_provisioning/_orchestrate.py:64`).
- `src/scistudio/cli/install.py` implements external CLI installation and
  copies the same flat skill layout for both Claude and Codex
  (`src/scistudio/cli/install.py:542`).
- `docs/cli-integration.md` documents the current count and the five task
  skills, so SPEC 2 should include doc updates if `scistudio-write-plot` is
  added (`docs/cli-integration.md:121`).

Adding `scistudio-write-plot` means updating both runtime provisioning
(`agent_provisioning.skills`) and external installer discovery/copy behavior,
plus tests that currently hard-code five task skills or 27 tools.

### Preview and execution surfaces

- Current API preview routing is still hardcoded in `ApiRuntime.preview_data`
  (`src/scistudio/api/runtime/_data.py:134`) and exposed by
  `GET /api/data/{data_ref}/preview` (`src/scistudio/api/routes/data.py:65`).
- `DataPreviewResponse` is currently a simple `ref`, `type_name`, `preview`
  envelope (`src/scistudio/api/schemas.py:231`).
- There is no `src/scistudio/previewers/` package yet in this worktree; ADR-048
  lists it as governed future scope, not a current surface.
- CodeBlock v2 provides reusable concepts for subprocess execution:
  backend registration, interpreter resolution, timeout wrapping, and
  project-local path resolution (`src/scistudio/blocks/code/_backends_registry.py:88`,
  `src/scistudio/blocks/code/_backends_registry.py:160`,
  `src/scistudio/blocks/code/config.py:166`).
- ADR-048 says plot jobs may reuse the block/code execution route where
  possible, but must write display-only artifacts to preview cache and never
  become scheduler-visible DAG work (`docs/adr/ADR-048.md:277`).

## Proposed In-Scope Files

Core MCP and plot authoring implementation:

- `src/scistudio/ai/agent/mcp/__init__.py` - import the new plot tool module
  or package for decorator side effects.
- `src/scistudio/ai/agent/mcp/tools_plot.py` or
  `src/scistudio/ai/agent/mcp/tools_plot/**` - define plot MCP tools,
  Pydantic result models, template helpers, project-root path handling, and
  plot-specific validation/run helpers.
- `src/scistudio/ai/agent/mcp/_context.py` - only if the plot tools need a
  narrow Protocol addition for active workflow/run/preview target discovery.
- `src/scistudio/blocks/code/**` - only for reusable runner hooks or a thin
  preview-job runner adapter; avoid changing CodeBlock DAG semantics.
- `src/scistudio/previewers/**` and `src/scistudio/api/runtime/**` - only if
  SPEC 2 needs a concrete preview cache or target-discovery API from SPEC 1.

Packaged skill and provisioning:

- `src/scistudio/_skills/scistudio/SKILL.md` - add `scistudio-write-plot` to
  the base skill index and static tool catalog fallback.
- `src/scistudio/_skills/scistudio/scistudio-write-plot/SKILL.md` - new
  task-scoped skill.
- `src/scistudio/agent_provisioning/skills.py` - add the skill to
  `_SKILL_NAMES`.
- `src/scistudio/agent_provisioning/_orchestrate.py` - update expected skill
  paths/counts.
- `src/scistudio/cli/install.py` - usually no hard-coded name change if source
  discovery is used, but update comments/docstrings/counts and verify flat
  install behavior.
- `pyproject.toml` - package-data glob likely already covers the new skill;
  update only if new non-Markdown assets/templates are added.

Documentation:

- `docs/cli-integration.md` - tool count and skill inventory.
- `docs/block-development/**` - plot authoring docs may belong adjacent to,
  but clearly separate from, block development docs.
- `docs/adr/ADR-048.md` - only if SPEC 2 uncovers contradictions in the ADR;
  otherwise the spec should refine without editing the ADR.
- Future companion spec path, likely under `specs/[###-adr-048-ai-plot-tools]/`
  or `docs/specs/adr-048-ai-plot-tools.md`, depending on the manager's chosen
  SpecKit migration path.

Tests:

- `tests/ai/test_mcp_fastmcp.py`
- `tests/ai/test_mcp_tools_authoring.py` or new
  `tests/ai/test_mcp_tools_plot.py`
- `tests/integration/test_phase2_mcp_end_to_end.py`
- `tests/ai/test_system_prompt.py`
- `tests/packaging/test_wheel_skills.py`
- `tests/agent_provisioning/test_skills.py`
- `tests/agent_provisioning/test_orchestrate.py`
- `tests/cli/test_install.py`
- Future plot runtime/cache tests, likely under `tests/previewers/`,
  `tests/api/`, or `tests/blocks/code/` depending on implementation split.

## Out-Of-Scope

- Replacing ADR-048 with the legacy old ADR-048 or old
  `adr-048-preview-providers` spec.
- Implementing type previewer routing, dynamic React previewer manifests, or
  rich imaging previewers except where target discovery or plot execution
  needs an integration point.
- Moving package/domain previewer logic into core for convenience.
- Treating plot jobs as `Block` subclasses, workflow nodes, scheduler jobs, or
  downstream data producers.
- Adding direct workflow YAML edits to plot tooling.
- Teaching agents to bind plots by block label alone. ADR-048 requires workflow
  path, stable node ID, and output port (`docs/adr/ADR-048.md:406`).
- Broad frontend plot UI work, except schema/API contracts that MCP tools must
  share with the UI/CLI.
- General CodeBlock v2 refactors. SPEC 2 should define only the reuse boundary
  needed for preview-side plot execution.

## Tool Schema Considerations

Common schema rules:

- All tools should be async FastMCP tools with `@mcp.tool(..., tags={...})`.
  Suggested category tag: `category:plot` or `category:authoring` plus a
  plot-specific tag. A new `category:plot` is clearer but requires prompt
  renderer/category tests to accept a fifth category.
- Read-class tools: `list_plot_targets`, `list_plot_examples`,
  `read_plot_source`, `validate_plot` if validation is non-mutating.
- Write/run-class tools: `scaffold_plot`, `run_plot_job`; both should return
  `next_step`.
- Every path argument must resolve under project root using the existing MCP
  path-safety pattern.
- Result models should avoid absolute local paths where not needed. When paths
  are returned for agent editing, prefer project-relative paths plus optional
  absolute resolved path only if consistent with existing tool envelopes.

Proposed tool contract details:

- `list_plot_targets(workflow_path: str | None = None, include_unavailable: bool = true)`
  returns `targets`, `count`, and maybe `next_step`.
  Each target should include `workflow_path`, `workflow_id`, `node_id`,
  `node_label`, `block_type`, `output_port`, `output_type`, `supports_collection`,
  `latest_run_id`, `latest_output_available`, and diagnostic fields when the
  latest output is missing. It should not require agents to know block names.

- `scaffold_plot(plot_id: str, target: PlotTargetSelector, language: Literal["python","r"], title: str | None = None, overwrite: bool = false)`
  creates `plots/<plot_id>/plot.yaml` plus `render.py` or `render.R`.
  It should return `manifest_path`, `script_path`, `bytes_written`,
  `warnings`, and `next_step`. It should fail rather than overwrite by
  default, mirroring `scaffold_block`.

- `list_plot_examples(language: Literal["python","r"] | None = None, library: str | None = None)`
  returns curated examples for `matplotlib`, `seaborn`, and `ggplot2`.
  Entries should include `id`, `language`, `library`, `title`, `description`,
  `source`, and expected output formats.

- `read_plot_source(plot_id: str | None = None, path: str | None = None)`
  reads an existing plot manifest and script. It should return manifest fields,
  project-relative paths, script language, script source, and validation
  warnings. Require exactly one of `plot_id` or `path`.

- `validate_plot(plot_id: str | None = None, path: str | None = None)`
  validates manifest schema, path confinement, language, entrypoint shape,
  target existence, output format declarations, and broken-target state.
  It should return `valid`, `errors`, `warnings`, normalized manifest payload,
  and a `next_step` pointing to `run_plot_job` when valid.

- `run_plot_job(plot_id: str, run_id: str | None = None, timeout_seconds: float | None = None)`
  executes against the latest available target collection unless `run_id` is
  supplied. It should return `status`, `returncode`, `artifact_paths`,
  `metadata_path`, `logs` or truncated `stdout`/`stderr`, `warnings`, `errors`,
  `cache_key`, and `next_step`. It must enforce ADR-048 constraints:
  preview-only output, timeout, output-size caps, cancellation/error isolation,
  sanitized errors, and current-overwrite cache behavior
  (`docs/adr/ADR-048.md:291`, `docs/adr/ADR-048.md:380`).

## Test Impact

Likely updates:

- MCP catalog count/name tests must add six plot tools and possibly a new
  category. Current tests assert exactly 27 tools
  (`tests/ai/test_mcp_fastmcp.py:78`,
  `tests/integration/test_phase2_mcp_end_to_end.py:79`).
- `tests/ai/test_system_prompt.py` should assert rendered prompts include the
  plot tools and that the base skill static fallback names them.
- Skill packaging tests must change from five task skills to six and verify
  `scistudio-write-plot/SKILL.md` is loadable and indexed
  (`tests/packaging/test_wheel_skills.py:18`).
- Provisioning tests must expect 14 project-installed skill files instead of
  12 if the base plus six task skills install to both providers
  (`tests/agent_provisioning/test_skills.py:19`).
- CLI install tests should verify flat sibling installation/removal includes
  `scistudio-write-plot` (`tests/cli/test_install.py:349`).

Likely new tests:

- `tests/ai/test_mcp_tools_plot.py` for tool unit tests:
  target listing, scaffold file creation, duplicate/overwrite behavior, example
  listing, source read, validation success/failure, path traversal rejection,
  broken target diagnostics, and run result envelope shape.
- Plot manifest/schema tests for invalid language, invalid entrypoint, missing
  workflow, missing node/output, unsupported output format, and duplicate plot
  IDs.
- Plot execution tests for Python matplotlib/seaborn happy path and sanitized
  failure path. R ggplot2 should be either optional/skip-if-unavailable or use a
  mocked runner unless CI guarantees R.
- Cache tests for `.scistudio/previews/<workflow_id>/<node_id>/<output_port>/<plot_id>/current.*`
  and `current.json` overwrite semantics.
- Integration tests ensuring a plot run does not alter workflow YAML, scheduler
  state, data lineage, or downstream outputs.
- If CodeBlock runner reuse is implemented, tests around runner selection,
  timeout propagation, stdout/stderr truncation, and project-local cwd should
  live near `tests/blocks/code/` or in plot-specific tests with mocks.

## Open Questions

- Where will the companion SPEC 2 live: SpecKit `specs/[###-*]/spec.md` or a
  legacy `docs/specs/adr-048-ai-plot-tools.md` file?
- Should plot MCP tools be a fifth MCP category (`plot`) or part of
  `authoring`? A fifth category is semantically cleaner but touches prompt
  rendering/category assumptions.
- What source of truth should `list_plot_targets` use for "latest output":
  live `workflow_runs`, persisted metadata/lineage, or a previewer/plot-target
  index introduced by SPEC 1?
- Does `run_plot_job` reuse CodeBlock backend primitives directly, or does it
  define a plot-runner adapter that borrows only subprocess/interpreter
  helpers?
- Should R support be hard-required in CI, optional with skip behavior, or
  validated by mocked runner tests plus manual verification?
- Should plot manifests allow multiple scripts/artifacts per plot or exactly
  one entrypoint per plot directory for the first spec?
- Should returned artifact paths be absolute, project-relative, preview-cache
  relative, or opaque artifact refs?

## Recommended Spec Requirements

- Define a `PlotTarget` model with stable workflow path, node ID, output port,
  output type, latest availability, and diagnostic fields. Human labels should
  be display-only.
- Define `plot.yaml` as a strict schema with `id`, `title`, `target`,
  `script`, `outputs`, and optional `runtime`/`limits` fields.
- Require `list_plot_targets` before `scaffold_plot`, mirroring the spirit of
  `list_blocks` before `scaffold_block` without borrowing block-reuse logic.
- Require `scaffold_plot` to create only `plots/<plot_id>/plot.yaml` and a
  language-specific render script. It must not edit workflows or blocks.
- Require `validate_plot` and `run_plot_job` before an agent may declare a plot
  ready.
- Require write/run result envelopes to include `next_step`; require scaffold
  and validation results to include `warnings`.
- Require project-root path confinement for all manifest/script reads and
  writes.
- Define preview-cache output and `current.json` metadata fields exactly, with
  current-overwrite semantics from ADR-048.
- Define timeout, output-size cap, stdout/stderr truncation, sanitized error,
  and cancellation semantics for `run_plot_job`.
- Add `scistudio-write-plot` to packaged skills, base skill index, static tool
  catalog fallback, provisioning, external CLI install docs, and all hard-coded
  skill/tool count tests.
- Keep plot tooling separate from block authoring docs. Documentation may link
  to block-development concepts, but must state that plot jobs are preview-only
  and not workflow blocks.
