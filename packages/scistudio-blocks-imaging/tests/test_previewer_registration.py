"""ADR-048 SPEC 1 — package-owned Image/Label previewer registration tests.

Covers (per the SPEC 1 acceptance items):

* :func:`get_previewers` returns ``Image`` + ``Label`` specs with
  ``owner_kind=PACKAGE``, resolvable ``backend_provider``, and a
  :class:`FrontendManifest` that passes ``scistudio.previewers.assets``
  validation (same-origin ``module_url`` resolving to a real file under
  ``asset_root``).
* Routing via :class:`PreviewRouter`: ``Image`` -> imaging, ``Label`` ->
  imaging, plain ``Array`` -> ``core.array.basic`` (FR-003).
* Removing imaging -> ``Image`` falls back to ``core.array.basic`` via
  parent-type resolution (FR-026).
* The Image provider returns a valid ``PreviewEnvelope`` with the 6 metadata
  flags set, and the same-origin ``frontend_manifest`` reaches the *session*
  envelope first-class — framework-stamped by
  :class:`~scistudio.previewers.session.PreviewSessionManager` from the resolved
  :class:`PreviewerSpec` (#1579) — while the provider called directly no longer
  embeds it into ``metadata.extra``.

These are pure-unit tests: they register the imaging specs explicitly (or run
monorepo discovery) and never require the package to be pip-installed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from scistudio_blocks_imaging import get_previewers as pkg_get_previewers
from scistudio_blocks_imaging.previewers import (
    IMAGE_PREVIEWER_ID,
    LABEL_PREVIEWER_ID,
    get_previewers,
    image_provider,
    label_provider,
)

from scistudio.previewers.assets import resolve_asset, validate_manifest
from scistudio.previewers.fallbacks import core_previewer_specs
from scistudio.previewers.models import (
    EnvelopeKind,
    OwnerKind,
    PreviewerSpec,
    PreviewLimits,
    PreviewRequest,
    PreviewTarget,
    TargetKind,
)
from scistudio.previewers.registry import PreviewerRegistry
from scistudio.previewers.router import PreviewRouter
from scistudio.previewers.session import PreviewSessionManager

# Recorded type chains (general -> specific) the router walks. Image extends
# Array; Label extends CompositeData.
_IMAGE_CHAIN = ("DataObject", "Array", "Image")
_LABEL_CHAIN = ("DataObject", "CompositeData", "Label")
_ARRAY_CHAIN = ("DataObject", "Array")


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _registry(*, with_imaging: bool = True) -> PreviewerRegistry:
    reg = PreviewerRegistry()
    for spec in core_previewer_specs():
        reg.register(spec)
    if with_imaging:
        for spec in get_previewers():
            reg.register(spec)
    return reg


def _data_target(recorded: str, chain: tuple[str, ...]) -> PreviewTarget:
    return PreviewTarget(kind=TargetKind.DATA_REF, ref="r", recorded_type=recorded, type_chain=chain)


def _install_fake_zarr(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install a 3-D (z, y, x) fake Zarr handle (no real file deps).

    Mirrors ``tests/previewers/test_preview_data_access.py`` so the provider's
    bounded ``array_plane`` read exercises a real code path without requiring
    ``tifffile``/on-disk Zarr in this env.
    """
    import sys
    import types

    class _FakeZarrArray:
        shape = (3, 16, 16)
        dtype = "uint16"

        def __getitem__(self, key: object) -> np.ndarray:
            return np.arange(16 * 16, dtype=np.uint16).reshape(16, 16)

    fake_zarr = types.ModuleType("zarr")
    fake_zarr.Array = _FakeZarrArray  # type: ignore[attr-defined]
    fake_zarr.open = lambda path, mode="r": _FakeZarrArray()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "zarr", fake_zarr)


def _image_zarr_ref(tmp_path: Path) -> Path:
    path = tmp_path / "img.zarr"
    path.mkdir()
    return path


def _image_request(spec: PreviewerSpec, path: Path, record_md: dict | None = None) -> PreviewRequest:
    from scistudio.previewers.data_access import PreviewDataAccess

    query: dict = {
        "_storage": {
            "backend": "zarr",
            "path": str(path),
            "format": "zarr",
            "metadata": {"axes": ["z", "y", "x"], "shape": [3, 16, 16]},
        },
    }
    if record_md is not None:
        query["_record_metadata"] = record_md
    target = _data_target("Image", _IMAGE_CHAIN)
    return PreviewRequest(
        target=target,
        spec=spec,
        query=query,
        data_access=PreviewDataAccess(),
        limits=PreviewLimits(),
        session_id=None,
    )


def _image_spec() -> PreviewerSpec:
    return next(s for s in get_previewers() if s.previewer_id == IMAGE_PREVIEWER_ID)


def _label_spec() -> PreviewerSpec:
    return next(s for s in get_previewers() if s.previewer_id == LABEL_PREVIEWER_ID)


# ---------------------------------------------------------------------------
# get_previewers() shape
# ---------------------------------------------------------------------------


def test_get_previewers_returns_image_and_label_package_specs() -> None:
    specs = get_previewers()
    ids = {s.previewer_id for s in specs}
    assert ids == {IMAGE_PREVIEWER_ID, LABEL_PREVIEWER_ID}
    for spec in specs:
        assert spec.owner_kind is OwnerKind.PACKAGE
        assert spec.owner_name == "scistudio-blocks-imaging"
        assert spec.priority > 0  # wins exact-type routing over core fallbacks
        # backend_provider is a directly-resolvable callable.
        assert callable(spec.backend_provider)

    by_id = {s.previewer_id: s for s in specs}
    assert by_id[IMAGE_PREVIEWER_ID].target_type == "Image"
    assert by_id[LABEL_PREVIEWER_ID].target_type == "Label"


def test_top_level_reexport_matches_module_factory() -> None:
    """The package top-level re-export (monorepo discovery seam) is the same factory."""
    assert {s.previewer_id for s in pkg_get_previewers()} == {IMAGE_PREVIEWER_ID, LABEL_PREVIEWER_ID}


def test_manifests_pass_asset_validation_and_resolve_to_a_real_file() -> None:
    for spec in get_previewers():
        manifest = spec.frontend_manifest
        assert manifest is not None
        result = validate_manifest(manifest)
        assert result.valid, result.diagnostics
        assert result.api_version_ok
        # module_url is backend-relative / same-origin (no http/https///data:).
        assert manifest.module_url == f"/api/previews/assets/{spec.previewer_id}/viewer.js"
        assert not manifest.module_url.startswith(("http", "//", "data:"))
        # asset_root is set and the served module resolves to a real file.
        assert manifest.asset_root is not None
        served = resolve_asset(manifest, "viewer.js")
        assert served.path.is_file()
        assert served.media_type == "text/javascript"
        # asset_root is NOT serialised to the frontend.
        assert "asset_root" not in manifest.to_dict()


# ---------------------------------------------------------------------------
# Routing (FR-003 / FR-026)
# ---------------------------------------------------------------------------


def test_image_target_routes_to_imaging_previewer() -> None:
    router = PreviewRouter(_registry())
    spec = router.resolve(_data_target("Image", _IMAGE_CHAIN))
    assert spec.previewer_id == IMAGE_PREVIEWER_ID
    assert spec.owner_kind is OwnerKind.PACKAGE


def test_label_target_routes_to_imaging_previewer() -> None:
    router = PreviewRouter(_registry())
    spec = router.resolve(_data_target("Label", _LABEL_CHAIN))
    assert spec.previewer_id == LABEL_PREVIEWER_ID


def test_plain_array_target_routes_to_core() -> None:
    router = PreviewRouter(_registry())
    spec = router.resolve(_data_target("Array", _ARRAY_CHAIN))
    assert spec.previewer_id == "core.array.basic"
    assert spec.owner_kind is OwnerKind.CORE


def test_image_falls_back_to_core_array_when_imaging_absent() -> None:
    """FR-026: with no imaging previewer, Image resolves to core via Array parent."""
    router = PreviewRouter(_registry(with_imaging=False))
    spec = router.resolve(_data_target("Image", _IMAGE_CHAIN))
    assert spec.previewer_id == "core.array.basic"
    assert spec.owner_kind is OwnerKind.CORE


def test_monorepo_discovery_registers_imaging_previewers() -> None:
    """The registry's monorepo dev fallback discovers get_previewers() via the package."""
    reg = PreviewerRegistry()
    reg.load_core()
    reg.load_packages(include_monorepo=True)
    ids = {s.previewer_id for s in reg.all_specs()}
    assert IMAGE_PREVIEWER_ID in ids
    assert LABEL_PREVIEWER_ID in ids


# ---------------------------------------------------------------------------
# Image provider envelope + framework-stamped manifest seam (#1579)
# ---------------------------------------------------------------------------


def test_image_provider_returns_valid_envelope_without_self_embedding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The provider alone returns a valid envelope but no longer embeds the manifest."""
    _install_fake_zarr(monkeypatch)
    spec = _image_spec()
    record_md = {
        "objective": "20x",
        "instrument": "scope-1",
        "channels": [{"name": "DAPI"}, {"name": "GFP", "excitation_nm": 488.0}],
        "wavelengths_nm": [405.0, 488.0],
    }
    request = _image_request(spec, _image_zarr_ref(tmp_path), record_md=record_md)
    envelope = image_provider(request)

    assert envelope.previewer_id == IMAGE_PREVIEWER_ID
    # kind=ARRAY so the host can fall back to the core Array viewer (FR-026).
    assert envelope.kind is EnvelopeKind.ARRAY
    assert envelope.error is None
    # 3-D fixture (z, y, x) -> z is the slider axis with size 3; PNG encoded.
    assert envelope.payload["slice_axis_size"] == 3
    assert envelope.payload["src"].startswith("data:image/png;base64,")
    # OME/channel metadata panel surfaced.
    assert envelope.payload["image_metadata"]["objective"] == "20x"
    assert [c["name"] for c in envelope.payload["image_metadata"]["channels"]] == ["DAPI", "GFP"]

    # The 6 mandatory metadata flags are all present (FR-011).
    md = envelope.metadata.to_dict()
    for flag in ("sampled", "truncated", "cached", "derived", "complete", "failed"):
        assert flag in md and isinstance(md[flag], bool)

    # #1579: the provider no longer embeds the manifest into metadata.extra; it
    # is framework-stamped by the session manager (see the session-driven test).
    assert "frontend_manifest" not in envelope.metadata.extra
    assert envelope.frontend_manifest is None


def test_session_manager_stamps_image_manifest_first_class(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Driven through PreviewSessionManager, the Image envelope carries the
    resolved spec's manifest first-class on ``envelope.frontend_manifest``."""
    _install_fake_zarr(monkeypatch)
    manager = PreviewSessionManager(_registry())
    target = _data_target("Image", _IMAGE_CHAIN)
    query = {
        "_storage": {
            "backend": "zarr",
            "path": str(_image_zarr_ref(tmp_path)),
            "format": "zarr",
            "metadata": {"axes": ["z", "y", "x"], "shape": [3, 16, 16]},
        },
    }
    envelope = manager.render_target(target, query)

    assert envelope.previewer_id == IMAGE_PREVIEWER_ID
    # First-class manifest is stamped from the resolved spec.
    fm = envelope.frontend_manifest
    assert fm is not None
    assert fm.previewer_id == IMAGE_PREVIEWER_ID
    assert fm.module_url == f"/api/previews/assets/{IMAGE_PREVIEWER_ID}/viewer.js"
    # Wire shape omits the backend-only asset_root.
    assert "asset_root" not in fm.to_dict()
    # And it is gone from the old metadata.extra channel.
    assert "frontend_manifest" not in envelope.metadata.extra


def test_image_provider_error_envelope_has_no_embedded_manifest() -> None:
    """A routine read failure yields a typed error envelope (FR-028) with no embed."""
    from scistudio.previewers.data_access import PreviewDataAccess

    spec = _image_spec()
    request = PreviewRequest(
        target=_data_target("Image", _IMAGE_CHAIN),
        spec=spec,
        query={"_storage": {"backend": "filesystem", "path": "/does/not/exist.tif", "format": "tif"}},
        data_access=PreviewDataAccess(),
        limits=PreviewLimits(),
        session_id=None,
    )
    envelope = image_provider(request)
    assert envelope.kind is EnvelopeKind.ERROR
    assert envelope.metadata.failed is True
    assert envelope.metadata.complete is False
    assert "frontend_manifest" not in envelope.metadata.extra
    assert envelope.frontend_manifest is None


def test_label_provider_returns_composite_envelope_without_self_embedding() -> None:
    from scistudio.previewers.data_access import PreviewDataAccess

    spec = _label_spec()
    record_md = {"slots": {"raster": "Array", "polygons": "DataFrame"}, "n_objects": 7}
    request = PreviewRequest(
        target=_data_target("Label", _LABEL_CHAIN),
        spec=spec,
        # No real raster path -> composite_raster_slot returns None; provider
        # still emits a valid slot-inventory envelope.
        query={
            "_storage": {"backend": "filesystem", "path": "/labels", "format": "zarr"},
            "_record_metadata": record_md,
        },
        data_access=PreviewDataAccess(),
        limits=PreviewLimits(),
        session_id=None,
    )
    envelope = label_provider(request)

    assert envelope.previewer_id == LABEL_PREVIEWER_ID
    assert envelope.kind is EnvelopeKind.COMPOSITE
    assert envelope.payload["slots"] == {"raster": "Array", "polygons": "DataFrame"}
    assert envelope.payload["image_metadata"]["n_objects"] == 7
    # Each slot advertises a child-routing resource.
    resource_ids = {r.resource_id for r in envelope.resources}
    assert resource_ids == {"slot:raster", "slot:polygons"}
    # #1579: no per-envelope embed; the session manager stamps it first-class.
    assert "frontend_manifest" not in envelope.metadata.extra
    assert envelope.frontend_manifest is None


def test_session_manager_stamps_label_manifest_first_class() -> None:
    """The Label session envelope also carries the resolved spec's manifest."""
    manager = PreviewSessionManager(_registry())
    target = _data_target("Label", _LABEL_CHAIN)
    query = {
        "_storage": {"backend": "filesystem", "path": "/labels", "format": "zarr"},
        "_record_metadata": {"slots": {"raster": "Array", "polygons": "DataFrame"}, "n_objects": 7},
    }
    envelope = manager.render_target(target, query)

    assert envelope.previewer_id == LABEL_PREVIEWER_ID
    fm = envelope.frontend_manifest
    assert fm is not None
    assert fm.previewer_id == LABEL_PREVIEWER_ID
    assert "frontend_manifest" not in envelope.metadata.extra


def test_provider_specs_have_distinct_ids_from_core() -> None:
    """Registering imaging on top of core produces no duplicate-id diagnostics."""
    reg = _registry()
    assert reg.diagnostics == []
    assert reg.get(IMAGE_PREVIEWER_ID) is not None
    assert reg.get("core.array.basic") is not None


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
