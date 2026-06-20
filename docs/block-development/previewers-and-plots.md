---
doc_type: block-development
title: "Previewers and Plot Jobs"
status: living
owner: "@jiazhenz026"
last_updated: 2026-06-10
governed_by:
  - ADR-048
summary: "ADR-048 author guide for package and project previewers (PreviewerSpec, PreviewDataAccess, backend providers, same-origin frontend manifests, routing precedence) and preview-side plot jobs (plot.yaml, Python/R render templates, target binding, preview cache, validation/run, export/save)."
---

# Previewers and Plot Jobs

ADR-048 adds two author-facing extension surfaces to SciStudio:

1. **Previewers** — a package or a project can register a full interactive
   previewer for a data type without moving domain UI into core.
2. **Plot jobs** — a user or AI assistant can attach a preview-only
   matplotlib / seaborn / ggplot2 figure to one block output port.

Both are *display* surfaces. Neither becomes a workflow block, a DAG node, a
lineage output, or a downstream Collection. The governing design is
[ADR-048](../adr/ADR-048.md) with two companion specs:
[`adr-048-preview-system`](../specs/adr-048-preview-system.md) (previewers) and
[`adr-048-ai-plot-tools`](../specs/adr-048-ai-plot-tools.md) (plot jobs). This
page is the author guide; those specs are the contract.

---

## Table of Contents

1. [The preview model](#the-preview-model)
2. [PreviewerSpec — declaring a previewer](#previewerspec-declaring-a-previewer)
3. [The backend provider](#the-backend-provider)
4. [PreviewDataAccess — bounded reads](#previewdataaccess-bounded-reads)
5. [The frontend manifest and same-origin assets](#the-frontend-manifest-and-same-origin-assets)
6. [Routing precedence](#routing-precedence)
7. [Package previewers](#package-previewers)
8. [Project previewers and project defaults](#project-previewers-and-project-defaults)
9. [Core fallback previewers](#core-fallback-previewers)
10. [Plot jobs are preview-only](#plot-jobs-are-preview-only)
11. [plot.yaml — the plot manifest](#plotyaml-the-plot-manifest)
12. [The render contract (Python and R)](#the-render-contract-python-and-r)
13. [Target binding](#target-binding)
14. [Validate and run](#validate-and-run)
15. [The preview cache, export, and save](#the-preview-cache-export-and-save)
16. [The AI plot path](#the-ai-plot-path)

---

## The preview model

A preview answers "what does this data ref look like?" without materialising the
full object. The runtime resolves a `PreviewTarget` (a data ref, collection ref,
artifact, or plot artifact plus its recorded type chain) to exactly one
previewer, runs that previewer's **backend provider** to produce a bounded
`PreviewEnvelope`, and the frontend `PreviewHost` mounts the previewer's
**frontend module** to render it.

Three tiers register previewers, in precedence order:

| Tier | Owner | Registered by |
|------|-------|---------------|
| Project | `OwnerKind.PROJECT` | `<project>/previewers/*.py` drop-ins + `.scistudio/previewers.json` |
| Package | `OwnerKind.PACKAGE` | the `scistudio.previewers` entry point |
| Core | `OwnerKind.CORE` | always loaded; generic fallbacks shipped with SciStudio |

Previewers are the **third extension entry point**, distinct from
`scistudio.blocks` (processing logic) and `scistudio.types` (semantic data
types). See [Publishing](publishing.md#the-three-entry-point-groups) and
[Custom Types](custom-types.md#types-vs-previewers) for the boundary.

---

## PreviewerSpec — declaring a previewer

A previewer is declared as a frozen `PreviewerSpec`
(`scistudio.previewers.models`). The spec holds *only metadata plus a provider
reference* — no provider instance, no UI code:

```python
from scistudio.previewers.models import (
    FrontendManifest,
    OwnerKind,
    PreviewerSpec,
)

spec = PreviewerSpec(
    previewer_id="imaging.image.viewer",   # stable, owner-namespaced id
    owner_kind=OwnerKind.PACKAGE,           # core / package / project
    owner_name="scistudio-blocks-imaging",
    target_type="Image",                    # the type name this previewer claims
    supports_collection=False,              # True => claims Collection[Image]
    priority=100,                           # higher wins within one tier+specificity
    capabilities=("slice", "lut", "range", "zoom", "metadata", "export"),
    backend_provider=image_provider,        # a callable OR a "module:callable" path
    frontend_manifest=FrontendManifest(...),  # optional same-origin UI descriptor
)
```

Field notes:

- `previewer_id` must be unique across all loaded specs. A duplicate id is
  recorded as a diagnostic and the later registration is rejected.
- `target_type` is the most-specific type name the previewer claims, e.g.
  `"Image"`. The router also offers it for any ancestor of a target's type chain
  (parent fallback) — see [routing precedence](#routing-precedence).
- `backend_provider` is either a `PreviewProvider` callable or a dotted
  `"module:callable"` import path resolved lazily.
- `frontend_manifest` is optional. A backend-only previewer (no custom UI) omits
  it and relies on a core renderer for the envelope's `kind`.

---

## The backend provider

A backend provider is any callable mapping a `PreviewRequest` to a
`PreviewEnvelope`:

```python
PreviewProvider = Callable[[PreviewRequest], PreviewEnvelope]
```

Providers **must not raise for routine failures** (missing slot, decode error).
Return a typed *error envelope* instead so the session API never crashes
(FR-028); the session manager still wraps the call defensively for unexpected
exceptions.

```python
from scistudio.previewers.models import (
    EnvelopeKind,
    PreviewEnvelope,
    PreviewMetadata,
    PreviewRequest,
)


def array_thumbnail_provider(request: PreviewRequest) -> PreviewEnvelope:
    ref = _ref_for(request)                  # build a StorageReference from query['_storage']
    plane = request.data_access.array_plane(ref, slice_index=0)  # BOUNDED read
    src = request.data_access.png_data_uri(plane.matrix)
    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.ARRAY,
        payload={"shape": plane.shape, "dtype": plane.dtype, "src": src},
        metadata=PreviewMetadata(
            sampled=plane.truncated,
            truncated=plane.truncated,
            complete=not plane.truncated,
        ),
    )
```

Every envelope carries a `PreviewMetadata` with six mandatory display flags —
`sampled`, `truncated`, `cached`, `derived`, `complete`, `failed` — so the UI
can honestly state "showing 200 of N rows" or "preview failed". Put
previewer-owned shape/type/axis details in `metadata.extra`.

The `EnvelopeKind` is one of `dataframe`, `array`, `series`, `text`, `artifact`,
`composite`, `collection`, `plot`, `error`. Choosing a kind that a core
renderer understands (e.g. `array`) lets the host **degrade cleanly** to the
core renderer if your packaged frontend module fails to load.

---

## PreviewDataAccess — bounded reads

`request.data_access` is a `PreviewDataAccess` and is the **only** surface a
provider may use to read payload bytes. Every method enforces a row / byte /
item / tile / dimension budget so a preview of a multi-GB Zarr / TIFF / Parquet
never materialises the whole object (FR-009 / FR-010):

| Method | Returns | Budget |
|--------|---------|--------|
| `dataframe_page(ref, page=, page_size=, sort_by=, sort_dir=)` | `DataFramePage` | `max_rows` |
| `array_plane(ref, slice_index=)` | `ArrayPlane` (one downsampled 2-D plane + axes) | `max_dim` |
| `array_tile(ref, slice_index=, y0=, x0=, height=, width=)` | `ArrayTile` | `max_tile` |
| `series_points(ref, metadata)` | `SeriesPoints` (decimated) | `series_points` |
| `text_chunk(ref)` | `TextChunk` | `text_chars` |
| `artifact_metadata(ref, mime_type=)` | `ArtifactInfo` (small images inline as data URI) | `max_bytes` |
| `composite_slots(metadata)` | `CompositeSlots` (slot inventory, no child render) | — |
| `collection_sample(count=, item_type=, items=)` | `CollectionSample` | `max_items` |
| `png_data_uri(matrix)` | grayscale PNG data URI | — |

Never construct your own storage reads. A provider that bypasses
`PreviewDataAccess` can OOM the backend and breaks the bounded-preview contract.

---

## The frontend manifest and same-origin assets

A previewer that ships custom UI declares a `FrontendManifest`. The frontend
`PreviewHost` dynamically imports the declared ES module at runtime and mounts
its exported component:

```python
from scistudio.previewers.models import PREVIEWER_API_VERSION, FrontendManifest

FrontendManifest(
    previewer_id="imaging.image.viewer",
    module_url="/api/previews/assets/imaging.image.viewer/viewer.js",  # SAME-ORIGIN, backend-relative
    export_name="default",
    css=(),
    version="0.1.0",                       # bump when the bundle changes (cache-bust)
    api_version=PREVIEWER_API_VERSION,     # "1"; a mismatch mounts with a diagnostic
    asset_root="/abs/path/to/package/assets",  # backend-only; never serialised
)
```

Same-origin rules (FR-022 / FR-024):

- `module_url` must be a **backend-relative**, same-origin URL. Remote
  (`http`/`https`/protocol-relative) URLs are rejected by the asset validator.
- `asset_root` is the filesystem directory the backend path-confines reads
  under. It is **never** serialised to the frontend.
- The frontend mounts inside a sandboxed `<iframe>`; the packaged module reads
  everything through the constrained host API
  (`host.envelope.payload`, `host.session.patchQuery` / `getResource`,
  `host.exportArtifact`). No remote code, no workflow mutation.
- The packaged module's contract is
  `export default { apiVersion, mount(container, host) }`.

Because the session envelope does not otherwise carry the manifest, providers
embed the wire manifest (the `to_dict()` shape, without `asset_root`) into
`metadata.extra["frontend_manifest"]` so the host can locate the module.

Project-local React build tooling is intentionally **not** auto-loaded — only
backend Python providers plus path-confined same-origin assets are wired.

---

## Routing precedence

`PreviewRouter` resolves a target to exactly one spec by walking the precedence
order (highest first):

1. project exact `Collection[T]`
2. project exact `T`
3. package exact `Collection[T]`
4. package exact `T`
5. project parent (closest ancestor in the type chain first)
6. package parent (closest ancestor first)
7. core collection fallback
8. core base fallback
9. unknown → `UnknownTargetError`

"Exact" means the spec's `target_type` equals the target's most-specific
recorded type; "parent" means it equals an ancestor in the type chain, closer
ancestors preferred. Within one tier + specificity, the highest `priority` wins.
An unresolved priority tie raises `RoutingAmbiguityError` — unless a project
default declaration breaks it (next section).

The practical consequence for type authors: **give your data type a concrete
type chain**. A target with `type_chain = ["DataObject", "Array", "Image"]`
routes to an `Image` previewer, then an `Array` previewer, then the core base
fallback. A type that records only `DataObject` can only ever hit the core base
fallback. This is the same reason block ports should use concrete types
([Block Contract](block-contract.md#concrete-accepted-types-by-default)).

---

## Package previewers

A package registers previewers through the `scistudio.previewers` entry point.
The callable returns `list[PreviewerSpec]`:

```toml
# pyproject.toml
[project.entry-points."scistudio.previewers"]
imaging = "scistudio_blocks_imaging.previewers:get_previewers"
```

```python
# scistudio_blocks_imaging/previewers/__init__.py
from scistudio.previewers.models import OwnerKind, PreviewerSpec


def get_previewers() -> list[PreviewerSpec]:
    return [
        PreviewerSpec(
            previewer_id="imaging.image.viewer",
            owner_kind=OwnerKind.PACKAGE,
            owner_name="scistudio-blocks-imaging",
            target_type="Image",
            priority=100,                 # > 0 so it wins over the core Array fallback
            backend_provider=image_provider,
            frontend_manifest=_frontend_manifest("imaging.image.viewer"),
        ),
        # ... Label previewer ...
    ]
```

For development inside this monorepo, the registry also discovers a module-level
`get_previewers()` re-exported from a `packages/scistudio-blocks-*` package's
top-level `__init__` (the same dev fallback used for `get_blocks` / `get_types`,
gated by `SCISTUDIO_DEV=1`). Installed entry points remain authoritative.

The worked reference is
[`packages/scistudio-blocks-imaging/README.md`](../../packages/scistudio-blocks-imaging/README.md#package-owned-imagelabel-previewers-adr-048-spec-1):
imaging owns the `Image` and `Label` domain previewers; core owns only the
generic numeric `Array` fallback.

---

## Project previewers and project defaults

A project can register project-local previewers without installing a package
(`scistudio.previewers.project`). Two discovery surfaces:

- **`<project>/previewers/*.py`** — a drop-in module exposing a module-level
  `get_previewers() -> list[PreviewerSpec]`, exactly the package protocol. Each
  spec must declare `owner_kind=OwnerKind.PROJECT`.
- **`<project>/.scistudio/previewers.json`** — a declarative manifest that
  declares **default previewers** for a target type:

```json
{
  "default_previewers": {
    "Image": "myproject.image.custom"
  }
}
```

A project default resolves an otherwise-ambiguous project-tier priority tie
(FR-005): if two project previewers tie on tier + specificity + priority for a
type, the one named in `default_previewers` wins instead of raising
`RoutingAmbiguityError`. Backend provider code is referenced by a
`module:callable` import path resolved lazily from a project-local `previewers/`
directory placed on `sys.path`.

---

## Core fallback previewers

Core always ships generic fallbacks so any target renders even with no package
or project previewer (`scistudio.previewers.fallbacks`):

| Previewer id | Target | Notes |
|---|---|---|
| `core.dataframe.basic` | `DataFrame` | bounded page |
| `core.array.basic` | `Array` | **generic numeric only** — no LUT / OME / channel / label semantics |
| `core.series.basic` | `Series` | chart + table |
| `core.text.basic` | `Text` | bounded chunk |
| `core.artifact.basic` | `Artifact` | metadata + small inline image |
| `core.composite.basic` | `CompositeData` | slot inventory |
| `core.collection.basic` | `Collection` (tier-7) | bounded item sample |
| `core.plot.basic` | plot artifact | renders PNG / JPEG / SVG / PDF (the `PlotPreviewer`) |
| `core.base.fallback` | `DataObject` (tier-8) | universal catch-all |

Core deliberately owns **only** the generic numeric `Array` viewer. Rich
image-domain behaviour (LUT colormaps, display range, slice slider, zoom/pan,
OME/channel metadata) is package-owned by `scistudio-blocks-imaging`. When you
add a domain type, ship a domain previewer rather than expecting core to render
it well.

---

## Plot jobs are preview-only

A **plot job** is a preview-only figure bound to one block output port. It lives
in `<project>/plots/<plot_id>/`, renders a display-only artifact, and shows
through the core `PlotPreviewer` in the preview panel.

A plot job is **not** a workflow block, **not** a DAG node, and produces **no**
lineage or downstream data:

- It never appears in the workflow YAML.
- It never becomes a node in the workflow graph.
- Re-running it overwrites the cached artifact; it never appends to lineage.
- To author reusable *processing* logic instead, write a block
  ([Quickstart](quickstart.md), `scistudio-write-block`). To add an existing
  block as a workflow node, edit the workflow (`scistudio-build-workflow`).

---

## plot.yaml — the plot manifest

Each plot job has a strict, versioned `plots/<plot_id>/plot.yaml`. Its binding
identity is `target.node_id` + `target.output_port`; `display_label` is metadata
only.

```yaml
schema_version: 1
id: cell_scatter
title: Cell Scatter
target:
  workflow_path: workflows/main.yaml
  workflow_id: main
  node_id: node_8f3a2c          # the binding key — never a label
  output_port: measurements
  display_label: Segment Cells / measurements
script:
  language: python              # or r
  path: render.py               # render.R for R
  entrypoint: render            # must be "render"
outputs:
  preferred_format: svg
  allowed_formats: [svg, pdf, png, jpeg]
runtime:
  timeout_seconds: 30
limits:
  max_input_bytes: 67108864
  max_output_bytes: 10485760    # 10 MiB
  max_files: 8
```

The manifest is validated against a closed schema (`extra="forbid"`). The
runtime always re-clamps `runtime` / `limits` to absolute ceilings, so a
hand-edited manifest cannot raise the caps beyond the safe envelope
(timeout ≤ 300 s, output ≤ 64 MiB, files ≤ 32).

---

## The render contract (Python and R)

The render script exposes a single context-free entry point. `context` is not a
plot authoring API.

**Python** - `render(collection)`:

```python
def render(collection):
    import matplotlib.pyplot as plt

    df = collection.items.open_one()
    fig, ax = plt.subplots()
    ax.scatter(df["x"], df["y"], s=6)
    return fig
```

**R** - `render <- function(collection)`:

```r
render <- function(collection) {
  df <- collection$items$open_one()
  ggplot2::ggplot(df, ggplot2::aes(x = x, y = y)) +
    ggplot2::geom_point()
}
```

Python collection helpers:

| API | Result |
|---|---|
| `collection.types` | `tuple[str, ...]` of normalized core base types. |
| `collection.items` | Sequence-like item wrapper. |
| `len(collection.items)` | Number of items. |
| `for item in collection.items` | Iterate item wrappers. |
| `collection.items[index]` | One item wrapper. |
| `collection.items[start:stop]` | List of item wrappers. |
| `collection.items.open()` | List of native Python values. |
| `collection.items.open(max_items=n)` | List of at most `n` native Python values. |
| `collection.items.open_one()` | First native Python value. |
| `item.type` | One normalized core base type name. |
| `item.metadata` | Read-only non-storage metadata mapping. |
| `item.open()` | One native Python value. |

R collection helpers:

| API | Result |
|---|---|
| `collection$types` | Character vector of normalized core base types. |
| `collection$items` | Sequence-like item wrapper. |
| `length(collection$items)` | Number of items. |
| `collection$items[[index]]` | One item wrapper. |
| `collection$items$open()` | List of native R values. |
| `collection$items$open(max_items = n)` | List of at most `n` native R values. |
| `collection$items$open_one()` | First native R value. |
| `collection$items[[index]]$type` | One normalized core base type name. |
| `collection$items[[index]]$metadata` | Non-storage metadata list. |
| `collection$items[[index]]$open()` | One native R value. |

Native conversion table:

| Core base type | Python `open()` result | R `open()` result |
|---|---|---|
| `Array` | `numpy.ndarray` | `matrix` for 2-D data, `array` otherwise |
| `DataFrame` | `pandas.DataFrame` | `data.frame` |
| `Series` | `pandas.Series` | atomic vector |
| `Text` | `str` | character scalar |
| `Artifact` | `pathlib.Path` | character scalar path |
| `CompositeData` | `dict[str, native]` recursively | named list recursively |

Package-defined subclasses are folded back to the nearest supported core base
type before user code sees them. For example, package `Image` and `Mask`
subclasses of core `Array` appear as `Array` and open as arrays.

`open()` is explicit materialization, not lazy loading. Before reading, it uses
metadata or storage size to enforce the plot input memory cap. If the input is
too large, `open()` fails and the user should write an explicit storage-aware
reader for that plot.

R plots do not require the R `arrow` package. The R harness reads base formats
(csv/tsv/txt/json) only, so DataFrame/Series stored as parquet and Array stored
as npy/npz/zarr — the runtime defaults — are transparently converted to CSV
before R runs and the harness reads the CSV copy. The conversion is preview-only
and does not touch persisted storage; Python plots read the original storage
directly. Values round-trip through CSV, so rely on column names and numeric
content rather than exact binary dtype fidelity in R render code.

seaborn works when the project environment provides it; ggplot2 works when R +
ggplot2 are installed. Only `svg`, `pdf`, `png`, `jpeg` are accepted output
formats.

---

## Target binding

Bind a plot to a stable **workflow path + node id + output port**, never to a
human block label. Block labels repeat and drift; the binding key is
`node_id` + `output_port`. Discover targets first (the AI path uses
`list_plot_targets`, which returns an opaque, stable `target_id` derived from
`workflow_path` + `node_id` + `output_port`, so repeated blocks with identical
labels still resolve to distinct targets).

---

## Validate and run

Validate the manifest and script before running. Validation catches broken
targets, schema errors, path traversal, bad output formats, and a missing
`render` entrypoint. R-runner unavailability is a **warning**, not an error, so
CI that skips real R execution still validates the manifest.

Running renders the figure preview-side in a bounded subprocess and writes the
artifacts to the preview cache. The run record reports a status of `succeeded`,
`failed`, `cancelled`, or `timed_out`, with truncated, sanitized stdout/stderr.

---

## The preview cache, export, and save

`run_plot_job` writes display-only artifacts to the preview cache:

```
.scistudio/previews/<workflow_id>/<node_id>/<output_port>/<plot_id>/
    current.svg        # (or current.png / current.pdf / current.jpeg)
    current.json       # run record: manifest, script hash, target, inputs,
                       # run id, runner, created time, outputs, status, error
```

Re-running overwrites `current.*` and `current.json`. The preview cache is
**not** a scientific result path. To keep a figure, export/save it explicitly —
the cache is overwritten on the next run and is not part of run lineage.

---

## The AI plot path

The `scistudio-write-plot` skill
([`src/scistudio/_skills/scistudio/scistudio-write-plot/SKILL.md`](../../src/scistudio/_skills/scistudio/scistudio-write-plot/SKILL.md))
is the AI authoring path for plot jobs. It teaches the six `category:plot` MCP
tools — `list_plot_targets`, `scaffold_plot`, `list_plot_examples`,
`read_plot_source`, `validate_plot`, `run_plot_job` — and requires the agent to
discover a `target_id` first, then `validate_plot` and `run_plot_job` before
declaring a plot ready. The CLI tool inventory is in
[`docs/cli-integration.md`](../cli-integration.md).
