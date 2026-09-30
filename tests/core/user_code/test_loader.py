"""The user module loader (ADR-056 FR-002, FR-003; spec NEW-003)."""

from __future__ import annotations

from pathlib import Path

from scistudio.core.user_code import install_user_import_path, load_user_module, module_owner_dir


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_returns_only_the_classes_a_module_defines(tmp_path: Path) -> None:
    _write(tmp_path / "blocks" / "scistudio_loader_b.py", "class Defined:\n    pass\n")
    _write(
        tmp_path / "blocks" / "scistudio_loader_a.py",
        "from scistudio_loader_b import Defined\nclass Own:\n    pass\n",
    )
    install_user_import_path([tmp_path / "blocks"])

    loaded = load_user_module("scistudio_loader_a")

    assert loaded.ok
    assert [cls.__name__ for cls in loaded.classes] == ["Own"]
    assert loaded.file == (tmp_path / "blocks" / "scistudio_loader_a.py").resolve()
    assert loaded.mtime_ns is not None


def test_exceptions_become_failure_information(tmp_path: Path) -> None:
    _write(tmp_path / "blocks" / "scistudio_loader_raises.py", "raise ValueError('broken')\n")
    _write(tmp_path / "blocks" / "scistudio_loader_exits.py", "import sys\nsys.exit(2)\n")
    install_user_import_path([tmp_path / "blocks"])

    raised = load_user_module("scistudio_loader_raises")
    exited = load_user_module("scistudio_loader_exits")
    missing = load_user_module("scistudio_loader_absent")

    assert (raised.ok, raised.error_type, raised.message) == (False, "ValueError", "broken")
    assert (exited.ok, exited.error_type) == (False, "SystemExit")
    assert (missing.ok, missing.error_type) == (False, "ModuleNotFoundError")


def test_module_owner_dir_reports_the_directory_a_stem_resolves_from(tmp_path: Path) -> None:
    project = _write(tmp_path / "project" / "types" / "scistudio_owner.py", "")
    _write(tmp_path / "library" / "types" / "scistudio_owner.py", "")
    _write(tmp_path / "library" / "types" / "scistudio_owner_pkg" / "__init__.py", "")
    install_user_import_path([tmp_path / "project" / "types", tmp_path / "library" / "types"])

    assert module_owner_dir("scistudio_owner") == project.parent.resolve()
    assert module_owner_dir("scistudio_owner_pkg") == (tmp_path / "library" / "types").resolve()
    assert module_owner_dir("scistudio_owner_absent") is None
