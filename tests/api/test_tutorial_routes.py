"""The Learning Center HTTP surface, over the real app.

``docs/specs/adr-053-learning-center.md`` §4.4's Routes row: catalogue, start,
resume, evaluate, user-interface event, leave, clear, and the removed route
returning 404 (FR-003).

These tests drive the routes rather than the runtime. ``tests/tutorials/``
already covers what the session does; what cannot be checked there is whether
the API layer supplies the four ports correctly — whether a started tutorial
really lands in the known-projects registry, whether a condition is judged
against the *product's* registries rather than a double, and whether the
responses carry the field names the frontend was written against. Every
assertion below is therefore about the seam, not about session behaviour.

Tutorials are mounted by pointing the core tier at a temporary directory, which
is how a test gets a core-tier tutorial without shipping one in the wheel. The
tier matters: FR-020a forbids a user-level or project-level manifest from
declaring a replay, so a fixture that exercises one has to be core.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from scistudio.api.runtime import ApiRuntime
from scistudio.tutorials import discovery
from scistudio.tutorials.manifest import TUTORIAL_MANIFEST_FILENAME

# ---------------------------------------------------------------------------
# Mounting tutorials
# ---------------------------------------------------------------------------


@pytest.fixture
def core_tier(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the core tutorial tier at an empty temporary directory.

    Replaces what SciStudio ships rather than adding to it, so a test's
    catalogue holds exactly the tutorials that test wrote and the shipped
    tutorial's own content cannot make an assertion pass or fail.
    """
    directory = tmp_path / "core-tutorials"
    directory.mkdir()
    monkeypatch.setattr(discovery, "core_tutorials_dir", lambda: directory)
    return directory


def mount(core: Path, tutorial_id: str, manifest: dict[str, Any], files: dict[str, str] | None = None) -> Path:
    """Write one tutorial into the core tier and return its directory."""
    directory = core / tutorial_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / TUTORIAL_MANIFEST_FILENAME).write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    for relative, content in (files or {}).items():
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return directory


def manifest_for(tutorial_id: str, steps: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    """A minimal valid manifest carrying *steps*."""
    return {
        "manifest_version": 1,
        "id": tutorial_id,
        "title": tutorial_id.replace("-", " ").title(),
        "summary": f"Fixture tutorial {tutorial_id}.",
        "steps": steps,
        **extra,
    }


BOOTSTRAP: dict[str, Any] = {"bootstrap": {"project_name": "Fixture Project"}}


def start(client: TestClient, tutorial_id: str, *, restart: bool = False) -> Any:
    return client.post(
        "/api/tutorials/sessions",
        json={"source_kind": "core", "source_id": "", "tutorial_id": tutorial_id, "restart": restart},
    )


def step_id(payload: dict[str, Any]) -> str | None:
    step = payload.get("step")
    return None if step is None else str(step["id"])


# ---------------------------------------------------------------------------
# FR-003 — the removed route
# ---------------------------------------------------------------------------


def test_the_bootstrap_route_is_removed_rather_than_aliased(client: TestClient) -> None:
    """FR-003: the old hardcoded-tutorial route is gone, not redirected.

    It judged by reading the frontend's copy of the workflow, which is the
    assumption this whole design replaces; an alias would leave two judging
    paths that can disagree, so the route has to return 404.
    """
    response = client.post("/api/tutorials/run-first-workflow/bootstrap", json={})

    assert response.status_code == 404, response.text


# ---------------------------------------------------------------------------
# The catalogue
# ---------------------------------------------------------------------------


def test_the_catalogue_groups_tutorials_by_source_and_reports_its_own_counts(
    client: TestClient, core_tier: Path
) -> None:
    """One group per source, each carrying only its own counts (FR-076)."""
    mount(core_tier, "first", manifest_for("first", [{"id": "one", "say": "One."}]))
    mount(core_tier, "second", manifest_for("second", [{"id": "one", "say": "One."}]))

    payload = client.get("/api/tutorials/catalogue").json()

    assert [group["source_kind"] for group in payload["groups"]] == ["core"]
    group = payload["groups"][0]
    assert group["source_id"] == ""
    assert (group["completed"], group["total"]) == (0, 2)
    assert sorted(entry["id"] for entry in group["tutorials"]) == ["first", "second"]
    assert payload["active"] is None


def test_the_catalogue_always_carries_a_diagnostics_list(client: TestClient, core_tier: Path) -> None:
    """``diagnostics`` is a list even when nothing went wrong.

    The Learning Center reads ``catalogue.diagnostics.length`` without guarding
    it, unlike ``groups``, so a null or absent value throws during render rather
    than showing an empty panel.
    """
    payload = client.get("/api/tutorials/catalogue").json()

    assert payload["diagnostics"] == []


def test_an_entry_carries_every_field_the_learning_center_renders(client: TestClient, core_tier: Path) -> None:
    """The row shape of checklist §6.1.6, field for field."""
    mount(
        core_tier,
        "covered",
        manifest_for("covered", [{"id": "one", "say": "One."}], order=3, cover="assets/cover.png"),
        files={"assets/cover.png": "not really a png"},
    )

    entry = client.get("/api/tutorials/catalogue").json()["groups"][0]["tutorials"][0]

    assert entry == {
        "source_kind": "core",
        "source_id": "",
        "id": "covered",
        "title": "Covered",
        "summary": "Fixture tutorial covered.",
        "cover_url": "/api/tutorials/core//covered/cover",
        "order": 3,
        "state": "not_started",
        "unavailable_reason": None,
        "project_directory": None,
        # True because this fixture's single step waits on nothing but the
        # reader — see `TutorialManifest.is_reading_only`, which derives the
        # answer from the steps rather than from a declared field.
        "reading": True,
    }


def test_an_unavailable_tutorial_is_listed_with_its_reason(client: TestClient, core_tier: Path) -> None:
    """FR-024: a tutorial whose requirements are unmet is still listed.

    A user cannot decide whether to install a package whose teaching material is
    invisible until after installing it.
    """
    mount(
        core_tier,
        "needs-a-package",
        manifest_for(
            "needs-a-package",
            [{"id": "one", "say": "One."}],
            requires={"packages": ["scistudio-blocks-definitely-not-installed"]},
        ),
    )

    entry = client.get("/api/tutorials/catalogue").json()["groups"][0]["tutorials"][0]

    assert entry["state"] == "unavailable"
    assert "scistudio-blocks-definitely-not-installed" in (entry["unavailable_reason"] or "")


# ---------------------------------------------------------------------------
# Starting, resuming, restarting
# ---------------------------------------------------------------------------


def test_starting_a_tutorial_creates_a_registered_project_and_reports_its_id(
    client: TestClient, runtime: ApiRuntime, core_tier: Path
) -> None:
    """FR-062, FR-063: the project exists, is registered, and the id is reported.

    ``SessionView`` carries only the path — the tutorial package cannot reach
    the known-projects registry — so the id in the response is the one thing
    here that proves the route resolved it rather than inventing it.
    """
    mount(core_tier, "makes-a-project", manifest_for("makes-a-project", [{"id": "one", "say": "One."}], **BOOTSTRAP))

    payload = start(client, "makes-a-project").json()

    assert payload["status"] == "active"
    assert payload["project_path"] is not None
    assert Path(payload["project_path"]).is_dir()
    assert payload["project_id"] in runtime.known_projects
    entry = runtime.known_projects[payload["project_id"]]
    assert (entry.tutorial_source_kind, entry.tutorial_source_id, entry.tutorial_id) == ("core", "", "makes-a-project")


def test_a_tutorial_without_a_bootstrap_starts_without_a_project(client: TestClient, core_tier: Path) -> None:
    """FR-009: a tutorial that declares no bootstrap never needs a project."""
    mount(core_tier, "no-project", manifest_for("no-project", [{"id": "one", "say": "One."}]))

    payload = start(client, "no-project").json()

    assert payload["project_path"] is None
    assert payload["project_id"] is None


def test_starting_an_already_running_tutorial_resumes_where_it_was(client: TestClient, core_tier: Path) -> None:
    """FR-090: resuming returns the step it was on, not the first one."""
    mount(
        core_tier,
        "two-steps",
        manifest_for(
            "two-steps",
            [
                {"id": "one", "say": "One."},
                {"id": "two", "say": "Two.", "done_when": {"ui_event": {"name": "preview_expanded"}}},
            ],
        ),
    )
    assert step_id(start(client, "two-steps").json()) == "one"
    advanced = client.post("/api/tutorials/sessions/active/continue").json()
    assert step_id(advanced) == "two"

    resumed = start(client, "two-steps").json()

    assert step_id(resumed) == "two"
    assert resumed["satisfied_step_ids"] == ["one"]


def test_restarting_deletes_the_project_and_makes_a_new_one(
    client: TestClient, runtime: ApiRuntime, core_tier: Path
) -> None:
    """FR-066: restart removes the project and recreates it at the same place."""
    mount(core_tier, "restartable", manifest_for("restartable", [{"id": "one", "say": "One."}], **BOOTSTRAP))
    first = start(client, "restartable").json()
    marker = Path(first["project_path"]) / "work.txt"
    marker.write_text("the user's leftovers", encoding="utf-8")

    second = start(client, "restartable", restart=True).json()

    assert second["project_path"] == first["project_path"]
    assert not marker.exists()
    assert second["project_id"] in runtime.known_projects
    assert first["project_id"] not in runtime.known_projects


def test_a_second_tutorial_is_refused_with_a_conflict(client: TestClient, core_tier: Path) -> None:
    """FR-043: one tutorial at a time, and the refusal is a real 409.

    The status code is the contract, not just the message: the Learning Center
    branches on 409 specifically and renders it as an offer to leave the running
    tutorial rather than as an error.
    """
    mount(core_tier, "running", manifest_for("running", [{"id": "one", "say": "One."}]))
    mount(core_tier, "other", manifest_for("other", [{"id": "one", "say": "One."}]))
    start(client, "running")

    refused = start(client, "other")

    assert refused.status_code == 409, refused.text
    assert "Running" in refused.json()["detail"]


def test_an_unstartable_tutorial_is_refused_without_the_conflict_code(client: TestClient, core_tier: Path) -> None:
    """An unmet requirement is 422, never 409.

    409 is how the frontend recognises "another tutorial is running" and it
    responds by offering to leave that one. Reusing it here would offer to leave
    a session that is not the problem — and in this test there is no session at
    all.
    """
    mount(
        core_tier,
        "unavailable",
        manifest_for(
            "unavailable",
            [{"id": "one", "say": "One."}],
            requires={"packages": ["scistudio-blocks-definitely-not-installed"]},
        ),
    )

    refused = start(client, "unavailable")

    assert refused.status_code == 422, refused.text


def test_starting_a_tutorial_nothing_ships_is_a_not_found(client: TestClient, core_tier: Path) -> None:
    refused = start(client, "no-such-tutorial")

    assert refused.status_code == 422, refused.text


# ---------------------------------------------------------------------------
# Judging: evaluate, user-interface events, continue
# ---------------------------------------------------------------------------


def test_an_explicit_evaluation_satisfies_a_step_no_event_reaches(client: TestClient, core_tier: Path) -> None:
    """FR-053: the path for state that no mapped event reports.

    ``file.changed`` is filtered to the ADR-036 extension allowlist, so a
    ``file_exists`` condition on a ``.tiff`` is never event-driven. Without the
    explicit request the step would wait forever with nothing to say why.
    """
    mount(
        core_tier,
        "waits-for-a-file",
        manifest_for(
            "waits-for-a-file",
            [
                {"id": "make-it", "say": "Make it.", "done_when": {"file_exists": {"path": "data/raw/scan.tiff"}}},
                {"id": "done", "say": "Done."},
            ],
            **BOOTSTRAP,
        ),
    )
    started = start(client, "waits-for-a-file").json()
    assert step_id(started) == "make-it"
    assert client.post("/api/tutorials/sessions/active/evaluate").json()["step"]["id"] == "make-it"

    scan = Path(started["project_path"]) / "data" / "raw" / "scan.tiff"
    scan.parent.mkdir(parents=True, exist_ok=True)
    scan.write_bytes(b"II*\x00")

    assert step_id(client.post("/api/tutorials/sessions/active/evaluate").json()) == "done"


def test_a_reported_interface_event_satisfies_its_step(client: TestClient, core_tier: Path) -> None:
    """FR-052: the one completion path that starts in the frontend.

    It still arrives as backend state — the route records it and the evaluator
    reads it back like any other term.
    """
    mount(
        core_tier,
        "waits-for-a-click",
        manifest_for(
            "waits-for-a-click",
            [
                {"id": "expand", "say": "Expand it.", "done_when": {"ui_event": {"name": "preview_expanded"}}},
                {"id": "done", "say": "Done."},
            ],
        ),
    )
    assert step_id(start(client, "waits-for-a-click").json()) == "expand"

    reported = client.post("/api/tutorials/sessions/active/ui-event", json={"name": "preview_expanded"})

    assert reported.status_code == 200, reported.text
    assert step_id(reported.json()) == "done"


def test_an_unknown_interface_event_name_is_refused(client: TestClient, core_tier: Path) -> None:
    """The name set is closed (FR-052), and a typo has to fail loudly.

    Recording an unlisted name would leave a step waiting on something nothing
    will ever report, with nothing to tell the user why — the same failure
    FR-049 rejects unknown vocabulary terms at validation to avoid.
    """
    mount(core_tier, "any", manifest_for("any", [{"id": "one", "say": "One."}]))
    start(client, "any")

    refused = client.post("/api/tutorials/sessions/active/ui-event", json={"name": "invented_event"})

    assert refused.status_code == 422, refused.text
    assert "preview_expanded" in refused.json()["detail"]


def test_a_reading_step_advances_on_an_explicit_continue(client: TestClient, core_tier: Path) -> None:
    """FR-012: a step with no condition waits for the user to say go on."""
    mount(
        core_tier,
        "reading",
        manifest_for("reading", [{"id": "read-me", "say": "Read."}, {"id": "then-this", "say": "Then."}]),
    )
    started = start(client, "reading").json()
    assert started["step"]["awaiting_continue"] is True

    assert step_id(client.post("/api/tutorials/sessions/active/continue").json()) == "then-this"


def test_a_condition_is_judged_against_the_products_own_registry(client: TestClient, core_tier: Path) -> None:
    """FR-046: judged on the backend, against product state, not a double.

    ``block_registered`` names a block type that only the real block registry
    can confirm. If the product-state port were wired to anything other than the
    live registry this passes by accident or never passes at all, and either way
    the failure would not be visible in the tutorial package's own tests.
    """
    registered = sorted(block["type_name"] for block in client.get("/api/blocks/").json()["blocks"])
    assert registered, "the block registry is empty, so this test cannot judge anything"
    block_type = registered[0]
    mount(
        core_tier,
        "reads-the-registry",
        manifest_for(
            "reads-the-registry",
            [
                {
                    "id": "installed",
                    "say": "It is there.",
                    "done_when": {"block_registered": {"block_type": block_type}},
                },
                {"id": "missing", "say": "It is not.", "done_when": {"block_registered": {"block_type": "no_such"}}},
            ],
        ),
    )

    # The first step's condition is already true, so entering satisfies it
    # immediately (FR-054) and the session stops on the one that is not.
    assert step_id(start(client, "reads-the-registry").json()) == "missing"


def test_an_engine_event_advances_the_step_without_anyone_asking(
    client: TestClient, runtime: ApiRuntime, core_tier: Path
) -> None:
    """FR-050: a mapped event re-judges the active step, with no poll and no request.

    ``interactive_complete`` is the sharpest case, because it is both the event
    that records the interaction and one of the events that re-judges the step.
    The recorder has to run first or the re-judgement reads the set as it was a
    moment ago, and the step waits for an unrelated event to come along — which
    is indistinguishable, from the user's side, from a tutorial that is broken.
    """
    import asyncio

    from scistudio.engine.events import INTERACTIVE_COMPLETE, EngineEvent

    mount(
        core_tier,
        "waits-for-a-panel",
        manifest_for(
            "waits-for-a-panel",
            [
                {
                    "id": "submit-it",
                    "say": "Submit the panel.",
                    "done_when": {"interaction_completed": {"node_id": "review-1"}},
                },
                {"id": "done", "say": "Done."},
            ],
        ),
    )
    assert step_id(start(client, "waits-for-a-panel").json()) == "submit-it"

    asyncio.run(
        runtime.event_bus.emit(
            EngineEvent(event_type=INTERACTIVE_COMPLETE, block_id="review-1", data={"workflow_id": "main"})
        )
    )

    # Nothing was asked for: the session that comes back has already moved on.
    assert step_id(client.get("/api/tutorials/sessions/active").json()) == "done"


def test_serving_a_page_is_what_reaches_it(client: TestClient, core_tier: Path) -> None:
    """``page_reached`` becomes true because the page was served.

    Nothing else in the product knows a reading page was opened, so the request
    for it is the signal. The step still advances on an evaluation rather than
    on the fetch, because ``page_reached`` is one of the terms no event maps to.
    """
    mount(
        core_tier,
        "has-pages",
        manifest_for(
            "has-pages",
            [
                {"id": "read-it", "say": "Read it.", "done_when": {"page_reached": {"page": "intro"}}},
                {"id": "done", "say": "Done."},
            ],
        ),
        files={"assets/pages/intro.md": "# Introduction\n"},
    )
    assert step_id(start(client, "has-pages").json()) == "read-it"

    page = client.get("/api/tutorials/core//has-pages/pages/intro")

    assert page.status_code == 200, page.text
    assert "Introduction" in page.text
    assert step_id(client.post("/api/tutorials/sessions/active/evaluate").json()) == "done"


# ---------------------------------------------------------------------------
# Leaving
# ---------------------------------------------------------------------------


def test_leaving_preserves_the_session_and_returns_no_content(client: TestClient, core_tier: Path) -> None:
    """FR-090: leaving keeps the tutorial's position for later."""
    mount(
        core_tier,
        "leavable",
        manifest_for(
            "leavable",
            [
                {"id": "one", "say": "One."},
                {"id": "two", "say": "Two.", "done_when": {"ui_event": {"name": "preview_expanded"}}},
            ],
        ),
    )
    start(client, "leavable")
    client.post("/api/tutorials/sessions/active/continue")

    left = client.post("/api/tutorials/sessions/active/leave")

    assert left.status_code == 204
    assert not left.content
    assert client.get("/api/tutorials/sessions/active").json() is None
    assert step_id(start(client, "leavable").json()) == "two"


def test_leaving_lets_another_tutorial_start(client: TestClient, core_tier: Path) -> None:
    mount(core_tier, "first", manifest_for("first", [{"id": "one", "say": "One."}]))
    mount(core_tier, "second", manifest_for("second", [{"id": "one", "say": "One."}]))
    start(client, "first")
    assert start(client, "second").status_code == 409

    client.post("/api/tutorials/sessions/active/leave")

    assert start(client, "second").status_code == 200


def test_acting_without_a_session_is_a_not_found(client: TestClient) -> None:
    for path in ("evaluate", "continue"):
        response = client.post(f"/api/tutorials/sessions/active/{path}")
        assert response.status_code == 404, f"{path}: {response.text}"
    assert client.post("/api/tutorials/sessions/active/leave").status_code == 204


def test_a_tutorial_project_deleted_from_outside_invalidates_its_session(client: TestClient, core_tier: Path) -> None:
    """FR-069: the session is discarded and the tutorial offered from the start."""
    mount(core_tier, "fragile", manifest_for("fragile", [{"id": "one", "say": "One."}], **BOOTSTRAP))
    started = start(client, "fragile").json()

    shutil.rmtree(started["project_path"])

    assert client.get("/api/tutorials/sessions/active").json() is None
    entry = client.get("/api/tutorials/catalogue").json()["groups"][0]["tutorials"][0]
    assert entry["state"] == "not_started"


# ---------------------------------------------------------------------------
# Progress and the one unlock
# ---------------------------------------------------------------------------


def test_progress_is_reported_per_source_with_no_total_across_them(client: TestClient, core_tier: Path) -> None:
    """FR-076: each group carries its own counts and there is no aggregate."""
    mount(core_tier, "only-one", manifest_for("only-one", [{"id": "one", "say": "One."}]))

    payload = client.get("/api/tutorials/progress").json()

    assert payload == {
        "groups": [{"source_kind": "core", "source_id": "", "label": "SciStudio", "completed": 0, "total": 1}]
    }


def test_finishing_a_tutorial_counts_it_as_complete(client: TestClient, core_tier: Path) -> None:
    mount(core_tier, "short", manifest_for("short", [{"id": "one", "say": "One."}]))
    start(client, "short")

    finished = client.post("/api/tutorials/sessions/active/continue").json()

    assert finished["status"] == "complete"
    assert finished["step"] is None
    assert client.get("/api/tutorials/progress").json()["groups"][0]["completed"] == 1
    assert client.get("/api/tutorials/catalogue").json()["groups"][0]["tutorials"][0]["state"] == "complete"


def test_the_unlock_is_reported_and_can_be_dismissed(client: TestClient) -> None:
    """FR-079: the single progress-driven offer, and its once-only dismissal."""
    assert client.get("/api/tutorials/unlock").json() == {"work_import_offer_pending": False}

    dismissed = client.post("/api/tutorials/unlock/dismiss")

    assert dismissed.status_code == 204
    assert client.get("/api/tutorials/unlock").json() == {"work_import_offer_pending": False}


# ---------------------------------------------------------------------------
# Clearing (FR-073, FR-088)
# ---------------------------------------------------------------------------


def test_the_clear_confirmation_names_the_directories_it_would_delete(client: TestClient, core_tier: Path) -> None:
    """FR-088: the user agrees to something specific, not to a description."""
    mount(core_tier, "makes-a-project", manifest_for("makes-a-project", [{"id": "one", "say": "One."}], **BOOTSTRAP))
    started = start(client, "makes-a-project").json()

    directories = client.get("/api/tutorials/data/clear-preview").json()["directories"]

    assert started["project_path"] in directories


def test_clearing_removes_tutorial_projects_and_leaves_real_ones_alone(
    client: TestClient, runtime: ApiRuntime, core_tier: Path, project_parent: Path
) -> None:
    """FR-073: tutorial data goes, the user's own work does not.

    The marker is what separates them, and only ``create_project`` writes one —
    which is why this is checked through the routes with a real project present
    rather than by trusting the directory layout.
    """
    mine = client.post(
        "/api/projects/", json={"name": "My Analysis", "description": "real work", "path": str(project_parent)}
    ).json()
    mount(core_tier, "makes-a-project", manifest_for("makes-a-project", [{"id": "one", "say": "One."}], **BOOTSTRAP))
    started = start(client, "makes-a-project").json()

    cleared = client.post("/api/tutorials/data/clear", json={"confirm": True})

    assert cleared.status_code == 200, cleared.text
    assert started["project_path"] in cleared.json()["deleted_directories"]
    assert not Path(started["project_path"]).exists()
    assert started["project_id"] not in runtime.known_projects
    assert Path(mine["path"]).is_dir()
    assert mine["id"] in runtime.known_projects
    assert client.get("/api/tutorials/sessions/active").json() is None


def test_clearing_must_be_confirmed(client: TestClient) -> None:
    refused = client.post("/api/tutorials/data/clear", json={"confirm": False})

    assert refused.status_code == 400, refused.text


# ---------------------------------------------------------------------------
# Assets (FR-006, FR-014)
# ---------------------------------------------------------------------------


def test_a_cover_is_served_from_inside_the_tutorial_directory(client: TestClient, core_tier: Path) -> None:
    mount(
        core_tier,
        "covered",
        manifest_for("covered", [{"id": "one", "say": "One."}], cover="assets/cover.svg"),
        files={"assets/cover.svg": "<svg/>"},
    )

    response = client.get("/api/tutorials/core//covered/cover")

    assert response.status_code == 200, response.text
    assert response.text == "<svg/>"


def test_a_tutorial_without_a_cover_reports_that_it_has_none(client: TestClient, core_tier: Path) -> None:
    mount(core_tier, "bare", manifest_for("bare", [{"id": "one", "say": "One."}]))

    assert client.get("/api/tutorials/core//bare/cover").status_code == 404


def test_an_asset_request_cannot_escape_the_tutorial_directory(client: TestClient, core_tier: Path) -> None:
    """FR-014: containment is enforced where the path is resolved, not by the URL.

    The request is refused because the manifest resolves it and rejects the
    escape, which is the check a hand-built path would have skipped.
    """
    mount(core_tier, "has-pages", manifest_for("has-pages", [{"id": "one", "say": "One."}]))
    (core_tier / "secret.md").write_text("not yours", encoding="utf-8")

    response = client.get("/api/tutorials/core//has-pages/pages/..%2Fsecret.md")

    assert response.status_code == 404, response.text
    assert "not yours" not in response.text


def test_a_package_tutorials_assets_use_the_named_source_in_the_url(client: TestClient, core_tier: Path) -> None:
    """The four-segment path still works when ``source_id`` is not empty.

    Core's empty ``source_id`` needs a route shape of its own; this pins that
    adding it did not cost the ordinary one.
    """
    mount(core_tier, "covered", manifest_for("covered", [{"id": "one", "say": "One."}], cover="assets/c.svg"))

    assert client.get("/api/tutorials/package/some-dist/covered/cover").status_code == 404


# ---------------------------------------------------------------------------
# A step that writes a block gives the product the block, not just the file
# ---------------------------------------------------------------------------


_PROBE_BLOCK_SOURCE = (
    "from scistudio.blocks.process.process_block import ProcessBlock\n"
    "\n"
    "\n"
    "class TutorialProbeBlock(ProcessBlock):\n"
    "    name = 'Tutorial Probe'\n"
    "    type_name = 'tutorial_probe'\n"
)


def _writes_a_block(core: Path, tutorial_id: str, destination: str) -> None:
    """Mount a tutorial whose first step writes a block and waits for it to register."""
    mount(
        core,
        tutorial_id,
        manifest_for(
            tutorial_id,
            [
                {
                    "id": "we-wrote-it",
                    "say": "A block now exists in your project. Find it in the palette.",
                    "do": [{"write": {"source": "assets/code/probe.py", "destination": destination}}],
                    "done_when": {"block_registered": {"block_type": "tutorial_probe"}},
                },
                {"id": "found-it", "say": "There it is."},
            ],
            **BOOTSTRAP,
        ),
        files={"assets/code/probe.py": _PROBE_BLOCK_SOURCE},
    )


def test_a_step_that_writes_a_block_leaves_the_product_holding_the_block(client: TestClient, core_tier: Path) -> None:
    """FR-059, for a claim only the registry can make true.

    The step writes ``blocks/probe.py`` and says "find it in the palette". Its
    own condition is ``block_registered``, so the step can only be satisfied if
    the *registry* has the block by the time the step is revealed — a file on
    disk is not enough, and was not enough: the scan happens when a project is
    opened or when the palette's Reload button is pressed, neither of which a
    tutorial step does.

    Entry satisfies the condition immediately (FR-054), so a passing run lands
    on the following step. Without the re-scan the session sits on
    ``we-wrote-it`` forever, with the user looking at a palette that does not
    contain what the step is telling them to find.
    """
    _writes_a_block(core_tier, "writes-a-block", "blocks/probe.py")

    assert step_id(start(client, "writes-a-block").json()) == "found-it"


def test_the_palette_lists_the_block_the_step_wrote(client: TestClient, core_tier: Path) -> None:
    """The same fact from the surface the user is looking at."""
    before = client.get("/api/blocks/").json()["blocks"]
    assert not any(block["type_name"] == "tutorial_probe" for block in before)

    _writes_a_block(core_tier, "writes-a-block", "blocks/probe.py")
    start(client, "writes-a-block")

    after = client.get("/api/blocks/").json()["blocks"]
    probe = next(block for block in after if block["type_name"] == "tutorial_probe")
    assert probe["base_category"] == "process"


def test_only_a_write_into_a_scanned_directory_asks_for_a_re_scan(tmp_path: Path) -> None:
    """Which writes are worth a registry re-scan.

    Tested as the predicate rather than through a route, deliberately: dropping
    the guard changes no outcome, because a ``.py`` file under ``data/`` is not
    scanned as a block whether or not the registries refresh. What it changes is
    that every copied CSV pays for a full re-scan and broadcasts
    ``blocks.reloaded`` to every client — a bootstrap copying a data directory
    would do it once per file. A route test would pass either way and would
    quietly stop protecting anything.

    The prefix case is the one worth writing down: ``blocksmith/`` starts with
    ``blocks`` and is not it.
    """
    from scistudio.api.routes.tutorials import _wrote_into_a_scanned_dir

    project = tmp_path / "proj"
    (project / "blocks").mkdir(parents=True)
    (project / "types").mkdir()
    (project / "data" / "raw").mkdir(parents=True)
    (project / "blocksmith").mkdir()

    def wrote(*relatives: str) -> bool:
        paths = [project / relative for relative in relatives]
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
        return _wrote_into_a_scanned_dir(paths, project_dir=project)

    assert wrote("blocks/probe.py") is True
    assert wrote("types/spectrum.py") is True
    # One block among data files is still a block.
    assert wrote("data/raw/cells.csv", "blocks/probe.py") is True

    assert wrote("data/raw/cells.csv") is False
    assert wrote("data/raw/probe.py") is False
    assert wrote("blocksmith/probe.py") is False
    assert _wrote_into_a_scanned_dir([tmp_path / "elsewhere" / "probe.py"], project_dir=project) is False
    # No project means nothing to be inside of.
    assert _wrote_into_a_scanned_dir([project / "blocks" / "probe.py"], project_dir=None) is False
