"""``create_app`` mounts the Explore Session API, above the SPA catch-all (#2240).

ADR-054 spec 3 (``docs/specs/adr-054-explore-session.md``) FR-056 gives every
session operation a route. Those routes existed and nothing included them, so
the whole API was dead code in the running application. One line in
``create_app`` fixes that, and the line has a position as well as a body.

**Why the position is tested against the route table and not only against a
request.** ``create_app`` mounts ``SPAStaticFiles`` at ``/`` last. That mount
matches every path, ``/api/explore/...`` included, and answers it with the SPA's
own 404 — so a router included after it is registered where nothing can reach
it. But the mount exists only when a built frontend is present: in a checkout
with no ``frontend/dist`` there is nothing at ``/`` to shadow anything, and a
request-based test passes on the broken ordering. That is not hypothetical.
These routes' first test suite was green for hours on a machine with no built
frontend and 404'd on every case the moment a ``frontend/dist`` appeared.

So the ordering is pinned twice and the two claims are different:

* :func:`test_the_explore_router_sits_above_the_spa_mount` states the *rule*
  against the route table, and fails if the ``include_router`` call moves below
  the mount regardless of what is built in this checkout.
* :func:`test_an_explore_route_answers_with_a_spa_mounted` proves the
  *behaviour* with a real SPA on disk, and
  :func:`test_the_spa_mount_swallows_a_route_registered_after_it` proves that
  behaviour is not vacuous by showing the mount really does swallow the same
  route when it comes first.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Mount

from scistudio.api import app as app_module
from scistudio.api.routes import explore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _built_spa(root: Path) -> Path:
    """A minimal built frontend, so ``create_app`` really mounts ``SPAStaticFiles``."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.html").write_text("<!doctype html><html><body>SPA</body></html>", encoding="utf-8")
    return root


def _app_with_spa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """``create_app()`` with a built SPA present, whatever this checkout contains."""
    spa = _built_spa(tmp_path / "frontend" / "dist")
    monkeypatch.setattr(app_module, "_resolve_spa_static_dir", lambda: spa)
    return app_module.create_app()


def _explore_route_indices(app: FastAPI) -> list[int]:
    return [i for i, route in enumerate(app.router.routes) if getattr(route, "path", "").startswith("/api/explore")]


def _spa_mount_index(app: FastAPI) -> int | None:
    for i, route in enumerate(app.router.routes):
        if isinstance(route, Mount) and route.path in {"", "/"}:
            return i
    return None


def _isolated_client(app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """A client on *app* with an isolated SciStudio home, as ``conftest.client`` does."""
    fake_home = tmp_path / "home"
    fake_home.mkdir(exist_ok=True)
    from scistudio.api import runtime as runtime_module

    monkeypatch.setattr(runtime_module.Path, "home", classmethod(lambda cls: fake_home))
    return TestClient(app)


# ---------------------------------------------------------------------------
# The router is mounted at all (FR-056)
# ---------------------------------------------------------------------------


def test_create_app_includes_every_explore_route() -> None:
    """Every route the explore router defines exists on the application.

    Asserted over the whole router rather than one sample path, so a partial
    registration — a second router, a prefix typo — fails as loudly as none.
    """
    app = app_module.create_app()
    mounted = {getattr(route, "path", "") for route in app.router.routes}
    declared = {getattr(route, "path", "") for route in explore.router.routes}

    assert declared, "the explore router declares no routes; this test would pass vacuously"
    assert declared <= mounted, f"create_app does not mount: {sorted(declared - mounted)}"


def test_the_explore_routes_are_registered_once() -> None:
    """No duplicate registration: ``include_router(explore.router)`` is called once."""
    app = app_module.create_app()
    paths = [getattr(route, "path", "") for route in app.router.routes]
    assert paths.count("/api/explore/sessions") == 2, (  # one POST, one GET
        "expected exactly the open and list routes at /api/explore/sessions; "
        f"found {paths.count('/api/explore/sessions')} registrations"
    )


# ---------------------------------------------------------------------------
# The ordering rule (the trap)
# ---------------------------------------------------------------------------


def test_the_explore_router_sits_above_the_spa_mount(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The rule itself: every explore route precedes the ``/`` mount in the table.

    This is the test that fails if someone moves ``include_router(explore.router)``
    below the ``app.mount("/", SPAStaticFiles(...))`` call. It asserts on
    positions rather than on a response, so it holds in a checkout with no built
    frontend — where a request against a wrongly-ordered app still succeeds
    because there is no mount to shadow it.
    """
    app = _app_with_spa(tmp_path, monkeypatch)
    mount_index = _spa_mount_index(app)
    explore_indices = _explore_route_indices(app)

    assert mount_index is not None, "the SPA mount is missing; this test would prove nothing"
    assert explore_indices, "no explore routes are registered"
    assert max(explore_indices) < mount_index, (
        "an explore route is registered after the SPA catch-all mount at '/', which matches "
        "every path and answers /api/explore/... with the SPA's own 404. Move "
        "app.include_router(explore.router) up, beside the other include_router calls."
    )


def test_an_explore_route_answers_with_a_spa_mounted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The behaviour: with a built SPA present, the route still answers.

    409 is the session API's own refusal (no project is open). Anything from the
    route is the point; a 404 would be the SPA's.
    """
    app = _app_with_spa(tmp_path, monkeypatch)
    with _isolated_client(app, tmp_path, monkeypatch) as client:
        response = client.get("/api/explore/sessions")

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["error"] == "no_active_project"


def test_the_spa_mount_swallows_a_route_registered_after_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control: the same route, moved below the mount, becomes unreachable.

    Without this, the two tests above could both pass on an application where the
    SPA mount never shadowed anything, and neither would be evidence of anything.
    Here the explore routes are moved to the end of the route table — the exact
    mistake the ordering rule forbids — and the request that answered 409 above
    comes back as the SPA's 404.
    """
    app = _app_with_spa(tmp_path, monkeypatch)
    moved = [route for route in app.router.routes if getattr(route, "path", "").startswith("/api/explore")]
    for route in moved:
        app.router.routes.remove(route)
    app.router.routes.extend(moved)

    with _isolated_client(app, tmp_path, monkeypatch) as client:
        response = client.get("/api/explore/sessions")

    assert response.status_code == 404, (
        "the SPA mount did not shadow the moved routes, so the ordering rule this "
        f"module pins is untested by construction (got {response.status_code})"
    )


# ---------------------------------------------------------------------------
# Teardown (the other half of the resolved TODO(#2240))
# ---------------------------------------------------------------------------


def test_app_teardown_shuts_down_the_session_services(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Leaving the app closes every explore session, so no kernel outlives the backend.

    The services are module state in ``api.routes.explore``, not runtime state,
    so nothing else in the lifespan teardown reaches them.
    """
    calls: list[bool] = []

    class _StubService:
        def shutdown(self, *, commit: bool = False) -> None:
            calls.append(commit)

    monkeypatch.setitem(explore._services, str(tmp_path / "project"), _StubService())  # type: ignore[arg-type]

    app = app_module.create_app()
    with _isolated_client(app, tmp_path, monkeypatch):
        assert calls == [], "the services were shut down before the app was left"

    assert calls == [False], "app teardown did not shut the explore session services down"
    assert explore._services == {}, "the service registry was not cleared on teardown"


def test_teardown_survives_a_service_that_cannot_shut_down(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A session that will not close must not take the backend's teardown with it."""

    class _AngryService:
        def shutdown(self, *, commit: bool = False) -> None:
            raise RuntimeError("the kernel will not die")

    monkeypatch.setitem(explore._services, str(tmp_path / "project"), _AngryService())  # type: ignore[arg-type]

    app = app_module.create_app()
    with _isolated_client(app, tmp_path, monkeypatch):
        pass

    assert explore._services == {}


def test_retire_kernels_for_project_builds_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A project nobody has explored retires nothing and constructs no service.

    The lookup the git route calls must not be a way to accidentally start a
    session service (and its commit thread) on every branch switch.
    """
    built: list[Any] = []

    def _explode(*args: Any, **kwargs: Any) -> Any:
        built.append(args)
        raise AssertionError("retire_kernels_for_project built a session service")

    monkeypatch.setattr(explore, "_build_service", _explode)
    assert explore.retire_kernels_for_project(tmp_path / "never-explored") == ()
    assert built == []
