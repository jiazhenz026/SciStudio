"""Skeleton tests for RunDir (ADR-035 §3.2, §3.4)."""

from __future__ import annotations

import pytest

from scieasy.blocks.ai.run_dir import RunDir


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_init_computes_path_correctly(tmp_path: object) -> None:
    """run_dir.path == project_dir/.scieasy/ai-block-runs/<run_id>/."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_init_rejects_run_id_with_separators() -> None:
    """RunDir(...,'foo/bar') should ValueError."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_create_makes_dir_and_signals_subdir() -> None:
    """RunDir.create() creates path/ and path/signals/."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_create_raises_on_collision() -> None:
    """Calling create() twice → FileExistsError."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_write_manifest_basic_shape() -> None:
    """Manifest JSON matches the example in ADR-035 §3.4."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_write_manifest_records_paths_verbatim() -> None:
    """ADR-035 §3.4: paths must NOT be rewritten / symlinked / copied."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_write_manifest_atomic() -> None:
    """tempfile + os.replace — never partial file on disk."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_write_manifest_inmemory_input_triggers_materialization() -> None:
    """Input with no storage_ref → DataObject.write_to_storage() called first."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_write_manifest_default_expected_path() -> None:
    """Output port without expected_path → ./{block_name}_outputs/{port}.{ext}."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_mcp_signal_path_under_signals_dir() -> None:
    """mcp_signal_path() returns path/signals/finish_ai_block.json."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_mark_done_signal_path_under_signals_dir() -> None:
    """mark_done_signal_path() returns path/signals/mark_done.json."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_copy_transcript_basic() -> None:
    """copy_transcript(src) copies src to path/transcript.log."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_copy_transcript_missing_source_logs_warning() -> None:
    """Missing source → log warning, do not raise."""
    raise NotImplementedError("skeleton")


# Smoke test: the module imports and the class exists.
def test_run_dir_class_imports() -> None:
    """Skeleton import smoke test — pass even before implementation."""
    assert RunDir is not None
