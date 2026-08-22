"""An interactive block: look at the label map and delete what is not a cell.

Core tutorial 2 writes this block into the tutorial project, together with the
small JavaScript window it opens (``blocks/review_labels_panel/``). It is a
real interactive block, the same machinery the built-in Data Router uses: it
declares ``execution_mode = INTERACTIVE``, the run pauses when it is reached,
:meth:`ReviewLabelsBlock.prepare_prompt` reduces the real input to a
window-sized JSON view, the panel collects your decision, and ``run`` computes
the outputs from it.

The panel is deliberately ordinary code. ``interactive_panel`` names a plain
ES module served from this project (``module_url``), confined to the directory
beside this file (``asset_root``); no framework, no build step. A block's
window is just a file it carries with it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import pyarrow as pa
from image import Image

from scistudio.blocks.base import (
    BlockConfig,
    ExecutionMode,
    InputPort,
    InteractiveMixin,
    InteractivePrompt,
    OutputPort,
    PanelManifest,
)
from scistudio.blocks.process import ProcessBlock
from scistudio.core.types import Collection, DataFrame

# Keep the JSON view the panel renders at or under this many cells per side;
# larger label maps are sent strided. Clicks still resolve exactly, because the
# panel reads the label id off the cell it hit rather than off coordinates.
MAX_PANEL_DIM = 160


def _label_rows(labels: np.ndarray) -> list[dict[str, Any]]:
    """One row per label: id, pixel area, and centroid, in label order."""
    rows: list[dict[str, Any]] = []
    for label_id in np.unique(labels):
        if label_id == 0:
            continue
        ys, xs = np.nonzero(labels == label_id)
        rows.append(
            {
                "id": int(label_id),
                "area": len(ys),
                "y": round(float(ys.mean()), 1),
                "x": round(float(xs.mean()), 1),
            }
        )
    return rows


class ReviewLabelsBlock(InteractiveMixin, ProcessBlock):
    """Pause the run, show the label map, and let a human remove bad labels.

    Input: the label ``Image`` a segmentation produced. The panel lists every
    label with its area and lets you mark labels for removal. Outputs: the
    cleaned label map, and a per-cell area table ready to save.
    """

    name: ClassVar[str] = "Review Labels"
    type_name: ClassVar[str] = "review_labels"
    description: ClassVar[str] = "Inspect a label map by eye and delete labels that are not cells."
    algorithm: ClassVar[str] = "manual_label_review"

    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE

    # The block-owned window: a hand-written, dependency-free ES module that
    # travels beside this file. The backend serves it, path-confined under
    # ``asset_root``, at the ``module_url`` below.
    interactive_panel: ClassVar[PanelManifest] = PanelManifest(
        panel_id="tutorial.review_labels",
        module_url="/api/blocks/panels/tutorial.review_labels/panel.mjs",
        version="1",
        asset_root=str(Path(__file__).resolve().parent / "review_labels_panel"),
    )

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="labels", accepted_types=[Image], description="The label map to review"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="labels", accepted_types=[Image], description="The label map with removals applied"),
        OutputPort(name="areas", accepted_types=[DataFrame], description="One row per kept label: id, area, centroid"),
    ]

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt:
        """Reduce the label map to the JSON view the panel renders.

        Args:
            inputs: The block's input collections; ``labels`` holds the map.
            config: The block configuration (unused here).

        Returns:
            An :class:`InteractivePrompt` whose payload carries the (possibly
            strided) label grid plus one row per label.
        """
        labels = self._labels_array(inputs)
        stride = max(1, int(np.ceil(max(labels.shape) / MAX_PANEL_DIM)))
        grid = labels[::stride, ::stride]
        return InteractivePrompt(
            panel_payload={
                "height": int(grid.shape[0]),
                "width": int(grid.shape[1]),
                "stride": stride,
                "grid": grid.astype(int).tolist(),
                "labels": _label_rows(labels),
            }
        )

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        """Apply the panel's decision and compute both outputs.

        Args:
            inputs: The block's input collections; ``labels`` holds the map.
            config: Carries ``interactive_response`` — ``{"removed": [ids]}``
                — injected by the engine after you confirm the panel.

        Returns:
            The cleaned label map on ``labels`` and the area table on ``areas``.
        """
        labels = self._labels_array(inputs)
        response = config.get("interactive_response", {}) or {}
        removed = [int(value) for value in response.get("removed", [])]
        cleaned = np.where(np.isin(labels, removed), 0, labels) if removed else labels

        rows = _label_rows(cleaned)
        table = pa.table(
            {
                "label": [row["id"] for row in rows],
                "area_px": [row["area"] for row in rows],
                "centroid_y": [row["y"] for row in rows],
                "centroid_x": [row["x"] for row in rows],
            }
        )
        return {
            "labels": Collection(items=[Image(axes=["y", "x"], data=cleaned)], item_type=Image),
            "areas": Collection(items=[DataFrame(data=table)], item_type=DataFrame),
        }

    def _labels_array(self, inputs: dict[str, Any]) -> np.ndarray:
        """The one label map this block reviews, as an int32 NumPy array."""
        collection = inputs.get("labels")
        if collection is None:
            raise ValueError("Review Labels requires its 'labels' input to be connected.")
        items = list(collection) if isinstance(collection, Collection) else [collection]
        if len(items) != 1:
            raise ValueError(f"Review Labels reviews one label map at a time, got {len(items)}.")
        return np.asarray(items[0].to_memory()).astype(np.int32)
