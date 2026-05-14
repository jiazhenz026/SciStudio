"""ADR-036 §3.2 — file GET/PUT endpoint test stubs.

These tests are SKELETONS. Phase 2A implementation agent (I36a) deletes
the ``xfail`` marker from each one and fills in the body. The test plan
in each docstring captures exactly what to assert.

Why xfail (not skip):
  - xfail surfaces if a test passes unexpectedly (the implementation
    arrived without anyone updating the marker), which catches drift.
  - skip is silent.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_read_file_happy_path() -> None:
    """GET /api/projects/{id}/file?path=blocks/foo.py returns content + mtime + size.

    Implementation steps for the test (I36a):
      1. Use the existing FastAPI test client fixture.
      2. Create a project with a known root containing ``blocks/foo.py``.
      3. GET the endpoint, assert 200, response.json() has ``content``,
         ``mtime``, ``size``, ``encoding == "utf-8"``.
    """
    raise NotImplementedError


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_read_file_404_missing() -> None:
    """GET on a non-existent path returns 404."""
    raise NotImplementedError


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_read_file_403_traversal() -> None:
    """GET with path="../../etc/passwd" returns 403 (path escapes project root)."""
    raise NotImplementedError


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_read_file_415_extension() -> None:
    """GET on a .exe (or any non-allowlisted extension) returns 415."""
    raise NotImplementedError


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_read_file_413_size() -> None:
    """GET on a > 10 MB file returns 413."""
    raise NotImplementedError


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_write_file_happy_path() -> None:
    """PUT writes content atomically and returns updated mtime + size.

    Implementation steps for the test (I36a):
      1. PUT body={"content": "print('hello')\\n"}.
      2. Assert 200, response.json() has new mtime, size == 16.
      3. Read the file off disk, assert content matches exactly.
    """
    raise NotImplementedError


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_write_file_atomic() -> None:
    """If the write fails mid-way, the destination retains the OLD content.

    Use ``monkeypatch.setattr("os.replace", raising_replace)`` to
    simulate failure after tempfile is written but before rename.
    """
    raise NotImplementedError


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_write_file_self_write_suppression() -> None:
    """PUT calls ``mark_self_write(target)`` BEFORE the on-disk replace.

    Install a fake watcher via ``set_active_watcher``, capture the call
    order with timestamps, assert ``mark_self_write`` happened before the
    file's mtime advanced.
    """
    raise NotImplementedError


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_write_file_413_size() -> None:
    """PUT with content > 10 MB returns 413 BEFORE touching disk.

    Verify by checking the destination file mtime has NOT advanced after
    the rejected request.
    """
    raise NotImplementedError


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_write_file_403_traversal() -> None:
    """PUT with traversal path returns 403 and does not create files outside root."""
    raise NotImplementedError


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_write_file_415_extension() -> None:
    """PUT to a .exe path returns 415."""
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Regression tests — ADR-036 audit P1-1.
#
# These DO NOT depend on a real implementation. They assert the FastAPI
# route table registers ``/{project_id:path}/file`` BEFORE the greedy
# ``/{project_id:path}`` catch-all so that ``GET /api/projects/<id>/file``
# resolves to the file handler, not the project handler. They must remain
# passing through the implementation phase.
# ---------------------------------------------------------------------------


def test_file_route_registered_before_catch_all() -> None:
    """``/{project_id:path}/file`` MUST appear before ``/{project_id:path}``.

    FastAPI matches routes in declaration order. If this test fails,
    requests to GET/PUT ``/api/projects/<id>/file`` are silently swallowed
    by ``get_project`` / ``update_project`` with ``project_id="<id>/file"``
    and the editor file endpoints become unreachable. See ADR-036 audit
    finding P1-1.
    """
    from scieasy.api.routes.projects import router

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

    Use the FastAPI router's ``url_path_for`` to confirm the file endpoint
    name is mapped, then exercise the ASGI matcher to confirm a request
    against the URL hits ``read_project_file`` (skeleton raises
    NotImplementedError -> we surface that exception class as the proof).
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from scieasy.api.routes.projects import router

    app = FastAPI()
    app.include_router(router)
    # Stub the runtime dependency so dependency resolution does not fail.
    from scieasy.api.deps import get_runtime

    app.dependency_overrides[get_runtime] = lambda: object()

    client = TestClient(app, raise_server_exceptions=False)
    # The skeleton handler raises NotImplementedError; FastAPI converts that
    # into a 500. We assert we DID hit the file handler (not the catch-all
    # which would 200 OK or 404), confirmed by the 500 surface.
    response = client.get("/api/projects/some-id/file?path=blocks/foo.py")
    assert response.status_code == 500, (
        f"Expected 500 from skeleton NotImplementedError in read_project_file, got "
        f"{response.status_code}: {response.text!r}. If this is 200/404, the "
        "catch-all /{project_id:path} is intercepting the request — P1-1 regression."
    )
