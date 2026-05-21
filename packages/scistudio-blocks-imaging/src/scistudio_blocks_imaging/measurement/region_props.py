"""RegionProps block for per-label measurements."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, ClassVar, cast

import numpy as np
import pyarrow as pa

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.array import Array
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio_blocks_imaging.types import Image, Label


class RegionProps(ProcessBlock):
    """Compute per-label region properties (area, centroid, intensity stats)."""

    type_name: ClassVar[str] = "imaging.region_props"
    name: ClassVar[str] = "Region Properties"
    description: ClassVar[str] = "Compute per-label region properties (area, centroid, intensity stats) as a DataFrame."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "measurement"
    algorithm: ClassVar[str] = "region_props"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="label", accepted_types=[Label], description="Label image."),
        InputPort(
            name="intensity_image",
            accepted_types=[Image],
            required=False,
            description="Optional intensity image for intensity_* properties.",
        ),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(
            name="properties",
            accepted_types=[DataFrame],
            description="Per-label measurement table.",
        ),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "properties": {
                "type": "array",
                "items": {"type": "string"},
                "default": ["area", "centroid", "bbox"],
                "description": "skimage.measure.regionprops_table property names.",
            },
        },
    }

    def process_item(
        self,
        item: Label,
        config: BlockConfig,
        state: Any = None,
    ) -> DataFrame:
        return _props_dataframe(item, None, config, image_index=None)

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        labels = inputs["label"]
        intensity = inputs.get("intensity_image")

        if isinstance(labels, Collection):
            label_items = [cast(Label, item) for item in labels]
            intensity_items = _resolve_intensity_collection(intensity, len(label_items))
            output = _concat_region_props(label_items, intensity_items, config)
        else:
            if isinstance(intensity, Collection):
                raise ValueError("RegionProps: intensity_image Collection requires label to also be a Collection")
            output = _props_dataframe(cast(Label, labels), cast(Image | None, intensity), config, image_index=None)

        return {"properties": output}


def _concat_region_props(labels: list[Label], intensities: list[Image | None], config: BlockConfig) -> DataFrame:
    props = _configured_properties(config)
    column_names = ["image_index", "label_id", *_expanded_output_columns(props)]
    rows: list[dict[str, Any]] = []

    for image_index, (label, intensity) in enumerate(zip(labels, intensities, strict=True)):
        item_df = _props_dataframe(label, intensity, config, image_index=image_index)
        item_table = cast(pa.Table, item_df._arrow_table)  # type: ignore[attr-defined]
        rows.extend(item_table.to_pylist())

    return _dataframe_from_rows(rows, column_names, framework=labels[0].framework.derive() if labels else None)


def _props_dataframe(
    label: Label,
    intensity_image: Image | None,
    config: BlockConfig,
    *,
    image_index: int | None,
) -> DataFrame:
    from skimage.measure import regionprops_table

    props = _configured_properties(config)
    if intensity_image is None and any("intensity" in prop for prop in props):
        raise ValueError("RegionProps: intensity_image is required for intensity-based properties")

    label_data = _label_data(label)
    intensity_data = _image_data(intensity_image) if intensity_image is not None else None
    if intensity_data is not None and intensity_data.shape != label_data.shape:
        raise ValueError(
            "RegionProps: intensity_image must have the same shape as the label raster "
            f"(got {intensity_data.shape} vs {label_data.shape})"
        )

    props_table = regionprops_table(
        label_data,
        intensity_image=intensity_data,
        properties=("label", *props),
    )

    row_count = len(props_table["label"])
    columns: dict[str, list[Any]] = {}
    if image_index is not None:
        columns["image_index"] = [image_index] * row_count
    columns["label_id"] = [int(value) for value in np.asarray(props_table.pop("label")).tolist()]
    for name, values in props_table.items():
        columns[name] = np.asarray(values).tolist()

    return _dataframe_from_columns(columns, framework=label.framework.derive())


def _configured_properties(config: BlockConfig) -> list[str]:
    raw = config.get("properties", ["area", "centroid", "bbox"])
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ValueError("RegionProps: properties must be a list of strings")

    props = [item for item in raw if item != "label"]
    if not props:
        raise ValueError("RegionProps: properties must contain at least one requested property")
    return props


def _expanded_output_columns(properties: Iterable[str]) -> list[str]:
    expanded: list[str] = []
    for prop in properties:
        if prop == "centroid":
            expanded.extend(["centroid-0", "centroid-1"])
        elif prop == "bbox":
            expanded.extend(["bbox-0", "bbox-1", "bbox-2", "bbox-3"])
        else:
            expanded.append(prop)
    return expanded


def _resolve_intensity_collection(raw: Any, expected_length: int) -> list[Image | None]:
    if raw is None:
        return [None] * expected_length
    if isinstance(raw, Collection):
        items: list[Image | None] = [cast(Image, item) for item in raw]
        if len(items) != expected_length:
            raise ValueError(
                "RegionProps: intensity_image Collection must match label Collection length "
                f"(got {len(items)} vs {expected_length})"
            )
        return items
    raise ValueError("RegionProps: intensity_image must also be a Collection when label is a Collection")


def _label_data(label: Label) -> np.ndarray:
    raster = label.slots.get("raster")
    if raster is None or not isinstance(raster, Array):
        raise ValueError("RegionProps: label input requires a populated 'raster' slot")
    return np.asarray(raster.to_memory(), dtype=np.int32)


def _image_data(image: Image) -> np.ndarray:
    if image.storage_ref is None and hasattr(image, "_data") and getattr(image, "_data", None) is not None:
        return np.asarray(image._data)  # type: ignore[attr-defined]
    return np.asarray(image.to_memory())


def _dataframe_from_columns(columns: dict[str, list[Any]], *, framework: Any = None) -> DataFrame:
    table = pa.table({name: pa.array(values) for name, values in columns.items()})
    result = DataFrame(
        columns=list(table.column_names),
        row_count=table.num_rows,
        framework=framework,
    )
    result._arrow_table = table  # type: ignore[attr-defined]
    return result


def _dataframe_from_rows(rows: list[dict[str, Any]], column_names: list[str], *, framework: Any = None) -> DataFrame:
    columns = {name: [row.get(name) for row in rows] for name in column_names}
    return _dataframe_from_columns(columns, framework=framework)
