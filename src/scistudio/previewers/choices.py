"""Deprecated alias for :mod:`scistudio.panels.choices` (ADR-054 spec 1, FR-038).

Core-internal machinery that resolved under ``scistudio.previewers`` before the
rename. It carries no author stability promise, but it imported, and a path that
silently stops importing is the break the alias package exists to prevent
(FR-020).

One value changed rather than just a name. ``CHOICES_FILENAME`` names *the file
this build reads and writes*, and that file is now ``panel-choices.json``, so the
constant re-exported here answers ``panel-choices.json`` and not the pre-rename
``previewer-choices.json``. Freezing the old value would be worse than the
rename: a caller asking this module which file to read would be told about a
file the runtime no longer writes. The pre-rename name is still on disk in real
projects, is still read, and is exported here as ``LEGACY_CHOICES_FILENAME``.

It contains no logic of its own — only imports and aliases. Removed under the
condition stated in the ADR-048 addendum (FR-044).
"""

from __future__ import annotations

from scistudio.panels.choices import (
    CHOICES_FILENAME as CHOICES_FILENAME,
)
from scistudio.panels.choices import (
    LEGACY_CHOICES_FILENAME as LEGACY_CHOICES_FILENAME,
)
from scistudio.panels.choices import (
    clear_choice as clear_choice,
)
from scistudio.panels.choices import (
    load_choice_layers as load_choice_layers,
)
from scistudio.panels.choices import (
    load_choices as load_choices,
)
from scistudio.panels.choices import (
    project_choices_path as project_choices_path,
)
from scistudio.panels.choices import (
    read_choice_layer as read_choice_layer,
)
from scistudio.panels.choices import (
    read_choice_layers as read_choice_layers,
)
from scistudio.panels.choices import (
    user_choices_path as user_choices_path,
)
from scistudio.panels.choices import (
    write_choice as write_choice,
)

__all__ = [
    "CHOICES_FILENAME",
    "clear_choice",
    "load_choices",
    "project_choices_path",
    "read_choice_layer",
    "user_choices_path",
    "write_choice",
]
