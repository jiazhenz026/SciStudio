"""Tests for :mod:`scistudio.engine.materialisation`.

Covers the test plan from ``docs/planning/phase-minus-1-bugfix-plan.md``
§3 (issue #1078):

- Round-trip DataFrame and Array through materialise → reconstruct.
- ``reconstruct_from_file`` falls back to :class:`Artifact` for
  ``target_type=Artifact`` and an unknown extension.
- ``reconstruct_from_file`` raises :class:`LookupError` for a
  concrete target type without a matching loader.
- Pass-through path: ``mount_pathlike`` is invoked when the source
  file already matches the target extension.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import patch

import numpy as np
import pyarrow as pa
import pytest

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.io.io_block import IOBlock
from scistudio.blocks.io.loaders.load_data import LoadData
from scistudio.blocks.io.savers.save_data import SaveData
from scistudio.blocks.registry import BlockRegistry, _spec_from_class
from scistudio.core.storage.ref import StorageReference
from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.text import Text
from scistudio.engine.materialisation import (
    materialise_to_file,
    reconstruct_from_file,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_registry(*classes: type) -> BlockRegistry:
    """Build an isolated :class:`BlockRegistry` with *classes* pre-registered."""
    reg = BlockRegistry()
    for cls in classes:
        reg._register_spec(_spec_from_class(cls, source="test"))
    return reg


def _registry_with_core_io() -> BlockRegistry:
    """Registry containing the real :class:`LoadData` and :class:`SaveData`."""
    return _build_registry(LoadData, SaveData)


# ---------------------------------------------------------------------------
# Round-trip tests
# ---------------------------------------------------------------------------


def test_round_trip_dataframe(tmp_path: Path) -> None:
    """materialise → reconstruct round-trips a DataFrame through CSV."""
    table = pa.table({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    df = DataFrame(columns=["a", "b"], row_count=3)
    df._arrow_table = table  # type: ignore[attr-defined]

    reg = _registry_with_core_io()
    out_path = materialise_to_file(df, tmp_path, extension=".csv", registry=reg)
    assert out_path.exists()
    assert out_path.suffix == ".csv"

    restored = reconstruct_from_file(out_path, DataFrame, registry=reg)
    assert isinstance(restored, DataFrame)
    assert sorted(restored.columns or []) == ["a", "b"]
    assert restored.row_count == 3


def test_round_trip_array(tmp_path: Path) -> None:
    """materialise → reconstruct round-trips an Array through .npy."""
    np_arr = np.arange(12, dtype=np.int64).reshape(3, 4)
    arr = Array(
        axes=[f"axis_{i}" for i in range(np_arr.ndim)],
        shape=tuple(np_arr.shape),
        dtype=str(np_arr.dtype),
    )
    arr._data = np_arr  # type: ignore[attr-defined]

    reg = _registry_with_core_io()
    out_path = materialise_to_file(arr, tmp_path, extension=".npy", registry=reg)
    assert out_path.exists()
    assert out_path.suffix == ".npy"

    restored = reconstruct_from_file(out_path, Array, registry=reg)
    assert isinstance(restored, Array)
    assert restored.shape == (3, 4)
    # The loader stores numpy data on ``_data``; verify content.
    assert np.array_equal(restored._data, np_arr)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# reconstruct_from_file fallback semantics
# ---------------------------------------------------------------------------


def test_reconstruct_falls_back_to_artifact_for_unknown_extension(tmp_path: Path) -> None:
    """When no loader matches and target_type=Artifact, return an Artifact."""
    src = tmp_path / "blob.weird"
    src.write_bytes(b"\x00\x01\x02")

    reg = _registry_with_core_io()
    result = reconstruct_from_file(src, Artifact, registry=reg)
    assert isinstance(result, Artifact)
    assert result.file_path == src
    assert result.description == "blob.weird"


def test_reconstruct_raises_lookup_for_concrete_type_no_loader(tmp_path: Path) -> None:
    """LookupError when target type is concrete and no loader matches."""

    class _MysteryType(DataObject):
        """Not in any loader's accepted_types."""

    src = tmp_path / "mystery.weird"
    src.write_bytes(b"\x00")

    reg = _registry_with_core_io()
    with pytest.raises(LookupError, match="no loader matches"):
        reconstruct_from_file(src, _MysteryType, registry=reg)


def test_reconstruct_missing_file_raises(tmp_path: Path) -> None:
    reg = _registry_with_core_io()
    with pytest.raises(FileNotFoundError, match="source not found"):
        reconstruct_from_file(tmp_path / "nope.csv", DataFrame, registry=reg)


# ---------------------------------------------------------------------------
# Pass-through (mount_pathlike) optimisation
# ---------------------------------------------------------------------------


class _PassThroughText(Text):
    """Subclass of Text so we can attach a storage_ref."""


class _TextDotXyz(IOBlock):
    """Module-level custom Text saver registered with a unique extension.

    Must live at module scope so :meth:`BlockRegistry._resolve_class`
    can ``getattr(module, class_name)`` it during dispatch (nested-in-
    function classes are unreachable through module attributes).
    """

    name: ClassVar[str] = "_TextDotXyz"
    type_name: ClassVar[str] = "test.txt_xyz"
    direction: ClassVar[str] = "output"
    supported_extensions: ClassVar[dict[str, str]] = {".xyz": "xyz"}
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="data", accepted_types=[Text]),
    ]
    output_ports: ClassVar[list[OutputPort]] = []
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        raise NotImplementedError

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        assert isinstance(obj, Text)
        Path(str(config.get("path"))).write_text(obj.content, encoding="utf-8")


def test_pass_through_invokes_mount_pathlike_when_extension_matches(tmp_path: Path) -> None:
    """When obj.storage_ref.path already has the target extension,
    materialise_to_file should invoke mount_pathlike instead of writing
    through the saver."""
    # Create a source file that simulates an on-disk text artifact.
    src = tmp_path / "src.txt"
    src.write_text("hello", encoding="utf-8")

    txt = Text(content="hello", format="plain")
    txt.storage_ref = StorageReference(backend="filesystem", path=str(src), format="text")

    reg = _registry_with_core_io()
    dest_dir = tmp_path / "out"

    with patch("scistudio.utils.fs.mount_pathlike") as mocked_mount:
        # Configure the mock to actually create the destination so the
        # downstream existence assertions succeed.
        def _fake_mount(s: Any, d: Any) -> Path:
            Path(d).parent.mkdir(parents=True, exist_ok=True)
            Path(d).write_text(Path(s).read_text(encoding="utf-8"), encoding="utf-8")
            return Path(d)

        mocked_mount.side_effect = _fake_mount
        out = materialise_to_file(txt, dest_dir, extension=".txt", registry=reg)

    mocked_mount.assert_called_once()
    args, _kwargs = mocked_mount.call_args
    # mount_pathlike(src_path, dest)
    assert Path(args[0]) == src
    assert Path(args[1]) == out


def test_pass_through_skipped_when_extension_mismatches(tmp_path: Path) -> None:
    """If the source extension does NOT match, the helper falls through
    to the saver round-trip instead of linking."""
    src = tmp_path / "src.txt"
    src.write_text("hello", encoding="utf-8")

    txt = Text(content="hello", format="plain")
    txt.storage_ref = StorageReference(backend="filesystem", path=str(src), format="text")

    reg = _registry_with_core_io()
    dest_dir = tmp_path / "out"

    with patch("scistudio.utils.fs.mount_pathlike") as mocked_mount:
        out = materialise_to_file(txt, dest_dir, extension=".md", registry=reg)

    mocked_mount.assert_not_called()
    assert out.exists()
    assert out.suffix == ".md"


# ---------------------------------------------------------------------------
# materialise_to_file: default extension + error paths
# ---------------------------------------------------------------------------


def test_default_extension_uses_first_saver_declared(tmp_path: Path) -> None:
    """When extension=None, the first registered saver's first
    declared extension is used. We register the module-level
    :class:`_TextDotXyz` saver to assert the value."""
    reg = _build_registry(_TextDotXyz)
    txt = Text(content="payload", format="plain")
    out = materialise_to_file(txt, tmp_path, extension=None, registry=reg)
    assert out.suffix == ".xyz"
    assert out.read_text(encoding="utf-8") == "payload"


def test_materialise_raises_lookup_when_no_saver_for_type(tmp_path: Path) -> None:
    """Empty registry => no saver matches => LookupError."""

    class _UnsupportedType(DataObject):
        pass

    reg = BlockRegistry()  # empty
    obj = _UnsupportedType()
    with pytest.raises(LookupError, match=r"no default extension|no saver"):
        materialise_to_file(obj, tmp_path, registry=reg)


def test_materialise_raises_lookup_when_no_saver_for_extension(tmp_path: Path) -> None:
    """Saver exists for the type but not for the requested extension."""
    txt = Text(content="x", format="plain")
    reg = _registry_with_core_io()
    with pytest.raises(LookupError, match="no saver matches"):
        materialise_to_file(txt, tmp_path, extension=".unknownext", registry=reg)


def test_reconstruct_handles_extra_dots_in_filename(tmp_path: Path) -> None:
    """Codex P1 regression: filenames like ``sample.v1.csv`` should
    resolve to a ``.csv`` loader by walking ``path.suffixes`` longest-
    first (the ``.v1.csv`` candidate has no handler, ``.csv`` does).
    Pre-fix, the helper joined all suffixes into ``.v1.csv`` and
    raised LookupError despite a registered ``.csv`` loader."""
    table = pa.table({"a": [1, 2, 3]})
    df = DataFrame(columns=["a"], row_count=3)
    df._arrow_table = table  # type: ignore[attr-defined]

    src = tmp_path / "sample.v1.csv"
    reg = _registry_with_core_io()
    # Use materialise to seed a real CSV under the extra-dot name.
    out = materialise_to_file(df, tmp_path, extension=".csv", filename_stem="sample.v1", registry=reg)
    assert out == src
    assert src.exists()

    restored = reconstruct_from_file(src, DataFrame, registry=reg)
    assert isinstance(restored, DataFrame)
    assert restored.row_count == 3


def test_materialise_normalises_extension_without_leading_dot(tmp_path: Path) -> None:
    """extension="csv" should be treated identically to extension=".csv"."""
    table = pa.table({"a": [1]})
    df = DataFrame(columns=["a"], row_count=1)
    df._arrow_table = table  # type: ignore[attr-defined]

    reg = _registry_with_core_io()
    out = materialise_to_file(df, tmp_path, extension="csv", registry=reg)
    assert out.suffix == ".csv"
    assert out.exists()
