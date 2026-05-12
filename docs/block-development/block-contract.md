# Block Contract

This document is the formal specification of the block contract. Every
block must satisfy these requirements to be valid in the SciEasy runtime.

---

## Table of Contents

1. [Block ABC and Inheritance Hierarchy](#block-abc-and-inheritance-hierarchy)
2. [Required ClassVar Declarations](#required-classvar-declarations)
3. [Optional ClassVar Declarations](#optional-classvar-declarations)
4. [The run() Contract](#the-run-contract)
5. [Hooks: validate() and postprocess()](#hooks-validate-and-postprocess)
6. [ProcessBlock Hooks](#processblock-hooks)
7. [IOBlock Hooks](#ioblock-hooks)
8. [Variadic Ports](#variadic-ports)
9. [Dynamic Ports](#dynamic-ports)
10. [Config Schema](#config-schema)
11. [Port Constraints](#port-constraints)

---

## Block ABC and Inheritance Hierarchy

All blocks inherit from `scieasy.blocks.base.block.Block` (ABC). The
framework provides six concrete base classes:

```
Block (ABC)
  +-- ProcessBlock    # Algorithm-driven data transformation
  +-- IOBlock         # Data loading and saving
  +-- CodeBlock       # User-written code execution
  +-- AppBlock        # External application integration (Fiji, Napari, etc.)
  +-- AIBlock         # AI-assisted operations
  +-- SubWorkflowBlock  # Nested workflow execution
```

Most block developers will subclass `ProcessBlock` or `IOBlock`.

---

## Required ClassVar Declarations

Every block must define these three ClassVars:

### `name: ClassVar[str]`

A human-readable display name. Must not be empty or `"Unnamed Block"`.

```python
name: ClassVar[str] = "Gaussian Blur"
```

### `input_ports: ClassVar[list[InputPort]]`

Declares the block's input connection endpoints. Each port specifies
accepted types and whether it is required.

```python
from scieasy.blocks.base.ports import InputPort
from scieasy.core.types.array import Array

input_ports: ClassVar[list[InputPort]] = [
    InputPort(name="image", accepted_types=[Array], required=True),
]
```

### `output_ports: ClassVar[list[OutputPort]]`

Declares the block's output connection endpoints.

```python
from scieasy.blocks.base.ports import OutputPort

output_ports: ClassVar[list[OutputPort]] = [
    OutputPort(name="image", accepted_types=[Array]),
]
```

### Port dataclass fields

```python
@dataclass(kw_only=True)
class Port:
    name: str                      # unique within the block
    accepted_types: list[type]     # empty list = accept any DataObject
    is_collection: bool = False    # hint for UI rendering
    description: str = ""
    required: bool = True

@dataclass(kw_only=True)
class InputPort(Port):
    default: Any | None = None
    constraint: Callable[[Any], bool] | None = None
    constraint_description: str = ""

@dataclass(kw_only=True)
class OutputPort(Port):
    pass
```

Type matching is `isinstance`-based: a port accepting `Array` will also
accept `Image` (since `Image` is a subclass of `Array`).

---

## Optional ClassVar Declarations

### `description: ClassVar[str]`

Human-readable description. Shown in the block palette and documentation.

### `version: ClassVar[str]`

Semantic version string. Default: `"0.1.0"`.

### `subcategory: ClassVar[str]`

Fine-grained palette grouping label (e.g., `"segmentation"`,
`"preprocess"`, `"io"`). The base category (`process`, `io`, `code`,
`app`, `ai`, `subworkflow`) is always inferred from the class hierarchy.

### `execution_mode: ClassVar[ExecutionMode]`

Execution mode hint. Default: `ExecutionMode.AUTO`.

### `terminate_grace_sec: ClassVar[float]`

Grace period (seconds) between SIGTERM and SIGKILL on cancellation.
Default: `5.0`.

### `key_dependencies: ClassVar[list[str]]`

Python package requirements. Displayed in the UI palette for user
guidance. Example: `["cellpose>=3.0", "torch>=2.0"]`.

### `config_schema: ClassVar[dict[str, Any]]`

JSON Schema for block configuration. Default: `{"type": "object", "properties": {}}`.
See [Config Schema](#config-schema) for details.

### Resource hints (ADR-022)

```python
requires_gpu: ClassVar[bool] = False   # not on Block ABC; set on your class
cpu_cores: ClassVar[int] = 1           # not on Block ABC; set on your class
```

---

## The run() Contract

Every block must have a concrete `run()` method with this signature:

```python
def run(
    self,
    inputs: dict[str, Collection],
    config: BlockConfig,
) -> dict[str, Collection]:
    ...
```

- **`inputs`**: Maps input port names to `Collection` instances. Each
  Collection wraps zero or more DataObject instances of the same type.
- **`config`**: `BlockConfig` instance (dict-like). Access parameters
  with `config.get("key", default)`.
- **Returns**: Maps output port names to `Collection` instances.

**Important**: `ProcessBlock` provides a default `run()` that calls
`process_item` per item. Most ProcessBlock subclasses do NOT override
`run()` directly.

---

## Hooks: validate() and postprocess()

### `validate(self, inputs: dict[str, Any]) -> bool`

Called before `run()`. Checks that all required ports have values and
that types match. The default implementation handles standard validation.
Override only if you need custom pre-run checks.

Raises `ValueError` on the first failed check.

### `postprocess(self, outputs: dict[str, Collection]) -> dict[str, Collection]`

Called after `run()`. Default: passes outputs through unchanged. Override
for cross-port consistency checks or output transformations.

---

## ProcessBlock Hooks

`ProcessBlock` (`scieasy.blocks.process.process_block.ProcessBlock`)
provides the setup/teardown lifecycle (ADR-027 D7).

### `setup(self, config: BlockConfig) -> Any`

Called once before iterating the input Collection. Use for expensive
one-time initialization:

- Loading an ML model
- Opening a database connection
- Compiling a regex
- Allocating a GPU context

The return value is passed to every `process_item` call as the `state`
argument and to `teardown`.

```python
def setup(self, config):
    from cellpose import models
    return models.Cellpose(model_type=config.get("model", "cyto3"))
```

**Rule**: `setup` receives only `config`. It must not access `inputs`.

### `process_item(self, item: Any, config: BlockConfig, state: Any = None) -> Any`

The Tier 1 entry point. Called once per item in the primary input
Collection. The `state` argument is whatever `setup()` returned.

```python
def process_item(self, item, config, state=None):
    data = np.asarray(item.to_memory())
    result_data = some_algorithm(data, state)
    result = Array(axes=list(item.axes), shape=result_data.shape, dtype=str(result_data.dtype))
    result._data = result_data
    return result
```

**Signature**: Always use the three-argument form
`(self, item, config, state=None)`. Legacy two-argument overrides
`(self, item, config)` are supported for backward compatibility but
should not be used in new code.

### `teardown(self, state: Any) -> None`

Called once after iteration, in a `finally` block. Always runs, even if
`process_item` raises an exception. Use to release resources:

```python
def teardown(self, state):
    if state is not None and hasattr(state, 'gpu') and state.gpu:
        import torch
        torch.cuda.empty_cache()
```

---

## IOBlock Hooks

`IOBlock` (`scieasy.blocks.io.io_block.IOBlock`) provides the
load/save dispatch.

### ClassVars

```python
direction: ClassVar[str] = "input"  # "input" for loaders, "output" for savers
```

### `load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection`

Called when `direction == "input"`. Must return a DataObject or
Collection.

**ADR-031 D4**: `output_dir` is the directory where loaders should
persist data. Two approaches:

#### Simple path (small/medium files)

Use one-shot `persist_array(ndarray)` to load and persist in one step:

```python
def load(self, config, output_dir=""):
    data = np.load(config.get("path"))
    ref = self.persist_array(data, data.shape, data.dtype, output_dir)
    return Array(axes=["y", "x"], shape=data.shape, dtype=str(data.dtype), storage_ref=ref)
```

#### Streaming path (large files)

Use iterator `persist_array(chunk_iter())` for constant-memory writes:

```python
def load(self, config, output_dir=""):
    import tifffile
    with tifffile.TiffFile(path) as tf:
        shape = (len(tf.pages), *tf.pages[0].shape)
        def page_chunks():
            for i, page in enumerate(tf.pages):
                yield (i, page.asarray())
        ref = self.persist_array(page_chunks(), shape, tf.pages[0].dtype, output_dir)
    return Array(axes=["z", "y", "x"], shape=shape, dtype=str(dtype), storage_ref=ref)
```

**Important (ADR-031 Addendum 1, A1-D3)**: IOBlock loaders MUST persist
directly via `persist_array()` or `persist_table()`. Do NOT use
`obj._data = ...` and rely on auto-flush in IOBlock loaders. Auto-flush
is a safety net for ProcessBlocks only.

### Persist helpers (Block base class)

Available on **all block types** (defined on `Block`, not just `IOBlock`).

#### `persist_array(data_or_iterator, shape, dtype, output_dir, chunks=None) -> StorageReference`

Writes array data to zarr storage. Accepts either a numpy ndarray (one
shot) or an iterator yielding `(index, chunk_array)` tuples for
constant-memory streaming writes.

#### `persist_table(table, output_dir) -> StorageReference`

Writes a `pyarrow.Table` to parquet storage. Returns a StorageReference.

### `save(self, obj: DataObject | Collection, config: BlockConfig) -> None`

Called when `direction == "output"`. Persist the object to the configured
path. The base class wraps the path in a `Text` Collection as a receipt.

---

## Variadic Ports

**ADR-029**: Blocks can declare user-configurable port lists.

### ClassVars for variadic ports

```python
variadic_inputs: ClassVar[bool] = False
variadic_outputs: ClassVar[bool] = False
allowed_input_types: ClassVar[list[type]] = []    # empty = any DataObject
allowed_output_types: ClassVar[list[type]] = []
min_input_ports: ClassVar[int | None] = None      # None = no limit
max_input_ports: ClassVar[int | None] = None
min_output_ports: ClassVar[int | None] = None
max_output_ports: ClassVar[int | None] = None
```

When `variadic_inputs` is `True`, the block's input ports are determined
per-instance from `self.config["input_ports"]` (a list of
`{"name": str, "types": [str]}` dicts) rather than from the ClassVar.

### Effective ports

Use `get_effective_input_ports()` / `get_effective_output_ports()` to
read the per-instance port list:

```python
def run(self, inputs, config):
    effective_ports = self.get_effective_input_ports()
    for port in effective_ports:
        data = inputs.get(port.name)
        # ...
```

---

## Dynamic Ports

**ADR-028 Addendum 1**: Blocks can declare ports whose accepted types
change based on a config value.

```python
dynamic_ports: ClassVar[dict[str, Any] | None] = {
    "source_config_key": "data_type",
    "output_port_mapping": {
        "data": {
            "array": ["Array"],
            "table": ["DataFrame"],
        },
    },
}
```

The `source_config_key` identifies which config field drives the type
override. The `output_port_mapping` maps port names to enum values to
type name lists. This is validated at registry scan time.

---

## Config Schema

Block configuration is declared via `config_schema`, a JSON Schema object
with optional `ui_widget` hints.

```python
config_schema: ClassVar[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "path": {
            "type": ["string", "array"],
            "items": {"type": "string"},
            "ui_priority": 0,
            "ui_widget": "file_browser",
        },
        "threshold": {
            "type": "number",
            "default": 0.5,
            "minimum": 0.0,
            "maximum": 1.0,
            "ui_widget": "slider",
        },
        "notes": {
            "type": "string",
            "ui_widget": "text_area",
        },
        "output_dir": {
            "type": "string",
            "ui_widget": "directory_browser",
        },
    },
    "required": ["path"],
}
```

### Supported `ui_widget` hints

| Widget | Use case |
|--------|----------|
| `file_browser` | File selection dialog |
| `directory_browser` | Directory selection dialog |
| `slider` | Numeric range input |
| `text_area` | Multi-line text input |
| `port_editor` | Variadic port editor (ADR-029) |

### Config schema MRO merge (ADR-030)

When a subclass inherits from a base with its own `config_schema`, the
schemas are merged using MRO (Method Resolution Order). The subclass's
properties override the base's properties of the same name. The
`required` arrays are unioned.

For example, `IOBlock` declares `config_schema` with a `path` property.
An `IOBlock` subclass like `LoadImage` adds an `axes` property. The
effective schema includes both `path` (from IOBlock) and `axes` (from
LoadImage).

---

## Port Constraints

Input ports can carry custom validation functions:

```python
def _check_positive(value):
    if hasattr(value, 'to_memory'):
        data = value.to_memory()
        return bool(data.min() >= 0)
    return True

input_ports: ClassVar[list[InputPort]] = [
    InputPort(
        name="image",
        accepted_types=[Array],
        constraint=_check_positive,
        constraint_description="All pixel values must be non-negative",
    ),
]
```

The `validate()` hook calls `validate_port_constraint(port, value)` for
each input. If the constraint function returns `False`, validation fails
with the `constraint_description` message.

---

## AppBlock: variadic ports + extension-based output binning

**Issue #680**: All AppBlock subclasses (Fiji, Napari, ElMAVEN, custom
external-app blocks) inherit:

- `variadic_inputs = True` and `variadic_outputs = True` — the user
  defines input and output ports via the standard ADR-029 port editor.
- A required `extension` field on every output port entry. The runtime
  uses this string (no leading dot, case-insensitive) to bin saved
  files into ports.
- A generic binner method `_bin_outputs_by_extension(output_files,
  config)` that subclasses call after their watcher returns.

### Routing rules

After the external app produces output files, the binner:

1. For each port, finds files whose suffix (case-insensitively) matches
   the port's declared extension and wraps them as
   `Artifact(file_path=..., mime_type=..., description=...)` instances
   in a `Collection(item_type=port.accepted_types[0])`.
2. Raises `ValueError("Port 'X' required, no '.ext' files in output dir")`
   when a required port receives zero files.
3. Logs `WARNING — Unmatched output file 'name.ext'` for files whose
   extension matches no port and continues.

### Config-save validation

The workflow validator's **Check 8** rejects configurations where two
output ports on the same variadic-output block declare the same
extension (case-insensitive):

```
Node 'A': Duplicate extension 'tif' across output ports {images, masks}
```

This catches the only ambiguity in the routing model at save time,
before the workflow runs.

### Subclass authoring

Concrete AppBlock subclasses keep their `output_ports` ClassVar as a
**default scaffold** that the user may override via the editor. The
`run()` method ends with:

```python
if config.get("output_ports"):
    return self._bin_outputs_by_extension(output_files, config)
# Backwards-compatible fallback when no ports are declared:
from scieasy.blocks.app.bridge import _guess_mime
from scieasy.core.types.artifact import Artifact
from scieasy.core.types.collection import Collection
artifacts = [
    Artifact(file_path=p, mime_type=_guess_mime(p), description=p.name)
    for p in output_files
]
return {"image": Collection(artifacts, item_type=Artifact)} if artifacts else {}
```

### What the binner does NOT do

- No file content inspection or type inference (the user is responsible
  for saving the right kind of data into the declared extension).
- No multi-extension ports (one extension per port — Collections are
  homogeneous by type).
- No per-port glob fields.
- No automatic port creation based on saved content.
