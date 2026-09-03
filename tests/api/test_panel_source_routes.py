"""The panel API surface over HTTP (T-004, T-008 backend half, T-010, D-020).

The behaviour these routes adapt is tested below them —
``tests/panels/test_panel_asset_route.py`` for the confinement check and
``tests/panels/test_panel_editing.py`` for where an edit lands. What is asserted
here is the surface D-020 fixes, because ``W3-fe`` is building against it and
the two meet at the wire:

* the merged asset route serves every tier through one URL shape and is the one
  route answering cross-origin (FR-021, A-008);
* the response the host already reads names the panel it chose and the panel to
  fall back to (FR-015, D-013), which is what lets the frontend delete its own
  mapping from a response's kind to a component (FR-036, SC-010);
* reading, saving, copy-on-write and revert answer at the paths and with the
  fields D-020 names (FR-024 to FR-029).
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

DOCUMENT = "<!doctype html><title>probe</title><body>probe</body>\n"


def _write_project_panel(project: Path, panel_id: str, *, capability: str = "displaying", **extra: object) -> Path:
    """Write a panel directory into the project tier and return it."""
    directory = project / "panels" / panel_id
    directory.mkdir(parents=True, exist_ok=True)
    declaration: dict[str, object] = {
        "panel_id": panel_id,
        "display_name": panel_id,
        "target_types": ["DataFrame"],
        "capability": capability,
        "entry": "index.html",
        "api_version": "1",
    }
    declaration.update(extra)
    # Bytes, not text: ``write_text`` translates newlines on Windows, and these
    # tests compare the served body to the document byte for byte.
    (directory / "panel.json").write_bytes((json.dumps(declaration, indent=2) + "\n").encode("utf-8"))
    (directory / "index.html").write_bytes(DOCUMENT.encode("utf-8"))
    return directory


def _create_session(client: TestClient, *, ref: str, recorded_type: str, type_chain: list[str]) -> httpx.Response:
    return client.post(
        "/api/previews/sessions",
        json={
            "target": {
                "kind": "data_ref",
                "ref": ref,
                "recorded_type": recorded_type,
                "type_chain": type_chain,
            },
            "query": {},
        },
    )


# ---------------------------------------------------------------------------
# T-004: the merged asset route
# ---------------------------------------------------------------------------


def test_the_merged_route_serves_a_core_panel_document(client: TestClient) -> None:
    """A built-in panel is on disk and served through the same route as any other.

    That is the precondition for Story 2: copying a built-in panel into a
    project is a directory copy, which a compiled-in component could never be.
    """
    response = client.get("/api/panels/assets/core.base.fallback/index.html")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<" in response.text


def test_the_merged_route_serves_a_project_panel_through_the_same_url_shape(
    client: TestClient, opened_project: Path
) -> None:
    """FR-021: the URL shape is identical whichever tier the panel came from."""
    _write_project_panel(opened_project, "probe.project.panel")
    assert client.post("/api/panels/reload").status_code == 200

    response = client.get("/api/panels/assets/probe.project.panel/index.html")
    assert response.status_code == 200
    assert response.text == DOCUMENT


def test_the_asset_route_is_the_only_one_that_answers_cross_origin(client: TestClient) -> None:
    """FR-021 and A-008: a panel at an opaque origin can reach this and nothing else.

    The header is on this route's own responses. Its absence everywhere else is
    what keeps the asset route the only thing a panel can fetch from without
    going through the host, so both halves are asserted.
    """
    served = client.get("/api/panels/assets/core.base.fallback/index.html")
    assert served.headers["access-control-allow-origin"] == "*"
    assert served.headers["cross-origin-resource-policy"] == "cross-origin"
    # No credentials are granted with it: these responses are read-only.
    assert "access-control-allow-credentials" not in served.headers

    for path in ("/api/panels", "/api/panels/choices"):
        other = client.get(path)
        assert other.status_code == 200
        assert "access-control-allow-origin" not in other.headers


@pytest.mark.parametrize(
    "asset_path",
    [
        "..%2f..%2fpanel.json",
        "%2e%2e%2f%2e%2e%2fpanel.json",
        "%2e%2e%2f%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
        "assets%2f..%2f..%2f..%2fpanel.json",
        "..\\..\\panel.json",
    ],
)
def test_an_encoded_traversal_through_the_route_is_refused(client: TestClient, asset_path: str) -> None:
    """The escape as it actually arrives: percent-encoded.

    A literal ``../..`` never reaches the server — every HTTP client, this one
    included, resolves it against the base URL before the request is sent, so
    asserting it here would assert the client's behaviour rather than the
    route's. The encoded spellings survive the client intact and are decoded by
    the ASGI layer into ``..`` just before the confinement check sees them,
    which is exactly the case worth pinning at this level. The unencoded forms
    are covered against the check itself in
    ``tests/panels/test_panel_asset_route.py``.
    """
    response = client.get(f"/api/panels/assets/core.base.fallback/{asset_path}")
    assert response.status_code in {400, 404}
    # A refusal, not a file: the body is the route's diagnostic rather than
    # whatever the traversal was reaching for.
    assert response.headers["content-type"].startswith("application/json")


def test_a_panel_id_that_is_a_traversal_is_refused(client: TestClient) -> None:
    response = client.get("/api/panels/assets/..%2f..%2f..%2fsecret/index.html")
    assert response.status_code in {400, 404}


def test_an_unknown_panel_is_a_404(client: TestClient) -> None:
    response = client.get("/api/panels/assets/no.such.panel/index.html")
    assert response.status_code == 404
    assert "no.such.panel" in response.json()["detail"]


def test_a_disallowed_suffix_is_refused_even_when_the_file_exists(client: TestClient, opened_project: Path) -> None:
    directory = _write_project_panel(opened_project, "probe.suffix")
    (directory / "secrets.py").write_text("TOKEN = 'x'\n", encoding="utf-8")
    assert client.post("/api/panels/reload").status_code == 200

    response = client.get("/api/panels/assets/probe.suffix/secrets.py")
    assert response.status_code == 404
    assert "TOKEN" not in response.text


def test_the_two_migration_routes_still_answer(client: TestClient) -> None:
    """FR-022: they keep serving their existing clients, through the merged check.

    A 404 rather than a 405 or a route-not-found is the point: the paths are
    still mounted and still answer, they simply have nothing to serve for a
    panel id that declares no manifest.
    """
    assert client.get("/api/previews/assets/core.base.fallback/index.html").status_code == 404
    assert client.get("/api/blocks/panels/core.base.fallback/index.html").status_code == 404


# ---------------------------------------------------------------------------
# T-008 backend half: the backend names the panel and the fallback
# ---------------------------------------------------------------------------


def test_the_envelope_names_the_chosen_panel_and_the_fallback(client: TestClient, opened_project: Path) -> None:
    """FR-015 and D-013, the whole of the backend's half of T-008.

    Everything the host needs to mount the chosen panel *and* the fallback is on
    the response it is already reading, so the frontend needs no table of its
    own to work either of them out (FR-036, SC-010).
    """
    upload = client.post("/api/data/upload", files={"file": ("p.csv", b"a,b\n1,2\n", "text/csv")})
    ref = upload.json()["ref"]
    created = _create_session(client, ref=ref, recorded_type="DataFrame", type_chain=["DataObject", "DataFrame"])
    assert created.status_code == 200
    body = created.json()

    assert body["fallback_panel_id"] == "core.base.fallback"
    for descriptor in (body["panel"], body["fallback_panel"]):
        assert descriptor is not None
        # D-016.3: the host refuses to mount without either of these, so a
        # descriptor missing one is a backend defect rather than a host fallback.
        assert descriptor["accepted_api_version"] == "1"
        assert descriptor["read_limits"]["max_rows"] > 0
        assert descriptor["read_limits"]["max_bytes"] > 0
        assert descriptor["document_url"].startswith("/api/panels/assets/")
        assert descriptor["asset_base_url"].startswith("/api/panels/assets/")
    assert body["panel"]["panel_id"] == body["previewer_id"]
    assert body["fallback_panel"]["panel_id"] == "core.base.fallback"
    # FR-011 / FR-049: the preview surface grants display only.
    assert body["panel"]["capability"] == "displaying"

    # And the document the descriptor names is actually servable, so the host
    # mounting straight from the response cannot be handed a dead URL.
    served = client.get(body["panel"]["document_url"])
    assert served.status_code == 200


def test_reading_and_patching_a_session_carry_the_same_two_fields(client: TestClient, opened_project: Path) -> None:
    """The host re-reads a session; it must not lose what it needs to remount."""
    upload = client.post("/api/data/upload", files={"file": ("p.csv", b"a\n1\n2\n3\n", "text/csv")})
    ref = upload.json()["ref"]
    session_id = _create_session(
        client, ref=ref, recorded_type="DataFrame", type_chain=["DataObject", "DataFrame"]
    ).json()["session_id"]

    read = client.get(f"/api/previews/sessions/{session_id}").json()
    patched = client.patch(f"/api/previews/sessions/{session_id}", json={"query": {"page": 1}}).json()
    for body in (read, patched):
        assert body["fallback_panel_id"] == "core.base.fallback"
        assert body["panel"] is not None
        assert body["fallback_panel"] is not None


# ---------------------------------------------------------------------------
# FR-023: the catalogue carries the descriptor and the tier
# ---------------------------------------------------------------------------


def test_the_catalogue_carries_a_descriptor_and_a_tier(client: TestClient) -> None:
    body = client.get("/api/panels").json()
    entries = {entry["panel_id"]: entry for entry in body["panels"]}

    fallback = entries["core.base.fallback"]
    assert fallback["tier"] == "core"
    assert fallback["capability"] == "displaying"
    assert fallback["descriptor"]["document_url"] == "/api/panels/assets/core.base.fallback/index.html"

    # FR-017: a block-addressed panel declares no target type, so it never
    # enters the type ladder — and the catalogue still has to answer for it,
    # because a producing mount looks it up by id.
    router = entries["core.interactive.data_router"]
    assert router["capability"] == "producing"
    assert router["target_types"] == []
    assert router["descriptor"] is not None


def test_the_catalogue_reports_the_tier_a_panel_shadows(client: TestClient, opened_project: Path) -> None:
    _write_project_panel(opened_project, "core.base.fallback", target_types=["DataObject"])
    assert client.post("/api/panels/reload").status_code == 200

    entries = {e["panel_id"]: e for e in client.get("/api/panels").json()["panels"]}
    assert entries["core.base.fallback"]["tier"] == "project"
    assert entries["core.base.fallback"]["shadows"] == "core"


# ---------------------------------------------------------------------------
# T-010: reading, writing, copy-on-write, and revert over HTTP
# ---------------------------------------------------------------------------


def test_reading_the_source_of_a_core_panel(client: TestClient) -> None:
    """FR-024: any resolved panel, whichever tier it came from."""
    body = client.get("/api/panels/core.base.fallback/source").json()
    assert body["panel_id"] == "core.base.fallback"
    assert body["tier"] == "core"
    assert body["editable"] is False
    assert body["entry"] == "index.html"
    assert "<" in body["source"]
    assert json.loads(body["declaration"])["panel_id"] == "core.base.fallback"


def test_saving_a_project_panel_writes_it_back_in_place(client: TestClient, opened_project: Path) -> None:
    directory = _write_project_panel(opened_project, "probe.inplace")
    assert client.post("/api/panels/reload").status_code == 200

    response = client.put("/api/panels/probe.inplace/source", json={"source": "<!doctype html>new\n"})
    assert response.status_code == 200
    body = response.json()
    assert body["tier"] == "project"
    assert body["copied"] is False
    assert (directory / "index.html").read_text(encoding="utf-8") == "<!doctype html>new\n"
    # FR-030: the response carries what the host needs to remount.
    assert body["descriptor"]["document_url"] == "/api/panels/assets/probe.inplace/index.html"
    assert client.get(body["descriptor"]["document_url"]).text == "<!doctype html>new\n"


def test_saving_a_core_panel_copies_it_into_the_project(client: TestClient, opened_project: Path) -> None:
    """FR-026 and FR-027, and Story 2 scenarios 1 and 4."""
    core_source = client.get("/api/panels/core.base.fallback/source").json()["source"]

    response = client.put(
        "/api/panels/core.base.fallback/source",
        json={"source": core_source + "<!-- edited -->\n"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["copied"] is True
    assert body["tier"] == "project"

    copy = opened_project / "panels" / "core.base.fallback"
    assert (copy / "index.html").read_text(encoding="utf-8").endswith("<!-- edited -->\n")
    assert json.loads((copy / "panel.json").read_text(encoding="utf-8"))["panel_id"] == "core.base.fallback"

    # The copy now resolves in preference to the built-in one.
    after = client.get("/api/panels/core.base.fallback/source").json()
    assert after["tier"] == "project"
    assert after["editable"] is True
    assert after["shadows"] == "core"


def test_saving_a_core_panel_with_no_project_open_is_refused(client: TestClient) -> None:
    """FR-026 names the open project; there is no second answer to fall back to."""
    response = client.put("/api/panels/core.base.fallback/source", json={"source": DOCUMENT})
    assert response.status_code == 409
    assert "no project is open" in response.json()["detail"]


def test_reverting_deletes_the_copy_and_restores_the_original(client: TestClient, opened_project: Path) -> None:
    """FR-029, and the revert Story 3 scenario 2 offers from the error surface."""
    original = client.get("/api/panels/core.base.fallback/source").json()["source"]
    client.put("/api/panels/core.base.fallback/source", json={"source": "<!doctype html>broken\n"})
    assert (opened_project / "panels" / "core.base.fallback").is_dir()

    response = client.delete("/api/panels/core.base.fallback/override")
    assert response.status_code == 200
    body = response.json()
    assert body["removed_tier"] == "project"
    assert body["restored_tier"] == "core"
    assert not (opened_project / "panels" / "core.base.fallback").exists()

    restored = client.get("/api/panels/core.base.fallback/source").json()
    assert restored["tier"] == "core"
    assert restored["source"] == original


def test_reverting_a_panel_that_shadows_nothing_is_refused(client: TestClient, opened_project: Path) -> None:
    _write_project_panel(opened_project, "probe.only")
    assert client.post("/api/panels/reload").status_code == 200

    response = client.delete("/api/panels/probe.only/override")
    assert response.status_code == 409
    assert "shadows nothing" in response.json()["detail"]
    assert (opened_project / "panels" / "probe.only").is_dir()


def test_saving_a_declaration_that_renames_the_panel_is_refused(client: TestClient, opened_project: Path) -> None:
    """FR-027: the id is what makes a copy take effect, so it is pinned."""
    directory = _write_project_panel(opened_project, "probe.rename")
    assert client.post("/api/panels/reload").status_code == 200
    renamed = json.dumps({**json.loads((directory / "panel.json").read_text(encoding="utf-8")), "panel_id": "other"})

    response = client.put(
        "/api/panels/probe.rename/source",
        json={"source": "<!doctype html>x\n", "declaration": renamed},
    )
    assert response.status_code == 400
    assert "keep the panel id" in response.json()["detail"]
    assert (directory / "index.html").read_text(encoding="utf-8") == DOCUMENT


@pytest.mark.parametrize("panel_id", ["..", "%2e%2e", "no.such.panel"])
def test_the_editing_routes_refuse_an_unusable_panel_id(client: TestClient, panel_id: str) -> None:
    for response in (
        client.get(f"/api/panels/{panel_id}/source"),
        client.put(f"/api/panels/{panel_id}/source", json={"source": DOCUMENT}),
        client.delete(f"/api/panels/{panel_id}/override"),
    ):
        assert response.status_code in {400, 404}


# ---------------------------------------------------------------------------
# FR-049: the choice is recorded per type and per capability
# ---------------------------------------------------------------------------


def test_a_choice_is_recorded_per_capability(client: TestClient, opened_project: Path) -> None:
    """FR-049: choosing a panel for looking at a frame must not disable producing.

    One slot for both would make setting a display default silently remove the
    person's ability to produce from that type.
    """
    _write_project_panel(opened_project, "probe.display", capability="displaying")
    _write_project_panel(opened_project, "probe.produce", capability="producing")
    assert client.post("/api/panels/reload").status_code == 200

    assert (
        client.put(
            "/api/panels/choices/DataFrame",
            json={"panel_id": "probe.display", "scope": "user", "capability": "displaying"},
        ).status_code
        == 200
    )
    body = client.put(
        "/api/panels/choices/DataFrame",
        json={"panel_id": "probe.produce", "scope": "user", "capability": "producing"},
    ).json()

    recorded = {(entry["capability"], entry["target_type"]): entry["panel_id"] for entry in body["choices"]}
    assert recorded[("displaying", "DataFrame")] == "probe.display"
    assert recorded[("producing", "DataFrame")] == "probe.produce"

    # Clearing one leaves the other standing.
    cleared = client.delete(
        "/api/panels/choices/DataFrame", params={"scope": "user", "capability": "displaying"}
    ).json()
    remaining = {(entry["capability"], entry["target_type"]) for entry in cleared["choices"]}
    assert ("displaying", "DataFrame") not in remaining
    assert ("producing", "DataFrame") in remaining


def test_an_unknown_capability_is_refused(client: TestClient) -> None:
    response = client.delete("/api/panels/choices/DataFrame", params={"capability": "inventing"})
    assert response.status_code == 400
    assert "Unknown capability" in response.json()["detail"]
