# Data types

Core types, all from `scistudio.core.types`. Read a value, build a value, or
stream large data — with the public methods below. For exact signatures see the
API reference (`scistudio.core.types`).

## Read and construct

| Type | `to_memory()` returns | Ergonomic read | Construct |
|---|---|---|---|
| `Array` | numpy `ndarray` | `to_numpy()` | `Array(axes=[...], data=arr)` |
| `DataFrame` | `pyarrow.Table` | `to_pandas()`, `to_numpy()` | `DataFrame(data=table)` |
| `Series` | `pyarrow.Table` | `to_pandas()`, `to_numpy()` | `Series(index_name=..., value_name=..., data=table)` |
| `Text` | `str` | — | `Text(content="...")` |
| `Artifact` | `bytes` (path is `item.file_path`) | — | `Artifact(file_path=Path(...))` |
| `CompositeData` | `dict[str, native]` | — | subclass with `expected_slots` |

- **`to_memory()`** is the canonical in-memory form (Arrow for tables, ndarray for
  arrays). The internal data path uses only this.
- **`to_pandas()` / `to_numpy()`** are public ergonomic accessors (read-only) for
  author code that thinks in pandas/numpy. Build back with the `data=` constructor
  and an Arrow table (`pyarrow.Table.from_pandas(df)`); never via `to_pandas()`.
- Constructors are **keyword-only**; the in-memory payload goes through `data=`.

## Arrays carry an axis schema

`Array` (and subclasses) take `axes: list[str]` at construction — e.g.
`["y", "x"]`. The 6-D scientific alphabet is `{t, z, c, lambda, y, x}`. Subclasses
tighten the schema with class vars `required_axes`, `allowed_axes`,
`canonical_order`. Preserve axes when transforming:
`Array(axes=list(item.axes), data=new_arr)`.

## Metadata

Typed metadata travels in a nested frozen `Meta` (Pydantic) model on a type;
update immutably with `with_meta(**changes)` (returns a new instance). Free-form
per-item metadata goes in the inherited `user` dict.

## Large data — never materialize whole

Scientific objects can exceed memory. Use the backend-served reads instead of
`to_memory()` on big data:

| Method | On | Does |
|---|---|---|
| `sel(**axes)` | `Array` | partial read along named axes (Zarr) |
| `slice(...)` | `DataObject` | sub-region / row range / byte range |
| `iter_chunks(chunk_size)` | `DataObject` | stream chunks / Parquet batches |
| `persist_array(...)` / `persist_table(...)` | `Block` | streaming writes |

## In a notebook: native objects, converted at the boundary

Everything above describes **block code**, which holds SciStudio objects. A
notebook cell does not. Between the two helpers a cell holds ordinary
`pandas.DataFrame`, `numpy.ndarray`, `str` and `Path` values — whatever the
science library returned — and the conversion happens only at the boundary:

| Boundary | Direction | What happens |
|---|---|---|
| `scistudio.load(...)` | in | returns a **`DataObject`**, storage-backed. Call `.to_pandas()` / `.to_numpy()` for the native form the rest of the cell works in. |
| `scistudio.output(name=obj)` | out | accepts a **native** object and wraps it into its SciStudio type *by construction from data*. You do not build a typed object first. |

The outbound mapping is the one the IO loaders already use:

| You pass | It becomes |
|---|---|
| `pandas.DataFrame` / `pyarrow.Table` | `DataFrame` |
| `pandas.Series` | single-column `Series` |
| `numpy.ndarray` | `Array`, with generated axis names (`axis_0`, `axis_1`, …) |
| `str` | `Text` |
| `pathlib.Path` to an existing file | `Artifact` |
| an existing `DataObject` | itself, unchanged |

Anything else raises, naming the type: the answer is either to declare a
SciStudio type for it or to convert it in the cell, and a silent pickle would be
neither.

Two consequences worth holding on to:

- **`load` gives you a storage-backed object in both modes** — in the session
  and in the packaged block — so `to_memory`, `slice`, and `iter_chunks` behave
  the same in each. A helper that returned an unbacked object would give you a
  notebook that works while you watch it and fails once packaged.
- **Generated axis names are a default, not a schema.** If the array has real
  axes, construct the `Array` yourself with `axes=[...]` and pass that to
  `output` rather than letting the wrap name them.

## Picking a type

Use the **most specific applicable** type on a port (a package `Image`/`Spectrum`
over `Array`/`Series`; `DataFrame` over `DataObject`). `DataObject` (the root) is
only for genuinely generic blocks. Call the `list_types` MCP tool to see what is
registered; a package type subclasses a core type and inherits all of the above.
