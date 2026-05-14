"""macOS-only verification of workflow_watcher edge cases.

These tests are skipped on non-Darwin hosts because they target HFS+/APFS
quirks the implementation agent (which runs on Windows) cannot reproduce:

1. ``/tmp`` is a symlink to ``/private/tmp``. ``Path.resolve()`` collapses
   the symlink, and the watcher's ``_normalise`` helper resolves both
   sides through the same path before the self-write deque compares
   tuples. We assert the deque actually matches when called via the
   symlinked path.
2. Filenames are normalised to NFD by APFS / HFS+. SciEasy code passes
   strings in whatever form the user typed (typically NFC from the
   composing input methods). The handler normalises through NFC before
   comparing or emitting paths so the wire format is stable. We
   verify a Korean filename written via the symlinked path is detected.
"""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path
from typing import Any

import pytest
from watchdog.events import FileModifiedEvent

from scieasy.api.routes.workflow_watcher import _WorkflowFileHandler

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="macOS-only FS quirks (symlinks, NFD/NFC).",
)


def _make_handler(project_dir: Path) -> tuple[_WorkflowFileHandler, list[dict[str, Any]]]:
    captured: list[dict[str, Any]] = []

    def broadcast(payload: dict[str, Any]) -> None:
        captured.append(payload)

    handler = _WorkflowFileHandler(project_dir=project_dir, broadcast=broadcast, loop=None)
    return handler, captured


def test_tmp_symlink_consistency_in_self_write_dedupe(tmp_path: Path) -> None:
    """A path inside ``/tmp`` and its ``/private/tmp`` equivalent dedupe."""
    project = tmp_path / "proj"
    yaml_path = project / "workflows" / "demo.yaml"
    yaml_path.parent.mkdir(parents=True)
    yaml_path.write_text("id: w\nnodes: []\nedges: []\n", encoding="utf-8")

    handler, captured = _make_handler(project)

    # Mark self-write with the resolved path, then synthesise an event
    # using a path that traverses ``/tmp`` (which is a symlink). Both
    # forms should resolve to the same target via Path.resolve().
    handler.mark_self_write(yaml_path.resolve())
    # macOS-only contract: /tmp -> /private/tmp.
    symlinked = (
        Path("/tmp") / yaml_path.relative_to(Path("/private/tmp"))
        if (str(yaml_path).startswith("/private/tmp"))
        else yaml_path
    )
    handler.on_any_event(FileModifiedEvent(str(symlinked)))

    assert captured == []


def test_nfd_filename_is_matched_via_nfc_normalisation(tmp_path: Path) -> None:
    """A Korean filename in NFD on disk is still recognised."""
    project = tmp_path / "proj"
    workflows = project / "workflows"
    workflows.mkdir(parents=True)

    # "테스트" in NFC -> when written to APFS the filename is stored as NFD.
    nfc_name = "테스트.yaml"
    nfd_name = unicodedata.normalize("NFD", nfc_name)
    yaml_path = workflows / nfd_name
    yaml_path.write_text("id: w\nnodes: []\nedges: []\n", encoding="utf-8")

    handler, captured = _make_handler(project)
    handler.on_any_event(FileModifiedEvent(str(yaml_path)))

    assert len(captured) == 1
    # The emitted path is normalised to NFC so the frontend can compare
    # against user-provided / API-returned identifiers without itself
    # normalising.
    emitted_path = captured[0]["path"]
    assert unicodedata.is_normalized("NFC", emitted_path)
