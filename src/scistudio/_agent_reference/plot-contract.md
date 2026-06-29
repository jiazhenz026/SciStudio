# Plot contract — `render(collection)`

A plot is a **preview-only** script bound to a block output port (not a workflow
node). It is import-free and dual-interpreter (Python + matplotlib/seaborn, or R +
ggplot2). The harness runs it in a confined subprocess, injects `collection`, and
collects the return.

## The entrypoint

Exactly `def render(collection):` (R: `render <- function(collection)`). Any other
signature — including `render(collection, context)` — is rejected. The script
**imports nothing from `scistudio`**.

```python
def render(collection):
    import matplotlib.pyplot as plt
    df = collection.items.open_one()        # native object (pandas DataFrame)
    fig, ax = plt.subplots()
    ax.bar(df["compound"], df["intensity"])
    return fig
```

## Injected `collection` shape

| Access | Yields |
|---|---|
| `collection.types` | tuple of type names on the port |
| `collection.items` | ordered: `len()`, iterate, `[i]`, `[a:b]` |
| `collection.items.open()` / `.open(max_items=n)` | all items opened, as a list (byte-budget guarded) |
| `collection.items.open_one()` | first item opened (empty → error) |
| `item.type` | type name (`"Array"`, `"DataFrame"`, …) |
| `item.metadata` | read-only mapping (storage/lineage keys stripped) |
| `item.open()` | native payload by type (below) |

`item.open()` returns **vanilla objects**, never a `DataObject`:

| `item.type` | `open()` |
|---|---|
| `Array` | numpy `ndarray` |
| `DataFrame` | pandas `DataFrame` |
| `Series` | pandas `Series` (or `DataFrame` if ≥2 columns, e.g. a spectrum's `lambda`/`intensity`) |
| `Text` | `str` |
| `Artifact` | `pathlib.Path` |
| `CompositeData` | `dict[str, <opened>]` |

## Return contract

Return one of:

- a Matplotlib figure (duck-typed: has `.savefig`),
- an artifact path (`str` / `pathlib.Path`) that resolves **inside the plot
  working dir** and exists,
- a `list`/`tuple` of the above (mixed allowed).

`None` or any other type is rejected.

## Notes

A plot is bound by a discovered `target_id` (a port), never by a block label, and
never becomes a DAG node. Read only a bounded sample for large data (`open()` is
budget-guarded). For a saved pipeline output instead of a preview, write a block
that emits an `Artifact`. The user-facing how-to is
`../../user-guide/writing-plots.md`.
