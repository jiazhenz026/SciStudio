# Audit — ADR-052 Public API Contract (no-context review 2)

- **Date:** 2026-06-28
- **Auditor persona:** `audit_reviewer` (independent, no-context)
- **Branch audited:** `audit/1833-no-context-2` vs `origin/main`
- **Governing docs (authoritative):** `docs/adr/ADR-052.md`,
  `docs/specs/adr-052-public-api-surface.md` (the per-symbol contract)
- **Evidence base:** source/test code, generated `docs/user/reference/**`,
  `mkdocs.yml`, `pyproject.toml`, the committed snapshot
  `tests/api/public_surface.snapshot.json`, and tool output from commands run in
  this worktree. No PR/issue/planning/`.workflow`/chat context was read.

## Recommendation: **PASS**

The implementation transcribes the ADR-052 per-symbol contract **exactly** — the
nine canonical roots' `__all__`, the per-symbol tiers/`Since`, the signatures, the
re-exports, the deletions, and the enforcement tests all match the governing
documents. No symbol is over-exported beyond the contract and no Public-marked
symbol is missing. Tests pass; `mkdocs build --strict` is clean. Findings are
three P3 documentation/convention nits only.

| Severity | Count |
|---|---|
| P1 (blocking) | 0 |
| P2 (should-fix) | 0 |
| P3 (nit / observation) | 3 |

---

## Check 1 — API count (sorted `__all__` vs spec)

Live `sorted(__all__)` (via `PYTHONPATH=$PWD/src python`, `importlib`) for each
root, compared to the spec per-symbol tables and "Net `__all__` change" notes.
**Every root matches exactly.**

| Root | Live count | Spec expectation | Verdict |
|---|---|---|---|
| `scistudio.core.types` | 10 | §3: 10 types; drops `TypeRegistry`/`TypeSpec` (§3.9) | ✅ exact |
| `scistudio.core.meta` | 3 | §3.10: exactly `FrameworkMeta`, `with_meta_changes`, `ChannelInfo` | ✅ exact |
| `scistudio.blocks.base` | 13 | §4 net: keep 6 + add `PackageOtaSource` + 6 interactive re-exports; drop `Port`/`BlockState`/`BlockResult`/4 port helpers | ✅ exact |
| `scistudio.blocks.process` | 1 | §5: `ProcessBlock` only | ✅ exact |
| `scistudio.blocks.io` | 12 | §6 net: keep `IOBlock`/`SimpleLoader`/`SimpleSaver`/`FormatCapability`/`MetadataFidelity`/`CapabilityDirection`/`MetadataFidelityLevel` + 5 capability errors; drop `LoadData`/`SaveData`/`normalize_extension(s)` | ✅ exact |
| `scistudio.blocks.app` | 7 | §7 net: keep `AppBlock` + add `FileExchangeBridge`/`FileWatcher`/`ProcessExitedWithoutOutputError`/`validate_app_command`/`ExternalAppBridge` + re-export `BlockCancelledByAppError` | ✅ exact |
| `scistudio.blocks.code` | 60 | §7A: entire `blocks/code` non-underscore surface; runner layer deleted | ✅ (see P3-A) |
| `scistudio.previewers.models` | 21 | §8.1: 21 Public rows; 7 Internal rows dropped (`PreviewSession` + 6 runtime-raised errors) | ✅ exact |
| `scistudio.previewers.data_access` | 11 | §8.2: `PreviewDataAccess` + 10 result types; `png_data_uri` (method, internal) + 5 `DEFAULT_MAX_*` dropped | ✅ exact |

**Drops verified present-but-internal (deep path still resolves):**
`scistudio.core.types.registry.{TypeRegistry,TypeSpec}`,
`scistudio.blocks.io.loaders.load_data.LoadData`,
`scistudio.blocks.base.ports.Port` all import via deep path but are absent from the
root `__all__`. No `@internal`-marked symbol appears in any of the nine `__all__`
(verified independently via `get_stability(...).tier`).

**Legacy runner layer deletion (spec §7A / §17):** confirmed deleted —
`src/scistudio/blocks/code/runner_registry.py`, `.../runners/*` (5 files), and
`tests/blocks/test_runner_registry.py`, `tests/blocks/test_runners_subprocess.py`
all `D` in `git diff --name-status`.

## Check 2 — Signatures (`inspect.signature`)

All spec-flagged shapes verified:

- **kw-only ctors (§3):** `DataObject(*, framework, meta, user, storage_ref)`;
  `Array`/`DataFrame`/`Series`/`Text`/`Artifact`/`CompositeData` ctors are all
  `KEYWORD_ONLY` (+ `**kwargs`). `Collection(items=None, item_type=None)` is
  positional-or-keyword per §3.8. ✅
- **removed `metadata` shim (§3.1/§16):** no `metadata` property
  (`getattr_static` ABSENT), no `metadata=` ctor kwarg. ✅
- **de-underscored reconstruction hooks (§3.1 opt-A):** `reconstruct_extra_kwargs`
  / `serialise_extra_metadata` present (public) on
  `DataObject`/`Array`/`DataFrame`/`Series`/`Text`/`Artifact`; old
  `_`-prefixed names gone. ✅
- **ergonomic accessors (§10):** `Array.to_numpy`, `DataFrame.to_pandas`/`to_numpy`,
  `Series.to_pandas`/`to_numpy` present; `Text`/`Artifact`/`CompositeData` have
  neither. ✅
- **large-data (§11):** `Array.sel(self, **kwargs: int|slice) -> Array`;
  `DataObject.slice(self, *args) -> Any`; `DataObject.iter_chunks(self, chunk_size: int) -> Iterator`;
  `Block.persist_array(self, data_or_iterator, shape, dtype, output_dir=None, chunks=None) -> StorageReference`;
  `Block.persist_table(self, table, output_dir=None) -> StorageReference`. ✅ (matches §11 verbatim)
- **re-exports (object identity `is`):**
  interactive surface (`InteractiveMixin`/`InteractivePrompt`/`PanelManifest`/`load_intermediate`/`PANEL_API_VERSION`/`INTERACTIVE_RESPONSE_KEY`)
  `blocks.base` is the same object as `blocks.base.interactive`;
  `BlockCancelledByAppError` in `blocks.app` is the same object as
  `blocks.base.exceptions`; `StorageReference` in `core.types` is the same object
  as `core.storage.ref`; `PackageOtaSource` in `blocks.base` is the same object as
  `package_info`; `core.meta` `FrameworkMeta`/`ChannelInfo` are the same objects as
  their defining modules. `PackageOtaSource` is in `blocks.base.__all__`. ✅
- **deep-path/underscore imports still work (ADR §9):** verified for
  `core.types.dataframe`, `blocks.base.ports.Port`, `registry.TypeRegistry/TypeSpec`,
  `io.loaders.load_data.LoadData`. ✅

## Check 3 — Tiers (`scistudio.stability.get_stability(obj).tier`)

Live tier for every `__all__` symbol read via `get_stability` and compared to the
spec Tier column **independently** of the snapshot:

- `core.types`: all `stable` (incl. `StorageReference`). ✅
- `core.meta`: all `stable`. ✅
- `blocks.base`: `Block`/`BlockConfig`/`InputPort`/`OutputPort`/`ExecutionMode`/`PackageInfo`
  `stable`; `PackageOtaSource` + whole interactive surface `provisional`. ✅
- `blocks.process`: `ProcessBlock` `stable`. ✅
- `blocks.io`: all `stable` (incl. the 5 capability errors and the two
  non-markable `Literal` aliases). ✅
- `blocks.app`: all `provisional`. ✅
- `blocks.code`: all `provisional`. ✅
- `previewers.models`: all `provisional`. ✅
- `previewers.data_access`: all `provisional`. ✅

**Snapshot vs live:** the committed `tests/api/public_surface.snapshot.json`
recomputed-diff is **empty** for all nine roots (symbol set + markable tier +
`Since` all match). Baseline `Since = 0.3.1` everywhere.

**Non-markable public symbols (`get_stability -> None` by design):** exactly the
nine the owner named — `INTERACTIVE_RESPONSE_KEY`, `PANEL_API_VERSION` (str
constants); `CapabilityDirection`, `MetadataFidelityLevel`, `InterpreterFamily`,
`PreviewProvider`, `PreviewResourceProvider`, `PreviewerSpecList` (`Literal`/`Callable`/`list`
aliases); `PREVIEWER_API_VERSION` (constant). Their snapshot tiers
(`provisional`×7, `stable`×2 for the io `Literal` aliases) **match the spec**
(§4.8, §6.3, §7A, §8.1). The freeze test's `NON_MARKABLE_PUBLIC_SYMBOLS`
exemption set is **exactly** these nine pairs in both
`tests/api/test_public_surface.py` and the supporting tests — membership is still
frozen for them; only the runtime-marker read is skipped.

**Independent corroboration:** the second, separately-derived spec fixture
`tests/adr052_contract/expected_surface.json` was diffed against the snapshot and
**agrees on all 9 roots, all symbols, and all tiers** — two independent
transcriptions of the spec converge on the same surface.

## Check 4 — Tests

Required test surfaces are present and **substantive** (not hollow):

- **Freeze snapshot + diff** — `tests/api/test_public_surface.py`:
  `test_snapshot_covers_exactly_the_canonical_roots` (snapshot roots == 9 canonical),
  `test_public_surface_frozen` (parametrized per root; recomputes live
  `__all__`+tier+`Since`, fails on added/removed/tier-changed/since-changed/undecorated),
  `test_no_internal_or_undecorated_in_all`.
- **Surface/tier/signature** — `tests/adr052_contract/test_surface_inventory.py`
  (membership + tier/`Since` vs independent fixture; exact mode for 7 roots, subset
  for `blocks.code`/`previewers.models`, but the freeze test pins all 9 exactly),
  `tests/api/test_stability_decorators.py`,
  `tests/adr052_contract/test_signatures.py`, plus inline signature asserts in
  `test_public_surface.py`.
- **Accessor round-trips** — `tests/api/test_ergonomic_accessors.py`: pins return
  types AND data equivalence to `to_memory()` (wrapper, not replacement), persists
  `DataFrame`/`Series` to a real Arrow backend, asserts canonical form unchanged.
- **Accessor data-flow guard (§8)** — `tests/api/test_accessor_dataflow_guard.py`:
  static scan of the named core data-flow modules for `.to_pandas(`/`.to_numpy(`
  with an explicit reasoned allowlist (the `.xlsx` reader/writer + a benign pyarrow
  leaf read) and a layout-coverage test so the scan cannot be hollow.
- **Stability decorators** — `tests/api/test_stability_decorators.py` (applied
  across the live surface) and `tests/stability/test_stability.py` (mechanism:
  no-op identity, metadata attach/read, classmethod/staticmethod/property/setter
  unwrapping, `__all__`).
- **§9 plot behavior-pinning** — `tests/api/test_plot_render_contract.py` /
  `tests/adr052_contract/test_plot_render_contract.py`: executes the real
  `scistudio.plot._harness.PYTHON_HARNESS` program text, builds the envelope via
  `scistudio.plot.runtime._input_envelope` over persisted fixtures, and pins the
  injected shape (`collection.types`/`.items`/`open`/`open_one`; `item.type`/
  `.metadata` strip-list/`.open()` native payloads incl. `CompositeData -> dict`)
  and the full return contract (figure / in-dir path / list / `None -> ValueError`
  / other `-> TypeError` / escaping `-> PermissionError` / missing
  `-> FileNotFoundError`). R reference half is a clearly-skipped, `TODO(#1824)`-tracked
  placeholder.

**Run (clean HOME, per the dispatch command):**

```
HOME=/private/tmp/clean-home-1833 PYTHONPATH=$PWD/src \
  python -m pytest tests/api tests/adr052_contract --no-cov -p no:randomly -q
```

Result: **PASS, exit 0** — all collected tests pass; only expected SKIPs
(Windows-only native-dialog ×3; §9 R reference ×2 — `TODO(#1824)`; `.xlsx`
sanctioned-exception allowlist skips ×7 in the data-flow guard parametrization).
No failures, no errors, no leaked desktop-plugin entry-point interference.

## Check 5 — Generated docs build

```
PYTHONPATH=$PWD/src python -m mkdocs build --strict
```

Result: **exit 0** ("Documentation built in ~1.2s"). The generated reference
under `docs/user/reference/**` (10 files, generated by
`scripts/docs/build_reference.py`) contains **only** the public `__all__` surface
with per-symbol **tier + `Since`** badges (e.g. "Stability: `stable` · Since:
`0.3.1`"), the `0.3.1a0` version stamp, and mkdocstrings `filters: ["!^_", ...]`
that exclude underscore members. The lone internal-symbol grep hit
(`png_data_uri` in `scistudio.previewers.data_access.md`) is a
`filters: ["!^_", "!^png_data_uri$"]` directive that **excludes** the internal
method from the rendered class — correct, not a leak. No documented heading begins
with `_`.

## Cross-cutting checks

- **No `@internal` in any `__all__`:** verified (Check 1/3).
- **Deep-path/underscore imports still work:** verified (Check 2).
- **Deferrals are tracked TODOs:** the only deferral markers in the added `.py`
  diff are the §9 R-reference placeholder, each citing `TODO(#1824)`, and the
  multi-version-docs `TODO(#1817)` in ADR-052 §7. No untracked "later"/"v1"
  deferrals.

---

## Findings (all P3)

**P3-A — `blocks.code`: ~15 non-underscore backend/notebook helper functions are
defined but excluded from `__all__`.**
`scistudio.blocks.code.backends.{matlab,notebook,python,r_quarto,shell}` define
non-underscore module-level helpers — `register` (×5), and matlab helpers
`build_matlab_command`, `environment_delta`, `escape_matlab_string`,
`infer_matlab_family`, `probe_matlab_version`, `resolve_executable`,
`resolve_matlab_executable`, `validate_matlab_family_for_suffix`,
`which_executable`, plus `notebook.executed_notebook_path` — that are neither in
`blocks.code.__all__` nor `_`-prefixed. These are genuine implementation details
(registration hooks, matlab-invocation plumbing) and match the §7A **table**,
which names backend *classes* as the public surface; ADR-052 §2 also makes
`__all__` membership (not the underscore) the authoritative definition of public,
so they are correctly internal. The only deviation is from §7A's looser prose
("publish the entire `blocks/code` non-underscore surface"). *Recommendation:*
underscore-prefix these helpers (or note in §7A that the backend public surface is
the classes, not the module-level helpers) so the "non-underscore == public"
convention reads cleanly. Not a contract violation.
(The three `config.py` non-underscore symbols `MigrationDiagnostic`,
`resolve_project_path`, `legacy_migration_diagnostics` are explicitly marked
Internal in §7A and are correctly excluded — no action.)

**P3-B — Spec-internal count inconsistency for `previewers.models` (doc, not
code).** Spec §8.2/§8.1 prose states `models.__all__` "declares 29 symbols" today
and that #1817 "drops the 7 Internal rows", which would imply 22, but the §8.1
per-symbol table has **21** Public rows and the implementation correctly ships 21.
The implementation matches the authoritative per-symbol table; the "29"/"drops 7"
prose is loose. *Recommendation:* reconcile the §8.1/§8.2 prose count. No code
change.

**P3-C — Non-markable snapshot tiers are membership-frozen but not value-checked
by the freeze test (by design).** For the nine non-markable symbols,
`test_public_surface_frozen` skips the tier/`Since` comparison (live read is
`None`), so a wrong tier *value* in the snapshot for one of them would not fail
CI; only add/remove is caught. This is consistent with ADR-052 §15 ("the snapshot
is the source of truth" for non-markable tiers), and all nine snapshot tiers were
manually verified against the spec here. *Recommendation (optional):* assert the
nine non-markable snapshot tiers against a small spec-derived constant to close the
residual gap. No defect today.

## Conclusion

The change set implements the ADR-052 public API contract exactly as the ADR and
the per-symbol spec specify — no more, no less. The nine canonical roots, tiers,
`Since`, signatures, re-exports, deletions, the freeze/anti-drift tests, and the
generated reference all conform; the suite passes and the strict docs build is
clean. **Recommendation: PASS** (3 P3 documentation/convention nits, none
blocking).
