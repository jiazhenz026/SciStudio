"""Provider-level tests for the generic array previewer (ADR-048 FR-013/FR-014).

These exercise :func:`array_previewer` directly with a stub
:class:`PreviewDataAccess` so the test pins the *payload contract* — the
numeric heatmap matrix, the value extent for the legend, the per-axis slice
descriptors, and the per-axis ``axis_indices`` query passthrough — independent
of any real storage backend.
"""

from __future__ import annotations

from typing import Any

from scistudio.previewers.data_access import ArrayPlane, PreviewDataAccess, SliceAxis
from scistudio.previewers.fallbacks import array_previewer
from scistudio.previewers.models import (
    EnvelopeKind,
    OwnerKind,
    PreviewerSpec,
    PreviewLimits,
    PreviewRequest,
    PreviewTarget,
    TargetKind,
)


class _StubAccess(PreviewDataAccess):
    """Records the slice request and returns a fixed signed ND plane."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[dict[str, Any]] = []

    def array_plane(
        self,
        ref: Any,
        *,
        slice_index: int = 0,
        axis_indices: dict[int, int] | None = None,
    ) -> ArrayPlane:
        self.calls.append({"slice_index": slice_index, "axis_indices": dict(axis_indices or {})})
        return ArrayPlane(
            shape=[4, 6, 3, 3],
            axes=["t", "z", "y", "x"],
            dtype="float64",
            slice_axis_name="t",
            slice_axis_size=4,
            slice_index=(axis_indices or {}).get(0, slice_index),
            slice_axes=[
                SliceAxis(axis=0, name="t", size=4, index=(axis_indices or {}).get(0, slice_index)),
                SliceAxis(axis=1, name="z", size=6, index=(axis_indices or {}).get(1, 0)),
            ],
            matrix=[[-1.0, 0.0, 2.0], [3.0, -4.0, 5.0], [0.0, 1.0, -2.0]],
            vmin=-4.0,
            vmax=5.0,
            truncated=False,
            ndim=4,
        )


def _request(query: dict[str, Any]) -> PreviewRequest:
    target = PreviewTarget(
        kind=TargetKind.DATA_REF,
        ref="r",
        recorded_type="Array",
        type_chain=("DataObject", "Array"),
    )
    spec = PreviewerSpec(
        previewer_id="core.array.basic",
        owner_kind=OwnerKind.CORE,
        owner_name="scistudio",
        target_type="Array",
        backend_provider=array_previewer,
    )
    return PreviewRequest(
        target=target,
        spec=spec,
        query=query,
        data_access=_StubAccess(),
        limits=PreviewLimits(),
    )


def test_array_previewer_emits_numeric_heatmap_payload() -> None:
    request = _request({"_storage": {"backend": "zarr", "path": "x"}})
    env = array_previewer(request)

    assert env.kind is EnvelopeKind.ARRAY
    payload = env.payload
    # The numeric matrix is the primary view (actual values, signed preserved).
    assert payload["matrix"] == [[-1.0, 0.0, 2.0], [3.0, -4.0, 5.0], [0.0, 1.0, -2.0]]
    # Value extent for the legend / diverging colormap (negatives NOT clipped).
    assert payload["vmin"] == -4.0
    assert payload["vmax"] == 5.0
    # Per-axis slice descriptors expose every non-displayed dimension.
    assert payload["slice_axes"] == [
        {"axis": 0, "name": "t", "size": 4, "index": 0},
        {"axis": 1, "name": "z", "size": 6, "index": 0},
    ]
    # ``thumbnail`` remains an alias of the matrix for the scalar/1-D paths.
    assert payload["thumbnail"] == payload["matrix"]
    # Legacy-compat raster src kept for the REST adapter (FR-008).
    assert isinstance(payload["src"], str)


def test_array_previewer_reads_axis_indices_from_query() -> None:
    # The session query carries per-axis selections (string keys after JSON).
    request = _request({"axis_indices": {"0": 2, "1": 5}, "slice_index": 0})
    env = array_previewer(request)

    access = request.data_access
    assert isinstance(access, _StubAccess)
    assert access.calls[0]["axis_indices"] == {0: 2, 1: 5}
    # The echoed descriptors reflect the requested per-axis selection.
    assert env.payload["slice_axes"][0]["index"] == 2
    assert env.payload["slice_axes"][1]["index"] == 5


def test_array_previewer_ignores_malformed_axis_indices() -> None:
    request = _request({"axis_indices": {"bad": "x", "1": 3}})
    env = array_previewer(request)
    access = request.data_access
    assert isinstance(access, _StubAccess)
    # Malformed entries are dropped; the valid one survives.
    assert access.calls[0]["axis_indices"] == {1: 3}
    assert env.kind is EnvelopeKind.ARRAY
