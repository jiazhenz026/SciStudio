# SciStudio test suite

## Running the suite locally

Run the tests in a dedicated environment that has **core only** installed
(editable) plus the `dev` extras — the same shape CI uses. Do **not** run them
from a shared base environment, and do **not** `pip install -e .` into a shared
environment (see `AGENTS.md`).

The suite has a small set of PTY / subprocess / thread tests marked `serial`
that must run outside `pytest-xdist`. Use the two-phase runner, which mirrors
the two `pytest` invocations CI runs (see `.github/workflows/ci.yml`):

```bash
python -m scistudio.qa.testing.run_python_tests
```

It runs the parallel bulk (`-n auto -m "not serial"`) first, then the `serial`
tests in-process (`-n 0 -m serial`). Forwarded args (e.g. `--no-cov`,
`--timeout=90`) apply to both phases.

## Environment-pollution isolation

A clean, core-only install exposes **no** domain blocks: core registers its
first-party palette in `BlockRegistry._scan_builtins`, and the
`scistudio.blocks` entry-point group is reserved for third-party plugins
(`_scan_tier2`, ADR-025). CI runs in exactly that clean state, so it is green.

A developer's machine is rarely that clean. Two channels leak domain blocks into
the registry and make discovery/registry tests fail locally even though CI
passes:

1. **Entry points** — a stale editable `*.dist-info/entry_points.txt` frozen
   from an earlier build can still declare retired/relocated built-ins under the
   `scistudio.blocks` group, and locally-installed domain packages
   (imaging / lcms / spectroscopy / srs) contribute their own entries.
2. **Desktop package discovery** — Tier 3 source-package discovery
   (`candidate_package_dirs`) scans the platform user-data plugins directory,
   where a real desktop install leaves domain packages behind.

`tests/conftest.py` neutralizes **both** channels for the whole test session so
the suite behaves like a clean core-only install regardless of what is installed
on the machine:

- the `scistudio.blocks` entry-point group is filtered out of
  `importlib.metadata.entry_points`, and
- the desktop user-data directory is redirected to a clean per-session temp root.

Tests that exercise Tier 2 / Tier 3 discovery inject their own entry points or
package dirs (via `unittest.mock.patch` / `monkeypatch`), which transparently
override the session baseline and are restored afterwards. The isolation is
locked in by `tests/blocks/test_entry_point_isolation.py`.
