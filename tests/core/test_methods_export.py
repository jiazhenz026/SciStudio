"""Tests for the ADR-038 §3.7 markdown methods export renderer.

The renderer is read-only against :class:`LineageStore`; tests seed the
store with fixture rows and assert on substrings + section structure in
the produced markdown. We deliberately don't full-parse the markdown —
the contract is "human-readable, includes the four user questions" not
"strict markdown AST".
"""

from __future__ import annotations

from typing import Any

import pytest

from scistudio.core.lineage.methods_export import render_methods_markdown
from scistudio.core.lineage.record import (
    BlockExecutionRecord,
    BlockIORow,
    DataObjectRow,
    RunRecord,
)
from scistudio.core.lineage.store import LineageStore


def _seed_run(store: LineageStore, **overrides: Any) -> str:
    """Insert a minimal RunRecord into the store and return its run_id."""
    base = dict(
        run_id="run-fixture-1",
        workflow_id="image_pipeline",
        workflow_yaml_snapshot="id: image_pipeline\nnodes:\n  - id: A\n",
        started_at="2026-05-15T14:30:00Z",
        status="completed",
        environment_snapshot={"python": "3.13.0", "platform": "linux"},
        triggered_by="user",
        finished_at="2026-05-15T14:30:12Z",
        workflow_git_commit="abc123def",
        workflow_dirty=0,
    )
    base.update(overrides)
    store.insert_run(RunRecord(**base))
    return base["run_id"]  # type: ignore[no-any-return]


def _seed_block_execution(
    store: LineageStore,
    *,
    block_execution_id: str,
    run_id: str,
    block_id: str,
    config: dict[str, Any] | None = None,
) -> None:
    be = BlockExecutionRecord(
        block_execution_id=block_execution_id,
        run_id=run_id,
        block_id=block_id,
        block_type="proc",
        block_version="0.1.0",
        block_config_resolved=config or {"threshold": 0.5},
        started_at="2026-05-15T14:30:01Z",
        finished_at="2026-05-15T14:30:05Z",
        duration_ms=4000,
        termination="completed",
    )
    store.insert_block_execution(be)


def _seed_data_object(
    store: LineageStore,
    *,
    object_id: str,
    type_name: str = "DataFrame",
    storage_path: str | None = "/proj/data/x.parquet",
    produced_by_execution: str | None = None,
) -> None:
    row = DataObjectRow(
        object_id=object_id,
        type_name=type_name,
        wire_payload={"backend": "arrow", "path": storage_path or ""},
        created_at="2026-05-15T14:30:05Z",
        storage_path=storage_path,
        produced_by_execution=produced_by_execution,
    )
    store.upsert_data_object(row)


def _seed_block_io(
    store: LineageStore,
    *,
    block_execution_id: str,
    direction: str,
    port_name: str,
    object_id: str,
    position: int = 0,
) -> None:
    store.insert_block_io(
        BlockIORow(
            block_execution_id=block_execution_id,
            direction=direction,
            port_name=port_name,
            object_id=object_id,
            position=position,
        )
    )


@pytest.fixture()
def store() -> LineageStore:
    """In-memory unified lineage store for each test."""
    s = LineageStore(":memory:")
    yield s
    s.close()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_render_returns_markdown_for_known_run(store: LineageStore) -> None:
    """A populated run yields a multi-section markdown body."""
    run_id = _seed_run(store)
    body = render_methods_markdown(store, run_id)
    assert body.startswith("# Methods")
    assert run_id in body
    assert "image_pipeline" in body
    # Status + workflow + git commit are surfaced (Q1).
    assert "completed" in body
    assert "abc123def" in body


def test_render_includes_environment_section(store: LineageStore) -> None:
    """Environment snapshot is rendered as a JSON code-fence."""
    run_id = _seed_run(store)
    body = render_methods_markdown(store, run_id)
    assert "## Environment" in body
    assert "```json" in body
    assert "python" in body and "3.13.0" in body


def test_render_includes_workflow_yaml_section(store: LineageStore) -> None:
    """Workflow YAML literal is surfaced inside a yaml code-fence (Q2)."""
    run_id = _seed_run(store)
    body = render_methods_markdown(store, run_id)
    assert "## Workflow definition" in body
    assert "```yaml" in body
    assert "nodes:" in body


def test_render_includes_block_executions(store: LineageStore) -> None:
    """Each block_executions row becomes a ### subsection with config (Q3+Q4a)."""
    run_id = _seed_run(store)
    _seed_block_execution(
        store,
        block_execution_id="be-1",
        run_id=run_id,
        block_id="load_image",
        config={"path": "in.tif", "channel": 0},
    )
    _seed_block_execution(
        store,
        block_execution_id="be-2",
        run_id=run_id,
        block_id="preprocess",
    )
    body = render_methods_markdown(store, run_id)
    assert "## Blocks" in body
    assert "### `load_image`" in body
    assert "### `preprocess`" in body
    assert "0.1.0" in body  # block_version
    # Config payload visible.
    assert '"channel"' in body or "channel" in body
    assert "in.tif" in body


def test_render_includes_io_tables(store: LineageStore) -> None:
    """Block I/O DataObjects are rendered as a table (Q4b)."""
    run_id = _seed_run(store)
    _seed_block_execution(store, block_execution_id="be-1", run_id=run_id, block_id="loader")
    _seed_data_object(
        store,
        object_id="obj-input-1",
        type_name="Artifact",
        storage_path="/proj/inputs/raw.tif",
    )
    _seed_data_object(
        store,
        object_id="obj-output-1",
        type_name="DataFrame",
        storage_path="/proj/data/x.parquet",
        produced_by_execution="be-1",
    )
    _seed_block_io(
        store,
        block_execution_id="be-1",
        direction="input",
        port_name="image",
        object_id="obj-input-1",
    )
    _seed_block_io(
        store,
        block_execution_id="be-1",
        direction="output",
        port_name="result",
        object_id="obj-output-1",
    )
    body = render_methods_markdown(store, run_id)
    assert "**Inputs:**" in body
    assert "**Outputs:**" in body
    assert "/proj/inputs/raw.tif" in body
    assert "/proj/data/x.parquet" in body
    assert "obj-input-1" in body
    assert "obj-output-1" in body


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_render_unknown_run_returns_not_found_body(store: LineageStore) -> None:
    """Missing run returns a useful body instead of raising — see method docstring."""
    body = render_methods_markdown(store, "no-such-run")
    assert "Run not found" in body
    assert "no-such-run" in body


def test_render_run_with_no_blocks(store: LineageStore) -> None:
    """A run with zero block_executions still renders cleanly."""
    run_id = _seed_run(store)
    body = render_methods_markdown(store, run_id)
    assert "## Blocks" in body
    assert "No blocks executed" in body


def test_render_run_without_workflow_yaml(store: LineageStore) -> None:
    """Empty workflow_yaml_snapshot suppresses the YAML section, not the header."""
    run_id = _seed_run(store, workflow_yaml_snapshot="")
    body = render_methods_markdown(store, run_id)
    assert "# Methods" in body
    assert "```yaml" not in body


def test_render_dirty_commit_marker(store: LineageStore) -> None:
    """``workflow_dirty=1`` surfaces a ``(dirty)`` marker next to the commit."""
    run_id = _seed_run(store, workflow_dirty=1)
    body = render_methods_markdown(store, run_id)
    assert "(dirty)" in body


def test_render_block_without_io_still_renders(store: LineageStore) -> None:
    """A block_execution with no block_io rows skips the I/O tables silently."""
    run_id = _seed_run(store)
    _seed_block_execution(store, block_execution_id="be-x", run_id=run_id, block_id="silent_block")
    body = render_methods_markdown(store, run_id)
    assert "### `silent_block`" in body
    assert "**Inputs:**" not in body
    assert "**Outputs:**" not in body


# ---------------------------------------------------------------------------
# D38-2.5 polish — partial re-run banner + error detail formatting
# ---------------------------------------------------------------------------


def test_render_partial_rerun_banner_when_execute_from_and_parent_set(
    store: LineageStore,
) -> None:
    """ADR-038 §3.6a: partial re-runs surface a banner naming the parent run."""
    # parent_run_id is a FK into runs — seed the parent first.
    _seed_run(store, run_id="run-prior")
    run_id = _seed_run(
        store,
        run_id="run-partial",
        execute_from_block_id="threshold_1",
        parent_run_id="run-prior",
    )
    body = render_methods_markdown(store, run_id)
    # Banner text is recognizable and names both the execute-from block and
    # the parent run so the reader can navigate back to the source recipe.
    assert "Partial re-run" in body
    assert "threshold_1" in body
    assert "run-prior" in body
    assert "ADR-038 §3.6a" in body


def test_render_no_partial_rerun_banner_when_full_run(store: LineageStore) -> None:
    """A full run (no execute_from_block_id) MUST NOT show the partial banner."""
    run_id = _seed_run(store)
    body = render_methods_markdown(store, run_id)
    assert "Partial re-run" not in body


def test_render_partial_rerun_banner_without_parent_run(store: LineageStore) -> None:
    """Codex P2 fix — banner fires when execute_from is set even without parent_run_id.

    The production ``ApiRuntime._build_lineage_recorder`` path records
    ``execute_from_block_id`` but does NOT yet populate ``parent_run_id``;
    without this looser gate, real partial reruns would export methods with no
    explanatory note. The banner degrades gracefully to "prior run's
    checkpoint" wording when no parent is named.
    """
    run_id = _seed_run(
        store,
        run_id="run-partial-noparent",
        execute_from_block_id="threshold_1",
        # parent_run_id intentionally omitted (matches current runtime path).
    )
    body = render_methods_markdown(store, run_id)
    assert "Partial re-run" in body
    assert "threshold_1" in body
    # Degrades gracefully — no parent SHA, references the checkpoint instead.
    assert "prior run" in body or "checkpoint" in body
    assert "ADR-038 §3.6a" in body


def test_render_error_termination_surfaces_detail_block(
    store: LineageStore,
) -> None:
    """Failed blocks emit a fenced ``Error detail:`` section, not just a bullet."""
    run_id = _seed_run(store)
    be = BlockExecutionRecord(
        block_execution_id="be-err",
        run_id=run_id,
        block_id="bad_block",
        block_type="proc",
        block_version="0.1.0",
        block_config_resolved={},
        started_at="2026-05-15T14:30:01Z",
        finished_at="2026-05-15T14:30:02Z",
        duration_ms=1000,
        termination="error",
        termination_detail="ValueError: bead size negative",
    )
    store.insert_block_execution(be)
    body = render_methods_markdown(store, run_id)
    # The detail is in its own fenced section, not appended to the bullet.
    assert "**Error detail:**" in body
    assert "ValueError: bead size negative" in body


def test_render_cancelled_termination_surfaces_detail_block(
    store: LineageStore,
) -> None:
    """Cancelled blocks surface their detail the same way as errors."""
    run_id = _seed_run(store)
    be = BlockExecutionRecord(
        block_execution_id="be-cx",
        run_id=run_id,
        block_id="aborted_block",
        block_type="proc",
        block_version="0.1.0",
        block_config_resolved={},
        started_at="2026-05-15T14:30:01Z",
        finished_at="2026-05-15T14:30:02Z",
        duration_ms=1000,
        termination="cancelled",
        termination_detail="cancelled by user",
    )
    store.insert_block_execution(be)
    body = render_methods_markdown(store, run_id)
    assert "**Cancelled detail:**" in body
    assert "cancelled by user" in body


def test_render_completed_block_no_detail_section_even_if_field_set(
    store: LineageStore,
) -> None:
    """Completed runs don't render a detail section even if the field is set."""
    run_id = _seed_run(store)
    be = BlockExecutionRecord(
        block_execution_id="be-ok",
        run_id=run_id,
        block_id="ok_block",
        block_type="proc",
        block_version="0.1.0",
        block_config_resolved={},
        started_at="2026-05-15T14:30:01Z",
        finished_at="2026-05-15T14:30:02Z",
        duration_ms=1000,
        termination="completed",
        termination_detail="should-not-render",
    )
    store.insert_block_execution(be)
    body = render_methods_markdown(store, run_id)
    assert "should-not-render" not in body
