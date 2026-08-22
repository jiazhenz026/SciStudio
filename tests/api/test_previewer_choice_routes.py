"""The previewer-choice API (#2049).

Routing behaviour lives in `tests/previewers/test_previewer_choice.py`. What
these tests own is the surface: which layer a write lands in, what the listing
reports about provenance and staleness, what is refused, and — the point of the
feature — that a recorded choice actually changes what a preview session
resolves to.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_PREVIEWER = """\
from scistudio.previewers.models import OwnerKind, PreviewerSpec


def get_previewers():
    return [
        PreviewerSpec(
            previewer_id="choice.project",
            owner_kind=OwnerKind.PROJECT,
            owner_name="probe",
            target_type="DataFrame",
            priority=90,
        ),
        PreviewerSpec(
            previewer_id="choice.alternate",
            owner_kind=OwnerKind.PROJECT,
            owner_name="probe",
            target_type="DataFrame",
            priority=10,
        ),
    ]
"""


def _install_previewers(project: Path, client: TestClient) -> None:
    previewers = project / "previewers"
    previewers.mkdir(parents=True, exist_ok=True)
    (previewers / "choice_probe.py").write_text(PROJECT_PREVIEWER, encoding="utf-8")
    assert client.post("/api/blocks/reload").status_code == 200


def _choices(client: TestClient) -> dict[str, dict]:
    response = client.get("/api/previews/choices")
    assert response.status_code == 200
    return {entry["target_type"]: entry for entry in response.json()["choices"]}


# -- listing -----------------------------------------------------------------


def test_no_choices_recorded_is_an_empty_list(client: TestClient, opened_project: Path) -> None:
    assert _choices(client) == {}


def test_a_user_scoped_choice_reports_its_scope(client: TestClient, opened_project: Path) -> None:
    _install_previewers(opened_project, client)
    response = client.put(
        "/api/previews/choices/DataFrame",
        json={"previewer_id": "choice.alternate", "scope": "user"},
    )
    assert response.status_code == 200

    entry = _choices(client)["DataFrame"]
    assert entry["previewer_id"] == "choice.alternate"
    assert entry["scope"] == "user"
    assert entry["available"] is True


def test_a_project_scoped_choice_overrides_the_user_one(client: TestClient, opened_project: Path) -> None:
    _install_previewers(opened_project, client)
    client.put("/api/previews/choices/DataFrame", json={"previewer_id": "choice.alternate", "scope": "user"})
    client.put("/api/previews/choices/DataFrame", json={"previewer_id": "choice.project", "scope": "project"})

    entry = _choices(client)["DataFrame"]
    assert entry["previewer_id"] == "choice.project"
    assert entry["scope"] == "project"


def test_clearing_the_project_layer_reveals_the_user_choice_again(client: TestClient, opened_project: Path) -> None:
    """The two layers stack rather than replace: clearing the override restores
    what it was overriding, instead of leaving the type unchosen."""
    _install_previewers(opened_project, client)
    client.put("/api/previews/choices/DataFrame", json={"previewer_id": "choice.alternate", "scope": "user"})
    client.put("/api/previews/choices/DataFrame", json={"previewer_id": "choice.project", "scope": "project"})

    assert client.delete("/api/previews/choices/DataFrame", params={"scope": "project"}).status_code == 200

    entry = _choices(client)["DataFrame"]
    assert entry["previewer_id"] == "choice.alternate"
    assert entry["scope"] == "user"


def test_a_choice_whose_previewer_is_gone_reads_as_unavailable(client: TestClient, opened_project: Path) -> None:
    """A choice outlives the package that provided it. Reporting it as stale is
    more useful than dropping it, because reinstalling should bring it back."""
    _install_previewers(opened_project, client)
    client.put("/api/previews/choices/DataFrame", json={"previewer_id": "choice.alternate", "scope": "user"})

    (opened_project / "previewers" / "choice_probe.py").unlink()
    # /api/blocks/reload rather than the previewer-owned endpoint (#2095): this
    # branch must merge in either order, so it depends only on what main has.
    assert client.post("/api/blocks/reload").status_code == 200

    entry = _choices(client)["DataFrame"]
    assert entry["previewer_id"] == "choice.alternate"
    assert entry["available"] is False


# -- refusals ----------------------------------------------------------------


def test_choosing_an_unknown_previewer_is_refused(client: TestClient, opened_project: Path) -> None:
    """Routing tolerates a previewer that has since disappeared; accepting one
    that never existed would store a preference that can never apply."""
    response = client.put(
        "/api/previews/choices/DataFrame",
        json={"previewer_id": "never.existed", "scope": "user"},
    )
    assert response.status_code == 400
    assert "never.existed" in response.json()["detail"]


def test_an_unknown_scope_is_refused_and_names_the_known_ones(client: TestClient, opened_project: Path) -> None:
    _install_previewers(opened_project, client)
    response = client.put(
        "/api/previews/choices/DataFrame",
        json={"previewer_id": "choice.alternate", "scope": "global"},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "project" in detail and "user" in detail


def test_clearing_a_type_that_was_never_chosen_succeeds(client: TestClient, opened_project: Path) -> None:
    assert client.delete("/api/previews/choices/NeverChosen", params={"scope": "user"}).status_code == 200


# -- persistence -------------------------------------------------------------


def test_a_project_scoped_choice_lands_in_the_project(client: TestClient, opened_project: Path) -> None:
    _install_previewers(opened_project, client)
    client.put("/api/previews/choices/DataFrame", json={"previewer_id": "choice.alternate", "scope": "project"})

    path = opened_project / ".scistudio" / "previewer-choices.json"
    assert path.is_file()
    assert json.loads(path.read_text(encoding="utf-8"))["choices"] == {"DataFrame": "choice.alternate"}


def test_the_author_declared_manifest_is_a_separate_file(client: TestClient, opened_project: Path) -> None:
    """FR-005's ``previewers.json`` is an author's declaration about a project;
    a choice is a person's preference about their own view. Writing a choice
    must not touch the manifest."""
    _install_previewers(opened_project, client)
    client.put("/api/previews/choices/DataFrame", json={"previewer_id": "choice.alternate", "scope": "project"})

    assert not (opened_project / ".scistudio" / "previewers.json").exists()


# -- the point of the feature ------------------------------------------------


def test_a_choice_changes_what_a_preview_session_resolves_to(client: TestClient, opened_project: Path) -> None:
    """End to end: without a choice the ladder picks the higher priority spec;
    with one, the session comes back from the chosen previewer instead."""
    _install_previewers(opened_project, client)
    upload = client.post("/api/data/upload", files={"file": ("t.csv", b"a,b\n1,2\n", "text/csv")})
    ref = upload.json()["ref"]

    def resolved() -> str:
        response = client.post(
            "/api/previews/sessions",
            json={
                "target": {
                    "kind": "data_ref",
                    "ref": ref,
                    "recorded_type": "DataFrame",
                    "type_chain": ["DataObject", "DataFrame"],
                },
                "query": {},
            },
        )
        assert response.status_code == 200
        return str(response.json()["previewer_id"])

    assert resolved() == "choice.project"

    assert (
        client.put(
            "/api/previews/choices/DataFrame",
            json={"previewer_id": "choice.alternate", "scope": "user"},
        ).status_code
        == 200
    )

    assert resolved() == "choice.alternate"


def test_clearing_the_choice_returns_routing_to_the_ladder(client: TestClient, opened_project: Path) -> None:
    _install_previewers(opened_project, client)
    client.put("/api/previews/choices/DataFrame", json={"previewer_id": "choice.alternate", "scope": "user"})
    assert client.delete("/api/previews/choices/DataFrame", params={"scope": "user"}).status_code == 200

    upload = client.post("/api/data/upload", files={"file": ("t.csv", b"a,b\n1,2\n", "text/csv")})
    response = client.post(
        "/api/previews/sessions",
        json={
            "target": {
                "kind": "data_ref",
                "ref": upload.json()["ref"],
                "recorded_type": "DataFrame",
                "type_chain": ["DataObject", "DataFrame"],
            },
            "query": {},
        },
    )
    assert response.json()["previewer_id"] == "choice.project"
