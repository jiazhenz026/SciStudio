"""Drop-in previewer scan hardening (#2044) and user-tier discovery (#2017).

Covers the shared ``_scan_previewer_dropins`` implementation in
``scistudio.previewers.project``: the FR-016 collision guard, scoped
``sys.path`` activation, bytecode eviction, ``BaseException`` isolation,
diagnostic surfacing, and the unconditional user tier.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scistudio.core.dropins import (
    PREVIEWERS_DIR_NAME,
    guard_dropin_roots,
    previewer_import_roots,
    previewer_scan_dirs,
)
from scistudio.previewers import build_preview_service
from scistudio.previewers.models import (
    EnvelopeKind,
    OwnerKind,
    PreviewTarget,
    TargetKind,
)
from scistudio.previewers.project import load_project_previewers, load_user_previewers
from scistudio.previewers.registry import PreviewerRegistry


def _write(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def _dropin_body(owner: str, previewer_id: str) -> str:
    return (
        "from scistudio.previewers.models import OwnerKind, PreviewerSpec\n"
        "def get_previewers():\n"
        "    return [PreviewerSpec(\n"
        f"        previewer_id={previewer_id!r},\n"
        f"        owner_kind=OwnerKind.{owner},\n"
        f"        owner_name={owner.lower()!r},\n"
        "        target_type='Image',\n"
        "    )]\n"
    )


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / "previewers").mkdir(parents=True)
    return project


@pytest.fixture()
def user_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    (home / ".scistudio" / "previewers").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


# -- tier definition (dropins.py) -------------------------------------------


def test_previewer_scan_dirs_project_then_user(project_dir: Path, user_home: Path) -> None:
    dirs = previewer_scan_dirs(project_dir)
    assert dirs == (project_dir / "previewers", user_home / ".scistudio" / "previewers")


def test_previewer_scan_dirs_user_tier_unconditional(user_home: Path) -> None:
    """FR-060 analog: the user tier exists with no project context at all."""
    assert previewer_scan_dirs(None) == (user_home / ".scistudio" / "previewers",)


def test_previewer_import_roots_start_with_scan_dirs(project_dir: Path, user_home: Path) -> None:
    roots = previewer_import_roots(project_dir)
    assert roots[:2] == (project_dir / "previewers", user_home / ".scistudio" / "previewers")


# -- #2044: scoped sys.path ---------------------------------------------------


def test_scan_does_not_permanently_mutate_sys_path(project_dir: Path) -> None:
    previewers_dir = project_dir / "previewers"
    _write(previewers_dir / "mine.py", _dropin_body("PROJECT", "project.mine"))
    registry = PreviewerRegistry()
    load_project_previewers(registry, project_dir)
    assert registry.get("project.mine") is not None
    assert str(previewers_dir) not in sys.path
    assert str(previewers_dir.resolve()) not in sys.path


def test_dropin_sibling_import_resolves_during_scan(project_dir: Path) -> None:
    """A drop-in importing a sibling module still works under scoped sys.path."""
    previewers_dir = project_dir / "previewers"
    _write(previewers_dir / "helpers.py", "PREVIEWER_ID = 'project.with.helper'\n")
    _write(
        previewers_dir / "mine.py",
        "import helpers\n"
        "from scistudio.previewers.models import OwnerKind, PreviewerSpec\n"
        "def get_previewers():\n"
        "    return [PreviewerSpec(previewer_id=helpers.PREVIEWER_ID, owner_kind=OwnerKind.PROJECT,"
        " owner_name='project', target_type='Image')]\n",
    )
    registry = PreviewerRegistry()
    load_project_previewers(registry, project_dir)
    assert registry.get("project.with.helper") is not None


# -- #2044: FR-016 collision guard --------------------------------------------


def test_colliding_dropin_is_refused_and_recorded(project_dir: Path) -> None:
    """A drop-in whose stem an installed module owns is never registered."""
    previewers_dir = project_dir / "previewers"
    _write(previewers_dir / "json.py", _dropin_body("PROJECT", "project.json"))
    _write(previewers_dir / "mine.py", _dropin_body("PROJECT", "project.mine"))
    registry = PreviewerRegistry()
    load_project_previewers(registry, project_dir)
    assert registry.get("project.json") is None
    assert registry.get("project.mine") is not None
    assert any("json.py" in message and "rejected" in message for message in registry.diagnostics)


def test_underscore_dropin_collision_is_guarded_but_not_registered(project_dir: Path) -> None:
    """Underscore names stay out of registration but inside the collision question."""
    previewers_dir = project_dir / "previewers"
    _write(previewers_dir / "_json.py", _dropin_body("PROJECT", "project.underscore.json"))
    collisions = guard_dropin_roots((previewers_dir,), dir_name=PREVIEWERS_DIR_NAME, bind=False)
    assert {collision.stem for collision in collisions} == {"_json"}
    registry = PreviewerRegistry()
    load_project_previewers(registry, project_dir)
    assert registry.get("project.underscore.json") is None


def test_refusal_releases_after_file_removed(project_dir: Path) -> None:
    previewers_dir = project_dir / "previewers"
    colliding = _write(previewers_dir / "json.py", _dropin_body("PROJECT", "project.json"))
    first = guard_dropin_roots((previewers_dir,), dir_name=PREVIEWERS_DIR_NAME, bind=False)
    assert {collision.stem for collision in first} == {"json"}
    colliding.unlink()
    second = guard_dropin_roots((previewers_dir,), dir_name=PREVIEWERS_DIR_NAME, bind=False)
    assert second == ()


# -- #2044: failure isolation + surfacing --------------------------------------


def test_broken_dropin_is_recorded_and_scan_continues(project_dir: Path) -> None:
    previewers_dir = project_dir / "previewers"
    _write(previewers_dir / "broken.py", "raise RuntimeError('boom')\n")
    _write(previewers_dir / "mine.py", _dropin_body("PROJECT", "project.mine"))
    registry = PreviewerRegistry()
    load_project_previewers(registry, project_dir)
    assert registry.get("project.mine") is not None
    assert any("broken.py" in message for message in registry.diagnostics)


def test_sys_exit_in_dropin_does_not_kill_scan(project_dir: Path) -> None:
    previewers_dir = project_dir / "previewers"
    _write(previewers_dir / "quitter.py", "import sys\nsys.exit(1)\n")
    _write(previewers_dir / "mine.py", _dropin_body("PROJECT", "project.mine"))
    registry = PreviewerRegistry()
    load_project_previewers(registry, project_dir)
    assert registry.get("project.mine") is not None
    assert any("quitter.py" in message for message in registry.diagnostics)


def test_sys_exit_in_factory_does_not_kill_scan(project_dir: Path) -> None:
    previewers_dir = project_dir / "previewers"
    _write(previewers_dir / "quitter.py", "import sys\ndef get_previewers():\n    sys.exit(1)\n")
    _write(previewers_dir / "mine.py", _dropin_body("PROJECT", "project.mine"))
    registry = PreviewerRegistry()
    load_project_previewers(registry, project_dir)
    assert registry.get("project.mine") is not None


def test_rescan_sees_same_size_same_second_edit(project_dir: Path) -> None:
    """FR-062: a same-length edit within one second must not replay stale bytecode."""
    previewers_dir = project_dir / "previewers"
    target = previewers_dir / "mine.py"
    _write(target, _dropin_body("PROJECT", "project.version.one"))
    first = PreviewerRegistry()
    load_project_previewers(first, project_dir)
    assert first.get("project.version.one") is not None

    _write(target, _dropin_body("PROJECT", "project.version.two"))
    second = PreviewerRegistry()
    load_project_previewers(second, project_dir)
    assert second.get("project.version.two") is not None


# -- #2017: user tier discovery -------------------------------------------------


def test_user_tier_discovers_user_library_previewer(user_home: Path) -> None:
    _write(user_home / ".scistudio" / "previewers" / "mine.py", _dropin_body("USER", "user.mine"))
    registry = PreviewerRegistry()
    load_user_previewers(registry)
    spec = registry.get("user.mine")
    assert spec is not None
    assert spec.owner_kind is OwnerKind.USER


def test_user_tier_rejects_project_owned_spec(user_home: Path) -> None:
    _write(user_home / ".scistudio" / "previewers" / "wrong.py", _dropin_body("PROJECT", "project.wrong"))
    registry = PreviewerRegistry()
    load_user_previewers(registry)
    assert registry.get("project.wrong") is None


def test_build_service_loads_user_tier_without_project(user_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The user tier loads unconditionally: no project open required (#2017)."""
    _write(user_home / ".scistudio" / "previewers" / "mine.py", _dropin_body("USER", "user.mine"))
    monkeypatch.setattr(PreviewerRegistry, "load_packages", lambda self: None)
    service = build_preview_service(project_dir=None)
    assert service.registry.get("user.mine") is not None


def test_project_previewer_shadows_user_previewer_id(
    project_dir: Path, user_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Project registers before user, so an id collision keeps the project spec."""
    _write(project_dir / "previewers" / "mine.py", _dropin_body("PROJECT", "shared.id"))
    _write(user_home / ".scistudio" / "previewers" / "mine.py", _dropin_body("USER", "shared.id"))
    monkeypatch.setattr(PreviewerRegistry, "load_packages", lambda self: None)
    service = build_preview_service(project_dir=project_dir)
    spec = service.registry.get("shared.id")
    assert spec is not None
    assert spec.owner_kind is OwnerKind.PROJECT


# -- #2044: render-time lazy provider resolution -------------------------------


def test_lazy_string_provider_resolves_with_scoped_import_roots(user_home: Path) -> None:
    """A drop-in's ``module:callable`` provider resolves at render time without
    the drop-in dir living on ``sys.path`` permanently."""
    previewers_dir = user_home / ".scistudio" / "previewers"
    _write(
        previewers_dir / "renderer.py",
        "from scistudio.previewers.models import EnvelopeKind, PreviewEnvelope\n"
        "def render(request):\n"
        "    return PreviewEnvelope(previewer_id=request.spec.previewer_id, target=request.target,\n"
        "        kind=EnvelopeKind.TEXT, payload={'content': 'from-user-dropin'})\n",
    )
    _write(
        previewers_dir / "mine.py",
        "from scistudio.previewers.models import OwnerKind, PreviewerSpec\n"
        "def get_previewers():\n"
        "    return [PreviewerSpec(previewer_id='user.lazy', owner_kind=OwnerKind.USER, owner_name='user',\n"
        "        target_type='Image', backend_provider='renderer:render')]\n",
    )
    service = build_preview_service(project_dir=None)
    assert str(previewers_dir) not in sys.path
    target = PreviewTarget(
        kind=TargetKind.DATA_REF,
        ref="r",
        recorded_type="Image",
        type_chain=("DataObject", "Array", "Image"),
    )
    envelope = service.sessions.create_session(target)
    assert envelope.kind is EnvelopeKind.TEXT
    assert envelope.payload == {"content": "from-user-dropin"}
    assert envelope.previewer_id == "user.lazy"
    assert str(previewers_dir) not in sys.path


# -- PR #2072 audit: cross-tier module-cache isolation -------------------------


def _render_body(content: str) -> str:
    return (
        "from scistudio.previewers.models import EnvelopeKind, PreviewEnvelope\n"
        "def render(request):\n"
        "    return PreviewEnvelope(previewer_id=request.spec.previewer_id, target=request.target,\n"
        f"        kind=EnvelopeKind.TEXT, payload={{'content': {content!r}}})\n"
    )


def _lazy_dropin_body(owner: str, previewer_id: str, provider: str = "renderer:render") -> str:
    return (
        "from scistudio.previewers.models import OwnerKind, PreviewerSpec\n"
        "def get_previewers():\n"
        "    return [PreviewerSpec(\n"
        f"        previewer_id={previewer_id!r},\n"
        f"        owner_kind=OwnerKind.{owner},\n"
        f"        owner_name={owner.lower()!r},\n"
        "        target_type='Image',\n"
        f"        backend_provider={provider!r})]\n"
    )


def _image_target() -> PreviewTarget:
    return PreviewTarget(
        kind=TargetKind.DATA_REF,
        ref="r",
        recorded_type="Image",
        type_chain=("DataObject", "Array", "Image"),
    )


def test_user_lazy_provider_never_executes_project_same_name_module(
    project_dir: Path, user_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A user spec's ``renderer:render`` resolves against the *user* root, even
    when the project has a same-named module (PR #2072 audit P1)."""
    _write(project_dir / "previewers" / "renderer.py", _render_body("project-renderer"))
    previewers_dir = user_home / ".scistudio" / "previewers"
    _write(previewers_dir / "renderer.py", _render_body("user-renderer"))
    _write(previewers_dir / "mine.py", _lazy_dropin_body("USER", "user.lazy"))
    monkeypatch.setattr(PreviewerRegistry, "load_packages", lambda self: None)
    service = build_preview_service(project_dir=project_dir)
    envelope = service.sessions.create_session(_image_target())
    assert envelope.kind is EnvelopeKind.TEXT
    assert envelope.payload == {"content": "user-renderer"}
    assert envelope.previewer_id == "user.lazy"
    assert "renderer" not in sys.modules


def test_user_lazy_provider_survives_project_close(
    project_dir: Path, user_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rebuilding with ``project_dir=None`` must not keep serving the closed
    project's provider module from the ``sys.modules`` cache (PR #2072 audit)."""
    _write(project_dir / "previewers" / "renderer.py", _render_body("project-renderer"))
    previewers_dir = user_home / ".scistudio" / "previewers"
    _write(previewers_dir / "renderer.py", _render_body("user-renderer"))
    _write(previewers_dir / "mine.py", _lazy_dropin_body("USER", "user.lazy"))
    monkeypatch.setattr(PreviewerRegistry, "load_packages", lambda self: None)
    with_project = build_preview_service(project_dir=project_dir)
    assert with_project.sessions.create_session(_image_target()).payload == {"content": "user-renderer"}
    without_project = build_preview_service(project_dir=None)
    envelope = without_project.sessions.create_session(_image_target())
    assert envelope.payload == {"content": "user-renderer"}
    assert envelope.previewer_id == "user.lazy"


def test_sibling_helper_import_does_not_leak_across_tiers(
    project_dir: Path, user_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both tiers sibling-import a same-named ``helpers.py``; each must get its
    own, with no false FR-016 refusal on the second scan (PR #2072 audit P1)."""
    _write(project_dir / "previewers" / "helpers.py", "PREVIEWER_ID = 'project.with.helper'\n")
    _write(
        project_dir / "previewers" / "mine.py",
        "import helpers\n"
        "from scistudio.previewers.models import OwnerKind, PreviewerSpec\n"
        "def get_previewers():\n"
        "    return [PreviewerSpec(previewer_id=helpers.PREVIEWER_ID, owner_kind=OwnerKind.PROJECT,"
        " owner_name='project', target_type='Image')]\n",
    )
    _write(user_home / ".scistudio" / "previewers" / "helpers.py", "PREVIEWER_ID = 'user.with.helper'\n")
    _write(
        user_home / ".scistudio" / "previewers" / "mine.py",
        "import helpers\n"
        "from scistudio.previewers.models import OwnerKind, PreviewerSpec\n"
        "def get_previewers():\n"
        "    return [PreviewerSpec(previewer_id=helpers.PREVIEWER_ID, owner_kind=OwnerKind.USER,"
        " owner_name='user', target_type='Image')]\n",
    )
    monkeypatch.setattr(PreviewerRegistry, "load_packages", lambda self: None)
    service = build_preview_service(project_dir=project_dir)
    project_spec = service.registry.get("project.with.helper")
    user_spec = service.registry.get("user.with.helper")
    assert project_spec is not None and project_spec.owner_kind is OwnerKind.PROJECT
    assert user_spec is not None and user_spec.owner_kind is OwnerKind.USER
    assert not any("rejected" in message for message in service.registry.diagnostics)
    assert "helpers" not in sys.modules


def test_failed_dropin_exec_leaves_no_sys_modules_residue(project_dir: Path) -> None:
    """A drop-in that raises during exec must not leave its half-executed
    module in ``sys.modules`` (PR #2072 audit)."""
    previewers_dir = project_dir / "previewers"
    _write(previewers_dir / "broken.py", "raise RuntimeError('boom')\n")
    registry = PreviewerRegistry()
    load_project_previewers(registry, project_dir)
    assert "_scistudio_project_previewer_broken" not in sys.modules
    assert any("broken.py" in message for message in registry.diagnostics)


def test_owner_kind_mismatch_is_recorded_on_diagnostics(user_home: Path) -> None:
    """A wrong-tier spec is skipped *and* surfaced, not only logged."""
    _write(user_home / ".scistudio" / "previewers" / "wrong.py", _dropin_body("PROJECT", "project.wrong"))
    registry = PreviewerRegistry()
    load_user_previewers(registry)
    assert registry.get("project.wrong") is None
    assert any("project.wrong" in message and "owner_kind" in message for message in registry.diagnostics)


def test_refused_name_is_not_reimported_on_every_guard_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A collision whose installed module raises on import is bound (refused)
    once per process, not retried on every guard pass (PR #2072 audit P2)."""
    counter = tmp_path / "counter.txt"
    counter.write_text("0", encoding="utf-8")
    site = tmp_path / "site"
    site.mkdir()
    _write(
        site / "boommod_pr2072.py",
        "import pathlib\n"
        f"p = pathlib.Path({str(counter)!r})\n"
        "p.write_text(str(int(p.read_text()) + 1))\n"
        "raise RuntimeError('boom')\n",
    )
    monkeypatch.syspath_prepend(str(site))
    dropin_dir = tmp_path / "previewers"
    dropin_dir.mkdir()
    colliding = _write(dropin_dir / "boommod_pr2072.py", _dropin_body("PROJECT", "project.boom"))
    try:
        guard_dropin_roots((dropin_dir,), dir_name=PREVIEWERS_DIR_NAME)
        guard_dropin_roots((dropin_dir,), dir_name=PREVIEWERS_DIR_NAME)
        assert counter.read_text(encoding="utf-8") == "1"
    finally:
        # Release the process-wide refusal so it cannot leak into other tests.
        colliding.unlink()
        guard_dropin_roots((dropin_dir,), dir_name=PREVIEWERS_DIR_NAME)
