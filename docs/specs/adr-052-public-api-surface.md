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
| ⚠️ | Public but **deprecated** — still importable, slated for removal under the §5 deprecation policy |

A module section is complete only when its file checklist is fully ticked and no
row is left 🤔.

### 2.3 `Since` baseline

The initial contract baseline is **`0.3.1`** — the current `BASE_VERSION` on
`main` (`src/scistudio/_version.py`), the version line the declared
`__all__`/decorator surface ships in. A symbol that has existed in code for many
releases still records `since="0.3.1"` because that is when it *first became
public on its declared surface* (ADR-052 §5). Symbols added after the baseline
record their own later version.

> Branch note: this branch (`guided/1819-public-api-contract-adr`) carries
> `BASE_VERSION = 0.3.1` and is current with `origin/main` (rebased; 0 behind),
> so the baseline already matches the shipping line.

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
- [x] `registry.py` (647) — `TypeRegistry`/`TypeSpec` → §3.9; **demoted to internal** (owner, opt B)
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
as-is; the plot object is now inventoried in §9 (the import-free `render(collection)` contract).

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
external reader at all. **Owner confirmed (2026-06-27): demote both to internal
(option B).** Remove both from `core.types.__all__` in #1817; the internal
`scistudio.core.types.registry` path keeps working, so no package change is needed.
Caveat: `tests/contracts/test_runtime_import_contract.py` frames a "TypeRegistry
public-API contract" to reconcile with the internal disposition in #1817.

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ➖ | `TypeRegistry` | class | Internal | — | — | owner 2026-06-27 (opt B); mutable runtime registry; 0 author importers; drop from `core.types.__all__` in #1817 |
| ➖ | `TypeSpec` | dataclass | Internal | — | — | owner 2026-06-27 (opt B); located-type descriptor; 0 external readers; drop from `__all__` in #1817 |

Recommendation pending the survey: **demote both to internal** (option B) — the
author-facing "what types exist" need is ADR-052 §4.4's separate read-only discovery
API (#1817), not the raw mutable registry.

## 4. Block Authoring — `scistudio.blocks.base`

Canonical root: `from scistudio.blocks.base import …`

File checklist:

- [x] `block.py` (507) — `Block` → §4.1
- [x] `config.py` (33) — `BlockConfig` → §4.2
- [x] `ports.py` (170) — `InputPort`/`OutputPort` → §4.3 (`Port` + 4 helpers internal)
- [x] `state.py` (38) — `ExecutionMode` → §4.4 (`BlockState` internal)
- [x] `package_info.py` (44) — `PackageInfo` + `PackageOtaSource` → §4.5
- [x] `interactive.py` (367) — interactive surface → §4.8 (public/provisional)
- [x] `exceptions.py` (21) — `BlockCancelledByAppError` → §4.7 (Public/provisional)
- [x] `result.py` (20) — `BlockResult` internal → §4.6

### 4.1 `block.py`

Module exports (`__all__`): `Block` public. (It imports `BlockConfig`, the port
helpers, and `ExecutionMode` from sibling modules — each covered in its own subsection.)

**`Block`** — ✅ Public / `stable` / 0.3.1. The ABC every block subclasses.

Block-authoring declaration (ClassVars an author sets on their block class):

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `name` / `description` / `version` | ClassVar | Public | stable | 0.3.1 | identity / display |
| ✅ | `subcategory` | ClassVar | Public | stable | 0.3.1 | palette grouping (#588) |
| ✅ | `input_ports` / `output_ports` | ClassVar | Public | stable | 0.3.1 | static port declaration |
| ✅ | `variadic_inputs` / `variadic_outputs` | ClassVar | Public | stable | 0.3.1 | ADR-029 variadic ports |
| ✅ | `allowed_input_types` / `allowed_output_types` | ClassVar | Public | stable | 0.3.1 | ADR-029 type constraints |
| ✅ | `min_input_ports` / `max_input_ports` / `min_output_ports` / `max_output_ports` | ClassVar | Public | stable | 0.3.1 | ADR-029 Add.1 count limits |
| ✅ | `dynamic_ports` | ClassVar | Public | **provisional** | 0.3.1 | owner 2026-06-27: declarative dynamic-port descriptor (ADR-028 Add.1); still settling |
| ✅ | `execution_mode` | ClassVar | Public | stable | 0.3.1 | `ExecutionMode` (§4.x state.py) |
| ✅ | `terminate_grace_sec` | ClassVar | Public | stable | 0.3.1 | SIGTERM grace (ADR-019) |
| ✅ | `key_dependencies` | ClassVar | Public | stable | 0.3.1 | declared pip deps |
| ✅ | `config_schema` | ClassVar | Public | stable | 0.3.1 | JSON schema for the config UI |

Lifecycle, hooks, and helpers:

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `__init__(config=None)` | method | Public | stable | 0.3.1 | sets `self.config` |
| ✅ | `self.config` | attribute | Public | stable | 0.3.1 | a `BlockConfig` (§4.x config.py) |
| ✅ | `validate(inputs)` | method | Public | stable | 0.3.1 | default port-contract check; overridable |
| ✅ | `run(inputs, config)` | method | Public | stable | 0.3.1 | **@abstractmethod — authors MUST override** |
| ✅ | `postprocess(outputs)` | method | Public | stable | 0.3.1 | optional; default passthrough |
| ✅ | `process_item(item, config)` | method | Public | stable | 0.3.1 | Tier-1 override point (default `run()` lives in `ProcessBlock`, §5) |
| ✅ | `get_effective_input_ports()` / `get_effective_output_ports()` | method | Public | stable | 0.3.1 | owner 2026-06-27; per-instance ports; dynamic/variadic blocks override (ADR-028 Add.1) |
| ✅ | `get_panel_manifest()` | method | Public | provisional | 0.3.1 | owner 2026-06-27; returns the declared `PanelManifest`; override for a dynamic panel (ADR-051); tier tied to the interactive surface (interactive.py) |
| ✅ | `pack` / `unpack` / `unpack_single` / `map_items` / `parallel_map` | staticmethod | Public | stable | 0.3.1 | ADR-020 Collection utilities |
| ✅ | `persist_array(...)` / `persist_table(...)` | method | Public | stable | 0.3.1 | §11 large-data streaming writes |
| ➖ | `_auto_flush(obj)` | staticmethod | Internal | — | — | called by pack / map_items / parallel_map |

`AIBlock` and `SubWorkflowBlock` are **out of the public surface** (decided
2026-06-27; ADR-052 §3 corrected): they are runtime base classes the engine and
the embedded agent compose, not an author extension point.

### 4.2 `config.py`

Module exports: `BlockConfig` public. A Pydantic `BaseModel` with `extra="allow"`, so
subclasses/plugins attach arbitrary validated fields.

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `BlockConfig` | class | Public | stable | 0.3.1 | Pydantic BaseModel, `extra="allow"` |
| ✅ | `params` | field | Public | stable | 0.3.1 | `dict[str, Any]` |
| ✅ | `get(key, default=None)` | method | Public | stable | 0.3.1 | params first, then Pydantic extras (#565) |

(Pydantic's own BaseModel API — `model_dump`, etc. — is Pydantic's contract, not re-frozen here.)

### 4.3 `ports.py`

Canonical author types: `InputPort`, `OutputPort` (authors declare ports with these).

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `InputPort` | dataclass (kw-only) | Public | stable | 0.3.1 | input connection endpoint |
| ✅ | `InputPort.name` / `.accepted_types` / `.is_collection` / `.description` / `.required` | field | Public | stable | 0.3.1 | shared port fields (from `Port` base) |
| ✅ | `InputPort.default` / `.constraint` / `.constraint_description` | field | Public | stable | 0.3.1 | input-only: default value + constraint fn + its description |
| ✅ | `OutputPort` | dataclass (kw-only) | Public | stable | 0.3.1 | output connection endpoint |
| ✅ | `OutputPort.name` / `.accepted_types` / `.is_collection` / `.description` / `.required` | field | Public | stable | 0.3.1 | shared port fields (from `Port` base) |
| ➖ | `Port` | dataclass | Internal | — | — | owner 2026-06-27: shared base; drop from `__all__` (authors use Input/OutputPort) |
| ➖ | `port_accepts_type` / `port_accepts_signature` / `validate_connection` / `validate_port_constraint` | function | Internal | — | — | owner 2026-06-27: demote all 4 (survey: 0 author/package use; all callers framework); drop from `__all__`. `port_accepts_signature` = dead code (0 call sites) → keep/delete follow-up under #1817 |
| ➖ | `ports_from_config_dicts` | function | Internal | — | — | ADR-029 variadic config conversion; not in `__all__` |

### 4.4 `state.py`

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `ExecutionMode` | enum | Public | stable | 0.3.1 | AUTO/INTERACTIVE/EXTERNAL; authors set `execution_mode` |
| ➖ | `BlockState` | enum | Internal | — | — | owner 2026-06-27: engine-managed lifecycle (ADR-018 scheduler owns state); drop from `__all__` |

### 4.5 `package_info.py`

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `PackageInfo` | dataclass (frozen) | Public | stable | 0.3.1 | returned from the `scistudio.blocks` entry point |
| ✅ | `PackageInfo.name` / `.description` / `.author` / `.version` | field | Public | stable | 0.3.1 | palette identity |
| ✅ | `PackageInfo.ota` | field | Public | provisional | 0.3.1 | `PackageOtaSource \| None` OTA source (#1784); provisional |
| ✅ | `PackageOtaSource` | dataclass (frozen) | Public | **provisional** | 0.3.1 | owner 2026-06-27: **add to `__all__`**; a package sets `ota=PackageOtaSource(...)` (#1784) |
| ✅ | `PackageOtaSource.manifest_url` / `.channel` | field | Public | provisional | 0.3.1 | per-package manifest URL + release channel (default `"stable"`) |

### 4.6 `result.py`

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ➖ | `BlockResult` | dataclass | Internal | — | — | owner 2026-06-27: engine execution-outcome container (outputs/duration_ms/error); authors return `dict[str, Collection]`; drop from `__all__` |

### 4.7 `exceptions.py`

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `BlockCancelledByAppError` | exception | Public | provisional | 0.3.1 | owner 2026-06-27: AppBlock **package subclasses raise it** when their external app exits without output (#681). Not in `__all__` today → add. Canonical path: re-export from `scistudio.blocks.app` (AppBlock authoring); confirm in #1817 |

### 4.8 `interactive.py` (ADR-051)

Has its own `__all__` but is **not re-exported from the `blocks.base` root today**
(deep path `scistudio.blocks.base.interactive` only). Per §2 the canonical public path
is the root — #1817 re-exports the public interactive symbols from
`blocks.base.__init__`. **Whole interactive surface = `provisional`** (owner
2026-06-27; ADR-051 recent, still settling; this also sets `get_panel_manifest`'s tier).

Author surface (Public / `provisional` / 0.3.1):

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `InteractiveMixin` | class | Public | provisional | 0.3.1 | the interaction capability mixin |
| ✅ | `interactive_panel` | ClassVar | Public | provisional | 0.3.1 | author MUST set (a `PanelManifest`) |
| ✅ | `prepare_prompt(inputs, config)` | method | Public | provisional | 0.3.1 | author overrides (default raises); → `InteractivePrompt` or dict |
| ✅ | `remap_saved_decision(...)` | method | Public | provisional | 0.3.1 | author MAY override (interaction-memory remap) |
| ✅ | `InteractivePrompt` | dataclass (frozen) | Public | provisional | 0.3.1 | the `prepare_prompt` return |
| ✅ | `InteractivePrompt.panel_payload` | field | Public | provisional | 0.3.1 | JSON-safe, window-sized view the panel renders |
| ✅ | `InteractivePrompt.intermediate` | field | Public | provisional | 0.3.1 | `tuple[StorageReference, ...]`; engine-held heavy reuse, excluded from lineage |
| ✅ | `PanelManifest` | dataclass (frozen) | Public | provisional | 0.3.1 | the block's window descriptor |
| ✅ | `PanelManifest.panel_id` | field | Public | provisional | 0.3.1 | frontend resolution key |
| ✅ | `PanelManifest.module_url` | field | Public | provisional | 0.3.1 | package panel module URL (empty for core panels) |
| ✅ | `PanelManifest.export_name` | field | Public | provisional | 0.3.1 | named export to mount (default `"default"`) |
| ✅ | `PanelManifest.css` | field | Public | provisional | 0.3.1 | optional CSS asset URLs |
| ✅ | `PanelManifest.version` | field | Public | provisional | 0.3.1 | panel bundle version |
| ✅ | `PanelManifest.api_version` | field | Public | provisional | 0.3.1 | must match `PANEL_API_VERSION` major |
| ✅ | `PanelManifest.response_schema` | field | Public | provisional | 0.3.1 | optional advisory response-shape declaration |
| ✅ | `PanelManifest.asset_root` | field | Public | provisional | 0.3.1 | package asset-confinement dir; **never serialized** (backend validator only) |
| ✅ | `PanelManifest.to_dict()` | method | Public | provisional | 0.3.1 | wire shape sent to the frontend (`asset_root` omitted) |
| ✅ | `load_intermediate(config)` | function | Public | provisional | 0.3.1 | author helper: compute phase reads intermediate refs |
| ✅ | `PANEL_API_VERSION` | constant | Public | provisional | 0.3.1 | panel API compat version |
| ✅ | `INTERACTIVE_RESPONSE_KEY` | constant | Public | provisional | 0.3.1 | `config[...]` key carrying the user's decision |

Internal (owner 2026-06-27 — demote from or keep out of `__all__`):

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ➖ | `SupportsInteraction` | protocol | Internal | — | — | registry validation protocol; was in `__all__` |
| ➖ | `coerce_prompt` | function | Internal | — | — | worker prompt-phase normalizer; was in `__all__` |
| ➖ | `serialise_storage_ref` / `deserialise_storage_ref` | function | Internal | — | — | intermediate-channel JSON; was in `__all__` |
| ➖ | `INTERACTIVE_INTERMEDIATE_KEY` | constant | Internal | — | — | engine-threaded; authors use `load_intermediate` |
| ➖ | `interactive_item_label` / `interactive_input_signature` | function | Internal | — | — | engine memory signatures; not in `__all__` |
| ➖ | `load_interactive_memory(config)` | function | Internal | — | — | engine reads the remembered-decision record from config; not in `__all__` |
| ➖ | `INTERACTIVE_MEMORY_KEY` | constant | Internal | — | — | engine/frontend memory record key; not in `__all__` |

**Net `interactive.py __all__` change (#1817):** keep `InteractiveMixin`,
`InteractivePrompt`, `PanelManifest`, `load_intermediate`, `PANEL_API_VERSION`,
`INTERACTIVE_RESPONSE_KEY`; drop `SupportsInteraction`, `coerce_prompt`,
`serialise_storage_ref`, `deserialise_storage_ref`, `INTERACTIVE_INTERMEDIATE_KEY`;
re-export the kept symbols from the `blocks.base` root (§2).

**Net `blocks.base.__all__` change (for #1817):** drop `Port`, `BlockState`,
`BlockResult`, and the four port helpers
(`port_accepts_type`/`port_accepts_signature`/`validate_connection`/`validate_port_constraint`,
survey-confirmed); add `PackageOtaSource` and the re-exported interactive surface
(§4.8). Keep `Block`, `BlockConfig`, `InputPort`, `OutputPort`, `ExecutionMode`,
`PackageInfo`.

## 5. Process Blocks — `scistudio.blocks.process`

Canonical root: `from scistudio.blocks.process import …`

Module exports (`__all__`): `ProcessBlock` only (confirmed against `__init__.py`).

File checklist:

- [x] `process_block.py` (206) — `ProcessBlock`
- [x] `utils.py` (23) — `to_arrow` (internal)

**`ProcessBlock(Block)`** — ✅ Public / `stable` / 0.3.1. The Tier-1 base authors
subclass (deterministic transforms; ADR-027 D7 setup/teardown lifecycle).

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `ProcessBlock` | class | Public | stable | 0.3.1 | |
| ✅ | `algorithm` | ClassVar | Public | stable | 0.3.1 | human-readable transform id |
| ✅ | `process_item(item, config, state=None)` | method | Public | stable | 0.3.1 | **the Tier-1 override** (3-arg, ADR-027 D7); overrides Block's 2-arg stub |
| ✅ | `setup(config)` | method | Public | stable | 0.3.1 | ADR-027 D7 once-per-run init; default returns `None` |
| ✅ | `teardown(state)` | method | Public | stable | 0.3.1 | ADR-027 D7 cleanup in `finally`; default no-op |
| ✅ | `run(inputs, config)` | method | Public | stable | 0.3.1 | default Tier-1 impl (setup → process_item per item → auto-flush → pack → teardown); Tier-2/3 override directly |
| ➖ | `_process_item_takes_state()` | method | Internal | — | — | signature-inspection shim (2-arg back-compat) |

**`utils.py`** — `to_arrow(obj)` ➖ Internal (process-builtins helper; not in `__all__`).
The canonical author path to the Arrow form is `DataFrame.to_memory()` (§3.1/§10);
`to_pandas()`/`to_numpy()` are the ergonomic accessors for pandas/numpy, a different shape.

Inherits the full `Block` surface (§4.1): authoring ClassVars, ports, `validate`,
`postprocess`, Collection utilities, `persist_*`, etc.

## 6. IO Blocks — `scistudio.blocks.io`

Canonical root: `from scistudio.blocks.io import …`

Current `__all__` (16): `IOBlock`, `SimpleLoader`, `SimpleSaver`, `LoadData`,
`SaveData`, `FormatCapability`, `MetadataFidelity`, `CapabilityDirection`,
`MetadataFidelityLevel`, the 5 capability errors, `normalize_extension`,
`normalize_extensions`.

File checklist:

- [x] `io_block.py` (300) — `IOBlock` → §6.1
- [x] `simple_io.py` (152) — `SimpleLoader` / `SimpleSaver` → §6.2
- [x] `capabilities.py` (232) — ADR-043 capability surface → §6.3
- [x] `materialisation.py` (472) — internal → §6.4
- [x] `loaders/` + `savers/` — `LoadData` / `SaveData` → §6.5 (internal)
- [x] `_unified_dispatch.py` (363) / `_config_enrichment.py` (73) — internal (underscore)

### 6.1 `io_block.py`

**`IOBlock(Block)`** — ✅ Public / `stable` / 0.3.1. The ABC plugin IO blocks subclass
(ADR-028 §D1); user loaders/savers subclass this or `SimpleLoader`/`SimpleSaver` (§6.2).

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `IOBlock` | class | Public | stable | 0.3.1 | |
| ✅ | `direction` | ClassVar | Public | stable | 0.3.1 | `"input"` / `"output"` |
| ✅ | `format_capabilities` | ClassVar | Public | stable | 0.3.1 | `tuple[FormatCapability, ...]` (ADR-043 go-forward declaration) |
| ⚠️ | `supported_extensions` | ClassVar | Public | deprecated | 0.3.1 | owner 2026-06-27: legacy ext→format scaffolding; **use `format_capabilities`**; removal per §5 (#1817) |
| ✅ | `get_format_capabilities()` | classmethod | Public | stable | 0.3.1 | returns explicit or synthesized capabilities; Simple* override |
| ✅ | `load(config, output_dir="")` | method (abstract) | Public | stable | 0.3.1 | input-direction override |
| ✅ | `save(obj, config)` | method (abstract) | Public | stable | 0.3.1 | output-direction override |
| ✅ | `run(inputs, config)` | method | Public | stable | 0.3.1 | default dispatch by `direction`; auto-flush safety net |
| ➖ | `__init_subclass__` | method | Internal | — | — | empty-input-port enforcement (#10) |
| ➖ | `_legacy_capability_data_type` / `_resolved_*_port_name` / `_detect_format` | method | Internal | — | — | dispatch + port-resolution helpers |

Inherits the `Block` surface (§4.1), incl. `persist_array`/`persist_table` (§11), and
sets stable-tier defaults for the inherited `name`/`description`/`subcategory`/
`input_ports`/`output_ports`/`config_schema` ClassVars.

### 6.2 `simple_io.py`

**`SimpleLoader(IOBlock)` / `SimpleSaver(IOBlock)`** — ✅ Public / `stable` / 0.3.1.
Ergonomic single-format bases (ADR-043) that synthesize one conservative capability.

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `SimpleLoader` | class | Public | stable | 0.3.1 | single-format loader base |
| ✅ | `SimpleLoader.output_type` / `.extensions` / `.format_id` / `.metadata_fidelity` | ClassVar | Public | stable | 0.3.1 | author declares these |
| ✅ | `SimpleLoader.load_file(path, config)` | method (abstract) | Public | stable | 0.3.1 | **the author override** |
| ✅ | `SimpleSaver` | class | Public | stable | 0.3.1 | single-format saver base |
| ✅ | `SimpleSaver.input_type` / `.extensions` / `.format_id` / `.metadata_fidelity` | ClassVar | Public | stable | 0.3.1 | author declares these |
| ✅ | `SimpleSaver.save_file(obj, path, config)` | method (abstract) | Public | stable | 0.3.1 | **the author override** |
| ➖ | `_require_path` / `_simple_capability_id` / `_simple_label` / `_required_data_type` / `_required_format_id` / `_required_extensions` | function | Internal | — | — | module helpers |

(Both also carry `direction`, `get_format_capabilities()`, `load`/`save` —
inherited or overridden from `IOBlock` §6.1.)

### 6.3 `capabilities.py` (ADR-043)

Author declaration surface plus a **catchable** error hierarchy.

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `FormatCapability` | dataclass (frozen) | Public | stable | 0.3.1 | one external file-format conversion an IOBlock owns |
| ✅ | `FormatCapability` fields: `id`/`direction`/`data_type`/`format_id`/`extensions`/`label`/`block_type`/`handler`/`is_default`/`priority`/`roundtrip_group`/`metadata_fidelity`/`is_synthesized` | field | Public | stable | 0.3.1 | author sets the declaration fields; `is_synthesized` is framework-set (legacy synthesis) |
| ✅ | `FormatCapability.migration_scaffold` / `.normalized_extensions` | property | Public | stable | 0.3.1 | |
| ✅ | `MetadataFidelity` | dataclass (frozen) | Public | stable | 0.3.1 | typed-`meta` preservation contract for one capability |
| ✅ | `MetadataFidelity` fields: `level`/`typed_meta_reads`/`typed_meta_writes`/`format_metadata_reads`/`format_metadata_writes`/`notes` | field | Public | stable | 0.3.1 | author declares preserved metadata |
| ✅ | `MetadataFidelity.typed_meta_fields` / `.format_metadata_fields` | property | Public | stable | 0.3.1 | |
| ✅ | `MetadataFidelity.validate_typed_meta_fields(data_type)` | method | Public | stable | 0.3.1 | validate declared fields against `data_type.Meta` |
| ✅ | `CapabilityDirection` / `MetadataFidelityLevel` | type-alias | Public | stable | 0.3.1 | `Literal` aliases (load/save; fidelity levels) |
| ✅ | `CapabilityValidationError` + `InvalidExtensionError` / `InvalidMetadataFidelityError` / `InvalidFormatCapabilityError` / `SimpleIODeclarationError` | class | Public | stable | 0.3.1 | owner 2026-06-27: keep public — authors may **catch** for internal fallback |
| ➖ | `normalize_extension` / `normalize_extensions` | function | Internal | — | — | owner 2026-06-27: demote; framework normalizes automatically (`FormatCapability.__post_init__`) |
| ➖ | `VALID_CAPABILITY_DIRECTIONS` / `VALID_METADATA_FIDELITY_LEVELS` / `_normalize_string_tuple` / `_meta_model_fields` | constant/function | Internal | — | — | module internals |

### 6.4 `materialisation.py`

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ➖ | `materialise_to_file` / `reconstruct_from_file` | function | Internal | — | — | owner 2026-06-27: AppBlock prepare/restore helpers; not re-exported from the io root (deep path only) |

### 6.5 `loaders/` + `savers/` — `LoadData` / `SaveData`

The concrete core dynamic-port IO blocks (`loaders/load_data.py`,
`savers/save_data.py`), re-exported into `io.__all__` today.

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ➖ | `LoadData` / `SaveData` | class (block) | Internal | — | — | owner 2026-06-27: confirmed internal (survey: 0 author/package use; core GUI builtins; `_unified_dispatch` delegates user capabilities into the single Load/Save block — the "inject into loader" design); drop from `io.__all__`. Deep import path stays working for internal callers (`ai_block`, core tests) |

**Net `io.__all__` change (for #1817):** keep `IOBlock`, `SimpleLoader`, `SimpleSaver`,
`FormatCapability`, `MetadataFidelity`, `CapabilityDirection`, `MetadataFidelityLevel`,
and the 5 capability errors; mark `IOBlock.supported_extensions` **deprecated**; drop
`normalize_extension`/`normalize_extensions`, `LoadData`, and `SaveData` (all internal, owner-confirmed).

**xlsx support (#1810, PR #1815 — OPEN, on `feature/1810-dataframe-xlsx-io`, not yet
in `main`).** Surveyed 2026-06-27: adds native `.xlsx` read/write for
`DataFrame`/`Series` but introduces **no new public symbol** — all new code is
underscore-private (`_capability.py` / `_helpers.py` / `_`-prefixed functions). It
layers behavior on already-inventoried public surface: new `xlsx` `FormatCapability`
instances on `LoadData`/`SaveData` (the type is §6.3-public; instances are framework
data), `LoadData` `.xlsx` fan-out (one `DataObject` per sheet, `is_collection=True`),
`SaveData` regroup-by-workbook, and interim `user["sheet_name"]` /
`user["display_name"]` conventions on the public `user` slot (canonical form tracked
by **#1812**). It is exactly the ADR-052 §3.1 pandas exception and **conforms**
(pandas/openpyxl only at the format boundary; Arrow-backed `DataObject` downstream).
The exception covers the **saver** too, so the ADR-052 §3.1 wording should widen
"loader" → "reader/writer" and cite PR #1815.

## 7. App Blocks — `scistudio.blocks.app`

Canonical root: `from scistudio.blocks.app import …`

**Whole §7 surface = `provisional`** (owner 2026-06-27: this area is expected to churn
with bug-fixes). Today `app.__all__ = ["AppBlock"]` only; ADR-052 §3 names the
file-exchange/watcher facilities as author surface and §6(a)/§12 record two
reach-throughs (`_guess_mime`, `_PopenProcessAdapter`). The file-exchange/watcher
facilities are now public/provisional (app survey, 6th agent; only imaging authors
AppBlocks — `FijiBlock`/`NapariBlock`). Both reach-throughs are resolved (owner):
`_PopenProcessAdapter` (b) — `FileWatcher` accepts a plain `Popen`; `_guess_mime` (c) —
extension→MIME removed/replaced. **§7 fully decided.**

File checklist:

- [x] `app_block.py` (499) — `AppBlock` provisional; `_PopenProcessAdapter` → internal (b) → §7.1
- [x] `bridge.py` (456) — `FileExchangeBridge`/`ExternalAppBridge` provisional; `_guess_mime` → remove/replace (c) → §7.2
- [x] `watcher.py` (159) — `FileWatcher`/`ProcessExitedWithoutOutputError` provisional → §7.3
- [x] `command_validator.py` (67) — `validate_app_command` provisional → §7.4

### 7.1 `app_block.py`

**`AppBlock(Block)`** — ✅ Public / `provisional` / 0.3.1 (owner 2026-06-27). The base
for blocks that delegate to an external GUI app via a file-exchange protocol.

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `AppBlock` | class | Public | provisional | 0.3.1 | external-app base |
| ✅ | `app_command` | ClassVar | Public | provisional | 0.3.1 | executable path/command |
| ✅ | `output_patterns` | ClassVar | Public | provisional | 0.3.1 | watcher globs |
| ✅ | `run(inputs, config)` | method | Public | provisional | 0.3.1 | prepare → launch → watch → collect/bin |
| ➖ | `_output_port_extensions` / `_output_port_capability_ids` / `_bin_outputs_by_extension` | method | Internal | — | — | output binning (#680) |
| ✅ | `_PopenProcessAdapter` | class | **Internal — resolved (b)** | — | — | owner 2026-06-27 (b): #1817 teaches `FileWatcher` to accept a plain `subprocess.Popen` (treat `.poll() is None` as alive) → adapter stays internal, the concept leaves the public surface; imaging passes the raw `Popen` directly (cross-repo migration) |
| ➖ | `_normalize_extension` / `_cleanup_process` | function | Internal | — | — | module helpers |

Inherits the `Block` surface (§4.1); sets provisional defaults for `execution_mode`
(EXTERNAL), `variadic_inputs`/`variadic_outputs`, `terminate_grace_sec`, ports, and
`config_schema`.

### 7.2 `bridge.py` — file-exchange facilities (pending survey)

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `FileExchangeBridge` | class | Public | provisional | 0.3.1 | survey: imaging uses `bridge.launch(...)` (proven demand); default bridge (prepare/launch/watch/collect) |
| ✅ | `ExternalAppBridge` | protocol | Public | provisional | 0.3.1 | bridge protocol; owner "all provisional"; ⚠️ zero current importers + `launch` signature drift vs impl (missing `argv_override`) — reconcile in #1817 |
| ✅ | `_guess_mime` | function | **Internal — remove/replace (c)** | — | — | survey: extension→MIME is **non-load-bearing** (`Artifact.mime_type` only written to a provenance sidecar; nothing branches on it; dispatch uses extension→format-id, not MIME) and **copy-pasted 4× in core** (bridge, `data_access`, `load_data._MIME_GUESS`, plot `_PLOT_MIME`). Per owner's "core must not infer from extensions": **not public**. #1817 replaces each caller with `None` or an authoritative source (declared type / `FormatCapability.format_id` / `StorageReference.format` / sidecar); typed path already sets `mime_type=None`. imaging's `from …bridge import _guess_mime` is a cross-repo migration (tracked deferral) |
| ➖ | `_external_app_launch_env` / `_materialise_data_object` / `_bridge_materialise_to_file` / `_bridge_default_extension_for` / `_resolve_saver_capability_for` / `_resolve_core_type_param` / `_get_registry` / `_default_extension_for_obj` / `_normalise_config_extension` / `_normalise_capability_id` / `_port_config_by_name` / `_try_mount_existing_path` / `_CORE_TYPE_DEFAULT_EXTENSION` | function/const | Internal | — | — | bridge internals |

### 7.3 `watcher.py` (pending survey)

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `FileWatcher` | class | Public | provisional | 0.3.1 | survey: imaging instantiates with full kwargs (`process_handle`/`timeout`/`stability_period`/`done_marker`) — proven demand. Per owner (b), #1817 makes `process_handle` accept a plain `subprocess.Popen` (no adapter needed) |
| ✅ | `ProcessExitedWithoutOutputError` | exception | Public | provisional | 0.3.1 | survey: imaging + core catch it; the watcher's documented raise contract |
| ➖ | `_snapshot` / `_diff` / `_matches` | method | Internal | — | — | polling internals |

### 7.4 `command_validator.py` (pending survey)

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `validate_app_command(command)` | function | Public | provisional | 0.3.1 | owner "all provisional": publish to complete the facility set (#70 security contract). Survey: not reached by imaging today (bridge validates internally) — weak demand but cheap/harmless |
| ➖ | `_SHELL_META` | constant | Internal | — | — | |

**`BlockCancelledByAppError`** (defined in `blocks.base.exceptions`, §4.7;
Public/provisional) — re-export from `scistudio.blocks.app` as its AppBlock-authoring
home (#1817).

**Net `app.__all__` change (#1817):** keep `AppBlock`; add `FileExchangeBridge`,
`FileWatcher`, `ProcessExitedWithoutOutputError`, `validate_app_command`, and
`ExternalAppBridge` (all provisional) + re-export `BlockCancelledByAppError`. Both
reach-throughs stay **internal** (owner-resolved): `_PopenProcessAdapter` (b) —
`FileWatcher` accepts a plain `Popen`; `_guess_mime` (c) — extension→MIME removed/replaced.
**§7 fully decided.**

## 7A. Code Blocks — `scistudio.blocks.code`

Added per owner 2026-06-27 (add CodeBlock; default provisional). `CodeBlock` is a
block-authoring base on par with `ProcessBlock` (§5) / `IOBlock` (§6) / `AppBlock` (§7) —
`registry/_spec` categorizes it as one of the six bases (io/process/**code**/app/ai/
subworkflow) and the write-block skill teaches it — but it was missing from the governed
surface. **Whole CodeBlock surface = `provisional`** (ADR-041-recent; no package subclasses
it yet — `accucor`/`accucor2` are planned, not written). Numbered §7A to avoid renumbering
§8–§18 and their cross-references.

> Requires an `ADR-052.md` `governs.modules` (+ §3 prose) addition of
> `scistudio.blocks.code` — batched with the §3.1 xlsx wording, pending owner.

Canonical root: `from scistudio.blocks.code import …`. Current `__all__`: `CodeBlock`,
`CodeBlockBackend`, `CodeBlockRuntimeContext`, `LazyList`, `register_codeblock_backend`,
`unregister_codeblock_backend`, `list_codeblock_backends`, `resolve_codeblock_backend`,
`ensure_codeblock_backends_loaded`, `run_codeblock_process`.

**`CodeBlock(Block)`** — ✅ Public / `provisional` / 0.3.1. Base for user scripts
(Python / R / Julia) run via an interpreter backend over a file-exchange boundary (ADR-041).

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `CodeBlock` | class | Public | provisional | 0.3.1 | script-authoring base; subclass to pin a packaged script + ports (e.g. an R/accucor wrapper) |
| ✅ | `name` / `description` / `variadic_inputs` / `variadic_outputs` / `input_ports` / `output_ports` | ClassVar | Public | provisional | 0.3.1 | inherited Block ClassVars (defaults) |
| ✅ | `config_schema` | ClassVar | Public | provisional | 0.3.1 | `script_path` / `interpreter_mode` / `interpreter_path` / `exchange_root` / declared `inputs`/`outputs` + port editor |
| ✅ | `__init__(config)` / `run(inputs, config)` | method | Public | provisional | 0.3.1 | `run` does exchange → launch → collect (no `process_item` hook; subclassing pins config/script) |

Config models (`config.py`):

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `CodeBlockConfig` | class | Public | provisional | 0.3.1 | the validated config model |
| ✅ | `PortFileConfig` | class | Public | provisional | 0.3.1 | per-port file config (name/direction/data_type/extension/capability_id/required/exchange_folder) |
| ✅ | `CodeBlockConfigError` | exception | Public | provisional | 0.3.1 | owner 2026-06-27: raised on invalid CodeBlock config; authors catch it (cf. §6.3 capability errors); **add to `blocks.code.__all__`** (not in it today) |
| ➖ | `MigrationDiagnostic` | class | Internal | — | — | legacy-config migration diagnostic model |
| ➖ | `resolve_project_path(...)` / `legacy_migration_diagnostics(config)` | function | Internal | — | — | path resolution + legacy-config migration tooling |

Backend-registration surface (`_backends_registry.py`) — all Public / provisional
(owner 2026-06-27, publish-all):

| St | Member | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `CodeBlockBackend` (Protocol) / `register_codeblock_backend` / `unregister_codeblock_backend` / `resolve_codeblock_backend` / `list_codeblock_backends` / `ensure_codeblock_backends_loaded` / `CodeBlockRuntimeContext` / `LazyList` | class/func | Public | provisional | 0.3.1 | backend-registration API + lazy list (already in `__all__`) |
| ✅ | `run_codeblock_process` / `CodeBlockTimeoutError` / `codeblock_exchange_env` | func/exc | Public | provisional | 0.3.1 | subprocess runner + timeout exception + exchange-env helper |

Full `blocks/code` module map. **Owner 2026-06-27: publish the entire `blocks/code`
non-underscore surface as Public / provisional**, re-exported from `blocks.code.__all__`
(#1817). The legacy runner layer is **dead code, deleted in #1817** (below; 0 production
importers — owner chose removal over deprecation); leading-underscore names stay internal.

| St | Module / symbol | Disposition | Notes |
|----|-----------------|-------------|-------|
| ✅ | `interpreters.InterpreterResolutionError` / `UnsupportedScriptExtensionError` | Public / provisional | catchable interpreter errors |
| ✅ | `exchange.CodeBlockExchangeError` | Public / provisional | catchable exchange error |
| ✅ | `introspect.introspect_script(path)` | Public / provisional | reads a script's declared ports |
| ✅ | `exchange.MaterialiseAdapter` / `ReconstructAdapter` (Protocol) | Public / provisional | custom-exchange extension points |
| ✅ | `exchange.*` records + functions (`CodeBlockExchangeManifest`/`Layout`/`Port`, `ExchangeFileRecord`/`Diagnostic`, `PortManifestRecord`, `OutputDiscoveryResult`; `prepare_codeblock_exchange`/`collect_codeblock_outputs`/`discover_declared_outputs`/`create_*`/`allocate_*`/`plan_*`/`initialise_*`/`normalise_extension`/`safe_exchange_name`) | Public / provisional | file-exchange surface |
| ✅ | `interpreters.ResolvedInterpreter` / `resolve_script_interpreter` / `InterpreterFamily` | Public / provisional | interpreter resolution |
| ✅ | `provenance.*` (`ScriptProvenance`/`EnvironmentSnapshot`/`CodeBlockProvenancePayload` + `capture_*`/`build_*`/`utc_now_iso`) | Public / provisional | provenance models/capture |
| ✅ | `validation.*` (`validate_codeblock_config` + `CodeBlockValidationDiagnostic` + `codeblock_config_payload`/`resolve_codeblock_data_type`/`selected_codeblock_capabilities`) | Public / provisional | config validation |
| ✅ | `backends/*` (`python`/`r_quarto`/`notebook`/`shell`/`matlab` backend classes) | Public / provisional | concrete backends; subclassable for a custom backend |
| ➖ | `runner_registry.RunnerRegistry` + `runners/*` (`python_runner`/`r_runner`/`julia_runner`/`base`) | **Delete (dead code)** | owner 2026-06-27: **delete** — 0 production importers (`code_block.py` uses `backends/`); #1817 removes `runner_registry.py` + `runners/*` + their tests (`test_runner_registry.py`/`test_runners_subprocess.py` + the `test_code_block.py` runner import). Not public |
| ➖ | leading-underscore internals (`_backends_registry` privates, `_SAFE_NAME_PATTERN`, `_ITEM_COUNT_WARNING_THRESHOLD`, …) | Internal | underscore convention |

## 8. Previewer Authoring — `scistudio.previewers`

**Canonical author roots (regularized):**

- `scistudio.previewers.models` — spec / manifest / request / envelope / enum /
  error-info / provider-protocol types.
- `scistudio.previewers.data_access` — the injected `PreviewDataAccess` reader and
  its bounded-read result dataclasses.
- One helper, `sanitize_svg`, currently lives in `scistudio.previewers.fallbacks`
  (otherwise a core-internal module). It is author-facing (a package SVG/plot
  previewer reuses it) and is **mis-homed**: relocate it to a public helper home
  in #1823 so the author surface is `models` + `data_access` + that helper, with
  no author import from `fallbacks`.

The operational classes (`PreviewerRegistry`, `PreviewRouter`,
`PreviewSessionManager`, `PreviewService`, `build_preview_service`,
`get_preview_service`, `load_project_previewers`) remain importable but are
**Internal** — core owns routing, session lifecycle, safety limits, bounded data
access, asset serving, and the generic fallback viewers (ADR-048); packages only
*register* previewers through the `scistudio.previewers` entry point. They appear
in `previewers/__init__.__all__` today; #1817 reconciles that `__all__` against
this contract (presence in `__all__` is not an author stability promise — §2).

**Subsystem tier:** the whole preview subsystem is **`provisional`** (owner
2026-06-27) — it is young (ADR-048; refactors #1579/#1598) and expected to settle,
the same posture taken for app blocks (§7) and code blocks (§7A).

**Reference implementation:** `scistudio-blocks-spectroscopy` is the canonical
shape — it splits registration (`previewers/__init__.py`: only `PreviewerSpec` /
`FrontendManifest`) from provider logic (`previewers/providers.py`), reads every
payload through the injected `PreviewDataAccess`, raises `ProviderError` for hard
failures while embedding `PreviewErrorInfo` for routine ones, and reuses
`sanitize_svg`. `scistudio-blocks-imaging` is **not** a model to follow (monolithic
module; its own array loader bypassing `PreviewDataAccess`; uses the legacy
`png_data_uri`); it is being rewritten, so symbols only it touches carry no weight.

File checklist:

- [x] `models.py` (650) — author type surface (§8.1)
- [x] `data_access.py` (804) — `PreviewDataAccess` + result types (§8.2)
- [x] `fallbacks.py` (629) — `sanitize_svg` public; 8 core providers + `core_previewer_specs` internal (§8.3)
- [x] `__init__.py` (164), `registry.py` (282), `router.py` (234), `session.py` (617), `project.py` (120), `assets.py` (161) — operational layer, Internal (§8.4)
- [x] `_raster.py` (101), `_table_cache.py` (127) — underscore-private internals

### 8.1 `models.py`

Canonical root: `from scistudio.previewers.models import …`. `__all__` declares 29
symbols. Both public packages import from here; usage is cited per row.

| St | Symbol | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `PREVIEWER_API_VERSION` | constant | Public | provisional | 0.3.1 | both packages stamp it on spec/manifest |
| ✅ | `OwnerKind` | class (StrEnum) | Public | provisional | 0.3.1 | author sets `OwnerKind.PACKAGE` |
| ✅ | `EnvelopeKind` | class (StrEnum) | Public | provisional | 0.3.1 | author sets the envelope kind (SERIES/ARRAY/COMPOSITE/ERROR seen) |
| ✅ | `TargetKind` | class (StrEnum) | Public | provisional | 0.3.1 | provider reads `target.kind` |
| ✅ | `PreviewErrorCode` | class (StrEnum) | Public | provisional | 0.3.1 | author embeds the code in `PreviewErrorInfo`; the canonical error vocabulary |
| ✅ | `PreviewerSpec` | class | Public | provisional | 0.3.1 | author returns these from `get_previewers` |
| ✅ | `FrontendManifest` | class | Public | provisional | 0.3.1 | same-origin UI descriptor the author ships |
| ✅ | `PreviewRequest` | class | Public | provisional | 0.3.1 | provider input (carries `target`/`spec`/`query`/`data_access`/`limits`); #1823 adds typed `storage`/`record_metadata` fields — see §8.5 |
| ✅ | `PreviewTarget` | class | Public | provisional | 0.3.1 | read off the request; shape: `kind`/`ref`/`recorded_type`/`type_chain`/`collection_item_type`/`is_collection` |
| ✅ | `PreviewSource` | class | Public | provisional | 0.3.1 | optional display identity on `target.source` (no runtime truth) |
| ✅ | `PreviewLimits` | class | Public | provisional | 0.3.1 | session budgets surfaced on `request.limits` |
| ✅ | `PreviewEnvelope` | class | Public | provisional | 0.3.1 | author returns it; `with_session()` is runtime-only (manager binds the session id) |
| ✅ | `PreviewMetadata` | class | Public | provisional | 0.3.1 | author sets the six FR-011 flags + `extra` |
| ✅ | `PreviewResource` | class | Public | provisional | 0.3.1 | author declares bounded follow-up resources |
| ✅ | `PreviewErrorInfo` | class | Public | provisional | 0.3.1 | author embeds a typed error in a failed envelope |
| ✅ | `PreviewProvider` | type-alias | Public | provisional | 0.3.1 | `Callable[[PreviewRequest], PreviewEnvelope]` — the provider shape |
| ✅ | `PreviewResourceProvider` | type-alias | Public | provisional | 0.3.1 | optional follow-up resource reader shape |
| ✅ | `PreviewerEntryPoint` | protocol | Public | provisional | 0.3.1 | `() -> list[PreviewerSpec]` entry-point shape |
| ✅ | `PreviewerSpecList` | type-alias | Public | provisional | 0.3.1 | `list[PreviewerSpec]` return alias |
| ✅ | `PreviewError` | class (Exception) | Public | provisional | 0.3.1 | base; authors catch |
| ✅ | `ProviderError` | class (Exception) | Public | provisional | 0.3.1 | authors raise for hard failures (spectroscopy raises it 5×) |
| ✅ | `PreviewSession` | class | Internal | — | — | backend-owned session record; neither package imports it |
| ✅ | `RoutingAmbiguityError` | class (Exception) | Internal | — | — | runtime raises (router); author signals via `PreviewErrorCode` instead |
| ✅ | `UnknownPreviewerError` | class (Exception) | Internal | — | — | runtime raises |
| ✅ | `UnknownTargetError` | class (Exception) | Internal | — | — | runtime raises |
| ✅ | `MissingBundleError` | class (Exception) | Internal | — | — | runtime raises (asset layer) |
| ✅ | `InvalidSpecError` | class (Exception) | Internal | — | — | runtime raises (registry) |
| ✅ | `DuplicatePreviewerIdError` | class (Exception) | Internal | — | — | runtime raises (registry) |

Note: every public dataclass here carries a `to_dict()` wire-serialization hook the
API layer calls; it is framework-facing, not part of the authoring path. #1817 drops
the 7 Internal rows (`PreviewSession` + the 6 runtime-raised errors) from
`models.__all__`.

### 8.2 `data_access.py`

Canonical root: `from scistudio.previewers.data_access import …`. `__all__` declares
15 symbols. `PreviewDataAccess` is **constructed by the runtime and injected** on
`request.data_access`; authors call its methods and never instantiate it. The
result dataclasses are **read-only outputs** authors receive, not types they build.

| St | Symbol | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `PreviewDataAccess` | class | Public | provisional | 0.3.1 | the only sanctioned payload-read surface; runtime-injected, not author-constructed |
| ✅ | `PreviewDataAccess.dataframe_page` | method | Public | provisional | 0.3.1 | bounded table page (spectroscopy uses) |
| ✅ | `PreviewDataAccess.table_xy_points` | method | Public | provisional | 0.3.1 | complete x/y points from two columns (spectroscopy uses) |
| ✅ | `PreviewDataAccess.array_plane` | method | Public | provisional | 0.3.1 | bounded N-D plane (imaging uses) |
| ✅ | `PreviewDataAccess.array_tile` | method | Public | provisional | 0.3.1 | bounded 2-D tile |
| ✅ | `PreviewDataAccess.series_points` | method | Public | provisional | 0.3.1 | complete curve points |
| ✅ | `PreviewDataAccess.text_chunk` | method | Public | provisional | 0.3.1 | bounded text chunk |
| ✅ | `PreviewDataAccess.artifact_metadata` | method | Public | provisional | 0.3.1 | bounded artifact metadata + small-image data URI |
| ✅ | `PreviewDataAccess.composite_slots` | method | Public | provisional | 0.3.1 | slot inventory (both packages use) |
| ✅ | `PreviewDataAccess.composite_raster_slot` | method | Public | provisional | 0.3.1 | bounded composite raster-slot read (imaging uses) |
| ✅ | `PreviewDataAccess.collection_sample` | method | Public | provisional | 0.3.1 | bounded collection item sample |
| ✅ | `PreviewDataAccess.png_data_uri` | method | Internal | — | — | legacy grayscale-PNG path; docstring "legacy-compat only"; sole caller is imaging, which is being rewritten |
| ✅ | `DataFramePage` | class | Public | provisional | 0.3.1 | return type |
| ✅ | `ArrayPlane` | class | Public | provisional | 0.3.1 | return type (imaging imports it) |
| ✅ | `SliceAxis` | class | Public | provisional | 0.3.1 | nested in `ArrayPlane.slice_axes` (imaging imports it) |
| ✅ | `ArrayTile` | class | Public | provisional | 0.3.1 | return type |
| ✅ | `SeriesPoints` | class | Public | provisional | 0.3.1 | return type |
| ✅ | `TableXYPoints` | class | Public | provisional | 0.3.1 | return type |
| ✅ | `TextChunk` | class | Public | provisional | 0.3.1 | return type |
| ✅ | `ArtifactInfo` | class | Public | provisional | 0.3.1 | return type |
| ✅ | `CompositeSlots` | class | Public | provisional | 0.3.1 | return type |
| ✅ | `CollectionSample` | class | Public | provisional | 0.3.1 | return type |
| ✅ | `DEFAULT_MAX_ROWS` | constant | Internal | — | — | runtime budget default; authors read budgets via `PreviewLimits` |
| ✅ | `DEFAULT_MAX_BYTES` | constant | Internal | — | — | as above |
| ✅ | `DEFAULT_MAX_ITEMS` | constant | Internal | — | — | as above |
| ✅ | `DEFAULT_MAX_TILE` | constant | Internal | — | — | as above |
| ✅ | `DEFAULT_MAX_DIM` | constant | Internal | — | — | as above |

### 8.3 `fallbacks.py`

Not an author root. Holds core's own fallback viewers; one helper escaped here and
is author-facing.

| St | Symbol | Kind | Disposition | Tier | Since | Notes |
|----|--------|------|-------------|------|-------|-------|
| ✅ | `sanitize_svg` | function | Reach-through (relocate) | provisional | 0.3.1 | spectroscopy imports it for SVG/plot previewers; relocate out of `fallbacks` to a public helper home in #1823 |
| ➖ | `dataframe_previewer` / `array_previewer` / `series_previewer` / `text_previewer` / `artifact_previewer` / `composite_previewer` / `collection_previewer` / `plot_previewer` / `base_fallback_previewer` | function | Internal | — | — | core's own fallback viewers; authors may read as reference impls, do not import |
| ➖ | `core_previewer_specs` | function | Internal | — | — | builds the core spec list at registry load |

### 8.4 Operational layer — Internal

Neither public package imports any of these; core owns the machinery (ADR-048).

| St | Symbol | Module | Disposition | Notes |
|----|--------|--------|-------------|-------|
| ➖ | `PreviewerRegistry` | registry.py | Internal | spec registration + entry-point discovery |
| ➖ | `PREVIEWER_ENTRY_POINT_GROUP` / `COMPANION_ENTRY_POINT_GROUPS` | registry.py | Internal | authors write the literal `"scistudio.previewers"` group in `pyproject.toml`, not the constant |
| ➖ | `PreviewRouter` | router.py | Internal | resolution order / precedence |
| ➖ | `PreviewSessionManager` | session.py | Internal | session lifecycle, framework manifest-stamping |
| ➖ | `PreviewService` / `build_preview_service` / `get_preview_service` | __init__.py | Internal | API-runtime bundle + accessor |
| ➖ | `load_project_previewers` / `PROJECT_PREVIEWERS_DIR` / `PROJECT_PREVIEWERS_MANIFEST` | project.py | Internal | project-local drop-in loading |
| ➖ | `validate_manifest` / `resolve_asset` / `is_remote_url` / `ManifestValidation` / `ServedAsset` | assets.py | Internal | backend asset validator / path-confinement (FR-024) |

### 8.5 Storage access — `request.storage` (closing the `_storage` leak)

Providers must read payloads **without catalog access** (FR-009), so the runtime
resolves the storage reference and hands it to the provider. That need is
legitimate and not package-specific — core's own fallback viewers (`fallbacks.py`),
spectroscopy, and imaging all rely on it. The *mechanism*, however, leaks a core
type into author code and is to be closed in #1823.

**Today (verified data flow):** `ApiRuntime.enrich_preview_query`
(`api/runtime/_data.py`) already holds a typed `StorageReference` (`record.ref`)
but **downgrades it to a JSON dict** under `request.query["_storage"]` (plus
`["_record_metadata"]`), because `query` crosses REST and is persisted on
`PreviewSession.query`. Every provider then re-imports
`scistudio.core.storage.ref.StorageReference` and rebuilds it from that dict
before calling `PreviewDataAccess`.

**Target (#1823):** add typed fields `storage: StorageReference | None` and
`record_metadata: dict` to `PreviewRequest` — an in-process object that already
carries the live `PreviewDataAccess` and is never serialized — populated by the
`PreviewSessionManager`. Providers then read `request.storage` and forward it to
`data_access.*`; they **no longer import `StorageReference` or touch `_storage`**.
The `_storage` / `_record_metadata` query keys demote to a **runtime-internal
serialization detail** (session persistence / resume), not an author contract.

| St | Surface element | Disposition | Tier | Since | Notes |
|----|-----------------|-------------|------|-------|-------|
| ✅ | `PreviewRequest.storage` (typed field, adds in #1823) | Public | provisional | — | the sanctioned way a provider obtains its `StorageReference`; replaces the `_storage` rebuild |
| ✅ | `PreviewRequest.record_metadata` (typed field, adds in #1823) | Public | provisional | — | replaces the `_record_metadata` query read |
| ✅ | `request.query["_storage"]` / `["_record_metadata"]` | Internal | — | — | runtime serialization form for session persistence; not an author contract (was an implicit one) |
| ➖ | `StorageReference` (`scistudio.core.storage.ref`) | Public (via `core.types` re-export, §3) | — | — | appears in `PreviewDataAccess` signatures + the new `request.storage` field; previewer authors only pass it through, never import or construct it. Canonical inventory tracked under the core.storage governed-modules gap (§17), unchanged by this section |

## 9. Plot `render(collection)` Contract

This is an **import-free, duck-typed, dual-interpreter (Python + R) authoring
contract**, not an importable-symbol surface. A plot script defines exactly
`def render(collection):` (R: `render <- function(collection)`) — the validator
rejects any other entrypoint, including `render(collection, context)`. The harness
runs the script in a **confined CodeBlock subprocess** (§7A), injects a
`collection` object, calls `render(collection)`, and collects the return value. The
script **imports nothing from `scistudio`**.

The implementing classes (`_PlotCollection`, `_PlotItem`, `_PlotItems`) are private
and live in `scistudio.ai.agent.mcp.tools_plot._harness`; the input envelope
(`{schema_version, collection: {types, items}}`) is built by
`scistudio.ai.agent.mcp.tools_plot.runtime._input_envelope`. None of these are
author-importable. The public contract is therefore the **shape** of the injected
object plus the **return contract**, recorded below. (These module paths are the
relocation target of #1824; the contract shape does not depend on where they live.)

**Tier = `provisional` (owner 2026-06-27); no behavior change.** The plot feature
is currently stable; this section records the contract exactly as it ships at
`0.3.1` and proposes **no behavior change**. Its current home under the AI-agent
MCP tooling is architecturally wrong, though — the user-facing REST route
`api/routes/plots.py` already imports up into `tools_plot` — so a
**behavior-preserving relocation** to a first-class home is tracked in **#1824**
(the `render(collection)` shape and return contract are unchanged by that move).
Enforcement (§15)
is a **behavior-pinning contract test** (a Python + R reference `render(collection)`
that asserts the shape and the return handling) added in the #1817 enforcement
phase — it freezes current behavior and changes nothing.

**Injected `collection` shape:**

| St | Surface element | Disposition | Tier | Since | Notes |
|----|-----------------|-------------|------|-------|-------|
| ✅ | `collection.types` | Public (shape) | provisional | 0.3.1 | `tuple[str, ...]` (Py) / character vector (R); distinct non-`DataObject` type names present |
| ✅ | `collection.items` | Public (shape) | provisional | 0.3.1 | ordered container: `len()` / iterate / `[i]` |
| ✅ | `collection.items.open(max_items=None)` | Public (shape) | provisional | 0.3.1 | list of opened payloads; byte-budget guarded (`max_input_bytes`) |
| ✅ | `collection.items.open_one()` | Public (shape) | provisional | 0.3.1 | first item opened; empty → `IndexError` (Py) / `stop` (R) |
| ✅ | `item.type` | Public (shape) | provisional | 0.3.1 | `str`; one of `Array`/`DataFrame`/`Series`/`Text`/`Artifact`/`CompositeData`; default `"DataObject"` |
| ✅ | `item.metadata` | Public (shape) | provisional | 0.3.1 | read-only (`MappingProxyType`); public keys only (strip-list below) |
| ✅ | `item.open()` | Public (shape) | provisional | 0.3.1 | materialized **native** payload per `item.type` (table below) — not a `DataObject` |

**`item.open()` return type by `item.type`:**

| `item.type` | `open()` returns |
|-------------|------------------|
| `Array` | `numpy.ndarray` |
| `DataFrame` | `pandas.DataFrame` |
| `Series` | `pandas.Series` (single column) / `pandas.DataFrame` (≥2 columns, #1750 — preserves both axes, e.g. a Spectrum's `{lambda, intensity}`) |
| `Text` | `str` |
| `Artifact` | `pathlib.Path` |
| `CompositeData` | `dict[str, <opened slot payload>]` (recurses one level) |

`item.open()` hands the author **vanilla scientific objects** (numpy / pandas / str /
Path / dict), never a `scistudio` `DataObject` — a deliberate non-`DataObject`
authoring boundary consistent with "a plot script imports nothing from
`scistudio`". It is a sanctioned pandas/numpy surface, logged in the §10 boundary
ledger.

**`item.metadata` strip-list:** the harness removes the storage/lineage-internal
keys `backend`, `format`, `path`, `storage_ref`, `storage`, `type_chain`,
`item_type`, `slots`; everything else passes through read-only. This filter is part
of the contract (it defines what a plot author may read).

**Return contract** — `render(collection)` returns one of:

| St | Returned value | Handling | Notes |
|----|----------------|----------|-------|
| ✅ | a Matplotlib figure (duck-typed: has `.savefig`) | saved to the working dir | format from the manifest's preferred/allowed set |
| ✅ | an artifact path (`str` / `pathlib.Path`) | collected | **must resolve inside the plot working dir** (else `PermissionError`) and exist (else `FileNotFoundError`) |
| ✅ | a `list` / `tuple` of the above | each collected | mixed figures + paths allowed |
| ✅ | `None`, or any other type | rejected | `None` → `ValueError`; other → `TypeError` |

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
single sanctioned pandas-using data-flow exception is the `.xlsx` reader/writer
(#1810; impl. PR #1815, OPEN), per ADR-052 §3.1 — surveyed and verified to use
pandas/openpyxl only at the format boundary and return Arrow-backed `DataObject`s
downstream (see the §6 xlsx note).

A second, distinct sanctioned boundary is the **plot `render(collection)` output
path** (§9): `item.open()` hands the plot author native numpy / pandas / str /
Path / dict, never a `DataObject`. This is an author-output boundary (a plot script
imports nothing from `scistudio`), not a data-flow block, so it is recorded
separately from the `.xlsx` data-flow exception. Provisional, no behavior change.

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
| ✅ | `scistudio.blocks.app.bridge._guess_mime` | imaging | a | **(c) remove/replace** — extension→MIME is non-contract (non-load-bearing; 4 copies in core); **not public**; imaging migrates to the declared type / `None` (cross-repo) | #1817 |
| ✅ | `scistudio.blocks.app.app_block._PopenProcessAdapter` | imaging | a | **(b) remove the need** — `FileWatcher` accepts a plain `Popen`; adapter stays internal; imaging passes the raw `Popen` (cross-repo) | #1817 |
| ✅ | `scistudio.previewers.data_access` (internals) | — | a | resolved §8: `data_access` is a canonical author root; the `StorageReference` / `_storage` leak is closed via typed `request.storage` (§8.5) | #1823 |
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
- **Import-free contracts get a behavior-pinning test.** The §9 plot
  `render(collection)` contract has no importable symbol, so the symbol snapshot
  cannot cover it. It is frozen instead by a **contract test**: a Python + R
  reference `render(collection)` that asserts the injected shape
  (`collection.types` / `.items` / `open` / `open_one`; `item.type` / `.metadata` /
  `.open()` return types) and the return handling (figure / in-dir path / list /
  rejects). The test pins current behavior and changes nothing; it lives under the
  same owner-reviewed `tests/api/**` protection.

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
- **✅ Plot `collection` vs `core.types.Collection` (resolved §9).** §9's plot
  `render(collection)` shape (`.types`, `.items.open()/open_one()`,
  `item.type/metadata/open()`) is a distinct object from `core.types.Collection`
  (ADR-020: `item_type`, `__iter__`, `storage_refs`) — same name, different objects.
  Located in the harness (`scistudio.ai.agent.mcp.tools_plot._harness`; relocation
  tracked #1824) and inventoried in §9 as an import-free, provisional contract.
- **🤔 CodeBlock missing from the governed surface (survey done, owner to confirm).**
  `scistudio.blocks.code` / `CodeBlock` is not in ADR-052 `governs.modules`, but the
  survey confirms CodeBlock **is** a genuine authoring base — `registry/_spec`
  categorizes it as one of the six bases (io/process/**code**/app/ai/subworkflow)
  exactly like `AppBlock`, and the write-block skill teaches it as a base to extend. It
  is also a single GUI builtin and has a real R/Quarto backend (the accucor fit).
  `accucor`/`accucor2` do **not** exist yet (LCMS is the bare template) — demand is
  latent/planned. **Recommend:** add a new §-section (provisional, mirroring AppBlock §7)
  + `governs.modules` + §3 update. `CodeBlock` base public/provisional; the
  backend-registration surface (`CodeBlockBackend`, `register_codeblock_backend`,
  `resolve`/`list`/`ensure_codeblock_backends_loaded`, `CodeBlockRuntimeContext`,
  `LazyList`) public/provisional **if** an accucor wrapper registers a custom
  interpreter; exact backend symbol set deferred until that design lands (like §13.2).
  `run_codeblock_process` / `unregister_codeblock_backend` / `CodeBlockTimeoutError` /
  `codeblock_exchange_env` lean internal. **Resolved (owner 2026-06-27): added as §7A,
  default provisional.** `ADR-052.md` `governs.modules` + §3 done. Owner 2026-06-27:
  **entire `blocks/code` non-underscore surface Public/provisional** (backend subset
  un-deferred); legacy runner layer **deprecated**.

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
| 2026-06-27 | **A confirmed (owner):** `TypeRegistry` + `TypeSpec` → **Internal** (drop from `core.types.__all__` in #1817; internal path unchanged, no package change). **core/types §3 now fully decided.** | Survey: 0 author importers. |
| 2026-06-27 | `block.py` decided (§4.1): `Block` public/stable; all authoring ClassVars stable EXCEPT `dynamic_ports` provisional; `get_effective_input/output_ports` public/stable; `get_panel_manifest` public/provisional (returns public `PanelManifest`); Collection utils + `persist_*` stable; `_auto_flush` internal. | Owner 2026-06-27. PanelManifest class itself is public (interactive.py). |
| 2026-06-27 | `blocks.base` remainder (§4.2–§4.7): `BlockConfig`/`InputPort`/`OutputPort`/`ExecutionMode`/`PackageInfo` public/stable; **demote** `Port`/`BlockState`/`BlockResult` to internal; **add** `PackageOtaSource` public/provisional; port-helper functions pending survey; `BlockCancelledByAppError` deferred to §7. | Owner 2026-06-27. |
| 2026-06-27 | Port-helper survey (3rd background agent): all four (`port_accepts_type`/`port_accepts_signature`/`validate_connection`/`validate_port_constraint`) have **0 author/package use** — every caller is framework (`Block.validate`, workflow validator, `/validate-connection`); `port_accepts_signature` has 0 call sites anywhere (dead-code candidate). Recommend demote all 4. | Awaiting owner confirm; contradicts the "maybe author-useful" hypothesis. |
| 2026-06-27 | **Confirmed (owner):** port helpers → all 4 internal (`port_accepts_signature` dead-code keep/delete tracked under #1817). `interactive.py` (§4.8): whole ADR-051 interactive surface public/**provisional**; `SupportsInteraction`/`coerce_prompt`/`serialise_storage_ref`/`deserialise_storage_ref`/`INTERACTIVE_INTERMEDIATE_KEY` → internal. **§4 blocks.base now fully decided.** | Owner 2026-06-27. |
| 2026-06-27 | `BlockCancelledByAppError` → **Public/provisional** (owner 2026-06-27), resolving the §4.7 deferral: AppBlock package subclasses raise it when their external app exits without output (#681). Add to public (canonical path: `blocks.app` re-export; confirm #1817). | Owner 2026-06-27. |
| 2026-06-27 | `process` (§5) recorded: `ProcessBlock` public/stable (`algorithm`/`setup`/`teardown`/`process_item`[3-arg]/`run`); `to_arrow` + `_process_item_takes_state` internal. No new decisions. | Mechanical; `__all__` = `ProcessBlock` only. |
| 2026-06-27 | `io` (§6) decided: `IOBlock`/`SimpleLoader`/`SimpleSaver` public/stable; `FormatCapability`/`MetadataFidelity`/`CapabilityDirection`/`MetadataFidelityLevel` + the 5 capability errors public/stable (errors kept public — authors catch for fallback); `IOBlock.supported_extensions` → **deprecated** (⚠️); `normalize_*` + `materialise_to_file`/`reconstruct_from_file` → internal; `LoadData`/`SaveData` pending survey. | Owner 2026-06-27. |
| 2026-06-27 | LoadData/SaveData survey (4th background agent): 0 author/package imports or subclasses (spectroscopy + imaging subclass `IOBlock` + register capabilities; never touch LoadData/SaveData); core GUI builtins; `_unified_dispatch` delegates to package blocks (confirms "inject into loader"). Recommend internal. | Awaiting owner confirm. |
| 2026-06-27 | PR #1815 (xlsx, closes #1810) survey (5th agent): OPEN/unmerged; **no new public symbol** (all underscore-private); layers behavior on `FormatCapability`/`LoadData`/`SaveData`/`user` slot; **conforms** to the §3.1 pandas exception (pandas only at the format boundary). §10 citation refreshed to "#1810, PR #1815, reader/writer"; ADR-052 §3.1 "loader"→"reader/writer" widening proposed to owner. | Owner asked to survey 1815's public-API impact. |
| 2026-06-27 | **Confirmed (owner):** `LoadData`/`SaveData` → Internal (drop from `io.__all__`; deep path stays for internal callers). **§6 io fully decided.** §7 app on hold (owner reviewing AppBlock). | Owner 2026-06-27. |
| 2026-06-27 | `app` (§7) tiering: owner 2026-06-27 — **whole AppBlock surface `provisional`** (area expected to churn with bug-fixes). `AppBlock` public/provisional; file-exchange/watcher facilities (Bridge/Watcher) lean public/provisional per §3; `_guess_mime`/`_PopenProcessAdapter` reach-throughs need public homes. Dispatched app survey (6th agent) to resolve the exact public facility set + reach-through homes. | Owner 2026-06-27. |
| 2026-06-27 | Owner: LCMS may wrap `accucor`/`accucor2` by subclassing `CodeBlock` (`scistudio.blocks.code`), which is **not** in ADR-052 governed surface. Dispatched lcms/CodeBlock survey (7th agent) to confirm + scope a public CodeBlock authoring API. Potential governed-surface gap (§17). | Owner 2026-06-27. |
| 2026-06-27 | App survey (6th agent): only imaging authors AppBlocks (`FijiBlock`/`NapariBlock`); it reaches `FileExchangeBridge`/`FileWatcher`/`ProcessExitedWithoutOutputError` (proven) + the 2 reach-throughs. §7 facilities → public/provisional (incl. `validate_app_command` + `ExternalAppBridge` per owner "all provisional"; ExternalAppBridge has 0 importers + signature drift). Reach-throughs `_PopenProcessAdapter`/`_guess_mime`: resolution options presented — prefer removing the need. | Owner to pick reach-through resolutions. |
| 2026-06-27 | CodeBlock/lcms survey (7th agent): accucor/accucor2 do NOT exist yet (LCMS is the bare template) — forward-looking intent. But CodeBlock IS a genuine authoring base (registry/_spec categorizes it as one of the 6 bases, like AppBlock; skill teaches it) — a real ADR-052 gap. Recommend: add `scistudio.blocks.code` as a new §-section (provisional, like AppBlock); `CodeBlock` base + backend-registration surface public/provisional; exact backend symbol set deferred until accucor design lands. | Owner to confirm adding CodeBlock + backend depth. |
| 2026-06-27 | **Confirmed (owner):** CodeBlock added, default **provisional** → recorded as **§7A** (`scistudio.blocks.code`): `CodeBlock` base + `CodeBlockConfig`/`PortFileConfig` public/provisional; backend-registration surface provisional with exact public subset deferred until accucor. | Owner 2026-06-27. §7A numbered to avoid renumbering §8–§18. |
| 2026-06-27 | ADR-052.md edited (owner-authorized; ADR carries `agent_editable: false`, owner-directed in-session): added `scistudio.blocks.code` to `governs.modules`; §3 names `CodeBlock` as an author base; §3.1 + §8 widened the xlsx pandas exception "loader"→"reader/writer" and cite PR #1815. Also removed stray non-English text from spec §7A (docs are English-only). | Owner 2026-06-27. |
| 2026-06-27 | Owner principle: **core should not infer from file extensions** — questions whether `_guess_mime` (extension→MIME) should exist in core at all (2 copies: `blocks/app/bridge.py`, `previewers/data_access.py`). Dispatched guess_mime caller survey (8th agent) to map callers + assess remove/replace (c) vs consolidate (b) vs expose (a). | Owner 2026-06-27. Reframes the §7.2 `_guess_mime` resolution. |
| 2026-06-27 | guess_mime survey (8th agent): extension→MIME is **non-load-bearing** (`Artifact.mime_type` only written to a provenance sidecar — nothing branches on it; dispatch uses extension→format-id) and **copy-pasted 4× in core** (bridge, data_access, load_data `_MIME_GUESS`, plot `_PLOT_MIME`). §7.2/§12 `_guess_mime` → **(c) remove/replace, not public** (applies owner's "core must not infer from extensions"); #1817 replaces callers with `None`/authoritative source; imaging import is a cross-repo deferral. | Owner principle 2026-06-27 + survey. |
| 2026-06-27 | **Resolved (owner):** `_PopenProcessAdapter` → (b) — #1817 makes `FileWatcher` accept a plain `subprocess.Popen`; adapter stays internal (concept removed from the surface); imaging passes the raw Popen (cross-repo). **§7 app fully decided** — facilities public/provisional; both reach-throughs internal; `BlockCancelledByAppError` re-exported to `blocks.app`. | Owner 2026-06-27. |
| 2026-06-27 | Owner: `CodeBlockConfigError` (config.py) → **Public/provisional** (authors catch invalid-config errors; cf. §6.3 capability errors); add to `blocks.code.__all__` (#1817). config.py `MigrationDiagnostic` / `resolve_project_path` / `legacy_migration_diagnostics` → internal. | Owner 2026-06-27. |
| 2026-06-27 | **Owner: publish the entire `blocks/code` non-underscore surface Public/provisional** (un-defers the backend-registration subset; full exchange/interpreters/introspect/provenance/validation/backends surface in). Fixed stray non-English text in §7A (docs English-only). | Owner 2026-06-27. |
| 2026-06-27 | **Correction (owner asked to verify code behavior):** the legacy runner layer is NOT marked deprecated in code and has **0 production importers** (`code_block.py` uses `backends/`); only `tests/blocks/test_runner_registry.py` / `test_runners_subprocess.py` / `test_code_block.py` reference it. It is **dead code**, not "deprecated" — prior row corrected. Recommend **deletion** (+ those tests) in #1817; not public. Owner to pick delete vs formal deprecate. | Owner 2026-06-27. |
| 2026-06-27 | **Owner: delete** the legacy runner layer (`runner_registry.py` + `runners/*`) as dead code in #1817 (+ remove `test_runner_registry.py` / `test_runners_subprocess.py` and the `test_code_block.py` runner import). Not public. **§7A CodeBlock fully decided.** | Owner 2026-06-27. |
| 2026-06-27 | Stale §2.3 branch note corrected: branch is now on `BASE_VERSION = 0.3.1` and current with `origin/main` (0 behind, 7 ahead) after the earlier rebase — the prior "still 0.3.0 / ~10 behind" prose was out of date. | Accurate-record hygiene; historical log rows left intact. |
| 2026-06-27 | Previewer reference survey (spectroscopy + imaging clones): only these two public packages ship a previewer. spectroscopy is the canonical shape (split `__init__`/`providers`; reads via `PreviewDataAccess`; raises `ProviderError`; reuses `sanitize_svg`). imaging is **not** a model (monolithic; own array loader bypassing `PreviewDataAccess`; uses legacy `png_data_uri`) — owner: imaging will be rewritten, so symbols only it touches carry no weight. | Owner 2026-06-27 (imaging's implementation is not a proper reference). |
| 2026-06-27 | §8 previewers decided. (1) Whole subsystem tier = **provisional** (young; cf. §7/§7A). (2) Author surface **regularized** to two canonical roots `scistudio.previewers.models` + `scistudio.previewers.data_access`, plus the single helper `sanitize_svg` to be **relocated** out of core-internal `fallbacks` in #1823; operational classes (registry/router/session/service/build/get/load_project) are Internal despite sitting in `previewers/__init__.__all__` (#1817 reconciles `__all__`). | Owner 2026-06-27. |
| 2026-06-27 | §8 dispositions: `models.py` author types all Public/provisional/0.3.1 (spec/manifest/request/envelope/metadata/resource/error-info/enums incl. `PreviewErrorCode`/provider protocols; `ProviderError` + base `PreviewError`). `PreviewSession` + the 6 runtime-raised error classes → **Internal** (owner #4); drop from `models.__all__` in #1817. | Owner 2026-06-27. |
| 2026-06-27 | §8 `data_access.py`: `PreviewDataAccess` Public/provisional (runtime-injected, author-called, never constructed) with its 10 bounded-read methods + 10 result dataclasses Public/provisional; `png_data_uri` → **Internal** (legacy-compat; sole caller imaging being rewritten — owner #3); `DEFAULT_MAX_*` constants Internal. | Owner 2026-06-27. |
| 2026-06-27 | §8.5 storage access investigated (owner: "why does a previewer need `StorageReference` — imaging hack or legitimate?"). Verdict: **legitimate need, leaky mechanism** — FR-009 requires providers to read without catalog access, and core fallbacks + spectroscopy + imaging all rely on it; but `enrich_preview_query` (`api/runtime/_data.py`) already holds a typed `StorageReference` (`record.ref`) and downgrades it to a JSON dict in `request.query["_storage"]` (because `query` is REST-crossing + persisted), forcing every provider to re-import `StorageReference` and rebuild it. | Owner 2026-06-27. Supersedes the initial "provisional author contract" take after tracing the data flow. |
| 2026-06-27 | **Owner chose option B:** #1823 adds typed `PreviewRequest.storage` / `.record_metadata` fields (the request is in-process, never serialized — it already carries live `PreviewDataAccess`); providers read `request.storage` and stop importing `StorageReference` / touching `_storage`. The `_storage` / `_record_metadata` query keys demote to a **runtime-internal serialization detail** (not an author contract). `StorageReference` stays Public via the `core.types` re-export (§3) and is only passed through by previewer authors — no previewer-driven core.storage burden. **§8 previewers fully decided.** | Owner 2026-06-27. |
| 2026-06-27 | Filed **#1823** (refactor: previewer authoring surface) to track the previewer-specific work: option-B storage closure (typed `request.storage`), `sanitize_svg` relocation to a public helper home, and the imaging previewer rewrite to the spectroscopy shape. Pure `__all__` membership edits stay with the master contract transcription (#1817); the design/relocation/cross-repo items are #1823. Spec §8/§8.5/§12 refs repointed accordingly. | Owner 2026-06-27 ("file an issue to refactor the package previewer system properly"). |
| 2026-06-27 | §9 plot `render(collection)` decided: **provisional**, **no behavior change** (owner: plot is currently stable). Recorded the import-free dual-interpreter (Py + R) contract from the harness verbatim — `collection.types`/`.items` (`open`/`open_one`), `item.type`/`.metadata` (strip-list) /`.open()` native-payload-by-type (Array→ndarray, DataFrame→pandas, Series→Series-or-DataFrame per #1750, Text→str, Artifact→Path, CompositeData→dict), and the return contract (figure / in-working-dir path / list; rejects None/other). Runs in a confined CodeBlock subprocess; implementing classes (`_PlotCollection`/`_PlotItem`/`_PlotItems`) private. `item.open()` native objects logged as a second sanctioned pandas/numpy boundary (§10, distinct from the xlsx data-flow exception). Freeze via a behavior-pinning Py+R contract test (§15). **§9 fully decided.** | Owner 2026-06-27. |
| 2026-06-27 | Filed **#1824** (relocate the plot `render(collection)` contract out of the MCP-tools namespace). Owner reversed the earlier "leave it": the contract + runtime sit under `scistudio.ai.agent.mcp.tools_plot`, but it is a first-class user feature and the REST route `api/routes/plots.py` already imports up into `tools_plot` (run_plot_job / validation / scaffold / relink / targets) — backwards. Behavior-preserving relocation to a first-class home (e.g. `scistudio.plots`); §9 contract unchanged. §9 prose repointed. Scope refined (owner): it is an **8-module engine** (`_harness`/`runtime`/`validation`/`models`/`targets`/`scaffold`/`relink`/`examples`), not a one-file move, and it must **sever the `ai.agent.mcp._context` coupling** (3 modules import `get_context`/`_resolve_project_root`/path helpers) via **dependency injection (approach b)** so nothing under the new home imports `ai.agent.mcp`; `tools.py` stays as a thin MCP wrapper. | Owner 2026-06-27 ("the plot contract living in the MCP tools is outrageous — file a migration issue"; chose approach b). |
