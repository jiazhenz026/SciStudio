"""Deprecated alias for :mod:`scistudio.panels.fallbacks` (ADR-054 spec 1, FR-038).

This path is not incidental. #1823 moved ``sanitize_svg`` to the public helpers
home and kept ``scistudio.previewers.fallbacks`` as a back-compat re-export of
it *specifically* so out-of-tree packages would not hard-break before migrating;
that promise is the whole reason the module was left importable then, and the
rename must not quietly withdraw it (FR-020, FR-042).

The generic core providers are re-exported under their pre-rename names as well.
They are core-internal and carry no author stability promise, but they resolved
before the rename and a path that silently stops resolving is exactly the break
the alias package exists to prevent.

It contains no logic of its own — only imports and aliases. Removed under the
condition stated in the ADR-048 addendum (FR-044).
"""

from __future__ import annotations

from scistudio.panels.fallbacks import (
    array_panel as array_previewer,
)
from scistudio.panels.fallbacks import (
    artifact_panel as artifact_previewer,
)
from scistudio.panels.fallbacks import (
    base_fallback_panel as base_fallback_previewer,
)
from scistudio.panels.fallbacks import (
    collection_panel as collection_previewer,
)
from scistudio.panels.fallbacks import (
    composite_panel as composite_previewer,
)
from scistudio.panels.fallbacks import (
    core_panel_specs as core_previewer_specs,
)
from scistudio.panels.fallbacks import (
    dataframe_panel as dataframe_previewer,
)
from scistudio.panels.fallbacks import (
    plot_panel as plot_previewer,
)
from scistudio.panels.fallbacks import (
    series_panel as series_previewer,
)
from scistudio.panels.fallbacks import (
    text_panel as text_previewer,
)

# The #1823 door itself. Out of ``__all__`` on both trees, because the canonical
# home is :mod:`scistudio.previewers.helpers` — but importable, which is the
# promise that was made.
from scistudio.panels.helpers import (
    sanitize_svg as sanitize_svg,
)

__all__ = [
    "array_previewer",
    "artifact_previewer",
    "base_fallback_previewer",
    "collection_previewer",
    "composite_previewer",
    "core_previewer_specs",
    "dataframe_previewer",
    "plot_previewer",
    "series_previewer",
    "text_previewer",
]
