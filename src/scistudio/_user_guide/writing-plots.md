# Writing a plot

When the built-in previews are not the figure you want, write a **plot**: a small
script that draws a chart from a workflow output port. Plots are **preview-only**
— they are a quick way to look at a result, not a step in the pipeline. They show
in the **plots** tab and you can write them in Python (matplotlib / seaborn) or R
(ggplot2).

## The one rule: `render(collection)`

A plot script defines exactly one function — `render(collection)` in Python,
`render <- function(collection)` in R — and **imports nothing from SciStudio**.
The harness runs your script, hands it the data from the port you pointed it at
as `collection`, calls `render`, and shows whatever figure you return.

```python
def render(collection):
    import matplotlib.pyplot as plt

    df = collection.items.open_one()        # the port's data as a pandas DataFrame
    fig, ax = plt.subplots()
    ax.bar(df["compound"], df["intensity"])
    ax.set_ylabel("intensity")
    return fig                               # a matplotlib figure
```

Bind the plot to a block's output port and it draws every time you look. That is
the whole contract.

## What `collection` gives you

The `collection` is the batch of items on the port you chose. You read it with a
tiny, fixed surface — no SciStudio types involved:

| You write | You get |
|---|---|
| `collection.types` | the type name(s) on the port, e.g. `("DataFrame",)` |
| `collection.items` | the items: `len()`, iterate, index `[i]` |
| `collection.items.open_one()` | the **first** item, opened to a native object |
| `collection.items.open()` | **all** items, opened, as a list (size-guarded) |
| `item.type` | the item's type name (`"Array"`, `"DataFrame"`, …) |
| `item.metadata` | the item's metadata (read-only) |
| `item.open()` | the item as a plain scientific object (see below) |

`open()` hands you **ordinary objects**, never a SciStudio wrapper:

| `item.type` | `item.open()` gives you |
|---|---|
| `Array` | a numpy `ndarray` |
| `DataFrame` | a pandas `DataFrame` |
| `Series` | a pandas `Series` (or `DataFrame` if it has two columns, e.g. a spectrum's `lambda`/`intensity`) |
| `Text` | a `str` |
| `Artifact` | a `pathlib.Path` |
| `CompositeData` | a `dict` of opened parts |

So a one-item table port is `collection.items.open_one()` → a pandas DataFrame,
and a batch of images is `collection.items.open()` → a list of numpy arrays.

## What to return

`render` returns one of:

- **a figure** — a matplotlib figure (anything with `.savefig`); the harness
  saves it for you;
- **a file path** — a `str` or `pathlib.Path` to an image you wrote yourself
  (it must live in the plot's working directory);
- **a list** of either, to produce several figures.

Returning `None` is an error — always return your figure.

## A batch example

Overlay every spectrum in a batch on one axis:

```python
def render(collection):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    for item in collection.items:
        s = item.open()                 # a pandas Series/DataFrame per spectrum
        ax.plot(s.index, s.values)
    ax.set_xlabel("wavelength")
    ax.set_ylabel("intensity")
    return fig
```

## R

The same contract, in R with ggplot2:

```r
render <- function(collection) {
  library(ggplot2)
  df <- collection$items$open_one()      # a data.frame
  ggplot(df, aes(x = compound, y = intensity)) + geom_col()
}
```

## Plots vs blocks

A plot is **not** a block: it never becomes a node in your workflow and never
feeds another step. It is a viewer bound to a port. If you need the figure to be
a real, saved output of the pipeline, make a block that produces an `Artifact`
instead. For a quick look while you work, a plot is the right tool — and the
[AI assistant](ai-assistant.md) will write one for you from a description.
