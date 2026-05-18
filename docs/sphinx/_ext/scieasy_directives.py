"""SciEasy custom Sphinx directives — ADR-044 §10.2 (TC-1D.3/4).

Per ADR-044 §10.2, this module registers three directive classes:

- ``ScieasyBlockCatalog`` — per-block autosummary pages (entry-points)
- ``ScieasyRunnerCatalog`` — per-runner (Python / R / Julia) pages
- ``ScieasyAIBlockCatalog`` — per-ADR-035 AI-block registry entry

The directive implementations live under
``src/scieasy/qa/docs/directives/``; this module is the Sphinx-extension
entry point that imports and registers them via ``setup()``.

Phase 1D sub-PR 3 (Track C, #1184) fills the bodies.
"""

from __future__ import annotations

from typing import Any


def setup(app: Any) -> dict[str, Any]:
    """Sphinx extension entry point — registers the three catalog directives.

    Per ADR-044 §10.2::

        app.add_directive("scieasy-block-catalog", ScieasyBlockCatalog)
        app.add_directive("scieasy-runner-catalog", ScieasyRunnerCatalog)
        app.add_directive("scieasy-ai-block-catalog", ScieasyAIBlockCatalog)
    """
    from scieasy.qa.docs.directives.scieasy_ai_block_catalog import ScieasyAIBlockCatalog
    from scieasy.qa.docs.directives.scieasy_block_catalog import ScieasyBlockCatalog
    from scieasy.qa.docs.directives.scieasy_runner_catalog import ScieasyRunnerCatalog

    app.add_directive("scieasy-block-catalog", ScieasyBlockCatalog)
    app.add_directive("scieasy-runner-catalog", ScieasyRunnerCatalog)
    app.add_directive("scieasy-ai-block-catalog", ScieasyAIBlockCatalog)

    return {
        "version": "1.0.0",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
