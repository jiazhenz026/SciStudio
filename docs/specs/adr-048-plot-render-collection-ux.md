---
spec_id: adr-048-plot-render-collection-ux
title: "ADR-048 Plot Render Collection UX Refactor Specification"
status: Draft
feature_branch: feat/1684-plot-render-collection-api
created: 2026-06-18
input: "Owner directive: replace the plot render user API with a context-free collection API, persist the refactor plan as a small spec, and list every user-facing API."
owners:
  - "@jiazhenz026"
related_adrs:
  - 48
related_specs:
  - adr-048-ai-plot-tools
  - adr-048-preview-system
  - adr-048-developer-docs-refresh
scope:
  in:
    - Breaking replacement of the plot render signature from `render(collection, context)` to `render(collection)`.
    - Python and R user-facing collection wrappers for opening plot input data as native scientific objects.
    - Core-base-type normalization for package-defined subclasses before data reaches the user-facing API.
    - Native conversion rules for Array, DataFrame, Series, Text, Artifact, and CompositeData inputs.
    - Return-value-based artifact collection for Python and R plot jobs.
    - Plot scaffold, examples, validation, tests, and human-facing author documentation for the new API.
  out:
    - Any compatibility layer for `render(collection, context)`.
    - User-facing storage format APIs such as `item.format`, backend names, or storage paths.
    - New workflow nodes, scheduler-visible DAG work, downstream collections, or scientific lineage outputs.
    - Package-specific plot APIs for domain subclasses such as Image or Mask.
    - New frontend previewer behavior beyond consuming the existing plot artifact preview path.
governs:
  modules:
    - scistudio.ai.agent.mcp.tools_plot
  contracts:
    - scistudio.ai.agent.mcp.tools_plot.runtime.run_plot_job
    - scistudio.ai.agent.mcp.tools_plot.validation.validate_plot
  entry_points: []
  files:
    - docs/specs/adr-048-plot-render-collection-ux.md
    - docs/specs/adr-048-ai-plot-tools.md
    - docs/block-development/previewers-and-plots.md
    - src/scistudio/ai/agent/mcp/tools_plot/_harness.py
    - src/scistudio/ai/agent/mcp/tools_plot/runtime.py
    - src/scistudio/ai/agent/mcp/tools_plot/validation.py
    - src/scistudio/ai/agent/mcp/tools_plot/scaffold.py
    - src/scistudio/ai/agent/mcp/tools_plot/examples.py
    - src/scistudio/_skills/scistudio/scistudio-write-plot/SKILL.md
tests:
  - tests/ai/test_mcp_tools_plot.py
  - tests/api/test_preview_plot_jobs.py
acceptance_source: manual
language_source: en
---

# ADR-048 Plot Render Collection UX Refactor Specification

## 1. Change Summary

This spec defines a pre-alpha breaking replacement for the preview-side plot
render API. The current API gives user scripts `render(collection, context)`.
The `context` argument is not a user-natural concept and mixes data access,
matplotlib access, and artifact saving into a helper object.

The planned API removes `context` completely. A plot script receives exactly
one SciStudio-provided object:

```python
def render(collection):
    arrays = collection.items.open()

    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    ax.imshow(arrays[0], cmap="gray")
    return fig
```

The new model is:

1. open data from `collection.items`;
2. plot with familiar Python or R libraries;
3. return, or in R draw, a plot artifact.

Because SciStudio is pre-alpha and has no external plot users, the
implementation must not keep a compatibility path for the old two-argument
contract.

## 2. User Scenarios & Testing

### User Story 1 - Python user opens array-like output data (Priority: P1)

As a Python user, I need a collection of package-defined array subclasses to
open as normal NumPy arrays without knowing the package subclass name or storage
format.

Independent Test: Given a collection whose items are package-defined subclasses
of core `Array` and are stored through zarr-backed refs, when a plot script
calls `collection.items.open()`, then it receives `list[numpy.ndarray]`.

Acceptance Scenarios:

1. Given a collection of ten package-defined image-like items, when the script
   reads `collection.types`, then it reports `("Array",)`.
2. Given the same collection, when the script calls `collection.items.open()`,
   then it receives ten `numpy.ndarray` objects.
3. Given one item, when the script calls `collection.items[0].open()`, then it
   receives the first item as one `numpy.ndarray`.

### User Story 2 - Python user opens table output data (Priority: P1)

As a Python user, I need table output data to open as pandas dataframes without
calling a SciStudio context helper.

Independent Test: Given a DataFrame collection, when the script calls
`collection.items.open()`, then it receives `list[pandas.DataFrame]`.

Acceptance Scenarios:

1. Given a DataFrame collection, when `collection.types` is read, then it
   reports `("DataFrame",)`.
2. Given the same collection, when `collection.items.open_one()` is called,
   then it returns the first table as a `pandas.DataFrame`.
3. Given a normal matplotlib figure is returned, when the plot job succeeds,
   then the runtime saves it using the manifest's preferred allowed format.

### User Story 3 - R user opens native output data (Priority: P1)

As an R user, I need the same collection model to open data as R-native objects
and to work with base R plotting or ggplot2.

Independent Test: Given a DataFrame collection, when an R render function calls
`collection$items$open()`, then it receives a list of `data.frame` values.

Acceptance Scenarios:

1. Given a DataFrame collection, when R reads `collection$types`, then it
   reports `c("DataFrame")`.
2. Given a DataFrame item, when R calls `collection$items[[1]]$open()`, then it
   receives a `data.frame`.
3. Given an R render function draws a base R plot to the active device, when
   the plot job succeeds, then the device output is promoted as the plot
   artifact.
4. Given an R render function returns a ggplot object, when the plot job
   succeeds, then the ggplot object is saved as the plot artifact.

### User Story 4 - Old context API is rejected (Priority: P1)

As a maintainer, I need the pre-alpha API to be clean, with no compatibility
branch for an unused public contract.

Independent Test: A script that defines `render(collection, context)` fails
validation before execution.

Acceptance Scenarios:

1. Given a Python script with `def render(collection, context):`, when
   `validate_plot` runs, then it fails with a signature error.
2. Given an R script with `render <- function(collection, context)`, when
   `validate_plot` runs, then it fails with a signature error.
3. Given old `context.to_dataframe`, `context.items`, or `context.save_figure`
   references in scaffold or examples, when docs tests scan the plot docs, then
   the stale references are rejected.

### Edge Cases

- Collection contains zero items.
- Collection contains mixed core base types.
- Item metadata has a package-specific type chain but no supported core base.
- Item storage exists but cannot be read by the native reader.
- Python `render()` returns `None`.
- Python `render()` returns an unsupported object.
- R render returns an unsupported object and does not draw to the active device.
- Returned artifact path escapes the confined plot working directory.
- Render writes too many artifacts or too many bytes.
- `open()` would materialize more input data than the plot runtime memory cap.
- A package subclass has the same leaf name as a core base type.

## 3. Requirements

### Functional Requirements

- FR-001: Python plot scripts must define exactly `render(collection)`.
  `render(collection, context)` is invalid.
- FR-002: R plot scripts must define exactly `render <- function(collection)`.
  A second formal argument is invalid.
- FR-003: No compatibility layer, deprecation warning, fallback call path, or
  automatic migration shim may be implemented for the old context API.
- FR-004: The user-facing `collection` must be a plot-runtime wrapper. It must
  not expose or subclass `scistudio.core.types.collection.Collection`.
- FR-005: The plot runtime must normalize package-defined subclasses to the
  nearest supported SciStudio core base type before exposing type information
  to user scripts.
- FR-006: The supported user-facing core base types are `Array`, `DataFrame`,
  `Series`, `Text`, `Artifact`, and `CompositeData`.
- FR-007: User-facing APIs must not expose storage format or backend details.
  Normal user code must not see `item.format`, backend names, zarr, parquet,
  tiff, CSV, storage refs, or storage paths as helper fields.
- FR-008: Storage backend, storage format, and storage path may remain internal
  reader-dispatch fields and may appear in sanitized error diagnostics when
  needed to debug unreadable data.
- FR-009: The Python collection wrapper must expose exactly the helper surface
  listed in section 3.2 unless a later spec expands it.
- FR-010: The R collection wrapper must expose exactly the helper surface listed
  in section 3.3 unless a later spec expands it.
- FR-011: `collection.types` and `collection$types` must report normalized core
  base type names only.
- FR-012: Item metadata exposed to users must be read-only and must exclude
  storage backend, storage format, and raw storage paths.
- FR-013: Python `open()` conversion must follow the table in section 3.4.
- FR-014: R `open()` conversion must follow the table in section 3.4.
- FR-015: Python `render()` may return a matplotlib figure, a path string, a
  `pathlib.Path`, or a list or tuple containing those supported values.
- FR-016: Python `render()` returning `None` is invalid.
- FR-017: R render may draw to the active graphics device, return a ggplot
  object, return an artifact path string, or return a list of supported plot
  values.
- FR-018: The Python harness must not scan the working directory for arbitrary
  artifacts. Artifacts must come from the render return value.
- FR-019: The R harness may promote the configured active graphics device output
  when the render function draws a base R plot.
- FR-020: Plot jobs must remain preview-only: no workflow YAML edits, no
  scheduler DAG mutation, no downstream collection creation, and no scientific
  lineage output.
- FR-021: Scaffolded Python and R scripts must use the new one-argument render
  API and must contain no `context` references.
- FR-022: Human-facing plot author docs must list every user-facing collection
  helper and every core base type conversion for Python and R.
- FR-023: `item.open()` and collection-level `open()` calls must perform an
  implementation-defined memory guard before materializing data. If the
  estimated or known materialized size exceeds the runtime cap, the call must
  fail with a clear error instead of loading the payload.
- FR-024: This spec must not add lazy-loading, selection, row-window, or
  chunk-iteration helpers to the user API. Users who need to plot data larger
  than the memory guard allows must author their own explicit storage-aware
  reading strategy outside the SciStudio collection helper surface.

### 3.2 Python User-Facing API

The complete Python API is:

| API | Result | Notes |
|---|---|---|
| `render(collection)` | entrypoint | Exactly one argument. |
| `collection.types` | `tuple[str, ...]` | Normalized core base type names only. |
| `collection.items` | `PlotItems` | Sequence-like item wrapper. |
| `len(collection.items)` | `int` | Number of items in the collection. |
| `for item in collection.items` | iterator | Iterates `PlotItem` wrappers. |
| `collection.items[index]` | `PlotItem` | Zero-based item access. |
| `collection.items[start:stop]` | `list[PlotItem]` | Slice access. |
| `collection.items.open()` | `list[Any]` | Opens all items as native Python values. |
| `collection.items.open(max_items=n)` | `list[Any]` | Opens at most `n` items. |
| `collection.items.open_one()` | `Any` | Opens the first item. Fails on empty collection. |
| `item.type` | `str` | One normalized core base type name. |
| `item.metadata` | read-only mapping | Non-storage metadata only. |
| `item.open()` | `Any` | Opens one item as a native Python value. |

No other Python helper is part of this spec. In particular, there is no
`context`, `context.plt`, `context.to_dataframe`, `context.items`,
`context.save_figure`, `item.format`, or `item.path` user API. The `open()`
helpers are explicit materialization calls, not lazy readers. They may fail
before reading when the runtime memory guard predicts an unsafe load.

### 3.3 R User-Facing API

The complete R API is:

| API | Result | Notes |
|---|---|---|
| `render <- function(collection)` | entrypoint | Exactly one argument. |
| `collection$types` | character vector | Normalized core base type names only. |
| `collection$items` | item wrapper object | Sequence-like item wrapper. |
| `length(collection$items)` | integer | Number of items in the collection. |
| `collection$items[[index]]` | item wrapper | One-based R item access. |
| `collection$items$open()` | list | Opens all items as native R values. |
| `collection$items$open(max_items = n)` | list | Opens at most `n` items. |
| `collection$items$open_one()` | native value | Opens the first item. Fails on empty collection. |
| `collection$items[[index]]$type` | character scalar | One normalized core base type name. |
| `collection$items[[index]]$metadata` | named list | Non-storage metadata only. |
| `collection$items[[index]]$open()` | native value | Opens one item as a native R value. |

No other R helper is part of this spec. In particular, there is no `context`,
`context$to_dataframe`, `context$save_plot`, storage-format helper, or raw
storage-path helper. The `open()` helpers are explicit materialization calls,
not lazy readers. They may fail before reading when the runtime memory guard
predicts an unsafe load.

### 3.4 Core Base Type Conversion Table

All package-specific subclasses must be folded back to the nearest supported
core base type before opening.

| Core base type | Python `open()` result | R `open()` result |
|---|---|---|
| `Array` | `numpy.ndarray` | `matrix` for 2-D data, `array` otherwise |
| `DataFrame` | `pandas.DataFrame` | `data.frame` |
| `Series` | `pandas.Series` | atomic vector, named when index labels are available |
| `Text` | `str` | character scalar |
| `Artifact` | `pathlib.Path` | character scalar path |
| `CompositeData` | `dict[str, native]` recursively | named list recursively |
| unsupported `DataObject` | clear error | clear error |

Examples:

- A package-defined `Image` subclass of `Array` opens as `numpy.ndarray` in
  Python and as `matrix` or `array` in R.
- A package-defined `Mask` subclass of `Array` opens as `numpy.ndarray` in
  Python and as `matrix` or `array` in R.
- A package-defined table subclass of `DataFrame` opens as `pandas.DataFrame`
  in Python and as `data.frame` in R.

## 4. Implementation Plan

### 4.1 Technical Approach

`run_plot_job` should write an input envelope that contains internal storage
refs and normalized core base type names. The harness should build wrapper
objects from that envelope and should keep storage details private.

The Python harness should contain:

- `_PlotCollection`
- `_PlotItems`
- `_PlotItem`
- native reader dispatch for supported core base types
- return-value artifact collection

The R harness should contain equivalent collection, items, item, native reader,
and artifact handling objects/functions.

### 4.2 Affected Files

| Path | Action | Rationale |
|---|---|---|
| `src/scistudio/ai/agent/mcp/tools_plot/_harness.py` | modify | Remove context, add Python/R collection wrappers and native readers. |
| `src/scistudio/ai/agent/mcp/tools_plot/runtime.py` | modify | Write normalized input envelope and collect returned artifacts. |
| `src/scistudio/ai/agent/mcp/tools_plot/validation.py` | modify | Enforce one-argument Python/R render signatures. |
| `src/scistudio/ai/agent/mcp/tools_plot/scaffold.py` | modify | Generate context-free Python/R templates. |
| `src/scistudio/ai/agent/mcp/tools_plot/examples.py` | modify | Replace context examples with collection API examples. |
| `src/scistudio/_skills/scistudio/scistudio-write-plot/SKILL.md` | modify | Teach AI agents the new render contract. |
| `docs/block-development/previewers-and-plots.md` | modify | Document the user-facing helper API and conversion table. |
| `tests/ai/test_mcp_tools_plot.py` | modify | Validate signatures, scaffolds, examples, and runtime behavior. |
| `tests/api/test_preview_plot_jobs.py` | modify | Verify preview cache behavior and no workflow mutation. |

### 4.3 Implementation Sequence

1. Add the normalized input envelope in `runtime.py`.
2. Replace `_Collection` and `_Context` in the Python harness with
   `_PlotCollection`, `_PlotItems`, and `_PlotItem`.
3. Add Python native readers for the supported core base types.
4. Replace `context.save_figure` with Python return-value artifact collection.
5. Replace R context construction with R collection wrappers and native readers.
6. Add R graphics-device handling for base R plots and ggplot return handling.
7. Tighten validation so two-argument render functions fail.
8. Rewrite scaffolds, examples, skill guidance, and human-facing docs.
9. Replace old context tests with new one-argument API tests.

### 4.4 Verification Plan

Tests must verify:

- Python `render(collection)` succeeds.
- Python `render(collection, context)` fails validation.
- R `render <- function(collection)` succeeds.
- R `render <- function(collection, context)` fails validation.
- Package-defined `Array` subclasses normalize to `Array`.
- `collection.types` and `collection$types` expose only core base types.
- `collection.items.open()` and `collection$items$open()` return the native
  values listed in section 3.4.
- Storage format and backend are not exposed as user helper fields.
- `open()` refuses payloads that exceed the runtime memory guard and does not
  materialize them.
- Python `None` return fails.
- Python matplotlib figure returns are saved as allowed artifacts.
- R base plots and ggplot returns are saved as allowed artifacts.
- Plot runs remain preview-only and do not mutate workflow YAML, scheduler
  outputs, DAG state, downstream data, or lineage.

### 4.5 Risks And Rollback

The main risk is that the harness duplicates some native read logic already
available in other SciStudio layers. This is acceptable because the plot
subprocess intentionally runs with a narrow user-facing wrapper and should not
expose core runtime objects directly.

Rollback is a normal pre-alpha revert of the new spec and implementation PR.
No compatibility migration is required because the old plot API has no external
user commitment.

## 5. Success Criteria

### Measurable Outcomes

- SC-001: New Python and R plot scaffolds contain no `context` references.
- SC-002: The plot docs include the full Python helper table, R helper table,
  and core base type conversion table from this spec.
- SC-003: A package-defined array subclass collection can be plotted in Python
  with `collection.items.open()` and no storage-format knowledge.
- SC-004: A DataFrame collection can be plotted in R with
  `collection$items$open()` and no context helper.
- SC-005: Validation rejects every two-argument render function fixture.
- SC-006: No test preserves `render(collection, context)` as a valid behavior.
- SC-007: Oversized input fixtures fail at `open()` with a memory-guard error
  before the full payload is materialized.

## 6. Assumptions

- SciStudio is pre-alpha and has no external plot API compatibility obligation.
- Core base types are the user-facing abstraction boundary for plot authoring.
- Package subclasses remain meaningful for routing and internal metadata, but
  they are not the normal plot authoring API.
- Storage backend and format remain implementation details, not user helpers.
