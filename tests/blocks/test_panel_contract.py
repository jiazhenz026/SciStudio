"""Static panel-contract checks (ADR-051, #2196).

Every failure mode the issue tabulates is exercised here at the severity it is
supposed to carry, plus the two drift guards that keep this module honest: the
copied asset-suffix allowlist and the copied remote-URL prefixes must still
equal the originals in :mod:`scistudio.previewers.assets`, which this module
cannot import (``blocks/`` is Layer 2, ``previewers/`` is Layer 4).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scistudio.blocks.base.interactive import PANEL_API_VERSION, PanelManifest
from scistudio.blocks.base.panel_contract import (
    _ALLOWED_ASSET_SUFFIXES,
    _REMOTE_PREFIXES,
    CODE_API_VERSION_MISMATCH,
    CODE_EXPORT_MISSING,
    CODE_IMPORT_FAILED,
    CODE_INVALID_MODULE_URL,
    CODE_MOUNT_FAILED,
    CODE_NOT_A_PANEL_MODULE,
    CODE_PANEL_CONTROL_MISSING,
    CODE_REMOTE_URL_REJECTED,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    check_panel_module_source,
    diagnostics_for_manifest,
    has_errors,
    strip_js_comments,
    validate_panel,
)

GOOD_PANEL = """
// A panel that satisfies the contract.
const API = "1";
export default {
  apiVersion: API,
  mount(container, host) {
    const ok = document.createElement("button");
    ok.addEventListener("click", () => host.confirm({ picked: 1 }));
    const no = document.createElement("button");
    no.addEventListener("click", () => host.cancel());
    container.append(ok, no);
    return { unmount() { container.replaceChildren(); } };
  },
};
"""


def _codes(diagnostics: list, severity: str | None = None) -> set[str]:
    return {d.code for d in diagnostics if severity is None or d.severity == severity}


def _write_panel(tmp_path: Path, body: str = GOOD_PANEL, name: str = "panel.mjs") -> Path:
    root = tmp_path / "assets"
    root.mkdir(exist_ok=True)
    (root / name).write_text(body, encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# Drift guards for the two constants this module copies rather than imports.
# ---------------------------------------------------------------------------


def test_asset_suffix_allowlist_matches_the_asset_route() -> None:
    """The copied allowlist still equals the one the panel route serves by."""
    from scistudio.previewers import assets

    assert set(_ALLOWED_ASSET_SUFFIXES) == set(assets._ALLOWED_ASSET_SUFFIXES)


def test_remote_prefixes_match_the_asset_route() -> None:
    """The copied off-origin prefixes still equal the ones the route refuses."""
    from scistudio.previewers import assets

    assert tuple(_REMOTE_PREFIXES) == tuple(assets._REMOTE_PREFIXES)


# ---------------------------------------------------------------------------
# Manifest / filesystem checks — hard errors.
# ---------------------------------------------------------------------------


def test_core_panel_with_no_module_url_is_clean() -> None:
    """A bundled core panel carries no module by design; there is nothing to check."""
    assert validate_panel(panel_id="core.interactive.data_router") == []


def test_package_panel_with_no_module_url_is_advisory_only() -> None:
    """A non-core id with no module is probably a forgotten URL — but never blocking."""
    diagnostics = validate_panel(panel_id="pkg.my_block")

    assert _codes(diagnostics) == {CODE_INVALID_MODULE_URL}
    assert not has_errors(diagnostics)


def test_asset_root_without_module_url_is_an_error() -> None:
    """Shipping assets and never naming one means nothing is ever imported."""
    diagnostics = validate_panel(panel_id="pkg.my_block", asset_root="/somewhere")

    assert _codes(diagnostics, SEVERITY_ERROR) == {CODE_INVALID_MODULE_URL}


def test_empty_panel_id_is_an_error() -> None:
    diagnostics = validate_panel(panel_id="", module_url="/api/blocks/panels/x/panel.mjs")

    assert _codes(diagnostics, SEVERITY_ERROR) == {CODE_INVALID_MODULE_URL}


def test_remote_module_url_is_rejected(tmp_path: Path) -> None:
    """`remote_url_rejected`: the host refuses off-origin code before importing."""
    diagnostics = validate_panel(
        panel_id="pkg.my_block",
        module_url="https://cdn.example.com/panel.mjs",
        asset_root=str(_write_panel(tmp_path)),
    )

    assert _codes(diagnostics, SEVERITY_ERROR) == {CODE_REMOTE_URL_REJECTED}


@pytest.mark.parametrize(
    "module_url",
    [
        "/api/previews/assets/pkg.my_block/panel.mjs",  # the previewer route, not the panel route
        "/api/blocks/panels/other.panel/panel.mjs",  # panel_id does not match the manifest
        "panel.mjs",  # not site-relative
        "/api/blocks/panels/pkg.my_block/",  # names no file
    ],
)
def test_module_url_that_resolves_to_no_route_is_an_error(tmp_path: Path, module_url: str) -> None:
    """`import_failed`: a URL off the panel route 404s, so the import fails."""
    diagnostics = validate_panel(
        panel_id="pkg.my_block",
        module_url=module_url,
        asset_root=str(_write_panel(tmp_path)),
    )

    assert _codes(diagnostics, SEVERITY_ERROR) == {CODE_IMPORT_FAILED}


def test_missing_asset_root_is_an_error(tmp_path: Path) -> None:
    diagnostics = validate_panel(
        panel_id="pkg.my_block",
        module_url="/api/blocks/panels/pkg.my_block/panel.mjs",
        asset_root=None,
    )

    assert _codes(diagnostics, SEVERITY_ERROR) == {CODE_IMPORT_FAILED}


def test_asset_root_that_is_not_a_directory_is_an_error(tmp_path: Path) -> None:
    diagnostics = validate_panel(
        panel_id="pkg.my_block",
        module_url="/api/blocks/panels/pkg.my_block/panel.mjs",
        asset_root=str(tmp_path / "not-there"),
    )

    assert _codes(diagnostics, SEVERITY_ERROR) == {CODE_IMPORT_FAILED}


def test_module_file_absent_from_disk_is_an_error(tmp_path: Path) -> None:
    """The reported `import_failed` — the 404 the issue's table names."""
    diagnostics = validate_panel(
        panel_id="pkg.my_block",
        module_url="/api/blocks/panels/pkg.my_block/missing.mjs",
        asset_root=str(_write_panel(tmp_path)),
    )

    assert _codes(diagnostics, SEVERITY_ERROR) == {CODE_IMPORT_FAILED}


def test_module_path_escaping_asset_root_is_an_error(tmp_path: Path) -> None:
    root = _write_panel(tmp_path)
    (tmp_path / "outside.mjs").write_text(GOOD_PANEL, encoding="utf-8")

    diagnostics = validate_panel(
        panel_id="pkg.my_block",
        module_url="/api/blocks/panels/pkg.my_block/../outside.mjs",
        asset_root=str(root),
    )

    assert _codes(diagnostics, SEVERITY_ERROR) == {CODE_IMPORT_FAILED}


def test_disallowed_asset_suffix_is_an_error(tmp_path: Path) -> None:
    root = _write_panel(tmp_path, name="panel.ts")

    diagnostics = validate_panel(
        panel_id="pkg.my_block",
        module_url="/api/blocks/panels/pkg.my_block/panel.ts",
        asset_root=str(root),
    )

    assert _codes(diagnostics, SEVERITY_ERROR) == {CODE_IMPORT_FAILED}


def test_manifest_api_version_mismatch_is_an_error(tmp_path: Path) -> None:
    """The host checks the manifest's own api_version before it imports anything."""
    diagnostics = validate_panel(
        panel_id="pkg.my_block",
        module_url="/api/blocks/panels/pkg.my_block/panel.mjs",
        asset_root=str(_write_panel(tmp_path)),
        api_version="99",
    )

    assert CODE_API_VERSION_MISMATCH in _codes(diagnostics, SEVERITY_ERROR)


# ---------------------------------------------------------------------------
# CSS entries: off-origin is certain, absent-from-disk is survivable.
# ---------------------------------------------------------------------------


def test_remote_css_url_is_an_error(tmp_path: Path) -> None:
    diagnostics = validate_panel(
        panel_id="pkg.my_block",
        module_url="/api/blocks/panels/pkg.my_block/panel.mjs",
        css=("https://cdn.example.com/panel.css",),
        asset_root=str(_write_panel(tmp_path)),
    )

    assert _codes(diagnostics, SEVERITY_ERROR) == {CODE_REMOTE_URL_REJECTED}


def test_missing_css_file_is_advisory_not_blocking(tmp_path: Path) -> None:
    """``injectManifestCss`` mounts the panel anyway, so a 404 stylesheet must not block."""
    diagnostics = validate_panel(
        panel_id="pkg.my_block",
        module_url="/api/blocks/panels/pkg.my_block/panel.mjs",
        css=("/api/blocks/panels/pkg.my_block/panel.css",),
        asset_root=str(_write_panel(tmp_path)),
    )

    assert not has_errors(diagnostics)
    assert _codes(diagnostics, SEVERITY_WARNING) == {CODE_IMPORT_FAILED}


# ---------------------------------------------------------------------------
# Panel module source checks.
# ---------------------------------------------------------------------------


def test_good_panel_source_is_clean() -> None:
    assert check_panel_module_source(GOOD_PANEL) == []


def test_named_export_when_manifest_expects_default_is_export_missing() -> None:
    """The issue's first row: named exports against the default ``export_name``."""
    source = (
        'export const panel = { apiVersion: "1", mount(c, h) { h.confirm(); h.cancel(); return { unmount() {} }; } };'
    )

    diagnostics = check_panel_module_source(source)

    assert _codes(diagnostics, SEVERITY_ERROR) == {CODE_EXPORT_MISSING}


def test_named_export_is_found_when_the_manifest_names_it() -> None:
    source = (
        'export const panel = { apiVersion: "1", mount(c, h) { h.confirm(); h.cancel(); return { unmount() {} }; } };'
    )

    assert check_panel_module_source(source, export_name="panel") == []


def test_export_as_default_is_found() -> None:
    source = GOOD_PANEL.replace("export default {", "const panel = {").replace(
        "};\n", "};\nexport { panel as default };\n", 1
    )

    assert CODE_EXPORT_MISSING not in _codes(check_panel_module_source(source))


def test_star_reexport_never_claims_a_missing_export() -> None:
    """``export *`` re-exports names this scanner cannot enumerate — never a hard error."""
    source = 'export * from "./impl.mjs";\n'

    assert CODE_EXPORT_MISSING not in _codes(check_panel_module_source(source))


@pytest.mark.parametrize(
    ("source", "missing"),
    [
        ("export default { mount(c, h) { h.confirm(); h.cancel(); return { unmount() {} }; } };", "apiVersion"),
        ('export default { apiVersion: "1", render() {} };', "mount"),
    ],
)
def test_export_without_apiversion_or_mount_is_not_a_panel_module(source: str, missing: str) -> None:
    """The issue's second row: the host's ``isPanelModule`` guard refuses it."""
    diagnostics = check_panel_module_source(source)

    assert CODE_NOT_A_PANEL_MODULE in _codes(diagnostics, SEVERITY_ERROR)
    assert missing in next(d for d in diagnostics if d.code == CODE_NOT_A_PANEL_MODULE).message


def test_wrong_module_apiversion_major_is_an_error() -> None:
    source = GOOD_PANEL.replace('const API = "1";', 'const API = "1";').replace(
        "apiVersion: API,", 'apiVersion: "2.0",'
    )

    assert CODE_API_VERSION_MISMATCH in _codes(check_panel_module_source(source), SEVERITY_ERROR)


def test_non_literal_apiversion_is_not_compared() -> None:
    """A module that computes its version cannot be checked, so it is not flagged."""
    assert CODE_API_VERSION_MISMATCH not in _codes(check_panel_module_source(GOOD_PANEL))


def test_remote_import_is_an_error() -> None:
    source = 'import lib from "https://cdn.example.com/lib.js";\n' + GOOD_PANEL

    assert CODE_IMPORT_FAILED in _codes(check_panel_module_source(source), SEVERITY_ERROR)


def test_relative_import_is_fine() -> None:
    source = 'import lib from "./helpers.mjs";\n' + GOOD_PANEL

    assert check_panel_module_source(source) == []


def test_missing_unmount_is_advisory() -> None:
    source = GOOD_PANEL.replace("return { unmount() { container.replaceChildren(); } };", "return {};")

    diagnostics = check_panel_module_source(source)

    assert not has_errors(diagnostics)
    assert _codes(diagnostics, SEVERITY_WARNING) == {CODE_MOUNT_FAILED}


def test_missing_host_controls_is_advisory() -> None:
    """A string search cannot prove a control is wired, so it must never block."""
    source = 'export default { apiVersion: "1", mount(c, h) { return { unmount() {} }; } };'

    diagnostics = check_panel_module_source(source)

    assert not has_errors(diagnostics)
    assert _codes(diagnostics, SEVERITY_WARNING) == {CODE_PANEL_CONTROL_MISSING}


def test_destructured_host_controls_are_recognised() -> None:
    source = (
        'export default { apiVersion: "1", mount(c, host) { const { confirm, cancel } = host; '
        "return { unmount() {} }; } };"
    )

    assert CODE_PANEL_CONTROL_MISSING not in _codes(check_panel_module_source(source))


def test_comment_only_mentions_do_not_satisfy_the_source_checks() -> None:
    """Prose about ``host.confirm`` is not a call to it."""
    source = '// calls host.confirm and host.cancel\nexport default { apiVersion: "1", mount(c, h) { return {}; } };'

    assert CODE_PANEL_CONTROL_MISSING in _codes(check_panel_module_source(source), SEVERITY_WARNING)


def test_comment_stripping_never_manufactures_a_hard_error() -> None:
    """A template literal that looks like a comment must not lose the export.

    The comment scanner does not track string literals, so it can swallow real
    code. Every hard-error check re-tests the raw source for exactly this
    reason; if that guard is removed this test fails.
    """
    source = "const tip = `/*`;\n" + GOOD_PANEL

    assert not has_errors(check_panel_module_source(source))


def test_strip_js_comments_keeps_urls_intact() -> None:
    assert "https://x/y" in strip_js_comments('const u = "https://x/y";')


# ---------------------------------------------------------------------------
# Adapters.
# ---------------------------------------------------------------------------


def test_diagnostics_for_manifest_reads_a_panel_manifest(tmp_path: Path) -> None:
    manifest = PanelManifest(
        panel_id="pkg.my_block",
        module_url="/api/blocks/panels/pkg.my_block/panel.mjs",
        asset_root=str(_write_panel(tmp_path)),
        api_version=PANEL_API_VERSION,
    )

    assert diagnostics_for_manifest(manifest) == []


def test_the_shipped_tutorial_panel_validates_clean() -> None:
    """The one real package-shaped panel in the tree must not be flagged."""
    root = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "scistudio"
        / "tutorials"
        / "core"
        / "what-is-a-type"
        / "assets"
        / "panels"
        / "review_labels"
    )
    if not root.is_dir():  # pragma: no cover - only when tutorial assets are stripped
        pytest.skip("tutorial panel assets are not present in this checkout")

    diagnostics = validate_panel(
        panel_id="tutorial.review_labels",
        module_url="/api/blocks/panels/tutorial.review_labels/panel.mjs",
        asset_root=str(root),
    )

    assert diagnostics == []


def test_source_check_result_tracks_the_file_on_disk(tmp_path: Path) -> None:
    """The cached result must not outlive an edit — that is the whole point of Check 11."""
    root = _write_panel(tmp_path)
    kwargs = {
        "panel_id": "pkg.my_block",
        "module_url": "/api/blocks/panels/pkg.my_block/panel.mjs",
        "asset_root": str(root),
    }
    assert validate_panel(**kwargs) == []

    (root / "panel.mjs").write_text('export default { apiVersion: "7", mount(c, h) {} };', encoding="utf-8")

    assert CODE_API_VERSION_MISMATCH in _codes(validate_panel(**kwargs), SEVERITY_ERROR)
