"""Built-in process blocks shipped with the framework."""

from scistudio.blocks.process.builtins.data_router import DataRouter
from scistudio.blocks.process.builtins.merge import MergeBlock
from scistudio.blocks.process.builtins.merge_collection import MergeCollection
from scistudio.blocks.process.builtins.pair_editor import PairEditor
from scistudio.blocks.process.builtins.split import SplitBlock

__all__ = [
    "DataRouter",
    "MergeBlock",
    "MergeCollection",
    "PairEditor",
    "SplitBlock",
]
