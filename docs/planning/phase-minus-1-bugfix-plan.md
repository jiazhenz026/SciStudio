# Phase -1 bug-fix sprint plan

> ADR-028 §D8 + adjacent IOBlock / AppBlock fixes — the final wave of P1 bug
> work before the ADR-042/043/044 QA freeze (P-1.2).
>
> Owner: manager. Executors: WAVE-1 / WAVE-2-A / WAVE-2-B / WAVE-3 sub-agents.
> Process: every issue closed under the standard CLAUDE.md 6-gate workflow.
> Source of truth for progress: `docs/planning/phase-minus-1-checklist.md`.

---

## 1. Sprint goal & exit condition

**Goal.** Close 8 outstanding P1 issues (#1073–#1080) that implement ADR-028
§D8 (`supported_extensions` ClassVar + `_detect_format` helper on IOBlock) and
clean up three D8-adjacent AppBlock/engine code paths. After this sprint the
IOBlock subsystem matches the ADR-028 contract end-to-end and the AppBlock
bridge no longer silently downgrades typed ports to `Artifact` / writes
`json.dumps(ndarray)` garbage.

**Exit condition.** All 8 PRs merged into `main` with CI green; no regressions
in the existing subprocess smoke / UI smoke flows; CHANGELOG carries one
compliant entry per merged PR; the repo is ready to enter the ADR-042/043/044
acceptance freeze (P-1.2).

---

## 2. Dependency graph

```
#1073 (IOBlock base ClassVar + helper)
   │
   ├─► #1074 (LoadData / SaveData)
   ├─► #1075 (LoadImage / SaveImage)
   └─► #1076 (LCMS plugin IOBlocks)
            │
            └─► #1077 (BlockRegistry.find_loader / find_saver)
                     │
                     ├─► #1078 (core/materialisation.py helpers)
                     │        │
                     │        └─► #1080 (AppBlock bridge.prepare)
                     └─► #1079 (AppBlock _bin_outputs_by_extension)
```

`#1077` formally requires only #1073 + "at least one per-block declaration"
per its issue body, but in practice we wait for the full Wave-2-B leg
(#1076 → #1077) before opening Wave-3 work so that BlockRegistry queries land
against a non-empty registry of declared extensions.

`#1079` consumes `reconstruct_from_file` from #1078; `#1080` consumes both
`materialise_to_file` and `reconstruct_from_file`. Wave-3 therefore ships
#1078 first, then #1079 and #1080 in parallel within the same agent.

SRS plugin scope check: `packages/scieasy-blocks-srs/` contains **no** IO
blocks (only preprocess / component_analysis / spectral_extraction modules),
so #1076 is LCMS-only despite the issue body mentioning SRS.

---

## 3. Per-issue analysis

### #1073 — IOBlock base ClassVar + `_detect_format` helper

- **Scope.** Add `supported_extensions: ClassVar[dict[str, str]] = {}` and a
  `_detect_format(self, path: Path) -> str | None` instance method (compound-
  then-single suffix lookup, case-insensitive) to the `IOBlock` base class.
  No behavior change for existing subclasses (they don't declare the ClassVar
  yet; that lands in #1074–#1076).
- **Files to modify.**
  - `src/scieasy/blocks/io/io_block.py` (currently 191 lines; `class IOBlock`
    at line 40). Add ClassVar near the existing ClassVars at line 56–67;
    add `_detect_format` method below the existing helpers.
- **Test strategy.**
  - Existing: `tests/blocks/io/test_io_block_abc.py` already covers the
    abstract contract; extend it.
  - New tests (same file, new `class TestDetectFormat`):
    - Compound `.ome.tif` resolves to compound entry when present.
    - Single `.tif` resolves to single entry.
    - Case-insensitive: `.TIF` matches `.tif`.
    - Miss returns `None`.
    - Empty `supported_extensions` (base default) always returns `None`.
- **Branch name.** `fix/issue-1073/ioblock-supported-extensions-classvar`
- **Expected diff size.** ~25 LoC source + ~60 LoC tests.
- **Assigned executor.** WAVE-1.
- **Merge ordering constraint.** Must merge first. Hard blocker for all 7
  downstream issues.

### #1074 — Declare `supported_extensions` on LoadData / SaveData (core)

- **Scope.** Populate the ClassVar from #1073 on the two universal core
  blocks. Wire the entry of `load()` / `save()` to use `self._detect_format`
  for format dispatch. Replace inline `if suffix == ".x":` chain entry points
  with a format-keyed dispatch; the per-format `_load_<fmt>` / `_save_<fmt>`
  methods stay as the implementation backend. Replace the hardcoded
  `"Supported: .npy, .npz, ..."` substring in `ValueError` messages with
  `sorted(self.supported_extensions.keys())`.
- **Files to modify.**
  - `src/scieasy/blocks/io/loaders/load_data.py` (722 lines; `class LoadData`
    near line 51).
  - `src/scieasy/blocks/io/savers/save_data.py` (762 lines; `class SaveData`
    near line 192).
- **Test strategy.**
  - Existing: `tests/blocks/io/test_load_data.py`, `tests/blocks/io/test_save_data.py`
    (both already broadly cover load/save paths; preserve).
  - New (append):
    - Assert `LoadData.supported_extensions` contains expected keys
      (`.npy`, `.npz`, `.zarr`, `.parquet`, `.pq`, `.pkl`, `.pickle`, plus
      text/artifact extensions present in current dispatch).
    - Assert `SaveData.supported_extensions` mirrors the loader set.
    - Assert the `ValueError` raised on unknown extension now mentions
      the keys from the ClassVar (regex-match against the sorted list).
- **Branch name.** `fix/issue-1074/load-save-data-supported-extensions`
- **Expected diff size.** ~80 LoC source + ~50 LoC tests.
- **Assigned executor.** WAVE-2-A.
- **Merge ordering constraint.** AFTER #1073.

### #1075 — Declare `supported_extensions` on LoadImage / SaveImage

- **Scope.** Declare ClassVar on both imaging IOBlocks; delete the module-
  level `_TIFF_EXTS` / `_ZARR_EXTS` / `_SUPPORTED_EXTS` / `_EXT_TO_FORMAT`
  constants; route dispatch through `self._detect_format(path)`.
- **Files to modify.**
  - `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/io/load_image.py`
    (module-level constants at lines 27–29; `class LoadImage` around line 210;
    dispatch site lines 302–306).
  - `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/io/save_image.py`
    (module-level constants at lines 31–35; `class SaveImage` around line 139;
    dispatch lookup lines 78–83).
- **Test strategy.**
  - Existing: `packages/scieasy-blocks-imaging/tests/test_load_image.py`,
    `test_save_image.py` (preserve all current behavior tests).
  - New:
    - Assert `LoadImage.supported_extensions == {".tif": "tiff", ".tiff": "tiff", ".zarr": "zarr"}`.
    - Assert `SaveImage.supported_extensions == LoadImage.supported_extensions`.
    - Verify module-level constants are gone via `assert not hasattr(load_image, "_TIFF_EXTS")` etc.
    - Smoke test: round-trip TIFF and Zarr through the new dispatch path.
- **Branch name.** `fix/issue-1075/load-save-image-supported-extensions`
- **Expected diff size.** ~50 LoC source (mostly deletions) + ~40 LoC tests.
- **Assigned executor.** WAVE-2-A.
- **Merge ordering constraint.** AFTER #1073.

### #1076 — Declare `supported_extensions` on LCMS plugin IOBlocks

- **Scope.** Populate the ClassVar on every IO block in `scieasy-blocks-lcms`;
  delete the private `_detect_format` helper at `load_mzml_files.py:160` in
  favour of the base-class helper; replace inline `if suffix == ".csv":`
  chains and pull `config_schema["format"]["enum"]` from the ClassVar.
  SRS plugin verified empty of IO blocks — no change there.
- **Files to modify.**
  - `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/io/load_mzml_files.py`
    (private `_detect_format` at line 160; consumer at line 126).
  - `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/io/load_peak_table.py`
  - `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/io/save_table.py`
    (`config_schema["format"].enum` duplicates the format set per issue).
  - `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/io/load_mid_table.py`
  - `packages/scieasy-blocks-lcms/src/scieasy_blocks_lcms/io/load_sample_metadata.py`
- **Test strategy.**
  - Existing: `packages/scieasy-blocks-lcms/tests/test_io/test_load_mzml_files.py`,
    `test_load_peak_table.py`, `test_save_table.py`, `test_load_mid_table.py`,
    `test_load_sample_metadata.py` (preserve).
  - New (one assertion per block, added to the matching test file):
    - Per-block `supported_extensions` populated with the right keys.
    - For `SaveTable`: assert `config_schema["format"]["enum"]` derived from
      `cls.supported_extensions` (no hardcoded duplication).
    - For `LoadMzMLFiles`: assert private `_detect_format` was removed
      (module-level `hasattr` check).
- **Branch name.** `fix/issue-1076/lcms-io-supported-extensions`
- **Expected diff size.** ~70 LoC source (mix of additions + deletions) +
  ~70 LoC tests.
- **Assigned executor.** WAVE-2-B.
- **Merge ordering constraint.** AFTER #1073.

### #1077 — `BlockRegistry.find_loader` / `find_saver` / `find_io_blocks_for_type`

- **Scope.** Add three query methods to `BlockRegistry`. Each consults the
  `supported_extensions` ClassVar from #1073 + the port `accepted_types`
  declared on registered IOBlock subclasses; uses the existing
  `TypeSignature.matches` (ADR-027) for type compatibility. Disambiguation:
  prefer the most-specific matching type; on ties, first-registered-wins
  (documented in the docstring).
- **Files to modify.**
  - `src/scieasy/blocks/registry.py` (861 lines; add new methods on the
    `BlockRegistry` class — `grep` confirms zero existing matches for
    `extension` in this file).
- **Test strategy.**
  - Existing: `tests/blocks/test_registry.py` (or equivalent — to be
    confirmed by executor; if missing, add a new `tests/blocks/test_registry_find.py`).
  - New tests:
    - Exact match: `find_loader(Image, ".tif")` returns `LoadImage`.
    - Subtype match: loader producing `Array`; query with `Image` (subclass)
      should NOT match (covariance direction).
    - Multiple candidates: register two loaders with overlapping extensions
      → first-registered-wins per docstring.
    - No match: returns `None`.
    - Case-insensitivity: `.TIFF` matches a loader declaring `.tiff`.
    - `find_io_blocks_for_type(Image, direction="input")` enumerates all
      loaders accepting `Image`.
- **Branch name.** `fix/issue-1077/blockregistry-find-loader-saver`
- **Expected diff size.** ~80 LoC source + ~120 LoC tests.
- **Assigned executor.** WAVE-2-B.
- **Merge ordering constraint.** AFTER #1073 + #1076 (so test fixtures can
  use real IO block declarations from LCMS as well as the imaging plugin
  already on `main`).

### #1078 — `core/materialisation.py` helpers

- **Scope.** Add a new module `src/scieasy/core/materialisation.py` exporting
  `materialise_to_file(obj, dest_dir, extension=None) -> Path` and
  `reconstruct_from_file(path, target_type, extension=None) -> DataObject`.
  Both consult `BlockRegistry.find_saver` / `find_loader` from #1077. If a
  source file is already in the target format on disk and reachable via
  `storage_ref.path`, the materialiser prefers a pass-through link to a
  full re-write — for v1 this means a small `scieasy.utils.fs.mount_pathlike`
  helper (POSIX symlink, Windows junction or hardlink), added in this PR.
  No existing `mount_pathlike` helper or `scieasy.utils.fs` module — both
  are created here. Fallback for `reconstruct_from_file`: if no loader
  matches and `target_type` is `Artifact` (or a subclass), return
  `Artifact(file_path=path, ...)`; otherwise raise `LookupError`.
- **Files to modify / create.**
  - `src/scieasy/core/materialisation.py` (new).
  - `src/scieasy/utils/fs.py` (new — `mount_pathlike`).
  - `src/scieasy/utils/__init__.py` (re-export `mount_pathlike` if the package
    follows that convention; otherwise leave untouched — executor confirms).
- **Test strategy.**
  - New: `tests/core/test_materialisation.py`
    - Round-trip a small DataFrame: materialise → reconstruct returns
      equivalent typed object.
    - Round-trip a small Array (numpy).
    - `reconstruct_from_file` falls back to `Artifact` for an unknown
      type/extension combination when `target_type` is `Artifact`.
    - `reconstruct_from_file` raises `LookupError` when no loader matches
      and `target_type` is concrete (e.g. `Image`).
    - Pass-through path: when source file already matches target extension,
      `mount_pathlike` is invoked (mock + assert call).
  - New: `tests/utils/test_fs.py`
    - POSIX path: `mount_pathlike` creates a symlink.
    - Windows path: creates a junction or hardlink (skip with `@pytest.mark.skipif`
      gate when not on the matching platform).
- **Branch name.** `fix/issue-1078/core-materialisation-helpers`
- **Expected diff size.** ~120 LoC source + ~150 LoC tests.
- **Assigned executor.** WAVE-3.
- **Merge ordering constraint.** AFTER #1077.

### #1079 — AppBlock `_bin_outputs_by_extension`: typed reconstruction

- **Scope.** Rewrite `AppBlock._bin_outputs_by_extension` (currently
  `src/scieasy/blocks/app/app_block.py` lines 182–258 region — the issue body
  cites 240–258 for the downgrade branch) to call
  `reconstruct_from_file(path, target_type=declared, extension=ext)` instead
  of silently downgrading any non-`Artifact` declared port type to `Artifact`.
  Remove the `"declared type ... not constructible from a file path"` warning;
  the Artifact fallback inside `reconstruct_from_file` (when no loader is
  found) is the new — intentional — fallback path.
- **Files to modify.**
  - `src/scieasy/blocks/app/app_block.py`.
- **Test strategy.**
  - Existing: `tests/blocks/app/test_appblock_fiji_integration.py`,
    `test_bridge_argv_override.py` (preserve).
  - New (same dir, e.g. `test_appblock_bin_outputs.py`):
    - FijiBlock-style block with `accepted_types=[Image]` + `extension="tif"`:
      output is a typed `Image` instance, NOT `Artifact`.
    - Legacy: declared `Artifact` port → reconstruction still yields
      `Artifact` (no regression).
    - No loader available + `accepted_types=[Image]`: raises a clear error
      (or falls back to `Artifact` only when port allows it — match the
      semantics chosen in #1078).
- **Branch name.** `fix/issue-1079/appblock-bin-outputs-typed-reconstruction`
- **Expected diff size.** ~40 LoC source (mostly deletions) + ~80 LoC tests.
- **Assigned executor.** WAVE-3.
- **Merge ordering constraint.** AFTER #1078.

### #1080 — AppBlock `bridge.py::prepare()`: type-dispatched materialisation

- **Scope.** Rewrite the DataObject branch of `FileExchangeBridge.prepare()`
  (`src/scieasy/blocks/app/bridge.py:31–74`) so that, instead of
  `json.dumps(obj.to_memory(), default=str)`, it calls
  `materialise_to_file(obj, exchange_dir / "inputs", extension)`. If the
  object's `storage_ref.path` is already in the target format on disk,
  prefer the `mount_pathlike` pass-through introduced in #1078. Collections
  iterate items one file at a time (current pattern). Scalar JSON
  serialisation untouched. Concrete AppBlock subclasses (FijiBlock,
  NapariBlock) keep their `run()` overrides — this PR does not migrate
  them; migration tracked separately.
- **Files to modify.**
  - `src/scieasy/blocks/app/bridge.py` (157 lines; the DataObject branch at
    lines ~31–74 per issue body).
- **Test strategy.**
  - Existing: `tests/blocks/app/test_bridge_argv_override.py` (preserve).
  - New (same dir, e.g. `test_bridge_prepare_materialisation.py`):
    - Minimal `AppBlock` subclass that does NOT override `run()`:
      DataFrame input → real `.csv` (or saver-default format) file appears
      in `exchange_dir/inputs/`, NOT a JSON-stringified blob.
    - Numpy-backed Image input → real image file appears (TIFF or whichever
      the saver defaults to).
    - Collection input → one file per item under `inputs/`.
    - Scalar input (string / int) → still serialised via JSON.
    - Verify `manifest.json` entries record `{type, path, extension, format}`.
- **Branch name.** `fix/issue-1080/appblock-bridge-prepare-materialisation`
- **Expected diff size.** ~60 LoC source + ~120 LoC tests.
- **Assigned executor.** WAVE-3.
- **Merge ordering constraint.** AFTER #1078. Can land in parallel with
  #1079 if WAVE-3 keeps them on separate branches/PRs (preferred).

---

## 4. Wave assignment (the executable plan)

Each wave = ONE executor agent. Each wave issues ONE PR per issue (no
combined PRs — one branch per issue, per CLAUDE.md Appendix C).

| Wave    | Executor   | Issues            | Starts when                     | PR count |
|---------|------------|-------------------|----------------------------------|----------|
| WAVE-1  | WAVE-1     | #1073             | now                              | 1        |
| WAVE-2-A | WAVE-2-A  | #1074, #1075      | #1073 PR merged                  | 2        |
| WAVE-2-B | WAVE-2-B  | #1076, #1077      | #1073 PR merged                  | 2        |
| WAVE-3  | WAVE-3     | #1078, #1079, #1080 | #1076 + #1077 PRs merged       | 3        |

Parallelism:

- WAVE-2-A and WAVE-2-B run concurrently after WAVE-1's PR merges. They
  touch disjoint files (core LoadData/SaveData + imaging plugin vs LCMS
  plugin + registry), so worktree-isolated agents won't collide.
- Within WAVE-3, #1078 lands first; #1079 and #1080 then ship as two
  separate PRs that may build on top of #1078's merged branch — the
  executor opens them serially or in parallel as conflicts allow.

Each executor runs the full CLAUDE.md 6-gate workflow per issue:
`start → create_issue (already exists; record gate with existing #) →
write_change_plan → create_branch → update_docs → update_changelog →
submit_pr`. The "create_issue" gate uses the existing issue numbers
#1073–#1080; executors record gate data referencing those issue URLs.

---

## 5. Risk register

1. **Inline extension logic migration (medium).** `load_data.py` and
   `save_data.py` carry six format-specific branches each. The ClassVar
   declaration is mechanical, but the dispatch refactor (extension →
   format key → `_load_<fmt>` method) must preserve every error message
   and every edge case. WAVE-2-A must keep the per-format helper methods
   intact and only change the entry-point lookup.

2. **Test parity (medium).** Existing tests assert specific error message
   substrings (e.g. `"Supported: .npy, .npz, ..."`). After #1074 the
   substring becomes derived from `sorted(supported_extensions.keys())`,
   so the exact text changes. Tests using `pytest.raises(... match=...)`
   must be updated to match the new derived list. Executor should grep
   for `"Supported:"` in `tests/blocks/io/` before changing message format.

3. **Cross-cutting impact on UI format selectors (low/medium).** The
   frontend port-editor reads `config_schema["format"]["enum"]` to populate
   format dropdowns (per #1076). After the consolidation, any UI smoke
   test that pins a particular enum order may break. WAVE-2-B must
   `git grep "format.*enum"` under `apps/`, `frontend/`, or wherever the
   GUI lives in this repo and confirm parity.

4. **Subprocess execution paths (medium).** Many IOBlock subclasses are
   instantiated and run under the subprocess executor (ADR-040). The
   `_detect_format` helper is a regular instance method on a ClassVar —
   safe to pickle / re-import in subprocess context, but the executor
   must re-run the subprocess smoke suite before declaring the wave done.

5. **`mount_pathlike` Windows semantics (low).** Symlinks on Windows
   require admin or developer mode. WAVE-3 must implement the helper to
   fall back to a hardlink or copy on permission failure, and the
   corresponding test must `@pytest.mark.skipif(platform.system() != "Windows", ...)`
   gate the Windows-specific assertion.

6. **AppBlock `_bin_outputs_by_extension` fallback semantics (medium).**
   The existing code logs a warning when a non-`Artifact` declared port
   has no constructor. After #1079, the warning is removed because the
   fallback is now intentional / declared. But callers that grepped logs
   for that warning string may rely on it. WAVE-3 must search the codebase
   and existing tests for the warning text and update.

7. **PR review timing (medium).** Eight PRs through a Codex review pipe
   over a short window risks reconcile thrash. Manager (not the executors)
   should serialise merges: WAVE-1 → wait for green + Codex reconcile →
   merge → release WAVE-2 → … etc. Per ADR-040 cascade memory: cap each
   PR's Codex reconcile at ONE round.

---

## 6. Definition of done for the sprint

- All 8 issues (#1073, #1074, #1075, #1076, #1077, #1078, #1079, #1080)
  CLOSED via merged PRs on `main`.
- `main` CI green at the close of the last merge.
- No regressions in:
  - subprocess executor smoke (`tests/runtime/test_subprocess_*` or
    equivalent — executor of WAVE-3 confirms the path).
  - UI smoke (live Chrome click-through per the cascade memory: any
    UI-touching change ≥ #1076 / #1077 requires a Chrome smoke test).
- Every merged PR carries a CHANGELOG entry in the standard format
  (`- [#NNNN] description (@agent, YYYY-MM-DD, branch: ..., session: ...)`).
- `docs/planning/phase-minus-1-checklist.md` shows all rows `[x]` with PR
  links appended.
- Manager performs a final post-merge drift sweep:
  `git grep -nE "_TIFF_EXTS|_ZARR_EXTS|_SUPPORTED_EXTS|_EXT_TO_FORMAT"` must
  return zero matches in `packages/` and `src/`; `git grep -n "json.dumps(value, default=str)"`
  in `src/scieasy/blocks/app/bridge.py` must return zero matches.
- Repo declared ready to enter the ADR-042/043/044 acceptance freeze
  (P-1.2).

---

## 7. Planning artifact

This file and its sibling `docs/planning/phase-minus-1-checklist.md` are
authored under branch `plan/phase-minus-1-bugfix-sprint` (off
`feat/issue-1100/adr-042-044-qa-infrastructure` — the manager's tracking
branch). The planning PR opens against the same starting branch; manager
merges into that branch before dispatching WAVE-1.
