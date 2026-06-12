---
doc_type: block-development
title: "Memory Safety"
status: living
owner: "@jiazhenz026"
last_updated: 2026-05-19
governed_by:
  - ADR-042
  - ADR-043
summary: "Developer guide for bounded-memory block patterns, Collection mapping tiers, and streaming IO."
---

# Memory Safety

This document covers patterns for processing large scientific datasets
without exhausting memory. The three-tier processing model, auto-flush
mechanism, and streaming data access are all designed to keep peak memory
bounded.

---

## Table of Contents

1. [The Problem](#the-problem)
2. [Tier 1: process_item with Auto-Flush](#tier-1-process_item-with-auto-flush)
3. [Tier 2: map_items and parallel_map](#tier-2-map_items-and-parallel_map)
4. [Tier 3: Manual run with pack/unpack](#tier-3-manual-run-with-packunpack)
5. [Auto-Flush Mechanism](#auto-flush-mechanism)
6. [Streaming Data Access](#streaming-data-access)
7. [IOBlock Streaming Writes](#ioblock-streaming-writes)
8. [Memory Hints and Resource Declarations](#memory-hints-and-resource-declarations)
9. [Decision Guide](#decision-guide)

---

## The Problem

Scientific data can be large. A single microscopy z-stack may be 10+ GB.
An LCMS peak table may have millions of rows. A time-lapse series may
contain thousands of frames.

If a block loads all items into memory simultaneously, the process will
run out of RAM. The three-tier processing model prevents this by
controlling how many items are in memory at any point.

---

## Data Access Strategies

Block authors choose how to read input data and how to produce output data.
The framework supports both full materialization and streaming -- choose based
on your expected data size.

### Reading input data

| Strategy | API | Memory | When to use |
|----------|-----|--------|-------------|
| **Full load** | `arr = item.to_memory()` | O(full array) | Data fits in RAM; need full array for computation |
| **Partial read** | `plane = item.sel(z=5)` | O(slice) | Only need a subset of dimensions |
| **Chunked iteration** | `for chunk in item.iter_chunks(1024):` | O(chunk) | Process large data piece by piece |

### Writing output data

| Strategy | API | Memory | When to use |
|----------|-----|--------|-------------|
| **Full output** | `Array(..., data=result)` | O(result) | Result fits in RAM (most blocks) |
| **Streaming write** | `ref = self.persist_array(chunk_iter, shape, dtype)` | O(chunk) | Producing very large output |

### Common patterns

**Pattern 1 -- Simple transform (most blocks):**

```python
def process_item(self, item, config, state=None):
    data = item.to_memory()                          # full read
    result = some_transform(data)
    return Array(axes=list(item.axes), shape=result.shape,
                 dtype=str(result.dtype), data=result)  # full write
```

**Pattern 2 -- Large data, chunked processing:**

```python
def process_item(self, item, config, state=None):
    def compute():
        for i, chunk in enumerate(item.iter_chunks(1024)):  # streaming read
            yield i, transform(chunk)
    ref = self.persist_array(compute(), shape, dtype)        # streaming write
    return Array(axes=list(item.axes), shape=shape,
                 dtype=str(dtype), storage_ref=ref)
```

**Pattern 3 -- Partial read, full write:**

```python
def process_item(self, item, config, state=None):
    plane = item.sel(z=config.get("z_index"))   # partial read
    data = plane.to_memory()
    result = process_plane(data)
    return Array(axes=list(plane.axes), shape=result.shape,
                 dtype=str(result.dtype), data=result)  # full write
```

---

## Tier 1: process_item with Auto-Flush

**O(1) peak memory** -- the recommended approach for 80% of blocks.

Override `process_item()` and let the framework handle everything else:

```python
class MyBlock(ProcessBlock):
    def process_item(self, item, config, state=None):
        data = np.asarray(item.to_memory())       # load one item
        result_data = transform(data)               # process it
        return Array(                                # auto-flushed, then GC'd
            axes=list(item.axes),
            shape=result_data.shape,
            dtype=str(result_data.dtype),
            data=result_data,
        )
```

How it works:

1. The default `ProcessBlock.run()` iterates the input Collection.
2. For each item, it calls `process_item(item, config, state)`.
3. The result is immediately auto-flushed to zarr storage.
4. The flushed result holds only a `StorageReference` (~100 bytes).
5. Python's garbage collector frees the in-memory data.
6. Peak memory = size of one input item + one output item.

### With setup/teardown

If your block needs expensive one-time initialization (ML model, compiled
regex, database connection):

```python
class MLBlock(ProcessBlock):
    def setup(self, config):
        import torch
        model = torch.load(config.get("model_path"))
        model.eval()
        return model  # this is `state`

    def process_item(self, item, config, state=None):
        data = np.asarray(item.to_memory())
        prediction = state(torch.from_numpy(data))
        # ... build result ...
        return result

    def teardown(self, state):
        if state is not None:
            import torch
            torch.cuda.empty_cache()
```

---

## Tier 2: map_items and parallel_map

For explicit iteration control in a custom `run()`:

### Sequential processing

```python
def run(self, inputs, config):
    images = inputs["images"]
    def transform(item):
        data = np.asarray(item.to_memory())
        result_data = process(data)
        return Array(axes=list(item.axes), shape=result_data.shape, dtype=str(result_data.dtype), data=result_data)
    output = self.map_items(transform, images)
    return {"output": output}
```

`map_items` processes items one at a time, auto-flushing each result.
Peak memory: O(1 item).

### Parallel processing

```python
output = self.parallel_map(transform, images, max_workers=4)
```

**Warning**: `parallel_map` loads `max_workers` items concurrently. For
large items (images, MSI datasets), set `max_workers=1` or use
`map_items()`.

---

## Tier 3: Manual run with pack/unpack

For complex multi-port logic, conditional outputs, or non-standard
iteration:

```python
def run(self, inputs, config):
    items = self.unpack(inputs["data"])
    good = []
    bad = []
    for item in items:
        data = item.to_memory()
        if passes_qc(data):
            good.append(process(item))
        else:
            bad.append(item)
    return {
        "passed": self.pack(good, item_type=Array),
        "failed": self.pack(bad, item_type=Array),
    }
```

- `unpack(collection)` returns `list[DataObject]`.
- `unpack_single(collection)` returns the single item (raises if len != 1).
- `pack(items, item_type)` creates a Collection, auto-flushing each item.

---

## Auto-Flush Mechanism

Auto-flush is the framework's safety net for memory management. It
writes in-memory DataObjects to project-local zarr/parquet storage
and sets the `storage_ref` on the instance.

### When auto-flush runs

- After each `process_item` return in the default `ProcessBlock.run()`.
- Inside `map_items()` and `parallel_map()`, per result.
- Inside `pack()`, per item.
- In `IOBlock.run()`, for any item in a load result that lacks `storage_ref`.

### What auto-flush does

1. Checks if `obj.storage_ref is not None` -- if yes, no-op.
2. Gets the output directory from the flush context.
3. Routes to the appropriate backend (zarr for arrays, parquet for tables).
4. Calls `obj.save(target_path)` to persist the data.
5. Sets `obj.storage_ref` to the new StorageReference.

### Exemptions

- **Artifacts with `file_path`** (ADR-031 D5): Path-only transport.
  Artifacts that have `file_path` set are not read into memory or copied.
- **Objects with existing `storage_ref`**: Already persisted, no-op.

### CompositeData recursive flush

For CompositeData instances (e.g., Label), auto-flush recursively
persists each internal slot's DataObject before persisting the composite
itself.

---

## Streaming Data Access

For reading large data without loading everything at once:

### `sel(**kwargs)` -- Named axis selection

```python
# Load only z-slice 15, channel 0
plane = img.sel(z=15, c=0)
data = plane.to_memory()  # only the selected plane is in memory
```

### `iter_over(axis)` -- Iterate over an axis

```python
for z_slice in img.iter_over("z"):
    data = z_slice.to_memory()  # one slice at a time
    process(data)
```

### `iter_chunks(chunk_size)` -- Raw chunk iteration

```python
for chunk in item.iter_chunks(chunk_size=1024*1024):
    process_chunk(chunk)
```

---

## Streaming Writes with persist_array / persist_table {#ioblock-streaming-writes}

Available on **all block types** (defined on the `Block` base class).
These helpers persist data directly to project-local storage without
relying on auto-flush. IOBlock loaders MUST use these helpers (ADR-031
Addendum 1, A1-D3). ProcessBlocks and other block types may also use
them for explicit persistence.

### `persist_array(data_or_iterator, shape, dtype, output_dir, chunks=None)`

```python
def load(self, config, output_dir=""):
    import tifffile
    path = config.get("path")
    with tifffile.TiffFile(path) as tf:
        n_pages = len(tf.pages)
        page_shape = tf.pages[0].shape
        page_dtype = tf.pages[0].dtype
        shape = (n_pages, *page_shape)

        # Streaming: yield one page at a time
        def page_iterator():
            for i, page in enumerate(tf.pages):
                yield (i, page.asarray())

        ref = self.persist_array(page_iterator(), shape, page_dtype, output_dir)

    return Array(
        axes=["z", "y", "x"],
        shape=shape,
        dtype=str(np.dtype(page_dtype)),
        storage_ref=ref,
    )
```

Memory: O(one page) regardless of total file size.

### `persist_table(table, output_dir)` {#persist-table}

Available on **all block types** (Block base class).

```python
def load(self, config, output_dir=""):
    import pyarrow as pa
    import pandas as pd

    df = pd.read_csv(config.get("path"))
    arrow_table = pa.Table.from_pandas(df)
    ref = self.persist_table(arrow_table, output_dir)

    return DataFrame(
        columns=[str(c) for c in df.columns],
        row_count=len(df),
        storage_ref=ref,
    )
```

---

## Memory Hints and Resource Declarations

Declare resource requirements as ClassVars to help the engine schedule
blocks appropriately:

```python
class HeavyBlock(ProcessBlock):
    requires_gpu: ClassVar[bool] = True
    cpu_cores: ClassVar[int] = 8
    key_dependencies: ClassVar[list[str]] = ["torch>=2.0"]
```

These are advisory hints. The engine uses `requires_gpu` and `cpu_cores`
for scheduling but does not enforce hard limits. **`key_dependencies`
(ADR-038, 2026-05-15) is now palette / documentation metadata only** —
the per-run environment-snapshot mechanism in `lineage.db.runs` captures
the full `uv pip freeze` regardless of what any block declares; see
ARCHITECTURE.md §6.7 + the "Resource Hints" section in
`architecture-for-block-devs.md` for the contract split.

---

## Decision Guide

| Scenario | Approach |
|----------|----------|
| Per-item transform, no shared state | Tier 1: `process_item` |
| Per-item with ML model | Tier 1: `process_item` + `setup`/`teardown` |
| Custom iteration logic | Tier 2: `map_items` in `run()` |
| Multi-port output | Tier 3: `pack`/`unpack` in `run()` |
| Large file loading | All blocks: `persist_array` streaming |
| Table loading | All blocks: `persist_table` |
| Selective data access | `sel()`, `iter_over()`, `iter_chunks()` |
