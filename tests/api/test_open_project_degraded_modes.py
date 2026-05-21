"""Phase 3.5 integration audit P2-1 — degraded-mode tests for ApiRuntime.open_project.

After integrating ADR-038 (lineage store) + ADR-039 (git auto-init),
``ApiRuntime.open_project`` performs **two independent best-effort
initialisations** in order:

  1. ``_init_lineage_store`` — opens ``<project>/.scistudio/lineage.db``;
     failure leaves ``runtime.lineage_store = None``.
  2. ADR-039 re-init hook — opens / inits the project git repo;
     failure leaves ``engine.is_repository(project_path) == False``.

Both failures are caught and logged at WARNING; the project must still
open. This test exercises the 2x2 matrix of (lineage init fails, git
init fails) to prove the degraded modes are wired correctly.

Reference: docs/audit/2026-05-15-adr-038-039-integration-audit.md P2-1.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def project_path(tmp_path: Path) -> Path:
    """Bare-minimum SciStudio project directory."""
    root = tmp_path / "demo_project"
    root.mkdir()
    (root / "project.yaml").write_text(
        "project:\n  name: Demo\n  description: Phase 3.5 P2-1 fixture\n",
        encoding="utf-8",
    )
    (root / "workflows").mkdir()
    return root


def _make_runtime():
    """Construct a bare ApiRuntime instance for a degraded-mode test.

    We avoid the test fixtures' app/TestClient wiring so this test does
    not need the full lifespan setup — we just want to call
    ``open_project`` directly.
    """
    from scistudio.api.runtime import ApiRuntime

    return ApiRuntime()


def test_open_project_succeeds_when_lineage_init_fails(
    project_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If lineage store init raises internally, project still opens.

    ``_init_lineage_store`` itself wraps the ``LineageStore(db_path)``
    call in try/except (best-effort per ADR-038 §3.1). The test patches
    ``LineageStore.__init__`` so the lazy import inside the method
    raises; the catch site logs WARNING and sets ``lineage_store=None``.
    """
    runtime = _make_runtime()

    from scistudio.core.lineage import store as _lineage_store_mod

    class _ExplodingStore:
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("lineage boom (degraded mode test)")

    with patch.object(_lineage_store_mod, "LineageStore", _ExplodingStore):
        project = runtime.open_project(str(project_path))

    assert project.path == str(project_path)
    # The active project should be set even though lineage init failed.
    assert runtime.active_project is not None
    assert runtime.active_project.path == str(project_path)
    # lineage_store should be None (degraded mode).
    assert runtime.lineage_store is None


def test_open_project_succeeds_when_git_init_fails(
    project_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If git auto-init raises, project still opens (degraded mode)."""
    runtime = _make_runtime()

    # Patch the lazily-imported GitEngine.is_repository / init_repository
    # so the ADR-039 hook in open_project raises.
    from scistudio.core.versioning import git_engine as _gem

    class _ExplodingEngine:
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("git boom (degraded mode test)")

    monkeypatch.setattr(_gem, "GitEngine", _ExplodingEngine)

    project = runtime.open_project(str(project_path))
    assert project.path == str(project_path)
    assert runtime.active_project is not None


def test_open_project_succeeds_when_both_inits_fail(
    project_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both lineage and git init failing must NOT prevent the project from opening."""
    runtime = _make_runtime()

    # Disable lineage init (patch the lazy import inside _init_lineage_store).
    from scistudio.core.lineage import store as _lineage_store_mod

    class _ExplodingStore:
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("lineage boom")

    monkeypatch.setattr(_lineage_store_mod, "LineageStore", _ExplodingStore)

    # Disable git init.
    from scistudio.core.versioning import git_engine as _gem

    class _ExplodingEngine:
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("git boom")

    monkeypatch.setattr(_gem, "GitEngine", _ExplodingEngine)

    project = runtime.open_project(str(project_path))
    assert project.path == str(project_path)
    assert runtime.active_project is not None
    assert runtime.lineage_store is None
