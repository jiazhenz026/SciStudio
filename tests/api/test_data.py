"""Tests for data upload + metadata registration.

ADR-048 no-compat (#1604): the legacy ``GET /api/data/{ref}/preview`` route and
its per-kind legacy-shape tests were removed. Preview behavior is covered
through the routed session API in ``tests/api/test_previewers.py`` and the
provider unit tests in ``tests/previewers/``.
"""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from scistudio.api.runtime import ApiRuntime, _infer_type_name_from_ref
from scistudio.core.storage.ref import StorageReference
from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact


class _DirectUploadRuntime:
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir
        self.destination: Path | None = None
        self.staged_path: Path | None = None
        self.finished = False
        self.discarded = False

    def stage_upload_file(self, filename: str) -> tuple[Path, Path]:
        destination = self.project_dir / "data" / "raw" / Path(filename).name
        destination.parent.mkdir(parents=True, exist_ok=True)
        staged_path = destination.parent / f".{destination.name}.upload"
        self.destination = destination
        self.staged_path = staged_path
        return destination, staged_path

    def finish_staged_upload(self, destination: Path, staged_path: Path) -> dict[str, Any]:
        self.finished = True
        staged_path.replace(destination)
        return {
            "ref": "data-1",
            "type_name": "Artifact",
            "metadata": {"size": destination.stat().st_size},
        }

    def discard_staged_upload(self, staged_path: Path) -> None:
        self.discarded = True
        with suppress(FileNotFoundError):
            staged_path.unlink()

    def upload_file(self, filename: str, content: bytes) -> dict[str, Any]:
        raise AssertionError("upload route must stream through staged upload paths")


def test_upload_metadata_and_preview_for_csv_and_text(client: TestClient, opened_project: Path) -> None:
    """Uploads should register data refs that can be previewed later.

    ADR-048 no-compat (#1604): the legacy ``GET /api/data/{ref}/preview`` route
    was removed; this asserts upload + metadata registration. Preview behavior
    for each kind is covered through the routed session API in
    ``tests/api/test_previewers.py``.
    """
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

    # The uploaded DataFrame is previewable through the routed session API.
    session = client.post(
        "/api/previews/sessions",
        json={"target": {"kind": "data_ref", "ref": csv_ref}, "query": {}},
    )
    assert session.status_code == 200, session.text
    assert session.json()["kind"] == "dataframe"
    assert session.json()["payload"]["total_rows"] == 2

    text_response = client.post(
        "/api/data/upload",
        files={"file": ("notes.txt", b"hello from SciStudio", "text/plain")},
    )
    assert text_response.status_code == 200
    text_ref = text_response.json()["ref"]

    text_session = client.post(
        "/api/previews/sessions",
        json={"target": {"kind": "data_ref", "ref": text_ref}, "query": {}},
    )
    assert text_session.status_code == 200, text_session.text
    assert text_session.json()["kind"] == "text"
    assert "hello from SciStudio" in text_session.json()["payload"]["content"]


def test_upload_oversized_file_rejected_with_413(
    client: TestClient,
    opened_project: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """#1526: an upload exceeding the cap is rejected with 413."""
    from scistudio.api.routes import data as data_routes

    # Shrink the cap so the test does not need a multi-GB payload.
    monkeypatch.setattr(data_routes, "MAX_UPLOAD_SIZE", 1024)
    monkeypatch.setattr(data_routes, "_UPLOAD_CHUNK_SIZE", 256)

    payload = b"x" * 4096  # 4 KiB > 1 KiB cap
    resp = client.post(
        "/api/data/upload",
        files={"file": ("big.bin", payload, "application/octet-stream")},
    )
    assert resp.status_code == 413
    assert "too large" in resp.json()["detail"].lower()


def test_upload_at_cap_boundary_is_accepted(
    client: TestClient,
    opened_project: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """#1526: an upload exactly at the cap is accepted (off-by-one guard)."""
    from scistudio.api.routes import data as data_routes

    monkeypatch.setattr(data_routes, "MAX_UPLOAD_SIZE", 1024)
    monkeypatch.setattr(data_routes, "_UPLOAD_CHUNK_SIZE", 256)

    payload = b"y" * 1024  # exactly at the cap
    resp = client.post(
        "/api/data/upload",
        files={"file": ("atcap.bin", payload, "application/octet-stream")},
    )
    assert resp.status_code == 200


def test_upload_streams_success_without_runtime_byte_buffer(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """#1526: successful uploads are streamed to a staged file, not bytes API."""
    import asyncio

    from scistudio.api.routes import data as data_routes

    monkeypatch.setattr(data_routes, "MAX_UPLOAD_SIZE", 4096)
    monkeypatch.setattr(data_routes, "_UPLOAD_CHUNK_SIZE", 128)

    class _ChunkedUpload:
        filename = "stream.bin"

        def __init__(self, payload: bytes) -> None:
            self._payload = payload
            self._offset = 0

        async def read(self, size: int = -1) -> bytes:
            if self._offset >= len(self._payload):
                return b""
            n = len(self._payload) - self._offset if size < 0 else min(size, len(self._payload) - self._offset)
            start = self._offset
            self._offset += n
            return self._payload[start : start + n]

    runtime = _DirectUploadRuntime(tmp_path)
    payload = b"streamed-body" * 64

    response = asyncio.run(data_routes.upload_data(_ChunkedUpload(payload), runtime=runtime))  # type: ignore[arg-type]

    assert response.ref == "data-1"
    assert runtime.finished is True
    assert runtime.destination is not None
    assert runtime.destination.read_bytes() == payload


def test_upload_streams_and_aborts_without_buffering_whole_body(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """#1526: the handler aborts mid-stream and never reads the full body.

    Drives ``upload_data`` directly with a fake ``UploadFile`` that records
    how many bytes were handed out. Once the running counter crosses the cap
    the handler must raise 413 *before* draining the rest of the stream — i.e.
    it must not materialize the entire (potentially OOM-sized) body first.
    """
    import asyncio

    from fastapi import HTTPException

    from scistudio.api.routes import data as data_routes

    monkeypatch.setattr(data_routes, "MAX_UPLOAD_SIZE", 1024)
    monkeypatch.setattr(data_routes, "_UPLOAD_CHUNK_SIZE", 256)

    class _FakeUpload:
        """Emit a very large body 256 bytes at a time, counting reads."""

        filename = "huge.bin"

        def __init__(self, total_bytes: int) -> None:
            self._remaining = total_bytes
            self.bytes_served = 0

        async def read(self, size: int = -1) -> bytes:
            if self._remaining <= 0:
                return b""
            n = self._remaining if size < 0 else min(size, self._remaining)
            self._remaining -= n
            self.bytes_served += n
            return b"z" * n

    # 1 GiB "virtual" body; if the handler buffered the whole thing it would
    # serve all of it. We assert it stops far earlier.
    total = 1024 * 1024 * 1024
    fake = _FakeUpload(total)
    runtime = _DirectUploadRuntime(tmp_path)
    existing = tmp_path / "data" / "raw" / "huge.bin"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_bytes(b"existing")

    raised = False
    try:
        asyncio.run(data_routes.upload_data(fake, runtime=runtime))  # type: ignore[arg-type]
    except HTTPException as exc:
        raised = True
        assert exc.status_code == 413

    assert raised, "oversized stream should raise 413"
    # The handler must have stopped reading shortly after crossing the cap,
    # not drained the whole 1 GiB body.
    assert fake.bytes_served <= data_routes.MAX_UPLOAD_SIZE + data_routes._UPLOAD_CHUNK_SIZE
    assert fake.bytes_served < total
    assert runtime.finished is False
    assert runtime.discarded is True
    assert runtime.staged_path is not None
    assert not runtime.staged_path.exists()
    assert existing.read_bytes() == b"existing"


# ADR-048 no-compat (#1604): the per-type legacy-preview-shape tests that lived
# here (image/chart/composite/artifact via GET /api/data/{ref}/preview) were
# removed with the route. Per-kind preview dispatch is covered through the
# routed session API in ``tests/api/test_previewers.py`` and the provider unit
# tests in ``tests/previewers/``.


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

    ref_tiff = StorageReference(backend="filesystem", path="/tmp/image.tif", format="tiff")
    assert _infer_type_name_from_ref(ref_tiff) == Artifact.__name__

    ref_png = StorageReference(backend="filesystem", path="/tmp/image.png", format="png")
    assert _infer_type_name_from_ref(ref_png) == Artifact.__name__


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


def test_register_output_payload_stamps_display_name_from_user_hook(
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """#1812: the descriptor carries a backend-resolved ``display_name``.

    ``user['display_name']`` (the producer override, e.g. the xlsx loader's
    ``"<file> — <sheet>"``) is resolved by the single backend authority and
    stamped onto the item descriptor so the frontend reads one field.
    """
    wire_payload = {
        "backend": "arrow",
        "path": str(opened_project / "data" / "arrow" / "sheet2.arrow"),
        "format": "arrow",
        "metadata": {
            "type_chain": ["DataObject", "DataFrame"],
            "user": {"sheet_name": "beta", "display_name": "exp.xlsx — beta"},
        },
    }
    result = runtime.register_output_payload(wire_payload)
    assert result["display_name"] == "exp.xlsx — beta"


def test_register_output_payload_stamps_display_name_from_source_file(
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """#1812: with no explicit override, the resolver falls back to the
    typed ``meta.source_file`` basename."""
    wire_payload = {
        "backend": "zarr",
        "path": str(opened_project / "data" / "zarr" / "beads.zarr"),
        "format": "zarr",
        "metadata": {
            "type_chain": ["DataObject", "Array", "Image"],
            "meta": {"source_file": "/uploads/beads.tif"},
        },
    }
    result = runtime.register_output_payload(wire_payload)
    assert result["display_name"] == "beads.tif"


def test_register_output_payload_omits_display_name_when_unresolved(
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """#1812: the field is omitted (not empty) when nothing resolves, so the
    frontend keeps its own truncated-ref fallback."""
    wire_payload = {
        "backend": "zarr",
        "path": str(opened_project / "data" / "zarr" / "anon.zarr"),
        "format": "zarr",
        "metadata": {"type_chain": ["DataObject", "Array", "Image"]},
    }
    result = runtime.register_output_payload(wire_payload)
    assert "display_name" not in result
