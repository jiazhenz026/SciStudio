"""Regression tests for ADR-048 routed preview session cache keys."""

from __future__ import annotations

from scistudio.previewers.models import (
    EnvelopeKind,
    OwnerKind,
    PreviewEnvelope,
    PreviewerSpec,
    PreviewRequest,
    PreviewTarget,
    TargetKind,
)
from scistudio.previewers.registry import PreviewerRegistry
from scistudio.previewers.session import PreviewSessionManager


def _target() -> PreviewTarget:
    return PreviewTarget(
        kind=TargetKind.DATA_REF,
        ref="array-1",
        recorded_type="Array",
        type_chain=("DataObject", "Array"),
    )


def _provider(request: PreviewRequest) -> PreviewEnvelope:
    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.ARRAY,
    )


def _manager() -> PreviewSessionManager:
    registry = PreviewerRegistry()
    registry.register(
        PreviewerSpec(
            previewer_id="core.array.basic",
            owner_kind=OwnerKind.CORE,
            owner_name="scistudio",
            target_type="Array",
            backend_provider=_provider,
        )
    )
    return PreviewSessionManager(registry)


def test_session_cache_key_distinguishes_axis_indices_and_identity() -> None:
    manager = _manager()
    envelope = manager.create_session(
        _target(),
        {
            "axis_indices": {"0": 1, "1": 2},
            "_storage": {"metadata": {"data_version": "v7"}},
        },
    )
    assert envelope.session_id is not None

    session = manager.get_session(envelope.session_id)
    first_key = session.cache_key
    assert first_key is not None
    assert "previewer=core.array.basic" in first_key
    assert "kind=data_ref" in first_key
    assert "ref=array-1" in first_key
    assert f"session={envelope.session_id}" in first_key
    assert "version=v7" in first_key
    assert 'axis_indices={"0":1,"1":2}' in first_key
    assert "_storage" not in first_key

    manager.patch_session(envelope.session_id, {"axis_indices": {"0": 1, "1": 4}})
    patched_key = manager.get_session(envelope.session_id).cache_key

    assert patched_key is not None
    assert patched_key != first_key
    assert 'axis_indices={"0":1,"1":4}' in patched_key
    assert f"session={envelope.session_id}" in patched_key
    assert "version=v7" in patched_key
