---
spec_id: adr-048-ai-plot-tools
title: "ADR-048 AI Plot Tools, Plot Runtime, And Skill Specification"
status: Planned
feature_branch: codex/adr-048-previewers-plot-jobs
created: 2026-06-10
input: "Owner-approved ADR-048 direction: provide AI-facing MCP tools and a packaged skill for writing preview-side Python/R plot jobs without guessing block names or modifying workflow DAGs."
owners:
  - "@jiazhenz026"
related_adrs:
  - 48
related_specs:
  - adr-048-preview-system
  - adr-048-developer-docs-refresh
scope:
  in:
    - Plot target discovery for workflow output ports using stable workflow path, node ID, and output port identity.
    - "`plots/<plot_id>/plot.yaml` schema and Python/R render script templates."
    - MCP tools for list, scaffold, example, read, validate, and run plot jobs.
    - Preview-side plot execution, cache output, logs, failure isolation, and current-overwrite behavior.
    - Packaged `scistudio-write-plot` skill and AI CLI/provisioning integration.
    - Documentation updates directly required for the AI plot tools and skill.
  out:
    - Type previewer routing and dynamic frontend previewer loading, except for consuming the PlotPreviewer artifact contract from `adr-048-preview-system`.
    - Rewriting all block and package developer docs. That is governed by `adr-048-developer-docs-refresh`.
    - Treating plot jobs as workflow blocks, scheduler DAG nodes, lineage-producing data outputs, or downstream collections.
    - Broad CodeBlock v2 refactors unrelated to preview-side plot execution.
governs:
  modules:
    - scistudio.agent_provisioning
    - scistudio.blocks.code
  contracts: []
  entry_points: []
  files:
    - docs/adr/ADR-048.md
    - docs/specs/adr-048-ai-plot-tools.md
    - src/scistudio/ai/agent/mcp/__init__.py
    - src/scistudio/_skills/scistudio/SKILL.md
    - src/scistudio/agent_provisioning/**
    - src/scistudio/cli/install.py
    - src/scistudio/blocks/code/**
    - docs/cli-integration.md
tests:
  - tests/ai/test_mcp_fastmcp.py
  - tests/ai/test_mcp_tools_plot.py
  - tests/integration/test_phase2_mcp_end_to_end.py
  - tests/ai/test_system_prompt.py
  - tests/packaging/test_wheel_skills.py
  - tests/agent_provisioning/test_skills.py
  - tests/agent_provisioning/test_orchestrate.py
  - tests/cli/test_install.py
  - tests/api/test_preview_plot_jobs.py
acceptance_source: adr
language_source: en
---

# ADR-048 AI Plot Tools, Plot Runtime, And Skill Specification

## 1. Change Summary

This spec implements the plot-job and AI-assistant half of ADR-048. Scientists
often need a quick matplotlib, seaborn, or ggplot2 figure from a block output
collection. That figure should appear in the preview panel, be exportable as a
publication-friendly artifact, and not become workflow DAG work.

The implementation must give AI assistants and users a safe authoring path:

1. discover valid plot targets from the current workflow and latest outputs;
2. scaffold a project-local plot manifest and render script;
3. validate the manifest, script entrypoint, target, and declared outputs;
4. run the plot against the selected output collection;
5. write display-only artifacts to the preview cache;
6. show the result through the core `PlotPreviewer`.

The key UX decision is that users and agents should not hand-type block names.
`list_plot_targets` returns stable target IDs and display labels. A scaffolded
manifest stores workflow path, node ID, and output port. Human block labels are
display metadata only.

## 2. User Scenarios & Testing

### User Story 1 - Agent discovers a target before writing a plot (Priority: P1)

As an AI assistant writing a plot for a user, I need to list valid output
targets so I do not guess a block name or bind to the wrong repeated block.

Independent Test: Create a workflow with two nodes using the same block type and
similar labels; verify `list_plot_targets` returns distinct target IDs with
workflow path, node ID, node label, block type, output port, output type, and
latest output availability.

Acceptance Scenarios:

1. Given two repeated blocks, when `list_plot_targets` runs, then each returned
   target has a unique `target_id` derived from workflow path, node ID, and
   output port.
2. Given a target without latest output data, when `list_plot_targets` runs with
   `include_unavailable=true`, then the target is listed with diagnostics and
   `latest_output_available=false`.
3. Given an agent has only a human block label, when it calls
   `scaffold_plot`, then the tool rejects label-only selection and asks for a
   discovered `target_id` or stable selector.

### User Story 2 - Python plot is scaffolded and run (Priority: P1)

As a scientist, I need an AI assistant to create a matplotlib or seaborn plot
from a block output collection and show it in the preview panel.

Independent Test: Scaffold a Python plot from a fixture target, edit the script
to save SVG, validate it, run it, and verify `.scistudio/previews/.../current.svg`
and `current.json` are produced.

Acceptance Scenarios:

1. Given a valid target ID, when `scaffold_plot` runs with `language=python`,
   then it creates `plots/<plot_id>/plot.yaml` and `render.py`.
2. Given the scaffolded script opens data with `collection.items.open_one()`
   and returns a matplotlib figure, when `run_plot_job` runs, then it returns
   success and an SVG artifact path.
3. Given the plot is rerun, when a new artifact is written, then the
   `current.*` files are overwritten and `current.json` records the new run.

### User Story 3 - R ggplot2 plot is supported (Priority: P1)

As a user with R installed, I need the same plot-job workflow to support
ggplot2 and vector PDF/SVG output.

Independent Test: Scaffold an R plot, validate the entrypoint, run it through an
R-capable runner when available, and verify plot output. In CI environments
without R, runner integration may be skipped with explicit skip reason while
manifest validation remains tested.

Acceptance Scenarios:

1. Given `language=r`, when `scaffold_plot` runs, then it creates `render.R`
   with `render <- function(collection)`.
2. Given R and ggplot2 are available, when `run_plot_job` runs, then it writes a
   PDF, SVG, PNG, or JPEG artifact accepted by `PlotPreviewer`.
3. Given R is unavailable, when validation runs, then it can still validate the
   manifest and report runner unavailability as a run-time diagnostic.

### User Story 4 - Plot failures do not affect workflow state (Priority: P1)

As a workflow author, I need failed exploratory plots to fail only the preview
panel, not the workflow run or downstream data.

Independent Test: Run a plot script that raises an exception; verify the tool
returns sanitized stderr, no workflow YAML is modified, no data lineage record
is created, and existing workflow outputs remain unchanged.

Acceptance Scenarios:

1. Given a plot script raises, when `run_plot_job` finishes, then it returns
   `status=failed` with truncated logs and a sanitized error.
2. Given a failing plot job, when the workflow run history is inspected, then no
   new scheduler node or downstream output exists.
3. Given a failing plot job previously had a successful `current.*` artifact,
   then the implementation records the failure state in `current.json` and does
   not silently display stale success as current.

### User Story 5 - Skill guides AI behavior (Priority: P2)

As a maintainer, I need the packaged `scistudio-write-plot` skill to make the
correct workflow obvious to AI assistants.

Independent Test: Provision project AI assets; verify the skill is installed for
supported agent surfaces, listed in the base SciStudio skill index, and names
the plot MCP tool sequence.

Acceptance Scenarios:

1. Given project provisioning runs, when skills are installed, then
   `scistudio-write-plot/SKILL.md` exists alongside existing task skills.
2. Given the base skill static tool catalog is rendered, when MCP discovery is
   unavailable, then plot tools are still documented in the fallback catalog.
3. Given an agent reads the plot skill, then it is told not to edit workflow DAGs
   and not to bind plots by block label alone.

### Edge Cases

- Plot ID contains path traversal, spaces, reserved names, or collisions.
- `plot.yaml` refers to a deleted workflow, node, or output port.
- Workflow contains repeated labels and repeated block types.
- Latest output exists but is not a collection.
- Latest output is a mixed-type collection.
- Script saves an unsupported extension.
- Script writes multiple artifacts.
- Script writes too many bytes or too many files.
- Python import fails for seaborn.
- R or ggplot2 is unavailable.
- Plot times out or is cancelled.
- stdout or stderr exceeds the log cap.
- User edits script path in the manifest to escape the project root.
- Rerun races with a preview panel trying to read `current.*`.

## 3. Requirements

### Functional Requirements

- FR-001: The implementation must add six MCP tools:
  `list_plot_targets`, `scaffold_plot`, `list_plot_examples`,
  `read_plot_source`, `validate_plot`, and `run_plot_job`.
- FR-002: Plot MCP tools must be registered through FastMCP import side effects
  in the same style as existing MCP tools.
- FR-003: Plot tools must use a plot-specific category or tags so prompts and
  tool catalogs can distinguish plot authoring from block authoring.
- FR-004: All plot file path arguments must be resolved under the project root
  and must reject traversal outside the project.
- FR-005: `list_plot_targets` must return stable target IDs and must include
  workflow path, workflow ID when available, node ID, node label, block type,
  output port, output type, collection support, latest run ID, latest output
  availability, and diagnostics.
- FR-006: Target IDs returned by `list_plot_targets` must be accepted by
  `scaffold_plot` so users and agents do not have to hand-type node IDs.
- FR-007: `scaffold_plot` must create exactly a plot directory containing
  `plot.yaml` and one language-specific render script unless explicitly
  extended by a future spec.
- FR-008: `scaffold_plot` must not overwrite an existing plot unless
  `overwrite=true` is supplied.
- FR-009: `scaffold_plot` must return manifest path, script path, bytes written,
  warnings, and `next_step`.
- FR-010: `plot.yaml` must be strict and versioned with schema version, plot ID,
  title, target, script, outputs, runtime, and limits fields.
- FR-011: The manifest target must store workflow path, stable node ID, and
  output port. Human labels may be stored only as display metadata.
- FR-012: Python render scripts must expose exactly `render(collection)`.
- FR-013: R render scripts must expose exactly `render <- function(collection)`.
- FR-014: Python scripts must open data through the collection helper surface
  and may use familiar libraries such as matplotlib or seaborn directly.
- FR-015: R scripts must open data through the collection helper surface and
  may use familiar libraries such as base R plotting or ggplot2 directly.
- FR-016: Plot scripts must receive the selected block output collection and
  must not receive direct workflow mutation APIs.
- FR-017: Collection helpers must include `collection.items.open()`,
  `collection.items.open_one()`, item indexing, item metadata, and equivalent
  R helpers.
- FR-018: Plot outputs must be produced by returning a matplotlib figure,
  ggplot object, path string, or list of supported return values. R base plots
  may be captured from the active device.
- FR-019: `list_plot_examples` must return curated examples for matplotlib,
  seaborn, and ggplot2.
- FR-020: `read_plot_source` must read either by `plot_id` or manifest path, but
  not both, and must return normalized manifest data plus script source.
- FR-021: `validate_plot` must validate manifest schema, path confinement,
  target existence, output format declarations, script language, entrypoint
  shape, and runner availability diagnostics.
- FR-022: `validate_plot` must return `valid`, `errors`, `warnings`,
  normalized manifest data, and `next_step`.
- FR-023: `run_plot_job` must execute against the latest available target output
  unless a specific compatible run ID is supplied.
- FR-024: `run_plot_job` must reuse existing CodeBlock runner primitives where
  practical for subprocess execution, interpreter resolution, timeout, log
  capture, cancellation, and project-root working directory.
- FR-025: Plot execution must not register workflow nodes, edit workflow YAML,
  create downstream collections, or claim scientific lineage output.
- FR-026: Plot execution must write display-only artifacts to
  `.scistudio/previews/<workflow_id>/<node_id>/<output_port>/<plot_id>/`.
- FR-027: Rerunning a plot must overwrite `current.*` and `current.json`.
- FR-028: `current.json` must record manifest path, script path, script hash,
  target workflow/node/output, input collection IDs, run ID, runner, created
  time, output artifacts, status, and sanitized error state.
- FR-029: `run_plot_job` must enforce timeout, output-size cap, file-count cap,
  stdout/stderr truncation, and sanitized errors.
- FR-030: `run_plot_job` must return status, return code, artifact paths, cache
  key, metadata path, logs or truncated log excerpts, warnings, errors, and
  `next_step`.
- FR-031: Successful plot artifacts must be consumable by the core
  `PlotPreviewer` from `adr-048-preview-system`.
- FR-032: The implementation must add a packaged `scistudio-write-plot` skill
  that instructs agents to discover targets, scaffold, edit, validate, run, and
  report plot artifacts.
- FR-033: Project provisioning and external CLI install must install
  `scistudio-write-plot` wherever other SciStudio task skills are installed.
- FR-034: MCP catalog, system prompt, skill packaging, and provisioning tests
  must be updated for the new plot tools and skill.
- FR-035: The tool workflow must be documented separately from block authoring:
  plot jobs are preview-only artifacts, not reusable block definitions.
- FR-036: When a render returns a figure object, plot execution must render one
  sibling artifact file per manifest `allowed_formats` value up front
  (`current.svg` + `current.pdf` + `current.png` + `current.jpg`), because the
  figure is closed immediately after render and cannot be re-rendered at
  save/export time. The preferred-format file is the canonical preview primary;
  the siblings exist so the previewer's Save/Export can produce a valid file in
  any rendered format. A render that returns an artifact *path* (not a figure)
  stays single-format — the author already chose that format. When the extra
  formats would exceed the output-byte or file-count caps, the run degrades
  gracefully to the preferred format per figure and warns, rather than failing.
- FR-037: The `PlotPreviewer` export resource must resolve the sibling file that
  matches the format the caller requested (via the `format` param derived from
  the user's Save-as choice or destination extension) rather than the primary
  bytes. The PLOT envelope must advertise the rendered formats
  (`payload.available_formats`) so the frontend can offer a Save-as format
  choice. Requesting a format that was not rendered must return a clear error,
  never a corrupt file written under a mismatched extension.

### Key Entities

`PlotTarget`:

| Field | Meaning |
|---|---|
| `target_id` | Opaque stable selector returned by `list_plot_targets`. |
| `workflow_path` | Project-relative workflow file path. |
| `workflow_id` | Stable workflow ID when available. |
| `node_id` | Stable node ID. |
| `node_label` | Human display label only. |
| `block_type` | Block type or package-qualified block ID. |
| `output_port` | Output port name. |
| `output_type` | Recorded output type. |
| `is_collection` | Whether the latest output is a collection. |
| `latest_run_id` | Latest run ID when available. |
| `latest_output_available` | Whether a plot can run immediately. |
| `diagnostics` | Missing-output or broken-target details. |

`plot.yaml`:

```yaml
schema_version: 1
id: cell_scatter
title: Cell Scatter
target:
  workflow_path: workflows/main.yaml
  workflow_id: main
  node_id: node_8f3a2c
  output_port: measurements
  display_label: Segment Cells / measurements
script:
  language: python
  path: render.py
  entrypoint: render
outputs:
  preferred_format: svg
  allowed_formats:
    - svg
    - pdf
    - png
    - jpeg
runtime:
  timeout_seconds: 30
limits:
  max_input_bytes: 67108864
  max_output_bytes: 10485760
  max_files: 8
```

Python template:

```python
def render(collection):
    import matplotlib.pyplot as plt

    df = collection.items.open_one()
    fig, ax = plt.subplots()
    ax.scatter(df["x"], df["y"], s=4)
    return fig
```

R template:

```r
render <- function(collection) {
  df <- collection$items$open_one()
  ggplot2::ggplot(df, ggplot2::aes(x = x, y = y)) +
    ggplot2::geom_point()
}
```

`PlotRunResult`:

| Field | Meaning |
|---|---|
| `status` | `succeeded`, `failed`, `cancelled`, or `timed_out`. |
| `returncode` | Process return code when available. |
| `artifact_paths` | Project-relative or preview-cache-relative artifact paths. |
| `data_ref` | Catalog reference for the first produced artifact when a live preview catalog is available. |
| `recorded_type` | Recorded catalog type for the artifact, normally `PlotArtifact`. |
| `type_chain` | Ordered type chain for routed preview resolution. |
| `preview_target` | PreviewHost-ready `plot_artifact` target when the artifact was registered. |
| `metadata_path` | Path to `current.json`. |
| `cache_key` | Preview cache key for UI refresh. |
| `stdout` | Truncated stdout. |
| `stderr` | Truncated stderr. |
| `warnings` | Non-fatal diagnostics. |
| `errors` | Fatal diagnostics. |
| `next_step` | Suggested next tool or UI action. |

## 4. Implementation Plan

### 4.1 Technical Approach

Implement plot tooling as a new MCP tool package plus a small runtime layer for
plot manifests and preview-side execution. The runtime layer should be usable by
MCP tools, future UI actions, and tests. It should borrow CodeBlock runner
mechanics where that reduces duplication, but it must not reuse CodeBlock in a
way that creates a workflow block or scheduler node.

The recommended package layout is:

| Module | Role |
|---|---|
| `tools_plot/__init__.py` | Registration side effects and public re-exports. |
| `tools_plot/models.py` | Pydantic result and manifest models. |
| `tools_plot/targets.py` | Target discovery and target ID normalization. |
| `tools_plot/scaffold.py` | Templates and file creation. |
| `tools_plot/validation.py` | Manifest, target, entrypoint, and runner checks. |
| `tools_plot/runtime.py` | Preview-side execution and cache writes. |
| `tools_plot/examples.py` | Curated example catalog. |

### 4.2 Affected Files

MCP and runtime:

- Add `src/scistudio/ai/agent/mcp/tools_plot/**`.
- Update `src/scistudio/ai/agent/mcp/__init__.py` to import plot tools for
  FastMCP registration.
- Update `src/scistudio/ai/agent/mcp/server.py` only if tool category rendering
  must recognize `category:plot`.
- Update `src/scistudio/ai/agent/mcp/_context.py` only if target discovery
  needs a narrow project/workflow context protocol.
- Reuse or adapt `src/scistudio/blocks/code/**` runner helpers without changing
  CodeBlock DAG semantics.
- Consume `src/scistudio/previewers/**` only for preview cache conventions and
  `PlotPreviewer` artifact metadata.

Skills and provisioning:

- Add `src/scistudio/_skills/scistudio/scistudio-write-plot/SKILL.md`.
- Update `src/scistudio/_skills/scistudio/SKILL.md`.
- Update `src/scistudio/agent_provisioning/skills.py`.
- Update `src/scistudio/agent_provisioning/_orchestrate.py` if expected skill
  counts or messages are pinned.
- Update `src/scistudio/cli/install.py` if flat skill install or reporting is
  name-aware.
- Update `pyproject.toml` only if non-Markdown templates or assets are added
  outside the existing package-data glob.

Documentation:

- Update `docs/cli-integration.md` for the new skill and tool inventory.
- Defer broad block/package author docs to
  `adr-048-developer-docs-refresh`.

### 4.3 Implementation Sequence

1. Add manifest and result Pydantic models with schema tests.
2. Add target discovery using current workflow graph and latest output metadata.
3. Add deterministic `target_id` generation and parser tests.
4. Add Python and R scaffold templates and overwrite/path-safety tests.
5. Add example catalog for matplotlib, seaborn, and ggplot2.
6. Add manifest/source read and validation tools.
7. Add plot runtime wrapper using project-root confinement and CodeBlock runner
   helpers where practical.
8. Add preview cache write and `current.json` metadata behavior.
9. Register all MCP tools and update tool catalog tests.
10. Add `scistudio-write-plot` and provisioning/install tests.
11. Add docs updates and manual smoke scenario.

### 4.4 Verification Plan

Unit tests:

- plot ID normalization and path traversal rejection;
- target ID uniqueness for repeated labels and repeated block types;
- scaffold creates exact expected files and refuses overwrite by default;
- read requires exactly one of `plot_id` or `path`;
- validation errors for missing manifest fields, broken target, unsupported
  format, invalid language, invalid entrypoint, and escaping script path;
- Python run success with SVG output;
- Python run failure with sanitized logs;
- timeout and output-size cap behavior;
- R manifest validation always, R execution skip-if-unavailable or mocked when
  CI lacks R.

MCP tests:

- FastMCP lists the six plot tools;
- tool schemas expose required arguments;
- write/run tools return `next_step`;
- transport integration can call at least one read-class and one write-class
  plot tool.

Skill and packaging tests:

- wheel includes `scistudio-write-plot/SKILL.md`;
- project provisioning installs the skill;
- CLI install installs/removes the skill with the rest of SciStudio skills;
- system prompt/static catalog mentions plot tools.

Runtime integration tests:

- plot run writes `current.*` and `current.json`;
- rerun overwrites current files;
- failed rerun records failure state;
- no workflow YAML, scheduler state, lineage output, or downstream collection
  changes are produced by plot execution.

### 4.5 Risks And Rollback

Risk: Agents may confuse plot jobs with workflow blocks.

Mitigation: Tool names, result messages, and the `scistudio-write-plot` skill
must repeatedly state that plot jobs are preview-only. Rollback by disabling
`run_plot_job` while keeping scaffold/validate available.

Risk: R support is environment-dependent.

Mitigation: Validate R manifests everywhere, run R integration tests only when R
and ggplot2 are available or through mocked runner coverage, and return clear
runner diagnostics.

Risk: Plot scripts can write large or unexpected files.

Mitigation: Use a confined working directory, output allowlist, max file count,
max bytes, timeout, and artifact extension checks before exposing outputs.

Risk: Target discovery source of truth may lag behind workflow execution
metadata.

Mitigation: Return diagnostics and availability flags. Do not let scaffolded
manifests imply an output exists until validation or run confirms it.

## 5. Success Criteria

### Measurable Outcomes

- SC-001: `mcp.list_tools()` includes all six plot tools with plot-specific
  category/tag metadata.
- SC-002: `list_plot_targets` distinguishes repeated block labels by stable
  target IDs.
- SC-003: `scaffold_plot` creates valid Python and R plot directories and
  refuses accidental overwrite.
- SC-004: `validate_plot` catches broken targets, invalid manifests, path
  traversal, unsupported output formats, and missing entrypoints.
- SC-005: `run_plot_job` writes current-overwrite preview artifacts and
  metadata without mutating workflow DAG or lineage state.
- SC-006: Python matplotlib SVG output is tested end to end.
- SC-007: R ggplot2 support is validated through either real runner tests in an
  R-enabled environment or explicit mocked/skip-if-unavailable coverage.
- SC-008: `scistudio-write-plot` is packaged, provisioned, installed by the CLI,
  and referenced by the base SciStudio skill.
- SC-009: Tool count, prompt rendering, packaging, and provisioning tests are
  updated for the new skill and tools.
- SC-010: Plot artifacts produced by the runtime can be displayed by the
  `PlotPreviewer` from the preview system spec.

## 6. Assumptions

- Workflow output metadata can provide stable node IDs and output port names for
  target discovery.
- The initial plot manifest model supports one entrypoint script per plot
  directory.
- Python plotting support relies on the project/runtime Python environment.
- R execution may be optional in CI but must be supported by the runtime when R
  and required packages are available.
- Preview cache paths are not scientific result paths; users must explicitly
  save or export plot artifacts they want to keep. A figure is rendered to every
  manifest-allowed format up front so an explicit save can produce a valid file
  in the user's chosen format without re-rendering (the figure is already
  closed); see FR-036 / FR-037.
