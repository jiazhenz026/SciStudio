"""Tests for the open-as type choice (#2112, ADR-048 FR-041 .. FR-043).

Several registered types can load the same extension, so the Data tree asks
which one a file opens as instead of guessing, and can remember the answer per
extension for the open project.

The ambiguity these tests rely on is core-only — ``.parquet`` is loadable as
``Array``, ``Artifact``, and ``DataFrame`` with nothing installed — so they
assert the same thing on a machine with plugins as on a bare CI runner.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient

from scistudio.api.routes.data import _open_as_candidates
from scistudio.api.runtime._data import _type_chain_from_registry
from scistudio.api.runtime._preview_image import _infer_type_name_from_ref
from scistudio.core.storage.ref import StorageReference
from scistudio.panels.open_as import (
    clear_open_as,
    normalize_extension,
    open_as_path,
    read_open_as,
    write_open_as,
)


def _write_parquet(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table({"a": [1, 2], "b": ["x", "y"]}), path)


# ---------------------------------------------------------------------------
# The remembered-choice store (FR-043)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("tif", ".tif"), (".TIF", ".tif"), ("  .Tiff ", ".tiff"), ("", ""), (".", "")],
)
def test_normalize_extension_gives_one_shape(raw: str, expected: str) -> None:
    """A suffix, a format id, and a typed query string normalize to one key."""
    assert normalize_extension(raw) == expected


def test_write_read_and_clear_roundtrip(tmp_path: Path) -> None:
    write_open_as(tmp_path, ".tif", "Image")
    write_open_as(tmp_path, "csv", "DataFrame")
    assert read_open_as(tmp_path) == {".tif": "Image", ".csv": "DataFrame"}

    # Clearing one leaves the other: the file is read before it is rewritten.
    clear_open_as(tmp_path, ".tif")
    assert read_open_as(tmp_path) == {".csv": "DataFrame"}

    # Clearing what was never chosen is not an error — the intent already holds.
    clear_open_as(tmp_path, ".nope")
    assert read_open_as(tmp_path) == {".csv": "DataFrame"}


def test_missing_file_is_an_empty_map(tmp_path: Path) -> None:
    assert read_open_as(tmp_path) == {}


@pytest.mark.parametrize(
    "payload",
    ['{"open_as": [1, 2]}', '["not", "an", "object"]', "{not json at all", '{"open_as": {"x": 5}}'],
)
def test_malformed_files_are_skipped_not_raised(tmp_path: Path, payload: str) -> None:
    """FR-043/FR-038: a lost preference must never stop a file from opening."""
    path = open_as_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    assert read_open_as(tmp_path) == {}


def test_one_bad_entry_does_not_cost_the_others(tmp_path: Path) -> None:
    path = open_as_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": 1, "open_as": {".tif": "Image", ".bad": 7, "": "X"}}),
        encoding="utf-8",
    )
    assert read_open_as(tmp_path) == {".tif": "Image"}


# ---------------------------------------------------------------------------
# Candidate ordering (FR-042)
# ---------------------------------------------------------------------------


class _FakeCapability:
    def __init__(self, data_type: type) -> None:
        self.data_type = data_type


class _FakeSpec:
    def __init__(self, base_type: str, description: str = "") -> None:
        self.base_type = base_type
        self.description = description
        self.file_path = ""
        self.module_path = ""
        self.is_dropin = False


class _FakeRuntime:
    """The two registries ``_open_as_candidates`` reads, and nothing else."""

    def __init__(self, capabilities: list[Any], specs: dict[str, Any]) -> None:
        self.block_registry = self
        self.type_registry = self
        self._capabilities = capabilities
        self._specs = specs

    def list_format_capabilities(self, **_kwargs: Any) -> list[Any]:
        return self._capabilities

    def all_specs(self) -> dict[str, Any]:
        return {}

    def resolve(self, name: str) -> Any:
        return self._specs[name]


def test_candidates_are_ordered_specific_tier_first(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-042: project -> package -> core, so the default is the most specific."""

    class ProjectType: ...

    class PackageType: ...

    class CoreType: ...

    ProjectType.__name__ = "ProjectType"
    PackageType.__name__ = "PackageType"
    CoreType.__name__ = "CoreType"

    runtime = _FakeRuntime(
        capabilities=[_FakeCapability(CoreType), _FakeCapability(ProjectType), _FakeCapability(PackageType)],
        specs={
            "ProjectType": _FakeSpec("CoreType"),
            "PackageType": _FakeSpec("CoreType"),
            "CoreType": _FakeSpec(""),
            "Artifact": _FakeSpec("DataObject"),
        },
    )
    origins = {"ProjectType": "project", "PackageType": "package", "CoreType": "core", "Artifact": "core"}
    monkeypatch.setattr(
        "scistudio.api.routes.data._type_origin",
        lambda spec, project_dir: origins[next(name for name, s in runtime._specs.items() if s is spec)],
    )

    project = type("P", (), {"path": str(tmp_path)})()
    names = [candidate.name for candidate in _open_as_candidates(runtime, project, ".x")]
    assert names[0] == "ProjectType"
    assert names.index("PackageType") < names.index("CoreType")


def test_artifact_is_always_offered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-042: "open it as a plain file" is always a real answer."""

    class Only: ...

    Only.__name__ = "Only"
    runtime = _FakeRuntime(
        capabilities=[_FakeCapability(Only)],
        specs={"Only": _FakeSpec("DataObject"), "Artifact": _FakeSpec("DataObject")},
    )
    monkeypatch.setattr("scistudio.api.routes.data._type_origin", lambda spec, project_dir: "core")
    project = type("P", (), {"path": str(tmp_path)})()

    candidates = {c.name: c for c in _open_as_candidates(runtime, project, ".only")}
    assert set(candidates) == {"Only", "Artifact"}
    # The fallback says so, rather than claiming a loader it does not have.
    assert candidates["Artifact"].loadable is False
    assert candidates["Only"].loadable is True


# ---------------------------------------------------------------------------
# Type chain derivation (FR-041)
# ---------------------------------------------------------------------------


def test_type_chain_walks_recorded_base_types() -> None:
    registry = _FakeRuntime(
        capabilities=[],
        specs={
            "SRSImage": _FakeSpec("Image"),
            "Image": _FakeSpec("Array"),
            "Array": _FakeSpec("DataObject"),
            "DataObject": _FakeSpec(""),
        },
    )
    assert _type_chain_from_registry(registry, "SRSImage") == ["DataObject", "Array", "Image", "SRSImage"]


def test_type_chain_of_an_unknown_type_is_the_type_itself() -> None:
    registry = _FakeRuntime(capabilities=[], specs={})
    assert _type_chain_from_registry(registry, "Ghost") == ["Ghost"]
    assert _type_chain_from_registry(None, "Ghost") == ["Ghost"]


def test_type_chain_survives_a_cycle() -> None:
    """A malformed drop-in spec must not be able to hang a registration."""
    registry = _FakeRuntime(capabilities=[], specs={"A": _FakeSpec("B"), "B": _FakeSpec("A")})
    assert _type_chain_from_registry(registry, "A") == ["B", "A"]


# ---------------------------------------------------------------------------
# Extension inference against the capability table
# ---------------------------------------------------------------------------


def test_inference_adopts_an_unambiguous_installed_type() -> None:
    """A single non-Artifact claimant for the extension wins the record."""

    class Image: ...

    Image.__name__ = "Image"
    registry = _FakeRuntime(capabilities=[_FakeCapability(Image)], specs={})
    ref = StorageReference(backend="filesystem", path="/x/y.tif", format="tif")
    assert _infer_type_name_from_ref(ref, registry) == "Image"
    # Without a registry the heuristic answer is unchanged.
    assert _infer_type_name_from_ref(ref) == "Artifact"


def test_inference_declines_an_ambiguous_extension() -> None:
    """Guessing between claimants would make the record depend on install order."""

    class Image: ...

    class SRSImage: ...

    Image.__name__ = "Image"
    SRSImage.__name__ = "SRSImage"
    registry = _FakeRuntime(
        capabilities=[_FakeCapability(Image), _FakeCapability(SRSImage)],
        specs={},
    )
    ref = StorageReference(backend="filesystem", path="/x/y.tif", format="tif")
    assert _infer_type_name_from_ref(ref, registry) == "Artifact"


def test_inference_keeps_core_formats_fixed() -> None:
    """A package cannot silently retype ``.csv`` out from under the heuristic."""

    class LCMSFeatureTable: ...

    LCMSFeatureTable.__name__ = "LCMSFeatureTable"
    registry = _FakeRuntime(capabilities=[_FakeCapability(LCMSFeatureTable)], specs={})
    ref = StorageReference(backend="filesystem", path="/x/y.csv", format="csv")
    assert _infer_type_name_from_ref(ref, registry) == "DataFrame"


# ---------------------------------------------------------------------------
# The endpoints
# ---------------------------------------------------------------------------


def test_candidates_lists_every_type_that_can_load_the_extension(client: TestClient, opened_project: Path) -> None:
    _write_parquet(opened_project / "data" / "table.parquet")

    resp = client.get("/api/data/open-as/candidates", params={"path": "data/table.parquet"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["extension"] == ".parquet"
    assert body["remembered"] is None
    names = {c["name"] for c in body["candidates"]}
    assert {"Array", "Artifact", "DataFrame"} <= names


def test_candidates_rejects_a_path_outside_the_project(client: TestClient, opened_project: Path) -> None:
    outside = opened_project.parent / "secret.txt"
    outside.write_text("nope", encoding="utf-8")
    resp = client.get("/api/data/open-as/candidates", params={"path": str(outside)})
    assert resp.status_code == 403


def test_candidates_missing_file_404(client: TestClient, opened_project: Path) -> None:
    resp = client.get("/api/data/open-as/candidates", params={"path": "data/missing.parquet"})
    assert resp.status_code == 404


def test_explicit_type_name_overrides_the_inferred_one(client: TestClient, opened_project: Path) -> None:
    _write_parquet(opened_project / "data" / "table.parquet")

    resp = client.post(
        "/api/data/register-path",
        json={"path": "data/table.parquet", "type_name": "Array"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["recorded_type"] == "Array"
    assert body["type_chain"] == ["DataObject", "Array"]
    # Not remembered: the caller did not ask for it.
    assert body["remembered"] is False
    assert client.get("/api/data/open-as").json()["entries"] == []


def test_a_type_that_cannot_open_the_extension_is_rejected(client: TestClient, opened_project: Path) -> None:
    _write_parquet(opened_project / "data" / "table.parquet")

    resp = client.post(
        "/api/data/register-path",
        json={"path": "data/table.parquet", "type_name": "Text"},
    )
    assert resp.status_code == 400
    assert "cannot open" in resp.json()["detail"]


def test_remembered_choice_applies_without_asking_again(client: TestClient, opened_project: Path) -> None:
    _write_parquet(opened_project / "data" / "first.parquet")
    _write_parquet(opened_project / "data" / "second.parquet")

    remembered = client.post(
        "/api/data/register-path",
        json={"path": "data/first.parquet", "type_name": "Array", "remember": True},
    )
    assert remembered.status_code == 200, remembered.text
    assert remembered.json()["remembered"] is True
    assert client.get("/api/data/open-as").json()["entries"] == [
        {"extension": ".parquet", "type_name": "Array", "available": True}
    ]

    # A different file with the same extension, and no explicit type: the
    # remembered choice wins over the extension heuristic (which says DataFrame).
    again = client.post("/api/data/register-path", json={"path": "data/second.parquet"})
    assert again.status_code == 200, again.text
    assert again.json()["recorded_type"] == "Array"

    # Candidates now report the choice, so the caller knows not to ask.
    candidates = client.get("/api/data/open-as/candidates", params={"path": "data/second.parquet"})
    assert candidates.json()["remembered"] == "Array"


def test_clearing_a_choice_returns_to_inference(client: TestClient, opened_project: Path) -> None:
    _write_parquet(opened_project / "data" / "table.parquet")
    client.post(
        "/api/data/register-path",
        json={"path": "data/table.parquet", "type_name": "Array", "remember": True},
    )

    cleared = client.delete("/api/data/open-as/.parquet")
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["entries"] == []

    resp = client.post("/api/data/register-path", json={"path": "data/table.parquet"})
    assert resp.json()["recorded_type"] == "DataFrame"


def test_clearing_an_unchosen_extension_succeeds(client: TestClient, opened_project: Path) -> None:
    resp = client.delete("/api/data/open-as/.never")
    assert resp.status_code == 200
    assert resp.json()["entries"] == []
