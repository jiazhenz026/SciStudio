# Data types

## 1. Where to look

| You need | Read |
|---|---|
| Signatures and methods of `DataObject`, `Array`, `DataFrame`, `Series`, `Text`, `Artifact`, `CompositeData`, `Collection` | `user-guide/api-reference/scistudio.core.types.md` |
| Typed metadata (`Meta`) for a type | `user-guide/api-reference/scistudio.core.meta.md` |
| Which types are registered in this project, and their parents | `list_types` |
| Types from installed packages | [package-discovery.md](package-discovery.md) |
| Defining a new data type and its loader | the `scistudio-write-type` skill |
| Using types in a block | [block-contract.md](block-contract.md) and the `scistudio-write-block` skill |
| What the user sees about each type | `user-guide/data-types.md` |

## 2. Rules

- **Use the most fitting type.** Pick the most specific registered type, such as
  a package `Image` over `Array` or `DataFrame` over `DataObject`. `DataObject` is
  never a port type on a user-facing block.
- **Construct with keywords and `data=`.** Constructors are keyword-only, and the
  in-memory payload goes in `data=`: `Array(axes=[...], data=arr)`,
  `DataFrame(data=table)`, `Series(index_name=..., value_name=..., data=table)`.
  `Text` takes `content=` and `Artifact` takes `file_path=`.
- **Read through the public accessors.** `to_memory()` returns the canonical form
  (a NumPy array for `Array`, a `pyarrow.Table` for `DataFrame` and `Series`), and
  `to_numpy()` / `to_pandas()` give NumPy and pandas views. Never read private
  attributes such as `_data` or `_storage_ref`.
- **Build tables from Arrow.** Convert a pandas result with
  `pyarrow.Table.from_pandas(df)` and pass it as `data=`. Do not read back an
  output you just built inside the same block; it is persisted when the block
  returns.
- **Name every array axis.** Pass `axes` from `t`, `z`, `c` (discrete channel),
  `lambda` (continuous spectral), `y`, and `x`, and keep them when transforming:
  `Array(axes=list(item.axes), data=new_arr)`. A subclass may require axes through
  `required_axes`, `allowed_axes`, and `canonical_order`.
- **Treat data objects as immutable.** Change typed metadata with
  `with_meta(**changes)`, which returns a new object. Put free-form per-item notes
  in the `user` dict.
- **Group named parts with `CompositeData`.** Subclass it with `expected_slots`
  mapping each slot name to a type, and use `set(name, obj)` and `get(name)`. A
  plain `CompositeData` accepts any slots.
- **Check the size before loading.** Call `inspect_data` (or read `shape`) before
  reading data whole. `to_memory()` warns above about 2 GB, and a GB-scale object
  must never be loaded whole.
- **Read large data in pieces.** Use `sel(axis=int | slice)` or `iter_over(axis)`
  on an `Array`, and `slice(...)` or `iter_chunks(chunk_size)` on any type. `sel`
  reads only the requested region from Zarr and returns a plain `Array`.
- **Write large arrays as a stream.** In a block, call
  `self.persist_array(iterator, shape, dtype)` with `(index, chunk)` pairs and wrap
  the reference as `Array(axes=[...], shape=shape, dtype=dtype, storage_ref=ref)`.
  `persist_table` writes one Arrow table, so reduce a large table chunk by chunk
  first.
- **By default, no extra batch handling is needed.** When you write an IO
  block for a new data type, inherit SimpleLoader/SimpleSaver and handle the read or write as a
  single-file operation; the core automatically fans in and fans out.
