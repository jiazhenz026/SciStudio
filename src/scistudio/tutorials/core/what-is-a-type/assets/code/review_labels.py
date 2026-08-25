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
from scistudio.core.types import Collection, DataFrame, DataObject

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


def _removals(raw: Any, slides: int) -> list[list[int]]:
    """Read the panel's answer as one removal list per slide.

    Two shapes are accepted, and the reason is compatibility in both
    directions: the panel sends a list of lists, one per slide, while a single
    flat list is what a one-slide caller writes by hand and what this block
    answered to before it learned to review a batch.
    """
    if not raw:
        return [[] for _ in range(slides)]
    if all(isinstance(entry, (list, tuple)) for entry in raw):
        lists = [[int(value) for value in entry] for entry in raw]
    else:
        lists = [[int(value) for value in raw]]
    lists = lists[:slides]
    lists.extend([] for _ in range(slides - len(lists)))
    return lists


class ReviewLabelsBlock(InteractiveMixin, ProcessBlock):
    """Pause the run, show the label maps, and let a human remove bad labels.

    Input: the label ``Image`` a segmentation produced, or a batch of them.
    The panel walks the batch a slide at a time, listing every label with its
    area and letting you mark labels for removal. Outputs: the cleaned label
    maps, and one per-cell area table per slide.
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
        OutputPort(name="areas", accepted_types=[DataFrame], description="One row per kept label: id, area, centroid"),
    ]

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt:
        """Reduce every label map in the batch to the JSON view the panel renders.

        One prompt for the whole batch rather than one per slide, because the
        decision is one decision: a reader looking at six slides wants to walk
        them, mark what is wrong on each, and confirm once. Pausing the run
        again for every image would ask them the same question six times and
        make "next slide" mean "finish and wait".

        Args:
            inputs: The block's input collections; ``labels`` holds the maps.
            config: The block configuration (unused here).

        Returns:
            An :class:`InteractivePrompt` whose payload carries one entry per
            slide: the (possibly strided) label grid plus one row per label.
        """
        slides = []
        for index, (labels, micrograph, _item) in enumerate(self._slides(inputs)):
            stride = max(1, int(np.ceil(max(labels.shape) / MAX_PANEL_DIM)))
            grid = labels[::stride, ::stride]
            slide: dict[str, Any] = {
                "index": index,
                "height": int(grid.shape[0]),
                "width": int(grid.shape[1]),
                "stride": stride,
                "grid": grid.astype(int).tolist(),
                # Counted on the full-resolution map, never on the strided
                # view: the areas are the science, and the stride exists
                # only so the picture fits in a window.
                "labels": _label_rows(labels),
            }
            if micrograph is not None:
                # The cells the labels were found in, on the same strided grid,
                # scaled to 0..255. The panel draws the labels *over* this: a
                # reader asked to delete what is not a cell has to be able to
                # see the cells. Sent as bytes rather than the raw values
                # because that is all a picture needs, and it halves a payload
                # that now carries two planes per slide.
                plane = micrograph[::stride, ::stride].astype(float)
                low, high = float(plane.min()), float(plane.max())
                scaled = plane - low if high <= low else (plane - low) * (255.0 / (high - low))
                slide["image"] = np.clip(scaled, 0, 255).astype(np.uint8).tolist()
            slides.append(slide)
        return InteractivePrompt(panel_payload={"slides": slides})

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        """Apply the panel's decision, slide by slide, and measure what is left.

        Args:
            inputs: The block's input collections; ``labels`` holds the maps.
            config: Carries ``interactive_response`` — ``{"removed": [[ids],
                [ids], ...]}``, one list per slide in input order — injected by
                the engine after you confirm the panel. A flat list is also
                accepted and read as the decision for a single slide, which is
                what a one-image run sends.

        Returns:
            One area table per slide on ``areas``, in the order the slides
            arrived. The corrected label map is not an output: the reader
            deleted the labels themselves, on screen, so handing the map back
            would only restate what they just did. The measurement is the thing
            the correction was for.
        """
        slides = self._slides(inputs)
        maps = [labels for labels, _micrograph, _item in slides]
        sources = [item for _labels, _micrograph, item in slides]
        response = config.get("interactive_response", {}) or {}
        per_slide = _removals(response.get("removed"), len(maps))

        tables: list[DataObject] = []
        for (labels, removed), source in zip(zip(maps, per_slide, strict=True), sources, strict=True):
            cleaned = np.where(np.isin(labels, removed), 0, labels) if removed else labels
            rows = _label_rows(cleaned)
            tables.append(
                DataFrame(
                    data=pa.table(
                        {
                            "label": [row["id"] for row in rows],
                            "area_px": [row["area"] for row in rows],
                            "centroid_y": [row["y"] for row in rows],
                            "centroid_x": [row["x"] for row in rows],
                        }
                    ),
                    # Named after the slide it measures, all the way from the
                    # loader: the preview lists these tables side by side, and
                    # the Save block names the files it writes from this.
                    framework=getattr(source, "framework", None),
                )
            )
        return {"areas": Collection(items=tables, item_type=DataFrame)}

    def _slides(self, inputs: dict[str, Any]) -> list[tuple[np.ndarray, np.ndarray | None, Any]]:
        """Every (label map, micrograph) in this batch, in order.

        A batch is the ordinary case here: core Load hands a multi-file
        selection down as a collection, so a reader who picked two micrographs
        arrives with two label maps and expects to review both.

        Segment Cells emits two channels — the micrograph on ``c=0``, the
        labels it found on ``c=1`` — precisely so a surface downstream can show
        one over the other, and the panel does. A plain 2-D array is still
        accepted and reviews the same way; it simply has no picture to sit the
        labels on, and the micrograph comes back ``None``.
        """
        collection = inputs.get("labels")
        if collection is None:
            raise ValueError("Review Labels requires its 'labels' input to be connected.")
        items = list(collection) if isinstance(collection, Collection) else [collection]
        if not items:
            raise ValueError("Review Labels received an empty batch of label maps.")
        slides: list[tuple[np.ndarray, np.ndarray | None, Any]] = []
        for item in items:
            data = np.asarray(item.to_memory())
            if data.ndim == 3:
                slides.append((data[-1].astype(np.int32), data[0], item))
            else:
                slides.append((data.astype(np.int32), None, item))
        return slides
