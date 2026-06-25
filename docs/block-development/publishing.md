---
doc_type: block-development
title: "Publishing Block Packages"
status: living
owner: "@jiazhenz026"
last_updated: 2026-06-10
governed_by:
  - ADR-042
  - ADR-043
  - ADR-047
  - ADR-048
summary: "Packaging and distribution guide for SciStudio block packages: the three extension entry points (scistudio.blocks, scistudio.types, scistudio.previewers), package layout, PackageInfo, published IO capabilities, and wheel packaging."
---

# Publishing

This document covers how to package and distribute SciStudio extensions as
installable Python packages (Tier 2 distribution). A package can ship three
distinct extension surfaces:

- **`scistudio.blocks`** — processing/IO/app/code blocks (workflow logic).
- **`scistudio.types`** — semantic `DataObject` subclasses (data types).
- **`scistudio.previewers`** — display behaviour for a type (ADR-048).

These are three separate entry-point groups. A package may wire any subset.

---

## Table of Contents

1. [Distribution Tiers](#distribution-tiers)
2. [Package Structure](#package-structure)
3. [pyproject.toml](#pyprojecttoml)
4. [The three entry-point groups](#the-three-entry-point-groups)
5. [PackageInfo Declaration](#packageinfo-declaration)
6. [The package callables](#the-package-callables)
7. [Published IO Format Capabilities](#published-io-format-capabilities)
8. [Testing Before Release](#testing-before-release)
9. [Versioning](#versioning)
10. [Optional Dependencies](#optional-dependencies)

---

## Distribution Tiers

### Tier 1: Drop-in files

Place `.py` files in `~/.scistudio/blocks/` or a project's `blocks/`
directory. No packaging needed. Good for personal blocks or prototyping.

### Tier 2: Installable packages

Distribute via PyPI (or private index). Users install with
`pip install your-package`. Good for shared, versioned, tested blocks.

---

## Package Structure

Follow the standard `src/` layout. The fastest way to a correct skeleton is
`scistudio init-block-package my-blocks`, which scaffolds exactly the structure
the registry and tests expect:

```
my-blocks/
  pyproject.toml
  README.md
  src/
    my_blocks/
      __init__.py          # get_blocks() -> (PackageInfo, list[type])
      blocks/
        __init__.py
        my_process.py      # ProcessBlock subclass
        my_loader.py       # IOBlock subclass
      types/
        __init__.py
        my_types.py        # Custom Array/DataFrame subclasses
      previewers/
        __init__.py        # get_previewers() -> list[PreviewerSpec] (ADR-048, optional)
        assets/
          viewer.js        # same-origin packaged ES module
  tests/
    __init__.py
    conftest.py
    test_my_process.py
    test_my_loader.py
```

The scaffolded `__init__.py` is the canonical primary pattern: a single
`get_blocks()` callable returning a `(PackageInfo, list[type])` tuple.

---

## pyproject.toml

Minimal example:

```toml
[build-system]
requires = ["hatchling>=1.24"]
build-backend = "hatchling.build"

[project]
name = "scistudio-blocks-mypackage"
version = "0.1.0"
description = "My custom blocks for SciStudio."
readme = "README.md"
authors = [
    {name = "Your Name"},
]
requires-python = ">=3.11"
dependencies = [
    "scistudio>=0.2.1",
    "numpy>=1.24",
]

[project.entry-points."scistudio.blocks"]
mypackage = "my_blocks:get_blocks"

[project.entry-points."scistudio.types"]
mypackage = "my_blocks:get_types"

# Optional (ADR-048): register display behaviour for your types.
[project.entry-points."scistudio.previewers"]
mypackage = "my_blocks.previewers:get_previewers"

[tool.hatch.build.targets.wheel]
packages = ["src/my_blocks"]
```

If you ship a packaged frontend previewer module, also include its assets in the
wheel (e.g. via `[tool.hatch.build.targets.wheel.force-include]`) so the
backend can serve them same-origin.

---

## The three entry-point groups

SciStudio discovers extensions via three separate entry-point groups. Wire only
the groups you need.

### `scistudio.blocks`

The block registry (`scistudio.blocks.registry`) scans this group at startup.
Each entry point points to a callable. The **primary** pattern — what
`scistudio init-block-package` scaffolds and what the package tests assert — is
a single `get_blocks()` returning a `(PackageInfo, list[type])` tuple:

```toml
[project.entry-points."scistudio.blocks"]
mypackage = "my_blocks:get_blocks"
```

For backward compatibility the registry (`registry/_scan.py`) also accepts a
callable returning a plain `list[type[Block]]`, a direct block class, and a
`get_block_package()` callable. Prefer the single
`get_blocks() -> (PackageInfo, list[type])` shape in new packages; the other
shapes are accepted only so older packages keep loading (they are not the
preferred new API).

### `scistudio.types`

The type registry (`scistudio.core.types.registry`) scans this group at startup.
Each entry point points to a callable returning `list[type]`:

```toml
[project.entry-points."scistudio.types"]
mypackage = "my_blocks:get_types"
```

Types register *semantic data types* — concrete `DataObject` subclasses such as
`Image`, `PeakTable`, `RamanSpectrum`. See [Custom Types](custom-types.md).

### `scistudio.previewers` (ADR-048)

The previewer registry (`scistudio.previewers.registry`) scans this group. Each
entry point points to a callable returning `list[PreviewerSpec]`:

```toml
[project.entry-points."scistudio.previewers"]
mypackage = "my_blocks.previewers:get_previewers"
```

Previewers register *display behaviour* for a type — a backend provider plus an
optional same-origin frontend manifest. They are distinct from types: a type
says "this is an `Image`", a previewer says "here is how an `Image` is shown".
See [Previewers and Plot Jobs](previewers-and-plots.md).

---

## PackageInfo Declaration

`PackageInfo` is a frozen dataclass that describes your package to the
registry:

```python
from scistudio.blocks.base.package_info import PackageInfo

info = PackageInfo(
    name="scistudio-blocks-mypackage",
    description="My custom processing blocks.",
    author="Your Name",
    version="0.1.0",
)
```

Fields:

| Field | Required | Default |
|-------|----------|---------|
| `name` | Yes | -- |
| `description` | No | `""` |
| `author` | No | `""` |
| `version` | No | `"0.1.0"` |

---

## The package callables

Your package's `__init__.py` wires the entry-point callables. The canonical
primary shape is a single `get_blocks()` returning the `(PackageInfo,
list[type])` tuple, a `get_types()` returning the exported types, and (for
ADR-048 previewers) a `get_previewers()` in a `previewers` submodule:

```python
"""My blocks package."""

from __future__ import annotations

from scistudio.blocks.base.package_info import PackageInfo
from my_blocks.blocks.my_process import MyProcessBlock
from my_blocks.blocks.my_loader import MyLoader
from my_blocks.types.my_types import MyImage

__version__ = "0.1.0"

_PACKAGE_INFO = PackageInfo(
    name="scistudio-blocks-mypackage",
    description="My custom blocks.",
    author="Your Name",
    version=__version__,
)
_TYPES: tuple[type, ...] = (MyImage,)
_BLOCKS: tuple[type, ...] = (MyProcessBlock, MyLoader)


def get_blocks() -> tuple[PackageInfo, list[type]]:
    """Return package metadata and the block list for the scistudio.blocks entry-point."""
    return (_PACKAGE_INFO, list(_BLOCKS))


def get_types() -> list[type]:
    """Return exported type classes for the scistudio.types entry-point."""
    return list(_TYPES)
```

The `scistudio.previewers` callable lives in a `previewers` submodule so it can
import the previewer models without pulling block code into the type scan:

```python
# my_blocks/previewers/__init__.py
from __future__ import annotations

from scistudio.previewers.models import OwnerKind, PreviewerSpec


def get_previewers() -> list[PreviewerSpec]:
    """Return the package's PreviewerSpec list for the scistudio.previewers entry-point."""
    return [
        PreviewerSpec(
            previewer_id="mypackage.myimage.viewer",
            owner_kind=OwnerKind.PACKAGE,
            owner_name="scistudio-blocks-mypackage",
            target_type="MyImage",
            priority=100,
            backend_provider="my_blocks.previewers.providers:my_image_provider",
        ),
    ]
```

See [Previewers and Plot Jobs](previewers-and-plots.md) for the provider,
`PreviewDataAccess`, and frontend-manifest details.

> **Legacy shapes still load.** The registry also accepts a `get_blocks()` that
> returns a plain `list[type]`, a `get_block_package()` callable, or a direct
> block class. Use the single `get_blocks() -> (PackageInfo, list[type])` tuple
> in new packages; do not mix shapes.

---

## Published IO Format Capabilities

Published IO packages must treat file formats as boundary capabilities owned by
IOBlocks, AppBlocks, CodeBlocks, and the registry. Do not put extension support
on DataObject classes. The governing architecture is
[ADR-043](../adr/ADR-043.md), with implementation requirements in
[the ADR-043 spec](../specs/adr-043-io-format-capability-registry.md).

Use explicit `FormatCapability` records when a package:

- Supports multiple file formats behind one user-facing block.
- Supports a format that another package may also claim.
- Needs a stable capability ID for workflow replay.
- Declares metadata fidelity stronger than `pixel_only`.
- Claims a tested round-trip group.

```python
from typing import ClassVar

from scistudio.blocks.io.capabilities import FormatCapability, MetadataFidelity
from scistudio.blocks.io.io_block import IOBlock
from my_blocks.types import MyImage


class LoadMyImage(IOBlock):
    name: ClassVar[str] = "Load My Image"
    direction: ClassVar[str] = "input"

    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        FormatCapability(
            id="my-blocks.image.ome-tiff.load",
            direction="load",
            data_type=MyImage,
            format_id="ome-tiff",
            extensions=(".ome.tif", ".ome.tiff"),
            label="OME-TIFF",
            block_type="LoadMyImage",
            handler="_load_ome_tiff",
            is_default=True,
            metadata_fidelity=MetadataFidelity(
                level="typed_meta",
                typed_meta_reads=("axes", "pixel_size", "channels"),
            ),
        ),
    )
```

Capability IDs should be package-qualified and stable. Changing a capability
ID is a workflow compatibility break because saved workflows use it as the
replay key when selection is ambiguous or user-chosen.

### Aggregate IOBlocks

Expose a compact palette. Many format handlers should remain one user-facing
block, such as `Load Image`, with a format/capability selector. Internal
handler methods can still be one method per format.

### Metadata fidelity

`metadata_fidelity` describes typed `meta` fields at the IO boundary. It does
not describe lineage, run environment, execution parameters, or workflow YAML
metadata. Declare `typed_meta`, `format_specific`, or `lossless` only when
tests prove the promised fields or round-trip behavior.

### Migration policy

Compatibility synthesis from legacy `supported_extensions` is migration
scaffolding only. It keeps existing blocks runnable while published packages
migrate to explicit capability declarations. Full hard-validation migration for
published packages is tracked by #1204.

---

## Testing Before Release

Run the full validation before publishing. Test all three entry-point surfaces:

```python
from scistudio.testing import BlockTestHarness
from scistudio.blocks.base.block import Block
from scistudio.blocks.base.package_info import PackageInfo

def test_entry_point_validates():
    from my_blocks import get_blocks
    harness = BlockTestHarness(Block)
    result = get_blocks()            # (PackageInfo, list[type])
    errors = harness.validate_entry_point_callable(result)
    assert not errors, "\n".join(errors)

def test_all_blocks_contract():
    from my_blocks import get_blocks
    _info, blocks = get_blocks()
    for block_cls in blocks:
        harness = BlockTestHarness(block_cls)
        errors = harness.validate_block()
        assert not errors, f"{block_cls.__name__}: {errors}"

def test_types_registered():
    from my_blocks import get_types
    types = get_types()
    assert len(types) > 0
    for t in types:
        assert isinstance(t, type)

def test_previewers_registered():
    # ADR-048: only if the package ships scistudio.previewers.
    from scistudio.previewers.models import OwnerKind, PreviewerSpec
    from my_blocks.previewers import get_previewers
    specs = get_previewers()
    assert specs
    for spec in specs:
        assert isinstance(spec, PreviewerSpec)
        assert spec.owner_kind is OwnerKind.PACKAGE
        assert spec.previewer_id and spec.target_type
```

`validate_entry_point_callable` accepts the `(PackageInfo, list[type[Block]])`
tuple (primary) or a plain `list[type[Block]]` (legacy). See
[Testing](testing.md) for previewer-registration, template, and packaging
checks.

> **Registry posture (ADR-047).** The block registry is decomposed into
> private scan helpers and exposes a capability-aware lookup surface
> (`find_loader_capability` / `find_saver_capability` /
> `list_format_capabilities`). The legacy IO finder API (`find_loader`,
> `find_saver`, `find_io_blocks_for_type`) has been removed. Package IO docs
> must declare `FormatCapability` records rather than rely on the removed
> extension-only finder.

---

## Versioning

Follow [Semantic Versioning](https://semver.org/):

- **MAJOR**: Breaking changes to block contract (port names, types,
  config schema changes that break existing workflows).
- **MINOR**: New blocks, new optional config fields, new types.
- **PATCH**: Bug fixes, documentation, internal improvements.

---

## Optional Dependencies

For blocks with heavy dependencies (e.g., ML frameworks), use optional
dependency groups:

```toml
[project.optional-dependencies]
gpu = [
    "torch>=2.0",
    "cellpose>=3.0",
]
```

In your block, import lazily and raise a clear error:

```python
def setup(self, config):
    try:
        from cellpose import models
    except ImportError as exc:
        raise ImportError(
            "This block requires the [gpu] extra: "
            "pip install scistudio-blocks-mypackage[gpu]"
        ) from exc
    return models.Cellpose(model_type=config.get("model"))
```

Use `key_dependencies` to display requirements in the UI:

```python
key_dependencies: ClassVar[list[str]] = ["cellpose>=3.0", "torch>=2.0"]
```
