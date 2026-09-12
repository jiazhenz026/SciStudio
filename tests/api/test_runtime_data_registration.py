"""Catalog registration for outputs the run never persisted.

An output that was written to storage serialises with a backend and a path. An
output that was not — an :class:`~scistudio.core.types.Artifact` is the ordinary
case, being a pointer to a file the run only read — serialises with all three
storage fields present but null, and names its file in its own ``file_path``.

Registration used to stringify that null, so every such output entered the
catalog under a path literally called ``"None"``. The compiled viewer showed
that path with a size of zero; the panel freshness stamp, which stats the file,
reported ``stale_context`` — "The panel's data is no longer available" — for
data that had never moved. Both readings were wrong, and neither pointed at the
registration that produced them.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from scistudio.api.runtime._data import describe_ref, register_data_ref, register_output_payload
from scistudio.previewers.models import PreviewTarget


def make_runtime(project_root):
    """A runtime carrying only what registration and freezing actually touch."""
    runtime = SimpleNamespace(
        active_project=SimpleNamespace(id="p", path=str(project_root)),
        data_catalog={},
        type_registry=SimpleNamespace(resolve=lambda name: SimpleNamespace(base_type="")),
    )
    runtime.describe_ref = lambda ref: describe_ref(runtime, ref)
    runtime.register_data_ref = lambda ref, **kwargs: register_data_ref(runtime, ref, **kwargs)
    runtime.get_data_record = lambda ref: runtime.data_catalog[ref]
    runtime.resolve_session_target = lambda target: PreviewTarget(
        kind=target.kind,
        ref=target.ref,
        recorded_type=runtime.data_catalog[target.ref].type_name,
        type_chain=tuple(runtime.data_catalog[target.ref].type_chain),
    )
    return runtime


def artifact_payload(file_path: str):
    """The wire envelope a loaded artifact really produces (observed in a run)."""
    return {
        "backend": None,
        "path": None,
        "format": None,
        "metadata": {
            "type_chain": ["DataObject", "Artifact"],
            "framework": {"object_id": "abc", "source": file_path},
            "meta": None,
            "user": {},
            "file_path": file_path,
            "mime_type": None,
            "description": file_path.rsplit("/", 1)[-1],
        },
    }


@pytest.fixture
def project(tmp_path):
    (tmp_path / "test_inputs").mkdir()
    (tmp_path / "test_inputs" / "figure.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 40)
    return tmp_path


def test_unpersisted_artifact_registers_the_file_it_names(project):
    runtime = make_runtime(project)
    descriptor = register_output_payload(runtime, artifact_payload("test_inputs/figure.png"))

    record = runtime.data_catalog[descriptor["data_ref"]]
    # The path is the file, resolved against the project root — never the
    # string "None", which is what a stringified null used to produce.
    assert record.ref.path == str(project / "test_inputs" / "figure.png")
    assert record.ref.path != "None"
    assert record.ref.backend == "filesystem"
    assert record.type_name == "Artifact"
    # describe_ref can stat it, so the recorded size is the real one.
    assert record.metadata["exists"] is True
    assert record.metadata["size_bytes"] == 48
    # The name the reader sees still resolves.
    assert descriptor["display_name"] == "figure.png"


def test_an_absolute_named_file_is_taken_as_it_stands(project):
    runtime = make_runtime(project)
    absolute = str(project / "test_inputs" / "figure.png")
    descriptor = register_output_payload(runtime, artifact_payload(absolute))

    assert runtime.data_catalog[descriptor["data_ref"]].ref.path == absolute


def test_an_output_naming_no_file_is_not_registered_at_all(project):
    """A value with nowhere to read from must not enter the catalog.

    Registering it anyway is what created the phantom entry: a catalog record
    whose every read failed, indistinguishable from data the user had deleted.
    """
    runtime = make_runtime(project)
    payload = {"backend": None, "path": None, "format": None, "metadata": {"type_chain": ["DataObject", "Text"]}}

    assert register_output_payload(runtime, payload) == payload
    assert runtime.data_catalog == {}


def test_a_persisted_output_is_registered_unchanged(project):
    runtime = make_runtime(project)
    stored = project / "table.parquet"
    stored.write_bytes(b"not really parquet")
    descriptor = register_output_payload(
        runtime,
        {
            "backend": "filesystem",
            "path": str(stored),
            "format": "parquet",
            "metadata": {"type_chain": ["DataObject", "DataFrame"]},
        },
    )

    record = runtime.data_catalog[descriptor["data_ref"]]
    assert record.ref.backend == "filesystem"
    assert record.ref.path == str(stored)
    assert record.type_name == "DataFrame"


def test_a_real_path_with_no_backend_is_filesystem_not_the_word_none(project):
    runtime = make_runtime(project)
    stored = project / "table.parquet"
    stored.write_bytes(b"x")
    descriptor = register_output_payload(
        runtime,
        {"backend": None, "path": str(stored), "format": None, "metadata": {"type_chain": ["DataObject", "DataFrame"]}},
    )

    assert runtime.data_catalog[descriptor["data_ref"]].ref.backend == "filesystem"


def test_a_registered_artifact_can_be_frozen_for_a_panel(project):
    """The regression itself: freezing stats the file, and it has to be there."""
    from scistudio.panels.targets import freeze_target

    runtime = make_runtime(project)
    descriptor = register_output_payload(runtime, artifact_payload("test_inputs/figure.png"))

    frozen = freeze_target(runtime, descriptor["data_ref"])
    assert frozen.storage is not None
    assert frozen.stamp is not None
    # And it stays valid, which is what the panel re-checks on every read.
    frozen.validate(runtime)


def test_a_collection_of_artifacts_freezes_every_member(project):
    """A collection failed as a whole because each member failed individually."""
    from scistudio.panels.targets import child_targets, freeze_target

    (project / "test_inputs" / "photo.jpg").write_bytes(b"\xff\xd8\xff" + b"1" * 20)
    runtime = make_runtime(project)
    runtime.register_output_payload = lambda payload: register_output_payload(runtime, payload)
    collection = register_output_payload(
        runtime,
        {
            "_collection": True,
            "item_type": "Artifact",
            "items": [artifact_payload("test_inputs/figure.png"), artifact_payload("test_inputs/photo.jpg")],
        },
    )

    parent = freeze_target(runtime, collection["collection_ref"])
    from scistudio.panels.contexts import read_access

    page = child_targets(runtime, parent, read_access())
    assert [item["display_name"] for item in page["items"]] == ["figure.png", "photo.jpg"]
    for item in page["items"]:
        parent.children[item["ref"]].validate(runtime)
