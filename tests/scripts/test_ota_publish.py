"""Tests for ``scripts/ota_publish.py``.

Covers the pure pieces: version parsing, monotonic build numbering, manifest
assembly, asset naming/URLs, sha256, and snapshot packing (including the
__pycache__ / egg-info exclusions). #2307 adds the PyPI trigger; there the gh,
git and network side is exercised through fakes, never for real.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
import subprocess
import tarfile
import urllib.error
from email.message import Message
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

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
# resolve_build_number (#2206)
# --------------------------------------------------------------------------- #
def test_build_number_follows_the_sequence_without_an_override(mod: ModuleType) -> None:
    assert mod.resolve_build_number(None, 31, 30, None) == 32


def test_override_names_the_build_outright(mod: ModuleType) -> None:
    assert mod.resolve_build_number(40, 31, 30, None) == 40


def test_override_may_publish_below_the_sequence_for_an_older_base(mod: ModuleType) -> None:
    # The notice window: above what 0.3.3 clients applied (25), at or below the
    # 0.3.4 installer baseline (30) so 0.3.4 clients still evaluate up-to-date.
    assert mod.resolve_build_number(28, 31, 30, "0.3.3") == 28


def test_override_below_the_sequence_is_refused_without_a_target_base(mod: ModuleType) -> None:
    # Publishing backwards with no older population named would either reach
    # nobody or replace a working SPA with the notice.
    with pytest.raises(ValueError, match="--min-base"):
        mod.resolve_build_number(28, 31, 30, None)


def test_override_equal_to_the_sequence_is_refused_without_a_target_base(mod: ModuleType) -> None:
    with pytest.raises(ValueError, match="at or below"):
        mod.resolve_build_number(31, 31, 30, None)


def test_override_below_the_sequence_counts_the_baseline_too(mod: ModuleType) -> None:
    # No patch published yet, but a shipped installer already reports build 30.
    with pytest.raises(ValueError, match=r"sequence \(30\)"):
        mod.resolve_build_number(30, None, 30, None)


def test_override_must_be_a_positive_build(mod: ModuleType) -> None:
    with pytest.raises(ValueError, match="positive"):
        mod.resolve_build_number(0, 31, 30, "0.3.3")


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
# Every file ota_publish.SHELL_FILES names, split by how the fake writes it.
# test_fake_desktop_covers_every_published_file keeps the two in step.
_SHELL_TEXT_FILES = (
    "main.js",
    "menu.js",
    "ota.js",
    "runtime-port.js",
    "background-mode.js",
    "installer.js",
    "preload.js",
    "connection-preload.js",
    "splash.html",
    "connection.html",
)
_SHELL_ASSETS = (
    "assets/icon.png",
    "assets/tray.png",
    "assets/tray@2x.png",
    "assets/trayTemplate.png",
    "assets/trayTemplate@2x.png",
)


def _fake_desktop(tmp_path: Path) -> Path:
    """A desktop/ directory holding just the files a snapshot deals with."""
    desktop = tmp_path / "desktop"
    desktop.mkdir(exist_ok=True)
    for name in _SHELL_TEXT_FILES:
        (desktop / name).write_text("// " + name, encoding="utf-8")
    (desktop / "assets").mkdir(exist_ok=True)
    for name in _SHELL_ASSETS:
        (desktop / name).write_bytes(b"PNG-stub")
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
    for name in _SHELL_TEXT_FILES:
        assert f"shell/{name}" in names


def test_fake_desktop_covers_every_published_file(mod: ModuleType) -> None:
    # The fixture must stay a complete shell, or snapshot tests would pass
    # against a list that no longer matches what is actually published.
    assert set(_SHELL_TEXT_FILES + _SHELL_ASSETS) == set(mod.SHELL_FILES)


def test_every_relative_require_of_the_shell_is_published(mod: ModuleType) -> None:
    # #2280: a module the shell requires that a patch does not carry crashes
    # every patched launch before any window appears -- the failure the #2159
    # menu.js drift nearly shipped. Every published module is scanned, not only
    # main.js and menu.js (AU1/AU2 P3-1).
    repo_root = Path(__file__).resolve().parents[2]
    modules = [name for name in mod.SHELL_FILES if name.endswith(".js")]
    assert "background-mode.js" in modules and "ota.js" in modules
    for name in modules:
        source = (repo_root / "desktop" / name).read_text(encoding="utf-8")
        for required in re.findall(r"""require\(["']\./([^"']+)["']\)""", source):
            file = required if required.endswith((".js", ".json")) else f"{required}.js"
            assert file in mod.SHELL_FILES, f"{name} requires ./{required}, which SHELL_FILES lacks"


def test_every_asset_a_published_page_references_is_published(mod: ModuleType) -> None:
    # #2280 (AU1/AU2 P3-1): a patched page resolves a relative src/href against
    # the patch directory, so the asset has to travel with it -- the #2097
    # broken splash logo, generalised to every published page.
    repo_root = Path(__file__).resolve().parents[2]
    pages = [name for name in mod.SHELL_FILES if name.endswith(".html")]
    assert "connection.html" in pages and "splash.html" in pages
    for name in pages:
        source = (repo_root / "desktop" / name).read_text(encoding="utf-8")
        for ref in re.findall(r'\b(?:src|href)="([^"#:]+)"', source):
            assert ref in mod.SHELL_FILES, f"{name} references {ref}, which SHELL_FILES lacks"


def test_snapshot_carries_the_tray_images(mod: ModuleType, tmp_path: Path) -> None:
    # #2280: main.js loads the tray images next to itself, and Electron picks
    # the @2x siblings up on its own on HiDPI displays. A patch without them
    # shows an empty tray icon in external-AI mode.
    names = _snapshot_names(mod, tmp_path)
    for name in (
        "assets/tray.png",
        "assets/tray@2x.png",
        "assets/trayTemplate.png",
        "assets/trayTemplate@2x.png",
    ):
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


def test_reinstall_notice_leads_with_the_address(mod: ModuleType) -> None:
    """The address comes before the release summary, not after it (#2183).

    This page exists to hand over one address. The summary was added during the
    0.3.4 migration and initially sat above it, so the only action the user has
    to take waited behind three sections of release notes. Ordering is a layout
    choice with no runtime signal, which is exactly the kind that gets undone by
    accident in a later copy edit.
    """
    html = mod.render_reinstall_notice("https://example.test/download", "x")
    address_at = html.index('id="url"')
    summary_at = html.index("<h2>")
    assert address_at < summary_at, "the release summary was moved above the address"


def test_reinstall_notice_says_what_to_do_with_the_address(mod: ModuleType) -> None:
    # A bare field and a Copy button do not say where to paste it. The page is
    # shown inside the app, so "open this in a browser" is not obvious.
    html = mod.render_reinstall_notice("https://example.test/download", "x")
    assert "browser" in html.lower()


def test_notice_names_the_readers_base_not_the_builds(mod: ModuleType) -> None:
    # The page reaches 0.3.3 clients; 0.3.4 is what it sends them to download.
    assert mod.notice_version_line("0.3.3", "0.3.4", 28) == "Installed 0.3.3 · update 28"


def test_notice_falls_back_to_the_builds_base_without_a_target(mod: ModuleType) -> None:
    assert mod.notice_version_line(None, "0.3.4", 28) == "Installed 0.3.4 · update 28"


def test_reinstall_notice_does_not_promise_notarization(mod: ModuleType) -> None:
    """A drafted section claimed macOS builds open without a right-click.

    The 0.3.4 dmgs ship signed but not stapled, so that is false until the
    staple workflow has run and the release assets have been replaced. A notice
    page is the wrong place to make a claim about the build the user is being
    sent to download, since the page outlives whatever was true when it was
    written.
    """
    html = mod.render_reinstall_notice("https://example.test/download", "x").lower()
    assert "notarized" not in html
    assert "right-click" not in html


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


# --------------------------------------------------------------------------- #
# #2307: every OTA build also publishes the open-source wheel to PyPI.
# --------------------------------------------------------------------------- #
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHA = "0123456789abcdef0123456789abcdef01234567"


class _Probe:
    """Stands in for the PyPI and git lookups, recording whether they were asked."""

    def __init__(self, *, on_pypi: bool | None = False, on_main: bool = True) -> None:
        self._on_pypi = on_pypi
        self._on_main = on_main
        self.calls: list[str] = []

    def on_pypi(self) -> bool | None:
        self.calls.append("pypi")
        return self._on_pypi

    def head_on_main(self) -> bool:
        self.calls.append("git")
        return self._on_main


def _decide(mod: ModuleType, probe: _Probe | None = None, **overrides: Any) -> tuple[Any, _Probe]:
    probe = probe or _Probe()
    args: dict[str, Any] = {
        "dry_run": False,
        "no_pypi": False,
        "reinstall_notice": False,
        "build": 29,
        "latest_published_build": 28,
        "baseline_build": 0,
        "version": "0.3.4a29",
        "on_pypi": probe.on_pypi,
        "head_on_main": probe.head_on_main,
    }
    args.update(overrides)
    return mod.decide_pypi_publish(**args), probe


def test_an_ordinary_publish_goes_to_pypi(mod: ModuleType) -> None:
    decision, probe = _decide(mod)
    assert decision.action == mod.PYPI_TRIGGER
    assert probe.calls == ["pypi", "git"]


def test_a_dry_run_never_reaches_pypi(mod: ModuleType) -> None:
    decision, probe = _decide(mod, dry_run=True)
    assert decision.action == mod.PYPI_SKIP
    assert "--dry-run" in decision.reason
    assert probe.calls == []


def test_no_pypi_opts_out(mod: ModuleType) -> None:
    decision, probe = _decide(mod, no_pypi=True)
    assert decision.action == mod.PYPI_SKIP
    assert "--no-pypi" in decision.reason
    assert probe.calls == []


def test_a_reinstall_notice_is_not_published(mod: ModuleType) -> None:
    # That snapshot's SPA is a page telling old clients to reinstall, so its
    # build number does not stand for a release of the product.
    decision, probe = _decide(mod, reinstall_notice=True)
    assert decision.action == mod.PYPI_SKIP
    assert "reinstall notice" in decision.reason
    assert probe.calls == []


@pytest.mark.parametrize("build", [28, 20])
def test_a_backfill_is_not_published(mod: ModuleType, build: int) -> None:
    # --build at or below the latest published build: PyPI may already hold the
    # version, and otherwise would list it out of order. Nothing is looked up.
    decision, probe = _decide(mod, build=build, version=f"0.3.4a{build}")
    assert decision.action == mod.PYPI_SKIP
    assert "backfill" in decision.reason
    assert probe.calls == []


def test_a_backfill_counts_the_installer_baseline_too(mod: ModuleType) -> None:
    # The same sequence resolve_build_number guards: a shipped installer
    # already reports build 30 even before any patch is published.
    decision, _ = _decide(mod, build=30, latest_published_build=None, baseline_build=30, version="0.3.4a30")
    assert decision.action == mod.PYPI_SKIP


def test_a_named_build_above_the_sequence_is_published(mod: ModuleType) -> None:
    decision, _ = _decide(mod, build=40, version="0.3.4a40")
    assert decision.action == mod.PYPI_TRIGGER


def test_a_version_pypi_already_has_is_skipped(mod: ModuleType) -> None:
    # PyPI versions are immutable; a second upload is rejected, so do not try.
    decision, probe = _decide(mod, _Probe(on_pypi=True))
    assert decision.action == mod.PYPI_SKIP
    assert "already on PyPI" in decision.reason
    assert probe.calls == ["pypi"]


def test_a_head_that_is_not_on_main_is_refused(mod: ModuleType) -> None:
    # The workflow builds the commit from GitHub: an unpushed commit cannot be
    # built there, and an unmerged one must never become a permanent version.
    decision, _ = _decide(mod, _Probe(on_main=False))
    assert decision.action == mod.PYPI_REFUSE
    assert "origin/main" in decision.reason


def test_an_unreachable_pypi_still_triggers(mod: ModuleType) -> None:
    # The workflow repeats the existence check before it builds, so an offline
    # lookup here must not cost the release.
    decision, _ = _decide(mod, _Probe(on_pypi=None))
    assert decision.action == mod.PYPI_TRIGGER
    assert "checks again" in decision.reason


def test_the_pypi_version_is_the_wheel_version(mod: ModuleType) -> None:
    # 0.3.4-alpha-build0012 is 0.3.4a12: the number format_pep440 stamps.
    assert mod.pypi_version("0.3.4", "alpha", 12) == "0.3.4a12"
    assert mod.pypi_version("0.3.4", "beta", 3) == "0.3.4b3"
    assert mod.pypi_json_url("0.3.4a12") == "https://pypi.org/pypi/scistudio/0.3.4a12/json"


def test_the_dispatch_command(mod: ModuleType) -> None:
    assert mod.pypi_workflow_command("o/r", _SHA, 29, "alpha") == [
        "gh",
        "workflow",
        "run",
        "pypi-publish.yml",
        "--repo",
        "o/r",
        "--ref",
        "main",
        "-f",
        f"ref={_SHA}",
        "-f",
        "build_number=29",
        "-f",
        "channel=alpha",
    ]


# The workflow file and the script meet across a YAML boundary. These keep the
# two from drifting, the way the shell tests keep SHELL_FILES and the asar list
# in step.
def _pypi_workflow(mod: ModuleType) -> dict[Any, Any]:
    path = _REPO_ROOT / ".github" / "workflows" / mod.PYPI_WORKFLOW
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_the_dispatch_sends_exactly_the_workflows_inputs(mod: ModuleType) -> None:
    workflow = _pypi_workflow(mod)
    triggers = workflow.get("on", workflow.get(True))  # PyYAML reads a bare `on:` key as True
    declared = set(triggers["workflow_dispatch"]["inputs"])
    command = mod.pypi_workflow_command("o/r", _SHA, 29, "alpha")
    sent = {command[i + 1].split("=", 1)[0] for i, part in enumerate(command) if part == "-f"}
    assert sent == declared


def test_the_publish_job_matches_the_trusted_publisher(mod: ModuleType) -> None:
    # PyPI's trusted publisher for `scistudio` names workflow pypi-publish.yml
    # and environment `pypi`. Renaming either fails the upload with an OIDC
    # error, and a stored token would defeat the point.
    job = _pypi_workflow(mod)["jobs"]["publish-pypi"]
    assert job["environment"] == "pypi"
    assert job["permissions"] == {"id-token": "write"}
    publish = [step for step in job["steps"] if str(step.get("uses", "")).startswith("pypa/gh-action-pypi-publish@")]
    assert len(publish) == 1
    assert "password" not in (publish[0].get("with") or {})


class _Response:
    status = 200

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def test_version_on_pypi_reads_the_json_api(mod: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def fake_urlopen(url: str, timeout: float) -> _Response:
        seen.append(url)
        return _Response()

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    assert mod.version_on_pypi("0.3.4a29") is True
    assert seen == ["https://pypi.org/pypi/scistudio/0.3.4a29/json"]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (urllib.error.HTTPError("u", 404, "Not Found", Message(), None), False),
        (urllib.error.HTTPError("u", 503, "Unavailable", Message(), None), None),
        (urllib.error.URLError("offline"), None),
        (TimeoutError("slow"), None),
    ],
)
def test_version_on_pypi_tells_absent_from_unknown(
    mod: ModuleType, monkeypatch: pytest.MonkeyPatch, error: Exception, expected: bool | None
) -> None:
    def fake_urlopen(url: str, timeout: float) -> _Response:
        raise error

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    assert mod.version_on_pypi("0.3.4a29") is expected


class _FakeRun:
    """Answers the git and gh commands the PyPI trigger runs; runs nothing."""

    def __init__(self, *, on_main: bool = True, dispatch_rc: int = 0) -> None:
        self.on_main = on_main
        self.dispatch_rc = dispatch_rc
        self.commands: list[list[str]] = []

    def __call__(self, cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        self.commands.append(cmd)
        if "rev-parse" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=f"{_SHA}\n", stderr="")
        if "merge-base" in cmd:
            return subprocess.CompletedProcess(cmd, 0 if self.on_main else 1, stdout="", stderr="")
        if cmd[:3] == ["gh", "workflow", "run"]:
            stderr = "HTTP 404: workflow pypi-publish.yml not found" if self.dispatch_rc else ""
            return subprocess.CompletedProcess(cmd, self.dispatch_rc, stdout="", stderr=stderr)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    def dispatched(self) -> list[list[str]]:
        return [cmd for cmd in self.commands if cmd[:3] == ["gh", "workflow", "run"]]


def _trigger(mod: ModuleType, **overrides: Any) -> Any:
    args: dict[str, Any] = {
        "repo": "o/r",
        "channel": "alpha",
        "base": "0.3.4",
        "build": 29,
        "latest_published_build": 28,
        "baseline_build": 0,
    }
    args.update(overrides)
    return mod.trigger_pypi_publish(**args)


def test_the_trigger_dispatches_the_head_commit(
    mod: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run = _FakeRun()
    monkeypatch.setattr(mod, "_run", run)
    monkeypatch.setattr(mod, "version_on_pypi", lambda version: False)

    decision = _trigger(mod)

    expected = mod.pypi_workflow_command("o/r", _SHA, 29, "alpha")
    assert decision.action == mod.PYPI_TRIGGER
    assert run.dispatched() == [expected]
    out = capsys.readouterr().out
    # The exact version, the exact command, and where to watch it.
    assert "scistudio 0.3.4a29" in out
    assert shlex.join(expected) in out
    assert "gh run watch" in out


def test_a_refused_trigger_prints_the_command_to_run_later(
    mod: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run = _FakeRun(on_main=False)
    monkeypatch.setattr(mod, "_run", run)
    monkeypatch.setattr(mod, "version_on_pypi", lambda version: False)

    decision = _trigger(mod)

    assert decision.action == mod.PYPI_REFUSE
    assert run.dispatched() == []
    out = capsys.readouterr().out
    assert "NOT triggered" in out
    assert shlex.join(mod.pypi_workflow_command("o/r", _SHA, 29, "alpha")) in out


def test_a_failed_dispatch_does_not_fail_the_publish(
    mod: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The OTA build is already live; raising here would read as if it were not.
    monkeypatch.setattr(mod, "_run", _FakeRun(dispatch_rc=1))
    monkeypatch.setattr(mod, "version_on_pypi", lambda version: False)

    decision = _trigger(mod)

    assert decision.action == mod.PYPI_REFUSE
    assert "workflow pypi-publish.yml not found" in decision.reason
    assert "NOT dispatched" in capsys.readouterr().out


def test_a_skip_touches_neither_git_nor_pypi(mod: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    run = _FakeRun()
    monkeypatch.setattr(mod, "_run", run)

    def no_network(version: str) -> bool | None:
        raise AssertionError("PyPI must not be asked for a skipped build")

    monkeypatch.setattr(mod, "version_on_pypi", no_network)

    assert _trigger(mod, no_pypi=True).action == mod.PYPI_SKIP
    assert run.commands == []


def _publish_side(mod: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, events: list[str]) -> Path:
    """Fake every release-side effect of main() and return a staged src dir."""
    src = tmp_path / "staged" / "src"
    (src / "scistudio").mkdir(parents=True)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(mod.tempfile, "mkdtemp", lambda prefix="": str(work))
    monkeypatch.setattr(mod, "make_snapshot", lambda src_dir, out, **kwargs: out.write_bytes(b"snapshot"))
    monkeypatch.setattr(mod, "fetch_latest_build", lambda repo, tag: 28)
    monkeypatch.setattr(mod, "ensure_release", lambda repo, tag, channel: events.append("ensure"))
    monkeypatch.setattr(mod, "upload_assets", lambda repo, tag, files: events.append("upload"))
    monkeypatch.setattr(mod, "version_on_pypi", lambda version: False)
    return src


def test_main_publishes_to_pypi_after_the_upload(
    mod: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    src = _publish_side(mod, monkeypatch, tmp_path, events)
    run = _FakeRun()
    monkeypatch.setattr(mod, "_run", run)
    trigger = mod.trigger_pypi_publish

    def spy(**kwargs: Any) -> Any:
        events.append("pypi")
        return trigger(**kwargs)

    monkeypatch.setattr(mod, "trigger_pypi_publish", spy)

    assert mod.main(["--channel", "alpha", "--src", str(src), "--yes"]) == 0

    assert events == ["ensure", "upload", "pypi"]
    # Latest published is 28, so this is build 29 on whatever base the checkout carries.
    assert run.dispatched() == [mod.pypi_workflow_command(mod.DEFAULT_REPO, _SHA, 29, "alpha")]


def test_main_never_reaches_pypi_when_the_upload_fails(
    mod: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    src = _publish_side(mod, monkeypatch, tmp_path, [])
    run = _FakeRun()
    monkeypatch.setattr(mod, "_run", run)

    def failed_upload(repo: str, tag: str, files: list[Path]) -> None:
        raise RuntimeError("Asset upload failed: HTTP 502")

    monkeypatch.setattr(mod, "upload_assets", failed_upload)

    with pytest.raises(RuntimeError, match="Asset upload failed"):
        mod.main(["--channel", "alpha", "--src", str(src), "--yes"])
    assert run.dispatched() == []


def test_main_dry_run_never_reaches_pypi(
    mod: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src = _publish_side(mod, monkeypatch, tmp_path, [])
    run = _FakeRun()
    monkeypatch.setattr(mod, "_run", run)

    assert mod.main(["--channel", "alpha", "--src", str(src), "--dry-run"]) == 0

    assert run.commands == []
    assert "PyPI: skipped -- --dry-run" in capsys.readouterr().out


def test_main_no_pypi_uploads_without_dispatching(
    mod: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    src = _publish_side(mod, monkeypatch, tmp_path, events)
    run = _FakeRun()
    monkeypatch.setattr(mod, "_run", run)

    assert mod.main(["--channel", "alpha", "--src", str(src), "--yes", "--no-pypi"]) == 0

    assert events == ["ensure", "upload"]
    assert run.dispatched() == []


# --------------------------------------------------------------------------- #
# #2396: the manifest names the next installer
# --------------------------------------------------------------------------- #
def _release(**overrides: Any) -> dict[str, Any]:
    version = "0.3.5-beta-build0035"
    names = [
        f"SciStudio-{version}-arm64.dmg",
        f"SciStudio-{version}-x64.dmg",
        f"SciStudio-Setup-{version}.exe",
        f"SciStudio-{version}.AppImage",
        # Present on real releases and must not be mistaken for an installer.
        "scistudio-0.3.5b35-py3-none-any.whl",
        "scistudio-0.3.5b35.tar.gz",
    ]
    release: dict[str, Any] = {
        "tag_name": "v0.3.5-beta",
        "draft": False,
        "html_url": "https://github.com/o/r/releases/tag/v0.3.5-beta",
        "assets": [
            {
                "name": name,
                "size": 1000 + index,
                "digest": "sha256:" + f"{index:x}" * 64,
                "browser_download_url": f"https://github.com/o/r/releases/download/v0.3.5-beta/{name}",
            }
            for index, name in enumerate(names, start=1)
        ],
    }
    release.update(overrides)
    return release


def test_installer_from_release_maps_every_platform(mod: ModuleType) -> None:
    installer = mod.installer_from_release(_release())
    assert installer["version"] == "0.3.5-beta-build0035"
    assert installer["release_page"] == "https://github.com/o/r/releases/tag/v0.3.5-beta"
    assert set(installer["assets"]) == {"darwin-arm64", "darwin-x64", "win32-x64", "linux-x64"}
    arm = installer["assets"]["darwin-arm64"]
    assert arm == {
        "url": "https://github.com/o/r/releases/download/v0.3.5-beta/SciStudio-0.3.5-beta-build0035-arm64.dmg",
        "sha256": "1" * 64,
        "size": 1001,
    }
    assert installer["assets"]["win32-x64"]["url"].endswith("SciStudio-Setup-0.3.5-beta-build0035.exe")
    assert installer["assets"]["linux-x64"]["url"].endswith("SciStudio-0.3.5-beta-build0035.AppImage")


def test_installer_platform_keys_match_the_shell(mod: ModuleType) -> None:
    # desktop/installer.js PLATFORM_KEYS is what the shell looks the asset up by.
    source = (_SCRIPT_PATH.parents[1] / "desktop" / "installer.js").read_text()
    keys = re.search(r"PLATFORM_KEYS = Object\.freeze\(\[([^\]]*)\]\)", source)
    assert keys is not None
    assert set(re.findall(r'"([^"]+)"', keys.group(1))) == set(mod.INSTALLER_ASSET_PATTERNS)


def test_installer_from_release_refuses_a_draft(mod: ModuleType) -> None:
    with pytest.raises(ValueError, match="draft"):
        mod.installer_from_release(_release(draft=True))


def test_installer_from_release_refuses_a_missing_platform(mod: ModuleType) -> None:
    release = _release()
    release["assets"] = [asset for asset in release["assets"] if not asset["name"].endswith(".AppImage")]
    with pytest.raises(ValueError, match="no asset for linux-x64"):
        mod.installer_from_release(release)


def test_installer_from_release_refuses_an_asset_without_a_digest(mod: ModuleType) -> None:
    release = _release()
    release["assets"][2]["digest"] = None
    with pytest.raises(ValueError, match="no sha256 digest"):
        mod.installer_from_release(release)


def test_installer_from_release_refuses_assets_of_different_versions(mod: ModuleType) -> None:
    release = _release()
    release["assets"][1]["name"] = "SciStudio-0.3.5-beta-build0034-x64.dmg"
    with pytest.raises(ValueError, match="disagree on the version"):
        mod.installer_from_release(release)


def test_build_manifest_carries_the_installer_only_when_given(mod: ModuleType) -> None:
    common: dict[str, Any] = {
        "channel": "alpha",
        "base": "0.3.5",
        "build": 33,
        "url": "https://x/backend-build33.tar.gz",
        "sha256": "0" * 64,
        "size": 1,
        "notes": "",
        "published_at": "2026-09-15T00:00:00Z",
    }
    assert "installer" not in mod.build_manifest(**common)
    installer = mod.installer_from_release(_release())
    assert mod.build_manifest(**common, installer=installer)["installer"] == installer


def test_main_installer_release_lands_in_the_manifest(
    mod: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src = _publish_side(mod, monkeypatch, tmp_path, [])
    monkeypatch.setattr(mod, "_run", _FakeRun())
    asked: list[tuple[str, str]] = []

    def fake_fetch(repo: str, tag: str) -> dict[str, Any]:
        asked.append((repo, tag))
        return _release()

    monkeypatch.setattr(mod, "fetch_release", fake_fetch)

    assert mod.main(["--channel", "alpha", "--src", str(src), "--dry-run", "--installer-release", "v0.3.5-beta"]) == 0

    assert asked == [(mod.DEFAULT_REPO, "v0.3.5-beta")]
    manifest = json.loads((tmp_path / "work" / "manifest.json").read_text())
    assert manifest["installer"]["version"] == "0.3.5-beta-build0035"
    assert "Manifest names installer 0.3.5-beta-build0035" in capsys.readouterr().out


def test_main_installer_release_that_is_incomplete_stops_the_publish(
    mod: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    src = _publish_side(mod, monkeypatch, tmp_path, events)
    monkeypatch.setattr(mod, "_run", _FakeRun())
    monkeypatch.setattr(mod, "fetch_release", lambda repo, tag: _release(draft=True))

    with pytest.raises(SystemExit):
        mod.main(["--channel", "alpha", "--src", str(src), "--yes", "--installer-release", "v0.3.5-beta"])
    assert events == []
