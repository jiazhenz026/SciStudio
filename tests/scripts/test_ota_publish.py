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
from types import ModuleType

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "ota_publish.py"


@pytest.fixture(scope="module")
def mod() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ota_publish", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- #
# parse_version
# --------------------------------------------------------------------------- #
def test_parse_version_prerelease(mod: ModuleType) -> None:
    assert mod.parse_version("0.2.1-alpha-build0006") == {
        "base": "0.2.1",
        "channel": "alpha",
        "build": 6,
    }


def test_parse_version_stable(mod: ModuleType) -> None:
    assert mod.parse_version("1.4.0") == {"base": "1.4.0", "channel": "stable", "build": 0}


def test_parse_version_beta_large_build(mod: ModuleType) -> None:
    assert mod.parse_version("0.2.1-beta-build0123")["build"] == 123


def test_parse_version_invalid_raises(mod: ModuleType) -> None:
    with pytest.raises(ValueError):
        mod.parse_version("not-a-version")


# --------------------------------------------------------------------------- #
# next_build_number
# --------------------------------------------------------------------------- #
def test_next_build_from_baseline_when_no_published(mod: ModuleType) -> None:
    # First patch must exceed the installer baseline build.
    assert mod.next_build_number(None, 6) == 7


def test_next_build_increments_latest_published(mod: ModuleType) -> None:
    assert mod.next_build_number(11, 6) == 12


def test_next_build_never_below_baseline(mod: ModuleType) -> None:
    # A stale/low published number must not let a patch regress past baseline.
    assert mod.next_build_number(3, 9) == 10


# --------------------------------------------------------------------------- #
# naming / urls
# --------------------------------------------------------------------------- #
def test_asset_and_url_and_tag(mod: ModuleType) -> None:
    assert mod.asset_name(12) == "backend-build12.tar.gz"
    assert mod.channel_tag("alpha") == "ota-alpha"
    assert mod.asset_url("o/r", "ota-alpha", "backend-build12.tar.gz") == (
        "https://github.com/o/r/releases/download/ota-alpha/backend-build12.tar.gz"
    )


# --------------------------------------------------------------------------- #
# build_manifest
# --------------------------------------------------------------------------- #
def test_build_manifest_shape(mod: ModuleType) -> None:
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


def test_build_manifest_omits_min_build_by_default(mod: ModuleType) -> None:
    # #1868: an ordinary optional patch must not carry min_build.
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
    assert "min_build" not in manifest["requires"]


def test_build_manifest_includes_min_build_when_mandatory(mod: ModuleType) -> None:
    # #1868: a mandatory patch records requires.min_build so the client blocks
    # startup for builds below it.
    manifest = mod.build_manifest(
        channel="alpha",
        base="0.2.1",
        build=8,
        url="https://example/backend-build8.tar.gz",
        sha256="abc",
        size=1234,
        notes="hi",
        published_at="2026-06-25T00:00:00Z",
        min_build=8,
    )
    assert manifest["requires"] == {"min_base": "0.2.1", "min_build": 8}


# --------------------------------------------------------------------------- #
# sha256_file
# --------------------------------------------------------------------------- #
def test_sha256_file(mod: ModuleType, tmp_path: Path) -> None:
    target = tmp_path / "blob.bin"
    target.write_bytes(b"scistudio")
    import hashlib

    assert mod.sha256_file(target) == hashlib.sha256(b"scistudio").hexdigest()


# --------------------------------------------------------------------------- #
# make_snapshot
# --------------------------------------------------------------------------- #
def test_make_snapshot_roots_at_src_and_excludes_caches(mod: ModuleType, tmp_path: Path) -> None:
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
    mod.make_snapshot(src, out, desktop_dir=_fake_desktop(tmp_path))

    with tarfile.open(out, "r:gz") as tar:
        names = set(tar.getnames())

    assert "src/scistudio/__init__.py" in names
    assert "src/scistudio/module.py" in names
    assert not any("__pycache__" in n for n in names)
    assert not any(n.endswith(".pyc") for n in names)
    assert not any("egg-info" in n for n in names)


# --------------------------------------------------------------------------- #
# #2097: the Electron shell rides inside the same snapshot, under shell/.
# --------------------------------------------------------------------------- #
def _fake_desktop(tmp_path: Path) -> Path:
    """A desktop/ directory holding just the files a snapshot deals with."""
    desktop = tmp_path / "desktop"
    desktop.mkdir(exist_ok=True)
    for name in ("main.js", "menu.js", "ota.js", "runtime-port.js", "preload.js", "splash.html"):
        (desktop / name).write_text("// " + name, encoding="utf-8")
    (desktop / "assets").mkdir(exist_ok=True)
    (desktop / "assets" / "icon.png").write_bytes(b"PNG-stub")
    # Present in the real desktop/ but deliberately never packed.
    (desktop / "bootstrap.js").write_text("// loader", encoding="utf-8")
    (desktop / "package.json").write_text('{"version": "0.3.3-alpha-build0000"}', encoding="utf-8")
    return desktop


def _snapshot_names(mod: ModuleType, tmp_path: Path) -> set[str]:
    src = tmp_path / "backend" / "src"
    pkg = src / "scistudio"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("x = 1", encoding="utf-8")
    out = tmp_path / "snap.tar.gz"
    mod.make_snapshot(src, out, desktop_dir=_fake_desktop(tmp_path))
    with tarfile.open(out, "r:gz") as tar:
        return set(tar.getnames())


def test_make_snapshot_carries_the_shell_beside_src(mod: ModuleType, tmp_path: Path) -> None:
    names = _snapshot_names(mod, tmp_path)
    assert "src/scistudio/__init__.py" in names
    for name in ("main.js", "menu.js", "ota.js", "runtime-port.js", "preload.js", "splash.html"):
        assert f"shell/{name}" in names


def test_make_snapshot_never_ships_the_bootstrap_loader(mod: ModuleType, tmp_path: Path) -> None:
    # The loader lives in the asar and decides which shell to trust. A patch able
    # to replace it could disable its own rollback.
    assert "shell/bootstrap.js" not in _snapshot_names(mod, tmp_path)


def test_make_snapshot_never_ships_a_shell_manifest(mod: ModuleType, tmp_path: Path) -> None:
    # The loader supplies the installed baseline version. A package.json inside
    # the patch would be the patch describing itself, which is precisely the
    # comparison the #1787 staleness check must never make.
    assert "shell/package.json" not in _snapshot_names(mod, tmp_path)


def test_published_shell_matches_the_asar_baseline_shell(mod: ModuleType) -> None:
    # Drift guard across the language boundary. The asar carries the baseline
    # shell (desktop/package.json build.files) and ota_publish ships the patched
    # one (SHELL_FILES). If a file is added to the shell and only one list is
    # updated, a patch either omits something main.js requires -- breaking the
    # shell for everyone who applies it -- or ships a file the baseline lacks.
    repo_root = Path(__file__).resolve().parents[2]
    package_json = json.loads((repo_root / "desktop" / "package.json").read_text(encoding="utf-8"))
    bundled = set(package_json["build"]["files"])
    published = set(mod.SHELL_FILES)

    assert published <= bundled, f"published but not bundled: {sorted(published - bundled)}"
    # bootstrap.js and package.json are bundled on purpose and never published.
    assert bundled - published == {"bootstrap.js", "package.json"}


def test_snapshot_carries_the_splash_asset(mod: ModuleType, tmp_path: Path) -> None:
    # splash.html references the logo with a RELATIVE src, so a patched splash
    # resolves it against the patch directory. Without the asset travelling with
    # the shell the loading screen renders a broken image -- observed on the
    # first real patched launch, not caught by any earlier test.
    assert "shell/assets/icon.png" in _snapshot_names(mod, tmp_path)


def test_shell_sources_refuses_an_incomplete_shell(mod: ModuleType, tmp_path: Path) -> None:
    # A shell/ without main.js fails isShellDir on every client and silently
    # falls back to the baseline, so fail at publish time instead.
    desktop = _fake_desktop(tmp_path)
    (desktop / "main.js").unlink()
    with pytest.raises(SystemExit) as excinfo:
        mod.shell_sources(desktop)
    assert "main.js" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# #2097 spec 8.1: the reinstall notice delivered as a patch.
# --------------------------------------------------------------------------- #
def test_reinstall_notice_substitutes_both_placeholders(mod: ModuleType) -> None:
    html = mod.render_reinstall_notice("https://example.test/download", "Installed 0.3.3")
    assert "https://example.test/download" in html
    assert "Installed 0.3.3" in html
    assert "__DOWNLOAD_URL__" not in html
    assert "__VERSION_LINE__" not in html


def test_reinstall_notice_page_can_be_copied_from(mod: ModuleType) -> None:
    # The whole reason this exists: a native dialog renders plain text that is
    # neither clickable nor selectable, so the address has to live in a page
    # where a button can put it on the clipboard.
    html = mod.render_reinstall_notice("https://example.test/download", "x")
    assert "clipboard.writeText" in html


def test_snapshot_replaces_the_spa_with_the_notice(mod: ModuleType, tmp_path: Path) -> None:
    src = tmp_path / "backend" / "src"
    static = src / "scistudio" / "api" / "static"
    static.mkdir(parents=True)
    (src / "scistudio" / "__init__.py").write_text("x = 1", encoding="utf-8")
    (static / "index.html").write_text("<html>the real SPA</html>", encoding="utf-8")
    out = tmp_path / "snap.tar.gz"

    notice = mod.render_reinstall_notice("https://example.test/dl", "Installed 0.3.3")
    mod.make_snapshot(src, out, desktop_dir=_fake_desktop(tmp_path), reinstall_notice=notice)

    with tarfile.open(out, "r:gz") as tar:
        names = tar.getnames()
        payload = tar.extractfile(mod.SPA_INDEX_ARCNAME).read().decode("utf-8")

    # Exactly one entry, and it is the notice rather than the real SPA.
    assert names.count(mod.SPA_INDEX_ARCNAME) == 1
    assert "https://example.test/dl" in payload
    assert "the real SPA" not in payload
    # The shell still rides along; this is an ordinary snapshot otherwise.
    assert "shell/main.js" in names


def test_snapshot_never_mutates_the_staged_tree(mod: ModuleType, tmp_path: Path) -> None:
    # Injecting into the archive rather than the tree is what stops a checkout
    # from quietly shipping the notice as its real frontend on the next publish.
    src = tmp_path / "backend" / "src"
    static = src / "scistudio" / "api" / "static"
    static.mkdir(parents=True)
    (src / "scistudio" / "__init__.py").write_text("x = 1", encoding="utf-8")
    index = static / "index.html"
    index.write_text("<html>the real SPA</html>", encoding="utf-8")

    mod.make_snapshot(
        src,
        tmp_path / "snap.tar.gz",
        desktop_dir=_fake_desktop(tmp_path),
        reinstall_notice=mod.render_reinstall_notice("https://example.test/dl", "x"),
    )

    assert index.read_text(encoding="utf-8") == "<html>the real SPA</html>"


def test_snapshot_without_a_notice_keeps_the_real_spa(mod: ModuleType, tmp_path: Path) -> None:
    src = tmp_path / "backend" / "src"
    static = src / "scistudio" / "api" / "static"
    static.mkdir(parents=True)
    (src / "scistudio" / "__init__.py").write_text("x = 1", encoding="utf-8")
    (static / "index.html").write_text("<html>the real SPA</html>", encoding="utf-8")
    out = tmp_path / "snap.tar.gz"

    mod.make_snapshot(src, out, desktop_dir=_fake_desktop(tmp_path))

    with tarfile.open(out, "r:gz") as tar:
        payload = tar.extractfile(mod.SPA_INDEX_ARCNAME).read().decode("utf-8")
    assert payload == "<html>the real SPA</html>"


# --------------------------------------------------------------------------- #
# #2169: min_base override — what makes --reinstall-notice reach anyone.
# --------------------------------------------------------------------------- #
def _manifest(mod: ModuleType, **kw: object) -> dict:
    args: dict[str, object] = {
        "channel": "alpha",
        "base": "0.3.4",
        "build": 26,
        "url": "https://example.test/backend-build26.tar.gz",
        "sha256": "abc",
        "size": 1,
        "notes": "",
        "published_at": "2026-08-25T00:00:00Z",
    }
    args.update(kw)
    return mod.build_manifest(**args)


def test_min_base_defaults_to_the_builds_own_base(mod: ModuleType) -> None:
    assert _manifest(mod)["requires"]["min_base"] == "0.3.4"


def test_min_base_can_be_overridden(mod: ModuleType) -> None:
    assert _manifest(mod, min_base="0.3.3")["requires"]["min_base"] == "0.3.3"


def test_the_override_is_what_turns_incompatible_into_patch(mod: ModuleType) -> None:
    """The whole point, expressed as the client's own comparison.

    compareBase(clientBase, min_base) < 0 is what desktop/ota.js uses to pick the
    incompatible branch, and that branch never downloads -- so a notice page
    published under a derived min_base is built, uploaded, and never fetched.
    """

    def client_is_incompatible(client_base: str, min_base: str) -> bool:
        def parts(v: str) -> list[int]:
            out = []
            for seg in v.split(".")[:3]:
                digits = ""
                for ch in seg:
                    if not ch.isdigit():
                        break
                    digits += ch
                out.append(int(digits) if digits else 0)
            while len(out) < 3:
                out.append(0)
            return out

        return parts(client_base) < parts(min_base)

    derived = _manifest(mod)["requires"]["min_base"]
    overridden = _manifest(mod, min_base="0.3.3")["requires"]["min_base"]

    # Without the override a 0.3.3 client takes the dialog-only path.
    assert client_is_incompatible("0.3.3", str(derived)) is True
    # With it, the same client takes the patch path and downloads the notice.
    assert client_is_incompatible("0.3.3", str(overridden)) is False


def test_the_migration_manifest_is_both_mandatory_and_a_patch(mod: ModuleType) -> None:
    """The shape the 0.3.3 -> 0.3.4 migration actually needs."""
    m = _manifest(mod, min_build=26, min_base="0.3.3")
    assert m["requires"] == {"min_base": "0.3.3", "min_build": 26}
    # mandatory needs manifest.build >= min_build, or isMandatoryUpdate returns False
    assert m["build"] >= m["requires"]["min_build"]
