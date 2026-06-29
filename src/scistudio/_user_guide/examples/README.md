# Examples

One worked example per block base class. Each folder has the block (a `.py`
file, or a script + notes for `CodeBlock`) and a short `README.md` that walks
through it. Copy a folder into your project's `blocks/` and edit from there.

| Folder | Base class | What it shows |
|---|---|---|
| [process-scale-array/](process-scale-array/) | `ProcessBlock` / `Block` | Per-item transform over a batch; reading a table with `to_pandas()` |
| [io-load-npy/](io-load-npy/) | `IOBlock` (`SimpleLoader`) | A custom file loader: `.npy` → `Array` |
| [app-fiji/](app-fiji/) | `AppBlock` | Hand an image to Fiji/ImageJ and read the result back |
| [code-accucor-r/](code-accucor-r/) | `CodeBlock` | Run an R script (AccuCor isotope correction) on a table |

Every example imports only from the **canonical public roots**
(`scistudio.blocks.base`, `scistudio.blocks.process`, `scistudio.blocks.io`,
`scistudio.blocks.app`, `scistudio.core.types`). For the exact signature of any
symbol used here, see the **API reference**.
