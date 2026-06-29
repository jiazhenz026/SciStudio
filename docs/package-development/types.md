# Designing your types

Your types are the anchor of the package: blocks name them on ports, the type
system checks connections against them, and previewers attach to them. Get the
types right and the blocks and previewers follow naturally.

A package type is a subclass of a core type. You inherit storage, serialization,
lazy reads, and the ergonomic accessors; you add **a name, a schema, typed
metadata, and a domain constructor**. We use the spectroscopy package's
`Spectrum` throughout.

## Subclass the right core type

Pick the core type whose canonical in-memory form matches your data:

| Your data | Subclass | `to_memory()` is |
|---|---|---|
| N-dimensional array | `Array` | numpy `ndarray` |
| 1-D indexed signal | `Series` | `pyarrow.Table` |
| table | `DataFrame` | `pyarrow.Table` |
| a bundle of named sub-objects | `CompositeData` | `dict[str, native]` |

A spectrum is a 1-D signal — intensity versus a spectral coordinate — so
`Spectrum` subclasses `Series`:

```python
class Spectrum(Series):
    """A single 1-D spectrum: intensity versus a spectral coordinate."""

    def __init__(self, *, index_name="lambda", value_name="intensity",
                 length=None, data=None, **kwargs):
        super().__init__(index_name=index_name, value_name=value_name,
                         length=length, data=data, **kwargs)
```

Note what the constructor does: it **pins the semantics**. Core `Series` has no
fixed axis names, so `Spectrum` sets sensible defaults (`index_name="lambda"`,
`value_name="intensity"`) while still forwarding `data=` and the standard slots
to the base. This is the idiom — extend the core constructor, do not replace its
machinery.

## Add typed metadata with a `Meta` model

Metadata that travels with the object — units, instrument, identifiers — goes in
a nested `Meta` model. Make it a **frozen** Pydantic model so `with_meta()`
updates stay immutable (which keeps lineage sound):

```python
class Spectrum(Series):
    class Meta(BaseModel):
        model_config = ConfigDict(frozen=True)
        lambda_unit: str | None = None       # required-to-exist, value may be None
        intensity_unit: str | None = None
        lambda_kind: str | None = None
        modality: str | None = None
        instrument: str | None = None
        sample_label: str | None = None
        # ... arbitrary user metadata belongs in the `user` dict, not here
```

The distinction the spectroscopy package draws is worth copying: **required-to-
exist** fields (the unit and kind fields a spectrum is meaningless without)
declare the type's contract even when their value is unknown (`None`); genuinely
free-form, per-user metadata belongs in the inherited `user` dict, not in `Meta`.

## Provide a domain constructor — the asymmetric half

Core deliberately gives you **reading** for free but **not** construction, and
the reason is principled. Reading out to numpy/pandas is generic and
unambiguous, so core owns it (`to_memory()`, `to_pandas()`, `to_numpy()`).
Construction is *not* generic: it needs domain knowledge — which array is the
index, which is the value, what the units are, how ids are assigned — that core
does not have. So construction is **your** job.

Concretely: an author with two numpy arrays (wavelengths and intensities) should
be able to build a `Spectrum` without knowing how it is packed into Arrow. So a
package **should** offer a public domain constructor — a `from_<domain>`
**classmethod on the type** — that takes domain-native inputs and packs to the
canonical form internally:

```python
import numpy as np
import pyarrow as pa

class Spectrum(Series):
    @classmethod
    def from_arrays(cls, lambdas: np.ndarray, intensities: np.ndarray, *,
                    meta: "Spectrum.Meta | None" = None) -> "Spectrum":
        table = pa.table({"lambda": lambdas, "intensity": intensities})
        return cls(data=table, meta=meta)
```

The contract is specific about *where* this lives: a domain constructor is a
`from_<domain>` classmethod **on the type** (`Spectrum.from_arrays(...)`), not a
free function and not a method hidden on a `_support` module. That way a consumer
finds construction in one obvious place — on the type they already hold — and the
author never has to hand-build the Arrow payload. (In the spectroscopy package
this logic currently sits in the internal `_support.build_spectrum`; the
contract's direction is to surface it as `Spectrum.from_arrays` — exactly the
kind of gap this guide exists to close.)

## What you inherit — and must not redefine

Because `Spectrum` is a `Series`, it already has:

- `to_memory()` — the canonical `pyarrow.Table`;
- `to_pandas()` → a pandas `Series`, `to_numpy()` → an `ndarray` — the ergonomic
  accessors (ADR-052 §3.1);
- `with_meta(**changes)` — immutable metadata update;
- `sel()` / `slice()` / `iter_chunks()` — large-data reads.

**Do not** define your own `to_pandas` / `to_numpy`. That is the single most
important type rule in the contract: per-package conversion helpers are exactly
the divergence the inherited accessors exist to prevent. You may add a
*domain-named* reader that returns named components (e.g. a method returning the
`(lambda, intensity)` pair), but build it on the inherited accessors, never on
Arrow internals or `_transient_data`.

## Composite types: many sub-objects

When your data is several named sub-objects together, subclass `CompositeData`
and declare the slots. The spectroscopy package's `SpectralDataset` is an
`index` table plus a `spectra` table:

```python
class SpectralDataset(CompositeData):
    expected_slots: ClassVar[dict[str, type]] = {
        "index": DataFrame,     # one row per spectrum
        "spectra": DataFrame,   # long-form points
    }

    def __init__(self, *, slots=None, **kwargs):
        super().__init__(slots=slots, **kwargs)
        # validate schemas + the index<->spectra join invariant here
```

Core `CompositeData` validates the slot *types*; your subclass adds the
domain invariants (required columns, the join key) in `__init__`. This is the
same pattern as `Spectrum` — extend the core constructor, add domain rules.

## Mark stability and version

Every public type and public method carries a stability tier and a `Since`,
declared in the code with the `scistudio.stability` decorators:

```python
from scistudio.stability import stable, provisional

@stable(since="0.1.0")
class Spectrum(Series):
    ...
```

- `@stable(since=...)` — supported; no breaking change without deprecation
  first.
- `@provisional(since=...)` — usable but still settling; may change in a minor
  release with a changelog note.
- `@internal` — no promise; excluded from the generated reference.

`Since` is your **package's** version line (e.g. `0.1.0`), not core's. These
decorators are no-ops at runtime; they attach metadata the reference generator
reads to render the tier badge and version automatically.

## Register the types

Finally, return your types from the `scistudio.types` entry-point callable and
list them in the package `__all__`:

```python
def get_types() -> list[type]:
    return [Spectrum, SpectralDataset]
```

## Next

[blocks.md](blocks.md) — the blocks that produce and consume these types.
