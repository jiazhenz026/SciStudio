# Audit — ADR-052 Public API Contract (no-context review 3)

- **Issue / umbrella:** #1833 (umbrella #1817)
- **Audit branch:** `audit/1833-no-context-3`
- **Reviewer:** audit_reviewer persona, no-context boundary
- **Date:** 2026-06-28
- **Governing docs read:** `docs/adr/ADR-052.md`, `docs/specs/adr-052-public-api-surface.md`
- **Evidence read:** repo source + tests, `docs/user/reference/**`, `mkdocs.yml`,
  `pyproject.toml`, `tests/api/public_surface.snapshot.json`, `git diff origin/main...HEAD`,
  and tool output (pytest, mkdocs, live introspection). No PR/issue/planning/chat
  context was read.

## Recommendation

**PASS WITH FIXES.**

The *importable* public contract — the heart of ADR-052 — is implemented exactly
as the spec specifies across all nine canonical roots: `__all__` membership,
stability tiers, `Since`, the signatures of the new/changed/removed members, the
re-exports, the demotions, and the freeze snapshot all match the spec with **zero**
discrepancies. The required test suite passes and `mkdocs build --strict` exits 0.

One substantive gap (P2) keeps this from a clean pass: three spec-`Internal`
non-underscore **methods** leak into the generated author-facing reference because
they were not decorated `@internal`, even though the doc generator already excludes
`@internal` members (and does so for `png_data_uri`). This is fixable with the
mechanism already in the change set.

## Owner check verdicts

| # | Check | Verdict |
|---|---|---|
| 1 | API count per root vs spec | PASS — all 9 roots' `__all__` match exactly (table below) |
| 2 | Signatures strictly (accessors §10, large-data §11, hooks, removed shim, kw-only ctors §3, re-exports) | PASS |
| 3 | Tiers strictly + non-markable exemption "exactly those, no more" | PASS — 9/9 None-returning symbols == the exemption set; snapshot tiers == spec |
| 4 | Tests strictly cover the contract | PASS with one gap — doc internal-exclusion for non-underscore methods is **uncovered** (see P2) |
| 5 | Generated docs build, public-only, badges | PASS for build/badges; **FAIL for "public-only"** — internal-method leak (P2) |

## Per-root `__all__`: expected (spec) vs actual (live)

Live read with `HOME=/private/tmp/clean-home-1833 PYTHONPATH=$PWD/src python` on
the audit tree.

| Root | Spec-expected count | Live count | Match |
|---|---|---|---|
| `scistudio.core.types` | 10 (drops `TypeRegistry`/`TypeSpec`, §3.9) | 10 | ✅ |
| `scistudio.core.meta` | 3 (`FrameworkMeta`,`with_meta_changes`,`ChannelInfo`, §3.10) | 3 | ✅ |
| `scistudio.blocks.base` | 13 (keep 6 + add `PackageOtaSource` + 6 re-exported interactive; drop `Port`/`BlockState`/`BlockResult`/4 port helpers, §4.8) | 13 | ✅ |
| `scistudio.blocks.process` | 1 (`ProcessBlock`, §5) | 1 | ✅ |
| `scistudio.blocks.io` | 12 (drops `LoadData`/`SaveData`/`normalize_extension(s)`, §6.5/§6.3) | 12 | ✅ |
| `scistudio.blocks.app` | 7 (`AppBlock` + 5 facilities + re-export `BlockCancelledByAppError`, §7) | 7 | ✅ |
| `scistudio.blocks.code` | §7A "entire non-underscore surface" (provisional) | 61 | ✅ (see P3) |
| `scistudio.previewers.models` | 21 (drops 7 runtime internals, §8.1) | 21 | ✅ |
| `scistudio.previewers.data_access` | 11 (drops `png_data_uri` method + `DEFAULT_MAX_*`, §8.2) | 11 | ✅ |

No `Internal`-present and no `Public`-absent symbols at the module-`__all__` level on
any root. Confirmed absent from `__all__`: `TypeRegistry`, `TypeSpec`, `LoadData`,
`SaveData`, `normalize_extension(s)`, `Port`, `BlockState`, `BlockResult`, the 4 port
helpers, the interactive internals, the 7 previewer-model internals, the 5
`DEFAULT_MAX_*` constants, `png_data_uri`. Deep-path/underscore imports for the
demoted symbols still resolve (e.g. `scistudio.core.types.registry.TypeRegistry`,
`scistudio.blocks.io.loaders.load_data.LoadData`,
`scistudio.blocks.io.capabilities.normalize_extension`) — ADR-052 §2/§9 honored.

### Tiers & non-markable exemption (check #3)

- Live `get_stability(obj)` vs the committed snapshot: **0 tier/since mismatches**
  for all markable symbols. Snapshot tiers independently match the spec per-symbol
  tables (core.types stable; blocks.io stable + the 5 capability errors stable;
  blocks.app/code/previewers provisional; the interactive surface + `PackageOtaSource`
  provisional on blocks.base).
- Exactly **9** `__all__` symbols return `get_stability() is None`, and they are
  exactly the `NON_MARKABLE_PUBLIC_SYMBOLS` exemption set (str constants /
  `Literal`/`Callable` aliases): `INTERACTIVE_RESPONSE_KEY`, `PANEL_API_VERSION`,
  `CapabilityDirection`, `MetadataFidelityLevel`, `InterpreterFamily`,
  `PREVIEWER_API_VERSION`, `PreviewProvider`, `PreviewResourceProvider`,
  `PreviewerSpecList`. "Exactly those, no more" — confirmed. Their snapshot tiers
  match spec.
- No `@internal` and no undecorated symbol in any root's `__all__` (the freeze /
  no-internal-leak tests assert this; independently confirmed).

### Signatures (check #2) — all verified by `inspect.signature`

- Ergonomic accessors present on the right owners: `Array.to_numpy`,
  `DataFrame.to_pandas`/`to_numpy`, `Series.to_pandas`/`to_numpy`; `Text`/`Artifact`/
  `CompositeData` carry none. (§10)
- Large-data: `Array.sel(self, **kwargs: int|slice) -> Array`;
  `DataObject.slice(self, *args) -> Any`; `iter_chunks(self, chunk_size: int)`;
  `Block.persist_array(self, data_or_iterator, shape, dtype, output_dir=None, chunks=None) -> StorageReference`;
  `persist_table(self, table, output_dir=None) -> StorageReference`. (§11)
- Reconstruction hooks de-underscored: `reconstruct_extra_kwargs` /
  `serialise_extra_metadata` present; `_`-prefixed names gone. (§3.1 opt-A)
- `DataObject.metadata` shim removed: no `metadata` property (static lookup absent),
  no `metadata=` ctor kwarg. (§16)
- kw-only ctors: `DataObject`/`Array`/`DataFrame`/`Series`/`Text`/`Artifact`/
  `CompositeData` all keyword-only (no non-self positional); `Text` uses `content=`,
  `Artifact` uses `file_path=`; `Collection(items=None, item_type=None)` positional
  per §3.8. (§3)
- Re-exports resolve and are in the right `__all__`: interactive→`blocks.base`,
  `PackageOtaSource`∈`blocks.base.__all__`, `BlockCancelledByAppError`→`blocks.app`,
  `StorageReference`→`core.types`.

## Findings

### P1 (blocking) — none.

### P2 — Spec-`Internal` non-underscore methods leak into the generated reference

ADR-052 §7: "internal symbols are excluded even if a docstring exists." The doc
generator `scripts/docs/build_reference.py::_internal_member_filters` excludes a
non-underscore class member from the rendered reference **only if it is decorated
`@internal`** (`get_stability(member).tier == "internal"`). Its own docstring cites
`PreviewDataAccess.png_data_uri` as the motivating case, and that method *is*
decorated `@internal`, so it is correctly excluded (0 occurrences in the built
page).

But the spec marks several other non-underscore **methods** `Internal` (➖) that were
left **undecorated** (`get_stability(...) is None`), so the filter does not catch
them and they render in the committed `docs/user/reference/**`:

| Method | Spec disposition | Decorated? | Renders in built docs |
|---|---|---|---|
| `DataObject.get_in_memory_data` | §3.1 Internal | no (tier=None) | yes — `scistudio.core.types.html` |
| `Series/Text/Artifact/CompositeData.get_in_memory_data` | §3.4–§3.7 Internal | no | yes |
| `Array.iter_over` | §3.2 Internal ("keep internal pending imaging rewrite") | no | yes |
| `FrameworkMeta.derive` | §3.10 Internal ("authors do not call") | no | yes |
| `PreviewDataAccess.png_data_uri` | §8.2 Internal | **yes** | no (correctly excluded) |

Evidence: built `build/mkdocs-site/scistudio.core.types.html` contains
`get_in_memory_data` (16×) and `iter_over` (5×); `scistudio.core.meta.html` contains
`derive` (12×). `mkdocs build --strict` still exits 0 (the leak is rendered content,
not a build warning), so the strict build does not catch it.

Impact: the author-facing generated reference advertises methods the contract says
are internal and that authors must not rely on (`to_memory()` is the canonical
reader; the axis-iteration surface is deferred to #1729). This undercuts a core
purpose of ADR-052 (telling authors what may change without warning).

Why uncovered (check #4 gap): no test asserts that non-underscore `Internal` class
members are absent from the generated reference; the freeze snapshot is module-`__all__`
only, so method-level internal dispositions are unenforced.

Fix (uses machinery already present): decorate these methods `@internal` exactly as
`png_data_uri` is — the generator will then filter them — and/or add a contract test
that the rendered reference excludes spec-`Internal` non-underscore members.

### P3 — `blocks.code.__all__` omits backend module-level helper functions

The `blocks.code` surface is published "entire non-underscore surface" per §7A.
Three spec-declared internals are correctly excluded (`MigrationDiagnostic`,
`legacy_migration_diagnostics`, `resolve_project_path`). However ~12 additional
non-underscore module-level **functions** in the backend/registry modules are also
absent from `__all__`: e.g. `escape_matlab_string`, `which_executable`,
`build_matlab_command`, `infer_matlab_family`, `probe_matlab_version`,
`resolve_matlab_executable`, `validate_matlab_family_for_suffix`, `resolve_executable`,
`environment_delta`, `executed_notebook_path`, plus `register` /
`load_codeblock_backend_modules`.

This is defensible: the per-symbol §7A table lists `backends/*` as "backend
**classes**", and these are clearly internal backend helpers, so excluding them is
the narrower, safer reading ("no more"). But it is in tension with the loose "entire
non-underscore surface" phrasing in §7A/decision-log. Recommend the owner confirm
intent — no change needed if "backend classes only" was meant (the implementation
already follows the authoritative table).

## Tooling results

- **Tests** — `HOME=/private/tmp/clean-home-1833 PYTHONPATH=$PWD/src python -m pytest
  tests/api tests/adr052_contract --no-cov -p no:randomly -q` → **exit 0**, no
  failures. Skips are all legitimate: Windows-only native dialogs (3); the §9 **R**
  reference (needs an R interpreter — Python reference pins the shape; TODO cites
  #1824); and the sanctioned `.xlsx` reader/writer exceptions in the accessor
  data-flow guard (6). The freeze, no-internal-leak, signature, ergonomic-accessor
  round-trip, accessor data-flow guard, stability, and §9 plot behavior-pinning
  tests (driving the real `scistudio.plot._harness.PYTHON_HARNESS`) are substantive,
  not hollow. A second independent spec transcription (`tests/adr052_contract/_spec_data.py`
  + `expected_surface.json`) corroborates every demotion / re-export / accessor /
  hook / ctor.
- **Docs** — `mkdocs build --strict` → **exit 0**. Reference pages carry `Stability`
  + `Since` badges; the only internal-name grep hit in `docs/user/reference/**` is the
  intentional `"!^png_data_uri$"` exclusion filter (not a leak). Module-level surface
  is public-only; the method-level leak is the P2 above.
- **Deferrals** — the two `TODO(#1817)` markers added in source (`port_accepts_signature`
  dead code; `_data`/`_arrow_table` bridge retirement) are tracked and cite the
  umbrella issue. The R reference skip cites #1824.

## Bottom line

The contract's load-bearing surface is implemented exactly as specified — module
`__all__`, tiers, `Since`, signatures, re-exports, deep-path preservation, and the
golden snapshot all match the spec with no discrepancies, and the required checks
pass. Resolve the P2 generated-docs internal-method leak (decorate the named methods
`@internal`, as `png_data_uri` already is, and add a test for it) and confirm the P3
`blocks.code` backend-helper scope; then this is a clean pass.
