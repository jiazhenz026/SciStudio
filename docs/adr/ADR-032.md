## ADR-032: Project-Level Metadata Store — SQLite Persistent Mirror of DataObject Metadata

**Status**: accepted
**Date**: 2026-04-11
**Related**: ADR-007 (lazy loading), ADR-017 (cross-process transport), ADR-027 D5 (three-slot metadata), ADR-031 (reference-only contract)

---

### 1. Purpose

This ADR addresses a **systemic metadata loss problem** identified by an independent audit (`docs/data-storage-transport-audit.en.md`, 2026-04-11): DataObject metadata (framework identity, typed plugin metadata, user annotations) survives only within a single workflow execution's process chain. Any path that touches persistent storage — project reopen, checkpoint restore, SaveData/LoadData round-trip, external data import — drops all metadata except structural properties (shape/dtype/axes).

This ADR:

1. Establishes a **project-level SQLite database** as the single persistent store for DataObject metadata.
2. Defines the database as a **persistent mirror of the wire format** — same serialization, same reconstruction path.
3. Specifies **write timing** (immediately after `_auto_flush` success) to maintain data-metadata consistency.
4. Subsumes **lineage graph traversal** as a metadata query — `derived_from` chains are queryable via the same database.
5. Makes metadata **available across project reopen, checkpoint restore, and cross-workflow data reuse**.

### 2. Context

#### 2.1 The four metadata layers (audit finding)

The audit identified four metadata representations with inconsistent fidelity:

| Layer | What it stores | framework | meta | user | Persistent? |
|-------|---------------|-----------|------|------|-------------|
| **1. DataObject slots** | In-memory three-slot model (ADR-027 D5) | ✅ | ✅ | ✅ | No (process lifetime) |
| **2. Wire format** | JSON sidecar in worker subprocess transport | ✅ | ✅ | ✅ | No (transit only) |
| **3. Storage backends** | Zarr .zattrs, Arrow schema, filesystem | ❌ | ❌ | ❌ | Yes (data only) |
| **4. API/Workflow YAML** | Block config, node layout | ❌ | ❌ | ❌ | Yes (config only) |

**Only Layer 2 (wire format) is full-fidelity**, but it is ephemeral — it exists only during a subprocess call and is never persisted. Layer 3 (storage backends) persists data but drops all identity and semantic metadata. Layer 4 (workflow YAML) persists workflow structure but not data-level metadata.

#### 2.2 Concrete failure scenarios

**Scenario 1: Project reopen**
User runs workflow → intermediate data in `data/zarr/` → closes SciEasy → reopens → clicks "continue from block X" → checkpoint loads StorageReference → backend reads zarr → DataObject reconstructed with shape/dtype/axes only → `framework.object_id`, `meta.pixel_size`, `user.experiment_id` all gone → downstream block calling `item.meta.pixel_size` crashes.

**Scenario 2: SaveData → LoadData round-trip**
Workflow A produces an Image with rich metadata → SaveData writes TIFF → collaborator imports TIFF via LoadData → only pixel data + shape/dtype → entire processing history, calibration parameters, user annotations lost.

**Scenario 3: Lineage query**
User asks "what processing was applied to produce this output?" → FrameworkMeta.derived_from exists in-memory during execution → but was never persisted → project reopen loses the lineage chain → unanswerable.

#### 2.3 Why per-file sidecars are insufficient

The Artifact type already uses a `.meta.json` sidecar pattern. Extending this to all types would mean:
- Every `.zarr` directory gets a `.zarr.meta.json`
- Every `.arrow` file gets a `.arrow.meta.json`
- Atomicity: data write + sidecar write is not atomic — crash between the two creates inconsistency
- Querying: finding all objects with `derived_from = X` requires scanning all sidecar files
- Portability: moving a zarr directory without its sidecar orphans the metadata

A centralized database avoids all of these problems.

---

### 3. Decisions

#### D1. One SQLite database per project

Each project directory contains a metadata database at:
```
<project_dir>/metadata.db
```

SQLite is chosen because:
- Zero external dependencies (Python stdlib `sqlite3`)
- Single file, portable with the project directory
- ACID transactions (data-metadata consistency)
- Supports JSON functions (`json_extract`) for querying nested metadata
- Read-concurrent, adequate for single-user scientific workflow

The database is **NOT a replacement for Storage backends** — backends still store data payloads (zarr arrays, arrow tables, files). The database stores only the DataObject identity and metadata envelope.

#### D2. Schema: indexed wire-format mirror

The database stores the exact JSON dict that `_serialise_one()` produces (the wire-format payload from Layer 2), plus extracted index columns for fast queries.

```sql
CREATE TABLE IF NOT EXISTS data_objects (
    -- Primary identity
    object_id       TEXT PRIMARY KEY,

    -- Index columns (extracted from wire payload for fast queries)
    derived_from    TEXT,           -- FrameworkMeta.derived_from (lineage parent)
    type_name       TEXT NOT NULL,  -- Last element of type_chain (e.g., "Image")
    backend         TEXT,           -- StorageReference.backend (e.g., "zarr")
    storage_path    TEXT,           -- StorageReference.path
    created_at      TEXT NOT NULL,  -- FrameworkMeta.created_at (ISO 8601)

    -- Full wire-format payload (source of truth for reconstruction)
    wire_payload    TEXT NOT NULL,  -- JSON: exact output of _serialise_one()

    -- Bookkeeping
    workflow_id     TEXT,           -- Which workflow produced this object
    block_id        TEXT,           -- Which block produced this object
    port_name       TEXT,           -- Which output port

    FOREIGN KEY (derived_from) REFERENCES data_objects(object_id)
        ON DELETE SET NULL
);

-- Lineage traversal: find all descendants of an object
CREATE INDEX IF NOT EXISTS idx_derived_from ON data_objects(derived_from);

-- Type filtering: find all Images, all DataFrames, etc.
CREATE INDEX IF NOT EXISTS idx_type_name ON data_objects(type_name);

-- Storage lookup: find the metadata for a given file path
CREATE INDEX IF NOT EXISTS idx_storage_path ON data_objects(storage_path);

-- Workflow context: find all objects produced by a workflow run
CREATE INDEX IF NOT EXISTS idx_workflow_block ON data_objects(workflow_id, block_id);
```

**Why mirror, not independent schema**: `_serialise_one()` already correctly serializes all three metadata slots (framework, meta, user) plus per-class extras (axes/shape/dtype, file_path/mime_type, columns/row_count, slots). Reusing this serialization:
- Avoids maintaining two serialization paths
- Guarantees the database contains exactly what the wire format contains
- Reconstruction uses the same `_reconstruct_one()` path as the worker subprocess

#### D3. Write timing: immediately after `_auto_flush` success

Metadata is written to the database **immediately after `_auto_flush()` successfully persists data to storage**. This ensures:

- **Consistency**: If data was written, metadata was written. If data write failed, metadata was not written.
- **Crash safety**: SQLite transactions are atomic. The metadata write is a single INSERT within a transaction.
- **No orphan metadata**: Metadata is never written without a corresponding data file.
- **No orphan data**: If the process crashes after data write but before metadata write, the data file exists without metadata. This is the same as current behavior (no regression) and can be detected by scanning storage paths not in the database.

**Implementation in `_auto_flush()`**:

```python
@staticmethod
def _auto_flush(obj: Any) -> Any:
    # ... existing Artifact skip, storage_ref check, etc. ...

    try:
        obj.save(target_path)  # Write data to storage
    except Exception:
        return obj

    # NEW: persist metadata to project database
    try:
        from scieasy.core.metadata_store import get_metadata_store
        store = get_metadata_store()
        if store is not None:
            store.put(obj)  # Serializes via _serialise_one(), inserts into SQLite
    except Exception:
        logging.warning("metadata_store.put() failed for %s", obj.framework.object_id)
        # Non-fatal: data is persisted, metadata loss is degraded but not broken

    return obj
```

The metadata write is **non-fatal** — if it fails, the data is still persisted and the workflow continues. This avoids making the metadata database a hard dependency for execution correctness.

#### D4. Read path: reconstruction from database

When a DataObject needs to be reconstructed from storage (checkpoint restore, project reopen), the database provides the full wire-format payload:

```python
# MetadataStore.get()
def get(self, object_id: str) -> DataObject | None:
    row = self._conn.execute(
        "SELECT wire_payload FROM data_objects WHERE object_id = ?",
        (object_id,)
    ).fetchone()
    if row is None:
        return None
    payload = json.loads(row[0])
    return _reconstruct_one(payload)  # Same path as worker subprocess
```

**Checkpoint restore integration**: Instead of reconstructing bare DataObjects with only `storage_ref`, checkpoint restore looks up the full metadata from the database:

```python
# In checkpoint restore path:
store = get_metadata_store()
if store is not None:
    obj = store.get(object_id)  # Full metadata reconstruction
else:
    obj = DataObject(storage_ref=ref)  # Fallback: degraded, metadata-less
```

#### D5. Lineage is a metadata query

With `derived_from` as an indexed column, lineage traversal is a recursive SQL query:

```sql
-- All ancestors of object 'abc' (full provenance chain)
WITH RECURSIVE ancestors AS (
    SELECT object_id, derived_from, type_name, block_id
    FROM data_objects WHERE object_id = 'abc'
    UNION ALL
    SELECT d.object_id, d.derived_from, d.type_name, d.block_id
    FROM data_objects d
    JOIN ancestors a ON d.object_id = a.derived_from
)
SELECT * FROM ancestors;

-- All descendants of object 'xyz' (impact analysis)
WITH RECURSIVE descendants AS (
    SELECT object_id, derived_from, type_name, block_id
    FROM data_objects WHERE object_id = 'xyz'
    UNION ALL
    SELECT d.object_id, d.derived_from, d.type_name, d.block_id
    FROM data_objects d
    JOIN descendants a ON d.derived_from = a.object_id
)
SELECT * FROM descendants;
```

This resolves the runtime audit's "lineage graph traversal missing" finding without a separate lineage subsystem.

#### D6. MetadataStore API

```python
class MetadataStore:
    """Project-level SQLite metadata store for DataObject identity and metadata."""

    def __init__(self, db_path: str | Path):
        """Open or create the metadata database."""
        ...

    def put(self, obj: DataObject, workflow_id: str = None, block_id: str = None, port_name: str = None) -> None:
        """Persist DataObject metadata. Upsert by object_id."""
        ...

    def get(self, object_id: str) -> DataObject | None:
        """Reconstruct a full DataObject from stored metadata."""
        ...

    def get_by_storage_path(self, path: str) -> DataObject | None:
        """Look up metadata for a data file on disk."""
        ...

    def ancestors(self, object_id: str) -> list[dict]:
        """Return the full provenance chain (derived_from traversal)."""
        ...

    def descendants(self, object_id: str) -> list[dict]:
        """Return all objects derived from this one."""
        ...

    def list_by_type(self, type_name: str) -> list[dict]:
        """List all objects of a given type (e.g., all Images)."""
        ...

    def list_by_workflow(self, workflow_id: str) -> list[dict]:
        """List all objects produced by a workflow run."""
        ...

    def delete(self, object_id: str) -> None:
        """Remove metadata entry (e.g., when data file is deleted)."""
        ...

    def vacuum(self, existing_paths: set[str]) -> int:
        """Remove entries whose storage_path no longer exists. Returns count removed."""
        ...
```

#### D7. Integration points

| Component | Integration | Notes |
|-----------|-------------|-------|
| `Block._auto_flush()` | After `obj.save()` succeeds, call `store.put(obj)` | D3 write timing |
| `IOBlock.run()` | After D4 safety net flush, call `store.put(item)` for each item | Loader outputs get metadata persisted |
| `checkpoint.py` restore | Use `store.get(object_id)` instead of bare `DataObject(storage_ref=ref)` | Full metadata reconstruction on project reopen |
| `scheduler._run_and_finalize()` | Pass `workflow_id` and `block_id` to `store.put()` via context | Bookkeeping columns populated |
| API endpoint | New `GET /api/projects/{id}/data-objects` for browsing | Optional, Phase 2 |
| API endpoint | New `GET /api/data-objects/{object_id}/lineage` for provenance | Optional, Phase 2 |

#### D8. Database lifecycle

- **Created**: On first `_auto_flush()` in a project (lazy initialization)
- **Location**: `<project_dir>/metadata.db`
- **Portable**: Moves with the project directory (SQLite is a single file)
- **Cleanup**: `vacuum()` removes entries for deleted data files
- **Migration**: Schema version stored in `PRAGMA user_version`. Future schema changes use versioned migrations.
- **Backup**: Standard SQLite backup (copy the file, or `VACUUM INTO`)

---

### 4. Impact Scope

#### 4.1 New files

| File | Purpose |
|------|---------|
| `src/scieasy/core/metadata_store.py` | MetadataStore class + `get_metadata_store()` singleton accessor |

#### 4.2 Modified files

| File | Changes |
|------|---------|
| `src/scieasy/blocks/base/block.py` | `_auto_flush()`: after `obj.save()`, call `store.put(obj)` (D3) |
| `src/scieasy/blocks/io/io_block.py` | `run()`: after D4 safety net flush, call `store.put(item)` for loader outputs |
| `src/scieasy/engine/checkpoint.py` | Restore path: use `store.get(object_id)` for full metadata reconstruction (D4) |
| `src/scieasy/engine/scheduler.py` | Pass `workflow_id`/`block_id` context for bookkeeping columns |
| `src/scieasy/engine/runners/worker.py` | `serialise_outputs()`: after auto_flush + serialise, call `store.put()` if store available |
| `src/scieasy/api/runtime.py` | Initialize MetadataStore with project path when project opens |

#### 4.3 Test files

| File | Purpose |
|------|---------|
| `tests/core/test_metadata_store.py` (new) | Unit tests: put/get/ancestors/descendants/vacuum |
| `tests/engine/test_checkpoint.py` | Update: verify metadata restored from db on project reopen |

---

### 5. Implementation Plan

#### Phase 1: Core store + auto_flush integration

1. Implement `MetadataStore` class with SQLite backend
2. Implement `get_metadata_store()` singleton (returns None when no project context)
3. Integrate into `_auto_flush()`: put() after save()
4. Integrate into `IOBlock.run()`: put() after D4 safety net flush
5. Unit tests for put/get/round-trip

#### Phase 2: Checkpoint + lineage integration

6. Update checkpoint restore to use `store.get(object_id)` for full reconstruction
7. Implement `ancestors()` / `descendants()` recursive queries
8. Pass workflow_id/block_id context from scheduler
9. Integration tests for project reopen with metadata preservation

#### Phase 3: API + UI (optional, incremental)

10. `GET /api/projects/{id}/data-objects` — browse all data objects in project
11. `GET /api/data-objects/{id}/lineage` — provenance graph
12. Frontend lineage visualization (deferred, not in this ADR's scope)

---

### 6. Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| **SQLite write contention** — concurrent worker subprocesses writing to same db | Medium | Workers run in subprocesses; each writes via the engine process (not directly). If needed, use WAL mode (`PRAGMA journal_mode=WAL`) for concurrent reads. |
| **Database corruption** — crash during write | Low | SQLite is ACID by default. WAL mode adds additional crash resilience. |
| **Database growth** — large projects with many data objects | Low | Each row is ~1-5KB (wire-format JSON). 10,000 objects = ~50MB. `vacuum()` removes stale entries. |
| **Performance overhead** — INSERT on every auto_flush | Low | SQLite INSERT is ~0.1ms. Block execution is seconds to minutes. Negligible overhead. |
| **Metadata store unavailable** — no project context, or db locked | Low | `get_metadata_store()` returns None; all put() calls are guarded with `if store is not None`. Execution continues without metadata persistence (degraded but functional). |

---

### 7. Alternatives Considered

1. **Per-file sidecar JSONs** (like Artifact's `.meta.json`). Rejected — no atomicity with data write, no query capability, file system clutter, no lineage traversal.

2. **Embed metadata in storage backends** (e.g., Zarr .zattrs, Parquet file metadata). Rejected — each backend has different metadata capabilities, no uniform query interface, and backends are designed for data-format-specific metadata (shape/dtype), not application-level metadata (framework/meta/user).

3. **External database (PostgreSQL, MongoDB)**. Rejected — adds deployment complexity, not portable with project directory, overkill for single-user scientific workflows.

4. **In-memory dict + periodic flush to JSON file**. Rejected — not crash-safe, no query capability, concurrent write issues.

5. **No metadata persistence — accept the loss**. Rejected — violates ADR-007's lazy loading design intent and scientific reproducibility requirements.

---

### 8. Consequences

- **Project reopen preserves full DataObject metadata** — framework identity, plugin metadata, user annotations all survive across sessions.
- **Lineage is queryable** — `derived_from` chains traversable via SQL recursive CTE. No separate lineage subsystem needed.
- **SaveData/LoadData round-trip is still lossy** — the database is per-project; exported files (TIFF, CSV) don't carry metadata. This is acceptable: the metadata lives in the project, not in the export. Future work could add a portable metadata export format.
- **One new dependency on project directory structure** — `metadata.db` file added. Portable with the project (single SQLite file).
- **Non-breaking** — metadata persistence is additive. If the database is missing or unavailable, the system degrades to current behavior (no metadata persistence). No existing functionality breaks.
- **Worker subprocesses do not write to the database directly** — only the engine process writes, avoiding SQLite concurrent write issues. Worker outputs are serialized to the engine via stdout JSON, then the engine writes to the database.

---

### Addendum 1: Engine-Side Metadata Writes (Worker Subprocess Boundary)

**Status**: accepted
**Date**: 2026-04-12

#### Context

ADR-032 D3 specifies that metadata should be written "immediately after `_auto_flush()` success." Implementation analysis revealed that `_auto_flush()` runs inside **worker subprocesses** (via `Block._auto_flush()` called from `ProcessBlock.run()` and `worker.serialise_outputs()`). Worker subprocesses cannot share SQLite connections with the engine process — SQLite does not support cross-process connection sharing safely.

#### Decision

**Metadata writes happen in the engine process, not the worker subprocess.**

The correct write point is `scheduler._run_and_finalize()`, after the engine receives the worker's stdout JSON containing the wire-format output dicts. The engine calls `MetadataStore.put_wire(wire_dict)` for each output DataObject in the result.

```
Worker subprocess:
  block.run() → _auto_flush() → data written to zarr/arrow
  serialise_outputs() → wire-format JSON written to stdout

Engine process:
  LocalRunner.run() → reads stdout JSON → returns wire-format dicts
  scheduler._run_and_finalize() → stores in _block_outputs
    → NEW: MetadataStore.put_wire() for each DataObject in output  ← metadata write here
```

**`put_wire(wire_dict)`** accepts the raw wire-format dict (the exact output of `_serialise_one()`) and inserts it directly into the database without reconstructing a DataObject. This avoids a redundant serialize→deserialize→reserialize round-trip.

#### Consistency implications

D3's original intent was tight data-metadata consistency: "if data was written, metadata was written." Engine-side writes relax this guarantee:

| Scenario | Data on disk? | Metadata in db? | Acceptable? |
|----------|--------------|----------------|-------------|
| Block completes normally | ✅ | ✅ | Yes |
| Worker crashes after data write, before stdout | ✅ | ❌ | Yes — orphan data detectable by `vacuum()` |
| Worker crashes during data write | ❌ | ❌ | Yes — consistent (both absent) |
| Engine crashes after receiving stdout, before db write | ✅ | ❌ | Yes — same orphan case, detectable |
| Long-running block (1000 items) | ✅ (incremental) | ❌ (until block finishes) | Acceptable — crash loses metadata for completed items, but outputs are incomplete anyway |

**The consistency window is bounded by one block execution.** This is acceptable because:
1. A crashed block's outputs are incomplete regardless of metadata presence
2. `vacuum(existing_paths)` can detect and report orphan data files without metadata entries
3. The alternative (worker-side SQLite writes) requires cross-process db sharing or a separate IPC channel — complexity not justified by the marginal consistency improvement

#### Supersedes

This addendum supersedes ADR-032 D3's statement "immediately after `_auto_flush()` success." The write timing is now: **immediately after the engine process receives wire-format outputs from the worker subprocess.** The non-fatal guarantee is preserved — metadata write failures do not crash workflows.

---

### Appendix: Relationship to ADR-031

ADR-031 (DataObject reference-only contract) ensures all DataObjects have `storage_ref` set when they cross block boundaries. ADR-032 builds on this by persisting the complete metadata envelope alongside the storage reference.

After both ADRs are implemented:
- ADR-031 guarantees: every DataObject has `storage_ref` → data is in storage
- ADR-032 guarantees: every DataObject's metadata is in the database → identity, lineage, and annotations are persistent

Together they close the gap between the architectural design ("DataObject is a lightweight reference") and the implementation reality.
