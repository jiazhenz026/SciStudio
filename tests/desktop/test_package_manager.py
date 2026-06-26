"""Tests for the Package Manager update-check service (issue #1784)."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

from scistudio.blocks.base.package_info import PackageInfo, PackageOtaSource
from scistudio.desktop.package_manager import (
    PackageUpdateError,
    check_package_updates,
    delete_package,
    fetch_manifest_json,
    list_installed_packages,
    rollback_package,
    update_package,
)


def _info(name: str, version: str, *, ota: bool = True) -> PackageInfo:
    source = (
        PackageOtaSource(manifest_url=f"https://example.com/{name}/manifest.json", channel="alpha") if ota else None
    )
    return PackageInfo(name=name, version=version, ota=source)


def _manifest(package: str, version: str, *, min_core_base: str = "0.2.1") -> dict:
    return {
        "package": package,
        "version": version,
        "url": f"https://example.com/{package}-{version}.tar.gz",
        "sha256": "a" * 64,
        "size": 10,
        "requires": {"min_core_base": min_core_base},
        "notes": f"notes for {version}",
    }


def test_check_skips_packages_without_ota_source():
    packages = {"p": _info("p", "1.0.0", ota=False)}
    results = check_package_updates(packages, core_base="0.2.1", fetch=lambda url: {})
    assert results == []


def test_check_reports_available_update():
    packages = {"spec": _info("spec", "1.0.0")}

    def fake_fetch(url: str) -> dict:
        assert url == "https://example.com/spec/manifest.json"
        return _manifest("spec", "1.2.0")

    [result] = check_package_updates(packages, core_base="0.2.1", fetch=fake_fetch)
    assert result.status == "update"
    assert result.update_available is True
    assert result.current_version == "1.0.0"
    assert result.available_version == "1.2.0"
    assert result.notes == "notes for 1.2.0"
    assert result.channel == "alpha"


def test_check_reports_up_to_date():
    packages = {"spec": _info("spec", "1.2.0")}
    [result] = check_package_updates(packages, core_base="0.2.1", fetch=lambda url: _manifest("spec", "1.2.0"))
    assert result.status == "none"
    assert result.update_available is False


def test_check_reports_incompatible_core():
    packages = {"spec": _info("spec", "1.0.0")}
    [result] = check_package_updates(
        packages,
        core_base="0.2.1",
        fetch=lambda url: _manifest("spec", "2.0.0", min_core_base="0.3.0"),
    )
    assert result.status == "incompatible"
    assert result.min_core_base == "0.3.0"
    assert result.available_version == "2.0.0"


def test_check_degrades_to_error_row_on_fetch_failure():
    packages = {"spec": _info("spec", "1.0.0")}

    def boom(url: str):
        raise OSError("network down")

    [result] = check_package_updates(packages, core_base="0.2.1", fetch=boom)
    assert result.status == "error"
    assert "network down" in result.reason
    assert result.current_version == "1.0.0"


def test_check_handles_malformed_manifest():
    packages = {"spec": _info("spec", "1.0.0")}
    [result] = check_package_updates(packages, core_base="0.2.1", fetch=lambda url: {"bogus": True})
    assert result.status == "invalid"


def test_check_one_bad_source_does_not_break_others():
    packages = {
        "good": _info("good", "1.0.0"),
        "bad": _info("bad", "1.0.0"),
    }

    def fetch(url: str):
        if "bad" in url:
            raise OSError("boom")
        return _manifest("good", "1.1.0")

    results = {r.package_name: r for r in check_package_updates(packages, core_base="0.2.1", fetch=fetch)}
    assert results["good"].status == "update"
    assert results["bad"].status == "error"


def _make_source_package(tmp: Path, *, dist_name: str, module: str, version: str) -> Path:
    """Build a minimal SciStudio source package tree and return its root."""
    root = tmp / f"{dist_name}-src"
    pkg = root / "src" / module
    pkg.mkdir(parents=True)
    (root / "pyproject.toml").write_text(f'[project]\nname = "{dist_name}"\nversion = "{version}"\n', encoding="utf-8")
    (pkg / "__init__.py").write_text("BLOCKS = []\n", encoding="utf-8")
    return root


def _tar_gz_bytes(source_root: Path) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        tar.add(source_root, arcname=source_root.name)
    return buffer.getvalue()


def _install_one(install_root: Path, *, dist_name: str, module: str, version: str) -> Path:
    """Install a freshly built source package into ``install_root``."""
    from scistudio.desktop.package_installer import install_local_package

    src_tmp = install_root.parent / f"build-{version}"
    src_tmp.mkdir(parents=True, exist_ok=True)
    source_root = _make_source_package(src_tmp, dist_name=dist_name, module=module, version=version)
    return install_local_package(source_root, install_root=install_root, install_dependencies=False).install_path


def test_list_installed_packages_reads_manifests(tmp_path):
    install_root = tmp_path / "packages"
    _install_one(install_root, dist_name="scistudio-blocks-demo", module="scistudio_blocks_demo", version="1.0.0")
    listed = list_installed_packages(install_root=install_root, backups_root=tmp_path / "backups")
    assert len(listed) == 1
    assert listed[0].package_name == "scistudio-blocks-demo"
    assert listed[0].version == "1.0.0"
    assert listed[0].has_backup is False


def test_update_package_downloads_verifies_and_backs_up(tmp_path):
    install_root = tmp_path / "packages"
    backups_root = tmp_path / "backups"
    _install_one(install_root, dist_name="scistudio-blocks-demo", module="scistudio_blocks_demo", version="1.0.0")

    # Build the "new version" snapshot the manifest will point at.
    new_src = _make_source_package(
        tmp_path / "newbuild", dist_name="scistudio-blocks-demo", module="scistudio_blocks_demo", version="1.2.0"
    )
    tarball_bytes = _tar_gz_bytes(new_src)
    sha = hashlib.sha256(tarball_bytes).hexdigest()

    info = PackageInfo(
        name="scistudio-blocks-demo",
        version="1.0.0",
        ota=PackageOtaSource(manifest_url="https://example.com/demo/manifest.json", channel="alpha"),
    )

    def fetch(url: str) -> dict:
        return {
            "package": "scistudio-blocks-demo",
            "version": "1.2.0",
            "url": "https://example.com/demo-1.2.0.tar.gz",
            "sha256": sha,
            "requires": {"min_core_base": "0.0.0"},
        }

    def download(url: str, dest: Path) -> None:
        dest.write_bytes(tarball_bytes)

    result = update_package(
        "scistudio-blocks-demo",
        packages={"scistudio-blocks-demo": info},
        core_base="0.2.1",
        fetch=fetch,
        download=download,
        install_root=install_root,
        backups_root=backups_root,
        install_dependencies=False,
    )
    assert result.action == "update"
    assert result.version == "1.2.0"
    assert result.previous_version == "1.0.0"
    assert result.needs_relaunch is True

    listed = {p.package_name: p for p in list_installed_packages(install_root=install_root, backups_root=backups_root)}
    assert listed["scistudio-blocks-demo"].version == "1.2.0"
    assert listed["scistudio-blocks-demo"].has_backup is True
    assert listed["scistudio-blocks-demo"].backup_version == "1.0.0"
    # Exactly one active version dir remains on the scan path.
    assert len(list(install_root.iterdir())) == 1


def test_update_package_rejects_checksum_mismatch(tmp_path):
    install_root = tmp_path / "packages"
    _install_one(install_root, dist_name="scistudio-blocks-demo", module="scistudio_blocks_demo", version="1.0.0")
    info = PackageInfo(
        name="scistudio-blocks-demo",
        version="1.0.0",
        ota=PackageOtaSource(manifest_url="https://example.com/demo/manifest.json"),
    )

    def fetch(url: str) -> dict:
        return {
            "package": "scistudio-blocks-demo",
            "version": "1.2.0",
            "url": "https://example.com/demo-1.2.0.tar.gz",
            "sha256": "f" * 64,
            "requires": {"min_core_base": "0.0.0"},
        }

    def download(url: str, dest: Path) -> None:
        dest.write_bytes(b"corrupted")

    with pytest.raises(PackageUpdateError, match="Checksum mismatch"):
        update_package(
            "scistudio-blocks-demo",
            packages={"scistudio-blocks-demo": info},
            core_base="0.2.1",
            fetch=fetch,
            download=download,
            install_root=install_root,
            backups_root=tmp_path / "backups",
            install_dependencies=False,
        )


def test_rollback_restores_previous_version(tmp_path):
    install_root = tmp_path / "packages"
    backups_root = tmp_path / "backups"
    _install_one(install_root, dist_name="scistudio-blocks-demo", module="scistudio_blocks_demo", version="1.0.0")

    new_src = _make_source_package(
        tmp_path / "newbuild", dist_name="scistudio-blocks-demo", module="scistudio_blocks_demo", version="1.2.0"
    )
    tarball_bytes = _tar_gz_bytes(new_src)
    sha = hashlib.sha256(tarball_bytes).hexdigest()
    info = PackageInfo(
        name="scistudio-blocks-demo",
        version="1.0.0",
        ota=PackageOtaSource(manifest_url="https://example.com/demo/manifest.json"),
    )
    update_package(
        "scistudio-blocks-demo",
        packages={"scistudio-blocks-demo": info},
        core_base="0.2.1",
        fetch=lambda url: {
            "package": "scistudio-blocks-demo",
            "version": "1.2.0",
            "url": "https://example.com/demo-1.2.0.tar.gz",
            "sha256": sha,
            "requires": {"min_core_base": "0.0.0"},
        },
        download=lambda url, dest: dest.write_bytes(tarball_bytes),
        install_root=install_root,
        backups_root=backups_root,
        install_dependencies=False,
    )

    result = rollback_package("scistudio-blocks-demo", install_root=install_root, backups_root=backups_root)
    assert result.action == "rollback"
    assert result.version == "1.0.0"
    assert result.previous_version == "1.2.0"
    listed = {p.package_name: p for p in list_installed_packages(install_root=install_root, backups_root=backups_root)}
    assert listed["scistudio-blocks-demo"].version == "1.0.0"
    assert listed["scistudio-blocks-demo"].has_backup is False


def test_rollback_without_backup_raises(tmp_path):
    install_root = tmp_path / "packages"
    _install_one(install_root, dist_name="scistudio-blocks-demo", module="scistudio_blocks_demo", version="1.0.0")
    with pytest.raises(PackageUpdateError, match="No rollback backup"):
        rollback_package("scistudio-blocks-demo", install_root=install_root, backups_root=tmp_path / "backups")


def test_delete_removes_active_and_backup(tmp_path):
    install_root = tmp_path / "packages"
    backups_root = tmp_path / "backups"
    _install_one(install_root, dist_name="scistudio-blocks-demo", module="scistudio_blocks_demo", version="1.0.0")
    result = delete_package("scistudio-blocks-demo", install_root=install_root, backups_root=backups_root)
    assert result.action == "delete"
    assert result.version == "1.0.0"
    assert list_installed_packages(install_root=install_root, backups_root=backups_root) == []


def test_delete_missing_package_raises(tmp_path):
    with pytest.raises(PackageUpdateError, match="not installed"):
        delete_package("nope", install_root=tmp_path / "packages", backups_root=tmp_path / "backups")


def test_fetch_manifest_json_rejects_non_http_scheme():
    with pytest.raises(ValueError, match="Unsupported manifest URL scheme"):
        fetch_manifest_json("file:///etc/passwd")


def test_fetch_manifest_json_reads_http(monkeypatch):
    import urllib.request

    class FakeResponse:
        headers = type("H", (), {"get_content_charset": staticmethod(lambda: "utf-8")})()

        def read(self):
            return json.dumps({"package": "p", "version": "1.0.0", "url": "u", "sha256": "s"}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: FakeResponse())
    data = fetch_manifest_json("https://example.com/manifest.json")
    assert data["package"] == "p"
