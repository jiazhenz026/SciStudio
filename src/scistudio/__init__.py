"""SciStudio -- AI-native, inclusive workflow runtime for multimodal scientific data."""

# #1742: ``__version__`` is derived from the single source of truth
# (:mod:`scistudio._version`) plus the local build counter, replacing the
# previously-hardcoded, drifted ``"0.1.0-dev"``. See ``scistudio.version`` and
# ``scripts/version.py``.
from scistudio.version import __version__

__all__ = ["__version__"]
