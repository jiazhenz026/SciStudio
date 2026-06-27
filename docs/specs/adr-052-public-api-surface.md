---
spec_id: adr-052-public-api-surface
title: "ADR-052 Public API Surface Inventory And Per-Symbol Contract"
status: Draft
feature_branch: guided/1819-public-api-contract-adr
created: 2026-06-27
input: "Owner-directed live session (guided/#1819, PR #1821): produce the exhaustive per-symbol public API contract that ADR-052 §3 defers to the implementation phase. Walk each governed module file by file and record, for every public-surface symbol, its public/internal disposition, stability tier, Since baseline, canonical import path, and reach-through classification, as the authoritative inventory the #1817 implementation transcribes into __all__ and stability decorators. Scope covers core modules, domain packages, and affected documentation."
owners:
  - "@jiazhenz026"
related_adrs:
  - 52
related_specs: []
scope:
  in:
    - Per-symbol public/internal disposition for the core public surface ADR-052 §3 names (scistudio.core.types, scistudio.blocks.base, scistudio.blocks.process, scistudio.blocks.io, scistudio.blocks.app, scistudio.previewers.models).
    - The stability tier (stable/provisional/internal) and Since baseline version for each public symbol, per ADR-052 §5.
    - The canonical root import path for each public symbol, per ADR-052 §2.
    - The ergonomic accessor surface (ADR-052 §3.1) and large-data surface (ADR-052 §3.2) as concrete per-type method rows.
    - The reach-through register (ADR-052 §6) classifying each known internal reach (a/b/c) with its disposition.
    - The plot render(collection) shape contract (ADR-052 §3) as a documented non-import surface.
    - The package public surface (ADR-052 §4) — the contract rules every package satisfies and the per-package reuse-surface inventory for the domain packages.
    - The affected documentation surface — the docs that must change when the contract lands (ADR-052 §7 and author/architecture guides).
    - The enforcement and anti-drift design that keeps the contract from changing silently, and the #1817 implementation sequence.
  out:
    - Writing __all__ declarations or stability decorators into source (the #1817 implementation phase; touches protected core and is out of this docs-only PR).
    - Implementing the mkdocstrings/griffe documentation build and doc-versioning machinery (ADR-052 §7; tracked by #1817). This doc inventories the affected docs; it does not build them.
    - Editing the external domain package repositories themselves (their per-symbol decisions are recorded here, then transcribed in-repo against each package's own version line).
    - Any change to the canonical to_memory() form or the ADR-031 storage/interchange decision.
governs:
  modules: []
  contracts: []
  entry_points: []
  files:
    - docs/specs/adr-052-public-api-surface.md
  excludes:
    - docs/user/reference/**
    - docs/user/llms.txt
planned_governs:
  modules: []
  contracts: []
  entry_points: []
  files: []
  excludes: []
tests:
  - tests/api/test_public_surface.py
  - tests/api/test_stability_decorators.py
  - tests/api/test_ergonomic_accessors.py
acceptance_source: adr
language_source: en
---

# ADR-052 Public API Surface Inventory And Per-Symbol Contract

## 1. Purpose And How To Read This

ADR-052 is the **policy**: it draws the public/private boundary (canonical root
import paths, `__all__`-defined membership), defines the three stability tiers and
the `Since`/deprecation rules, and names the core public surface at the level of
"these modules, this kind of symbol". It deliberately stops short of the
exhaustive per-symbol list — ADR-052 §3 says "the exhaustive per-symbol `__all__`
is produced in the implementation phase".

**This document is that per-symbol list.** It is the authoritative inventory that,
for every symbol on the governed surface, records:

- whether it is **Public** or **Internal** (ADR-052 §2),
- its **stability tier** — `stable` / `provisional` / `internal` (ADR-052 §5),
- its **`Since`** baseline (ADR-052 §5),
- the **canonical import path** an author uses (ADR-052 §2), and
- for internal reach-through, its **classification (a/b/c)** and disposition
  (ADR-052 §6).

It does **not** edit source. The actual `__all__` declarations and
`@stable`/`@provisional`/`@internal` decorators are written into the modules in
the #1817 implementation phase, which transcribes the decisions recorded here.
Keeping the decisions in this doc first means the boundary is settled and reviewed
once, as data, before any protected-core edit.

This is the contract we are committing to defend across releases once we enter
alpha; treat each row as a promise, not a description.

## 2. Conventions

### 2.1 Per-symbol table columns

Each module section carries one table with these columns:

| Column | Meaning |
|---|---|
| **St** | Decision status — see §2.2 |
| **Symbol** | The symbol name as authors would import or call it |
| **Kind** | `class` / `method` / `function` / `constant` / `type-alias` / `protocol` |
| **Disposition** | `Public` (enters `__all__`) / `Internal` (excluded) / `Reach-through (a\|b\|c)` per ADR-052 §6 |
| **Tier** | `stable` / `provisional` / `internal`; `—` until decided |
| **Since** | First version the symbol is public on this surface; `—` until decided |
| **Notes** | Rationale, open questions, links to reach-through rows, deprecation intent |

The **canonical import path** is stated once per module section (it is the same
root for every public symbol in that module, by ADR-052 §2), not repeated per row.

### 2.2 Decision status markers

| Marker | Meaning |
|---|---|
| ✅ | Decided this session (or already fixed by ADR-052 with the cited section) |
| 🤔 | Open — needs a decision before this contract is complete |
| ⏸ | Deferred to a tracked follow-up (cite the issue in Notes) |
| ➖ | Internal by inspection; listed so the file is accounted for, no promise attached |

A module section is complete only when its file checklist is fully ticked and no
row is left 🤔.

### 2.3 `Since` baseline

The initial contract baseline is **`0.3.1`** — the current `BASE_VERSION` on
`main` (`src/scistudio/_version.py`), the version line the declared
`__all__`/decorator surface ships in. A symbol that has existed in code for many
releases still records `since="0.3.1"` because that is when it *first became
public on its declared surface* (ADR-052 §5). Symbols added after the baseline
record their own later version.

> Branch note: this branch (`guided/1819-public-api-contract-adr`) still carries
> `BASE_VERSION = 0.3.0` and is ~10 commits behind `main` (now `0.3.1`). It must
> catch up to `main` before finalize so the baseline matches the shipping line.

### 2.4 Tier defaults

Per ADR-052 §5: `stable` = supported, no incompatible change within a major
version without deprecation; `provisional` = usable but may change in a minor
release with a changelog note; `internal` = no promise, excluded from docs. When a
symbol's tier is undecided, prefer the **narrowest honest** tier (a brand-new,
still-settling surface is `provisional`, not `stable`).

## 3. Core Data Types — `scistudio.core.types`

Canonical root: `from scistudio.core.types import …`

The root `__init__.py` already declares an `__all__`; reconcile this inventory
against it during fill-in. Each file gets a subsection (§3.x) below with its
module exports and per-class member tables — recorded at **method level**, since
the freeze snapshot (§15) covers the public methods of public classes.

File checklist:

- [x] `base.py` (553) — `DataObject`, `TypeSignature` → §3.1
- [x] `array.py` (450) — `Array` → §3.2
- [x] `dataframe.py` (132) — `DataFrame` → §3.3
- [x] `series.py` (152) — `Series` → §3.4
- [x] `text.py` (129) — `Text` → §3.5
- [x] `artifact.py` (131) — `Artifact` → §3.6
- [x] `composite.py` (152) — `CompositeData` → §3.7
- [x] `collection.py` (83) — `Collection` → §3.8
- [~] `registry.py` (647) — `TypeRegistry`/`TypeSpec` (in `__all__` today) → §3.9; disposition pending survey
- [x] `serialization.py` (379) — fully internal → §3.9
- [x] `_backend_defaults.py` (56) — internal module → §3.9

Cross-module symbols surfaced by these files but **defined outside** `core/types/`
(part of the core.types author surface via re-export — canonical path
`scistudio.core.types`): `StorageReference` (`scistudio.core.storage.ref`),
`FrameworkMeta` and the `with_meta_changes` helper (`scistudio.core.meta`). Flagged
in §17 because `scistudio.core.meta` / `scistudio.core.storage` are not in ADR-052
`governs.modules`.

### 3.1 `base.py`

Module exports (`__all__`): `DataObject`, `TypeSignature` public; `_get_backend`,
`_SIZE_WARNING_THRESHOLD` internal.

**`TypeSignature`** (dataclass) — ✅ Public / `stable` / 0.3.1. Read-mostly type
descriptor (authors rarely construct it; used by port type checks).

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `TypeSignature` | class | Public | stable | 0.3.1 | owner 2026-06-27 |
| ✅ | `type_chain` / `slot_schema` / `required_axes` | field | Public | stable | 0.3.1 | dataclass fields |
| ✅ | `matches(other)` | method | Public | stable | 0.3.1 | |
| ✅ | `from_type(data_type)` | classmethod | Public | stable | 0.3.1 | |

**`DataObject`** — ✅ Public / `stable` / 0.3.1. The base every data type subclasses.

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `DataObject` | class | Public | stable | 0.3.1 | base type |
| ✅ | `Meta` | ClassVar | Public | stable | 0.3.1 | Meta-model pattern; authors override |
| ✅ | `__init__(*, framework, meta, user, storage_ref)` | method | Public | stable | 0.3.1 | base ctor; subclasses add `data=` |
| ✅ | `framework` / `meta` / `user` | property | Public | stable | 0.3.1 | ADR-027 three-slot |
| ✅ | `with_meta(**changes)` | method | Public | stable | 0.3.1 | immutable update (ADR-052 §3) |
| ✅ | `dtype_info` | property | Public | stable | 0.3.1 | → `TypeSignature` |
| ✅ | `storage_ref` (getter + setter) | property | Public | stable | 0.3.1 | setter also public (owner 2026-06-27) |
| ✅ | `to_memory()` | method | Public | stable | 0.3.1 | canonical reader (§10) |
| ✅ | `slice(*args)` | method | Public | stable | 0.3.1 | §11 large-data |
| ✅ | `iter_chunks(chunk_size)` | method | Public | stable | 0.3.1 | §11 large-data |
| ✅ | `save(path)` | method | Public | provisional | 0.3.1 | manual persist; framework usually auto-flushes (owner 2026-06-27) |
| ✅ | `get_in_memory_data()` | method | Internal | — | — | persistence path; authors use `to_memory()` (owner 2026-06-27) |
| ✅ | `serialise_extra_metadata(obj)` | classmethod | Public (de-underscore #1817) | provisional | 0.3.1 | owner 2026-06-27 (opt. A); 0/6 packages override (all via `Meta`) → provisional; pair |
| ✅ | `reconstruct_extra_kwargs(metadata)` | classmethod | Public (de-underscore #1817) | provisional | 0.3.1 | owner 2026-06-27 (opt. A); symmetric pair with serialise |
| ⏸ | `metadata` property + `metadata=` kwarg | property/param | Removed | — | — | deprecated shim; Phase 11 passed → delete in #1817 (owner 2026-06-27) |
| ➖ | `_data` / `_arrow_table` | property | Internal | — | — | transient-data bridges (removed once callers migrate) |
| ➖ | `_validate_user(user)` | staticmethod | Internal | — | — | JSON-serialisable check |

The reconstruction-hook pair (`reconstruct_extra_kwargs` / `serialise_extra_metadata`)
is published as a `provisional` author extension point (owner 2026-06-27, option A).
Three rules — already encoded in core and its tests — go into the contract: (1) they
are a **symmetric pair**: override both or neither (`CompositeData` overrides neither;
its slots recurse through the serializer); (2) the override pattern is
**`super()`-chain-then-extend**, not replace; (3) `serialise_*` output must be
JSON-serialisable (tuples→lists, `Path`→`str`, dtype→canonical string) and
`reconstruct_*` must invert exactly those conversions. `provisional` reflects that
no package overrides them today (0/6 — all route extra state through `Meta`), so the
exact contract may still settle.

Cross-module symbols surfaced by `base.py`: `StorageReference`
(`core.storage.ref`) — Public via the `core.types` re-export (ADR-052 §3);
`FrameworkMeta` (`core.meta`) — read-only author surface (`obj.framework`); decide
public-read vs internal. `with_meta_changes` (`core.meta`) — internal helper
(authors use the `with_meta` method). See the §17 governed-modules gap.

### 3.2 `array.py`

Module exports (`__all__`): `Array` public. No other module-level symbols.

**`Array`** — ✅ Public / `stable` / 0.3.1. N-dimensional array with named axes
(`DataObject` subclass).

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `Array` | class | Public | stable | 0.3.1 | |
| ✅ | `required_axes` / `allowed_axes` / `canonical_order` | ClassVar | Public | stable | 0.3.1 | axis schema; subclasses override (like `Meta`) |
| ✅ | `__init__(*, axes, shape, dtype, chunk_shape, data, **kwargs)` | method | Public | stable | 0.3.1 | `data=` ctor (ADR-031); `axes` required |
| ✅ | `axes` / `shape` / `dtype` / `chunk_shape` | attribute | Public | stable | 0.3.1 | kept **writable** (owner 2026-06-27) |
| ✅ | `ndim` | property | Public | stable | 0.3.1 | |
| ✅ | `__array__(dtype, copy)` | method | Public | stable | 0.3.1 | `np.asarray(arr)` protocol |
| ✅ | `sel(**axes)` | method | Public | stable | 0.3.1 | §11 large-data |
| ✅ | `with_meta(**changes)` | method | Public | stable | 0.3.1 | override (propagates axes/shape/dtype/chunk_shape) |
| ✅ | `to_memory()` | method | Public | stable | 0.3.1 | override (transient-data transition) |
| ✅ | `to_numpy()` **[new]** | method | Public | stable | 0.3.1 | §10 — to be ADDED in #1817 (not present today) |
| ⏸ | `iter_over(axis)` | method | Internal | internal | — | owner 2026-06-27: keep internal pending imaging rewrite; axis-iteration surface (cf. `axis_iter` §12, #1729) unsettled |
| ✅ | `reconstruct_extra_kwargs` / `serialise_extra_metadata` | classmethod | Public (de-underscore #1817) | provisional | 0.3.1 | `Array` overrides both (axes/shape/dtype/chunk_shape); per §3.1 opt-A |
| ➖ | `_validate_axes()` | method | Internal | — | — | |

### 3.3 `dataframe.py`

Module exports (`__all__`): `DataFrame` public. No other module-level symbols. No
new decisions — follows the `base.py`/`array.py` patterns + §10 + the hook decision.

**`DataFrame`** — ✅ Public / `stable` / 0.3.1. Columnar tabular data, Arrow/Parquet-backed.

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `DataFrame` | class | Public | stable | 0.3.1 | |
| ✅ | `__init__(*, columns, row_count, schema, data, **kwargs)` | method | Public | stable | 0.3.1 | `data=` ctor (ADR-031) |
| ✅ | `columns` / `row_count` / `schema` | attribute | Public | stable | 0.3.1 | writable (per array.py decision) |
| ✅ | `with_meta(**changes)` | method | Public | stable | 0.3.1 | override (propagates columns/row_count/schema) |
| ✅ | `to_pandas()` **[new]** | method | Public | stable | 0.3.1 | §10 — to be ADDED in #1817 |
| ✅ | `to_numpy()` **[new]** | method | Public | stable | 0.3.1 | §10 — to be ADDED in #1817 |
| ✅ | `reconstruct_extra_kwargs` / `serialise_extra_metadata` | classmethod | Public (de-underscore #1817) | provisional | 0.3.1 | overrides for columns/row_count/schema; per §3.1 opt-A |

Inherits the rest of the public surface from `DataObject` (§3.1): `to_memory()`
(returns a `pyarrow.Table` — canonical form, §3.1/§10), `slice()` (row range),
`iter_chunks()` (Parquet row batches) per §11, `save()`, `framework`/`meta`/`user`,
`dtype_info`, `storage_ref`, `Meta`.

### 3.4 `series.py`

Module exports (`__all__`): `Series` public; `_series_table_payload` internal. No
new decisions — mirrors `dataframe.py` + §10 + the hook decision.

**`Series`** — ✅ Public / `stable` / 0.3.1. One-dimensional indexed data
(time series / chromatogram / spectrum), Arrow/Parquet-backed.

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `Series` | class | Public | stable | 0.3.1 | |
| ✅ | `__init__(*, index_name, value_name, length, data, **kwargs)` | method | Public | stable | 0.3.1 | `data=` ctor (ADR-031) |
| ✅ | `index_name` / `value_name` / `length` | attribute | Public | stable | 0.3.1 | writable (per array.py decision) |
| ✅ | `with_meta(**changes)` | method | Public | stable | 0.3.1 | override (propagates index_name/value_name/length) |
| ✅ | `to_pandas()` **[new]** | method | Public | stable | 0.3.1 | §10 → `pandas.Series`; add in #1817 |
| ✅ | `to_numpy()` **[new]** | method | Public | stable | 0.3.1 | §10 → ndarray; add in #1817 |
| ✅ | `reconstruct_extra_kwargs` / `serialise_extra_metadata` | classmethod | Public (de-underscore #1817) | provisional | 0.3.1 | overrides for index_name/value_name/length; per §3.1 opt-A |
| ➖ | `get_in_memory_data()` | method | Internal | — | — | override (normalises to `pyarrow.Table`); base decided Internal |
| ➖ | `_series_table_payload(...)` | function | Internal | — | — | module-level helper |

Inherits the rest from `DataObject` (§3.1): `to_memory()` (→ `pyarrow.Table`, one
column), `slice()`, `iter_chunks()` (§11), `save()`, `framework`/`meta`/`user`,
`dtype_info`, `storage_ref`, `Meta`.

### 3.5 `text.py`

Module exports (`__all__`): `Text` public. No new decisions — same pattern; note the
constructor takes `content=` (the str payload) rather than `data=`, and `Text` adds
no ergonomic accessor (its canonical `to_memory()` is already `str`, §10).

**`Text`** — ✅ Public / `stable` / 0.3.1. Plain text / markdown / JSON content.

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `Text` | class | Public | stable | 0.3.1 | |
| ✅ | `__init__(*, content, format, encoding, **kwargs)` | method | Public | stable | 0.3.1 | payload via `content=` (not `data=`) |
| ✅ | `content` / `format` / `encoding` | attribute | Public | stable | 0.3.1 | writable |
| ✅ | `with_meta(**changes)` | method | Public | stable | 0.3.1 | override |
| ✅ | `reconstruct_extra_kwargs` / `serialise_extra_metadata` | classmethod | Public (de-underscore #1817) | provisional | 0.3.1 | overrides for content/format/encoding; per §3.1 opt-A |
| ➖ | `get_in_memory_data()` | method | Internal | — | — | override (returns `content`); base decided Internal |

Inherits from `DataObject` (§3.1): `to_memory()` (→ `str`), `save()`,
`framework`/`meta`/`user`, `dtype_info`, `storage_ref`, `Meta`. No `to_pandas`/
`to_numpy` (already ergonomic, §10).

### 3.6 `artifact.py`

Module exports (`__all__`): `Artifact` public. No new decisions — payload via
`file_path=`, no ergonomic accessor (canonical `to_memory()` is a `pathlib.Path`, §10).

**`Artifact`** — ✅ Public / `stable` / 0.3.1. Opaque file artifact (PDF, binary, report).

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `Artifact` | class | Public | stable | 0.3.1 | |
| ✅ | `__init__(*, file_path, mime_type, description, **kwargs)` | method | Public | stable | 0.3.1 | payload via `file_path=` |
| ✅ | `file_path` / `mime_type` / `description` | attribute | Public | stable | 0.3.1 | writable |
| ✅ | `with_meta(**changes)` | method | Public | stable | 0.3.1 | override |
| ✅ | `reconstruct_extra_kwargs` / `serialise_extra_metadata` | classmethod | Public (de-underscore #1817) | provisional | 0.3.1 | overrides for file_path/mime_type/description; per §3.1 opt-A |
| ➖ | `get_in_memory_data()` | method | Internal | — | — | override (returns file bytes); base decided Internal |

Inherits from `DataObject` (§3.1): `to_memory()` (→ `pathlib.Path`), `save()`,
`framework`/`meta`/`user`, `dtype_info`, `storage_ref`, `Meta`. No `to_pandas`/`to_numpy` (§10).

### 3.7 `composite.py`

Module exports (`__all__`): `CompositeData` public. The slot API is public; this is
the **hook exception** — `CompositeData` overrides *neither* reconstruction hook (its
slots are nested `DataObject`s; the serializer owns the recursion — agent survey +
ADR-027 note in source).

**`CompositeData`** — ✅ Public / `stable` / 0.3.1. Named collection of heterogeneous `DataObject` slots.

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `CompositeData` | class | Public | stable | 0.3.1 | |
| ✅ | `expected_slots` | ClassVar | Public | stable | 0.3.1 | subclass declares slot→type schema (like `Meta`) |
| ✅ | `__init__(*, slots, **kwargs)` | method | Public | stable | 0.3.1 | payload via `slots=` (child DataObjects) |
| ✅ | `get(slot_name)` | method | Public | stable | 0.3.1 | retrieve a slot |
| ✅ | `set(slot_name, data)` | method | Public | stable | 0.3.1 | store a slot (validates vs `expected_slots`); mutable |
| ✅ | `slot_types()` | method | Public | stable | 0.3.1 | expected slot→type mapping |
| ✅ | `slot_names` | property | Public | stable | 0.3.1 | populated slot names |
| ✅ | `with_meta(**changes)` | method | Public | stable | 0.3.1 | override (shares slots by ref) |
| ➖ | `get_in_memory_data()` | method | Internal | — | — | override; base decided Internal |
| ➖ | `_slots` | attribute | Internal | — | — | populated-slot storage |
| — | reconstruction hooks | classmethod | **not overridden** | — | — | hook exception; serializer owns slot recursion |

Inherits from `DataObject` (§3.1): `to_memory()` (→ `dict[str, native]`), `save()`,
`framework`/`meta`/`user`, `dtype_info`, `storage_ref`. No `to_pandas`/`to_numpy` (§10).

### 3.8 `collection.py`

Module exports (`__all__`): `Collection` public. `Collection` is **not** a
`DataObject` (ADR-020) — it is the homogeneous inter-block transport wrapper.

**`Collection`** — ✅ Public / `stable` / 0.3.1. Ordered homogeneous container of `DataObject`s.

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `Collection` | class | Public | stable | 0.3.1 | ADR-020 transport wrapper (not a DataObject) |
| ✅ | `__init__(items=None, item_type=None)` | method | Public | stable | 0.3.1 | positional (not kw-only); empty needs explicit `item_type` |
| ✅ | `item_type` | property | Public | stable | 0.3.1 | immutable element type |
| ✅ | `length` | property | Public | stable | 0.3.1 | |
| ✅ | `__iter__` / `__len__` / `__getitem__` | method | Public | stable | 0.3.1 | container protocol (slice returns list) |
| ✅ | `__class_getitem__` | method | Public | stable | 0.3.1 | `Collection[Image]` annotation syntax |
| ✅ | `__repr__` | method | Public | stable | 0.3.1 | `Collection[Type](length=N)` display string (format not load-bearing) |
| ✅ | `storage_refs` | property | Public | stable | 0.3.1 | per-item StorageReference list |
| ➖ | `_items` / `_item_type` | attribute | Internal | — | — | `__slots__` |

✅ **Not the plot `collection`** (confirmed, owner 2026-06-27). The plot
`render(collection)` contract (§9) describes a *different* object (ADR-048 plot-render:
`.types`, `.items.open()/open_one()`, `item.type/metadata/open()`) that merely shares
the name. This `core.types.Collection` (ADR-020 transport wrapper) is inventoried above
as-is; the plot object is located and inventoried in the §8/§9 plot-preview pass (§17).

### 3.9 `registry.py`, `serialization.py`, `_backend_defaults.py`

**`serialization.py`** — ✅ fully **Internal** (owner 2026-06-27). DataObject
serialise/reconstruct for worker transport; no public symbols (all underscore). Calls
the §3.1 reconstruction-hook pair polymorphically and owns the `CompositeData` slot
recursion.

**`_backend_defaults.py`** — ➖ **Internal** module (underscore name). `build_default()`
wires the default type→backend router; not re-exported, not author-facing.

**`registry.py`** — `TypeRegistry` and `TypeSpec` are **currently in
`core.types.__all__`** (public today), but ADR-052 §3 does not list them and the core
sweep found **0 author-facing importers** (all internal: serialization, api/runtime,
engine/worker, ai/agent mcp). Background survey complete (2nd agent, 2026-06-27):
**0 author-facing importers** in core src or either public package — both packages
touch `TypeRegistry` only in tests via the internal path, and `TypeSpec` has no
external reader at all. **Recommend demote both to internal (option B)**; awaiting
owner confirm. Caveat: `tests/contracts/test_runtime_import_contract.py` frames a
"TypeRegistry public-API contract" to reconcile with the internal disposition in #1817.

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| 🤔 | `TypeRegistry` | class | pending (lean Internal) | — | — | mutable runtime registry (register/scan/resolve); 0 author importers in core |
| 🤔 | `TypeSpec` | dataclass | pending (lean Internal) | — | — | located-type descriptor (name/module_path/class_name/base_type/description) |

Recommendation pending the survey: **demote both to internal** (option B) — the
author-facing "what types exist" need is ADR-052 §4.4's separate read-only discovery
API (#1817), not the raw mutable registry.

## 4. Block Authoring — `scistudio.blocks.base`

Canonical root: `from scistudio.blocks.base import …`

File checklist:

- [ ] `block.py` (507) — `Block`
- [ ] `config.py` (33) — `BlockConfig`
- [ ] `ports.py` (170) — `InputPort`, `OutputPort`
- [ ] `state.py` (38) — `ExecutionMode`
- [ ] `package_info.py` (44) — `PackageInfo`
- [ ] `interactive.py` (367) — `InteractiveMixin`, `InteractivePrompt`, `PanelManifest` (ADR-051)
- [ ] `exceptions.py` (21) — block exceptions; public?
- [ ] `result.py` (20) — block result; public?

| St | Symbol | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| 🤔 | `Block` | class | Public | — | — | shared contract base |
| 🤔 | `BlockConfig` | class | Public | — | — | config base |
| 🤔 | `InputPort` | class | Public | — | — | |
| 🤔 | `OutputPort` | class | Public | — | — | |
| 🤔 | `ExecutionMode` | enum | Public | — | — | |
| 🤔 | `PackageInfo` | class | Public | — | — | registration handshake (ADR-025) |
| 🤔 | `InteractiveMixin` | class | Public | — | — | ADR-051 |
| 🤔 | `InteractivePrompt` | class | Public | — | — | ADR-051 |
| 🤔 | `PanelManifest` | class | Public | — | — | ADR-051 |
| 🤔 | (exceptions) | class | Public? | — | — | enumerate from exceptions.py |
| 🤔 | (result) | class | Public? | — | — | enumerate from result.py |

`AIBlock` and `SubWorkflowBlock` are **out of the public surface** (decided
2026-06-27; ADR-052 §3 corrected): they are runtime base classes the engine and
the embedded agent compose, not an author extension point.

## 5. Process Blocks — `scistudio.blocks.process`

Canonical root: `from scistudio.blocks.process import …`

File checklist:

- [ ] `process_block.py` (206) — `ProcessBlock`
- [ ] `utils.py` (23) — public helper, or internal?

| St | Symbol | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| 🤔 | `ProcessBlock` | class | Public | — | — | the base authors subclass |
| 🤔 | (utils contents) | function | Public? | — | — | enumerate from utils.py |

## 6. IO Blocks — `scistudio.blocks.io`

Canonical root: `from scistudio.blocks.io import …`

File checklist:

- [ ] `io_block.py` (300) — `IOBlock`
- [ ] `simple_io.py` (152) — simple loader/saver helpers (ADR-052 §3)
- [ ] `capabilities.py` (232) — capability surface; public or internal?
- [ ] `materialisation.py` (472) — has `__all__`; confirm what is author-facing
- [ ] `_unified_dispatch.py` (363) — expected internal
- [ ] `_config_enrichment.py` (73) — expected internal

| St | Symbol | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| 🤔 | `IOBlock` | class | Public | — | — | |
| 🤔 | (simple loader/saver) | class | Public | — | — | enumerate from simple_io.py |
| 🤔 | (capabilities) | ? | Public? | — | — | decide author-facing vs runtime-only |
| 🤔 | (materialisation `__all__`) | ? | ? | — | — | reconcile existing `__all__` |

## 7. App Blocks — `scistudio.blocks.app`

Canonical root: `from scistudio.blocks.app import …`

ADR-052 §6 flags this module as a reach-through hotspot (`_guess_mime`,
`_PopenProcessAdapter`); AppBlock authoring surface is "incomplete" today.

File checklist:

- [ ] `app_block.py` (499) — `AppBlock`, `_PopenProcessAdapter` (reach-through)
- [ ] `bridge.py` (456) — file-exchange/bridge; `_guess_mime` (reach-through)
- [ ] `watcher.py` (159) — file watcher facilities
- [ ] `command_validator.py` (67) — public or internal?

| St | Symbol | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| 🤔 | `AppBlock` | class | Public | — | — | |
| 🤔 | (file-exchange/watcher) | ? | Public | — | — | ADR-052 §3 "file-exchange/watcher facilities" — enumerate |
| 🤔 | `_guess_mime` | function | Reach-through (a) | — | — | see §12; needs public home |
| 🤔 | `_PopenProcessAdapter` | class | Reach-through (a) | — | — | see §12; needs public home |

## 8. Previewer Authoring — `scistudio.previewers.models`

Canonical root: `from scistudio.previewers.models import …` (ADR-048)

`models.py` already declares an `__all__`; reconcile against it.

File checklist:

- [ ] `models.py` (650) — `PreviewerSpec`, `FrontendManifest`, owner-kind + API-version constants, preview-error types

| St | Symbol | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| 🤔 | `PreviewerSpec` | class | Public | — | — | ADR-048 |
| 🤔 | `FrontendManifest` | class | Public | — | — | |
| 🤔 | (owner-kind constants) | constant | Public | — | — | enumerate |
| 🤔 | (API-version constants) | constant | Public | — | — | enumerate |
| 🤔 | (preview-error types) | class | Public | — | — | enumerate |

## 9. Plot `render(collection)` Contract

Canonical usage: a plot script **imports nothing** from `scistudio`. The public
surface is the shape of the `collection` object the harness passes, plus the
return contract (ADR-052 §3). It is documented here as a supported authoring usage
even though it has no importable symbol.

| St | Surface element | Disposition | Since | Notes |
|----|-----------------|-------------|-------|-------|
| 🤔 | `collection.types` | Public (shape) | — | |
| 🤔 | `collection.items.open()` / `open_one()` | Public (shape) | — | |
| 🤔 | `item.type` / `item.metadata` / `item.open()` | Public (shape) | — | |
| 🤔 | return contract (figure object or artifact path) | Public (shape) | — | confirm exact accepted return types |

## 10. Ergonomic Accessors (ADR-052 §3.1)

Public-only, additive, read-only. They wrap `to_memory()` and never replace it.
Packages **inherit, never redefine** (ADR-052 §4.2). Kept out of the core
data-flow path by guard (ADR-052 §8). ADR-052 §3.1 fixes these as `@stable` from
the core version that ships them → baseline `0.3.1`.

| St | Type | Accessor | Returns | Tier | Since | Notes |
|----|------|----------|---------|------|-------|-------|
| ✅ | `Array` | `to_numpy()` | `ndarray` | stable | 0.3.1 | explicit alias of inherited reader |
| ✅ | `DataFrame` | `to_pandas()` | `pandas.DataFrame` | stable | 0.3.1 | |
| ✅ | `DataFrame` | `to_numpy()` | `ndarray` | stable | 0.3.1 | |
| ✅ | `Series` | `to_pandas()` | `pandas.Series` | stable | 0.3.1 | |
| ✅ | `Series` | `to_numpy()` | `ndarray` | stable | 0.3.1 | |

`Text` / `Artifact` / `CompositeData` add no accessor (already ergonomic). The
single sanctioned pandas-using data-flow exception is the planned `.xlsx` loader
(#1810), per ADR-052 §3.1.

## 11. Large-Data Access (ADR-052 §3.2)

Read/write without materializing the whole object. ADR-052 §3.2 fixes these as
`@stable`.

| St | Method | On | Semantics | Tier | Since | Notes |
|----|--------|----|-----------|------|-------|-------|
| ✅ | `sel(**axes)` | `Array` | partial read by named axes (Zarr) | stable | 0.3.1 | |
| ✅ | `slice(...)` | `DataObject` | array sub-region / row range / byte range | stable | 0.3.1 | confirm signature |
| ✅ | `iter_chunks(chunk_size)` | `DataObject` | streaming chunks / row batches / byte chunks | stable | 0.3.1 | confirm signature |
| ✅ | `persist_array(...)` | `Block` | streaming array write (Zarr) | stable | 0.3.1 | confirm signature |
| ✅ | `persist_table(...)` | `Block` | streaming table write (Arrow/Parquet) | stable | 0.3.1 | confirm signature |

## 12. Reach-Through Register (ADR-052 §6)

Every known reach into internals, classified. (a) core-internal reach-through →
give a public home/alternative; (b) package-owned domain helper → package exposes
it publicly; (c) "looks generic" builder → promote to core only on proven
identical cross-package use, else stays package-public. None of these break when
ADR-052 lands; each migrates only once its public replacement exists.

| St | Reach | Importer | Class | Disposition | Tracking |
|----|-------|----------|-------|-------------|----------|
| ⏸ | `scistudio.utils.axis_iter` | imaging | a | relocate into core; axis-iteration public surface (incl. `Array.iter_over`) deferred pending imaging rewrite (owner 2026-06-27) | #1729 |
| 🤔 | `scistudio.utils.constraints.has_axes` | imaging | a | public home or alternative | #1817 |
| 🤔 | `scistudio.blocks.app.bridge._guess_mime` | imaging | a | public AppBlock-authoring home | #1817 |
| 🤔 | `scistudio.blocks.app.app_block._PopenProcessAdapter` | imaging | a | public AppBlock-authoring home | #1817 |
| 🤔 | `scistudio.previewers.data_access` (internals) | — | a | public previewer-authoring alternative | #1817 |
| 🤔 | `build_spectrum` | spectroscopy | b | package exposes on `Spectrum` (ADR-052 §4.2) | #1817 |
| 🤔 | `spectrum_arrays` | spectroscopy | b | replaced by inherited `to_numpy`/`to_pandas` | #1817 |
| 🤔 | `coerce_spectra` | spectroscopy | b | package public helper | #1817 |
| 🤔 | `dataframe_from_rows` | multiple | c | promote only if proven generic | #1817 |
| 🤔 | `dataframe_from_pandas` | multiple | c | promote only if proven generic | #1817 |
| 🤔 | `dataframe_collection` | multiple | c | promote only if proven generic | #1817 |

## 13. Package Public Surface (ADR-052 §4)

A package exposes a **registration surface to core** (entry-point callables —
unchanged, ADR-025/§4.1) and a **reuse surface to authors** (§4.2), and the reuse
surface follows the same rules as core's. Per-symbol package decisions are recorded
here; each package then transcribes its own subsection into its repo against its
own version line (the external repos are not edited from here — see scope).

### 13.1 Contract rules every package satisfies (ADR-052 §4, already decided)

- [ ] Every type a package's blocks consume/produce is **public at the package top
  level** (`from scistudio_blocks_X import T`), not a deep path.
- [ ] Construction + reading live **on the type**, following the core idiom (`data=`
  constructor; inherited `to_memory()`, `sel()`, `with_meta()`, and the §10
  accessors). A package **SHOULD** add a public domain constructor that packs
  domain-native inputs to canonical form.
- [ ] A package **MUST NOT** define its own `to_pandas`/`to_numpy` (no shadowing of
  the inherited core accessors).
- [ ] Blocks are **not author-facing by default**; a package MAY publish a block
  class only as an opt-in marked `stable`.
- [ ] Previewers are **not author-facing**.
- [ ] `__all__` on the package top level and any public submodule.
- [ ] **No underscore-named author-facing helper** (`_support`-style modules are
  package-internal only).
- [ ] Public symbols carry the §5 decorators + `Since` against the **package's own
  version line**.
- [ ] A public discovery surface exists (ADR-052 §4.4).

### 13.2 Per-package reuse-surface inventories

Reference repos (ADR-052 §4.4): `scistudio-package-template` (canonical layout),
`scistudio-blocks-spectroscopy`, `scistudio-blocks-imaging`.

> Deferred (owner, 2026-06-27): the packages still need substantial refactoring,
> so their current source is not the final shape — do **not** enumerate from it
> now. Finish the core inventory first; fill these in when the owner signals the
> packages are ready. Do not fetch the package repos until then.

- [ ] **spectroscopy** — `Spectrum` (subclasses core `Series`); `build_spectrum`
  → public constructor on `Spectrum`; `spectrum_arrays` → inherited
  `to_numpy`/`to_pandas`; `coerce_spectra` → public helper. (table TBD)
- [ ] **imaging** — image type(s); reaches `axis_iter`/`has_axes`/`_guess_mime`/
  `_PopenProcessAdapter` resolved per §12. (table TBD)
- [ ] **lcms** — (table TBD)
- [ ] **srs** (private repo) — (table TBD)

## 14. Affected Documentation Surface

Docs that must change when the contract lands. This doc inventories them; the
edits themselves land with #1817 (not in this docs-only PR).

- [ ] Generated API reference (mkdocstrings/griffe) wired into the docs build,
  public surface only, with tier/`Since` badges (ADR-052 §7) — #1817.
- [ ] `docs/user/reference/**` — generated output target (ADR-052
  `planned_governs`); stays generated, not hand-edited.
- [ ] `mkdocs.yml` — reference nav (ADR-052 `planned_governs`).
- [ ] `docs/block-development/*` (block-contract, quickstart,
  architecture-for-block-devs) — point authors at the public surface and the
  canonical import roots.
- [ ] `docs/architecture/ARCHITECTURE.md` — record the public/private boundary.
- [ ] CHANGELOG — the contract, the `Since` baseline, and any deprecations.
- [ ] `scistudio-package-template` — adopt the §13.1 rules (separate repo).
- [ ] Custom-block GUI starter template — teaching surface for the public API
  (#1816/#1817).
- [ ] `docs/user/llms.txt` / embedded-agent context — point the agent at the
  public surface so it stops reaching into internals.

## 15. Enforcement And Anti-Drift

The owner's question: can we *freeze* the API so a test locks it, and forbid
editing that test, so an accidental edit cannot drift the contract?

The right goal is **not an immutable test** — the contract MUST be able to evolve
under the §5 deprecation policy (add `provisional`, promote to `stable`, deprecate
then remove). The goal is that **every surface change is loud, reviewed, and
documented**, and that *accidental* change is impossible. The design:

- **Golden snapshot.** Generate the actual public surface — every symbol in each
  `__all__`, with its tier and `Since` — into one committed artifact (e.g.
  `tests/api/public_surface.snapshot.json`). The freeze test recomputes the live
  surface and diffs it against the snapshot.
- **Accidental drift fails CI.** A refactor that adds, removes, or renames a
  public symbol makes the snapshot diff non-empty → the freeze test fails. The
  author cannot silently change the surface by editing code.
- **Intentional change is a reviewable diff.** Changing the contract means editing
  the snapshot, which shows up as a human-readable `+added` / `-removed` / tier or
  `Since` change in the PR — exactly what a reviewer should see.
- **The snapshot and test are protected from silent edits.** CODEOWNERS +
  protected-path + branch protection require **owner review** for any change to
  `tests/api/**` and the snapshot artifact. (The repo already gates the governance
  surface, protected core, Sentrux, and the gate ledger — extend the same
  machinery to these paths.) This is the practical form of "the test can't be
  changed without me": not literally immutable, but unmergeable without owner
  approval.
- **Intentional change is tied to policy.** An audit/Sentrux rule fails a
  non-empty snapshot diff unless the same PR carries a CHANGELOG entry and the
  metadata stays consistent with §5 (a removed `stable` symbol must have been
  `deprecated` for ≥1 minor first; a new symbol carries a `Since`). This binds the
  freeze to the deprecation policy instead of just asserting a string.
- **Single source of truth.** The snapshot can be the same artifact the generated
  docs consume, so the freeze test, the docs, and the contract can never disagree.

Net: you cannot change the API **by accident** (CI catches it), and you cannot
change it **on purpose** without owner review **and** a changelog/policy entry.
That is stronger and more honest than an un-editable test.

## 16. Implementation Sequence (#1817)

Confirming the agreed flow (this spec is step 0). Steps 1–4 are the #1817 change
set: they touch protected core and are **out** of this docs-only PR.

0. **Finalize this per-symbol contract** (this doc) — the data the rest transcribes.
1. **Declare + decorate + docstring.** Add `__all__` on the canonical roots; add
   `@stable`/`@provisional`/`@internal` + `Since` on each public symbol; write or
   clean each public symbol's docstring (docs *and* the freeze test read these, so
   docstrings belong with this step, not later). [protected core →
   `admin-approved:core-change`]
2. **Generate the reference** from docstrings + decorators (mkdocstrings/griffe),
   public surface only, tier/`Since` badges (ADR-052 §7).
3. **Freeze.** Snapshot the surface + add the freeze test + the anti-drift guard
   (§15). Land this with or immediately after step 1 so the surface cannot drift
   before it is locked.
4. **Update affected docs** (§14): block-development guides, architecture,
   CHANGELOG, package template, agent context.
5. **Packages adopt** the same in each repo, against each package's version line
   (§13).

Owner's stated order was correct; the only refinements: docstrings fold into
step 1 (the docs and the freeze both read them), and the freeze (3) should not lag
behind the declaration (1).

Cleanup folded into step 1 (Phase-11 debt now overdue): delete the
`DataObject.metadata` property and the `metadata=` constructor kwarg (deprecation
shim; owner 2026-06-27), and retire the `_data`/`_arrow_table` transient bridges
once their callers migrate.

## 17. Open Questions / Parking Lot

- **✅ `Since` baseline = `0.3.1`** (current `BASE_VERSION` on `main`). Resolved
  2026-06-27. Branch must catch up to `main` before finalize (§2.3).
- **✅ `AIBlock` / `SubWorkflowBlock` are NOT public.** Resolved 2026-06-27;
  ADR-052 §3 corrected. Runtime/engine + agent base classes, not an author
  extension point.
- **✅ Session scope = full affected surface** — core modules + domain packages +
  affected docs, not core-only. Resolved 2026-06-27.
- **⏸ Package inventory deferred** (owner, 2026-06-27). Packages need substantial
  refactoring first, so enumerating from current source would capture
  soon-to-change symbols. Finish core first; fill §13.2 when the owner signals.
  Do not fetch the package repos until then.
- **🤔 `registry.py` / `serialization.py` public exports.** Are `TypeSignature`
  and `StorageReference` public (named in ADR-052 §3), and what are their canonical
  paths — re-exported from `scistudio.core.types`, or elsewhere?
- **🤔 Reconcile against existing `__all__`.** `core/types/__init__.py`,
  `previewers/models.py`, and `blocks/io/materialisation.py` already declare
  `__all__`; confirm whether today's surface matches or revises them.
- **🤔 Governed-modules gap.** `base.py` surfaces `StorageReference`
  (`scistudio.core.storage.ref`), `FrameworkMeta` and `with_meta_changes`
  (`scistudio.core.meta`) as part of the core.types author surface, but
  `scistudio.core.meta` / `scistudio.core.storage` are not in ADR-052
  `governs.modules`. Decide: add them (or the specific re-exported symbols) to the
  governed surface, or treat the `scistudio.core.types` re-export as the canonical
  governed path.
- **🤔 Plot `collection` vs `core.types.Collection`.** §9's plot
  `render(collection)` shape (`.types`, `.items.open()/open_one()`,
  `item.type/metadata/open()`) does not match `core.types.Collection` (ADR-020:
  `item_type`, `__iter__`, `storage_refs`) — they share a name but are different
  objects. The plot `collection` is ADR-048's plot-render object. Locate it (plot /
  preview subsystem) and inventory its public shape; decide whether it is in this
  contract's scope (§9 / §3.8).

## 18. Decision Log

A running, dated log of decisions taken during fill-in, so the rationale survives
even after the tables are complete.

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-06-27 | Scaffold created; ADR-052 §3.1 accessors (§10) and §3.2 large-data (§11) pre-filled as `stable` / baseline. | These are already fixed by ADR-052; the rest are filled live. |
| 2026-06-27 | `Since` baseline = `0.3.1`. | Current `BASE_VERSION` on `main`; this branch is ~10 commits behind (still `0.3.0`) and must catch up before finalize. |
| 2026-06-27 | `AIBlock` & `SubWorkflowBlock` excluded from the public surface; ADR-052 §3 corrected. | Runtime/engine + embedded-agent base classes, not an author extension point. |
| 2026-06-27 | Session scope = full affected surface (core modules + domain packages + affected docs). | Owner directive; not core-only. |
| 2026-06-27 | Enforcement = golden snapshot + freeze test + protected-path/CODEOWNERS + changelog-gated drift audit (§15). | "Can't change by accident, can't change on purpose without review + changelog" — stronger than an un-editable test. |
| 2026-06-27 | Rebased branch onto `origin/main` (now `0.3.1`); deferred package inventory (§13.2) until packages are refactored — core first. | Owner: packages need refactoring; enumerating current source would capture stale symbols. |
| 2026-06-27 | `base.py` completed (§3.1): `DataObject` & `TypeSignature` public/stable; `storage_ref` setter public; `save` provisional; `get_in_memory_data` internal; `metadata` shim slated for deletion (Phase 11 over); `_serialise_extra_metadata` promoted public (pair `_reconstruct_extra_kwargs` pending override survey). | First core file decided. |
| 2026-06-27 | Reconstruction-hook survey (background agent): core `Array`/`Series`/`DataFrame`/`Text`/`Artifact` override both hooks (symmetric pair); `CompositeData` neither (slots recurse via the serializer); **0/6** spectroscopy + imaging package types override — all route extra state through the `Meta` slot. | Evidence for the promote-vs-internal hook decision; author demand is latent, not demonstrated. |
| 2026-06-27 | `array.py` completed (§3.2): `Array` + schema ClassVars + `data=` ctor + writable `axes/shape/dtype/chunk_shape` + `ndim`/`__array__`/`sel`/`with_meta`/`to_memory` public/stable; `to_numpy()` to be added (§10); `iter_over` kept Internal pending imaging rewrite. | Owner 2026-06-27; imaging slated for rewrite. |
| 2026-06-27 | Reconstruction-hook pair → **option A**: promote both to public, `provisional`, de-underscore in #1817 (`reconstruct_extra_kwargs` / `serialise_extra_metadata`). | Owner 2026-06-27. Public home for the documented extension point; `provisional` because 0/6 packages use it today. |
| 2026-06-27 | `dataframe.py` completed (§3.3): `DataFrame` public/stable; writable `columns/row_count/schema`; `to_pandas`/`to_numpy` to add (§10); hooks per opt-A. No new decisions. | Mechanical application of established patterns. |
| 2026-06-27 | `series.py` completed (§3.4): `Series` public/stable; writable `index_name/value_name/length`; `to_pandas`/`to_numpy` to add (§10); `get_in_memory_data` override stays Internal; hooks per opt-A. No new decisions. | Mirrors dataframe.py. |
| 2026-06-27 | `text.py` completed (§3.5): `Text` public/stable; `content=` payload (not `data=`); writable content/format/encoding; no accessor (already str); hooks per opt-A; `get_in_memory_data` override Internal. No new decisions. | Mechanical. |
| 2026-06-27 | `artifact.py` completed (§3.6): `Artifact` public/stable; `file_path=` payload; writable attrs; no accessor (Path); hooks per opt-A. No new decisions. | Mechanical. |
| 2026-06-27 | `composite.py` completed (§3.7): `CompositeData` public/stable; slot API `get`/`set`/`slot_types`/`slot_names`/`expected_slots` public; **hook exception** (overrides neither). No new decisions. | Confirms agent survey. |
| 2026-06-27 | `collection.py` recorded (§3.8): `core.types.Collection` (ADR-020 transport wrapper) public/stable. Flagged: §9 plot `collection` (ADR-048) is a DIFFERENT object/shape — needs locating & reconciling. | §9 mismatch open (§17). |
| 2026-06-27 | §9 plot `collection` confirmed NOT `core.types.Collection` (separate ADR-048 object; annotated §3.8); added missed `Collection.__repr__`. `serialization.py` + `_backend_defaults.py` confirmed Internal (§3.9). | Owner 2026-06-27. |
| 2026-06-27 | `registry.py` `TypeRegistry`/`TypeSpec` disposition pending: background survey of imaging + spectroscopy package usage dispatched (core sweep already shows 0 author importers; lean demote-to-internal). | Owner asked to verify package usage before demoting. |
| 2026-06-27 | CompositeData ergonomics resolved: keep `_slots` internal behind validating `get()`/`set()`; **do NOT add `__getitem__`/`__setitem__`** (owner 2026-06-27). `get()`/`set()` is the slot API. | Owner decided against dict-style slot access. |
| 2026-06-27 | `TypeRegistry`/`TypeSpec` survey (2nd background agent): 0 author-facing importers in core or either public package; packages touch `TypeRegistry` only in tests via the internal path; `TypeSpec` has no external reader. Recommend demote both to internal (B). | Awaiting owner confirm. |
