# scistudio-blocks-fixture

A **fake**, in-repo SciStudio block package used purely as a test fixture.

It mirrors the *structure* of a real domain package (imaging / lcms /
spectroscopy / srs):

- `get_block_package()` / `get_types()` / `get_previewers()` factories
- `types.py` — trivial `Image` / `Mask` / `Label` DataObject subtypes
- `io/` — a loader (`LoadImageFixture`) and a saver (`SaveDataFixture`),
  each declaring `FormatCapability` records
- `previewers/` — a trivial `get_previewers()` factory + a same-origin
  `viewer.js` asset

...but carries **zero** real scientific behaviour. It exists so that core
machinery tests (serialization round-trip, registry / type discovery, IO
capability dispatch, previewer routing) have a plugin stand-in after the
real domain packages are decoupled out of the core repo (issue #1770).

## How it is discovered in tests

This package is **never** globally installed (`pip install` is forbidden by
repo rules). Instead:

1. `tests/conftest.py` prepends
   `tests/fixtures/scistudio-blocks-fixture/src` to `sys.path` so
   `import scistudio_blocks_fixture` works during the test session.
2. Tests that need **entry-point discovery** inject the fixture's entry
   points per-test via `monkeypatch` (pointing `scistudio.blocks` /
   `scistudio.types` / `scistudio.previewers` at `scistudio_blocks_fixture`).

This keeps the default registry baseline clean for tests that assert exact
block/type lists.
