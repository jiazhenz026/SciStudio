# Implementation record: #1075

## Files modified

- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/io/load_image.py`
  - Removed module-level legacy constants `_TIFF_EXTS`, `_ZARR_EXTS`, `_SUPPORTED_EXTS` (lines 27-29).
  - Declared `supported_extensions: ClassVar[dict[str, str]] = {".tif": "tiff", ".tiff": "tiff", ".zarr": "zarr"}` on `LoadImage`.
  - Replaced the `ext in _SUPPORTED_EXTS` / `ext in _TIFF_EXTS` checks in `_load_single` with a call to `self._detect_format(path)`. Error message now references `sorted(LoadImage.supported_extensions.keys())`.
  - Added a defensive `raise ValueError("LoadImage: format id ... has no dispatch arm")` for the case where a future ClassVar entry has no matching dispatch — surfaces missing wiring loudly rather than silently mis-routing.
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/io/save_image.py`
  - Removed module-level legacy constants `_TIFF_FORMAT`, `_ZARR_FORMAT`, `_SUPPORTED_FORMATS`, `_EXT_TO_FORMAT` (lines 31-35).
  - Declared `supported_extensions: ClassVar[dict[str, str]]` on `SaveImage`, mirroring `LoadImage.supported_extensions` exactly.
  - Rewrote `_resolve_format(path, explicit, block=None)` to (a) cross-check the explicit `config['format']` string against the ClassVar's set of registered format-identifier values, and (b) route path-based detection through `block._detect_format(path)` when a block is supplied or walk the ClassVar directly otherwise. Same compound-suffix-first, case-insensitive semantics as `IOBlock._detect_format`.
  - Updated `SaveImage._write_single` to compare `fmt == "tiff"` (string literal) rather than referencing the now-deleted `_TIFF_FORMAT` constant.
  - Threaded `block=self` into all three `_resolve_format` call sites inside `SaveImage.save`.
- `packages/scieasy-blocks-imaging/tests/test_load_image.py`
  - Appended `TestSupportedExtensionsClassVar` class with 8 new cases (exact ClassVar value, `_TIFF_EXTS`/`_ZARR_EXTS`/`_SUPPORTED_EXTS` removal assertion, `_detect_format` resolution on known/unknown/case-variant suffixes, error-message inspection, ClassVar-vs-IOBlock-base inheritance, TIFF + Zarr smoke round-trips).
- `packages/scieasy-blocks-imaging/tests/test_save_image.py`
  - Symmetric `TestSupportedExtensionsClassVar` class with 8 new cases including the explicit `SaveImage == LoadImage` mirror assertion, removal of `_TIFF_FORMAT`/`_ZARR_FORMAT`/`_SUPPORTED_FORMATS`/`_EXT_TO_FORMAT`, and the unsupported-extension error path.
- `CHANGELOG.md` — `[Unreleased]` entry (added in follow-up commit).

## Implementation rationale

- **Module-level constants were redundant once the ClassVar exists.** `_TIFF_EXTS` and `_EXT_TO_FORMAT` carried exactly the information that `supported_extensions` now carries declaratively. Removing them per the spec is mechanical; the only call sites were `_load_single` (now calls `_detect_format`) and `_resolve_format` (rewritten to consult the ClassVar). Format identifier strings `"tiff"` / `"zarr"` survive in-line where the dispatch decision is made.
- **`_resolve_format` retains the `explicit: str | None` config-override path** because `SaveImage` accepts `config['format']` as an explicit override. The new implementation cross-checks the explicit value against `set(SaveImage.supported_extensions.values())` (the format-identifier vocabulary) so a misspelled override still fails loudly.
- **LoadImage and SaveImage ClassVars are mirror-identical.** Round-trip discoverability for `BlockRegistry.find_loader`/`find_saver` (#1077). Tested explicitly.
- **`_detect_format` for path-based dispatch was threaded through `_resolve_format(path, fmt_cfg, block=self)`.** The module-level `_resolve_format` accepts an optional `block: SaveImage | None` parameter and falls back to walking `SaveImage.supported_extensions` directly when no block is in hand (matches `IOBlock._detect_format` semantics for callers that don't hold an instance).

## Deviations from the spec

None substantive. One observation:

- The 5 pre-existing test failures in this package (`test_t_img_002_class_has_required_classvars`, `test_t_img_003_class_has_required_classvars`, `test_load_zarr_round_trip_preserves_axes`, `test_save_collection_tiff_round_trip_preserves_data_and_axes`, `test_save_zarr_round_trip`) are unchanged by this PR — they fail on the WAVE-1 base commit too. They check `"path" in SaveImage.config_schema["properties"]` (which now lives on the inherited `IOBlock.config_schema` per ADR-030 MRO merge) and `img._data` (which is now `None` after the auto-flush from #1073). Out of scope here; the issue-#1075 spec list does not include these tests.

## Tests added

All 16 new cases pass under `PYTHONPATH=src:packages/scieasy-blocks-imaging/src python -m pytest packages/scieasy-blocks-imaging/tests/test_load_image.py::TestSupportedExtensionsClassVar packages/scieasy-blocks-imaging/tests/test_save_image.py::TestSupportedExtensionsClassVar --timeout=60 --no-cov`. Lint clean (ruff check + ruff format --check).

## Known TODOs left in code

None for #1075. The cascade's remaining items are tracked on #1076 (LCMS IO blocks) and #1077 (`BlockRegistry.find_loader`/`find_saver`), referenced from the new ClassVar docstrings on both blocks.
