"""PairwiseDistance block for labelled object distances."""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
import pyarrow as pa

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.array import Array
from scistudio.core.types.dataframe import DataFrame
from scistudio_blocks_imaging.types import Label


class PairwiseDistance(ProcessBlock):
    """Compute pairwise distances between labelled objects in a label image."""

    type_name: ClassVar[str] = "imaging.pairwise_distance"
    name: ClassVar[str] = "Pairwise Distance"
    description: ClassVar[str] = "Compute pairwise distances between labelled objects (centroid or edge metric)."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "measurement"
    algorithm: ClassVar[str] = "pairwise_distance"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="label", accepted_types=[Label], description="Label image."),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(
            name="distances",
            accepted_types=[DataFrame],
            description="Long-format distance table (label_id_a, label_id_b, distance).",
        ),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "metric": {
                "type": "string",
                "enum": ["centroid", "edge"],
                "default": "centroid",
            },
            "max_distance": {
                "type": ["number", "null"],
                "default": None,
                "description": "Optional cutoff; pairs above this are dropped.",
            },
        },
    }

    def process_item(
        self,
        item: Label,
        config: BlockConfig,
        state: Any = None,
    ) -> DataFrame:
        from skimage.measure import regionprops

        metric = str(config.get("metric", "centroid"))
        if metric not in {"centroid", "edge"}:
            raise ValueError(f"PairwiseDistance: unsupported metric {metric!r}")

        max_distance = config.get("max_distance")
        max_distance_value = float(max_distance) if max_distance is not None else None

        labels = _label_data(item)
        props = list(regionprops(labels))
        rows: list[dict[str, Any]] = []
        edge_coords: dict[int, np.ndarray] = {}

        for left_index, left_prop in enumerate(props):
            for right_prop in props[left_index + 1 :]:
                if metric == "centroid":
                    distance = float(np.linalg.norm(np.asarray(left_prop.centroid) - np.asarray(right_prop.centroid)))
                else:
                    left_coords = edge_coords.setdefault(left_prop.label, np.argwhere(labels == left_prop.label))
                    right_coords = edge_coords.setdefault(right_prop.label, np.argwhere(labels == right_prop.label))
                    distance = _min_pairwise_distance(left_coords, right_coords)

                if max_distance_value is not None and distance > max_distance_value:
                    continue

                rows.append(
                    {
                        "label_id_a": int(left_prop.label),
                        "label_id_b": int(right_prop.label),
                        "distance": distance,
                    }
                )

        return _dataframe_from_rows(rows, framework=item.framework.derive())


def _label_data(item: Label) -> np.ndarray:
    raster = item.slots.get("raster")
    if raster is None or not isinstance(raster, Array):
        raise ValueError("PairwiseDistance: label input requires a populated 'raster' slot")
    return np.asarray(raster.to_memory(), dtype=np.int32)


def _min_pairwise_distance(left: np.ndarray, right: np.ndarray) -> float:
    if left.size == 0 or right.size == 0:
        return float("inf")
    deltas = left[:, None, :].astype(np.float64) - right[None, :, :].astype(np.float64)
    distances = np.sqrt(np.sum(deltas * deltas, axis=2))
    return float(np.min(distances))


def _dataframe_from_rows(rows: list[dict[str, Any]], *, framework: Any = None) -> DataFrame:
    columns = {
        "label_id_a": [row["label_id_a"] for row in rows],
        "label_id_b": [row["label_id_b"] for row in rows],
        "distance": [row["distance"] for row in rows],
    }
    table = pa.table({name: pa.array(values) for name, values in columns.items()})
    result = DataFrame(columns=list(table.column_names), row_count=table.num_rows, framework=framework)
    result._arrow_table = table  # type: ignore[attr-defined]
    return result
