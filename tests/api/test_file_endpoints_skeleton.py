"""ADR-036 §3.2 — file route-ordering regression tests.

The xfail skeletons that lived here have been replaced by the real
implementation tests in :mod:`tests.api.test_file_endpoints` (Phase 2A,
I36a). The route-ordering regression tests below remain — they MUST keep
passing through the implementation phase to guard against the audit
P1-1 finding (FastAPI route declaration order).
"""

from __future__ import annotations

from typing import ClassVar


def test_file_route_registered_before_catch_all() -> None:
    """``/{project_id:path}/file`` MUST appear before ``/{project_id:path}``.

    FastAPI matches routes in declaration order. If this test fails,
    requests to GET/PUT ``/api/projects/<id>/file`` are silently swallowed
    by ``get_project`` / ``update_project`` with ``project_id="<id>/file"``
    and the editor file endpoints become unreachable. See ADR-036 audit
    finding P1-1.
    """
    from scistudio.api.routes.projects import router

    paths_in_order = [r.path for r in router.routes]
    file_get = paths_in_order.index("/api/projects/{project_id:path}/file")
    catch_all_get = paths_in_order.index("/api/projects/{project_id:path}")
    assert file_get < catch_all_get, (
        "ADR-036 P1-1 regression: /file routes must precede "
        "/{project_id:path} catch-all so FastAPI matches them first. "
        f"Current order: {paths_in_order}"
    )


def test_file_route_resolves_to_file_handler_not_catch_all() -> None:
    """A live ``GET /api/projects/<id>/file`` reaches ``read_project_file``.

    With Phase 2A in place the handler now returns 404 (project unknown)
    rather than 500, but the important assertion is that the catch-all
    does NOT intercept the request.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from scistudio.api.deps import get_runtime
    from scistudio.api.routes.projects import router

    app = FastAPI()
    app.include_router(router)

    class _StubRuntime:
        known_projects: ClassVar[dict[str, object]] = {}

    app.dependency_overrides[get_runtime] = lambda: _StubRuntime()

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/projects/some-id/file?path=blocks/foo.py")
    # The implementation hits ``_resolve_project_file`` which raises 404
    # for an unknown project. The catch-all handler would surface 200 or
    # a different shape; 404 confirms the file route handled it.
    assert response.status_code == 404, (
        f"Expected 404 from read_project_file (unknown project), got "
        f"{response.status_code}: {response.text!r}. If 200/415, the "
        "catch-all /{project_id:path} is intercepting the request — P1-1 regression."
    )
