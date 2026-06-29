# Package discovery

Installed packages (imaging, LC-MS, spectroscopy, …) add types, blocks, and
previewers. Discover and use them through their **public** surface — never their
internals.

## Discover what is available

Use the MCP tools, not source reading or guessing:

| Need | Tool |
|---|---|
| Which blocks exist (built-in + all installed packages) | `list_blocks` |
| Which data types are registered | `list_types` |
| A block's exact ports + `config_schema` | `get_block_schema(block_type)` |

`list_blocks` / `list_types` return the canonical, namespaced names
(`imaging.threshold`, `Spectrum`). Treat their output as authoritative; do not
type names from memory.

## Use a package's public symbols

When you author code (a custom block or a plot) that references a package type,
import it from the package **top level**:

```python
from scistudio_blocks_spectroscopy import Spectrum   # CORRECT
# from scistudio_blocks_spectroscopy.types import Spectrum   # WRONG (deep path)
# from scistudio_blocks_spectroscopy._support import ...      # WRONG (internal)
```

A package's reuse surface is **its types plus their constructors and inherited
accessors**. A package type subclasses a core type, so it already has
`to_memory()` / `to_pandas()` / `to_numpy()` / `sel()` / `with_meta()`
([data-types.md](data-types.md)) — use those, never a `_support` helper. Domain
construction is a `from_<domain>` classmethod **on the type**
(e.g. `Spectrum.from_arrays(...)`).

## Prefer reuse over authoring

Before writing a new block, `list_blocks` and reuse one whose I/O contract matches.
Before writing a new type, `list_types` and reuse the most specific
existing one; only declare a new `DataObject` subclass when none fits. Prefer the
core `Load`/`Save` blocks with a `core_type` (they cover package types) over a
package-specific IO block unless no `core_type` fits — see
[workflow-schema.md](workflow-schema.md).
