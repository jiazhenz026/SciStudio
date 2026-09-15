"""The deprecation shared by the whole public previewer surface."""
# Maintainer context (kept outside generated API documentation):
# Every public symbol of the Python previewer forms is deprecated in favour of
# HTML panels. ADR-054 §8: both legacy forms stay supported and deprecated in
# 0.3.5 and are removed in 0.3.6; the removal is tracked in #2288. The marker
# is applied to every public class and function of the canonical previewer roots
# and to the root modules themselves, so constants and type aliases that cannot
# carry a marker are covered by the module-wide declaration (ADR-052 §5, #2426).
# Runtime diagnostics for the legacy forms come from the code paths that load
# them, not from this marker.
# Development references: ADR-052, ADR-054, #2288, #2426.

from __future__ import annotations

from scistudio.stability import deprecated

PREVIEWERS_DEPRECATED = deprecated(
    since="0.3.5",
    removed_in="0.3.6",
    replacement=(
        "HTML panels, each a folder with a `panel.json` descriptor and an HTML page, "
        "discovered and validated through `scistudio.panels`."
    ),
)

__all__ = ["PREVIEWERS_DEPRECATED"]
