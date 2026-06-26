"""Tests for the Package Manager update-check service (issue #1784)."""

from __future__ import annotations

import json

import pytest

from scistudio.blocks.base.package_info import PackageInfo, PackageOtaSource
from scistudio.desktop.package_manager import check_package_updates, fetch_manifest_json


def _info(name: str, version: str, *, ota: bool = True) -> PackageInfo:
    source = PackageOtaSource(manifest_url=f"https://example.com/{name}/manifest.json", channel="alpha") if ota else None
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
