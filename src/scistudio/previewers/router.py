"""PreviewRouter: resolve a target over one legacy previewer registry."""
# Maintainer context (kept outside generated API documentation):
# The routing ladder is implemented once, in :mod:`scistudio.panels.router`,
# over panels and legacy previewers together (#2465). This class keeps the
# deprecated operational name importable for code that routes over a bare
# :class:`PreviewerRegistry`; it holds no ladder of its own and is removed with
# the rest of ``scistudio.previewers`` in 0.6.
# Development references: #2465, ADR-048, ADR-054.

from __future__ import annotations

from scistudio.previewers.models import PreviewerSpec, PreviewTarget
from scistudio.previewers.registry import PreviewerRegistry
from scistudio.stability import internal


@internal()
class PreviewRouter:
    """Resolve targets over the specs, choices and project defaults of one registry."""

    def __init__(self, registry: PreviewerRegistry) -> None:
        self._registry = registry

    def resolve(self, target: PreviewTarget) -> PreviewerSpec:
        """Return the single best spec for *target*, or raise a routing error."""
        from scistudio.panels.router import PanelRouter

        return PanelRouter.over_registry(self._registry).resolve(target)


__all__ = ["PreviewRouter"]
