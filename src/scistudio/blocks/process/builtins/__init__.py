"""Built-in process blocks shipped with the framework."""

from scistudio.blocks.process.builtins.data_router import DataRouter
from scistudio.blocks.process.builtins.filter_collection import FilterCollection
from scistudio.blocks.process.builtins.merge import MergeBlock
from scistudio.blocks.process.builtins.merge_collection import MergeCollection
from scistudio.blocks.process.builtins.pair_editor import PairEditor
from scistudio.blocks.process.builtins.slice_collection import SliceCollection
from scistudio.blocks.process.builtins.split import SplitBlock
from scistudio.blocks.process.builtins.split_collection import SplitCollection

__all__ = [
    "DataRouter",
    "FilterCollection",
    "MergeBlock",
    "MergeCollection",
    "PairEditor",
    "SliceCollection",
    "SplitBlock",
    "SplitCollection",
]
