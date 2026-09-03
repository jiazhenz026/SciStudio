"""A panel document has to be able to change and be seen changing (FR-032).

ADR-054 spec 1 FR-030 requires a save to reload the panel, and FR-032 requires
the reload trigger to fire for panel files the *agent* writes on the person's
behalf, not only for files the person edits directly. Both run through the
ADR-036/ADR-045 file surface, and both were silently excluded: a panel's entry
document is ``index.html``, and ``.html`` was not in
:data:`~scistudio.api.file_contracts.ADR036_FILE_ALLOWLIST`.

The consequence was one gap wearing two faces. The watcher's
``_ProjectFileHandler._entity_id_for`` filters on that allowlist, so a panel
document that changed on disk produced no ``file.changed`` event at all — while
the ``panel.json`` beside it *did* fire, which made the gap read as a flaky
reload rather than as a missing extension. And ``PUT /api/projects/{id}/file``
answered 415, so the person's own save of a panel document was refused by the
editor route that every other source file goes through.

These tests pin the extension from both sides so it cannot be dropped again.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from scistudio.api.file_contracts import ADR036_FILE_ALLOWLIST
from scistudio.api.routes.workflow_watcher import _ProjectFileHandler

PANEL_DOCUMENT = "<!doctype html><title>panel</title><body>panel</body>\n"


def _open(client: TestClient, project_path: Path) -> str:
    response = client.post(
        "/api/projects/",
        json={"name": "T", "description": "", "path": str(project_path)},
    )
    assert response.status_code == 200, response.text
    project_id = str(response.json()["id"])
    client.get(f"/api/projects/{project_id}")
    return project_id


def test_the_allowlist_admits_a_panel_entry_document() -> None:
    """The one constant both the watcher and the file route filter on."""
    assert ".html" in ADR036_FILE_ALLOWLIST
    assert ".json" in ADR036_FILE_ALLOWLIST, "panel.json fired before this change and must keep firing"


def test_the_watcher_reports_a_panel_document_as_a_changed_file(tmp_path: Path) -> None:
    """FR-032: a panel document that changes on disk produces a signal.

    Asserted against the handler's own entity resolution rather than through a
    real filesystem event, because what was broken is the filter, not the
    observer: with ``.html`` excluded, ``_entity_id_for`` returned ``None`` and
    the event was dropped before anything else could see it.
    """
    project_dir = tmp_path / "project"
    (project_dir / "panels" / "core.table.basic").mkdir(parents=True)
    handler = _ProjectFileHandler(
        project_dir=project_dir,
        broadcast=lambda *args, **kwargs: None,
        loop=asyncio.new_event_loop(),
        runtime=None,
    )

    document = project_dir / "panels" / "core.table.basic" / "index.html"
    document.write_text(PANEL_DOCUMENT, encoding="utf-8")
    assert handler._entity_id_for(document) == "panels/core.table.basic/index.html"

    declaration = project_dir / "panels" / "core.table.basic" / "panel.json"
    declaration.write_text("{}\n", encoding="utf-8")
    assert handler._entity_id_for(declaration) == "panels/core.table.basic/panel.json"

    # The filter still filters: an extension outside the allowlist is dropped,
    # so this change widened the allowlist rather than removing the check.
    excluded = project_dir / "panels" / "core.table.basic" / "notes.tiff"
    excluded.write_text("x", encoding="utf-8")
    assert handler._entity_id_for(excluded) is None


def test_the_file_route_accepts_a_panel_document(client: TestClient, project_parent: Path) -> None:
    """The person's own save path, which answered 415 before this change."""
    project_id = _open(client, project_parent / "panelsave")
    project_root = Path(client.app.state.runtime.known_projects[project_id].path)
    (project_root / "panels" / "probe.panel").mkdir(parents=True)
    (project_root / "panels" / "probe.panel" / "index.html").write_bytes(b"<!doctype html>old\n")

    written = client.put(
        f"/api/projects/{project_id}/file?path=panels/probe.panel/index.html",
        json={"content": PANEL_DOCUMENT},
    )
    assert written.status_code == 200, written.text

    read = client.get(f"/api/projects/{project_id}/file?path=panels/probe.panel/index.html")
    assert read.status_code == 200
    assert read.json()["content"] == PANEL_DOCUMENT


def test_the_file_route_still_refuses_an_extension_outside_the_allowlist(
    client: TestClient, project_parent: Path
) -> None:
    """Widening the allowlist by one entry is not the same as opening it."""
    project_id = _open(client, project_parent / "panelrefuse")
    refused = client.put(
        f"/api/projects/{project_id}/file?path=panels/probe.panel/index.exe",
        json={"content": "x"},
    )
    assert refused.status_code == 415
