---
doc_type: block-development
title: "Architecture for Block Developers"
status: living
owner: "@jiazhenz026"
last_updated: 2026-05-19
governed_by:
  - ADR-042
  - ADR-043
summary: "Execution model and data transport guidance for block authors, including canonical-zone and boundary IO rules."
---

# Architecture for Block Developers

This document explains the execution model, data transport, and lifecycle
that block developers need to understand.

---

## Table of Contents

1. [Subprocess Isolation](#subprocess-isolation)
2. [Data Transport](#data-transport)
3. [Boundary Formats](#boundary-formats)
4. [Block Lifecycle](#block-lifecycle)
5. [Three Tiers of Collection Handling](#three-tiers-of-collection-handling)
6. [Cancellation Semantics](#cancellation-semantics)
7. [Resource Hints](#resource-hints)

---

## Subprocess Isolation

**ADR-017**: Every block executes in its own subprocess. This gives you:

- **Library freedom**: Import any Python package, any version. Your block's
  subprocess has its own import namespace.
- **Memory isolation**: Your block can use as much memory as the OS allows
  without affecting other blocks.
- **CPU isolation**: Long-running computation does not block the engine.
- **Crash containment**: If your block crashes, only that subprocess dies.

**What you cannot do**:

- Share in-memory state between blocks. There is no shared address space.
- Hold open database connections or sockets across block boundaries.
- Return raw Python objects (numpy arrays, pandas DataFrames) directly.
  All data must go through the typed DataObject + StorageReference system.

### How data crosses the subprocess boundary

The engine serializes only lightweight metadata (StorageReference pointers,
config dicts, framework metadata) as JSON. Scientific data (arrays, tables)
lives in project-local storage (zarr, parquet) and is accessed via
StorageReference.

```
Engine process                    Block subprocess
     |                                 |
     |  --- JSON (config, refs) --->   |
     |                                 |  block.run(inputs, config)
     |                                 |  item.to_memory()  # reads from zarr
     |                                 |  result._data = ...
     |                                 |  _auto_flush(result)  # writes to zarr
     |  <-- JSON (output refs) ---     |
     |                                 |
```

---

## Data Transport

**ADR-020**: Data flows between blocks as `Collection` objects. A Collection
is a homogeneous ordered list of DataObject instances.

### Collection is a transport wrapper

Collection is NOT a DataObject subclass. It wraps zero or more DataObject
instances of the same type. The engine never inspects Collection contents;
it passes the Collection as-is through the subprocess boundary.

### Single-item semantics

Even a single image flows as a `Collection[Image](length=1)`. There is no
special scalar path.

### Type identity

Port matching uses `collection.item_type`, which is an `isinstance`-based
check. A `Collection[FluorImage]` matches a port that accepts `Image`
because `FluorImage` is a subclass of `Image`.

---

## Boundary Formats

Inside the canonical workflow zone, block edges are type-only. A ProcessBlock
should consume `Image`, `DataFrame`, `PeakTable`, or another DataObject type
without caring whether the object originally came from TIFF, PNG, CSV, mzML,
or Zarr.

External file formats matter only at boundaries:

- `IOBlock` load and save blocks.
- `AppBlock` file exchange.
- `CodeBlock` file exchange.
- AI/tool sessions that materialise files for an external process.

ADR-043 represents each boundary conversion as a `FormatCapability`. The
registry resolves capabilities by direction, type, extension or format id, and
optional stable `capability_id`. If multiple packages can handle the same
boundary, the user or workflow must choose a capability id unless one package
declares a valid default.

Metadata fidelity is about typed `DataObject.meta` fields at the boundary.
Lineage records, run parameters, and environment snapshots are runtime
provenance; they are not IO metadata fidelity promises.

---

## Block Lifecycle

### ProcessBlock lifecycle (Tier 1)

```
run(inputs, config)
  |
  v
setup(config) -> state         # load model, open connection (once)
  |
  v
for item in primary_collection:
    process_item(item, config, state)  # per-item logic
    _auto_flush(result)                # persist to storage (raises RuntimeError on failure)
  |
  v
teardown(state)                # release resources (always runs, even on error)
  |
  v
return {port_name: Collection(results)}
```

The `setup` / `teardown` lifecycle (ADR-027 D7) is optional. If your block
does not override `setup()`, `state` is `None`.

### IOBlock lifecycle

```
run(inputs, config)
  |
  v
if direction == "input":
    load(config, output_dir) -> DataObject | Collection
    # auto-flush any items without storage_ref (fail-hard: raises RuntimeError on failure)
    return {port_name: Collection}
else:
    save(obj, config)
    return {receipt_port: Collection[Text]}
```

**IOBlock loaders MUST persist directly** (ADR-031 Addendum 1, A1-D3):
1. Use `persist_array(ndarray)` for one-shot persistence (small/medium files), or
2. Use `persist_array(chunk_iter())` for streaming persistence (large files).

Do NOT use `_data` assignment in IOBlock loaders. Auto-flush is a fail-hard
safety net (raises `RuntimeError` on failure) intended for ProcessBlocks only.

---

## Three Tiers of Collection Handling

**ADR-020** defines three tiers for how blocks interact with Collections.

### Tier 1: process_item (80% of blocks)

Override `process_item(self, item, config, state)`. The framework handles
iteration, auto-flush, and Collection packing. Peak memory: O(1 item).

```python
def process_item(self, item, config, state=None):
    data = np.asarray(item.to_memory())
    result_data = some_transform(data)
    result = Array(axes=list(item.axes), shape=result_data.shape, dtype=str(result_data.dtype))
    result._data = result_data
    return result
```

### Tier 2: map_items / parallel_map

Override `run()` and use the built-in utilities for explicit control:

```python
def run(self, inputs, config):
    images = inputs["images"]
    def transform(item):
        data = np.asarray(item.to_memory())
        # ... transform ...
        result = Array(axes=list(item.axes), shape=data.shape, dtype=str(data.dtype))
        result._data = transformed
        return result
    output = self.map_items(transform, images)
    return {"output": output}
```

- `map_items(func, collection)` -- sequential, auto-flush per item.
- `parallel_map(func, collection, max_workers)` -- parallel, use cautiously.

### Tier 3: manual run with pack/unpack

Override `run()` completely for multi-port logic, conditional outputs, or
non-Collection results:

```python
def run(self, inputs, config):
    items = self.unpack(inputs["data"])
    results = []
    for item in items:
        # complex multi-step logic
        results.append(processed)
    return {"output": self.pack(results, item_type=Array)}
```

- `unpack(collection)` -- returns `list[DataObject]`.
- `unpack_single(collection)` -- returns the single item (raises if len != 1).
- `pack(items, item_type)` -- creates a Collection, auto-flushing each item.

---

## Cancellation Semantics

**ADR-018**: The engine can cancel a running block at any time.

- The engine sends SIGTERM to the block subprocess.
- After `terminate_grace_sec` (default 5.0 seconds), SIGKILL is sent.
- Block states: `CANCELLED` (user-initiated) and `SKIPPED` (upstream
  dependency unavailable).

**Best practice**: If your block writes intermediate files, use atomic
write patterns (write to a temp file, then rename) so cancellation does
not leave corrupt output.

---

## Resource Hints

**ADR-022**: Blocks can declare resource requirements as ClassVars. These
hints are advisory; the engine uses them for scheduling decisions.

```python
class MyGPUBlock(ProcessBlock):
    requires_gpu: ClassVar[bool] = True
    cpu_cores: ClassVar[int] = 4
    key_dependencies: ClassVar[list[str]] = ["torch>=2.0", "cellpose>=3.0"]
```

- `requires_gpu` -- Hint that the block needs GPU access.
- `cpu_cores` -- Requested CPU cores for parallel computation.
- `key_dependencies` -- Python packages the block requires (displayed in
  the palette UI for user guidance). **Note (ADR-038, 2026-05-15):** this
  ClassVar is now strictly *block-author-facing palette metadata*. It is
  **NOT** the runtime environment-snapshot mechanism — the engine captures
  the full `uv pip freeze` per run in `lineage.db.runs.environment_snapshot`
  per ADR-038 §3.1, regardless of what any individual block declares.
  `key_dependencies` survives as documentation / palette UX, not as a
  reproducibility contract.

---

## Custom blocks alongside git (ADR-039)

Your custom block files at `<project>/blocks/*.py` are **git-tracked source like
any other Python file**. There is nothing block-author-specific about how SciStudio
treats them. When the user clicks Commit in the GUI, modified block files are
staged and committed alongside workflow YAML and project notes. When the user
switches branches via the BranchPicker, your block files are checked out to the
new branch's content; the `BlockRegistry.hot_reload()` (ADR-036 §3.5) re-discovers
blocks on save, so branch switching transparently rebuilds the palette.

Two consequences worth knowing:

1. **`block_version` is force-injected by the framework, not by your code.** Per
   ADR-038 §3.3, `BlockRegistry.scan()` reads `importlib.metadata.version(distribution_name)`
   at registration time and stamps it onto your `BlockSpec.version` field. If your
   plugin package's `pyproject.toml` is missing a version, registration **fails
   loudly** rather than defaulting. In-tree project blocks (`<project>/blocks/*.py`)
   read `scistudio.__version__` as a uniform default; plugin blocks read their own
   distribution version per ADR-037 D11. Test your plugin packages with
   `BlockTestHarness.validate_package_info()` (ADR-026).

2. **The framework records lineage externally — your block authoring contract is
   unchanged.** You continue to write `Block.run(inputs, config) → outputs`. You
   do **not** call into `LineageStore` directly. The engine observes your block's
   execution and writes the appropriate rows into `<project>/.scistudio/lineage.db`
   (4 normalized tables per ADR-038 §3.1) without any code on your side. If you
   need to read past lineage for AI-driven parameter tuning or similar, query the
   database via the MCP `get_lineage` tool (ADR-033) or directly via `sqlite3`.

---

## Summary

| Concept | Rule |
|---------|------|
| Isolation | Each block runs in its own subprocess |
| Data transport | StorageReference pointers cross the boundary, not raw data |
| Collection | Homogeneous typed wrapper, the standard block-to-block transport |
| Tier 1 | Override `process_item` for per-item logic (recommended) |
| Tier 2 | Use `map_items` / `parallel_map` in a custom `run()` |
| Tier 3 | Use `pack` / `unpack` in a fully custom `run()` |
| Cancellation | Subprocess is killed; use atomic writes for safety |
| Source control | Your block `.py` files are git-tracked (ADR-039); branch switch reloads the palette |
| Lineage recording | Framework writes lineage rows externally; your `Block.run` contract is unchanged (ADR-038) |
