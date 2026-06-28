"""Authoring-time block that references another workflow file as one node."""

from __future__ import annotations

from scistudio.blocks.subworkflow.subworkflow_block import (
    SubWorkflowBlock,
    SubWorkflowBroken,
)

__all__ = ["SubWorkflowBlock", "SubWorkflowBroken"]
