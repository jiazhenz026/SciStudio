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
    panel_asset_security_headers,
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


def test_an_alternate_data_stream_on_a_panel_file_is_refused(tmp_path: Path) -> None:
    """``index.html:hidden.json`` names a second, invisible file (#2229).

    An NTFS alternate data stream hangs off a file the panel directory *does*
    hold, so it is inside the root and survives every containment check. It is
    also not in the directory listing, and the suffix allowlist sees the
    stream's name rather than the file's — so a ``.json`` stream attached to
    ``index.html`` was resolved and served in full. Refusing ``:`` in a path
    segment closes it, and closes ``index.html::$DATA`` — the same file reached
    past a name the allowlist never inspected — with it.
    """
    root = tmp_path / "project"
    root.mkdir()
    directory = write_panel(root, "probe.ads")

    if sys.platform == "win32":
        with open(str(directory / "index.html") + ":hidden.json", "w", encoding="utf-8") as handle:
            handle.write('{"token": "secret"}')
        # The stream is genuinely readable, so the refusal below is the rule
        # rather than the file being absent.
        with open(str(directory / "index.html") + ":hidden.json", encoding="utf-8") as handle:
            assert "secret" in handle.read()
    else:  # pragma: no cover - the colon is an ordinary character here
        # On a platform with no streams the same request is an ordinary file
        # name. It is refused anyway: the rule must not change meaning between
        # the developer's machine and the user's.
        (directory / "index.html:hidden.json").write_text("{}", encoding="utf-8")

    for asked in ("index.html:hidden.json", "index.html::$DATA"):
        with pytest.raises(MissingBundleError, match="escapes confinement root"):
            resolve_confined_asset(directory, asked, panel_id="probe.ads")


def test_a_nul_in_the_asset_path_is_refused_by_name(tmp_path: Path) -> None:
    """A NUL truncates a name at the syscall boundary, so it never gets there.

    Without the check the byte reached ``resolve()``, which on Windows quietly
    turned it into a different file name — a request answered by a path nobody
    asked for. It is now a refusal that says what was wrong with the request.
    """
    root = tmp_path / "project"
    root.mkdir()
    directory = write_panel(root, "probe.nul")

    with pytest.raises(MissingBundleError, match="NUL"):
        resolve_confined_asset(directory, "index\x00.html", panel_id="probe.nul")


def test_a_traversal_never_reaches_the_filesystem(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The containment is lexical first, and only then resolve-then-contain.

    ``Path.resolve`` walks the filesystem, following every symlink on the way.
    A boundary enforced only *after* that walk is a boundary the walk has
    already crossed, so a client-chosen traversal is refused before the walk
    happens at all. Measured by counting the walks: exactly one, for the root
    the route was handed, and none for the path the client sent.
    """
    root = tmp_path / "project"
    root.mkdir()
    directory = write_panel(root, "probe.lexical")
    (tmp_path / "secret.html").write_text("secret\n", encoding="utf-8")

    walked: list[str] = []
    real_resolve = Path.resolve

    def counting_resolve(self: Path, *args: object, **kwargs: object) -> Path:
        walked.append(str(self))
        return real_resolve(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "resolve", counting_resolve)

    with pytest.raises(MissingBundleError, match="escapes confinement root"):
        resolve_confined_asset(directory, "../../secret.html", panel_id="probe.lexical")

    assert walked == [str(directory)]


def test_two_dots_anywhere_in_the_request_are_refused(tmp_path: Path) -> None:
    """The lexical rule is the two characters, not the traversal segment.

    Stricter than the property that matters, on purpose: a panel asset named
    ``figure..cache.css`` has no legitimate use, and a rule about the characters is one
    a reader can check by looking rather than by simulating a join. The file
    below exists and is inside the root, so the refusal is the rule.
    """
    root = tmp_path / "project"
    root.mkdir()
    directory = write_panel(root, "probe.dots")
    (directory / "figure..cache.css").write_text("body{}", encoding="utf-8")

    with pytest.raises(MissingBundleError, match="escapes confinement root"):
        resolve_confined_asset(directory, "figure..cache.css", panel_id="probe.dots")


def test_the_ordinary_shapes_a_panel_asks_for_still_resolve(tmp_path: Path) -> None:
    """The lexical check refuses traversals, not the paths panels actually use."""
    root = tmp_path / "project"
    root.mkdir()
    directory = write_panel(root, "probe.ordinary")
    (directory / "nested").mkdir()
    (directory / "nested" / "chart.css").write_text("body{}", encoding="utf-8")

    for asked in ("nested/chart.css", "./nested/chart.css", "nested//chart.css", "/nested/chart.css"):
        served = resolve_confined_asset(directory, asked, panel_id="probe.ordinary")
        assert served.path == (directory / "nested" / "chart.css").resolve()
        assert served.media_type == "text/css"


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


# ---------------------------------------------------------------------------
# The boundary the response carries (#2229)
# ---------------------------------------------------------------------------


def test_a_served_document_carries_the_frames_own_sandbox() -> None:
    """FR-008's boundary is one attribute on one code path in the host; the
    served document restates it so it holds however the document is reached.

    Here rather than beside the confinement tests only in file order: it is the
    same module, deliberately, because three routes serve these documents and a
    boundary that held on one of them would be one a document reaches around by
    being requested through another.
    """
    headers = panel_asset_security_headers("text/html; charset=utf-8")

    assert headers["Content-Security-Policy"] == "sandbox allow-scripts"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["X-Content-Type-Options"] == "nosniff"


def test_the_documents_sandbox_is_neither_stricter_nor_weaker_than_the_frames() -> None:
    """Stricter and the panel cannot run; weaker and it regains the origin the
    whole boundary exists to withhold."""
    policy = panel_asset_security_headers("text/html")["Content-Security-Policy"]

    assert "allow-scripts" in policy
    assert "allow-same-origin" not in policy


@pytest.mark.parametrize(
    "media_type",
    ["text/javascript", "application/json", "image/svg+xml", "text/css", "application/octet-stream"],
)
def test_a_non_document_asset_is_hardened_but_not_sandboxed(media_type: str) -> None:
    """``nosniff`` rides on everything — a ``.json`` sniffed as HTML is the same
    problem — but the sandbox directive belongs to the document."""
    headers = panel_asset_security_headers(media_type)

    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" not in headers


def test_the_route_never_forbids_framing() -> None:
    """The mechanism *is* a framed document; ``X-Frame-Options: DENY`` would
    break every panel, so it is deliberately absent."""
    for media_type in ("text/html", "text/javascript"):
        assert "X-Frame-Options" not in panel_asset_security_headers(media_type)
