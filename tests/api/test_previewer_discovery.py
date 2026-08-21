"""Previewer listing and reload endpoints (#2095).

The previewer tier gained a project and a user tier in #2017/#2044 without the
surface blocks and types already had around theirs: nothing enumerated the
registered previewers, and the previewer side had no reload entry point of its
own.

Note what is *not* claimed here. ``refresh_all_registries()`` has rebuilt the
previewer registry since #2021, so ``POST /api/blocks/reload`` already picked up
a drop-in previewer edit before this change; ``test_blocks_reload_also_rebuilds_previewers``
pins that pre-existing behaviour so the new endpoint cannot be mistaken for the
thing that made reloading work. What is new is a previewer-owned surface onto
that one implementation (FR-027's argument, applied one tier over).
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

DROPIN = """\
from scistudio.previewers.models import OwnerKind, PreviewerSpec


def get_previewers():
    return [
        PreviewerSpec(
            previewer_id={previewer_id!r},
            owner_kind=OwnerKind.PROJECT,
            owner_name="probe",
            target_type={target_type!r},
            priority={priority},
            capabilities=("probe",),
        ),
    ]
"""


def _write_dropin(
    project: Path, filename: str, *, previewer_id: str, target_type: str = "Array", priority: int = 50
) -> Path:
    previewers = project / "previewers"
    previewers.mkdir(parents=True, exist_ok=True)
    path = previewers / filename
    path.write_text(
        DROPIN.format(previewer_id=previewer_id, target_type=target_type, priority=priority),
        encoding="utf-8",
    )
    return path


# -- listing ----------------------------------------------------------------


def test_list_previewers_returns_the_core_fallbacks(client: TestClient) -> None:
    """Core specs load unconditionally, so the listing is never empty."""
    response = client.get("/api/previews/previewers")
    assert response.status_code == 200
    body = response.json()
    ids = {p["previewer_id"] for p in body["previewers"]}
    assert "core.series.basic" in ids
    assert "core.dataframe.basic" in ids
    assert all(p["owner_kind"] == "core" for p in body["previewers"])


def test_list_previewers_reports_the_tier_a_dropin_came_from(client: TestClient, opened_project: Path) -> None:
    _write_dropin(opened_project, "probe.py", previewer_id="probe.project")
    assert client.post("/api/previews/reload").status_code == 200

    body = client.get("/api/previews/previewers").json()
    entry = next(p for p in body["previewers"] if p["previewer_id"] == "probe.project")
    assert entry["owner_kind"] == "project"
    assert entry["owner_name"] == "probe"
    assert entry["target_type"] == "Array"
    assert entry["capabilities"] == ["probe"]


def test_list_previewers_orders_by_routing_precedence(client: TestClient, opened_project: Path) -> None:
    """Project first, then user, then package, then core (ADR-048 FR-003).

    The listing exists to be read by a person deciding which previewer wins, so
    it presents them in the order the router considers them rather than in
    registration order.
    """
    _write_dropin(opened_project, "probe.py", previewer_id="probe.project")
    assert client.post("/api/previews/reload").status_code == 200

    body = client.get("/api/previews/previewers").json()
    kinds = [p["owner_kind"] for p in body["previewers"]]
    assert kinds[0] == "project"
    # Every core spec sorts after every non-core one.
    first_core = kinds.index("core")
    assert set(kinds[first_core:]) == {"core"}


def test_list_previewers_filters_by_exact_target_type(client: TestClient, opened_project: Path) -> None:
    """The filter is an exact match, not the router's specificity walk.

    A caller asking what claims ``Spectrum`` wants the previewers written for
    ``Spectrum``, not every ancestor previewer that would also render one.
    """
    _write_dropin(opened_project, "probe.py", previewer_id="probe.spectrum", target_type="Spectrum")
    assert client.post("/api/previews/reload").status_code == 200

    body = client.get("/api/previews/previewers", params={"target_type": "Spectrum"}).json()
    assert [p["previewer_id"] for p in body["previewers"]] == ["probe.spectrum"]

    # ``Series`` is Spectrum's parent in the router's walk, but it is not this
    # spec's declared target, so the exact filter must not return it.
    series = client.get("/api/previews/previewers", params={"target_type": "Series"}).json()
    assert "probe.spectrum" not in {p["previewer_id"] for p in series["previewers"]}


def test_list_previewers_filter_with_no_match_is_empty_not_an_error(client: TestClient) -> None:
    body = client.get("/api/previews/previewers", params={"target_type": "NoSuchType"}).json()
    assert body["previewers"] == []


def test_list_previewers_surfaces_a_refused_dropin(client: TestClient, opened_project: Path) -> None:
    """A drop-in refused by the FR-016 collision guard was previously silent.

    It was recorded on the registry diagnostics and then only logged, so from
    the product it looked like a previewer that simply never appeared.
    """
    previewers = opened_project / "previewers"
    previewers.mkdir(parents=True, exist_ok=True)
    (previewers / "json.py").write_text("def get_previewers():\n    return []\n", encoding="utf-8")
    assert client.post("/api/previews/reload").status_code == 200

    body = client.get("/api/previews/previewers").json()
    assert any("json.py" in d for d in body["diagnostics"]), body["diagnostics"]


# -- reload ------------------------------------------------------------------


def test_reload_picks_up_a_new_dropin_previewer(client: TestClient, opened_project: Path) -> None:
    before = client.get("/api/previews/previewers").json()
    assert "probe.added" not in {p["previewer_id"] for p in before["previewers"]}

    _write_dropin(opened_project, "probe.py", previewer_id="probe.added")
    response = client.post("/api/previews/reload")
    assert response.status_code == 200
    body = response.json()
    assert "probe.added" in body["added"]
    assert body["removed"] == []
    assert body["reloaded"] == len(before["previewers"]) + 1

    after = client.get("/api/previews/previewers").json()
    assert "probe.added" in {p["previewer_id"] for p in after["previewers"]}


def test_reload_reports_a_removed_dropin(client: TestClient, opened_project: Path) -> None:
    path = _write_dropin(opened_project, "probe.py", previewer_id="probe.transient")
    assert client.post("/api/previews/reload").status_code == 200

    path.unlink()
    body = client.post("/api/previews/reload").json()
    assert body["removed"] == ["probe.transient"]
    assert body["added"] == []


def test_reload_picks_up_an_edit_to_an_existing_dropin(client: TestClient, opened_project: Path) -> None:
    """The registry caches the module, so an edit needs the rebuild.

    This is the loop a previewer author lives in, and the reason the surface
    needs its own endpoint rather than borrowing the block one.
    """
    _write_dropin(opened_project, "probe.py", previewer_id="probe.edited", priority=10)
    assert client.post("/api/previews/reload").status_code == 200
    body = client.get("/api/previews/previewers", params={"target_type": "Array"}).json()
    assert next(p for p in body["previewers"] if p["previewer_id"] == "probe.edited")["priority"] == 10

    _write_dropin(opened_project, "probe.py", previewer_id="probe.edited", priority=77)
    assert client.post("/api/previews/reload").status_code == 200
    body = client.get("/api/previews/previewers", params={"target_type": "Array"}).json()
    assert next(p for p in body["previewers"] if p["previewer_id"] == "probe.edited")["priority"] == 77


def test_blocks_reload_also_rebuilds_previewers(client: TestClient, opened_project: Path) -> None:
    """Pre-existing behaviour from #2021, pinned so the new endpoint is not
    mistaken for what made previewer reloading work.

    ``refresh_all_registries()`` rebuilds types, blocks, and previewers, and
    every reload endpoint reaches that one implementation. If this ever stops
    holding, the three endpoints have drifted apart again — the exact decay
    ADR-053 §10.3/§10.4 consolidated away.
    """
    _write_dropin(opened_project, "probe.py", previewer_id="probe.via.blocks")
    assert client.post("/api/blocks/reload").status_code == 200

    body = client.get("/api/previews/previewers").json()
    assert "probe.via.blocks" in {p["previewer_id"] for p in body["previewers"]}


def test_reload_with_no_change_reports_no_delta(client: TestClient, opened_project: Path) -> None:
    first = client.post("/api/previews/reload").json()
    second = client.post("/api/previews/reload").json()
    assert second["added"] == []
    assert second["removed"] == []
    assert second["reloaded"] == first["reloaded"]
