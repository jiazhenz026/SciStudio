"""Shared test fixtures for the SciStudio test suite."""

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixture block-package discovery (issue #1770)
# ---------------------------------------------------------------------------
#
# ``tests/fixtures/scistudio-blocks-fixture`` is a fake, in-repo SciStudio
# block package that mirrors the structure of a real domain package
# (imaging / lcms / spectroscopy / srs) with zero real behaviour. It stands
# in for the now-decoupled domain packages so core machinery tests have a
# plugin to exercise.
#
# It is NEVER globally installed (``pip install`` is forbidden). Prepending
# its ``src`` to ``sys.path`` here makes ``import scistudio_blocks_fixture``
# work during the test session. Its entry points are NOT activated globally;
# tests that need entry-point discovery inject them per-test via
# ``monkeypatch`` so the default registry baseline stays clean.
_FIXTURE_PKG_SRC = Path(__file__).resolve().parent / "fixtures" / "scistudio-blocks-fixture" / "src"
if _FIXTURE_PKG_SRC.is_dir():
    sys.path.insert(0, str(_FIXTURE_PKG_SRC))

# ---------------------------------------------------------------------------
# Env-pollution isolation: neutralize ambient ``scistudio.blocks`` entry points
# (issue #1933)
# ---------------------------------------------------------------------------
#
# Core registers its first-party palette in ``_scan_builtins``; the
# ``scistudio.blocks`` entry-point group is reserved for *third-party* plugin
# packages (``BlockRegistry._scan_tier2`` / ADR-025). A clean, core-only
# install — CI and the packaged desktop bundle — therefore exposes ZERO
# ``scistudio.blocks`` entry points.
#
# A developer's editable checkout is not clean:
#   * a stale ``*.dist-info/entry_points.txt`` frozen from an earlier build can
#     still declare now-retired/relocated built-ins (``slice_collection``,
#     ``split_collection``, ...) under this group, and
#   * locally-installed domain packages (imaging / lcms / spectroscopy / srs)
#     leak their own ``scistudio.blocks`` entry points into the interpreter.
# Both pollute Tier 2 discovery and make registry tests fail locally even though
# CI is green (#1770, #1933; the recurring "gate tests leak user plugins" pain).
#
# We make the whole test session behave like a clean core-only install by
# filtering the ``scistudio.blocks`` group out of
# ``importlib.metadata.entry_points`` for the session. Tests that exercise Tier
# 2 discovery inject their own entry points by patching
# ``importlib.metadata.entry_points`` (see tests/blocks/test_registry.py);
# ``unittest.mock.patch`` restores this wrapper afterwards, so per-test
# injection is unaffected. ``_scan_tier2`` reads the group through this same
# module attribute, so the isolation reaches it without touching core code.
import importlib.metadata as _im  # noqa: E402

_ISOLATED_EP_GROUP = "scistudio.blocks"
_real_entry_points = _im.entry_points
_EntryPoints = getattr(_im, "EntryPoints", None)


def _entry_points_without_leaked_blocks(*args: object, **kwargs: object) -> object:
    """``importlib.metadata.entry_points`` with the ``scistudio.blocks`` group removed.

    Handles every return shape across supported Pythons: an ``EntryPoints``
    tuple (``group=`` calls, and 3.12+ no-arg calls) is filtered element-wise;
    the deprecated ``SelectableGroups`` mapping (3.10/3.11 no-arg) has the group
    key dropped and is rebuilt as the same type so ``.select(...)`` keeps
    working.
    """
    result = _real_entry_points(*args, **kwargs)  # type: ignore[arg-type]
    if _EntryPoints is not None and isinstance(result, _EntryPoints):
        return _EntryPoints(ep for ep in result if ep.group != _ISOLATED_EP_GROUP)
    try:
        pruned = {group: eps for group, eps in result.items() if group != _ISOLATED_EP_GROUP}
    except AttributeError:
        return result
    try:
        return type(result)(pruned)
    except Exception:  # pragma: no cover - defensive: unknown container shape
        return pruned


_im.entry_points = _entry_points_without_leaked_blocks  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Phase 11 / T-TRK-003 + T-TRK-004 — test-only block registration
# ---------------------------------------------------------------------------
#
# Two test-only fixtures get patched into the registry at collection time:
#
# 1. ``NoopBlock`` (from T-TRK-003) — relocated from
#    ``src/scistudio/blocks/process/builtins/transform.py`` to
#    ``tests/fixtures/noop_block.py``. Aliased to ``"process_block"``.
#
# 2. ``NoopIOBlock`` (from T-TRK-004) — concrete ``IOBlock`` subclass,
#    needed because ADR-028 §D1 makes core ``IOBlock`` abstract and
#    ``LoadData`` / ``SaveData`` only land in T-TRK-007 / T-TRK-008.
#    Aliased to ``"io_block"`` so that ~6 existing test workflows that
#    declare ``block_type="io_block"`` continue to instantiate.
#
# Both are TEST-ONLY shims. Production registries created outside the
# pytest session do not see them. Per master plan §1 user override on
# decision 1 (doc-external changes permitted when scoped to the feature
# being tested) and the precedent established by T-TRK-003.
from scistudio.blocks import registry as _registry_module  # noqa: E402  (after sys.path setup above)

_original_scan_builtins = _registry_module.BlockRegistry._scan_builtins


def _patched_scan_builtins(self: "_registry_module.BlockRegistry") -> None:
    _original_scan_builtins(self)

    from tests.fixtures.noop_block import NoopBlock
    from tests.fixtures.noop_io_block import NoopIOBlock

    noop_spec = _registry_module._spec_from_class(NoopBlock, source="builtin")
    self._register_spec(noop_spec)
    # Legacy alias: tests still reference block_type="process_block".
    self._aliases["process_block"] = noop_spec.name

    noop_io_spec = _registry_module._spec_from_class(NoopIOBlock, source="builtin")
    self._register_spec(noop_io_spec)
    # Legacy alias: tests still reference block_type="io_block". The
    # production ``IOBlock`` is abstract post-T-TRK-004 and is not
    # instantiable; test workflows must resolve ``io_block`` to the
    # concrete ``NoopIOBlock`` to actually run.
    self._aliases["io_block"] = noop_io_spec.name


_registry_module.BlockRegistry._scan_builtins = _patched_scan_builtins  # type: ignore[method-assign]


@pytest.fixture(scope="session", autouse=True)
def _isolate_desktop_user_data_dirs(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Redirect desktop user-data dirs to a clean temp root for the session (#1933).

    Tier 3 source-package discovery (``candidate_package_dirs`` /
    ``_scan_package_src_dirs``) scans the platform user-data plugins directory
    for installed domain packages. A developer's machine has real packages there
    (imaging / lcms / spectroscopy) that leak into the registry and fail
    domain-prefix / previewer tests locally, even though CI — with a clean user
    profile — discovers nothing. Pointing the platform dir at an empty session
    temp root reproduces CI's clean state.

    This is the second env-pollution channel alongside the ``scistudio.blocks``
    entry-point isolation above. Tests that exercise desktop discovery override
    this baseline by patching ``_platformdirs_dir`` themselves (see
    tests/blocks/test_desktop_package_discovery.py); ``monkeypatch`` restores
    this session baseline afterwards.
    """
    from scistudio.desktop import paths as _desktop_paths

    root = tmp_path_factory.mktemp("scistudio-user-data")
    original = _desktop_paths._platformdirs_dir
    _desktop_paths._platformdirs_dir = lambda kind: root / kind  # type: ignore[assignment]
    try:
        yield
    finally:
        _desktop_paths._platformdirs_dir = original  # type: ignore[assignment]


@pytest.fixture()
def tmp_project_dir(tmp_path: pytest.TempPathFactory) -> "Path":
    """Create a temporary project directory structure for testing."""
    from pathlib import Path

    project_dir: Path = tmp_path / "test_project"  # type: ignore[operator]
    project_dir.mkdir()
    return project_dir
