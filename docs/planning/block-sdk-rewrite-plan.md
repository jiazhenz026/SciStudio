# Block Developer SDK Documentation — Rewrite Plan

**Date**: 2026-04-12
**Related issues**: #449, #505
**Motivation**: Current `docs/guides/block-sdk.md` is severely outdated. References ViewProxy (deleted in ADR-031), uses legacy metadata dict (replaced by three-slot model in ADR-027 D5), and is missing documentation for variadic ports, dynamic ports, IOBlock persist helpers, custom types, resource declarations, cancellation semantics, and streaming data access.

---

## 1. Document Set: `docs/block-development/`

### 1.1 `quickstart.md`

**Target audience**: New block developers, scientists with minimal Python experience.

**Sections**:
- What is a block? (3 sentences)
- Five-minute example: minimal ProcessBlock with `process_item()` override
- Show the three required ClassVars: `name`, `input_ports`, `output_ports`
- Where to save the file (`<project>/blocks/` or `~/.scistudio/blocks/`)
- Test it immediately (drop file, reload palette, create workflow)
- Next steps (pointers to other docs)

**ADR references**: ADR-020 (Tier 1 process_item), ADR-008 (Tier 1 drop-in files)

### 1.2 `architecture-for-block-devs.md`

**Target audience**: Block developers who need to understand the execution model.

**Sections**:
- Subprocess isolation guarantee (ADR-017): can use any library/CPU/memory, cannot share state
- Data transport across subprocess boundary (ADR-020): Collection serialization, StorageReference
- Block lifecycle: setup() → iterate → process_item() → auto-flush → teardown()
- Three tiers of Collection handling (ADR-020): Tier 1 (80%), Tier 2, Tier 3
- Memory safety patterns: auto-flush per item, streaming access, iter_chunks
- Cancellation semantics (ADR-018): engine kills subprocess, atomic writes for safety
- Resource hints (ADR-022): requires_gpu, cpu_cores, psutil monitoring

**ADR references**: ADR-017, ADR-018, ADR-019, ADR-020, ADR-022, ADR-031

### 1.3 `block-contract.md`

**Target audience**: Block developers who need the formal specification.

**Sections**:
- Block ABC and inheritance hierarchy (ProcessBlock, IOBlock, CodeBlock, AppBlock, AIBlock, SubWorkflowBlock)
- Required ClassVar declarations: name, description, input_ports, output_ports, config_schema
- Optional ClassVar declarations: version, subcategory, execution_mode, requires_gpu, cpu_cores, key_dependencies
- Variadic ports (ADR-029): variadic_inputs/outputs, allowed_types, min/max limits
- Dynamic ports (ADR-028 Addendum 1): dynamic_ports dict, get_effective_*_ports()
- The run() contract: signature, input/output format, exception handling
- Hooks: validate(), postprocess()
- ProcessBlock hooks: setup(config) → state, process_item(item, config, state), teardown(state)
- IOBlock hooks: load(config, output_dir), save(obj, config), persist_array(), persist_table()
- Config schema: JSON Schema + ui_widget hints (file_browser, directory_browser, port_editor, slider, text_area)
- Port constraints: custom validation functions on InputPort

**ADR references**: ADR-004, ADR-020, ADR-027 D7, ADR-028, ADR-029, ADR-030

### 1.4 `data-types.md`

**Target audience**: Block developers deciding what types to use.

**Sections**:
- Six core base types (ADR-001): DataObject, Array, Series, DataFrame, Text, Artifact
- Instance-level axes on Array (ADR-027 D1): required_axes, allowed_axes, canonical_order
- Array subclasses and when to use them (2D image, 3D stack, hyperspectral)
- Collection — the transport wrapper (ADR-020): construction, iteration, single-item semantics
- CompositeData with named slots
- Type inheritance and port matching (isinstance-based)
- Storage and lazy loading (ADR-031): to_memory(), sel(), iter_chunks()
- Metadata slots (ADR-027 D5): framework, meta, user
- When to load data into memory (decision matrix)

**ADR references**: ADR-001, ADR-020, ADR-027 D1/D5, ADR-031

### 1.5 `custom-types.md`

**Target audience**: Plugin developers creating domain-specific types.

**Sections**:
- Where domain types live (ADR-027 D2): plugins, not core
- Anatomy of a custom Array subclass: required_axes, allowed_axes, Meta Pydantic model
- Meta model constraints: frozen, no PrivateAttr, JSON-round-trippable
- Physical quantities and units (ADR-027 D8): PhysicalQuantity(value, unit)
- Plugin type registration via scistudio.types entry-point
- Worker subprocess type reconstruction (TypeRegistry.scan)
- Metadata immutability and derivation: with_meta()

**ADR references**: ADR-027 D2/D5/D8, ADR-025

### 1.6 `memory-safety.md`

**Target audience**: Block developers working with large datasets.

**Sections**:
- Tier 1: process_item() with auto-flush (O(1) peak memory)
- Tier 2: map_items() and parallel_map() with explicit control
- Tier 3: manual run() with pack()/unpack()
- Auto-flush mechanism: writes to project zarr directory per item
- Streaming data access: sel(), iter_chunks(), iterate_over_axes()
- Collection-level parallelism: workflow fan-out vs block-internal threading
- Memory hints and resource management (requires_gpu, cpu_cores)

**ADR references**: ADR-020, ADR-022, ADR-027 D7/D13

### 1.7 `collection-guide.md`

**Target audience**: Block developers working with multi-item data.

**Sections**:
- What is Collection? (ADR-020)
- Construction: `Collection(items=[...], item_type=Type)`
- Iteration patterns: for loop, index access, len()
- Single-item Collections: semantics and auto-unwrap
- Empty Collections: valid, meaningful for conditional workflows
- Utilities: unpack(), pack(), unpack_single()
- Storage and serialization: items serialized individually
- Advanced: merging Collections (MergeCollection block)

**ADR references**: ADR-020, ADR-021

### 1.8 `testing.md`

**Target audience**: Block developers writing tests.

**Sections**:
- BlockTestHarness overview: contract validation + smoke testing
- validate_block(): checks ABC compliance
- validate_entry_point_callable(): for Tier 2 packages
- smoke_test(inputs, params): in-process execution
- Test patterns: fixtures, synthetic data, assertions
- What NOT to test: subprocess behavior, cross-process serialization
- Testing Tier 1 drop-in blocks vs Tier 2 packages

**ADR references**: ADR-025, ADR-026

### 1.9 `publishing.md`

**Target audience**: Block developers distributing packages.

**Sections**:
- Tier 2 distribution via PyPI
- Package structure (pyproject.toml, src layout, tests)
- Entry-points: scistudio.blocks and scistudio.types
- PackageInfo declaration
- get_blocks() and get_types() callables
- README best practices
- Testing before release
- Versioning (semver)
- Optional dependencies

**ADR references**: ADR-008, ADR-025, ADR-026

### 1.10 `examples/` Directory

```
examples/
├── simple-transform/          # Minimal ProcessBlock
├── collection-processing/     # Tier 2 map_items(), parallel processing
├── custom-io-adapter/         # IOBlock loader for custom format
├── multi-block-package/       # Full Tier 2 package with pyproject.toml
├── stateful-processing/       # ProcessBlock with setup/teardown (ML model)
├── with-custom-types/         # Custom Array subclass + Meta model
└── appblock-integration/      # AppBlock for external software
```

Each example includes: complete working code, docstrings, test file, README walkthrough.

---

## 2. Block Scaffold Template

Generated by `scistudio new-block-package <name>`:

```
my-blocks/
├── pyproject.toml              # Entry-points, dependencies
├── README.md
├── src/
│   └── my_blocks/
│       ├── __init__.py         # get_blocks(), get_types()
│       ├── blocks/
│       │   ├── simple_process.py  # Example ProcessBlock
│       │   └── custom_io.py      # Example IOBlock
│       └── types/
│           └── my_types.py       # Example custom type (optional)
└── tests/
    ├── test_simple_process.py
    └── conftest.py
```

**Key principles for template**:
- NO `_data` direct access (use `to_memory()`)
- NO ViewProxy usage
- NO monkey-patching or global state
- Shows `persist_array()` / `persist_table()` for IOBlock
- Shows three-argument `process_item(self, item, config, state)`
- Shows config_schema with ui_widget hints
- Shows test with BlockTestHarness

---

## 3. Feature Coverage Checklist

### Block Categories & Inheritance
- [ ] ProcessBlock, IOBlock, CodeBlock, AppBlock, AIBlock, SubWorkflowBlock

### ClassVar Declarations
- [ ] name, description, version, subcategory
- [ ] input_ports, output_ports, config_schema
- [ ] execution_mode, terminate_grace_sec, key_dependencies
- [ ] requires_gpu, cpu_cores

### Processing & Lifecycle
- [ ] run() contract, validate(), postprocess()
- [ ] setup/teardown lifecycle (3-arg process_item with state)
- [ ] Tier 1/2/3 processing tiers
- [ ] Auto-flush mechanism

### Variadic Ports (ADR-029)
- [ ] variadic_inputs/outputs, allowed_types, min/max limits
- [ ] get_effective_*_ports()

### Dynamic Ports (ADR-028 Add1)
- [ ] dynamic_ports ClassVar, source_config_key

### Config Schema
- [ ] JSON Schema + ui_widget hints
- [ ] MRO merge (ADR-030)

### Data Types & Collection
- [ ] Six core types, Collection, CompositeData
- [ ] Array axes (instance-level, required/allowed)
- [ ] Lazy loading: to_memory, sel, iter_chunks, iter_over

### Metadata (ADR-027 D5)
- [ ] framework, meta, user slots
- [ ] Meta Pydantic model declaration
- [ ] with_meta() immutable updates

### Custom Types & Plugins
- [ ] Domain types in plugins
- [ ] scistudio.types entry-point
- [ ] PhysicalQuantity

### Storage & Persistence (ADR-031)
- [ ] StorageReference, lazy loading
- [ ] IOBlock persist helpers
- [ ] Artifact path-only transport

### Subprocess Isolation (ADR-017)
- [ ] Can use any lib/CPU/memory
- [ ] Cannot share state, hold connections

### Cancellation (ADR-018)
- [ ] CANCELLED/SKIPPED states
- [ ] Atomic write patterns

### Testing (ADR-026)
- [ ] BlockTestHarness: validate_block, smoke_test

### Distribution (ADR-025)
- [ ] Tier 1 drop-in, Tier 2 PyPI
- [ ] Entry-points protocol

---

## 4. Current block-sdk.md Issues

### Outdated
- ViewProxy as primary data access pattern (ADR-031 deleted ViewProxy)
- Legacy `metadata={}` dict (replaced by framework/meta/user three-slot model)
- 2-argument process_item (now 3-argument with state)
- "Read source" punts instead of documenting

### Missing entirely
- Variadic ports (ADR-029)
- Dynamic ports (ADR-028 Add1)
- IOBlock persist helpers (ADR-031 D4)
- Custom types in plugins (ADR-027 D2)
- Metadata three-slot model (ADR-027 D5)
- Instance-level axes (ADR-027 D1)
- Lazy loading / streaming access (ADR-031)
- Resource hints (ADR-022)
- Cancellation semantics (ADR-018)

### Recommendation
**Delete** current `docs/guides/block-sdk.md` and replace with the 10-document set in `docs/block-development/`.
