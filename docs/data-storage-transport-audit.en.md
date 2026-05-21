# SciStudio Data Storage and Transport Audit Report (English)

Audit date: 2026-04-11  
Scope: `docs/architecture/ARCHITECTURE.md`, `docs/adr/ADR.md`, `src/scistudio/**`, `packages/scistudio-blocks-*/**`  
Method: read-only audit, no business-code changes

## Executive Summary

The main conclusions are:

1. The real runtime boundary is no longer the older “engine injects `ViewProxy`” model that still appears in older docs. The current implementation sends JSON wire payloads across the process boundary, and the worker reconstructs typed `DataObject` / `Collection` instances with `storage_ref`. Payload data is only read when code later calls `to_memory()` or `view()`. Evidence: `src/scistudio/engine/runners/worker.py:43-91`, `src/scistudio/core/types/serialization.py:93-225`, aligned with newer ADR text in `docs/adr/ADR.md:4659-4705`, `4722-4726`, `5108-5113`.
2. “Lazy by default” is only partially true. It is mostly true at the scheduler/worker transport boundary, but many loaders, utilities, process blocks, and plugin blocks still materialize full data eagerly inside the worker.
3. Laziness is not enforced uniformly by the framework. In practice it depends on file format and block implementation.
4. There are several implementation gaps that are more than documentation drift: `SaveData` cannot reliably export storage-backed core objects; `LoadData(core_type='Series')` drops payload; `LoadPeakTable` stores a `pandas.DataFrame` inside JSON-oriented `user` metadata; and raw-file / artifact “path handle” semantics are broken by auto-flush copying the actual file at block boundaries.

## Design Intent and Documentation State

### Core intent

The architecture principles say:

- `Lazy by default`: data objects should hold references, not payloads.  
  `docs/architecture/ARCHITECTURE.md:28-35`

This is clearly aimed at keeping very large datasets on disk until a block explicitly requests access.

### Older documentation model

Older docs still describe an injected-`ViewProxy` system:

- `docs/architecture/ARCHITECTURE.md:331-362`
- `docs/architecture/ARCHITECTURE.md:613-618`
- `docs/adr/ADR.md:210-239`

Those sections say blocks receive `ViewProxy`, and the worker reconstructs `ViewProxy`.

### Newer documentation model

Newer ADR addenda describe a different runtime:

- worker reconstructs typed `DataObject`, not `ViewProxy`:  
  `docs/adr/ADR.md:4659-4705`, `4722-4726`
- `ViewProxy` is retained only as an opt-in helper via `item.view()`:  
  `docs/adr/ADR.md:5108-5113`

So the documentation set currently mixes two generations of architecture. The code matches the newer model.

## Actual End-to-End Data Flow

### 1. Loading stage

`IOBlock.run()` wraps input-direction results into `Collection` and forwards output-direction blocks to `save()`:  
`src/scistudio/blocks/io/io_block.py:105-145`

#### Core `LoadData`

The real behavior is format-dependent:

| Type / Format | Real implementation | Full in-memory load? |
|---|---|---|
| `Array` + `.zarr` | metadata-only object with `storage_ref` | No |
| `Array` + `.npy/.npz/.parquet` | reads full ndarray into `_data` | Yes |
| `DataFrame` + csv/tsv/parquet/json | reads full `pyarrow.Table` into `_arrow_table` | Yes |
| `Series` + tabular | returns metadata-only `Series(...)`, payload not preserved | Payload lost |
| `Text` | `read_text()` | Yes |
| `Artifact` | keeps `file_path`, no `storage_ref` | Not yet, but copied later |

Evidence:

- `src/scistudio/blocks/io/loaders/load_data.py:233-339`
- `src/scistudio/blocks/io/loaders/load_data.py:342-427`
- `src/scistudio/blocks/io/loaders/load_data.py:430-468`
- `src/scistudio/blocks/io/loaders/load_data.py:488-562`

#### Plugin loaders

Representative cases:

- Imaging `LoadImage` loads both TIFF and Zarr eagerly through `tf.asarray()` or `np.asarray(arr_node[...])`:  
  `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/io/load_image.py:76-141`
- LCMS `LoadMzMLFiles` returns `MSRawFile(file_path=path, meta=...)`, which looks like a handle-only design:  
  `packages/scistudio-blocks-lcms/src/scistudio_blocks_lcms/io/load_mzml_files.py:100-113`
- LCMS `LoadPeakTable` stores a pandas frame copy in `table.user["pandas_df"]`:  
  `packages/scistudio-blocks-lcms/src/scistudio_blocks_lcms/io/load_peak_table.py:123-134`

### 2. How data moves between blocks

The scheduler stores runner results directly in `_block_outputs`:  
`src/scistudio/engine/scheduler.py:292-301`

Downstream inputs are gathered by simply forwarding the stored output entry by port name:  
`src/scistudio/engine/scheduler.py:322-346`

`LocalRunner` sends worker input as pure JSON:  
`src/scistudio/engine/runners/local.py:97-108`  
`src/scistudio/engine/runners/process_handle.py:145-170`

So the real path is:

1. worker serializes outputs into wire-format dicts
2. scheduler stores those dicts
3. downstream execution sends those dicts to a new worker over stdin JSON
4. the new worker reconstructs typed `DataObject` instances there

This means the engine mostly stores lightweight wire payloads, not live typed objects.

### 3. How data is processed inside blocks

`ProcessBlock.run()` is per-item at the framework loop level and auto-flushes each result:  
`src/scistudio/blocks/process/process_block.py:123-174`

But many APIs still materialize eagerly:

- `Array.__array__()` calls `to_memory()`: `src/scistudio/core/types/array.py:120-134`
- `Array.sel()` materializes storage-backed arrays before slicing: `src/scistudio/core/types/array.py:165-172`, `211-223`
- `iterate_over_axes()` starts with `source.to_memory()`: `src/scistudio/utils/axis_iter.py:151-188`
- `broadcast_apply()` is explicitly in-memory-only: `src/scistudio/utils/broadcast.py:68-75`
- SRS baseline explicitly does `np.asarray(item.to_memory(), dtype=np.float64)`: `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/preprocess/srs_baseline.py:76-97`

`CodeBlock` is even more explicit:

- single-item `Collection` -> `view().to_memory()`
- multi-item `Collection` -> `LazyList`

Evidence:

- `src/scistudio/blocks/code/code_block.py:24-37`
- `src/scistudio/blocks/code/code_block.py:105-125`
- `src/scistudio/blocks/code/lazy_list.py:33-35`

Important nuance: `LazyList` is item-lazy, not chunk-lazy. Accessing an item still loads the full item through `to_memory()`.

### 4. Saving, auto-flush, and checkpoints

Intermediate persistence relies on `_auto_flush()`:  
`src/scistudio/blocks/base/block.py:350-403`

The worker calls `_auto_flush()` before serializing outputs:  
`src/scistudio/engine/runners/worker.py:94-177`

The default intermediate output directory comes from `LocalRunner._derive_output_dir()`:  
`src/scistudio/engine/runners/local.py:23-39`

Default path:

`<project_dir>/data/zarr/<workflow_id>/<block_id>`

But that directory can contain `.zarr`, `.parquet`, text files, binary artifacts, or composite directories. The name is misleading.

Checkpoints also persist mostly wire-format references rather than live objects:  
`src/scistudio/engine/checkpoint.py:26-83`

On restore, the scheduler does not use the deprecated `ViewProxy` deserialization path. It injects wire-format dicts back into `_block_outputs` and lets the worker reconstruct typed objects later:  
`src/scistudio/engine/checkpoint.py:86-122`  
`src/scistudio/engine/scheduler.py:934-971`

## Direct Answer: Is data fully loaded into memory?

Not always, but often.

The accurate statement is:

- usually not in the scheduler/engine process
- usually not across the process boundary
- often yes inside worker-side loaders and algorithm blocks

Most obviously eager paths include:

- `LoadData(Array .npy/.npz/.parquet)`
- `LoadData(DataFrame csv/tsv/parquet/json)`
- `LoadImage(TIFF/Zarr)`
- many algorithm blocks using `to_memory()` or `np.asarray(...)`

## Key Gaps and Violations of the Design Philosophy

### High priority

1. **Core architecture docs still describe injected `ViewProxy`, but the runtime now uses typed `DataObject`.**  
   Old docs: `docs/architecture/ARCHITECTURE.md:331-362`, `618`. Newer ADR + code: `docs/adr/ADR.md:4659-4705`, `4722-4726`, `5108-5113`, and `src/scistudio/engine/runners/worker.py:43-91`.

2. **“Lazy by default” is not consistently realized.**  
   Counterexamples include eager `LoadData` paths for `.npy/.npz/.csv/.parquet/.json`, eager imaging TIFF/Zarr loading, and `Array.sel()` materializing full arrays before slicing. Evidence: `src/scistudio/blocks/io/loaders/load_data.py:233-427`, `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/io/load_image.py:76-141`, `src/scistudio/core/types/array.py:165-223`.

3. **`SaveData` cannot reliably export storage-backed core objects.**  
   It depends on `get_in_memory_data()` or `_arrow_table`, while downstream workers often only reconstruct storage-backed typed objects. Evidence: `src/scistudio/blocks/io/savers/save_data.py:271-425`, `597-625`; `src/scistudio/core/types/base.py:350-381`.

4. **`LoadData(core_type='Series')` loses payload.**  
   `_load_series()` reads the table indirectly, then returns a new `Series(...)` without `_data`, `_arrow_table`, or `storage_ref`. Evidence: `src/scistudio/blocks/io/loaders/load_data.py:456-468`.

5. **Mutable `user` metadata bypasses validation, and `LoadPeakTable` already stores a non-JSON object there.**  
   JSON requirement: `src/scistudio/core/types/base.py:193-206`; mutable dict exposure: `230-237`; plugin example: `packages/scistudio-blocks-lcms/src/scistudio_blocks_lcms/io/load_peak_table.py:123-134`; serialization assumes JSON-clean `user`: `src/scistudio/core/types/serialization.py:281-305`.

6. **Raw-file / artifact handle semantics are broken at block boundaries.**  
   `MSRawFile` is intended as path + header metadata only: `packages/scistudio-blocks-lcms/src/scistudio_blocks_lcms/types.py:24-35`. But `_auto_flush()` plus `Artifact.get_in_memory_data()` ends up reading bytes from the original file and copying them into managed intermediate storage. Evidence: `src/scistudio/blocks/base/block.py:374-403`, `src/scistudio/core/types/artifact.py:44-48`.

### Medium priority

1. **Imaging Zarr loading clearly violates the large-data lazy-loading goal.**  
   Evidence: `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/io/load_image.py:97-140`.

2. **CodeBlock is asymmetric across languages.**  
   Python sees real Python objects, but R/Julia runners reserialize with `default=str`, so complex objects can degrade into strings. Evidence: `src/scistudio/blocks/code/runners/python_runner.py:32-84`, `r_runner.py:36-38,91-92`, `julia_runner.py:35-36,92-93`.

3. **Persistence atomicity is inconsistent.**  
   `FilesystemBackend` and `ZarrBackend` use temp-then-rename: `src/scistudio/core/storage/filesystem.py:31-68`, `src/scistudio/core/storage/zarr_backend.py:25-60`. `ArrowBackend` does not provide the same level of atomic write, and `CompositeStore` explicitly documents non-atomic multi-slot writes: `src/scistudio/core/storage/arrow_backend.py:21-45`, `src/scistudio/core/storage/composite_store.py:58-76`.

## Overall Judgment

SciStudio has already built two important foundations well:

- lightweight reference-style cross-process transport
- typed `DataObject` reconstruction inside worker subprocesses

Those parts are coherent and mostly aligned with the newer ADR addenda.

The real weakness is that “lazy by default” has not become a stable end-to-end system property. It behaves more like a partial capability: strong at the transport boundary, inconsistent at ingestion, frequently abandoned inside algorithm blocks, and not fully supported by the generic export layer.

If the whole audit is compressed into one sentence:

> SciStudio’s transport layer is mostly reference-based now, but its load, processing, and export layers still contain widespread eager materialization, payload-loss edge cases, and multiple mismatches with the stated design philosophy.
