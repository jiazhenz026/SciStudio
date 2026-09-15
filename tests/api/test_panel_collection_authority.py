"""Collection groups and type ancestry come from backend output registration."""

from __future__ import annotations

from dataclasses import replace

import pytest

from scistudio.panels.registry import PanelRegistry
from scistudio.panels.targets import PanelError, collection_store, freeze_target, register_collection
from tests.panels.conftest import make_runtime


def test_collection_snapshot_ignores_client_group_and_survives_new_outputs(tmp_path):
    runtime, store = make_runtime(tmp_path)
    service = runtime.get_preview_service()
    panels = PanelRegistry()
    panels.register(replace(service.registry.panels.get("lab.text"), types=("Text", "Collection[Text]")))
    service.registry.install_panels(panels)
    old = register_collection(
        runtime,
        {
            "kind": "collection",
            "count": 2,
            "item_type": "Text",
            "items": [{"data_ref": "data-a"}, {"data_ref": "data-a"}],
        },
    )
    for _i in range(1030):
        register_collection(runtime, {"kind": "collection", "count": 0, "item_type": "Text", "items": []})
    ctx = store.create(
        {
            "kind": "preview",
            "target": {"ref": old["collection_ref"]},
            "query": {"_collection_items": [{"data_ref": "evil"}]},
        }
    )
    assert len(ctx.input["items"]) == 2
    assert ctx.input["items"][0]["ref"] == "data-a"
    assert store.authorize(ctx, "data-a").target.recorded_type == "Text"
    with pytest.raises(PanelError):
        store.authorize(ctx, "evil")
    assert store.get(ctx.context_id) is ctx
    runtime.data_catalog = {}
    assert not collection_store(runtime)
    with pytest.raises(PanelError):
        store.get(ctx.context_id)


def test_collection_ancestry_and_empty_snapshot(tmp_path):
    runtime, store = make_runtime(tmp_path)
    collection = register_collection(runtime, {"kind": "collection", "count": 0, "item_type": "Image", "items": []})
    frozen = freeze_target(runtime, collection["collection_ref"])
    assert frozen.target.type_chain == ("DataObject", "Array", "Image")
    panels = PanelRegistry()
    panels.register(
        replace(runtime.get_preview_service().registry.panels.get("lab.text"), types=("Collection[Array]",))
    )
    runtime.get_preview_service().registry.install_panels(panels)
    ctx = store.create({"kind": "preview", "target": {"ref": collection["collection_ref"]}})
    assert ctx.input["count"] == 0 and ctx.input["items"] == []


def test_registration_preserves_single_item_normalization(tmp_path):
    from scistudio.api.runtime._data import register_output_payload

    runtime, _store = make_runtime(tmp_path)
    runtime.register_output_payload = lambda payload: register_output_payload(runtime, payload)
    scalar = {"text": "already serialized payload"}
    assert register_output_payload(runtime, {"_collection": True, "items": [scalar]}) == scalar
    group = register_output_payload(runtime, {"_collection": True, "item_type": "Text", "items": []})
    assert group["collection_ref"] in collection_store(runtime)
