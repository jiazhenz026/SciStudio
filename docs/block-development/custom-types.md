# Custom Types

This document covers how plugin developers create domain-specific data
types, register them via entry-points, and integrate with the framework's
metadata and serialization systems.

---

## Table of Contents

1. [Where Domain Types Live](#where-domain-types-live)
2. [Creating a Custom Array Subclass](#creating-a-custom-array-subclass)
3. [Creating a Custom DataFrame Subclass](#creating-a-custom-dataframe-subclass)
4. [Creating a Custom CompositeData Subclass](#creating-a-custom-compositedata-subclass)
5. [Meta Model Requirements](#meta-model-requirements)
6. [Physical Quantities and Units](#physical-quantities-and-units)
7. [Plugin Type Registration](#plugin-type-registration)
8. [Worker Subprocess Type Reconstruction](#worker-subprocess-type-reconstruction)
9. [Immutable Metadata Updates](#immutable-metadata-updates)

---

## Where Domain Types Live

**ADR-027 D2**: Domain-specific types belong in plugin packages, not in
core. Core defines the six base types (`Array`, `DataFrame`, `Series`,
`Text`, `Artifact`, `CompositeData`). Plugins add domain semantics.

Examples of where types live:

| Type | Package |
|------|---------|
| `Image`, `Label`, `Mask`, `Transform` | `scistudio-blocks-imaging` |
| `PeakTable`, `MIDTable` | `scistudio-blocks-lcms` |
| `RamanSpectrum` | `scistudio-blocks-srs` |

---

## Creating a Custom Array Subclass

Array subclasses tighten the axis schema and add domain-specific Meta.

```python
"""Custom Array subclass for fluorescence images."""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

from scistudio.core.types.array import Array
from scistudio.core.units import PhysicalQuantity


class FluorImage(Array):
    """Fluorescence microscopy image requiring spatial + channel axes."""

    required_axes: ClassVar[frozenset[str]] = frozenset({"y", "x", "c"})
    allowed_axes: ClassVar[frozenset[str] | None] = frozenset({"t", "z", "c", "y", "x"})
    canonical_order: ClassVar[tuple[str, ...]] = ("t", "z", "c", "y", "x")

    class Meta(BaseModel):
        """Per-instance fluorescence imaging metadata."""

        model_config = ConfigDict(frozen=True)

        pixel_size: PhysicalQuantity | None = None
        channels: list[str] | None = None
        excitation_wavelengths: list[float] | None = None
        emission_wavelengths: list[float] | None = None
        objective: str | None = None
        acquisition_date: datetime | None = None
        source_file: str | None = None
```

### Key points

- `required_axes` enforces that every instance has at least `y`, `x`,
  and `c` axes. Construction with `axes=["y", "x"]` would raise
  `ValueError`.
- `allowed_axes` restricts the axes to the imaging 6D alphabet.
  `None` means no restriction.
- `canonical_order` defines the preferred display ordering.
- The `Meta` inner class is a frozen Pydantic model.

---

## Creating a Custom DataFrame Subclass

DataFrame subclasses add domain-specific column semantics.

```python
from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

from scistudio.core.types.dataframe import DataFrame


class PeakTable(DataFrame):
    """LCMS peak table with source-tool metadata."""

    class Meta(BaseModel):
        model_config = ConfigDict(frozen=True)

        source: str = "unknown"        # "ElMAVEN", "MZmine", "XCMS"
        polarity: str | None = None    # "+", "-", or None
```

---

## Creating a Custom CompositeData Subclass

CompositeData subclasses declare named, typed slots.

```python
from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

from scistudio.core.types.array import Array
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame


class Label(CompositeData):
    """Label image with raster and/or polygon representation."""

    expected_slots: ClassVar[dict[str, type]] = {
        "raster": Array,
        "polygons": DataFrame,
    }

    class Meta(BaseModel):
        model_config = ConfigDict(frozen=True)
        source_file: str | None = None
        n_objects: int | None = None

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if self._slots.get("raster") is None and self._slots.get("polygons") is None:
            raise ValueError("Label requires at least one of raster or polygons")
```

### Slot access

```python
raster = label.get("raster")   # returns Array
label.set("raster", new_array) # validates type against expected_slots
```

---

## Meta Model Requirements

All `Meta` Pydantic models must follow these rules (ADR-027 D5):

1. **`model_config = ConfigDict(frozen=True)`** -- Immutability is required.
   Meta instances are shared by reference across derived objects.

2. **No `PrivateAttr`** -- Private attributes break serialization.

3. **JSON-round-trippable** -- All field types must survive
   `json.dumps()` / `json.loads()`. This is required for cross-process
   transport (ADR-017). Use primitive types, `str`, `int`, `float`,
   `bool`, `None`, `list`, `dict`, or Pydantic models that serialize
   to JSON.

4. **Declare as a `Meta` ClassVar on the DataObject subclass**:

```python
class MyType(Array):
    Meta: ClassVar[type[BaseModel] | None] = None  # inherited from DataObject

    class Meta(BaseModel):     # your override
        model_config = ConfigDict(frozen=True)
        my_field: str = ""
```

---

## Physical Quantities and Units

**ADR-027 D8**: Use `PhysicalQuantity` for values with units.

```python
from scistudio.core.units import PhysicalQuantity

pixel_size = PhysicalQuantity(value=0.325, unit="um")
```

`PhysicalQuantity` is a simple Pydantic-compatible model with `value`
(float) and `unit` (str). It serializes cleanly to JSON.

---

## Plugin Type Registration

Plugin types are registered via the `scistudio.types` entry-point group
in `pyproject.toml`.

### pyproject.toml

```toml
[project.entry-points."scistudio.types"]
my_plugin = "my_plugin_package:get_types"
```

### get_types() callable

```python
def get_types() -> list[type]:
    """Return the plugin's exported type classes."""
    from my_plugin_package.types import FluorImage, RatioImage
    return [FluorImage, RatioImage]
```

The `TypeRegistry` scans all `scistudio.types` entry-points at startup
and makes the types available for:

- Port type matching
- Worker subprocess reconstruction
- Block palette type dropdowns

---

## Worker Subprocess Type Reconstruction

When data crosses the subprocess boundary, the worker needs to
reconstruct typed DataObject instances from their serialized form. The
framework uses:

1. `_reconstruct_extra_kwargs(metadata)` -- class method that extracts
   constructor kwargs from the wire-format metadata sidecar.
2. `_serialise_extra_metadata(obj)` -- class method that produces the
   metadata sidecar from an instance.

### When to override

Most plugin types inherit their base class's hooks and do NOT need to
override. The base classes (`Array`, `DataFrame`, `Series`, `Text`,
`Artifact`, `CompositeData`) each implement these hooks.

Override only if your subclass adds constructor-required fields beyond
what the base class handles.

```python
class MySpecialArray(Array):
    def __init__(self, *, calibration: dict, **kwargs):
        super().__init__(**kwargs)
        self.calibration = calibration

    @classmethod
    def _reconstruct_extra_kwargs(cls, metadata):
        base = super()._reconstruct_extra_kwargs(metadata)
        base["calibration"] = metadata.get("calibration", {})
        return base

    @classmethod
    def _serialise_extra_metadata(cls, obj):
        base = super()._serialise_extra_metadata(obj)
        base["calibration"] = obj.calibration
        return base
```

---

## Immutable Metadata Updates

Use `with_meta()` to create a new instance with updated metadata:

```python
# Original image
img = Image(
    axes=["c", "y", "x"],
    shape=(3, 512, 512),
    dtype="uint16",
    meta=Image.Meta(source_file="raw.tiff"),
)

# Create derived image with updated pixel_size
from scistudio.core.units import PhysicalQuantity
derived = img.with_meta(pixel_size=PhysicalQuantity(value=0.325, unit="um"))

# derived has:
# - new framework with derived_from = img.framework.object_id
# - new meta with pixel_size set
# - same user dict (shallow copy)
# - same storage_ref
```

**Requirement**: `with_meta()` only works if the instance has a typed
`meta` slot (i.e., the class declares a `Meta` ClassVar). Calling
`with_meta()` on a plain `DataObject()` with `meta=None` raises
`ValueError`.

Array subclasses automatically propagate `axes`, `shape`, `dtype`, and
`chunk_shape` through `with_meta()`.
