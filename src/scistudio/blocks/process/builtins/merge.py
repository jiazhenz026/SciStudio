"""MergeBlock — merge, join, concatenate multi-input data."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import pyarrow as pa

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.blocks.process.utils import to_arrow
from scistudio.core.types.dataframe import DataFrame

if TYPE_CHECKING:
    from scistudio.core.types.collection import Collection


class MergeBlock(ProcessBlock):
    """Combine two tables into one.

    Takes a table on each of its two input ports and produces a single
    combined table. Today it stacks the two tables on top of each other
    (concatenation); key-based joins are recognised but not yet implemented.

    Ports: reads ``left`` and ``right`` (each a DataFrame) and emits the
    combined table on ``merged``. Config: ``how`` selects the strategy --
    ``"concat"`` (the default) stacks the rows; any other value (``"inner"``,
    ``"outer"``, ``"left"``) is reserved and currently raises
    :class:`NotImplementedError`. ``on`` names the join column(s) and applies
    only to the not-yet-implemented join strategies.

    Example:
        >>> block = MergeBlock({"how": "concat"})
    """

    name: ClassVar[str] = "Merge"
    """Display name shown in the block palette and on the canvas node."""

    algorithm: ClassVar[str] = "merge"
    """Stable identifier for this block's transform; recorded in metadata."""

    description: ClassVar[str] = "Merge or concatenate multiple DataFrames"
    """One-line summary shown in the palette and node tooltip."""

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="left", accepted_types=[DataFrame], description="Left/first table"),
        InputPort(name="right", accepted_types=[DataFrame], description="Right/second table"),
    ]
    """The two input ports: ``left`` and ``right``, each accepting a DataFrame."""

    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="merged", accepted_types=[DataFrame], description="Merged table"),
    ]
    """The single output port ``merged``, carrying the combined DataFrame."""

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Combine the ``left`` and ``right`` tables into one.

        Each input may arrive either as a raw DataFrame or as a length-one
        Collection wrapping one; a Collection is unwrapped before merging.

        Args:
            inputs: Mapping with ``left`` and ``right``, each a DataFrame or a
                Collection holding one DataFrame.
            config: The block configuration. ``how`` selects the strategy and
                defaults to ``"concat"``.

        Returns:
            Mapping of ``merged`` to a Collection holding the combined
            DataFrame.

        Raises:
            TypeError: If either input does not resolve to an Arrow table.
            NotImplementedError: If ``how`` is anything other than ``"concat"``.
        """
        from scistudio.core.types.collection import Collection

        left_obj = inputs["left"]
        right_obj = inputs["right"]

        # ADR-020: Unpack Collection inputs if present.
        if isinstance(left_obj, Collection):
            left_obj = self.unpack_single(left_obj)
        if isinstance(right_obj, Collection):
            right_obj = self.unpack_single(right_obj)

        left_data = to_arrow(left_obj)
        right_data = to_arrow(right_obj)

        if not isinstance(left_data, pa.Table):
            raise TypeError(f"Expected Arrow Table, got {type(left_data).__name__}")
        if not isinstance(right_data, pa.Table):
            raise TypeError(f"Expected Arrow Table, got {type(right_data).__name__}")

        how = config.get("how", "concat")

        if how == "concat":
            merged = pa.concat_tables([left_data, right_data], promote_options="default")
        else:
            # TODO: implement non-concat join strategies (e.g. inner/left/outer on a join key column).
            raise NotImplementedError(f"Join strategy '{how}' is not yet implemented; use 'concat'.")

        result = _persist_arrow_result(merged)
        return {"merged": Collection([result], item_type=DataFrame)}


def _persist_arrow_result(table: pa.Table) -> DataFrame:
    """Create a DataFrame and persist the Arrow table to storage.

    ADR-031 D3: replaces the former ``result._arrow_table = table``
    pattern. The DataFrame is persisted to Arrow/Parquet storage and
    returned with ``storage_ref`` set.
    """
    import tempfile
    import uuid
    from pathlib import Path

    from scistudio.core.storage.arrow_backend import ArrowBackend
    from scistudio.core.storage.flush_context import get_output_dir
    from scistudio.core.storage.ref import StorageReference

    result = DataFrame(columns=table.column_names, row_count=table.num_rows)
    output_dir = get_output_dir()
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="scistudio_merge_")
    ref = StorageReference(backend="arrow", path=str(Path(output_dir) / f"{uuid.uuid4()}.parquet"))
    backend = ArrowBackend()
    result._storage_ref = backend.write(table, ref)
    return result
