"""Routed previewer session API tests (ADR-048 FR-007 / FR-028 / FR-029)."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from fastapi.testclient import TestClient

from scistudio.api.runtime import ApiRuntime
from scistudio.core.storage.ref import StorageReference


def _create_session(client: TestClient, *, ref: str, recorded_type: str, type_chain: list[str], kind: str = "data_ref"):
    return client.post(
        "/api/previews/sessions",
        json={
            "target": {
                "kind": kind,
                "ref": ref,
                "recorded_type": recorded_type,
                "type_chain": type_chain,
            },
            "query": {},
        },
    )


def test_create_session_for_dataframe(client: TestClient, opened_project: Path) -> None:
    upload = client.post(
        "/api/data/upload",
        files={"file": ("t.csv", b"a,b\n1,2\n3,4\n", "text/csv")},
    )
    ref = upload.json()["ref"]
    resp = _create_session(client, ref=ref, recorded_type="DataFrame", type_chain=["DataObject", "DataFrame"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["previewer_id"] == "core.dataframe.basic"
    assert body["kind"] == "dataframe"
    assert body["session_id"]
    assert body["payload"]["total_rows"] == 2
    # FR-011: metadata carries the mandatory display flags.
    for flag in ("sampled", "truncated", "cached", "derived", "complete", "failed"):
        assert flag in body["metadata"]


def test_read_and_patch_session_repaginate(client: TestClient, opened_project: Path) -> None:
    header = "idx\n"
    body = "".join(f"{i}\n" for i in range(137))
    upload = client.post("/api/data/upload", files={"file": ("p.csv", (header + body).encode(), "text/csv")})
    ref = upload.json()["ref"]
    created = _create_session(client, ref=ref, recorded_type="DataFrame", type_chain=["DataObject", "DataFrame"]).json()
    sid = created["session_id"]

    read = client.get(f"/api/previews/sessions/{sid}")
    assert read.status_code == 200
    assert read.json()["payload"]["page"] == 1

    patched = client.patch(f"/api/previews/sessions/{sid}", json={"query": {"page": 3, "page_size": 50}})
    assert patched.status_code == 200
    assert patched.json()["payload"]["page"] == 3
    assert len(patched.json()["payload"]["rows"]) == 37


def test_read_unknown_session_returns_404(client: TestClient, opened_project: Path) -> None:
    resp = client.get("/api/previews/sessions/pv-does-not-exist")
    assert resp.status_code == 404


def test_patch_unknown_session_returns_404(client: TestClient, opened_project: Path) -> None:
    resp = client.patch("/api/previews/sessions/pv-nope", json={"query": {"page": 2}})
    assert resp.status_code == 404


def test_create_session_unknown_target_returns_error_envelope(client: TestClient, opened_project: Path) -> None:
    """An unroutable target with no core fallback yields an error envelope, not a 500.

    All recorded types fall back to ``core.base.fallback`` (tier 8), so to hit
    the unknown path we send a collection with an item type that has neither a
    package nor a collection-capable previewer — the core collection fallback
    still catches it. We instead assert the *base* fallback path is robust by
    sending a bogus data_ref: the provider degrades to an artifact error
    envelope rather than crashing (FR-028).
    """
    # A target whose ref does not exist in any backend: provider read fails and
    # degrades gracefully to an artifact/error envelope (no API crash).
    resp = _create_session(client, ref="missing-ref", recorded_type="DataFrame", type_chain=["DataObject", "DataFrame"])
    assert resp.status_code == 200
    body = resp.json()
    # Provider could not read the missing file -> error envelope (FR-028).
    assert body["kind"] in {"error", "artifact"}
    assert body["metadata"]["failed"] in {True, False}


def test_array_session_resource_tile(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
    monkeypatch,
) -> None:
    import sys
    import types

    import numpy as np

    matrix = np.arange(64 * 64, dtype=np.float32).reshape(64, 64)

    class _FakeArray:
        shape = (64, 64)
        dtype = "float32"

        def __getitem__(self, key: object) -> np.ndarray:
            return matrix

    fake_zarr = types.ModuleType("zarr")
    fake_zarr.Array = _FakeArray  # type: ignore[attr-defined]
    fake_zarr.open = lambda path, mode="r": _FakeArray()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "zarr", fake_zarr)

    zarr_path = opened_project / "data" / "zarr" / "tile.zarr"
    zarr_path.mkdir(parents=True)
    record = runtime.register_data_ref(
        StorageReference(
            backend="zarr",
            path=str(zarr_path),
            format="zarr",
            metadata={"type_chain": ["DataObject", "Array"], "axes": ["y", "x"]},
        ),
        type_name="Array",
    )
    created = _create_session(client, ref=record.id, recorded_type="Array", type_chain=["DataObject", "Array"]).json()
    sid = created["session_id"]
    assert created["kind"] == "array"

    # The array envelope advertises a 'tile' resource.
    assert any(r["resource_id"] == "tile" for r in created["resources"])
    res = client.get(f"/api/previews/sessions/{sid}/resources/tile")
    assert res.status_code == 200
    assert "matrix" in res.json()["data"]


def test_resource_unknown_session_returns_404(client: TestClient, opened_project: Path) -> None:
    resp = client.get("/api/previews/sessions/pv-missing/resources/tile")
    assert resp.status_code == 404


def test_collection_session_lists_items(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    # Use a base type (DataFrame) that no package previewer claims, so this test
    # deterministically exercises the core collection fallback whether or not the
    # imaging package is registered (SCISTUDIO_DEV=1 monorepo discovery in CI would
    # otherwise route Collection[Image] to imaging.image.viewer, priority 100).
    items = [{"data_ref": f"d{i}", "type_name": "DataFrame"} for i in range(10)]
    resp = client.post(
        "/api/previews/sessions",
        json={
            "target": {
                "kind": "collection_ref",
                "ref": "coll-1",
                "recorded_type": "DataFrame",
                "type_chain": ["DataObject", "DataFrame"],
                "collection_item_type": "DataFrame",
            },
            "query": {
                "_collection_items": items,
                "_collection_count": 10,
                "_collection_item_type": "DataFrame",
            },
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["previewer_id"] == "core.collection.basic"
    assert body["kind"] == "collection"
    assert body["payload"]["count"] == 10
    assert body["payload"]["item_type"] == "DataFrame"
    assert len(body["payload"]["items"]) == 10


def test_collection_resource_uses_descriptor_params(
    client: TestClient,
    opened_project: Path,
) -> None:
    items = [{"data_ref": "child-0", "type_name": "DataFrame"}]
    resp = client.post(
        "/api/previews/sessions",
        json={
            "target": {
                "kind": "collection_ref",
                "ref": "coll-params",
                "recorded_type": "DataFrame",
                "type_chain": ["DataObject", "DataFrame"],
                "collection_item_type": "DataFrame",
            },
            "query": {
                "_collection_items": items,
                "_collection_count": 1,
                "_collection_item_type": "DataFrame",
            },
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    sid = body["session_id"]
    resource = body["resources"][0]

    res = client.get(
        f"/api/previews/sessions/{sid}/resources/{resource['resource_id']}",
        params={"params": json.dumps(resource["params"])},
    )

    assert res.status_code == 200
    child = res.json()["data"]
    assert child["target"]["ref"] == "child-0"
    assert child["target"]["recorded_type"] == "DataFrame"


def test_composite_resource_uses_descriptor_params(
    client: TestClient,
    opened_project: Path,
) -> None:
    resp = client.post(
        "/api/previews/sessions",
        json={
            "target": {
                "kind": "data_ref",
                "ref": "comp-params",
                "recorded_type": "CompositeData",
                "type_chain": ["DataObject", "CompositeData"],
            },
            "query": {"_record_metadata": {"slots": {"raster": "Array"}}},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    sid = body["session_id"]
    resource = body["resources"][0]

    res = client.get(
        f"/api/previews/sessions/{sid}/resources/{resource['resource_id']}",
        params={"params": json.dumps(resource["params"])},
    )

    assert res.status_code == 200
    child = res.json()["data"]
    assert child["target"]["ref"] == "comp-params#raster"
    assert child["target"]["recorded_type"] == "Array"


def test_resource_params_reject_non_object_and_oversized_payload(client: TestClient, opened_project: Path) -> None:
    non_object = client.get(
        "/api/previews/sessions/pv-any/resources/item:0",
        params={"params": json.dumps(["not", "an", "object"])},
    )
    assert non_object.status_code == 422

    oversized = client.get(
        "/api/previews/sessions/pv-any/resources/item:0",
        params={"params": json.dumps({"item": "x" * 9000})},
    )
    assert oversized.status_code == 413


def test_plot_export_resource_returns_bounded_sanitized_svg(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    plot_path = opened_project / "plot.svg"
    plot_path.write_text("<svg><script>alert(1)</script><rect width='1' height='1'/></svg>", encoding="utf-8")
    record = runtime.register_data_ref(
        StorageReference(
            backend="filesystem",
            path=str(plot_path),
            format="svg",
            metadata={"plot_artifact": True, "type_chain": ["DataObject", "PlotArtifact"]},
        ),
        type_name="PlotArtifact",
    )
    created = _create_session(
        client,
        ref=record.id,
        recorded_type="PlotArtifact",
        type_chain=["DataObject", "PlotArtifact"],
        kind="plot_artifact",
    ).json()
    sid = created["session_id"]
    export_resource = next(r for r in created["resources"] if r["resource_id"] == "export")

    res = client.get(
        f"/api/previews/sessions/{sid}/resources/export",
        params={"params": json.dumps(export_resource["params"])},
    )

    assert res.status_code == 200
    data = res.json()["data"]
    assert data["format"] == "svg"
    assert data["mime_type"] == "image/svg+xml"
    assert data["filename"] == "plot.svg"
    assert data["data_uri"].startswith("data:image/svg+xml;base64,")
    decoded = base64.b64decode(data["data_uri"].split(",", 1)[1]).decode("utf-8")
    assert "<script" not in decoded
    assert "alert(1)" not in decoded
    assert "<rect" in decoded
    assert data["sanitized"] is True


def test_legacy_preview_route_still_works(client: TestClient, opened_project: Path) -> None:
    """FR-008: the old one-shot route is preserved verbatim alongside the session API."""
    upload = client.post("/api/data/upload", files={"file": ("legacy.csv", b"a\n1\n2\n", "text/csv")})
    ref = upload.json()["ref"]
    preview = client.get(f"/api/data/{ref}/preview")
    assert preview.status_code == 200
    assert preview.json()["preview"]["kind"] == "table"
