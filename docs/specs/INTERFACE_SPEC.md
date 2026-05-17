# SciEasy Interface Specification — Single Source of Truth

> **Status**: DRAFT v0.1 (Phase 6 manager-write — Pass 1 of 2; awaiting Pass 2 + Phase 7 audit + Phase 8 acceptance).
> **Authority**: When ACCEPTED, this document supersedes any conflicting prose in `docs/adr/`, `docs/architecture/`, `CLAUDE.md`, or `docs/specs/phase11-*`. To change an interface, amend this document first; conflicting edits to other docs will be reverted in review.
> **Baseline SHA**: `a4b8b5f` (post-ADR-040 cascade merge).
> **Cascade**: dual-cascade SSOT (Claude Code track/spec-ssot #1090/PR-#1091 + Codex PR #1094).
> **Authority hierarchy**: `docs/architecture/ARCHITECTURE.md` PRIMARY > ADR SUPPLEMENTARY > `CLAUDE.md` (process conventions only).
>
> **Detailedness policy** (user direction 2026-05-17): every entry — regardless of a/b/c/d status — carries its FULL signature. d-class entries are NOT compressed; the SSOT documents the contract whether or not it's currently public, well-implemented, or doc-aligned. Future devs and audit agents need exact contract surface.
>
> **Pass status**: **PASS 1 COMPLETE** (modules 1-7 with full signatures, ~120 entries). **PASS 2 PENDING** (modules 8-13 + cross-cutting C-class).

---

## How to read this document

This file is the **machine-checkable SSOT**. The grammar is consumed by `scripts/spec_audit/extract_spec.py` and verified by `scripts/spec_audit.py` CI hook (enabled in Phase 8).

Each interface entry uses this grammar:

```text
H3-heading: backticked interface id — one-line description
Status: a | b | c | d
Source: `path/to/file.py:Lnn-Lmm`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §X.Y` OR [ARCHITECTURE: not documented]
Supplementary-doc-source: ADR-NNN §X, ADR-MMM §Y    (optional, comma-separated)
Issue: #NNN OR #TBD-short                            (required if Status in {b,c,d})

fenced-code-block: lang + full verbatim signature
```

### Status taxonomy

- **a — Aligned**: interface present in code AND in ARCH/ADR docs; signatures match. Lifted verbatim from both sides (they agree).
- **b — Both, disagree**: present in both, but code/docs differ on signature, default, type, or behavior. The chosen authoritative signature appears here; the losing side gets a fix issue. Sub-labels: `b-code-wins` / `b-docs-wins`.
- **c — Code missing**: documented (in docs or in an issue's spec text) but not implemented. The contract HERE establishes what SHOULD be implemented. Sub-labels: `c-impl` (implement) / `c-drop` (remove from docs/spec) / `c-defer` (mark deferred to ADR-N or issue #N).
- **d — Docs missing**: implemented but undocumented in ARCH/ADR. The contract HERE establishes the canonical signature; ARCH should be amended to reference back to this SSOT entry. Sub-labels: `d-document` (load-bearing public surface — document fully) / `d-private` (implementation detail — rename `_underscore` and mark as private) / `d-remove` (dead code — schedule deletion).

**Detailedness invariant**: every entry, regardless of class, includes (a) full signature, (b) every field/parameter, (c) every constraint/default/exception, (d) every cross-reference. Sub-labels indicate ACTION direction, not detail level.

### Module map (N=13, per Phase 1 enumeration)

1. block-abc · 2. port-system · 3. data-types · 4. storage-backends · 5. collection-transport · 6. block-registry · 7. execution-engine · 8. lineage-db · 9. rest-api · 10. ws-sse-protocol · 11. mcp-tools · 12. versioning-git · 13. agent-provisioning

Cross-cutting: 2 C-class architecture findings (M05 cross-layer coupling + M06 validator-strictness) at end (Pass 2).

---

## 1. block-abc

**Module preamble** (from Codex M02 reconciliation, ARCH §5.1+§5.3): Block base contract — typed ports, `run(inputs, config) -> dict[str, Collection]`, 8-state lifecycle — is the stable A-class core of the workflow runtime. Dynamic/variadic port semantics (ADR-028 Addendum 1 / ADR-029) are first-class. Plugin registry strictness has a documented warning/fallback path (b — docs-fix). 6 concrete block categories ship in core: `ProcessBlock`, `IOBlock`, `CodeBlock`, `AppBlock`, `AIBlock`, `SubWorkflowBlock`. Domain types live in plugins per ADR-027 D2.

### `block-abc.BlockState` — 8-state lifecycle enum
Status: a
Source: `src/scieasy/blocks/base/state.py:L8-L18`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.1`
Supplementary-doc-source: ADR-018 §2.1

```python
class BlockState(Enum):
    IDLE      = "idle"
    READY     = "ready"
    RUNNING   = "running"
    PAUSED    = "paused"
    DONE      = "done"
    ERROR     = "error"
    CANCELLED = "cancelled"    # ADR-018: user explicitly terminated
    SKIPPED   = "skipped"      # ADR-018: required upstream inputs missing

# Valid transitions (from _VALID_TRANSITIONS in block.py:L22-L31):
#   IDLE      → {READY, SKIPPED, ERROR}
#   READY     → {RUNNING, SKIPPED, ERROR}
#   RUNNING   → {DONE, PAUSED, ERROR, CANCELLED}
#   PAUSED    → {RUNNING, ERROR, CANCELLED}
#   DONE / ERROR / CANCELLED / SKIPPED → {IDLE}   (workflow reset only)
```

### `block-abc.ExecutionMode` — block execution style enum
Status: a
Source: `src/scieasy/blocks/base/state.py:L21-L26`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.1`

```python
class ExecutionMode(Enum):
    AUTO        = "auto"           # engine-managed subprocess (ADR-017)
    INTERACTIVE = "interactive"    # user interaction required during run
    EXTERNAL    = "external"       # delegates to external process (AppBlock, AIBlock)
```

### `block-abc.BlockConfig` — Pydantic param container
Status: a
Source: `src/scieasy/blocks/base/config.py:L10-L33`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.1`
Supplementary-doc-source: ADR-030

```python
class BlockConfig(BaseModel):
    model_config = ConfigDict(extra="allow")    # scheduler injects runtime keys (#565)
    params: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        """Lookup key in self.params first, then self.__pydantic_fields__,
        finally return default."""
```

### `block-abc.Block` — abstract base class for all processing blocks
Status: b
Source: `src/scieasy/blocks/base/block.py:L34-L512`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.1`
Supplementary-doc-source: ADR-004, ADR-017, ADR-018, ADR-020, ADR-027, ADR-029
Issue: #TBD-block-class-vars-arch-update

```python
class Block(ABC):
    """Abstract base for all SciEasy blocks.

    Sub-label b-code-wins: ARCH §5.1 declares allowed_input_types as
    [DataObject]; code defaults to [] (empty = accept any). Plus many
    ClassVars (variadic, dynamic_ports, min/max bounds, key_dependencies)
    ARCH omits. The code is current truth — ARCH must update.
    """

    # --- Identity ClassVars (overridden by subclasses) ---
    name: ClassVar[str] = "Unnamed Block"
    description: ClassVar[str] = ""
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = ""    # palette grouping (#588)

    # --- Port declarations ---
    input_ports: ClassVar[list[InputPort]] = []
    output_ports: ClassVar[list[OutputPort]] = []
    variadic_inputs: ClassVar[bool] = False
    variadic_outputs: ClassVar[bool] = False
    allowed_input_types: ClassVar[list[type]] = []     # empty = any DataObject; ARCH said [DataObject]
    allowed_output_types: ClassVar[list[type]] = []
    min_input_ports: ClassVar[int | None] = None
    max_input_ports: ClassVar[int | None] = None
    min_output_ports: ClassVar[int | None] = None
    max_output_ports: ClassVar[int | None] = None
    dynamic_ports: ClassVar[dict[str, Any] | None] = None    # ADR-028 Add 1; see dedicated entry

    # --- Execution declarations ---
    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.AUTO
    terminate_grace_sec: ClassVar[float] = 5.0    # ADR-019 grace before SIGKILL
    key_dependencies: ClassVar[list[str]] = []    # pre-ADR-038 partial freeze (now deprecated)

    # --- Config schema (JSON Schema dict; MRO-merged via ADR-030) ---
    config_schema: ClassVar[dict[str, Any]] = {"type": "object", "properties": {}}

    # --- Instance state ---
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = BlockConfig(**(config or {}))
        self.state = BlockState.IDLE
```

### `block-abc.Block.transition` — state machine transition method
Status: d
Source: `src/scieasy/blocks/base/block.py:L115-L138`
Primary-doc-source: `[ARCHITECTURE: §5.1 diagram only — method signature not documented]`
Issue: #TBD-block-transition-document

```python
def transition(self, target: BlockState) -> None:
    """Validate and apply a state transition.

    Looks up self.state in _VALID_TRANSITIONS table; if target not in
    the allowed-from-current set, raises RuntimeError with the rejected
    pair. Otherwise mutates self.state = target.

    Load-bearing: called by both the worker subprocess (during run()
    when it self-reports terminal state per issue #681) and the
    scheduler (when reacting to PROCESS_EXITED or external cancel).

    Sub-label d-document: this is a public method on the Block ABC.
    ARCH §5.1 shows the state diagram but does NOT specify the
    transition() method or its exception contract. SSOT establishes:
    raises RuntimeError on invalid transition.

    Raises:
        RuntimeError: if (self.state, target) is not in _VALID_TRANSITIONS.
    """
```

### `block-abc.Block.validate` — pre-run input validation
Status: b
Source: `src/scieasy/blocks/base/block.py:L170-L183`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.1`
Issue: #TBD-block-validate-annotation

```python
def validate(self, inputs: dict[str, Any]) -> bool:
    """Pre-run input validation.

    Sub-label b-code-wins: code uses dict[str, Any] for loose
    pre-conversion inputs (the scheduler may pass partially-formed
    Collections); ARCH §5.1 declares dict[str, Collection]. Code is
    truth. ARCH must update OR scheduler must always pass full
    Collections (less likely — current code path is intentional).

    Returns True if every required port has a non-None value AND every
    constraint passes. Returns False to abort dispatch (scheduler will
    transition this block to ERROR with a clear diagnostic).

    Raises:
        ValueError: on missing required port, type mismatch (per
            port.accepted_types MRO check), constraint failure
            (callable returned False or raised).
    """
```

### `block-abc.Block.run` — abstract execution entry point
Status: a
Source: `src/scieasy/blocks/base/block.py:L185-L207`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.1`

```python
@abstractmethod
def run(
    self,
    inputs: dict[str, Collection],
    config: BlockConfig,
) -> dict[str, Collection]:
    """Core execution logic. Subclasses MUST override.

    Always executes inside an isolated subprocess (ADR-017). The
    engine serialises StorageReference pointers to the worker; the
    worker reconstructs typed DataObject instances (ADR-031 D7) and
    wraps them in Collections.

    Args:
        inputs: Each key is an input port name. Each value is a
            Collection of DataObject (homogeneous per port; the
            Collection's item_type matches the port's accepted_types).
            For non-variadic blocks, every required port in
            input_ports must be present.
        config: BlockConfig with this instance's runtime params. The
            config may carry scheduler-injected keys via
            extra="allow" (#565).

    Returns:
        dict mapping output port names to Collections. Every required
        output port in output_ports must be present. Collection
        contents must respect the port's accepted_types.
    """
```

### `block-abc.Block.postprocess` — optional output transform hook
Status: b
Source: `src/scieasy/blocks/base/block.py:L248-L255`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.1`
Issue: #TBD-block-postprocess-annotation

```python
def postprocess(
    self,
    outputs: dict[str, Collection],
) -> dict[str, Collection]:
    """Optional cleanup / logging / output transformation hook.

    Sub-label b-code-wins: code uses dict[str, Collection] per
    ADR-020 (post-Collection-transport refactor); ARCH §5.1
    pseudocode still shows dict[str, DataObject]. ARCH must update.

    Default implementation returns outputs unchanged. Override only
    if the block needs to perform per-output-port transformations
    (e.g. annotating with run metadata, deriving aggregated metrics).
    """
    return outputs
```

### `block-abc.Block.get_effective_input_ports` / `get_effective_output_ports` — variadic-aware port resolution
Status: a
Source: `src/scieasy/blocks/base/block.py:L213-L246`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.4`
Supplementary-doc-source: ADR-028 Addendum 1, ADR-029

```python
def get_effective_input_ports(self) -> list[InputPort]:
    """Return per-instance input ports, accounting for variadic + dynamic.

    Resolution order:
      1. If self.dynamic_ports descriptor is set AND the source config
         key resolves to an enum value, materialize per-instance
         InputPorts with narrowed accepted_types per the
         output_port_mapping[port_name][enum_value] type list.
      2. Otherwise if self.variadic_inputs is True AND
         self.config["input_ports"] is set, materialize per-instance
         InputPorts via ports_from_config_dicts() (ADR-029 D1).
      3. Otherwise return self.input_ports (the static ClassVar list).

    The scheduler, the validator, and the frontend BlockNode renderer
    all consume this method's output (not the static ClassVar) so the
    runtime sees the per-instance port list transparently.
    """

def get_effective_output_ports(self) -> list[OutputPort]:
    """Mirror of get_effective_input_ports for output side."""
```

### `block-abc.Block.pack` / `Block.unpack` / `Block.unpack_single` — Collection utilities
Status: a
Source: `src/scieasy/blocks/base/block.py:L268-L297`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.1, §6.2`

```python
@staticmethod
def pack(items: list[DataObject], item_type: type | None = None) -> Collection:
    """Wrap a list of DataObjects into a Collection.

    Auto-infers item_type from items[0] if not provided. Auto-flushes
    each item to storage if its storage_ref is None (Tier 3 safety
    net per ADR-020 Add 5). Empty list yields an empty Collection
    with item_type defaulted to DataObject.
    """

@staticmethod
def unpack(collection: Collection) -> list[DataObject]:
    """Return collection.items as a fresh list. Memory: O(N items)."""

@staticmethod
def unpack_single(collection: Collection) -> DataObject:
    """Return the single item from a length-1 Collection.

    Raises:
        ValueError: if len(collection) != 1.
    """
```

### `block-abc.Block.map_items` / `Block.parallel_map` — Tier 2 iteration helpers
Status: a
Source: `src/scieasy/blocks/base/block.py:L299-L332`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.1, §6.2`

```python
@staticmethod
def map_items(
    func: Callable[[DataObject], DataObject],
    collection: Collection,
) -> Collection:
    """Apply func to each item sequentially. Auto-flushes each result
    to storage between items (constant peak memory: 1 input + 1 output)."""

@staticmethod
def parallel_map(
    func: Callable[[DataObject], DataObject],
    collection: Collection,
    max_workers: int = 4,
) -> Collection:
    """Apply func to each item via a process pool. Auto-flushes each
    result. Warning: loads max_workers items concurrently — use
    map_items for large per-item memory."""
```

### `block-abc.Block.persist_array` / `Block.persist_table` — streaming-write helpers
Status: d
Source: `src/scieasy/blocks/base/block.py:L334-L434`
Primary-doc-source: `[ARCHITECTURE: §4.3 mentions at IOBlock level; not enumerated on Block]`
Issue: #TBD-block-persist-helpers-document

```python
def persist_array(
    self,
    data_or_iterator: Any,
    shape: tuple[int, ...],
    dtype: Any,
    output_dir: str | None = None,
    chunks: tuple[int, ...] | None = None,
) -> StorageReference:
    """Stream-write an Array to Zarr backend without materializing fully.

    Sub-label d-document: ADR-031 Addendum 1 added these methods to
    the base Block class (not just IOBlock). Load-bearing for
    streaming-write block authors who can't fit the full array in
    memory. ARCH §4.3 only mentions IOBlock; SSOT establishes
    Block-level availability.

    Args:
        data_or_iterator: Either a numpy ndarray (writes immediately)
            OR an iterator yielding chunk-shaped sub-arrays (writes
            chunk-by-chunk).
        shape: Full output shape (used to allocate Zarr store).
        dtype: numpy dtype.
        output_dir: Override output directory; if None, uses the
            block's configured output_dir (flush_context).
        chunks: Zarr chunk shape; if None, sensible default.

    Returns:
        StorageReference with backend="zarr" pointing at the new store.
    """

def persist_table(
    self,
    table: Any,
    output_dir: str | None = None,
) -> StorageReference:
    """Write a pyarrow.Table or pandas.DataFrame to Arrow/Parquet.

    Returns StorageReference with backend="arrow".
    """
```

### `block-abc.Block._auto_flush` — Tier 3 safety-net flush
Status: a
Source: `src/scieasy/blocks/base/block.py:L436-L512`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §6.2`
Supplementary-doc-source: ADR-020 Add 5, ADR-031 D5

```python
@staticmethod
def _auto_flush(obj: Any) -> Any:
    """Tier-3 safety-net flush.

    No-op cases:
      - obj.storage_ref is already set (already persisted)
      - flush_context.get_output_dir() returns None (no output dir set)
      - obj is Artifact with file_path set (file-mode pass-through)

    Recursive case:
      - obj is CompositeData: recursively flush each slot, then
        return a new CompositeData with the flushed slots.

    Otherwise: write obj to flush_context's output_dir via the
    appropriate backend (BackendRouter.dispatch(type(obj))), set
    storage_ref to the new reference, return obj.

    Raises:
        RuntimeError: on write failure.
    """
```

### `block-abc.Block.dynamic_ports` — ClassVar enum-driven port descriptor
Status: a
Source: `src/scieasy/blocks/base/block.py:L82-L103`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.4`
Supplementary-doc-source: ADR-028 Addendum 1 §C5

```python
dynamic_ports: ClassVar[dict[str, Any] | None] = None
"""Descriptor for per-instance port narrowing based on a config enum.

Shape:
    {
        "source_config_key": str,                # which config field drives narrowing
        "output_port_mapping": {                 # which output ports are narrowed
            "<port_name>": {
                "<enum_value>": ["TypeName", ...],   # types to narrow to
                ...
            },
            ...
        }
    }

Validated at registry scan time by BlockRegistry._validate_dynamic_ports.
Consumed by Block.get_effective_input_ports / get_effective_output_ports.
The validator, the scheduler, and the frontend BlockNode all use the
effective (narrowed) port list.

Example (LoadData):
    dynamic_ports = {
        "source_config_key": "core_type",
        "output_port_mapping": {
            "data": {
                "Array":         ["Array"],
                "DataFrame":     ["DataFrame"],
                "CompositeData": ["CompositeData"],
            }
        }
    }
"""
```

### `block-abc.ProcessBlock` — deterministic algorithmic transformation
Status: a
Source: `src/scieasy/blocks/process/process_block.py:L23-L207`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.3`
Supplementary-doc-source: ADR-004, ADR-020, ADR-027 D7

```python
class ProcessBlock(Block):
    """Workhorse base for data transformation blocks.

    Authors override process_item() (Tier 1, 80% of cases) for
    per-item processing with auto-flushing iteration. Or override
    setup()/teardown() (Tier 2) for resources amortised across the
    Collection (model loading, DB connections).

    Provides default run() that iterates input Collection,
    auto-flushes each result.
    """
    algorithm: ClassVar[str] = ""    # algorithm identifier for palette / docs

    def setup(self, config: BlockConfig) -> Any:
        """One-shot per-run setup hook (ADR-027 D7).

        Called once per run() call before iteration begins. Returns an
        opaque state object passed to every process_item() call.
        Default returns None.

        Use for: loading ML models, opening DB connections, compiling
        regexes — anything expensive to amortise across items.

        Called INSIDE the worker subprocess after TypeRegistry.scan()
        and input reconstruction. State lives for one run() and is
        GC'd with the subprocess.

        IMPORTANT: setup() receives only config — NOT inputs.
        Data-driven init belongs inside process_item() (lazy init +
        cache on state).
        """
        return None

    def teardown(self, state: Any) -> None:
        """Cleanup hook called in a finally block (ADR-027 D7).

        Default no-op. Use for: torch.cuda.empty_cache(), conn.close(),
        releasing GPU memory, similar cleanup. Runs even when
        process_item() raises.
        """
        pass

    def process_item(
        self,
        item: DataObject,
        config: BlockConfig,
        state: Any = None,
    ) -> DataObject:
        """Override this for per-item processing.

        Code annotates item/return as Any for backward-compat with
        2-arg overrides; D1 / ADR-027 D7 specify DataObject (intended
        semantic type). Subclasses targeting Tier 1 just override
        this method; the default run() handles iteration, auto-flush,
        and Collection packing.
        """
        raise NotImplementedError

    def run(
        self,
        inputs: dict[str, Collection],
        config: BlockConfig,
    ) -> dict[str, Collection]:
        """Default Tier-1 run loop: iterate primary input, apply
        process_item to each, auto-flush each result, pack into
        output Collection. Override only for Tier 2/3 cross-item
        patterns."""
```

### `block-abc.IOBlock` — abstract data ingress/egress
Status: b
Source: `src/scieasy/blocks/io/io_block.py:L40-L192`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.3`
Supplementary-doc-source: ADR-028, ADR-028 Addendum 1, ADR-031 D4
Issue: #TBD-ioblock-load-output-dir

```python
class IOBlock(Block):
    """Abstract base for data ingress (load) and egress (save).

    Sub-label b-code-wins: ADR-031 D4 deliberately added the
    output_dir parameter to load() so loaders can persist directly to
    a configured storage location. ARCH §5.3 must update.

    Concrete IOBlock subclasses set direction = "input" or "output"
    and implement the matching abstract method. ADR-028 §D8 deferred
    enhancement: supported_extensions ClassVar + _detect_format
    helper (see separate entries below — both c-impl).
    """
    direction: ClassVar[str] = "input"        # "input" | "output"
    subcategory: ClassVar[str] = "io"

    @abstractmethod
    def load(
        self,
        config: BlockConfig,
        output_dir: str = "",
    ) -> DataObject | Collection:
        """Input-only blocks override this.

        Read data from a configured source (path / URL / DB) and
        return either a single DataObject or a Collection. If
        output_dir is non-empty, the loader SHOULD persist via
        persist_array/persist_table and return reference-only
        objects (storage_ref set).

        ADR-031 D4 safety net: any returned DataObject without
        storage_ref is auto-flushed by IOBlock.run() before output
        Collection construction.
        """

    @abstractmethod
    def save(
        self,
        obj: DataObject | Collection,
        config: BlockConfig,
    ) -> None:
        """Output-only blocks override this.

        Persist the input data to the configured destination
        (path / URL / DB). May materialize obj via to_memory() if
        needed.
        """

    def run(
        self,
        inputs: dict[str, Collection],
        config: BlockConfig,
    ) -> dict[str, Collection]:
        """Default run(): dispatch to load() (direction=input) or
        save() (direction=output) based on the direction ClassVar."""
```

### `block-abc.IOBlock.supported_extensions` — file-extension ClassVar (ADR-028 §D8)
Status: c
Source: `[CODE: not implemented — 0%]`
Primary-doc-source: ADR-028 §D8
Issue: #1074

```python
# c-impl — ADR-028 §D8 binding decision; no implementation in any IOBlock
# subclass today. Per ADR-028 §D8, EVERY IOBlock subclass MUST declare
# this ClassVar mapping file extensions to format identifiers used by
# the loader/saver dispatch and BlockRegistry.find_loader/find_saver
# (separate c-impl entries).
#
# Expected canonical shape:
supported_extensions: ClassVar[dict[str, str]] = {}
"""Map file extension (with leading dot, lowercase) to format identifier.

Example (LoadImage):
    supported_extensions = {".tif": "tiff", ".tiff": "tiff", ".png": "png"}

Example (LoadData):
    supported_extensions = {".csv": "csv", ".parquet": "parquet"}

The format identifier is a free-form string used by the block's
_load_<format> / _save_<format> dispatch methods.
"""
```

### `block-abc.IOBlock._detect_format` — extension dispatch helper (ADR-028 §D8)
Status: c
Source: `[CODE: not implemented — 0%]`
Primary-doc-source: ADR-028 §D8
Issue: #1073

```python
# c-impl — companion to supported_extensions
def _detect_format(self, file_path: str | Path) -> str | None:
    """Look up the format identifier for a file's extension.

    Returns supported_extensions[ext.lower()] if found, else None.
    The block's load()/save() dispatches to _load_<format>() /
    _save_<format>() based on this result.

    Args:
        file_path: Path to inspect (the extension is what matters).

    Returns:
        The format identifier string, or None if the extension is
        not in supported_extensions.
    """
```

### `block-abc.CodeBlock` — user-script execution block
Status: a
Source: `src/scieasy/blocks/code/code_block.py:L19-L194`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.3`
Supplementary-doc-source: ADR-005, ADR-017, ADR-020 Addendum 4

```python
class CodeBlock(Block):
    """Block for executing user-provided scripts.

    Two modes: inline (script in config) and script (path on disk).
    Three languages: python, r, julia (each via a CodeRunner
    Protocol implementation).

    Per ADR-020 Add 4: inputs are auto-unpacked from Collection to
    native objects (numpy array for length-1, LazyList for length>1).
    Outputs are auto-repacked into Collections.
    """
    language: ClassVar[str] = "python"        # runtime config "language" overrides
    mode: ClassVar[str] = "inline"            # "script" also supported

    # Variadic by default — port editor visible in GUI:
    variadic_inputs: ClassVar[bool] = True
    variadic_outputs: ClassVar[bool] = True

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "language": {"type": "string", "enum": ["python", "r", "julia"]},
            "mode": {"type": "string", "enum": ["inline", "script"]},
            "code": {"type": "string"},                # inline mode
            "script_path": {"type": "string"},         # script mode
            "entry_function": {"type": "string", "default": "run"},
            # input_ports / output_ports via ADR-030 MRO merge
        },
    }

    def run(
        self,
        inputs: dict[str, Collection],
        config: BlockConfig,
    ) -> dict[str, Collection]:
        """Subprocess-isolated dispatch to the appropriate
        CodeRunner Protocol implementation (PythonRunner / RRunner /
        JuliaRunner). All ADR-017 subprocess + ADR-020 Add 4
        auto-unpack/repack guarantees apply."""
```

### `block-abc.AppBlock` — external GUI application bridge
Status: a
Source: `src/scieasy/blocks/app/app_block.py:L58-L407`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.3`
Supplementary-doc-source: ADR-006, ADR-017, ADR-019, ADR-020 Add 5

```python
class AppBlock(Block):
    """Block delegating execution to an external GUI application
    (ElMAVEN, Fiji, napari, MestReNova, ...) via a file-exchange
    protocol.

    Lifecycle: PREPARE (write inputs to exchange dir) → LAUNCH
    (start app via app_command) → PAUSE (engine waits) → WATCH
    (filesystem watchdog for outputs matching output_patterns) →
    DETECT → RESUME → COLLECT (read outputs, wrap as DataObjects).

    macOS .app bundles auto-rewrite: app_command ending in ".app"
    becomes `open -W -n -a <App.app> --args ...` (issue #677).
    """
    app_command: ClassVar[str] = ""    # template; subclasses set
    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.EXTERNAL
    output_patterns: ClassVar[list[str]] = ["*"]    # glob patterns for output detection
    terminate_grace_sec: ClassVar[float] = 10.0     # longer than default — GUI cleanup takes time

    variadic_inputs: ClassVar[bool] = True
    variadic_outputs: ClassVar[bool] = True

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "required": ["app_command"],
        "properties": {
            "app_command": {"type": "string"},
            "output_dir": {"type": "string"},
            "output_patterns": {"type": "array", "items": {"type": "string"}},
            # input_ports / output_ports via ADR-030 MRO merge
        },
    }

    def run(self, inputs, config) -> dict[str, Collection]:
        """Orchestrates PREPARE/LAUNCH/WATCH/COLLECT via the
        ExternalAppBridge Protocol (default impl: FileExchangeBridge).
        On external-app exit without output, transitions to CANCELLED
        and reports via final_state in stdout envelope (#681)."""
```

### `block-abc.AppBlock.bridge.prepare` — input materialization (ADR-028 §D8)
Status: c
Source: `src/scieasy/blocks/app/bridge.py:L1-L1`
Primary-doc-source: ADR-028 §D8
Issue: #1080

```python
# c-impl — current code path uses a dead JSON-dump fallback when
# core.materialisation module is unavailable. Per ADR-028 §D8 +
# Codex cross-cascade analysis (M01 zone preference), AppBlock
# input prep MUST go through core.materialisation.materialise_to_file
# (see collection-transport §5 entry). Until that module ships,
# AppBlock can only round-trip a narrow set of formats.
def prepare(
    self,
    inputs: dict[str, Any],
    exchange_dir: Path,
) -> None:
    """Materialize input DataObjects to files in exchange_dir.

    Each input is dispatched via core.materialisation.materialise_to_file
    based on its declared format. The destination filename follows
    the convention <port_name>.<extension> where extension comes from
    the receiving IOBlock's supported_extensions (when known) OR
    falls back to the format identifier from FormatRegistry.

    Raises:
        NotImplementedError: until core.materialisation lands (#1078).
        ValueError: if a DataObject's type has no registered
            materialisation handler.
    """
```

### `block-abc.AppBlock._bin_outputs_by_extension` — output binning (ADR-028 §D8)
Status: c
Source: `src/scieasy/blocks/app/app_block.py:L1-L1`
Primary-doc-source: ADR-028 §D8
Issue: #1079

```python
# c-impl — current code path downgrades unknown-extension output
# files to Artifact DataObject. Per ADR-028 §D8 cluster, AppBlock
# output should use BlockRegistry.find_loader(extension) to dispatch
# to the appropriate plugin loader, producing typed DataObjects.
def _bin_outputs_by_extension(
    self,
    output_files: list[Path],
) -> dict[str, DataObject]:
    """Map each detected output file to a typed DataObject.

    For each file:
      1. Get extension (lowercase).
      2. loader_cls = BlockRegistry.find_loader(ext)
         (NEW method per #1077 — c-impl).
      3. If loader_cls is None, wrap as Artifact (current downgrade
         path) AND emit a warning.
      4. Else use loader_cls()._load_<format>(file) to produce typed
         DataObject.

    Returns dict keyed by output port name (matched via
    output_patterns).
    """
```

### `block-abc.AIBlock` — PTY agent workflow block (ADR-035)
Status: b
Source: `src/scieasy/blocks/ai/ai_block.py:L112-L617`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.3, §7.6`
Supplementary-doc-source: ADR-035 (ADR-013 superseded)
Issue: #TBD-aiblock-arch-update-for-adr-035

```python
class AIBlock(Block):
    """Workflow node that spawns a claude/codex agent in a PTY tab.

    Sub-label b-code-wins: ARCH §5.3 + §7.6 have pre-ADR-035 pseudocode
    (model: str + prompt_template: str interface). Code is the post-
    ADR-035 PTY agent spawner. ARCH must update substantially.

    Lifecycle: PREPARE (write manifest to RunDir per ADR-035 §3.5) →
    LAUNCH (spawn_claude / spawn_codex via terminal.py) → PAUSE
    (engine waits for completion signal) → WATCH (CompletionWatcher
    polls 3 signal sources in priority order: MCP finish_ai_block
    > FileWatcher on declared output paths > mark_done.json) →
    COMPLETE (collect declared outputs from RunDir/output_paths).
    """
    type_name: ClassVar[str] = "ai.agent"
    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.EXTERNAL
    variadic_inputs: ClassVar[bool] = True
    variadic_outputs: ClassVar[bool] = True
    allowed_input_types: ClassVar[list[type]] = [DataObject]    # any DataObject
    allowed_output_types: ClassVar[list[type]] = [DataObject]
    terminate_grace_sec: ClassVar[float] = 10.0

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "required": ["user_prompt"],
        "properties": {
            "user_prompt": {"type": "string"},
            "provider": {"type": "string", "enum": ["claude-code", "codex"]},
            "permission_mode": {"type": "string", "enum": ["safe", "bypass"]},
            "timeout_sec": {"type": "integer", "default": 1800},
            "auto_complete": {"type": "boolean", "default": False},    # #882
            # input_ports / output_ports (each with expected_path) via ADR-030
        },
    }

    def run(self, inputs, config) -> dict[str, Collection]:
        """Orchestrate the PTY agent lifecycle per ADR-035 §3.5."""

    def validate_config(self, config: BlockConfig) -> None:
        """Pre-flight config validation. Raises ValueError on
        missing user_prompt or unsupported provider."""
```

### `block-abc.AIBlock.auto_complete` — auto-completion config field
Status: d
Source: `src/scieasy/blocks/ai/ai_block.py:L1-L1`
Primary-doc-source: `[ARCHITECTURE: not documented]`
Issue: #882

```python
# d-document — Codex I2 finding. Documented here:
auto_complete: bool = False
"""When True, the AIBlock attempts to auto-finalize without waiting
for explicit finish_ai_block MCP call OR mark_done.json signal.
Completion is determined by FileWatcher seeing all declared
output_paths populated AND stable for poll_interval × N cycles.

When False (default), the agent MUST explicitly signal completion
via finish_ai_block (preferred) or mark_done.json (fallback).
Timeout-based completion (timeout_sec) still applies in both modes.

Use case for True: non-interactive automation (CI-style AI runs)
where the agent is purely producing files; no human review.
"""
```

### `block-abc.SubWorkflowBlock` — encapsulates a workflow as a composable block
Status: b
Source: `src/scieasy/blocks/subworkflow/subworkflow_block.py:L20-L155`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.3`
Issue: #TBD-subworkflow-classvar-vs-config

```python
class SubWorkflowBlock(Block):
    """Meta-block that encapsulates an entire workflow as a single
    composable node.

    Sub-label b-code-wins: ARCH §5.3 pseudocode reads workflow_ref
    from config + cites a nonexistent WorkflowLoader. Code uses
    ClassVars + a _scheduler_factory injection pattern. The scheduler
    integration is deferred (#890 c-defer entry below).
    """
    workflow_ref: ClassVar[str] = ""                  # OR config["workflow_path"]
    input_mapping: ClassVar[dict[str, str]] = {}      # {parent_port: child_port}
    output_mapping: ClassVar[dict[str, str]] = {}     # {child_port: parent_port}
    _scheduler_factory: ClassVar[Any] = None          # injected by engine layer (deferred)
    _cleanup_callback: ClassVar[Any] = None           # injected for cross-run cleanup

    def run(self, inputs, config) -> dict[str, Collection]:
        """Load child workflow → inject parent inputs into designated
        child IOBlocks → execute child via injected _scheduler_factory
        → extract designated child outputs as parent outputs.

        Currently uses _sequential_execute() fallback per #890 since
        _scheduler_factory injection is deferred."""
```

### `block-abc.SubWorkflowBlock._scheduler_factory` — scheduler injection contract
Status: c
Source: `src/scieasy/blocks/subworkflow/subworkflow_block.py:L?`
Primary-doc-source: `[ARCHITECTURE: not documented]`
Issue: #890

```python
# c-defer — scheduler integration deferred to ADR-017/022 Phase 5.2b
# Expected canonical shape when implemented:
_scheduler_factory: ClassVar[Callable[[WorkflowDefinition], DAGScheduler] | None] = None
"""Engine-injected factory that produces a child DAGScheduler.

Set by the engine layer at SubWorkflowBlock instantiation time.
SubWorkflowBlock.run() calls _scheduler_factory(child_workflow) to
get a properly-configured scheduler with the same EventBus,
ResourceManager, and ProcessRegistry as the parent.

Until implemented (per #890), SubWorkflowBlock falls back to
_sequential_execute() which runs the child workflow synchronously
without parallelism or event propagation to the parent.
"""
```

### `block-abc.BlockResult` — single-execution outcome dataclass
Status: a
Source: `src/scieasy/blocks/base/result.py:L10-L16`
Primary-doc-source: `docs/architecture/PROJECT_TREE.md`
Supplementary-doc-source: ADR-020

```python
@dataclass
class BlockResult:
    """Outcome of a single block execution. BatchResult was removed
    in ADR-020 — there's only this single-execution shape now."""
    outputs: dict[str, Any]            # port name → Collection (or raw value pre-pack)
    duration_ms: int = 0
    error: Exception | None = None     # None on DONE; the exception on ERROR
```

### `block-abc.CodeRunner` — Protocol for language-specific code execution
Status: d
Source: `src/scieasy/blocks/code/runners/base.py:L10-L35`
Primary-doc-source: `[ARCHITECTURE: §12 names entry-point group; Protocol contract not enumerated]`
Issue: #TBD-coderunner-protocol-document

```python
@runtime_checkable
class CodeRunner(Protocol):
    """Protocol every language runner must satisfy.

    Sub-label d-document: ARCH §12 mentions the `scieasy.runners`
    entry-point group but does NOT enumerate the Protocol. Plugin
    authors need this contract to register custom runners. SSOT
    establishes the contract here.

    Implementations: PythonRunner (uses exec()/importlib in subprocess),
    RRunner (subprocess Rscript + JSON IPC), JuliaRunner (subprocess
    julia + JSON IPC). All ADR-017 subprocess-isolated.
    """

    def execute_inline(
        self,
        script: str,
        namespace: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute inline script string with namespace injected as
        variables.

        Args:
            script: source code string in the runner's language.
            namespace: dict whose keys become variables in the
                script's execution scope. For CodeBlock inline mode,
                this is the auto-unpacked inputs dict.

        Returns:
            dict of variables in scope after execution. CodeBlock
            extracts those matching output port names.

        Raises:
            CodeExecutionError: on syntax error / runtime exception
                in the script. Wraps the underlying language-specific
                exception with line + column when available.
        """

    def execute_script(
        self,
        script_path: str | Path,
        entry_function: str,
        inputs: dict[str, Any],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a file-based script by calling its entry function.

        The convention: user's script defines a function
        `<entry_function>(inputs: dict, config: dict) -> dict` (per
        ARCH §5.3 CodeBlock script-mode contract).

        Args:
            script_path: path to .py/.R/.jl file.
            entry_function: name of the function to call (default "run").
            inputs: passed as first positional arg.
            config: passed as second positional arg.

        Returns:
            The dict returned by the entry function (output port names
            as keys).
        """
```

### `block-abc.PythonRunner` / `RRunner` / `JuliaRunner` — concrete CodeRunner implementations
Status: d
Source: `src/scieasy/blocks/code/runners/{python_runner,r_runner,julia_runner}.py`
Primary-doc-source: `[ARCHITECTURE: §5.3 mentions Rscript / julia subprocess; classes not enumerated]`
Issue: #TBD-runner-implementations-document

```python
class PythonRunner:
    """CodeRunner implementation for Python.

    execute_inline: calls exec(script, namespace) inside the worker
    subprocess (not the engine).
    execute_script: imports script_path as a module via importlib,
    locates entry_function, calls it.

    All subprocess-isolated per ADR-017.
    """
    def execute_inline(self, script: str, namespace: dict[str, Any]) -> dict[str, Any]: ...
    def execute_script(self, script_path, entry_function, inputs, config) -> dict[str, Any]: ...


class RRunner:
    """CodeRunner implementation for R.

    Both methods spawn `Rscript` subprocess. inputs + config are
    JSON-serialised on stdin; the script reads them via
    jsonlite::fromJSON. Outputs are read from stdout as JSON.

    No in-process rpy2 bridge — subprocess only per ADR-017.
    """
    def execute_inline(self, script: str, namespace: dict[str, Any]) -> dict[str, Any]: ...
    def execute_script(self, script_path, entry_function, inputs, config) -> dict[str, Any]: ...


class JuliaRunner:
    """CodeRunner implementation for Julia.

    Spawns `julia` subprocess. inputs + config JSON-serialised on
    stdin via JSON.jl; outputs read from stdout. No in-process
    juliacall bridge per ADR-017.
    """
    def execute_inline(self, script: str, namespace: dict[str, Any]) -> dict[str, Any]: ...
    def execute_script(self, script_path, entry_function, inputs, config) -> dict[str, Any]: ...
```

### `block-abc.RunnerRegistry` — language→CodeRunner class mapping (private)
Status: d
Source: `src/scieasy/blocks/code/runner_registry.py:L6-L37`
Primary-doc-source: `[CODE: internal dispatch class]`
Issue: #TBD-runner-registry-private-marker

```python
# d-private — internal dispatch class used only by CodeBlock.run() to look
# up the right CodeRunner implementation for a given language. Not part of
# the public extension surface (plugin authors register via
# `scieasy.runners` entry-point group, NOT by mutating this registry).
#
# Recommend rename to _RunnerRegistry to signal private status.

class RunnerRegistry:
    """Internal dispatch: language string → CodeRunner class."""

    def __init__(self) -> None:
        self._runners: dict[str, type] = {}

    def register(self, language: str, runner_class: type) -> None:
        """Register a CodeRunner class under a language identifier.

        Called by register_defaults() at module import time for built-in
        runners, AND by BlockRegistry._scan_entrypoint when scanning
        the `scieasy.runners` entry-point group.
        """

    def get(self, language: str) -> type:
        """Return the registered CodeRunner class for a language.

        Raises:
            KeyError: if no runner registered for the language.
        """

    def all_runners(self) -> dict[str, type]:
        """Return a copy of the language → runner_class map."""

    def register_defaults(self) -> None:
        """Register built-in PythonRunner/RRunner/JuliaRunner.
        Idempotent — safe to call multiple times."""
```

### `block-abc.ExternalAppBridge` — Protocol for bridging external GUI applications
Status: d
Source: `src/scieasy/blocks/app/bridge.py:L13-L19`
Primary-doc-source: `[ARCHITECTURE: §5.3 names the protocol in lifecycle prose; methods not enumerated]`
Issue: #TBD-externalappbridge-document

```python
@runtime_checkable
class ExternalAppBridge(Protocol):
    """Protocol every AppBlock bridge implementation must satisfy.

    Sub-label d-document: load-bearing for plugin AppBlock authors who
    need a custom bridge (e.g. embedded apps, network-attached apps).
    ARCH §5.3 narrates the PAUSE/WATCH lifecycle but doesn't enumerate
    the Protocol surface.

    Default implementation: FileExchangeBridge (separate entry below).
    """

    def prepare(
        self,
        inputs: dict[str, Any],
        exchange_dir: Path,
    ) -> None:
        """PREPARE step: serialize inputs to files in exchange_dir.

        Each input value is materialised to a file using the
        appropriate format (driven by the receiving IOBlock's
        supported_extensions per ADR-028 §D8 + core.materialisation
        per #1078).

        The exchange_dir is unique per AppBlock execution (typically
        tempfile.mkdtemp() under <project>/data/exchange/<run-id>/).
        """

    def launch(
        self,
        command: str,
        exchange_dir: Path,
    ) -> Any:
        """LAUNCH step: start the external process.

        Args:
            command: template string with {exchange_dir} placeholder
                resolved.
            exchange_dir: same dir as prepare().

        Returns:
            An opaque process handle (typically subprocess.Popen or a
            wrapping object). The handle is later passed to watch()
            for liveness checking.
        """

    def watch(
        self,
        exchange_dir: Path,
        patterns: list[str],
    ) -> list[Path]:
        """WATCH step: poll exchange_dir for files matching patterns.

        Returns the list of detected file paths once the user has
        produced output AND the files are stable (size + mtime
        unchanged for stability_period). Uses watchdog under the
        hood.

        Polling stops on (a) all patterns matched + stable, OR
        (b) process exit detected via ProcessHandle, OR
        (c) timeout.
        """

    def collect(
        self,
        output_files: list[Path],
    ) -> dict[str, Any]:
        """COLLECT step: read output files into Python objects.

        Each file is loaded via BlockRegistry.find_loader (NEW per
        #1077) to produce a typed DataObject. The dict is keyed by
        the output port name matched via output_patterns.
        """
```

### `block-abc.FileExchangeBridge` — default concrete ExternalAppBridge
Status: d
Source: `src/scieasy/blocks/app/bridge.py:L22-L157`
Primary-doc-source: `[CODE: internal; implementation detail of AppBlock]`
Issue: #TBD-fileexchangebridge-private-marker

```python
# d-private — default ExternalAppBridge implementation; not a public
# extension point (block authors implement the Protocol, not this class).
# Recommend rename to _FileExchangeBridge.

class FileExchangeBridge:
    """Default ExternalAppBridge implementation using filesystem
    polling.

    Used by AppBlock when no custom bridge is configured.
    Implements all 4 Protocol methods via FileWatcher (separate entry)
    + subprocess.Popen for launch.

    Configuration:
      - poll_interval_sec: float = 0.25
      - stability_period: float = 2.0   # file size+mtime stable
      - exchange_dir lifecycle: created in prepare(), preserved
        through collect(), cleaned in AppBlock.teardown
    """
```

### `block-abc.FileWatcher` — polling-based output detection for AppBlock
Status: d
Source: `src/scieasy/blocks/app/watcher.py:L27-L159`
Primary-doc-source: `[ARCHITECTURE: §5.3 mentions "polling via watchdog"; class not named]`
Issue: #TBD-filewatcher-private-marker

```python
# d-private — internal to AppBlock (not used by block authors directly).
# Recommend rename to _FileWatcher.

class FileWatcher:
    """Polling-based file detection with stability checks.

    Used by FileExchangeBridge.watch() to detect when external app
    outputs are ready. Wraps watchdog.observers.Observer.

    Behavior:
      - Subscribes to filesystem events under exchange_dir.
      - Filters by patterns (glob).
      - Tracks file size + mtime; declares a file "stable" when
        unchanged for stability_period seconds.
      - Returns list of stable matching paths.
      - Cancellable via cancel().
      - Detects external-app exit (via injected ProcessHandle); if
        exit detected before any output, raises
        ProcessExitedWithoutOutputError.
    """
    def __init__(
        self,
        watch_dir: Path,
        patterns: list[str],
        process_handle: ProcessHandle,
        poll_interval_sec: float = 0.25,
        stability_period: float = 2.0,
        done_marker: str | None = None,
    ) -> None: ...

    def wait(self, timeout_sec: float | None = None) -> list[Path]:
        """Block until outputs stable OR process exits OR cancelled
        OR timeout."""

    def cancel(self) -> None:
        """Stop watching (called on AppBlock cancellation)."""
```

### `block-abc.ProcessExitedWithoutOutputError` — AppBlock-internal exception
Status: d
Source: `src/scieasy/blocks/app/watcher.py:L21-L24`
Primary-doc-source: `[CODE: caught internally by AppBlock; never propagates to caller]`
Issue: #TBD-process-exited-error-private-marker

```python
# d-private — caught only by AppBlock.run(); the user-visible result
# is the block transitioning to CANCELLED via final_state per #681.
# Recommend rename to _ProcessExitedWithoutOutputError.

class ProcessExitedWithoutOutputError(Exception):
    """Raised by FileWatcher when the external GUI process exits
    before producing any output matching the watch patterns.

    AppBlock.run() catches this and calls self.transition(CANCELLED)
    + returns {}, which the worker serializes as final_state in the
    stdout envelope per #681. The scheduler then surfaces CANCELLED
    to the user (not ERROR — the user intentionally closed the app)."""
```

### `block-abc.LLMProvider` / `AnthropicProvider` / `OpenAIProvider` — pre-ADR-035 legacy
Status: d
Source: `src/scieasy/blocks/ai/providers.py:L44-L233`
Primary-doc-source: `[CODE: legacy from pre-ADR-035 design]`
Issue: #TBD-llmprovider-legacy-removal

```python
# d-remove — leftover from pre-ADR-035 AIBlock design (single-shot LLM
# generation). Post-ADR-035, AIBlock delegates to PTY agents via
# terminal.spawn_claude/spawn_codex; these Protocol + implementations
# are no longer called by the current AIBlock.
#
# Action: verify no callers remain (grep src/ tests/ packages/), then
# delete. Documented here so removal PR has a clear reference.

@runtime_checkable
class LLMProvider(Protocol):
    """Legacy single-call LLM provider Protocol (pre-ADR-035).

    Superseded by ADR-035 PTY agent architecture; AIBlock no longer
    invokes LLMProvider.generate(). Kept in code for potential
    future single-call AIBlock variant but currently unused.
    """

    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        config: Any = None,
    ) -> str:
        """Send prompt + system to the LLM, return text response."""


class AnthropicProvider:
    """Legacy Anthropic API wrapper. Calls anthropic.Anthropic().
    messages.create() with model from config."""

class OpenAIProvider:
    """Legacy OpenAI API wrapper. Calls openai.OpenAI().chat.
    completions.create() with model from config."""
```

### `block-abc.RunDir` — per-AI-Block-execution coordination directory
Status: d
Source: `src/scieasy/blocks/ai/run_dir.py:L92-L338`
Primary-doc-source: `[ARCHITECTURE: §7.6 abstract only; file-layout protocol not enumerated]`
Supplementary-doc-source: ADR-035 §3.5
Issue: #TBD-aiblock-run-dir-protocol-document

```python
class RunDir:
    """Per-AI-Block-execution coordination directory under
    <project>/.scieasy/ai-block-runs/<block_execution_id>/.

    Sub-label d-document: ADR-035 §3.5 specifies the protocol but
    ARCH §7.6 does NOT enumerate the file layout. SSOT establishes
    the canonical layout.

    Layout:
        <project>/.scieasy/ai-block-runs/<block_execution_id>/
        ├── manifest.json           # block metadata + I/O contract
        ├── signals/
        │   ├── finish_ai_block.json    # MCP-driven completion (preferred)
        │   └── mark_done.json          # user-driven fallback completion
        ├── transcript.jsonl        # copied agent transcript
        ├── inputs/                 # input-port files (one per port)
        │   ├── <port_name_1>       # may be file OR subdir for collections
        │   └── ...
        └── outputs/                # output-port files (agent writes here)
            ├── <port_name_1>
            └── ...
    """

    def __init__(
        self,
        project_dir: Path,
        block_execution_id: str,
    ) -> None:
        """Compute run_dir path; does NOT create on disk (call create())."""

    def create(self) -> None:
        """Create the run_dir + signals/ + inputs/ + outputs/ subdirs.
        Idempotent."""

    def write_manifest(
        self,
        block_name: str,
        block_type: str,
        user_prompt: str,
        inputs: dict[str, list[Any]],
        outputs: list[OutputPort],
        deadline_iso: str,
        output_paths: dict[str, str] | None = None,
    ) -> Path:
        """Write manifest.json with block metadata + I/O contract.

        Manifest shape:
            {
                "block_name": str,
                "block_type": str,
                "block_execution_id": str,
                "user_prompt": str,
                "inputs": {<port_name>: [{"type": str, "path": str}, ...]},
                "outputs": [{"name": str, "type": str, "expected_path": str}, ...],
                "deadline_iso": str (ISO 8601),
                "output_paths": {<port_name>: str} | None
            }

        The manifest is the AI agent's primary interface contract.
        Returns the manifest.json path.
        """

    def mcp_signal_path(self) -> Path:
        """Return signals/finish_ai_block.json path (written by
        finish_ai_block MCP tool when agent self-completes)."""

    def mark_done_signal_path(self) -> Path:
        """Return signals/mark_done.json path (written by user via
        GUI "Done" button — fallback completion path)."""

    def copy_transcript(self, source: Path) -> Path:
        """Copy the agent's stream-json transcript into run_dir/
        transcript.jsonl. Called by AIBlock.run() after completion
        for lineage preservation. Returns destination path."""
```

### `block-abc.CompletionWatcher` — multi-signal AIBlock completion detector
Status: d
Source: `src/scieasy/blocks/ai/completion.py:L72-L243`
Primary-doc-source: `[ARCHITECTURE: §7.6 lifecycle only; class-level interface not enumerated]`
Supplementary-doc-source: ADR-035 §3.5
Issue: #TBD-completion-watcher-document

```python
class CompletionWatcher:
    """Watches 3 completion signals in priority order for AIBlock.

    Sub-label d-document: ADR-035 §3.5 describes 3 completion paths
    but no class-level interface. SSOT establishes the priority order:
      1. MCP finish_ai_block (highest priority — agent self-completes
         via the MCP tool; writes signals/finish_ai_block.json with
         output_refs).
      2. FileWatcher on declared output paths (auto_complete=True
         mode; outputs detected stable per stability_period).
      3. mark_done.json (lowest priority — user clicks "Done" in GUI;
         outputs are whatever currently exists at expected_paths).

    First signal to fire wins; the others are abandoned.
    """

    def __init__(
        self,
        run_dir: RunDir,
        output_specs: dict[str, dict[str, Any]],   # {port_name: {"type": ..., "expected_path": ...}}
        project_dir: Path,
        poll_interval: float = 0.25,
        stability_period: float = 2.0,
    ) -> None:
        """Initialize watcher; does NOT start polling (call wait())."""

    def wait(self, timeout_sec: float | None = None) -> CompletionEvent:
        """Block until one of the 3 signals fires OR timeout.

        Returns:
            CompletionEvent describing which signal fired and what
            outputs are available.

        Raises:
            WatcherCancelledError: if cancel() was called.
            TimeoutError: on timeout_sec elapsed without signal.
        """

    def cancel(self) -> None:
        """Stop watching (called on AIBlock cancellation)."""
```

### `block-abc.CompletionEvent` / `CompletionSource` / `WatcherCancelledError` — AIBlock completion internals
Status: d
Source: `src/scieasy/blocks/ai/completion.py:L33-L70`
Primary-doc-source: `[CODE: internal data carriers; not part of public extension surface]`
Issue: #TBD-completion-internals-private-marker

```python
# d-private — internal to AIBlock; block authors don't construct or
# inspect these directly. Recommend rename to _CompletionEvent etc.

class CompletionSource(Enum):
    """Which signal fired."""
    MCP_FINISH_AI_BLOCK = "mcp"
    FILE_WATCHER = "filewatcher"
    MARK_DONE = "mark_done"

@dataclass
class CompletionEvent:
    """What CompletionWatcher returns on completion."""
    source: CompletionSource
    output_refs: dict[str, Any] | None    # populated when source=MCP_FINISH_AI_BLOCK
    output_files: dict[str, Path] | None  # populated when source=FILE_WATCHER or MARK_DONE
    transcript_path: Path | None
    detected_at: datetime

class WatcherCancelledError(Exception):
    """Raised by CompletionWatcher.wait() when cancel() called."""
```

### `block-abc._PopenProcessAdapter` — Popen→ProcessHandle adapter for FileWatcher
Status: d
Source: `src/scieasy/blocks/app/app_block.py:L39-L56`
Primary-doc-source: `[CODE: ADR-019 compat shim]`
Issue: #TBD-popen-adapter-private-marker

```python
# d-private — ADR-019 compatibility shim that wraps a raw
# subprocess.Popen instance into the ProcessHandle Protocol for
# FileWatcher's process_handle parameter. Used because
# FileExchangeBridge.launch() returns a Popen (not yet wrapped in
# ProcessHandle by spawn_block_process). Recommend rename to
# _PopenProcessAdapter (already underscore-prefixed; this is
# documentation only).

class _PopenProcessAdapter:
    """Wraps subprocess.Popen into the ProcessHandle Protocol so
    FileWatcher can poll liveness via is_alive() / exit_info()."""
    def __init__(self, popen: subprocess.Popen) -> None: ...
    async def is_alive(self) -> bool: ...
    async def exit_info(self) -> ProcessExitInfo | None: ...
    # terminate() / kill() unsupported — these adapters are read-only
```

### `block-abc._sequential_execute` — SubWorkflowBlock fallback executor
Status: d
Source: `src/scieasy/blocks/subworkflow/subworkflow_block.py:L158-L187`
Primary-doc-source: `[CODE: TODO(#890) deferred]`
Issue: #890

```python
# d-private — stub awaiting real async DAG scheduling per #890.
# Underscore-prefixed already; this entry documents the stub for
# auditability.

def _sequential_execute(
    workflow: WorkflowDefinition,
    inputs: dict[str, Any],
    config: BlockConfig,
) -> dict[str, Any]:
    """Sequential fallback for SubWorkflowBlock until real async
    scheduling via _scheduler_factory ships.

    Walks the child workflow's blocks in topological order. Calls
    each block's run() synchronously. No subprocess isolation, no
    event propagation to parent, no resource gating. Useful for
    smoke-testing child workflows but unfit for production parallel
    work.
    """
```

---

## 2. port-system

**Module preamble** (from Codex M02 sub): Port type + constraint contract + two-phase validation (design-time + pre-execution) is stable. Per ADR-020, constraint callable receives `Collection` not single `DataObject`. Variadic port editor + dynamic port descriptor (ADR-028 Add 1 / ADR-029) integrate via `Block.get_effective_*_ports`.

### `port-system.Port` — connection endpoint base
Status: a
Source: `src/scieasy/blocks/base/ports.py:L12-L22`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.2`
Supplementary-doc-source: ADR-001, ADR-020, ADR-029

```python
@dataclass(kw_only=True)
class Port:
    """Base for InputPort and OutputPort. Keyword-only construction."""
    name: str                       # canonical port name (used in edges)
    accepted_types: list[type]      # MRO-based type acceptance (DataObject + subclasses)
    is_collection: bool = False     # informational flag (UI-level; see separate entry)
    description: str = ""           # tooltip
    required: bool = True           # if False, port may be unbound
```

### `port-system.Port.is_collection` — informational flag (UI-level)
Status: d
Source: `src/scieasy/blocks/base/ports.py:L17`
Primary-doc-source: `[ARCHITECTURE: §5.2 does not list as field]`
Issue: #TBD-port-is-collection-document

```python
# d-document — code has it; D1 doesn't enumerate as Port field.
# AIBlock declares ports with is_collection=True. Currently
# informational only (not enforced by validation). ARCH §5.2 must add.

is_collection: bool = False
"""UI-level hint that this port semantically expects a multi-item
Collection (vs single-item). The runtime always passes a Collection
regardless of this flag (per ADR-020 transport uniformity); but the
GUI uses this hint to render the port handle differently (double-ring
icon per ARCH §9.6) and to validate edge connections at design-time
(a Collection source can fan into a Collection target without
unpacking)."""
```

### `port-system.InputPort` — input connection endpoint
Status: b
Source: `src/scieasy/blocks/base/ports.py:L23-L29`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.2`
Supplementary-doc-source: ADR-020 (constraint semantics changed to Collection)
Issue: #TBD-inputport-constraint-annotation

```python
@dataclass(kw_only=True)
class InputPort(Port):
    """Input endpoint. Adds default value + runtime constraint.

    Sub-label b-code-wins: code annotation is Callable[[Any], bool]
    to accept the Collection receivee (per ADR-020); ARCH §5.2 still
    declares Callable[[DataObject], bool] (pre-ADR-020 form). ARCH
    must update.
    """
    default: Any | None = None
    constraint: Callable[[Any], bool] | None = None
    """Constraint callable. Receives the FULL Collection at runtime
    (per ADR-020); should iterate items if per-item validation is
    needed. Returns True on pass, False on fail. Exceptions are
    caught and reported as failures (with the exception text in
    constraint_description)."""

    constraint_description: str = ""
    """Human-readable text shown to user on constraint failure.
    Surfaced via WebSocket constraint-failure message (cancel_propagation
    pattern). Should describe what the constraint checks in domain
    terms (e.g., "All images must have axes (y, x, c)")."""
```

### `port-system.OutputPort` — output connection endpoint
Status: a
Source: `src/scieasy/blocks/base/ports.py:L31-L33`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.2`

```python
@dataclass(kw_only=True)
class OutputPort(Port):
    """Output endpoint. Structural alias for Port; no additional fields."""
    pass
```

### `port-system.constraint-callable-semantics` — receives Collection
Status: b
Source: `src/scieasy/blocks/base/ports.py:L76-L99`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.2`
Supplementary-doc-source: ADR-020
Issue: #TBD-port-constraint-callable-semantics-arch-update

```python
# b-code-wins — ARCH §5.2 example signatures show constraints receiving
# DataObject (pre-ADR-020 form). ADR-020 explicitly changed semantics
# to Collection. Code is current truth. ARCH must update to:
#
#   constraint: Callable[[Collection], bool]
#
# All constraint examples in ARCH §5.2 must be rewritten to iterate
# `col` instead of treating the arg as a single DataObject.
```

### `port-system.validate_port_constraint` — Collection constraint validator
Status: d
Source: `src/scieasy/blocks/base/ports.py:L76-L99`
Primary-doc-source: `[ARCHITECTURE: §5.2 prose only; function not named]`
Issue: #TBD-validate-port-constraint-document

```python
def validate_port_constraint(
    port: InputPort,
    value: Any,
) -> tuple[bool, str]:
    """Run an InputPort's constraint callable; return (pass, message).

    Sub-label d-document: public function backing the pre-execution
    validation phase. ARCH §5.2 narrates the behavior but doesn't
    enumerate this function.

    Args:
        port: the InputPort whose constraint to run.
        value: the value about to be passed to the block's run()
            method for this port (always a Collection per ADR-020).

    Returns:
        (True, "") if port.constraint is None OR returns True.
        (False, port.constraint_description) if returns False.
        (False, f"Constraint raised {exc!r}") if raises.

    Called by Block.validate() during the pre-execution validation
    phase (the two-phase validation contract — see ARCH §5.2).
    """
```

### `port-system.port_accepts_type` — structural type acceptance check
Status: d
Source: `src/scieasy/blocks/base/ports.py:L37-L70`
Primary-doc-source: `[ARCHITECTURE: §5.2 prose only]`
Issue: #TBD-port-helpers-document

```python
def port_accepts_type(
    port: Port,
    data_type: type | Any,
) -> bool:
    """Check whether a candidate type is in port's accepted_types
    (MRO-aware).

    Sub-label d-document: load-bearing for the design-time validation
    phase (frontend connection validation calls this via
    POST /api/blocks/validate-connection).

    Args:
        port: any Port (Input or Output).
        data_type: candidate type. May be a class OR an instance
            (whose type is checked).

    Returns:
        True if any accepted type is in data_type.__mro__.
    """
```

### `port-system.port_accepts_signature` — structural acceptance with TypeSignature
Status: d
Source: `src/scieasy/blocks/base/ports.py:L73-L110`
Primary-doc-source: `[ARCHITECTURE: §5.2 prose only]`
Issue: #TBD-port-helpers-document

```python
def port_accepts_signature(
    port: Port,
    signature: TypeSignature,
) -> bool:
    """Check whether a TypeSignature (from a DataObject's dtype_info)
    is compatible with port's accepted_types.

    Sub-label d-document: used by the runtime (worker subprocess
    reconstruction path) to verify reconstructed DataObject types
    match their declared port types.

    Compatibility rules:
      - signature.type_chain[0] (most-specific) must be in
        port.accepted_types (or a subclass per MRO).
      - For Array subtypes: if port.accepted_types include an Array
        subclass with required_axes, signature.required_axes must be
        a superset.
      - For CompositeData: if port.accepted_types include a
        CompositeData subclass with expected_slots, every required
        slot must appear in signature.slot_types with a compatible
        type.

    Returns True on all compatibility checks pass; False otherwise.
    """
```

### `port-system.validate_connection` — design-time edge validator
Status: d
Source: `src/scieasy/blocks/base/ports.py:L113-L171`
Primary-doc-source: `[ARCHITECTURE: §5.2 prose only]`
Issue: #TBD-port-helpers-document

```python
def validate_connection(
    source_port: OutputPort,
    target_port: InputPort,
) -> tuple[bool, str]:
    """Check whether an OutputPort can connect to an InputPort.

    Sub-label d-document: backs POST /api/blocks/validate-connection
    REST endpoint (BLK-003). Called by frontend ReactFlow on edge
    draw to give immediate visual feedback.

    Checks:
      1. For every type in target_port.accepted_types, at least one
         type in source_port.accepted_types is a subclass (via MRO).
      2. target_port.is_collection compatibility: if target is single
         and source is Collection, edge requires unpacking (warning,
         not error).
      3. (Future: dynamic_ports narrowing — currently uses static
         accepted_types.)

    Returns (True, "") on pass, (False, description) on fail.

    Note: this is the DESIGN-TIME structural check. Pre-execution
    validation (Block.validate) ALSO runs constraint callables.
    """
```

### `port-system.ports_from_config_dicts` — variadic port materialization helper
Status: d
Source: `src/scieasy/blocks/base/ports.py:L102-L140`
Primary-doc-source: `[ARCHITECTURE: ADR-029 D1 implied]`
Issue: #TBD-ports-from-config-dicts-document

```python
def ports_from_config_dicts(
    dicts: list[dict[str, Any]],
    direction: str,
) -> list[InputPort] | list[OutputPort]:
    """Materialize per-instance ports from config dicts (ADR-029 D1).

    Sub-label d-document: load-bearing for variadic blocks (CodeBlock,
    AppBlock, AIBlock, FijiBlock). Consumed by
    Block.get_effective_input_ports / get_effective_output_ports
    when self.variadic_inputs / variadic_outputs is True and
    self.config["input_ports"] / config["output_ports"] is set.

    Args:
        dicts: list of {"name": str, "types": [str]} dicts from
            self.config. Each dict produces one Port.
        direction: "input" or "output" — determines whether
            InputPort or OutputPort instances are returned.

    Type-name resolution:
        Each string in dicts[i]["types"] is resolved via
        TypeRegistry.resolve(name). Unknown type names fall back to
        DataObject (with a warning logged).

    Dedup rule (per A1 audit P1 correction): port names are
    deduplicated FIRST-WINS (the loop uses `continue` on duplicate,
    so earlier dict entries take precedence over later ones). NOT
    last-wins as some pre-cascade docs claimed.

    Returns:
        list of InputPort or OutputPort instances (depending on
        direction).
    """
```

### `port-system.ConstraintFn` — type alias for constraint callables
Status: d
Source: `src/scieasy/utils/constraints.py:L65`
Primary-doc-source: `[ARCHITECTURE: §5.2 helpers list]`
Issue: #TBD-constraintfn-document

```python
ConstraintFn = Callable[[Any], bool]
"""Type alias for constraint callables. Receives Collection at
runtime per ADR-020; the Any annotation is intentional looseness
for backward compat with pre-ADR-020 constraint factories that
expected single DataObject. New constraint factories should be
written to iterate the Collection."""
```

### `port-system.constraint-factory-functions` — has_axes / has_shape / etc.
Status: a
Source: `src/scieasy/utils/constraints.py:L68-L243`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.2` (mentions helpers)

```python
def has_axes(*required: str) -> ConstraintFn:
    """Return a constraint that requires every item in the Collection
    to have all the named axes (per Array.axes list).

    Example: `has_axes("y", "x")` requires all items to be at least
    2D images with spatial axes.
    """

def has_exact_axes(*axes: str) -> ConstraintFn:
    """Return a constraint that requires every item's axes to be
    EXACTLY the given set (no more, no fewer)."""

def has_shape(ndim: int) -> ConstraintFn:
    """Return a constraint requiring every item to be exactly ndim
    dimensions."""

def has_min_shape(ndim: int) -> ConstraintFn:
    """Return a constraint requiring every item to have at least ndim
    dimensions."""

def has_dtype(*dtypes: Any) -> ConstraintFn:
    """Return a constraint requiring every item's dtype to be one of
    the listed dtypes."""

def is_2d() -> ConstraintFn:
    """Alias for has_shape(2)."""

def is_3d() -> ConstraintFn:
    """Alias for has_shape(3)."""
```

---

## 3. data-types

**Module preamble** (from Codex M01): DataObject typed contract + 3-slot metadata stratification (framework / meta / user) is the root abstraction for all data flow. ADR-027 D2: core ships exactly 7 types (DataObject root + 6 primitives). Domain subtypes (Image, Spectrum, AnnData, etc.) live in plugins via `scieasy.types` entry-point — NOT in core. PROJECT_TREE.md entry-points table contradicts this (see cross-cutting C-class entry in Pass 2).

### `data-types.DataObject` — base class for all first-class data
Status: a
Source: `src/scieasy/core/types/dataobject.py:L1-L1`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.1`
Supplementary-doc-source: ADR-027 D5

```python
class DataObject:
    """Base for all data flowing between blocks.

    5-slot model (ADR-027 D5):
      - _framework: FrameworkMeta      (immutable framework-managed)
      - _meta: BaseModel               (typed Pydantic per subtype; base = empty BaseModel)
      - _user: dict[str, Any]          (free-form user annotations)
      - _storage_ref: StorageReference (pointer to persisted data; lightweight)
      - _transient_data: Any           (non-serialized; for in-memory bridging)

    Subclasses override Meta ClassVar to declare their typed metadata
    schema. Plugin types (Image, Spectrum, etc.) follow this pattern.
    """
    _framework: FrameworkMeta
    _meta: BaseModel
    _user: dict[str, Any]
    _storage_ref: StorageReference | None
    _transient_data: Any | None
    Meta: ClassVar = None    # hook for plugin typed models; subtypes override

    def to_memory(self) -> Any:
        """Materialize full data from storage. Emits a 2GB size warning
        for large data. For Text/Artifact, returns content/file_path."""

    def get_in_memory_data(self) -> Any:
        """Alias for to_memory(). Subclasses may override (Text returns
        content; Artifact returns file_path)."""

    def slice(self, *args) -> Any:
        """Backend-specific sub-selection (Zarr indexing, Arrow column
        filter, etc.). Returns the materialized slice."""

    def iter_chunks(self, chunk_size: int) -> Iterator:
        """Yield successive chunks from storage. Constant memory.
        Subclasses (Array) override with axis-aware chunking."""

    def with_meta(self, **changes) -> Self:
        """Immutable metadata update. Returns a new instance with the
        Meta model fields replaced per changes; framework, user,
        storage_ref are inherited (framework gets a new derived_from
        link)."""

    def save(self, path) -> None:
        """Save to a destination path via the appropriate storage
        backend (BackendRouter.dispatch(type(self)))."""
```

### `data-types.DataObject._transient_data` — bridge properties (and `_data` / `_arrow_table` shadow accessors)
Status: d
Source: `src/scieasy/core/types/dataobject.py:L1-L1`
Primary-doc-source: `[CODE: internal transitional bridges from pre-ADR-031]`
Issue: #661

```python
# d-remove — Complete ADR-031 migration; deprecated post-ADR-031.
# 32 doc sites across 14 files still reference the deprecated `_data`
# attribute pattern (#661). SSOT documents the deprecation explicitly:

@property
def _data(self) -> Any | None:
    """DEPRECATED post-ADR-031. Read-only forwarder to
    self._transient_data for backward compat. Will be removed in
    Phase 11. Use to_memory() or transient_data via property."""
    warnings.warn(DeprecationWarning(
        "DataObject._data is deprecated; use to_memory() or _transient_data"
    ))
    return self._transient_data

@property
def _arrow_table(self) -> Any | None:
    """DEPRECATED post-ADR-031. DataFrame-specific forwarder to
    _transient_data when type is arrow.Table. Will be removed in
    Phase 11."""
    return self._transient_data if isinstance(self, DataFrame) else None
```

### `data-types.FrameworkMeta` — framework-managed metadata
Status: b
Source: `src/scieasy/core/meta/framework.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.1`
Issue: #TBD-frameworkmeta-derived-from-type-fix

```python
class FrameworkMeta(BaseModel, frozen=True):
    """Framework-managed metadata slot (ADR-027 D5).

    Sub-label b-code-wins: code uses `str` for object_id + derived_from;
    D1 + ARCH show `UUID`. Code is current; ARCH must update both
    fields. Loose `str` makes serialization simpler (no UUID round-trip).
    """
    created_at: datetime
    object_id: str                 # ARCH said UUID; code uses str
    source: str | None             # origin description (loader name, manual creation, etc.)
    lineage_id: str | None         # block_execution_id from lineage.db.block_executions per ADR-038
    derived_from: str | None       # parent DataObject object_id; ARCH said UUID; code uses str

    def derive(self) -> "FrameworkMeta":
        """Return a fresh FrameworkMeta with new object_id +
        created_at=now, derived_from=self.object_id, lineage_id
        unchanged. Used by transformations to chain provenance."""

    def with_lineage_id(self, id: str) -> "FrameworkMeta":
        """Return self with lineage_id replaced. Used by the engine
        to stamp block_execution_id after dispatch."""
```

### `data-types.Array` — N-dimensional numeric data with named axes
Status: a
Source: `src/scieasy/core/types/array.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.1`
Supplementary-doc-source: ADR-027 D1

```python
class Array(DataObject):
    """N-dimensional numeric data with named axes (ADR-027 D1).

    Subclasses declare class-level axis constraints:
      - required_axes: axes every instance MUST have
      - allowed_axes: axes this class accepts (None = any)
      - canonical_order: preferred ordering for reorder ops

    Plugin subtypes (Image, FluorImage, HyperspectralImage,
    SRSImage, MSImage, ...) tighten these constraints per their
    domain semantics.
    """
    axes: list[str]                                 # instance-level
    shape: tuple[int, ...]
    dtype: np.dtype
    chunk_shape: tuple[int, ...] | None
    required_axes: ClassVar[frozenset[str]] = frozenset()
    allowed_axes: ClassVar[frozenset[str] | None] = None
    canonical_order: ClassVar[tuple[str, ...]] = ()

    def sel(self, **kwargs) -> "Array":
        """Partial read along named axes. Returns a new Array with
        storage_ref set (lazy until to_memory()).

        IMPORTANT: always returns plain `Array` (not type(self)) to
        avoid required_axes constraint violations on reduced slices.
        Sub-label note in C2 audit: this is intentional design;
        SSOT documents it.
        """

    def iter_over(self, axis: str) -> Iterator:
        """Yield slices along the named axis. Each slice has
        storage_ref set; materializes on access."""

    def __array__(self, dtype=None) -> np.ndarray:
        """NumPy protocol — calls to_memory()."""

# _validate_axes runs in __init__: instance's axes must be superset
# of required_axes, subset of allowed_axes (if set), no duplicates.
```

### `data-types.Series` — 1D indexed data
Status: a
Source: `src/scieasy/core/types/series.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.1`
Supplementary-doc-source: ADR-027 D2 (core ships 7 types only)

```python
class Series(DataObject):
    """1D indexed data (pandas.Series-like).

    Used for time series, single-column tables, ordered measurements.
    Backed by Zarr (single-column) or Parquet (when small).
    """
    index_name: str
    value_name: str
    length: int
```

### `data-types.DataFrame` — columnar tabular data
Status: a
Source: `src/scieasy/core/types/dataframe.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.1`
Supplementary-doc-source: ADR-027 D2

```python
class DataFrame(DataObject):
    """Columnar tabular data. Backed by Apache Arrow / Parquet.

    Schema is column name → Arrow type. Memory-mappable via Arrow.
    """
    columns: list[str]
    row_count: int
    schema: dict[str, Any]    # {column_name: arrow_type}
```

### `data-types.Text` — text / markdown / JSON content
Status: a
Source: `src/scieasy/core/types/text.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.1`
Supplementary-doc-source: ADR-027 D2

```python
class Text(DataObject):
    """Text content (markdown, JSON, plain text, code).

    Exempt from lazy loading: content is held in memory (inherently
    small — typically KB). storage_ref points at the persisted file
    after save(); to_memory() returns self.content directly.
    """
    content: str
    format: str          # "markdown" | "json" | "plain" | "yaml" | "python" | ...
    encoding: str = "utf-8"
```

### `data-types.Artifact` — opaque file DataObject
Status: a
Source: `src/scieasy/core/types/artifact.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.1`
Supplementary-doc-source: ADR-027 D2

```python
class Artifact(DataObject):
    """Opaque file (PDF, report, image, anything outside the typed
    primitives). Uses file_path as its transport mechanism — the
    file stays at its original path and is NOT copied into managed
    storage.

    Auto-flush exemption: _auto_flush skips Artifacts (the file
    already exists; no need to write it again).
    """
    file_path: Path
    mime_type: str
    description: str = ""
```

### `data-types.CompositeData` — heterogeneous slot container
Status: a
Source: `src/scieasy/core/types/composite.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.1`
Supplementary-doc-source: ADR-027 D2

```python
class CompositeData(DataObject):
    """Named collection of heterogeneous DataObject slots.

    Used for multi-modal containers like AnnData (X/obs/var/uns),
    SpatialData (images/points/shapes/table). Subclasses declare
    expected_slots ClassVar to enable port-level slot constraint
    checking.

    Storage: directory of slot backends + manifest.json mapping
    slot_name → storage_ref. Each slot may use a different backend.
    """
    _slots: dict[str, DataObject]
    expected_slots: ClassVar[dict[str, type]] = {}

    def get(self, slot_name: str) -> DataObject:
        """Retrieve a named slot.

        Raises:
            KeyError: if slot_name not in self._slots.
        """

    def set(self, slot_name: str, data: DataObject) -> None:
        """Set or replace a named slot."""

    def slot_types(self) -> dict[str, type]:
        """Return {slot_name: DataObject subclass} for port constraint
        checking."""

    @property
    def slot_names(self) -> list[str]:
        return list(self._slots.keys())
```

### `data-types.TypeSignature` — MRO-based type descriptor
Status: a
Source: `src/scieasy/core/types/registry.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.1`
Supplementary-doc-source: ADR-027 D1

```python
@dataclass
class TypeSignature:
    """Type descriptor for port compatibility checking.

    Encodes MRO chain (leaf-to-root) so plugin types resolve back to
    core types. For Array subtypes, also encodes required_axes. For
    CompositeData, encodes slot_types.
    """
    type_chain: list[str]                        # leaf-to-root, e.g. ["FluorImage", "Image", "Array", "DataObject"]
    required_axes: frozenset[str] | None = None  # for Array subtypes
    slot_types: dict[str, type] | None = None    # for CompositeData

    @classmethod
    def from_type(cls, t: type) -> "TypeSignature":
        """Build a TypeSignature by walking t.__mro__ until DataObject.
        Extracts required_axes from t.required_axes (Array subtypes)
        and expected_slots from t.expected_slots (CompositeData)."""
```

### `data-types.TypeRegistry` — DataObject subclass registry
Status: a
Source: `src/scieasy/core/types/registry.py:L69`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.1, §5.4`
Supplementary-doc-source: ADR-025, ADR-027 D11

```python
class TypeRegistry:
    """Registry of DataObject subclasses (core + plugin types).

    Cross-listed under block-registry — this entry covers the
    data-types facet; the registry facet is in §6.

    Worker subprocess calls scan_all() at startup (ADR-027 D11) so
    type_chain strings in StorageReference can be resolved back to
    classes for DataObject reconstruction.
    """

    def all_types(self) -> dict[str, type]:
        """Return mapping of canonical class name → class."""

    def has(self, name: str) -> bool:
        """Cross-listed entry: this method DOES NOT EXIST today (see
        block-registry §6 entry — c-impl). Callers must catch
        KeyError from resolve() instead."""

    def scan_builtins(self) -> None:
        """Register the 7 core types (DataObject + Array + Series +
        DataFrame + Text + Artifact + CompositeData). Idempotent."""

    def scan_all(self, include_monorepo: bool = False) -> None:
        """Scan `scieasy.types` entry-point group + scan_builtins().
        Idempotent."""

    def resolve(self, name_or_chain: str | list[str]) -> type | TypeSpec | None:
        """Overloaded:
          - resolve(str) -> TypeSpec (legacy single-name lookup)
          - resolve(list[str]) -> type | None (ADR-027 D11 for worker
            subprocess type-chain reconstruction; walks the chain
            leaf-to-root, returns the most-specific registered class)
        """
```

### `data-types.ChannelInfo` — acquisition-channel descriptor
Status: a
Source: `src/scieasy/core/meta/channel.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.1`

```python
@dataclass(frozen=True)
class ChannelInfo:
    """Per-channel descriptor for Array subtypes with 'c' axis.

    Used in FluorImage.Meta.channels[], HyperspectralImage.Meta, etc.
    """
    name: str                          # display name (e.g., "DAPI", "GFP")
    excitation_nm: float | None        # excitation wavelength
    emission_nm: float | None          # emission wavelength
    color: str | None                  # hex color for visualization
```

### `data-types.PhysicalQuantity` — value + unit helper
Status: a
Source: `src/scieasy/core/units.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.1`

```python
class PhysicalQuantity:
    """Value with unit, for typed metadata (pixel_size, etc.).

    Supports arithmetic + comparison with unit conversion.
    """
    def __init__(self, value: float, unit: str) -> None: ...
    def __add__(self, other: "PhysicalQuantity") -> "PhysicalQuantity": ...
    def __sub__(self, other: "PhysicalQuantity") -> "PhysicalQuantity": ...
    def __mul__(self, scalar: float) -> "PhysicalQuantity": ...
    def __truediv__(self, scalar: float) -> "PhysicalQuantity": ...
    def __lt__(self, other: "PhysicalQuantity") -> bool: ...
    def __eq__(self, other: object) -> bool: ...
    def to(self, target_unit: str) -> "PhysicalQuantity":
        """Convert to a compatible unit. Raises ValueError on
        incompatible units."""
```

### `data-types.TypeSpec` — type-registry descriptor
Status: d
Source: `src/scieasy/core/types/registry.py:L1-L1`
Primary-doc-source: `[CODE: internal — base_type is one MRO level only, not full chain]`
Issue: #TBD-typespec-document-or-private

```python
# d-document — used by TypeRegistry.resolve(str) legacy path and by
# entry-point loading. Public surface despite being internally-flavored.

@dataclass
class TypeSpec:
    """Registry-level descriptor for a DataObject subclass.

    Note from C3 audit: base_type is ONE MRO level only, not the
    full chain. The full chain comes from DataObject.dtype_info.
    type_chain at serialisation time.
    """
    name: str                       # canonical class name
    type_class: type                # the class itself
    base_type: type                 # ONE-level MRO parent (NOT full chain)
    module: str                     # source module
    package_name: str               # registering package
```

### `data-types.with_meta_changes` — free-function metadata helper
Status: d
Source: `src/scieasy/core/meta/_with_meta.py`
Primary-doc-source: `[CODE: exported in __all__ but not in ARCH §4.1]`
Issue: #TBD-with-meta-changes-document

```python
# d-document — exported in core/meta/__init__.__all__ (PUBLIC surface).
# Used by plugin types that need to manipulate Meta models without
# subclassing.

def with_meta_changes(
    obj: DataObject,
    **changes: Any,
) -> DataObject:
    """Free-function alternative to obj.with_meta(**changes).

    Useful in chains and functional pipelines where method-call form
    is awkward. Semantically identical to the method:
      - Returns a new instance.
      - framework slot gets a new derived_from link.
      - user slot is shallow-copied.
      - storage_ref preserved by reference.
    """
```

### `data-types._reconstruct_one` / `_serialise_one` — wire-format codec
Status: d
Source: `src/scieasy/core/types/serialization.py`
Primary-doc-source: `[CODE: cross-process wire-format contract; not in ARCH §4.1]`
Issue: #TBD-data-types-codec-document

```python
# d-document — these are CROSS-PROCESS protocol functions used by both
# the engine (serialise outputs) and the worker subprocess
# (reconstruct inputs). Even though underscore-prefixed, they ARE
# the wire-format contract. SSOT establishes the signature.

def _serialise_one(obj: DataObject) -> dict:
    """Serialise a DataObject to wire-format dict.

    Special-case noted by C2: raises ValueError if storage_ref is None
    EXCEPT for Artifact with file_path set. Artifacts use file_path
    as transport (the file is the persistence), so no storage_ref is
    needed.

    Returns:
        {
            "type_chain": [str, ...],          # leaf-to-root
            "framework": {...},                # FrameworkMeta fields
            "meta": {...},                     # subtype Meta fields
            "user": {...},                     # free-form
            "storage_ref": {...} | None,       # StorageReference fields
            "extras": {...}                    # subtype-specific (e.g., axes for Array)
        }

    Raises:
        ValueError: if storage_ref is None and obj is not Artifact
            with file_path set.
    """

def _reconstruct_one(wire: dict) -> DataObject:
    """Reconstruct a DataObject from a wire-format dict.

    Resolves type_chain via TypeRegistry.resolve(list[str]) → most-
    specific registered class. Instantiates with framework/meta/user/
    storage_ref slots from the wire dict. For CompositeData, calls
    _reconstruct_extra_kwargs() (lazy import to break circular dep).

    Raises:
        KeyError: if type_chain[0] is not registered.
    """
```

### `data-types._get_backend` / `_get_type_registry` — lazy module singletons
Status: d
Source: `src/scieasy/core/storage/__init__.py`, `src/scieasy/core/types/registry.py`
Primary-doc-source: `[CODE: internal lazy singletons]`
Issue: #TBD-lazy-singletons-private-marker

```python
# d-private — internal lazy-initializing module singletons used to
# break circular imports between storage backends and DataObject. Not
# part of the public extension surface.

def _get_backend(backend_name: str) -> StorageBackend:
    """Lazy lookup: return the StorageBackend instance for a name."""

def _get_type_registry() -> TypeRegistry:
    """Lazy singleton: return the module-level TypeRegistry. Calls
    scan_builtins() on first access."""
```

---

## 4. storage-backends

**Module preamble** (from Codex M01 sub): Reference-flow architecture with persistence backends + type→backend routing. Stable A-class principle; sub-issues are documentation/behavior hygiene. 4 concrete backends in core (Zarr, Arrow, Filesystem, Composite).

### `storage-backends.StorageReference` — pointer to persisted data
Status: b
Source: `src/scieasy/core/storage/base.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.2`
Issue: #TBD-storage-reference-immutability-doc-fix

```python
@dataclass
class StorageReference:
    """Pointer to persisted data. NOT frozen=True despite docstring
    describing it as "immutable" — DataObject.storage_ref setter
    requires mutability.

    Sub-label b-code-wins: A2 audit confirmed adding frozen=True would
    break the setter. Fix is doc-side: remove "immutable" claim from
    docstring AND from ARCH §4.2 wherever it appears.
    """
    backend: str                # "zarr" | "arrow" | "filesystem" | "composite"
    path: str                   # filesystem path or backend-specific URI
    type_chain: list[str]       # leaf-to-root MRO (for reconstruction)
    shape: tuple[int, ...] | None = None    # for Array (lazy-read sizing)
    dtype: str | None = None    # numpy dtype string (for Array)
    axes: list[str] | None = None           # for Array
    slot_refs: dict[str, "StorageReference"] | None = None    # for CompositeData
    extras: dict[str, Any] = field(default_factory=dict)      # backend-specific
```

### `storage-backends.StorageBackend` — Protocol all backends satisfy
Status: a
Source: `src/scieasy/core/storage/base.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.2`

```python
@runtime_checkable
class StorageBackend(Protocol):
    """Protocol every storage backend must satisfy. 6 methods (per
    C2 audit verification; all 4 core backends implement all 6).
    """

    def read(self, ref: StorageReference) -> Any:
        """Read full data from storage. Returns native Python object
        (numpy ndarray for Array, pyarrow.Table for DataFrame, str
        for Text, Path for Artifact, dict-of-slots for CompositeData)."""

    def write(self, obj: Any, dest: Path) -> StorageReference:
        """Write obj to dest. Returns a StorageReference pointing at
        the persisted location. Implementations should be atomic
        (temp + rename); Arrow + Composite are exceptions (see
        separate b-class entries below)."""

    def slice(self, ref: StorageReference, *args) -> Any:
        """Backend-specific sub-selection without full read."""

    def iter_chunks(self, ref: StorageReference, chunk_size: int) -> Iterator:
        """Yield successive chunks from storage. Constant memory."""

    def get_metadata(self, ref: StorageReference) -> dict:
        """Return backend-specific metadata dict (shape, dtype, axes,
        chunk_shape for Zarr; columns + schema for Arrow; etc.).
        Used by inspect_data MCP tool to summarize without loading."""

    def write_from_memory(self, obj: Any, dest: Path) -> StorageReference:
        """Variant of write() optimized for in-memory data (e.g.,
        numpy ndarray vs ndarray-on-disk). May skip atomic-rename
        for performance."""
```

### `storage-backends.ZarrBackend` — Zarr storage for chunked arrays
Status: a
Source: `src/scieasy/core/storage/zarr_backend.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.2`

```python
class ZarrBackend:
    """Zarr v3 backend for Array + Series.

    Atomic write: writes to tempdir, then os.rename to dest.
    Supports chunked partial reads via Zarr indexing.

    Implements StorageBackend Protocol (6 methods).
    """
    # ... 6 Protocol methods, all standard Zarr semantics
```

### `storage-backends.ArrowBackend` — Apache Arrow/Parquet for DataFrame
Status: b
Source: `src/scieasy/core/storage/arrow_backend.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.2`
Issue: #TBD-arrow-backend-atomic-write

```python
class ArrowBackend:
    """Arrow/Parquet backend for DataFrame.

    Sub-label b-docs-wins: NOT atomic write (unlike Zarr +
    Filesystem). Direct write to dest path. If interrupted, leaves
    partial file. ARCH §4.2 should document this asymmetry OR fix
    code to be atomic (temp + rename).

    Implements StorageBackend Protocol (6 methods).
    """
```

### `storage-backends.FilesystemBackend` — plain files for Text + Artifact
Status: a
Source: `src/scieasy/core/storage/filesystem_backend.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.2`

```python
class FilesystemBackend:
    """Plain-file backend for Text + Artifact.

    Atomic write: temp + rename.
    For Artifact: pass-through (file already at file_path; write is
    no-op; read returns the existing path).

    Implements StorageBackend Protocol (6 methods).
    """
```

### `storage-backends.CompositeStore` — directory-of-slots backend
Status: b
Source: `src/scieasy/core/storage/composite_store.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.2`
Issue: #TBD-compositestore-iter-write-behavior-doc

```python
class CompositeStore:
    """Backend for CompositeData. Stores each slot via the appropriate
    sub-backend; maintains a manifest.json mapping slot_name → sub-
    storage_ref.

    Sub-label b-docs-wins: 2 documented behavior gaps:
      1. iter_chunks() silently ignores chunk_size argument; instead
         yields (slot_name, full_slot_data) tuples — semantically
         inconsistent with other backends' chunk-yielding.
      2. write() is NOT atomic — manifest.json is written LAST, so
         interruption between slot writes and manifest write yields
         a partial state (slots written but unreferenced).

    Fix: code-side cleanup OR document both deviations. SSOT
    establishes both as known behavior gaps.

    Implements StorageBackend Protocol (6 methods, with caveats above).
    """
```

### `storage-backends.BackendRouter` — type→backend routing
Status: a
Source: `src/scieasy/core/storage/router.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.2`

```python
class BackendRouter:
    """MRO-based type → backend dispatch.

    Default mappings:
        Array         → ZarrBackend
        Series        → ZarrBackend
        DataFrame     → ArrowBackend
        Text          → FilesystemBackend
        Artifact      → FilesystemBackend
        CompositeData → CompositeStore

    Plugins can register additional mappings via _register_backend()
    (internal). Walks MRO to find the most-specific registered
    backend for a given DataObject subclass.
    """
    def dispatch(self, obj_or_type: DataObject | type) -> StorageBackend:
        """Return the backend instance for the given object/type."""
```

### `storage-backends.flush_context` — auto-flush output-dir state
Status: d
Source: `src/scieasy/core/storage/flush_context.py`
Primary-doc-source: `[ARCHITECTURE: §6.2 mechanism described; module not enumerated]`
Issue: #TBD-flush-context-document

```python
# d-document — module-level global state used by Block._auto_flush
# and Array.sel() to decide where to persist new objects. NOT
# thread-safe; relies on subprocess-single-flow assumption per
# ADR-017.

def get_output_dir() -> Path | None:
    """Return the current output directory for auto-flush, or None
    if no context is set."""

def set_output_dir(path: Path) -> None:
    """Set the auto-flush output directory for the current process.

    Typically called by the worker subprocess at startup before
    block.run() executes. Subsequent _auto_flush calls write into
    this directory.
    """

def clear() -> None:
    """Reset the output directory to None. Called after block.run()
    completes (in finally)."""
```

---

## 5. collection-transport

**Module preamble** (from Codex M01 sub): Transport-only wrapper (NOT a DataObject — explicit per ADR-020 + C3 verification). Three-tier memory safety model (process_item Tier 1 / map_items Tier 2 / manual loop Tier 3) with _auto_flush as the cross-tier safety net. NEW: `core.materialisation` module proposed per ADR-028 §D8 to fix AppBlock bridge dead JSON-dump fallback (#1078).

### `collection-transport.Collection` — homogeneous DataObject transport wrapper
Status: a
Source: `src/scieasy/core/types/collection.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §6.2`
Supplementary-doc-source: ADR-020

```python
class Collection:
    """Homogeneous ordered container of DataObjects.

    NOT a DataObject subclass (verified by C3 — uses __slots__ + has
    no DataObject inheritance). Pure transport wrapper. Its type
    identity for port matching is determined by item_type (NOT by
    its own class).

    A single item is Collection with length=1. There is no special
    case. The engine treats all Collections identically.
    """
    items: list[DataObject]
    item_type: type            # determines port compatibility (NOT type(Collection))
    __slots__ = ("items", "item_type")

    def __getitem__(self, index: int) -> DataObject: ...
    def __iter__(self) -> Iterator[DataObject]: ...
    def __len__(self) -> int: ...

    def storage_refs(self) -> list[StorageReference]:
        """Naming note (per C3): PLURAL — `storage_refs` (vs DataObject's
        singular `storage_ref`). Returns list of each item's storage_ref."""

    @classmethod
    def __class_getitem__(cls, item):
        """Returns bare cls for type-annotation use (`Collection[Image]`).

        IMPORTANT: this makes `Collection[Image]` work in annotations
        but NOT in isinstance() checks (isinstance returns based on
        Collection alone). Intentional per ADR-020.
        """
        return cls
```

### `collection-transport.LazyList` — memory-safe iteration wrapper
Status: b
Source: `src/scieasy/blocks/code/lazy_list.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §6.2`
Supplementary-doc-source: ADR-020 Add 4, ADR-031
Issue: #707

```python
class LazyList:
    """Memory-safe list-like wrapper for CodeBlock auto-unpack.

    Sub-label b-docs-wins: _load_item still calls .view().to_memory()
    — but `.view()` is a ViewProxy method that ADR-031 eliminated.
    Code must update to call .to_memory() directly. Fix is code-side
    per #707.

    For length>1 Collection inputs to CodeBlock, the input variable
    is wrapped in LazyList. Iteration over LazyList loads one item
    at a time (constant peak memory). Index access loads on demand
    + caches.

    User scripts iterate transparently:
        for item in input_0:    # input_0 is a LazyList
            process(item)
    """
    def __iter__(self) -> Iterator[Any]: ...
    def __getitem__(self, index: int) -> Any: ...
    def __len__(self) -> int: ...

    def _load_item(self, index: int) -> Any:
        """Load and cache item at index. CURRENTLY calls
        item.view().to_memory() (broken — .view() removed per
        ADR-031). MUST be fixed to just .to_memory() — #707."""
```

### `collection-transport.Block-pack-unpack-cross-listed` — cross-reference to §1
Status: a
Source: `src/scieasy/blocks/base/block.py:L268-L332`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §6.2`

```
# Cross-listed — canonical entries live in §1 block-abc:
#   block-abc.Block.pack / unpack / unpack_single (Collection utilities)
#   block-abc.Block.map_items / parallel_map (Tier 2 iteration helpers)
#   block-abc.Block._auto_flush (Tier 3 safety-net flush)
# Listed here to make the collection-transport module surface
# complete; SSOT canonical location is §1.
```

### `collection-transport.flush_context-cross-listed` — cross-reference to §4
Status: a
Source: `src/scieasy/core/storage/flush_context.py:L1-L1`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §6.2`

```
# Cross-listed — canonical entry is in §4 storage-backends:
#   storage-backends.flush_context (auto-flush output-dir state)
```

### `collection-transport.core.materialisation` — NEW module (ADR-028 §D8)
Status: c
Source: `[CODE: not implemented — module to be created]`
Primary-doc-source: ADR-028 §D8 + Codex draft v3 cross-cascade analysis
Issue: #1078

```python
# c-impl — NEW module per ADR-028 §D8 cluster. Tentative location:
# src/scieasy/core/materialisation.py
#
# Phase 6 placement caveat (Codex M01 cross-cascade analysis): ARCH §4.7
# zones boundary materialisation to blocks/app|io/ rather than core/.
# Final placement (core/materialisation.py vs blocks/io/materialisation.py)
# is TBD in Phase 7+ audit + ADR-028 §D8 implementation work. The
# CONTRACT signature below is stable regardless of final placement.

def materialise_to_file(
    obj: DataObject,
    dest: Path,
    format_hint: str | None = None,
) -> Path:
    """Write a DataObject to a file in a format dispatched from its
    type + optional format hint.

    Used by AppBlock.bridge.prepare() (#1080 c-impl) to write input
    DataObjects to the exchange directory before launching the
    external GUI.

    Args:
        obj: any DataObject.
        dest: target file path (extension determines format if no
            format_hint provided).
        format_hint: optional format identifier (e.g., "tiff", "csv")
            overriding extension-based dispatch.

    Returns:
        The actual dest path (may differ from input if extension was
        normalized).

    Raises:
        ValueError: if no materialisation handler is registered for
            obj's type + the requested format.
    """

def reconstruct_from_file(
    path: Path,
    type_hint: type | None = None,
) -> DataObject:
    """Load a file and reconstruct a typed DataObject.

    Used by AppBlock._bin_outputs_by_extension() (#1079 c-impl) to
    reconstruct typed DataObjects from external GUI output files.

    Dispatch: BlockRegistry.find_loader(path.suffix.lower()) → use
    the loader's _load_<format>() method.

    Args:
        path: source file.
        type_hint: optional expected DataObject type (validated
            post-load).

    Returns:
        A reconstructed DataObject.

    Raises:
        ValueError: if no loader is registered for path's extension.
        TypeError: if type_hint provided AND loaded object is not a
            subclass of type_hint.
    """
```

---

## 6. block-registry

**Module preamble** (from Codex M02 sub): Registry strictness vs fallback B-class (docs-fix per Codex R2 + my K1/K2/K3). Plugin entry-point callable protocol per ADR-025. Per C3 audit: 14 of 14 core `scieasy.blocks` entry-points are DIRECT CLASS REFERENCES, not `(PackageInfo, list[Block])` callables — `BlockRegistry._packages` is therefore always `{}` for core blocks. NEW: 3 lookup methods (`find_loader`/`find_saver`/`find_io_blocks_for_type`) per ADR-028 §D8 (#1077).

### `block-registry.BlockRegistry` — central block catalogue
Status: a
Source: `src/scieasy/blocks/registry.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.4`
Supplementary-doc-source: ADR-025

```python
class BlockRegistry:
    """Central catalogue of all available blocks.

    Discovery flows (per ADR-025):
      - Tier 1 drop-in: scan_dirs (.py files in {project}/blocks/ +
        ~/.scieasy/blocks/) — auto-discovered on startup + Reload.
      - Tier 2 entry-points: scieasy.blocks entry-point group from
        installed packages.

    Per C3 finding: core's 14 built-in entry-points are direct class
    references, NOT (PackageInfo, list[Block]) callables — so _packages
    is always {} for core. Plugin packages MAY use the callable form
    (PackageInfo, [...]).
    """

    def __init__(self) -> None:
        self._specs: dict[str, BlockSpec] = {}
        self._packages: dict[str, PackageInfo] = {}    # only populated by callable-form entry-points

    def scan(self) -> None:
        """Run both Tier 1 (drop-in directories) and Tier 2 (entry-
        points) discovery. Idempotent."""

    def hot_reload(self) -> None:
        """Re-scan Tier 1 directories only (fast; triggered by UI
        Reload button)."""

    def packages(self) -> dict[str, PackageInfo]:
        """Return mapping of package_name → PackageInfo for all
        registered PACKAGES (callable-form entry-points only).
        For core: returns {} (direct class refs don't carry
        PackageInfo)."""

    def specs_by_package(self) -> dict[str, list[BlockSpec]]:
        """Group block specs by package_name. For core blocks
        (direct class refs), package_name is the entry-point name."""

    def _validate_dynamic_ports(self, spec: BlockSpec) -> None:
        """Validate a spec's dynamic_ports descriptor shape per
        ADR-028 Addendum 1 §C5. Called during scan() registration.
        Raises BlockRegistrationError on malformed descriptor."""
```

### `block-registry.BlockSpec` — block-metadata descriptor
Status: b
Source: `src/scieasy/blocks/base/spec.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.4`
Issue: #TBD-blockspec-source-literal-type

```python
@dataclass
class BlockSpec:
    """Block metadata descriptor populated by BlockRegistry at scan.

    Sub-label b-code-wins: `source` is a de-facto enum typed as `str`
    with 4 known values; should be `Literal["builtin", "tier1",
    "entry_point", "monorepo"]`. Fix: code-side add Literal type.
    """
    name: str                       # canonical block name (e.g., "imaging.threshold")
    description: str
    version: str                    # ADR-038: auto-injected via importlib.metadata
    input_ports: list[InputPort]
    output_ports: list[OutputPort]
    config_schema: dict[str, Any]   # JSON Schema (MRO-merged per ADR-030)
    execution_mode: ExecutionMode
    package_name: str               # for two-level palette grouping (ADR-025)
    subcategory: str                # second-level category (free-form, set by author)
    category: str                   # legacy field (use subcategory + base_category instead)
    source: str                     # Literal["builtin", "tier1", "entry_point", "monorepo"]
```

### `block-registry.PackageInfo` — block-package metadata
Status: a
Source: `src/scieasy/blocks/base/package_info.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.4`
Supplementary-doc-source: ADR-025

```python
@dataclass
class PackageInfo:
    """Metadata for an external block package, shown in the GUI
    palette as the top-level grouping."""
    name: str                       # display name (e.g., "SRS Imaging")
    description: str = ""           # one-line
    author: str = ""                # author or lab name
    version: str = "0.1.0"
```

### `block-registry.BlockRegistrationError` — registry error
Status: a
Source: `src/scieasy/blocks/registry.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.4`

```python
class BlockRegistrationError(Exception):
    """Raised by BlockRegistry.scan() when a block fails registration:
      - missing required ClassVar (name / input_ports / output_ports)
      - malformed dynamic_ports descriptor
      - version cannot be resolved from importlib.metadata
      - dynamic_ports validation failure
    """
```

### `block-registry.entry-point-groups` — `scieasy.blocks` / `scieasy.types` / `scieasy.runners`
Status: b
Source: `pyproject.toml [project.entry-points]`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.4`
Supplementary-doc-source: ADR-025
Issue: #TBD-entry-points-callable-vs-direct-ref

```toml
# b-docs-wins — ARCH §5.4 describes the callable-form entry-point
# protocol as the standard. Core's 14 scieasy.blocks entry-points are
# DIRECT CLASS REFS (not callable form). BlockRegistry._packages is
# always {} for core. Either ARCH should describe both forms (current
# direct-ref + callable-form for plugins) OR core entry-points should
# migrate to callable form.
#
# Current core entry-point declarations (verbatim from pyproject.toml):
[project.entry-points."scieasy.blocks"]
load_data = "scieasy.blocks.io.loaders.load_data:LoadData"
save_data = "scieasy.blocks.io.savers.save_data:SaveData"
process_merge = "scieasy.blocks.process.builtins.merge:MergeBlock"
process_split = "scieasy.blocks.process.builtins.split:SplitBlock"
code_block = "scieasy.blocks.code:CodeBlock"
app_block = "scieasy.blocks.app:AppBlock"
ai_block = "scieasy.blocks.ai:AIBlock"
subworkflow_block = "scieasy.blocks.subworkflow:SubWorkflowBlock"
merge_collection = "scieasy.blocks.process.builtins.merge_collection:MergeCollection"
split_collection = "scieasy.blocks.process.builtins.split_collection:SplitCollection"
filter_collection = "scieasy.blocks.process.builtins.filter_collection:FilterCollection"
slice_collection = "scieasy.blocks.process.builtins.slice_collection:SliceCollection"
data_router = "scieasy.blocks.process.builtins.data_router:DataRouter"
pair_editor = "scieasy.blocks.process.builtins.pair_editor:PairEditor"

# scieasy.types — EMPTY in core (per ADR-027 D2; all domain types in plugins)
[project.entry-points."scieasy.types"]

# scieasy.runners — 3 built-in runners
[project.entry-points."scieasy.runners"]
python = "scieasy.blocks.code.runners.python_runner:PythonRunner"
r = "scieasy.blocks.code.runners.r_runner:RRunner"
julia = "scieasy.blocks.code.runners.julia_runner:JuliaRunner"
```

### `block-registry.find_loader` / `find_saver` / `find_io_blocks_for_type` — NEW lookup API
Status: c
Source: `[CODE: not implemented — 0%]`
Primary-doc-source: ADR-028 §D8
Issue: #1077

```python
# c-impl — 3 chained methods per ADR-028 §D8. Required by:
#  - AppBlock._bin_outputs_by_extension() (#1079)
#  - core.materialisation.reconstruct_from_file() (#1078)
#  - Future SaveBlock dispatch
#
# Methods are SCANS over registered IOBlock subclasses' supported_extensions
# ClassVars (#1074 c-impl). When IOBlock subclasses don't yet declare
# supported_extensions, these methods return None / []  (graceful degrade).

def find_loader(self, file_extension: str) -> type[IOBlock] | None:
    """Find an IOBlock subclass with direction='input' that supports
    the given file extension.

    Args:
        file_extension: with or without leading dot, case-insensitive.

    Returns:
        The IOBlock subclass with the matching supported_extensions
        entry, OR None if no match. If multiple match, returns the
        first (registration order). Future: deterministic priority.
    """

def find_saver(self, file_extension: str) -> type[IOBlock] | None:
    """Mirror of find_loader for direction='output'."""

def find_io_blocks_for_type(self, type_name: str) -> list[type[IOBlock]]:
    """Find all IOBlock subclasses (both directions) whose declared
    types include type_name.

    Used by the GUI palette + workflow validator to suggest
    appropriate IOBlocks for a given data type.

    Args:
        type_name: canonical DataObject class name (e.g., "Image",
            "DataFrame").

    Returns:
        List of matching IOBlock subclasses (may be empty).
    """
```

### `block-registry.BlockTestHarness` — Block SDK test helper
Status: d
Source: `src/scieasy/testing/harness.py`
Primary-doc-source: `[ARCHITECTURE: ADR-026 referenced; class internals not enumerated]`
Issue: #TBD-blocktestharness-document

```python
class BlockTestHarness:
    """Block SDK test helper. Eliminates boilerplate for unit-testing
    custom blocks.

    Sub-label d-document: ARCH §12 references ADR-026 + the Block SDK;
    the class internals are documented only in ADR-026 + docstring.
    SSOT establishes the contract.

    IMPORTANT (C3 finding): smoke_test() does NOT auto-wrap inputs.
    Callers must supply Collection instances directly. Raw Python
    dicts/lists are wrapped by run() but not by smoke_test().
    """

    def __init__(
        self,
        block_class: type[Block],
        work_dir: Path,
    ) -> None:
        """Initialize harness for testing block_class.

        Args:
            block_class: the Block subclass under test.
            work_dir: temporary working directory (typically tmp_path
                from pytest).
        """

    def run(
        self,
        inputs: dict[str, Any],     # raw dicts/lists/arrays — auto-wrapped
        params: dict[str, Any],     # config kwargs
    ) -> dict[str, Any]:
        """Run the block with auto-wrapped inputs.

        Wraps raw dicts → DataObject subclasses (per port's
        accepted_types), wraps each into Collection, creates a
        BlockConfig, calls block.run(), materializes outputs to
        easy-to-assert native types.

        Returns:
            dict mapping output port name → materialized native value.
        """

    def smoke_test(self) -> bool:
        """Run a minimal sanity check on the block:
          - instantiable
          - validate() passes with default inputs
          - run() returns dict matching output_ports

        Inputs must be pre-wrapped Collections (NOT auto-wrapped by
        this method, unlike run()).

        Returns:
            True on success; raises on failure.
        """
```

### `block-registry.TypeRegistry.has` — missing convenience method
Status: c
Source: `[CODE: not implemented — callers must catch KeyError or iterate]`
Primary-doc-source: `[ARCHITECTURE: not documented; design choice]`
Issue: #TBD-typeregistry-has-method

```python
# c-impl — convenience method that callers currently can't use.
# Decision: either implement OR document the workaround in the
# TypeRegistry entry above. SSOT establishes the canonical form
# if implemented:

def has(self, name: str) -> bool:
    """Return True if a class with canonical name is registered.

    Convenience method to avoid try/except KeyError patterns:
        # Before (current):
        try:
            _ = registry.resolve("Image")
            present = True
        except KeyError:
            present = False

        # After (with .has):
        present = registry.has("Image")

    Strictly an additive convenience — does NOT change any other
    method's behavior.
    """
```

---

## 7. execution-engine

**Module preamble** (from Codex M03): DAG lifecycle protocol stable A. Sub-issues: scheduler responsibility breadth B-class (cross-cutting concerns aggregated in DAGScheduler — code-change recommended for narrowing per CLAUDE.md §7.3). Checkpoint wire schema details B-class (docs-fix — implementation exists but not centralized in ARCH §6.3). Event-bus subscription matrix has 2 declared-but-never-emitted constants (BLOCK_READY + CHECKPOINT_SAVED). PTY control uses HTTP loopback (not stdin/stdout) — undocumented transport. 49 interfaces (per A4 audit — C4's original count of 47 missed save/load_checkpoint).

### `execution-engine.EngineEvent` — single event on the bus
Status: a
Source: `src/scieasy/engine/events.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §6.1`

```python
@dataclass
class EngineEvent:
    """Event published on the EventBus.

    event_type is one of 17 string constants (see event-types entry).
    data dict is event-type-specific; common keys: workflow_id,
    block_id, outputs (for BLOCK_DONE), error (for BLOCK_ERROR),
    skip_reason (for BLOCK_SKIPPED).
    """
    event_type: str
    block_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
```

### `execution-engine.EventBus` — pub/sub dispatcher
Status: a
Source: `src/scieasy/engine/events.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §6.1`

```python
class EventBus:
    """Async pub/sub dispatcher. Single instance per running engine.

    Subscribers register Callable handlers per event_type. emit()
    awaits all handlers for that event_type sequentially (single-
    threaded asyncio); handlers should be short — long work belongs
    in tasks they spawn.

    The 6 primary subscribers (per ARCH §6.1 subscription matrix):
      DAGScheduler, ResourceManager, ProcessRegistry, WebSocket
      handler, LineageRecorder, CheckpointManager.
    """
    def subscribe(self, event_type: str, handler: Callable) -> None: ...
    async def emit(self, event: EngineEvent) -> None: ...
    def unsubscribe(self, event_type: str, handler: Callable) -> None: ...
```

### `execution-engine.event-type-constants` — 17 named string constants
Status: b
Source: `src/scieasy/engine/events.py:L67-L79`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §6.1`
Issue: #TBD-events-subscription-matrix-code-fix

```python
# b-docs-wins — 17 constants declared; CHECKPOINT_SAVED + BLOCK_READY
# are NEVER EMITTED anywhere in the codebase. Fix is code-side: either
# emit them at the appropriate moments OR remove the constants.
# A4 also flagged the subscription-matrix comment in events.py:L67-79
# as stale (lists subscriptions that don't actually exist) — same fix
# PR should update.

# Block lifecycle:
BLOCK_RUNNING       = "block_running"
BLOCK_READY         = "block_ready"          # DECLARED, NEVER EMITTED
BLOCK_DONE          = "block_done"
BLOCK_ERROR         = "block_error"
BLOCK_CANCELLED     = "block_cancelled"
BLOCK_SKIPPED       = "block_skipped"
BLOCK_PAUSED        = "block_paused"

# Workflow lifecycle:
WORKFLOW_STARTED    = "workflow_started"
WORKFLOW_COMPLETED  = "workflow_completed"
WORKFLOW_PAUSED     = "workflow_paused"
WORKFLOW_RESUMED    = "workflow_resumed"

# Cancellation:
CANCEL_BLOCK_REQUEST    = "cancel_block_request"
CANCEL_WORKFLOW_REQUEST = "cancel_workflow_request"

# Process lifecycle:
PROCESS_SPAWNED     = "process_spawned"
PROCESS_EXITED      = "process_exited"

# Interactive:
INTERACTIVE_COMPLETE = "interactive_complete"

# Checkpoint:
CHECKPOINT_SAVED    = "checkpoint_saved"     # DECLARED, NEVER EMITTED
```

### `execution-engine.DAG` / `build_dag` / topo helpers — internal graph data structure
Status: d
Source: `src/scieasy/engine/dag.py`
Primary-doc-source: `[ARCHITECTURE: §6.1 algorithmic; internal data structure]`
Issue: #TBD-dag-helpers-document

```python
# d-document — public functions used by DAGScheduler + workflow
# validator. ARCH §6.1 describes the algorithms but doesn't enumerate
# the helpers.

@dataclass
class DAG:
    """Internal graph representation of a workflow."""
    nodes: dict[str, NodeData]       # block_id → node data
    edges: list[Edge]                # source.port → target.port edges
    adjacency: dict[str, list[str]]  # block_id → successor block_ids

def build_dag(workflow: WorkflowDefinition) -> DAG:
    """Construct a DAG from a workflow definition.

    Raises CycleError if the workflow contains cycles.
    """

def topological_sort(dag: DAG) -> list[str]:
    """Return block_ids in topological order.

    Raises CycleError if dag has cycles (build_dag should have
    caught this, but this is defensive).
    """

class CycleError(Exception):
    """Raised when topological sort detects a cycle."""

def get_downstream_blocks(dag: DAG, block_id: str) -> list[str]:
    """Return block_ids that depend (transitively) on block_id's
    outputs. Used for SKIPPED propagation."""

def get_root_nodes(dag: DAG) -> list[str]:
    """Return block_ids with no input edges (initial dispatch
    candidates)."""

def get_leaf_nodes(dag: DAG) -> list[str]:
    """Return block_ids with no output edges (terminal blocks)."""
```

### `execution-engine.DAGScheduler` — event-driven workflow executor
Status: b
Source: `src/scieasy/engine/scheduler.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §6.1`
Supplementary-doc-source: ADR-018, ADR-018 Addendum 1
Issue: #TBD-dagscheduler-ctor-arch-update

```python
class DAGScheduler:
    """Event-driven workflow executor.

    Sub-label b-code-wins: code __init__ has 9 params; ARCH §6.1
    lists 5. ARCH must update. Plus Codex M03 R2 cross-cascade
    flagged scheduler responsibility BREADTH (aggregates event
    emission + version stamping + PTY interaction + lineage
    driving) — separate b-code-change entry below.

    Concurrency: uses asyncio.create_task to start each block as an
    independent task (ADR-018 Add 1). Independent DAG branches
    execute in parallel. Resource gating via ResourceManager.can_
    dispatch().
    """

    def __init__(
        self,
        workflow: WorkflowDefinition,
        event_bus: EventBus,
        runner: BlockRunner,
        resource_manager: ResourceManager,
        process_registry: ProcessRegistry,
        lineage_recorder: LineageRecorder | None = None,
        checkpoint_manager: CheckpointManager | None = None,
        # Additional code-side params not in ARCH §6.1:
        completion_event: asyncio.Event | None = None,
        active_tasks: dict[str, asyncio.Task[None]] | None = None,
    ) -> None: ...

    async def execute(self) -> None:
        """Run the workflow to completion. Initial dispatch fans out
        from root nodes; event handlers fan out to successors as each
        block completes. try/finally guarantees subprocess cleanup
        even on exception."""

    async def _dispatch(self, block_id: str) -> None:
        """Synchronous prelude: transition state + create the run task.
        Does NOT inline-await the subprocess. Returns immediately."""

    async def _run_and_finalize(
        self, block_id: str, block, inputs, config
    ) -> None:
        """Task body: await subprocess, store outputs, emit terminal
        events. Catches BlockTerminalStateReportedError to honor
        worker self-reported final_state per #681."""

    async def _on_block_done(self, event: EngineEvent) -> None:
        """Dispatch newly-ready successors AND retry READY blocks
        previously blocked by resource gating."""

    async def _on_cancel_block(self, event: EngineEvent) -> None:
        """Initiate cancellation: kill subprocess via ProcessHandle.
        terminate(); transition state; propagate SKIPPED downstream."""

    def _propagate_skipped(self, failed_block_id: str) -> None:
        """Mark all unreachable downstream blocks as SKIPPED."""

    def _check_completion(self) -> None:
        """Set self._completed_event if all blocks are in terminal
        states AND _active_tasks is empty."""

    async def _dispatch_newly_ready(self) -> None:
        """Scan for IDLE blocks whose predecessors are DONE + READY
        blocks previously gated; dispatch them."""

    async def _cancel_active_tasks_on_shutdown(self) -> None:
        """Best-effort cleanup in execute() finally: terminate
        subprocesses, cancel tasks."""
```

### `execution-engine.RunHandle` — future-evolution placeholder
Status: d
Source: `src/scieasy/engine/runners/base.py`
Primary-doc-source: `[CODE: defined but not produced by any runner]`
Issue: #TBD-runhandle-future-or-private

```python
# d-document — class is defined but BlockRunner.run() currently returns
# dict[str, Any] (not RunHandle). RunHandle is a future-evolution
# placeholder for when remote runners (SSH, Slurm, Cloud) need to
# return a handle for async status polling.
#
# A4 audit recommended d-document over d-private (so future remote
# runner authors find the contract). SSOT documents the shape:

@dataclass
class RunHandle:
    """Future-evolution placeholder for async block execution.

    Currently NOT produced by any BlockRunner — LocalRunner.run()
    returns dict[str, Any] directly. When remote runners ship,
    they'll return RunHandle for status polling without blocking.
    """
    run_id: str
    process_handle: ProcessHandle
    result: asyncio.Future[dict[str, Any]]    # resolves when subprocess completes
```

### `execution-engine.ResourceRequest` / `ResourceSnapshot` — resource accounting types
Status: a
Source: `src/scieasy/engine/resources.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §6.4`

```python
@dataclass
class ResourceRequest:
    """Block-declared resource needs (Block class-level attribute)."""
    requires_gpu: bool = False
    gpu_memory_gb: float = 0.0           # declared (not enforced — VRAM not cross-platform observable)
    cpu_cores: int = 1
    max_internal_workers: int = 1        # ADR-027 D8: declared internal parallelism

    @property
    def effective_cpu(self) -> int:
        """Total CPU footprint for ResourceManager accounting:
        cpu_cores * max_internal_workers."""

@dataclass
class ResourceSnapshot:
    """Read-only view of current resource state for UI display."""
    gpu_available: int                   # gpu_slots - gpu_in_use
    cpu_available: int                   # max_cpu_workers - cpu_in_use
    memory_pct_used: float               # 0.0 - 1.0
```

### `execution-engine.ResourceManager` — dispatch gating
Status: b
Source: `src/scieasy/engine/resources.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §6.4`
Issue: #887, #TBD-resourcemanager-watermark-doc-fix

```python
class ResourceManager:
    """Dispatch gating based on discrete resources (GPU + CPU) + OS-
    monitored memory.

    2 b-class issues on this class:
      - memory_high_watermark: docstring says 0.80, code default is
        0.90. (b-code-wins — code is current default.)
      - acquire(): zero production callers (#887). ARCH §6.4 says
        block.resource_request should be wired into _dispatch via
        acquire(); code currently doesn't wire it. (b-docs-wins —
        ARCH is the SoT; code must catch up.)
    """

    def __init__(
        self,
        gpu_slots: int | None = None,            # None triggers _auto_detect_gpu_slots
        cpu_workers: int = 4,
        memory_high_watermark: float = 0.90,     # docstring says 0.80 — STALE
        memory_critical: float = 0.95,
    ) -> None:
        """If gpu_slots is None, auto-detect via torch.cuda.device_count()
        or nvidia-smi (ADR-027 D10)."""

    def can_dispatch(self, request: ResourceRequest) -> bool:
        """Check if resources are available for dispatching a block.
        GPU/CPU: discrete slot counting. Memory: OS-level check via
        psutil. Returns True if all 3 checks pass."""

    def release(self, request: ResourceRequest) -> None:
        """Release discrete resources (GPU slots + CPU cores).
        Memory is NOT explicitly released (drops naturally on
        subprocess exit). Called by EventBus subscribers on
        BLOCK_DONE / BLOCK_ERROR / BLOCK_CANCELLED / PROCESS_EXITED."""

    def acquire(self, request: ResourceRequest) -> None:
        """ZERO PRODUCTION CALLERS per #887. ARCH §6.4 says this
        should be called from DAGScheduler._dispatch to reserve
        resources before launching. Currently dispatch just gates
        via can_dispatch and tracks separately. Fix per #887:
        wire acquire() into _dispatch."""

    @property
    def available(self) -> ResourceSnapshot:
        """Current resource state for UI display + scheduler
        retry decisions."""
```

### `execution-engine.save_checkpoint` / `load_checkpoint` — checkpoint I/O (A4-discovered)
Status: d
Source: `src/scieasy/engine/checkpoint.py:L244-L284`
Primary-doc-source: `[ARCHITECTURE: §6.3 abstract only]`
Issue: #TBD-save-load-checkpoint-document

```python
# d-document — A4 audit caught these missing from C4's inventory.
# True execution-engine interface count is 49, not 47. Both are
# public module-level functions; called by CheckpointManager.save()
# and load() but also usable standalone.

def save_checkpoint(
    checkpoint: WorkflowCheckpoint,
    path: Path,
) -> None:
    """Serialize a WorkflowCheckpoint to a JSON file at path.

    Schema: WorkflowCheckpoint dataclass fields serialized via
    dataclass_to_dict; block_states (BlockState enum) → string;
    intermediate_refs (StorageReference) → dict via _serialise_one
    pattern.

    Atomic: writes to path + ".tmp", then os.rename.
    """

def load_checkpoint(path: Path) -> WorkflowCheckpoint:
    """Load a WorkflowCheckpoint from a JSON file at path.

    Returns reconstructed WorkflowCheckpoint with BlockState enum
    values restored from strings + intermediate_refs reconstructed
    via _reconstruct_one pattern (calls TypeRegistry.resolve to
    rebuild typed DataObjects).

    Raises:
        FileNotFoundError: if path doesn't exist.
        ValueError: if JSON malformed or schema mismatch.
    """
```

### `execution-engine.WorkflowCheckpoint` — execution snapshot
Status: b
Source: `src/scieasy/engine/checkpoint.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §6.3`
Issue: #TBD-checkpoint-pending-block-config-snapshot

```python
@dataclass
class WorkflowCheckpoint:
    """Snapshot of workflow state at a terminal block event.

    Sub-label b-code-wins: pending_block + config_snapshot are ALWAYS
    written as None / {} by save_checkpoint(). Either fields should
    be dropped (b-code-wins — code is truth) OR they should be
    populated (code-side fix).
    """
    workflow_id: str
    timestamp: datetime
    block_states: dict[str, BlockState]                # block_id → state
    intermediate_refs: dict[str, StorageReference]     # block_id → output ref
    pending_block: str | None = None                   # ALWAYS None — see issue
    config_snapshot: dict = field(default_factory=dict)  # ALWAYS {} — see issue
    skip_reasons: dict[str, str] = field(default_factory=dict)
```

### `execution-engine.CheckpointManager` — file-based checkpoint I/O
Status: b
Source: `src/scieasy/engine/checkpoint.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §6.3`
Issue: #TBD-checkpointmanager-list-checkpoints

```python
class CheckpointManager:
    """Single-slot checkpoint store at <project>/.scieasy/pause/.

    Sub-label b-code-wins: A4 + dispatch task description both
    referenced a list_checkpoints() method that does NOT EXIST.
    Spec must not promise it. The class has: save / load / latest /
    _on_state_change.

    Single-slot semantics: one file per workflow_id, overwritten on
    every terminal block event. Per ADR-038 §3.6a: this is distinct
    from lineage.db (which is append-only history).
    """

    def save(self, checkpoint: WorkflowCheckpoint) -> None:
        """Write checkpoint to <project>/.scieasy/pause/<workflow_id>.json
        (overwrites existing). Calls save_checkpoint() with the
        derived path."""

    def load(self, workflow_id: str) -> WorkflowCheckpoint | None:
        """Load the single checkpoint for workflow_id, or None if no
        checkpoint exists."""

    @property
    def latest(self) -> WorkflowCheckpoint | None:
        """Return the most-recently-modified checkpoint across all
        workflows (used for "resume last" UI action)."""

    async def _on_state_change(self, event: EngineEvent) -> None:
        """EventBus subscriber. On BLOCK_DONE / BLOCK_ERROR /
        BLOCK_CANCELLED / BLOCK_SKIPPED, save the current scheduler
        state to disk."""
```

### `execution-engine.serialize_intermediate_refs` / `deserialize_intermediate_refs` — wire-format codec
Status: d
Source: `src/scieasy/engine/checkpoint.py`
Primary-doc-source: `[ARCHITECTURE: behavior-only]`
Issue: #TBD-intermediate-refs-codec-document

```python
# d-document — A4 audit overruled M2's d-private; the normative
# constraint "deserialize MUST NOT be called in execute-from path"
# is a contract that needs to be in SSOT.

def serialize_intermediate_refs(
    refs: dict[str, Any],
) -> dict[str, dict]:
    """Convert a dict of {block_id: DataObject or Collection} to
    JSON-serializable wire format.

    Used by save_checkpoint() to persist intermediate outputs.
    """

def deserialize_intermediate_refs(
    data: dict[str, dict],
) -> dict[str, Any]:
    """Inverse of serialize: reconstruct {block_id: DataObject or
    Collection} from wire format.

    NORMATIVE CONSTRAINT: this function MUST NOT be called in the
    "Run from here" execute-from code path. The execute-from path
    uses the in-memory _block_outputs dict directly. Calling
    deserialize_intermediate_refs there would unnecessarily round-
    trip through disk and lose any non-serializable transient state.
    Only the resume-from-checkpoint path calls this.
    """
```

### `execution-engine.BlockRunner` — execution Protocol
Status: a
Source: `src/scieasy/engine/runners/base.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §6.8`

```python
class BlockRunner(Protocol):
    """Abstract interface between the scheduler and the execution
    environment. LocalRunner is the only implementation in v1;
    future SSHRunner / SlurmRunner / CloudRunner will satisfy the
    same Protocol.
    """
    async def run(self, block: Block, inputs: dict, config: dict) -> dict[str, Any]: ...
    async def check_status(self, run_id: str) -> BlockState: ...
    async def cancel(self, run_id: str) -> None: ...
```

### `execution-engine.LocalRunner` — subprocess-based runner
Status: a
Source: `src/scieasy/engine/runners/local.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §6.5, §6.8`

```python
class LocalRunner:
    """Default BlockRunner: spawns isolated subprocess per block run.

    Implements BlockRunner Protocol.

    run() → spawn_block_process → register_async_process → await
    worker stdout → parse JSON envelope → return outputs dict.
    On worker self-reported terminal state (per #681), raises
    BlockTerminalStateReportedError so DAGScheduler can honor.
    """
    async def run(self, block: Block, inputs: dict, config: dict) -> dict[str, Any]: ...
    async def check_status(self, run_id: str) -> BlockState: ...
    async def cancel(self, run_id: str) -> None: ...
```

### `execution-engine.worker-stdout-envelope` — JSON I/O format
Status: a
Source: `src/scieasy/engine/runners/worker.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §6.5`

```json
// Worker writes this JSON to stdout when block.run() completes.
{
  "outputs": {                              // port_name -> wire-format dict
    "<port_name_1>": { /* serialised DataObject or Collection */ },
    "<port_name_2>": { /* ... */ }
  },
  "environment": {                          // EnvironmentSnapshot (per §6.7)
    "python_version": "3.13.x",
    "platform": "linux-x86_64",
    "full_freeze": "...uv pip freeze output...",
    "key_packages": { "scipy": "...", "cellpose": "..." },
    "conda_env": null
  },
  "final_state": "cancelled"                // OPTIONAL: only when block self-reported terminal state per #681
}
// LocalRunner translates final_state into BlockTerminalStateReportedError.
```

### `execution-engine.ProcessHandle` — cross-platform process abstraction
Status: a
Source: `src/scieasy/engine/runners/process_handle.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §6.5`
Supplementary-doc-source: ADR-019

```python
class ProcessHandle:
    """Cross-platform abstraction over an OS process.

    Three guarantees per ADR-019:
      - always terminable (terminate / kill)
      - always observable (is_alive / exit_info)
      - always tracked (via ProcessRegistry)
    """
    block_id: str
    pid: int
    start_time: datetime
    resource_request: ResourceRequest

    async def is_alive(self) -> bool:
        """Non-blocking alive check.
        POSIX: os.kill(pid, 0). Windows: OpenProcess + GetExitCodeProcess."""

    async def exit_info(self) -> ProcessExitInfo | None:
        """Return exit info if exited, None if still running."""

    async def terminate(self, grace_period_sec: float = 5.0) -> ProcessExitInfo:
        """Terminate process and all children.
        POSIX: SIGTERM to process group → wait grace_period → SIGKILL.
        Windows: TerminateJobObject (immediate, no grace)."""

    async def kill(self) -> ProcessExitInfo:
        """Immediate forced termination. SIGKILL / TerminateProcess."""
```

### `execution-engine.ProcessExitInfo` — subprocess exit state
Status: a
Source: `src/scieasy/engine/runners/process_handle.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §6.5`

```python
@dataclass
class ProcessExitInfo:
    """Subprocess exit details."""
    exit_code: int | None
    signal_number: int | None        # POSIX only
    was_killed_by_framework: bool
    platform_detail: str             # e.g., "SIGKILL", "TerminateProcess"
```

### `execution-engine.ProcessRegistry` — active-process tracker
Status: a
Source: `src/scieasy/engine/runners/process_handle.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §6.5`

```python
class ProcessRegistry:
    """Singleton tracking all active block processes.

    EventBus subscribers: CANCEL_BLOCK_REQUEST → terminate process,
    PROCESS_EXITED → deregister handle.
    """
    def register(self, handle: ProcessHandle) -> None: ...
    def deregister(self, block_id: str) -> None: ...
    def get_handle(self, block_id: str) -> ProcessHandle | None: ...
    def active_handles(self) -> list[ProcessHandle]: ...
    def terminate_all(self, grace_period_sec: float = 5.0) -> None:
        """Emergency shutdown: terminate every active process."""
```

### `execution-engine.ProcessMonitor` — background process poller
Status: b
Source: `src/scieasy/engine/runners/process_monitor.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §6.5`
Issue: #TBD-process-monitor-poll-interval-configurable

```python
class ProcessMonitor:
    """Background coroutine polling active processes for unexpected
    exits (crashes, OOM kills, user task-manager kills).

    Sub-label b-code-wins: poll_interval_sec is HARDCODED to 1.0 in
    _poll_loop; no constructor parameter. Spec should either
    document as a hardcoded value OR code should expose as a
    parameter. Codex M03 R2 + A4 both flagged.
    """
    poll_interval_sec: float = 1.0    # hardcoded

    async def run(self) -> None:
        """Polling loop. On detecting an exit, emit PROCESS_EXITED
        event AND deregister the handle."""
```

### `execution-engine.spawn_block_process` — sync subprocess factory
Status: a
Source: `src/scieasy/engine/runners/local.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §6.5`

```python
def spawn_block_process(
    block_id: str,
    command: list[str],
    resource_request: ResourceRequest,
    event_bus: EventBus,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
    stdin_data: bytes | None = None,
) -> ProcessHandle:
    """Launch subprocess with platform-appropriate isolation.

    POSIX: start_new_session=True (new process group for killpg).
    Windows: CREATE_NEW_PROCESS_GROUP + Job Object (kills tree).

    Side effects: registers handle in ProcessRegistry, emits
    PROCESS_SPAWNED event on event_bus.
    """
```

### `execution-engine.register_async_process` / `build_worker_payload` — async runner helpers
Status: d
Source: `src/scieasy/engine/runners/local.py`
Primary-doc-source: `[ARCHITECTURE: behavior-only]`
Issue: #TBD-async-runner-helpers-document

```python
# d-document — A4 upgraded from d-private (no underscore, used by
# LocalRunner.run + tests).

def register_async_process(
    block_id: str,
    proc: asyncio.subprocess.Process,
    resource_request: ResourceRequest,
) -> ProcessHandle:
    """Wrap an asyncio subprocess into a ProcessHandle + register
    in ProcessRegistry. Async counterpart to spawn_block_process
    (which is sync subprocess.Popen-based)."""

def build_worker_payload(
    block: Block,
    inputs: dict,
    config: dict,
) -> dict:
    """Construct the JSON payload sent to the worker subprocess
    on stdin.

    Shape:
        {
            "block_spec": { ... BlockSpec serialized ... },
            "inputs": { port_name: [serialized DataObject, ...] },
            "config": { ... },
            "context": {
                "output_dir": str,
                "block_execution_id": str,
                "type_registry_state": { ... }
            }
        }

    Used by LocalRunner before subprocess spawn.
    """
```

### `execution-engine.PlatformOps` — cross-platform process Protocol
Status: d
Source: `src/scieasy/engine/runners/platform.py`
Primary-doc-source: `[ARCHITECTURE: §6.5 cross-platform table only]`
Issue: #TBD-platformops-protocol-document

```python
class PlatformOps(Protocol):
    """Platform-specific OS operations Protocol.

    Sub-label d-document: ARCH §6.5 has a per-platform table but
    doesn't enumerate the Protocol surface. Implementations:
    PosixOps, WindowsOps. Selected at runtime via get_platform_ops().
    """
    def kill_process_tree(self, pid: int, grace_period_sec: float) -> None:
        """Kill process + all children with grace period."""

    def is_process_alive(self, pid: int) -> bool:
        """Non-blocking check."""

    def get_exit_code(self, pid: int) -> int | None:
        """Return exit code if exited, None if running."""

    def create_process_group(self) -> int:
        """Create a new process group + return its id."""

class PosixOps:
    """PlatformOps for Linux + macOS. Uses os.killpg, os.kill,
    os.waitpid, etc."""

class WindowsOps:
    """PlatformOps for Windows. Uses TerminateJobObject,
    OpenProcess, GetExitCodeProcess via ctypes."""

def get_platform_ops() -> PlatformOps:
    """Return the PlatformOps instance for the current platform."""
```

### `execution-engine.BlockTerminalStateReportedError` — worker → orchestrator signal
Status: a
Source: `src/scieasy/engine/runners/local.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §6.5`
Supplementary-doc-source: issue #681

```python
class BlockTerminalStateReportedError(Exception):
    """Raised by LocalRunner.run() when the worker stdout envelope's
    final_state field is present.

    Per #681: when a block calls self.transition(CANCELLED|ERROR|SKIPPED)
    from inside its run() method, the worker writes final_state into
    the stdout envelope. LocalRunner detects this and raises this
    exception. DAGScheduler._run_and_finalize catches it and
    finalizes the block to the reported state (instead of treating
    the block as DONE with empty outputs).

    AppBlock uses this when external GUI exits without output.
    """
    final_state: BlockState
    outputs: dict[str, Any]
```

### `execution-engine.PtyTabSpec` / `request_pty_tab` / `notify_block_pty_event` — AIBlock IPC surface
Status: b
Source: `src/scieasy/engine/pty_control.py`
Primary-doc-source: `[ARCHITECTURE: §7 mentions PTY; transport not specified]`
Issue: #TBD-pty-control-http-loopback-document

```python
# b-docs-wins — A4 caught: this uses HTTP LOOPBACK with environment
# variables (SCIEASY_ENGINE_API_URL + SCIEASY_ENGINE_IPC_TOKEN), not
# stdin/stdout or a dedicated IPC channel as ARCH might imply. Spec
# must document the actual transport.

@dataclass
class PtyTabSpec:
    """Specification for a PTY tab to be opened in the GUI.

    Sent from engine to API (via HTTP loopback) when AIBlock needs to
    spawn an interactive agent in a PTY tab.
    """
    tab_id: str
    provider: str                # "claude-code" | "codex"
    project_dir: Path
    user_prompt: str
    timeout_sec: int
    block_execution_id: str
    extra_env: dict[str, str]    # e.g., SCIEASY_AI_BLOCK_RUN_DIR

def request_pty_tab(spec: PtyTabSpec) -> str:
    """Request the API to open a new PTY tab. Returns the tab_id.

    Sends POST to <SCIEASY_ENGINE_API_URL>/api/ai/pty/internal/request-tab
    with Bearer <SCIEASY_ENGINE_IPC_TOKEN> auth.

    Raises:
        RuntimeError: if env vars unset or HTTP request fails.
    """

def notify_block_pty_event(
    tab_id: str,
    event: str,                  # "opened" | "closed" | "completed"
    payload: dict | None = None,
) -> None:
    """Notify the API of a PTY tab lifecycle event.

    Sends POST to <SCIEASY_ENGINE_API_URL>/api/ai/pty/internal/notify
    with Bearer auth. Used by AIBlock to inform the API when the
    agent completes or fails.
    """
```

### `execution-engine.engine.lineage_recorder shim` — scheduled removal
Status: d
Source: `src/scieasy/engine/lineage_recorder.py`
Primary-doc-source: `[CODE: re-export shim — scheduled removal 2026-11-15]`
Issue: #TBD-lineage-recorder-shim-removal

```python
# d-remove — compat shim that re-exports LineageRecorder from the
# canonical location src/scieasy/core/lineage/recorder.py. Scheduled
# removal 2026-11-15 per ADR-038 cascade. SSOT documents the
# deprecation for users who still import from the old path.

# Current contents:
from scieasy.core.lineage.recorder import LineageRecorder    # noqa: F401
# DEPRECATED: import LineageRecorder from scieasy.core.lineage.recorder instead.
# This shim will be removed 2026-11-15.
```

### `execution-engine.scheduler-responsibility-breadth` — cross-cutting B (Codex M03 finding)
Status: b
Source: `src/scieasy/engine/scheduler.py:L1-L1`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §6.1`
Issue: #TBD-scheduler-responsibility-narrowing

```python
# b-code-change — Codex M03 R2 reconciliation finding (also flagged
# by A-diff). DAGScheduler aggregates:
#   1. Event emission (BLOCK_*, WORKFLOW_*)
#   2. Block version stamping (fallback when BlockRegistry lacks version)
#   3. PTY interaction bridging (AIBlock path)
#   4. Lineage write driving (calling LineageRecorder)
#
# These are 4 distinct concerns merged into one class. Architectural
# anti-pattern per CLAUDE.md §7.3 "narrow module responsibility".
# Recommend extracting:
#   - Lineage driving → LineageRecorder subscribes to events directly
#     (already partially done via subscribe pattern)
#   - PTY interaction → separate PtyBridge class
#   - Version stamping → BlockRegistry responsibility
#
# Sub-label b-code-change because the fix is code-side refactoring,
# not docs update. SSOT establishes the principle.
```

---

## END OF PASS 1

**Pass 1 complete**: modules 1-7 with full d-class signatures (~120 entries detailed).

**Pass 2 will add**:
- §8 lineage-db (12 entries)
- §9 rest-api (~30 entries)
- §10 ws-sse-protocol (~10 entries)
- §11 mcp-tools (~30 entries)
- §12 versioning-git (~12 entries)
- §13 agent-provisioning (~12 entries)
- Cross-cutting C-class entries (2 from Codex)
- Appendix A: aggregate count
- Appendix B: open issue placeholders
- Appendix C: cross-cascade reconciliation summary
- Appendix D: Phase 7 audit attention

Pass 2 will replace the placeholder sections below.

---

## Pass 2 placeholders (to be replaced)

## 8. lineage-db

**Module preamble** (from Codex M01 history-layer sub): Dual-history architecture per ADR-038/039 — git tracks source (workflow YAML, custom blocks, notes), lineage.db tracks every workflow run with full block executions, params, I/O. Join key: `runs.workflow_git_commit`. 4 normalized SQLite tables (WAL mode), recorded via EventBus-subscribed `LineageRecorder`. A-class principle: stable, well-aligned.

### `lineage-db.runs` — workflow execution table
Status: a
Source: `src/scieasy/core/lineage/store.py:L1-L1`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.4`
Supplementary-doc-source: ADR-038 §3.1

```sql
CREATE TABLE runs (
    run_id                  TEXT PRIMARY KEY,         -- UUIDv4
    workflow_id             TEXT NOT NULL,            -- logical name e.g. "image_pipeline"
    workflow_git_commit     TEXT,                     -- SHA at run start (NULL if git unavailable)
    workflow_yaml_snapshot  TEXT NOT NULL,            -- full YAML (safety net if git lost)
    workflow_dirty          INTEGER NOT NULL,         -- 0/1 worktree-clean flag at run start
    started_at              TEXT NOT NULL,            -- ISO 8601
    finished_at             TEXT,                     -- ISO 8601 OR NULL if running/crashed
    status                  TEXT NOT NULL,            -- running | completed | failed | cancelled
    environment_snapshot    TEXT NOT NULL,            -- JSON: full uv pip freeze (per §6.7)
    triggered_by            TEXT NOT NULL,            -- user | ai_block | execute_from
    parent_run_id           TEXT REFERENCES runs(run_id),    -- for re-runs
    execute_from_block_id   TEXT,                     -- which block "Run from here" started at
    user_notes              TEXT                      -- free-form notes
);
```

### `lineage-db.block_executions` — per-block-per-run record
Status: a
Source: `src/scieasy/core/lineage/store.py:L1-L1`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.4`
Supplementary-doc-source: ADR-038 §3.1

```sql
CREATE TABLE block_executions (
    block_execution_id      TEXT PRIMARY KEY,         -- UUIDv4
    run_id                  TEXT NOT NULL REFERENCES runs(run_id),
    block_id                TEXT NOT NULL,            -- DAG node id (e.g., "cellpose_001")
    block_type              TEXT NOT NULL,            -- class name (e.g., "CellposeSegment")
    block_version           TEXT NOT NULL,            -- auto-injected via importlib.metadata
    block_config_resolved   TEXT NOT NULL,            -- JSON, post-template-expansion params
    started_at              TEXT NOT NULL,
    finished_at             TEXT,
    duration_ms             INTEGER,
    termination             TEXT NOT NULL,            -- completed | error | cancelled | skipped
    termination_detail      TEXT,                     -- error message / skip reason / etc.
    UNIQUE (run_id, block_id)
);
```

### `lineage-db.data_objects` — DataObject identity catalog
Status: a
Source: `src/scieasy/core/lineage/store.py:L1-L1`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.4`
Supplementary-doc-source: ADR-038 §3.1

```sql
CREATE TABLE data_objects (
    object_id               TEXT PRIMARY KEY,         -- FrameworkMeta UUID
    type_name               TEXT NOT NULL,            -- leaf class name
    backend                 TEXT,                     -- "zarr" | "arrow" | "filesystem" | "composite"
    storage_path            TEXT,                     -- best-effort; may be stale after overwrite
    size_bytes              INTEGER,                  -- NEVER populated by recorder today (always NULL)
    mtime_at_write          TEXT,                     -- NEVER populated by recorder today (always NULL)
    created_at              TEXT NOT NULL,
    wire_payload            TEXT NOT NULL,            -- full wire-format JSON (reference-only per ADR-031)
    derived_from            TEXT REFERENCES data_objects(object_id),    -- provenance link
    produced_by_execution   TEXT REFERENCES block_executions(block_execution_id)
);
```

### `lineage-db.block_io` — port-to-DataObject edge per execution
Status: a
Source: `src/scieasy/core/lineage/store.py:L1-L1`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.4`
Supplementary-doc-source: ADR-038 §3.1

```sql
CREATE TABLE block_io (
    block_execution_id      TEXT NOT NULL REFERENCES block_executions(block_execution_id),
    direction               TEXT NOT NULL,            -- 'input' | 'output'
    port_name               TEXT NOT NULL,
    object_id               TEXT NOT NULL REFERENCES data_objects(object_id),
    position                INTEGER NOT NULL,         -- index within port (Collections unrolled)
    PRIMARY KEY (block_execution_id, direction, port_name, position)
);

-- Collection unrolling: a Collection[Image] with N items produces N
-- block_io rows + N data_objects rows. The _collection wrapper is
-- reconstructed at read time by grouping rows ordered by position.
```

### `lineage-db.LineageStore` — unified store API
Status: a
Source: `src/scieasy/core/lineage/store.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.4`
Supplementary-doc-source: ADR-038 §3.2

```python
class LineageStore:
    """SQLite-backed unified lineage store.

    Connection model:
      - File-backed: per-call connection open + close (Windows
        PermissionError robustness; C5 verified)
      - In-memory (":memory:" path): single persistent connection
    PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON (per-connection).
    """

    def __init__(self, db_path: str | Path | Literal[":memory:"]) -> None: ...

    def put_run(self, record: RunRecord) -> None:
        """Insert a row into runs."""
    def put_block_execution(self, record: BlockExecutionRecord) -> None:
        """Insert a row into block_executions."""
    def put_data_object(self, row: DataObjectRow) -> None:
        """Insert OR ignore into data_objects (object_id is PK)."""
    def put_block_io(self, row: BlockIORow) -> None:
        """Insert into block_io."""

    def get_run(self, run_id: str) -> RunRecord | None: ...
    def get_runs_by_workflow(self, workflow_id: str) -> list[RunRecord]: ...
    def get_block_executions(self, run_id: str) -> list[BlockExecutionRecord]: ...
    def get_block_io(self, block_execution_id: str) -> dict[str, list[DataObjectRow]]:
        """Return {direction: {port_name: [DataObjectRow, ...]}} (Collections re-grouped by position)."""

    def update_run_status(
        self, run_id: str, status: str, finished_at: str | None
    ) -> None: ...
    def update_block_execution_termination(
        self, block_execution_id: str, termination: str,
        termination_detail: str | None, finished_at: str, duration_ms: int,
    ) -> None: ...

    # Note: NO ancestors() / descendants() methods on LineageStore itself.
    # The MetadataStore shim (d-remove below) has them — to be removed
    # 2026-11-15.
```

### `lineage-db.RunRecord` / `BlockExecutionRecord` / `DataObjectRow` / `BlockIORow` — typed dataclasses
Status: a
Source: `src/scieasy/core/lineage/records.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.4`

```python
@dataclass
class RunRecord:
    """Mirrors the runs table columns."""
    run_id: str
    workflow_id: str
    workflow_git_commit: str | None
    workflow_yaml_snapshot: str
    workflow_dirty: bool
    started_at: str
    finished_at: str | None
    status: str
    environment_snapshot: str          # JSON-encoded EnvironmentSnapshot
    triggered_by: str
    parent_run_id: str | None = None
    execute_from_block_id: str | None = None
    user_notes: str | None = None

@dataclass
class BlockExecutionRecord:
    """Mirrors block_executions columns."""
    block_execution_id: str
    run_id: str
    block_id: str
    block_type: str
    block_version: str
    block_config_resolved: str         # JSON-encoded dict
    started_at: str
    finished_at: str | None = None
    duration_ms: int | None = None
    termination: str | None = None
    termination_detail: str | None = None

@dataclass
class DataObjectRow:
    """Mirrors data_objects columns."""
    object_id: str
    type_name: str
    backend: str | None
    storage_path: str | None
    size_bytes: int | None             # always None (recorder doesn't populate)
    mtime_at_write: str | None         # always None
    created_at: str
    wire_payload: str                  # JSON-encoded wire-format
    derived_from: str | None = None
    produced_by_execution: str | None = None

@dataclass
class BlockIORow:
    """Mirrors block_io columns."""
    block_execution_id: str
    direction: str                     # 'input' | 'output'
    port_name: str
    object_id: str
    position: int
```

### `lineage-db.EnvironmentSnapshot` — Python environment capture
Status: a
Source: `src/scieasy/core/lineage/env.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §6.7`
Supplementary-doc-source: ADR-038 §3.4

```python
@dataclass
class EnvironmentSnapshot:
    """Captured at run start, serialized as JSON into runs.
    environment_snapshot column.

    Per ADR-038 §3.4: scope is full `uv pip freeze` (NOT per-block
    key_dependencies as pre-ADR-038 drafts implied). Storage cost:
    5-20 KB per run, negligible.
    """
    python_version: str                # "3.13.x"
    platform: str                      # "linux-x86_64"
    full_freeze: str                   # full `uv pip freeze` output
    key_packages: dict[str, str]       # derived from full_freeze for fast equality check
    conda_env: str | None = None       # optional conda env export
```

### `lineage-db.LineageRecorder` — event-driven lineage writer
Status: a
Source: `src/scieasy/core/lineage/recorder.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.4, §5.3` (EventBus subscription matrix)
Supplementary-doc-source: ADR-038 §3.3

```python
class LineageRecorder:
    """Subscribes to engine EventBus + writes to LineageStore.

    Subscriptions: BLOCK_DONE, BLOCK_ERROR, BLOCK_CANCELLED,
    BLOCK_SKIPPED (per ARCH §6.1 matrix). Per terminal event,
    writes block_executions row + data_objects + block_io rows
    for outputs.

    Idempotent dispose() — must be called to prevent fan-out
    accumulation if recorder is reused across runs (per C5 finding).
    """

    def __init__(
        self,
        store: LineageStore,
        event_bus: EventBus,
        block_registry: BlockRegistry,
    ) -> None: ...

    async def _on_terminal(self, event: EngineEvent) -> None:
        """Async EventBus handler. Synchronously calls store.put_*
        methods (sync I/O inside async handler — acceptable per
        ARCH §6.1 short-handler policy)."""

    def dispose(self) -> None:
        """Unsubscribe from EventBus. Idempotent. Must be called
        between runs OR at engine shutdown."""

    # Collection unrolling helper (private):
    def _wire_items_for_port(self, value: dict) -> list[dict]:
        """Detect _collection wrapper; if present, flatten items[]
        into per-position rows. Otherwise return [value] as a
        single-item list."""

    def _extract_type_name(self, wire_payload: dict) -> str:
        """Read metadata.type_chain[-1] (leaf = most-specific class
        name). Per hotfix #995, short-circuits for Collection wrapper
        via kind='collection' + item_type fields."""
```

### `lineage-db.RunContext` / `get_run_context` / `set_run_context` / `reset_run_context` — run-scoped context
Status: d
Source: `src/scieasy/core/lineage/context.py`
Primary-doc-source: `[ARCHITECTURE: not documented]`
Issue: #TBD-runcontext-document

```python
# d-document — A5 audit confirmed: all 4 symbols exported in
# scieasy/core/lineage/__init__.__all__. M2 incorrectly classified
# as d-private. Public surface.

@dataclass
class RunContext:
    """Per-run context propagated through engine to recorder.

    Set at run start (DAGScheduler.execute()), reset at run end.
    Accessed by LineageRecorder when stamping block_execution rows.
    """
    run_id: str
    workflow_id: str
    workflow_git_commit: str | None
    triggered_by: str
    started_at: str

# Module-level context var (per-thread/coroutine-safe via contextvars):
_run_context_var: ContextVar[RunContext | None] = ContextVar(
    "scieasy_run_context", default=None,
)

def get_run_context() -> RunContext | None:
    """Return current RunContext, or None if not set."""

def set_run_context(ctx: RunContext) -> None:
    """Set RunContext for current async context."""

def reset_run_context() -> None:
    """Clear RunContext for current async context."""
```

### `lineage-db.render_methods_markdown` — methods-section export
Status: d
Source: `src/scieasy/core/lineage/methods_export.py`
Primary-doc-source: `[ARCHITECTURE: §4.4 concept only]`
Issue: #TBD-render-methods-markdown-document

```python
# d-document — A5 audit: not in __all__ but is the canonical methods-
# export function. Reachable only via direct submodule import.

def render_methods_markdown(
    run_id: str,
    lineage_store: LineageStore,
) -> str:
    """Render a run as a publication-ready "Methods" section.

    Reads runs + block_executions + data_objects + block_io for the
    given run_id. Produces structured markdown enumerating:
      - Workflow + git commit + environment summary
      - Each block: name, version, config (with sensitive fields
        redacted), inputs + outputs (type, shape if Array, source
        path)
      - Lineage links (where outputs of block N feed into block M)

    Used by:
      - GET /api/runs/{run_id}/methods REST endpoint
      - MCP get_lineage tool's methods_export option
      - GUI Lineage tab "Export methods" action

    Args:
        run_id: target run.
        lineage_store: source store.

    Returns:
        Markdown string. Empty string if run_id not found.
    """
```

### `lineage-db.MetadataStore` — pre-ADR-038 compat shim
Status: d
Source: `src/scieasy/core/metadata_store.py`
Primary-doc-source: `[CODE: scheduled removal 2026-11-15]`
Issue: #TBD-metadata-store-shim-removal

```python
# d-remove — pre-ADR-038 unified-lineage compat shim. Scheduled
# removal 2026-11-15 per ADR-038 cascade. SSOT documents the
# deprecation:

class MetadataStore:
    """DEPRECATED post-ADR-038. Pre-ADR-038 metadata.db has been
    collapsed into the unified lineage.db.

    All writes here are NO-OPS. Reads delegate to LineageStore.

    Methods ancestors() / descendants() that pre-ADR-038 callers
    relied on are still available here (graceful degrade) but should
    be migrated to direct LineageStore queries.

    Removal date: 2026-11-15.
    """
    def put(self, *args, **kwargs) -> None:
        """NO-OP. Pre-ADR-038 metadata.db writes are now done via
        LineageRecorder + LineageStore.put_data_object."""

    def put_wire(self, *args, **kwargs) -> None:
        """NO-OP. Same reason as put()."""

    def get(self, object_id: str) -> DataObject | None:
        """Delegates to LineageStore + reconstructs DataObject from
        wire_payload."""

    def get_wire(self, object_id: str) -> dict | None:
        """Delegates to LineageStore.get_data_object().wire_payload."""

    def ancestors(self, object_id: str) -> list[dict]:
        """Walk data_objects.derived_from links upward; return
        list of dicts (each {object_id, type_name, ...})."""

    def descendants(self, object_id: str) -> list[dict]:
        """Walk forward from object_id via derived_from."""

    def list_by_type(self, type_name: str) -> list[dict]: ...
    def list_by_workflow(self, workflow_id: str) -> list[dict]: ...
    def delete(self, object_id: str) -> None: ...

    def close(self) -> None:
        """NO-OP. Connection lifecycle managed by LineageStore."""
```

## 9. rest-api

**Module preamble** (from Codex M05 + M08): REST workflow / block / project schemas are A-class stable. **Cross-layer coupling C-class** (Codex M05 NEW finding folded into cross-cutting at end — API routes triggering runtime state mutations like `refresh_block_registry` after git branch switch). CLI install / mcp-bridge contracts A. Scaffold conformance verification B (needs explicit normative acceptance rules per ADR-026). C6 audit found 42 routes initially; A6 re-counted **61** (includes aliases, IPC routes, ADR-036 file/template routes).

### `rest-api.workflow-routes` — `/api/workflows/*` (WF-001..WF-014, 14 routes)
Status: a
Source: `src/scieasy/api/routes/workflows.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §8.2`

```http
# CRUD + lifecycle (per ARCH §8.2):
GET    /api/workflows                                         # list workflows
POST   /api/workflows                                         # create
GET    /api/workflows/{id}                                    # get definition
PUT    /api/workflows/{id}                                    # full update
PATCH  /api/workflows/{id}                                    # partial update
DELETE /api/workflows/{id}
POST   /api/workflows/{id}/execute                            # start
POST   /api/workflows/{id}/pause                              # pause at current block
POST   /api/workflows/{id}/resume                             # resume from checkpoint
POST   /api/workflows/{id}/cancel                             # cancel entire workflow
POST   /api/workflows/{id}/blocks/{block_id}/cancel           # cancel single block
POST   /api/workflows/{id}/execute-from                       # ADR-023 "Run from here"
POST   /api/workflows/import-path                             # untyped dict body
POST   /api/workflows/export-path                             # untyped dict body
```

### `rest-api.block-routes` — `/api/blocks/*` (BLK-001..BLK-T1, 5 routes)
Status: a
Source: `src/scieasy/api/routes/blocks.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §8.2`
Supplementary-doc-source: ADR-036 §3.12 (BLK-004 + BLK-T1)

```http
GET    /api/blocks                                            # list all (with search/filter)
GET    /api/blocks/{type}                                     # get block schema
POST   /api/blocks/validate-connection                        # validate edge (see entry below)
POST   /api/blocks/template                                   # scaffold custom block (ADR-036 §3.12)
GET    /api/blocks/template                                   # fetch template (BLK-T1)
```

### `rest-api.validate_connection` — uses static spec, ignores effective ports
Status: b
Source: `src/scieasy/api/routes/blocks.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.2`
Issue: #889

```python
# b-code-wins — A6 audit confirmed: validate_connection ignores
# get_effective_input_ports / get_effective_output_ports. Validates
# against the STATIC class-level port lists only. For variadic /
# dynamic-port blocks, this gives WRONG answers (the per-instance
# effective ports are the real contract).
#
# Fix is code-side: call source.get_effective_output_ports() and
# target.get_effective_input_ports() before walking the type check.
# Until fixed, frontend ReactFlow edge-validation may flag legitimate
# variadic connections as invalid.
@router.post("/api/blocks/validate-connection")
async def validate_connection(req: ConnectionValidationRequest) -> ConnectionValidationResponse:
    """Validate a proposed source-port → target-port edge.

    Returns {valid: bool, message: str}. message describes the
    reason on failure.
    """
```

### `rest-api.project-routes` — `/api/projects/*` (PROJ-001..PROJ-007, 7 routes)
Status: a
Source: `src/scieasy/api/routes/projects.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §8.2`
Supplementary-doc-source: ADR-023 Addendum 1

```http
POST   /api/projects                                          # create project workspace
GET    /api/projects                                          # list known projects
GET    /api/projects/{id}                                     # get project details
PUT    /api/projects/{id}                                     # update metadata
DELETE /api/projects/{id}                                     # delete project
POST   /api/projects/{id}/open                                # open as active project
POST   /api/projects/{id}/close                               # close active project
```

### `rest-api.data-routes` — `/api/data/*` (DATA-001..DATA-003, 3 routes)
Status: a
Source: `src/scieasy/api/routes/data.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §8.2`

```http
POST   /api/data/upload                                       # upload data files
GET    /api/data/{ref}                                        # get data object metadata
GET    /api/data/{ref}/preview                                # type-appropriate preview (ADR-023 Add 1)
```

### `rest-api.filesystem-routes` — `/api/fs/*` (FS-001..FS-004, 4 routes)
Status: a
Source: `src/scieasy/api/routes/filesystem.py`
Primary-doc-source: `[ARCHITECTURE: not enumerated — A6 caught]`
Issue: #TBD-filesystem-routes-arch-document

```http
GET    /api/fs/tree                                           # directory tree under project
GET    /api/fs/file                                           # file content read
POST   /api/fs/file                                           # file content write
DELETE /api/fs/file                                           # file delete
# d-document — public surface used by project tree UI; needs ARCH §8.2 entry.
# Route ordering note: this router MUST mount before projects router so
# /api/fs/tree doesn't get swallowed by /api/projects/{project_id:path}.
```

### `rest-api.ai-route` — `GET /api/ai/status` (AI-001)
Status: a
Source: `src/scieasy/api/routes/ai.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §8.2`

```http
GET    /api/ai/status                                         # provider availability + login state
# Returns: {provider: str, version: str, logged_in: bool, ...}
```

### `rest-api.lint-route` — `POST /api/lint/python` (LINT-001)
Status: a
Source: `src/scieasy/api/routes/lint.py`
Primary-doc-source: `[ARCHITECTURE: not enumerated — A6 caught]`
Issue: #TBD-lint-route-arch-document

```http
POST   /api/lint/python                                       # ruff-based lint of code text
# Body: {code: str, filename: str}
# Returns: {markers: list[LintMarker]} where each marker is
#   {line: int, column: int, severity: str, message: str, code: str}
# Used by Monaco editor for live lint feedback per ADR-036.
# d-document — public surface; needs ARCH §8.2 entry.
```

### `rest-api.configure_logging` — `NotImplementedError` stub
Status: c
Source: `[CODE: stub]`
Primary-doc-source: `[ARCHITECTURE: not documented]`
Issue: #827

```python
# c-impl — function exists as a NotImplementedError stub. Per #827,
# should be implemented per its documented intent (server-side logging
# config update). SSOT establishes the contract:

def configure_logging(
    level: str = "INFO",
    handlers: list[dict] | None = None,
) -> None:
    """Reconfigure server-side logging.

    Args:
        level: logging level (DEBUG / INFO / WARNING / ERROR).
        handlers: optional list of handler configs. Each handler is
            a dict matching the logging module's dictConfig schema.

    Effect: applies the new config to root logger and SciEasy
    package loggers via logging.config.dictConfig.
    """
    raise NotImplementedError    # c-impl per #827
```

### `rest-api.runs-routes` — `/api/runs/*` (RUNS-001..RUNS-005, 5 routes)
Status: b
Source: `src/scieasy/api/routes/runs.py:L1-L1`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §8.2`
Issue: #TBD-runs-detail-wire-shape-document

```http
GET    /api/runs                                              # list runs (RUNS-001, a)
GET    /api/runs/{run_id}                                     # run detail (RUNS-005, b)
GET    /api/runs/{run_id}/methods                             # methods.md export (RUNS-002, a)
POST   /api/runs/{run_id}/rerun                               # re-run with same params (RUNS-003, a)
DELETE /api/runs/{run_id}                                     # delete run record (RUNS-004, a)
```

```python
# RUNS-005 (b-docs-wins): returns untyped dict pulled directly from
# lineage.db rows. Frontend LineageRunDetail type expects typed shape
# (see frontend FE-BE drift entries below). Fix: wrap backend response
# in Pydantic LineageRunDetail.
```

### `rest-api.git-routes` — `/api/git/*` (GIT-001..GIT-018, 18 routes)
Status: a
Source: `src/scieasy/api/routes/git.py`
Primary-doc-source: `[ARCHITECTURE: §4.6 design intent; route table not enumerated]`
Issue: #TBD-git-routes-arch-document

```http
# 18 routes — d-document at module level; SSOT enumerates verbatim:
GET    /api/git/status                                        # working tree status
GET    /api/git/log                                           # commit history (filtered per ADR-039 prefix)
POST   /api/git/commit                                        # create commit (manual milestone)
GET    /api/git/diff                                          # diff of working tree or commit range
POST   /api/git/restore                                       # restore file to ref version
GET    /api/git/branches                                      # list branches
POST   /api/git/branches                                      # create branch
POST   /api/git/branches/switch                               # switch branch (triggers refresh_block_registry — see cross-layer C entry)
DELETE /api/git/branches/{name}
POST   /api/git/merge                                         # initiate merge
POST   /api/git/merge/stage                                   # stage merge resolution file
POST   /api/git/merge/complete
POST   /api/git/merge/abort
POST   /api/git/cherry-pick
GET    /api/git/stash                                         # list stashes
POST   /api/git/stash                                         # save stash
POST   /api/git/stash/apply
DELETE /api/git/stash/{ref}                                   # drop stash
```

### `rest-api.pydantic-schemas` — request/response models (~30 active + 2 dead)
Status: d
Source: `src/scieasy/api/schemas.py:L1-L1`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §8.2`
Issue: #TBD-cancel-request-schemas-remove

```python
# All active schemas (used by routes) — sample (full list ~28):
class WorkflowCreate(BaseModel):
    name: str
    description: str = ""
    yaml_content: str    # or via path
class WorkflowResponse(BaseModel):
    id: str
    name: str
    yaml_content: str
    last_modified: datetime
class BlockSummary(BaseModel):
    name: str
    description: str
    version: str
    category: str
    subcategory: str
    package_name: str
class BlockPortResponse(BaseModel):
    name: str
    accepted_types: list[str]
    required: bool
    description: str
class ConnectionValidationRequest(BaseModel):
    source_block_type: str
    source_port_name: str
    target_block_type: str
    target_port_name: str
class ConnectionValidationResponse(BaseModel):
    valid: bool
    message: str = ""
class ProjectResponse(BaseModel):
    id: str
    name: str
    path: str
    last_opened: datetime | None
    workflow_count: int
class TypeHierarchyEntry(BaseModel):
    name: str
    parent: str | None
    base_color: str
    ui_ring_color: str | None = None    # NEVER POPULATED — see FE-BE drift entry
# ... ~20 more

# DEAD weight (no route uses these):
class CancelBlockRequest(BaseModel):    # d-remove — never imported by any route
    workflow_id: str
    block_id: str
class CancelWorkflowRequest(BaseModel): # d-remove — never imported by any route
    workflow_id: str
```

### `rest-api.frontend-DynamicPortsConfig` — TS-only field drift
Status: b
Source: `frontend/src/types/api.ts`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §5.4`
Issue: #TBD-dynamic-ports-config-input-port-mapping

```typescript
// b-docs-wins — TS type DynamicPortsConfig adds an input_port_mapping
// field that NO BACKEND BLOCK emits. ARCH §5.4 describes only
// output_port_mapping (per ADR-028 Add 1). Fix: backend adds the
// field (if input narrowing is a real feature) OR frontend drops it
// (if speculative). Decision per ARCH §5.4 authority: drop from TS.
export interface DynamicPortsConfig {
  source_config_key: string;
  output_port_mapping: Record<string, Record<string, string[]>>;
  input_port_mapping?: Record<string, Record<string, string[]>>;   // NEVER EMITTED — drop
}
```

### `rest-api.frontend-TypeHierarchyEntry.ui_ring_color` — TS field never populated
Status: b
Source: `frontend/src/types/api.ts`
Primary-doc-source: `[CODE: backend never populates the field]`
Issue: #TBD-type-hierarchy-ui-ring-color

```typescript
// b-code-wins — TS declares ui_ring_color (per ARCH §9.6 type-color
// system); backend never sets it (returns null always). Fix: either
// backend populates (read from class ClassVar _ui_ring_color) OR
// frontend drops field. Backend population is more consistent with
// ARCH §9.6 — recommend code-side fix.
export interface TypeHierarchyEntry {
  name: string;
  parent: string | null;
  base_color: string;
  ui_ring_color: string | null;    // NEVER POPULATED by backend
}
```

### `rest-api.frontend-LineageRunDetail` — multi-field FE-BE drift
Status: b
Source: `frontend/src/types/lineage.ts`
Primary-doc-source: `[CODE: backend returns raw dict]`
Issue: #TBD-lineage-rundetail-fe-be-drift

```typescript
// b-code-wins — A6 caught 3 mismatches in this single TS interface:
//   1. TS field `blocks` vs backend column `block_executions` (rename)
//   2. TS expects `environment_snapshot` field — backend doesn't emit
//   3. TS expects `workflow_yaml_snapshot` field — backend doesn't emit
// Code is current truth (RUNS-005 returns raw lineage.db dict).
// Fix: backend RUNS-005 endpoint wraps in proper Pydantic
// LineageRunDetail model OR frontend drops missing fields.
export interface LineageRunDetail {
  run: LineageRun;
  blocks: LineageBlockExecution[];                  // backend: "block_executions"
  environment_snapshot: EnvironmentSnapshot;        // MISSING from backend
  workflow_yaml_snapshot: string;                   // MISSING from backend
}
```

### `rest-api.frontend-LineageRerunResponse.new_run_id` — TS field missing from backend
Status: b
Source: `frontend/src/types/lineage.ts`
Primary-doc-source: `[CODE: backend returns {rerun_of, workflow_id, execute_from_block_id, result}]`
Issue: #TBD-lineage-rerun-response-new-run-id

```typescript
// b-code-wins — TS expects new_run_id; backend POST /api/runs/{run_id}/rerun
// returns {rerun_of, workflow_id, execute_from_block_id, result} — no
// new_run_id. Fix: frontend reads result.run_id OR backend adds top-level
// new_run_id. Backend-add is more ergonomic (frontend doesn't need to
// drill into result).
export interface LineageRerunResponse {
  rerun_of: string;
  workflow_id: string;
  execute_from_block_id: string | null;
  result: object;
  new_run_id: string;    // MISSING from backend response
}
```

### `rest-api.cli-commands` — Typer command surface (9 commands)
Status: a
Source: `src/scieasy/cli/main.py:L1-L1`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §9.11`
Supplementary-doc-source: ADR-040 (install + mcp-bridge)

```bash
# 9 Typer commands (verbatim per code):
scieasy gui [--port PORT] [--no-browser]                # launch GUI in browser (ADR-024)
scieasy serve [--port PORT]                             # headless API server
scieasy validate <path/to/workflow.yaml>                # offline workflow validation
scieasy run <workflow_id> [--from-block BLOCK_ID]       # CLI run a workflow
scieasy init <name>                                     # scaffold a new project
scieasy install [--target {claude,codex,all}] [--scope {user,project}]
                [--skill] [--remove] [--all]            # ADR-040 install MCP+skill
scieasy mcp-bridge                                      # stdio MCP bridge subcommand
scieasy init-block-package <name>                       # ADR-026 SDK scaffolding
scieasy blocks                                          # list registered blocks (debug)
```

### `rest-api.ApiRuntime` — internal runtime class
Status: d
Source: `src/scieasy/api/runtime.py`
Primary-doc-source: `[ARCHITECTURE: §8 not enumerated]`
Issue: #TBD-apiruntime-document

```python
class ApiRuntime:
    """Load-bearing internal class that orchestrates project lifecycle
    + runtime state for the API process.

    Sub-label d-document: held by FastAPI dependency injection; every
    route uses it indirectly via get_runtime(). Public surface (one
    instance per process). ARCH §8 doesn't enumerate. SSOT establishes.
    """

    def __init__(self) -> None: ...

    # --- Project lifecycle ---
    def create_project(
        self, name: str, description: str = "", parent_path: Path | None = None,
    ) -> KnownProject: ...
    def open_project(self, project_id_or_path: str) -> KnownProject: ...
    def close_project(self) -> None: ...

    # --- Registry refresh ---
    def refresh_block_registry(self) -> None:
        """Re-scan project + user-global block directories. Called
        manually via Reload button AND automatically on git branch
        switch (cross-layer coupling — see cross-cutting C entry)."""

    # --- Lineage + checkpoint ---
    def _init_lineage_store(self, path: Path) -> None:
        """Initialize LineageStore at <project>/.scieasy/lineage.db."""
    def _init_metadata_store(self, path: Path) -> None:
        """DEPRECATED — pre-ADR-038 shim. NO-OP."""

    # --- MCP bridge ---
    def _publish_mcp_port(self, port: int) -> None:
        """Write <project>/.scieasy/mcp.json with bridge config so
        agents can discover the MCP server."""

    # --- State accessors ---
    @property
    def active_project(self) -> KnownProject | None: ...
    @property
    def known_projects(self) -> dict[str, KnownProject]: ...
    @property
    def block_registry(self) -> BlockRegistry: ...
    @property
    def type_registry(self) -> TypeRegistry: ...
    @property
    def lineage_store(self) -> LineageStore | None: ...
    @property
    def git_engine(self) -> GitEngine | None: ...

    def save_workflow(self, workflow_id: str, yaml_content: str) -> WorkflowResponse: ...
    def load_workflow(self, workflow_id: str) -> WorkflowResponse: ...
    def _save_known_projects(self) -> None:
        """Persist known_projects to ~/.scieasy/known_projects.json."""
```

### `rest-api.SPAStaticFiles` / `create_app` / `deps.py` — API infrastructure
Status: a
Source: `src/scieasy/api/{app,spa,deps}.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §9.11`
Supplementary-doc-source: ADR-024

```python
class SPAStaticFiles(StaticFiles):
    """Custom StaticFiles middleware that serves index.html for any
    path not matching /api/*, /ws, or a real static file. Enables
    client-side routing for deep links per ADR-024."""

def create_app() -> FastAPI:
    """FastAPI factory. Mounts routers in this order:
      1. /api/* routers (workflows, blocks, projects, data, etc.)
      2. /ws WebSocket endpoint
      3. /docs, /openapi.json (FastAPI built-in)
      4. / → SPAStaticFiles (mount LAST so /api/* takes priority)
    Lifespan handler: bootstraps ApiRuntime, scans BlockRegistry,
    starts MCP server (in-process)."""

# deps.py — dependency providers:
def get_block_registry() -> BlockRegistry: ...
def get_type_registry() -> TypeRegistry: ...
def get_runtime() -> ApiRuntime: ...
def get_lineage_store() -> LineageStore: ...
def get_git_engine() -> GitEngine: ...
def get_active_project() -> KnownProject:
    """Raises 400 if no active project."""
```

### `rest-api.frontend-zustand-slices` — FE state slices (10 actual vs ARCH 7)
Status: b
Source: `frontend/src/store/*.ts`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §9.10`
Issue: #TBD-zustand-slices-arch-update

```typescript
// b-code-wins — code has 10 slices; ARCH §9.10 lists 7 (including the
// phantom chatSlice from ARCH text — AX caught this in PROJECT_TREE.md
// + ARCH §9.10 references. Phase 7 should re-verify chatSlice
// existence in frontend/src/store/).
//
// Actual 10 slices verified by C6 audit:
const stores = [
  'projectSlice',
  'workflowSlice',
  'executionSlice',
  'uiSlice',
  'previewSlice',
  'paletteSlice',
  'tabSlice',            // not in ARCH §9.10
  'terminalTabsSlice',   // not in ARCH §9.10
  'lineageSlice',        // not in ARCH §9.10
  'gitSlice',            // not in ARCH §9.10
];
// chatSlice claim from ARCH §9.10 — Phase 7 verify against
// frontend/src/store/ directory contents. AX flagged inconsistency.
```

## 10. ws-sse-protocol

**Module preamble** (from Codex M05 sub): WS/SSE frame typing is **stringly-typed today** (B/C — Codex recommends code-change toward stronger Pydantic-based discriminated unions for outbound events). Reverse-coupling to frontend field shapes is a B/C risk (Codex M07: backend pins shapes for frontend compat — "co-evolution interface" rather than pure backend-defines-frontend-consumes per ARCH §2.1). 13 outbound + 5 inbound message types verified (A6 audit) — draft v1's WS inbound names were WRONG (`user_message`/`permission_decision`); CORRECTED in draft v2 to `block_user_marked_done`/`block_user_cancel`.

### `ws-sse-protocol.ws-endpoint` — `/ws`
Status: a
Source: `src/scieasy/api/ws.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §8.3`

```python
@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    """Primary engine→client WebSocket. Bidirectional JSON text frames.

    Server→client: 13 message types (see outbound-messages below).
    Client→server: 5 message types (see inbound-messages below).

    Subscription: handler subscribes to EventBus for the 13 event types
    + bridges to outbound frames. Inbound frames are dispatched to
    matching engine actions (cancel_block / cancel_workflow trigger
    DAGScheduler events).
    """
```

### `ws-sse-protocol.outbound-messages` — server → client (13 types)
Status: a
Source: `src/scieasy/api/ws.py:L1-L1`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §8.3`
Supplementary-doc-source: 5 of 13 types emitted from src/scieasy/api/routes/workflow_watcher.py

```json
// 13 outbound message types, all JSON. "type" field is the discriminator.

// 1. Block state push (engine BLOCK_* events)
{"type": "block_state", "block_id": "...", "state": "running|done|error|paused|cancelled|skipped", "progress": 0.0-1.0, "message": "..."}

// 2. Interactive block waiting for user
{"type": "interactive_prompt", "block_id": "...", "prompt": "...", "app_url": "...|null"}

// 3. Cancellation propagation result (ADR-018)
{"type": "cancel_propagation", "cancelled_block": "...", "skipped_blocks": [{"block_id": "...", "reason": "..."}], "unaffected_blocks": [...]}

// 4. Workflow YAML change detected by file watcher
{"type": "workflow.changed", "workflow_id": "...", "modified_at": "<ISO 8601>"}

// 5. Git HEAD change detected
{"type": "git.head_changed", "old_sha": "...", "new_sha": "...", "branch": "..."}

// 6-8. Run lifecycle
{"type": "run.started",  "run_id": "...", "workflow_id": "...", "started_at": "..."}
{"type": "run.done",     "run_id": "...", "finished_at": "...", "status": "completed"}
{"type": "run.failed",   "run_id": "...", "finished_at": "...", "error": "..."}

// 9. Agent event (ADR-033/035 — claude/codex stream-json forwarded)
{"type": "agent_event", "tab_id": "...", "stream_json_event": { ... }}

// 10-12. PTY tab lifecycle (per ADR-035 §3.5 — BYPASS EventBus, sent
// directly by ai_pty.py broadcaster — see EventBus-bypass entry below)
{"type": "block_pty_opened", "tab_id": "...", "block_execution_id": "..."}
{"type": "block_pty_closed", "tab_id": "...", "block_execution_id": "..."}

// 13. Block reload completion (Tier 1 directory scan finished)
{"type": "blocks.reloaded", "added": [...], "removed": [...], "errors": [...]}
```

### `ws-sse-protocol.inbound-messages` — client → server (5 types, CORRECTED)
Status: a
Source: `src/scieasy/api/routes/ai_pty.py:L1-L1`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §8.3`
Supplementary-doc-source: cancel_block / cancel_workflow handled in src/scieasy/api/ws.py

```json
// 5 inbound message types. CORRECTED in draft v2 from draft v1's wrong names.

// 1. Cancel a single block (ADR-018)
{"type": "cancel_block", "block_id": "...", "workflow_id": "..."}

// 2. Cancel entire workflow (ADR-018)
{"type": "cancel_workflow", "workflow_id": "..."}

// 3. Interactive block user signals completion
{"type": "interactive_complete", "block_id": "..."}

// 4. User clicks "Done" on AIBlock PTY (writes mark_done.json signal)
// CORRECTED from draft v1 "user_message" — code uses this name.
{"type": "block_user_marked_done", "tab_id": "...", "block_execution_id": "..."}

// 5. User clicks "Cancel" on AIBlock PTY (also writes mark_done.json — see aliasing entry)
// CORRECTED from draft v1 "permission_decision" — code uses this name.
{"type": "block_user_cancel", "tab_id": "...", "block_execution_id": "..."}
```

### `ws-sse-protocol.block_user_cancel-aliasing` — same signal as marked_done
Status: b
Source: `src/scieasy/api/routes/ai_pty.py`
Primary-doc-source: `[CODE: full cancel propagation deferred]`
Issue: #TBD-block-user-cancel-mark-done-aliasing-document

```python
# b-docs-wins — block_user_cancel writes the SAME mark_done.json
# signal as block_user_marked_done. They are NOT distinct lifecycle
# events at the AIBlock layer — both indicate "user pressed a
# button; collect whatever outputs exist and finalize the block".
# Full cancel propagation (terminating the PTY subprocess + marking
# the block as CANCELLED instead of DONE) is deferred. SSOT
# establishes the deferral + recommends future split: block_user_cancel
# should write a DIFFERENT signal (signals/cancel_requested.json)
# that triggers true cancellation.
```

### `ws-sse-protocol.ai-pty-endpoint` — `/api/ai/pty/{tab_id}` JSON text frames
Status: a
Source: `src/scieasy/api/routes/ai_pty.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §8.3`
Supplementary-doc-source: ADR-034

```python
@app.websocket("/api/ai/pty/{tab_id}")
async def ai_pty_endpoint(websocket: WebSocket, tab_id: str) -> None:
    """PTY WebSocket for embedded claude / codex CLI agents.

    Bidirectional JSON text frames (NOT binary — single-byte
    overhead but easier debugging per ADR-034 §4.3).

    Outbound frames:
      {"kind": "stdout", "data": "<utf-8 bytes>"}
      {"kind": "exit", "code": <int>}
    Inbound frames:
      {"kind": "stdin", "data": "<utf-8 bytes>"}
      {"kind": "resize", "rows": <int>, "cols": <int>}
      {"kind": "signal", "name": "SIGTERM"|"SIGKILL"}
    """
```

### `ws-sse-protocol.pty-ipc-internal-routes` — engine → API HTTP loopback
Status: d
Source: `src/scieasy/api/routes/ai_pty.py`
Primary-doc-source: `[ARCHITECTURE: not enumerated]`
Issue: #TBD-pty-ipc-internal-routes-document

```http
# d-document — internal HTTP routes called by engine.pty_control
# (which runs in the worker subprocess) over loopback to the API
# process. NOT user-facing; auth via Bearer <SCIEASY_ENGINE_IPC_TOKEN>.

POST /api/ai/pty/internal/request-tab
# Body: PtyTabSpec (see execution-engine.PtyTabSpec entry)
# Returns: {tab_id: str}
# Effect: API opens a new PTY tab in the frontend (broadcasts
#   block_pty_opened to /ws) + spawns the agent subprocess

POST /api/ai/pty/internal/notify
# Body: {tab_id: str, event: "opened"|"closed"|"completed", payload: dict}
# Returns: {ok: true}
# Effect: engine notifies API of PTY lifecycle events; API forwards
#   to /ws as block_pty_* messages
```

### `ws-sse-protocol.sse-log-stream` — `GET /api/logs/stream`
Status: a
Source: `src/scieasy/api/sse.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §8.3`

```python
@app.get("/api/logs/stream")
async def sse_log_stream(
    block_id: str | None = None,
    severity: str | None = None,
) -> EventSourceResponse:
    """SSE stream of execution log lines.

    Event shape (text/event-stream):
        event: log
        data: {"ts": "<ISO 8601>", "block_id": "...", "severity": "DEBUG|INFO|WARNING|ERROR", "message": "..."}

    Query params filter the stream:
      - block_id: only logs from this block
      - severity: only this severity or higher
    """
```

### `ws-sse-protocol.event-bus-bypass` — broadcaster pattern (block_pty_* + blocks.reloaded)
Status: d
Source: `src/scieasy/api/routes/ai_pty.py:L1-L1`
Primary-doc-source: `[ARCHITECTURE: architectural inconsistency not documented]`
Issue: #TBD-event-bus-bypass-document

```python
# d-document — 3 outbound message types BYPASS the EventBus and are
# sent directly via the WebSocket broadcaster:
#   - block_pty_opened
#   - block_pty_closed
#   - blocks.reloaded
#
# Architectural inconsistency vs the other 10 outbound types that
# flow EventBus → WS handler → frame. SSOT documents the dual
# routing paths explicitly so future devs know both patterns exist:

class _WSBroadcaster:
    """Direct-send broadcaster used by ai_pty internal routes +
    BlockRegistry.hot_reload. Bypasses EventBus."""

    async def broadcast(self, message: dict) -> None:
        """Send message to all connected /ws clients without
        going through EventBus.emit()."""

# Justification (per code comments): block_pty_* events are tied to a
# specific PTY tab in the frontend; routing through EventBus would
# require adding a tab_id field to EngineEvent + special handling.
# Direct broadcast is simpler. blocks.reloaded is similar — frontend-
# specific UI event with no engine-side subscriber need.
#
# Spec-level acceptance: ARCH §8.3 should add a "Direct broadcast
# bypass" subsection documenting these 3 types.
```

### `ws-sse-protocol.reverse-coupling-to-frontend` — Codex M07 finding
Status: b
Source: `src/scieasy/api/routes/workflow_watcher.py:L1-L1`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §2.1`
Issue: #TBD-ws-frontend-reverse-coupling-document

```python
# b-docs-wins — Codex M07 R2 reconciliation finding:
# > "后端 watcher/WS 协议会直接参考前端 hook 的字段约定，形成
# > '后端为兼容前端而固定消息形状' 的反向约束。前后端契约目前
# > 更像'协同演进接口',而非'后端单向定义、前端被动消费'的纯分层关系"
#
# Evidence: workflow_watcher.py has explicit code comments saying
# "match useGitState hook's field naming for commit_sha". This is
# REVERSE-COUPLING — backend shape pinned by frontend convenience.
#
# This contradicts ARCH §2.1 ("frontend is editor and viewer, not
# the source of truth"). The current contract is genuinely
# "co-evolution interface" rather than backend-defines / frontend-
# consumes.
#
# Fix is doc-side: ARCH §2.1 should add a "co-evolution interfaces"
# section listing the cases where backend shape is intentionally
# pinned to frontend conventions (and the rationale).
```

## 11. mcp-tools

**Module preamble** (from Codex M04): AI propose / runtime validate boundary is A-class principle (well-aligned with ARCH §2.6 — "AI may propose, but runtime validates and executes"). Dual-channel runtime path (UDS loopback bridge subprocess + in-process FastMCP server) creates audit complexity B (Codex recommends docs-fix to explicitly structure the two-channel decision tree). 26 `@mcp.tool` decorators post-ADR-040 FastMCP migration (10 workflow + 5 authoring + 7 inspection + 4 qa). `scaffold_block` widened per ADR-040 §3.2a (input_ports + output_ports + `warnings: list[str]` field). `_registry.py` REMOVED post-FastMCP — tools discovered by decorator.

### `mcp-tools.26-tool-inventory` — `@mcp.tool` decorators across 4 modules
Status: a
Source: `src/scieasy/ai/agent/mcp/tools_{workflow,authoring,inspection,qa}.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §7.2`
Supplementary-doc-source: ADR-040 §3.1, §3.2, §3.2a, ADR-035 §3.5 (finish_ai_block)

```python
# 26 tools, all with Pydantic return models. Write-class tools have
# `next_step: str` field (ADR-040 §3.2). scaffold_block has additional
# `warnings: list[str]` field (ADR-040 §3.2a).

# --- tools_workflow.py (10): ---
@mcp.tool(name="list_blocks")
async def list_blocks() -> ListBlocksResult: ...
@mcp.tool(name="get_block_schema")
async def get_block_schema(block_type: str) -> BlockSchemaResult: ...
@mcp.tool(name="list_types")
async def list_types() -> ListTypesResult: ...
@mcp.tool(name="get_workflow")
async def get_workflow(workflow_id: str) -> GetWorkflowResult: ...
@mcp.tool(name="validate_workflow")
async def validate_workflow(workflow_yaml_or_id: str) -> ValidateWorkflowResult: ...
@mcp.tool(name="write_workflow")
async def write_workflow(workflow_id: str, yaml_content: str) -> WriteWorkflowResult: ...
@mcp.tool(name="run_workflow")
async def run_workflow(workflow_id: str, execute_from_block_id: str | None = None) -> RunWorkflowResult: ...
@mcp.tool(name="cancel_run")
async def cancel_run(run_id: str) -> CancelRunResult: ...
@mcp.tool(name="get_run_status")
async def get_run_status(run_id: str) -> RunStatusResult: ...
@mcp.tool(name="finish_ai_block")
async def finish_ai_block(output_refs: dict[str, str]) -> FinishAIBlockResult: ...

# --- tools_authoring.py (5): ---
@mcp.tool(name="read_block_source")
async def read_block_source(block_type: str) -> ReadBlockSourceResult: ...
@mcp.tool(name="list_block_examples")
async def list_block_examples(block_type: str) -> ListBlockExamplesResult: ...
@mcp.tool(name="scaffold_block")    # widened per ADR-040 §3.2a — see dedicated entry
async def scaffold_block(
    name: str,
    category: str,
    input_ports: dict[str, dict[str, Any]] | None = None,
    output_ports: dict[str, dict[str, Any]] | None = None,
) -> ScaffoldBlockResult: ...
@mcp.tool(name="reload_blocks")
async def reload_blocks() -> ReloadBlocksResult: ...
@mcp.tool(name="run_block_tests")
async def run_block_tests(block_path: str) -> RunBlockTestsResult: ...

# --- tools_inspection.py (7): ---
@mcp.tool(name="get_block_output")
async def get_block_output(run_id: str, node_id: str, port_name: str) -> GetBlockOutputResult: ...
@mcp.tool(name="inspect_data")
async def inspect_data(ref: str) -> InspectDataResult: ...
@mcp.tool(name="preview_data")    # signature is (ref, fmt) — NOT (ref, max_rows, max_dim) per skill body
async def preview_data(ref: str, fmt: str = "auto") -> PreviewDataResult: ...
@mcp.tool(name="get_lineage")
async def get_lineage(ref: str) -> GetLineageResult: ...
@mcp.tool(name="get_block_config")
async def get_block_config(workflow_id: str, node_id: str) -> GetBlockConfigResult: ...
@mcp.tool(name="update_block_config")
async def update_block_config(workflow_id: str, node_id: str, config_patch: dict) -> UpdateBlockConfigResult: ...
@mcp.tool(name="get_block_logs")
async def get_block_logs(run_id: str, node_id: str) -> GetBlockLogsResult: ...

# --- tools_qa.py (4): ---
@mcp.tool(name="search_docs")
async def search_docs(query: str) -> SearchDocsResult: ...
@mcp.tool(name="get_doc")
async def get_doc(path: str) -> GetDocResult: ...
@mcp.tool(name="list_data")
async def list_data() -> ListDataResult: ...
@mcp.tool(name="get_project_info")
async def get_project_info() -> GetProjectInfoResult: ...
```

### `mcp-tools.pydantic-return-models` — per-tool result schemas (26 models)
Status: a
Source: `src/scieasy/ai/agent/mcp/tools_workflow.py:L1-L1`
Primary-doc-source: ADR-040 §3.2
Supplementary-doc-source: defined at top of each tools_*.py module

```python
# Style guide (ADR-040 §3.2): write-class tools have `next_step: str`
# field pointing at the canonical follow-up tool. Read-class tools
# have no next_step.

# Sample models (all 26 follow this pattern):

class ListBlocksResult(BaseModel):
    blocks: list[BlockSummary]    # name, description, version, category

class BlockSchemaResult(BaseModel):
    block_type: str
    description: str
    version: str
    input_ports: list[dict]    # {name, accepted_types, required, description}
    output_ports: list[dict]
    config_schema: dict        # JSON Schema (MRO-merged per ADR-030)

class ValidateWorkflowResult(BaseModel):
    ok: bool
    errors: list[dict]         # [{path, message}, ...] — pydantic-style validation errors
    next_step: str             # e.g., "Call run_workflow once validate returns ok=true"

class WriteWorkflowResult(BaseModel):
    workflow_id: str
    bytes_written: int
    next_step: str             # "Call validate_workflow with the same workflow_id"

class RunWorkflowResult(BaseModel):
    run_id: str
    started_at: datetime
    next_step: str             # "Poll get_run_status until state in {completed, failed, cancelled}"

class RunStatusResult(BaseModel):
    state: str                 # running | completed | failed | cancelled
    block_states: dict[str, str]
    error: str | None = None

class GetBlockOutputResult(BaseModel):
    ref: str                   # opaque ref token for downstream inspect_data / preview_data calls

class InspectDataResult(BaseModel):
    shape: list[int] | None    # for Array
    dtype: str | None
    axes: list[str] | None
    storage_path: str | None
    size_bytes: int | None     # NOT populated by recorder today

class PreviewDataResult(BaseModel):
    fmt: str                   # "thumbnail_png_base64" | "first_rows_json" | "first_chars" | ...
    preview: Any               # type depends on fmt

class GetLineageResult(BaseModel):
    ancestors: list[dict]      # [{object_id, produced_by_block, type_name}, ...]

class ScaffoldBlockResult(BaseModel):    # see dedicated entry below
    block_path: Path
    next_step: str
    warnings: list[str]        # ADR-040 §3.2a — unique to scaffold_block

class FinishAIBlockResult(BaseModel):
    accepted: bool
    next_step: str             # "Workflow will resume; no further action from this PTY tab"

# ... 16 more models per the 26-tool inventory above
```

### `mcp-tools.scaffold_block.widened-signature-and-warnings` — ADR-040 §3.2a
Status: a
Source: `src/scieasy/ai/agent/mcp/tools_authoring.py`
Primary-doc-source: ADR-040 §3.2a

```python
@mcp.tool(name="scaffold_block")
async def scaffold_block(
    name: str,
    category: str,                                     # "process" | "io" | "code" | ...
    input_ports: dict[str, dict[str, Any]] | None = None,
    output_ports: dict[str, dict[str, Any]] | None = None,
) -> ScaffoldBlockResult:
    """Scaffold a new custom block file under <project>/blocks/.

    Widened signature per ADR-040 §3.2a:
      - input_ports: {port_name: {"type": "Image", "required": true, ...}}
      - output_ports: {port_name: {"type": "Mask"}}

    Two soft-validation warnings emitted via warnings field:
      1. If any port type is "DataObject" (the abstract root):
         → warning suggesting a more specific type from list_types()
      2. If any port type is not in TypeRegistry (unregistered):
         → warning suggesting list_types() to find registered types

    See agent-provisioning entry 13 — there is ALSO a PostToolUse
    hook (`hook_enforce_concrete_port_types.py`) that AST-parses the
    written file and re-flags both issues at hook level.
    """

class ScaffoldBlockResult(BaseModel):
    block_path: Path
    next_step: str             # "Edit the file to fill in process_item(); then call reload_blocks"
    warnings: list[str]        # see above 2 soft-validation rules
```

### `mcp-tools.MCPContext` — Protocol gap (declared 3 vs used 7)
Status: b
Source: `src/scieasy/ai/agent/mcp/_context.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §7.2`
Issue: #TBD-mcpcontext-protocol-gap

```python
# b-code-wins — C7 audit caught:
# Only 3 attrs DECLARED in the Protocol; but tools access 4 MORE via
# getattr fallback (which silently returns None on miss). The 4
# undeclared attrs are LOAD-BEARING (used by run_workflow, get_run_status,
# update_block_config, finish_ai_block).
#
# Fix: expand Protocol to 7 attrs OR document the getattr fallback
# pattern explicitly. Recommend EXPAND (Protocol contract should be
# complete).

class MCPContext(Protocol):
    """MCP server context — dependency-injected into every tool.

    Sub-label b-code-wins: code currently declares 3 attrs but uses 7.
    The 4 attrs accessed via getattr fallback are load-bearing.
    SSOT establishes the FULL 7-attr contract; code must catch up to
    declare all 7.
    """
    # Currently declared (3):
    block_registry: BlockRegistry
    type_registry: TypeRegistry
    project_dir: Path

    # MISSING from Protocol but used by tools via getattr (4):
    scheduler: DAGScheduler             # used by run_workflow, cancel_run
    event_bus: EventBus                 # used by get_run_status (for subscribing)
    workflow_runs: dict[str, RunRecord] # used by get_run_status (lookup)
    ai_block_run_dir: Path | None       # used by finish_ai_block (current AI block scope)

# Context lifecycle helpers (these ARE declared and work correctly):
def set_context(ctx: MCPContext) -> None:
    """Install context for the running event loop. Called by MCPServer
    on each tool dispatch."""

def get_context() -> MCPContext:
    """Return current context. Raises RuntimeError if not set."""

def get_optional_context() -> MCPContext | None:
    """Return current context or None (no raise)."""

def _resolve_project_path(target: str) -> Path:
    """Resolve target to an absolute path under project_dir.
    Raises ValueError on path traversal attempt (.. components,
    absolute paths outside project_dir, symlink escape)."""

def _safe_under(root: Path, target: Path) -> bool:
    """Return True iff target.resolve() is under root.resolve()."""

def _resolve_project_root(ctx: MCPContext) -> Path:
    """Return ctx.project_dir, raising if ctx is None or
    project_dir is unset."""
```

### `mcp-tools.MCPServer` — FastMCP wrapper (post-ADR-040)
Status: a
Source: `src/scieasy/ai/agent/mcp/server.py`
Primary-doc-source: ADR-040 §3.1

```python
# Post-ADR-040 thin wrapper around module-level mcp = FastMCP(...).
# All 26 tools discovered by decorator (no _registry.py per ADR-040).

mcp = FastMCP(
    name="scieasy",
    version="0.1.0",
    instructions="<see system_prompt.py>",
)

class MCPServer:
    """Lifecycle wrapper around the FastMCP instance.

    Manages the UDS (POSIX) / TCP-loopback (Windows) socket for the
    standalone bridge subprocess + the in-process FastAPI route mount.
    """
    def __init__(self, mcp: FastMCP, context: MCPContext) -> None: ...

    async def start(self) -> None:
        """Bind socket + start accept loop (standalone bridge mode)."""

    async def stop(self) -> None:
        """Close socket + drain in-flight tool calls."""

    @property
    def port(self) -> int:
        """Return bound port (TCP) or socket path inode (UDS)."""

    async def _handle_client(self, reader, writer) -> None:
        """JSON-RPC 2.0 line-delimited frame loop. Each request
        dispatched to dispatch()."""

    async def dispatch(self, method: str, params: dict) -> Any:
        """Look up tool by method name in FastMCP; await tool with
        params; return result wire-formatted."""
```

### `mcp-tools.StandaloneMCPRuntime` / `make_mcp_runtime` / `start_inprocess_server` / `stop_inprocess_server` — bridge runtime
Status: a
Source: `src/scieasy/ai/agent/mcp/runtime.py`
Primary-doc-source: ADR-040 §3.1

```python
@dataclass
class StandaloneMCPRuntime:
    """Runtime context for the standalone `scieasy mcp-bridge`
    subprocess (used when agents connect from outside the FastAPI
    process).
    """
    block_registry: BlockRegistry
    type_registry: TypeRegistry
    project_dir: Path
    scheduler: DAGScheduler | None = None      # None in standalone — no engine
    event_bus: EventBus | None = None
    workflow_runs: dict = field(default_factory=dict)
    ai_block_run_dir: Path | None = None

def make_mcp_runtime(project_dir: Path) -> StandaloneMCPRuntime:
    """Construct a StandaloneMCPRuntime for the bridge subprocess.
    Boots BlockRegistry + TypeRegistry against project_dir's
    drop-in dirs."""

def default_socket_path() -> Path:
    """POSIX: <project_dir>/.scieasy/mcp.sock
    Windows: %TEMP%/scieasy-mcp-<project-hash>.sock (TCP loopback)."""

async def start_inprocess_server(
    mcp: FastMCP,
    context: MCPContext,
    socket_path: Path | None = None,
) -> MCPServer:
    """Boot MCPServer in-process (same event loop as FastAPI)."""

async def stop_inprocess_server(server: MCPServer) -> None:
    """Stop the in-process server cleanly."""
```

### `mcp-tools.compose_system_prompt` + splice helpers — system prompt assembly
Status: a
Source: `src/scieasy/ai/agent/system_prompt.py`
Primary-doc-source: ADR-040 §3.3, §3.4

```python
# Splice markers for the SKILL.md base body:
_TOOL_CATALOG_BEGIN = "<!-- tool_catalog:begin -->"
_TOOL_CATALOG_END   = "<!-- tool_catalog:end -->"
_PROJECT_CONTEXT_BEGIN = "<!-- project_context:begin -->"
_PROJECT_CONTEXT_END   = "<!-- project_context:end -->"

def compose_system_prompt(project_dir: Path) -> str:
    """Assemble the agent's system prompt by splicing:
      1. Builtin base (src/scieasy/ai/agent/system_prompt.py BASE constant)
      2. Project overlay (<project>/.scieasy/system_prompt.md, optional)
      3. Per-machine overlay (<project>/.scieasy/system_prompt.local.md, optional)
      4. SKILL.md base (loaded via importlib.resources from
         src/scieasy/_skills/scieasy/SKILL.md) with:
           - <!-- tool_catalog --> spliced with _render_tool_catalog()
           - <!-- project_context --> spliced with _render_project_context(project_dir)

    Returns the assembled prompt string. Passed via
    --append-system-prompt @<tmp_file> to the spawned agent CLI.
    """

def _load_skill_md() -> str:
    """Load src/scieasy/_skills/scieasy/SKILL.md via
    importlib.resources.files (post-ADR-040 §3.4 relocation)."""

def _render_tool_catalog() -> str:
    """Enumerate registered tools via mcp.list_tools(); render
    each as `- mcp__scieasy__<name>: <description first line>`."""

def _render_project_context(project_dir: Path) -> str:
    """Per ADR-040 §3.3: render project-context section with:
      - Project name + path
      - Top-3 by-mtime workflow files (with name + last_modified)
      - Installed plugin list (from BlockRegistry.packages())
      - Git: branch + dirty flag (if git available)
    Performance budget: <100ms (#825 requirement)."""

def _splice_catalog(skill_md: str, catalog: str) -> str:
    """Replace content between <!-- tool_catalog:begin/end --> markers."""
```

### `mcp-tools.terminal-spawn` — `spawn_claude` / `spawn_codex`
Status: a
Source: `src/scieasy/ai/agent/terminal.py`
Primary-doc-source: ADR-034, ADR-040

```python
def spawn_claude(
    project_dir: Path,
    user_prompt: str | None = None,
    dangerous: bool = False,
    extra_env: dict[str, str] | None = None,
) -> PtyProcess:
    """Spawn `claude` CLI as a PTY subprocess.

    argv:
        ["claude", "--append-system-prompt", f"@{prompt_path}",
         "--mcp-config", str(mcp_config)]
        + (["--dangerously-skip-permissions"] if dangerous else [])

    Writes system prompt to a tempfile (via _write_system_prompt_tempfile)
    and mcp.json to <project>/.scieasy/mcp.json (via _ensure_mcp_config).

    Sets cwd=project_dir so claude's CLAUDE.md / .claude/ /
    .agents/ / .codex/ discovery resolves to the project's
    provisioned files.
    """

def spawn_codex(
    project_dir: Path,
    user_prompt: str | None = None,
    dangerous: bool = False,
    extra_env: dict[str, str] | None = None,
) -> PtyProcess:
    """Spawn `codex` CLI as a PTY subprocess.

    argv:
        ["codex"] + (["--dangerously-bypass-approvals-and-sandbox"] if dangerous else [])

    No --mcp-config / --append-system-prompt — Codex reads
    AGENTS.md + .agents/skills/ + .codex/config.toml from cwd
    automatically (per ADR-040 §2.7 + §3.7).

    Sets cwd=project_dir.
    """

def _write_system_prompt_tempfile(project_dir: Path) -> Path:
    """Render via compose_system_prompt + write to a tempfile.
    Returns the tempfile path for --append-system-prompt @<path>."""

def _ensure_mcp_config(project_dir: Path) -> Path:
    """Write <project>/.scieasy/mcp.json with the bridge config
    payload. Idempotent (skips if file unchanged). Returns path."""
```

### `mcp-tools.mcp.json-wire-format` — bridge config
Status: a
Source: `src/scieasy/cli/install.py:L91-L106`
Primary-doc-source: ADR-040 §3.9
Supplementary-doc-source: written by `src/scieasy/ai/agent/terminal.py::_ensure_mcp_config`

```json
{
  "mcpServers": {
    "scieasy": {
      "command": "<sys.executable>",                          // anchored to current Python — Codex P1 hotfix
      "args": ["-m", "scieasy", "mcp-bridge"],
      "env": {
        "SCIEASY_PROJECT_DIR": "<project_dir>"
      }
    }
  }
}
```

### `mcp-tools.mcp-bridge-subcommand` — `scieasy mcp-bridge`
Status: a
Source: `src/scieasy/cli/mcp_bridge.py`
Primary-doc-source: ADR-040 §3.1

```python
@app.command()
def mcp_bridge() -> None:
    """Run the standalone MCP bridge subprocess.

    Reads SCIEASY_PROJECT_DIR from env → make_mcp_runtime →
    start_inprocess_server → blocks on accept loop until stdin EOF.

    Invoked by Claude Code / Codex when they read mcp.json and
    spawn the bridge. Bridge connects to the in-process FastAPI MCP
    server via UDS (POSIX) or TCP loopback (Windows).
    """
```

### `mcp-tools.list_block_runs-ghost-tool` — non-existent tool in static catalog
Status: c
Source: `src/scieasy/_skills/scieasy/SKILL.md:L103`
Primary-doc-source: `[CODE: tool doesn't exist — 7th inspection tool is get_block_logs]`
Issue: #TBD-skill-md-ghost-tool-fix

```python
# c-drop — A7 audit caught: src/scieasy/_skills/scieasy/SKILL.md line
# 103 (static fallback catalog) lists `list_block_runs` as one of 7
# inspection tools. NO SUCH TOOL EXISTS. The 7th inspection tool is
# `get_block_logs`.
#
# Codex agents reading SKILL.md verbatim will call
# mcp__scieasy__list_block_runs and get METHOD_NOT_FOUND.
#
# Fix is code-side: replace "list_block_runs" with "get_block_logs"
# at SKILL.md:L103. NOT a c-impl (we don't want a new tool — just
# fix the catalog).
```

### `mcp-tools.preview_data-skill-body-args-wrong` — skill body documents wrong args
Status: b
Source: `src/scieasy/_skills/scieasy/scieasy-inspect-data/SKILL.md`
Primary-doc-source: `[CODE: preview_data(ref, fmt) — no max_rows / max_dim]`
Issue: #TBD-preview-data-skill-body-fix

```python
# b-code-wins — A7 audit caught: the scieasy-inspect-data SKILL.md
# documents preview_data(ref, max_rows?, max_dim?) but the actual
# tool signature is preview_data(ref, fmt). max_rows and max_dim
# are NOT implemented parameters.
#
# Agents reading this skill will try preview_data(ref, max_rows=10)
# and get TypeError or silently get unintended fmt.
#
# Fix is content-side: rewrite the skill body to match the code's
# (ref, fmt) signature + enumerate the supported fmt values
# ("thumbnail_png_base64", "first_rows_json", "first_chars", "auto").
```

### `mcp-tools._context.py-docstring-tool-count-stale` — 25 vs 26
Status: b
Source: `src/scieasy/ai/agent/mcp/_context.py`
Primary-doc-source: `[CODE: docstring stale]`
Issue: #TBD-mcp-context-docstring-fix

```python
# b-code-wins — A7 audit caught: _context.py module docstring says
# "25 MCP tools" but post-ADR-035 + ADR-040, count is 26
# (10 workflow including finish_ai_block + 5 + 7 + 4).
# One-line fix: change "25" → "26".
```

## 12. versioning-git

**Module preamble**: This module is **almost entirely d-class** per cross-cascade analysis (Claude C5 + K1/K2/K3 + I1/I2 all confirm; Codex folded these surfaces into M03/M05/M08 without separating). ARCH §4.6 describes design intent (bundled portable git CLI, per-platform binary table, commit-prefix convention) but does NOT enumerate the 22-method `GitEngine` public API. Two c-drop entries: `git_author.json` (spec fiction — file does NOT exist) and `watcher.py` / `GitChangeWatcher` (collapsed into `api/routes/workflow_watcher.py`). Recommend Phase 7+ produces a dedicated ARCH §4.6 expansion enumerating the GitEngine method surface.

### `versioning-git.GitEngine` — bundled-git subprocess wrapper class
Status: d
Source: `src/scieasy/core/versioning/git_engine.py`
Primary-doc-source: `[ARCHITECTURE: §4.6 design intent only — 22 public methods undocumented]`
Issue: #TBD-git-engine-document

```python
class GitEngine:
    """Subprocess wrapper around the bundled portable git CLI.

    Per ADR-039: NOT pygit2 / gitpython / dulwich — uses the bundled
    git binary via subprocess for max cross-platform reliability +
    100% bug-for-bug compatibility with external git tools.

    Sub-label d-document: 22 public methods enumerated below. ARCH
    §4.6 narrates design + bundled binary table but doesn't list
    methods. SSOT establishes canonical method surface.
    """

    def __init__(self, project_path: Path) -> None:
        """Init with project root. Does NOT auto-init git repo;
        call init_repository() explicitly."""

    def init_repository(self) -> None:
        """git init + write default .gitignore + initial commit
        ("Initial commit (auto-generated by SciEasy)").
        Idempotent on already-initialized repo."""

    def is_repository(self) -> bool:
        """Return True if <project>/.git exists + is valid."""

    def commit(self, message: str, files: list[str] | None = None) -> str:
        """Create commit; returns the new commit SHA.
        files=None → commit all staged changes.
        files=[...] → git add + commit only these files (atomic)."""

    def log(
        self,
        max_count: int | None = None,
        prefix_filter: str | None = None,   # "auto:" | "agent:" | "" (no-prefix only)
        ref: str | None = None,
    ) -> list[CommitInfo]:
        """Return commit history. prefix_filter applies ADR-039 §3.4a
        commit-prefix convention filtering."""

    def diff(self, ref: str | None = None, paths: list[str] | None = None) -> str:
        """Return diff text. ref=None → diff working tree vs HEAD.
        ref="A..B" → diff between two refs."""

    def restore(self, ref: str, paths: list[str]) -> None:
        """git restore --source=<ref> on each path."""

    def head_state(self) -> HeadState:
        """Return (head_sha, dirty: bool) tuple."""

    def status(self) -> dict[str, list[str]]:
        """Return {staged: [...], modified: [...], untracked: [...]}."""

    def current_branch(self) -> str:
        """Return current branch name. Raises GitError if detached HEAD."""

    def branches(self) -> list[str]:
        """List all local branch names."""

    def branch_create(self, name: str, start_point: str | None = None) -> None:
        """Create branch. start_point=None → branch from HEAD."""

    def branch_switch(self, name: str) -> None:
        """git switch <name>. Refreshes BlockRegistry as side effect
        (cross-layer coupling — see cross-cutting C entry)."""

    def branch_delete(self, name: str, force: bool = False) -> None:
        """git branch -d (or -D if force=True)."""

    def merge(self, ref: str) -> MergeResult:
        """Initiate merge of ref into current branch.
        Returns MergeResult with status ('fast-forward' | 'clean' |
        'conflict') + (if conflict) list of conflicted files.

        On conflict: caller drives resolution via merge_stage_file +
        merge_complete (or merge_abort)."""

    def cherry_pick(self, ref: str) -> None:
        """git cherry-pick <ref>. May raise GitError on conflict."""

    def merge_stage_file(self, path: str) -> None:
        """git add <path> during conflict resolution."""

    def merge_complete(self, message: str) -> str:
        """git commit during merge — returns merge commit SHA."""

    def merge_abort(self) -> None:
        """git merge --abort."""

    def stash_list(self) -> list[dict]:
        """git stash list — return [{ref, message, branch, ts}, ...]."""

    def stash_save(self, message: str | None = None) -> None:
        """git stash push -m <message>."""

    def stash_apply(self, ref: str | None = None) -> None:
        """git stash apply (ref=None → most recent)."""

    def stash_drop(self, ref: str | None = None) -> None:
        """git stash drop."""
```

### `versioning-git.HeadState` — head state tuple
Status: d
Source: `src/scieasy/core/versioning/git_engine.py`
Primary-doc-source: `[ARCHITECTURE: §4.6 not enumerated]`
Issue: #TBD-git-engine-types-document

```python
@dataclass(frozen=True)
class HeadState:
    """Result of head_state() — used by LineageRecorder when
    stamping runs.workflow_git_commit."""
    sha: str | None        # None if no commits yet (fresh repo)
    dirty: bool            # True if working tree has unstaged changes
```

### `versioning-git.MergeResult` — merge outcome
Status: d
Source: `src/scieasy/core/versioning/git_engine.py`
Primary-doc-source: `[ARCHITECTURE: §4.6 not enumerated]`
Issue: #TBD-git-engine-types-document

```python
# Type alias (not a dataclass — kept as dict for JSON serialization
# via REST):
MergeResult = dict[str, Any]
# Shape:
#   {"status": "fast-forward" | "clean" | "conflict",
#    "commit_sha": str | None,         # set on fast-forward + clean
#    "conflicted_files": list[str]}    # set on conflict, else []
```

### `versioning-git.GitError` — exception type
Status: d
Source: `src/scieasy/core/versioning/git_engine.py`
Primary-doc-source: `[ARCHITECTURE: §4.6 not enumerated]`
Issue: #TBD-git-engine-types-document

```python
class GitError(Exception):
    """Raised when a git subprocess returns non-zero exit code.

    Attributes:
        cmd: the git command that failed (argv list)
        returncode: subprocess exit code
        stderr: captured stderr (may be empty)

    NOTE: GitTimeoutError does NOT exist — subprocess.TimeoutExpired
    is NOT wrapped (C5 + A5 audit confirmed). Callers must catch both
    GitError AND subprocess.TimeoutExpired. Recommend adding
    GitTimeoutError that wraps subprocess.TimeoutExpired with same
    cmd context (separate code-fix issue).
    """
    cmd: list[str]
    returncode: int
    stderr: str
```

### `versioning-git.BundledGitMissing` — exception when binary not found
Status: d
Source: `src/scieasy/core/versioning/git_engine.py`
Primary-doc-source: `[ARCHITECTURE: §4.6 not enumerated]`
Issue: #TBD-git-engine-types-document

```python
class BundledGitMissing(Exception):
    """Raised by GitBinary discovery when no git binary can be
    located via any of the 4 search paths.

    Operational note: in this case, ApiRuntime opens the project
    in DEGRADED MODE (no git operations) per ADR-039 §3.4. The
    .scieasy/no_git marker file is NOT automatically created — user
    sees a warning in the GUI.
    """
```

### `versioning-git.GitBinary` — binary discovery (4 paths)
Status: d
Source: `src/scieasy/core/versioning/git_engine.py`
Primary-doc-source: `[ARCHITECTURE: §4.6 per-platform table only — discovery logic not enumerated]`
Issue: #TBD-git-binary-discovery-document

```python
class GitBinary:
    """Locates the git binary at GitEngine construction time.

    4 discovery paths, tried in order (first hit wins):

      1. Env var: $SCIEASY_GIT_BUNDLE_ROOT (if set) — typically used
         for testing alternate bundles.
      2. PyInstaller bundled path: sys._MEIPASS + "/git/bin/git"
         (per ADR-037 desktop bundle).
      3. Dev walkup: walk parents of __file__ looking for
         desktop/git-portable/git/bin/git.exe (Windows) or
         git/bin/git (POSIX) — for dev checkouts.
      4. shutil.which("git") — system PATH fallback.

    Raises BundledGitMissing if all 4 fail.
    """
    def __init__(self) -> None:
        self.path: Path = self._discover()

    def _discover(self) -> Path: ...

    def run(
        self,
        args: list[str],
        cwd: Path,
        timeout: float = 30.0,
    ) -> subprocess.CompletedProcess:
        """Invoke `self.path <args>` via subprocess.run with cwd.
        Raises subprocess.TimeoutExpired on timeout.
        Raises GitError on non-zero exit."""
```

### `versioning-git.DEFAULT_GITIGNORE` / `write_default_gitignore`
Status: a
Source: `src/scieasy/core/versioning/gitignore_template.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.6`

```python
DEFAULT_GITIGNORE = """\
# Data files (not versioned — see ADR-038 for run lineage)
data/

# SciEasy runtime state (per-project, per-machine; not portable)
.scieasy/

# Python caches, plugin venvs, editor caches, OS noise
__pycache__/
*.py[cod]
*-venv/
*.venv/
.idea/
.vscode/
.DS_Store
Thumbs.db
"""

def write_default_gitignore(project_path: Path) -> None:
    """Write DEFAULT_GITIGNORE to <project>/.gitignore IF the file
    doesn't already exist (preserves user edits). Called by
    GitEngine.init_repository()."""
```

### `versioning-git.is_dirty` / `modified_files` — status helpers
Status: d
Source: `src/scieasy/core/versioning/` (helper functions)
Primary-doc-source: `[ARCHITECTURE: §4.6 prose-only]`
Issue: #TBD-versioning-helpers-document

```python
def is_dirty(git_engine: GitEngine) -> bool:
    """Return True if working tree has any unstaged or untracked
    changes. Equivalent to head_state().dirty but doesn't require
    the full HeadState return."""

def modified_files(git_engine: GitEngine) -> list[str]:
    """Return list of paths (relative to project root) with
    unstaged modifications. Excludes untracked (use git_engine.
    status()['untracked'] for those)."""
```

### `versioning-git.commit-prefix-convention` — agent / auto / no-prefix
Status: d
Source: `src/scieasy/core/versioning/git_engine.py:L1-L1`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.6`
Supplementary-doc-source: ADR-039 §3.4a
Issue: #TBD-commit-prefix-convention-document

```python
# d-document — ARCH §4.6 prose mentions the 3 commit prefixes; SSOT
# establishes them as normative constants.

COMMIT_PREFIX_AUTO  = "auto:"      # pre-run squash commit, hidden in History panel default
COMMIT_PREFIX_AGENT = "agent:"     # agent-authored milestone (ADR-034/035 or programmatic)
# (no prefix)                      # user-authored manual milestone

# GitEngine.log() prefix_filter parameter uses these. The GUI
# History panel renders each prefix differently:
#   auto:    → small grey dots in branch graph (topology preservation)
#   agent:   → 🤖 icon
#   (none)   → 👤 icon
```

### `versioning-git.no_git-marker` — degraded mode opt-out
Status: d
Source: `src/scieasy/api/runtime.py:L1-L1`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §4.6`
Issue: #TBD-no-git-marker-constant

```python
# d-document — the marker file path is inlined in runtime.py rather
# than a named constant in versioning/. Recommend extracting to a
# named module-level constant for visibility:

NO_GIT_MARKER_FILENAME = "no_git"    # under <project>/.scieasy/

# Operational semantics:
# - Presence of <project>/.scieasy/no_git → ApiRuntime skips git
#   auto-init (degraded mode; no git operations available).
# - User creates this manually if they don't want git tracking.
# - Per ADR-039 §3.4: file is NOT auto-created on BundledGitMissing;
#   user must opt out explicitly.
```

### `versioning-git.git_author.json` — spec fiction (file does NOT exist)
Status: c
Source: `[CODE: file does NOT exist — identity hardcoded]`
Primary-doc-source: ARCH §4.6 + §10 workspace diagram (BOTH stale)
Issue: #TBD-git-author-json-c-drop

```python
# c-drop — A5 audit + C5 + I1/I2 all confirm: docs describe a
# git_author.json identity-cache JSON file that has NEVER existed in
# code. Identity is HARDCODED as module-level constants:

_DEFAULT_AUTHOR_NAME  = "SciEasy User"
_DEFAULT_AUTHOR_EMAIL = "noreply@scieasy.local"

# These are passed to git via env GIT_AUTHOR_NAME / GIT_AUTHOR_EMAIL
# (and committer counterparts) on every GitEngine.commit() call.
#
# Fix is doc-side:
#  1. Remove git_author.json from ARCH §4.6 file-list table
#  2. Remove git_author.json from ARCH §10 workspace diagram
#  3. Add explicit note: "Identity hardcoded as constants; ADR-039
#     OQ-1 was resolved as 'no cache file'."
#
# If future requirement emerges for per-project author override,
# that's a SEPARATE feature (c-impl) — but currently no such req.
```

### `versioning-git.watcher.py / GitChangeWatcher` — collapsed into API layer
Status: c
Source: `[CODE: NOT in versioning/ — moved to api/routes/workflow_watcher.py]`
Primary-doc-source: PROJECT_TREE.md (stale)
Issue: #TBD-project-tree-watcher-py-removal

```python
# c-drop — A5 confirmed: PROJECT_TREE.md still lists watcher.py in
# core/versioning/, but the file was collapsed into api/routes/
# workflow_watcher.py during an earlier refactor (rationale: git
# watching is API-layer concern — it pushes WS events out, not a
# core-layer responsibility).
#
# Fix is doc-side:
#  1. Remove watcher.py from PROJECT_TREE.md core/versioning/ listing
#  2. Optionally add a note pointing at api/routes/workflow_watcher.py
#     for git head-change detection
#
# The functionality (git.head_changed WS message) lives at:
#   src/scieasy/api/routes/workflow_watcher.py::_GitHeadHandler
# which is documented in §10 ws-sse-protocol above.
```

## 13. agent-provisioning

**Module preamble** (from Codex M08): CLI install / mcp-bridge contract A-class (post-ADR-040 install-parity). Scaffold conformance verification B-class (needs explicit normative acceptance rules per ADR-026). Per ADR-040 §3.5-§3.10: provisions CLAUDE.md/AGENTS.md + .claude/settings.json hook matchers + 6 hook scripts + 6 skills + .codex/config.toml + version-marker. 2 c-defer entries: ADR-041 placeholders (#1015 Layer 7 ACL + #1016 BlockRegistry runtime DataObject-port rejection).

### `agent-provisioning.install_project_agent_assets` — main orchestrator
Status: a
Source: `src/scieasy/agent_provisioning/_orchestrate.py`
Primary-doc-source: ADR-040 §3.8

```python
def install_project_agent_assets(
    project_dir: Path,
    *,
    force: bool = False,
) -> ProvisionResult:
    """Idempotent provisioning of all agent-reliability assets to a
    project workspace.

    Per ADR-040 §3.8 ordering (called AFTER ADR-039 git init,
    BEFORE ApiRuntime.open_project finishes):
      1. Write CLAUDE.md (skip if exists + content matches AND
         force=False)
      2. Write AGENTS.md (identical content to CLAUDE.md)
      3. Write .claude/settings.json (hook matchers + skill paths)
      4. Write .claude/hooks/*.py (6 scripts)
      5. Write .claude/skills/scieasy/* (6 skills)
      6. Write .agents/skills/scieasy/* (mirror — same 6 skills for Codex)
      7. Write .codex/config.toml (MCP wiring)
      8. Write .claude/.scieasy-provision-version (= SCIEASY_PROVISION_VERSION)
      9. Best-effort: git add + commit ("provision: scieasy agent
         assets v<version>")

    Args:
        project_dir: project workspace root.
        force: if True, overwrite user-edited files (DANGEROUS).
            Default False = preserve user edits (per-file hash compare).

    Returns:
        ProvisionResult listing written / skipped / failed paths.
    """
```

### `agent-provisioning.ProvisionResult` — orchestration outcome
Status: a
Source: `src/scieasy/agent_provisioning/_orchestrate.py`
Primary-doc-source: ADR-040 §3.8

```python
@dataclass
class ProvisionResult:
    """Outcome of install_project_agent_assets."""
    written: list[Path]                              # paths that were created or updated
    skipped: list[Path]                              # paths already up-to-date (or user-edited + force=False)
    failed: list[tuple[Path, Exception]]             # (path, exception) for non-fatal failures
    version: str                                     # SCIEASY_PROVISION_VERSION installed
```

### `agent-provisioning.SCIEASY_PROVISION_VERSION` — version constant + marker file
Status: a
Source: `src/scieasy/agent_provisioning/__init__.py`
Primary-doc-source: ADR-040 §3.8

```python
SCIEASY_PROVISION_VERSION = "0.1.0"
"""Bumped whenever the provisioned asset set changes (new hook,
new skill, template content edit). install_project_agent_assets
compares against <project>/.claude/.scieasy-provision-version to
detect version drift and trigger top-up updates.

Marker file at <project>/.claude/.scieasy-provision-version
contains literally the version string (no other content).
"""
```

### `agent-provisioning.6-hook-scripts` — PreToolUse + PostToolUse matchers
Status: d
Source: `src/scieasy/agent_provisioning/templates/hook_*.py`
Primary-doc-source: ADR-040 §3.6
Issue: #TBD-agent-provisioning-hooks-document-in-arch

```python
# d-document — 6 hook scripts, each with matcher + stdin JSON + exit
# code contract. ADR-040 §3.6 specifies; SSOT establishes the full
# signature for each.

# === PreToolUse (3 hooks, exit 2 = block tool call) ===

# 1. deny_scieasy_cli — block `scieasy ...` Bash invocations
# Matcher: Bash
# Stdin: {tool_name: "Bash", tool_input: {command: "..."}, session_id: ...}
# Effect: if command matches /\bscieasy\s+(?!mcp-bridge)/ → exit 2 with
#   stderr "Use mcp__scieasy__* tools, not the CLI"; else exit 0.

# 2. protect_workflow_yaml — block direct edits to workflows/*.yaml
# Matcher: Edit|Write
# Stdin: {tool_name: "Edit"|"Write", tool_input: {file_path: "..."}, ...}
# Effect: if file_path matches workflows/*.yaml → exit 2 with stderr
#   "Use mcp__scieasy__write_workflow / update_block_config"; else exit 0.

# 3. enforce_list_blocks_before_block_write — session-keyed list_blocks gate
# Matcher: Edit|Write|MultiEdit|Bash|mcp__scieasy__scaffold_block
# Stdin: {tool_name: ..., tool_input: ..., session_id: ..., ...}
# Effect: check for marker <project>/.scieasy/.session-state/<session_id>/list_blocks_called
#   IF marker absent AND tool would write to blocks/*.py → exit 2 with
#   stderr "Call mcp__scieasy__list_blocks first to check existing blocks
#   (#875 reuse rule)"; ELSE exit 0.
#   (Header carries TODO(#1015) Layer 7 ACL placeholder for full filesystem ACL.)

# === PostToolUse (3 hooks, always exit 0; effect is stderr reminder + side effects) ===

# 4. remind_poll_status — reminder after run_workflow
# Matcher: mcp__scieasy__run_workflow
# Stdin: {tool_name: ..., tool_response: ..., session_id: ..., ...}
# Effect: print to stderr "Poll mcp__scieasy__get_run_status until
#   state in {completed, failed, cancelled}". Exit 0.

# 5. mark_list_blocks_called — write session marker
# Matcher: mcp__scieasy__list_blocks
# Stdin: {tool_name: ..., session_id: ..., ...}
# Effect: touch <project>/.scieasy/.session-state/<session_id>/list_blocks_called
#   (so enforce_list_blocks_before_block_write hook unblocks subsequent writes).
#   Exit 0.

# 6. enforce_concrete_port_types — AST scan blocks/*.py for DataObject ports
# Matcher: Edit|Write|MultiEdit|mcp__scieasy__scaffold_block
# Stdin: {tool_name: ..., tool_input: ..., tool_response: ..., ...}
# Effect: if any blocks/*.py was just edited, AST-parse to find
#   InputPort(accepted_types=[DataObject]) / OutputPort(accepted_types=[DataObject])
#   patterns; print stderr warning per occurrence (NOT block — exit 0).
#   Header carries TODO(#1016) for future hard-reject in BlockRegistry.

# All 6 scripts:
# - Are pure Python stdlib (no scieasy package import — agents run them as
#   `python <script>`, not via `python -m scieasy.*`)
# - Read stdin JSON via json.load(sys.stdin)
# - Output to stderr (stdout reserved for hook protocol)
# - Exit code semantics: 0 = pass, 2 = block (only PreToolUse honors)
```

### `agent-provisioning.session-marker-path` — multi-hook coordination state
Status: d
Source: `src/scieasy/agent_provisioning/templates/hook_{mark,enforce}_list_blocks_*.py`
Primary-doc-source: ADR-040 §3.6
Issue: #TBD-agent-provisioning-session-marker-document

```python
# d-document — session-marker file path used by 2 cooperating hooks
# (mark_list_blocks_called writes; enforce_list_blocks_before_block_write
# reads). The path includes session_id from the Claude Code hook stdin
# payload for per-session isolation.

SESSION_MARKER_PATH_TEMPLATE = "<project>/.scieasy/.session-state/<session_id>/list_blocks_called"
"""Path template — substitute <project> with project root + <session_id>
with the hook stdin payload's session_id field.

File contents: empty (presence is the signal).

Cleanup: .scieasy/.session-state/ directory is git-ignored AND should be
periodically pruned (orphaned session dirs for completed agent sessions).
No auto-cleanup today — recommend cron-style cleanup as future enhancement.
"""
```

### `agent-provisioning.claude_agents_md-template` — CLAUDE.md / AGENTS.md content
Status: b
Source: `src/scieasy/agent_provisioning/templates/claude_agents_md.md`
Primary-doc-source: ADR-040 §3.5
Issue: #TBD-claude-agents-md-codex-hook-text-fix

```markdown
<!-- b-code-wins — A7 audit caught: template currently says "Codex
     hooks are deferred to #1015" in 5 occurrences, but
     write_codex_config DOES provision the equivalent hooks via
     .codex/config.toml [hooks] sections (per ADR-040 Addendum 4).
     Template text is FACTUALLY WRONG — agents reading it will
     believe they have no hook safety net on Codex side.

     Fix is content-side: replace the 5 "Codex hooks deferred"
     stanzas with accurate description of the Codex hook coverage.

     SSOT establishes the CORRECT template structure: -->

# SciEasy Project Agent Guide

You are working inside a SciEasy project workspace. This file is the
identity + non-negotiable rules entry point read at agent session start.

## Identity & non-negotiable rules
1. Use `mcp__scieasy__*` tools for anything touching blocks, workflows,
   runs, or data. Do NOT use the `scieasy` CLI via Bash.
2. Do NOT directly Edit/Write `workflows/*.yaml` — use
   `mcp__scieasy__write_workflow` / `update_block_config`.
3. BEFORE writing a new block, call `mcp__scieasy__list_blocks` and
   reuse an existing block if its I/O contract matches.
4. BEFORE selecting port types, call `mcp__scieasy__list_types`.
   Use the most specific applicable type; `DataObject` only for
   generic blocks.
5. Working directory IS the project root. Use relative paths.
6. All workflow YAML changes are git-tracked.

## Hook coverage
[CORRECTED — was: "Codex side has no hooks; deferred to #1015"
 NOW: enumerate the 6 hooks installed on BOTH Claude Code side
 (.claude/hooks/) AND Codex side (.codex/config.toml [hooks])]

## Skills available
[5 task skills + 1 base skill — see scieasy-build-workflow,
 scieasy-write-block, scieasy-debug-run, scieasy-inspect-data,
 scieasy-project-qa]
```

### `agent-provisioning.codex_config.toml` — Codex MCP + hooks wiring
Status: a
Source: `src/scieasy/agent_provisioning/codex_config.py:L1-L1`
Primary-doc-source: ADR-040 §3.7
Supplementary-doc-source: ADR-040 §3.9 (CLI install path reuses same renderer)

```toml
# Rendered content of <project>/.codex/config.toml.
# The template file in templates/ is DOCUMENTATION ONLY — never loaded
# at runtime. SSOT documents the actually-rendered content:

[mcp_servers.scieasy]
command = "<sys.executable>"                    # anchored to current Python
args = ["-m", "scieasy", "mcp-bridge"]

[mcp_servers.scieasy.env]
SCIEASY_PROJECT_DIR = "<project_dir absolute path>"

# Plus 6 [hooks] sections mirroring the .claude/hooks/ behavior
# (per ADR-040 Addendum 4):
[hooks.deny_scieasy_cli]
on = "PreToolUse"
match = "Bash"
script = "python .claude/hooks/deny_scieasy_cli.py"
# ... 5 more [hooks.*] sections (same as 6 PreToolUse + PostToolUse)
```

### `agent-provisioning.codex_config.toml-template-documentation-only` — template never loaded
Status: b
Source: `src/scieasy/agent_provisioning/templates/codex_config.toml`
Primary-doc-source: `[CODE: template file is docs-only — actual rendering in codex_config.py]`
Issue: #TBD-codex-config-template-documentation-only-note

```toml
# b-docs-wins — A7 caught: templates/codex_config.toml is NEVER loaded
# at runtime by write_codex_config(). The actual rendering is done by
# Python code in codex_config.py (using string formatting). The
# template file is for human reference only.
#
# This is confusing — readers naturally assume template files are
# loaded. Fix is content-side: add a comment header at top of
# templates/codex_config.toml saying "DOCUMENTATION ONLY — not loaded
# at runtime; see codex_config.py for actual rendering."
```

### `agent-provisioning.settings.json-template` — `.claude/settings.json` hook matchers
Status: d
Source: `src/scieasy/agent_provisioning/hooks.py`
Primary-doc-source: ADR-040 §3.6
Issue: #TBD-claude-settings-json-template-document

```json
// d-document — full rendered structure of <project>/.claude/settings.json.
// SSOT establishes:
{
  "hooks": {
    "PreToolUse": [
      {"matcher": "Bash",
       "hooks": [{"type": "command", "command": "python .claude/hooks/deny_scieasy_cli.py"}]},
      {"matcher": "Edit|Write",
       "hooks": [{"type": "command", "command": "python .claude/hooks/protect_workflow_yaml.py"}]},
      {"matcher": "Edit|Write|MultiEdit|Bash|mcp__scieasy__scaffold_block",
       "hooks": [{"type": "command", "command": "python .claude/hooks/enforce_list_blocks_before_block_write.py"}]}
    ],
    "PostToolUse": [
      {"matcher": "mcp__scieasy__run_workflow",
       "hooks": [{"type": "command", "command": "python .claude/hooks/remind_poll_status.py"}]},
      {"matcher": "mcp__scieasy__list_blocks",
       "hooks": [{"type": "command", "command": "python .claude/hooks/mark_list_blocks_called.py"}]},
      {"matcher": "Edit|Write|MultiEdit|mcp__scieasy__scaffold_block",
       "hooks": [{"type": "command", "command": "python .claude/hooks/enforce_concrete_port_types.py"}]}
    ]
  }
}
```

### `agent-provisioning.6-skills` — base + 5 task skills
Status: d
Source: `src/scieasy/_skills/scieasy/SKILL.md:L1-L1`
Primary-doc-source: ADR-040 §3.4
Issue: #TBD-agent-provisioning-skills-document

```markdown
<!-- d-document — 6 SKILL.md files installed by skills.py:
     - src/scieasy/_skills/scieasy/SKILL.md  (BASE)
       Frontmatter: name: scieasy, description: ...
       Marker comments: <!-- tool_catalog:begin/end -->,
                        <!-- project_context:begin/end -->
       Body: ~80 LOC — identity, 5-skill index, non-negotiable rules
     - src/scieasy/_skills/scieasy/scieasy-build-workflow/SKILL.md
     - src/scieasy/_skills/scieasy/scieasy-write-block/SKILL.md
       (includes #875 list_blocks rule + ADR-040 §3.2a port-type rule)
     - src/scieasy/_skills/scieasy/scieasy-debug-run/SKILL.md
     - src/scieasy/_skills/scieasy/scieasy-inspect-data/SKILL.md
       (has wrong preview_data args — see mcp-tools §11 b entry)
     - src/scieasy/_skills/scieasy/scieasy-project-qa/SKILL.md

     Each task skill has frontmatter:
       name: <slug>
       description: <when to use this skill — trigger spec>

     Cross-installed by skills.py to BOTH:
       - .claude/skills/scieasy/*    (Claude Code discovery)
       - .agents/skills/scieasy/*    (Codex discovery)

     The relocation from skills/scieasy/ → src/scieasy/_skills/scieasy/
     happened in ADR-040 §3.4 to fix the wheel-install bug (#824). -->
```

### `agent-provisioning.lifecycle-wiring` — create_project + open_project + scieasy init
Status: a
Source: `src/scieasy/api/runtime.py:L1-L1`
Primary-doc-source: ADR-040 §3.8
Supplementary-doc-source: `src/scieasy/cli/main.py::init` mirrors the same wiring

```python
# All 3 callsites wrap install_project_agent_assets in try/except per
# ADR-040 §7 "non-fatal" semantics (provisioning failure logs WARNING
# but does NOT prevent project open / create).

# In api/runtime.py::create_project (after git auto-init, before open):
try:
    result = install_project_agent_assets(project_path, force=False)
    if result.failed:
        logger.warning("Provisioning had %d non-fatal failures", len(result.failed))
except Exception:
    logger.exception("Provisioning failed entirely; continuing without agent assets")

# Same pattern in api/runtime.py::open_project (idempotent top-up
# for existing projects on each open — ADR-040 §3.8 idempotency
# guarantee).

# Same pattern in cli/main.py::init (after git init, before final echo).
```

### `agent-provisioning.ADR-041-placeholders` — Layer 7 ACL + BlockRegistry rejection
Status: c
Source: `[CODE: deferred to ADR-041 per ADR-040 §3.10]`
Primary-doc-source: ADR-040 §3.10
Issue: #1015

```python
# c-defer — both explicit ADR-040 §3.10 deferrals, tracked at ADR-041
# placeholders. SSOT establishes the deferred contracts so the future
# ADR-041 implementer has the canonical shape:

# #1015 — Layer 7 filesystem ACL on <project>/blocks/
def enforce_blocks_directory_acl(project_dir: Path) -> None:
    """[DEFERRED #1015] Apply filesystem ACL to <project>/blocks/ so
    only specific tools (mcp__scieasy__scaffold_block + the
    scieasy CLI) can write there. Currently relies on PreToolUse
    hook (enforce_list_blocks_before_block_write.py) which can be
    bypassed by direct fs writes (e.g., user manually runs
    `vim blocks/foo.py`)."""

# #1016 — BlockRegistry runtime rejection of DataObject-typed ports
def reject_dataobject_typed_ports(spec: BlockSpec) -> None:
    """[DEFERRED #1016] At registry scan time, REJECT (don't register)
    any Block whose input_ports / output_ports contain accepted_types=
    [DataObject] (the abstract root). Currently only emits warnings
    via PostToolUse hook (enforce_concrete_port_types.py) + scaffold_block
    soft-warnings. Hard rejection would prevent the block from being
    palette-listed."""
```

## Cross-cutting C-class entries (NEW from Codex cross-cascade)

These two entries are architectural-level concerns that span multiple modules. Both surfaced by Codex's coarser-granularity analysis and missed by my finer-granularity per-interface inventory. Folded into draft v3 cross-cascade reconciliation.

### `cross-cutting.rest-api.cross-layer-coupling` — API → runtime mutation
Status: c
Source: `src/scieasy/api/routes/git.py:L1-L1`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §3`
Supplementary-doc-source: Codex M05 R2 cross-cascade finding (HIGH-CONFIDENCE, MED dispute level)
Issue: #TBD-rest-api-cross-layer-coupling

```python
# c-impl — Codex R2 finding:
# > "API 路由中出现 runtime 级动作（例如分支切换后 refresh block registry），
# > 从分层角度看属于'API 编排 runtime 状态刷新'的跨层连接点"
#
# Concrete examples:
#   1. POST /api/git/branches/switch → triggers ApiRuntime.refresh_block_registry()
#      (because branch switch may have changed blocks/*.py files)
#   2. POST /api/projects/{id}/open → triggers _init_lineage_store +
#      _init_metadata_store + refresh_block_registry + _publish_mcp_port
#   3. POST /api/blocks/template (BLK-004) → triggers BlockRegistry hot_reload
#
# These are all "API surface (Layer 5) directly invokes runtime state
# mutation (Layer 3)" — anti-pattern per ARCH §3 "clean layer boundaries"
# + CLAUDE.md §7.3 "narrow module responsibility".
#
# Recommended fix (per Codex R2 + my reading):
#   Option A (cleaner): API publishes an EngineEvent (e.g.,
#     GIT_BRANCH_CHANGED); BlockRegistry subscribes + reacts.
#     Layer-clean — API doesn't reach into runtime.
#   Option B (pragmatic): keep current pattern, document the explicit
#     allow-list of API→runtime calls + rationale per case.
#
# SSOT sub-label: c-impl with Option B as default (pragmatic — these
# coupling points are intentional + few in count). Option A as future
# enhancement if the coupling set grows.

# Affected REST endpoints (full list — Phase 7 audit expands):
@router.post("/api/git/branches/switch")
async def switch_branch(req: BranchSwitchRequest) -> BranchSwitchResponse:
    """Switch git branch.
    SIDE EFFECT: triggers ApiRuntime.refresh_block_registry() because
    blocks/*.py may have changed across branches.
    CROSS-LAYER COUPLING per c-impl entry above."""
```

### `cross-cutting.workflow-yaml.validator-strictness-variability` — context-dependent validation
Status: c
Source: `src/scieasy/workflow/validator.py`
Primary-doc-source: `docs/architecture/ARCHITECTURE.md §2.1` (workflow graph is SoT — implicitly deterministic)
Supplementary-doc-source: Codex M06 R2 cross-cascade finding (HIGH-CONFIDENCE, MED dispute level)
Issue: #TBD-validator-strictness-context-dependent

```python
# c-impl — Codex M06 R2 finding:
# > "validator 在 registry 可用与不可用场景下行为不同（严格端口/类型校验
# > vs warning/fallback），导致'事实源严格性'受运行上下文影响。
# > 同一图定义在不同执行环境下可得到不同级别诊断结果"
#
# Concrete behavior:
#   - When BlockRegistry is fully scanned (normal API process,
#     CLI `scieasy validate`): validate_workflow does STRICT
#     port-type checking (every block_type resolves, every port
#     accepted_types resolved, every constraint callable checked).
#   - When BlockRegistry is unavailable or partially scanned (e.g.,
#     mock-runner test scenario, agent that scaffolded a block but
#     hasn't called reload_blocks): validate_workflow DEGRADES to
#     warning-only mode (unresolved block_types become warnings;
#     no port-type check).
#
# Result: SAME workflow.yaml produces DIFFERENT diagnostic depth in
# different contexts. Violates "single source of truth" intent of
# ARCH §2.1 — the workflow graph IS the SoT, but its validation
# strictness varies.
#
# Recommended fix (3 options — SSOT picks Option A as default;
# Phase 7+ may reconsider):
#   Option A (strict + explicit): force strict-only — reject when
#     registry unavailable. Test scenarios use mock_registry()
#     context manager to satisfy.
#   Option B (document the modes): keep current behavior but make
#     it explicit in result envelope:
#       ValidateWorkflowResult.mode: Literal["strict", "degraded"]
#     so callers can see which mode ran.
#   Option C (parameterize): add explicit `mode` parameter to
#     validate_workflow MCP tool / REST endpoint — caller chooses.
#
# Sub-label: c-impl with Option A. Option B as fallback if A breaks
# too many existing test patterns.

# Affected surfaces:
@mcp.tool(name="validate_workflow")
async def validate_workflow(workflow_yaml_or_id: str) -> ValidateWorkflowResult:
    """STRICTNESS VARIES BY REGISTRY AVAILABILITY — see c-impl entry."""

# REST endpoint counterpart:
@router.post("/api/workflows/{id}/validate")
async def rest_validate_workflow(...) -> ValidationResponse:
    """Same strictness variability — same fix applies."""

# Workflow-side function:
def validate_workflow(
    workflow: WorkflowDefinition,
    block_registry: BlockRegistry | None,    # <-- THIS is the variability source
    type_registry: TypeRegistry | None,
) -> ValidationResult:
    """If block_registry is None → degraded mode."""
```

## Appendix A: Aggregate count

| Class | Sub-label distribution | Count |
|---|---|---|
| **a — Aligned** | (verbatim lift from code + ARCH) | ~82 |
| **b — Both, disagree** | b-code-wins ~22 / b-docs-wins ~11 | ~33 |
| **c — Code missing** | c-impl ~10 / c-drop ~4 / c-defer ~4 | ~18 |
| **d — Docs missing** | d-document ~44 / d-private ~15 / d-remove ~5 | ~64 |
| **TOTAL** | | **~197 interface entries across 13 modules + 2 cross-cutting** |

**Distribution by module** (final, post-Phase 5 + cross-cascade):

| # | Module | Total | a | b | c | d |
|---|---|---|---|---|---|---|
| 1 | block-abc | 30 | 14 | 6 | 4 | 6 |
| 2 | port-system | 13 | 4 | 2 | 0 | 7 |
| 3 | data-types | 19 | 9 | 1 | 0 | 9 |
| 4 | storage-backends | 9 | 3 | 2 | 0 | 4 |
| 5 | collection-transport | 7 | 2 | 1 | 1 | 3 |
| 6 | block-registry | 9 | 2 | 2 | 2 | 3 |
| 7 | execution-engine | 27 | 10 | 6 | 0 | 11 |
| 8 | lineage-db | 11 | 7 | 0 | 0 | 4 |
| 9 | rest-api | 23 | 12 | 6 | 1 | 4 |
| 10 | ws-sse-protocol | 8 | 4 | 2 | 0 | 2 |
| 11 | mcp-tools | 15 | 9 | 3 | 1 | 2 |
| 12 | versioning-git | 12 | 1 | 0 | 2 | 9 |
| 13 | agent-provisioning | 12 | 4 | 1 | 2 | 5 |
| cross-cutting | (2 new from Codex) | 2 | 0 | 0 | 2 | 0 |
| **TOTAL** | | **197** | **81** | **32** | **15** | **69** |

(Counts approximate per Pass-2 entry boundaries; Phase 7 auditors will re-tally.)

---

## Appendix B: Open issue placeholders (Phase 9 → real GitHub issues)

All `#TBD-*` placeholders below get instantiated as real GitHub issues in Phase 9. Each placeholder is referenced by exactly one SSOT entry above; Phase 9 opens the issue + updates the SSOT to reference the real number.

### From draft v1 (Phase 3)
`#TBD-block-class-vars-arch-update`, `#TBD-block-transition-document`, `#TBD-block-validate-annotation`, `#TBD-block-postprocess-annotation`, `#TBD-block-persist-helpers-document`, `#TBD-ioblock-load-output-dir`, `#TBD-aiblock-arch-update-for-adr-035`, `#TBD-subworkflow-classvar-vs-config`, `#TBD-coderunner-protocol-document`, `#TBD-runner-implementations-document`, `#TBD-runner-registry-private-marker`, `#TBD-externalappbridge-document`, `#TBD-fileexchangebridge-private-marker`, `#TBD-filewatcher-private-marker`, `#TBD-process-exited-error-private-marker`, `#TBD-llmprovider-legacy-removal`, `#TBD-aiblock-run-dir-protocol-document`, `#TBD-completion-watcher-document`, `#TBD-completion-internals-private-marker`, `#TBD-popen-adapter-private-marker`, `#TBD-port-is-collection-document`, `#TBD-validate-port-constraint-document`, `#TBD-port-helpers-document`, `#TBD-ports-from-config-dicts-document`, `#TBD-constraintfn-document`, `#TBD-inputport-constraint-annotation`, `#TBD-port-constraint-callable-semantics-arch-update`, `#TBD-frameworkmeta-derived-from-type-fix`, `#TBD-typespec-document-or-private`, `#TBD-data-types-helpers-document-vs-private`, `#TBD-with-meta-changes-document`, `#TBD-data-types-codec-document`, `#TBD-lazy-singletons-private-marker`, `#TBD-flush-context-document`, `#TBD-arrow-backend-atomic-write`, `#TBD-blockspec-source-literal-type`, `#TBD-entry-points-callable-vs-direct-ref`, `#TBD-blocktestharness-document`, `#TBD-typeregistry-has-method`, `#TBD-runcontext-document`, `#TBD-render-methods-markdown-document`, `#TBD-metadata-store-shim-removal`, `#TBD-async-runner-helpers-document`, `#TBD-platformops-protocol-document`, `#TBD-pty-control-http-loopback-document`, `#TBD-lineage-recorder-shim-removal`, `#TBD-dag-helpers-document`, `#TBD-dagscheduler-ctor-arch-update`, `#TBD-runhandle-future-or-private`, `#TBD-intermediate-refs-codec-document`, `#TBD-resourcemanager-watermark-doc-fix`, `#TBD-save-load-checkpoint-document`, `#TBD-checkpoint-pending-block-config-snapshot`, `#TBD-checkpointmanager-list-checkpoints`, `#TBD-scheduler-responsibility-narrowing`, `#TBD-events-subscription-matrix-code-fix`, `#TBD-runs-detail-wire-shape-document`, `#TBD-git-routes-arch-document`, `#TBD-filesystem-routes-arch-document`, `#TBD-lint-route-arch-document`, `#TBD-dynamic-ports-config-input-port-mapping`, `#TBD-type-hierarchy-ui-ring-color`, `#TBD-apiruntime-document`, `#TBD-zustand-slices-arch-update`, `#TBD-pty-ipc-internal-routes-document`, `#TBD-event-bus-bypass-document`, `#TBD-ws-frontend-reverse-coupling-document`, `#TBD-block-user-cancel-mark-done-aliasing-document`, `#TBD-mcpcontext-protocol-gap`, `#TBD-git-engine-document`, `#TBD-git-engine-types-document`, `#TBD-git-binary-discovery-document`, `#TBD-versioning-helpers-document`, `#TBD-commit-prefix-convention-document`, `#TBD-no-git-marker-constant`, `#TBD-agent-provisioning-hooks-document-in-arch`, `#TBD-agent-provisioning-session-marker-document`, `#TBD-claude-settings-json-template-document`, `#TBD-agent-provisioning-skills-document`.

### NEW from Phase 5 (draft v2 — Phase 4 audit findings)
`#TBD-storage-reference-immutability-doc-fix`, `#TBD-compositestore-iter-write-behavior-doc`, `#TBD-process-monitor-poll-interval-configurable`, `#TBD-lineage-rundetail-fe-be-drift`, `#TBD-lineage-rerun-response-new-run-id`, `#TBD-cancel-request-schemas-remove`, `#TBD-ws-inbound-message-names-correction`, `#TBD-skill-md-ghost-tool-fix`, `#TBD-mcp-context-docstring-fix`, `#TBD-claude-agents-md-codex-hook-text-fix`, `#TBD-project-tree-entry-points-fix`, `#TBD-arch-workspace-diagram-git-author-fix`, `#TBD-project-tree-watcher-py-removal`, `#TBD-preview-data-skill-body-fix`, `#TBD-codex-config-template-documentation-only-note`.

### NEW from draft v3 (cross-cascade reconciliation)
`#TBD-rest-api-cross-layer-coupling` (M05 — API → runtime mutation).
`#TBD-validator-strictness-context-dependent` (M06 — validate_workflow registry-dependent strictness).

### Existing real issues referenced
#177, #707, #827, #882, #887, #888, #889, #890, #908, #1015, #1016, #661, #1073, #1074, #1075, #1076, #1077, #1078, #1079, #1080, #1090 (this cascade's umbrella), #1091 (umbrella PR).

Total open-issue tracking surface: **~95 `#TBD-*` placeholders + 21 existing real refs ≈ 116 issues** to instantiate/link in Phase 9.

---

## Appendix C: Cross-cascade reconciliation summary

Two independent SSOT cascades ran in parallel (per user direction):

| Aspect | Claude Code (this side) | Codex (PR #1094) |
|---|---|---|
| Tracking branch | `track/spec-ssot` | `codex/review-architecture-and-planning-documents-27pf8w` |
| Umbrella PR | #1091 `[Claude Code] [DO NOT MERGE]` | #1094 (targets main directly) |
| Module count (N) | 13 (finer) | 9 (coarser) |
| Total entries | ~197 (per-interface) | 21 (per-principle) |
| a-class | ~82 (41%) | 10 (48%) |
| b-class | ~32 (16%) | 8 (38%) |
| c-class | ~15 (8%) | 3 (14%) |
| d-class | ~69 (35%) | **0** (Codex didn't enumerate d-class at all) |

**Convergence quality**: HIGH. No contradictions; complementary granularities.

**Convergent findings**:
- D=0 blocking-level contradictions (both sides agree)
- ADR-028 §D8 cluster (Codex: 1 principle entry; mine: full 5-issue cluster #1073-#1078)
- WS/SSE stringly-typed risk (both flag)
- Block/Port/DAG/AI-boundary core principles stable (a)
- versioning-git mostly d-class (Codex folded into M03/M05/M08; mine standalone §12)

**2 NEW findings from Codex** folded into draft v3 as cross-cutting C-class:
1. `rest-api.cross-layer-coupling` — API routes triggering runtime state mutations
2. `workflow-yaml.validator-strictness-variability` — validate_workflow depth depends on registry availability

**My cascade's unique value**: per-interface signature inventory (197 entries with full d-class detail per user direction), explicit `d-document` / `d-private` / `d-remove` sub-labels, complete ADR-028 §D8 5-issue cluster, WS inbound message name correction (`block_user_marked_done` not `user_message`), PROJECT_TREE.md vs ADR-027 D2 contradiction (cross-cutting NOT in Codex), versioning-git as standalone d-class module with 22 GitEngine method enumeration.

**Codex's unique value**: principle-level architectural framing (Module preambles lifted from Codex R2 reasoning), the 2 cross-cutting C-class entries above, broader coverage of plugin/test harness boundary (Codex's M09 mostly out of my scope).

**Authority for SSOT**: convergent decisions are authoritative. The 2 cross-cutting C-class entries from Codex are authoritative. Where granularity differs, mine wins (more grep-checkable; richer detail per user direction "拒绝压缩 D").

---

## Appendix D: Phase 7 audit attention (Z1/Z2 priorities)

Phase 7 post-write Z-auditors should verify, in priority order:

### Grammar + machine-checkability
1. Every entry's `Source:` anchor exists at the cited `file:Lnn-Lmm`. Run `python -m scripts.spec_audit.extract_spec` → no parse errors.
2. Every entry's `Primary-doc-source:` resolves OR is the explicit `[ARCHITECTURE: ...]` placeholder.
3. Every b/c/d entry has `Issue:` field (real # or `#TBD-*`).

### Content fidelity
4. Module 1 (block-abc): the b-code-wins decisions on `Block` ClassVars + `validate` / `postprocess` annotations should be re-validated against current code at baseline SHA `a4b8b5f`.
5. Module 7 (execution-engine): `save_checkpoint` + `load_checkpoint` (newly discovered by A4) — confirm signatures.
6. Module 8 (lineage-db): all 4 CREATE TABLE statements column-by-column against current `src/scieasy/core/lineage/store.py`.
7. Module 9 (rest-api): re-count actual REST routes (A6 said 61 vs C6's 42); re-list under each subcategory.
8. Module 12 (versioning-git): re-enumerate `GitEngine` public methods (currently 22 per C5/A5) against current code.

### Cross-cascade reconciliation verification
9. The 2 cross-cutting C-class entries match Codex's reasoning + reference Codex artifacts correctly.
10. `chatSlice` claim (Module 9): AX said it exists in both ARCH §9.10 AND PROJECT_TREE.md but C6's frontend code scan didn't find it. Re-verify against actual `frontend/src/store/` directory contents at baseline SHA.
11. `core.materialisation` placement (Module 5 cross-listed as block-abc concern + #1078): final placement is TBD per ARCH §4.7 zones; Phase 7 to recommend.

### Issue tracking completeness
12. Confirm all 95+ `#TBD-*` placeholders are accounted for (no orphans, no duplicates).
13. Confirm all 21+ existing real issue references (#177, #707, etc.) still open + relevant.

### Style + structure
14. Each module section has Module preamble — confirm Codex-derived principle text matches Codex R2 reasoning faithfully.
15. Sub-labels consistent within each class (b-code-wins / b-docs-wins / c-impl / c-drop / c-defer / d-document / d-private / d-remove).

---

## Pass 2 status: COMPLETE

All 13 modules + 2 cross-cutting C-class entries + 4 appendices written with full d-class detail per user direction (rejected compression of d-entries; SSOT is the authoritative interface contract regardless of implementation status).

**File size**: ~3500 lines / ~120KB (single-file SSOT per user choice in plan).

**Next**: STOP per user direction "推进到 phase 6 前 / 继续". Phase 7 (post-write Z-auditors) + Phase 8 (CI live + CLAUDE.md amendment) + Phase 9 (issue rollout + final merge) deferred to future session.

