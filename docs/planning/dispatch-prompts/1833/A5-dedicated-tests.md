[DISPATCH-TEMPLATE-V1: test_engineer]

## Task Identity

- Repository: SciStudio
- Owner request (verbatim intent, 2026-06-27): write a **brand-new, dedicated, from-scratch test suite** for the ADR-052 public API contract — NOT edits to existing tests. A separate test agent (A4) already covers the in-repo `tests/api/**` set and the existing-test reconciliation; that work is kept. YOU write an independent, self-contained, dedicated contract suite in its OWN directory.
- Task kind: feature
- Persona: test_engineer
- Issue: #1833 (umbrella tracking #1817)
- Protected branch: main
- Agent branch: test/1833-adr-052-dedicated-suite
- Agent worktree: /Users/jiazhenz/scistudio-wt-1833-tests2
- Gate record: manager-owned; do NOT touch.

## Required Rules

Read and follow, FROM YOUR WORKTREE:
- `docs/adr/ADR-052.md`
- `docs/specs/adr-052-public-api-surface.md` — AUTHORITATIVE. You transcribe the EXPECTED contract from it. ALL sections: §3, §3.10, §4 (incl. §4.8), §5, §6 (incl. §6.5), §7, §7A, §8 (incl. §8.1/§8.2/§8.5), §9, §10, §11, §15, §16.
- `AGENTS.md`, `docs/ai-developer/rules.md`, `docs/ai-developer/personas/test-engineer.md`, `docs/ai-developer/specific_rules/test-engineering.md`

## Scope — DEDICATED, DISJOINT

You own ONLY a brand-new directory:
- `tests/adr052_contract/**` (create it; put your ENTIRE suite here, incl. `__init__.py`, a `conftest.py` if needed, and an expected-surface fixture json)

You must NOT:
- modify ANY existing test file (another agent owns those — owner: "his work can be kept; you write a dedicated set");
- touch anything outside `tests/adr052_contract/**`;
- touch `src/**`, `docs/**`, `mkdocs.yml`, `pyproject.toml`;
- read the implementation worktrees, the other test agent's branch, or any `src/` change — derive PURELY from ADR-052 + the spec.

If you need anything outside `tests/adr052_contract/**`, STOP and report.

## Coordination

- The implementation and a separate test agent run IN PARALLEL in worktrees you must NOT look at. Independence is the point.
- Work only in `/Users/jiazhenz/scistudio-wt-1833-tests2` on `test/1833-adr-052-dedicated-suite`.
- MUST NOT `pip install -e .`. Use `PYTHONPATH=$PWD/src`.
- DO NOT commit/push/PR. The manager integrates your worktree.
- `scistudio.stability` (`@stable`/`@provisional`/`@internal`/`get_stability`/`StabilityInfo`) is real on main. The NEW core/blocks/previewers surface is NOT in your worktree, so most of your assertions CANNOT pass here yet — EXPECTED. Write them correct-by-spec; do NOT weaken them to pass against the current (pre-impl) tree.

## SHARED FREEZE CONTRACT (manager-defined; identical across all agents)

- Canonical public roots (public surface = each root's `__all__`):
  1. `scistudio.core.types`  2. `scistudio.core.meta`  3. `scistudio.blocks.base`
  4. `scistudio.blocks.process`  5. `scistudio.blocks.io`  6. `scistudio.blocks.app`
  7. `scistudio.blocks.code`  8. `scistudio.previewers.models`  9. `scistudio.previewers.data_access`
- Every name in a root's `__all__` carries exactly one `@stable(since=...)`/`@provisional(since=...)` matching the spec Tier column; `@internal` is NEVER in `__all__`. Baseline `since="0.3.1"`.
- `get_stability(obj)` returns the `StabilityInfo` (tier/since); it transparently unwraps classmethods/staticmethods/properties (reads off `fget`/`fset`/`fdel`). Use it to read tiers; a public property is decorated on its getter, so `get_stability` finds it via `fget`.

## Work To Do — a comprehensive, dedicated contract suite under `tests/adr052_contract/`

Write independent, well-named tests (suggested file split; you may organize differently within the directory):

1. `test_surface_inventory.py` — per canonical root, assert the live `__all__` exactly equals the spec-derived expected set (count + names), AND each symbol's `get_stability` tier+since match the spec. Drive it from a committed expected fixture you author: `tests/adr052_contract/expected_surface.json` ({root: {symbol: {tier, since}}}), transcribed BY HAND from the spec tables / "Net __all__ change" notes. This is YOUR independent derivation (distinct from the other agent's snapshot).
2. `test_no_internal_leak.py` — assert no symbol marked `@internal` (or undecorated) appears in any root `__all__`; assert the demoted symbols are NOT in their root `__all__`: `TypeRegistry`, `TypeSpec` (core.types); `Port`, `BlockState`, `BlockResult`, the 4 port helpers (blocks.base); `LoadData`, `SaveData`, `normalize_extension`, `normalize_extensions` (blocks.io); `png_data_uri`, `DEFAULT_MAX_*`, the 7 model internals `PreviewSession`/`RoutingAmbiguityError`/`UnknownPreviewerError`/`UnknownTargetError`/`MissingBundleError`/`InvalidSpecError`/`DuplicatePreviewerIdError` (previewers).
3. `test_signatures.py` — assert the signatures/shape of the spec-flagged new/changed members: ergonomic accessors return types (§10); `Array.sel(**axes)`, `DataObject.slice`, `iter_chunks` (§11); `Block.persist_array(...)`, `persist_table(...)` (§11); the de-underscored hook NAMES exist and the `_`-prefixed versions are gone; `DataObject` has NO `metadata` property and the ctor rejects `metadata=`; constructor kw-only payloads per §3 (`Array(axes=...,data=...)`, `DataFrame(data=...)`, `Series(data=...)`, `Text(content=...)`, `Artifact(file_path=...)`, `CompositeData(slots=...)`, `Collection(items, item_type)` positional).
4. `test_ergonomic_accessors.py` — round-trips: `Array.to_numpy()`→ndarray; `DataFrame.to_pandas()`→pandas.DataFrame, `.to_numpy()`→ndarray; `Series.to_pandas()`→pandas.Series, `.to_numpy()`→ndarray; assert they wrap `to_memory()` (same values) and that `Text`/`Artifact`/`CompositeData` expose NO such accessor.
5. `test_reexports.py` — assert the re-exports land on the canonical root: interactive surface (`InteractiveMixin`, `InteractivePrompt`, `PanelManifest`, `load_intermediate`, `PANEL_API_VERSION`, `INTERACTIVE_RESPONSE_KEY`) importable from `scistudio.blocks.base`; `BlockCancelledByAppError` from `scistudio.blocks.app`; `PackageOtaSource` in `scistudio.blocks.base.__all__`; `StorageReference` from `scistudio.core.types`.
6. `test_deprecations.py` — assert `IOBlock.supported_extensions` is marked deprecated (carries the deprecated marker/tier per the repo convention) while still importable.
7. `test_accessor_dataflow_guard.py` — independent static scan asserting `to_pandas`/`to_numpy` do NOT appear in the core data-flow path (loaders, savers, auto-flush, worker serialize/reconstruct, checkpoint, scheduler/engine, previewer bounded reads), with the `.xlsx` reader/writer (#1810/#1815) as the single sanctioned pandas exception.
8. `test_stability_semantics.py` — assert the decorators are runtime no-ops (decorated object identity unchanged; behavior unchanged) and `get_stability` round-trips tier/since across a representative public symbol per root.
9. `test_plot_render_contract.py` — DEFERRED: a clearly-skipped placeholder `pytest.mark.skip(reason="ADR-052 §9 behavior-pinning test pending #1824 plot relocation")` + `TODO(#1824)`. Do NOT write real §9 assertions (relocated home unknown; the manager continues you after #1824 merges).

Keep the suite self-contained in `tests/adr052_contract/` with its own `__init__.py` and fixtures. Use `pytest` idioms; parametrize over the 9 roots where natural.

## Validation (run in your worktree — most will fail without the impl)

- `PYTHONPATH=$PWD/src python -m pytest tests/adr052_contract -q --collect-only` — must at least import/collect cleanly.
- Expect surface/accessor/signature tests to FAIL here (impl not present). Do NOT weaken them. State this in your report.

## TODO And Deferral Rule

`TODO(#1824)`: §9 plot behavior-pinning test (placeholder skip now; filled after #1824 merges).

## Output Required

1. Your independent **expected_surface.json** content as a table per root (the manager cross-checks it against the spec and the other agents' maps).
2. New test file paths under `tests/adr052_contract/`.
3. Which tests are EXPECTED to fail in isolation vs which collect/pass.
4. Any spec ambiguity you interpreted.
5. Confirmation you did NOT modify any existing test or any file outside `tests/adr052_contract/`.

## Stop Conditions

Stop and report if: you are tempted to edit an existing test or read the impl/other-test worktrees; the spec is ambiguous about a symbol's tier/disposition; you need a path outside `tests/adr052_contract/`.
