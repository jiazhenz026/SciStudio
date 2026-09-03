"""Panel listing and reload endpoints (#2095).

The panel tier gained a project and a user tier in #2017/#2044 without the
surface blocks and types already had around theirs: nothing enumerated the
registered panels, and the panel side had no reload entry point of its
own.

Note what is *not* claimed here. ``refresh_all_registries()`` has rebuilt the
panel registry since #2021, so ``POST /api/blocks/reload`` already picked up
a drop-in panel edit before this change; ``test_blocks_reload_also_rebuilds_panels``
pins that pre-existing behaviour so the new endpoint cannot be mistaken for the
thing that made reloading work. What is new is a panel-owned surface onto
that one implementation (FR-027's argument, applied one tier over).
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

DROPIN = """\
from scistudio.panels.models import OwnerKind, PanelSpec


def get_previewers():
    return [
        PanelSpec(
            previewer_id={previewer_id!r},
            owner_kind=OwnerKind.PROJECT,
            owner_name="probe",
            target_type={target_type!r},
            priority={priority},
            features=("probe",),
        ),
    ]
"""


def _write_dropin(
    project: Path, filename: str, *, previewer_id: str, target_type: str = "Array", priority: int = 50
) -> Path:
    panels = project / "previewers"
    panels.mkdir(parents=True, exist_ok=True)
    path = panels / filename
    path.write_text(
        DROPIN.format(previewer_id=previewer_id, target_type=target_type, priority=priority),
        encoding="utf-8",
    )
    return path


# -- listing ----------------------------------------------------------------


def test_list_panels_returns_the_core_fallbacks(client: TestClient) -> None:
    """Core specs load unconditionally, so the listing is never empty."""
    response = client.get("/api/panels")
    assert response.status_code == 200
    body = response.json()
    ids = {p["panel_id"] for p in body["panels"]}
    assert "core.series.basic" in ids
    assert "core.dataframe.basic" in ids
    assert all(p["owner_kind"] == "core" for p in body["panels"])


def test_list_panels_reports_the_tier_a_dropin_came_from(client: TestClient, opened_project: Path) -> None:
    _write_dropin(opened_project, "probe.py", previewer_id="probe.project")
    assert client.post("/api/panels/reload").status_code == 200

    body = client.get("/api/panels").json()
    entry = next(p for p in body["panels"] if p["panel_id"] == "probe.project")
    assert entry["owner_kind"] == "project"
    assert entry["owner_name"] == "probe"
    assert entry["target_type"] == "Array"
    assert entry["features"] == ["probe"]


def test_list_panels_orders_by_routing_precedence(client: TestClient, opened_project: Path) -> None:
    """Project first, then user, then package, then core (ADR-048 FR-003).

    The listing exists to be read by a person deciding which panel wins, so
    it presents them in the order the router considers them rather than in
    registration order.
    """
    _write_dropin(opened_project, "probe.py", previewer_id="probe.project")
    assert client.post("/api/panels/reload").status_code == 200

    body = client.get("/api/panels").json()
    kinds = [p["owner_kind"] for p in body["panels"]]
    assert kinds[0] == "project"
    # Every core spec sorts after every non-core one.
    first_core = kinds.index("core")
    assert set(kinds[first_core:]) == {"core"}


def test_list_panels_filters_by_exact_target_type(client: TestClient, opened_project: Path) -> None:
    """The filter is an exact match, not the router's specificity walk.

    A caller asking what claims ``Spectrum`` wants the panels written for
    ``Spectrum``, not every ancestor panel that would also render one.
    """
    _write_dropin(opened_project, "probe.py", previewer_id="probe.spectrum", target_type="Spectrum")
    assert client.post("/api/panels/reload").status_code == 200

    body = client.get("/api/panels", params={"target_type": "Spectrum"}).json()
    assert [p["panel_id"] for p in body["panels"]] == ["probe.spectrum"]

    # ``Series`` is Spectrum's parent in the router's walk, but it is not this
    # spec's declared target, so the exact filter must not return it.
    series = client.get("/api/panels", params={"target_type": "Series"}).json()
    assert "probe.spectrum" not in {p["panel_id"] for p in series["panels"]}


def test_list_panels_filter_with_no_match_is_empty_not_an_error(client: TestClient) -> None:
    body = client.get("/api/panels", params={"target_type": "NoSuchType"}).json()
    assert body["panels"] == []


def test_list_panels_surfaces_a_refused_dropin(client: TestClient, opened_project: Path) -> None:
    """A drop-in refused by the FR-016 collision guard was previously silent.

    It was recorded on the registry diagnostics and then only logged, so from
    the product it looked like a panel that simply never appeared.
    """
    panels = opened_project / "previewers"
    panels.mkdir(parents=True, exist_ok=True)
    (panels / "json.py").write_text("def get_previewers():\n    return []\n", encoding="utf-8")
    assert client.post("/api/panels/reload").status_code == 200

    body = client.get("/api/panels").json()
    assert any("json.py" in d for d in body["diagnostics"]), body["diagnostics"]


# -- reload ------------------------------------------------------------------


def test_reload_picks_up_a_new_dropin_panel(client: TestClient, opened_project: Path) -> None:
    before = client.get("/api/panels").json()
    assert "probe.added" not in {p["panel_id"] for p in before["panels"]}

    _write_dropin(opened_project, "probe.py", previewer_id="probe.added")
    response = client.post("/api/panels/reload")
    assert response.status_code == 200
    body = response.json()
    assert "probe.added" in body["added"]
    assert body["removed"] == []

    # ADR-054 spec 1 FR-023: ``reloaded`` counts the routing specs, while the
    # listing is their union with the panels addressed by the block that opens
    # them (FR-017), which declare no target type and so never enter the type
    # ladder. The two numbers therefore differ by however many of those exist;
    # what the rebuild must guarantee is the delta, so that is what is asserted.
    after = client.get("/api/panels").json()
    assert {p["panel_id"] for p in after["panels"]} == {p["panel_id"] for p in before["panels"]} | {"probe.added"}


def test_reload_reports_a_removed_dropin(client: TestClient, opened_project: Path) -> None:
    path = _write_dropin(opened_project, "probe.py", previewer_id="probe.transient")
    assert client.post("/api/panels/reload").status_code == 200

    path.unlink()
    body = client.post("/api/panels/reload").json()
    assert body["removed"] == ["probe.transient"]
    assert body["added"] == []


def test_reload_picks_up_an_edit_to_an_existing_dropin(client: TestClient, opened_project: Path) -> None:
    """The registry caches the module, so an edit needs the rebuild.

    This is the loop a panel author lives in, and the reason the surface
    needs its own endpoint rather than borrowing the block one.
    """
    _write_dropin(opened_project, "probe.py", previewer_id="probe.edited", priority=10)
    assert client.post("/api/panels/reload").status_code == 200
    body = client.get("/api/panels", params={"target_type": "Array"}).json()
    assert next(p for p in body["panels"] if p["panel_id"] == "probe.edited")["priority"] == 10

    _write_dropin(opened_project, "probe.py", previewer_id="probe.edited", priority=77)
    assert client.post("/api/panels/reload").status_code == 200
    body = client.get("/api/panels", params={"target_type": "Array"}).json()
    assert next(p for p in body["panels"] if p["panel_id"] == "probe.edited")["priority"] == 77


def test_blocks_reload_also_rebuilds_panels(client: TestClient, opened_project: Path) -> None:
    """Pre-existing behaviour from #2021, pinned so the new endpoint is not
    mistaken for what made panel reloading work.

    ``refresh_all_registries()`` rebuilds types, blocks, and panels, and
    every reload endpoint reaches that one implementation. If this ever stops
    holding, the three endpoints have drifted apart again — the exact decay
    ADR-053 §10.3/§10.4 consolidated away.
    """
    _write_dropin(opened_project, "probe.py", previewer_id="probe.via.blocks")
    assert client.post("/api/blocks/reload").status_code == 200

    body = client.get("/api/panels").json()
    assert "probe.via.blocks" in {p["panel_id"] for p in body["panels"]}


def test_reload_with_no_change_reports_no_delta(client: TestClient, opened_project: Path) -> None:
    first = client.post("/api/panels/reload").json()
    second = client.post("/api/panels/reload").json()
    assert second["added"] == []
    assert second["removed"] == []
    assert second["reloaded"] == first["reloaded"]
