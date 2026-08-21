"""Shared helpers for the tutorial manifest, condition, and action tests.

ADR-053 Learning Center spec §4.4. These tests exercise
``src/scistudio/tutorials/{manifest,conditions,actions}.py`` and nothing else:
the package deliberately has no dependency on ``scistudio.api``, so none of
this needs a FastAPI app, a session, or a running engine.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml

from scistudio.tutorials.conditions import RunSummary
from scistudio.tutorials.manifest import TUTORIAL_MANIFEST_FILENAME
from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition

MINIMAL_MANIFEST: dict[str, Any] = {
    "manifest_version": 1,
    "id": "example",
    "title": "Example",
    "summary": "A tutorial used by the tests.",
    "steps": [{"id": "one", "say": "Do the thing."}],
}


def write_tutorial(
    directory: Path,
    manifest: dict[str, Any] | None = None,
    *,
    files: dict[str, str] | None = None,
) -> Path:
    """Create a tutorial directory and return it.

    ``files`` maps tutorial-directory-relative paths to their text contents, so
    a test can give a tutorial the assets its manifest references without
    committing binary material.
    """
    directory.mkdir(parents=True, exist_ok=True)
    payload = MINIMAL_MANIFEST if manifest is None else manifest
    (directory / TUTORIAL_MANIFEST_FILENAME).write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )
    for relative, content in (files or {}).items():
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        # newline="": tests compare bytes read back from these files against
        # POSIX literals, so LF must land on disk untranslated rather than
        # becoming CRLF on Windows (#2075).
        target.write_text(content, encoding="utf-8", newline="")
    return directory


def snapshot_tree(root: Path) -> dict[str, tuple[int, bytes | None]]:
    """Return a content snapshot of every path under ``root``.

    Used to assert FR-055: evaluating a condition creates no file and changes
    nothing on disk.
    """
    snapshot: dict[str, tuple[int, bytes | None]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in list(dirnames) + list(filenames):
            path = Path(dirpath) / name
            relative = str(path.relative_to(root))
            if path.is_file():
                snapshot[relative] = (path.stat().st_size, path.read_bytes())
            else:
                snapshot[relative] = (0, None)
    return snapshot


@dataclass
class StubProductState:
    """A hand-built :class:`~scistudio.tutorials.conditions.ProductState`.

    Every member is a plain value the test sets, so each vocabulary term can be
    driven true and false without any product machinery (spec §4.4, Conditions
    row). ``reads`` records which members evaluation touched, which is how the
    side-effect test shows evaluation only reads.
    """

    project_dir: Path | None = None
    tutorial_library_dir: Path | None = None
    workflow_definition: WorkflowDefinition | None = None
    block_types: frozenset[str] = frozenset()
    data_types: frozenset[str] = frozenset()
    previewer_types: frozenset[str] = frozenset()
    plots: tuple[tuple[str, str, str], ...] = ()
    runs: tuple[RunSummary, ...] = ()
    ports_with_output: frozenset[tuple[str, str]] = frozenset()
    branches: frozenset[str] = frozenset()
    current_branch: str | None = None
    library: frozenset[tuple[str, str]] = frozenset()
    interactions: frozenset[str] = frozenset()
    pages: frozenset[str] = frozenset()
    events: frozenset[str] = frozenset()
    reads: list[str] = field(default_factory=list)

    def workflow(self) -> WorkflowDefinition | None:
        self.reads.append("workflow")
        return self.workflow_definition

    def block_type_names(self) -> frozenset[str]:
        self.reads.append("block_type_names")
        return self.block_types

    def data_type_names(self) -> frozenset[str]:
        self.reads.append("data_type_names")
        return self.data_types

    def previewer_type_ids(self) -> frozenset[str]:
        self.reads.append("previewer_type_ids")
        return self.previewer_types

    def plot_bindings(self) -> tuple[tuple[str, str, str], ...]:
        self.reads.append("plot_bindings")
        return self.plots

    def run_records(self) -> tuple[RunSummary, ...]:
        self.reads.append("run_records")
        return self.runs

    def port_has_output(self, node_id: str, port: str) -> bool:
        self.reads.append("port_has_output")
        return (node_id, port) in self.ports_with_output

    def git_branches(self) -> frozenset[str]:
        self.reads.append("git_branches")
        return self.branches

    def git_current_branch(self) -> str | None:
        self.reads.append("git_current_branch")
        return self.current_branch

    def library_entries(self) -> frozenset[tuple[str, str]]:
        self.reads.append("library_entries")
        return self.library

    def interactions_completed(self) -> frozenset[str]:
        self.reads.append("interactions_completed")
        return self.interactions

    def pages_reached(self) -> frozenset[str]:
        self.reads.append("pages_reached")
        return self.pages

    def ui_events(self) -> frozenset[str]:
        self.reads.append("ui_events")
        return self.events


@pytest.fixture
def loaded_workflow() -> WorkflowDefinition:
    """A two-node workflow: ``LoadCSV -> SaveCSV``."""
    return WorkflowDefinition(
        id="wf-1",
        nodes=[
            NodeDef(id="load-1", block_type="LoadCSV", config={"path": "data/raw/cells.csv"}),
            NodeDef(id="save-1", block_type="SaveCSV", config={"path": "data/processed/out.csv"}),
        ],
        edges=[EdgeDef(source="load-1:table", target="save-1:table")],
    )
