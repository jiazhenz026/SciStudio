"""Previewer listing and reload endpoints (#2095), over panel folders (#2493).

The listing enumerates every routing candidate with the tier it came from, and
the previewer side has its own reload entry point onto the one registry
rebuild. Since #2493 a previewer is a preview panel: a folder under
``<project>/panels`` with a ``panel.json`` and a page.

``test_blocks_reload_also_rebuilds_previewers`` pins that
``POST /api/blocks/reload`` reaches the same rebuild, so the previewer endpoint
cannot be mistaken for the thing that made reloading work (FR-027's argument,
applied one tier over).
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


def _write_panel(
    project: Path, panel_id: str, *, target_type: str = "Array", priority: int = 50, **fields: object
) -> Path:
    directory = project / "panels" / panel_id
    directory.mkdir(parents=True, exist_ok=True)
    descriptor = {
        "id": panel_id,
        "api_version": "1.0",
        "contexts": ["preview"],
        "types": [target_type],
        "priority": priority,
        **fields,
    }
    (directory / "panel.json").write_text(json.dumps(descriptor), encoding="utf-8")
    (directory / "index.html").write_text("<p>probe</p>", encoding="utf-8")
    return directory


# -- listing ----------------------------------------------------------------


def test_list_previewers_returns_the_core_panels(client: TestClient) -> None:
    """The built-in core panels load unconditionally, so the listing is never empty."""
    response = client.get("/api/previews/previewers")
    assert response.status_code == 200
    body = response.json()
    ids = {p["previewer_id"] for p in body["previewers"]}
    assert "core.series.basic" in ids
    assert "core.dataframe.basic" in ids
    assert all(p["owner_kind"] == "core" for p in body["previewers"])
    assert all(p["panel"] is not None for p in body["previewers"])


def test_list_previewers_reports_the_tier_a_panel_came_from(client: TestClient, opened_project: Path) -> None:
    _write_panel(opened_project, "probe.project")
    assert client.post("/api/previews/reload").status_code == 200

    body = client.get("/api/previews/previewers").json()
    entry = next(p for p in body["previewers"] if p["previewer_id"] == "probe.project")
    assert entry["owner_kind"] == "project"
    assert entry["target_type"] == "Array"
    assert entry["panel"]["types"] == ["Array"]
    assert set(entry) >= {"previewer_id", "owner_kind", "owner_name", "priority", "panel", "api_version"}
    assert not {"renderer", "backend_provider", "frontend_manifest"} & set(entry)


def test_list_previewers_orders_by_routing_precedence(client: TestClient, opened_project: Path) -> None:
    """Project first, then user, then package, then core (ADR-048 FR-003).

    The listing exists to be read by a person deciding which previewer wins, so
    it presents them in the order the router considers them rather than in
    registration order.
    """
    _write_panel(opened_project, "probe.project")
    assert client.post("/api/previews/reload").status_code == 200

    body = client.get("/api/previews/previewers").json()
    kinds = [p["owner_kind"] for p in body["previewers"]]
    assert kinds[0] == "project"
    # Every core spec sorts after every non-core one.
    first_core = kinds.index("core")
    assert set(kinds[first_core:]) == {"core"}


def test_list_previewers_filters_by_exact_target_type(client: TestClient, opened_project: Path) -> None:
    """The filter is an exact match, not the router's specificity walk.

    A caller asking what claims ``Array`` wants the previewers written for
    ``Array``, not every ancestor previewer that would also render one.
    """
    _write_panel(opened_project, "probe.array", target_type="Array")
    assert client.post("/api/previews/reload").status_code == 200

    body = client.get("/api/previews/previewers", params={"target_type": "Array"}).json()
    assert {p["previewer_id"] for p in body["previewers"]} == {"probe.array", "core.array.basic"}

    # ``DataObject`` is Array's parent in the router's walk, but it is not this
    # panel's declared type, so the exact filter must not return it.
    parent = client.get("/api/previews/previewers", params={"target_type": "DataObject"}).json()
    assert "probe.array" not in {p["previewer_id"] for p in parent["previewers"]}


def test_list_previewers_filter_with_no_match_is_empty_not_an_error(client: TestClient) -> None:
    body = client.get("/api/previews/previewers", params={"target_type": "NoSuchType"}).json()
    assert body["previewers"] == []


def test_list_previewers_surfaces_a_refused_panel_folder(client: TestClient, opened_project: Path) -> None:
    """A panel folder refused by validation was previously silent.

    It was recorded on the catalog diagnostics and then only logged, so from the
    product it looked like a previewer that simply never appeared.
    """
    _write_panel(opened_project, "probe.bad", id="probe.mismatch")
    assert client.post("/api/previews/reload").status_code == 200

    body = client.get("/api/previews/previewers").json()
    assert any("probe.bad" in d for d in body["diagnostics"]), body["diagnostics"]


# -- reload ------------------------------------------------------------------


def test_reload_picks_up_a_new_preview_panel(client: TestClient, opened_project: Path) -> None:
    baseline = client.post("/api/previews/reload")
    assert baseline.status_code == 200
    before_count = baseline.json()["reloaded"]
    before = client.get("/api/previews/previewers").json()
    assert "probe.added" not in {p["previewer_id"] for p in before["previewers"]}

    _write_panel(opened_project, "probe.added")
    response = client.post("/api/previews/reload")
    assert response.status_code == 200
    body = response.json()
    assert "probe.added" in body["added"]
    assert body["removed"] == []
    assert body["reloaded"] == before_count + 1

    after = client.get("/api/previews/previewers").json()
    entry = next(p for p in after["previewers"] if p["previewer_id"] == "probe.added")
    assert entry["shadowed"] is False


def test_reload_reports_a_removed_panel(client: TestClient, opened_project: Path) -> None:
    import shutil

    directory = _write_panel(opened_project, "probe.transient")
    assert client.post("/api/previews/reload").status_code == 200

    shutil.rmtree(directory)
    body = client.post("/api/previews/reload").json()
    assert body["removed"] == ["probe.transient"]
    assert body["added"] == []


def test_reload_picks_up_an_edit_to_an_existing_panel(client: TestClient, opened_project: Path) -> None:
    """This is the loop a previewer author lives in."""
    _write_panel(opened_project, "probe.edited", priority=10)
    assert client.post("/api/previews/reload").status_code == 200
    body = client.get("/api/previews/previewers", params={"target_type": "Array"}).json()
    assert next(p for p in body["previewers"] if p["previewer_id"] == "probe.edited")["priority"] == 10

    _write_panel(opened_project, "probe.edited", priority=77)
    assert client.post("/api/previews/reload").status_code == 200
    body = client.get("/api/previews/previewers", params={"target_type": "Array"}).json()
    assert next(p for p in body["previewers"] if p["previewer_id"] == "probe.edited")["priority"] == 77


def test_blocks_reload_also_rebuilds_previewers(client: TestClient, opened_project: Path) -> None:
    """``refresh_all_registries()`` rebuilds types, blocks, and panels, and every
    reload endpoint reaches that one implementation. If this ever stops holding,
    the endpoints have drifted apart again — the exact decay ADR-053
    §10.3/§10.4 consolidated away.
    """
    _write_panel(opened_project, "probe.via.blocks")
    assert client.post("/api/blocks/reload").status_code == 200

    body = client.get("/api/previews/previewers").json()
    assert "probe.via.blocks" in {p["previewer_id"] for p in body["previewers"]}


def test_reload_with_no_change_reports_no_delta(client: TestClient, opened_project: Path) -> None:
    first = client.post("/api/previews/reload").json()
    second = client.post("/api/previews/reload").json()
    assert second["added"] == []
    assert second["removed"] == []
    assert second["reloaded"] == first["reloaded"]
