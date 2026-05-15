# ADR-032 Implementation Roadmap

> **⚠️ SUPERSEDED by ADR-038 (2026-05-15).** ADR-032 itself is superseded; the
> `metadata.db` store described in this roadmap is collapsed into the unified
> `<project>/.scieasy/lineage.db` (4 normalized tables). This roadmap is preserved
> for historical context — actual implementation is tracked via the ADR-038/039
> cascade checklist at `docs/planning/adr-038-039-checklist.md`.

**Date**: 2026-04-12
**Status**: superseded by ADR-038 implementation cascade (2026-05-15)
**Related issues**: #639, #640, #641 (closed as superseded; see ADR-038 sub-issues)

---

## Key Architectural Finding: Worker Subprocess Boundary

Metadata writes **CANNOT happen inside `_auto_flush()` or `IOBlock.run()`** as ADR-032 D3 originally suggested, because these methods run in worker subprocesses that cannot share SQLite connections with the engine process.

The correct architecture (documented in ADR-032 Addendum 1):

```
Worker subprocess:
  block.run() → _auto_flush() → data written to zarr/arrow
  serialise_outputs() → wire-format JSON written to stdout

Engine process:
  LocalRunner.run() → reads stdout JSON
  scheduler._run_and_finalize() → stores in _block_outputs
    → MetadataStore.put_wire() for each output DataObject  ← write here
```

---

## Phase 1a: Core MetadataStore (#639)

**New file**: `src/scieasy/core/metadata_store.py`

### MetadataStore class

```python
class MetadataStore:
    def __init__(self, db_path: str | Path)
    def put(self, obj: DataObject, workflow_id=None, block_id=None, port_name=None)
    def put_wire(self, wire_dict: dict, workflow_id=None, block_id=None, port_name=None)
    def get(self, object_id: str) -> DataObject | None
    def get_wire(self, object_id: str) -> dict | None
    def get_by_storage_path(self, path: str) -> DataObject | None
    def ancestors(self, object_id: str) -> list[dict]
    def descendants(self, object_id: str) -> list[dict]
    def list_by_type(self, type_name: str) -> list[dict]
    def list_by_workflow(self, workflow_id: str) -> list[dict]
    def delete(self, object_id: str)
    def vacuum(self, existing_paths: set[str]) -> int
    def close(self)
```

### Singleton accessor

```python
# Same pattern as flush_context.py
_store: MetadataStore | None = None

def get_metadata_store() -> MetadataStore | None:
    return _store

def set_metadata_store(store: MetadataStore | None) -> None:
    global _store
    _store = store
```

### SQLite schema

```sql
CREATE TABLE IF NOT EXISTS data_objects (
    object_id       TEXT PRIMARY KEY,
    derived_from    TEXT,
    type_name       TEXT NOT NULL,
    backend         TEXT,
    storage_path    TEXT,
    created_at      TEXT NOT NULL,
    wire_payload    TEXT NOT NULL,
    workflow_id     TEXT,
    block_id        TEXT,
    port_name       TEXT
);
CREATE INDEX IF NOT EXISTS idx_derived_from ON data_objects(derived_from);
CREATE INDEX IF NOT EXISTS idx_type_name ON data_objects(type_name);
CREATE INDEX IF NOT EXISTS idx_storage_path ON data_objects(storage_path);
CREATE INDEX IF NOT EXISTS idx_workflow_block ON data_objects(workflow_id, block_id);
```

WAL mode enabled. Schema version tracked in `PRAGMA user_version`.

### `put_wire()` — primary write method

Accepts raw wire-format dict (output of `_serialise_one()`), extracts index columns, INSERT OR REPLACE:

```python
def put_wire(self, wire_dict, workflow_id=None, block_id=None, port_name=None):
    md = wire_dict.get("metadata", {})
    framework = md.get("framework", {})
    object_id = framework.get("object_id")
    if not object_id:
        return  # Cannot store without identity
    self._conn.execute(
        "INSERT OR REPLACE INTO data_objects VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            object_id,
            framework.get("derived_from"),
            (md.get("type_chain") or ["DataObject"])[-1],
            wire_dict.get("backend"),
            wire_dict.get("path"),
            framework.get("created_at", ""),
            json.dumps(wire_dict),
            workflow_id,
            block_id,
            port_name,
        )
    )
    self._conn.commit()
```

### Tests (16+)

- put/get round-trip
- put_wire/get_wire round-trip
- get_by_storage_path
- ancestors (recursive CTE)
- descendants (recursive CTE)
- list_by_type filtering
- list_by_workflow filtering
- vacuum removes orphans
- duplicate object_id upsert
- Collection items stored individually
- CompositeData slots stored recursively
- Missing object_id returns None
- Empty database queries
- WAL mode enabled
- Schema version tracking

---

## Phase 1b: Engine Integration (#640)

**Depends on**: #639

### Initialize MetadataStore

In `src/scieasy/api/runtime.py`, `open_project()` or equivalent:
```python
from scieasy.core.metadata_store import MetadataStore, set_metadata_store
store = MetadataStore(Path(project_dir) / "metadata.db")
set_metadata_store(store)
```

### Primary write path

In `src/scieasy/engine/scheduler.py`, `_run_and_finalize()` after storing outputs:

```python
def _persist_output_metadata(self, node_id, result, workflow_id):
    store = get_metadata_store()
    if store is None:
        return
    for port_name, value in result.items():
        if isinstance(value, dict) and value.get("_collection"):
            for item in value.get("items", []):
                if isinstance(item, dict) and "metadata" in item:
                    try:
                        store.put_wire(item, workflow_id, node_id, port_name)
                    except Exception:
                        logging.warning("metadata persist failed for %s/%s", node_id, port_name)
        elif isinstance(value, dict) and "metadata" in value:
            try:
                store.put_wire(value, workflow_id, node_id, port_name)
            except Exception:
                logging.warning("metadata persist failed for %s/%s", node_id, port_name)
```

Non-fatal: metadata write failures do not crash workflows.

### Tests (6)

- Normal block execution writes metadata to db
- Multi-item Collection writes one entry per item
- Worker crash: no metadata written (expected)
- Engine crash recovery: orphan data detectable by vacuum
- Non-fatal: metadata write failure doesn't crash workflow
- workflow_id/block_id/port_name correctly populated

---

## Phase 2a: Checkpoint Restore Sync (#641)

**Depends on**: #639, #640

### Backfill on checkpoint restore

In `scheduler.execute_from()`, after loading checkpoint data into `_block_outputs`:

```python
def _sync_checkpoint_to_store(self):
    store = get_metadata_store()
    if store is None:
        return
    for node_id, outputs in self._block_outputs.items():
        for port_name, value in outputs.items():
            # Same pattern as _persist_output_metadata
            ...  # only INSERT if not already in store
```

### Tests (5)

- Project reopen: metadata available from db after restore
- Checkpoint without db: degrades to current behavior
- Sync only adds missing entries (no overwrites)
- Full metadata round-trip: run → checkpoint → restore → verify meta/framework/user
- Graceful degradation when store unavailable
