"""Tools for building blocks that hand work to an external GUI application.

Import everything from this one place::

    from scistudio.blocks.app import AppBlock, FileExchangeBridge

This is the surface a block author uses to wrap a desktop program — an image
viewer, an analysis GUI, a file converter — as a SciStudio block: the base
:class:`AppBlock`, the file-exchange helpers (:class:`FileExchangeBridge` and
the :class:`ExternalAppBridge` protocol it satisfies), the output-file
:class:`FileWatcher` and its :class:`ProcessExitedWithoutOutputError`, the
:func:`validate_app_command` safety check, and
:class:`BlockCancelledByAppError` (re-exported here because this is where an
app-block author meets it).

Everything in this module is still settling and may change in a future minor
release.
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
