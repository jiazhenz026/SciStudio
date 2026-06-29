# Public API boundary

Build only against the public surface. Importing internals produces code that
breaks on the next release — and it is the single most common authoring mistake.

## The rule

A symbol is public **only** when imported from a **canonical root** below and
listed in that root's `__all__`. Everything else is internal: importable today,
unsupported, and liable to move or vanish without notice.

| Canonical root | Public surface |
|---|---|
| `scistudio.core.types` | `DataObject`, `Array`, `DataFrame`, `Series`, `Text`, `Artifact`, `CompositeData`, `Collection`, `StorageReference`, `TypeSignature` |
| `scistudio.core.meta` | metadata facilities for subclassing a type |
| `scistudio.blocks.base` | `Block`, `BlockConfig`, `InputPort`, `OutputPort`, `ExecutionMode`, `PackageInfo`, interactive facilities |
| `scistudio.blocks.process` | `ProcessBlock` |
| `scistudio.blocks.io` | `IOBlock`, `SimpleLoader`, `SimpleSaver`, `FormatCapability`, `MetadataFidelity` |
| `scistudio.blocks.app` | `AppBlock`, `FileExchangeBridge`, `FileWatcher`, `validate_app_command` |
| `scistudio.blocks.code` | `CodeBlock`, `CodeBlockConfig`, `PortFileConfig` |
| `scistudio.previewers.models` | `PreviewerSpec`, `FrontendManifest`, owner-kind / API-version constants |
| `scistudio.previewers.data_access` | bounded preview-read helpers |
| `scistudio.stability` | `stable`, `provisional`, `internal` decorators |

```python
# CORRECT — canonical roots
from scistudio.blocks.base import Block, BlockConfig, InputPort, OutputPort
from scistudio.blocks.process import ProcessBlock
from scistudio.core.types import Array, DataFrame, Collection

# WRONG — deep module paths (internal; will break)
from scistudio.blocks.base.block import Block            # ✗
from scistudio.blocks.base.ports import InputPort        # ✗
from scistudio.blocks.process.process_block import ProcessBlock  # ✗
```

## Hard prohibitions

- **No deep module paths.** Import `from scistudio.blocks.base import InputPort`,
  never `from scistudio.blocks.base.ports import InputPort`. The deep path couples
  you to internal file layout.
- **No underscore modules or members.** `scistudio.*._anything`, `_support`,
  `_guess_mime`, `_PopenProcessAdapter`, `scistudio.utils.*` internals — never.
  If you think you need one, you are missing a public path: stop and find it, or
  ask.
- **Not author extension points:** `AIBlock` and `SubWorkflowBlock` are runtime
  base classes the engine composes — do **not** subclass them to author a block.
  To put AI in a workflow, the user adds the built-in **AI Agent** block and
  configures it (prompt + ports); you do not write an `AIBlock` subclass.

## Stability and version

Every public symbol carries a tier and a `Since` (via `scistudio.stability`
decorators, visible in the API reference):

- `stable` — rely on it; no incompatible change within a major version without a
  deprecation period.
- `provisional` — usable, may change in a minor release.
- `internal` — excluded from the public surface; never rely on it.

Prefer `stable` symbols. When you author a package's public symbols, mark them
with the same decorators against the package's own version line.

## Packages

A package's public symbols live at its **top level**, e.g.
`from scistudio_blocks_spectroscopy import Spectrum` — never a deep path like
`scistudio_blocks_spectroscopy.types`, and never its `_support` module. See
[package-discovery.md](package-discovery.md).
