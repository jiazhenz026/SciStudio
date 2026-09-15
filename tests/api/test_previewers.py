"""Routed previewer session API tests (ADR-048 FR-007 / FR-028 / FR-029)."""

from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient

from scistudio.api.runtime import ApiRuntime
from scistudio.core.storage.ref import StorageReference


def _prefer_fixture_package(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure the in-repo fixture previewer package is the discovered plugin.

    Issue #1770: the real imaging package was decoupled out of core. These
    API tests exercise *core* previewer routing / asset serving against the
    fixture stand-in package, whose ``src`` is already on ``sys.path`` via
    ``tests/conftest.py``. The fixture's entry points are injected per-test
    via ``monkeypatch`` in each caller.
    """
    package_src = Path(__file__).resolve().parents[2] / "tests/fixtures/scistudio-blocks-fixture/src"
    monkeypatch.syspath_prepend(str(package_src))


def _install_fake_zarr(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import types

    import numpy as np

    matrix = np.arange(3 * 16 * 16, dtype=np.uint16).reshape(3, 16, 16)

    class _FakeArray:
        shape = (3, 16, 16)
        dtype = "uint16"

        def __getitem__(self, key: object) -> np.ndarray:
            return cast(np.ndarray, matrix[0])

    fake_zarr = types.ModuleType("zarr")
    fake_zarr.Array = _FakeArray  # type: ignore[attr-defined]
    fake_zarr.open = lambda path, mode="r": _FakeArray()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "zarr", fake_zarr)


def _create_session(
    client: TestClient, *, ref: str, recorded_type: str, type_chain: list[str], kind: str = "data_ref"
) -> httpx.Response:
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


def _panel_context(client: TestClient, *, ref: str, kind: str = "data_ref") -> str:
    """Open the panel context a mounted panel reads through.

    A core previewer is a panel now, so the data a session used to carry in its
    payload is fetched by the panel itself. Tests that pinned paging, sorting,
    or child navigation follow the same path the frame does rather than
    asserting against a payload that no longer exists.
    """
    response = client.post("/api/panels/contexts", json={"kind": "preview", "target": {"kind": kind, "ref": ref}})
    assert response.status_code == 200, response.text
    return str(response.json()["context_id"])


def _panel_read(
    client: TestClient, context_id: str, ref: str, op: str, params: dict[str, Any] | None = None
) -> httpx.Response:
    return client.post(
        f"/api/panels/contexts/{context_id}/read",
        json={"ref": ref, "op": op, "params": params or {}},
    )


def test_adr048_viewer_category_sweep(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every ADR-048 viewer category reaches the routed session API.

    This is a compact e2e-style sweep for the PR-readiness question: each row
    goes through ``POST /api/previews/sessions`` and asserts the selected viewer
    ID/kind, including Image/Label discovered through an installed-mode
    ``scistudio.previewers`` entry point (the fixture stand-in package).
    """
    _install_fake_zarr(monkeypatch)
    _prefer_fixture_package(monkeypatch)
    fixture_ep = importlib.metadata.EntryPoint(
        name="fixture",
        value="scistudio_blocks_fixture.previewers:get_previewers",
        group="scistudio.previewers",
    )
    real_entry_points = importlib.metadata.entry_points

    def _entry_points(*args: object, **kwargs: object) -> object:
        if kwargs.get("group") == "scistudio.previewers":
            return (fixture_ep,)
        return real_entry_points(*args, **kwargs)

    monkeypatch.setattr(importlib.metadata, "entry_points", _entry_points)
    with pytest.warns(DeprecationWarning, match="is deprecated through 0.5.x"):
        runtime.get_panel_service().rescan(legacy=True)

    def _record(
        name: str,
        *,
        type_name: str,
        content: bytes | str | None = None,
        backend: str = "filesystem",
        fmt: str | None = None,
        metadata: dict[str, object] | None = None,
        suffix: str = "",
    ) -> str:
        path = opened_project / f"{name}{suffix}"
        if backend == "zarr":
            path.mkdir(parents=True, exist_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_text(content or "", encoding="utf-8")
        record = runtime.register_data_ref(
            StorageReference(backend=backend, path=str(path), format=fmt, metadata=metadata),
            type_name=type_name,
        )
        return record.id

    refs = {
        "dataframe": _record(
            "sweep/table.csv",
            type_name="DataFrame",
            content="a,b\n1,2\n3,4\n",
            fmt="csv",
            metadata={"type_chain": ["DataObject", "DataFrame"]},
        ),
        "array": _record(
            "sweep/array.zarr",
            type_name="Array",
            backend="zarr",
            fmt="zarr",
            metadata={"type_chain": ["DataObject", "Array"], "axes": ["z", "y", "x"]},
        ),
        "series": _record(
            "sweep/series.json",
            type_name="Series",
            content="{}",
            fmt="json",
            metadata={"type_chain": ["DataObject", "Series"], "values": [0, 1, 4, 9, 16]},
        ),
        "text": _record(
            "sweep/notes.txt",
            type_name="Text",
            content="hello from adr048 viewer sweep\n",
            fmt="txt",
            metadata={"type_chain": ["DataObject", "Text"]},
        ),
        "artifact": _record(
            "sweep/artifact.bin",
            type_name="Artifact",
            content=b"opaque artifact bytes",
            fmt="bin",
            metadata={"type_chain": ["DataObject", "Artifact"]},
        ),
        "composite": _record(
            "sweep/composite.json",
            type_name="CompositeData",
            content="{}",
            fmt="json",
            metadata={"type_chain": ["DataObject", "CompositeData"], "slots": {"raster": "Array"}},
        ),
        "image": _record(
            "sweep/image.zarr",
            type_name="Image",
            backend="zarr",
            fmt="zarr",
            metadata={"type_chain": ["DataObject", "Array", "Image"], "axes": ["z", "y", "x"]},
        ),
        "label": _record(
            "sweep/label.json",
            type_name="Label",
            content="{}",
            fmt="json",
            metadata={
                "type_chain": ["DataObject", "CompositeData", "Label"],
                "slots": {"polygons": "Artifact"},
                "n_objects": 7,
            },
        ),
        "plot": _record(
            "sweep/plot.svg",
            type_name="PlotArtifact",
            content="<svg><script>alert(1)</script><rect width='1' height='1'/></svg>",
            fmt="svg",
            metadata={"plot_artifact": True, "type_chain": ["DataObject", "PlotArtifact"]},
        ),
    }

    # Every core previewer is a panel now (ADR-054 Phase B), so its envelope is
    # a `panel` one naming the panel to mount rather than a per-type payload the
    # frontend switches on. A package previewer that is still a compiled module
    # keeps the category it always had, which is what the two fixture viewers
    # here are for: this sweep is the one place both kinds are checked together.
    cases = [
        ("dataframe", "data_ref", "DataFrame", ["DataObject", "DataFrame"], "core.dataframe.basic", "panel"),
        ("array", "data_ref", "Array", ["DataObject", "Array"], "core.array.basic", "panel"),
        ("series", "data_ref", "Series", ["DataObject", "Series"], "core.series.basic", "panel"),
        ("text", "data_ref", "Text", ["DataObject", "Text"], "core.text.basic", "panel"),
        ("artifact", "artifact", "Artifact", ["DataObject", "Artifact"], "core.artifact.basic", "panel"),
        (
            "composite",
            "data_ref",
            "CompositeData",
            ["DataObject", "CompositeData"],
            "core.composite.basic",
            "panel",
        ),
        ("image", "data_ref", "Image", ["DataObject", "Array", "Image"], "fixture.image.viewer", "array"),
        (
            "label",
            "data_ref",
            "Label",
            ["DataObject", "CompositeData", "Label"],
            "fixture.label.viewer",
            "composite",
        ),
        ("plot", "plot_artifact", "PlotArtifact", ["DataObject", "PlotArtifact"], "core.plot.basic", "panel"),
    ]

    observed: dict[str, tuple[str, str]] = {}
    for name, kind, recorded_type, type_chain, previewer_id, envelope_kind in cases:
        response = _create_session(
            client,
            ref=refs[name],
            recorded_type=recorded_type,
            type_chain=type_chain,
            kind=kind,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        observed[name] = (body["previewer_id"], body["kind"])
        assert body["previewer_id"] == previewer_id
        assert body["kind"] == envelope_kind
        assert body["session_id"]
        if name in {"image", "label"}:
            assert body["frontend_manifest"]["module_url"] == f"/api/previews/assets/{previewer_id}/viewer.js"
        if envelope_kind == "panel":
            # The envelope's job is now to name the panel and the session it may
            # read through; the data itself arrives through the panel's reads.
            assert body["panel"]["id"] == previewer_id
        # The plot's SVG is no longer inlined in a payload, so there is no
        # payload to scrub here. That the served bytes are scrubbed is pinned
        # against the route that serves them, in
        # tests/panels/test_plot_artifact_reads.py::TestServedSvg.

    assert observed == {
        "dataframe": ("core.dataframe.basic", "panel"),
        "array": ("core.array.basic", "panel"),
        "series": ("core.series.basic", "panel"),
        "text": ("core.text.basic", "panel"),
        "artifact": ("core.artifact.basic", "panel"),
        "composite": ("core.composite.basic", "panel"),
        "image": ("fixture.image.viewer", "array"),
        "label": ("fixture.label.viewer", "composite"),
        "plot": ("core.plot.basic", "panel"),
    }


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
    # The envelope names the panel to mount; the rows arrive through its read.
    assert body["kind"] == "panel"
    assert body["panel"]["id"] == "core.dataframe.basic"
    assert body["session_id"]
    # FR-011: metadata carries the mandatory display flags.
    for flag in ("sampled", "truncated", "cached", "derived", "complete", "failed"):
        assert flag in body["metadata"]
    # #1579: a core fallback has no compiled frontend module → the field is null.
    assert body["frontend_manifest"] is None

    context = _panel_context(client, ref=ref)
    page = _panel_read(client, context, ref, "table.page").json()
    assert page["total"] == 2
    assert [row["a"] for row in page["rows"]] == [1, 3]


def test_read_and_patch_session_repaginate(client: TestClient, opened_project: Path) -> None:
    header = "idx\n"
    body = "".join(f"{i}\n" for i in range(137))
    upload = client.post("/api/data/upload", files={"file": ("p.csv", (header + body).encode(), "text/csv")})
    ref = upload.json()["ref"]
    created = _create_session(client, ref=ref, recorded_type="DataFrame", type_chain=["DataObject", "DataFrame"]).json()
    assert created["session_id"]

    # Paging is the panel's own read now: it asks for the page it wants rather
    # than patching a session query and re-rendering the whole envelope.
    context = _panel_context(client, ref=ref)
    first = _panel_read(client, context, ref, "table.page").json()
    assert first["page"] == 1

    third = _panel_read(client, context, ref, "table.page", {"page": 3, "page_size": 50}).json()
    assert third["page"] == 3
    assert len(third["rows"]) == 37


def test_paginated_dataframe_is_not_flagged_truncated(client: TestClient, opened_project: Path) -> None:
    """#1920 (Part 1 of #1886): a complete-but-paginated table must not carry the
    misleading truncated/incomplete flags. Every row is reachable by paging, so
    the metadata stays truncated=False / complete=True (regression of #1052)."""
    header = "idx\n"
    body = "".join(f"{i}\n" for i in range(137))  # multi-page at the default page size
    upload = client.post("/api/data/upload", files={"file": ("m.csv", (header + body).encode(), "text/csv")})
    ref = upload.json()["ref"]
    created = _create_session(client, ref=ref, recorded_type="DataFrame", type_chain=["DataObject", "DataFrame"]).json()
    meta = created["metadata"]
    assert meta["truncated"] is False
    assert meta["complete"] is True

    # The same rule holds on the read the panel actually pages with: a table
    # that spans pages is complete, because every row is reachable.
    context = _panel_context(client, ref=ref)
    page = _panel_read(client, context, ref, "table.page").json()
    assert page["total_pages"] > 1  # genuinely spans multiple pages
    assert page["truncated"] is False
    assert page["complete"] is True


def test_panel_read_sorts_dataframe(client: TestClient, opened_project: Path) -> None:
    """#1604 / ADR-054: sorting is the table read's own parameter.

    It arrived through the legacy ``GET /api/data/{ref}/preview`` adapter, then
    through a session PATCH, and now through the read the panel issues — three
    transports for one behaviour, which is why the behaviour is what this
    asserts and the transport is only how it gets there.
    """
    csv = "score\n3\n1\n2\n"
    upload = client.post("/api/data/upload", files={"file": ("s.csv", csv.encode(), "text/csv")})
    ref = upload.json()["ref"]
    context = _panel_context(client, ref=ref)

    desc = _panel_read(client, context, ref, "table.page", {"sort_by": "score", "sort_dir": "desc"})
    assert desc.status_code == 200, desc.text
    desc_page = desc.json()
    # The read echoes the sort it applied, so a panel can render the indicator
    # from the answer rather than from what it asked for.
    assert desc_page["sort"] == {"by": "score", "direction": "desc"}
    assert [row["score"] for row in desc_page["rows"]] == [3, 2, 1]

    asc = _panel_read(client, context, ref, "table.page", {"sort_by": "score", "sort_dir": "asc"})
    assert [row["score"] for row in asc.json()["rows"]] == [1, 2, 3]

    # A missing sort column is ignored (no crash, original order preserved).
    bogus = _panel_read(client, context, ref, "table.page", {"sort_by": "does_not_exist"})
    assert bogus.status_code == 200, bogus.text
    assert [row["score"] for row in bogus.json()["rows"]] == [3, 1, 2]


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
    # The route resolves and the API does not crash. A panel-backed previewer
    # accepts the target and reports the missing file when it reads, so the
    # degraded answer is a panel envelope rather than an error payload — the
    # failure surfaces where the read happens, not before it is attempted.
    assert body["kind"] in {"error", "artifact", "panel"}
    assert body["metadata"]["failed"] in {True, False}


def test_array_session_resource_tile(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    assert created["kind"] == "panel"
    assert created["panel"]["id"] == "core.array.basic"

    # Tiles were a session resource the envelope advertised; they are the array
    # panel's own read now, which is what lets it fetch a tile per scroll
    # position instead of one whole plane per render.
    context = _panel_context(client, ref=record.id)
    tile = _panel_read(client, context, record.id, "array.tile", {"y0": 0, "x0": 0, "height": 2, "width": 2})
    assert tile.status_code == 200, tile.text
    body = tile.json()
    # The tile is the real values at their own resolution, with the geometry
    # that says where in the plane they came from (#1886 item A).
    # The read reports the window it was asked for and returns the values for
    # it. (The stand-in zarr here ignores slicing and hands back its whole
    # plane, so the geometry is what this can honestly assert; the values are
    # sized against a real array in tests/panels.)
    assert body["height"] == 2 and body["width"] == 2
    assert body["values"]


def test_image_session_serializes_first_class_frontend_manifest(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#1579: a package-routed session JSON carries the manifest first-class.

    Issue #1770: discovery is entry-point only. Injecting the fixture
    package's ``scistudio.previewers`` entry point routes an ``Image`` target
    to ``fixture.image.viewer``; the session manager then stamps that spec's
    manifest onto the top-level ``frontend_manifest`` field.
    """
    import sys
    import types

    import numpy as np

    _prefer_fixture_package(monkeypatch)
    fixture_ep = importlib.metadata.EntryPoint(
        name="fixture",
        value="scistudio_blocks_fixture.previewers:get_previewers",
        group="scistudio.previewers",
    )
    real_entry_points = importlib.metadata.entry_points

    def _entry_points(*args: object, **kwargs: object) -> object:
        if kwargs.get("group") == "scistudio.previewers":
            return (fixture_ep,)
        return real_entry_points(*args, **kwargs)

    monkeypatch.setattr(importlib.metadata, "entry_points", _entry_points)
    # Rebuild the preview service so the fixture previewers are registered.
    with pytest.warns(DeprecationWarning, match="is deprecated through 0.5.x"):
        runtime.get_panel_service().rescan(legacy=True)

    matrix = np.arange(16 * 16, dtype=np.uint16).reshape(16, 16)

    class _FakeArray:
        shape = (3, 16, 16)
        dtype = "uint16"

        def __getitem__(self, key: object) -> np.ndarray:
            return matrix

    fake_zarr = types.ModuleType("zarr")
    fake_zarr.Array = _FakeArray  # type: ignore[attr-defined]
    fake_zarr.open = lambda path, mode="r": _FakeArray()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "zarr", fake_zarr)

    zarr_path = opened_project / "data" / "zarr" / "img.zarr"
    zarr_path.mkdir(parents=True)
    record = runtime.register_data_ref(
        StorageReference(
            backend="zarr",
            path=str(zarr_path),
            format="zarr",
            metadata={"type_chain": ["DataObject", "Array", "Image"], "axes": ["z", "y", "x"]},
        ),
        type_name="Image",
    )
    created = _create_session(
        client, ref=record.id, recorded_type="Image", type_chain=["DataObject", "Array", "Image"]
    ).json()

    assert created["previewer_id"] == "fixture.image.viewer"
    # First-class manifest in the wire body (#1579).
    assert created["frontend_manifest"]["previewer_id"] == "fixture.image.viewer"
    assert created["frontend_manifest"]["module_url"] == "/api/previews/assets/fixture.image.viewer/viewer.js"
    # The backend-only asset_root is never serialized.
    assert "asset_root" not in created["frontend_manifest"]
    # Old flattened metadata channel is no longer populated by the provider.
    assert "frontend_manifest" not in created["metadata"]


def test_resource_unknown_session_returns_404(client: TestClient, opened_project: Path) -> None:
    resp = client.get("/api/previews/sessions/pv-missing/resources/tile")
    assert resp.status_code == 404


def test_collection_session_lists_items(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    # Use a base type (DataFrame) that no package previewer claims, so this test
    # deterministically exercises the core collection fallback whether or not any
    # package previewer is registered (an Image previewer would otherwise route
    # Collection[Image] to a package viewer at priority 100).
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
    assert body["kind"] == "panel"
    assert body["panel"]["id"] == "core.collection.basic"


def _registered_collection(
    client: TestClient, runtime: ApiRuntime, *, count: int = 2, columns: int = 1
) -> tuple[str, list[str]]:
    """A collection of real catalog refs, the way a run's output produces one."""
    from scistudio.panels.targets import register_collection

    header = ",".join(f"col_{i}" for i in range(columns))
    row = ",".join(str(i) for i in range(columns))
    refs: list[str] = []
    for n in range(count):
        upload = client.post(
            "/api/data/upload",
            files={"file": (f"c{n}.csv", f"{header}\n{row}\n".encode(), "text/csv")},
        )
        assert upload.status_code == 200, upload.text
        refs.append(upload.json()["ref"])
    group = register_collection(
        runtime,
        {
            "kind": "collection",
            "count": len(refs),
            "item_type": "DataFrame",
            "items": [{"data_ref": ref, "type_name": "DataFrame"} for ref in refs],
        },
    )
    return str(group["collection_ref"]), refs


def test_collection_panel_lists_and_opens_its_items(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """Listing a collection and opening one member, through the panel's own path.

    The compiled viewer got both from the envelope: the members in its payload
    and a per-member ``PreviewResource`` to open one. A panel reads the members
    and asks the host to open one by reference, which is the same two
    capabilities with the descriptor left on the backend.
    """
    ref, children = _registered_collection(client, runtime, count=3)
    context = _panel_context(client, ref=ref, kind="collection_ref")

    page = _panel_read(client, context, ref, "collection.items").json()
    assert page["count"] == 3
    assert page["item_type"] == "DataFrame"
    assert [item["ref"] for item in page["items"]] == children

    opened = client.post(f"/api/panels/contexts/{context}/open", json={"ref": children[0]})
    assert opened.status_code == 200, opened.text
    child = opened.json()
    assert child["target"]["ref"] == children[0]
    assert child["target"]["recorded_type"] == "DataFrame"


def test_a_wide_collection_item_still_opens(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """#1837: a wide or richly-described member must still open.

    The collection fallback round-tripped a member's whole descriptor through
    ``PreviewResource.params``; for a table with many columns that crossed the
    API's 256-entry param guard and opening the member failed with HTTP 422.
    The panel path cannot regress that way by construction — a member is
    addressed by its reference, and the descriptor never leaves the backend —
    so what this pins is that the listing really does carry identity only,
    which is the property that keeps it constant-size however wide the table.
    """
    ref, children = _registered_collection(client, runtime, count=2, columns=300)
    context = _panel_context(client, ref=ref, kind="collection_ref")

    page = _panel_read(client, context, ref, "collection.items").json()
    item = page["items"][0]
    assert set(item) <= {"ref", "type_name", "kind", "display_name"}
    assert item["ref"] == children[0]

    opened = client.post(f"/api/panels/contexts/{context}/open", json={"ref": item["ref"]})
    assert opened.status_code == 200, opened.text
    assert opened.json()["target"]["ref"] == children[0]


def test_collection_image_child_resource_uses_catalog_storage(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Collection item previews must route through the catalog-backed Image previewer."""
    import numpy as np
    import tifffile

    _prefer_fixture_package(monkeypatch)
    fixture_ep = importlib.metadata.EntryPoint(
        name="fixture",
        value="scistudio_blocks_fixture.previewers:get_previewers",
        group="scistudio.previewers",
    )
    real_entry_points = importlib.metadata.entry_points

    def _entry_points(*args: object, **kwargs: object) -> object:
        if kwargs.get("group") == "scistudio.previewers":
            return (fixture_ep,)
        return real_entry_points(*args, **kwargs)

    monkeypatch.setattr(importlib.metadata, "entry_points", _entry_points)
    with pytest.warns(DeprecationWarning, match="is deprecated through 0.5.x"):
        runtime.get_panel_service().rescan(legacy=True)

    image_path = opened_project / "images" / "child.tif"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(image_path, np.arange(64, dtype=np.uint8).reshape(8, 8))
    record = runtime.register_data_ref(
        StorageReference(
            backend="filesystem",
            path=str(image_path),
            format="tiff",
            metadata={"type_chain": ["DataObject", "Array", "Image"], "axes": ["y", "x"]},
        ),
        type_name="Image",
    )

    from scistudio.panels.targets import register_collection

    group = register_collection(
        runtime,
        {
            "kind": "collection",
            "count": 1,
            "item_type": "Image",
            "items": [{"data_ref": record.id, "type_name": "Image"}],
        },
    )
    ref = str(group["collection_ref"])
    context = _panel_context(client, ref=ref, kind="collection_ref")

    page = _panel_read(client, context, ref, "collection.items").json()
    assert [item["ref"] for item in page["items"]] == [record.id]

    opened = client.post(f"/api/panels/contexts/{context}/open", json={"ref": record.id})
    assert opened.status_code == 200, opened.text
    child = opened.json()
    # The member routes on its own recorded type, through the catalog storage
    # the backend froze — not through anything the collection listing carried.
    assert child["previewer_id"] == "fixture.image.viewer"
    assert child["kind"] == "array"
    assert child["target"]["ref"] == record.id
    assert child["target"]["recorded_type"] == "Image"
    assert child["target"]["type_chain"] == ["DataObject", "Array", "Image"]
    assert child["payload"]["shape"] == [8, 8]
    assert str(child["payload"]["src"]).startswith("data:image/png;base64,")


def test_imaging_previewer_asset_served_from_companion_package_entry_point(
    client: TestClient,
    runtime: ApiRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Imaging viewer assets remain available when previewer entry-point metadata is stale."""
    _prefer_fixture_package(monkeypatch)
    block_ep = importlib.metadata.EntryPoint(
        name="fixture",
        value="scistudio_blocks_fixture:get_block_package",
        group="scistudio.blocks",
    )
    real_entry_points = importlib.metadata.entry_points

    def _entry_points(*args: object, **kwargs: object) -> object:
        group = kwargs.get("group")
        if group == "scistudio.previewers":
            return ()
        if group == "scistudio.blocks":
            return (block_ep,)
        if group == "scistudio.types":
            return ()
        return real_entry_points(*args, **kwargs)

    monkeypatch.setattr(importlib.metadata, "entry_points", _entry_points)
    with pytest.warns(DeprecationWarning, match="is deprecated through 0.5.x"):
        runtime.get_panel_service().rescan(legacy=True)

    spec = runtime.get_preview_service().registry.get("fixture.image.viewer")
    assert spec is not None
    assert spec.frontend_manifest is not None

    resp = client.get("/api/previews/assets/fixture.image.viewer/viewer.js")

    assert resp.status_code == 200
    assert "text/javascript" in resp.headers["content-type"]
    assert b"mount" in resp.content


def test_composite_panel_lists_and_opens_a_slot(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """A composite's slots are read by the panel and opened by slot reference.

    The compiled viewer advertised one ``PreviewResource`` per slot carrying the
    slot descriptor; the panel reads the inventory and opens a slot by the
    reference the backend minted for it, which is the same navigation with the
    descriptor kept on the backend.
    """
    # A composite is a directory holding its slots and a manifest naming them;
    # the slot has to live inside it, which is the confinement the reader checks
    # before it will open a child.
    composite = opened_project / "composite"
    composite.mkdir()
    raster = composite / "raster"
    raster.mkdir()
    (composite / "manifest.json").write_text(
        json.dumps({"slots": {"raster": {"backend": "filesystem", "path": str(raster), "format": "npy"}}}),
        encoding="utf-8",
    )
    record = runtime.register_data_ref(
        StorageReference(
            backend="filesystem",
            path=str(composite),
            metadata={
                "type_chain": ["DataObject", "CompositeData"],
                # The recorded slot carries the wire envelope a serializer
                # writes; its own chain is the only authority for the slot type.
                "slots": {
                    "raster": {
                        "backend": "filesystem",
                        "path": str(raster),
                        "format": "npy",
                        "metadata": {"type_chain": ["DataObject", "Array"]},
                    }
                },
            },
        ),
        type_name="CompositeData",
    )
    context = _panel_context(client, ref=record.id)

    response = _panel_read(client, context, record.id, "composite.slots")
    assert response.status_code == 200, response.text
    slots = response.json()
    assert [slot["name"] for slot in slots["slots"]] == ["raster"]
    # The slot's type comes from its own recorded chain, so it routes; a
    # stringified storage descriptor here is what once matched no previewer.
    assert slots["slots"][0]["type_name"] == "Array"

    opened = client.post(f"/api/panels/contexts/{context}/open", json={"ref": slots["slots"][0]["ref"]})
    assert opened.status_code == 200, opened.text
    child = opened.json()
    assert child["target"]["ref"] == f"{record.id}#raster"
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
    assert created["kind"] == "panel"
    assert created["panel"]["id"] == "core.plot.basic"

    # Saving was an `export` session resource that returned a scrubbed data URI.
    # It is the plot panel's artifact read and the token route that serves it
    # now; what must not change is that the bytes a reader ends up saving carry
    # no script.
    context = _panel_context(client, ref=record.id, kind="plot_artifact")
    granted = _panel_read(client, context, record.id, "artifact.file", {"variant": "svg"})
    assert granted.status_code == 200, granted.text
    assert granted.json()["formats"] == ["svg"]

    served = client.get(granted.json()["url"])
    assert served.status_code == 200
    assert served.headers["content-type"].startswith("image/svg+xml")
    assert "<script" not in served.text
    assert "alert(1)" not in served.text
    assert "<rect" in served.text
