[DISPATCH-TEMPLATE-V1: test_engineer]

## Task Identity

- Repository: SciStudio
- Owner request: Land the ADR-052 public API contract. Owner HARD RULE: **ALL test work in the repo is done by you, the single test agent**, started in parallel with the implementation so neither pollutes the other's context. You derive the EXPECTED public surface from the spec ALONE; the implementation lives in worktrees you cannot see. The mismatch (if any) between your spec-derived expectation and the live implementation is the whole point — it surfaces at integration.
- Task kind: feature
- Persona: test_engineer
- Issue: #1833 (umbrella tracking #1817)
- Protected branch: main
- Agent branch: test/1833-adr-052-tests
- Agent worktree: /Users/jiazhenz/scistudio-wt-1833-tests
- Gate record: manager-owned; do NOT touch.

## Required Rules

Read and follow, FROM YOUR WORKTREE:
- `docs/adr/ADR-052.md`
- `docs/specs/adr-052-public-api-surface.md` — AUTHORITATIVE. You transcribe the EXPECTED surface from it. Key sections: **§3, §3.10, §4 (incl. §4.8 net change), §5, §6 (incl. §6.5 net change), §7 (incl. net change), §7A, §8 (incl. §8.1/§8.2 drops), §9, §10, §11, §15 (enforcement/freeze design), §16.**
- `AGENTS.md`, `docs/ai-developer/rules.md`, `docs/ai-developer/personas/test-engineer.md`, `docs/ai-developer/specific_rules/test-engineering.md`

## Scope

You own ONLY:
- `tests/**` (EVERY test file — owner's hard rule that one agent owns all tests)

You must NOT touch:
- `src/**` (the implementation — DO NOT read the impl agents' worktrees; derive purely from the spec)
- `docs/**`, `mkdocs.yml`, `pyproject.toml`
- `scistudio.ai.agent.mcp.tools_plot/**`

If you need an out-of-scope path, STOP and report.

## Coordination

- The implementation is being written IN PARALLEL in worktrees you cannot and must not see. Do NOT try to read `src/` changes from other branches/worktrees. Derive the expected surface from ADR-052 + the spec ONLY.
- Work only in worktree `/Users/jiazhenz/scistudio-wt-1833-tests` on `test/1833-adr-052-tests`.
- MUST NOT `pip install -e .`. Use `PYTHONPATH=$PWD/src`.
- **DO NOT commit/push/PR.** The manager integrates your worktree.
- `scistudio.stability` is on main (real). The NEW core/blocks/previewers surface is NOT in your worktree, so the surface/accessor/freeze tests CANNOT pass here yet — that is EXPECTED. Write them correct-by-spec; the manager validates them against the real implementation at integration.

## SHARED FREEZE CONTRACT (manager-defined; identical across all agents — your tests enforce it)

- Canonical public roots (public surface = each root's `__all__`):
  1. `scistudio.core.types`  2. `scistudio.core.meta`  3. `scistudio.blocks.base`
  4. `scistudio.blocks.process`  5. `scistudio.blocks.io`  6. `scistudio.blocks.app`
  7. `scistudio.blocks.code`  8. `scistudio.previewers.models`  9. `scistudio.previewers.data_access`
- Decoration rule: EVERY name in a root's `__all__` carries exactly one `@stable(since=...)`/`@provisional(since=...)` matching the spec Tier column. `@internal` is NEVER in `__all__`. Baseline `since="0.3.1"`.
- **Freeze snapshot schema** (`tests/api/public_surface.snapshot.json`): JSON keyed by canonical root → object keyed by symbol name → `{ "tier": "stable|provisional", "since": "0.3.1" }`. Only top-level `__all__` symbols (the count/names/tiers lock). Build it BY HAND from the spec tables / "Net __all__ change" notes (this is your independent spec derivation).
- **Freeze test** recomputes the live surface (import each root, read `sorted(__all__)`, read `get_stability(obj)` → tier/since) and asserts it equals the committed snapshot, with a clear `+added / -removed / tier-changed / since-changed` diff message on failure.

## Work To Do

1. **`tests/api/public_surface.snapshot.json`** — the spec-derived expected surface for all 9 roots. Transcribe each root's expected `__all__` from the spec:
   - core.types (§3/§3.9: keep list **minus** `TypeRegistry`/`TypeSpec`), core.meta (§3.10: `FrameworkMeta, with_meta_changes, ChannelInfo`), blocks.base (§4.8 net change), blocks.process (§5: `ProcessBlock`), blocks.io (§6.5 net change), blocks.app (§7 net change), blocks.code (§7A surface), previewers.models (§8.1: 29 − 7 internal), previewers.data_access (§8.2 keep list). Each symbol's tier from its table; `since="0.3.1"`.
2. **`tests/api/test_public_surface.py`** — (a) the freeze test (live vs snapshot, per the schema above); (b) assert NO `@internal`/undecorated symbol appears in any root `__all__`; (c) **signature assertions** for the spec-flagged new/changed members (this is the "signatures strictly consistent" layer): the ergonomic accessors return types, `Array.sel(**axes)`, `DataObject.slice`, `iter_chunks`, `Block.persist_array`/`persist_table` signatures, the de-underscored hook NAMES (`reconstruct_extra_kwargs`/`serialise_extra_metadata` exist, underscore versions gone), `DataObject` has NO `metadata` property / no `metadata=` kwarg, `TypeRegistry`/`TypeSpec` NOT in `core.types.__all__`, `LoadData`/`SaveData`/`normalize_extension(s)` NOT in `io.__all__`, the interactive surface re-exported from `blocks.base`, `BlockCancelledByAppError` reachable from `blocks.app`, `PackageOtaSource` in `blocks.base.__all__`.
3. **`tests/api/test_stability_decorators.py`** — verify the decorators are runtime no-ops + attach correct `StabilityInfo` (tier/since) and that `get_stability` reads them back across representative public symbols of each root. CHECK the existing `tests/stability/test_stability.py` first and do NOT duplicate the pure-mechanism unit tests — this file is the API-surface-level usage check (every `__all__` symbol is decorated with a valid tier/since).
4. **`tests/api/test_ergonomic_accessors.py`** — round-trip tests (§10): `Array.to_numpy()` → ndarray; `DataFrame.to_pandas()` → pandas.DataFrame & `to_numpy()` → ndarray; `Series.to_pandas()` → pandas.Series & `to_numpy()` → ndarray. Assert they WRAP `to_memory()` (same data) and are read-only/additive. Assert `Text`/`Artifact`/`CompositeData` have NO such accessor.
5. **Ergonomic-accessor data-flow guard** (ADR-052 §8, spec §10) — a test (e.g. `tests/api/test_accessor_dataflow_guard.py`) asserting the accessors (`to_pandas`/`to_numpy`) do NOT appear in the core data-flow path (loaders, savers, auto-flush, worker serialization/reconstruction, checkpoint, scheduler/engine, previewer bounded reads), with the `.xlsx` reader/writer (#1810/#1815) recorded as the single sanctioned pandas-using exception. A static scan (grep/AST over the listed modules) is acceptable.
6. **Update existing tests that the new surface changes** (derive each from the spec — the implementation makes these real):
   - rename old `_reconstruct_extra_kwargs`/`_serialise_extra_metadata` references → `reconstruct_extra_kwargs`/`serialise_extra_metadata`;
   - remove uses of the deleted `DataObject(metadata=...)` shim / `.metadata` property → use the three-slot meta API;
   - stop importing `TypeRegistry`/`TypeSpec`/`LoadData`/`SaveData`/`normalize_extension(s)`/port helpers/`png_data_uri`/`DEFAULT_MAX_*`/the 7 previewer model internals/`_guess_mime` as PUBLIC (use the internal module path if a test genuinely needs the internal, or drop the assertion);
   - reconcile `tests/contracts/test_runtime_import_contract.py` (it frames a "TypeRegistry public-API contract") with the now-internal disposition (§3.9 caveat);
   - **DELETE** `tests/blocks/test_runner_registry.py` and `tests/blocks/test_runners_subprocess.py` (dead legacy runner layer, §7A) and remove the runner import from `tests/blocks/test_code_block.py`;
   - adjust any custom-block-template test (`tests/api/test_blocks_template*.py`) only as needed to match the contract-API template (canonical roots) — keep them green against the new template.
7. **§9 plot `render(collection)` behavior-pinning test — DEFER.** The plot contract is being relocated by the owner under **#1824** (in flight). Add a clearly-marked placeholder: a skipped/xfail test in `tests/api/test_plot_render_contract.py` with `pytest.mark.skip(reason="ADR-052 §9 behavior-pinning test pending #1824 plot relocation")` and a `TODO(#1824)` comment. Do NOT write the real assertions yet (the relocated home is unknown). The manager will continue YOU (same test agent) to fill it in after #1824 merges.

## Validation (run in your worktree — most new tests will NOT pass here)

- `PYTHONPATH=$PWD/src python -m pytest tests/api/test_stability_decorators.py -q` may partially run (stability module is real).
- The freeze/public-surface/accessor tests will FAIL in your worktree because the new implementation is not here. That is EXPECTED. Make them correct-by-spec; do NOT weaken them to pass against the current (pre-impl) tree. State this clearly in your report.
- Run a syntax/import check: `PYTHONPATH=$PWD/src python -m pytest tests/api -q --collect-only` to ensure your test files at least import/collect.

## TODO And Deferral Rule

`TODO(#1824)`: §9 plot behavior-pinning test (placeholder skip now; filled after #1824 merges).

## Output Required

1. Your **spec-derived expected surface** (the snapshot content) as a table per root — the manager diffs this against the implementation agents' maps and the spec.
2. New/changed/deleted test file paths.
3. Which existing tests you updated for the changed surface and why (cite the spec row).
4. Confirmation the §9 plot test is a tracked skip citing #1824.
5. A clear statement of which new tests are EXPECTED to fail in isolation (no impl present) vs which you ran green.
6. Any ambiguity in the spec you had to interpret (so the manager/audit can confirm).

## Stop Conditions

Stop and report if: you are tempted to read the implementation worktrees (you must not); the spec is ambiguous about a symbol's tier/disposition; you cannot express a contract as a test; you need an out-of-scope (non-`tests/`) file.
