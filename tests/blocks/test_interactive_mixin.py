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
    INTERACTIVE_MEMORY_KEY,
    PANEL_API_VERSION,
    InteractiveMixin,
    InteractivePrompt,
    PanelManifest,
    SupportsInteraction,
    coerce_prompt,
    deserialise_storage_ref,
    interactive_input_signature,
    interactive_item_label,
    load_interactive_memory,
    load_intermediate,
    serialise_storage_ref,
)
from scistudio.core.storage.ref import StorageReference
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection


class TestInteractiveItemLabel:
    """:func:`interactive_item_label` — duck-typed best-effort item naming."""

    def test_prefers_explicit_name(self) -> None:
        class Item:
            name = "explicit.tif"

        assert interactive_item_label(Item(), 3) == "explicit.tif"

    def test_source_file_basename(self) -> None:
        class Meta:
            source_file = "/data/raw/io-coverage/spectrum_07.txt"

        class Item:
            meta = Meta()

        assert interactive_item_label(Item(), 2) == "spectrum_07.txt"

    def test_source_file_windows_separator(self) -> None:
        class Meta:
            source_file = r"C:\data\images\img_03.tif"

        class Item:
            meta = Meta()

        assert interactive_item_label(Item(), 0) == "img_03.tif"

    def test_artifact_file_path_basename(self) -> None:
        from pathlib import Path

        class Item:
            meta = None
            file_path = Path("/tmp/exports/report.pdf")

        assert interactive_item_label(Item(), 1) == "report.pdf"

    def test_empty_name_falls_through_to_source_file(self) -> None:
        class Meta:
            source_file = "/d/a.txt"

        class Item:
            name = ""
            meta = Meta()

        assert interactive_item_label(Item(), 0) == "a.txt"

    def test_fallback_to_index_when_nothing_identifying(self) -> None:
        assert interactive_item_label(object(), 9) == "item_9"


class _SourceMeta:
    def __init__(self, source_file: str) -> None:
        self.source_file = source_file


class _FileItem(DataObject):
    """DataObject stub whose meta carries a source filename."""

    def __init__(self, source_file: str) -> None:
        super().__init__()
        self._m = _SourceMeta(source_file)

    @property
    def meta(self) -> _SourceMeta:  # type: ignore[override]
        return self._m


class TestInteractiveInputSignature:
    """:func:`interactive_input_signature` — generic identity fingerprint."""

    def test_signature_is_per_port_filename_lists(self) -> None:
        col = Collection([_FileItem("/d/a.txt"), _FileItem("/d/b.txt")], item_type=_FileItem)
        sig = interactive_input_signature({"input_1": col})
        assert sig == {"input_1": ["a.txt", "b.txt"]}

    def test_signature_handles_multiple_ports_and_singletons(self) -> None:
        col = Collection([_FileItem("/d/a.txt")], item_type=_FileItem)
        sig = interactive_input_signature({"input_1": col, "input_2": _FileItem("/d/solo.txt")})
        assert sig == {"input_1": ["a.txt"], "input_2": ["solo.txt"]}

    def test_signature_order_sensitive(self) -> None:
        c1 = Collection([_FileItem("/d/a.txt"), _FileItem("/d/b.txt")], item_type=_FileItem)
        c2 = Collection([_FileItem("/d/b.txt"), _FileItem("/d/a.txt")], item_type=_FileItem)
        assert interactive_input_signature({"p": c1}) != interactive_input_signature({"p": c2})


class TestLoadInteractiveMemory:
    """:func:`load_interactive_memory` — enabled-record extraction."""

    def test_reads_top_level_record(self) -> None:
        rec = {"enabled": True, "decision": {"x": 1}, "signature": {"p": ["a"]}}
        assert load_interactive_memory({INTERACTIVE_MEMORY_KEY: rec}) == rec

    def test_reads_params_nested_record(self) -> None:
        rec = {"enabled": True, "decision": {}, "signature": {}}
        assert load_interactive_memory({"params": {INTERACTIVE_MEMORY_KEY: rec}}) == rec

    def test_disabled_returns_none(self) -> None:
        assert load_interactive_memory({INTERACTIVE_MEMORY_KEY: {"enabled": False}}) is None

    def test_absent_returns_none(self) -> None:
        assert load_interactive_memory({"params": {}}) is None
        assert load_interactive_memory({}) is None


class TestRemapSavedDecisionDefault:
    """Default :meth:`InteractiveMixin.remap_saved_decision` — exact-match replay."""

    class _Block(InteractiveMixin):
        interactive_panel = PanelManifest(panel_id="core.interactive.test")

    def test_replays_on_identical_signature(self) -> None:
        block = self._Block()
        decision = {"assignments": {"port_1": ["input_1:0"]}}
        sig = {"input_1": ["a.txt"]}
        assert block.remap_saved_decision(decision, sig, sig) == decision

    def test_falls_back_when_signature_differs(self) -> None:
        block = self._Block()
        decision = {"assignments": {"port_1": ["input_1:0"]}}
        assert block.remap_saved_decision(decision, {"input_1": ["a.txt"]}, {"input_1": ["b.txt"]}) is None


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
