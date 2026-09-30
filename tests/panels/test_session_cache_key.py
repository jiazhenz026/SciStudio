"""Regression tests for ADR-048 routed preview session cache keys (panel sessions)."""

from __future__ import annotations

from scistudio.panels.models import OwnerKind, PreviewerSpec, PreviewTarget, TargetKind
from scistudio.panels.sessions import PreviewSessions


def _target() -> PreviewTarget:
    return PreviewTarget(
        kind=TargetKind.DATA_REF,
        ref="array-1",
        recorded_type="Array",
        type_chain=("DataObject", "Array"),
    )


def _spec() -> PreviewerSpec:
    return PreviewerSpec(
        previewer_id="core.array.basic",
        owner_kind=OwnerKind.CORE,
        owner_name="scistudio",
        target_type="Array",
        panel={"id": "core.array.basic", "api_version": "1.0"},
    )


def test_session_cache_key_distinguishes_axis_indices_and_identity() -> None:
    sessions = PreviewSessions()
    envelope = sessions.create_session(
        _spec(),
        _target(),
        {
            "axis_indices": {"0": 1, "1": 2},
            "_storage": {"metadata": {"data_version": "v7"}},
        },
    )
    assert envelope.session_id is not None

    session = sessions.get_session(envelope.session_id)
    first_key = session.cache_key
    assert first_key is not None
    assert "previewer=core.array.basic" in first_key
    assert "kind=data_ref" in first_key
    assert "ref=array-1" in first_key
    assert f"session={envelope.session_id}" in first_key
    assert "version=v7" in first_key
    assert 'axis_indices={"0":1,"1":2}' in first_key
    assert "_storage" not in first_key

    sessions.patch_session(envelope.session_id, {"axis_indices": {"0": 1, "1": 4}}, lambda _id: "1.0")
    patched_key = sessions.get_session(envelope.session_id).cache_key

    assert patched_key is not None
    assert patched_key != first_key
    assert 'axis_indices={"0":1,"1":4}' in patched_key
    assert f"session={envelope.session_id}" in patched_key
    assert "version=v7" in patched_key
