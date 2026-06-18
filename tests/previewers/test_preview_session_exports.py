"""Regression tests for package-owned preview resource providers."""

from __future__ import annotations

import base64

from scistudio.previewers.models import (
    EnvelopeKind,
    OwnerKind,
    PreviewEnvelope,
    PreviewerSpec,
    PreviewRequest,
    PreviewResource,
    PreviewTarget,
    TargetKind,
)
from scistudio.previewers.registry import PreviewerRegistry
from scistudio.previewers.session import PreviewSessionManager


def _target() -> PreviewTarget:
    return PreviewTarget(
        kind=TargetKind.DATA_REF,
        ref="spectrum-1",
        recorded_type="Spectrum",
        type_chain=("DataObject", "Series", "Spectrum"),
    )


def _provider(request: PreviewRequest) -> PreviewEnvelope:
    points = [{"x": 400.0, "y": 0.1}, {"x": 410.0, "y": 0.5}]
    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.SERIES,
        payload={
            "points": points,
            "table": {
                "columns": ["lambda", "intensity"],
                "rows": [{"lambda": p["x"], "intensity": p["y"]} for p in points],
            },
            "axes": {
                "x": {"name": "wavelength-nm", "label": "wavelength-nm"},
                "y": {"name": "intensity", "label": "intensity"},
            },
        },
        resources=(
            PreviewResource(
                resource_id="export_figure_svg",
                kind="asset",
                media_type="image/svg+xml",
                params={"format": "svg", "target": "figure"},
            ),
            PreviewResource(
                resource_id="export_points_csv",
                kind="asset",
                media_type="text/csv",
                params={"format": "csv", "target": "points"},
            ),
        ),
    )


def _resource_provider(_request: PreviewRequest, resource_id: str, _params: dict[str, object]) -> dict[str, object]:
    if resource_id == "export_points_csv":
        payload = base64.b64encode(b"lambda,intensity\n400.0,0.1\n").decode("ascii")
        return {
            "format": "csv",
            "mime_type": "text/csv",
            "filename": "points.csv",
            "size_bytes": 27,
            "data_uri": f"data:text/csv;base64,{payload}",
        }
    if resource_id == "export_figure_svg":
        payload = base64.b64encode(b"<svg><path d='M0,0L1,1'/></svg>").decode("ascii")
        return {
            "format": "svg",
            "mime_type": "image/svg+xml",
            "filename": "figure.svg",
            "size_bytes": 31,
            "data_uri": f"data:image/svg+xml;base64,{payload}",
        }
    raise AssertionError(resource_id)


def _manager() -> PreviewSessionManager:
    registry = PreviewerRegistry()
    registry.register(
        PreviewerSpec(
            previewer_id="pkg.spectrum",
            owner_kind=OwnerKind.PACKAGE,
            owner_name="pkg",
            target_type="Spectrum",
            backend_provider=_provider,
            resource_provider=_resource_provider,
        )
    )
    return PreviewSessionManager(registry)


def test_custom_csv_export_resource_is_dispatched_to_package_provider() -> None:
    manager = _manager()
    envelope = manager.create_session(_target())
    assert envelope.session_id is not None

    data = manager.read_resource(envelope.session_id, "export_points_csv", {"format": "csv", "target": "points"})

    assert data["mime_type"] == "text/csv"
    decoded = base64.b64decode(data["data_uri"].split(",", 1)[1]).decode("utf-8")
    assert "lambda,intensity" in decoded
    assert "400.0,0.1" in decoded


def test_custom_figure_export_resource_is_dispatched_to_package_provider() -> None:
    manager = _manager()
    envelope = manager.create_session(_target())
    assert envelope.session_id is not None

    data = manager.read_resource(envelope.session_id, "export_figure_svg", {"format": "svg", "target": "figure"})

    assert data["mime_type"] == "image/svg+xml"
    decoded = base64.b64decode(data["data_uri"].split(",", 1)[1]).decode("utf-8")
    assert "<svg" in decoded
