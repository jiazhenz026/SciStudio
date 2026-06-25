"""Tests for ``scripts/ota_publish.py``.

Covers the pure pieces: version parsing, monotonic build numbering, manifest
assembly, asset naming/URLs, sha256, and snapshot packing (including the
__pycache__ / egg-info exclusions). The gh/IO side is not exercised here.
"""

from __future__ import annotations

import importlib.util
import json
import tarfile
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "ota_publish.py"


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("ota_publish", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- #
# parse_version
# --------------------------------------------------------------------------- #
def test_parse_version_prerelease(mod):
    assert mod.parse_version("0.2.1-alpha-build0006") == {
        "base": "0.2.1",
        "channel": "alpha",
        "build": 6,
    }


def test_parse_version_stable(mod):
    assert mod.parse_version("1.4.0") == {"base": "1.4.0", "channel": "stable", "build": 0}


def test_parse_version_beta_large_build(mod):
    assert mod.parse_version("0.2.1-beta-build0123")["build"] == 123


def test_parse_version_invalid_raises(mod):
    with pytest.raises(ValueError):
        mod.parse_version("not-a-version")


# --------------------------------------------------------------------------- #
# next_build_number
# --------------------------------------------------------------------------- #
def test_next_build_from_baseline_when_no_published(mod):
    # First patch must exceed the installer baseline build.
    assert mod.next_build_number(None, 6) == 7


def test_next_build_increments_latest_published(mod):
    assert mod.next_build_number(11, 6) == 12


def test_next_build_never_below_baseline(mod):
    # A stale/low published number must not let a patch regress past baseline.
    assert mod.next_build_number(3, 9) == 10


# --------------------------------------------------------------------------- #
# naming / urls
# --------------------------------------------------------------------------- #
def test_asset_and_url_and_tag(mod):
    assert mod.asset_name(12) == "backend-build12.tar.gz"
    assert mod.channel_tag("alpha") == "ota-alpha"
    assert mod.asset_url("o/r", "ota-alpha", "backend-build12.tar.gz") == (
        "https://github.com/o/r/releases/download/ota-alpha/backend-build12.tar.gz"
    )


# --------------------------------------------------------------------------- #
# build_manifest
# --------------------------------------------------------------------------- #
def test_build_manifest_shape(mod):
    manifest = mod.build_manifest(
        channel="alpha",
        base="0.2.1",
        build=7,
        url="https://example/backend-build7.tar.gz",
        sha256="abc",
        size=1234,
        notes="hi",
        published_at="2026-06-25T00:00:00Z",
    )
    assert manifest["channel"] == "alpha"
    assert manifest["build"] == 7
    assert manifest["requires"] == {"min_base": "0.2.1"}
    assert manifest["sha256"] == "abc"
    assert manifest["size"] == 1234
    # Round-trips as JSON (it is written to the release asset verbatim).
    assert json.loads(json.dumps(manifest))["url"].endswith("backend-build7.tar.gz")


# --------------------------------------------------------------------------- #
# sha256_file
# --------------------------------------------------------------------------- #
def test_sha256_file(mod, tmp_path):
    target = tmp_path / "blob.bin"
    target.write_bytes(b"scistudio")
    import hashlib

    assert mod.sha256_file(target) == hashlib.sha256(b"scistudio").hexdigest()


# --------------------------------------------------------------------------- #
# make_snapshot
# --------------------------------------------------------------------------- #
def test_make_snapshot_roots_at_src_and_excludes_caches(mod, tmp_path):
    src = tmp_path / "backend" / "src"
    pkg = src / "scistudio"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("x = 1\n")
    (pkg / "module.py").write_text("y = 2\n")
    # Noise that must be excluded from the snapshot.
    cache = pkg / "__pycache__"
    cache.mkdir()
    (cache / "module.cpython-312.pyc").write_bytes(b"\x00")
    egg = src / "scistudio.egg-info"
    egg.mkdir()
    (egg / "PKG-INFO").write_text("meta\n")

    out = tmp_path / "snap.tar.gz"
    mod.make_snapshot(src, out)

    with tarfile.open(out, "r:gz") as tar:
        names = set(tar.getnames())

    assert "src/scistudio/__init__.py" in names
    assert "src/scistudio/module.py" in names
    assert not any("__pycache__" in n for n in names)
    assert not any(n.endswith(".pyc") for n in names)
    assert not any("egg-info" in n for n in names)
