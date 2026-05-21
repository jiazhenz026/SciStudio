"""Issue #1369 regression — Save Image config exposes a file browser.

SaveImage writes single-image outputs to a concrete file path
(``out.tif``, ``out.zarr``, ``out.png``, ``out.jpg``). The bottom panel
must therefore open the **file** picker, not the directory picker.

The base ``IOBlock`` declares ``path`` with ``ui_widget="file_browser"``,
but the ADR-030 registry post-processor (in
``scistudio.blocks.registry._merge_config_schema``) flips that to
``directory_browser`` for any ``direction=="output"`` subclass that does
NOT declare ``path`` in its own ``config_schema``. Pre-#1369 SaveImage
inherited ``path`` from the base, so the post-processor rewrote it to
``directory_browser`` — driving the bottom panel into the native
directory picker even though ``SaveImage.save()`` ultimately wrote to
``_write_single`` for single-image outputs.

The fix re-declares ``path`` in ``SaveImage.config_schema.properties``
so ``_subclass_declares_field`` returns True and the post-processor
leaves the inherited ``file_browser`` widget alone. This test pins the
contract by walking the registry-merged schema for ``SaveImage`` and
asserting the resulting ``ui_widget`` is ``"file_browser"``.

The bottom panel mapping
(``frontend/src/components/BottomPanel.tsx``) reads ``ui_widget`` →
``browseMode`` directly (``file_browser`` → ``"file"``,
``directory_browser`` → ``"directory"``), so a backend assertion is
sufficient to lock the UX contract end-to-end.

Codex review on PR #1395 flagged a related UI/runtime mismatch: with
``file_browser`` consistently exposed, a user picking ``out.tif`` for
a node that turns out to receive a multi-item Collection at runtime
would have their filename silently dropped (pre-fix batch logic did
``out_dir = path if path.suffix == "" else path.parent`` then wrote
``out_dir/image_0000.tif``). The companion runtime fix in
``SaveImage.save`` now honours the typed stem in batch mode (``out.tif``
+ N items → ``out_0000.tif``, ``out_0001.tif``, …) and keeps the legacy
bare-directory branch when ``path`` has no suffix. The batch tests
below pin both branches.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from scistudio_blocks_imaging.io.save_image import SaveImage
from scistudio_blocks_imaging.types import Image

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.registry import _merge_config_schema
from scistudio.core.types.collection import Collection


def _make_image(arr: np.ndarray, axes: list[str]) -> Image:
    img = Image(axes=axes, shape=arr.shape, dtype=arr.dtype)
    img._data = arr
    return img


def test_save_image_path_uses_file_browser_after_merge() -> None:
    """The registry-merged ``path`` schema must advertise ``file_browser``.

    Pre-#1369 ``path`` was inherited from IOBlock and the post-processor
    rewrote ``ui_widget`` to ``directory_browser`` for output IOBlock
    subclasses. Post-#1369 SaveImage declares ``path`` itself, so the
    inherited ``file_browser`` is preserved.
    """
    merged = _merge_config_schema(SaveImage)
    assert "path" in merged["properties"], "SaveImage must expose a path config"
    path_prop = merged["properties"]["path"]
    assert path_prop["ui_widget"] == "file_browser", (
        f"SaveImage.path must advertise file_browser so the bottom panel opens the "
        f"native file picker (single-image saves write to a concrete file); got "
        f"{path_prop['ui_widget']!r}. See issue #1369."
    )


def test_save_image_path_is_single_string_not_array() -> None:
    """``path`` is a single-string field for single-image saves.

    Multi-image batch mode still treats the path as a directory at
    runtime (``SaveImage.save`` handles the dispatch), but the config
    UI surface is a single string. ADR-030 directory_browser shape
    typically narrows ``type`` to ``"string"`` and drops ``items``;
    after #1369 the post-processor no longer mutates this field, so we
    assert the declaration shape directly: ``type == "string"`` and no
    ``items`` key.
    """
    merged = _merge_config_schema(SaveImage)
    path_prop = merged["properties"]["path"]
    assert path_prop["type"] == "string"
    assert "items" not in path_prop


def test_save_image_path_is_required() -> None:
    """``path`` remains required even after the local override."""
    merged = _merge_config_schema(SaveImage)
    assert "path" in merged.get("required", [])


def test_save_image_other_savers_still_get_directory_browser_for_path() -> None:
    """Regression guard: the override must be SaveImage-specific.

    Other output IOBlock subclasses that did NOT receive the same
    treatment (e.g. ``SaveData`` in the core ``io.savers`` module)
    should continue to use ``directory_browser`` because they expect a
    directory at runtime. This test pins the locality of the #1369
    change so a future refactor cannot accidentally widen the
    file-browser semantics to every output block.
    """
    pytest.importorskip("scistudio.blocks.io.savers.save_data")
    from scistudio.blocks.io.savers.save_data import SaveData

    merged = _merge_config_schema(SaveData)
    assert merged["properties"]["path"]["ui_widget"] == "directory_browser"


def test_save_image_batch_with_file_suffix_path_honours_stem(tmp_path: Path) -> None:
    """Codex review on PR #1395 — batch mode honours the typed file stem.

    With the new file-browser UX a user types ``out.tif`` for the
    SaveImage ``path``. If the node turns out to receive a multi-item
    Collection at runtime, batch dispatch must:

    * write into ``out.tif.parent`` (NOT lose the filename), AND
    * use ``out.tif.stem`` as the per-item filename prefix.

    Pre-fix behaviour silently stripped the stem and wrote
    ``parent/image_0000.tif`` — making the file-picker UX misleading.
    """
    arr = np.zeros((2, 2), dtype=np.uint8)
    imgs = [_make_image(arr.copy(), ["y", "x"]) for _ in range(3)]
    col = Collection(items=imgs, item_type=Image)
    out_file = tmp_path / "result.tif"
    SaveImage().save(col, BlockConfig(params={"path": str(out_file)}))
    # Filename stem is honoured; outputs land in the same directory.
    assert (tmp_path / "result_0000.tif").exists()
    assert (tmp_path / "result_0001.tif").exists()
    assert (tmp_path / "result_0002.tif").exists()
    # The literal file path is NOT created (filename was used as stem,
    # not as a literal target).
    assert not out_file.exists()


def test_save_image_batch_with_bare_directory_path_uses_image_prefix(
    tmp_path: Path,
) -> None:
    """Legacy backward-compat — bare-directory ``path`` keeps ``image`` prefix.

    Workflow YAMLs that pass a bare directory (no suffix, e.g.
    ``batch_out``) for batch saves are unchanged: ``path`` is the
    output directory and per-item filenames use the default ``image``
    prefix. This pins the legacy branch so the #1395 stem-honouring
    fix does not silently change YAML-driven batch outputs.
    """
    arr = np.zeros((2, 2), dtype=np.uint8)
    imgs = [_make_image(arr.copy(), ["y", "x"]) for _ in range(2)]
    col = Collection(items=imgs, item_type=Image)
    out_dir = tmp_path / "batch_out"
    SaveImage().save(col, BlockConfig(params={"path": str(out_dir)}))
    # Legacy ``image_XXXX`` prefix preserved for bare-directory paths.
    assert (out_dir / "image_0000.tif").exists()
    assert (out_dir / "image_0001.tif").exists()
