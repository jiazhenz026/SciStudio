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
    """Merge, join, or concatenate multiple DataFrames.

    Config params:
        how: Join strategy — "concat" (vertical), "inner", "outer", "left".
             Default: "concat".
        on: Column(s) to join on.  Required for inner/outer/left.
    """

    name: ClassVar[str] = "Merge"
    algorithm: ClassVar[str] = "merge"
    description: ClassVar[str] = "Merge or concatenate multiple DataFrames"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="left", accepted_types=[DataFrame], description="Left/first table"),
        InputPort(name="right", accepted_types=[DataFrame], description="Right/second table"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="merged", accepted_types=[DataFrame], description="Merged table"),
    ]

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Merge two DataFrames via Arrow tables.

        Accepts both raw DataFrame and Collection[DataFrame] inputs for
        backward compatibility during the ADR-020 transition.
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
