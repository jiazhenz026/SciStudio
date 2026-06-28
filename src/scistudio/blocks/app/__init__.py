"""App block authoring surface (ADR-052 §7).

Canonical root: ``from scistudio.blocks.app import …``. The whole app-block
surface is **provisional** (ADR-052 §7): the base :class:`AppBlock`, the
file-exchange facilities (:class:`FileExchangeBridge` and the
:class:`ExternalAppBridge` protocol), the output :class:`FileWatcher` and its
:class:`ProcessExitedWithoutOutputError`, the :func:`validate_app_command`
security helper, and :class:`BlockCancelledByAppError` (re-exported from
``scistudio.blocks.base`` as its AppBlock-authoring home).
"""

from __future__ import annotations

from scistudio.blocks.app.app_block import AppBlock
from scistudio.blocks.app.bridge import ExternalAppBridge, FileExchangeBridge
from scistudio.blocks.app.command_validator import validate_app_command
from scistudio.blocks.app.watcher import FileWatcher, ProcessExitedWithoutOutputError
from scistudio.blocks.base.exceptions import BlockCancelledByAppError

__all__ = [
    "AppBlock",
    "BlockCancelledByAppError",
    "ExternalAppBridge",
    "FileExchangeBridge",
    "FileWatcher",
    "ProcessExitedWithoutOutputError",
    "validate_app_command",
]
