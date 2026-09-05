# Examples

One worked example per shape. Each folder has the artifact — a block `.py` file,
a script, a panel document, or a notebook — and a short `README.md` that walks
through it. Copy a folder into your project and edit from there.

## Blocks

Copy into your project's `blocks/`.

| Folder | Base class | What it shows |
|---|---|---|
| [process-scale-array/](process-scale-array/) | `ProcessBlock` / `Block` | Per-item transform over a batch; reading a table with `to_pandas()` |
| [io-load-npy/](io-load-npy/) | `IOBlock` (`SimpleLoader`) | A custom file loader: `.npy` → `Array` |
| [app-fiji/](app-fiji/) | `AppBlock` | Hand an image to Fiji/ImageJ and read the result back |
| [code-accucor-r/](code-accucor-r/) | `CodeBlock` | Run an R script (AccuCor isotope correction) on a table |
| [notebook-find-peaks/](notebook-find-peaks/) | packaged notebook | Work a computation out in cells, then package it into a block |

## Panels

A panel is a self-contained HTML document that renders one target type. Copy
into your project's `panels/<panel_id>/` — the directory name is the panel id —
then call `reload_panels`.

| Folder | Capability | What it shows |
|---|---|---|
| [panel-series-view/](panel-series-view/) | `displaying` | Render a `Series`; the init/ready handshake; sending nothing back |
| [panel-region-picker/](panel-region-picker/) | `producing` | Drag a region and emit the decision as one line of code |

Every block example imports only from the **canonical public roots**
(`scistudio.blocks.base`, `scistudio.blocks.process`, `scistudio.blocks.io`,
`scistudio.blocks.app`, `scistudio.core.types`). For the exact signature of any
symbol used here, see the **API reference**. Every panel example is one file
with no external dependency at all — that is the panel contract, not a
simplification for the example's sake.
