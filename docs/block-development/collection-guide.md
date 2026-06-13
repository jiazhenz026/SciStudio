---
doc_type: block-development
title: "Collection Guide"
status: living
owner: "@jiazhenz026"
last_updated: 2026-06-10
governed_by:
  - ADR-042
  - ADR-048
summary: "Patterns for working with the Collection transport wrapper: construction, iteration, single/empty collections, pack/unpack utilities, serialization, and how a collection's item type drives preview routing."
---

# Collection Guide

This document covers patterns for working with Collections -- the
standard block-to-block transport wrapper in SciStudio.

---

## Table of Contents

1. [What is Collection?](#what-is-collection)
2. [Construction](#construction)
3. [Iteration Patterns](#iteration-patterns)
4. [Single-Item Collections](#single-item-collections)
5. [Empty Collections](#empty-collections)
6. [Utilities: unpack, pack, unpack_single](#utilities-unpack-pack-unpack_single)
7. [Storage and Serialization](#storage-and-serialization)
8. [Collection in Block Signatures](#collection-in-block-signatures)
9. [Collections and preview](#collections-and-preview)

---

## What is Collection?

`Collection` (`scistudio.core.types.collection.Collection`) is a
homogeneous ordered container of DataObject instances. It is the standard
block-to-block transport type.

**Key properties**:

- NOT a DataObject subclass -- it is a transport wrapper only.
- All items must be instances of the same base type.
- `item_type` is set at construction and cannot change.
- The engine never unpacks, iterates, or inspects Collection contents.

**ADR-020**: Collection exists because blocks may produce zero, one, or
many items. The engine treats the entire Collection as an opaque unit;
only the receiving block decides how to iterate.

---

## Construction

### From a list of items (type inferred)

```python
from scistudio.core.types.collection import Collection

coll = Collection(items=[img1, img2, img3])
# item_type is inferred from type(img1)
```

### From a list with explicit item_type

```python
coll = Collection(items=[img1, img2], item_type=Image)
```

### Empty Collection (requires explicit item_type)

```python
coll = Collection(items=[], item_type=Array)
```

An empty Collection without `item_type` raises `TypeError`.

---

## Iteration Patterns

### For loop

```python
for item in collection:
    data = item.to_memory()
    process(data)
```

### Index access

```python
first = collection[0]
last = collection[-1]
sub = collection[1:3]  # returns a list, not a Collection
```

### Length

```python
n = len(collection)
# or
n = collection.length
```

### List conversion

```python
items = list(collection)  # list of DataObject instances
```

---

## Single-Item Collections

Even a single data object flows as a `Collection(length=1)`. There is
no special scalar path. This is by design -- it keeps the block contract
uniform.

```python
# Creating a single-item Collection
single = Collection(items=[my_image], item_type=Image)

# Extracting the single item
item = collection[0]

# Or use the unpack_single utility
item = Block.unpack_single(collection)  # raises ValueError if len != 1
```

---

## Empty Collections

Empty Collections are valid and meaningful. They represent "no data"
for conditional workflows:

```python
# A filter block might output zero items
empty = Collection(items=[], item_type=Image)
```

Downstream blocks receive an empty Collection and iterate zero times.
This is the correct way to handle "nothing to process" -- not by raising
an exception.

---

## Utilities: unpack, pack, unpack_single

The `Block` base class provides static utility methods for Collection
manipulation.

### `Block.unpack(collection) -> list[DataObject]`

Returns a plain list of DataObject instances:

```python
items = self.unpack(inputs["images"])
for item in items:
    data = item.to_memory()
```

### `Block.unpack_single(collection) -> DataObject`

Extracts the single item from a length-1 Collection. Raises
`ValueError` if the Collection does not have exactly one item.

```python
single_image = self.unpack_single(inputs["image"])
data = single_image.to_memory()
```

### `Block.pack(items, item_type=None) -> Collection`

Creates a Collection from a list of DataObjects, auto-flushing each
item to storage:

```python
results = [process(item) for item in items]
output = self.pack(results, item_type=Array)
return {"output": output}
```

If `item_type` is not provided, it is inferred from the first item.

### `Block.map_items(func, collection) -> Collection`

Applies a function to each item sequentially, auto-flushing each result:

```python
def transform(item):
    data = np.asarray(item.to_memory())
    result_data = some_transform(data)
    return Array(axes=list(item.axes), shape=result_data.shape,
                 dtype=str(result_data.dtype), data=result_data)

output = self.map_items(transform, inputs["images"])
```

Peak memory: O(1 input + 1 output per iteration).

### `Block.parallel_map(func, collection, max_workers=4) -> Collection`

Applies a function to each item in parallel:

```python
output = self.parallel_map(transform, inputs["images"], max_workers=2)
```

**Caution**: `max_workers` items are in memory concurrently. For large
items, use `max_workers=1` or `map_items`.

---

## Storage and Serialization

### How Collection crosses the subprocess boundary

Items are serialized individually. Each item's `StorageReference`
(pointing to zarr or parquet storage) crosses as JSON. The Collection
wrapper itself is reconstructed on the receiving side with the correct
`item_type`.

### Storage references

```python
refs = collection.storage_refs  # list of StorageReference (or None)
```

---

## Collection in Block Signatures

### run() signature

```python
def run(
    self,
    inputs: dict[str, Collection],
    config: BlockConfig,
) -> dict[str, Collection]:
```

Both inputs and outputs are `dict[str, Collection]`. Even single items
are wrapped in a Collection.

### Port declarations

Ports can hint that they carry multi-item data:

```python
input_ports: ClassVar[list[InputPort]] = [
    InputPort(name="images", accepted_types=[Image], is_collection=True),
]
```

The `is_collection=True` flag is a UI hint -- it does not change runtime
behavior. All port values are Collections regardless.

### Type matching

Port type matching uses `collection.item_type`:

```python
# Port accepts [Array]
# Collection[Image] matches because Image is a subclass of Array
port_accepts_type(port, collection)  # True
```

---

## Collections and preview

A collection ref is previewable as a `collection_ref` target. ADR-048 preview
routing uses the collection's **item type** to choose a previewer: a
`Collection[Image]` first tries an `Image` collection previewer
(`supports_collection=True`), then an `Image` item previewer, then the generic
core collection fallback (`core.collection.basic`, a bounded item sample). The
core collection fallback only surfaces a bounded sample of item refs — it never
materialises every item. As with single objects, a `Collection[DataObject]` can
only reach the generic fallback, so a concrete `item_type` is what lets a
collection reach a domain previewer. See
[Previewers and Plot Jobs](previewers-and-plots.md#routing-precedence).
