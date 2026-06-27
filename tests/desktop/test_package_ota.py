"""Tests for the pure per-package OTA decision logic (issue #1784)."""

from __future__ import annotations

import pytest

from scistudio.desktop.package_ota import (
    PackageManifest,
    compare_semver,
    evaluate_update,
    parse_semver,
)


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("1.2.3", (1, 2, 3, True)),
        ("0.0.0", (0, 0, 0, True)),
        ("10.20.30", (10, 20, 30, True)),
        ("1.2.3-alpha", (1, 2, 3, False)),
        ("1.2.3-rc.1", (1, 2, 3, False)),
        ("1.2.3+build7", (1, 2, 3, True)),
        ("", None),
        ("1.2", None),
        ("v1.2.3", None),
        ("1.2.3.4", None),
        (None, None),
    ],
)
def test_parse_semver(version, expected):
    assert parse_semver(version) == expected


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("1.0.0", "1.0.0", 0),
        ("1.0.1", "1.0.0", 1),
        ("1.0.0", "1.0.1", -1),
        ("2.0.0", "1.9.9", 1),
        ("1.2.0", "1.10.0", -1),  # numeric, not lexical
        ("1.0.0", "1.0.0-alpha", 1),  # release beats prerelease
        ("1.0.0-alpha", "1.0.0", -1),
        ("1.0.0+build", "1.0.0", 0),  # build metadata is still a release
        ("garbage", "1.0.0", -1),  # unparsable sorts below
        ("garbage", "nonsense", 0),
    ],
)
def test_compare_semver(a, b, expected):
    assert compare_semver(a, b) == expected


def _manifest(**overrides) -> dict:
    base = {
        "package": "scistudio-blocks-spectroscopy",
        "version": "1.1.0",
        "url": "https://example.com/pkg-1.1.0.tar.gz",
        "sha256": "a" * 64,
        "size": 1234,
        "requires": {"min_core_base": "0.2.1"},
        "notes": "fix",
        "published_at": "2026-06-26T00:00:00Z",
    }
    base.update(overrides)
    return base


def test_manifest_from_dict_parses_requires():
    manifest = PackageManifest.from_dict(_manifest())
    assert manifest is not None
    assert manifest.package == "scistudio-blocks-spectroscopy"
    assert manifest.version == "1.1.0"
    assert manifest.min_core_base == "0.2.1"
    assert manifest.size == 1234


@pytest.mark.parametrize(
    "broken",
    [
        {"version": "1.0.0", "url": "u", "sha256": "s"},  # no package
        {"package": "p", "url": "u", "sha256": "s"},  # no version
        {"package": "p", "version": "1.0.0", "sha256": "s"},  # no url
        {"package": "p", "version": "1.0.0", "url": "u"},  # no sha256
        "not-a-dict",
        None,
        42,
    ],
)
def test_manifest_from_dict_rejects_malformed(broken):
    assert PackageManifest.from_dict(broken) is None


def test_evaluate_update_offers_newer_compatible():
    manifest = PackageManifest.from_dict(_manifest(version="1.2.0"))
    result = evaluate_update(manifest, installed_version="1.1.0", core_base="0.2.1")
    assert result.kind == "update"
    assert result.available_version == "1.2.0"


def test_evaluate_update_up_to_date():
    manifest = PackageManifest.from_dict(_manifest(version="1.1.0"))
    result = evaluate_update(manifest, installed_version="1.1.0", core_base="0.2.1")
    assert result.kind == "none"
    assert result.reason == "up-to-date"


def test_evaluate_update_older_remote_is_noop():
    manifest = PackageManifest.from_dict(_manifest(version="1.0.0"))
    result = evaluate_update(manifest, installed_version="1.1.0", core_base="0.2.1")
    assert result.kind == "none"


def test_evaluate_update_incompatible_core():
    manifest = PackageManifest.from_dict(_manifest(version="2.0.0", requires={"min_core_base": "0.3.0"}))
    result = evaluate_update(manifest, installed_version="1.1.0", core_base="0.2.1")
    assert result.kind == "incompatible"
    assert result.min_core_base == "0.3.0"
    assert result.available_version == "2.0.0"


def test_evaluate_update_compatible_when_core_newer_than_min():
    manifest = PackageManifest.from_dict(_manifest(version="2.0.0", requires={"min_core_base": "0.2.0"}))
    result = evaluate_update(manifest, installed_version="1.1.0", core_base="0.2.1")
    assert result.kind == "update"


def test_evaluate_update_bad_manifest():
    result = evaluate_update(None, installed_version="1.1.0", core_base="0.2.1")
    assert result.kind == "invalid"


def test_evaluate_update_unparsable_installed_version():
    manifest = PackageManifest.from_dict(_manifest(version="1.2.0"))
    result = evaluate_update(manifest, installed_version="dev", core_base="0.2.1")
    assert result.kind == "none"
    assert result.reason == "installed-version-unparsable"
