[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Land the ADR-052 public API contract; you implement the **core data-type surface** exactly as the owner-signed per-symbol spec records it.
- Task kind: feature
- Persona: implementer
- Issue: #1833 (umbrella tracking #1817)
- Umbrella PR: (manager-owned; do not open PRs)
- Protected branch: main
- Agent branch: feat/1833-adr-052-core
- Agent worktree: /Users/jiazhenz/scistudio-wt-1833-core
- Gate record: .workflow/records/1833-manager-1833-adr-052-public-api.json (manager-owned; do NOT touch)

## Required Rules

Read and follow, FROM YOUR WORKTREE:
- `docs/adr/ADR-052.md` (the policy)
- `docs/specs/adr-052-public-api-surface.md` (THE AUTHORITATIVE per-symbol contract — your checklist). Sections you implement: **§3 (all of §3.1–§3.10), §10 (ergonomic accessors), §11 (the Array/DataObject large-data methods), §16 step 1, §17/§18 decision log rows about core/types and core.meta.**
- `AGENTS.md`, `docs/ai-developer/rules.md`, `docs/ai-developer/personas/implementer.md`

The spec is signed and authoritative. Where the spec and your intuition disagree, the spec wins. Transcribe it literally.

## Scope

You own ONLY:
- `src/scistudio/core/**` (primarily `core/types/**` and `core/meta/**`)

You must NOT touch:
- `tests/**` (a separate single test agent owns ALL tests — owner's hard rule)
- `src/scistudio/blocks/**`, `src/scistudio/previewers/**`
- `mkdocs.yml`, `pyproject.toml`, `docs/**`
- anything under `scistudio.ai.agent.mcp.tools_plot/**`

If you need an out-of-scope path, STOP and report back. Do not edit it.

## Coordination

- You are NOT alone in this codebase. Other agents edit blocks/, previewers/, doc build, and tests IN PARALLEL right now. Stay strictly inside `src/scistudio/core/**`.
- Work only in your worktree `/Users/jiazhenz/scistudio-wt-1833-core` on branch `feat/1833-adr-052-core`.
- MUST NOT `pip install -e .`. Run python with `PYTHONPATH=$PWD/src`.
- **DO NOT commit, push, or open a PR.** The manager commits and integrates your worktree. Just edit files and report changed paths.
- The `scistudio.stability` module (`@stable`/`@provisional`/`@internal`/`get_stability`, `since=`) is ALREADY on main. Import and use it; do not reimplement it.

## SHARED FREEZE CONTRACT (manager-defined; identical across all agents — implement against it)

- Canonical public roots (public surface = each root's `__all__`):
  1. `scistudio.core.types`  2. `scistudio.core.meta`  3. `scistudio.blocks.base`
  4. `scistudio.blocks.process`  5. `scistudio.blocks.io`  6. `scistudio.blocks.app`
  7. `scistudio.blocks.code`  8. `scistudio.previewers.models`  9. `scistudio.previewers.data_access`
  (You own the declarations for roots #1 and #2.)
- Decoration rule: EVERY name in a root's `__all__` carries exactly one `@stable(since=...)` or `@provisional(since=...)` matching the spec Tier column. `@internal` is NEVER in `__all__` (internal symbols are simply excluded from `__all__`; they stay importable via their module path). Baseline `since="0.3.1"` for everything unless a spec row says otherwise (none do for core).
- Method-level decoration: public methods/properties/classmethods named "Public" in the spec tables carry the same decorators with their spec tier. For a classmethod, put `@classmethod` OUTERMOST then `@stable(...)`. For a property, decorate the property object (the stability module unwraps fget/fset/fdel).
- The freeze snapshot + tests are the test agent's job; you only make the live surface match the spec.

## Work To Do (transcribe the spec literally)

1. **`core/types/__init__.py __all__`** (§3, §3.9): KEEP `Array, Artifact, Collection, CompositeData, DataFrame, DataObject, Series, StorageReference, Text, TypeSignature`. **DROP `TypeRegistry`, `TypeSpec`** (owner demoted to Internal, §3.9 / §17 / decision log 2026-06-27 "A confirmed"). They remain importable via `scistudio.core.types.registry`; just remove from `__all__`.
2. **`core/meta/__init__.py __all__`** (§3.10): it already declares exactly `FrameworkMeta, with_meta_changes, ChannelInfo`. Verify and decorate. (`FrameworkMeta.derive` stays Internal.)
3. **Stability decorators on every public symbol** per the §3 tables (and §3.10):
   - Classes `@stable(since="0.3.1")`: `DataObject, TypeSignature, Array, DataFrame, Series, Text, Artifact, CompositeData, Collection, FrameworkMeta, with_meta_changes, ChannelInfo`.
   - Public methods/properties at the tiers the tables give. Note the few non-stable cases: `DataObject.save` → **@provisional**; the reconstruction-hook pair → **@provisional** (see step 5). Everything else in §3 core tables is **@stable**.
   - Decorate the public methods named Public in the tables: `with_meta`, `to_memory`, `slice`, `iter_chunks` (§11), `save`(prov), `matches`/`from_type` (TypeSignature), `Array.sel`(§11)/`ndim`/`__array__`, `CompositeData.get/set/slot_types/slot_names`, `Collection.item_type/length/__iter__/__len__/__getitem__/__class_getitem__/__repr__/storage_refs`, etc. Use the spec tables as the exact member list per class. Do NOT decorate members the spec marks `➖ Internal` (e.g. `get_in_memory_data`, `_validate_*`, `_data`/`_arrow_table`).
4. **Ergonomic accessors — ADD (do not exist today), §10 / §3.1**: `Array.to_numpy() -> ndarray`; `DataFrame.to_pandas() -> pandas.DataFrame`, `DataFrame.to_numpy() -> ndarray`; `Series.to_pandas() -> pandas.Series`, `Series.to_numpy() -> ndarray`. All `@stable(since="0.3.1")`. They WRAP `to_memory()`, are read-only, additive, and MUST NOT be used anywhere in the core data flow. `Text`/`Artifact`/`CompositeData` get NO accessor.
5. **De-underscore the reconstruction-hook pair** (§3.1 option A): rename `_reconstruct_extra_kwargs` → `reconstruct_extra_kwargs` and `_serialise_extra_metadata` → `serialise_extra_metadata` on `DataObject` (base.py) and every override (`array.py`, `dataframe.py`, `series.py`, `text.py`, `artifact.py`). Mark BOTH `@provisional(since="0.3.1")`. Update `serialization.py` (its `hasattr(cls, "_reconstruct_extra_kwargs")` / `cls._reconstruct_extra_kwargs(...)` / `_serialise_extra_metadata` polymorphic call sites) to the new names. Keep the symmetric-pair + super()-chain semantics. `CompositeData` overrides NEITHER (hook exception — leave as-is).
6. **Delete the `DataObject.metadata` deprecation shim** (§3.1, §16): remove the `metadata` property and the legacy `metadata=` constructor kwarg + its DeprecationWarning branch from `base.py`. Grep the WHOLE repo for any remaining `DataObject(...metadata=...)` construction or `.metadata` reads on DataObject instances. Fix the ones inside `src/scistudio/core/**`. If any caller OUTSIDE `core/**` still uses the shim, do NOT edit it — list it in your report for the manager to route. (Most `metadata=` hits in the repo are unrelated params — workflow/data-record/storage-backend metadata; only the DataObject shim is in scope.)
7. **Docstrings**: write/clean a clear docstring on every public symbol (the griffe reference build reads these). Internal symbols need no doc work.
8. Keep `serialization.py`, `_backend_defaults.py`, `registry.py` internal (no public `__all__` additions).
9. Leave `_data`/`_arrow_table` as internal with a `TODO(#1817): retire transient-data bridges once all callers migrate` comment if not already present (do NOT remove them now).

## Validation (run in your worktree; you may RUN tests but must NOT edit them)

- `PYTHONPATH=$PWD/src python -c "import scistudio.core.types, scistudio.core.meta; print(sorted(scistudio.core.types.__all__))"`
- `PYTHONPATH=$PWD/src python -c "from scistudio.core.types import Array, DataFrame, Series; import numpy as np; ..."` — smoke-test the new accessors round-trip from `to_memory()`.
- `PYTHONPATH=$PWD/src python -m pytest tests/core -x -q` (read-only run) to catch regressions from the hook rename / shim deletion. Existing tests that reference the OLD underscore hook names or the removed shim or `TypeRegistry`/`TypeSpec`-in-`__all__` will fail — that is EXPECTED; the test agent updates them from the same spec. **Report which test files reference those so the manager can confirm the test agent covers them. Do NOT edit tests.**

## TODO And Deferral Rule

Deferred work must be tracked with `TODO(#NNN): <reason>`. Known deferrals:
- `TODO(#1817)`: retire `_data`/`_arrow_table` transient bridges once callers migrate (internal; no surface impact).

## Output Required

Before reporting done, provide:
1. **Public surface map** for roots #1 and #2: a table `import_path.symbol → kind → tier → since` for every public symbol AND every decorated public member, exactly as you implemented it. (This is the manager's reconciliation key.)
2. Changed file paths.
3. The accessor round-trip smoke result.
4. The list of EXISTING test files referencing the renamed hooks / removed shim / demoted `TypeRegistry`/`TypeSpec` (for the test agent).
5. Any out-of-`core/` caller of the metadata shim you found (to route).
6. Any blocker or scope issue.

## Stop Conditions

Stop and report if: you need an out-of-scope file; the spec conflicts with itself or with AGENTS.md; the hook rename breaks serialization in a way the spec did not anticipate; you cannot make the surface match the spec.
