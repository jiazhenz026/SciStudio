"""Durability regression tests for workflow YAML writes (#1543 / BUG-8).

Concurrent readers (canvas + agent routes) and the FS watcher read the
workflow YAML while it is being written. A direct ``Path.write_text``
allowed a reader to observe truncated YAML and let two writers race
last-write-wins. ``save_yaml`` now writes atomically; these tests assert
an interrupted save leaves the prior YAML fully readable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scistudio.workflow import serializer as serializer_mod
from scistudio.workflow.definition import NodeDef, WorkflowDefinition
from scistudio.workflow.serializer import load_yaml, save_yaml


class _BoomError(Exception):
    pass


def _make_workflow(node_id: str) -> WorkflowDefinition:
    return WorkflowDefinition(
        id="wf-durability",
        nodes=[NodeDef(id=node_id, block_type="IOBlock", config={"direction": "input"})],
    )


def test_interrupted_yaml_save_keeps_prior_file_readable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "wf.yaml"

    # Persist a good first version.
    save_yaml(_make_workflow("first"), path)
    assert load_yaml(path).nodes[0].id == "first"

    # Simulate a crash during the serialised write of the second version.
    def _boom_dump(*_args: object, **_kwargs: object) -> str:
        raise _BoomError("simulated crash mid yaml.safe_dump")

    monkeypatch.setattr(serializer_mod.yaml, "safe_dump", _boom_dump)

    with pytest.raises(_BoomError):
        save_yaml(_make_workflow("second"), path)

    # The prior YAML still loads cleanly.
    restored = load_yaml(path)
    assert restored.nodes[0].id == "first"

    # No temp siblings remain next to the YAML file.
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "wf.yaml"]
    assert leftovers == []


def test_yaml_save_overwrite_is_complete(tmp_path: Path) -> None:
    path = tmp_path / "wf.yaml"
    save_yaml(_make_workflow("first"), path)
    save_yaml(_make_workflow("second"), path)
    # Latest write fully present, never truncated.
    assert load_yaml(path).nodes[0].id == "second"
