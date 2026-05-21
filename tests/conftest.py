"""Shared test fixtures for the SciStudio test suite."""

import pytest

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
from scistudio.blocks import registry as _registry_module

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


@pytest.fixture()
def tmp_project_dir(tmp_path: pytest.TempPathFactory) -> "Path":  # noqa: F821
    """Create a temporary project directory structure for testing."""
    from pathlib import Path

    project_dir: Path = tmp_path / "test_project"  # type: ignore[operator]
    project_dir.mkdir()
    return project_dir
