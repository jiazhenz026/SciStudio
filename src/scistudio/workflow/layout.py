"""LayoutInfo -- optional node position storage for ReactFlow restore."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LayoutInfo:
    """Optional visual layout metadata for a workflow graph.

    Stores node positions, zoom level, and pan offset so that the
    frontend editor can restore the user's last view.
    """

    node_positions: dict[str, dict[str, float]] = field(default_factory=dict)
    zoom: float = 1.0
    pan_x: float = 0.0
    pan_y: float = 0.0
