"""ADR-051: unit tests for the interaction capability contract module.

Covers :class:`PanelManifest` (wire shape; ``asset_root`` never serialized),
:class:`InteractivePrompt`, :func:`coerce_prompt`, the storage-reference
serialization helpers, and :func:`load_intermediate`.
"""

from __future__ import annotations

import pytest

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.interactive import (
    INTERACTIVE_INTERMEDIATE_KEY,
    PANEL_API_VERSION,
    InteractiveMixin,
    InteractivePrompt,
    PanelManifest,
    SupportsInteraction,
    coerce_prompt,
    deserialise_storage_ref,
    load_intermediate,
    serialise_storage_ref,
)
from scistudio.core.storage.ref import StorageReference


class TestPanelManifest:
    def test_to_dict_wire_shape(self) -> None:
        m = PanelManifest(panel_id="core.interactive.data_router", module_url="/api/x/y.js", version="2")
        wire = m.to_dict()
        assert wire == {
            "panel_id": "core.interactive.data_router",
            "module_url": "/api/x/y.js",
            "export_name": "default",
            "css": [],
            "version": "2",
            "api_version": PANEL_API_VERSION,
        }

    def test_asset_root_never_serialized(self) -> None:
        m = PanelManifest(panel_id="p", asset_root="/secret/filesystem/path")
        assert "asset_root" not in m.to_dict()

    def test_response_schema_included_when_set(self) -> None:
        m = PanelManifest(panel_id="p", response_schema={"type": "object"})
        assert m.to_dict()["response_schema"] == {"type": "object"}

    def test_core_panel_defaults_module_url_empty(self) -> None:
        m = PanelManifest(panel_id="core.interactive.pair_editor")
        assert m.module_url == ""


class TestInteractivePrompt:
    def test_defaults_no_intermediate(self) -> None:
        p = InteractivePrompt(panel_payload={"a": 1})
        assert p.panel_payload == {"a": 1}
        assert p.intermediate == ()

    def test_coerce_passthrough(self) -> None:
        p = InteractivePrompt(panel_payload={"a": 1})
        assert coerce_prompt(p) is p

    def test_coerce_dict_wraps_as_payload(self) -> None:
        p = coerce_prompt({"options": [1, 2]})
        assert isinstance(p, InteractivePrompt)
        assert p.panel_payload == {"options": [1, 2]}
        assert p.intermediate == ()

    def test_coerce_rejects_other(self) -> None:
        with pytest.raises(TypeError):
            coerce_prompt(["not", "a", "dict"])  # type: ignore[arg-type]


class TestStorageRefSerialization:
    def test_round_trip(self) -> None:
        ref = StorageReference(backend="zarr", path="a/b/c", format="parquet", metadata={"k": "v"})
        data = serialise_storage_ref(ref)
        assert data == {"backend": "zarr", "path": "a/b/c", "format": "parquet", "metadata": {"k": "v"}}
        back = deserialise_storage_ref(data)
        assert back.backend == "zarr"
        assert back.path == "a/b/c"
        assert back.format == "parquet"
        assert back.metadata == {"k": "v"}


class TestLoadIntermediate:
    def test_empty_returns_empty_tuple(self) -> None:
        assert load_intermediate({}) == ()
        assert load_intermediate(BlockConfig()) == ()

    def test_loads_dicts_and_refs(self) -> None:
        ref_dict = {"backend": "zarr", "path": "p", "format": None, "metadata": None}
        live = StorageReference(backend="arrow", path="q")
        config = {INTERACTIVE_INTERMEDIATE_KEY: [ref_dict, live]}
        refs = load_intermediate(config)
        assert len(refs) == 2
        assert all(isinstance(r, StorageReference) for r in refs)
        assert refs[0].backend == "zarr"
        assert refs[1].backend == "arrow"


class TestSupportsInteractionProtocol:
    def test_mixin_default_prepare_prompt_raises(self) -> None:
        class _Stub(InteractiveMixin):
            interactive_panel = PanelManifest(panel_id="p")

        with pytest.raises(NotImplementedError):
            _Stub().prepare_prompt({}, BlockConfig())

    def test_runtime_checkable_protocol(self) -> None:
        class _Good:
            interactive_panel = PanelManifest(panel_id="p")

            def prepare_prompt(self, inputs: object, config: object) -> object:
                return InteractivePrompt(panel_payload={})

        assert isinstance(_Good(), SupportsInteraction)
