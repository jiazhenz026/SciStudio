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

## Picking a type

Use the **most specific applicable** type on a port (a package `Image`/`Spectrum`
over `Array`/`Series`; `DataFrame` over `DataObject`). `DataObject` (the root) is
only for genuinely generic blocks. Call the `list_types` MCP tool to see what is
registered; a package type subclasses a core type and inherits all of the above.
