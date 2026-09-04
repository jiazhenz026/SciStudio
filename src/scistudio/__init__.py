"""SciStudio -- AI-native, inclusive workflow runtime for multimodal scientific data."""

# #1742: ``__version__`` is derived from the single source of truth
# (:mod:`scistudio._version`) plus the local build counter, replacing the
# previously-hardcoded, drifted ``"0.1.0-dev"``. See ``scistudio.version`` and
# ``scripts/version.py``.
from typing import TYPE_CHECKING, Any

from scistudio.version import __version__

if TYPE_CHECKING:  # pragma: no cover - imported for annotations only
    from scistudio.explore.notebook_api import input, load, output

__all__ = ["__version__", "input", "load", "output"]

#: The notebook helpers, exposed lazily (ADR-054 FR-010; spec assumption A-006).
#: A notebook writes ``scistudio.load(scistudio.input("signal"))``, so the three
#: names have to be reachable from the top-level package — but the explore
#: subsystem carries the storage stack and the kernel machinery behind it, and
#: every ``import scistudio`` in the product would then pay for it. So they are
#: resolved on first attribute access, the way
#: :mod:`scistudio.qa.governance` resolves its own delegated surface: importing
#: ``scistudio`` still costs only the version.
_LAZY_EXPLORE_HELPERS = frozenset({"input", "load", "output"})


def __getattr__(name: str) -> Any:
    """Resolve the notebook helpers on first use (FR-010)."""
    if name in _LAZY_EXPLORE_HELPERS:
        from scistudio.explore import notebook_api

        return getattr(notebook_api, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
