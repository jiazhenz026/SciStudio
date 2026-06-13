---
doc_type: block-development
title: "Data Types"
status: living
owner: "@jiazhenz026"
last_updated: 2026-06-10
governed_by:
  - ADR-042
  - ADR-048
summary: "Core data type hierarchy, Collection transport, Array axes, metadata slots, lazy loading, type-inheritance port matching, and the preview-routing implications of a type's recorded type chain."
---

# Data Types

This document covers the core data type hierarchy, Collection transport,
Array axes, metadata slots, and lazy loading.

---

## Table of Contents

1. [Six Core Base Types](#six-core-base-types)
2. [DataObject Base Class](#dataobject-base-class)
3. [Array](#array)
4. [DataFrame](#dataframe)
5. [Series](#series)
6. [Text](#text)
7. [Artifact](#artifact)
8. [CompositeData](#compositedata)
9. [Collection -- The Transport Wrapper](#collection----the-transport-wrapper)
10. [Metadata Slots](#metadata-slots)
11. [Lazy Loading and Data Access](#lazy-loading-and-data-access)
12. [Type Inheritance and Port Matching](#type-inheritance-and-port-matching)
13. [Preview implications](#preview-implications)

---

## Six Core Base Types

SciStudio defines six core data types in `scistudio.core.types`:

| Type | Module | Purpose |
|------|--------|---------|
| `DataObject` | `base.py` | Abstract base for all data objects |
| `Array` | `array.py` | N-dimensional numeric data (images, spectra, tensors) |
| `DataFrame` | `dataframe.py` | Columnar tabular data |
| `Series` | `series.py` | 1D indexed data (chromatograms, spectra) |
| `Text` | `text.py` | String content (plain, markdown, JSON) |
| `Artifact` | `artifact.py` | Opaque file handle (PDF, binary, instrument files) |
| `CompositeData` | `composite.py` | Named slots of heterogeneous DataObjects |

Domain-specific subclasses (e.g., `Image`, `FluorImage`, `PeakTable`,
`MSRawFile`) live in **plugin packages**, not in core (ADR-027 D2).

---

## DataObject Base Class

`scistudio.core.types.base.DataObject` is the root of the data type
hierarchy. Every data object has five declared slots:

```python
class DataObject:
    _framework: FrameworkMeta   # identity, lineage, provenance
    _meta: BaseModel | None     # typed domain metadata (Pydantic)
    _user: dict[str, Any]       # free-form user metadata (JSON-serializable)
    _storage_ref: StorageReference | None  # pointer to persisted data
    _transient_data: Any        # in-memory data set via the `data=`
                                # constructor parameter (ADR-031 Addendum 2);
                                # never serialized, auto-flushed to storage
```

### Construction

```python
from scistudio.core.types.array import Array

img = Array(
    axes=["y", "x"],
    shape=(512, 512),
    dtype="float64",
    framework=FrameworkMeta(source="my_loader"),
    user={"experiment": "test-001"},
)
```

### Key methods

| Method | Purpose |
|--------|---------|
| `to_memory()` | Load full data from storage into memory |
| `slice(*args)` | Sub-select data without full materialisation |
| `iter_chunks(chunk_size)` | Yield successive chunks from storage |
| `save(path)` | Persist to storage, return StorageReference |
| `with_meta(**changes)` | Return a new instance with updated `meta` slot |

---

## Array

N-dimensional array with named axes. The primary type for images,
spectra, and tensors.

```python
from scistudio.core.types.array import Array

arr = Array(
    axes=["z", "c", "y", "x"],
    shape=(50, 3, 512, 512),
    dtype="uint16",
)
```

### Instance-level axes (ADR-027 D1)

`axes` is a required instance-level attribute. Subclasses declare
class-level constraints via three ClassVars:

```python
class Image(Array):
    required_axes: ClassVar[frozenset[str]] = frozenset({"y", "x"})
    allowed_axes: ClassVar[frozenset[str] | None] = frozenset({"t", "z", "c", "lambda", "y", "x"})
    canonical_order: ClassVar[tuple[str, ...]] = ("t", "z", "c", "lambda", "y", "x")
```

- `required_axes` -- Minimum set of axes any instance must carry.
- `allowed_axes` -- Superset of valid axis names. `None` = no restriction.
- `canonical_order` -- Preferred axis ordering for display.

### The 6D axis alphabet

```
t       -- time
z       -- depth
c       -- discrete channel
lambda  -- continuous spectral wavelength
y       -- spatial Y
x       -- spatial X
```

`c` (discrete) and `lambda` (continuous spectral) are distinct axes and
may coexist in a single instance.

### Named selection (ADR-027 D4)

```python
# Select a single z-slice, single channel
plane = img.sel(z=15, c=0)     # axes: ["y", "x"]

# Select a z-range
sub_stack = img.sel(z=slice(10, 20))  # axes: ["z", "y", "x"]
```

Integer indices remove the axis. Slices keep the axis.

### Iteration over an axis (ADR-027 D4)

```python
for z_slice in img.iter_over("z"):
    # z_slice is an Array with axes ["c", "y", "x"]
    process(z_slice)
```

Memory: O(one slice per iteration step).

---

## DataFrame

Columnar tabular data, backed by Arrow/Parquet.

```python
from scistudio.core.types.dataframe import DataFrame

table = DataFrame(
    columns=["mz", "rt", "intensity"],
    row_count=5000,
    schema={"mz": "float64", "rt": "float64", "intensity": "float64"},
)
```

Attributes: `columns`, `row_count`, `schema`.

---

## Series

One-dimensional indexed data (time series, chromatogram, spectrum).

```python
from scistudio.core.types.series import Series

spectrum = Series(
    index_name="wavenumber",
    value_name="intensity",
    length=1024,
)
```

Attributes: `index_name`, `value_name`, `length`.

---

## Text

String content (plain text, markdown, JSON).

```python
from scistudio.core.types.text import Text

note = Text(content="Experiment completed successfully.", format="plain")
```

Attributes: `content`, `format`, `encoding`.

---

## Artifact

Opaque file handle for non-scientific data (PDFs, binary blobs, reports).

```python
from pathlib import Path
from scistudio.core.types.artifact import Artifact

pdf = Artifact(
    file_path=Path("/data/report.pdf"),
    mime_type="application/pdf",
    description="Analysis report",
)
```

**ADR-031 D5**: Artifacts with `file_path` set use path-only transport.
They are exempt from auto-flush -- the framework does not read file
contents into memory or copy them to managed storage.

---

## CompositeData

Named slots of heterogeneous DataObjects. Used for compound data like
labeled images (raster + polygon table).

```python
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.array import Array
from scistudio.core.types.dataframe import DataFrame

class Label(CompositeData):
    expected_slots: ClassVar[dict[str, type]] = {
        "raster": Array,
        "polygons": DataFrame,
    }
```

Access slots with `obj.get("raster")` and `obj.set("raster", array)`.

---

## Collection -- The Transport Wrapper

`Collection` is the standard block-to-block transport type. It is NOT a
DataObject subclass.

```python
from scistudio.core.types.collection import Collection
from scistudio.core.types.array import Array

# Construct from a list of items
coll = Collection(items=[img1, img2, img3], item_type=Array)

# Iterate
for item in coll:
    data = item.to_memory()

# Index access
first = coll[0]
count = len(coll)

# Empty Collection requires explicit item_type
empty = Collection(items=[], item_type=Array)
```

### Key rules

- All items must be instances of the same base type.
- `item_type` is set at construction and cannot change.
- Empty Collection without explicit `item_type` raises `TypeError`.
- Single-item Collections are the standard pattern (no scalar path).

See [Collection Guide](collection-guide.md) for detailed patterns.

---

## Metadata Slots

**ADR-027 D5**: Every DataObject has three metadata slots.

### `framework` (FrameworkMeta)

Framework-managed, immutable from block authors' perspective. Carries
identity (`object_id`), lineage (`derived_from`), creation timestamp.

```python
# Read framework metadata
obj_id = item.framework.object_id

# Derive a new framework (for output objects)
new_fw = item.framework.derive()
```

### `meta` (Pydantic BaseModel or None)

Typed domain metadata. Plugin subclasses declare their own `Meta` model:

```python
from pydantic import BaseModel, ConfigDict

class Image(Array):
    class Meta(BaseModel):
        model_config = ConfigDict(frozen=True)
        pixel_size: PhysicalQuantity | None = None
        source_file: str | None = None
```

Access: `item.meta.pixel_size`. Update immutably: `item.with_meta(pixel_size=new_val)`.

**Rules for Meta models**:
- Must be `frozen=True` (immutable).
- No `PrivateAttr`.
- Must be JSON-round-trippable (all fields JSON-serializable).

### `user` (dict)

Free-form escape hatch. The framework does not interpret these values.
Must be JSON-serializable per ADR-017 (cross-process transport).

```python
item.user["experiment_id"] = "exp-042"
```

---

## Lazy Loading and Data Access

**ADR-031**: DataObject instances are lightweight references. Data lives
in storage (zarr, parquet, filesystem).

### When to load data

| Scenario | Method | Memory |
|----------|--------|--------|
| Need full array for computation | `item.to_memory()` | Full array in RAM |
| Need a sub-region | `item.slice(...)` | Sub-region in RAM |
| Process in chunks | `item.iter_chunks(size)` | One chunk at a time |
| Select named axes | `item.sel(z=5)` | One slice in RAM |
| Iterate over axis | `item.iter_over("z")` | One slice per step |

### Decision matrix

- **Small data** (< 100 MB): Use `to_memory()` freely.
- **Medium data** (100 MB - 2 GB): Consider `sel()` or `iter_over()`.
- **Large data** (> 2 GB): Use `iter_chunks()` or process via
  `process_item` (auto-flush gives O(1) peak memory).

A `ResourceWarning` is emitted when `to_memory()` would load more than
2 GB.

---

## Type Inheritance and Port Matching

Port type checking is `isinstance`-based. A port that accepts `Array`
will also accept any subclass (`Image`, `FluorImage`, etc.).

```
Array
  +-- Image            (plugin: scistudio-blocks-imaging)
  |     +-- FluorImage
  |     +-- Mask
  +-- (other Array subclasses in plugins)

DataFrame
  +-- PeakTable        (plugin: scistudio-blocks-lcms)

CompositeData
  +-- Label            (plugin: scistudio-blocks-imaging)
```

When a Collection is checked against a port, the Collection's
`item_type` is used for the isinstance check. A
`Collection[FluorImage]` matches a port accepting `[Array]`.

---

## Preview implications

A data ref carries a recorded **type chain** (ordered general → specific, e.g.
`["DataObject", "Array", "Image"]`). ADR-048 preview routing dispatches on that
chain: it finds the most specific previewer for the recorded type, then walks
toward more general ancestors, then falls back to the generic core previewer for
the base type.

Two consequences for type and block authors:

- **Record concrete types.** A `Collection[Image]` routes to an `Image`
  previewer; a `Collection[DataObject]` can only reach the generic core base
  fallback. This is the same reason ports should use concrete `accepted_types`
  ([Block Contract](block-contract.md#concrete-accepted-types-by-default)).
- **Core owns only generic fallbacks.** Core ships generic previewers
  (`core.dataframe.basic`, `core.array.basic`, `core.series.basic`,
  `core.text.basic`, `core.artifact.basic`, `core.composite.basic`,
  `core.collection.basic`, `core.plot.basic`, `core.base.fallback`). Rich
  domain display — for example the imaging `Image` / `Label` viewers — is
  package-owned. To give your custom type a domain viewer, ship a previewer for
  it. See [Previewers and Plot Jobs](previewers-and-plots.md) and
  [Types vs Previewers](custom-types.md#types-vs-previewers).
