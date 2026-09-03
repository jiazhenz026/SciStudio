"""The ADR-048 previewer compatibility shim (T-012, FR-042, FR-043, SC-009).

Two properties, and the second matters more than the first.

**It still renders (FR-042).** A previewer written against the retired ES-module
form — the ``scistudio.previewers`` entry-point group, a ``get_previewers()``
factory, a :class:`~scistudio.panels.models.FrontendManifest` naming a
same-origin module — becomes a panel directory the merged asset route serves and
the frame host mounts. The fixture package's ``previewers/`` package is that
previewer: it is the real retired form, imported rather than restated, because a
restatement is the one thing that cannot catch a change to the original.

**It grants nothing new (FR-043).** The declaration the shim generates says
``displaying``, which is what makes the host's capability gate drop ``emit``
structurally, and the generated document contains no emission path and reads no
binding. Both halves are asserted here; the host-side half of SC-009 — that a
mount of this document is granted no outbound path and no bindings — is
``frontend/src/panels/panelCompat.test.tsx``, because a declaration cannot prove
what the host does with it.

The tests write their own shim root rather than using
:func:`~scistudio.panels.compat.compat_shim_root`, so nothing here depends on a
process-global temporary directory or leaves one behind.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scistudio.core.panels import PanelCapability, PanelTier, read_panel_declaration
from scistudio.panels.assets import resolve_confined_asset
from scistudio.panels.compat import (
    COMPAT_SHIM_ENTRY,
    COMPAT_SHIM_MAX_BUNDLE_FILES,
    CompatShimError,
    build_compat_panel,
    compat_shim_document,
    install_compat_panels,
    is_compat_panel,
    module_entry_path,
    shimmable_specs,
)
from scistudio.panels.descriptor import panel_descriptor
from scistudio.panels.discovery import PanelDiscovery, discover_panels
from scistudio.panels.models import FrontendManifest, OwnerKind, PanelSpec
from scistudio.panels.registry import PanelRegistry
from tests.panels.conftest import write_panel

# ---------------------------------------------------------------------------
# The retired form, as a package actually ships it
# ---------------------------------------------------------------------------


@pytest.fixture
def legacy_spec() -> PanelSpec:
    """The fixture package's own ADR-048 previewer, straight from its factory."""
    from scistudio_blocks_fixture.previewers import IMAGE_PANEL_ID, get_previewers

    spec = next(s for s in get_previewers() if s.previewer_id == IMAGE_PANEL_ID)
    assert spec.frontend_manifest is not None, "the fixture must still ship the retired module form"
    return spec


def _bundle_spec(tmp_path: Path, *, previewer_id: str = "pkg.legacy.viewer", entry: str = "viewer.js") -> PanelSpec:
    """A hand-built previewer in the retired form, for the cases the fixture cannot show."""
    assets = tmp_path / "bundle"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / entry).write_text("export default { apiVersion: '1', mount() { return {unmount(){}}; } };\n")
    return PanelSpec(
        previewer_id=previewer_id,
        owner_kind=OwnerKind.PACKAGE,
        owner_name="pkg",
        target_type="Array",
        features=("slice",),
        frontend_manifest=FrontendManifest(
            previewer_id=previewer_id,
            module_url=f"/api/previews/assets/{previewer_id}/{entry}",
            export_name="default",
            asset_root=str(assets),
        ),
    )


# ---------------------------------------------------------------------------
# FR-042: the retired form becomes a panel the one loader mounts
# ---------------------------------------------------------------------------


def test_a_retired_form_previewer_becomes_a_panel_directory(legacy_spec: PanelSpec, tmp_path: Path) -> None:
    """The wrap produces the D-007 on-disk form, not a special case beside it."""
    panel = build_compat_panel(legacy_spec, root=tmp_path)

    assert panel.directory.is_dir()
    assert (panel.directory / COMPAT_SHIM_ENTRY).is_file()
    assert (panel.directory / "panel.json").is_file()
    assert panel.manifest.entry == COMPAT_SHIM_ENTRY
    assert panel.entry_path.is_file()

    # The declaration is a real one: it parses through the same reader every
    # other tier's panel.json goes through (FR-003).
    reread = read_panel_declaration(panel.directory)
    assert reread.panel_id == legacy_spec.previewer_id
    assert reread.capability is PanelCapability.DISPLAYING


def test_the_whole_bundle_travels_not_only_the_entry_module(legacy_spec: PanelSpec, tmp_path: Path) -> None:
    """A module that imports a sibling still mounts, and `assetUrl` still resolves."""
    panel = build_compat_panel(legacy_spec, root=tmp_path)

    assert (panel.directory / "viewer.js").is_file()
    assert (panel.directory / "viewer_label.js").is_file(), "the sibling the entry module imports"
    assert (panel.directory / "viewer.css").is_file(), "a non-JavaScript asset beside the module"


def test_the_generated_panel_is_served_by_the_merged_asset_route(legacy_spec: PanelSpec, tmp_path: Path) -> None:
    """One route, one confinement check, one allowlist — the shim adds none of its own."""
    panel = build_compat_panel(legacy_spec, root=tmp_path)

    document = resolve_confined_asset(panel.directory, COMPAT_SHIM_ENTRY, panel_id=panel.panel_id)
    assert document.media_type.startswith("text/html")
    module = resolve_confined_asset(panel.directory, "viewer.js", panel_id=panel.panel_id)
    assert module.media_type == "text/javascript"

    descriptor = panel_descriptor(panel)
    assert descriptor.document_url == f"/api/panels/assets/{panel.panel_id}/{COMPAT_SHIM_ENTRY}"
    assert descriptor.asset_base_url == f"/api/panels/assets/{panel.panel_id}/"


def test_the_document_imports_the_module_from_its_own_panel_directory(legacy_spec: PanelSpec, tmp_path: Path) -> None:
    """The import is relative, so it lands on the one route a frame at an opaque origin can read."""
    panel = build_compat_panel(legacy_spec, root=tmp_path)
    document = (panel.directory / COMPAT_SHIM_ENTRY).read_text(encoding="utf-8")

    assert '"entry_url": "./viewer.js"' in document
    assert "import(COMPAT.entry_url)" in document
    assert "/api/previews/assets" not in document, "the retained route answers no cross-origin read"


def test_the_wrapped_previewer_keeps_its_python_provider(legacy_spec: PanelSpec, tmp_path: Path) -> None:
    """FR-042 keeps it *rendering*: what it renders is what its Python side already produced."""
    panel = build_compat_panel(legacy_spec, root=tmp_path)
    assert panel.provider is legacy_spec.backend_provider


def test_the_declared_api_version_is_the_previewers_own(tmp_path: Path) -> None:
    """A module built against a major the host no longer accepts is refused, not laundered."""
    spec = _bundle_spec(tmp_path)
    stale = FrontendManifest(
        previewer_id=spec.previewer_id,
        module_url=spec.frontend_manifest.module_url,
        asset_root=spec.frontend_manifest.asset_root,
        api_version="9",
    )
    panel = build_compat_panel(PanelSpec(**{**spec.__dict__, "frontend_manifest": stale}), root=tmp_path / "out")

    assert panel.manifest.api_version == "9"
    descriptor = panel_descriptor(panel)
    assert descriptor.api_version == "9"
    assert descriptor.accepted_api_version != "9", "the host's version gate is what refuses it (FR-004)"


# ---------------------------------------------------------------------------
# FR-043 / SC-009: the shim grants nothing new
# ---------------------------------------------------------------------------


def test_the_generated_declaration_is_displaying_only(legacy_spec: PanelSpec, tmp_path: Path) -> None:
    """The capability is not the spec's to choose: a wrapped previewer displays (FR-043)."""
    producing = PanelSpec(**{**legacy_spec.__dict__, "capability": PanelCapability.PRODUCING})
    panel = build_compat_panel(producing, root=tmp_path)

    assert panel.manifest.capability is PanelCapability.DISPLAYING
    declaration = json.loads((panel.directory / "panel.json").read_text(encoding="utf-8"))
    assert declaration["capability"] == "displaying"

    descriptor = panel_descriptor(panel)
    assert descriptor.capability is PanelCapability.DISPLAYING


def test_the_generated_document_carries_no_emission_path(legacy_spec: PanelSpec, tmp_path: Path) -> None:
    """No `emit`, and no binding read: a package obtains those by migrating (FR-043)."""
    panel = build_compat_panel(legacy_spec, root=tmp_path)
    document = (panel.directory / COMPAT_SHIM_ENTRY).read_text(encoding="utf-8")

    assert '"emit"' not in document and "'emit'" not in document
    # The word survives in the comment that explains the omission; what must not
    # appear is a *read* of the field, in any spelling the payload allows.
    assert ".bindings" not in document
    assert '["bindings"]' not in document
    assert '"bindings"' not in document


def test_the_host_api_maps_onto_the_named_message_types(legacy_spec: PanelSpec, tmp_path: Path) -> None:
    """D-017: an export is not a read, so each retired call maps to the type that means it."""
    panel = build_compat_panel(legacy_spec, root=tmp_path)
    document = (panel.directory / COMPAT_SHIM_ENTRY).read_text(encoding="utf-8")

    for call, message in [
        ("patchQuery", '"read"'),
        ("getResource", '"resource"'),
        ("exportArtifact", '"host_action"'),
        ("saveArtifact", '"host_action"'),
    ]:
        assert call in document, f"the retired host API's {call} must still exist"
        assert message in document, f"{call} has no message type to travel on"
    assert 'action: "export"' in document
    assert 'action: "download"' in document

    # The three the adapter answers without a message at all, from `init` and
    # the envelope it was handed.
    assert "context.asset_base_url" in document, "assetUrl comes from the init payload"
    assert "envelope.session_id" in document, "previewSessionId is the envelope's own field"
    assert "context.api_version" in document, "apiVersion is the backend's, echoed (D-010)"


# ---------------------------------------------------------------------------
# FR-014: a shim that cannot wrap is the ordinary load failure, never a crash
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("case", "mutate"),
    [
        ("a remote module url", {"module_url": "https://cdn.example.com/viewer.js"}),
        ("no asset root", {"asset_root": None}),
        ("a module the bundle does not contain", {"module_url": "/api/previews/assets/pkg.legacy.viewer/gone.js"}),
    ],
)
def test_an_unwrappable_previewer_is_a_diagnostic(tmp_path: Path, case: str, mutate: dict) -> None:
    """Each refusal names the previewer and returns a message, not an exception the caller must catch."""
    spec = _bundle_spec(tmp_path)
    manifest = FrontendManifest(**{**spec.frontend_manifest.__dict__, **mutate})
    broken = PanelSpec(**{**spec.__dict__, "frontend_manifest": manifest})

    with pytest.raises(CompatShimError) as excinfo:
        build_compat_panel(broken, root=tmp_path / "out")
    assert spec.previewer_id in str(excinfo.value), case


def test_one_unwrappable_previewer_does_not_cost_the_others(tmp_path: Path) -> None:
    """Refusals are recorded on the discovery surface; the panel falls to FR-014 with the data visible."""
    good = _bundle_spec(tmp_path / "a", previewer_id="pkg.good")
    bad_manifest = FrontendManifest(
        previewer_id="pkg.bad",
        module_url="https://cdn.example.com/viewer.js",
        asset_root=str(tmp_path / "a" / "bundle"),
    )
    bad = PanelSpec(**{**good.__dict__, "previewer_id": "pkg.bad", "frontend_manifest": bad_manifest})

    registry = PanelRegistry()
    registry.register(good)
    registry.register(bad)
    discovery = PanelDiscovery()

    wrapped = install_compat_panels(registry, discovery, root=tmp_path / "out")

    assert wrapped == ["pkg.good"]
    assert discovery.get("pkg.good") is not None
    assert discovery.get("pkg.bad") is None
    assert any("pkg.bad" in message for message in discovery.diagnostics)


def test_a_bundle_past_the_bound_is_refused_rather_than_copied(tmp_path: Path) -> None:
    """The shim wraps a viewer and its assets; a package doing more is told so."""
    spec = _bundle_spec(tmp_path)
    assets = Path(spec.frontend_manifest.asset_root)
    for index in range(COMPAT_SHIM_MAX_BUNDLE_FILES + 1):
        (assets / f"chunk_{index:04d}.js").write_text("export const x = 1;\n")

    with pytest.raises(CompatShimError, match="larger than the shim wraps"):
        build_compat_panel(spec, root=tmp_path / "out")


def test_a_bundle_that_would_overwrite_the_generated_files_is_refused(tmp_path: Path) -> None:
    """The document's name is reserved; a collision is a migration prompt, not a silent overwrite."""
    spec = _bundle_spec(tmp_path)
    (Path(spec.frontend_manifest.asset_root) / COMPAT_SHIM_ENTRY).write_text("<!doctype html>\n")

    with pytest.raises(CompatShimError, match="migrate the package"):
        build_compat_panel(spec, root=tmp_path / "out")


# ---------------------------------------------------------------------------
# Selection: what gets wrapped, and what stops being wrapped
# ---------------------------------------------------------------------------


def test_a_migrated_package_shadows_its_own_shim(tmp_path: Path) -> None:
    """FR-019 does the withdrawing: a directory for the id means no shim for it."""
    spec = _bundle_spec(tmp_path, previewer_id="pkg.legacy.viewer")
    package_root = tmp_path / "panels"
    write_panel(package_root, "pkg.legacy.viewer", target_types=["Array"])
    discovery = discover_panels(core_root=tmp_path / "empty-core", package_roots=[(package_root, "pkg")])

    registry = PanelRegistry()
    registry.register(spec)
    wrapped = install_compat_panels(registry, discovery, root=tmp_path / "out")

    assert wrapped == []
    assert discovery.get("pkg.legacy.viewer") is not None
    assert not is_compat_panel(discovery.get("pkg.legacy.viewer"))


def test_a_directory_registered_panel_is_never_wrapped(tmp_path: Path) -> None:
    """A spec with no ADR-048 manifest has nothing to wrap and is left alone."""
    package_root = tmp_path / "panels"
    write_panel(package_root, "pkg.modern", target_types=["Array"])
    discovery = discover_panels(core_root=tmp_path / "empty-core", package_roots=[(package_root, "pkg")])
    registry = PanelRegistry()

    assert shimmable_specs(registry.all_specs(), set(discovery.panels)) == []
    assert install_compat_panels(registry, discovery, root=tmp_path / "out") == []


def test_the_wrapped_panel_keeps_the_tier_its_package_registered_from(tmp_path: Path) -> None:
    """A shim does not promote a package panel into the core tier or out of it."""
    spec = _bundle_spec(tmp_path)
    panel = build_compat_panel(spec, root=tmp_path / "out")
    assert panel.tier is PanelTier.PACKAGE
    assert panel.owner_name == "pkg"
    assert is_compat_panel(panel)


# ---------------------------------------------------------------------------
# Reading a module URL
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("module_url", "expected"),
    [
        ("/api/previews/assets/pkg.viewer/viewer.js", "viewer.js"),
        ("/api/blocks/panels/pkg.viewer/panel.mjs", "panel.mjs"),
        ("/api/previews/assets/pkg.viewer/nested/viewer.js", "nested/viewer.js"),
        ("/api/previews/assets/pkg.viewer/viewer.js?v=2", "viewer.js"),
        ("/somewhere/else/viewer.js", "viewer.js"),
    ],
)
def test_the_entry_path_is_read_out_of_the_module_url(module_url: str, expected: str) -> None:
    manifest = FrontendManifest(previewer_id="pkg.viewer", module_url=module_url)
    assert module_entry_path(manifest) == expected


def test_a_module_url_naming_no_file_is_refused() -> None:
    manifest = FrontendManifest(previewer_id="pkg.viewer", module_url="/")
    with pytest.raises(CompatShimError, match="no file to serve"):
        module_entry_path(manifest)


def test_the_template_alone_is_not_a_configured_document() -> None:
    """The placeholder is substituted, so a generated document never ships the stand-in."""
    document = compat_shim_document(entry_url="./viewer.js", export_name="Viewer", api_version="1")
    assert "__SCISTUDIO_COMPAT__" not in document
    assert '"export_name": "Viewer"' in document
