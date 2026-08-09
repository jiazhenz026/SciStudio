"""Tutorial projects: registered, marked, hidden from one listing, operable.

``docs/specs/adr-053-learning-center.md`` FR-062 to FR-069, and the FR-073
promise that clearing leaves user projects alone.

The tension these tests hold is the whole design. FR-063 requires a tutorial
project to be in the known-projects registry, because several routes — including
the path-containment check in ``api/routes/projects.py`` — resolve a project's
real path through it, so an unregistered one could not be operated at all.
FR-065 requires it to be absent from the listing that feeds the recent-project
list, the projects dropdown, and the welcome pane. Registered and invisible at
the same time is what the marker plus one route-level filter buys, and what
breaks if either half moves.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scistudio.api.runtime import ApiRuntime
from scistudio.core import dropins
from scistudio.tutorials import projects as tutorial_projects
from scistudio.tutorials.projects import TutorialKey

WELCOME = TutorialKey.core("welcome-to-scistudio")


def _start_tutorial_project(runtime: ApiRuntime, key: TutorialKey = WELCOME, title: str = "Welcome To SciStudio"):
    """Create one tutorial project the way the Learning Center will.

    The plan comes from the tutorial layer and the creation from the runtime,
    which is the split the checklist's ``api -> tutorials`` one-way edge forces:
    the tutorial package decides where the project goes and what marks it, and
    only the API layer can call ``create_project``.
    """
    plan = tutorial_projects.plan_tutorial_project(key, title)
    tutorial_projects.ensure_tutorial_parent()
    tutorial_projects.ensure_scoped_library()
    return plan, runtime.create_project(
        plan.name,
        plan.description,
        str(plan.parent),
        dir_name=plan.dir_name,
        tutorial_source_kind=key.source_kind,
        tutorial_source_id=key.source_id,
        tutorial_id=key.tutorial_id,
    )


@pytest.fixture
def user_project(client: TestClient, project_parent: Path) -> dict:
    """A project of the user's own, stored outside the tutorial parent."""
    response = client.post(
        "/api/projects/",
        json={"name": "My Analysis", "description": "real work", "path": str(project_parent)},
    )
    assert response.status_code == 200
    return response.json()


# ---------------------------------------------------------------------------
# FR-062 / FR-063 / FR-064 — created, registered, marked
# ---------------------------------------------------------------------------


def test_a_tutorial_project_is_created_under_the_tutorial_parent(client: TestClient, runtime: ApiRuntime) -> None:
    """FR-062: one dedicated parent, the location the product already used."""
    plan, project = _start_tutorial_project(runtime)

    assert Path(project.path) == plan.path
    assert Path(project.path).parent == dropins.tutorial_parent_dir()
    assert (Path(project.path) / "project.yaml").is_file()


def test_a_tutorial_project_is_recorded_in_the_known_projects_registry(client: TestClient, runtime: ApiRuntime) -> None:
    """FR-063: without the entry, the routes that resolve paths through it fail."""
    _, project = _start_tutorial_project(runtime)

    assert project.id in runtime.known_projects
    persisted = json.loads(runtime.known_projects_path.read_text(encoding="utf-8"))
    entry = next(item for item in persisted["projects"] if item["id"] == project.id)
    assert entry["tutorial_source_kind"] == "core"
    assert entry["tutorial_id"] == "welcome-to-scistudio"


def test_the_marker_carries_the_tutorial_identity(client: TestClient, runtime: ApiRuntime) -> None:
    """FR-064 with FR-019: which tutorial, not merely that it is one.

    Restarting has to delete the previous project *of that tutorial* (FR-066)
    and progress is keyed the same way (FR-075), so a boolean would not do.
    """
    _, project = _start_tutorial_project(runtime)

    assert tutorial_projects.tutorial_key_of(project) == WELCOME
    assert tutorial_projects.is_tutorial_entry(project) is True
    assert tutorial_projects.find_tutorial_project(runtime.known_projects.values(), WELCOME) is project


def test_a_user_project_carries_no_marker(client: TestClient, user_project: dict, runtime: ApiRuntime) -> None:
    entry = runtime.known_projects[user_project["id"]]

    assert tutorial_projects.tutorial_key_of(entry) is None
    assert tutorial_projects.is_tutorial_entry(entry) is False


def test_a_projects_file_written_before_the_marker_existed_still_loads(
    client: TestClient, runtime: ApiRuntime, project_parent: Path
) -> None:
    """Adding fields to ``KnownProject`` must not break an existing install.

    ``_load_known_projects`` builds entries with ``KnownProject(**entry)``, so
    the three marker fields have to default rather than be required.
    """
    legacy = project_parent / "legacy"
    (legacy / ".scistudio").mkdir(parents=True)
    (legacy / "project.yaml").write_text("project:\n  id: project-legacy\n  name: Legacy\n", encoding="utf-8")
    runtime.known_projects_path.write_text(
        json.dumps(
            {
                "projects": [
                    {
                        "id": "project-legacy",
                        "name": "Legacy",
                        "path": str(legacy),
                        "description": "",
                        "last_opened": "2026-01-01T00:00:00+00:00",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    runtime._load_known_projects()

    entry = runtime.known_projects["project-legacy"]
    assert entry.tutorial_source_kind is None
    assert tutorial_projects.is_tutorial_entry(entry) is False
    assert [item["name"] for item in client.get("/api/projects/").json()] == ["Legacy"]


def test_the_marker_survives_re_adoption_by_path(client: TestClient, runtime: ApiRuntime) -> None:
    """The marker is written into the project as well as into the registry.

    A tutorial project re-adopted after its registry entry was lost must not
    reappear in the listing surfaces FR-065 keeps it out of.
    """
    _, project = _start_tutorial_project(runtime)
    path = project.path
    runtime.known_projects.pop(project.id)
    runtime._save_known_projects()

    readopted = runtime.open_project(path)

    assert tutorial_projects.tutorial_key_of(readopted) == WELCOME
    assert client.get("/api/projects/").json() == []


# ---------------------------------------------------------------------------
# FR-065 — absent from the listing, operable everywhere else
# ---------------------------------------------------------------------------


def test_a_tutorial_project_is_absent_from_the_project_listing(
    client: TestClient, runtime: ApiRuntime, user_project: dict
) -> None:
    """FR-065: the one response behind all three surfaces excludes it."""
    _, project = _start_tutorial_project(runtime)

    listed = client.get("/api/projects/").json()

    assert [item["id"] for item in listed] == [user_project["id"]]
    assert project.id not in {item["id"] for item in listed}


def test_a_tutorial_project_is_operable_through_every_other_route(client: TestClient, runtime: ApiRuntime) -> None:
    """FR-065's second half — and FR-063's reason.

    Open, update, read a file, write a file, and delete: each of these resolves
    the project through ``known_projects``, which is why the marker hides the
    entry from one listing rather than removing it from the registry.
    """
    _, project = _start_tutorial_project(runtime)

    opened = client.get(f"/api/projects/{project.id}")
    assert opened.status_code == 200, opened.text
    assert opened.json()["path"] == project.path

    updated = client.put(f"/api/projects/{project.id}", json={"description": "renamed mid-tutorial"})
    assert updated.status_code == 200, updated.text

    read = client.get(f"/api/projects/{project.id}/file", params={"path": "workflows/main.yaml"})
    assert read.status_code == 200, read.text

    written = client.put(
        f"/api/projects/{project.id}/file",
        params={"path": "workflows/main.yaml"},
        json={"content": read.json()["content"]},
    )
    assert written.status_code == 200, written.text

    deleted = client.delete(f"/api/projects/{project.id}")
    assert deleted.status_code == 204, deleted.text
    assert not Path(project.path).exists()


# ---------------------------------------------------------------------------
# FR-066 / FR-067 — restart deletes and recreates
# ---------------------------------------------------------------------------


def test_restart_names_the_directory_before_anything_is_deleted(client: TestClient, runtime: ApiRuntime) -> None:
    """FR-067: the confirmation's data is the directory itself.

    The label says "restart" while the effect is deleting a folder, and the user
    is entitled to see which one.
    """
    _, project = _start_tutorial_project(runtime)

    named = tutorial_projects.restart_preview(runtime.known_projects.values(), WELCOME)

    assert named == Path(project.path)
    assert named.is_dir(), "naming the directory must not delete it"


def test_restart_deletes_the_previous_project_and_recreates_it_in_place(
    client: TestClient, runtime: ApiRuntime
) -> None:
    """FR-066: deleted and recreated at the same location, with no serial suffix.

    The serial-suffix naming the single-tutorial implementation used for repeat
    runs is gone with it, so a user who restarts six times has one directory
    rather than six.
    """
    plan, first = _start_tutorial_project(runtime)
    (Path(first.path) / "data" / "raw" / "user-edit.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    assert tutorial_projects.delete_tutorial_project(first.path) is True
    runtime.known_projects.pop(first.id, None)
    runtime._save_known_projects()
    assert not Path(first.path).exists()

    _, second = _start_tutorial_project(runtime)

    assert Path(second.path) == plan.path == Path(first.path)
    assert second.id != first.id
    assert not (Path(second.path) / "data" / "raw" / "user-edit.csv").exists()
    assert list(dropins.tutorial_parent_dir().glob("welcome-to-scistudio*")) == [plan.path]


def test_two_tutorials_get_two_directories(client: TestClient, runtime: ApiRuntime) -> None:
    """FR-019 on disk: identity is the pair of source and id."""
    first = TutorialKey("package", "scistudio-blocks-imaging", "intro")
    second = TutorialKey("package", "scistudio-blocks-lcms", "intro")

    _, one = _start_tutorial_project(runtime, first, "Imaging Intro")
    _, two = _start_tutorial_project(runtime, second, "LC-MS Intro")

    assert one.path != two.path
    assert tutorial_projects.find_tutorial_project(runtime.known_projects.values(), first) is one
    assert tutorial_projects.find_tutorial_project(runtime.known_projects.values(), second) is two


# ---------------------------------------------------------------------------
# FR-069 — deleted outside the product
# ---------------------------------------------------------------------------


def test_a_project_removed_outside_the_product_reads_as_gone(client: TestClient, runtime: ApiRuntime) -> None:
    """FR-069: the check the session invalidates itself on.

    ``project.yaml`` is the same evidence ``list_projects`` prunes stale entries
    on, so the session and the registry agree about what "gone" means.
    """
    _, project = _start_tutorial_project(runtime)
    assert tutorial_projects.tutorial_project_exists(project.path) is True

    shutil.rmtree(project.path)

    assert tutorial_projects.tutorial_project_exists(project.path) is False
    assert tutorial_projects.restart_preview(runtime.known_projects.values(), WELCOME) is None


def test_a_gutted_project_directory_also_reads_as_gone(client: TestClient, runtime: ApiRuntime) -> None:
    """A directory without ``project.yaml`` is not a project any route can open."""
    _, project = _start_tutorial_project(runtime)

    (Path(project.path) / "project.yaml").unlink()

    assert tutorial_projects.tutorial_project_exists(project.path) is False


# ---------------------------------------------------------------------------
# FR-073 — clearing leaves the user's own work alone
# ---------------------------------------------------------------------------


def test_clearing_removes_tutorial_projects_and_leaves_user_projects_listed(
    client: TestClient, runtime: ApiRuntime, user_project: dict
) -> None:
    """User Story 6, acceptance 3, end to end through the listing route."""
    _, project = _start_tutorial_project(runtime)
    library = dropins.tutorial_library_dir()

    preview = tutorial_projects.clear_preview()
    assert set(preview) == {Path(project.path), library}

    deleted = tutorial_projects.clear_tutorial_data()

    assert set(deleted) == {Path(project.path), library}
    assert not Path(project.path).exists()
    assert Path(user_project["path"]).is_dir()
    # The pruning pass drops the entry whose directory has gone, so the user's
    # project is what remains listed.
    assert [item["id"] for item in client.get("/api/projects/").json()] == [user_project["id"]]


# ---------------------------------------------------------------------------
# FR-081 — nothing is gated on progress
# ---------------------------------------------------------------------------


def _collect_route_paths(routes: object, prefix: str = "") -> set[str]:
    """Recursively collect route paths, tolerant of Starlette's two layouts.

    Starlette < 1.3 flattens ``include_router`` children straight into
    ``app.routes``, each exposing ``.path``. Starlette >= 1.3, pulled in by
    FastAPI 0.138, instead inserts one ``_IncludedRouter`` with no ``.path``,
    putting the real routes under ``route.original_router.routes`` and the mount
    prefix under ``route.include_context.prefix`` (#1769).

    Reading ``.path`` alone therefore finds nothing on a newer Starlette and the
    assertion below fails for a dependency version rather than for a missing
    route — which is what happened: this test passed locally and failed in the
    CI-equivalent environment, where the pin is newer. The same walker lives in
    ``tests/contracts/test_runtime_import_contract.py`` for the same reason.
    """
    paths: set[str] = set()
    for route in routes:  # type: ignore[attr-defined,union-attr]
        path = getattr(route, "path", None)
        if path is not None:
            paths.add(prefix + path)
        included = getattr(route, "original_router", None)
        if included is not None:
            context = getattr(route, "include_context", None)
            nested_prefix = prefix + (getattr(context, "prefix", "") or "")
            paths |= _collect_route_paths(getattr(included, "routes", ()), nested_prefix)
    return paths


def test_the_work_import_entry_exists_with_no_tutorials_completed(client: TestClient) -> None:
    """FR-081 / User Story 5, acceptance 3.

    The unlock decides when the product volunteers the offer, never whether the
    surface exists. The route is registered on a fresh install with no recorded
    progress at all.
    """
    assert "/api/work-import/sessions" in _collect_route_paths(client.app.routes)
