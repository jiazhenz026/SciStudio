# Audit — ADR-052 Public API Contract (no-context review 1)

- **Audit branch:** `audit/1833-no-context-1`
- **Base:** `origin/main` (diff: `git diff origin/main...HEAD`)
- **Reviewer:** independent no-context `audit_reviewer` (SciStudio)
- **Date:** 2026-06-28
- **Governing docs read:** `docs/adr/ADR-052.md`, `docs/specs/adr-052-public-api-surface.md`
- **Context boundary honored:** no PR/issue/checklist/planning/ledger/manager text was read. Verification is code-vs-spec only, from the two governing docs, the source/test code, the generated reference under `docs/user/reference/**`, `mkdocs.yml`, the snapshot `tests/api/public_surface.snapshot.json`, the branch diff, and tool output I ran.

## Recommendation: **PASS**

The implementation matches the ADR-052 per-symbol contract exactly — every canonical root's `__all__` count, the spot-checked signatures, the stability tiers (runtime markers and snapshot-carried tiers for the marker-less symbols), the enforcement tests, and the strict docs build all reconcile against the spec with no public/internal leak. The only finding is a single P3 spec-prose miscount that does **not** affect the delivered surface.

---

## 1. API count — spec-expected `__all__` vs live (Owner Check 1)

Live surface read with `PYTHONPATH=$PWD/src python` importing each root and `sorted(__all__)`; spec column derived independently from the §3–§8 per-symbol tables and "Net `__all__` change" notes.

| Root | Spec-expected count | Live count | Δ | Notes (drops/adds verified) |
|---|---|---|---|---|
| `scistudio.core.types` | 10 | 10 | 0 | DROPS `TypeRegistry`/`TypeSpec` (§3.9); `StorageReference` re-export present (§3.1) |
| `scistudio.core.meta` | 3 | 3 | 0 | exactly `FrameworkMeta`, `with_meta_changes`, `ChannelInfo` (§3.10) |
| `scistudio.blocks.base` | 13 | 13 | 0 | DROPS `Port`/`BlockState`/`BlockResult` + 4 port helpers; ADDS `PackageOtaSource` + 6 interactive re-exports (§4.8/§4 net-change) |
| `scistudio.blocks.process` | 1 | 1 | 0 | `ProcessBlock` only (§5) |
| `scistudio.blocks.io` | 12 | 12 | 0 | DROPS `LoadData`/`SaveData`/`normalize_extension(s)`; 5 capability errors kept (§6) |
| `scistudio.blocks.app` | 7 | 7 | 0 | ADDS bridge/watcher facilities + re-exported `BlockCancelledByAppError` (§7 net-change) |
| `scistudio.blocks.code` | entire non-underscore surface (directive) | 60 | n/a | §7A §enumerated symbols all present; runner layer deleted; no underscore leak (see §6) |
| `scistudio.previewers.models` | 21 | 21 | 0 | DROPS the 7 Internal rows (`PreviewSession` + 6 runtime errors) (§8.1) |
| `scistudio.previewers.data_access` | 11 | 11 | 0 | DROPS `png_data_uri` (method→internal) + `DEFAULT_MAX_*` constants (§8.2) |

Live `__all__` membership equals the snapshot membership for all 9 roots (138 symbols total), and the freeze test `test_public_surface_frozen` diffs live vs snapshot per root. No symbol the spec marks Internal appears in any `__all__`; no symbol the spec marks Public is absent. The demoted/dropped set (`TypeRegistry`, `TypeSpec`, `Port`, `BlockState`, `BlockResult`, the 4 port helpers, `LoadData`, `SaveData`, `normalize_extension(s)`, `PreviewSession`, the 6 runtime preview errors, `SupportsInteraction`, `coerce_prompt`, `serialise/deserialise_storage_ref`, `INTERACTIVE_INTERMEDIATE_KEY`, `AIBlock`, `SubWorkflowBlock`, `RunnerRegistry`) is absent from every root `__all__` and remains importable via its deep path (verified — nothing breaks, ADR-052 §2/§9).

## 2. Signatures (Owner Check 2)

Spot-checked via `inspect.signature`; all match the spec:

- **§10 ergonomic accessors** present: `Array.to_numpy(self)`, `DataFrame.to_pandas/to_numpy(self)`, `Series.to_pandas/to_numpy(self)`.
- **§11 large-data:** `Array.sel(self, **kwargs: int|slice) -> Array`; `DataObject.slice(self, *args) -> Any`; `DataObject.iter_chunks(self, chunk_size: int) -> Iterator[Any]`; `Block.persist_array(self, data_or_iterator, shape, dtype, output_dir=None, chunks=None) -> StorageReference`; `Block.persist_table(self, table, output_dir=None) -> StorageReference`. Matches §11 verbatim.
- **De-underscored reconstruction-hook pair:** `reconstruct_extra_kwargs` / `serialise_extra_metadata` are public on `DataObject`/`Array`/`DataFrame`/`Series`/`Text`/`Artifact`/`CompositeData`; the old `_`-prefixed names are gone (§3.1 opt-A).
- **Removed `metadata` shim (§16 cleanup):** `DataObject.metadata` property is absent; `DataObject(metadata=...)` raises `TypeError: unexpected keyword argument 'metadata'`. Ctor is `(*, framework, meta, user, storage_ref)`.
- **kw-only constructors (§3):** `Array`/`DataFrame`/`Series`/`Text`/`Artifact`/`CompositeData`/`DataObject` all keyword-only; `Text` uses `content=`, `Artifact` uses `file_path=`, `CompositeData` uses `slots=`. `Collection.__init__(items=None, item_type=None)` is positional (matches §3.8).
- **Re-exports:** interactive surface re-exported from `blocks.base`; `BlockCancelledByAppError` re-exported from `blocks.app` (and correctly NOT in `blocks.base.__all__`, per the §4 net-change list); `PackageOtaSource` in `blocks.base.__all__`; `StorageReference` re-exported from `core.types`.

## 3. Tiers (Owner Check 3)

`scistudio.stability.get_stability(obj).tier` read for every public symbol; matches the spec Tier column:

- `core.types`: all `stable`. `core.meta`: all `stable`. `blocks.process`: `stable`. `blocks.io`: bases + errors `stable`. `blocks.base`: `Block`/`BlockConfig`/`InputPort`/`OutputPort`/`ExecutionMode`/`PackageInfo` `stable`; `PackageOtaSource` + interactive surface `provisional`. `blocks.app`, `blocks.code`, `previewers.models`, `previewers.data_access`: all `provisional` (whole-subsystem provisional per §7/§7A/§8).
- **Marker-less symbols (9):** `get_stability` returns `None` (by design) for `INTERACTIVE_RESPONSE_KEY`, `PANEL_API_VERSION`, `CapabilityDirection`, `MetadataFidelityLevel`, `InterpreterFamily`, `PREVIEWER_API_VERSION`, `PreviewProvider`, `PreviewResourceProvider`, `PreviewerSpecList`. Their tier is carried by the snapshot, and the snapshot values match the spec: `CapabilityDirection`/`MetadataFidelityLevel` → `stable` (§6.3); the other 7 → `provisional` (§4.8/§7A/§8.1).
- **Exemption is exactly those 9:** `NON_MARKABLE_PUBLIC_SYMBOLS` in both `tests/api/test_public_surface.py` and `tests/adr052_contract/_spec_data.py` lists precisely these 9 tuples — no more, no fewer — and the exemption only skips the runtime-marker read (snapshot membership + tier still locked).

Observation (not a finding): `StorageReference` carries `stable`. The spec assigns it no dedicated per-symbol tier row (it is "Public via re-export, §3"; §8.5 shows `—`), but `stable` is the consistent reading given its placement in the `core.types` stable data-type surface (ADR-052 §3).

## 4. Tests (Owner Check 4)

`HOME=/private/tmp/clean-home-1833 PYTHONPATH=$PWD/src python -m pytest tests/api tests/adr052_contract --no-cov -p no:randomly -q`
→ **725 passed, 11 skipped in 193s (exit 0).**

The contract is enforced by real, non-hollow suites:
- **Freeze + boundary** (`tests/api/test_public_surface.py`): freeze diff live-vs-snapshot per root; no-internal/undecorated-in-`__all__`; concrete signature assertions.
- **Independent contract** (`tests/adr052_contract/`): a separately hand-transcribed `expected_surface.json` + `_spec_data.py` driving surface-inventory, signatures, tiers/stability-semantics, no-internal-leak, re-exports, ergonomic-accessor round-trips, the accessor data-flow guard, deprecations, and the plot-render contract.
- **Ergonomic accessors:** round-trip tests from the canonical form.
- **Accessor data-flow guard** (`test_accessor_dataflow_guard.py`): static token/AST scan over the real data-flow modules (loaders/savers/`block.py`/`serialization.py`/engine worker+local+checkpoint+scheduler/`previewers/data_access.py`) asserting no un-allow-listed `.to_pandas(`/`.to_numpy(`; the single sanctioned `.xlsx` pandas boundary is pinned as the only exception; a layout-presence test prevents a hollow scan.
- **Stability decorators** (`tests/api/test_stability_decorators.py`) and stability-semantics tests cover the `@stable`/`@provisional`/`@internal` no-op-with-metadata behavior.
- **§9 plot render** (`test_plot_render_contract.py`, both copies): a genuine behavior-pinning test that executes the harness program text `scistudio.plot._harness.PYTHON_HARNESS`, builds envelopes via `scistudio.plot.runtime._input_envelope` over real persisted artifacts, and pins the injected shape (`collection.types`/`.items`/`.open()`/`.open_one()`; `item.type`/`.metadata` strip-list/`.open()` native-payload-by-type) and the return contract (figure→savefig / in-dir path / list / `None`→`ValueError` / other→`TypeError` / escaping→`PermissionError` / missing→`FileNotFoundError`).

The 11 skips are legitimate: the §9 **R-reference** halves are clearly-skipped placeholders carrying a tracked `TODO(#1824)` (the §9 R-half deferral is tracked, not a silent gap), plus matplotlib/optional-dep gating in the broader `tests/api` set. No contract row is left untested or hollowed.

## 5. Generated docs build (Owner Check 5)

- `PYTHONPATH=$PWD/src python -m mkdocs build --strict` → **exit 0** (no missing-ref/strict warnings).
- `scripts/docs/build_reference.py` generates one page per canonical root under `docs/user/reference/**`, filtering to each module's `__all__`, rendering `Stability`/`Since` badges from `get_stability`, excluding `internal`-tier members, and stamping a "GENERATED … Do not hand-edit" header.
- Regenerating with `--generate-only` produced **zero git diff** against the committed reference — generated docs are current and stay generated (AGENTS §3.4). All 9 roots have a page; no internal symbol leaks into the rendered surface.

## 6. Other contract obligations

- **No `@internal` in any `__all__`:** confirmed (tier dump shows no `internal` tier; freeze `test_no_internal_or_undecorated_in_all` passes).
- **Deep-path / underscore imports still work:** verified for `core.types.dataframe.DataFrame`, `…registry.TypeRegistry/TypeSpec`, `blocks.base.ports.Port`, `…state.BlockState`, `…result.BlockResult`, `blocks.io.capabilities.normalize_extension(s)`, `…loaders.load_data.LoadData`, `…savers.save_data.SaveData`, `previewers.fallbacks.sanitize_svg` (back-compat re-export) and `previewers.helpers.sanitize_svg` (public home). `PreviewDataAccess.png_data_uri` remains as an internal method (absent from `__all__`).
- **Runner layer deleted (§7A):** `scistudio.blocks.code.runner_registry` and `…runners` are `ModuleNotFoundError`; the diff removes `runner_registry.py`, `runners/*`, and their tests.
- **Spec deferrals tracked, not silent:** ADR-052 §7 carries `TODO(#1817): multi-version published reference docs`; spec §13.2/§13.3 (package adoption / template) cite `#1826`; §14 cites `#1817`/`#1825`; §9 R-half cites `#1824`. No untracked `TODO`/`placeholder`/`temporary` was introduced in the changed `src/**.py` (scan returned empty after excluding issue/ADR-cited lines).
- **blocks.code surface (note):** §7A is a directive ("publish the entire non-underscore surface"), not an enumerated list, so the exact count (60) is implementation judgment within that directive rather than a spec-enumerable number. I verified all §7A-named symbols are present, no underscore name leaks, the runner layer is gone, and the freeze snapshot locks the membership. Conforms.

## 7. Findings

### P1 (block)
None.

### P2 (should-fix)
None.

### P3 (nit)
- **Spec prose miscount, `previewers.models`.** Spec §8.1 states the module "`__all__` declares 29 symbols", but `origin/main`'s `previewers/models.py __all__` actually has **28** entries (21 Public rows + 7 Internal rows enumerated in the §8.1 table). The delivered surface is correct (28 − 7 = 21 = live), so this is purely an inaccurate description of the *prior* surface in the spec, not an implementation defect. Suggest correcting "29" → "28" in spec §8.1. (Evidence: `git show origin/main:src/scistudio/previewers/models.py` → `__all__` count = 28.)

## 8. Commands run (evidence)

- `pytest tests/api tests/adr052_contract --no-cov -p no:randomly -q` (HOME=clean) → `725 passed, 11 skipped` (exit 0).
- `python -m mkdocs build --strict` → exit 0.
- `python scripts/docs/build_reference.py --generate-only` then `git diff docs/user/reference/` → empty (restored with `git checkout --`).
- Per-root `__all__` + `get_stability` tier/`Since` dumps; `inspect.signature` spot-checks; deep-path import probes; `git diff origin/main...HEAD --stat`.

**Final recommendation: PASS.** The implementation is exactly the ADR-052 contract — no more, no less. The single P3 is a spec-text count typo describing the pre-change surface and has no effect on the delivered public API.
