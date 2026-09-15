"""Python for this MiniApp. The page calls the functions defined here by name.

``setup`` runs once, when the MiniApp opens, and receives the data the user
chose as a SciStudio data object. Load what is expensive to load here and keep
it in a module-level name; every subsequent call reuses it.

Every other function defined in this file whose name does not start with an
underscore is callable from the page as ``scistudio.call("<name>", {...})``.
Arguments arrive as keyword arguments from the page's JSON object; return
anything JSON-serialisable, or a NumPy array, which reaches the page as an
ArrayBuffer with its dtype and shape.

Right now ``setup`` does nothing, which is why the page you are looking at
explains itself instead of showing your data. The agent replaces this file.
"""

from __future__ import annotations

from typing import Any


def setup(data: Any) -> None:
    """Receive the chosen data once, before the page makes its first call."""
    return None
