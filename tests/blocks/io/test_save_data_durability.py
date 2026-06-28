"""Durability + pickle-warning regression tests for SaveData.

Covers:
- #1516 / BUG-2: every SaveData writer is crash-safe — an overwrite that
  crashes mid-write leaves the prior artifact intact (no truncation).
- #1545 / BUG-10: enabling ``allow_pickle`` emits a prominent WARNING so
  the (remote-code-execution) opt-in is auditable.
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path

import numpy as np
import pyarrow as pa
import pytest

from scistudio.blocks.io.savers.save_data import SaveData
from scistudio.core.types.array import Array
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.text import Text
from scistudio.utils import atomic_io


class _BoomError(Exception):
    pass


def _make_dataframe() -> DataFrame:
    table = pa.table({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]})
    df = DataFrame(columns=table.column_names, row_count=table.num_rows)
    df._arrow_table = table  # type: ignore[attr-defined]
    return df


# ---------------------------------------------------------------------------
# #1516 — crash-safe overwrite
# ---------------------------------------------------------------------------


class TestSaveDataCrashSafety:
    def test_text_overwrite_crash_leaves_prior_artifact_intact(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "out.txt"
        block = SaveData(config={"params": {"core_type": "Text", "path": str(path), "overwrite": True}})

        # First, a good write.
        block.save(Text(content="ORIGINAL"), block.config)
        assert path.read_text(encoding="utf-8") == "ORIGINAL"

        # Now simulate a crash partway through the atomic write of the
        # overwrite by making os.replace blow up (after the temp file is
        # fully written + fsynced, before the swap is published).
        real_replace = atomic_io.os.replace

        def _boom_replace(src: str, dst: str) -> None:
            raise _BoomError("simulated crash before atomic swap")

        monkeypatch.setattr(atomic_io.os, "replace", _boom_replace)
        with pytest.raises(_BoomError):
            block.save(Text(content="DOOMED"), block.config)
        monkeypatch.setattr(atomic_io.os, "replace", real_replace)

        # The prior artifact is untouched and fully readable.
        assert path.read_text(encoding="utf-8") == "ORIGINAL"
        # No temp siblings left behind.
        leftovers = [p.name for p in tmp_path.iterdir() if p.name != "out.txt"]
        assert leftovers == []

    def test_dataframe_csv_overwrite_crash_leaves_prior_artifact_intact(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import pyarrow.csv as pcsv

        path = tmp_path / "df.csv"
        block = SaveData(config={"params": {"core_type": "DataFrame", "path": str(path), "overwrite": True}})

        block.save(_make_dataframe(), block.config)
        original = pcsv.read_csv(str(path)).to_pydict()
        assert original == {"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]}

        def _boom_replace(src: str, dst: str) -> None:
            raise _BoomError("simulated crash before atomic swap")

        monkeypatch.setattr(atomic_io.os, "replace", _boom_replace)
        with pytest.raises(_BoomError):
            block.save(_make_dataframe(), block.config)

        monkeypatch.undo()
        # Prior CSV still parses and is unchanged.
        assert pcsv.read_csv(str(path)).to_pydict() == original
        leftovers = [p.name for p in tmp_path.iterdir() if p.name != "df.csv"]
        assert leftovers == []

    def test_zarr_store_write_crash_leaves_no_partial_store(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The directory-style zarr output is published atomically (#1516).

        A crash during the directory swap must leave the destination
        absent (the safe "missing, not half-written" failure mode for
        directory outputs) and remove the temp build dir — never a
        truncated store at the destination path.
        """
        pytest.importorskip("zarr")
        from scistudio.blocks.base.config import BlockConfig
        from scistudio.blocks.io.savers.save_data import _save_array

        path = tmp_path / "arr.zarr"
        arr = Array(axes=["x"], shape=(3,), dtype=np.dtype("int64"))
        arr._data = np.array([1, 2, 3])  # type: ignore[attr-defined]
        cfg = BlockConfig(params={"path": str(path), "format": "zarr"})

        def _boom_replace(src: str, dst: str) -> None:
            raise _BoomError("simulated crash before dir swap")

        monkeypatch.setattr(atomic_io.os, "replace", _boom_replace)
        with pytest.raises(_BoomError):
            _save_array(arr, cfg)
        monkeypatch.undo()

        # No store was published and no temp build dir was left behind.
        assert not path.exists()
        leftovers = list(tmp_path.iterdir())
        assert leftovers == []

    def test_zarr_store_round_trip_via_atomic_dir(self, tmp_path: Path) -> None:
        """A clean zarr save publishes a fully loadable store (#1516)."""
        zarr = pytest.importorskip("zarr")
        from scistudio.blocks.base.config import BlockConfig
        from scistudio.blocks.io.savers.save_data import _save_array

        path = tmp_path / "arr.zarr"
        arr = Array(axes=["x"], shape=(3,), dtype=np.dtype("int64"))
        arr._data = np.array([1, 2, 3])  # type: ignore[attr-defined]
        _save_array(arr, BlockConfig(params={"path": str(path), "format": "zarr"}))

        assert path.is_dir()
        np.testing.assert_array_equal(zarr.load(str(path)), np.array([1, 2, 3]))
        # No temp build dirs left next to the published store.
        leftovers = [p.name for p in tmp_path.iterdir() if p.name != "arr.zarr"]
        assert leftovers == []

    def test_successful_text_overwrite_replaces_content(self, tmp_path: Path) -> None:
        path = tmp_path / "out.txt"
        block = SaveData(config={"params": {"core_type": "Text", "path": str(path), "overwrite": True}})
        block.save(Text(content="v1"), block.config)
        block.save(Text(content="v2"), block.config)
        assert path.read_text(encoding="utf-8") == "v2"


# ---------------------------------------------------------------------------
# #1545 — pickle opt-in emits a prominent warning
# ---------------------------------------------------------------------------


class TestPickleWarning:
    def test_pickle_save_emits_warning(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        path = tmp_path / "df.pkl"
        block = SaveData(config={"params": {"core_type": "DataFrame", "path": str(path), "allow_pickle": True}})
        with caplog.at_level(logging.WARNING, logger="scistudio.blocks.io.savers.save_data"):
            block.save(_make_dataframe(), block.config)

        assert path.exists()
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warnings, "expected a WARNING when allow_pickle is enabled"
        msg = " ".join(r.getMessage().lower() for r in warnings)
        assert "pickle" in msg
        assert "code" in msg  # references arbitrary-code-execution risk

    def test_pickle_save_refused_without_opt_in(self, tmp_path: Path) -> None:
        path = tmp_path / "df.pkl"
        block = SaveData(config={"params": {"core_type": "DataFrame", "path": str(path)}})
        with pytest.raises(ValueError, match="pickle"):
            block.save(_make_dataframe(), block.config)
        # Default behavior unchanged: nothing written.
        assert not path.exists()

    def test_pickle_save_roundtrips_when_enabled(self, tmp_path: Path) -> None:
        path = tmp_path / "df.pkl"
        block = SaveData(config={"params": {"core_type": "DataFrame", "path": str(path), "allow_pickle": True}})
        block.save(_make_dataframe(), block.config)
        with path.open("rb") as fh:
            recovered = pickle.load(fh)
        # The pickled payload is the in-memory arrow table.
        assert isinstance(recovered, pa.Table)
        assert recovered.to_pydict() == {"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]}
