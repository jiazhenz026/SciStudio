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

Build your first SciStudio block in five minutes.

---

## What is a block?

A **block** is a self-contained unit of computation with typed inputs, typed
outputs, and validated configuration. Users wire blocks together on a visual
canvas to form workflows. The runtime executes most blocks in an isolated
subprocess; interactive blocks are the exception and run in-process (see
[Architecture for Block Devs](architecture-for-block-devs.md)).

---

## Five-minute example: Invert Image

Create a file called `invert_image.py`:

```python
"""Minimal ProcessBlock that inverts image intensities."""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.array import Array


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
        return Array(
            axes=list(item.axes),
            shape=item.shape,
            dtype=str(inverted.dtype),
            framework=item.framework.derive(),
            user=dict(item.user),
            data=inverted,  # in-memory result; auto-flushed by the framework
        )
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

4. **`data=inverted`** passes the in-memory result to the `Array` constructor
   (ADR-031 Addendum 2). It is stored in the transient `_transient_data` slot;
   the framework's auto-flush mechanism persists it to zarr storage before the
   result crosses the block boundary. In production IOBlock loaders, prefer
   `persist_array()` for streaming writes (see
   [IOBlock persist helpers](block-contract.md#ioblock-persist-helpers)).

---

## Where to save the file

**Tier 1 (drop-in file):** Place the `.py` file in your project's `blocks/`
directory or `~/.scistudio/blocks/`. The runtime discovers it automatically.

**Tier 2 (installable package):** Create a Python package with
`pyproject.toml` and `scistudio.blocks` entry-points. See
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

from scistudio.blocks.io.simple_io import SimpleLoader
from scistudio.core.types.array import Array


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
from scistudio.testing import BlockTestHarness

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

## Data Access Strategies

Block authors choose how to read input data and how to produce output data.
The framework supports both full materialization and streaming -- choose based
on your expected data size.

### Reading input data

| Strategy | API | Memory | When to use |
|----------|-----|--------|-------------|
| **Full load** | `arr = item.to_memory()` | O(full array) | Data fits in RAM; need full array for computation |
| **Partial read** | `plane = item.sel(z=5)` | O(slice) | Only need a subset of dimensions |
| **Chunked iteration** | `for chunk in item.iter_chunks(1024):` | O(chunk) | Process large data piece by piece |

### Writing output data

| Strategy | API | Memory | When to use |
|----------|-----|--------|-------------|
| **Full output** | `Array(..., data=result)` | O(result) | Result fits in RAM (most blocks) |
| **Streaming write** | `ref = self.persist_array(chunk_iter, shape, dtype)` | O(chunk) | Producing very large output |

For the full streaming patterns and worked examples, see
[Memory Safety](memory-safety.md#data-access-strategies).

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
