---
doc_type: block-development
title: "Block Developer SDK Quickstart"
status: living
owner: "@jiazhenz026"
last_updated: 2026-05-19
governed_by:
  - ADR-042
  - ADR-043
summary: "Five-minute block authoring guide with pointers to process blocks and simple local IO blocks."
---

# Block Developer SDK -- Quickstart

Build your first SciEasy block in five minutes.

---

## What is a block?

A **block** is a self-contained unit of computation with typed inputs, typed
outputs, and validated configuration. Users wire blocks together on a visual
canvas to form workflows. The runtime executes each block in an isolated
subprocess.

---

## Five-minute example: Invert Image

Create a file called `invert_image.py`:

```python
"""Minimal ProcessBlock that inverts image intensities."""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np

from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.core.types.array import Array


class InvertImage(ProcessBlock):
    """Invert the intensity of each image in the input Collection."""

    name: ClassVar[str] = "Invert Image"
    description: ClassVar[str] = "Subtract each pixel from the maximum value."
    subcategory: ClassVar[str] = "preprocess"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Array], required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Array]),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {},
    }

    def process_item(self, item: Array, config: BlockConfig, state: Any = None) -> Array:
        data = np.asarray(item.to_memory())
        inverted = data.max() - data
        result = Array(
            axes=list(item.axes),
            shape=item.shape,
            dtype=str(inverted.dtype),
            framework=item.framework.derive(),
            user=dict(item.user),
        )
        result._data = inverted  # transient; auto-flushed by the framework
        return result
```

### What this code does

1. **Three required ClassVars** tell the runtime about the block:
   - `name` -- displayed in the block palette.
   - `input_ports` -- declares a single input accepting `Array` objects.
   - `output_ports` -- declares a single output producing `Array` objects.

2. **`process_item(self, item, config, state)`** is the Tier 1 entry point.
   The framework's default `run()` iterates the input Collection, calls
   `process_item` for each item, auto-flushes each result to storage, and
   packs the results into an output Collection. You only write the per-item
   logic.

3. **`item.to_memory()`** materialises the array data from storage. The item
   arrives as a lightweight reference; you must call `to_memory()` when you
   need the actual numpy array.

4. **`result._data = inverted`** is a transient assignment. The framework's
   auto-flush mechanism persists this to zarr storage before the result
   crosses the block boundary. In production IOBlock loaders, prefer
   `persist_array()` for streaming writes (see
   [IOBlock persist helpers](block-contract.md#ioblock-persist-helpers)).

---

## Where to save the file

**Tier 1 (drop-in file):** Place the `.py` file in your project's `blocks/`
directory or `~/.scieasy/blocks/`. The runtime discovers it automatically.

**Tier 2 (installable package):** Create a Python package with
`pyproject.toml` and `scieasy.blocks` entry-points. See
[Publishing](publishing.md).

---

## Loading or saving local files

For a quick local loader or saver, use `SimpleLoader` or `SimpleSaver` instead
of a full package capability declaration. The framework synthesizes a
conservative `pixel_only` `FormatCapability` from the type, extension, format
id, and handler method.

```python
from pathlib import Path
from typing import Any, ClassVar

from scieasy.blocks.io.simple_io import SimpleLoader
from scieasy.core.types.array import Array


class LoadNpy(SimpleLoader):
    name: ClassVar[str] = "Load NPY"
    output_type: ClassVar[type] = Array
    extensions: ClassVar[list[str]] = [".npy"]
    format_id: ClassVar[str] = "npy"

    def load_file(self, path: Path, config: dict[str, Any]) -> Array:
        ...
```

Published packages should use explicit `FormatCapability` records when they
support multiple formats, need stable replay IDs, declare metadata fidelity, or
may conflict with another package. See [Block Contract](block-contract.md) and
[Publishing](publishing.md).

---

## Test it immediately

```python
from scieasy.testing import BlockTestHarness

def test_invert_image_contract():
    from invert_image import InvertImage
    harness = BlockTestHarness(InvertImage)
    errors = harness.validate_block()
    assert not errors, errors
```

The `BlockTestHarness.validate_block()` method checks that your block
satisfies the contract: correct ClassVars, concrete `run()`, proper port
declarations, and a non-empty `name`.

---

## Next steps

| Topic | Document |
|-------|----------|
| Subprocess isolation and execution model | [Architecture for Block Devs](architecture-for-block-devs.md) |
| Formal ClassVar specification and hooks | [Block Contract](block-contract.md) |
| Core data types and lazy loading | [Data Types](data-types.md) |
| Working with Collections | [Collection Guide](collection-guide.md) |
| Memory-safe processing for large data | [Memory Safety](memory-safety.md) |
| Creating custom domain types | [Custom Types](custom-types.md) |
| Testing with BlockTestHarness | [Testing](testing.md) |
| Packaging and distributing blocks | [Publishing](publishing.md) |
