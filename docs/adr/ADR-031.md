## ADR-031: Data Object Reference-Only Contract, ViewProxy Elimination, and Lazy Loading Enforcement

**Status**: accepted (Phase 1+2+3 implemented; Addendum 1+2 in progress)
**Date**: 2026-04-11 (Addendum 1: 2026-04-12, Addendum 2: 2026-04-12)
**Supersedes**: ADR-027 Addendum 1 (~~proposed~~ → **deprecated**)
**Amends**: ADR-007 (implementation alignment), ADR-017 (transport contract), ADR-028 (IOBlock contract)

---

### 1. Purpose

This ADR addresses a **critical divergence between architectural design and implementation** across the data storage, transport, and access layers. An independent audit (ref: `docs/data-storage-transport-audit.en.md`, 2026-04-11) confirmed that the "lazy by default" principle from ADR-007 is systematically violated in practice.

This ADR:

1. Establishes **DataObject as the single, definitive data reference type** — no secondary accessor classes.
2. **Eliminates `ViewProxy`** entirely — its methods are absorbed into DataObject/Array.
3. **Prohibits the `_data` / `_arrow_table` in-memory backdoor** on DataObject instances that cross block boundaries.
4. **Requires IOBlock loaders to persist data to storage and return reference-only objects.**
5. **Exempts Artifact/file-handle types from auto-flush** — path-only transport.
6. **Deprecates ADR-027 Addendum 1** in its entirety; correct decisions are restated here.
7. **Aligns documentation** to a single coherent model.

### 2. Context

#### 2.1 Design intent (ADR-007, ADR-017, ADR-027)

The architecture specifies:

> DataObject instances are lightweight wrappers (~KB) holding a StorageReference. Blocks never receive raw data directly. — ADR-007

> No scientific data crosses the process boundary. Only StorageReference pointers (~100 bytes each) and config dicts cross. — ADR-017

> `worker.reconstruct_inputs` returns typed DataObject instances, not ViewProxy. Lazy loading is preserved at the method level. — ADR-027 Addendum 1

#### 2.2 Actual implementation state (audit findings)

The independent audit (`docs/data-storage-transport-audit.en.md`) found:

1. **Almost all loaders are eager.** Only `LoadData(.zarr)` returns a storage-backed reference. All other paths (`LoadImage` TIFF/Zarr, `LoadData` .npy/.csv/.parquet/.json, plugin loaders) read full data into memory and attach it to an undeclared `_data` or `_arrow_table` attribute. Evidence: `load_data.py:233-427`, `load_image.py:76-141`.

2. **`_data` is not part of the DataObject contract.** The `DataObject.__init__` constructor has four declared slots: `framework`, `meta`, `user`, `storage_ref`. The `_data` attribute appears nowhere in the base class. It is monkey-patched onto instances by loader code: `img._data = np.asarray(...)`. The base class's `get_in_memory_data()` legitimizes this via `hasattr(self, "_data")` — a contract violation that the framework itself endorses.

3. **ViewProxy is vestigial.** ADR-027 Addendum 1 demoted ViewProxy from "engine-injected input type" to "opt-in helper via `item.view()`". In practice, **zero package-level blocks call `item.view()`**. ViewProxy's sole runtime role is as an unnecessary intermediary in `DataObject.to_memory()` → `self.view().to_memory()`. The class adds indirection without value.

4. **The transport layer is reference-based, but load/process/export are not.** The scheduler→worker JSON wire protocol correctly transmits StorageReference pointers. But data enters the system as in-memory blobs (load), gets processed as in-memory blobs (process), and gets exported from in-memory blobs (save). The reference-based transport is sandwiched between eager endpoints.

5. **SaveData cannot reliably export storage-backed objects.** `_save_array()` calls `obj.get_in_memory_data()`, which succeeds only if `_data` is set. A storage-backed Array (reconstructed in worker with only `storage_ref`) has no `_data`, causing `get_in_memory_data()` to raise. Evidence: `save_data.py:280-348`, `base.py:350-362`.

6. **`LoadData(Series)` loses payload.** `_load_series()` returns a `Series()` with neither `_data`, `_arrow_table`, nor `storage_ref`. The data is silently discarded. Evidence: `load_data.py:456-468`.

7. **`LoadPeakTable` stores pandas DataFrame in `user` metadata.** The `user` dict requires JSON-serializability per ADR-017. A pandas DataFrame is not JSON-serializable. This silently breaks cross-process transport. Evidence: `load_peak_table.py:123-134`.

8. **Artifact file semantics are broken by auto-flush.** `MSRawFile` is designed as a path handle, but `_auto_flush()` calls `get_in_memory_data()` which reads the file's raw bytes, then writes them to managed storage. The original file semantics are lost. Evidence: `block.py:374-403`, `artifact.py:44-48`.

9. **`Array.sel()` materializes full data before slicing.** The method that should enable lazy partial reads (`sel(z=5)`) starts by calling `self.to_memory()` to load the entire array. Evidence: `array.py:165-223`.

10. **Documentation mixes two generations.** `ARCHITECTURE.md:331-362` describes the old ViewProxy-injection model. `ADR.md:4659-5135` (ADR-027 Addendum 1) describes typed DataObject reconstruction. The code matches the newer model, but the architectural docs still reference the old one.

#### 2.3 Why ADR-027 Addendum 1 is deprecated

ADR-027 Addendum 1 made several correct observations but stopped short of the necessary conclusion:

- **Correct**: worker should return typed DataObject, not ViewProxy.
- **Correct**: `_reconstruct_extra_kwargs` / `_serialise_extra_metadata` hooks are the right per-class reconstruction pattern.
- **Correct**: Meta Pydantic constraints (frozen, JSON-round-trippable) are necessary.
- **Incorrect**: ViewProxy should be "demoted to opt-in helper." It should be **deleted** — no block uses it, and its functionality belongs on DataObject directly.
- **Incomplete**: Did not address the `_data` backdoor, loader eagerness, SaveData breakage, or Artifact semantics.
- **Incomplete**: Did not establish DataObject as the single source of truth for data access methods.

This ADR supersedes ADR-027 Addendum 1 in full. Decisions that remain correct are restated below with updated rationale.

---

### 3. Decisions

#### D1. DataObject is the single data reference type (source of truth)

**D1.1 Type hierarchy and per-class responsibilities**

```
DataObject (base)
├── Array          — N-dimensional numeric data (images, spectra, tensors)
│   ├── Image      — 2D/3D images (plugin)
│   ├── Label      — segmentation masks (plugin, CompositeData subclass)
│   └── ...
├── DataFrame      — tabular data (columns + rows)
├── Series         — single-column data
├── Text           — string content
├── Artifact       — opaque file handle (PDF, binary, raw instrument files)
│   └── MSRawFile  — mass spec raw data (plugin)
└── CompositeData  — named slots of DataObjects
    └── Label      — raster + metadata slots (plugin)
```

**D1.2 DataObject base class contract**

DataObject holds exactly four declared slots:
- `_framework: FrameworkMeta` — identity and lineage
- `_meta: BaseModel | None` — typed metadata
- `_user: dict[str, Any]` — free-form metadata (JSON-serializable)
- `_storage_ref: StorageReference | None` — pointer to persisted data

**DataObject MUST NOT carry raw data payloads.** There is no `_data` attribute, no `_arrow_table` attribute, no in-memory data container of any kind on DataObject instances that cross block boundaries.

**DataObject provides these data access methods** (all route through `storage_ref` → backend):

| Method | Defined on | Behavior |
|--------|-----------|----------|
| `to_memory()` | **DataObject** | Materialize full data from storage. Emits 2GB size warning. |
| `get_in_memory_data()` | **DataObject** | Alias for `to_memory()`. Subclasses may override (Text, Artifact). |
| `slice(*args)` | **DataObject** | Backend-specific sub-selection (zarr indexing, arrow column filter, etc.) |
| `iter_chunks(chunk_size)` | **DataObject** | Yield successive chunks from storage. |

**D1.3 Array subclass contract**

Array adds geometry metadata and array-specific access methods. These are **declared constructor parameters**, not monkey-patched attributes:

| Attribute/Method | Defined on | Type | Notes |
|-----------------|-----------|------|-------|
| `axes` | **Array** (constructor) | `list[str]` | Named axes, e.g. `["z", "y", "x", "c"]` |
| `shape` | **Array** (constructor) | `tuple[int, ...] \| None` | Data dimensions |
| `dtype` | **Array** (constructor) | `str \| None` | Element type |
| `chunk_shape` | **Array** (constructor) | `tuple[int, ...] \| None` | Storage chunk hint |
| `sel(**kwargs)` | **Array** | `-> Array` | Partial read along named axes. Reads from storage, not `_data`. |
| `iter_over(axis)` | **Array** | `-> Iterator[Array]` | Yield slices along one axis. Each slice has `storage_ref` set. |
| `__array__(dtype)` | **Array** | `-> np.ndarray` | NumPy protocol. Calls `to_memory()`. |

**Key change**: `sel()` and `iter_over()` no longer stash results in `_data`. Slice results are persisted to a temporary zarr store and returned with `storage_ref` set. This maintains the reference-only contract even for derived slices.

**D1.4 DataFrame subclass contract**

| Attribute/Method | Defined on | Notes |
|-----------------|-----------|-------|
| `to_memory()` | Inherited from **DataObject** | Returns `pyarrow.Table` from arrow backend |
| `get_in_memory_data()` | Inherited from **DataObject** | Same as `to_memory()` |

**Key change**: No `_arrow_table` attribute. All data access goes through `storage_ref` → ArrowBackend. The `_arrow_table` pattern is eliminated.

**D1.5 Text subclass contract**

| Attribute/Method | Defined on | Notes |
|-----------------|-----------|-------|
| `content` | **Text** (constructor) | String content. Small enough to hold in memory. |
| `get_in_memory_data()` | **Text** (override) | Returns `self.content` directly. |

Text is exempt from the "no in-memory data" rule because text content is inherently small (~KB) and is part of the object's identity (e.g., a prompt string). `storage_ref` is optional for Text.

**D1.6 Artifact subclass contract**

| Attribute/Method | Defined on | Notes |
|-----------------|-----------|-------|
| `file_path` | **Artifact** (constructor) | Path to the opaque file on disk. |
| `mime_type` | **Artifact** (constructor) | MIME type string. |
| `get_in_memory_data()` | **Artifact** (override) | Reads bytes from `file_path`. |

Artifact uses **path-only transport** — `file_path` is the reference, not `storage_ref`. Artifact is exempt from auto-flush (D5). `_auto_flush()` skips Artifact instances with `file_path` set.

**D1.7 CompositeData subclass contract**

CompositeData holds named slots, each of which is a DataObject. Each slot independently follows the storage-ref contract. The CompositeStore backend handles recursive persistence.

#### D2. ViewProxy is deleted

The `ViewProxy` class (`src/scieasy/core/proxy.py`) is deleted entirely. Its functionality is absorbed into the type hierarchy as follows:

| ViewProxy method | New location | Notes |
|---|---|---|
| `to_memory()` | **DataObject**.`to_memory()` | Direct backend read via `_get_backend(self._storage_ref).read(...)`. Includes 2GB size warning. |
| `slice(*args)` | **DataObject**.`slice(*args)` | Direct backend call. |
| `iter_chunks(chunk_size)` | **DataObject**.`iter_chunks(chunk_size)` | Direct backend call. |
| `shape` property | **Array**.`shape` | Already a constructor parameter on Array. Not on DataObject. |
| `axes` property | **Array**.`axes` | Already a constructor parameter on Array. Not on DataObject. |
| `from_file(path)` | Removed | Use `Artifact(file_path=Path(path))` or construct DataObject with appropriate `storage_ref`. |
| `_get_backend(ref)` | Module-level utility in `scieasy.core.storage.backend_router` | Shared backend resolution, used by DataObject methods internally. |

**`DataObject.view()` is deleted.** There is no ViewProxy path. Block authors call methods directly on the typed instance:

```python
# OLD (via ViewProxy):
data = image.view().to_memory()        # indirection through ViewProxy
chunk = image.view().slice(0, 100)     # indirection through ViewProxy

# NEW (direct on DataObject/Array):
data = image.to_memory()               # DataObject method, direct backend call
sub = image.sel(z=5)                   # Array method, direct backend call
for chunk in image.iter_chunks(1024):  # DataObject method, direct backend call
    ...
```

#### D3. `_data` and `_arrow_table` are prohibited on cross-boundary DataObjects

**Rule**: Any DataObject returned from `Block.run()` (or `IOBlock.load()`) MUST have `storage_ref` set (or `file_path` for Artifact). The framework enforces this at the IOBlock level (D4) and at the worker auto-flush boundary.

**Transient in-memory data within a single block's `run()` is allowed.** A block may compute results in memory (e.g., CellPose producing a mask ndarray). The framework's existing `_auto_flush()` mechanism persists these to storage before the data crosses the process boundary. This behavior is unchanged.

**Per-class elimination of in-memory backdoors:**

| Class | Attribute removed | Current usage | Migration |
|-------|------------------|---------------|-----------|
| **Array** | `_data` (monkey-patched, not declared) | Set by loaders: `img._data = np.asarray(...)`. Checked by `Array.to_memory()`, `Array.sel()`, `get_in_memory_data()`. | Remove all `_data` assignments and `hasattr` checks. All data access routes through `storage_ref` → ZarrBackend. |
| **DataFrame** | `_arrow_table` (monkey-patched, not declared) | Set by loaders: `df._arrow_table = table`. Checked by `get_in_memory_data()`, `_dataframe_to_arrow_table()`. | Remove all `_arrow_table` assignments and checks. All data access routes through `storage_ref` → ArrowBackend. |
| **Series** | `_arrow_table` (inherited pattern from DataFrame) | Set inconsistently. `_load_series()` currently loses payload entirely. | Fix payload loss first (write to arrow backend). Then same migration as DataFrame. |
| **Text** | `content` (declared constructor parameter) | **Exempt.** Text content is small (~KB) and is part of the object's identity. `content` is a legitimate declared field, not a monkey-patched backdoor. | No change. |
| **Artifact** | `file_path` (declared constructor parameter) | **Exempt.** File path is the transport mechanism. | No change. See D5. |
| **CompositeData** | Per-slot `_data`/`_arrow_table` on slot objects | Each slot is independently a DataObject. | Recursive: each slot follows its own class's migration. |

**What `_auto_flush()` handles after this ADR**: Only transient outputs from ProcessBlock/CodeBlock/AppBlock `run()` methods — block authors who compute results in memory and don't explicitly persist them. The framework flushes these to storage before serialization. IOBlock loaders are expected to handle their own persistence (D4).

#### D4. IOBlock base class guarantees storage-ref; provides persistence helpers for loader authors

The `load()` signature changes to accept an `output_dir` parameter. The IOBlock base class provides two guarantees:

1. **Correctness guarantee**: After `load()` returns, the base class checks every DataObject. If `storage_ref` is missing, the base class auto-flushes to storage. **No DataObject without `storage_ref` ever crosses the block boundary.** This is a safety net — loader authors who return in-memory objects still produce correct results.

2. **Helper API**: The base class provides `persist_array()` and `persist_table()` helpers for loader authors who want streaming writes (constant memory). **Loader authors who know their data is large SHOULD use these helpers.** Loader authors who don't care can return in-memory objects and let the base class handle persistence.

**The framework guarantees correctness. The loader author controls optimality.** Loader authors know their data characteristics — a 1KB CSV doesn't need streaming; a 100G TIFF does.

**New `IOBlock` contract:**

```python
class IOBlock(Block):
    @abstractmethod
    def load(self, config: BlockConfig, output_dir: str) -> DataObject | Collection:
        """Load data from source.

        Implementations may EITHER:

        (a) Return an in-memory DataObject (simple path):
            The base class auto-persists it to storage. Works for small/medium
            files. Will OOM on very large files.

            return Image(_data=np.array(...), axes=["y","x"], shape=shape, dtype=dtype)

        (b) Write to storage directly and return a reference (streaming path):
            Use self.persist_array() / self.persist_table() helpers for
            constant-memory writes. Required for large files.

            ref = self.persist_array(chunks_iter, shape, dtype, output_dir)
            return Image(storage_ref=ref, axes=["y","x"], shape=shape, dtype=dtype)

        Artifact subclasses are exempt — return with file_path, no storage write needed.
        """
        ...

    # -- persistence helpers for loader authors ---

    def persist_array(
        self, data_or_iterator, shape, dtype, output_dir, chunks=None,
    ) -> StorageReference:
        """Write array data to zarr storage, return StorageReference.

        data_or_iterator may be:
        - numpy ndarray (written in one shot)
        - iterator of (slice, chunk_array) tuples (streaming, constant memory)

        Memory usage: O(one chunk) for iterator mode, O(full array) for ndarray mode.
        """
        ...

    def persist_table(self, table, output_dir) -> StorageReference:
        """Write Arrow table to storage, return StorageReference."""
        ...

    # -- run() with auto-flush safety net ---

    def run(self, inputs, config):
        if self.direction == "input":
            output_dir = get_output_dir()
            result = self.load(config, output_dir=output_dir)
            if not isinstance(result, Collection):
                result = Collection(items=[result], item_type=type(result))
            # Safety net: auto-flush any item without storage_ref
            for item in result:
                if isinstance(item, DataObject) and item.storage_ref is None:
                    if not (isinstance(item, Artifact) and item.file_path is not None):
                        self._auto_flush(item)  # persist to zarr/arrow, set storage_ref
            return {self._resolved_load_output_port_name(): result}
```

**Example: LoadImage TIFF — streaming path (large files, constant memory):**

```python
def load(self, config, output_dir=None):
    path = Path(config.get("path"))

    with tifffile.TiffFile(str(path)) as tf:
        page0 = tf.pages[0]
        shape = (len(tf.pages), *page0.shape) if len(tf.pages) > 1 else page0.shape
        dtype = page0.dtype
        axes = _infer_axes(tf)

        # Stream page-by-page — memory = O(one page)
        def page_chunks():
            for i, page in enumerate(tf.pages):
                yield (i, page.asarray())

        ref = self.persist_array(page_chunks(), shape, dtype, output_dir)

    return Image(axes=axes, shape=shape, dtype=dtype, storage_ref=ref)
    # ← ~KB object. No _data, no in-memory payload.
```

**Example: LoadData CSV — simple path (small files, base class handles persistence):**

```python
def _load_dataframe(self, path, config, output_dir):
    import pyarrow.csv as pcsv
    table = pcsv.read_csv(str(path))
    # Return in-memory — base class will auto-persist via _auto_flush
    df = DataFrame()
    df._arrow_table = table  # OK for simple path; base class flushes this
    return df
```

**Example: LoadData CSV — streaming path (large files):**

```python
def _load_dataframe(self, path, config, output_dir):
    import pyarrow.csv as pcsv
    table = pcsv.read_csv(str(path))
    ref = self.persist_table(table, output_dir)
    return DataFrame(storage_ref=ref)
    # ← Reference only. No _arrow_table.
```

**Loader author's choice matrix:**

| Data size | Approach | Memory | Code complexity |
|-----------|----------|--------|-----------------|
| Small (< 1GB) | Return in-memory, base class auto-flushes | O(file size) | Minimal — same as today |
| Large (> 1GB) | Use `persist_array()` / `persist_table()` streaming helpers | O(chunk size) | Slightly more — iterate chunks |

**All 6 loader classes should be updated to use the new `load(config, output_dir)` signature.** Whether each individual loader function uses the simple path or streaming path is the loader author's decision based on expected data size:

| Loader | Recommended path | Rationale |
|--------|-----------------|-----------|
| `LoadImage` TIFF | Streaming | Scientific images routinely exceed 1GB |
| `LoadImage` Zarr | Reference | Zarr is already chunked storage — reference existing store |
| `LoadData` Array .zarr | Reference | Already lazy (only correct loader today) |
| `LoadData` Array .npy/.npz | Simple | Typically small; streaming .npy is not straightforward |
| `LoadData` DataFrame csv/parquet | Simple or Streaming | Author's choice based on expected table size |
| `LoadData` Text | Simple | Text files are small |
| `LoadData` Artifact | Exempt | Path-only transport (D5) |
| LCMS loaders | Simple | Domain-specific, typically small tables |

#### D5. Artifact and file-handle types skip auto-flush

`Artifact` and its subclasses (e.g., `MSRawFile`) use `file_path` as their transport mechanism, not `storage_ref`. They represent opaque files that should not be read into memory or copied into managed storage.

**`_auto_flush()` is modified to skip Artifact instances that have `file_path` set:**

```python
@staticmethod
def _auto_flush(obj: Any) -> Any:
    if not isinstance(obj, DataObject):
        return obj
    # NEW: Artifact with file_path uses path-only transport
    from scieasy.core.types.artifact import Artifact
    if isinstance(obj, Artifact) and obj.file_path is not None:
        return obj
    # ... existing flush logic ...
```

**Serialization**: `_serialise_one()` already handles Artifact via `_serialise_extra_metadata()` which writes `file_path` to the metadata sidecar. `_reconstruct_one()` already handles it via `_reconstruct_extra_kwargs()` which restores `file_path`. No changes needed to the wire protocol.

**SaveData for Artifact**: `_save_artifact()` copies the file via `shutil.copy2()`. This is correct behavior — it copies the file to the user-chosen path, not to managed storage.

#### D6. `get_in_memory_data()` per-class behavior

The current `get_in_memory_data()` on `DataObject` uses `hasattr` to check for undeclared attributes. This is replaced with a clean per-class dispatch:

**DataObject (base class):**
```python
def get_in_memory_data(self) -> Any:
    """Materialize data from storage for persistence/export."""
    return self.to_memory()  # storage_ref → backend → read
```

**Per-class overrides:**

| Class | `get_in_memory_data()` behavior | Rationale |
|-------|-------------------------------|-----------|
| **DataObject** (base) | `return self.to_memory()` | Default: read from storage via backend. |
| **Array** | Inherited from DataObject | `to_memory()` → ZarrBackend.read() → `np.ndarray` |
| **DataFrame** | Inherited from DataObject | `to_memory()` → ArrowBackend.read() → `pyarrow.Table` |
| **Series** | Inherited from DataObject | `to_memory()` → ArrowBackend.read() → `pyarrow.Table` (single column) |
| **Text** (override) | `return self.content` | Text content is in-memory by design (~KB). No storage round-trip needed. |
| **Artifact** (override) | `return self.file_path.read_bytes()` | Reads from original file. Not from managed storage. |
| **CompositeData** | Inherited from DataObject | `to_memory()` → CompositeStore.read() → reconstructs slot dict |

**Removed**: The `hasattr(self, "_data")` and `hasattr(self, "_arrow_table")` checks in the base class. No monkey-patched attributes are consulted.

This means SaveData's `_save_array()`, `_save_dataframe()`, etc. all work correctly with storage-backed objects — they call `get_in_memory_data()` → `to_memory()` → backend read.

#### D7. Worker reconstruction contract (restated from ADR-027 Add1)

`worker.reconstruct_inputs()` returns **typed DataObject instances** (e.g., `Image`, `DataFrame`), not `ViewProxy`. This decision from ADR-027 Addendum 1 is **correct and retained**.

The reconstruction hooks remain:
- `cls._reconstruct_extra_kwargs(metadata)` — per-base-class kwargs extraction
- `cls._serialise_extra_metadata(obj)` — per-base-class metadata serialization

The Meta Pydantic constraints remain:
- Frozen, no `PrivateAttr`, all fields must round-trip through `model_dump_json` / `model_validate_json`

#### D8. Checkpoint deserialization updated

`checkpoint.py`'s `deserialize_intermediate_refs()` currently constructs `ViewProxy` instances. This function is rewritten to construct typed `DataObject` instances using the same `_reconstruct_one()` path as the worker.

If type resolution fails (missing plugin), fall back to a base `DataObject(storage_ref=ref)` rather than a `ViewProxy`.

#### D9. Documentation is unified

All references to the old "engine injects ViewProxy" model are removed from:
- `docs/architecture/ARCHITECTURE.md:331-362` (and line 618)
- `docs/adr/ADR.md` ADR-007 discussion text
- Block SDK guide

The canonical documentation model is:
- Blocks receive **typed DataObject instances** with `storage_ref` set
- Data is lazy — `to_memory()` / `sel()` / `iter_chunks()` trigger reads on demand
- ViewProxy does not exist

---

### 4. Impact Scope

#### 4.1 Files deleted

| File | Reason |
|------|--------|
| `src/scieasy/core/proxy.py` | ViewProxy class eliminated |
| `tests/core/test_proxy.py` | Tests for deleted class |
| `tests/core/test_proxy_multi_backend.py` | Tests for deleted class |

#### 4.2 Core type system changes

**DataObject base class** (`src/scieasy/core/types/base.py`):

| Change | Detail |
|--------|--------|
| Delete `view()` method | Returns ViewProxy — ViewProxy no longer exists (D2) |
| Rewrite `to_memory()` | Direct: `_get_backend(self._storage_ref).read(self._storage_ref)`. Add 2GB size warning from ViewProxy. |
| Add `slice(*args)` | New method: `_get_backend(self._storage_ref).slice(self._storage_ref, *args)` |
| Add `iter_chunks(chunk_size)` | New method: `yield from _get_backend(self._storage_ref).iter_chunks(self._storage_ref, chunk_size)` |
| Rewrite `get_in_memory_data()` | Remove `hasattr(self, "_data")` and `hasattr(self, "_arrow_table")` checks. New body: `return self.to_memory()` (D6) |
| Remove `TYPE_CHECKING` ViewProxy import | Line 34: `from scieasy.core.proxy import ViewProxy` |

**Array subclass** (`src/scieasy/core/types/array.py`):

| Change | Detail |
|--------|--------|
| Remove `to_memory()` override | Delete the `if self._storage_ref is None and hasattr(self, "_data")` backdoor. Inherit DataObject's `to_memory()`. |
| Rewrite `sel(**kwargs)` | Remove `hasattr(self, "_data")` check (line 214). Always read from storage: `full_data = self.to_memory()`. Persist slice result to temp zarr with `storage_ref` instead of stashing in `_data`. |
| Rewrite `iter_over(axis)` | Delegates to `sel()` per-index — inherits sel()'s storage-based behavior. |
| `__array__()` | No change — already calls `self.to_memory()`. |
| `shape`, `axes`, `dtype` | No change — already declared constructor parameters. |

**DataFrame subclass** (`src/scieasy/core/types/dataframe.py`):

| Change | Detail |
|--------|--------|
| No `_arrow_table` attribute | All data access through inherited `to_memory()` → ArrowBackend |

**Text subclass** (`src/scieasy/core/types/text.py`):

| Change | Detail |
|--------|--------|
| `get_in_memory_data()` override | Returns `self.content`. No storage round-trip. (Existing behavior, no change.) |

**Artifact subclass** (`src/scieasy/core/types/artifact.py`):

| Change | Detail |
|--------|--------|
| `get_in_memory_data()` override | Returns `self.file_path.read_bytes()`. (Existing behavior, no change.) |
| Exempt from auto-flush | See D5. |

**CompositeData** (`src/scieasy/core/types/composite.py`):

| Change | Detail |
|--------|--------|
| Per-slot compliance | Each slot is an independent DataObject — follows its own class's contract. CompositeStore handles recursive persistence. |

#### 4.3 IOBlock and loader changes

| File | Changes |
|------|---------|
| `src/scieasy/blocks/io/io_block.py` | Change `load()` signature to `load(self, config, output_dir)`. Add `persist_array()` and `persist_table()` helper methods. Update `run()` to pass `output_dir` and auto-flush any item without `storage_ref` (D4 safety net). |
| `src/scieasy/blocks/io/loaders/load_data.py` | Update `load()` to accept `output_dir`. Per-function changes: `_load_array .zarr` (already lazy, no change). `_load_array .npy/.npz/.parquet` (simple path — base class auto-flushes). `_load_dataframe` (simple or streaming — author's choice). `_load_series` (fix payload loss — must write to arrow). `_load_text` (simple path). `_load_artifact` (exempt, path-only D5). `_load_composite_data` (recursive, pass output_dir). |
| `packages/scieasy-blocks-imaging/.../load_image.py` | Streaming path for `_load_tiff` (page-by-page via `persist_array()`). `_load_zarr` (reference existing zarr store, no copy). |
| `packages/scieasy-blocks-lcms/.../load_mzml_files.py` | Update `load()` signature. MSRawFile is Artifact subclass — path-only, exempt. |
| `packages/scieasy-blocks-lcms/.../load_peak_table.py` | Fix: write DataFrame to arrow via `persist_table()`, remove pandas from `user` dict. |
| `packages/scieasy-blocks-lcms/.../load_mid_table.py` | Update `load()` signature, use simple or streaming path. |
| `packages/scieasy-blocks-lcms/.../load_sample_metadata.py` | Update `load()` signature, use simple path. |
| `src/scieasy/blocks/io/savers/save_data.py` | Remove `_arrow_table` check. Phase 3: add chunked export for Parquet/CSV/Zarr. |
| `packages/scieasy-blocks-imaging/.../save_image.py` | No immediate change. Phase 3: add chunked TIFF write. |
| `packages/scieasy-blocks-lcms/.../save_table.py` | Update `save()` to use `get_in_memory_data()` consistently. |

#### 4.4 Block framework changes

| File | Changes |
|------|---------|
| `src/scieasy/blocks/base/block.py` | Remove `_is_view_proxy()` helper. Update `validate()` to remove ViewProxy branch. Update `_auto_flush()` to skip Artifact (D5). |
| `src/scieasy/blocks/process/process_block.py` | No change — already calls `_auto_flush()` on outputs. |
| `src/scieasy/blocks/process/utils.py` | Remove ViewProxy isinstance check in `to_arrow()`. |
| `src/scieasy/blocks/app/bridge.py` | Remove ViewProxy isinstance check. |
| `src/scieasy/blocks/process/builtins/split.py` | Replace `_arrow_table` assignments with `get_in_memory_data()` + storage write. |
| `src/scieasy/blocks/process/builtins/merge.py` | Same pattern. |

#### 4.5 Engine changes

| File | Changes |
|------|---------|
| `src/scieasy/engine/checkpoint.py` | Rewrite `deserialize_intermediate_refs()` to construct DataObject, not ViewProxy (D8). |
| `src/scieasy/engine/runners/worker.py` | Remove ViewProxy references from docstrings. No structural changes — already returns typed DataObject. |
| `src/scieasy/engine/runners/local.py` | `serialise_inputs()` added by PR #623 (P0 fix) remains as defense-in-depth. |
| `src/scieasy/engine/scheduler.py` | Remove ViewProxy comments. |

#### 4.6 SaveData and saver changes

SaveData is a **sink block** — it reads data from storage and writes to a user-chosen file format.

**Audit finding §2.2.5: SaveData currently cannot reliably export storage-backed objects.** `_save_array()` calls `obj.get_in_memory_data()`, which checks `hasattr(self, "_data")`. A storage-backed Array reconstructed in the worker has `storage_ref` set but no `_data`, so `get_in_memory_data()` raises `ValueError`. The same applies to `_dataframe_to_arrow_table()` which checks for `_arrow_table`.

**This is resolved by D6**: `get_in_memory_data()` is rewritten to route through `to_memory()` → storage backend read. SaveData works correctly with storage-backed objects without SaveData-specific code changes in Phase 1/2.

**Phase 3 optimization**: For large data, SaveData should read from storage chunk-by-chunk and write to the target format incrementally, avoiding full materialization. This is format-dependent — Parquet and Zarr support chunked writes; NPY and CSV do not.

| File | Changes |
|------|---------|
| `src/scieasy/blocks/io/savers/save_data.py` | Phase 1/2: Remove `_arrow_table` check in `_dataframe_to_arrow_table()`. All paths work via `get_in_memory_data()` → `to_memory()` → storage read. Phase 3: Add chunked export paths for formats that support it (Parquet, Zarr). |
| `packages/scieasy-blocks-imaging/.../save_image.py` | Phase 1/2: No change needed — SaveImage calls `to_memory()` which now routes through storage. Phase 3: Add chunked TIFF write (page-by-page from zarr). |

**Per-format SaveData behavior after this ADR:**

| Format | Phase 1/2 (correctness) | Phase 3 (streaming) |
|--------|------------------------|---------------------|
| `.zarr` | `get_in_memory_data()` → full read → zarr write | Direct zarr-to-zarr copy (zero materialization) |
| `.npy` | `get_in_memory_data()` → full read → `np.save()` | Full read required (NPY format is not chunked) |
| `.parquet` | `get_in_memory_data()` → full read → `pq.write_table()` | Chunked: read row groups from arrow → write row groups to parquet |
| `.csv` | `get_in_memory_data()` → full read → `write_csv()` | Chunked: read batches from arrow → write batches to CSV |
| TIFF | `get_in_memory_data()` → full read → `tifffile.imwrite()` | Chunked: read z-planes from zarr → write pages to TIFF |

#### 4.7 Utility changes

| File | Changes |
|------|---------|
| `src/scieasy/utils/axis_iter.py` | Replace `result._data = data` with persist-to-zarr + set storage_ref. |
| `src/scieasy/utils/broadcast.py` | Update ViewProxy references in docstrings/warnings. |

#### 4.8 Test changes

| File | Changes |
|------|---------|
| `tests/core/test_proxy.py` | Delete entirely. |
| `tests/core/test_proxy_multi_backend.py` | Delete entirely. |
| `tests/core/test_dataobject_extended.py` | Update: assert `storage_ref is not None` instead of `_data` checks. |
| `tests/core/test_storage.py` | Remove ViewProxy construction. |
| `tests/engine/test_checkpoint.py` | Update: assert DataObject instead of ViewProxy from deserialization. |
| `tests/engine/test_worker.py` | Remove ViewProxy assertion (already asserts `not isinstance(x, ViewProxy)`). |
| `tests/engine/test_worker_typed_reconstruction.py` | Remove ViewProxy imports and negative assertions. |
| `tests/blocks/test_block_base.py` | Remove ViewProxy validation tests. |
| `tests/blocks/test_process_utils.py` | Remove ViewProxy mock. |
| `tests/blocks/io/test_load_data.py` | Update: assert `storage_ref is not None` instead of `_data`/`_arrow_table` checks. |

#### 4.9 Documentation changes

| File | Changes |
|------|---------|
| `docs/architecture/ARCHITECTURE.md` | Remove ViewProxy-injection model (lines 331-362, 613-618). Update to DataObject-only model. |
| `docs/adr/ADR.md` (ADR-007) | Add note: "ViewProxy eliminated in ADR-031. Methods absorbed into DataObject." |
| `docs/adr/ADR.md` (ADR-027 Add1) | Mark as ~~deprecated~~ — superseded by ADR-031. |
| `docs/guides/block-sdk.md` | Update data access examples: `item.to_memory()` not `item.view().to_memory()`. |

---

### 5. Implementation Plan

#### Phase 1: Loader rewrite + core enforcement (all loaders write to storage directly)

1. **Change `IOBlock.load()` signature** — add `output_dir: str` parameter. Update `IOBlock.run()` to pass `output_dir` and enforce `storage_ref` on returned objects (D4).
2. **Rewrite all 6 loader classes (~12 functions)** to write directly to zarr/arrow storage and return reference-only DataObjects. Use streaming writes where the format supports it (TIFF page-by-page, CSV Arrow streaming, etc.).
3. **Artifact auto-flush skip** (D5) — `_auto_flush()` skips Artifact with `file_path`.
4. **Fix `_load_series()` payload loss** — write to arrow backend, return with `storage_ref`.
5. **Fix `LoadPeakTable` user-dict violation** — write DataFrame to arrow storage, not `user` dict.
6. **Update test fixtures** — mock loaders in `tests/` must comply with new `load()` signature.

#### Phase 2: ViewProxy elimination and `_data` cleanup

7. **Move `_get_backend()` and data access methods to DataObject** — `to_memory()`, `slice()`, `iter_chunks()`. Add 2GB size warning.
8. **Delete `ViewProxy` class** (`src/scieasy/core/proxy.py`) and `DataObject.view()` method.
9. **Rewrite `get_in_memory_data()`** — route through `to_memory()`, remove `hasattr(self, "_data")` / `_arrow_table` checks (D6).
10. **Update `Array.to_memory()`** — remove `_data` backdoor, always read from storage.
11. **Update `Array.sel()`** — remove `_data` check, read from storage. Persist slice result to temp zarr with storage_ref (no `_data` stashing).
12. **Update `checkpoint.py`** — `deserialize_intermediate_refs()` constructs typed DataObject, not ViewProxy (D8).
13. **Update `save_data.py`** — remove `_arrow_table` check in `_dataframe_to_arrow_table()`.
14. **Remove all ViewProxy imports, isinstance checks, and helpers** — `block.py:_is_view_proxy()`, `process/utils.py`, `app/bridge.py`, all comments.
15. **Update `split.py`, `merge.py`, `axis_iter.py`** �� replace `_arrow_table`/`_data` assignments with storage writes.
16. **Delete test files** — `test_proxy.py`, `test_proxy_multi_backend.py`. Update all tests asserting `_data` to assert `storage_ref`.

#### Phase 3: Process-side optimization (incremental)

17. **Array.sel() Zarr partial-read** — leverage Zarr backend's native slicing instead of full materialization + numpy indexing.
18. **SaveData streaming export** — for formats that support it, read from zarr chunk-by-chunk, write to target format chunk-by-chunk.
19. **Block SDK guidance** — document `iter_chunks()` / `sel()` as preferred over `to_memory()` for large data. Add framework-level memory warning when `to_memory()` on large data.

---

### 6. Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Performance regression from format conversion** — loaders convert source format (TIFF/CSV/etc.) to zarr/arrow; downstream reads from zarr/arrow, SaveData converts back to target format | Medium | This is inherent to using zarr as universal intermediate format. Streaming writes minimize memory. For workflows where source and target format match, a future "passthrough" optimization can skip intermediate storage. |
| **Existing plugin blocks break** — blocks that set `_data` directly | Low | D4 enforcement is backward-compatible — it flushes `_data` objects to zarr automatically. Blocks don't need to change immediately. |
| **`Array.sel()` becomes slower** — currently reads from `_data` (in-memory), will read from zarr | Medium | Zarr partial-read (Phase 4) mitigates this. For small arrays, the overhead is negligible. |
| **Test breakage** — many tests assert `_data` presence | Low | Systematic update: assert `storage_ref is not None` instead. |
| **Checkpoint backward compatibility** — old checkpoints may have ViewProxy-format entries | Low | `deserialize_intermediate_refs()` rewritten to produce DataObject. Old wire format still parseable. |

---

### 7. Alternatives Considered

1. **Keep ViewProxy as opt-in helper (ADR-027 Add1 approach).** Rejected — no block uses it. Maintaining a class with zero consumers adds complexity without value.

2. **Keep `_data` but enforce it's always backed by storage_ref too.** Rejected — two sources of truth for the same data. Which wins when they disagree? The `_data` pattern invites bypass of the storage contract.

3. **Create per-format read-only backends (TiffBackend, NpyBackend, etc.) for true zero-copy lazy loading.** Deferred — not rejected, but not required for this ADR. Zarr as the universal intermediate format is sufficient. Per-format backends can be added incrementally when performance requires it.

4. **Make DataObject.to_memory() check `_data` first as fast-path cache.** Rejected — this is the existing backdoor that caused the regression. A single code path (storage_ref → backend → read) is simpler, more predictable, and debuggable.

---

### 8. Consequences

- **DataObject becomes the single, unambiguous data abstraction.** No ViewProxy, no `_data` backdoor, no dual code paths.
- **All loaders become compliant immediately** via D4 (IOBlock enforcement), without individual loader code changes.
- **SaveData works with storage-backed objects** because `get_in_memory_data()` routes through `to_memory()`.
- **100G+ data support becomes architecturally possible** once Phase 3 (streaming loaders) is implemented. Phase 1 alone does not solve the OOM problem but removes the architectural barriers to solving it.
- **The wire protocol is unchanged.** JSON payload format between scheduler and worker is not modified.
- **56+ code locations require updates** across 19 source files. The changes are mechanical (remove ViewProxy imports, remove `_data` checks, update assertions) except for the IOBlock enforcement (D4) and the `to_memory()` rewrite.
- **ADR-027 Addendum 1 is formally deprecated.** Its correct decisions (typed reconstruction, per-class hooks, Meta constraints) are restated in D7.

---

### Addendum 1: Hard Gate Enforcement, D3 Clarification, and `persist` Helpers Promotion

**Date**: 2026-04-12
**Motivation**: Post-implementation audit (2026-04-12) found that Phases 1-3 left the engine layer structurally unable to enforce the storage-ref-only contract. Three layers of silent tolerance allow DataObjects without `storage_ref` to propagate through the wire format and crash in downstream blocks. See GitHub #659 for the full audit.

#### A1-D1. D3 Clarification — resolving the internal contradiction

ADR-031 D3 contains two statements that contradict each other:

- **D3 table** (§3 D3): "Remove all `_data` assignments and `hasattr` checks."
- **D3 text** (§3 D3 paragraph 5): "Transient in-memory data within a single block's `run()` is allowed. [...] The framework's existing `_auto_flush()` mechanism persists these to storage before the data crosses the process boundary."

**Resolution**: The D3 table is narrowed in scope. The corrected rule is:

> **IOBlock loaders** MUST NOT set `_data` or `_arrow_table`. They MUST persist data to storage directly via `persist_array()` / `persist_table()` and return DataObjects with `storage_ref` set. This applies to all IOBlock subclasses, whether in core (`load_data.py`) or in packages (`load_image.py`, LCMS loaders, etc.).
>
> **ProcessBlock / CodeBlock / AppBlock** MAY set `_data` or `_arrow_table` transiently within their `run()` / `process_item()` method. The framework guarantees that `_auto_flush()` persists these to storage before the object leaves the worker subprocess. Block authors who want to avoid full materialization MAY call `self.persist_array()` / `self.persist_table()` directly (see A1-D4).
>
> The `hasattr(self, "_data")` backward-compat checks in `DataObject.get_in_memory_data()` and `Array.to_memory()` are **retained** for the ProcessBlock transient path. They are NOT a backdoor — they exist exclusively to support `_auto_flush()` within a single subprocess lifetime.

**Rationale**: ProcessBlocks must call `item.to_memory()` to compute results — the data is already fully in memory. Requiring explicit `persist_array()` in every ProcessBlock would add boilerplate without reducing memory usage. The meaningful optimization boundary is between IOBlock (where streaming avoids full materialization) and ProcessBlock (where full materialization is inherent to the computation).

#### A1-D2. Hard gate at worker subprocess exit

**Rule**: No DataObject without `storage_ref` (or Artifact with `file_path`) may leave a worker subprocess. The framework enforces this at `serialise_outputs()` in `worker.py`.

**Three enforcement points, all mandatory:**

| Layer | File | Current behavior | Required behavior |
|-------|------|-----------------|-------------------|
| `_auto_flush` | `block.py` | Silent return when `output_dir=None`; silent catch on `save()` exception | **Raise `RuntimeError`** on both failure modes. If `output_dir` is None in worker context, that is a framework bug. If `save()` fails, the block has produced invalid output. |
| `serialise_outputs` | `worker.py` | No validation after `_auto_flush` | **Hard gate**: after `_auto_flush`, before `_serialise_one`, assert `storage_ref is not None` (Artifact with `file_path` exempt). Raise `RuntimeError` on violation. |
| `_serialise_one` | `serialization.py` | Emits `backend=None, path=None` for missing `storage_ref` | **Raise `ValueError`** instead of emitting null references. Defense-in-depth — should never trigger if the previous two layers work correctly. |

**Consequence**: Errors that currently surface as `ValueError: Cannot load data: no storage reference set` in downstream blocks will now surface as `RuntimeError` in the **source** block's worker, with a clear message identifying which DataObject and which flush operation failed.

#### A1-D3. IOBlock loaders — full-read prohibition

All IOBlock `load()` implementations MUST persist data to storage before returning. The safety net in `IOBlock.run()` (lines 237-243) remains as defense-in-depth but MUST NOT be the primary persistence path.

**Specific violations being fixed:**

| File | Sites | Migration |
|------|-------|-----------|
| `load_data.py` | 4× `result._data = arr` (pickle/npy/npz/parquet Array) | `self.persist_array(arr, shape, dtype, output_dir)` |
| `load_data.py` | 3× `df._arrow_table = table` (csv/parquet/json DataFrame) | `self.persist_table(table, output_dir)` |
| `load_image.py` | 1× `img._data = data` (single-page TIFF) | `self.persist_array(data, shape, dtype, output_dir)` |

**Rule for future IOBlock authors**: If your `load()` method reads data from a file, you MUST either:
1. Use `self.persist_array()` or `self.persist_table()` to write to managed storage, OR
2. Construct a `StorageReference` pointing at an existing store (e.g., zarr-backed data loaded by reference).

Returning a DataObject with `_data` set and no `storage_ref` from an IOBlock loader is a contract violation.

#### A1-D4. `persist_array` / `persist_table` promoted to Block base class

`persist_array()` and `persist_table()` are moved from `IOBlock` to `Block`, making them available to all block types.

```python
class Block:
    def persist_array(
        self, data_or_iterator, shape, dtype, output_dir=None, chunks=None,
    ) -> StorageReference:
        """Write array data to zarr storage, return StorageReference.

        Available to all block types. ProcessBlock authors may use this
        for explicit persistence when processing large data, as an
        alternative to the _data + _auto_flush path.

        Args:
            data_or_iterator: numpy ndarray (one-shot) or iterator of
                (index, chunk_array) tuples (streaming, constant memory).
            shape: Full array shape.
            dtype: Element dtype.
            output_dir: Target directory. Defaults to get_output_dir().
            chunks: Optional zarr chunk shape.

        Returns:
            StorageReference pointing to the written zarr store.
        """
        ...

    def persist_table(self, table, output_dir=None) -> StorageReference:
        """Write Arrow table to storage, return StorageReference.

        Available to all block types.
        """
        ...
```

**ProcessBlock author's choice matrix** (updated from §3 D4):

| Approach | When to use | Memory | Code |
|----------|-------------|--------|------|
| `result._data = arr` (transient) | Small/medium results; typical case | O(result size) | Minimal |
| `self.persist_array(arr, ...)` (explicit) | Large results; author wants control | O(result size) | Slightly more |
| `self.persist_array(chunk_iter, ...)` (streaming) | Very large results; chunk-wise processing | O(chunk size) | Most complex |

All three paths produce a valid DataObject with `storage_ref` set before leaving the worker — the first via `_auto_flush`, the latter two directly.

---

### Addendum 2: Declared Transient Data Slot and Typed Constructor API

**Date**: 2026-04-12
**Motivation**: Block authors currently pass in-memory data to DataObject instances via undeclared monkey-patch attributes (`obj._data = arr`, `df._arrow_table = table`). These attributes have no type annotation, no IDE support, no documentation, and require `# type: ignore` suppressions throughout the codebase. This addendum formalizes the transient data slot as a declared field with typed constructor parameters per subclass.

#### A2-D1. `_transient_data` field on DataObject base class

DataObject gains a single declared transient field:

```python
class DataObject:
    _transient_data: Any = None
```

**Contract:**
- `_transient_data` holds in-memory data produced by a block's computation, before `_auto_flush` persists it to storage.
- `_transient_data` is **never serialized**. The existing serialization (`_serialise_one`) uses explicit white-list field access — `_transient_data` is not in the white list and will never enter the wire format.
- `_transient_data` is **never reconstructed**. `_reconstruct_one` only restores `storage_ref`, `framework`, `meta`, `user`, and per-class extras.
- `_transient_data` exists only within a single subprocess lifetime. It is set during `block.run()`, read by `_auto_flush` → `save()` → `get_in_memory_data()`, and dies when the subprocess exits.
- After `_auto_flush` persists the data and sets `storage_ref`, `_transient_data` MAY be cleared to release memory. This is optional — the subprocess is about to exit anyway.

#### A2-D2. Typed `data=` constructor parameter per subclass

Each data-carrying subclass exposes a typed `data` keyword argument in its constructor. The constructor writes this value into `_transient_data`.

| Subclass | Constructor parameter | Python type | Notes |
|----------|----------------------|-------------|-------|
| **Array** | `data: np.ndarray \| None = None` | `numpy.ndarray` | N-dimensional numeric data |
| **DataFrame** | `data: pa.Table \| None = None` | `pyarrow.Table` | Columnar tabular data |
| **Series** | `data: pa.Table \| None = None` | `pyarrow.Table` | Single-column table |
| **Text** | `content: str` (existing) | `str` | Already declared — no change needed |
| **Artifact** | `file_path: Path` (existing) | `Path` | Already declared — no change needed |
| **CompositeData** | N/A — slots are independent DataObjects | — | Each slot follows its own type's pattern |

**Example — Array constructor:**

```python
class Array(DataObject):
    def __init__(self, *, axes, shape, dtype, chunk_shape=None,
                 data: np.ndarray | None = None,
                 **kwargs):
        super().__init__(**kwargs)
        self.axes = axes
        self.shape = shape
        self.dtype = dtype
        self.chunk_shape = chunk_shape
        if data is not None:
            self._transient_data = data
```

#### A2-D3. Backward compatibility via `_data` / `_arrow_table` property bridges

To avoid breaking 25+ ProcessBlock files and 60+ test files, the old monkey-patch names are preserved as property bridges that read/write `_transient_data`:

```python
class DataObject:
    _transient_data: Any = None

    @property
    def _data(self):
        return self._transient_data

    @_data.setter
    def _data(self, value):
        self._transient_data = value

    @property
    def _arrow_table(self):
        return self._transient_data

    @_arrow_table.setter
    def _arrow_table(self, value):
        self._transient_data = value
```

**Migration path:**
- **Phase 1** (this addendum): Add `_transient_data`, `data=` constructors, property bridges. Zero breaking changes.
- **Phase 2** (gradual): New code and documentation use `data=` constructor. Old code migrates at natural pace.
- **Phase 3** (future): Add `DeprecationWarning` to `_data` / `_arrow_table` property setters.

#### A2-D4. Updated `to_memory()` and `get_in_memory_data()`

Base class methods are simplified to check the declared field instead of `hasattr`:

```python
class DataObject:
    def to_memory(self) -> Any:
        if self._storage_ref is not None:
            return _get_backend(self._storage_ref).read(self._storage_ref)
        if self._transient_data is not None:
            return self._transient_data
        raise ValueError("Cannot load data: no storage reference and no transient data.")

    def get_in_memory_data(self) -> Any:
        if self._storage_ref is not None:
            return self.to_memory()
        if self._transient_data is not None:
            return self._transient_data
        raise ValueError(f"{type(self).__name__} has no data to persist.")
```

The `hasattr(self, "_data")` and `hasattr(self, "_arrow_table")` checks are **removed** from both methods. The property bridges ensure old code that sets `._data` or `._arrow_table` writes to `_transient_data`, which these methods now read directly.

Array's `to_memory()` override is simplified accordingly — it no longer needs its own `hasattr` check.

#### A2-D5. Block author experience (final state)

```python
# ProcessBlock — full materialization (most common)
def process_item(self, item, config):
    arr = item.to_memory()
    result = some_computation(arr)
    return Image(axes=item.axes, shape=result.shape,
                 dtype=str(result.dtype), data=result)

# ProcessBlock — streaming (large data, author opts in)
def process_item(self, item, config):
    def chunks():
        for chunk in item.iter_chunks(1024):
            yield transform(chunk)
    ref = self.persist_array(chunks(), shape, dtype)
    return Image(axes=item.axes, shape=shape, dtype=dtype, storage_ref=ref)

# IOBlock loader — must persist directly (Addendum 1 A1-D3)
def load(self, config, output_dir=""):
    raw = np.load(path)
    ref = self.persist_array(raw, raw.shape, raw.dtype, output_dir)
    return Array(axes=["y","x"], shape=raw.shape,
                 dtype=str(raw.dtype), storage_ref=ref)
```

---

### Appendix A: Deprecated ADR-027 Addendum 1

**Status**: ~~proposed~~ → **deprecated (superseded by ADR-031)**

ADR-027 Addendum 1 ("Worker subprocess type reconstruction returns typed DataObject instances, not ViewProxy") is deprecated in its entirety. The following decisions from Addendum 1 are **restated in ADR-031** with updated scope:

| Addendum 1 Decision | ADR-031 Status |
|---|---|
| D11': typed DataObject reconstruction in worker | **Retained** (ADR-031 D7) |
| `_reconstruct_extra_kwargs` / `_serialise_extra_metadata` hooks | **Retained** (ADR-031 D7) |
| Meta Pydantic constraints (frozen, JSON-round-trippable) | **Retained** (ADR-031 D7) |
| ViewProxy "demoted to opt-in helper via `item.view()`" | **Rejected** — ViewProxy deleted entirely (ADR-031 D2) |
| PhysicalQuantity Pydantic integration via `__get_pydantic_core_schema__` | **Retained** — unchanged, not in scope of ADR-031 |

References to ADR-027 Addendum 1 in code comments should be updated to cite ADR-031 D7 for reconstruction contract and ADR-031 D2 for ViewProxy elimination.

---

### Addendum 2: Declared `_transient_data` Slot + Typed `data=` Constructor

**Date**: 2026-04-12
**Status**: Accepted

#### Context

After Addendum 1 enforced the hard gate (no `_data`/`_arrow_table` on objects crossing block boundaries), the remaining problem is that loaders and the `_auto_flush` transition still monkey-patch `_data` or `_arrow_table` onto DataObject instances. These are not declared fields — they are set via `obj._data = arr` without any class-level declaration, making them invisible to static analysis, serialization guards, and documentation.

#### Decisions

**A2-D1**: Add a declared `_transient_data: Any = None` field on `DataObject.__init__`. This is the single canonical slot for in-memory data that has not yet been persisted. It is never serialised.

**A2-D2**: Add backward-compatible property bridges `_data` and `_arrow_table` on `DataObject` that read/write `_transient_data`. This preserves backward compatibility with existing code that uses `obj._data = arr` or `obj._arrow_table = table`.

**A2-D3**: Simplify `get_in_memory_data()` and `Array.to_memory()` to check `self._transient_data is not None` instead of `hasattr(self, "_data")` / `hasattr(self, "_arrow_table")`.

**A2-D4**: Add a typed `data=` constructor parameter to `Array`, `DataFrame`, and `Series`. When provided, it sets `_transient_data` in the constructor body.

#### Consequences

- All transient in-memory data is now stored in a declared, documented field.
- Static analysis tools can see the field and reason about its lifecycle.
- The `_serialise_one` / `_reconstruct_one` round-trip naturally excludes `_transient_data` because it is not part of `_serialise_extra_metadata`.
- The property bridges will be removed in a future phase once all callers migrate to the `data=` constructor.

---

### Appendix B: Audit Report Reference

This ADR was motivated by the independent data storage and transport audit documented in `docs/data-storage-transport-audit.en.md` (2026-04-11). Key audit findings are cited in §2.2 with evidence references to specific source files and line numbers.

The audit's summary:

> SciEasy's transport layer is mostly reference-based now, but its load, processing, and export layers still contain widespread eager materialization, payload-loss edge cases, and multiple mismatches with the stated design philosophy.
