"""Session-manager frontend-manifest stamping tests (ADR-048 §4 / #1579).

:class:`PreviewSessionManager` promotes the resolved :class:`PreviewerSpec`'s
``frontend_manifest`` to a first-class field on the returned
:class:`PreviewEnvelope`:

* a spec manifest is auto-injected when the provider sets none;
* a provider-set manifest wins (precedence — never overwritten);
* a spec with no manifest yields ``envelope.frontend_manifest is None``.

These use a minimal in-memory registry with trivial providers; they never
require a package install or real storage.
"""

from __future__ import annotations

from scistudio.previewers.models import (
    EnvelopeKind,
    FrontendManifest,
    OwnerKind,
    PreviewEnvelope,
    PreviewerSpec,
    PreviewMetadata,
    PreviewRequest,
    PreviewTarget,
    TargetKind,
)
from scistudio.previewers.registry import PreviewerRegistry
from scistudio.previewers.session import PreviewSessionManager

_SPEC_MANIFEST = FrontendManifest(
    previewer_id="pkg.widget",
    module_url="/api/previews/assets/pkg.widget/viewer.js",
    asset_root="/backend/only/assets",
)
_PROVIDER_MANIFEST = FrontendManifest(
    previewer_id="pkg.widget",
    module_url="/api/previews/assets/pkg.widget/other.js",
)


def _target() -> PreviewTarget:
    return PreviewTarget(
        kind=TargetKind.DATA_REF,
        ref="r",
        recorded_type="Widget",
        type_chain=("DataObject", "Widget"),
    )


def _spec(*, manifest: FrontendManifest | None, provider) -> PreviewerSpec:
    return PreviewerSpec(
        previewer_id="pkg.widget",
        owner_kind=OwnerKind.PACKAGE,
        owner_name="pkg",
        target_type="Widget",
        priority=100,
        backend_provider=provider,
        frontend_manifest=manifest,
    )


def _manager_for(spec: PreviewerSpec) -> PreviewSessionManager:
    reg = PreviewerRegistry()
    reg.register(spec)
    return PreviewSessionManager(reg)


def _bare_envelope(request: PreviewRequest) -> PreviewEnvelope:
    """A trivial provider that sets NO frontend manifest."""
    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.ARRAY,
        metadata=PreviewMetadata(),
    )


def _envelope_with_own_manifest(request: PreviewRequest) -> PreviewEnvelope:
    """A trivial provider that DOES set its own frontend manifest."""
    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.ARRAY,
        metadata=PreviewMetadata(),
        frontend_manifest=_PROVIDER_MANIFEST,
    )


def test_spec_manifest_is_auto_injected_when_provider_sets_none() -> None:
    manager = _manager_for(_spec(manifest=_SPEC_MANIFEST, provider=_bare_envelope))
    envelope = manager.render_target(_target())
    assert envelope.frontend_manifest is _SPEC_MANIFEST
    # Wire shape never leaks the backend-only asset_root.
    assert "asset_root" not in envelope.frontend_manifest.to_dict()
    assert envelope.to_dict()["frontend_manifest"]["module_url"] == _SPEC_MANIFEST.module_url


def test_provider_set_manifest_is_not_overwritten() -> None:
    manager = _manager_for(_spec(manifest=_SPEC_MANIFEST, provider=_envelope_with_own_manifest))
    envelope = manager.render_target(_target())
    # Precedence: the provider's own manifest wins over the spec default.
    assert envelope.frontend_manifest is _PROVIDER_MANIFEST


def test_no_manifest_when_spec_declares_none() -> None:
    manager = _manager_for(_spec(manifest=None, provider=_bare_envelope))
    envelope = manager.render_target(_target())
    assert envelope.frontend_manifest is None
    assert envelope.to_dict()["frontend_manifest"] is None


def test_stamp_also_applies_to_session_envelope() -> None:
    """create_session goes through the same _render seam, so the manifest is
    stamped on the session envelope too (with the session id bound)."""
    manager = _manager_for(_spec(manifest=_SPEC_MANIFEST, provider=_bare_envelope))
    envelope = manager.create_session(_target())
    assert envelope.session_id is not None
    assert envelope.frontend_manifest is _SPEC_MANIFEST
