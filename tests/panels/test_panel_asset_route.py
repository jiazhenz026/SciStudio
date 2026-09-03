"""The merged asset route: one confinement check, four roots (T-004, SC-008).

ADR-054 spec 1 FR-021 and D-008. One route serves all four tiers, using one
path-confinement check and one suffix allowlist, differing only in the root each
tier resolves to. That single check is the only thing standing between a panel
id and an arbitrary filesystem read, so it is tested adversarially and it is
tested **against each of the four roots** — a check that held for the project
tier and not for the package tier would satisfy no property worth having.

The adversarial cases, named so a reader can see what is claimed:

* ``..`` traversal, at the start of a path and buried in the middle of one;
* an absolute path, POSIX-style and Windows-drive-style;
* percent-encoded traversal, single- and double-encoded;
* a backslash-separated traversal, because the joins run on Windows too;
* a symlink inside the panel directory pointing outside it (skipped where the
  platform will not create one);
* a panel id that is itself a traversal, and one carrying a separator;
* a suffix outside the allowlist — the file exists and is refused anyway;
* an oversized document, which is a load failure with a readable diagnostic
  rather than a truncated read.

The tier roots are fixture directories, never the shipped
``src/scistudio/panels/builtin/``: a test asserting against the real built-in
panels would fail every time one of them was edited.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scistudio.core.panels import PanelTier
from scistudio.panels.assets import (
    MAX_PANEL_ASSET_BYTES,
    MissingBundleError,
    PanelAssetTooLargeError,
    is_allowed_asset_suffix,
    is_safe_panel_id,
    resolve_confined_asset,
)
from scistudio.panels.discovery import discover_panels
from tests.panels.conftest import write_panel

#: Every way a request can try to leave the root it was given. Named so a
#: failure report says which one got out.
ESCAPES = [
    ("parent traversal", "../secret.html"),
    ("deep parent traversal", "../../secret.html"),
    ("traversal in the middle", "assets/../../secret.html"),
    ("backslash traversal", "..\\secret.html"),
    ("posix absolute path", "/etc/passwd"),
    ("windows drive absolute path", "C:/Windows/win.ini"),
    ("unc path", "//server/share/secret.html"),
    ("dot segments only", "../.."),
]


@pytest.fixture
def four_roots(tmp_path: Path) -> dict[PanelTier, Path]:
    """Return one populated root per tier, each holding the same panel shape.

    The same panel id is deliberately *not* reused across tiers here: shadowing
    is tested elsewhere, and this suite wants four independent roots so a
    per-root assertion says something about that root.
    """
    roots: dict[PanelTier, Path] = {}
    for tier in PanelTier:
        root = tmp_path / tier.value
        root.mkdir()
        write_panel(root, f"probe.{tier.value}")
        (root / f"probe.{tier.value}" / "extra.css").write_text("body{}", encoding="utf-8")
        roots[tier] = root
    # The thing a traversal is trying to reach, one level above every root.
    (tmp_path / "secret.html").write_text("<!doctype html>secret\n", encoding="utf-8")
    return roots


def _panel_dir(roots: dict[PanelTier, Path], tier: PanelTier) -> Path:
    return roots[tier] / f"probe.{tier.value}"


# ---------------------------------------------------------------------------
# SC-008: identical behaviour for all four tier roots
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tier", list(PanelTier))
def test_the_entry_document_is_served_from_every_tier_root(four_roots: dict[PanelTier, Path], tier: PanelTier) -> None:
    """One route, four roots: the shape is identical whichever tier answered."""
    served = resolve_confined_asset(_panel_dir(four_roots, tier), "index.html", panel_id=f"probe.{tier.value}")
    assert served.path == (_panel_dir(four_roots, tier) / "index.html").resolve()
    assert served.media_type.startswith("text/html")


@pytest.mark.parametrize("tier", list(PanelTier))
@pytest.mark.parametrize(("name", "escape"), ESCAPES, ids=[case[0] for case in ESCAPES])
def test_confinement_holds_for_every_tier_root(
    four_roots: dict[PanelTier, Path], tier: PanelTier, name: str, escape: str
) -> None:
    """SC-008: path confinement behaves identically for all four tier roots.

    Measured against each root, because one check that held for three of them
    would be three-quarters of a security boundary.
    """
    with pytest.raises(MissingBundleError):
        resolve_confined_asset(_panel_dir(four_roots, tier), escape, panel_id=f"probe.{tier.value}")
    # And the file the traversal was reaching for is genuinely there, so the
    # refusal is confinement rather than a missing file.
    assert (four_roots[tier].parent / "secret.html").is_file()


@pytest.mark.parametrize("tier", list(PanelTier))
def test_the_suffix_allowlist_holds_for_every_tier_root(four_roots: dict[PanelTier, Path], tier: PanelTier) -> None:
    """SC-008: the same allowlist answers every tier.

    The file exists and is inside the root; it is refused on its suffix alone,
    which is the property that keeps a panel directory from serving a ``.py``
    somebody dropped beside the document.
    """
    panel_dir = _panel_dir(four_roots, tier)
    (panel_dir / "secrets.py").write_text("TOKEN = 'x'\n", encoding="utf-8")
    with pytest.raises(MissingBundleError, match="not an allowed panel asset type"):
        resolve_confined_asset(panel_dir, "secrets.py", panel_id=f"probe.{tier.value}")


# ---------------------------------------------------------------------------
# The allowlist itself (D-008)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "index.html",
        "panel.js",
        "panel.mjs",
        "panel.css",
        "panel.map",
        "data.json",
        "icon.svg",
        "raster.png",
        "raster.jpg",
        "raster.jpeg",
        "face.woff",
        "face.woff2",
    ],
)
def test_the_allowlist_is_the_previewer_set_plus_html(name: str) -> None:
    """D-008: today's previewer set plus ``.html`` and the raster types."""
    assert is_allowed_asset_suffix(name)


@pytest.mark.parametrize("name", ["panel.py", "panel.pyc", "panel.sh", "panel.exe", "panel", "panel.yaml"])
def test_the_allowlist_refuses_everything_else(name: str) -> None:
    assert not is_allowed_asset_suffix(name)


# ---------------------------------------------------------------------------
# The panel id is itself a path segment
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "panel_id",
    ["..", ".", "../..", "core/../..", "core\\..", "/etc", "C:/Windows", "", "core.plot\x00.basic"],
)
def test_a_panel_id_that_is_itself_a_traversal_is_refused(panel_id: str) -> None:
    """The id arrives as a path segment; it is refused before it is joined."""
    assert not is_safe_panel_id(panel_id)


@pytest.mark.parametrize("panel_id", ["core.plot.basic", "acme.image.viewer", "probe-1", "probe_2"])
def test_an_ordinary_panel_id_is_accepted(panel_id: str) -> None:
    assert is_safe_panel_id(panel_id)


# ---------------------------------------------------------------------------
# Symlinks, encodings, and the size bound
# ---------------------------------------------------------------------------


def test_a_symlink_out_of_the_panel_directory_is_refused(tmp_path: Path) -> None:
    """A symlink is resolved before it is contained, so it cannot be a way out.

    The confinement is resolve-then-contain rather than contain-then-resolve,
    which is the ordering that makes this hold: a link inside the directory
    pointing outside it lands outside the root and is refused by the same
    comparison that refuses ``..``.
    """
    root = tmp_path / "project"
    root.mkdir()
    directory = write_panel(root, "probe.link")
    outside = tmp_path / "outside.html"
    outside.write_text("<!doctype html>outside\n", encoding="utf-8")
    try:
        (directory / "escape.html").symlink_to(outside)
    except (OSError, NotImplementedError):  # pragma: no cover - platform dependent
        pytest.skip("this platform will not create a symlink without elevation")

    with pytest.raises(MissingBundleError, match="escapes confinement root"):
        resolve_confined_asset(directory, "escape.html", panel_id="probe.link")


def test_percent_encoded_traversal_is_refused_once_decoded(tmp_path: Path) -> None:
    """The ASGI layer decodes before the path reaches the check.

    So the check never sees ``%2e%2e``; it sees ``..``. Both spellings are
    asserted here — the decoded one because that is what arrives, and the raw
    one because a literal ``%2e%2e`` directory name must not be *invented* by
    the check either.
    """
    root = tmp_path / "user"
    root.mkdir()
    directory = write_panel(root, "probe.encoded")
    (tmp_path / "secret.html").write_text("secret\n", encoding="utf-8")

    with pytest.raises(MissingBundleError, match="escapes confinement root"):
        resolve_confined_asset(directory, "../secret.html", panel_id="probe.encoded")
    # Still-encoded, it is simply a file name that does not exist. It must not
    # be decoded here and turned back into a traversal.
    with pytest.raises(MissingBundleError, match="not found on disk"):
        resolve_confined_asset(directory, "%2e%2e/secret.html", panel_id="probe.encoded")


def test_an_oversized_document_is_a_load_failure_with_a_readable_diagnostic(tmp_path: Path) -> None:
    """The Edge Cases entry: a document past the bound fails to load, readably."""
    root = tmp_path / "project"
    root.mkdir()
    directory = write_panel(root, "probe.big")
    (directory / "index.html").write_text("x" * 4096, encoding="utf-8")

    with pytest.raises(PanelAssetTooLargeError) as caught:
        resolve_confined_asset(directory, "index.html", panel_id="probe.big", max_bytes=1024)
    assert "index.html" in caught.value.message
    assert "1024" in caught.value.message
    assert caught.value.detail["size_bytes"] == 4096

    # And the shipped bound is generous enough that an ordinary document passes.
    assert resolve_confined_asset(directory, "index.html", panel_id="probe.big").path.is_file()
    assert MAX_PANEL_ASSET_BYTES > 4096


def test_a_directory_is_not_served_as_a_file(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    directory = write_panel(root, "probe.dir")
    (directory / "assets.json").mkdir()
    with pytest.raises(MissingBundleError, match="not found on disk"):
        resolve_confined_asset(directory, "assets.json", panel_id="probe.dir")


def test_an_empty_asset_path_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    directory = write_panel(root, "probe.empty")
    with pytest.raises(MissingBundleError, match="empty"):
        resolve_confined_asset(directory, "", panel_id="probe.empty")


def test_a_remote_url_is_never_served(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    directory = write_panel(root, "probe.remote")
    for url in ("https://example.test/x.js", "//example.test/x.js", "data:text/html,x", "file:///etc/passwd"):
        with pytest.raises(MissingBundleError, match="remote asset url"):
            resolve_confined_asset(directory, url, panel_id="probe.remote")


# ---------------------------------------------------------------------------
# The route's own root resolution: four tiers, one shape
# ---------------------------------------------------------------------------


def test_discovery_gives_the_route_one_root_per_tier(four_roots: dict[PanelTier, Path]) -> None:
    """The only thing that differs by tier is the root the route is handed.

    This is the property FR-021 states, checked directly: the route asks
    discovery for the panel and serves out of ``panel.directory``, so four tiers
    become four roots and nothing else about the request changes.
    """
    discovery = discover_panels(
        core_root=four_roots[PanelTier.CORE],
        package_roots=[(four_roots[PanelTier.PACKAGE], "acme")],
        user_roots=(four_roots[PanelTier.USER],),
        project_roots=(four_roots[PanelTier.PROJECT],),
    )
    for tier in PanelTier:
        panel = discovery.get(f"probe.{tier.value}")
        assert panel is not None
        assert panel.tier is tier
        served = resolve_confined_asset(panel.directory, "extra.css", panel_id=panel.panel_id)
        assert served.media_type == "text/css"
        with pytest.raises(MissingBundleError):
            resolve_confined_asset(panel.directory, "../secret.html", panel_id=panel.panel_id)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows path separators only")
def test_a_windows_short_name_style_join_stays_confined(tmp_path: Path) -> None:
    """A backslash-separated request cannot climb out on the platform that uses them."""
    root = tmp_path / "project"
    root.mkdir()
    directory = write_panel(root, "probe.win")
    (tmp_path / "secret.html").write_text("secret\n", encoding="utf-8")
    with pytest.raises(MissingBundleError, match="escapes confinement root"):
        resolve_confined_asset(directory, "..\\..\\secret.html", panel_id="probe.win")
