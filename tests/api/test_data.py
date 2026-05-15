"""Tests for data upload, metadata, and preview endpoints."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from scieasy.api.runtime import ApiRuntime, _infer_type_name_from_ref
from scieasy.core.storage.ref import StorageReference
from scieasy.core.types.array import Array
from scieasy.core.types.composite import CompositeData
from scieasy.core.types.series import Series


def test_upload_metadata_and_preview_for_csv_and_text(client: TestClient, opened_project: Path) -> None:
    """Uploads should register data refs that can be previewed later."""
    csv_response = client.post(
        "/api/data/upload",
        files={"file": ("table.csv", b"a,b\n1,2\n3,4\n", "text/csv")},
    )
    assert csv_response.status_code == 200
    csv_ref = csv_response.json()["ref"]

    metadata = client.get(f"/api/data/{csv_ref}")
    assert metadata.status_code == 200
    assert metadata.json()["type_name"] == "DataFrame"
    assert metadata.json()["metadata"]["format"] == "csv"

    preview = client.get(f"/api/data/{csv_ref}/preview")
    assert preview.status_code == 200
    assert preview.json()["preview"]["kind"] == "table"
    assert preview.json()["preview"]["row_count"] == 2

    text_response = client.post(
        "/api/data/upload",
        files={"file": ("notes.txt", b"hello from SciEasy", "text/plain")},
    )
    assert text_response.status_code == 200
    text_ref = text_response.json()["ref"]

    text_preview = client.get(f"/api/data/{text_ref}/preview")
    assert text_preview.status_code == 200
    assert text_preview.json()["preview"]["kind"] == "text"
    assert "hello from SciEasy" in text_preview.json()["preview"]["content"]


def test_preview_supports_image_series_composite_and_artifact_types(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Preview routing should dispatch to type-specific payloads."""
    image_path = opened_project / "data" / "raw" / "image.tiff"
    image_path.write_bytes(b"fake-tiff")

    # T-TRK-004 / ADR-028 §D2: ``TIFFAdapter`` was deleted; the runtime
    # preview path now reads via a deferred ``import tifffile`` inside
    # ``ApiRuntime.preview_data``. The CI environment does not always
    # have the real ``tifffile`` installed, so inject a stub module
    # into ``sys.modules`` whose ``imread`` returns a fixed matrix.
    # This mirrors the OLD test's monkeypatch on
    # ``tiff_adapter.TIFFAdapter.read``.
    import sys
    import types

    fake_matrix = np.array([[0.0, 1.0], [2.0, 3.0]])
    fake_tifffile = types.ModuleType("tifffile")
    fake_tifffile.imread = lambda path: fake_matrix  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tifffile", fake_tifffile)
    image_record = runtime.register_data_ref(
        StorageReference(backend="filesystem", path=str(image_path), format="tiff"),
        type_name=Array.__name__,
    )
    image_preview = client.get(f"/api/data/{image_record.id}/preview")
    assert image_preview.status_code == 200
    assert image_preview.json()["preview"]["kind"] == "image"
    assert image_preview.json()["preview"]["src"].startswith("data:image/png;base64,")

    series_path = opened_project / "data" / "raw" / "series.bin"
    series_path.write_bytes(b"series")
    series_record = runtime.register_data_ref(
        StorageReference(backend="filesystem", path=str(series_path), format="bin"),
        type_name=Series.__name__,
        metadata={"values": [1.0, 2.5, 3.5]},
    )
    series_preview = client.get(f"/api/data/{series_record.id}/preview")
    assert series_preview.status_code == 200
    assert series_preview.json()["preview"]["kind"] == "chart"
    assert len(series_preview.json()["preview"]["points"]) == 3

    composite_path = opened_project / "data" / "raw" / "composite.json"
    composite_path.write_text("{}", encoding="utf-8")
    composite_record = runtime.register_data_ref(
        StorageReference(backend="filesystem", path=str(composite_path), format="json"),
        type_name=CompositeData.__name__,
        metadata={"slots": {"X": "Array", "obs": "DataFrame"}},
    )
    composite_preview = client.get(f"/api/data/{composite_record.id}/preview")
    assert composite_preview.status_code == 200
    assert composite_preview.json()["preview"]["kind"] == "composite"
    assert composite_preview.json()["preview"]["slots"]["obs"] == "DataFrame"

    artifact_path = opened_project / "data" / "raw" / "report.bin"
    artifact_path.write_bytes(b"artifact")
    artifact_record = runtime.register_data_ref(
        StorageReference(backend="filesystem", path=str(artifact_path), format="bin"),
    )
    artifact_preview = client.get(f"/api/data/{artifact_record.id}/preview")
    assert artifact_preview.status_code == 200
    assert artifact_preview.json()["preview"]["kind"] == "artifact"


# ---------------------------------------------------------------------------
# Tests for #407 — _infer_type_name_from_ref honours type_chain
# ---------------------------------------------------------------------------


def test_infer_type_name_from_ref_uses_type_chain_when_present() -> None:
    """_infer_type_name_from_ref returns the rightmost type_chain entry."""
    ref = StorageReference(
        backend="zarr",
        path="/tmp/store.zarr",
        format="zarr",
        metadata={"type_chain": ["DataObject", "Array", "Image"]},
    )
    assert _infer_type_name_from_ref(ref) == "Image"


def test_infer_type_name_from_ref_falls_back_to_extension_without_type_chain() -> None:
    """Without type_chain, _infer_type_name_from_ref falls back to extension heuristic."""
    ref_zarr = StorageReference(backend="zarr", path="/tmp/store.zarr", format="zarr")
    assert _infer_type_name_from_ref(ref_zarr) == Array.__name__

    ref_csv = StorageReference(backend="filesystem", path="/tmp/data.csv", format="csv")
    assert _infer_type_name_from_ref(ref_csv) == "DataFrame"


def test_register_output_payload_preserves_plugin_type_name(
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """register_output_payload with type_chain produces DataRecord.type_name from chain."""
    wire_payload = {
        "backend": "zarr",
        "path": str(opened_project / "data" / "zarr" / "image.zarr"),
        "format": "zarr",
        "metadata": {
            "type_chain": ["DataObject", "Array", "Image"],
            "axes": ["y", "x"],
            "shape": [512, 512],
            "dtype": "uint16",
        },
    }
    result = runtime.register_output_payload(wire_payload)
    data_ref = result["data_ref"]
    assert result["type_name"] == "Image"

    record = runtime.get_data_record(data_ref)
    assert record.type_name == "Image"
    assert record.type_chain == ["DataObject", "Array", "Image"]


def test_preview_data_dispatches_plugin_image_type_via_type_chain(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """preview_data returns 'image' kind for a plugin Image type registered via type_chain."""
    import sys
    import types

    fake_matrix = np.array([[0.0, 1.0], [2.0, 3.0]])
    fake_tifffile = types.ModuleType("tifffile")
    fake_tifffile.imread = lambda path: fake_matrix  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tifffile", fake_tifffile)

    image_path = opened_project / "data" / "raw" / "plugin_image.tiff"
    image_path.write_bytes(b"fake-tiff")

    # Simulate a plugin Image type (subclass of Array) registered via type_chain.
    # The DataRecord.type_name is "Image", not "Array", which is what broke
    # the old hardcoded comparison.
    record = runtime.register_data_ref(
        StorageReference(
            backend="filesystem",
            path=str(image_path),
            format="tiff",
            metadata={"type_chain": ["DataObject", "Array", "Image"]},
        ),
        type_name="Image",
    )
    # "Image" is registered in the TypeRegistry via the imaging plugin or
    # the monorepo scan.  If not installed, TypeRegistry.resolve returns None
    # and preview_data falls back to the .tiff suffix path — either way the
    # kind should be "image".
    preview = client.get(f"/api/data/{record.id}/preview")
    assert preview.status_code == 200
    assert preview.json()["preview"]["kind"] == "image"


def test_preview_data_supports_zarr_image_payloads(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Zarr-backed array/image payloads should preview as images, not artifacts."""
    import sys
    import types

    zarr_path = opened_project / "data" / "zarr" / "preview_image.zarr"
    zarr_path.mkdir(parents=True)

    fake_matrix = np.array([[0.0, 1.0], [2.0, 3.0]])

    class _FakeArray:
        def __getitem__(self, key: object) -> np.ndarray:
            return fake_matrix

    fake_zarr = types.ModuleType("zarr")
    fake_zarr.Array = _FakeArray  # type: ignore[attr-defined]
    fake_zarr.open = lambda path, mode="r": _FakeArray()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "zarr", fake_zarr)

    record = runtime.register_data_ref(
        StorageReference(
            backend="zarr",
            path=str(zarr_path),
            format="zarr",
            metadata={"type_chain": ["DataObject", "Array", "Image"]},
        ),
        type_name="Image",
    )

    preview = client.get(f"/api/data/{record.id}/preview")
    assert preview.status_code == 200
    assert preview.json()["preview"]["kind"] == "image"
    assert preview.json()["preview"]["src"].startswith("data:image/png;base64,")


def _install_fake_zarr(monkeypatch: MonkeyPatch, matrix: np.ndarray) -> None:
    """Helper: monkeypatch ``zarr`` so ``zarr.open()`` yields *matrix*.

    Used by the #899 3-D viewer tests below. ``_FakeArray[...]`` returns
    *matrix* so that ``_load_preview_matrix`` produces the numpy array
    the test wants to slice through.
    """
    import sys
    import types

    class _FakeArray:
        def __getitem__(self, key: object) -> np.ndarray:
            return matrix

    fake_zarr = types.ModuleType("zarr")
    fake_zarr.Array = _FakeArray  # type: ignore[attr-defined]
    fake_zarr.open = lambda path, mode="r": _FakeArray()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "zarr", fake_zarr)


# ---------------------------------------------------------------------------
# Tests for #899 — 3-D viewer single-slider preview
# ---------------------------------------------------------------------------


def test_preview_data_2d_image_has_no_slider_fields(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """ndim == 2: no slice_axis_* fields → frontend renders no slider."""
    matrix = np.arange(256, dtype=np.float32).reshape(16, 16)
    _install_fake_zarr(monkeypatch, matrix)

    zarr_path = opened_project / "data" / "zarr" / "img2d.zarr"
    zarr_path.mkdir(parents=True)
    record = runtime.register_data_ref(
        StorageReference(
            backend="zarr",
            path=str(zarr_path),
            format="zarr",
            metadata={
                "type_chain": ["DataObject", "Array", "Image"],
                "axes": ["y", "x"],
                "shape": [16, 16],
            },
        ),
        type_name="Image",
    )

    body = client.get(f"/api/data/{record.id}/preview").json()["preview"]
    assert body["kind"] == "image"
    assert body["shape"] == [16, 16]
    assert body["axes"] == ["y", "x"]
    assert body["slice_axis_name"] is None
    assert body["slice_axis_size"] is None
    assert body["slice_index"] is None


def test_preview_data_3d_yxc_image_renders_slider_for_c_axis(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """(y, x, c) RGB plot: slider axis is 'c' with size 3."""
    # Channels must differ in PIXEL DISTRIBUTION (not just scale) because
    # ``_image_data_uri_from_matrix`` normalizes per-slab — three uniform
    # channels would all become identical max-white PNGs.
    base = np.arange(96, dtype=np.float32).reshape(8, 12)
    matrix = np.stack([base, np.fliplr(base), np.flipud(base)], axis=-1)
    assert matrix.shape == (8, 12, 3)
    _install_fake_zarr(monkeypatch, matrix)

    zarr_path = opened_project / "data" / "zarr" / "rgb.zarr"
    zarr_path.mkdir(parents=True)
    record = runtime.register_data_ref(
        StorageReference(
            backend="zarr",
            path=str(zarr_path),
            format="zarr",
            metadata={
                "type_chain": ["DataObject", "Array", "Image"],
                "axes": ["y", "x", "c"],
                "shape": [8, 12, 3],
            },
        ),
        type_name="Image",
    )

    body = client.get(f"/api/data/{record.id}/preview").json()["preview"]
    assert body["kind"] == "image"
    # Original shape preserved.
    assert body["shape"] == [8, 12, 3]
    assert body["axes"] == ["y", "x", "c"]
    assert body["slice_axis_name"] == "c"
    assert body["slice_axis_size"] == 3
    assert body["slice_index"] == 0

    # Slider drag to channel 2 must change the rendered slab.
    body2 = client.get(f"/api/data/{record.id}/preview?slice=2").json()["preview"]
    assert body2["slice_index"] == 2
    assert body2["src"] != body["src"]


def test_preview_data_3d_zyx_image_picks_z_as_slider(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """(z, y, x) z-stack: axes-aware detection picks 'z' as slider axis."""
    matrix = np.arange(5 * 4 * 6, dtype=np.float32).reshape(5, 4, 6)
    _install_fake_zarr(monkeypatch, matrix)

    zarr_path = opened_project / "data" / "zarr" / "zyx.zarr"
    zarr_path.mkdir(parents=True)
    record = runtime.register_data_ref(
        StorageReference(
            backend="zarr",
            path=str(zarr_path),
            format="zarr",
            metadata={
                "type_chain": ["DataObject", "Array", "Image"],
                "axes": ["z", "y", "x"],
                "shape": [5, 4, 6],
            },
        ),
        type_name="Image",
    )

    body = client.get(f"/api/data/{record.id}/preview").json()["preview"]
    assert body["shape"] == [5, 4, 6]
    assert body["slice_axis_name"] == "z"
    assert body["slice_axis_size"] == 5


def test_preview_data_3d_no_axes_uses_axis0_fallback(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """No axes declared: last 2 dims = (y, x); first dim becomes slider 'axis 0'."""
    matrix = np.zeros((7, 9, 11), dtype=np.float32)
    _install_fake_zarr(monkeypatch, matrix)

    zarr_path = opened_project / "data" / "zarr" / "noaxes.zarr"
    zarr_path.mkdir(parents=True)
    record = runtime.register_data_ref(
        StorageReference(
            backend="zarr",
            path=str(zarr_path),
            format="zarr",
            metadata={"type_chain": ["DataObject", "Array"]},
        ),
        type_name="Array",
    )

    body = client.get(f"/api/data/{record.id}/preview").json()["preview"]
    assert body["axes"] == []
    assert body["slice_axis_name"] == "axis 0"
    assert body["slice_axis_size"] == 7


def test_preview_data_clamps_out_of_range_slice_query(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """?slice=999 on a 3-slice array clamps to 2 and returns 200, not 400."""
    matrix = np.zeros((4, 5, 3), dtype=np.float32)
    _install_fake_zarr(monkeypatch, matrix)

    zarr_path = opened_project / "data" / "zarr" / "clamp.zarr"
    zarr_path.mkdir(parents=True)
    record = runtime.register_data_ref(
        StorageReference(
            backend="zarr",
            path=str(zarr_path),
            format="zarr",
            metadata={
                "type_chain": ["DataObject", "Array", "Image"],
                "axes": ["y", "x", "c"],
                "shape": [4, 5, 3],
            },
        ),
        type_name="Image",
    )

    high = client.get(f"/api/data/{record.id}/preview?slice=999")
    assert high.status_code == 200
    assert high.json()["preview"]["slice_index"] == 2

    low = client.get(f"/api/data/{record.id}/preview?slice=-5")
    assert low.status_code == 200
    assert low.json()["preview"]["slice_index"] == 0


def test_preview_data_dispatches_plugin_spectrum_type_via_type_chain(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """preview_data returns 'chart' kind for a plugin Spectrum type registered via type_chain."""
    series_path = opened_project / "data" / "raw" / "spectrum.bin"
    series_path.write_bytes(b"spectrum-data")

    record = runtime.register_data_ref(
        StorageReference(
            backend="filesystem",
            path=str(series_path),
            format="bin",
            metadata={"type_chain": ["DataObject", "Series", "Spectrum"], "values": [1.0, 2.5, 3.5]},
        ),
        type_name="Spectrum",
        metadata={"values": [1.0, 2.5, 3.5]},
    )
    # "Spectrum" may or may not be in the TypeRegistry (depends on plugins
    # installed).  With type_chain present, issubclass(resolved, Series) works
    # if registered.  As a fallback, the type_name "Spectrum" != "Series" so
    # we also accept the chart kind via the Series fallback condition check.
    # The test asserts that either the registry path or the name-equality path
    # produces "chart" — no "artifact" should ever be returned.
    preview = client.get(f"/api/data/{record.id}/preview")
    assert preview.status_code == 200
    # Spectrum falls back to Series name check or registry-based issubclass
    assert preview.json()["preview"]["kind"] == "chart"
