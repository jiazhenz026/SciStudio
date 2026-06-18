"""Durability regression tests for checkpoint writes (#1515 / BUG-1).

The single checkpoint slot is overwritten on every terminal block event.
Before the atomic-write fix a crash mid-``json.dump`` left a truncated
file that broke "run from here". These tests assert that an interrupted
checkpoint write leaves the previously persisted checkpoint readable.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scistudio.engine import checkpoint as checkpoint_mod
from scistudio.engine.checkpoint import (
    WorkflowCheckpoint,
    load_checkpoint,
    save_checkpoint,
)

_TS = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)


def _make_checkpoint(**overrides: object) -> WorkflowCheckpoint:
    defaults: dict[str, object] = {
        "workflow_id": "wf-durability",
        "timestamp": _TS,
        "block_states": {"A": "DONE", "B": "READY"},
    }
    defaults.update(overrides)
    return WorkflowCheckpoint(**defaults)  # type: ignore[arg-type]


class _BoomError(Exception):
    pass


def test_interrupted_checkpoint_write_keeps_prior_checkpoint_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "cp.json"

    # Write a good first checkpoint.
    first = _make_checkpoint(block_states={"A": "DONE"})
    save_checkpoint(first, path)
    assert load_checkpoint(path).block_states == {"A": "DONE"}

    # Simulate a crash mid-write of the *second* checkpoint by making the
    # JSON serialiser blow up partway through the temp-file write.
    def _boom_dump(*_args: object, **_kwargs: object) -> None:
        raise _BoomError("simulated crash mid json.dump")

    monkeypatch.setattr(checkpoint_mod.json, "dump", _boom_dump)

    second = _make_checkpoint(block_states={"A": "DONE", "B": "DONE"})
    with pytest.raises(_BoomError):
        save_checkpoint(second, path)

    # The prior good checkpoint is still fully readable.
    restored = load_checkpoint(path)
    assert restored.block_states == {"A": "DONE"}

    # No temp siblings were left behind next to the checkpoint slot.
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "cp.json"]
    assert leftovers == []


def test_checkpoint_file_never_truncated_on_overwrite(tmp_path: Path) -> None:
    """A clean overwrite still yields a complete, parseable JSON file."""
    path = tmp_path / "cp.json"
    save_checkpoint(_make_checkpoint(block_states={"A": "DONE"}), path)
    save_checkpoint(_make_checkpoint(block_states={"A": "DONE", "B": "DONE"}), path)

    # The file parses cleanly (never half-written) and reflects the latest write.
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["block_states"] == {"A": "DONE", "B": "DONE"}
