"""Colocalization block for channel-wise overlap metrics."""

from __future__ import annotations

from typing import Any, ClassVar, cast

import numpy as np
import pyarrow as pa

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio_blocks_imaging.types import Image, Mask


class Colocalization(ProcessBlock):
    """Compute Pearson, Manders, and Costes channel colocalization metrics."""

    type_name: ClassVar[str] = "imaging.colocalization"
    name: ClassVar[str] = "Colocalization"
    description: ClassVar[str] = "Compute Pearson / Manders / Costes colocalization metrics for two intensity channels."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "measurement"
    algorithm: ClassVar[str] = "colocalization"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="channel_a", accepted_types=[Image], description="First intensity channel."),
        InputPort(name="channel_b", accepted_types=[Image], description="Second intensity channel."),
        InputPort(
            name="mask",
            accepted_types=[Mask],
            required=False,
            description="Optional region-of-interest mask.",
        ),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(
            name="metrics",
            accepted_types=[DataFrame],
            description="One-row DataFrame with Pearson / Manders / Costes columns.",
        ),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "metrics": {
                "type": "array",
                "items": {"type": "string", "enum": ["pearson", "manders", "costes"]},
                "default": ["pearson", "manders"],
            },
        },
    }

    def process_item(
        self,
        item: Image,
        config: BlockConfig,
        state: Any = None,
    ) -> DataFrame:
        metrics = _configured_metrics(config)
        return _metrics_dataframe(item, item, None, metrics=metrics, image_index=None)

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        metrics = _configured_metrics(config)
        channel_a = inputs["channel_a"]
        channel_b = inputs["channel_b"]
        mask = inputs.get("mask")

        if isinstance(channel_a, Collection) or isinstance(channel_b, Collection) or isinstance(mask, Collection):
            a_items = _require_collection(channel_a, "Colocalization", "channel_a")
            b_items = _require_collection(channel_b, "Colocalization", "channel_b")
            if len(a_items) != len(b_items):
                raise ValueError(
                    "Colocalization: channel_a and channel_b Collections must have the same length "
                    f"(got {len(a_items)} vs {len(b_items)})"
                )
            mask_items = _resolve_mask_collection(mask, len(a_items))
            rows: list[dict[str, Any]] = []
            for image_index, (a_item, b_item, mask_item) in enumerate(zip(a_items, b_items, mask_items, strict=True)):
                item_df = _metrics_dataframe(a_item, b_item, mask_item, metrics=metrics, image_index=image_index)
                item_table = cast(pa.Table, item_df._arrow_table)  # type: ignore[attr-defined]
                rows.extend(item_table.to_pylist())
            return {
                "metrics": _dataframe_from_rows(
                    rows,
                    column_names=_column_names(metrics, include_image_index=True),
                    framework=a_items[0].framework.derive() if a_items else None,
                )
            }

        if isinstance(mask, Collection):
            raise ValueError("Colocalization: mask Collection requires channel_a/channel_b to also be Collections")

        return {
            "metrics": _metrics_dataframe(
                cast(Image, channel_a),
                cast(Image, channel_b),
                cast(Mask | None, mask),
                metrics=metrics,
                image_index=None,
            )
        }


def _metrics_dataframe(
    channel_a: Image,
    channel_b: Image,
    mask: Mask | None,
    *,
    metrics: list[str],
    image_index: int | None,
) -> DataFrame:
    a = _image_data(channel_a).astype(np.float64)
    b = _image_data(channel_b).astype(np.float64)
    if a.shape != b.shape:
        raise ValueError(f"Colocalization: channel shapes must match (got {a.shape} vs {b.shape})")

    mask_array = _mask_data(mask, a.shape) if mask is not None else np.ones(a.shape, dtype=bool)
    a_values = a[mask_array]
    b_values = b[mask_array]

    row: dict[str, Any] = {}
    if image_index is not None:
        row["image_index"] = image_index
    if "pearson" in metrics:
        row["pearson_r"] = _pearson(a_values, b_values)
    if "manders" in metrics:
        m1, m2 = _manders(a_values, b_values)
        row["manders_m1"] = m1
        row["manders_m2"] = m2
    if "costes" in metrics:
        threshold_a, threshold_b, pearson_r = _costes(a_values, b_values)
        row["costes_threshold_a"] = threshold_a
        row["costes_threshold_b"] = threshold_b
        row["costes_pearson_r"] = pearson_r

    return _dataframe_from_rows(
        [row],
        column_names=_column_names(metrics, include_image_index=image_index is not None),
        framework=channel_a.framework.derive(),
    )


def _configured_metrics(config: BlockConfig) -> list[str]:
    raw = config.get("metrics", ["pearson", "manders"])
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ValueError("Colocalization: metrics must be a list of strings")

    metrics = list(dict.fromkeys(raw))
    invalid = [metric for metric in metrics if metric not in {"pearson", "manders", "costes"}]
    if invalid:
        raise ValueError(f"Colocalization: unsupported metrics {invalid}")
    if not metrics:
        raise ValueError("Colocalization: metrics must request at least one metric")
    return metrics


def _column_names(metrics: list[str], *, include_image_index: bool) -> list[str]:
    names: list[str] = ["image_index"] if include_image_index else []
    if "pearson" in metrics:
        names.append("pearson_r")
    if "manders" in metrics:
        names.extend(["manders_m1", "manders_m2"])
    if "costes" in metrics:
        names.extend(["costes_threshold_a", "costes_threshold_b", "costes_pearson_r"])
    return names


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    if a.size < 2 or b.size < 2:
        return 0.0
    if np.isclose(np.std(a), 0.0) or np.isclose(np.std(b), 0.0):
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def _manders(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    a_sum = float(np.sum(a))
    b_sum = float(np.sum(b))
    coloc_a = float(np.sum(a[b > 0]))
    coloc_b = float(np.sum(b[a > 0]))
    return (0.0 if np.isclose(a_sum, 0.0) else coloc_a / a_sum, 0.0 if np.isclose(b_sum, 0.0) else coloc_b / b_sum)


def _costes(a: np.ndarray, b: np.ndarray) -> tuple[float, float, float]:
    if a.size < 2 or b.size < 2:
        return (0.0, 0.0, 0.0)

    if np.allclose(a, a[0]) or np.allclose(b, b[0]):
        threshold_a = float(np.mean(a))
        threshold_b = float(np.mean(b))
        return (threshold_a, threshold_b, 0.0)

    slope, intercept = np.polyfit(a, b, deg=1)
    threshold_a = float(np.min(a))
    threshold_b = float(slope * threshold_a + intercept)

    for candidate_a in np.unique(np.sort(a)[::-1]):
        candidate_b = float(slope * candidate_a + intercept)
        below = (a <= candidate_a) & (b <= candidate_b)
        if np.count_nonzero(below) < 2:
            continue
        if _pearson(a[below], b[below]) <= 0.0:
            threshold_a = float(candidate_a)
            threshold_b = candidate_b
            break

    above = (a > threshold_a) & (b > threshold_b)
    return (threshold_a, threshold_b, _pearson(a[above], b[above]) if np.count_nonzero(above) >= 2 else 0.0)


def _image_data(image: Image) -> np.ndarray:
    if image.storage_ref is None and hasattr(image, "_data") and getattr(image, "_data", None) is not None:
        return np.asarray(image._data)  # type: ignore[attr-defined]
    return np.asarray(image.to_memory())


def _mask_data(mask: Mask, expected_shape: tuple[int, ...]) -> np.ndarray:
    if mask.storage_ref is None and hasattr(mask, "_data") and getattr(mask, "_data", None) is not None:
        data = np.asarray(mask._data, dtype=bool)  # type: ignore[attr-defined]
    else:
        data = np.asarray(mask.to_memory(), dtype=bool)
    if data.shape != expected_shape:
        raise ValueError(f"Colocalization: mask shape must match channel shape (got {data.shape} vs {expected_shape})")
    return data


def _require_collection(raw: Any, block_name: str, input_name: str) -> list[Image]:
    if not isinstance(raw, Collection):
        raise ValueError(f"{block_name}: {input_name} must be a Collection when any input is a Collection")
    return [cast(Image, item) for item in raw]


def _resolve_mask_collection(raw: Any, expected_length: int) -> list[Mask | None]:
    if raw is None:
        return [None] * expected_length
    if isinstance(raw, Collection):
        items: list[Mask | None] = [cast(Mask, item) for item in raw]
        if len(items) == 1:
            return items * expected_length
        if len(items) != expected_length:
            raise ValueError(
                "Colocalization: mask Collection must have length 1 or match the channel Collection length "
                f"(got {len(items)} vs {expected_length})"
            )
        return items
    return [cast(Mask, raw)] * expected_length


def _dataframe_from_rows(rows: list[dict[str, Any]], *, column_names: list[str], framework: Any = None) -> DataFrame:
    columns = {name: [row.get(name) for row in rows] for name in column_names}
    table = pa.table({name: pa.array(values) for name, values in columns.items()})
    result = DataFrame(columns=list(table.column_names), row_count=table.num_rows, framework=framework)
    result._arrow_table = table  # type: ignore[attr-defined]
    return result
