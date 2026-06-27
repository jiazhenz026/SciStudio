"""Trivial fixture previewers mirroring a package's previewer surface.

Provides a :func:`get_previewers` factory returning ``PreviewerSpec`` for
the fixture :class:`Image` and :class:`Label` types, plus minimal backend
providers and a same-origin ``viewer.js`` asset. This lets core's previewer
registry / routing / asset-serving machinery be tested against a stand-in
package instead of the decoupled imaging package.

The providers return a bounded ARRAY/COMPOSITE envelope with no real data
read — just enough structure for routing tests to assert previewer id and
envelope kind.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scistudio.core.storage.ref import StorageReference
from scistudio.previewers.models import (
    PREVIEWER_API_VERSION,
    EnvelopeKind,
    FrontendManifest,
    OwnerKind,
    PreviewEnvelope,
    PreviewerSpec,
    PreviewMetadata,
    PreviewRequest,
)

IMAGE_PREVIEWER_ID = "fixture.image.viewer"
LABEL_PREVIEWER_ID = "fixture.label.viewer"
OWNER_NAME = "scistudio-blocks-fixture"
VIEWER_BUNDLE_VERSION = "0.1.0"
_VIEWER_FILE = "viewer.js"
_ASSET_ROOT = str(Path(__file__).resolve().parent / "assets")


def _module_url(previewer_id: str) -> str:
    return f"/api/previews/assets/{previewer_id}/{_VIEWER_FILE}"


def _frontend_manifest(previewer_id: str) -> FrontendManifest:
    return FrontendManifest(
        previewer_id=previewer_id,
        module_url=_module_url(previewer_id),
        export_name="default",
        css=(),
        version=VIEWER_BUNDLE_VERSION,
        api_version=PREVIEWER_API_VERSION,
        asset_root=_ASSET_ROOT,
    )


def _ref_for(request: PreviewRequest) -> StorageReference:
    storage = request.query.get("_storage") or {}
    return StorageReference(
        backend=str(storage.get("backend", "filesystem")),
        path=str(storage.get("path", request.target.ref)),
        format=storage.get("format"),
        metadata=storage.get("metadata"),
    )


def image_provider(request: PreviewRequest) -> PreviewEnvelope:
    """Return an ARRAY envelope for a fixture Image.

    Reads a single 2-D TIFF plane via ``tifffile`` from the catalog-resolved
    storage path and encodes it as a PNG data-URI through the host data-access
    helper. Intentionally minimal: no slicing, downsampling, LUT, or OME — just
    enough for routing/round-trip tests to observe a real shape + PNG ``src``.
    """
    ref = _ref_for(request)
    try:
        import numpy as np
        import tifffile

        arr = np.asarray(tifffile.imread(str(ref.path)))
        shape = [int(d) for d in arr.shape]
        plane = arr
        while plane.ndim > 2:
            plane = plane[0]
        if plane.ndim == 1:
            plane = plane.reshape(1, int(plane.shape[0]))
        matrix: list[list[float | None]] = [[float(v) for v in row] for row in plane.tolist()]
        src = request.data_access.png_data_uri(matrix)
    except Exception:
        shape = []
        src = ""
    payload: dict[str, Any] = {"shape": shape, "dtype": "uint8", "axes": [], "src": src}
    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.ARRAY,
        payload=payload,
        metadata=PreviewMetadata(complete=True),
    )


def label_provider(request: PreviewRequest) -> PreviewEnvelope:
    """Return a minimal COMPOSITE envelope for a fixture Label."""
    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.COMPOSITE,
        payload={"slots": {}},
        metadata=PreviewMetadata(complete=True),
    )


def get_previewers() -> list[PreviewerSpec]:
    """Return the fixture package's ``PreviewerSpec`` list."""
    return [
        PreviewerSpec(
            previewer_id=IMAGE_PREVIEWER_ID,
            owner_kind=OwnerKind.PACKAGE,
            owner_name=OWNER_NAME,
            target_type="Image",
            supports_collection=False,
            priority=100,
            capabilities=("slice", "metadata"),
            backend_provider=image_provider,
            frontend_manifest=_frontend_manifest(IMAGE_PREVIEWER_ID),
        ),
        PreviewerSpec(
            previewer_id=LABEL_PREVIEWER_ID,
            owner_kind=OwnerKind.PACKAGE,
            owner_name=OWNER_NAME,
            target_type="Label",
            supports_collection=False,
            priority=100,
            capabilities=("slots", "metadata"),
            backend_provider=label_provider,
            frontend_manifest=_frontend_manifest(LABEL_PREVIEWER_ID),
        ),
    ]


__all__ = [
    "IMAGE_PREVIEWER_ID",
    "LABEL_PREVIEWER_ID",
    "OWNER_NAME",
    "VIEWER_BUNDLE_VERSION",
    "get_previewers",
    "image_provider",
    "label_provider",
]
